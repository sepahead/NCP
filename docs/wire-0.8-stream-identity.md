# Wire 0.8 — stream identity, source correlation, session fencing (design freeze)

> **Status:** design, targeting the **untagged** wire-`0.8` line. The proto is cut
> (`proto/ncp.proto`); Rust/TS/C/Python, schemas, vectors, and the conformance corpus
> are implemented and reviewed against this record **before** any `v0.8.0` tag exists
> (`AGENTS.md` runbook: everything green before the tag, never tag-then-fix).
>
> **Provenance:** closes **F-01** and lays the identity/fencing envelope for **F-02**
> (2026-07-11 deep review, `KNOWN_LIMITATIONS.md`), per the maintainer's normative
> design decisions. The review's generic `StreamHeader` was **rejected** in favour of
> separate, typed concerns.

## 1. Problem (F-01)

Wire 0.7's single top-level `seq` means two incompatible things: an origin delivery
sequence on `SensorFrame`, but a *source echo* on `CommandFrame`/plane
`ObservationFrame` — which `LinkMonitor`/`ActionBuffer` then read as delivery loss. A
decimating controller (commands for sensor seqs `1` then `8`) is scored as six lost
commands, CUSUM hits `5.65 ≥ 5.0`, and ESTOP latches on a healthy transport.

## 2. Four separate, typed concerns

Never a generic `header`. Their scope/lifetime/trust differ.

| Concept | Describes | Home |
|---|---|---|
| **stream** | *this* frame's ordered stream identity + position | `stream: StreamPosition` |
| **source** | the frame that drove this frame | `source: StreamPosition` |
| **session** | which live opening of the session | top-level `session_id` + `session: SessionRef{generation}` |
| **authority** | permission to control a plant | separate `authority` object *(deferred, §9)* |

## 3. Types

```proto
message StreamPosition {
  string epoch = 1;   // opaque per-incarnation id; canonical lowercase UUIDv4; REQUIRED; EQUALITY-ONLY, unordered
  int64  seq   = 2;   // position within the incarnation; REQUIRED; 1 .. 2^53-1
  // tag 3 reserved BY POLICY (registry note, NOT proto-`reserved`) for future publisher_id
}
message SessionRef {
  string generation = 1;   // server-issued opaque incarnation id (UUIDv4); "" = unset
}
```

**`epoch` naming:** kept `epoch` (not `incarnation`) with the frozen "equality-only,
unordered" clause — the rename is required only if the name implies ordering, which
the spec forbids.

## 4. Effective identity & the no-fallback rule

The effective session identity is the **inseparable pair** `(session_id,
session.generation)` (with `realm` from the deployment/key). Every post-open frame
addressing a session MUST carry both, validated **atomically** against the live pair
under the same session-state lock, **before any side effect** (stimulus, advance,
close, TTL refresh, epoch/seq state, LinkMonitor, mode change, ESTOP latch):

```
missing session_id           -> reject         wrong/stale generation      -> reject
missing session.generation   -> reject         unknown session_id          -> reject
payload session_id != key    -> reject         wrong-session ESTOP         -> reject (no latch)
```

**No repair, ever:** a receiver must never fill `session_id` from the key, nor fill
`generation` from the currently-active session. That would turn stale/malformed
traffic into valid traffic. Compare against the **actual received sample key**, not a
wildcard subscription selector.

`session.generation` (incarnation fencing: *is this the live incarnation?*) is
orthogonal to a future `request_id` (operation dedup: *did this already run?*); the
future dedup key is `(session_id, generation, request_id)`.

## 5. Application per message type

Top-level `seq` is deleted and `reserved` (number **and** name) on every data-plane
frame — no 0.8 alias; the old observation `seq == 0` sentinel is replaced by `source`
**absence**.

| Message | `session_id` | `session` (generation) | `stream` | `source` |
|---|---|---|---|---|
| `OpenSession` | required (requested) | **absent** (incarnation doesn't exist yet) | — | — |
| `SessionOpened` | required | **iff `ok == true`** (issues it) | — | — |
| `StepRequest`/`RunRequest` | required | required | — | — |
| `StimulusFrame` | required | required (nested: == outer) | — | — |
| `CloseSession`/`SessionClosed` | required | required | — | — |
| `ErrorFrame` | conditional | conditional (copy both or neither) | — | — |
| `SensorFrame` | required *(new)* | required | required | absent (origin) |
| `CommandFrame` | required *(new)* | required | required | required for closed-loop Active |
| `ObservationFrame` | required | required | required | driving sensor (plane form); absent for pull/RPC |
| `BulkObservation` | required | required | required | trigger/watermark; absent for pull/RPC |
| `ControlStatus` | required *(new)* | required | required (when periodic) | — |
| `LinkStatus` | required | required | own stream required | `observed_stream` (the monitored stream) |

Invariant: **every message carrying `session: SessionRef` also carries a required
`session_id`**, except a message that *creates* rather than *addresses* a session
(`OpenSession`). `ErrorFrame` carries both or neither.

**Why `session_id` on the control plane (new):** transport-agnosticism. The normative
`Control(stream SensorFrame) returns (stream CommandFrame)` gRPC stream has no Zenoh
key to recover `session_id` from; the same frame must be interpretable across every
declared transport. The Zenoh key becomes a *redundant* binding validated for
equality, not the sole home of identity.

## 6. Frozen semantics

- **`stream.epoch`** — one logical-stream incarnation, scoped by `session generation +
  authenticated publisher + concrete routing key + message kind`. Mint a fresh epoch
  per logical stream and per restart. Equality-only; never ordered/timestamp/authority.
- **`stream.seq`** — starts at 1 per epoch, +1 per new logical frame (assigned **after**
  intentional decimation; a transport retry keeps its seq; a TTL-refreshing command is
  a new logical frame → next seq), never wraps within an epoch. It is the **only**
  sequence loss/`LinkMonitor`/`ActionBuffer` read.
- **`source`** — a complete `{epoch, seq}` (a bare scalar can't disambiguate a sensor
  restart's reused `seq`). Correlation/provenance only; never loss accounting; its seq
  may repeat or jump. Omit when absent (no `seq = 0`). It is the *single* directly-driving
  frame (primary watermark), **not** an exhaustive dependency graph — a future bounded
  `input_watermarks` handles fusion. **Scope:** `command.source` is implicitly scoped to
  the enclosing frame's `(session_id, generation)`; cross-session source references are
  **invalid** in 0.8.
- **`t` / `source_t`** — `t` is uniformly THIS publisher's local monotonic creation time,
  scoped to `stream.epoch`; the driving sensor's time travels explicitly in optional
  `source_t`. No frame smuggles another's clock into `t`.
- **`session_id` syntax** — same as a routing key segment plus a length bound: 1..64
  UTF-8 bytes, no `/ * $ # ?`, no whitespace/control chars, case-sensitive, exact
  decoded-string equality (no case-folding / Unicode normalization by receivers). An
  ASCII-only profile is preferred for identical cross-language behaviour.

## 7. Receiver state machine

Key state by `scope = session generation + authenticated publisher + exact routing key
+ message kind`; keep `active_epoch`, `last_seq`, `retired_epochs`.

```
1. Validate ncp_version, kind, (session_id == key), (session.generation == live), publisher.
2. If the frame can actuate, validate authority context.
3. epoch == active_epoch:  seq <= last_seq -> reject (dup/stale, NO watchdog refresh);
                           seq  > last_seq -> record gap; accept; last_seq = seq.
4. epoch != active_epoch:  accept ONLY via an authorized transition; retire old; reset
                           last_seq + LinkMonitor; activate new.
5. epoch in retired       -> reject even with a huge seq.
```

A different random epoch MUST NOT auto-replace the active stream. **Authorized epoch
transition** = explicit authenticated open-stream/session transition; OR a current
authority lease naming the new epoch; OR (constrained single-publisher profile — the
strongest guard before authentication lands) prior-stream expiry **+** same
authenticated publisher **+** current session generation, retaining retired-epoch
tombstones for the session lifetime. `LinkMonitor` runs only on the accepted scope +
active epoch + `stream.seq`, resetting **only after** an accepted transition.

## 8. LinkStatus (F-16) — final shape

Keep the identity-critical fields; **defer** the diagnostic counters the bounded
algorithm cannot report identically across bindings.

- **`stream`** (own) — every `LinkStatus` frame's own `StreamPosition`; a consumer
  validates it (stale/dup status frames rejected) **before** trusting any reported
  burst/loss/high-water — the CUSUM burst feeds a fail-safe, so status ordering matters.
- **`observed_stream`** — the monitored stream's `{active epoch, forward high-water seq}`;
  never regresses in-epoch; changes epoch only on an accepted transition; a foreign/late
  arrival never moves it; **absent before the first valid observed frame**.
- **`last_arrival_seq`** (`optional int64`) — the most recent valid in-epoch arrival
  presented (incl. late/dup); `== observed_stream.seq` on forward arrival, `<` it under
  reordering; rejected frames don't update it. **Presence invariant:** `observed_stream`
  present ⇔ `last_arrival_seq` present (both absent while a pre-first-frame burst trips).
- **Deferred (tags 14/15 left free; `session` occupies 13):** reorder/duplicate counts — the current bounded
  (≤4096) reconciliation set cannot distinguish a true duplicate from a very-late first
  arrival, so counts would be implementation-dependent. They land later with precise
  names (`late_reconciled_count`, `duplicate_or_stale_count`, `outside_reorder_window_count`)
  once a bounded reorder window is normatively fixed.
- **`received`/`lost`/`loss_rate` precise meaning (comments frozen in-proto):** `received`
  = distinct in-epoch positions recognized delivered (excludes duplicates); `lost` =
  currently-unresolved gaps (may *decrease* on late reconcile); `loss_rate` = lost /
  observed span, not / raw arrivals.
- **Pre-tag item:** `observed_stream.epoch` says *which incarnation* but not *which named
  substream* (`sensor/imu` vs `command/cmd_vel`). Before tagging, require either
  key-bound identity (validated) or payload `observed_kind`/`observed_name`.

## 9. Increment plan

1. **Increment 1 (this effort).** `StreamPosition`; `stream`+`source`+`source_t`;
   removed/reserved top-level `seq`; the `t` fix; `session_id` on the control plane;
   `session: SessionRef{generation}` issued on `SessionOpened` and required on every
   post-open session-scoped frame (incl. Step/Run/Close/SessionClosed/Stimulus, and the
   data plane), conditional on `ErrorFrame`; the receiver state machine in the
   constrained single-publisher profile; LinkStatus §8; the profile-independent §10
   vectors; Rust core → schemas → conformance green, then `ncp-ts`, then
   `ncp-cpp`/`ncp-python`, then the consumer migration.
2. **Increment 2 — authority (F-02).** `authority{term, lease_id}` on command/stop
   frames only, plant-issued lease validation, the authorized epoch-transition path,
   RPC idempotency (`request_id`, sim revision).
3. **Increment 3 — identity binding.** `publisher_id` in `StreamPosition` tag 3, bound
   to the authenticated principal + registration + session generation + permitted key.
4. Later: applied-command/stop acks, safe-action profiles, then the `v0.8.0` cut.

## 10. Conformance vectors required before the v0.8 tag

★ = profile-independent, lands in increment 1.

**Stream/source (F-01):** ★ decimation `1,2`/source `1,8` → 0 loss · ★ command loss
`1,3` → 1 missing · ★ duplicate `42,42` → reject, no TTL refresh/watchdog extend · ★
source restart `C{40,41}`/source `S1:900→S2:1` → continuous, no loss · ★ retired-epoch
replay → reject · ★ `source` absent valid per kind; `source:{epoch,seq:0}` invalid.

**Session fencing:** G1 Step/Run/Close after G2 open → reject, G2 untouched · outer G2
/ nested stimulus G1 → reject before stimulus · post-open request missing `session` →
reject (never infer) · `SessionOpened(ok=true)` without `session` → invalid;
`(ok=false)` without → valid · delayed `SessionClosed(G1)` while client on G2 → ignored
· `ErrorFrame` for stale G1 → echoes G1 as context only.

**Key/payload `session_id`:** payload==key, live gen → accept · payload≠key → reject
before state/TTL · stale gen → reject before side effects · missing payload
`session_id` (even with key `s1`) → reject · wrong-session ESTOP → reject, no latch ·
wildcard subscription → compare actual sample key · gRPC `Control` frame → resolves
without Zenoh context · cross-session `command.source` → reject.

**LinkStatus:** arrivals `1,2,5,3` → `observed_stream.seq=5`, `last_arrival_seq=3`, one
unresolved gap (4) · `…,3,3` → high-water 5, distinct-received unchanged on the 2nd `3`
· accepted C1→C2 transition → `observed_stream=C2/1`, metrics reset, own stream
continues · own-stream `20` then `19` → `19` rejected, newer burst not rolled back ·
invalid seq before any valid observed frame → `burst=true`, own stream present,
`observed_stream`+`last_arrival_seq` absent · foreign/retired observed epoch → no reset.

## 11. Consumer migration (2026-07-11 survey)

- **prisoma / `ncp-observer`** — 100% source-correlation. Every `.seq` join site migrates
  to `source.{epoch,seq}` (`sensor.seq→sensor.stream.seq`, `command.seq→command.source.seq`,
  `obs.seq→obs.source.seq`), joining on the full `{epoch,seq}`; adopting `stream.epoch`
  retires its `RESET_MARGIN` heuristic. **Trap:** binding to `stream_seq` instead of
  `source` → three independent counters that never join (silent zero-sample regression).
  Now also reads/validates the new payload `session_id`/`session.generation`.
- **crebain** — needs **both**. `sensor_frame_from_pose` stamps `SensorFrame.stream`
  (+ `session_id`/`session`); `command_for_buffer` copies `stream` (ActionBuffer
  dedup/`seq>=1` gate) **and** `source` (sensor echo); TS `useDroneController` `seq>=1` +
  `{estop,seq:0}` move to `stream.seq`. Re-pin all four pins + re-install `@sepahead/ncp`.
  The `ncp` Rust feature is off by default — the break surfaces only under the
  `check:rust:ncp`/TS jobs; don't let the feature gate hide it.
