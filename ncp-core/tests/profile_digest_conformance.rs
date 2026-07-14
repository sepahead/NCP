//! Independent-corpus replay for the two portable configuration digests.

use ncp_core::plant::PlantProfile;
use ncp_core::security::DeploymentConfig;
use serde_json::Value;
use std::path::PathBuf;

fn load(name: &str) -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("testdata/conformance")
        .join(name);
    serde_json::from_slice(
        &std::fs::read(&path)
            .unwrap_or_else(|error| panic!("cannot read {}: {error}", path.display())),
    )
    .unwrap_or_else(|error| panic!("invalid JSON in {}: {error}", path.display()))
}

#[test]
fn security_state_digest_vectors() {
    let corpus = load("security-state-digest.json");
    for case in corpus["valid_cases"].as_array().expect("valid cases") {
        let config: DeploymentConfig = serde_json::from_value(case["input"].clone())
            .unwrap_or_else(|error| panic!("{} did not deserialize: {error}", case["id"]));
        assert_eq!(
            config
                .security_state_digest()
                .unwrap_or_else(|error| panic!("{} did not digest: {error}", case["id"])),
            case["expected_digest"].as_str().expect("expected digest"),
            "security-state digest case {}",
            case["id"]
        );
    }
    for case in corpus["invalid_cases"].as_array().expect("invalid cases") {
        let rejected = serde_json::from_value::<DeploymentConfig>(case["input"].clone())
            .map(|config| config.security_state_digest().is_err())
            .unwrap_or(true);
        assert!(
            rejected,
            "invalid security case {} was accepted",
            case["id"]
        );
    }
}

#[test]
fn plant_profile_digest_vectors() {
    let corpus = load("plant-profile.json");
    for case in corpus["valid_cases"].as_array().expect("valid cases") {
        let mut profile: PlantProfile = serde_json::from_value(case["input"].clone())
            .unwrap_or_else(|error| panic!("{} did not deserialize: {error}", case["id"]));
        let expected = case["expected_digest"].as_str().expect("expected digest");
        assert_eq!(
            profile
                .computed_digest()
                .unwrap_or_else(|error| panic!("{} did not digest: {error}", case["id"])),
            expected,
            "plant-profile digest case {}",
            case["id"]
        );
        profile.profile_digest_sha256 = expected.to_owned();
        profile
            .validate()
            .unwrap_or_else(|error| panic!("{} did not validate: {error}", case["id"]));
    }
    for case in corpus["invalid_cases"].as_array().expect("invalid cases") {
        let rejected = serde_json::from_value::<PlantProfile>(case["input"].clone())
            .map(|profile| profile.validate().is_err())
            .unwrap_or(true);
        assert!(rejected, "invalid plant case {} was accepted", case["id"]);
    }
}
