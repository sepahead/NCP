# NCP canonical-JSON Schemas

These draft-2020-12 schemas are the generated JSON projection for the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate. [`index.json`](index.json) lists wire
`1.0`, compact proto hash `163acc57d8a62b66`, and the 14 stable message schemas.

Do not edit `*.schema.json` by hand. Change the Rust reference types and normative
proto together, then regenerate:

```bash
cargo run -p ncp-core --features schema --bin gen-schemas -- schemas
python3 scripts/check_schema_defaults.py
python3 scripts/check_proto_schema_parity.py
```

The generator removes deserialize-only missing-value sentinels, retains only
type-compatible non-authorizing defaults, makes required contract fields explicit,
records closed known enum values, and gives every top-level or nested
`ncp_version` the exact canonical same-major-1 pattern (including the `u64` minor
bound). Semantic validation still applies after schema shape validation; schema
acceptance alone does not prove identity, authorization, operation correlation, or
resource safety.

`ErrorFrame.code` is required and its schema enum is generated from
[`../contract/errors.v1.json`](../contract/errors.v1.json). Missing or unknown error
codes are invalid even when the diagnostic `error` string is non-empty.

Every ingress must first apply the universal budget in
[`../contract/limits.v1.json`](../contract/limits.v1.json). The schemas are included
byte-for-byte in the complete normative digest at
[`../contract/manifest.v1.json`](../contract/manifest.v1.json) and in the candidate
JSON baseline.

See [`../proto/ncp.proto`](../proto/ncp.proto),
[`../NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md), and
[`../conformance/README.md`](../conformance/README.md).
