//! Cross-session NCP RPC over a REAL Zenoh tcp link.
//!
//! `loopback.rs` proves `ncp-zenoh` runs by delivering a session's own publications
//! to its own subscribers (one in-process session). This goes further: two
//! INDEPENDENT `ZenohBus` sessions — one **listens** on a localhost tcp endpoint, the
//! other **connects** to it — so every request/reply crosses Zenoh's actual transport
//! between sessions (the path a two-process deployment uses, with multicast discovery
//! off). It drives the full control-plane lifecycle (open → step → run → close)
//! through the typed `ZenohNcpClient` (which performs the version + advisory-contract
//! handshake on the reply) against a NEST-free `serve_rpc` handler, asserting the wire
//! contract — handshake, the scientific-boundary discriminators, the lifecycle, the
//! recorded port — survives the production medium end to end.

use ncp_core::keys::Keys;
use ncp_core::{
    AuthorityLease, CloseSession, IdentityClaim, NetworkRef, NetworkRefKind, OpenSession,
    OperationContext, Plane as NcpPlane, PrincipalRole, RunRequest, SessionRef, StepRequest,
    CONTRACT_HASH, NCP_VERSION,
};
use ncp_zenoh::{ZenohBus, ZenohConfig, ZenohNcpClient};
use serde::de::DeserializeOwned;
use serde::Serialize;
use serde_json::{json, Value};
use std::time::Duration;

const GENERATION: &str = "293279f3-d459-4bfd-aeeb-604799e96925";
const SECURITY_DIGEST: &str = "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab";

fn session() -> SessionRef {
    SessionRef {
        generation: GENERATION.into(),
    }
}

fn commander_identity() -> IdentityClaim {
    IdentityClaim {
        principal_id: "controller-principal-1".into(),
        entity_id: "controller-1".into(),
        role: PrincipalRole::Commander,
        plane: NcpPlane::Control,
    }
}

fn authority() -> AuthorityLease {
    AuthorityLease {
        session_epoch: GENERATION.into(),
        term: 1,
        lease_id: "20000000-0000-4000-8000-000000000001".into(),
        issuer_principal_id: "controller-principal-1".into(),
        holder_principal_id: "controller-principal-1".into(),
        holder_entity_id: "controller-1".into(),
        issued_at_utc_ms: 1_700_000_000_000,
        expires_at_utc_ms: 1_700_000_060_000,
    }
}

fn operation(id: &str, expected_state_version: u64) -> OperationContext {
    OperationContext {
        operation_id: id.into(),
        request_digest: String::new(),
        session_epoch: GENERATION.into(),
        expected_state_version,
        deadline_utc_ms: 1_700_000_030_000,
        retry: false,
    }
}

fn seal<T>(request: T) -> T
where
    T: Serialize + DeserializeOwned,
{
    let mut value = serde_json::to_value(request).expect("serialize mutation request");
    let digest = ncp_core::request_digest(&value).expect("compute request-digest-v1");
    value["operation"]["request_digest"] = Value::String(digest);
    serde_json::from_value(value).expect("deserialize sealed mutation request")
}

fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

fn base_cfg() -> ZenohConfig {
    let mut c = ZenohConfig::default();
    c.insert_json5("scouting/multicast/enabled", "false")
        .unwrap();
    c.insert_json5("scouting/gossip/enabled", "false").unwrap();
    c.insert_json5("transport/shared_memory/enabled", "false")
        .unwrap();
    c
}

fn listen_cfg(port: u16) -> ZenohConfig {
    let mut c = base_cfg();
    c.insert_json5("listen/endpoints", &format!("[\"tcp/127.0.0.1:{port}\"]"))
        .unwrap();
    c
}

fn connect_cfg(port: u16) -> ZenohConfig {
    let mut c = base_cfg();
    c.insert_json5("connect/endpoints", &format!("[\"tcp/127.0.0.1:{port}\"]"))
        .unwrap();
    c
}

/// A NEST-free mock NCP server: maps each control-plane request to its reply, with
/// the mandatory scientific-boundary discriminators set. A real backend would advance
/// a kernel here; the wire contract is identical either way (that is the point — the
/// transport carries the contract regardless of the simulator behind it).
fn mock_handler(req: Vec<u8>) -> Vec<u8> {
    let v: Value = serde_json::from_slice(&req).unwrap_or_else(|_| json!({}));
    let sid = v.get("session_id").and_then(Value::as_str).unwrap_or("s");
    let kind = v.get("kind").and_then(Value::as_str).unwrap_or("");
    let receipt = || {
        let operation = &v["operation"];
        json!({
            "operation_id": operation["operation_id"],
            "request_digest": operation["request_digest"],
            "result_digest": "82bfecaa6d47a3ec4cc56b948f511e641d186d19545b9a0c697b825ecaff5241",
            "outcome": "succeeded",
            "state_version": operation["expected_state_version"].as_u64().unwrap_or(0) + 1,
            "committed_at_utc_ms": 1_700_000_001_000_i64,
            "responder_principal_id": "body-principal-1",
            "responder_entity_id": "simulator-1"
        })
    };
    let reply = match kind {
        "open_session" => json!({
            "kind": "session_opened", "ncp_version": NCP_VERSION, "session_id": sid, "ok": true,
            "state_version": 1,
            "backend": "mock", "contract_hash": CONTRACT_HASH,
            "provenance": {"network_ref": "x", "backend": "mock", "calibrated_posterior": false,
                           "is_simulation_output": true, "advisory_only": true},
            "session": {"generation": GENERATION},
            "identity": {"principal_id": "body-principal-1", "entity_id": "simulator-1",
                         "role": "body", "plane": "control"},
            "security_profile": "dev-loopback-insecure",
            "security_state_digest": SECURITY_DIGEST,
            "gateway_permitted": false,
        }),
        "step_request" | "run_request" => json!({
            "kind": "observation_frame", "ncp_version": NCP_VERSION, "session_id": sid,
            // Wire 0.8: an RPC-reply observation carries its OWN stream position
            // (seq >= 1) and the live session; the pull/RPC-reply form is
            // distinguished by `source` ABSENCE, not by a seq-0 sentinel.
            "stream": {"epoch": "3ef6f0ad-8ee6-4c6a-9e3f-86dc9ce849a1", "seq": 1},
            "session": {"generation": GENERATION},
            "calibrated_posterior": false, "is_simulation_output": true,
            "records": {"vm": {"port": "vm", "target": "pop", "observable": "V_m",
                               "times": [1.0], "values": [-65.0], "unit": "mV"}},
            "receipt": receipt(),
        }),
        "close_session" => json!({
            "kind": "session_closed", "ncp_version": NCP_VERSION, "session_id": sid, "ok": true,
            "session": {"generation": GENERATION},
            "receipt": receipt(),
        }),
        other => {
            json!({"kind": "error", "ncp_version": NCP_VERSION,
                   "code": "NCP-WIRE-001", "request_kind": other,
                   "error": format!("unknown kind {other}")})
        }
    };
    serde_json::to_vec(&reply).unwrap()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn ncp_rpc_over_real_zenoh_tcp_link() {
    let port = free_port();

    // Server session LISTENS on a localhost tcp endpoint and serves the RPC queryable.
    let server = ZenohBus::with_config(listen_cfg(port), Keys::default())
        .await
        .expect("open server session (listen)");
    let _rpc_task = server.serve_rpc(mock_handler).await.expect("serve_rpc");

    // Client session CONNECTS to it — a separate session, real tcp transport between them.
    let client_bus = ZenohBus::with_config(connect_cfg(port), Keys::default())
        .await
        .expect("open client session (connect)");
    let client = ZenohNcpClient::new(client_bus);
    let open_msg = OpenSession {
        session_id: "uav1".into(),
        network: NetworkRef {
            kind: NetworkRefKind::Builtin,
            ref_: "iaf_psc_alpha".into(),
            ..Default::default()
        },
        identity: commander_identity(),
        security_profile: "dev-loopback-insecure".into(),
        security_state_digest: SECURITY_DIGEST.into(),
        gateway_permitted: false,
        ..Default::default()
    };

    // Readiness POLL instead of a blind sleep (robust on a slow CI runner): retry the
    // first RPC until the queryable is reachable across the link. `request()` returns
    // Err immediately when no peer has answered yet (no internal timeout), so each
    // attempt is cheap; fail loudly after a hard deadline rather than hang.
    let mut opened = None;
    for _ in 0..100 {
        match client.open(&open_msg).await {
            Ok(o) => {
                opened = Some(o);
                break;
            }
            Err(_) => tokio::time::sleep(Duration::from_millis(100)).await,
        }
    }
    let opened =
        opened.expect("queryable never became reachable over the zenoh tcp link within ~10s");
    assert!(opened.ok, "session must open");
    let prov = opened
        .provenance
        .expect("session_opened carries provenance");
    assert!(
        prov.is_simulation_output && !prov.calibrated_posterior,
        "scientific boundary must hold over the wire"
    );

    // step — observation_frame with the boundary discriminators + the recorded port.
    let obs = client
        .step(&seal(StepRequest {
            session_id: "uav1".into(),
            advance_ms: Some(10.0),
            session: session(),
            operation: operation("10000000-0000-4000-8000-000000000001", 1),
            authority: authority(),
            ..Default::default()
        }))
        .await
        .expect("step over zenoh");
    assert!(
        obs.is_simulation_output && !obs.calibrated_posterior,
        "observation_frame boundary must hold"
    );
    assert!(
        obs.records.contains_key("vm"),
        "the recorded port must come back across the link"
    );

    // run — batch advance.
    let run = client
        .run(&seal(RunRequest {
            session_id: "uav1".into(),
            duration_ms: 50.0,
            session: session(),
            operation: operation("10000000-0000-4000-8000-000000000002", 2),
            authority: authority(),
            ..Default::default()
        }))
        .await
        .expect("run over zenoh");
    assert!(run.is_simulation_output, "run observation_frame boundary");

    // close.
    let closed = client
        .close(&seal(CloseSession {
            session_id: "uav1".into(),
            session: session(),
            operation: operation("10000000-0000-4000-8000-000000000003", 3),
            authority: authority(),
            ..Default::default()
        }))
        .await
        .expect("close over zenoh");
    assert!(closed.ok, "session must close");
}

/// A server on an OLDER wire: a valid reply except its `ncp_version` is a stale
/// wire ("0.4"). This is the cutover hazard — a leftover old peer on the bus.
fn stale_version_handler(req: Vec<u8>) -> Vec<u8> {
    let v: Value = serde_json::from_slice(&req).unwrap_or_else(|_| json!({}));
    let sid = v.get("session_id").and_then(Value::as_str).unwrap_or("s");
    let reply = json!({
        "kind": "session_opened", "ncp_version": "0.4", "session_id": sid, "ok": true,
        "backend": "mock", "contract_hash": CONTRACT_HASH,
        "provenance": {"network_ref": "x", "backend": "mock", "calibrated_posterior": false,
                       "is_simulation_output": true, "advisory_only": true},
        "state_version": 1,
        "session": {"generation": GENERATION},
        "identity": {"principal_id": "body-principal-1", "entity_id": "simulator-1",
                     "role": "body", "plane": "control"},
        "security_profile": "dev-loopback-insecure",
        "security_state_digest": SECURITY_DIGEST,
        "gateway_permitted": false,
    });
    serde_json::to_vec(&reply).unwrap()
}

/// SHOULD-FIX #4b (Rust side): the HARD version gate fires across the real transport.
/// A stale-wire `session_opened` reply must be REJECTED by a current-wire client (the
/// handshake `negotiate`s the reply's version) — never coerced — so a half-upgraded
/// fleet fails closed instead of two wire revisions silently mis-decoding each other.
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn mixed_version_open_is_rejected_over_the_wire() {
    let port = free_port();
    let server = ZenohBus::with_config(listen_cfg(port), Keys::default())
        .await
        .expect("open server session (listen)");
    let _rpc_task = server
        .serve_rpc(stale_version_handler)
        .await
        .expect("serve_rpc");

    let client_bus = ZenohBus::with_config(connect_cfg(port), Keys::default())
        .await
        .expect("open client session (connect)");
    let client = ZenohNcpClient::new(client_bus);
    let open_msg = OpenSession {
        session_id: "uav1".into(),
        network: NetworkRef {
            kind: NetworkRefKind::Builtin,
            ref_: "iaf_psc_alpha".into(),
            ..Default::default()
        },
        identity: commander_identity(),
        security_profile: "dev-loopback-insecure".into(),
        security_state_digest: SECURITY_DIGEST.into(),
        gateway_permitted: false,
        ..Default::default()
    };

    // open() is always Err here: before the queryable is reachable it is a "no reply"
    // error; once reachable it is the VERSION-gate error. Poll until we see the gate
    // (error text mentions "version"), so the test asserts the rejection, not the
    // not-yet-ready transient — and never coerces a 0.4 reply into an Ok.
    let mut rejected = false;
    for _ in 0..100 {
        match client.open(&open_msg).await {
            Ok(_) => panic!("a stale-wire session_opened must be rejected, not accepted"),
            Err(e) => {
                if e.to_string().contains("version") {
                    rejected = true;
                    break;
                }
                tokio::time::sleep(Duration::from_millis(100)).await;
            }
        }
    }
    assert!(
        rejected,
        "the hard version gate must reject a 0.4 session_opened over the wire within ~10s"
    );
}
