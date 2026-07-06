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

use crate::messages::{ChannelValue, CommandFrame, LinkStatus, Map, Mode};
use crate::safety::CommandWatchdog;

/// Plant-side packetized-predictive-control buffer (the deadline backstop).
#[derive(Clone, Debug, Default)]
pub struct ActionBuffer {
    latest: Option<CommandFrame>,
    recv_s: f64,
    watchdog: CommandWatchdog,
    /// Latched ESTOP (mirrors `SafetyGovernor`): once an ESTOP command is ingested
    /// the buffer fails safe (HOLD) on every subsequent `active()` until a
    /// supervisor [`reset`]s it — a later non-ESTOP command does NOT clear it.
    /// A plain HOLD command stays non-latching (it self-clears on the next Active).
    estop: bool,
    /// Highest accepted command `seq`, for monotonic-forward acceptance (drop
    /// stale/duplicate/reordered frames). Wire 0.6: `seq >= 1` is mandatory —
    /// `seq < 1` is never accepted (no escape hatch); a non-advancing seq is
    /// accepted only once the stream has EXPIRED (restart re-anchor, mirroring
    /// [`CommandWatchdog::on_command`]).
    last_seq: i64,
}

impl ActionBuffer {
    pub fn new() -> Self {
        Self::default()
    }

    /// Ingest a command accepted at local time `now_s`. A stale/duplicate/reordered
    /// command (`seq <=` the last accepted) is DROPPED while the stream is live — a
    /// replayed older horizon must not overwrite a newer one or rewind the replay
    /// clock (`recv_s`) / refresh the deadline. An ESTOP latches regardless of
    /// ordering or stamping — a fail-safe is never dropped.
    ///
    /// Wire 0.6: `seq < 1` (unstamped/negative, including the `0` serde default)
    /// is NEVER accepted — the pre-0.6 "`seq == 0` always advances" escape hatch
    /// let a default-constructed/hostile frame bypass replay rejection and refresh
    /// the deadline. A *strictly-lower* `seq >= 1` is accepted only once the
    /// stream has EXPIRED (`should_hold` true — the plant is already safely
    /// holding): that re-anchors a legitimately restarted controller's fresh epoch
    /// without a wire epoch field. An *equal* `seq` never re-anchors (a
    /// frozen/replayed frame must not duty-cycle liveness across expiry windows).
    /// Mirrors [`CommandWatchdog::on_command`].
    pub fn on_command(&mut self, now_s: f64, command: CommandFrame) {
        if command.mode == Mode::Estop {
            self.estop = true; // latch even if the frame is stale/out-of-order/unstamped
        }
        if command.seq < 1 {
            return; // unstamped/invalid seq: never buffered (ESTOP latched above)
        }
        if command.seq <= self.last_seq
            && (command.seq == self.last_seq || !self.watchdog.should_hold(now_s))
        {
            return; // duplicate (always), or stale/reordered while LIVE (ESTOP latched above)
        }
        self.last_seq = command.seq;
        self.watchdog.on_command(now_s, command.ttl_ms, command.seq);
        self.recv_s = now_s;
        self.latest = Some(command);
    }

    /// Clear a latched ESTOP (supervisor authority).
    pub fn reset(&mut self) {
        self.estop = false;
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

/// Cap a horizon length to the deadline: `N <= ttl_ms / horizon_dt_ms`, so the
/// replay can never outlive `ttl_ms` (the load-bearing PPC safety invariant).
pub fn max_horizon_len(ttl_ms: f64, horizon_dt_ms: f64) -> usize {
    // A non-finite ttl/dt (or dt <= 0) has no bounded horizon: `Inf / dt` floors to
    // `Inf`, which `as usize` saturates to `usize::MAX` — a garbage/`+Inf` ttl would
    // then authorise an effectively unbounded predictive horizon. Return 0 (no
    // replay) instead, so a non-finite input fails safe rather than open.
    if !ttl_ms.is_finite() || !horizon_dt_ms.is_finite() || horizon_dt_ms <= 0.0 {
        return 0;
    }
    (ttl_ms / horizon_dt_ms).floor().max(0.0) as usize
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
        }
    }

    /// Sensible defaults: 5% baseline loss, CUSUM trip at 5.
    pub fn with_defaults(session_id: impl Into<String>) -> Self {
        Self::new(session_id, 0.05, 5.0)
    }

    /// Reset the monitor for a NEW stream epoch (a restarted publisher whose `seq`
    /// legitimately regressed — see `CommandWatchdog::on_command`'s re-anchor
    /// rule). Without this, a seq regression reads as one giant "duplicate" run:
    /// `expected` stays at the old high-water mark and every new-epoch frame is a
    /// metrics no-op until seq catches up. Clears counters and the CUSUM/burst
    /// state; a burst-driven ESTOP stays latched in the `SafetyGovernor` — that
    /// latch, not this detector, is the persistent fail-safe.
    pub fn reset(&mut self) {
        let session_id = std::mem::take(&mut self.session_id);
        *self = Self::new(session_id, self.ref_loss, self.threshold);
    }

    fn observe(&mut self, lost_slot: bool) {
        // One-sided CUSUM on the loss indicator; resets at 0, trips at threshold.
        let inc = if lost_slot { 1.0 } else { 0.0 } - self.ref_loss;
        self.cusum = (self.cusum + inc).max(0.0);
        self.burst = self.cusum > self.threshold;
    }

    /// Record an arrived message with sequence `seq`.
    pub fn on_seq(&mut self, seq: i64) {
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
                self.lost = self.lost.saturating_add(missed);
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
            self.received = self.received.saturating_add(1);
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

    pub fn status(&self, t: f64) -> LinkStatus {
        LinkStatus {
            session_id: self.session_id.clone(),
            t,
            last_seq: self.last_seq,
            received: self.received,
            lost: self.lost,
            loss_rate: self.loss_rate(),
            burst: self.burst,
            ..Default::default()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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
            seq: 1,
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
                    seq: bad_seq,
                    mode: Mode::Active,
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
                seq: 1,
                ttl_ms: 200.0,
                mode: Mode::Active,
                channels: vec3(0.5),
                ..Default::default()
            },
        );
        buf.on_command(
            2.01,
            CommandFrame {
                seq: 0,
                ttl_ms: 200.0,
                mode: Mode::Active,
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
    fn action_buffer_restart_reanchors_only_lower_seq_after_expiry() {
        let mut buf = ActionBuffer::new();
        let cmd = |seq: i64, v: f64| CommandFrame {
            seq,
            ttl_ms: 200.0,
            mode: Mode::Active,
            channels: vec3(v),
            ..Default::default()
        };
        buf.on_command(1.0, cmd(1000, 0.4));
        // Expired (t=2.0 >> ttl). A restarted controller's seq=1 re-anchors...
        assert!(buf.should_hold(1.5), "expired");
        buf.on_command(2.0, cmd(1, 0.7));
        assert_eq!(
            buf.active(2.05).expect("restart epoch is live")["velocity_setpoint"].data[0],
            0.7,
            "a strictly-lower seq re-anchors after expiry (restart recovery)"
        );
        // ...but an EXACT duplicate of the last frame never does, even expired —
        // a frozen/replayed frame must not duty-cycle liveness across expiry.
        assert!(buf.should_hold(3.0), "new epoch expired");
        buf.on_command(3.0, cmd(1, 0.7));
        assert!(
            buf.should_hold(3.05),
            "an equal-seq replay must NOT re-anchor after expiry"
        );
        // And while LIVE, lower seqs are still replay-rejected.
        buf.on_command(4.0, cmd(50, 0.2));
        buf.on_command(4.01, cmd(49, 0.9));
        assert_eq!(
            buf.active(4.05).unwrap()["velocity_setpoint"].data[0],
            0.2,
            "a lower seq on a LIVE stream is still rejected"
        );
    }

    #[test]
    fn link_monitor_counts_gaps_and_flags_burst() {
        let mut m = LinkMonitor::new("uav1", 0.05, 3.0);
        for s in [0, 1, 2] {
            m.on_seq(s);
        }
        assert_eq!(m.lost, 0);
        assert!(!m.is_burst());
        // Jump 3 -> 13: 10 consecutive losses -> CUSUM trips.
        m.on_seq(13);
        assert!(m.lost >= 10);
        assert!(m.is_burst(), "a long gap should flag a burst");
        assert!(m.loss_rate() > 0.0);
        assert_eq!(m.status(0.0).kind, "link_status");
    }

    #[test]
    fn action_buffer_estop_latches_but_hold_does_not() {
        let mut buf = ActionBuffer::new();
        let cmd = |seq: i64, mode: Mode, v: f64| CommandFrame {
            seq,
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

        // Supervisor reset clears it.
        buf.reset();
        buf.on_command(0.05, cmd(6, Mode::Active, 0.9));
        assert!(
            buf.active(0.05).is_some(),
            "after reset, Active applies again"
        );
    }

    #[test]
    fn action_buffer_drops_stale_or_reordered_command() {
        let mut buf = ActionBuffer::new();
        buf.on_command(
            1.0,
            CommandFrame {
                seq: 5,
                mode: Mode::Active,
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
                seq: 3,
                mode: Mode::Active,
                channels: vec3(0.9),
                ..Default::default()
            },
        );
        assert_eq!(
            buf.active(1.0).unwrap()["velocity_setpoint"].data[0],
            0.5,
            "a stale/reordered command must not overwrite the newer setpoint"
        );
        // A stale ESTOP (seq 2 <= 5) is still latched — a fail-safe is never dropped.
        buf.on_command(
            1.02,
            CommandFrame {
                seq: 2,
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
                seq: 10,
                ttl_ms: 200.0,
                mode: Mode::Active,
                channels: vec3(0.3),
                ..Default::default()
            },
        );
        // Replaying the SAME seq at a much later time must not rewind the replay
        // clock / refresh the deadline (else a dead link stays "fresh").
        buf.on_command(
            5.0,
            CommandFrame {
                seq: 10,
                ttl_ms: 200.0,
                mode: Mode::Active,
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
        // 0,1,2 then jump to 6 (lose 3,4,5): 3 lost over span [0,6] = 7 -> ~0.43.
        for s in [0, 1, 2, 6] {
            m.on_seq(s);
        }
        let base = m.loss_rate();
        assert!(base > 0.3, "real loss must register, got {base}");
        // A flood of 50 duplicates of an old seq must NOT lower the reported loss
        // (the span-based denominator + duplicate no-op make it replay-immune).
        for _ in 0..50 {
            m.on_seq(0);
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
        m.on_seq(0);
        m.on_seq(20); // big gap -> CUSUM trips
        assert!(m.is_burst(), "a large gap must trip the jam burst");
        // Flooding duplicates of an old seq must NOT clear the latched burst (each
        // duplicate is a metrics no-op, so it cannot lower the loss CUSUM).
        for _ in 0..100 {
            m.on_seq(0);
        }
        assert!(
            m.is_burst(),
            "duplicate flood must not suppress the jam burst"
        );
    }

    #[test]
    fn out_of_order_arrival_reconciles_loss() {
        // resilience-1: a reordered (not lost) seq must not permanently inflate
        // loss_rate. 0,1,4 counts 2 and 3 as lost; their late arrival reconciles.
        let mut m = LinkMonitor::new("uav1", 0.05, 5.0);
        for s in [0, 1, 4] {
            m.on_seq(s);
        }
        assert_eq!(m.lost, 2, "gap to 4 counts 2,3 as lost");
        m.on_seq(2);
        m.on_seq(3);
        assert_eq!(m.lost, 0, "reordered arrivals reconcile the loss count");
        assert_eq!(m.loss_rate(), 0.0, "pure reordering -> zero loss");
        // A duplicate of an already-reconciled seq is a no-op (no negative lost).
        m.on_seq(2);
        assert_eq!(m.lost, 0);
    }

    #[test]
    fn invalid_detector_params_fall_back_to_defaults() {
        // resilience-2: non-finite ref_loss/threshold must not poison or disable
        // the jam detector — they fall back to the live defaults (0.05 / 5.0).
        let mut m = LinkMonitor::new("x", f64::NAN, f64::NAN);
        m.on_seq(0);
        m.on_seq(100); // big gap -> burst should still trip with default params
        assert!(
            m.is_burst(),
            "clamped/defaulted params keep the burst detector live"
        );
    }

    #[test]
    fn seq_at_i64_max_saturates_without_panic() {
        // FIX 5: a single peer-reachable frame with seq == i64::MAX must not panic
        // on the `expected = seq + 1` bookkeeping (debug overflow) — it saturates.
        let mut m = LinkMonitor::with_defaults("uav1");
        m.on_seq(0); // expected -> 1
        m.on_seq(i64::MAX); // gap, and expected -> saturating_add(1) == i64::MAX
                            // A following frame at i64::MAX is now <= expected (no panic, no spurious gap).
        m.on_seq(i64::MAX);
        // loss_rate denominator uses saturating_add too — must stay finite in [0,1].
        let lr = m.loss_rate();
        assert!(
            (0.0..=1.0).contains(&lr),
            "loss_rate stays in [0,1], got {lr}"
        );
        assert_eq!(
            m.status(0.0).kind,
            "link_status",
            "monitor still usable after saturation"
        );
    }

    #[test]
    fn mixed_sign_extreme_seq_does_not_overflow() {
        // A garbage/hostile peer can straddle zero with extreme magnitude. The gap
        // arithmetic (`seq - e`, `exp - first`) must saturate, not overflow (debug
        // panic / release wrap) and silently fail the jam detector open.
        let mut m = LinkMonitor::with_defaults("uav1");
        m.on_seq(i64::MIN); // first_seq = i64::MIN, expected -> i64::MIN + 1
        m.on_seq(i64::MAX); // gap ~2^64: `missed = seq.saturating_sub(e)` must not panic
        let lr = m.loss_rate(); // `span = exp.saturating_sub(first)` must not panic
        assert!(
            (0.0..=1.0).contains(&lr),
            "loss_rate stays in [0,1] after a mixed-sign extreme gap, got {lr}"
        );
        assert!(m.is_burst(), "an enormous gap still trips the jam burst");
        assert_eq!(
            m.status(0.0).kind,
            "link_status",
            "monitor remains usable after saturation"
        );
    }

    #[test]
    fn max_horizon_len_bounds_nonfinite_ttl() {
        // A finite ttl/dt gives the exact floor; a non-finite ttl/dt (or dt<=0) must
        // return 0 (no replay), never usize::MAX from an `Inf as usize` saturation.
        assert_eq!(max_horizon_len(200.0, 50.0), 4);
        assert_eq!(max_horizon_len(f64::INFINITY, 50.0), 0);
        assert_eq!(max_horizon_len(f64::NAN, 50.0), 0);
        assert_eq!(max_horizon_len(200.0, f64::INFINITY), 0);
        assert_eq!(max_horizon_len(200.0, 0.0), 0);
    }

    #[test]
    fn huge_seq_jump_is_bounded_but_lost_stays_exact() {
        // A hostile/glitched peer can send a seq billions ahead. The CUSUM
        // bookkeeping must not loop per-missed-seq (that would stall the thread),
        // yet `lost` must remain the exact gap count. Returning at all proves the bound.
        let mut m = LinkMonitor::new("uav1", 0.05, 5.0);
        m.on_seq(0); // expected -> 1
        m.on_seq(1_000_000_001); // gap = 1_000_000_001 - 1 = 1_000_000_000
        assert_eq!(
            m.lost, 1_000_000_000,
            "lost count stays exact regardless of the loop bound"
        );
        assert!(m.is_burst(), "a billion-seq gap trips the burst detector");
    }
}
