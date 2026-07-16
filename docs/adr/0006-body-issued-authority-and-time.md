# ADR-006 — Use body-issued authority and receiver-local time

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
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
plant identity
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

If body restart preserves an exact authenticated snapshot, it restores into
`RECONNECTING` or `HOLD`, never directly `ACTIVE`; only the exact unexpired holder
may prove continuity. If snapshot continuity is unavailable or ambiguous, the
body retires the session generation and opens a fresh opaque UUIDv4 generation.
Old generations reject by inequality; no generation ordering is inferred.

## Rejected alternatives

- Last-writer-wins action topics.
- Commander-issued or payload-self-asserted leases.
- A configuration toggle between direct and gated modes.
- Wall-clock expiry as the only restart fence.
- A fourth ambiguous authority epoch.
- Lexicographic comparison of UUID epochs.
- Granting a new lease before old command admission and quiescence are closed.

## Illustrative wire example

```json
{
  "session_epoch": "00000000-0000-4000-8000-0000000000a2",
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
  "session_epoch": "00000000-0000-4000-8000-0000000000a2",
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

`INIT/HOLD_NO_LEASE -> ACQUIRING -> ACTIVE(term n) -> RENEWING ->
ACTIVE(term n, same lease identity)`.

Transfer:

`ACTIVE(A,n) -> TRANSFER_REQUESTED -> HOLD_QUIESCING -> REVOKED(A,n) ->
GRANTING(B,n+1) -> ACTIVE(B,n+1)`.

Expiry or uncertainty:

`ACTIVE -> HOLD`. ESTOP:

`ANY_NON_RETIRED -> ESTOP_LATCHED -> OPERATOR_RESET -> SESSION_RETIRED`.

## Bounds and resource behavior

Lease duration, clock uncertainty, operation deadline, transfer time, HOLD
quiescence, in-flight commands, receipt journal, term range, retries, and query
work are finite. Resource exhaustion fails to HOLD/deny and never creates a
holder.

## Threat and hazard analysis

This addresses split brain, stale delayed commands, self-issued authority,
handover overlap, restart revival, lease replay, and wall-clock manipulation.
HOLD is a protocol lifecycle state whose actual actuator behavior is defined by
the content-addressed plant profile. It is not universally zero-safe or physical
certification. A transfer can create availability loss and must declare its
bounded fail posture.

## Formal properties

- At most one live holder exists for a plant/session generation.
- Every admitted action command matches the exact current fence.
- Renewal preserves the exact term/lease/issuer/holder identity and cannot revive
  an expired lease.
- A revoked, expired, old-generation, old-term, old-lease, old-holder, or retired
  stream command is never admitted.
- No transfer makes the new holder live before old admission is closed and the
  required quiescence boundary is reached.
- Restart never restores `ACTIVE` without exact continuity proof.

TLA+/state-machine tests shall include delay, duplication, partition, crash at
every transfer boundary, storage uncertainty, deadline equality, and two
commanders.

## Migration

Haldir and Engram commander adapters become clients of Crebain-issued authority.
Haldir decisions remain local permission evidence; they do not become leases.
Legacy authority copies and first-publisher adoption are removed from native
paths.

## Operational recovery

Ambiguous mutation outcomes are queried by operation ID. Lost or corrupt
authority state fails to HOLD and retires the generation if exact continuity
cannot be established. Operators may preempt only through enrolled override
authority and receipted body operations.

## Compatibility and rollback

The new lifecycle requires a complete provider/commander/body migration.
Rollback restores the prior disabled candidate and cannot retain a new commander
against an old body.

## Open questions

Plant-profile-specific HOLD/quiescence bounds and durable-store technology are
deployment inputs. They cannot weaken body serialization, exact fencing, or
receiver-local expiry.

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

No qualifying safety, distributed-systems, Haldir, or Crebain review is recorded.
