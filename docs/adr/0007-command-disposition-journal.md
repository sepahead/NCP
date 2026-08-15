# ADR-007 — Journal body-issued command dispositions

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: plant/safety reviewer, Haldir owner, Crebain owner

## Context

A successful publish or Haldir Gate receipt does not prove that Crebain received,
admitted, applied, hold-effective, rejected, superseded, expired, or failed a command. Commanders
need authenticated body evidence and idempotent query without turning protocol
success into a physical-effect claim.

## Proposed decision

Crebain shall emit a bounded `CommandDisposition` and support
`QueryCommandDisposition`. Each disposition binds:

- plant/body principal and exact plant profile;
- session ID and generation, transcript, and security state;
- authenticated command publisher principal and exact raw candidate authority
  field bytes/digest or syntactic absence, kept distinct from verified body
  authority;
- one closed `CommandAuthorityEvidence` branch;
- command stream epoch and sequence;
- original authenticated command-frame digest, command-content digest, command
  ID, mode, applicable operation ID, and its producer-authenticated,
  receiver-independent `NormativeSourceRef` or explicit normative absence;
- optional body-local `ResolvedCaptureSourceCorrelation` as separate provenance.
  It names the body as receiver and cannot substitute for a downstream
  observer's local resolution;
- disposition-journal incarnation, state version, and body-local monotonic
  disposition sequence;
- one closed disposition state;
- software/hardware boundary name, body clock incarnation, and body-local
  monotonic timestamp;
- for `applied`, one `BodyAppliedValueRef` to a distinct body-owned Active value
  object; other states carry no such value reference;
- for `hold_effective` or `stop_latched`, one exact
  `BodyRestrictiveCommandAssociationEvidence` to the earlier fail-safe effect and
  later post-admission association; other states carry no such association;
- reason/error code, terminal flag, exact prior-record digest, and prior state;
  and
- pre-existing body-authority provenance used for the command, when applicable.

`CommandAuthorityEvidence` is phase-aware and closed. `CANDIDATE_NOT_EVALUATED`
is legal only on the first `received` record and binds the exact
`CommandAuthorityCandidate`: either the bounded encoded lease field or syntactic
absence. It grants no term, lease ID, holder, or authority.
`VERIFIED_BODY_LEASE` binds the exact body-issued lease bytes/digest, term, random
lease ID, holder, issuer, session/generation/security context, monotonic
enforcement deadline, installed authority-state head and currentness receipt;
the authenticated publisher must equal the verified holder.
`VERIFIED_BODY_LEASE_AT_FAIL_SAFE_RESERVATION_CUT` binds that same exact verified
lease/currentness/declaration evidence as captured while current by the installed
fail-safe reservation, plus the reservation fact/commit, protected bytes,
grant/slot and unchanged effective deadline. It is legal only for the same
non-Active candidate whose reservation atomically retired that lease/declaration.
It grants no continuing authority, cannot authorize Active or another command,
and cannot survive a changed reservation, bytes, slot, deadline or cut lineage.
`PERMITTED_ESTOP_LEASE_ABSENCE` binds exact candidate absence, exact ESTOP mode,
and the installed manifest/plant-profile rule that permits only that omission.
`REJECTED_CANDIDATE_AUTHORITY` binds the raw candidate form and one exact closed
failure classification, such as absent-when-required, malformed, invalid issuer
or signature, holder mismatch, stale term/lease ID, expired, revoked, or
wrong-session/generation/security context. It carries no verified holder/term/
lease ID. A later `rejected` record can carry either verified authority or the
rejected branch when another check failed. Candidate-declared term, ID, or holder
is never reported as verified provenance. An `admitted` record and its successors require
exactly one of `VERIFIED_BODY_LEASE`,
`VERIFIED_BODY_LEASE_AT_FAIL_SAFE_RESERVATION_CUT`, or
`PERMITTED_ESTOP_LEASE_ABSENCE`, under the branch restrictions above.

The canonical `DispositionRecord` contains neither its own record digest nor its
signature, delivery receipt, or successor journal-head digest. A protected body
envelope carries the exact record bytes and route/context plus a signature and
receipt over the recomputed record digest. A successful journal append separately
produces the prior/installed-head transition receipt. This ordering prevents a
self-referential digest.

The closed enum states and boundary terminality are:

| State | Boundary terminality |
|---|---|
| `received` | non-terminal |
| `rejected` | terminal |
| `admitted` | non-terminal |
| `applied` | terminal for the named boundary |
| `hold_effective` | terminal for the named body-local HOLD association |
| `superseded` | terminal |
| `expired` | terminal |
| `failed` | terminal |
| `unknown_after_boundary` | terminal and never strengthened later |
| `stop_latched` | terminal for the named body-local latch only |

`applied` means only that the named Active-value boundary accepted the command
and atomically armed its watchdog at the recorded instant. `hold_effective`
means only that the body associated an admitted HOLD with its confirmed
body-local clear effect. The association does not repeat that effect. Neither
means the physical plant achieved the requested state. `stop_latched` proves
only that the named body-local stop latch entered. It does not prove actuator
motion, zero energy, hazard removal, or regulatory
safety. `unknown_after_boundary` is terminal for that command and cannot later
be upgraded to `applied`, `hold_effective`, or `stop_latched`; a new command is
required. The `stop_latched`
disposition is legal only for a semantically and stream-admitted stop command.
It is not the record for a fail-safe side effect caused by a command candidate
that the body later rejects.

Every new exact command identity has at most one disposition chain. It starts
with an authenticated `received` record bound to the exact original frame/content
digests, session/generation, authenticated publisher, raw authority candidate,
`CANDIDATE_NOT_EVALUATED`, originating `CommandIngressAttemptRecord`, stream
position, and operation context. The only next
states are `rejected` or `admitted`, with the final authority-evidence branch.
`applied`, `hold_effective`, `superseded`, `expired`, `failed`,
`unknown_after_boundary`, and `stop_latched` require the exact authenticated `admitted` predecessor chain and
unchanged final authority evidence. A caller-supplied command ID, raw
candidate-declared lease fields, or standalone terminal record is insufficient.

The normal `received -> admitted` bundle binds the exact complete body deadline
set `COMMAND_ADMISSION_LEASE_NOT_AFTER` and
`COMMAND_ADMISSION_TTL_NOT_AFTER` and evaluates both strict-before at its durable
selector transition. It also binds the exact installed body freshness grant,
installation receipt, selected slot, and unchanged exclusive absolute deadline.
The retained `TTL` identifier names that grant deadline. It does not authorize a
per-frame TTL. Equality or later lease time rejects admission. Equality or later
effective command deadline selects the typed expired/rejected case and
cannot create an admitted tip. A receive timestamp, arrival-relative watchdog,
lease-installation receipt or earlier sample does not satisfy either commit-bound
condition.

Grant expiry has a canonical cause independent of tombstone scheduling. The grant
registry records `DEADLINE_ELAPSED` or an authenticated restrictive cut with its
linearization order. If a security/declaration/session/revocation cut ordered
strictly before the effective command deadline, the candidate is superseded by
that cut. Otherwise an evaluation at or after the effective deadline selects the
command-expired branch, whether or not a lazy
`EXPIRE_BODY_COMMAND_FRESHNESS_GRANT` CAS already materialized its tombstone. A
worker cannot change `expired` into `superseded` by racing that CAS. Admission,
START and boundary receipts bind the exact deadline/cut order and selected cause.

Command application is a durable attempt protocol, not a direct call followed by
a best-effort journal append. `DispositionJournalHead` binds a bounded
`BodyCommandApplicationAttempt` map. Its closed attempt states are
`INSTALLED_PENDING_BOUNDARY | OUTCOME_PENDING_QUERY_OR_RESOLUTION | TERMINAL`;
exact-key absence is typed map nonmembership. Closed `BodyActuationGateState` is
`OPEN(epoch, activation-fact digest) |
FENCED(epoch, cause, fence-fact digest) |
RETIRED(epoch, retirement-fact digest)`. Each referenced fact is receipt-free
and excludes the candidate/installed arbiter head, selector, commit and receipt.
The arbiter successor binds the fact; its post-CAS activation/fence/retirement
receipt binds the installed head. No gate state binds that later receipt.
`BodyActuationArbiterGenesisFact` installs the first FENCED epoch with no output
or operation only as the subordinate
`BODY_ACTUATION_ARBITER_STATE_GENESIS_FROM_DOMAIN_RESERVATION` edge of the
jurisdiction-global `InstalledActuationAuthorityDomainSelector`. The ADR-001 generation-
creation receipt and domain-reservation operation, not a child-created arbiter
selector, authorize that edge. Epochs never repeat or reopen in place.
`START_BODY_COMMAND_APPLICATION_ATTEMPT` accepts one exact admitted tip, a
never-used attempt ID, idempotency context, intended boundary/value reference,
current gate epoch, and the complete strict-before
`COMMAND_APPLICATION_LEASE_NOT_AFTER` plus
`COMMAND_APPLICATION_TTL_NOT_AFTER` condition set over that same grant/slot and
unchanged effective absolute deadline. Its compare-and-swap installs the attempt
before boundary invocation. A sibling attempt, reused ID, missing deadline member,
changed grant/slot, stale gate or non-admitted tip loses and cannot invoke.
The closed `BodyCommandApplicationStartRejectionCause` union is
`FRESHNESS_GRANT_RESTRICTIVELY_CUT | LEASE_NOT_CURRENT |
COMMAND_TTL_ELAPSED`, in that total precedence order, subject to the canonical
grant-cause rule above. The first two create `superseded`. Otherwise, an elapsed
grant deadline creates `expired`. Equality selects the applicable elapsed branch.
The terminal append binds exactly one selected cause and its complete currentness or
at-or-after evaluation set and structurally forbids every other cause. A branch
cannot require both strict-before and elapsed purposes for one deadline.

The named body software/hardware boundary implements a qualified durable
`BodyActuationArbiter`. It consumes an installed attempt and exact gate epoch at
most once, checks the same body clock and deadlines at acceptance, and records
one queryable result: definitive accepted value, definitive no-effect rejection,
or, for a restrictive operation, bounded ambiguity pending same-key resolution.
Active reply ambiguity queries the indivisible installed bundle; it is not a
third normal authoritative result. Its acceptance evidence binds the attempt,
idempotency key, value/ref, boundary, gate epoch and acceptance instant. Storage
state never substitutes for that boundary evidence. A deployment without an
idempotent/queryable arbiter and a proven deadline/fence ordering keeps Active
application disabled.

Local realm serialization is not sufficient to enroll physical hardware. The
facility/hardware authority therefore owns one bounded
`PhysicalActuationJurisdictionEnrollmentRegistryHead` through one sole
`InstalledPhysicalActuationJurisdictionEnrollmentRegistrySelector`, outside all
server authority realms. Its stable `PhysicalActuationFacilityKey`, complete
facility-issued `PhysicalEffectPathKey` inventory and immutable
`PhysicalActuationFacilityConflictGraph` cover every actuator, channel, bus,
power path, watchdog, HOLD path, ESTOP/interlock, reset and handover path that can
interact.

The finite inventory also defines immutable
`PhysicalActuationJurisdictionEnrollmentSlotKey` values and immutable
`PhysicalActuationFacilityIncidenceInventory`. Let `U`, `P`, `H`, `E` and `A`
be the exact finite slot, path-key, hardware-identity/incarnation, physical-effect
and effect-authority universes. The four canonical slot-incidence maps have
domain `U`, reference only their declared universe, give every identity at least
one slot and give every slot nonempty `P/H/E/A` incidence sets. Therefore the
slot unions equal `P`, `H`, `E` and `A`;
`PhysicalActuationFacilityPathOwnerEpochTombstoneLedger` keys equal `P`.

Slots sharing any `P/H/E/A` identity have a conflict edge; every additional edge
binds its qualified interaction basis. Registry keys, incidences and edges come
only from qualification, never caller names. A reservation compares its complete
neighborhood in the sole facility selector. Thus disjoint slots can progress,
but aliases cannot. Any orphan/extra incidence, dangling reference, ledger-key
mismatch or missing identity/edge invalidates qualification. Topology change
requires complete isolation, permanent old facility/hardware retirement and
fresh key/inventory.

For component `C`, `PhysicalActuationFacilityComponentIncidenceProjection` is
the member-slot unions `P(C), H(C), E(C), A(C)`. Complete partitions have
disjoint slot sets covering `U` and projections covering all universes; shared
identity merges components. Wrong projection rejects.

Every operation that claims complete-component isolation uses one canonical
`PhysicalActuationFacilityConflictComponentClosure`. Let `U` be the immutable
finite slot inventory and let `R` relate two slots when they share a path,
hardware identity, effect/authority path, or either direction of a facility
conflict edge. Starting
from the operation's nonempty seed set `S0`, the qualification computes
`S(n+1) = S(n) union {v in U | exists u in S(n): R(u,v)}`. The component is the
first fixed point. The fixed point must occur in at most `|U|` iterations.
Canonical sorted expansion layers bind the exact least fixed point.

`PhysicalActuationFacilityConflictComponentComplementProof` binds every slot in
`U \ component`, the exact component incidence projection, the complete immutable
adjacency/path/identity commitments, and
typed nonmembership of every relation from the component to its complement.
A supplied superset, subset, unbounded search, omitted inventory member, or one
cross-boundary relation rejects. Lost-selector recovery uses the last
authenticated inventory plus the immutable qualification envelope. If the last
inventory is absent or ambiguous, it seeds the envelope's complete inventory.
If the envelope is absent or ambiguous, closure cannot proceed. Isolation can
enlarge. It cannot omit possible hardware.

`PhysicalActuationFacilityRegistryQualification` binds the facility authority,
durable selector/store, strict-serializable compare-and-swap and recovery model,
hardware command authentication/query semantics, immutable inventory, and hard
map/transaction/byte/epoch bounds. Its independent
`PhysicalActuationFacilityRegistryQualificationReceipt` is not a caller
assertion. Receipt-free
`PhysicalActuationFacilityRegistryGenesisFact` binds that receipt, the configured
facility root, exact selector absence plus never-used proof, complete slot/path/
hardware/effect/authority incidence and conflict inventory, the exact
per-path-ledger key set, finite bounds and one authenticated
`PhysicalActuationBoundaryInitialIsolationEvidence` per `P` member. Each evidence
member binds its exact incident `H/E/A` projection and identity/incarnations,
actual inhibition, durable enrollment-state high-water/retired set and proof that
no current epoch can authorize an effect. An unassigned label is insufficient.

`PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT_REGISTRY_GENESIS_FROM_FACILITY_AUTHORITY`
is the sole bootstrap. Its candidate binds the genesis fact and starts registry
state `ACTIVE_FACILITY_REGISTRY` with every slot
`UNASSIGNED_PHYSICALLY_ISOLATED`. Post-CAS
`PhysicalActuationFacilityRegistryGenesisReceipt` binds the fact and exact
installed selector/head; a final non-authorizing persistence manifest binds the
complete crash-visible bytes. After any use, selector absence, replay, a sibling
selector or reconstructed empty state is corruption and cannot authorize plant
work.

Every later facility-registry mutation constructs one
`PhysicalActuationFacilityCASCondition` over exact facility/store qualification,
operation identity, expected selector/head/version, complete affected slot/path/
hardware/effect/authority/conflict set, receipt-free fact and intended reserve
delta. The candidate binds that condition and fact.
`PhysicalActuationFacilityCommitReceipt` then binds the
prior and installed selector/head and monotonic bounded facility commit position;
every specialized receipt depends on it, and
`PhysicalActuationFacilityPersistenceManifest` binds the complete bundle last.
No fact/candidate binds a later receipt. Same-operation reply loss returns the
retained result; changed content rejects. Hardware uses separate tokens/query and
is outside this storage CAS.

An independent append authority closes rollback.
`PhysicalActuationFacilityCommitLineageAnchorQualification` binds its distinct
authority, durable store/incarnation, sole
`InstalledPhysicalActuationFacilityCommitLineageAnchorSelector`, exact facility
key/selector/store incarnation, strict CAS/recovery, signing/history,
anti-rollback and finite bounds. Its independent
`PhysicalActuationFacilityCommitLineageAnchorQualificationReceipt` and receipt-free
`PhysicalActuationFacilityCommitLineageAnchorGenesisFact` drive
`PHYSICAL_ACTUATION_FACILITY_COMMIT_LINEAGE_ANCHOR_GENESIS`, which installs `OPEN`
`PhysicalActuationFacilityCommitLineageAnchorHead` before facility genesis from
typed absence/never-use. Its
`PhysicalActuationFacilityCommitLineageAnchorGenesisReceipt` and persistence
manifest expose no partial state. Facility qualification binds this genesis and
cannot replace it.

Every facility commit that can be exposed or consumed has exactly one contiguous
append. A commit stranded only by winning terminalization stays permanently
non-authorizing and non-exposable. Receipt-free
`PhysicalActuationFacilityCommitLineageAnchorAppendFact` binds its verified
ADR-001 protected `PhysicalActuationFacilityCommitReceipt` and
`PhysicalActuationFacilityPersistenceManifest`, exact prior/installed facility
heads and root, selector/store incarnation, event/operation/idempotency identity,
checked position (`first` or `prior + 1`), expected `OPEN` anchor head and signed
accumulator; it excludes candidates/receipts.
That anchor-only audience is not facility-commit exposure.
`APPEND_PHYSICAL_ACTUATION_FACILITY_COMMIT_LINEAGE_ANCHOR` uses the sole anchor
CAS to install the next `OPEN` high-water. Generic
`PhysicalActuationFacilityCommitLineageAnchorCommitReceipt`, dependent
`PhysicalActuationFacilityCommitLineageAnchorAppendReceipt` and final
`PhysicalActuationFacilityCommitLineageAnchorPersistenceManifest` bind its prior/
installed heads, positions, root inclusion and history. Exact replay returns the
bundle; skip, duplicate, reorder, fork or changed-content reuse rejects.

Commit outputs/tokens remain non-exposable until the exact consumer verifies the
audience-specific protected append export.
Receipt-free `PhysicalActuationFacilityAnchoredCommitExposureEvidence` binds both
source bundles, root/inclusion and consumer event; its CAS records the declared
exact/bounded-use key. Stranded, cached, bare or unmanifested state grants nothing.

Receipt-free `PhysicalActuationFacilityCommitLineageAnchorTerminalizationFact`
binds independent permanent-loss diagnosis, qualification, expected `OPEN` head
and complete append history.
`TERMINALIZE_LOST_PHYSICAL_ACTUATION_FACILITY_COMMIT_LINEAGE` and APPEND compare
the same selector. Terminalization installs `TERMINAL_NO_SUCCESSOR`; its generic
receipt, `PhysicalActuationFacilityCommitLineageAnchorTerminalizationReceipt`
and final manifest retain the last high-water/append inclusion. An append winner retries
terminalization at its successor; a
terminalization winner permanently blocks append/reset and leaves the losing
facility commit non-exposable.
Receipt-free `PhysicalActuationFacilityFinalHighWaterNoSuccessorEvidence` is
constructed only from the verified protected terminalization-receipt/manifest
export. It binds final facility version/position/root, append inclusion, terminal
head/receipt, signed history and no successor, excludes the isolation candidate,
and targets only
`ISOLATE_LOST_PHYSICAL_ACTUATION_FACILITY_COMPLETE_COMPONENT_SET`.

Reply loss returns retained state; changed identity/content rejects. Pre-append
crash is non-exposable;
pre-manifest append/terminal crash yields no final evidence. Genesis
reserves append/export per commit and terminal/final.
Every facility CAS charges
`PhysicalActuationFacilityCommitLineageAnchorAppendCost`; closure retains
`PhysicalActuationFacilityCommitLineageAnchorTerminalizationCost`, and
`OneCASFenceOutputCost` includes its append/exposure. Insufficient reserve,
overflow or cap-plus-one rejects before facility commit.

ADR-001 exact mappings, distinct from facility/higher enrollment, are:
`FACILITY_COMMIT_TO_INDEPENDENT_LINEAGE_ANCHOR` =
`PhysicalActuationFacilityCommitReceipt`, facility-to-APPEND, `EXACTLY_ONCE`
key `(facility key, store incarnation, position, root)`;
`INDEPENDENT_LINEAGE_ANCHOR_APPEND_TO_FACILITY_COMMIT_CONSUMER` =
`PhysicalActuationFacilityCommitLineageAnchorAppendReceipt`, anchor-to-exact
consumer/store, scheduled exact/finite-bounded key; and
`INDEPENDENT_LINEAGE_ANCHOR_FINAL_TO_LOST_FACILITY_ISOLATION` =
`PhysicalActuationFacilityCommitLineageAnchorTerminalizationReceipt`,
anchor-to-ISOLATE, one terminal key. As for every ADR-001/ADR-007 cross-store
authority hop, facts accept only protected verification/inner digest after source
and export manifests. Generic commit, store/incarnation, history, audience,
key-use, replay and `production-secure` principal must match; target CAS records
consumption. ADR-009 currentness cannot cross this bridge.

The closed registry state is `ACTIVE_FACILITY_REGISTRY |
RETIREMENT_DRAIN_ONLY | PERMANENTLY_RETIRED`. One reserved
`PhysicalActuationFacilityRetirementBudget` covers the worst-case database
positions/bytes/storage/scheduler work and one-use hardware invalidation/query
rights needed to eliminate every issued epoch, resolve each prepared slot and
retain every tombstone. Preparing or enlarging an obligation atomically grows
that reserve first. Ordinary enrollment cannot consume it. Before commit-position,
epoch or byte capacity would cross its reserve, exact
`BEGIN_PHYSICAL_ACTUATION_FACILITY_REGISTRY_RETIREMENT` alone changes
`ACTIVE_FACILITY_REGISTRY -> RETIREMENT_DRAIN_ONLY`,
using closed `PhysicalActuationFacilityRetirementCause`
`CAPACITY_THRESHOLD | ADMINISTRATIVE_FACILITY_RETIREMENT |
ACTIVE_QUALIFICATION_WITHDRAWN_RESTRICTIVE_CLOSE_STILL_QUALIFIED`. The last
branch requires intact CAS/durability/currentness under a prequalified restrictive
close mode. A store/selector fault cannot self-attest it and instead takes the
external physical-isolation/fresh-facility-key path below.

The budget is state-dependent. Checked
`PhysicalActuationFacilityOperationCostVector` fields count selector/commit
positions, durable/retained bytes, work, idempotency entries, hardware
authorizations and query/results, receipts and manifests, plus independent
lineage-anchor append/export positions, bytes and work. Qualification bounds every
fact, condition, candidate, head, receipt, manifest, token and proof.
`PhysicalActuationFacilityRetirementReceiptSchedule` gives each closed event one
exact row: a facility CAS counts condition, candidate, head, generic receipt/
manifest, specialized multiset and anchor bundle; hardware counts authorization,
query disposition and result; terminal evidence counts proof/read/work/response.
Per-member counts equal partition cardinality. Unknown/unbounded, zero, duplicate
or extra output rejects.

The sole facility selector owns
`PhysicalActuationFacilityHigherRegistryEnrollmentHead`, keyed by higher
principal/selector/store incarnation/history and facility key, with states
`RESERVE_PREPARED | CONFIRMED_ACTIVE | DRAIN_ONLY | PERMANENTLY_RETIRED`.
PREPARE alone inserts and writes
`PhysicalActuationFacilityPendingIntentAbortReserve`; protected reciprocal
evidence drives CONFIRM, BEGIN_DRAIN and retirement. Unconfirmed CANCEL races
CONFIRM and tombstones the reserve. Retirement also requires the terminal local
partition. The higher root cannot write/resize this reserve, and no terminal
state admits work.

Each admitted lineage preallocates a never-reused
`PhysicalActuationFacilityHigherRealmPendingIntentEnvelope`. Exactly
`PhysicalActuationFacilityRealmFullSetFenceCost(x) =
UnresolvedHigherPendingCost(x) + LocalRetainedInventoryCost(x) +
ExplicitEmptyEnvelopeCost(x) + OneCASFenceOutputCost(x)`.
The terms cover all nonterminal higher states and unused count through protected
drain acknowledgment; all local capacity/authorization/slot/token/invalidation
state; empty roots/proofs; and exact conditions, heads, receipts, anchor bundles,
protected exports and manifests. Pending conversion retains its charge through
higher terminalization.

Envelope admission/reuse, capacity, PREPARE and same-realm re-enrollment prove
every prospective vector dimension fits the one-CAS fence. OPEN CASs retain
`RequiredFacilityContinuationBudget`, the maximum over admitted authority and
closure traces. Registry/realm BEGIN freezes admission and installs
`RequiredFacilityClosureOnlyBudget` over only restrictive continuations.
Independent obligations add, exclusive branches take maximum, batch base/
marginal allocation is canonical, releases preserve floors, and FINALIZE proves
charge/cost/floor/remainder bijection. Wrong phase/cardinality, omitted term,
undercharge, underflow, overflow or cap-plus-one rejects.

BEGIN emits
`PhysicalActuationFacilityRegistryRetirementPreparationReceipt` and freezes
complete `PhysicalActuationFacilityRetirementRealmSet`, partitioning each
nonterminal realm by `PhysicalActuationFacilityRetirementRealmPriorState`
`OPEN_AT_FACILITY_RETIREMENT_BEGIN | ISOLATION_ALREADY_IN_PROGRESS`. OPEN freezes
all local capacity, consumed authorization/slot and path/neighbor obligations;
in-progress preserves origin/set/evidence exactly. Drain-only adds no capacity,
PREPARE, re-enrollment or epoch and claims neither realm loss, readable higher
state nor isolation.

OPEN members take the facility-retirement local-set branch; in-progress members
finish their installed origin, never relabel it, and `PERMANENTLY_ISOLATED`
never reopens.
`FINALIZE_PHYSICAL_ACTUATION_FACILITY_REGISTRY_RETIREMENT` requires exact
bijections to `PhysicalActuationFacilityRetirementRealmIsolationReceipt` or each
origin-matching final receipt, all realms permanently isolated, slots
`HARDWARE_RETIRED`, epochs eliminated, capacity terminal, retained tombstones and
remaining budget. Its CAS installs `PERMANENTLY_RETIRED` and emits
`PhysicalActuationFacilityRegistryRetirementReceipt` binding all frozen capacity/
authorization/realm/slot/path/hardware/effect/authority inventories. No return or
counter reset exists; overflow retires the affected identity or waits.

The facility head's bounded
`PhysicalActuationFacilityAuthorizationCapacityReservationLedgerHead` uses never-reused
`PhysicalActuationFacilityAuthorizationCapacityReservationKey` and closed states
`HELD_FOR_EXACT_HIGHER_AUTHORIZATION | CONSUMED_BY_FACILITY_RESERVATION |
CLOSED_BEFORE_HIGHER_AUTHORIZATION | CLOSED_UNUSED_AUTHORIZATION |
CLOSED_CONSUMED_AUTHORIZATION | CLOSED_BY_FACILITY_RETIREMENT`. Its permanent
per-`(AuthorityRealmKey, intended authorization identity)` index is
`CAPACITY_KEY_BOUND(capacity_key) | ABORTED_BEFORE_CAPACITY_RESERVATION`;
reserve requires typed nonmembership. Entries never reset, move or disappear.
HELD has no unilateral expiry and closes only by exact higher cancellation,
proved unused/consumed outcome, lost-realm full-set isolation or facility
retirement. Terminalization releases only the checked difference above its
retained floor, so finite lifetime capacity remains consumed.

Only `RESERVE_PHYSICAL_ACTUATION_FACILITY_AUTHORIZATION_CAPACITY`, in ACTIVE, can
install HELD. Its receipt-free
`PhysicalActuationFacilityAuthorizationCapacityReservationFact` binds the facility key, unique higher
identity, realm/slot/footprint/target store, protected higher pending-intent
verification, manifest authorization and current facility security, exact
realm-entry prior state, checked counters and
`PhysicalActuationFacilityAuthorizationCapacityCharge`. The charge is the
maximum of consumed and unused terminal branches, not their sum; each includes
full isolation-partition cost, and the charge includes the exact incremental
one-CAS full-realm fence cost. The higher artifact proves
`PENDING_FACILITY_CAPACITY` and its `AUTHORIZE_OR_CANCEL` reserve; a read or
historical artifact cannot authorize.

The sole CAS checks facility-global entry/byte/position/work totals while
preserving retirement reserve, and checks the complete prospective realm entry
against one-transaction fence member/byte/work bounds. All realms share global
totals. Equality passes; overflow/cap-plus-one creates no key, entry or receipt.
Exact retry does not recharge. The winner creates or compares the exact OPEN
realm entry, installs HELD and emits
`PhysicalActuationFacilityAuthorizationCapacityReservationReceipt` binding the
fact, charge, prior/installed facility and realm heads and commit. It grants no higher, slot,
epoch or hardware authority.

Closed release origin is `HIGHER_PREAUTHORIZATION_CANCELLATION |
HIGHER_LOST_DOMAIN_PENDING_INTENT_FROZEN`. Exact release consumes protected
higher cancellation verification and closed prior state
`NO_CAPACITY_ENTRY | MATCHING_HELD_CAPACITY_ENTRY`. In ACTIVE, the first branch
requires index nonmembership, installs only
`ABORTED_BEFORE_CAPACITY_RESERVATION`, preserves OPEN realm state or typed realm
nonmembership, and forbids a capacity key/charge/release delta. The second also
requires the exact OPEN realm entry, changes HELD to
`CLOSED_BEFORE_HIGHER_AUTHORIZATION` and preserves its terminal floor. Its
`PhysicalActuationFacilityAuthorizationCapacityReleaseReceipt` binds higher
evidence, identity, prior/installed heads, origin and
branch; the held branch also binds key and checked delta. A concurrent isolation/
retirement result is returned on exact retry. Delayed reserve loses to the
tombstone.

The facility head also binds one bounded canonical
`PhysicalActuationFacilityRealmFenceRegistryHead`. It has no independent
selector. Each entry is keyed by exact ADR-001 `AuthorityRealmKey` and retains
the complete local capacity-reservation set, consumed higher-root
physical-jurisdiction authorization set, authorization/slot mappings and every
exact unused-authorization tombstone. Its closed phase is
`OPEN_RESERVATION_AUTHORITY | ISOLATION_DRAIN_ONLY |
PERMANENTLY_ISOLATED`. The capacity-reserve event, not higher authorization or
reservation PREPARE, creates the first OPEN entry from typed nonmembership.
Every later reserve, reservation PREPARE, unused cancellation or same-realm
re-enrollment compares that same OPEN entry. A historical higher head, local
retirement receipt, matching realm label or higher authorization without its
exact still-held facility capacity entry grants nothing.

Exact `CANCEL_UNUSED_PHYSICAL_ACTUATION_FACILITY_RESERVATION_AUTHORIZATION`
consumes one higher authorization and its embedded capacity-reservation receipt
and compares the sole facility selector. It requires the matching capacity entry
to be `HELD_FOR_EXACT_HIGHER_AUTHORIZATION`, proves the authorization identity
absent from the complete consumed set and every prepared, reserved, installed or
handover slot, then atomically changes the capacity entry to
`CLOSED_UNUSED_AUTHORIZATION`, installs a permanent unused tombstone in the
realm entry and emits
`PhysicalActuationFacilityUnusedReservationAuthorizationReceipt`. The event can
run only while the facility and realm entry are ACTIVE/OPEN. PREPARE and
cancellation contend on the same selector and held capacity entry. If PREPARE
wins, cancellation returns the exact consumption result. If cancellation wins,
PREPARE loses. From a terminal facility root,
`PhysicalActuationFacilityTerminalAuthorizationNonmembershipEvidence` binds the
exact capacity key, complete retained authorization/slot inventory and
no-successor retirement receipt and replaces this mutation.

Closed `PhysicalActuationFacilityRealmIsolationOrigin` is
`AUTHORITY_REALM_LOST_DOMAIN_FULL_SET |
FACILITY_REGISTRY_RETIREMENT_LOCAL_SET`.
Each origin installs one total
`PhysicalActuationFacilityRealmIsolationSlotPriorState` partition for every
frozen consumed mapping. Its closed prior-state union is the complete slot union.
Closed `PhysicalActuationFacilityRealmIsolationSlotDisposition` is the second
column:

| Prior slot state | Installed isolation disposition |
|---|---|
| `UNASSIGNED_PHYSICALLY_ISOLATED` | `PRESERVE_TERMINAL_UNASSIGNED_CLOSURE` |
| `RESERVATION_PREPARED_NO_REALM_AUTHORITY` | `PREPARE_RESERVATION_INSTALLATION_INVALIDATION` |
| `RESERVATION_INSTALLATION_INVALIDATION_PREPARED` | `CONTINUE_RESERVATION_INSTALLATION_INVALIDATION` |
| `RESERVED_FOR_AUTHORITY_REALM_FENCED` | `PREPARE_RESERVED_EPOCH_INVALIDATION` |
| `RESERVED_EPOCH_INVALIDATION_PREPARED` | `CONTINUE_RESERVED_EPOCH_INVALIDATION` |
| `INSTALLED_FOR_AUTHORITY_REALM_FENCED` | `PREPARE_INSTALLED_EPOCH_INVALIDATION` |
| `INSTALLED_EPOCH_INVALIDATION_PREPARED` | `CONTINUE_INSTALLED_EPOCH_INVALIDATION` |
| `HANDOVER_FENCED` | `CLAIM_ELIMINATED_EPOCH_HANDOVER` |
| `HARDWARE_RETIRED` | `PRESERVE_HARDWARE_RETIREMENT` |

Closed
`PhysicalActuationFacilityRealmIsolationInvalidationContinuation` is
`ORIGINAL_OPERATION_REACHABLE_JOIN |
ORIGINAL_OPERATION_ABANDONED_RESTRICTIVE_TAKEOVER`. Both branches preserve the
same invalidation operation ID, token, epoch, hardware identities and query
result. The takeover branch additionally requires one
`ProtectedPhysicalActuationRestrictiveInvalidationDelegation`. Only the facility
isolation PREPARE CAS can create it. The protected artifact binds the original
invalidation authorization, digest and crash-complete source manifest, exact operation ID, installation and
invalidation tokens, epoch, path/hardware set, same-token query key, original
invoker, facility-authority delegate, installed isolation head/commit, origin
and `CONTINUE_EXISTING_INVALIDATION_ONLY` key use. It is written after that CAS
and exposed only in its crash-complete manifest. The hardware boundary verifies
its signature, facility history and exact installed isolation head, then JOINs
or queries the already named idempotent operation. It cannot create a second
operation, token, epoch, invalidation or result. An unreachable original invoker
changes only who may continue the restrictive call.

Each PREPARE row burns the installation token, enters its matching
invalidation-prepared state and emits one fresh original invalidation
authorization. Each CONTINUE row preserves the epoch, tokens and operation and
emits exactly one delegation only for the takeover branch. The handover row
allocates no token. Lost-domain closure can release or retire it. Facility
retirement can only retire its component. Terminal rows preserve their exact
closure evidence; facility retirement adds the required component-retirement
obligation. A duplicate, omission, row mismatch, changed token or delegation
without an installed original invalidation rejects.

`BEGIN_PHYSICAL_ACTUATION_FACILITY_REALM_ISOLATION` consumes the exact ADR-001
higher-root isolation-preparation receipt and its exact per-facility frozen
authorization set. This event is exclusively the
`AUTHORITY_REALM_LOST_DOMAIN_FULL_SET` origin; facility administrative or
capacity retirement cannot use that origin. It accepts only
`ACTIVE_FACILITY_REGISTRY`; if registry-retirement BEGIN committed first, this
event loses and ADR-001 must later use terminal facility full-set evidence. Its
closed
`PhysicalActuationFacilityRealmIsolationPriorState` is
`NO_LOCAL_REALM_ENTRY | OPEN_LOCAL_REALM_ENTRY`. From typed nonmembership, it
proves that no realm entry exists. Its frozen higher set can contain only
`PENDING_FACILITY_CAPACITY`,
`PREAUTHORIZATION_CANCELLATION_PENDING_FACILITY_RELEASE`, or
`CANCELED_BEFORE_AUTHORIZATION` with the exact global no-capacity abort index.
The transaction
installs an abort tombstone for each pending identity and rejects an issued or
consumed member as an inconsistent missing local entry. It then installs
`ISOLATION_DRAIN_ONLY` with
explicit empty capacity/slot roots. From OPEN, it changes that entry to
`ISOLATION_DRAIN_ONLY` and
freezes its complete local capacity set. In the same facility-selector CAS, both
branches project the complete frozen higher set exactly. Already terminal higher
entries remain terminal. Each pending or preauthorization-cancellation member
applies the exact no-entry-or-held partition. It installs the intent-abort
tombstone or closes the held entry and emits the capacity-release receipt with
origin `HIGHER_LOST_DOMAIN_PENDING_INTENT_FROZEN` or
`HIGHER_PREAUTHORIZATION_CANCELLATION`, respectively. Each issued but unconsumed
authorization changes its
held capacity entry to `CLOSED_UNUSED_AUTHORIZATION` and installs the unused
tombstone. Each consumed authorization maps to exactly one consumed slot. The
OPEN branch requires every local intended-identity index entry to match one
frozen higher-map entry. Omission or identity mismatch rejects. A concurrent
reservation PREPARE or same-realm re-enrollment either commits first and appears
in the consumed partition, or loses after the fence and appears unused. No new
authorization can enter the frozen higher set. The transaction applies the total
nine-state partition above. Hardware invalidation and lost-state physical
isolation then use the exact new or preserved queryable path for every consumed
member. It emits
`PhysicalActuationFacilityRealmIsolationPreparationReceipt` over the installed
origin, complete higher/local partition and exact per-slot dispositions.

Healthy facility retirement uses the distinct
`FACILITY_REGISTRY_RETIREMENT_LOCAL_SET` origin. Exact
`BEGIN_PHYSICAL_ACTUATION_FACILITY_REALM_ISOLATION_FOR_REGISTRY_RETIREMENT`
consumes the registry-retirement preparation receipt and exactly one member of
its frozen OPEN-realm set. It accepts only `RETIREMENT_DRAIN_ONLY` and that
still-OPEN entry, then freezes the complete locally held capacity-reservation and
consumed authorization/slot sets recorded at registry BEGIN. Its CAS installs
`ISOLATION_DRAIN_ONLY`, changes
every held capacity entry to `CLOSED_BY_FACILITY_RETIREMENT`, and moves every
consumed member through the total nine-state partition above. It emits
`PhysicalActuationFacilityRetirementRealmIsolationPreparationReceipt` over the
installed origin, frozen local set and exact invalidation authorizations. Because
registry BEGIN already prohibited new capacity reservations, PREPARE and
re-enrollment, the frozen local set cannot grow. This branch makes no claim about
the membership of the independently stored ADR-001 higher map and cannot
substitute for its lost-domain full-set partition.

Lost-domain isolation does not wait for the higher cut or permanent realm
tombstone before it can retire old facility authority. Exact
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_FOR_LOST_REALM_ISOLATION` consumes the
installed
`PhysicalActuationFacilityRealmIsolationPreparationReceipt`, its exact ADR-001
`AuthorityRealmExternalIsolationPreparationReceipt`, the frozen higher full set,
and one `FacilityAuthorityLostRealmSlotRetirementFact`. The fact binds the
consumed authorization/slot mapping, the exact least-fixed-point component and
complement proof, and a total component partition. Each non-target member must
already be `UNASSIGNED_PHYSICALLY_ISOLATED | HARDWARE_RETIRED`. Otherwise this
event rejects and complete facility retirement must freeze the other live realm.
The fact also binds independent actual isolation of every component path,
permanent retirement of every old hardware identity/incarnation, and exact new
or preserved invalidation-token query results. It does not consume or require
an ADR-001 isolation cut, realm tombstone, local jurisdiction-retirement receipt,
or readable local realm state.

The lost-realm CAS sets each consumed target and still-unassigned component
member to `HARDWARE_RETIRED`, closes its capacity entry, and retains unknown
local semantics. Per consumed mapping it emits one
`FacilityAuthorityLostRealmSlotRetirementReceipt` and one authorization-closure
receipt with branch `LOST_REALM_FACILITY_AUTHORITY_HARDWARE_RETIRED`. They prove
only facility/hardware retirement, so facility FINALIZE can precede the higher
cut without claiming local retirement.

Exact
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_DURING_FACILITY_REGISTRY_RETIREMENT`
instead consumes its local-origin preparation, matching mapping and
`PhysicalActuationFacilityRetirementSlotClosureFact`. After exact invalidation
or lost-hardware isolation, it permanently retires affected identities, installs
`HARDWARE_RETIRED` and `CLOSED_CONSUMED_AUTHORIZATION`, retains the physical
record and emits closure branch
`FACILITY_REGISTRY_RETIREMENT_HARDWARE_RETIRED`. It emits no local-semantic or
handover claim; no final path accepts that facility key/identity/epoch.

`FINALIZE_PHYSICAL_ACTUATION_FACILITY_REALM_ISOLATION` requires the installed
origin's exact bijection. Lost-domain covers every frozen higher member as
preserved terminal, pending/preauthorization release, issued-unused tombstone or
consumed-slot terminal evidence. Facility retirement covers every frozen local
capacity/mapping and claims no higher completeness. Both eliminate all epochs/
tokens and nonterminal old-realm slot states, close consumed capacity, retain
physical records and install `PERMANENTLY_ISOLATED`. Lost-domain emits
`PhysicalActuationFacilityRealmIsolationFenceReceipt`; local retirement emits
`PhysicalActuationFacilityRetirementRealmIsolationReceipt`, which cannot support
the higher cut. A lost-domain `HANDOVER_FENCED` member can become unassigned only
with its exact prior invalidation, eliminated epoch, handover record and closed
capacity; every other member needs terminal closure or the lost-realm retirement
receipt. Local-origin handover/unassigned components must become
`HARDWARE_RETIRED`. No relabel is allowed.

After final facility retirement, closed
`PhysicalActuationFacilityTerminalCapacityReservationClosureEvidence` is
`ABORT_TOMBSTONE_RETAINED | CAPACITY_ENTRY_CLOSED_BEFORE_CONSUMPTION |
TERMINAL_INTENDED_IDENTITY_NONMEMBERSHIP`. The branches bind, respectively, the
abort index; an exact never-consumed
`CLOSED_BEFORE_HIGHER_AUTHORIZATION | CLOSED_BY_FACILITY_RETIREMENT` key; or
typed nonmembership in both final uniqueness and capacity indexes while
forbidding a key. Authorization nonmembership additionally binds the exact key
and proves no consumed set/slot. Terminal realm-partition evidence projects
every frozen higher member to retained terminal, capacity closure, unused
tombstone or terminal consumed slot. All use the never-reopening retained
inventory; a live or remote absence read never suffices.

The facility registry's closed slot-owner state is
`UNASSIGNED_PHYSICALLY_ISOLATED |
RESERVATION_PREPARED_NO_REALM_AUTHORITY |
RESERVATION_INSTALLATION_INVALIDATION_PREPARED |
RESERVED_FOR_AUTHORITY_REALM_FENCED |
RESERVED_EPOCH_INVALIDATION_PREPARED |
INSTALLED_FOR_AUTHORITY_REALM_FENCED |
INSTALLED_EPOCH_INVALIDATION_PREPARED | HANDOVER_FENCED |
HARDWARE_RETIRED`. `UNASSIGNED_PHYSICALLY_ISOLATED` means no nonretired NCP
facility epoch can authorize a new effect through the covered paths. It does not
mean zero output, quiescence, benign stored energy, cleared latches or plant
safety. Every release retains a complete
`PhysicalActuationHandoverPhysicalStateRecord` of possible/unknown output and
interlock state. A new realm starts hardware/body state FENCED/HOLD and performs
plant-profile-specific inspection and reconciliation before any OPEN gate; no
universal zero-safe action is inferred.

Receipt-free `PhysicalActuationJurisdictionEnrollmentReservationFact` binds the
target ADR-001 `AuthorityRealmKey`, exact authority-domain/store incarnation and
qualification, immutable realm isolation envelope, exact facility slot and
complete canonical footprint/conflict neighborhood, plus closed
`PhysicalActuationSlotRealmAdmissionEvidence`:
`NEVER_ASSIGNED_SLOT | SAME_AUTHORITY_REALM_REENROLLMENT |
PRIOR_AUTHORITY_REALM_PERMANENTLY_RETIRED`. The last branch consumes the exact
ADR-001 higher-root permanent realm tombstone; remote absence or local
jurisdiction retirement cannot substitute. The middle branch consumes exact
`PhysicalActuationSameAuthorityRealmReenrollmentEqualityEvidence`. It binds
byte-equality of the old and fresh `AuthorityRealmKey`, server authority
principal, stable realm ID, immutable realm-isolation envelope, facility key,
slot, footprint/component and target domain/store, plus the still-installed
higher enrollment and current OPEN facility-realm entry. It also proves the old
authorization is the exact closure-ready consumed mapping and the old epoch is
eliminated; only the winning re-enrollment CAS closes that authorization. A projection, renamed
store, widened envelope or merely textually equal caller label rejects. Every
branch also binds a fresh
`AuthorityRealmPhysicalJurisdictionReservationAuthorizationReceipt`, its
embedded
`PhysicalActuationFacilityAuthorizationCapacityReservationReceipt`, the matching
`HELD_FOR_EXACT_HIGHER_AUTHORIZATION` capacity entry and the exact current
`OPEN_RESERVATION_AUTHORITY` realm entry. Closed
`PhysicalActuationFacilityRealmReservationPriorState`
`NO_LOCAL_REALM_ENTRY | OPEN_LOCAL_REALM_ENTRY` applies to the earlier facility
capacity-reserve event: the first branch creates the entry, and the second
compares its current OPEN head. PREPARE itself never creates a realm entry.
Exact
`PREPARE_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_FOR_AUTHORITY_REALM`
compare-and-swaps the active facility selector, verifies the slot and every graph
neighbor against the closed availability predicate, verifies that a different
target realm has permanently passed the old realm's immutable physical-isolation-
envelope authority, proves that the precharged realm still fits its full-fence
bound, atomically changes the exact held capacity entry to
`CONSUMED_BY_FACILITY_RESERVATION`, records the higher authorization identity as
consumed, reserves only the additional slot/hardware closure delta, and installs
`RESERVATION_PREPARED_NO_REALM_AUTHORITY` with checked-next never-reused
`PhysicalActuationJurisdictionFencingEpoch` and one-use hardware-installation
token. Its post-CAS
`PhysicalActuationFacilityReservationAuthorizationConsumptionReceipt` binds the
higher authorization, exact prior/installed realm entry, authorization set,
slot, prepared head and facility commit. The realm has no invocation authority
in that state.

For this PREPARE, the target slot must be exactly
`UNASSIGNED_PHYSICALLY_ISOLATED`. Every distinct conflict-neighbor slot must be
exactly `UNASSIGNED_PHYSICALLY_ISOLATED | HARDWARE_RETIRED`. A prepared,
reserved, installed, invalidation-prepared or `HANDOVER_FENCED` neighbor is not
available. Same-realm re-enrollment from a target `HANDOVER_FENCED` slot is the
separate PREPARE-equivalent event below. It applies this identical complete-
neighborhood predicate in the same facility CAS. Unknown state or an omitted
neighbor rejects.

Post-CAS
`PhysicalActuationJurisdictionHardwareFenceInstallationAuthorization` binds the
facility commit receipt, prepared head, exact slot/path set, target realm/store,
hardware identities/incarnations, token and epoch. No candidate or caller token
can drive the boundary. Idempotent/queryable hardware event
`INSTALL_PHYSICAL_ACTUATION_JURISDICTION_FENCING_EPOCH` consumes that exact
authorization, serializes it against same-token invalidation, installs the epoch
at every final path in non-actuating FENCED state, and returns
`PhysicalActuationJurisdictionHardwareFenceInstallationReceipt`. Exact
`CONFIRM_PHYSICAL_ACTUATION_JURISDICTION_RESERVATION_AFTER_HARDWARE_FENCE`
consumes that complete boundary receipt, moves only the matching prepared slot to
`RESERVED_FOR_AUTHORITY_REALM_FENCED`, and emits one-use target-store-bound
`PhysicalActuationJurisdictionEnrollmentReservationReceipt`. An unknown hardware
result keeps the slot prepared and unavailable until same-token query resolves;
it cannot allocate a different epoch or realm.

Facility qualification includes durable
`PhysicalActuationBoundaryEnrollmentState` at every final path. It binds the
immutable hardware identity, never-reused hardware-state incarnation,
authenticated current facility owner/epoch, installation-token disposition,
monotonic epoch high-water and retired-epoch set. It rejects rollback and stale
epochs across power loss, reset, firmware change, restore and controller cloning.
Restart restores that exact authenticated state or enters non-actuating
`ENROLLMENT_STATE_UNTRUSTED`; it cannot infer the latest epoch from a request.
Recovery from untrusted state requires complete physical isolation and permanent
retirement of the old hardware identity/incarnation. A UUID, volatile counter or
server database receipt alone is not a physical fence.

`ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_PHYSICAL_JURISDICTION_ENROLLMENT`
consumes the reservation receipt through ADR-001 fresh
`CANDIDATE_PARTICIPANT_ADMISSION`: it proves typed selector absence/never-used,
and atomically installs the native realm-local registry, participant entry,
domain-state/reserve successor and state `PENDING_FACILITY_CONFIRMATION`. The
facility event `CONFIRM_PHYSICAL_ACTUATION_JURISDICTION_ENROLLMENT` consumes its
exact native genesis/participant-admission receipt, advances the same facility
slot to `INSTALLED_FOR_AUTHORITY_REALM_FENCED`, and emits
`PhysicalActuationJurisdictionEnrollmentReceipt`. Exact
`ACTIVATE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_FACILITY_CONFIRMATION`
consumes that receipt and alone moves the matching local registry to
`ACTIVE_REGISTRY`. No domain reservation, body genesis, gate opening or
invocation is legal while pending. Reply loss queries and resumes the same exact
step; it never reserves another realm, slot or epoch.

Before local registry genesis, target-store
`CANCEL_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_BEFORE_CREATION` consumes the
same facility reservation receipt and atomically installs a permanent genesis-
canceled tombstone at the jurisdiction-selector key. It emits
`ActuationAuthorityDomainRegistryGenesisCancellationReceipt`; genesis and
cancellation compare the same target-store key. After genesis but before local
activation, `RETIRE_UNCONFIRMED_ACTUATION_AUTHORITY_DOMAIN_REGISTRY` can install
`RETIRED_FOR_TOPOLOGY_CHANGE` only from the original pending/empty registry, with
no domain reservation, arbiter, body or operation history. It emits
`ActuationAuthorityDomainUnconfirmedRegistryRetirementReceipt`. The local
retirement can commit before or after facility confirmation, but it races local
activation on the same local selector. If activation wins, unconfirmed
retirement loses and normal active retirement is required. If unconfirmed
retirement wins, a delayed facility confirmation can still commit independently
from its historical genesis receipt, but it cannot reactivate the retired local
selector. The installed handover branch below joins the exact facility
confirmation and local retirement receipts and proves that no activation receipt
or ACTIVE local head ever existed. Thus neither cross-store commit order strands
the slot or invents a distributed transaction.

Every ADR-007 boundary-operation token and hardware request binds the facility,
slot, physical jurisdiction, exact current fencing epoch and final enrollment
receipt. The final hardware boundary validates all of them before any effect.

Every issued installation token has a total restrictive exit. Facility CAS
`PREPARE_PHYSICAL_ACTUATION_JURISDICTION_EPOCH_INVALIDATION` moves
`RESERVATION_PREPARED_NO_REALM_AUTHORITY |
RESERVED_FOR_AUTHORITY_REALM_FENCED |
INSTALLED_FOR_AUTHORITY_REALM_FENCED` to the matching
`RESERVATION_INSTALLATION_INVALIDATION_PREPARED |
RESERVED_EPOCH_INVALIDATION_PREPARED |
INSTALLED_EPOCH_INVALIDATION_PREPARED`. It burns the installation token in the
facility candidate and emits post-CAS
`PhysicalActuationJurisdictionHardwareEpochInvalidationAuthorization` over the
exact installed head, complete path set, hardware identities, epoch and fresh
one-use invalidation token. Confirmation, release, handover or old installation
prepared against the earlier head then loses.

Idempotent/queryable hardware event
`INVALIDATE_PHYSICAL_ACTUATION_JURISDICTION_EPOCH_AND_ISOLATE` consumes that
authorization, serializes against the original installation token, durably
tombstones both tokens and the epoch whether installation occurred before or
after the invalidation race, leaves every covered boundary FENCED, and emits
`PhysicalActuationJurisdictionHardwareEpochInvalidationReceipt`. A later stale
installation authorization rejects. An unknown result leaves the slot in its
invalidation-prepared state until same-token query resolves. Closed
`PhysicalActuationHardwareEpochEliminationEvidence` is
`EXACT_HARDWARE_INVALIDATION_RECEIPT |
LOST_HARDWARE_STATE_COMPLETE_COMPONENT_ISOLATED_IDENTITIES_RETIRED`. The second
branch consumes `PhysicalActuationLostHardwareStateIsolationFact`, which requires
the exact least-fixed-point component and complement proof above, independent
actual isolation of that complete component, and permanent retirement of every
affected hardware identity. It can lead only to `HARDWARE_RETIRED`, never back
to an available old identity.

`RETIRE_PREPARED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_EPOCH_INVALIDATION`
consumes that evidence from
`RESERVATION_INSTALLATION_INVALIDATION_PREPARED`. The exact-receipt branch
returns the slot to `UNASSIGNED_PHYSICALLY_ISOLATED`; the lost-hardware branch
installs `HARDWARE_RETIRED`. Both retain realm/slot/token/epoch and physical-state
tombstones, change the matching capacity entry to
`CLOSED_CONSUMED_AUTHORIZATION` and emit
`PhysicalActuationFacilityReservationAuthorizationClosureReceipt`. If neither
proof exists, the slot remains unavailable forever.

The closed `PhysicalActuationJurisdictionReservedAbandonmentEvidence` is
`NO_LOCAL_REGISTRY_GENESIS_CANCELED |
UNCONFIRMED_LOCAL_REGISTRY_RETIRED`. The first branch consumes the
target-store genesis-cancellation tombstone/receipt. The second consumes exact
retirement of a genesis-only pending local registry. Exact
`ABANDON_RESERVED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_EPOCH_INVALIDATION`
consumes one branch plus the hardware-elimination evidence. Exact invalidation
returns the slot to `UNASSIGNED_PHYSICALLY_ISOLATED`; lost hardware installs
`HARDWARE_RETIRED`. It retains every uncertainty, changes the matching capacity
entry to `CLOSED_CONSUMED_AUTHORIZATION`, emits the exact authorization-closure
receipt and races delayed facility confirmation on the one facility selector.
Realm-state loss cannot use this event. It uses only the cut-independent
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_FOR_LOST_REALM_ISOLATION` edge after the
ADR-001 PREPARE receipt; facility FINALIZE then enables the higher cut.

The closed `PhysicalActuationJurisdictionInstalledHandoverEvidence` is
`EXACT_ACTIVE_LOCAL_JURISDICTION_RETIREMENT |
UNCONFIRMED_EMPTY_LOCAL_REGISTRY_RETIRED_WITHOUT_ACTIVATION`. The first branch requires complete
closure of this jurisdiction's local registry, bodies, arbiters, operations and
jurisdiction-scoped credentials; it does not retire other disjoint jurisdictions
or the whole realm. The second binds both the exact facility confirmation and
genesis-only local retirement receipts in either commit order, the installed
retired local head, and typed absence of any activation receipt or ACTIVE
ancestry. Realm-state loss is structurally forbidden here and follows only the
PREPARE-bound lost-realm retirement edge above. No branch waits for an ADR-001
cut or permanent realm tombstone.

Exact `BEGIN_PHYSICAL_ACTUATION_JURISDICTION_HANDOVER` consumes one installed
branch plus hardware-elimination evidence from
`INSTALLED_EPOCH_INVALIDATION_PREPARED`. Exact invalidation moves the slot to
`HANDOVER_FENCED`; lost hardware moves it to `HARDWARE_RETIRED`, changes the
matching capacity entry to `CLOSED_CONSUMED_AUTHORIZATION` and emits the exact
authorization-closure receipt. The normal
retirement order is jurisdiction-local/body closure, realm-domain closure when
otherwise required, facility epoch invalidation, handover and release. ADR-001
domain finalization requires only the old hardware epoch to remain FENCED; it
does not wait for facility release, so the two roots do not deadlock.

Only from `HANDOVER_FENCED` can
`RELEASE_PHYSICAL_ACTUATION_JURISDICTION_AFTER_ISOLATION` return the slot to
`UNASSIGNED_PHYSICALLY_ISOLATED`, or
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_HARDWARE` can install
`HARDWARE_RETIRED`. Both events retain prior realm/jurisdiction/path/epoch
tombstones, the cross-realm admission barrier and physical-state handover record.
Each event also emits
`PhysicalActuationFacilityReservationAuthorizationClosureReceipt` for the exact
consumed authorization whose old epoch can no longer authorize any effect. The
receipt binds the prior/installed facility heads and selector, authorization
identity, slot, eliminated epoch/token, physical-state record and selected
release/retirement branch. Both change the old capacity entry to
`CLOSED_CONSUMED_AUTHORIZATION`.

Same-realm re-enrollment is the separate exact event
`PREPARE_HANDOVER_FENCED_SLOT_REENROLLMENT`. It requires a fresh higher-root
physical-jurisdiction authorization receipt and its protected cross-store
verification, its exact still-held facility capacity reservation, and the exact
`SAME_AUTHORITY_REALM_REENROLLMENT` branch with
`PhysicalActuationSameAuthorityRealmReenrollmentEqualityEvidence`. It also
requires the exact
`OPEN_RESERVATION_AUTHORITY` facility-realm fence entry and the same complete
neighbor-state predicate as initial PREPARE. In one facility CAS, it closes the
old authorization and capacity entry, consumes the fresh held capacity entry,
records the fresh authorization in the complete consumed set, allocates a
checked-next never-used epoch and fresh one-use installation token, and moves
`HANDOVER_FENCED -> RESERVATION_PREPARED_NO_REALM_AUTHORITY`. It emits the old
authorization-closure receipt, the fresh
`PhysicalActuationFacilityReservationAuthorizationConsumptionReceipt`, and a
fresh `PhysicalActuationJurisdictionHardwareFenceInstallationAuthorization`.
The standard idempotent hardware INSTALL and facility CONFIRM transitions then
move the prepared slot through `RESERVED_FOR_AUTHORITY_REALM_FENCED`. No
enrollment receipt, invocation right, body authority or OPEN gate exists before
that confirmation chain completes.

The event loses to realm isolation, unused-authorization cancellation or
facility retirement on the facility selector. A `PERMANENTLY_ISOLATED` realm
entry can never use it. A stale handover head, reused epoch/token, direct
`HANDOVER_FENCED -> RESERVED_FOR_AUTHORITY_REALM_FENCED` jump, or omitted
installation query rejects.
A different realm can prepare the released slot only after the exact prior-realm
permanent higher-root tombstone. This prevents a later old-realm full-envelope
isolation cut from targeting hardware already assigned to another live realm,
while allowing disjoint jurisdictions and same-realm local re-enrollment without
retiring the whole realm. A stale old-realm database can
still propose work, but every final boundary rejects its retired epoch; no local
receipt can relabel that request as applied.

`PhysicalActuationFacilityReservationAuthorizationClosureReceipt` has closed
producer discriminant
`LOST_REALM_FACILITY_AUTHORITY_HARDWARE_RETIRED |
FACILITY_REGISTRY_RETIREMENT_HARDWARE_RETIRED |
PREPARED_RESERVATION_EPOCH_ELIMINATED |
RESERVED_LOCAL_REGISTRY_ABANDONED |
INSTALLED_LOCAL_REGISTRY_LOST_HARDWARE_RETIRED |
HANDOVER_RELEASED_TO_UNASSIGNED |
HANDOVER_HARDWARE_RETIRED |
SAME_REALM_REENROLLMENT_REPLACED`.
The producer mapping is exact: the branches map respectively to
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_FOR_LOST_REALM_ISOLATION`,
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_DURING_FACILITY_REGISTRY_RETIREMENT`,
`RETIRE_PREPARED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_EPOCH_INVALIDATION`,
`ABANDON_RESERVED_PHYSICAL_ACTUATION_JURISDICTION_AFTER_EPOCH_INVALIDATION`,
the lost-hardware branch of
`BEGIN_PHYSICAL_ACTUATION_JURISDICTION_HANDOVER`,
`RELEASE_PHYSICAL_ACTUATION_JURISDICTION_AFTER_ISOLATION`,
`RETIRE_PHYSICAL_ACTUATION_JURISDICTION_HARDWARE`, and
`PREPARE_HANDOVER_FENCED_SLOT_REENROLLMENT`. The BEGIN exact-
invalidation branch emits zero closure receipts because the authorization
remains owned in `HANDOVER_FENCED`. The lost-realm batch emits exactly one
receipt for each member of its complete consumed-mapping partition. Every other
listed producer emits exactly one for its selected authorization. Every
unlisted event emits zero.

The receipt binds producer event/operation, discriminant, ordinal and batch
cardinality, authorization identity, capacity key, realm, slot, prior/installed
facility and realm heads, eliminated epoch/tokens, exact nested hardware and
local-closure evidence branches, installed terminal capacity state and physical-
state record. For a batch, ordinals are canonical, unique and cover
`[0, cardinality)` with a bijection to consumed mappings. The receipt schedule,
generic commit receipt, protected export and persistence manifests carry the
same cardinality. A zero-for-required, duplicate, extra, wrong-producer or
cross-branch receipt rejects before ADR-001 can consume it.

Unassigned hardware retirement covers a complete component. The facility head's
bounded `PhysicalActuationUnassignedHardwareRetirementIntentHead` records the
one-use PREPARE from an unassigned target, exact component/hardware set and
no-crossing complement proof. It blocks reservation, release, re-enrollment and
epoch installation on that set.

Receipt-free preparation binds every affected slot/path/epoch/token and closed
disposition `ALL_AFFECTED_NEIGHBORS_TERMINAL_OR_UNASSIGNED |
ATOMICALLY_PREPARED_EVERY_AFFECTED_LIVE_EPOCH_FOR_INVALIDATION`. The first
requires every other member unassigned or hardware-retired. The second, in the
same CAS, moves every affected prepared/reserved/installed member to its matching
invalidation-prepared state, burns installation tokens and emits exact
invalidation authorizations. `HANDOVER_FENCED`, another operation's invalidation,
unknown or omitted state rejects. The preparation receipt binds the total
partition and outputs.

`RETIRE_UNASSIGNED_PHYSICAL_ACTUATION_JURISDICTION_HARDWARE` consumes that receipt,
all elimination receipts and independent actual-isolation/permanent-identity-
retirement evidence. Its final CAS requires every member unassigned or retired,
makes every still-unassigned member over a retired path/identity
`HARDWARE_RETIRED`, closes the intent and emits its receipt. It cannot leave a
neighbor available, replace identity or infer safe output. Facility drain runs
this once per component without a dummy reservation.

The facility registry is an independently qualified physical root, not an
ADR-001 cross-store transaction participant. A remote registry read is never
realm-local command currentness. Loss or ambiguity of its selector makes every
possibly owned/conflicting slot unavailable. It cannot emit a facility full-set
fence receipt or a terminal facility inventory.

Closed `LostPhysicalActuationFacilityStateCompleteComponentIsolationEvidence`
is the sole external closure branch. It binds lost facility/selector/store
incarnation, qualification, immutable incidence/conflict inventory, ADR-001
higher preparation/frozen set and closed
`LostPhysicalActuationFacilityLastAuthenticatedRootEvidence`
`EXACT_FINAL_AUTHENTICATED_FACILITY_ROOT_NO_SUCCESSOR |
UNKNOWN_LAST_AUTHENTICATED_FACILITY_ROOT`. Exact requires protected
terminalization verification in
`PhysicalActuationFacilityFinalHighWaterNoSuccessorEvidence`. It binds the lost
selector/store incarnation, final version/position/root, last append inclusion,
terminal high-water, signed history and no-successor. Its only audience is
`ISOLATE_LOST_PHYSICAL_ACTUATION_FACILITY_COMPLETE_COMPONENT_SET`; its isolation
commit records the one-use key. Cache, observation, unanchored history or bare
evidence fails; absent/ambiguous protected evidence forces unknown and seeds `U`.

Both branches produce
`LostPhysicalActuationFacilityCompleteComponentPartition`: canonical
least-fixed-point components under `R`, ordered by each component's smallest
slot. Components are disjoint and cover `U`; each binds complement proof and
member-derived `P(C)/H(C)/E(C)/A(C)`. Their projections cover `P/H/E/A`, and
each path-ledger key maps to its unique component. Exact maps every final-root/
frozen-higher member; unknown repeatedly seeds the smallest uncovered slot.

Independent physical-isolation authority attests every `P` path and component
hardware/effect/authority projection isolated, every old epoch/token/credential/
facility/hardware identity permanently retired, and no resume after restore/
clone/delay. Its frozen-higher bijection selects terminal authorization, proved
unused, or possibly consumed with retired complete component. It claims no
facility/local commit. Missing inventory, complement, retirement or barrier
rejects.

Recovery requires genesis under a fresh never-used facility key/store/selector
and hardware inventory. Software cannot reconstruct the old selector or reuse an
epoch. If the facility authority cannot prove the old key will never be reused,
plant activation remains disabled. Live facility ownership, hard-fence, loss
recovery, cross-provider overlap and physical isolation evidence remain external
pre-release gates and are **NOT RUN** for this candidate.

One stable `PhysicalActuationJurisdictionKey` identifies the qualified physical
installation within which any effect/authority paths can interact. It has a
never-reused registry incarnation. The stable `ActuationAuthorityDomainKey`
derives from that jurisdiction/incarnation plus one immutable
`ActuationAuthorityDomainFootprint`. The footprint covers every shared
physical effect and authority path, not only Active actuator channels: actuator
and channel partitions, drive/power buses, watchdog expiry, HOLD clear, ESTOP
latch/interlock, reset and handover authority. One domain can cover multiple
actuators only when that enrolled boundary supplies the atomic ordering and body-
global HOLD/ESTOP semantics required by this ADR. The key excludes logical
session, generation, lease/term, profile revision/digest, security epoch and
every caller label. A profile can reference an enrolled key; it cannot mint a new
key or change its footprint.

One plant-session generation binds exactly one
`ActuationAuthorityDomainKey`. Zero keys, multiple keys, or a command naming a
different key reject. Independent domains use independent plant sessions and
authority lineages. NCP does not claim atomic application, HOLD or ESTOP across
those sessions. If coordinated multi-actuator semantics are required, the plant
profile must bind one qualified enrolled domain whose physical boundary provides
that atomicity; a software list of independent keys is insufficient. This
single-domain rule keeps the generation-global lifecycle and fail-safe result
meaning identical to the physical ordering domain.

The jurisdiction authority owns one bounded `ActuationAuthorityDomainRegistryHead`
through its sole `InstalledActuationAuthorityDomainSelector`, keyed only by the
stable `PhysicalActuationJurisdictionKey`. The never-reused registry incarnation
is versioned head content, not part of the selector key, so qualified re-enrollment
can advance it without creating a second currentness root. The registry maps
every enrolled `ActuationAuthorityDomainKey` and controlling body enrollment to
exactly one durable
`BodyActuationArbiterStateHead` and binds the immutable enrolled
`ActuationAuthorityDomainConflictGraph`. It also binds the facility key,
complete physical-path component, current never-reused hardware fencing epoch
and `PhysicalActuationJurisdictionEnrollmentReceipt`; no local successor can
change them. A conflict edge exists when two
footprints overlap on any physical effect or authority path. There is no per-key
or per-session selector. Every registry transition preserves all unaffected map
entries and the graph byte-for-byte. Its closed registry state is
`PENDING_FACILITY_CONFIRMATION | ACTIVE_REGISTRY |
RETIRED_FOR_TOPOLOGY_CHANGE`; only the active branch admits a
domain transition. A keyed head's closed owner state is
`UNOWNED_PHYSICALLY_ISOLATED |
RESERVED_FOR_GENERATION_GENESIS_FENCED |
RESERVED_PARTIAL_RETIREMENT_FENCED |
RESERVED_PARTIAL_RETIREMENT_RETIRED |
OWNED_BY_GENERATION_FENCED | OWNED_BY_GENERATION_ACTIVE |
OWNER_HANDOVER_FENCED | DOMAIN_RETIRED`. Every owned/reserved branch binds the
exact logical session/generation, parent lineage creation receipt, body-control
head/mirror status and owner-lineage tombstones. Only
`OWNED_BY_GENERATION_ACTIVE` can contain an OPEN gate. A second logical session,
different generation, profile revision or security epoch cannot own or activate
the same key. Concurrent plant sessions are legal only when the enrolled conflict
graph proves their keys nonadjacent. A profile assertion alone is not such proof.

The jurisdiction enrollment also binds one ADR-001
`AuthorityTransactionDomainKey` and its content-addressed qualification digest.
The registry selector, each admitted parent lineage and required child selector,
the body composite selector and the local security-authority selector must share
that exact key before any plant reservation. This is a placement invariant, not
a caller field and not evidence that their logical owners are the same. The
qualification must cover every multi-selector conditional compare and complete
bundle size used below. A remote read, cached receipt or independently committing
store cannot satisfy it. If the jurisdiction cannot share one qualified atomicity
domain with the plant provider, the provider can expose simulation or observer
roles, but plant genesis and command admission remain closed.

Every realm-local ADR-007 authority-domain/body event constructs the applicable ADR-001
`AuthorityTransactionCASCondition`. Its participant set always contains
`AUTHORITY_TRANSACTION_DOMAIN_STATE` and the registered jurisdiction-registry/
arbiter selector; body, parent-lineage and local-security selectors are mandatory
whenever the event reads or changes their authority. The condition binds exact
participant-registry membership, shared domain/store incarnation, ACL, complete
read/write set and retirement-reserve delta. Receipt-free event facts exclude
the condition, candidates and receipts; candidates bind fact plus condition. The
winning `AuthorityTransactionCommitReceipt` precedes every domain, arbiter, body
and event-specific receipt, and the final non-authorizing persistence manifest
attests their complete durable bundle. A key-equality assertion, pre-read,
unregistered participant, incomplete receipt set or missing reserve update cannot
implement an event. The physical device effect remains outside storage atomicity
and still requires the independent idempotent arbiter/watchdog evidence and
restrictive orphan reconciliation below.
Facility-registry events instead compare only their independent installed
facility selector and emit its generic/specialized facility receipts. Hardware
epoch installation/invalidation uses the exact one-use, idempotent/queryable
boundary protocol and never claims either storage CAS.

Every realm-scoped ADR-007 descriptor, command/declaration identity, authority/
freshness grant, journal record/head, body/arbiter operation, value reference,
application evidence, disposition and receipt directly binds the exact neutral
ADR-001 `AuthorityRealmKey` and full source-kind/logical-session/generation
identity. All foreign-key joins require exact equality. The facility root binds a
target realm only while its slot is prepared/reserved/installed; unassigned
facility state is not silently realm-scoped. A literal `{realm}` route segment,
transitive receipt ancestor or identical session bytes cannot replace the direct
field. Missing/default/mismatched realm rejects before authority or semantic
allocation.

`ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_PHYSICAL_JURISDICTION_ENROLLMENT`
uses ADR-001 `CANDIDATE_PARTICIPANT_ADMISSION`, consumes the one-use
`PhysicalActuationJurisdictionEnrollmentReservationReceipt`, and installs the
complete bounded body/domain inventory and registry once in
`PENDING_FACILITY_CONFIRMATION`, with
each entry `UNOWNED_PHYSICALLY_ISOLATED` and its qualified physical-isolation
evidence. Its native genesis and participant-admission receipts follow the
ADR-001 transaction DAG. Exact
`ACTIVATE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_FACILITY_CONFIRMATION`
consumes the facility enrollment receipt and moves only that matching registry
to `ACTIVE_REGISTRY`; it creates no domain owner. Before body-session genesis,
`RESERVE_ACTUATION_AUTHORITY_DOMAIN_FOR_GENERATION` consumes the exact ADR-001
generation-creation receipt, conditionally compares that the same parent remains
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS` with no partial-retirement prepared
head, verifies that receipt's single domain key, and moves
that entry to `RESERVED_FOR_GENERATION_GENESIS_FENCED`. The same registry CAS
verifies every graph-adjacent entry is `UNOWNED_PHYSICALLY_ISOLATED`, so two
concurrent reservations for differently named but overlapping domains cannot
both win. Its subordinate
`BODY_ACTUATION_ARBITER_STATE_GENESIS_FROM_DOMAIN_RESERVATION` transition installs
the fresh FENCED arbiter genesis. The domain transition emits one
`ActuationAuthorityDomainReservationReceipt` and one complete
`BodyActuationArbiterTransitionReceiptSetRoot`. Neither candidate head binds
these post-CAS receipts. The reservation fact and receipt bind the exact target
key, complete canonical conflict set, prior/installed registry heads and selector
version. A conflicting owner, wrong key, omitted conflict or overlapping enrolled
boundary rejects the plant session. The parent comparison and registry mutation
commit through their shared authority transaction domain. Sampling the parent
before a separate registry commit leaves the delayed-reservation race open and
does not implement this event.

Body genesis consumes the reservation receipt and exact arbiter-genesis receipt
set once through fresh ADR-001 participant admission. Its common CAS compares
typed body-selector absence/never-used, the parent still selecting this exact
generation in `GENERATION_ALLOCATED_PENDING_CHILD_GENESIS`, current local
security, and the exact still-installed
`RESERVED_FOR_GENERATION_GENESIS_FENCED` jurisdiction/arbiter head; a historical
receipt cannot survive a winning cancellation. It atomically installs the body
selector/head, participant entry and reserve, including one
`BodyActuationArbiterMirror` for that reserved domain head. This first body head
remains non-authorizing. Next, receipt-free
`ActuationAuthorityDomainGenerationConfirmationFact` binds that body-genesis
head and receipt, the exact reserved domain head/key, registry head/version and
typed nonmembership of a prior confirmation.
`CONFIRM_ACTUATION_AUTHORITY_DOMAIN_GENERATION_GENESIS` writes the jurisdiction
registry and authority-domain state in one common transaction while
conditionally comparing that the exact ADR-001 parent remains
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS`, local security remains current and
the body selector still selects the body-genesis head bound by the fact. It moves the keyed entry to
`OWNED_BY_GENERATION_FENCED`, and emits
`ActuationAuthorityDomainGenerationConfirmationReceipt` over the fact,
prior/installed domain and registry heads and selector version. The candidate
domain head binds the fact and installed body-genesis head, never a future body
successor or post-CAS receipt.

Next, `RECONCILE_BODY_ACTUATION_DOMAIN_GENERATION_GENESIS` compare-and-swaps the
body selector, consumes that confirmation receipt and verifies the exact current
registry head. It normally requires the allocated-pending parent. The sole
exception is a frozen `GENERATION_PARTIAL_RETIREMENT_PREPARED` parent whose exact
preparation fact already binds this installed confirmation and body-genesis head;
that exception is non-authorizing and can lead only to partial BEGIN and
retirement. It installs a body successor whose mirror names the owned/FENCED
domain successor and emits
`BodyActuationDomainGenerationReconciliationReceipt` over both transitions. Only
that reconciliation receipt can let ADR-001 confirm the logical generation as
live. The intermediate mismatch is HOLD/FENCED and non-authorizing; it cannot
issue a grant, open a gate or accept a command. Reply loss recovers the same
reservation, genesis, confirmation or reconciliation. It
cannot allocate a sibling session, substitute a domain or create another arbiter.

All arbiter activation, fence, operation, retention and retirement transitions
compare-and-swap this global registry selector, so domain ownership and physical order
cannot diverge. A body control transition conditionally verifies that selector
and consumes or reconciles its complete receipt set. Every command names the
generation's exact domain.

Release or owner handover requires FENCED state, the complete retirement-closure
union, predecessor body/ADR-001 finalization and no pending semantic
reconciliation. Exact physical quiescence can release the keyed entry to
`UNOWNED_PHYSICALLY_ISOLATED` or reserve it once for the one parent-authorized
successor generation. Lost/corrupt registry-selector state cannot be recreated or
released by software; every potentially affected footprint remains unavailable
until qualified external isolation or hardware replacement establishes a new
immutable enrolled registry identity.

The domain-owner edges are explicit. Before body genesis,
`CANCEL_ACTUATION_AUTHORITY_DOMAIN_RESERVATION_BEFORE_BODY_GENESIS` alone can move
`RESERVED_FOR_GENERATION_GENESIS_FENCED -> UNOWNED_PHYSICALLY_ISOLATED`. It
consumes the exact ADR-001 `LogicalSessionGenerationAbortIntent`, proves typed
nonmembership of the body child selector, and proves that the genesis arbiter is
still FENCED with no operation, output or invocation right. It retains the
canceled generation, arbiter incarnation, gate epoch and marker tombstones. It
emits `ActuationAuthorityDomainReservationCancellationReceipt`, which the parent
abort consumes. A missing body selector is not nonmembership, and any installed
body genesis requires normal body retirement instead.

If another required child installed but the body child did not,
`CANCEL_ACTUATION_AUTHORITY_DOMAIN_RESERVATION_DURING_PARTIAL_PARENT_RETIREMENT`
is the disjoint cancellation edge. It consumes the exact ADR-001
`LogicalSessionGenerationPartialRetirementPreparationReceipt`, whose frozen
partition proves body-selector nonmembership and the unused body marker while at
least one other required child is installed. It also requires the exact still-
reserved registry head and genesis arbiter zero-history proof. Its registry CAS
returns the domain to `UNOWNED_PHYSICALLY_ISOLATED` and emits the same typed
`ActuationAuthorityDomainReservationCancellationReceipt`. That receipt's closed
cause is `ALL_CHILDREN_ABSENT_PARENT_ABORT |
BODY_CHILD_ABSENT_PARTIAL_PARENT`; each cause requires and forbids its exact
abort-intent or preparation evidence. PREPARE has already made stale body genesis
lose, so cancellation cannot race a later child installation. The parent BEGIN
edge consumes this receipt before it enters retiring.

Once body genesis exists, no edge can release directly from
`RESERVED_FOR_GENERATION_GENESIS_FENCED`. Before the ADR-001 partial-parent CAS,
`FENCE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_FOR_PARTIAL_BODY_RETIREMENT` consumes
the exact `LogicalSessionGenerationPartialRetirementPreparationReceipt`, verifies
the current parent is `GENERATION_PARTIAL_RETIREMENT_PREPARED` and binds its
receipt-free complete partial-retirement fact, then compare-and-swaps the
jurisdiction registry from `RESERVED_FOR_GENERATION_GENESIS_FENCED` to
`RESERVED_PARTIAL_RETIREMENT_FENCED`. It emits
`ActuationAuthorityDomainReservedPartialRetirementFenceReceipt`, which the
parent partial-retirement CAS must consume. Domain confirmation and this fence
therefore contend on the same exact registry head: confirmation first selects
owned reconciliation and normal retirement; the partial fence first makes every
historical confirmation lose. A body drain or parent partial transition without
the applicable winning branch receipt rejects.

During that fenced partial-parent retirement, the readable-arbiter branch of
`RETIRE_BODY_ACTUATION_BOUNDARY_AFTER_PHYSICAL_QUIESCENCE` requires the original
genesis FENCED head, a complete zero-history proof for OPEN gates, operations,
outputs, watchdogs, invocations and acceptances, and qualified physical-
quiescence evidence. Its jurisdiction-registry CAS installs the terminal arbiter
and moves the owner to `RESERVED_PARTIAL_RETIREMENT_RETIRED`. The disjoint
`ISOLATE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_STATE_LOSS`
branch requires the exact lost-genesis-arbiter fact, the same complete zero-
history proof and qualified external isolation of every footprint path. It moves
the owner to the same state without inventing an arbiter successor. Both compare
the exact `RESERVED_PARTIAL_RETIREMENT_FENCED` registry head and fence receipt,
and both emit one post-CAS
`ActuationAuthorityDomainReservedPartialRetirementReceipt` with their exact
closure branch. The new owner state is terminal and non-authorizing but remains
reserved until the body selector consumes the closure and reaches TERMINAL.

If body genesis installed while the domain remained reserved and parent
confirmation never committed,
`RELEASE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_RETIREMENT`
consumes the exact terminal partial-body receipt and an
`ActuationAuthorityDomainReservedPartialRetirementReceipt`. It requires the
current owner state `RESERVED_PARTIAL_RETIREMENT_RETIRED`, whose closed closure
branch is `EXACT_GENESIS_ARBITER_RETIRED |
LOST_GENESIS_ARBITER_PHYSICALLY_ISOLATED`. The exact branch binds the terminal
arbiter retirement receipt and proves its complete ancestry never left genesis
FENCED and created no operation, output, watchdog, invocation or acceptance. The
lost branch binds the last authenticated genesis mirror, complete no-operation
history and qualified physical isolation of every footprint path; it invents no
arbiter successor. The release returns the entry to
`UNOWNED_PHYSICALLY_ISOLATED` with all generation, marker, incarnation, epoch and
lost-state tombstones. If registry confirmation already installed owned state, this edge
rejects and the normal owner-handover path applies. Neither branch infers
nonmembership from an unavailable selector.

After body retirement closure,
`BEGIN_ACTUATION_AUTHORITY_DOMAIN_OWNER_HANDOVER` consumes the exact terminal body
receipt and closure evidence and moves
`OWNED_BY_GENERATION_FENCED -> OWNER_HANDOVER_FENCED`; the retired arbiter and all
no-reuse evidence remain bound. After ADR-001 finalization, exactly one of three
edges can consume that handover state:
`RELEASE_ACTUATION_AUTHORITY_DOMAIN_AFTER_GENERATION_FINALIZATION` installs
`UNOWNED_PHYSICALLY_ISOLATED` with current qualified isolation evidence;
`HANDOVER_ACTUATION_AUTHORITY_DOMAIN_TO_SUCCESSOR_GENERATION` consumes the one
parent-authorized successor creation receipt and verifies that it binds the same
`PhysicalActuationJurisdictionKey`, current registry incarnation, exact domain key
and controlling body enrollment. It installs
`RESERVED_FOR_GENERATION_GENESIS_FENCED` and a fresh subordinate arbiter genesis;
or `RETIRE_ACTUATION_AUTHORITY_DOMAIN_AFTER_HARDWARE_WITHDRAWAL` installs terminal
`DOMAIN_RETIRED` with qualified decommission evidence. The branches are mutually
exclusive, retain every predecessor tombstone and compare the complete conflict
neighborhood through the jurisdiction-global registry selector. Release does not erase
history; handover cannot reuse an arbiter identity; terminal retirement has no
future reservation edge.

The closed domain-owner event surface is
`ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_FROM_PHYSICAL_JURISDICTION_ENROLLMENT |
CANCEL_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_GENESIS_BEFORE_CREATION |
RETIRE_UNCONFIRMED_ACTUATION_AUTHORITY_DOMAIN_REGISTRY |
ACTIVATE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_FACILITY_CONFIRMATION |
RESERVE_ACTUATION_AUTHORITY_DOMAIN_FOR_GENERATION |
BODY_ACTUATION_ARBITER_STATE_GENESIS_FROM_DOMAIN_RESERVATION |
CANCEL_ACTUATION_AUTHORITY_DOMAIN_RESERVATION_BEFORE_BODY_GENESIS |
CANCEL_ACTUATION_AUTHORITY_DOMAIN_RESERVATION_DURING_PARTIAL_PARENT_RETIREMENT |
FENCE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_FOR_PARTIAL_BODY_RETIREMENT |
RETIRE_BODY_ACTUATION_BOUNDARY_AFTER_PHYSICAL_QUIESCENCE |
ISOLATE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_STATE_LOSS |
RELEASE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_RETIREMENT |
CONFIRM_ACTUATION_AUTHORITY_DOMAIN_GENERATION_GENESIS |
RECONCILE_BODY_ACTUATION_DOMAIN_GENERATION_GENESIS |
BEGIN_ACTUATION_AUTHORITY_DOMAIN_OWNER_HANDOVER |
RELEASE_ACTUATION_AUTHORITY_DOMAIN_AFTER_GENERATION_FINALIZATION |
HANDOVER_ACTUATION_AUTHORITY_DOMAIN_TO_SUCCESSOR_GENERATION |
RETIRE_ACTUATION_AUTHORITY_DOMAIN_AFTER_HARDWARE_WITHDRAWAL |
RETIRE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_FOR_TOPOLOGY_CHANGE |
REENROLL_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_TOPOLOGY_CHANGE`.
Unknown, default or inferred aliases reject. `OWNED_BY_GENERATION_ACTIVE` contains
only OPEN. Reserved genesis and
`RESERVED_PARTIAL_RETIREMENT_FENCED` contain only the first FENCED arbiter; the
latter additionally binds the parent partial-retirement fact and preexisting
preparation receipt. It structurally excludes its own post-CAS fence receipt;
that crash-complete sidecar binds the prior and installed registry heads.
`RESERVED_PARTIAL_RETIREMENT_RETIRED` contains either that arbiter's exact
terminal descendant or the qualified lost-state isolation branch, never OPEN.
Owned-FENCED and handover states can retain FENCED or physically retired arbiter
state but never OPEN.

The jurisdiction enrollment must cover every body principal and physical path
that can interact through the footprint graph. No live physical effect path can
belong to two registry jurisdictions or incarnations. A local registry schema or
body-membership change can re-enroll only over the exact already enrolled
facility slot/path/conflict set and within the immutable ADR-001 realm isolation
envelope. It first fences and physically isolates every affected domain, retires
the old local registry incarnation and completes facility handover plus a fresh
facility reservation/confirmation for the intended local incarnation. Exact
`RETIRE_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_FOR_TOPOLOGY_CHANGE` requires every
entry to be `UNOWNED_PHYSICALLY_ISOLATED` or `DOMAIN_RETIRED`, no owner,
reservation or handover, and a complete qualified physical-isolation inventory.
It retains the old graph, keys and tombstones in
`RETIRED_FOR_TOPOLOGY_CHANGE`. Exact
`REENROLL_ACTUATION_AUTHORITY_DOMAIN_REGISTRY_AFTER_TOPOLOGY_CHANGE` consumes that
retirement receipt plus the new exact external facility reservation/enrollment
receipts and installs a fresh never-used local registry incarnation over that
same immutable external inventory while preserving all prior no-reuse
tombstones. Adding a bus, actuator, watchdog, interlock, reset/effect path or
conflict edge outside the old facility inventory—or any identity/path outside
the realm envelope—cannot take this event. It requires permanent retirement of
the old facility inventory/hardware identity and a fresh facility key; envelope
widening also requires a fresh `AuthorityRealmKey`. There is no state with two
live incarnations. A second registry, copied receipt or profile assertion cannot
authorize overlapping hardware. If unique complete jurisdiction cannot be
established, plant activation remains disabled.

The owned head binds one authoritative
`BodyActuationGateState`, a never-reused arbiter incarnation and shared monotonic
gate-epoch allocator/high-water, a bounded
`BodyActuationBoundaryOperationRegistry`, exact application-attempt and
restrictive-token consumption indexes, a bounded retained terminal-watchdog
ledger, a pre-reserved emergency/recovery capacity root and one closed current-
output branch:
`NO_ACTIVE_OUTPUT | ARMED_ACTIVE_OUTPUT | RESTRICTIVE_ACTION_CHAIN`. An armed
branch contains exactly one output/value reference, application attempt,
watchdog commitment, clock incarnation, deadline and watchdog epoch. The
restrictive branch binds a bounded canonical
`BodyActuationRestrictiveActionChain` whose entries reference exact restrictive
operation-registry keys, action identities/profile order, predecessor links and
individual pending/accepted/no-effect/unknown results. It retains every
initiating fence/watchdog cause and one complete
`BodyActuationPossibleOutputSet`; it never asserts plant safety. That bounded
set can contain exact prior armed value/ref, ambiguous Active candidate
value/ref, restrictive-action accepted-at-boundary references, restrictive-
action outcome-unknown references and explicit no-prior-output evidence. An
Active qualification-failure member also binds its exact
`POSSIBLY_ARMED_WATCHDOG_QUALIFICATION_FAILURE` token/capacity branch. The
action chain records the corresponding no-effect exclusions. The set and chain
together are the complete possibility product. No transition can collapse an
unresolved Active or restrictive candidate into the displaced prior value,
discard an accepted-at-boundary possibility, or infer physical effect from
boundary acceptance.
Exact `BodyActuationArbiterIncarnationCoordinate` is
`(ActuationAuthorityDomainKey, SessionRef, never_reused_arbiter_incarnation)`.
It keys the gate, emergency/recovery reserve, restrictive-cause overflow reserve
and overflow seal. Fresh arbiter genesis creates
gate `ABSENT -> FENCED`, emergency reserve `ABSENT -> INSTALLED`, overflow
reserve `ABSENT -> QUALIFIED` and typed seal absence. Handover preserves every
old RETIRED entry and creates a new coordinate; none has a RETIRED-to-live edge.
The conflict graph is instead registry-incarnation-persistent, and the identity
no-reuse accumulator is domain/registry-incarnation-persistent. Handover
preserves both INSTALLED. Topology retirement alone changes the graph
`INSTALLED -> RETIRED`; hardware withdrawal or topology retirement changes the
applicable accumulator `INSTALLED -> RETIRED` with its complete retained digest.
Neither has a terminal-to-installed edge.
The gate allocator uses one never-reused arbiter incarnation and one checked
monotonic JSON-safe sequence shared by OPEN, FENCED and RETIRED edges. A later
state consumes exactly the next value; separate open/fence counters, wrap,
rollback or reuse reject. Restart and retirement preserve the allocator and
high-water. Every retention checkpoint preserves no-reuse membership for gate
epochs, operation IDs, application-attempt consumption keys, restrictive tokens,
watchdog/acceptance epochs and idempotency keys.

The operation registry is keyed by one closed
`BodyActuationBoundaryConsumptionKey`: the exact installed body application-
attempt ID for Active work, or the exact one-use restrictive token/watchdog epoch
for restrictive work. The arbiter-allocated boundary operation ID and
idempotency key are immutable fields inside that entry, not caller-selectable map
dimensions. The consumption indexes map each application attempt and restrictive
token bijectively to that one registry key for the no-reuse horizon.
The application-attempt index is
`ABSENT -> RESERVED -> CONSUMED | RETIRED_TOMBSTONE`.
START installs RESERVED. Accepted or definitively rejected boundary consumption
installs CONSUMED with its exact boundary evidence. A
`BodyActuationBoundaryNoEffectFact` may instead install RETIRED_TOMBSTONE only
under its closed `ABANDONED_WITHOUT_BOUNDARY_CONSUMPTION` branch, when
`REJECT_BODY_COMMAND_AT_ACTUATION_BOUNDARY_WITHOUT_EFFECT` or exact cut closure
proves no acceptance, invocation, query or resumption right remains. Generic
fence or ambiguity preserves RESERVED. The tombstone binds attempt/preimage and
no-consumption proof; it is not consumption evidence. Each edge shares the
arbiter CAS/receipt set with its result.
The entry binds the complete immutable operation preimage.
Its closed kind is
`ACTIVE_VALUE_APPLICATION | PROFILE_RESTRICTIVE_ACTION`. The restrictive branch
requires one closed `BodyActuationRestrictiveActionOrigin`:
`WATCHDOG_EXPIRY | AUTHORITY_CUT | FAIL_SAFE_COMMAND | SECURITY_CUT |
CLOCK_RESTART | RETIREMENT_OR_DOMAIN_HANDOVER |
REMOTE_CAPACITY_EXHAUSTION | ACTIVE_QUALIFICATION_FAILURE |
CUT_CAUSE_LEDGER_OVERFLOW | EXPLICIT_RECOVERY`. Origin-specific required and
forbidden fields bind the exact authorization/cause; one origin cannot borrow
another's token, deadline, receipt consumer or retention rule. Its closed
state is
`PENDING_BOUNDARY_INVOCATION | ACTIVE_VALUE_ACCEPTED |
RESTRICTIVE_ACTION_ACCEPTED | DEFINITIVE_NO_EFFECT |
OUTCOME_PENDING_QUERY_OR_RESOLUTION_FENCED | OUTCOME_UNKNOWN_FENCED`. Exact retry or query returns that installed entry and
receipt. The same attempt/token with a different operation ID, idempotency key or
preimage conflicts and cannot allocate a second entry. An accepted
operation remains authoritative after its output is replaced; replay cannot
reinstall the old value. An outcome-unknown operation remains fenced and cannot
be reinvoked under another identity. Missing registry state never means no
effect.

`START_BODY_ACTUATION_BOUNDARY_OPERATION` is the only semantic absent-to-pending
registry edge. It can be the primary edge for an Active call or a subordinate
edge inside the same arbiter compare-and-swap as watchdog expiry, fencing or
unknown-outcome recovery; it is never a separately durable second transaction.
The compare-and-swap validates the exact installed body application/fence
input, current gate, immutable preimage, reserved capacity, consumption-index
nonmembership and key nonmembership before it exports a one-use boundary
invocation token. For Active work, that input is the installed body application
attempt and its receipt. For watchdog expiry, it is the current armed watchdog,
its bound expiry token and complete at-or-after evaluation. For Active
qualification-failure retirement, it is the exact failed bundle/query proof and
pre-reserved recovery token. For an authority, fail-safe, security or retirement cut, it is
the receipt-free `BodyActuationFenceIntent` defined below. No branch can
substitute a post-CAS arbiter receipt as its own input. An Active start also
preallocates distinct never-
used restrictive tokens and capacity for its possible unknown-outcome recovery
and, if accepted, watchdog-expiry path. The two reservations have disjoint
lifecycles. Rejection tombstones both tokens and releases both matching capacity
units. Acceptance tombstones the unused recovery token and binds the expiry token
and its capacity to the armed watchdog. A qualification-failure retirement
consumes the recovery token for the profile interlock/restrictive path but retains
the candidate expiry token, capacity and a
`POSSIBLY_ARMED_WATCHDOG_QUALIFICATION_FAILURE` tombstone through physical-
quiescence retirement; it never assumes that token was unused.
A newer accepted value or a non-expiry fence tombstones that old expiry token and
releases its unit; exact watchdog expiry alone consumes it. Every edge retains a
permanent identity tombstone, so a stale timer or retry cannot recover released
capacity or invoke a token. For Active application,
`ACCEPT_BODY_COMMAND_AT_ACTUATION_BOUNDARY` is the only accepted-
value edge from that exact pending entry. Its one arbiter compare-and-swap checks
the open gate epoch and acceptance-time deadline set, changes the operation to
`ACTIVE_VALUE_ACCEPTED`, installs the new value and watchdog, and partitions the
exact prior current-output branch. From `ARMED_ACTIVE_OUTPUT`, it atomically
moves the prior pair to retained `REPLACED_BY_NEWER_ACCEPTANCE` state,
tombstones the prior expiry token, releases only its capacity unit and
invalidates the old timer before the new pair is current. From
`NO_ACTIVE_OUTPUT`, it proves exact inapplicability. A restrictive or ambiguous
prior output branch forbids Active acceptance.
The physical value, installed arbiter successor and durable watchdog arm are one
qualified fault-domain operation. If the value can become effective before the
selector/watchdog bundle is durable, Active application is disabled.

`REJECT_BODY_COMMAND_AT_ACTUATION_BOUNDARY_WITHOUT_EFFECT` installs
`DEFINITIVE_NO_EFFECT` from the same pending operation and changes no output.
An ambiguous caller response does not install an ambiguous authoritative state.
Exact same-key query reads the already installed accepted/no-effect entry, or
leaves the invocation pending while its bounded resumption right remains. A
`FAIL_BODY_ACTUATION_ACTIVE_QUALIFICATION_AND_RETIRE` transition is legal only
from the exact readable installed pending head when those rights end without a
definitive result or evidence shows that value effect could escape the required
value/successor/watchdog atomicity. It installs `OUTCOME_UNKNOWN_FENCED`,
consumes the distinct pre-reserved recovery token to create a restrictive/
interlock operation, installs a never-reused fence epoch, seals Active for the
generation and requires irreversible body retirement drain. The possible-output
set retains exact prior armed/no-output evidence, the ambiguous candidate
value/ref and its possibly armed expiry token/capacity through physical
quiescence. No same-generation query can refine that terminal unknown or support
`applied`. The Active entry cannot masquerade as the restrictive entry or supply
its token. The post-CAS result receipts bind the operation, exact prior/installed
arbiter heads, selector version, gate, complete prior-output/watchdog partition
and qualification failure. A caller timeout alone cannot select this branch.
Retained-registry exhaustion cannot drop a predecessor. New Active START rejects
unless all recovery capacity is already reserved; an OPEN gate invariant
requires its separate emergency restrictive reserve.

Lost or corrupt arbiter head/selector state cannot take that transition because
it cannot prove ancestry, no-reuse or the next epoch. Instead
`ISOLATE_BODY_AFTER_ACTUATION_ARBITER_STATE_LOSS` consumes a receipt-free
`BodyActuationArbiterStateLossIsolationFact` through one body-selector edge.
The fact binds the last authenticated arbiter mirror, exact loss diagnosis,
separately authorized hardware-interlock/isolation evidence when available and
the complete unknown operation/output/watchdog/token inventory. It installs no
arbiter successor, epoch, result or physical-effect claim. The body mirror enters
`ARBITER_STATE_LOST_ISOLATION_REQUIRED`, all NCP actuation/authority stays closed,
and successor-generation creation remains forbidden until qualified physical
isolation and retirement evidence closes every possible old-boundary effect. A
missing interlock proof remains explicit unknown; a new empty arbiter is never
reconstructed from state loss.

From a predecessor outside the ESTOP-restrictive class, that event can own the
transition to retirement drain with cause
`ACTUATION_ARBITER_STATE_LOSS_ISOLATION`. The ESTOP-restrictive class includes
`ESTOP_LATCHED`, `ESTOP_OUTCOME_UNKNOWN`, and any reserved, invoked, ambiguous or
otherwise possibly effective ESTOP operation even while the lifecycle label is
still HOLD and the ESTOP floor is `NONE`. State loss maps that last case to
`ESTOP_OUTCOME_UNKNOWN` because it is a possibility claim, not a latch-success
claim. For every member of this class, the event must preserve parent
`INSTALLED_CHAIN`, the resulting exact ESTOP state, accepted-transfer fence,
HOLD-cycle ancestry and all state-loss possibilities. It cannot enter drain directly.
`OPERATOR_RESET_AND_RETIRE_GENERATION` or
`INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE`, respectively, later consumes both
its ordinary local reset/inspection evidence and the state-loss/isolation fact.
No capacity, restart, rebind, continuity-failure or generic retirement event can
bypass either specialized ESTOP edge.

Before an authority, fail-safe, security or retirement cut reaches the arbiter,
the authenticated body-control authority constructs one receipt-free
`BodyActuationFenceIntent`. It binds a stable idempotency key, the exact expected
body head and selector version, exact current arbiter head/gate epoch, current
session/generation/security/plant-profile context, typed cut cause and
authorization, candidate profile action and current reserve-root digest. It does
not name a restrictive token or capacity unit. The arbiter derives one from its
current reserve only when the closed action selection requires a new invocation;
a caller cannot mint or choose it. The intent excludes every
candidate/installed successor, selector commit and arbiter/body receipt. Exact
retry returns the installed selection and, when applicable, operation bound to
the consumed token; changed preimage or token reuse conflicts. This is an
authenticated command to become more
restrictive, not proof that the expected body head remains current or that the
physical action succeeded.

`FENCE_BODY_ACTUATION_BOUNDARY_AND_SELECT_RESTRICTIVE_ACTION` handles that intent
or an exact internally generated recovery cut. It always atomically installs a
never-reused `FENCED` gate epoch, invalidates any current Active watchdog,
partitions the exact prior output, records the cut cause and installs one closed
action selection, and moves the same exact domain owner to or preserves
`OWNED_BY_GENERATION_FENCED`. It cannot change the domain owner. Only either
START selection also consumes a fresh reserve and
installs one pending restrictive-action operation/token before boundary
invocation. JOIN references its existing operation; equal/lower and incomparable
branches create no operation or invocation token. `EXPIRE_BODY_ACTUATION_WATCHDOG` is
the specialized deadline-driven form. It is legal only from the exact current
`ARMED_ACTIVE_OUTPUT`, with an at-or-after evaluation of its unchanged deadline.
It moves that pair to retained `EXPIRED_TO_RESTRICTIVE_ACTION`, installs the
fence and pending restrictive operation in one arbiter compare-and-swap, and
cannot wait for a journal worker. Every other fence cause, including clock
discontinuity, first retains `FENCED_TO_RESTRICTIVE_ACTION`; only the exact later
definitive clock-restart resolution can retire it. A timer for a retained,
replaced, sibling or old-epoch pair has no invocation right.

Repeated cuts use one closed `BodyActuationRestrictiveActionSelection` derived
from the content-addressed plant profile:
`JOIN_IDENTICAL_ACTION | START_PROFILE_DOMINATING_ACTION |
START_QUALIFIED_ESTOP_SEVERITY_OVERRIDE |
RECORD_EQUAL_OR_LOWER_CUT_WITHOUT_INVOCATION |
FENCE_INCOMPARABLE_ACTION_FOR_OPERATOR_RESOLUTION`. The profile supplies a
finite canonical action-identity set and a strict dominance relation that is
validated as irreflexive, asymmetric, transitive and acyclic. It also supplies a
finite maximum chain/escalation length. An invalid relation or bound disables
gate activation. NCP does not assume one universal zero-safe action or total
severity order.

Selection compares the candidate with the complete canonical maximal unresolved
frontier, not one arbitrary chain member. The selector has a proved total,
exclusive partition for every bounded candidate/frontier product. Identical
action identity selects `JOIN_IDENTICAL_ACTION`. With no identity match, a
candidate that strictly dominates every frontier member selects
`START_PROFILE_DOMINATING_ACTION` with
`DOMINATES_COMPLETE_FRONTIER` evidence. An empty frontier can select that same
branch only with disjoint `EMPTY_FRONTIER_PROFILE_AUTHORIZED` evidence. These
two values plus `QUALIFIED_ESTOP_SEVERITY_OVERRIDE` form the closed
`BodyActuationRestrictiveActionStartEvidence` union; vacuous dominance is invalid.
A distinct exact ESTOP candidate on a nonempty frontier that does not dominate
the complete frontier can instead select
`START_QUALIFIED_ESTOP_SEVERITY_OVERRIDE` only with
`QUALIFIED_ESTOP_SEVERITY_OVERRIDE` start evidence and an exact
`BodyFailSafeSeverityOverrideProof`. That proof binds the current profile,
domain, ESTOP action identity, complete frontier and a qualified independently
assertable latch boundary. For every frontier member it proves either
`HOLD_CLEAR_SUPERSEDED_OR_SERIALIZED` or
`PRIOR_RESTRICTIVE_ACTION_PRESERVED_WITH_INDEPENDENT_ESTOP_ASSERTION`; no member
can be omitted. It also proves that one qualified pre-invocation fault domain can
install `ESTOP_PENDING`, invalidate every older HOLD token, reserve a distinct
ESTOP token and retain every prior action/result obligation before any latch
invocation. It does not claim profile dominance, latch success or physical
certification. A candidate that is strictly dominated and comparable
with every frontier member selects
`RECORD_EQUAL_OR_LOWER_CUT_WITHOUT_INVOCATION`. Every other product, including
partial dominance or one incomparable member, selects
`FENCE_INCOMPARABLE_ACTION_FOR_OPERATOR_RESOLUTION`. Exactly one branch is legal.

Those predicates are evaluated in the stated order and are structurally
disjoint. JOIN requires identity equality. Both START branches require identity
inequality. The profile-dominance branch excludes override evidence; the override
branch requires the exact ESTOP proof. The equal/lower and incomparable branches
both require `NOT_QUALIFIED_ESTOP_SEVERITY_OVERRIDE`. Thus a dominated or
incomparable ESTOP with valid override cannot also select a no-invocation branch,
and an ESTOP whose action identity equals a reachable HOLD identity makes remote
HOLD/ESTOP qualification fail.

An identical pending or terminal action joins its exact token/query result. A
profile-dominating distinct action or qualified ESTOP severity override consumes
a different pre-reserved token, creates a separate pending operation through the
subordinate START edge, and appends it to the chain without dropping its
predecessor. An equal/lower cut
records the new cause but cannot invoke again. An incomparable action keeps every
prior possibility and obligation, stays fenced, and requires the profile's
operator/inspection resolution. Unknown never becomes no-effect through a later
cut. Only `START_PROFILE_DOMINATING_ACTION`, including its explicit authorized
empty-frontier evidence, and `START_QUALIFIED_ESTOP_SEVERITY_OVERRIDE` derive and
consume a fresh reserve token/capacity unit. JOIN references the existing
operation token. Equal/lower and incomparable branches structurally forbid a
candidate token and leave the reserve unchanged.
Each stable fence-intent key has one retained selection tombstone, so retry cannot
reselect after the frontier changes or consume a later token.

Action-chain length and initiating-cut cardinality are separate bounds. One
bounded `BodyActuationRestrictiveCutCauseLedger` retains each accepted stable cut
key, authenticated cause/preimage digest, selected branch and linked gate epoch;
exact replay does not grow it and conflicting key reuse rejects. The manifest
sets independent maximum count/bytes for this ledger and reserves capacity for
that maximum plus one exact overflow-seal record. Gate activation also binds one
`BodyActuationRestrictiveCauseOverflowReserve`: dedicated profile-action token/
capacity or a qualified independently assertable hardware-interlock capability,
with all evidence/capacity needed at cap-plus-one. This is a policy/reserve
commitment, not a future result selection. An interlock already asserted in a
state incompatible with Active output forbids OPEN.
At cap-plus-one, the exact
`SEAL_BODY_ACTUATION_RESTRICTIVE_CAUSE_OVERFLOW` arbiter transition records that
cut in the overflow seal, consumes a fresh shared gate epoch, remains FENCED and
installs the contemporaneous closed
`BodyActuationRestrictiveCauseOverflowSelection`:
`START_PROFILE_OVERFLOW_RESTRICTIVE_ACTION |
ASSERT_OR_PROVE_QUALIFIED_HARDWARE_INTERLOCK`. It atomically either consumes the
dedicated overflow token to append one pending profile action to the normal
chain with kind `PROFILE_RESTRICTIVE_ACTION` and origin
`CUT_CAUSE_LEDGER_OVERFLOW`, or asserts the reserved interlock and binds its
evidence (or proves a
concurrently asserted instance ordered before the seal). It then closes
automatic selection for the generation and requires body retirement drain. The
pending branch uses the normal one-invocation/ambiguity/result DAG; the interlock
branch is boundary evidence, not a safety or certification claim. If neither
branch was prequalified, the gate could not have opened. No later cut can reopen,
invoke or append in that sealed generation. Thus no accepted cause is dropped,
an Active output is never merely abandoned in storage, and cause floods cannot
consume ordinary escalation tokens.

Each FENCED-to-FENCED cut consumes a fresh gate epoch from the same shared
allocator and preserves the complete action chain, operation registry,
possible-output set and prior fence ancestry. At gate activation, the arbiter
reserves the manifest-bounded bytes, capacity units and never-used tokens for
the validated maximum number of profile-authorized automatic restrictive
escalations reachable during that OPEN epoch, the independent bounded cause
ledger and its overflow seal.
Each accepted watchdog additionally binds its own preallocated expiry token and
capacity. Therefore deadline expiry and required fencing never depend on a new
general-purpose allocation. If the finite profile/reserve cannot be proved, the
gate cannot open for Active work. Corrupt or missing reserve state forces the
hardware interlock/retirement path and permits no claimed restrictive result.

If a profile enables remote HOLD and ESTOP, gate activation and every matching
freshness-grant installation also bind one complete
`BodyFailSafeEscalationQualificationRoot`. It enumerates every bounded reachable
maximal frontier from `HOLD_PENDING | HOLD_EFFECTIVE | HOLD_OUTCOME_UNKNOWN` and
every other profile-authorized restrictive action during the grant/gate horizon.
For each nonempty frontier, the distinct ESTOP action must either dominate the
complete frontier or have a valid `BodyFailSafeSeverityOverrideProof` for every
member. The empty-frontier case requires explicit profile authorization. The
root also proves ESTOP and every reachable HOLD identity differ and that capacity
and a distinct token are reserved for each maximum escalation trace. Missing,
unknown, default, stale-profile, partial-frontier or no-token evidence disables
both remote HOLD and remote ESTOP; it cannot leave HOLD enabled with an
unexecutable escalation promise. A profile can still use a separately qualified
local interlock, but NCP then grants no remote fail-safe mode. Runtime selector
totality remains fail-closed for unqualified inputs and does not turn an
incomparable action into an invocation.

`RESOLVE_BODY_ACTUATION_RESTRICTIVE_ACTION` consumes only that exact operation
token. From pending, it installs the corresponding operation entry as
`RESTRICTIVE_ACTION_ACCEPTED`, `DEFINITIVE_NO_EFFECT`, or
`OUTCOME_PENDING_QUERY_OR_RESOLUTION_FENCED`, updates the exact action-chain member, and
emits the matching `BodyActuationRestrictiveActionResultReceipt`. The ambiguity
branch is nonterminal and binds its bounded same-key query/resumption contract.
`RESOLVE_BODY_ACTUATION_RESTRICTIVE_AMBIGUITY` can later move that same
restrictive operation to its definitive accepted or no-effect state only from
new exact device evidence for the original invocation. It cannot invoke again or
change identity. Active caller ambiguity is not eligible: it queries the
indivisible installed bundle, and qualification failure takes the sealed
retirement path above.
`CLOSE_BODY_ACTUATION_RESTRICTIVE_AMBIGUITY_UNKNOWN` alone moves a restrictive
operation to
`OUTCOME_UNKNOWN_FENCED`, and only after exact evidence that every
query/resumption right ended. The complete chain and possible-output set remain
retained on every branch.
All branches remain fenced. Acceptance proves only that the
named local boundary accepted the profile action; no-effect and unknown cannot
claim quiescence or safety. Pending ambiguity retains only its bounded same-key
query/resumption right; terminal unknown forbids further query/invocation and
retains its no-reuse tombstone. Expiry/fence and newer acceptance have one
arbiter order. If acceptance
wins first, the fence partitions that new pair. If the fence wins first, later
Active acceptance rejects until an explicit qualified gate activation with a
fresh epoch.

Each fence, watchdog-expiry and restrictive-resolution transition emits a crash-
complete arbiter receipt over the exact operation, prior/installed arbiter
heads, selector version, gate edge, output/watchdog partition and result. The
post-CAS receipts for one event form one canonical
`BodyActuationArbiterTransitionReceiptSetRoot`. Its closed event-specific
cardinality includes the generic arbiter commit and every required specialized
fence, START, deadline, watchdog, severity, result, activation, retirement or
compaction sidecar, and forbids every inapplicable sidecar. The body-selector
transition consumes that complete set root once and installs its mirror and
pending/terminal command partitions. Its post-CAS
`BodyActuationArbiterMirrorCommitReceipt` binds the arbiter transition, exact prior/
installed body heads and complete receipt-set root; it is not another
physical gate-fence receipt. A missing, extra, duplicate or substituted sidecar
rejects the whole body transition. In
particular, `RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT`, remote-capacity exhaustion and
authority/security cuts consume the pre-existing arbiter receipt-set root and
verify its required `BodyActuationGateFenceReceipt`; they can emit only their
body-owned mirror or reconciliation receipts. No candidate body successor binds its own future
sidecar as fence evidence. If the expected body compare-and-swap
loses, the arbiter stays fenced;
`REBASE_BODY_ACTUATION_GATE_FENCE_AFTER_LOSING_CAS` binds the exact already
installed arbiter head/receipt-set root over the new body head. It cannot rerun or relabel
the restrictive action. Until reconciliation, grant issuance, application,
reconnect, transfer completion and gate activation remain closed.

`BodySessionControlStateHead` contains one `BodyActuationArbiterMirror` over the
exact domain key, owner/head and selector version, arbiter-head digest, gate
state/epoch, operation-registry, action-chain, possible-output, watchdog and
retention roots, latest consumed arbiter receipt-set root, and a bounded pending
semantic-obligation map. Every installed arbiter transition receipt set appears
exactly once in this mirror's body-head ancestry. The closed receipt-to-body
consumer table is:

| Installed arbiter transition | Sole body consumer |
|---|---|
| `BODY_ACTUATION_ARBITER_STATE_GENESIS_FROM_DOMAIN_RESERVATION` | `BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION`, through the exact domain-reservation receipt |
| Active operation START | `RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION` with `START_MIRROR` |
| Active accepted or no-effect result | `RESOLVE_BODY_COMMAND_APPLICATION_ATTEMPT`, or `CLOSE_FENCED_COMMAND_AFTER_AUTHORITY_CUT` when the cut already won |
| Active qualification-failure terminal/fence | `RETIRE_BODY_SESSION_GENERATION` with the exact qualification-failure retirement fact; later application closure consumes only the installed drain obligation |
| authority, fail-safe, security, restart, retirement or capacity fence/START | the exact cause-owning body event; a lost parent CAS uses `REBASE_BODY_ACTUATION_GATE_FENCE_AFTER_LOSING_CAS` |
| watchdog-expiry fence/START | `RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION` with `WATCHDOG_EXPIRY_MIRROR` |
| restrictive-cause overflow seal/fence/optional START | `RETIRE_BODY_SESSION_GENERATION` with cause `ACTUATION_RESTRICTIVE_CAUSE_LEDGER_OVERFLOW`; a lost parent CAS uses the exact rebase path |
| fail-safe restrictive result/refinement/terminal unknown | `COMPLETE_RESERVED_FAIL_SAFE_COMMAND` or `MARK_BODY_FAIL_SAFE_EFFECT_OUTCOME_PENDING` |
| every other restrictive result/refinement/terminal unknown | `RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION` with `RESTRICTIVE_RESULT_MIRROR` |
| activation | exactly one of `COMMIT_PLANT_AUTHORITY_ACQUISITION`, `INSTALL_SUCCESSOR_AUTHORITY_GRANT`, or `COMPLETE_RECONNECT_WITH_EXACT_CONTINUITY` |
| physical-quiescence retirement | `INSTALL_BODY_RETIREMENT_BOUNDARY_CLOSURE_EVIDENCE` with `EXACT_ARBITER_RETIREMENT` |
| qualified retention compaction | `RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION` with `RETENTION_CHECKPOINT_MIRROR` |

The generic reconciliation event can only copy the exact installed arbiter roots
and create or close the typed pending semantic obligation. It cannot create an
authority, disposition, side-effect result, quiescence claim or physical receipt.
A cause-owning event that consumes the arbiter receipt directly does not also use
generic reconciliation. If its first CAS loses, generic reconciliation can retain
the exact receipt as pending; the retried semantic event then consumes that
installed obligation, not the arbiter receipt a second time. A stale/inapplicable
arbiter call creates no transition receipt and permits a read-only result only
when the body mirror already names that exact arbiter head. Missing, duplicate,
wrong-owner or out-of-order receipt consumption keeps the mirror mismatched and
all authority widening closed.

`ACTIVATE_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH` requires the exact
body recovery/transfer/reconnect authorization, completed prior restrictive
obligations, a complete closure partition for every member of the possible-
output/action-chain product, exact `OWNED_BY_GENERATION_FENCED` ownership for
that body generation and a qualified boundary activation receipt. The domain
CAS moves the owner to `OWNED_BY_GENERATION_ACTIVE` and installs `OPEN` with a
never-used epoch and `NO_ACTIVE_OUTPUT`; it cannot open from unknown/no-effect
state without the separately required inspection/reset/quiescence evidence.
Active qualification-failure unknown and
`ARBITER_STATE_LOST_ISOLATION_REQUIRED` have no same-generation activation edge
under any inspection or reset. They require retirement/finalization and, after
proved physical isolation, a separately parent-authorized fresh arbiter
incarnation in a successor generation.
Every timer
callback compares its watchdog epoch and commitment to the then-current arbiter
head before invocation. Restart restores the exact head/selector or remains
fenced and uses the clock-restart restrictive operation. Eligible terminal
operation/watchdog records can compact only through
`COMPACT_BODY_ACTUATION_BOUNDARY_RETENTION` and a signed monotonic checkpoint
after journal, query and recovery obligations are final. The checkpoint preserves
the shared gate-epoch allocator/high-water, every operation ID, attempt-
consumption key, restrictive token, idempotency key, watchdog/acceptance epoch,
reservation tombstone and the complete action-chain/possible-output closure.
Compaction never changes current output, reuses any identity, restores a released
capacity unit to a stale token, drops a possible effect, or turns unknown into no
effect. If neither retention nor qualified compaction fits, the arbiter rejects
new Active work and remains fenced.

Receipt-free `BodyActuationBoundaryRetentionCheckpointFact` carries complete
disjoint compaction partitions. A selection entry changes
`INSTALLED -> RETIRED_TOMBSTONE` only after no live operation, query, recovery or
receipt needs its full bytes; its signed tombstone retains the fence-intent key,
selected branch/digest and no-reuse membership. A cut-cause entry changes
`RECORDED -> RETIRED_TOMBSTONE` under the same condition while retaining its
stable key, cause/preimage, branch and gate-epoch digest. An
`OVERFLOW_SEALED` sentinel remains intact through arbiter retirement. The sole
arbiter CAS emits `BodyActuationBoundaryRetentionCheckpointReceipt`; exact replay
returns it, and an omitted, extra or live-referenced entry rejects.

The arbiter's `BodyActuationAcceptanceDeadlineEvaluationReceipt` binds the exact
attempt, gate, freshness grant/slot and derivation, lease/absolute-TTL intent set,
complete evaluation set and acceptance instant. START's storage-commit evaluation
is necessary but not sufficient. The
arbiter is the qualified enforcement endpoint for application deadlines and
effect ordering; a later storage timestamp cannot replace or invalidate its
proved pre-deadline acceptance.

Value acceptance and expiry enforcement are one indivisible arbiter operation.
At acceptance, the arbiter atomically installs the value and arms or replaces a
persistent local/hardware `BodyActuationWatchdogCommitment` whose exclusive
deadline is no later than
`min(effective_command_deadline, live_lease_deadline)`. The matching
`BodyActuationWatchdogArmReceipt` binds the attempt, accepted value/ref, gate and
watchdog epochs, body-clock incarnation, exact exclusive deadline and selected
plant-profile expiry action. The watchdog survives a process crash; equality
with its deadline takes the profile's local restrictive action and cannot wait
for a journal worker. An exact replay, query, retry, recovery or receipt return
reuses the installed commitment and can never refresh or extend it. Only a
separately admitted newer value can atomically replace it under that newer
command's independently bounded deadline. If output can become effective before
the watchdog is durably armed, or restart cannot prove the watchdog/output pair,
Active application is disabled and recovery remains non-actuating. This rule
does not define a universal zero-safe action or claim physical certification.

`RESOLVE_BODY_COMMAND_APPLICATION_ATTEMPT` consumes that installed attempt. It
does not install an output or arm/replace a watchdog. Definitive acceptance can
create `applied` and `BodyBoundaryApplicationEvidence` only from the exact
already committed arbiter acceptance/watchdog receipts and prior-output
partition. If a later accepted value already replaced that pair, resolution also
binds its authenticated retained-ledger ancestry; replacement does not erase the
earlier acceptance. A definitive no-effect result selects exactly
one closed `BodyActuationArbiterRejectionCause` in this total precedence order:
`GATE_NOT_OPEN`, `AUTHORITY_CUT`, `FRESHNESS_GRANT_RESTRICTIVELY_CUT`,
`LEASE_NOT_CURRENT`, `COMMAND_TTL_ELAPSED`, or
`OTHER_DEFINITIVE_BOUNDARY_REJECTION`. The first four create `superseded`, TTL
creates `expired`, and the final cause creates `failed`. The result binds only
the selected cause and its complete fence, at-or-after, or boundary-rejection
proof; fields for every non-selected cause are structurally absent. Therefore a
single preimage cannot choose two terminal dispositions when several rejection
predicates are true. An
indeterminate call enters `OUTCOME_PENDING_QUERY_OR_RESOLUTION` while the
installed contract has a bounded same-key query or resumption right. That
intermediate bundle emits `BodyCommandApplicationAmbiguityPendingReceipt` and
structurally forbids a terminal disposition. A later resolution bundle binds the
attempt, exact arbiter evidence and acceptance-time evaluation, linked terminal
disposition and terminal attempt receipt. RESOLVE can
commit after lease/TTL expiry or an authority cut; it verifies the earlier
acceptance order and does not require current live authority. Only after no
further invocation, query or retry can occur can unresolved ambiguity become
terminal `unknown_after_boundary`. That terminal never strengthens. Crash before
START invokes nothing; crash after START recovers the same attempt; crash after
possible effect cannot recreate it with another identity.

`CLOSE_COMMAND_NON_SUCCESS` consumes receipt-free
`BodyCommandNonSuccessClosureFact` over one exact ADMITTED tip with typed
nonmembership of an application attempt or pending restrictive association.
Its closed cause precedence is `AUTHORITY_SECURITY_OR_GATE_CUT |
COMMAND_TTL_ELAPSED | OTHER_DEFINITIVE_PRE_BOUNDARY_FAILURE`, mapping only to
`SUPERSEDED | EXPIRED | FAILED`, respectively. TTL uses the original unchanged
absolute deadline and an at-or-after CAS evaluation; a fence or cut can never
select EXPIRED. One body/journal CAS appends the linked terminal record and emits
the generic receipts plus `BodyCommandNonSuccessClosureReceipt`. The admission
reserve covers it. Exact replay returns the receipt; changed cause/content
rejects. The event never invokes the boundary or closes an ambiguous attempt.

Every fail-safe, authority-removal, emergency-rebind or retirement cut competes
with application through the same gate epoch. After the minimum authenticated
context is known, fail-safe handling first obtains a durable
`BodyActuationGateFenceReceipt` from
`FENCE_BODY_ACTUATION_BOUNDARY_AND_SELECT_RESTRICTIVE_ACTION`, then installs the exact
reservation/cut against that fence. The receipt binds the exact prior/installed
arbiter heads, output/watchdog partition, new fence epoch, closed action
selection and one closed `BodyActuationRestrictiveOperationDisposition`:
`STARTED_NEW_OPERATION | JOINED_EXISTING_OPERATION |
NO_OPERATION_FOR_SELECTION`. START binds the fresh operation-registry entry and
consumed restrictive-action token. JOIN binds the exact already installed entry
and token and proves no new consumption. The no-operation branch is legal only
for the equal/lower or incomparable selection and structurally forbids every
operation/token field. Thus a fence receipt never fabricates an operation for a
selection that cannot invoke. It does not claim that any restrictive action
succeeded. An old-epoch attempt cannot be accepted
after the fence. A definitive acceptance that ordered before the fence can be
recorded later as `applied` only with exact arbiter acceptance/fence-order
evidence; the cut did not cause a later actuation. Otherwise the fenced attempt
uses the exact pending/query state until it can close as `expired`, `superseded`,
`failed`, or, after all invocation/query rights end, `unknown_after_boundary`.
A crash after the arbiter fence
but before storage recording leaves the body non-actuating and recovery must
install or reconcile that same fence.

`REOPEN_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH` is a required subordinate mirror
edge, never a standalone body transition. It has three disjoint branches:
`FRESH_ACQUISITION_AND_DECLARATION` from the exact installed `ACQUIRING`
operation and candidate declaration, `SUCCESSOR_TRANSFER_GRANT` from exact
`GRANTING_SUCCESSOR`, and `RECONNECT_CONTINUITY` from the exact fenced reconnect
candidate. A consumed HOLD cycle permits those later authority paths but is not
activation authority.

For each branch, the arbiter first uses
`ACTIVATE_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH` to install an OPEN candidate bound
to the exact pending parent operation, candidate lease/declaration and a fresh
never-used epoch. That candidate cannot accept a boundary operation unless a
body application-attempt receipt already binds the matching installed body
mirror; none can exist before the parent commit. The matching parent event
`COMMIT_PLANT_AUTHORITY_ACQUISITION`, `INSTALL_SUCCESSOR_AUTHORITY_GRANT`, or
`COMPLETE_RECONNECT_WITH_EXACT_CONTINUITY` then consumes that activation receipt
and atomically installs the subordinate reopen mirror,
`ACTIVE`, the exact `LIVE` lease, pending `NONE` and current declaration in the
body selector. No durable body tuple has `HOLD + LIVE + NONE`. The arbiter
activation and body mirror are two ordered selector transitions in the same
qualified authority transaction domain, not one combined state transition. The
separation is deliberate because boundary invocation and recovery can occur
between their commits; it does not permit either transition to pre-read a selector
that commits independently. Every branch is legal only
in parent `INSTALLED_CHAIN`, outside ESTOP, with complete proofs that earlier
fail-safe and fenced command/application/ingress work is terminal. It is
forbidden from drain-only and terminal.

If a fence or activation becomes durable but its expected body CAS loses, the
mismatch itself is restrictive. Recovery rebases that exact fence over the
current state or uses
`FENCE_BODY_ACTUATION_BOUNDARY_AND_SELECT_RESTRICTIVE_ACTION` to advance the
orphan activation to a fresh FENCED epoch. It never abandons, duplicates or
treats that candidate as OPEN. Normal admission/application and authority
widening remain disabled until one current receipted body head and arbiter state
agree. Genesis uses the same qualified mechanism for its first
state but keeps the arbiter and body mirror FENCED while authority is HOLD/absent;
only a qualified acquisition activation can first open them.

The closed application/gate event surface is
`ISSUE_BODY_COMMAND_FRESHNESS_GRANT |
EXPIRE_BODY_COMMAND_FRESHNESS_GRANT |
START_BODY_COMMAND_APPLICATION_ATTEMPT |
BODY_ACTUATION_ARBITER_STATE_GENESIS_FROM_DOMAIN_RESERVATION |
START_BODY_ACTUATION_BOUNDARY_OPERATION |
ACCEPT_BODY_COMMAND_AT_ACTUATION_BOUNDARY |
REJECT_BODY_COMMAND_AT_ACTUATION_BOUNDARY_WITHOUT_EFFECT |
FAIL_BODY_ACTUATION_ACTIVE_QUALIFICATION_AND_RETIRE |
ISOLATE_BODY_AFTER_ACTUATION_ARBITER_STATE_LOSS |
FENCE_BODY_ACTUATION_BOUNDARY_AND_SELECT_RESTRICTIVE_ACTION |
EXPIRE_BODY_ACTUATION_WATCHDOG |
SEAL_BODY_ACTUATION_RESTRICTIVE_CAUSE_OVERFLOW |
RESOLVE_BODY_ACTUATION_RESTRICTIVE_ACTION |
RESOLVE_BODY_ACTUATION_RESTRICTIVE_AMBIGUITY |
CLOSE_BODY_ACTUATION_RESTRICTIVE_AMBIGUITY_UNKNOWN |
RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION |
ACTIVATE_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH |
RETIRE_BODY_ACTUATION_BOUNDARY_AFTER_PHYSICAL_QUIESCENCE |
COMPACT_BODY_ACTUATION_BOUNDARY_RETENTION |
RESOLVE_BODY_COMMAND_APPLICATION_ATTEMPT |
MARK_BODY_COMMAND_APPLICATION_OUTCOME_PENDING |
CLOSE_BODY_COMMAND_APPLICATION_AMBIGUITY |
CLOSE_COMMAND_NON_SUCCESS |
REOPEN_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH |
NORMAL_HOLD_RECOVERY |
REBASE_BODY_ACTUATION_GATE_FENCE_AFTER_LOSING_CAS |
RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT |
UPGRADE_BODY_FAIL_SAFE_TO_ESTOP |
MARK_BODY_FAIL_SAFE_EFFECT_OUTCOME_PENDING |
COMPLETE_RESERVED_FAIL_SAFE_COMMAND |
ADMIT_RESTRICTIVE_COMMAND_AFTER_FAIL_SAFE_EFFECT |
ASSOCIATE_ADMITTED_RESTRICTIVE_COMMAND_WITH_EFFECT |
EXHAUST_BODY_REMOTE_COMMAND_CAPACITY_TO_RETIREMENT_DRAIN |
SEAL_BODY_REMOTE_COMMAND_CAPACITY_UNDER_ESTOP |
ESTOP_ONLY_DRAIN_ADMISSION |
CLOSE_FENCED_COMMAND_BEFORE_APPLICATION_ATTEMPT |
CLOSE_FENCED_COMMAND_AFTER_AUTHORITY_CUT |
CLOSE_FENCED_BODY_OPERATION_AFTER_AUTHORITY_CUT |
INSTALL_BODY_RETIREMENT_BOUNDARY_CLOSURE_EVIDENCE |
COMPACT_BODY_RETIREMENT_RETENTION`. Unknown, inferred and legacy aliases reject.

Remote command freshness uses the body clock only. Before a publisher can send a
remote command, the body installs one receipt-free
`BodyCommandFreshnessGrantCommitment` through the sole body-session-control
selector. The commitment binds a random grant ID, body/plant/profile,
session/generation/security, body clock incarnation, authenticated publisher,
declaration and stream epoch, a bounded non-overlapping command-sequence slot
range, allowed modes, body issue tick, exclusive maximum not-after tick, and TTL/
capacity ceilings. The candidate body head binds the commitment. Post-CAS
`BodyCommandFreshnessGrantInstallationReceipt` binds the commitment, exact prior/
installed body heads, selector version and generic commit. The exported
`BodyCommandFreshnessGrant` binds that commitment and receipt; the successor head
never binds this post-CAS artifact. A grant is freshness evidence only. It grants
no identity, route, manifest permission, command declaration, lease, or actuator
authority. Missing, overlapping, default, stale, wrong-context or uninstalled
grants reject.

Grant issuance is itself a bounded idempotent body operation. An authenticated
request carries a stable request key and requested mode/capacity ceilings, but no
caller-selected grant ID, slot range, body time or deadline. The body allocates a
never-used operation/grant ID and range and records one
`BodyCommandFreshnessGrantOperation` in
`PENDING_INSTALL | TERMINAL_INSTALLED | TERMINAL_REJECTED`. Exact retry or reply
loss queries that request key and returns the same installed grant/receipt or
rejection; it cannot allocate another range or burn capacity again. Conflicting
reuse rejects. Publisher restart imports only an exact exported grant and
installation receipt. Its local allocator can consume only body-granted slots;
uncertain locally used slots remain consumed, and neither sender recovery nor a
new grant operation can reuse a body-tombstoned position.

`ISSUE_BODY_COMMAND_FRESHNESS_GRANT` has two disjoint branches. Normal issuance
requires parent `INSTALLED_CHAIN`, a non-retired body root, current manifest/
security, exact live publisher declaration, checked `issue_tick <
maximum_not_after`, bounded range length, and allocator proof that the range does
not overlap any active or tombstoned grant/stream position. It reserves worst-case
position-index, conflict-tombstone, command-chain and ingress-journal capacity for
every granted slot before the CAS. For each HOLD/ESTOP-capable slot it also
reserves the worst-case fail-safe operation and HOLD-to-ESTOP upgrade capacity;
an Active-only range consumes no fail-safe reservation. The reservation covers
the maximum permitted mode-order trace. An ordinarily admitted HOLD can install
one effect and one monotonic ESTOP upgrade. A first Active candidate and one later
qualified conflicting ESTOP can use only their separately bounded records. No
trace can overrun the journal. The
`ESTOP_ONLY_DRAIN` branch is legal only in HOLD before retirement or atomically
with entry into retirement drain. It targets a separately manifest-enrolled
emergency principal, allows exactly one ESTOP slot, uses the dedicated escalation
capacity, and grants no Active/HOLD or lease right. Each generation starts with a
one-use `drain_emergency_grant_budget`; issuing this grant consumes the budget
permanently even if the grant expires unused. No already-draining state can issue
another grant. Unknown branch, insufficient capacity, inverted window, range
reuse, consumed budget or caller-selected allocator state rejects.

`EXPIRE_BODY_COMMAND_FRESHNESS_GRANT` compare-and-swaps the same selector at or
after the grant deadline or on a restrictive security/declaration/session cut. It
installs an exact grant/range tombstone and cannot free those positions for reuse
inside the generation. Equality selects expiry. Issuance, expiry, clock restart,
security change and retirement therefore have one order; a worker cannot keep a
stale grant alive in a side store.

An early declaration, security, session, authority-transfer or revocation cut
first fences the body actuation gate and then tombstones every affected grant and
mode. A normal cut preserves no old-holder remote ESTOP right. The only exception
is the same CAS that reserves a HOLD effect: it can move explicitly policy-
authorized, unused ESTOP slots into the bounded ESTOP-only escalation snapshot
while tombstoning Active/HOLD use. Transfer or revocation can preserve that right
only for a separately enrolled emergency principal and explicit manifest policy;
holder identity alone never survives. Boundary acceptance before the fence can
resolve later; the old grant cannot be accepted after it.

Prepared authenticated command context resolves one positive stream position to
one exact installed freshness grant and permitted slot. The selected compact
command repeats no grant, lease, or `ttl_ms` field. The grant already carries its
receiver-clock incarnation and exclusive body-clock deadline. A retained
compatibility `CommandFrame.t` value is diagnostic only and is excluded from
authorization and cross-peer time comparison. Receive time cannot start or
refresh the deadline. The same unchanged grant deadline drives
`COMMAND_ADMISSION_TTL_NOT_AFTER`, `COMMAND_APPLICATION_TTL_NOT_AFTER`, and
`FAIL_SAFE_EFFECT_NOT_AFTER`. Those retained `TTL` names do not select a
per-frame lifetime. Equality is expired. The body watchdog uses only the
remaining absolute lifetime. Therefore delayed Active, HOLD, and ESTOP frames
cannot become fresh on arrival.

Every grant slot has one bounded `BodyCommandPositionEntry`, keyed by the exact
grant/slot and authenticated publisher/declaration/stream/session/generation/
security context. After minimum envelope, grant, route, audience and canonical-
content verification, the first candidate stores its protected-content digest,
mode and original ingress/command-chain lineage. Exact candidate replay returns
or joins that installed lineage without a new ingress attempt, chain, position
entry or durable counter. A changed candidate stores at most the first conflicting
digest plus a saturated `POSITION_CONFLICT_SEEN` marker and profile-bounded
counter; later variants cause no durable growth. This position index bounds Active
replay and conflict independently of command ID.

The position index does not itself authorize or suppress an ESTOP fail-safe
effect. Active never creates a `BodyFailSafeEffectSlotKey`. Therefore, an
authenticated fresh ESTOP can install one restrictive effect slot after
different Active content occupies the same position. It can then take its
bounded latch attempt. Its command-stream result is
`CONFLICTING_STREAM_POSITION_REJECTED`, and it creates no second command chain.
A conflicting remote HOLD fails ordinary stream admission and cannot install an
effect slot. Once a restrictive effect slot exists, changed equal/lower severity
cannot invoke again and only HOLD-to-ESTOP can upgrade. A later Active candidate
can never weaken an installed restrictive effect. This preserves bounded ESTOP
priority without giving arrival order or rejected HOLD bytes authority.

Fail-safe idempotency is a publisher-position slot, not a content-selected key.
`BodyFailSafeEffectSlotKey` binds grant ID/slot, authenticated publisher,
declaration/stream epoch, route/audience, session/generation and security context.
It excludes command content, command ID, signature, transport and receipt bytes.
The slot entry binds the canonical authenticated protected-content digest, mode/
severity and one state from
`RESERVED | OUTCOME_PENDING_RESOLUTION | TERMINAL_TOMBSTONE`; exact-key absence
is typed nonmembership. Re-signing identical protected content joins the same
entry. Changed content at the same slot creates a conflict tombstone and no new
effect when its severity is equal or lower. The only content-conflict widening is
severity-monotonic HOLD-to-ESTOP. The bounded tombstone retains the first selected
content digest/severity/effect lineage, at most the first conflicting digest, and
a saturated `CONFLICT_SEEN` marker plus profile-bounded counter. Later variants
return that tombstone without a durable append or counter growth. It remains until
irreversible generation retirement; compaction cannot make membership ambiguous.

The closed `BodyFailSafeEffectSelection` union is
`ACTIVE_NO_EFFECT | INSTALL_NEW_RESTRICTIVE_EFFECT |
JOIN_IDENTICAL_PENDING_EFFECT | RETURN_IDENTICAL_TERMINAL_EFFECT |
JOIN_OR_RETURN_STRONGER_GLOBAL_EFFECT | CONFLICT_NO_NEW_EFFECT |
UPGRADE_HOLD_TO_ESTOP | REJECT_EFFECT_FRESHNESS`. ESTOP INSTALL and UPGRADE
require an exact arbiter restrictive-chain transition, never-reused fence epoch,
pending operation and one-use invocation token. HOLD INSTALL instead includes
the arbiter transition, complete ordinary admission, admitted predecessor, body
reservation, fence, pending operation and token in one authority-domain
transaction. Failed HOLD admission leaves none of them installed. ESTOP INSTALL
can use the complete pre-replay gate defined below. UPGRADE appends a distinct
ESTOP action against the complete current HOLD/restrictive frontier. It cannot
inherit the HOLD token. JOIN can resume or query only that same installed
operation. It performs the first invocation only after its body reservation
mirror commits. It also requires definitive proof that the arbiter token remains
unconsumed. JOIN cannot create or perform a second invocation. RETURN,
stronger-global, conflict and freshness-rejection branches cannot invoke.
Unknown, default, mixed, wrong-slot and missing-state cases reject.

One `BodyFailSafeSeverityArbiter` is committed by the same body selector. Its HOLD
component has a never-reused stable cycle ID, its origin gate epoch, the latest
gate epoch that carried it and one closed state:
`NONE | HOLD_PENDING | HOLD_EFFECTIVE | HOLD_OUTCOME_UNKNOWN |
HOLD_CYCLE_CONSUMED`. `HOLD_EFFECTIVE` and `HOLD_OUTCOME_UNKNOWN` are terminal
physical-result states; the unknown branch claims no clear effect. Every fresh
FENCED epoch that is not a qualified reopen carries the exact cycle ID and state
forward. ESTOP upgrade, restart, rebind, overflow, capacity pressure and another
restrictive cut cannot reset, consume or silently replace it.

Exact `NORMAL_HOLD_RECOVERY` alone consumes `HOLD_EFFECTIVE`. Receipt-free
`BodyNormalHoldRecoveryFact` binds the current cycle, exact FENCED arbiter with
no pending operation, ESTOP floor `NONE`, typed pending-ESTOP absence, qualified physical
recovery and exact body head. Its body-only CAS preserves HOLD, lease/declaration
absence and the FENCED arbiter mirror, retains every slot/operation tombstone and
installs `HOLD_CYCLE_CONSUMED`, not NONE. Its
`BodyNormalHoldRecoveryReceipt` binds that commit. A later exact acquisition,
successor grant or reconnect activation alone changes CONSUMED to NONE while
atomically installing ACTIVE, LIVE authority and a fresh OPEN epoch. Replay
returns the same bundle; changed cycle/head rejects. `HOLD_PENDING` cannot finalize or reopen. If its bounded
same-key result path ends without definitive evidence, the normal arbiter result
DAG first terminalizes it as `HOLD_OUTCOME_UNKNOWN`; that state permanently
forbids same-generation reopen and requires retirement plus the applicable
physical-boundary closure. Physical quiescence cannot relabel pending HOLD as
effective.
Its generation-global ESTOP floor is
`NONE | ESTOP_LATCHED | ESTOP_OUTCOME_UNKNOWN`; it never decreases inside a
non-retired generation. A distinct
optional `pending_estop_operation` holds the exact one-use token before its
boundary result. A pending operation and either non-NONE floor forbid gate reopen.
Definitive boundary no-effect clears only the pending operation and retains its
failure tombstone; the floor remains `NONE`. Confirmed latch installs
`ESTOP_LATCHED`; ambiguous possible effect installs `ESTOP_OUTCOME_UNKNOWN`. A
fresh ESTOP in the same or a different slot while HOLD is pending, effective or
outcome-unknown, while the ESTOP floor is `NONE` and no ESTOP operation is
pending, uses
`UPGRADE_BODY_FAIL_SAFE_TO_ESTOP`. Before that body event, the arbiter selects
the ESTOP profile action against the complete current HOLD/restrictive frontier
through either the complete-dominance or qualified severity-override START branch,
consumes a distinct pre-reserved ESTOP token, appends one pending restrictive-
chain operation and advances `FENCED -> FENCED` with a fresh shared gate epoch.
The body upgrade consumes that exact arbiter receipt and mirrors the pending
operation; it does not reopen the gate, repeat the clear boundary or inherit the
HOLD token. Later ESTOP attempts join/query that operation. HOLD cannot pass,
cancel or downgrade it. An unknown ESTOP boundary remains non-authorizing and
cannot become an ordinary HOLD cycle. This priority edge prevents an ambiguous
clear from starving latch escalation while still allowing a later fresh gate
epoch to process a new HOLD after authenticated recovery.

Software order alone is insufficient. The named clear/latch boundary owns a
durable `BodyFailSafeBoundarySeverityState` and one serial acceptance order, but
that state is a device-specific subordinate of the authoritative arbiter
operation. It cannot be invoked or used directly by a body event. Every HOLD or
ESTOP invocation token binds its exact arbiter operation and severity-state
version. For ESTOP upgrade, the same qualified pre-invocation fault domain that
installs the pending arbiter operation advances the boundary guard to
`ESTOP_PENDING` with a fresh version, permanently makes every older unconsumed
HOLD token non-acceptable, and returns
`BodyFailSafeBoundarySeverityFenceReceipt` without invoking the latch. The
arbiter successor/receipt and later body upgrade bind that receipt/version. If
the body CAS loses or crashes, the unmatched arbiter fence and severity guard
remain restrictive and must be reconciled; neither can be abandoned as HOLD-
accepting or OPEN. A deployment that cannot bind the severity guard and pending
arbiter operation in this qualified fault domain disables remote HOLD/ESTOP.

At actual boundary acceptance, a HOLD token succeeds only while its bound
severity version is current and no ESTOP is pending, accepted or outcome-unknown.
If ESTOP won the boundary order, the older clear returns definitive
`REMOTE_EFFECT_REJECTED_BEFORE_BOUNDARY` with selected cause
`HOLD_SUPERSEDED_BY_ESTOP` and no clear effect. If HOLD acceptance won
first, the later ESTOP may latch in the next serial position. Thus no delayed
clear can modify or release a pending or accepted ESTOP. Both acceptance and
no-effect receipts bind the boundary severity versions and order. A deployment
whose clear and latch operations cannot provide this atomic severity-aware order
keeps remote HOLD/ESTOP disabled.

ESTOP fail-safe effects and command admission are orthogonal. Remote HOLD effects
are not. Both modes first pass these checks:

- strict raw byte and shape limits.
- protected-envelope validation and canonical frame kind and version.
- the verified transport principal.
- current default-deny manifest permission for the actor and action plane.
- the exact route, audience, and direct realm.
- the live session and generation.
- the authenticated publisher, declaration, and stream epoch.
- a positive syntactic position and current security state.
- one unambiguous and structurally valid mode with its field exclusions.
- an installed plant-profile action.
- an installed unexpired grant with an exact permitted slot. An ESTOP-only
  upgrade can instead use one exact unconsumed slot in the current preserved
  `BodyFailSafeEscalationAdmissionSnapshot` and its unchanged deadline.

ESTOP can then select its retained effect slot before ordinary stream-order,
occupied-position, command-identity, and lease checks. HOLD must satisfy every
ordinary admission check before it can select an effect. The same reservation
CAS appends its exact `received -> admitted` chain. No HOLD boundary token exists
before that durable admission.

Exact pending or terminal replay joins or returns the retained state without a
fresh durable ingress attempt. An already recorded conflict does the same. Only
bounded rate-limited telemetry can change. The first same-slot conflict can
install its bounded conflict marker without a boundary token. A new Active
command, a qualified new HOLD or ESTOP slot, or an ESTOP upgrade
atomically reserves a fresh body-local ingress-attempt identity and appends
`CommandIngressAttemptRecord`. The non-authorizing record binds:

- the exact protected bytes and digests.
- the current-session context, body clock, and receive time.
- the grant, slot, and unchanged deadline.
- the effect selection and global severity state.
- one closed `side_effect_intent`: `NONE_ACTIVE`, `CLEAR_ACTIVE`, or
  `CLEAR_AND_LATCH_ESTOP`.

A new HOLD effect binds its complete ordinary-admission
predicate and installs its `received -> admitted` chain in that same CAS. A new
ESTOP effect binds the durable pre-replay gate evidence. Both bind their
reservation, fence or upgrade ancestry and complete active-command/application
roots. Join, return, unqualified conflict and expired branches structurally
forbid a new reservation, fence or invocation token.

The arbiter-to-body reservation mirror is necessary but not timely boundary
acceptance. The reservation deliberately retires live declaration/grant use only
after ordinary HOLD admission or after the complete ESTOP pre-replay gate. The
qualified clear/latch boundary consumes only the current arbiter operation's
invocation token. That token is paired with the installed body reservation or
upgrade receipt and its captured pre-cut grant, slot, and deadline snapshot.
There is no second body-owned physical invocation token. It does not require
that retired grant to remain live. At most once, the boundary atomically
evaluates the unchanged `FAIL_SAFE_EFFECT_NOT_AFTER`, exact session/generation
and security context, reservation gate/fence epoch, and boundary severity
state/version at its acceptance instant. Strict-before acceptance
emits `BodyFailSafeBoundaryAcceptanceDeadlineEvaluationReceipt` over the token,
protected-content digest, selected clear/latch intent, deadline evaluation, gate
and severity order, and boundary instant. Equality or later time produces definitive
no-effect. The closed `BodyFailSafeBoundaryNoEffectCause` total precedence is
`SESSION_OR_GENERATION_CUT | SECURITY_CONTEXT_CUT |
RESERVATION_GATE_RETIRED_OR_REPLACED | HOLD_SUPERSEDED_BY_ESTOP |
FAIL_SAFE_EFFECT_DEADLINE_ELAPSED | OTHER_DEFINITIVE_BOUNDARY_REJECTION`.
`BodyFailSafeBoundaryNoEffectReceipt` binds exactly one selected cause, the
current boundary/security order and structurally forbids evidence fields for
every other cause. Its outcome is
`REMOTE_EFFECT_REJECTED_BEFORE_BOUNDARY`; the software authority cut and
restrictive fence remain. An effect-claiming completion after a later cut requires
exact proof that acceptance preceded the deadline and fence. A definitive no-
effect result binds its exact no-effect receipt. The boundary result next goes
only through `RESOLVE_BODY_ACTUATION_RESTRICTIVE_ACTION`, which consumes the
same arbiter token, updates the exact chain member/possible-output product and
emits the installed arbiter result receipt. The body cannot complete from the raw
boundary receipt. A timeout, cancellation or local return without either proof
installs or preserves the exact ambiguous arbiter result/query branch. A profile watchdog or
capacity action can independently take a local safe action after expiry, but its
record is local-policy evidence and never impersonates acceptance of the stale
remote command. An implementation without atomic deadline-aware, idempotent,
queryable and severity-aware fail-safe boundary acceptance disables remote
HOLD/ESTOP.

`MARK_BODY_FAIL_SAFE_EFFECT_OUTCOME_PENDING` is the only body transition after
an ambiguous boundary return. It consumes the exact installed
`OUTCOME_PENDING_QUERY_OR_RESOLUTION_FENCED` entry and ambiguity receipt,
preserves the reservation/upgrade mirror, captured snapshot,
effect-slot entry, gate/severity fence and bounded same-key query/resumption
rights. Receipt-free `BodyFailSafeEffectBoundaryStatusFact` drives one body CAS:
ingress `SIDE_EFFECT_RESERVED -> SIDE_EFFECT_OUTCOME_PENDING_RESOLUTION`,
effect slot `RESERVED -> OUTCOME_PENDING_RESOLUTION`, and, for ESTOP only,
pending ESTOP `RESERVED -> OUTCOME_PENDING_RESOLUTION`; HOLD requires typed
pending-ESTOP absence. `BodyFailSafeEffectBoundaryStatusReceipt` binds all
changed/preserved entries. The event installs no terminal side-effect record or
command disposition and cannot invoke with a new identity. A definitive same-key boundary query first updates that
same arbiter operation/chain member through
`RESOLVE_BODY_ACTUATION_RESTRICTIVE_AMBIGUITY`; it cannot use a new token. Later
`COMPLETE_RESERVED_FAIL_SAFE_COMMAND` consumes the resulting exact arbiter
accepted/no-effect receipt, or installs terminal
`UNKNOWN_AFTER_SIDE_EFFECT_BOUNDARY` only after the arbiter receipt proves every
bounded query/resumption right ended through
`CLOSE_BODY_ACTUATION_RESTRICTIVE_AMBIGUITY_UNKNOWN` while the operation remains
unknown and fenced. A timeout label alone cannot skip the pending state.

Only a selected fresh ESTOP reservation can precede ordinary command-stream
replay, lease, channel, source, and remaining semantic checks. The installed
action and profile check named above still occurs before reservation. The
reservation can cut Active software authority and request the body-local stop
latch. Remote HOLD must first pass those checks and install its admitted
predecessor. Exact replay joins or returns. Same-slot changed bytes cannot repeat
an equal or lower effect.
A fresh ESTOP can only take the monotonic upgrade edge. No remote side effect is
permitted for an old generation, wrong route, principal or audience, or an
unverifiable or oversized envelope. An ambiguous mode, invalid grant or slot,
expired deadline, or incomplete current-session context is also inert. This
preserves ESTOP priority without turning HOLD, arrival time, signature variation,
or an old signed frame into a timeless credential.

The plant profile sets a hard
`max_fail_safe_effect_slots_per_generation`. The implementation reserves separate
capacity for one generation-global ESTOP escalation token and for the evidence
that closes the generation. From a non-ESTOP predecessor, before the last general
slot could be consumed, the arbiter first consumes a pre-reserved capacity-cut
restrictive token, advances the shared gate to a fresh FENCED epoch and installs
the profile's local action at least as restrictive as HOLD as a pending chain
operation. `EXHAUST_BODY_REMOTE_COMMAND_CAPACITY_TO_RETIREMENT_DRAIN` is the
required pre-invocation body-mirror owner. It consumes that arbiter receipt,
closes general remote command admission, preserves every effect-slot tombstone,
mirrors the pending operation and enters irreversible generation retirement
drain. Only after that body mirror is installed can the named boundary consume
the arbiter token once. `RESOLVE_BODY_ACTUATION_RESTRICTIVE_ACTION` then installs
the arbiter result, and
`RECONCILE_BODY_ACTUATION_ARBITER_TRANSITION(RESTRICTIVE_RESULT_MIRROR)` mirrors
that result and closes the exact capacity-action obligation. This non-fail-safe
path structurally forbids `COMPLETE_RESERVED_FAIL_SAFE_COMMAND`; drain entry and
reconciliation do not claim that the action succeeded. Reconnect, clock restore
and same-generation resume are then impossible. The only remaining remote edge is
`ESTOP_ONLY_DRAIN_ADMISSION`. At drain entry the same capacity CAS either
preserves the generation's one still-unexpired ESTOP-only grant/slot, consumes the
unused one-use budget to install exactly one such grant/slot, or records that no
remote edge remains. The first two branches bind that sole slot into the drain
head. A valid remote ESTOP first consumes the reserved escalation token in a new
arbiter chain operation, advances FENCED to a fresh FENCED epoch, then uses
`ESTOP_ONLY_DRAIN_ADMISSION` to install the exact body reservation mirror before
the sole latch invocation. It cannot admit Active/HOLD or reopen a declaration/
lease. Use, expiry, rejection or tombstoning closes the remote edge permanently;
drain cannot mint a successor grant or slot. If the token or its evidence cannot
be preserved, the capacity transition closes the remote edge and requires the
deployment's separately authorized out-of-band hardware interlock. NCP remains
`ESTOP_OUTCOME_UNKNOWN` unless the unified arbiter operation later supplies
exact latch evidence; it cannot claim `ESTOP_LATCHED` or fall back to HOLD.

From any member of the ESTOP-restrictive class defined above, capacity exhaustion
cannot use that generic drain edge.
`SEAL_BODY_REMOTE_COMMAND_CAPACITY_UNDER_ESTOP` closes
general and remaining remote admission, preserves the exact ESTOP-restrictive
state or pending operation,
accepted-transfer fence, HOLD-cycle ancestry, arbiter mirror and outstanding
query/result obligations, and installs no capacity-action token or physical
invocation. Only `OPERATOR_RESET_AND_RETIRE_GENERATION` or
`INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE`, respectively, can later enter drain
and must consume this capacity seal together with their normal local evidence.
Effect-
slot keys can be compacted only after the installed final retirement selector
makes every old-generation frame permanently unacceptable.

`RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT` is the body reservation mirror and software-
authority cut. Its ESTOP branch requires the complete pre-replay restrictive gate.
Its HOLD branch conditionally compares the complete ordinary admission predicate.
The predicate includes position replay, command identity, and the exact
live-holder lease. It also includes strict HOLD field exclusions, the installed
profile, and the unchanged deadline. The HOLD branch is
one authority-domain transaction. It installs the arbiter operation and token,
body reservation, fence, and one-time authenticated `received -> admitted`
chain with `VERIFIED_BODY_LEASE_AT_FAIL_SAFE_RESERVATION_CUT`. A failed compare
installs none of those values. The ESTOP branch consumes the exact arbiter
fence/START receipt created after its pre-replay gate. The winning transaction
atomically performs these changes:

- removes live lease authority.
- retires the live declaration.
- installs or preserves HOLD for a non-ESTOP predecessor.
- preserves an existing ESTOP latch.
- partitions and fences the complete command and application sets.
- records the pending fail-safe operation.

It terminalizes a cancellable authority operation and preserves an accepted
transfer at the same or a later fenced phase. It does not claim that a requested
new ESTOP latch is physically effective. Every authority-widening transition
structurally rejects while this operation or an arbiter gate mismatch is pending.
A restrictive rebind or retirement must carry the exact reservation and fence.
The reservation allocates no second physical token and cannot invoke the named
boundary. If an ESTOP reservation CAS loses, its pending arbiter operation
remains fenced. Before invocation or authority progress, the same receipt must
rebase over the winning body head. A losing HOLD transaction leaves no
pending operation or token.

The cut also retains a bounded `BodyFailSafeEscalationAdmissionSnapshot` over the
exact pre-cut manifest, current security state, publisher/declaration, unexpired
freshness-grant registry and unused slots. That snapshot authorizes no Active or
HOLD work and cannot refresh a deadline; it exists only so a later authenticated,
fresh ESTOP is not stranded by the declaration retirement caused by an earlier
HOLD. `UPGRADE_BODY_FAIL_SAFE_TO_ESTOP` verifies the same current security/
session/generation, exact preserved slot authority and strict-before deadline;
the current `BodyFailSafeEscalationQualificationRoot`; and the exact installed
complete-dominance or qualified severity-override START evidence for the current
frontier. It is legal from `HOLD_PENDING | HOLD_EFFECTIVE |
HOLD_OUTCOME_UNKNOWN`. It then consumes the already installed ESTOP arbiter-
operation/fresh-fence receipt
and advances the body-owned global severity mirror through the same body
selector. It preserves the original HOLD reservation and exact prior chain
ancestry. It allocates no latch token and cannot invoke before that body mirror
commits. A losing, expired, same/lower-severity, wrong-principal or wrong-slot
upgrade cannot invoke.

The body records the boundary state change in a distinct non-authorizing
`BodyFailSafeSideEffectRecord`, never by skipping `admitted` in a command
disposition chain. The record binds the exact protected envelope and command
candidate bytes/digests, `CommandIngressAttemptRecord`, verified current-session context,
closed mode classification, exact body buffer/latch boundary, before/after state
commitments, body clock and global journal position, and one closed outcome:
`CONFIRMED_CHANGED | CONFIRMED_ALREADY_EFFECTIVE |
REMOTE_EFFECT_REJECTED_BEFORE_BOUNDARY |
UNKNOWN_AFTER_SIDE_EFFECT_BOUNDARY`. The rejected outcome binds the exact
selected `BodyFailSafeBoundaryNoEffectCause` and definitive no-effect evidence.
A clear-only outcome cannot claim an ESTOP latch, and a rejected or unknown
outcome cannot claim physical effect.

`COMPLETE_RESERVED_FAIL_SAFE_COMMAND` is the only body transition that consumes
the selected initial reservation or ESTOP-upgrade mirror after the arbiter has
resolved the boundary call. Its composite compare-and-swap still expects the
installed reservation/upgrade head and consumes exactly one matching
`BodyActuationRestrictiveActionResultReceipt` plus its bound severity/deadline
evidence. A raw boundary receipt, state label or body-owned token is insufficient.
It installs this record and refines the already non-authorizing cut state. A prior
`ESTOP_LATCHED` lifecycle remains
`ESTOP_LATCHED` for every side-effect intent and outcome; a command candidate can
never reset it to HOLD. From a non-ESTOP predecessor, confirmed `CLEAR_ACTIVE`
remains HOLD and confirmed `CLEAR_AND_LATCH_ESTOP` enters `ESTOP_LATCHED`.
`REMOTE_EFFECT_REJECTED_BEFORE_BOUNDARY` retains the software HOLD/fence,
terminalizes the exact arbiter operation with its no-effect cause and claims no
remote boundary effect. `HOLD_SUPERSEDED_BY_ESTOP` retains the stronger ESTOP
boundary state and cannot clear or modify the latch. A session, security or gate
cut preserves the more restrictive successor state. Deadline expiry cannot be
relabeled as a cut, and no branch clears a confirmed or unknown ESTOP floor.
`UNKNOWN_AFTER_SIDE_EFFECT_BOUNDARY` for clear-only keeps authority lifecycle in
HOLD but terminalizes the independent HOLD cycle as `HOLD_OUTCOME_UNKNOWN`; it
cannot record `HOLD_EFFECTIVE` or definitive no effect. For any ESTOP-
latch intent it enters `ESTOP_OUTCOME_UNKNOWN`, preserves the prior HOLD/ESTOP
fence and blocks Active, ordinary reset and severity downgrade. Only the ADR-006
qualified inspection/reset-and-retire path can consume that unknown lifecycle
state. It does not claim that HOLD or ESTOP was physically achieved.

The reservation cut has already removed live lease authority and the live
declaration. Completion preserves those tombstones and terminalized cancellable
operation, and preserves a durably accepted transfer at the same or a later
fenced phase. From a non-ESTOP predecessor, a later branch can instead enter
retirement drain with those fences intact. From an `ESTOP_LATCHED` predecessor,
the latch and any accepted-transfer fence remain until the exact operator-reset
retirement path. From `ESTOP_OUTCOME_UNKNOWN`, the unknown result and transfer
fence remain until the exact ADR-006 inspection/reset-and-retire path. No branch
cancels that transfer. The reservation and completion
bundles each emit their applicable authority, declaration-ledger, journal and
generic commit receipts. A journal-only cut, retained live lease, ESTOP
downgrade, canceled accepted transfer, unchanged live declaration or missing
specialized receipt rejects.

For a new ESTOP effect, the journal installs these values atomically before
invoking the latch boundary:

- the exact effect-slot entry and ingress attempt.
- the gate fence or severity-upgrade ancestry.
- the side-effect intent.

For a new HOLD effect, that
reservation first proves every ordinary admission predicate. It then installs
the admitted predecessor, effect slot, fence, and intent. The boundary
consumes the exact arbiter one-use token and records one durable
severity/deadline result. The arbiter then
updates that same registry entry and complete chain/possible-output product;
only its result receipt can reach body completion. An exact replay during
recovery joins this state and cannot allocate a sibling attempt, fence or token.
A HOLD-to-ESTOP upgrade preserves the pending HOLD operation and uses only its
separately pre-reserved arbiter ESTOP token. Confirmed buffer/latch state and the
side-effect record then commit through the completion CAS. A crash or storage fault
at the boundary leaves a durable unresolved reservation: recovery starts in the
corresponding non-actuating state, never restores the prior active buffer, and
blocks new `Active` admission and application until the exact reservation is
finalized or enters retirement drain. It cannot remake the candidate with new
bytes, time, gate epoch or identity.

For a new `NONE_ACTIVE` candidate, full command admission independently emits one
closed `CommandIngressAttemptResolution`. Exact replay returns or joins the
original position entry, ingress resolution and command-chain outcome without a
new durable append. For an ESTOP reservation or upgrade,
`COMPLETE_RESERVED_FAIL_SAFE_COMMAND` installs only the exact terminal side-
effect record and resolution. It advances the retained ingress operation to
`SIDE_EFFECT_RESOLVED_PENDING_COMMAND_ADMISSION`. It writes no command
disposition or attempt resolution and does not terminalize that ingress entry.
For an admitted HOLD, confirmed or unknown boundary outcomes instead advance
directly to `RESTRICTIVE_COMMAND_ADMITTED_PENDING_ASSOCIATION`. A definitive
no-effect result appends the exact `superseded`, `expired`, or `failed` terminal
disposition selected by its closed cause and terminalizes the ingress entry.

`ADMIT_RESTRICTIVE_COMMAND_AFTER_FAIL_SAFE_EFFECT` applies only to ESTOP. It
consumes that exact pending entry and effect resolution. It evaluates the
original candidate against the captured pre-cut declaration, grant snapshot,
unchanged deadline, and remaining admission rules. It then installs the exact
attempt resolution and command-chain records. It never rechecks against the
intentionally retired live declaration, reopens authority, or invokes the effect.
`NEW_COMMAND_CHAIN` is legal only when the exact command identity is absent from
active and retained state. It binds the new one-time
`received -> rejected` or `received -> admitted` result.
`EXACT_REPLAY_EXISTING_CHAIN` binds identical bytes/digests and the already
installed active or retained chain; it emits no new command disposition.
`CONFLICTING_STREAM_POSITION_REJECTED` binds the selected position entry and
unequal candidate digest and creates no new command chain; it remains eligible
only for the separately bounded fail-safe selection described above.
`CONFLICTING_COMMAND_IDENTITY_REJECTED` binds the existing identity and unequal
candidate content, and `REJECTED_BEFORE_COMMAND_IDENTITY` binds the exact
closed structural/semantic reason when no canonical command identity can be
formed. Neither rejection branch creates a command chain.

That ESTOP-only admission event can append a new `received -> rejected` chain or
`received -> admitted` for a fully valid command whose post-effect append still
beats the unchanged deadline. It uses the exact permitted lease-absence branch.
It never appends `stop_latched` in that bundle because boundary acceptance
preceded the admitted predecessor. A qualified ESTOP can latch and then finish
`received -> rejected` after stream-order, occupied-position, or command-identity
conflict. It can also reject when currentness or the unchanged deadline loses a
race after boundary acceptance. An exact
envelope replay joins or returns the existing effect and never invokes the
boundary again. Unequal protected bytes at the same publisher position use the
same effect slot only for qualified ESTOP selection. Equal or lower severity has
no new effect, while HOLD-to-ESTOP can take only the one monotonic upgrade. A
same-command-ID conflict at another position remains a different bounded slot,
but still selects
`CONFLICTING_COMMAND_IDENTITY_REJECTED` and never creates a second `received`.
Neither replay nor conflict gets a new `admitted`, `hold_effective`, or
`stop_latched` disposition.
A fresh invalid `Active` candidate
finishes `received -> rejected` and has no fail-safe side-effect record; an exact
Active replay returns that installed attempt/chain outcome with no new durable
attempt or resolution. After the admission event installs either its terminal
rejection or the later restrictive association reaches a terminal disposition,
the ingress-operation entry can become `TERMINAL`; no earlier event can discard
it.

`ASSOCIATE_ADMITTED_RESTRICTIVE_COMMAND_WITH_EFFECT` is a distinct post-admission
body-journal transition. Receipt-free
`AdmittedRestrictiveCommandEffectAssociationFact` binds the exact pending-
association ingress entry, admitted HOLD/ESTOP tip and terminal fail-safe record
for identical protected bytes, grant/slot, intent and reservation, expected body/
journal head, next sequence and retained reserve. Its sole body-selector CAS
changes ingress pending-association to TERMINAL and the tip
`ADMITTED -> HOLD_EFFECTIVE | STOP_LATCHED | UNKNOWN_AFTER_BOUNDARY`.
Accepted HOLD selects HOLD_EFFECTIVE, accepted ESTOP selects STOP_LATCHED, and
terminal ambiguity selects UNKNOWN_AFTER_BOUNDARY. A definitive HOLD no-effect
was terminalized during completion. A definitive ESTOP no-effect cannot enter an
admitted association. The generic body/journal receipts precede
`AdmittedRestrictiveCommandEffectAssociationReceipt`, which binds earlier
effect evidence/instant and the strictly later association append. Admission
pre-reserves this bounded bundle. Exact replay returns it; changed bytes, outcome
or key rejects. No other event terminalizes pending-association. It invokes no
boundary operation, arms no watchdog and cannot change severity.

`DispositionJournalHead` carries a bounded map from never-reused ingress-attempt
identity to closed `CommandIngressAttemptOperationState`. The state records exact
candidate/content and optional command identity and admits only:
`ACTIVE_ATTEMPT_PENDING`, `SIDE_EFFECT_RESERVED`,
`SIDE_EFFECT_OUTCOME_PENDING_RESOLUTION`,
`SIDE_EFFECT_RESOLVED_PENDING_COMMAND_ADMISSION`,
`RESTRICTIVE_COMMAND_ADMITTED_PENDING_ASSOCIATION`,
or `TERMINAL`. Each branch requires only
the attempt, reservation, outcome, attempt-resolution and side-effect-resolution
objects that can exist at that point and structurally forbids inconsistent or
default fields. Every related append compare-and-swaps this map entry in the
same global journal transition.

The exact HOLD path is
`ACTIVE_ATTEMPT_PENDING -> SIDE_EFFECT_RESERVED ->
SIDE_EFFECT_OUTCOME_PENDING_RESOLUTION ->
RESTRICTIVE_COMMAND_ADMITTED_PENDING_ASSOCIATION -> TERMINAL`.
The reservation edge already carries the admitted predecessor. A definitive
no-effect completion can move directly from a reserved state to `TERMINAL`.
The exact ESTOP path is
`ACTIVE_ATTEMPT_PENDING -> SIDE_EFFECT_RESERVED ->
SIDE_EFFECT_OUTCOME_PENDING_RESOLUTION ->
SIDE_EFFECT_RESOLVED_PENDING_COMMAND_ADMISSION ->
RESTRICTIVE_COMMAND_ADMITTED_PENDING_ASSOCIATION -> TERMINAL`.
Either pending-outcome edge is omitted for an immediately definitive boundary
result. `RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT` takes the first edge, never
ABSENT-to-reserved. Its HOLD case proves and records complete ordinary admission.
Its ESTOP case uses the complete pre-replay gate.
`ADMIT_RESTRICTIVE_COMMAND_AFTER_FAIL_SAFE_EFFECT` is ESTOP-only. It enters
pending association for an admitted result. Rejection or no-chain enters
`TERMINAL`.

Every event that removes live authority or a live command declaration binds one
receipt-free `BodyAuthorityCutCommandPartitionFact`. It binds the exact prior
composite/journal heads, cut and arbiter-fence evidence, and canonical complete
active-command, application-attempt and ingress/fail-safe-operation roots. Its
pairwise-disjoint partitions preserve already terminal chains, map each
unadmitted `received` tip to an exact linked `rejected` record, separate
`ADMITTED_NOT_STARTED` tips with proved application-attempt-map nonmembership
from `APPLICATION_ATTEMPT_INSTALLED`, and classify each installed attempt as
definitive acceptance before the fence, definitive no-effect, or fenced/ambiguous
pending query/resolution. It also classifies every ingress/fail-safe operation.
Their union equals every prior key; a caller
subset or generic shared key rejects.

The fact allocates one canonical command-key order and contiguous strictly
increasing global journal-sequence range for every record installed by the bulk
cut. Each new terminal record links its exact prior command tip. The successor
sets the final record as its last global record, installs exact key-to-record and
key-to-fence bijections, and preserves every unrelated retained chain. A map
label without its authenticated linked record is invalid.

Each `BodySessionControlBodyCommandCutResolutionKey` has a closed total path:
`ADMITTED_NOT_STARTED -> TERMINAL_TOMBSTONE` only through
`CLOSE_FENCED_COMMAND_BEFORE_APPLICATION_ATTEMPT`;
`APPLICATION_ATTEMPT_INSTALLED -> TERMINAL_TOMBSTONE` through definitive
`CLOSE_FENCED_COMMAND_AFTER_AUTHORITY_CUT`, or
`APPLICATION_ATTEMPT_INSTALLED -> OUTCOME_PENDING_QUERY_OR_RESOLUTION` through
`MARK_BODY_COMMAND_APPLICATION_OUTCOME_PENDING`, followed by
`OUTCOME_PENDING_QUERY_OR_RESOLUTION -> TERMINAL_TOMBSTONE` through definitive
fenced closure or `CLOSE_BODY_COMMAND_APPLICATION_AMBIGUITY`. The receipt-free
partition fact, command tip and attempt evidence change in one body CAS; its
`BodyCommandCutResolutionClosureReceipt` binds the exact prior/terminal entry.
Replay is exact; missing, extra or reopened keys reject.

`CLOSE_FENCED_COMMAND_BEFORE_APPLICATION_ATTEMPT` consumes one exact
`ADMITTED_NOT_STARTED` tip. It requires the installed cut/fence and exact typed
nonmembership of any application attempt, query or retry right, appends
`superseded` with the selected gate/authority-cut cause, and cannot invoke or
claim boundary evidence.

`CLOSE_FENCED_COMMAND_AFTER_AUTHORITY_CUT` consumes one exact fenced admitted tip
and installed application attempt from its separate partition. Definitive arbiter
acceptance that ordered before the fence can install `applied` with
`BodyBoundaryApplicationEvidence`. Definitive no-effect uses the same total
cause-to-terminal mapping as normal resolution: gate/authority/grant/lease cut is
`superseded`, TTL is `expired`, and only other definitive rejection is `failed`.
An ambiguous boundary first uses
`MARK_BODY_COMMAND_APPLICATION_OUTCOME_PENDING` and remains queryable with no
terminal disposition. Only `CLOSE_BODY_COMMAND_APPLICATION_AMBIGUITY`, after all
bounded invocation/query/resumption rights provably end, can install terminal
`unknown_after_boundary`. No other branch can create `applied`, and terminal
unknown never strengthens. The closure events are legal from a
non-authorizing HOLD/ESTOP or emergency-rebind state and from parent
`RETIRED_DRAIN_ONLY`; it requires the original admission/cut evidence but no
currently live lease or declaration.

`CLOSE_FENCED_BODY_OPERATION_AFTER_AUTHORITY_CUT` similarly consumes one exact
ingress, fail-safe or application-recovery obligation and installs only its
evidence-derived terminal outcome. In parent drain-only, the arbiter first
executes `RETIRE_BODY_ACTUATION_BOUNDARY_AFTER_PHYSICAL_QUIESCENCE`. That
transition requires the installed FENCED head, no pending invocation or
ARMED/current watchdog, complete terminal operation and watchdog ledgers, a fail-safe HOLD
cycle in `NONE | HOLD_EFFECTIVE | HOLD_OUTCOME_UNKNOWN |
HOLD_CYCLE_CONSUMED`, and authenticated
physical-quiescence evidence for the named plant-profile boundary. Its arbiter-
state transition through the jurisdiction-registry selector installs a `RETIRED`
gate, `NO_ACTIVE_OUTPUT`, retained
`RETIRED_WITH_BODY_PHYSICAL_QUIESCENCE` partition and crash-complete retirement
receipt. Physical-quiescence evidence is a separately qualified observation/
inspection input, not an actuator invocation. This transition creates no
boundary-operation entry or invocation token; the closed operation-kind union
therefore has no retirement-quiescence kind. It does not claim regulatory
safety. In particular, it preserves an already terminal HOLD result and cannot
convert `HOLD_PENDING` to `HOLD_EFFECTIVE`, terminal unknown or no effect.

Receipt-free `BodyActuationBoundaryPhysicalQuiescenceFact` binds a complete
watchdog/reserve partition at the same arbiter-incarnation coordinate. The
retirement CAS changes only the exact current-output watchdog lineage from
`FENCED_TO_RESTRICTIVE_ACTION` or `EXPIRED_TO_RESTRICTIVE_ACTION` to
`RETIRED_WITH_BODY_PHYSICAL_QUIESCENCE`; unrelated
`REPLACED_BY_NEWER_ACCEPTANCE` and already
`RETIRED_BY_CLOCK_DISCONTINUITY` entries retain their cause. Typed absence of a
current watchdog creates no entry. The CAS also changes
emergency reserve `INSTALLED -> RETIRED`, overflow reserve
`QUALIFIED -> RETIRED` or `CONSUMED -> RETIRED`, and an existing overflow seal
`SEALED_START | SEALED_INTERLOCK -> RETIRED`. Typed seal absence stays absent.
The `BodyActuationBoundaryRetirementReceipt` binds this complete partition and
retained no-reuse digests. A successor creates fresh reserve/seal keys at a new
coordinate; it never performs `RETIRED -> INSTALLED | QUALIFIED`.

That retirement event has two disjoint readable-registry owner branches. The
normal branch requires `OWNED_BY_GENERATION_FENCED`, retains that owner until
normal handover, and permits the complete terminal histories described above.
The partial-genesis branch requires
`RESERVED_PARTIAL_RETIREMENT_FENCED`, the exact
`ActuationAuthorityDomainReservedPartialRetirementFenceReceipt`, ADR-001 partial-
parent-retirement evidence, HOLD cycle `NONE`, and a
complete proof that the arbiter history contains only genesis FENCED state. Its
same jurisdiction-registry CAS moves the owner to
`RESERVED_PARTIAL_RETIREMENT_RETIRED` with
`EXACT_GENESIS_ARBITER_RETIRED` and emits
`ActuationAuthorityDomainReservedPartialRetirementReceipt`. The candidate heads
contain the receipt-free retirement fact, not either post-CAS receipt.

If only the reserved genesis arbiter state is lost, the distinct
`ISOLATE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_STATE_LOSS`
transition consumes `BodyActuationLostArbiterPhysicalIsolationFact`, exact
partial-parent evidence, the exact partial-retirement fence receipt and qualified
isolation for the complete domain footprint. Its registry CAS installs
`RESERVED_PARTIAL_RETIREMENT_RETIRED` with
`LOST_GENESIS_ARBITER_PHYSICALLY_ISOLATED` and emits the same typed partial-
retirement receipt. It installs no arbiter head, epoch or result. A lost or
unreadable jurisdiction selector cannot take this edge and keeps the footprint
unavailable for external topology retirement/re-enrollment.
Both retired candidate branches bind only their receipt-free retirement or
isolation fact plus the preexisting preparation and fence receipts. They
structurally exclude their own post-CAS
`ActuationAuthorityDomainReservedPartialRetirementReceipt`; that receipt binds
the prior and installed registry heads and exact selected closure branch.

The closed `BodyActuationBoundaryRetirementClosureEvidence` union is
`EXACT_ARBITER_RETIREMENT | LOST_ARBITER_PHYSICAL_ISOLATION`. The exact branch
binds the domain's retirement receipt, terminal/quiescent arbiter head and complete
outstanding-obligation root. The lost-state branch binds
`BodyActuationLostArbiterPhysicalIsolationFact`: the last authenticated full
mirror, complete possible operation/output/watchdog/token inventory, qualified
physical interlock/isolation evidence, isolation boundary and no-reuse horizon.
It installs no arbiter head, epoch or receipt and cannot claim the unknown old
state became RETIRED. If the last authenticated mirror contains `HOLD_PENDING`,
the lost-state closure records it only as terminal `HOLD_OUTCOME_UNKNOWN` in the
body retirement inventory. It never records `HOLD_EFFECTIVE` or a definitive no-
effect result, and it still creates no arbiter successor.
`INSTALL_BODY_RETIREMENT_BOUNDARY_CLOSURE_EVIDENCE` consumes exactly one branch
for the generation's exact domain key. If the exact branch's body compare-and-swap loses,
the arbiter remains retired and a rebase installs the same receipt over the
later body head; no recovery can reopen it. A lost-state branch with missing or
ambiguous physical isolation remains incomplete and blocks finalization.
Receipt-free `BodyRetirementRetentionCompactionFact` partitions complete
consumed arbiter-receipt-index and semantic-obligation sets from every live
reference. `COMPACT_BODY_RETIREMENT_RETENTION` alone changes exact entries
`CONSUMED -> RETIRED_TOMBSTONE` in both maps, retaining each key, receipt-set/
obligation digest, consumed linkage and never-consume-again proof. Pending or
live-referenced entries cannot compact; omitted/extra entries reject. Its one
body CAS emits `BodyRetirementRetentionCompactionReceipt`; replay is exact.
Other evidence required by a live closure, effect-slot tombstone, ESTOP
escalation, arbiter operation or terminal/quiescent head remains exact. Body retirement finalization requires
the exact selected closure evidence and receipt and rejects every remaining
`HOLD_PENDING` or other nonterminal fail-safe operation. These closure event kinds
are the complete drain/rebind closure union. They cannot admit, apply without pre-fence acceptance
evidence, create a lease/declaration, reopen a transfer, or change command
bytes. Each emits a specialized receipt over the generic body commit and its
exact prior/installed subordinate heads.

Any nonterminal HOLD/ESTOP entry is a pending higher-severity operation. New
Active admission, same-generation descriptor rebind, and planned security
rebind, authority acquisition and return to Active require the exact pending
higher-severity and fenced-command/application sets to be empty. Emergency
rebind carries each such entry into fenced recovery and cannot discard it.
Terminal entries move to a
bounded retained commitment/tombstone set before eviction. Before capacity,
sequence, or retention limits could permit attempt-identity reuse or erase an
unresolved operation, the body retires an exact non-ESTOP session generation or
installs an authenticated security/incarnation rotation whose old context can
never be accepted. An ESTOP or indeterminate predecessor remains non-authorizing
and blocks successor-generation creation until authenticated operator reset.

The prior-record digest links records for one command. Its predecessor has a
strictly smaller global journal sequence but need not be adjacent; records for
other commands can interleave. The installed head's active-command tip map, not
`global_sequence - 1`, selects each per-command predecessor. A record that skips
its selected command tip or treats another command's record as its predecessor
rejects.

A first `received` append requires that the exact command identity is absent from
both the active-tip map and retained terminal-command set. A successful
non-terminal successor replaces only that command's active tip; every unrelated
tip and retained terminal entry remains byte-for-byte unchanged. A successful
terminal append atomically removes that active tip and adds the complete terminal
chain commitment to retained state. It cannot remain active, disappear without a
retained terminal commitment, or change another command. A non-command clock
bridge with exact continuity and a planned descriptor/security rebind preserve
the maps; the planned forms require them quiescent. A restrictive clock branch,
emergency rebind, fail-safe reservation, authority cut or retirement applies the
complete partition rule above. A pure Active ingress-attempt/resolution advances
one ingress-operation entry and preserves command maps; a non-Active reservation
also installs its exact gate/cut partition. Every effect is derived from the
authenticated prior head; an append cannot supply an arbitrary replacement map.

The authenticated delivery contains the exact disposition-record bytes. A
receiver bounds and strictly decodes the protected envelope and embedded record
before semantic allocation; rejects duplicate members, unknown members, missing
required members, unknown enum values, non-canonical scalars, and trailing bytes;
recomputes the record, original-frame, content, predecessor, and optional
body-applied-value frame/content digests; and verifies the body envelope and
append receipt over that exact recomputed record. A separately supplied semantic
object or payload that contradicts those authenticated bytes rejects. Metadata
cannot override decoded record content.

An application or later terminal record has a disposition sequence strictly
greater than its admitted predecessor. Within one body clock incarnation, its
body-local timestamp cannot precede that predecessor. Across a body clock
restart, the canonical `BodyClockRestartBridge` is a distinct non-command global
journal record in one closed form. `FROM_EVENT` binds the old and new clock
incarnations, exact prior last-global-event digest/kind/sequence, first new-clock
bridge event context/time, and prior `DispositionJournalHead` digest.
`FROM_EMPTY_HEAD` is allowed only when the authenticated installed prior head has
global sequence `0`, last-event kind `EMPTY_GENESIS`, and no last-event digest; it
binds that exact empty head instead of fabricating a prior event. It leaves every
per-command tip and retained entry unchanged and contains neither its own digest
nor an installed-head digest or receipt. The bridge also binds the exact prior
`PlantAuthorityStateHead` and one closed authority-recovery branch:
`MAP_LIVE_LEASE_DEADLINE_NO_LATER`,
`EXPIRE_LEASE_AND_ENTER_HOLD`, or
`PRESERVE_HOLD_NO_LEASE`, or
`PRESERVE_ESTOP_LATCHED_NO_LEASE`, or
`PRESERVE_ESTOP_OUTCOME_UNKNOWN_NO_LEASE`, or
`RESUME_ACCEPTED_TRANSFER_NO_LATER`. The first branch carries an authenticated
old-to-new-clock mapping and a fresh-clock deadline no later than the old
remaining duration and installs a non-authorizing `RECONNECTING` candidate, not
`ACTIVE`. The expire and preserve-HOLD branches install typed lease absence and
terminalize only cancellable acquisition, renewal, or reconnect work. The
preserve-ESTOP branches accept only their exact confirmed or unknown ESTOP state,
typed lease absence, pending `NONE` and no accepted transfer; each preserves that
state and authorizes nothing.
The transfer branch binds the authenticated exact transfer operation/phase and
one closed lifecycle floor
`NON_ESTOP_FLOOR | CONFIRMED_ESTOP_FLOOR | UNKNOWN_ESTOP_FLOOR`. It maps every
applicable deadline without extension and preserves or advances that latched
phase, every predecessor fence and the exact selected floor. Confirmed and
unknown ESTOP variants cannot substitute. If those
facts are unavailable, the
body can retire a non-ESTOP generation with its fences intact. A confirmed ESTOP
predecessor instead remains latched and non-authorizing with the same or a later
fenced transfer phase until `OPERATOR_RESET_AND_RETIRE_GENERATION`; an unknown
ESTOP outcome remains quarantined until
`INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE`. No restart
branch cancels an accepted transfer or restores predecessor admission. If
restart restores exact authenticated
monotonic-clock continuity under the same incarnation, no bridge is emitted.
Otherwise, the bridge binds the exact installed
`BodyActuationArbiterStateHead`/selector, complete operation-registry,
Active-output, `BodyActuationWatchdogCommitment`, application-attempt and gate
roots. Before its body-selector CAS, the qualified arbiter uses
`FENCE_BODY_ACTUATION_BOUNDARY_AND_SELECT_RESTRICTIVE_ACTION` with kind
`PROFILE_RESTRICTIVE_ACTION` and origin `CLOCK_RESTART`, then resolves or retains that exact
operation. Arbiter-owned `BodyClockRestartActuationFenceReceipt` and
`BodyClockRestartRestrictiveActionReceipt` bind the exact prior/installed arbiter
heads, operation entry, output/watchdog partition, gate order and result. The
body restart emits only its mirror commit. Only a definitive restrictive result can retire the old
output/watchdog pair as `RETIRED_BY_CLOCK_DISCONTINUITY`; a timeout or ambiguous
boundary remains fenced and outcome-pending and cannot issue a grant, reconnect
or reopen. Exact
`CLOCK_RESTART_DEFINITIVE_RESULT_RETIRES_EXACT_PRIOR_WATCHDOG` is a
`RESOLVE_BODY_ACTUATION_RESTRICTIVE_ACTION` case: its receipt-free
`BodyActuationRestrictiveActionResolutionFact` binds origin `CLOCK_RESTART`,
the exact `FENCED_TO_RESTRICTIVE_ACTION` watchdog/output pair and definitive
accepted-or-no-effect result. Its arbiter CAS retires that watchdog while
retaining the result and complete possible-output set; no-effect is not effect or
quiescence evidence. Pending/ambiguous resolution preserves the fenced watchdog.
Acceptance of an installed Active attempt proved before the restart
fence can be recorded later, but it cannot preserve output after that fence.
Definitive no-effect follows the normal cause mapping; unresolved attempts retain
their exact query rights. If the expected body CAS loses, the boundary fence stays
restrictive and `REBASE_BODY_ACTUATION_GATE_FENCE_AFTER_LOSING_CAS` binds it over
the new head before any other progress.

The bridge then binds the canonical complete installed
`BodyCommandFreshnessGrantCommitment` registry and installs one
`EXPIRED_ON_BODY_CLOCK_RESTART` tombstone for every exact grant key. The prior
registry and tombstone map have an exact bijection; omission, preservation,
numeric copying, receive-time refresh or implicit migration rejects. The bridge
preserves every exact reserved, outcome-pending and terminal fail-safe effect
entry. Recovery may consume only the one-use invocation/query right installed
before restart; a terminal tombstone cannot disappear. No new grant, command
admission, application or fail-safe effect can start until the restrictive
restart action, watchdog/output/operation-registry partition, attempt partition and gate/body-head
rebase are all installed. Any later grant uses the new clock; return to Active
also requires a separately qualified fresh gate epoch.
After the in-transaction comparison wins, the same durable bundle materializes a
distinct `BodyClockRestartBridgeCommitReceipt`. That receipt binds the
bridge-record digest and prior
and installed journal heads, prior and installed authority heads, prior and
installed body-session-control heads, and generic composite commit receipt. The
subordinate journal successor increments global sequence, sets last-global-record
digest/kind to that bridge, and changes current body-clock incarnation from the
exact prior value to a fresh never-reused value. The authority successor changes
to that same fresh clock and implements exactly the selected recovery branch.
Both successors are installed by one body-session-control compare-and-swap; a
journal-only or authority-only clock transition is invalid. A later restart after
only a bridge uses `FROM_EVENT` and names that bridge. The global journal sequence
and composite current-head ancestry establish order; raw timestamps from
different clock incarnations are not compared. A new clock incarnation without
that committed bridge cannot issue a causally later disposition, lease proof,
command admission, or ACTIVE transition.

A same-generation descriptor replacement uses one canonical non-command
`BodySessionDescriptorRebindJournalRecord`. It binds the stable
body/plant/session/generation scope; exact old and successor descriptor
revisions, descriptor digests, and negotiation transcripts; the unchanged
security binding; an authenticated closed replacement cause; the idempotency
operation; current body-clock incarnation and event time; the exact prior
journal head and prior global record; and content-addressed commitments to the
complete affected authority and action-command-declaration sets. The record
identifies each declaration preserved byte-for-byte and each declaration
retired because it is not valid under the successor descriptor. It also binds
the exact prior authority head and the successor HOLD/no-lease authority state.
It contains no successor head, selector value, signature, record digest, or
commit receipt.

The descriptor-rebind form is valid only after command admission closes, the
active-command map is empty, and every ingress-attempt and side-effect operation
is terminal and retained. Its predecessor lifecycle is exactly HOLD or ACTIVE;
`ESTOP_LATCHED` rejects and can only leave through
`OPERATOR_RESET_AND_RETIRE_GENERATION`. It preserves those empty/current and
retained command and operation commitments exactly. Descriptor replacement
cannot strand a command, reset ESTOP, or reinterpret an old-binding command as
current under the successor.

One `InstalledBodySessionControlStateSelector` compare-and-swap installs the
successor descriptor binding, journal head, declaration ledger, and plant-
authority head in one successor composite head. The journal successor advances
the global sequence and makes the descriptor-rebind record the last global
record. The authority successor enters HOLD with no live lease, and the
declaration successor retires every declaration that the record does not prove
compatible with the successor descriptor. No command admission or ACTIVE
transition can use the successor descriptor until later receipted authority and
declaration transitions establish those rights under that exact binding. A
partial install, an undeclared preservation, a widened declaration, a retained
lease, a changed security binding, or a sibling successor fails closed.

After the in-transaction comparison wins, the same durable bundle materializes a
distinct `BodySessionDescriptorRebindJournalCommitReceipt`. That receipt binds the operation,
descriptor-rebind-record digest, prior and installed journal-head digests,
prior and installed declaration-ledger and authority-head digests, prior and
installed `BodySessionControlStateHead` digests, the generic
`BodySessionControlStateCommitReceipt`, and selector version. The generic and
specialized receipts cannot authorize any state beyond the installed successor
that they identify.

A planned same-generation security rotation uses one canonical non-command
`SecurityRebindJournalRecord`. It binds the stable body/plant/session/generation
scope; exact old and prepared-successor security authority domains, semantic
state digests, security epochs, and revocation epochs; old and successor
descriptor revisions and negotiation transcripts; the idempotency operation;
the ADR-009 `SecurityStateTransitionAuthorization`; current body-clock
incarnation and event time; the exact prior journal head and prior global record;
and content-addressed commitments to retirement of every old-state declaration,
grant, lease, and admission surface. The planned form is valid only after old-
state admission closes, the active-command map is empty, and every nonterminal
ingress operation—including an Active attempt—is terminal and retained. It
preserves the empty current-operation map plus retained command/operation
commitments and contains neither its own digest nor an installed head, selector,
signature, or receipt.

An emergency-revocation form can preserve old-state active tips only as fenced
historical obligations. From an ACTIVE or other non-ESTOP predecessor, the body
enters or remains in HOLD. From `ESTOP_LATCHED`, it preserves the latch. From
`ESTOP_OUTCOME_UNKNOWN`, it preserves that exact state, the accepted-transfer
fence and every unresolved arbiter operation/query/inspection obligation with
typed lease absence. An already `RETIRED_DRAIN_ONLY` control root remains
drain-only and cannot reopen HOLD; a TERMINAL root rejects the event. Every
nonterminal branch admits no new command and closes each old-state tip under the
newly installed security state. A `received` tip can
only become `rejected`; an `admitted` tip can only become the exact justified
non-success terminal state unless definitive arbiter evidence proves application
accepted before the rebind fence. That pre-cut fact can be recorded later as
`applied`; no actuation can begin after the fence.
Every unresolved ingress/side-effect operation, including an Active attempt and
every confirmed-or-unknown ESTOP arbiter obligation, is
also carried as a fenced historical obligation and recovered in the
non-actuating state. Normal admission remains blocked until every fenced command
tip, fenced ingress operation and required arbiter reconciliation is terminal
and retained. None can
complete as newly admitted or begin application after the rebind.

The planned record is consumed only by
`APPLY_PLANNED_BODY_SECURITY_REBIND`; the emergency record is consumed only by
`APPLY_EMERGENCY_BODY_SECURITY_REBIND`. Their closed discriminants and required/
forbidden fields are disjoint. An inferred mode, a planned record with pending
work, an emergency record that omits a reachable tuple, or a generic legacy
`APPLY_BODY_SECURITY_REBIND` transition rejects.

One durable `InstalledBodySessionControlStateSelector` compare-and-swap installs
one successor composite head that binds the successor descriptor, security
binding, and subordinate journal head together. A separate
`SecurityRebindJournalCommitReceipt` binds the operation, rebind-record digest,
prior and installed journal-head digests, prior and installed
`BodySessionControlStateHead` digests, the generic
`BodySessionControlStateCommitReceipt`, and selector version. The subordinate
successor journal head increments global sequence,
commits the rebind as its last global record, and makes the new transcript and
security state current. A partial install, replay, sibling successor, invalid
active-tip transition, or current-selector mismatch fails closed. If the exact
installed prior head, authorization, or atomic continuation cannot be proved,
the body keeps admission closed. It can retire only an exact non-ESTOP
predecessor; an ESTOP or indeterminate predecessor blocks successor-generation
creation until authenticated operator reset.

Historical command records continue to carry the transcript and security state
that was installed when each append committed. Current-head ancestry, including
each required rebind edge, authenticates their place in the session-global
journal. A retired context can support historical query interpretation only. It
cannot authorize a new append, replay, lease, stream, grant, or application.
Compaction retains the transition ancestry needed by every retained command
chain. A later signature under a replacement key cannot backfill a missing
predecessor, append, or rebind.

Separate body-boundary application evidence binds the exact successful
body-journal append-record digest. The canonical append record contains the exact
admitted-record digest, a strictly later body journal event sequence, and exact
command/frame/content identity, boundary, body clock incarnation, authority
receipt, installed `BodyCommandApplicationAttempt`, definitive
`BodyActuationArbiter` acceptance evidence, and one `BodyAppliedValueRef`. The reference binds a separately
persisted body-owned frame digest and content reference, declared stream
position, schema, and body semantic contract. The value frame contains neither
the disposition-record digest nor its later evidence receipt. The append record
contains neither its own record digest nor a later evidence receipt. The body
persists the referenced value object before or atomically with the append; a
digest for unavailable bytes is not value evidence. After the in-transaction
comparison wins, the same durable bundle materializes
`BodyBoundaryApplicationEvidence` over
the record digest and the append's prior and installed
`DispositionJournalHead` digests, prior and installed
`BodySessionControlStateHead` digests, both post-CAS commit receipts, installed
attempt, and exact arbiter acceptance/fence-order evidence. Capture
verifies the referenced value bytes
and frame or, for a projected delivery, the ADR-004
`TrustedProjectionRecord` followed by this receiver's separately created
`TrustedProjectionProvenance`, plus the body authority receipt and proof that the
installed event head is an ancestor or retained member of the separately
authenticated current head. A projected value remains labeled with its exact
transform; it cannot be presented as the unavailable original. After
compaction, the current retained-chain commitment carries an exact membership
proof for that event. A losing sibling append, caller-selected historical head,
stale compaction root, or orphaned content digest is not application evidence.
Receiver arrival time or temporal proximity cannot establish the causal edge.
`BodyBoundaryApplicationEvidence` contains no receiver-local projection
provenance or future admission receipt.

For the `applied` state, the disposition is the canonical successful append
record and `BodyBoundaryApplicationEvidence` is the post-CAS receipt for that
same record and head transition. They use the same body event sequence and record
digest without a hash cycle. The exact referenced body-owned value object exists
at that boundary append. An `applied` disposition without its successful
append/evidence receipt and either the referenced value object or exact trusted
projection provenance is not application proof.
The body evidence names only the body-owned frame, schema, semantic field or
contract, and content reference. It does not name or authenticate a downstream
consumer axis contract. A consumer maps that body field through its
independently authenticated semantic segment. Raw value bytes travel only on
the separately declared, scoped, privacy-projected body stream; the disposition
does not expose them by default.

For one exact plant-session generation, canonical
`BodySessionControlStateHead` is the body's sole composite currentness root for
the current descriptor revision, negotiation transcript, security binding,
plant authority/lifecycle, action-command declaration, disposition journal and
the imported physical-authority state of its one actuation domain.
It directly binds the exact ADR-001 `AuthorityRealmKey`, plant
`source_session_kind`, logical session ID and generation as one canonical
consumer foreign key. It also binds the stable body principal,
plant-profile digest, a never-reused control
incarnation, strictly increasing control-state version, closed `CONTROL_ROOT`
`INSTALLED_CHAIN | RETIRED_DRAIN_ONLY | TERMINAL`, those three current
bindings, exact subordinate `PlantAuthorityStateHead`, action-command
`DeclarationLedgerHead`, and `DispositionJournalHead` digests, the exact
`ActuationAuthorityDomainKey` and complete `BodyActuationArbiterMirror`, and prior
composite head. The mirror binds its matching global domain owner state and
selector version. The head also binds the exact currently imported
`SecurityAuthorityStateHead` together with that imported authority head's
selector version and commit receipt. It excludes its own digest/receipt, every
successor/selector digest, and every post-CAS specialized receipt.
Every body-control successor, selector, fact and generic or specialized receipt
directly repeats that exact realm/full-source identity. A different realm or
source-session kind with all other bytes equal rejects before selector lookup.
`InstalledBodySessionControlStateSelector` is its only currentness selector.
Every authority acquire/renew/transfer/release/revoke/expiry, HOLD/ESTOP
lifecycle change, action-command declaration/retirement, disposition,
ingress-attempt, side-effect, clock-bridge, retention, descriptor/security
rebind, and terminalization transition compares and swaps this same selector.
The three body-owned subordinate heads have no independently effective selector
in this body-session scope. A mirrored arbiter head is different: physical
currentness remains exclusively under its jurisdiction-global
`InstalledActuationAuthorityDomainSelector`; the body mirror cannot replace,
fork or recreate that selector.

Every composite compare-and-swap also conditionally verifies, in the same
authority-transaction-domain commit, that the referenced
`InstalledSecurityAuthorityStateSelector` version remains installed. Every
actuation or authority-widening transition verifies the exact global domain
selector, owner generation and mirror version. These are external trust and
physical-authority fences, not additional body-session currentness roots. A plant
body can admit commands only when every applicable compare condition binds the
same `AuthorityTransactionDomainKey` and its qualification covers the complete
transaction. Checking a remote or independently changing parent, security or
actuation-domain selector before or after the body compare-and-swap is
insufficient. A database brand, nominal serializable mode or successful happy-
path test is not the qualification; the provider must prove the exact multi-key
atomic compare, crash visibility, recovery and bound semantics it uses.

Every authority acquisition/renewal/successor-grant/reconnect commit, gate
activation, freshness-grant issue, normal command admission and Active
application also binds the exact current ADR-001
`LogicalSessionGenerationGenesisConfirmationReceipt` and conditionally verifies
that the installed lineage selector still selects this exact generation in
`GENERATION_LIVE`. Body/domain genesis and the one prepared-phase owned-domain
reconciliation remain non-authorizing. If
parent retirement orders first, every widening or application CAS loses.
If the implementation cannot provide that transaction, plant command admission
remains closed; a planned stop-before-change procedure cannot qualify the normal
open-admission race.

This rule orders against the security-authority state installed at this
enforcement boundary. It does not claim instantaneous CA, revocation-feed, or
fleet-wide propagation. Live mTLS revocation/rotation evidence and measured
propagation bounds remain separate pre-release gates. Once the local security
authority selector advances, every pending old-state body compare-and-swap loses.

The canonical `DispositionJournalHead` remains global to all of that body's
commands and descriptor/security rebinds. It binds the stable scope, journal
incarnation/state version, global append sequence, current descriptor revision
and digest, negotiation transcript and security binding, current body-clock incarnation,
last-global-record digest and closed kind (or exact `EMPTY_GENESIS` state),
prior-journal-head digest, bounded active-command tip map, retained-chain
set/compaction root, bounded application-attempt map, the historical actuation-
gate epoch/fence projection, bounded current ingress-
attempt/side-effect operation map,
fenced authority-cut partitions, retirement physical-quiescence evidence,
retained terminal operation commitments/tombstone root, and retained
security-transition ancestry. It excludes every composite-head digest, its own
digest/receipt, and every successor/selector digest. Every append derives the new
last-record fields and applicable command/ingress-operation map transition from
its canonical record; retention-only transitions preserve them. Every command
record and value reference matches the stable scope and the
transcript/security binding installed at its append. Every clock bridge matches
the then-current binding. Only a valid `BodySessionDescriptorRebindJournalRecord`
or `SecurityRebindJournalRecord` can change the journal's current descriptor or
transcript. Only a valid `SecurityRebindJournalRecord` can change its security
binding.
The journal's actuation projection is evidence about the gate order observed by
those records. At each append its domain key and gate fields must equal the
current `BodyActuationArbiterMirror`; it never owns a gate, domain or invocation
right.

Plant-session-generation creation atomically allocates one-use body-child marker
and intended never-used control, authority, action-command-declaration and
journal incarnations; it does not create a body selector or head. Before body
genesis, the exact actuation domain is reserved and its arbiter state is created
through `BODY_ACTUATION_ARBITER_STATE_GENESIS_FROM_DOMAIN_RESERVATION` as
specified above.

Receipt-free `BodySessionControlGenesisFact` binds the exact ADR-001 generation-
creation receipt and child marker, typed body-selector absence plus never-used
proof, intended incarnations, current pending parent, reserved jurisdiction/
arbiter, current local-security head and the prior receipts below. It excludes
the common CAS condition, every candidate and current/future receipt. Exact
`BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION` is ADR-001
`INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS` under
`CANDIDATE_PARTICIPANT_ADMISSION`. Its one authority-domain transaction compares
and advances the domain state/reserve, pending parent lineage, exact jurisdiction/
arbiter and local-security participants; changes the exact body-child marker from
`ALLOCATED` to `CONSUMED` in that pending parent lineage; installs the fresh body selector/head
and participant entry; and installs the sequence-0 `EMPTY_GENESIS` journal,
empty command-declaration ledger, version-1 HOLD/no-lease plant-authority head
and reserved/FENCED `BodyActuationArbiterMirror` inside the version-1 composite
head. It consumes `ActuationAuthorityDomainReservationReceipt` and the event-
complete arbiter-genesis receipt set. The subordinate genesis kinds are
`PLANT_AUTHORITY_GENESIS_FROM_BODY_SESSION_CREATION` and
`COMMAND_DECLARATION_GENESIS_FROM_BODY_SESSION_CREATION`.

The body and domain-state candidates bind the fact, participant-admission
commitment and common condition; the admission commitment binds the intended
semantic projection but excludes candidate digests. The winning
`AuthorityTransactionCommitReceipt` precedes
`BodySessionControlStateCommitReceipt`, native body-genesis and participant-
admission receipts. `BodySessionControlStateCommitReceipt` binds the parent
creation operation, installed composite head/selector and common transaction
receipt. The authority, declaration and journal specialized receipts plus
`BodyActuationArbiterMirrorCommitReceipt` additionally bind their empty/genesis
heads, exact domain key and body commit receipt. A merely signed empty
subordinate or composite head, missing selector after creation, wrong domain,
restart reset, sibling genesis or reused incarnation is not current and retires
the generation if exact state cannot be recovered. The domain-confirmation then
body-reconciliation handshake above must install the owned/FENCED mirror
successor before ADR-001 can mark the generation live.

For every later transition, the body first constructs the immutable fact or
record and each affected subordinate successor from its exact prior subordinate
head. Unaffected subordinate heads are preserved byte-for-byte. It then
constructs one composite successor that binds all three subordinate heads, the
complete arbiter mirror and the applicable current descriptor/transcript/
security values. One ADR-001 authority-domain transaction conditionally mutates
`InstalledBodySessionControlStateSelector` and advances the domain selector plus
every other applicable participant; there is no independently committing body
CAS. A post-CAS `BodySessionControlStateCommitReceipt` binds the scope, prior and
installed composite heads, selector version, transition kind and common
`AuthorityTransactionCommitReceipt`.
Each affected subordinate emits its specialized commit receipt over that generic
receipt and its own prior/installed heads. The composite head binds no receipt.
Here and throughout this ADR, “post-CAS” names content-dependency order after the
in-transaction comparison wins. The selector, installed heads, generic receipt,
all required specialized receipts/currentness evidence and required sidecars
persist as one crash-complete durable bundle and become visible only after the
full bundle is durable. It never means a later crash-visible transaction.

A normal command admission or application-start transition validates the exact
installed authority/lifecycle, live command declaration, open actuation gate and
fresh deadline set in the prior composite and preserves those subordinate heads
in its successor. A reserved fail-safe completion instead consumes its one-use
captured pre-cut snapshot; a fenced post-cut closure consumes the installed
admission/attempt/cut evidence and cannot create a new actuation. The fail-safe
reservation makes the exact branch-specific non-widening authority,
lifecycle/latch, declaration, gate and complete command-partition change in one
CAS. Therefore an authority, lifecycle, declaration, gate, descriptor or
security transition that orders first makes a normal command CAS lose.
A valid historical subordinate or composite head, same-body wrong-session/
profile head, mismatched subordinate binding, caller-selected command tip, or
sibling branch cannot become current.
Compaction preserves exact membership/ancestry evidence for every retained
application event and terminal command chain that remains admissible to query;
it cannot make a losing or evicted sibling appear committed.
On rollback, ambiguity, fork, or missing installed-head evidence, disposition
append/query fails closed and body command admission follows its separate
profile-defined HOLD policy; it never fabricates a terminal answer.

The body retains one deterministic terminal answer per exact command identity.
An exact idempotent query binds the installed body-session-control head and its
subordinate journal head, then returns the complete authenticated chain needed to
interpret that answer. A conflicting frame or content digest under the same
identity rejects.

## Low-overhead command reconciliation

The selected body admission order differs by restrictive mode. ESTOP alone can
select its early idempotent local latch after complete authenticated current-
context and grant checks. HOLD follows ordinary stream monotonicity and live-
holder lease checks before it can request the installed HOLD action.

Only exact Active, HOLD, and ESTOP modes can authorize remote command work.
`Init`, absent, default, unknown, and ambiguous modes reject as commands. The
body can separately select a profile-defined HOLD action from current local
policy and body state. Rejected bytes and their claimed mode do not select or
parameterize that action. The local action is not an admitted remote HOLD and
cannot produce `HOLD_EFFECTIVE` for the rejected command.

HOLD and ESTOP structurally forbid publisher values, source coordinates,
predictive horizons, and caller-selected local actions. The installed plant
profile supplies each restrictive action. A command rejection and a body-local
restrictive result remain separate records.

The body binds each new command position and exact frame digest before lower
semantic checks. It never replaces that digest. A qualified conflicting ESTOP
can use only the preallocated generation-wide restrictive-conflict attribution.
The attribution cannot create another command chain or overwrite the primary
position result.

One position represents one setpoint and one application attempt. A source-bound
Active command uses the exact retained and pinned source publication. No
timestamp, bare source position, digest without values, or latest-value fallback
can substitute.

Freshness comes from the unchanged exclusive deadline in the body-issued grant.
Receiver arrival does not start or refresh a TTL. Grant installation reserves
the complete no-reuse, source-pin, restrictive, and disposition capacity for its
position range.

Immediately before a new ESTOP reservation, the body atomically rechecks the
security state, manifest permission, grant or escalation-snapshot currentness,
unchanged deadline, and installed profile action. Boundary acceptance repeats
the applicable currentness and deadline checks. A cut that wins either order
installs no new remote effect.

`QueryCommandDisposition` uses one exact command coordinate. It binds the direct
realm, plant body, complete session foreign key, authenticated publisher,
declaration, publisher incarnation, stream epoch, position, and expected command
digest. The result is a closed union:

- `RETAINED_DISPOSITION` carries the complete retained chain and current
  membership evidence for that coordinate.
- `RETIRED_DISPOSITION_COMMITMENT` carries the coordinate, terminal label, and
  no-reuse commitment only.
- `QUERY_FAILURE` carries `EVIDENCE_UNAVAILABLE` and no disposition claim.

Each branch compares the same exact query coordinate with every carried artifact.
The canonical result projection omits its digest, authentication envelope,
signature, and receipt. A later authenticated envelope binds the recomputed
digest and complete query request. This order prevents a hash cycle and command
substitution.

A retired commitment cannot prove `APPLIED`, `HOLD_EFFECTIVE`, or
`STOP_LATCHED` as an application or effect claim. Those interpretations require
the retained complete chain and exact body-local association evidence. No branch
proves physical achievement or certification.

B03 selects positive finite journal capacities and implementation names. Each
selection must reserve the complete terminal path, fit aggregate bytes, reject
overflow, and preserve no-reuse for the declared lifetime. B03 cannot change the
union, command identity, admission order, or claim boundary.

The following non-wire projection closes the result branches for B01 challenge
tests. It does not allocate a future wire shape.

```json
{"query_coordinate_bound":true,"result_projection_omits_authentication":true,"retained_requires_complete_chain":true,"retired_proves_effect":false,"early_effect_mode":"ESTOP_ONLY","estop_reservation_rechecks_currentness":true,"effect_boundary_rechecks_currentness":true,"hold_admission_precedes_effect":true,"rejected_candidate_cannot_select_local_hold":true,"post_effect_admission_mode":"ESTOP_ONLY","branches":["QUERY_FAILURE","RETAINED_DISPOSITION","RETIRED_DISPOSITION_COMMITMENT"]}
```

## Rejected alternatives

Rejected: treating publish/Gate acknowledgement as execution; non-body
disposition issuance; free-text success; strengthening terminal ambiguity;
defining `applied` as physical achievement/safety; or accepting a historical
snapshot/caller-selected tip as current.

## Illustrative wire example

```json
{"kind":"command_disposition","session_id":"plant-alpha","state":"received"}
```

This incomplete excerpt grants no state.

## Invalid or hostile example

```json
{"kind":"command_disposition","state":"physically_safe","terminal":true}
```

Unknown states and non-body issuers reject.

## Actors and state transitions

Active uses `NONE -> RECEIVED -> ADMITTED -> APPLIED`. Other paths are
`RECEIVED -> REJECTED`, `ADMITTED -> SUPERSEDED`,
`ADMITTED -> EXPIRED`, `ADMITTED -> FAILED`, or
`ADMITTED -> UNKNOWN_AFTER_BOUNDARY`; restrictive association alone reaches
`HOLD_EFFECTIVE` or `STOP_LATCHED`. Terminal states do not transition. Sequence
increases and each non-first record authenticates its predecessor.

Fresh context appends `CommandIngressAttemptRecord`; fail-safe selection can add
one `BodyFailSafeSideEffectRecord`. Their resolution records are evidence, not
success. Replay/wrong context appends nothing.

## Bounds and resource behavior

All grants, slots, records, attempts, effects, tombstones, bytes, transitions,
queries and work are finite. Safety/ESTOP reserves are not borrowed or blocked
by observers. Each transaction fits its complete qualified bound; cap-plus-one
cannot omit participants. Compaction preserves predecessor/no-reuse evidence.
Before exhaustion could erase it, the body irreversibly retires.

## Threat and hazard analysis

This blocks false execution, laundering, retry conflict and silent ambiguity;
loss remains uncertainty, not safety. A qualified ESTOP can spend one fresh
granted latch position before later stream and lease checks, so audit and
rate-limit that bounded denial surface. Remote HOLD has no equivalent pre-
admission action. Replay, equal or lower variants, and wrong or expired context
cannot invoke again.

## Formal properties

- Only the authenticated current body issues a disposition. One exact identity
  has one terminal state; cross-`AuthorityRealmKey` replay/merge rejects.
  `unknown_after_boundary` never strengthens. `hold_effective`,
  `stop_latched` and `applied` are distinct evidence claims, never physical or
  safety certification.
- Facility genesis proves each path and `U/P/H/E/A` incidence: each slot
  has nonempty sets, ledger keys equal P, shared identities conflict and
  components cover universes. Reciprocal enrollment and exact budgets
  precede use; full/local isolation origins stay distinct. Only independently
  anchored commits are consumable; terminalization shares the anchor CAS and
  exact/unknown root closure covers its component. High-water survives
  clone; `UNASSIGNED_PHYSICALLY_ISOLATED` is not safety/reuse authority.
- Fail-safe effect needs exact context and strict-before
  `FAIL_SAFE_EFFECT_NOT_AFTER`; attempt/fence/mirror precede its one-use token.
  Remote HOLD also needs ordinary admission and an exact admitted predecessor.
  Early ESTOP needs the complete pre-replay gate. Both need the complete frontier,
  including `HOLD_OUTCOME_UNKNOWN`, plus distinct ESTOP token and qualified
  dominance or override. Missing evidence disables both. Replay cannot repeat.
- Each authenticated `received` chain takes one rejected/admitted edge.
  `CANDIDATE_NOT_EVALUATED` is not authority; successors retain exact content,
  predecessor and admitted evidence.
- Active application first installs one `BodyCommandApplicationAttempt` and
  arbiter operation under immutable attempt/operation/idempotency keys. In one
  qualified fault domain, acceptance installs value and a non-extended watchdog;
  otherwise Active is disabled. Replacement records
  `REPLACED_BY_NEWER_ACCEPTANCE`; only the current watchdog can expire. No-effect
  maps one cause to superseded/expired/failed; ambiguity retains same-key query
  and can end only as non-strengthening unknown.
- Every cut installs a fresh FENCED epoch, complete output/watchdog partition and
  total restrictive selection. START consumes a token, JOIN reuses one, and
  equal/lower/incomparable branches invoke nothing. Complete frontiers/results
  remain distinct; one receipt-set root reconciles once. Clock ambiguity cannot
  retire its watchdog. Physical-quiescence retirement preserves replaced/clock-
  retired causes and terminalizes only the exact current lineage and
  per-incarnation reserves.
- The application-attempt consumption index is absent→reserved→consumed or
  no-acceptance tombstone; ambiguity never fabricates either terminal result.
  Selection/cut compaction requires no live reference and retains key/digest/
  no-reuse. Emergency/overflow reserve and seal use the never-reused arbiter
  coordinate; terminal same-key resurrection is impossible.
- ESTOP ingress follows attempt-pending→side-effect-reserved→optional
  outcome-pending→side-effect-resolved. A rejection then terminalizes the
  ingress entry. An admitted command instead enters pending association before
  it terminalizes.
  HOLD atomically installs its admitted predecessor with the reservation and
  moves from outcome resolution directly to admitted-pending-association or a
  no-effect terminal state. Failed HOLD admission installs no arbiter, fence,
  token, or effect state. ESTOP uses its complete pre-replay gate. MARK changes
  ingress/effect and ESTOP-pending entries together. Only
  `ASSOCIATE_ADMITTED_RESTRICTIVE_COMMAND_WITH_EFFECT` appends
  hold-effective/stop-latched/unknown and terminalizes the association path.
- A rejected ESTOP can retain bounded attempt/effect evidence but no admitted or
  association success. Rejected remote HOLD has no effect record. Active uses no
  effect slot. Exact replay appends or invokes nothing. Same-slot equal or lower
  changed content does nothing, and HOLD-to-ESTOP has one upgrade. Wrong, expired,
  malformed, oversized or unauthenticated context has no unauthorized effect.
- Per-command predecessors increase globally but can interleave. The installed
  head alone derives active/retained maps and complete cut partitions.
  `BodySessionControlStateHead` is the sole composite body CAS root; subordinate
  heads and exact parent/security/domain participants advance with its receipts
  under one `AuthorityTransactionDomainKey`. Separate reads, sibling heads and
  wrong scope fail closed.
- Sequence-zero `EMPTY_GENESIS` exists only through
  `BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION` from typed absence; no
  `UNINITIALIZED` selector exists. Rebind requires the exact descriptor/security
  journal record and preserves ESTOP, transfer, drain and ambiguity obligations.
  `BodyClockRestartBridge` plus
  `BodyClockRestartBridgeCommitReceipt` replaces cross-clock comparison without
  extension; `FROM_EMPTY_HEAD` is genesis-only.
- Hostile models cover facility incidence/anchors, all nine slot states, cuts,
  frontiers, acceptance/watchdog races, replay, receipt roots, retention,
  exhaustion and partial retirement. They inject orphan/empty incidence,
  missing edges/partitions, append after terminal, stale roots, unanchored
  exposure, ambiguous clock retirement, wrong quiescence watchdog, false
  consumed attempt, live-reference compaction, same-key reserve resurrection,
  absent-seal retirement, missing MARK edges, cut-as-expired, HOLD recovery that
  skips CONSUMED, retired-index live references, the removed reverse-order
  ingress state, association bypass/split CAS, stale timer/token, forged ESTOP
  override, unknown/default and cap-plus-one. All reject or return the single
  installed bundle. Observer failure cannot block body journal progress.

## Migration

Commanders query/reconcile instead of treating transport success as execution.
Crebain needs the body journal before a role receipt; legacy Gate receipts remain
Gate-only evidence.

## Operational recovery

After reply loss, query exact identity/context. Missing terminal proof returns
unknown/retention-expired, never fabricated `applied`; replay precedes conflict.

## Compatibility and rollback

This needs the rebaselined core and adapters. Rollback disables native command;
it cannot retain execution claims without dispositions.

## Open questions

<a id="ncp-b01-selector-allocation-adr-007-v1"></a>

The disposition-query semantic question is closed by the low-overhead command
reconciliation. Exact implementation names and bounded journal capacities remain
B03 allocation inputs. Retention loss stays non-authorizing and cannot fabricate
a terminal outcome.

B03 selects 1 through 32 canonical implementation identities. Each identity
matches `[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?` and can name only a journal,
query, retention,
or recovery boundary defined by this ADR. Journal capacity is 1 through
1,048,576 entries. Aggregate capacity is 1 through 1,073,741,824 bytes.
Retention is 1 through 86,400,000,000,000 nanoseconds. Each selection must fit
the complete retained chain, source pin, conflict attribution, retired
commitment, and terminal no-reuse state.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Protocol semantics separates receipt, admission, application, and effect.
2. Security permits only the body to issue dispositions.
3. Safety keeps boundary claims limited.
4. Distributed lifecycle closes terminal and ambiguous outcomes.
5. Resource capacity is finite and reserved.
6. Interoperability migration reconciles outcomes.
7. Science claims no effectiveness.
8. Operations covers query, retention, and recovery.
9. Verification tests crash and retry behavior.
10. Lifecycle governance leaves state, boundary, and retention with the body.

## Ratification record

The non-normative registry derives review status; these invariants stay fixed.
