# ADR-007 — Journal body-issued command dispositions

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: plant/safety reviewer, Haldir owner, Crebain owner

## Context

A successful publish or Haldir Gate receipt does not prove that Crebain received,
admitted, applied, rejected, superseded, expired, or failed a command. Commanders
need authenticated body evidence and idempotent query without turning protocol
success into a physical-effect claim.

## Proposed decision

Crebain shall emit a bounded `CommandDisposition` and support
`QueryCommandDisposition`. Each disposition binds:

- plant/body principal and exact plant profile;
- session ID and generation, transcript, and security state;
- command publisher principal, lease term and ID;
- command stream epoch and sequence;
- command payload digest, mode, and applicable operation ID;
- body-local monotonic disposition sequence;
- one closed disposition state;
- software/hardware boundary name and body-local timestamp;
- optional applied-setpoint digest, never raw secret payload by default;
- reason/error code, terminal flag, and prior-state linkage; and
- body signature/authenticated ingress context and receipt digest.

The closed enum states and boundary terminality are:

| State | Boundary terminality |
|---|---|
| `received` | non-terminal |
| `rejected` | terminal |
| `admitted` | non-terminal |
| `applied` | terminal for the named boundary |
| `superseded` | terminal |
| `expired` | terminal |
| `failed` | terminal |
| `unknown_after_boundary` | terminal and never strengthened later |
| `stop_latched` | terminal for the named body-local latch only |

`applied` means only that the named body boundary accepted the command at the
recorded instant. It does not mean the physical plant achieved the requested
state. `stop_latched` proves only that the named body-local stop latch entered;
it does not prove actuator motion, zero energy, hazard removal, or regulatory
safety. `unknown_after_boundary` is terminal for that command and cannot later
be upgraded to `applied`; a new command is required.

The body retains one deterministic terminal answer per exact command identity.
An exact idempotent query returns that answer. A conflicting command digest under
the same identity rejects.

## Rejected alternatives

- Treat publish acknowledgement or Gate receipt as plant execution.
- Let Haldir, Engram, Galadriel, or observers issue dispositions.
- Use free-text success without a closed state.
- Upgrade an ambiguous terminal result after retry.
- Define `applied` as physical goal achievement or safety certification.

## Illustrative wire example

```json
{
  "ncp_version": "1.0",
  "kind": "command_disposition",
  "session_id": "plant-alpha",
  "session_generation": "00000000-0000-4000-8000-0000000000a2",
  "publisher_principal_id": "haldir-commander-a",
  "command_stream": {
    "epoch": "00000000-0000-4000-8000-000000000001",
    "seq": 42
  },
  "command_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "disposition_sequence": 109,
  "state": "applied",
  "boundary": "crebain-flight-controller-input",
  "terminal": true
}
```

## Invalid or hostile example

```json
{
  "ncp_version": "1.0",
  "kind": "command_disposition",
  "state": "physically_safe",
  "terminal": true,
  "issuer_principal_id": "haldir-commander-a"
}
```

Unknown states and non-body issuers reject.

## Actors and state transitions

Typical path:

`NONE -> RECEIVED -> ADMITTED -> APPLIED`.

Other terminal paths:

`RECEIVED -> REJECTED`, `ADMITTED -> SUPERSEDED`,
`ADMITTED -> EXPIRED`, `ADMITTED -> FAILED`, or
`ADMITTED -> UNKNOWN_AFTER_BOUNDARY`. A validated stop command may also end in
`STOP_LATCHED` for the named latch boundary.

Only allowed edges may occur; terminal states do not transition. Disposition
sequence increases strictly within the body journal incarnation.

## Bounds and resource behavior

Journal entries, retention time/bytes, per-command transitions, query size,
subscriber queue, reason length, and body-local work are finite. Journal capacity
is reserved for safety-critical terminal states. Observer backpressure cannot
block disposition creation or plant watchdogs.

## Threat and hazard analysis

This prevents false execution claims, non-body receipt laundering, conflicting
retries, and silent ambiguity. A disposition journal can still be lost,
corrupted, delayed, or unavailable; uncertainty remains explicit. Physical
sensors, actuator feedback, and regulatory safety remain outside this message.

## Formal properties

- Only the authenticated current body can issue a disposition.
- One exact command identity has at most one terminal state.
- `unknown_after_boundary` cannot later strengthen.
- `stop_latched` cannot be interpreted as physical effect or safety
  certification.
- Every disposition references an admitted or rejected command identity exactly.
- Observer failure cannot block body journal progress.

## Migration

Commanders add query/reconciliation logic and stop treating transport success as
execution. Crebain implements the body journal before any consumer role receipt.
Legacy Gate receipts remain Gate-only evidence.

## Operational recovery

After reply loss, query by exact command identity and operation context. If the
journal cannot prove a terminal result, return explicit unknown/retention-expired
failure; never fabricate `applied`. Recovery replays body journal state before
accepting a conflicting identity.

## Compatibility and rollback

This requires the rebaselined core and corresponding body/commander adapters.
Rollback disables the native commander role; it cannot keep execution claims
without dispositions.

## Open questions

Exact boundary registry values and retention minima are B03/N03 inputs. They may
not imply physical achievement or permit terminal strengthening.

## Ten-lens review

1. Semantics: receipt, admission, application, and physical effect are distinct.
2. Security: only the exact body can issue the record.
3. Safety: boundary meaning and limitations are explicit.
4. Lifecycle: terminal and ambiguous outcomes are closed.
5. Resources: journal and queries are finite and priority protected.
6. Migration: commanders reconcile instead of assuming.
7. Science: protocol evidence cannot validate effectiveness.
8. Operations: query, retention, alarms, and recovery are defined.
9. Evidence: crash-boundary and conflicting-retry tests are required.
10. Governance: body owns state/boundary registry and retention policy.

## Ratification record

No qualifying plant/safety, Haldir, or Crebain review is recorded.
