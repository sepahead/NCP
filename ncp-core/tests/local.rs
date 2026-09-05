use std::io::{Cursor, Write};
use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc,
};

use ncp_core::local::*;
use ncp_core::local_data::*;
use serde_json::{json, Value};

fn binding(role: LocalRole) -> LocalBinding {
    LocalBinding {
        profile_digest: local_profile_digest().unwrap(),
        run_id: "10c99b86-c8e0-4b94-80ae-8cec74456e2a".into(),
        generation: "748d5ab4-51c1-408f-b144-a27602edc823".into(),
        role,
    }
}

#[derive(Default)]
struct Counts {
    executions: AtomicUsize,
    retires: AtomicUsize,
}
struct Backend(Arc<Counts>);
impl LocalBackend for Backend {
    fn validate(&self, _: LocalOperation, body: &Value) -> Result<(), LocalError> {
        match body.get("reject").and_then(Value::as_str) {
            Some("invalid") => Err(LocalError(LocalCode::InvalidInput)),
            Some("bad_code") => Err(LocalError(LocalCode::Ok)),
            _ => Ok(()),
        }
    }
    fn execute(&mut self, _: LocalOperation, body: &Value) -> Result<Value, LocalError> {
        let count = self.0.executions.fetch_add(1, Ordering::SeqCst) + 1;
        match body.get("fault").and_then(Value::as_str) {
            Some("error") => Err(LocalError(LocalCode::State)),
            Some("panic") => panic!("controlled owner fault"),
            Some("oversize") => Ok(json!({"payload": "x".repeat(MAX_LOCAL_FRAME_BYTES)})),
            Some("deep") => {
                let mut value = Value::Null;
                for _ in 0..34 {
                    value = json!([value]);
                }
                Ok(value)
            }
            _ => Ok(json!({"count": count, "value": body})),
        }
    }
    fn retire(&mut self) {
        self.0.retires.fetch_add(1, Ordering::SeqCst);
    }
}

fn owner(role: LocalRole) -> (LocalOwner<Backend>, Arc<Counts>) {
    let counts = Arc::new(Counts::default());
    (
        LocalOwner::new(binding(role), Backend(counts.clone())).unwrap(),
        counts,
    )
}
fn request(role: LocalRole, sequence: u64, operation: LocalOperation, body: Value) -> LocalRequest {
    let b = binding(role);
    let mut request = LocalRequest {
        schema: "ncp.local.request.v1".into(),
        profile_digest: b.profile_digest,
        run_id: b.run_id,
        generation: b.generation,
        sequence,
        operation,
        body,
        request_digest: String::new(),
    };
    request.seal().unwrap();
    request
}
fn bytes(request: &LocalRequest) -> Vec<u8> {
    serde_json::to_vec(request).unwrap()
}
fn send(owner: &mut LocalOwner<Backend>, request: &LocalRequest) -> LocalResponse {
    serde_json::from_slice(&owner.handle(&bytes(request)).unwrap()).unwrap()
}
fn ack(owner: &mut LocalOwner<Backend>, response: &LocalResponse) -> LocalRequest {
    let request = request(
        owner.binding().role,
        response.sequence,
        LocalOperation::Ack,
        json!({"result_digest": response.result_digest}),
    );
    let response = send(owner, &request);
    response.verify(owner.binding(), &request).unwrap();
    assert_eq!(response.outcome, LocalOutcome::Acknowledged);
    request
}

#[test]
fn exact_replay_lookup_ack_and_compact_unavailable_never_reexecute() {
    let (mut owner, counts) = owner(LocalRole::Body);
    let original = request(
        LocalRole::Body,
        1,
        LocalOperation::Prepare,
        json!({"v": -0.0}),
    );
    let first = owner.handle(&bytes(&original)).unwrap();
    assert_eq!(first, owner.handle(&bytes(&original)).unwrap());
    let query = request(
        LocalRole::Body,
        1,
        LocalOperation::Result,
        json!({"request_digest":original.request_digest}),
    );
    let recovered = owner.handle(&bytes(&query)).unwrap();
    assert_eq!(first, recovered);
    let response: LocalResponse = serde_json::from_slice(&recovered).unwrap();
    response
        .verify_retrieved(owner.binding(), &original, &query)
        .unwrap();
    assert!(response.verify(owner.binding(), &query).is_err());
    let acknowledged = ack(&mut owner, &response);
    assert_eq!(owner.retained_bytes(), 0);
    assert_eq!(
        send(&mut owner, &acknowledged).outcome,
        LocalOutcome::Acknowledged
    );
    let released = send(&mut owner, &query);
    released.verify(owner.binding(), &query).unwrap();
    assert_eq!(released.outcome, LocalOutcome::Unavailable);
    assert_eq!(
        send(&mut owner, &original).outcome,
        LocalOutcome::Unavailable
    );
    assert_eq!(counts.executions.load(Ordering::SeqCst), 1);
}

#[test]
fn unacknowledged_result_blocks_successors_and_changed_retries() {
    let (mut owner, counts) = owner(LocalRole::Body);
    let first = request(LocalRole::Body, 1, LocalOperation::Prepare, json!({}));
    let result = send(&mut owner, &first);
    let changed = request(LocalRole::Body, 1, LocalOperation::Prepare, json!({"x":1}));
    assert_eq!(send(&mut owner, &changed).code, LocalCode::Conflict);
    let next = request(LocalRole::Body, 2, LocalOperation::Step, json!({}));
    assert_eq!(send(&mut owner, &next).code, LocalCode::ResultPending);
    let wrong_ack = request(
        LocalRole::Body,
        1,
        LocalOperation::Ack,
        json!({"result_digest":"0".repeat(64)}),
    );
    assert_eq!(send(&mut owner, &wrong_ack).code, LocalCode::Conflict);
    assert_eq!(counts.executions.load(Ordering::SeqCst), 1);
    ack(&mut owner, &result);
    assert_eq!(send(&mut owner, &next).outcome, LocalOutcome::Committed);
    assert_eq!(counts.executions.load(Ordering::SeqCst), 2);
}

#[test]
fn invalid_data_and_wrong_role_do_not_consume_the_next_position() {
    for role in [LocalRole::Monitor, LocalRole::Capture] {
        let (mut owner, counts) = owner(role);
        let step = request(role, 1, LocalOperation::Step, json!({}));
        let rejected = send(&mut owner, &step);
        rejected.verify(owner.binding(), &step).unwrap();
        assert_eq!(rejected.code, LocalCode::Role);
        for reason in ["invalid", "bad_code"] {
            let invalid = request(role, 1, LocalOperation::Prepare, json!({"reject":reason}));
            let response = send(&mut owner, &invalid);
            response.verify(owner.binding(), &invalid).unwrap();
            assert_eq!(response.code, LocalCode::InvalidInput);
        }
        assert_eq!(counts.executions.load(Ordering::SeqCst), 0);
        let valid = request(role, 1, LocalOperation::Prepare, json!({}));
        assert_eq!(send(&mut owner, &valid).outcome, LocalOutcome::Committed);
    }
}

#[test]
fn wrong_role_response_cannot_forge_success_or_another_rejection() {
    for role in [LocalRole::Monitor, LocalRole::Capture] {
        let (mut owner, counts) = owner(role);
        let step = request(role, 1, LocalOperation::Step, json!({}));
        let rejected = send(&mut owner, &step);
        rejected.verify(owner.binding(), &step).unwrap();
        for (outcome, code) in [
            (LocalOutcome::Committed, LocalCode::Ok),
            (
                LocalOutcome::RejectedBeforeExecution,
                LocalCode::InvalidInput,
            ),
        ] {
            let mut forged = rejected.clone();
            forged.outcome = outcome;
            forged.code = code;
            let mut digest_input = serde_json::to_value(&forged).unwrap();
            digest_input
                .as_object_mut()
                .unwrap()
                .remove("result_digest");
            forged.result_digest = local_digest("ncp.local.response.v1", &digest_input).unwrap();
            assert_eq!(
                forged.verify(owner.binding(), &step),
                Err(LocalError(LocalCode::Binding))
            );
        }
        assert_eq!(counts.executions.load(Ordering::SeqCst), 0);
    }
}

#[test]
fn every_post_execution_fault_is_retained_unknown_and_permanently_retires() {
    for fault in ["error", "panic", "oversize", "deep"] {
        let (mut owner, counts) = owner(LocalRole::Neural);
        let operation = request(
            LocalRole::Neural,
            1,
            LocalOperation::Prepare,
            json!({"fault":fault}),
        );
        let response = send(&mut owner, &operation);
        response.verify(owner.binding(), &operation).unwrap();
        assert_eq!(response.outcome, LocalOutcome::Indeterminate, "{fault}");
        assert_eq!(send(&mut owner, &operation), response);
        assert!(owner.retained_bytes() < 1024);
        ack(&mut owner, &response);
        let next = request(LocalRole::Neural, 2, LocalOperation::Prepare, json!({}));
        assert_eq!(send(&mut owner, &next).code, LocalCode::Retired);
        assert_eq!(counts.executions.load(Ordering::SeqCst), 1);
        drop(owner);
        assert_eq!(counts.retires.load(Ordering::SeqCst), 1);
    }
}

#[test]
fn wrong_identity_and_tampered_digest_never_touch_backend() {
    let (mut owner, counts) = owner(LocalRole::Neural);
    let valid = request(LocalRole::Neural, 1, LocalOperation::Prepare, json!({}));
    for field in ["profile_digest", "generation", "run_id"] {
        let mut value = serde_json::to_value(&valid).unwrap();
        value[field] = json!(if field == "profile_digest" {
            "0".repeat(64)
        } else {
            "64789f06-e732-4db0-9b05-9563c5699813".into()
        });
        let mut changed: LocalRequest = serde_json::from_value(value).unwrap();
        changed.seal().unwrap();
        assert_eq!(send(&mut owner, &changed).code, LocalCode::Binding);
    }
    let mut tampered = valid.clone();
    tampered.body = json!({"changed":true});
    assert!(owner.handle(&bytes(&tampered)).is_err());
    assert_eq!(counts.executions.load(Ordering::SeqCst), 0);
    assert_eq!(send(&mut owner, &valid).outcome, LocalOutcome::Committed);
}

#[test]
fn compiled_profile_is_required_before_owner_creation() {
    let mut b = binding(LocalRole::Body);
    b.profile_digest = "0".repeat(64);
    assert!(LocalOwner::new(b, Backend(Arc::default())).is_err());
    for uuid in [
        "garbage",
        "748D5AB4-51C1-408F-B144-A27602EDC823",
        "748d5ab4-51c1-308f-b144-a27602edc823",
    ] {
        let mut b = binding(LocalRole::Body);
        b.generation = uuid.into();
        assert!(b.validate().is_err());
    }
    binding(LocalRole::Body).validate().unwrap();
}

#[test]
fn malformed_duplicate_and_overbound_frames_have_no_execution() {
    let (mut owner, counts) = owner(LocalRole::Body);
    for frame in [
        b"{\"x\":1,\"x\":2}".to_vec(),
        b"{\"x\":NaN}".to_vec(),
        vec![b' '; MAX_LOCAL_FRAME_BYTES + 1],
        b"[]".to_vec(),
    ] {
        assert!(owner.handle(&frame).is_err());
    }
    assert_eq!(counts.executions.load(Ordering::SeqCst), 0);
    assert_eq!(
        send(
            &mut owner,
            &request(LocalRole::Body, 1, LocalOperation::Prepare, json!({}))
        )
        .outcome,
        LocalOutcome::Committed
    );
}

#[test]
fn channel_exit_retires_even_if_a_library_caller_reuses_owner() {
    for input in [vec![], vec![0], vec![0, 0, 0, 0], vec![0, 1, 0, 1]] {
        let (mut owner, counts) = owner(LocalRole::Body);
        let _ = serve_local(&mut owner, &mut Cursor::new(input), &mut Vec::new());
        assert_eq!(
            send(
                &mut owner,
                &request(LocalRole::Body, 1, LocalOperation::Prepare, json!({}))
            )
            .code,
            LocalCode::Retired
        );
        assert_eq!(counts.executions.load(Ordering::SeqCst), 0);
        assert_eq!(counts.retires.load(Ordering::SeqCst), 1);
    }
}

struct BrokenWriter;
impl Write for BrokenWriter {
    fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
        Err(std::io::Error::other("controlled lost output"))
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

#[test]
fn lost_channel_after_execution_retains_known_result_but_cannot_resume_mutations() {
    let (mut owner, counts) = owner(LocalRole::Body);
    let request = request(LocalRole::Body, 1, LocalOperation::Prepare, json!({}));
    let mut input = Vec::new();
    write_local_frame(&mut input, &bytes(&request)).unwrap();
    assert!(serve_local(&mut owner, &mut Cursor::new(input), &mut BrokenWriter).is_err());
    let response = send(&mut owner, &request);
    assert_eq!(response.outcome, LocalOutcome::Committed);
    ack(&mut owner, &response);
    let next = self::request(LocalRole::Body, 2, LocalOperation::Step, json!({}));
    assert_eq!(send(&mut owner, &next).code, LocalCode::Retired);
    assert_eq!(counts.executions.load(Ordering::SeqCst), 1);
}

#[test]
fn complete_response_tampering_and_original_request_tampering_are_detected() {
    let (mut owner, _) = owner(LocalRole::Body);
    let original = request(LocalRole::Body, 1, LocalOperation::Prepare, json!({}));
    let response = send(&mut owner, &original);
    response.verify(owner.binding(), &original).unwrap();
    let mut tampered = response.clone();
    tampered.body = json!({});
    assert!(tampered.verify(owner.binding(), &original).is_err());
    let mut wrong_original = original;
    wrong_original.body = json!({"different":true});
    assert!(response.verify(owner.binding(), &wrong_original).is_err());
}

fn plan() -> RunPlan {
    RunPlan {
        schema: "ncp.local.plan.v1".into(),
        entity_ids: vec!["a".into(), "b".into()],
        planned_steps: 4,
        step_us: 20000,
        resolution_us: 100,
        readout_delay_us: 1000,
        seed: 7,
        execution_mode: "direct_simulation".into(),
        capture_mode: "lossless_bounded".into(),
        monitor_mode: "record_only".into(),
        calibrated_posterior: false,
        observation_layout: observation_layout(),
        action_layout: action_layout(),
    }
}
fn snapshot(plan: &RunPlan) -> Snapshot {
    let mut value = Snapshot {
        schema: "ncp.local.snapshot.v1".into(),
        plan_digest: plan.digest().unwrap(),
        step: 0,
        time_us: 0,
        entity_ids: plan.entity_ids.clone(),
        available: vec![true, false],
        values: vec![0.0; 12],
        innovations: plan
            .entity_ids
            .iter()
            .enumerate()
            .map(|(i, id)| ScalarInnovation {
                entity_id: id.clone(),
                modality: "visual".into(),
                dof: 3,
                status: if i == 0 {
                    InnovationStatus::Birth
                } else {
                    InnovationStatus::Unavailable
                },
                nis: None,
                source: None,
            })
            .collect(),
        snapshot_digest: String::new(),
    };
    value.seal(plan).unwrap();
    value
}

#[test]
fn unsupported_profiles_layouts_and_clock_grids_fail_before_preparation() {
    let baseline = plan();
    baseline.validate().unwrap();
    let mut cases = Vec::new();
    let mut p = baseline.clone();
    p.calibrated_posterior = true;
    cases.push(p);
    let mut p = baseline.clone();
    p.execution_mode = "haldir_gated".into();
    cases.push(p);
    let mut p = baseline.clone();
    p.monitor_mode = "deny_tighten".into();
    cases.push(p);
    let mut p = baseline.clone();
    p.entity_ids.swap(0, 1);
    cases.push(p);
    let mut p = baseline.clone();
    p.observation_layout[0].unit = "mm".into();
    cases.push(p);
    let mut p = baseline.clone();
    p.readout_delay_us = p.step_us;
    cases.push(p);
    let mut p = baseline.clone();
    p.resolution_us = 333;
    cases.push(p);
    for p in cases {
        assert!(p.validate().is_err());
    }
}

#[test]
fn absent_observation_is_inert_and_diagnostic_missingness_is_explicit() {
    let plan = plan();
    let original = snapshot(&plan);
    original.validate(&plan).unwrap();
    let mut bad = original.clone();
    bad.values[6] = 1.0;
    assert!(bad.seal(&plan).is_err());
    let mut bad = original.clone();
    bad.innovations[1].nis = Some(0.0);
    assert!(bad.seal(&plan).is_err());
    let mut bad = original.clone();
    bad.available[1] = true;
    assert!(bad.validate(&plan).is_err());
    let mut observed = original;
    observed.innovations[0].status = InnovationStatus::Observed;
    observed.innovations[0].nis = Some(0.0);
    assert!(observed.seal(&plan).is_err());
    observed.innovations[0].source = Some(InnovationSource {
        sensor_id: "visual-a".into(),
        fusion_track_id: 1,
        fusion_sequence: 1,
        measurement_time_us: 0,
        residual_m: [0.0; 3],
        covariance_m2: [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    });
    observed.seal(&plan).unwrap();
}

#[test]
fn neural_readout_preserves_available_lane_and_exact_completed_window() {
    let plan = plan();
    let source = snapshot(&plan);
    let mut result = NeuralProposal {
        schema: "ncp.local.neural-result.v1".into(),
        plan_digest: plan.digest().unwrap(),
        step: 1,
        source_snapshot_digest: source.snapshot_digest.clone(),
        selected_modes: vec![ActionMode::Active, ActionMode::ZeroAcceleration],
        values: vec![2.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        neural_time_us: 20000,
        completed_end_us: 19000,
        window_start_us: 0,
        spike_counts: vec![1; 12],
        neural_model: "iaf_psc_alpha".into(),
    };
    result.validate(&plan, &source).unwrap();
    result.values[3] = 1.0;
    assert!(result.validate(&plan, &source).is_err());
    result.values[3] = 0.0;
    result.selected_modes[1] = ActionMode::Active;
    assert!(result.validate(&plan, &source).is_err());
    result.selected_modes[1] = ActionMode::ZeroAcceleration;
    result.window_start_us = 1;
    assert!(result.validate(&plan, &source).is_err());
    result.window_start_us = 0;
    result.completed_end_us = 20000;
    assert!(result.validate(&plan, &source).is_err());
}
