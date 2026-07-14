# `ncp` Python binding

`ncp-python` is the PyO3 interface to the Rust reference implementation for the
unreleased, release-blocked NCP `1.0.0-rc.1` candidate. It is wire/decision binding
evidence, not an independent non-Rust implementation.

Build it through maturin, not plain Cargo:

```bash
maturin develop -m ncp-python/Cargo.toml --features extension-module
```

```python
import ncp

assert ncp.PACKAGE_VERSION == "1.0.0-rc.1"
assert ncp.NCP_VERSION == "1.0"
assert ncp.CONTRACT_HASH == "163acc57d8a62b66"
assert len(ncp.NORMATIVE_CONTRACT_DIGEST) == 64
assert ncp.BUILD_IDENTITY == "unreleased-worktree"  # RC default, not a source commit
keys = ncp.Keys("ncp")
assert keys.command("body-1") == "ncp/session/body-1/command"
```

The module exposes version/hash checks, canonical keys, message validation, rate
codec helpers, the persistent latching `Governor`, and `ActionBuffer`. A live body
needs both the governor and buffer: the first applies sensor/geofence/speed policy,
while the second applies TTL, monotonic stream sequence, bounded predictive replay,
and its own ESTOP latch.

`ActionBuffer` is declaration-bound: a lower/equal sequence remains rejected after
TTL expiry, and a foreign epoch requires a fresh object. `reset()` is a body-local
primitive for an already-authorized session-generation cut. It clears the latch and
permanently retires that object (`is_retired() == True`); it does not authenticate an
authorized operator or restore authority. Construct a new buffer only for the fresh
`SessionOpened` generation.

Every binding entry point that accepts JSON applies the same universal byte,
depth/node, string/number, Unicode, and duplicate-key preflight before typed decode;
call `validate` for complete message-shape and semantic validation. An active wire-1.0
`CommandFrame` additionally needs the matching authority lease. The binding does not
authenticate payload claims by itself; the transport/deployment adapter must bind the
verified principal to entity, role, and plane and enforce exact live
route/session-generation admission before calling the local buffer. Its local
fail-safe priority is not a malformed remote-ESTOP bypass.

The complete normative digest is in
[`../contract/manifest.v1.json`](../contract/manifest.v1.json). This RC wheel is not
published or independently live-certified. See
[`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) and
[`RELEASE_READINESS.md`](../RELEASE_READINESS.md).

Licensed under either [MIT](../LICENSE-MIT) or
[Apache-2.0](../LICENSE-APACHE).
