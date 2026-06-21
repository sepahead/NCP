# conformance

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

Golden **wire vectors** — canonical NCP message instances every language peer must
round-trip. This directory is the cross-language interop contract: a divergence in any
binding's wire handling fails CI here, not in a downstream integration.

NCP is one normative protocol (`proto/ncp.proto`) with peers in Rust, Python, TypeScript,
and C++. `conformance/vectors/` holds one canonical instance per message `kind` plus the
binary bulk-codec block, so every peer can prove it agrees on the *same* bytes.

The corpus has two complementary axes. `vectors/` pins the **wire shape** — do the
peers agree on the same *bytes*. `behavior/` pins **runtime behavior** — do the peers
make the same *decisions* (version accept/reject, advisory contract status, validation,
the safety-governor HOLD/ESTOP/clamp outcomes). A peer can serialize the right bytes and
still mis-decide; the two axes together close that gap.

## What's here

```text
vectors/*.json        one canonical instance per message kind (open_session, capabilities, …)
vectors/*.bin         packed little-endian bulk column block(s) (bulk_observation.bin)
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
- **TypeScript** — the `ncp-ts` peer validates the same vectors against the generated
  schemas (see `ncp-ts/`).

## How the peers consume it (behavior — `behavior/vectors.json`)

- **Rust** — `ncp-core/tests/behavior_conformance.rs` drives every vector through the
  real `ncp_core` functions and asserts the declared outcome, so the corpus can never
  claim a decision the reference does not make. Gates in CI via `cargo test`.
- **Python** — `scripts/check_behavior_vectors.py` replays the identical corpus through
  the `ncp` PyO3 binding (`check_version` / `contract_status` / `validate` / `govern`).
  It skips with exit 0 when the binding is not built (maturin is not yet in CI — see
  `ROADMAP.md`); the Rust half gates regardless.

Run the whole matrix with `scripts/check.sh` (it invokes `check_conformance_vectors.py`
for the wire vectors and `check_behavior_vectors.py` for the behavioral corpus).

## See also

- [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) — the normative spec.
- [repository README](../README.md) — the polyglot SDK and full check matrix.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
