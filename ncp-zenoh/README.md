# `ncp-zenoh`

`ncp-zenoh` is the stable transport binding named by the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate. It carries canonical JSON over Zenoh
queryable RPC and per-session pub/sub keys; it does not change the normative wire.
It re-exports the coordinated package, wire, compact-proto, complete-contract, and
build identity constants from `ncp-core`; the RC build identity is the
non-certifying `unreleased-worktree` sentinel.

The four local QoS classes are explicit:

| Plane | Zenoh intent | Bounded queue meaning |
|---|---|---|
| control | reliable request/reply, backpressure | reject overflow |
| perception | high-priority freshness, drop congestion | replace latest |
| action | express real-time, drop congestion | highest fail-safe severity: ESTOP, HOLD/non-active, Active; equal severity latest |
| observation | low-priority diagnostic, drop congestion | drop oldest and count |

Plane-specific publish/subscribe methods require the live `SessionRef` returned by
`SessionOpened` and validate kind, wire, exact payload-to-key `session_id`, exact
generation, stream shape, scientific flags, and structural lease fields before
delivery. They do not authenticate a principal or prove that a lease is currently
held; the production adapter/body must enforce those authority checks. Generic raw
byte methods remain an explicit untrusted escape hatch and do not confer NCP
validity. Each `ZenohBus` object owns one bounded, non-evicting typed-publisher
fence shared by its clones; base and named concrete routes are independent, and a
separately constructed wrapper is a fresh publisher declaration. A position is
consumed before the awaited Zenoh put, so a failed put remains delivery-ambiguous:
never retry the same position. Each typed subscriber declaration has its own fresh,
non-evicting fence before callbacks, queues, or latches; a glob subscription tracks
each actual concrete route independently. Redeclare both ends deliberately when
adopting a restarted stream epoch. Bare `NCPB` is rejected. Every remote ESTOP needs
a complete envelope and live binding; it may omit only the authority lease.

`ZenohControlTransport` owns one command epoch and one JSON-safe sequence allocator
across Active, HOLD, and ESTOP; caller and emergency positions are always replaced by
that single action-stream identity. `send_command()` reports bounded slot admission
(`Accepted`, `ReplacedPending`, or `Rejected`), not Zenoh delivery. A pending
pre-publication replacement reuses the slot's position so local replacement creates no fake
gap. Once a put is attempted, the position is consumed. If a fail-safe put is
rejected or delivery-ambiguous, `fail_safe_delivery_pending()` remains true and
Active admission is rejected until the caller submits a new logical fail-safe at a
new position and it publishes successfully. The dispatcher does not busy-loop or
requeue the same bytes/position.

The typed observation subscriber owns the normative 64-frame bounded queue: on
overflow it drops the oldest frame and increments
`observation_queue_drops_total()`. Instrumentation exports that aggregate as
`ncp_queue_drops_total{plane="observation"}` without high-cardinality session
labels. Generic raw subscriptions do not acquire typed observation semantics.

`production-secure` is currently unavailable in this adapter. The Zenoh callbacks
used by `ncp-zenoh` expose the key and payload but not a transport-authenticated
remote principal, so the adapter cannot bind an NCP `IdentityClaim` to the verified
peer identity. `ZenohBus::open_secure` validates the TLS-only client configuration
prerequisite and then intentionally fails closed before opening a session. The
shipped ACL/TLS templates remain configuration-only, and generic `open()`,
`with_config()`, or arbitrary config-file loading must not be represented as
`production-secure`.

`serve_rpc` bounds concurrent handler lifetimes, contains panics, validates
selector/request/reply/session correlation, and returns registered errors:
`NCP-WIRE-001` for an invalid request and `NCP-INTERNAL-001` for contained handler,
reply, spawn, or capacity failures. Explicit timeout variants should cover requested
simulation duration plus backend overhead. Subscription handles must be released on
session close.

`ncp-gateway` is a native same-wire 1.0 user of this crate; it is not the 0.8
migration gateway. Engram's local native-1.0 migration is in progress, but only a
backend that passes the complete native contract can be placed behind it.

Run:

```bash
cargo test -p ncp-zenoh
```

See [`NEURO_CYBERNETIC_PROTOCOL.md`](../NEURO_CYBERNETIC_PROTOCOL.md),
[`SECURITY.md`](../SECURITY.md), and
[`RELEASE_READINESS.md`](../RELEASE_READINESS.md). Licensed under either
[MIT](../LICENSE-MIT) or [Apache-2.0](../LICENSE-APACHE).
