# conformance

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

Golden **conformance vectors** — canonical JSON wire messages every language peer
must round-trip, plus one bounded local/offline bulk-codec fixture. This directory
is the cross-language interop contract: a divergence in any binding's JSON handling
or runtime decisions fails CI here, not in a downstream integration.

NCP is one normative protocol (`proto/ncp.proto`) with peers in Rust, Python,
TypeScript, and C++. `conformance/vectors/` holds one canonical JSON instance per
message `kind`, so every peer can prove it agrees on the same wire shape. The binary
fixture separately pins `BulkBlock`'s local codec; it is not a transported
`BulkObservation` envelope and does not imply binary support in every SDK.

The corpus has two complementary axes. `vectors/` pins the **JSON wire shape** (and
the separate local bulk-codec fixture). `behavior/` pins **runtime behavior** — do the peers
make the same *decisions* (version accept/reject, advisory contract status, validation,
the safety-governor HOLD/ESTOP/clamp outcomes). A peer can serialize the right bytes and
still mis-decide; the two axes together close that gap.

## What's here

```text
vectors/*.json        one canonical instance per message kind (open_session, capabilities, …)
vectors/*.bin         local/offline packed bulk-codec fixture; not a transported frame
behavior/vectors.json language-neutral {function, input, expect} decision vectors
```

## How the peers consume it (wire shape — `vectors/`)

- **Python** — `scripts/check_conformance_vectors.py` validates every `*.json` against
  the schema for its `kind` (field-set + required + enum, resolving local `$ref`/`$defs`)
  and decodes each `*.bin` against its expected columns. Stdlib-only; also gates corpus
  coverage (every schema `kind` must have a vector).
- **C++** — `ncp-cpp/tests/corpus.rs` drives every `*.json` through the C ABI
  `ncp_validate` and asserts accept/reject parity.
- **Rust** — `ncp-core/tests/conformance.rs` guards serde `<->` JSON Schema field-set
  parity type-side; the Rust bulk encoder is byte-pinned to the committed `*.bin`
  (`bulk::tests::matches_committed_golden_vector`).
- **TypeScript** — `ncp-ts/scripts/check-behavior.mjs` drives every JSON fixture
  through the shipped `assertNcpMessage` ingress gate (and the specialized
  data-plane gate where applicable).

## How the peers consume it (behavior — `behavior/vectors.json`)

All four SDK peers replay the SAME corpus, so a divergence in any one peer's decision
logic fails CI here:

- **Rust** — `ncp-core/tests/behavior_conformance.rs` drives every vector through the
  real `ncp_core` functions and asserts the declared outcome, so the corpus can never
  claim a decision the reference does not make. Gates in CI via `cargo test`.
- **C++** — `ncp-cpp/tests/behavior_corpus.rs` drives the full corpus through the C ABI
  (`ncp_check_version` / `ncp_contract_status` / `ncp_validate` / `ncp_govern`). Gates
  in CI via `cargo test`.
- **Python** — `scripts/check_behavior_vectors.py` replays the identical corpus through
  the `ncp` PyO3 binding. The dedicated CI job builds/imports the maturin wheel and runs
  with `NCP_REQUIRE_BINDING=1`, so a missing binding cannot skip as pass.
- **TypeScript** — `ncp-ts/scripts/check-behavior.mjs` now replays the **full `govern`
  corpus** (via the new `safety.ts` port — `SafetyGovernor`/`CommandWatchdog`/`ActionBuffer`)
  alongside `checkVersion`, `contractStatus`, full `validate` parity through
  `assertNcpMessage`, the scientific-boundary discriminators, and seq/ttl/latch ingress checks.
  Gates in the `ts-dist` CI job.

Run the whole matrix with `scripts/check.sh` (it invokes `check_conformance_vectors.py`
for the wire vectors and `check_behavior_vectors.py` for the behavioral corpus).

## See also

- [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) — the normative spec.
- [repository README](../README.md) — the polyglot SDK and full check matrix.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
