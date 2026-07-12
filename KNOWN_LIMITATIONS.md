# Known Limitations & Hardening Backlog

> Wire **0.8**, released as the latest immutable tag `v0.8.0` (SDK manifests
> 0.8.0). This tracks findings from continuing adversarial reviews of NCP
> (correctness, safety, robustness, overhead) **and their current status**. Each
> notes whether the fix changes the on-wire contract (`wire-breaking`, needs a
> version bump + consumer buy-in across all pinned consumers) or is internal
> (`safe`). NCP is a generic, shared contract, so conservatism on the still-open
> items is deliberate.
>
> The original 35-item audit is retained below, but the old numeric status summary
> is intentionally retired: the 0.7 review added cross-language, provenance,
> integer-precision, error-frame, CI/supply-chain, and consumer-integration findings.
> All original high-severity safety findings remain resolved. Line numbers are
> indicative and may drift — search by symbol.


## Resolved

Fixed in-tree, each wire-safe and covered by a regression test. Do not re-open
these without checking the cited code first.

### High — safety / robustness (all three closed)

- **decode: per-column allocations now carry a cumulative budget — the
  overlapping/duplicate-column memory-amplification (OOM DoS) is closed** —
  `bulk.rs` (`BulkBlock::decode`) · _safety_ · **fixed** (commit `0672168`).
  A running `alloc_budget` (`= bytes.len()`) charges both copied names and numeric
  data, and a 64 MiB input ceiling bounds absolute work, so a tiny
  hostile block can no longer force ~64,000× allocation. Every conforming block
  lays columns out disjointly, so only overlapping/amplifying blocks are rejected.
- **Unbounded / non-finite `ttl_ms` no longer defeats the `CommandWatchdog`
  deadline backstop** — `safety.rs` (`CommandWatchdog::on_command`) · _safety_ ·
  **fixed** (commit `0672168`). The enforced ttl is clamped to a finite ceiling
  (`MAX_TTL_MS = 60_000`) and a non-finite `ttl_ms` maps to `0` (immediately
  stale). The wire still carries `ttl_ms` unchanged; only local enforcement is
  bounded. (Closes both the "unbounded ttl" and the "non-finite `+Inf` ttl" fail-OPEN.)
- **Empty position-channel data no longer bypasses the geofence** — `safety.rs`
  (`SafetyGovernor::govern`) · _safety_ · **fixed** (commit `0672168`). An empty
  position vector previously read as `r = sqrt(0) = 0` ("at the origin", inside any
  fence); it now fails closed to HOLD like an absent channel, and the same guard is
  mirrored at the horizon look-ahead.

### Wire-breaking — resolved by the wire-0.6 cut (v0.6.0)

- **`ncp_version` is now required and value-checked on every message, closing the
  data-plane gap** — `messages.rs` (`required_fields`, `validate`,
  `WireFrame::validate_wire`, `decode_validated`) · _design-gap_ · **fixed (wire
  0.6)**. Every `kind` lists `ncp_version` in `required_fields()` (injected into
  every schema's `required` array plus a `const` pin), `validate()` rejects an
  absent OR incompatible version (never coerces), an absent version now
  deserializes to a detectable `""` instead of silently defaulting to the
  receiver's own, and the Zenoh data-plane ingress/publish paths run
  `decode_validated` per frame. The serialization is unchanged, so
  `CONTRACT_HASH` is identical — the version string is the gate.
- **The `seq == 0` always-accept escape hatch is removed: the action plane
  requires a stamped, strictly-increasing `seq >= 1`** — `safety.rs`
  (`CommandWatchdog::on_command`), `resilience.rs` (`ActionBuffer::on_command`),
  `transport.rs` (`NeuroControlLoop::tick`) · _safety_ · **fixed (wire 0.6)**.
  An unstamped/negative seq never refreshes liveness or overwrites a held
  setpoint (an ESTOP still latches regardless — a fail-safe is never dropped).
  Restart recovery without a wire epoch field: a strictly-LOWER seq re-anchors a
  new stream epoch only once the stream has already expired (the plant is safely
  holding); an EQUAL seq never re-anchors, so a frozen/replayed frame cannot
  duty-cycle liveness across expiry windows. `ObservationFrame.seq` stamping on
  the observation plane is now normative (publisher-enforced in
  `ncp-zenoh::publish_observation`; `0` remains the pull/RPC-reply form).
  Residual: alternating replays of DIFFERENT captured frames across expiry
  windows can still duty-cycle a plant — receiver-side seq discipline cannot
  distinguish that from a restart on an unauthenticated wire; adversarial
  integrity remains mTLS's job (see `SECURITY.md`).

### Medium / low — safety governor & link monitor

- **A non-finite / negative `SafetyLimits` value no longer silently disables
  enforcement (fail-closed)** — `safety.rs` (`SafetyGovernor::govern`) · _safety_ ·
  **fixed**. `NaN`/`±Inf`/`< 0` for `geofence_radius_m` or `max_speed_mps` made the
  `> 0.0` enforcement gates false, skipping the geofence/speed block entirely
  (fail-OPEN). `govern` now treats any such limit as an unrecoverable
  misconfiguration: it latches `config_fail_closed`, HOLDs, and reports
  `safety_ok() == false`. `0.0` remains the documented "disabled" value. (Covers
  the former "NaN safety limit", "NaN/negative `SafetyLimits`", and the limit half
  of "NaN velocity/position" findings; the NaN velocity/position *data* paths were
  already fail-safe.)
- **Staleness and ttl checks no longer fail OPEN on a backward (non-monotonic)
  clock step** — `safety.rs` (`SafetyGovernor::govern`, `CommandWatchdog::should_hold`)
  · _safety_ · **fixed**. A rewound clock made `(now_s - last)` / `(now_s - t)`
  negative → never `> timeout` → "not stale/expired". Both paths now treat
  `now_s < last` / `now_s < t` as stale/expired (HOLD), completing the earlier
  non-finite-clock guard.
- **`LinkMonitor` seq arithmetic no longer overflows on mixed-sign extreme seqs**
  — `resilience.rs` (`LinkMonitor::on_seq`, `loss_rate`) · _safety_ · **fixed**.
  `missed = seq - e` and `span = exp - first` are now `saturating_sub`, so a
  garbage/hostile peer straddling zero with extreme magnitude can no longer
  overflow (debug panic / release wrap) and silently fail the jam detector open.
- **`max_horizon_len` no longer returns `usize::MAX` for a non-finite `ttl_ms`** —
  `resilience.rs` · _robustness_ · **fixed**. `Inf / dt` floored and cast to
  `usize` saturated to `usize::MAX` (an effectively unbounded predictive horizon);
  a non-finite `ttl_ms`/`horizon_dt_ms` (or `dt <= 0`) now returns `0` (no replay),
  and finite horizons are capped by both the enforced 60 s TTL and
  `MAX_HORIZON_STEPS = 65_536`.
- **Bulk encoding no longer truncates counts, lengths, or offsets** — `bulk.rs`
  (`BulkBlock::encode`) · _robustness_ · **fixed in 0.7**. Encoding is fallible,
  checks every `u16`/`u32` conversion and arithmetic operation before allocation,
  rejects blocks over 64 MiB or 4,096 columns, and validates directory-region
  overlap with a sorted `O(n log n)` scan rather than pairwise `O(n²)` work.
- **Bare bulk blocks no longer masquerade as complete observation frames** —
  `ncp-zenoh::publish_observation` · _correctness/security_ · **fixed in 0.7**.
  NCPB has no session/seq/timestamp/provenance, so the public observation-plane
  publisher accepts only validated JSON `ObservationFrame` until a complete
  cross-language `BulkObservation` envelope ships.
- **Cross-language acceptance drift is closed for kind, int64 precision, enums,
  nested stimuli, provenance, and RPC errors** — `messages.rs`, schema generator,
  TS/C/Python gates, behavior corpus · _interop_ · **fixed in 0.7**. Unknown enum
  strings are retained verbatim; int64 JSON numbers are limited to ±(2^53−1);
  boundaries are explicit; replies are typed/versioned and session-checked.
- **Realm key-expression injection is rejected before transport open** — `keys.rs`,
  `ncp-zenoh`, `ncp-gateway` · _robustness/security_ · **fixed in 0.7**.
  `valid_realm` validates every segment, `Keys::try_new` returns a normal config
  error, the validated realm is private/immutable after construction, transport
  boundaries revalidate defensively, and the gateway refuses an invalid
  `NCP_REALM` rather than constructing widened keys.
- **Wire-facing key builders are fallible** — `keys.rs`, `bus.rs` · _robustness_ ·
  **fixed in 0.7**. `try_sensor`/`try_command`/named/glob variants reject unsafe
  session/entity segments as normal errors; transport boundaries use them. The
  infallible builders remain only as programmer-convenience wrappers.
- **Lifecycle RPC verbs no longer share one unsplittable query key** — `keys.rs`,
  `bus.rs`, `ncp-zenoh`, proto `wire key` annotations · _authorization_ ·
  **fixed in 0.7**. Clients query exact `{realm}/rpc/{request_kind}` keys, servers
  declare `{realm}/rpc/*`, and the default-deny ACL grants RPC authority only to
  the authenticated commander.
- **Safety limits no longer interpret free-text units as SI values** — `safety.rs`,
  `ncp-ts/src/safety.ts`, shared govern corpus · _safety_ · **fixed in 0.7**.
  `from_capabilities` binds geofence/speed enforcement only to the explicit
  canonical `pose_position` (`m`) and `velocity_setpoint` (`m/s`) declarations;
  declaration order cannot redirect a limit to an unrelated first channel.
  Missing/mismatched negotiated units start config fail-closed, and live frames
  with the wrong or absent unit HOLD.
- **Truncated safety vectors no longer understate position/speed magnitude** —
  `safety.rs`, `ncp-ts/src/safety.ts`, shared govern corpus · _safety_ · **fixed
  in 0.7**. Enabled geofence/speed limits require negotiated `vec3` channels with
  implicit width 3 or explicit `size=3`; every live tick and predictive horizon
  step must carry exactly three finite values. Short/long vectors fail closed,
  and HOLD/ESTOP output canonicalizes the velocity channel to a zero `m/s` vec3.
- **Geofence enforcement no longer waits until the plant is already outside** —
  `safety.rs`, `ncp-ts/src/safety.ts`, shared govern corpus · _safety_ · **fixed
  in 0.7**. The governor projects canonical velocity over the full period that
  `ActionBuffer` can apply tick 0 and the horizon before TTL, preserving safe
  inward motion while HOLDing/truncating before a crossing. A geofence therefore
  requires a projectable canonical velocity contract and matching effective
  position/command `frame_id` values.
- **Truncating the first unsafe horizon step no longer creates indefinite tick-0
  replay** — Rust/TS safety ports + shared corpus · _safety_ · **fixed in 0.7**.
  An empty horizon is the legacy “replay current channels until TTL” form, not
  “drain after tick 0”; the governor now HOLDs the entire command when the first
  future step is unsafe. Later unsafe steps retain a non-empty safe prefix.
- **TTL and sensor-freshness expiry are inclusive at the deadline** — Rust/TS and
  the shared stateful/govern corpora · _safety_ · **fixed in 0.7**. `elapsed >=`
  the configured deadline HOLDs; an exactly-on-deadline scheduler tick cannot
  actuate once more.
- **A clock rewind can no longer be healed by re-anchoring on rewound time** —
  `CommandWatchdog` / Rust, TS, Python and C behavior corpus · _safety_ · **fixed
  in 0.7**. The watchdog retains a high-water mark, HOLDs through catch-up, and
  requires a fresh non-duplicate command before authority returns.
- **A duplicate or malformed HOLD can no longer leave an older Active horizon
  running** — `ActionBuffer` / shared behavior corpus · _safety_ · **fixed in
  0.7**. Every non-Active mode clears actuation before replay/envelope rejection;
  ESTOP additionally latches.
- **The reference control loop no longer mutates controllers on stale input or
  extends TTL after safety projection** — `NeuroControlLoop` · _safety_ · **fixed
  in 0.7**. Controller panics are contained, restarts reset state, cross-tick
  clock regression HOLDs, and the final TTL is geofence-checked before publish.
- **Link monitoring no longer treats `seq=0` as a valid first delivery** —
  `LinkMonitor` · _safety_ · **fixed in 0.7**. Closed-loop streams require
  `seq>=1`; an unstamped or precision-unsafe sample trips the burst fail-safe
  without refreshing counters, and the CUSUM trips inclusively at its threshold.
- **A slow RPC no longer serializes every lifecycle request** — `ncp-zenoh`
  (`serve_rpc`) · _robustness_ · **fixed in 0.7**. Validated requests run in
  independent blocking-pool tasks behind a 64-request cap held through reply
  delivery, and completed task entries are reaped before accepting more work.
  A synchronous backend cannot pin an async worker; saturation returns a typed
  busy error instead of allocating unbounded work. Aborting the returned serve
  task stops accepting/replying, but cannot forcibly pre-empt a synchronous call
  already executing; that bounded call finishes in the blocking pool.
- **Control ticks no longer create an unbounded number of Zenoh publish tasks** —
  `ZenohControlTransport` · _robustness_ · **fixed in 0.7**. One worker and one
  pending slot conflate Active frames while preserving/retrying fail-safe priority.
- **Observation payloads can no longer claim a session different from their key**
  — core/Zenoh publisher and subscriber gates · _interop/security_ · **fixed in
  0.7**. NCP-aware subscriptions also drop invalid data-plane envelopes before
  invoking application callbacks; generic raw `subscribe` stays caller-validated.
- **Session subscription handles are releasable and borrowed sessions retain
  ownership** — `ncp-zenoh` (`unsubscribe_session`, `close`) · _robustness_ ·
  **fixed in 0.7**. A lifecycle close can drop only that session's callbacks;
  wrapper shutdown drops the rest, and `from_session` never closes its host's
  Zenoh session.
- **Streaming command publish failures are observable** —
  `ZenohControlTransport::send_command` · _robustness_ · **fixed in 0.7**. The
  bounded dispatcher emits a diagnostic and retries HOLD/ESTOP ahead of Active
  instead of silently swallowing a failed fail-safe.
- **The `t` clock domain is explicit** — proto/spec/message docs · _design-gap_ ·
  **fixed in 0.7**. Envelope `t` is producer-local monotonic seconds, never a
  cross-peer deadline; commands/plane observations echo the driving sensor time,
  `seq` performs correlation, and simulation time remains milliseconds.
- **Missing or short codec input is neutral, never an extreme** — `codec.rs` and
  Engram's parity implementation · _safety_ · **fixed in 0.7**. The degraded
  encode path inserts the midpoint of `rate_range_hz`, matching the already-safe
  decode midpoint, so absent sensor components cannot become maximum reverse or
  minimum-range control intent. A regression test pins the reference behavior.
- **Callback panics no longer kill a receive path** — `ncp-zenoh::subscribe` and
  `ncp-core::LocalBus` · _robustness_ · **fixed in 0.7**. Subscriber panics are
  contained and diagnosed while healthy subscribers still receive the sample;
  local queryable panics become `BusError`s rather than unwinding the caller.


## Open — `safe` (internal; no wire change)

These change local behaviour only (no proto/schema/`CONTRACT_HASH`/wire-JSON edit,
no consumer re-pin). Each is a proposal with a concrete fix.

- **Bulk send/receive paths each perform two full copies of the numeric arrays,
  undercutting the 'parse-free / low-copy' design** — `bulk.rs:119` · _overhead_.
  - _Proposed:_ Receive — add consuming accessors (`Column::into_f64(self)` /
    `into_i64(self)`) and an apply that takes the `BulkBlock` by value so the
    matching-width arms move the `Vec` out instead of cloning. Send — add an
    `encode_from(times, values, senders)` that borrows the `Observation`'s slices
    directly to skip the `to_bulk_block` clone. No wire-format change.
- **Gateway bridge timeout (30 s) exceeds Zenoh's default query timeout (~10 s) — a
  slow-but-alive backend yields a spurious 'no reply' to the client** — `main.rs:29`
  · _correctness_. **Mitigated in 0.7:** `request_with_timeout` and the typed
  `step_with_timeout` / `run_with_timeout` APIs now provide per-call alignment and
  `deploy/README.md` documents it. This remains partly a **deployment tuning** concern: a long
  `run_request` (advancing NEST by a large duration) legitimately needs a long
  client-side query timeout, which the gateway cannot control.
  - _Guidance:_ Set `queries_default_timeout` or use the shipped per-call timeout
    APIs for at least the expected step/run duration, and keep
    the gateway's socket timeout aligned so a successful backend never out-lives the
    query window. Document the relationship in `deploy/README.md`.
- **`latest_sensor()` deep-clones the entire `SensorFrame` under a `Mutex` on every
  control tick** — `lib.rs:542` · _overhead_.
  - _Proposed:_ Store the latest frame as `Arc<SensorFrame>` (e.g.
    `ArcSwapOption`), so the reader clones only a pointer. `latest_sensor` returns
    `Option<Arc<SensorFrame>>`; the controller already takes `Option<&SensorFrame>`
    so `arc.as_deref()` works. Trait-API change, not wire.
- **Per-publish key strings are rebuilt via nested `format!` on every frame (plant
  publishes every tick)** — `keys.rs:64` · _overhead_.
  - _Proposed:_ Cache the per-session, per-plane key strings once at transport
    construction and reuse them in the hot `put` calls. Non-wire.
- **Hot action/perception planes are JSON-only; constant string fields
  (`ncp_version`/`kind`/`frame_id`) are re-encoded every frame** — `messages.rs:794` ·
  _design-gap_. (Deliberate: the self-describing JSON wire is the default; see
  `PERFORMANCE.md` for why it is not a measured bottleneck.)
  - _Proposed:_ Do **not** drop the fields (that breaks `validate()`/`diagnose_version`
    and the self-describing wire). Instead add an OPTIONAL negotiated binary
    control-frame codec for high-rate deployments (peers advertise support in the
    capabilities handshake; JSON stays the always-available default), mirroring how
    `BulkBlock` was added additively for observations.
- **Geofence uses the full Euclidean norm over all position elements about a
  hardcoded origin (counts altitude; no configurable center)** — `safety.rs:293` ·
  _design-gap_.
  - _Proposed:_ Document the fence explicitly as a sphere about the frame origin, or
  restrict the norm to horizontal (xy) components and/or add a configurable center
  and per-axis bounds to `SafetyLimits` (the latter extends the wire schema →
  `wire-breaking` for that field).
- **Prospective geofence projection is kinematic, not a certified plant model** —
  `SafetyGovernor` integrates the commanded `velocity_setpoint` as if it were the
  realized world-frame velocity. Inertia, acceleration limits, tracking error,
  wind, actuator lag, and localization uncertainty can still carry a physical
  plant across the boundary after NCP HOLDs. This layer prevents an NCP command /
  replay from *requesting* a modeled crossing; it cannot guarantee containment.
  - _Required deployment control:_ enforce the authoritative geofence and braking
    envelope again in the flight controller / safety PLC using measured state.
    A future NCP dynamics/braking contract would be wire-visible and must be
    negotiated rather than guessed.
- **`SafetyGovernor::govern` deep-clones the whole `CommandFrame` every active
  tick** — `safety.rs:305` · _overhead_.
  - _Proposed:_ Change the signature to take `command: CommandFrame` by value; the
    active path mutates in place and returns it (no clone); HOLD/ESTOP branches still
    build fresh frames. Non-wire.
- **Inline callback subscriber on the lossy perception plane can head-of-line-block
  the safety-critical action plane on the same session** — `lib.rs:466` ·
  _robustness_.
  - _Proposed:_ Offer a bounded handler variant for the perception plane that drops
    instead of back-pressuring (Zenoh `RingChannel`/`FifoChannel`, drained on a
    dedicated task). Keep the inline callback for control/observation. Non-wire.
- **Zenoh subscribe callback forces a `String` + `Vec<u8>` heap allocation on every
  received frame (every sensor/command tick)** — `lib.rs:468` · _overhead_.
  - _Proposed:_ Change the callback bound to `Fn(&str, &[u8])` (matching
    `ncp_core::SubCallback`) and pass borrowed key/payload; callbacks that need to
    retain copy explicitly. Source-API change for downstream callbacks; wire unchanged.
- **`send_command` still serializes/allocates one JSON buffer per command on the
  latency-critical action plane** — `ZenohControlTransport` · _overhead_. The
  former per-command task/key clones are resolved by the bounded long-lived
  dispatcher; serialization remains.
  - _Proposed:_ add an owned `ZBytes` publish path and reuse a capacity-bounded
    serialization buffer where Zenoh ownership permits it. Non-wire.
- **`ZenohBus::put` re-copies the payload via `to_vec()` even when the caller already
  owns the serialized `Vec`** — `lib.rs:441` · _overhead_.
  - _Proposed:_ Add `put_owned(&self, key, payload: Vec<u8>, plane)` (or make `put`
    generic over `impl Into<ZBytes>`) that moves the owned buffer with no copy, and
    route `send_command`/`publish_command`/RPC through it. Non-wire.

## Open — coordinated / wire-visible or deployment policy

- **General JSON envelopes have no universal pre-parse byte, nesting-depth, map,
  string, or channel-array budget shared by all SDKs.** Bulk blocks, predictive
  horizons, codec components, RPC concurrency and command dispatch are bounded,
  but an externally exposed raw JSON endpoint can still spend memory/CPU parsing
  a very large otherwise-structural message before semantic validation rejects
  it. Rust/TS/Python/C also differ in parser depth defaults.
  - _Required deployment control:_ cap payload bytes at the router/socket/API edge
    before parsing and rate-limit unauthenticated/open deployments.
  - _Proposed contract fix:_ agree cross-language maxima and conformance vectors,
    enforce them in every ingress, schema and binding, then ship under a major wire
    version because previously accepted messages would be rejected.


### From the 2026-07-11 deep protocol review (confirmed; wire-0.8 candidates)

A second concentrated external static audit (`NCP_deep_protocol_review_2026-07-11`)
confirmed the defects below. Each is fail-safe in the narrow sense, but the fix is
**wire-visible** — this project treats an acceptance-rule or envelope change as a
MAJOR wire bump (cf. the 0.6 `seq>=1` cut, which changed acceptance with identical
serialization), so these ride the **wire-0.8** line, not a 0.7 patch. See
`ROADMAP.md` §"Wire 0.8" for the sequenced program; IDs are the review's.

**Status (wire-0.8 branch, untagged):** F-01 and F-16 are **LANDED** in-tree with
regression tests + a cross-language vector (increment 1 — the stream/source identity
split, the §7 epoch-keyed receiver, and LinkStatus §8); they move to *Resolved* when
`v0.8.0` is cut. F-04 and the authority-coupled items (F-02/F-22/…) remain **open**
(increment 2+).

- **F-01 · `seq` conflation → a false jam ESTOP — LANDED (wire-0.8 branch)** — the
  wire-0.8 cut gives every data-plane frame its own `stream:{epoch,seq}` (the *only*
  thing `LinkMonitor`/`ActionBuffer`/loss accounting read) distinct from a
  correlation-only `source:{epoch,seq}`. The receiver feeds `stream.seq` (contiguous
  per publisher), so a decimating/event-triggering controller no longer scores as
  loss; and the §7 epoch-keyed receiver state machine rejects a foreign-epoch hijack
  of a live stream and refuses to revive a retired epoch (tracked in a bounded
  per-stream tombstone ring — a DoS guard against hostile epoch churn; an epoch aged
  out of that ring could re-anchor only from an already-safe *expired* HOLD state,
  never displacing a live stream). · _safety/correctness_ ·
  _Regression:_ `resilience.rs::link_monitor_scores_own_stream_seq_not_source_seq_f01`,
  `resilience.rs::action_buffer_epoch_keying_rejects_hijack_and_retired_replay`,
  `transport.rs::foreign_sensor_epoch_cannot_hijack_a_live_stream`, and the
  cross-language `foreign_epoch_cannot_hijack_live_stream` behavior vector. Publisher-id
  binding in `stream.epoch` tag 3 is increment 3 (still unauthenticated; see SECURITY.md).
- **F-04 · predictive-horizon bound over-advertises by one at integer TTL** —
  `max_horizon_len` and the `CommandFrame` validator admit `N = floor(ttl_ms/dt)`
  steps, but `CommandWatchdog` expires *inclusively* (`elapsed >= ttl` HOLDs), so a
  step scheduled at exactly `t = N·dt = ttl` never actuates. The executable bound is
  `ceil(ttl_ms/dt) − 1`; the two agree except when `ttl_ms` is an exact multiple of
  `dt`, where the advertised ride-through is one tick longer than deliverable.
  Fail-safe (the watchdog wins) but it over-states the advertised guarantee.
  Confirmed by `resilience.rs::horizon_bound_over_advertises_by_one_at_integer_ttl_f04`.
  · _correctness_ · _Fix (wire-0.8):_ integer-µs `ttl`/`horizon_dt` and the strict
  invariant `N·dt < ttl`; tightening validation rejects previously-accepted frames.
- **F-16 · `LinkStatus.last_seq` ambiguous under reordering — LANDED (wire-0.8 branch)**
  — the ambiguous top-level `last_seq` is retired (proto `reserved 5`). `LinkStatus`
  now reports the forward high-water via `observed_stream:{epoch,seq}` and the latest
  arrival via `optional last_arrival_seq` (which a late frame lowers *below* the
  high-water without regressing it), plus the status frame's own `stream`/`session`
  envelope a consumer validates before trusting any metric. Presence invariant:
  `observed_stream` present ⇔ `last_arrival_seq` present (both absent before the first
  valid frame). · _diagnostic_ · _Regression:_
  `resilience.rs::link_status_reports_observed_stream_and_last_arrival`,
  `link_status_omits_observed_stream_before_the_first_valid_frame`. Bounded
  reorder/duplicate CLASSIFICATION counters (tags 14/15) are deliberately deferred
  (they cannot be reported identically across bindings yet — see §8 of the design).
  Coverage note: the observed_stream / last_arrival / loss-count semantics are pinned
  by the Rust unit tests above + the wire-schema `validate` corpus; a *cross-language*
  `LinkMonitor` replay corpus awaits a TS `LinkMonitor` port (TS currently mirrors only
  `ActionBuffer` + `CommandWatchdog`), so the §10 LinkStatus behavior vectors are
  Rust-reference-only for now.
- **F-22 · optimistic programmatic defaults** — `SessionClosed::default().ok = true`
  and `ControlStatus::default().safety_ok = true` (`messages.rs`): a missing or
  uninitialised value reads as success/safe, and `#[serde(default)]` fills an absent
  wire field the same way. · _safety_ · _Fix (wire-visible):_ default `ok = false`
  and a tri-state `safety_state = Unknown | Safe | Degraded | Unsafe`, with a `Raw`
  deserialization shape separated from a `Validated` wrapper that authority APIs
  consume (`govern`/`apply` take only the validated type).
- **F-02 / F-05 / F-27 · no wire authority, epoch, or freshness** — restart recovery
  is inferred from TTL expiry rather than an explicit epoch, and there is no
  `session_generation` (server-issued), `stream_epoch`, `publisher_id`,
  `authority_term`/lease, or source-age / Age-of-Information bound (a delayed frame
  gets a fresh full TTL at local receipt). Adequate for a single-writer,
  unauthenticated-or-mTLS-bounded deployment; unsafe for fleets, failover, or
  partition (split-brain authority is undefined). · _design-gap_ · _Fix (wire-0.8):_
  a `StreamHeader` with epoch/generation/authority fields + a negotiated
  freshness/clock profile (review Part III). Partially noted already under the 0.6
  `seq>=1` residual and the "arrival-based TTL" resilience note.
- **F-12 / F-13 · simulation RPCs are neither idempotent nor single-owner** —
  `StepRequest`/`RunRequest` carry no `request_id`, expected/returned sim revision,
  or dedupe contract, and the Zenoh client returns the first matching reply — so a
  lost reply plus retry can double-advance the simulation, and a stray responder can
  win a race. · _correctness_ · _Fix (wire-0.8):_ `RequestMeta{request_id,
  expected_sim_revision}` + `result_sim_revision`, a bounded idempotency cache
  (same ID → same result; same ID, different digest → typed conflict), and
  responder-identity binding / ambiguity rejection.
- **F-03 / 2.2 · generic zero is not a universal safe action, and NCP `Estop` is a
  protocol label, not a certified physical E-stop** — `SafetyGovernor` synthesises an
  all-zeros command as the safe action, but zero thrust / steer / brake / torque /
  valve is plant-specific, and a zero-velocity setpoint is a HOLD request, not an
  emergency stop. The protocol must not infer a safe action from frame shape alone.
  · _safety_ · _Fix (wire-0.8):_ a plant-owned `SafeActionProfile` with per-channel
  semantics, negotiated and acknowledged by ID; reserve `ESTOP` for a profile that
  defines the actual plant response and an independent local stop path.

---
_Status tracked against the current tree; resolved items cite the fixing commit or
the module that now guards them, each with a regression test._
