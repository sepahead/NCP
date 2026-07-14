//! Behavioral conformance — the ncp-core reference vs the language-neutral
//! decision corpus (`conformance/behavior/vectors.json`).
//!
//! `tests/conformance.rs` pins the *wire shape* (serde <-> schema field parity).
//! This pins *behavior*: for every vector in the corpus, drive the real
//! `ncp_core` function and assert it produces the outcome the corpus declares.
//! Two things follow:
//!   1. the corpus can never claim an outcome the reference does not produce
//!      (this test fails if it drifts), and
//!   2. any other peer that replays the same corpus (e.g. the Python binding via
//!      `scripts/check_behavior_vectors.py`) is checking against outcomes that
//!      are themselves verified against the reference here.
//!
//! Covered functions: `check_version`, `contract_status`, `validate`, and the
//! `SafetyGovernor` (HOLD / ESTOP / speed-clamp / watchdog) decisions.

use ncp_core::{
    check_version, contract_status, validate, ActionBuffer, CommandFrame, ContractStatus,
    SafetyGovernor, SafetyLimits, SensorFrame, CONTRACT_HASH, NCP_VERSION,
};
use serde_json::Value;
use std::collections::BTreeSet;
use std::path::PathBuf;

/// Load the crate-local corpus snapshot. The package-surface gate byte-compares
/// it with the canonical repository corpus before testing the extracted archive.
fn load_corpus() -> Value {
    let path = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/testdata/conformance/behavior"
    ))
    .join("vectors.json");
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("failed to read behavior corpus {}: {e}", path.display()));
    serde_json::from_str(&text)
        .unwrap_or_else(|e| panic!("behavior corpus {} is not valid JSON: {e}", path.display()))
}

fn load_manifest() -> Value {
    let path = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/testdata/conformance/manifest.v1.json"
    ));
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| {
        panic!(
            "failed to read conformance manifest {}: {e}",
            path.display()
        )
    });
    serde_json::from_str(&text).unwrap_or_else(|e| {
        panic!(
            "conformance manifest {} is not valid JSON: {e}",
            path.display()
        )
    })
}

fn load_request_digest_corpus() -> Value {
    let path = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/testdata/conformance/request-digest.json"
    ));
    serde_json::from_slice(&std::fs::read(&path).expect("request-digest vectors readable"))
        .expect("request-digest vectors are JSON")
}

fn load_profile_corpus(name: &str) -> Value {
    let path =
        PathBuf::from(concat!(env!("CARGO_MANIFEST_DIR"), "/testdata/conformance")).join(name);
    serde_json::from_slice(&std::fs::read(&path).expect("profile vectors readable"))
        .expect("profile vectors are JSON")
}

fn apply_digest_case(base: &Value, case: &Value) -> Value {
    let mut request = base.clone();
    for patch in case["patch"].as_array().expect("digest patch array") {
        let path = patch["path"].as_array().expect("digest patch path");
        assert!(!path.is_empty(), "digest patch path must not be empty");
        let mut parent = &mut request;
        for segment in &path[..path.len() - 1] {
            parent = parent
                .as_object_mut()
                .expect("digest patch parent object")
                .get_mut(segment.as_str().expect("digest patch string segment"))
                .expect("digest patch intermediate member");
        }
        let leaf = path.last().unwrap().as_str().expect("digest patch leaf");
        let object = parent.as_object_mut().expect("digest patch leaf parent");
        match patch["op"].as_str().expect("digest patch op") {
            "set" => {
                object.insert(leaf.to_owned(), patch["value"].clone());
            }
            "remove" => {
                object.remove(leaf).expect("digest patch removal target");
            }
            operation => panic!("unknown digest patch operation {operation:?}"),
        }
    }
    request
}

fn cases<'a>(corpus: &'a Value, function: &str) -> &'a Vec<Value> {
    corpus["cases"][function]
        .as_array()
        .unwrap_or_else(|| panic!("corpus has no array of `{function}` cases"))
}

/// L2 magnitude of the governed command's `velocity_setpoint` channel (0 when the
/// channel is absent — but the HOLD/ESTOP path always re-inserts it zeroed).
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

#[test]
fn check_version_corpus() {
    let corpus = load_corpus();
    for case in cases(&corpus, "check_version") {
        let name = case["name"].as_str().unwrap();
        let version = case["input"]["version"].as_str().unwrap();
        let strict = case["input"]["strict"].as_bool().unwrap();
        let got = check_version(version, strict);
        let expect = &case["expect"];
        if expect["error"].as_bool() == Some(true) {
            assert!(
                got.is_err(),
                "check_version[{name}]: expected an error for {version:?} (strict={strict}), got {got:?}"
            );
        } else {
            let want = expect["compatible"].as_bool().unwrap();
            assert_eq!(
                got.expect("unexpected error"),
                want,
                "check_version[{name}]: {version:?} (strict={strict})"
            );
        }
    }
}

#[test]
fn contract_status_corpus() {
    let corpus = load_corpus();
    for case in cases(&corpus, "contract_status") {
        let name = case["name"].as_str().unwrap();
        let peer = case["input"]["peer_hash"].as_str(); // None when JSON null
        let tag = match contract_status(peer) {
            ContractStatus::Match => "match",
            ContractStatus::NotAdvertised => "not_advertised",
            ContractStatus::Mismatch { .. } => "mismatch",
        };
        assert_eq!(
            tag,
            case["expect"]["status"].as_str().unwrap(),
            "contract_status[{name}]: peer={peer:?}"
        );
    }
}

#[test]
fn request_digest_corpus() {
    let corpus = load_request_digest_corpus();
    for case in corpus["cases"].as_array().expect("request-digest cases") {
        let request = apply_digest_case(&corpus["base_request"], case);
        assert_eq!(
            ncp_core::request_digest(&request).expect("request digest computes"),
            case["expected_digest"].as_str().unwrap(),
            "request-digest case {}",
            case["id"].as_str().unwrap()
        );
    }
}

#[test]
fn validate_corpus() {
    let corpus = load_corpus();
    for case in cases(&corpus, "validate") {
        let name = case["name"].as_str().unwrap();
        let message = &case["input"]["message"];
        let want_valid = case["expect"]["valid"].as_bool().unwrap();
        let got = validate(message);
        assert_eq!(
            got.is_ok(),
            want_valid,
            "validate[{name}]: expected valid={want_valid}, got {got:?}"
        );
    }
}

#[test]
fn govern_corpus() {
    let corpus = load_corpus();
    for case in cases(&corpus, "govern") {
        let name = case["name"].as_str().unwrap();
        let input = &case["input"];
        let limits: SafetyLimits = serde_json::from_value(input["limits"].clone())
            .unwrap_or_else(|e| panic!("govern[{name}]: bad limits: {e}"));
        let command: CommandFrame = serde_json::from_value(input["command"].clone())
            .unwrap_or_else(|e| panic!("govern[{name}]: bad command: {e}"));
        let sensor: Option<SensorFrame> = match input.get("sensor") {
            Some(Value::Null) | None => None,
            Some(s) => Some(
                serde_json::from_value(s.clone())
                    .unwrap_or_else(|e| panic!("govern[{name}]: bad sensor: {e}")),
            ),
        };
        let now_s = input["now_s"].as_f64().unwrap();
        let last_sensor_s = input["last_sensor_s"].as_f64(); // None when null

        // One-shot governor per vector: govern() latches ESTOP on &mut self, but
        // each corpus vector is a single, self-contained decision (latching across
        // calls is covered by safety.rs unit tests, not the cross-language corpus).
        let mut gov = SafetyGovernor::new(limits);
        let out = gov.govern(&command, sensor.as_ref(), now_s, last_sensor_s);
        let out = serde_json::to_value(&out).unwrap();

        assert_eq!(
            out["mode"].as_str().unwrap(),
            case["expect"]["mode"].as_str().unwrap(),
            "govern[{name}]: mode"
        );
        if let Some(want_mag) = case["expect"]["velocity_setpoint_magnitude"].as_f64() {
            let got_mag = velocity_magnitude(&out);
            assert!(
                (got_mag - want_mag).abs() < 1e-9,
                "govern[{name}]: velocity magnitude want {want_mag}, got {got_mag}"
            );
        }
    }
}

#[test]
fn action_buffer_corpus() {
    let corpus = load_corpus();
    for case in cases(&corpus, "action_buffer") {
        let name = case["name"].as_str().unwrap();
        let operations = case["operations"]
            .as_array()
            .unwrap_or_else(|| panic!("action_buffer[{name}]: operations is not an array"));
        let mut buffer = ActionBuffer::new();
        for (index, operation) in operations.iter().enumerate() {
            match operation["op"].as_str().unwrap() {
                "command" => {
                    let command: CommandFrame =
                        serde_json::from_value(operation["command"].clone()).unwrap_or_else(|e| {
                            panic!("action_buffer[{name}][{index}]: bad command: {e}")
                        });
                    buffer.on_command(operation["now_s"].as_f64().unwrap(), command);
                }
                "reset" => buffer.reset(),
                "active" => {
                    let output = buffer.active(operation["now_s"].as_f64().unwrap());
                    let expect = &operation["expect"];
                    let want_active = expect["active"].as_bool().unwrap();
                    assert_eq!(
                        output.is_some(),
                        want_active,
                        "action_buffer[{name}][{index}]: active state"
                    );
                    assert_eq!(
                        buffer.is_estopped(),
                        expect["estopped"].as_bool().unwrap(),
                        "action_buffer[{name}][{index}]: ESTOP state"
                    );
                    if let Some(want) = expect.get("value").and_then(Value::as_f64) {
                        let got = output
                            .as_ref()
                            .and_then(|channels| channels.get("velocity_setpoint"))
                            .and_then(|channel| channel.data.first())
                            .copied()
                            .unwrap_or_else(|| {
                                panic!("action_buffer[{name}][{index}]: missing output value")
                            });
                        assert!(
                            (got - want).abs() < 1e-12,
                            "action_buffer[{name}][{index}]: want {want}, got {got}"
                        );
                    }
                }
                op => panic!("action_buffer[{name}][{index}]: unknown operation {op:?}"),
            }
        }
    }
}

#[test]
fn wire_pins_match_corpus_single_source() {
    // SHOULD-FIX #4a: `NCP_VERSION` and `CONTRACT_HASH` are independent hardcoded
    // constants in each peer (Rust here, TS, Python). Pin BOTH to the corpus header
    // so the corpus is the single cross-language source of wire truth — a peer that
    // bumps the wire but forgets the corpus (or vice versa) fails here, the same way
    // `contract_hash_matches_proto` ties the hash to the proto. (The Python binding
    // and ncp-ts assert the same against this corpus; check-version-coherence.sh
    // adds the {ncp-core, ncp-ts, corpus} cross-check.)
    let corpus = load_corpus();
    assert_eq!(
        NCP_VERSION,
        corpus["ncp_version"].as_str().unwrap(),
        "ncp-core NCP_VERSION must equal the behavior corpus ncp_version"
    );
    assert_eq!(
        CONTRACT_HASH,
        corpus["contract_hash"].as_str().unwrap(),
        "ncp-core CONTRACT_HASH must equal the behavior corpus contract_hash"
    );
}

#[test]
fn mandatory_manifest_matches_every_applicable_rust_vector() {
    let corpus = load_corpus();
    let manifest = load_manifest();
    let mut executed = BTreeSet::new();

    for (family, cases) in corpus["cases"].as_object().expect("behavior cases object") {
        for case in cases.as_array().expect("behavior family array") {
            executed.insert(format!(
                "behavior/{family}/{}",
                case["name"].as_str().expect("behavior case name")
            ));
        }
    }

    let request_digest = load_request_digest_corpus();
    for case in request_digest["cases"]
        .as_array()
        .expect("request-digest cases")
    {
        executed.insert(format!(
            "request-digest/{}",
            case["id"].as_str().expect("request-digest case id")
        ));
    }

    for (prefix, filename) in [
        ("security-state-digest", "security-state-digest.json"),
        ("plant-profile", "plant-profile.json"),
    ] {
        let corpus = load_profile_corpus(filename);
        for family in ["valid_cases", "invalid_cases"] {
            for case in corpus[family].as_array().expect("profile digest cases") {
                executed.insert(format!(
                    "{prefix}/{}",
                    case["id"].as_str().expect("profile digest case id")
                ));
            }
        }
    }

    let vectors = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/testdata/conformance/vectors"
    ));
    for entry in std::fs::read_dir(&vectors).expect("canonical vector directory") {
        let path = entry.expect("canonical vector entry").path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        let value: Value = serde_json::from_slice(&std::fs::read(&path).expect("vector bytes"))
            .unwrap_or_else(|error| panic!("invalid vector {}: {error}", path.display()));
        validate(&value).unwrap_or_else(|error| {
            panic!(
                "canonical vector {} failed validation: {error}",
                path.display()
            )
        });
        executed.insert(format!(
            "wire/{}/canonical",
            value["kind"].as_str().expect("canonical vector kind")
        ));
    }

    let migration_path = PathBuf::from(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/testdata/conformance/migration/channel-requirement.json"
    ));
    let migration: Value =
        serde_json::from_slice(&std::fs::read(&migration_path).expect("migration vector bytes"))
            .expect("migration vectors are JSON");
    for case in migration["cases"].as_array().expect("migration cases") {
        executed.insert(format!(
            "migration/{}",
            case["id"].as_str().expect("migration vector id")
        ));
    }

    let required = manifest["vectors"]
        .as_array()
        .expect("manifest vectors")
        .iter()
        .filter(|vector| vector["required"].as_bool() == Some(true))
        .filter(|vector| {
            vector["applicability"]["implementations"]
                .as_array()
                .is_some_and(|implementations| {
                    implementations
                        .iter()
                        .any(|implementation| implementation.as_str() == Some("rust"))
                })
        })
        .map(|vector| {
            vector["id"]
                .as_str()
                .expect("manifest vector id")
                .to_owned()
        })
        .collect::<BTreeSet<_>>();

    assert_eq!(
        executed, required,
        "required Rust conformance set must be exact: no skip, missing, or extra vector"
    );
}
