# proto

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

The **normative protobuf IDL** for the Neuro-Cybernetic Protocol. `ncp.proto` is the
single source of truth for the NCP message *schema* — message structure, field numbers,
types, and enums — and the cross-language conformance baseline.

It is the **schema contract, not the shipped runtime encoding.** The wire NCP peers
actually exchange today is **JSON** (`serde_json`) on every shipped plane. The
purpose-built binary `BulkBlock` (`ncp-core/src/bulk.rs`) is a bounded local/offline
column codec; a bare block is not a complete observation frame and is rejected by
the Zenoh binding. The protobuf *binary* encoding defined here is a schema/IDL
artifact and a possible future opt-in codec — the prost Rust bindings under `gen/rust/`
are generated but **not** compiled or wired as a runtime path (`gen/` is gitignored and
is not a Cargo workspace member, and `ncp-core` has no `prost` dependency). See
[Schema vs. runtime encoding](#schema-vs-runtime-encoding) below.

In the polyglot NCP SDK (one protocol, peers in Rust/Python/TS/C++) every shipped
representation is generated from the Rust reference projection or checked against
this normative IDL:

- **preview protobuf bindings** (Rust/prost, TS/ts-proto, Python) — generated via
  `buf` (`buf.yaml` / `buf.gen.yaml`) under ignored `gen/`; these are not the
  shipped SDK runtime;
- **JSON Schemas** in `schemas/*.schema.json` — the JSON projection (incl. the enum
  *wire strings* `"V_m"`, `"current_pA"`, …), generated from the Rust reference
  and kept in bidirectional parity with this file;
- **Rust serde types** in `ncp-core/src/messages.rs` — the behavioral reference;
  Python/C wrap it directly and TypeScript types are generated from it with ts-rs.

The shipped JSON runtime is deliberately not compiled from the preview protobuf
bindings. Parity is nevertheless CI-enforced:
`scripts/check_proto_schema_parity.py` (proto ↔ JSON Schema, field/type/cardinality + enum
wire-string), freshly generated-schema diffs, and `ncp-core/tests/conformance.rs`
(Rust serde ↔ JSON Schema + golden vectors).

## Schema vs. runtime encoding

`ncp.proto` answers *what* the messages are; by itself it does not decide *how the bytes
travel*. Keeping those two concerns separate is deliberate:

- **Schema (this file).** Field numbers, types, enums, and their JSON wire-strings are the
  cross-language contract. A Rust, Python, TS, or C++ peer is "NCP-correct" when its
  messages match this schema — independent of which byte encoding it puts on the link.
- **Runtime encoding (what ships today).** The Sensor, Command, RPC, and Observation planes serialize
  with `serde_json` (`ncp-core/src/messages.rs` ↔ `ncp-zenoh/src/lib.rs`). JSON is the default because it is
  human-debuggable and schema-evolution-tolerant (unknown fields are ignored), and —
  measured at ~0.2–0.5 µs to (de)serialize a control frame — negligible against a
  20–1000 Hz control budget where in-sim / NEST compute dominates.

**Why protobuf-binary is the IDL but not the wire.** The prost bindings in `gen/rust/`
are *preview* artifacts that exist to evaluate a proto-native rewire of the polyglot SDK
(see [`gen/README.md`](../gen/README.md)). They are intentionally outside the build:
`gen/` is gitignored, it is not listed in the workspace `members`, and no crate depends on
`prost`. Protobuf binary is therefore best understood as a **negotiated, opt-in encoding**
worth enabling only for a kHz- or bandwidth-constrained consumer — not the current
default. Turning it on would change the *encoding*, never the *schema*, because both the
JSON projection (`schemas/*.schema.json`) and any binary codec derive from this one file.

> **Security note.** `BulkBlock` encode/decode is bounded to 64 MiB, checks all
> narrowing/offset arithmetic, and charges copied names plus numeric columns to a
> cumulative allocation budget. It remains outside the shipped transport until a
> complete, cross-language `BulkObservation` envelope exists.


## The `ncp_version` axis

Every message carries a `kind` string discriminator and an `ncp_version` string
(currently `"0.7"`). Receivers check the **full** `ncp_version`: pre-1.0 the minor is
breaking, so an exact `(major, minor)` match is required and any `0.x` minor difference
is fail-closed rejected — never coerced. Unknown fields are ignored on deserialize
(additive forward-compatibility within a compatible wire version).

## Editing

```bash
# after editing ncp.proto, re-check wire/JSON parity:
python scripts/check_proto_schema_parity.py
```

> ProtoJSON is **not** the NCP JSON wire for enums: canonical protobuf JSON emits an
> enum's constant name (`"V_M"`), but the NCP JSON wire uses the `schemas/` string
> (`"V_m"`). Each enum value annotates its JSON wire string; protobuf-JSON peers MUST map
> through that table. Binary peers use the field number and are unaffected.

See the [NCP specification](../NEURO_CYBERNETIC_PROTOCOL.md) for the normative protocol
description and the [repository README](../README.md) for the SDK overview.

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
