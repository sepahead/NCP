# ADR-010 — Specify finite per-plane QoS and overload behavior

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: real-time/performance reviewer and consumer reviewers

## Context

Generic reliable delivery does not define which messages may queue, drop,
supersede, block, or survive restart. Without exact per-plane policy, observer or
extension load can starve control, stale action can queue behind newer action,
and an implementation can claim success while silently dropping required
evidence.

## Proposed decision

NCP shall define one finite QoS profile for each core-plane/message-class pair.
The minimum semantics are:

| Core plane and message class | Queue/retention | Overload behavior |
|---|---|---|
| control / RPC | bounded request/reply and idempotency journal | reject before mutation with explicit overload/deadline result |
| action / command | capacity one per declared stream plus bounded in-flight receipt state | newest eligible command may supersede only by explicit rule. Fail-safe severity has priority. Ambiguous fail-safe blocks later Active |
| perception / sensor | bounded latest/history policy declared by stream | explicit gaps/drop counters. Never fabricate continuity |
| observation / disposition | bounded priority journal and subscriber queues | body journal cannot block. Slow observers gap or detach |

The NCP `Plane` enum has exactly four recognized core operational values plus the
fail-closed `unknown` sentinel. Extension traffic is not a fifth operational
plane and does not enter a core-plane QoS object. ADR-008 gives extension traffic
a separate installed resource profile for ingress, reassembly, parsing, and
callback work. That profile remains under the same finite endpoint or deployment
envelope and cannot borrow control or action capacity. A future non-core traffic
class requires its own registered profile and does not widen the `Plane` enum by
default.

ADR-001 `AuthorityRealmKey` is the canonical tuple of server authority principal
and stable realm ID. It excludes credential/security epochs, queue/store
incarnations, and every session or stream generation. A reusable QoS profile
contract can remain realm-independent. Each installed QoS binding is
realm-scoped and identifies the exact
`(AuthorityRealmKey, profile digest, plane, message class, literal route,
audience)` tuple.

Every realm-scoped admission request, queue key, capacity reservation, allocator
entry, in-flight state, overload fact, gap/drop record, query result, and receipt
in this ADR carries `authority_realm_key: AuthorityRealmKey` as a direct
canonical member. Its canonical bytes and digest include that member. The same
rule applies to installed profile bindings, scheduler lanes, durable journals,
shutdown/retention records, and metrics evidence used to make a conformance or
nonstarvation claim. A nested parent, route, endpoint, descriptor, transcript,
or local configuration cannot supply a missing realm in portable evidence.
When session coordinates are present, the direct realm and those coordinates
together encode the exact
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` consumer
foreign key once. A duplicate compatibility realm must compare exactly or
reject.

The direct realm must equal the authenticated ingress realm, default-deny
manifest scope, audience, route projection, session descriptor, declaration, and
owning queue or journal. Missing, default, wildcard, retired, or mismatched realm
data rejects before queue lookup, budget selection, allocation, mutation,
priority arbitration, or callback. A route's realm segment is only the canonical
projection of the stable realm ID; it cannot supply the server-authority
principal or authorize an installed binding.

Each declared action stream has one allocator across every mode that its scope
permits. A severity change inside that stream cannot bypass sequence or
idempotency accounting. The lease-bound declaration and an optional ESTOP-only
declaration keep separate allocators because positions from different publisher
incarnations are not comparable. The body-owned event order merges their
attempts and applies severity priority.

ESTOP receives action-queue priority, admission, and a `stop_latched`
disposition only after full envelope, manifest actor/plane, route, audience,
session, stream, and semantic validation. It may omit only the authority lease
as separately specified. ADR-007's distinct body-local early ESTOP reservation
can latch after its complete pre-replay restrictive gate but before the
remaining stream checks. That latch grants no queue entry, command admission,
or disposition, and an ambiguous reservation blocks later Active admission.
HOLD has no pre-replay exception.

Priority after verification does not prevent verifier starvation. Action ingress
therefore uses two bounded scheduling stages before semantic severity arbitration:

1. Before decode or allocation, enforce hard frame, nesting, member, attachment
   and decompression ceilings. Then apply bounded token/queue budgets keyed by the
   already authenticated `AuthorityRealmKey`, transport principal, credential
   epoch and literal route. Unauthenticated traffic and principal or realm spray
   share a smaller global hostile-input budget. No raw payload member selects a
   budget.
2. Route bounded candidates into independent finite verifier lanes. The normal
   action lane is fair and quota-limited per authenticated
   realm/principal/route. A reserved emergency lane is usable only by a
   separately enrolled emergency transport credential/principal in the exact
   realm and on its exact manifest route; bytes that merely decode to HOLD/ESTOP
   cannot enter it. Both lanes perform the complete bounded-envelope,
   authentication, manifest, realm, route, audience, session, grant, mode,
   deadline, and installed-profile checks in ADR-007's pre-replay restrictive
   gate. Only then can the verified severity arbiter classify ESTOP, HOLD, and
   Active. A qualified fresh ESTOP can reserve its early body-local latch before
   the remaining stream, lease, channel, and source checks. Those checks still
   determine command admission and disposition. HOLD and Active receive no early
   side effect.

After ratification and rebaseline, the proposed predecode budget would include
each accepted class/path collection ceiling. Trusted route or typed API context
would select the message class; raw kind, mode, unit, metadata spelling, or
fallback value could not select a verifier lane or reserve semantic queue
capacity. The proposed 256-entry `OpenSession` binding metadata rule would be
checked per matched map during duplicate-aware structural decoding. A 257th
distinct member would reject before its key or value is retained. Unknown
same-named maps would not inherit that class-specific ceiling.

For an Active command, checked-codec completeness and installed-profile
admission are finite work bounded by mapping, channel, component, and horizon
ceilings. They complete before Active admission and cannot invent missing
midpoints, zeros, range endpoints, components, or units. A qualified early ESTOP
latch remains separately attributed when later stream admission rejects its
command. Remote HOLD reaches its installed effect only after ordinary command
admission. A separate body-local fail-safe response never converts rejected
remote bytes into a successful command disposition.

The emergency lane grants verifier service only, never authority, admission or a
side effect. Invalid signatures, wrong-context traffic and lane misuse consume a
bounded attempt and cannot allocate durable command state. If Active and ESTOP
share one credential/route, pre-verification scheduling cannot safely distinguish
them; that deployment cannot claim bounded ESTOP nonstarvation under a same-
principal flood. A qualified nonstarvation claim therefore requires the separate
enrolled emergency lane or equivalent independently authenticated capacity.

Realm partitioning is not a resource multiplier. Every per-realm budget sits
under a finite endpoint/deployment cap that covers all enrolled realms and the
hostile-input pool. Adding realm keys cannot create unbounded queues, metrics
labels, verifier lanes, or reserved emergency capacity. Conversely, an
authenticated request in realm A cannot consume, replenish, supersede, or
deduplicate realm B's installed action capacity.

Every profile names reliability, ordering, durability, queue capacity, retention,
deadline, retry, supersession, drop/gap behavior, shutdown behavior, and evidence
emission. Defaults are non-authorizing and fail closed.

## Low-overhead QoS reconciliation

Every installed QoS profile has a closed shape. It names:

- the plane, message class, route, and audience.
- reliability, ordering, and durability.
- item and aggregate byte capacity.
- admission deadline, retention, and bounded retry.
- supersession, gap or drop behavior, and shutdown behavior.
- the evidence result.

The profile is selected from trusted prepared context before payload decoding or
queue allocation. Missing, unknown, corrupt, uninstalled, zero-authority, or
mismatched profiles reject before reservation. Transport defaults cannot supply
a missing field or widen a profile.

Every variable-size queue reserves item count and aggregate bytes. A request can
enter only when both reservations succeed. Each plane remains under one finite
endpoint or deployment cap, so adding realms, principals, routes, or subscribers
cannot multiply capacity without bound. ADR-008 extension resources remain in a
separate finite partition under that outer cap.

Action ingress reserves separate normal and enrolled emergency verification
work. Raw bytes that look like ESTOP cannot select the emergency lane. Complete
envelope authentication and the checks required to classify an enrolled
emergency candidate run before severity arbitration. Command admission then
runs its remaining stream and authority checks. Only ADR-007's separately
attributed early ESTOP latch can precede them. The body keeps fixed capacity for
lifecycle cuts, local restriction, and the sole final ESTOP path.

Lifecycle cuts, local restrictive escalation, and ready ESTOP work remain
preemptive. When perception work is ready, the installed profile's positive
`active_burst_max` caps consecutive Active body transitions. Reaching that cap
requires service of one ready perception event before another Active transition.
HOLD and ESTOP do not consume the Active burst count and cannot be delayed by
this fairness rule. The counter is body-owned, bounded, and reset only by the
selected service transition or a lifecycle-generation cut.

Control mutation deadlines govern only the start of new work. An authenticated
exact retry or query can return retained state after that deadline without
refreshing authority. Replies correlate through one exact bounded request
identity. A mismatch leaves unrelated pending requests untouched.

Prepared simulation steps use a separate finite request window, response window,
aggregate byte reservation, strict execution cursor, and one non-refreshing gap
deadline. Observer and extension work cannot consume those slots or action
capacity.

B03 selects a finite installed QoS-profile set and values within one shared outer
envelope. The envelope bounds item capacity, aggregate bytes, admission deadline,
retention, total attempts, pending-request count, gap wait, and work resolution.
It also bounds the consecutive Active transitions permitted while perception is
ready.
Every selected value must pass equality, overflow, exhaustion, and
corrupt-profile tests. A measured value cannot change ordering, authority, drop,
retry, or shutdown meaning.

The work-resolution duration covers normal completion plus any required
isolation termination before a worker slot can be reused. Timeout or task
cancellation without proved termination leaves the slot reserved. A profile
whose callback or backend cannot meet that bound is ineligible for a reclaimable
worker pool. An external effect that can remain outcome-unknown instead fences
its finite lane and cannot be retried under a new identity.

## Rejected alternatives

- One transport QoS setting for all planes.
- Unbounded reliable queues.
- Drop-oldest action queues without command identity/disposition.
- Let observer/extension traffic share action capacity.
- Bypass validation to prioritize raw ESTOP-looking bytes.
- Treat a missing metric or not-run load test as a pass.

## Illustrative profile

```json
{
  "profile_id": "ncp-action-v1",
  "authority_realm_key": {
    "server_authority_principal_id": "ncp-authority-a",
    "stable_realm_id": "realm-a"
  },
  "plane": "action",
  "route": "realm-a/session/plant-alpha/command/controller-a",
  "capacity_per_stream": 1,
  "ordering": "strict_stream_sequence",
  "retention": "until_terminal_disposition_or_expiry",
  "overload": "reject_new_active_and_emit_disposition",
  "fail_safe_priority": [
    "estop",
    "hold",
    "active"
  ]
}
```

This excerpt is not a complete installed profile.

## Invalid or hostile example

```json
{
  "plane": "action",
  "capacity_per_stream": 0,
  "overload": "best_effort",
  "fallback": "accept_without_receipt"
}
```

Unknown, zero, unbounded, best-effort authority, or receipt-free recovery
profiles reject. A realm-scoped installed profile also rejects when its direct
`AuthorityRealmKey` is missing, default, wildcard, or inconsistent with the
route and authenticated endpoint.

## Actors and state transitions

Queue entry:

`PREALLOCATION_BOUNDS -> AUTHENTICATED_REALM_PRINCIPAL_ROUTE_BUDGET ->
VERIFIER_LANE -> VERIFIED_SEVERITY_ARBITRATION -> ADMISSION_CHECK -> RESERVED
-> ENQUEUED -> CONSUMED -> DISPOSITIONED`.

Overload:

`ADMISSION_CHECK -> REJECTED_OVERLOAD`.

Ambiguous fail-safe:

`FAIL_SAFE_RESERVED -> OUTCOME_UNKNOWN -> ACTIVE_BLOCKED -> QUERY/OPERATOR
RESOLUTION`.

Observer/extension overload never changes the control/action state machine.

## Bounds and resource behavior

Every queue, journal, retry, timer, frame, batch, subscriber, metric label,
diagnostic, and shutdown wait has a maximum. Memory and CPU reservations for
predecode, normal verification, emergency verification and post-verification
control/action are independent of observer/extension budgets. Exact profiles are
benchmarked at just-below, exact, and just-above limits. Saturation tests cover
invalid signatures, valid Active floods, principal spray, emergency-route misuse,
same- and different-principal contention, same-principal cross-realm traffic,
realm spray, restart, and a valid ESTOP waiting at each boundary.

The proposed resource profile also binds the finite class/path lookup,
duplicate-aware immediate-member counting, codec mapping/component walk, exact
channel/unit/profile comparison, and horizon walk. These checks cannot allocate
from the semantic queue before they finish.

## Threat and hazard analysis

The decision addresses resource exhaustion, priority inversion, stale action,
fail-safe bypass, observer-induced control blocking, silent data loss, and
shutdown hangs. Rejecting or dropping can still reduce availability and affect a
plant; plant profiles and operators must define the bounded fail posture.

Direct realm identity prevents an attacker from replaying an otherwise valid
queue reservation, overload receipt, or stream position into a realm with equal
principal/session/generation text. It also prevents a consumer from merging
cross-realm gap or performance evidence. Global hostile-input bounds prevent the
opposite failure: manufacturing realm labels to multiply pre-authentication
capacity.

## Formal properties

- No queue grows without bound.
- Every realm-scoped profile binding, admission, queue/reservation key, journal
  entry, overload/gap fact, and receipt has one direct non-default
  `AuthorityRealmKey` in its canonical bytes.
- Realm equality holds across authenticated ingress, manifest, audience, route,
  descriptor, declaration, allocator, queue, journal, and evidence projection.
- A projection or metric aggregation that drops or rewrites the realm cannot
  support admission, conformance, or a nonstarvation claim.
- Same-principal, same-session, same-generation, same-stream, same-sequence, and
  same-byte work in different realms never shares replay, capacity,
  supersession, ambiguity, or receipt state.
- Exact bytes replayed at another authenticated realm cannot select a queue. A
  separately valid request with all non-realm fields equal but either realm-key
  coordinate changed uses distinct installed QoS and admission state.
- Per-realm partitions remain under one finite aggregate deployment cap; realm
  or principal spray cannot multiply pre-authentication resources.
- Extension/observer work cannot consume reserved control/action capacity.
- Raw mode bytes and invalid signatures cannot select reserved emergency verifier
  capacity. Only the exact authenticated emergency principal/credential/route can
  enter that finite lane, and full verification remains mandatory.
- Under the qualified separate-emergency-lane profile, normal or hostile verifier
  saturation cannot consume its reserved service budget. Without that separation,
  same-principal ESTOP nonstarvation is not claimed.
- A lower-severity action cannot pass an unresolved higher-severity attempt.
- While perception is ready, no more than the installed positive
  `active_burst_max` consecutive Active transitions occur before one perception
  event is serviced. This bound never delays a lifecycle cut, local restrictive
  escalation, HOLD, or ESTOP.
- Every accepted or rejected mutation has a terminal receipt/query path.
- Gaps are explicit and never replaced with invented observations.

## Migration

N05 implements pure checked queue/transition cores; N06 maps them to transport.
Consumers stop relying on unspecified transport defaults and configure exact
registered profiles. They key QoS evidence and session state by
`(AuthorityRealmKey, session_kind, logical_session_id, generation)`. The corpus
adds cross-realm replay/merge, route/direct-key mismatch, realm-dropping
projection, and realm-spray capacity mutants.

## Operational recovery

After restart, durable journals restore terminal/ambiguous state before new
mutations. Non-durable perception/observation queues start with explicit gaps.
Capacity or metric-store failure cannot disable action admission guards.

## Compatibility and rollback

QoS profile identity is transcript-bound. Changing semantics requires a new
profile and explicit session transition, not an in-place configuration edit. The
transcript binds both the realm-independent profile contract digest and the
direct installed `AuthorityRealmKey`. Rollback selects an earlier complete
profile/provider pair in the same realm; moving to another realm is a new
session lineage.

## Open questions

<a id="ncp-b01-selector-allocation-adr-010-v1"></a>

The quality-of-service semantic question is closed by the low-overhead
reconciliation. Measured queue capacities and deadlines remain bounded B03
allocation inputs. No performance or saturation campaign evidence exists.

B03 selects 1 through 32 quality-of-service profile identities that match
`[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?`. The shared outer envelope permits:

- 1 through 65,536 queue items.
- 1 through 1,073,741,824 aggregate bytes.
- 1 through 300,000,000,000 admission nanoseconds.
- 1 through 86,400,000,000,000 retention nanoseconds.
- 1 through 1,025 total attempts.
- 1 through 65,536 consecutive Active transitions while perception is ready.
- 1 through 65,536 pending requests.
- 1 through 300,000,000,000 receiver-local nanoseconds for gap waiting.
- 1 through 300,000,000,000 receiver-local nanoseconds for work resolution.

One total attempt means no retry. Validity requires the plane-specific count,
bytes, scheduler work, terminal state, emergency reserve, and shutdown path fit
their installed endpoint or deployment cap. Deadlines cannot start, refresh, or
extend protocol authority.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: every plane defines ordering, loss, and receipt behavior.
2. Security: overload cannot invoke a permissive path.
3. Safety: fail-safe priority follows the required checks, per-stream allocation,
   and the body-owned event order.
4. Lifecycle: restart, shutdown, ambiguity, and supersession are explicit.
5. Resources: all queues/work are finite and reserved by plane.
6. Migration: portable profiles replace transport-default inference.
7. Science: dropped/missing observations remain visible.
8. Operations: metrics, alarms, tuning, and recovery are specified.
9. Evidence: load, fault, boundary, and duration tests remain mandatory.
10. Governance: profile owners and change rules are registered.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes.
