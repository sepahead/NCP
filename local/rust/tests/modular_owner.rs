#[path = "support/modular_fixture.rs"]
mod fixture;
use fixture::*;
use ncp_local::modular_buffer::*;
use ncp_local::modular_client::Client;
use ncp_local::modular_owner::*;
use ncp_local::modular_wire::*;
use std::cell::Cell;
use std::rc::Rc;

fn setup() -> (Owner<Counter>, Client<Counter>, Rc<Cell<usize>>) {
    let calls = Rc::new(Cell::new(0));
    (
        Owner::new(
            binding(),
            Counter::new(calls.clone()),
            vec![SEMANTIC.into()],
        )
        .unwrap(),
        Client::new(binding()).unwrap(),
        calls,
    )
}
fn run(
    owner: &mut Owner<Counter>,
    client: &mut Client<Counter>,
    op: AppOperation<Counter>,
) -> AppResponse<Counter> {
    let request = client.begin(op).unwrap().to_vec();
    let bytes = owner.process(&request).unwrap().to_vec();
    let response = client.observe(&bytes).unwrap();
    if response.outcome == Outcome::Committed {
        let ack = client.acknowledgement().unwrap();
        let receipt = owner.process(&ack).unwrap();
        client.observe_acknowledgement(receipt).unwrap();
    }
    response
}
fn prepare(owner: &mut Owner<Counter>, client: &mut Client<Counter>) {
    run(owner, client, Operation::Prepare(Prepare { initial: 7 }));
}
fn raw(owner: &Owner<Counter>, sequence: u64, operation: AppOperation<Counter>) -> Vec<u8> {
    Request::encode(
        binding(),
        sequence,
        Command::Execute {
            expected_predecessor_result_digest: owner.predecessor().map(str::to_owned),
            operation,
        },
    )
    .unwrap()
}
fn reseal(mut value: serde_json::Value) -> Vec<u8> {
    value["result_digest"] = typed_digest(RESPONSE_SCHEMA, &value, Some("result_digest"))
        .unwrap()
        .into();
    serde_json::to_vec(&value).unwrap()
}
#[test]
fn prepare_replay_precedes_changed_lifecycle_and_predecessor() {
    let (mut owner, mut client, calls) = setup();
    let request = client
        .begin(Operation::Prepare(Prepare { initial: 7 }))
        .unwrap()
        .to_vec();
    let first = owner.process(&request).unwrap().to_vec();
    assert_eq!(owner.lifecycle(), Lifecycle::Active);
    assert_eq!(owner.process(&request).unwrap(), first);
    assert_eq!(calls.get(), 1);
    assert_eq!(client.next_sequence(), Some(1));
    client.observe(&first).unwrap();
    assert_eq!(client.next_sequence(), Some(1));
    let ack = client.acknowledgement().unwrap();
    client
        .observe_acknowledgement(owner.process(&ack).unwrap())
        .unwrap();
    assert_eq!(client.next_sequence(), Some(2));
    let old = owner.process(&request).unwrap();
    assert_eq!(
        AppResponse::<Counter>::decode(old, &binding())
            .unwrap()
            .outcome,
        Outcome::Unavailable
    );
}
#[test]
fn exact_clean_rejection_clears_only_pending_without_sequence_or_head_change() {
    let (mut owner, mut client, calls) = setup();
    prepare(&mut owner, &mut client);
    let head = client.predecessor().unwrap().to_owned();
    let response = run(
        &mut owner,
        &mut client,
        Operation::Application(Change::Add {
            amount: 0,
            output_bytes: 0,
        }),
    );
    assert_eq!(response.outcome, Outcome::RejectedBeforeExecution);
    assert!(client.pending_request().is_none());
    assert_eq!(client.next_sequence(), Some(2));
    assert_eq!(client.predecessor(), Some(head.as_str()));
    assert_eq!(calls.get(), 1);
    assert_eq!(owner.high_water(), 1);
    assert_eq!(
        run(
            &mut owner,
            &mut client,
            Operation::Application(Change::Add {
                amount: 1,
                output_bytes: 0
            })
        )
        .outcome,
        Outcome::Committed
    );
}
#[test]
fn changed_request_cannot_authorize_response_even_when_claimed_digest_is_unchanged() {
    let (mut owner, mut client, _) = setup();
    let original = client
        .begin(Operation::Prepare(Prepare { initial: 7 }))
        .unwrap()
        .to_vec();
    let response = owner.process(&original).unwrap();
    let mut parsed = Request::<AppOperation<Counter>>::decode(&original, &binding()).unwrap();
    if let Command::Execute {
        operation: Operation::Prepare(input),
        ..
    } = &mut parsed.command
    {
        input.initial = 8;
    }
    assert!(verify_response::<Counter>(&binding(), &parsed, response).is_err());
}
#[test]
fn role_policy_rejects_resealed_forged_success_and_wrong_rejection_code() {
    let (mut owner, _, _) = setup();
    let request = raw(&owner, 1, Operation::Abort(Empty {}));
    let parsed = Request::<AppOperation<Counter>>::decode(&request, &binding()).unwrap();
    let original = owner.process(&request).unwrap().to_vec();
    assert_eq!(
        verify_response::<Counter>(&binding(), &parsed, &original)
            .unwrap()
            .code,
        Code::Role
    );
    let mut value: serde_json::Value = serde_json::from_slice(&original).unwrap();
    value["code"] = "state".into();
    assert!(verify_response::<Counter>(&binding(), &parsed, &reseal(value.clone())).is_err());
    value["code"] = "ok".into();
    value["outcome"] = "committed".into();
    value["body"] = serde_json::json!({"kind":"aborted"});
    assert!(verify_response::<Counter>(&binding(), &parsed, &reseal(value)).is_err());
}
#[test]
fn panic_invalid_output_and_unfulfilled_reservation_retire_after_consumption() {
    for action in [
        Change::Panic,
        Change::BackendError,
        Change::InvalidOutput,
        Change::OmitOutput,
        Change::IgnoreWriteError,
    ] {
        let (mut owner, mut client, calls) = setup();
        prepare(&mut owner, &mut client);
        let response = run(&mut owner, &mut client, Operation::Application(action));
        assert_eq!(response.outcome, Outcome::Indeterminate);
        assert_eq!(owner.high_water(), 2);
        assert_eq!(owner.lifecycle(), Lifecycle::Retired);
        assert!(client.is_retired());
        assert!(client.pending_request().is_some());
        assert_eq!(calls.get(), 2);
        assert!(owner.retained().is_some());
    }
}

#[test]
fn application_admission_cannot_change_the_installed_role_policy() {
    let (mut owner, mut client, calls) = setup();
    prepare(&mut owner, &mut client);
    let result = run(
        &mut owner,
        &mut client,
        Operation::Application(Change::AdmissionRole),
    );
    assert_eq!(result.code, Code::InvalidInput);
    assert_eq!(result.outcome, Outcome::RejectedBeforeExecution);
    assert_eq!(calls.get(), 1);
    assert_eq!(owner.high_water(), 1);
    assert_eq!(
        run(
            &mut owner,
            &mut client,
            Operation::Application(Change::Add {
                amount: 1,
                output_bytes: 0
            })
        )
        .outcome,
        Outcome::Committed
    );
}
#[test]
fn finish_has_empty_precondition_and_cannot_allocate_fresh_outputs() {
    let (mut owner, mut client, calls) = setup();
    prepare(&mut owner, &mut client);
    let rejection = run(
        &mut owner,
        &mut client,
        Operation::Finish(Finish {
            allocate: false,
            demand: true,
        }),
    );
    assert_eq!(rejection.code, Code::Capacity);
    assert_eq!(calls.get(), 1);
    let failed = run(
        &mut owner,
        &mut client,
        Operation::Finish(Finish {
            allocate: true,
            demand: false,
        }),
    );
    assert_eq!(failed.outcome, Outcome::Indeterminate);
    assert_eq!(owner.lifecycle(), Lifecycle::Retired);
    let (mut owner, mut client, _) = setup();
    prepare(&mut owner, &mut client);
    assert_eq!(
        run(
            &mut owner,
            &mut client,
            Operation::Finish(Finish {
                allocate: false,
                demand: false
            })
        )
        .outcome,
        Outcome::Committed
    );
    assert_eq!(owner.lifecycle(), Lifecycle::Finished);
    assert_eq!(owner.usage().live_slots, 0);
}
#[test]
fn buffer_ack_lifetime_read_manifest_join_and_release_replay_are_exact() {
    let (mut owner, mut client, _) = setup();
    prepare(&mut owner, &mut client);
    let output = run(
        &mut owner,
        &mut client,
        Operation::Application(Change::Add {
            amount: 1,
            output_bytes: 4,
        }),
    );
    let Body::Application {
        data: Output {
            manifest: Some(manifest),
            ..
        },
    } = output.body
    else {
        panic!("manifest")
    };
    assert_eq!(owner.usage().live_slots, 1);
    let finish = run(
        &mut owner,
        &mut client,
        Operation::Finish(Finish {
            allocate: false,
            demand: false,
        }),
    );
    assert_eq!(finish.code, Code::State);
    let wrong = run(
        &mut owner,
        &mut client,
        Operation::BufferRead(ReadInput {
            reference: manifest.reference(),
            expected_manifest_digest: "0".repeat(64),
            index: 0,
        }),
    );
    assert_eq!(wrong.outcome, Outcome::RejectedBeforeExecution);
    let request = client
        .begin(Operation::BufferRead(ReadInput {
            reference: manifest.reference(),
            expected_manifest_digest: manifest.manifest_digest.clone(),
            index: 0,
        }))
        .unwrap()
        .to_vec();
    let response = owner.process(&request).unwrap().to_vec();
    let parsed = Request::<AppOperation<Counter>>::decode(&request, &binding()).unwrap();
    let mut changed: serde_json::Value = serde_json::from_slice(&response).unwrap();
    changed["body"]["data"]["manifest_digest"] = "b".repeat(64).into();
    assert!(verify_response::<Counter>(&binding(), &parsed, &reseal(changed)).is_err());
    client.observe(&response).unwrap();
    let ack = client.acknowledgement().unwrap();
    client
        .observe_acknowledgement(owner.process(&ack).unwrap())
        .unwrap();
    let release = client
        .begin(Operation::BufferRelease(ReferenceInput {
            reference: manifest.reference(),
        }))
        .unwrap()
        .to_vec();
    let released = owner.process(&release).unwrap().to_vec();
    assert_eq!(owner.usage().live_slots, 0);
    assert_eq!(owner.process(&release).unwrap(), released);
    client.observe(&released).unwrap();
    let ack = client.acknowledgement().unwrap();
    client
        .observe_acknowledgement(owner.process(&ack).unwrap())
        .unwrap();
    let stale = run(
        &mut owner,
        &mut client,
        Operation::BufferRead(ReadInput {
            reference: manifest.reference(),
            expected_manifest_digest: manifest.manifest_digest,
            index: 0,
        }),
    );
    assert_eq!(stale.code, Code::BufferUnavailable);
}
#[test]
fn previous_ack_stamp_does_not_release_newer_owed_result() {
    let (mut owner, mut client, _) = setup();
    let request = client
        .begin(Operation::Prepare(Prepare { initial: 1 }))
        .unwrap()
        .to_vec();
    client.observe(owner.process(&request).unwrap()).unwrap();
    let old_ack = client.acknowledgement().unwrap();
    client
        .observe_acknowledgement(owner.process(&old_ack).unwrap())
        .unwrap();
    let next = client
        .begin(Operation::Application(Change::Add {
            amount: 1,
            output_bytes: 0,
        }))
        .unwrap()
        .to_vec();
    let owed = owner.process(&next).unwrap().to_vec();
    assert_eq!(
        AppResponse::<Counter>::decode(owner.process(&old_ack).unwrap(), &binding())
            .unwrap()
            .outcome,
        Outcome::Acknowledged
    );
    assert_eq!(owner.retained().unwrap(), owed);
    client.observe(&owed).unwrap();
    let ack = client.acknowledgement().unwrap();
    client
        .observe_acknowledgement(owner.process(&ack).unwrap())
        .unwrap();
    assert_eq!(
        AppResponse::<Counter>::decode(owner.process(&old_ack).unwrap(), &binding())
            .unwrap()
            .outcome,
        Outcome::Unavailable
    );
}
#[test]
fn malformed_frame_retires_without_fabricated_correlation_and_eof_also_retires() {
    let (mut owner, _, _) = setup();
    assert!(owner.process(br#"{"sequence":1,"sequence":1}"#).is_err());
    assert_eq!(owner.high_water(), 0);
    assert!(owner.retained().is_none());
    let (mut owner, _, _) = setup();
    serve(&mut owner, &mut &b""[..], &mut Vec::new()).unwrap();
    assert!(owner
        .process(&raw(&owner, 1, Operation::Prepare(Prepare { initial: 1 })))
        .is_err());
}
#[test]
fn lost_response_preserves_pending_and_forbids_dispatch_retry() {
    let (_, mut client, _) = setup();
    client
        .begin(Operation::Prepare(Prepare { initial: 1 }))
        .unwrap();
    let original = client.pending_request().unwrap().to_vec();
    assert!(client.dispatch(&mut &b""[..], &mut Vec::new()).is_err());
    assert!(client.is_retired());
    assert_eq!(client.pending_request().unwrap(), original);
    assert!(client.result_query().is_err());
}

#[test]
fn import_capacity_and_incomplete_seal_rejection_preserve_owned_prefix() {
    let (mut owner, mut client, _) = setup();
    prepare(&mut owner, &mut client);
    let mut source_binding = binding();
    source_binding.generation = "44444444-4444-4444-8444-444444444444".into();
    let mut source_pool = BufferPool::new(source_binding.clone(), vec![SEMANTIC.into()]).unwrap();
    let context =
        TrustedHostCreationContext::new(source_binding.clone(), "b".repeat(64), None).unwrap();
    let source = source_pool.publish(&context, SEMANTIC, b"abc").unwrap();
    let usage = owner.usage();
    let denied = run(
        &mut owner,
        &mut client,
        Operation::BufferImportBegin(Import {
            manifest: source.clone(),
            source: source_binding.clone(),
            label: "x".repeat(1_000),
        }),
    );
    assert_eq!(denied.code, Code::Capacity);
    assert_eq!(owner.usage(), usage);
    let response = run(
        &mut owner,
        &mut client,
        Operation::BufferImportBegin(Import {
            manifest: source.clone(),
            source: source_binding,
            label: "owned".into(),
        }),
    );
    let Body::ImportReserved { reference } = response.body else {
        panic!("import")
    };
    let import_request_digest = response.request_digest;
    let high_water = owner.high_water();
    let usage = owner.usage();
    let incomplete = run(
        &mut owner,
        &mut client,
        Operation::BufferSeal(SealInput {
            reference: reference.clone(),
            expected_import_request_digest: import_request_digest.clone(),
            expected_source_manifest_digest: source.manifest_digest.clone(),
        }),
    );
    assert_eq!(incomplete.outcome, Outcome::RejectedBeforeExecution);
    assert_eq!(owner.high_water(), high_water);
    assert_eq!(owner.usage(), usage);
    let chunk = source_pool.read(&source.reference(), 0).unwrap();
    run(
        &mut owner,
        &mut client,
        Operation::BufferAppend(AppendInput {
            reference: reference.clone(),
            chunk,
        }),
    );
    let result = run(
        &mut owner,
        &mut client,
        Operation::BufferSeal(SealInput {
            reference: reference.clone(),
            expected_import_request_digest: import_request_digest,
            expected_source_manifest_digest: source.manifest_digest.clone(),
        }),
    );
    let Body::ImportSealed { data, manifest } = result.body else {
        panic!("seal")
    };
    assert_eq!((data.byte_length, data.label.as_str()), (3, "owned"));
    assert_eq!(owner.usage().incomplete_slots, 0);
    let read = run(
        &mut owner,
        &mut client,
        Operation::BufferRead(ReadInput {
            reference: reference.clone(),
            expected_manifest_digest: manifest.manifest_digest,
            index: 0,
        }),
    );
    let Body::Chunk { data } = read.body else {
        panic!("read")
    };
    assert_eq!(data.decoded().unwrap(), b"abc");
    run(
        &mut owner,
        &mut client,
        Operation::BufferRelease(ReferenceInput { reference }),
    );
    assert_eq!(owner.usage().live_slots, 0);
}

#[test]
fn missing_optional_member_does_not_survive_lossless_typed_rejoin() {
    let (mut owner, mut client, _) = setup();
    let original = client
        .begin(Operation::Prepare(Prepare { initial: 7 }))
        .unwrap()
        .to_vec();
    let mut value: serde_json::Value = serde_json::from_slice(&original).unwrap();
    value["command"]
        .as_object_mut()
        .unwrap()
        .remove("expected_predecessor_result_digest");
    value["request_digest"] = typed_digest(REQUEST_SCHEMA, &value, Some("request_digest"))
        .unwrap()
        .into();
    assert!(Request::<AppOperation<Counter>>::decode(
        &serde_json::to_vec(&value).unwrap(),
        &binding()
    )
    .is_err());
    let response = owner.process(&original).unwrap();
    let mut value: serde_json::Value = serde_json::from_slice(response).unwrap();
    value["body"]["data"]
        .as_object_mut()
        .unwrap()
        .remove("manifest");
    assert!(AppResponse::<Counter>::decode(&reseal(value), &binding()).is_err());
}

#[test]
fn lost_ack_and_partial_response_leave_pending_evidence_without_retry() {
    let (mut owner, mut client, _) = setup();
    let original = client
        .begin(Operation::Prepare(Prepare { initial: 7 }))
        .unwrap()
        .to_vec();
    client.observe(owner.process(&original).unwrap()).unwrap();
    assert!(client
        .dispatch_acknowledgement(&mut &b""[..], &mut Vec::new())
        .is_err());
    assert!(client.is_retired());
    assert_eq!(client.pending_request().unwrap(), original);
    assert!(client.acknowledgement().is_err());
    let (mut owner, mut client, _) = setup();
    let original = client
        .begin(Operation::Prepare(Prepare { initial: 7 }))
        .unwrap()
        .to_vec();
    let mut framed = Vec::new();
    ncp_local::local::write_local_frame(&mut framed, owner.process(&original).unwrap()).unwrap();
    framed.pop();
    assert!(client
        .dispatch(&mut framed.as_slice(), &mut Vec::new())
        .is_err());
    assert!(client.is_retired());
    assert_eq!(client.pending_request().unwrap(), original);
}

#[test]
fn pending_conflict_query_mismatch_and_wrong_ack_leave_the_owed_bytes_unchanged() {
    let (mut owner, mut client, calls) = setup();
    let original = client
        .begin(Operation::Prepare(Prepare { initial: 7 }))
        .unwrap()
        .to_vec();
    let owed = owner.process(&original).unwrap().to_vec();
    let conflict = raw(&owner, 1, Operation::Prepare(Prepare { initial: 8 }));
    assert_eq!(
        AppResponse::<Counter>::decode(owner.process(&conflict).unwrap(), &binding())
            .unwrap()
            .code,
        Code::Conflict
    );
    let next = raw(
        &owner,
        2,
        Operation::Application(Change::Add {
            amount: 1,
            output_bytes: 0,
        }),
    );
    assert_eq!(
        AppResponse::<Counter>::decode(owner.process(&next).unwrap(), &binding())
            .unwrap()
            .code,
        Code::ResultPending
    );
    let query = Request::<AppOperation<Counter>>::encode(
        binding(),
        1,
        Command::Result {
            original_request_digest: "a".repeat(64),
        },
    )
    .unwrap();
    assert_eq!(
        AppResponse::<Counter>::decode(owner.process(&query).unwrap(), &binding())
            .unwrap()
            .outcome,
        Outcome::Unavailable
    );
    client.observe(&owed).unwrap();
    let mut ack: serde_json::Value =
        serde_json::from_slice(&client.acknowledgement().unwrap()).unwrap();
    ack["command"]["result_digest"] = "a".repeat(64).into();
    ack["request_digest"] = typed_digest(REQUEST_SCHEMA, &ack, Some("request_digest"))
        .unwrap()
        .into();
    let ack = serde_json::to_vec(&ack).unwrap();
    assert_eq!(
        AppResponse::<Counter>::decode(owner.process(&ack).unwrap(), &binding())
            .unwrap()
            .code,
        Code::Conflict
    );
    assert_eq!(owner.retained().unwrap(), owed);
    assert_eq!(calls.get(), 1);
}

#[test]
fn unknown_generation_and_bad_sequence_fail_before_application_decoder() {
    use serde::{Deserialize, Deserializer, Serialize};
    use std::sync::atomic::{AtomicUsize, Ordering};
    static DECODED: AtomicUsize = AtomicUsize::new(0);
    #[derive(Serialize)]
    struct Marker;
    impl<'de> Deserialize<'de> for Marker {
        fn deserialize<D: Deserializer<'de>>(_: D) -> Result<Self, D::Error> {
            DECODED.fetch_add(1, Ordering::SeqCst);
            Ok(Marker)
        }
    }
    let request = Request::<Empty>::encode(
        binding(),
        1,
        Command::Execute {
            expected_predecessor_result_digest: None,
            operation: Empty {},
        },
    )
    .unwrap();
    let mut value: serde_json::Value = serde_json::from_slice(&request).unwrap();
    value["binding"]["generation"] = "44444444-4444-4444-8444-444444444444".into();
    value["request_digest"] = typed_digest(REQUEST_SCHEMA, &value, Some("request_digest"))
        .unwrap()
        .into();
    assert!(Request::<Marker>::decode(&serde_json::to_vec(&value).unwrap(), &binding()).is_err());
    value["binding"]["generation"] = binding().generation.into();
    value["sequence"] = serde_json::json!(1.0);
    value["request_digest"] = typed_digest(REQUEST_SCHEMA, &value, Some("request_digest"))
        .unwrap()
        .into();
    assert!(Request::<Marker>::decode(&serde_json::to_vec(&value).unwrap(), &binding()).is_err());
    assert_eq!(DECODED.load(Ordering::SeqCst), 0);
}

fn rehash_adversarial_manifest(value: &mut serde_json::Value) {
    use sha2::{Digest, Sha256};
    fn project(value: &serde_json::Value, bytes: &mut Vec<u8>) {
        match value {
            serde_json::Value::Null => bytes.push(0),
            serde_json::Value::Number(number) => {
                bytes.push(3);
                bytes.extend_from_slice(&number.as_f64().unwrap().to_bits().to_be_bytes());
            }
            serde_json::Value::String(text) => {
                bytes.push(4);
                bytes.extend_from_slice(&(text.len() as u64).to_be_bytes());
                bytes.extend_from_slice(text.as_bytes());
            }
            serde_json::Value::Object(object) => {
                bytes.push(6);
                bytes.extend_from_slice(&(object.len() as u64).to_be_bytes());
                let mut rows: Vec<_> = object.iter().collect();
                rows.sort_unstable_by_key(|(key, _)| key.as_bytes());
                for (key, child) in rows {
                    project(&serde_json::Value::String(key.clone()), bytes);
                    project(child, bytes);
                }
            }
            _ => panic!("closed manifest has no other scalar types"),
        }
    }
    value.as_object_mut().unwrap().remove("manifest_digest");
    let mut bytes = b"ncp.modular.buffer-manifest.v1\0".to_vec();
    project(value, &mut bytes);
    let digest: String = Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    value["manifest_digest"] = digest.into();
}

#[test]
fn seal_source_and_receiver_substitutions_fail_even_when_both_hashes_are_recomputed() {
    let (mut owner, mut client, _) = setup();
    prepare(&mut owner, &mut client);
    let mut origin = binding();
    origin.generation = "44444444-4444-4444-8444-444444444444".into();
    let mut pool = BufferPool::new(origin.clone(), vec![SEMANTIC.into()]).unwrap();
    let source = pool
        .publish(
            &TrustedHostCreationContext::new(origin.clone(), "b".repeat(64), None).unwrap(),
            SEMANTIC,
            b"abc",
        )
        .unwrap();
    let imported = run(
        &mut owner,
        &mut client,
        Operation::BufferImportBegin(Import {
            manifest: source.clone(),
            source: origin.clone(),
            label: "source-bound".into(),
        }),
    );
    let Body::ImportReserved { reference } = imported.body else {
        panic!("import")
    };
    run(
        &mut owner,
        &mut client,
        Operation::BufferAppend(AppendInput {
            reference: reference.clone(),
            chunk: pool.read(&source.reference(), 0).unwrap(),
        }),
    );
    let before = owner.usage();
    for (creation, source_digest) in [
        ("0".repeat(64), source.manifest_digest.clone()),
        (imported.request_digest.clone(), "0".repeat(64)),
    ] {
        let result = run(
            &mut owner,
            &mut client,
            Operation::BufferSeal(SealInput {
                reference: reference.clone(),
                expected_import_request_digest: creation,
                expected_source_manifest_digest: source_digest,
            }),
        );
        assert_eq!(result.outcome, Outcome::RejectedBeforeExecution);
        assert_eq!(owner.usage(), before);
    }
    let request = client
        .begin(Operation::BufferSeal(SealInput {
            reference: reference.clone(),
            expected_import_request_digest: imported.request_digest,
            expected_source_manifest_digest: source.manifest_digest,
        }))
        .unwrap()
        .to_vec();
    let original = Request::<AppOperation<Counter>>::decode(&request, &binding()).unwrap();
    let result = owner.process(&request).unwrap().to_vec();
    for (field, altered) in [
        ("creating_request_digest", serde_json::json!("0".repeat(64))),
        (
            "imported_manifest_digest",
            serde_json::json!("0".repeat(64)),
        ),
        ("buffer_id", serde_json::json!(reference.buffer_id + 1)),
    ] {
        let mut value: serde_json::Value = serde_json::from_slice(&result).unwrap();
        value["body"]["manifest"][field] = altered;
        rehash_adversarial_manifest(&mut value["body"]["manifest"]);
        assert!(verify_response::<Counter>(&binding(), &original, &reseal(value)).is_err());
    }
    let mut value: serde_json::Value = serde_json::from_slice(&result).unwrap();
    value["body"]["manifest"]["binding"]["generation"] = origin.generation.into();
    rehash_adversarial_manifest(&mut value["body"]["manifest"]);
    assert!(verify_response::<Counter>(&binding(), &original, &reseal(value)).is_err());
    client.observe(&result).unwrap();
    client
        .observe_acknowledgement(owner.process(&client.acknowledgement().unwrap()).unwrap())
        .unwrap();
    run(
        &mut owner,
        &mut client,
        Operation::BufferRelease(ReferenceInput { reference }),
    );
    assert_eq!(owner.usage().live_slots, 0);
}

mod egress {
    use super::*;
    use serde::{de::DeserializeOwned, Deserialize, Serialize};
    use std::cell::RefCell;

    // Closed test application with numerical results. It owns no external engine.
    struct NumberApp<V> {
        value: Rc<RefCell<V>>,
        calls: Rc<Cell<usize>>,
    }
    impl<V: Serialize + DeserializeOwned + PartialEq + Clone> Contract for NumberApp<V> {
        type Prepare = fixture::Prepare;
        type Command = fixture::Change;
        type ImportDescriptor = fixture::Import;
        type ImportMetadata = fixture::Metadata;
        type Finish = fixture::Finish;
        type Result = V;
        type Imported = V;
        type Terminal = V;
        fn descriptor() -> &'static [u8] {
            br#"{"schema":"ncp.test.numeric-egress.v1","status":"test-only","data_shapes":"closed numerical egress test types"}"#
        }
        fn allows(_: OperationName) -> bool {
            true
        }
        fn check_input(_: &AppOperation<Self>) -> Result<(), ModularError> {
            Ok(())
        }
        fn check_response(
            _: &AppOperation<Self>,
            _: &AppBody<Self>,
            _: &ExecutionContext,
        ) -> Result<(), ModularError> {
            Ok(())
        }
        fn check_import_metadata(
            descriptor: &fixture::Import,
            metadata: &fixture::Metadata,
        ) -> Result<(), ModularError> {
            Counter::check_import_metadata(descriptor, metadata)
        }
    }
    impl<V: Serialize + DeserializeOwned + PartialEq + Clone> Application for NumberApp<V> {
        fn admit(
            &self,
            _: &AppOperation<Self>,
            _: &AdmissionView<'_>,
        ) -> Result<AdmissionDemand, Code> {
            Ok(AdmissionDemand::default())
        }
        fn execute(
            &mut self,
            op: &AppOperation<Self>,
            _: &mut ExecutionPermit<'_, '_>,
        ) -> Result<ApplicationOutput<V, V>, Diagnostic> {
            self.calls.set(self.calls.get() + 1);
            Ok(if matches!(op, Operation::Finish(_)) {
                ApplicationOutput::Terminal(self.value.borrow().clone())
            } else {
                ApplicationOutput::Result(self.value.borrow().clone())
            })
        }
        fn split_import<'a>(
            &'a self,
            descriptor: &'a fixture::Import,
        ) -> Result<ImportSource<'a, fixture::Metadata>, Code> {
            Ok(ImportSource {
                manifest: &descriptor.manifest,
                expected_binding: &descriptor.source,
                metadata: fixture::Metadata {
                    byte_length: descriptor.manifest.byte_length,
                    label: descriptor.label.clone(),
                },
            })
        }
        fn validate_import(
            &self,
            _: &fixture::Metadata,
            _: &BufferManifest,
            _: &[u8],
        ) -> Result<V, Code> {
            self.calls.set(self.calls.get() + 1);
            Ok(self.value.borrow().clone())
        }
    }
    fn number_binding<V: Serialize + DeserializeOwned + PartialEq + Clone>() -> BufferBinding {
        let mut result = binding();
        result.application_digest = typed_digest(
            PROFILE_DOMAIN,
            &parse_value(NumberApp::<V>::descriptor()).unwrap(),
            None,
        )
        .unwrap();
        result
    }
    fn call<V: Serialize + DeserializeOwned + PartialEq + Clone>(
        owner: &mut Owner<NumberApp<V>>,
        client: &mut Client<NumberApp<V>>,
        operation: AppOperation<NumberApp<V>>,
    ) -> AppResponse<NumberApp<V>> {
        let request = client.begin(operation).unwrap().to_vec();
        let wire = owner.process(&request).unwrap().to_vec();
        assert_eq!(owner.process(&request).unwrap(), wire);
        let response = client.observe(&wire).unwrap();
        if response.outcome == Outcome::Committed {
            client
                .observe_acknowledgement(owner.process(&client.acknowledgement().unwrap()).unwrap())
                .unwrap();
        }
        response
    }
    #[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
    #[serde(deny_unknown_fields)]
    struct Number {
        value: Option<f64>,
    }

    #[test]
    fn finite_optional_and_nonfinite_outputs_rejoin_in_every_application_slot() {
        for phase in ["prepare", "application", "import", "finish"] {
            for value in [
                Some(1.25),
                Some(-0.0),
                None,
                Some(f64::NAN),
                Some(f64::INFINITY),
                Some(f64::NEG_INFINITY),
            ] {
                let stored = Rc::new(RefCell::new(Number { value: Some(7.0) }));
                let calls = Rc::new(Cell::new(0));
                let binding = number_binding::<Number>();
                let mut owner = Owner::new(
                    binding.clone(),
                    NumberApp {
                        value: stored.clone(),
                        calls: calls.clone(),
                    },
                    vec![SEMANTIC.into()],
                )
                .unwrap();
                let mut client = Client::<NumberApp<Number>>::new(binding.clone()).unwrap();
                if phase != "prepare" {
                    call(
                        &mut owner,
                        &mut client,
                        Operation::Prepare(fixture::Prepare { initial: 7 }),
                    );
                }
                let operation = match phase {
                    "prepare" => Operation::Prepare(fixture::Prepare { initial: 7 }),
                    "application" => Operation::Application(fixture::Change::Add {
                        amount: 1,
                        output_bytes: 0,
                    }),
                    "finish" => Operation::Finish(fixture::Finish {
                        allocate: false,
                        demand: false,
                    }),
                    "import" => {
                        let mut source_binding = binding.clone();
                        source_binding.generation = "44444444-4444-4444-8444-444444444444".into();
                        let mut pool =
                            BufferPool::new(source_binding.clone(), vec![SEMANTIC.into()]).unwrap();
                        let context = TrustedHostCreationContext::new(
                            source_binding.clone(),
                            "b".repeat(64),
                            None,
                        )
                        .unwrap();
                        let source = pool.publish(&context, SEMANTIC, b"abc").unwrap();
                        let imported = call(
                            &mut owner,
                            &mut client,
                            Operation::BufferImportBegin(fixture::Import {
                                manifest: source.clone(),
                                source: source_binding,
                                label: "input".into(),
                            }),
                        );
                        let Body::ImportReserved { reference } = imported.body else {
                            panic!("import")
                        };
                        call(
                            &mut owner,
                            &mut client,
                            Operation::BufferAppend(AppendInput {
                                reference: reference.clone(),
                                chunk: pool.read(&source.reference(), 0).unwrap(),
                            }),
                        );
                        Operation::BufferSeal(SealInput {
                            reference,
                            expected_import_request_digest: imported.request_digest,
                            expected_source_manifest_digest: source.manifest_digest,
                        })
                    }
                    _ => unreachable!(),
                };
                *stored.borrow_mut() = Number { value };
                let sequence = owner.high_water() + 1;
                let before = calls.get();
                let result = call(&mut owner, &mut client, operation);
                let expected = if value.is_some_and(|number| !number.is_finite()) {
                    Outcome::Indeterminate
                } else {
                    Outcome::Committed
                };
                assert_eq!(result.outcome, expected, "{phase} {value:?}");
                assert_eq!(owner.high_water(), sequence);
                assert_eq!(calls.get(), before + 1);
                if expected == Outcome::Indeterminate {
                    assert_eq!(owner.lifecycle(), Lifecycle::Retired);
                    assert!(client.is_retired());
                    assert!(client.pending_request().is_some());
                } else {
                    let actual = match result.body {
                        Body::Prepared { data }
                        | Body::Application { data }
                        | Body::ImportSealed { data, .. }
                        | Body::Finished { data } => data,
                        _ => panic!("output"),
                    };
                    assert_eq!(actual.value.map(f64::to_bits), value.map(f64::to_bits));
                }
            }
        }
    }
    #[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
    #[serde(deny_unknown_fields)]
    struct NormalizingNumber {
        #[serde(deserialize_with = "absolute")]
        value: f64,
    }
    fn absolute<'de, D: serde::Deserializer<'de>>(decoder: D) -> Result<f64, D::Error> {
        Ok(f64::deserialize(decoder)?.abs())
    }
    #[test]
    fn outgoing_decoder_cannot_normalize_sign_or_values_before_commit() {
        for value in [0.0_f64, 1.25, -0.0, -1.25] {
            let binding = number_binding::<NormalizingNumber>();
            let mut owner = Owner::new(
                binding.clone(),
                NumberApp {
                    value: Rc::new(RefCell::new(NormalizingNumber { value })),
                    calls: Rc::new(Cell::new(0)),
                },
                vec![SEMANTIC.into()],
            )
            .unwrap();
            let mut client = Client::new(binding).unwrap();
            let response = call(
                &mut owner,
                &mut client,
                Operation::Prepare(fixture::Prepare { initial: 7 }),
            );
            assert_eq!(
                response.outcome,
                if value.is_sign_negative() {
                    Outcome::Indeterminate
                } else {
                    Outcome::Committed
                }
            );
            assert_eq!(owner.high_water(), 1);
        }
    }
    #[test]
    fn outgoing_plain_float_decoder_rejects_nonfinite_null_conversion() {
        for value in [1.25_f64, f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let binding = number_binding::<f64>();
            let mut owner = Owner::new(
                binding.clone(),
                NumberApp {
                    value: Rc::new(RefCell::new(value)),
                    calls: Rc::new(Cell::new(0)),
                },
                vec![SEMANTIC.into()],
            )
            .unwrap();
            let mut client = Client::new(binding).unwrap();
            let response = call(
                &mut owner,
                &mut client,
                Operation::Prepare(fixture::Prepare { initial: 7 }),
            );
            assert_eq!(
                response.outcome,
                if value.is_finite() {
                    Outcome::Committed
                } else {
                    Outcome::Indeterminate
                }
            );
        }
    }
}

// A real byte consumer for the generic lease seam. This test contract is not an
// installed sensor, renderer, controller, or scientific application profile.
mod input_leases {
    use super::*;
    use serde::{Deserialize, Serialize};

    const DESCRIPTOR: &[u8] = br#"{"schema":"ncp.test.tensor-consumer.rust.v1","status":"test-only","dtype":"f32le","operation":"sum_then_accumulate"}"#;
    #[derive(Clone, Debug, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct TensorImport {
        manifest: BufferManifest,
        source: BufferBinding,
        shape: [usize; 2],
        dtype: String,
    }
    #[derive(Debug, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Metadata {
        shape: [usize; 2],
        dtype: String,
    }
    #[derive(Clone, Debug, Serialize, Deserialize)]
    #[serde(rename_all = "snake_case")]
    enum Action {
        Sum,
        ReadUnnamed,
        IgnoreReadError,
    }
    #[derive(Debug, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Consume {
        inputs: Vec<InputSpec>,
        output_bytes: usize,
        action: Action,
    }
    #[derive(Debug, Serialize, Deserialize)]
    #[serde(deny_unknown_fields)]
    struct End {
        inputs: Vec<InputSpec>,
    }
    #[derive(Debug, Serialize, Deserialize, PartialEq)]
    #[serde(deny_unknown_fields)]
    struct TensorResult {
        accumulated_sum: f64,
        source_manifests: Vec<String>,
        output_manifest: Option<BufferManifest>,
    }
    struct Consumer {
        calls: Rc<Cell<usize>>,
        total: Rc<Cell<f64>>,
    }
    impl Contract for Consumer {
        type Prepare = Empty;
        type Command = Consume;
        type ImportDescriptor = TensorImport;
        type ImportMetadata = Metadata;
        type Finish = End;
        type Result = TensorResult;
        type Imported = TensorResult;
        type Terminal = TensorResult;
        fn descriptor() -> &'static [u8] {
            DESCRIPTOR
        }
        fn allows(_: OperationName) -> bool {
            true
        }
        fn check_input(op: &AppOperation<Self>) -> Result<(), ModularError> {
            match op {
                Operation::Application(input)
                    if input.inputs.len() > 25 || !matches!(input.output_bytes, 0 | 4) =>
                {
                    Err(ModularError::Wire)
                }
                Operation::Finish(input) if input.inputs.len() > 25 => Err(ModularError::Wire),
                Operation::BufferImportBegin(input)
                    if input.dtype != "f32le"
                        || input.shape.iter().any(|&n| !(1..=64).contains(&n))
                        || input.manifest.byte_length
                            != input.shape.iter().product::<usize>() * 4 =>
                {
                    Err(ModularError::Wire)
                }
                _ => Ok(()),
            }
        }
        fn check_response(
            op: &AppOperation<Self>,
            body: &AppBody<Self>,
            context: &ExecutionContext,
        ) -> Result<(), ModularError> {
            let data = match body {
                Body::Prepared { data }
                | Body::Application { data }
                | Body::ImportSealed { data, .. }
                | Body::Finished { data } => data,
                _ => return Ok(()),
            };
            if !data.accumulated_sum.is_finite() || data.source_manifests.len() > LIVE_SLOTS {
                return Err(ModularError::Wire);
            }
            if let Operation::Application(input) = op {
                if data.source_manifests
                    != input
                        .inputs
                        .iter()
                        .map(|s| s.expected_manifest_digest.clone())
                        .collect::<Vec<_>>()
                    || data.output_manifest.as_ref().map_or(0, |m| m.byte_length)
                        != input.output_bytes
                {
                    return Err(ModularError::Binding);
                }
            }
            if let Some(manifest) = &data.output_manifest {
                manifest
                    .verify(context.binding())
                    .map_err(|_| ModularError::Binding)?;
                if manifest.creating_request_digest != context.request_digest()
                    || manifest.causal_predecessor.as_deref() != context.predecessor()
                {
                    return Err(ModularError::Binding);
                }
            }
            Ok(())
        }
        fn check_import_metadata(
            descriptor: &TensorImport,
            metadata: &Metadata,
        ) -> Result<(), ModularError> {
            if descriptor.shape != metadata.shape || descriptor.dtype != metadata.dtype {
                Err(ModularError::Binding)
            } else {
                Ok(())
            }
        }
    }
    impl Consumer {
        fn result(&self) -> TensorResult {
            TensorResult {
                accumulated_sum: self.total.get(),
                source_manifests: vec![],
                output_manifest: None,
            }
        }
    }
    impl Application for Consumer {
        fn admit(
            &self,
            op: &AppOperation<Self>,
            _: &AdmissionView<'_>,
        ) -> Result<AdmissionDemand, Code> {
            let (inputs, bytes) = match op {
                Operation::Application(input) => (input.inputs.clone(), input.output_bytes),
                Operation::Finish(input) => (input.inputs.clone(), 0),
                _ => (vec![], 0),
            };
            Ok(AdmissionDemand {
                inputs,
                outputs: if bytes == 0 {
                    vec![]
                } else {
                    vec![OutputSpec {
                        semantic_digest: SEMANTIC.into(),
                        byte_length: bytes,
                    }]
                },
            })
        }
        fn execute(
            &mut self,
            op: &AppOperation<Self>,
            permit: &mut ExecutionPermit<'_, '_>,
        ) -> Result<ApplicationOutput<TensorResult, TensorResult>, Diagnostic> {
            self.calls.set(self.calls.get() + 1);
            match op {
                Operation::Prepare(_) => Ok(ApplicationOutput::Result(self.result())),
                Operation::Application(input) => {
                    if !matches!(input.action, Action::Sum) {
                        let failed = permit.input(input.inputs.len()).is_err();
                        if matches!(input.action, Action::ReadUnnamed) || !failed {
                            return Err(Diagnostic::Backend);
                        }
                    }
                    let mut result = self.result();
                    let views = (0..input.inputs.len())
                        .map(|slot| permit.input(slot).map_err(|_| Diagnostic::Backend))
                        .collect::<Result<Vec<_>, _>>()?;
                    for view in &views {
                        // Actual f32le values are read only during entered execution.
                        for row in view.bytes().chunks_exact(4) {
                            result.accumulated_sum +=
                                f64::from(f32::from_le_bytes(row.try_into().unwrap()));
                        }
                        result
                            .source_manifests
                            .push(view.manifest().manifest_digest.clone());
                    }
                    drop(views);
                    self.total.set(result.accumulated_sum);
                    if input.output_bytes != 0 {
                        let value = self.total.get() as f32;
                        if !value.is_finite() {
                            return Err(Diagnostic::InvalidOutput);
                        }
                        permit
                            .write_output(0, 0, &value.to_le_bytes())
                            .map_err(|_| Diagnostic::Backend)?;
                        result.output_manifest =
                            Some(permit.seal_output(0).map_err(|_| Diagnostic::Backend)?);
                    }
                    Ok(ApplicationOutput::Result(result))
                }
                Operation::Finish(_) => Ok(ApplicationOutput::Terminal(self.result())),
                Operation::Abort(_) => Ok(ApplicationOutput::Aborted),
                _ => Err(Diagnostic::Internal),
            }
        }
        fn split_import<'a>(
            &'a self,
            descriptor: &'a TensorImport,
        ) -> Result<ImportSource<'a, Metadata>, Code> {
            Ok(ImportSource {
                manifest: &descriptor.manifest,
                expected_binding: &descriptor.source,
                metadata: Metadata {
                    shape: descriptor.shape,
                    dtype: descriptor.dtype.clone(),
                },
            })
        }
        fn validate_import(
            &self,
            metadata: &Metadata,
            manifest: &BufferManifest,
            bytes: &[u8],
        ) -> Result<TensorResult, Code> {
            if metadata.dtype != "f32le"
                || bytes.len() != metadata.shape.iter().product::<usize>() * 4
                || manifest.byte_length != bytes.len()
                || bytes
                    .chunks_exact(4)
                    .any(|row| !f32::from_le_bytes(row.try_into().unwrap()).is_finite())
            {
                return Err(Code::InvalidInput);
            }
            // Pure validation retains no bytes and does not update total or calls.
            Ok(self.result())
        }
    }
    type Setup = (
        Owner<Consumer>,
        Client<Consumer>,
        Rc<Cell<usize>>,
        Rc<Cell<f64>>,
    );
    fn setup() -> Setup {
        let mut bind = binding();
        bind.application_digest =
            typed_digest(PROFILE_DOMAIN, &parse_value(DESCRIPTOR).unwrap(), None).unwrap();
        let calls = Rc::new(Cell::new(0));
        let total = Rc::new(Cell::new(0.0));
        let owner = Owner::new(
            bind.clone(),
            Consumer {
                calls: calls.clone(),
                total: total.clone(),
            },
            vec![SEMANTIC.into()],
        )
        .unwrap();
        (owner, Client::new(bind).unwrap(), calls, total)
    }
    fn call(
        owner: &mut Owner<Consumer>,
        client: &mut Client<Consumer>,
        op: AppOperation<Consumer>,
    ) -> AppResponse<Consumer> {
        let request = client.begin(op).unwrap().to_vec();
        let wire = owner.process(&request).unwrap().to_vec();
        assert_eq!(owner.process(&request).unwrap(), wire);
        let result = client.observe(&wire).unwrap();
        if result.outcome == Outcome::Committed {
            client
                .observe_acknowledgement(owner.process(&client.acknowledgement().unwrap()).unwrap())
                .unwrap();
        }
        result
    }
    fn prepare(owner: &mut Owner<Consumer>, client: &mut Client<Consumer>) {
        call(owner, client, Operation::Prepare(Empty {}));
    }
    fn tensor() -> Vec<u8> {
        [1.0_f32, 2.0, 3.0, 4.0, 5.0, 6.0]
            .into_iter()
            .flat_map(f32::to_le_bytes)
            .collect()
    }
    fn source(owner: &Owner<Consumer>, bytes: &[u8]) -> (BufferPool, TensorImport) {
        let mut binding = owner.binding().clone();
        binding.generation = "44444444-4444-4444-8444-444444444444".into();
        let mut pool = BufferPool::new(binding.clone(), vec![SEMANTIC.into()]).unwrap();
        let context =
            TrustedHostCreationContext::new(binding.clone(), "b".repeat(64), None).unwrap();
        let manifest = pool.publish(&context, SEMANTIC, bytes).unwrap();
        (
            pool,
            TensorImport {
                manifest,
                source: binding,
                shape: [2, 3],
                dtype: "f32le".into(),
            },
        )
    }
    fn import(
        owner: &mut Owner<Consumer>,
        client: &mut Client<Consumer>,
        bytes: &[u8],
        complete: bool,
    ) -> (InputSpec, SealInput) {
        let (pool, descriptor) = source(owner, bytes);
        let begun = call(
            owner,
            client,
            Operation::BufferImportBegin(descriptor.clone()),
        );
        let Body::ImportReserved { reference } = begun.body else {
            panic!("import")
        };
        let seal = SealInput {
            reference: reference.clone(),
            expected_import_request_digest: begun.request_digest,
            expected_source_manifest_digest: descriptor.manifest.manifest_digest.clone(),
        };
        let mut spec = InputSpec {
            reference: reference.clone(),
            expected_manifest_digest: "0".repeat(64),
        };
        if complete {
            call(
                owner,
                client,
                Operation::BufferAppend(AppendInput {
                    reference,
                    chunk: pool.read(&descriptor.manifest.reference(), 0).unwrap(),
                }),
            );
            let Body::ImportSealed { manifest, .. } = call(
                owner,
                client,
                Operation::BufferSeal(SealInput {
                    reference: seal.reference.clone(),
                    expected_import_request_digest: seal.expected_import_request_digest.clone(),
                    expected_source_manifest_digest: seal.expected_source_manifest_digest.clone(),
                }),
            )
            .body
            else {
                panic!("seal")
            };
            spec.expected_manifest_digest = manifest.manifest_digest;
        }
        (spec, seal)
    }
    fn consume(inputs: Vec<InputSpec>, output_bytes: usize) -> AppOperation<Consumer> {
        Operation::Application(Consume {
            inputs,
            output_bytes,
            action: Action::Sum,
        })
    }
    fn release(owner: &mut Owner<Consumer>, client: &mut Client<Consumer>, input: &InputSpec) {
        call(
            owner,
            client,
            Operation::BufferRelease(ReferenceInput {
                reference: input.reference.clone(),
            }),
        );
    }

    #[test]
    fn actual_imported_tensor_changes_state_and_exact_output_bytes() {
        let (mut owner, mut client, calls, total) = setup();
        prepare(&mut owner, &mut client);
        let bytes = tensor();
        let (first, _) = import(&mut owner, &mut client, &bytes, true);
        assert_eq!((calls.get(), total.get()), (1, 0.0));
        let Body::Application { data } =
            call(&mut owner, &mut client, consume(vec![first.clone()], 4)).body
        else {
            panic!("result")
        };
        assert_eq!(data.accumulated_sum, 21.0);
        assert_eq!(
            data.source_manifests,
            vec![first.expected_manifest_digest.clone()]
        );
        let output = data.output_manifest.unwrap();
        let Body::Chunk { data: chunk } = call(
            &mut owner,
            &mut client,
            Operation::BufferRead(ReadInput {
                reference: output.reference(),
                expected_manifest_digest: output.manifest_digest.clone(),
                index: 0,
            }),
        )
        .body
        else {
            panic!("read")
        };
        assert_eq!(chunk.decoded().unwrap(), 21.0_f32.to_le_bytes());
        call(
            &mut owner,
            &mut client,
            Operation::BufferRelease(ReferenceInput {
                reference: output.reference(),
            }),
        );
        let mut changed = bytes.clone();
        changed[2] ^= 0x10;
        assert_eq!(
            changed.iter().zip(&bytes).filter(|(a, b)| a != b).count(),
            1
        );
        let (second, _) = import(&mut owner, &mut client, &changed, true);
        assert_ne!(
            first.expected_manifest_digest,
            second.expected_manifest_digest
        );
        let Body::Application { data } =
            call(&mut owner, &mut client, consume(vec![second.clone()], 0)).body
        else {
            panic!("result")
        };
        let delta = f64::from(f32::from_le_bytes(changed[..4].try_into().unwrap()) - 1.0);
        assert_eq!(data.accumulated_sum, 42.0 + delta);
        assert_eq!(
            data.source_manifests,
            vec![second.expected_manifest_digest.clone()]
        );
        let Body::Application { data } = call(
            &mut owner,
            &mut client,
            consume(vec![first.clone(), second.clone()], 0),
        )
        .body
        else {
            panic!("two-input result")
        };
        assert_eq!(data.accumulated_sum, 84.0 + 2.0 * delta);
        assert_eq!(
            data.source_manifests,
            vec![
                first.expected_manifest_digest.clone(),
                second.expected_manifest_digest.clone()
            ]
        );
        release(&mut owner, &mut client, &first);
        release(&mut owner, &mut client, &second);
        assert_eq!(
            call(
                &mut owner,
                &mut client,
                Operation::Finish(End { inputs: vec![] })
            )
            .outcome,
            Outcome::Committed
        );
    }

    #[test]
    fn finite_input_sum_cannot_publish_nonfinite_f32_output() {
        for overflowing in [false, true] {
            let (mut owner, mut client, calls, total) = setup();
            prepare(&mut owner, &mut client);
            let bytes = if overflowing {
                [3e38_f32; 6]
                    .into_iter()
                    .flat_map(f32::to_le_bytes)
                    .collect()
            } else {
                tensor()
            };
            let (input, _) = import(&mut owner, &mut client, &bytes, true);
            let sequence = owner.high_water() + 1;
            let result = call(&mut owner, &mut client, consume(vec![input], 4));
            assert_eq!(
                result.outcome,
                if overflowing {
                    Outcome::Indeterminate
                } else {
                    Outcome::Committed
                }
            );
            assert_eq!((owner.high_water(), calls.get()), (sequence, 2));
            assert!(total.get().is_finite());
            if overflowing {
                assert!(total.get() > f64::from(f32::MAX));
                assert_eq!(owner.lifecycle(), Lifecycle::Retired);
                assert!(client.is_retired());
                assert_eq!(owner.usage().live_slots, 1);
                assert_eq!(owner.usage().reserved_bytes, 24);
            }
        }
    }

    #[test]
    fn selected_input_and_output_admission_failures_preserve_effects() {
        for fault in [
            "generation",
            "unknown",
            "released",
            "incomplete",
            "digest",
            "duplicate",
            "roster",
            "output_slots",
        ] {
            let (mut owner, mut client, calls, total) = setup();
            prepare(&mut owner, &mut client);
            let (healthy, _) = import(&mut owner, &mut client, &tensor(), true);
            let (mut input, _) = import(&mut owner, &mut client, &tensor(), fault != "incomplete");
            if fault == "released" {
                release(&mut owner, &mut client, &input);
            }
            if fault == "generation" {
                input.reference.generation = "55555555-5555-4555-8555-555555555555".into();
            }
            if fault == "unknown" {
                input.reference.buffer_id = MAX_ID;
            }
            if fault == "digest" {
                input.expected_manifest_digest = "0".repeat(64);
            }
            if fault == "output_slots" {
                for _ in 2..LIVE_SLOTS {
                    import(&mut owner, &mut client, &tensor(), true);
                }
            }
            let inputs = match fault {
                "duplicate" => vec![input.clone(), input],
                "roster" => vec![input; 25],
                _ => vec![input],
            };
            let before = (owner.high_water(), owner.usage(), calls.get(), total.get());
            let response = call(
                &mut owner,
                &mut client,
                consume(inputs, if fault == "output_slots" { 4 } else { 0 }),
            );
            assert_eq!(
                response.outcome,
                Outcome::RejectedBeforeExecution,
                "{fault}"
            );
            assert_eq!(
                (owner.high_water(), owner.usage(), calls.get(), total.get()),
                before,
                "{fault}"
            );
            assert_eq!(
                call(&mut owner, &mut client, consume(vec![healthy], 0)).outcome,
                Outcome::Committed,
                "{fault}"
            );
        }
    }

    #[test]
    fn bad_payload_digest_and_coherent_nonfinite_tensor_cannot_seal() {
        for nonfinite in [false, true] {
            let (mut owner, mut client, calls, total) = setup();
            prepare(&mut owner, &mut client);
            let mut bytes = tensor();
            if nonfinite {
                bytes[..4].copy_from_slice(&f32::NAN.to_le_bytes());
            }
            let (pool, descriptor) = source(&owner, &bytes);
            let begun = call(
                &mut owner,
                &mut client,
                Operation::BufferImportBegin(descriptor.clone()),
            );
            let Body::ImportReserved { reference } = begun.body else {
                panic!("import")
            };
            let chunk = if nonfinite {
                pool.read(&descriptor.manifest.reference(), 0).unwrap()
            } else {
                let mut changed = bytes.clone();
                changed[2] ^= 0x10;
                let (changed_pool, changed_source) = source(&owner, &changed);
                let mut chunk = changed_pool
                    .read(&changed_source.manifest.reference(), 0)
                    .unwrap();
                chunk.manifest_digest = descriptor.manifest.manifest_digest.clone();
                chunk
            };
            assert_eq!(
                call(
                    &mut owner,
                    &mut client,
                    Operation::BufferAppend(AppendInput {
                        reference: reference.clone(),
                        chunk
                    })
                )
                .outcome,
                Outcome::Committed
            );
            let before = (owner.high_water(), owner.usage(), calls.get(), total.get());
            assert_eq!(
                call(
                    &mut owner,
                    &mut client,
                    Operation::BufferSeal(SealInput {
                        reference: reference.clone(),
                        expected_import_request_digest: begun.request_digest,
                        expected_source_manifest_digest: descriptor.manifest.manifest_digest
                    })
                )
                .outcome,
                Outcome::RejectedBeforeExecution
            );
            assert_eq!(
                (owner.high_water(), owner.usage(), calls.get(), total.get()),
                before
            );
            call(
                &mut owner,
                &mut client,
                Operation::BufferAbort(ReferenceInput { reference }),
            );
            let (healthy, _) = import(&mut owner, &mut client, &tensor(), true);
            assert_eq!(
                call(&mut owner, &mut client, consume(vec![healthy], 0)).outcome,
                Outcome::Committed
            );
        }
    }

    #[test]
    fn unnamed_or_ignored_input_failure_retires_after_entry() {
        for action in [Action::ReadUnnamed, Action::IgnoreReadError] {
            let (mut owner, mut client, calls, _) = setup();
            prepare(&mut owner, &mut client);
            let (input, _) = import(&mut owner, &mut client, &tensor(), true);
            let sequence = owner.high_water() + 1;
            assert_eq!(
                call(
                    &mut owner,
                    &mut client,
                    Operation::Application(Consume {
                        inputs: vec![input],
                        output_bytes: 0,
                        action
                    })
                )
                .outcome,
                Outcome::Indeterminate
            );
            assert_eq!(owner.high_water(), sequence);
            assert_eq!(calls.get(), 2);
            assert_eq!(owner.lifecycle(), Lifecycle::Retired);
            assert!(client.is_retired());
            let (mut owner, mut client, _, _) = setup();
            prepare(&mut owner, &mut client);
            let (input, _) = import(&mut owner, &mut client, &tensor(), true);
            assert_eq!(
                call(&mut owner, &mut client, consume(vec![input], 0)).outcome,
                Outcome::Committed
            );
        }
    }

    #[test]
    fn finish_cannot_demand_input_capabilities() {
        let (mut owner, mut client, calls, total) = setup();
        prepare(&mut owner, &mut client);
        let (input, _) = import(&mut owner, &mut client, &tensor(), true);
        release(&mut owner, &mut client, &input);
        let before = (owner.high_water(), owner.usage(), calls.get(), total.get());
        assert_eq!(
            call(
                &mut owner,
                &mut client,
                Operation::Finish(End {
                    inputs: vec![input]
                })
            )
            .outcome,
            Outcome::RejectedBeforeExecution
        );
        assert_eq!(
            (owner.high_water(), owner.usage(), calls.get(), total.get()),
            before
        );
        assert_eq!(
            call(
                &mut owner,
                &mut client,
                Operation::Finish(End { inputs: vec![] })
            )
            .outcome,
            Outcome::Committed
        );
    }
}
