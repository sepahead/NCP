#![doc = include_str!("../README.md")]
//!
//! # Configuration and security
//!
//! Config via env:
//!   NCP_REALM        key-expression realm           (default `ncp`; set per deployment)
//!   NCP_BRIDGE_ADDR  numeric loopback TCP address    (default `127.0.0.1:28474`)
//!   NCP_ZENOH_CONFIG path to a strict Zenoh client config (default: quiet, no auth)
//!
//! Security: the realm is *addressing*, not a credential. By default this gateway
//! opens the hardened config (multicast scouting disabled). For an enforced
//! deployment run the realm-rendered router ACL separately and set
//! `NCP_ZENOH_CONFIG` to a configured copy of `deploy/zenoh-client-secure.json5`.
//! If it is unset or the strict client validation fails, the secure path refuses to
//! start rather than silently opening a hole.

use ncp_core::keys::Keys;
use ncp_zenoh::{ZenohBus, NCP_ZENOH_CONFIG_ENV};
use std::ffi::OsStr;
use std::fmt;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::str::FromStr;
use std::sync::{Arc, Mutex};
use std::time::Duration;
use std::{collections::BTreeMap, collections::BTreeSet};

const DEFAULT_BRIDGE_ADDR: &str = "127.0.0.1:28474";
const MAX_GATEWAY_LINEAGES: usize = 4_096;
const MAX_GATEWAY_OBSERVATION_POSITIONS: usize = 4_096;

#[derive(Debug)]
struct GatewayObservationFence {
    epoch: String,
    high_water: i64,
    reply_fingerprints: BTreeMap<i64, String>,
}

#[derive(Debug)]
struct GatewayLiveSession {
    generation: String,
    observation: Option<GatewayObservationFence>,
}

#[derive(Clone, Debug)]
enum GatewayRequestFence {
    Open {
        session_id: String,
        attempt: u64,
    },
    Mutation {
        session_id: String,
        generation: String,
        kind: String,
    },
}

#[derive(Debug, Default)]
struct GatewayRestartState {
    next_open_attempt: u64,
    openings: BTreeMap<String, u64>,
    live: BTreeMap<String, GatewayLiveSession>,
    seen_generations: BTreeSet<(String, String)>,
    observation_positions: usize,
}

impl GatewayRestartState {
    fn retire_live(&mut self, session_id: &str) -> Result<(), String> {
        if let Some(live) = self.live.remove(session_id) {
            let retained = live
                .observation
                .map_or(0, |observation| observation.reply_fingerprints.len());
            self.observation_positions = self
                .observation_positions
                .checked_sub(retained)
                .ok_or_else(|| "gateway observation fence state is inconsistent".to_owned())?;
        }
        Ok(())
    }

    fn begin_request(
        &mut self,
        request: &serde_json::Value,
    ) -> Result<GatewayRequestFence, String> {
        let kind = ncp_core::message_kind(request)
            .ok_or_else(|| "gateway request carries no kind".to_owned())?;
        let session_id = request
            .get("session_id")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| "gateway request carries no session_id".to_owned())?;
        if kind == "open_session" {
            if !self.openings.contains_key(session_id)
                && self.openings.len() >= MAX_GATEWAY_LINEAGES
            {
                return Err("gateway opening fence reached its non-evicting capacity".to_owned());
            }
            self.next_open_attempt = self
                .next_open_attempt
                .checked_add(1)
                .ok_or_else(|| "gateway open-attempt counter exhausted".to_owned())?;
            let attempt = self.next_open_attempt;
            self.retire_live(session_id)?;
            self.openings.insert(session_id.to_owned(), attempt);
            return Ok(GatewayRequestFence::Open {
                session_id: session_id.to_owned(),
                attempt,
            });
        }
        if !matches!(kind, "step_request" | "run_request" | "close_session") {
            return Err(format!(
                "gateway restart fence does not accept lifecycle request kind {kind:?}"
            ));
        }
        let generation = request
            .pointer("/session/generation")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| "mutating gateway request carries no session generation".to_owned())?;
        let live = self.live.get(session_id).ok_or_else(|| {
            "gateway has not observed a fresh successful open for this session since startup"
                .to_owned()
        })?;
        if live.generation != generation {
            return Err("gateway mutation generation does not match its live opening".to_owned());
        }
        if kind == "close_session" {
            self.retire_live(session_id)?;
        }
        Ok(GatewayRequestFence::Mutation {
            session_id: session_id.to_owned(),
            generation: generation.to_owned(),
            kind: kind.to_owned(),
        })
    }

    fn accept_reply(
        &mut self,
        fence: &GatewayRequestFence,
        reply: &serde_json::Value,
    ) -> Result<(), String> {
        match fence {
            GatewayRequestFence::Open {
                session_id,
                attempt,
            } => {
                if self.openings.get(session_id) != Some(attempt) {
                    return Err("gateway open result was superseded by a newer attempt".to_owned());
                }
                self.openings.remove(session_id);
                if ncp_core::message_kind(reply) == Some("error") {
                    return Ok(());
                }
                if reply.get("ok").and_then(serde_json::Value::as_bool) == Some(false) {
                    return Ok(());
                }
                let generation = reply
                    .pointer("/session/generation")
                    .and_then(serde_json::Value::as_str)
                    .ok_or_else(|| "successful open reply carries no generation".to_owned())?;
                let key = (session_id.clone(), generation.to_owned());
                if self.seen_generations.contains(&key) {
                    return Err("gateway open reply revives a retired generation".to_owned());
                }
                if self.seen_generations.len() >= MAX_GATEWAY_LINEAGES {
                    return Err(
                        "gateway generation fence reached its non-evicting capacity".to_owned()
                    );
                }
                self.seen_generations.insert(key);
                self.live.insert(
                    session_id.clone(),
                    GatewayLiveSession {
                        generation: generation.to_owned(),
                        observation: None,
                    },
                );
                Ok(())
            }
            GatewayRequestFence::Mutation {
                session_id,
                generation,
                kind,
            } => {
                if ncp_core::message_kind(reply) == Some("error") || kind == "close_session" {
                    return Ok(());
                }
                let live = self.live.get_mut(session_id).ok_or_else(|| {
                    "gateway mutation result belongs to a retired or superseded session".to_owned()
                })?;
                if &live.generation != generation {
                    return Err("gateway mutation result generation is no longer live".to_owned());
                }
                let epoch = reply
                    .pointer("/stream/epoch")
                    .and_then(serde_json::Value::as_str)
                    .ok_or_else(|| "observation reply carries no stream epoch".to_owned())?;
                let seq = reply
                    .pointer("/stream/seq")
                    .and_then(serde_json::Value::as_i64)
                    .ok_or_else(|| {
                        "observation reply carries no exact stream sequence".to_owned()
                    })?;
                reply
                    .get("receipt")
                    .and_then(serde_json::Value::as_object)
                    .ok_or_else(|| "observation reply carries no receipt".to_owned())?;
                // Retain a fixed-size digest of the complete parsed reply, not
                // merely its receipt. The result_digest is not independently
                // recomputable at this boundary, so receipt equality alone must
                // never authorize a changed result body at the same position.
                // serde_json::Value maps serialize in deterministic key order.
                let fingerprint =
                    ncp_core::idempotency::sha256_hex(&serde_json::to_vec(reply).map_err(
                        |error| format!("observation reply cannot be fingerprinted: {error}"),
                    )?);
                match &mut live.observation {
                    None if seq == 1 => {
                        if self.observation_positions >= MAX_GATEWAY_OBSERVATION_POSITIONS {
                            return Err(
                                "gateway observation fence reached its non-evicting capacity"
                                    .to_owned(),
                            );
                        }
                        live.observation = Some(GatewayObservationFence {
                            epoch: epoch.to_owned(),
                            high_water: 1,
                            reply_fingerprints: BTreeMap::from([(1, fingerprint)]),
                        });
                        self.observation_positions += 1;
                        Ok(())
                    }
                    None => Err(
                        "first observation reply for a fresh generation must use seq 1".to_owned(),
                    ),
                    Some(observation) if observation.epoch != epoch => Err(
                        "observation reply changed epoch without a fresh successful open".to_owned(),
                    ),
                    Some(observation) if seq > observation.high_water => {
                        if self.observation_positions >= MAX_GATEWAY_OBSERVATION_POSITIONS {
                            return Err(
                                "gateway observation fence reached its non-evicting capacity"
                                    .to_owned(),
                            );
                        }
                        observation.high_water = seq;
                        observation.reply_fingerprints.insert(seq, fingerprint);
                        self.observation_positions += 1;
                        Ok(())
                    }
                    Some(observation)
                        if seq <= observation.high_water
                            && observation.reply_fingerprints.get(&seq) == Some(&fingerprint) =>
                    {
                        Ok(())
                    }
                    Some(observation) => Err(format!(
                        "observation stream is replayed, reordered, or non-increasing: high-water {}, got {seq}",
                        observation.high_water
                    )),
                }
            }
        }
    }

    fn finish_request(&mut self, fence: &GatewayRequestFence) {
        if let GatewayRequestFence::Open {
            session_id,
            attempt,
        } = fence
        {
            if self.openings.get(session_id) == Some(attempt) {
                self.openings.remove(session_id);
            }
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct BridgeEndpoint(SocketAddr);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum BridgeEndpointError {
    NonUnicode,
    Malformed,
    ZeroPort,
    NonLoopback,
}

impl fmt::Display for BridgeEndpointError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NonUnicode => write!(formatter, "must be valid UTF-8"),
            Self::Malformed => write!(
                formatter,
                "must be a numeric IP socket address such as 127.0.0.1:28474 or [::1]:28474; hostnames and paths are rejected"
            ),
            Self::ZeroPort => write!(formatter, "must use a nonzero TCP port"),
            Self::NonLoopback => write!(formatter, "must use a loopback IP address"),
        }
    }
}

impl std::error::Error for BridgeEndpointError {}

impl FromStr for BridgeEndpoint {
    type Err = BridgeEndpointError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let address = value
            .parse::<SocketAddr>()
            .map_err(|_| BridgeEndpointError::Malformed)?;
        if address.port() == 0 {
            return Err(BridgeEndpointError::ZeroPort);
        }
        if !address.ip().is_loopback() {
            return Err(BridgeEndpointError::NonLoopback);
        }
        Ok(Self(address))
    }
}

impl fmt::Display for BridgeEndpoint {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.0.fmt(formatter)
    }
}

fn bridge_endpoint_from_env(value: Option<&OsStr>) -> Result<BridgeEndpoint, BridgeEndpointError> {
    value
        .unwrap_or_else(|| OsStr::new(DEFAULT_BRIDGE_ADDR))
        .to_str()
        .ok_or(BridgeEndpointError::NonUnicode)?
        .parse()
}

fn realm_from_env(value: Option<&OsStr>) -> Result<String, &'static str> {
    match value {
        None => Ok(ncp_core::DEFAULT_REALM.to_owned()),
        Some(value) => value
            .to_str()
            .map(str::to_owned)
            .ok_or("must be valid UTF-8"),
    }
}

fn require_loopback_peer(peer: SocketAddr) -> std::io::Result<()> {
    if peer.ip().is_loopback() {
        return Ok(());
    }
    Err(std::io::Error::new(
        std::io::ErrorKind::PermissionDenied,
        "Python bridge connection resolved to a non-loopback peer",
    ))
}

fn read_bridge_reply(reader: &mut impl BufRead) -> std::io::Result<Vec<u8>> {
    let maximum_line_bytes = ncp_core::bounded_json::MAX_FRAME_BYTES + 2;
    let mut limited = reader.take(maximum_line_bytes as u64);
    let mut line = Vec::new();
    if limited.read_until(b'\n', &mut line)? == 0 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::UnexpectedEof,
            "Python bridge closed without a reply",
        ));
    }
    if line.last() != Some(&b'\n') {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "Python bridge reply is not newline terminated within the NCP frame budget",
        ));
    }
    line.pop();
    if line.last() == Some(&b'\r') {
        line.pop();
    }
    if line.len() > ncp_core::bounded_json::MAX_FRAME_BYTES {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "Python bridge reply exceeds the NCP frame byte limit",
        ));
    }
    ncp_core::bounded_json::preflight(&line).map_err(|error| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            format!("Python bridge reply fails bounded JSON preflight: {error}"),
        )
    })?;
    Ok(line)
}

/// Bind a native-1.0 backend reply to the complete originating lifecycle
/// request before it can cross the gateway. The loopback backend may restart
/// independently; a syntactically valid reply from an old session generation or
/// operation must therefore be contained rather than forwarded.
fn validate_bridge_reply_for_request(request: &[u8], reply: &[u8]) -> Result<(), String> {
    let request = ncp_core::bounded_json::parse_value(request)
        .map_err(|error| format!("invalid gateway request JSON: {error}"))?;
    ncp_core::validate(&request).map_err(|error| format!("invalid gateway request: {error}"))?;
    let request_kind = ncp_core::message_kind(&request)
        .ok_or_else(|| "gateway request carries no kind".to_owned())?;
    let session_id = request
        .get("session_id")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| "gateway request carries no session_id".to_owned())?;
    let reply = ncp_core::validate_rpc_reply_for(request_kind, session_id, reply)
        .map_err(|error| format!("invalid backend reply: {error}"))?;
    let reply_kind = ncp_core::message_kind(&reply)
        .ok_or_else(|| "validated lifecycle reply carries no kind".to_owned())?;
    let receipt = reply.get("receipt").filter(|receipt| !receipt.is_null());

    if request_kind == "open_session" && reply_kind == "session_opened" {
        for field in [
            "security_profile",
            "security_state_digest",
            "gateway_permitted",
            "gateway",
        ] {
            if request.get(field) != reply.get(field) {
                return Err(format!(
                    "backend open reply {field} does not match the precommitted request"
                ));
            }
        }
    }

    if matches!(
        request_kind,
        "step_request" | "run_request" | "close_session"
    ) {
        let expected_generation = request
            .pointer("/session/generation")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| "mutating gateway request carries no session generation".to_owned())?;
        let reply_generation = reply
            .pointer("/session/generation")
            .and_then(serde_json::Value::as_str);
        match reply_generation {
            Some(generation) if generation == expected_generation => {}
            None if reply_kind == "error" && receipt.is_none() => {}
            Some(generation) => {
                return Err(format!(
                    "backend reply session generation mismatch: expected {expected_generation:?}, got {generation:?}"
                ))
            }
            None => {
                return Err(
                    "terminal backend reply carries no session generation".to_owned(),
                )
            }
        }

        if let Some(receipt) = receipt {
            let expected_operation_id = request
                .pointer("/operation/operation_id")
                .and_then(serde_json::Value::as_str)
                .ok_or_else(|| "mutating gateway request carries no operation_id".to_owned())?;
            let expected_request_digest = request
                .pointer("/operation/request_digest")
                .and_then(serde_json::Value::as_str)
                .ok_or_else(|| "mutating gateway request carries no request_digest".to_owned())?;
            if receipt
                .get("operation_id")
                .and_then(serde_json::Value::as_str)
                != Some(expected_operation_id)
            {
                return Err("backend receipt operation_id does not match the request".to_owned());
            }
            if receipt
                .get("request_digest")
                .and_then(serde_json::Value::as_str)
                != Some(expected_request_digest)
            {
                return Err("backend receipt request_digest does not match the request".to_owned());
            }
        } else if reply_kind != "error" {
            return Err("successful mutation reply carries no responder receipt".to_owned());
        }
    } else if receipt.is_some() {
        return Err("non-mutating open reply must not carry a mutation receipt".to_owned());
    }
    Ok(())
}

fn handle_identity_argument() -> bool {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    match arguments.as_slice() {
        [] => false,
        [argument] if argument == "--version" => {
            println!("ncp-gateway {}", env!("CARGO_PKG_VERSION"));
            true
        }
        [argument] if argument == "--identity-json" => {
            println!(
                "{}",
                serde_json::json!({
                    "package": "ncp-gateway",
                    "package_version": env!("CARGO_PKG_VERSION"),
                    "wire_version": ncp_core::NCP_VERSION,
                    "compact_proto_hash": ncp_core::CONTRACT_HASH,
                    "normative_contract_digest": ncp_core::NORMATIVE_CONTRACT_DIGEST,
                    "build_identity": ncp_core::BUILD_IDENTITY,
                })
            );
            true
        }
        _ => {
            eprintln!("usage: ncp-gateway [--version|--identity-json]");
            std::process::exit(2);
        }
    }
}

/// Forward one NCP request (JSON bytes) to the Python bridge and return the reply
/// (JSON bytes). Newline-delimited JSON, one request → one reply. Blocking — the
/// control-plane RPC is rare (session lifecycle), never the per-tick hot path.
fn forward_to_python(endpoint: BridgeEndpoint, request: &[u8]) -> std::io::Result<Vec<u8>> {
    let stream = TcpStream::connect(endpoint.0)?;
    require_loopback_peer(stream.peer_addr()?)?;
    stream.set_read_timeout(Some(Duration::from_secs(30)))?;
    stream.set_write_timeout(Some(Duration::from_secs(30)))?;
    let mut writer = stream.try_clone()?;
    writer.write_all(request)?;
    writer.write_all(b"\n")?;
    writer.flush()?;
    let mut reader = BufReader::new(stream);
    read_bridge_reply(&mut reader)
}

fn error_frame(code: ncp_core::RpcErrorCode, message: &str, request: &[u8]) -> Vec<u8> {
    let request = serde_json::from_slice::<serde_json::Value>(request).ok();
    let session_id = request
        .as_ref()
        .and_then(|value| value.get("session_id"))
        .and_then(|value| value.as_str())
        .filter(|session_id| ncp_core::valid_id_segment(session_id))
        .map(str::to_owned);
    let session = request
        .as_ref()
        .and_then(|value| value.get("session"))
        .and_then(|value| serde_json::from_value::<ncp_core::SessionRef>(value.clone()).ok())
        .filter(|value| ncp_core::is_canonical_uuid_v4(&value.generation));
    let request_kind = request
        .as_ref()
        .and_then(ncp_core::message_kind)
        .map(str::to_owned);
    ncp_core::rpc_error_payload_with_session(code, message, session_id, session, request_kind)
}

#[tokio::main]
async fn main() {
    if handle_identity_argument() {
        return;
    }
    let realm = match realm_from_env(std::env::var_os("NCP_REALM").as_deref()) {
        Ok(realm) => realm,
        Err(error) => {
            eprintln!("[ncp-gateway] refusing invalid NCP_REALM: {error}");
            std::process::exit(1);
        }
    };
    let bridge_addr = std::env::var_os("NCP_BRIDGE_ADDR");
    let bridge_endpoint = match bridge_endpoint_from_env(bridge_addr.as_deref()) {
        Ok(endpoint) => endpoint,
        Err(error) => {
            eprintln!("[ncp-gateway] refusing invalid NCP_BRIDGE_ADDR: {error}");
            std::process::exit(1);
        }
    };

    // Honor NCP_ZENOH_CONFIG explicitly. The current ncp-zenoh secure path validates
    // the strict client config and then fails closed because its callbacks cannot
    // expose a transport-authenticated peer principal for IdentityClaim binding.
    // When unset, this remains the visibly unauthenticated development path with
    // multicast scouting off. The realm is addressing, not a credential.
    let keys = match Keys::try_new(realm.clone()) {
        Ok(keys) => keys,
        Err(error) => {
            eprintln!("[ncp-gateway] refusing invalid NCP_REALM: {error}");
            std::process::exit(1);
        }
    };
    let open = match std::env::var_os(NCP_ZENOH_CONFIG_ENV) {
        Some(path) => {
            eprintln!(
                "[ncp-gateway] requesting production-secure Zenoh config from \
                 {NCP_ZENOH_CONFIG_ENV}={path:?}; startup will fail closed until \
                 transport-authenticated peer identity is callback-visible"
            );
            ZenohBus::open_secure(keys).await
        }
        None => {
            eprintln!(
                "[ncp-gateway] INSECURE dev-loopback-insecure: {NCP_ZENOH_CONFIG_ENV} \
                 is unset; multicast scouting is OFF but there is no ACL/TLS. The realm \
                 is addressing, not a credential. production-secure is currently \
                 unavailable in ncp-zenoh; see SECURITY.md."
            );
            ZenohBus::open_realm(keys).await
        }
    };
    let bus = match open {
        Ok(b) => b,
        Err(e) => {
            eprintln!("[ncp-gateway] failed to open Zenoh session: {e}");
            std::process::exit(1);
        }
    };

    let endpoint = bridge_endpoint;
    let restart_state = Arc::new(Mutex::new(GatewayRestartState::default()));
    let callback_state = Arc::clone(&restart_state);
    let serve = bus
        .serve_rpc(move |req: Vec<u8>| {
            // forward_to_python is blocking std::net I/O (30s timeouts). block_in_place
            // frees this tokio worker so other tasks on the shared multi-thread runtime
            // (data planes, Zenoh internals) aren't starved while the bridge round-trip
            // is in flight. Valid here: ncp-gateway runs on the multi-thread runtime.
            let parsed = match ncp_core::bounded_json::parse_value(&req)
                .map_err(|error| error.to_string())
                .and_then(|value| {
                    ncp_core::validate(&value)
                        .map_err(|error| error.to_string())
                        .map(|_| value)
                }) {
                Ok(value) => value,
                Err(error) => {
                    return error_frame(
                        ncp_core::RpcErrorCode::InvalidMessage,
                        &format!("invalid NCP request: {error}"),
                        &req,
                    )
                }
            };
            let request_fence = match callback_state
                .lock()
                .map_err(|_| "gateway restart-state lock is poisoned".to_owned())
                .and_then(|mut state| state.begin_request(&parsed))
            {
                Ok(fence) => fence,
                Err(error) => {
                    return error_frame(
                        ncp_core::RpcErrorCode::ContainedInternalFailure,
                        &format!("gateway restart fence rejected request: {error}"),
                        &req,
                    )
                }
            };
            tokio::task::block_in_place(|| {
                let response = match forward_to_python(endpoint, &req) {
                    Ok(reply) if !reply.is_empty() => {
                        match validate_bridge_reply_for_request(&req, &reply) {
                            Ok(()) => {
                                let parsed_reply = ncp_core::bounded_json::parse_value(&reply)
                                    .map_err(|error| error.to_string());
                                let accepted = parsed_reply.and_then(|parsed_reply| {
                                    callback_state
                                        .lock()
                                        .map_err(|_| {
                                            "gateway restart-state lock is poisoned".to_owned()
                                        })
                                        .and_then(|mut state| {
                                            state.accept_reply(&request_fence, &parsed_reply)
                                        })
                                });
                                match accepted {
                                    Ok(()) => reply,
                                    Err(error) => error_frame(
                                        ncp_core::RpcErrorCode::ContainedInternalFailure,
                                        &format!("gateway restart fence rejected reply: {error}"),
                                        &req,
                                    ),
                                }
                            }
                            Err(error) => error_frame(
                                ncp_core::RpcErrorCode::ContainedInternalFailure,
                                &format!("uncorrelated Python bridge reply: {error}"),
                                &req,
                            ),
                        }
                    }
                    Ok(_) => error_frame(
                        ncp_core::RpcErrorCode::ContainedInternalFailure,
                        "empty reply from Python bridge",
                        &req,
                    ),
                    Err(e) => error_frame(
                        ncp_core::RpcErrorCode::ContainedInternalFailure,
                        &format!("bridge I/O or reply failure at {endpoint}: {e}"),
                        &req,
                    ),
                };
                let completed = callback_state
                    .lock()
                    .map_err(|_| "gateway restart-state lock is poisoned".to_owned())
                    .map(|mut state| state.finish_request(&request_fence));
                match completed {
                    Ok(()) => response,
                    Err(error) => error_frame(
                        ncp_core::RpcErrorCode::ContainedInternalFailure,
                        &format!("gateway restart fence could not complete request: {error}"),
                        &req,
                    ),
                }
            })
        })
        .await;
    let serve_task = match serve {
        Ok(task) => task,
        Err(e) => {
            eprintln!("[ncp-gateway] failed to declare RPC queryable: {e}");
            std::process::exit(1);
        }
    };

    println!(
        "[ncp-gateway] serving NCP RPC on Zenoh keys '{realm}/rpc/*' → loopback Python bridge {bridge_endpoint}"
    );
    println!(
        "[ncp-gateway] RPC-only bridge; streaming sensor/command/observation planes connect directly between NCP peers"
    );
    println!("[ncp-gateway] Ctrl-C to stop.");
    let _ = tokio::signal::ctrl_c().await;
    serve_task.abort();
    let _ = bus.close().await;
    println!("[ncp-gateway] stopped.");
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    const GENERATION_A: &str = "293279f3-d459-4bfd-aeeb-604799e96925";
    const GENERATION_B: &str = "693279f3-d459-4bfd-aeeb-604799e96925";

    fn close_request(generation: &str, operation_id: &str) -> Vec<u8> {
        let mut request = serde_json::json!({
            "ncp_version": ncp_core::NCP_VERSION,
            "kind": "close_session",
            "session_id": "s",
            "session": {"generation": generation},
            "operation": {
                "operation_id": operation_id,
                "request_digest": "",
                "session_epoch": generation,
                "expected_state_version": 3,
                "deadline_utc_ms": 1_700_000_030_000_i64,
                "retry": false
            },
            "authority": {
                "session_epoch": generation,
                "term": 1,
                "lease_id": "20000000-0000-4000-8000-000000000001",
                "issuer_principal_id": "authority",
                "holder_principal_id": "controller",
                "holder_entity_id": "controller",
                "issued_at_utc_ms": 1_700_000_000_000_i64,
                "expires_at_utc_ms": 1_700_000_030_000_i64
            }
        });
        let digest = ncp_core::request_digest(&request).unwrap();
        request["operation"]["request_digest"] = serde_json::Value::String(digest);
        ncp_core::validate(&request).unwrap();
        serde_json::to_vec(&request).unwrap()
    }

    fn close_reply(request: &[u8], generation: &str) -> Vec<u8> {
        let request: serde_json::Value = serde_json::from_slice(request).unwrap();
        let reply = serde_json::json!({
            "ncp_version": ncp_core::NCP_VERSION,
            "kind": "session_closed",
            "session_id": "s",
            "ok": true,
            "session": {"generation": generation},
            "receipt": {
                "operation_id": request["operation"]["operation_id"],
                "request_digest": request["operation"]["request_digest"],
                "result_digest": "82bfecaa6d47a3ec4cc56b948f511e641d186d19545b9a0c697b825ecaff5241",
                "outcome": "succeeded",
                "state_version": 4,
                "committed_at_utc_ms": 1_700_000_001_000_i64,
                "responder_principal_id": "body-principal",
                "responder_entity_id": "simulator"
            }
        });
        ncp_core::validate(&reply).unwrap();
        serde_json::to_vec(&reply).unwrap()
    }

    fn open_pair() -> (serde_json::Value, serde_json::Value) {
        let mut request: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../conformance/vectors/open_session.json"
        ))
        .unwrap();
        let mut reply: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../conformance/vectors/session_opened.json"
        ))
        .unwrap();
        request["session_id"] = serde_json::Value::String("s".into());
        reply["session_id"] = serde_json::Value::String("s".into());
        (request, reply)
    }

    #[test]
    fn bridge_endpoint_accepts_ipv4_loopback() {
        let endpoint = "127.0.0.1:28474"
            .parse::<BridgeEndpoint>()
            .expect("IPv4 loopback endpoint should pass");
        assert_eq!(endpoint.0, "127.0.0.1:28474".parse().unwrap());
    }

    #[test]
    fn bridge_endpoint_uses_loopback_default_when_unset() {
        let endpoint = bridge_endpoint_from_env(None).expect("default endpoint should pass");
        assert_eq!(endpoint.0, DEFAULT_BRIDGE_ADDR.parse().unwrap());
    }

    #[test]
    fn bridge_endpoint_accepts_ipv6_loopback() {
        let endpoint = "[::1]:28474"
            .parse::<BridgeEndpoint>()
            .expect("IPv6 loopback endpoint should pass");
        assert_eq!(endpoint.0, "[::1]:28474".parse().unwrap());
    }

    #[test]
    fn bridge_endpoint_rejects_non_loopback_address() {
        let error = "192.0.2.1:28474"
            .parse::<BridgeEndpoint>()
            .expect_err("remote endpoint must fail");
        assert_eq!(error, BridgeEndpointError::NonLoopback);
    }

    #[test]
    fn bridge_endpoint_rejects_unspecified_address() {
        let error = "0.0.0.0:28474"
            .parse::<BridgeEndpoint>()
            .expect_err("unspecified endpoint must fail");
        assert_eq!(error, BridgeEndpointError::NonLoopback);
    }

    #[test]
    fn bridge_endpoint_rejects_hostname() {
        let error = "localhost:28474"
            .parse::<BridgeEndpoint>()
            .expect_err("hostnames must fail closed");
        assert_eq!(error, BridgeEndpointError::Malformed);
    }

    #[test]
    fn bridge_endpoint_rejects_missing_port() {
        let error = "127.0.0.1"
            .parse::<BridgeEndpoint>()
            .expect_err("missing port must fail");
        assert_eq!(error, BridgeEndpointError::Malformed);
    }

    #[cfg(unix)]
    #[test]
    fn bridge_endpoint_rejects_non_unicode_environment_value() {
        use std::os::unix::ffi::OsStrExt;

        let error = bridge_endpoint_from_env(Some(OsStr::from_bytes(b"\xff")))
            .expect_err("non-Unicode configuration must fail");
        assert_eq!(error, BridgeEndpointError::NonUnicode);
    }

    #[cfg(unix)]
    #[test]
    fn realm_rejects_non_unicode_environment_value() {
        use std::os::unix::ffi::OsStrExt;

        let error = realm_from_env(Some(OsStr::from_bytes(b"\xff")))
            .expect_err("non-Unicode realms must fail rather than select the default realm");
        assert_eq!(error, "must be valid UTF-8");
    }

    #[test]
    fn bridge_endpoint_rejects_zero_port() {
        let error = "127.0.0.1:0"
            .parse::<BridgeEndpoint>()
            .expect_err("port zero must fail");
        assert_eq!(error, BridgeEndpointError::ZeroPort);
    }

    #[test]
    fn bridge_peer_check_rejects_non_loopback_address() {
        let peer = "198.51.100.7:28474".parse().unwrap();
        let error = require_loopback_peer(peer).expect_err("remote peer must fail");
        assert_eq!(error.kind(), std::io::ErrorKind::PermissionDenied);
    }

    #[test]
    fn bridge_peer_check_accepts_loopback_address() {
        let peer = "127.0.0.1:28474".parse().unwrap();
        assert!(require_loopback_peer(peer).is_ok());
    }

    #[test]
    fn bridge_reply_reader_accepts_one_bounded_json_line() {
        let mut input = Cursor::new(b"{\"kind\":\"error\"}\r\nignored");
        let reply = read_bridge_reply(&mut input).expect("bounded line should pass");
        assert_eq!(reply, br#"{"kind":"error"}"#);
    }

    #[test]
    fn bridge_reply_reader_rejects_unterminated_input() {
        let mut input = Cursor::new(br#"{"kind":"error"}"#);
        let error = read_bridge_reply(&mut input).expect_err("missing delimiter must fail");
        assert_eq!(error.kind(), std::io::ErrorKind::InvalidData);
    }

    #[test]
    fn bridge_reply_reader_rejects_oversized_input() {
        let mut input = Cursor::new(vec![b'x'; ncp_core::bounded_json::MAX_FRAME_BYTES + 3]);
        let error = read_bridge_reply(&mut input).expect_err("oversized reply must fail");
        assert_eq!(error.kind(), std::io::ErrorKind::InvalidData);
    }

    #[test]
    fn bridge_reply_reader_rejects_duplicate_keys() {
        let mut input = Cursor::new(b"{\"kind\":\"error\",\"kind\":\"error\"}\n");
        let error = read_bridge_reply(&mut input).expect_err("duplicate key must fail");
        assert!(error.to_string().contains("NCP-LIMIT-007"), "{error}");
    }

    #[test]
    fn error_frame_classifies_and_preserves_valid_session_pair() {
        let request = br#"{
            "ncp_version":"1.0",
            "kind":"step_request",
            "session_id":"s",
            "session":{"generation":"293279f3-d459-4bfd-aeeb-604799e96925"}
        }"#;
        let reply = error_frame(
            ncp_core::RpcErrorCode::ContainedInternalFailure,
            "bridge unavailable",
            request,
        );
        let reply: serde_json::Value = serde_json::from_slice(&reply).unwrap();
        ncp_core::validate(&reply).unwrap();
        assert_eq!(reply["code"], "NCP-INTERNAL-001");
        assert_eq!(reply["session_id"], "s");
        assert_eq!(
            reply["session"]["generation"],
            "293279f3-d459-4bfd-aeeb-604799e96925"
        );
        assert!(reply["receipt"].is_null());
    }

    #[test]
    fn bridge_reply_gate_accepts_exact_generation_operation_and_digest() {
        let request = close_request(GENERATION_A, "10000000-0000-4000-8000-000000000001");
        let reply = close_reply(&request, GENERATION_A);
        validate_bridge_reply_for_request(&request, &reply).unwrap();
    }

    #[test]
    fn bridge_restart_rejects_stale_generation_and_accepts_fresh_lineage() {
        let retired_request = close_request(GENERATION_A, "10000000-0000-4000-8000-000000000001");
        let retired_reply = close_reply(&retired_request, GENERATION_A);
        validate_bridge_reply_for_request(&retired_request, &retired_reply).unwrap();

        let restarted_request = close_request(GENERATION_B, "10000000-0000-4000-8000-000000000002");
        assert!(
            validate_bridge_reply_for_request(&restarted_request, &retired_reply)
                .unwrap_err()
                .contains("generation mismatch")
        );
        let restarted_reply = close_reply(&restarted_request, GENERATION_B);
        validate_bridge_reply_for_request(&restarted_request, &restarted_reply).unwrap();
    }

    #[test]
    fn bridge_reply_gate_rejects_wrong_operation_and_digest() {
        let request = close_request(GENERATION_A, "10000000-0000-4000-8000-000000000001");
        let reply = close_reply(&request, GENERATION_A);
        let mut wrong_operation: serde_json::Value = serde_json::from_slice(&reply).unwrap();
        wrong_operation["receipt"]["operation_id"] =
            serde_json::Value::String("10000000-0000-4000-8000-000000000099".into());
        assert!(validate_bridge_reply_for_request(
            &request,
            &serde_json::to_vec(&wrong_operation).unwrap()
        )
        .unwrap_err()
        .contains("operation_id"));

        let mut wrong_digest: serde_json::Value = serde_json::from_slice(&reply).unwrap();
        wrong_digest["receipt"]["request_digest"] = serde_json::Value::String("d".repeat(64));
        assert!(validate_bridge_reply_for_request(
            &request,
            &serde_json::to_vec(&wrong_digest).unwrap()
        )
        .unwrap_err()
        .contains("request_digest"));
    }

    #[test]
    fn bridge_reply_gate_allows_only_receiptless_uncorrelated_error() {
        let request = close_request(GENERATION_A, "10000000-0000-4000-8000-000000000001");
        let error = ncp_core::rpc_error_payload(
            ncp_core::RpcErrorCode::ContainedInternalFailure,
            "backend outcome unavailable after restart",
            None,
            Some("close_session".into()),
        );
        validate_bridge_reply_for_request(&request, &error).unwrap();
    }

    #[test]
    fn bridge_open_reply_must_preserve_precommitted_security_pair() {
        let (request, mut reply) = open_pair();
        reply["security_state_digest"] = serde_json::Value::String("d".repeat(64));
        let error = validate_bridge_reply_for_request(
            &serde_json::to_vec(&request).unwrap(),
            &serde_json::to_vec(&reply).unwrap(),
        )
        .unwrap_err();
        assert!(error.contains("security_state_digest"), "{error}");
    }

    #[test]
    fn fresh_gateway_requires_observed_open_and_never_revives_generation() {
        let mut state = GatewayRestartState::default();
        let close = serde_json::from_slice::<serde_json::Value>(&close_request(
            GENERATION_A,
            "10000000-0000-4000-8000-000000000001",
        ))
        .unwrap();
        assert!(state
            .begin_request(&close)
            .unwrap_err()
            .contains("fresh successful open"));

        let (request, reply) = open_pair();
        let open = state.begin_request(&request).unwrap();
        state.accept_reply(&open, &reply).unwrap();
        assert!(state.begin_request(&close).is_ok());

        let reopened = state.begin_request(&request).unwrap();
        assert!(state
            .accept_reply(&reopened, &reply)
            .unwrap_err()
            .contains("revives a retired generation"));
    }

    #[test]
    fn failed_open_reply_leaves_gateway_closed_without_becoming_internal_failure() {
        let mut state = GatewayRestartState::default();
        let (request, mut reply) = open_pair();
        reply["ok"] = serde_json::Value::Bool(false);
        reply["state_version"] = serde_json::Value::from(0);
        reply["session"] = serde_json::Value::Null;
        reply["provenance"] = serde_json::Value::Null;
        reply["error"] = serde_json::Value::String("backend unavailable".into());
        ncp_core::validate(&reply).unwrap();

        let open = state.begin_request(&request).unwrap();
        state.accept_reply(&open, &reply).unwrap();

        let close = serde_json::from_slice::<serde_json::Value>(&close_request(
            GENERATION_A,
            "10000000-0000-4000-8000-000000000001",
        ))
        .unwrap();
        assert!(state
            .begin_request(&close)
            .unwrap_err()
            .contains("fresh successful open"));
    }

    #[test]
    fn gateway_restart_fence_rejects_non_lifecycle_kinds() {
        let mut state = GatewayRestartState::default();
        let request = serde_json::json!({
            "kind": "sensor_frame",
            "session_id": "s",
        });
        assert!(state
            .begin_request(&request)
            .unwrap_err()
            .contains("does not accept lifecycle request kind"));
    }

    #[test]
    fn gateway_generation_fence_fails_closed_at_capacity() {
        let mut state = GatewayRestartState::default();
        for index in 0..MAX_GATEWAY_LINEAGES {
            state
                .seen_generations
                .insert((format!("retired-{index}"), format!("generation-{index}")));
        }
        let (request, reply) = open_pair();
        let open = state.begin_request(&request).unwrap();
        assert!(state
            .accept_reply(&open, &reply)
            .unwrap_err()
            .contains("capacity"));
        assert!(!state.live.contains_key("s"));
    }

    #[test]
    fn gateway_opening_fence_fails_closed_at_capacity() {
        let mut state = GatewayRestartState::default();
        for index in 0..MAX_GATEWAY_LINEAGES {
            state.openings.insert(format!("opening-{index}"), 1);
        }
        let (request, _) = open_pair();
        assert!(state
            .begin_request(&request)
            .unwrap_err()
            .contains("opening fence"));
    }

    #[test]
    fn completed_failed_open_releases_its_opening_capacity() {
        let mut state = GatewayRestartState::default();
        let (request, _) = open_pair();
        let fence = state.begin_request(&request).unwrap();
        assert_eq!(state.openings.len(), 1);

        state.finish_request(&fence);

        assert!(state.openings.is_empty());
        assert!(state.begin_request(&request).is_ok());
    }

    #[test]
    fn completing_superseded_open_does_not_remove_newer_attempt() {
        let mut state = GatewayRestartState::default();
        let (request, reply) = open_pair();
        let older = state.begin_request(&request).unwrap();
        let newer = state.begin_request(&request).unwrap();

        state.finish_request(&older);

        assert_eq!(state.openings.get("s"), Some(&2));
        state.accept_reply(&newer, &reply).unwrap();
        assert!(!state.openings.contains_key("s"));
    }

    #[test]
    fn gateway_observation_fence_fails_closed_at_capacity() {
        let mut state = GatewayRestartState::default();
        let (request, reply) = open_pair();
        let open = state.begin_request(&request).unwrap();
        state.accept_reply(&open, &reply).unwrap();
        state.live.get_mut("s").unwrap().observation = Some(GatewayObservationFence {
            epoch: "3ef6f0ad-8ee6-4c6a-9e3f-86dc9ce849a1".into(),
            high_water: MAX_GATEWAY_OBSERVATION_POSITIONS as i64,
            reply_fingerprints: (1..=MAX_GATEWAY_OBSERVATION_POSITIONS)
                .map(|seq| (seq as i64, format!("fingerprint-{seq}")))
                .collect(),
        });
        state.observation_positions = MAX_GATEWAY_OBSERVATION_POSITIONS;
        let step = serde_json::json!({
            "kind": "step_request",
            "session_id": "s",
            "session": {"generation": GENERATION_A}
        });
        let fence = state.begin_request(&step).unwrap();
        let observation = serde_json::json!({
            "kind": "observation_frame",
            "stream": {
                "epoch": "3ef6f0ad-8ee6-4c6a-9e3f-86dc9ce849a1",
                "seq": MAX_GATEWAY_OBSERVATION_POSITIONS + 1
            },
            "receipt": {"result_digest": "a".repeat(64)}
        });
        assert!(state
            .accept_reply(&fence, &observation)
            .unwrap_err()
            .contains("capacity"));
    }

    #[test]
    fn gateway_observation_fence_allows_only_full_reply_identical_terminal_replay() {
        let mut state = GatewayRestartState::default();
        let (request, reply) = open_pair();
        let open = state.begin_request(&request).unwrap();
        state.accept_reply(&open, &reply).unwrap();
        let step = serde_json::json!({
            "kind": "step_request",
            "session_id": "s",
            "session": {"generation": GENERATION_A}
        });
        let fence = state.begin_request(&step).unwrap();
        let observation = serde_json::json!({
            "kind": "observation_frame",
            "stream": {"epoch": "3ef6f0ad-8ee6-4c6a-9e3f-86dc9ce849a1", "seq": 1},
            "receipt": {
                "operation_id": "10000000-0000-4000-8000-000000000001",
                "request_digest": "a".repeat(64),
                "result_digest": "b".repeat(64)
            }
        });
        state.accept_reply(&fence, &observation).unwrap();
        state.accept_reply(&fence, &observation).unwrap();

        let mut different_body = observation.clone();
        different_body["sim_time_ms"] = serde_json::Value::from(1.0);
        assert!(state
            .accept_reply(&fence, &different_body)
            .unwrap_err()
            .contains("replayed"));

        let mut different_operation = observation.clone();
        different_operation["receipt"]["operation_id"] =
            serde_json::Value::String("10000000-0000-4000-8000-000000000099".into());
        assert!(state
            .accept_reply(&fence, &different_operation)
            .unwrap_err()
            .contains("replayed"));

        let mut different_receipt = observation.clone();
        different_receipt["receipt"]["state_version"] = serde_json::Value::from(2);
        assert!(state
            .accept_reply(&fence, &different_receipt)
            .unwrap_err()
            .contains("replayed"));

        let mut gap = observation.clone();
        gap["stream"]["seq"] = serde_json::Value::from(3);
        gap["receipt"]["operation_id"] =
            serde_json::Value::String("10000000-0000-4000-8000-000000000088".into());
        state.accept_reply(&fence, &gap).unwrap();

        let mut reordered = observation.clone();
        reordered["stream"]["seq"] = serde_json::Value::from(2);
        reordered["receipt"]["operation_id"] =
            serde_json::Value::String("10000000-0000-4000-8000-000000000077".into());
        assert!(state
            .accept_reply(&fence, &reordered)
            .unwrap_err()
            .contains("non-increasing"));

        let mut foreign_epoch = observation;
        foreign_epoch["stream"]["epoch"] =
            serde_json::Value::String("4ef6f0ad-8ee6-4c6a-9e3f-86dc9ce849a1".into());
        foreign_epoch["stream"]["seq"] = serde_json::Value::from(2);
        assert!(state
            .accept_reply(&fence, &foreign_epoch)
            .unwrap_err()
            .contains("changed epoch"));
    }
}
