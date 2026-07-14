//! # ncp (Python) — PyO3 bindings for the NCP Rust core
//!
//! So Python projects use the **canonical Rust implementation** of NCP rather
//! than reimplementing the wire: the version guard, the key scheme, the rate
//! codec, the action-plane safety governor, and message validation all come from
//! `ncp-core`. A Python backend may keep its own server-side models (e.g. Engram's
//! NEST server keeps Pydantic ones),
//! but any Python peer can compute keys, encode/decode, and validate frames
//! through this module and be guaranteed wire-identical to the Rust and TS peers.
//!
//! Build the importable extension with maturin (`maturin develop -m
//! ncp-python/Cargo.toml --features extension-module`). The `extension-module`
//! feature is **off by default** so `cargo build`/`check`/`test --workspace`
//! works on Linux/Windows (enabling it unconditionally suppresses the libpython
//! link and breaks the non-Python build/test); maturin must enable it explicitly.
//!
//! ```python
//! import ncp
//! ncp.NCP_VERSION                      # "1.0"
//! k = ncp.Keys("ncp")                  # the realm is a deployment choice (e.g. "engram/ncp")
//! k.command("uav3")                    # "ncp/session/uav3/command"
//! ncp.decode_command(codec_json, '{"vel_x":200.0}', seq=7, t=0.0)  # CommandFrame JSON
//! gov = ncp.Governor('{"command_timeout_ms": 500.0}')  # PERSISTENT (latching) governor
//! ```

use ncp_core::{
    valid_id_segment, ActionBuffer as CoreActionBuffer, AuthorityLease, ChannelValue, CodecSpec,
    CommandFrame, Keys as CoreKeys, Map, Mode, SafetyGovernor, SafetyLimits, SensorFrame,
    WireFrame,
};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

fn val<E: std::fmt::Display>(e: E) -> PyErr {
    PyValueError::new_err(e.to_string())
}

fn parse_bounded<T: serde::de::DeserializeOwned>(json: &str) -> PyResult<T> {
    let value = ncp_core::bounded_json::parse_value(json.as_bytes()).map_err(val)?;
    serde_json::from_value(value).map_err(val)
}

fn validate_key_segment(value: &str, label: &str) -> PyResult<()> {
    if valid_id_segment(value) {
        Ok(())
    } else {
        Err(PyValueError::new_err(format!(
            "invalid NCP {label} key segment: {value:?}"
        )))
    }
}

/// The NCP key scheme (the three planes + control RPC), so Python addresses the
/// same keys as the Rust peers.
#[pyclass]
struct Keys {
    inner: CoreKeys,
}

#[pymethods]
impl Keys {
    #[new]
    #[pyo3(signature = (realm = None))]
    fn new(realm: Option<String>) -> PyResult<Self> {
        let realm = realm.unwrap_or_else(|| ncp_core::DEFAULT_REALM.to_string());
        Ok(Keys {
            inner: CoreKeys::try_new(realm).map_err(val)?,
        })
    }
    /// Control-plane prefix. Use `rpc_for_kind()` for a request.
    fn rpc(&self) -> String {
        self.inner.rpc()
    }
    fn rpc_for_kind(&self, kind: &str) -> PyResult<String> {
        self.inner.rpc_for_kind(kind).map_err(val)
    }
    fn rpc_glob(&self) -> String {
        self.inner.rpc_glob()
    }
    fn sensor(&self, session_id: &str) -> PyResult<String> {
        validate_key_segment(session_id, "session id")?;
        Ok(self.inner.sensor(session_id))
    }
    fn sensor_named(&self, session_id: &str, name: &str) -> PyResult<String> {
        validate_key_segment(session_id, "session id")?;
        validate_key_segment(name, "sensor name")?;
        Ok(self.inner.sensor_named(session_id, name))
    }
    fn command(&self, session_id: &str) -> PyResult<String> {
        validate_key_segment(session_id, "session id")?;
        Ok(self.inner.command(session_id))
    }
    fn command_named(&self, session_id: &str, name: &str) -> PyResult<String> {
        validate_key_segment(session_id, "session id")?;
        validate_key_segment(name, "command name")?;
        Ok(self.inner.command_named(session_id, name))
    }
    fn observation(&self, session_id: &str) -> PyResult<String> {
        validate_key_segment(session_id, "session id")?;
        Ok(self.inner.observation(session_id))
    }
    fn session_glob(&self, session_id: &str) -> PyResult<String> {
        validate_key_segment(session_id, "session id")?;
        Ok(self.inner.session_glob(session_id))
    }
}

/// `True` if `version` is major-compatible with this NCP. Raises on a major
/// mismatch when `strict`.
#[pyfunction]
#[pyo3(signature = (version, strict = false))]
fn check_version(version: &str, strict: bool) -> PyResult<bool> {
    ncp_core::check_version(version, strict).map_err(val)
}

/// Classify a peer-advertised contract hash against ours — the **advisory** half of
/// the handshake (`ncp_version`/`check_version` is the hard gate). Never raises;
/// returns a stable tag: `"match"` (peer == ours), `"not_advertised"` (peer sent
/// `None`), or `"mismatch"` (peer advertised a different hash — log it, the session
/// still proceeds). Mirrors `ncp_core::contract_status` / `ContractStatus`.
#[pyfunction]
#[pyo3(signature = (peer_hash = None))]
fn contract_status(peer_hash: Option<&str>) -> &'static str {
    use ncp_core::ContractStatus;
    match ncp_core::contract_status(peer_hash) {
        ContractStatus::Match => "match",
        ContractStatus::NotAdvertised => "not_advertised",
        ContractStatus::Mismatch { .. } => "mismatch",
    }
}

/// Compute the normative request-digest-v1 SHA-256 for a step/run/close JSON
/// request. The embedded digest and retry bit may be absent or placeholders;
/// authority renewal and retry metadata are outside the semantic projection.
#[pyfunction]
fn request_digest(request_json: &str) -> PyResult<String> {
    let request = ncp_core::bounded_json::parse_value(request_json.as_bytes()).map_err(val)?;
    ncp_core::request_digest(&request).map_err(val)
}

/// Rate-encode a complete wire-valid `SensorFrame` JSON to
/// `{population: rate_hz}` JSON, via the checked Rust codec. `sensor_json` may be
/// `"null"` for the intentional no-sensor case.
#[pyfunction]
fn encode_rates(codec_json: &str, sensor_json: &str) -> PyResult<String> {
    let codec: CodecSpec = parse_bounded(codec_json)?;
    let sensor: Option<SensorFrame> = parse_bounded(sensor_json)?;
    let rates = codec.encode_checked(sensor.as_ref()).map_err(val)?;
    serde_json::to_string(&rates).map_err(val)
}

/// Rate-decode `{population: rate_hz}` JSON to a wire-valid `CommandFrame` JSON,
/// via the checked Rust codec. The caller owns the monotonically increasing seq;
/// the binding never fabricates one.
#[pyfunction]
#[pyo3(signature = (codec_json, rates_json, seq, t = 0.0, frame_id = "world", mode = "hold", epoch = "", session_generation = "", session_id = "", authority_json = None))]
#[allow(clippy::too_many_arguments)]
fn decode_command(
    codec_json: &str,
    rates_json: &str,
    seq: i64,
    t: f64,
    frame_id: &str,
    mode: &str,
    epoch: &str,
    session_generation: &str,
    session_id: &str,
    authority_json: Option<&str>,
) -> PyResult<String> {
    let codec: CodecSpec = parse_bounded(codec_json)?;
    let rates: Map<f64> = parse_bounded(rates_json)?;
    let mode = parse_mode(mode)?;
    // Wire 1.0: the caller owns stream/session identity and, for Active mode, the
    // authority lease. The binding never fabricates any of them.
    let stream = ncp_core::StreamPosition {
        epoch: epoch.to_string(),
        seq,
    };
    let session = ncp_core::SessionRef {
        generation: session_generation.to_string(),
    };
    let authority = match authority_json {
        Some(value) => parse_bounded::<Option<AuthorityLease>>(value)?,
        None => None,
    };
    let cmd = codec
        .decode_checked_with_authority(
            &rates, t, stream, frame_id, mode, session, session_id, authority,
        )
        .map_err(val)?;
    serde_json::to_string(&cmd).map_err(val)
}

fn parse_mode(s: &str) -> PyResult<Mode> {
    Ok(match s {
        "init" => Mode::Init,
        "active" => Mode::Active,
        "hold" => Mode::Hold,
        "estop" => Mode::Estop,
        other => return Err(PyValueError::new_err(format!("unknown mode {other:?}"))),
    })
}

fn parse_sensor(sensor_json: Option<&str>) -> PyResult<Option<SensorFrame>> {
    match sensor_json {
        None => Ok(None),
        Some(value) => parse_bounded(value),
    }
}

/// Apply the action-plane safety governor to a `CommandFrame` JSON, returning the
/// governed `CommandFrame` JSON (HOLD on a stale sensor, ESTOP on geofence breach,
/// speed clamp). `sensor_json`/`last_sensor_s` may be `None`.
///
/// **One-shot**: a fresh governor is constructed per call, so the ESTOP latch
/// cannot persist across calls. Use this for stateless/corpus checks only — a
/// real plant MUST hold a persistent [`Governor`] so a latched ESTOP survives
/// until an authorized operator calls `reset()`.
#[pyfunction]
#[pyo3(signature = (limits_json, command_json, now_s, sensor_json = None, last_sensor_s = None))]
fn govern(
    limits_json: &str,
    command_json: &str,
    now_s: f64,
    sensor_json: Option<&str>,
    last_sensor_s: Option<f64>,
) -> PyResult<String> {
    let limits: SafetyLimits = parse_bounded(limits_json)?;
    let mut gov = SafetyGovernor::new(limits);
    govern_with(&mut gov, command_json, now_s, sensor_json, last_sensor_s)
}

fn govern_with(
    gov: &mut SafetyGovernor,
    command_json: &str,
    now_s: f64,
    sensor_json: Option<&str>,
    last_sensor_s: Option<f64>,
) -> PyResult<String> {
    let mut command: CommandFrame = parse_bounded(command_json)?;
    // An explicit ESTOP always latches. Every other invalid action envelope is
    // converted to HOLD so a binding caller cannot accidentally actuate after
    // bypassing `validate()`.
    if command.mode != Mode::Estop && command.validate_wire().is_err() {
        command.mode = Mode::Hold;
    }
    let mut sensor = parse_sensor(sensor_json)?;
    let sensor_valid = sensor
        .as_ref()
        .is_some_and(|frame| frame.validate_wire().is_ok());
    if !sensor_valid {
        sensor = None;
    }
    // `sensor=None` independently denies actuation. Preserve the timestamp of
    // the last accepted sensor so prolonged absence/invalid input can still
    // cross the reference governor's total-silence ESTOP deadline.
    let out = gov.govern(&command, sensor.as_ref(), now_s, last_sensor_s);
    serde_json::to_string(&out).map_err(val)
}

/// A **persistent** action-plane safety governor: the stateful form whose ESTOP
/// latch survives across calls (a geofence breach / inbound ESTOP / link collapse
/// keeps every later `govern` at ESTOP until an authorized operator calls `reset()`).
/// This is what a real plant must hold — the module-level one-shot `govern`
/// function cannot latch by construction. Wraps `ncp_core::SafetyGovernor`.
#[pyclass]
struct Governor {
    inner: SafetyGovernor,
}

#[pymethods]
impl Governor {
    #[new]
    fn new(limits_json: &str) -> PyResult<Self> {
        let limits: SafetyLimits = parse_bounded(limits_json)?;
        Ok(Self {
            inner: SafetyGovernor::new(limits),
        })
    }

    /// Govern one `CommandFrame` JSON against the latest sensor; returns the
    /// governed `CommandFrame` JSON. The ESTOP latch persists across calls.
    #[pyo3(signature = (command_json, now_s, sensor_json = None, last_sensor_s = None))]
    fn govern(
        &mut self,
        command_json: &str,
        now_s: f64,
        sensor_json: Option<&str>,
        last_sensor_s: Option<f64>,
    ) -> PyResult<String> {
        govern_with(
            &mut self.inner,
            command_json,
            now_s,
            sensor_json,
            last_sensor_s,
        )
    }

    /// Clear the governor's local ESTOP after external operator/interlock
    /// authorization. This method does not authenticate or restore session
    /// authority. A config-level fail-closed state is not cleared.
    fn reset(&mut self) {
        self.inner.reset()
    }

    /// True while ESTOP is latched.
    fn is_estopped(&self) -> bool {
        self.inner.is_estopped()
    }

    /// Latch ESTOP when a link monitor reports a sustained loss burst (a jam).
    fn note_link(&mut self, burst: bool) {
        self.inner.note_link(burst)
    }

    /// False under a latched ESTOP or a config-level fail-closed.
    fn safety_ok(&self) -> bool {
        self.inner.safety_ok()
    }
}

/// Persistent plant-side command buffer. This complements [`Governor`]: the
/// governor checks sensor freshness/geofence/speed policy, while `ActionBuffer`
/// enforces command `ttl_ms`, seq/replay rejection, bounded predictive-horizon
/// replay, and a separate ESTOP latch. A live actuator needs both layers.
#[pyclass]
struct ActionBuffer {
    inner: CoreActionBuffer,
}

#[pymethods]
impl ActionBuffer {
    #[new]
    fn new() -> Self {
        Self {
            inner: CoreActionBuffer::new(),
        }
    }

    /// Ingest one CommandFrame JSON at the plant's local arrival time. This is a
    /// body-local buffer API, not a remote ingress gate: callers must first bind
    /// authenticated actor/plane and the exact live route/session generation.
    /// Over-budget or malformed JSON raises ValueError; parseable invalid/replayed
    /// frames are fail-closed and ignored by the core, while a locally admitted
    /// ESTOP latches.
    fn on_command(&mut self, now_s: f64, command_json: &str) -> PyResult<()> {
        let command: CommandFrame = parse_bounded(command_json)?;
        self.inner.on_command(now_s, command);
        Ok(())
    }

    /// Return the active channel-map JSON at `now_s`, or `None` when the plant
    /// must HOLD (no command, expired TTL, replay rejection, horizon drain, or
    /// latched ESTOP).
    fn active(&self, now_s: f64) -> PyResult<Option<String>> {
        self.inner
            .active(now_s)
            .map(|channels| serde_json::to_string(&channels).map_err(val))
            .transpose()
    }

    /// True when no active setpoint is safe to apply at `now_s`.
    fn should_hold(&self, now_s: f64) -> bool {
        self.inner.should_hold(now_s)
    }

    /// Clear the local latch and permanently retire this generation-bound buffer.
    /// This method does not authenticate an operator or restore remote authority;
    /// a successful generation cut constructs a fresh ActionBuffer.
    fn reset(&mut self) {
        self.inner.reset()
    }

    /// True while the action buffer's ESTOP is latched.
    fn is_estopped(&self) -> bool {
        self.inner.is_estopped()
    }

    /// True after reset permanently retired this generation-bound buffer.
    fn is_retired(&self) -> bool {
        self.inner.is_retired()
    }
}

/// Validate an NCP message JSON of a given `kind` through the universal bounded
/// JSON ingress, the canonical semantic validator, and its Rust wire type.
/// Raises `ValueError` on a resource-limit, syntax, schema, or semantic failure;
/// otherwise returns canonical JSON. A structurally valid frame can still be
/// rejected downstream by stateful safety policy (for example a stale or
/// replayed command).
#[pyfunction]
fn validate(kind: &str, json: &str) -> PyResult<String> {
    use ncp_core::*;
    // Run the CANONICAL, kind-aware checks first: required fields + the
    // scientific-boundary value pins (calibrated_posterior=false /
    // is_simulation_output=true). The typed serde round-trip below alone does NOT
    // enforce these — a missing required field would silently default, and a
    // tampered discriminator would round-trip clean. (Previously this binding
    // skipped ncp_core::validate entirely, so the Python wire check was weaker
    // than the Rust reference.)
    let mut value = ncp_core::bounded_json::parse_value(json.as_bytes()).map_err(val)?;
    match value.as_object_mut() {
        Some(m) => match m.get("kind") {
            Some(serde_json::Value::String(k)) if k == kind => {}
            Some(serde_json::Value::String(k)) => {
                return Err(PyValueError::new_err(format!(
                    "kind mismatch: argument {kind:?} but body says {k:?}"
                )));
            }
            Some(_) => return Err(PyValueError::new_err("NCP message kind must be a string")),
            None => {
                return Err(PyValueError::new_err(
                    "NCP message carries no kind (mandatory since wire 0.6)",
                ));
            }
        },
        None => return Err(PyValueError::new_err("NCP message is not a JSON object")),
    }
    ncp_core::validate(&value).map_err(|e| PyValueError::new_err(e.to_string()))?;

    // Round-trip the same document that was validated. `kind` is a mandatory
    // wire-0.6 discriminator and must never be fabricated from the API argument.
    macro_rules! rt {
        ($t:ty) => {{
            let v: $t = serde_json::from_value(value.clone()).map_err(val)?;
            serde_json::to_string(&v).map_err(val)
        }};
    }
    match kind {
        "open_session" => rt!(OpenSession),
        "session_opened" => rt!(SessionOpened),
        "step_request" => rt!(StepRequest),
        "run_request" => rt!(RunRequest),
        "stimulus_frame" => rt!(StimulusFrame),
        "observation_frame" => rt!(ObservationFrame),
        "close_session" => rt!(CloseSession),
        "session_closed" => rt!(SessionClosed),
        "sensor_frame" => rt!(SensorFrame),
        "command_frame" => rt!(CommandFrame),
        "control_status" => rt!(ControlStatus),
        "link_status" => rt!(LinkStatus),
        "capabilities" => rt!(Capabilities),
        "error" => rt!(ErrorFrame),
        other => Err(PyValueError::new_err(format!(
            "unknown NCP message kind {other:?}"
        ))),
    }
}

/// Convenience: build a `ChannelValue` JSON (`{"data": [...], "unit": ...}`).
#[pyfunction]
#[pyo3(signature = (data, unit = None))]
fn channel_value(data: Vec<f64>, unit: Option<String>) -> PyResult<String> {
    if data.iter().any(|value| {
        !value.is_finite() || value.abs() > ncp_core::bounded_json::MAX_FINITE_NUMBER_MAGNITUDE
    }) {
        return Err(PyValueError::new_err(
            "NCP-LIMIT-006: channel data exceeds the finite numeric budget",
        ));
    }
    let encoded = serde_json::to_string(&ChannelValue { data, unit }).map_err(val)?;
    ncp_core::bounded_json::preflight(encoded.as_bytes()).map_err(val)?;
    Ok(encoded)
}

#[pymodule]
fn ncp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("PACKAGE_VERSION", env!("CARGO_PKG_VERSION"))?;
    m.add("NCP_VERSION", ncp_core::NCP_VERSION)?;
    m.add("CONTRACT_HASH", ncp_core::CONTRACT_HASH)?;
    m.add(
        "NORMATIVE_CONTRACT_DIGEST",
        ncp_core::NORMATIVE_CONTRACT_DIGEST,
    )?;
    m.add("BUILD_IDENTITY", ncp_core::BUILD_IDENTITY)?;
    m.add("DEFAULT_REALM", ncp_core::DEFAULT_REALM)?;
    m.add_class::<Keys>()?;
    m.add_class::<Governor>()?;
    m.add_class::<ActionBuffer>()?;
    m.add_function(wrap_pyfunction!(check_version, m)?)?;
    m.add_function(wrap_pyfunction!(contract_status, m)?)?;
    m.add_function(wrap_pyfunction!(request_digest, m)?)?;
    m.add_function(wrap_pyfunction!(encode_rates, m)?)?;
    m.add_function(wrap_pyfunction!(decode_command, m)?)?;
    m.add_function(wrap_pyfunction!(govern, m)?)?;
    m.add_function(wrap_pyfunction!(validate, m)?)?;
    m.add_function(wrap_pyfunction!(channel_value, m)?)?;
    Ok(())
}
