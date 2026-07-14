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
