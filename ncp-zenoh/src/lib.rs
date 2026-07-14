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
//! - **perception** — CongestionControl=DROP + DataHigh priority; the typed control
//!   transport keeps one replace-latest receive slot;
//! - **action** — express + DROP + RealTime priority (lowest-latency setpoint),
//!   safety-gated by the sender with one ESTOP-prioritized publish slot;
//! - **observation** — DROP + Data priority; the typed subscriber uses an explicit
//!   64-frame drop-oldest queue and exposes its cumulative drop counter;
//! - **control** — CongestionControl=BLOCK plus a 128-request admission limit that
//!   rejects overflow with a typed busy error.
//!
//! Async API (native to Zenoh; all NCP consumers run on tokio). The in-process
//! [`ncp_core::Bus`] / [`ncp_core::LocalBus`] remain for tests and co-process use.
//!
//! ## Security: the realm is addressing, not a credential
//!
//! The realm string (`{realm}/…`) is *addressing*, not authorization — anyone who
//! can reach the bus and knows (or guesses) the realm can publish/subscribe on it.
//! It is **not** a secret or a credential.
//!
//! The default [`ZenohBus::open`] / [`ZenohBus::open_realm`] path is hardened to be
//! quiet-by-default: multicast scouting is **disabled** so a default deployment does
//! not auto-advertise on the LAN (peers still connect via explicit
//! `connect`/`listen` endpoints in a supplied config).
//!
//! The shipped ACL/TLS templates and strict client-config validator are only
//! configuration prerequisites. The current Zenoh callback surface used by this
//! adapter does not expose a transport-authenticated remote principal that can be
//! bound to an NCP [`ncp_core::IdentityClaim`]. Consequently
//! [`ZenohBus::open_secure`] intentionally fails closed, and generic open/config
//! methods must not be represented as `production-secure`.

use ncp_core::keys::{valid_id_segment, Keys};
use std::sync::Arc;
use zenoh::qos::{CongestionControl, Priority};
use zenoh::{Config, Session};

/// Coordinated package/wire identity exposed without requiring a second import.
pub use ncp_core::{BUILD_IDENTITY, NCP_VERSION, NORMATIVE_CONTRACT_DIGEST, PACKAGE_VERSION};
/// Re-export so consumers can configure Zenoh without depending on `zenoh`.
pub use zenoh::Config as ZenohConfig;

/// Environment variable naming a Zenoh config file (json5/json) to load. When set,
/// [`ZenohBus::open`] / [`ZenohBus::open_realm`] (and the `ncp-gateway` binary) load
/// it instead of the hardened default. For [`ZenohBus::open_secure`]'s fail-closed
/// config preflight, point it at a configured copy of
/// `deploy/zenoh-client-secure.json5`, never the router ACL file.
pub const NCP_ZENOH_CONFIG_ENV: &str = "NCP_ZENOH_CONFIG";

/// The stable adapter currently cannot bind a callback's payload identity claim to
/// a verified transport principal. `production-secure` therefore remains
/// unavailable and [`ZenohBus::open_secure`] fails closed.
pub const PRODUCTION_SECURE_IDENTITY_BINDING_AVAILABLE: bool = false;

const PRODUCTION_SECURE_IDENTITY_BINDING_ERROR: &str =
    "production-secure is unavailable in ncp-zenoh: the current Zenoh callback surface does not \
     expose a transport-authenticated peer principal, so IdentityClaim cannot be bound to the \
     verified transport identity";

fn require_production_secure_identity_binding() -> Result<()> {
    Err(ZenohError(
        PRODUCTION_SECURE_IDENTITY_BINDING_ERROR.to_owned(),
    ))
}

/// Build the hardened default config: Zenoh defaults with **multicast scouting
/// disabled** so a default deployment does not auto-advertise on the LAN. Peers can
/// still connect via explicit `connect`/`listen` endpoints supplied in a config
/// file (see [`NCP_ZENOH_CONFIG_ENV`]). This is addressing-hygiene, not auth. The
/// current adapter has no production-secure identity-binding path; see
/// [`PRODUCTION_SECURE_IDENTITY_BINDING_AVAILABLE`].
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

/// Validate the TLS-only client configuration prerequisite. This proves only the
/// local config shape; it cannot prove or provide callback peer-identity binding.
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
    /// Simulation/diagnostic observations. Read-only subscribers may shed old
    /// frames under pressure; this plane never inherits control authority.
    Observation,
    /// Lifecycle RPC requests and replies. Reliable.
    Control,
}

impl Plane {
    fn congestion(self) -> CongestionControl {
        match self {
            // Drop-oldest on the wire for high-rate / latency-critical streams.
            Plane::Perception | Plane::Action | Plane::Observation => CongestionControl::Drop,
            Plane::Control => CongestionControl::Block,
        }
    }
    fn priority(self) -> Priority {
        match self {
            Plane::Action => Priority::RealTime,
            Plane::Perception => Priority::DataHigh,
            Plane::Observation | Plane::Control => Priority::Data,
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

fn oversized_rpc_reply_error(actual_bytes: usize) -> ZenohError {
    ZenohError(format!(
        "NCP-LIMIT-001: RPC reply frame byte limit exceeded ({actual_bytes} > {})",
        ncp_core::bounded_json::MAX_FRAME_BYTES
    ))
}

/// Copy a Zenoh payload only after its segmented representation has passed the
/// universal frame-byte limit. `ZBytes::len` does not flatten the payload; keeping
/// this check in one helper prevents an ingress path from accidentally calling
/// `to_bytes` (and allocating an attacker-sized contiguous buffer) first.
fn copy_admitted_zbytes(payload: &zenoh::bytes::ZBytes) -> Option<Vec<u8>> {
    (payload.len() <= ncp_core::bounded_json::MAX_FRAME_BYTES)
        .then(|| payload.to_bytes().into_owned())
}

fn validate_and_copy_rpc_reply(
    payload: &zenoh::bytes::ZBytes,
    request_kind: &str,
    session_id: &str,
) -> Result<Vec<u8>> {
    let bytes =
        copy_admitted_zbytes(payload).ok_or_else(|| oversized_rpc_reply_error(payload.len()))?;
    ncp_core::validate_rpc_reply_for(request_kind, session_id, &bytes).map_err(|error| {
        ZenohError(bounded_diagnostic(format_args!(
            "invalid NCP RPC reply: {error}"
        )))
    })?;
    Ok(bytes)
}

fn bounded_transport_reply_error(payload: &zenoh::bytes::ZBytes) -> String {
    if payload.len() > ncp_core::bounded_json::MAX_FRAME_BYTES {
        return oversized_rpc_reply_error(payload.len()).0;
    }

    let mut prefix = Vec::with_capacity(payload.len().min(MAX_RPC_DIAGNOSTIC_BYTES));
    for slice in payload.slices() {
        let remaining = MAX_RPC_DIAGNOSTIC_BYTES.saturating_sub(prefix.len());
        if remaining == 0 {
            break;
        }
        prefix.extend_from_slice(&slice[..slice.len().min(remaining)]);
    }
    let text = String::from_utf8_lossy(&prefix);
    if prefix.len() < payload.len() {
        bounded_diagnostic(format_args!("{text}..."))
    } else {
        bounded_diagnostic(format_args!("{text}"))
    }
}

#[derive(Debug)]
enum TypedCommandPublishError {
    /// The payload/route/fence rejected before transport delivery was attempted.
    Rejected(ZenohError),
    /// The stream position was consumed, but Zenoh could not prove whether the put
    /// reached any subscriber. Retrying the same position is forbidden.
    DeliveryAmbiguous(ZenohError),
}

impl TypedCommandPublishError {
    fn into_inner(self) -> ZenohError {
        match self {
            Self::Rejected(error) | Self::DeliveryAmbiguous(error) => error,
        }
    }
}

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

fn check_live_session_ref(session: &ncp_core::SessionRef) -> Result<()> {
    if ncp_core::is_canonical_uuid_v4(&session.generation) {
        Ok(())
    } else {
        Err(ZenohError(
            "expected live session generation must be a canonical lowercase UUIDv4".into(),
        ))
    }
}

/// Session-bound perception-plane gate: the `SensorFrame` must be valid and its
/// payload `session_id` must exactly match the session encoded in the Zenoh key.
fn check_sensor_payload_for(
    session_id: &str,
    session: &ncp_core::SessionRef,
    payload: &[u8],
) -> Result<ncp_core::SensorFrame> {
    ncp_core::decode_sensor_plane_payload_for(session_id, session, payload)
        .map_err(|e| ZenohError(format!("refusing to publish sensor frame: {e}")))
}

/// Live-session-bound action-plane gate. Every remote command, including ESTOP,
/// requires a complete kind/version/stream/session envelope. ESTOP may omit only
/// the authority lease; stale or cross-session input is rejected before callback.
fn check_command_payload_for(
    session_id: &str,
    session: &ncp_core::SessionRef,
    payload: &[u8],
) -> Result<ncp_core::CommandFrame> {
    ncp_core::decode_command_plane_payload_for(session_id, session, payload)
        .map_err(|e| ZenohError(format!("refusing to publish command frame: {e}")))
}

/// Publish gate for the observation plane. The shipped transport accepts only a
/// complete, versioned JSON `observation_frame` with its own `stream.seq >= 1` and
/// a `source` position identifying the driving sensor (`seq == 0` is pull-only).
/// A bare NCPB column block is deliberately rejected: it carries no session, seq,
/// timestamp, or honesty-boundary provenance. `BulkBlock` remains a local/negotiated
/// payload codec until a fully specified envelope is implemented across every SDK.
fn check_observation_payload_for(
    session_id: &str,
    session: &ncp_core::SessionRef,
    payload: &[u8],
) -> Result<ncp_core::ObservationFrame> {
    ncp_core::decode_observation_plane_payload_for(session_id, session, payload)
        .map_err(|e| ZenohError(format!("refusing observation frame: {e}")))
}

fn accept_publisher_stream(
    fence: &std::sync::Mutex<ncp_core::StreamMonotonicityFence>,
    route: &str,
    kind: &str,
    session: &ncp_core::SessionRef,
    stream: &ncp_core::StreamPosition,
) -> Result<()> {
    let mut fence = fence.lock().map_err(|_| {
        ZenohError("typed publisher stream fence is poisoned; refusing publish".into())
    })?;
    fence
        .accept(route, kind, session, stream)
        .map_err(|error| ZenohError(format!("typed publisher stream rejected: {error}")))
}

fn accept_subscriber_stream(
    fence: &std::sync::Mutex<ncp_core::StreamMonotonicityFence>,
    route: &str,
    kind: &str,
    session: &ncp_core::SessionRef,
    stream: &ncp_core::StreamPosition,
) -> bool {
    let Ok(mut fence) = fence.lock() else {
        return false;
    };
    fence.accept(route, kind, session, stream).is_ok()
}

/// Validate both layers of lifecycle routing: the selector grants authority for
/// one verb, and the payload must be that same complete/versioned request. This
/// prevents a client authorized only for one exact RPC key from smuggling a
/// different lifecycle message through it.
#[derive(Debug)]
struct RpcRequestError {
    code: ncp_core::RpcErrorCode,
    detail: String,
}

impl std::fmt::Display for RpcRequestError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.detail)
    }
}

fn check_rpc_request(
    keys: &Keys,
    selector: &str,
    payload: &[u8],
) -> std::result::Result<serde_json::Value, RpcRequestError> {
    let selector_kind = selector_request_kind(keys, selector).ok_or_else(|| RpcRequestError {
        code: ncp_core::RpcErrorCode::InvalidMessage,
        detail: format!("unsupported NCP RPC selector {selector:?}"),
    })?;
    let (request, _) =
        ncp_core::validate_rpc_request_for(&selector_kind, payload).map_err(|error| {
            RpcRequestError {
                code: error.rpc_error_code(),
                detail: error.to_string(),
            }
        })?;
    Ok(request)
}

fn check_rpc_handler_reply(request_kind: &str, session_id: &str, payload: &[u8]) -> Result<()> {
    ncp_core::validate_rpc_reply_for(request_kind, session_id, payload)
        .map(drop)
        .map_err(|error| ZenohError(bounded_diagnostic(format_args!("{error}"))))
}

fn rpc_error_payload(
    code: ncp_core::RpcErrorCode,
    error: impl std::fmt::Display,
    session_id: Option<String>,
    session: Option<ncp_core::SessionRef>,
    request_kind: Option<String>,
) -> Vec<u8> {
    let reply = ncp_core::rpc_error_payload_with_session(
        code,
        bounded_diagnostic(format_args!("{error}")),
        session_id,
        session,
        request_kind,
    );
    if reply.len() <= ncp_core::bounded_json::MAX_FRAME_BYTES {
        return reply;
    }
    ncp_core::rpc_error_payload_with_session(
        ncp_core::RpcErrorCode::JsonLimit(ncp_core::bounded_json::JsonLimitCode::FrameBytes),
        "generated RPC error reply exceeded the frame byte limit",
        None,
        None,
        None,
    )
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

fn request_session_ref(value: &serde_json::Value) -> Option<ncp_core::SessionRef> {
    value
        .get("session")
        .and_then(|session| serde_json::from_value(session.clone()).ok())
        .filter(|session: &ncp_core::SessionRef| {
            ncp_core::is_canonical_uuid_v4(&session.generation)
        })
}

type RpcHandler = dyn Fn(Vec<u8>) -> Vec<u8> + Send + Sync;
type RetainedSubscribers = Arc<std::sync::Mutex<Vec<(String, zenoh::pubsub::Subscriber<()>)>>>;
type PublisherStreamFence = Arc<std::sync::Mutex<ncp_core::StreamMonotonicityFence>>;
type ObservationItem = (String, Vec<u8>);
type ObservationQueue = Arc<std::sync::Mutex<std::collections::VecDeque<ObservationItem>>>;
type ObservationWorkers = Arc<std::sync::Mutex<Vec<(String, tokio::task::JoinHandle<()>)>>>;

/// Bound concurrent blocking/backend calls. Control RPC is rare; this ceiling is
/// the normative control queue capacity while preventing a hostile client from
/// turning one queryable into unbounded tasks/memory.
const MAX_IN_FLIGHT_RPC_REQUESTS: usize = 128;
/// Normative observation subscriber queue capacity from `contract/limits.v1.json`.
const OBSERVATION_QUEUE_CAPACITY: usize = 64;

fn enqueue_observation(
    queue: &std::sync::Mutex<std::collections::VecDeque<ObservationItem>>,
    item: ObservationItem,
    drops: &std::sync::atomic::AtomicU64,
) {
    let mut queue = queue.lock().unwrap_or_else(|error| error.into_inner());
    if queue.len() >= OBSERVATION_QUEUE_CAPACITY {
        queue.pop_front();
        drops.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    }
    queue.push_back(item);
}

async fn dispatch_observations<F>(
    queue: ObservationQueue,
    notify: Arc<tokio::sync::Notify>,
    callback: Arc<F>,
) where
    F: Fn(String, Vec<u8>) + Send + Sync + 'static,
{
    loop {
        notify.notified().await;
        loop {
            let item = queue
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .pop_front();
            let Some((key, payload)) = item else {
                break;
            };
            if std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                callback(key, payload);
            }))
            .is_err()
            {
                eprintln!("ncp-zenoh: observation callback panicked; sample dropped");
            }
        }
    }
}

fn dispatch_rpc(keys: &Keys, handler: &RpcHandler, selector: &str, req: Vec<u8>) -> Vec<u8> {
    let selector_kind = selector_request_kind(keys, selector);
    let parsed = ncp_core::bounded_json::parse_value(&req).ok();
    let session_id = parsed.as_ref().and_then(request_session_id);
    let session = parsed.as_ref().and_then(request_session_ref);
    match check_rpc_request(keys, selector, &req) {
        Err(error) => rpc_error_payload(error.code, error, session_id, session, selector_kind),
        Ok(request) => {
            let request_kind = ncp_core::message_kind(&request)
                .expect("validated request carries kind")
                .to_owned();
            let request_session = request_session_id(&request)
                .expect("validated lifecycle request carries a safe session_id");
            let request_session_ref = request_session_ref(&request);
            match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| handler(req))) {
                Ok(reply) => {
                    match check_rpc_handler_reply(&request_kind, &request_session, &reply) {
                        Ok(()) => reply,
                        Err(error) => rpc_error_payload(
                            ncp_core::RpcErrorCode::ContainedInternalFailure,
                            error,
                            Some(request_session),
                            request_session_ref,
                            Some(request_kind),
                        ),
                    }
                }
                Err(_) => rpc_error_payload(
                    ncp_core::RpcErrorCode::ContainedInternalFailure,
                    "RPC handler panicked",
                    Some(request_session),
                    request_session_ref,
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
    let parsed = ncp_core::bounded_json::parse_value(&req).ok();
    let error_session_id = parsed.as_ref().and_then(request_session_id);
    let error_session = parsed.as_ref().and_then(request_session_ref);
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
            ncp_core::RpcErrorCode::ContainedInternalFailure,
            format_args!("RPC dispatch task failed: {error}"),
            error_session_id,
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
    // Clone-shared, bounded, and deliberately non-evicting. A put error leaves
    // the accepted position consumed because delivery may be ambiguous; reopening
    // it would permit a replay after a partial transport send.
    publisher_streams: PublisherStreamFence,
    // Retain subscriber handles for the session lifetime — a dropped Zenoh
    // Subscriber undeclares its subscription, so callbacks would stop firing.
    // Keep each selector so a closed NCP session can release only its own handles.
    subs: RetainedSubscribers,
    // Dedicated observation callbacks run behind the normative bounded
    // drop-oldest queue rather than inline on Zenoh's receive task.
    observation_workers: ObservationWorkers,
    observation_queue_drops: Arc<std::sync::atomic::AtomicU64>,
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
    /// addressing, not a credential, and this path is not `production-secure`.
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
    /// neither validates secure-client invariants nor binds authenticated peer
    /// identity, so it must not be represented as `production-secure`.
    pub async fn with_config_file(path: impl AsRef<std::path::Path>, keys: Keys) -> Result<Self> {
        Self::with_config(config_from_file(path.as_ref())?, keys).await
    }

    /// Fail-closed placeholder for the unavailable `production-secure` adapter.
    ///
    /// The method loads and validates the TLS-only client config named by
    /// [`NCP_ZENOH_CONFIG_ENV`], then refuses to open: the Zenoh callbacks used by
    /// this adapter expose no transport-authenticated remote principal to bind to
    /// an NCP `IdentityClaim`. Configured mTLS and router ACLs alone do not close
    /// that payload/transport identity boundary.
    pub async fn open_secure(keys: Keys) -> Result<Self> {
        let path = std::env::var_os(NCP_ZENOH_CONFIG_ENV).ok_or_else(|| {
            ZenohError(format!(
                "open_secure requires {NCP_ZENOH_CONFIG_ENV} to name a strict Zenoh \
                 client config (start from deploy/zenoh-client-secure.json5)"
            ))
        })?;
        let config = config_from_file(std::path::Path::new(&path))?;
        Self::with_secure_config(config, keys).await
    }

    async fn with_secure_config(config: Config, keys: Keys) -> Result<Self> {
        validate_secure_client_config(&config)?;
        require_production_secure_identity_binding()?;
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
            publisher_streams: Arc::new(std::sync::Mutex::new(
                ncp_core::StreamMonotonicityFence::default(),
            )),
            subs: Arc::new(std::sync::Mutex::new(Vec::new())),
            observation_workers: Arc::new(std::sync::Mutex::new(Vec::new())),
            observation_queue_drops: Arc::new(std::sync::atomic::AtomicU64::new(0)),
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
            publisher_streams: Arc::new(std::sync::Mutex::new(
                ncp_core::StreamMonotonicityFence::default(),
            )),
            subs: Arc::new(std::sync::Mutex::new(Vec::new())),
            observation_workers: Arc::new(std::sync::Mutex::new(Vec::new())),
            observation_queue_drops: Arc::new(std::sync::atomic::AtomicU64::new(0)),
            owns_session: false,
        }
    }

    pub fn keys(&self) -> &Keys {
        &self.keys
    }
    /// Raw Zenoh session handle. Operations through it bypass NCP decoding,
    /// live-session binding, monotonicity fencing, and plane-specific admission.
    pub fn session(&self) -> &Arc<Session> {
        &self.session
    }

    /// Cumulative valid observation frames dropped from this wrapper's bounded
    /// subscriber queues. This is the value exported as
    /// `ncp_queue_drops_total{plane="observation"}` by an instrumentation adapter;
    /// session identifiers must not become metric labels.
    pub fn observation_queue_drops_total(&self) -> u64 {
        self.observation_queue_drops
            .load(std::sync::atomic::Ordering::Relaxed)
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
        let request = ncp_core::bounded_json::parse_value(message)
            .map_err(err("parse bounded NCP RPC request"))?;
        ncp_core::validate(&request).map_err(err("invalid NCP RPC request"))?;
        let kind = ncp_core::message_kind(&request)
            .expect("validated NCP request always carries a string kind");
        let session_id = request
            .get("session_id")
            .and_then(serde_json::Value::as_str)
            .expect("validated lifecycle request always carries a string session_id");
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
                Ok(sample) => {
                    return validate_and_copy_rpc_reply(sample.payload(), kind, session_id)
                }
                Err(error) => last_err = Some(bounded_transport_reply_error(error.payload())),
            }
        }
        match last_err {
            Some(error) => Err(ZenohError(bounded_diagnostic(format_args!(
                "rpc error reply for {rpc_key}: {error}"
            )))),
            None => Err(ZenohError(format!("no reply for {rpc_key}"))),
        }
    }

    /// Publish a `SensorFrame` (perception plane) for a session.
    ///
    /// Wire 1.0 candidate: the payload is validated against the caller-supplied
    /// live session binding before it leaves this peer (own stream position,
    /// compatible version, right kind). [`Self::put`] remains an explicitly raw,
    /// untrusted escape hatch whose samples are fenced by typed subscribers. The
    /// stream position is consumed before the awaited put; a put error is
    /// delivery-ambiguous and retrying the same position is rejected rather than
    /// silently reopening replay.
    pub async fn put_sensor(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        payload: &[u8],
    ) -> Result<()> {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        let route = self.keys.sensor(session_id);
        let frame = check_sensor_payload_for(session_id, session, payload)?;
        accept_publisher_stream(
            &self.publisher_streams,
            &route,
            "sensor_frame",
            session,
            &frame.stream,
        )?;
        self.put(&route, payload, Plane::Perception).await
    }

    /// Subscribe to the command (action) plane — the plant receives `CommandFrame`s.
    pub async fn subscribe_commands<F>(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        callback: F,
    ) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        let selector = self.keys.command(session_id);
        let expected_route = selector.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = std::sync::Mutex::new(ncp_core::StreamMonotonicityFence::default());
        self.subscribe(&selector, move |key, payload| {
            if key != expected_route {
                return;
            }
            let Ok(frame) =
                check_command_payload_for(&expected_session_id, &expected_session, &payload)
            else {
                return;
            };
            if !accept_subscriber_stream(
                &stream_fence,
                &key,
                "command_frame",
                &expected_session,
                &frame.stream,
            ) {
                return;
            }
            callback(key, payload);
        })
        .await
    }

    /// Subscribe to the observation plane (the free read-only observer tap).
    pub async fn subscribe_observations<F>(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        callback: F,
    ) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        let selector = self.keys.observation(session_id);
        let expected_route = selector.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = std::sync::Mutex::new(ncp_core::StreamMonotonicityFence::default());
        let queue = Arc::new(std::sync::Mutex::new(
            std::collections::VecDeque::with_capacity(OBSERVATION_QUEUE_CAPACITY),
        ));
        let callback = Arc::new(callback);
        let notify = Arc::new(tokio::sync::Notify::new());
        let callback_queue = queue.clone();
        let callback_notify = notify.clone();
        let drops = self.observation_queue_drops.clone();
        let subscriber = self
            .session
            .declare_subscriber(selector.clone())
            .callback(move |sample| {
                let key = sample.key_expr().as_str().to_string();
                if key != expected_route {
                    return;
                }
                let Some(payload) = copy_admitted_zbytes(sample.payload()) else {
                    return;
                };
                let Ok(frame) = check_observation_payload_for(
                    &expected_session_id,
                    &expected_session,
                    &payload,
                ) else {
                    return;
                };
                if !accept_subscriber_stream(
                    &stream_fence,
                    &key,
                    "observation_frame",
                    &expected_session,
                    &frame.stream,
                ) {
                    return;
                }
                enqueue_observation(&callback_queue, (key, payload), &drops);
                callback_notify.notify_one();
            })
            .await
            .map_err(err("declare observation subscriber"))?;
        let worker = tokio::spawn(dispatch_observations(queue, notify, callback));
        self.subs
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .push((selector.clone(), subscriber));
        self.observation_workers
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .push((selector, worker));
        Ok(())
    }

    /// Raw observer/diagnostic tap across every plane of a logical session. This
    /// cannot prove one live generation and performs no typed payload admission;
    /// its callback must never drive actuation, safety latches, or mutable session
    /// state. Use the plane-specific subscribers for trusted delivery.
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
                let ke = query.key_expr().clone();
                let selector = ke.as_str().to_owned();
                let req = match query.payload() {
                    Some(payload) => match copy_admitted_zbytes(payload) {
                        Some(payload) => payload,
                        None => {
                            let reply = rpc_error_payload(
                                ncp_core::RpcErrorCode::JsonLimit(
                                    ncp_core::bounded_json::JsonLimitCode::FrameBytes,
                                ),
                                format_args!(
                                    "RPC request frame byte limit exceeded ({} > {})",
                                    payload.len(),
                                    ncp_core::bounded_json::MAX_FRAME_BYTES
                                ),
                                None,
                                None,
                                selector_request_kind(&keys, &selector),
                            );
                            if let Err(error) = query.reply(ke, reply).await {
                                eprintln!("ncp-zenoh: oversized RPC reply failed: {error}");
                            }
                            continue;
                        }
                    },
                    None => Vec::new(),
                };
                let permit = match permits.clone().try_acquire_owned() {
                    Ok(permit) => Arc::new(permit),
                    Err(_) => {
                        let parsed = ncp_core::bounded_json::parse_value(&req).ok();
                        let session_id = parsed.as_ref().and_then(request_session_id);
                        let session = parsed.as_ref().and_then(request_session_ref);
                        let request_kind = selector_request_kind(&keys, &selector);
                        let reply = rpc_error_payload(
                            ncp_core::RpcErrorCode::ContainedInternalFailure,
                            "RPC server busy: in-flight request limit reached",
                            session_id,
                            session,
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
    /// Wire 1.0 candidate: a JSON frame published on the **observation plane** owns
    /// its stream position (`seq >= 1`) and carries an optional driving sensor
    /// position in `source`. Pull/RPC form is identified by absent `source`, never
    /// by an unstamped observation sequence.
    pub async fn publish_observation(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        payload: &[u8],
    ) -> Result<()> {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        let route = self.keys.observation(session_id);
        let frame = check_observation_payload_for(session_id, session, payload)?;
        accept_publisher_stream(
            &self.publisher_streams,
            &route,
            "observation_frame",
            session,
            &frame.stream,
        )?;
        self.put(&route, payload, Plane::Observation).await
    }

    /// Publish a command frame on a session's action plane (safety-gated upstream).
    ///
    /// Wire 1.0 candidate: every payload is a complete envelope bound to the exact
    /// live `(session_id, generation)` before publish. An authenticated **ESTOP**
    /// may omit its authority lease, but never its envelope or session binding.
    pub async fn publish_command(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        payload: &[u8],
    ) -> Result<()> {
        self.publish_command_classified(session_id, session, payload)
            .await
            .map_err(TypedCommandPublishError::into_inner)
    }

    async fn publish_command_classified(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        payload: &[u8],
    ) -> std::result::Result<(), TypedCommandPublishError> {
        check_id("session", session_id).map_err(TypedCommandPublishError::Rejected)?;
        check_live_session_ref(session).map_err(TypedCommandPublishError::Rejected)?;
        let route = self.keys.command(session_id);
        let frame = check_command_payload_for(session_id, session, payload)
            .map_err(TypedCommandPublishError::Rejected)?;
        accept_publisher_stream(
            &self.publisher_streams,
            &route,
            "command_frame",
            session,
            &frame.stream,
        )
        .map_err(TypedCommandPublishError::Rejected)?;
        self.put(&route, payload, Plane::Action)
            .await
            .map_err(TypedCommandPublishError::DeliveryAmbiguous)
    }

    /// Subscribe to the sensor (perception) plane for a session.
    pub async fn subscribe_sensors<F>(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        callback: F,
    ) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        let selector = self.keys.sensor(session_id);
        let expected_route = selector.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = std::sync::Mutex::new(ncp_core::StreamMonotonicityFence::default());
        self.subscribe(&selector, move |key, payload| {
            if key != expected_route {
                return;
            }
            let Ok(frame) =
                check_sensor_payload_for(&expected_session_id, &expected_session, &payload)
            else {
                return;
            };
            if !accept_subscriber_stream(
                &stream_fence,
                &key,
                "sensor_frame",
                &expected_session,
                &frame.stream,
            ) {
                return;
            }
            callback(key, payload);
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
        session: &ncp_core::SessionRef,
        name: &str,
        payload: &[u8],
    ) -> Result<()> {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        check_id("sensor name", name)?;
        let route = self.keys.sensor_named(session_id, name);
        let frame = check_sensor_payload_for(session_id, session, payload)?;
        accept_publisher_stream(
            &self.publisher_streams,
            &route,
            "sensor_frame",
            session,
            &frame.stream,
        )?;
        self.put(&route, payload, Plane::Perception).await
    }

    /// Publish a `CommandFrame` to one named actuator: `…/command/{name}`.
    /// Validated like [`Self::publish_command`], including exact live-generation
    /// fencing for ESTOP.
    pub async fn publish_command_named(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        name: &str,
        payload: &[u8],
    ) -> Result<()> {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        check_id("actuator name", name)?;
        let route = self.keys.command_named(session_id, name);
        let frame = check_command_payload_for(session_id, session, payload)?;
        accept_publisher_stream(
            &self.publisher_streams,
            &route,
            "command_frame",
            session,
            &frame.stream,
        )?;
        self.put(&route, payload, Plane::Action).await
    }

    /// Subscribe to **all** of a session's sensors (any count): `…/sensor/**`.
    pub async fn subscribe_sensors_glob<F>(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        callback: F,
    ) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        // Guard the glob entry point too (release builds drop the key-builder
        // debug_assert), so a wildcard-bearing id cannot widen the subscription.
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        let selector = self.keys.sensor_glob(session_id);
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = std::sync::Mutex::new(ncp_core::StreamMonotonicityFence::default());
        self.subscribe(&selector, move |key, payload| {
            let Ok(frame) =
                check_sensor_payload_for(&expected_session_id, &expected_session, &payload)
            else {
                return;
            };
            if !accept_subscriber_stream(
                &stream_fence,
                &key,
                "sensor_frame",
                &expected_session,
                &frame.stream,
            ) {
                return;
            }
            callback(key, payload);
        })
        .await
    }

    /// Subscribe to one named actuator's command stream: `…/command/{name}`.
    pub async fn subscribe_command_named<F>(
        &self,
        session_id: &str,
        session: &ncp_core::SessionRef,
        name: &str,
        callback: F,
    ) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        check_id("session", session_id)?;
        check_live_session_ref(session)?;
        check_id("actuator name", name)?;
        let selector = self.keys.command_named(session_id, name);
        let expected_route = selector.clone();
        let expected_session_id = session_id.to_owned();
        let expected_session = session.clone();
        let stream_fence = std::sync::Mutex::new(ncp_core::StreamMonotonicityFence::default());
        self.subscribe(&selector, move |key, payload| {
            if key != expected_route {
                return;
            }
            let Ok(frame) =
                check_command_payload_for(&expected_session_id, &expected_session, &payload)
            else {
                return;
            };
            if !accept_subscriber_stream(
                &stream_fence,
                &key,
                "command_frame",
                &expected_session,
                &frame.stream,
            ) {
                return;
            }
            callback(key, payload);
        })
        .await
    }

    /// Raw, untrusted observer tap across the whole fleet (every session/plane):
    /// `{realm}/session/**`. It is suitable for diagnostics only and performs no
    /// live-generation admission.
    pub async fn subscribe_fleet<F>(&self, callback: F) -> Result<()>
    where
        F: Fn(String, Vec<u8>) + Send + Sync + 'static,
    {
        self.subscribe(&self.keys.fleet_glob(), callback).await
    }

    // ───────────────────────── primitives ─────────────────────────

    /// Raw, untrusted byte publish on `key` with the QoS of `plane`.
    ///
    /// This primitive performs no NCP decode, route/session binding, authority
    /// decision, or monotonicity fencing. It is suitable only for diagnostics or
    /// callers that independently enforce the complete typed boundary.
    pub async fn put(&self, key: &str, payload: &[u8], plane: Plane) -> Result<()> {
        self.session
            .put(key, payload.to_vec())
            .congestion_control(plane.congestion())
            .priority(plane.priority())
            .express(plane.express())
            .await
            .map_err(err("zenoh put"))
    }

    /// Raw, untrusted subscription to `key` (which may contain `*`/`**`);
    /// `callback` gets `(key, bytes)` with no NCP admission or replay fence.
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
                let Some(payload) = copy_admitted_zbytes(sample.payload()) else {
                    return;
                };
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
        self.observation_workers
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .retain(|(selector, worker)| {
                let keep = selector != prefix && !selector.starts_with(&prefix_slash);
                if !keep {
                    worker.abort();
                }
                keep
            });
        Ok(before - subscribers.len())
    }

    /// Release this wrapper's subscribers and, only when this wrapper opened the
    /// Zenoh session itself, gracefully close the underlying session. A wrapper
    /// created with [`Self::from_session`] never closes its host's borrowed
    /// session.
    pub async fn close(&self) -> Result<()> {
        self.subs.lock().unwrap_or_else(|e| e.into_inner()).clear();
        for (_, worker) in self
            .observation_workers
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .drain(..)
        {
            worker.abort();
        }
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
    command: ncp_core::CommandFrame,
    bytes: Vec<u8>,
    priority: CommandPriority,
}

#[derive(Debug, Default)]
struct CommandDispatchState {
    pending: Option<PendingCommand>,
    /// A fail-safe position crossed publisher admission but did not receive a
    /// transport success. Active (or a weaker fail-safe) stays blocked until a new
    /// logical fail-safe at least this strong is successfully put.
    required_fail_safe: Option<CommandPriority>,
}

fn command_priority(mode: &ncp_core::Mode) -> CommandPriority {
    match mode {
        ncp_core::Mode::Active => CommandPriority::Active,
        ncp_core::Mode::Estop => CommandPriority::Estop,
        _ => CommandPriority::Hold,
    }
}

fn next_command_sequence(counter: &std::sync::atomic::AtomicI64) -> Option<i64> {
    counter
        .fetch_update(
            std::sync::atomic::Ordering::Relaxed,
            std::sync::atomic::Ordering::Relaxed,
            |current| {
                current
                    .checked_add(1)
                    .filter(|next| *next <= ncp_core::JSON_SAFE_INTEGER_MAX)
            },
        )
        .ok()
        .and_then(|prior| prior.checked_add(1))
}

/// Store at most one not-yet-published command. The transport is the action-stream
/// publisher, so it assigns every new slot one position from a single allocator.
/// Replacing an unattempted slot reuses that slot's position without a false gap.
fn enqueue_command(
    state: &std::sync::Mutex<CommandDispatchState>,
    mut command: ncp_core::CommandFrame,
    stream_epoch: &str,
    sequence: &std::sync::atomic::AtomicI64,
) -> ncp_core::transport::CommandSendOutcome {
    let priority = command_priority(&command.mode);
    let mut state = state.lock().unwrap_or_else(|error| error.into_inner());
    if state
        .required_fail_safe
        .is_some_and(|required| priority < required)
    {
        return ncp_core::transport::CommandSendOutcome::Rejected;
    }
    if state
        .pending
        .as_ref()
        .is_some_and(|current| current.priority > priority)
    {
        return ncp_core::transport::CommandSendOutcome::Rejected;
    }
    let outcome = if let Some(current) = state.pending.as_ref() {
        // This candidate has not crossed the publication boundary. Reuse the
        // selected slot's position so intentional local conflation cannot create
        // an artificial action-stream loss gap.
        command.stream = current.command.stream.clone();
        ncp_core::transport::CommandSendOutcome::ReplacedPending
    } else {
        let Some(seq) = next_command_sequence(sequence) else {
            return ncp_core::transport::CommandSendOutcome::Rejected;
        };
        command.stream = ncp_core::StreamPosition {
            epoch: stream_epoch.to_owned(),
            seq,
        };
        ncp_core::transport::CommandSendOutcome::Accepted
    };
    state.pending = Some(PendingCommand {
        command,
        bytes: Vec::new(),
        priority,
    });
    outcome
}

fn note_publish_failure(state: &std::sync::Mutex<CommandDispatchState>, priority: CommandPriority) {
    if priority == CommandPriority::Active {
        return;
    }
    let mut state = state.lock().unwrap_or_else(|error| error.into_inner());
    state.required_fail_safe = Some(
        state
            .required_fail_safe
            .map_or(priority, |required| required.max(priority)),
    );
    if state
        .pending
        .as_ref()
        .is_some_and(|pending| pending.priority < priority)
    {
        // This command was accepted while the fail-safe put was in flight. Its
        // position remains consumed, but delivery is now forbidden by the latch.
        state.pending = None;
    }
}

fn note_publish_success(state: &std::sync::Mutex<CommandDispatchState>, priority: CommandPriority) {
    let mut state = state.lock().unwrap_or_else(|error| error.into_inner());
    if state
        .required_fail_safe
        .is_some_and(|required| priority >= required)
    {
        state.required_fail_safe = None;
    }
}

async fn dispatch_commands(
    bus: ZenohBus,
    session_id: String,
    session: ncp_core::SessionRef,
    state: Arc<std::sync::Mutex<CommandDispatchState>>,
    notify: Arc<tokio::sync::Notify>,
) {
    loop {
        notify.notified().await;
        loop {
            let pending = state
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .pending
                .take();
            let Some(pending) = pending else {
                break;
            };
            let mut pending = pending;
            if pending.bytes.is_empty() {
                let Ok(bytes) = serde_json::to_vec(&pending.command) else {
                    eprintln!("ncp: command serialization failed for session {session_id:?}");
                    continue;
                };
                pending.bytes = bytes;
            }
            match bus
                .publish_command_classified(&session_id, &session, &pending.bytes)
                .await
            {
                Ok(()) => note_publish_success(&state, pending.priority),
                Err(TypedCommandPublishError::Rejected(error)) => {
                    eprintln!(
                        "ncp: command rejected before transport delivery for session {session_id:?}: {error}"
                    );
                    note_publish_failure(&state, pending.priority);
                    break;
                }
                Err(TypedCommandPublishError::DeliveryAmbiguous(error)) => {
                    eprintln!(
                        "ncp: command delivery ambiguous for session {session_id:?}: {error}; same position will not be retried"
                    );
                    note_publish_failure(&state, pending.priority);
                    break;
                }
            }
        }
    }
}

pub struct ZenohControlTransport {
    _bus: ZenohBus,
    session_id: String,
    session: ncp_core::SessionRef,
    latest: Arc<std::sync::Mutex<Option<ncp_core::SensorFrame>>>,
    command_state: Arc<std::sync::Mutex<CommandDispatchState>>,
    command_notify: Arc<tokio::sync::Notify>,
    command_worker: tokio::task::JoinHandle<()>,
    command_stream_epoch: String,
    command_seq: std::sync::atomic::AtomicI64,
}

impl ZenohControlTransport {
    pub async fn new(
        bus: ZenohBus,
        session_id: impl Into<String>,
        session: ncp_core::SessionRef,
    ) -> Result<Self> {
        let session_id = session_id.into();
        check_id("session", &session_id)?;
        check_live_session_ref(&session)?;
        let command_stream_epoch = ncp_core::transport::mint_stream_epoch()
            .map_err(|error| ZenohError(error.to_string()))?;
        let latest: Arc<std::sync::Mutex<Option<ncp_core::SensorFrame>>> =
            Arc::new(std::sync::Mutex::new(None));
        let sink = latest.clone();
        bus.subscribe_sensors(&session_id, &session, move |_key, bytes| {
            // Wire 1.0 candidate data-plane ingress gate. The typed subscriber has
            // already rejected a wrong id/generation; `decode_validated` rejects an
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
        let command_state = Arc::new(std::sync::Mutex::new(CommandDispatchState::default()));
        let command_notify = Arc::new(tokio::sync::Notify::new());
        let command_worker = tokio::spawn(dispatch_commands(
            bus.clone(),
            session_id.clone(),
            session.clone(),
            command_state.clone(),
            command_notify.clone(),
        ));
        Ok(Self {
            _bus: bus,
            session_id,
            session,
            latest,
            command_state,
            command_notify,
            command_worker,
            command_stream_epoch,
            command_seq: std::sync::atomic::AtomicI64::new(0),
        })
    }

    /// True while a fail-safe publication is delivery-ambiguous and later Active
    /// output remains blocked. Recovery requires a newly submitted fail-safe with
    /// a new transport-assigned position, or a fresh transport declaration.
    pub fn fail_safe_delivery_pending(&self) -> bool {
        self.command_state
            .lock()
            .unwrap_or_else(|error| error.into_inner())
            .required_fail_safe
            .is_some()
    }
}

impl Drop for ZenohControlTransport {
    fn drop(&mut self) {
        self.command_worker.abort();
    }
}

/// What `send_command` should do with a frame (pure, unit-testable).
///
/// - A locally generated **ESTOP is always selected for normalization** — the
///   transport binds it to its immutable live session before the remote gate,
///   while preserving a bounded, wire-valid caller payload.
/// - A wire-valid frame publishes.
/// - An invalid **Active** frame is skipped LOUDLY — a controller trying to
///   actuate with an unstamped/incompatible frame is a real fault.
/// - An invalid non-Active frame (Hold/Init) is skipped silently: the loop
///   legitimately emits unstampable HOLDs before it has established its publisher
///   stream position, and the plant holds by default anyway.
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

/// Repair the publisher identity on a locally submitted ESTOP and bind it to the
/// transport's immutable live session. Caller-provided cross-session identity is
/// never allowed to choose the action-plane key or latch.
fn ensure_publishable_estop_identity(
    frame: &mut ncp_core::CommandFrame,
    authoritative_session_id: &str,
    authoritative_session: &ncp_core::SessionRef,
    command_stream_epoch: &str,
    provisional_seq: i64,
) {
    if !ncp_core::is_canonical_uuid_v4(&frame.stream.epoch)
        || !(1..=ncp_core::JSON_SAFE_INTEGER_MAX).contains(&frame.stream.seq)
    {
        frame.stream.epoch = command_stream_epoch.to_string();
        frame.stream.seq = provisional_seq;
    }
    frame.session_id = authoritative_session_id.to_string();
    frame.session = authoritative_session.clone();
    // The protocol admits ESTOP without a lease. This local publisher binding is
    // not transport authentication; a production adapter must separately bind the
    // sender to its verified transport principal. Carrying a malformed or foreign
    // lease would only make the normalized local emergency envelope invalid.
    frame.authority = None;
}

fn normalize_command_for_publish<'a>(
    command: &'a ncp_core::CommandFrame,
    authoritative_session_id: &str,
    authoritative_session: &ncp_core::SessionRef,
    command_stream_epoch: &str,
    provisional_seq: i64,
) -> std::borrow::Cow<'a, ncp_core::CommandFrame> {
    if command.mode == ncp_core::Mode::Estop {
        let mut safe = command.clone();
        // Bind a local ESTOP to this transport's session and publisher identity.
        // This clears caller authority rather than inventing or repairing it.
        ensure_publishable_estop_identity(
            &mut safe,
            authoritative_session_id,
            authoritative_session,
            command_stream_epoch,
            provisional_seq,
        );
        let bounded = serde_json::to_vec(&safe)
            .ok()
            .is_some_and(|payload| ncp_core::bounded_json::preflight(&payload).is_ok());
        if ncp_core::WireFrame::validate_wire(&safe).is_err() || !bounded {
            // A programmatic ESTOP can contain resource-invalid diagnostic data
            // that is unsafe to echo. Retain only the emergency mode and
            // authoritative publisher/session identity. An empty command map is
            // deliberate: the body applies its content-addressed plant-profile
            // ESTOP action; the transport must not manufacture a universal action.
            safe = ncp_core::CommandFrame {
                stream: ncp_core::StreamPosition {
                    epoch: command_stream_epoch.to_owned(),
                    seq: provisional_seq,
                },
                session: authoritative_session.clone(),
                session_id: authoritative_session_id.to_owned(),
                mode: ncp_core::Mode::Estop,
                ..Default::default()
            };
        }
        std::borrow::Cow::Owned(safe)
    } else {
        std::borrow::Cow::Borrowed(command)
    }
}

impl ncp_core::ControlTransport for ZenohControlTransport {
    fn send_command(
        &self,
        command: &ncp_core::CommandFrame,
    ) -> ncp_core::transport::CommandSendOutcome {
        // Never publish a wire-invalid remote frame. A local ESTOP is normalized
        // into a complete envelope below; the remote publisher gate has no envelope
        // exception.
        match command_publish_decision(command) {
            PublishDecision::Publish => {}
            PublishDecision::SkipSilent => {
                return ncp_core::transport::CommandSendOutcome::Rejected
            }
            PublishDecision::SkipLoud => {
                if let Err(e) = ncp_core::WireFrame::validate_wire(command) {
                    eprintln!("ncp: NOT publishing invalid Active command ({e})");
                }
                return ncp_core::transport::CommandSendOutcome::Rejected;
            }
        }
        if command.mode != ncp_core::Mode::Estop
            && (command.session_id != self.session_id || command.session != self.session)
        {
            eprintln!(
                "ncp: NOT publishing command for a session other than the transport's live binding"
            );
            return ncp_core::transport::CommandSendOutcome::Rejected;
        }
        // Normalize a malformed in-memory ESTOP to a complete minimal wire frame;
        // enqueue_command then replaces every caller stream position with the one
        // transport-owned action stream, avoiding mixed emergency/caller epochs.
        let command = normalize_command_for_publish(
            command,
            &self.session_id,
            &self.session,
            &self.command_stream_epoch,
            1,
        );
        let outcome = enqueue_command(
            &self.command_state,
            command.into_owned(),
            &self.command_stream_epoch,
            &self.command_seq,
        );
        if outcome != ncp_core::transport::CommandSendOutcome::Rejected {
            self.command_notify.notify_one();
        }
        outcome
    }

    fn latest_sensor(&self) -> Option<ncp_core::SensorFrame> {
        self.latest
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone()
    }
}

/// Validate an RPC reply's own `kind` discriminator before the typed decode. Pure
/// (no transport), so both the basic server-side shape gate and the stricter typed
/// client correlation gate can exercise the same bounded parser.
fn validate_reply_value(
    reply: &[u8],
    request_kind: &str,
    expect_session_id: &str,
) -> Result<serde_json::Value> {
    ncp_core::validate_rpc_reply_for(request_kind, expect_session_id, reply)
        .map_err(|error| ZenohError(bounded_diagnostic(format_args!("{error}"))))
}

fn surface_error_reply(value: serde_json::Value) -> Result<serde_json::Value> {
    let kind = ncp_core::message_kind(&value).expect("validate requires string kind");
    if kind == "error" {
        return Err(ZenohError(bounded_diagnostic(format_args!(
            "NCP error {}: {}",
            value
                .get("code")
                .and_then(|field| field.as_str())
                .expect("validated ErrorFrame has a string code"),
            value
                .get("error")
                .and_then(|field| field.as_str())
                .expect("validated ErrorFrame has a string error")
        ))));
    }
    Ok(value)
}

/// Basic reply gate used where only the selector kind and logical session are
/// available. Typed lifecycle clients use [`check_reply_for_request`] so a reply
/// cannot claim a different generation or a different mutation receipt.
#[cfg(test)]
fn check_reply(
    reply: &[u8],
    request_kind: &str,
    expect_session_id: &str,
) -> Result<serde_json::Value> {
    surface_error_reply(validate_reply_value(
        reply,
        request_kind,
        expect_session_id,
    )?)
}

fn required_correlation_string<'a>(value: &'a serde_json::Value, path: &str) -> Result<&'a str> {
    value
        .as_str()
        .filter(|value| !value.is_empty())
        .ok_or_else(|| ZenohError(format!("NCP request carries no string {path}")))
}

/// Bind one typed Zenoh lifecycle reply to the complete originating mutation.
/// A bare pre-authentication/shape `ErrorFrame` may omit session and receipt, but
/// every terminal receipt must be fenced by the exact request generation,
/// operation ID, and request digest before it can affect client state.
fn check_reply_for_request(reply: &[u8], request: &serde_json::Value) -> Result<serde_json::Value> {
    let request_kind = required_correlation_string(&request["kind"], "kind")?;
    let session_id = required_correlation_string(&request["session_id"], "session_id")?;
    let value = validate_reply_value(reply, request_kind, session_id)?;

    if matches!(
        request_kind,
        "step_request" | "run_request" | "close_session"
    ) {
        let expected_generation =
            required_correlation_string(&request["session"]["generation"], "session.generation")?;
        let expected_operation_id = required_correlation_string(
            &request["operation"]["operation_id"],
            "operation.operation_id",
        )?;
        let expected_request_digest = required_correlation_string(
            &request["operation"]["request_digest"],
            "operation.request_digest",
        )?;
        let reply_kind = ncp_core::message_kind(&value).expect("validated reply carries kind");
        let receipt = value.get("receipt").filter(|receipt| !receipt.is_null());
        let reply_generation = value
            .get("session")
            .and_then(|session| session.get("generation"))
            .and_then(serde_json::Value::as_str);

        match reply_generation {
            Some(generation) if generation == expected_generation => {}
            None if reply_kind == "error" && receipt.is_none() => {}
            Some(generation) => {
                return Err(ZenohError(format!(
                    "NCP RPC reply session generation mismatch: expected {expected_generation:?}, got {generation:?}"
                )))
            }
            None => {
                return Err(ZenohError(
                    "NCP terminal RPC reply carries no session generation".into(),
                ))
            }
        }

        if let Some(receipt) = receipt {
            let operation_id = receipt
                .get("operation_id")
                .and_then(serde_json::Value::as_str)
                .expect("validated responder receipt has operation_id");
            if operation_id != expected_operation_id {
                return Err(ZenohError(format!(
                    "NCP RPC reply receipt operation_id mismatch: expected {expected_operation_id:?}, got {operation_id:?}"
                )));
            }
            let request_digest = receipt
                .get("request_digest")
                .and_then(serde_json::Value::as_str)
                .expect("validated responder receipt has request_digest");
            if request_digest != expected_request_digest {
                return Err(ZenohError(format!(
                    "NCP RPC reply receipt request_digest mismatch: expected {expected_request_digest:?}, got {request_digest:?}"
                )));
            }
        } else if reply_kind != "error" {
            return Err(ZenohError(
                "NCP successful mutation reply carries no responder receipt".into(),
            ));
        }
    } else if value
        .get("receipt")
        .is_some_and(|receipt| !receipt.is_null())
    {
        return Err(ZenohError(
            "NCP non-mutating RPC reply must not carry a mutation receipt".into(),
        ));
    }

    surface_error_reply(value)
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
        // then validate the reply against the wire-1.0 contract for its
        // kind (required fields incl. a compatible `ncp_version`).
        let value = check_reply_for_request(&reply, &request)?;
        serde_json::from_value(value).map_err(err("parse reply"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const TEST_SECURITY_DIGEST: &str =
        "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab";
    const LIVE_GENERATION: &str = "00000000-0000-4000-8000-0000000000a2";

    fn live_session() -> ncp_core::SessionRef {
        ncp_core::SessionRef {
            generation: LIVE_GENERATION.into(),
        }
    }

    fn sensor_payload(session_id: &str, epoch: &str, seq: i64) -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "kind": "sensor_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": session_id,
            "stream": {"epoch": epoch, "seq": seq},
            "session": {"generation": LIVE_GENERATION},
            "t": 0.0,
            "channels": {}
        }))
        .unwrap()
    }

    fn command_payload(session_id: &str, epoch: &str, seq: i64) -> Vec<u8> {
        serde_json::to_vec(&serde_json::json!({
            "kind": "command_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": session_id,
            "stream": {"epoch": epoch, "seq": seq},
            "session": {"generation": LIVE_GENERATION},
            "t": 0.0,
            "mode": "hold",
            "ttl_ms": 200.0,
            "channels": {}
        }))
        .unwrap()
    }

    fn observation_payload(session_id: &str, epoch: &str, seq: i64) -> Vec<u8> {
        serde_json::to_vec(&ncp_core::ObservationFrame {
            session_id: session_id.into(),
            stream: ncp_core::StreamPosition {
                epoch: epoch.into(),
                seq,
            },
            source: Some(ncp_core::StreamPosition {
                epoch: "f0000000-0000-4000-8000-000000000001".into(),
                seq: 1,
            }),
            session: live_session(),
            ..Default::default()
        })
        .unwrap()
    }

    async fn wait_for_count(
        counter: &std::sync::atomic::AtomicUsize,
        expected: usize,
        context: &str,
    ) {
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
        while std::time::Instant::now() < deadline {
            if counter.load(std::sync::atomic::Ordering::SeqCst) >= expected {
                return;
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        panic!(
            "timed out waiting for {context}: expected {expected}, observed {}",
            counter.load(std::sync::atomic::Ordering::SeqCst)
        );
    }

    async fn raw_put_until_count(
        bus: &ZenohBus,
        key: &str,
        payload: &[u8],
        plane: Plane,
        counter: &std::sync::atomic::AtomicUsize,
        expected: usize,
        context: &str,
    ) {
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
        while std::time::Instant::now() < deadline
            && counter.load(std::sync::atomic::Ordering::SeqCst) < expected
        {
            bus.put(key, payload, plane).await.unwrap();
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        wait_for_count(counter, expected, context).await;
    }

    fn control_identity(
        principal_id: &str,
        entity_id: &str,
        role: ncp_core::PrincipalRole,
    ) -> ncp_core::IdentityClaim {
        ncp_core::IdentityClaim {
            principal_id: principal_id.into(),
            entity_id: entity_id.into(),
            role,
            plane: ncp_core::Plane::Control,
        }
    }

    fn valid_open(session_id: &str) -> ncp_core::OpenSession {
        ncp_core::OpenSession {
            session_id: session_id.into(),
            network: ncp_core::NetworkRef {
                ref_: "model".into(),
                ..Default::default()
            },
            identity: control_identity(
                "commander-principal-1",
                "controller-1",
                ncp_core::PrincipalRole::Commander,
            ),
            security_profile: ncp_core::security::DEV_LOOPBACK_INSECURE.into(),
            security_state_digest: TEST_SECURITY_DIGEST.into(),
            ..Default::default()
        }
    }

    fn unavailable_opened(session_id: &str) -> ncp_core::SessionOpened {
        ncp_core::SessionOpened {
            session_id: session_id.into(),
            ok: false,
            error: Some("unavailable".into()),
            identity: control_identity(
                "body-principal-1",
                "simulator-1",
                ncp_core::PrincipalRole::Body,
            ),
            security_profile: ncp_core::security::DEV_LOOPBACK_INSECURE.into(),
            security_state_digest: TEST_SECURITY_DIGEST.into(),
            ..Default::default()
        }
    }

    #[test]
    fn plane_qos_profiles() {
        assert_eq!(Plane::Action.congestion(), CongestionControl::Drop);
        assert_eq!(Plane::Action.priority(), Priority::RealTime);
        assert!(Plane::Action.express());
        assert_eq!(Plane::Observation.congestion(), CongestionControl::Drop);
        assert_eq!(Plane::Observation.priority(), Priority::Data);
        assert!(!Plane::Observation.express());
        assert_eq!(Plane::Control.congestion(), CongestionControl::Block);
        assert_eq!(MAX_IN_FLIGHT_RPC_REQUESTS, 128);
        assert_eq!(OBSERVATION_QUEUE_CAPACITY, 64);
        assert!(!Plane::Perception.express());
    }

    #[test]
    fn observation_queue_drops_oldest_and_counts_exactly() {
        let queue = std::sync::Mutex::new(std::collections::VecDeque::new());
        let drops = std::sync::atomic::AtomicU64::new(0);
        for index in 0..=OBSERVATION_QUEUE_CAPACITY {
            enqueue_observation(&queue, (format!("key-{index}"), vec![index as u8]), &drops);
        }
        let queue = queue.into_inner().unwrap();
        assert_eq!(queue.len(), OBSERVATION_QUEUE_CAPACITY);
        assert_eq!(queue.front().unwrap().0, "key-1");
        assert_eq!(
            queue.back().unwrap().0,
            format!("key-{OBSERVATION_QUEUE_CAPACITY}")
        );
        assert_eq!(drops.load(std::sync::atomic::Ordering::Relaxed), 1);
    }

    #[test]
    fn check_reply_rejects_wrong_kind_session_and_unversioned_errors() {
        // Right kind -> Ok.
        let opened = serde_json::json!({
            "kind": "session_opened",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "ok": true,
            "state_version": 1,
            "backend": "mock",
            "provenance": {
                "network_ref": "model",
                "backend": "mock",
                "calibrated_posterior": false,
                "is_simulation_output": true,
                "advisory_only": true
            },
            "session": {"generation": "293279f3-d459-4bfd-aeeb-604799e96925"},
            "identity": {
                "principal_id": "body-principal-1",
                "entity_id": "simulator-1",
                "role": "body",
                "plane": "control"
            },
            "security_profile": "dev-loopback-insecure",
            "security_state_digest": TEST_SECURITY_DIGEST,
            "gateway_permitted": false
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
            code: "NCP-WIRE-001".into(),
            error: "boom".into(),
            session_id: Some("s".into()),
            session: Some(ncp_core::SessionRef {
                generation: "293279f3-d459-4bfd-aeeb-604799e96925".into(),
            }),
            ..Default::default()
        };
        assert!(check_reply(&serde_json::to_vec(&error).unwrap(), "open_session", "s").is_err());
        let wrong_error = ncp_core::ErrorFrame {
            code: "NCP-WIRE-001".into(),
            error: "boom".into(),
            session_id: Some("s".into()),
            session: Some(ncp_core::SessionRef {
                generation: "293279f3-d459-4bfd-aeeb-604799e96925".into(),
            }),
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
    fn typed_rpc_reply_correlation_rejects_stale_generation_and_wrong_receipt() {
        const OPERATION_ID: &str = "10000000-0000-4000-8000-000000000001";
        const REQUEST_DIGEST: &str =
            "cf0d5f7440ea8ed8c5c8326182905ba66ceecca92ffccd592d56f9b9a42fe9df";
        let request = serde_json::json!({
            "kind": "step_request",
            "session_id": "s",
            "session": {"generation": LIVE_GENERATION},
            "operation": {
                "operation_id": OPERATION_ID,
                "request_digest": REQUEST_DIGEST,
            },
        });
        let reply = serde_json::json!({
            "kind": "observation_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "stream": {"epoch": "30000000-0000-4000-8000-000000000001", "seq": 1},
            "session": {"generation": LIVE_GENERATION},
            "records": {},
            "calibrated_posterior": false,
            "is_simulation_output": true,
            "receipt": {
                "operation_id": OPERATION_ID,
                "request_digest": REQUEST_DIGEST,
                "result_digest": "82bfecaa6d47a3ec4cc56b948f511e641d186d19545b9a0c697b825ecaff5241",
                "outcome": "succeeded",
                "state_version": 2,
                "committed_at_utc_ms": 1_700_000_001_000_i64,
                "responder_principal_id": "body-principal-1",
                "responder_entity_id": "simulator-1"
            }
        });

        assert!(check_reply_for_request(&serde_json::to_vec(&reply).unwrap(), &request).is_ok());

        let mut stale_generation = reply.clone();
        stale_generation["session"]["generation"] = "30000000-0000-4000-8000-000000000099".into();
        let error =
            check_reply_for_request(&serde_json::to_vec(&stale_generation).unwrap(), &request)
                .expect_err("a stale reply generation must not complete the mutation");
        assert!(error.0.contains("generation mismatch"), "{error}");

        let mut wrong_operation = reply.clone();
        wrong_operation["receipt"]["operation_id"] = "10000000-0000-4000-8000-000000000099".into();
        let error =
            check_reply_for_request(&serde_json::to_vec(&wrong_operation).unwrap(), &request)
                .expect_err("a receipt for another operation must not complete the mutation");
        assert!(error.0.contains("operation_id mismatch"), "{error}");

        let mut wrong_digest = reply.clone();
        wrong_digest["receipt"]["request_digest"] = "d".repeat(64).into();
        let error = check_reply_for_request(&serde_json::to_vec(&wrong_digest).unwrap(), &request)
            .expect_err("a receipt for other request bytes must not complete the mutation");
        assert!(error.0.contains("request_digest mismatch"), "{error}");

        let mut terminal_error = serde_json::json!({
            "kind": "error",
            "ncp_version": ncp_core::NCP_VERSION,
            "code": "NCP-STATE-001",
            "error": "rejected",
            "session_id": "s",
            "session": {"generation": LIVE_GENERATION},
            "request_kind": "step_request",
            "receipt": reply["receipt"].clone(),
        });
        terminal_error["receipt"]["outcome"] = "rejected".into();
        let error =
            check_reply_for_request(&serde_json::to_vec(&terminal_error).unwrap(), &request)
                .expect_err("a correlated terminal rejection surfaces as the typed NCP error");
        assert!(error.0.contains("NCP error NCP-STATE-001"), "{error}");

        terminal_error["session"]["generation"] = "30000000-0000-4000-8000-000000000099".into();
        let error =
            check_reply_for_request(&serde_json::to_vec(&terminal_error).unwrap(), &request)
                .expect_err("a stale terminal rejection must fail correlation first");
        assert!(error.0.contains("generation mismatch"), "{error}");
    }

    #[test]
    fn rpc_reply_admission_checks_zbytes_length_before_copying() {
        let payload =
            zenoh::bytes::ZBytes::from(vec![b'x'; ncp_core::bounded_json::MAX_FRAME_BYTES + 1]);

        let error = validate_and_copy_rpc_reply(&payload, "open_session", "s")
            .expect_err("oversized reply must fail before conversion to an owned buffer");

        assert!(error.0.contains("NCP-LIMIT-001"), "{error}");
        assert!(error.0.len() <= MAX_RPC_DIAGNOSTIC_BYTES);
    }

    #[test]
    fn zbytes_copy_helper_rejects_oversized_payload_before_flattening() {
        let at_limit =
            zenoh::bytes::ZBytes::from(vec![b'x'; ncp_core::bounded_json::MAX_FRAME_BYTES]);
        let oversized =
            zenoh::bytes::ZBytes::from(vec![b'x'; ncp_core::bounded_json::MAX_FRAME_BYTES + 1]);

        assert_eq!(
            copy_admitted_zbytes(&at_limit).map(|bytes| bytes.len()),
            Some(ncp_core::bounded_json::MAX_FRAME_BYTES)
        );
        assert!(
            copy_admitted_zbytes(&oversized).is_none(),
            "oversized payload must be rejected before flattening/copying"
        );
    }

    #[test]
    fn source_has_no_direct_zbytes_flattening_bypass() {
        let source = include_str!("lib.rs");
        let flatten_call = [".to_", "bytes()"].concat();
        assert_eq!(
            source.matches(&flatten_call).count(),
            1,
            "all ZBytes flattening must remain centralized in copy_admitted_zbytes"
        );
    }

    #[test]
    fn transport_error_diagnostics_copy_only_a_bounded_prefix() {
        let payload =
            zenoh::bytes::ZBytes::from(vec![b'x'; ncp_core::bounded_json::MAX_FRAME_BYTES + 1]);

        let diagnostic = bounded_transport_reply_error(&payload);

        assert!(diagnostic.contains("NCP-LIMIT-001"));
        assert!(diagnostic.len() <= MAX_RPC_DIAGNOSTIC_BYTES);
    }

    #[test]
    fn rpc_selector_payload_and_handler_reply_are_bound_together() {
        let keys = Keys::default();
        let request = valid_open("s");
        let bytes = serde_json::to_vec(&request).unwrap();
        assert!(check_rpc_request(&keys, "ncp/rpc/open_session", &bytes).is_ok());
        assert!(check_rpc_request(&keys, "ncp/rpc/run_request", &bytes).is_err());
        assert!(check_rpc_request(
            &keys,
            "ncp/rpc/open_session",
            br#"{"kind":"open_session","session_id":"s"}"#,
        )
        .is_err());

        let opened = unavailable_opened("s");
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
            code: "NCP-WIRE-001".into(),
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
        let request = valid_open("s");
        let request = serde_json::to_vec(&request).unwrap();
        let reply = unavailable_opened("s");
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
        let generation = "293279f3-d459-4bfd-aeeb-604799e96925";
        let payload = rpc_error_payload(
            ncp_core::RpcErrorCode::InvalidMessage,
            "bad selector",
            Some("s".into()),
            Some(ncp_core::SessionRef {
                generation: generation.into(),
            }),
            Some("open_session".into()),
        );
        let value: serde_json::Value = serde_json::from_slice(&payload).unwrap();
        ncp_core::validate(&value).unwrap();
        assert_eq!(value["kind"], "error");
        assert_eq!(value["ncp_version"], ncp_core::NCP_VERSION);
        assert_eq!(value["code"], "NCP-WIRE-001");
        assert_eq!(value["session_id"], "s");
        assert_eq!(value["session"]["generation"], generation);
        assert!(value["receipt"].is_null());
    }

    #[test]
    fn rpc_dispatch_classifies_wire_and_contained_failures() {
        let keys = Keys::default();
        let handler = |_request: Vec<u8>| br#"{}"#.to_vec();

        let assert_code = |payload: Vec<u8>, expected: &str| {
            let reply = dispatch_rpc(&keys, &handler, "ncp/rpc/open_session", payload);
            let reply: serde_json::Value = serde_json::from_slice(&reply).unwrap();
            ncp_core::validate(&reply).unwrap();
            assert_eq!(reply["code"], expected);
            assert!(reply["session_id"].is_null());
            assert!(reply["session"].is_null());
        };

        assert_code(br#"{}"#.to_vec(), "NCP-WIRE-001");
        assert_code(
            br#"{"kind":"open_session","kind":"open_session"}"#.to_vec(),
            "NCP-LIMIT-007",
        );
        let too_deep = format!(
            "{}0{}",
            "[".repeat(ncp_core::bounded_json::MAX_NESTING_DEPTH + 1),
            "]".repeat(ncp_core::bounded_json::MAX_NESTING_DEPTH + 1)
        );
        assert_code(too_deep.into_bytes(), "NCP-LIMIT-002");
        assert_code(
            vec![b' '; ncp_core::bounded_json::MAX_FRAME_BYTES + 1],
            "NCP-LIMIT-001",
        );
        assert_code(br#"{"#.to_vec(), "NCP-LIMIT-009");

        let invalid_handler_reply = dispatch_rpc(
            &keys,
            &handler,
            "ncp/rpc/open_session",
            serde_json::to_vec(&valid_open("s")).unwrap(),
        );
        let invalid_handler_reply: serde_json::Value =
            serde_json::from_slice(&invalid_handler_reply).unwrap();
        ncp_core::validate(&invalid_handler_reply).unwrap();
        assert_eq!(invalid_handler_reply["code"], "NCP-INTERNAL-001");
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
            check_observation_payload_for("s", &live_session(), &raw).is_err(),
            "a bare NCPB block has no session/seq/provenance and must not publish"
        );

        let valid = ncp_core::ObservationFrame {
            session_id: "s".into(),
            stream: ncp_core::StreamPosition {
                epoch: "00000000-0000-4000-8000-000000000001".into(),
                seq: 1,
            },
            source: Some(ncp_core::StreamPosition {
                epoch: "00000000-0000-4000-8000-000000000001".into(),
                seq: 1,
            }),
            session: ncp_core::SessionRef {
                generation: "00000000-0000-4000-8000-0000000000a2".into(),
            },
            ..Default::default()
        };
        assert!(check_observation_payload_for(
            "s",
            &live_session(),
            &serde_json::to_vec(&valid).unwrap()
        )
        .is_ok());
        assert!(
            check_observation_payload_for(
                "other",
                &live_session(),
                &serde_json::to_vec(&valid).unwrap()
            )
            .is_err(),
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
            &live_session(),
            &serde_json::to_vec(&missing_boundary).unwrap()
        )
        .is_err());
    }

    #[test]
    fn perception_and_action_gates_reject_cross_session_payloads() {
        let sensor = serde_json::json!({
            "kind": "sensor_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "stream": {
                "epoch": "00000000-0000-4000-8000-000000000001",
                "seq": 1
            },
            "session": {"generation": "00000000-0000-4000-8000-0000000000a2"},
            "t": 0.0,
            "channels": {}
        });
        let sensor = serde_json::to_vec(&sensor).unwrap();
        assert!(check_sensor_payload_for("s", &live_session(), &sensor).is_ok());
        assert!(check_sensor_payload_for("other", &live_session(), &sensor).is_err());

        let command = serde_json::json!({
            "kind": "command_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "session_id": "s",
            "stream": {
                "epoch": "00000000-0000-4000-8000-000000000001",
                "seq": 1
            },
            "session": {"generation": "00000000-0000-4000-8000-0000000000a2"},
            "t": 0.0,
            "mode": "hold",
            "ttl_ms": 200.0,
            "channels": {}
        });
        let command = serde_json::to_vec(&command).unwrap();
        assert!(check_command_payload_for("s", &live_session(), &command).is_ok());
        assert!(check_command_payload_for("other", &live_session(), &command).is_err());
    }

    #[test]
    fn command_publish_gate_rejects_invalid_active_and_cross_session_estop() {
        let live = live_session();
        let invalid_active = serde_json::json!({
            "kind": "command_frame",
            "ncp_version": ncp_core::NCP_VERSION,
            "seq": 0,
            "mode": "active",
            "ttl_ms": 200.0,
            "channels": {"velocity_setpoint": {"data": [1.0]}}
        });
        assert!(check_command_payload_for(
            "s",
            &live,
            &serde_json::to_vec(&invalid_active).unwrap()
        )
        .is_err());

        let partial_estop = serde_json::json!({
            "kind": "wrong",
            "session_id": "s",
            "seq": 0,
            "mode": "estop",
            "channels": {"velocity_setpoint": {"data": [9.0]}}
        });
        assert!(
            check_command_payload_for("s", &live, &serde_json::to_vec(&partial_estop).unwrap())
                .is_err(),
            "ESTOP may omit authority, not its complete live-session wire envelope"
        );

        let same_session_estop = ncp_core::CommandFrame {
            session_id: "s".into(),
            stream: ncp_core::StreamPosition {
                epoch: "10000000-0000-4000-8000-000000000001".into(),
                seq: 1,
            },
            session: live.clone(),
            mode: ncp_core::Mode::Estop,
            ..Default::default()
        };
        let same_session_estop = serde_json::to_vec(&same_session_estop).unwrap();
        check_command_payload_for("s", &live, &same_session_estop)
            .expect("complete same-live-session ESTOP may omit authority");
        assert!(check_command_payload_for("other", &live, &same_session_estop).is_err());
        let stale_live = ncp_core::SessionRef {
            generation: "30000000-0000-4000-8000-000000000003".into(),
        };
        assert!(check_command_payload_for("s", &stale_live, &same_session_estop).is_err());

        let mut invalid_estop = ncp_core::CommandFrame {
            t: f64::NAN,
            frame_id: String::new(),
            source: Some(ncp_core::StreamPosition {
                epoch: "invalid-source-epoch".into(),
                seq: 0,
            }),
            source_t: f64::NAN,
            mode: ncp_core::Mode::Estop,
            ..Default::default()
        };
        invalid_estop.channels.insert(
            "bad\nchannel".into(),
            ncp_core::ChannelValue::scalar(f64::NAN, None),
        );
        let normalized = normalize_command_for_publish(
            &invalid_estop,
            "bound-session",
            &live,
            "40000000-0000-4000-8000-000000000004",
            7,
        );
        assert_eq!(normalized.mode, ncp_core::Mode::Estop);
        assert_eq!(normalized.session_id, "bound-session");
        assert_eq!(normalized.session, live);
        assert_eq!(normalized.source, None);
        assert_eq!(normalized.source_t, 0.0);
        assert_eq!(normalized.authority, None);
        assert!(
            normalized.channels.is_empty(),
            "transport fallback must leave the plant-profile action to the body"
        );
        ncp_core::WireFrame::validate_wire(normalized.as_ref())
            .expect("transport must normalize an in-memory ESTOP to a publishable minimal frame");
        check_command_payload_for(
            "bound-session",
            &live,
            &serde_json::to_vec(normalized.as_ref()).unwrap(),
        )
        .expect("normalized malformed ESTOP must pass the typed publisher gate");

        let cross_session_estop = ncp_core::CommandFrame {
            session_id: "other-session".into(),
            stream: ncp_core::StreamPosition {
                epoch: "10000000-0000-4000-8000-000000000001".into(),
                seq: 1,
            },
            session: ncp_core::SessionRef {
                generation: "20000000-0000-4000-8000-000000000002".into(),
            },
            mode: ncp_core::Mode::Estop,
            channels: [(
                "deployment_stop".into(),
                ncp_core::ChannelValue::scalar(0.25, Some("plant-unit")),
            )]
            .into_iter()
            .collect(),
            ..Default::default()
        };
        let normalized = normalize_command_for_publish(
            &cross_session_estop,
            "bound-session",
            &live,
            "40000000-0000-4000-8000-000000000004",
            8,
        );
        assert_eq!(normalized.session_id, "bound-session");
        assert_eq!(normalized.session, live);
        assert_eq!(
            normalized.channels.get("deployment_stop"),
            cross_session_estop.channels.get("deployment_stop"),
            "a bounded valid ESTOP payload must not be replaced by a transport action"
        );
        check_command_payload_for(
            "bound-session",
            &live,
            &serde_json::to_vec(normalized.as_ref()).unwrap(),
        )
        .expect("typed ESTOP must reach its bound live-session publisher");
    }

    #[test]
    fn resource_oversized_estop_collapses_to_a_canonical_payload() {
        let live = live_session();
        let mut command = ncp_core::CommandFrame {
            stream: ncp_core::StreamPosition {
                epoch: "10000000-0000-4000-8000-000000000001".into(),
                seq: 1,
            },
            session: live.clone(),
            session_id: "caller-session".into(),
            frame_id: "diagnostic".into(),
            mode: ncp_core::Mode::Estop,
            ..Default::default()
        };
        for index in 0..4 {
            command.channels.insert(
                format!("bulk_{index}"),
                ncp_core::ChannelValue {
                    data: vec![1.0; ncp_core::bounded_json::MAX_ARRAY_ITEMS],
                    unit: None,
                },
            );
        }

        let normalized = normalize_command_for_publish(
            &command,
            "bound-session",
            &live,
            "40000000-0000-4000-8000-000000000004",
            9,
        );

        assert_eq!(normalized.mode, ncp_core::Mode::Estop);
        assert_eq!(normalized.session_id, "bound-session");
        assert_eq!(normalized.session, live);
        assert_eq!(normalized.frame_id, "world");
        assert!(
            normalized.channels.is_empty(),
            "transport fallback must not manufacture an actuator command"
        );
        let payload = serde_json::to_vec(normalized.as_ref()).unwrap();
        ncp_core::bounded_json::preflight(&payload)
            .expect("canonical ESTOP fallback must satisfy the ingress resource budget");
        ncp_core::WireFrame::validate_wire(normalized.as_ref())
            .expect("canonical ESTOP fallback must satisfy typed wire validation");
        check_command_payload_for("bound-session", &live, &payload)
            .expect("canonical ESTOP fallback must pass the publisher gate");
    }

    #[test]
    fn command_dispatch_slot_is_bounded_and_fail_safe_prioritized() {
        const STREAM: &str = "40000000-0000-4000-8000-000000000004";
        let state = std::sync::Mutex::new(CommandDispatchState::default());
        let sequence = std::sync::atomic::AtomicI64::new(0);
        let command = |byte: u8, priority| ncp_core::CommandFrame {
            frame_id: byte.to_string(),
            mode: match priority {
                CommandPriority::Active => ncp_core::Mode::Active,
                CommandPriority::Hold => ncp_core::Mode::Hold,
                CommandPriority::Estop => ncp_core::Mode::Estop,
            },
            ..Default::default()
        };
        assert_eq!(
            enqueue_command(
                &state,
                command(1, CommandPriority::Active),
                STREAM,
                &sequence,
            ),
            ncp_core::transport::CommandSendOutcome::Accepted
        );
        assert_eq!(
            enqueue_command(&state, command(2, CommandPriority::Hold), STREAM, &sequence,),
            ncp_core::transport::CommandSendOutcome::ReplacedPending
        );
        assert_eq!(
            enqueue_command(
                &state,
                command(3, CommandPriority::Active),
                STREAM,
                &sequence,
            ),
            ncp_core::transport::CommandSendOutcome::Rejected,
            "Active must not overwrite a pending HOLD"
        );
        assert_eq!(
            enqueue_command(
                &state,
                command(4, CommandPriority::Estop),
                STREAM,
                &sequence,
            ),
            ncp_core::transport::CommandSendOutcome::ReplacedPending
        );
        assert_eq!(
            enqueue_command(&state, command(5, CommandPriority::Hold), STREAM, &sequence,),
            ncp_core::transport::CommandSendOutcome::Rejected,
            "HOLD must not overwrite a pending ESTOP"
        );
        let queued = state.into_inner().unwrap().pending.unwrap();
        assert_eq!(queued.priority, CommandPriority::Estop);
        assert_eq!(queued.command.frame_id, "4");
        assert_eq!(queued.command.stream.epoch, STREAM);
        assert_eq!(
            queued.command.stream.seq, 1,
            "every pre-publication replacement reuses the selected slot position"
        );
        assert_eq!(sequence.load(std::sync::atomic::Ordering::Relaxed), 1);
    }

    #[test]
    fn ambiguous_estop_blocks_active_until_new_estop_position_succeeds() {
        const STREAM: &str = "40000000-0000-4000-8000-000000000004";
        let state = std::sync::Mutex::new(CommandDispatchState::default());
        let sequence = std::sync::atomic::AtomicI64::new(0);
        let command = |mode| ncp_core::CommandFrame {
            mode,
            ..Default::default()
        };

        assert_eq!(
            enqueue_command(&state, command(ncp_core::Mode::Estop), STREAM, &sequence,),
            ncp_core::transport::CommandSendOutcome::Accepted
        );
        let failed = state.lock().unwrap().pending.take().unwrap();
        assert_eq!(failed.command.stream.seq, 1);
        note_publish_failure(&state, failed.priority);

        assert_eq!(
            enqueue_command(&state, command(ncp_core::Mode::Active), STREAM, &sequence,),
            ncp_core::transport::CommandSendOutcome::Rejected,
            "Active stays blocked after ambiguous fail-safe delivery"
        );
        assert_eq!(sequence.load(std::sync::atomic::Ordering::Relaxed), 1);

        assert_eq!(
            enqueue_command(&state, command(ncp_core::Mode::Estop), STREAM, &sequence,),
            ncp_core::transport::CommandSendOutcome::Accepted
        );
        let retry = state.lock().unwrap().pending.take().unwrap();
        assert_eq!(
            retry.command.stream.seq, 2,
            "recovery is a new logical frame"
        );
        note_publish_success(&state, retry.priority);

        assert_eq!(
            enqueue_command(&state, command(ncp_core::Mode::Active), STREAM, &sequence,),
            ncp_core::transport::CommandSendOutcome::Accepted,
            "Active resumes only after a new fail-safe position succeeds"
        );
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn malformed_estop_correlation_reaches_typed_zenoh_put() {
        const COMMAND_EPOCH: &str = "40000000-0000-4000-8000-000000000004";
        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let live = live_session();
        let received = Arc::new(std::sync::Mutex::new(None::<Vec<u8>>));
        let received_count = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let sink = received.clone();
        let count = received_count.clone();
        bus.subscribe_commands("s", &live, move |_, payload| {
            *sink.lock().unwrap() = Some(payload);
            count.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        let transport = ZenohControlTransport::new(bus.clone(), "s", live.clone())
            .await
            .unwrap();
        let malformed_estop = ncp_core::CommandFrame {
            stream: ncp_core::StreamPosition {
                epoch: COMMAND_EPOCH.into(),
                seq: 1,
            },
            source: Some(ncp_core::StreamPosition {
                epoch: "invalid-source-epoch".into(),
                seq: 0,
            }),
            source_t: f64::NAN,
            session: live.clone(),
            session_id: "s".into(),
            mode: ncp_core::Mode::Estop,
            ..Default::default()
        };

        assert_eq!(
            ncp_core::ControlTransport::send_command(&transport, &malformed_estop),
            ncp_core::transport::CommandSendOutcome::Accepted
        );
        wait_for_count(&received_count, 1, "normalized malformed ESTOP typed put").await;
        let payload = received
            .lock()
            .unwrap()
            .take()
            .expect("typed subscriber captured the ESTOP put");
        let decoded = check_command_payload_for("s", &live, &payload)
            .expect("the emitted ESTOP must pass the typed publisher decoder");
        assert_eq!(
            (
                decoded.mode,
                decoded.source,
                decoded.source_t,
                decoded.authority,
            ),
            (ncp_core::Mode::Estop, None, 0.0, None)
        );
        assert!(
            !transport.fail_safe_delivery_pending(),
            "a successful normalized ESTOP put must clear publication-pending state"
        );

        drop(transport);
        bus.close().await.unwrap();
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
    fn shipped_zenoh_configs_parse_and_client_template_passes_config_preflight() {
        let deploy = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/deploy");
        config_from_file(&deploy.join("zenoh-access-control.json5"))
            .expect("secure router template must match the locked Zenoh config schema");
        let client = config_from_file(&deploy.join("zenoh-client-secure.json5"))
            .expect("secure client template must match the locked Zenoh config schema");
        validate_secure_client_config(&client)
            .expect("shipped client template must satisfy the TLS config preflight");
    }

    #[test]
    fn secure_config_loading_fails_closed_on_missing_input() {
        let missing = std::path::Path::new("/nonexistent/ncp-zenoh-acl.json5");
        assert!(config_from_file(missing).is_err());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn open_secure_fails_closed_without_transport_peer_identity_binding() {
        let error = match ZenohBus::with_secure_config(secure_client_test_config(), Keys::default())
            .await
        {
            Ok(bus) => {
                bus.close().await.unwrap();
                panic!("open_secure must not open an identity-unbound transport")
            }
            Err(error) => error,
        };
        assert!(
            error
                .to_string()
                .contains("does not expose a transport-authenticated peer principal"),
            "{error}"
        );
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
        let live = live_session();
        let e = bus.put_sensor("bad/id", &live, b"{}").await.unwrap_err();
        assert!(e.to_string().contains("invalid session id segment"), "{e}");
        // A glob-escaping entity name on a named publish is rejected too.
        assert!(bus
            .put_sensor_named("uav3", &live, "imu*", b"{}")
            .await
            .is_err());
        let _ = bus.close().await;
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn typed_publishers_share_fence_across_clones_and_separate_concrete_routes() {
        const SENSOR_A: &str = "10000000-0000-4000-8000-000000000001";
        const SENSOR_B: &str = "20000000-0000-4000-8000-000000000002";
        const COMMAND_A: &str = "30000000-0000-4000-8000-000000000003";
        const OBSERVATION_A: &str = "40000000-0000-4000-8000-000000000004";

        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let clone = bus.clone();
        let live = live_session();

        let sensor = sensor_payload("s", SENSOR_A, 2);
        bus.put_sensor("s", &live, &sensor).await.unwrap();
        let duplicate = clone.put_sensor("s", &live, &sensor).await.unwrap_err();
        assert!(
            duplicate.to_string().contains("not strictly greater"),
            "{duplicate}"
        );

        // Concrete keys are independent streams even when the payload position
        // is identical, and clones share one publisher-side high-water fence.
        bus.put_sensor_named("s", &live, "imu", &sensor)
            .await
            .unwrap();
        let named_duplicate = clone
            .put_sensor_named("s", &live, "imu", &sensor)
            .await
            .unwrap_err();
        assert!(
            named_duplicate.to_string().contains("not strictly greater"),
            "{named_duplicate}"
        );

        let foreign = sensor_payload("s", SENSOR_B, 3);
        let foreign_error = clone.put_sensor("s", &live, &foreign).await.unwrap_err();
        assert!(
            foreign_error.to_string().contains("foreign epoch"),
            "{foreign_error}"
        );

        let command = command_payload("s", COMMAND_A, 2);
        bus.publish_command("s", &live, &command).await.unwrap();
        assert!(clone
            .publish_command("s", &live, &command)
            .await
            .unwrap_err()
            .to_string()
            .contains("not strictly greater"));
        bus.publish_command_named("s", &live, "motor", &command)
            .await
            .unwrap();
        assert!(clone
            .publish_command_named("s", &live, "motor", &command)
            .await
            .unwrap_err()
            .to_string()
            .contains("not strictly greater"));

        let observation = observation_payload("s", OBSERVATION_A, 2);
        bus.publish_observation("s", &live, &observation)
            .await
            .unwrap();
        assert!(clone
            .publish_observation("s", &live, &observation)
            .await
            .unwrap_err()
            .to_string()
            .contains("not strictly greater"));

        // A separately constructed wrapper is a new publisher declaration and
        // therefore gets a fresh fence even when it borrows the same session.
        let fresh = ZenohBus::from_session(bus.session().clone(), Keys::default());
        fresh.put_sensor("s", &live, &foreign).await.unwrap();
        fresh.close().await.unwrap();
        bus.close().await.unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn failed_typed_put_consumes_the_position_across_clones() {
        const EPOCH: &str = "50000000-0000-4000-8000-000000000005";

        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let clone = bus.clone();
        let live = live_session();
        let sensor = sensor_payload("s", EPOCH, 1);

        bus.close().await.unwrap();
        let transport_error = clone.put_sensor("s", &live, &sensor).await.unwrap_err();
        assert!(
            transport_error.to_string().contains("zenoh put"),
            "the first attempt must pass the fence and fail at the closed transport: {transport_error}"
        );

        let replay_error = bus.put_sensor("s", &live, &sensor).await.unwrap_err();
        assert!(
            replay_error.to_string().contains("not strictly greater"),
            "an ambiguous put failure must not reopen the consumed position: {replay_error}"
        );

        let command = command_payload("s", EPOCH, 1);
        let classified = clone
            .publish_command_classified("s", &live, &command)
            .await
            .unwrap_err();
        assert!(
            matches!(classified, TypedCommandPublishError::DeliveryAmbiguous(_)),
            "the dispatcher must distinguish post-fence put ambiguity from pre-admission rejection"
        );
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn exact_typed_sensor_subscribers_have_fresh_non_mutating_fences() {
        const EPOCH_A: &str = "60000000-0000-4000-8000-000000000006";
        const EPOCH_B: &str = "70000000-0000-4000-8000-000000000007";

        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let live = live_session();
        let key = bus.keys().sensor("s");
        let first_count = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let seen = first_count.clone();
        bus.subscribe_sensors("s", &live, move |_, _| {
            seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let a2 = sensor_payload("s", EPOCH_A, 2);
        raw_put_until_count(
            &bus,
            &key,
            &a2,
            Plane::Perception,
            &first_count,
            1,
            "the first exact sensor subscriber",
        )
        .await;
        for rejected in [
            sensor_payload("s", EPOCH_A, 1),
            a2.clone(),
            sensor_payload("s", EPOCH_B, 3),
        ] {
            bus.put(&key, &rejected, Plane::Perception).await.unwrap();
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        assert_eq!(
            first_count.load(std::sync::atomic::Ordering::SeqCst),
            1,
            "reorder, duplicate, and foreign epoch must be dropped before callback"
        );

        let second_count = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let seen = second_count.clone();
        bus.subscribe_sensors("s", &live, move |_, _| {
            seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let b3 = sensor_payload("s", EPOCH_B, 3);
        raw_put_until_count(
            &bus,
            &key,
            &b3,
            Plane::Perception,
            &second_count,
            1,
            "the freshly declared exact sensor subscriber",
        )
        .await;
        assert_eq!(first_count.load(std::sync::atomic::Ordering::SeqCst), 1);

        // The old declaration's rejected foreign epoch did not mutate it; its
        // original epoch can still advance while the fresh B-bound declaration
        // rejects that epoch independently.
        let a3 = sensor_payload("s", EPOCH_A, 3);
        raw_put_until_count(
            &bus,
            &key,
            &a3,
            Plane::Perception,
            &first_count,
            2,
            "the original exact sensor epoch advancing after rejection",
        )
        .await;
        assert_eq!(second_count.load(std::sync::atomic::Ordering::SeqCst), 1);
        bus.close().await.unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn typed_sensor_glob_fences_each_actual_route_independently() {
        const IMU_EPOCH: &str = "80000000-0000-4000-8000-000000000008";
        const GPS_EPOCH: &str = "90000000-0000-4000-8000-000000000009";

        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let live = live_session();
        let imu_key = bus.keys().sensor_named("s", "imu");
        let gps_key = bus.keys().sensor_named("s", "gps");
        let total = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let routes = Arc::new(std::sync::Mutex::new(std::collections::BTreeMap::<
            String,
            usize,
        >::new()));
        let seen_total = total.clone();
        let seen_routes = routes.clone();
        bus.subscribe_sensors_glob("s", &live, move |key, _| {
            *seen_routes.lock().unwrap().entry(key).or_default() += 1;
            seen_total.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let imu2 = sensor_payload("s", IMU_EPOCH, 2);
        raw_put_until_count(
            &bus,
            &imu_key,
            &imu2,
            Plane::Perception,
            &total,
            1,
            "the glob IMU route",
        )
        .await;
        let gps1 = sensor_payload("s", GPS_EPOCH, 1);
        raw_put_until_count(
            &bus,
            &gps_key,
            &gps1,
            Plane::Perception,
            &total,
            2,
            "the glob GPS route",
        )
        .await;

        for rejected in [sensor_payload("s", IMU_EPOCH, 1), imu2] {
            bus.put(&imu_key, &rejected, Plane::Perception)
                .await
                .unwrap();
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        assert_eq!(total.load(std::sync::atomic::Ordering::SeqCst), 2);

        let gps2 = sensor_payload("s", GPS_EPOCH, 2);
        raw_put_until_count(
            &bus,
            &gps_key,
            &gps2,
            Plane::Perception,
            &total,
            3,
            "the independently advancing glob GPS route",
        )
        .await;
        {
            let routes = routes.lock().unwrap();
            assert_eq!(routes.get(&imu_key), Some(&1));
            assert_eq!(routes.get(&gps_key), Some(&2));
        }
        bus.close().await.unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn command_and_observation_subscribers_fence_before_effects() {
        const COMMAND_EPOCH: &str = "a0000000-0000-4000-8000-00000000000a";
        const COMMAND_FOREIGN: &str = "b0000000-0000-4000-8000-00000000000b";
        const OBSERVATION_EPOCH: &str = "c0000000-0000-4000-8000-00000000000c";
        const OBSERVATION_FOREIGN: &str = "d0000000-0000-4000-8000-00000000000d";

        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let live = live_session();
        let command_key = bus.keys().command("s");
        let named_command_key = bus.keys().command_named("s", "motor");
        let observation_key = bus.keys().observation("s");
        let command_count = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let named_count = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let observation_count = Arc::new(std::sync::atomic::AtomicUsize::new(0));

        let seen = command_count.clone();
        bus.subscribe_commands("s", &live, move |_, _| {
            seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        let seen = named_count.clone();
        bus.subscribe_command_named("s", &live, "motor", move |_, _| {
            seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        let seen = observation_count.clone();
        bus.subscribe_observations("s", &live, move |_, _| {
            seen.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        })
        .await
        .unwrap();
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;

        let command2 = command_payload("s", COMMAND_EPOCH, 2);
        raw_put_until_count(
            &bus,
            &command_key,
            &command2,
            Plane::Action,
            &command_count,
            1,
            "the exact command callback",
        )
        .await;
        raw_put_until_count(
            &bus,
            &named_command_key,
            &command2,
            Plane::Action,
            &named_count,
            1,
            "the named command callback",
        )
        .await;
        let observation2 = observation_payload("s", OBSERVATION_EPOCH, 2);
        raw_put_until_count(
            &bus,
            &observation_key,
            &observation2,
            Plane::Observation,
            &observation_count,
            1,
            "the queued observation callback",
        )
        .await;

        // A stale-generation ESTOP carries a foreign high sequence. Session
        // binding must reject it before the stream fence or it would poison the
        // declaration and prevent the legitimate live epoch from advancing.
        let mut stale_estop: serde_json::Value =
            serde_json::from_slice(&command_payload("s", COMMAND_FOREIGN, 100)).unwrap();
        stale_estop["mode"] = "estop".into();
        stale_estop["session"]["generation"] = "e0000000-0000-4000-8000-00000000000e".into();
        let stale_estop = serde_json::to_vec(&stale_estop).unwrap();
        for (key, payload, plane) in [
            (&command_key, &command2, Plane::Action),
            (&command_key, &stale_estop, Plane::Action),
            (&named_command_key, &command2, Plane::Action),
        ] {
            bus.put(key, payload, plane).await.unwrap();
        }
        for rejected in [
            observation2.clone(),
            observation_payload("s", OBSERVATION_EPOCH, 1),
            observation_payload("s", OBSERVATION_FOREIGN, 3),
        ] {
            bus.put(&observation_key, &rejected, Plane::Observation)
                .await
                .unwrap();
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        assert_eq!(command_count.load(std::sync::atomic::Ordering::SeqCst), 1);
        assert_eq!(named_count.load(std::sync::atomic::Ordering::SeqCst), 1);
        assert_eq!(
            observation_count.load(std::sync::atomic::Ordering::SeqCst),
            1
        );
        assert_eq!(
            bus.observation_queue_drops_total(),
            0,
            "rejected replays must never enter the bounded observation queue"
        );

        let command3 = command_payload("s", COMMAND_EPOCH, 3);
        raw_put_until_count(
            &bus,
            &command_key,
            &command3,
            Plane::Action,
            &command_count,
            2,
            "the live command after stale ESTOP rejection",
        )
        .await;
        raw_put_until_count(
            &bus,
            &named_command_key,
            &command3,
            Plane::Action,
            &named_count,
            2,
            "the named command stream advancing",
        )
        .await;
        let observation3 = observation_payload("s", OBSERVATION_EPOCH, 3);
        raw_put_until_count(
            &bus,
            &observation_key,
            &observation3,
            Plane::Observation,
            &observation_count,
            2,
            "the observation stream advancing after rejected samples",
        )
        .await;
        assert_eq!(bus.observation_queue_drops_total(), 0);
        bus.close().await.unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn typed_data_plane_apis_reject_cross_session_publish_and_delivery() {
        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let live = live_session();
        let sensor = |session_id: &str| {
            serde_json::to_vec(&serde_json::json!({
                "kind": "sensor_frame",
                "ncp_version": ncp_core::NCP_VERSION,
                "session_id": session_id,
                "stream": {
                    "epoch": "00000000-0000-4000-8000-000000000001",
                    "seq": 1
                },
                "session": {"generation": "00000000-0000-4000-8000-0000000000a2"},
                "t": 0.0,
                "channels": {}
            }))
            .unwrap()
        };
        let command = |session_id: &str| {
            serde_json::to_vec(&serde_json::json!({
                "kind": "command_frame",
                "ncp_version": ncp_core::NCP_VERSION,
                "session_id": session_id,
                "stream": {
                    "epoch": "00000000-0000-4000-8000-000000000002",
                    "seq": 1
                },
                "session": {"generation": "00000000-0000-4000-8000-0000000000a2"},
                "t": 0.0,
                "mode": "hold",
                "ttl_ms": 200.0,
                "channels": {}
            }))
            .unwrap()
        };
        let wrong_sensor = sensor("other");
        let wrong_command = command("other");
        let mut stale_sensor_value: serde_json::Value =
            serde_json::from_slice(&sensor("expected")).unwrap();
        stale_sensor_value["session"]["generation"] = "30000000-0000-4000-8000-000000000003".into();
        let stale_sensor = serde_json::to_vec(&stale_sensor_value).unwrap();
        let mut stale_estop_value: serde_json::Value =
            serde_json::from_slice(&command("expected")).unwrap();
        stale_estop_value["mode"] = "estop".into();
        stale_estop_value["session"]["generation"] = "30000000-0000-4000-8000-000000000003".into();
        let stale_estop = serde_json::to_vec(&stale_estop_value).unwrap();
        let mut missing_generation_estop_value = stale_estop_value;
        missing_generation_estop_value
            .as_object_mut()
            .unwrap()
            .remove("session");
        let missing_generation_estop = serde_json::to_vec(&missing_generation_estop_value).unwrap();

        assert!(bus
            .put_sensor("expected", &live, &wrong_sensor)
            .await
            .is_err());
        assert!(bus
            .put_sensor_named("expected", &live, "imu", &wrong_sensor)
            .await
            .is_err());
        assert!(bus
            .publish_command("expected", &live, &wrong_command)
            .await
            .is_err());
        assert!(bus
            .publish_command_named("expected", &live, "motor", &wrong_command)
            .await
            .is_err());
        assert!(bus
            .put_sensor("expected", &live, &stale_sensor)
            .await
            .is_err());
        assert!(bus
            .publish_command("expected", &live, &stale_estop)
            .await
            .is_err());
        assert!(bus
            .publish_command("expected", &live, &missing_generation_estop)
            .await
            .is_err());

        let sensor_exact = Arc::new(std::sync::Mutex::new(Vec::<String>::new()));
        let sensor_glob = Arc::new(std::sync::Mutex::new(Vec::<String>::new()));
        let command_exact = Arc::new(std::sync::Mutex::new(Vec::<String>::new()));
        let command_named = Arc::new(std::sync::Mutex::new(Vec::<String>::new()));

        let sink = sensor_exact.clone();
        bus.subscribe_sensors("expected", &live, move |_, payload| {
            let value: serde_json::Value = serde_json::from_slice(&payload).unwrap();
            sink.lock()
                .unwrap()
                .push(value["session_id"].as_str().unwrap().to_owned());
        })
        .await
        .unwrap();
        let sink = sensor_glob.clone();
        bus.subscribe_sensors_glob("expected", &live, move |_, payload| {
            let value: serde_json::Value = serde_json::from_slice(&payload).unwrap();
            sink.lock()
                .unwrap()
                .push(value["session_id"].as_str().unwrap().to_owned());
        })
        .await
        .unwrap();
        let sink = command_exact.clone();
        bus.subscribe_commands("expected", &live, move |_, payload| {
            let value: serde_json::Value = serde_json::from_slice(&payload).unwrap();
            sink.lock()
                .unwrap()
                .push(value["session_id"].as_str().unwrap().to_owned());
        })
        .await
        .unwrap();
        let sink = command_named.clone();
        bus.subscribe_command_named("expected", &live, "motor", move |_, payload| {
            let value: serde_json::Value = serde_json::from_slice(&payload).unwrap();
            sink.lock()
                .unwrap()
                .push(value["session_id"].as_str().unwrap().to_owned());
        })
        .await
        .unwrap();

        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        bus.put(
            &bus.keys().sensor("expected"),
            &wrong_sensor,
            Plane::Perception,
        )
        .await
        .unwrap();
        bus.put(
            &bus.keys().sensor_named("expected", "imu"),
            &wrong_sensor,
            Plane::Perception,
        )
        .await
        .unwrap();
        bus.put(
            &bus.keys().command("expected"),
            &wrong_command,
            Plane::Action,
        )
        .await
        .unwrap();
        bus.put(
            &bus.keys().command_named("expected", "motor"),
            &wrong_command,
            Plane::Action,
        )
        .await
        .unwrap();
        bus.put(
            &bus.keys().sensor("expected"),
            &stale_sensor,
            Plane::Perception,
        )
        .await
        .unwrap();
        bus.put(&bus.keys().command("expected"), &stale_estop, Plane::Action)
            .await
            .unwrap();
        bus.put(
            &bus.keys().command_named("expected", "motor"),
            &missing_generation_estop,
            Plane::Action,
        )
        .await
        .unwrap();
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        for seen in [&sensor_exact, &sensor_glob, &command_exact, &command_named] {
            assert!(
                seen.lock().unwrap().is_empty(),
                "a typed subscriber delivered a cross-session payload"
            );
        }

        let good_sensor = sensor("expected");
        let good_command = command("expected");
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(2);
        while std::time::Instant::now() < deadline {
            bus.put(
                &bus.keys().sensor("expected"),
                &good_sensor,
                Plane::Perception,
            )
            .await
            .unwrap();
            bus.put(
                &bus.keys().sensor_named("expected", "imu"),
                &good_sensor,
                Plane::Perception,
            )
            .await
            .unwrap();
            bus.put(
                &bus.keys().command("expected"),
                &good_command,
                Plane::Action,
            )
            .await
            .unwrap();
            bus.put(
                &bus.keys().command_named("expected", "motor"),
                &good_command,
                Plane::Action,
            )
            .await
            .unwrap();
            tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            if [&sensor_exact, &sensor_glob, &command_exact, &command_named]
                .iter()
                .all(|seen| !seen.lock().unwrap().is_empty())
            {
                break;
            }
        }
        for seen in [&sensor_exact, &sensor_glob, &command_exact, &command_named] {
            let seen = seen.lock().unwrap();
            assert!(
                !seen.is_empty(),
                "valid same-session payload was not delivered"
            );
            assert!(seen.iter().all(|session| session == "expected"));
        }

        bus.close().await.unwrap();
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 1)]
    async fn session_subscribers_are_releasable_without_closing_the_bus() {
        let bus = ZenohBus::with_config(isolated_test_config(), Keys::default())
            .await
            .unwrap();
        let live = live_session();
        bus.subscribe_commands("s1", &live, |_, _| {})
            .await
            .unwrap();
        bus.subscribe_observations("s1", &live, |_, _| {})
            .await
            .unwrap();
        bus.subscribe_commands("s2", &live, |_, _| {})
            .await
            .unwrap();
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
        assert!(bus
            .observation_workers
            .lock()
            .unwrap()
            .iter()
            .all(|(selector, _)| !selector.contains("/s1/")));
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
