//! Bounded, tamper-evident audit events for NCP security and safety decisions.
//!
//! The built-in chain detects mutation/deletion/reordering within a retained
//! segment. Production deployments anchor chain heads in an independent durable
//! system; this module does not claim that an in-process hash is a signature.

use std::collections::BTreeMap;
use std::fmt;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::authority::LifecycleState;
use crate::bounded_json::MAX_KEY_BYTES;
use crate::messages::{is_canonical_uuid_v4, JSON_SAFE_INTEGER_MAX};
use crate::security::{AuthenticatedActor, PrincipalRole};

const AUDIT_EVENT_SCHEMA: &str = "ncp.audit-event.v1";

/// Predecessor digest used for the first event in a newly anchored segment.
pub const AUDIT_GENESIS_DIGEST: &str =
    "0000000000000000000000000000000000000000000000000000000000000000";
/// Maximum number of bounded key/value attributes carried by one event.
pub const MAX_AUDIT_ATTRIBUTES: usize = 32;
/// Maximum UTF-8 byte length of an audit attribute key.
pub const MAX_AUDIT_ATTRIBUTE_KEY_BYTES: usize = 64;
/// Maximum UTF-8 byte length of an audit attribute value.
pub const MAX_AUDIT_ATTRIBUTE_BYTES: usize = 512;
/// Maximum UTF-8 byte length of an audit identifier.
pub const MAX_AUDIT_IDENTIFIER_BYTES: usize = MAX_KEY_BYTES;
/// Wire-1.0 session identifiers have a stricter bound than general identifiers.
pub const MAX_AUDIT_SESSION_ID_BYTES: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuditEventType {
    LifecycleTransition,
    AuthorityAcquired,
    AuthorityTransferred,
    AuthorityExpired,
    OperatorOverride,
    EstopLatched,
    EstopReset,
    CertificatePolicyChanged,
    PolicyDenied,
    GatewayUsed,
    IdempotencyReplay,
    QueueDrop,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuditActor {
    pub principal_id: String,
    pub entity_id: String,
    pub role: PrincipalRole,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuditEventDraft {
    pub event_id: String,
    pub event_type: AuditEventType,
    pub occurred_at_utc_ms: i64,
    pub trace_id: Option<String>,
    pub session_id: Option<String>,
    pub session_epoch: Option<String>,
    pub operation_id: Option<String>,
    pub authority_term: Option<u64>,
    pub state_before: Option<LifecycleState>,
    pub state_after: Option<LifecycleState>,
    pub claimed_principal_id: String,
    pub claimed_entity_id: String,
    pub policy_digest_sha256: String,
    #[serde(default)]
    pub attributes: BTreeMap<String, String>,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuditEvent {
    pub schema: String,
    pub sequence: u64,
    pub event_id: String,
    pub event_type: AuditEventType,
    pub occurred_at_utc_ms: i64,
    pub trace_id: Option<String>,
    pub session_id: Option<String>,
    pub session_epoch: Option<String>,
    pub operation_id: Option<String>,
    pub authority_term: Option<u64>,
    pub state_before: Option<LifecycleState>,
    pub state_after: Option<LifecycleState>,
    pub actor: AuditActor,
    pub policy_digest_sha256: String,
    pub attributes: BTreeMap<String, String>,
    pub previous_digest_sha256: String,
    pub event_digest_sha256: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuditError {
    pub code: &'static str,
    pub detail: String,
}

impl AuditError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for AuditError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for AuditError {}

#[derive(Clone, Debug)]
pub struct AuditChain {
    next_sequence: u64,
    previous_digest: String,
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest.iter().map(|byte| format!("{byte:02x}")).collect()
}

fn is_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .as_bytes()
            .iter()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}

fn valid_id(value: &str, max: usize) -> bool {
    value.len() <= max && crate::keys::valid_id_segment(value)
}

fn valid_optional_id(value: Option<&str>) -> bool {
    value.is_none_or(|value| valid_id(value, MAX_AUDIT_IDENTIFIER_BYTES))
}

fn valid_optional_uuid(value: Option<&str>) -> bool {
    value.is_none_or(is_canonical_uuid_v4)
}

fn valid_utc_timestamp(value: i64) -> bool {
    (0..=JSON_SAFE_INTEGER_MAX).contains(&value)
}

fn valid_positive_safe_integer(value: u64) -> bool {
    (1..=JSON_SAFE_INTEGER_MAX as u64).contains(&value)
}

fn valid_optional_lifecycle_state(value: Option<LifecycleState>) -> bool {
    !matches!(value, Some(LifecycleState::Unknown))
}

fn forbidden_attribute(key: &str) -> bool {
    let normalized = key.to_ascii_lowercase();
    [
        "private_key",
        "secret",
        "password",
        "token",
        "channel_payload",
        "raw_payload",
    ]
    .iter()
    .any(|forbidden| normalized.contains(forbidden))
}

fn valid_attributes(attributes: &BTreeMap<String, String>) -> bool {
    attributes.len() <= MAX_AUDIT_ATTRIBUTES
        && attributes.iter().all(|(key, value)| {
            valid_id(key, MAX_AUDIT_ATTRIBUTE_KEY_BYTES)
                && !forbidden_attribute(key)
                && value.len() <= MAX_AUDIT_ATTRIBUTE_BYTES
                && !value.chars().any(char::is_control)
        })
}

fn valid_authenticated_actor(actor: &AuthenticatedActor) -> bool {
    valid_id(&actor.principal_id, MAX_AUDIT_IDENTIFIER_BYTES)
        && valid_id(&actor.entity_id, MAX_AUDIT_IDENTIFIER_BYTES)
        && valid_id(&actor.certificate_identity, MAX_AUDIT_IDENTIFIER_BYTES)
        && actor.role != PrincipalRole::Unknown
}

impl AuditActor {
    fn is_valid(&self) -> bool {
        valid_id(&self.principal_id, MAX_AUDIT_IDENTIFIER_BYTES)
            && valid_id(&self.entity_id, MAX_AUDIT_IDENTIFIER_BYTES)
            && self.role != PrincipalRole::Unknown
    }
}

impl AuditEventDraft {
    fn validate(&self, authenticated_actor: &AuthenticatedActor) -> Result<(), AuditError> {
        if !valid_authenticated_actor(authenticated_actor)
            || !valid_id(&self.claimed_principal_id, MAX_AUDIT_IDENTIFIER_BYTES)
            || !valid_id(&self.claimed_entity_id, MAX_AUDIT_IDENTIFIER_BYTES)
        {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit actor identifiers or role are invalid",
            ));
        }
        if self.claimed_principal_id != authenticated_actor.principal_id
            || self.claimed_entity_id != authenticated_actor.entity_id
        {
            return Err(AuditError::new(
                "NCP-AUTH-002",
                "audit actor claim does not match authenticated transport identity",
            ));
        }
        if !is_canonical_uuid_v4(&self.event_id)
            || !valid_utc_timestamp(self.occurred_at_utc_ms)
            || !valid_optional_id(self.trace_id.as_deref())
            || self
                .session_id
                .as_deref()
                .is_some_and(|value| !valid_id(value, MAX_AUDIT_SESSION_ID_BYTES))
            || !valid_optional_uuid(self.session_epoch.as_deref())
            || !valid_optional_uuid(self.operation_id.as_deref())
            || self
                .authority_term
                .is_some_and(|term| !valid_positive_safe_integer(term))
            || !valid_optional_lifecycle_state(self.state_before)
            || !valid_optional_lifecycle_state(self.state_after)
            || !is_digest(&self.policy_digest_sha256)
            || !valid_attributes(&self.attributes)
        {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit event fields exceed semantic or resource bounds",
            ));
        }
        Ok(())
    }
}

impl AuditEvent {
    fn validate(&self) -> Result<(), AuditError> {
        if self.schema != AUDIT_EVENT_SCHEMA
            || !valid_positive_safe_integer(self.sequence)
            || !is_canonical_uuid_v4(&self.event_id)
            || !valid_utc_timestamp(self.occurred_at_utc_ms)
            || !valid_optional_id(self.trace_id.as_deref())
            || self
                .session_id
                .as_deref()
                .is_some_and(|value| !valid_id(value, MAX_AUDIT_SESSION_ID_BYTES))
            || !valid_optional_uuid(self.session_epoch.as_deref())
            || !valid_optional_uuid(self.operation_id.as_deref())
            || self
                .authority_term
                .is_some_and(|term| !valid_positive_safe_integer(term))
            || !valid_optional_lifecycle_state(self.state_before)
            || !valid_optional_lifecycle_state(self.state_after)
            || !self.actor.is_valid()
            || !is_digest(&self.policy_digest_sha256)
            || !valid_attributes(&self.attributes)
            || !is_digest(&self.previous_digest_sha256)
            || !is_digest(&self.event_digest_sha256)
        {
            return Err(AuditError::new(
                "NCP-AUDIT-002",
                "audit event contains invalid or unbounded persisted fields",
            ));
        }
        Ok(())
    }

    fn computed_digest(&self) -> Result<String, AuditError> {
        let mut value = serde_json::to_value(self).map_err(|error| {
            AuditError::new("NCP-AUDIT-001", format!("event encoding failed: {error}"))
        })?;
        let object = value.as_object_mut().ok_or_else(|| {
            AuditError::new(
                "NCP-AUDIT-001",
                "audit event did not encode as a JSON object",
            )
        })?;
        if object.remove("event_digest_sha256").is_none() {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit event digest field is absent from its projection",
            ));
        }
        let canonical = serde_json::to_vec(&value).map_err(|error| {
            AuditError::new(
                "NCP-AUDIT-001",
                format!("event canonicalization failed: {error}"),
            )
        })?;
        Ok(sha256_hex(&canonical))
    }
}

impl Default for AuditChain {
    fn default() -> Self {
        Self::new()
    }
}

impl AuditChain {
    pub fn new() -> Self {
        Self {
            next_sequence: 1,
            previous_digest: AUDIT_GENESIS_DIGEST.into(),
        }
    }

    pub fn resume(next_sequence: u64, previous_digest: String) -> Result<Self, AuditError> {
        if !valid_positive_safe_integer(next_sequence) || !is_digest(&previous_digest) {
            return Err(AuditError::new(
                "NCP-AUDIT-002",
                "audit resume anchor is invalid",
            ));
        }
        Ok(Self {
            next_sequence,
            previous_digest,
        })
    }

    pub fn append(
        &mut self,
        draft: AuditEventDraft,
        authenticated_actor: &AuthenticatedActor,
    ) -> Result<AuditEvent, AuditError> {
        if !valid_positive_safe_integer(self.next_sequence) || !is_digest(&self.previous_digest) {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit chain state is invalid or exhausted; start a newly anchored segment",
            ));
        }
        let following_sequence = self.next_sequence.checked_add(1).ok_or_else(|| {
            AuditError::new(
                "NCP-AUDIT-001",
                "audit sequence arithmetic overflowed; start a newly anchored segment",
            )
        })?;
        draft.validate(authenticated_actor)?;
        let mut event = AuditEvent {
            schema: AUDIT_EVENT_SCHEMA.into(),
            sequence: self.next_sequence,
            event_id: draft.event_id,
            event_type: draft.event_type,
            occurred_at_utc_ms: draft.occurred_at_utc_ms,
            trace_id: draft.trace_id,
            session_id: draft.session_id,
            session_epoch: draft.session_epoch,
            operation_id: draft.operation_id,
            authority_term: draft.authority_term,
            state_before: draft.state_before,
            state_after: draft.state_after,
            actor: AuditActor {
                principal_id: authenticated_actor.principal_id.clone(),
                entity_id: authenticated_actor.entity_id.clone(),
                role: authenticated_actor.role,
            },
            policy_digest_sha256: draft.policy_digest_sha256,
            attributes: draft.attributes,
            previous_digest_sha256: self.previous_digest.clone(),
            event_digest_sha256: String::new(),
        };
        event.event_digest_sha256 = event.computed_digest()?;
        self.previous_digest = event.event_digest_sha256.clone();
        self.next_sequence = following_sequence;
        Ok(event)
    }

    pub fn verify(events: &[AuditEvent], expected_anchor: &str) -> Result<(), AuditError> {
        if !is_digest(expected_anchor) {
            return Err(AuditError::new(
                "NCP-AUDIT-002",
                "audit verification anchor is invalid",
            ));
        }
        let mut previous = expected_anchor;
        let mut prior_sequence: Option<u64> = None;
        for event in events {
            event.validate()?;
            if event.previous_digest_sha256 != previous {
                return Err(AuditError::new(
                    "NCP-AUDIT-002",
                    "audit chain predecessor digest is broken",
                ));
            }
            if let Some(sequence) = prior_sequence {
                let expected_sequence = sequence.checked_add(1).ok_or_else(|| {
                    AuditError::new("NCP-AUDIT-002", "audit sequence arithmetic overflowed")
                })?;
                if event.sequence != expected_sequence {
                    return Err(AuditError::new(
                        "NCP-AUDIT-002",
                        "audit chain sequence is broken",
                    ));
                }
            }
            if event.event_digest_sha256 != event.computed_digest()? {
                return Err(AuditError::new(
                    "NCP-AUDIT-002",
                    "audit event digest does not match its canonical projection",
                ));
            }
            previous = &event.event_digest_sha256;
            prior_sequence = Some(event.sequence);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const EVENT1: &str = "123e4567-e89b-42d3-a456-426614174020";
    const EVENT2: &str = "123e4567-e89b-42d3-a456-426614174021";

    fn actor() -> AuthenticatedActor {
        AuthenticatedActor {
            principal_id: "operator".into(),
            certificate_identity: "urn:ncp:operator".into(),
            entity_id: "plant".into(),
            role: PrincipalRole::Operator,
            may_reset_estop: true,
            may_override: true,
        }
    }

    fn draft(id: &str, event_type: AuditEventType) -> AuditEventDraft {
        AuditEventDraft {
            event_id: id.into(),
            event_type,
            occurred_at_utc_ms: 1_000,
            trace_id: Some("trace-1".into()),
            session_id: Some("session-1".into()),
            session_epoch: None,
            operation_id: None,
            authority_term: Some(1),
            state_before: Some(LifecycleState::Estop),
            state_after: Some(LifecycleState::Hold),
            claimed_principal_id: "operator".into(),
            claimed_entity_id: "plant".into(),
            policy_digest_sha256: "a".repeat(64),
            attributes: BTreeMap::from([("reason".into(), "operator-inspection".into())]),
        }
    }

    fn appended_event() -> AuditEvent {
        AuditChain::new()
            .append(draft(EVENT1, AuditEventType::EstopReset), &actor())
            .unwrap()
    }

    fn rehash(event: &mut AuditEvent) {
        event.event_digest_sha256 = event.computed_digest().unwrap();
    }

    #[test]
    fn canonical_chain_detects_mutation_deletion_and_reordering() {
        let actor = actor();
        let mut chain = AuditChain::new();
        let first = chain
            .append(draft(EVENT1, AuditEventType::EstopReset), &actor)
            .unwrap();
        let second = chain
            .append(draft(EVENT2, AuditEventType::OperatorOverride), &actor)
            .unwrap();
        AuditChain::verify(&[first.clone(), second.clone()], AUDIT_GENESIS_DIGEST).unwrap();

        let mut mutated = second.clone();
        mutated.attributes.insert("reason".into(), "changed".into());
        assert!(AuditChain::verify(&[first.clone(), mutated], AUDIT_GENESIS_DIGEST).is_err());
        assert!(AuditChain::verify(std::slice::from_ref(&second), AUDIT_GENESIS_DIGEST).is_err());
        assert!(AuditChain::verify(&[second, first], AUDIT_GENESIS_DIGEST).is_err());
    }

    #[test]
    fn actor_mismatch_and_sensitive_or_unbounded_attributes_are_rejected() {
        let actor = actor();
        let mut chain = AuditChain::new();
        let mut wrong = draft(EVENT1, AuditEventType::EstopReset);
        wrong.claimed_principal_id = "attacker".into();
        assert_eq!(
            chain.append(wrong, &actor).unwrap_err().code,
            "NCP-AUTH-002"
        );

        let mut secret = draft(EVENT1, AuditEventType::EstopReset);
        secret
            .attributes
            .insert("private_key".into(), "never-log".into());
        assert_eq!(
            chain.append(secret, &actor).unwrap_err().code,
            "NCP-AUDIT-001"
        );
    }

    #[test]
    fn append_accepts_both_nonnegative_json_safe_timestamp_boundaries() {
        let actor = actor();
        let mut chain = AuditChain::new();
        let mut first = draft(EVENT1, AuditEventType::EstopReset);
        first.occurred_at_utc_ms = 0;
        let first = chain.append(first, &actor).unwrap();
        let mut second = draft(EVENT2, AuditEventType::OperatorOverride);
        second.occurred_at_utc_ms = JSON_SAFE_INTEGER_MAX;
        let second = chain.append(second, &actor).unwrap();

        assert_eq!(
            (first.occurred_at_utc_ms, second.occurred_at_utc_ms),
            (0, JSON_SAFE_INTEGER_MAX)
        );
    }

    #[test]
    fn append_rejects_timestamp_above_json_safe_boundary() {
        let mut event = draft(EVENT1, AuditEventType::EstopReset);
        event.occurred_at_utc_ms = JSON_SAFE_INTEGER_MAX + 1;
        let error = AuditChain::new()
            .append(event, &actor())
            .expect_err("unsafe UTC milliseconds must not enter the chain");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_rejects_negative_timestamp() {
        let mut event = draft(EVENT1, AuditEventType::EstopReset);
        event.occurred_at_utc_ms = -1;
        let error = AuditChain::new()
            .append(event, &actor())
            .expect_err("negative UTC milliseconds must not enter the chain");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn draft_deserialization_rejects_non_finite_timestamp_spelling() {
        let json = serde_json::to_string(&draft(EVENT1, AuditEventType::EstopReset))
            .unwrap()
            .replace(
                "\"occurred_at_utc_ms\":1000",
                "\"occurred_at_utc_ms\":1e400",
            );

        assert!(serde_json::from_str::<AuditEventDraft>(&json).is_err());
    }

    #[test]
    fn append_rejects_unbounded_authenticated_actor_identifier() {
        let mut authenticated = actor();
        authenticated.principal_id = "p".repeat(MAX_AUDIT_IDENTIFIER_BYTES + 1);
        let mut event = draft(EVENT1, AuditEventType::EstopReset);
        event.claimed_principal_id = authenticated.principal_id.clone();
        let error = AuditChain::new()
            .append(event, &authenticated)
            .expect_err("matching but unbounded actor claims must fail closed");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_rejects_unbounded_certificate_identifier() {
        let mut authenticated = actor();
        authenticated.certificate_identity = "c".repeat(MAX_AUDIT_IDENTIFIER_BYTES + 1);
        let error = AuditChain::new()
            .append(draft(EVENT1, AuditEventType::EstopReset), &authenticated)
            .expect_err("the verified certificate identifier must be bounded");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_rejects_unknown_authenticated_actor_role() {
        let mut authenticated = actor();
        authenticated.role = PrincipalRole::Unknown;
        let error = AuditChain::new()
            .append(draft(EVENT1, AuditEventType::EstopReset), &authenticated)
            .expect_err("an unknown role cannot produce an authoritative audit actor");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_rejects_unbounded_optional_identifier() {
        let mut event = draft(EVENT1, AuditEventType::EstopReset);
        event.trace_id = Some("t".repeat(MAX_AUDIT_IDENTIFIER_BYTES + 1));
        let error = AuditChain::new()
            .append(event, &actor())
            .expect_err("trace identifiers must obey the protocol key bound");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_rejects_session_id_above_wire_limit() {
        let mut event = draft(EVENT1, AuditEventType::EstopReset);
        event.session_id = Some("s".repeat(MAX_AUDIT_SESSION_ID_BYTES + 1));
        let error = AuditChain::new()
            .append(event, &actor())
            .expect_err("audit correlation must preserve the wire session-id bound");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_rejects_unknown_lifecycle_state_when_present() {
        let mut event = draft(EVENT1, AuditEventType::EstopReset);
        event.state_before = Some(LifecycleState::Unknown);
        let error = AuditChain::new()
            .append(event, &actor())
            .expect_err("unknown lifecycle values must remain fail closed");

        assert_eq!(error.code, "NCP-AUDIT-001");
    }

    #[test]
    fn append_accepts_last_safe_sequence_then_remains_exhausted() {
        let mut chain = AuditChain::resume(
            JSON_SAFE_INTEGER_MAX as u64,
            AUDIT_GENESIS_DIGEST.to_string(),
        )
        .unwrap();
        let last = chain
            .append(draft(EVENT1, AuditEventType::EstopReset), &actor())
            .unwrap();
        let error = chain
            .append(draft(EVENT2, AuditEventType::OperatorOverride), &actor())
            .expect_err("the sequence must not wrap or append beyond the safe boundary");

        assert_eq!(
            (last.sequence, error.code),
            (JSON_SAFE_INTEGER_MAX as u64, "NCP-AUDIT-001")
        );
    }

    #[test]
    fn verify_rejects_rehashed_unsafe_timestamp() {
        let mut event = appended_event();
        event.occurred_at_utc_ms = JSON_SAFE_INTEGER_MAX + 1;
        rehash(&mut event);

        assert!(AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST).is_err());
    }

    #[test]
    fn verify_rejects_rehashed_unbounded_actor() {
        let mut event = appended_event();
        event.actor.entity_id = "e".repeat(MAX_AUDIT_IDENTIFIER_BYTES + 1);
        rehash(&mut event);

        assert!(AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST).is_err());
    }

    #[test]
    fn verify_rejects_rehashed_invalid_policy_digest() {
        let mut event = appended_event();
        event.policy_digest_sha256 = "A".repeat(64);
        rehash(&mut event);

        assert!(AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST).is_err());
    }

    #[test]
    fn verify_rejects_rehashed_unsafe_authority_term() {
        let mut event = appended_event();
        event.authority_term = Some(JSON_SAFE_INTEGER_MAX as u64 + 1);
        rehash(&mut event);

        assert!(AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST).is_err());
    }

    #[test]
    fn verify_rejects_rehashed_oversized_attribute() {
        let mut event = appended_event();
        event
            .attributes
            .insert("reason".into(), "x".repeat(MAX_AUDIT_ATTRIBUTE_BYTES + 1));
        rehash(&mut event);

        assert!(AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST).is_err());
    }

    #[test]
    fn verify_rejects_u64_sequence_without_panicking_or_wrapping() {
        let mut event = appended_event();
        event.sequence = u64::MAX;
        rehash(&mut event);

        let result =
            std::panic::catch_unwind(|| AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST));

        assert!(result.is_ok_and(|verification| verification.is_err()));
    }

    #[test]
    fn semantically_valid_local_rehash_is_not_misrepresented_as_a_signature() {
        let mut event = appended_event();
        event
            .attributes
            .insert("reason".into(), "locally-rewritten".into());
        rehash(&mut event);

        assert!(AuditChain::verify(&[event], AUDIT_GENESIS_DIGEST).is_ok());
    }

    #[test]
    fn audit_struct_deserialization_rejects_unknown_fields() {
        let mut value = serde_json::to_value(draft(EVENT1, AuditEventType::EstopReset)).unwrap();
        value
            .as_object_mut()
            .unwrap()
            .insert("future_extension".into(), serde_json::Value::Bool(true));

        assert!(serde_json::from_value::<AuditEventDraft>(value).is_err());
    }
}
