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
use std::collections::{BTreeMap, VecDeque};
use std::fmt;

pub const MAX_OPERATION_CACHE_ENTRIES: usize = 65_536;
pub const MAX_OPERATION_RETENTION_MS: u64 = 86_400_000;

/// Receiver-local clock sample used for one idempotency decision.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct OperationClock {
    pub utc_ms: i64,
    pub monotonic_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
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

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
struct OperationRecord {
    request_digest: String,
    state: RecordState,
    expires_at_monotonic_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct IdempotencySnapshot {
    responder: ResponderBinding,
    max_entries: usize,
    retention_ms: u64,
    records: Vec<(OperationKey, OperationRecord)>,
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
    !value.is_empty()
        && value.len() <= max
        && !value.chars().any(|character| {
            character.is_control()
                || character.is_whitespace()
                || matches!(character, '/' | '*' | '$' | '#' | '?')
        })
}

impl OperationContext {
    pub fn validate(
        &self,
        request: &serde_json::Value,
        now_utc_ms: i64,
    ) -> Result<(), OperationError> {
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
        if self.deadline_utc_ms <= now_utc_ms {
            return Err(OperationError::new(
                "NCP-OP-002",
                "operation deadline is expired (equality is expired)",
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
        Ok(OperationKey {
            principal_id: caller.principal_id.clone(),
            session_id: session_id.into(),
            session_epoch: context.session_epoch.clone(),
            operation_id: context.operation_id.clone(),
        })
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
        self.records
            .retain(|_, record| record.expires_at_monotonic_ms > now_monotonic_ms);
        self.insertion_order
            .retain(|key| self.records.contains_key(key));
    }

    fn make_room(&mut self) -> Result<(), OperationError> {
        while self.records.len() >= self.max_entries {
            let Some(candidate) = self.insertion_order.pop_front() else {
                break;
            };
            if self
                .records
                .get(&candidate)
                .is_some_and(|record| !matches!(record.state, RecordState::Pending))
            {
                self.records.remove(&candidate);
                break;
            }
            self.insertion_order.push_back(candidate);
            if self.insertion_order.iter().all(|key| {
                self.records
                    .get(key)
                    .is_some_and(|record| matches!(record.state, RecordState::Pending))
            }) {
                break;
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
        Self::verify_authority(request, context, caller, authority, clock.monotonic_ms)?;
        let key = Self::key(caller, session_id, context)?;
        self.purge_expired(clock.monotonic_ms);
        if let Some(record) = self.records.get(&key) {
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
        let expires_at_monotonic_ms = clock
            .monotonic_ms
            .checked_add(self.retention_ms)
            .ok_or_else(|| OperationError::new("NCP-OP-006", "retention deadline overflow"))?;
        self.records.insert(
            key.clone(),
            OperationRecord {
                request_digest: context.request_digest.clone(),
                state: RecordState::Pending,
                expires_at_monotonic_ms,
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
        committed_at_utc_ms: i64,
    ) -> Result<ResponderReceipt, OperationError> {
        self.responder.verify_actor(actor)?;
        if state_version > JSON_SAFE_INTEGER_MAX as u64
            || matches!(
                outcome,
                OperationOutcome::Unknown | OperationOutcome::OutcomeUnknown
            )
        {
            return Err(OperationError::new(
                "NCP-OP-004",
                "terminal commit outcome/state version is invalid",
            ));
        }
        let key = Self::key(caller, session_id, context)?;
        let record = self.records.get_mut(&key).ok_or_else(|| {
            OperationError::new("NCP-OP-003", "operation reservation is unavailable")
        })?;
        if record.request_digest != context.request_digest {
            return Err(OperationError::new(
                "NCP-OP-001",
                "commit digest conflicts with the reserved operation",
            ));
        }
        if let RecordState::Terminal(receipt) = &record.state {
            return Ok(receipt.clone());
        }
        if matches!(record.state, RecordState::Unavailable) {
            return Err(OperationError::new(
                "NCP-OP-003",
                "operation completion is unavailable",
            ));
        }
        let receipt = ResponderReceipt {
            operation_id: context.operation_id.clone(),
            request_digest: context.request_digest.clone(),
            result_digest: sha256_hex(result_bytes),
            outcome,
            state_version,
            committed_at_utc_ms,
            responder_principal_id: actor.principal_id.clone(),
            responder_entity_id: actor.entity_id.clone(),
        };
        record.state = RecordState::Terminal(receipt.clone());
        Ok(receipt)
    }

    pub fn snapshot(&self) -> IdempotencySnapshot {
        IdempotencySnapshot {
            responder: self.responder.clone(),
            max_entries: self.max_entries,
            retention_ms: self.retention_ms,
            records: self
                .records
                .iter()
                .map(|(key, record)| (key.clone(), record.clone()))
                .collect(),
        }
    }

    pub fn restore(
        snapshot: IdempotencySnapshot,
        now_monotonic_ms: u64,
    ) -> Result<Self, OperationError> {
        let mut cache = Self::new(
            snapshot.responder,
            snapshot.max_entries,
            snapshot.retention_ms,
        )?;
        if snapshot.records.len() > cache.max_entries {
            return Err(OperationError::new(
                "NCP-OP-006",
                "snapshot exceeds the configured cache capacity",
            ));
        }
        for (key, mut record) in snapshot.records {
            if record.expires_at_monotonic_ms <= now_monotonic_ms {
                continue;
            }
            if matches!(record.state, RecordState::Pending) {
                record.state = RecordState::Unavailable;
            }
            cache.insertion_order.push_back(key.clone());
            cache.records.insert(key, record);
        }
        Ok(cache)
    }

    pub fn verify_receipt(
        &self,
        receipt: &ResponderReceipt,
        actor: &AuthenticatedActor,
    ) -> Result<(), OperationError> {
        self.responder.verify_actor(actor)?;
        if receipt.responder_principal_id != self.responder.principal_id
            || receipt.responder_entity_id != self.responder.entity_id
            || !valid_digest(&receipt.request_digest)
            || !valid_digest(&receipt.result_digest)
        {
            return Err(OperationError::new(
                "NCP-AUTH-002",
                "responder receipt identity or digest is invalid",
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
                1_100,
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
                    clock(1_200, 20),
                )
                .unwrap(),
            OperationDecision::Replay(receipt)
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
                1_100,
            )
            .unwrap_err();
        assert_eq!(error.code, "NCP-AUTH-002");
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
        let snapshot = operation_cache.snapshot();
        let mut restored = IdempotencyCache::restore(snapshot, 11).unwrap();
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
                1_100,
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
                1_100,
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
