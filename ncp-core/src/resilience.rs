//! Degraded-link resilience for the action and perception planes — see
//! `RESILIENCE.md`. Two plant-side primitives, both pure/dependency-light:
//!
//! - [`ActionBuffer`] — **packetized predictive control**: holds the latest
//!   `CommandFrame` and its (short) horizon of future setpoints, and returns the
//!   setpoint to apply *now*, replaying the horizon through dropouts and failing
//!   safe (HOLD) once the command expires (`ttl_ms`, via [`CommandWatchdog`]) or
//!   the horizon drains. A single lost packet becomes a non-event.
//! - [`LinkMonitor`] — a **seq-gap loss + CUSUM burst detector** over the message
//!   `seq` stream (present on both planes), producing a [`LinkStatus`]. Separates
//!   ordinary loss (poor connection) from a sustained burst (possible jam). It
//!   detects; the SafetyGovernor decides.

use crate::messages::{
    ChannelValue, CommandFrame, LinkStatus, Map, Mode, SessionRef, StreamPosition, WireFrame,
    JSON_SAFE_INTEGER_MAX, MAX_HORIZON_STEPS,
};
use crate::safety::{CommandWatchdog, MAX_TTL_MS};

/// Plant-side packetized-predictive-control buffer (the deadline backstop).
#[derive(Clone, Debug, Default)]
pub struct ActionBuffer {
    latest: Option<CommandFrame>,
    recv_s: f64,
    watchdog: CommandWatchdog,
    /// Latched ESTOP (mirrors `SafetyGovernor`): once an ESTOP command is ingested
    /// the buffer fails safe (HOLD) on every subsequent `active()` until a
    /// authorized operator [`reset`]s it — a later non-ESTOP command does NOT clear it.
    /// A plain HOLD command stays non-latching (it self-clears on the next Active).
    estop: bool,
    /// Highest accepted command `seq`, for monotonic-forward acceptance (drop
    /// stale/duplicate/reordered frames). Wire 0.6: `seq >= 1` is mandatory —
    /// `seq < 1` is never accepted (no escape hatch), and expiry never resets the
    /// high-water mark.
    last_seq: i64,
    /// The declaration-bound stream epoch. Once established, a foreign epoch is
    /// rejected even after expiry; a new declaration uses a fresh ActionBuffer.
    active_epoch: Option<String>,
    /// An ESTOP reset retires the complete session-bound admission context. The
    /// old buffer can be inspected but never accepts another frame.
    retired: bool,
}

impl ActionBuffer {
    pub fn new() -> Self {
        Self::default()
    }

    /// Ingest a command accepted into this local session/declaration context at
    /// time `now_s`. A remote caller must first enforce authenticated actor/plane,
    /// exact route/session-generation, and typed wire admission; this buffer is not
    /// a network ingress gate. Within that admitted context, a stale, duplicate, or
    /// reordered Active command (`seq <=` the high-water mark) is dropped forever —
    /// expiry never reopens replay. Every non-Active mode clears buffered actuation
    /// before local replay checks; ESTOP also latches.
    ///
    /// Wire 0.6: `seq < 1` (unstamped/negative, including the `0` serde default)
    /// is NEVER accepted — the pre-0.6 "`seq == 0` always advances" escape hatch
    /// let a default-constructed/hostile frame bypass replay rejection and refresh
    /// the deadline. One buffer is declaration-bound to its first epoch. A restart,
    /// lower sequence, or foreign epoch requires a fresh session/declaration and
    /// buffer; neither timeout nor HOLD authorizes an in-place re-anchor. Mirrors
    /// [`CommandWatchdog::on_command`].
    pub fn on_command(&mut self, now_s: f64, command: CommandFrame) {
        if self.retired {
            return;
        }
        // Fail-safe priority: a HOLD/INIT/future non-actuating mode immediately
        // clears the buffered setpoint even if its envelope is malformed or its
        // seq is stale/duplicate. Dropping it would leave the previous Active
        // horizon running until ttl — fail-open. Only Active can add authority.
        if command.mode != Mode::Active {
            self.latest = None;
        }
        if command.mode == Mode::Estop {
            self.estop = true; // latch even if the frame is stale/out-of-order/unstamped
        }
        if command.mode != Mode::Estop && command.validate_wire().is_err() {
            return;
        }
        if !(1..=JSON_SAFE_INTEGER_MAX).contains(&command.stream.seq) {
            return; // unstamped/invalid stream.seq: never buffered (ESTOP latched above)
        }
        // One ActionBuffer belongs to one authorized stream declaration. Expiry is
        // not permission to adopt a foreign epoch; a restart constructs a fresh
        // session/declaration/buffer context.
        match &self.active_epoch {
            None => self.active_epoch = Some(command.stream.epoch.clone()),
            Some(active) if *active != command.stream.epoch => {
                return;
            }
            Some(_) => {} // same epoch: fall through to the seq discipline
        }
        if command.stream.seq <= self.last_seq {
            return; // duplicate/stale/reordered, including after expiry
        }
        self.last_seq = command.stream.seq;
        if command.mode != Mode::Active {
            // Preserve the high-water mark against a live-stream replay, but do
            // not refresh the actuation watchdog or buffer a non-Active frame.
            return;
        }
        self.watchdog
            .on_command(now_s, command.ttl_ms, command.stream.seq);
        self.recv_s = now_s;
        self.latest = Some(command);
    }

    /// Clear this local ESTOP latch and permanently retire the buffer's session and
    /// stream admission context. The deployment must complete the generation cut
    /// and construct a fresh ActionBuffer for the new SessionOpened generation.
    pub fn reset(&mut self) {
        self.estop = false;
        self.latest = None;
        self.recv_s = 0.0;
        self.watchdog = CommandWatchdog::new();
        self.last_seq = 0;
        self.active_epoch = None;
        self.retired = true;
    }

    /// True once ESTOP reset retired this session-bound buffer.
    pub fn is_retired(&self) -> bool {
        self.retired
    }

    /// True while ESTOP is latched.
    pub fn is_estopped(&self) -> bool {
        self.estop
    }

    /// The setpoint channels to apply at `now_s`, or `None` if the plant must fail
    /// safe (HOLD): a latched ESTOP, no command, expired `ttl_ms`, any non-`Active`
    /// mode (HOLD/ESTOP/INIT — or any mode added later), or the predictive horizon
    /// has drained. `channels` is tick 0; `horizon[i]` is tick i+1 at
    /// `horizon_dt_ms` spacing.
    pub fn active(&self, now_s: f64) -> Option<Map<ChannelValue>> {
        if self.estop {
            return None; // latched fail-safe
        }
        if self.watchdog.should_hold(now_s) {
            return None;
        }
        let cmd = self.latest.as_ref()?;
        // ALLOWLIST, not denylist: only `Active` actuates. `Init` is the
        // startup/handshake mode during which a plant must NOT drive, and a
        // denylist (`Hold | Estop`) would also actuate on `Init` and on any Mode
        // variant added later — a fail-OPEN default. Fail safe to HOLD on
        // anything that is not explicitly `Active`.
        if !matches!(cmd.mode, Mode::Active) {
            return None;
        }
        let dt = cmd.horizon_dt_ms.unwrap_or(0.0);
        if dt <= 0.0 || cmd.horizon.is_empty() {
            return Some(cmd.channels.clone()); // legacy single-step
        }
        let tick = (((now_s - self.recv_s) * 1000.0) / dt).floor() as i64;
        if tick <= 0 {
            Some(cmd.channels.clone())
        } else {
            // tick k -> horizon[k-1]; beyond the horizon -> drained -> HOLD.
            cmd.horizon.get((tick - 1) as usize).cloned()
        }
    }

    /// True if the plant must HOLD at `now_s` (no usable setpoint).
    pub fn should_hold(&self, now_s: f64) -> bool {
        self.active(now_s).is_none()
    }
}

/// Cap the number of future horizon steps to the strict watchdog deadline.
///
/// Horizon entry `i` (zero based) is scheduled at `(i + 1) * horizon_dt_ms`, while
/// [`CommandWatchdog`] expires inclusively at `elapsed >= ttl_ms`.  A setpoint at
/// exactly the TTL boundary is therefore not executable.  The exact bound is
/// `ceil(ttl_ms / horizon_dt_ms) - 1`, not `floor(ttl_ms / horizon_dt_ms)` (the two
/// differ when TTL is an integer multiple of the cadence).
pub fn max_horizon_len(ttl_ms: f64, horizon_dt_ms: f64) -> usize {
    // A non-finite ttl/dt (or dt <= 0) has no bounded horizon: `Inf / dt` floors to
    // `Inf`, which `as usize` saturates to `usize::MAX` — a garbage/`+Inf` ttl would
    // then authorise an effectively unbounded predictive horizon. Return 0 (no
    // replay) instead, so a non-finite input fails safe rather than open.
    if !ttl_ms.is_finite() || !horizon_dt_ms.is_finite() || horizon_dt_ms <= 0.0 {
        return 0;
    }
    let ratio = ttl_ms.clamp(0.0, MAX_TTL_MS) / horizon_dt_ms;
    let steps = (ratio.ceil() - 1.0).max(0.0);
    if !steps.is_finite() {
        return 0;
    }
    (steps.max(0.0) as usize).min(MAX_HORIZON_STEPS)
}

/// seq-gap loss + CUSUM burst detector. Feed each message's `seq`; read
/// [`LinkMonitor::status`] for a [`LinkStatus`].
#[derive(Clone, Debug)]
pub struct LinkMonitor {
    session_id: String,
    expected: Option<i64>,
    /// First seq ever observed — the lower bound of the span over which loss is
    /// measured, so `loss_rate` is a fraction of the seqs that SHOULD have arrived,
    /// not of `received` (which a duplicate/replay flood inflates).
    first_seq: Option<i64>,
    last_seq: i64,
    received: i64,
    lost: i64,
    cusum: f64,
    ref_loss: f64,
    threshold: f64,
    burst: bool,
    /// Recently gap-counted seqs (bounded), so an out-of-order arrival can be
    /// reconciled — decrementing `lost` — instead of permanently inflating
    /// `loss_rate` on a merely-reordered link.
    missing: std::collections::BTreeSet<i64>,
    /// Wire 0.8 (§8): the MONITORED stream's epoch, recorded on the first valid
    /// in-epoch arrival, so `LinkStatus.observed_stream` names *which incarnation*
    /// the reported high-water/loss belongs to. `None` before any valid frame (the
    /// pre-first-frame burst case) — `observed_stream` is then absent, tracking
    /// `last_arrival_seq`. One monitor instance belongs to one declared epoch; a
    /// fresh receiver declaration constructs or explicitly resets the monitor.
    observed_epoch: Option<String>,
}

impl LinkMonitor {
    /// `ref_loss` is the tolerated baseline loss fraction; `threshold` is the
    /// CUSUM trip level (higher = slower but fewer false alarms).
    pub fn new(session_id: impl Into<String>, ref_loss: f64, threshold: f64) -> Self {
        // Validate the detector params. The CUSUM jam trigger is load-bearing
        // (it gates the HOLD→ESTOP fail-safe): a `ref_loss >= 1.0` makes the
        // burst never trip (fail-open), a `threshold <= 0` false-trips every
        // frame, and a non-finite either poisons the accumulator. Clamp to a
        // live, sane range rather than trusting the caller.
        let ref_loss = if ref_loss.is_finite() {
            ref_loss.clamp(0.0, 0.99)
        } else {
            0.05
        };
        let threshold = if threshold.is_finite() && threshold > 0.0 {
            threshold
        } else {
            5.0
        };
        Self {
            session_id: session_id.into(),
            expected: None,
            first_seq: None,
            last_seq: -1,
            received: 0,
            lost: 0,
            cusum: 0.0,
            ref_loss,
            threshold,
            burst: false,
            missing: std::collections::BTreeSet::new(),
            observed_epoch: None,
        }
    }

    /// Sensible defaults: 5% baseline loss, CUSUM trip at 5.
    pub fn with_defaults(session_id: impl Into<String>) -> Self {
        Self::new(session_id, 0.05, 5.0)
    }

    /// Reset the monitor only while constructing/adopting a NEW authenticated
    /// receiver declaration. This is not an in-place payload-driven epoch switch:
    /// the enclosing route/session fence must already have retired the old monitor.
    /// Clears counters and CUSUM/burst state; a burst-driven ESTOP stays latched in
    /// the `SafetyGovernor` — that latch, not this detector, is the persistent
    /// fail-safe.
    pub fn reset(&mut self) {
        let session_id = std::mem::take(&mut self.session_id);
        *self = Self::new(session_id, self.ref_loss, self.threshold);
    }

    fn observe(&mut self, lost_slot: bool) {
        // One-sided CUSUM on the loss indicator; resets at 0, trips at threshold.
        let inc = if lost_slot { 1.0 } else { 0.0 } - self.ref_loss;
        self.cusum = (self.cusum + inc).max(0.0);
        self.burst = self.cusum >= self.threshold;
    }

    /// Record an arrived message from stream `epoch` with sequence `seq`. The caller
    /// runs the monitor on one already-admitted declaration and creates/resets it
    /// only when adopting a fresh declaration, so `epoch` names the incarnation the
    /// loss metrics belong to — recorded for `LinkStatus.observed_stream` only on a
    /// valid sequence.
    pub fn on_seq(&mut self, epoch: &str, seq: i64) {
        // LinkStatus is shared as JSON with JS peers. A precision-unsafe or
        // negative seq is not a usable sample; trip the burst fail-safe and keep
        // the last valid metrics rather than emitting counters JS cannot represent.
        // A pre-first-frame burst leaves `observed_epoch` unset — `observed_stream`
        // and `last_arrival_seq` both stay absent (§8 presence invariant).
        if !(1..=JSON_SAFE_INTEGER_MAX).contains(&seq) {
            self.burst = true;
            return;
        }
        self.observed_epoch = Some(epoch.to_string());
        // Cap the CUSUM bookkeeping iterations per call so a huge/hostile seq jump
        // (peer restart, counter glitch, malicious sender, e.g. seq=9_000_000_000)
        // cannot stall this thread. The one-sided CUSUM trips at
        // ~threshold/(1-ref_loss) losses (~6 for the defaults), far below the cap,
        // so a larger real gap changes nothing observable past the trip point.
        const MAX_GAP_OBSERVE: i64 = 256;
        // Bound on the reconciliation set so a hostile/huge gap cannot grow it
        // without limit; `lost` stays exact regardless (see saturating_add).
        const MISSING_CAP: usize = 4096;
        if self.first_seq.is_none() {
            self.first_seq = Some(seq);
        }
        // A pure duplicate (already-accounted seq, not filling a known gap) must be a
        // metrics no-op: counting it as a fresh delivery would inflate `received` AND,
        // via observe(false), suppress the CUSUM burst — so a replay/jam flood of old
        // seqs could mask both loss_rate and the HOLD->ESTOP fail-safe.
        let mut new_delivery = true;
        if let Some(e) = self.expected {
            if seq > e {
                // Missed e..=seq-1. `missed` is positive (guarded by `seq > e`).
                // `saturating_sub`: a mixed-sign extreme pair (e.g. e near i64::MIN,
                // seq near i64::MAX from a garbage/hostile peer) would overflow a raw
                // `seq - e` (debug panic / release wrap), silently failing the jam
                // detector open; saturate to keep `missed` a valid non-negative gap.
                let missed = seq.saturating_sub(e);
                // `saturating_add`: exact unless the lost count would overflow.
                self.lost = self.lost.saturating_add(missed).min(JSON_SAFE_INTEGER_MAX);
                // Remember the (bounded) head of the gap so a later out-of-order
                // arrival can be reconciled. The loop short-circuits at the cap,
                // so a billion-seq gap costs at most MISSING_CAP inserts.
                for s in e..seq {
                    if self.missing.len() >= MISSING_CAP {
                        break;
                    }
                    self.missing.insert(s);
                }
                for _ in 0..missed.min(MAX_GAP_OBSERVE) {
                    self.observe(true);
                }
            } else if seq < e {
                // Out-of-order / duplicate. If this seq was previously counted as
                // lost, it actually arrived late: reconcile by decrementing `lost`
                // and forgetting it, so mere reordering does not permanently
                // inflate loss_rate (and spuriously escalate the fail-safe).
                if self.missing.remove(&seq) {
                    self.lost = (self.lost - 1).max(0);
                } else {
                    // A true duplicate (already reconciled / never missing) is a
                    // metrics no-op — it must not lower the loss CUSUM.
                    new_delivery = false;
                }
            }
        }
        if new_delivery {
            self.received = self.received.saturating_add(1).min(JSON_SAFE_INTEGER_MAX);
            self.observe(false);
        }
        self.last_seq = seq;
        // Advance the next-expected seq FORWARD only: an out-of-order (late)
        // arrival must not rewind `expected` (that would re-open the gap it just
        // filled and corrupt reconciliation). CRITICAL: a frame with seq ==
        // i64::MAX would make `seq + 1` overflow and panic in debug — saturate so
        // next-expected pins at i64::MAX instead of wrapping/panicking.
        let next = seq.saturating_add(1);
        self.expected = Some(self.expected.map_or(next, |e| e.max(next)));
    }

    pub fn loss_rate(&self) -> f64 {
        // Span-based: lost as a fraction of the seqs that SHOULD have arrived over
        // [first_seq, expected-1], NOT of `received` (which duplicates inflate). This
        // makes the rate immune to a duplicate/replay flood masking real loss.
        match (self.first_seq, self.expected) {
            (Some(first), Some(exp)) => {
                // `saturating_sub`: `exp` and `first` can straddle zero with extreme
                // magnitude (a hostile/glitched peer), which would overflow a raw
                // `exp - first`; saturate so the span stays a valid positive count.
                let span = exp.saturating_sub(first).max(1); // `exp` = forward next-expected high-water
                (self.lost as f64 / span as f64).clamp(0.0, 1.0)
            }
            _ => 0.0,
        }
    }

    pub fn is_burst(&self) -> bool {
        self.burst
    }

    /// Build a [`LinkStatus`] at publisher time `t`. The caller (the status
    /// publisher) supplies its OWN `stream` position and the live `session` — the
    /// LinkStatus envelope identity a consumer validates *before* trusting any
    /// reported metric (§8). The monitor fills the observed side: `received`/`lost`/
    /// `loss_rate`/`burst`, plus `observed_stream` (the monitored incarnation + its
    /// forward high-water) and `last_arrival_seq`, both absent until the first valid
    /// in-epoch frame (presence invariant: `observed_stream` present ⇔
    /// `last_arrival_seq` present).
    pub fn status(&self, t: f64, stream: StreamPosition, session: SessionRef) -> LinkStatus {
        // Forward high-water: `expected` is high-water + 1, advanced forward-only, so
        // a late/reordered arrival never regresses `observed_stream.seq` (§8).
        let observed_stream =
            self.observed_epoch
                .clone()
                .zip(self.expected)
                .map(|(epoch, expected)| StreamPosition {
                    epoch,
                    seq: expected - 1,
                });
        LinkStatus {
            session_id: self.session_id.clone(),
            t,
            received: self.received,
            lost: self.lost,
            loss_rate: self.loss_rate(),
            burst: self.burst,
            stream,
            observed_stream,
            // F-16: the last valid ARRIVAL, reported separately from the high-water
            // (< observed_stream.seq under reordering; == it on forward arrival).
            last_arrival_seq: (self.last_seq >= 1).then_some(self.last_seq),
            session,
            ..Default::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::messages::test_ids::{session, stream, EPOCH, SID};
    use crate::messages::AuthorityLease;

    fn authority() -> AuthorityLease {
        AuthorityLease {
            session_epoch: session().generation,
            term: 1,
            lease_id: "20000000-0000-4000-8000-000000000001".into(),
            issuer_principal_id: "controller-1".into(),
            holder_principal_id: "controller-1".into(),
            holder_entity_id: "body-1".into(),
            issued_at_utc_ms: 1_000,
            expires_at_utc_ms: 2_000,
        }
    }

    fn vec3(x: f64) -> Map<ChannelValue> {
        let mut m = Map::new();
        m.insert(
            "velocity_setpoint".into(),
            ChannelValue::vec3(x, 0.0, 0.0, Some("m/s")),
        );
        m
    }

    #[test]
    fn action_buffer_replays_horizon_then_holds() {
        let mut buf = ActionBuffer::new();
        // tick0 = -0.1, horizon = [-0.2, -0.3], 50 ms spacing, ttl 200 ms.
        let cmd = CommandFrame {
            stream: stream(1),
            session: session(),
            session_id: SID.into(),
            mode: Mode::Active,
            authority: Some(authority()),
            ttl_ms: 200.0,
            channels: vec3(-0.1),
            horizon: vec![vec3(-0.2), vec3(-0.3)],
            horizon_dt_ms: Some(50.0),
            ..Default::default()
        };
        buf.on_command(1.0, cmd);
        assert_eq!(buf.active(1.00).unwrap()["velocity_setpoint"].data[0], -0.1); // tick 0
        assert_eq!(buf.active(1.06).unwrap()["velocity_setpoint"].data[0], -0.2); // tick 1
        assert_eq!(buf.active(1.11).unwrap()["velocity_setpoint"].data[0], -0.3); // tick 2
        assert!(buf.should_hold(1.16), "horizon drained (tick 3) -> HOLD");
        assert!(buf.should_hold(1.30), "past ttl -> HOLD");
    }

    #[test]
    fn action_buffer_holds_without_command_and_on_estop() {
        let mut buf = ActionBuffer::new();
        assert!(buf.should_hold(0.0), "no command -> HOLD");
        // Even an UNSTAMPED (seq 0) ESTOP latches — a fail-safe is never dropped,
        // though the frame itself is not buffered.
        buf.on_command(
            0.0,
            CommandFrame {
                mode: Mode::Estop,
                channels: vec3(5.0),
                ..Default::default()
            },
        );
        assert!(buf.is_estopped(), "an unstamped ESTOP must still latch");
        assert!(buf.should_hold(0.01), "ESTOP -> HOLD");
    }

    #[test]
    fn action_buffer_rejects_unstamped_seq() {
        // Wire 0.6: the "seq == 0 always advances" escape hatch is REMOVED. An
        // unstamped/negative-seq Active command must never be buffered, never
        // refresh the deadline, and never overwrite a held setpoint.
        let mut buf = ActionBuffer::new();
        for bad_seq in [0, -1, i64::MIN] {
            buf.on_command(
                1.0,
                CommandFrame {
                    stream: stream(bad_seq),
                    session: session(),
                    session_id: SID.into(),
                    mode: Mode::Active,
                    authority: Some(authority()),
                    channels: vec3(9.9),
                    ..Default::default()
                },
            );
            assert!(
                buf.should_hold(1.0),
                "unstamped seq {bad_seq} must not produce an active setpoint"
            );
        }
        // A stamped command is live; a following seq-0 spray must not disturb it.
        buf.on_command(
            2.0,
            CommandFrame {
                stream: stream(1),
                session: session(),
                session_id: SID.into(),
                ttl_ms: 200.0,
                mode: Mode::Active,
                authority: Some(authority()),
                channels: vec3(0.5),
                ..Default::default()
            },
        );
        buf.on_command(
            2.01,
            CommandFrame {
                stream: stream(0),
                session: session(),
                session_id: SID.into(),
                ttl_ms: 200.0,
                mode: Mode::Active,
                authority: Some(authority()),
                channels: vec3(9.9),
                ..Default::default()
            },
        );
        let live = buf.active(2.05).expect("stamped command is live");
        assert_eq!(
            live["velocity_setpoint"].data[0], 0.5,
            "a seq-0 frame must not overwrite the live setpoint"
        );
        assert!(
            buf.should_hold(2.3),
            "…and must not have refreshed the deadline (expires on the seq-1 anchor)"
        );
    }

    #[test]
    fn action_buffer_lower_sequence_never_reanchors_after_expiry() {
        let mut buf = ActionBuffer::new();
        let cmd = |seq: i64, v: f64| CommandFrame {
            stream: stream(seq),
            session: session(),
            session_id: SID.into(),
            ttl_ms: 200.0,
            mode: Mode::Active,
            authority: Some(authority()),
            channels: vec3(v),
            ..Default::default()
        };
        buf.on_command(1.0, cmd(1000, 0.4));
        // Expiry never resets this declaration's sequence high-water.
        assert!(buf.should_hold(1.5), "expired");
        buf.on_command(2.0, cmd(1, 0.7));
        assert!(
            buf.should_hold(2.05),
            "a lower sequence remains rejected after expiry"
        );
        // A strictly newer position in the same declared stream is still accepted.
        buf.on_command(4.0, cmd(1001, 0.2));
        buf.on_command(4.01, cmd(1000, 0.9));
        assert_eq!(
            buf.active(4.05).unwrap()["velocity_setpoint"].data[0],
            0.2,
            "a lower seq on a LIVE stream is still rejected"
        );
    }

    #[test]
    fn action_buffer_epoch_is_declaration_bound_even_after_expiry() {
        use crate::messages::StreamPosition;
        let ep_a = "aaaaaaaa-0000-4000-8000-000000000001";
        let ep_b = "bbbbbbbb-0000-4000-8000-000000000002";
        let cmd = |epoch: &str, seq: i64, v: f64| CommandFrame {
            stream: StreamPosition {
                epoch: epoch.into(),
                seq,
            },
            session: session(),
            session_id: SID.into(),
            ttl_ms: 200.0,
            mode: Mode::Active,
            authority: Some(authority()),
            channels: vec3(v),
            ..Default::default()
        };
        let mut buf = ActionBuffer::new();
        buf.on_command(1.0, cmd(ep_a, 5, 0.4));
        assert_eq!(buf.active(1.05).unwrap()["velocity_setpoint"].data[0], 0.4);
        // A foreign epoch with a much higher seq must NOT hijack the live stream.
        buf.on_command(1.06, cmd(ep_b, 9999, 0.9));
        assert_eq!(
            buf.active(1.07).unwrap()["velocity_setpoint"].data[0],
            0.4,
            "a foreign epoch cannot advance a LIVE stream (no hijack)"
        );
        // Expiry still does not authorize the foreign epoch.
        assert!(buf.should_hold(1.5), "epoch A expired");
        buf.on_command(1.5, cmd(ep_b, 1, 0.7));
        assert!(
            buf.should_hold(1.55),
            "a new epoch requires a fresh authorized declaration/buffer"
        );
        // The rejected foreign epoch did not replace or tombstone the declaration:
        // a strictly newer position in the original epoch can resume it.
        buf.on_command(2.0, cmd(ep_a, 100_000, 0.2));
        assert_eq!(
            buf.active(2.05).unwrap()["velocity_setpoint"].data[0],
            0.2,
            "the original declared epoch remains authoritative after expiry"
        );
    }

    #[test]
    fn link_monitor_counts_gaps_and_flags_burst() {
        let mut m = LinkMonitor::new("uav1", 0.05, 3.0);
        for s in [1, 2, 3] {
            m.on_seq(EPOCH, s);
        }
        assert_eq!(m.lost, 0);
        assert!(!m.is_burst());
        // Jump expected 4 -> 14: 10 consecutive losses -> CUSUM trips.
        m.on_seq(EPOCH, 14);
        assert!(m.lost >= 10);
        assert!(m.is_burst(), "a long gap should flag a burst");
        assert!(m.loss_rate() > 0.0);
        assert_eq!(m.status(0.0, stream(1), session()).kind, "link_status");
    }

    #[test]
    fn link_status_reports_observed_stream_and_last_arrival() {
        // §8/§10: arrivals 1,2,5,3 -> observed_stream.seq is the forward high-water
        // (5), last_arrival_seq is the most recent ARRIVAL (3, < high-water under
        // reordering), and one gap (4) is still unresolved.
        let mut m = LinkMonitor::with_defaults("uav1");
        for s in [1, 2, 5, 3] {
            m.on_seq(EPOCH, s);
        }
        let st = m.status(1.0, stream(7), session());
        let observed = st
            .observed_stream
            .expect("observed_stream present after valid frames");
        assert_eq!(
            observed.epoch, EPOCH,
            "observed_stream names the monitored epoch"
        );
        assert_eq!(
            observed.seq, 5,
            "observed_stream.seq is the forward high-water"
        );
        assert_eq!(
            st.last_arrival_seq,
            Some(3),
            "last_arrival_seq is the latest arrival, below the high-water under reordering"
        );
        assert_eq!(
            st.stream.seq, 7,
            "own stream is the caller-supplied position"
        );
        assert_eq!(st.lost, 1, "the gap at seq 4 is still unresolved");
    }

    #[test]
    fn link_status_omits_observed_stream_before_the_first_valid_frame() {
        // §8: a pre-first-frame burst leaves the own stream present but
        // observed_stream + last_arrival_seq ABSENT (the presence invariant).
        let mut m = LinkMonitor::with_defaults("uav1");
        m.on_seq(EPOCH, 0); // invalid seq: trips the burst, no valid observed frame yet
        let st = m.status(1.0, stream(7), session());
        assert!(st.burst, "an invalid seq trips the burst fail-safe");
        assert!(
            st.observed_stream.is_none(),
            "observed_stream is absent before the first valid frame"
        );
        assert!(
            st.last_arrival_seq.is_none(),
            "last_arrival_seq is absent before the first valid frame"
        );
        assert_eq!(
            st.stream.seq, 7,
            "the status frame still carries its own stream"
        );
    }

    #[test]
    fn action_buffer_estop_latches_but_hold_does_not() {
        let mut buf = ActionBuffer::new();
        let cmd = |seq: i64, mode: Mode, v: f64| CommandFrame {
            stream: stream(seq),
            session: session(),
            session_id: SID.into(),
            authority: matches!(&mode, Mode::Active).then(authority),
            mode,
            channels: vec3(v),
            ..Default::default()
        };
        // A normal Active command applies.
        buf.on_command(0.0, cmd(1, Mode::Active, 0.5));
        assert!(buf.active(0.0).is_some(), "Active command applies");

        // A HOLD command suppresses output but does NOT latch.
        buf.on_command(0.01, cmd(2, Mode::Hold, 0.5));
        assert!(buf.should_hold(0.01), "HOLD suppresses");
        buf.on_command(0.02, cmd(3, Mode::Active, 0.5));
        assert!(
            buf.active(0.02).is_some(),
            "a HOLD must clear once a fresh Active arrives"
        );

        // An ESTOP command latches: a later Active command must NOT revive output.
        buf.on_command(0.03, cmd(4, Mode::Estop, 0.5));
        assert!(buf.is_estopped());
        buf.on_command(0.04, cmd(5, Mode::Active, 0.9));
        assert!(
            buf.should_hold(0.04),
            "ESTOP latches — a later Active does not revive the actuator"
        );

        // Authorized reset clears this local latch, retires the old generation's
        // buffer, and cannot accept another command in-place.
        buf.reset();
        assert!(buf.is_retired());
        assert!(
            buf.should_hold(0.04),
            "reset requires a fresh post-ESTOP command"
        );
        buf.on_command(0.05, cmd(6, Mode::Active, 0.9));
        assert!(
            buf.active(0.05).is_none(),
            "retired buffer cannot reactivate the pre-reset generation"
        );

        // The deployment constructs a new session-bound buffer only after a fresh
        // SessionOpened generation and stream declaration.
        let mut fresh = ActionBuffer::new();
        fresh.on_command(0.06, cmd(1, Mode::Active, 0.9));
        assert!(fresh.active(0.06).is_some());
    }

    #[test]
    fn action_buffer_drops_stale_or_reordered_command() {
        let mut buf = ActionBuffer::new();
        buf.on_command(
            1.0,
            CommandFrame {
                stream: stream(5),
                session: session(),
                session_id: SID.into(),
                mode: Mode::Active,
                authority: Some(authority()),
                channels: vec3(0.5),
                ..Default::default()
            },
        );
        assert_eq!(buf.active(1.0).unwrap()["velocity_setpoint"].data[0], 0.5);
        // An older/reordered command (seq 3 <= 5) is dropped: the held setpoint and
        // the replay clock stay put.
        buf.on_command(
            1.01,
            CommandFrame {
                stream: stream(3),
                session: session(),
                session_id: SID.into(),
                mode: Mode::Active,
                authority: Some(authority()),
                channels: vec3(0.9),
                ..Default::default()
            },
        );
        assert_eq!(
            buf.active(1.01).unwrap()["velocity_setpoint"].data[0],
            0.5,
            "a stale/reordered command must not overwrite the newer setpoint"
        );
        // A stale ESTOP (seq 2 <= 5) is still latched — a fail-safe is never dropped.
        buf.on_command(
            1.02,
            CommandFrame {
                stream: stream(2),
                session: session(),
                session_id: SID.into(),
                mode: Mode::Estop,
                channels: vec3(0.0),
                ..Default::default()
            },
        );
        assert!(buf.is_estopped(), "a stale ESTOP must still latch");
        assert!(buf.should_hold(1.02), "latched ESTOP -> HOLD");
    }

    #[test]
    fn action_buffer_ignores_replayed_command() {
        let mut buf = ActionBuffer::new();
        buf.on_command(
            1.0,
            CommandFrame {
                stream: stream(10),
                session: session(),
                session_id: SID.into(),
                ttl_ms: 200.0,
                mode: Mode::Active,
                authority: Some(authority()),
                channels: vec3(0.3),
                ..Default::default()
            },
        );
        // Replaying the SAME seq at a much later time must not rewind the replay
        // clock / refresh the deadline (else a dead link stays "fresh").
        buf.on_command(
            5.0,
            CommandFrame {
                stream: stream(10),
                session: session(),
                session_id: SID.into(),
                ttl_ms: 200.0,
                mode: Mode::Active,
                authority: Some(authority()),
                channels: vec3(0.3),
                ..Default::default()
            },
        );
        assert!(
            buf.should_hold(1.3),
            "the duplicate seq=10 replay at t=5 must not refresh the t=1 deadline"
        );
    }

    #[test]
    fn loss_rate_immune_to_duplicate_flood() {
        // High CUSUM threshold to isolate the loss_rate metric from the burst flag.
        let mut m = LinkMonitor::new("uav1", 0.05, 1000.0);
        // 1,2,3 then jump to 7 (lose 4,5,6): 3 lost over span [1,7] = 7 -> ~0.43.
        for s in [1, 2, 3, 7] {
            m.on_seq(EPOCH, s);
        }
        let base = m.loss_rate();
        assert!(base > 0.3, "real loss must register, got {base}");
        // A flood of 50 duplicates of an old seq must NOT lower the reported loss
        // (the span-based denominator + duplicate no-op make it replay-immune).
        for _ in 0..50 {
            m.on_seq(EPOCH, 1);
        }
        assert!(
            (m.loss_rate() - base).abs() < 1e-9,
            "duplicate flood changed loss_rate ({} vs {base})",
            m.loss_rate()
        );
    }

    #[test]
    fn duplicate_flood_does_not_suppress_burst() {
        let mut m = LinkMonitor::new("uav1", 0.05, 3.0);
        m.on_seq(EPOCH, 1);
        m.on_seq(EPOCH, 21); // big gap -> CUSUM trips
        assert!(m.is_burst(), "a large gap must trip the jam burst");
        // Flooding duplicates of an old seq must NOT clear the latched burst (each
        // duplicate is a metrics no-op, so it cannot lower the loss CUSUM).
        for _ in 0..100 {
            m.on_seq(EPOCH, 1);
        }
        assert!(
            m.is_burst(),
            "duplicate flood must not suppress the jam burst"
        );
    }

    #[test]
    fn out_of_order_arrival_reconciles_loss() {
        // resilience-1: a reordered (not lost) seq must not permanently inflate
        // loss_rate. 1,2,5 counts 3 and 4 as lost; their late arrival reconciles.
        let mut m = LinkMonitor::new("uav1", 0.05, 5.0);
        for s in [1, 2, 5] {
            m.on_seq(EPOCH, s);
        }
        assert_eq!(m.lost, 2, "gap to 5 counts 3,4 as lost");
        m.on_seq(EPOCH, 3);
        m.on_seq(EPOCH, 4);
        assert_eq!(m.lost, 0, "reordered arrivals reconcile the loss count");
        assert_eq!(m.loss_rate(), 0.0, "pure reordering -> zero loss");
        // A duplicate of an already-reconciled seq is a no-op (no negative lost).
        m.on_seq(EPOCH, 3);
        assert_eq!(m.lost, 0);
    }

    #[test]
    fn invalid_detector_params_fall_back_to_defaults() {
        // resilience-2: non-finite ref_loss/threshold must not poison or disable
        // the jam detector — they fall back to the live defaults (0.05 / 5.0).
        let mut m = LinkMonitor::new("x", f64::NAN, f64::NAN);
        m.on_seq(EPOCH, 1);
        m.on_seq(EPOCH, 101); // big gap -> burst should still trip with default params
        assert!(
            m.is_burst(),
            "clamped/defaulted params keep the burst detector live"
        );
    }

    #[test]
    fn precision_unsafe_seq_trips_burst_without_corrupting_status() {
        // A typed caller can bypass the JSON ingress. A seq outside the shared
        // exact-integer range must trip the safe burst state without leaking an
        // unrepresentable counter into LinkStatus.
        let mut m = LinkMonitor::with_defaults("uav1");
        m.on_seq(EPOCH, 1); // expected -> 2
        m.on_seq(EPOCH, i64::MAX);
        m.on_seq(EPOCH, i64::MAX);
        assert!(m.is_burst());
        let lr = m.loss_rate();
        assert!(
            (0.0..=1.0).contains(&lr),
            "loss_rate stays in [0,1], got {lr}"
        );
        assert_eq!(
            m.status(0.0, stream(1), session()).kind,
            "link_status",
            "monitor still usable after rejecting an unsafe seq"
        );
    }

    #[test]
    fn unstamped_seq_trips_burst_without_refreshing_metrics() {
        let mut monitor = LinkMonitor::with_defaults("uav1");
        monitor.on_seq(EPOCH, 0);
        assert!(monitor.is_burst(), "wire-unstamped seq must fail safe");
        let status = monitor.status(0.0, stream(1), session());
        assert_eq!(status.last_arrival_seq, None);
        assert_eq!(status.received, 0);
    }

    #[test]
    fn mixed_sign_extreme_seq_does_not_overflow() {
        // Garbage/hostile signed extremes are rejected and trip the burst latch;
        // they must never overflow bookkeeping or enter JSON telemetry.
        let mut m = LinkMonitor::with_defaults("uav1");
        m.on_seq(EPOCH, i64::MIN);
        m.on_seq(EPOCH, i64::MAX);
        let lr = m.loss_rate();
        assert!(
            (0.0..=1.0).contains(&lr),
            "loss_rate stays in [0,1] after a mixed-sign extreme gap, got {lr}"
        );
        assert!(m.is_burst(), "an enormous gap still trips the jam burst");
        assert_eq!(
            m.status(0.0, stream(1), session()).kind,
            "link_status",
            "monitor remains usable after saturation"
        );
    }

    #[test]
    fn max_horizon_len_bounds_nonfinite_ttl() {
        // A finite ttl/dt gives the strict executable bound; a non-finite ttl/dt (or dt<=0) must
        // return 0 (no replay), never usize::MAX from an `Inf as usize` saturation.
        assert_eq!(max_horizon_len(200.0, 50.0), 3);
        assert_eq!(max_horizon_len(f64::INFINITY, 50.0), 0);
        assert_eq!(max_horizon_len(f64::NAN, 50.0), 0);
        assert_eq!(max_horizon_len(200.0, f64::INFINITY), 0);
        assert_eq!(max_horizon_len(200.0, 0.0), 0);
        assert_eq!(
            max_horizon_len(1e300, 1e-310),
            0,
            "an overflowing quotient fails closed"
        );
        assert_eq!(
            max_horizon_len(60_000.0, 0.5),
            MAX_HORIZON_STEPS,
            "finite horizons are resource-capped"
        );
    }

    #[test]
    fn huge_seq_jump_is_bounded_but_lost_stays_exact() {
        // A hostile/glitched peer can send a seq billions ahead. The CUSUM
        // bookkeeping must not loop per-missed-seq (that would stall the thread),
        // yet `lost` must remain the exact gap count. Returning at all proves the bound.
        let mut m = LinkMonitor::new("uav1", 0.05, 5.0);
        m.on_seq(EPOCH, 1); // expected -> 2
        m.on_seq(EPOCH, 1_000_000_002); // gap = 1_000_000_002 - 2 = 1_000_000_000
        assert_eq!(
            m.lost, 1_000_000_000,
            "lost count stays exact regardless of the loop bound"
        );
        assert!(m.is_burst(), "a billion-seq gap trips the burst detector");
    }

    #[test]
    fn link_monitor_scores_own_stream_seq_not_source_seq_f01() {
        // F-01 CLOSED (wire-0.8): the LinkMonitor scores loss on the frame's OWN
        // `stream.seq` (contiguous per publisher), NOT the driving `source` seq. A
        // controller that decimates / event-triggers its source (commands driven by
        // sensor seqs 1 then 8) still emits a CONTIGUOUS own stream (1,2), so the
        // decimation is invisible to the monitor — no false jam. The receiver feeds
        // `stream.seq` (see `transport.rs` / `ActionBuffer`), which is what closes F-01.
        let mut healthy = LinkMonitor::with_defaults("uav1"); // ref_loss 0.05, threshold 5.0
        healthy.on_seq(EPOCH, 1);
        healthy.on_seq(EPOCH, 2); // decimated SOURCE -> still a contiguous OWN stream
        assert!(
            !healthy.is_burst(),
            "a decimated source no longer trips a false jam (F-01 closed)"
        );
        // A genuine gap in the monitored OWN stream is real loss and MUST still trip.
        let mut lossy = LinkMonitor::with_defaults("uav1");
        lossy.on_seq(EPOCH, 1);
        lossy.on_seq(EPOCH, 8); // six genuinely-lost frames on the monitored own stream
        assert!(
            lossy.is_burst(),
            "a real gap in the monitored own stream still trips the jam burst"
        );
    }

    #[test]
    fn horizon_bound_matches_strict_watchdog_deadline_f04() {
        // F-04 regression: the advertised and executable bounds are identical,
        // including at an exact TTL/cadence multiple where the watchdog rejects the
        // setpoint scheduled exactly on the inclusive expiry boundary.
        let executable = |ttl: f64, dt: f64| (ttl / dt).ceil() as usize - 1;

        assert_eq!(max_horizon_len(100.0, 100.0), 0);
        assert_eq!(max_horizon_len(100.0, 100.0), executable(100.0, 100.0));
        assert_eq!(max_horizon_len(200.0, 100.0), 1);
        assert_eq!(executable(200.0, 100.0), 1);
        assert_eq!(max_horizon_len(200.0, 50.0), 3);
        assert_eq!(executable(200.0, 50.0), 3);

        // Non-integer ttl/dt: floor already equals ceil-1, so no discrepancy.
        assert_eq!(max_horizon_len(250.0, 100.0), 2);
        assert_eq!(executable(250.0, 100.0), 2);
    }
}
