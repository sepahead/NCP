//! Bounded, responder-authenticated idempotency for mutating NCP lifecycle RPCs.
//!
//! The operation digest covers the protocol-owned request-digest-v1 semantic
//! projection. A retry must set `retry=true`; that attempt bit and the renewable
//! authority envelope are intentionally outside the digest. If a server cannot
//! prove a prior result (cache expiry, non-durable restart, or eviction), it
//! returns `outcome_unknown` instead of risking a second state transition.

use crate::messages::{is_canonical_uuid_v4, JSON_SAFE_INTEGER_MAX};
pub use crate::messages::{OperationContext, OperationOutcome, ResponderReceipt};
use crate::request_digest::verify_request_digest;
use crate::security::{AuthenticatedActor, PrincipalRole};
use crate::{AuthorityLease, AuthorityMachine};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::fmt;

pub const MAX_OPERATION_CACHE_ENTRIES: usize = 65_536;
pub const MAX_OPERATION_RETENTION_MS: u64 = 86_400_000;
const IDEMPOTENCY_SNAPSHOT_VERSION: u32 = 1;

/// Receiver-local clock sample used for one idempotency decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct OperationClock {
    pub utc_ms: i64,
    pub monotonic_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResponderBinding {
    pub principal_id: String,
    pub entity_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum OperationDecision {
    Execute,
    Replay(ResponderReceipt),
    OutcomeUnknown,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OperationError {
    pub code: &'static str,
    pub detail: String,
}

impl OperationError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for OperationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for OperationError {}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct OperationKey {
    principal_id: String,
    session_id: String,
    session_epoch: String,
    operation_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
enum RecordState {
    Pending,
    Terminal(ResponderReceipt),
    Unavailable,
}

#[derive(Deserialize)]
enum StrictSnapshotRecordState {
    Pending,
    Terminal(StrictSnapshotReceipt),
    Unavailable,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct StrictSnapshotReceipt {
    operation_id: String,
    request_digest: String,
    result_digest: String,
    outcome: OperationOutcome,
    state_version: u64,
    committed_at_utc_ms: i64,
    responder_principal_id: String,
    responder_entity_id: String,
}

impl From<StrictSnapshotRecordState> for RecordState {
    fn from(value: StrictSnapshotRecordState) -> Self {
        match value {
            StrictSnapshotRecordState::Pending => Self::Pending,
            StrictSnapshotRecordState::Terminal(receipt) => Self::Terminal(ResponderReceipt {
                operation_id: receipt.operation_id,
                request_digest: receipt.request_digest,
                result_digest: receipt.result_digest,
                outcome: receipt.outcome,
                state_version: receipt.state_version,
                committed_at_utc_ms: receipt.committed_at_utc_ms,
                responder_principal_id: receipt.responder_principal_id,
                responder_entity_id: receipt.responder_entity_id,
            }),
            StrictSnapshotRecordState::Unavailable => Self::Unavailable,
        }
    }
}

fn deserialize_snapshot_record_state<'de, D>(deserializer: D) -> Result<RecordState, D::Error>
where
    D: serde::Deserializer<'de>,
{
    StrictSnapshotRecordState::deserialize(deserializer).map(Into::into)
}

#[derive(Clone, Debug)]
struct OperationRecord {
    request_digest: String,
    expected_state_version: u64,
    reserved_at_utc_ms: i64,
    clock_floor_utc_ms: i64,
    clock_floor_monotonic_ms: u64,
    state: RecordState,
    expires_at_monotonic_ms: Option<u64>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SnapshotRecord {
    request_digest: String,
    expected_state_version: u64,
    reserved_at_utc_ms: i64,
    clock_floor_utc_ms: i64,
    #[serde(deserialize_with = "deserialize_snapshot_record_state")]
    state: RecordState,
    remaining_retention_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdempotencySnapshot {
    version: u32,
    responder: ResponderBinding,
    max_entries: usize,
    retention_ms: u64,
    records: Vec<(OperationKey, SnapshotRecord)>,
}

#[derive(Clone, Debug)]
pub struct IdempotencyCache {
    responder: ResponderBinding,
    max_entries: usize,
    retention_ms: u64,
    records: BTreeMap<OperationKey, OperationRecord>,
    insertion_order: VecDeque<OperationKey>,
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .as_bytes()
            .iter()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}

fn valid_id(value: &str, max: usize) -> bool {
    value.len() <= max && crate::keys::valid_id_segment(value)
}

fn valid_positive_json_timestamp(value: i64) -> bool {
    value > 0 && value <= JSON_SAFE_INTEGER_MAX
}

impl OperationContext {
    pub fn validate(
        &self,
        request: &serde_json::Value,
        now_utc_ms: i64,
    ) -> Result<(), OperationError> {
        if !valid_positive_json_timestamp(now_utc_ms) {
            return Err(OperationError::new(
                "NCP-OP-002",
                "receiver UTC clock is outside the positive JSON-safe timestamp range",
            ));
        }
        if !is_canonical_uuid_v4(&self.operation_id) || !is_canonical_uuid_v4(&self.session_epoch) {
            return Err(OperationError::new(
                "NCP-OP-001",
                "operation_id and session_epoch must be canonical lowercase UUIDv4 values",
            ));
        }
        if !valid_digest(&self.request_digest) {
            return Err(OperationError::new(
                "NCP-OP-001",
                "request digest is malformed",
            ));
        }
        let embedded = request
            .get("operation")
            .cloned()
            .and_then(|value| serde_json::from_value::<OperationContext>(value).ok())
            .ok_or_else(|| {
                OperationError::new("NCP-OP-001", "request operation context is malformed")
            })?;
        if &embedded != self {
            return Err(OperationError::new(
                "NCP-OP-001",
                "request operation context does not match the reserved context",
            ));
        }
        verify_request_digest(request)
            .map_err(|error| OperationError::new("NCP-OP-001", error.to_string()))?;
        if self.expected_state_version > JSON_SAFE_INTEGER_MAX as u64 {
            return Err(OperationError::new(
                "NCP-OP-004",
                "expected state version exceeds the JSON-safe integer range",
            ));
        }
        if !valid_positive_json_timestamp(self.deadline_utc_ms)
            || self.deadline_utc_ms <= now_utc_ms
        {
            return Err(OperationError::new(
                "NCP-OP-002",
                "operation deadline is invalid or expired (equality is expired)",
            ));
        }
        Ok(())
    }
}

impl ResponderBinding {
    fn validate(&self) -> Result<(), OperationError> {
        if !valid_id(&self.principal_id, 128) || !valid_id(&self.entity_id, 128) {
            return Err(OperationError::new(
                "NCP-AUTH-002",
                "responder principal/entity is empty, wildcarded, or unbounded",
            ));
        }
        Ok(())
    }

    fn verify_actor(&self, actor: &AuthenticatedActor) -> Result<(), OperationError> {
        if actor.principal_id != self.principal_id || actor.entity_id != self.entity_id {
            return Err(OperationError::new(
                "NCP-AUTH-002",
                "authenticated responder is not the single configured responder",
            ));
        }
        Ok(())
    }
}

impl IdempotencyCache {
    pub fn new(
        responder: ResponderBinding,
        max_entries: usize,
        retention_ms: u64,
    ) -> Result<Self, OperationError> {
        responder.validate()?;
        if max_entries == 0 || max_entries > MAX_OPERATION_CACHE_ENTRIES {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency cache entry bound is invalid",
            ));
        }
        if retention_ms == 0 || retention_ms > MAX_OPERATION_RETENTION_MS {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency retention is invalid",
            ));
        }
        Ok(Self {
            responder,
            max_entries,
            retention_ms,
            records: BTreeMap::new(),
            insertion_order: VecDeque::new(),
        })
    }

    fn key(
        caller: &AuthenticatedActor,
        session_id: &str,
        context: &OperationContext,
    ) -> Result<OperationKey, OperationError> {
        if !valid_id(&caller.principal_id, 128)
            || !valid_id(&caller.entity_id, 128)
            || !valid_id(session_id, 64)
        {
            return Err(OperationError::new(
                "NCP-AUTH-004",
                "operation principal/session identity is invalid",
            ));
        }
        if !is_canonical_uuid_v4(&context.session_epoch)
            || !is_canonical_uuid_v4(&context.operation_id)
            || !valid_digest(&context.request_digest)
        {
            return Err(OperationError::new(
                "NCP-OP-001",
                "operation reservation identity or digest is invalid",
            ));
        }
        Ok(OperationKey {
            principal_id: caller.principal_id.clone(),
            session_id: session_id.into(),
            session_epoch: context.session_epoch.clone(),
            operation_id: context.operation_id.clone(),
        })
    }

    fn validate_snapshot_key(key: &OperationKey) -> Result<(), OperationError> {
        if !valid_id(&key.principal_id, 128) || !valid_id(&key.session_id, 64) {
            return Err(OperationError::new(
                "NCP-AUTH-004",
                "idempotency snapshot principal/session identity is invalid",
            ));
        }
        if !is_canonical_uuid_v4(&key.session_epoch) || !is_canonical_uuid_v4(&key.operation_id) {
            return Err(OperationError::new(
                "NCP-OP-001",
                "idempotency snapshot operation identity is invalid",
            ));
        }
        Ok(())
    }

    fn verify_session_binding(
        request: &serde_json::Value,
        session_id: &str,
        context: &OperationContext,
    ) -> Result<(), OperationError> {
        let request_session_id = request
            .get("session_id")
            .and_then(serde_json::Value::as_str);
        let request_generation = request
            .get("session")
            .and_then(serde_json::Value::as_object)
            .and_then(|session| session.get("generation"))
            .and_then(serde_json::Value::as_str);
        if request_session_id != Some(session_id)
            || request_generation != Some(context.session_epoch.as_str())
        {
            return Err(OperationError::new(
                "NCP-AUTH-004",
                "request, cache key, and operation context do not name the same session",
            ));
        }
        Ok(())
    }

    fn validate_receipt_contents(
        responder: &ResponderBinding,
        receipt: &ResponderReceipt,
    ) -> Result<(), OperationError> {
        if receipt.responder_principal_id != responder.principal_id
            || receipt.responder_entity_id != responder.entity_id
            || !valid_id(&receipt.responder_principal_id, 128)
            || !valid_id(&receipt.responder_entity_id, 128)
            || !is_canonical_uuid_v4(&receipt.operation_id)
            || !valid_digest(&receipt.request_digest)
            || !valid_digest(&receipt.result_digest)
            || receipt.state_version > JSON_SAFE_INTEGER_MAX as u64
            || !valid_positive_json_timestamp(receipt.committed_at_utc_ms)
            || matches!(
                receipt.outcome,
                OperationOutcome::Unknown | OperationOutcome::OutcomeUnknown
            )
        {
            return Err(OperationError::new(
                "NCP-AUTH-002",
                "responder receipt identity or terminal contents are invalid",
            ));
        }
        Ok(())
    }

    fn validate_snapshot_record(
        responder: &ResponderBinding,
        retention_ms: u64,
        key: &OperationKey,
        record: &SnapshotRecord,
    ) -> Result<(), OperationError> {
        Self::validate_snapshot_key(key)?;
        if !valid_digest(&record.request_digest)
            || record.expected_state_version > JSON_SAFE_INTEGER_MAX as u64
            || !valid_positive_json_timestamp(record.reserved_at_utc_ms)
            || !valid_positive_json_timestamp(record.clock_floor_utc_ms)
            || record.clock_floor_utc_ms < record.reserved_at_utc_ms
            || record.remaining_retention_ms == 0
            || record.remaining_retention_ms > retention_ms
        {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency snapshot record bounds are invalid",
            ));
        }
        if let RecordState::Terminal(receipt) = &record.state {
            Self::validate_receipt_contents(responder, receipt)?;
            if receipt.operation_id != key.operation_id
                || receipt.request_digest != record.request_digest
                || receipt.state_version < record.expected_state_version
                || receipt.committed_at_utc_ms < record.reserved_at_utc_ms
                || record.clock_floor_utc_ms < receipt.committed_at_utc_ms
            {
                return Err(OperationError::new(
                    "NCP-OP-001",
                    "idempotency snapshot receipt conflicts with its reservation",
                ));
            }
        }
        Ok(())
    }

    fn verify_authority(
        request: &serde_json::Value,
        context: &OperationContext,
        caller: &AuthenticatedActor,
        authority: &AuthorityMachine,
        now_monotonic_ms: u64,
    ) -> Result<(), OperationError> {
        if caller.role != PrincipalRole::Commander {
            return Err(OperationError::new(
                "NCP-AUTH-003",
                "only an authenticated commander may execute a lifecycle mutation",
            ));
        }
        let supplied = request
            .get("authority")
            .cloned()
            .and_then(|value| serde_json::from_value::<AuthorityLease>(value).ok())
            .ok_or_else(|| {
                OperationError::new("NCP-LEASE-003", "request authority lease is malformed")
            })?;
        let active = authority.active_lease(now_monotonic_ms).ok_or_else(|| {
            OperationError::new(
                "NCP-LEASE-002",
                "there is no unexpired active authority lease",
            )
        })?;
        if &supplied != active {
            return Err(OperationError::new(
                "NCP-LEASE-001",
                "request authority is not the currently active lease",
            ));
        }
        if supplied.session_epoch != context.session_epoch
            || supplied.holder_principal_id != caller.principal_id
            || supplied.holder_entity_id != caller.entity_id
        {
            return Err(OperationError::new(
                "NCP-AUTH-002",
                "authenticated caller/session does not match the active authority holder",
            ));
        }
        Ok(())
    }

    fn purge_expired(&mut self, now_monotonic_ms: u64) {
        self.records.retain(|_, record| match &record.state {
            RecordState::Pending => true,
            RecordState::Terminal(_) | RecordState::Unavailable => record
                .expires_at_monotonic_ms
                .is_some_and(|expires_at| expires_at > now_monotonic_ms),
        });
        self.insertion_order
            .retain(|key| self.records.contains_key(key));
    }

    fn make_room(&mut self) -> Result<(), OperationError> {
        let candidates = self.insertion_order.len();
        for _ in 0..candidates {
            if self.records.len() < self.max_entries {
                break;
            }
            let Some(candidate) = self.insertion_order.pop_front() else {
                break;
            };
            match self.records.get(&candidate) {
                Some(record) if matches!(record.state, RecordState::Pending) => {
                    self.insertion_order.push_back(candidate);
                }
                Some(_) => {
                    self.records.remove(&candidate);
                }
                None => {}
            }
        }
        if self.records.len() >= self.max_entries {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency cache is full of in-progress operations",
            ));
        }
        Ok(())
    }

    // Keep authenticated caller, session/request identity, live authority,
    // authoritative state, and the receiver clock explicit at the trust boundary.
    // Bundling them into one caller-constructible bag would make it easier to
    // accidentally reuse stale authority or state across requests.
    #[expect(clippy::too_many_arguments)]
    pub fn begin(
        &mut self,
        caller: &AuthenticatedActor,
        session_id: &str,
        context: &OperationContext,
        request: &serde_json::Value,
        authority: &AuthorityMachine,
        current_state_version: u64,
        clock: OperationClock,
    ) -> Result<OperationDecision, OperationError> {
        context.validate(request, clock.utc_ms)?;
        Self::verify_session_binding(request, session_id, context)?;
        if current_state_version > JSON_SAFE_INTEGER_MAX as u64 {
            return Err(OperationError::new(
                "NCP-OP-004",
                "authoritative state version exceeds the JSON-safe integer range",
            ));
        }
        Self::verify_authority(request, context, caller, authority, clock.monotonic_ms)?;
        let key = Self::key(caller, session_id, context)?;
        self.purge_expired(clock.monotonic_ms);
        if let Some(record) = self.records.get_mut(&key) {
            if clock.utc_ms < record.clock_floor_utc_ms
                || clock.monotonic_ms < record.clock_floor_monotonic_ms
            {
                return Err(OperationError::new(
                    "NCP-OP-006",
                    "receiver clock precedes the retained idempotency record",
                ));
            }
            record.clock_floor_utc_ms = clock.utc_ms;
            record.clock_floor_monotonic_ms = clock.monotonic_ms;
            if record.request_digest != context.request_digest {
                return Err(OperationError::new(
                    "NCP-OP-001",
                    "operation ID was reused with different request content",
                ));
            }
            return match &record.state {
                RecordState::Terminal(receipt) => Ok(OperationDecision::Replay(receipt.clone())),
                RecordState::Unavailable => Ok(OperationDecision::OutcomeUnknown),
                RecordState::Pending => Err(OperationError::new(
                    "NCP-OP-005",
                    "the identical operation is still in progress",
                )),
            };
        }
        if context.retry {
            return Ok(OperationDecision::OutcomeUnknown);
        }
        if context.expected_state_version != current_state_version {
            return Err(OperationError::new(
                "NCP-OP-004",
                "expected state version does not match the authoritative state",
            ));
        }
        self.make_room()?;
        clock
            .monotonic_ms
            .checked_add(self.retention_ms)
            .ok_or_else(|| OperationError::new("NCP-OP-006", "retention deadline overflow"))?;
        self.records.insert(
            key.clone(),
            OperationRecord {
                request_digest: context.request_digest.clone(),
                expected_state_version: context.expected_state_version,
                reserved_at_utc_ms: clock.utc_ms,
                clock_floor_utc_ms: clock.utc_ms,
                clock_floor_monotonic_ms: clock.monotonic_ms,
                state: RecordState::Pending,
                expires_at_monotonic_ms: None,
            },
        );
        self.insertion_order.push_back(key);
        Ok(OperationDecision::Execute)
    }

    // The commit API deliberately keeps authenticated identity, request identity,
    // and terminal result material separate so callers cannot accidentally attest
    // a result for a different operation.
    #[expect(clippy::too_many_arguments)]
    pub fn commit(
        &mut self,
        caller: &AuthenticatedActor,
        session_id: &str,
        context: &OperationContext,
        actor: &AuthenticatedActor,
        outcome: OperationOutcome,
        result_bytes: &[u8],
        state_version: u64,
        clock: OperationClock,
    ) -> Result<ResponderReceipt, OperationError> {
        self.responder.verify_actor(actor)?;
        if state_version > JSON_SAFE_INTEGER_MAX as u64
            || !valid_positive_json_timestamp(clock.utc_ms)
            || matches!(
                outcome,
                OperationOutcome::Unknown | OperationOutcome::OutcomeUnknown
            )
        {
            return Err(OperationError::new(
                "NCP-OP-004",
                "terminal commit outcome, state version, or timestamp is invalid",
            ));
        }
        let key = Self::key(caller, session_id, context)?;
        self.purge_expired(clock.monotonic_ms);
        let receipt = ResponderReceipt {
            operation_id: context.operation_id.clone(),
            request_digest: context.request_digest.clone(),
            result_digest: sha256_hex(result_bytes),
            outcome,
            state_version,
            committed_at_utc_ms: clock.utc_ms,
            responder_principal_id: actor.principal_id.clone(),
            responder_entity_id: actor.entity_id.clone(),
        };
        let record = self.records.get_mut(&key).ok_or_else(|| {
            OperationError::new("NCP-OP-003", "operation reservation is unavailable")
        })?;
        if clock.utc_ms < record.clock_floor_utc_ms
            || clock.monotonic_ms < record.clock_floor_monotonic_ms
        {
            return Err(OperationError::new(
                "NCP-OP-004",
                "terminal commit precedes the reserved state or receiver clock",
            ));
        }
        if record.request_digest != context.request_digest {
            return Err(OperationError::new(
                "NCP-OP-001",
                "commit digest conflicts with the reserved operation",
            ));
        }
        if state_version < record.expected_state_version {
            return Err(OperationError::new(
                "NCP-OP-004",
                "terminal commit precedes the reserved state or receiver clock",
            ));
        }
        if let RecordState::Terminal(committed) = &record.state {
            if committed == &receipt {
                return Ok(committed.clone());
            }
            return Err(OperationError::new(
                "NCP-OP-001",
                "terminal operation was committed again with conflicting result material",
            ));
        }
        if matches!(record.state, RecordState::Unavailable) {
            return Err(OperationError::new(
                "NCP-OP-003",
                "operation completion is unavailable",
            ));
        }
        let expires_at_monotonic_ms = clock
            .monotonic_ms
            .checked_add(self.retention_ms)
            .ok_or_else(|| OperationError::new("NCP-OP-006", "retention deadline overflow"))?;
        record.state = RecordState::Terminal(receipt.clone());
        record.clock_floor_utc_ms = clock.utc_ms;
        record.clock_floor_monotonic_ms = clock.monotonic_ms;
        record.expires_at_monotonic_ms = Some(expires_at_monotonic_ms);
        Ok(receipt)
    }

    /// Captures unexpired records using remaining durations rather than
    /// process-local absolute monotonic timestamps.
    ///
    /// # Errors
    ///
    /// Returns an error if the supplied clock moved behind a record's latest
    /// retained transition or if the internal map/order invariant is broken.
    pub fn snapshot(&self, now_monotonic_ms: u64) -> Result<IdempotencySnapshot, OperationError> {
        let mut records = Vec::with_capacity(self.records.len());
        let mut seen = BTreeSet::new();
        for key in &self.insertion_order {
            if !seen.insert(key) {
                return Err(OperationError::new(
                    "NCP-OP-006",
                    "idempotency insertion order contains a duplicate key",
                ));
            }
            let record = self.records.get(key).ok_or_else(|| {
                OperationError::new(
                    "NCP-OP-006",
                    "idempotency insertion order references a missing record",
                )
            })?;
            if now_monotonic_ms < record.clock_floor_monotonic_ms {
                return Err(OperationError::new(
                    "NCP-OP-006",
                    "idempotency snapshot clock precedes the retained record",
                ));
            }
            let remaining_retention_ms = if matches!(&record.state, RecordState::Pending) {
                self.retention_ms
            } else {
                let expires_at_monotonic_ms = record.expires_at_monotonic_ms.ok_or_else(|| {
                    OperationError::new(
                        "NCP-OP-006",
                        "terminal idempotency record has no retention deadline",
                    )
                })?;
                if expires_at_monotonic_ms <= now_monotonic_ms {
                    continue;
                }
                expires_at_monotonic_ms
                    .checked_sub(now_monotonic_ms)
                    .filter(|remaining| *remaining <= self.retention_ms)
                    .ok_or_else(|| {
                        OperationError::new(
                            "NCP-OP-006",
                            "idempotency snapshot clock precedes the retained operation window",
                        )
                    })?
            };
            records.push((
                key.clone(),
                SnapshotRecord {
                    request_digest: record.request_digest.clone(),
                    expected_state_version: record.expected_state_version,
                    reserved_at_utc_ms: record.reserved_at_utc_ms,
                    clock_floor_utc_ms: record.clock_floor_utc_ms,
                    state: record.state.clone(),
                    remaining_retention_ms,
                },
            ));
        }
        if seen.len() != self.records.len() {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency records are missing from insertion order",
            ));
        }
        Ok(IdempotencySnapshot {
            version: IDEMPOTENCY_SNAPSHOT_VERSION,
            responder: self.responder.clone(),
            max_entries: self.max_entries,
            retention_ms: self.retention_ms,
            records,
        })
    }

    /// Restores a snapshot only when its identity and limits exactly match the
    /// independently configured local cache.
    ///
    /// Pending records become unavailable tombstones because a restart cannot
    /// prove whether their side effects committed. Remaining retention durations
    /// are rebased onto the new process's monotonic clock.
    ///
    /// # Errors
    ///
    /// Returns an error for a configuration mismatch, malformed or duplicate
    /// record, inconsistent terminal receipt, or monotonic deadline overflow.
    pub fn restore(
        snapshot: IdempotencySnapshot,
        responder: ResponderBinding,
        max_entries: usize,
        retention_ms: u64,
        now_monotonic_ms: u64,
    ) -> Result<Self, OperationError> {
        let mut cache = Self::new(responder, max_entries, retention_ms)?;
        if snapshot.version != IDEMPOTENCY_SNAPSHOT_VERSION {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency snapshot version is unsupported",
            ));
        }
        if snapshot.responder != cache.responder {
            return Err(OperationError::new(
                "NCP-AUTH-002",
                "idempotency snapshot responder does not match local configuration",
            ));
        }
        if snapshot.max_entries != cache.max_entries || snapshot.retention_ms != cache.retention_ms
        {
            return Err(OperationError::new(
                "NCP-OP-006",
                "idempotency snapshot limits do not match local configuration",
            ));
        }
        if snapshot.records.len() > cache.max_entries {
            return Err(OperationError::new(
                "NCP-OP-006",
                "snapshot exceeds the configured cache capacity",
            ));
        }
        for (key, snapshot_record) in snapshot.records {
            Self::validate_snapshot_record(
                &cache.responder,
                cache.retention_ms,
                &key,
                &snapshot_record,
            )?;
            let expires_at_monotonic_ms = now_monotonic_ms
                .checked_add(snapshot_record.remaining_retention_ms)
                .ok_or_else(|| {
                    OperationError::new(
                        "NCP-OP-006",
                        "restored idempotency retention deadline overflows",
                    )
                })?;
            let state = if matches!(&snapshot_record.state, RecordState::Pending) {
                RecordState::Unavailable
            } else {
                snapshot_record.state
            };
            let record = OperationRecord {
                request_digest: snapshot_record.request_digest,
                expected_state_version: snapshot_record.expected_state_version,
                reserved_at_utc_ms: snapshot_record.reserved_at_utc_ms,
                clock_floor_utc_ms: snapshot_record.clock_floor_utc_ms,
                clock_floor_monotonic_ms: now_monotonic_ms,
                state,
                expires_at_monotonic_ms: Some(expires_at_monotonic_ms),
            };
            if cache.records.insert(key.clone(), record).is_some() {
                return Err(OperationError::new(
                    "NCP-OP-001",
                    "idempotency snapshot contains duplicate operation keys",
                ));
            }
            cache.insertion_order.push_back(key);
        }
        Ok(cache)
    }

    /// Verifies the authenticated responder and correlates a terminal receipt to
    /// the caller's expected operation identity and exact result bytes.
    ///
    /// # Errors
    ///
    /// Returns an error when the responder or receipt is malformed, unauthenticated,
    /// nonterminal, or inconsistent with `context` or `result_bytes`.
    pub fn verify_receipt(
        &self,
        receipt: &ResponderReceipt,
        actor: &AuthenticatedActor,
        context: &OperationContext,
        result_bytes: &[u8],
    ) -> Result<(), OperationError> {
        self.responder.verify_actor(actor)?;
        Self::validate_receipt_contents(&self.responder, receipt)?;
        if !is_canonical_uuid_v4(&context.operation_id)
            || !valid_digest(&context.request_digest)
            || receipt.operation_id != context.operation_id
            || receipt.request_digest != context.request_digest
            || receipt.result_digest != sha256_hex(result_bytes)
        {
            return Err(OperationError::new(
                "NCP-OP-001",
                "responder receipt does not match the expected operation and result",
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const OP: &str = "123e4567-e89b-42d3-a456-426614174010";
    const EPOCH: &str = "123e4567-e89b-42d3-a456-426614174000";

    fn server(id: &str) -> AuthenticatedActor {
        AuthenticatedActor {
            principal_id: id.into(),
            certificate_identity: format!("urn:ncp:{id}"),
            entity_id: "body".into(),
            role: PrincipalRole::Body,
            may_reset_estop: false,
            may_override: false,
        }
    }

    fn caller(id: &str) -> AuthenticatedActor {
        AuthenticatedActor {
            principal_id: id.into(),
            certificate_identity: format!("urn:ncp:{id}"),
            entity_id: format!("{id}-entity"),
            role: PrincipalRole::Commander,
            may_reset_estop: false,
            may_override: false,
        }
    }

    fn lease(
        holder: &AuthenticatedActor,
        term: u64,
        lease_id: &str,
        issued_at_utc_ms: i64,
        expires_at_utc_ms: i64,
    ) -> AuthorityLease {
        AuthorityLease {
            session_epoch: EPOCH.into(),
            term,
            lease_id: lease_id.into(),
            issuer_principal_id: holder.principal_id.clone(),
            holder_principal_id: holder.principal_id.clone(),
            holder_entity_id: holder.entity_id.clone(),
            issued_at_utc_ms,
            expires_at_utc_ms,
        }
    }

    fn authority(
        holder: &AuthenticatedActor,
        active_lease: AuthorityLease,
        now_utc_ms: i64,
        now_monotonic_ms: u64,
    ) -> AuthorityMachine {
        let mut authority = AuthorityMachine::new(EPOCH).unwrap();
        authority.begin_open().unwrap();
        authority.initialize().unwrap();
        authority
            .acquire(active_lease, holder, holder, now_utc_ms, now_monotonic_ms)
            .unwrap();
        authority
    }

    fn request(
        retry: bool,
        advance_ms: f64,
        deadline_utc_ms: i64,
        active_lease: &AuthorityLease,
    ) -> (serde_json::Value, OperationContext) {
        let mut context = OperationContext {
            operation_id: OP.into(),
            request_digest: String::new(),
            session_epoch: EPOCH.into(),
            expected_state_version: 7,
            deadline_utc_ms,
            retry,
        };
        let mut request = serde_json::json!({
            "kind": "step_request",
            "ncp_version": "1.0",
            "session_id": "session",
            "session": {"generation": EPOCH},
            "operation": context.clone(),
            "authority": active_lease,
            "advance_ms": advance_ms
        });
        context.request_digest = crate::request_digest::request_digest(&request).unwrap();
        request["operation"] = serde_json::to_value(&context).unwrap();
        (request, context)
    }

    fn refresh_digest(request: &mut serde_json::Value, context: &mut OperationContext) {
        context.request_digest = crate::request_digest::request_digest(request).unwrap();
        request["operation"] = serde_json::to_value(context).unwrap();
    }

    fn clock(utc_ms: i64, monotonic_ms: u64) -> OperationClock {
        OperationClock {
            utc_ms,
            monotonic_ms,
        }
    }

    fn cache() -> IdempotencyCache {
        IdempotencyCache::new(
            ResponderBinding {
                principal_id: "server".into(),
                entity_id: "body".into(),
            },
            8,
            1_000,
        )
        .unwrap()
    }

    fn restore_cache(
        snapshot: IdempotencySnapshot,
        now_monotonic_ms: u64,
    ) -> Result<IdempotencyCache, OperationError> {
        IdempotencyCache::restore(
            snapshot,
            ResponderBinding {
                principal_id: "server".into(),
                entity_id: "body".into(),
            },
            8,
            1_000,
            now_monotonic_ms,
        )
    }

    fn committed_snapshot() -> IdempotencySnapshot {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut operation_cache = cache();
        let (initial_request, context) = request(false, 10.0, 62_000, &lease);
        operation_cache
            .begin(
                &caller,
                "session",
                &context,
                &initial_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        operation_cache
            .commit(
                &caller,
                "session",
                &context,
                &server("server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(1_100, 20),
            )
            .unwrap();
        operation_cache.snapshot(20).unwrap()
    }

    #[test]
    fn cache_identity_rejects_unicode_bom_delimiter() {
        let error = IdempotencyCache::new(
            ResponderBinding {
                principal_id: "server\u{feff}suffix".into(),
                entity_id: "body".into(),
            },
            8,
            1_000,
        )
        .unwrap_err();

        assert_eq!(error.code, "NCP-AUTH-002");
    }

    #[test]
    fn make_room_scans_mixed_capacity_once_and_preserves_pending_records() {
        let mut operation_cache = IdempotencyCache::new(
            ResponderBinding {
                principal_id: "server".into(),
                entity_id: "body".into(),
            },
            2_049,
            1_000,
        )
        .unwrap();
        let mut pending_keys = Vec::with_capacity(2_048);
        for index in 0..2_048 {
            let key = OperationKey {
                principal_id: "caller".into(),
                session_id: "session".into(),
                session_epoch: EPOCH.into(),
                operation_id: format!("123e4567-e89b-42d3-a456-{index:012x}"),
            };
            pending_keys.push(key.clone());
            operation_cache.records.insert(
                key.clone(),
                OperationRecord {
                    request_digest: "a".repeat(64),
                    expected_state_version: 7,
                    reserved_at_utc_ms: 1_000,
                    clock_floor_utc_ms: 1_000,
                    clock_floor_monotonic_ms: 10,
                    state: RecordState::Pending,
                    expires_at_monotonic_ms: None,
                },
            );
            operation_cache.insertion_order.push_back(key);
        }
        let evictable = OperationKey {
            principal_id: "caller".into(),
            session_id: "session".into(),
            session_epoch: EPOCH.into(),
            operation_id: "123e4567-e89b-42d3-a456-426614174999".into(),
        };
        operation_cache.records.insert(
            evictable.clone(),
            OperationRecord {
                request_digest: "b".repeat(64),
                expected_state_version: 7,
                reserved_at_utc_ms: 1_000,
                clock_floor_utc_ms: 1_000,
                clock_floor_monotonic_ms: 10,
                state: RecordState::Unavailable,
                expires_at_monotonic_ms: Some(1_010),
            },
        );
        operation_cache.insertion_order.push_back(evictable.clone());

        operation_cache.make_room().unwrap();

        assert!(!operation_cache.records.contains_key(&evictable));
        assert!(pending_keys
            .iter()
            .all(|key| operation_cache.records.contains_key(key)));
    }

    #[test]
    fn snapshot_json_round_trip_preserves_strict_terminal_record() {
        let snapshot = committed_snapshot();
        let encoded = serde_json::to_vec(&snapshot).unwrap();

        let decoded = serde_json::from_slice::<IdempotencySnapshot>(&encoded).unwrap();

        assert_eq!(decoded, snapshot);
    }

    #[test]
    fn snapshot_deserialization_rejects_unknown_terminal_receipt_fields() {
        let mut encoded = serde_json::to_value(committed_snapshot()).unwrap();
        encoded["records"][0][1]["state"]["Terminal"]["unrecognized"] = serde_json::json!(true);

        let error = serde_json::from_value::<IdempotencySnapshot>(encoded).unwrap_err();

        assert!(error.to_string().contains("unknown field"));
    }

    #[test]
    fn lost_response_replays_original_without_second_transition() {
        let server = server("server");
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();
        let (first_request, first) = request(false, 10.0, 62_000, &lease);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &first,
                    &first_request,
                    &authority,
                    7,
                    clock(1_000, 10),
                )
                .unwrap(),
            OperationDecision::Execute
        );
        let receipt = cache
            .commit(
                &caller,
                "session",
                &first,
                &server,
                OperationOutcome::Succeeded,
                br#"{"state":8}"#,
                8,
                clock(1_100, 20),
            )
            .unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_099, 21),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_200, 19),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_200, 100),
                )
                .unwrap(),
            OperationDecision::Replay(receipt)
        );
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_199, 101),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_201, 99),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
    }

    #[test]
    fn changed_duplicate_conflicts_and_pending_duplicate_does_not_execute() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();
        let (first_request, first) = request(false, 10.0, 62_000, &lease);
        cache
            .begin(
                &caller,
                "session",
                &first,
                &first_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);
        let pending = cache
            .begin(
                &caller,
                "session",
                &retry,
                &retry_request,
                &authority,
                7,
                clock(1_001, 11),
            )
            .unwrap_err();
        assert_eq!(pending.code, "NCP-OP-005");
        let (changed_request, changed) = request(true, 11.0, 62_000, &lease);
        let conflict = cache
            .begin(
                &caller,
                "session",
                &changed,
                &changed_request,
                &authority,
                7,
                clock(1_001, 11),
            )
            .unwrap_err();
        assert_eq!(conflict.code, "NCP-OP-001");
    }

    #[test]
    fn pending_reservation_does_not_expire_and_terminal_retention_starts_at_commit() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();
        let (initial_request, context) = request(false, 10.0, 62_000, &lease);
        cache
            .begin(
                &caller,
                "session",
                &context,
                &initial_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();

        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    7,
                    clock(2_000, 1_011),
                )
                .unwrap_err()
                .code,
            "NCP-OP-005"
        );
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    7,
                    clock(2_001, 1_010),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        let receipt = cache
            .commit(
                &caller,
                "session",
                &context,
                &server("server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(2_001, 1_012),
            )
            .unwrap();
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(2_100, 2_011),
                )
                .unwrap(),
            OperationDecision::Replay(receipt)
        );
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(2_100, 2_012),
                )
                .unwrap(),
            OperationDecision::OutcomeUnknown
        );
    }

    #[test]
    fn existing_reservation_rejects_receiver_utc_rewind() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut operation_cache = cache();
        let (initial_request, context) = request(false, 10.0, 62_000, &lease);
        operation_cache
            .begin(
                &caller,
                "session",
                &context,
                &initial_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);

        let error = operation_cache
            .begin(
                &caller,
                "session",
                &retry,
                &retry_request,
                &authority,
                7,
                clock(999, 11),
            )
            .unwrap_err();

        assert_eq!(error.code, "NCP-OP-006");
    }

    #[test]
    fn existing_reservation_rejects_receiver_monotonic_rewind() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut operation_cache = cache();
        let (initial_request, context) = request(false, 10.0, 62_000, &lease);
        operation_cache
            .begin(
                &caller,
                "session",
                &context,
                &initial_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);

        let error = operation_cache
            .begin(
                &caller,
                "session",
                &retry,
                &retry_request,
                &authority,
                7,
                clock(1_001, 9),
            )
            .unwrap_err();

        assert_eq!(error.code, "NCP-OP-006");
    }

    #[test]
    fn only_configured_authenticated_responder_can_commit() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();
        let (request, context) = request(false, 10.0, 62_000, &lease);
        cache
            .begin(
                &caller,
                "session",
                &context,
                &request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let error = cache
            .commit(
                &caller,
                "session",
                &context,
                &server("sibling-server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(1_100, 20),
            )
            .unwrap_err();
        assert_eq!(error.code, "NCP-AUTH-002");
    }

    #[test]
    fn commit_rejects_invalid_or_pre_reservation_material_and_conflicting_recommit() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();
        let (request, context) = request(false, 10.0, 62_000, &lease);
        cache
            .begin(
                &caller,
                "session",
                &context,
                &request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();

        for timestamp in [0, -1, 999, JSON_SAFE_INTEGER_MAX + 1] {
            let error = cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"ok",
                    8,
                    clock(timestamp, 11),
                )
                .unwrap_err();
            assert_eq!(error.code, "NCP-OP-004");
        }

        assert_eq!(
            cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"ok",
                    8,
                    clock(1_100, 9),
                )
                .unwrap_err()
                .code,
            "NCP-OP-004"
        );
        assert_eq!(
            cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"ok",
                    8,
                    clock(1_100, u64::MAX),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );

        assert_eq!(
            cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"ok",
                    6,
                    clock(1_100, 20),
                )
                .unwrap_err()
                .code,
            "NCP-OP-004"
        );
        let receipt = cache
            .commit(
                &caller,
                "session",
                &context,
                &server("server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(1_100, 20),
            )
            .unwrap();
        assert_eq!(receipt.committed_at_utc_ms, 1_100);
        assert_eq!(
            cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"ok",
                    8,
                    clock(1_100, 20),
                )
                .unwrap(),
            receipt
        );
        assert_eq!(
            cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"different",
                    8,
                    clock(1_100, 20),
                )
                .unwrap_err()
                .code,
            "NCP-OP-001"
        );
        assert_eq!(
            cache
                .commit(
                    &caller,
                    "session",
                    &context,
                    &server("server"),
                    OperationOutcome::Succeeded,
                    b"ok",
                    8,
                    clock(1_100, 1_020),
                )
                .unwrap_err()
                .code,
            "NCP-OP-003"
        );
    }

    #[test]
    fn receipt_verification_rejects_nonterminal_or_unbounded_contents() {
        let cache = cache();
        let actor = server("server");
        let context = OperationContext {
            operation_id: OP.into(),
            request_digest: "a".repeat(64),
            ..Default::default()
        };
        let valid = ResponderReceipt {
            operation_id: OP.into(),
            request_digest: "a".repeat(64),
            result_digest: sha256_hex(b"result"),
            outcome: OperationOutcome::Succeeded,
            state_version: 8,
            committed_at_utc_ms: 1_100,
            responder_principal_id: actor.principal_id.clone(),
            responder_entity_id: actor.entity_id.clone(),
        };
        cache
            .verify_receipt(&valid, &actor, &context, b"result")
            .unwrap();

        let mut invalid = valid.clone();
        invalid.outcome = OperationOutcome::OutcomeUnknown;
        assert_eq!(
            cache
                .verify_receipt(&invalid, &actor, &context, b"result")
                .unwrap_err()
                .code,
            "NCP-AUTH-002"
        );
        invalid = valid.clone();
        invalid.committed_at_utc_ms = 0;
        assert_eq!(
            cache
                .verify_receipt(&invalid, &actor, &context, b"result")
                .unwrap_err()
                .code,
            "NCP-AUTH-002"
        );
        invalid = valid;
        invalid.state_version = JSON_SAFE_INTEGER_MAX as u64 + 1;
        assert_eq!(
            cache
                .verify_receipt(&invalid, &actor, &context, b"result")
                .unwrap_err()
                .code,
            "NCP-AUTH-002"
        );
    }

    #[test]
    fn receipt_verification_cross_binds_operation_and_result() {
        let cache = cache();
        let actor = server("server");
        let context = OperationContext {
            operation_id: OP.into(),
            request_digest: "a".repeat(64),
            ..Default::default()
        };
        let receipt = ResponderReceipt {
            operation_id: context.operation_id.clone(),
            request_digest: context.request_digest.clone(),
            result_digest: sha256_hex(b"result"),
            outcome: OperationOutcome::Succeeded,
            state_version: 8,
            committed_at_utc_ms: 1_100,
            responder_principal_id: actor.principal_id.clone(),
            responder_entity_id: actor.entity_id.clone(),
        };
        let mut other_context = context.clone();
        other_context.operation_id = "423e4567-e89b-42d3-a456-426614174010".into();

        assert_eq!(
            cache
                .verify_receipt(&receipt, &actor, &other_context, b"result")
                .unwrap_err()
                .code,
            "NCP-OP-001"
        );
        assert_eq!(
            cache
                .verify_receipt(&receipt, &actor, &context, b"different")
                .unwrap_err()
                .code,
            "NCP-OP-001"
        );
    }

    #[test]
    fn restart_pending_and_expired_or_evicted_retry_are_explicitly_unknown() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut operation_cache = cache();
        let (first_request, first) = request(false, 10.0, 62_000, &lease);
        operation_cache
            .begin(
                &caller,
                "session",
                &first,
                &first_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let snapshot = operation_cache.snapshot(10).unwrap();
        let mut restored = restore_cache(snapshot, 11).unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);
        assert_eq!(
            restored
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    7,
                    clock(1_100, 12),
                )
                .unwrap(),
            OperationDecision::OutcomeUnknown
        );
        assert_eq!(
            restored
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    7,
                    clock(1_099, 13),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        assert_eq!(
            restored
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    7,
                    clock(1_101, 11),
                )
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        let mut empty = cache();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);
        assert_eq!(
            empty
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    7,
                    clock(1_100, 12),
                )
                .unwrap(),
            OperationDecision::OutcomeUnknown
        );
    }

    #[test]
    fn restore_rejects_untrusted_configuration_and_malformed_or_duplicate_records() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut operation_cache = cache();
        let (initial_request, context) = request(false, 10.0, 62_000, &lease);
        operation_cache
            .begin(
                &caller,
                "session",
                &context,
                &initial_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let snapshot = operation_cache.snapshot(10).unwrap();

        assert_eq!(
            IdempotencyCache::restore(
                snapshot.clone(),
                ResponderBinding {
                    principal_id: "other-server".into(),
                    entity_id: "body".into(),
                },
                8,
                1_000,
                0,
            )
            .unwrap_err()
            .code,
            "NCP-AUTH-002"
        );
        assert_eq!(
            IdempotencyCache::restore(
                snapshot.clone(),
                ResponderBinding {
                    principal_id: "server".into(),
                    entity_id: "body".into(),
                },
                7,
                1_000,
                0,
            )
            .unwrap_err()
            .code,
            "NCP-OP-006"
        );

        let mut invalid_version = snapshot.clone();
        invalid_version.version += 1;
        assert_eq!(
            restore_cache(invalid_version, 0).unwrap_err().code,
            "NCP-OP-006"
        );
        let mut invalid_key = snapshot.clone();
        invalid_key.records[0].0.session_epoch = "not-an-epoch".into();
        assert_eq!(
            restore_cache(invalid_key, 0).unwrap_err().code,
            "NCP-OP-001"
        );
        let mut invalid_digest = snapshot.clone();
        invalid_digest.records[0].1.request_digest = "A".repeat(64);
        assert_eq!(
            restore_cache(invalid_digest, 0).unwrap_err().code,
            "NCP-OP-006"
        );
        let mut invalid_retention = snapshot.clone();
        invalid_retention.records[0].1.remaining_retention_ms = 0;
        assert_eq!(
            restore_cache(invalid_retention, 0).unwrap_err().code,
            "NCP-OP-006"
        );
        let mut duplicate = snapshot;
        duplicate.records.push(duplicate.records[0].clone());
        assert_eq!(restore_cache(duplicate, 0).unwrap_err().code, "NCP-OP-001");
    }

    #[test]
    fn restore_cross_binds_terminal_receipt_and_rebases_monotonic_retention() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 5_000);
        let mut operation_cache = cache();
        let (initial_request, context) = request(false, 10.0, 62_000, &lease);
        operation_cache
            .begin(
                &caller,
                "session",
                &context,
                &initial_request,
                &authority,
                7,
                clock(1_000, 5_000),
            )
            .unwrap();
        let receipt = operation_cache
            .commit(
                &caller,
                "session",
                &context,
                &server("server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(1_100, 5_000),
            )
            .unwrap();
        assert_eq!(
            operation_cache.snapshot(4_999).unwrap_err().code,
            "NCP-OP-006"
        );
        let snapshot = operation_cache.snapshot(5_500).unwrap();
        assert_eq!(snapshot.records[0].1.remaining_retention_ms, 500);

        let mut wrong_operation = snapshot.clone();
        let RecordState::Terminal(wrong_operation_receipt) =
            &mut wrong_operation.records[0].1.state
        else {
            panic!("committed record must be terminal");
        };
        wrong_operation_receipt.operation_id = "423e4567-e89b-42d3-a456-426614174010".into();
        assert_eq!(
            restore_cache(wrong_operation, 7).unwrap_err().code,
            "NCP-OP-001"
        );

        let mut impossible_version = snapshot.clone();
        let RecordState::Terminal(impossible_version_receipt) =
            &mut impossible_version.records[0].1.state
        else {
            panic!("committed record must be terminal");
        };
        impossible_version_receipt.state_version = 6;
        assert_eq!(
            restore_cache(impossible_version, 7).unwrap_err().code,
            "NCP-OP-001"
        );

        let mut pre_reservation_commit = snapshot.clone();
        let RecordState::Terminal(pre_reservation_receipt) =
            &mut pre_reservation_commit.records[0].1.state
        else {
            panic!("committed record must be terminal");
        };
        pre_reservation_receipt.committed_at_utc_ms = 999;
        assert_eq!(
            restore_cache(pre_reservation_commit, 7).unwrap_err().code,
            "NCP-OP-001"
        );

        assert_eq!(
            restore_cache(snapshot.clone(), u64::MAX - 100)
                .unwrap_err()
                .code,
            "NCP-OP-006"
        );
        let mut restored = restore_cache(snapshot, 7).unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &lease);
        assert_eq!(
            restored
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_200, 506),
                )
                .unwrap(),
            OperationDecision::Replay(receipt)
        );
        assert_eq!(
            restored
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(1_200, 507),
                )
                .unwrap(),
            OperationDecision::OutcomeUnknown
        );
        assert!(operation_cache.snapshot(6_000).unwrap().records.is_empty());
    }

    #[test]
    fn deadline_equality_and_state_conflict_fail_before_reservation() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();
        let (expired_request, expired_context) = request(false, 10.0, 2_000, &lease);
        let expired = cache
            .begin(
                &caller,
                "session",
                &expired_context,
                &expired_request,
                &authority,
                7,
                clock(2_000, 10),
            )
            .unwrap_err();
        assert_eq!(expired.code, "NCP-OP-002");
        let invalid_clock = cache
            .begin(
                &caller,
                "session",
                &expired_context,
                &expired_request,
                &authority,
                7,
                clock(0, 10),
            )
            .unwrap_err();
        assert_eq!(invalid_clock.code, "NCP-OP-002");
        let (request, context) = request(false, 10.0, 62_000, &lease);
        let conflict = cache
            .begin(
                &caller,
                "session",
                &context,
                &request,
                &authority,
                8,
                clock(1_000, 10),
            )
            .unwrap_err();
        assert_eq!(conflict.code, "NCP-OP-004");
    }

    #[test]
    fn request_session_must_match_cache_key_and_operation_generation() {
        let caller = caller("caller");
        let lease = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let authority = authority(&caller, lease.clone(), 1_000, 10);
        let mut cache = cache();

        let (mut wrong_id_request, mut wrong_id_context) = request(false, 10.0, 62_000, &lease);
        wrong_id_request["session_id"] = serde_json::json!("other-session");
        refresh_digest(&mut wrong_id_request, &mut wrong_id_context);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &wrong_id_context,
                    &wrong_id_request,
                    &authority,
                    7,
                    clock(1_000, 10),
                )
                .unwrap_err()
                .code,
            "NCP-AUTH-004"
        );

        let (mut wrong_generation_request, mut wrong_generation_context) =
            request(false, 10.0, 62_000, &lease);
        wrong_generation_request["session"]["generation"] =
            serde_json::json!("323e4567-e89b-42d3-a456-426614174000");
        refresh_digest(&mut wrong_generation_request, &mut wrong_generation_context);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &wrong_generation_context,
                    &wrong_generation_request,
                    &authority,
                    7,
                    clock(1_000, 10),
                )
                .unwrap_err()
                .code,
            "NCP-AUTH-004"
        );
        assert!(cache.records.is_empty());
    }

    #[test]
    fn renewed_lease_replays_but_stale_or_expired_authority_fails_before_lookup() {
        let caller = caller("caller");
        let initial = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let mut authority = authority(&caller, initial.clone(), 1_000, 10);
        let mut cache = cache();
        let (first_request, first) = request(false, 10.0, 63_000, &initial);
        cache
            .begin(
                &caller,
                "session",
                &first,
                &first_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        let receipt = cache
            .commit(
                &caller,
                "session",
                &first,
                &server("server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(1_100, 15),
            )
            .unwrap();

        let renewed = lease(
            &caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            2_000,
            62_000,
        );
        authority
            .renew(renewed.clone(), &caller, &caller, 2_000, 20)
            .unwrap();
        let (retry_request, retry) = request(true, 10.0, 63_000, &renewed);
        assert_eq!(first.request_digest, retry.request_digest);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(2_100, 21),
                )
                .unwrap(),
            OperationDecision::Replay(receipt)
        );

        let (stale_request, stale) = request(true, 10.0, 63_000, &initial);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &stale,
                    &stale_request,
                    &authority,
                    8,
                    clock(2_100, 21),
                )
                .unwrap_err()
                .code,
            "NCP-LEASE-001"
        );

        authority.tick(60_020);
        assert_eq!(
            cache
                .begin(
                    &caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(62_000, 60_020),
                )
                .unwrap_err()
                .code,
            "NCP-LEASE-002"
        );
    }

    #[test]
    fn authority_transfer_never_replays_another_principals_result() {
        let first_caller = caller("caller-one");
        let second_caller = caller("caller-two");
        let initial = lease(
            &first_caller,
            1,
            "223e4567-e89b-42d3-a456-426614174001",
            1_000,
            61_000,
        );
        let mut authority = authority(&first_caller, initial.clone(), 1_000, 10);
        let mut cache = cache();
        let (first_request, first) = request(false, 10.0, 62_000, &initial);
        cache
            .begin(
                &first_caller,
                "session",
                &first,
                &first_request,
                &authority,
                7,
                clock(1_000, 10),
            )
            .unwrap();
        cache
            .commit(
                &first_caller,
                "session",
                &first,
                &server("server"),
                OperationOutcome::Succeeded,
                b"ok",
                8,
                clock(1_100, 15),
            )
            .unwrap();

        let transferred = AuthorityLease {
            session_epoch: EPOCH.into(),
            term: 2,
            lease_id: "223e4567-e89b-42d3-a456-426614174002".into(),
            issuer_principal_id: first_caller.principal_id.clone(),
            holder_principal_id: second_caller.principal_id.clone(),
            holder_entity_id: second_caller.entity_id.clone(),
            issued_at_utc_ms: 2_000,
            expires_at_utc_ms: 62_000,
        };
        authority
            .acquire(
                transferred.clone(),
                &first_caller,
                &second_caller,
                2_000,
                20,
            )
            .unwrap();
        let (retry_request, retry) = request(true, 10.0, 62_000, &transferred);
        assert_eq!(first.request_digest, retry.request_digest);
        assert_eq!(
            cache
                .begin(
                    &second_caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(2_100, 21),
                )
                .unwrap(),
            OperationDecision::OutcomeUnknown
        );
        assert_eq!(
            cache
                .begin(
                    &first_caller,
                    "session",
                    &retry,
                    &retry_request,
                    &authority,
                    8,
                    clock(2_100, 21),
                )
                .unwrap_err()
                .code,
            "NCP-AUTH-002"
        );
    }
}
