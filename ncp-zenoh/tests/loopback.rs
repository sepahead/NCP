//! Reference-runtime integration test: a bounded feedback cycle over an actual
//! Zenoh session. The numerical plant publishes state, the controller emits an
//! exactly correlated command, and a reference plant profile validates its channel
//! shape before it changes the next sampled state. An independent read-only tap
//! observes the same sensor stream. This proves the in-process reference path runs.
//! It does not implement complete body admission, produce a durable disposition,
//! or qualify cross-host transport, a physical plant, Crebain, Prisoma, security,
//! stability, or latency.

use ncp_core::keys::Keys;
use ncp_core::plant::{PlantChannel, PlantClass, SafeAction};
use ncp_core::ControlTransport;
use ncp_core::{
    AuthorityLease, ChannelValue, CommandFrame, Map, Mode, NeuroControlLoop, PlantCommand,
    PlantProfile, ReflexController, SafeActionKind, SafetyLimits, SensorFrame, StreamPosition,
};
use ncp_zenoh::{ZenohBus, ZenohConfig, ZenohControlTransport};
use std::sync::{Arc, Mutex};
use std::time::Duration;

const SESSION_ID: &str = "uav1";
const COMMANDS: i64 = 12;
const STEP_SECONDS: f64 = 0.05;

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

fn reference_plant_profile() -> PlantProfile {
    let mut profile = PlantProfile {
        schema: "ncp.plant-profile.v1".into(),
        status: "reference-non-certifying".into(),
        profile_id: "zenoh-loopback-reference".into(),
        revision: 1,
        plant_class: PlantClass::Simulation,
        body_entity_id: "reference-body".into(),
        command_channels: vec![PlantChannel {
            name: "velocity_setpoint".into(),
            unit: "m/s".into(),
            arity: 3,
            min: -1.5,
            max: 1.5,
            actuator_semantics: "reference Cartesian velocity input".into(),
        }],
        hold_action: SafeAction {
            kind: SafeActionKind::Neutral,
            channel_values: Map::from([("velocity_setpoint".into(), vec![0.0; 3])]),
            hold_max_ms: None,
            body_local_executor: "reference-body".into(),
        },
        estop_action: SafeAction {
            kind: SafeActionKind::Shutdown,
            channel_values: Map::from([("velocity_setpoint".into(), vec![0.0; 3])]),
            hold_max_ms: None,
            body_local_executor: "reference-body".into(),
        },
        body_is_final_authority: true,
        protocol_estop_is_physical_certification: false,
        consumer_safety_case_required: true,
        profile_digest_sha256: String::new(),
    };
    profile.profile_digest_sha256 = profile.computed_digest().unwrap();
    profile.validate().unwrap();
    profile
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn zenoh_feedback_cycle_preserves_causality_and_reduces_error() {
    let bus = ZenohBus::with_config(loopback_cfg(), Keys::default())
        .await
        .unwrap();
    let live_session = ncp_core::SessionRef {
        generation: "00000000-0000-4000-8000-0000000000a2".into(),
    };

    // The reference plant subscribes to the action plane. A separate read-only
    // tap observes perception without influencing controller or plant state.
    let commands: Arc<Mutex<Vec<CommandFrame>>> = Arc::new(Mutex::new(Vec::new()));
    let command_sink = commands.clone();
    bus.subscribe_commands(SESSION_ID, &live_session, move |_k, bytes| {
        if let Ok(command) = ncp_core::decode_validated::<CommandFrame>(&bytes) {
            command_sink.lock().unwrap().push(command);
        }
    })
    .await
    .unwrap();
    let observed_sensors: Arc<Mutex<Vec<SensorFrame>>> = Arc::new(Mutex::new(Vec::new()));
    let observation_sink = observed_sensors.clone();
    bus.subscribe_sensors(SESSION_ID, &live_session, move |_k, bytes| {
        if let Ok(frame) = ncp_core::decode_validated::<SensorFrame>(&bytes) {
            observation_sink.lock().unwrap().push(frame);
        }
    })
    .await
    .unwrap();

    // Controller: ZenohControlTransport (subscribe sensor / publish command) + a
    // reflex loop. Ingress and control use the same process-wide monotonic clock.
    let transport = ZenohControlTransport::new(bus.clone(), SESSION_ID, live_session.clone())
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
        SESSION_ID,
        live_session.clone(),
    )
    .expect("loopback session binding is canonical")
    .with_authority(authority());
    // Let the subscription declarations settle.
    tokio::time::sleep(Duration::from_millis(300)).await;

    let sensor_epoch = "00000000-0000-4000-8000-000000000001";
    let plant_profile = reference_plant_profile();
    let initial_position = 1.0;
    let mut position = initial_position;
    let mut velocity = 0.0;
    let mut sampled_positions = Vec::with_capacity((COMMANDS + 1) as usize);
    let mut command_epoch: Option<String> = None;

    // Publish one initial sample, execute COMMANDS profile-valid commands, and
    // publish one final sample. Every command is therefore bracketed by an exact
    // source sample and a causally later observation of the resulting plant state.
    for sample_seq in 1..=COMMANDS + 1 {
        let source = StreamPosition {
            epoch: sensor_epoch.into(),
            seq: sample_seq,
        };
        sampled_positions.push(position);
        let mut channels = Map::new();
        channels.insert(
            "pose_position".into(),
            ChannelValue::vec3(position, 0.0, 0.0, Some("m")),
        );
        channels.insert(
            "pose_velocity".into(),
            ChannelValue::vec3(velocity, 0.0, 0.0, Some("m/s")),
        );
        let sensor = SensorFrame {
            stream: source.clone(),
            session: live_session.clone(),
            session_id: SESSION_ID.into(),
            t: (sample_seq - 1) as f64 * STEP_SECONDS,
            channels,
            ..Default::default()
        };
        let bytes = serde_json::to_vec(&sensor).unwrap();
        bus.put_sensor(SESSION_ID, &live_session, &bytes)
            .await
            .unwrap();

        tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                let controller_has_source = control
                    .transport
                    .latest_sensor()
                    .is_some_and(|frame| frame.stream == source);
                let observer_has_source = observed_sensors
                    .lock()
                    .unwrap()
                    .iter()
                    .any(|frame| frame.stream == source);
                if controller_has_source && observer_has_source {
                    break;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("controller and observer did not receive the exact sensor position");

        if sample_seq == COMMANDS + 1 {
            break;
        }

        let proposed_command = control
            .tick()
            .expect("reference command remains attributable and transport-slot admissible");
        assert_eq!(proposed_command.source.as_ref(), Some(&source));

        let received = tokio::time::timeout(Duration::from_secs(5), async {
            loop {
                if let Some(command) = commands
                    .lock()
                    .unwrap()
                    .iter()
                    .find(|command| command.source.as_ref() == Some(&source))
                    .cloned()
                {
                    break command;
                }
                tokio::time::sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .expect("plant did not receive the exactly correlated command");
        assert_eq!(received.session_id, SESSION_ID);
        assert_eq!(received.session, live_session);
        assert_eq!(received.source.as_ref(), Some(&source));
        assert_eq!(received.stream.seq, sample_seq);
        assert_eq!(
            received, proposed_command,
            "the plant must receive the exact transport-slot-admitted command"
        );
        match &command_epoch {
            Some(epoch) => assert_eq!(&received.stream.epoch, epoch),
            None => command_epoch = Some(received.stream.epoch.clone()),
        }

        // This is only the reference plant-shape check. Complete body admission
        // additionally needs authenticated ingress, current manifest/security
        // state, authority, executor capacity, stream state, and durable result
        // handling. This test provides none of those missing claims.
        assert_eq!(received.mode, Mode::Active);
        let velocity_setpoint = received
            .channels
            .get("velocity_setpoint")
            .expect("governed command omitted the required plant channel");
        assert_eq!(velocity_setpoint.unit.as_deref(), Some("m/s"));
        let admitted = PlantCommand {
            profile_digest_sha256: plant_profile.profile_digest_sha256.clone(),
            channels: Map::from([("velocity_setpoint".into(), velocity_setpoint.data.clone())]),
        };
        plant_profile
            .validate_active_command(&admitted)
            .expect("reference plant profile rejected the governed command shape");

        // This is an explicit reference numerical plant, not an NCP safety or
        // stability claim: x[k+1] = x[k] + dt * u[k]. The next sensor sample is
        // derived from the profile-valid state update, which makes feedback causal.
        velocity = admitted.channels["velocity_setpoint"][0];
        position += STEP_SECONDS * velocity;
    }

    assert!(
        position.abs() < initial_position.abs(),
        "feedback should reduce the reference position error: {initial_position} -> {position}"
    );
    assert!(
        sampled_positions
            .windows(2)
            .all(|pair| pair[1].abs() < pair[0].abs()),
        "each profile-valid command must reduce error in its causally later sample: {sampled_positions:?}"
    );
    assert_eq!(commands.lock().unwrap().len(), COMMANDS as usize);
    {
        let observations = observed_sensors.lock().unwrap();
        assert_eq!(observations.len(), (COMMANDS + 1) as usize);
        assert_eq!(
            observations.last().map(|frame| &frame.stream),
            Some(&StreamPosition {
                epoch: sensor_epoch.into(),
                seq: COMMANDS + 1,
            })
        );
    }

    let _ = bus.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn delivered_sensor_frames_are_counted_before_local_coalescing() {
    let bus = ZenohBus::with_config(loopback_cfg(), Keys::default())
        .await
        .unwrap();
    let session = ncp_core::SessionRef {
        generation: "00000000-0000-4000-8000-0000000000a2".into(),
    };
    let transport = ZenohControlTransport::new(bus.clone(), "uav1", session.clone())
        .await
        .unwrap();
    for seq in 1..=12 {
        let frame = SensorFrame {
            stream: ncp_core::StreamPosition {
                epoch: "00000000-0000-4000-8000-000000000001".into(),
                seq,
            },
            session: session.clone(),
            session_id: "uav1".into(),
            t: seq as f64 * 0.005,
            ..Default::default()
        };
        bus.put_sensor("uav1", &session, &serde_json::to_vec(&frame).unwrap())
            .await
            .unwrap();
        tokio::time::timeout(Duration::from_secs(2), async {
            while transport
                .latest_sensor()
                .is_none_or(|sample| sample.stream.seq != seq)
            {
                tokio::time::sleep(Duration::from_millis(1)).await;
            }
        })
        .await
        .expect("the declared frame must arrive before the next test publication");
    }
    let snapshot = transport.sensor_snapshot();
    assert_eq!(snapshot.counters.received, 12);
    assert_eq!(snapshot.counters.lost, 0);
    assert_eq!(snapshot.counters.coalesced, 11);
    assert!(!snapshot.counters.burst_observed);
    let received_at = snapshot.latest.unwrap().received_at_s;
    tokio::time::sleep(Duration::from_millis(5)).await;
    assert_eq!(
        transport.sensor_snapshot().latest.unwrap().received_at_s,
        received_at
    );
    let _ = bus.close().await;
}
