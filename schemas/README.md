# NCP JSON Schemas

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

JSON-Schema (draft 2020-12) mirrors of the NCP message types — the **JSON projection** of the
normative protocol, used to validate the JSON transport and the conformance corpus.

NCP is one normative protocol with peers in Rust (`ncp-core`), Python (`ncp-python`), TypeScript
(`ncp-ts`), and C++ (`ncp-cpp`). The wire contract lives in [`proto/ncp.proto`](../proto/ncp.proto);
the schemas here are one of the three contract projections (Rust serde / JSON Schema / protobuf) that a
parity guard keeps from drifting apart.

## Source of truth & regeneration (IMPORTANT)

These files are **generated, not hand-edited**, and **NCP owns their generation**
(proto-first): `cargo run -p ncp-core --features schema --bin gen-schemas` derives them
directly from the `ncp-core` serde reference types — the conformance-locked reference
implementation of `proto/ncp.proto`, which carries the enum wire strings
(`#[serde(rename)]`), legitimate optional defaults, `kind` discriminator consts, and
the `required_fields` validation contract. Deserialize-only missing-field sentinels
are stripped: required/const fields do not advertise defaults, and every retained
default is type-compatible. CI **regenerates and diffs** the schemas on every run,
while `scripts/check_schema_defaults.py` independently pins these invariants and the
fail-closed `CommandFrame.mode = "hold"` default.

Downstream consumers (e.g. engram) are pure **consumers** of these schemas: they validate
their own representations *against* this projection, they do not produce it. (Engram's
`test_schema_drift` checks its Pydantic models stay field-compatible with the vendored
copy.)

Do not edit a `*.schema.json` by hand — run `gen-schemas` and commit the result.
[`index.json`](index.json) lists the v0.7.1 release's message set
(`ncp_version` `0.7`): `capabilities`,
`open_session` / `session_opened`, `close_session` / `session_closed`, `run_request`,
`step_request`, `sensor_frame` / `stimulus_frame` / `observation_frame` / `command_frame`,
`control_status`, `link_status`, and the typed RPC `error` frame.

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
