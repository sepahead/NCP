# Wire-0.8 capture migration validator

> **Candidate status:** this is repository-owned validation tooling for the
> unreleased, release-blocked `1.0.0-rc.1` candidate. It does not translate a
> capture, certify a peer, or release wire 1.0. The immutable `v0.8.0` wire remains
> a different contract with compact hash `d1b50a2d8a265276`.

The validator answers one narrow question: does a complete, ordered wire-0.8
capture limited to capabilities, the lifecycle open exchange, sensor data, and
observations contain enough explicit legacy evidence to check units, coordinate
frames, session lineage, publisher restart boundaries and high-water state,
authority applicability, and simulation epistemic status without choosing a default? An
accepted report is validation-only. It emits no target records and sets every
security, authority, safety, scientific-upgrade, and release-certification claim to
`false`.

## Current behavior and claim boundary

| Concern | Input and state | Accepted result | Rejection |
|---|---|---|---|
| envelope/resources | one duplicate-free JSON document, at most 1 MiB and 4096 ordered records | exact schema and explicit nullable metadata | bounded `NCP-LIMIT-*` error or `envelope` gap |
| contract identity | header and every payload | exact wire `0.8`; open/opened hash `d1b50a2d8a265276` | `contract_identity` gap |
| units | one preceding capabilities record plus every captured channel/observation scalar | explicit string or explicit `null`, exact declaration/name/arity/type/parallel-array match | `unit` gap; no inherited, guessed, or malformed unit/value |
| frames | every sensor frame | explicit bounded, non-empty `frame_id` | `frame` gap; no implicit `world` |
| session lineage | ordered open/opened records and redundant per-record metadata | one exact realm, `(session_id, generation, session_opened_index)`, frozen route grammar, and request/provenance agreement | `session_lineage` gap; cross-realm, stale, contradictory, and missing outcomes reject |
| restart/high-water | global process-incarnation and epoch fences plus non-evicting per-stream state | one active incarnation per publisher ID, globally unique epochs, sequence 1 at declaration/restart, then contiguous sequence | `stream_continuity` gap for replay, reorder, gaps, collisions, retired incarnations, or partial prefixes |
| authority applicability | record kind | no authority-requiring post-open operation or action record; accepted `open_session`/`session_opened` lifecycle traffic is not described as passive | authority-bearing records reject; `control_status` also rejects because frozen 0.8 defines no transport key for it |
| epistemic status | explicit open simulation request, session provenance, and observation records | requested seed agrees when specified; `calibrated_posterior=false`, `is_simulation_output=true`, and `advisory_only=true` where applicable | `epistemic_status` gap |
| output | accepted source bytes and current validator identity | deterministic report with source SHA-256, scalar counts, package/build identity, compact target hash, and full target normative digest | no wire-1.0 artifact is emitted |

`publisher_id` and `publisher_incarnation` are capture correlation metadata. They
do not authenticate a publisher. The validator cannot recover transport identity,
signatures, leases, operation receipts, plant evidence, or missing packets from old
bytes. Those are nonclaims, not fields to fill after the fact.

## Validator requirements

- **NCP-MIG-CAP-001 — bounded exact envelope.** The validator SHALL apply the
  universal duplicate/resource preflight before semantic allocation. The capture
  and every record SHALL carry their exact required fields; nullable correlation
  fields SHALL appear as `null`, not disappear into a decoder default.
- **NCP-MIG-CAP-002 — frozen declared contract identity.** The source SHALL declare
  wire `0.8` and the immutable compact hash. A correct version with another hash
  SHALL reject. Matching declarations do not authenticate capture origin.
- **NCP-MIG-CAP-003 — explicit units and arity.** Capabilities and values SHALL
  agree exactly on channel name, kind, size, requirement boolean, and unit. Missing,
  unknown, contradictory, or undeclared values SHALL reject.
- **NCP-MIG-CAP-004 — explicit frames.** A spatial sensor record SHALL carry a
  non-empty bounded coordinate frame. The validator SHALL NOT supply `world` for a
  missing field.
- **NCP-MIG-CAP-005 — complete session lineage.** Every successful opening SHALL
  follow one unresolved open request. Every post-open record SHALL bind the exact
  opening index, logical session ID, live generation, one exact realm, and frozen
  concrete-route grammar. Open request shapes and successful provenance SHALL
  agree on network reference and any explicitly requested seed. A new opening
  retires the prior generation; delayed old records SHALL reject.
- **NCP-MIG-CAP-006 — crash/restart fence.** Capture indexes SHALL be contiguous.
  The first position for a complete stream SHALL be sequence 1. Within a publisher
  incarnation the epoch SHALL remain fixed and sequences SHALL advance by one. A
  publisher-incarnation change SHALL retire that process globally and use a
  never-seen epoch and sequence 1. Epochs SHALL be globally unique because the
  wire-0.8 source position carries no publisher ID. Retired incarnations and epochs
  SHALL remain rejected for the rest of validation.
- **NCP-MIG-CAP-007 — source correlation.** Observation-plane source positions
  SHALL identify a preceding captured sensor position in the same session
  generation and exact source timestamp. A reordered, future, cross-generation,
  cross-realm, colliding, missing, or timestamp-contradictory source SHALL reject.
- **NCP-MIG-CAP-008 — no authority synthesis.** Because wire 0.8 did not carry the
  1.0 lease and idempotent-operation evidence, authority-requiring legacy records
  SHALL reject. `control_status` SHALL also reject because the frozen wire-0.8
  transport grammar has no status route from which to reconstruct its provenance.
  No sidecar default can convert those records into authorized 1.0 actions.
- **NCP-MIG-CAP-009 — epistemic honesty.** Simulation provenance SHALL retain the
  exact negative calibration and positive simulation discriminators. Absence,
  contradiction, or optimistic replacement SHALL reject.
- **NCP-MIG-CAP-010 — validation-only receipt.** An accepted report SHALL contain
  the source-byte SHA-256, checked scalar counts, validator package/build identity,
  compact target hash, and complete target normative digest, SHALL set
  `target_artifact_emitted=false`, and SHALL keep all upgrade/certification fields
  false.

The canonical positive fixture at
`conformance/migration/v0.8-to-v1.0/wire-0.8-reconstructable-capture.json` is
generator-synchronized into `ncp-core/testdata/migration/` so the retained crate
archive is self-contained. It begins at capabilities/open, exercises a successful
session, multiple sensor and observation streams, publisher-process restarts with
fresh globally unique epochs, and a second session generation. Mutation tests
remove or contradict each required axis, cross realms, routes, sessions, and
publishers, replay retired state, reorder source evidence, skip high-water
positions, collide or reuse an epoch after restart, contradict source timestamps or
requested seeds, malform nested network/record/stimulus/binding shapes, alter the
frozen hash, add defaults, and exceed JSON bounds.

## Capture envelope and command

Each record has this strict metadata shape:

```json
{
  "capture_index": 4,
  "route": "ncp/session/capture-session/sensor/pose",
  "route_session_id": "capture-session",
  "publisher_id": "sensor",
  "publisher_incarnation": "44444444-4444-4444-8444-444444444444",
  "session_opened_index": 3,
  "payload": {"ncp_version": "0.8", "kind": "sensor_frame"}
}
```

Run the local validator with:

```bash
cargo run -p ncp-core --bin validate-wire-08-capture -- \
  ncp-core/testdata/migration/wire-0.8-reconstructable-capture.json
```

A zero exit status means only that this implementation accepted the bounded local
document. Multi-process crash injection, real transport capture loss, hostile live
peers, duration fault/soak, cross-language installed-artifact replay, signatures,
and clean-room reproduction remain **NOT RUN** until retained external evidence
exists.
