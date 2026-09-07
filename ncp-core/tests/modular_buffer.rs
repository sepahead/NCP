use ncp_core::modular_buffer::*;

fn binding(generation: &str) -> BufferBinding {
    BufferBinding {
        profile_digest: "1".repeat(64),
        application_digest: "2".repeat(64),
        run_id: "10000000-0000-4000-8000-000000000001".into(),
        endpoint_id: "10000000-0000-4000-8000-000000000002".into(),
        generation: generation.into(),
    }
}

fn context(binding: &BufferBinding) -> TrustedHostCreationContext {
    TrustedHostCreationContext::new(binding.clone(), "3".repeat(64), Some("4".repeat(64))).unwrap()
}

fn pool(binding: &BufferBinding) -> BufferPool {
    BufferPool::new(binding.clone(), vec!["5".repeat(64)]).unwrap()
}

const SOURCE: &str = "10000000-0000-4000-8000-000000000003";
const TARGET: &str = "10000000-0000-4000-8000-000000000004";

#[test]
fn canonical_base64_boundaries_and_padding_bits() {
    for (raw, encoded) in [
        (b"f".as_slice(), "Zg=="),
        (b"fo".as_slice(), "Zm8="),
        (b"foo".as_slice(), "Zm9v"),
    ] {
        assert_eq!(encode_chunk(raw).unwrap(), encoded);
        assert_eq!(decode_chunk(encoded).unwrap(), raw);
    }
    for size in [1, 2, 3, CHUNK_BYTES - 1, CHUNK_BYTES] {
        let bytes: Vec<u8> = (0..size).map(|i| (i % 251) as u8).collect();
        assert_eq!(decode_chunk(&encode_chunk(&bytes).unwrap()).unwrap(), bytes);
    }
    for bad in [
        "", "Zg", "Zh==", "Zm9=", "Zg===", "Zg==\n", "Zg==AAAA", "-w==", "_w==", "é===", "AA=A",
        "====",
    ] {
        assert!(decode_chunk(bad).is_err(), "accepted {bad:?}");
    }
    assert!(encode_chunk(&vec![0; CHUNK_BYTES + 1]).is_err());
    assert!(decode_chunk(&"A".repeat(CHUNK_BYTES.div_ceil(3) * 4)).is_err());
}

#[test]
fn installed_semantic_roster_has_exact_identity_and_cardinality_bounds() {
    let owner = binding(SOURCE);
    let full: Vec<String> = (0..SEMANTIC_SLOTS).map(|i| format!("{i:064x}")).collect();
    assert!(BufferPool::new(owner.clone(), full.clone()).is_ok());
    let mut too_many = full;
    too_many.push(format!("{SEMANTIC_SLOTS:064x}"));
    for bad in [
        vec![],
        too_many,
        vec!["5".repeat(64); 2],
        vec!["6".repeat(64), "5".repeat(64)],
        vec!["A".repeat(64)],
    ] {
        assert!(matches!(
            BufferPool::new(owner.clone(), bad),
            Err(BufferError::Binding)
        ));
    }
    assert!(TrustedHostCreationContext::new(owner.clone(), "3".repeat(63), None).is_err());
    assert!(TrustedHostCreationContext::new(owner, "3".repeat(64), Some("4".repeat(63))).is_err());
}

#[test]
fn producer_copies_owned_bytes_and_binds_context_without_digest_cycle() {
    let binding = binding(SOURCE);
    let mut pool = pool(&binding);
    let mut payload = vec![1, 2, 3];
    let manifest = pool
        .publish(&context(&binding), &"5".repeat(64), &payload)
        .unwrap();
    payload.fill(9);
    manifest.verify(&binding).unwrap();
    assert_eq!(
        pool.read(&manifest.reference(), 0)
            .unwrap()
            .decoded()
            .unwrap(),
        [1, 2, 3]
    );
    assert_eq!(manifest.creating_request_digest, "3".repeat(64));
    assert_eq!(manifest.causal_predecessor, Some("4".repeat(64)));
    let value = serde_json::to_value(&manifest).unwrap();
    assert!(value.get("result_digest").is_none());
    assert!(serde_json::to_vec(&manifest).unwrap().len() <= MANIFEST_BYTES);
}

#[test]
fn failed_context_and_schema_admission_preserves_allocation_and_counter() {
    let source = binding(SOURCE);
    let mut pool = pool(&source);
    let preserved = pool
        .publish(&context(&source), &"5".repeat(64), b"preserve")
        .unwrap();
    for field in ["profile", "application", "generation", "endpoint", "run"] {
        let mut wrong = source.clone();
        match field {
            "profile" => wrong.profile_digest = "6".repeat(64),
            "application" => wrong.application_digest = "6".repeat(64),
            "generation" => wrong.generation = TARGET.into(),
            "endpoint" => wrong.endpoint_id = TARGET.into(),
            _ => wrong.run_id = TARGET.into(),
        }
        let before = pool.usage();
        assert_eq!(
            pool.publish(&context(&wrong), &"5".repeat(64), b"x"),
            Err(BufferError::Binding)
        );
        assert_eq!(pool.usage(), before);
        assert_eq!(
            pool.read(&preserved.reference(), 0)
                .unwrap()
                .decoded()
                .unwrap(),
            b"preserve"
        );
    }
    let before = pool.usage();
    assert_eq!(
        pool.publish(&context(&source), &"6".repeat(64), b"x"),
        Err(BufferError::Binding)
    );
    assert_eq!(
        pool.publish(&context(&source), &"5".repeat(64), b""),
        Err(BufferError::Capacity)
    );
    assert_eq!(pool.usage(), before);
}

#[test]
fn manifest_tampering_and_closed_wire_reject_before_use() {
    let source = binding(SOURCE);
    let mut pool = pool(&source);
    let manifest = pool
        .publish(&context(&source), &"5".repeat(64), b"x")
        .unwrap();
    let json = serde_json::to_vec(&manifest).unwrap();
    assert_eq!(BufferManifest::from_json(&json, &source).unwrap(), manifest);
    let mut tampered = manifest.clone();
    tampered.creating_request_digest = "6".repeat(64);
    assert_eq!(tampered.verify(&source), Err(BufferError::Conflict));
    assert_eq!(manifest.verify(&binding(TARGET)), Err(BufferError::Binding));
    let mut value = serde_json::to_value(&manifest).unwrap();
    value["result_digest"] = serde_json::json!("6".repeat(64));
    assert!(BufferManifest::from_json(&serde_json::to_vec(&value).unwrap(), &source).is_err());
    let chunk = pool.read(&manifest.reference(), 0).unwrap();
    let json = String::from_utf8(chunk.to_json().unwrap()).unwrap();
    assert_eq!(BufferChunk::from_json(json.as_bytes()).unwrap(), chunk);
    for malformed in [
        json.replacen("{", "{\"index\":0,", 1),
        json.replace("\"index\":0", "\"index\":-0"),
        json.replace("\"index\":0", "\"index\":0.0"),
        json.replace("\"index\":0", "\"index\":true"),
        json.replace("\"index\":0", "\"index\":9007199254740992"),
        json.replace("\"index\":0", "\"index\":\"\\ud800\""),
        json.replacen("{", "{\"path\":\"/tmp/not-a-handle\",", 1),
    ] {
        assert!(
            BufferChunk::from_json(malformed.as_bytes()).is_err(),
            "accepted malformed chunk"
        );
    }
    let padded = format!("{json}{}", " ".repeat(FRAME_BYTES - json.len()));
    assert!(BufferChunk::from_json(padded.as_bytes()).is_ok());
    assert_eq!(
        BufferChunk::from_json(format!("{padded} ").as_bytes()),
        Err(BufferError::Capacity)
    );
}

#[test]
fn import_prefix_and_sealing_preserve_source_and_destination_reservations() {
    let source = binding(SOURCE);
    let target = binding(TARGET);
    let mut producer = pool(&source);
    let mut receiver = pool(&target);
    let payload: Vec<u8> = (0..CHUNK_BYTES + 7).map(|i| (i % 251) as u8).collect();
    let manifest = producer
        .publish(&context(&source), &"5".repeat(64), &payload)
        .unwrap();
    let handle = receiver
        .begin_import(&context(&target), &manifest, &source)
        .unwrap();
    assert_eq!(
        producer.usage().reserved_bytes + receiver.usage().reserved_bytes,
        payload.len() * 2
    );
    let before = receiver.usage();
    assert_eq!(receiver.seal(&handle), Err(BufferError::State));
    assert_eq!(receiver.read(&handle, 0), Err(BufferError::State));
    assert_eq!(
        receiver.append(&handle, &producer.read(&manifest.reference(), 1).unwrap()),
        Err(BufferError::Conflict)
    );
    let first = producer.read(&manifest.reference(), 0).unwrap();
    receiver.append(&handle, &first).unwrap();
    assert_eq!(receiver.append(&handle, &first), Err(BufferError::Conflict));
    let mut corrupted = producer.read(&manifest.reference(), 1).unwrap();
    corrupted.chunk_sha256 = "0".repeat(64);
    assert_eq!(
        receiver.append(&handle, &corrupted),
        Err(BufferError::Conflict)
    );
    assert_eq!(receiver.usage(), before);
    receiver
        .append(&handle, &producer.read(&manifest.reference(), 1).unwrap())
        .unwrap();
    let imported = receiver.seal(&handle).unwrap();
    assert_eq!(
        imported.imported_manifest_digest,
        Some(manifest.manifest_digest)
    );
    assert_eq!(receiver.usage().reserved_bytes, before.reserved_bytes);
    assert_eq!(receiver.usage().live_slots, before.live_slots);
    assert_eq!(receiver.usage().incomplete_slots, 0);
    let restored: Vec<u8> = (0..imported.chunk_count)
        .flat_map(|i| receiver.read(&handle, i).unwrap().decoded().unwrap())
        .collect();
    assert_eq!(restored, payload);
    assert_eq!(receiver.abort_import(&handle), Err(BufferError::State));
    receiver.release(&handle).unwrap();
    assert_eq!(receiver.release(&handle), Err(BufferError::Unavailable));
    assert_eq!(receiver.usage().next_id, 2);
    assert_eq!(producer.usage().reserved_bytes, payload.len());
}

#[test]
fn incomplete_abort_is_named_and_never_reuses_an_id() {
    let source = binding(SOURCE);
    let target = binding(TARGET);
    let mut producer = pool(&source);
    let manifest = producer
        .publish(&context(&source), &"5".repeat(64), b"x")
        .unwrap();
    let mut receiver = pool(&target);
    let first = receiver
        .begin_import(&context(&target), &manifest, &source)
        .unwrap();
    let second = receiver
        .begin_import(&context(&target), &manifest, &source)
        .unwrap();
    let before = receiver.usage();
    assert_eq!(receiver.release(&first), Err(BufferError::State));
    assert_eq!(
        receiver.abort_import(&manifest.reference()),
        Err(BufferError::Binding)
    );
    assert_eq!(receiver.usage(), before);
    receiver.abort_import(&first).unwrap();
    assert_eq!(receiver.abort_import(&first), Err(BufferError::Unavailable));
    receiver
        .append(&second, &producer.read(&manifest.reference(), 0).unwrap())
        .unwrap();
    receiver.seal(&second).unwrap();
    let next = receiver
        .begin_import(&context(&target), &manifest, &source)
        .unwrap();
    assert_eq!(next.buffer_id, 3);
}

#[test]
fn valid_chunk_hash_cannot_hide_wrong_complete_payload() {
    let source = binding(SOURCE);
    let target = binding(TARGET);
    let mut producer = pool(&source);
    let mut receiver = pool(&target);
    let manifest = producer
        .publish(&context(&source), &"5".repeat(64), b"x")
        .unwrap();
    let other = producer
        .publish(&context(&source), &"5".repeat(64), b"y")
        .unwrap();
    let handle = receiver
        .begin_import(&context(&target), &manifest, &source)
        .unwrap();
    let mut forged = producer.read(&other.reference(), 0).unwrap();
    forged.manifest_digest.clone_from(&manifest.manifest_digest);
    receiver.append(&handle, &forged).unwrap();
    let before = receiver.usage();
    assert_eq!(receiver.seal(&handle), Err(BufferError::Conflict));
    assert_eq!(receiver.usage(), before);
    assert_eq!(receiver.read(&handle, 0), Err(BufferError::State));
    receiver.abort_import(&handle).unwrap();
    let fresh = receiver
        .begin_import(&context(&target), &manifest, &source)
        .unwrap();
    receiver
        .append(&fresh, &producer.read(&manifest.reference(), 0).unwrap())
        .unwrap();
    receiver.seal(&fresh).unwrap();
}

#[test]
fn exact_payload_and_slot_capacity_fail_without_admission() {
    let source = binding(SOURCE);
    let context = context(&source);
    let mut pool = pool(&source);
    let maximum = vec![7; BUFFER_BYTES];
    let before = pool.usage();
    assert_eq!(
        pool.publish(&context, &"5".repeat(64), &vec![7; BUFFER_BYTES + 1]),
        Err(BufferError::Capacity)
    );
    assert_eq!(pool.usage(), before);
    for _ in 0..ENDPOINT_BYTES / BUFFER_BYTES {
        pool.publish(&context, &"5".repeat(64), &maximum).unwrap();
    }
    let before = pool.usage();
    assert_eq!(
        pool.publish(&context, &"5".repeat(64), b"x"),
        Err(BufferError::Capacity)
    );
    assert_eq!(pool.usage(), before);
    assert_eq!(
        pool.read(
            &BufferRef {
                generation: SOURCE.into(),
                buffer_id: 1
            },
            255
        )
        .unwrap()
        .decoded()
        .unwrap(),
        vec![7; CHUNK_BYTES]
    );
    let mut small = BufferPool::new(source.clone(), vec!["5".repeat(64)]).unwrap();
    for _ in 0..LIVE_SLOTS {
        small.publish(&context, &"5".repeat(64), b"x").unwrap();
    }
    let before = small.usage();
    assert_eq!(
        small.publish(&context, &"5".repeat(64), b"x"),
        Err(BufferError::Capacity)
    );
    assert_eq!(small.usage(), before);
}

#[test]
fn incomplete_and_total_slot_limits_share_one_budget() {
    let source = binding(SOURCE);
    let target = binding(TARGET);
    let mut producer = pool(&source);
    let manifest = producer
        .publish(&context(&source), &"5".repeat(64), b"x")
        .unwrap();
    let mut receiver = pool(&target);
    for _ in 0..INCOMPLETE_SLOTS {
        receiver
            .begin_import(&context(&target), &manifest, &source)
            .unwrap();
    }
    let before = receiver.usage();
    assert_eq!(
        receiver.begin_import(&context(&target), &manifest, &source),
        Err(BufferError::Capacity)
    );
    assert_eq!(receiver.usage(), before);
    for _ in 0..LIVE_SLOTS - INCOMPLETE_SLOTS {
        receiver
            .publish(&context(&target), &"5".repeat(64), b"x")
            .unwrap();
    }
    assert_eq!(receiver.usage().live_slots, LIVE_SLOTS);
    assert_eq!(
        receiver.publish(&context(&target), &"5".repeat(64), b"x"),
        Err(BufferError::Capacity)
    );
}

#[test]
fn exact_composition_bounds_count_each_endpoint() {
    assert_eq!(
        admit_composition(&[ENDPOINT_BYTES; 4]),
        Ok(COMPOSITION_BYTES)
    );
    assert_eq!(admit_composition(&[1; ENDPOINTS]), Ok(ENDPOINTS));
    assert_eq!(
        admit_composition(&[1; ENDPOINTS + 1]),
        Err(BufferError::Capacity)
    );
    assert_eq!(
        admit_composition(&[
            ENDPOINT_BYTES,
            ENDPOINT_BYTES,
            ENDPOINT_BYTES,
            ENDPOINT_BYTES,
            1
        ]),
        Err(BufferError::Capacity)
    );
    assert_eq!(
        admit_composition(&[ENDPOINT_BYTES + 1]),
        Err(BufferError::Capacity)
    );
    assert_eq!(admit_composition(&[0; ENDPOINTS]), Ok(0));
    assert_eq!(
        admit_composition(&[0; ENDPOINTS + 1]),
        Err(BufferError::Capacity)
    );
}
