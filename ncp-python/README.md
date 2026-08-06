# `ncp` Python binding

`ncp-python` is the PyO3 interface to the Rust reference implementation for the
unreleased, release-blocked NCP `1.0.0-rc.1` candidate. It is wire/decision binding
evidence, not an independent non-Rust implementation.

Python 3.11 or later and maturin are required. Build through maturin, not plain
Cargo:

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
codec helpers, the persistent latching `Governor`, and `ActionBuffer`. These
primitives are necessary but not sufficient for a live body. The governor applies
sensor/geofence/speed policy, while the buffer applies TTL, monotonic stream
sequence, bounded predictive replay, and its own ESTOP latch.

The module-level `govern` function and persistent `Governor.govern` method can
raise `ValueError` for a local `SafetyGovernError`. In that case, the governor
produced no attributable bounded wire-shape candidate. A persistent governor keeps
its local ESTOP latch set after an unattributable-envelope failure. Success proves
shape and bounds, not publisher-position freshness. The standalone governor has no
allocator or stream high-water and can normalize an invalid sequence to `1`; never
publish that normalized position into an existing stream. Put the owning publisher's
next fresh position in the input command, then admit that position, the exact route,
and the live session generation.

`ActionBuffer` is declaration-bound: a lower/equal sequence remains rejected after
TTL expiry, and a foreign epoch requires a fresh object. `reset()` is a body-local
primitive for an already-authorized session-generation cut. It clears the latch and
permanently retires that object (`is_retired() == True`); it does not authenticate an
authorized operator or restore authority. Construct a new buffer only for the fresh
`SessionOpened` generation.

Every binding entry point that accepts JSON applies the same generic byte,
depth/node, string/number, Unicode, and duplicate-key preflight before typed decode;
call `validate` for complete message-shape and semantic validation. An active wire-1.0
`CommandFrame` additionally needs the matching authority lease. The binding does not
authenticate payload claims by itself; the transport/deployment adapter must bind the
verified principal to entity, role, and plane and enforce exact live
route/session-generation admission before calling the local buffer. Its local
fail-safe priority is not a malformed remote-ESTOP bypass.

The generic object-entry ceiling does not close the open trusted-message-class and
decoded-path allocation or equal Rust, TypeScript, and Python preallocation rule.
Checked codecs can still invent midpoint or zero values, accept sparse components,
select units by mapping order, and erase units in `PlantCommand`. Their output is
not plant-eligible Active evidence until the body performs unit-preserving
installed-profile validation.

The complete normative digest is in
[`../contract/manifest.v1.json`](../contract/manifest.v1.json). This RC wheel is not
published or independently live-certified. See
[`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) and
[`RELEASE_READINESS.md`](../RELEASE_READINESS.md).

Licensed under either [MIT](../LICENSE-MIT) or
[Apache-2.0](../LICENSE-APACHE).
