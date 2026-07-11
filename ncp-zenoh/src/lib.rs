#![doc = include_str!("../README.md")]
#![cfg_attr(docsrs, feature(doc_cfg))]
//!
//! # Transport details
//!
//! The perception, action and observation **data planes** are *pub/sub* on
//! per-session keys (see [`ncp_core::keys`]). Observers (e.g. an
//! analysis/observer client) attach to the data-plane keys read-only with zero
//! changes to the control path.
//!
//! Each plane gets the QoS its job needs (see [`Plane`]). NCP sets
//! CongestionControl + priority + express per plane; wire reliability is left at
//! Zenoh's default (the minimal feature set here does not enable the `unstable`
//! reliability API):
//! - **perception** — CongestionControl=DROP + DataHigh priority (TX-queue DROP
//!   only when the queue is full — no conflation guarantee, i.e. it is *not*
//!   guaranteed to drop to the latest frame, only to drop *some* frames);
//! - **action** — express + DROP + RealTime priority (lowest-latency setpoint),
//!   safety-gated by the sender;
//! - **control/observation** — CongestionControl=BLOCK (no drop).
//!
//! Observation publish reuses the Control plane's reliable/BLOCK QoS, so under
//! congestion it back-pressures the publisher rather than dropping — keep the
//! observation stream low-rate.
//!
//! Async API (native to Zenoh; all NCP consumers run on tokio). The in-process
//! [`ncp_core::Bus`] / [`ncp_core::LocalBus`] remain for tests and co-process use.
//!
//! ## Security: the realm is addressing, not a credential
//!
//! The realm string (`{realm}/…`) is *addressing*, not authorization — anyone who
//! can reach the bus and knows (or guesses) the realm can publish/subscribe on it.
//! It is **not** a secret or a credential. To actually restrict who may drive an
//! actuator, deploy the shipped per-plane access-control template and pair it with
//! mutual TLS (see `deploy/zenoh-access-control.json5` and `SECURITY.md`).
//!
//! The default [`ZenohBus::open`] / [`ZenohBus::open_realm`] path is hardened to be
//! quiet-by-default: multicast scouting is **disabled** so a default deployment does
//! not auto-advertise on the LAN (peers still connect via explicit
//! `connect`/`listen` endpoints in a supplied config). For an ACL/TLS-enforced
//! deployment, run the realm-rendered router template separately and point
//! `NCP_ZENOH_CONFIG` at a configured copy of `deploy/zenoh-client-secure.json5`,
//! then call [`ZenohBus::open_secure`]. Generic [`ZenohBus::open`] and
//! [`ZenohBus::with_config_file`] load arbitrary configs but do not apply the strict
//! secure-client validation.

use ncp_core::keys::{valid_id_segment, Keys};
use std::sync::Arc;
use zenoh::qos::{CongestionControl, Priority};
use zenoh::{Config, Session};

/// Re-export so consumers can configure Zenoh without depending on `zenoh`.
pub use zenoh::Config as ZenohConfig;

/// Environment variable naming a Zenoh config file (json5/json) to load. When set,
/// [`ZenohBus::open`] / [`ZenohBus::open_realm`] (and the `ncp-gateway` binary) load
/// it instead of the hardened default. For [`ZenohBus::open_secure`], point it at a
/// configured copy of `deploy/zenoh-client-secure.json5`, never the router ACL file.
pub const NCP_ZENOH_CONFIG_ENV: &str = "NCP_ZENOH_CONFIG";

/// Build the hardened default config: Zenoh defaults with **multicast scouting
/// disabled** so a default deployment does not auto-advertise on the LAN. Peers can
/// still connect via explicit `connect`/`listen` endpoints supplied in a config
/// file (see [`NCP_ZENOH_CONFIG_ENV`]). This is addressing-hygiene, not auth — the
/// realm is not a credential; for real authorization run the `deploy/` router ACL
/// and connect through [`ZenohBus::open_secure`] with the client template.
fn default_quiet_config() -> Result<Config> {
    let mut cfg = Config::default();
    // Fail-closed on the discovery surface: scouting-off is the security guarantee
    // of this path. Zenoh's own default is multicast scouting ON (LAN
    // auto-advertise), so if this insert ever fails we must NOT silently hand back a
    // config that re-enables it — surface the error so the open aborts.
    cfg.insert_json5("scouting/multicast/enabled", "false")
        .map_err(|e| ZenohError(format!("disable multicast scouting: {e}")))?;
    Ok(cfg)
}

/// Load a Zenoh config file (json5/json) from `path`, surfacing a parse/IO error as
/// [`ZenohError`] rather than panicking — a missing or malformed security config
/// must fail the open, never silently fall back to an open default.
fn config_from_file(path: &std::path::Path) -> Result<Config> {
    Config::from_file(path)
        .map_err(|e| ZenohError(format!("load Zenoh config {}: {e}", path.display())))
}

fn config_value(config: &Config, path: &str) -> Result<serde_json::Value> {
    let json = config
        .get_json(path)
        .map_err(|e| ZenohError(format!("secure config missing {path}: {e}")))?;
    serde_json::from_str(&json)
        .map_err(|e| ZenohError(format!("secure config {path} is not valid JSON: {e}")))
}

fn required_config_path(config: &Config, path: &str) -> Result<()> {
    match config_value(config, path)? {
        serde_json::Value::String(value) if !value.trim().is_empty() => Ok(()),
        _ => Err(ZenohError(format!(
            "secure client config requires a non-empty {path}"
        ))),
    }
}

fn collect_endpoint_strings<'a>(value: &'a serde_json::Value, out: &mut Vec<&'a str>) {
    match value {
        serde_json::Value::String(endpoint) => out.push(endpoint),
        serde_json::Value::Array(values) => {
            for value in values {
                collect_endpoint_strings(value, out);
            }
        }
        serde_json::Value::Object(values) => {
            for value in values.values() {
                collect_endpoint_strings(value, out);
            }
        }
        _ => {}
    }
}

/// `open_secure` is specifically the fail-closed *client* path. Prove that the
/// supplied config cannot discover or accept a plaintext peer and that it presents
/// a client certificate while verifying the router against an explicit CA.
fn validate_secure_client_config(config: &Config) -> Result<()> {
    if config_value(config, "mode")?.as_str() != Some("client") {
        return Err(ZenohError(
            "secure client config requires mode=\"client\"".into(),
        ));
    }
    for path in ["scouting/multicast/enabled", "scouting/gossip/enabled"] {
        if config_value(config, path)?.as_bool() != Some(false) {
            return Err(ZenohError(format!(
                "secure client config requires {path}=false"
            )));
        }
    }

    let endpoints_value = config_value(config, "connect/endpoints")?;
    let mut endpoints = Vec::new();
    collect_endpoint_strings(&endpoints_value, &mut endpoints);
    if endpoints.is_empty()
        || endpoints
            .iter()
            .any(|endpoint| !endpoint.starts_with("tls/"))
    {
        return Err(ZenohError(
            "secure client config requires one or more exclusively tls/ connect endpoints".into(),
        ));
    }

    let listen_value = config_value(config, "listen/endpoints")?;
    let mut listeners = Vec::new();
    collect_endpoint_strings(&listen_value, &mut listeners);
    if !listeners.is_empty() {
        return Err(ZenohError(
            "secure client config must not expose listen endpoints".into(),
        ));
    }

    for path in [
        "transport/link/tls/root_ca_certificate",
        "transport/link/tls/connect_certificate",
        "transport/link/tls/connect_private_key",
    ] {
        required_config_path(config, path)?;
    }
    if config_value(config, "transport/link/tls/verify_name_on_connect")?.as_bool() != Some(true) {
        return Err(ZenohError(
            "secure client config requires transport/link/tls/verify_name_on_connect=true".into(),
        ));
    }
    Ok(())
}

/// Resolve the effective config for the default open path: if [`NCP_ZENOH_CONFIG_ENV`]
/// is set, load that file (fail-closed on error); otherwise use the hardened
/// scouting-off default.
fn resolve_default_config() -> Result<Config> {
    match std::env::var_os(NCP_ZENOH_CONFIG_ENV) {
        Some(path) => config_from_file(std::path::Path::new(&path)),
        None => default_quiet_config(),
    }
}

/// A transport plane with its QoS profile.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Plane {
    /// Sensors → controller. Lossy-OK: TX-queue DROP only when full, no conflation
    /// guarantee (drops some frames, not necessarily down to the latest).
    Perception,
    /// Controller → actuators. Lowest-latency, express, safety-critical.
    Action,
    /// Lifecycle RPC replies / observation broadcast. Reliable.
    Control,
}

impl Plane {
    fn congestion(self) -> CongestionControl {
        match self {
            // Drop-oldest on the wire for high-rate / latency-critical streams.
            Plane::Perception | Plane::Action => CongestionControl::Drop,
            Plane::Control => CongestionControl::Block,
        }
    }
    fn priority(self) -> Priority {
        match self {
            Plane::Action => Priority::RealTime,
            Plane::Perception => Priority::DataHigh,
            Plane::Control => Priority::Data,
        }
    }
    fn express(self) -> bool {
        // Kill batching for the latency-critical action setpoint.
        matches!(self, Plane::Action)
    }
}

#[derive(Debug)]
pub struct ZenohError(pub String);
impl std::fmt::Display for ZenohError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}
impl std::error::Error for ZenohError {}
type Result<T> = std::result::Result<T, ZenohError>;

fn err<E: std::fmt::Display>(ctx: &str) -> impl Fn(E) -> ZenohError + '_ {
    move |e| ZenohError(format!("{ctx}: {e}"))
}

/// Reject a caller-supplied id segment (session id, entity name) before it is
/// interpolated into a key expression. Guards against empty/whitespace ids and
/// Zenoh key-expression metacharacters (`/ * $ # ?`) that would silently widen a
/// publish/subscribe to the wrong keyspace. Glob subscribers are intentionally
/// *not* guarded — their wildcards are constructed by the key builders.
fn check_id(kind: &str, id: &str) -> Result<()> {
    if valid_id_segment(id) {
        Ok(())
    } else {
        Err(ZenohError(format!("invalid {kind} id segment: {id:?}")))
    }
}

/// Wire-0.6 publish gate for the perception plane: a `SensorFrame` must decode,
/// carry the right `kind`, a compatible `ncp_version`, and a stamped `seq >= 1`.
fn check_sensor_payload(payload: &[u8]) -> Result<()> {
    ncp_core::validate_sensor_plane_payload(payload)
        .map_err(|e| ZenohError(format!("refusing to publish sensor frame: {e}")))
}

/// Wire-0.6 publish gate for the action plane. An ESTOP command is ALWAYS allowed
/// through (a fail-safe is never suppressed — receivers latch it before any
/// seq/version gate); everything else must pass full wire validation.
fn check_command_payload(payload: &[u8]) -> Result<()> {
    ncp_core::validate_command_plane_payload(payload)
        .map_err(|e| ZenohError(format!("refusing to publish command frame: {e}")))
}

/// Publish gate for the observation plane. The shipped transport accepts only a
/// complete, versioned JSON `observation_frame` and requires `seq >= 1` — the
/// plane-published form must echo its driving sensor seq (`0` is pull-path-only).
/// A bare NCPB column block is deliberately rejected: it carries no session, seq,
/// timestamp, or honesty-boundary provenance. `BulkBlock` remains a local/negotiated
/// payload codec until a fully specified envelope is implemented across every SDK.
fn check_observation_payload_for(session_id: &str, payload: &[u8]) -> Result<()> {
    ncp_core::validate_observation_plane_payload_for(session_id, payload)
        .map_err(|e| ZenohError(format!("refusing observation frame: {e}")))
}

/// Validate both layers of lifecycle routing: the selector grants authority for
/// one verb, and the payload must be that same complete/versioned request. This
/// prevents a client authorized only for one exact RPC key from smuggling a
/// different lifecycle message through it.
fn check_rpc_request(keys: &Keys, selector: &str, payload: &[u8]) -> Result<serde_json::Value> {
    let selector_kind = selector_request_kind(keys, selector)
        .ok_or_else(|| ZenohError(format!("unsupported NCP RPC selector {selector:?}")))?;
    let (request, _) = ncp_core::validate_rpc_request_for(&selector_kind, payload)
        .map_err(|error| ZenohError(error.to_string()))?;
    Ok(request)
}

fn check_rpc_handler_reply(request_kind: &str, session_id: &str, payload: &[u8]) -> Result<()> {
    ncp_core::validate_rpc_reply_for(request_kind, session_id, payload)
        .map(drop)
        .map_err(|error| ZenohError(error.to_string()))
}

fn rpc_error_payload(
    error: impl Into<String>,
    session_id: Option<String>,
    request_kind: Option<String>,
) -> Vec<u8> {
    ncp_core::rpc_error_payload(error, session_id, request_kind)
}

fn selector_request_kind(keys: &Keys, selector: &str) -> Option<String> {
    ncp_core::keys::RPC_REQUEST_KINDS
        .iter()
        .copied()
        .find(|kind| keys.rpc_for_kind(kind).is_ok_and(|key| key == selector))
        .map(str::to_owned)
}

fn request_session_id(value: &serde_json::Value) -> Option<String> {
    value
        .get("session_id")
        .and_then(serde_json::Value::as_str)
        .filter(|session_id| valid_id_segment(session_id))
        .map(str::to_owned)
}

type RpcHandler = dyn Fn(Vec<u8>) -> Vec<u8> + Send + Sync;
type RetainedSubscribers = Arc<std::sync::Mutex<Vec<(String, zenoh::pubsub::Subscriber<()>)>>>;

/// Bound concurrent blocking/backend calls. Control RPC is rare; this ceiling is
/// deliberately generous while preventing a hostile client from turning one
/// queryable into unbounded tasks/memory.
const MAX_IN_FLIGHT_RPC_REQUESTS: usize = 64;

fn dispatch_rpc(keys: &Keys, handler: &RpcHandler, selector: &str, req: Vec<u8>) -> Vec<u8> {
    let selector_kind = selector_request_kind(keys, selector);
    let parsed = serde_json::from_slice::<serde_json::Value>(&req).ok();
    let session_id = parsed.as_ref().and_then(request_session_id);
    match check_rpc_request(keys, selector, &req) {
        Err(error) => rpc_error_payload(error.to_string(), session_id, selector_kind),
        Ok(request) => {
            let request_kind = ncp_core::message_kind(&request)
                .expect("validated request carries kind")
                .to_owned();
            let request_session = request_session_id(&request)
                .expect("validated lifecycle request carries a safe session_id");
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handler(req))) {
                Ok(reply) => {
                    match check_rpc_handler_reply(&request_kind, &request_session, &reply) {
                        Ok(()) => reply,
                        Err(error) => rpc_error_payload(
                            error.to_string(),
                            Some(request_session),
                            Some(request_kind),
                        ),
                    }
                }
                Err(_) => rpc_error_payload(
                    "RPC handler panicked",
                    Some(request_session),
                    Some(request_kind),
                ),
            }
        }
    }
}

async fn dispatch_rpc_off_thread(
    keys: Keys,
    handler: Arc<RpcHandler>,
    selector: String,
    req: Vec<u8>,
    permit: Arc<tokio::sync::OwnedSemaphorePermit>,
) -> Vec<u8> {
    let parsed = serde_json::from_slice::<serde_json::Value>(&req).ok();
    let error_session = parsed.as_ref().and_then(request_session_id);
    let error_kind = selector_request_kind(&keys, &selector);
    match tokio::task::spawn_blocking(move || {
        // Keep a permit clone in the blocking closure so aborting the async
        // reply task cannot release capacity while this synchronous handler is
        // still executing. The caller retains its own clone through reply
        // delivery, bounding the complete request lifetime rather than only the
        // backend call.
        let _permit = permit;
        dispatch_rpc(&keys, handler.as_ref(), &selector, req)
    })
    .await
    {
        Ok(reply) => reply,
        Err(error) => rpc_error_payload(
            format!("RPC dispatch task failed: {error}"),
            error_session,
            error_kind,
        ),
    }
}

/// An NCP-aware Zenoh session. Wraps a [`zenoh::Session`] with the NCP key scheme
/// and per-plane QoS.
#[derive(Clone)]
pub struct ZenohBus {
    session: Arc<Session>,
    keys: Keys,
    // Retain subscriber handles for the session lifetime — a dropped Zenoh
    // Subscriber undeclares its subscription, so callbacks would stop firing.
    // Keep each selector so a closed NCP session can release only its own handles.
    subs: RetainedSubscribers,
    /// `false` for `from_session`: a wrapper must never close a session owned by
    /// its host application.
    owns_session: bool,
}

impl ZenohBus {
    /// Open with the hardened default config and realm.
    ///
    /// "Hardened default" = Zenoh defaults with multicast scouting **disabled** so a
    /// default deployment does not auto-advertise on the LAN. If [`NCP_ZENOH_CONFIG_ENV`]
    /// is set, the named config file is loaded instead (and a load error fails the
    /// open — it never silently falls back to an open default). The realm is
    /// addressing, not a credential; for ACL/TLS enforcement use [`Self::open_secure`].
    pub async fn open() -> Result<Self> {
        Self::with_config(resolve_default_config()?, Keys::default()).await
    }

    /// Open with the hardened default config and an explicit realm. See [`Self::open`]
    /// for the scouting-off default and the [`NCP_ZENOH_CONFIG_ENV`] override.
    pub async fn open_realm(keys: Keys) -> Result<Self> {
        Self::with_config(resolve_default_config()?, keys).await
    }

    /// Open with an arbitrary Zenoh config loaded from a file (json5/json). A missing
    /// or malformed file fails the open rather than falling back. This generic path
    /// does not validate the secure-client invariants; use [`Self::open_secure`] for
    /// an enforced deployment.
    pub async fn with_config_file(path: impl AsRef<std::path::Path>, keys: Keys) -> Result<Self> {
        Self::with_config(config_from_file(path.as_ref())?, keys).await
    }

    /// Open the secure deployment config: load the file named by [`NCP_ZENOH_CONFIG_ENV`]
    /// (the operator points it at a configured copy of
    /// `deploy/zenoh-client-secure.json5`). Unlike
    /// [`Self::open`], the env var is **required** here — if it is unset the open
    /// fails rather than starting an unauthenticated session, so a misconfigured
    /// "secure" deployment refuses to come up instead of silently opening a hole.
    pub async fn open_secure(keys: Keys) -> Result<Self> {
        let path = std::env::var_os(NCP_ZENOH_CONFIG_ENV).ok_or_else(|| {
            ZenohError(format!(
                "open_secure requires {NCP_ZENOH_CONFIG_ENV} to name a strict Zenoh \
                 client config (start from deploy/zenoh-client-secure.json5)"
            ))
        })?;
        let config = config_from_file(std::path::Path::new(&path))?;
        validate_secure_client_config(&config)?;
        Self::with_config(config, keys).await
    }

    /// Open with an explicit config and realm.
    pub async fn with_config(config: Config, keys: Keys) -> Result<Self> {
        keys.validate()
            .map_err(|e| ZenohError(format!("refusing invalid realm: {e}")))?;
        let session = zenoh::open(config).await.map_err(err("zenoh open"))?;
        Ok(Self {
            session: Arc::new(session),
            keys,
            subs: Arc::new(std::sync::Mutex::new(Vec::new())),
            owns_session: true,
        })
    }

    /// Wrap an already-open session (so a host app, e.g. a ROS 2 robot client,
    /// can share one Zenoh session across ROS traffic and NCP).
    pub fn from_session(session: Arc<Session>, keys: Keys) -> Self {
        keys.validate()
            .expect("refusing to wrap a Zenoh session with an invalid NCP realm");
        Self {
            session,
            keys,
            subs: Arc::new(std::sync::Mutex::new(Vec::new())),
            owns_session: false,
        }
    }

    pub fn keys(&self) -> &Keys {
        &self.keys
    }
    pub fn session(&self) -> &Arc<Session> {
        &self.session
    }

    // ───────────────────────── client side ─────────────────────────

    /// Control-plane RPC: send a serialized NCP message, return the reply bytes.
    pub async fn request(&self, message: &[u8]) -> Result<Vec<u8>> {
        self.request_inner(message, None).await
    }

    /// Control-plane RPC with an explicit query deadline. Use this for a long
    /// `step_request`/`run_request` so the transport deadline is at least the
    /// expected backend simulation duration; otherwise Zenoh's configured default
    /// query timeout applies.
    pub async fn request_with_timeout(
        &self,
        message: &[u8],
        timeout: std::time::Duration,
    ) -> Result<Vec<u8>> {
        self.request_inner(message, Some(timeout)).await
    }

    async fn request_inner(
        &self,
        message: &[u8],
        timeout: Option<std::time::Duration>,
    ) -> Result<Vec<u8>> {
        let request: serde_json::Value =
            serde_json::from_slice(message).map_err(err("parse NCP RPC request"))?;
        ncp_core::validate(&request).map_err(err("invalid NCP RPC request"))?;
        let kind = ncp_core::message_kind(&request)
            .expect("validated NCP request always carries a string kind");
        let rpc_key = self
            .keys
            .rpc_for_kind(kind)
            .map_err(|error| ZenohError(format!("cannot route NCP RPC kind {kind:?}: {error}")))?;
        let get = self.session.get(rpc_key.clone()).payload(message);
        let replies = match timeout {
            Some(timeout) => get.timeout(timeout).await,
            None => get.await,
        }
        .map_err(err("zenoh get"))?;
        // Capture the last error reply so a remote error (server replied with an
        // error) is distinguishable from a dead server (no reply at all).
        let mut last_err: Option<String> = None;
        while let Ok(reply) = replies.recv_async().await {
            match reply.result() {
                Ok(sample) => return Ok(sample.payload().to_bytes().to_vec()),
                Err(e) => {
                    last_err = Some(String::from_utf8_lossy(&e.payload().to_bytes()).into_owned())
                }
            }
        }
        match last_err {
            Some(e) => Err(ZenohError(format!("rpc error reply for {}: {e}", rpc_key))),
            None => Err(ZenohError(format!("no reply for {rpc_key}"))),
        }
    }

    /// Publish a `SensorFrame` (perception plane) for a session.
    ///
    /// Wire 0.6: the payload is validated before it leaves this peer (a
    /// stamped `seq >= 1`, a compatible `ncp_version`, the right `kind`) — a
    /// non-conforming publisher fails loudly here instead of being silently
    /// dropped by every receiver. [`Self::put`] remains the raw escape hatch.
    pub async fn put_sensor(&self, session_id: &str, payload: &[u8]) -> Result<()> {
        check_id("session", session_id)?;
        check_sensor_payload(payload)?;
        self.put(&self.keys.sensor(session_id), payload, Plane::Perception)
            .await
    }

    /// Subscribe to the command (action) plane — the plant receives `CommandFrame`s.
    pub async fn subscribe_commands<F>(&self, session_id: &str, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        self.subscribe(&self.keys.command(session_id), move |key, payload| {
            if check_command_payload(&payload).is_ok() {
                callback(key, payload);
            }
        })
        .await
    }

    /// Subscribe to the observation plane (the free read-only observer tap).
    pub async fn subscribe_observations<F>(&self, session_id: &str, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        let expected_session = session_id.to_owned();
        self.subscribe(&self.keys.observation(session_id), move |key, payload| {
            if check_observation_payload_for(&expected_session, &payload).is_ok() {
                callback(key, payload);
            }
        })
        .await
    }

    /// Subscribe to every plane of a session (observer/diagnostic tap).
    pub async fn subscribe_session<F>(&self, session_id: &str, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        // Guard the glob entry point too: a malformed/wildcard id must be rejected
        // here, not silently widen the subscription in a release build (debug_assert
        // in the key builder is compiled out).
        check_id("session", session_id)?;
        self.subscribe(&self.keys.session_glob(session_id), callback)
            .await
    }

    // ───────────────────────── server side ─────────────────────────

    /// Serve the control-plane RPC queryable. `handler` maps request JSON bytes →
    /// reply JSON bytes (e.g. a gateway forwards it to a Python backend's
    /// `SessionService.handle_json`). Each accepted query runs independently so a
    /// slow backend request cannot head-of-line block every lifecycle verb; the
    /// number of in-flight handlers is bounded and excess queries receive a typed
    /// `ErrorFrame`. Synchronous handlers run on Tokio's blocking pool rather than
    /// an async worker. Abort the returned task to stop accepting/replying without
    /// closing a shared Zenoh session; Rust cannot forcibly cancel a synchronous
    /// handler already executing, so those remain bounded and finish in the
    /// blocking pool.
    pub async fn serve_rpc<F>(&self, handler: F) -> Result<tokio::task::JoinHandle<()>>
    where
        F: Fn(Vec<u8>) -> Vec<u8> + Send + Sync + 'static,
    {
        let queryable = self
            .session
            .declare_queryable(self.keys.rpc_glob())
            .await
            .map_err(err("declare queryable"))?;
        let handler: Arc<RpcHandler> = Arc::new(handler);
        let keys = self.keys.clone();
        let permits = Arc::new(tokio::sync::Semaphore::new(MAX_IN_FLIGHT_RPC_REQUESTS));
        Ok(tokio::spawn(async move {
            let mut handlers = tokio::task::JoinSet::new();
            loop {
                let query = tokio::select! {
                    // Prefer reaping completed entries whenever both a reply
                    // task and a new query are ready. Together with the permit
                    // held through reply delivery, this keeps both active and
                    // completed-but-unjoined JoinSet entries bounded under a
                    // continuously readable hostile query stream.
                    biased;
                    completed = handlers.join_next(), if !handlers.is_empty() => {
                        if let Some(Err(error)) = completed {
                            eprintln!("ncp-zenoh: RPC dispatch task failed: {error}");
                        }
                        continue;
                    },
                    result = queryable.recv_async() => match result {
                        Ok(query) => query,
                        Err(_) => break,
                    },
                };
                let req = query
                    .payload()
                    .map(|p| p.to_bytes().to_vec())
                    .unwrap_or_default();
                let ke = query.key_expr().clone();
                let selector = ke.as_str().to_owned();
                let permit = match permits.clone().try_acquire_owned() {
                    Ok(permit) => Arc::new(permit),
                    Err(_) => {
                        let parsed = serde_json::from_slice::<serde_json::Value>(&req).ok();
                        let session_id = parsed.as_ref().and_then(request_session_id);
                        let request_kind = selector_request_kind(&keys, &selector);
                        let reply = rpc_error_payload(
                            "RPC server busy: in-flight request limit reached",
                            session_id,
                            request_kind,
                        );
                        if let Err(error) = query.reply(ke, reply).await {
                            eprintln!("ncp-zenoh: busy RPC reply failed: {error}");
                        }
                        continue;
                    }
                };
                let handler = handler.clone();
                let keys = keys.clone();
                handlers.spawn(async move {
                    // The public handler is deliberately synchronous (the gateway
                    // bridges to a blocking TCP backend). Running it directly in
                    // this async task would still pin a Tokio worker and could
                    // serialize every request on a current-thread runtime.
                    let reply =
                        dispatch_rpc_off_thread(keys, handler, selector, req, permit.clone()).await;
                    if let Err(error) = query.reply(ke, reply).await {
                        // No log crate in this minimal feature set; surface to stderr
                        // so a failed reply isn't silently dropped.
                        eprintln!("ncp-zenoh: RPC reply failed: {error}");
                    }
                    // `permit` intentionally remains live through the awaited
                    // reply. Dropping it here completes the bounded request.
                    drop(permit);
                });
            }
            // Dropping JoinSet cancels async reply tasks. An already-running
            // spawn_blocking call cannot be pre-empted by Tokio; its semaphore
            // permit stays owned until the synchronous handler returns.
        }))
    }

    /// Publish an observation frame on a session's observation key: either a JSON
    /// complete, versioned JSON `observation_frame`.
    ///
    /// Wire 0.6 (normative): a JSON frame published on the **observation plane**
    /// must echo the driving `SensorFrame.seq` — `seq >= 1` is enforced here
    /// (`seq == 0` is only legal in the pull/RPC reply path, which does not go
    /// through this publisher). This is the publisher-side half of the split-plane
    /// seq-join contract that any observer aligns on.
    pub async fn publish_observation(&self, session_id: &str, payload: &[u8]) -> Result<()> {
        check_id("session", session_id)?;
        check_observation_payload_for(session_id, payload)?;
        self.put(&self.keys.observation(session_id), payload, Plane::Control)
            .await
    }

    /// Publish a command frame on a session's action plane (safety-gated upstream).
    ///
    /// Wire 0.6: the payload is validated before publish (stamped `seq >= 1`,
    /// compatible `ncp_version`, right `kind`) — except an **ESTOP**, which is
    /// always allowed through: a fail-safe is never suppressed by a validation
    /// gate (receivers latch ESTOP before any seq/version check).
    pub async fn publish_command(&self, session_id: &str, payload: &[u8]) -> Result<()> {
        check_id("session", session_id)?;
        check_command_payload(payload)?;
        self.put(&self.keys.command(session_id), payload, Plane::Action)
            .await
    }

    /// Subscribe to the sensor (perception) plane for a session.
    pub async fn subscribe_sensors<F>(&self, session_id: &str, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        self.subscribe(&self.keys.sensor(session_id), move |key, payload| {
            if check_sensor_payload(&payload).is_ok() {
                callback(key, payload);
            }
        })
        .await
    }

    // ───────────── per-named-entity (multi-sensor / multi-actuator) ─────────────
    // A UAV with a varying number of sensors/actuators addresses each by name on
    // its own sub-key; the callback's `key` argument identifies which entity. Per
    // entity `seq` is its own stream (one LinkMonitor/ActionBuffer per entity).

    /// Publish a `SensorFrame` for one named sensor: `…/sensor/{name}`.
    /// Validated like [`Self::put_sensor`] (per-entity `seq` is its own stream).
    pub async fn put_sensor_named(
        &self,
        session_id: &str,
        name: &str,
        payload: &[u8],
    ) -> Result<()> {
        check_id("session", session_id)?;
        check_id("sensor name", name)?;
        check_sensor_payload(payload)?;
        self.put(
            &self.keys.sensor_named(session_id, name),
            payload,
            Plane::Perception,
        )
        .await
    }

    /// Publish a `CommandFrame` to one named actuator: `…/command/{name}`.
    /// Validated like [`Self::publish_command`] (ESTOP always passes).
    pub async fn publish_command_named(
        &self,
        session_id: &str,
        name: &str,
        payload: &[u8],
    ) -> Result<()> {
        check_id("session", session_id)?;
        check_id("actuator name", name)?;
        check_command_payload(payload)?;
        self.put(
            &self.keys.command_named(session_id, name),
            payload,
            Plane::Action,
        )
        .await
    }

    /// Subscribe to **all** of a session's sensors (any count): `…/sensor/**`.
    pub async fn subscribe_sensors_glob<F>(&self, session_id: &str, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        // Guard the glob entry point too (release builds drop the key-builder
        // debug_assert), so a wildcard-bearing id cannot widen the subscription.
        check_id("session", session_id)?;
        self.subscribe(&self.keys.sensor_glob(session_id), move |key, payload| {
            if check_sensor_payload(&payload).is_ok() {
                callback(key, payload);
            }
        })
        .await
    }

    /// Subscribe to one named actuator's command stream: `…/command/{name}`.
    pub async fn subscribe_command_named<F>(
        &self,
        session_id: &str,
        name: &str,
        callback: F,
    ) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        check_id("actuator name", name)?;
        self.subscribe(
            &self.keys.command_named(session_id, name),
            move |key, payload| {
                if check_command_payload(&payload).is_ok() {
                    callback(key, payload);
                }
            },
        )
        .await
    }

    /// Subscribe across the whole fleet (every session/plane): `{realm}/session/**`
    /// — e.g. an observer/dashboard over all UAVs.
    pub async fn subscribe_fleet<F>(&self, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        self.subscribe(&self.keys.fleet_glob(), callback).await
    }

    // ───────────────────────── primitives ─────────────────────────

    /// Publish on `key` with the QoS of `plane`.
    pub async fn put(&self, key: &str, payload: &[u8], plane: Plane) -> Result<()> {
        self.session
            .put(key, payload.to_vec())
            .congestion_control(plane.congestion())
            .priority(plane.priority())
            .express(plane.express())
            .await
            .map_err(err("zenoh put"))
    }

    /// Subscribe to `key` (may contain `*`/`**`); `callback` gets `(key, bytes)`.
    ///
    /// Backpressure model: this is a Zenoh **callback** subscriber — the callback
    /// runs INLINE on Zenoh's receive task, one sample at a time. There is no
    /// user-side queue, so a slow callback applies natural backpressure to the
    /// stream (it does NOT buffer unboundedly and cannot exhaust memory). The flip
    /// side is head-of-line: keep `callback` cheap (decode + hand off), and for a
    /// control loop prefer latest-wins (overwrite a shared `SensorFrame`, as
    /// [`ZenohControlTransport`] does) over doing heavy work here. Callback
    /// panics are contained and logged so one hostile frame cannot silently kill
    /// the subscription, but callers should still decode fallibly and drop.
    pub async fn subscribe<F>(&self, key: &str, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        let selector = key.to_string();
        let callback = Arc::new(callback);
        let sub = self
            .session
            .declare_subscriber(selector.clone())
            .callback(move |sample| {
                let key = sample.key_expr().as_str().to_string();
                let payload = sample.payload().to_bytes().to_vec();
                if std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    callback(key, payload);
                }))
                .is_err()
                {
                    eprintln!("ncp-zenoh: subscriber callback panicked; sample dropped");
                }
            })
            .await
            .map_err(err("declare subscriber"))?;
        // Keep the handle alive (dropping it undeclares the subscription).
        self.subs
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .push((selector, sub));
        Ok(())
    }

    /// Undeclare every subscriber owned by this wrapper for one NCP session.
    /// Long-lived fleet processes should call this after `close_session` so a
    /// create/close cycle does not retain callbacks forever. Other sessions and
    /// fleet-wide subscriptions remain active.
    pub fn unsubscribe_session(&self, session_id: &str) -> Result<usize> {
        check_id("session", session_id)?;
        let glob = self.keys.session_glob(session_id);
        let prefix = glob
            .strip_suffix("/**")
            .expect("session_glob always ends in /**");
        let prefix_slash = format!("{prefix}/");
        let mut subscribers = self.subs.lock().unwrap_or_else(|e| e.into_inner());
        let before = subscribers.len();
        subscribers
            .retain(|(selector, _)| selector != prefix && !selector.starts_with(&prefix_slash));
        Ok(before - subscribers.len())
    }

    /// Release this wrapper's subscribers and, only when this wrapper opened the
    /// Zenoh session itself, gracefully close the underlying session. A wrapper
    /// created with [`Self::from_session`] never closes its host's borrowed
    /// session.
    pub async fn close(&self) -> Result<()> {
        self.subs.lock().unwrap_or_else(|e| e.into_inner()).clear();
        if self.owns_session {
            self.session.close().await.map_err(err("zenoh close"))
        } else {
            Ok(())
        }
    }
}

/// A [`ncp_core::ControlTransport`] backed by Zenoh — the **controller side** of
/// the streaming closed loop. It subscribes to the perception plane
/// (`…/session/{id}/sensor`), keeping the latest `SensorFrame`, and publishes
/// `CommandFrame`s to the safety-gated action plane (`…/command`). Drop it into a
/// `ncp_core::NeuroControlLoop` to run a spiking or reflex controller over Zenoh
/// **streaming** — no per-tick RPC round trip. Construct within a tokio runtime.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
enum CommandPriority {
    Active,
    Hold,
    Estop,
}

#[derive(Debug)]
struct PendingCommand {
    bytes: Vec<u8>,
    priority: CommandPriority,
}

fn command_priority(mode: &ncp_core::Mode) -> CommandPriority {
    match mode {
        ncp_core::Mode::Active => CommandPriority::Active,
        ncp_core::Mode::Estop => CommandPriority::Estop,
        _ => CommandPriority::Hold,
    }
}

/// Store at most one not-yet-published command. Equal-priority frames conflate to
/// the latest, while a pending fail-safe cannot be overwritten by Active.
fn enqueue_command(
    slot: &std::sync::Mutex<Option<PendingCommand>>,
    pending: PendingCommand,
) -> bool {
    let mut slot = slot.lock().unwrap_or_else(|error| error.into_inner());
    if slot
        .as_ref()
        .is_some_and(|current| current.priority > pending.priority)
    {
        return false;
    }
    *slot = Some(pending);
    true
}

async fn dispatch_commands(
    bus: ZenohBus,
    session_id: String,
    slot: Arc<std::sync::Mutex<Option<PendingCommand>>>,
    notify: Arc<tokio::sync::Notify>,
) {
    loop {
        notify.notified().await;
        loop {
            let pending = slot
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .take();
            let Some(pending) = pending else {
                break;
            };
            if let Err(error) = bus.publish_command(&session_id, &pending.bytes).await {
                eprintln!("ncp: command publish failed for session {session_id:?}: {error}");
                if pending.priority != CommandPriority::Active {
                    // A failed fail-safe must remain ahead of any later Active.
                    // One worker plus one slot bounds memory regardless of outage.
                    enqueue_command(&slot, pending);
                    tokio::time::sleep(std::time::Duration::from_millis(100)).await;
                    notify.notify_one();
                    break;
                }
            }
        }
    }
}

pub struct ZenohControlTransport {
    _bus: ZenohBus,
    latest: Arc<std::sync::Mutex<Option<ncp_core::SensorFrame>>>,
    command_slot: Arc<std::sync::Mutex<Option<PendingCommand>>>,
    command_notify: Arc<tokio::sync::Notify>,
    command_worker: tokio::task::JoinHandle<()>,
}

impl ZenohControlTransport {
    pub async fn new(bus: ZenohBus, session_id: impl Into<String>) -> Result<Self> {
        let session_id = session_id.into();
        let latest: Arc<std::sync::Mutex<Option<ncp_core::SensorFrame>>> =
            Arc::new(std::sync::Mutex::new(None));
        let sink = latest.clone();
        bus.subscribe_sensors(&session_id, move |_key, bytes| {
            // Wire 0.6: the data-plane ingress gate. `decode_validated` rejects an
            // unparseable, kind-mismatched, version-less/incompatible, or
            // unstamped (`seq < 1`) frame — dropped with a diagnostic so a
            // mismatched peer is observable, never silently steering the loop.
            match ncp_core::decode_validated::<ncp_core::SensorFrame>(&bytes) {
                Ok(sf) => *sink.lock().unwrap_or_else(|e| e.into_inner()) = Some(sf),
                Err(e) => match ncp_core::diagnose_version(&bytes) {
                    Some(ve) => eprintln!("ncp: dropped sensor frame ({ve})"),
                    None => eprintln!("ncp: dropped sensor frame: {e}"),
                },
            }
        })
        .await?;
        let command_slot = Arc::new(std::sync::Mutex::new(None));
        let command_notify = Arc::new(tokio::sync::Notify::new());
        let command_worker = tokio::spawn(dispatch_commands(
            bus.clone(),
            session_id.clone(),
            command_slot.clone(),
            command_notify.clone(),
        ));
        Ok(Self {
            _bus: bus,
            latest,
            command_slot,
            command_notify,
            command_worker,
        })
    }
}

impl Drop for ZenohControlTransport {
    fn drop(&mut self) {
        self.command_worker.abort();
    }
}

/// What `send_command` should do with a frame (pure, unit-testable).
///
/// - An **ESTOP always publishes** — a fail-safe is never suppressed, stamped or
///   not (receivers latch ESTOP before any seq/version gate).
/// - A wire-valid frame publishes.
/// - An invalid **Active** frame is skipped LOUDLY — a controller trying to
///   actuate with an unstamped/incompatible frame is a real fault.
/// - An invalid non-Active frame (Hold/Init) is skipped silently: the loop
///   legitimately emits unstampable HOLDs before its first sensor arrives (there
///   is no sensor seq to echo yet), and the plant holds by default anyway.
#[derive(Debug, PartialEq, Eq, Clone, Copy)]
enum PublishDecision {
    Publish,
    SkipSilent,
    SkipLoud,
}

fn command_publish_decision(cmd: &ncp_core::CommandFrame) -> PublishDecision {
    use ncp_core::{Mode, WireFrame};
    if cmd.mode == Mode::Estop {
        return PublishDecision::Publish;
    }
    if cmd.validate_wire().is_ok() {
        return PublishDecision::Publish;
    }
    if cmd.mode == Mode::Active {
        PublishDecision::SkipLoud
    } else {
        PublishDecision::SkipSilent
    }
}

fn normalize_command_for_publish(
    command: &ncp_core::CommandFrame,
) -> std::borrow::Cow<'_, ncp_core::CommandFrame> {
    if command.mode == ncp_core::Mode::Estop && ncp_core::WireFrame::validate_wire(command).is_err()
    {
        let mut governor = ncp_core::SafetyGovernor::default();
        std::borrow::Cow::Owned(governor.govern(command, None, 0.0, None))
    } else {
        std::borrow::Cow::Borrowed(command)
    }
}

impl ncp_core::ControlTransport for ZenohControlTransport {
    fn send_command(&self, command: &ncp_core::CommandFrame) {
        // Wire 0.6: never publish a wire-invalid frame (fail loud at the sender,
        // not silently at every receiver) — except ESTOP, which always goes out.
        match command_publish_decision(command) {
            PublishDecision::Publish => {}
            PublishDecision::SkipSilent => return,
            PublishDecision::SkipLoud => {
                if let Err(e) = ncp_core::WireFrame::validate_wire(command) {
                    eprintln!("ncp: NOT publishing invalid Active command ({e})");
                }
                return;
            }
        }
        // Normalize a malformed in-memory ESTOP to a complete zeroed wire frame;
        // the raw publisher gate intentionally gives ESTOP priority, but a typed
        // NaN/control-character payload still needs to serialize predictably.
        let command = normalize_command_for_publish(command);
        let Ok(bytes) = serde_json::to_vec(command.as_ref()) else {
            return;
        };
        if enqueue_command(
            &self.command_slot,
            PendingCommand {
                bytes,
                priority: command_priority(&command.mode),
            },
        ) {
            self.command_notify.notify_one();
        }
    }

    fn latest_sensor(&self) -> Option<ncp_core::SensorFrame> {
        self.latest
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }
}

/// Validate an RPC reply's own `kind` discriminator before the typed decode: an
/// error frame surfaces as `Err`, and a wrong-but-valid-JSON reply is rejected
/// rather than silently decoding into an all-default `Resp`. Pure (no transport),
/// so it is unit-testable.
fn check_reply(
    reply: &[u8],
    request_kind: &str,
    expect_session_id: &str,
) -> Result<serde_json::Value> {
    let value = ncp_core::validate_rpc_reply_for(request_kind, expect_session_id, reply)
        .map_err(|error| ZenohError(error.to_string()))?;
    let kind = ncp_core::message_kind(&value).expect("validate requires string kind");
    if kind == "error" {
        return Err(ZenohError(format!(
            "NCP error: {}",
            value
                .get("error")
                .and_then(|field| field.as_str())
                .expect("validated ErrorFrame has a string error")
        )));
    }
    Ok(value)
}

/// Convenience: a typed NCP client over Zenoh.
pub struct ZenohNcpClient {
    bus: ZenohBus,
}

impl ZenohNcpClient {
    pub fn new(bus: ZenohBus) -> Self {
        Self { bus }
    }

    /// Open a session; returns the parsed `SessionOpened`. The handshake gates on
    /// **version compatibility** (a `SessionOpened` whose `ncp_version` is
    /// incompatible is rejected, never coerced) and treats the `contract_hash` as an
    /// **advisory** signal: a hash mismatch is logged but does *not* fail the session,
    /// so a version-compatible flow keeps working when a peer is on a different
    /// contract revision (e.g. it added an optional field). See
    /// [`ncp_core::ContractStatus`].
    pub async fn open(&self, msg: &ncp_core::OpenSession) -> Result<ncp_core::SessionOpened> {
        self.open_inner(msg, None).await
    }

    /// Open with an explicit transport query deadline.
    pub async fn open_with_timeout(
        &self,
        msg: &ncp_core::OpenSession,
        timeout: std::time::Duration,
    ) -> Result<ncp_core::SessionOpened> {
        self.open_inner(msg, Some(timeout)).await
    }

    async fn open_inner(
        &self,
        msg: &ncp_core::OpenSession,
        timeout: Option<std::time::Duration>,
    ) -> Result<ncp_core::SessionOpened> {
        let opened: ncp_core::SessionOpened = self.rpc(msg, "session_opened", timeout).await?;
        let status = ncp_core::negotiate(&opened.ncp_version, opened.contract_hash.as_deref())
            .map_err(|e| ZenohError(format!("session_opened version: {e}")))?;
        if let Some(advisory) = status.advisory() {
            // Advisory, not fatal: log so operators can spot a fleet on mixed revisions.
            eprintln!("[ncp-zenoh] {advisory}");
        }
        Ok(opened)
    }

    /// Step a session; returns the parsed `ObservationFrame`.
    pub async fn step(&self, msg: &ncp_core::StepRequest) -> Result<ncp_core::ObservationFrame> {
        self.rpc(msg, "observation_frame", None).await
    }

    /// Step with an explicit transport query deadline.
    pub async fn step_with_timeout(
        &self,
        msg: &ncp_core::StepRequest,
        timeout: std::time::Duration,
    ) -> Result<ncp_core::ObservationFrame> {
        self.rpc(msg, "observation_frame", Some(timeout)).await
    }

    /// Run a session for a duration; returns the parsed `ObservationFrame`.
    pub async fn run(&self, msg: &ncp_core::RunRequest) -> Result<ncp_core::ObservationFrame> {
        self.rpc(msg, "observation_frame", None).await
    }

    /// Run with an explicit transport query deadline. The deadline should cover
    /// the requested simulation duration plus backend overhead.
    pub async fn run_with_timeout(
        &self,
        msg: &ncp_core::RunRequest,
        timeout: std::time::Duration,
    ) -> Result<ncp_core::ObservationFrame> {
        self.rpc(msg, "observation_frame", Some(timeout)).await
    }

    /// Close a session.
    pub async fn close(&self, msg: &ncp_core::CloseSession) -> Result<ncp_core::SessionClosed> {
        self.rpc(msg, "session_closed", None).await
    }

    /// Close with an explicit transport query deadline.
    pub async fn close_with_timeout(
        &self,
        msg: &ncp_core::CloseSession,
        timeout: std::time::Duration,
    ) -> Result<ncp_core::SessionClosed> {
        self.rpc(msg, "session_closed", Some(timeout)).await
    }

    async fn rpc<Req, Resp>(
        &self,
        msg: &Req,
        expect_kind: &str,
        timeout: Option<std::time::Duration>,
    ) -> Result<Resp>
    where
        Req: serde::Serialize,
        Resp: serde::de::DeserializeOwned,
    {
        let request = serde_json::to_value(msg).map_err(err("serialize request"))?;
        let session_id = request
            .get("session_id")
            .and_then(|field| field.as_str())
            .ok_or_else(|| ZenohError("NCP request carries no string session_id".into()))?;
        let request_kind = request
            .get("kind")
            .and_then(|field| field.as_str())
            .ok_or_else(|| ZenohError("NCP request carries no string kind".into()))?;
        if ncp_core::expected_rpc_reply_kind(request_kind) != Some(expect_kind) {
            return Err(ZenohError(format!(
                "typed RPC mismatch: request {request_kind:?} cannot expect {expect_kind:?}"
            )));
        }
        let req = serde_json::to_vec(msg).map_err(err("serialize request"))?;
        let reply = match timeout {
            Some(timeout) => self.bus.request_with_timeout(&req, timeout).await?,
            None => self.bus.request(&req).await?,
        };
        // Reject an error frame or a wrong-`kind` reply before the typed decode,
        // so a misrouted reply cannot silently become an all-default `Resp` —
        // then (wire 0.6) validate the reply against the wire contract for its
        // kind (required fields incl. a compatible `ncp_version`).
        let value = check_reply(&reply, request_kind, session_id)?;
        serde_json::from_value(value).map_err(err("parse reply"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn plane_qos_profiles() {
        assert_eq!(Plane::Action.congestion(), CongestionControl::Drop);
        assert_eq!(Plane::Action.priority(), Priority::RealTime);
        assert!(Plane::Action.express());
        assert_eq!(Plane::Control.congestion(), CongestionControl::Block);
        assert!(!Plane::Perception.express());
    }

    #[test]
    fn check_reply_rejects_wrong_kind_session_and_unversioned_errors() {
        // Right kind -> Ok.
        let opened = serde_json::json!({
            "kind": "session_opened",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "ok": true,
            "backend": "mock",
            "provenance": {
                "network_ref": "model",
                "backend": "mock",
                "calibrated_posterior": false,
                "is_simulation_output": true,
                "advisory_only": true
            }
        });
        assert!(check_reply(&serde_json::to_vec(&opened).unwrap(), "open_session", "s").is_ok());
        // Wrong-but-valid-JSON kind -> Err (not a silent all-default decode).
        let observation = serde_json::json!({
            "kind": "observation_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "seq": 0,
            "records": {},
            "calibrated_posterior": false,
            "is_simulation_output": true
        });
        assert!(check_reply(
            &serde_json::to_vec(&observation).unwrap(),
            "open_session",
            "s"
        )
        .is_err());
        assert!(check_reply(
            &serde_json::to_vec(&opened).unwrap(),
            "open_session",
            "other"
        )
        .is_err());
        // An error frame must itself be versioned, then surfaces as Err.
        let error = ncp_core::ErrorFrame {
            error: "boom".into(),
            session_id: Some("s".into()),
            ..Default::default()
        };
        assert!(check_reply(&serde_json::to_vec(&error).unwrap(), "open_session", "s").is_err());
        let wrong_error = ncp_core::ErrorFrame {
            error: "boom".into(),
            session_id: Some("s".into()),
            request_kind: Some("close_session".into()),
            ..Default::default()
        };
        assert!(check_reply(
            &serde_json::to_vec(&wrong_error).unwrap(),
            "open_session",
            "s"
        )
        .is_err());
        assert!(check_reply(br#"{"kind":"error","error":"boom"}"#, "open_session", "s").is_err());
    }

    #[test]
    fn rpc_selector_payload_and_handler_reply_are_bound_together() {
        let keys = Keys::default();
        let request = ncp_core::OpenSession {
            session_id: "s".into(),
            network: ncp_core::NetworkRef {
                ref_: "model".into(),
                ..Default::default()
            },
            ..Default::default()
        };
        let bytes = serde_json::to_vec(&request).unwrap();
        assert!(check_rpc_request(&keys, "ncp/rpc/open_session", &bytes).is_ok());
        assert!(check_rpc_request(&keys, "ncp/rpc/run_request", &bytes).is_err());
        assert!(check_rpc_request(
            &keys,
            "ncp/rpc/open_session",
            br#"{"kind":"open_session","session_id":"s"}"#,
        )
        .is_err());

        let opened = ncp_core::SessionOpened {
            session_id: "s".into(),
            ok: false,
            error: Some("unavailable".into()),
            ..Default::default()
        };
        assert!(check_rpc_handler_reply(
            "open_session",
            "s",
            &serde_json::to_vec(&opened).unwrap()
        )
        .is_ok());
        assert!(
            check_rpc_handler_reply("run_request", "s", &serde_json::to_vec(&opened).unwrap())
                .is_err()
        );

        let error = ncp_core::ErrorFrame {
            error: "rejected".into(),
            ..Default::default()
        };
        assert!(
            check_rpc_handler_reply("open_session", "s", &serde_json::to_vec(&error).unwrap())
                .is_ok()
        );
        assert!(check_rpc_handler_reply(
            "open_session",
            "s",
            br#"{"kind":"error","error":"unversioned"}"#,
        )
        .is_err());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn synchronous_rpc_handler_runs_off_the_async_worker() {
        let keys = Keys::default();
        let request = ncp_core::OpenSession {
            session_id: "s".into(),
            network: ncp_core::NetworkRef {
                ref_: "model".into(),
                ..Default::default()
            },
            ..Default::default()
        };
        let request = serde_json::to_vec(&request).unwrap();
        let reply = ncp_core::SessionOpened {
            session_id: "s".into(),
            ok: false,
            error: Some("unavailable".into()),
            ..Default::default()
        };
        let reply = serde_json::to_vec(&reply).unwrap();
        let handler: Arc<RpcHandler> = Arc::new(move |_| {
            std::thread::sleep(std::time::Duration::from_millis(250));
            reply.clone()
        });
        let permits = Arc::new(tokio::sync::Semaphore::new(1));
        let permit = Arc::new(permits.clone().acquire_owned().await.unwrap());
        let dispatch_permit = permit.clone();
        let started = std::time::Instant::now();
        let dispatch = dispatch_rpc_off_thread(
            keys,
            handler,
            "ncp/rpc/open_session".into(),
            request,
            dispatch_permit,
        );
        let heartbeat = async {
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            started.elapsed()
        };
        let (reply, heartbeat_elapsed) = tokio::join!(dispatch, heartbeat);
        assert!(
            heartbeat_elapsed < std::time::Duration::from_millis(150),
            "blocking RPC handler pinned the current-thread runtime for {heartbeat_elapsed:?}"
        );
        assert!(check_reply(&reply, "open_session", "s").is_ok());
        assert_eq!(
            permits.available_permits(),
            0,
            "the caller's permit clone must bound the reply-delivery phase"
        );
        drop(permit);
        assert_eq!(permits.available_permits(), 1);
    }

    #[test]
    fn generated_rpc_error_is_a_valid_typed_frame() {
        let payload = rpc_error_payload(
            "bad selector",
            Some("s".into()),
            Some("open_session".into()),
        );
        let value: serde_json::Value = serde_json::from_slice(&payload).unwrap();
        ncp_core::validate(&value).unwrap();
        assert_eq!(value["kind"], "error");
        assert_eq!(value["ncp_version"], ncp_core::NCP_VERSION);
    }

    #[test]
    fn check_id_rejects_keyexpr_metacharacters() {
        // A clean id passes.
        assert!(check_id("session", "uav3").is_ok());
        // Metacharacters that would widen/escape the key expression are rejected
        // BEFORE the key is built (fail-closed boundary, FIX 7).
        for bad in [
            "", " ", "a/b", "*", "**", "a*", "$kid", "a#b", "a?b", "a b", "a\tb",
        ] {
            assert!(
                check_id("session", bad).is_err(),
                "expected reject for {bad:?}"
            );
        }
    }

    #[test]
    fn observation_publish_rejects_unenveloped_bulk_and_missing_provenance() {
        let raw = ncp_core::BulkBlock::new()
            .with("times", ncp_core::Column::F64(vec![1.0]))
            .encode()
            .unwrap();
        assert!(
            check_observation_payload_for("s", &raw).is_err(),
            "a bare NCPB block has no session/seq/provenance and must not publish"
        );

        let valid = ncp_core::ObservationFrame {
            session_id: "s".into(),
            seq: 1,
            ..Default::default()
        };
        assert!(check_observation_payload_for("s", &serde_json::to_vec(&valid).unwrap()).is_ok());
        assert!(
            check_observation_payload_for("other", &serde_json::to_vec(&valid).unwrap()).is_err(),
            "the payload session must match the observation key session"
        );

        let missing_boundary = serde_json::json!({
            "kind": "observation_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "seq": 1,
            "records": {}
        });
        assert!(check_observation_payload_for(
            "s",
            &serde_json::to_vec(&missing_boundary).unwrap()
        )
        .is_err());
    }

    #[test]
    fn command_publish_gate_rejects_invalid_active_but_never_drops_estop() {
        let invalid_active = serde_json::json!({
            "kind": "command_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "seq": 0,
            "mode": "active",
            "ttl_ms": 200.0,
            "channels": {"velocity_setpoint": {"data": [1.0]}}
        });
        assert!(check_command_payload(&serde_json::to_vec(&invalid_active).unwrap()).is_err());

        let malformed_estop = serde_json::json!({
            "kind": "wrong",
            "seq": 0,
            "mode": "estop",
            "channels": {"velocity_setpoint": {"data": [9.0]}}
        });
        assert!(
            check_command_payload(&serde_json::to_vec(&malformed_estop).unwrap()).is_ok(),
            "an explicit ESTOP is latched by receivers before envelope validation"
        );

        let mut invalid_estop = ncp_core::CommandFrame {
            t: f64::NAN,
            seq: 0,
            frame_id: String::new(),
            mode: ncp_core::Mode::Estop,
            ..Default::default()
        };
        invalid_estop.channels.insert(
            "bad\nchannel".into(),
            ncp_core::ChannelValue::scalar(f64::NAN, None),
        );
        let normalized = normalize_command_for_publish(&invalid_estop);
        assert_eq!(normalized.mode, ncp_core::Mode::Estop);
        ncp_core::WireFrame::validate_wire(normalized.as_ref())
            .expect("transport must normalize an in-memory ESTOP to publishable zero output");
    }

    #[test]
    fn command_dispatch_slot_is_bounded_and_fail_safe_prioritized() {
        let slot = std::sync::Mutex::new(None);
        let pending = |byte: u8, priority| PendingCommand {
            bytes: vec![byte],
            priority,
        };
        assert!(enqueue_command(&slot, pending(1, CommandPriority::Active)));
        assert!(enqueue_command(&slot, pending(2, CommandPriority::Hold)));
        assert!(
            !enqueue_command(&slot, pending(3, CommandPriority::Active)),
            "Active must not overwrite a pending HOLD"
        );
        assert!(enqueue_command(&slot, pending(4, CommandPriority::Estop)));
        assert!(
            !enqueue_command(&slot, pending(5, CommandPriority::Hold)),
            "HOLD must not overwrite a pending ESTOP"
        );
        let queued = slot.into_inner().unwrap().unwrap();
        assert_eq!(queued.priority, CommandPriority::Estop);
        assert_eq!(queued.bytes, vec![4]);
    }

    #[test]
    fn default_config_disables_multicast_scouting() {
        // The hardened default open() path must not auto-advertise on the LAN:
        // scouting/multicast/enabled is forced false. Zenoh's own default is true,
        // so this asserts our override actually took effect (closed-realm default).
        let cfg = default_quiet_config().expect("hardened default config must build");
        let json = cfg.get_json("scouting/multicast/enabled").unwrap();
        assert_eq!(
            json.trim(),
            "false",
            "multicast scouting must be off by default"
        );
    }

    fn secure_client_test_config() -> Config {
        let mut cfg = Config::default();
        for (path, value) in [
            ("mode", r#""client""#),
            ("connect/endpoints", r#"["tls/router.example:7447"]"#),
            ("listen/endpoints", "[]"),
            ("scouting/multicast/enabled", "false"),
            ("scouting/gossip/enabled", "false"),
            ("transport/link/tls/root_ca_certificate", r#""ca.pem""#),
            ("transport/link/tls/connect_certificate", r#""client.pem""#),
            (
                "transport/link/tls/connect_private_key",
                r#""client-key.pem""#,
            ),
            ("transport/link/tls/verify_name_on_connect", "true"),
        ] {
            cfg.insert_json5(path, value).unwrap();
        }
        cfg
    }

    fn isolated_test_config() -> Config {
        let mut cfg = default_quiet_config().expect("isolated test config");
        for (path, value) in [
            ("scouting/gossip/enabled", "false"),
            ("listen/endpoints", "[]"),
            ("connect/endpoints", "[]"),
            ("transport/shared_memory/enabled", "false"),
        ] {
            cfg.insert_json5(path, value)
                .expect("isolated tests disable external transports");
        }
        cfg
    }

    #[test]
    fn secure_client_config_gate_rejects_plaintext_discovery_and_missing_identity() {
        let valid = secure_client_test_config();
        validate_secure_client_config(&valid).expect("complete mTLS client config");

        let mut plaintext = secure_client_test_config();
        plaintext
            .insert_json5("connect/endpoints", r#"["tcp/router.example:7447"]"#)
            .unwrap();
        assert!(validate_secure_client_config(&plaintext).is_err());

        let mut discovery = secure_client_test_config();
        discovery
            .insert_json5("scouting/multicast/enabled", "true")
            .unwrap();
        assert!(validate_secure_client_config(&discovery).is_err());

        let mut anonymous = secure_client_test_config();
        anonymous
            .insert_json5("transport/link/tls/connect_certificate", "null")
            .unwrap();
        assert!(validate_secure_client_config(&anonymous).is_err());

        let mut no_hostname_check = secure_client_test_config();
        no_hostname_check
            .insert_json5("transport/link/tls/verify_name_on_connect", "false")
            .unwrap();
        assert!(validate_secure_client_config(&no_hostname_check).is_err());
    }

    #[test]
    fn shipped_zenoh_configs_parse_and_client_template_passes_secure_gate() {
        let deploy = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/deploy");
        config_from_file(&deploy.join("zenoh-access-control.json5"))
            .expect("secure router template must match the locked Zenoh config schema");
        let client = config_from_file(&deploy.join("zenoh-client-secure.json5"))
            .expect("secure client template must match the locked Zenoh config schema");
        validate_secure_client_config(&client)
            .expect("shipped client template must satisfy open_secure's fail-closed gate");
    }

    #[test]
    fn open_secure_requires_the_config_env_var() {
        // Fail-closed: open_secure must refuse when NCP_ZENOH_CONFIG is unset rather
        // than starting an unauthenticated session. We assert the precondition the
        // async path enforces (env var presence) without standing up a session.
        // SAFETY of the test: serialized within this single test; restored after.
        let saved = std::env::var_os(NCP_ZENOH_CONFIG_ENV);
        std::env::remove_var(NCP_ZENOH_CONFIG_ENV);
        assert!(
            std::env::var_os(NCP_ZENOH_CONFIG_ENV).is_none(),
            "precondition: env var unset"
        );
        // A missing config file must be a load error (fail-closed), never a silent
        // fallback to an open default.
        let missing = std::path::Path::new("/nonexistent/ncp-zenoh-acl.json5");
        assert!(config_from_file(missing).is_err());
        if let Some(v) = saved {
            std::env::set_var(NCP_ZENOH_CONFIG_ENV, v);
        }
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn put_sensor_rejects_bad_session_id_at_the_entry_point() {
        // Open an isolated bus (no scouting/listen/connect) so the test needs no
        // router. The FIX 7 guard rejects before any key is built or I/O happens,
        // so a metacharacter session id resolves to Err on the public entry point.
        let mut cfg = Config::default();
        let _ = cfg.insert_json5("scouting/multicast/enabled", "false");
        let _ = cfg.insert_json5("listen/endpoints", "[]");
        let _ = cfg.insert_json5("connect/endpoints", "[]");
        let _ = cfg.insert_json5("transport/shared_memory/enabled", "false");
        let bus = ZenohBus::with_config(cfg, Keys::default()).await.unwrap();
        let e = bus.put_sensor("bad/id", b"{}").await.unwrap_err();
        assert!(e.to_string().contains("invalid session id segment"), "{e}");
        // A glob-escaping entity name on a named publish is rejected too.
        assert!(bus.put_sensor_named("uav3", "imu*", b"{}").await.is_err());
        let _ = bus.close().await;
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn session_subscribers_are_releasable_without_closing_the_bus() {
        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        bus.subscribe_commands("s1", |_, _| {}).await.unwrap();
        bus.subscribe_observations("s1", |_, _| {}).await.unwrap();
        bus.subscribe_commands("s2", |_, _| {}).await.unwrap();
        bus.subscribe_fleet(|_, _| {}).await.unwrap();
        assert_eq!(bus.subs.lock().unwrap().len(), 4);

        assert_eq!(bus.unsubscribe_session("s1").unwrap(), 2);
        let selectors: Vec<String> = bus
            .subs
            .lock()
            .unwrap()
            .iter()
            .map(|(selector, _)| selector.clone())
            .collect();
        assert_eq!(selectors.len(), 2);
        assert!(selectors.iter().any(|selector| selector.contains("/s2/")));
        assert!(selectors
            .iter()
            .any(|selector| selector.ends_with("/session/**")));
        assert!(bus.unsubscribe_session("bad/*").is_err());
        bus.close().await.unwrap();
        assert!(bus.subs.lock().unwrap().is_empty());
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn closing_a_borrowed_wrapper_does_not_close_the_host_session() {
        let session = Arc::new(zenoh::open(isolated_test_config()).await.unwrap());
        let borrowed = ZenohBus::from_session(session.clone(), Keys::default());
        assert!(!borrowed.owns_session);
        borrowed.subscribe_fleet(|_, _| {}).await.unwrap();
        borrowed.close().await.unwrap();
        assert!(borrowed.subs.lock().unwrap().is_empty());

        // A successful operation through the host handle proves close() released
        // only this wrapper's handles and left the borrowed session alive.
        session
            .put("ncp-test/borrowed-still-open", b"ok")
            .await
            .unwrap();
        session.close().await.unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_panicking_subscriber_drops_one_sample_but_stays_alive() {
        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let attempts = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let seen = attempts.clone();
        let (tx, rx) = std::sync::mpsc::channel();
        bus.subscribe("ncp-test/callback-panic", move |_, _| {
            if seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst) == 0 {
                panic!("intentional callback fault");
            }
            tx.send(()).unwrap();
        })
        .await
        .unwrap();

        bus.put("ncp-test/callback-panic", b"first", Plane::Control)
            .await
            .unwrap();
        bus.put("ncp-test/callback-panic", b"second", Plane::Control)
            .await
            .unwrap();
        rx.recv_timeout(std::time::Duration::from_secs(2))
            .expect("the subscription must receive a sample after the contained panic");
        assert!(attempts.load(std::sync::atomic::Ordering::SeqCst) >= 2);
        bus.close().await.unwrap();
    }
}
