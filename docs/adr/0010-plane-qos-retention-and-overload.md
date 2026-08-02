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

NCP shall define one finite QoS profile per plane and message class. The minimum
semantics are:

| Plane | Queue/retention | Overload behavior |
|---|---|---|
| control RPC | bounded request/reply and idempotency journal | reject before mutation with explicit overload/deadline result |
| action command | capacity one per declared stream plus bounded in-flight receipt state | newest eligible command may supersede only by explicit rule; fail-safe severity has priority; ambiguous fail-safe blocks later Active |
| perception/sensor | bounded latest/history policy declared by stream | explicit gaps/drop counters; never fabricate continuity |
| observation/disposition | bounded priority journal and subscriber queues | body journal cannot block; slow observers gap or detach |
| extension | separate bounded queue and CPU budget | drop/reject with extension-specific gap; never borrow control/action reserve |
| bulk/offline | negotiated bounded transfer/window | throttle or abort without holding real-time resources |

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

One action allocator spans Active, HOLD, and ESTOP attempts so a severity change
cannot bypass sequence/idempotency accounting. ESTOP receives action-queue
priority, admission, and a `stop_latched` disposition only after full envelope,
manifest actor/plane, route, audience, session, stream, and semantic validation;
it may omit only the authority lease as separately specified. ADR-007's distinct
body-local fail-safe side-effect reservation can clear/latch after its exact
minimum current-context gate but before the remaining stream/replay/semantic
checks. That side effect grants no queue entry, command admission, or disposition,
and an ambiguous reservation blocks later Active admission.

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
   cannot enter it. Both lanes still perform complete envelope signature,
   manifest, grant, realm, route, audience, session, stream and semantic
   verification. Only then does the verified severity arbiter order ESTOP, HOLD
   and Active.

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
midpoints, zeros, range endpoints, components, or units. Restrictive attempts
retain ADR-007's separate body-local effect ordering: later codec or profile
semantic failure cannot suppress an already reserved current-context HOLD or
ESTOP effect, and it still grants no queue entry or success disposition.

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

Exact numeric capacities and measured deadlines remain performance-gate inputs. Preallocation, authenticated lane keys, isolation, finiteness, priority, and explicit-loss rules are closed. The performance and saturation campaigns have not been executed.

B03 allocation names and reviewed exclusions are maintained in the [external selector-allocation inventory](selector-allocation.authoring.v1.json) under this stable ADR anchor. That B01 inventory is coordination evidence only. It does not authorize a release or satisfy an external gate.
## Ten-lens review

1. Semantics: every plane defines ordering, loss, and receipt behavior.
2. Security: overload cannot invoke a permissive path.
3. Safety: fail-safe priority follows full validation and one allocator.
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
