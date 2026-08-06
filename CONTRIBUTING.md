# Contributing to NCP

Repository HEAD is the unreleased and release-blocked NCP `1.0.0-rc.1` candidate.
Its wire is `1.0`. Its compact proto hash is `163acc57d8a62b66`.

The latest immutable release is `v0.8.0`. It uses a different wire.

Contributions are welcome under the
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Before you start

Read these files first:

- [`AGENTS.md`](AGENTS.md)
- [`DOCUMENTATION_STYLE.md`](DOCUMENTATION_STYLE.md)
- [`NEURO_CYBERNETIC_PROTOCOL.md`](NEURO_CYBERNETIC_PROTOCOL.md)
- [`SECURITY.md`](SECURITY.md)
- [`RELEASE_READINESS.md`](RELEASE_READINESS.md)

For an NCP 1.0 implementation task, also read the generated resumption brief and
task ledger. Then read the complete finalization blueprint.

Start only a dependency-ready task. Preserve unrelated work in each repository.

## Contract changes

[`contract/manifest.v1.json`](contract/manifest.v1.json) generates the normative
precedence and exact source set.

Open an issue or design record before a semantic change. Identify each affected
message, field, schema, limit, registry, transition, package, transport, consumer,
migration, and claim.

A complete wire change can require updates to these items:

- registries and normative prose
- `proto/ncp.proto`, including reserved names and numbers
- Rust reference types and semantic validation
- generated JSON Schemas and TypeScript outputs
- canonical, behavior, limit, and migration vectors
- conformance and contract manifests
- Python, C, and C++ fixtures
- package-local test data
- the compact proto hash
- the candidate baseline
- the changelog and integration guide
- each affected current document

Change the source before you run its generator. Do not hand-edit a generated file.

Do not add an optimistic default or consumer-specific branch. Do not weaken a
resource, security, or safety guard.

An unknown value must not authorize an operation. Do not mark an experimental
feature as stable by implication.

## Documentation changes

Use the STE-aligned profile in
[`DOCUMENTATION_STYLE.md`](DOCUMENTATION_STYLE.md). Preserve exact normative terms
and historical values.

Do not rewrite generated files or frozen history only to change their style. Run
the link checker and inspect the rendered document.

## Build and test

Run focused tests during development. Then run the complete local matrix.

```bash
cargo fmt --all -- --check
cargo test -p ncp-core --all-features
bun run regen
bun run check:behavior
python3 scripts/generate_conformance_manifest.py
python3 scripts/generate_contract_manifest.py
scripts/check.sh
```

`scripts/check.sh` requires Rust 1.88 or later, Python 3.11 or later, C++17,
Node.js 18+, Bun, npm, Buf, and `cargo-deny` 0.19.9. It invokes both Bun and npm.

Treat a missing required tool or a skipped applicable vector as a failure.

## Evidence and claims

Add the valid, malformed, boundary, stale, replay, restart, concurrency, and
resource tests that apply to the change.

Keep exact source, toolchain, configuration, environment, and artifact identities
for an evidence campaign.

Local tests do not close a live-security, independent-peer, fault, soak, fuzz,
sanitizer, performance, supply chain, clean-room, publication, or consumer gate.

Keep each unexecuted gate at **NOT RUN**. Model-generated review is optional advice.
It is not certification.

Simulation output is not a paper reproduction or a calibrated posterior. Protocol
ESTOP is not a certified physical emergency stop. The body and consumer safety
case remain final.

## Pull requests and commits

Keep each change small enough for a complete review. Explain the failure or gap
that the change closes.

Add a characterization test before an accept-path change when practical. Add a
positive test before a new fail-closed path when practical.

Include the exact commands and results. List each gate that remains **NOT RUN**.

Preserve unrelated work and historical wire-0.8 documents. Engram's native-1.0
migration remains in progress. Copied candidate files do not complete or certify
that migration.

Use one professional commit for one coherent passing part. Push it to the
authorized branch. Verify the remote object after the push.

Contributions use the dual MIT or Apache-2.0 license unless a file states another
license.
