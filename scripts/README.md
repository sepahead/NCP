# scripts

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

Maintenance and ops scripts for the **NCP** workspace — the local conformance gate,
the cross-consumer pin tooling, and the NEST/transport micro-benchmarks. NCP is a
polyglot SDK around **one** normative wire contract with peers in Rust, Python, C/C++,
and TypeScript; these scripts keep that contract checkable and its consumers in sync.

These are operator tools, not part of the published SDK. Run them from anywhere — each
resolves the repo root from its own location.

## Index

| Script | What it does |
|---|---|
| `check.sh` | Complete local release gate: format/clippy, locked Rust workspace tests, real C++ ABI demo, an isolated maturin-built Python wheel with required behavior/smoke tests, reproducible TS source/dist, schema/corpus/baseline guards, ACL self-tests, version coherence, `cargo-deny`, and `buf`. Requires `cargo`, `python3`, `c++`, `bun`, `cargo-deny`, and `buf`. |
| `sync_rust_package_testdata.py [--write]` | Checks (or refreshes) crate-local package-test snapshots and dual-license files against their canonical repository-root copies. Missing, stale, symlinked, and unexpected managed files fail. |
| `check_rust_packages.py [--offline]` | Packages all five publishable Rust crates, asserts every archive contains both licenses and all required testdata, tests core/Zenoh/C-ABI from extraction, and type-checks Python/gateway from extraction using temporary local patches for unpublished exact NCP dependencies. |
| `repin-ncp.sh <tag> [base-dir]` | Re-pin every **discovered** NCP consumer to a single tag and refresh lockfiles. Consumers self-register via a `.ncp-consumer` descriptor in their own repo — this script names none of them. Edits files only — no commit/push/stage. |
| `check-consumer-pins.sh [expected-tag] [base-dir]` | Read-only pin-consistency guard: **discovers** consumers (any sibling with a `.ncp-consumer` descriptor) and verifies they pin one agreed tag (optionally `expected-tag`). No writes, builds, or git/network calls. See [`INTEGRATING.md`](../INTEGRATING.md) §"Registering a consumer". |
| `check_proto_schema_parity.py` | Wire-conformance guard: `proto/ncp.proto` vs `schemas/*.schema.json` (field-set + enum wire-string parity). |
| `check_conformance_vectors.py` | Validates the golden message vectors in `conformance/vectors/*.json` against the JSON Schemas. |
| `check_wire_baseline.py` | Enforces additive-only JSON-wire compatibility with the frozen baseline. For a new release line, `--freeze DIR` captures the snapshot and `--verify-exact DIR` proves schemas/vectors are byte-identical immediately before tagging. |
| `check_acl_template.py` | Offline structural guard for the complete secure-router template: mTLS/default-deny, exact key shapes, command/observation PUT = commander, sensor PUT = robot, lifecycle RPC = commander, and observer read-only coverage on all data planes. Runs negative self-tests on every invocation. |
| `render_acl_template.py` | Safely renders every ACL key from the neutral `ncp` realm to one validated exact deployment realm; writes atomically with owner-only permissions. |
| `verify_acl_deployment.py` | Live mTLS/ACL proof using observer-received nonce acknowledgments. Allowed writes must arrive, denied writes must remain absent after a same-plane allowed baseline, and a no-client-cert connection must fail. Also has offline self-test and dry-run modes. |
| `bench_realtime.py` | Real-time-factor sweep for a Brunel-style NEST network served over NCP. |
| `bench_overlap.py` | Whether in-process Python threading can overlap NCP transport I/O with `nest.Run()` (GIL test). |
| `bench_gil_overlap.py` | Whether a native (non-GIL-holding) thread overlaps transport with `nest.Run()`. |
| `bench_chunk_overhead.py` | Cost of chunked vs monolithic NEST simulation under NCP's stepwise control model. |

## Run

```bash
scripts/check.sh                         # full local gate (mirrors CI)
python3 scripts/sync_rust_package_testdata.py
python3 scripts/check_rust_packages.py --offline
scripts/check-consumer-pins.sh v0.6.0    # verify all consumers pin the latest release
scripts/repin-ncp.sh v0.6.0              # re-pin all consumers to that immutable tag
python3 scripts/check_proto_schema_parity.py
python3 scripts/check_acl_template.py
python3 scripts/verify_acl_deployment.py --self-test
```

The `bench_*.py` scripts require a working PyNEST install; see `PERFORMANCE.md`.

## Secure Zenoh deployment tools

Render the router config when a deployment uses a realm other than the neutral
`ncp`. Unsafe/wildcard realms are rejected, existing output is preserved unless
`--force` is explicit, and the completed file atomically replaces the destination:

```bash
scripts/render_acl_template.py \
  --realm engram/ncp \
  --output /etc/ncp/zenoh-router.json5
python3 scripts/check_acl_template.py
```

The structural guard is offline and stdlib-only. It checks the shipped template
and mutates copies to prove the guard rejects widened keys, missing or misbound
PUT authorities, incomplete observer reads, duplicate certificate CNs, bad ACL
tokens, disabled mTLS, and unsafe realm rendering.

After starting the rendered router, use the live verifier with three distinct
mTLS identities whose certificate CNs map to the `commander`, `robot`, and
`observer` subjects. It requires `eclipse-zenoh` (the imported module is
`zenoh`). A put call returning success is deliberately not treated as evidence.
The verifier subscribes as the observer, sends a fresh nonce per trial on a
randomized `acl-verify-*` session, and waits for end-to-end delivery:

```bash
python3 -m pip install eclipse-zenoh
python3 scripts/verify_acl_deployment.py \
  --endpoint tls/router.example:7447 \
  --realm engram/ncp \
  --ca /etc/ncp/certs/ca.pem \
  --commander-cert /etc/ncp/certs/commander.pem \
  --commander-key /etc/ncp/certs/commander-key.pem \
  --robot-cert /etc/ncp/certs/robot.pem \
  --robot-key /etc/ncp/certs/robot-key.pem \
  --observer-cert /etc/ncp/certs/observer.pem \
  --observer-key /etc/ncp/certs/observer-key.pem
```

Use `--dry-run` with the same arguments to validate credential paths, TLS-only
client configuration, disabled discovery/listeners, hostname verification, and
the probe plan without opening a network session. Increase `--timeout` or
`--settle` on a high-latency router. A denied check without a successful allowed
delivery on that same plane is reported as inconclusive/failing, never as proof.
The CLI-only verifier was removed because `z_put` cannot prove delivery or tell
an ACL drop from a disconnected client.

## See also

- The normative wire contract: [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md)
- Repository overview: [repo README](../README.md)

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
