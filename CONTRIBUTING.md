# Contributing to NCP

Repository HEAD is the unreleased, release-blocked NCP `1.0.0-rc.1` candidate
(wire `1.0`, compact proto hash `163acc57d8a62b66`). The latest immutable annotated
source tag is `v0.8.0` and is wire-incompatible. Contributions are welcome under the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

Read [`AGENTS.md`](AGENTS.md),
[`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md),
[`SECURITY.md`](SECURITY.md), and
[`RELEASE_READINESS.md`](RELEASE_READINESS.md) first.

## Contract changes

The normative precedence and exact source set are generated in
[`contract/manifest.v1.json`](contract/manifest.v1.json). Open an issue/design note
for any semantic change and identify affected messages, field numbers, schemas,
limits, registries, state transitions, packages, transports, persisted data,
consumers, migration, and claims.

A complete wire change updates, in one review:

- registries and normative prose;
- `proto/ncp.proto` with reserved numbers/names as needed;
- Rust reference types and semantic validation;
- generated JSON Schemas and TypeScript declarations/dist;
- canonical, behavior, limit, and migration vectors;
- mandatory conformance and complete contract manifests;
- Python/C/C++ binding fixtures and package-local testdata;
- compact proto hash, candidate baseline, changelog, integration guide, and every
  affected current document.

Never hand-edit generated artifacts, add an optimistic default, branch on a
consumer, weaken a resource/security/safety guard, or label an experimental feature
stable by implication. Unknown values cannot authorize action.

## Build and test

Use focused tests during development, then run the complete local matrix:

```bash
cargo fmt --all -- --check
cargo test -p ncp-core --all-features
bun run regen
bun run check:behavior
python3 scripts/generate_conformance_manifest.py
python3 scripts/generate_contract_manifest.py
scripts/check.sh
```

`scripts/check.sh` requires Rust 1.88+, Python 3, C++17, Bun/npm, Buf, and
`cargo-deny`. Missing required tools or skipped applicable vectors are failures.

## Evidence and claims

Tests must include valid, malformed, boundary, stale/replay, identity/plane,
interruption/restart, concurrency, and resource cases appropriate to the change.
Retain exact source/toolchain/config/environment digests for campaigns.

Local green tests do not close live security, independent-peer, fault/soak,
fuzz/sanitizer, performance, supply-chain, clean-room, publication, or consumer
gates. Mark them **NOT RUN** until exact evidence exists. Model-generated review is
optional advice and never certification.

Scientific and physical-safety boundaries are binding: simulation output is not a
paper reproduction or calibrated posterior; protocol ESTOP is not a certified
physical emergency stop; the body and consumer safety case remain final.

## Pull requests

Keep changes reviewable, explain the failure being closed, add characterization
before implementation where practical, and include commands/results plus explicit
not-run gates. Preserve unrelated work and historical 0.8 documents. Engram's
native-1.0 migration is explicit and in progress; never copy candidate files alone
and call that a complete or certified migration.

Contributions are accepted under the repository's dual MIT/Apache-2.0 license unless
explicitly stated otherwise.
