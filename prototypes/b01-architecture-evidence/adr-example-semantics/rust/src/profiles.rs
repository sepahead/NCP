use std::collections::BTreeSet;

use serde_json::Value;

use crate::error::{EngineError, EngineResult};
use crate::model::{ProductionAdmission, ProfileResult};
use crate::strict_json::{parse_strict, JsonLimits};

const PLANT_PROFILE: &str = "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1";
const CONTRACT_IDENTITY: &str = "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1";
const FORWARDING_WRAPPER: &str = "ADR003_FLATTENED_FORWARDING_WRAPPER_V1";
const PROTECTED_HEADER: &str = "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1";
const PENDING_RESERVATION: &str = "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1";
const DECLARE_STREAM: &str = "ADR005_DECLARE_STREAM_EXCERPT_V1";
const UNDECLARED_FRAME: &str = "ADR005_UNDECLARED_FRAME_V1";
const BODY_LEASE: &str = "ADR006_BODY_LEASE_EXCERPT_V1";
const STALE_SELF_ISSUED_LEASE: &str = "ADR006_STALE_SELF_ISSUED_LEASE_V1";
const DISPOSITION_QUERY: &str = "ADR007_DISPOSITION_QUERY_PROJECTION_V1";
const RECEIVED_DISPOSITION: &str = "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1";
const INVALID_DISPOSITION: &str = "ADR007_INVALID_DISPOSITION_V1";
const RAW_EXTENSION_CHUNK: &str = "ADR008_RAW_CHUNK_PROJECTION_V1";
const ASSESSMENT_ENVELOPE: &str = "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1";
const POLICY_INJECTION: &str = "ADR008_GALADRIEL_POLICY_INJECTION_V1";
const SECURITY_STATE: &str = "ADR009_SECURITY_STATE_PROJECTION_V1";
const INVALID_SECURITY_STATE: &str = "ADR009_INVALID_SECURITY_STATE_V1";
const ACTION_QOS: &str = "ADR010_ACTION_QOS_PROFILE_V1";
const INVALID_ACTION_QOS: &str = "ADR010_INVALID_ACTION_QOS_PROFILE_V1";
const GATED_INTENT: &str = "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1";
const COMMAND_IDENTITY: &str = "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1";
const EFFECT_PATH_FENCING: &str = "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1";
const MAXIMUM_JSON_SAFE_INTEGER: u64 = 9_007_199_254_740_991;

#[derive(Debug)]
pub(crate) struct Evaluation {
    pub(crate) profile_result: ProfileResult,
    pub(crate) production_admission: ProductionAdmission,
    pub(crate) diagnostics: Vec<String>,
    pub(crate) payload_interpreted: bool,
}

pub(crate) fn evaluate(
    profile: &str,
    document: &Value,
    fixture: &Value,
) -> EngineResult<Evaluation> {
    let mut diagnostics = BTreeSet::new();
    match profile {
        PLANT_PROFILE => evaluate_plant(document, fixture, &mut diagnostics)?,
        CONTRACT_IDENTITY => evaluate_contract_identity(document, fixture, &mut diagnostics)?,
        FORWARDING_WRAPPER => evaluate_forwarding_wrapper(document, fixture, &mut diagnostics)?,
        PROTECTED_HEADER => evaluate_protected_header(document, fixture, &mut diagnostics)?,
        PENDING_RESERVATION => evaluate_pending_reservation(document, fixture, &mut diagnostics)?,
        DECLARE_STREAM => evaluate_declare_stream(document, fixture, &mut diagnostics)?,
        UNDECLARED_FRAME => evaluate_undeclared_frame(document, fixture, &mut diagnostics)?,
        BODY_LEASE | STALE_SELF_ISSUED_LEASE => {
            evaluate_lease(document, fixture, &mut diagnostics)?;
        }
        DISPOSITION_QUERY => evaluate_disposition_query(document, fixture, &mut diagnostics)?,
        RECEIVED_DISPOSITION | INVALID_DISPOSITION => {
            evaluate_disposition(document, fixture, &mut diagnostics)?;
        }
        RAW_EXTENSION_CHUNK => {
            evaluate_raw_extension_chunk(document, fixture, &mut diagnostics)?;
        }
        ASSESSMENT_ENVELOPE => {
            evaluate_assessment_envelope(document, fixture, &mut diagnostics)?;
        }
        POLICY_INJECTION => evaluate_policy_injection(document, fixture, &mut diagnostics)?,
        SECURITY_STATE => {
            evaluate_security_state(document, fixture, &mut diagnostics)?;
        }
        INVALID_SECURITY_STATE => {
            evaluate_invalid_security_state(document, fixture, &mut diagnostics)?;
        }
        ACTION_QOS | INVALID_ACTION_QOS => {
            evaluate_action_qos(document, fixture, &mut diagnostics)?;
        }
        GATED_INTENT => evaluate_gated_intent(document, fixture, &mut diagnostics)?,
        COMMAND_IDENTITY => evaluate_command_identity(document, fixture, &mut diagnostics)?,
        EFFECT_PATH_FENCING => {
            evaluate_effect_path_fencing(document, fixture, &mut diagnostics)?;
        }
        unknown => {
            return Err(EngineError::corpus(format!(
                "unknown semantic profile {unknown:?}"
            )));
        }
    }

    let rejected = !diagnostics.is_empty();
    let profile_result = if rejected {
        ProfileResult::Reject
    } else if profile == PENDING_RESERVATION {
        ProfileResult::MatchNonWireExcerpt
    } else {
        ProfileResult::MatchNonAuthorizingExcerpt
    };
    let production_admission = if profile == PENDING_RESERVATION {
        ProductionAdmission::NotApplicable
    } else if rejected || profile == GATED_INTENT {
        ProductionAdmission::Reject
    } else {
        ProductionAdmission::NotEvaluated
    };
    let payload_interpreted = profile != FORWARDING_WRAPPER;

    Ok(Evaluation {
        profile_result,
        production_admission,
        diagnostics: diagnostics.into_iter().map(str::to_owned).collect(),
        payload_interpreted,
    })
}

fn evaluate_plant(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let expected_version = fixture_str(fixture, "/expected_ncp_version")?;
    let expected_kind = fixture_str(fixture, "/expected_session_kind")?;
    let expected_commander = fixture_str(fixture, "/expected_commander_principal_id")?;
    let algorithm = fixture_str(fixture, "/digest_algorithm")?;
    let version_matches = string_at(document, "/ncp_version")
        .and_then(parse_stable_wire_major)
        .zip(parse_stable_wire_major(expected_version))
        .is_some_and(|(actual, expected)| actual == expected);
    if !version_matches {
        diagnostics.insert("NCP_VERSION_MISMATCH");
    }
    if string_at(document, "/kind") != Some(expected_kind) {
        diagnostics.insert("SESSION_KIND_MISMATCH");
    }
    if string_at(document, "/commander_identity/principal_id") != Some(expected_commander) {
        diagnostics.insert("COMMANDER_PRINCIPAL_MISMATCH");
    }
    if document.get("network").is_some() || document.get("sim").is_some() {
        diagnostics.insert("PLANT_CONTAINS_SIMULATION_ONLY_MEMBER");
    }
    if !string_at(document, "/plant_profile_digest")
        .is_some_and(|digest| is_prefixed_digest(digest, algorithm))
    {
        diagnostics.insert("PLANT_PROFILE_MISSING");
    }
    if !string_at(document, "/security_state_digest")
        .is_some_and(|digest| is_prefixed_digest(digest, algorithm))
    {
        diagnostics.insert("PLANT_SECURITY_CONTEXT_MISSING");
    }
    Ok(())
}

fn evaluate_contract_identity(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    if string_at(document, "/wire_version")
        .and_then(parse_stable_wire_major)
        .is_none_or(|major| major != 1)
    {
        diagnostics.insert("WIRE_VERSION_MISMATCH");
    }
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR002 fixture is missing authenticated realm key"))?;
    match document.get("authority_realm_key") {
        Some(actual) if authority_realm_key_has_required_shape(actual) => {
            if actual != expected_realm {
                diagnostics.insert("AUTHORITY_REALM_KEY_MISMATCH");
            }
        }
        Some(_) | None => {
            diagnostics.insert("AUTHORITY_REALM_KEY_MISSING");
        }
    }
    let algorithm = fixture_str(fixture, "/digest_algorithm")?;
    let expected_digest = fixture_str(fixture, "/expected_stable_core_digest")?;
    let stable_core_matches = match document.get("stable_core_digest") {
        None | Some(Value::Null) => {
            diagnostics.insert("STABLE_CORE_DIGEST_MISSING_OR_NULL");
            false
        }
        Some(Value::String(digest)) if !is_prefixed_digest(digest, algorithm) => {
            diagnostics.insert("STABLE_CORE_DIGEST_INVALID");
            false
        }
        Some(Value::String(digest)) if digest != expected_digest => {
            diagnostics.insert("STABLE_CORE_DIGEST_MISMATCH");
            false
        }
        Some(Value::String(_)) => true,
        Some(_) => {
            diagnostics.insert("STABLE_CORE_DIGEST_INVALID");
            false
        }
    };
    if document.get("contract_hash").is_some() && !stable_core_matches {
        diagnostics.insert("COMPACT_HASH_NOT_COMPATIBILITY_IDENTITY");
    }
    Ok(())
}

fn parse_stable_wire_major(value: &str) -> Option<u64> {
    let mut parts = value.split('.');
    let major = parse_canonical_u64(parts.next()?)?;
    if let Some(minor) = parts.next() {
        parse_canonical_u64(minor)?;
    }
    if parts.next().is_some() || major == 0 {
        return None;
    }
    Some(major)
}

fn parse_canonical_u64(value: &str) -> Option<u64> {
    if value.is_empty()
        || value.len() > 20
        || !value.bytes().all(|byte| byte.is_ascii_digit())
        || (value.len() > 1 && value.starts_with('0'))
    {
        return None;
    }
    value.parse().ok()
}

fn evaluate_forwarding_wrapper(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let required_algorithm = fixture_str(fixture, "/required_algorithm")?;
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR003 fixture is missing authenticated realm key"))?;
    let expected_signature_bytes = fixture_u64(fixture, "/expected_signature_bytes")?;
    let signature_verifies = fixture_bool(fixture, "/signature_verifies")?;

    if let Some(header) = document.get("header") {
        diagnostics.insert("UNPROTECTED_HEADER_FORBIDDEN");
        if header.get("jku").is_some() {
            diagnostics.insert("REMOTE_JKU_FORBIDDEN");
        }
    }

    let decoded_header = string_at(document, "/protected")
        .and_then(|encoded| decode_base64url(encoded, 4_096).ok())
        .and_then(|bytes| {
            let limits = JsonLimits {
                maximum_input_bytes: 4_096,
                maximum_json_depth: 8,
                maximum_json_nodes: 128,
                maximum_object_members: 64,
                maximum_array_items: 64,
                maximum_key_utf8_bytes: 128,
                maximum_string_utf8_bytes: 1_024,
                maximum_total_string_utf8_bytes: 4_096,
                maximum_integer_characters: 16,
                allow_floats: false,
            };
            parse_strict(&bytes, limits).ok()
        });
    match decoded_header {
        Some(Value::Object(header)) => {
            match header.get("alg") {
                None => {
                    diagnostics.insert("ALGORITHM_LABEL_REQUIRED");
                }
                Some(Value::String(actual)) if actual != required_algorithm => {
                    diagnostics.insert("ALGORITHM_LABEL_FORBIDDEN");
                }
                Some(Value::String(_)) => {}
                Some(_) => {
                    diagnostics.insert("ALGORITHM_LABEL_FORBIDDEN");
                }
            }
            match header.get("authority_realm_key") {
                Some(actual) if authority_realm_key_has_required_shape(actual) => {
                    if actual != expected_realm {
                        diagnostics.insert("AUTHORITY_REALM_KEY_MISMATCH");
                    }
                }
                Some(_) | None => {
                    diagnostics.insert("AUTHORITY_REALM_KEY_MISSING");
                }
            }
            if header.get("jku").is_some() {
                diagnostics.insert("REMOTE_JKU_FORBIDDEN");
            }
        }
        Some(_) | None => {
            diagnostics.insert("PROTECTED_HEADER_NOT_JSON");
        }
    }

    let expected_signature_bytes = usize::try_from(expected_signature_bytes)
        .map_err(|_| EngineError::corpus("ADR003 signature length does not fit usize"))?;
    let signature_has_expected_length = string_at(document, "/signature")
        .and_then(|encoded| decode_base64url(encoded, expected_signature_bytes).ok())
        .is_some_and(|bytes| bytes.len() == expected_signature_bytes);
    if !signature_has_expected_length {
        diagnostics.insert("SIGNATURE_LENGTH_INVALID");
    } else if !signature_verifies {
        diagnostics.insert("SIGNATURE_NOT_VALID");
    }
    Ok(())
}

fn evaluate_protected_header(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let required_algorithm = fixture_str(fixture, "/required_algorithm")?;
    match document.get("alg") {
        None => {
            diagnostics.insert("ALGORITHM_LABEL_REQUIRED");
        }
        Some(Value::String(actual)) if actual != required_algorithm => {
            diagnostics.insert("ALGORITHM_LABEL_FORBIDDEN");
        }
        Some(Value::String(_)) => {}
        Some(_) => {
            diagnostics.insert("ALGORITHM_LABEL_FORBIDDEN");
        }
    }
    if document.get("jku").is_some() {
        diagnostics.insert("REMOTE_JKU_FORBIDDEN");
    }
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR003 fixture is missing authenticated realm key"))?;
    match document.get("authority_realm_key") {
        Some(actual) if authority_realm_key_has_required_shape(actual) => {
            if actual != expected_realm {
                diagnostics.insert("AUTHORITY_REALM_KEY_MISMATCH");
            }
        }
        Some(_) | None => {
            diagnostics.insert("AUTHORITY_REALM_KEY_MISSING");
        }
    }
    if string_at(document, "/route") != Some(fixture_str(fixture, "/expected_route")?) {
        diagnostics.insert("REALM_ROUTE_MISMATCH");
    }
    if string_at(document, "/audience") != Some(fixture_str(fixture, "/expected_audience")?) {
        diagnostics.insert("PROTECTED_HEADER_AUDIENCE_MISMATCH");
    }
    Ok(())
}

fn evaluate_pending_reservation(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let expected_state = fixture_str(fixture, "/expected_state")?;
    let output_permitted = fixture_bool(fixture, "/output_allocation_permitted")?;
    if string_at(document, "/state") != Some(expected_state) {
        diagnostics.insert("PENDING_STATE_INVALID");
    }
    match document.get("allocates_output_slot") {
        Some(Value::Bool(actual)) if *actual && !output_permitted => {
            diagnostics.insert("PENDING_STATE_ALLOCATES_OUTPUT");
        }
        Some(Value::Bool(_)) => {}
        Some(_) | None => {
            diagnostics.insert("OUTPUT_ALLOCATION_FLAG_INVALID");
        }
    }
    Ok(())
}

fn evaluate_declare_stream(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    if string_at(document, "/ncp_version")
        .and_then(parse_stable_wire_major)
        .is_none_or(|major| major != 1)
    {
        diagnostics.insert("NCP_VERSION_MISMATCH");
    }
    if string_at(document, "/kind") != Some("declare_stream") {
        diagnostics.insert("MESSAGE_KIND_MISMATCH");
    }
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR005 fixture is missing authenticated realm"))?;
    if !realm_and_route_match(
        document,
        expected_realm,
        fixture_str(fixture, "/expected_route")?,
    ) {
        diagnostics.insert("REALM_ROUTE_MISMATCH");
    }
    if document.get("sequence_start").and_then(Value::as_u64) != Some(1) {
        diagnostics.insert("STREAM_SEQUENCE_START_INVALID");
    }
    if string_at(document, "/publisher_principal_id")
        != Some(fixture_str(
            fixture,
            "/authenticated_publisher_principal_id",
        )?)
    {
        diagnostics.insert("PUBLISHER_PRINCIPAL_MISMATCH");
    }
    let live_epochs = fixture_string_array(fixture, "/live_declaration_epoch_ids")?;
    match string_at(document, "/stream_epoch") {
        None | Some("") => {
            diagnostics.insert("STREAM_EPOCH_REQUIRED");
        }
        Some(epoch) if live_epochs.contains(epoch) => {
            diagnostics.insert("STREAM_EPOCH_ALREADY_LIVE");
        }
        Some(_) => {}
    }
    Ok(())
}

fn evaluate_undeclared_frame(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR005 fixture is missing authenticated realm"))?;
    if document.get("authority_realm_key") != Some(expected_realm) {
        diagnostics.insert("REALM_REQUIRED");
    }
    let epoch = string_at(document, "/stream/epoch");
    let live = fixture
        .pointer("/live_declaration_epoch_ids")
        .and_then(Value::as_array)
        .ok_or_else(|| EngineError::corpus("ADR005 fixture has no declaration epoch array"))?;
    if !epoch.is_some_and(|candidate| live.iter().any(|item| item.as_str() == Some(candidate))) {
        diagnostics.insert("STREAM_DECLARATION_NOT_LIVE");
    }
    Ok(())
}

fn evaluate_lease(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let body = fixture_str(fixture, "/enrolled_body_principal_id")?;
    if string_at(document, "/issuer_principal_id") != Some(body) {
        diagnostics.insert("LEASE_ISSUER_NOT_BODY");
    }
    let current = fixture
        .pointer("/current_lease")
        .ok_or_else(|| EngineError::corpus("ADR006 fixture is missing current lease"))?;
    let fields = [
        "session_generation",
        "term",
        "lease_id",
        "holder_principal_id",
        "holder_entity_id",
    ];
    let is_current = fields
        .iter()
        .all(|field| document.get(*field) == current.get(*field));
    let evaluation_time = fixture_u64(fixture, "/evaluation_utc_ms")?;
    let live_now = document
        .get("issued_at_utc_ms")
        .and_then(json_safe_u64)
        .zip(document.get("expires_at_utc_ms").and_then(json_safe_u64))
        .is_some_and(|(issued, expires)| issued <= evaluation_time && evaluation_time < expires);
    if !is_current || !live_now {
        diagnostics.insert("LEASE_NOT_CURRENT");
    }
    Ok(())
}

fn evaluate_disposition_query(
    document: &Value,
    _fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    require_exact_projection_members(
        document,
        &[
            "branches",
            "early_effect_mode",
            "effect_boundary_rechecks_currentness",
            "estop_reservation_rechecks_currentness",
            "hold_admission_precedes_effect",
            "post_effect_admission_mode",
            "query_coordinate_bound",
            "rejected_candidate_cannot_select_local_hold",
            "result_projection_omits_authentication",
            "retained_requires_complete_chain",
            "retired_proves_effect",
        ],
        "DISPOSITION_RESULT_PROJECTION_INVALID",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "query_coordinate_bound",
        true,
        "DISPOSITION_QUERY_COORDINATE_INVALID",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "result_projection_omits_authentication",
        true,
        "DISPOSITION_RESULT_PROJECTION_INVALID",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "retained_requires_complete_chain",
        true,
        "DISPOSITION_RETAINED_CHAIN_REQUIRED",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "retired_proves_effect",
        false,
        "DISPOSITION_RETIRED_EFFECT_FORBIDDEN",
        diagnostics,
    );
    if document.get("early_effect_mode").and_then(Value::as_str) != Some("ESTOP_ONLY") {
        diagnostics.insert("FAIL_SAFE_EARLY_EFFECT_MODE_INVALID");
    }
    require_exact_projection_member(
        document,
        "estop_reservation_rechecks_currentness",
        true,
        "ESTOP_RESERVATION_CURRENTNESS_RECHECK_REQUIRED",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "effect_boundary_rechecks_currentness",
        true,
        "FAIL_SAFE_EFFECT_BOUNDARY_RECHECK_REQUIRED",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "hold_admission_precedes_effect",
        true,
        "HOLD_ADMISSION_ORDER_INVALID",
        diagnostics,
    );
    require_exact_projection_member(
        document,
        "rejected_candidate_cannot_select_local_hold",
        true,
        "REJECTED_CANDIDATE_LOCAL_HOLD_FORBIDDEN",
        diagnostics,
    );
    if document
        .get("post_effect_admission_mode")
        .and_then(Value::as_str)
        != Some("ESTOP_ONLY")
    {
        diagnostics.insert("POST_EFFECT_ADMISSION_MODE_INVALID");
    }
    let expected = [
        "QUERY_FAILURE",
        "RETAINED_DISPOSITION",
        "RETIRED_DISPOSITION_COMMITMENT",
    ];
    if document
        .get("branches")
        .and_then(Value::as_array)
        .is_none_or(|branches| {
            branches.len() != expected.len()
                || branches
                    .iter()
                    .zip(expected)
                    .any(|(actual, expected)| actual.as_str() != Some(expected))
        })
    {
        diagnostics.insert("DISPOSITION_RESULT_BRANCHES_INVALID");
    }
    Ok(())
}

fn evaluate_disposition(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    if string_at(document, "/kind") != Some("command_disposition") {
        diagnostics.insert("MESSAGE_KIND_MISMATCH");
    }
    let state = string_at(document, "/state");
    let nonterminal = fixture_string_array(fixture, "/nonterminal_states")?;
    let terminal = fixture_string_array(fixture, "/terminal_states")?;
    let known_nonterminal = state.is_some_and(|candidate| nonterminal.contains(&candidate));
    let known_terminal = state.is_some_and(|candidate| terminal.contains(&candidate));
    if !known_nonterminal && !known_terminal {
        diagnostics.insert("DISPOSITION_STATE_UNKNOWN");
        if document.get("terminal").is_some() {
            diagnostics.insert("DISPOSITION_TERMINALITY_INVALID");
        }
        return Ok(());
    }
    if let Some(claimed_terminal) = document.get("terminal") {
        if claimed_terminal.as_bool() != Some(known_terminal) {
            diagnostics.insert("DISPOSITION_TERMINALITY_INVALID");
        }
    }
    Ok(())
}

fn evaluate_raw_extension_chunk(
    document: &Value,
    _fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    require_exact_projection_members(
        document,
        &[
            "activation_context_binds_clock_and_expiry",
            "activation_context_binds_processing_profiles",
            "callback_after_schema_reservation",
            "callback_boundary_state_before_entry",
            "complete_hash_once",
            "conflict_overwrites_bytes",
            "currentness_and_expiry_rechecked_before_callback",
            "currentness_and_expiry_rechecked_before_schema",
            "duplicate_copies_bytes",
            "entered_callback_releases_resources_before_resolution",
            "first_index_can_reserve",
            "header_class_registry_and_length_checked_before_reservation",
            "outer_encoding",
            "package_is_structured_frame",
            "receiver_activation_incarnation_bound",
            "reserve_before_copy",
            "retired_context_discloses_result",
            "slot_transition_orders_currentness_cut",
            "stable_slot_excludes_mutable_declarations",
            "terminal_lookup_precedes_work_admission",
            "terminal_tombstone_required",
        ],
        "EXTENSION_OUTER_ENCODING_INVALID",
        diagnostics,
    );
    if string_at(document, "/outer_encoding") != Some("BOUNDED_RAW_CHUNK") {
        diagnostics.insert("EXTENSION_OUTER_ENCODING_INVALID");
    }
    for (field, expected, diagnostic) in [
        (
            "package_is_structured_frame",
            false,
            "EXTENSION_PACKAGE_FRAME_NESTING_FORBIDDEN",
        ),
        (
            "first_index_can_reserve",
            true,
            "EXTENSION_FIRST_INDEX_RULE_INVALID",
        ),
        (
            "stable_slot_excludes_mutable_declarations",
            true,
            "EXTENSION_STABLE_SLOT_INVALID",
        ),
        (
            "receiver_activation_incarnation_bound",
            true,
            "EXTENSION_RECEIVER_ACTIVATION_INCARNATION_REQUIRED",
        ),
        (
            "activation_context_binds_processing_profiles",
            true,
            "EXTENSION_ACTIVATION_PROFILE_BINDING_REQUIRED",
        ),
        (
            "activation_context_binds_clock_and_expiry",
            true,
            "EXTENSION_ACTIVATION_TIME_BINDING_REQUIRED",
        ),
        (
            "header_class_registry_and_length_checked_before_reservation",
            true,
            "EXTENSION_HEADER_ADMISSION_INVALID",
        ),
        (
            "terminal_lookup_precedes_work_admission",
            true,
            "EXTENSION_TERMINAL_LOOKUP_ORDER_INVALID",
        ),
        (
            "retired_context_discloses_result",
            false,
            "EXTENSION_RETIRED_RESULT_DISCLOSURE_FORBIDDEN",
        ),
        (
            "reserve_before_copy",
            true,
            "EXTENSION_RESERVATION_ORDER_INVALID",
        ),
        (
            "slot_transition_orders_currentness_cut",
            true,
            "EXTENSION_CURRENTNESS_CUT_ORDER_INVALID",
        ),
        (
            "duplicate_copies_bytes",
            false,
            "EXTENSION_DUPLICATE_COPY_FORBIDDEN",
        ),
        (
            "conflict_overwrites_bytes",
            false,
            "EXTENSION_CONFLICT_OVERWRITE_FORBIDDEN",
        ),
        (
            "complete_hash_once",
            true,
            "EXTENSION_COMPLETE_HASH_RULE_INVALID",
        ),
        (
            "currentness_and_expiry_rechecked_before_schema",
            true,
            "EXTENSION_PRE_SCHEMA_CURRENTNESS_RECHECK_REQUIRED",
        ),
        (
            "callback_after_schema_reservation",
            true,
            "EXTENSION_SCHEMA_RESERVATION_REQUIRED",
        ),
        (
            "currentness_and_expiry_rechecked_before_callback",
            true,
            "EXTENSION_PRE_CALLBACK_CURRENTNESS_RECHECK_REQUIRED",
        ),
        (
            "callback_boundary_state_before_entry",
            true,
            "EXTENSION_CALLBACK_BOUNDARY_STATE_REQUIRED",
        ),
        (
            "entered_callback_releases_resources_before_resolution",
            false,
            "EXTENSION_CALLBACK_RESOURCE_LIFETIME_INVALID",
        ),
        (
            "terminal_tombstone_required",
            true,
            "EXTENSION_TERMINAL_TOMBSTONE_REQUIRED",
        ),
    ] {
        require_exact_projection_member(document, field, expected, diagnostic, diagnostics);
    }
    Ok(())
}

fn evaluate_assessment_envelope(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    if string_at(document, "/extension_id") != Some("org.sepahead.galadriel.assessment") {
        diagnostics.insert("EXTENSION_ID_MISMATCH");
    }
    if string_at(document, "/schema_version") != Some("1") {
        diagnostics.insert("EXTENSION_SCHEMA_VERSION_MISMATCH");
    }
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR008 fixture is missing authenticated realm"))?;
    if !realm_and_route_match(
        document,
        expected_realm,
        fixture_str(fixture, "/expected_route")?,
    ) {
        diagnostics.insert("REALM_ROUTE_MISMATCH");
    }
    if string_at(document, "/producer_principal_id")
        != Some(fixture_str(fixture, "/extension_assessor_principal_id")?)
    {
        diagnostics.insert("EXTENSION_PRODUCER_ROLE_INVALID");
    }
    if string_at(document, "/audience_principal_id")
        != Some(fixture_str(fixture, "/extension_receiver_principal_id")?)
    {
        diagnostics.insert("EXTENSION_RECEIVER_ROLE_INVALID");
    }
    let assessments = document
        .pointer("/lifecycle_outcome_evidence/assessments")
        .and_then(Value::as_array);
    match assessments {
        Some(items) if !items.is_empty() => {
            for assessment in items {
                if string_at(assessment, "/kind") != Some("EVALUATED_DEFAULT_REPORT")
                    || string_at(assessment, "/report_evidence/verdict/verdict")
                        != Some("attributed_inconsistency")
                    || string_at(assessment, "/report_evidence/verdict/magnitude")
                        .is_none_or(str::is_empty)
                {
                    diagnostics.insert("ASSESSMENT_MAGNITUDE_REQUIRED");
                }
                if !typed_digest_matches(
                    assessment.pointer("/assessment_binding_identity"),
                    "galadriel-assessment-binding-v2",
                ) {
                    diagnostics.insert("DIGEST_ENCODING_INVALID");
                }
            }
        }
        Some(_) | None => {
            diagnostics.insert("ASSESSMENT_MAGNITUDE_REQUIRED");
        }
    }
    if !typed_digest_matches(
        document.get("release_suite_identity"),
        "galadriel-release-suite-v1",
    ) || [
        "manifest_digest",
        "extension_schema_digest",
        "model_digest",
        "configuration_digest",
        "evidence_schema_digest",
    ]
    .iter()
    .any(|field| {
        !document
            .get(*field)
            .and_then(Value::as_str)
            .is_some_and(|digest| is_prefixed_digest(digest, "sha256"))
    }) {
        diagnostics.insert("DIGEST_ENCODING_INVALID");
    }
    Ok(())
}

fn evaluate_policy_injection(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR008 fixture is missing authenticated realm"))?;
    if document.get("authority_realm_key") != Some(expected_realm) {
        diagnostics.insert("REALM_REQUIRED");
    }
    if string_at(document, "/producer_principal_id")
        != Some(fixture_str(fixture, "/extension_assessor_principal_id")?)
    {
        diagnostics.insert("EXTENSION_PRODUCER_ROLE_INVALID");
    }
    if ["effect", "calibrated_for_policy", "state_usability"]
        .iter()
        .any(|field| document.get(*field).is_some())
    {
        diagnostics.insert("EXTENSION_POLICY_FIELD_FORBIDDEN");
    }
    Ok(())
}

fn require_exact_projection_member(
    document: &Value,
    field: &str,
    expected: bool,
    diagnostic: &'static str,
    diagnostics: &mut BTreeSet<&'static str>,
) {
    if document.get(field).and_then(Value::as_bool) != Some(expected) {
        diagnostics.insert(diagnostic);
    }
}

fn require_exact_projection_members(
    document: &Value,
    expected: &[&str],
    diagnostic: &'static str,
    diagnostics: &mut BTreeSet<&'static str>,
) {
    if document.as_object().is_none_or(|members| {
        members.len() != expected.len()
            || expected.iter().any(|field| !members.contains_key(*field))
    }) {
        diagnostics.insert(diagnostic);
    }
}

fn evaluate_effect_path_fencing(
    document: &Value,
    _fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    require_exact_projection_members(
        document,
        &[
            "disjoint_paths_require_independent_fencing_domains",
            "endpoint_aliases_normalized",
            "fencing_token_binds_domain_incarnation",
            "handover_allows_live_writer_overlap",
            "hot_path_evaluates_proof_graph",
            "overlap_uses_resource_intersection",
            "unfenceable_replacement_requires_isolation",
            "write_requires_current_fencing_term",
        ],
        "EFFECT_OVERLAP_CHECK_REQUIRED",
        diagnostics,
    );
    for (field, expected, diagnostic) in [
        (
            "endpoint_aliases_normalized",
            true,
            "EFFECT_ENDPOINT_ALIAS_NORMALIZATION_REQUIRED",
        ),
        (
            "overlap_uses_resource_intersection",
            true,
            "EFFECT_OVERLAP_CHECK_REQUIRED",
        ),
        (
            "disjoint_paths_require_independent_fencing_domains",
            true,
            "EFFECT_FENCING_DOMAIN_SEPARATION_REQUIRED",
        ),
        (
            "fencing_token_binds_domain_incarnation",
            true,
            "EFFECT_FENCING_DOMAIN_INCARNATION_REQUIRED",
        ),
        (
            "write_requires_current_fencing_term",
            true,
            "EFFECT_WRITE_FENCING_TERM_REQUIRED",
        ),
        (
            "unfenceable_replacement_requires_isolation",
            true,
            "EFFECT_PATH_ISOLATION_REQUIRED",
        ),
        (
            "handover_allows_live_writer_overlap",
            false,
            "EFFECT_HANDOVER_OVERLAP_FORBIDDEN",
        ),
        (
            "hot_path_evaluates_proof_graph",
            false,
            "EFFECT_HOT_PATH_PROOF_GRAPH_FORBIDDEN",
        ),
    ] {
        require_exact_projection_member(document, field, expected, diagnostic, diagnostics);
    }
    Ok(())
}

fn evaluate_security_state(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let expected_realm = fixture
        .pointer("/authenticated_authority_realm")
        .ok_or_else(|| EngineError::corpus("ADR009 fixture is missing authority realm"))?;
    match document.get("authority_realm") {
        Some(actual) if authority_realm_has_required_shape(actual) => {
            if actual != expected_realm {
                diagnostics.insert("AUTHORITY_REALM_MISMATCH");
            }
        }
        Some(_) | None => {
            diagnostics.insert("AUTHORITY_REALM_KEY_REQUIRED");
        }
    }
    if string_at(document, "/profile") != Some(fixture_str(fixture, "/required_profile")?) {
        diagnostics.insert("SECURITY_PROFILE_INVALID");
    }
    let maximum_epoch = fixture_u64(fixture, "/maximum_security_epoch")?;
    let security_epoch_is_valid = document
        .get("security_epoch")
        .and_then(json_safe_u64)
        .is_some_and(|epoch| epoch > 0 && epoch <= maximum_epoch);
    let revocation_epoch_is_valid = document
        .get("revocation_epoch")
        .and_then(json_safe_u64)
        .is_some_and(|epoch| epoch > 0 && epoch <= maximum_epoch);
    if !security_epoch_is_valid {
        diagnostics.insert("SECURITY_EPOCH_INVALID");
    }
    if !revocation_epoch_is_valid {
        diagnostics.insert("REVOCATION_EPOCH_INVALID");
    }
    let principals = document.get("principals").and_then(Value::as_array);
    if !principals.is_some_and(|items| {
        let principal_ids = items
            .iter()
            .filter_map(|principal| string_at(principal, "/principal_id"))
            .collect::<BTreeSet<_>>();
        !items.is_empty()
            && principal_ids.len() == items.len()
            && items.iter().all(|principal| {
                string_at(principal, "/principal_id").is_some_and(|value| !value.is_empty())
                    && string_at(principal, "/role").is_some_and(|value| !value.is_empty())
                    && principal
                        .get("planes")
                        .and_then(Value::as_array)
                        .is_some_and(|planes| {
                            !planes.is_empty()
                                && planes.iter().all(|plane| {
                                    plane.as_str().is_some_and(|value| !value.is_empty())
                                })
                                && planes
                                    .iter()
                                    .filter_map(Value::as_str)
                                    .collect::<BTreeSet<_>>()
                                    .len()
                                    == planes.len()
                        })
            })
    }) {
        diagnostics.insert("PRINCIPAL_MEMBERSHIP_REQUIRED");
    }
    let key_epochs = document.get("key_epochs").and_then(Value::as_array);
    if !key_epochs.is_some_and(|items| {
        let epochs = items
            .iter()
            .filter_map(|key| key.get("epoch").and_then(json_safe_u64))
            .collect::<BTreeSet<_>>();
        let key_ids = items
            .iter()
            .filter_map(|key| string_at(key, "/kid"))
            .collect::<BTreeSet<_>>();
        !items.is_empty()
            && epochs.len() == items.len()
            && key_ids.len() == items.len()
            && items.iter().all(|key| {
                key.get("epoch")
                    .and_then(json_safe_u64)
                    .is_some_and(|epoch| epoch > 0)
                    && string_at(key, "/kid").is_some_and(|kid| !kid.is_empty())
            })
    }) {
        diagnostics.insert("KEY_EPOCH_MEMBERSHIP_REQUIRED");
    }
    let required_algorithm = fixture_str(fixture, "/required_key_algorithm")?;
    if let Some(items) = key_epochs.filter(|items| !items.is_empty()) {
        if !items
            .iter()
            .all(|key| key.get("algorithm").and_then(Value::as_str) == Some(required_algorithm))
        {
            diagnostics.insert("SECURITY_ALGORITHM_NOT_EXACT");
        }
        if !items.iter().all(|key| {
            key.get("kid")
                .and_then(Value::as_str)
                .is_some_and(|kid| is_prefixed_digest(kid, "sha256"))
        }) {
            diagnostics.insert("KEY_ID_NOT_CONTENT_ADDRESSED");
        }
    }
    Ok(())
}

fn evaluate_invalid_security_state(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    evaluate_security_state(document, fixture, diagnostics)?;
    let required_algorithm = fixture_str(fixture, "/required_key_algorithm")?;
    if string_at(document, "/algorithm") != Some(required_algorithm) {
        diagnostics.insert("SECURITY_ALGORITHM_NOT_EXACT");
    }
    if !string_at(document, "/kid").is_some_and(|kid| is_prefixed_digest(kid, "sha256")) {
        diagnostics.insert("KEY_ID_NOT_CONTENT_ADDRESSED");
    }
    Ok(())
}

fn evaluate_action_qos(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    match document.get("authority_realm_key") {
        Some(actual) if authority_realm_key_has_required_shape(actual) => {
            let expected_realm = fixture.pointer("/authenticated_realm_key").ok_or_else(|| {
                EngineError::corpus("ADR010 fixture is missing authenticated realm")
            })?;
            if !realm_and_route_match(
                document,
                expected_realm,
                fixture_str(fixture, "/expected_route")?,
            ) {
                diagnostics.insert("REALM_ROUTE_MISMATCH");
            }
        }
        Some(_) | None => {
            diagnostics.insert("AUTHORITY_REALM_KEY_REQUIRED");
        }
    }
    let maximum_capacity = fixture_u64(fixture, "/maximum_capacity_per_stream")?;
    if !document
        .get("capacity_per_stream")
        .and_then(json_safe_u64)
        .is_some_and(|capacity| capacity > 0 && capacity <= maximum_capacity)
    {
        diagnostics.insert("QOS_CAPACITY_INVALID");
    }
    if string_at(document, "/profile_id") != Some("ncp-action-v1") {
        diagnostics.insert("QOS_PROFILE_ID_REQUIRED");
    }
    if string_at(document, "/plane") != Some("action") {
        diagnostics.insert("QOS_PLANE_REQUIRED");
    }
    if string_at(document, "/route").is_none_or(str::is_empty) {
        diagnostics.insert("QOS_ROUTE_REQUIRED");
    }
    if string_at(document, "/ordering") != Some("strict_stream_sequence") {
        diagnostics.insert("QOS_ORDERING_REQUIRED");
    }
    if string_at(document, "/retention") != Some("until_terminal_disposition_or_expiry") {
        diagnostics.insert("QOS_RETENTION_REQUIRED");
    }
    if string_at(document, "/overload") != Some("reject_new_active_and_emit_disposition") {
        diagnostics.insert("QOS_OVERLOAD_INVALID");
    }
    if document.get("fallback").is_some() {
        diagnostics.insert("QOS_FALLBACK_FORBIDDEN");
    }
    let required_priority = fixture
        .pointer("/required_fail_safe_priority")
        .ok_or_else(|| EngineError::corpus("ADR010 fixture is missing fail-safe priority"))?;
    match document.get("fail_safe_priority") {
        Some(actual @ Value::Array(_)) if actual != required_priority => {
            diagnostics.insert("FAIL_SAFE_PRIORITY_INVALID");
        }
        Some(Value::Array(_)) => {}
        Some(_) | None => {
            diagnostics.insert("QOS_FAIL_SAFE_PRIORITY_REQUIRED");
        }
    }
    Ok(())
}

fn evaluate_gated_intent(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR011 fixture is missing authenticated realm"))?;
    if document.get("authority_realm_key") != Some(expected_realm) {
        diagnostics.insert("AUTHORITY_REALM_MISMATCH");
    }
    if string_at(document, "/audience") != Some(fixture_str(fixture, "/expected_audience")?) {
        diagnostics.insert("INTENT_AUDIENCE_MISMATCH");
    }
    if string_at(document, "/issuer") != Some(fixture_str(fixture, "/expected_issuer")?) {
        diagnostics.insert("INTENT_ISSUER_MISMATCH");
    }
    let evaluation_time = fixture_u64(fixture, "/evaluation_utc_ms")?;
    if document
        .get("expires_at_utc_ms")
        .and_then(json_safe_u64)
        .is_none_or(|expiry| expiry <= evaluation_time)
    {
        diagnostics.insert("INTENT_EXPIRED");
    }
    Ok(())
}

fn evaluate_command_identity(
    document: &Value,
    fixture: &Value,
    diagnostics: &mut BTreeSet<&'static str>,
) -> EngineResult<()> {
    if string_at(document, "/kind") != Some("command_frame") {
        diagnostics.insert("MESSAGE_KIND_MISMATCH");
    }
    let expected_realm = fixture
        .pointer("/authenticated_realm_key")
        .ok_or_else(|| EngineError::corpus("ADR011 fixture is missing authenticated realm"))?;
    if document.get("authority_realm_key") != Some(expected_realm) {
        diagnostics.insert("AUTHORITY_REALM_KEY_REQUIRED");
    }
    if string_at(document, "/identity/principal_id")
        != Some(fixture_str(fixture, "/gated_commander_principal_id")?)
    {
        diagnostics.insert("COMMAND_IDENTITY_LAUNDERING");
    }
    if string_at(document, "/authority/issuer_principal_id")
        != Some(fixture_str(fixture, "/enrolled_body_principal_id")?)
    {
        diagnostics.insert("COMMAND_AUTHORITY_ISSUER_NOT_BODY");
    }
    Ok(())
}

fn fixture_str<'value>(fixture: &'value Value, pointer: &str) -> EngineResult<&'value str> {
    fixture
        .pointer(pointer)
        .and_then(Value::as_str)
        .ok_or_else(|| EngineError::corpus(format!("fixture member {pointer:?} must be a string")))
}

fn fixture_u64(fixture: &Value, pointer: &str) -> EngineResult<u64> {
    fixture
        .pointer(pointer)
        .and_then(json_safe_u64)
        .ok_or_else(|| {
            EngineError::corpus(format!(
                "fixture member {pointer:?} must be an unsigned integer"
            ))
        })
}

fn fixture_bool(fixture: &Value, pointer: &str) -> EngineResult<bool> {
    fixture
        .pointer(pointer)
        .and_then(Value::as_bool)
        .ok_or_else(|| EngineError::corpus(format!("fixture member {pointer:?} must be a Boolean")))
}

fn fixture_string_array<'value>(
    fixture: &'value Value,
    pointer: &str,
) -> EngineResult<BTreeSet<&'value str>> {
    let items = fixture
        .pointer(pointer)
        .and_then(Value::as_array)
        .ok_or_else(|| {
            EngineError::corpus(format!("fixture member {pointer:?} must be an array"))
        })?;
    let mut result = BTreeSet::new();
    for item in items {
        let value = item.as_str().ok_or_else(|| {
            EngineError::corpus(format!("fixture member {pointer:?} contains a non-string"))
        })?;
        if !result.insert(value) {
            return Err(EngineError::corpus(format!(
                "fixture member {pointer:?} contains a duplicate"
            )));
        }
    }
    Ok(result)
}

fn string_at<'value>(value: &'value Value, pointer: &str) -> Option<&'value str> {
    value.pointer(pointer).and_then(Value::as_str)
}

fn json_safe_u64(value: &Value) -> Option<u64> {
    value
        .as_u64()
        .filter(|integer| *integer <= MAXIMUM_JSON_SAFE_INTEGER)
}

fn realm_and_route_match(
    document: &Value,
    expected_realm_key: &Value,
    expected_route: &str,
) -> bool {
    document.get("authority_realm_key") == Some(expected_realm_key)
        && string_at(document, "/route") == Some(expected_route)
}

fn is_prefixed_digest(value: &str, algorithm: &str) -> bool {
    value
        .strip_prefix(algorithm)
        .and_then(|suffix| suffix.strip_prefix(':'))
        .is_some_and(is_raw_digest)
}

fn is_raw_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn typed_digest_matches(value: Option<&Value>, expected_domain: &str) -> bool {
    value.is_some_and(|identity| {
        string_at(identity, "/algorithm") == Some("sha256")
            && string_at(identity, "/domain") == Some(expected_domain)
            && string_at(identity, "/encoding") == Some("lowercase_hex")
            && string_at(identity, "/digest").is_some_and(is_raw_digest)
    })
}

fn authority_realm_has_required_shape(value: &Value) -> bool {
    value.as_object().is_some_and(|realm| {
        string_at(value, "/server_authority_principal").is_some_and(|item| !item.is_empty())
            && string_at(value, "/stable_realm_id").is_some_and(|item| !item.is_empty())
            && realm.len() >= 2
    })
}

fn authority_realm_key_has_required_shape(value: &Value) -> bool {
    string_at(value, "/server_authority_principal_id").is_some_and(|item| !item.is_empty())
        && string_at(value, "/stable_realm_id").is_some_and(|item| !item.is_empty())
}

fn decode_base64url(encoded: &str, maximum_decoded_bytes: usize) -> EngineResult<Vec<u8>> {
    let decoded_length = base64url_decoded_length(encoded)?;
    if decoded_length > maximum_decoded_bytes {
        return Err(EngineError::semantic(
            "base64url decoded length exceeds its pre-allocation bound",
        ));
    }
    let mut output = Vec::with_capacity(decoded_length);
    let mut accumulator = 0_u32;
    let mut bits = 0_u8;
    for byte in encoded.bytes() {
        let value = base64url_digit(byte)
            .ok_or_else(|| EngineError::semantic("invalid base64url alphabet"))?;
        accumulator = (accumulator << 6) | u32::from(value);
        bits += 6;
        while bits >= 8 {
            bits -= 8;
            let shifted = accumulator >> bits;
            let octet = u8::try_from(shifted & 0xff)
                .map_err(|error| EngineError::semantic(format!("base64 byte: {error}")))?;
            output.push(octet);
            accumulator &= (1_u32 << bits) - 1;
        }
    }
    if (bits > 0 && accumulator != 0) || output.len() != decoded_length {
        return Err(EngineError::semantic(
            "non-canonical base64url trailing bits",
        ));
    }
    Ok(output)
}

fn base64url_decoded_length(encoded: &str) -> EngineResult<usize> {
    let remainder = encoded.len() % 4;
    if remainder == 1 {
        return Err(EngineError::semantic("invalid unpadded base64url length"));
    }
    let mut final_digit = 0_u8;
    for byte in encoded.bytes() {
        final_digit = base64url_digit(byte)
            .ok_or_else(|| EngineError::semantic("invalid base64url alphabet"))?;
    }
    if (remainder == 2 && final_digit & 0x0f != 0) || (remainder == 3 && final_digit & 0x03 != 0) {
        return Err(EngineError::semantic(
            "non-canonical base64url trailing bits",
        ));
    }
    let complete = (encoded.len() / 4)
        .checked_mul(3)
        .ok_or_else(|| EngineError::semantic("base64url decoded length overflow"))?;
    complete
        .checked_add(if remainder == 0 { 0 } else { remainder - 1 })
        .ok_or_else(|| EngineError::semantic("base64url decoded length overflow"))
}

fn base64url_digit(byte: u8) -> Option<u8> {
    match byte {
        b'A'..=b'Z' => Some(byte - b'A'),
        b'a'..=b'z' => Some(byte - b'a' + 26),
        b'0'..=b'9' => Some(byte - b'0' + 52),
        b'-' => Some(62),
        b'_' => Some(63),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::{decode_base64url, evaluate};

    #[test]
    fn decode_base64url_should_require_unpadded_canonical_encoding() {
        assert_eq!(decode_base64url("e30", 2).ok(), Some(b"{}".to_vec()));
        assert!(decode_base64url("e30", 1).is_err());
        assert!(decode_base64url("e31", 2).is_err());
        assert!(decode_base64url("e30=", 2).is_err());
    }

    #[test]
    fn evaluate_should_reject_unknown_profile() {
        let result = evaluate("UNKNOWN", &json!({}), &json!({}));
        assert!(result.is_err());
    }

    #[test]
    fn evaluate_should_detect_pending_allocation_guard_removal() {
        let fixture = json!({
            "expected_state": "PENDING_INTENT_ONLY",
            "output_allocation_permitted": false
        });
        let hostile = json!({
            "state": "PENDING_INTENT_ONLY",
            "allocates_output_slot": true
        });
        let evaluation = evaluate(super::PENDING_RESERVATION, &hostile, &fixture);
        assert!(evaluation.is_ok());
        let diagnostics = evaluation.ok().map(|value| value.diagnostics);
        assert_eq!(
            diagnostics,
            Some(vec!["PENDING_STATE_ALLOCATES_OUTPUT".to_owned()])
        );
    }

    #[test]
    fn contract_identity_should_allow_an_advisory_compact_hash() {
        let stable_core_digest =
            "sha256:1111111111111111111111111111111111111111111111111111111111111111";
        let realm = json!({
            "server_authority_principal_id": "ncp-authority-a",
            "stable_realm_id": "realm-a"
        });
        let fixture = json!({
            "authenticated_realm_key": realm,
            "digest_algorithm": "sha256",
            "expected_stable_core_digest": stable_core_digest
        });
        let document = json!({
            "authority_realm_key": realm,
            "wire_version": "1.0",
            "stable_core_digest": stable_core_digest,
            "contract_hash": "163acc57d8a62b66"
        });
        let evaluation = evaluate(super::CONTRACT_IDENTITY, &document, &fixture);
        assert!(evaluation.is_ok());
        let evaluation = evaluation.ok();
        assert!(evaluation
            .as_ref()
            .is_some_and(|value| value.diagnostics.is_empty()));
        assert!(evaluation
            .is_some_and(|value| value.profile_result
                == crate::model::ProfileResult::MatchNonAuthorizingExcerpt));
    }
}
