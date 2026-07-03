# Known Limitations & Hardening Backlog

> Wire **v0.5.2**. This tracks findings from an adversarial review of NCP
> (correctness, safety, robustness, overhead) **and their current status**. Each
> notes whether the fix changes the on-wire contract (`wire-breaking`, needs a
> version bump + consumer buy-in across Engram/crebain/prisoma) or is internal
> (`safe`). NCP is a generic, shared contract, so conservatism on the still-open
> items is deliberate.
>
> **Status (35 findings): 9 resolved · 26 open (23 `safe` · 3 `wire-breaking`).**
> All **3 high-severity** safety findings are **resolved** (wire-safe, with
> regression tests). The remaining 26 are medium/low; the 3 `wire-breaking` ones
> are gated behind a wire version bump. Line numbers below are indicative and may
> drift — search by symbol.


## Resolved

Fixed in-tree, each wire-safe and covered by a regression test. Do not re-open
these without checking the cited code first.

### High — safety / robustness (all three closed)

- **decode: per-column allocations now carry a cumulative budget — the
  overlapping/duplicate-column memory-amplification (OOM DoS) is closed** —
  `bulk.rs` (`BulkBlock::decode`) · _safety_ · **fixed** (commit `0672168`).
  A running `alloc_budget` (`= bytes.len()`) is charged `checked_sub(data_len)`
  per column and rejects when the declared payload exceeds the input, so a tiny
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
  a non-finite `ttl_ms`/`horizon_dt_ms` (or `dt <= 0`) now returns `0` (no replay).


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
- **codec `encode` maps a missing/short sensor channel to `rate_range_hz.0` (=
  `value_range` minimum), the same 'missing data → extreme actuation' hazard the
  `decode` side was explicitly hardened against** — `codec.rs:128` · _safety_.
  **Parity-coupled:** the same fallback exists in Engram's `codec.py:72`, so a fix
  must land in **both** peers together to keep the reference codec bit-faithful
  (the `decode`-side neutral-midpoint fix was made in both — this is the missing
  encode half).
  - _Proposed (both peers):_ On a missing/short channel, insert the neutral rate —
    the midpoint of `rate_range_hz` (equivalently the rate for the `value_range`
    midpoint), `0.5 * (rate_range_hz.0 + rate_range_hz.1)` — instead of the low end,
    or skip emitting the population so downstream hold-last applies. Degraded-path
    only; the rate-map structure is unchanged.
- **Free-text channel units are never validated against the SI units
  `SafetyLimits` assumes; the speed clamp and geofence silently mis-scale on a unit
  mismatch** — `safety.rs:369` · _safety_.
  - _Proposed:_ At construction (`with_channels`/`from_capabilities`) require the
    negotiated `ChannelSpec.unit` of the velocity/position channels to equal the
    canonical SI unit the limit is expressed in (`m/s`, `m`); on mismatch (or absent
    unit when a limit is set) start `config_fail_closed = true`. Spec-wise, pin a
    small canonical-unit vocabulary for safety-relevant channels in
    `NEURO_CYBERNETIC_PROTOCOL.md` rather than leaving `unit` free text.
- **Channel arity is never validated against `ChannelKind`/size; a truncated vec3
  position frame makes the geofence under-report distance and fail to ESTOP** —
  `safety.rs:293` · _safety_. (The *empty*-vector case now fails closed; a
  *short-but-nonempty* vector still computes a magnitude over too few components.)
  - _Proposed:_ Validate channel arity against the negotiated `ChannelSpec` before
    enforcement: when the geofence/velocity channel's `ChannelKind` is vec3 (or its
    size is set), require the data length to equal that width, else fail closed
    (HOLD for velocity, ESTOP/HOLD for the un-evaluable geofence). Optionally surface
    a per-kind arity check in `validate()`.
- **Gateway bridge timeout (30 s) exceeds Zenoh's default query timeout (~10 s) — a
  slow-but-alive backend yields a spurious 'no reply' to the client** — `main.rs:29`
  · _correctness_. This is partly a **deployment tuning** concern: a long
  `run_request` (advancing NEST by a large duration) legitimately needs a long
  client-side query timeout, which the gateway cannot control.
  - _Proposed / guidance:_ Set the client's Zenoh `queries_default_timeout` (or a
    per-call `.timeout(..)`) to at least the expected step/run duration, and keep
    the gateway's socket timeout aligned so a successful backend never out-lives the
    query window. Document the relationship in `deploy/README.md`.
- **RPC queryable handler runs serially in the recv loop — one slow/hung backend
  stalls all control-plane RPC** — `lib.rs:319` · _robustness_.
  - _Proposed:_ Clone the `Arc<handler>` and `tokio::spawn` a task per received query
    (handler call + `query.reply().await` inside it) so concurrent RPCs are served in
    parallel; the recv loop only dispatches. Single-key on the wire unchanged.
- **Subscriptions are never removed — per-session subscribe on a long-lived bus
  leaks handles and keeps firing callbacks for closed sessions** — `lib.rs:476` ·
  _design-gap_.
  - _Proposed:_ Return an opaque guard from `subscribe*` whose `Drop` undeclares it,
    or add `close_session_subs(session_id)`. API change only, not wire.
- **`close()` unconditionally closes the underlying session, including one borrowed
  via `from_session`** — `lib.rs:484` · _robustness_.
  - _Proposed:_ Track ownership (`owned: bool`, true only for `with_config`/`open*`)
    and make `close()` a no-op / undeclare-only when not owned; or document that
    `from_session` callers must never call `close()`.
- **`latest_sensor()` deep-clones the entire `SensorFrame` under a `Mutex` on every
  control tick** — `lib.rs:542` · _overhead_.
  - _Proposed:_ Store the latest frame as `Arc<SensorFrame>` (e.g.
    `ArcSwapOption`), so the reader clones only a pointer. `latest_sensor` returns
    `Option<Arc<SensorFrame>>`; the controller already takes `Option<&SensorFrame>`
    so `arc.as_deref()` works. Trait-API change, not wire.
- **`encode` silently truncates `n_cols`/`total_len`/offsets via unchecked
  `as u16`/`as u32` casts, producing corrupt blocks instead of erroring** —
  `bulk.rs:281` · _robustness_.
  - _Proposed:_ Add `debug_assert!`s, or a fallible `try_encode() -> Result<…,
    BulkError>` using `u16::try_from`/`u32::try_from` (→ `BulkError::Overflow`),
    keeping infallible `encode()` as a thin wrapper. No wire-format change.
- **Realm string is interpolated into every key without validation — a
  wildcard/empty/trailing-slash realm silently widens or breaks the keyspace** —
  `keys.rs:53` · _robustness_. (Session `id`/`name` segments *are* validated; the
  realm is not.)
  - _Proposed:_ Add a `valid_realm()` check (non-empty; each `/`-separated segment
    passes `valid_id_segment`; no `* $ # ?`/whitespace; no leading/trailing/double
    slash) and apply it in `Keys::new` and when the gateway reads `NCP_REALM`,
    returning an error instead of building corrupt keys.
- **Per-publish key strings are rebuilt via nested `format!` on every frame (plant
  publishes every tick)** — `keys.rs:64` · _overhead_.
  - _Proposed:_ Cache the per-session, per-plane key strings once at transport
    construction and reuse them in the hot `put` calls. Non-wire.
- **`Keys` builders panic (`assert!`) on an invalid id — process abort instead of
  fail-safe reject** — `keys.rs:65` · _robustness_.
  - _Proposed:_ Provide fallible builders (`try_session`/`try_sensor` → `Result`)
    and use them on any wire-facing path; reserve `assert!`/panic for clearly-internal,
    already-validated callers.
- **The per-frame timestamp field `t` has no specified unit or clock domain on any
  message** — `messages.rs:770` · _design-gap_.
  - _Proposed:_ Pin `t`'s contract in `proto/ncp.proto` and
    `NEURO_CYBERNETIC_PROTOCOL.md` — recommend "seconds, sender's monotonic clock,
    not comparable across peers; use `seq` for correlation and the plant's own clock
    for liveness". Or drop `t` in favour of `seq` + `sim_time_ms`.
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
- **`serve_rpc` cannot be stopped without closing the session, and its doc claims a
  returned task that does not exist** — `lib.rs:318` · _api_.
  - _Proposed:_ Return the `JoinHandle`/`AbortHandle` (or a guard whose `Drop`
    aborts) from `serve_rpc` and fix the doc to match.
- **Action-plane publish errors are silently swallowed in the streaming control
  transport** — `lib.rs:538` · _robustness_.
  - _Proposed:_ On `Err` from `publish_command`, increment a counter or emit a
    throttled diagnostic (as the sensor-decode path already does), keeping the send
    non-blocking.
- **Zenoh subscribe callback forces a `String` + `Vec<u8>` heap allocation on every
  received frame (every sensor/command tick)** — `lib.rs:468` · _overhead_.
  - _Proposed:_ Change the callback bound to `Fn(&str, &[u8])` (matching
    `ncp_core::SubCallback`) and pass borrowed key/payload; callbacks that need to
    retain copy explicitly. Source-API change for downstream callbacks; wire unchanged.
- **`send_command` allocates per command on the latency-critical action plane
  (`Keys`/`String` clone + `spawn`)** — `lib.rs:530` · _overhead_.
  - _Proposed:_ Make `Keys.realm: Arc<str>` and store `session_id: Arc<str>` so
    clones are refcount-only; replace the per-command `tokio::spawn` with one
    long-lived publisher task fed by a `watch`/bounded-mpsc. Non-wire.
- **`ZenohBus::put` re-copies the payload via `to_vec()` even when the caller already
  owns the serialized `Vec`** — `lib.rs:441` · _overhead_.
  - _Proposed:_ Add `put_owned(&self, key, payload: Vec<u8>, plane)` (or make `put`
    generic over `impl Into<ZBytes>`) that moves the owned buffer with no copy, and
    route `send_command`/`publish_command`/RPC through it. Non-wire.


## Open — `wire-breaking` (needs a version bump + fleet buy-in)

These change on-wire addressing or acceptance rules, so they must ride a wire
version bump with all peers (Engram/crebain/prisoma) re-pinned in lockstep — hence
they are documented, not silently applied. See `VERSIONING.md`.

- **Single RPC key per realm prevents per-verb ACL — the shipped ACL lets an
  observer/robot close or step any session** — `zenoh-access-control.json5:81` ·
  _design-gap_ · **wire-breaking**.
  - _Proposed:_ Split the privileged verbs onto distinct key-expressions (e.g.
    `{realm}/rpc/open` vs `{realm}/rpc/admin`) so the ACL can allow `open` but
    restrict `step`/`run`/`close` to the commander; or authorize the caller's proven
    identity per verb in the RPC handler. The key-split changes on-wire RPC addressing.
- **`ncp_version` is neither required nor checked on the data plane: an absent
  version defaults to our own and incompatible-but-parseable sensor/command frames
  are accepted** — `messages.rs:1219` · _design-gap_ · **wire-breaking**.
  - _Proposed:_ Have data-plane decoders call `check_version(frame.ncp_version,
    strict)` on each parsed frame and drop on mismatch, treating an absent
    `ncp_version` as incompatible; at minimum add `ncp_version` to `required_fields()`
    for every kind so `validate()` enforces the spec's "every message carries
    `ncp_version`".
- **`seq == 0` is an always-accept escape hatch that bypasses the normative
  anti-replay/anti-stale guarantee — and `seq = 0` is the wire default** —
  `resilience.rs:48` · _safety_ · **wire-breaking**.
  - _Proposed:_ Restrict the `seq == 0` escape hatch to the pull/sim service path.
    On the streaming action plane require strictly-positive, strictly-advancing `seq`
    (the plant-side `ActionBuffer`/`CommandWatchdog` must not treat `seq == 0` as
    advancing), and add "`seq > 0`" as a conformance requirement for `command_frame`
    on the action plane. Document `seq = 0` as "anti-replay disabled — never use on
    the action plane."

---
_Status tracked against the current tree; resolved items cite the fixing commit or
the module that now guards them, each with a regression test._
