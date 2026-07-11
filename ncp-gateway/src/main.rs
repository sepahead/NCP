#![doc = include_str!("../README.md")]
//!
//! # Configuration and security
//!
//! Config via env:
//!   NCP_REALM        key-expression realm           (default `ncp`; set per deployment)
//!   NCP_BRIDGE_ADDR  Python bridge_server.py addr    (default `127.0.0.1:28474`)
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
use std::io::{BufRead, BufReader, Write};
use std::net::TcpStream;
use std::time::Duration;

const DEFAULT_BRIDGE_ADDR: &str = "127.0.0.1:28474";

/// Forward one NCP request (JSON bytes) to the Python bridge and return the reply
/// (JSON bytes). Newline-delimited JSON, one request → one reply. Blocking — the
/// control-plane RPC is rare (session lifecycle), never the per-tick hot path.
fn forward_to_python(addr: &str, request: &[u8]) -> std::io::Result<Vec<u8>> {
    let stream = TcpStream::connect(addr)?;
    stream.set_read_timeout(Some(Duration::from_secs(30)))?;
    stream.set_write_timeout(Some(Duration::from_secs(30)))?;
    let mut writer = stream.try_clone()?;
    writer.write_all(request)?;
    writer.write_all(b"\n")?;
    writer.flush()?;
    let mut reader = BufReader::new(stream);
    let mut line = Vec::new();
    reader.read_until(b'\n', &mut line)?;
    while line.last() == Some(&b'\n') || line.last() == Some(&b'\r') {
        line.pop();
    }
    Ok(line)
}

fn error_frame(message: &str, request: &[u8]) -> Vec<u8> {
    let request = serde_json::from_slice::<serde_json::Value>(request).ok();
    let session_id = request
        .as_ref()
        .and_then(|value| value.get("session_id"))
        .and_then(|value| value.as_str())
        .filter(|session_id| ncp_core::valid_id_segment(session_id))
        .map(str::to_owned);
    let request_kind = request
        .as_ref()
        .and_then(ncp_core::message_kind)
        .map(str::to_owned);
    ncp_core::rpc_error_payload(message, session_id, request_kind)
}

#[tokio::main]
async fn main() {
    let realm = std::env::var("NCP_REALM").unwrap_or_else(|_| ncp_core::DEFAULT_REALM.to_string());
    let bridge_addr =
        std::env::var("NCP_BRIDGE_ADDR").unwrap_or_else(|_| DEFAULT_BRIDGE_ADDR.to_string());

    // Honor NCP_ZENOH_CONFIG explicitly: when set, load the strict client config
    // file (fail-closed — a missing/malformed file aborts startup). When unset, fall
    // back to the hardened default (multicast scouting off). The realm is addressing,
    // not a credential — enforcement comes from this config, not the realm string.
    let keys = match Keys::try_new(realm.clone()) {
        Ok(keys) => keys,
        Err(error) => {
            eprintln!("[ncp-gateway] refusing invalid NCP_REALM: {error}");
            std::process::exit(1);
        }
    };
    let open = match std::env::var_os(NCP_ZENOH_CONFIG_ENV) {
        Some(path) => {
            println!("[ncp-gateway] loading Zenoh config from {NCP_ZENOH_CONFIG_ENV}={path:?}");
            ZenohBus::open_secure(keys).await
        }
        None => {
            eprintln!(
                "[ncp-gateway] {NCP_ZENOH_CONFIG_ENV} unset: opening hardened default \
                 (multicast scouting OFF, no ACL/TLS). The realm is addressing, not a \
                 credential — run the secure router separately and set \
                 {NCP_ZENOH_CONFIG_ENV} to a configured copy of \
                 deploy/zenoh-client-secure.json5. See SECURITY.md."
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

    let addr = bridge_addr.clone();
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
                return error_frame(&format!("invalid NCP request: {error}"), &req);
            }
            tokio::task::block_in_place(|| match forward_to_python(&addr, &req) {
                Ok(reply) if !reply.is_empty() => reply,
                Ok(_) => error_frame("empty reply from Python bridge", &req),
                Err(e) => error_frame(&format!("bridge unreachable at {addr}: {e}"), &req),
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
        "[ncp-gateway] serving NCP RPC on Zenoh keys '{realm}/rpc/*' → Python bridge {bridge_addr}"
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
