# NCP JSON Schemas

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

JSON-Schema (draft 2020-12) mirrors of the NCP message types — the **JSON projection** of the
normative protocol, used to validate the JSON transport and the conformance corpus.

NCP is one normative protocol with peers in Rust (`ncp-core`), Python (`ncp-python`), TypeScript
(`ncp-ts`), and C++ (`ncp-cpp`). The wire contract lives in [`proto/ncp.proto`](../proto/ncp.proto);
the schemas here are one of the three wire projections (Rust serde / JSON Schema / protobuf) that a
parity guard keeps from drifting apart.

## Source of truth & regeneration (IMPORTANT)

These files are **generated, not hand-edited**. Today they are emitted from the engram
Pydantic models via `backend/neurocontrol/export_schemas.py` and re-vendored here; a
drift guard checks the committed copy against a fresh export. NCP also ships its own
**proto-first** generator — `cargo run -p ncp-core --features schema --bin gen-schemas`
derives the schemas directly from the `ncp-core` serde reference types (the
conformance-locked reference implementation, which carry the enum wire strings) — and a
**schema-default safety guard** (`scripts/check_schema_defaults.py`) asserts every
committed field DEFAULT matches that Rust reference (it caught `CommandFrame.mode`
defaulting to the actuating `"active"` instead of the fail-safe `"hold"`). The full
cutover to NCP-owned generation (replacing the committed schemas, adapting the
parity/conformance guards to the schemars shape, migrating engram to a pure consumer)
is staged; until then the Pydantic export is the transitional source and the default
guard bridges the two.

Do not edit a `*.schema.json` by hand — regenerate and commit the result.
[`index.json`](index.json) lists the message set (`ncp_version` `0.4`): `capabilities`,
`open_session` / `session_opened`, `close_session` / `session_closed`, `run_request`,
`step_request`, `sensor_frame` / `stimulus_frame` / `observation_frame` / `command_frame`,
`control_status`, `link_status`.

## Drift guards

- [`scripts/check_proto_schema_parity.py`](../scripts/check_proto_schema_parity.py) — field-set and
  enum wire-string parity between `proto/ncp.proto` and `schemas/*.schema.json`.
- `ncp-core/tests/conformance.rs` — guards the Rust serde types against these schemas.

## See also

- [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) — the human-readable spec.
- [`proto/ncp.proto`](../proto/ncp.proto) — the normative wire contract.
- [repository README](../README.md) — the full SDK overview.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
