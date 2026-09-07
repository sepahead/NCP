use ncp_local::modular_wire::*;
use ncp_local::{modular_buffer as buffer, modular_client as client, modular_owner as owner};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

#[derive(Deserialize)]
struct Vector {
    json: String,
    bits: String,
}

#[test]
fn descriptor_response_dispositions_cover_every_closed_combination() {
    let descriptor: Value = serde_json::from_slice(owner::CORE_DESCRIPTOR).unwrap();
    let binding = buffer::BufferBinding {
        profile_digest: "1".repeat(64),
        application_digest: "2".repeat(64),
        run_id: "10000000-0000-4000-8000-000000000001".into(),
        endpoint_id: "10000000-0000-4000-8000-000000000002".into(),
        generation: "10000000-0000-4000-8000-000000000003".into(),
    };
    let mut pool = buffer::BufferPool::new(binding.clone(), vec!["5".repeat(64)]).unwrap();
    let context =
        buffer::TrustedHostCreationContext::new(binding.clone(), "3".repeat(64), None).unwrap();
    let manifest = pool.publish(&context, &"5".repeat(64), b"a").unwrap();
    let chunk = pool.read(&manifest.reference(), 0).unwrap();
    let mut operations: Vec<_> = descriptor["operation_arms"]
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect();
    operations.extend(["result".into(), "ack".into()]);
    let outcomes = descriptor["outcome_codes"].as_object().unwrap();
    let codes: Vec<_> = outcomes
        .values()
        .flat_map(|v| v.as_array().unwrap())
        .collect();
    let mut accepted = 0;
    let mut checked = 0;
    for operation in operations {
        for (outcome, permitted_codes) in outcomes {
            let disposition = &descriptor["response_dispositions"][outcome];
            for code in &codes {
                for kind in descriptor["response_body_arms"].as_object().unwrap().keys() {
                    let expected_body = if disposition["operations"]
                        .as_array()
                        .is_some_and(|list| list.contains(&json!(operation)))
                    {
                        &disposition["body"]
                    } else {
                        &disposition["operation_bodies"][&operation]
                    };
                    let expected = permitted_codes.as_array().unwrap().contains(code)
                        && expected_body.as_str() == Some(kind);
                    let mut body = json!({"kind":kind});
                    match kind.as_str() {
                        "prepared" | "application" | "finished" => body["data"] = json!({}),
                        "import_sealed" => {
                            body["manifest"] = json!(manifest);
                            body["data"] = json!({});
                        }
                        "import_reserved" | "buffer_changed" => {
                            body["reference"] = json!(manifest.reference())
                        }
                        "chunk" => body["data"] = json!(chunk),
                        "indeterminate" => body["reason"] = json!("backend"),
                        "acknowledged" => {
                            body["stamp"] = json!({"sequence":1,"original_request_digest":"3".repeat(64),"result_digest":"4".repeat(64)})
                        }
                        _ => {}
                    }
                    // Closed shape only: application-value semantics are tested by owner controls.
                    let response: Response<Value, Value, Value> = serde_json::from_value(json!({
                        "schema":RESPONSE_SCHEMA,"binding":binding,"sequence":1,"operation":operation,
                        "request_digest":"3".repeat(64),"outcome":outcome,"code":code,"body":body,"result_digest":"4".repeat(64)
                    })).unwrap();
                    let actual = response.check_shape().is_ok();
                    assert_eq!(actual, expected, "{operation}/{outcome}/{code}/{kind}");
                    accepted += usize::from(actual);
                    checked += 1;
                }
            }
        }
    }
    assert_eq!((accepted, checked), (105, 10_296));
}

#[test]
fn descriptor_logical_extents_match_components_and_composition_admission() {
    let descriptor: Value = serde_json::from_slice(owner::CORE_DESCRIPTOR).unwrap();
    let bounds = &descriptor["bounds"];
    assert_eq!(
        bounds["endpoint_logical_working_extent_excluding_payload"],
        owner::ENDPOINT_LOGICAL_OVERHEAD
    );
    assert_eq!(
        owner::ENDPOINT_LOGICAL_OVERHEAD,
        131_072 + 32_768 + 16_384 + 6 * 65_536 + 3 * 65_536 + 131_072 + 32_768 + 5 * 65_536
    );
    assert_eq!(
        bounds["additional_client_logical_bytes"],
        client::CLIENT_LOGICAL_OVERHEAD
    );
    assert_eq!(
        client::CLIENT_LOGICAL_OVERHEAD,
        6 * 65_536 + 3 * 65_536 + 131_072 + 32_768 + 5 * 65_536 + 4096
    );
    assert_eq!(
        bounds["sixteen_clients_additional_logical_bytes"],
        16 * client::CLIENT_LOGICAL_OVERHEAD
    );
    assert_eq!(bounds["input_spec_encoded_bytes"], buffer::INPUT_SPEC_BYTES);
    assert_eq!(bounds["input_spec_slots"], buffer::LIVE_SLOTS);
    assert_eq!(
        bounds["additional_input_metadata_logical_bytes"],
        buffer::INPUT_METADATA_BYTES
    );
    assert_eq!(
        buffer::INPUT_METADATA_BYTES,
        2 * buffer::LIVE_SLOTS * buffer::INPUT_SPEC_BYTES + 4096
    );
    assert_eq!(bounds["owner_frame_extents"], 6);
    assert_eq!(bounds["parsed_value_extents"], 3);
    assert_eq!(bounds["decoded_source_utf8_bytes"], 65_536);
    assert_eq!(bounds["scanner_token_utf8_bytes"], 2 * 65_536);
    assert_eq!(bounds["scalar_base64_utf8_bytes"], 2 * 65_536);
    assert_eq!(
        bounds["additional_import_metadata_logical_bytes"],
        owner::IMPORT_METADATA_LOGICAL_BYTES
    );
    assert_eq!(
        bounds["import_metadata_record_encoded_bytes"],
        owner::IMPORT_METADATA_BYTES
    );
    assert_eq!(
        owner::composition_budget(&[0; 16]).unwrap(),
        (0, 20_185_088)
    );
    let mut full = [0; 16];
    full[..4].fill(buffer::ENDPOINT_BYTES);
    assert_eq!(
        owner::composition_budget(&full).unwrap(),
        (268_435_456, 20_185_088)
    );
    assert!(owner::composition_budget(&[0; 17]).is_err());
    full[4] = 1;
    assert!(owner::composition_budget(&full).is_err());
}

#[test]
fn selected_binary64_values_match_independent_bit_and_hash_construction() {
    let vectors: Vec<Vector> =
        serde_json::from_str(include_str!("fixtures/modular-binary64.json")).unwrap();
    for row in vectors {
        let value = parse_value(row.json.as_bytes()).unwrap();
        let bits = u64::from_str_radix(&row.bits, 16).unwrap();
        assert_eq!(value.as_f64().unwrap().to_bits(), bits, "{}", row.json);
        let mut bytes = PROFILE_DOMAIN.as_bytes().to_vec();
        bytes.push(0);
        bytes.push(3);
        bytes.extend_from_slice(&bits.to_be_bytes());
        let expected: String = Sha256::digest(bytes)
            .iter()
            .map(|byte| format!("{byte:02x}"))
            .collect();
        assert_eq!(
            typed_digest(PROFILE_DOMAIN, &value, None).unwrap(),
            expected
        );
    }
    assert_ne!(
        typed_digest(PROFILE_DOMAIN, &parse_value(b"0").unwrap(), None).unwrap(),
        typed_digest(PROFILE_DOMAIN, &parse_value(b"-0").unwrap(), None).unwrap()
    );
}

#[test]
fn exact_typed_projection_budget_rejects_one_more_zero_before_projection_growth() {
    // Domain+NUL and array tag/u64 length occupy32 bytes. Each numeric zero uses9.
    assert_eq!(PROFILE_DOMAIN.len() + 1 + 9, 32);
    let accepted = serde_json::json!(vec![0; 14_560]);
    let rejected = serde_json::json!(vec![0; 14_561]);
    assert_eq!(32 + 9 * 14_560, 131_072);
    assert!(serde_json::to_vec(&rejected).unwrap().len() < 65_536);
    assert!(typed_digest(PROFILE_DOMAIN, &accepted, None).is_ok());
    assert_eq!(
        typed_digest(PROFILE_DOMAIN, &rejected, None),
        Err(ModularError::Capacity)
    );
}

#[test]
fn frame_bound_and_lexical_failures_are_checked_before_generic_decode() {
    let mut valid = vec![b' '; 65_536];
    valid[0] = b'0';
    assert_eq!(parse_value(&valid).unwrap(), serde_json::json!(0));
    valid.push(b' ');
    assert_eq!(parse_value(&valid), Err(ModularError::Capacity));
    for payload in [
        br#"{"a":1,"\u0061":2}"#.as_slice(),
        br#""\ud800""#,
        b"0 trailing",
        b"NaN",
        b"1e301",
        b"9007199254740992",
        b"-9007199254740992",
    ] {
        assert!(parse_value(payload).is_err());
    }
    assert!(typed_digest(
        PROFILE_DOMAIN,
        &serde_json::json!(9_007_199_254_740_992_u64),
        None
    )
    .is_err());
    assert!(typed_digest("ncp.local.request.v1", &serde_json::json!({}), None).is_err());
}
