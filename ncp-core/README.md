# ncp-core

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

The **normative Rust reference** for the Neuro-Cybernetic Protocol (NCP): a versioned,
transport-agnostic, project-agnostic standard for letting a NEST-based simulation
serve external robot / UAV / simulation systems — for perception, action, both, or neither.

This crate is the one other NCP peers depend on. It is serde-only (no transport): the wire
types, the version guard (`NCP_VERSION` / `check_version`), the key scheme, a reference rate
codec, the action-plane safety governor, and an in-process bus and control loop. The Zenoh
transport lives in `ncp-zenoh`; the Python, TypeScript, and C++ peers (`ncp-python`,
`ncp-ts`, `ncp-cpp`) serialize to semantically-equivalent JSON for every shipped
plane. `BulkBlock` is a bounded, golden-vector-pinned local/offline column codec,
not a standalone observation frame.

**Scientific boundary (binding):** returned `V_m`/spikes are raw simulation outputs of a
specified model, never a validated reproduction. Every `ObservationFrame` carries
`calibrated_posterior=false` and `is_simulation_output=true`. A neuro-controller is a control
artifact, never a paper-reproduction claim.

```rust
use ncp_core::{OpenSession, NetworkRef, NetworkRefKind, RecordSpec, RecordTarget, Observable};

let open = OpenSession {
    session_id: "uav3-percept".into(),
    network: NetworkRef {
        kind: NetworkRefKind::Builtin,
        ref_: "iaf_psc_alpha".into(),
        population_sizes: [("feat".to_string(), 1)].into_iter().collect(),
        ..Default::default()
    },
    record: RecordSpec { targets: vec![RecordTarget {
        port: "spk".into(), target: "feat".into(), observable: Observable::Spikes,
        ..Default::default()
    }] },
    ..Default::default()
};
let json = serde_json::to_string(&open).unwrap();
assert!(json.contains("\"kind\":\"open_session\""));
```

Public modules: `messages` (wire types + `validate`), `codec`, `keys`, `safety`, `bus`,
`bulk`, `resilience`, `transport`.

See the normative specification [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md)
and the [repository README](../README.md) for the full protocol, the wire contract, and the
peer matrix.

## Transport-agnostic by construction

`ncp-core` pulls in **no transport** — no Zenoh, no sockets, no async runtime, just
`serde`. Everything reaches the outside world through one trait, `ControlTransport`
(`send_command` / `latest_sensor` / `send_status`), so the same `NeuroControlLoop`
runs unchanged over:

- `InProcessTransport` — in-memory and deterministic (injectable clock); used by the
  examples and by software-in-the-loop tests;
- the Zenoh pub/sub transport in `ncp-zenoh` (cross-process, many-to-many fleet
  fan-out, ROS 2 / `rmw_zenoh` interop, SHM zero-copy);
- a plain TCP socket (see the `ncp_tcp_client` example), or any transport a consumer
  supplies.

Why this seam matters (first principles): interoperability is a property of the
**contract** — wire shape, version compatibility, and the action-plane safety
envelope — not of any one transport. NCP is **generic** and carries no
consumer-specific assumptions. In practice the hub / command-center consumer is
**Engram** (a NEST spiking-sim backend) driving robots and UAVs interchangeably
through NCP; **crebain** (a tactical-UAV app) runs standalone on its own drone stack
*and/or* through NCP alongside others; **prisoma** is a third consumer. They share
these types, not a transport.

## Encoding: JSON on every shipped plane

The runtime wire is **JSON** (`serde_json`) on the three live planes — Sensor
(perception), Command (action), and RPC (control). JSON is the deliberate, debuggable
default: human-readable, trivially bridged across languages, and (per the `overhead`
benchmark below) far under any realistic control budget. The compact
**binary `BulkBlock`** (`NCPB` magic + version byte; module `bulk`) remains useful
for local/offline arrays, but lacks the session/seq/provenance envelope required on
the observation plane and is not accepted bare by `ncp-zenoh`.

`proto/ncp.proto` (with `gen/rust`) is the **schema source-of-truth and conformance
reference**, *not* the shipped runtime encoding — the generated prost bindings are
not compiled into the runtime path. So protobuf is the schema contract; JSON is what
actually flows. A negotiated binary encoding could later be offered as an opt-in for
a kHz-rate or bandwidth-constrained consumer without changing these types.

## Safety and codec

**Action-plane safety (`safety`).** The action plane is the only plane with command
authority, so it is the only one with a governor. `SafetyGovernor::govern` returns a
*fresh* `CommandFrame` (it never mutates its input) after applying, in order:

- **speed clamp** — magnitude-limits the commanded velocity to `max_speed_mps`;
  `ReflexController` uses the same vector-magnitude convention;
- **geofence** — a breach **latches** ESTOP; while still in bounds, the governor
  projects canonical velocity over every interval the command buffer can apply
  before TTL, then HOLDs/truncates before a crossing (safe inward motion remains
  active); every later post-breach tick returns zeroed ESTOP until supervisor reset;
- **stale-sensor HOLD** — a missing/old sensor falls back to HOLD, *non-latching*
  (it clears as soon as fresh data resumes);
- **fail-safe clock** — a non-finite tick time fails to HOLD, never fail-open;
- **config fail-closed** — a limit naming a channel absent from the negotiated
  `Capabilities` latches HOLD and reports `safety_ok=false`.

`CommandWatchdog` is the producer-overrun backstop: if the controller misses its
deadline the plant-side watchdog HOLDs independently, and an out-of-order (older
`seq`) command does not refresh the deadline. A clock rewind revokes authority
through catch-up until a fresh command arrives. `ActionBuffer` clears buffered
actuation on every non-Active mode before replay checks, so a stale/duplicate HOLD
is never dropped while an older setpoint continues.

**Codec (`codec`).** A *declarative* `CodecSpec` freezes the
sensor->rate->command interface so a trained SNN policy can train against a stable
contract. The reference implementation is deterministic linear **rate coding**: the
encoder maps a sensor component onto a population firing rate; the decoder maps a
readout rate back onto a command component. It fails safe — a non-finite sensor
sample encodes to the rate-range low bound, and an absent readout population decodes
to the **neutral midpoint**, not full-reverse actuation.

**Resilience (`resilience`).** `ActionBuffer` replays a command's predictive
`horizon` through a link dropout and HOLDs on `ttl` expiry; `LinkMonitor` tracks link
health / jam detection.

The reference loop steps controllers only on fresh validated sensors, resets them
on stream-epoch restart, contains controller panics, and applies the final
cadence-derived TTL before prospective geofence enforcement. It publishes no
action until there is a stamped sensor envelope to echo.

## Examples

Run with `cargo run -p ncp-core --example <name>` (add `--release` for benchmarks):

- **`uav_control_safety`** — full UAV motion + control + safety with no transport
  stack. A `NeuroControlLoop` + `ReflexController` flies a simulated quad to target,
  then every `SafetyGovernor` gate (speed clamp; geofence -> latched ESTOP;
  stale-sensor HOLD; ESTOP-mode passthrough; non-finite-clock fail-safe; predictive-
  horizon clamp), the `ActionBuffer` horizon replay, and the `CommandWatchdog`
  deadline run as pass/fail checks. The single best read for *how the safety layer
  behaves*.
- **`overhead`** (build `--release`) — the per-tick overhead benchmark (the repo
  previously had none). A full control tick is **~1 us**: `CommandFrame` ser/de
  ~= 248 / 446 ns (215 B), `SensorFrame` ~= 223 / 474 ns (195 B),
  `SafetyGovernor::govern` ~= 140 ns, `ReflexController::step` ~= 134 ns — i.e.
  0.003-0.1 % of a 20-1000 Hz budget, with in-sim compute dominating. It also shows
  the binary `BulkBlock` is several times smaller than JSON for 1000 floats. Use it
  to answer *is NCP just overhead?* — the contract + safety cost is negligible; the
  contract is the point.
- **`ncp_tcp_client`** — a minimal Rust NCP client over a plain TCP socket with
  newline-delimited JSON, run against Engram's reference Python `bridge_server`. It
  proves cross-process, cross-language interop *without* Zenoh and exits non-zero on
  any version / contract / scientific-boundary violation.

## Known limitations

NCP ships a live [`KNOWN_LIMITATIONS.md`](../KNOWN_LIMITATIONS.md) ledger spanning
correctness, safety, robustness, overhead, and integration. All original high-severity
findings are fixed and regression-tested: bulk decode is bounded and rejects
overlap/duplicate/padding tricks, watchdog TTL is finite and capped, and an empty
position channel fails closed. Wire 0.7 adds full typed validation, precision-safe
JSON integers, strict realm/RPC addressing, and cross-language behavior vectors.
Remaining unit/arity, transport-lifecycle, deployment-validation, and copy/latency
items stay explicit; consult the ledger rather than the retired numeric audit count.


## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
