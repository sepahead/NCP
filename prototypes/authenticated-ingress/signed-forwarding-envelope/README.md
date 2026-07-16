# Strict signed-forwarding envelope prototype

> **Quarantine:** this isolated Python project is non-normative, non-shipping,
> forwarding-only, and unable to grant NCP identity, authority, a session, a
> lease, operation success, plant action, certification, or release readiness.
> It does not repair direct Zenoh `production-secure`.

This is prototype B from
[`../../../docs/research/authenticated-ingress-feasibility.md`](../../../docs/research/authenticated-ingress-feasibility.md).
It tests whether an unavoidable carrier can forward one exact signed NCP payload
without inheriting or laundering the operation signer's identity.

## Accepted path

The receiver is configured for one non-negotiable `b-over-a-forwarding` profile:

```text
simulated verified-A carrier context
  -> strict bounded flattened JWS JSON
  -> exact protected and payload base64url strings retained
  -> exact protected algorithm/type/critical-profile members
  -> current exact-byte default-deny Ed25519 key manifest
  -> carrier/signer/route/plane/class/audience/digest congruence
  -> Ed25519 verification over received encoded strings
  -> decoded-payload SHA-256 and relevant NCP semantic binding
  -> one SQLite BEGIN IMMEDIATE conditional high-water upsert
  -> successful FULL-synchronous commit
  -> immutable verified context plus the exact signed payload bytes
```

An A-direct endpoint rejects this verifier. The carrier must have the
transport-local `forwarder` role and must differ from the manifest-enrolled
operation signer at both principal and entity identity. The signer must be an
NCP `commander` with an exact literal grant. Either authentication axis failing
rejects; neither substitutes for the other. The handoff retains both identities,
the carrier role/profile, and the exact stable-core and security-state digests.

The prototype's carrier context is simulated input, not output from a live
prototype-A connection. It proves local congruence logic only, not an end-to-end
B-over-A trusted boundary.

## Exact envelope profile

The outer object contains exactly `protected`, `payload`, and `signature`. The
profile accepts only:

- flattened JWS JSON, never compact, general, detached, or unprotected forms;
- canonical unpadded base64url with exact decode/re-encode equality;
- `alg: "Ed25519"`, never `EdDSA`, `none`, or an attacker-selected verifier;
- `typ: "ncp-forwarding-envelope+jws;v=1"`;
- `crit: ["ncp"]`;
- one content-addressed 32-byte public key from the current manifest; and
- one exact 64-byte signature verified by PyNaCl 1.6.2's libsodium-backed stack.

The protected NCP context binds the literal endpoint, issuer, receiver audience,
stable-core digest, security-state digest, exact key-manifest digest/generation,
key epoch, clock policy and interval, session ID/generation, decoded-payload
digest, and three distinct state families:

1. `forwarding_epoch` plus `forwarding_sequence` are outer-envelope replay state.
2. `payload_stream` mirrors NCP stream epoch/sequence only for streamed messages.
3. `payload_operation` mirrors NCP operation ID, request digest, and expected
   state version only for idempotent operation messages.

This distinction corrects an earlier draft assumption. Current NCP session
generations and stream epochs are canonical UUIDv4s, not positive integer
generations, while operation requests carry `expected_state_version`, not an
invented operation generation.

The executed positive profiles are `command_frame` and `step_request`. The
prototype checks their exact relevant context but is not a complete independent
NCP semantic implementation. Ordinary NCP validation, session, lease,
idempotency, lifecycle, safety, and plant-local admission remain downstream.

## Replay and recovery semantics

Replay state is an owner-only SQLite database with:

- schema and caller-pinned store identity/recovery epoch;
- exact stored schema SQL, not merely familiar table and trigger names;
- `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`,
  `trusted_schema=OFF`, and a 5-second busy timeout verified per connection;
- `BEGIN IMMEDIATE` plus one conditional upsert that cannot lower high water;
- commit success required before the message is handed off;
- 128 retained replay scopes and 8,388,608-byte bounds for the main database and
  each SQLite sidecar at open;
- owner-only directory/file checks, `O_NOFOLLOW`, `fstat`, atomic replacement,
  file and directory `fsync`, and stale sidecar removal;
- a cooperative shared/exclusive advisory lock retained for every open store so
  recovery rejects while another conforming local process is active; and
- fail-closed absence, corruption, schema mismatch, identity mismatch, insecure
  permissions, equal/lower sequence, capacity exhaustion, and SQLite errors.

Commit-before-handoff is deliberately **at-most-once**, not exactly-once. A crash
after commit but before consumer execution loses that handoff and rejects its
retry. The consumer in this prototype is disposable; a real side-effecting
consumer would require a higher-layer operation/idempotency recovery design.

Store initialization or recovery is a separate owner-signed operation. It binds
the old and new store IDs, exact next recovery epoch, audience, schema, clock
policy, and expiry. Initialization requires an absent database path. Recovery
requires a new store ID and rejects a valid store whose externally pinned prior
identity does not match. The recovery epoch is also inside every signed
forwarding envelope. An empty recovered store therefore cannot accept an old
envelope: senders must reissue under the new epoch.

Filesystem snapshot rollback or copying back a structurally valid older database
is not detectable without an external monotonic anchor. `integrity_check` proves
structure, not recency. WAL-aware backup, disk-full behavior, a kill during the
SQLite `COMMIT` call, multi-instance storage, owner-key custody, and durable
external storage of the pinned state remain unproved.

## Bounds and verification

The strict preflight parser validates UTF-8, BOM absence, escapes and surrogate
pairs, depth, width, nodes, string sizes, number grammar, safe integers, and one
complete JSON value before semantic allocation. Duplicate object names reject
during the bounded parse. Current byte limits are:

| Boundary | Limit |
| --- | ---: |
| outer envelope | 1,500,000 |
| decoded protected header | 16,384 |
| decoded NCP payload | 1,048,576 |
| key manifest | 65,536 |
| replay database at open | 8,388,608 |
| each replay sidecar at open | 8,388,608 |

Run:

```bash
./run.sh
```

The runner checks the exact uv lock, dependency hashes, source invariants,
formatting, security-focused Ruff rules, compilation, twenty-three tests, and a
machine-local live result. Tests cover syntax/encoding/numeric ambiguity,
algorithm and remote-key substitution, signature mutation and noncanonical
Ed25519 scalar, small-order key rejection, manifest failures, carrier/signer and
route confusion, direct/forwarding exclusivity, both NCP contexts, key
rotation/removal, duplicate/lower replay, concurrent processes, restart,
capacity, corrupt or substituted schema SQL, main/sidecar bounds, permissions,
initialization overwrite, active-process recovery, signed recovery, and crashes
immediately before and after commit.

See [`SECTION_REVIEW.md`](SECTION_REVIEW.md) for the assumption challenge,
three-lens decision, evidence limits, and next permitted work.
