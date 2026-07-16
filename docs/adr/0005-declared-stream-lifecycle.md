# ADR-005 — Declare and retire every stream explicitly

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: distributed-systems reviewer and all stream consumer owners

## Context

NCP frames carry a stream epoch and sequence, but the current stable contract does
not establish an authenticated declaration operation. Some consumer code can
adopt a first frame or silently mint a fresh epoch at sequence exhaustion. That
lets traffic create authorization state and contradicts the rule that exhausted
publishers stop until redeclared.

## Proposed decision

Every streamed plane shall use explicit authenticated operations:

- `DeclareStream` establishes one stream incarnation;
- `StreamDeclared` returns the receiver-issued declaration receipt;
- `RetireStream` permanently closes the incarnation;
- `RedeclareStream` creates a fresh opaque UUIDv4 epoch after retirement,
  restart, publisher change, schema change, or exhaustion.

A declaration binds exact publisher principal/entity, session ID and generation,
plane, literal route, message class, opaque stream epoch, starting sequence,
channel/schema selection, transcript, security state, audience, QoS profile,
operation context, and declaration digest.

`StreamPosition.epoch` is an opaque canonical UUIDv4 compared for equality only.
It is never ordered, incremented, or replaced with `0`. Sequence starts at `1`,
increases strictly within the declared epoch, and remains in the JSON-safe range.

Frames cannot create, rotate, widen, or revive a stream. Sequence exhaustion
makes the publisher silent. Reconnect, HOLD, lease expiry, or a quiet period does
not reset the receiver's high-water mark.

Plane declarations are non-fungible. A perception declaration does not authorize
action publication, and an observer grant does not authorize any declaration.

## Rejected alternatives

- Adopt the first valid frame's epoch.
- Rotate automatically at sequence maximum.
- Treat epoch UUIDs as ordered counters or timestamps.
- Reset high water after timeout, reconnect, or HOLD.
- Share one epoch across different publishers, planes, routes, or message kinds.

## Illustrative wire example

```json
{
  "ncp_version": "1.0",
  "kind": "declare_stream",
  "session_id": "plant-alpha",
  "session_generation": "00000000-0000-4000-8000-0000000000a2",
  "plane": "action",
  "route": "realm/session/plant-alpha/command/controller-a",
  "message_class": "command_frame",
  "stream_epoch": "00000000-0000-4000-8000-000000000001",
  "sequence_start": 1,
  "publisher_principal_id": "haldir-commander-a"
}
```

## Invalid or hostile example

```json
{
  "ncp_version": "1.0",
  "kind": "command_frame",
  "stream": {
    "epoch": "00000000-0000-4000-8000-000000000099",
    "seq": 1
  },
  "session": {
    "generation": "00000000-0000-4000-8000-0000000000a2"
  }
}
```

The frame rejects when no exact live declaration exists, even if its syntax and
session generation are otherwise valid.

## Actors and state transitions

`ABSENT -> DECLARING -> LIVE -> RETIRING -> RETIRED`.

Exhaustion, publisher change, security-state change, session retirement, schema
change, or explicit revoke moves to `RETIRED`. A fresh declaration uses a new
epoch and starts at sequence `1`. A retired epoch never returns to `LIVE`.

## Bounds and resource behavior

Declaration bytes, streams per session/principal/plane, channels, schema size,
route length, high-water entries, retirement tombstones, duplicate retention,
and operation retries are finite. Capacity exhaustion rejects declaration before
allocating publisher state.

## Threat and hazard analysis

This prevents first-frame authority, epoch injection, replay after quiet periods,
silent rollover, cross-plane use, and unbounded high-water state. State loss can
cause denial; it must not cause acceptance. Durable storage rollback and
multi-instance ownership require external design and testing.

## Formal properties

- Every accepted frame maps to exactly one live declaration.
- Sequence for an epoch is strictly increasing and never wraps.
- Retired epochs are never accepted again.
- No frame changes declaration state.
- Plane, route, class, session, publisher, and security context match exactly.

## Migration

Publishers add declare/retire operations before emitting native frames. Existing
implicit-adoption helpers are deleted or confined to labelled legacy gateways.
Consumers persist high water and explicit gaps.

## Operational recovery

If declaration state cannot be proven current after restart, the receiver rejects
frames and requires an authenticated redeclaration. A publisher never guesses
whether a prior declaration committed; it queries by idempotency context.

## Compatibility and rollback

This is a pre-release wire/lifecycle correction. Rollback disables the new native
session as a whole; it cannot keep new frames with old implicit adoption.

## Open questions

Exact declaration RPC names and tombstone retention durations are B03/N03 inputs.
They cannot weaken explicit declaration, equality-only epoch semantics, or
exhaustion silence.

## Ten-lens review

1. Semantics: stream creation is an operation, not a frame side effect.
2. Security: publisher, route, plane, class, and session bind exactly.
3. Safety: stale action streams cannot revive.
4. Lifecycle: restart, exhaustion, retire, and redeclare are explicit.
5. Resources: state and tombstones are finite.
6. Migration: gateways label legacy implicit behavior.
7. Science: observation gaps remain exact.
8. Operations: publishers can query ambiguous declarations and recover.
9. Evidence: reorder, replay, exhaustion, restart, and cross-plane vectors run.
10. Governance: stream schema and publisher ownership are registered.

## Ratification record

No qualifying distributed-systems or consumer-owner review is recorded.
