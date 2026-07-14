//! Bounded, tamper-evident audit events for NCP security and safety decisions.
//!
//! The built-in chain detects mutation/deletion/reordering within a retained
//! segment. Production deployments anchor chain heads in an independent durable
//! system; this module does not claim that an in-process hash is a signature.

use crate::authority::LifecycleState;
use crate::messages::{is_canonical_uuid_v4, JSON_SAFE_INTEGER_MAX};
use crate::security::{AuthenticatedActor, PrincipalRole};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::fmt;

pub const AUDIT_GENESIS_DIGEST: &str =
    "0000000000000000000000000000000000000000000000000000000000000000";
pub const MAX_AUDIT_ATTRIBUTES: usize = 32;
pub const MAX_AUDIT_ATTRIBUTE_BYTES: usize = 512;

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
pub struct AuditActor {
    pub principal_id: String,
    pub entity_id: String,
    pub role: PrincipalRole,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
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
    !value.is_empty()
        && value.len() <= max
        && !value.chars().any(|character| {
            character.is_control()
                || character.is_whitespace()
                || matches!(character, '/' | '*' | '$' | '#' | '?')
        })
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

impl AuditEvent {
    fn computed_digest(&self) -> Result<String, AuditError> {
        let mut value = serde_json::to_value(self).map_err(|error| {
            AuditError::new("NCP-AUDIT-001", format!("event encoding failed: {error}"))
        })?;
        value
            .as_object_mut()
            .expect("AuditEvent serializes as an object")
            .remove("event_digest_sha256");
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
        if next_sequence == 0
            || next_sequence > JSON_SAFE_INTEGER_MAX as u64
            || !is_digest(&previous_digest)
        {
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
        if self.next_sequence > JSON_SAFE_INTEGER_MAX as u64 {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit sequence is exhausted; start a newly anchored segment",
            ));
        }
        if !is_canonical_uuid_v4(&draft.event_id)
            || draft
                .session_epoch
                .as_deref()
                .is_some_and(|value| !is_canonical_uuid_v4(value))
            || draft
                .operation_id
                .as_deref()
                .is_some_and(|value| !is_canonical_uuid_v4(value))
            || draft
                .authority_term
                .is_some_and(|term| term == 0 || term > JSON_SAFE_INTEGER_MAX as u64)
            || !is_digest(&draft.policy_digest_sha256)
        {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit identifiers, authority term, or policy digest are invalid",
            ));
        }
        if draft.claimed_principal_id != authenticated_actor.principal_id
            || draft.claimed_entity_id != authenticated_actor.entity_id
        {
            return Err(AuditError::new(
                "NCP-AUTH-002",
                "audit actor claim does not match authenticated transport identity",
            ));
        }
        for value in [draft.trace_id.as_deref(), draft.session_id.as_deref()]
            .into_iter()
            .flatten()
        {
            if !valid_id(value, 128) {
                return Err(AuditError::new(
                    "NCP-AUDIT-001",
                    "audit trace/session identifier is invalid",
                ));
            }
        }
        if draft.attributes.len() > MAX_AUDIT_ATTRIBUTES
            || draft.attributes.iter().any(|(key, value)| {
                !valid_id(key, 64)
                    || forbidden_attribute(key)
                    || value.len() > MAX_AUDIT_ATTRIBUTE_BYTES
                    || value.chars().any(char::is_control)
            })
        {
            return Err(AuditError::new(
                "NCP-AUDIT-001",
                "audit attributes are unbounded, sensitive, or invalid",
            ));
        }
        let mut event = AuditEvent {
            schema: "ncp.audit-event.v1".into(),
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
        self.next_sequence += 1;
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
        let mut prior_sequence = None;
        for event in events {
            if event.schema != "ncp.audit-event.v1"
                || event.previous_digest_sha256 != previous
                || prior_sequence.is_some_and(|sequence| event.sequence != sequence + 1)
                || event.event_digest_sha256 != event.computed_digest()?
            {
                return Err(AuditError::new(
                    "NCP-AUDIT-002",
                    "audit chain digest or sequence is broken",
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
}
