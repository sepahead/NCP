//! In-process UAV action-plane demonstration using NCP wire-1.0 `CommandFrame`s.
//!
//! This is a deliberately small simulation, not a production security profile,
//! physical safety system, flight certification, interoperability certification,
//! or scientific/posterior-calibration claim. The controller and plant share one
//! unauthenticated in-process Zenoh session. A bounded authority lease is acquired
//! locally only to demonstrate the wire and receiver-side gates; a real deployment
//! must bind authority to its verified transport principal and default-deny
//! manifest.
//!
//! The simulated plant accepts velocity only when all of these are true:
//! the command is for the configured live session, its locally measured age is
//! strictly below the example's bounded watchdog TTL, it carries the exact locally
//! active authority lease, and its only channel is a finite world-frame vec3 in
//! `m/s`. HOLD/unknown/invalid inputs de-energize. ESTOP latches for the remainder
//! of this session generation; this example intentionally exposes no reset path.
//! Restart only after a lifecycle authority has opened a fresh generation.
//! Zero velocity is merely this simulated model's inert output, not a claim that
//! any physical plant has a universal zero-safe action.
//!
//! Required environment: `NCP_REALM`, `NCP_SESSION_ID`, and
//! `NCP_SESSION_GENERATION` (a server-issued canonical lowercase UUIDv4).
//! `NCP_TRAJ_OUT` is optional and defaults to `./ncp_drone_trajectory.jsonl`.
//!
//! Run: `cargo run -p ncp-zenoh --example uav_drone_loop`
//! No router is required; scouting is disabled for the single in-process session.

use ncp_core::authority::MAX_AUTHORITY_LEASE_MS;
use ncp_core::security::AuthenticatedActor;
use ncp_core::{
    AuthorityLease, AuthorityMachine, ChannelValue, CommandFrame, Keys, LifecycleState, Mode,
    PrincipalRole, SessionRef, StreamPosition, WireFrame, JSON_SAFE_INTEGER_MAX,
};
use ncp_zenoh::{ZenohBus, ZenohConfig};
use std::error::Error;
use std::fs::File;
use std::io::{self, BufWriter, Write};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const COMMANDER_PRINCIPAL: &str = "uav-example-commander";
const COMMANDER_ENTITY: &str = "uav-example-controller";
const EXAMPLE_LEASE_DURATION_MS: i64 = 30_000;
const EXAMPLE_COMMAND_TTL_MS: f64 = 250.0;
// Example-model envelope only; this is not a physical plant profile or certification.
const EXAMPLE_MAX_COMPONENT_SPEED_M_S: f64 = 5.0;
const MAX_REALM_BYTES: usize = 256;
const MAX_TRAJECTORY_PATH_BYTES: usize = 4_096;
const CONTROL_HZ: usize = 20;
const PLANT_HZ: usize = 50;
const PLANT_STEPS: usize = 8 * PLANT_HZ;

type ExampleResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

fn invalid_input(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message.into())
}

fn required_env(name: &str) -> io::Result<String> {
    match std::env::var(name) {
        Ok(value) => Ok(value),
        Err(std::env::VarError::NotPresent) => Err(invalid_input(format!(
            "required environment variable {name} is not set"
        ))),
        Err(std::env::VarError::NotUnicode(_)) => Err(invalid_input(format!(
            "environment variable {name} is not valid UTF-8"
        ))),
    }
}

fn optional_env(name: &str, default: &str) -> io::Result<String> {
    match std::env::var(name) {
        Ok(value) => Ok(value),
        Err(std::env::VarError::NotPresent) => Ok(default.to_owned()),
        Err(std::env::VarError::NotUnicode(_)) => Err(invalid_input(format!(
            "environment variable {name} is not valid UTF-8"
        ))),
    }
}

#[derive(Clone, Debug)]
struct ExampleConfig {
    realm: String,
    session_id: String,
    live_session: SessionRef,
    trajectory_path: String,
    keys: Keys,
}

impl ExampleConfig {
    fn from_env() -> io::Result<Self> {
        Self::from_values(
            required_env("NCP_REALM")?,
            required_env("NCP_SESSION_ID")?,
            required_env("NCP_SESSION_GENERATION")?,
            optional_env("NCP_TRAJ_OUT", "./ncp_drone_trajectory.jsonl")?,
        )
    }

    fn from_values(
        realm: String,
        session_id: String,
        session_generation: String,
        trajectory_path: String,
    ) -> io::Result<Self> {
        if realm.len() > MAX_REALM_BYTES {
            return Err(invalid_input(format!(
                "NCP_REALM exceeds the {MAX_REALM_BYTES}-byte example limit"
            )));
        }
        let keys =
            Keys::try_new(realm.clone()).map_err(|error| invalid_input(error.to_string()))?;
        if session_id.len() > 64 || !ncp_core::valid_id_segment(&session_id) {
            return Err(invalid_input(
                "NCP_SESSION_ID must be a safe single key segment of 1..=64 bytes",
            ));
        }
        if !ncp_core::is_canonical_uuid_v4(&session_generation) {
            return Err(invalid_input(
                "NCP_SESSION_GENERATION must be a canonical lowercase UUIDv4",
            ));
        }
        if trajectory_path.is_empty()
            || trajectory_path.len() > MAX_TRAJECTORY_PATH_BYTES
            || trajectory_path.chars().any(char::is_control)
        {
            return Err(invalid_input(format!(
                "NCP_TRAJ_OUT must be a non-empty control-free UTF-8 path of at most \
                 {MAX_TRAJECTORY_PATH_BYTES} bytes"
            )));
        }
        // Exercise the fallible builder now, before any Zenoh resource is opened.
        keys.try_command(&session_id)
            .map_err(|error| invalid_input(error.to_string()))?;
        Ok(Self {
            realm,
            session_id,
            live_session: SessionRef {
                generation: session_generation,
            },
            trajectory_path,
            keys,
        })
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct DroneState {
    x: f64,
    y: f64,
    z: f64,
}

/// Latest validated action-plane command and its receiver-local arrival instant.
#[derive(Clone)]
struct LatestCmd {
    frame: CommandFrame,
    arrived: Instant,
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct PlantOutput {
    label: &'static str,
    velocity: [f64; 3],
}

impl PlantOutput {
    const fn stopped(label: &'static str) -> Self {
        Self {
            label,
            velocity: [0.0, 0.0, 0.0],
        }
    }
}

struct ExamplePlantGate {
    authority: AuthorityMachine,
    live_session_id: String,
    live_session: SessionRef,
}

impl ExamplePlantGate {
    fn new(authority: AuthorityMachine, live_session_id: String, live_session: SessionRef) -> Self {
        Self {
            authority,
            live_session_id,
            live_session,
        }
    }

    fn govern(
        &mut self,
        command: Option<&CommandFrame>,
        age: Option<Duration>,
        now_monotonic_ms: u64,
    ) -> PlantOutput {
        self.authority.tick(now_monotonic_ms);
        if self.authority.state() == LifecycleState::Estop {
            return PlantOutput::stopped("estop_latched");
        }

        let Some(frame) = command else {
            return PlantOutput::stopped("no_command");
        };
        if frame.session_id != self.live_session_id || frame.session != self.live_session {
            return PlantOutput::stopped("session_hold");
        }
        match &frame.mode {
            Mode::Estop => {
                self.authority.estop();
                return PlantOutput::stopped("estop_latched");
            }
            Mode::Init => return PlantOutput::stopped("init_hold"),
            Mode::Hold => return PlantOutput::stopped("hold"),
            Mode::Unknown(_) => return PlantOutput::stopped("unknown_hold"),
            Mode::Active => {}
        }

        let fresh = age.is_some_and(|elapsed| {
            frame.ttl_ms.is_finite()
                && frame.ttl_ms > 0.0
                && frame.ttl_ms <= EXAMPLE_COMMAND_TTL_MS
                && elapsed.as_secs_f64() * 1_000.0 < frame.ttl_ms
        });
        if !fresh {
            // Strict boundary: age == ttl_ms is already expired.
            return PlantOutput::stopped("watchdog_hold");
        }

        let Some(active_lease) = self.authority.active_lease(now_monotonic_ms) else {
            return PlantOutput::stopped("authority_hold");
        };
        if frame.authority.as_ref() != Some(active_lease) {
            return PlantOutput::stopped("authority_hold");
        }
        let Some(velocity) = command_velocity(frame) else {
            return PlantOutput::stopped("invalid_command_hold");
        };
        PlantOutput {
            label: "active",
            velocity,
        }
    }
}

fn command_velocity(frame: &CommandFrame) -> Option<[f64; 3]> {
    if frame.frame_id != "world" || frame.channels.len() != 1 {
        return None;
    }
    let channel = frame.channels.get("velocity_setpoint")?;
    if channel.unit.as_deref() != Some("m/s") || channel.data.len() != 3 {
        return None;
    }
    let velocity = [channel.data[0], channel.data[1], channel.data[2]];
    velocity
        .iter()
        .all(|component| {
            component.is_finite() && component.abs() <= EXAMPLE_MAX_COMPONENT_SPEED_M_S
        })
        .then_some(velocity)
}

fn example_actor() -> AuthenticatedActor {
    AuthenticatedActor {
        principal_id: COMMANDER_PRINCIPAL.to_owned(),
        certificate_identity: "local-example-only-no-transport-authentication".to_owned(),
        entity_id: COMMANDER_ENTITY.to_owned(),
        role: PrincipalRole::Commander,
        may_reset_estop: false,
        may_override: false,
    }
}

fn activate_example_authority(
    live_session: &SessionRef,
    lease_id: String,
    now_utc_ms: i64,
    now_monotonic_ms: u64,
) -> ExampleResult<(AuthorityLease, AuthorityMachine)> {
    let expires_at_utc_ms = now_utc_ms
        .checked_add(EXAMPLE_LEASE_DURATION_MS)
        .ok_or_else(|| invalid_input("authority lease UTC expiry overflow"))?;
    let lease = AuthorityLease {
        session_epoch: live_session.generation.clone(),
        term: 1,
        lease_id,
        issuer_principal_id: COMMANDER_PRINCIPAL.to_owned(),
        holder_principal_id: COMMANDER_PRINCIPAL.to_owned(),
        holder_entity_id: COMMANDER_ENTITY.to_owned(),
        issued_at_utc_ms: now_utc_ms,
        expires_at_utc_ms,
    };
    let actor = example_actor();
    let mut authority = AuthorityMachine::new(live_session.generation.clone())?;
    authority.begin_open()?;
    authority.initialize()?;
    authority.acquire(lease.clone(), &actor, &actor, now_utc_ms, now_monotonic_ms)?;
    Ok((lease, authority))
}

fn utc_now_ms() -> io::Result<i64> {
    let elapsed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| io::Error::other(format!("system UTC precedes Unix epoch: {error}")))?;
    let millis = i64::try_from(elapsed.as_millis())
        .map_err(|_| io::Error::other("system UTC millisecond value exceeds i64"))?;
    if millis > JSON_SAFE_INTEGER_MAX {
        return Err(io::Error::other(
            "system UTC millisecond value exceeds the exact JSON integer range",
        ));
    }
    Ok(millis)
}

fn valid_bounded_identity(value: &str) -> bool {
    value.len() <= 128 && ncp_core::valid_id_segment(value)
}

fn validate_lease_for_emit(
    lease: &AuthorityLease,
    live_session: &SessionRef,
    now_utc_ms: i64,
) -> io::Result<()> {
    if lease.session_epoch != live_session.generation
        || !ncp_core::is_canonical_uuid_v4(&lease.session_epoch)
        || !ncp_core::is_canonical_uuid_v4(&lease.lease_id)
    {
        return Err(invalid_input(
            "Active command authority does not identify the configured live session",
        ));
    }
    if lease.term == 0 || lease.term > JSON_SAFE_INTEGER_MAX as u64 {
        return Err(invalid_input(
            "Active command authority term is outside the exact JSON integer range",
        ));
    }
    if ![
        lease.issuer_principal_id.as_str(),
        lease.holder_principal_id.as_str(),
        lease.holder_entity_id.as_str(),
    ]
    .into_iter()
    .all(valid_bounded_identity)
    {
        return Err(invalid_input(
            "Active command authority identities are empty, unsafe, or unbounded",
        ));
    }
    let duration = lease
        .expires_at_utc_ms
        .checked_sub(lease.issued_at_utc_ms)
        .ok_or_else(|| invalid_input("Active command authority duration overflow"))?;
    if !(1..=MAX_AUTHORITY_LEASE_MS).contains(&duration)
        || lease.issued_at_utc_ms < 0
        || now_utc_ms < lease.issued_at_utc_ms
        || now_utc_ms >= lease.expires_at_utc_ms
    {
        return Err(invalid_input(
            "Active command authority lease is not live at emission",
        ));
    }
    Ok(())
}

fn active_lease_for_emit<'a>(
    authority: &'a mut AuthorityMachine,
    expected_lease: &AuthorityLease,
    now_monotonic_ms: u64,
) -> io::Result<&'a AuthorityLease> {
    authority.tick(now_monotonic_ms);
    authority
        .active_lease(now_monotonic_ms)
        .filter(|lease| *lease == expected_lease)
        .ok_or_else(|| {
            invalid_input("refusing to emit Active: local live-session authority is inactive")
        })
}

#[allow(clippy::too_many_arguments)]
fn build_command(
    session_id: &str,
    live_session: &SessionRef,
    stream_epoch: &str,
    seq: i64,
    t_ms: f64,
    mode: Mode,
    velocity: [f64; 3],
    acquired_lease: Option<&AuthorityLease>,
    now_utc_ms: i64,
) -> io::Result<CommandFrame> {
    let authority = if mode == Mode::Active {
        let lease = acquired_lease.ok_or_else(|| {
            invalid_input("refusing to emit Active command without an acquired authority lease")
        })?;
        validate_lease_for_emit(lease, live_session, now_utc_ms)?;
        Some(lease.clone())
    } else {
        if acquired_lease.is_some() {
            return Err(invalid_input(
                "non-Active example commands must not carry controller authority",
            ));
        }
        None
    };

    let mut channels = ncp_core::Map::new();
    channels.insert(
        "velocity_setpoint".to_owned(),
        ChannelValue::vec3(velocity[0], velocity[1], velocity[2], Some("m/s")),
    );
    let frame = CommandFrame {
        stream: StreamPosition {
            epoch: stream_epoch.to_owned(),
            seq,
        },
        session: live_session.clone(),
        session_id: session_id.to_owned(),
        t: t_ms,
        ttl_ms: EXAMPLE_COMMAND_TTL_MS,
        mode,
        channels,
        authority,
        ..Default::default()
    };
    if frame.mode == Mode::Active && command_velocity(&frame).is_none() {
        return Err(invalid_input(
            "refusing to emit Active outside the defined example velocity envelope",
        ));
    }
    frame
        .validate_wire()
        .map_err(|error| invalid_input(format!("invalid example command: {error}")))?;
    let encoded = serde_json::to_vec(&frame)
        .map_err(|error| invalid_input(format!("cannot encode example command: {error}")))?;
    ncp_core::validate_command_plane_payload_for(session_id, live_session, &encoded)
        .map_err(|error| invalid_input(format!("invalid example command envelope: {error}")))?;
    Ok(frame)
}

#[derive(Clone, Copy)]
enum PlanAction {
    Active,
    Hold,
    Dropout,
    Estop,
}

#[derive(Clone, Copy)]
struct PlanLeg {
    ticks: usize,
    action: PlanAction,
    velocity: [f64; 3],
}

const PLAN: &[PlanLeg] = &[
    PlanLeg {
        ticks: 30,
        action: PlanAction::Active,
        velocity: [0.0, 1.5, 0.0],
    },
    PlanLeg {
        ticks: 30,
        action: PlanAction::Active,
        velocity: [2.0, 0.0, 0.0],
    },
    PlanLeg {
        ticks: 30,
        action: PlanAction::Active,
        velocity: [0.0, 0.0, 2.0],
    },
    PlanLeg {
        ticks: 20,
        // Stop publishing while the last Active command is still selected so the
        // receiver visibly reaches its strict watchdog boundary.
        action: PlanAction::Dropout,
        velocity: [0.0, 0.0, 0.0],
    },
    PlanLeg {
        ticks: 20,
        action: PlanAction::Hold,
        velocity: [0.0, 0.0, 0.0],
    },
    PlanLeg {
        ticks: 20,
        action: PlanAction::Estop,
        velocity: [9.0, 9.0, 9.0],
    },
    // Remain silent after ESTOP. Hostile later Active traffic is exercised by the
    // receiver-gate tests; this controller must never originate it.
    PlanLeg {
        ticks: 10,
        action: PlanAction::Dropout,
        velocity: [0.0, 0.0, 0.0],
    },
];

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() -> ExampleResult<()> {
    let config = ExampleConfig::from_env()?;
    let command_key = config
        .keys
        .try_command(&config.session_id)
        .map_err(|error| invalid_input(error.to_string()))?;

    let authority_origin = Instant::now();
    let authority_issued_at_utc_ms = utc_now_ms()?;
    let lease_id = ncp_core::transport::mint_stream_epoch()?;
    let (controller_lease, mut controller_authority) = activate_example_authority(
        &config.live_session,
        lease_id,
        authority_issued_at_utc_ms,
        0,
    )?;
    let plant_authority = controller_authority.clone();
    let command_stream_epoch = ncp_core::transport::mint_stream_epoch()?;

    let mut zenoh_config = ZenohConfig::default();
    zenoh_config.insert_json5("scouting/multicast/enabled", "false")?;
    zenoh_config.insert_json5("scouting/gossip/enabled", "false")?;
    let bus = ZenohBus::with_config(zenoh_config, config.keys.clone()).await?;
    println!(
        "NCP UAV example  realm={}  key={}  generation={}  -> {}",
        config.realm, command_key, config.live_session.generation, config.trajectory_path
    );
    println!(
        "DEMO ONLY: local unauthenticated authority; not production security or flight certification"
    );

    let latest: Arc<Mutex<Option<LatestCmd>>> = Arc::new(Mutex::new(None));
    let sink = Arc::clone(&latest);
    bus.subscribe_commands(
        &config.session_id,
        &config.live_session,
        move |_key, bytes| {
            if let Ok(frame) = serde_json::from_slice::<CommandFrame>(&bytes) {
                *sink.lock().unwrap_or_else(|error| error.into_inner()) = Some(LatestCmd {
                    frame,
                    arrived: Instant::now(),
                });
            }
        },
    )
    .await?;

    // Let the local subscription declaration settle before publishing.
    tokio::time::sleep(Duration::from_millis(300)).await;

    let trajectory = Arc::new(Mutex::new(Vec::<String>::new()));
    let plant_trajectory = Arc::clone(&trajectory);
    let plant_latest = Arc::clone(&latest);
    let mut plant_gate = ExamplePlantGate::new(
        plant_authority,
        config.session_id.clone(),
        config.live_session.clone(),
    );
    let plant = tokio::spawn(async move {
        let dt = 1.0 / PLANT_HZ as f64;
        let mut state = DroneState::default();
        for step in 1..=PLANT_STEPS {
            tokio::time::sleep(Duration::from_millis(1_000 / PLANT_HZ as u64)).await;
            let latest = plant_latest
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .clone();
            let age = latest.as_ref().map(|command| command.arrived.elapsed());
            let now_monotonic_ms =
                u64::try_from(authority_origin.elapsed().as_millis()).unwrap_or(u64::MAX);
            let output = plant_gate.govern(
                latest.as_ref().map(|command| &command.frame),
                age,
                now_monotonic_ms,
            );
            let mut velocity = output.velocity;
            if state.y <= 0.0 && velocity[1] < 0.0 {
                velocity[1] = 0.0;
            }
            state.x += velocity[0] * dt;
            state.y += velocity[1] * dt;
            state.z += velocity[2] * dt;
            state.y = state.y.max(0.0);

            let t = step as f64 * dt;
            let line = format!(
                "{{\"t\":{t:.2},\"x\":{:.3},\"y\":{:.3},\"z\":{:.3},\"vx\":{:.3},\"vy\":{:.3},\"vz\":{:.3},\"mode\":\"{}\"}}",
                state.x,
                state.y,
                state.z,
                velocity[0],
                velocity[1],
                velocity[2],
                output.label
            );
            plant_trajectory
                .lock()
                .unwrap_or_else(|error| error.into_inner())
                .push(line);
            if step.is_multiple_of(10) {
                println!(
                    "  t={t:4.2}s  pos=({:6.2},{:6.2},{:6.2})  \
                     v=({:5.2},{:5.2},{:5.2})  [{}]",
                    state.x, state.y, state.z, velocity[0], velocity[1], velocity[2], output.label
                );
            }
        }
    });

    let period = Duration::from_millis(1_000 / CONTROL_HZ as u64);
    let mut sequence = 0_i64;
    let mut elapsed_ticks = 0_usize;
    for leg in PLAN {
        for _ in 0..leg.ticks {
            elapsed_ticks += 1;
            let now_monotonic_ms =
                u64::try_from(authority_origin.elapsed().as_millis()).unwrap_or(u64::MAX);
            let (mode, lease) = match leg.action {
                PlanAction::Active => {
                    let active_lease = active_lease_for_emit(
                        &mut controller_authority,
                        &controller_lease,
                        now_monotonic_ms,
                    )?;
                    (Mode::Active, Some(active_lease))
                }
                PlanAction::Hold => (Mode::Hold, None),
                PlanAction::Estop => {
                    // Latch the controller-side copy before publication. A delivery-
                    // ambiguous ESTOP must never leave this controller free to resume.
                    controller_authority.estop();
                    (Mode::Estop, None)
                }
                PlanAction::Dropout => {
                    tokio::time::sleep(period).await;
                    continue;
                }
            };
            sequence = sequence
                .checked_add(1)
                .ok_or_else(|| io::Error::other("command sequence overflow"))?;
            let command = build_command(
                &config.session_id,
                &config.live_session,
                &command_stream_epoch,
                sequence,
                elapsed_ticks as f64 * (1_000.0 / CONTROL_HZ as f64),
                mode,
                leg.velocity,
                lease,
                utc_now_ms()?,
            )?;
            let payload = serde_json::to_vec(&command)?;
            bus.publish_command(&config.session_id, &config.live_session, &payload)
                .await?;
            tokio::time::sleep(period).await;
        }
    }

    plant.await?;

    let lines = trajectory
        .lock()
        .unwrap_or_else(|error| error.into_inner())
        .clone();
    let file = File::create(&config.trajectory_path)?;
    let mut writer = BufWriter::new(file);
    for line in &lines {
        writeln!(writer, "{line}")?;
    }
    writer.flush()?;
    bus.close().await?;
    println!(
        "wrote {} simulated trajectory samples to {}",
        lines.len(),
        config.trajectory_path
    );
    println!("done; ESTOP remained latched and no reset was attempted");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const GENERATION: &str = "123e4567-e89b-42d3-a456-426614174000";
    const LEASE_ID: &str = "123e4567-e89b-42d3-a456-426614174001";
    const STREAM_EPOCH: &str = "123e4567-e89b-42d3-a456-426614174002";
    const NOW_UTC_MS: i64 = 10_000;
    const NOW_MONOTONIC_MS: u64 = 100;

    fn live_session() -> SessionRef {
        SessionRef {
            generation: GENERATION.to_owned(),
        }
    }

    fn gate_and_lease() -> (ExamplePlantGate, AuthorityLease) {
        let session = live_session();
        let (lease, machine) =
            activate_example_authority(&session, LEASE_ID.to_owned(), NOW_UTC_MS, NOW_MONOTONIC_MS)
                .expect("test authority must activate");
        (
            ExamplePlantGate::new(machine, "uav1".to_owned(), session),
            lease,
        )
    }

    fn command(mode: Mode, lease: Option<&AuthorityLease>) -> CommandFrame {
        build_command(
            "uav1",
            &live_session(),
            STREAM_EPOCH,
            1,
            50.0,
            mode,
            [1.0, 2.0, 3.0],
            lease,
            NOW_UTC_MS,
        )
        .expect("test command must be valid")
    }

    #[test]
    fn config_rejects_unvalidated_routing_values() {
        let valid = |realm: &str, session: &str, generation: &str| {
            ExampleConfig::from_values(
                realm.to_owned(),
                session.to_owned(),
                generation.to_owned(),
                "trajectory.jsonl".to_owned(),
            )
        };
        assert!(valid("", "uav1", GENERATION).is_err());
        assert!(valid("ncp/*", "uav1", GENERATION).is_err());
        assert!(valid("ncp", "", GENERATION).is_err());
        assert!(valid("ncp", "uav/other", GENERATION).is_err());
        assert!(valid("ncp", &"x".repeat(65), GENERATION).is_err());
        assert!(valid("ncp", "uav1", "not-a-generation").is_err());
        assert!(valid("ncp", "uav1", GENERATION).is_ok());
    }

    #[test]
    fn active_builder_requires_a_live_matching_lease() {
        let (_, lease) = gate_and_lease();
        assert!(build_command(
            "uav1",
            &live_session(),
            STREAM_EPOCH,
            1,
            50.0,
            Mode::Active,
            [1.0, 2.0, 3.0],
            None,
            NOW_UTC_MS,
        )
        .is_err());

        let mut wrong_generation = lease.clone();
        wrong_generation.session_epoch = "123e4567-e89b-42d3-a456-426614174099".to_owned();
        assert!(build_command(
            "uav1",
            &live_session(),
            STREAM_EPOCH,
            1,
            50.0,
            Mode::Active,
            [1.0, 2.0, 3.0],
            Some(&wrong_generation),
            NOW_UTC_MS,
        )
        .is_err());

        assert!(build_command(
            "uav1",
            &live_session(),
            STREAM_EPOCH,
            1,
            50.0,
            Mode::Active,
            [1.0, 2.0, 3.0],
            Some(&lease),
            lease.expires_at_utc_ms,
        )
        .is_err());
        assert!(build_command(
            "uav1",
            &live_session(),
            STREAM_EPOCH,
            1,
            50.0,
            Mode::Active,
            [1.0, 2.0, 3.0],
            Some(&lease),
            lease.expires_at_utc_ms - 1,
        )
        .is_ok());
        assert!(build_command(
            "uav1",
            &live_session(),
            STREAM_EPOCH,
            1,
            50.0,
            Mode::Active,
            [EXAMPLE_MAX_COMPONENT_SPEED_M_S + 0.001, 0.0, 0.0],
            Some(&lease),
            NOW_UTC_MS,
        )
        .is_err());
    }

    #[test]
    fn controller_never_reissues_active_after_estop() {
        let session = live_session();
        let (lease, mut authority) =
            activate_example_authority(&session, LEASE_ID.to_owned(), NOW_UTC_MS, NOW_MONOTONIC_MS)
                .expect("test authority must activate");
        assert!(active_lease_for_emit(&mut authority, &lease, NOW_MONOTONIC_MS).is_ok());
        authority.estop();
        assert!(active_lease_for_emit(&mut authority, &lease, NOW_MONOTONIC_MS).is_err());
    }

    #[test]
    fn watchdog_expires_at_ttl_equality_and_rejects_oversized_ttl() {
        let (mut gate, lease) = gate_and_lease();
        let frame = command(Mode::Active, Some(&lease));
        assert_eq!(
            gate.govern(
                Some(&frame),
                Some(Duration::from_millis(249)),
                NOW_MONOTONIC_MS,
            ),
            PlantOutput {
                label: "active",
                velocity: [1.0, 2.0, 3.0],
            }
        );
        assert_eq!(
            gate.govern(
                Some(&frame),
                Some(Duration::from_millis(250)),
                NOW_MONOTONIC_MS,
            ),
            PlantOutput::stopped("watchdog_hold")
        );

        let mut oversized = frame;
        oversized.ttl_ms = EXAMPLE_COMMAND_TTL_MS + 1.0;
        assert_eq!(
            gate.govern(Some(&oversized), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("watchdog_hold")
        );
    }

    #[test]
    fn authority_expires_at_receiver_monotonic_deadline() {
        let (mut gate, lease) = gate_and_lease();
        let frame = command(Mode::Active, Some(&lease));
        let deadline = NOW_MONOTONIC_MS + EXAMPLE_LEASE_DURATION_MS as u64;
        assert_eq!(
            gate.govern(Some(&frame), Some(Duration::ZERO), deadline - 1)
                .label,
            "active"
        );
        assert_eq!(
            gate.govern(Some(&frame), Some(Duration::ZERO), deadline),
            PlantOutput::stopped("authority_hold")
        );
    }

    #[test]
    fn active_requires_the_exact_locally_active_authority() {
        let (mut gate, lease) = gate_and_lease();
        let mut missing = command(Mode::Active, Some(&lease));
        missing.authority = None;
        assert_eq!(
            gate.govern(Some(&missing), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("authority_hold")
        );

        let mut wrong = command(Mode::Active, Some(&lease));
        wrong.authority.as_mut().expect("authority exists").lease_id =
            "123e4567-e89b-42d3-a456-426614174099".to_owned();
        assert_eq!(
            gate.govern(Some(&wrong), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("authority_hold")
        );
    }

    #[test]
    fn estop_latches_and_later_active_cannot_clear_it() {
        let (mut gate, lease) = gate_and_lease();
        let estop = command(Mode::Estop, None);
        assert_eq!(
            gate.govern(
                Some(&estop),
                Some(Duration::from_secs(99)),
                NOW_MONOTONIC_MS,
            ),
            PlantOutput::stopped("estop_latched")
        );

        let active = command(Mode::Active, Some(&lease));
        assert_eq!(
            gate.govern(Some(&active), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("estop_latched")
        );
        assert_eq!(gate.authority.state(), LifecycleState::Estop);
    }

    #[test]
    fn foreign_session_estop_cannot_latch_the_live_session() {
        let (mut gate, lease) = gate_and_lease();
        let mut foreign_estop = command(Mode::Estop, None);
        foreign_estop.session_id = "other".to_owned();
        assert_eq!(
            gate.govern(Some(&foreign_estop), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("session_hold")
        );

        let active = command(Mode::Active, Some(&lease));
        assert_eq!(
            gate.govern(Some(&active), Some(Duration::ZERO), NOW_MONOTONIC_MS,)
                .label,
            "active"
        );
    }

    #[test]
    fn malformed_velocity_never_actuates() {
        let (mut gate, lease) = gate_and_lease();
        let mut frame = command(Mode::Active, Some(&lease));
        frame
            .channels
            .get_mut("velocity_setpoint")
            .expect("velocity channel exists")
            .data
            .push(4.0);
        assert_eq!(
            gate.govern(Some(&frame), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("invalid_command_hold")
        );

        let mut wrong_unit = command(Mode::Active, Some(&lease));
        wrong_unit
            .channels
            .get_mut("velocity_setpoint")
            .expect("velocity channel exists")
            .unit = Some("km/h".to_owned());
        assert_eq!(
            gate.govern(Some(&wrong_unit), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("invalid_command_hold")
        );

        let mut non_finite = command(Mode::Active, Some(&lease));
        non_finite
            .channels
            .get_mut("velocity_setpoint")
            .expect("velocity channel exists")
            .data[0] = f64::NAN;
        assert_eq!(
            gate.govern(Some(&non_finite), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("invalid_command_hold")
        );

        let mut unbounded = command(Mode::Active, Some(&lease));
        unbounded
            .channels
            .get_mut("velocity_setpoint")
            .expect("velocity channel exists")
            .data[0] = EXAMPLE_MAX_COMPONENT_SPEED_M_S + 0.001;
        assert_eq!(
            gate.govern(Some(&unbounded), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("invalid_command_hold")
        );

        let mut wrong_frame = command(Mode::Active, Some(&lease));
        wrong_frame.frame_id = "body".to_owned();
        assert_eq!(
            gate.govern(Some(&wrong_frame), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("invalid_command_hold")
        );

        let mut extra_channel = command(Mode::Active, Some(&lease));
        extra_channel.channels.insert(
            "unexpected_actuator".to_owned(),
            ChannelValue::scalar(1.0, None),
        );
        assert_eq!(
            gate.govern(Some(&extra_channel), Some(Duration::ZERO), NOW_MONOTONIC_MS,),
            PlantOutput::stopped("invalid_command_hold")
        );
    }
}
