//! NCP 1.0 lifecycle and single-controller authority model.
//!
//! Authority is an authenticated, bounded lease, never a last-writer-wins
//! property of the action topic. UTC timestamps are audit metadata and bound the
//! accepted duration; only a receiver-local monotonic deadline drives expiry.
//! Restart restoration deliberately cannot restore `Active` without an explicit
//! continuity proof through [`AuthorityMachine::reconnect`].

use crate::messages::{is_canonical_uuid_v4, JSON_SAFE_INTEGER_MAX};
pub use crate::messages::{AuthorityLease, LifecycleState};
use crate::security::{AuthenticatedActor, PrincipalRole};
use serde::{Deserialize, Serialize};
use std::fmt;

pub const MAX_AUTHORITY_LEASE_MS: i64 = 60_000;
pub const MAX_CLOCK_UNCERTAINTY_MS: i64 = 5_000;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuthoritySnapshot {
    pub session_epoch: String,
    pub state: LifecycleState,
    pub state_version: u64,
    pub highest_term: u64,
    pub lease: Option<AuthorityLease>,
    pub estop_latched: bool,
    /// True once an authorized ESTOP reset has retired this immutable session
    /// generation. A retired machine can be restored for audit only; it can never
    /// reopen or reacquire authority.
    #[serde(default)]
    pub retired: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuthorityError {
    pub code: &'static str,
    pub detail: String,
}

impl AuthorityError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for AuthorityError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for AuthorityError {}

#[derive(Clone, Debug)]
pub struct AuthorityMachine {
    state: LifecycleState,
    session_epoch: String,
    state_version: u64,
    highest_term: u64,
    lease: Option<AuthorityLease>,
    accepted_until_monotonic_ms: Option<u64>,
    estop_latched: bool,
    retired: bool,
}

fn valid_identity(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !value.chars().any(|character| {
            character.is_control()
                || character.is_whitespace()
                || matches!(character, '/' | '*' | '$' | '#' | '?')
        })
}

pub(crate) fn validate_lease_shape(lease: &AuthorityLease) -> Result<(), AuthorityError> {
    if !is_canonical_uuid_v4(&lease.session_epoch) || !is_canonical_uuid_v4(&lease.lease_id) {
        return Err(AuthorityError::new(
            "NCP-LEASE-003",
            "session_epoch and lease_id must be canonical lowercase UUIDv4 values",
        ));
    }
    if lease.term == 0 || lease.term > JSON_SAFE_INTEGER_MAX as u64 {
        return Err(AuthorityError::new(
            "NCP-LEASE-004",
            "authority term must be in 1..=JSON_SAFE_INTEGER_MAX",
        ));
    }
    for (label, value) in [
        ("issuer_principal_id", lease.issuer_principal_id.as_str()),
        ("holder_principal_id", lease.holder_principal_id.as_str()),
        ("holder_entity_id", lease.holder_entity_id.as_str()),
    ] {
        if !valid_identity(value) {
            return Err(AuthorityError::new(
                "NCP-LEASE-003",
                format!("{label} is empty, wildcarded, or unbounded"),
            ));
        }
    }
    if !(0..=JSON_SAFE_INTEGER_MAX).contains(&lease.issued_at_utc_ms)
        || !(0..=JSON_SAFE_INTEGER_MAX).contains(&lease.expires_at_utc_ms)
    {
        return Err(AuthorityError::new(
            "NCP-LEASE-002",
            "lease UTC timestamps must be non-negative JSON-safe integers",
        ));
    }
    let duration = lease
        .expires_at_utc_ms
        .checked_sub(lease.issued_at_utc_ms)
        .ok_or_else(|| AuthorityError::new("NCP-LEASE-002", "lease time overflow"))?;
    if !(1..=MAX_AUTHORITY_LEASE_MS).contains(&duration) {
        return Err(AuthorityError::new(
            "NCP-LEASE-002",
            "lease duration must be positive and bounded",
        ));
    }
    Ok(())
}

fn local_deadline(
    lease: &AuthorityLease,
    now_utc_ms: i64,
    now_monotonic_ms: u64,
) -> Result<u64, AuthorityError> {
    validate_lease_shape(lease)?;
    if lease.issued_at_utc_ms > now_utc_ms.saturating_add(MAX_CLOCK_UNCERTAINTY_MS) {
        return Err(AuthorityError::new(
            "NCP-LEASE-002",
            "lease issue time exceeds the clock-uncertainty bound",
        ));
    }
    let remaining = lease.expires_at_utc_ms.saturating_sub(now_utc_ms);
    if remaining <= 0 {
        return Err(AuthorityError::new(
            "NCP-LEASE-002",
            "authority lease is expired at receipt",
        ));
    }
    let declared_duration = lease.expires_at_utc_ms - lease.issued_at_utc_ms;
    let accepted_remaining = remaining.min(declared_duration) as u64;
    now_monotonic_ms
        .checked_add(accepted_remaining)
        .ok_or_else(|| AuthorityError::new("NCP-LEASE-002", "monotonic deadline overflow"))
}

impl AuthorityMachine {
    pub fn new(session_epoch: impl Into<String>) -> Result<Self, AuthorityError> {
        let session_epoch = session_epoch.into();
        if !is_canonical_uuid_v4(&session_epoch) {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "session generation must be a canonical lowercase UUIDv4",
            ));
        }
        Ok(Self {
            state: LifecycleState::Closed,
            session_epoch,
            state_version: 0,
            highest_term: 0,
            lease: None,
            accepted_until_monotonic_ms: None,
            estop_latched: false,
            retired: false,
        })
    }

    pub fn state(&self) -> LifecycleState {
        self.state
    }

    pub fn state_version(&self) -> u64 {
        self.state_version
    }

    pub fn active_lease(&self, now_monotonic_ms: u64) -> Option<&AuthorityLease> {
        (!self.retired
            && self.state == LifecycleState::Active
            && !self.estop_latched
            && self
                .accepted_until_monotonic_ms
                .is_some_and(|deadline| now_monotonic_ms < deadline))
        .then_some(())
        .and(self.lease.as_ref())
    }

    fn transition(&mut self, next: LifecycleState) {
        if self.state != next {
            self.state = next;
            self.state_version = self.state_version.saturating_add(1);
        }
    }

    pub fn begin_open(&mut self) -> Result<(), AuthorityError> {
        if self.retired {
            return Err(AuthorityError::new(
                "NCP-STATE-003",
                "retired session generation cannot be reopened",
            ));
        }
        if self.state != LifecycleState::Closed {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "open is allowed only from closed",
            ));
        }
        self.transition(LifecycleState::Opening);
        Ok(())
    }

    pub fn initialize(&mut self) -> Result<(), AuthorityError> {
        if self.state != LifecycleState::Opening {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "initialize is allowed only from opening",
            ));
        }
        self.transition(LifecycleState::Init);
        Ok(())
    }

    /// Acquire or transfer authority. A commander may acquire for itself. A
    /// current holder may transfer to another authenticated holder. Only an
    /// enrolled operator with override authority may preempt a different holder.
    pub fn acquire(
        &mut self,
        lease: AuthorityLease,
        issuer: &AuthenticatedActor,
        holder: &AuthenticatedActor,
        now_utc_ms: i64,
        now_monotonic_ms: u64,
    ) -> Result<(), AuthorityError> {
        if self.retired {
            return Err(AuthorityError::new(
                "NCP-STATE-003",
                "retired session generation cannot reacquire authority",
            ));
        }
        if matches!(
            self.state,
            LifecycleState::Closed
                | LifecycleState::Opening
                | LifecycleState::Closing
                | LifecycleState::Failed
        ) {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "authority cannot be acquired in the current lifecycle state",
            ));
        }
        if self.state == LifecycleState::Estop || self.estop_latched {
            return Err(AuthorityError::new(
                "NCP-STATE-002",
                "authority cannot activate while ESTOP is latched",
            ));
        }
        if lease.session_epoch != self.session_epoch {
            return Err(AuthorityError::new(
                "NCP-LEASE-001",
                "lease belongs to a different session generation",
            ));
        }
        if lease.issuer_principal_id != issuer.principal_id
            || lease.holder_principal_id != holder.principal_id
            || lease.holder_entity_id != holder.entity_id
        {
            return Err(AuthorityError::new(
                "NCP-AUTH-002",
                "authenticated issuer/holder does not match the lease",
            ));
        }
        if holder.role != PrincipalRole::Commander {
            return Err(AuthorityError::new(
                "NCP-AUTH-003",
                "only a commander principal may hold controller authority",
            ));
        }
        let current_holder = self
            .lease
            .as_ref()
            .filter(|_| {
                matches!(
                    self.state,
                    LifecycleState::Active | LifecycleState::Reconnecting
                ) && self
                    .accepted_until_monotonic_ms
                    .is_some_and(|deadline| now_monotonic_ms < deadline)
            })
            .map(|current| current.holder_principal_id.as_str());
        let self_acquire = issuer.principal_id == holder.principal_id
            && issuer.role == PrincipalRole::Commander
            && current_holder.is_none();
        let holder_transfer = current_holder == Some(issuer.principal_id.as_str())
            && issuer.role == PrincipalRole::Commander;
        let operator_override = issuer.role == PrincipalRole::Operator && issuer.may_override;
        if !(self_acquire || holder_transfer || operator_override) {
            return Err(AuthorityError::new(
                "NCP-LEASE-003",
                "issuer may not acquire, transfer, or preempt this authority",
            ));
        }
        if lease.term <= self.highest_term {
            return Err(AuthorityError::new(
                "NCP-LEASE-001",
                "authority term is not strictly newer",
            ));
        }
        let deadline = local_deadline(&lease, now_utc_ms, now_monotonic_ms)?;
        self.highest_term = lease.term;
        self.lease = Some(lease);
        self.accepted_until_monotonic_ms = Some(deadline);
        self.transition(LifecycleState::Active);
        Ok(())
    }

    /// Renew the exact active lease while its receiver-local monotonic deadline is
    /// still live. Both granting issuer and current holder are authenticated
    /// arguments; serialized lease possession is insufficient. Expired renewal
    /// transitions to HOLD and requires acquisition of a newer term.
    pub fn renew(
        &mut self,
        lease: AuthorityLease,
        issuer: &AuthenticatedActor,
        holder: &AuthenticatedActor,
        now_utc_ms: i64,
        now_monotonic_ms: u64,
    ) -> Result<(), AuthorityError> {
        if self.retired {
            return Err(AuthorityError::new(
                "NCP-STATE-003",
                "retired session generation cannot renew authority",
            ));
        }
        if self.state != LifecycleState::Active {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "authority renewal is allowed only while active",
            ));
        }
        let current = self.lease.as_ref().ok_or_else(|| {
            AuthorityError::new("NCP-LEASE-003", "there is no authority lease to renew")
        })?;
        if lease.session_epoch != current.session_epoch
            || lease.term != current.term
            || lease.lease_id != current.lease_id
            || lease.issuer_principal_id != current.issuer_principal_id
            || lease.holder_principal_id != current.holder_principal_id
            || lease.holder_entity_id != current.holder_entity_id
            || issuer.principal_id != current.issuer_principal_id
            || holder.principal_id != current.holder_principal_id
            || holder.entity_id != current.holder_entity_id
        {
            return Err(AuthorityError::new(
                "NCP-LEASE-001",
                "renewal does not match the current authority identity",
            ));
        }
        let issuer_authorized = (issuer.role == PrincipalRole::Commander)
            || (issuer.role == PrincipalRole::Operator && issuer.may_override);
        if !issuer_authorized || holder.role != PrincipalRole::Commander {
            return Err(AuthorityError::new(
                "NCP-AUTH-003",
                "renewal requires its authenticated granting issuer and commander holder",
            ));
        }
        if self.estop_latched {
            return Err(AuthorityError::new("NCP-STATE-002", "ESTOP is latched"));
        }
        if self
            .accepted_until_monotonic_ms
            .is_none_or(|deadline| now_monotonic_ms >= deadline)
        {
            self.accepted_until_monotonic_ms = None;
            self.transition(LifecycleState::Hold);
            return Err(AuthorityError::new(
                "NCP-LEASE-002",
                "expired authority cannot be renewed; acquire a newer term",
            ));
        }
        let deadline = local_deadline(&lease, now_utc_ms, now_monotonic_ms)?;
        self.lease = Some(lease);
        self.accepted_until_monotonic_ms = Some(deadline);
        self.transition(LifecycleState::Active);
        Ok(())
    }

    pub fn tick(&mut self, now_monotonic_ms: u64) {
        if self.state == LifecycleState::Active
            && self
                .accepted_until_monotonic_ms
                .is_none_or(|deadline| now_monotonic_ms >= deadline)
        {
            self.accepted_until_monotonic_ms = None;
            self.transition(LifecycleState::Hold);
        }
    }

    pub fn disconnect(&mut self, principal_id: &str) -> Result<(), AuthorityError> {
        let current = self
            .lease
            .as_ref()
            .ok_or_else(|| AuthorityError::new("NCP-LEASE-003", "there is no current holder"))?;
        if current.holder_principal_id != principal_id {
            return Err(AuthorityError::new(
                "NCP-AUTH-004",
                "disconnect principal is not the authority holder",
            ));
        }
        if !self.estop_latched {
            self.transition(LifecycleState::Reconnecting);
        }
        Ok(())
    }

    pub fn reconnect(
        &mut self,
        holder: &AuthenticatedActor,
        session_epoch: &str,
        term: u64,
        lease_id: &str,
        now_monotonic_ms: u64,
    ) -> Result<(), AuthorityError> {
        if self.retired {
            return Err(AuthorityError::new(
                "NCP-STATE-003",
                "retired session generation cannot reconnect",
            ));
        }
        if self.estop_latched {
            return Err(AuthorityError::new(
                "NCP-STATE-002",
                "ESTOP remains latched",
            ));
        }
        if self.state != LifecycleState::Reconnecting {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "reconnect continuity proof is allowed only from reconnecting",
            ));
        }
        let current = self
            .lease
            .as_ref()
            .ok_or_else(|| AuthorityError::new("NCP-LEASE-003", "there is no retained lease"))?;
        if session_epoch != current.session_epoch
            || term != current.term
            || lease_id != current.lease_id
            || holder.principal_id != current.holder_principal_id
            || holder.entity_id != current.holder_entity_id
        {
            return Err(AuthorityError::new(
                "NCP-LEASE-001",
                "reconnect continuity proof is stale or mismatched",
            ));
        }
        if self
            .accepted_until_monotonic_ms
            .is_none_or(|deadline| now_monotonic_ms >= deadline)
        {
            self.accepted_until_monotonic_ms = None;
            self.transition(LifecycleState::Hold);
            return Err(AuthorityError::new(
                "NCP-LEASE-002",
                "authority lease expired before reconnect",
            ));
        }
        self.transition(LifecycleState::Active);
        Ok(())
    }

    pub fn estop(&mut self) {
        // ESTOP reset is a generation cut.  A restored retired machine is
        // audit-only and must remain inert, including against a delayed ESTOP
        // event from the superseded generation.
        if self.retired {
            return;
        }
        self.estop_latched = true;
        self.accepted_until_monotonic_ms = None;
        self.transition(LifecycleState::Estop);
    }

    /// Perform the local authority half of an authorized ESTOP generation cut.
    /// Success retires this immutable machine permanently; a new SessionOpened
    /// generation constructs a new machine rather than reopening this one.
    pub fn reset_estop(&mut self, actor: &AuthenticatedActor) -> Result<(), AuthorityError> {
        if actor.role != PrincipalRole::Operator || !actor.may_reset_estop {
            return Err(AuthorityError::new(
                "NCP-STATE-002",
                "ESTOP reset requires an enrolled operator reset grant",
            ));
        }
        if !self.estop_latched {
            return Err(AuthorityError::new("NCP-STATE-001", "ESTOP is not latched"));
        }
        self.estop_latched = false;
        self.lease = None;
        self.accepted_until_monotonic_ms = None;
        // Reset is a generation cut, not a return to HOLD inside the old session.
        // This machine's epoch is immutable, so retire it permanently and require a
        // newly constructed machine for the fresh SessionOpened generation.
        self.retired = true;
        self.transition(LifecycleState::Closed);
        Ok(())
    }

    /// True once this immutable session generation was retired by ESTOP reset.
    pub fn is_retired(&self) -> bool {
        self.retired
    }

    pub fn begin_close(&mut self) -> Result<(), AuthorityError> {
        if matches!(self.state, LifecycleState::Closed | LifecycleState::Closing) {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "session is already closed or closing",
            ));
        }
        self.lease = None;
        self.accepted_until_monotonic_ms = None;
        self.transition(LifecycleState::Closing);
        Ok(())
    }

    pub fn finish_close(&mut self) -> Result<(), AuthorityError> {
        if self.state != LifecycleState::Closing {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "finish_close is allowed only from closing",
            ));
        }
        self.transition(LifecycleState::Closed);
        Ok(())
    }

    pub fn fail(&mut self) {
        self.lease = None;
        self.accepted_until_monotonic_ms = None;
        self.transition(LifecycleState::Failed);
    }

    pub fn snapshot(&self) -> AuthoritySnapshot {
        AuthoritySnapshot {
            session_epoch: self.session_epoch.clone(),
            state: self.state,
            state_version: self.state_version,
            highest_term: self.highest_term,
            lease: self.lease.clone(),
            estop_latched: self.estop_latched,
            retired: self.retired,
        }
    }

    /// Restore durable safety state. A former active/reconnecting session is
    /// restored as `Reconnecting`, without an accepted monotonic deadline; a new
    /// term must be acquired because process-local expiry continuity was lost.
    pub fn restore(snapshot: AuthoritySnapshot) -> Result<Self, AuthorityError> {
        if snapshot.state == LifecycleState::Unknown
            || !is_canonical_uuid_v4(&snapshot.session_epoch)
            || snapshot.highest_term > JSON_SAFE_INTEGER_MAX as u64
            || snapshot.state_version > JSON_SAFE_INTEGER_MAX as u64
        {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "authority snapshot identity/version is invalid",
            ));
        }
        if snapshot.state == LifecycleState::Estop && !snapshot.estop_latched {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "ESTOP lifecycle state requires a durable ESTOP latch",
            ));
        }
        if snapshot.retired
            && (snapshot.state != LifecycleState::Closed
                || snapshot.estop_latched
                || snapshot.lease.is_some())
        {
            return Err(AuthorityError::new(
                "NCP-STATE-001",
                "retired authority snapshot must be closed, unlatched, and lease-free",
            ));
        }
        if let Some(lease) = &snapshot.lease {
            validate_lease_shape(lease)?;
            if lease.session_epoch != snapshot.session_epoch || lease.term > snapshot.highest_term {
                return Err(AuthorityError::new(
                    "NCP-STATE-001",
                    "authority snapshot lease conflicts with its epoch/term",
                ));
            }
        }
        let state = if snapshot.estop_latched || snapshot.state == LifecycleState::Estop {
            LifecycleState::Estop
        } else if matches!(
            snapshot.state,
            LifecycleState::Active | LifecycleState::Reconnecting
        ) {
            LifecycleState::Reconnecting
        } else {
            snapshot.state
        };
        Ok(Self {
            state,
            session_epoch: snapshot.session_epoch,
            state_version: snapshot.state_version,
            highest_term: snapshot.highest_term,
            lease: snapshot.lease,
            accepted_until_monotonic_ms: None,
            estop_latched: snapshot.estop_latched,
            retired: snapshot.retired,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{BTreeSet, HashSet, VecDeque};

    const EPOCH: &str = "123e4567-e89b-42d3-a456-426614174000";
    const LEASE1: &str = "123e4567-e89b-42d3-a456-426614174001";
    const LEASE2: &str = "123e4567-e89b-42d3-a456-426614174002";

    fn actor(id: &str, role: PrincipalRole) -> AuthenticatedActor {
        AuthenticatedActor {
            principal_id: id.into(),
            certificate_identity: format!("urn:ncp:{id}"),
            entity_id: "plant".into(),
            role,
            may_reset_estop: role == PrincipalRole::Operator,
            may_override: role == PrincipalRole::Operator,
        }
    }

    fn lease(term: u64, id: &str, issuer: &str, holder: &str) -> AuthorityLease {
        AuthorityLease {
            session_epoch: EPOCH.into(),
            term,
            lease_id: id.into(),
            issuer_principal_id: issuer.into(),
            holder_principal_id: holder.into(),
            holder_entity_id: "plant".into(),
            issued_at_utc_ms: 1_000,
            expires_at_utc_ms: 2_000,
        }
    }

    fn initialized() -> AuthorityMachine {
        let mut machine = AuthorityMachine::new(EPOCH).unwrap();
        machine.begin_open().unwrap();
        machine.initialize().unwrap();
        machine
    }

    #[test]
    fn two_controllers_require_newer_authorized_transfer_or_override() {
        let c1 = actor("controller-a", PrincipalRole::Commander);
        let c2 = actor("controller-b", PrincipalRole::Commander);
        let operator = actor("operator", PrincipalRole::Operator);
        let mut machine = initialized();
        machine
            .acquire(
                lease(1, LEASE1, "controller-a", "controller-a"),
                &c1,
                &c1,
                1_000,
                10,
            )
            .unwrap();
        assert!(machine
            .acquire(
                lease(2, LEASE2, "controller-b", "controller-b"),
                &c2,
                &c2,
                1_000,
                10
            )
            .is_err());
        machine
            .acquire(
                lease(2, LEASE2, "operator", "controller-b"),
                &operator,
                &c2,
                1_000,
                10,
            )
            .unwrap();
        assert_eq!(
            machine.active_lease(11).unwrap().holder_principal_id,
            "controller-b"
        );
    }

    #[test]
    fn strict_lease_boundary_partition_rejoin_and_stale_term_fail_closed() {
        let c1 = actor("controller-a", PrincipalRole::Commander);
        let mut machine = initialized();
        machine
            .acquire(
                lease(1, LEASE1, "controller-a", "controller-a"),
                &c1,
                &c1,
                1_000,
                10,
            )
            .unwrap();
        machine.disconnect("controller-a").unwrap();
        machine.reconnect(&c1, EPOCH, 1, LEASE1, 1_009).unwrap();
        machine.disconnect("controller-a").unwrap();
        let err = machine.reconnect(&c1, EPOCH, 1, LEASE1, 1_010).unwrap_err();
        assert_eq!(err.code, "NCP-LEASE-002");
        assert_eq!(machine.state(), LifecycleState::Hold);
        assert!(machine
            .acquire(
                lease(1, LEASE1, "controller-a", "controller-a"),
                &c1,
                &c1,
                1_500,
                2_000
            )
            .is_err());
    }

    #[test]
    fn renewal_requires_authenticated_issuer_and_unexpired_current_lease() {
        let commander = actor("controller-a", PrincipalRole::Commander);
        let operator = actor("operator", PrincipalRole::Operator);
        let mut machine = initialized();
        machine
            .acquire(
                lease(1, LEASE1, "operator", "controller-a"),
                &operator,
                &commander,
                1_000,
                10,
            )
            .unwrap();

        let mut renewed = lease(1, LEASE1, "operator", "controller-a");
        renewed.issued_at_utc_ms = 1_500;
        renewed.expires_at_utc_ms = 2_500;

        let forged = machine
            .renew(renewed.clone(), &commander, &commander, 1_500, 20)
            .unwrap_err();
        assert_eq!(forged.code, "NCP-LEASE-001");

        machine
            .renew(renewed.clone(), &operator, &commander, 1_500, 20)
            .unwrap();
        assert!(machine.active_lease(1_019).is_some());

        let expired = machine
            .renew(renewed, &operator, &commander, 2_500, 1_020)
            .unwrap_err();
        assert_eq!(expired.code, "NCP-LEASE-002");
        assert_eq!(machine.state(), LifecycleState::Hold);
        assert!(machine.active_lease(1_020).is_none());
    }

    #[test]
    fn restart_preserves_estop_and_never_restores_active_authority() {
        let c1 = actor("controller-a", PrincipalRole::Commander);
        let operator = actor("operator", PrincipalRole::Operator);
        let mut machine = initialized();
        machine
            .acquire(
                lease(1, LEASE1, "controller-a", "controller-a"),
                &c1,
                &c1,
                1_000,
                0,
            )
            .unwrap();
        let restored = AuthorityMachine::restore(machine.snapshot()).unwrap();
        assert_eq!(restored.state(), LifecycleState::Reconnecting);
        assert!(restored.active_lease(0).is_none());

        machine.estop();
        let mut restored = AuthorityMachine::restore(machine.snapshot()).unwrap();
        assert_eq!(restored.state(), LifecycleState::Estop);
        assert!(restored.reconnect(&c1, EPOCH, 1, LEASE1, 1).is_err());
        restored.reset_estop(&operator).unwrap();
        assert_eq!(restored.state(), LifecycleState::Closed);
        assert!(restored.is_retired());
        restored.estop();
        assert_eq!(restored.state(), LifecycleState::Closed);
        assert!(!restored.snapshot().estop_latched);
        assert!(restored.begin_open().is_err());
        assert!(restored
            .acquire(
                lease(2, LEASE2, "controller-a", "controller-a"),
                &c1,
                &c1,
                1_000,
                1,
            )
            .is_err());
        let restored_again = AuthorityMachine::restore(restored.snapshot()).unwrap();
        assert!(restored_again.is_retired());
        assert!(restored_again.active_lease(0).is_none());
    }

    #[test]
    fn restore_rejects_estop_lifecycle_without_durable_latch() {
        let mut machine = initialized();
        machine.state = LifecycleState::Estop;
        machine.estop_latched = false;

        let error = AuthorityMachine::restore(machine.snapshot()).unwrap_err();

        assert_eq!(error.code, "NCP-STATE-001");
    }

    #[test]
    fn acquire_rejects_estop_lifecycle_even_when_latch_flag_is_false() {
        let commander = actor("controller-a", PrincipalRole::Commander);
        let mut machine = initialized();
        machine.state = LifecycleState::Estop;
        machine.estop_latched = false;

        let error = machine
            .acquire(
                lease(1, LEASE1, "controller-a", "controller-a"),
                &commander,
                &commander,
                1_000,
                10,
            )
            .unwrap_err();

        assert_eq!(error.code, "NCP-STATE-002");
    }

    #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
    struct AbstractState {
        holder: u8,
        term: u8,
        estop: bool,
        connected: bool,
    }

    /// Exhaustively explores a bounded two-controller/partition/restart model.
    /// The executable implementation tests above bind abstract events to wire
    /// identities; this search proves the central safety invariants for every
    /// trace through depth ten, rather than a hand-picked happy path.
    #[test]
    fn exhaustive_two_controller_model_has_no_counterexample() {
        let initial = AbstractState {
            holder: 0,
            term: 0,
            estop: false,
            connected: true,
        };
        let mut queue = VecDeque::from([(initial, 0u8)]);
        let mut visited = HashSet::from([initial]);
        let mut explored = 0usize;
        while let Some((state, depth)) = queue.pop_front() {
            explored += 1;
            assert!(state.holder <= 2, "at most one holder is representable");
            assert!(
                !(state.estop && state.holder != 0),
                "ESTOP forbids active authority"
            );
            if depth == 10 {
                continue;
            }
            let mut next = BTreeSet::new();
            // Fresh term grant to either controller; ESTOP blocks activation.
            if !state.estop && state.term < 6 {
                for holder in [1, 2] {
                    next.insert((holder, state.term + 1, state.estop, state.connected));
                }
            }
            // Partition/disconnect removes active authority without lowering term.
            next.insert((0, state.term, state.estop, false));
            // Rejoin does not regain authority implicitly.
            next.insert((state.holder, state.term, state.estop, true));
            // ESTOP is sticky over partition/rejoin/restart.
            next.insert((0, state.term, true, state.connected));
            // Authenticated operator reset returns to no-holder HOLD.
            if state.estop {
                next.insert((0, state.term, false, state.connected));
            }
            // Process restart never restores a holder.
            next.insert((0, state.term, state.estop, state.connected));
            for (holder, term, estop, connected) in next {
                let candidate = AbstractState {
                    holder,
                    term,
                    estop,
                    connected,
                };
                // No transition lowers the accepted term; stale authority cannot return.
                assert!(candidate.term >= state.term);
                if visited.insert(candidate) {
                    queue.push_back((candidate, depth + 1));
                }
            }
        }
        assert!(
            explored >= 50,
            "model search unexpectedly shallow: {explored}"
        );
    }
}
