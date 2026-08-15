# ADR-006 — Use body-issued authority and receiver-local time

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: safety reviewer, distributed-systems reviewer, Haldir
  owner, Crebain owner

## Context

A publisher's ability to reach an action route does not grant plant authority.
Direct Engram and Haldir-gated modes need one serialized commander term, bounded
leases, deterministic handover, restart fencing, and unambiguous time semantics.
The current primitives include opaque session generation, strictly increasing
lease term, random lease ID, bounded UTC interval, receiver-local monotonic
deadline, command stream epoch/sequence, HOLD, and ESTOP.

Calling an additional value “plant authority epoch” would overlap these fences.
Session and stream UUIDs are equality-only identifiers, not ordered counters.

## Proposed decision

Crebain, as the enrolled body for a plant session, is the sole issuer and
enforcer of plant action authority. It serializes:

- `AcquirePlantAuthority`;
- `RenewPlantAuthority`;
- `TransferPlantAuthority`;
- `ReleasePlantAuthority`;
- `RevokePlantAuthority`; and
- `QueryPlantAuthority`.

The exact command-admission fence is:

```text
exact neutral AuthorityRealmKey
+ source session kind
+ plant identity
+ logical session ID
+ exact SessionRef.generation
+ exact current lease term and lease ID
+ exact current holder principal/entity
+ exact declared command stream epoch
+ strictly increasing command sequence
+ exact operation/idempotency context where applicable
```

Each equality field must equal current body state; term and sequence additionally
obey their monotonic rules. The tuple is not compared lexicographically.

For one plant-session generation, authority is subordinate state under the
ADR-007 `BodySessionControlStateHead`. Canonical `PlantAuthorityStateHead` binds
the exact neutral ADR-001 `AuthorityRealmKey`, source session kind and
body/plant/profile/session/generation scope, never-reused authority
incarnation, strictly increasing authority-state version and highest used term,
closed plant lifecycle/latch state, exact current lease or typed absence,
pending authority operation, retained lease/term tombstones, receiver-local
clock incarnation/deadline state, and prior authority head. It excludes every
composite head, its own digest/receipt, and every successor/selector digest.
There is no independently effective plant-authority selector.

This state is a product, not one flat phase label. The parent
`BodySessionControlStateHead` owns closed `CONTROL_ROOT` with only
`INSTALLED_CHAIN`, `RETIRED_DRAIN_ONLY`, and `TERMINAL`
branches. `PlantAuthorityStateHead` does not bind that parent root or any sibling
head. Its subordinate
`LIFECYCLE_LATCH` axis is
`HOLD | ACTIVE | ESTOP_LATCHED | ESTOP_OUTCOME_UNKNOWN | RETIRED`.
`LEASE_CURRENTNESS` is `ABSENT | LIVE | RETIRED_TOMBSTONE`; the `LIVE` branch
binds the exact lease and receipt-free currentness/deadline commitment. The
installed-currentness receipt is a co-committed sidecar indexed to the installed
head and selector; the head does not content-bind that later receipt.
`PENDING_AUTHORITY_OPERATION` is
`NONE | ACQUIRING | RENEWING | TRANSFER_REQUESTED | HOLD_QUIESCING |
PREDECESSOR_RETIRED | GRANTING_SUCCESSOR | RECONNECTING`. Every transition names
the predecessor and successor on each affected axis and preserves every other
axis byte-for-byte. A label from one axis cannot stand in for the complete
state.

Every realm-scoped authority request, lease, transition fact, command fence,
currentness/evaluation commitment, journal record, handover/reconnect object and
receipt in this ADR directly binds the exact neutral `AuthorityRealmKey` and full
source-kind/logical-session/generation identity. All joins require equality. A
literal route or transitive descriptor/receipt ancestor cannot replace the realm
field; missing/default/mismatched realm rejects before authority allocation.

Only invariant-valid tuples are reachable. `ACTIVE` requires a `LIVE` lease and
pending operation `NONE`, `RENEWING`, or `TRANSFER_REQUESTED`, plus exact
`OWNED_BY_GENERATION_ACTIVE` ownership and an OPEN arbiter mirror for the
generation's one ADR-007 `ActuationAuthorityDomainKey`. `HOLD` with a
`LIVE` predecessor lease is legal only in `HOLD_QUIESCING`; that lease is fenced
from admission. `PREDECESSOR_RETIRED` and `GRANTING_SUCCESSOR` require HOLD and
lease absence. `ACQUIRING` requires HOLD and lease absence. `RECONNECTING`
requires HOLD and lease absence and carries its predecessor lease only as
non-authorizing recovery content. `ESTOP_LATCHED` and
`ESTOP_OUTCOME_UNKNOWN` have no live lease. Either can retain an exact accepted-
transfer phase behind its fence. `ESTOP_LATCHED` asserts a confirmed body-
boundary latch. `ESTOP_OUTCOME_UNKNOWN` asserts only that the latch operation can
have taken effect; it never claims a latch or physical safety. Both require a
specialized authenticated local retirement path.
For retirement and fault composition, the ESTOP-restrictive class also includes
any reserved, invoked, ambiguous or otherwise possibly effective ESTOP operation
in the ADR-007 mirror, even while the lifecycle label is HOLD and the ESTOP
floor has not advanced. A restrictive transition must resolve that operation as
definitive no effect before it can use a generic non-ESTOP retirement edge. If
arbiter state is lost first, the body records `ESTOP_OUTCOME_UNKNOWN`, remains in
`INSTALLED_CHAIN`, and uses the unknown-ESTOP inspection path. A pending label can
never bypass that path by entering drain first.
`RETIRED` lifecycle and `RETIRED_TOMBSTONE` lease states are legal only when the
parent control root is `RETIRED_DRAIN_ONLY` or `TERMINAL`, with pending authority
operation `NONE`; unlike `ABSENT`, they can never permit a future acquisition.
The parent drain-only head binds the terminal authority subhead plus exact
declaration and journal subheads that contain the complete typed application,
ingress, fail-safe, transfer and retention obligation inventories. `TERMINAL`
requires every such obligation terminal and the exact physical-quiescence
evidence required by the plant profile. Every other Cartesian combination
rejects. This parent-to-subhead DAG never makes the authority subhead bind a
sibling or parent digest.

Command admission requires the composite `INSTALLED_CHAIN`, lifecycle `ACTIVE`,
lease `LIVE` with exact installation evidence, a currently selected and receipted
composite head that contains that exact authority head, fresh unexpired deadline
evaluations, pending operation `NONE`, and the exact live command declaration.
The same transaction conditionally verifies the ADR-001
`InstalledLogicalSessionGenerationLineageSelector` still selects this exact
generation in `GENERATION_LIVE`. The parent, body, ADR-007 jurisdiction and local
ADR-009 security selectors bind one exact qualified
`AuthorityTransactionDomainKey`; a separately sampled selector or mismatched key
rejects. Every authority acquisition/renewal/successor-
grant/reconnect commit, gate activation, freshness-grant issue, normal command
admission and Active application binds the exact current
`LogicalSessionGenerationGenesisConfirmationReceipt` and performs that parent-
live comparison in the same authority-widening transaction. A receipt for a
different child set, generation or historical LIVE head rejects. A body
genesis or domain reconciliation under
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS` remains non-authorizing. Parent
retirement ordering first makes every widening/admission CAS lose.
`RENEWING`, `RECONNECTING`, or any
transfer phase grants no interim command admission. A restart-mapped lease is a
fenced continuity candidate inside `RECONNECTING`; it is not `LIVE` and has no
currentness receipt until the continuity transition commits.

Every ADR-006 event that conditionally reads or writes authority state constructs
the ADR-001 `AuthorityTransactionCASCondition`. Its participant set always
contains `AUTHORITY_TRANSACTION_DOMAIN_STATE` and the exact registered body
selector; it additionally contains each applicable parent-lineage, ADR-007
domain/arbiter and local-security selector. The condition proves one common
domain/store incarnation, participant-registry membership, per-role ACL and exact
retirement-reserve delta. Event facts exclude that condition, all candidates and
receipts; candidates bind the fact and condition. The winning
`AuthorityTransactionCommitReceipt` binds the complete read/write set and
installed-state root. Body and event-specific receipts depend on it, and the
final non-authorizing persistence manifest binds the exact complete durable
bundle. Missing membership, a remote/pre-read selector, partial receipt DAG or
reserve under-accounting rejects before mutation. A closed event-specific
participant set may omit an irrelevant selector only when its mutation inventory
proves that the event cannot read, widen, fence or preserve authority from that
selector; domain state is never omitted.

The parent also carries the complete ADR-007 `BodyActuationArbiterMirror`, not a
gate-only copy. It binds the generation's one exact
`PhysicalActuationJurisdictionKey`, registry incarnation,
`ActuationAuthorityDomainKey`, jurisdiction-global domain owner/head and selector version,
installed arbiter head, gate, operation-registry, restrictive-chain, possible-output,
watchdog, retention and complete transition-receipt-set roots plus every pending
semantic reconciliation obligation. Each arbiter transition set enters body
ancestry exactly once through the ADR-007 closed consumer table. A missing,
substituted or partial root keeps authority widening closed. The mirror gate is
FENCED in every HOLD/lease-absent tuple. There is no
durable `HOLD + LIVE + NONE` staging tuple. Before
`COMMIT_PLANT_AUTHORITY_ACQUISITION`, `INSTALL_SUCCESSOR_AUTHORITY_GRANT`, or
`COMPLETE_RECONNECT_WITH_EXACT_CONTINUITY`, the qualified ADR-007 arbiter can
install one OPEN candidate with a never-used epoch, bound to that exact pending
operation and candidate lease/declaration. The parent body event consumes the
activation receipt and atomically installs its complete arbiter mirror,
`ACTIVE + LIVE + NONE`, and the exact current declaration. The arbiter cannot
accept an application before a body attempt binds that installed mirror. If the
parent compare-and-swap loses, the orphan activation is fenced with a later epoch
and cannot authorize the next retry. A completed HOLD cycle cannot activate;
after body-only recovery, one of the three qualified authority branches and a
current declaration is required.

`PLANT_AUTHORITY_GENESIS_FROM_BODY_SESSION_CREATION` is the only empty
authority initialization. It creates version 1 in HOLD with no lease inside the
same one-use body-session-control genesis compare-and-swap. That genesis consumes
the exact ADR-001 `LogicalSessionGenerationCreationReceipt` and plant child-
selector marker for this generation, the exact
`ActuationAuthorityDomainReservationReceipt` and arbiter-genesis receipt set. It
conditionally verifies that the parent remains
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS` and the exact reserved registry head
is still current through the creation receipt's qualified authority transaction
domain,
then mirrors that reserved/FENCED domain; cancellation ordering first makes
genesis lose. A parent read followed by an independently committing body write
does not implement genesis and keeps the child non-authorizing.
`CONFIRM_ACTUATION_AUTHORITY_DOMAIN_GENERATION_GENESIS` then installs only the
owned/FENCED registry successor from that body-genesis receipt.
`RECONCILE_BODY_ACTUATION_DOMAIN_GENERATION_GENESIS` consumes the domain
confirmation receipt, installs the matching owned/FENCED body mirror and emits
the sole reconciliation receipt that permits ADR-001 to mark the generation
live. Its only prepared-parent use binds the exact frozen partial-retirement
partition and can lead only to retirement; it grants no live authority. Every
intermediate state remains HOLD/FENCED. A random child
generation, replayed marker or non-current logical-session lineage cannot
initialize authority. Missing state,
sibling genesis, restart reset, or incarnation reuse after any use retires the
session generation.

Every acquire, renew, transfer, release, revoke, expiry, HOLD, ESTOP latch/reset,
and authority recovery first constructs an immutable
`PlantAuthorityTransitionFact`. The fact binds the exact operation, prior
authority head, current body time, authorization and closed predecessor/
successor values. When it creates or renews a lease, it also binds the complete
candidate `PlantAuthorityLease` bytes and digest. It contains no successor
authority head, body-session-control head, selector version, commit receipt, or
currentness receipt. The authority successor binds the fact. The body-session
composite successor binds that authority successor and the exact subordinate
action-command declaration and disposition-journal heads. One compare-and-swap
of `InstalledBodySessionControlStateSelector` installs the transition.

After the in-transaction comparison wins,
`PlantAuthorityStateCommitReceipt` binds the fact, prior and installed authority
heads, prior and installed body-session-control heads, selector version, and
generic `BodySessionControlStateCommitReceipt`. When a live lease is installed,
a distinct `PlantAuthorityCurrentnessReceipt` binds the exact lease
bytes/digest, installed authority/composite heads, both commit receipts, body
clock and exclusive local deadline. The selector, heads, generic receipt,
required specialized receipts and currentness sidecar persist in one durable
bundle and become visible only after the full bundle is durable. “After” names
content-dependency order inside that transaction, not a later crash-visible
write. A candidate lease or signed authority head without that matching
installed-currentness receipt grants nothing.
The receipt proves installation and currentness at that commit. It does not
claim that its historical composite head remains selected after journal-only
successors. At later admission, the currently selected composite head and its
generic commit prove membership of the same exact authority head; the
installation receipt proves the lease/head origin; and the fresh deadline
evaluation proves time currentness. No one of those three inputs substitutes for
another.

Every deadline-sensitive body transition also uses the distinct
`BodyAuthorityDeadlineConditionIntent`,
`BodyAuthorityDeadlineConditionIntentSetRoot`,
`BodyAuthorityCommitTimeDeadlineCondition`, and
`BodyAuthorityCommitTimeDeadlineEvaluationSetRoot` family. Its closed purposes
are `AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE` and
`EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE`. Its closed kinds are
`ACQUISITION_COMMIT_NOT_AFTER | RENEWAL_BEGIN_LEASE_NOT_AFTER |
RENEWAL_COMMIT_NOT_AFTER | RENEWAL_CANCEL_PRESERVE_LEASE_NOT_AFTER |
LIVE_LEASE_EXPIRY_NOT_AFTER | RECONNECT_COMMIT_NOT_AFTER |
TRANSFER_BEGIN_LEASE_NOT_AFTER | TRANSFER_HOLD_QUIESCENCE_NOT_AFTER |
SUCCESSOR_GRANT_NOT_AFTER |
COMMAND_ADMISSION_LEASE_NOT_AFTER | COMMAND_ADMISSION_TTL_NOT_AFTER |
COMMAND_APPLICATION_LEASE_NOT_AFTER | COMMAND_APPLICATION_TTL_NOT_AFTER |
FAIL_SAFE_EFFECT_NOT_AFTER`.
These types use a body-authority digest domain and cannot be replaced by the
observer-authorization family in ADR-004.

The fact and candidate successor bind the exact complete intent-set root. After
the in-transaction comparison wins, the generic and specialized commit receipts
and the event receipt bind the exact complete evaluation-set root. The evaluation
uses the ADR-004 integrated transaction-manager proof or independently qualified
completion-bound proof through durable commit. Strict-before authorization
rejects equality; expiry permits equality. A timestamp or currentness receipt
sampled before a stall is insufficient. `PlantAuthorityCurrentnessReceipt`
proves lease installation only. Every later command admission/application,
renewal, preserve-old-lease cancellation, transfer progress and reconnect must
pair it with the fresh commit-bound evaluation set required for that event. A
missing, extra, wrong-family, wrong-purpose or unbound evaluation rejects.

Every installed pending operation has a closed terminal path. Acquisition either
commits one fresh lease or uses `CANCEL_OR_FAIL_PLANT_AUTHORITY_ACQUISITION` to
return to HOLD with lease absence. Renewal either commits the exact same lease
identity with a bounded later deadline, uses
`CANCEL_PLANT_AUTHORITY_RENEWAL_PRESERVE_EXACT_UNEXPIRED_LEASE` before the old
exclusive deadline, or uses `FAIL_OR_EXPIRE_PLANT_AUTHORITY_RENEWAL_TO_HOLD`.
The cancellation branch preserves the complete old lease and currentness
commitment byte-for-byte, but the winning cancellation bundle emits a new
`PlantAuthorityCurrentnessReceipt` bound to its new authority/composite heads,
commits and fresh strict-before cancellation evaluation. An earlier head-bound
receipt never migrates across the head change. The branch cannot extend the
deadline. Equality with the old deadline selects the HOLD branch. After
predecessor retirement, a successor
grant either installs the new higher-term lease or uses
`FAIL_SUCCESSOR_AUTHORITY_GRANT_TO_HOLD`; failure preserves predecessor lease,
term, and declaration tombstones and can never reactivate the predecessor.
`BEGIN_PLANT_AUTHORITY_TRANSFER` first commit-bound proves
`TRANSFER_BEGIN_LEASE_NOT_AFTER`; equality or later time selects ordinary
expiry/HOLD and creates no transfer latch. A winning begin commits exact
no-extension quiescence and successor-grant deadlines. Progress through HOLD quiescence and successor grant
uses the applicable strict-before condition. Equality or later time selects the
typed timeout/failure branch. A quiescence timeout advances the accepted
transfer to non-authorizing retirement drain; a successor-grant timeout uses
`FAIL_SUCCESSOR_AUTHORITY_GRANT_TO_HOLD` and retains the exact failed-transfer
tombstone. Neither branch cancels the accepted transfer or revives the old
holder. Under ESTOP, timeout preserves the latch and transfer tombstone until
operator reset. Clock restart maps every applicable transfer deadline without
extension.
Reply loss queries the installed operation. Ambiguous or unavailable operation
state from a non-ESTOP predecessor retires the session generation instead of
guessing a branch. An `ESTOP_LATCHED` predecessor remains latched and
non-authorizing until the exact operator-reset transition. An
`ESTOP_OUTCOME_UNKNOWN` predecessor remains quarantined and non-authorizing until
the exact local inspection/reset-and-retire transition; it does not become
latched merely because continuity proof is unavailable.

Restrictive transitions cannot be blocked by a pending operation. Expiry,
revocation, emergency security rebind, ESTOP, terminal retirement, and restart
ambiguity enumerate every applicable reachable predecessor tuple. Each binds the
exact predecessor transition fact and operation ID; it cannot clear an unrelated
operation. Acquisition, renewal, and reconnect can terminate into an exact
tombstone. A durably accepted transfer is different: from
`TRANSFER_REQUESTED`, `HOLD_QUIESCING`, `PREDECESSOR_RETIRED`, or
`GRANTING_SUCCESSOR`, a restrictive transition preserves that exact transfer at
the same or a later phase with every predecessor fence intact. A non-ESTOP
branch can instead retire the generation with those fences. A branch in the
ESTOP-restrictive class cannot use generic retirement and preserves the
restrictive lifecycle/pending state and fenced transfer until its specialized
local retirement path. A possible ESTOP must first close as definitive no effect
or become `ESTOP_OUTCOME_UNKNOWN`. It never cancels the transfer or restores predecessor
admission. Descriptor and planned security rebind require pending operation
`NONE` and a `HOLD` or `ACTIVE` predecessor; both reject `ESTOP_LATCHED` and
`ESTOP_OUTCOME_UNKNOWN`.
`LATCH_BODY_ESTOP` is a body-owned reconciliation edge, not a physical-boundary
invocation, RPC shortcut or assertion that a requested latch succeeded. It accepts
an invariant-valid non-retired tuple only after the ADR-007 arbiter has installed
and resolved one exact qualified ESTOP operation. Its compare-and-swap consumes
the matching `BodyActuationRestrictiveActionResultReceipt`, the complete
`BodyActuationArbiterTransitionReceiptSetRoot`, the result-bound boundary and
severity evidence, the installed body reservation/mirror and the current body
selector. The result must report the identified ESTOP latch as
`RESTRICTIVE_ACTION_ACCEPTED`. The edge atomically installs `ESTOP_LATCHED`, lease
absence, retirement of the live action-command declaration, and either a terminal
tombstone for a cancellable operation or the fenced accepted-transfer latch. Raw
device evidence, a storage label, a timeout or a body-owned token is insufficient.

A remotely requested ESTOP reaches the same state effect only through the ESTOP
branch of `COMPLETE_RESERVED_FAIL_SAFE_COMMAND`; it cannot invoke
`LATCH_BODY_ESTOP` directly. An enrolled local interlock or authenticated local
operator must create, mirror, invoke and resolve its own qualified ADR-007
operation before `LATCH_BODY_ESTOP` can reconcile that result. From
`ESTOP_OUTCOME_UNKNOWN`, a qualified idempotent query must resolve the original
operation, or a new one-use local operation must independently prove the same
identified latch through that DAG. Neither route can refine unknown to confirmed
from an assumption or from evidence that is not bound to the consumed operation.

Security rebind is two exact body events, not one mode flag on an ambiguous
transition. `APPLY_PLANNED_BODY_SECURITY_REBIND` accepts only a quiescent
`PENDING_AUTHORITY_OPERATION=NONE` predecessor in HOLD with lease absence or in
ACTIVE with one exact live lease. It requires the ADR-007 planned-rebind guards,
retires any live lease and declaration, and installs HOLD with lease absence and
pending operation `NONE` under the successor security context.

`APPLY_EMERGENCY_BODY_SECURITY_REBIND` accepts every invariant-valid
nonterminal tuple. It never preserves or creates Active authority. It maps
Active to HOLD with lease absence, preserves `ESTOP_LATCHED` and
`ESTOP_OUTCOME_UNKNOWN` exactly, and keeps an existing HOLD fail-closed.
Acquisition, renewal and reconnect operations
become exact non-authorizing fenced/tombstoned recovery obligations. A durably
accepted transfer remains at the same or a later fenced phase, including inside
either ESTOP state. For a non-ESTOP predecessor, the composite root can instead
retire with its predecessor fences in terminal tombstones. That retirement
alternative is forbidden for an `ESTOP_LATCHED` or `ESTOP_OUTCOME_UNKNOWN`
predecessor; emergency rebind must preserve the exact restrictive state and any
fenced accepted-transfer phase. The emergency
event atomically installs the ADR-007
emergency security-rebind record and all authority/declaration/journal effects;
it cannot silently cancel work, reset ESTOP or widen lifecycle state.

Neither ESTOP lifecycle state can reset into `ACTIVE` or HOLD in the same
generation. `OPERATOR_RESET_AND_RETIRE_GENERATION` is an authenticated local-
operator and physical-boundary transition only from `ESTOP_LATCHED` to
`RETIRED_DRAIN_ONLY`. It accepts every invariant-valid confirmed-latch tuple,
including each exact fenced accepted-transfer phase, and binds qualified evidence
that the identified latch was reset at the identified boundary.

`INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE` is the disjoint local path from
`ESTOP_OUTCOME_UNKNOWN`. It requires an authenticated enrolled operator, the
exact plant/profile/session/generation and boundary identity, exhaustion and
recording of every supported idempotent outcome query or resumption path, a
qualified physical inspection/interlock procedure, and evidence that the old
generation is isolated from later actuation and the boundary is in the profile-
approved reset-and-retire condition. It preserves the exact unknown-outcome
tombstone. Its receipt never asserts whether the earlier latch occurred and
proves neither physical safety nor regulatory certification. If any required
query, isolation, inspection, interlock or reset evidence is absent or ambiguous,
the tuple remains `ESTOP_OUTCOME_UNKNOWN`, cannot enter drain-only, and cannot
authorize a successor generation.

Both specialized paths set pending authority state to `NONE`; lifecycle and
lease enter `RETIRED` and `RETIRED_TOMBSTONE`; and the drain head retains the
accepted-transfer operation, predecessor-retirement fence, lease/term/holder
tombstones and exact local evidence for the required no-reuse horizon. Entering
drain-only is not transfer cancellation and does not claim that every in-flight
body-boundary operation succeeded. Neither path is a remote NCP RPC.
`RETIRE_BODY_SESSION_GENERATION` rejects both `ESTOP_LATCHED` and
`ESTOP_OUTCOME_UNKNOWN` and every other member of the ESTOP-restrictive class; it
cannot stand in for either specialized transition.

Every body composite edge from `INSTALLED_CHAIN` to `RETIRED_DRAIN_ONLY`,
regardless of its cause-owning outer event, carries the one subordinate
`ENTER_BODY_SESSION_GENERATION_RETIREMENT_DRAIN` transition and first constructs
receipt-free `BodySessionGenerationRetirementFact`. The fact has one closed
cause:
`EXPLICIT_NON_ESTOP_RETIREMENT |
ACCEPTED_TRANSFER_QUIESCENCE_TIMEOUT |
RESTRICTIVE_AUTHORITY_CUT_WITH_ACCEPTED_TRANSFER |
AUTHORITY_OPERATION_CONTINUITY_FAILURE |
CLOCK_RESTART_CONTINUITY_FAILURE |
EMERGENCY_SECURITY_REBIND |
REMOTE_CAPACITY_EXHAUSTION |
ACTUATION_RESTRICTIVE_CAUSE_LEDGER_OVERFLOW |
ACTIVE_ACTUATION_QUALIFICATION_FAILURE |
ACTUATION_ARBITER_STATE_LOSS_ISOLATION |
CONFIRMED_ESTOP_OPERATOR_RESET |
UNKNOWN_ESTOP_INSPECTION_RESET`. It binds the exact prior composite and
subordinate heads, authenticated cause and exact reset/inspection/isolation
evidence when applicable. Timeout and restrictive-cut causes additionally bind
the exact accepted-transfer phase and required deadline/cut evidence; continuity,
restart, emergency-rebind, capacity, readable Active qualification failure,
unavailable/corrupt-arbiter external isolation, generic retirement, confirmed-
ESTOP reset and unknown-ESTOP inspection have disjoint cause-specific evidence.
The fact
also binds
canonical complete typed partitions for declarations, active command tips,
command-application attempts, ingress/fail-safe operations, accepted transfers,
retention and physical-quiescence obligations. The same CAS removes all live
authority, retires declarations, turns each unadmitted received tip into an
exact linked rejection record, and fences each admitted/invoked or ambiguous
boundary operation for non-success reconciliation. It allocates a canonical key
order and contiguous global journal-sequence range for every new linked record
and binds exact key-to-record/outcome bijections. It cannot fabricate `applied`,
drop a prior chain or omit an obligation.

For an available arbiter, the entry CAS consumes the complete transition-receipt
set that fences the generation's exact domain or proves exact agreement with an
already FENCED mirror and no missing reconciliation set. For proved state loss,
it instead consumes `BodyActuationArbiterStateLossIsolationFact`, preserves the
last authenticated mirror and installs only
`ARBITER_STATE_LOST_ISOLATION_REQUIRED`; it cannot invent an arbiter successor,
epoch or receipt. The resulting `BodyActuationArbiterMirror` is either FENCED
with every operation/output/watchdog/reconciliation obligation retained, or
retains the exact lost-state unknown inventory. It cannot be OPEN or carry a
fabricated RETIRED state.

Only later qualified arbiter physical-quiescence retirement or external physical
isolation for lost state, followed by
`INSTALL_BODY_RETIREMENT_BOUNDARY_CLOSURE_EVIDENCE`, can close the domain.
Thus restart, rebind, authority cut, capacity pressure or state loss cannot turn
a storage retirement label into physical quiescence.

An arbiter-state-loss event can take that drain edge directly only from outside
the ESTOP-restrictive class. From a confirmed, unknown or possibly effective
ESTOP predecessor, `ISOLATE_BODY_AFTER_ACTUATION_ARBITER_STATE_LOSS` instead
preserves `INSTALLED_CHAIN`, maps a merely pending possible ESTOP to
`ESTOP_OUTCOME_UNKNOWN`, and retains the exact state-loss inventory. The later
confirmed reset or unknown inspection event consumes both its specialized local
evidence and that state-loss fact when it owns the drain edge. Likewise,
`EXHAUST_BODY_REMOTE_COMMAND_CAPACITY_TO_RETIREMENT_DRAIN` is legal only outside
the ESTOP-restrictive class. `SEAL_BODY_REMOTE_COMMAND_CAPACITY_UNDER_ESTOP`
preserves the class in `INSTALLED_CHAIN`; only the matching specialized local
event can later enter drain.

Drain-only permits only exact fenced-command/application/ingress/fail-safe
resolution, transfer-tombstone closure, physical-quiescence evidence and safe
retention. Those events need the original admitted/reservation evidence but no
live lease or declaration and can never create authority or an `applied` result.
Receipt-free `BodySessionGenerationRetirementFinalizationFact` binds the exact
current drain head and canonical complete inventories proving no live command,
active application attempt, pending body operation, open transfer or missing
boundary-closure evidence. It consumes exactly one ADR-007
`BodyActuationBoundaryRetirementClosureEvidence` branch for the immutable
generation domain key: `EXACT_ARBITER_RETIREMENT` with that domain's terminal arbiter head/receipt, or
`LOST_ARBITER_PHYSICAL_ISOLATION` with its qualified isolation fact and no
invented arbiter state. A foreign or substituted key rejects.
For partial parent genesis whose domain never advanced past reservation, either
closure branch additionally consumes the exact
`ActuationAuthorityDomainReservedPartialRetirementReceipt` and conditionally
verifies the jurisdiction registry is
`RESERVED_PARTIAL_RETIREMENT_RETIRED` for this generation. The exact branch must
bind `EXACT_GENESIS_ARBITER_RETIRED`; the lost branch must bind
`LOST_GENESIS_ARBITER_PHYSICALLY_ISOLATED`. Normal owned-domain finalization
forbids that receipt, and reserved-partial finalization cannot substitute normal
owner-handover evidence.
The partial-retirement receipt must descend from the exact
`ActuationAuthorityDomainReservedPartialRetirementFenceReceipt` that the ADR-001
parent partial-retirement edge consumed. A stale body-genesis head or direct
reserved-to-retired claim cannot substitute.
`FINALIZE_BODY_SESSION_GENERATION_RETIREMENT` alone installs
`TERMINAL`; its receipt binds the fact, prior/installed composite and subordinate
heads, selector version, generic commit and complete terminal bijections.

ADR-001 successor allocation atomically consumes that exact finalization receipt
through the logical-session lineage selector, publishes one new generation and
emits one `LogicalSessionGenerationCreationReceipt`. The new body genesis consumes
that receipt and its one-use plant child marker. A second successor cannot merely
bind or replay the predecessor receipt. If
the predecessor entered drain-only from either ESTOP state, it also binds exactly
one installed `OPERATOR_RESET_AND_RETIRE_GENERATION` or
`INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE` receipt through the finalization
lineage, matching the predecessor state. Missing, mismatched, remote, generic-
retirement or replayed specialized/finalization evidence rejects. A new
generation whose predecessor closure uses
`LOST_ARBITER_PHYSICAL_ISOLATION` additionally binds the exact state-loss
isolation fact, qualified physical-isolation evidence for every
possible old output/watchdog/token and its terminal finalization lineage. A
software fence or new empty arbiter cannot substitute. The new generation then starts separately
in HOLD with no lease. Thus a generic
retirement cannot erase a confirmed or possible ESTOP boundary effect and use
generation rollover as a reset path.

The closed authority/lifecycle-affecting body event union is:

- `BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION`;
- `CONFIRM_ACTUATION_AUTHORITY_DOMAIN_GENERATION_GENESIS`;
- `RECONCILE_BODY_ACTUATION_DOMAIN_GENERATION_GENESIS`;
- `ISSUE_BODY_COMMAND_FRESHNESS_GRANT`;
- `EXPIRE_BODY_COMMAND_FRESHNESS_GRANT`;
- `REOPEN_BODY_ACTUATION_GATE_WITH_FRESH_EPOCH`;
- `BEGIN_PLANT_AUTHORITY_ACQUISITION`;
- `COMMIT_PLANT_AUTHORITY_ACQUISITION`;
- `CANCEL_OR_FAIL_PLANT_AUTHORITY_ACQUISITION`;
- `BEGIN_PLANT_AUTHORITY_RENEWAL`;
- `COMMIT_PLANT_AUTHORITY_RENEWAL`;
- `CANCEL_PLANT_AUTHORITY_RENEWAL_PRESERVE_EXACT_UNEXPIRED_LEASE`;
- `FAIL_OR_EXPIRE_PLANT_AUTHORITY_RENEWAL_TO_HOLD`;
- `BEGIN_PLANT_AUTHORITY_TRANSFER`;
- `ENTER_PLANT_AUTHORITY_TRANSFER_HOLD_QUIESCING`;
- `TIME_OUT_PLANT_AUTHORITY_TRANSFER_TO_RETIREMENT_DRAIN`;
- `RETIRE_PREDECESSOR_AUTHORITY_AND_COMMAND_DECLARATION`;
- `BEGIN_SUCCESSOR_AUTHORITY_GRANT`;
- `INSTALL_SUCCESSOR_AUTHORITY_GRANT`;
- `FAIL_SUCCESSOR_AUTHORITY_GRANT_TO_HOLD`;
- `APPLY_BODY_CLOCK_RESTART`;
- `COMPLETE_RECONNECT_WITH_EXACT_CONTINUITY`;
- `FAIL_RECONNECT_TO_HOLD`;
- `EXPIRE_PLANT_AUTHORITY`;
- `RELEASE_PLANT_AUTHORITY`;
- `REVOKE_PLANT_AUTHORITY`;
- `ENTER_BODY_HOLD`;
- `NORMAL_HOLD_RECOVERY`;
- `LATCH_BODY_ESTOP`;
- `OPERATOR_RESET_AND_RETIRE_GENERATION`;
- `INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE`;
- `RETIRE_BODY_SESSION_GENERATION`;
- `ISOLATE_BODY_AFTER_ACTUATION_ARBITER_STATE_LOSS`;
- `ENTER_BODY_SESSION_GENERATION_RETIREMENT_DRAIN` as the required subordinate
  edge of every outer retirement-drain transition;
- `CLOSE_FENCED_COMMAND_AFTER_AUTHORITY_CUT`;
- `CLOSE_FENCED_BODY_OPERATION_AFTER_AUTHORITY_CUT`;
- `INSTALL_BODY_RETIREMENT_BOUNDARY_CLOSURE_EVIDENCE`;
- `COMPACT_BODY_RETIREMENT_RETENTION`;
- `FINALIZE_BODY_SESSION_GENERATION_RETIREMENT`;
- `REPLACE_BODY_SESSION_DESCRIPTOR`;
- `APPLY_PLANNED_BODY_SECURITY_REBIND`;
- `APPLY_EMERGENCY_BODY_SECURITY_REBIND`;
- `RESERVE_BODY_FAIL_SAFE_SIDE_EFFECT`;
- `UPGRADE_BODY_FAIL_SAFE_TO_ESTOP`;
- `EXHAUST_BODY_REMOTE_COMMAND_CAPACITY_TO_RETIREMENT_DRAIN`;
- `SEAL_BODY_REMOTE_COMMAND_CAPACITY_UNDER_ESTOP`; and
- `COMPLETE_RESERVED_FAIL_SAFE_COMMAND`.

The `MAP_LIVE_LEASE_DEADLINE_NO_LATER` branch of
`APPLY_BODY_CLOCK_RESTART` uses subordinate authority transition
`BEGIN_RECONNECT_RECOVERY`; the other clock branches never create that pending
operation. Each event uses the exact axis cases, mutation contract, pre-CAS fact,
and post-CAS sidecar cardinality specified in this ADR. The retained B01 selector
matrix is diagnostic only and cannot change that meaning. Unknown, default,
inferred, or legacy aliases reject.

`NORMAL_HOLD_RECOVERY` is body-only: it changes the exact ADR-007 HOLD cycle
`HOLD_EFFECTIVE -> HOLD_CYCLE_CONSUMED` while preserving lifecycle HOLD, typed
lease/declaration absence and the FENCED arbiter mirror. It grants no authority
or OPEN epoch. Only a later fresh acquisition/grant/reconnect activation can
atomically install `ACTIVE + LIVE + NONE + OPEN`.

The body clock is authority state, not journal-only metadata. If restart restores
the exact authenticated monotonic clock state and continuity under the same clock
incarnation, no clock bridge occurs. Otherwise, the ADR-007
`BodyClockRestartBridge` is one receipt-free multi-subhead transition under the
body-session-control selector. In addition to its closed authority-recovery
branch, the bridge inventories every installed ADR-007 Active output,
`BodyActuationWatchdogCommitment`, application attempt and actuation-gate epoch.
Unless exact authenticated monotonic/watchdog continuity under the same clock
incarnation avoids the bridge entirely, the qualified arbiter first fences the
old epoch and takes or confirms the profile's local restrictive restart action.
The bridge binds that exact fence and partitions every attempt. Only a definitive
accepted-or-no-effect restrictive-action result can then move the exact old
watchdog lineage
`FENCED_TO_RESTRICTIVE_ACTION -> RETIRED_BY_CLOCK_DISCONTINUITY`; the no-effect
branch preserves the old output in the complete possible-output set and is not
quiescence evidence. Pending or ambiguous resolution remains
`FENCED_TO_RESTRICTIVE_ACTION`, blocks grant issuance, reconnect and gate reopen,
and cannot copy an old numeric deadline. A losing body CAS rebases the exact
restrictive fence over the new head.

The bridge also inventories every installed ADR-007 body-issued command-freshness
grant and creates an exact expiry tombstone for each one. No old-clock grant or
numeric deadline migrates. It preserves every installed fail-safe effect
operation, position-slot conflict and terminal tombstone; none can be remade under
the new clock. Its authority branch either maps
an unexpired lease to a fresh-clock deadline that is provably no later than the
old remaining duration, expires the lease and enters HOLD, preserves an
already-HOLD typed no-lease state, or uses
`PRESERVE_ESTOP_LATCHED_NO_LEASE` for a confirmed-latch predecessor without an
accepted transfer, or `PRESERVE_ESTOP_OUTCOME_UNKNOWN_NO_LEASE` for an unknown-
outcome predecessor without one. Each branch preserves the exact ESTOP state,
typed lease absence and pending `NONE`; neither can enter HOLD or authorize work.
A final `RESUME_ACCEPTED_TRANSFER_NO_LATER` branch accepts only an authenticated
exact accepted-transfer phase and one closed lifecycle floor
`NON_ESTOP_FLOOR | CONFIRMED_ESTOP_FLOOR | UNKNOWN_ESTOP_FLOOR`. It maps every
applicable deadline without extension and preserves or advances that transfer
phase, every predecessor fence, and the exact selected lifecycle floor. The
confirmed and unknown variants cannot substitute for each other. If
that proof is unavailable from a non-ESTOP predecessor, the body retires the
generation with the transfer fences intact instead of applying the clock
bridge. From an `ESTOP_LATCHED` or `ESTOP_OUTCOME_UNKNOWN` predecessor,
unavailable proof cannot select generic retirement: the body preserves the exact
restrictive state, remains non-authorizing, and preserves the accepted transfer
at the same or a later fenced phase. The confirmed state requires
`OPERATOR_RESET_AND_RETIRE_GENERATION`; the unknown state requires
`INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE`. The lease-mapping branch installs HOLD, lease
absence, and `RECONNECTING` with the exact fenced predecessor lease and mapped
exclusive deadline. Only `COMPLETE_RECONNECT_WITH_EXACT_CONTINUITY` can later
install that same term/lease/issuer/holder as `LIVE`; equality with the mapped
deadline is expired. `FAIL_RECONNECT_TO_HOLD` removes and tombstones the candidate.
The expire and preserve-HOLD branches install pending operation `NONE` for a
cancellable acquisition, renewal, or reconnect and retain its exact tombstone.
They cannot cancel a durably accepted transfer. Both the journal successor and
authority successor bind the same bridge fact. One
composite compare-and-swap installs both, and the
post-CAS bridge receipt binds both pairs of subordinate heads. A journal-only
clock change, an old-clock authority head beside a new-clock journal head, or
command/ACTIVE admission before that commit keeps admission closed. An exact
non-ESTOP predecessor can then retire; an ESTOP or indeterminate predecessor
cannot authorize a successor generation without the operator-reset receipt.

Command admission uses the same composite selector. It validates the exact
current `PlantAuthorityStateHead`, lease installation/currentness receipt,
current composite membership, closed plant
lifecycle, subordinate action-command `DeclarationLedgerHead`, and fresh
`COMMAND_ADMISSION_LEASE_NOT_AFTER` intent in the prior composite head. The
winning bundle binds the matching strict-before evaluation. Its journal successor
preserves those exact subordinate digests, and its composite successor binds the
journal successor. A concurrent authority,
lifecycle, descriptor/security, or command-declaration transition changes the
expected composite head, so the command compare-and-swap loses and the command
is not admitted. This single order closes the check-to-append race; a second
independent selector check does not.

Within one session generation, every acquisition or transfer grant has a
strictly higher persisted term. A new holder receives a new random lease ID and
declares a fresh command stream epoch. Renewal is allowed only while the exact
current lease is strictly unexpired; it preserves the same term, lease ID,
issuer, and holder while extending the receiver-local deadline within the
declared maximum duration. A late renewal enters `HOLD` and requires a newer
acquisition. UTC timestamps are audit and duration bounds; the receiving body
derives and enforces the local monotonic deadline. Equality with the deadline is
expired.

Handover is body-coordinated:

1. record an idempotent transfer request from the current holder or enrolled
   overriding operator;
2. stop admitting new commands for the old holder;
3. enter plant-profile `HOLD` and reach the declared bounded quiescence boundary;
4. retire the old lease and command declaration durably;
5. persist a strictly higher term;
6. issue the new bounded lease and accept a fresh command declaration; and
7. return body-issued receipts for every terminal step.

If body restart preserves an exact authenticated snapshot of a clean `ACTIVE`
state with no pending acquire, transfer, release, revoke, ESTOP, or other
authority mutation, it restores into `RECONNECTING` or `HOLD`, never directly
`ACTIVE`; only the exact unexpired holder may prove continuity. A durably
accepted transfer or release is a non-reversible latch. Restart resumes its
stop-admission, HOLD, retirement, and grant phases; it cannot reactivate the old
holder or silently cancel the operation. If the exact phase or snapshot
continuity is unavailable or ambiguous, an exactly proved non-ESTOP generation
can retire and open a fresh opaque UUIDv4 generation. A proved or possible ESTOP
state remains non-authorizing and blocks successor-generation creation until
authenticated local operator reset. Old generations reject by inequality; no
generation ordering is inferred.

## Low-overhead authority reconciliation

One body owner serializes lease transitions, command positions, restrictive
effects, dispositions, and executor acceptance for one plant generation. A
security-dependent body transition compares the exact security selector in its
qualified local transaction. The body does not own global security state. It
holds no lock across network, application, or device work.

The live lease binds:

- the direct realm, plant profile, and lease-bound command declaration.
- the security state, holder, term, random lease ID, and authority version.
- the receiver clock and exclusive deadline.

Serialized lease bytes never restore live authority after restart.

The body issues each command freshness grant before publication. The grant binds
the receiver clock, absolute exclusive deadline, declaration, publisher
incarnation, position range, permitted modes, complete reserved state, and each
required live-lease coordinate. Receiver arrival is evidence only. It never
starts or refreshes command lifetime.

Active and explicit HOLD require the current lease holder and ordinary stream
monotonicity before their installed action. HOLD carries no remote value, source,
or horizon. Its effect comes from the installed plant profile.

ESTOP is the only remote mode that can omit the lease and reach an early
idempotent local latch after its complete current-context gate. The command still
requires authenticated action ingress, a live generation, current security, and
explicit ESTOP intent. It also requires an exact live declaration and unexpired
body grant, or the bounded post-HOLD escalation snapshot over that declaration,
an explicitly preserved unused ESTOP slot, and the same unchanged deadline. A
rejected or conflicting command can cause a separately attributed local latch
only after it passes that complete pre-replay restrictive gate. It cannot claim
an admitted `STOP_LATCHED` disposition. Malformed, unauthenticated,
stale-generation, or expired-grant or snapshot input cannot reach the latch.

One command position carries one setpoint and one application attempt. The body
issues a receiver-owned single-use executor capability after Active admission.
The executor accepts that capability through the body owner, then performs
bounded device work outside the lock. Unknown completion keeps the lane
restrictive and cannot authorize a retry.

A compact simulation step uses a separate receiver-issued grant and strict
execution owner. It grants simulation mutation only and shares no plant lease,
command position, or executor capacity.

B03 selects positive finite owner capacities and implementation names here.
Deadline, retention, and queue values use the bounded ADR-010 profile envelope.
Receiver-owned time is integer monotonic nanoseconds within one explicit clock
incarnation. Each value must fit checked arithmetic, aggregate bytes, owner-state
limits, and its complete terminal path. Missing, unknown, zero, overflowed, or
uninstalled values reject before authority or allocation. B03 cannot change body
issuance, absolute time, ESTOP ordering, or restart meaning.

## Rejected alternatives

- Last-writer-wins action topics.
- Commander-issued or payload-self-asserted leases.
- A configuration toggle between direct and gated modes.
- Wall-clock expiry as the only restart fence.
- A fourth ambiguous authority epoch.
- Lexicographic comparison of UUID epochs.
- Granting a new lease before old command admission and quiescence are closed.

## Illustrative wire example

This JSON is a lease-field excerpt, not a valid complete wire object. A complete
realm-scoped lease also carries the direct `AuthorityRealmKey`, source-session
kind, logical session ID, descriptor/transcript/security binding, plant profile,
body/arbiter scope, clock/deadline policy, operation context and applicable
installed-head/receipt references required above. Omission here grants nothing.

```json
{
  "session_generation": "00000000-0000-4000-8000-0000000000a2",
  "term": 7,
  "lease_id": "00000000-0000-4000-8000-0000000000b7",
  "issuer_principal_id": "crebain-body-a",
  "holder_principal_id": "haldir-commander-a",
  "holder_entity_id": "controller-a",
  "issued_at_utc_ms": 1784200000000,
  "expires_at_utc_ms": 1784200030000
}
```

## Invalid or hostile example

```json
{
  "session_generation": "00000000-0000-4000-8000-0000000000a2",
  "term": 6,
  "lease_id": "00000000-0000-4000-8000-0000000000b6",
  "issuer_principal_id": "engram-commander-a",
  "holder_principal_id": "engram-commander-a",
  "holder_entity_id": "controller-a",
  "issued_at_utc_ms": 1784200000000,
  "expires_at_utc_ms": 1784200030000
}
```

A commander cannot self-issue the body lease; a stale term cannot regain
authority.

## Actors and state transitions

The tuples below are `(root, lifecycle, lease, pending operation)`:

`ABSENT_NEVER_USED body selector --fresh participant-admission genesis-->
(INSTALLED_CHAIN, HOLD, ABSENT, NONE) ->
(INSTALLED_CHAIN, HOLD, ABSENT, ACQUIRING) ->
(INSTALLED_CHAIN, ACTIVE, LIVE(term n), NONE)`.

Renewal is
`(INSTALLED_CHAIN, ACTIVE, LIVE(term n), NONE) ->
(INSTALLED_CHAIN, ACTIVE, LIVE(term n), RENEWING) ->` either the same tuple with
`NONE` and an extended deadline, the exact unextended and still-unexpired lease
with `NONE`, or `(INSTALLED_CHAIN, HOLD, ABSENT, NONE)`.

Transfer:

`(INSTALLED_CHAIN, ACTIVE, LIVE(A,n), NONE) ->
(INSTALLED_CHAIN, ACTIVE, LIVE(A,n), TRANSFER_REQUESTED) ->
(INSTALLED_CHAIN, HOLD, LIVE(A,n), HOLD_QUIESCING) ->
(INSTALLED_CHAIN, HOLD, ABSENT, PREDECESSOR_RETIRED) ->
(INSTALLED_CHAIN, HOLD, ABSENT, GRANTING_SUCCESSOR) ->
(INSTALLED_CHAIN, ACTIVE, LIVE(B,n+1), NONE)`.

A failed successor grant ends at `HOLD(ABSENT,NONE)` with the predecessor
tombstones intact.

Restart continuity is `(INSTALLED_CHAIN, ACTIVE, LIVE, NONE) ->
(INSTALLED_CHAIN, HOLD, ABSENT, RECONNECTING) ->` either
`(INSTALLED_CHAIN, ACTIVE, same LIVE, NONE)` or
`(INSTALLED_CHAIN, HOLD, ABSENT, NONE)`. The middle state carries the exact fenced
predecessor lease as non-authorizing recovery content.

Expiry or non-ESTOP uncertainty:

`ACTIVE -> HOLD`. Confirmed ESTOP and reset:

`ANY_REACHABLE_NON_RETIRED_TUPLE ->
(INSTALLED_CHAIN, ESTOP_LATCHED, ABSENT,
NONE | EXACT_FENCED_ACCEPTED_TRANSFER_PHASE) ->
OPERATOR_RESET_AND_RETIRE_GENERATION ->
(RETIRED_DRAIN_ONLY, RETIRED, RETIRED_TOMBSTONE, NONE) ->
FINALIZE_BODY_SESSION_GENERATION_RETIREMENT ->
(TERMINAL, RETIRED, RETIRED_TOMBSTONE, NONE)`.

An ambiguous ESTOP boundary instead follows
`ANY_REACHABLE_NON_RETIRED_TUPLE ->
(INSTALLED_CHAIN, ESTOP_OUTCOME_UNKNOWN, ABSENT,
NONE | EXACT_FENCED_ACCEPTED_TRANSFER_PHASE) ->
INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE ->
(RETIRED_DRAIN_ONLY, RETIRED, RETIRED_TOMBSTONE, NONE)`. It cannot use the
confirmed-latch reset edge or generic retirement. Finalization then uses the
same complete-inventory edge shown above.

## Bounds and resource behavior

Lease duration, clock uncertainty, operation deadline, transfer time, HOLD
quiescence, in-flight commands, receipt journal, term range, retries, and query
work are finite. The pending-operation slot is singular and bounded. Candidate
lease bytes, transfer/reconnect recovery content, retained operation facts, and
term/lease/operation tombstones have explicit count, byte, and retention limits.
Each resolution binds the exact predecessor fact and operation ID. Resource
exhaustion fails to HOLD/deny or retires an exact non-ESTOP generation and never
creates a holder, drops a latched transfer, resets ESTOP, or reuses an identity.

Generic `CommandFrame` wire validity is not plant eligibility. After an attempt
is classified as Active and before authority attachment or admission, the
producer's checked codec must require every declared sensor component and
decoder population, a finite value for each, contiguous components
`0..arity-1`, and one consistent explicit unit for every output channel. It must
not invent a midpoint, zero, range endpoint, component, or unit. Plant admission
then resolves the exact content-addressed installed profile and requires the
exact channel set, arity, unit, range, current session generation, authority
lease, and horizon constraints. The body repeats the installed-profile check at
the final actuator boundary. Missing or inconsistent data makes Active
ineligible; a local unchecked mapper cannot supply qualification evidence.

This Active construction and admission work does not move ADR-007's ESTOP latch
gate. After the complete pre-replay restrictive gate passes, a current
authenticated explicit ESTOP can reserve or apply its installed body-local
latch. The latch can precede stream replay or lease checks. A later command
rejection does not suppress or undo that separately attributed latch. Remote
HOLD instead requires ordinary stream monotonicity, the exact live-holder lease,
and the installed plant profile before it can reserve or invoke HOLD. A
body-local watchdog or governor can request HOLD through its separate local
policy path without attributing that
effect to rejected remote bytes. Wrong context, unbounded or unauthenticated
input, a wrong route or audience, an ambiguous mode, an invalid slot, or an
expired deadline remains inert. HOLD and ESTOP claim no universal safe actuator
value.

## Threat and hazard analysis

This addresses split brain, stale delayed commands, self-issued authority,
handover overlap, restart revival, lease replay, and wall-clock manipulation.
HOLD is a protocol lifecycle state whose actual actuator behavior is defined by
the content-addressed plant profile. It is not universally zero-safe or physical
certification. A transfer can create availability loss and must declare its
bounded fail posture.

## Formal properties

- Identical plant/session/generation/lease/stream/command bytes under a different
  `AuthorityRealmKey` cannot satisfy authority currentness, idempotency, replay,
  disposition or handover equality.
- At most one live holder exists for a plant/session generation.
- Every admitted action command matches the exact current fence.
- Renewal preserves the exact term/lease/issuer/holder identity and cannot revive
  an expired lease.
- A revoked, expired, old-generation, old-term, old-lease, old-holder, or retired
  stream command is never admitted.
- No transfer makes the new holder live before old admission is closed and the
  required quiescence boundary is reached.
- Authority/lifecycle change, action-command declaration change, and command
  admission have one composite compare-and-swap order. A command checked against
  a lease or declaration that loses currentness cannot append as admitted.
- Empty authority state exists only through
  `PLANT_AUTHORITY_GENESIS_FROM_BODY_SESSION_CREATION` in the one-use composite
  session genesis. It cannot be recreated after state loss.
- Lifecycle, lease currentness, and pending operation are independent closed
  axes. No phase alias can omit an axis edge or grant authority.
- Every acquisition, renewal, successor-grant, and reconnect operation either
  installs its exact authorized result, installs its exact no-install terminal
  result, or causes non-ESTOP generation retirement. A confirmed ESTOP
  predecessor remains latched until operator-reset retirement; an unknown ESTOP
  outcome remains quarantined until inspection/reset-and-retire. No durable
  pending phase is a sink.
- Restrictive transitions preempt admission from every pending phase. ESTOP
  removes live lease authority and command declaration in the same composite
  transition while preserving an accepted-transfer latch until the matching
  confirmed or unknown-outcome specialized retirement path.
- `RETIRE_BODY_SESSION_GENERATION` cannot consume `ESTOP_LATCHED` or
  `ESTOP_OUTCOME_UNKNOWN`. Only authenticated local physical-boundary
  `OPERATOR_RESET_AND_RETIRE_GENERATION` can consume the confirmed state; only
  `INSPECT_UNKNOWN_ESTOP_BOUNDARY_AND_RETIRE` with complete qualified evidence
  can consume the unknown state. Each retains any accepted-transfer fence and
  ESTOP result as a terminal tombstone. The complete-inventory finalizer alone
  installs `TERMINAL`, and successor-generation genesis binds the matching
  specialized retirement and finalization receipts through one lineage.
- Every `INSTALLED_CHAIN -> RETIRED_DRAIN_ONLY` edge consumes one cause-specific
  `BodySessionGenerationRetirementFact` through the same subordinate retirement
  transition, regardless of whether timeout, authority cut, continuity failure,
  restart, emergency rebind, capacity exhaustion, generic retirement, reset or
  inspection owns the outer event. Causes cannot borrow one another's evidence,
  and no state label can replace the fact. Normal entry retains a complete
  FENCED arbiter mirror. State-loss entry retains the last authenticated mirror,
  creates no arbiter successor and requires external isolation. Only later
  physical-quiescence/isolation evidence can close the boundary lineage.
- A drain-only or terminal body root has no live authority, declaration or
  admission edge. Terminal requires complete subordinate closure and exact
  physical-quiescence evidence; no active command/application/operation can be
  stranded beside it.
- Restart never restores `ACTIVE` without exact clean-state continuity proof.
- After durable transfer acceptance, the old holder never becomes `ACTIVE`
  again in that session generation.

TLA+/state-machine tests shall include delay, duplication, partition, crash at
every transfer boundary, storage uncertainty, deadline equality, and two
commanders. Every transfer crash trace must resume the latched operation or
retire a non-ESTOP generation; a confirmed ESTOP trace must preserve the latch
until operator reset, and an ambiguous ESTOP trace must preserve unknown state
until qualified inspection/reset-and-retire. None may reactivate the old holder.

## Migration

Haldir and Engram commander adapters become clients of Crebain-issued authority.
Haldir decisions remain local permission evidence; they do not become leases.
Legacy authority copies and first-publisher adoption are removed from native
paths.

## Operational recovery

Ambiguous mutation outcomes are queried by operation ID. Lost or corrupt
authority state keeps admission closed. If exact non-ESTOP currentness can be
recovered, the generation retires when continuity cannot be established. A
confirmed latch requires authenticated local operator reset and retirement. A
possible but unproved latch requires the complete qualified local query,
inspection, interlock, isolation and reset-and-retire evidence; a reset command
alone is insufficient. Operators may preempt only through enrolled override
authority and receipted body operations.

## Compatibility and rollback

The new lifecycle requires a complete provider/commander/body migration.
Rollback restores the prior disabled candidate and cannot retain a new commander
against an old body.

## Open questions

<a id="ncp-b01-selector-allocation-adr-006-v1"></a>

Exact implementation names and bounded capacities remain allocation inputs.
Body-final authority, time, lease, and fail-closed safety rules are closed.

B03 selects 1 through 32 canonical implementation identities. Each identity
matches `[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?` and can name only a boundary
that implements the owner, clock, lease, grant, or executor semantics above.
Authority-state capacity is 1 through 65,536 entries. The selected value must
fit the complete active, ambiguous, terminal, and restart state under one
checked aggregate byte budget.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: every fence component has one comparison rule.
2. Security: body issuer and exact holder are authenticated.
3. Safety: Crebain remains final software actuator authority; HOLD limits are
   profile-specific.
4. Lifecycle: transfer, expiry, restart, ESTOP, and ambiguity are closed.
5. Resources: lease and handover work are bounded.
6. Migration: direct and gated adapters share generic authority operations.
7. Science: command admission makes no effectiveness or calibration claim.
8. Operations: query, alarm, recovery, and operator override are explicit.
9. Evidence: formal and live crash-point handover campaigns are mandatory.
10. Governance: body, operator, profile, and incident ownership are named.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes.
