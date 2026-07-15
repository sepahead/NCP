# `ncp-core`

`ncp-core` is the Rust reference implementation for the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate (wire `1.0`, compact proto hash
`163acc57d8a62b66`). The normative contract lives in the repository's
[`contract/`](../contract/), [`proto/`](../proto/), [`schemas/`](../schemas/),
prose specification, and mandatory corpus; this crate is an informative
implementation of it.

The crate is transport-independent. It provides canonical JSON message types and
validation, key grammar, universal bounded decoding, security-profile and authority
manifest validation, session/lease state machines, bounded idempotency and receipts,
portable domain-separated security-state and plant-profile digests, content-addressed
plant profiles, deterministic safety/governor/watchdog/action buffer logic,
codec/bulk helpers, audit chaining, and an in-process reference loop.
Zenoh lives in [`ncp-zenoh`](../ncp-zenoh/).

RPC failures use a required registered `ErrorFrame.code`. The typed builders
distinguish invalid wire messages (`NCP-WIRE-001`) from contained implementation
failures (`NCP-INTERNAL-001`) while preserving an exact optional session pair.
`canonicalize_message_json` is the shared bounded validate-and-round-trip path used
by the Python and C/C++ bindings; it emits deterministic Rust-reference bytes and
keeps those wrappers from acquiring subtly different defaults or field ordering.

Runtime/package introspection is available through `PACKAGE_VERSION`,
`NCP_VERSION`, `CONTRACT_HASH`, `NORMATIVE_CONTRACT_DIGEST`, and `BUILD_IDENTITY`.
The checked-in RC reports `unreleased-worktree`; only an immutable release build
may override it with an exact source identity, and that override is not itself a
release certification.

Important boundaries:

- payload identity is not authentication; a transport adapter binds the verified
  principal to entity/role/plane;
- raw `Bus` callbacks carry untrusted bytes; the exact typed `NcpBusClient` and
  `NcpBusServer` boundaries additionally bind the live session and retain a bounded,
  non-evicting per-lifetime stream high-water fence;
- active action and step/run/close require matching live authority; mutations also
  use operation context and authenticated receipts;
- authority renewal authenticates the exact current issuer and holder and requires
  the local monotonic lease deadline to remain unexpired; expiry requires a newer
  acquisition rather than late renewal;
- one watchdog/action-buffer/control-loop instance is declaration-bound to one
  stream epoch and permanent sequence high-water. Expiry never permits a lower
  sequence or foreign epoch; restart constructs fresh declaration state;
- `ActionBuffer::reset` and `AuthorityMachine::reset_estop` retire their old
  generation-bound objects. They are audit state afterward and cannot reacquire or
  reactivate; a fresh `SessionOpened` generation gets fresh objects;
- periodically published status positions start at 1, never repeat, and stop at
  JSON-safe exhaustion until a new publisher declaration;
- `BulkBlock` is bounded local/offline data and not a transport frame;
- HOLD/ESTOP is not physical safety certification and the body remains final
  actuator authority;
- simulation results remain `calibrated_posterior=false` and
  `is_simulation_output=true` and are not paper reproductions.

The `validate-wire-08-capture` binary and
`validate_wire_0_8_capture` API provide bounded, validation-only legacy-capture
reconstructability checks. They require the exact declared legacy wire/compact
contract identity, one realm and frozen route grammar, exact nested shapes,
explicit units and frames, opening lineage, global non-evicting publisher/epoch
restart fences, source correlation, requested-seed agreement, and epistemic flags.
Wire-0.8 records that would need authority or operation evidence reject, as does
`control_status` because the frozen route grammar has no status route. The report
binds the source bytes, validator package/build identity, compact target hash, and
complete target normative digest; it emits no target capture or upgraded claim.
See
[`docs/wire-0.8-capture-migration.md`](../docs/wire-0.8-capture-migration.md).

Run the crate's complete tests with:

```bash
cargo test -p ncp-core --all-features
```

The full repository gate is [`scripts/check.sh`](../scripts/check.sh). Local tests do
not satisfy live security, independent-peer, fault/soak, fuzz, package-signing, or
consumer-certification pre-release gates. See
[`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md) and
[`RELEASE_READINESS.md`](../RELEASE_READINESS.md).

Licensed under either [MIT](../LICENSE-MIT) or
[Apache-2.0](../LICENSE-APACHE) at your option.
