# ncp-gateway

[![License: MIT OR Apache-2.0](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)

A reference Rust NCP edge for a NEST-based commander (e.g. Engram): a **binary** that
serves the lifecycle RPC key family and bridges each request to a separate Python
`SessionService` process. Streaming data planes connect directly between NCP peers.

When the commander's brain is NEST (Python), its NCP *server* stays Python. This gateway gives it a
production-grade Rust Zenoh edge: it declares `{realm}/rpc/*`, receives client requests on
exact `{realm}/rpc/{request_kind}` keys, then forwards each RPC to Python `bridge_server.py` over a localhost
socket — reusing the transport-neutral `handle_json` seam. The fleet-facing, latency-sensitive
transport becomes Rust (SHM/QoS, many-to-many discovery, free observer taps); `nest.Run` stays
in Python.

In the polyglot NCP SDK, one normative wire contract is spoken by peers in Rust, Python, TypeScript,
and C/C++. `ncp-gateway` is the Rust deployment edge in front of a Python commander; it builds on
[`ncp-core`](../ncp-core) (keys/realms) and [`ncp-zenoh`](../ncp-zenoh) (the Zenoh transport).

```text
 Zenoh bus  ──(SHM/QoS)──►  ncp-gateway (this)  ──(TCP, newline-JSON)──►  bridge_server.py
    ▲                          {realm}/rpc/* queryable                    SessionService.handle_json → nest.Run
    └── robot/UAV bodies, analysis/observer clients, dashboards attach as peers / observers
```

## Run

```text
cargo run -p ncp-gateway
```

Configuration is via environment variables:

```text
NCP_REALM        key-expression realm           (default: ncp; set per deployment)
NCP_BRIDGE_ADDR  Python bridge_server.py addr   (default: 127.0.0.1:28474)
NCP_ZENOH_CONFIG strict Zenoh client config     (optional; required for secure deployment)
```

The gateway serves only lifecycle RPC on `{realm}/rpc/*`. Sensor, command, and
observation planes connect directly between NCP peers. Ctrl-C to stop.

For a secure deployment, run a separately realm-rendered
`deploy/zenoh-access-control.json5` as the router and point `NCP_ZENOH_CONFIG` at a
configured copy of `deploy/zenoh-client-secure.json5`. The gateway's strict client
open rejects the router config (`mode="router"`) and any plaintext/discovery-capable
client config.

## See also

- The normative wire contract: [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md)
- Repository overview: [NCP README](../README.md)

## License

Licensed under either of [MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE) at your option.
