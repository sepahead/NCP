//! Safety governor for the **action plane** — the only plane with command
//! authority. Enforces the parts of `SafetyLimits` a controller can: HOLD on a
//! stale sensor, **latch** ESTOP on a geofence breach, and clamp speed. Returns a
//! *fresh* `CommandFrame` (never mutates the input). `max_tilt_rad` is advisory —
//! the plant / flight controller enforces it. Mirrors `loop.py::SafetyGovernor`.
//!
//! ESTOP **latches**: once any condition trips it, every subsequent `govern`
//! returns ESTOP + a zeroed command until a supervisor calls
//! [`reset`](SafetyGovernor::reset). HOLD (on a
//! stale/frozen sensor) is **non-latching** — it clears as soon as fresh data
//! flows again.
//!
//! The watchdog (`govern` with `last_sensor_s = None` or stale) is the
//! producer-overrun backstop: if the brain (`nest.Run`) misses the deadline, the
//! plant-side governor fails safe to HOLD independent of the controller.

use crate::messages::{
    Capabilities, ChannelKind, ChannelSpec, ChannelValue, CommandFrame, Mode, SafetyLimits,
    SensorFrame, WireFrame, JSON_SAFE_INTEGER_MAX,
};

const POSITION_CHANNEL: &str = "pose_position";
const VELOCITY_CHANNEL: &str = "velocity_setpoint";
const POSITION_UNIT: &str = "m";
const VELOCITY_UNIT: &str = "m/s";
const SAFETY_VECTOR_WIDTH: usize = 3;

#[derive(Clone, Debug)]
pub struct SafetyGovernor {
    pub limits: SafetyLimits,
    /// Channel carrying the plant position (geofence input). Resolved from the
    /// negotiated `Capabilities`, not hardcoded.
    position_channel: String,
    /// Channel carrying the commanded velocity (speed clamp target).
    velocity_channel: String,
    /// All negotiated command channels — the HOLD/zero path zeroes their union
    /// with the inbound command's channels, never just one literal name.
    command_channels: Vec<String>,
    /// Latched emergency-stop. Set by any ESTOP-tripping condition; cleared only
    /// by [`reset`](SafetyGovernor::reset). While set, every `govern` returns a zeroed ESTOP frame.
    estop: bool,
    /// Latched config-level fail-closed. Set when a geofence/speed limit is
    /// unenforceable: its channel is absent from the negotiated specs (FIX 3), or
    /// the limit itself is non-finite/negative (`NaN`/`±Inf`/`< 0`, which the
    /// `> 0.0` enforcement gates would silently skip — fail-OPEN). The governor
    /// then HOLDs and reports `safety_ok=false`. A misconfiguration cannot be
    /// fixed at runtime, so it does not clear on [`reset`](SafetyGovernor::reset).
    config_fail_closed: bool,
    /// Whether the canonical negotiated position spec is a width-3 vector in metres.
    position_contract_valid: bool,
    /// Whether the canonical negotiated velocity spec is a width-3 vector in m/s.
    velocity_contract_valid: bool,
}

impl Default for SafetyGovernor {
    fn default() -> Self {
        Self {
            limits: SafetyLimits::default(),
            position_channel: POSITION_CHANNEL.to_string(),
            velocity_channel: VELOCITY_CHANNEL.to_string(),
            command_channels: vec![VELOCITY_CHANNEL.to_string()],
            estop: false,
            config_fail_closed: false,
            position_contract_valid: true,
            velocity_contract_valid: true,
        }
    }
}

impl SafetyGovernor {
    /// Construct with default channel wiring (`pose_position` / `velocity_setpoint`).
    /// Prefer [`from_capabilities`](SafetyGovernor::from_capabilities) so the enforced channels track the negotiated
    /// handshake.
    pub fn new(limits: SafetyLimits) -> Self {
        let config_fail_closed = Self::invalid_numeric_limits(&limits);
        Self {
            limits,
            config_fail_closed,
            ..Default::default()
        }
    }

    /// Construct with explicitly resolved channel names. `command_channels` is the
    /// negotiated set of command-plane channels the HOLD/zero path must zero.
    /// `sensor_channels` is the negotiated perception-plane set, used only to
    /// validate that a configured geofence's position channel actually exists. If
    /// a limit references a channel absent from these specs the governor starts in
    /// a latched config fail-closed state (FIX 3).
    pub fn with_channels(
        limits: SafetyLimits,
        position_channel: impl Into<String>,
        velocity_channel: impl Into<String>,
        command_channels: Vec<String>,
        sensor_channels: Vec<String>,
    ) -> Self {
        let position_channel = position_channel.into();
        let velocity_channel = velocity_channel.into();
        let command_channels = if command_channels.is_empty() {
            vec![velocity_channel.clone()]
        } else {
            command_channels
        };
        let config_fail_closed = Self::invalid_numeric_limits(&limits)
            || Self::invalid_channel_config(
                &position_channel,
                &velocity_channel,
                &command_channels,
                &sensor_channels,
            )
            || Self::detect_misconfig(
                &limits,
                &position_channel,
                &velocity_channel,
                &command_channels,
                &sensor_channels,
            );
        Self {
            limits,
            position_channel,
            velocity_channel,
            command_channels,
            estop: false,
            config_fail_closed,
            position_contract_valid: true,
            velocity_contract_valid: true,
        }
    }

    /// A geofence/speed limit whose channel is not declared in the negotiated
    /// specs is a misconfiguration that must fail closed rather than silently
    /// no-op. Position is checked against the sensor specs; speed against the
    /// command specs.
    fn detect_misconfig(
        limits: &SafetyLimits,
        position_channel: &str,
        velocity_channel: &str,
        command_channels: &[String],
        sensor_channels: &[String],
    ) -> bool {
        let geofence_bad = limits.geofence_radius_m.is_some_and(|r| r > 0.0)
            && !sensor_channels.iter().any(|c| c == position_channel);
        let needs_velocity = limits.max_speed_mps.is_some_and(|s| s > 0.0)
            || limits.geofence_radius_m.is_some_and(|r| r > 0.0);
        let speed_bad = needs_velocity && !command_channels.iter().any(|c| c == velocity_channel);
        geofence_bad || speed_bad
    }

    /// Numeric limits are configuration, not live telemetry. Detect bad values
    /// at construction so `safety_ok()` cannot report healthy before the first
    /// command reaches the governor.
    fn invalid_numeric_limits(limits: &SafetyLimits) -> bool {
        let bad_optional =
            |value: Option<f64>| value.is_some_and(|value| !value.is_finite() || value < 0.0);
        !limits.command_timeout_ms.is_finite()
            || limits.command_timeout_ms <= 0.0
            || bad_optional(limits.max_speed_mps)
            || bad_optional(limits.max_tilt_rad)
            || bad_optional(limits.geofence_radius_m)
    }

    fn invalid_channel_config(
        position_channel: &str,
        velocity_channel: &str,
        command_channels: &[String],
        sensor_channels: &[String],
    ) -> bool {
        let valid = |name: &str| !name.is_empty() && !name.chars().any(char::is_control);
        let unique_valid = |names: &[String]| {
            let mut seen = std::collections::BTreeSet::new();
            names
                .iter()
                .all(|name| valid(name) && seen.insert(name.as_str()))
        };
        !valid(position_channel)
            || !valid(velocity_channel)
            || !unique_valid(command_channels)
            || !unique_valid(sensor_channels)
    }

    fn compatible_safety_vec3(spec: Option<&ChannelSpec>, expected_unit: &str) -> bool {
        spec.is_some_and(|spec| {
            spec.kind == ChannelKind::Vec3
                && spec.unit.as_deref() == Some(expected_unit)
                && spec
                    .size
                    .is_none_or(|size| size == SAFETY_VECTOR_WIDTH as i64)
        })
    }

    /// Resolve safety inputs from negotiated [`Capabilities`]. Safety semantics
    /// bind to the explicit canonical `pose_position` and `velocity_setpoint`
    /// names, never whichever declaration happens to be first. An enabled limit
    /// requires the matching spec to be `vec3`, width 3 (implicit or `size=3`),
    /// and in its canonical SI unit.
    pub fn from_capabilities(caps: &Capabilities) -> Self {
        let command_channels: Vec<String> = caps
            .command_channels
            .iter()
            .map(|c| c.name.clone())
            .collect();
        let sensor_channels: Vec<String> = caps
            .sensor_channels
            .iter()
            .map(|c| c.name.clone())
            .collect();
        let position_contract_valid = Self::compatible_safety_vec3(
            caps.sensor_channels
                .iter()
                .find(|channel| channel.name == POSITION_CHANNEL),
            POSITION_UNIT,
        );
        let velocity_contract_valid = Self::compatible_safety_vec3(
            caps.command_channels
                .iter()
                .find(|channel| channel.name == VELOCITY_CHANNEL),
            VELOCITY_UNIT,
        );
        let mut governor = Self::with_channels(
            caps.safety.clone(),
            POSITION_CHANNEL,
            VELOCITY_CHANNEL,
            command_channels,
            sensor_channels,
        );
        governor.position_contract_valid = position_contract_valid;
        governor.velocity_contract_valid = velocity_contract_valid;
        governor.config_fail_closed |= governor.enabled_channel_contract_invalid();
        governor
    }

    fn enabled_channel_contract_invalid(&self) -> bool {
        (self
            .limits
            .geofence_radius_m
            .is_some_and(|radius| radius > 0.0)
            && !self.position_contract_valid)
            || ((self.limits.max_speed_mps.is_some_and(|speed| speed > 0.0)
                || self
                    .limits
                    .geofence_radius_m
                    .is_some_and(|radius| radius > 0.0))
                && !self.velocity_contract_valid)
    }

    fn valid_safety_vector(channel: &ChannelValue, expected_unit: &str) -> bool {
        channel.unit.as_deref() == Some(expected_unit)
            && channel.data.len() == SAFETY_VECTOR_WIDTH
            && channel.data.iter().all(|value| value.is_finite())
    }

    /// Clear a latched ESTOP. Only a supervisor calls this — after a fresh govern
    /// the latch may re-engage if the tripping condition still holds. A config-level
    /// fail-closed latch (undeclared limit channel) is NOT cleared: it is an
    /// unrecoverable misconfiguration, not a transient breach.
    pub fn reset(&mut self) {
        self.estop = false;
    }

    /// True while ESTOP is latched.
    pub fn is_estopped(&self) -> bool {
        self.estop
    }

    /// Latch ESTOP when the link monitor reports a sustained loss burst (a jam) —
    /// the documented Layer-3 fail-safe escalation. A collapsed link is NOT a
    /// transient HOLD; it de-energizes to a latched safe state until a supervisor
    /// [`reset`](SafetyGovernor::reset)s (an operator-supplied loss-rate threshold may gate this too, but
    /// the CUSUM `burst` is the trip today). Without this, a jammed craft sits in
    /// self-clearing HOLD forever while the link is dead.
    pub fn note_link(&mut self, burst: bool) {
        if burst {
            self.estop = true; // latch
        }
    }

    /// Whether the last governed command was safe. False under a latched ESTOP or a
    /// config-level fail-closed (undeclared limit channel). The loop reports this
    /// in `ControlStatus.safety_ok`.
    pub fn safety_ok(&self) -> bool {
        !self.estop && !self.config_fail_closed
    }

    /// Zero the union of the inbound command's channels and the negotiated command
    /// channels, preserving each channel's arity (width) and unit so the HOLD/ESTOP
    /// frame is shaped exactly like the live command — no channel is silently
    /// dropped or left unzeroed.
    fn zeroed_channels(&self, command: &CommandFrame) -> crate::messages::Map<ChannelValue> {
        let mut m = crate::messages::Map::new();
        for (name, cv) in &command.channels {
            if name.is_empty() || name.chars().any(char::is_control) {
                continue;
            }
            let (width, unit) = if name == &self.velocity_channel {
                (SAFETY_VECTOR_WIDTH, Some(VELOCITY_UNIT.to_string()))
            } else {
                (cv.data.len().max(1), cv.unit.clone())
            };
            m.insert(
                name.clone(),
                ChannelValue {
                    data: vec![0.0; width],
                    unit,
                },
            );
        }
        for name in &self.command_channels {
            if name.is_empty() || name.chars().any(char::is_control) {
                continue;
            }
            m.entry(name.clone()).or_insert_with(|| {
                if name == &self.velocity_channel {
                    ChannelValue::vec3(0.0, 0.0, 0.0, Some(VELOCITY_UNIT))
                } else {
                    ChannelValue::scalar(0.0, None)
                }
            });
        }
        m
    }

    fn safe_envelope(command: &CommandFrame) -> (f64, i64, String) {
        let t = if command.t.is_finite() {
            command.t
        } else {
            0.0
        };
        let seq = if (1..=JSON_SAFE_INTEGER_MAX).contains(&command.seq) {
            command.seq
        } else {
            1
        };
        let frame_id =
            if command.frame_id.is_empty() || command.frame_id.chars().any(char::is_control) {
                "world".to_string()
            } else {
                command.frame_id.clone()
            };
        (t, seq, frame_id)
    }

    fn estop_frame(&self, command: &CommandFrame) -> CommandFrame {
        let (t, seq, frame_id) = Self::safe_envelope(command);
        CommandFrame {
            t,
            seq,
            frame_id,
            mode: Mode::Estop,
            channels: self.zeroed_channels(command),
            ..Default::default()
        }
    }

    fn hold_frame(&self, command: &CommandFrame) -> CommandFrame {
        let (t, seq, frame_id) = Self::safe_envelope(command);
        CommandFrame {
            t,
            seq,
            frame_id,
            mode: Mode::Hold,
            channels: self.zeroed_channels(command),
            ..Default::default()
        }
    }

    /// Apply safety to `command`. `now_s` and `last_sensor_s` are wall-clock
    /// seconds; a missing/old sensor forces HOLD (fail-safe to zero, **not**
    /// latch-last). ESTOP **latches**: once tripped, every later call returns a
    /// zeroed ESTOP until [`reset`](SafetyGovernor::reset). Takes `&mut self` because of that latch.
    pub fn govern(
        &mut self,
        command: &CommandFrame,
        sensor: Option<&SensorFrame>,
        now_s: f64,
        last_sensor_s: Option<f64>,
    ) -> CommandFrame {
        // Latched ESTOP dominates everything until a supervisor reset.
        if self.estop {
            return self.estop_frame(command);
        }
        // An INBOUND ESTOP-mode command is itself a fail-safe: LATCH and
        // propagate it (zeroed ESTOP out), never downgrade it to a non-latching
        // HOLD — mirroring `ActionBuffer::on_command`'s "a fail-safe is never
        // dropped" rule, so an explicit ESTOP latches at every layer.
        if command.mode == Mode::Estop {
            self.estop = true;
            return self.estop_frame(command);
        }
        // `limits` is public for source compatibility. Enabling a limit after
        // construction must not bypass an incompatible negotiated channel spec.
        if self.enabled_channel_contract_invalid() {
            self.config_fail_closed = true;
        }

        // A timestamp without the actual validated sensor document is not proof
        // of perception liveness. Hostile/misrouted/versionless sensors HOLD.
        let sensor = sensor.filter(|frame| frame.validate_wire().is_ok());

        // A configured-but-nonsensical geofence/speed limit (non-finite or
        // negative) must fail closed, not silently disable enforcement:
        // `NaN > 0.0` and `-5.0 > 0.0` are BOTH false, so the geofence/speed
        // blocks below would skip entirely — a fail-OPEN that lets unbounded
        // motion through. `limits` is a public, post-construction-mutable field,
        // so guard here at every tick (not only at construction), and latch
        // `config_fail_closed` so `safety_ok()` reports the misconfiguration.
        // `0.0` stays the documented "disabled" value — only `< 0` / non-finite trips.
        if Self::invalid_numeric_limits(&self.limits) {
            self.config_fail_closed = true; // unrecoverable misconfig -> safety_ok()=false
        }

        // Config-level fail-closed (an undeclared/incompatible channel or bad
        // numeric limit): HOLD every command; `safety_ok()` reports false.
        if self.config_fail_closed {
            return self.hold_frame(command);
        }

        // Default-deny on a bad command_timeout_ms: a non-finite / zero / negative
        // timeout is treated as "always stale" (HOLD), never "never stale". Note
        // `f64::NAN.max(0.0) == 0.0`, so the old `.max(0.0)` pre-clamp turned NaN
        // into a never-stale 0 — fail-open. Compare the raw ms value instead.
        // A huge-but-finite timeout is just as capable of defeating freshness as
        // +Inf. Enforcement is local and bounded even though the wire preserves
        // the configured value, mirroring the command TTL watchdog.
        let timeout_ms = self.limits.command_timeout_ms.min(MAX_TTL_MS);
        let timeout_s = timeout_ms / 1000.0;
        let stale = sensor.is_none()
            || match last_sensor_s {
                None => true,
                Some(last) => {
                    // A non-finite clock (NaN/±inf `now_s` or `last`) makes the
                    // `(now_s - last) >= timeout_s` comparison NaN→false — i.e. "not
                    // stale", a fail-OPEN on a bad clock. Treat any non-finite clock
                    // input as stale (HOLD), defaulting the staleness backstop closed.
                    !now_s.is_finite()
                    || !last.is_finite()
                    || !timeout_ms.is_finite()
                    || timeout_ms <= 0.0
                    || !timeout_s.is_finite()
                    // A non-monotonic (backward) clock step makes `(now_s - last)`
                    // negative → never `> timeout_s` → "not stale", a fail-OPEN on a
                    // rewound clock. Treat any backward step as stale (HOLD).
                    || now_s < last
                    || (now_s - last) >= timeout_s
                }
            };
        if stale {
            // Sustained TOTAL silence escalates HOLD -> latched ESTOP. A single
            // missed deadline is a transient (non-latching HOLD, self-clears when
            // data resumes), but a link that stays silent past
            // `LINK_LOSS_ESTOP_FACTOR` deadlines is a collapsed link and must
            // de-energize to a latched safe state — the intent `note_link`
            // documents. The CUSUM jam burst (`note_link`) only fires on ARRIVING
            // gappy frames, so without this a fully silent link would sit in
            // self-clearing HOLD forever. Wire-invisible: the escalation deadline
            // is derived from the existing `command_timeout_ms` (capped at
            // `MAX_TTL_MS`), not a new `SafetyLimits` field.
            if let Some(last) = last_sensor_s {
                if now_s.is_finite() && last.is_finite() && now_s >= last {
                    let deadline_s = (timeout_s * LINK_LOSS_ESTOP_FACTOR).min(MAX_TTL_MS / 1000.0);
                    if (now_s - last) >= deadline_s {
                        self.estop = true; // latch: the link is collapsed
                        return self.estop_frame(command);
                    }
                }
            }
            // HOLD is non-latching — do NOT set self.estop.
            return self.hold_frame(command);
        }

        // `stale` includes missing/invalid sensor documents, so reaching this
        // point proves the frame passed `validate_wire` above.
        let sensor = sensor.expect("non-stale safety path has a validated sensor");

        // Geofence: if a positive radius is configured we MUST be able to evaluate
        // it. An absent position channel (sensor missing it, or no sensor) is a
        // fail-closed condition, not a silent no-op.
        if let Some(radius) = self.limits.geofence_radius_m {
            if radius > 0.0 {
                let pos = sensor.channels.get(&self.position_channel);
                match pos {
                    None => {
                        // Cannot evaluate the fence -> fail closed. HOLD (non-latching:
                        // the channel may reappear) with safety_ok=false at the caller.
                        return self.hold_frame(command);
                    }
                    Some(pos) => {
                        // The limit is metres over a three-dimensional position.
                        // Summing a truncated vector understates distance; accepting
                        // an unrecognised unit silently rescales the fence.
                        if !Self::valid_safety_vector(pos, POSITION_UNIT) {
                            return self.hold_frame(command);
                        }
                        let r = pos.data.iter().map(|c| c * c).sum::<f64>().sqrt();
                        // A non-finite `r` (NaN from upstream) fails safe to ESTOP
                        // rather than silently passing the `r > radius` comparison.
                        if !r.is_finite() || r > radius {
                            self.estop = true; // latch
                            return self.estop_frame(command);
                        }
                    }
                }
            }
        }

        // Freshness, total-silence escalation, and the CURRENT geofence state
        // deliberately run before command validation/mode checks. A controller
        // HOLD (or malformed non-ESTOP frame) is safe for this tick, but it must
        // not mask a collapsed link or an already-breached physical boundary.
        // The governor remains an actuation boundary for direct Rust callers: a
        // typed struct is not authority for prospective motion.
        if command.validate_wire().is_err() {
            return self.hold_frame(command);
        }

        // Only `Active` commands may actuate. A remaining non-Active inbound mode
        // (Init/Hold, or any mode added later) must never drive the plant.
        if !matches!(command.mode, Mode::Active) {
            return self.hold_frame(command);
        }

        let mut out = command.clone();
        if let Some(max_speed) = self.limits.max_speed_mps {
            if max_speed > 0.0 {
                // Tick 0: an absent or non-finite velocity cannot be enforced ->
                // fail closed (HOLD).
                if self.clamp_velocity(&mut out.channels, max_speed).is_err() {
                    return self.hold_frame(command);
                }
                // CRITICAL: clamp every predictive horizon step too. The
                // ActionBuffer replays `horizon[i]` verbatim on every tick after
                // 0, so an unclamped horizon defeats the speed limit for the whole
                // ride-through window. A step that cannot be clamped (absent /
                // non-finite velocity) truncates the horizon there, so replay
                // HOLDs rather than emitting an unbounded setpoint.
                let mut safe_len = out.horizon.len();
                for (i, step) in out.horizon.iter_mut().enumerate() {
                    if self.clamp_velocity(step, max_speed).is_err() {
                        // `ActionBuffer` treats an empty horizon as the legacy
                        // "hold tick-0 until ttl" form. Truncating a non-empty
                        // horizon to zero would therefore do the opposite of
                        // HOLD and replay the current setpoint. If the first
                        // future step is unsafe, reject the entire command.
                        if i == 0 {
                            return self.hold_frame(command);
                        }
                        safe_len = i;
                        break;
                    }
                }
                out.horizon.truncate(safe_len);
            }
        }

        // Prospective geofence enforcement: an in-bounds sample is not enough.
        // `ActionBuffer` may replay tick 0 until ttl (legacy/no-horizon form) or
        // replay each predictive step open-loop. Project the actual canonical
        // velocity trajectory through that entire possible actuation window and
        // reject/truncate before it can cross the sphere.
        if let Some(radius) = self.limits.geofence_radius_m {
            if radius > 0.0 {
                if command.frame_id != sensor.frame_id {
                    return self.hold_frame(command);
                }
                let pos = sensor
                    .channels
                    .get(&self.position_channel)
                    .expect("positive geofence validated position above");
                if self
                    .enforce_geofence_trajectory(&mut out, pos, radius)
                    .is_err()
                {
                    return self.hold_frame(command);
                }
            }
        }
        out
    }

    fn enforce_geofence_trajectory(
        &self,
        command: &mut CommandFrame,
        position: &ChannelValue,
        radius: f64,
    ) -> Result<(), ()> {
        let mut projected = [position.data[0], position.data[1], position.data[2]];
        let ttl_s = command.ttl_ms.min(MAX_TTL_MS) / 1000.0;
        if !ttl_s.is_finite() || ttl_s <= 0.0 {
            return Err(());
        }

        if command.horizon.is_empty() {
            return self
                .advance_geofence_position(&mut projected, &command.channels, ttl_s, radius)
                .and_then(|inside| inside.then_some(()).ok_or(()));
        }

        let dt_s = command.horizon_dt_ms.ok_or(())? / 1000.0;
        if !dt_s.is_finite() || dt_s <= 0.0 {
            return Err(());
        }
        let tick_zero_s = ttl_s.min(dt_s);
        if !self.advance_geofence_position(
            &mut projected,
            &command.channels,
            tick_zero_s,
            radius,
        )? {
            return Err(());
        }
        let mut remaining_s = (ttl_s - tick_zero_s).max(0.0);
        let mut safe_len = command.horizon.len();
        for (index, step) in command.horizon.iter().enumerate() {
            if remaining_s <= 0.0 {
                break; // watchdog expires before this step; leaving it is inert
            }
            let duration_s = remaining_s.min(dt_s);
            let safe = self
                .advance_geofence_position(&mut projected, step, duration_s, radius)
                .unwrap_or(false);
            if !safe {
                // Empty has legacy "replay tick 0" semantics. We cannot encode
                // "tick 0 then drain" with a zero-length horizon, so rejecting
                // the whole command is the only fail-closed decision at index 0.
                if index == 0 {
                    return Err(());
                }
                safe_len = index;
                break;
            }
            remaining_s = (remaining_s - duration_s).max(0.0);
        }
        command.horizon.truncate(safe_len);
        Ok(())
    }

    fn advance_geofence_position(
        &self,
        position: &mut [f64; SAFETY_VECTOR_WIDTH],
        channels: &crate::messages::Map<ChannelValue>,
        duration_s: f64,
        radius: f64,
    ) -> Result<bool, ()> {
        let velocity = channels.get(&self.velocity_channel).ok_or(())?;
        if !Self::valid_safety_vector(velocity, VELOCITY_UNIT)
            || !duration_s.is_finite()
            || duration_s < 0.0
        {
            return Err(());
        }
        for (coordinate, speed) in position.iter_mut().zip(&velocity.data) {
            *coordinate += speed * duration_s;
        }
        let norm = position
            .iter()
            .map(|value| value * value)
            .sum::<f64>()
            .sqrt();
        Ok(norm.is_finite() && norm <= radius)
    }

    /// Clamp the velocity channel of `channels` to `max_speed` (m/s), in place,
    /// preserving direction and unit. `Ok(())` if it was within the limit or
    /// successfully scaled down; `Err(())` if the velocity channel is absent, not
    /// exactly a width-3 `m/s` vector, or has non-finite magnitude — i.e. the limit
    /// cannot be enforced and the caller must fail safe. Shared by tick 0 and every
    /// horizon step so the speed bound holds across the entire predictive replay.
    fn clamp_velocity(
        &self,
        channels: &mut crate::messages::Map<ChannelValue>,
        max_speed: f64,
    ) -> Result<(), ()> {
        let vel = channels.get(&self.velocity_channel).ok_or(())?;
        if !Self::valid_safety_vector(vel, VELOCITY_UNIT) {
            return Err(());
        }
        let mag = vel.data.iter().map(|c| c * c).sum::<f64>().sqrt();
        if !mag.is_finite() {
            return Err(());
        }
        if mag > max_speed {
            let k = max_speed / mag;
            let data: Vec<f64> = vel.data.iter().map(|c| c * k).collect();
            let unit = vel.unit.clone();
            channels.insert(self.velocity_channel.clone(), ChannelValue { data, unit });
        }
        Ok(())
    }
}

/// Plant-side deadline backstop that **enforces `CommandFrame.ttl_ms`** — which is
/// otherwise carried on the wire but never checked. Feed each accepted command's
/// **local** arrival time and its `ttl_ms`; the plant must fail safe (HOLD to a
/// zero/safe setpoint) once the latest command has expired or none has arrived.
/// Using the plant's own clock avoids controller↔plant clock skew. This is the
/// deadline backstop the packetized-predictive-control horizon (see RESILIENCE.md)
/// relies on: replay buffered predictions only while unexpired, HOLD on drain.
/// Upper bound on an enforced command ttl. The wire field `ttl_ms` is unbounded,
/// but the plant-side deadline backstop must stay finite: an absurdly large (or
/// `+Inf`) ttl would let a single command keep the plant "live" indefinitely,
/// defeating the watchdog. 60 s is far beyond any real control deadline.
pub const MAX_TTL_MS: f64 = 60_000.0;

/// How many consecutive `command_timeout_ms` deadlines of TOTAL sensor silence
/// escalate the non-latching staleness HOLD to a latched ESTOP. One missed
/// deadline is a transient (HOLD); staying silent this many deadlines means the
/// link is collapsed, which must de-energize to a latched safe state (a
/// supervisor `reset` is then required). Fail-safe over-triggering (a spurious
/// ESTOP on a long-but-recoverable dropout) is acceptable; failing OPEN — sitting
/// in self-clearing HOLD on a dead link — is not.
const LINK_LOSS_ESTOP_FACTOR: f64 = 20.0;

#[derive(Clone, Copy, Debug, Default)]
struct WatchdogClock {
    high_water_s: Option<f64>,
    faulted: bool,
}

#[derive(Debug)]
pub struct CommandWatchdog {
    last_recv_s: Option<f64>,
    ttl_s: f64,
    /// Highest accepted command `seq`. The deadline refreshes only on a strictly
    /// advancing seq, so a stale/duplicate command cannot extend liveness.
    last_seq: i64,
    /// Highest local clock sample observed by either ingestion or enforcement.
    /// Interior state is intentional: `should_hold(&self)` is the polling API,
    /// and a rewind seen there must revoke authority for later ingestion too.
    clock: std::sync::Mutex<WatchdogClock>,
}

impl Clone for CommandWatchdog {
    fn clone(&self) -> Self {
        let clock = *self.clock.lock().unwrap_or_else(|error| error.into_inner());
        Self {
            last_recv_s: self.last_recv_s,
            ttl_s: self.ttl_s,
            last_seq: self.last_seq,
            clock: std::sync::Mutex::new(clock),
        }
    }
}

impl Default for CommandWatchdog {
    fn default() -> Self {
        Self {
            last_recv_s: None,
            ttl_s: 0.0,
            last_seq: 0,
            clock: std::sync::Mutex::new(WatchdogClock::default()),
        }
    }
}

impl CommandWatchdog {
    pub fn new() -> Self {
        Self::default()
    }

    /// `Some(true)` means the clock has caught up but a fresh command is still
    /// required; `Some(false)` is healthy; `None` is a fault at this sample.
    fn observe_clock(&self, now_s: f64) -> Option<bool> {
        let mut clock = self.clock.lock().unwrap_or_else(|error| error.into_inner());
        if !now_s.is_finite() {
            clock.faulted = true;
            return None;
        }
        if let Some(high_water) = clock.high_water_s {
            if now_s < high_water {
                clock.faulted = true;
                return None;
            }
        }
        clock.high_water_s = Some(now_s);
        Some(clock.faulted)
    }

    fn clear_clock_fault(&self) {
        self.clock
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .faulted = false;
    }

    /// Record an accepted command received at local time `now_s` with its `ttl_ms`
    /// and `seq`. The deadline refreshes only when `seq` strictly advances — a
    /// duplicate/stale/replayed command (`seq <= last`) must NOT extend liveness, or
    /// a trickle of stale frames would keep the plant "fresh" forever.
    ///
    /// Wire 0.6: `seq < 1` (unstamped/negative — including the `0` serde default)
    /// NEVER refreshes liveness. The pre-0.6 "`seq == 0` always refreshes" escape
    /// hatch let a default-constructed or hostile all-zeros frame keep the plant
    /// "commanded" forever, defeating the deadline backstop.
    ///
    /// **Stream-epoch re-anchor (restart recovery):** a *strictly-lower* `seq` is
    /// additionally accepted when the stream is already EXPIRED
    /// ([`should_hold`](Self::should_hold) is true) — a legitimately restarted
    /// controller restarts its counter at 1, and without this rule the plant would
    /// reject its frames forever. An *equal* `seq` NEVER re-anchors: a single
    /// frozen/replayed frame re-delivered across expiry windows must fail safe
    /// permanently, not duty-cycle liveness. Re-anchoring only from the expired
    /// (already holding, safe) state grants nothing an injecting attacker could
    /// not get by forging a fresh high `seq` — the wire is unauthenticated (see
    /// SECURITY.md); seq discipline defends against transport artifacts and buggy
    /// peers, and integrity against adversaries is mTLS's job.
    pub fn on_command(&mut self, now_s: f64, ttl_ms: f64, seq: i64) {
        let Some(recovering_clock) = self.observe_clock(now_s) else {
            return;
        };
        if !(1..=JSON_SAFE_INTEGER_MAX).contains(&seq) {
            return; // unstamped/invalid seq never refreshes liveness (wire 0.6)
        }
        if seq <= self.last_seq
            && (seq == self.last_seq || (!recovering_clock && !self.should_hold(now_s)))
        {
            return; // duplicate (always), or stale/reordered while the stream is LIVE
        }
        self.last_seq = seq;
        self.last_recv_s = Some(now_s);
        // Bound the enforced ttl: a non-finite `ttl_ms` (e.g. `+Inf`) makes
        // `(now - t) > ttl_s` never true → the backstop never fires (fail-OPEN).
        // Map non-finite to 0 (immediately stale) and clamp very large values to a
        // finite ceiling. The wire still carries `ttl_ms` unchanged.
        self.ttl_s = if ttl_ms.is_finite() {
            ttl_ms.clamp(0.0, MAX_TTL_MS) / 1000.0
        } else {
            0.0
        };
        self.clear_clock_fault();
    }

    /// True if the plant must fail safe to HOLD: no command yet, or the latest is
    /// past its ttl. (A non-positive ttl is treated as immediately stale.)
    pub fn should_hold(&self, now_s: f64) -> bool {
        if self.observe_clock(now_s) != Some(false) {
            return true;
        }
        match self.last_recv_s {
            None => true,
            // A non-finite clock (`now_s` or the stored `t`) makes
            // `(now_s - t) >= ttl_s` evaluates NaN→false — "not expired", a
            // fail-OPEN backstop on a bad clock. Treat any non-finite clock as
            // expired (HOLD), so the deadline backstop defaults closed.
            Some(t) => {
                !now_s.is_finite()
                    || !t.is_finite()
                    || self.ttl_s <= 0.0
                    // A backward clock step makes `(now_s - t)` negative → never
                    // `>= ttl_s` → "not expired", a fail-OPEN on a rewound clock.
                    // Treat any backward step as expired (HOLD).
                    || now_s < t
                    || (now_s - t) >= self.ttl_s
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn active_command() -> CommandFrame {
        CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: channels_with("velocity_setpoint", 1.0, "m/s"),
            ..Default::default()
        }
    }

    fn fresh_sensor() -> SensorFrame {
        SensorFrame {
            seq: 1,
            ..Default::default()
        }
    }

    #[test]
    fn command_watchdog_enforces_ttl() {
        let mut wd = CommandWatchdog::new();
        assert!(wd.should_hold(0.0), "no command yet -> HOLD");
        wd.on_command(1.0, 200.0, 1); // ttl 200 ms
        assert!(!wd.should_hold(1.1), "within ttl -> apply");
        assert!(wd.should_hold(1.3), "0.3 s > 0.2 s ttl -> HOLD");

        let mut exact = CommandWatchdog::new();
        exact.on_command(0.0, 1_000.0, 1);
        assert!(
            exact.should_hold(1.0),
            "the command expires at its deadline, not one tick after it"
        );
    }

    #[test]
    fn duplicate_command_does_not_extend_ttl() {
        let mut wd = CommandWatchdog::new();
        wd.on_command(1.0, 200.0, 5); // accepted; ttl 200 ms
                                      // Stale/duplicate commands (seq <= 5) must NOT refresh the deadline.
        wd.on_command(1.15, 200.0, 5); // duplicate
        wd.on_command(1.15, 200.0, 3); // older
        assert!(
            wd.should_hold(1.25),
            "deadline anchored at the seq=5 command; stale frames must not extend it"
        );
        // A strictly-advancing command refreshes it.
        wd.on_command(1.25, 200.0, 6);
        assert!(!wd.should_hold(1.3), "seq=6 advances -> refreshed");
    }

    #[test]
    fn unstamped_or_negative_seq_never_refreshes() {
        // Wire 0.6: the pre-0.6 "seq == 0 always refreshes" escape hatch is GONE.
        // A spray of unstamped (0) or garbage (negative / i64::MIN) frames must
        // never grant liveness — that was the anti-replay/anti-stale bypass.
        let mut wd = CommandWatchdog::new();
        for bad_seq in [0, -1, i64::MIN, JSON_SAFE_INTEGER_MAX + 1, i64::MAX] {
            wd.on_command(1.0, 200.0, bad_seq);
            assert!(
                wd.should_hold(1.05),
                "seq {bad_seq} must not refresh the deadline"
            );
        }
        // ...and on a LIVE stream they must not disturb the anchor either.
        wd.on_command(2.0, 200.0, 7);
        wd.on_command(2.05, 200.0, 0);
        wd.on_command(2.05, 200.0, -9);
        assert!(
            !wd.should_hold(2.1),
            "live seq=7 deadline unaffected by garbage"
        );
        assert!(
            wd.should_hold(2.3),
            "…and the deadline still expires on time"
        );
    }

    #[test]
    fn restart_reanchors_only_after_expiry() {
        let mut wd = CommandWatchdog::new();
        wd.on_command(1.0, 200.0, 1000); // live stream at seq 1000
                                         // While LIVE, a lower/equal seq (replay or premature restart) is rejected.
        wd.on_command(1.05, 200.0, 1);
        assert!(
            wd.should_hold(1.35),
            "a low seq on a live stream must not refresh (deadline still anchored at t=1.0)"
        );
        // After expiry (the plant is already HOLDing — a safe state), a restarted
        // controller's low seq re-anchors the stream and restores liveness.
        assert!(wd.should_hold(1.5), "expired");
        wd.on_command(1.5, 200.0, 1); // restart epoch: seq restarts at 1
        assert!(!wd.should_hold(1.6), "post-expiry restart re-anchors");
        // The new epoch's discipline applies: its own replays are rejected.
        wd.on_command(1.62, 200.0, 1);
        assert!(
            wd.should_hold(1.75),
            "duplicate within the new epoch does not refresh"
        );
        // The largest JSON-safe wire sequence is accepted without panic; a
        // duplicate at that bound cannot advance.
        let mut wd2 = CommandWatchdog::new();
        wd2.on_command(0.0, 200.0, JSON_SAFE_INTEGER_MAX);
        assert!(!wd2.should_hold(0.1));
        wd2.on_command(0.15, 200.0, JSON_SAFE_INTEGER_MAX);
        assert!(
            wd2.should_hold(0.3),
            "a duplicate at the JSON-safe bound does not extend the deadline"
        );
    }

    #[test]
    fn nan_clock_on_command_stays_fail_safe() {
        // A non-finite receive clock corrupts nothing observable: the stored
        // deadline is non-finite, so should_hold stays true (fail-closed), and a
        // later valid-clock frame re-anchors (the stream reads as expired).
        let mut wd = CommandWatchdog::new();
        wd.on_command(f64::NAN, 200.0, 1);
        assert!(wd.should_hold(0.1), "NaN-anchored deadline must HOLD");
        wd.on_command(5.0, 200.0, 2);
        assert!(!wd.should_hold(5.1), "a valid frame recovers liveness");
    }

    #[test]
    fn unbounded_or_nonfinite_ttl_still_expires() {
        // +Inf ttl must NOT mean "never stale" (that would let one command keep
        // the plant live forever — fail-OPEN). It is clamped to a finite ceiling.
        let mut wd = CommandWatchdog::new();
        wd.on_command(0.0, f64::INFINITY, 1);
        assert!(
            wd.should_hold(MAX_TTL_MS / 1000.0 + 1.0),
            "a +Inf ttl must still expire past the finite ceiling"
        );
        // NaN ttl -> immediately stale (fail-safe).
        let mut wd2 = CommandWatchdog::new();
        wd2.on_command(0.0, f64::NAN, 1);
        assert!(
            wd2.should_hold(0.001),
            "a NaN ttl is treated as immediately stale"
        );
    }

    #[test]
    fn empty_position_holds_under_geofence() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(10.0),
            ..Default::default()
        });
        // A declared position channel that arrives with no data must not read as
        // r = sqrt(0) = 0 ("at the origin", inside the fence) — fail closed to HOLD.
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "pose_position".to_string(),
            ChannelValue {
                data: vec![],
                unit: Some("m".into()),
            },
        );
        let sensor = SensorFrame {
            seq: 1,
            channels: ch,
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&sensor), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Hold,
            "an empty position vector must fail closed (HOLD), not bypass the geofence"
        );
    }

    #[test]
    fn geofence_breach_latches_even_when_command_holds() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(5.0),
            ..Default::default()
        });
        let command = CommandFrame {
            seq: 1,
            mode: Mode::Hold,
            channels: channels_with("velocity_setpoint", 0.0, "m/s"),
            ..Default::default()
        };
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with("pose_position", 10.0, "m"),
            ..Default::default()
        };

        let out = gov.govern(&command, Some(&sensor), 1.0, Some(1.0));

        assert_eq!(out.mode, Mode::Estop);
        assert!(
            gov.is_estopped(),
            "a controller HOLD must not hide an already-breached geofence"
        );
    }

    #[test]
    fn note_link_burst_latches_estop() {
        let mut gov = SafetyGovernor::new(SafetyLimits::default());
        assert!(!gov.is_estopped());
        gov.note_link(false); // no jam -> no change
        assert!(!gov.is_estopped());
        gov.note_link(true); // jam burst -> latch
        assert!(gov.is_estopped(), "a link burst must latch ESTOP");
        gov.note_link(false); // a later clear link must NOT un-latch
        assert!(gov.is_estopped(), "ESTOP latch must persist until reset");
        gov.reset();
        assert!(!gov.is_estopped());
    }

    #[test]
    fn geofence_lookahead_projects_direction_and_truncates_before_crossing() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(10.0),
            max_speed_mps: Some(5.0),
            command_timeout_ms: 500.0,
            ..Default::default()
        });
        let cmd = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            ttl_ms: 500.0,
            channels: channels_with("velocity_setpoint", 1.0, "m/s"),
            horizon: vec![
                channels_with("velocity_setpoint", 1.0, "m/s"),
                channels_with("velocity_setpoint", 1.0, "m/s"),
                channels_with("velocity_setpoint", 1.0, "m/s"),
                channels_with("velocity_setpoint", 1.0, "m/s"),
            ],
            horizon_dt_ms: Some(100.0),
            ..Default::default()
        };
        // A gentle outward trajectory remains inside for its full ttl and should
        // not be discarded merely because the plant is near the boundary.
        let near = SensorFrame {
            seq: 1,
            channels: channels_with("pose_position", 9.0, "m"),
            ..Default::default()
        };
        let out = gov.govern(&cmd, Some(&near), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Active,
            "tick-0 inside the fence still actuates"
        );
        assert_eq!(out.horizon.len(), 4, "the exact safe trajectory is kept");

        // At 5 m/s: tick 0 reaches 9.5 m, horizon[0] reaches exactly 10 m,
        // horizon[1] would reach 10.5 m. Keep only the representable safe prefix.
        let crossing = CommandFrame {
            channels: channels_with("velocity_setpoint", 5.0, "m/s"),
            horizon: vec![
                channels_with("velocity_setpoint", 5.0, "m/s"),
                channels_with("velocity_setpoint", 5.0, "m/s"),
                channels_with("velocity_setpoint", 5.0, "m/s"),
            ],
            ..cmd.clone()
        };
        let out = gov.govern(&crossing, Some(&near), 1.5, Some(1.5));
        assert_eq!(out.mode, Mode::Active);
        assert_eq!(
            out.horizon.len(),
            1,
            "trajectory must drain before the first crossing step"
        );
        // r=3: well inside (3 < 10-2) -> horizon preserved.
        let inside = SensorFrame {
            seq: 2,
            channels: channels_with("pose_position", 3.0, "m"),
            ..Default::default()
        };
        let out2 = gov.govern(&cmd, Some(&inside), 2.0, Some(2.0));
        assert_eq!(
            out2.horizon.len(),
            4,
            "well inside the fence the horizon is kept"
        );
    }

    #[test]
    fn geofence_projects_legacy_tick_zero_for_the_full_ttl() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(10.0),
            command_timeout_ms: 500.0,
            ..Default::default()
        });
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with("pose_position", 9.9, "m"),
            ..Default::default()
        };
        let outward = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            ttl_ms: 200.0,
            channels: channels_with("velocity_setpoint", 1.0, "m/s"),
            ..Default::default()
        };
        assert_eq!(
            gov.govern(&outward, Some(&sensor), 1.0, Some(1.0)).mode,
            Mode::Hold,
            "legacy no-horizon tick 0 would cross while replayed to ttl"
        );

        let inward = CommandFrame {
            seq: 2,
            channels: channels_with("velocity_setpoint", -1.0, "m/s"),
            ..outward
        };
        assert_eq!(
            gov.govern(&inward, Some(&sensor), 2.0, Some(2.0)).mode,
            Mode::Active,
            "direction-aware projection must preserve an inward command"
        );

        let body_frame = CommandFrame {
            seq: 3,
            frame_id: "body".into(),
            ..inward
        };
        assert_eq!(
            gov.govern(&body_frame, Some(&sensor), 3.0, Some(3.0)).mode,
            Mode::Hold,
            "position and velocity must share one coordinate frame"
        );
    }

    #[test]
    fn first_unsafe_horizon_step_cannot_become_legacy_replay() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            max_speed_mps: Some(1.0),
            ..Default::default()
        });
        let cmd = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            ttl_ms: 200.0,
            channels: channels_with("velocity_setpoint", 0.5, "m/s"),
            horizon: vec![channels_with("velocity_setpoint", 0.5, "km/h")],
            horizon_dt_ms: Some(50.0),
            ..Default::default()
        };
        let out = gov.govern(&cmd, Some(&fresh_sensor()), 1.0, Some(1.0));
        assert_eq!(out.mode, Mode::Hold);
        assert!(out.horizon.is_empty());
    }

    fn channels_with(name: &str, x: f64, unit: &str) -> crate::messages::Map<ChannelValue> {
        let mut m = crate::messages::Map::new();
        m.insert(
            name.to_string(),
            ChannelValue::vec3(x, 0.0, 0.0, Some(unit)),
        );
        m
    }

    fn channel_spec(
        name: &str,
        kind: ChannelKind,
        unit: Option<&str>,
        size: Option<i64>,
    ) -> ChannelSpec {
        ChannelSpec {
            name: name.into(),
            kind,
            unit: unit.map(str::to_string),
            size,
            ..Default::default()
        }
    }

    #[test]
    fn nan_velocity_setpoint_fails_safe_to_hold() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            max_speed_mps: Some(5.0),
            ..Default::default()
        });
        let cmd = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: channels_with("velocity_setpoint", f64::NAN, "m/s"),
            ..Default::default()
        };
        // Fresh sensor (now == last → not stale); a NaN must not slip past the clamp.
        let out = gov.govern(&cmd, Some(&fresh_sensor()), 1.0, Some(1.0));
        assert_eq!(out.mode, Mode::Hold, "NaN velocity must fail safe to HOLD");
        let v = out
            .channels
            .get("velocity_setpoint")
            .expect("setpoint present");
        assert!(v.data.iter().all(|c| *c == 0.0), "HOLD zeroes the setpoint");
    }

    #[test]
    fn nonfinite_sensor_payload_holds_before_geofence_evaluation() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(10.0),
            ..Default::default()
        });
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with("pose_position", f64::NAN, "m"),
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&sensor), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Hold,
            "an invalid non-finite SensorFrame must fail closed before geofence evaluation"
        );
        assert!(
            !gov.is_estopped(),
            "an invalid frame is dropped; it cannot assert a breach"
        );
    }

    #[test]
    fn zero_geofence_radius_is_disabled() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(0.0),
            ..Default::default()
        });
        // pose 3,0,0 → r=3 > 0; with radius 0 the fence is disabled (matches loop.py).
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with("pose_position", 3.0, "m"),
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&sensor), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Active,
            "radius 0 disables the geofence; no ESTOP"
        );
    }

    // ───────────────────────── FIX 1: ESTOP latches until reset ─────────────────────────

    #[test]
    fn estop_latches_until_reset() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(10.0),
            ..Default::default()
        });
        // Breach the fence: pose 99,0,0 -> r=99 > 10 -> ESTOP.
        let breach = SensorFrame {
            seq: 1,
            channels: channels_with("pose_position", 99.0, "m"),
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&breach), 1.0, Some(1.0));
        assert_eq!(out.mode, Mode::Estop, "geofence breach must ESTOP");
        assert!(gov.is_estopped());
        assert!(!gov.safety_ok());

        // Now feed a perfectly safe state — the latch must keep returning ESTOP.
        let inside = SensorFrame {
            seq: 2,
            channels: channels_with("pose_position", 1.0, "m"),
            ..Default::default()
        };
        let still = gov.govern(&active_command(), Some(&inside), 2.0, Some(2.0));
        assert_eq!(
            still.mode,
            Mode::Estop,
            "ESTOP must latch — a safe sensor does NOT clear it"
        );
        let v = still
            .channels
            .get("velocity_setpoint")
            .expect("zeroed setpoint present");
        assert!(
            v.data.iter().all(|c| *c == 0.0),
            "latched ESTOP zeroes the command"
        );

        // Supervisor reset clears it; the next safe state is ACTIVE again.
        gov.reset();
        assert!(!gov.is_estopped());
        let after = gov.govern(&active_command(), Some(&inside), 3.0, Some(3.0));
        assert_eq!(
            after.mode,
            Mode::Active,
            "after reset a safe state resumes ACTIVE"
        );
    }

    // ───────────────── FIX 2: default-deny on a bad command_timeout_ms ─────────────────

    #[test]
    fn bad_command_timeout_defaults_to_hold() {
        for bad in [f64::NAN, 0.0, -5.0, f64::NEG_INFINITY] {
            let mut gov = SafetyGovernor::new(SafetyLimits {
                command_timeout_ms: bad,
                ..Default::default()
            });
            // last == now: under a *valid* timeout this is the freshest possible
            // sensor (not stale). A bad timeout must STILL force HOLD (fail closed),
            // never fall through to ACTIVE.
            let out = gov.govern(&active_command(), None, 10.0, Some(10.0));
            assert_eq!(
                out.mode,
                Mode::Hold,
                "timeout {bad} must fail closed to HOLD"
            );
        }
        // Sanity: a finite positive timeout with a fresh sensor is NOT stale.
        let mut ok = SafetyGovernor::new(SafetyLimits {
            command_timeout_ms: 500.0,
            ..Default::default()
        });
        assert_eq!(
            ok.govern(&active_command(), Some(&fresh_sensor()), 10.0, Some(10.0))
                .mode,
            Mode::Active
        );
    }

    #[test]
    fn capabilities_resolve_canonical_safety_channels_not_first_channels() {
        let caps = Capabilities {
            sensor_channels: vec![
                channel_spec("imu_accel", ChannelKind::Vec3, Some("m/s2"), None),
                channel_spec(
                    POSITION_CHANNEL,
                    ChannelKind::Vec3,
                    Some(POSITION_UNIT),
                    Some(3),
                ),
            ],
            command_channels: vec![
                channel_spec("thrust", ChannelKind::Scalar, Some("N"), None),
                channel_spec(
                    VELOCITY_CHANNEL,
                    ChannelKind::Vec3,
                    Some(VELOCITY_UNIT),
                    Some(3),
                ),
            ],
            safety: SafetyLimits {
                geofence_radius_m: Some(10.0),
                max_speed_mps: Some(1.0),
                ..Default::default()
            },
            ..Default::default()
        };
        let mut gov = SafetyGovernor::from_capabilities(&caps);
        assert!(gov.safety_ok(), "compatible canonical specs must negotiate");

        let command = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: channels_with(VELOCITY_CHANNEL, 2.0, VELOCITY_UNIT),
            ..Default::default()
        };
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with(POSITION_CHANNEL, 3.0, POSITION_UNIT),
            ..Default::default()
        };
        let out = gov.govern(&command, Some(&sensor), 1.0, Some(1.0));
        assert_eq!(out.mode, Mode::Active);
        assert_eq!(out.channels[VELOCITY_CHANNEL].data, vec![1.0, 0.0, 0.0]);
    }

    #[test]
    fn capabilities_fail_closed_on_incompatible_position_spec() {
        let incompatible = [
            channel_spec(POSITION_CHANNEL, ChannelKind::Vec3, None, Some(3)),
            channel_spec(POSITION_CHANNEL, ChannelKind::Vec3, Some("cm"), Some(3)),
            channel_spec(
                POSITION_CHANNEL,
                ChannelKind::Scalar,
                Some(POSITION_UNIT),
                None,
            ),
            channel_spec(
                POSITION_CHANNEL,
                ChannelKind::Vec3,
                Some(POSITION_UNIT),
                Some(2),
            ),
        ];
        for position in incompatible {
            let caps = Capabilities {
                sensor_channels: vec![position],
                command_channels: vec![channel_spec(
                    VELOCITY_CHANNEL,
                    ChannelKind::Vec3,
                    Some(VELOCITY_UNIT),
                    Some(3),
                )],
                safety: SafetyLimits {
                    geofence_radius_m: Some(10.0),
                    ..Default::default()
                },
                ..Default::default()
            };
            assert!(!SafetyGovernor::from_capabilities(&caps).safety_ok());
        }
    }

    #[test]
    fn capabilities_fail_closed_on_incompatible_velocity_spec() {
        let incompatible = [
            channel_spec(VELOCITY_CHANNEL, ChannelKind::Vec3, None, Some(3)),
            channel_spec(VELOCITY_CHANNEL, ChannelKind::Vec3, Some("km/h"), Some(3)),
            channel_spec(
                VELOCITY_CHANNEL,
                ChannelKind::Scalar,
                Some(VELOCITY_UNIT),
                None,
            ),
            channel_spec(
                VELOCITY_CHANNEL,
                ChannelKind::Vec3,
                Some(VELOCITY_UNIT),
                Some(4),
            ),
        ];
        for velocity in incompatible {
            let caps = Capabilities {
                command_channels: vec![velocity],
                safety: SafetyLimits {
                    max_speed_mps: Some(1.0),
                    ..Default::default()
                },
                ..Default::default()
            };
            assert!(!SafetyGovernor::from_capabilities(&caps).safety_ok());
        }
    }

    #[test]
    fn geofence_requires_a_projectable_velocity_contract() {
        let caps = Capabilities {
            sensor_channels: vec![channel_spec(
                POSITION_CHANNEL,
                ChannelKind::Vec3,
                Some(POSITION_UNIT),
                Some(3),
            )],
            safety: SafetyLimits {
                geofence_radius_m: Some(10.0),
                ..Default::default()
            },
            ..Default::default()
        };
        assert!(
            !SafetyGovernor::from_capabilities(&caps).safety_ok(),
            "a reactive-only fence cannot guarantee that replay stays in bounds"
        );
    }

    #[test]
    fn geofence_rejects_wrong_unit_or_truncated_position() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(5.0),
            ..Default::default()
        });
        for position in [
            ChannelValue {
                data: vec![3.0, 0.0, 0.0],
                unit: Some("cm".into()),
            },
            ChannelValue {
                data: vec![3.0],
                unit: Some(POSITION_UNIT.into()),
            },
        ] {
            let sensor = SensorFrame {
                seq: 1,
                channels: [(POSITION_CHANNEL.into(), position)].into_iter().collect(),
                ..Default::default()
            };
            let out = gov.govern(&active_command(), Some(&sensor), 1.0, Some(1.0));
            assert_eq!(out.mode, Mode::Hold);
            assert!(!gov.is_estopped());
        }
    }

    #[test]
    fn speed_clamp_rejects_wrong_unit_or_truncated_velocity() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            max_speed_mps: Some(1.0),
            ..Default::default()
        });
        for velocity in [
            ChannelValue {
                data: vec![0.5, 0.0, 0.0],
                unit: Some("km/h".into()),
            },
            ChannelValue {
                data: vec![0.5],
                unit: Some(VELOCITY_UNIT.into()),
            },
        ] {
            let command = CommandFrame {
                seq: 1,
                mode: Mode::Active,
                channels: [(VELOCITY_CHANNEL.into(), velocity)].into_iter().collect(),
                ..Default::default()
            };
            let out = gov.govern(&command, Some(&fresh_sensor()), 1.0, Some(1.0));
            assert_eq!(out.mode, Mode::Hold);
            assert_eq!(
                out.channels[VELOCITY_CHANNEL].data.len(),
                SAFETY_VECTOR_WIDTH
            );
        }
    }

    // ───────────── FIX 3: geofence on a non-default channel; absent => fail closed ─────────────

    #[test]
    fn geofence_breach_on_non_default_channel_still_holds() {
        // Negotiated channel names differ from the historical literals.
        let mut gov = SafetyGovernor::with_channels(
            SafetyLimits {
                geofence_radius_m: Some(10.0),
                ..Default::default()
            },
            "ned_pos",                 // position channel (geofence input)
            "thrust_vec",              // velocity channel
            vec!["thrust_vec".into()], // negotiated command channels
            vec!["ned_pos".into()],    // negotiated sensor channels
        );
        // Breach on the *negotiated* channel name, not "pose_position".
        let breach = SensorFrame {
            seq: 1,
            channels: channels_with("ned_pos", 50.0, "m"),
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&breach), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Estop,
            "breach on the negotiated channel must ESTOP, not no-op"
        );
    }

    #[test]
    fn geofence_channel_absent_from_specs_fails_closed() {
        // A geofence is configured but its position channel is not in the negotiated
        // sensor specs -> misconfiguration -> fail closed (HOLD + safety_ok=false).
        let mut gov = SafetyGovernor::with_channels(
            SafetyLimits {
                geofence_radius_m: Some(10.0),
                ..Default::default()
            },
            "pose_position", // geofence wants this...
            "velocity_setpoint",
            vec!["velocity_setpoint".into()],
            vec!["imu_accel".into()], // ...but the sensor specs don't declare it
        );
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with("imu_accel", 0.0, "m/s2"),
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&sensor), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Hold,
            "undeclared geofence channel must fail closed to HOLD"
        );
        assert!(
            !gov.safety_ok(),
            "config fail-closed reports safety_ok=false"
        );
    }

    #[test]
    fn geofence_channel_missing_from_frame_holds() {
        // Channel IS declared in specs but the live sensor frame omits it -> cannot
        // evaluate the fence -> fail closed (HOLD), non-latching.
        let mut gov = SafetyGovernor::with_channels(
            SafetyLimits {
                geofence_radius_m: Some(10.0),
                ..Default::default()
            },
            "ned_pos",
            "thrust_vec",
            vec!["thrust_vec".into()],
            vec!["ned_pos".into()],
        );
        let sensor = SensorFrame {
            seq: 1,
            channels: channels_with("other", 1.0, "m"),
            ..Default::default()
        };
        let out = gov.govern(&active_command(), Some(&sensor), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Hold,
            "geofence channel missing from the frame -> HOLD"
        );
        assert!(
            !gov.is_estopped(),
            "a missing-frame channel HOLD must not latch"
        );
    }

    // ───────── CRITICAL: predictive horizon steps obey the same speed clamp ─────────

    #[test]
    fn horizon_steps_are_speed_clamped() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            max_speed_mps: Some(1.0),
            ..Default::default()
        });
        // tick 0 within limit; the horizon carries an over-limit step (mag 5).
        let mut tick0 = crate::messages::Map::new();
        tick0.insert(
            "velocity_setpoint".into(),
            ChannelValue::vec3(0.5, 0.0, 0.0, Some("m/s")),
        );
        let mut over = crate::messages::Map::new();
        over.insert(
            "velocity_setpoint".into(),
            ChannelValue::vec3(3.0, 4.0, 0.0, Some("m/s")), // mag 5 > 1
        );
        let cmd = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: tick0,
            horizon: vec![over],
            horizon_dt_ms: Some(50.0),
            ..Default::default()
        };
        // Fresh sensor, no geofence -> ACTIVE; the horizon must come back clamped.
        let out = gov.govern(&cmd, Some(&fresh_sensor()), 1.0, Some(1.0));
        assert_eq!(out.mode, Mode::Active);
        let hv = &out.horizon[0]["velocity_setpoint"].data;
        let mag = hv.iter().map(|c| c * c).sum::<f64>().sqrt();
        assert!(
            (mag - 1.0).abs() < 1e-9,
            "horizon step must be clamped to max_speed (1.0), got {mag}"
        );
    }

    #[test]
    fn nonfinite_horizon_step_rejects_the_active_command() {
        let mut gov = SafetyGovernor::new(SafetyLimits {
            max_speed_mps: Some(2.0),
            ..Default::default()
        });
        let step = |x: f64| {
            let mut m = crate::messages::Map::new();
            m.insert(
                "velocity_setpoint".into(),
                ChannelValue::vec3(x, 0.0, 0.0, Some("m/s")),
            );
            m
        };
        let cmd = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: step(0.5),
            // good, then non-finite, then good: replay must stop AT the poisoned step.
            horizon: vec![step(1.0), step(f64::NAN), step(1.0)],
            horizon_dt_ms: Some(50.0),
            ..Default::default()
        };
        let out = gov.govern(&cmd, Some(&fresh_sensor()), 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Hold,
            "a non-finite predictive step invalidates the Active payload"
        );
        assert!(
            out.horizon.is_empty(),
            "the safe HOLD carries no replay horizon"
        );
    }

    #[test]
    fn nonfinite_or_negative_limit_fails_closed() {
        // A configured-but-nonsensical geofence/speed limit (NaN / ±Inf / negative)
        // must fail closed — `NaN > 0.0` / `-1.0 > 0.0` are false, which would
        // otherwise SKIP the geofence/speed enforcement entirely (fail-OPEN).
        for limits in [
            SafetyLimits {
                geofence_radius_m: Some(f64::NAN),
                ..Default::default()
            },
            SafetyLimits {
                geofence_radius_m: Some(f64::INFINITY),
                ..Default::default()
            },
            SafetyLimits {
                geofence_radius_m: Some(-5.0),
                ..Default::default()
            },
            SafetyLimits {
                max_speed_mps: Some(f64::NAN),
                ..Default::default()
            },
            SafetyLimits {
                max_speed_mps: Some(-1.0),
                ..Default::default()
            },
        ] {
            let mut gov = SafetyGovernor::new(limits);
            // A would-be-actuating command on the freshest possible sensor.
            let cmd = CommandFrame {
                seq: 1,
                mode: Mode::Active,
                channels: channels_with("velocity_setpoint", 99.0, "m/s"),
                ..Default::default()
            };
            let sensor = SensorFrame {
                seq: 1,
                channels: channels_with("pose_position", 1000.0, "m"),
                ..Default::default()
            };
            let out = gov.govern(&cmd, Some(&sensor), 1.0, Some(1.0));
            assert_eq!(
                out.mode,
                Mode::Hold,
                "a non-finite/negative limit must fail closed to HOLD, not disable enforcement"
            );
            assert!(
                !gov.safety_ok(),
                "a bad limit latches config fail-closed -> safety_ok()=false"
            );
        }
        // Guard the boundary: 0.0 remains the documented "disabled" value, and a
        // finite positive limit still enforces normally (regression fence).
        let mut ok = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(0.0),
            max_speed_mps: Some(5.0),
            ..Default::default()
        });
        let out = ok.govern(
            &CommandFrame {
                seq: 1,
                mode: Mode::Active,
                channels: channels_with("velocity_setpoint", 2.0, "m/s"),
                ..Default::default()
            },
            Some(&SensorFrame {
                seq: 1,
                channels: channels_with("pose_position", 3.0, "m"),
                ..Default::default()
            }),
            1.0,
            Some(1.0),
        );
        assert_eq!(
            out.mode,
            Mode::Active,
            "radius 0 disabled + within speed -> active"
        );
        assert!(ok.safety_ok());
    }

    #[test]
    fn backward_clock_step_fails_closed() {
        // A non-monotonic (rewound) clock must not read as "fresh": both the
        // sensor-staleness check and the command watchdog must HOLD on a backward step.
        let mut gov = SafetyGovernor::new(SafetyLimits {
            command_timeout_ms: 500.0,
            ..Default::default()
        });
        // last_sensor at t=2.0, now stepped BACK to t=1.0 -> (now-last) = -1.0.
        let out = gov.govern(&active_command(), Some(&fresh_sensor()), 1.0, Some(2.0));
        assert_eq!(
            out.mode,
            Mode::Hold,
            "a backward clock step must fail safe to HOLD, not actuate"
        );

        let mut wd = CommandWatchdog::new();
        wd.on_command(2.0, 500.0, 1); // command recorded at t=2.0
        assert!(
            wd.should_hold(1.0),
            "the watchdog must HOLD when the clock steps backward past the recv time"
        );
        wd.on_command(1.0, 500.0, 2);
        assert!(
            wd.should_hold(2.0),
            "a command received on the rewound clock must not restore authority, and catch-up alone is insufficient"
        );
        wd.on_command(2.0, 500.0, 2);
        assert!(
            !wd.should_hold(2.1),
            "a fresh command at the recovered high-water mark may restore liveness"
        );
    }

    #[test]
    fn nan_clock_forces_hold() {
        // safety-2: a non-finite `now_s` must be treated as stale (HOLD), not slip
        // past the `(now_s - last) >= timeout` comparison as "fresh".
        let mut gov = SafetyGovernor::new(SafetyLimits::default());
        let out = gov.govern(
            &active_command(),
            Some(&fresh_sensor()),
            f64::NAN,
            Some(1.0),
        );
        assert_eq!(out.mode, Mode::Hold, "NaN clock must fail safe to HOLD");

        let mut wd = CommandWatchdog::new();
        wd.on_command(1.0, 200.0, 1);
        assert!(wd.should_hold(f64::NAN), "watchdog HOLDs on a NaN clock");
    }

    #[test]
    fn hold_zeroes_all_command_channels() {
        // Inbound command carries two channels; negotiated command set adds a third.
        // A HOLD (here via stale sensor) must zero the UNION, not just one literal.
        let mut gov = SafetyGovernor::with_channels(
            SafetyLimits {
                command_timeout_ms: 500.0,
                ..Default::default()
            },
            "pose_position",
            "thrust_vec",
            vec!["thrust_vec".into(), "yaw_rate".into()],
            vec!["pose_position".into()],
        );
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "thrust_vec".into(),
            ChannelValue::vec3(3.0, 4.0, 0.0, Some("m/s")),
        );
        ch.insert("aux_servo".into(), ChannelValue::scalar(7.0, Some("rad")));
        let cmd = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: ch,
            ..Default::default()
        };
        // No sensor -> stale -> HOLD.
        let out = gov.govern(&cmd, None, 1.0, None);
        assert_eq!(out.mode, Mode::Hold);
        for name in ["thrust_vec", "aux_servo", "yaw_rate"] {
            let cv = out
                .channels
                .get(name)
                .unwrap_or_else(|| panic!("{name} must be zeroed in HOLD"));
            assert!(
                cv.data.iter().all(|c| *c == 0.0),
                "{name} must be all zeros"
            );
        }
    }

    #[test]
    fn total_silence_escalates_hold_to_latched_estop() {
        // Default command_timeout_ms = 500 ms -> escalation deadline = 20 * 0.5 = 10 s.
        let mut gov = SafetyGovernor::new(SafetyLimits::default());
        let cmd = active_command();
        // A brief dropout (well under the deadline) is a non-latching HOLD.
        let out = gov.govern(&cmd, None, 6.0, Some(1.0)); // 5 s silence
        assert_eq!(out.mode, Mode::Hold, "a brief dropout HOLDs (non-latching)");
        assert!(gov.safety_ok(), "a transient HOLD does not trip safety_ok");
        assert!(!gov.is_estopped());
        // Sustained total silence past the deadline latches ESTOP.
        let out = gov.govern(&cmd, None, 12.0, Some(1.0)); // 11 s silence > 10 s
        assert_eq!(out.mode, Mode::Estop, "a collapsed link must latch ESTOP");
        assert!(gov.is_estopped(), "the ESTOP must latch");
        // Latched: even fresh data now returns ESTOP until a supervisor reset.
        let out = gov.govern(&cmd, Some(&fresh_sensor()), 12.0, Some(12.0));
        assert_eq!(out.mode, Mode::Estop, "ESTOP stays latched until reset");
        gov.reset();
        let out = gov.govern(&cmd, Some(&fresh_sensor()), 12.0, Some(12.0));
        assert_eq!(
            out.mode,
            Mode::Active,
            "reset clears the latch when link is live"
        );
    }

    #[test]
    fn non_active_inbound_mode_holds() {
        // A non-Active command must never actuate, even with a fresh sensor and
        // an in-bounds setpoint (defense-in-depth with ActionBuffer's allowlist).
        let mut gov = SafetyGovernor::new(SafetyLimits::default());
        for mode in [Mode::Init, Mode::Hold] {
            let cmd = CommandFrame {
                seq: 1,
                mode: mode.clone(),
                channels: channels_with("velocity_setpoint", 1.0, "m/s"),
                ..Default::default()
            };
            let out = gov.govern(&cmd, Some(&fresh_sensor()), 1.0, Some(1.0));
            assert_eq!(out.mode, Mode::Hold, "{mode:?} must normalize to HOLD");
            let v = out.channels.get("velocity_setpoint").expect("present");
            assert!(v.data.iter().all(|c| *c == 0.0), "HOLD zeroes the setpoint");
        }
    }

    #[test]
    fn noncanonical_unknown_active_never_gains_authority() {
        let mut gov = SafetyGovernor::new(SafetyLimits::default());
        let command = CommandFrame {
            seq: 1,
            mode: Mode::Unknown("active".into()),
            ttl_ms: 200.0,
            channels: channels_with("velocity_setpoint", 1.0, "m/s"),
            ..Default::default()
        };

        let out = gov.govern(&command, Some(&fresh_sensor()), 1.0, Some(1.0));

        assert_eq!(out.mode, Mode::Hold);
        assert!(
            out.channels
                .values()
                .all(|channel| channel.data.iter().all(|value| *value == 0.0)),
            "an ambiguous in-memory mode must fail closed to zero output"
        );
    }

    #[test]
    fn inbound_estop_command_latches_and_propagates() {
        // An explicit inbound ESTOP is a fail-safe: it must come back as a zeroed
        // ESTOP (never a non-latching HOLD downgrade) and must LATCH — mirroring
        // ActionBuffer's "a fail-safe is never dropped".
        let mut gov = SafetyGovernor::new(SafetyLimits::default());
        let estop_cmd = CommandFrame {
            mode: Mode::Estop,
            channels: channels_with("velocity_setpoint", 9.0, "m/s"),
            ..Default::default()
        };
        let out = gov.govern(&estop_cmd, None, 1.0, Some(1.0));
        assert_eq!(
            out.mode,
            Mode::Estop,
            "inbound ESTOP is propagated, not downgraded"
        );
        let v = out.channels.get("velocity_setpoint").expect("present");
        assert!(
            v.data.iter().all(|c| *c == 0.0),
            "ESTOP zeroes the setpoint"
        );
        assert!(gov.is_estopped(), "inbound ESTOP must latch");
        // A subsequent perfectly-safe Active command is still ESTOP until reset.
        let active = CommandFrame {
            seq: 1,
            mode: Mode::Active,
            channels: channels_with("velocity_setpoint", 0.5, "m/s"),
            ..Default::default()
        };
        assert_eq!(
            gov.govern(&active, None, 2.0, Some(2.0)).mode,
            Mode::Estop,
            "the latch persists until a supervisor reset"
        );
        gov.reset();
        assert_eq!(
            gov.govern(&active, Some(&fresh_sensor()), 3.0, Some(3.0))
                .mode,
            Mode::Active,
            "reset restores normal governing"
        );
    }

    #[test]
    fn bad_command_timeout_latches_config_fail_closed() {
        for bad in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            let mut gov = SafetyGovernor::new(SafetyLimits {
                command_timeout_ms: bad,
                ..Default::default()
            });
            assert!(
                !gov.safety_ok(),
                "bad timeout {bad} must be visible before the first command"
            );
            let out = gov.govern(&active_command(), None, 1.0, Some(1.0));
            assert_eq!(out.mode, Mode::Hold, "bad timeout {bad} must HOLD");
            assert!(
                !gov.safety_ok(),
                "a bad command_timeout_ms ({bad}) must report safety_ok()=false, not a healthy HOLD"
            );
        }
    }

    #[test]
    fn invalid_advisory_limit_is_visible_at_construction() {
        let gov = SafetyGovernor::new(SafetyLimits {
            max_tilt_rad: Some(f64::NAN),
            ..Default::default()
        });
        assert!(
            !gov.safety_ok(),
            "an invalid plant-enforced advisory limit cannot report healthy"
        );
    }

    #[test]
    fn invalid_or_duplicate_negotiated_channels_fail_closed_at_construction() {
        let gov = SafetyGovernor::with_channels(
            SafetyLimits::default(),
            "pose",
            "velocity",
            vec!["velocity".into(), "velocity".into()],
            vec!["pose".into()],
        );
        assert!(!gov.safety_ok());

        let gov = SafetyGovernor::with_channels(
            SafetyLimits::default(),
            "pose\nspoof",
            "velocity",
            vec!["velocity".into()],
            vec!["pose".into()],
        );
        assert!(!gov.safety_ok());

        let mut gov = SafetyGovernor::with_channels(
            SafetyLimits::default(),
            "pose",
            "velocity\nspoof",
            vec!["velocity\nspoof".into()],
            vec!["pose".into()],
        );
        let output = gov.govern(&active_command(), Some(&fresh_sensor()), 1.0, Some(1.0));
        assert_eq!(output.mode, Mode::Hold);
        output
            .validate_wire()
            .expect("config-fail HOLD must still be a complete publishable frame");
    }
}
