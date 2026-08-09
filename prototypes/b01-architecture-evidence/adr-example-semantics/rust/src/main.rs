mod decision;
mod error;
mod model;
mod patch;
mod profiles;
mod sha256;
mod source;
mod strict_json;

use std::collections::BTreeSet;
use std::env;
use std::ffi::OsString;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use serde::Serialize;
use serde_json::{json, Value};

use crate::decision::{review_packet_binding_self_test, verify_decision_set};
use crate::error::{EngineError, EngineResult};
use crate::model::{
    validate_bounded_fixture, Corpus, DecisionSetBinding, PatchTarget, ProductionAdmission,
    ProfileResult, RESULT_SCHEMA,
};
use crate::patch::apply_patch;
use crate::profiles::{evaluate, Evaluation};
use crate::sha256::sha256_hex;
use crate::source::{read_bounded, resolve_regular_relative_file, SourceRepository};
use crate::strict_json::{parse_strict, JsonLimits};

const ENGINE_ROOT: &str = "prototypes/b01-architecture-evidence/adr-example-semantics/rust";
const MAXIMUM_ENGINE_SOURCE_FILES: usize = 32;
const MAXIMUM_ENGINE_SOURCE_PATH_BYTES: usize = 512;
const MAXIMUM_ENGINE_SOURCE_FILE_BYTES: usize = 262_144;
const MAXIMUM_AGGREGATE_ENGINE_SOURCE_BYTES: usize = 2_097_152;

#[derive(Debug)]
struct Arguments {
    corpus: PathBuf,
    repo_root: PathBuf,
    self_test: bool,
}

#[derive(Serialize)]
struct ResultDocument {
    schema: &'static str,
    schema_version: u64,
    engine: &'static str,
    semantic_claim: &'static str,
    corpus_sha256: String,
    decision_set_binding: DecisionSetBinding,
    case_count: usize,
    mutation_count: usize,
    source_identities: Vec<SourceIdentity>,
    engine_source_identities: Vec<EngineSourceIdentity>,
    cases: Vec<CaseResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    self_tests: Option<SelfTestResult>,
}

#[derive(Serialize)]
struct SourceIdentity {
    case_id: String,
    path: String,
    json_fence_ordinal: usize,
    adr_byte_length: usize,
    adr_sha256: String,
    fence_byte_length: usize,
    fence_sha256: String,
}

#[derive(Serialize)]
struct EngineSourceIdentity {
    path: String,
    byte_length: usize,
    sha256: String,
}

#[derive(Serialize)]
struct CaseResult {
    id: String,
    profile_result: ProfileResult,
    production_admission: ProductionAdmission,
    diagnostics: Vec<String>,
    payload_interpreted: bool,
    mutations: Vec<MutationResult>,
}

#[derive(Serialize)]
struct MutationResult {
    id: String,
    profile_result: ProfileResult,
    production_admission: ProductionAdmission,
    diagnostics: Vec<String>,
    payload_interpreted: bool,
}

#[derive(Clone, Copy, Serialize)]
struct SelfTestResult {
    executed: usize,
    detected: usize,
}

struct BoundedOutput {
    bytes: Vec<u8>,
    maximum_bytes: usize,
}

impl BoundedOutput {
    fn new(maximum_bytes: usize) -> Self {
        Self {
            bytes: Vec::with_capacity(maximum_bytes.min(16_384)),
            maximum_bytes,
        }
    }

    fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

impl Write for BoundedOutput {
    fn write(&mut self, buffer: &[u8]) -> io::Result<usize> {
        let next_length = self
            .bytes
            .len()
            .checked_add(buffer.len())
            .ok_or_else(|| io::Error::other("engine output byte count overflow"))?;
        if next_length > self.maximum_bytes {
            return Err(io::Error::other(format!(
                "engine output exceeds {} bytes",
                self.maximum_bytes
            )));
        }
        self.bytes.extend_from_slice(buffer);
        Ok(buffer.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("adr-example-semantics-rust: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> EngineResult<()> {
    let arguments = parse_arguments()?;
    let bootstrap = JsonLimits::corpus_bootstrap();
    let corpus_bytes = read_bounded(&arguments.corpus, bootstrap.maximum_input_bytes)?;
    let corpus_sha256 = sha256_hex(&corpus_bytes);
    let corpus_value = parse_strict(&corpus_bytes, bootstrap)?;
    let corpus: Corpus = serde_json::from_value(corpus_value)
        .map_err(|error| EngineError::corpus(format!("corpus shape is invalid: {error}")))?;
    corpus.validate(corpus_bytes.len())?;
    let decision_set = verify_decision_set(&arguments.repo_root, &corpus)?;
    let engine_source_identities = collect_engine_source_identities(&arguments.repo_root)?;

    let registry = corpus
        .diagnostic_registry
        .iter()
        .map(String::as_str)
        .collect::<BTreeSet<_>>();
    let mut repository = SourceRepository::new(&arguments.repo_root, corpus.limits)?;
    let mut cases = Vec::with_capacity(corpus.cases.len());
    let mut source_identities = Vec::with_capacity(corpus.cases.len());
    let mut mutation_count = 0_usize;

    for case in &corpus.cases {
        decision_set.verify_source(&case.source)?;
        let document = repository.load_document(&case.source)?;
        validate_bounded_fixture(&case.profile, &case.bounded_fixture)?;
        let evaluation = evaluate(&case.profile, &document, &case.bounded_fixture)?;
        verify_evaluation(
            &case.id,
            &evaluation,
            case.expected_profile_result,
            case.production_admission,
            &case.expected_diagnostics,
            case.payload_interpreted,
            &registry,
        )?;

        let mut mutation_results = Vec::with_capacity(case.mutations.len());
        for mutation in &case.mutations {
            let mut mutated_document = document.clone();
            let mut mutated_fixture = case.bounded_fixture.clone();
            let target = match mutation.patch.target {
                PatchTarget::Document => &mut mutated_document,
                PatchTarget::BoundedFixture => &mut mutated_fixture,
            };
            apply_patch(target, &mutation.patch)?;
            mutated_document = enforce_mutated_limits(
                &mutated_document,
                corpus.limits.json(corpus.limits.maximum_json_fence_bytes),
            )?;
            mutated_fixture = enforce_mutated_limits(
                &mutated_fixture,
                corpus.limits.json(corpus.limits.maximum_json_fence_bytes),
            )?;
            validate_bounded_fixture(&case.profile, &mutated_fixture)?;
            let mutated = evaluate(&case.profile, &mutated_document, &mutated_fixture)?;
            verify_evaluation(
                &mutation.id,
                &mutated,
                mutation.expected_profile_result,
                mutation.production_admission,
                &mutation.expected_diagnostics,
                mutation.payload_interpreted,
                &registry,
            )?;
            mutation_results.push(MutationResult {
                id: mutation.id.clone(),
                profile_result: mutated.profile_result,
                production_admission: mutated.production_admission,
                diagnostics: mutated.diagnostics,
                payload_interpreted: mutated.payload_interpreted,
            });
            mutation_count = mutation_count
                .checked_add(1)
                .ok_or_else(|| EngineError::semantic("mutation count overflow"))?;
        }

        source_identities.push(SourceIdentity {
            case_id: case.id.clone(),
            path: case.source.path.clone(),
            json_fence_ordinal: case.source.json_fence_ordinal,
            adr_byte_length: case.source.adr_byte_length,
            adr_sha256: case.source.adr_sha256.clone(),
            fence_byte_length: case.source.fence_byte_length,
            fence_sha256: case.source.fence_sha256.clone(),
        });
        cases.push(CaseResult {
            id: case.id.clone(),
            profile_result: evaluation.profile_result,
            production_admission: evaluation.production_admission,
            diagnostics: evaluation.diagnostics,
            payload_interpreted: evaluation.payload_interpreted,
            mutations: mutation_results,
        });
    }
    repository.verify_exact_fence_coverage()?;

    let self_tests = if arguments.self_test {
        Some(run_self_tests()?)
    } else {
        None
    };
    let result = ResultDocument {
        schema: RESULT_SCHEMA,
        schema_version: 1,
        engine: "rust",
        semantic_claim: "local-prototype-only",
        corpus_sha256,
        decision_set_binding: decision_set.binding,
        case_count: cases.len(),
        mutation_count,
        source_identities,
        engine_source_identities,
        cases,
        self_tests,
    };
    let mut output = BoundedOutput::new(corpus.limits.maximum_engine_output_bytes);
    serde_json::to_writer(&mut output, &result)
        .map_err(|error| EngineError::json(format!("serializing result: {error}")))?;
    let output = output.into_bytes();
    let stdout = io::stdout();
    let mut lock = stdout.lock();
    lock.write_all(&output)
        .and_then(|()| lock.write_all(b"\n"))
        .map_err(|error| EngineError::io("writing stdout", error))
}

fn parse_arguments() -> EngineResult<Arguments> {
    let mut arguments = env::args_os();
    let _program = arguments.next();
    let mut corpus = None;
    let mut repo_root = None;
    let mut self_test = false;
    while let Some(argument) = arguments.next() {
        match argument.to_str() {
            Some("--corpus") => {
                if corpus.is_some() {
                    return Err(EngineError::input("--corpus was provided more than once"));
                }
                corpus = Some(next_path(&mut arguments, "--corpus")?);
            }
            Some("--repo-root") => {
                if repo_root.is_some() {
                    return Err(EngineError::input(
                        "--repo-root was provided more than once",
                    ));
                }
                repo_root = Some(next_path(&mut arguments, "--repo-root")?);
            }
            Some("--self-test") if !self_test => self_test = true,
            Some("--self-test") => {
                return Err(EngineError::input(
                    "--self-test was provided more than once",
                ));
            }
            Some(other) => {
                return Err(EngineError::input(format!(
                    "unknown argument {other:?}; expected --corpus, --repo-root, or --self-test"
                )));
            }
            None => return Err(EngineError::input("argument is not valid UTF-8")),
        }
    }
    Ok(Arguments {
        corpus: corpus.ok_or_else(|| EngineError::input("missing --corpus PATH"))?,
        repo_root: repo_root.ok_or_else(|| EngineError::input("missing --repo-root PATH"))?,
        self_test,
    })
}

fn next_path(arguments: &mut impl Iterator<Item = OsString>, flag: &str) -> EngineResult<PathBuf> {
    let value = arguments
        .next()
        .ok_or_else(|| EngineError::input(format!("{flag} requires a path")))?;
    if value.is_empty() {
        return Err(EngineError::input(format!("{flag} path is empty")));
    }
    Ok(PathBuf::from(value))
}

fn enforce_mutated_limits(value: &Value, limits: JsonLimits) -> EngineResult<Value> {
    let encoded = serde_json::to_vec(value)
        .map_err(|error| EngineError::json(format!("serializing mutated value: {error}")))?;
    parse_strict(&encoded, limits)
        .map_err(|error| EngineError::corpus(format!("mutated JSON exceeds bounds: {error}")))
}

fn verify_evaluation(
    owner: &str,
    actual: &Evaluation,
    expected_result: ProfileResult,
    expected_admission: ProductionAdmission,
    expected_diagnostics: &[String],
    expected_payload_interpreted: bool,
    registry: &BTreeSet<&str>,
) -> EngineResult<()> {
    for diagnostic in &actual.diagnostics {
        if !registry.contains(diagnostic.as_str()) {
            return Err(EngineError::semantic(format!(
                "{owner:?} emitted unregistered diagnostic {diagnostic:?}"
            )));
        }
    }
    if actual.profile_result != expected_result
        || actual.production_admission != expected_admission
        || actual.diagnostics != expected_diagnostics
        || actual.payload_interpreted != expected_payload_interpreted
    {
        return Err(EngineError::semantic(format!(
            "computed result differs from corpus expectation for {owner:?}: computed {actual:?}"
        )));
    }
    Ok(())
}

fn collect_engine_source_identities(root: &Path) -> EngineResult<Vec<EngineSourceIdentity>> {
    let source_directory_relative = format!("{ENGINE_ROOT}/src");
    let source_directory = root.join(&source_directory_relative);
    let directory_metadata = fs::symlink_metadata(&source_directory).map_err(|error| {
        EngineError::io(
            format!("inspecting Rust source directory {source_directory:?}"),
            error,
        )
    })?;
    if directory_metadata.file_type().is_symlink() || !directory_metadata.is_dir() {
        return Err(EngineError::input(
            "Rust source directory must be a regular non-symlink directory",
        ));
    }
    let mut paths = vec![
        format!("{ENGINE_ROOT}/Cargo.lock"),
        format!("{ENGINE_ROOT}/Cargo.toml"),
    ];
    for path in &paths {
        validate_engine_source_path(path)?;
    }
    for entry in fs::read_dir(&source_directory).map_err(|error| {
        EngineError::io(
            format!("reading Rust source directory {source_directory:?}"),
            error,
        )
    })? {
        let entry = entry.map_err(|error| {
            EngineError::io(
                format!("reading entry in Rust source directory {source_directory:?}"),
                error,
            )
        })?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| EngineError::input("Rust source filename is not valid UTF-8"))?;
        if !name.ends_with(".rs") {
            return Err(EngineError::input(format!(
                "unexpected non-Rust file in engine source directory: {name:?}"
            )));
        }
        let relative = format!("{source_directory_relative}/{name}");
        validate_engine_source_path(&relative)?;
        if paths.len() == MAXIMUM_ENGINE_SOURCE_FILES {
            return Err(EngineError::input(format!(
                "Rust engine source set exceeds {MAXIMUM_ENGINE_SOURCE_FILES} files"
            )));
        }
        paths.push(relative);
    }
    paths.sort();
    if paths.windows(2).any(|pair| pair[0] == pair[1]) {
        return Err(EngineError::semantic(
            "duplicate Rust engine source identity path",
        ));
    }
    let mut identities = Vec::with_capacity(paths.len());
    let mut aggregate_bytes = 0_usize;
    for relative in paths {
        let path = resolve_regular_relative_file(root, &relative)?;
        let bytes = read_bounded(&path, MAXIMUM_ENGINE_SOURCE_FILE_BYTES)?;
        aggregate_bytes = aggregate_bytes
            .checked_add(bytes.len())
            .ok_or_else(|| EngineError::semantic("engine source byte count overflow"))?;
        if aggregate_bytes > MAXIMUM_AGGREGATE_ENGINE_SOURCE_BYTES {
            return Err(EngineError::input(format!(
                "Rust engine source set exceeds {MAXIMUM_AGGREGATE_ENGINE_SOURCE_BYTES} bytes"
            )));
        }
        identities.push(EngineSourceIdentity {
            path: relative,
            byte_length: bytes.len(),
            sha256: sha256_hex(&bytes),
        });
    }
    Ok(identities)
}

fn validate_engine_source_path(relative: &str) -> EngineResult<()> {
    if relative.len() > MAXIMUM_ENGINE_SOURCE_PATH_BYTES {
        return Err(EngineError::input(format!(
            "Rust engine source path exceeds {MAXIMUM_ENGINE_SOURCE_PATH_BYTES} UTF-8 bytes"
        )));
    }
    Ok(())
}

fn run_self_tests() -> EngineResult<SelfTestResult> {
    let limits = JsonLimits::corpus_bootstrap();
    let duplicate_rejected = parse_strict(br#"{"a":1,"\u0061":2}"#, limits).is_err();
    let float_rejected = parse_strict(b"1e0", limits).is_err();

    let mut shallow = limits;
    shallow.maximum_json_depth = 1;
    let depth_rejected = parse_strict(br#"{"nested":{}}"#, shallow).is_err();

    let mut patch_target = json!({"a": 1});
    let missing_replace = crate::model::Patch {
        target: PatchTarget::Document,
        op: crate::model::PatchOperation::Replace,
        path: "/missing".to_owned(),
        value: Some(json!(2)),
    };
    let missing_patch_rejected = apply_patch(&mut patch_target, &missing_replace).is_err();
    let unknown_profile_rejected = evaluate("UNKNOWN_PROFILE", &json!({}), &json!({})).is_err();

    let pending = evaluate(
        "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
        &json!({"allocates_output_slot": true, "state": "PENDING_INTENT_ONLY"}),
        &json!({"expected_state": "PENDING_INTENT_ONLY", "output_allocation_permitted": false}),
    )?;
    let pending_guard_detected = pending.profile_result == ProfileResult::Reject
        && pending.diagnostics == ["PENDING_STATE_ALLOCATES_OUTPUT"];

    let contract = evaluate(
        "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
        &json!({
            "authority_realm_key": {
                "server_authority_principal_id": "ncp-authority-a",
                "stable_realm_id": "realm-a"
            },
            "wire_version": "1.0",
            "stable_core_digest": "163acc57d8a62b66"
        }),
        &json!({
            "authenticated_realm_key": {
                "server_authority_principal_id": "ncp-authority-a",
                "stable_realm_id": "realm-a"
            },
            "expected_wire_version": "1.0",
            "digest_algorithm": "sha256"
        }),
    )?;
    let digest_guard_detected = contract.profile_result == ProfileResult::Reject
        && contract.diagnostics == ["STABLE_CORE_DIGEST_INVALID"];

    let wire = evaluate(
        "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
        &json!({
            "authority_realm_key": {
                "server_authority_principal_id": "ncp-authority-a",
                "stable_realm_id": "realm-a"
            },
            "wire_version": "0.8",
            "stable_core_digest":
                "sha256:1111111111111111111111111111111111111111111111111111111111111111"
        }),
        &json!({
            "authenticated_realm_key": {
                "server_authority_principal_id": "ncp-authority-a",
                "stable_realm_id": "realm-a"
            },
            "expected_wire_version": "1.0",
            "digest_algorithm": "sha256"
        }),
    )?;
    let wire_guard_detected = wire.profile_result == ProfileResult::Reject
        && wire.diagnostics == ["WIRE_VERSION_MISMATCH"];

    let security = evaluate(
        "ADR009_SECURITY_STATE_PROJECTION_V1",
        &json!({
            "authority_realm": {
                "server_authority_principal": "spiffe://ncp.example/body-server",
                "stable_realm_id": "plant-a"
            },
            "profile": "ncp-production-ingress-v1",
            "security_epoch": 12,
            "revocation_epoch": 0,
            "principals": [{
                "principal_id": "body-a",
                "role": "body",
                "planes": ["action"]
            }],
            "key_epochs": [{
                "kid": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "algorithm": "Ed25519",
                "epoch": 12
            }]
        }),
        &json!({
            "authenticated_authority_realm": {
                "server_authority_principal": "spiffe://ncp.example/body-server",
                "stable_realm_id": "plant-a"
            },
            "required_profile": "ncp-production-ingress-v1",
            "required_key_algorithm": "Ed25519",
            "maximum_security_epoch": 9007199254740991_u64
        }),
    )?;
    let revocation_guard_detected = security.profile_result == ProfileResult::Reject
        && security.diagnostics == ["REVOCATION_EPOCH_INVALID"];

    let qos = evaluate(
        "ADR010_INVALID_ACTION_QOS_PROFILE_V1",
        &json!({
            "authority_realm_key": {
                "server_authority_principal_id": "ncp-authority-a",
                "stable_realm_id": "realm-a"
            },
            "plane": "action",
            "route": "realm-a/session/a/command/b",
            "profile_id": "ncp-action-v1",
            "capacity_per_stream": 0,
            "ordering": "strict_stream_sequence",
            "retention": "until_terminal_disposition_or_expiry",
            "overload": "reject_new_active_and_emit_disposition",
            "fail_safe_priority": ["estop", "hold", "active"]
        }),
        &json!({
            "authenticated_realm_key": {
                "server_authority_principal_id": "ncp-authority-a",
                "stable_realm_id": "realm-a"
            },
            "maximum_capacity_per_stream": 1,
            "required_fail_safe_priority": ["estop", "hold", "active"]
        }),
    )?;
    let capacity_guard_detected =
        qos.profile_result == ProfileResult::Reject && qos.diagnostics == ["QOS_CAPACITY_INVALID"];

    let controls = [
        duplicate_rejected,
        float_rejected,
        depth_rejected,
        missing_patch_rejected,
        unknown_profile_rejected,
        pending_guard_detected,
        digest_guard_detected,
        wire_guard_detected,
        revocation_guard_detected,
        capacity_guard_detected,
    ];
    let review_packet_controls = review_packet_binding_self_test()?;
    let executed = controls.len() + review_packet_controls;
    let detected = controls.iter().filter(|detected| **detected).count() + review_packet_controls;
    if detected != executed {
        return Err(EngineError::semantic(format!(
            "self-test detected {detected} of {executed} hostile controls",
        )));
    }
    Ok(SelfTestResult { executed, detected })
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::BoundedOutput;

    #[test]
    fn bounded_output_rejects_a_write_beyond_the_limit_without_partial_growth() {
        let mut output = BoundedOutput::new(4);
        assert!(output.write_all(b"ncp").is_ok());
        assert!(output.write_all(b"10").is_err());
        assert_eq!(output.into_bytes(), b"ncp");
    }
}
