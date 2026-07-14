//! Transport-neutral **bus** abstraction: RPC via a *queryable* on a key
//! expression, streaming via *pub/sub* on per-session keys. Peers address data
//! (`{realm}/**`), not server addresses — location-transparent, many-to-many.
//!
//! `ncp-core` ships a synchronous `Bus` trait plus an in-process `LocalBus`
//! (deterministic, dependency-free — for tests and co-process use) and the
//! generic `NcpBusClient` / `NcpBusServer` that carry NCP over any `Bus`. The
//! Zenoh binding lives in the `ncp-zenoh` crate. Raw [`Bus`] payloads are
//! deliberately untrusted bytes: only the exact typed `NcpBus*` boundaries add
//! bounded decoding, live-session binding, and per-lifetime stream monotonicity.
//! Mirrors `backend/neurocontrol/bus.py`.

use std::sync::{Arc, Mutex};

use crate::keys::Keys;

const MAX_RPC_DIAGNOSTIC_BYTES: usize = 1_024;

struct BoundedDiagnostic {
    output: String,
    truncated: bool,
}

impl BoundedDiagnostic {
    fn new() -> Self {
        Self {
            output: String::with_capacity(MAX_RPC_DIAGNOSTIC_BYTES),
            truncated: false,
        }
    }

    fn finish(mut self) -> String {
        if self.truncated {
            self.output.push_str("...");
        }
        self.output
    }
}

impl std::fmt::Write for BoundedDiagnostic {
    fn write_str(&mut self, value: &str) -> std::fmt::Result {
        if self.truncated {
            return Ok(());
        }
        let remaining = MAX_RPC_DIAGNOSTIC_BYTES
            .saturating_sub(3)
            .saturating_sub(self.output.len());
        if value.len() <= remaining {
            self.output.push_str(value);
            return Ok(());
        }
        let mut end = remaining.min(value.len());
        while !value.is_char_boundary(end) {
            end -= 1;
        }
        self.output.push_str(&value[..end]);
        self.truncated = true;
        Ok(())
    }
}

fn bounded_diagnostic(arguments: std::fmt::Arguments<'_>) -> String {
    let mut writer = BoundedDiagnostic::new();
    let _ = std::fmt::write(&mut writer, arguments);
    writer.finish()
}

fn check_reply_frame_size(reply: &[u8]) -> Result<(), BusError> {
    if reply.len() > crate::bounded_json::MAX_FRAME_BYTES {
        return Err(BusError(format!(
            "NCP-LIMIT-001: RPC reply frame byte limit exceeded ({} > {})",
            reply.len(),
            crate::bounded_json::MAX_FRAME_BYTES
        )));
    }
    Ok(())
}

fn bounded_rpc_error_payload(
    code: crate::RpcErrorCode,
    error: impl std::fmt::Display,
    session_id: Option<String>,
    session: Option<crate::SessionRef>,
    request_kind: Option<String>,
) -> Vec<u8> {
    let reply = crate::rpc_error_payload_with_session(
        code,
        bounded_diagnostic(format_args!("{error}")),
        session_id,
        session,
        request_kind,
    );
    if reply.len() <= crate::bounded_json::MAX_FRAME_BYTES {
        return reply;
    }
    crate::rpc_error_payload_with_session(
        crate::RpcErrorCode::JsonLimit(crate::bounded_json::JsonLimitCode::FrameBytes),
        "generated RPC error reply exceeded the frame byte limit",
        None,
        None,
        None,
    )
}

fn check_bus_keys(keys: &Keys) -> Result<(), BusError> {
    keys.validate()
        .map_err(|error| BusError(format!("refusing invalid NCP realm: {error}")))
}

fn key_error(error: crate::InvalidKeySegment) -> BusError {
    BusError(error.to_string())
}

fn check_live_session(session: &crate::SessionRef) -> Result<(), BusError> {
    if crate::is_canonical_uuid_v4(&session.generation) {
        Ok(())
    } else {
        Err(BusError(
            "expected live session generation must be a canonical lowercase UUIDv4".into(),
        ))
    }
}

fn accept_publisher_stream(
    fence: &Mutex<crate::StreamMonotonicityFence>,
    route: &str,
    kind: &str,
    session: &crate::SessionRef,
    stream: &crate::StreamPosition,
) -> Result<(), BusError> {
    let mut fence = fence.lock().map_err(|_| {
        BusError("typed publisher stream fence is poisoned; refusing publish".into())
    })?;
    fence
        .accept(route, kind, session, stream)
        .map_err(|error| BusError(format!("typed publisher stream rejected: {error}")))
}

fn accept_subscriber_stream(
    fence: &Mutex<crate::StreamMonotonicityFence>,
    route: &str,
    kind: &str,
    session: &crate::SessionRef,
    stream: &crate::StreamPosition,
) -> bool {
    let Ok(mut fence) = fence.lock() else {
        return false;
    };
    fence.accept(route, kind, session, stream).is_ok()
}

/// Answers an RPC: request bytes → reply bytes.
pub type QueryHandler = Arc<dyn Fn(&[u8]) -> Vec<u8> + Send + Sync>;
/// Receives a published sample: (key, payload).
pub type SubCallback = Arc<dyn Fn(&str, &[u8]) + Send + Sync>;

/// Minimal zenoh-style key match: exact, `prefix/**`, or `*` single-segment.
pub fn key_matches(pattern: &str, key: &str) -> bool {
    if pattern == key {
        return true;
    }
    if let Some(prefix) = pattern.strip_suffix("/**") {
        return key == prefix || key.starts_with(&format!("{prefix}/"));
    }
    let pp: Vec<&str> = pattern.split('/').collect();
    let kp: Vec<&str> = key.split('/').collect();
    if pp.len() != kp.len() {
        return false;
    }
    pp.iter().zip(kp.iter()).all(|(p, k)| *p == "*" || p == k)
}

/// A raw data-centric byte bus: queryable RPC + pub/sub streaming.
///
/// This trait performs no NCP decoding, route/session binding, authentication, or
/// replay fencing. Treat every callback payload as untrusted; NCP peers should use
/// [`NcpBusClient`] and [`NcpBusServer`] or apply equivalent explicit gates.
pub trait Bus: Send + Sync {
    /// Register an RPC responder on `key`.
    fn declare_queryable(&self, key: &str, handler: QueryHandler);
    /// Query `key` and return the first reply payload.
    ///
    /// Implementations backed by a byte stream MUST stop reading/copying once
    /// [`crate::bounded_json::MAX_FRAME_BYTES`] is exceeded and return
    /// `NCP-LIMIT-001`; they must not first assemble an unbounded reply `Vec`.
    /// `LocalBus` checks the application-owned handler result before it escapes
    /// the co-process boundary. [`NcpBusClient`] repeats the check defensively.
    fn query(&self, key: &str, payload: &[u8]) -> Result<Vec<u8>, BusError>;
    /// Subscribe to samples on `key` (may contain `*`/`**`).
    fn declare_subscriber(&self, key: &str, callback: SubCallback);
    /// Publish `payload` on `key`.
    fn put(&self, key: &str, payload: &[u8]) -> Result<(), BusError>;
    /// Tear down.
    fn close(&self) {}
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BusError(pub String);

impl std::fmt::Display for BusError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}
impl std::error::Error for BusError {}

/// In-process raw byte bus: models queryable RPC + pub/sub so the decoupled
/// binding is testable and usable same-process (co-process SITL). It intentionally
/// does not make an arbitrary raw publication an accepted NCP frame.
#[derive(Clone, Default)]
pub struct LocalBus {
    queryables: Arc<Mutex<Vec<(String, QueryHandler)>>>,
    subs: Arc<Mutex<Vec<(String, SubCallback)>>>,
}

impl LocalBus {
    pub fn new() -> Self {
        Self::default()
    }
}

impl Bus for LocalBus {
    fn declare_queryable(&self, key: &str, handler: QueryHandler) {
        self.queryables
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push((key.to_string(), handler));
    }

    fn query(&self, key: &str, payload: &[u8]) -> Result<Vec<u8>, BusError> {
        let handler = {
            let qs = self.queryables.lock().unwrap_or_else(|e| e.into_inner());
            qs.iter()
                .find(|(pat, _)| key_matches(pat, key))
                .map(|(_, h)| h.clone())
        };
        let reply = match handler {
            Some(h) => std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| h(payload)))
                .map_err(|_| BusError(format!("queryable for {key:?} panicked")))?,
            None => return Err(BusError(format!("no queryable answers {key:?}"))),
        };
        check_reply_frame_size(&reply)?;
        Ok(reply)
    }

    fn declare_subscriber(&self, key: &str, callback: SubCallback) {
        self.subs
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push((key.to_string(), callback));
    }

    fn put(&self, key: &str, payload: &[u8]) -> Result<(), BusError> {
        let matched: Vec<SubCallback> = {
            let subs = self.subs.lock().unwrap_or_else(|e| e.into_inner());
            subs.iter()
                .filter(|(pat, _)| key_matches(pat, key))
                .map(|(_, cb)| cb.clone())
                .collect()
        };
        let mut panics = 0usize;
        for cb in matched {
            if std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| cb(key, payload))).is_err()
            {
                panics = panics.saturating_add(1);
            }
        }
        if panics > 0 {
            return Err(BusError(format!(
                "{panics} subscriber callback(s) panicked while delivering {key:?}"
            )));
        }
        Ok(())
    }
}

/// NCP client over a `Bus` — talks only to the bus, never a server address.
pub struct NcpBusClient<B: Bus> {
    pub bus: B,
    pub keys: Keys,
    typed_publisher_streams: Mutex<crate::StreamMonotonicityFence>,
}

impl<B: Bus> NcpBusClient<B> {
    pub fn new(bus: B, keys: Keys) -> Self {
        Self {
            bus,
            keys,
            typed_publisher_streams: Mutex::new(crate::StreamMonotonicityFence::default()),
        }
    }

    /// Send an NCP RPC message (already-serialized JSON bytes) and return the
    /// reply JSON bytes.
    pub fn request(&self, message: &[u8]) -> Result<Vec<u8>, BusError> {
        check_bus_keys(&self.keys)?;
        let value = crate::bounded_json::parse_value(message)
            .map_err(|error| BusError(format!("invalid or over-budget NCP RPC JSON: {error}")))?;
        crate::validate(&value)
            .map_err(|error| BusError(format!("invalid NCP RPC request: {error}")))?;
        let kind = crate::message_kind(&value)
            .expect("validated NCP message always carries a string kind");
        let key = self
            .keys
            .rpc_for_kind(kind)
            .map_err(|error| BusError(format!("cannot route {kind:?}: {error}")))?;
        let session_id = value
            .get("session_id")
            .and_then(serde_json::Value::as_str)
            .expect("validated lifecycle request carries session_id");
        let reply = self.bus.query(&key, message)?;
        check_reply_frame_size(&reply)?;
        let validated = crate::validate_rpc_reply_for(kind, session_id, &reply)
            .map_err(|error| BusError(bounded_diagnostic(format_args!("{error}"))))?;
        if crate::message_kind(&validated) == Some("error") {
            return Err(BusError(bounded_diagnostic(format_args!(
                "NCP error {}: {}",
                validated
                    .get("code")
                    .and_then(serde_json::Value::as_str)
                    .expect("validated ErrorFrame carries code"),
                validated
                    .get("error")
                    .and_then(serde_json::Value::as_str)
                    .expect("validated ErrorFrame carries error")
            ))));
        }
        Ok(reply)
    }

    /// Subscribe to the observation stream for one exact live session incarnation;
    /// `callback` receives only payloads matching both id and generation.
    pub fn subscribe_observations(
        &self,
        session_id: &str,
        session: &crate::SessionRef,
        callback: SubCallback,
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        check_live_session(session)?;
        let key = self.keys.try_observation(session_id).map_err(key_error)?;
        let expected_route = key.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = Arc::new(Mutex::new(crate::StreamMonotonicityFence::default()));
        self.bus.declare_subscriber(
            &key,
            Arc::new(move |key, payload| {
                if key != expected_route {
                    return;
                }
                let Ok(frame) = crate::decode_observation_plane_payload_for(
                    &expected_session_id,
                    &expected_session,
                    payload,
                ) else {
                    return;
                };
                if !accept_subscriber_stream(
                    &stream_fence,
                    &expected_route,
                    "observation_frame",
                    &expected_session,
                    &frame.stream,
                ) {
                    return;
                }
                callback(key, payload);
            }),
        );
        Ok(())
    }

    /// Subscribe to the command (action) plane for one exact live session. Even
    /// ESTOP is fenced before callback/latch mutation.
    pub fn subscribe_commands(
        &self,
        session_id: &str,
        session: &crate::SessionRef,
        callback: SubCallback,
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        check_live_session(session)?;
        let key = self.keys.try_command(session_id).map_err(key_error)?;
        let expected_route = key.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = Arc::new(Mutex::new(crate::StreamMonotonicityFence::default()));
        self.bus.declare_subscriber(
            &key,
            Arc::new(move |key, payload| {
                if key != expected_route {
                    return;
                }
                let Ok(frame) = crate::decode_command_plane_payload_for(
                    &expected_session_id,
                    &expected_session,
                    payload,
                ) else {
                    return;
                };
                if !accept_subscriber_stream(
                    &stream_fence,
                    &expected_route,
                    "command_frame",
                    &expected_session,
                    &frame.stream,
                ) {
                    return;
                }
                callback(key, payload);
            }),
        );
        Ok(())
    }

    /// Publish a `SensorFrame` for one exact live session incarnation.
    pub fn put_sensor(
        &self,
        session_id: &str,
        session: &crate::SessionRef,
        payload: &[u8],
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        check_live_session(session)?;
        let key = self.keys.try_sensor(session_id).map_err(key_error)?;
        let frame = crate::decode_sensor_plane_payload_for(session_id, session, payload)
            .map_err(|error| BusError(format!("refusing sensor publish: {error}")))?;
        accept_publisher_stream(
            &self.typed_publisher_streams,
            &key,
            "sensor_frame",
            session,
            &frame.stream,
        )?;
        self.bus.put(&key, payload)
    }
}

/// Serve NCP RPC over a `Bus`: a queryable answers Open/Step/Run/Close by
/// delegating to `handler` (e.g. the NCP gateway's `handler` forwards to a
/// backend's `SessionService.handle_json`).
pub struct NcpBusServer<B: Bus> {
    pub bus: B,
    pub keys: Keys,
    typed_publisher_streams: Mutex<crate::StreamMonotonicityFence>,
}

impl<B: Bus> NcpBusServer<B> {
    pub fn new(bus: B, keys: Keys) -> Self {
        Self {
            bus,
            keys,
            typed_publisher_streams: Mutex::new(crate::StreamMonotonicityFence::default()),
        }
    }

    /// Register the RPC queryable. `handler` maps request JSON bytes → reply
    /// JSON bytes.
    pub fn serve_rpc(&self, handler: QueryHandler) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        for request_kind in crate::keys::RPC_REQUEST_KINDS {
            let expected_kind = (*request_kind).to_owned();
            let key = self
                .keys
                .rpc_for_kind(request_kind)
                .expect("RPC_REQUEST_KINDS contains only routable kinds");
            let handler = handler.clone();
            self.bus.declare_queryable(
                &key,
                Arc::new(move |payload| {
                    let parsed = crate::bounded_json::parse_value(payload).ok();
                    let session_id = parsed
                        .as_ref()
                        .and_then(|value| value.get("session_id"))
                        .and_then(serde_json::Value::as_str)
                        .filter(|value| crate::valid_id_segment(value))
                        .map(str::to_owned);
                    let parsed_session = parsed
                        .as_ref()
                        .and_then(|value| value.get("session"))
                        .and_then(|value| {
                            serde_json::from_value::<crate::SessionRef>(value.clone()).ok()
                        })
                        .filter(|value| crate::is_canonical_uuid_v4(&value.generation));
                    let (request, session) =
                        match crate::validate_rpc_request_for(&expected_kind, payload) {
                            Ok(request) => request,
                            Err(error) => {
                                return bounded_rpc_error_payload(
                                    error.rpc_error_code(),
                                    format_args!("invalid {expected_kind} request: {error}"),
                                    session_id,
                                    parsed_session,
                                    Some(expected_kind.clone()),
                                );
                            }
                        };
                    let request_session = request
                        .get("session")
                        .and_then(|value| {
                            serde_json::from_value::<crate::SessionRef>(value.clone()).ok()
                        })
                        .filter(|value| crate::is_canonical_uuid_v4(&value.generation));
                    let reply = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        handler(payload)
                    })) {
                        Ok(reply) => reply,
                        Err(_) => {
                            return bounded_rpc_error_payload(
                                crate::RpcErrorCode::ContainedInternalFailure,
                                "RPC handler panicked",
                                Some(session),
                                request_session,
                                Some(expected_kind.clone()),
                            )
                        }
                    };
                    match crate::validate_rpc_reply_for(&expected_kind, &session, &reply) {
                        Ok(_) => reply,
                        Err(error) => bounded_rpc_error_payload(
                            crate::RpcErrorCode::ContainedInternalFailure,
                            error,
                            Some(session),
                            request_session,
                            Some(expected_kind.clone()),
                        ),
                    }
                }),
            );
        }
        Ok(())
    }

    /// Publish an observation frame on one exact live session's observation key.
    pub fn publish_observation(
        &self,
        session_id: &str,
        session: &crate::SessionRef,
        payload: &[u8],
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        check_live_session(session)?;
        let key = self.keys.try_observation(session_id).map_err(key_error)?;
        let frame = crate::decode_observation_plane_payload_for(session_id, session, payload)
            .map_err(|error| BusError(format!("refusing observation publish: {error}")))?;
        accept_publisher_stream(
            &self.typed_publisher_streams,
            &key,
            "observation_frame",
            session,
            &frame.stream,
        )?;
        self.bus.put(&key, payload)
    }

    /// Publish a complete command frame on one exact live session's action plane.
    pub fn publish_command(
        &self,
        session_id: &str,
        session: &crate::SessionRef,
        payload: &[u8],
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        check_live_session(session)?;
        let key = self.keys.try_command(session_id).map_err(key_error)?;
        let frame = crate::decode_command_plane_payload_for(session_id, session, payload)
            .map_err(|error| BusError(format!("refusing command publish: {error}")))?;
        accept_publisher_stream(
            &self.typed_publisher_streams,
            &key,
            "command_frame",
            session,
            &frame.stream,
        )?;
        self.bus.put(&key, payload)
    }

    /// Subscribe to the sensor plane for one exact live session incarnation.
    pub fn subscribe_sensors(
        &self,
        session_id: &str,
        session: &crate::SessionRef,
        callback: SubCallback,
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        check_live_session(session)?;
        let key = self.keys.try_sensor(session_id).map_err(key_error)?;
        let expected_route = key.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = Arc::new(Mutex::new(crate::StreamMonotonicityFence::default()));
        self.bus.declare_subscriber(
            &key,
            Arc::new(move |key, payload| {
                if key != expected_route {
                    return;
                }
                let Ok(frame) = crate::decode_sensor_plane_payload_for(
                    &expected_session_id,
                    &expected_session,
                    payload,
                ) else {
                    return;
                };
                if !accept_subscriber_stream(
                    &stream_fence,
                    &expected_route,
                    "sensor_frame",
                    &expected_session,
                    &frame.stream,
                ) {
                    return;
                }
                callback(key, payload);
            }),
        );
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};

    const OPEN_SESSION: &[u8] = include_bytes!("../testdata/conformance/vectors/open_session.json");
    const SESSION_OPENED: &[u8] =
        include_bytes!("../testdata/conformance/vectors/session_opened.json");
    const CLOSE_SESSION: &[u8] =
        include_bytes!("../testdata/conformance/vectors/close_session.json");
    const SESSION_CLOSED: &[u8] =
        include_bytes!("../testdata/conformance/vectors/session_closed.json");
    const SENSOR_FRAME: &[u8] = include_bytes!("../testdata/conformance/vectors/sensor_frame.json");
    const COMMAND_FRAME: &[u8] =
        include_bytes!("../testdata/conformance/vectors/command_frame.json");
    const OBSERVATION_FRAME: &[u8] =
        include_bytes!("../testdata/conformance/vectors/observation_frame.json");
    const RESTARTED_STREAM_EPOCH: &str = "40000000-0000-4000-8000-000000000001";

    fn live_session() -> crate::SessionRef {
        crate::SessionRef {
            generation: "293279f3-d459-4bfd-aeeb-604799e96925".into(),
        }
    }

    fn sensor_frame_at(epoch: &str, seq: i64) -> Vec<u8> {
        let mut frame: serde_json::Value = serde_json::from_slice(SENSOR_FRAME).unwrap();
        frame["stream"]["epoch"] = epoch.into();
        frame["stream"]["seq"] = seq.into();
        serde_json::to_vec(&frame).unwrap()
    }

    #[test]
    fn key_matching() {
        assert!(key_matches("a/b", "a/b"));
        assert!(key_matches("a/**", "a"));
        assert!(key_matches("a/**", "a/b/c"));
        assert!(key_matches("a/*/c", "a/b/c"));
        assert!(!key_matches("a/*/c", "a/b/d"));
        assert!(!key_matches("a/b", "a/b/c"));
    }

    #[test]
    fn multi_uav_varying_entities_route_with_no_crosstalk() {
        use crate::keys::Keys;
        let bus = LocalBus::new();
        let k = Keys::default();

        // A controller subscribes to each UAV's whole sensor set (any count) via
        // the per-UAV sensor wildcard; the sample key identifies which sensor.
        let sensors = Arc::new(Mutex::new(Vec::<String>::new()));
        for uav in ["uav1", "uav2", "uav3"] {
            let sink = sensors.clone();
            bus.declare_subscriber(
                &k.sensor_glob(uav),
                Arc::new(move |key: &str, _p: &[u8]| sink.lock().unwrap().push(key.to_string())),
            );
        }
        // Plant-side per-actuator subscribers (varying counts per UAV).
        let cmds = Arc::new(Mutex::new(Vec::<(String, String)>::new()));
        for (uav, act) in [("uav1", "cmd_vel"), ("uav2", "gimbal"), ("uav3", "rotor2")] {
            let sink = cmds.clone();
            let label = format!("{uav}/{act}");
            bus.declare_subscriber(
                &k.command_named(uav, act),
                Arc::new(move |_key: &str, p: &[u8]| {
                    sink.lock()
                        .unwrap()
                        .push((label.clone(), String::from_utf8_lossy(p).into_owned()))
                }),
            );
        }

        // Varying sensor counts: uav1=3, uav2=1, uav3=2.
        for (uav, name) in [
            ("uav1", "imu"),
            ("uav1", "cam"),
            ("uav1", "lidar"),
            ("uav2", "imu"),
            ("uav3", "imu"),
            ("uav3", "gps"),
        ] {
            bus.put(&k.sensor_named(uav, name), b"x").unwrap();
        }
        // Commands to specific actuators (rotor0 has no subscriber).
        bus.put(&k.command_named("uav3", "rotor2"), b"R2").unwrap();
        bus.put(&k.command_named("uav1", "cmd_vel"), b"V1").unwrap();
        bus.put(&k.command_named("uav3", "rotor0"), b"R0").unwrap();

        let s = sensors.lock().unwrap();
        let count = |u: &str| {
            s.iter()
                .filter(|key| key.contains(&format!("/session/{u}/")))
                .count()
        };
        assert_eq!(
            (count("uav1"), count("uav2"), count("uav3")),
            (3, 1, 2),
            "each UAV's sensor-glob receives exactly its own varying sensor set"
        );

        let c = cmds.lock().unwrap();
        assert!(c.iter().any(|(l, v)| l == "uav3/rotor2" && v == "R2"));
        assert!(c.iter().any(|(l, v)| l == "uav1/cmd_vel" && v == "V1"));
        assert!(
            !c.iter().any(|(_, v)| v == "R0"),
            "rotor0 has no subscriber -> not delivered (no crosstalk)"
        );
    }

    #[test]
    fn local_bus_rpc_and_pubsub() {
        let bus = LocalBus::new();
        bus.declare_queryable(
            "ncp/rpc",
            Arc::new(|p: &[u8]| {
                let mut v = b"echo:".to_vec();
                v.extend_from_slice(p);
                v
            }),
        );
        let reply = bus.query("ncp/rpc", b"hi").unwrap();
        assert_eq!(reply, b"echo:hi");

        let seen = Arc::new(Mutex::new(Vec::<String>::new()));
        let seen2 = seen.clone();
        bus.declare_subscriber(
            "ncp/session/s1/**",
            Arc::new(move |_k: &str, p: &[u8]| {
                seen2
                    .lock()
                    .unwrap()
                    .push(String::from_utf8_lossy(p).into_owned());
            }),
        );
        bus.put("ncp/session/s1/observation", b"obs").unwrap();
        bus.put("ncp/session/s2/observation", b"nope").unwrap();
        assert_eq!(&*seen.lock().unwrap(), &vec!["obs".to_string()]);
    }

    #[test]
    fn local_bus_query_rejects_an_oversized_reply() {
        let bus = LocalBus::new();
        bus.declare_queryable(
            "ncp/rpc/hostile",
            Arc::new(|_| vec![b'x'; crate::bounded_json::MAX_FRAME_BYTES + 1]),
        );

        let error = bus.query("ncp/rpc/hostile", b"request").unwrap_err();

        assert!(error.0.contains("NCP-LIMIT-001"), "{error}");
    }

    #[test]
    fn rpc_diagnostics_are_truncated_without_losing_utf8_boundaries() {
        let hostile = "🧠".repeat(MAX_RPC_DIAGNOSTIC_BYTES);

        let diagnostic = bounded_diagnostic(format_args!("handler reply: {hostile}"));

        assert!(diagnostic.len() <= MAX_RPC_DIAGNOSTIC_BYTES);
        assert!(diagnostic.ends_with("..."));
    }

    #[test]
    fn local_bus_contains_callback_and_queryable_panics() {
        let bus = LocalBus::new();
        bus.declare_queryable("ncp/rpc/fault", Arc::new(|_| panic!("query fault")));
        let error = bus.query("ncp/rpc/fault", b"request").unwrap_err();
        assert!(error.0.contains("panicked"), "{error}");

        let delivered = Arc::new(AtomicUsize::new(0));
        bus.declare_subscriber("ncp/session/s/sensor", Arc::new(|_, _| panic!("sub fault")));
        let sink = delivered.clone();
        bus.declare_subscriber(
            "ncp/session/s/sensor",
            Arc::new(move |_, _| {
                sink.fetch_add(1, Ordering::Relaxed);
            }),
        );
        let error = bus.put("ncp/session/s/sensor", b"sample").unwrap_err();
        assert!(error.0.contains("1 subscriber"), "{error}");
        assert_eq!(delivered.load(Ordering::Relaxed), 1);
        // The failing callback is isolated: it does not poison bus state or stop
        // delivery to healthy subscribers on subsequent samples.
        assert!(bus.put("ncp/session/s/sensor", b"next").is_err());
        assert_eq!(delivered.load(Ordering::Relaxed), 2);
    }

    #[test]
    fn ncp_bus_rpc_binds_selector_request_and_reply() {
        let bus = LocalBus::new();
        let keys = Keys::default();
        let server = NcpBusServer::new(bus.clone(), keys.clone());
        server
            .serve_rpc(Arc::new(|payload| {
                let request: serde_json::Value = serde_json::from_slice(payload).unwrap();
                match crate::message_kind(&request).unwrap() {
                    "open_session" => SESSION_OPENED.to_vec(),
                    "close_session" => SESSION_CLOSED.to_vec(),
                    other => panic!("unexpected request kind {other}"),
                }
            }))
            .unwrap();

        let client = NcpBusClient::new(bus.clone(), keys.clone());
        let reply = client.request(OPEN_SESSION).unwrap();
        let reply: serde_json::Value = serde_json::from_slice(&reply).unwrap();
        assert_eq!(crate::message_kind(&reply), Some("session_opened"));

        // A caller with authority for only `open_session` cannot smuggle a
        // different lifecycle request through that selector.
        let error = bus
            .query(&keys.rpc_for_kind("open_session").unwrap(), CLOSE_SESSION)
            .unwrap();
        let error: serde_json::Value = serde_json::from_slice(&error).unwrap();
        crate::validate(&error).unwrap();
        assert_eq!(crate::message_kind(&error), Some("error"));
        assert_eq!(error["code"], "NCP-WIRE-001");
        assert_eq!(error["request_kind"], "open_session");
        assert_eq!(error["session_id"], "vec-open-1");
        assert_eq!(
            error["session"]["generation"],
            "293279f3-d459-4bfd-aeeb-604799e96925"
        );
    }

    #[test]
    fn ncp_bus_rpc_preserves_bounded_json_error_codes() {
        let bus = LocalBus::new();
        let keys = Keys::default();
        let calls = Arc::new(AtomicUsize::new(0));
        let handler_calls = calls.clone();
        NcpBusServer::new(bus.clone(), keys.clone())
            .serve_rpc(Arc::new(move |_| {
                handler_calls.fetch_add(1, Ordering::Relaxed);
                SESSION_OPENED.to_vec()
            }))
            .unwrap();
        let selector = keys.rpc_for_kind("open_session").unwrap();

        let assert_code = |payload: &[u8], expected: &str| {
            let reply = bus.query(&selector, payload).unwrap();
            let reply: serde_json::Value = serde_json::from_slice(&reply).unwrap();
            crate::validate(&reply).unwrap();
            assert_eq!(reply["code"], expected);
            assert!(reply["session_id"].is_null());
            assert!(reply["session"].is_null());
        };

        assert_code(
            br#"{"kind":"open_session","kind":"open_session"}"#,
            "NCP-LIMIT-007",
        );
        let too_deep = format!(
            "{}0{}",
            "[".repeat(crate::bounded_json::MAX_NESTING_DEPTH + 1),
            "]".repeat(crate::bounded_json::MAX_NESTING_DEPTH + 1)
        );
        assert_code(too_deep.as_bytes(), "NCP-LIMIT-002");
        let too_large = vec![b' '; crate::bounded_json::MAX_FRAME_BYTES + 1];
        assert_code(&too_large, "NCP-LIMIT-001");
        assert_code(br#"{"#, "NCP-LIMIT-009");
        assert_code(br#"{}"#, "NCP-WIRE-001");
        assert_eq!(calls.load(Ordering::Relaxed), 0);
    }

    #[test]
    fn ncp_bus_rpc_contains_handler_faults_and_bad_replies() {
        let wrong_reply_bus = LocalBus::new();
        let server = NcpBusServer::new(wrong_reply_bus.clone(), Keys::default());
        server
            .serve_rpc(Arc::new(|_| SESSION_CLOSED.to_vec()))
            .unwrap();
        let client = NcpBusClient::new(wrong_reply_bus, Keys::default());
        let error = client.request(OPEN_SESSION).unwrap_err();
        assert!(error.0.contains("reply kind mismatch"), "{error}");
        assert!(error.0.contains("NCP-INTERNAL-001"), "{error}");

        let panic_bus = LocalBus::new();
        let server = NcpBusServer::new(panic_bus.clone(), Keys::default());
        server
            .serve_rpc(Arc::new(|_| panic!("hostile handler panic")))
            .unwrap();
        let client = NcpBusClient::new(panic_bus, Keys::default());
        let error = client.request(OPEN_SESSION).unwrap_err();
        assert!(error.0.contains("handler panicked"), "{error}");
        assert!(error.0.contains("NCP-INTERNAL-001"), "{error}");
    }

    #[test]
    fn ncp_bus_rpc_contains_an_oversized_handler_reply() {
        let bus = LocalBus::new();
        let server = NcpBusServer::new(bus.clone(), Keys::default());
        server
            .serve_rpc(Arc::new(|_| {
                vec![b'x'; crate::bounded_json::MAX_FRAME_BYTES + 1]
            }))
            .unwrap();
        let client = NcpBusClient::new(bus, Keys::default());

        let error = client.request(OPEN_SESSION).unwrap_err();

        assert!(error.0.contains("NCP-INTERNAL-001"), "{error}");
        assert!(error.0.contains("NCP-LIMIT-001"), "{error}");
        assert!(error.0.len() <= MAX_RPC_DIAGNOSTIC_BYTES);
    }

    #[test]
    fn ncp_bus_publishers_validate_before_delivery() {
        let bus = LocalBus::new();
        let keys = Keys::default();
        let client = NcpBusClient::new(bus.clone(), keys.clone());
        let server = NcpBusServer::new(bus, keys);
        let sensors = Arc::new(AtomicUsize::new(0));
        let commands = Arc::new(AtomicUsize::new(0));
        let observations = Arc::new(AtomicUsize::new(0));
        let live_session = live_session();

        let seen = sensors.clone();
        server
            .subscribe_sensors(
                "vec-open-1",
                &live_session,
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();
        let seen = commands.clone();
        client
            .subscribe_commands(
                "vec-open-1",
                &live_session,
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();
        let seen = observations.clone();
        client
            .subscribe_observations(
                "vec-open-1",
                &live_session,
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();

        client
            .put_sensor("vec-open-1", &live_session, SENSOR_FRAME)
            .unwrap();
        server
            .publish_command("vec-open-1", &live_session, COMMAND_FRAME)
            .unwrap();
        server
            .publish_observation("vec-open-1", &live_session, OBSERVATION_FRAME)
            .unwrap();
        assert_eq!(sensors.load(Ordering::Relaxed), 1);
        assert_eq!(commands.load(Ordering::Relaxed), 1);
        assert_eq!(observations.load(Ordering::Relaxed), 1);

        assert!(client
            .put_sensor("vec-open-1", &live_session, SENSOR_FRAME)
            .is_err());
        assert!(server
            .publish_command("vec-open-1", &live_session, COMMAND_FRAME)
            .is_err());
        assert!(server
            .publish_observation("vec-open-1", &live_session, OBSERVATION_FRAME)
            .is_err());

        // Raw bytes can bypass publisher gates, but every exact typed subscriber
        // independently drops the duplicate before invoking application code.
        server
            .bus
            .put(&server.keys.sensor("vec-open-1"), SENSOR_FRAME)
            .unwrap();
        server
            .bus
            .put(&server.keys.command("vec-open-1"), COMMAND_FRAME)
            .unwrap();
        server
            .bus
            .put(&server.keys.observation("vec-open-1"), OBSERVATION_FRAME)
            .unwrap();
        assert_eq!(
            (
                sensors.load(Ordering::Relaxed),
                commands.load(Ordering::Relaxed),
                observations.load(Ordering::Relaxed),
            ),
            (1, 1, 1),
        );

        assert!(client
            .put_sensor("bad/*", &live_session, SENSOR_FRAME)
            .is_err());
        assert!(server
            .publish_command("vec-open-1", &live_session, br#"{"mode":"active"}"#)
            .is_err());
        let mut unstamped: serde_json::Value = serde_json::from_slice(OBSERVATION_FRAME).unwrap();
        unstamped["stream"]["seq"] = 0.into();
        assert!(server
            .publish_observation(
                "vec-open-1",
                &live_session,
                &serde_json::to_vec(&unstamped).unwrap(),
            )
            .is_err());
        let mut wrong_session: serde_json::Value =
            serde_json::from_slice(OBSERVATION_FRAME).unwrap();
        wrong_session["session_id"] = "other-session".into();
        let wrong_observation = serde_json::to_vec(&wrong_session).unwrap();
        assert!(server
            .publish_observation("vec-open-1", &live_session, &wrong_observation)
            .is_err());

        let mut wrong_session: serde_json::Value = serde_json::from_slice(SENSOR_FRAME).unwrap();
        wrong_session["session_id"] = "other-session".into();
        let wrong_sensor = serde_json::to_vec(&wrong_session).unwrap();
        assert!(client
            .put_sensor("vec-open-1", &live_session, &wrong_sensor)
            .is_err());

        let mut wrong_session: serde_json::Value = serde_json::from_slice(COMMAND_FRAME).unwrap();
        wrong_session["session_id"] = "other-session".into();
        let wrong_command = serde_json::to_vec(&wrong_session).unwrap();
        assert!(server
            .publish_command("vec-open-1", &live_session, &wrong_command)
            .is_err());

        // The NCP-aware subscriber boundary also rejects a raw-bus bypass. The
        // generic LocalBus remains intentionally raw for tests/non-NCP traffic.
        server
            .bus
            .put(&server.keys.observation("vec-open-1"), &wrong_observation)
            .unwrap();
        server
            .bus
            .put(&server.keys.sensor("vec-open-1"), &wrong_sensor)
            .unwrap();
        server
            .bus
            .put(&server.keys.command("vec-open-1"), &wrong_command)
            .unwrap();
        server
            .bus
            .put(&server.keys.sensor("vec-open-1"), br#"{}"#)
            .unwrap();
        server
            .bus
            .put(&server.keys.command("vec-open-1"), br#"{}"#)
            .unwrap();
        assert_eq!(sensors.load(Ordering::Relaxed), 1);
        assert_eq!(commands.load(Ordering::Relaxed), 1);
        assert_eq!(observations.load(Ordering::Relaxed), 1);

        // ESTOP may omit authority, but it never bypasses the complete envelope or
        // exact live-session binding gate.
        assert!(server
            .publish_command("vec-open-1", &live_session, br#"{"mode":"estop"}"#)
            .is_err());
        let mut estop: serde_json::Value = serde_json::from_slice(COMMAND_FRAME).unwrap();
        estop["mode"] = "estop".into();
        estop["stream"]["seq"] = 8.into();
        estop.as_object_mut().unwrap().remove("authority");
        let estop = serde_json::to_vec(&estop).unwrap();
        server
            .publish_command("vec-open-1", &live_session, &estop)
            .unwrap();
        assert_eq!(commands.load(Ordering::Relaxed), 2);

        let mut stale: serde_json::Value = serde_json::from_slice(&estop).unwrap();
        stale["session"]["generation"] = "10000000-0000-4000-8000-000000000003".into();
        let stale = serde_json::to_vec(&stale).unwrap();
        assert!(server
            .publish_command("vec-open-1", &live_session, &stale)
            .is_err());
        server
            .bus
            .put(&server.keys.command("vec-open-1"), &stale)
            .unwrap();
        let mut missing_generation: serde_json::Value = serde_json::from_slice(&estop).unwrap();
        missing_generation
            .as_object_mut()
            .unwrap()
            .remove("session");
        server
            .bus
            .put(
                &server.keys.command("vec-open-1"),
                &serde_json::to_vec(&missing_generation).unwrap(),
            )
            .unwrap();
        assert_eq!(
            commands.load(Ordering::Relaxed),
            2,
            "raw-bypass stale-generation ESTOP must not reach the callback/latch"
        );
    }

    #[test]
    fn typed_sensor_publisher_rejects_reorder_duplicate_and_foreign_epoch() {
        let bus = LocalBus::new();
        let keys = Keys::default();
        let publisher = NcpBusClient::new(bus, keys);
        let live = live_session();
        let epoch = serde_json::from_slice::<serde_json::Value>(SENSOR_FRAME).unwrap()["stream"]
            ["epoch"]
            .as_str()
            .unwrap()
            .to_owned();

        publisher
            .put_sensor("vec-open-1", &live, &sensor_frame_at(&epoch, 2))
            .unwrap();
        let reordered = publisher
            .put_sensor("vec-open-1", &live, &sensor_frame_at(&epoch, 1))
            .unwrap_err();
        let duplicate = publisher
            .put_sensor("vec-open-1", &live, &sensor_frame_at(&epoch, 2))
            .unwrap_err();
        let foreign = publisher
            .put_sensor(
                "vec-open-1",
                &live,
                &sensor_frame_at(RESTARTED_STREAM_EPOCH, 3),
            )
            .unwrap_err();

        assert!(reordered.0.contains("not strictly greater"), "{reordered}");
        assert!(duplicate.0.contains("not strictly greater"), "{duplicate}");
        assert!(foreign.0.contains("foreign epoch"), "{foreign}");
    }

    #[test]
    fn fresh_typed_sensor_publisher_accepts_restarted_epoch() {
        let bus = LocalBus::new();
        let keys = Keys::default();
        let retired = NcpBusClient::new(bus.clone(), keys.clone());
        let live = live_session();
        let first_epoch = serde_json::from_slice::<serde_json::Value>(SENSOR_FRAME).unwrap()
            ["stream"]["epoch"]
            .as_str()
            .unwrap()
            .to_owned();
        retired
            .put_sensor("vec-open-1", &live, &sensor_frame_at(&first_epoch, 2))
            .unwrap();
        let fresh = NcpBusClient::new(bus, keys);

        assert!(fresh
            .put_sensor(
                "vec-open-1",
                &live,
                &sensor_frame_at(RESTARTED_STREAM_EPOCH, 1),
            )
            .is_ok());
    }

    #[test]
    fn typed_sensor_subscriber_fences_stream_until_redeclaration() {
        let bus = LocalBus::new();
        let keys = Keys::default();
        let server = NcpBusServer::new(bus.clone(), keys.clone());
        let live = live_session();
        let first_epoch = serde_json::from_slice::<serde_json::Value>(SENSOR_FRAME).unwrap()
            ["stream"]["epoch"]
            .as_str()
            .unwrap()
            .to_owned();
        let original_seen = Arc::new(AtomicUsize::new(0));
        let seen = original_seen.clone();
        server
            .subscribe_sensors(
                "vec-open-1",
                &live,
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();
        let route = keys.sensor("vec-open-1");

        bus.put(&route, &sensor_frame_at(&first_epoch, 2)).unwrap();
        bus.put(&route, &sensor_frame_at(&first_epoch, 1)).unwrap();
        bus.put(&route, &sensor_frame_at(&first_epoch, 2)).unwrap();
        bus.put(&route, &sensor_frame_at(RESTARTED_STREAM_EPOCH, 3))
            .unwrap();

        let restarted_seen = Arc::new(AtomicUsize::new(0));
        let seen = restarted_seen.clone();
        server
            .subscribe_sensors(
                "vec-open-1",
                &live,
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();
        bus.put(&route, &sensor_frame_at(RESTARTED_STREAM_EPOCH, 3))
            .unwrap();

        assert_eq!(
            (
                original_seen.load(Ordering::Relaxed),
                restarted_seen.load(Ordering::Relaxed),
            ),
            (1, 1),
            "the original declaration rejects replay/restart while the fresh declaration accepts its first epoch"
        );
    }
}
