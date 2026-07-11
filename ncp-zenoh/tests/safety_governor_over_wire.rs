//! The **safety governor over a real Zenoh transport** (RELEASE_READINESS blocker #1).
//!
//! `cross_session_rpc.rs` proves the control-plane *lifecycle* crosses two
//! independent Zenoh sessions. This proves the **action plane's safety authority**
//! does too: that `SafetyGovernor::govern` — the HOLD / latched-ESTOP / speed-clamp
//! gate that is the only thing standing between a controller and an actuator —
//! produces the same verdict when its `CommandFrame` and `SensorFrame` travel over
//! the wire as it does in-process, and (the property a unit test cannot show) that
//! an **ESTOP latch survives the transport**: once a geofence breach trips it, a
//! subsequent perfectly-safe frame is *still* ESTOP across the link.
//!
//! Topology (two independent sessions over a real localhost tcp link, multicast
//! discovery off — the two-process deployment path):
//!   - the **plant** session LISTENs; it subscribes to the perception plane
//!     (`…/sensor`) and the action plane (`…/command`), runs the governor on each
//!     received command against its latest sensor, and publishes the *governed*
//!     command back on the reliable observation plane so the test can read it.
//!   - the **controller** session CONNECTs; it publishes sensors + commands and
//!     subscribes to the governed read-back.
//!
//! The governor's limits and clock are **plant-side deployment config** (a real
//! plant reads its own `SafetyLimits`, not the wire), so they are set in-process;
//! the `CommandFrame`, the `SensorFrame`, and the governed result all cross the
//! real Zenoh transport — which is exactly what this test exists to prove.
//!
//! Expectations are driven from `conformance/behavior/vectors.json` (the same
//! `govern` cases the in-process `behavior_conformance.rs` checks) so the wire test
//! and the language-neutral corpus cannot diverge. Each request is stamped with a
//! unique `seq` (which the governor preserves) so a straggler frame on the lossy
//! action/perception planes can never be mistaken for the current case's verdict.

use ncp_core::keys::Keys;
use ncp_core::{CommandFrame, Mode, SafetyGovernor, SafetyLimits, SensorFrame, WireFrame};
use ncp_zenoh::{ZenohBus, ZenohConfig};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::atomic::{AtomicI64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

const SID: &str = "uav-gov";
static SEQ: AtomicI64 = AtomicI64::new(1);

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

/// Load the `govern` cases from the crate-local snapshot of the shared corpus.
/// The package-surface gate byte-compares it with the canonical root fixture.
fn govern_cases() -> Vec<Value> {
    let path = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/testdata/conformance/behavior"
    ))
    .join("vectors.json");
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("read behavior corpus {}: {e}", path.display()));
    let corpus: Value =
        serde_json::from_str(&text).unwrap_or_else(|e| panic!("corpus is not valid JSON: {e}"));
    corpus["cases"]["govern"]
        .as_array()
        .expect("corpus has no `govern` cases")
        .clone()
}

/// L2 magnitude of the governed command's `velocity_setpoint` channel — identical
/// to `behavior_conformance.rs::velocity_magnitude` so the wire test scores the
/// corpus exactly as the in-process reference does.
fn velocity_magnitude(frame: &Value) -> f64 {
    frame["channels"]["velocity_setpoint"]["data"]
        .as_array()
        .map(|data| {
            data.iter()
                .filter_map(Value::as_f64)
                .map(|c| c * c)
                .sum::<f64>()
                .sqrt()
        })
        .unwrap_or(0.0)
}

/// The plant's governor + clock + latest sensor, shared between the Zenoh callbacks
/// and the test driver (one process hosts both sessions). The driver configures the
/// governor per case; the callbacks read it.
struct PlantState {
    gov: SafetyGovernor,
    now_s: f64,
    last_sensor_s: Option<f64>,
    latest_sensor: Option<SensorFrame>,
}

/// Stand up the plant: subscribe to the perception + action planes; on each command
/// run the governor against the latest sensor and publish the governed command on
/// the reliable observation plane for read-back.
async fn spawn_plant(server: &ZenohBus, state: Arc<Mutex<PlantState>>) {
    {
        let st = state.clone();
        server
            .subscribe_sensors(SID, move |_k, bytes| {
                if let Ok(sf) = serde_json::from_slice::<SensorFrame>(&bytes) {
                    st.lock().unwrap().latest_sensor = Some(sf);
                }
            })
            .await
            .expect("subscribe sensors");
    }
    let st = state.clone();
    let pub_bus = server.clone();
    let handle = tokio::runtime::Handle::current();
    server
        .subscribe_commands(SID, move |_k, bytes| {
            let Ok(command) = serde_json::from_slice::<CommandFrame>(&bytes) else {
                return;
            };
            // Govern under the lock (govern takes &mut self for the ESTOP latch),
            // then release before the async publish.
            let governed = {
                let mut s = st.lock().unwrap();
                let sensor = s.latest_sensor.clone();
                let now = s.now_s;
                let last = s.last_sensor_s;
                s.gov.govern(&command, sensor.as_ref(), now, last)
            };
            let Ok(out) = serde_json::to_vec(&governed) else {
                return;
            };
            let bus = pub_bus.clone();
            handle.spawn(async move {
                // Test-rig read-back of the governed COMMAND on the reliable
                // observation key: use the raw `put` escape hatch deliberately —
                // `publish_observation` (correctly) refuses non-observation kinds
                // under the wire-0.6 plane gates.
                let key = bus.keys().observation(SID);
                let _ = bus.put(&key, &out, ncp_zenoh::Plane::Control).await;
            });
        })
        .await
        .expect("subscribe commands");
}

/// Drive one governed exchange over the wire: stamp `command`/`sensor` with a fresh
/// `seq`, publish the sensor (perception plane) and wait until the plant has stored
/// *this* sensor, then publish the command (action plane) and return the governed
/// frame the plant emits with the matching `seq`. The `seq` match makes the test
/// immune to dropped/duplicated frames on the lossy planes.
async fn govern_over_wire(
    client: &ZenohBus,
    state: &Arc<Mutex<PlantState>>,
    sink: &Arc<Mutex<Vec<Value>>>,
    mut command: CommandFrame,
    mut sensor: SensorFrame,
) -> Value {
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    command.seq = seq;
    sensor.seq = seq;
    // The corpus carries complete envelopes. Only the per-exchange sequence is
    // replaced so read-back can be correlated without repairing any other field.
    let sbytes = serde_json::to_vec(&sensor).unwrap();
    let cbytes = serde_json::to_vec(&command).unwrap();

    // Publish the sensor until the plant has stored exactly this one (seq match):
    // guarantees the correct sensor is in place before the command is governed,
    // regardless of cross-key delivery ordering.
    let mut sensor_ready = false;
    for _ in 0..100 {
        client.put_sensor(SID, &sbytes).await.expect("put sensor");
        tokio::time::sleep(Duration::from_millis(50)).await;
        if state
            .lock()
            .unwrap()
            .latest_sensor
            .as_ref()
            .is_some_and(|s| s.seq == seq)
        {
            sensor_ready = true;
            break;
        }
    }
    assert!(
        sensor_ready,
        "sensor (seq {seq}) never crossed the perception plane within ~5s"
    );

    // Publish the command and wait for the governed read-back with the same seq.
    for _ in 0..100 {
        client
            .publish_command(SID, &cbytes)
            .await
            .expect("publish command");
        tokio::time::sleep(Duration::from_millis(50)).await;
        if let Some(v) = sink
            .lock()
            .unwrap()
            .iter()
            .rev()
            .find(|v| v["seq"].as_i64() == Some(seq))
            .cloned()
        {
            return v;
        }
    }
    panic!("governed command (seq {seq}) never came back over the wire within ~5s");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn safety_governor_decisions_survive_the_wire() {
    let port = free_port();

    let server = ZenohBus::with_config(listen_cfg(port), Keys::default())
        .await
        .expect("open plant session (listen)");
    let state = Arc::new(Mutex::new(PlantState {
        gov: SafetyGovernor::new(SafetyLimits::default()),
        now_s: 0.0,
        last_sensor_s: None,
        latest_sensor: None,
    }));
    spawn_plant(&server, state.clone()).await;

    let client = ZenohBus::with_config(connect_cfg(port), Keys::default())
        .await
        .expect("open controller session (connect)");
    let sink: Arc<Mutex<Vec<Value>>> = Arc::new(Mutex::new(Vec::new()));
    {
        let snk = sink.clone();
        // The test rig intentionally reflects a governed CommandFrame on the
        // observation key. Use the explicitly raw subscriber to match the raw
        // diagnostic `put` in `spawn_plant`; the NCP-aware observation helper
        // correctly rejects a non-ObservationFrame.
        client
            .subscribe(&client.keys().observation(SID), move |_k, bytes| {
                if let Ok(v) = serde_json::from_slice::<Value>(&bytes) {
                    snk.lock().unwrap().push(v);
                }
            })
            .await
            .expect("subscribe observations");
    }

    // ── 1. Valid corpus inputs preserve their verdict over Zenoh; hostile inputs
    // are rejected at the publisher gate before they can reach the plant. ──
    // Each executable case gets a FRESH governor (govern() latches ESTOP).
    let mut transported = 0usize;
    let mut rejected_at_ingress = 0usize;
    for case in govern_cases() {
        let name = case["name"].as_str().unwrap().to_string();
        let input = &case["input"];
        let limits: SafetyLimits = serde_json::from_value(input["limits"].clone())
            .unwrap_or_else(|e| panic!("govern[{name}]: bad limits: {e}"));
        let command: CommandFrame = serde_json::from_value(input["command"].clone())
            .unwrap_or_else(|e| panic!("govern[{name}]: bad command: {e}"));
        let sensor: Option<SensorFrame> = serde_json::from_value(input["sensor"].clone())
            .unwrap_or_else(|e| panic!("govern[{name}]: bad sensor: {e}"));
        let now_s = input["now_s"].as_f64().expect("now_s");
        let last_sensor_s = input["last_sensor_s"].as_f64(); // None when null

        let command_valid = command.validate_wire().is_ok();
        let sensor_valid = sensor
            .as_ref()
            .is_some_and(|frame| frame.validate_wire().is_ok());
        if !command_valid || !sensor_valid {
            if !command_valid && command.mode != Mode::Estop {
                let bytes = serde_json::to_vec(&command).unwrap();
                assert!(
                    client.publish_command(SID, &bytes).await.is_err(),
                    "govern[{name}]: invalid non-ESTOP command must be rejected by the publisher"
                );
                rejected_at_ingress += 1;
            }
            if let Some(sensor) = sensor.as_ref().filter(|_| !sensor_valid) {
                let bytes = serde_json::to_vec(sensor).unwrap();
                assert!(
                    client.put_sensor(SID, &bytes).await.is_err(),
                    "govern[{name}]: invalid sensor must be rejected by the publisher"
                );
                rejected_at_ingress += 1;
            }
            // A deliberately malformed ESTOP is allowed by policy and is covered
            // by the pure publish-gate + cross-language corpus tests; publishing
            // it here would race the next case's fresh-governor reset.
            continue;
        }
        {
            let mut s = state.lock().unwrap();
            s.gov = SafetyGovernor::new(limits);
            s.now_s = now_s;
            s.last_sensor_s = last_sensor_s;
        }
        let got = govern_over_wire(
            &client,
            &state,
            &sink,
            command,
            sensor.expect("sensor_valid proves presence"),
        )
        .await;
        transported += 1;
        assert_eq!(
            got["mode"].as_str().unwrap(),
            case["expect"]["mode"].as_str().unwrap(),
            "govern[{name}]: mode over the wire"
        );
        if let Some(want) = case["expect"]["velocity_setpoint_magnitude"].as_f64() {
            let got_mag = velocity_magnitude(&got);
            assert!(
                (got_mag - want).abs() < 1e-9,
                "govern[{name}]: velocity magnitude want {want}, got {got_mag} over the wire"
            );
        }
    }
    assert!(transported >= 10, "unexpected loss of valid wire coverage");
    assert!(
        rejected_at_ingress >= 4,
        "hostile corpus cases did not exercise the publisher gates"
    );

    // ── 2. The ESTOP LATCH survives the transport (the wire-specific property) ──
    // One persistent governor: a geofence breach latches ESTOP, and a SUBSEQUENT
    // perfectly-safe frame — a full second round trip later — is STILL ESTOP.
    {
        let mut s = state.lock().unwrap();
        s.gov = SafetyGovernor::new(SafetyLimits {
            geofence_radius_m: Some(5.0),
            command_timeout_ms: 500.0,
            ..Default::default()
        });
        s.now_s = 1.0;
        s.last_sensor_s = Some(1.0);
    }
    let active_cmd: CommandFrame = serde_json::from_value(json!({
        "kind": "command_frame", "ncp_version": ncp_core::NCP_VERSION,
        "seq": 1, "mode": "active", "ttl_ms": 200.0,
        "channels": {"velocity_setpoint": {"data": [2.0, 0.0, 0.0], "unit": "m/s"}}
    }))
    .unwrap();
    let breach: SensorFrame = serde_json::from_value(json!({
        "kind": "sensor_frame", "ncp_version": ncp_core::NCP_VERSION, "seq": 1,
        "channels": {"pose_position": {"data": [10.0, 0.0, 0.0], "unit": "m"}}
    }))
    .unwrap();
    let estopped = govern_over_wire(&client, &state, &sink, active_cmd.clone(), breach).await;
    assert_eq!(
        estopped["mode"].as_str().unwrap(),
        "estop",
        "a geofence breach must ESTOP over the wire"
    );

    let safe: SensorFrame = serde_json::from_value(json!({
        "kind": "sensor_frame", "ncp_version": ncp_core::NCP_VERSION, "seq": 1,
        "channels": {"pose_position": {"data": [0.0, 0.0, 0.0], "unit": "m"}}
    }))
    .unwrap();
    let still = govern_over_wire(&client, &state, &sink, active_cmd, safe).await;
    assert_eq!(
        still["mode"].as_str().unwrap(),
        "estop",
        "ESTOP must LATCH across the wire — a safe sensor must not clear it"
    );
    assert!(
        velocity_magnitude(&still).abs() < 1e-9,
        "a latched ESTOP must zero the command over the wire"
    );

    let _ = client.close().await;
    let _ = server.close().await;
}
