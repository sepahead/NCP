# `ncp-zenoh`

`ncp-zenoh` is the stable transport binding named by the unreleased,
release-blocked NCP `1.0.0-rc.1` candidate. It carries validated NCP JSON over Zenoh
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
that single action-stream identity. `send_command()` reports the result of bounded slot admission
(`Accepted`, `ReplacedPending`, `StreamExhausted`, or `Rejected`), not Zenoh
delivery. The admitted variants carry the exact transport-assigned position. A pending
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

The reviewed Cargo feature set is exactly TCP, TLS, UDP, and shared memory.
Zenoh defaults and `transport_compression` remain disabled. The workspace root
patches only `zenoh-transport 1.9.0` to immutable revision
`9045545b72a77602a87f40203cb614b48157b4bc`. That reviewed backport selects
patched `lz4_flex 0.11.6`, updates its `twox-hash` dependency to `2.1.3`, and
selects non-yanked `spin 0.9.9` and `0.10.1`. The fork CI pins
`cargo-deny 0.19.9` and rejects yanked lock entries and current RustSec
vulnerabilities. Its qualification lock also selects fixed
`crossbeam-epoch 0.9.20`, `rand 0.8.6` and `0.9.4`, `quinn-proto 0.11.15`,
`rustls-webpki 0.103.13`, and `serde_with 3.21.0`.
This removes `RUSTSEC-2026-0041` from the root lock.

The package checker verifies the selected Git revision, tree, tracked files, and
reviewed delta from the checksum-bound registry source during qualification. The
receipt classifies these checks as point-in-time local-process attestations and
does not retain the exact fork source bytes. Cargo does not verify Git signatures.

Cargo patches are root-selected and do not propagate from a published library
dependency. Each source-tree consumer must retain the same exact root patch and
run its own locked dependency gate. Without that patch, the normalized source
archive resolves registry `zenoh-transport 1.9.0` to affected
`lz4_flex 0.10.0` and its `twox-hash 1.6.3` dependency. The package checker does
not compile that fallback. It applies the exact patch at the consuming test root.
The conditioned graph then resolves patched `lz4_flex 0.11.6` and updates its
`twox-hash` dependency to `2.1.3`. The qualification also runs the exact fork's
`security_backport` regression and its compression-enabled library tests.

Exact resolution and fetch can use network access. Cargo dependency access is
offline only during compile and test. The checker claims no host or child-process
network isolation and no host filesystem isolation. Its source comparison covers
both conditioned consumer graphs at two points in time. It retains no
compiler-input trace or command transcript. The result is `CONDITIONAL_PASS`, with
`package_self_contained=false`,
`self_contained_distribution_gate=OPEN_FAIL_CLOSED`, `decision=NO_GO`, and
`release_authorized=false`. A future package candidate must use a qualified
immutable upstream release or another reviewed distribution design. Cargo feature
unification by another dependency can also enable unreviewed Zenoh features. Such
a build is outside this candidate profile.

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
