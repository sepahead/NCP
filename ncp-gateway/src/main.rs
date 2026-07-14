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
use std::time::Duration;

const DEFAULT_BRIDGE_ADDR: &str = "127.0.0.1:28474";

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
    let serve = bus
        .serve_rpc(move |req: Vec<u8>| {
            // forward_to_python is blocking std::net I/O (30s timeouts). block_in_place
            // frees this tokio worker so other tasks on the shared multi-thread runtime
            // (data planes, Zenoh internals) aren't starved while the bridge round-trip
            // is in flight. Valid here: ncp-gateway runs on the multi-thread runtime.
            let parsed = serde_json::from_slice::<serde_json::Value>(&req);
            if let Err(error) = parsed
                .as_ref()
                .map_err(|error| error.to_string())
                .and_then(|value| ncp_core::validate(value).map_err(|error| error.to_string()))
            {
                return error_frame(
                    ncp_core::RpcErrorCode::InvalidMessage,
                    &format!("invalid NCP request: {error}"),
                    &req,
                );
            }
            tokio::task::block_in_place(|| match forward_to_python(endpoint, &req) {
                Ok(reply) if !reply.is_empty() => reply,
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
}
