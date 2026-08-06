# `ncp-core`

`ncp-core` is the Rust reference implementation for the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate (wire `1.0`, compact proto hash
`163acc57d8a62b66`). The normative contract lives in the repository's
[`contract/`](../contract/), [`proto/`](../proto/), [`schemas/`](../schemas/),
prose specification, and mandatory corpus; this crate is an informative
implementation of it.

The crate is transport-independent. It provides canonical JSON message types and
validation, key grammar, generic bounded-JSON decoding, security-profile and authority
manifest validation, session/lease state machines, bounded idempotency and receipts,
portable domain-separated security-state and plant-profile digests, content-addressed
plant profiles, deterministic safety/governor/watchdog/action buffer logic,
codec/bulk helpers, audit chaining, and an in-process reference loop.
Zenoh lives in [`ncp-zenoh`](../ncp-zenoh/).

These primitives are necessary but not sufficient for plant-eligible Active output.
The accepted trusted-message-class/decoded-path allocation and equal Rust,
TypeScript, and Python preallocation enforcement for the 256-entry metadata limit
remain open, including exact 256/257 parity vectors. Checked codecs can still
invent midpoint or zero values, accept sparse components, select units by mapping
order, and erase units in `PlantCommand`. A body must not treat that output as
Active admission evidence until unit-preserving installed-profile validation is
integrated.

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
- the breaking candidate API `NeuroControlLoop::tick` returns
  `Result<CommandFrame, ControlLoopTickError>`. Loop-local candidate exhaustion is
  detected before the controller runs. A transport-owned stream can instead
  exhaust or synchronously reject the governed command during slot admission,
  after the controller but before status emission. It contains a panic during slot
  admission and also rejects an admitted position that is wire-invalid, changes
  epoch, does not advance a new slot, or does not exactly reuse the last pending
  position. A panic or invalid result has ambiguous transport-side effects, never
  local operation success. The loop latches that failure and performs no later
  sensor, controller, command, or status work; recovery requires a fresh
  loop/transport generation.
  For a tick with an accepted sensor, `Ok` carries the exact validated
  transport-assigned position and means bounded local slot admission, not network
  delivery. Before the first accepted sensor, `Ok` is a local governed result and
  status only. Construct fresh loop and transport declarations after their
  respective exhaustion errors. The loop retains each trustworthy tick-clock
  high-water sample even when command admission or governance returns an error.
  A controller panic permanently retires that controller within the loop because
  unwinding can leave partially mutated state; all later ticks remain non-Active
  and recovery requires a fresh loop/controller generation;
- `SafetyGovernor::govern` returns `Result`. It preserves a canonical attributable
  stream/session envelope for each safe frame. Among the envelope's identity and
  position fields, it can normalize only an invalid stream sequence to `1`; it can
  also normalize non-routing metadata. The standalone governor has no publisher
  allocator or stream high-water state. Sequence `1` is the required initial
  numeric value for a newly declared stream, but the governor neither declares nor
  admits that position. A caller must not publish that fallback into an existing
  stream; it must withhold the frame or invoke the governor with the owning
  publisher's next fresh position. `NeuroControlLoop` stamps its own position
  before governance. See [`KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md). If the
  attributable envelope is unavailable, the governor latches locally and returns
  `SafetyGovernError` without a wire frame. The caller or transport must separately
  admit the exact route and live session generation;
- each generated HOLD or ESTOP frame passes semantic validation and generic
  bounded-JSON preflight over exact serialized bytes. The governor tries the
  complete representable zeroed channel union, then all negotiated channels, then
  an empty channel map. If all three tiers fail, it returns `SafetyGovernError`
  without a wire frame;
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
