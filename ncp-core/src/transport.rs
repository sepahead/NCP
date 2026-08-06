//! Closed-loop control runner (sync) — the layered special case where a neural
//! backend (e.g. an Engram network) is "just another controller". A `Controller`
//! turns the latest `SensorFrame` into a `CommandFrame`; a `SafetyGovernor` clamps
//! it; a `ControlTransport` admits it to a local transport slot. Slot admission is
//! not a network-delivery acknowledgement. (A Python peer mirrors this in its
//! `transport`/`loop` modules.)
//!
//! Clocks are injectable so the loop is deterministic under test.

use crate::messages::{
    AuthorityLease, ChannelValue, CommandFrame, ControlStatus, Mode, SafetyLimits, SensorFrame,
    SessionRef, StreamPosition, WireFrame, JSON_SAFE_INTEGER_MAX,
};
use crate::safety::{SafetyGovernError, SafetyGovernor, MAX_TTL_MS};
use std::sync::{Arc, Mutex};

/// A fail-closed local control-loop tick error.
///
/// The loop records no successful command admission or status for a failed tick.
/// A transport that reports an invalid admitted position has violated the trait
/// contract; its external side effects are ambiguous and cannot be undone here.
/// An already pending asynchronous command is not a delivery acknowledgement and
/// can remain in the transport.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ControlLoopTickError {
    /// The loop-local candidate allocator consumed JSON-safe position `2^53-1`.
    /// This is detected before the controller runs.
    CommandStreamExhausted,
    /// A transport-owned action-stream allocator was exhausted during slot
    /// admission. The controller and governor can already have run.
    TransportCommandStreamExhausted,
    /// The transport synchronously rejected the final governed command before
    /// admitting it to a publication slot.
    CommandPublicationRejected,
    /// The transport claimed admission with an invalid position, changed its
    /// action-stream epoch, failed to advance a new position, or claimed a
    /// replacement at anything other than the last admitted position. The loop
    /// latches this error; recovery requires a fresh loop/transport generation.
    InvalidTransportAdmission,
    /// The safety governor could not produce a bounded, semantically valid command
    /// candidate.
    Safety(SafetyGovernError),
}

impl std::fmt::Display for ControlLoopTickError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::CommandStreamExhausted => formatter.write_str(
                "control-loop candidate stream is exhausted; create a fresh declaration",
            ),
            Self::TransportCommandStreamExhausted => formatter.write_str(
                "transport command stream is exhausted; create a fresh transport declaration",
            ),
            Self::CommandPublicationRejected => {
                formatter.write_str("transport rejected the governed command before slot admission")
            }
            Self::InvalidTransportAdmission => formatter
                .write_str("transport returned an invalid or inconsistent command-slot admission"),
            Self::Safety(error) => write!(formatter, "control-loop safety failure: {error}"),
        }
    }
}

impl std::error::Error for ControlLoopTickError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::CommandStreamExhausted
            | Self::TransportCommandStreamExhausted
            | Self::CommandPublicationRejected
            | Self::InvalidTransportAdmission => None,
            Self::Safety(error) => Some(error),
        }
    }
}

impl From<SafetyGovernError> for ControlLoopTickError {
    fn from(error: SafetyGovernError) -> Self {
        Self::Safety(error)
    }
}

/// A fail-closed local control-loop construction error.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ControlLoopConfigError(pub String);

impl std::fmt::Display for ControlLoopConfigError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.0)
    }
}

impl std::error::Error for ControlLoopConfigError {}

/// Mint a fresh CSPRNG-backed canonical UUIDv4 for one logical publisher stream.
///
/// Stream epochs are equality-only identifiers, not credentials, but the wire
/// contract requires them to be unpredictable and fresh across publisher
/// restarts. Entropy failure therefore aborts construction instead of falling
/// back to time/PID/counters that can collide after snapshots or process reuse.
pub fn mint_stream_epoch() -> Result<String, ControlLoopConfigError> {
    let mut bytes = [0_u8; 16];
    getrandom::fill(&mut bytes).map_err(|error| {
        ControlLoopConfigError(format!("failed to obtain stream-epoch entropy: {error}"))
    })?;
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    Ok(format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}",
        bytes[0],
        bytes[1],
        bytes[2],
        bytes[3],
        bytes[4],
        bytes[5],
        bytes[6],
        bytes[7],
        bytes[8],
        bytes[9],
        bytes[10],
        bytes[11],
        bytes[12],
        bytes[13],
        bytes[14],
        bytes[15],
    ))
}

/// Result of handing one governed command to a transport-owned publication slot.
///
/// An admitted outcome carries the exact stream position assigned to the stored
/// command. A replacement reuses the not-yet-published position and therefore
/// must not advance the loop's candidate counter. `Accepted` is bounded local
/// slot admission, not a delivery acknowledgement; an asynchronous put can still
/// be delivery-ambiguous and must consume its transport position. Within one
/// transport binding, `Accepted` must retain one canonical epoch and strictly
/// advance its position; `ReplacedPending` must equal the most recently admitted
/// position. A malformed or inconsistent admitted outcome is a transport contract
/// violation, never operation success. A panic is also an ambiguous admission:
/// the loop contains the unwind and permanently retires that transport binding.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum CommandSendOutcome {
    Accepted(StreamPosition),
    ReplacedPending(StreamPosition),
    StreamExhausted,
    Rejected,
}

/// Moves sensor/command frames between a controller and a plant.
pub trait ControlTransport: Send + Sync {
    fn send_command(&self, command: &CommandFrame) -> CommandSendOutcome;
    fn latest_sensor(&self) -> Option<SensorFrame>;
    fn send_status(&self, _status: &ControlStatus) {}
}

/// Bidirectional in-process channel (tests / co-process SITL). The plant calls
/// `push_sensor` / `last_command`; the controller uses `ControlTransport`.
#[derive(Clone, Default)]
pub struct InProcessTransport {
    inner: Arc<Mutex<InProcessInner>>,
}

#[derive(Default)]
struct InProcessInner {
    latest_sensor: Option<SensorFrame>,
    last_command: Option<CommandFrame>,
    commands: Vec<CommandFrame>,
    statuses: Vec<ControlStatus>,
}

impl InProcessTransport {
    pub fn new() -> Self {
        Self::default()
    }
    pub fn push_sensor(&self, frame: SensorFrame) {
        self.inner
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .latest_sensor = Some(frame);
    }
    pub fn last_command(&self) -> Option<CommandFrame> {
        self.inner
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .last_command
            .clone()
    }
    pub fn commands(&self) -> Vec<CommandFrame> {
        self.inner
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .commands
            .clone()
    }
    pub fn statuses(&self) -> Vec<ControlStatus> {
        self.inner
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .statuses
            .clone()
    }
}

impl ControlTransport for InProcessTransport {
    fn send_command(&self, command: &CommandFrame) -> CommandSendOutcome {
        let mut g = self.inner.lock().unwrap_or_else(|e| e.into_inner());
        g.last_command = Some(command.clone());
        g.commands.push(command.clone());
        CommandSendOutcome::Accepted(command.stream.clone())
    }
    fn latest_sensor(&self) -> Option<SensorFrame> {
        self.inner
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .latest_sensor
            .clone()
    }
    fn send_status(&self, status: &ControlStatus) {
        self.inner
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .statuses
            .push(status.clone());
    }
}

/// Turns the latest sensor into a command each tick.
pub trait Controller: Send {
    fn reset(&mut self) {}
    fn step(&mut self, sensor: Option<&SensorFrame>, dt_ms: f64) -> CommandFrame;
}

/// Deterministic PD reflex (`velocity_setpoint = -kp*(pos-target) - kd*vel`).
/// The fixed-wiring baseline a trained SNN controller must beat.
pub struct ReflexController {
    pub target: [f64; 3],
    pub kp: f64,
    pub kd: f64,
    pub max_speed: f64,
    pub position_channel: String,
    pub velocity_channel: String,
}

impl Default for ReflexController {
    fn default() -> Self {
        Self {
            target: [0.0, 0.0, 0.0],
            kp: 1.0,
            kd: 0.3,
            max_speed: 1.5,
            position_channel: "pose_position".into(),
            velocity_channel: "pose_velocity".into(),
        }
    }
}

impl Controller for ReflexController {
    fn step(&mut self, sensor: Option<&SensorFrame>, _dt_ms: f64) -> CommandFrame {
        let hold = |sensor: Option<&SensorFrame>| {
            let mut ch = crate::messages::Map::new();
            ch.insert(
                "velocity_setpoint".into(),
                ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
            );
            let mut command = CommandFrame {
                mode: Mode::Hold,
                channels: ch,
                ..Default::default()
            };
            if let Some(sensor) = sensor {
                command.source = Some(sensor.stream.clone());
                command.source_t = sensor.t;
                command.session = sensor.session.clone();
                command.session_id.clone_from(&sensor.session_id);
                command.frame_id.clone_from(&sensor.frame_id);
            }
            command
        };
        let Some(sensor) = sensor else {
            return hold(None);
        };
        if sensor.validate_wire().is_err()
            || !self.kp.is_finite()
            || !self.kd.is_finite()
            || !self.max_speed.is_finite()
            || self.max_speed < 0.0
            || self.target.iter().any(|value| !value.is_finite())
            || self.position_channel.is_empty()
            || self.velocity_channel.is_empty()
        {
            return hold(Some(sensor));
        }
        let get3 = |name: &str, unit: &str| -> Option<[f64; 3]> {
            let channel = sensor.channels.get(name)?;
            if channel.unit.as_deref() != Some(unit)
                || channel.data.len() != 3
                || channel.data.iter().any(|value| !value.is_finite())
            {
                return None;
            }
            Some([channel.data[0], channel.data[1], channel.data[2]])
        };
        let Some(p) = get3(&self.position_channel, "m") else {
            return hold(Some(sensor));
        };
        let Some(v) = get3(&self.velocity_channel, "m/s") else {
            return hold(Some(sensor));
        };
        let mut cmd = [0.0; 3];
        for i in 0..3 {
            let u = -self.kp * (p[i] - self.target[i]) - self.kd * v[i];
            if !u.is_finite() {
                return hold(Some(sensor));
            }
            cmd[i] = u;
        }
        let magnitude = cmd.iter().map(|value| value * value).sum::<f64>().sqrt();
        if !magnitude.is_finite() {
            return hold(Some(sensor));
        }
        if magnitude > self.max_speed && magnitude > 0.0 {
            let scale = self.max_speed / magnitude;
            for value in &mut cmd {
                *value *= scale;
            }
        }
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "velocity_setpoint".into(),
            ChannelValue {
                data: cmd.to_vec(),
                unit: Some("m/s".into()),
            },
        );
        CommandFrame {
            source: Some(sensor.stream.clone()),
            source_t: sensor.t,
            session: sensor.session.clone(),
            session_id: sensor.session_id.clone(),
            frame_id: sensor.frame_id.clone(),
            mode: Mode::Active,
            channels: ch,
            ..Default::default()
        }
    }
}

/// Fixed-rate scheduler tying transport + controller + safety together. `now_fn`
/// is injectable so the loop is deterministic under test.
pub struct NeuroControlLoop<T: ControlTransport, C: Controller> {
    pub transport: T,
    pub controller: C,
    pub rate_hz: f64,
    gov: SafetyGovernor,
    /// Immutable live-session binding. A new server-issued generation requires
    /// a new loop instance, which also mints new publisher epochs and resets all
    /// controller/link/governor state. Payload data can never rebind the loop.
    session_id: String,
    session: SessionRef,
    /// Current authenticated commander lease supplied by the host authority
    /// service. The loop never fabricates or acquires authority from payload data.
    authority: Option<AuthorityLease>,
    /// A panic can leave arbitrary controller state partially mutated. Once one
    /// occurs, this loop never invokes or trusts that controller again; recovery
    /// requires a fresh loop/controller generation.
    controller_failed: bool,
    /// A malformed admitted position or panic during admission leaves the
    /// transport's action-stream state ambiguous. No local reset can prove whether
    /// bytes are pending or published, so this loop retires the transport
    /// permanently after the first violation.
    transport_failed: bool,
    now_fn: Box<dyn Fn() -> f64 + Send>,
    command_stream_epoch: String,
    command_seq: i64,
    /// Last transport-owned action position accepted by this loop. It binds all
    /// later admission receipts to one epoch, strict advancement for new slots,
    /// and exact position reuse for pre-publication replacement.
    last_admitted_command_position: Option<StreamPosition>,
    status_stream_epoch: String,
    /// Last consumed position in the loop-owned status stream. Zero means no
    /// status has been published yet and is never emitted on the wire.
    status_seq: i64,
    /// Link-health monitor over the inbound sensor `seq` stream. A sustained loss
    /// burst feeds the HOLD-to-ESTOP escalation without identifying its cause.
    link: crate::resilience::LinkMonitor,
    last_sensor_t: Option<f64>,
    /// Last accepted sensor's `(t, seq)`, to detect a frozen/cached stream. The
    /// watchdog clock (`last_sensor_t`) only advances when the sensor STRICTLY
    /// advances (FIX 4) — a repeated/stale frame must still trip the stale-sensor
    /// HOLD even though a frame "arrived".
    last_sensor_ts: Option<(f64, i64)>,
    /// The last ACCEPTED sensor frame — the only one the controller/governor/source
    /// correlation consumes. A frame that fails seq discipline (unstamped, or a replayed
    /// regression on a live stream) must not steer the controller or leak its seq
    /// into commands; it goes stale naturally via `last_sensor_t`.
    accepted_sensor: Option<SensorFrame>,
    /// Highest valid local tick-clock sample. A backward step between ticks is
    /// a clock fault even if the clock remains monotonic within the current tick;
    /// retain the high-water mark so the loop HOLDs until time catches up.
    last_tick_now: Option<f64>,
    /// Declaration-bound sensor stream epoch. A foreign epoch never replaces it in
    /// place, including after expiry; a restarted publisher requires a fresh typed
    /// declaration and loop instance.
    active_sensor_epoch: Option<String>,
}

impl<T: ControlTransport, C: Controller> NeuroControlLoop<T, C> {
    pub fn new(
        transport: T,
        controller: C,
        rate_hz: f64,
        safety: SafetyLimits,
        session_id: impl Into<String>,
        session: SessionRef,
    ) -> Result<Self, ControlLoopConfigError> {
        let session_id = session_id.into();
        if !crate::valid_id_segment(&session_id) {
            return Err(ControlLoopConfigError(
                "control loop session_id must be one safe key segment".into(),
            ));
        }
        if !crate::is_canonical_uuid_v4(&session.generation) {
            return Err(ControlLoopConfigError(
                "control loop session generation must be a canonical lowercase UUIDv4".into(),
            ));
        }
        let command_stream_epoch = mint_stream_epoch()?;
        let mut status_stream_epoch = mint_stream_epoch()?;
        while status_stream_epoch == command_stream_epoch {
            status_stream_epoch = mint_stream_epoch()?;
        }
        Ok(Self {
            transport,
            controller,
            rate_hz,
            gov: SafetyGovernor::new(safety),
            session_id,
            session,
            authority: None,
            controller_failed: false,
            transport_failed: false,
            now_fn: Box::new(monotonic_secs),
            command_stream_epoch,
            command_seq: 0,
            last_admitted_command_position: None,
            status_stream_epoch,
            status_seq: 0,
            link: crate::resilience::LinkMonitor::with_defaults("ncp-loop"),
            last_sensor_t: None,
            last_sensor_ts: None,
            active_sensor_epoch: None,
            accepted_sensor: None,
            last_tick_now: None,
        })
    }

    /// Override the clock (tests).
    pub fn with_clock(mut self, now_fn: Box<dyn Fn() -> f64 + Send>) -> Self {
        self.now_fn = now_fn;
        self
    }

    /// Bind the active lease obtained from the authenticated host authority
    /// service. This is explicit because controller output cannot self-authorize.
    pub fn with_authority(mut self, authority: AuthorityLease) -> Self {
        self.authority = Some(authority);
        self
    }

    /// Replace or clear the host-provided commander lease (renewal, transfer, or
    /// expiry). A missing, malformed, or wrong-session lease forces Active output
    /// to HOLD before it reaches the transport.
    pub fn set_authority(&mut self, authority: Option<AuthorityLease>) {
        self.authority = authority;
    }

    fn dt_ms(&self) -> f64 {
        if self.rate_is_safe() {
            1000.0 / self.rate_hz
        } else {
            0.0
        }
    }

    fn rate_is_safe(&self) -> bool {
        if !self.rate_hz.is_finite() || self.rate_hz <= 0.0 {
            return false;
        }
        let dt_ms = 1000.0 / self.rate_hz;
        dt_ms.is_finite() && dt_ms > 0.0 && dt_ms * 2.0 <= MAX_TTL_MS
    }

    /// One control step: read sensor → controller → safety → transport-slot
    /// admission.
    ///
    /// # Errors
    ///
    /// Local candidate exhaustion is detected before the controller runs.
    /// Transport-owned exhaustion, synchronous rejection, a panicking admission,
    /// or an invalid admission receipt is detected later, after governance but
    /// before status emission. A panic or invalid receipt permanently retires this
    /// loop/transport binding. For a tick with an accepted sensor, `Ok` means the
    /// returned command and its exact
    /// position were admitted to a bounded local transport slot; it is not a
    /// network-delivery acknowledgement. Before the first accepted sensor, `Ok` is
    /// a local governed fallback and status update only; no command is offered to
    /// the transport.
    pub fn tick(&mut self) -> Result<CommandFrame, ControlLoopTickError> {
        if self.transport_failed {
            return Err(ControlLoopTickError::InvalidTransportAdmission);
        }
        let now = (self.now_fn)();
        let tick_clock_ok =
            now.is_finite() && self.last_tick_now.is_none_or(|previous| now >= previous);
        if tick_clock_ok {
            // Clock admission is independent of command/status success. Retain
            // every trustworthy sample before any later `?` or transport error so
            // an erroring tick cannot let a subsequent rewind re-anchor liveness.
            self.last_tick_now = Some(now);
        }
        // Wire 1.0: an unstamped sensor (`seq < 1`) is not a wire-legal frame —
        // treat it as ABSENT entirely (no freshness refresh, no link feed, no
        // correlate, not even geofence input): an invalid frame is no frame.
        let candidate = self.transport.latest_sensor().filter(|sensor| {
            tick_clock_ok
                && sensor.validate_wire().is_ok()
                && sensor.session_id == self.session_id
                && sensor.session == self.session
        });
        // The sensor is fresh only when its declaration-bound epoch is unchanged,
        // `seq` strictly advances, and publisher-local `t` does not regress. Arrival
        // alone never refreshes the watchdog, including after expiry. A lower seq or
        // foreign epoch cannot re-anchor this live loop; publisher restart requires
        // a fresh loop/route declaration with new controller and LinkMonitor state.
        if let Some(s) = candidate {
            let same_epoch = self
                .active_sensor_epoch
                .as_deref()
                .is_none_or(|epoch| epoch == s.stream.epoch);
            let advanced = same_epoch
                && self
                    .last_sensor_ts
                    .is_none_or(|(previous_t, previous_seq)| {
                        s.stream.seq > previous_seq && s.t >= previous_t
                    });
            if advanced {
                if self.active_sensor_epoch.is_none() {
                    self.active_sensor_epoch = Some(s.stream.epoch.clone());
                }
                self.last_sensor_t = Some(now);
                self.last_sensor_ts = Some((s.t, s.stream.seq));
                // Feed the link monitor only on a genuinely-new sensor (a frozen
                // re-delivery is a duplicate no-op in the monitor regardless).
                self.link.on_seq(&s.stream.epoch, s.stream.seq);
                self.accepted_sensor = Some(s);
            }
        }
        let rate_is_safe = self.rate_is_safe();
        let dt_ms = self.dt_ms();
        let timeout_s = self.gov.limits.command_timeout_ms.min(MAX_TTL_MS) / 1000.0;
        let sensor_is_fresh = tick_clock_ok
            && timeout_s.is_finite()
            && timeout_s > 0.0
            && self.last_sensor_t.is_some_and(|last| {
                let age = now - last;
                age.is_finite() && age >= 0.0 && age < timeout_s
            });
        let sensor = if sensor_is_fresh {
            self.accepted_sensor.as_ref()
        } else {
            None
        };
        let command_seq = self
            .command_seq
            .checked_add(1)
            .filter(|seq| *seq <= JSON_SAFE_INTEGER_MAX)
            .ok_or(ControlLoopTickError::CommandStreamExhausted)?;
        let mut cmd = if rate_is_safe && sensor.is_some() && !self.controller_failed {
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                self.controller.step(sensor, dt_ms)
            })) {
                Ok(command) => command,
                Err(_) => {
                    // Unwinding can leave the controller partially mutated even
                    // when the panic itself is caught. Retire it permanently;
                    // `AssertUnwindSafe` is containment, not state validation.
                    self.controller_failed = true;
                    CommandFrame::default()
                }
            }
        } else {
            CommandFrame::default()
        };
        let controller_fault = self.controller_failed;
        // The command owns a distinct stream and local creation time. The driving
        // sensor travels only in `source`/`source_t`; equating publisher streams
        // would turn intentional sensor decimation into command loss/replay state.
        // A candidate seq is committed only after transport-slot acceptance, so a
        // synchronous rejection does not advance this loop-local counter.
        cmd.stream = StreamPosition {
            epoch: self.command_stream_epoch.clone(),
            seq: command_seq,
        };
        cmd.session = self.session.clone();
        cmd.session_id.clone_from(&self.session_id);
        cmd.t = if now.is_finite() { now } else { 0.0 };
        if let Some(s) = self.accepted_sensor.as_ref() {
            cmd.source = Some(s.stream.clone());
            cmd.source_t = s.t;
            cmd.frame_id.clone_from(&s.frame_id);
        } else {
            cmd.source = None;
            cmd.source_t = 0.0;
        }
        if cmd.mode == Mode::Active {
            cmd.authority = self
                .authority
                .as_ref()
                .filter(|lease| {
                    lease.session_epoch == cmd.session.generation
                        && crate::authority::validate_lease_shape(lease).is_ok()
                })
                .cloned();
            if cmd.authority.is_none() {
                cmd.mode = Mode::Hold;
            }
        }
        // Couple the emitted deadline to the loop period BEFORE the governor
        // projects the geofence trajectory. Extending TTL after safety would
        // authorize replay beyond the interval that was checked. Never repair a
        // non-finite/non-positive controller TTL into an actuating command.
        if rate_is_safe && cmd.ttl_ms.is_finite() && cmd.ttl_ms > 0.0 {
            cmd.ttl_ms = cmd.ttl_ms.max(dt_ms * 2.0).min(MAX_TTL_MS);
        }
        // A controller-produced Active frame must satisfy the entire typed wire
        // gate before safety processing. Invalid TTL/channel/horizon data becomes
        // HOLD; it is never repaired into an actuating frame.
        if cmd.mode == Mode::Active && cmd.validate_wire().is_err() {
            cmd.mode = Mode::Hold;
        }
        // Escalate to a latched ESTOP if the link monitor reports a sustained loss
        // burst. An installed body executor must map ESTOP through its plant
        // profile; the burst does not prove jamming or define a universal physical
        // action. Checked every tick so the latch persists once tripped.
        self.gov.note_link(self.link.is_burst());
        let mut cmd = self.gov.govern(&cmd, sensor, now, self.last_sensor_t)?;
        // loop_latency_ms is a real health field: emit the measured tick cost (not a
        // constant 0.0) and flag an overrun past the loop period in `note`. Measure
        // before publishing: if the clock failed during computation, force this
        // very command to HOLD rather than merely reporting the fault afterward.
        let end = (self.now_fn)();
        let measured_latency_ms = (end - now) * 1000.0;
        let clock_ok =
            tick_clock_ok && end.is_finite() && end >= now && measured_latency_ms.is_finite();
        if clock_ok {
            // Retain the highest trustworthy intra-tick sample before transport
            // admission, whose synchronous error paths return early.
            self.last_tick_now = Some(end);
        }
        if !clock_ok && cmd.mode != Mode::Estop {
            cmd.mode = Mode::Hold;
            cmd = self.gov.govern(&cmd, sensor, now, self.last_sensor_t)?;
        }
        // Before the first accepted sensor there is no truthful source binding.
        // Offer only a valid governed frame; the plant retains its own watchdog.
        if self.accepted_sensor.is_some() {
            if cmd.validate_wire().is_err() {
                return Err(ControlLoopTickError::CommandPublicationRejected);
            }
            let outcome = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                self.transport.send_command(&cmd)
            })) {
                Ok(outcome) => outcome,
                Err(_) => {
                    // A transport can mutate or admit its slot before unwinding.
                    // Containment cannot determine whether that happened, so the
                    // action-stream binding is ambiguous and must never be reused.
                    self.transport_failed = true;
                    return Err(ControlLoopTickError::InvalidTransportAdmission);
                }
            };
            match outcome {
                CommandSendOutcome::Accepted(position) => {
                    let advances_one_stream = self
                        .last_admitted_command_position
                        .as_ref()
                        .is_none_or(|previous| {
                            position.epoch == previous.epoch && position.seq > previous.seq
                        });
                    cmd.stream = position.clone();
                    if !advances_one_stream || cmd.validate_wire().is_err() {
                        self.transport_failed = true;
                        return Err(ControlLoopTickError::InvalidTransportAdmission);
                    }
                    self.last_admitted_command_position = Some(position);
                    self.command_seq = command_seq;
                }
                CommandSendOutcome::ReplacedPending(position) => {
                    let reuses_pending = self
                        .last_admitted_command_position
                        .as_ref()
                        .is_some_and(|previous| previous == &position);
                    cmd.stream = position;
                    if !reuses_pending || cmd.validate_wire().is_err() {
                        self.transport_failed = true;
                        return Err(ControlLoopTickError::InvalidTransportAdmission);
                    }
                }
                CommandSendOutcome::StreamExhausted => {
                    return Err(ControlLoopTickError::TransportCommandStreamExhausted);
                }
                CommandSendOutcome::Rejected => {
                    return Err(ControlLoopTickError::CommandPublicationRejected);
                }
            }
        }
        let loop_latency_ms = if clock_ok { measured_latency_ms } else { 0.0 };
        let note = if !rate_is_safe {
            Some(format!(
                "invalid control rate: {:?} Hz cannot meet the finite watchdog bound",
                self.rate_hz
            ))
        } else if controller_fault {
            Some("controller failure latched; fresh loop/controller required".into())
        } else if !clock_ok {
            Some("control-loop clock anomaly; command forced safe by governor".into())
        } else if !sensor_is_fresh {
            Some("sensor unavailable or stale; command forced safe by governor".into())
        } else if loop_latency_ms > dt_ms {
            Some(format!("overrun: {loop_latency_ms:.1}ms > {dt_ms:.1}ms"))
        } else {
            None
        };
        // A status position is consumed before the publication attempt. If the
        // transport drops it, the resulting gap is observable; the same position
        // is never reused. At 2^53-1 exhaustion this publisher becomes silent
        // until a fresh loop declaration mints a new stream epoch.
        if let Some(next_status_seq) = self
            .status_seq
            .checked_add(1)
            .filter(|seq| *seq <= JSON_SAFE_INTEGER_MAX)
        {
            self.status_seq = next_status_seq;
            self.transport.send_status(&ControlStatus {
                stream: StreamPosition {
                    epoch: self.status_stream_epoch.clone(),
                    seq: next_status_seq,
                },
                session: self.session.clone(),
                session_id: self.session_id.clone(),
                t: if now.is_finite() { now } else { 0.0 },
                mode: cmd.mode.clone(),
                loop_latency_ms,
                safety_ok: self.gov.safety_ok() && rate_is_safe && clock_ok && !controller_fault,
                note,
                ..Default::default()
            });
        }
        Ok(cmd)
    }
}

fn monotonic_secs() -> f64 {
    use std::time::Instant;
    thread_local! { static START: Instant = Instant::now(); }
    START.with(|s| s.elapsed().as_secs_f64())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::messages::test_ids::{session, stream, SID};
    use std::collections::VecDeque;
    use std::sync::atomic::{AtomicUsize, Ordering};

    fn bound_loop<T: ControlTransport, C: Controller>(
        transport: T,
        controller: C,
        rate_hz: f64,
        safety: SafetyLimits,
    ) -> NeuroControlLoop<T, C> {
        NeuroControlLoop::new(transport, controller, rate_hz, safety, SID, session())
            .expect("test session binding is canonical")
    }

    fn must_tick<T: ControlTransport, C: Controller>(
        control_loop: &mut NeuroControlLoop<T, C>,
    ) -> CommandFrame {
        control_loop
            .tick()
            .expect("test command identity remains attributable")
    }

    fn velocity_command(x: f64, ttl_ms: f64) -> CommandFrame {
        let mut channels = crate::messages::Map::new();
        channels.insert(
            "velocity_setpoint".into(),
            ChannelValue::vec3(x, 0.0, 0.0, Some("m/s")),
        );
        CommandFrame {
            mode: Mode::Active,
            ttl_ms,
            channels,
            ..Default::default()
        }
    }

    struct TrackingController {
        steps: Arc<AtomicUsize>,
        resets: Arc<AtomicUsize>,
        velocity: f64,
        ttl_ms: f64,
    }

    impl Controller for TrackingController {
        fn reset(&mut self) {
            self.resets.fetch_add(1, Ordering::SeqCst);
        }

        fn step(&mut self, _sensor: Option<&SensorFrame>, _dt_ms: f64) -> CommandFrame {
            self.steps.fetch_add(1, Ordering::SeqCst);
            velocity_command(self.velocity, self.ttl_ms)
        }
    }

    struct MutateThenPanicController {
        steps: Arc<AtomicUsize>,
        mutated: bool,
    }

    impl Controller for MutateThenPanicController {
        fn step(&mut self, _sensor: Option<&SensorFrame>, _dt_ms: f64) -> CommandFrame {
            self.steps.fetch_add(1, Ordering::SeqCst);
            if !self.mutated {
                self.mutated = true;
                panic!("controller fault after mutation")
            }
            velocity_command(1.0, 200.0)
        }
    }

    struct PreStampedController {
        steps: Arc<AtomicUsize>,
    }

    impl Controller for PreStampedController {
        fn step(&mut self, _sensor: Option<&SensorFrame>, _dt_ms: f64) -> CommandFrame {
            self.steps.fetch_add(1, Ordering::SeqCst);
            CommandFrame {
                stream: stream(7),
                session: session(),
                session_id: SID.into(),
                mode: Mode::Hold,
                ..Default::default()
            }
        }
    }

    #[derive(Clone)]
    struct ScriptedTransport {
        sensor: SensorFrame,
        outcomes: Arc<Mutex<VecDeque<CommandSendOutcome>>>,
        commands: Arc<Mutex<Vec<CommandFrame>>>,
        statuses: Arc<Mutex<Vec<ControlStatus>>>,
    }

    impl ScriptedTransport {
        fn new(sensor: SensorFrame, outcomes: Vec<CommandSendOutcome>) -> Self {
            Self {
                sensor,
                outcomes: Arc::new(Mutex::new(outcomes.into())),
                commands: Arc::new(Mutex::new(Vec::new())),
                statuses: Arc::new(Mutex::new(Vec::new())),
            }
        }
    }

    impl ControlTransport for ScriptedTransport {
        fn send_command(&self, command: &CommandFrame) -> CommandSendOutcome {
            self.commands
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .push(command.clone());
            self.outcomes
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .pop_front()
                .expect("test transport has a scripted send outcome")
        }

        fn latest_sensor(&self) -> Option<SensorFrame> {
            Some(self.sensor.clone())
        }

        fn send_status(&self, status: &ControlStatus) {
            self.statuses
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .push(status.clone());
        }
    }

    #[derive(Clone)]
    struct PanicAfterAdmissionTransport {
        sensor: SensorFrame,
        sensor_reads: Arc<AtomicUsize>,
        send_attempts: Arc<AtomicUsize>,
        admitted_commands: Arc<Mutex<Vec<CommandFrame>>>,
        status_attempts: Arc<AtomicUsize>,
    }

    impl PanicAfterAdmissionTransport {
        fn new(sensor: SensorFrame) -> Self {
            Self {
                sensor,
                sensor_reads: Arc::new(AtomicUsize::new(0)),
                send_attempts: Arc::new(AtomicUsize::new(0)),
                admitted_commands: Arc::new(Mutex::new(Vec::new())),
                status_attempts: Arc::new(AtomicUsize::new(0)),
            }
        }
    }

    impl ControlTransport for PanicAfterAdmissionTransport {
        fn send_command(&self, command: &CommandFrame) -> CommandSendOutcome {
            self.send_attempts.fetch_add(1, Ordering::SeqCst);
            self.admitted_commands
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .push(command.clone());
            panic!("transport fault after slot mutation")
        }

        fn latest_sensor(&self) -> Option<SensorFrame> {
            self.sensor_reads.fetch_add(1, Ordering::SeqCst);
            Some(self.sensor.clone())
        }

        fn send_status(&self, _status: &ControlStatus) {
            self.status_attempts.fetch_add(1, Ordering::SeqCst);
        }
    }

    fn sensor_with_motion(t: f64, seq: i64, position_x: f64) -> SensorFrame {
        let mut channels = crate::messages::Map::new();
        channels.insert(
            "pose_position".into(),
            ChannelValue::vec3(position_x, 0.0, 0.0, Some("m")),
        );
        channels.insert(
            "pose_velocity".into(),
            ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
        );
        SensorFrame {
            t,
            stream: stream(seq),
            session: session(),
            session_id: SID.into(),
            channels,
            ..Default::default()
        }
    }

    fn test_authority() -> AuthorityLease {
        AuthorityLease {
            session_epoch: session().generation,
            term: 1,
            lease_id: "20000000-0000-4000-8000-000000000001".into(),
            issuer_principal_id: "controller-principal-1".into(),
            holder_principal_id: "controller-principal-1".into(),
            holder_entity_id: "controller-1".into(),
            issued_at_utc_ms: 1_700_000_000_000,
            expires_at_utc_ms: 1_700_000_060_000,
        }
    }

    #[test]
    fn reflex_loop_holds_without_sensor_then_drives() {
        let transport = InProcessTransport::new();
        let controller = ReflexController::default();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            controller,
            20.0,
            SafetyLimits {
                max_speed_mps: Some(1.5),
                command_timeout_ms: 500.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));

        // No sensor yet -> HOLD.
        let cmd = must_tick(&mut loop_);
        assert_eq!(cmd.mode, Mode::Hold);
        assert!(
            transport.commands().is_empty(),
            "without a stamped sensor the loop must not invent an action seq"
        );

        // Provide a sensor with a position error -> ACTIVE drive back toward origin.
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "pose_position".into(),
            ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
        );
        ch.insert(
            "pose_velocity".into(),
            ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
        );
        transport.push_sensor(SensorFrame {
            stream: stream(1),

            session: session(),
            session_id: SID.into(),
            channels: ch,
            ..Default::default()
        });
        *clock.lock().unwrap() = 0.05;
        let cmd = must_tick(&mut loop_);
        assert_eq!(cmd.mode, Mode::Active);
        assert_eq!(
            cmd.stream.seq, 1,
            "first published command starts its own stream"
        );
        assert_eq!(cmd.source.as_ref().map(|source| source.seq), Some(1));
        let v = &cmd.channels["velocity_setpoint"].data;
        assert!(v[0] < 0.0, "should push back toward origin, got {v:?}");
    }

    #[test]
    fn control_loop_never_self_authorizes_active_output() {
        let transport = InProcessTransport::new();
        transport.push_sensor(sensor_with_motion(0.0, 1, 1.0));
        let mut loop_ = bound_loop(
            transport,
            ReflexController::default(),
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 0.0));

        let command = must_tick(&mut loop_);
        assert_eq!(command.mode, Mode::Hold);
        assert!(command.authority.is_none());
    }

    #[test]
    fn unstamped_sensor_is_treated_as_absent() {
        // Wire 1.0: a seq<1 sensor is not wire-legal — the loop must treat it as
        // NO sensor (stale HOLD), never actuate from it or cite it as a source.
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                max_speed_mps: Some(1.5),
                command_timeout_ms: 500.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "pose_position".into(),
            ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
        );
        transport.push_sensor(SensorFrame {
            stream: stream(0), // unstamped
            session: session(),
            session_id: SID.into(),
            channels: ch,
            ..Default::default()
        });
        let cmd = must_tick(&mut loop_);
        assert_eq!(cmd.mode, Mode::Hold, "an unstamped sensor must not drive");
    }

    #[test]
    fn frozen_sensor_trips_stale_hold() {
        // FIX 4: a sensor that keeps arriving with the SAME (t, seq) is a frozen
        // stream; the watchdog clock must not advance, so once the timeout elapses
        // the loop HOLDs even though frames are "arriving" every tick.
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                max_speed_mps: Some(1.5),
                command_timeout_ms: 200.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));

        // One frozen frame (t=0, seq=1) that we never update.
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "pose_position".into(),
            ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
        );
        ch.insert(
            "pose_velocity".into(),
            ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
        );
        transport.push_sensor(SensorFrame {
            t: 0.0,
            stream: stream(1),

            session: session(),
            session_id: SID.into(),
            channels: ch,
            ..Default::default()
        });

        // First tick at t=0 accepts it -> ACTIVE.
        let cmd = must_tick(&mut loop_);
        assert_eq!(cmd.mode, Mode::Active, "first fresh frame drives");

        // Advance wall clock well past the 200 ms timeout WITHOUT updating the
        // sensor (same seq re-delivered). The frozen stream must go stale.
        *clock.lock().unwrap() = 0.5;
        let cmd = must_tick(&mut loop_);
        assert_eq!(
            cmd.mode,
            Mode::Hold,
            "a frozen sensor must trip the stale-sensor HOLD"
        );

        // …and it must NEVER go Active again: an equal-seq re-delivery never
        // re-anchors, so a wedged stream cannot duty-cycle Active/HOLD across
        // expiry windows.
        *clock.lock().unwrap() = 1.0;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "no oscillation on a frozen stream"
        );
        // Past the total-silence deadline (20 × 200 ms = 4 s), the designed
        // escalation latches ESTOP. The sustained freeze demonstrates missing
        // perception freshness, not its network cause; the latch must not revive.
        *clock.lock().unwrap() = 5.0;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Estop,
            "sustained freeze escalates to ESTOP"
        );
        *clock.lock().unwrap() = 6.0;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Estop,
            "…and the ESTOP stays latched"
        );
    }

    #[test]
    fn restarted_sensor_stream_requires_a_fresh_loop_declaration() {
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                max_speed_mps: Some(1.5),
                command_timeout_ms: 200.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));
        let frame = |t: f64, seq: i64| {
            let mut m = crate::messages::Map::new();
            m.insert(
                "pose_position".into(),
                ChannelValue::vec3(0.5, 0.0, 0.0, Some("m")),
            );
            m.insert(
                "pose_velocity".into(),
                ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
            );
            SensorFrame {
                t,
                stream: stream(seq),
                session: session(),
                session_id: SID.into(),
                channels: m,
                ..Default::default()
            }
        };
        // Live stream at a high seq.
        transport.push_sensor(frame(0.0, 500));
        assert_eq!(must_tick(&mut loop_).mode, Mode::Active);
        // Restart frame arrives BEFORE expiry: rejected while the old anchor is
        // live — it must neither steer the controller nor replace correlation.
        *clock.lock().unwrap() = 0.1;
        transport.push_sensor(frame(0.1, 1));
        let cmd = must_tick(&mut loop_);
        assert_eq!(cmd.mode, Mode::Active, "old anchor still fresh");
        assert_eq!(
            cmd.source.as_ref().map(|source| source.seq),
            Some(500),
            "a regressed frame on a live stream must not steer or become the source"
        );
        // Expiry does not reopen the declaration's replay window.
        *clock.lock().unwrap() = 0.5; // past the 200 ms timeout
        let cmd = must_tick(&mut loop_);
        assert_eq!(cmd.mode, Mode::Hold, "lower sequence remains rejected");
        assert_eq!(cmd.source.as_ref().map(|source| source.seq), Some(500));
        *clock.lock().unwrap() = 0.8;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "rejected restart frame remains unusable"
        );
        *clock.lock().unwrap() = 2.0;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "equal-seq frame never re-anchors"
        );
        // Only a position that advances the already-declared epoch can resume this
        // loop. A real publisher restart constructs a fresh transport/loop.
        *clock.lock().unwrap() = 2.1;
        transport.push_sensor(frame(2.1, 501));
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Active,
            "the existing declared stream may advance after a pause"
        );
    }

    #[test]
    fn foreign_sensor_epoch_cannot_hijack_a_live_stream() {
        // A foreign epoch never replaces this declaration's bound epoch in-place.
        use crate::messages::StreamPosition;
        let ep_a = "aaaaaaaa-0000-4000-8000-000000000001";
        let ep_b = "bbbbbbbb-0000-4000-8000-000000000002";
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                max_speed_mps: Some(1.5),
                command_timeout_ms: 200.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));
        let frame = |t: f64, epoch: &str, seq: i64| {
            let mut m = crate::messages::Map::new();
            m.insert(
                "pose_position".into(),
                ChannelValue::vec3(0.5, 0.0, 0.0, Some("m")),
            );
            m.insert(
                "pose_velocity".into(),
                ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
            );
            SensorFrame {
                t,
                stream: StreamPosition {
                    epoch: epoch.into(),
                    seq,
                },
                session: session(),
                session_id: SID.into(),
                channels: m,
                ..Default::default()
            }
        };
        // Establish epoch A, live.
        transport.push_sensor(frame(0.0, ep_a, 5));
        assert_eq!(
            must_tick(&mut loop_)
                .source
                .as_ref()
                .map(|source| source.seq),
            Some(5),
            "epoch A accepted"
        );
        // A foreign epoch with a huge seq must NOT hijack the LIVE stream.
        *clock.lock().unwrap() = 0.1;
        transport.push_sensor(frame(0.1, ep_b, 9999));
        assert_eq!(
            must_tick(&mut loop_)
                .source
                .as_ref()
                .map(|source| source.seq),
            Some(5),
            "a foreign epoch cannot advance a LIVE stream (no hijack)"
        );
        // Expiry still does not authorize the foreign epoch.
        *clock.lock().unwrap() = 0.5;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "a foreign epoch remains rejected after expiry"
        );
        // The already-bound epoch can still advance with a fresh position.
        *clock.lock().unwrap() = 1.0;
        transport.push_sensor(frame(1.0, ep_a, 6));
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Active,
            "the declared epoch may advance after a pause"
        );
    }

    #[test]
    fn command_owns_stream_and_source_correlates_sensor() {
        // Wire 1.0: the command owns a contiguous publisher stream and local
        // creation time. The driving sensor is correlated only through
        // source/source_t, so decimation is not misclassified as command loss.
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                max_speed_mps: Some(1.5),
                command_timeout_ms: 500.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));

        // A sensor-less tick publishes nothing and therefore consumes no action
        // stream position.
        let _ = must_tick(&mut loop_);

        // A sensor with distinctive identity/time drives the first command.
        let mut ch = crate::messages::Map::new();
        ch.insert(
            "pose_position".into(),
            ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
        );
        ch.insert(
            "pose_velocity".into(),
            ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
        );
        transport.push_sensor(SensorFrame {
            t: 0.1,
            stream: stream(7),

            session: session(),
            session_id: SID.into(),
            frame_id: "map".into(),
            channels: ch,
            ..Default::default()
        });
        *clock.lock().unwrap() = 0.05;
        let cmd = must_tick(&mut loop_);
        assert_eq!(
            cmd.stream.seq, 1,
            "the first command owns position 1 in its own stream"
        );
        assert_ne!(cmd.stream.epoch, stream(7).epoch);
        assert_eq!(cmd.source.as_ref().map(|source| source.seq), Some(7));
        assert_eq!(cmd.source_t, 0.1, "source_t retains the sensor timestamp");
        assert_eq!(cmd.t, 0.05, "command t is the command publisher's clock");
        assert_eq!(cmd.frame_id, "map", "the coordinate frame is echoed");
    }

    #[test]
    fn loop_session_binding_is_immutable_and_rejects_new_generation_payloads() {
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                command_timeout_ms: 200.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));

        transport.push_sensor(sensor_with_motion(0.0, 1, 0.0));
        let first = must_tick(&mut loop_);
        assert_eq!(first.session, session());
        assert_eq!(first.source.as_ref().map(|source| source.seq), Some(1));

        let mut foreign_generation = sensor_with_motion(0.05, 2, 0.0);
        foreign_generation.session.generation = "50000000-0000-4000-8000-000000000005".into();
        transport.push_sensor(foreign_generation);
        *clock.lock().unwrap() = 0.05;
        let second = must_tick(&mut loop_);
        assert_eq!(second.session, session());
        assert_eq!(
            second.source.as_ref().map(|source| source.seq),
            Some(1),
            "a payload cannot rebind a live loop to another generation"
        );

        *clock.lock().unwrap() = 0.3;
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "a rejected generation eventually leaves the original sensor stale"
        );
    }

    #[test]
    fn loop_construction_rejects_invalid_binding_and_epochs_are_csprng_fresh() {
        let invalid = NeuroControlLoop::new(
            InProcessTransport::new(),
            ReflexController::default(),
            20.0,
            SafetyLimits::default(),
            "bad/*",
            session(),
        );
        assert!(invalid.is_err());

        let mut epochs = std::collections::BTreeSet::new();
        for _ in 0..128 {
            let epoch = mint_stream_epoch().expect("platform CSPRNG is available");
            assert!(crate::is_canonical_uuid_v4(&epoch));
            assert!(
                epochs.insert(epoch),
                "fresh publisher epochs must not collide"
            );
        }
    }

    #[test]
    fn controller_is_not_stepped_on_a_stale_sensor() {
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            TrackingController {
                steps: steps.clone(),
                resets: Arc::new(AtomicUsize::new(0)),
                velocity: 0.1,
                ttl_ms: 200.0,
            },
            20.0,
            SafetyLimits {
                command_timeout_ms: 200.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));
        transport.push_sensor(sensor_with_motion(0.0, 1, 0.0));
        assert_eq!(must_tick(&mut loop_).mode, Mode::Active);
        assert_eq!(steps.load(Ordering::SeqCst), 1);

        *clock.lock().unwrap() = 0.5;
        assert_eq!(must_tick(&mut loop_).mode, Mode::Hold);
        assert_eq!(
            steps.load(Ordering::SeqCst),
            1,
            "a cached/stale sensor must not advance controller state"
        );
    }

    #[test]
    fn controller_panic_retires_partially_mutated_controller() {
        let transport = InProcessTransport::new();
        transport.push_sensor(sensor_with_motion(1.0, 1, 0.0));
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            MutateThenPanicController {
                steps: steps.clone(),
                mutated: false,
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_authority(test_authority())
        .with_clock(Box::new(|| 1.0));

        let command = must_tick(&mut loop_);
        assert_eq!(command.mode, Mode::Hold);
        assert!(command
            .channels
            .values()
            .flat_map(|channel| &channel.data)
            .all(|value| *value == 0.0));
        let status = transport.statuses().pop().unwrap();
        assert!(!status.safety_ok);
        assert!(status.note.unwrap().contains("controller failure latched"));

        let later = must_tick(&mut loop_);
        assert_eq!(later.mode, Mode::Hold);
        assert_eq!(
            steps.load(Ordering::SeqCst),
            1,
            "a controller that unwound is never invoked or trusted again"
        );
        let status = transport.statuses().pop().unwrap();
        assert!(!status.safety_ok);
        assert!(status
            .note
            .unwrap()
            .contains("fresh loop/controller required"));
    }

    #[test]
    fn ttl_is_normalized_before_geofence_projection() {
        let transport = InProcessTransport::new();
        transport.push_sensor(sensor_with_motion(1.0, 1, 9.5));
        let mut loop_ = bound_loop(
            transport,
            TrackingController {
                steps: Arc::new(AtomicUsize::new(0)),
                resets: Arc::new(AtomicUsize::new(0)),
                velocity: 1.0,
                ttl_ms: 200.0,
            },
            2.0,
            SafetyLimits {
                geofence_radius_m: Some(10.0),
                command_timeout_ms: 2_000.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(|| 1.0));

        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "the final 1000ms ttl crosses the fence even though the controller's original 200ms ttl did not"
        );
    }

    #[test]
    fn backward_tick_clock_holds_until_the_high_water_mark_is_recovered() {
        let transport = InProcessTransport::new();
        transport.push_sensor(sensor_with_motion(1.0, 1, 0.0));
        let times = Arc::new(Mutex::new(std::collections::VecDeque::from([
            1.0, 1.0, 0.5, 0.5, 1.1, 1.1,
        ])));
        let times2 = times.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits {
                command_timeout_ms: 500.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || {
            times2.lock().unwrap().pop_front().unwrap_or(1.1)
        }));
        assert_eq!(must_tick(&mut loop_).mode, Mode::Active);

        transport.push_sensor(sensor_with_motion(1.1, 2, 0.0));
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Hold,
            "a backward step between ticks must fail closed"
        );
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Active,
            "fresh input may resume only after the clock exceeds its high-water mark"
        );
    }

    #[test]
    fn controller_is_not_reset_by_replayed_lower_sensor_sequence() {
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let resets = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            TrackingController {
                steps: Arc::new(AtomicUsize::new(0)),
                resets: resets.clone(),
                velocity: 0.1,
                ttl_ms: 200.0,
            },
            20.0,
            SafetyLimits {
                command_timeout_ms: 200.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));
        transport.push_sensor(sensor_with_motion(0.0, 500, 0.0));
        assert_eq!(must_tick(&mut loop_).mode, Mode::Active);
        assert_eq!(resets.load(Ordering::SeqCst), 0);

        *clock.lock().unwrap() = 0.5;
        transport.push_sensor(sensor_with_motion(0.5, 1, 0.0));
        assert_eq!(must_tick(&mut loop_).mode, Mode::Hold);
        assert_eq!(
            resets.load(Ordering::SeqCst),
            0,
            "a replay cannot reset controller state after expiry"
        );
    }

    #[test]
    fn reflex_controller_rejects_bad_inputs_and_clamps_vector_magnitude() {
        let mut reflex = ReflexController::default();
        let mut missing_velocity = sensor_with_motion(0.0, 1, 1.0);
        missing_velocity.channels.remove("pose_velocity");
        assert_eq!(reflex.step(Some(&missing_velocity), 50.0).mode, Mode::Hold);

        let mut wrong_unit = sensor_with_motion(0.0, 2, 1.0);
        wrong_unit.channels.get_mut("pose_velocity").unwrap().unit = Some("km/h".into());
        assert_eq!(reflex.step(Some(&wrong_unit), 50.0).mode, Mode::Hold);

        let valid = sensor_with_motion(0.0, 3, 10.0);
        let command = reflex.step(Some(&valid), 50.0);
        let velocity = &command.channels["velocity_setpoint"].data;
        let magnitude = velocity
            .iter()
            .map(|value| value * value)
            .sum::<f64>()
            .sqrt();
        assert!((magnitude - reflex.max_speed).abs() < 1e-12);

        reflex.max_speed = f64::NAN;
        assert_eq!(reflex.step(Some(&valid), 50.0).mode, Mode::Hold);
    }

    #[test]
    fn link_loss_burst_escalates_to_latched_estop() {
        // A sustained loss burst on the sensor seq stream must latch ESTOP via the
        // loop's LinkMonitor -> SafetyGovernor::note_link escalation (not mere HOLD).
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            // Huge command_timeout so the stale-sensor path cannot mask the burst.
            SafetyLimits {
                command_timeout_ms: 100_000.0,
                ..Default::default()
            },
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || *clock2.lock().unwrap()));

        let frame = |t: f64, seq: i64| {
            let mut m = crate::messages::Map::new();
            m.insert(
                "pose_position".into(),
                ChannelValue::vec3(0.1, 0.0, 0.0, Some("m")),
            );
            m.insert(
                "pose_velocity".into(),
                ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
            );
            SensorFrame {
                t,
                stream: stream(seq),
                session: session(),
                session_id: SID.into(),
                channels: m,
                ..Default::default()
            }
        };
        for (i, seq) in [0_i64, 1, 2, 50].into_iter().enumerate() {
            let t = (i as f64 + 1.0) * 0.05;
            *clock.lock().unwrap() = t;
            transport.push_sensor(frame(t, seq));
            let cmd = must_tick(&mut loop_);
            if seq == 50 {
                assert_eq!(
                    cmd.mode,
                    Mode::Estop,
                    "a sensor-sequence loss burst must escalate to ESTOP"
                );
            }
        }
        // Latched: a subsequent clean frame must STILL be ESTOP.
        *clock.lock().unwrap() = 0.30;
        transport.push_sensor(frame(0.30, 51));
        assert_eq!(
            must_tick(&mut loop_).mode,
            Mode::Estop,
            "loss-burst ESTOP must latch until reset"
        );
    }

    #[test]
    fn loop_latency_ms_is_measured() {
        // A clock advancing per read => the post-send read exceeds the tick-start
        // read, so loop_latency_ms is a real measured value, not a constant 0.0.
        let transport = InProcessTransport::new();
        let clock = Arc::new(Mutex::new(0.0_f64));
        let clock2 = clock.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits::default(),
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || {
            let mut t = clock2.lock().unwrap();
            *t += 0.001; // +1 ms per read
            *t
        }));
        let _ = must_tick(&mut loop_);
        let st = transport.statuses().pop().expect("a status was emitted");
        assert!(
            st.loop_latency_ms > 0.0,
            "loop_latency_ms must be a measured value, got {}",
            st.loop_latency_ms
        );
    }

    #[test]
    fn status_stream_starts_at_one_and_advances_strictly() {
        let transport = InProcessTransport::new();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));

        let _ = must_tick(&mut loop_);
        let _ = must_tick(&mut loop_);

        let statuses = transport.statuses();
        assert_eq!(statuses.len(), 2);
        assert_eq!(statuses[0].stream.seq, 1);
        assert_eq!(statuses[1].stream.seq, 2);
        assert_eq!(statuses[0].stream.epoch, statuses[1].stream.epoch);
    }

    #[test]
    fn status_stream_exhaustion_never_reuses_the_last_position() {
        let transport = InProcessTransport::new();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));
        loop_.status_seq = JSON_SAFE_INTEGER_MAX - 1;

        let _ = must_tick(&mut loop_);
        assert_eq!(transport.statuses()[0].stream.seq, JSON_SAFE_INTEGER_MAX);

        let _ = must_tick(&mut loop_);
        assert_eq!(
            transport.statuses().len(),
            1,
            "an exhausted status publisher must become silent rather than repeat 2^53-1"
        );
    }

    #[test]
    fn command_stream_exhaustion_returns_no_controller_or_wire_frame() {
        let transport = InProcessTransport::new();
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            PreStampedController {
                steps: steps.clone(),
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));
        transport.push_sensor(sensor_with_motion(1.0, 1, 0.0));
        loop_.command_seq = JSON_SAFE_INTEGER_MAX;

        let error = loop_
            .tick()
            .expect_err("an exhausted publisher cannot return a controller frame");

        assert_eq!(error, ControlLoopTickError::CommandStreamExhausted);
        assert_eq!(steps.load(Ordering::SeqCst), 0);
        assert!(transport.commands().is_empty());
        assert!(transport.statuses().is_empty());
    }

    #[test]
    fn malformed_transport_admission_retires_the_binding() {
        let transport = ScriptedTransport::new(
            sensor_with_motion(1.0, 1, 0.0),
            vec![
                CommandSendOutcome::Accepted(StreamPosition::default()),
                CommandSendOutcome::Accepted(StreamPosition {
                    epoch: "40000000-0000-4000-8000-000000000004".into(),
                    seq: 1,
                }),
            ],
        );
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            PreStampedController {
                steps: steps.clone(),
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::InvalidTransportAdmission
        );
        assert_eq!(loop_.command_seq, 0);
        assert_eq!(steps.load(Ordering::SeqCst), 1);
        assert_eq!(transport.commands.lock().unwrap().len(), 1);
        assert!(transport.statuses.lock().unwrap().is_empty());

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::InvalidTransportAdmission,
            "an ambiguous transport binding cannot recover in place"
        );
        assert_eq!(steps.load(Ordering::SeqCst), 1);
        assert_eq!(transport.commands.lock().unwrap().len(), 1);
        assert_eq!(transport.outcomes.lock().unwrap().len(), 1);
        assert!(transport.statuses.lock().unwrap().is_empty());
    }

    #[test]
    fn transport_panic_after_slot_mutation_retires_the_binding() {
        let transport = PanicAfterAdmissionTransport::new(sensor_with_motion(1.0, 1, 0.0));
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            PreStampedController {
                steps: steps.clone(),
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::InvalidTransportAdmission,
            "a transport unwind after mutation is contained as ambiguous admission"
        );
        assert_eq!(loop_.command_seq, 0);
        assert_eq!(steps.load(Ordering::SeqCst), 1);
        assert_eq!(transport.sensor_reads.load(Ordering::SeqCst), 1);
        assert_eq!(transport.send_attempts.load(Ordering::SeqCst), 1);
        assert_eq!(transport.admitted_commands.lock().unwrap().len(), 1);
        assert_eq!(transport.status_attempts.load(Ordering::SeqCst), 0);

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::InvalidTransportAdmission,
            "an ambiguous transport binding cannot recover in place"
        );
        assert_eq!(steps.load(Ordering::SeqCst), 1);
        assert_eq!(transport.sensor_reads.load(Ordering::SeqCst), 1);
        assert_eq!(transport.send_attempts.load(Ordering::SeqCst), 1);
        assert_eq!(transport.admitted_commands.lock().unwrap().len(), 1);
        assert_eq!(transport.status_attempts.load(Ordering::SeqCst), 0);
    }

    fn assert_inconsistent_admission_retires_binding(hostile: CommandSendOutcome) {
        let first = StreamPosition {
            epoch: "40000000-0000-4000-8000-000000000004".into(),
            seq: 42,
        };
        let transport = ScriptedTransport::new(
            sensor_with_motion(1.0, 1, 0.0),
            vec![
                CommandSendOutcome::Accepted(first.clone()),
                hostile,
                CommandSendOutcome::Accepted(StreamPosition {
                    epoch: first.epoch.clone(),
                    seq: 43,
                }),
            ],
        );
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            PreStampedController {
                steps: steps.clone(),
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));

        assert_eq!(loop_.tick().unwrap().stream, first);
        assert_eq!(loop_.command_seq, 1);
        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::InvalidTransportAdmission
        );
        assert_eq!(loop_.command_seq, 1);
        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::InvalidTransportAdmission
        );
        assert_eq!(loop_.command_seq, 1);
        assert_eq!(steps.load(Ordering::SeqCst), 2);
        assert_eq!(transport.commands.lock().unwrap().len(), 2);
        assert_eq!(transport.outcomes.lock().unwrap().len(), 1);
        assert_eq!(
            transport.statuses.lock().unwrap().len(),
            1,
            "only the valid pre-violation admission emits status"
        );
    }

    #[test]
    fn inconsistent_transport_admissions_retire_the_binding() {
        let first = StreamPosition {
            epoch: "40000000-0000-4000-8000-000000000004".into(),
            seq: 42,
        };
        for hostile in [
            CommandSendOutcome::Accepted(StreamPosition {
                epoch: "50000000-0000-4000-8000-000000000005".into(),
                seq: 43,
            }),
            CommandSendOutcome::Accepted(first.clone()),
            CommandSendOutcome::ReplacedPending(StreamPosition {
                epoch: first.epoch.clone(),
                seq: 43,
            }),
        ] {
            assert_inconsistent_admission_retires_binding(hostile);
        }
    }

    #[test]
    fn valid_transport_admissions_advance_or_replace_exactly() {
        let first = StreamPosition {
            epoch: "40000000-0000-4000-8000-000000000004".into(),
            seq: 42,
        };
        let next = StreamPosition {
            epoch: first.epoch.clone(),
            seq: 43,
        };
        let transport = ScriptedTransport::new(
            sensor_with_motion(1.0, 1, 0.0),
            vec![
                CommandSendOutcome::Accepted(first.clone()),
                CommandSendOutcome::ReplacedPending(first.clone()),
                CommandSendOutcome::Accepted(next.clone()),
            ],
        );
        let mut loop_ = bound_loop(
            transport.clone(),
            PreStampedController {
                steps: Arc::new(AtomicUsize::new(0)),
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));

        assert_eq!(loop_.tick().unwrap().stream, first);
        assert_eq!(loop_.command_seq, 1);
        assert_eq!(loop_.tick().unwrap().stream, first);
        assert_eq!(loop_.command_seq, 1);
        assert_eq!(loop_.tick().unwrap().stream, next);
        assert_eq!(loop_.command_seq, 2);
        assert_eq!(transport.statuses.lock().unwrap().len(), 3);
    }

    #[test]
    fn synchronous_transport_rejection_is_an_error_and_reuses_local_candidate() {
        let assigned = StreamPosition {
            epoch: "40000000-0000-4000-8000-000000000004".into(),
            seq: 42,
        };
        let transport = ScriptedTransport::new(
            sensor_with_motion(1.0, 1, 0.0),
            vec![
                CommandSendOutcome::Rejected,
                CommandSendOutcome::Accepted(assigned.clone()),
            ],
        );
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            TrackingController {
                steps: steps.clone(),
                resets: Arc::new(AtomicUsize::new(0)),
                velocity: 0.5,
                ttl_ms: 200.0,
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_authority(test_authority())
        .with_clock(Box::new(|| 1.0));

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::CommandPublicationRejected
        );
        assert_eq!(
            loop_.command_seq, 0,
            "rejection must not commit the candidate"
        );
        assert!(transport.statuses.lock().unwrap().is_empty());

        let admitted = loop_.tick().expect("the second slot is accepted");
        assert_eq!(
            admitted.stream, assigned,
            "tick returns the assigned position"
        );
        assert_eq!(loop_.command_seq, 1);
        assert_eq!(steps.load(Ordering::SeqCst), 2);
        let attempts = transport.commands.lock().unwrap();
        assert_eq!(attempts.len(), 2);
        assert_eq!(
            attempts[0].stream, attempts[1].stream,
            "the loop-local candidate position is reused after rejection"
        );
        assert_eq!(transport.statuses.lock().unwrap().len(), 1);
    }

    #[test]
    fn rejected_tick_retains_clock_high_water_until_recovery() {
        let assigned_hold = StreamPosition {
            epoch: "40000000-0000-4000-8000-000000000004".into(),
            seq: 42,
        };
        let assigned_active = StreamPosition {
            epoch: assigned_hold.epoch.clone(),
            seq: 43,
        };
        let transport = ScriptedTransport::new(
            sensor_with_motion(2.0, 1, 0.0),
            vec![
                CommandSendOutcome::Rejected,
                CommandSendOutcome::Accepted(assigned_hold),
                CommandSendOutcome::Accepted(assigned_active),
            ],
        );
        let times = Arc::new(Mutex::new(VecDeque::from([
            2.0, 2.0, // rejected tick establishes the high-water mark
            1.0, 1.0, // rewind must fail closed
            2.1, 2.1, // recovery only after crossing the retained mark
        ])));
        let times_for_loop = times.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            TrackingController {
                steps: Arc::new(AtomicUsize::new(0)),
                resets: Arc::new(AtomicUsize::new(0)),
                velocity: 0.5,
                ttl_ms: 200.0,
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || {
            times_for_loop
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .pop_front()
                .unwrap_or(2.1)
        }));

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::CommandPublicationRejected
        );
        assert_eq!(
            loop_.tick().expect("rewind emits a governed HOLD").mode,
            Mode::Hold,
            "a rejected tick must still retain its clock high-water mark"
        );
        assert_eq!(
            loop_
                .tick()
                .expect("clock recovery restores slot admission")
                .mode,
            Mode::Active,
            "Active can resume only after the clock exceeds the retained mark"
        );
    }

    #[test]
    fn transport_owned_exhaustion_is_reported_before_status() {
        let transport = ScriptedTransport::new(
            sensor_with_motion(1.0, 1, 0.0),
            vec![CommandSendOutcome::StreamExhausted],
        );
        let steps = Arc::new(AtomicUsize::new(0));
        let mut loop_ = bound_loop(
            transport.clone(),
            PreStampedController {
                steps: steps.clone(),
            },
            20.0,
            SafetyLimits::default(),
        )
        .with_clock(Box::new(|| 1.0));

        assert_eq!(
            loop_.tick().unwrap_err(),
            ControlLoopTickError::TransportCommandStreamExhausted
        );
        assert_eq!(steps.load(Ordering::SeqCst), 1);
        assert_eq!(loop_.command_seq, 0);
        assert!(transport.statuses.lock().unwrap().is_empty());
    }

    #[test]
    fn invalid_or_unwatchdoggable_rate_forces_hold() {
        for rate_hz in [0.0, -20.0, f64::NAN, 0.01] {
            let transport = InProcessTransport::new();
            let mut channels = crate::messages::Map::new();
            channels.insert(
                "pose_position".into(),
                ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
            );
            channels.insert(
                "pose_velocity".into(),
                ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
            );
            transport.push_sensor(SensorFrame {
                stream: stream(1),

                session: session(),
                session_id: SID.into(),
                channels,
                ..Default::default()
            });
            let mut loop_ = bound_loop(
                transport.clone(),
                ReflexController::default(),
                rate_hz,
                SafetyLimits::default(),
            )
            .with_authority(test_authority())
            .with_clock(Box::new(|| 1.0));
            let command = must_tick(&mut loop_);
            assert_eq!(command.mode, Mode::Hold, "rate={rate_hz:?}");
            assert!(command.ttl_ms.is_finite(), "rate={rate_hz:?}");
            let status = transport.statuses().pop().unwrap();
            assert!(!status.safety_ok, "rate={rate_hz:?}");
            assert!(status.note.unwrap().contains("invalid control rate"));
        }
    }

    #[test]
    fn clock_failure_during_tick_forces_current_command_hold() {
        let transport = InProcessTransport::new();
        let mut channels = crate::messages::Map::new();
        channels.insert(
            "pose_position".into(),
            ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
        );
        channels.insert(
            "pose_velocity".into(),
            ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
        );
        transport.push_sensor(SensorFrame {
            stream: stream(1),

            session: session(),
            session_id: SID.into(),
            channels,
            ..Default::default()
        });
        let times = Arc::new(Mutex::new(std::collections::VecDeque::from([1.0, 0.0])));
        let times2 = times.clone();
        let mut loop_ = bound_loop(
            transport.clone(),
            ReflexController::default(),
            20.0,
            SafetyLimits::default(),
        )
        .with_authority(test_authority())
        .with_clock(Box::new(move || {
            times2.lock().unwrap().pop_front().unwrap_or(0.0)
        }));
        let command = must_tick(&mut loop_);
        assert_eq!(command.mode, Mode::Hold);
        assert!(command
            .channels
            .values()
            .flat_map(|channel| &channel.data)
            .all(|value| *value == 0.0));
        let status = transport.statuses().pop().unwrap();
        assert!(!status.safety_ok);
        assert!(status.note.unwrap().contains("clock anomaly"));
    }
}
