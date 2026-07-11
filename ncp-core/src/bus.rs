//! Transport-neutral **bus** abstraction: RPC via a *queryable* on a key
//! expression, streaming via *pub/sub* on per-session keys. Peers address data
//! (`{realm}/**`), not server addresses — location-transparent, many-to-many.
//!
//! `ncp-core` ships a synchronous `Bus` trait plus an in-process `LocalBus`
//! (deterministic, dependency-free — for tests and co-process use) and the
//! generic `NcpBusClient` / `NcpBusServer` that carry NCP over any `Bus`. The
//! Zenoh binding lives in the `ncp-zenoh` crate. Mirrors `backend/neurocontrol/
//! bus.py`.

use crate::keys::Keys;
use std::sync::{Arc, Mutex};

fn check_bus_keys(keys: &Keys) -> Result<(), BusError> {
    keys.validate()
        .map_err(|error| BusError(format!("refusing invalid NCP realm: {error}")))
}

fn key_error(error: crate::InvalidKeySegment) -> BusError {
    BusError(error.to_string())
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

/// A data-centric bus: queryable RPC + pub/sub streaming.
pub trait Bus: Send + Sync {
    /// Register an RPC responder on `key`.
    fn declare_queryable(&self, key: &str, handler: QueryHandler);
    /// Query `key` and return the first reply payload.
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

/// In-process bus: models queryable RPC + pub/sub so the decoupled binding is
/// testable and usable same-process (co-process SITL).
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
        match handler {
            Some(h) => std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| h(payload)))
                .map_err(|_| BusError(format!("queryable for {key:?} panicked"))),
            None => Err(BusError(format!("no queryable answers {key:?}"))),
        }
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
}

impl<B: Bus> NcpBusClient<B> {
    pub fn new(bus: B, keys: Keys) -> Self {
        Self { bus, keys }
    }

    /// Send an NCP RPC message (already-serialized JSON bytes) and return the
    /// reply JSON bytes.
    pub fn request(&self, message: &[u8]) -> Result<Vec<u8>, BusError> {
        check_bus_keys(&self.keys)?;
        let value: serde_json::Value = serde_json::from_slice(message)
            .map_err(|error| BusError(format!("invalid NCP RPC JSON: {error}")))?;
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
        let validated = crate::validate_rpc_reply_for(kind, session_id, &reply)
            .map_err(|error| BusError(error.to_string()))?;
        if crate::message_kind(&validated) == Some("error") {
            return Err(BusError(format!(
                "NCP error: {}",
                validated
                    .get("error")
                    .and_then(serde_json::Value::as_str)
                    .expect("validated ErrorFrame carries error")
            )));
        }
        Ok(reply)
    }

    /// Subscribe to the observation stream for a session; `callback` gets raw
    /// JSON payloads.
    pub fn subscribe_observations(
        &self,
        session_id: &str,
        callback: SubCallback,
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        let key = self.keys.try_observation(session_id).map_err(key_error)?;
        let expected_session = session_id.to_owned();
        self.bus.declare_subscriber(
            &key,
            Arc::new(move |key, payload| {
                if crate::validate_observation_plane_payload_for(&expected_session, payload).is_ok()
                {
                    callback(key, payload);
                }
            }),
        );
        Ok(())
    }

    /// Subscribe to the command (action) plane — what a plant does to receive
    /// `CommandFrame`s.
    pub fn subscribe_commands(
        &self,
        session_id: &str,
        callback: SubCallback,
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        let key = self.keys.try_command(session_id).map_err(key_error)?;
        self.bus.declare_subscriber(
            &key,
            Arc::new(move |key, payload| {
                if crate::validate_command_plane_payload(payload).is_ok() {
                    callback(key, payload);
                }
            }),
        );
        Ok(())
    }

    /// Publish a `SensorFrame` (perception plane) — what a plant does each tick.
    pub fn put_sensor(&self, session_id: &str, payload: &[u8]) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        let key = self.keys.try_sensor(session_id).map_err(key_error)?;
        crate::validate_sensor_plane_payload(payload)
            .map_err(|error| BusError(format!("refusing sensor publish: {error}")))?;
        self.bus.put(&key, payload)
    }
}

/// Serve NCP RPC over a `Bus`: a queryable answers Open/Step/Run/Close by
/// delegating to `handler` (e.g. the NCP gateway's `handler` forwards to a
/// backend's `SessionService.handle_json`).
pub struct NcpBusServer<B: Bus> {
    pub bus: B,
    pub keys: Keys,
}

impl<B: Bus> NcpBusServer<B> {
    pub fn new(bus: B, keys: Keys) -> Self {
        Self { bus, keys }
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
                    let parsed = serde_json::from_slice::<serde_json::Value>(payload).ok();
                    let session_id = parsed
                        .as_ref()
                        .and_then(|value| value.get("session_id"))
                        .and_then(serde_json::Value::as_str)
                        .filter(|value| crate::valid_id_segment(value))
                        .map(str::to_owned);
                    let Ok((_request, session)) =
                        crate::validate_rpc_request_for(&expected_kind, payload)
                    else {
                        return crate::rpc_error_payload(
                            format!("invalid {expected_kind} request"),
                            session_id,
                            Some(expected_kind.clone()),
                        );
                    };
                    let reply = match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                        handler(payload)
                    })) {
                        Ok(reply) => reply,
                        Err(_) => {
                            return crate::rpc_error_payload(
                                "RPC handler panicked",
                                Some(session),
                                Some(expected_kind.clone()),
                            )
                        }
                    };
                    match crate::validate_rpc_reply_for(&expected_kind, &session, &reply) {
                        Ok(_) => reply,
                        Err(error) => crate::rpc_error_payload(
                            error.to_string(),
                            Some(session),
                            Some(expected_kind.clone()),
                        ),
                    }
                }),
            );
        }
        Ok(())
    }

    /// Publish an observation frame (JSON bytes) on a session's observation key.
    pub fn publish_observation(&self, session_id: &str, payload: &[u8]) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        let key = self.keys.try_observation(session_id).map_err(key_error)?;
        crate::validate_observation_plane_payload_for(session_id, payload)
            .map_err(|error| BusError(format!("refusing observation publish: {error}")))?;
        self.bus.put(&key, payload)
    }

    /// Publish a command frame (JSON bytes) on a session's action plane.
    pub fn publish_command(&self, session_id: &str, payload: &[u8]) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        let key = self.keys.try_command(session_id).map_err(key_error)?;
        crate::validate_command_plane_payload(payload)
            .map_err(|error| BusError(format!("refusing command publish: {error}")))?;
        self.bus.put(&key, payload)
    }

    /// Subscribe to the sensor (perception) plane for a session.
    pub fn subscribe_sensors(
        &self,
        session_id: &str,
        callback: SubCallback,
    ) -> Result<(), BusError> {
        check_bus_keys(&self.keys)?;
        let key = self.keys.try_sensor(session_id).map_err(key_error)?;
        self.bus.declare_subscriber(
            &key,
            Arc::new(move |key, payload| {
                if crate::validate_sensor_plane_payload(payload).is_ok() {
                    callback(key, payload);
                }
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
        assert_eq!(error["request_kind"], "open_session");
        assert_eq!(error["session_id"], "vec-open-1");
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

        let panic_bus = LocalBus::new();
        let server = NcpBusServer::new(panic_bus.clone(), Keys::default());
        server
            .serve_rpc(Arc::new(|_| panic!("hostile handler panic")))
            .unwrap();
        let client = NcpBusClient::new(panic_bus, Keys::default());
        let error = client.request(OPEN_SESSION).unwrap_err();
        assert!(error.0.contains("handler panicked"), "{error}");
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

        let seen = sensors.clone();
        server
            .subscribe_sensors(
                "vec-open-1",
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();
        let seen = commands.clone();
        client
            .subscribe_commands(
                "vec-open-1",
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();
        let seen = observations.clone();
        client
            .subscribe_observations(
                "vec-open-1",
                Arc::new(move |_, _| {
                    seen.fetch_add(1, Ordering::Relaxed);
                }),
            )
            .unwrap();

        client.put_sensor("vec-open-1", SENSOR_FRAME).unwrap();
        server.publish_command("vec-open-1", COMMAND_FRAME).unwrap();
        server
            .publish_observation("vec-open-1", OBSERVATION_FRAME)
            .unwrap();
        assert_eq!(sensors.load(Ordering::Relaxed), 1);
        assert_eq!(commands.load(Ordering::Relaxed), 1);
        assert_eq!(observations.load(Ordering::Relaxed), 1);

        assert!(client.put_sensor("bad/*", SENSOR_FRAME).is_err());
        assert!(server
            .publish_command("vec-open-1", br#"{"mode":"active"}"#)
            .is_err());
        let mut unstamped: serde_json::Value = serde_json::from_slice(OBSERVATION_FRAME).unwrap();
        unstamped["stream"]["seq"] = 0.into();
        assert!(server
            .publish_observation("vec-open-1", &serde_json::to_vec(&unstamped).unwrap())
            .is_err());
        let mut wrong_session: serde_json::Value =
            serde_json::from_slice(OBSERVATION_FRAME).unwrap();
        wrong_session["session_id"] = "other-session".into();
        let wrong_session = serde_json::to_vec(&wrong_session).unwrap();
        assert!(server
            .publish_observation("vec-open-1", &wrong_session)
            .is_err());

        // The NCP-aware subscriber boundary also rejects a raw-bus bypass. The
        // generic LocalBus remains intentionally raw for tests/non-NCP traffic.
        server
            .bus
            .put(&server.keys.observation("vec-open-1"), &wrong_session)
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

        // ESTOP bypasses the normal wire envelope gate by design: even a stale
        // or partially decoded peer must retain a way to command no actuation.
        server
            .publish_command("vec-open-1", br#"{"mode":"estop"}"#)
            .unwrap();
        assert_eq!(commands.load(Ordering::Relaxed), 2);
    }
}
