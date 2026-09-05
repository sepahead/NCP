//! Descriptor identity, parser limits, and previous-candidate rejection controls.

use ncp_local::bounded_json as wire;
use ncp_local::local::{
    local_digest, local_profile_digest, LocalBinding, LocalRole, LOCAL_PROFILE_DESCRIPTOR,
    MAX_LOCAL_FRAME_BYTES, MAX_SEQUENCE,
};
use ncp_local::local_data::{MAX_ENTITIES, MAX_STEPS};
use serde_json::Value;
use sha2::{Digest, Sha256};

#[test]
fn installed_descriptor_binds_actual_ingress_limits_and_data_bounds() {
    let descriptor: Value = serde_json::from_str(LOCAL_PROFILE_DESCRIPTOR).unwrap();
    assert!(LOCAL_PROFILE_DESCRIPTOR.len() <= MAX_LOCAL_FRAME_BYTES);
    wire::preflight(LOCAL_PROFILE_DESCRIPTOR.as_bytes()).unwrap();
    let ingress = &descriptor["ingress"];
    for (name, value) in [
        ("maximum_frame_bytes", MAX_LOCAL_FRAME_BYTES),
        ("maximum_depth", wire::MAX_NESTING_DEPTH),
        ("maximum_objects", wire::MAX_OBJECTS),
        ("maximum_arrays", wire::MAX_ARRAYS),
        ("maximum_total_members", wire::MAX_TOTAL_MEMBERS),
        ("maximum_total_array_items", wire::MAX_TOTAL_ARRAY_ITEMS),
        ("maximum_object_members", wire::MAX_OBJECT_MEMBERS),
        ("maximum_array_items", wire::MAX_ARRAY_ITEMS),
        ("maximum_key_utf8_bytes", wire::MAX_KEY_BYTES),
        ("maximum_string_utf8_bytes", wire::MAX_STRING_BYTES),
        (
            "maximum_total_string_utf8_bytes",
            wire::MAX_TOTAL_STRING_BYTES,
        ),
    ] {
        assert_eq!(ingress[name].as_u64(), Some(value as u64), "{name}");
    }
    assert_eq!(
        ingress["maximum_integer_magnitude"].as_u64(),
        Some(MAX_SEQUENCE)
    );
    assert_eq!(
        ingress["maximum_finite_number_magnitude"].as_f64(),
        Some(wire::MAX_FINITE_NUMBER_MAGNITUDE)
    );
    let plan = &descriptor["data_schema"]["$defs"]["RunPlan"]["properties"];
    assert_eq!(plan["planned_steps"]["maximum"].as_u64(), Some(MAX_STEPS));
    assert_eq!(
        plan["entity_ids"]["maxItems"].as_u64(),
        Some(MAX_ENTITIES as u64)
    );
}

#[test]
fn every_descriptor_section_is_bound_and_previous_candidate_is_rejected() {
    let descriptor: Value = serde_json::from_str(LOCAL_PROFILE_DESCRIPTOR).unwrap();
    let identity: Value =
        serde_json::from_str(include_str!("fixtures/local-profile-identity.json")).unwrap();
    let digest = local_profile_digest().unwrap();
    assert_eq!(digest, identity["typed_profile_digest"]);
    assert_eq!(
        format!("{:x}", Sha256::digest(LOCAL_PROFILE_DESCRIPTOR.as_bytes())),
        identity["descriptor_sha256"]
    );
    for section in descriptor.as_object().unwrap().keys() {
        let mut changed = descriptor.clone();
        changed.as_object_mut().unwrap().remove(section);
        assert_ne!(
            local_digest("ncp.local.profile.v1", &changed).unwrap(),
            digest
        );
    }
    let mut binding = LocalBinding {
        profile_digest: identity["previous_candidate_digest"]
            .as_str()
            .unwrap()
            .into(),
        run_id: "10c99b86-c8e0-4b94-80ae-8cec74456e2a".into(),
        generation: "748d5ab4-51c1-408f-b144-a27602edc823".into(),
        role: LocalRole::Body,
    };
    assert!(binding.validate().is_err());
    binding.profile_digest = digest;
    binding.validate().unwrap();
    for label in ["status", "publication_status", "qualification_status"] {
        assert!(descriptor.get(label).is_none());
        let mut changed = descriptor.clone();
        changed[label] = Value::String("released".into());
        binding.profile_digest = local_digest("ncp.local.profile.v1", &changed).unwrap();
        assert!(binding.validate().is_err());
    }
}
