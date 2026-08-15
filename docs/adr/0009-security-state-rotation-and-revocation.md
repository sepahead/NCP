# ADR-009 — Bind semantic security state, rotation, and revocation

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: security reviewer, operations reviewer, supply-chain
  reviewer, security-artifact-anchor infrastructure owner/operator, independent
  anchor security reviewer

## Context

Hashing one configuration file or relying on a key ID does not identify the
complete public trust state that governs a session. Rotation, revocation,
manifest membership, audiences, algorithms, profiles, and ACLs can change after
discovery. Peers need a deterministic semantic identity and an explicit
transition rather than stale continuation.

## Proposed decision

The `security_state_digest` shall cover a canonical semantic projection of:

- the exact neutral ADR-001 `AuthorityRealmKey`, matching
  `AuthorityTransactionDomainKey`, local security-authority lineage and current
  `security_epoch`;
- named transport/authentication profile and exact profile version;
- enrolled principals, entities, roles, planes, literal route/class grants, and
  audiences;
- signing/certificate key fingerprints, fully specified algorithms, key epochs,
  validity intervals, and allowed uses;
- trust roots and authenticated manifest identities;
- revocation set digest and monotonically increasing revocation epoch;
- ACL/authority manifest digests;
- replay/recovery domain identities and clock policy;
- privacy/redaction policy identifiers relevant to attached observers; and
- the stable-core and accepted extension manifest identities to which the state
  applies.

Each realm-local ADR-001 authority transaction domain/store incarnation owns
exactly one canonical `SecurityAuthorityStateHead` through exactly one
`InstalledSecurityAuthorityStateSelector`. A selector cannot participate in two
realms or stores. A selector in an external consumer store is not realm-local and
cannot join this compare-and-swap. Fleet or global CA, key-custody, and
revocation-feed state remains external signed input. Each local enforcement root
installs that input independently. This ADR claims no cross-store atomicity,
cross-realm atomicity, or instantaneous propagation.

The head binds the neutral realm and authority domain, a never-reused state-
lineage incarnation, and a strictly increasing `authority_state_version`. It also
binds one closed `SecurityAuthorityPhase`, the current enforcement semantic-state
digest, positive security and revocation epochs, and the prior-head digest.
The phase union is exactly
`CURRENT | PREPARED_CHANGE | SUCCESSOR_ACTIVE_REBIND_PENDING |
EMERGENCY_FENCED_RECOVERY_REQUIRED | DOMAIN_RETIREMENT_DRAIN |
DOMAIN_RETIRED`. Selector absence before the sole genesis is not a phase.
It always binds one bounded
`RegisteredExternalSecurityEnforcementRootRegistryHead` and one installed
`RealmSecurityAttestationClockState`, plus one bounded
`EmergencySecurityFencingObligationMap` whose retained local entries are
dormant outside an incident.
The registry head, in turn, always owns and binds the exact
`EmergencySecurityExternalClosureObligationMap` root and its canonical
one-entry-per-retained-registration bijection. Registration, emergency apply,
external reconciliation, recovery and domain drain mutate that map only through
the installed registry head inside the global security CAS. It is not an
optional side object or an independently writable selector.
Optional state includes one `PlannedSecurityStateChangeCandidate`, its exact
`PlannedSecurityAffectedRootSetCommitment`,
`PlannedSecurityExternalEnforcementRootSetCommitment`.

The head shape is phase-discriminated. An
`EMERGENCY_FENCED_RECOVERY_REQUIRED` head requires exactly one current
`EmergencySecurityFenceIncidentCommitment`,
`EmergencySecurityRecoveryBaselineCommitment`, and
`EmergencySecurityCumulativeRestrictionCommitment`, plus both authoritative
obligation maps. A first emergency creates all three roots; a consecutive
emergency preserves the baseline and advances the incident and cumulative root.
`CURRENT`, `PREPARED_CHANGE` and `SUCCESSOR_ACTIVE_REBIND_PENDING` structurally
forbid live incident/baseline/cumulative fields. `DOMAIN_RETIREMENT_DRAIN` and
`DOMAIN_RETIRED` retain their prior emergency roots only inside exact
`SecurityAuthorityDomainRetirementEmergencyArchiveCommitment` and forbid
recovery use. Proved-empty maps still require canonical empty roots; absence is
not an empty incident.

Before each authority transition, the enrolled authority constructs one closed
`SecurityAuthorityTransitionFact` variant. The genesis variant binds typed
selector absence, never-used proof, external trust-root enrollment, and the exact
initial state. Every other variant binds the exact prior head. Each fact binds
only the fields required by its exact event. A fact contains no successor head,
selector version, current or future commit receipt, per-session
`SecurityStateTransitionAuthorization`, or later root-rebind evidence.

Before the fact, receipt-free `SecurityAuthoritySuccessorStateCommitment` fixes
the complete canonical successor semantic fields, encoding/schema version,
counter effects, registry/map projections and closed derivation rule, while
excluding the fact, management envelope, successor head/digest, selector and
every receipt. The fact binds that commitment. For one prior head or typed
genesis absence, event and commitment, the derivation rule admits exactly one
canonical successor semantic projection; authentication representation cannot
change that projection. The candidate binds the fact, commitment, exact ADR-001
`AuthorityTransactionCASCondition`, applicable
`RealmSecurityDeadlineConditionIntentSetRoot`, and later closed
`SecurityAuthorityCandidateAuthenticationEvidence`:
`GENESIS_TRUST_ROOT_ENROLLMENT_EVIDENCE |
NON_GENESIS_MANAGEMENT_ENVELOPE_DIGEST`. Genesis binds only the authenticated
enrollment evidence and forbids an envelope digest. Every other event binds only
its later management-envelope digest and forbids the genesis branch. One exact
full input tuple admits one candidate byte string. Distinct valid threshold
envelopes can form competing candidates only for the same fixed semantic
projection; the operation map retains the first exact input tuple, and the
selector CAS permits at most one to install. A retry returns that installed
tuple. An omitted field, alternate serialization for the same tuple, extra
successor member, mixed branch or second candidate byte string from the same
full tuple rejects.

The successor head binds the fact. It excludes its own digest, signature, and
receipt. It also excludes each successor selector and later receipt. Updates
compare-and-swap the authority-owned
`InstalledSecurityAuthorityStateSelector`. After the in-transaction comparison
wins, `SecurityAuthorityStateCommitReceipt` binds the prior and installed heads.
It also binds both authority-state versions, selector version, operation,
enrolled security authority, and the exact ADR-001
`AuthorityTransactionCommitReceipt`.

The same authority-domain transaction persists the selector, installed head, and
complete signed receipt bundle. It exposes the bundle only after crash-complete
durable commit. The authority-state version starts at 1 and increments by exactly
one on every successful authority-state compare-and-swap. It is distinct from
`security_epoch` and `revocation_epoch`. Those semantic counters advance only
under the closed rules below.

Every installed head binds one
`SecurityAuthorityTransitionAuthenticationPolicy`. The policy has five
purpose-separated key uses:
`SECURITY_MANAGEMENT_TRANSITION_AUTHORIZATION |
SECURITY_COMMIT_RECEIPT_AUTHENTICATION |
EXTERNAL_CURRENTNESS_ATTESTATION |
CROSS_STORE_PUBLICATION_MANIFEST_AUTHENTICATION |
ENFORCEMENT_CREDENTIAL`. Each use has an exact key fingerprint, key epoch,
algorithm, threshold, validity rule and historical-verification policy.
Management, receipt, currentness, publication-manifest and enforcement uses
cannot substitute for one another. In particular, a currentness key cannot
authorize a source transition or authenticate a source commit receipt, and a
receipt key cannot authenticate a final cross-store manifest.
Each use contains a bounded closed set of
`SecurityAuthorityAuthenticationKeyOrigin` instances:
`ONLINE_PRIMARY | OFFLINE_RECOVERY_DOMAIN`. Currentness and enforcement permit
only `ONLINE_PRIMARY`. Management, receipt and publication-manifest policy can
also enroll distinct `OFFLINE_RECOVERY_DOMAIN` instances. The
`OFFLINE_RECOVERY_THRESHOLD` continuity mode uses only the offline-recovery
management instance; its commit receipt and any protected recovery or incident
publication use only the offline-recovery receipt and manifest instances.
Purpose and origin are both exact. A key cannot substitute across either axis.

The trust-root enrollment for genesis authenticates all five initial online
authorities and a separately controlled offline-recovery authority. Exact
`SecurityAuthorityGenesisKeyProofOfPossessionSet` contains one proof for every
initial management, receipt, currentness, publication-manifest and enforcement
key and every enrolled offline-recovery management, receipt and
publication-manifest key. Each proof binds realm/domain/lineage, purpose,
origin, fingerprint, key epoch, algorithm, enrollment commitment, fresh
enrollment challenge and replay domain. The enrollment threshold authenticates
the complete set root. Omitted, duplicate, wrong-purpose, wrong-origin or
cross-purpose proofs reject; possession of one use/origin's private key cannot
enroll another.
Each non-genesis `SecurityAuthorityTransitionFact` is constructed first and
structurally excludes its management envelope. The authority then signs exact
fact bytes/digest in
`ProtectedSecurityAuthorityManagementAuthorizationEnvelope`; the candidate
successor binds both the fact and envelope digest. Its closed continuity mode is
`PREDECESSOR_THRESHOLD |
DUAL_SIGNED_BOUNDED_VERIFICATION_OVERLAP |
OFFLINE_RECOVERY_THRESHOLD`. The first mode verifies against the exact
predecessor head. The dual-signed mode verifies the same transition under both
predecessor and successor management thresholds and is legal only for a bounded
key transition fixed by the prepared candidate. It preserves receipt-
verification continuity; it grants no concurrent enforcement authority. The
offline mode verifies against the independently enrolled recovery threshold and
is legal only for emergency fence, compromise declaration, restrictive recovery
or domain-retirement events whose exact allowlist is fixed by the installed
policy. Unknown modes or mixed-use keys reject.

The envelope binds the exact transition-fact bytes/digest, realm/domain/lineage,
expected prior head/selector version, event, operation and replay domain,
candidate or recovery commitment when applicable, signer set, threshold,
algorithm and key-use policy. It contains no successor receipt and cannot be
replayed across a sibling head or event.

Any transition that enrolls a successor key set also binds
`SecurityAuthoritySuccessorKeyProofOfPossession` for every successor management,
receipt, currentness, publication-manifest and enforcement key. The proofs bind
every online/offline origin instance, the same purpose-separated identity fields
and the exact prepared-successor commitment; one use or origin cannot satisfy
another. At activation, the predecessor
management and issuance signing cutoffs are exact commit coordinates. No new
artifact under the predecessor can commit, be exposed as installed or authorize
after that cut; verification rejects it even if a signer can still perform raw
cryptographic operations. A separately qualified signer/HSM fence can strengthen
custody but is not inferred from the protocol cut. Historical verification
material, algorithms, manifests, cutoffs and signed ancestry are retained;
deleting an online private key does not delete its verification history or
authorize re-signing an old receipt.

`ProtectedSecurityAuthorityCommitReceiptEnvelope` has closed payload mode
`GLOBAL_SECURITY_AUTHORITY_COMMIT |
PER_KEY_CURRENTNESS_ISSUANCE_COMMIT |
PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT`. It authenticates the exact
`SecurityAuthorityStateCommitReceipt` or
`ExternalSecurityCurrentnessIssuanceCommitReceipt` or
`ExternalSecurityDerivedAuthorityGrantLedgerCommitReceipt`, respectively, under the
purpose-separated receipt key selected by the exact global security head.
The global mode also binds the installed global head and complete registered
external-root registry-snapshot commitment, exact transition event and
canonical complete event-specific sibling-receipt type/digest set. A sibling
receipt is included only when it derives from the same common transaction; a
missing, extra, duplicated or cross-transaction receipt rejects. The envelope
selects
`CrossStoreSecurityReceiptAudienceBinding /
SOURCE_SECURITY_DOMAIN_HISTORY`, and is the
`DURABLE_HISTORICAL_COMMIT` specialization of
`ProtectedCrossStoreSecurityReceiptEnvelope`. The per-key mode binds the
installed child head/commit receipt and has closed submode
`REGISTRATION_GENESIS |
ATTESTATION_ISSUANCE |
CLOCK_RESTART`. Registration binds the enrollment commitment and joint global
registration coordinate and forbids payload/attestation/expiry fields.
Attestation issuance binds the observed global coordinate, signed-payload and
post-CAS-attestation digests and exact audience. Every per-key mode selects
`CrossStoreSecurityReceiptAudienceBinding /
SINGLE_REGISTERED_EXTERNAL_ROOT`. Clock restart binds the bridge, child
candidate and joint installed global coordinate and forbids issuance fields.
The grant-ledger mode binds the installed ledger head/commit receipt and has
closed submode `LEDGER_GENESIS | GRANT_APPEND | GRANT_LINEAGE_CLOSE |
CLOCK_RESTART`. Genesis binds the enrollment commitment and post-CAS specialized
genesis-receipt digest. Grant append binds the exact plan digest, post-CAS
`ExternalSecurityDerivedAuthorityGrantReceipt` digest, target-specific
`ExternalSecurityDerivedAuthorityTargetProjection`, common source-transaction
coordinate. It excludes both aggregate roots/counts, every privacy projection,
tree opening and membership proof because those are created only after all
protected envelopes and the pre-manifest commitment exist. The later selected
`CrossStoreProtectedOutputDeliveryCapsule` carries the fixed-shape family-member
and family-set proofs. Optional exact openings are legal only in that capsule
under the separately linearized unanimous exact-topology branch. It selects only that plan's
`SINGLE_REGISTERED_EXTERNAL_ROOT` audience and contains no sibling receipt,
projection or envelope. Lineage close binds the exact close commitment and post-CAS
`ExternalSecurityDerivedAuthorityGrantLineageCloseReceipt` digest. Clock
restart binds the bridge and mapped ledger candidate. These submodes
structurally forbid currentness payload, attestation and expiry fields. Every
per-key mode and submode is
`DURABLE_HISTORICAL_COMMIT`: after attestation expiry it can prove only committed
ancestry and idempotent history, never current authority.

Separate
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope` is the
`EPHEMERAL_AUTHORITY_WINDOW` specialization. It binds the exact post-CAS
attestation, pre-CAS payload envelope, durable per-key commit-envelope digest,
installed global/child coordinates, audience and fixed expiry. It is created by
the qualified receipt signer inside the same commit and expires without erasing
the durable lineage. Thus every post-CAS artifact crosses only in its exact
audience-bound protected envelope. The pre-CAS currentness signature proves
payload intent but cannot prove installation or substitute for either post-CAS
envelope.
An activation that changes that key uses the same bounded dual-signature
continuity mode for this one commit; subsequent commits accept only the
successor receipt policy. An offline-recovery commit uses the separately
enrolled recovery-receipt threshold fixed by the predecessor policy.
After the transaction manager fixes the commit coordinates and all conditions
pass, its qualified commit signer creates that envelope before final durable
selector publication. The transaction atomically persists the installed head,
receipt, envelope and persistence manifest or publishes none of them. The head
does not bind this later receipt or envelope. A post-publication signing promise,
currentness signature, unsigned local database row or message-selected key
cannot authenticate source ancestry.

`SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT` is the sole local
security genesis. Before its one-use CAS, the enrolled authority constructs the
provision variant of `SecurityAuthorityTransitionFact`. It binds the exact realm/
domain/store, never-used lineage incarnation, initial semantic enforcement state
and authority, security and revocation epochs 1, authenticated parent trust-root
enrollment, typed selector absence plus never-used proof, operation and
enrollment authorization. It contains no prior or successor authority head,
installed selector version, current/future receipt or per-session authorization.
The version-1 candidate head binds this fact instead of fabricating a prior head.

The genesis is ADR-001
`INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS` under
`CANDIDATE_PARTICIPANT_ADMISSION`. One authority-domain transaction compares the
active domain state and atomically installs the version-1 security head/selector,
`LOCAL_SECURITY_ENFORCEMENT` participant entry, ACL and closure-reserve successor.
The head is never current or usable outside that registry membership. The
winning `AuthorityTransactionCommitReceipt` precedes
`SecurityAuthorityStateCommitReceipt`, the native genesis receipt and
`AuthorityTransactionDomainParticipantAdmissionReceipt`; the persistence
manifest binds the complete bundle last. Authorization, a signed candidate or an
absent slot does not prove installation. After any use, selector loss, rollback,
sibling genesis, reconstructed absence, restart reset or lineage reuse routes to
ADR-001 loss isolation or a separately enrolled replacement realm; it never
creates another epoch-1 root under the old key.

The closed security-authority transition union is:

- `SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT`;
- `INSTALL_NON_AUTHORIZING_SECURITY_METADATA_UPDATE`;
- `REGISTER_EXTERNAL_SECURITY_ENFORCEMENT_ROOT`;
- `CONFIRM_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_LOCAL_GENESIS`;
- `APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART`;
- `CANCEL_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`;
- `EXPIRE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`;
- `BEGIN_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT`;
- `FINALIZE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT`;
- `PREPARE_PLANNED_SECURITY_STATE_CHANGE`;
- `CANCEL_PREPARED_SECURITY_STATE_CHANGE_BEFORE_QUIESCE`;
- `ACTIVATE_PREPARED_SECURITY_STATE_CHANGE_AFTER_QUIESCE`;
- `COMPLETE_PLANNED_SECURITY_STATE_CHANGE_AFTER_REBIND`;
- `APPLY_EMERGENCY_SECURITY_FENCE`;
- `DECLARE_SECURITY_COMPROMISE_INCIDENT`;
- `RECONCILE_EMERGENCY_SECURITY_FENCING_OBLIGATION`;
- `RECONCILE_EMERGENCY_SECURITY_EXTERNAL_CLOSURE_OBLIGATION`;
- `RECOVER_FROM_EMERGENCY_SECURITY_FENCE`;
- `BEGIN_SECURITY_AUTHORITY_DOMAIN_RETIREMENT_DRAIN`; and
- `RETIRE_SECURITY_AUTHORITY_DOMAIN_FOR_REPLACEMENT`.

The separate per-external-key issuance transition union is exactly
`EXTERNAL_SECURITY_CURRENTNESS_ISSUANCE_GENESIS_FROM_REGISTRATION |
ISSUE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_GENESIS_CURRENTNESS_ATTESTATION |
ISSUE_REALM_SECURITY_CURRENTNESS_ATTESTATION`. These events do not mutate the
global security head. A clock restart jointly advances each extant per-key
issuance head through the global
`APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART` transaction.

Every successful global transition increments `authority_state_version` by
exactly one.
`INSTALL_NON_AUTHORIZING_SECURITY_METADATA_UPDATE` can change only bounded
diagnostic or audit metadata that is outside the enforcement semantic-state
digest. It preserves both semantic epochs and every authority-bearing member.
Changing a key, trust root, algorithm, validity rule, principal, role, route,
plane, audience, ACL, profile, revocation member, or accepted extension cannot
use this event.

Every deadline-sensitive security transition uses one domain-separated
commit-bound condition family. Receipt-free
`RealmSecurityDeadlineConditionIntent` binds the exact store/authority, event,
operation, expected prior installed selector/head and complete read-set versions, clock
incarnation, deadline, comparator and
`RealmSecurityDeadlineTimingProofProfile`. The profile fixes only
the construction, qualification identity, maximum completion bound and abort
policy. It contains no trusted sample, evaluation, result or receipt. Its closed
purpose is
`COMMIT_STRICTLY_BEFORE_EXCLUSIVE_DEADLINE |
COMMIT_AT_OR_AFTER_EXCLUSIVE_DEADLINE`. Its closed kind is:

`SOURCE_EXTERNAL_ROOT_GENESIS_ISSUE_NOT_AFTER_INITIALIZATION |
SOURCE_EXTERNAL_ROOT_CONFIRMATION_NOT_AFTER_INITIALIZATION |
SOURCE_EXTERNAL_ROOT_CONFIRMATION_ACCEPT_NOT_AFTER |
SOURCE_EXTERNAL_ROOT_CONFIRMATION_ELAPSED_AT_OR_AFTER |
LOCAL_EXTERNAL_ROOT_GENESIS_ACCEPT_NOT_AFTER |
LOCAL_EXTERNAL_ROOT_CONFIRMATION_ACCEPT_NOT_AFTER |
CURRENTNESS_ENVELOPE_VALIDITY_NOT_AFTER |
PLANNED_SECURITY_ACTIVATION_NOT_AFTER |
PLANNED_SECURITY_REBIND_NOT_AFTER |
IMPORTED_SECURITY_MIRROR_NOT_AFTER |
SOURCE_EXTERNAL_AUTHORITY_HORIZON_ELAPSED_AT_OR_AFTER |
SECURITY_ATTESTATION_CLOCK_RESTART_CUTOFF |
EXACT_TOPOLOGY_DISCLOSURE_RELEASE_NOT_AFTER`.

`EXACT_TOPOLOGY_DISCLOSURE_RELEASE_NOT_AFTER` is legal only for
`AUTHORIZE_CROSS_STORE_EXACT_TOPOLOGY_DISCLOSURE` in the owner-local
disclosure-ledger store/authority coordinate. It uses
`COMMIT_STRICTLY_BEFORE_EXCLUSIVE_DEADLINE`, binds the complete disclosure read
condition set and cannot select the at-or-after purpose.

`RealmSecurityDeadlineConditionIntentSetRoot` is the canonical complete staged
set. The transition fact and every candidate successor bind that root before the
CAS. Inside the same serialized transaction that compares the selector,
`RealmSecurityDeadlineConditionEvaluation` binds the trusted authorization-
linearization instant, exact intent, instantiated timing proof and result.
`RealmSecurityDeadlineConditionEvaluationSetRoot` is the exact matching set.
The common transaction receipt, selector-specific receipt, specialized receipt
and final persistence manifest bind the evaluation root; the successor excludes
it and every later receipt. A pre-lock sample, signed candidate, wall time,
post-commit check or root from ADR-004's observer-authorization family cannot
substitute.

The timing proof has the same two closed constructions as ADR-004:
`TRANSACTION_MANAGER_LINEARIZATION | QUALIFIED_COMPLETION_BOUND`, but uses the
realm-security type and digest domain. The bounded branch includes the trusted
sample, checked hard completion bound through signing and durable commit,
qualification and enforced abort/final recheck. Equality takes the restrictive
result. Registration checks both new source deadlines; local genesis checks both
mapped local deadlines; source confirmation, pending expiry, both currentness
issuers, planned activation/completion, every import or local authority action,
clock restart and timed horizon retirement bind their exact applicable complete
set. If one proof is missing, stale, from another clock/store/event or incomplete,
the transition does not publish.

Receipt-free `PlannedSecurityStateChangeCore` is constructed first. It binds the
exact prior current head, operation, complete proposed enforcement semantic
state, planned counter effects, closed change class, source clock
identity/incarnation and policy, bounded activation/rebind deadlines and the two
qualified minimum-work margins. It binds no root set, disposition map, captured
horizon, final candidate or receipt.

After deriving all sets from installed registries,
`PlannedSecurityStateChangeCandidate` binds that core, the complete affected-
root commitment, external-root commitment, external-entry disposition-map root,
and closed `PlannedSecurityExternalHorizonSummary`:
`PROVED_EMPTY_EXTERNAL_SET_NO_HORIZON |
NONEMPTY_FINITE_MAXIMUM`. The empty branch requires the external set to be empty
and forbids every horizon/value field. The nonempty branch binds a bijection to
every member's expected per-key issuance and grant-ledger
selectors/heads/versions, attestation high-water, empty
terminal-required lineage-set root, child horizon, grant ledger
`next_grant_sequence`, optional last-committed sequence and exact
`ExternalSecurityDerivedAuthorityFiniteBoundarySummary`. An empty ledger
summary makes the member horizon exactly the finite child horizon. A nonempty
finite summary makes it the checked maximum of the child and ledger bounds. The
unmappable-historical branch or a marker child cannot enter this finite branch.
The summary also binds the exact
canonical maximum across all members.
Set/member keys bind the core digest, never the final candidate digest. The
candidate is receipt-free, excludes its own digest and has no back-edge from a
bound set or map.
At PREPARE's commit point,
`PlannedSecurityDeadlineFeasibilityEvaluation` proves with checked arithmetic
that the activation deadline is strictly future by at least the complete
quiesce/fence margin. For the nonempty horizon branch, it also proves the
deadline strictly later than the exact maximum plus the qualified horizon-
evaluation/activation-commit bound. The empty branch forbids that comparison.
For both, the rebind deadline follows activation by at least the complete
activation/rebind margin and all present values remain inside the clock-policy
applicability horizon. Equality, overflow or an infeasible interval rejects.
Prepared and rebind-pending phases cannot change clock incarnation. Loss of that
clock routes to emergency fencing or domain retirement; a restart cannot re-date
the candidate. Its
closed `PlannedSecurityStateChangeClass` is
`AUTHORIZING_KEY_ROTATION | AUTHORIZING_NONROTATION |
PLANNED_REVOCATION_SET_CHANGE`. The core and candidate are non-authorizing.

`PlannedSecurityAffectedRootKey` binds the planned-change core digest, exact
realm, root type, selector key, selector incarnation, and owner.
`PlannedSecurityAffectedRootSetCommitment`
binds the planned-change core and the canonical complete keyed set of every live
realm-local root whose admission, authority, delivery, publication, or mutation
can depend on the prior state. It binds the authoritative registry snapshot from
which that set was derived. A caller list, duplicate key, omitted root, or
unregistered root rejects.

The external registry is subordinate content of the security-authority head and
has no independent selector. Its exact immutable key is
`RegisteredExternalSecurityEnforcementRootKey`. It binds the source
realm/domain/lineage, external role and root key, import-store incarnation,
mirror key and owner. It also binds the exact ADR-004 parent-enrollment registry
selector and incarnation, immutable parent-entry key, allocation-receipt digest,
local outer selector and never-reused local state-lineage incarnation. A
replacement parent, reallocated entry, reconstructed selector or new local
incarnation therefore has a different source key. Its closed entry state is
`REGISTERED_PENDING_LOCAL_GENESIS | REGISTERED_ACTIVE | RETIREMENT_PENDING |
PERMANENTLY_RETIRED`; entries are never removed or reused.

Each registry entry owns exactly one bounded
`ExternalSecurityCurrentnessIssuanceHead` through one
`InstalledExternalSecurityCurrentnessIssuanceSelector` in the same qualified
source transaction store. The head binds the registered key, never-reused
issuance lineage, positive issuance-head version, prior-head digest, exact global
security head/commit ancestry and registry-entry version observed by its latest
ordinary issuance. Joint registration/restart successors instead bind their
receipt-free common commitment and structurally forbid a not-yet-installed
global commit receipt.
It also owns the one-use genesis marker, active sequence, bounded
idempotency operation/result map, clock incarnation, last issuance envelope and
the monotonic derived-authority horizon or permanent
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` marker.
`QualifiedExternalAuthorityDerivationHorizonPolicy` has exactly two modes:
`FINITE_CONSERVATIVE_HORIZON | LOCAL_TERMINAL_EVIDENCE_REQUIRED`. The finite
mode fixes the complete derivation classes, enforced final-boundary rule and
checked horizon construction. The marker mode is selected when any derived
action, effect, callback, publication, delivery or retry is unbounded,
ambiguous, or not stopped by an enforceable final boundary. The marker is
irreversible for that registered-key incarnation and forbids every elapsed-time
closure branch.

Each entry also owns exactly one bounded
`ExternalSecurityDerivedAuthorityGrantLedgerHead` through one
`InstalledExternalSecurityDerivedAuthorityGrantLedgerSelector` in that same
source store. The ledger head binds the registered key, a never-reused ledger
incarnation, positive version/prior digest, positive exclusive-next
`next_grant_sequence`, bounded idempotency operation/result map, source-clock
incarnation, one closed
`ExternalSecurityDerivedAuthorityFiniteBoundarySummary`, one canonical
`ExternalSecurityDerivedAuthorityGrantLineageMapRoot` and its exact open
projection `OpenLocalTerminalClosureRequiredGrantLineageSetRoot`. The complete
map contains
the allocated grant sequence, exact plan,
`ExternalDerivedAuthorityLocalWorkLineageCommitment`,
`ExternalSecurityDerivedAuthoritySourceResultCommitment` and preallocated
specialized-receipt identity for every
committed `LOCAL_TERMINAL_CLOSURE_REQUIRED` grant whose closed
`ExternalSecurityDerivedAuthorityGrantLineageState` is
`OPEN_LOCAL_TERMINAL_CLOSURE_REQUIRED` or one of the terminal states below. The
open projection contains exactly the open entries. The terminal states are
`CLOSED_BY_COMPLETE_LOCAL_EMERGENCY_FENCE |
CLOSED_BY_LOCAL_TERMINAL |
CLOSED_BY_SOURCE_PENDING_NEVER_LIVE_PROOF |
CLOSED_BY_SOURCE_COMMIT_AND_LOCAL_NO_INSTALL_TOMBSTONE |
CLOSED_BY_PERMANENT_ISOLATION`. Entries are never silently removed. A close
changes only the exact matched open entries to one terminal state and preserves
their identities in the complete map root. An installed map entry structurally
excludes the later generic commit, specialized receipt, protected-envelope and
manifest bytes or digests.

Grant-ledger genesis is version 1, has `next_grant_sequence = 1`, has no
`last_committed_grant_sequence`, and has empty lineage roots. The configured
positive `maximum_grant_sequence` permits the exclusive-next sentinel
`maximum_grant_sequence + 1`. An append is legal only when the prior next value
is at most the maximum; it allocates that exact value and advances next by
checked arithmetic to exactly one greater. The successor and every receipt bind
the allocated value, installed next value and
`last_committed_grant_sequence`; the latter is absent exactly at genesis and
otherwise equals the greatest allocated value. The sentinel is exhausted and
cannot append. Retry returns the retained allocation without increment.
The installed idempotency result is only the receipt-free source-result
commitment, allocated sequence and preallocated receipt identity; it never
binds later receipt/envelope bytes. The post-CAS retained bundle resolves that
identity to the one committed result.

`ExternalSecurityDerivedAuthorityFiniteBoundarySummary` is exactly
`PROVED_EMPTY_NO_FINITE_BOUNDARY | NONEMPTY_FINITE_MAXIMUM |
UNMAPPABLE_HISTORICAL_MAXIMUM_LOCAL_TERMINAL_REQUIRED`. Genesis selects the empty
branch and forbids a value or clock comparison. A marker-only append or lineage
close preserves the prior branch. The first finite append creates the nonempty
branch; later finite appends store the checked maximum. Clock restart maps that
maximum to its exact conservative upper/later image. If this is impossible, the
third irreversible, nonauthorizing branch binds the original maximum/clock and
restart-map evidence but forbids a current-clock numeric horizon. It also
requires the owning `ExternalSecurityCurrentnessIssuanceHead` to install
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` in the same common restart CAS. Thereafter
every grant uses local-terminal closure mode and the third branch persists.
Empty remains empty without invented time. Every candidate, receipt, capture and
manifest binds the selected branch.

Before registration, receipt-free
`ExternalSecurityCurrentnessIssuanceEnrollmentCommitment` binds the registered
key, issuance and grant-ledger selector/incarnations and both typed
absence/never-used proofs, expected prior global head, clock state, exact
four-family output inventory, family/completion identities and complete
retention/retry reserve. The global registration fact/registry-entry candidate, issuance
genesis candidate and empty grant-ledger genesis candidate all bind that
commitment; no candidate binds another candidate, an installed head or a future
receipt. The joint CAS installs the global registry entry, issuance-head version
1 and grant-ledger version 1. Its global commit receipt and
`ExternalSecurityCurrentnessIssuanceCommitReceipt` bind the installed global
and issuance heads/selectors and the one source transaction receipt.
Generic `ExternalSecurityDerivedAuthorityGrantLedgerCommitReceipt` binds the
installed empty ledger head/selector and that same source transaction receipt.
Specialized `ExternalSecurityDerivedAuthorityGrantLedgerGenesisReceipt` then
binds the enrollment commitment and generic receipt and excludes the later
envelope. Their purpose-separated
commit envelopes use `GLOBAL_SECURITY_AUTHORITY_COMMIT`,
`PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / REGISTRATION_GENESIS`, and
`PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT / LEDGER_GENESIS`. One
`ProtectedRegisteredExternalSecurityEnforcementRootReceiptEnvelope` binds the
specialized pending-registration receipt for the registered root under
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT`. One
`CrossStoreProducerPreManifestBundleCommitment` binds the joint receipts,
sidecars and exact four-envelope partition.
`SecurityAuthorityGlobalCommitPublicationManifest`,
`ExternalSecurityCurrentnessCommitPublicationManifest` and
`ExternalSecurityDerivedAuthorityGrantLedgerCommitPublicationManifest` own the
three commit-envelope families.
`RegisteredExternalSecurityEnforcementRootPublicationManifest` owns the
pending-registration family. The mandatory shared completion manifest
authenticates the exact four-family set last. The hierarchy and
retention record are stored before exposure; no family manifest can complete
registration alone.

Issuance mutates only that key's selector. In the same serializable source
transaction it uses
`SecurityAuthorityGlobalCutReadCondition` to compare, without advancing, the
exact global security selector/head, phase `CURRENT`, current default-deny
manifest authorization and registry entry/version. Its closed
`SecurityAuthorityGlobalCutReadConditionProfile` is
`PENDING_GENESIS_CURRENTNESS_ISSUANCE |
ACTIVE_ENTRY_AUTHORITY_OPERATION`.
`PENDING_GENESIS_CURRENTNESS_ISSUANCE` requires the exact
`REGISTERED_PENDING_LOCAL_GENESIS` entry, pending-registration receipt,
protected receipt envelope, its family manifest, shared completion, two scoped
membership proofs and passing verification.
It structurally forbids a current per-entry manifest-authorization receipt.
`ACTIVE_ENTRY_AUTHORITY_OPERATION` requires the exact `REGISTERED_ACTIVE`
entry and current per-entry manifest-authorization receipt, its protected
envelope, family manifest, shared completion, two scoped membership proofs and
passing verification. It structurally
forbids pending-registration authorization. The read condition, candidate and
receipt bind the selected profile. Unknown, default, mixed or cross-profile
evidence rejects. The store validates this read set at the issuance or
authorization linearization point. A concurrent global PREPARE, emergency,
retirement, semantic change or registry-state write makes one side lose. A
platform that cannot prove read-write conflict serializability cannot implement
this split.

Global restrictive transitions have reserved capacity and scheduling priority
over issuance. Issuance has per-key rate, queue, operation-count and byte caps;
one root cannot keep a global cut from committing. The global head does not
advance for a refresh, so unrelated realm-local authority operations and other
external keys do not import or verify that refresh. An attestation instead binds
two authenticated coordinates: the exact global security head/receipt and the
exact per-key issuance head/receipt. An importer tracks both monotonic lineages.

Restrictive marker closure uses a separate
`ExternalSecurityDerivedAuthorityClosureReadCondition`. It binds the same realm,
registered key/version, global selector/head and target ledger selector/head but
authorizes no issuance and requires no `CURRENT` manifest authorization. It
allows only an extant `REGISTERED_ACTIVE | RETIREMENT_PENDING` entry while the
global phase is `CURRENT | PREPARED_CHANGE |
SUCCESSOR_ACTIVE_REBIND_PENDING | EMERGENCY_FENCED_RECOVERY_REQUIRED |
DOMAIN_RETIREMENT_DRAIN`. It proves that the proposed write only advances the
closed marker lattice and preserves every sibling. The serializable read still
conflicts with each global or per-key change; `DOMAIN_RETIRED`, a permanent
entry, widening output or stale coordinates reject.
`ExternalSecurityDerivedAuthorityClosedMarkerReadCondition` is the read-only
companion for a lineage already closed by source pending-never-LIVE,
role completion, emergency or final retirement. It binds the exact terminal map
member, origin-compatible close commitment/receipt/envelope/final manifest and
ADR-004 operation, permits an active, retirement-pending or permanently retired
entry while the source domain remains verifiable, and performs no ledger
mutation. A different terminal state, missing close ancestry,
`DOMAIN_RETIRED` without retained historical verification or any attempt to
re-close/widen rejects.

The complete cross-store protected-artifact, audience, producer, privacy, exact-disclosure, retention, verification and compromise-anchor rules are in the [cross-store producer and compromise evidence module](modules/adr-009-cross-store-producer-and-compromise-evidence.md). That maintained module is a content-bound part of this ADR review source set. Its closed types and fail-closed rules apply here without weakening or caller-selected substitution.

The security-artifact anchor is not the ADR-004 challenge-exposure anchor by
default. A deployment that colocates both functions must qualify separate
subsubjects. Parsed content-addressed subjects bind separate complete authority,
owner, operator, authenticated-principal, key-fingerprint, credential,
security-epoch, store, selector-incarnation, failure-domain, policy, and emitter
identities. Same-field and cross-field aliases reject. A retained
content-addressed correlated-failure analysis binds both subject digests, shared
failure modes, and residual risks.

A separately controlled issuer signs `PASS` over the exact separation subject
and validity window. Retained trust, credential-issuance,
credential-signature, payload-signature, and exact zero-skip `PASS`
verification artifacts are mandatory. Their signed-64-bit ancestry is strict
and bounded. Missing, stale, equal-boundary, overflowing, or over-limit evidence
rejects. Local structural validation cannot prove organizational independence,
live revocation, or installed-deployment truth; the external X05 qualification
remains mandatory.

`REGISTER_EXTERNAL_SECURITY_ENFORCEMENT_ROOT` is legal only in `CURRENT`. It
consumes the exact ADR-004
`ExternalCompositeStateEnrollmentAllocationReceipt`, its exact
`PENDING_REGISTRATION_BOOTSTRAP` protected envelope and passing verification,
intended root/mirror-key commitment, default-deny source manifest authorization, owner/store qualification
and the ADR-004 source-registered-role reserve for one maximum emergency
work-set closure/rebind-or-retirement continuation. A marker policy cannot
register without that exact precharge. For
`TRUSTED_DELIVERY_BOUNDARY`, the allocation receipt must also bind the exact
ADR-004 `TrustedDeliveryBoundaryNoInstallTombstoneReserve` incarnation,
count/byte bounds and one deterministic position per value through this
registry entry's `maximum_grant_sequence`; its cap must equal the source grant
cap. Other roles bind typed inapplicability. Missing, smaller, differently
keyed or cap-plus-one local capacity rejects registration before a grant can
append.

The allocation also fixes one
`ExternalSecurityEnforcementRootPublicationManifestCredentialCommitment` for
the future installed root. It binds the root/owner/store/incarnation,
`CROSS_STORE_PUBLICATION_MANIFEST_AUTHENTICATION` fingerprint, key epoch,
algorithm, threshold, validity and historical-verification/rotation policy.
Registration also consumes the allocation-bound ADR-004
`ExternalCompositeStateEnrollmentManifestCredentialProofOfPossessionSet`, with
one exact member per threshold key and owner-authenticated challenge/replay
ancestry. The pending registry entry/receipt and later local imported-security
state bind that same commitment/proof. Confirmation proves the installed local
credential matches it. Rotation requires an authenticated source/local
successor under the registered policy and retains predecessor history for
already committed manifests. A missing possession member, message-selected,
uncommitted or merely `ENFORCEMENT_CREDENTIAL` key cannot authenticate a
publication manifest.

Registration also fixes one source-clock
`source_genesis_issue_not_after`, one
`source_confirmation_accept_not_after`, the qualified source-to-import
clock-policy identity and the conservative mapped local
`local_genesis_accept_not_after` and `local_confirmation_accept_not_after`,
`QualifiedExternalAuthorityDerivationHorizonPolicy` and one-use genesis nonce.
The registration fact and successor bind the installed source clock
identity/incarnation and static feasibility policy. At the registration commit
point, `ExternalSecurityRegistrationDeadlineFeasibilityEvaluation` uses checked
arithmetic to prove:

- the source genesis-issuance deadline is strictly future by at least the
  qualified signing, commit, transfer and local-genesis budget;
- the source confirmation deadline follows it by at least the qualified
  local-commit, return-transfer and source-confirmation budget; and
- both deadlines and their conservative local images remain inside the exact
  clock-relation applicability horizons.

Equality, overflow, inverted ordering, a stale clock incarnation or an
insufficient interval rejects without allocating the registry entry.
The commit receipts, four family manifests and shared completion bind the
evaluation; the successor does not bind those later objects.
It atomically creates one `REGISTERED_PENDING_LOCAL_GENESIS` entry, its
version-1 issuance head/selector and the complete issuance/retirement reserve,
and persists the role-specific no-install-reserve commitment or typed
inapplicability in that entry. The receipt, applicable family bodies and shared
completion bind the same value. It then emits
`RegisteredExternalSecurityEnforcementRootReceipt`. That pending receipt is a
bounded deny-only genesis authorization. It is not active registration.
Its `ProtectedRegisteredExternalSecurityEnforcementRootReceiptEnvelope` binds
the receipt, registered root/key and owner, enrollment commitment, installed
global/issuance/ledger coordinates, genesis nonce, source clock incarnation,
`source_genesis_issue_not_after`, operation and replay domain. It uses
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT`; equality and
later time reject. The
`RegisteredExternalSecurityEnforcementRootPublicationManifest` family and
shared completion from the same maximal registration producer authenticate it.
A bare registration receipt or the source-history global envelope cannot
authorize pending-genesis issuance.

Before either currentness-issuance CAS, the source constructs one receipt-free
`RealmSecurityCurrentnessAttestationPayload`. Its closed mode is
`PENDING_GENESIS | ACTIVE_ENTRY`. It binds the exact expected global security
head/selector version, expected per-key issuance head/selector version, expected
next issuance-head version, registry-entry version, mode-specific authorization
evidence, realm/domain/lineage, registry and audience keys,
semantic digest and epochs, clock incarnation, trusted issue sample, fixed
validity, operation, timing-intent-set root, and the mode-specific genesis nonce
or active request nonce and sequence. It excludes the candidate issuance
head/digest, CAS condition, commit-bound evaluation, installed selector version,
current/future issuance commit, authenticated attestation and persistence
receipt. The candidate/fact also preallocates the exact two-family output
inventory, both family identities, one completion identity and complete
retention/retry reserve.

`PENDING_GENESIS` binds the exact digest of the strictly prior pending
registration receipt, its protected envelope, selected registration family,
producer completion, delivery capsule/two scoped proofs and verification
evidence, and structurally
forbids an active-entry manifest-authorization receipt digest, active request
nonce and sequence. It requires
`PENDING_GENESIS_CURRENTNESS_ISSUANCE`.
`ACTIVE_ENTRY` binds the exact digests of the strictly prior current-manifest
authorization receipt, its protected envelope, selected
current-authorization family, producer completion, delivery capsule/two scoped
proofs and verification evidence, and
structurally forbids pending authorization and the genesis nonce. It requires
`ACTIVE_ENTRY_AUTHORITY_OPERATION`. Unknown, mixed or default products reject.

The exact authorized source key signs that payload before the CAS into
`ProtectedRealmSecurityCurrentnessAttestationEnvelope`. The candidate issuance
successor binds the payload and exact envelope digest. The signed envelope alone is
non-authorizing. The winning transaction proves its commit-bound deadline
conditions, installs the successor and durably persists the exact envelope,
`ExternalSecurityCurrentnessIssuanceCommitReceipt`, mode-specific authenticated
attestation, durable `PER_KEY_CURRENTNESS_ISSUANCE_COMMIT /
ATTESTATION_ISSUANCE` envelope, ephemeral
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`, one
pre-manifest commitment,
`ExternalSecurityCurrentnessCommitPublicationManifest` for the durable family,
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest` for the
ephemeral family, and one shared completion manifest as a crash-complete
hierarchy. Both family/authentication sets precede completion; retention
finalization precedes exposure. It also binds the
exact passing global-cut read condition and source transaction receipt. The
currentness signature authenticates payload intent; the receipt envelope proves
which per-key successor committed; only the unexpired installed-attestation
envelope can grant its fixed authority window. A stalled signature or commit
misses the fixed bound and publishes nothing. A losing envelope cannot be
rebound to another global head, issuance head, version, entry, audience,
sequence or operation.
This pre-CAS envelope stays nested in the installed per-key commit envelope. It
never crosses alone as an authorizing receipt and does not create a second
verification policy.

Exact
`ISSUE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_GENESIS_CURRENTNESS_ATTESTATION`
issues `AuthenticatedExternalSecurityEnforcementRootGenesisCurrentnessAttestation`
only through one per-key issuance-selector CAS whose global read condition sees
`CURRENT`, selects `PENDING_GENESIS_CURRENTNESS_ISSUANCE` and sees that exact
pending entry and pending authorization bundle. It cannot consume or infer an
active-entry authorization receipt. The successor records the consumed one-use
genesis nonce, fixed validity, envelope digest and genesis-issuance marker. The
post-CAS attestation binds that envelope, observed global security head/commit
receipt, installed issuance head/commit receipt, registry entry/version,
audience root and mirror key, nonce, source-clock incarnation, trusted issue
sample and the two fixed source deadlines.
ADR-004 local genesis consumes the pending receipt, the exact
`ProtectedRegisteredExternalSecurityEnforcementRootReceiptEnvelope`, its
`RegisteredExternalSecurityEnforcementRootPublicationManifest`, shared
registration-producer completion, delivery capsule, both scoped proofs and
passing verification. Separately, it consumes the exact
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`, its
`CrossStoreSecurityReceiptVerificationEvidence`, the matching inner
attestation, the matching durable per-key commit envelope, both selected family
manifests/capsules, the shared completion manifest and the exact qualified clock
relation before the mapped local genesis deadline. The protected envelope must select
`EPHEMERAL_AUTHORITY_WINDOW` and
`SINGLE_REGISTERED_EXTERNAL_ROOT`; its audience, operation, installed global
and child coordinates, inner-attestation digest, durable per-key
commit-envelope digest and fixed expiry must match byte-for-byte. A bare inner
attestation, bare pending receipt, one family alone or durable commit envelope
alone cannot satisfy local genesis. The pending-registration envelope digest and
verification evidence in the currentness payload must equal the separately
verified registration hierarchy; nesting a digest does not replace that
producer's proof.
It always installs the local root and imported mirror deny-only in
`PENDING_SOURCE_CONFIRMATION`. It emits the exact parent-installation, initial
mirror-transition and outer-root commit receipts. A historical pending receipt,
local allocation, or source `CURRENT` head cannot install local authority.

An active entry has authority only with one exact
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationReceipt`. The
receipt binds the registered key and entry version, exact installed global
security head/commit receipt, semantic digest and security epoch, default-deny
manifest membership for the owner, role, source, audience, store and local
selector incarnation, and its receipt-free commitment in the installed entry.
Its closed origin is
`INITIAL_SOURCE_CONFIRMATION |
PLANNED_SUCCESSOR_REAUTHORIZATION |
EMERGENCY_RECOVERY_REAUTHORIZATION`. An entry is currently reauthorized only
when the receipt's security epoch and semantic digest equal the installed
`CURRENT` head, that head authentically descends from the receipt head without
changing this entry's authorization commitment, and the exact manifest
membership still passes. A predecessor-semantic receipt, registry state alone or
broad role membership cannot substitute.

Receipt-free `ExternalDerivedAuthorityLocalWorkLineageCommitment` is constructed
before any grant whose final local key includes the future grant digest. It
binds realm, registered root, stable grant-lineage incarnation, issuance
sequence, allocated grant sequence, target role/operation, target installation-
plan member, preallocated specialized-receipt identity and
`ExternalSecurityDerivedAuthorityTargetProjection`. A
`TRUSTED_DELIVERY_BOUNDARY` commitment also binds the registered immutable
no-install-reserve commitment and distinct slot whose one-based index equals
the allocated grant sequence; every other role binds typed inapplicability. It
excludes the grant digest, full local work key, candidates and receipts. The
per-target plan and sealed grant bind it. The installed full local key later
derives from it plus the grant digest; emergency/terminal closure maps the
commitment bijectively to that key or an exact no-install tombstone.

One source operation can target one or more registered external roots.
Before it builds the grant core, the source derives the exact target roster and
constructs one `RealmSecurityDeadlineConditionIntentSetRoot`. The set contains
exactly one `CURRENTNESS_ENVELOPE_VALIDITY_NOT_AFTER` intent per target and no
other realm-security intent. Each member binds the event/operation, source
store, expected global and target-child read coordinates, target ledger
predecessor, currentness-envelope digest and fixed exclusive expiry. Its key is
the registered external-root key. Omitted, duplicate, extra, reused,
cross-target or equality-at-expiry input rejects.

Receipt-free `ExternalSecurityDerivedAuthorityGrantCore` fixes the shared
operation, authority semantics, exact target roster and that deadline-intent
root before any per-target plan while excluding the target set, sealed source
object, result commitment, candidates and receipts.
`ExternalSecurityDerivedAuthorityTargetProjection` is the canonical
least-authority projection of that core for one registered target. It binds the
target key, registered role and exact permitted authority tuples. The closed
role rule is `OBSERVER_ADMISSION_EXACT_SCOPE |
TRUSTED_DELIVERY_BOUNDARY_MEMBER_SCOPE |
REGISTERED_ROLE_EXACT_SCOPE`. Observer admission receives only the complete
observer-authorized scope. A delivery boundary receives only tuples whose
delivery-boundary member is that exact root and only its registered
release/history operations. Another role must select its exact default-deny
manifest projection function. No projection can grant another target's route,
plane, operation or local-work identity.
Receipt-free `ExternalSecurityDerivedAuthorityGrantTargetSetCommitment` is the
canonical bounded set of exact registered keys and one
`ExternalSecurityDerivedAuthorityGrantPlan` per key. Each member binds the same
grant core and its own audience, target projection, unique deadline intent,
local-work identity, currentness bundle, ledger predecessor, allocated
exclusive-next sequence, preallocated specialized-receipt identity and closure
mode. The set proves the exact role-specific projection cover: every requested
authority tuple appears in every role for which it is required, no target gains
an unauthorized tuple, and no required target or tuple is omitted. The set root
and members exclude candidates and receipts. Duplicate, missing, extra,
cross-operation, swapped-projection or overlapping-boundary members reject; a
single-target operation uses a one-member set.

`ExternalSecurityDerivedAuthorityGrantReadConditionSet` contains one shared
global cut plus one exact per-target currentness read and grant-ledger write
condition, and binds the exact deadline-intent root. One qualified source
transaction rechecks every read, evaluates every intent at its authorization
linearization point and installs the source operation and every target ledger
successor or none. The exact
`RealmSecurityDeadlineConditionEvaluationSetRoot` is bound by the common
transaction receipt, source-selector receipt, every generic ledger receipt,
specialized grant receipt, receipt-set root, grant-append family manifest and
shared completion manifest; no candidate binds that post-linearization result.

After the generic commits, each specialized
`ExternalSecurityDerivedAuthorityGrantReceipt` is created. Source-local
`ExternalSecurityDerivedAuthorityGrantReceiptSet` then binds a canonical
bijection from the target set to every specialized receipt, target projection,
generic ledger commit and the common source-transaction coordinate. It is a
non-crossing set commitment, not a protected cross-store receipt and not an
authority artifact. Only after that root exists does each target's
`ProtectedSecurityAuthorityCommitReceiptEnvelope / GRANT_APPEND` bind its own
member, target projection and common source-transaction coordinate under
`SINGLE_REGISTERED_EXTERNAL_ROOT`. Exact aggregate roots/counts remain
source-local in the complete-set guard, pre-manifest private opening and
retention record. After the family and completion manifests authenticate, the
selected `CrossStoreProtectedOutputDeliveryCapsule` carries exactly the
recipient's envelope plus its fixed-shape family-member and family-set proofs.
Only a separately authorized exact-topology capsule branch can additionally
carry either scope's opening; immutable envelopes and manifests never change
privacy shape. A recipient receives no sibling receipt or projection. The source-side complete-set guard,
`ExternalSecurityDerivedAuthorityGrantAppendPublicationManifest` family and
mandatory completion bind every target envelope. If the complete target set cannot fit the registered
transaction/byte bounds and precharged closure reserves, planning rejects; it
cannot stage a partially authorizing subset.

Every new source-side grant that allocates derived authority for an external
enforcement root uses one
`ExternalSecurityDerivedAuthorityGrantReadCondition`. This condition is the
closed conjunction of the exact
`SecurityAuthorityGlobalCutReadCondition /
ACTIVE_ENTRY_AUTHORITY_OPERATION` and a read of the matching
`InstalledExternalSecurityCurrentnessIssuanceSelector`, installed child head,
latest issuance commit receipt, durable commit envelope and unexpired
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`, matching inner
attestation, both currentness family manifests/capsules and their shared
completion manifest. Those artifacts must select
this registered key, current authorization receipt, operation, global head and
child head byte-for-byte and verify under the installed source policy. The same
serializable source transaction validates both reads and compare-and-swaps the
matching `InstalledExternalSecurityDerivedAuthorityGrantLedgerSelector` at the
grant linearization point.

A later operation that activates or dispatches an already allocated
multi-target grant does not append that ledger again. It uses one receipt-free
`ExternalSecurityDerivedAuthorityActivationReadConditionSet`: the exact shared
global-cut read in `ACTIVE_ENTRY_AUTHORITY_OPERATION` plus a canonical member
for every target projection. Each member binds the registered key/role,
issued-plan currentness coordinate, exact latest same-global-head descendant
issuance coordinate, current registration and manifest-authorization receipts,
protected attestation and final manifest, and passing verification. The
descendant can refresh freshness only; changed global head, authorization,
role, projection or semantic/security state rejects.
The set binds the complete target-set root/count, activation operation and a
distinct `RealmSecurityDeadlineConditionIntentSetRoot` containing exactly one
`CURRENTNESS_ENVELOPE_VALIDITY_NOT_AFTER` intent per selected latest envelope.
Each intent binds that envelope's fixed expiry and selected coordinates. The
activation set structurally forbids a grant-ledger write or allocation and
cannot reuse the issuance-time deadline-intent root.

The activation source transaction validates this complete read set at the LIVE
linearization point. The receipt-free activation commitment and every LIVE
candidate bind the expected
`ExternalSecurityDerivedAuthorityActivationReadConditionSet`, never its later
validation result. The common transaction receipt, activation-set receipt,
per-target envelopes and final manifest bind the passing commit-time read
validation, exact `RealmSecurityDeadlineConditionEvaluationSetRoot` and installed
coordinates. Strict-before is required for every member; equality rejects. A
target refresh that wins first must appear as the exact
allowed descendant; activation that wins first fixes its verified set. A global
cut or incompatible child change that wins first makes activation lose. One
target omitted, duplicated, stale, swapped or verified only at grant issuance
rejects.

Before that transaction, receipt-free
`ExternalSecurityDerivedAuthorityGrantPlan` binds the exact registered key,
`REGISTERED_ACTIVE` entry/version, activation receipt, current-manifest
authorization receipt, global and child coordinates, protected currentness
artifacts, its unique deadline intent and common intent-set root, expected prior
grant-ledger head/version, prior `next_grant_sequence`, allocated sequence,
preallocated specialized-receipt identity, target projection, requested
authority, the local-work commitment's delivery no-install-reserve
commitment/slot or typed inapplicability, and one closed
`ExternalSecurityDerivedAuthorityGrantClosureMode`:
`FINITE_ENFORCED_FINAL_BOUNDARY |
LOCAL_TERMINAL_CLOSURE_REQUIRED`. The finite branch binds
`derived_authority_final_boundary_not_after` and its exact enforcement proof.
That boundary includes every action, effect, callback, publication, delivery
and retry that the grant can derive. Checked arithmetic and the qualified
derivation policy must prove it is no later than the
`FINITE_CONSERVATIVE_HORIZON` already stored in the read child head. The
terminal-closure branch is legal only for a child head carrying
`LOCAL_TERMINAL_EVIDENCE_REQUIRED`; it structurally forbids a time field and
binds the exact bounded open-work lineage and role-specific local closure-
partition identity. No elapsed-time claim is made.
Every ADR-004 distributed-closure member binds this exact plan mode.
`DEADLINE_ELAPSED_UNACKNOWLEDGED` is legal only for
`FINITE_ENFORCED_FINAL_BOUNDARY` and must prove that same enforced boundary;
`LOCAL_TERMINAL_CLOSURE_REQUIRED` forbids elapsed closure. Authorization closure
can still record exact local terminal evidence, but its marker remains open until
the role-completion event installs the matching no-work/quiescence close.
For a delivery target, the read condition also proves that allocated sequence
is at most the registered reserve cap and that its deterministic slot index is
the same value. This checks immutable source registration state, not the remote
local store. Retry selects the same slot; mismatch or cap-plus-one rejects
before semantic allocation.

The installed grant receipt binds the plan, passing combined read condition and
complete deadline-evaluation-set root,
prior/installed ledger heads, ledger-selector commit receipt, common source
transaction receipt, receipt-free
`ExternalSecurityDerivedAuthoritySourceResultCommitment` and the source
selector's post-CAS commit receipt; it excludes the later
protected envelope and source-local receipt set. After that set commits the
complete specialized-receipt bijection, the durable
`PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT / GRANT_APPEND` envelope binds
that target's receipt, projection, membership proof and audience. The final
persistence manifest binds the set and all target envelopes. The installed
ledger successor increments its version and exclusive-next sequence exactly as
specified above. A finite append creates or raises
`ExternalSecurityDerivedAuthorityFiniteBoundarySummary`; a terminal append
preserves that summary and inserts the exact lineage in
`OpenLocalTerminalClosureRequiredGrantLineageSetRoot` for the terminal branch. A
finite child operation cannot extend the installed boundary. A terminal-closure
child cannot escape or replace its retained work lineage and must appear in the
external root's complete fence/terminal/isolation partition. Exact retry returns
the same ledger successor and receipts; a changed plan under the same operation
rejects.

The source-result commitment is fixed after the per-target plans/set and sealed
source object, but before every source and ledger candidate. It binds that
sealed object, exact deadline-intent root, all preallocated specialized-receipt
identities and the exact source-subsystem successor projection while
excluding candidates, installed heads and receipts. The source and ledger
candidates bind it; target plans bind only the earlier grant core. The source selector's generic commit receipt follows
the common transaction receipt and excludes every specialized grant receipt,
envelope, receipt set, response and manifest. The exact post-CAS order is common
transaction receipt, generic source/ledger commits, specialized receipts,
source-local receipt set, per-target protected envelopes, optional source-local
non-authorizing aggregate/result and persistence manifest. Any issuance-stage aggregate is
optional,
source-local and non-authorizing. It cannot represent role acceptance or LIVE
state; a role-specific accepted response requires that role's later installed
activation guard. Thus a specialized grant receipt
can prove both source and target-ledger installation without either installed
head binding that later receipt.

Retirement, PREPARE or emergency therefore conflicts with grant issuance in one
source-store order, while concurrent attestation issuance conflicts through the
per-key selector. If a finite grant wins first, its entire derived lifetime is
already contained by the captured child-head horizon and recorded ledger
maximum. If a terminal-closure grant wins first, the captured ledger set and
permanent marker make time-based closure ineligible and the later complete local
closure partition must account for its exact lineage. If either restrictive cut
or child refresh wins first, the stale grant condition loses. A semantic digest,
epoch, registry entry or attestation without both exact selector reads and the
ledger write is insufficient.

Every event that closes marker lineages first constructs receipt-free
`ExternalSecurityDerivedAuthorityGrantLineageCloseCommitment`. It binds the
enclosing source event/operation, exact prior ledger head/open-set root, affected
members, matching closed evidence and terminal state. Its closed scope is
`WHOLE_REGISTERED_ROOT_OPEN_SET | EXACT_ROLE_COMPLETION_SET`. The first covers
every open lineage. The second covers exactly the completed source-grant/role
members. Its direct source PENDING-to-TERMINAL branch binds the receipt-free
ADR-004 `ObserverGrantPendingNeverLiveClosureCommitment`, including the source
terminal projection, namespace preimages and complete affected target-marker
set; it cannot bind the post-CAS
`ObserverGrantPendingNeverLiveClosureProof`. Its remote role-completion branch
instead binds one closed
`ExternalSecurityDerivedAuthorityRoleCompletionSourceFact`:
ADR-004 `ObserverGrantRoleCompletionRecordingFact` for an observer;
ADR-004 boundary-aggregation fact for delivery quiescence/no-install;
the role's manifest-owned completion fact; or its qualified isolation fact.
The observer fact contains the exact audience-protected local completion/
no-install evidence, final publication manifest and passing verification, prior
target-history role product, plan/grant key, expected ledger marker,
deterministic successor projection and idempotency operation. Every other
branch binds its corresponding exact protected evidence, manifest,
verification and role-owned state projection. A cross-role fact or evidence
union member rejects. Both source branches preserve all open siblings. The close
commitment excludes candidates, installed heads, post-CAS proofs, receipts,
protected output envelopes and manifests.

An emergency, retirement or domain-drain finalizer that acts on an earlier
captured open-marker root also constructs exact
`ExternalSecurityDerivedAuthorityCapturedMarkerClosurePartition`. It is a
canonical bijection from every captured member to one closed disposition:
`STILL_OPEN_CLOSE_IN_THIS_TRANSACTION |
COMPATIBLY_CLOSED_BY_ROLE_AFTER_CAPTURE`. The first requires that exact member
to remain open in the current descendant ledger and places it in this
transaction's whole-root close commitment. The second requires the exact
evidence-compatible terminal member plus the intervening role-completion
lineage-close receipt, protected envelope, final manifest, common-transaction
ancestry and gap-free descent from the captured ledger head; the finalizer
preserves it byte-for-byte. A different terminal cause, missing receipt,
cross-role close, reopened member, omitted capture or extra member rejects. If
the still-open subset is empty, the finalizer performs no ledger write and
structurally forbids a new close commitment/receipt. Otherwise it closes exactly
that subset while preserving the compatible subset. The enclosing commitment,
final receipt and recovery/retirement guard bind the partition and both subset
roots.

Whole-root emergency/retirement closes in the existing joint global/ledger CAS.
It does not pretend that a different target-history selector also committed.
For an `OBSERVER_ADMISSION` member, ADR-004
`RECORD_OBSERVER_GRANT_ROLE_COMPLETION` selects one closed
`ObserverGrantRoleCompletionRecordingProfile`:
`OPEN_MARKER_JOINT_CLOSE |
ALREADY_CLOSED_TARGET_ONLY |
FINITE_NO_MARKER_TARGET_ONLY`.
The first invokes
`CLOSE_EXTERNAL_SECURITY_DERIVED_AUTHORITY_LINEAGE_FROM_ROLE_COMPLETION`, uses
`ExternalSecurityDerivedAuthorityClosureReadCondition`, and compare-and-swaps
the exact grant ledger and ADR-004 target-history entry with the role source
operation, or none. The ledger and target candidates both bind the same close
commitment; the target candidate also binds the recording fact. The
already-closed profile instead uses
`ExternalSecurityDerivedAuthorityClosedMarkerReadCondition`, preserves the exact
pending-never/emergency/final terminal marker and close receipt, and changes
only target history. The finite profile proves the plan has no ADR-009 marker
and also changes only target history. Neither target-only profile fabricates a
ledger write or lineage-close receipt.
Every other role uses its registered owner-specific recording profile and
authoritative selector in place of target history. The source transaction
requires that selector and the matching role projection; a ledger-only caller,
ADR-004 selector substituted for another role, or owner state omitted from the
operation rejects.
Direct source
PENDING-to-TERMINAL binds the complete target-ledger marker set in that same
source transaction; later protected local role completion uses the retained
source idempotency/result map. For the observer joint profile, exact post-CAS
order is the
common transaction receipt; generic
`ExternalSecurityDerivedAuthorityGrantLedgerCommitReceipt` and ADR-004
`ObserverAttachmentTargetHistoryCommitReceipt`; then sibling specialized
`ExternalSecurityDerivedAuthorityGrantLineageCloseReceipt` and
`ObserverGrantRoleCompletionRecordingReceipt`; then ADR-004 record resolution;
then the
`PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT / GRANT_LINEAGE_CLOSE` envelope
and ADR-004 role-resolution envelope.
Each specialized receipt binds its respective generic commit; the target-only
recording receipt instead binds the target commit and exact closed-marker read
condition or finite-plan proof. The retained result binds every applicable
receipt identity and exact byte string without making a candidate depend on a
future receipt.
The specialized close receipt binds the commitment, both installed coordinates
and common transaction receipt and excludes the later envelope. The envelope
binds both receipt digests and exact audience. One
`CrossStoreProducerPreManifestBundleCommitment` binds the complete joint
receipt/sidecar/envelope set. The observer joint profile has two deterministic
families:
`ExternalSecurityDerivedAuthorityGrantLineageClosePublicationManifest` owns the
ledger-close envelope and
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest` owns the
role-resolution envelope. The mandatory shared completion manifest
authenticates those two families last. The target-only observer profiles omit
the ledger receipt/envelope and ledger-close family; the same completion type
authenticates their one role-resolution family. Other roles use their
registered owner-specific role family plus the conditional ledger-close family
for a joint profile, followed by the same completion rule. No family alone
completes the producer. Exact retry returns the installed families, completion
and delivery capsules. A partial target set, stale
global read, changed evidence or receipt without sibling preservation rejects.
Complete captured-set partitioning remains mandatory for emergency and
ordinary/final retirement; only its still-open subset is closed again.
For the direct source branch, the post-CAS ADR-004
`ObserverGrantPendingNeverLiveClosureProof` binds the installed observer and
target-ledger commits plus the earlier closure commitment and completed source
terminal producer manifest. No candidate, pre-CAS close commitment or source
terminal bundle points to that proof. The first transaction installs no ADR-004
pending-never role record. Its terminal and lineage-close envelopes, shared
pre-manifest commitment, exact applicable
source-closure/boundary/ledger-close families and mandatory shared completion
exclude the later proof. ADR-004
`ADVANCE_OBSERVER_GRANT_ROLE_CLOSURE_EVIDENCE` then performs an independent
target-history CAS that consumes the proof, installs the role record and
produces its own receipt, resolution, envelope, pre-manifest commitment, one
role-resolution family manifest and mandatory completion manifest. A crash
between transactions is fail-closed and recoverable from reserved identities;
it cannot authorize checkpoint or continuation.

ADR-004 role-record writers do not mutate this global security head. Their exact
security-profile read condition permits an online write only in `CURRENT` under
the installed `ONLINE_PRIMARY` predecessor policy. It permits an offline write
only in `EMERGENCY_FENCED_RECOVERY_REQUIRED | DOMAIN_RETIREMENT_DRAIN` when the
installed policy explicitly allowlists that exact target-history-only closure
recovery or retirement event under `OFFLINE_RECOVERY_THRESHOLD`.
`PREPARED_CHANGE |
SUCCESSOR_ACTIVE_REBIND_PENDING` waits; `DOMAIN_RETIRED` is archive-only. This
is the narrow retained-evidence exception inside drain: it can add a
non-authorizing observer target-history record but cannot change a ledger,
registration, currentness, enforcement state or continuation result.

After a whole-root emergency/final-retirement close, source-local finite-horizon
close or qualified permanent isolation, ADR-004
`RECONCILE_OBSERVER_GRANT_ROLE_SOURCE_CLOSURE` is the only target-history writer
for the resulting source-closure origins. Its receipt-free
`ObserverGrantRoleSourceClosureReconciliationFact` consumes one closed
`ObserverGrantRoleSourceClosureReconciliationEvidence`:
`LOCAL_WHOLE_ROOT_RETURN |
SOURCE_LOCAL_FINITE_HORIZON_CLOSE |
QUALIFIED_PERMANENT_ISOLATION_CLOSE`. The local-return branch binds the original
external-root closure envelope and manifest plus the source's retained passing
verification. The source-local branch instead binds the commit-time elapsed
evaluation, exact capture, clock/restart ancestry,
`ExternalSecurityEnforcementRootRetirementReceipt` and retirement publication
manifest;
it is legal only for finite-plan members and advances their finite-horizon
component. The isolation branch binds the qualified role/root isolation fact
and authentication plus one closed
`ObserverGrantRolePermanentIsolationSourceOrigin`:
`ORDINARY_RETIREMENT_ISOLATION |
EMERGENCY_LOST_ROOT_ISOLATION |
DOMAIN_DRAIN_TRANSFERRED_ISOLATION`. Ordinary retirement binds the exact
`ExternalSecurityEnforcementRootRetirementReceipt` and manifest. Emergency
binds `EmergencySecurityExternalClosureObligationReceipt`, its lineage/common
commits and authenticated final manifest. Domain drain binds
`SecurityAuthorityDomainRetirementExternalObligationTransferCommitment`,
`SecurityAuthorityDomainRetirementDrainReceipt`, the final retirement receipt
and manifest. Each branch binds its exact installed ledger terminal state and
common commit and forbids the other two branches' fields. Cross-branch fields
are structurally forbidden. The
local-return and isolation branches also bind applicable installed source-local
lineage-close/common receipts and the source persistence manifest. A branch
with a closed marker binds
`ExternalSecurityDerivedAuthorityClosedMarkerReadCondition`; the finite branch
instead binds that exact retirement receipt/common commit and manifest plus exact marker
nonmembership/inapplicability; it cannot invent a lineage-close receipt. It is legal only
for the exact registered `OBSERVER_ADMISSION` key and
`OBSERVER_ADMISSION_EXACT_SCOPE` plan member. Its grant-to-target bijection binds
that role, member/projection and exact accepted-grant role-state identity; a
delivery or other registered role cannot set the observer source-closure
component. It does not
re-verify the source's outgoing lineage-close envelope under its wrong return
audience. A bounded complete affected-set partition maps each grant to exactly
one mutable target entry, already-compatible/reconciled entry,
already-published-or-advanced retained old-grant history routed archive-only, or
permanently sealed source target routed archive-only. It binds exact prior
products, the compatible append-only ADR-004 evidence-record-set union and
derived-status successor, preservation of every retained record/trust
disposition, mutable-member count, preallocated per-member
record-resolution/envelope identities, one opaque operation-scoped
role-resolution-family identity, one opaque completion identity, exact output
counts, hierarchy/retention reserve delta and operation; it excludes candidates
and receipts. For a nonempty mutable set, one target-history
transaction installs every mutable member or none and emits
`ObserverGrantRoleSourceClosureReconciliationReceipt`. Every such member's
record resolution and role-resolution envelope belong to that same maximal
producer. One pre-manifest commitment binds the aggregate receipt and exact
member-to-resolution/envelope bijection; one ADR-004 role-resolution family
manifest owns the batch and the mandatory completion authenticates that
one-family set last. A zero-mutable-member partition performs no target-history
write and emits no new receipt, protected output, pre-manifest commitment,
family manifest or completion; retained exact retry/archive disposition remains
non-authorizing. A per-member family, duplicate role-resolution family,
unexpected family, missing or second completion, or missing/duplicate/swapped
member rejects. Publication, local role
recording and permanent target sealing race on that selector. Exact retry
returns the retained result; stale, partial, wrong-origin or post-seal input is
archive-only and cannot support continuation. One sealed historical target does
not block reconciliation of another mutable target under the same registered
root. Archive-only refinement cannot recompute or change an installed
continuation-policy result.

The evidence-to-successor mapping is closed and deterministic. A current
complete local-emergency closure for an installed full work key selects
`CLOSED_BY_COMPLETE_LOCAL_EMERGENCY_FENCE`; its exact committed no-install
tombstone instead selects
`CLOSED_BY_SOURCE_COMMIT_AND_LOCAL_NO_INSTALL_TOMBSTONE`. A terminal assessment's
retained-inventory member selects `CLOSED_BY_LOCAL_TERMINAL`, while its
never-installed member selects the no-install state. The permanent-isolation
branch selects `CLOSED_BY_PERMANENT_ISOLATION` only when that branch is the
enclosing closure evidence and no installed/terminal inventory is asserted.
Direct source PENDING-to-TERMINAL with authenticated nonexistence of LIVE,
activation and response artifacts selects
`CLOSED_BY_SOURCE_PENDING_NEVER_LIVE_PROOF`. Ordinary local completion selects
one closed `ExternalSecurityDerivedAuthorityRoleCompletionEvidence`:
`DELIVERY_TRANSPORT_QUIESCENT |
OBSERVER_NEVER_INSTALLED_NO_FRAME |
OBSERVER_INSTALLED_TERMINAL_NO_NEW_ADMISSION |
MANIFEST_ROLE_NO_ACTION_COMPLETE |
LOCAL_NO_INSTALL_ZERO_WORK |
PERMANENT_ROLE_ISOLATION_COMPLETE`. Delivery binds the exact ADR-004
`ProtectedTrustedDeliveryBoundaryClosureEvidenceEnvelope /
BOUNDARY_TRANSPORT_QUIESCENCE`. Observer-never-installed binds the exact
ADR-004 `ProtectedObserverGrantRoleCompletionEvidenceEnvelope /
NEVER_INSTALLED_NO_FRAME`, terminal-observed ancestry and no-frame receipt.
Observer-installed binds that envelope's
`INSTALLED_TERMINAL_NO_NEW_ADMISSION` branch, terminal local admission
head/commit and complete no-new-admission/action partition. Another
role must use its manifest-owned, audience-protected no-action completion type;
generic terminal status is not enough. The no-install and isolation branches
bind their exact zero-work or complete no-action/no-pending-work partitions.
Every remote branch uses `REGISTERED_SOURCE_AUTHORITY` plus passing verification.
The terminal rows select `CLOSED_BY_LOCAL_TERMINAL`, no-install selects its
dedicated state, and isolation selects `CLOSED_BY_PERMANENT_ISOLATION`.
Unknown role/evidence, authorization closure alone, a terminal head without its
work partition or a bare local receipt never closes a marker.
Ordinary local final retirement permits only the terminal and no-install rows.
An overlap, mixed row, branch-incompatible state or alternative encoding
rejects. The close commitment, specialized receipt and every emergency,
retirement and domain guard bind the exact resulting complete map root.

`CONFIRM_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_LOCAL_GENESIS` is legal only in
`CURRENT`, strictly before the fixed source confirmation deadline. It consumes
ADR-004 `ExternalSecurityEnforcementRootLocalGenesisConfirmationFact`. That
receipt-free fact binds the exact parent-installation, initial mirror-transition
and outer-root commit receipts, the exact ADR-004
`ProtectedExternalCompositeStateEnrollmentReturnEnvelope /
LOCAL_DENY_ONLY_GENESIS_INSTALLATION`, its publication manifest and passing
verification. It proves that the local root is installed
deny-only under the intended owner/store/root/mirror key. The transaction
fact also preallocates the exact two-family output inventory, global and
activation-family identities, one completion identity and complete
hierarchy/retention/retry reserve. The transaction
re-evaluates exact current default-deny manifest membership and changes only that
entry from `REGISTERED_PENDING_LOCAL_GENESIS` to `REGISTERED_ACTIVE`, with an
`INITIAL_SOURCE_CONFIRMATION` authorization commitment for the installed
security epoch. It emits
`RegisteredExternalSecurityEnforcementRootActivationReceipt` and
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationReceipt` in the
same crash-complete bundle. Its global commit receipt returns only in the
`GLOBAL_SECURITY_AUTHORITY_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY` envelope.
A distinct
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope`
with closed origin
`INITIAL_SOURCE_CONFIRMATION | PLANNED_SUCCESSOR_REAUTHORIZATION |
EMERGENCY_RECOVERY_REAUTHORIZATION` binds the current-manifest-authorization
receipt and its origin-specific sibling. The initial branch binds the activation
receipt, installed registry entry/version, exact credential commitment and
authorization epoch, local confirmation fact, operation and registered-root
audience under
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`. It cannot
authorize alone. One pre-manifest commitment binds the complete receipt,
sidecar and two-envelope partition.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family and
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`
owns the current-authorization family. The mandatory shared completion authenticates the exact
two-family set last. Hierarchy retention becomes durable before either envelope
is exposed. The local root
can become authorizing only after it imports this strictly newer source
confirmation ancestry, the activation family, shared completion, two scoped
proofs, manifest-authorization receipt and a later fresh active-entry
currentness-attestation issuance head under the import rule below.
An intervening planned change, emergency or recovery makes the pending entry
terminal instead of carrying it forward; return to `CURRENT` never resurrects
predecessor admission.

`CANCEL_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`
changes a pending entry directly to `PERMANENTLY_RETIRED`. It consumes one exact
ADR-004 protected enrollment-return envelope in
`PRE_GENESIS_CANCELLATION | FINAL_RETIREMENT` payload under
`PENDING_GENESIS_BOOTSTRAP_RETURN`, with its manifest and passing verification;
it structurally forbids any activation receipt.
`EXPIRE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`
does the same at or after the fixed confirmation deadline from the source
current clock. Pending state proves that source confirmation never committed.
Its closed
`ExternalSecurityEnforcementRootNeverActivatedClosureEvidence` is
`LOCAL_PRE_GENESIS_CANCELED | LOCAL_DENY_ONLY_ROOT_FINALLY_RETIRED |
SOURCE_CONFIRMATION_DEADLINE_ELAPSED |
SOURCE_SEMANTIC_CHANGE_BEFORE_ACTIVATION |
SOURCE_DOMAIN_RETIREMENT_DRAIN_BEFORE_ACTIVATION`. The first three branches are
selected by the two current-phase events above. The semantic-change branch is
selected only by PREPARE or emergency fencing from pending state and binds the
exact predecessor entry plus new global cut. The last branch is selected only by
the domain-retirement-drain cut from pending state. They emit
`ExternalSecurityEnforcementRootNeverActivatedClosureReceipt`, retain the
registration key forever and grant no claim that an unreported local root is
absent. Confirmation, cancellation and expiry contend on the sole source
security selector; exactly one can win.

Every maximal global producer that terminalizes one or more pending entries
preallocates the canonical complete affected-entry set, one envelope identity
per member, the exact conditional family map, one completion identity and
complete hierarchy/retention/retry reserve. Its global-commit family is always
present. Its never-activated-closure family is present if and only if the
affected set is nonempty; multiple roots are members of that one deterministic
family, not separate families.
`ProtectedExternalSecurityEnforcementRootNeverActivatedClosureEnvelope` binds
one exact closure receipt, branch evidence, permanent registry tombstone,
installed global coordinate, registered-root audience, operation and replay
domain under
`PERMANENT_CLOSURE_TOMBSTONE / SINGLE_REGISTERED_EXTERNAL_ROOT`. A bare receipt
cannot cross stores. One pre-manifest commitment binds the complete global
receipt/envelope and member partition.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family and
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest` owns
the conditional per-root family. The mandatory completion authenticates the
exact one- or two-family set last, and retention becomes durable before
exposure. A zero-member cut has only the global family plus completion. Exact
retry returns the selected family, completion and two-proof capsule without
siblings.

`BEGIN_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT` changes the entry to
`RETIREMENT_PENDING` and stops new currentness attestations or source grants for
that key. Its receipt-free transition fact preallocates the exact global-commit
and retirement-pending family identities, one completion identity and complete
hierarchy/retention/retry reserve. Its global transaction compares the target's exact per-key issuance
and grant-ledger selectors/heads. It records the issuance high-water, ledger
`next_grant_sequence`, optional last-committed sequence, finite-boundary-summary
branch and exact open terminal-required lineage-set root together with the
complete derived-authority closure mode. An issuance or grant append that
linearizes first is included; one that validates after the registry write loses.
Closed `ExternalSecurityEnforcementRootRetirementPendingReceiptOrigin` is
`ORDINARY_RETIREMENT_BEGIN | PLANNED_ACTIVATION_RETIREMENT |
EMERGENCY_RECOVERY_RETIREMENT | DOMAIN_RETIREMENT_DRAIN`. Post-CAS
`ExternalSecurityEnforcementRootRetirementPendingReceipt` selects the ordinary
branch here and binds the
prior/installed global heads and entry versions, registered key, captured
issuance and ledger heads/selectors/incarnations, maximum/next/optional-last
sequence, finite summary, open-marker root, transaction receipt and operation
result. Its `DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`
`ProtectedExternalSecurityEnforcementRootRetirementPendingEnvelope` and
the `GLOBAL_SECURITY_AUTHORITY_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY`
envelope belong to the same maximal producer. One pre-manifest commitment binds
their receipts, sidecars and exact two-envelope partition.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family and
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest` owns the
retirement-pending family. The mandatory completion authenticates the exact
two-family set last, and hierarchy retention becomes durable before exposure.
The local root can therefore verify the exact source
grant cut; an event name, bare entry state or caller-copied high-water cannot
replace the protected receipt.
`FINALIZE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT` consumes one exact
`ExternalSecurityEnforcementRootRetirementClosureEvidence`. Its closed branch is
`LOCAL_EXTERNAL_ROOT_FINAL_RETIREMENT |
SOURCE_DERIVED_AUTHORITY_HORIZON_ELAPSED_NO_FUTURE_AUTHORITY |
EXTERNAL_ROOT_PERMANENTLY_ISOLATED`. The local branch
binds ADR-004 `ProtectedExternalCompositeStateEnrollmentReturnEnvelope /
FINAL_RETIREMENT`, its final-retirement receipt, authenticated manifest and
passing verification under `ACTIVE_OR_RETIREMENT_RETURN`, and the
exact still-accepted close-signing credential/qualification fixed by the source
registry entry. When the captured open marker set is nonempty it also consumes
the deterministic receipt-free ADR-004
`ExternalCompositeTerminalMarkerGrantClosureAssessment` and exact captured
marker closure partition. It jointly advances the grant ledger only for the
partition's still-open subset; an all-compatibly-closed partition forbids a
ledger write or new close receipt.
The assessment is recomputed from the already authenticated final head,
terminal inventory/no-install map, protected final-retirement receipt and
captured source set; it has no signer or envelope. A receipt under a withdrawn,
unknown or message-selected credential, partial assessment or global-only
finalization cannot close source state. The horizon branch is legal only when the captured open marker set is
empty for a
`RETIREMENT_PENDING` entry in `CURRENT` or domain drain. It binds the exact
source attestation high-water, grant sequence state, both captured heads and
finite-boundary-summary branch. `PROVED_EMPTY_NO_FINITE_BOUNDARY` uses the finite
child horizon alone; `NONEMPTY_FINITE_MAXIMUM` uses their checked maximum.
`UNMAPPABLE_HISTORICAL_MAXIMUM_LOCAL_TERMINAL_REQUIRED` is ineligible. It also binds the
source-clock retirement cut and a qualified
proof that every fixed
external authority-derivation horizon for this key is elapsed. The qualified
policy and local final boundary must bound every authority-bearing action,
effect, callback, publication, delivery and retry admitted under an attestation,
not only mirror admission. If any such derivation is unbounded, ambiguous after
the proposed horizon, or lacks final-boundary expiry enforcement, the entry is
structurally ineligible for this branch and requires exact local terminal
evidence. The horizon branch proves only that no conforming local root or delayed
attempt can exercise source authority. It does not claim local terminal state,
transport quiescence, delivery of already admitted immutable evidence or
evidence deletion. The event installs `PERMANENTLY_RETIRED`. Reply loss returns
the same retained operation and receipt. Remote absence, ordinary mirror expiry,
a local owner claim or a caller-created replacement key cannot retire or replace
the entry.

Finalization compares the exact current descendants of every issuance and
grant-ledger head captured by BEGIN. If clock restart won first, the horizon
branch binds the complete
`RealmSecurityAttestationClockRestartReceipt` ancestry and evaluates only the
mapped current-clock upper/later values. An unmappable
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` marker or historical old-clock numeric value
makes that branch ineligible. If finalization wins first, a later restart can
only preserve the permanent tombstone; it cannot remap or reopen the entry.
Stale captured heads, a skipped restart or direct comparison of an old-clock
value in the current clock rejects.

The isolation branch consumes exact protected role-specific permanent-isolation
evidence for the registered local-root incarnation and passing verification. A
plant or body role additionally requires complete physical-footprint isolation.
In `DOMAIN_RETIREMENT_DRAIN`, it also consumes either the already-closed lost
emergency obligation/receipt for that same incident and capture or the exact
transferred pending capture and domain-drain transfer commitment. The latter
binds the exact captured marker closure partition and jointly closes only its
still-open subset to `CLOSED_BY_PERMANENT_ISOLATION`; compatible post-capture
role closures are preserved with their exact ancestry. The already-closed
branch verifies its bound partition/current ledger. The same rule applies in
`CURRENT` after ordinary retirement begins, without fabricating an emergency
incident. Before the CAS, the finalization fact preallocates the exact
conditional family inventory, identities, completion identity and complete
hierarchy/retention/retry reserve. The global and retirement-tombstone families
are always present. The ledger-lineage-close family is present if and only if
the exact still-open subset is nonempty. The winning source transaction installs the permanent no-reuse
registry tombstone and a ledger successor only when the still-open subset is
nonempty. It proves isolation and source retirement, not local terminal state.

Every successful finalization branch emits one
`ExternalSecurityEnforcementRootRetirementReceipt`. It binds the selected
closure-evidence branch, prior/installed global head and registry entry, captured
issuance/grant-ledger coordinates, optional installed ledger successor/lineage
close, permanent tombstone, elapsed evaluation or protected local/isolation
evidence, captured marker partition and both subset roots when applicable,
operation and common transaction receipt. Its
`ProtectedExternalSecurityEnforcementRootRetirementEnvelope` uses
`PERMANENT_CLOSURE_TOMBSTONE / SINGLE_REGISTERED_EXTERNAL_ROOT` for the exact
retired root. The global commit envelope uses
`GLOBAL_SECURITY_AUTHORITY_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY`. When the
still-open subset is nonempty, the ledger-close envelope uses
`PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT / GRANT_LINEAGE_CLOSE` for that
registered root. One pre-manifest commitment binds the exact receipt, sidecar
and two- or three-envelope partition.
`SecurityAuthorityGlobalCommitPublicationManifest`,
`ExternalSecurityEnforcementRootRetirementPublicationManifest` and the
conditional
`ExternalSecurityDerivedAuthorityGrantLineageClosePublicationManifest` own
their separate families. The mandatory completion authenticates the exact
two- or three-family set last, and retention becomes durable before exposure.
Exact retry returns the selected family, completion and two-proof capsules.
Source-local finite-role reconciliation binds this retirement family,
completion, capsule and commit-time evaluation, not a generic “retired” status.

Registration, confirmation, never-activated closure and ordinary
registration-retirement events compare the sole security selector, increment
only `authority_state_version`, and preserve the enforcement digest and semantic
epochs. Both currentness-attestation issuance events compare that selector as a
global read fence, mutate only the matching per-key issuance selector and
preserve `authority_state_version` and both semantic epochs. The genesis
high-water is the sole one-use marker; there is no parallel Boolean with an
independent value. Active-entry issuance uses a separate positive
`currentness_attestation_sequence` that starts at 1 and increments by exactly
one for each new committed request. Registration, confirmation and
issuance are closed outside `CURRENT`. Restrictive retirement completion remains
legal in `DOMAIN_RETIREMENT_DRAIN` from the reserved closure budget.

Each active-entry issuance request binds the registered key, audience mirror,
bounded caller freshness nonce, requested validity and idempotency operation.
The bounded
`RealmSecurityCurrentnessAttestationIssuanceOperationMap` and operation-
commitment index make an exact retry return the same result; a
changed request under the same operation rejects and a retry does not advance
the sequence. The installed successor fixes the sequence, source issue time,
validity limit, exact pre-CAS envelope digest and cumulative external-authority
horizon. The payload is fixed before the CAS, and the installed head/receipt
prove whether that exact signed candidate won. The envelope must verify with the
exact attestation-signing key epoch, algorithm and use authorized by the expected
global security head. The global read condition also requires exact
`REGISTERED_ACTIVE` state and the current manifest-authorization receipt. A
message-supplied key ID, stale activation receipt or predecessor authorization
cannot select trust.

The source exposes nothing unless the complete installed bundle contains the
exact signed envelope bytes. Qualified deterministic signing material is useful
only when it is committed before publication and can reproduce those exact
bytes; a key ID, HSM audit line or promise to sign later is insufficient. Crash,
key rotation, disablement or destruction after commit therefore cannot burn a
genesis nonce or sequence while losing its only usable envelope. Exact retry
returns the retained bundle and never chooses a new signature, time or validity.

Source issue time and every source horizon use the installed
`RealmSecurityAttestationClockState` and its never-reused clock incarnation.
`APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART` is the only clock-incarnation
change. Its receipt-free `RealmSecurityAttestationClockRestartBridge` binds the
exact prior security head/receipt, old and new clock states, conversion policy,
all uncertainty inputs and one canonical complete
`RealmSecurityAttestationClockRestartMap`. Each
`RealmSecurityAttestationClockRestartMapEntry` has closed kind
`AUTHORITY_VALIDITY_CUTOFF | AUTHORITY_CLOSURE_HORIZON`. A cutoff entry covers
every pending-genesis, confirmation and active-attestation acceptance/validity
deadline. It binds the exact conservative lower/earlier image and selects
`MAPPED_TO_EXACT_LOWER_EARLIER_IMAGE`; if unavailable, it selects
`EXPIRED_OR_CANCELED_ON_RESTART` and atomically terminalizes or cancels the
affected authority. Equality with a mapped cutoff is expired.

A closure-horizon entry separately covers every
`external_authority_horizon_not_after`, nonempty grant-ledger finite maximum and
timed retirement horizon. It binds the exact conservative upper/later image and
selects `MAPPED_TO_EXACT_UPPER_LATER_IMAGE`. If unavailable, overflowing or
outside either applicability horizon, it selects
`LOCAL_TERMINAL_EVIDENCE_REQUIRED_AFTER_UNMAPPABLE_RESTART`, retains the original
tagged value as historical evidence, atomically changes that key's
`ExternalSecurityCurrentnessIssuanceHead` from
`FINITE_CONSERVATIVE_HORIZON` to permanent
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` or preserves an already installed marker
byte-for-byte, and forbids every source-horizon retirement branch for that root.
Only an unmappable ledger
`NONEMPTY_FINITE_MAXIMUM` installs the ledger summary's matching third branch.
An empty summary remains empty; a separately mapped nonempty maximum retains its
mapped branch even when another closure field caused the root marker. The
complete issuance-candidate set proves no key was omitted. A new numeric horizon
is never invented. Each entry
binds field kind/key, both clock incarnations, old value, relation, applicability
horizons, correlated uncertainty, rounding and checked result. A field used as
both cutoff and closure input has two purpose-separated entries; they cannot
merge or exchange polarity. Empty ledger summaries remain empty and forbid an
entry/value. Existing `LOCAL_TERMINAL_EVIDENCE_REQUIRED` markers, grant
sequences, lineage maps and open-marker projections remain byte-for-byte.
Conversion invents no per-grant member in
`OpenLocalTerminalClosureRequiredGrantLineageSetRoot`; the root-level marker
instead requires whole-root terminal or permanent-isolation evidence whose work
partition covers every retained lineage.

The bridge is fixed before every successor. Each child restart candidate binds
its exact prior child head, bridge and new clock state, but no global successor
or future receipt. `ExternalSecurityCurrentnessIssuanceClockRestartCandidateSetRoot`
commits the canonical complete issuance-candidate set. Each issuance candidate
binds the exact applicable per-field/per-purpose entry projection. Each numeric
field binds only its declared cutoff and/or closure-horizon kind; a dual-purpose
field binds two distinct entries. A permanent marker binds typed inapplicability
and an empty projection only for that marker's numeric closure-horizon field;
the candidate still binds all applicable validity and acceptance cutoffs. Each
grant-ledger restart candidate binds its exact prior ledger head, bridge, selected
finite-boundary-summary branch, exact upper-mapped maximum or terminal-required
result, and new clock state while preserving every sequence and lineage. The
empty-summary branch binds typed no-value/no-entry evidence, not an invented
map member. The
`UNMAPPABLE_HISTORICAL_MAXIMUM_LOCAL_TERMINAL_REQUIRED` branch retains the old
maximum with its old-clock tag and restart evidence but structurally forbids a
new-clock numeric maximum; canonical
`ExternalSecurityDerivedAuthorityGrantLedgerClockRestartCandidateSetRoot`
commits that complete ledger-candidate set. The global restart candidate binds
the bridge and both set roots. The one joint CAS installs the global successor
and every issuance and ledger successor. It emits
`RealmSecurityAttestationClockRestartReceipt` plus one
`ExternalSecurityCurrentnessIssuanceCommitReceipt` and purpose-separated commit
envelope per issuance child, plus one
`ExternalSecurityDerivedAuthorityGrantLedgerCommitReceipt` and
`PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT / CLOCK_RESTART` envelope per
ledger child. Those receipts bind their installed coordinates and the common
transaction receipt. The aggregate restart receipt binds the prior and
installed global heads/selectors, exact complete issuance and ledger
prior/installed head-selector/commit-envelope bijections, bridge, both candidate
set roots and common transaction receipt. Each issuance envelope uses
`PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / CLOCK_RESTART`; the global envelope uses
`GLOBAL_SECURITY_AUTHORITY_COMMIT`. Each pending registration terminalized by an
`EXPIRED_OR_CANCELED_ON_RESTART` cutoff emits its exact
`ProtectedExternalSecurityEnforcementRootNeverActivatedClosureEnvelope`. The
bridge/global candidate preallocates that canonical pending-terminalization set,
one closure-envelope identity per member, the
exact conditional family inventory, family/completion identities and
retention/retry reserve: the global family is always present, the currentness
family is present exactly for a nonempty issuance-child set, and the ledger
family is present exactly for a nonempty ledger-child set. The
never-activated-closure family is present exactly for a nonempty
pending-terminalization set. One
`CrossStoreProducerPreManifestBundleCommitment` binds the complete receipt,
sidecar and envelope partitions.
`SecurityAuthorityGlobalCommitPublicationManifest`,
`ExternalSecurityCurrentnessCommitPublicationManifest` and
`ExternalSecurityDerivedAuthorityGrantLedgerCommitPublicationManifest` own
their applicable commit-envelope families.
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest` owns
the conditional pending-root family. The mandatory completion
manifest authenticates the exact one-, two-, three- or four-family set last. This
one-way graph is bridge -> issuance/ledger candidates -> their set roots ->
global candidate -> commit receipts -> envelopes -> pre-manifest -> applicable
family manifests -> completion -> retention finalization; no candidate binds a
later object.

The reserve covers that worst-case joint transaction. A missing, extra, merged,
overflowing, uncertainty-erased, sibling or replayed map rejects. Without the
bridge, the source issues no new attestation and cannot use a source-horizon
retirement branch; it must obtain exact local terminal evidence or take the
higher ADR-001 isolation path. Restart time, wall time and a fresh process-local
counter cannot reset a pending deadline or prove an old horizon elapsed.
Restart is closed in `PREPARED_CHANGE` and
`SUCCESSOR_ACTIVE_REBIND_PENDING`; loss of the candidate's clock there requires
emergency fencing or domain retirement. In `DOMAIN_RETIREMENT_DRAIN`, restart is
an explicitly permitted closure-support event and cannot reopen registration,
confirmation, issuance or recovery.

The candidate also binds one
`PlannedSecurityExternalEnforcementRootSetCommitment`. Its member key,
`PlannedSecurityExternalEnforcementRootKey`, binds the planned-change core and
one exact
`RegisteredExternalSecurityEnforcementRootKey`; it cannot relabel or merge
registry entries. The set is the canonical complete registry snapshot of every
external root that can still admit, deliver, publish, invoke or mutate under an
imported predecessor mirror. A capture root that can only retain already-admitted
immutable evidence is not an enforcement root. A caller list, unregistered
mirror, omitted `REGISTERED_ACTIVE | RETIREMENT_PENDING` root or consumer claim
cannot choose the set. Each member binds its exact activation receipt.
`REGISTERED_PENDING_LOCAL_GENESIS` is excluded because its local root is absent
or deny-only and has never been able to import `CURRENT`. A retirement-pending
root remains in the set until its source tombstone commits.

Every set member must have a finite qualified complete derived-authority
horizon. A member marked `LOCAL_TERMINAL_EVIDENCE_REQUIRED` must complete exact
local final retirement and source tombstoning before PREPARE; a readiness claim
or expected future connection is insufficient. The candidate binds each captured
horizon through the nonempty summary branch. The unmappable-historical ledger
branch forces that marker and is ineligible. This gives every prepared member a
time-bounded closure fallback even if its local fence acknowledgement is later
lost. A proved-empty external set uses the no-horizon branch and never invents a
zero/default maximum.

The candidate also binds one canonical complete
`PlannedSecurityExternalEntrySuccessorDispositionMap` over every registry key.
The map root binds the planned-change core and registry snapshot, not the final
candidate.
Its closed per-entry disposition is
`PENDING_TERMINATE_NEVER_ACTIVATED_AT_PREPARE |
ACTIVE_REAUTHORIZE_UNDER_SUCCESSOR_MANIFEST |
ACTIVE_RETIRE_AT_ACTIVATION |
RETIREMENT_PENDING_PRESERVE |
PERMANENT_TOMBSTONE_PRESERVE`. The active-reauthorize branch binds exact
membership in the proposed default-deny manifest for the same owner, role,
source, audience, store, parent entry and local selector incarnation. The active-
retire branch is mandatory when that membership is absent. Pending,
retirement-pending and permanent entries cannot select an active disposition.
The map is derived from the same registry snapshot as the external set; missing,
extra, duplicated or state-inconsistent entries reject.

`PREPARE_PLANNED_SECURITY_STATE_CHANGE` installs the candidate, realm-local
affected-root commitment, external-enforcement-root commitment and complete
successor-disposition map. It compares the exact current per-key issuance head
and grant-ledger head for every active or retirement-pending external member,
fixing the attestation high-water, grant next/optional-last sequence and
finite-boundary-summary branch. Each installed selector/head/version, sequence,
terminal-required set root, component bound and derived horizon must equal its
horizon-summary tuple byte-for-byte; a nonempty marker set, newer, lower,
missing or substituted tuple makes PREPARE lose. It preserves the current
enforcement digest and both semantic epochs.
It grants no candidate-state authority. In the same global CAS, every pending
entry becomes `PERMANENTLY_RETIRED` with
`SOURCE_SEMANTIC_CHANGE_BEFORE_ACTIVATION` never-activated closure evidence.
Thus no predecessor pending registration can confirm after a return to
`CURRENT`.
The receipt-free PREPARE fact binds that canonical complete prior-pending
subset, complete external-enforcement-root set and exact per-root captured
projection. It preallocates one closure-envelope identity per pending member,
one fence-directive envelope identity per external-set member, the global
family identity, both conditional family identities, one completion identity
and complete hierarchy/retention/retry reserve. The never-activated-closure
family is present if and only if the pending subset is nonempty. The
fence-directive family is present if and only if the external set is nonempty.
`ProtectedPlannedSecurityExternalEnforcementFenceDirectiveEnvelope` binds the
global commit/head, candidate, external-set commitment, exact target
membership/projection, registered key/entry/version and local-root incarnation,
PREPARE-captured issuance/ledger heads, sequences, horizon/marker state,
operation and replay domain under
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`. It is a
non-authorizing restrictive directive. One pre-manifest commitment binds the
global envelope and exact directive/closure member partitions.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family and
`PlannedSecurityExternalEnforcementFenceDirectivePublicationManifest` owns the
conditional directive family.
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest` owns
the conditional closure family. The mandatory completion authenticates the
exact one-, two- or three-family set last. Retention becomes durable before
exposure. A root must receive its directive family, shared completion, both
scoped proofs and passing verification; the global source-history envelope
alone cannot disclose or prove its target projection.

`PREPARED_CHANGE` closes new realm-local and external root registration, source
confirmation, currentness issuance and new admission so that neither set can grow
after its snapshot. If confirmation wins first, the activated root appears in
the committed external set and disposition map. If PREPARE wins first,
confirmation loses permanently and the local deny-only root can import the
source tombstone and retire.
An already-enumerated realm-local root can finish only work admitted before
PREPARE, and only until its own quiesce transaction wins. An external root can
finish only work that its local selector admitted before it imports the prepared
source head. Preparation cannot block emergency fencing or domain retirement.

Each nonempty affected set then uses
`QUIESCE_SECURITY_AFFECTED_ROOT_FOR_PREPARED_CHANGE`. The root-specific
transaction compares the prepared security selector and the exact affected-root
selector in their common realm-local ADR-001 transaction domain. It closes new
old-state admission and reaches a non-authorizing quiescent or fenced state. Its
`PlannedSecurityAffectedRootQuiesceReceipt` binds the candidate, set commitment,
root key, prior and installed root heads, root-specific commit receipt, and exact
closed `PlannedSecurityAffectedRootQuiesceMode`:
`QUIESCENT_NO_LIVE_AUTHORITY | FENCED_NON_AUTHORIZING |
TERMINALIZED_WITHOUT_SUCCESSOR_AUTHORITY`. A receipt from another candidate,
root, version, realm, or store does not match.

Each nonempty external set then uses
`FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_PREPARED_CHANGE`. The external
root consumes the exact
`ProtectedPlannedSecurityExternalEnforcementFenceDirectiveEnvelope`, selected
`PlannedSecurityExternalEnforcementFenceDirectivePublicationManifest`, source
producer completion, capsule, both scoped proofs and passing verification. Its
closed `PlannedSecurityExternalEnforcementFenceImportMode` is
`IMPORT_NEW_PREPARED_AND_CLOSE |
CLOSE_ALREADY_IMPORTED_SAME_PREPARED_CHANGE`.
The first imports the exact authenticated source `PREPARED_CHANGE` head through
`IMPORT_AUTHENTICATED_REALM_SECURITY_SUCCESSOR` and closes in the same
sole-root CAS. The second requires that a global-history-only import already
installed the byte-identical prepared source head and `FENCED_DENY`, proves that
no planned fence receipt exists, preserves that global coordinate and closes in
a new sole-root version. A bare same-head no-op, another directive, a sibling
prepared head or changed external-set member rejects.

Both modes close every new predecessor-state admission path and partition all
already-admitted work. Their exact closed
`PlannedSecurityExternalEnforcementFenceMode` is
`QUIESCENT_NO_LIVE_AUTHORITY |
FENCED_WITH_ONLY_PREAUTHORIZED_IMMUTABLE_DRAIN |
TERMINALIZED_WITHOUT_SUCCESSOR_AUTHORITY`. The drain branch can retain only
immutable, already-released read/evidence bytes whose disclosure authorization
linearized before the local fence. It grants no new callback, release,
publication, command, mutation, physical effect, invocation, retry right or
content change. A root with any admitted authority-bearing action must close it
and use a quiescent or terminal branch before it can acknowledge the planned
fence.

This name is a closed semantic case of the registered outer root's native mirror-
update event, not a second selector mutation. For example, ADR-004 uses
`INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` or
`INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE`. The native publication receipt and the
planned external fence receipt are co-committed in the one crash-complete bundle.
An activated local root that is still deny-only pending its source-confirmation
import takes the same event as `FENCED_DENY -> FENCED_DENY`. It binds an exact
empty preauthorized-work partition and cannot fabricate predecessor authority.
Exact retry returns the one installed planned fence receipt. The two delivery
orders converge on the same mirror coordinate, work partition and receipt
semantics; only the local import version can reflect the prior fail-closed
global import.

`PlannedSecurityExternalEnforcementFenceReceipt` binds the candidate, external
set commitment and key, authenticated prepared source head/receipt, imported-
mirror transition receipt, selected import mode, exact directive hierarchy,
prior/installed sole external roots, complete preadmitted-work partition and
outer-root commit receipt. Another candidate,
mirror, realm, root, version or incomplete partition rejects. A remote receipt
without the installed local root cannot acknowledge the fence.

An external root can reach its irreversible local terminal head after source
activation but before the source begins the matching registration retirement.
It cannot and need not mutate that terminal head to import `PREPARED_CHANGE`.
Closed `PlannedSecurityExternalEnforcementClosureEvidence` is
`INSTALLED_PREPARED_FENCE | PREEXISTING_LOCAL_FINAL_RETIREMENT |
PREPARED_CAPTURED_DERIVED_AUTHORITY_HORIZON_ELAPSED`. The first branch consumes
the exact ADR-004 protected enrollment-return envelope in `PLANNED_FENCE`
payload, its manifest and passing verification. The second consumes its
`FINAL_RETIREMENT` payload under `ACTIVE_OR_RETIREMENT_RETURN`, terminal outer
head and parent tombstone for the
committed external key. It proves that the root had no successor authority
before PREPARE.

The elapsed branch binds the candidate, installed PREPARED head, exact per-key
issuance head/high-water captured by PREPARE, clock incarnation, qualified
derivation policy and a commit-bound at-or-after evaluation. It is structurally
available only when every local authority-bearing action, effect, callback,
publication, delivery and retry admitted under that high-water has a finite
enforced final boundary. Because PREPARE closes issuance, the captured horizon
cannot grow. Equality is elapsed. This branch proves only that predecessor
source authority can no longer be exercised; it does not claim local terminal
state, transport reachability or evidence deletion. A role marked
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` cannot use it. No branch accepts ordinary
mirror expiry, remote absence, a pending registration, a local owner claim or an
unsigned terminal label.

`ACTIVATE_PREPARED_SECURITY_STATE_CHANGE_AFTER_QUIESCE` consumes one closed
realm-local `PlannedSecurityActivationGuard`:

- `COMPLETE_AFFECTED_ROOT_QUIESCE_RECEIPT_BIJECTION` requires one exact receipt
  for every committed affected-root key and no extra receipt. The activation
  transaction compares every installed quiescent/fenced root named by those
  receipts.
- `PROVED_EMPTY_AFFECTED_ROOT_SET` requires the committed set to be empty and
  structurally forbids every quiesce receipt.

Activation also consumes one closed
`PlannedSecurityExternalActivationGuard`:

- `COMPLETE_EXTERNAL_ENFORCEMENT_CLOSURE_EVIDENCE_BIJECTION` requires one exact
  closed external-enforcement evidence branch for every committed key and no
  extra evidence. Every fence branch names the installed candidate-bound local
  fence. Every preexisting-terminal branch names the exact retained local
  terminal head and parent tombstone. Every elapsed branch names the exact
  PREPARE-captured issuance high-water and passing commit-bound horizon
  evaluation.
- `PROVED_EMPTY_EXTERNAL_ENFORCEMENT_ROOT_SET` requires that committed set to be
  empty and structurally forbids every external closure branch.

No authorizing change can take a direct `CURRENT -> CURRENT` path. Before the
activation CAS, its receipt-free fact derives the exact reauthorized-active and
active-retire subsets from the installed disposition map. It preallocates one
current-authorization receipt/envelope identity per reauthorized member, one
retirement-pending receipt/envelope identity per active-retire member, the exact
conditional family map, one completion identity and complete
hierarchy/retention/retry reserve. The global family is always present. The
current-authorization and retirement-pending families are present if and only
if their respective subsets are nonempty. An activation
without local quiesce or external closure evidence is legal only for the
matching proved-empty branch. An explicitly non-authorizing metadata update uses
its separate event and cannot change the enforcement digest.

Activation installs the exact candidate enforcement state. It increments
`security_epoch` by exactly one. If and only if the candidate changes the
canonical revocation set, activation also increments `revocation_epoch` by
exactly one. A nonempty affected set enters
`SUCCESSOR_ACTIVE_REBIND_PENDING`. An empty set returns directly to `CURRENT`.
The same CAS applies the complete external disposition map. Each authorized
active entry remains `REGISTERED_ACTIVE` but replaces its predecessor
authorization commitment with
`PLANNED_SUCCESSOR_REAUTHORIZATION` bound to the installed successor. Each
entry whose predecessor authorization descends from an emergency-recovery
rebind base must also carry forward the exact
`ExternalSecurityRecoveryRebindAncestryCommitment` and append this planned
activation coordinate. It cannot discard or replace that base merely because
the local root has not acknowledged rebind.
Each
active-retire entry becomes `RETIREMENT_PENDING`; retirement-pending and
permanent entries remain restrictive. Post-CAS manifest-authorization receipts
are emitted only for the exact reauthorized entries and are bound to the
installed successor head/receipt. No currentness issuance or source grant can use
an active entry until that receipt exists in the crash-complete activation
bundle.
Each active-retire member emits
`ExternalSecurityEnforcementRootRetirementPendingReceipt /
PLANNED_ACTIVATION_RETIREMENT`, binding the exact PREPARE-captured
issuance/ledger tuple, disposition member and installed successor. Its protected
retirement-pending envelope uses the existing registered-root branch.
Each reauthorized member emits
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope /
PLANNED_SUCCESSOR_REAUTHORIZATION`, binding its authorization receipt,
candidate, installed successor, exact predecessor authorization and any
required recovery-rebind ancestry.
One pre-manifest commitment binds the global envelope and the exact conditional
member partitions.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family,
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`
owns the conditional reauthorization family, and
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest` owns the
conditional retirement-pending family. The mandatory completion authenticates
the exact one-, two- or three-family set last. Retention becomes durable before
exposure. No reauthorization receipt is current-authority evidence without its
selected family, completion, two scoped proofs and a current source read.
Activation retires predecessor authority at its linearization point. NCP does not
permit an old and successor state to authorize concurrently inside that
realm-local transaction domain. Every active or retirement-pending external
enforcement root is already locally fenced, permanently terminal, or beyond the
exact PREPARE-captured complete predecessor-authority horizon. Such a root can
enable successor authority only by later importing the installed `CURRENT`
successor, current manifest-authorization receipt and fresh issuance-bound
currentness attestation through its sole selector. Thus planned activation has
no governed predecessor/successor enforcement overlap. Emergency fencing uses
the bounded asynchronous residual rule below because it cannot wait for external
acknowledgement.
`SUCCESSOR_ACTIVE_REBIND_PENDING` permits only the committed root rebind or
terminalization events, emergency fencing, and domain retirement. It cannot admit
a new root, session, grant, lease, stream, or authority-bearing operation.

After activation, each affected root uses
`REBIND_SECURITY_AFFECTED_ROOT_TO_INSTALLED_SUCCESSOR`. The event consumes a
`SecurityStateTransitionAuthorization` constructed after the installed successor
receipt. Its closed `PlannedSecurityAffectedRootRebindResult` is
`REBOUND_TO_SUCCESSOR | TERMINALIZED_WITHOUT_SUCCESSOR_AUTHORITY`. The resulting
`PlannedSecurityAffectedRootRebindReceipt` binds the exact installed root,
successor security head, candidate, affected-root key, and root-specific commit
receipt.

Activation must commit strictly before the candidate activation deadline.
Planned completion must commit strictly before its rebind deadline. Equality or
later time cannot activate or complete. If no root quiesced, the authority can
cancel an overdue candidate. Otherwise it must apply an emergency fence or retire
the realm through the guarded drain sequence below.

`COMPLETE_PLANNED_SECURITY_STATE_CHANGE_AFTER_REBIND` consumes
`PlannedSecurityAffectedRootRebindClosedSetGuard`. The guard binds a bijection
from the committed affected-root set to exact installed rebind receipts. The
transaction compares each current affected-root head named by those receipts in
the same realm-local transaction. It then moves
`SUCCESSOR_ACTIVE_REBIND_PENDING -> CURRENT` without changing either semantic
epoch. A missing, duplicate, stale, losing, or cross-candidate receipt keeps the
phase pending. The phase can still take an emergency fence or domain retirement.

`CANCEL_PREPARED_SECURITY_STATE_CHANGE_BEFORE_QUIESCE` is legal only while every
affected root still equals its committed pre-quiesce head. It removes the
candidate, preserves both epochs, and retains the authenticated cancellation
cause. Once any affected root quiesces, cancellation cannot reopen it. The
authority must activate, apply an emergency fence, or retire the domain.
An external root that already installed the prepared fence remains `FENCED_DENY`;
cancellation does not remotely reopen it. It can return to `CURRENT_IMPORT` only
after it imports the later installed cancellation head, which is a `CURRENT`
descendant with the unchanged predecessor semantic state, and separately
consumes the exact current-manifest-authorization hierarchy and a fresh
same-cancellation-head currentness producer: durable
`ProtectedSecurityAuthorityCommitReceiptEnvelope /
PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / ATTESTATION_ISSUANCE` with selected
`ExternalSecurityCurrentnessCommitPublicationManifest`, ephemeral
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope` with selected
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest`, both
capsules and scoped proofs, their shared completion, matching inner attestation,
qualified clock relation and passing verification. The protected currentness
payload's authorization-hierarchy digest must equal the separately verified
current-manifest bundle. The global cancellation head, one currentness family
or a bare attestation alone preserves `FENCED_DENY`.

Every transition that changes the current enforcement semantic-state digest
increments `security_epoch` by exactly one. Every canonical revocation-set change
increments `revocation_epoch` by exactly one. All other transitions preserve the
revocation set and its epoch.
`DECLARE_SECURITY_COMPROMISE_INCIDENT` always changes the semantic digest and
therefore increments `security_epoch`; it increments `revocation_epoch` exactly
when its cumulative classification adds a canonical revocation. Every other
transition preserves `SecurityCompromiseIncidentCumulativeStateRoot`
byte-for-byte.

`RECOVER_FROM_EMERGENCY_SECURITY_FENCE` preserves every installed revocation
and retired-key tombstone. It cannot reactivate a retired key.
`RETIRE_SECURITY_AUTHORITY_DOMAIN_FOR_REPLACEMENT` makes the old security root
terminal as part of ADR-001 realm drain. ADR-001 then consumes that exact
terminal head and receipt to close the registered local-security participant.
A parent authority enrolls the
replacement only in a distinct never-used `AuthorityRealmKey`/transaction domain
and selector; a realm never gains a second local security-currentness root. No
transition changes either domain identity.
An unknown, default, inferred, or legacy transition kind rejects.

The closed authority phases and exact root transitions are:

- `SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT`:
  `ABSENT_NEVER_USED -> CURRENT` in the participant-admission transaction;
- `INSTALL_NON_AUTHORIZING_SECURITY_METADATA_UPDATE`: `CURRENT -> CURRENT`;
- `REGISTER_EXTERNAL_SECURITY_ENFORCEMENT_ROOT`:
  `CURRENT -> CURRENT`;
- `CONFIRM_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_LOCAL_GENESIS`:
  `CURRENT -> CURRENT`;
- `APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART`:
  `CURRENT | DOMAIN_RETIREMENT_DRAIN ->` the same phase;
- `CANCEL_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`:
  `CURRENT -> CURRENT`;
- `EXPIRE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`:
  `CURRENT -> CURRENT`;
- `BEGIN_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT`:
  `CURRENT -> CURRENT`;
- `FINALIZE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT`:
  `CURRENT | DOMAIN_RETIREMENT_DRAIN ->` the same phase;
- `PREPARE_PLANNED_SECURITY_STATE_CHANGE`: `CURRENT -> PREPARED_CHANGE`;
- `CANCEL_PREPARED_SECURITY_STATE_CHANGE_BEFORE_QUIESCE`:
  `PREPARED_CHANGE -> CURRENT`;
- `ACTIVATE_PREPARED_SECURITY_STATE_CHANGE_AFTER_QUIESCE`:
  `PREPARED_CHANGE -> SUCCESSOR_ACTIVE_REBIND_PENDING | CURRENT`;
- `COMPLETE_PLANNED_SECURITY_STATE_CHANGE_AFTER_REBIND`:
  `SUCCESSOR_ACTIVE_REBIND_PENDING -> CURRENT`;
- `APPLY_EMERGENCY_SECURITY_FENCE`: exactly `CURRENT | PREPARED_CHANGE |
  SUCCESSOR_ACTIVE_REBIND_PENDING |
  EMERGENCY_FENCED_RECOVERY_REQUIRED` to
  `EMERGENCY_FENCED_RECOVERY_REQUIRED`;
- `DECLARE_SECURITY_COMPROMISE_INCIDENT`: the same source phases and destination
  as `APPLY_EMERGENCY_SECURITY_FENCE`, with its additional offline-recovery and
  cumulative-incident guards;
- `RECONCILE_EMERGENCY_SECURITY_FENCING_OBLIGATION`:
  `EMERGENCY_FENCED_RECOVERY_REQUIRED ->
  EMERGENCY_FENCED_RECOVERY_REQUIRED`;
- `RECONCILE_EMERGENCY_SECURITY_EXTERNAL_CLOSURE_OBLIGATION`:
  `EMERGENCY_FENCED_RECOVERY_REQUIRED ->
  EMERGENCY_FENCED_RECOVERY_REQUIRED`;
- `RECOVER_FROM_EMERGENCY_SECURITY_FENCE`:
  `EMERGENCY_FENCED_RECOVERY_REQUIRED -> CURRENT`;
- `BEGIN_SECURITY_AUTHORITY_DOMAIN_RETIREMENT_DRAIN`: exactly `CURRENT |
  PREPARED_CHANGE | SUCCESSOR_ACTIVE_REBIND_PENDING |
  EMERGENCY_FENCED_RECOVERY_REQUIRED` to `DOMAIN_RETIREMENT_DRAIN`; and
- `RETIRE_SECURITY_AUTHORITY_DOMAIN_FOR_REPLACEMENT`:
  `DOMAIN_RETIREMENT_DRAIN -> DOMAIN_RETIRED`.

The per-key issuance selector transitions are:

- `EXTERNAL_SECURITY_CURRENTNESS_ISSUANCE_GENESIS_FROM_REGISTRATION`:
  `ABSENT_NEVER_USED -> ISSUANCE_READY`;
- `ISSUE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_GENESIS_CURRENTNESS_ATTESTATION`:
  `ISSUANCE_READY -> ISSUANCE_READY`; and
- `ISSUE_REALM_SECURITY_CURRENTNESS_ATTESTATION`:
  `ISSUANCE_READY -> ISSUANCE_READY`; and
- joint `APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART`:
  `ISSUANCE_READY -> ISSUANCE_READY` for every extant entry.

The pending-genesis issuance edge requires the exact passing
`PENDING_GENESIS_CURRENTNESS_ISSUANCE` global-cut read condition. The active
issuance edge requires the exact passing `ACTIVE_ENTRY_AUTHORITY_OPERATION`
condition. Registration genesis is part of the joint registration CAS, and
clock restart is part of its enclosing global transaction; neither imports a
post-registration global-cut read condition. Registry retirement or a
non-`CURRENT` global phase closes each standalone issuance edge without
inventing a child phase transition.

The per-key derived-authority grant-ledger transitions are:

- joint registration genesis:
  `ABSENT_NEVER_USED -> GRANT_LEDGER_READY`;
- grant append with the exact combined read condition:
  `GRANT_LEDGER_READY -> GRANT_LEDGER_READY` in `CURRENT`;
- joint marker-lineage close with emergency reconciliation or registry
  finalization:
  `GRANT_LEDGER_READY -> GRANT_LEDGER_READY`; and
- `CLOSE_EXTERNAL_SECURITY_DERIVED_AUTHORITY_LINEAGE_FROM_ROLE_COMPLETION`
  with exact restrictive closure read:
  `GRANT_LEDGER_READY -> GRANT_LEDGER_READY`; and
- joint `APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART`:
  `GRANT_LEDGER_READY -> GRANT_LEDGER_READY` for every extant entry.

No ledger-only caller can append, close, reset or remap a lineage.

Emergency fencing atomically cancels a prepared candidate and closes new
security admission. It also terminates a pending planned-rebind phase as
authorizing state and transfers every affected root into the emergency
obligation map.

ADR-001 domain drain can preempt every operational non-retired security phase,
but it does not make this security root terminal immediately.
`BEGIN_SECURITY_AUTHORITY_DOMAIN_RETIREMENT_DRAIN` consumes the installed
ADR-001 `RETIREMENT_DRAIN_ONLY` domain head and its complete security-retirement
preparation. It cancels any prepared candidate, permanently closes registration,
confirmation, currentness-attestation issuance and recovery, installs a
restrictive enforcement state and changes every `REGISTERED_ACTIVE` entry to
`RETIREMENT_PENDING`. It terminalizes every
`REGISTERED_PENDING_LOCAL_GENESIS` entry with a never-activated source
tombstone. The one CAS binds the per-key last-issued currentness-attestation
high-water and each grant ledger's next/optional-last sequence after comparing
every extant issuance and grant-ledger selector/head from the complete registry
snapshot. It binds the open terminal-required lineage-set root, ledger clock
incarnation, exact finite-boundary-summary branch, and conservative checked
aggregate source-clock authority-derivation horizon or exact
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` marker. It also binds a
finite child horizon alone for `PROVED_EMPTY_NO_FINITE_BOUNDARY` and the checked
child/ledger maximum only for `NONEMPTY_FINITE_MAXIMUM`; the
unmappable-historical branch forces the root marker and forbids a current
comparison. It binds a canonical complete partition of every
dormant, pending or closed local
emergency entry. Each keyed
`SecurityAuthorityDomainRetirementEmergencyObligationDisposition` is exactly
`DORMANT_NOT_APPLICABLE_AT_DRAIN_CUT |
ALREADY_CLOSED_AT_DRAIN_CUT |
TRANSFERRED_PENDING_TO_PARTICIPANT_CLOSURE`. The closed branch binds its current
closure receipt. The transferred branch binds the exact matching ADR-001
participant-closure key and remains an obligation; it is not silently declared
closed.

The drain fact also binds a second canonical complete partition of every
external emergency-closure entry.
`SecurityAuthorityDomainRetirementExternalObligationDisposition` is exactly
`DORMANT_NOT_APPLICABLE_AT_DRAIN_CUT |
ALREADY_CLOSED_AT_DRAIN_CUT |
TRANSFERRED_PENDING_TO_EXTERNAL_REGISTRY_RETIREMENT`. The closed branch binds
the current external closure receipt. The transferred branch binds the exact
pending capture and
`SecurityAuthorityDomainRetirementExternalObligationTransferCommitment`, then
atomically changes that obligation entry to
`TRANSFERRED_TO_DOMAIN_RETIREMENT` while the same cut changes its registered
external entry to `RETIREMENT_PENDING`. It remains subject to the registry's
exact local-terminal, finite-horizon or permanent-isolation finalization rule;
transfer is not closure. Post-CAS
`SecurityAuthorityDomainRetirementDrainReceipt` binds that complete cut. A local
deny-only pending root never becomes active after it.

The receipt-free drain fact also binds exact prior-active and prior-pending
registry subsets and preallocates one retirement-pending receipt/envelope
identity per prior-active member, one never-activated closure-envelope identity
per prior-pending member, the exact conditional family map, one completion
identity and complete hierarchy/retention/retry reserve. The global family is
always present. The retirement-pending and never-activated-closure families are
present if and only if their corresponding subsets are nonempty. Each
prior-active member emits
`ExternalSecurityEnforcementRootRetirementPendingReceipt /
DOMAIN_RETIREMENT_DRAIN`, binding the cut and exact captured issuance/ledger
tuple, plus its registered-root protected envelope. Each prior-pending member
emits its never-activated closure envelope. The global envelope binds the drain
receipt digest in its event-specific sibling set. One pre-manifest commitment
binds the exact one-, two- or three-envelope-family partition.
`SecurityAuthorityGlobalCommitPublicationManifest`,
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest` and
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest` own
the applicable families. The mandatory completion authenticates the exact one-,
two- or three-family set last. Retention becomes durable before exposure.

`DOMAIN_RETIREMENT_DRAIN` permits only the exact participant and external
registry retirement closures selected by the drain receipt, the complete
polarity-correct attestation-clock restart needed to evaluate timed registry
closures, and final security-domain retirement. Emergency-obligation
reconciliation events have no drain-phase edge. An external active or
retirement-pending entry reaches `PERMANENTLY_RETIRED` from its exact local
final-retirement receipt, qualified elapsed-attestation-horizon proof or
protected permanent-isolation evidence under the branch defined above. Horizon
closure proves no remaining conforming source authority; isolation closure
proves loss containment. Neither pretends that a disconnected local root or
transport is terminal.

`SecurityAuthorityDomainRetirementGuard` requires the installed ADR-001 domain
phase `RETIREMENT_DRAIN_ONLY`, the still-`REGISTERED_ACTIVE`
`LOCAL_SECURITY_ENFORCEMENT` participant entry and a complete closure partition
for every other applicable participant. Every other realm-local authority
surface must be terminal, fenced non-authorizing, or represented by exact
permanent-isolation evidence. Every emergency obligation must be closed or
transferred by the exact domain-drain receipt to the same root's participant-
closure entry. Every prepared or pending-rebind affected-root key must appear in
that partition. The guard cannot require the security participant or security
head to be terminal before this event; that would create a closure cycle.
Every external registry entry must be `PERMANENTLY_RETIRED`, with its exact
never-activated, local-terminal, elapsed-horizon or permanent-isolation closure
receipt. The guard
also requires every external emergency entry to be inapplicable, already closed
at the drain cut or transferred by the exact drain receipt to that same key's
now-final external registry retirement. It binds the exact current security head, participant entries, closure
receipts, source clock/high-water evidence and ADR-001 reserve state.

Only `RETIRE_SECURITY_AUTHORITY_DOMAIN_FOR_REPLACEMENT` consumes that guard and
installs `DOMAIN_RETIRED` and emits
`SecurityAuthorityDomainRetirementReceipt`. It is the last local security event.
It cannot leave a pending obligation that requires the retired selector. The
next exact ADR-001 event is
`TERMINALIZE_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT`; it consumes that
terminal security head and receipt and changes only the matching
`LOCAL_SECURITY_ENFORCEMENT` entry to `TERMINAL_RETAINED`. ADR-001 can finalize
the domain only after that participant closure commits. A missing closure
remains in drain forever or routes through the higher ADR-001 full-envelope loss
path. Neither event can be reversed in that authority domain.

The counter effect is part of each event, not an implementation choice:

- fresh participant-admission genesis installs authority-state version 1,
  security epoch 1, and
  revocation epoch 1;
- metadata update, external-root registration/confirmation/retirement,
  currentness-attestation issuance, attestation-clock restart, prepare, cancel,
  planned completion, and obligation reconciliation preserve the enforcement
  digest and both semantic epochs;
- planned activation increments `security_epoch` and increments
  `revocation_epoch` only for a canonical revocation-set change;
- emergency fencing, recovery and domain-retirement drain increment
  `security_epoch`;
- emergency fencing increments `revocation_epoch` if and only if it changes the
  canonical revocation set;
- compromise declaration increments `security_epoch`, monotonically advances
  the cumulative incident root and increments `revocation_epoch` if and only if
  it adds a canonical revocation;
- recovery increments `revocation_epoch` if and only if its non-widening delta
  adds at least one canonical revocation; otherwise it preserves both the exact
  revocation set and epoch;
- domain-retirement drain preserves the installed revocation set and
  `revocation_epoch`; and
- final domain retirement preserves both semantic epochs and the installed
  revocation set.

Every session descriptor, stream declaration, authority lease, observer grant,
authenticated envelope, and receipt binds the exact security-state digest and
security epoch and verifies that state through installed-head ancestry or an
exact former-current transition where historical interpretation is permitted.
Each realm-scoped object also directly binds the exact neutral
`AuthorityRealmKey`; route text or transitive security ancestry cannot replace
that field. Only the installed current head in that exact realm can authorize new
admission.

Every realm-local admission, authorization, release, publication, or mutation
that relies on this security state must serialize with the locally installed
security-authority selector. Receipt-free
`LocalSecurityCurrentnessConditionProjection` is a non-authoritative typed
ADR-001 `PreCASAuthoritySemanticCommitment` inside the one common
`AuthorityTransactionCASCondition`; it is not a second CAS or currentness root.
It binds exact realm/operation/authority scope, transaction-store identity,
security-authority domain/lineage incarnation, authority-state version, security
epoch, revocation epoch, semantic/installed-head digests and selector
incarnation/version. Those values come from authenticated installed state and a
strictly prior `SecurityAuthorityStateCommitReceipt`; a grant, payload or
consumer cannot synthesize them. The common condition compares that exact
selector/head/version while advancing the complete applicable participant set.
The projection excludes the common condition, candidates and current/future
receipts; candidates bind the projection and common condition. If the security
fence is subordinate content of the operation's sole composite root, that exact
registered selector is still named as the security participant. Separate
before/after checks do not implement this rule.

In `PREPARED_CHANGE`, the projection also binds the candidate, affected-root
commitment, and exact root key. Only a root in that committed set can finish
predecessor work before its quiesce wins. In
`SUCCESSOR_ACTIVE_REBIND_PENDING`, only the exact planned rebind or
terminalization event can pass. A generic phase check cannot substitute for
these event-specific conditions.

This common-condition rule applies only when every named selector is registered
in the same realm-local ADR-001 transaction domain and store incarnation. It
applies to body operations and to provider-internal observer-grant, boundary or
receiver surfaces only when each exact selector is qualified and enrolled in
that common store. ADR-004 standalone delivery and observer roots are external
and use the imported rule below. A descriptor or revocation root used by local
grant authorization is subordinate to the sole composite or is compared in that
same transaction. A remote response, external consumer selector, cross-store
prepare, or distributed saga cannot enter the participant set. Without the
common local transaction, that realm-local authority surface is closed.

An enforcement or capture boundary outside the source realm store uses an
asynchronous imported-state rule. Its sole installed admission/authorization
root embeds one bounded `ImportedRealmSecurityMirror` for each accepted
`ImportedRealmSecurityMirrorKey`. The key binds the source
`AuthorityRealmKey`, security-authority domain and lineage, and importing
boundary/store incarnation. The mirror is subordinate content of that sole root.
It is not a second selector, a remote currentness oracle, or a source-authority
head.

The mirror binds the latest accepted authenticated source authority-state
version, source head and commit receipt, semantic digest, both source epochs,
retained ancestry, local import version, and a trusted local monotonic expiry
deadline. Its closed
`ImportedRealmSecurityMirrorState` is
`CURRENT_IMPORT | FENCED_DENY | RETIRED`.
Every mirror mutation consumes one closed
`ImportedRealmSecurityMirrorTransitionEvidence`:
`GENESIS_EVIDENCE |
POST_GENESIS_REGISTERED_ENTRY_CURRENTNESS_PRODUCT`.
`GENESIS_EVIDENCE` contains exactly one
`ExternalCompositeStateEnrollmentImportedSecurityGenesisEvidence`, whose two
named fields are the distinct registration and genesis-currentness bundles
below. It is legal only from typed mirror-key absence in
`IMPORTED_REALM_SECURITY_MIRROR_GENESIS_FROM_AUTHENTICATED_SOURCE_RECEIPT`.
The post-genesis branch contains exactly one
`ImportedRealmSecurityRegisteredEntryEvidence` and one
`ImportedRealmSecurityCurrentnessEvidence`; it structurally forbids every
genesis-only bundle, pending outer-role field and typed-absence assertion.
No generic product decoder can reinterpret one branch as the other.

`IMPORTED_REALM_SECURITY_MIRROR_GENESIS_FROM_AUTHENTICATED_SOURCE_RECEIPT`
requires typed mirror-key absence and the same two completed bundles defined by
the source-genesis contract above. The registration bundle contains the pending
`RegisteredExternalSecurityEnforcementRootReceipt`,
`ProtectedRegisteredExternalSecurityEnforcementRootReceiptEnvelope`, selected
`RegisteredExternalSecurityEnforcementRootPublicationManifest`,
registration-producer completion, delivery capsule, both scoped proofs and
passing verification. The distinct currentness bundle contains the matching
`AuthenticatedExternalSecurityEnforcementRootGenesisCurrentnessAttestation`,
`ProtectedSecurityAuthorityCommitReceiptEnvelope /
PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / ATTESTATION_ISSUANCE`,
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`,
selected `ExternalSecurityCurrentnessCommitPublicationManifest` and
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest` families,
both family capsules, their shared currentness-producer completion, both scoped
proofs for each selected member, passing verification and the exact qualified
clock relation. The ephemeral envelope must be the unexpired
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT` branch for this
operation and audience. Its installed global/child coordinates, durable
per-key commit-envelope digest, inner-artifact digest and expiry must match the
durable sibling and imported objects byte-for-byte. The root key, mirror key,
owner, store incarnation, nonce and pending registry version must also match
byte-for-byte. One family, one producer's completion for the other, a bare
receipt or a digest of either bundle rejects. The
mapped local genesis and confirmation deadlines must be strictly future at the
local CAS. Genesis always installs `FENCED_DENY` at local import version 1 and
the outer role phase `PENDING_SOURCE_CONFIRMATION`, even though the authenticated
source head is `CURRENT`. It cannot install `CURRENT_IMPORT`.

`IMPORT_AUTHENTICATED_REALM_SECURITY_SUCCESSOR` accepts only a strictly newer
descendant from the same source realm/domain/lineage. A skipped source version
requires the complete bounded authenticated ancestry from the installed source
head to the imported head, including each exact management-authorization and
commit-receipt envelope under its historical verification policy. A sibling,
rollback, gap, changed realm, changed lineage, wrong-purpose signature or
unreceipted head rejects.

Distinct `REFINE_IMPORTED_REALM_SECURITY_MIRROR_WITH_SAME_HEAD_ROOT_EVIDENCE`
accepts no global successor. It requires the byte-identical already imported
global head and one newly verified root-specific restrictive hierarchy that was
not present in the prior mirror. `RETIREMENT_PENDING_HIERARCHY` preserves
`FENCED_DENY` and installs its exact origin/captured per-key coordinate.
Either permanent-closure hierarchy routes through
`RETIRE_IMPORTED_REALM_SECURITY_MIRROR`. The event advances the sole outer
selector and local import version once while preserving the global coordinate.
It selects `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` and cannot consume current
authorization, any currentness field or a bare directive. It cannot acknowledge
planned/emergency closure by itself. Exact retry returns the installed receipt;
stale, sibling, duplicate-different or wrong-root refinement rejects.

The mirror also binds the latest accepted head/version in its registered
per-key issuance lineage. `REFRESH_IMPORTED_REALM_SECURITY_MIRROR_CURRENTNESS`
requires a strictly newer issuance descendant while the global coordinate is the
same accepted `CURRENT` head. A global successor import requires an issuance
head created against that exact successor before it can install
`CURRENT_IMPORT`. Global ancestry never orders two issuance heads, and issuance
ancestry never substitutes for a global semantic transition. A rollback, sibling
or gap on either coordinate rejects.

Closed `ImportedRealmSecurityRegisteredEntryEvidence` is
`PENDING_REGISTRATION_HIERARCHY |
CURRENT_AUTHORIZATION_HIERARCHY |
RETIREMENT_PENDING_HIERARCHY |
NEVER_ACTIVATED_PERMANENT_CLOSURE_HIERARCHY |
ACTIVE_RETIREMENT_PERMANENT_CLOSURE_HIERARCHY |
NO_ENTRY_PROJECTION_FENCE_ONLY |
GLOBAL_DOMAIN_RETIRED_WITHOUT_ENTRY_PROJECTION`. It is an authenticated input
sum, not a decoded registry-state enum. Unknown/default evidence and mixed
variant fields reject.

Closed `ImportedRealmSecurityCurrentnessEvidence` is
`COMPLETE_CURRENTNESS_HIERARCHY |
NO_CURRENTNESS_HIERARCHY_FENCE_ONLY`. The complete branch contains the exact
durable and ephemeral families, their capsules and scoped proofs, shared
completion, passing verification, matching inner attestation and qualified
clock relation defined below. The fence-only branch contains no currentness
field, digest, family, capsule, proof, completion, attestation or clock
relation. It lets an importer install an authenticated newer global/root state
and immediately deny when currentness is unavailable. It grants no window and
cannot preserve the prior local deadline. A partial, malformed, expired,
mismatched or mixed hierarchy is neither branch and rejects; it is never
reclassified as intentional absence.

`PENDING_REGISTRATION_HIERARCHY` fixes the exact registration envelope, selected
family, producer completion, capsule, both proofs and verification above.
`CURRENT_AUTHORIZATION_HIERARCHY` fixes
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope`,
its selected
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`,
producer completion, capsule, both proofs, passing verification and exact closed
authorization origin. `RETIREMENT_PENDING_HIERARCHY` fixes
`ProtectedExternalSecurityEnforcementRootRetirementPendingEnvelope`,
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest`, producer
completion, capsule, both proofs, passing verification and one exact
`ExternalSecurityEnforcementRootRetirementPendingReceiptOrigin`.

`NEVER_ACTIVATED_PERMANENT_CLOSURE_HIERARCHY` fixes
`ProtectedExternalSecurityEnforcementRootNeverActivatedClosureEnvelope`,
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest`,
producer completion, capsule, both proofs, passing verification and exact
never-activated origin. `ACTIVE_RETIREMENT_PERMANENT_CLOSURE_HIERARCHY` fixes
`ProtectedExternalSecurityEnforcementRootRetirementEnvelope`,
`ExternalSecurityEnforcementRootRetirementPublicationManifest`, producer
completion, capsule, both proofs, passing verification and exact retirement
closure branch. Every root-specific variant uses
`SINGLE_REGISTERED_EXTERNAL_ROOT` and must match the mirror key, root/store
incarnation, source head, entry version and origin byte-for-byte.

`NO_ENTRY_PROJECTION_FENCE_ONLY` contains only the exact authenticated global
source-history hierarchy for a non-retired source head and structurally forbids
every root-specific field. It can install or preserve `FENCED_DENY`, but cannot
claim an entry state, capture a per-root high-water, acknowledge a planned or
emergency directive, retire a root or reopen authority.
`GLOBAL_DOMAIN_RETIRED_WITHOUT_ENTRY_PROJECTION` contains exact authenticated
global `DOMAIN_RETIRED` ancestry and also forbids every root-specific field. It
can install `RETIRED` because the entire source domain is terminal; it makes no
per-root closure claim.

For `POST_GENESIS_REGISTERED_ENTRY_CURRENTNESS_PRODUCT`, the installed mirror
state is this closed product:

| Authenticated source/evidence product | Installed result |
|---|---|
| `DOMAIN_RETIRED` plus `GLOBAL_DOMAIN_RETIRED_WITHOUT_ENTRY_PROJECTION` | `RETIRED` |
| Any source phase plus either exact permanent root-closure hierarchy | `RETIRED` |
| `CURRENT` plus `CURRENT_AUTHORIZATION_HIERARCHY` plus `COMPLETE_CURRENTNESS_HIERARCHY` | `CURRENT_IMPORT` |
| `CURRENT` plus `CURRENT_AUTHORIZATION_HIERARCHY` plus `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` | `FENCED_DENY` while retaining the exact authenticated root state |
| `CURRENT` plus pending or retirement-pending hierarchy plus `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` | `FENCED_DENY` |
| `PREPARED_CHANGE | SUCCESSOR_ACTIVE_REBIND_PENDING | EMERGENCY_FENCED_RECOVERY_REQUIRED | DOMAIN_RETIREMENT_DRAIN` plus any non-permanent exact variant plus `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` | `FENCED_DENY` |
| Any non-retired source head plus `NO_ENTRY_PROJECTION_FENCE_ONLY` plus `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` | `FENCED_DENY` without an entry-state claim |

An impossible pair rejects. Missing root evidence never defaults to an entry
state. Complete currentness is forbidden with a non-`CURRENT` source phase, a
pending/retiring/permanent/no-entry root variant, or a same-head restrictive
refinement. The importer can still take a global fail-closed fence through the
explicit no-projection and no-currentness variants.
`GENESIS_EVIDENCE` never enters this product. Its event-specific rule above
always installs `FENCED_DENY / PENDING_SOURCE_CONFIRMATION` until the distinct
source confirmation transition wins.

`CURRENT_IMPORT` requires source phase
`CURRENT`, `CURRENT_AUTHORIZATION_HIERARCHY`, the matching unexpired
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`, its passing
`CrossStoreSecurityReceiptVerificationEvidence`, the matching inner
`AuthenticatedRealmSecurityCurrentnessAttestation`, and
`QualifiedRealmSecurityImportClockRelation`. The complete currentness hierarchy
also contains the matching
`ProtectedSecurityAuthorityCommitReceiptEnvelope /
PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / ATTESTATION_ISSUANCE`,
selected `ExternalSecurityCurrentnessCommitPublicationManifest` and
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest` families,
both family capsules and scoped proofs, and their one shared producer completion.
Both envelopes and both families must pass verification. The protected
installed-attestation envelope must select
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT`, match the exact
operation, audience, installed global/child coordinates, inner-attestation
digest, durable per-key commit-envelope digest and expiry, and remain unexpired
at the local CAS. It also requires the exact current-
manifest authorization receipt/hierarchy carried by the inner attestation to
match the separately verified `CURRENT_AUTHORIZATION_HIERARCHY`. The durable
commit envelope proves ancestry but grants no window; the ephemeral envelope
alone is an incomplete maximal producer. Neither can satisfy this product alone.
The first such import
requires the exact
`RegisteredExternalSecurityEnforcementRootActivationReceipt` for the source
confirmation transition, global ancestry from that confirmed head to the
attestation's observed global head, and per-key issuance ancestry from its
registered genesis head to the installed attestation-issuance head. It changes
the local outer role out of
`PENDING_SOURCE_CONFIRMATION`.

`PENDING_REGISTRATION_HIERARCHY` or `RETIREMENT_PENDING_HIERARCHY` installs or
preserves `FENCED_DENY` regardless of an otherwise operational source phase.
`PREPARED_CHANGE`, `SUCCESSOR_ACTIVE_REBIND_PENDING`,
`EMERGENCY_FENCED_RECOVERY_REQUIRED`, and `DOMAIN_RETIREMENT_DRAIN` also install
or preserve `FENCED_DENY`; global ancestry alone uses
`NO_ENTRY_PROJECTION_FENCE_ONLY` and cannot label a root entry.
Either exact permanent root-closure hierarchy installs `RETIRED`.
`DOMAIN_RETIRED` can install `RETIRED` through its distinct global-only variant.
The most restrictive applicable result wins. An unknown phase, evidence variant
or impossible combination rejects. A descendant can always make local state
more restrictive with authenticated global ancestry alone; it cannot claim a
per-root state, acknowledge a directive, retire one root early, or install or
extend authority without the exact root-specific hierarchy.

`FENCE_IMPORTED_REALM_SECURITY_ON_EXPIRY_OR_UNCERTAINTY` changes
`CURRENT_IMPORT -> FENCED_DENY`. Equality with the local expiry deadline takes
the fence. An authenticated newer descendant can move `FENCED_DENY ->
CURRENT_IMPORT` only through
`IMPORT_AUTHENTICATED_REALM_SECURITY_SUCCESSOR` and only when that source head is
`CURRENT` and the same-head issuance-bound attestation and clock relation pass.

`REFRESH_IMPORTED_REALM_SECURITY_MIRROR_CURRENTNESS` preserves the source head
semantic digest and both source semantic epochs, but it advances to a strictly
newer per-key issuance head.
`ISSUE_REALM_SECURITY_CURRENTNESS_ATTESTATION` creates that head through one
per-key issuance-selector CAS whose global read condition sees `CURRENT`,
selects `ACTIVE_ENTRY_AUTHORITY_OPERATION`, and sees the mirror key's exact
`REGISTERED_ACTIVE` entry and current-manifest authorization bundle. Pending
registration evidence cannot satisfy this profile. Its successor records the
committed request nonce, next exact `currentness_attestation_sequence`, fixed
validity, issuance high-water and conservative source-clock
`external_authority_horizon_not_after` derived from the registered clock policy.
It also binds the exact pre-CAS signed-envelope digest. The post-CAS
`AuthenticatedRealmSecurityCurrentnessAttestation` binds that exact installed
per-key issuance head and commit receipt, observed global security head and
commit receipt, current-manifest authorization receipt, signed envelope, trusted
issue sample, validity limit, source-clock incarnation, audience mirror key,
registry version, sequence and nonce. The event cannot run for a pending,
retirement-pending, retired or stale-authorization entry.
Replay cannot extend its fixed validity limit. The winning CAS proves checked
arithmetic and fixes that limit no
later than `trusted_issue_sample +
qualified_maximum_attestation_validity`; a caller cannot supply a wider value.
The commit-bound evaluation also proves that the authorization-linearization
instant is strictly before that limit; equality publishes nothing. The source
horizon is no earlier than the latest
conforming final-boundary authority deadline that this attestation can create,
including every bounded derived action, effect, callback, publication, delivery
and retry. It monotonically retains the maximum across all issuances for the
key. Equality at that source horizon is elapsed for retirement purposes. A role
whose qualified derivation policy has no finite conservative horizon records
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` instead of a deadline; clock time can never
convert that marker into horizon closure.

The local refresh imports that strictly newer attestation-issuance head with
complete ancestry. It can refresh `CURRENT_IMPORT` or restore
`FENCED_DENY -> CURRENT_IMPORT` only when no later imported non-`CURRENT` source
head exists. It cannot preserve an old source version while moving the local
deadline, restore from a stale pre-fence head, skip an ancestry step, or change
`RETIRED`.

Every event that installs or restores `CURRENT_IMPORT`, including a strictly
newer `CURRENT` successor import, consumes that same exact issuance-currentness
proof: the durable per-key commit envelope, protected installed-attestation
envelope, `ExternalSecurityCurrentnessCommitPublicationManifest`,
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest`, both family
capsules and scoped proofs, their shared completion, passing verification,
matching inner attestation and clock relation. Every such event also consumes
the origin-matched
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope`,
its selected
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`
family, producer completion, delivery capsule, both scoped proofs and passing
verification. The initial branch binds the activation receipt; planned and
recovery branches bind their exact reauthorization ancestry. The protected
currentness payload's authorization-envelope/hierarchy digest must equal that
separately verified bundle. Every event must unwrap and compare all artifacts;
it cannot accept the inner attestation, a bare activation/authorization receipt,
one currentness family or a durable issuance-commit envelope alone.
Authenticated ancestry proves that one head descends from another. It does not
prove that the descendant remains the source tip. If the importer has already
installed a later prepared, emergency, retirement-drain or retired head, the
older issuance head cannot reopen it. If that later source transition has not
reached the importer, an unexpired earlier issuance can still authorize only
until its fixed local deadline. That bounded residual is explicit distributed
exposure, not proof of present source-tip state.

`RETIRE_IMPORTED_REALM_SECURITY_MIRROR` changes either non-retired mirror state
to `RETIRED` and retains a permanent key tombstone. Closed
`ImportedRealmSecurityMirrorRetirementEvidenceMode` is
`IMPORT_NEWER_GLOBAL_DOMAIN_RETIREMENT |
IMPORT_NEWER_ROOT_PERMANENT_CLOSURE |
REFINE_SAME_GLOBAL_HEAD_WITH_ROOT_PERMANENT_CLOSURE`. The first consumes exact
global `DOMAIN_RETIRED` ancestry. The other two consume exactly one
`NEVER_ACTIVATED_PERMANENT_CLOSURE_HIERARCHY |
ACTIVE_RETIREMENT_PERMANENT_CLOSURE_HIERARCHY`. The same-head mode is legal only
when global ancestry already installed `FENCED_DENY` without that root
projection. Every mode selects
`NO_CURRENTNESS_HIERARCHY_FENCE_ONLY`; currentness fields are forbidden. It
preserves the authenticated global coordinate, installs the
root-specific permanent evidence, advances the sole outer selector/local import
version once and cannot claim a newer source head. Same evidence is exact retry;
a stale, sibling, wrong-root, wrong-origin or second distinct closure rejects.
The same outer-root
incarnation cannot add that mirror key again. Each mirror event emits
`ImportedRealmSecurityMirrorTransitionReceipt`. The receipt binds the exact
prior and installed outer roots, mirror value, source receipt set, event, and
outer-root commit receipt.

The local import version starts at 1 and increments by exactly one for each
mirror event. An exact retry returns the installed receipt and does not advance
it. Unrelated outer-root events preserve it. The expiry deadline is no later than
both the conservative local no-later image of the attestation's fixed source
validity limit and
`trusted_local_import_time + qualified_maximum_import_lag`.
`QualifiedRealmSecurityImportClockRelation` binds distinct source/import clock
incarnations, correlated offset/rate bounds, qualification identity and source
qualification receipt, and source and target applicability horizons. Every
mapped source instant and derived local bound must remain inside those horizons.
Missing, stale, inverted, overflowing, uncertainty-erased or audience-mismatched
mapping evidence selects `FENCED_DENY`. A source monotonic instant is never
compared directly with a local monotonic instant. Equality with the local
deadline never authorizes.

An external admission or authority-bearing action compares and advances the
same sole root that contains the mirror. Therefore import-first makes an
old-state action lose. Action-first leaves an exact local admission receipt under
the earlier mirror. No transaction spans the source and external stores.
Galadriel, Haldir, Prisoma, and other external consumers use this rule unless
their exact selector is a qualified realm-local participant.

`RETAIN_PREVIOUSLY_ADMITTED_EVIDENCE_AFTER_SECURITY_FENCE` is the only
post-fence exception. Its
`PreviouslyAdmittedSecurityEvidenceRetentionCommitment` binds immutable bytes,
the exact pre-fence local admission receipt, installed mirror version, and
non-authorizing destination. It can finish a local capture, durable append, or
compaction that admission already authorized. It cannot create a new admission,
delivery, callback, publication, command, lease, grant, mutation authority, or
success claim. A retained object remains historical evidence under its
former-current source state.

These two ordering rules do not claim instantaneous CA, revocation-feed, fleet,
or external-consumer propagation. An expired, uncertain, or overdue local mirror
denies new authority. A restrictive local fence can execute only through its
separately authorized fail-safe rule. Uncertainty cannot create or preserve
active authority.

`security_epoch` is a positive, bounded, JSON-safe integer in one persisted
security authority domain. Only the enrolled security authority advances it.
Each new current enforcement semantic state uses exactly the prior epoch plus
one. Preparation preserves the prior epoch because it grants no authority and
does not change the current enforcement state. An epoch is never a UUID, wall
time, peer-provided value, or opaque value that an implementation orders
lexically. Loss of the durable
`SecurityAuthorityStateHead` or installed selector cannot reset the counter.
Recovery from that durable head/selector loss creates a separately authorized
new security authority domain, invalidates the old domain's sessions and grants,
and requires explicit re-enrollment. It is distinct from guarded
`RECOVER_FROM_EMERGENCY_SECURITY_FENCE`, which preserves the installed domain
identity and advances its state and security epochs. Counter exhaustion fails
closed and requires the same domain-replacement procedure as durable loss.

Planned security change uses this bounded sequence:

1. Construct one non-authorizing candidate and both complete root sets.
2. Install all three through `PREPARE_PLANNED_SECURITY_STATE_CHANGE`.
3. Quiesce or fence every realm-local affected root.
4. Close every active or retirement-pending external member through its exact
   installed prepared fence or preexisting local final-retirement evidence.
5. Activate only after both exact receipt bijections or their proved-empty
   guards.
6. Construct each realm-local rebind authorization from the installed successor
   receipt.
7. Rebind or terminalize every realm-local affected root under the successor.
8. Complete only after the exact realm-local rebind-receipt bijection.
9. Retain the transition, external fence, retirement and revocation records.

Candidate distribution can occur before activation, but it grants no authority.
The activation cut rejects predecessor credentials. A post-activation rebind uses
the successor authority and exact former-current ancestry. There is no
authorizing key overlap inside the realm-local enforcement root, and every
active or retirement-pending external enforcement root is deny-only or terminal
across the activation cut. A pending local-genesis registration has never gained
source authority and confirmation is closed throughout the prepared phase.

`SecurityStateTransitionAuthorization` is the canonical pre-install
authorization for one session rebind, but it is constructed only after the
security-authority successor and its commit receipt exist. It binds the
`SecurityAuthorityTransitionFact`, security authority domain, exact old
and prepared-successor semantic state digests, security and revocation epochs,
the old state's former-current ancestry, the exact installed successor
`SecurityAuthorityStateHead`, selector version and
`SecurityAuthorityStateCommitReceipt`,
session and generation, old and successor descriptor revisions and negotiation
transcripts, idempotency operation, closed planned-or-emergency mode, and exact
retirement/fencing requirements. It excludes its own digest, signature,
installation selector, and later commit receipt. Its signature proves
authorization only. It does not prove that the successor state became current.

For a continuing plant session, ADR-007 appends one
`SecurityRebindJournalRecord` under the installed prior journal head and
atomically changes the sole `InstalledBodySessionControlStateSelector`. Its
successor `BodySessionControlStateHead` binds the new descriptor/security
binding and subordinate journal head. The post-CAS
`SecurityRebindJournalCommitReceipt` proves that installation. Every historical
record remains bound to the state that was current when it committed and to the
exact rebind ancestry. A retired state is valid only for interpreting that
history. It cannot authorize new traffic or mutation.

Planned body quiescence uses the same body-session composite selector before
activation. It requires empty active-command, application-attempt, and
nonterminal ingress/fail-safe sets. It preserves retained terminal evidence.
Every body composite compare-and-swap verifies the exact security selector
version through the same qualified ADR-001 `AuthorityTransactionDomainKey` as
the parent, body, and ADR-007 jurisdiction selectors. If that transaction is
unavailable, plant command admission remains closed. A replica read or planned
stop procedure does not close the race.

Every realm-local ADR-009 event constructs one ADR-001
`AuthorityTransactionCASCondition`. The domain-state and registered
`LOCAL_SECURITY_ENFORCEMENT` participants are mandatory. PREPARE includes the
exact authoritative realm-local and registered-external root snapshots. Each
realm-local quiesce and rebind event includes its exact affected root. ACTIVATE
and planned completion include the canonical complete realm-local affected-root
participant set. The external guard contributes only authenticated receipts from
already installed independent-root fences; it never places an external selector
in the realm-local transaction. Emergency reconciliation includes the exact
obligation root or its ADR-001 lost-participant evidence.

The condition binds the common domain/store incarnation, participant
membership/ACL, read/write set, and retirement-reserve delta. Receipt-free facts
exclude the condition, candidates, and receipts. Candidates bind the fact and
condition. The winning `AuthorityTransactionCommitReceipt` precedes security and
root-specific receipts. The final non-authorizing persistence manifest attests
the complete bundle. A remote currentness response, independently committing
store, omitted participant, or incomplete receipt DAG keeps the surface closed.

The planned and emergency receipt graph is acyclic. Prior root receipts and
closed-set guards precede the new condition. For reconciliation, the
receipt-free closure commitment precedes the condition and every candidate.
The condition precedes every candidate. The common transaction receipt follows all installed candidates.
Security and root-specific commit receipts follow the common receipt.
Quiesce, rebind, or obligation-closure receipts follow the root-specific receipt
that each one attests. The persistence manifest is last. No earlier object binds
a later object in that order. A `CLOSED` map entry binds its pre-CAS commitment,
not its post-CAS closure receipt; the later closed-set guard establishes their
exact bijection.

`EmergencySecurityFencingObligationKey` binds the realm, affected-root type,
selector key, selector incarnation, and owner. The bounded
`EmergencySecurityFencingObligationMap` reserves exactly one retained entry for
each admitted realm-local root that can use security state. Each
`EmergencySecurityFencingObligationEntry` binds an expected root head,
an optional `required_fence_version`, optional
`closed_through_fence_version`, and closed
`EmergencySecurityFencingObligationState`
`DORMANT_NOT_CURRENTLY_REQUIRED | PENDING | CLOSED`.
`DORMANT_NOT_CURRENTLY_REQUIRED` structurally forbids both fence-version fields
and a current closure commitment. `PENDING` requires the exact current
`required_fence_version` and
`EmergencySecurityFenceIncidentCommitment`, and forbids
`closed_through_fence_version` and a closure commitment. `CLOSED`
preserves the incident commitment, requires both versions to be present and
equal, and binds the matching
receipt-free `EmergencySecurityFencingClosureCommitment`. That commitment fixes
the required epoch/version, expected root, closed evidence branch and exact
root-successor semantic commitment or prior isolation evidence. It excludes
every candidate, installed head, common transaction receipt and closure receipt.
The post-CAS receipt proves that the committed result installed.
The set excludes the authority-domain self selector and the security-authority
selector. Those two selectors install and own the fence. It includes every other
admitted applicable authority surface, including a dormant reserved entry for a
new root before its first emergency.

External selectors never enter that realm-local map or transaction. Instead,
the source registry owns one precharged
`EmergencySecurityExternalClosureObligationMap`. Its stable
`EmergencySecurityExternalClosureObligationKey` is the exact
`RegisteredExternalSecurityEnforcementRootKey`. Registration installs one
dormant entry before the external key can become active; the entry and its
worst-case closure-result bytes are never evicted or borrowed.

`EmergencySecurityExternalClosureObligationEntry` has closed state
`DORMANT_NOT_CURRENTLY_REQUIRED | PENDING | CLOSED |
TRANSFERRED_TO_DOMAIN_RETIREMENT`. A dormant entry
structurally forbids a required emergency epoch, captured authority tuple and
current closure commitment. A pending entry binds the exact
`EmergencySecurityFenceIncidentCommitment`, required `security_epoch`, registry
entry/state/version, per-key issuance and grant-ledger
selectors/incarnations,
installed issuance head/version/commit receipt, attestation high-water and
captured `FINITE_CONSERVATIVE_HORIZON` value or permanent
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` marker. It also binds the installed
grant-ledger head/version/commit receipt, next/optional-last grant sequence,
exact `ExternalSecurityDerivedAuthorityFiniteBoundarySummary` and exact
terminal-required lineage-set root, and forbids a closure commitment. The empty
summary branch forbids a ledger boundary value; the finite branch binds its
current-clock maximum. The unmappable-historical branch binds only its tagged
old maximum/restart evidence and forces the captured child marker, so elapsed-
horizon closure is structurally forbidden.
A
closed entry preserves that exact
capture and binds one matching receipt-free
`EmergencySecurityExternalClosureCommitment`. That commitment fixes the
selected evidence branch and all prior protected input/evidence digests or the
exact elapsed-horizon deadline intent. For a nonempty captured marker set it
binds the exact captured marker closure partition. A nonempty still-open subset
also binds the receipt-free grant-lineage close commitment; an empty still-open
subset structurally forbids that field and a new ledger write. An empty captured
set forbids both partition and close commitment. It excludes the commit-bound
evaluation, candidate, installed head, common transaction receipt and closure
receipt. The
key set is a canonical bijection with the retained external registry. Unknown,
duplicate, omitted or extra entries reject. Only the domain-drain cut can install the transferred
state. It preserves the full pending capture, forbids an emergency-closure
commitment and binds one receipt-free
`SecurityAuthorityDomainRetirementExternalObligationTransferCommitment`; the
later drain receipt proves which transfer commitment installed.

Before each first or consecutive emergency CAS, receipt-free
`EmergencySecurityFenceIncidentCommitment` binds the exact prior installed
security head/selector, event and operation, next security epoch, expected
realm-local roots, complete external registry and per-key child-head captures,
emergency semantic delta, baseline/cumulative-restriction inputs and reserve
projection. It also binds the canonical pending-registration terminalization
set, canonical captured active/retirement-pending external-directive set, one
closure-envelope identity per pending member, one emergency-directive envelope
identity per captured member, the exact conditional family inventory,
family/completion identities and hierarchy/retention/retry reserve.
The global family is always present. The incident family is present exactly for
`DECLARE_SECURITY_COMPROMISE_INCIDENT`; the never-activated-closure family is
present exactly for a nonempty pending-terminalization set. The
emergency-directive family is present exactly for a nonempty captured external
set. It excludes the successor-state commitment, every candidate,
installed head, selector version and receipt. Each projected `PENDING` local or
external obligation entry and the
`SecurityAuthoritySuccessorStateCommitment` bind this same incident digest.
Thus no entry names the head that contains it. After the CAS,
the event-specific `SecurityAuthorityStateCommitReceipt` projection binds the
incident and installed emergency head. Its
`GLOBAL_SECURITY_AUTHORITY_COMMIT` envelope authenticates that receipt. The
incident envelope is present only for declaration; one never-activated closure
envelope is present per terminalized pending root.
`ProtectedExternalSecurityEnforcementRootEmergencyFenceDirectiveEnvelope` binds
the global emergency commit/head, incident/cumulative root, required security
epoch, exact target registry entry/version and local-root incarnation, captured
issuance/ledger heads, sequences, horizon/marker state, operation and replay
domain under
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`. One such envelope
exists for every captured active or retirement-pending external root on each
first or consecutive emergency. It is restrictive and non-authorizing. One
pre-manifest commitment binds the exact envelope/member partitions.
`SecurityAuthorityGlobalCommitPublicationManifest`,
conditional `SecurityCompromiseIncidentDeclarationPublicationManifest` and
conditional
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest` and
conditional
`ExternalSecurityEnforcementRootEmergencyFenceDirectivePublicationManifest`
own their separate families. The mandatory completion authenticates the exact
one-, two-, three- or four-family set last, and retention becomes durable before
exposure.
Reconciliation and
external import require that exact post-CAS ancestry; the incident alone grants
nothing.

In this emergency section, the emergency CAS/apply mechanics cover both
`APPLY_EMERGENCY_SECURITY_FENCE` and
`DECLARE_SECURITY_COMPROMISE_INCIDENT`. The latter additionally binds and
advances the cumulative incident root under its offline-recovery authorization.
Ordinary emergency apply structurally preserves that root and cannot declare or
refine a compromise incident.

The first such emergency event creates one receipt-free
`EmergencySecurityRecoveryBaselineCommitment` from the exact last operational
pre-emergency enforcement state, authority set, restriction/revocation set,
semantic digest and epochs. Every consecutive emergency preserves that baseline
byte-for-byte. Each emergency event also binds one
`EmergencySecurityFenceSemanticDelta` and advances one
`EmergencySecurityCumulativeRestrictionCommitment`. The delta is proven
non-widening relative to the exact prior installed enforcement state: it cannot
add a principal, role, route, plane, audience, key use, profile, extension or
grant; widen validity or ACL; or remove a restriction, revocation or tombstone.
It may remove authority, add restrictions or revocations, and replace a
compromised credential only under the separately enrolled emergency-recovery
policy without changing its authority set. The cumulative commitment derives
the canonical union of every restriction/revocation installed since the
baseline and cannot remove a prior member. Unknown, incomparable or
non-canonical deltas reject.

Each emergency event derives the complete key set from the installed
participant and authority registries. It also includes every root in a prepared
or pending-rebind realm-local plan. Active external roots are not local
obligation-map members. Every `REGISTERED_ACTIVE` or `RETIREMENT_PENDING`
external entry instead becomes a pending external-closure obligation with its
exact child-head capture. Pending local-genesis roots are already deny-only.
The event installs the restrictive semantic state first
and makes each applicable local entry `PENDING`. Its
`required_fence_version` is exactly the installed emergency fence's new
`security_epoch`; it is never a caller counter. The event binds each exact
expected affected-root head, clears current closed-through state and archives
any prior closure receipt in bounded historical evidence. A consecutive
emergency strictly increases `security_epoch`, updates every applicable expected
head and rearms a dormant, pending or closed entry at that exact newer version.
The keyed map prevents duplicate obligations and unbounded per-incident append.
The same CAS rearms every applicable external entry at the new emergency epoch,
including an entry closed under an earlier emergency. Issuance and source grants
are closed before this capture. The CAS compares every captured per-key issuance
and grant-ledger selector/head, so an issuance or derived-authority grant that
linearizes first is included and one that validates after the emergency cut loses. A dormant
pending-genesis or permanently retired entry remains inapplicable and cannot be
fabricated into the captured set.

The same emergency CAS terminalizes every still-pending external registration
with `SOURCE_SEMANTIC_CHANGE_BEFORE_ACTIVATION` evidence and invalidates every
active entry's current-manifest authorization by advancing `security_epoch`.
It preserves retirement-pending and permanent tombstones. An active registry
label during the emergency is non-authorizing because the global phase is not
`CURRENT` and its authorization epoch is stale.

Participant admission reserves one local obligation entry and its worst-case
closure bytes before a local root becomes usable. External registration does
the same for its external-closure entry. If either reserve cannot cover a new
root, admission rejects or the realm enters drain-only. Emergency fencing
cannot fail because a caller omitted capacity.

`RECONCILE_EMERGENCY_SECURITY_FENCING_OBLIGATION` consumes one exact current
`PENDING` entry. Its closed `EmergencySecurityFencingClosureEvidence` union is
`EXACT_AFFECTED_ROOT_FENCED_NON_AUTHORIZING |
LOST_AFFECTED_ROOT_PERMANENTLY_ISOLATED`. The exact branch compares and fences
the root with the security selector in one realm-local transaction. The lost
branch uses the ADR-001 evidence-only disposition and its role-specific
permanent-isolation fact. A lost body or plant root requires complete physical-
footprint isolation. No branch invents an unavailable root head.

The exact branch selects one
`EmergencySecurityFencingExactRootDisposition`:
`INSTALLED_FENCE_FOR_REQUIRED_VERSION |
EXISTING_NON_AUTHORIZING_FENCE_DOMINATES_REQUIRED_VERSION |
ROOT_TERMINAL_OR_RETIRED_DRAIN_ONLY`. The dominance branch invokes no new
physical or fail-safe effect. It binds the installed fence and proves that no
later root state reopened authority.

The transition sets `closed_through_fence_version` to the exact current required
version, installs the exact receipt-free closure commitment and changes only
that entry to `CLOSED`. After the common transaction installs both candidates,
its
`EmergencySecurityFencingObligationClosureReceipt` binds the obligation key,
prior and installed security heads, required fence version, exact installed
affected-root fence or loss-isolation evidence, closure commitment, and the
common transaction receipt. Neither the installed security head nor its map
entry binds that later receipt. A stale closure receipt cannot close a rearmed
entry.

`RECONCILE_EMERGENCY_SECURITY_EXTERNAL_CLOSURE_OBLIGATION` changes exactly one
current external entry from `PENDING` to `CLOSED`. Its closed
`EmergencySecurityExternalClosureEvidence` union is:

`INSTALLED_EXTERNAL_EMERGENCY_FENCE_COMPLETE_CLOSURE |
LOCAL_EXTERNAL_ROOT_TERMINAL_COMPLETE_CLOSURE |
CAPTURED_FINITE_EXTERNAL_AUTHORITY_HORIZON_ELAPSED |
LOST_EXTERNAL_ROOT_PERMANENTLY_ISOLATED`.

The installed-fence branch consumes the ADR-004
`ExternalCompositeEmergencyAuthorityClosureReceipt` in its exact
`DURABLE_HISTORICAL_COMMIT / REGISTERED_SOURCE_AUTHORITY /
ACTIVE_OR_RETIREMENT_RETURN` protected cross-store envelope, exact
`ExternalCompositeEmergencyAuthorityClosurePublicationManifest` and passing
verification. That receipt binds the
imported emergency head, one local composite-selector CAS, and a complete
role-specific partition proving that no predecessor-authorized action, effect,
callback, publication, delivery or retry remains open or restartable. It also
binds a bijection from every captured
`OpenLocalTerminalClosureRequiredGrantLineageSetRoot` member to the exact closed
local work lineage or an exact local no-install tombstone. A missing, extra,
duplicate or bare source-grant claim rejects. Fencing new admission alone is
insufficient. An already installed complete fence can
dominate a consecutive emergency only through a fresh closure receipt that
binds the newer required epoch and proves no intervening reopen.

The local-terminal branch consumes the exact ADR-004
`ProtectedExternalCompositeStateEnrollmentReturnEnvelope / FINAL_RETIREMENT`,
parent tombstone, authenticated manifest and passing verification, plus
the deterministic receipt-free
`ExternalCompositeTerminalMarkerGrantClosureAssessment` when the captured
marker set is nonempty. That assessment bijects every source ledger member to
the terminal local inventory or proves it could never install after the
permanent terminal selector/tombstone; its authenticity derives only from those
already protected inputs and it has no post-terminal writer. The
elapsed branch is legal only for the captured
`FINITE_CONSERVATIVE_HORIZON`; its commit-bound evaluation proves the source
clock is at or after that exact captured boundary, where equality is elapsed.
It also proves that the emergency cut stopped every later issuance and source
grant for the key. The marker branch cannot select elapsed closure. The lost
branch consumes role-specific permanent-isolation evidence; a plant or body
footprint requires complete physical-footprint isolation. Remote absence,
mirror expiry, a server fence request, a local status claim or an unprotected
receipt satisfies no branch.

If the captured open marker-lineage set is nonempty, every nonelapsed branch
binds the exact captured marker closure partition. Only a nonempty still-open
subset binds `ExternalSecurityDerivedAuthorityGrantLineageCloseCommitment` and
jointly advances the grant ledger with the global emergency obligation. The
compatible subset preserves its intervening role-completion terminal states and
exact receipt/envelope/manifest/common-transaction ancestry. An all-compatible
partition forbids a ledger write and new lineage-close receipt. The obligation
receipt/guard bind the partition and current result root. The elapsed branch
requires the captured set to be empty. Only the exact role-completion event can
write a marker-lineage terminal state outside the enclosing source operation;
no generic or ledger-only close event exists.

Before that source CAS, the obligation-reconciliation fact preallocates the
exact conditional family inventory, identities, completion identity and
hierarchy/retention/retry reserve. The global family is always present. The
ledger-lineage-close family is present if and only if the exact still-open
subset is nonempty.
The winning source CAS re-compares the current installed
`EMERGENCY_FENCED_RECOVERY_REQUIRED` descendant carrying the same incident
commitment and required epoch, its post-CAS receipt/envelope, registry entry and
captured child tuple. Its
`EmergencySecurityExternalClosureObligationReceipt` binds the prior and
installed security heads, obligation key, exact capture, installed receipt-free
closure commitment, selected closure evidence, commit-bound evaluation when
applicable, protected-envelope verification when applicable, captured marker
partition and both subset roots when applicable. It binds an installed ledger
successor, new lineage-close receipt/envelope and common transaction receipt
only when the still-open subset is nonempty; otherwise those fields are
forbidden and it binds every compatible intervening close ancestry. The
`CLOSED` entry and installed security head exclude this later receipt. It grants
no external authority. Exact retry returns the same receipt; a stale closure
cannot close a rearmed entry.
The global commit envelope binds the exact event-specific obligation-receipt
digest in its complete sibling-receipt set. When the still-open subset is
nonempty, the per-key ledger-close envelope binds the lineage-close receipt and
commitment. One pre-manifest commitment binds the complete receipts, sidecars
and one- or two-envelope partition.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family and
the conditional
`ExternalSecurityDerivedAuthorityGrantLineageClosePublicationManifest` owns the
ledger-close family. The mandatory completion authenticates the exact one- or
two-family set last. Retention becomes durable before exposure, and exact retry
returns the selected family, completion and two-proof capsule.

`EmergencySecurityFencingClosedSetRecoveryGuard` binds the exact installed
obligation-map root and a bijection from every currently required key to its
post-CAS current closure receipt. Each receipt must bind the exact closure
commitment installed in its `CLOSED` entry and the same incident commitment and
required epoch. Every applicable entry must be `CLOSED` at that exact epoch. A retained entry for a root already terminal before
that emergency remains dormant and is excluded by the canonical applicable-set
derivation. The guard rejects a pending, omitted, duplicate, extra, stale,
cross-realm or cross-version entry.
`EmergencySecurityExternalClosureClosedSetRecoveryGuard` independently binds
the exact installed external-obligation-map root and a bijection from every
captured external key and installed closure commitment to its post-CAS current
closure receipt for that same incident commitment and required epoch. Across
both guards, the receipts' prior/installed security heads must form one
monotonic, gap-free chain of `EMERGENCY_FENCED_RECOVERY_REQUIRED` descendants
whose origin is the incident's installed emergency head and whose final
installed head is the guard head; each next prior head equals the preceding
installed head. The receipts need not share one head digest. When both
applicable sets are empty, both bijections and the receipt chain are explicitly
empty, and its origin and end are the same installed incident head. It rejects
one pending, omitted, duplicate, extra, stale, sibling,
cross-key, cross-incident or cross-epoch member.
For every captured nonempty marker set, the guard also re-compares the current
grant-ledger selector/head and proves the exact captured partition. It maps the
still-open-at-reconciliation subset to terminal entries and lineage-close
receipt/envelope installed by that obligation, and the compatible subset to the
retained post-capture role-completion entries and their exact protected/common
ancestry. An all-compatible partition proves no obligation ledger write
occurred. A ledger rollback, still-open lineage, wrong subset, different close
commitment or missing protected receipt blocks recovery.
Before recovery CAS, its receipt-free fact derives the exact reauthorized,
active-retire and isolation-retire subsets from the installed recovery
disposition map. It preallocates every current-authorization,
retirement-pending and permanent-retirement receipt/envelope identity, exact
conditional family map, one completion identity and complete
hierarchy/retention/retry reserve. The global family is always present. Each
root-addressed family is present if and only if its corresponding subset is
nonempty.
`RECOVER_FROM_EMERGENCY_SECURITY_FENCE` compares every available affected root
named by the local guard and consumes exact isolation evidence for every lost
local root. It also consumes both closed-set guards and re-compares the complete
external registry/obligation projection. In the same security CAS it archives
both closed-set roots and returns every retained local and external entry to
`DORMANT_NOT_CURRENTLY_REQUIRED`. It also archives the emergency baseline and
cumulative-restriction roots as historical evidence; the installed `CURRENT`
successor structurally forbids live emergency-only fields. It cannot run without
both complete guards.

Recovery preserves all installed revocations and retired-key tombstones. It
installs a new enforcement state at the next security epoch. Exact
`EmergencySecurityRecoverySemanticDelta` proves that the recovery state is a
subset of the exact
`EmergencySecurityRecoveryBaselineCommitment` authority and the currently
installed `EmergencySecurityCumulativeRestrictionCommitment`. Because each
emergency delta only accumulates restrictions, those two roots cover the
original authority ceiling and every restriction installed across consecutive
emergencies. The recovery delta cannot add a principal, role,
route, plane, audience, key use, profile, extension or grant; remove a
revocation/tombstone; or widen any validity or ACL. It can remove authority,
replace compromised credentials under the separately enrolled recovery policy,
and add revocations or restrictions. A wider operational successor requires a
later ordinary planned change authorized from the recovered state.

Recovery also consumes one canonical complete
`EmergencySecurityExternalEntryRecoveryDispositionMap`. Its closed per-entry
disposition is
`ACTIVE_REAUTHORIZE_UNDER_RECOVERY_MANIFEST |
ACTIVE_RETIRE_AT_RECOVERY |
ACTIVE_PERMANENTLY_RETIRE_AFTER_ISOLATION |
RETIREMENT_PENDING_PRESERVE |
PERMANENT_TOMBSTONE_PRESERVE`. Reauthorization requires exact membership in the
installed recovery default-deny manifest and the same entry's exact
pre-emergency current-manifest authorization; absence in either forces
retirement. It also requires that entry's current external closure branch to be
`INSTALLED_EXTERNAL_EMERGENCY_FENCE_COMPLETE_CLOSURE` or
`CAPTURED_FINITE_EXTERNAL_AUTHORITY_HORIZON_ELAPSED` and preserves the exact
registered local-root incarnation. This is source-known eligibility, not a
claim that a disconnected local root is currently live, nonterminal or
nonisolated; the later local selector CAS proves its own predecessor state. A
`LOCAL_EXTERNAL_ROOT_TERMINAL_COMPLETE_CLOSURE` branch forces
`ACTIVE_RETIRE_AT_RECOVERY` and retains its exact local finalization input. A
`LOST_EXTERNAL_ROOT_PERMANENTLY_ISOLATED` branch forces
`ACTIVE_PERMANENTLY_RETIRE_AFTER_ISOLATION`; the same recovery CAS installs the
source registry's permanent no-reuse tombstone and emits its exact retirement
closure receipt from the already verified isolation evidence. It cannot leave a
marker key stranded in `RETIREMENT_PENDING` or be selected for reauthorization.
The
recovery CAS installs fresh `EMERGENCY_RECOVERY_REAUTHORIZATION` commitments for
the authorized active subset and changes the retire subset to
`RETIREMENT_PENDING`; the isolation subset becomes `PERMANENTLY_RETIRED`.
Their post-CAS current-manifest authorization receipts
bind the installed recovery head and are retained in the same crash-complete
bundle.
Each reauthorized member emits
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope /
EMERGENCY_RECOVERY_REAUTHORIZATION`, binding its receipt, recovery head,
incident/closed-obligation ancestry, exact predecessor authorization and
recovery-rebind base. Each active-retire member emits
`ExternalSecurityEnforcementRootRetirementPendingReceipt /
EMERGENCY_RECOVERY_RETIREMENT` plus its registered-root protected envelope,
binding the captured child tuple and recovery disposition. Each isolation member
emits its protected permanent-retirement envelope and receipt under the
`EXTERNAL_ROOT_PERMANENTLY_ISOLATED` closure branch. One pre-manifest commitment
binds the global envelope and exact conditional member partitions.
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global family.
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`,
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest` and
`ExternalSecurityEnforcementRootRetirementPublicationManifest` own their
conditional families. The mandatory completion authenticates the exact one-,
two-, three- or four-family set last. Retention becomes durable before exposure.
No family alone reopens authority.

Each recovery reauthorization also begins one immutable
`ExternalSecurityRecoveryRebindAncestryCommitment`. It binds the registered key
and local incarnation, incident and closure receipt, recovery head/receipt and
recovery authorization. Every later planned-successor authorization for that
entry carries the same base plus the exact gap-free chain of intervening
planned candidate, activation head/receipt and predecessor authorization.
A later emergency starts a different incident; retirement ends eligibility.
Content-addressed checkpoints can compact the proof, but cannot omit a head,
cross an incident, change an incarnation or assert a remote rebind.

Recovery does not itself reopen an affected local or external root. A later root
rebind or imported refresh requires the fresh current-state authorization
receipt and applicable local or imported-mirror ordering rule. A root admitted
after recovery starts with one dormant reserved entry and no fabricated prior
fence or closure version.

The emergency security transition changes the local security selector first.
Every uncommitted old-state body CAS then loses, including
`START_BODY_COMMAND_APPLICATION_ATTEMPT`. No command application can begin after
that security fence. For this rule, application begins only when the exact
ADR-007 START transaction installs its attempt and invocation right. The body
obligation then installs the ADR-007 actuation-gate fence and complete
command/application partition.

A pre-fence `received` tip that was not admitted closes as `rejected`. An admitted
tip with no installed application attempt closes as `superseded`. For an already
installed attempt, only exact arbiter acceptance ordered before the affected
body's gate fence can be recorded later as `applied`. The late record consumes
the installed attempt and exact acceptance/fence-order evidence. It starts no
new application. Definitive no-effect and ambiguous outcomes use the ADR-007
closure transitions. An ambiguous outcome remains pending until it can close as
`unknown_after_boundary`.

A non-ESTOP body enters non-authorizing HOLD/fenced state or stays
`RETIRED_DRAIN_ONLY`. `RETIRED_DRAIN_ONLY` can append only evidence-derived
closure records for work accepted before the cut. `ESTOP_LATCHED` remains
latched. `ESTOP_OUTCOME_UNKNOWN` remains unknown and cannot become
`ESTOP_LATCHED`, no-effect, HOLD, or current authority by inference. Neither
security recovery nor root rebind clears either ESTOP state. ADR-007 operator
reset or inspection remains mandatory.

Normal command admission remains blocked while any body obligation is pending.
An obligation becomes closed only after the exact gate fence, command and
application partition, preserved ESTOP state, and durable closure receipt exist.
If prior state or ordering evidence is missing, the body remains fenced. Recovery
cannot use a missing receipt as evidence that no effect occurred.

Emergency revocation changes the revocation epoch, closes affected connections,
rejects retired keys when the state reaches each enforcement boundary, and
forces explicit recovery. It does not wait for planned quiescence. Until an
external boundary imports an authenticated update, its qualified propagation and
expiry bound is residual exposure during the fenced emergency. The protocol
does not erase this distributed-systems fact or call propagation an immediate
cut. Recovery nevertheless stays closed until every captured external
obligation proves complete installed closure, local terminal state, elapsed
finite authority horizon or permanent isolation. Mirror expiry cannot close a
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` key. Unknown, overdue, or rolled-back local
state fails closed.

## Low-overhead security-state reconciliation

One realm owner publishes an immutable current snapshot and one-way currentness
gate. Verified ingress receives an opaque actor capability for that snapshot.
Application code cannot split, rebuild, or revive it.

A security cut closes its predecessor before publishing a successor. Each owner
rechecks currentness before retention, release, send attempt, or executor
acceptance. No lock spans network, application, parser, or device work.

The cut and each committing owner transition have one local order. A transition
commits under the still-current opaque capability before the cut, or it rejects
after the cut. Work performed outside the owner uses a bounded in-flight
reservation and a second currentness check before its result becomes visible.
A cut marks such a reservation as draining and does not wait under the owner
lock.

The security-state projection commits accepted extension manifests, but not
their derived activation contexts. Each later activation binds its producer,
audience, realm, scope, manifest, route, package class, parser, callback,
resource, frame, and route-encoding profiles. It also binds the complete
`security_state_digest`, receiver-clock incarnation, exclusive activation
expiry, and receiver-issued activation incarnation. This order prevents a digest
cycle.

B03 derives one positive exact-opening limit from the complete canonical shell,
encoding expansion, and 1,048,576-byte frame ceiling. Boundary and overflow
tests are mandatory. Unknown inputs or unsafe arithmetic reject before
allocation. B03 cannot change opening or disclosure semantics.

A runtime can replace the detailed proof graph with bounded local state and one
atomic owner transition only when all observable results remain unchanged.

## Rejected alternatives

- Digest raw file bytes while ignoring semantic equivalence or included files.
- Accept a known `kid` without exact current manifest and key epoch.
- Continue a session across security-state change with only a warning.
- Let predecessor and successor security states authorize concurrently inside
  one enforcement root.
- Fetch keys or trust state from message-supplied remote URLs.
- Claim one atomic compare across realm-local and external consumer stores.
- Install an authorizing nonrotation update without affected-root quiescence.
- Activate from a caller-selected subset of affected-root receipts.
- Represent emergency work with one Boolean or count instead of keyed obligations.
- Treat imported source state as current without an installed local expiry bound.
- Treat authenticated ancestry or a historical `CURRENT` receipt as proof of
  source-tip currentness.
- Make an external registration active before the exact deny-only local root is
  installed and source-confirmed.
- Downgrade `ESTOP_OUTCOME_UNKNOWN` during security recovery.
- Treat a signed transition authorization or candidate successor as proof that
  the successor state was installed.
- Scope a command journal to only the current security epoch and lose
  same-generation historical query and command-identity fencing at rotation.

## Illustrative semantic projection

```json
{
  "authority_realm": {
    "server_authority_principal": "spiffe://ncp.example/body-server",
    "stable_realm_id": "plant-a"
  },
  "profile": "ncp-production-ingress-v1",
  "security_epoch": 12,
  "revocation_epoch": 4,
  "principals": [
    {
      "principal_id": "crebain-body-a",
      "role": "body",
      "planes": [
        "control",
        "action",
        "observation"
      ]
    }
  ],
  "key_epochs": [
    {
      "kid": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "algorithm": "Ed25519",
      "epoch": 3
    }
  ]
}
```

## Invalid or hostile example

```json
{
  "profile": "production-secure",
  "algorithm": "EdDSA",
  "kid": "current",
  "security_epoch": "00000000-0000-4000-8000-00000000000c",
  "revocation_epoch": 0
}
```

Ambiguous algorithm, mutable key name, UUID-typed security epoch, and missing
realm and semantic membership reject.

## Actors and state transitions

`ABSENT_NEVER_USED --SECURITY_AUTHORITY_STATE_GENESIS_FROM_TRUST_ROOT_ENROLLMENT-->
CURRENT(epoch 1)` commits only with the domain participant entry and reserve.

Nonempty planned path:

`CURRENT(epoch n) --PREPARE_PLANNED_SECURITY_STATE_CHANGE-->
PREPARED_CHANGE(epoch n)
--ACTIVATE_PREPARED_SECURITY_STATE_CHANGE_AFTER_QUIESCE-->
SUCCESSOR_ACTIVE_REBIND_PENDING(epoch n+1)
--COMPLETE_PLANNED_SECURITY_STATE_CHANGE_AFTER_REBIND-->
CURRENT(epoch n+1)`.

Proved-empty planned path:

`PREPARED_CHANGE(epoch n)
--ACTIVATE_PREPARED_SECURITY_STATE_CHANGE_AFTER_QUIESCE-->
CURRENT(epoch n+1)`.

Cancellation path:

`PREPARED_CHANGE(epoch n)
--CANCEL_PREPARED_SECURITY_STATE_CHANGE_BEFORE_QUIESCE-->
CURRENT(epoch n)`.

Emergency path:

`ANY_OPERATIONAL_NON_RETIRED_PHASE(epoch n)
--APPLY_EMERGENCY_SECURITY_FENCE-->
EMERGENCY_FENCED_RECOVERY_REQUIRED(epoch n+1)
--RECONCILE_EMERGENCY_SECURITY_FENCING_OBLIGATION*-->
EMERGENCY_FENCED_RECOVERY_REQUIRED(epoch n+1)
--RECONCILE_EMERGENCY_SECURITY_EXTERNAL_CLOSURE_OBLIGATION*-->
EMERGENCY_FENCED_RECOVERY_REQUIRED(epoch n+1)
--RECOVER_FROM_EMERGENCY_SECURITY_FENCE-->
CURRENT(epoch n+2)`.

Any operational phase can instead enter
`DOMAIN_RETIREMENT_DRAIN(epoch n+1)`, then `DOMAIN_RETIRED(epoch n+1)`.
The two starred edge families can interleave in any order. Recovery requires
both exact closed-set guards. Domain retirement requires the separate
retirement guard.

External registration handshake:

`ABSENT --REGISTER_EXTERNAL_SECURITY_ENFORCEMENT_ROOT-->
REGISTERED_PENDING_LOCAL_GENESIS
-- local deny-only genesis -->
LOCAL_PENDING_SOURCE_CONFIRMATION
--CONFIRM_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_LOCAL_GENESIS-->
REGISTERED_ACTIVE
--ISSUE_REALM_SECURITY_CURRENTNESS_ATTESTATION-->
REGISTERED_ACTIVE(new per-key issuance head)
-- fresh-attested import of that confirmation descendant -->
LOCAL_CURRENT_IMPORT`.

PREPARE closes source confirmation. If it wins first, the pending local root
is permanently retired, stays deny-only until it imports that tombstone, and is
excluded from the planned external set. If confirmation wins first, the active
key is included and the installed local root must supply its exact planned-fence,
preexisting-terminal or captured elapsed-horizon closure branch.

Planned external imported-mirror path:

`CURRENT_IMPORT(source version n)
--IMPORT prepared source successor / planned external fence-->
FENCED_DENY(source version n+1)
--IMPORT installed CURRENT activation or cancellation descendant-->
CURRENT_IMPORT(source version n+k)`.

The import requires a complete authenticated ancestry for every positive `k`.
Every arrow that installs `CURRENT_IMPORT` also requires a fresh, audience-bound
issuance-currentness attestation and qualified clock relation.
`REFRESH_IMPORTED_REALM_SECURITY_MIRROR_CURRENTNESS` preserves the semantic
digest, both semantic epochs and the global source authority-state version. It
advances the per-key issuance-head version and local import version.
Expiry or uncertainty moves `CURRENT_IMPORT -> FENCED_DENY`. Only a matching
current global source head, currently authorized registry entry, newer per-key
issuance head, exact unexpired currentness and clock evidence can return it to
`CURRENT_IMPORT`.

No message can self-advance security or recovery epochs.
Implementations compare `security_epoch` numerically only after bounded JSON-safe
integer validation. They compare session, stream, grant, ledger, and receiver-clock
incarnations only for opaque exact equality.

## Bounds and resource behavior

Principal, route, key, root, revocation, extension, digest-input, candidate,
affected-root, mirror, ancestry, connection-close, rebind, obligation, closure,
audit, and verification work are finite. Implementations apply item, byte,
depth, and transaction-participant limits before semantic allocation.

Projection and every keyed set are canonical and duplicate-free before hashing.
The realm-local affected-root and emergency-obligation maxima cannot exceed the
qualified ADR-001 participant and transaction-byte bounds. The external-
enforcement receipt-set maximum must also fit the activation transaction byte
bound, although its selectors are not participants. If one complete activation,
completion, or recovery compare cannot fit, candidate preparation or participant
admission rejects. An implementation cannot split that compare into a saga.

An imported mirror accepts a bounded ancestry batch. A consumer can install
multiple contiguous batches, but it stays deny-only between them. Source
retention or checkpoint proof must preserve a bounded authenticated path from the
installed mirror head. Missing proof keeps the mirror fenced.

External registration reserves the source entry, pending/active/retirement
receipts, per-key issuance and grant-ledger selectors/heads, issuance
high-water, grant next/optional-last sequence and finite-boundary-summary branch,
complete marker-lineage close set, complete
clock-restart participation, one dormant external emergency-obligation entry,
one emergency-apply mutation, one authority-state/CAS position and complete
receipt/envelope bytes for its reconciliation, its recovery-guard membership,
and its worst-case planned/emergency/domain-drain transfer and closure bytes
before it emits the pending receipt. Both source deadlines are fixed at
registration and bounded by policy. Pending expiry can reclaim only explicitly
temporary queue, work-buffer and scratch capacity after its terminal bundle is
durable. It cannot reuse or remove the registry key/entry/tombstone, registry or
child selectors, issuance/grant-ledger lineages and counters, operation/replay
evidence, external-obligation key, no-install positions or anti-ABA reserve.
Those retained objects count against the configured lifetime registration
count/byte cap. Cap exhaustion denies new registration in that registry. Further
capacity requires planned drain and replacement by a distinct source authority
domain/registry through normal re-enrollment; a new root incarnation inside the
full registry is insufficient. No path recycles an old slot. Thus delayed
confirmation, activation or issuance replay still meets the permanent tombstone
and exact used lineages.

Registration also reserves a hard maximum count and byte budget for per-key
currentness-issuance operations and their canonical signed results. A new
request cannot commit if it would consume the last retirement position or exceed
that budget. Exact query/retry remains available from qualified retained or
content-addressed archive storage; an implementation cannot silently evict an
operation ID and issue a different sequence. Before exhaustion, the source
retires that external key and, if needed, enrolls a distinct never-used root.
Counter or archive pressure cannot reset the key, sequence or authority horizon.
Per-key issuance queues and rates are bounded. The source transaction manager
reserves admission and commit capacity for global restrictive writes and does
not admit an issuance while doing so could exhaust the proven maximum time or
work needed by PREPARE, emergency, target retirement, clock restart or domain
drain. Exact cap and cap-plus-one schedules are conformance inputs.

Registration separately reserves a hard maximum count/byte budget for grant
append operations, specialized results, protected envelopes, retained lineage
entries and exact queries. Each open marker lineage precharges its worst-case
complete close member and ledger/global joint-CAS bytes before append. Grant
append cannot consume the last close, emergency, retirement or clock-restart
position. Exact-cap append succeeds; cap-plus-one rejects before semantic
allocation. Closure capacity is never released until the retained terminal
entry and no-reuse evidence exist, and archive loss cannot reset the grant
sequence state or permit a different result.

The local obligation map has at most one key per admitted affected root, and the
external map has exactly one key per retained external registration. A newer
emergency rearms existing keys instead of appending incident entries.
Participant admission and external registration reserve their respective
closure positions and bytes before use. Retained historical receipts use
bounded content-addressed checkpoints without removing any live, pending,
transferred, no-reuse, or recovery-guard evidence.

Security epoch, revocation epoch, authority-state version, issuance-head
version, currentness-attestation sequence, grant-ledger version,
`next_grant_sequence`, present `last_committed_grant_sequence`, bounded
operation/result counters and mirror import version are positive JSON-safe
integers. Grant-ledger genesis has next 1 and absent last. A committed append
allocates prior next, stores that value as last and advances next exactly once;
the maximum-plus-one sentinel is valid only as exhausted exclusive-next state.
Required and closed-through fence versions are absent or positive JSON-safe
integers exactly as their dormant, pending or closed shape specifies. Overflow,
wrap, skip where exact increment is required, a forbidden present/absent field
or a non-integer representation rejects before semantic allocation. Counter
exhaustion enters deny-only drain or domain replacement. It never resets a
lineage.

`SecurityAuthorityClosureReserve` holds enough authority-state and transaction
positions for one emergency fence, one local reconciliation per maximum affected
root, one external reconciliation per maximum registered external root, both
complete recovery closed-set comparisons, the complete external-entry
disposition/retirement/obligation-transfer partition, one compare of every
extant per-key issuance and grant-ledger head, every precharged marker-lineage
close, one worst-case clock mapping and terminal domain retirement. It also reserves the maximum receipts, protected envelopes,
verification evidence and persistence-manifest bytes for those positions.
From an emergency head, its closed continuation budget selects exactly one of:
all required reconciliations plus one recovery CAS and a successor reserve that
still covers a future emergency/drain, or the domain-drain transfer and terminal
path. Recovery rejects if it cannot install that replenished successor reserve;
it cannot borrow the terminal branch. Normal metadata, prepare, activation,
completion and issuance cannot consume either closed continuation. Before a
semantic epoch reaches the
point that leaves no emergency or retirement-drain increment, normal transition
enters domain drain. Final domain retirement preserves both semantic epochs.

After the reserve boundary, a newer external incident cannot weaken or reopen the
installed fence. The higher ADR-001 realm root performs full-envelope isolation
and retirement if the local security root has no position for another incident.
External audit retention can record the cause, but it cannot claim a new local
revocation state. Mirror import-version bounds similarly reserve one deny fence
and terminal mirror retirement.

## Threat and hazard analysis

This addresses key/algorithm confusion, manifest rollback, stale grants,
candidate activation before quiescence, imported-mirror rollback, revoked-key
continuation, omitted emergency roots, and partial reconfiguration. It also
prevents a late evidence write from becoming new authority.

Emergency revocation can reduce availability, force HOLD, preserve an unknown
ESTOP outcome, or leave a body in drain-only. Those operational hazards require
testing. Key custody, CA compromise, trusted time, source retention, and signed
provenance remain external gates.

## Formal properties

- Equal semantic state produces equal digest in every implementation.
- A changed authorizing member changes the digest.
- A message under a retired security/revocation epoch is never accepted for new
  admission, authority or mutation. A durable historical commit or permanent
  tombstone remains verifiable only under its exact class, audience, retained
  former-current ancestry and compromise disposition; verification grants no
  current authority.
- A protected object with identical principal/session/generation/security epochs
  and bytes but a different `AuthorityRealmKey` never reuses a local security
  head, replay entry, grant, receipt or semantic lineage.
- A current enforcement semantic-state change increments `security_epoch` by
  exactly one. Preparation preserves it. The epoch is never reused, decremented,
  reset, or interpreted as a UUID in one installed domain.
- A canonical revocation-set change increments `revocation_epoch` by exactly
  one. Every transition that preserves the set also preserves its epoch.
- Authority state versions start at 1 and increment by exactly one for every
  successful security-authority compare-and-swap. A stale, sibling, repeated,
  skipped, rolled-back, exhausted or unreceipted authority version rejects.
  Security and revocation epochs do not substitute for this version.
- The first security-authority state consumes typed selector absence plus
  never-used proof and atomically installs the head, selector, participant entry
  and reserve. Its `SecurityAuthorityStateCommitReceipt` and participant-
  admission receipt depend on the one `AuthorityTransactionCommitReceipt`.
  Missing state after use cannot become a new epoch-1 genesis.
- Every non-genesis source transition is authorized by the exact predecessor
  management threshold, bounded dual-signature continuity mode or separately
  enrolled offline-recovery threshold. Commit receipts use a distinct key use.
  Currentness and enforcement keys cannot authenticate either ancestry layer.
  Successor keys prove possession before activation, predecessor issuance stops
  at the exact activation cut, and retained public verification history does not
  grant new signing authority.
- Deadline intents bind only static timing-proof profiles. Commit-time
  evaluations bind the trusted sample, instantiated proof and result. Registration
  and PREPARE cannot install expired, inverted, overflowed or infeasible
  deadlines, and a clock restart cannot re-date a prepared candidate.
- Normal signing-key retirement forbids new issuance but preserves historical
  verification. Ephemeral authority artifacts expire; durable commits and
  permanent tombstones do not. Compromise requires the closed conservative
  disposition and cannot be repaired by re-signing old bytes.
- Rebinding cannot widen a principal beyond the new manifest.
- A prepared security candidate grants no admission, signature, session, lease,
  grant, or mutation authority.
- Planned construction is acyclic:
  `PlannedSecurityStateChangeCore -> member/set/disposition roots ->
  PlannedSecurityStateChangeCandidate`. No member binds the final candidate
  digest, and no candidate can select a second encoding from the same roots.
- A metadata-only update cannot change the enforcement digest or any
  authority-bearing member.
- An authorizing planned change has no direct current-to-current edge. It
  activates only from a prepared candidate after an exact complete quiesce-
  receipt bijection or proved-empty affected set.
- The affected-root set comes from installed authoritative registries. A caller
  cannot omit, duplicate, substitute, or add a root.
- The registered external-enforcement set comes from its authoritative registry.
  It contains every active or retirement-pending entry and excludes each
  never-activated pending entry. Planned activation requires one exact installed
  local fence, preexisting final-retirement or PREPARE-captured complete elapsed-
  horizon branch for every member, or the proved-empty guard. The evidence is
  authenticated external input, not a claim that external selectors joined the
  realm-local transaction.
- External registration is source-owned anti-ABA state under the sole security
  selector and exact per-key issuance/grant-ledger selectors. It accepts the
  local allocation only through the protected bootstrap audience and passing
  verification; a bare, foreign or post-cancellation replay can create no
  active authority. Registration starts pending;
  local genesis is deny-only; source confirmation consumes the exact local
  installation and current manifest membership; and a fresh-attested
  confirmation successor alone can activate the local root. PREPARE or emergency
  terminalizes every remaining pending entry. Planned activation and emergency
  recovery apply a complete per-entry reauthorize-or-retire disposition. No
  predecessor pending or active authorization can resurrect under a successor.
  Retirement-pending stops new attestations and remains in every planned set
  until its permanent source tombstone commits.
- Every source grant, release or dispatch to an external root read-validates the
  exact active entry/current manifest authorization against the global selector
  and the exact installed per-key issuance head/currentness bundle. Its complete
  derived final boundary fits inside that already stored finite horizon, or the
  key permanently requires local terminal evidence. Retirement, child refresh
  and grant issuance have one source-store order; matching only the semantic
  digest, epoch, registry entry or attestation cannot issue a late grant. A
  multi-target grant evaluates one exact currentness-expiry intent per target,
  atomically advances every target ledger, and exposes only each target's
  least-authority projection and two membership proofs. Missing/swapped targets,
  expiry equality, sibling artifacts or a crossing aggregate reject.
- A retirement-pending external key can reach its permanent source tombstone
  from `CURRENT` without forcing source-domain retirement only after the exact
  local terminal receipt, its qualified complete derived-authority horizon or
  qualified permanent isolation. Ordinary mirror expiry, a remote absence read
  or an isolation claim without role-specific/physical-footprint proof remains
  insufficient.
- Genesis and active currentness attestations are post-CAS receipts of exact
  per-key issuance transitions. Genesis issuance read-validates the global
  security selector and exact pending entry/registration-authorization bundle
  through `PENDING_GENESIS_CURRENTNESS_ISSUANCE`. Active issuance uses
  `ACTIVE_ENTRY_AUTHORITY_OPERATION` and read-validates the exact
  active/currently-authorized entry and source manifest. PREPARE, emergency,
  retirement, grant and issuance therefore have one source-store order without
  advancing unrelated issuance lineages. A signature produced after an
  unretained read cannot create or extend authority.
- Joint registration and clock restart use receipt-free common commitments.
  Child candidates never bind the global successor; post-CAS receipts link both
  installed coordinates. Their candidate/receipt DAG is acyclic and produces an
  authenticated per-key genesis or restart edge for importers.
- Each active-entry issuance advances one exact per-key sequence. Exact
  idempotent retry returns the retained result without advancing it. A changed
  request, skipped/repeated sequence, uncommitted payload or unpublished signed
  envelope cannot create authority.
- Each grant append allocates the prior exclusive-next sequence and advances it
  once; genesis is next 1/last absent and maximum-plus-one is exhausted. Empty
  and marker-only ledgers carry no finite value. First/later finite appends
  create/raise the maximum; marker close preserves it. Restart upper-maps it or
  preserves it only as an unmappable historical value with whole-root terminal
  evidence required; it never invents an empty/current value.
- Each registration precharges a finite issuance-operation/result budget and
  preserves retirement capacity. Exact-cap issuance can commit; cap-plus-one,
  checked overflow or archive loss cannot issue, reuse an operation or reset the
  sequence.
- Source attestation-clock restart maps authority cutoffs to exact lower/earlier
  images and closure horizons to exact upper/later images while atomically
  advancing every extant per-key selector. Unmappable authority expires/cancels;
  an unmappable horizon permanently requires local terminal evidence. Without
  the complete typed map, issuance and horizon retirement are closed. Restart
  during domain drain supports closure only.
- Every affected root is non-authorizing under the predecessor before activation.
  Activation compares the exact installed heads that the quiesce receipts name.
- Activation retires predecessor authority at one realm-local linearization
  point. Prepared distribution and post-activation rebind create no authorizing
  overlap inside that domain. Every active or retirement-pending external root
  is deny-only, terminal or beyond its complete predecessor-authority horizon
  before planned activation and can enable the successor only through a later
  currently reauthorized, fresh-attested local import. An emergency cut captures
  every active or retirement-pending external key's exact child head and
  authority horizon. Recovery remains closed until each capture has one exact
  installed complete-fence, local-terminal, elapsed-finite-horizon or
  permanent-isolation closure; expiry cannot close a permanent
  `LOCAL_TERMINAL_EVIDENCE_REQUIRED` marker.
- A prepared candidate can be cancelled only while every affected root remains
  at its committed pre-quiesce head. Emergency fencing or domain retirement can
  preempt every non-retired planned phase.
- Each planned rebind authorization is constructed after the installed successor
  receipt. A recovery-descended external entry carries its immutable recovery
  base through every planned successor. Local emergency rebind accepts only the
  latest gap-free current descendant with no newer incident or retirement and
  proves its own nonterminal predecessor. A candidate, omitted head, source
  liveness guess, signature, or losing root successor cannot substitute.
- Planned completion has one exact rebind receipt for every affected-root key and
  no others. A root is either rebound to the successor or terminalized without
  successor authority.
- Emergency recovery preserves all installed revocations and retired-key
  tombstones and is non-widening against both pre-emergency authority and
  emergency restrictions. Its complete external-entry disposition reauthorizes
  only the intersection of pre-emergency and recovery-manifest membership and
  retires all others. Added revocations advance `revocation_epoch` exactly once;
  an unchanged set preserves it. Recovery cannot reactivate a retired key.
- The local emergency-obligation map has one reserved key per admitted affected
  root. The external emergency-closure map has one precharged key per retained
  external registration and is authoritative subordinate content of the
  installed source registry head.
  A root is dormant before its first emergency. A newer fence sets its required
  version to the exact new security epoch, clears current closed-through state
  and rearms the key against the exact expected root head.
- One reconciliation changes one exact current obligation from `PENDING` to
  `CLOSED`. The installed entry binds only its receipt-free closure commitment;
  its post-CAS receipt binds that commitment and the matching installed root
  result, verified external closure, elapsed-horizon evaluation or permanent-
  isolation evidence.
- Emergency recovery requires a complete bijection from obligation keys to
  current closure receipts in both maps. One pending, omitted, duplicate, extra,
  stale, cross-realm, cross-key or cross-epoch entry blocks recovery. A
  local-terminal or permanent-isolation external closure forces retirement;
  only an installed complete fence or elapsed finite horizon can remain
  eligible for reauthorization. Recovery archives both exact closed sets and
  returns retained entries to dormant without inventing prior versions for a
  later-admitted root.
- Domain-retirement drain stops registration, confirmation and attestation
  issuance, makes the source enforcement state restrictive, terminalizes every
  never-active pending entry and moves every active external entry to retirement
  pending. Final source retirement requires one exact local-terminal,
  elapsed-attestation-horizon or permanent-isolation closure for every external
  key, including a transferred emergency capture. The horizon branch
  is available only when the qualified policy and final boundary give every
  derived authority-bearing action and delayed attempt a finite conservative
  deadline. Otherwise the permanent marker requires local terminal evidence.
  The timed branch proves no future conforming source authority, not local root
  terminal state or deletion of retained immutable evidence.
- Security retirement first closes every other applicable participant, then
  installs the security root `DOMAIN_RETIRED`. Only its exact terminal receipt
  lets ADR-001 change the still-active `LOCAL_SECURITY_ENFORCEMENT` participant
  to `TERMINAL_RETAINED`; domain finalization follows. Requiring that
  participant to be terminal before security retirement is invalid and cannot
  satisfy either guard.
- Domain replacement never changes an installed domain identity. It terminalizes
  the old local root and realm, then enrolls a distinct parent-authorized realm/
  transaction domain at version and epochs 1.
- Security-authority construction is acyclic. The order is successor-state
  commitment, transition fact, genesis enrollment evidence or non-genesis
  management envelope, condition, successor head, authority commit
  receipt/envelope, and later root authorization or closure receipt. A head
  never binds a receipt that depends on that same head.
- An unknown state cannot preserve authority.
- Same-generation rebind has one installed composite successor selected by the
  sole body-session-control compare-and-swap. Its descriptor/security binding and
  subordinate journal head cannot advance independently. The authorization or a
  losing candidate cannot become current by replay.
- A realm-local security selector and affected-root selector cannot use separate
  non-atomic checks while authority remains open. Without their exact common
  qualified ADR-001 transaction domain, that realm-local surface is closed.
- An external store never joins the source ADR-001 transaction. Its imported
  mirror is subordinate to its sole local root. It tracks independent monotonic
  global-security and per-key issuance coordinates. A semantic advance requires
  authenticated global ancestry; a refresh requires per-key issuance ancestry
  against the same global head. Every import that installs `CURRENT_IMPORT`
  requires an exact current-manifest authorization receipt, unexpired audience-
  bound attestation and qualified source-to-import clock relation. Either
  ancestry alone can only preserve or strengthen a fence.
- Imported authority is the intersection of source phase and exact registered
  entry state and current manifest authorization. Only
  `CURRENT + REGISTERED_ACTIVE + CURRENTLY_REAUTHORIZED` can authorize. Pending,
  stale-authorization or retirement-pending fences; either source or entry
  retirement retires. A source-wide CURRENT label cannot reactivate a key.
- An external mirror update and authority-bearing local action have one order on
  the same external root. Import-first rejects old state. Action-first retains an
  exact prior-state admission receipt.
- Post-fence evidence retention requires exact pre-fence admission and immutable
  bytes. It cannot create delivery, callback, command, grant, mutation authority,
  or a stronger result.
- An emergency security fence makes every uncommitted old-state
  `START_BODY_COMMAND_APPLICATION_ATTEMPT` lose. Application cannot begin under
  the retired security selector.
- A late `applied` record after emergency fencing requires exact arbiter
  acceptance before the affected body's gate fence. It invokes no application
  and cannot use current successor authority to strengthen an old attempt.
- Emergency reconciliation preserves `ESTOP_LATCHED`,
  `ESTOP_OUTCOME_UNKNOWN`, and `RETIRED_DRAIN_ONLY` exactly. Security recovery
  cannot infer a latch, no-effect result, HOLD result, or reset.
- Local selector ordering does not prove instantaneous external revocation
  propagation. Exact live mTLS rotation/revocation and measured propagation
  evidence remain pre-release gates; unknown or overdue local state denies.
- Every retained pre-rebind record has exact current-head transition ancestry.
  It remains historical evidence and grants no current authority.
- Planned body rebind has no active old-state command, application, or
  nonterminal ingress/fail-safe tip. Emergency fencing preserves and closes each
  exact tip under ADR-007 without inventing a no-effect result.

## Required hostile and recovery tests

N04 and N06 must reject or fence these cases:

- authorize a source transition with a currentness/enforcement key, stale
  predecessor threshold, missing initial or successor proof of possession
  (including a publication-manifest key), a cross-purpose possession proof,
  missing offline-recovery management/receipt/manifest possession proof,
  online/offline origin substitution, unlisted offline-recovery event,
  overlapping predecessor issuance after activation or unsigned/unretained
  commit bundle; derive two successor byte strings from one signed fact,
  omit/change its successor-state commitment, or mix/omit the
  genesis-versus-non-genesis candidate-authentication branch;
- bind a commit-time timing proof into a pre-CAS intent; initialize equal,
  inverted, expired, overflowed or infeasible registration/candidate deadlines;
  use a pre-lock sample or restart to re-date a prepared candidate;
- reject a durable pre-cut receipt solely because its key retired normally;
  accept a new signature under that retired key; treat an expired currentness
  attestation as durable; re-sign a historical receipt; or trust a compromised
  key without the exact independent-anchor/conservative disposition; erase
  per-key commit ancestry when its attestation expires or mix registration,
  issuance and clock-restart commit-envelope fields; use a same-failure-domain,
  unenrolled, post-cutoff, rolled-back or caller-timestamped compromise anchor;
  anchor only an envelope or pre-manifest state; use a different family or
  completion body/authentication; omit the family-member or family-set proof;
  accept a bare anchor receipt/head, wrong source-history audience, missing
  anchor family manifest or shared completion, wrong anchor-domain
  manifest-authentication origin, torn anchor receipt set or cap-plus-one
  anchor publication; bind an incident cutoff into the earlier anchor receipt,
  envelope, family manifest or completion, regenerate an anchor after
  compromise, or accept cutoff equality; use an unauthorized or sibling incident declaration,
  omit an affected or anchor key, select a later/caller cutoff, use an
  incomplete cutoff input set, compare unrelated order domains, erase mapping
  uncertainty or accept an expired order relation; fork, roll back, skip or
  replay the global incident root, use an older valid declaration after a newer
  declaration adds a key or moves the cutoff earlier, omit current-head/
  non-supersession validation, or let ordinary emergency apply mutate the
  incident root;
  select `SINGLE_REGISTERED_EXTERNAL_ROOT` for a global commit, select
  `SOURCE_SECURITY_DOMAIN_HISTORY` for a per-key or ephemeral-authority
  envelope, encode an empty/future audience set, or treat a durable global
  history envelope as current authority; accept a bare bootstrap allocation,
  wrong prospective key/owner/source, foreign parent ancestry, changed operation
  or bootstrap mode on any payload other than the exact allocation receipt;
  use pending-genesis return ancestry for ordinary role output, active ancestry
  for a different root, or permanent history to mutate/continue authority;
  select the active global-cut profile for pending-genesis currentness, select
  the pending profile for active issuance, grant or activation, omit either
  profile's exact authorization envelope, selected family, shared completion,
  capsule, scoped proof or passing verification, mix both authorization products
  or leave the profile unknown/default;
  accept any protected envelope before its selected family manifest and the
  shared producer completion are durable; use the wrong public pre-manifest,
  family manifest or completion; omit either scoped proof; prove the member
  under the family root but not that family under the producer root; accept a
  torn family set; or omit the producer completeness assertion, retained-audit
  opening or compromise disposition required by the verifier mode; mutate every
  pre-manifest producer/operation/coordinate/set/count/opaque-manifest-identity
  field; omit or duplicate any receipt, sidecar or envelope; assign one envelope
  to two families; use a sibling or cross-operation commitment, two manifests
  for one family, two completion manifests, or a family/completion body without
  the exact public pre-manifest digest; expose before completion and retention
  durability;
  let one single-root member retrieve a sibling envelope/receipt/identity/
  sidecar, or disclose an unpadded count/topology without installed permission;
  brute-force a small count from the public projection, distinguish real from
  dummy sibling leaves, replay a member proof across producer/audience roots, use
  an unknown hiding suite, let A authorize exact topology while B denies it,
  ignore a restrictive policy change at delivery, or exceed the fixed padding
  capacity by one;
  crash/recover at commits/envelopes -> pre-manifest commitment -> every family
  manifest/authentication -> shared completion/authentication -> retention ->
  exposure, require exact retry, and exercise exact envelope, private/public
  pre-manifest, family, completion, two-proof, retention and retry reserve
  capacity plus cap-plus-one rejection before the producer mutation; enumerate
  every
  off-diagonal substitution in the complete
  5-by-5 source/bootstrap/pending/imported/anchor
  `CrossStorePublicationManifestAuthenticationOrigin` matrix and reject all 20;
  within source trust, reject online/offline key-origin substitution for every
  predecessor/dual/offline continuity-mode row;
- register an external consumer selector as a realm-local ADR-001 participant;
- create an imported mirror without its exact pending registration, genesis
  protected installed-attestation envelope, passing cross-store verification,
  matching inner genesis currentness attestation or local one-use marker; use a
  bare inner attestation or durable per-key commit envelope as authority;
  install anything but deny-only pending-source-confirmation state at genesis;
  replay a retired
  registration; confirm after PREPARE/deadline/expiry; omit an active or
  retirement-pending root from a planned set; include a pending root as an
  authority member; or finalize ordinary registration retirement from mirror
  expiry/remote absence; register a delivery root with a missing, smaller,
  differently keyed or cap-mismatched no-install reserve, and exercise exact cap
  and cap-plus-one; expire a pending entry, reallocate its registry/obligation/
  issuance/ledger slot and accept a delayed confirmation or issuance replay;
  exercise the retained lifetime-object cap without tombstone eviction;
- enumerate the complete source-phase by
  `ImportedRealmSecurityRegisteredEntryEvidence` by
  `ImportedRealmSecurityCurrentnessEvidence` product. Accept only these result
  classes: exact global domain retirement or exact permanent root closure
  installs `RETIRED`; exact `CURRENT` authorization plus
  `COMPLETE_CURRENTNESS_HIERARCHY` installs `CURRENT_IMPORT`; exact `CURRENT`
  authorization plus `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY`, and every valid
  nonpermanent restrictive or no-entry product, installs `FENCED_DENY`.
  Reject every impossible pair, unknown/default variant, mixed variant,
  forbidden extra field, partial hierarchy reclassified as absence, or result
  stronger than that product permits;
- for every `CURRENT_IMPORT` installation, remove or substitute each durable
  currentness envelope, ephemeral installed-attestation envelope, selected
  family manifest, family authentication set, family capsule, member proof,
  family-set proof, shared completion, verification result, inner attestation,
  current-authorization hierarchy and clock relation in turn. Mix the two
  currentness families across producers or bind either family to the other
  producer's completion. Mismatch the operation, audience, root/store
  incarnation, global head, issuance head, registry version, inner digest,
  durable-sibling digest, expiry or source/import clock. Every case must remain
  fenced or reject and must never install or extend authority;
- exercise all seven registered-entry evidence variants against every
  applicable source phase. A pending or retirement-pending hierarchy stays
  fenced even with valid currentness. A non-retired global-only no-entry
  projection can fence but cannot claim entry state, capture a per-root
  high-water, acknowledge a planned/emergency directive, retire one root or
  reopen authority. The global-domain-retired variant retires only with exact
  authenticated `DOMAIN_RETIRED` ancestry. A permanent root-closure hierarchy
  retires only the byte-matching root through its exact selected family,
  completion, capsule, two proofs and origin;
- refine the byte-identical imported global head with each legal same-head
  restrictive hierarchy. Retirement-pending refinement must preserve
  `FENCED_DENY`; either permanent-closure refinement must install `RETIRED`.
  Each first refinement advances only the sole outer selector and local import
  version. Exact retry must return the same receipt without advancing. Reject a
  current-authorization or pending-registration refinement, a bare directive,
  a newer/older/sibling global head, a wrong root/origin/incarnation, a second
  distinct closure, or any attempt to acknowledge planned/emergency closure;
- deliver one planned-fence directive with its new prepared global ancestry and
  exercise `IMPORT_NEW_PREPARED_AND_CLOSE`. Then deliver the byte-identical
  prepared global history first and the directive second and exercise
  `CLOSE_ALREADY_IMPORTED_SAME_PREPARED_CHANGE`. Both orders must converge on
  the same source coordinate, captured per-root tuple, no-new-predecessor-work
  partition, fence mode and acknowledged source closure, while retaining their
  truthful local import histories. Reject the same-head mode before the global
  head, after an existing fence receipt, or with a changed directive/member.
  A global-only prepared import may fence but cannot emit the planned-fence
  receipt;
- race same-head retirement-pending or permanent refinement against currentness
  refresh, and race global prepared, emergency, drain or domain-retired import
  against stale currentness, in both orders. The restrictive result must win or
  the stale operation must lose. Import a strictly newer `CURRENT` head with
  exact current authorization but
  `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY`; it must advance the authenticated
  coordinates and fence immediately, never leave the older `CURRENT_IMPORT`
  authoritative. A partial newer hierarchy rejects and cannot be relabeled as
  that absence branch. A later current cancellation/activation
  descendant can restore `CURRENT_IMPORT` only with its own exact current-
  authorization hierarchy and fresh same-head durable-plus-ephemeral
  currentness producer;
- reuse a source registration across a replacement parent entry, allocation,
  local selector or state incarnation; confirm a predecessor pending entry after
  planned change/emergency; reissue for an active entry removed by the successor
  or recovery manifest; omit, duplicate or misclassify one complete successor
  disposition;
- race a source grant/release/dispatch against external retirement, PREPARE and
  emergency in both orders and against same-key currentness refresh; attempt the
  grant with only a matching semantic digest/epoch, registry entry,
  attestation, or stale activation/manifest-authorization receipt; omit or
  mismatch its per-key selector/head, or set any derived action/effect/callback/
  publication/delivery/retry boundary after the stored finite horizon;
- for a multi-target grant, omit/swap/duplicate a target, projection, currentness
  intent, target-set proof or receipt-set proof; change either source-local exact
  root/count or external padded root/hiding proof; distinguish target-set size
  one from two within one capacity class; accept expiry equality, cross the
  source-local aggregate, reveal a sibling member or
  install authority outside the exact role projection; for a delivery target,
  swap/reuse/omit the registered reserve commitment or sequence-indexed slot,
  and prove retry selects the identical slot without a remote-store read; at
  activation, omit/swap/stale one read-only target currentness member, reuse only
  issuance-time verification, accept expiry equality or an incompatible
  descendant, or perform a second ledger append; race same-key refresh and the
  global cut against LIVE in both orders;
- close exact role marker lineages from source pending-never-LIVE, protected
  local transport quiescence, zero-work no-install and complete isolation;
  reject a partial target set, wrong protected return audience, authorization-
  closure-only terminal ACK, elapsed-time marker close, open-sibling mutation
  or terminal-state substitution; race local observer-role recording,
  whole-root source closure, target-history reconciliation, checkpoint
  publication and permanent target sealing in both orders; require the
  recording/reconciliation fact, exact common-transaction ancestry, compatible
  installed role product and retained specialized receipt, and reject
  cross-grant, wrong-origin, stale-product or post-seal continuation evidence;
  after emergency capture or retirement BEGIN, exercise all-still-open,
  all-role-closed and mixed captured-marker partitions, then reconcile,
  finalize, recover and transfer to domain drain; reject a second close,
  missing compatible receipt, envelope, selected family, shared completion,
  capsule or scoped proof, wrong subset, stale captured head or ledger write for
  the all-compatible case;
- accept a mirror rollback, sibling, ancestry gap, changed realm, changed
  lineage, expired deadline, unreceipted source head, stale currentness
  attestation, missing/mismatched installed-attestation envelope, missing or
  failed cross-store verification, missing/invalid clock relation, delayed
  historical `CURRENT` descendant after a newer non-current source head, or
  replay that extends an attestation deadline;
- import a source-wide `CURRENT` head whose matching registry entry is pending,
  stale-authorized, retirement-pending or permanently retired and attempt to
  install `CURRENT_IMPORT`; advance only the global or only the per-key issuance
  coordinate while claiming the other advanced;
- race each currentness-attestation issuance against PREPARE, emergency,
  registration retirement and domain-retirement drain; reject a signature built
  after an uncommitted read or for a losing issuance candidate; reject a skipped,
  repeated or overflowed sequence, changed retry request, reused operation or
  publication that was not durably retained; exercise exact issuance cap,
  cap-plus-one and retained-result archive loss; verify that two unrelated keys
  advance independently and that a reserved-priority global fence cannot starve;
- exercise grant-ledger genesis/marker-only empty summary, first finite append,
  later maximum, marker close, clock restart, exact sequence maximum and
  maximum-plus-one rejection; reject invented empty-branch time, skipped/rolled
  sequence, receipt-bound installed lineage entry or changed idempotent retry;
  restart a marker-only key with typed numeric inapplicability and no closure-
  horizon entry for the marker field,
  and reject a fabricated cutoff, closure horizon, wrong extra purpose kind or
  empty-ledger entry;
- use active manifest authorization in pending-genesis mode or pending
  authorization in active mode; omit the initial manifest-authorization receipt
  from confirmation; create a registration/restart candidate cycle; omit,
  duplicate or substitute one child candidate, commit receipt, receipt envelope
  or common-transaction link in a joint global/per-key commit;
- restart the source attestation clock with one field omitted, duplicated,
  merged, wrong-polarity, overflowed, outside either applicability horizon or
  mapped from a sibling head. For old uncertainty interval `[90, 110]`, the new
  source-authorization cutoff uses 90 while old derived-authority retirement
  before 110 rejects. Reject new issuance and
  horizon retirement without the exact installed bridge. An unmappable horizon
  must atomically install the issuance marker; only an unmappable nonempty
  ledger maximum installs the third ledger branch, while empty or separately
  mapped summaries retain their exact branch. On a second restart, an existing
  marker is preserved while a newly unmappable retained maximum enters the
  third branch. Ordinary, planned, emergency and
  domain elapsed-horizon closure then reject, while exact whole-root terminal or
  permanent isolation remains legal; race clock restart against external-root
  retirement finalization in both orders, require current descendant heads and
  complete restart ancestry, and reject old-clock numeric comparison or horizon
  closure after an unmappable marker;
- race one old-state external admission with one mirror advance in both orders;
- use post-fence retention to deliver bytes, invoke a callback, publish, command,
  mutate live state, or claim success;
- bind a planned member/set back to the final candidate, substitute a core,
  derive two candidates from one core/root tuple, omit a captured horizon or
  choose an activation deadline not strictly beyond the maximum captured
  horizon plus its evaluation/commit bound; put a horizon in the proved-empty
  branch, omit/miscalculate the nonempty maximum, or bind a stale issuance
  head/high-water to a lower horizon;
- activate an authorizing change directly from `CURRENT`;
- activate before one affected root quiesces, or use a missing, duplicate, stale,
  extra, wrong-root, or wrong-candidate quiesce receipt;
- activate before one active external member installs `FENCED_DENY`, proves
  preexisting final retirement or reaches its exact PREPARE-captured complete
  horizon, or use missing, duplicate, stale, extra, wrong-mirror,
  wrong-candidate or remote-only external closure evidence;
- re-enable a planned external root from the prepared source head, the
  predecessor head, or candidate bytes instead of a later installed CURRENT
  successor with a fresh issuance-currentness attestation;
- rebind an emergency-closed root at the recovery head and after one or more
  planned successors; reject a missing/reordered chain head, changed recovery
  base/incarnation, newer incident, retirement, stale currentness or local
  terminal/isolation predecessor;
- exercise both PREPARE-versus-source-confirmation orders, emergency before and
  after deny-only genesis, pending expiry versus confirmation, active local
  final retirement versus PREPARE, and source retirement at one tick before,
  equal to and after every attestation horizon;
- attempt horizon retirement with an unbounded derived action, unenforced final
  deadline, delayed retry beyond the proposed horizon, omitted derivation class
  or `LOCAL_TERMINAL_EVIDENCE_REQUIRED`; require exact local terminal evidence;
  exercise the qualified ordinary timed branch from source `CURRENT` and
  `DOMAIN_RETIREMENT_DRAIN`, and the candidate-bound planned branch at one tick
  before, equal to and after the captured complete horizon; reject a missing,
  branch-mismatched or partially manifested
  `ExternalSecurityEnforcementRootRetirementReceipt`;
- reject security retirement with one other participant still open, with a
  pre-terminalized or missing local-security participant, or without the exact
  external/emergency closure partition; reject ADR-001 local-security
  participant closure before the terminal security head and receipt;
- cancel after the first affected root quiesces;
- classify a changed trust root, key, algorithm, validity rule, principal, route,
  ACL, audience, profile, revocation member, or extension as metadata-only;
- complete planned rebind with a missing, duplicate, losing, stale, or
  cross-candidate rebind receipt;
- recover with a principal/role/route/audience/key use absent from the
  pre-emergency state, remove a revocation/restriction, reauthorize an external
  entry absent from either manifest, or preserve/increment `revocation_epoch`
  contrary to the exact recovery delta;
- apply a first or consecutive emergency delta that widens authority, removes a
  restriction/revocation/tombstone, replaces the original pre-emergency
  baseline, or drops a member of the cumulative restriction root;
- omit an emergency obligation, create two keys for one affected root, close the
  wrong fence version, give a dormant entry a fabricated version, retain an old
  closure as current after rearm, or recover with one `PENDING` entry;
- exercise every external emergency closure branch with exact protected
  evidence; reject a new-admission-only fence, bare local receipt, wrong
  audience/epoch/key/captured child head, horizon one tick early, elapsed branch
  for `LOCAL_TERMINAL_EVIDENCE_REQUIRED`, or a closure receipt bound directly
  into its installed `CLOSED` head; mutate one deterministic terminal-assessment
  member to missing, extra, ambiguous or the wrong closed-lineage state;
- attempt recovery with a missing/extra/stale external closure receipt, with a
  local-terminal or permanent-isolation branch mapped to reauthorization, or
  without the exact local and external closed-set bijections;
- exercise a root admitted before the first emergency, a root admitted after
  recovery, and consecutive emergencies before and after first closure; require
  the exact new security epoch, expected head, full child capture and
  closure-receipt invalidation; prove an older complete fence cannot close the
  newer epoch without a fresh dominance receipt and no intervening reopen;
- race external emergency reconciliation against domain drain in both orders;
  drain-first must install the exact transfer commitment and permit only
  registry retirement closure, while reconciliation-first is archived as
  already closed and cannot be replayed after transfer; exercise a transferred
  lost marker root through permanent isolation, complete ledger close,
  permanent registry tombstone and fresh drain guard, rejecting stale guards;
- crash after emergency apply, after affected-root fencing, and after receipt
  publication, then resume the same obligation without repeating an effect;
- start body application after the security fence or accept at the body boundary
  after its gate fence;
- append `applied` without exact pre-gate-fence arbiter acceptance, or strengthen
  an ambiguous attempt after query rights end;
- turn `ESTOP_OUTCOME_UNKNOWN` into latched, no-effect, HOLD, or current state by
  default; and
- reopen `RETIRED_DRAIN_ONLY` or use drain-only closure to admit new work.

Model and mutation checks must cover the empty affected-set branch, first/last
obligation, equality-at-expiry, counter maximum, fence-versus-START race, and
activation-versus-emergency race. These checks are future implementation
requirements. They are not current live-security or release evidence.

## Migration

N04 generates the projection, planned-change, imported-mirror, and emergency-map
types and vectors. N06 integrates realm-local transactions and external
same-root import ordering. Consumers compare exact state and reattach. They do
not interpret raw provider configuration.

## Operational recovery

On state mismatch, corruption, or rollback, stop admission and enter the
plane-appropriate denial, HOLD, ESTOP-preserving, or drain-only posture. Restore
only from an authenticated, content-addressed state with a newer authorized
recovery transition and complete closed-set guard.

## Compatibility and rollback

Rollback to a previous security state requires an explicit new epoch and
authorization. It is not a numeric decrement or byte restore. Retained security
history remains auditable even when deployment is prohibited.

## Open questions

<a id="ncp-b01-selector-allocation-adr-009-v1"></a>

The cross-store opening meaning is closed. B03 must select its derived finite
numeric maximum and 1 through 16 exact capsule-profile identities under the
predicate above. Each identity is 1 through 128 bytes and matches
`[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?`. It fixes the protected-envelope
family, proof shape, audience/disclosure mode, and bounded delivery container.
Unknown or default security, currentness, audience, producer, disclosure,
capsule profile, or retirement values deny.

The exact-opening maximum is selected from 1 through 1,048,576 bytes. Its
predicate derives the exact smaller maximum from the complete canonical shell,
encoding expansion, and universal structured-frame ceiling. It rejects an
unknown shell or encoding, a nonpositive payload result, and unsafe arithmetic.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: state identity covers meaning, not one filename.
2. Security: algorithms, keys, routes, roles, audiences, and revocation bind.
3. Safety: trust uncertainty cannot preserve plant authority.
4. Lifecycle: prepare, quiesce, activate, rebind, revoke, and recover are explicit.
5. Resources: state and transition work are bounded.
6. Migration: portable vectors make independent equality testable.
7. Science: authenticity cannot validate scientific claims.
8. Operations: local, imported, planned, and emergency procedures are executable.
9. Evidence: live planned rotation/revocation remains an external gate.
10. Governance: roots, manifests, keys, incidents, and retention have owners.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes.
