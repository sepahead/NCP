# ADR-010 — Specify finite per-plane QoS and overload behavior

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
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

One action allocator spans Active, HOLD, and ESTOP attempts so a severity change
cannot bypass sequence/idempotency accounting. Authenticated ESTOP receives
priority only after full envelope, route, actor, session, stream, and semantic
validation; it may omit only the authority lease as separately specified.

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
  "plane": "action",
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
profiles reject.

## Actors and state transitions

Queue entry:

`ADMISSION_CHECK -> RESERVED -> ENQUEUED -> CONSUMED -> DISPOSITIONED`.

Overload:

`ADMISSION_CHECK -> REJECTED_OVERLOAD`.

Ambiguous fail-safe:

`FAIL_SAFE_RESERVED -> OUTCOME_UNKNOWN -> ACTIVE_BLOCKED -> QUERY/OPERATOR
RESOLUTION`.

Observer/extension overload never changes the control/action state machine.

## Bounds and resource behavior

Every queue, journal, retry, timer, frame, batch, subscriber, metric label,
diagnostic, and shutdown wait has a maximum. Memory and CPU reservations for
control/action are independent of observer/extension budgets. Exact profiles are
benchmarked at just-below, exact, and just-above limits.

## Threat and hazard analysis

The decision addresses resource exhaustion, priority inversion, stale action,
fail-safe bypass, observer-induced control blocking, silent data loss, and
shutdown hangs. Rejecting or dropping can still reduce availability and affect a
plant; plant profiles and operators must define the bounded fail posture.

## Formal properties

- No queue grows without bound.
- Extension/observer work cannot consume reserved control/action capacity.
- A lower-severity action cannot pass an unresolved higher-severity attempt.
- Every accepted or rejected mutation has a terminal receipt/query path.
- Gaps are explicit and never replaced with invented observations.

## Migration

N05 implements pure checked queue/transition cores; N06 maps them to transport.
Consumers stop relying on unspecified transport defaults and configure exact
registered profiles.

## Operational recovery

After restart, durable journals restore terminal/ambiguous state before new
mutations. Non-durable perception/observation queues start with explicit gaps.
Capacity or metric-store failure cannot disable action admission guards.

## Compatibility and rollback

QoS profile identity is transcript-bound. Changing semantics requires a new
profile and explicit session transition, not an in-place configuration edit.
Rollback selects an earlier complete profile/provider pair.

## Open questions

Exact numeric capacities and measured deadlines are N05/N06/performance-gate
inputs. The isolation, finiteness, priority, and explicit-loss rules are closed.

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

No qualifying real-time/performance or consumer review is recorded.
