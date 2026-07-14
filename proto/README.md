# NCP protobuf IDL

[`ncp.proto`](ncp.proto) is the normative field-number, message-shape, enum, and
annotation IDL for the unreleased NCP `1.0.0-rc.1` candidate. The runtime stable
encoding is canonical JSON; protobuf binary is excluded from stable 1.0.

The file declares package `ncp.v1`, wire `1.0`, and enough structured annotations
to map protobuf enum names and lifecycle RPCs to the canonical JSON wire. The compact
`CONTRACT_HASH` (`163acc57d8a62b66`) is FNV-1a over its canonicalized semantic
structure. The complete normative SHA-256 digest additionally covers registries,
schemas, prose, limits, security profiles, and conformance, and is generated in
[`../contract/manifest.v1.json`](../contract/manifest.v1.json).

Preview code generation under ignored `gen/` is tooling only. No runtime crate
depends on prost and no peer may advertise protobuf as a stable transport encoding.
`ErrorFrame.code` is the required canonical-JSON classification projected at
additive protobuf field 8; its accepted values remain closed by the error registry.

After any semantic edit, update the compact hash and all projections/vectors, then
run:

```bash
python3 scripts/check_proto_schema_parity.py
python3 scripts/check_conformance_vectors.py
python3 scripts/check_buf_breaking.py
buf lint
buf build
```

Unknown JSON fields are handled under the bounded extension policy, but unknown
closed security/authority/capability values never authorize an operation. See
[`../NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) for semantics
and [`../VERSIONING.md`](../VERSIONING.md) for compatibility.

Licensed under either [MIT](../LICENSE-MIT) or
[Apache-2.0](../LICENSE-APACHE).
