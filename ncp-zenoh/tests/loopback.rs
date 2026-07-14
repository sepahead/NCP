//! Real-runtime integration test: a closed control loop over an actual Zenoh
//! session (loopback within one process — Zenoh delivers a session's own
//! publications to its own subscribers). Proves `ncp-zenoh` actually *runs*
//! (pub/sub + the `ZenohControlTransport` streaming control plane), not just
//! compiles. Cross-host routing is a Zenoh property, exercised in deployment.

use ncp_core::keys::Keys;
use ncp_core::ControlTransport;
use ncp_core::{
    AuthorityLease, ChannelValue, CommandFrame, Map, NeuroControlLoop, ReflexController,
    SafetyLimits, SensorFrame,
};
use ncp_zenoh::{ZenohBus, ZenohConfig, ZenohControlTransport};
use std::sync::{Arc, Mutex};
use std::time::Duration;

fn loopback_cfg() -> ZenohConfig {
    let mut c = ZenohConfig::default();
    // No external discovery needed: one in-process session, local delivery.
    c.insert_json5("scouting/multicast/enabled", "false")
        .unwrap();
    c.insert_json5("scouting/gossip/enabled", "false").unwrap();
    c.insert_json5("transport/shared_memory/enabled", "false")
        .unwrap();
    c
}

fn authority() -> AuthorityLease {
    AuthorityLease {
        session_epoch: "00000000-0000-4000-8000-0000000000a2".into(),
        term: 1,
        lease_id: "20000000-0000-4000-8000-000000000001".into(),
        issuer_principal_id: "controller-principal-1".into(),
        holder_principal_id: "controller-principal-1".into(),
        holder_entity_id: "controller-1".into(),
        issued_at_utc_ms: 1_700_000_000_000,
        expires_at_utc_ms: 1_700_000_060_000,
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn zenoh_closed_loop_roundtrip() {
    let bus = ZenohBus::with_config(loopback_cfg(), Keys::default())
        .await
        .unwrap();
    let live_session = ncp_core::SessionRef {
        generation: "00000000-0000-4000-8000-0000000000a2".into(),
    };

    // The "plant" subscribes to the action plane.
    let last_cmd: Arc<Mutex<Option<CommandFrame>>> = Arc::new(Mutex::new(None));
    let sink = last_cmd.clone();
    bus.subscribe_commands("uav1", &live_session, move |_k, bytes| {
        if let Ok(c) = serde_json::from_slice::<CommandFrame>(&bytes) {
            *sink.lock().unwrap() = Some(c);
        }
    })
    .await
    .unwrap();

    // Controller: ZenohControlTransport (subscribe sensor / publish command) + a
    // reflex loop. Fixed clock so the safety governor sees the sensor as fresh.
    let transport = ZenohControlTransport::new(bus.clone(), "uav1", live_session.clone())
        .await
        .unwrap();
    let mut control = NeuroControlLoop::new(
        transport,
        ReflexController::default(),
        20.0,
        SafetyLimits {
            max_speed_mps: Some(1.5),
            command_timeout_ms: 5000.0,
            ..Default::default()
        },
        "uav1",
        live_session.clone(),
    )
    .expect("loopback session binding is canonical")
    .with_authority(authority())
    .with_clock(Box::new(|| 0.0));
    // Let the subscription declarations settle.
    tokio::time::sleep(Duration::from_millis(300)).await;

    // The plant streams a sensor frame (+1 m x position error) and the controller
    // ticks; both planes use DROP QoS, so we run the loop until the round trip
    // converges rather than relying on a single sample landing. Each attempt is a
    // fresh sensor sample with a strictly increasing stream position; replaying
    // one position as a transport retry is intentionally rejected.
    let mut channels = Map::new();
    channels.insert(
        "pose_position".into(),
        ChannelValue::vec3(1.0, 0.0, 0.0, Some("m")),
    );
    channels.insert(
        "pose_velocity".into(),
        ChannelValue::vec3(0.0, 0.0, 0.0, Some("m/s")),
    );
    let mut sensor = SensorFrame {
        stream: ncp_core::StreamPosition {
            epoch: "00000000-0000-4000-8000-000000000001".into(),
            seq: 7,
        },
        session: live_session.clone(),
        session_id: "uav1".into(),
        t: 0.0,
        channels,
        ..Default::default()
    };
    let mut received: Option<CommandFrame> = None;
    let start = std::time::Instant::now();
    while start.elapsed() < Duration::from_secs(10) {
        let bytes = serde_json::to_vec(&sensor).unwrap();
        bus.put_sensor("uav1", &live_session, &bytes).await.unwrap();
        sensor.stream.seq += 1;
        tokio::time::sleep(Duration::from_millis(100)).await;
        if control.transport.latest_sensor().is_some() {
            control.tick(); // publishes a CommandFrame on the action plane
        }
        if let Some(c) = last_cmd.lock().unwrap().clone() {
            received = Some(c);
            break;
        }
    }

    assert!(
        control.transport.latest_sensor().is_some(),
        "controller never received the sensor frame over Zenoh"
    );
    let received = received.expect("plant never received a command over Zenoh");
    let vx = received.channels["velocity_setpoint"].data[0];
    // ReflexController pushes back toward the origin: negative x velocity.
    assert!(
        vx < 0.0,
        "command should drive back toward origin, got vx={vx}"
    );

    let _ = bus.close().await;
}
