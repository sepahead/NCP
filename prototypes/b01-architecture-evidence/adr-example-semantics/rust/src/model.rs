use std::collections::BTreeSet;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::error::{EngineError, EngineResult};
use crate::strict_json::JsonLimits;

pub(crate) const CORPUS_SCHEMA: &str = "ncp.b01-adr-example-semantics-corpus.v1";
pub(crate) const RESULT_SCHEMA: &str = "ncp.b01-adr-example-semantics-result.v1";
pub(crate) const MAXIMUM_PATCH_PATH_UTF8_BYTES: usize = 512;
const MAXIMUM_MUTATION_PURPOSE_UTF8_BYTES: usize = 512;
const EXPECTED_MUTATION_COUNT: usize = 132;
const DIAGNOSTIC_REGISTRY: &[&str] = &[
    "ALGORITHM_LABEL_FORBIDDEN",
    "ALGORITHM_LABEL_REQUIRED",
    "ASSESSMENT_MAGNITUDE_REQUIRED",
    "AUTHORITY_REALM_KEY_MISMATCH",
    "AUTHORITY_REALM_KEY_MISSING",
    "AUTHORITY_REALM_KEY_REQUIRED",
    "AUTHORITY_REALM_MISMATCH",
    "COMMANDER_PRINCIPAL_MISMATCH",
    "COMMAND_AUTHORITY_ISSUER_NOT_BODY",
    "COMMAND_IDENTITY_LAUNDERING",
    "COMPACT_HASH_NOT_COMPATIBILITY_IDENTITY",
    "DIGEST_ENCODING_INVALID",
    "DISPOSITION_QUERY_COORDINATE_INVALID",
    "DISPOSITION_RESULT_BRANCHES_INVALID",
    "DISPOSITION_RESULT_PROJECTION_INVALID",
    "DISPOSITION_RETAINED_CHAIN_REQUIRED",
    "DISPOSITION_RETIRED_EFFECT_FORBIDDEN",
    "DISPOSITION_STATE_UNKNOWN",
    "DISPOSITION_TERMINALITY_INVALID",
    "EFFECT_ENDPOINT_ALIAS_NORMALIZATION_REQUIRED",
    "EFFECT_FENCING_DOMAIN_INCARNATION_REQUIRED",
    "EFFECT_FENCING_DOMAIN_SEPARATION_REQUIRED",
    "EFFECT_HANDOVER_OVERLAP_FORBIDDEN",
    "EFFECT_HOT_PATH_PROOF_GRAPH_FORBIDDEN",
    "EFFECT_OVERLAP_CHECK_REQUIRED",
    "EFFECT_PATH_ISOLATION_REQUIRED",
    "EFFECT_WRITE_FENCING_TERM_REQUIRED",
    "ESTOP_RESERVATION_CURRENTNESS_RECHECK_REQUIRED",
    "EXTENSION_ACTIVATION_PROFILE_BINDING_REQUIRED",
    "EXTENSION_ACTIVATION_TIME_BINDING_REQUIRED",
    "EXTENSION_CALLBACK_BOUNDARY_STATE_REQUIRED",
    "EXTENSION_CALLBACK_RESOURCE_LIFETIME_INVALID",
    "EXTENSION_COMPLETE_HASH_RULE_INVALID",
    "EXTENSION_CONFLICT_OVERWRITE_FORBIDDEN",
    "EXTENSION_CURRENTNESS_CUT_ORDER_INVALID",
    "EXTENSION_DUPLICATE_COPY_FORBIDDEN",
    "EXTENSION_FIRST_INDEX_RULE_INVALID",
    "EXTENSION_HEADER_ADMISSION_INVALID",
    "EXTENSION_ID_MISMATCH",
    "EXTENSION_OUTER_ENCODING_INVALID",
    "EXTENSION_PACKAGE_FRAME_NESTING_FORBIDDEN",
    "EXTENSION_POLICY_FIELD_FORBIDDEN",
    "EXTENSION_PRE_CALLBACK_CURRENTNESS_RECHECK_REQUIRED",
    "EXTENSION_PRE_SCHEMA_CURRENTNESS_RECHECK_REQUIRED",
    "EXTENSION_PRODUCER_ROLE_INVALID",
    "EXTENSION_RECEIVER_ACTIVATION_INCARNATION_REQUIRED",
    "EXTENSION_RECEIVER_ROLE_INVALID",
    "EXTENSION_RESERVATION_ORDER_INVALID",
    "EXTENSION_RETIRED_RESULT_DISCLOSURE_FORBIDDEN",
    "EXTENSION_SCHEMA_RESERVATION_REQUIRED",
    "EXTENSION_SCHEMA_VERSION_MISMATCH",
    "EXTENSION_STABLE_SLOT_INVALID",
    "EXTENSION_TERMINAL_LOOKUP_ORDER_INVALID",
    "EXTENSION_TERMINAL_TOMBSTONE_REQUIRED",
    "FAIL_SAFE_EARLY_EFFECT_MODE_INVALID",
    "FAIL_SAFE_EFFECT_BOUNDARY_RECHECK_REQUIRED",
    "FAIL_SAFE_PRIORITY_INVALID",
    "HOLD_ADMISSION_ORDER_INVALID",
    "INTENT_AUDIENCE_MISMATCH",
    "INTENT_EXPIRED",
    "INTENT_ISSUER_MISMATCH",
    "KEY_EPOCH_MEMBERSHIP_REQUIRED",
    "KEY_ID_NOT_CONTENT_ADDRESSED",
    "LEASE_ISSUER_NOT_BODY",
    "LEASE_NOT_CURRENT",
    "MESSAGE_KIND_MISMATCH",
    "NCP_VERSION_MISMATCH",
    "OUTPUT_ALLOCATION_FLAG_INVALID",
    "PENDING_STATE_ALLOCATES_OUTPUT",
    "PENDING_STATE_INVALID",
    "PLANT_CONTAINS_SIMULATION_ONLY_MEMBER",
    "PLANT_PROFILE_MISSING",
    "PLANT_SECURITY_CONTEXT_MISSING",
    "POST_EFFECT_ADMISSION_MODE_INVALID",
    "PRINCIPAL_MEMBERSHIP_REQUIRED",
    "PROTECTED_HEADER_AUDIENCE_MISMATCH",
    "PROTECTED_HEADER_NOT_JSON",
    "PUBLISHER_PRINCIPAL_MISMATCH",
    "QOS_CAPACITY_INVALID",
    "QOS_FAIL_SAFE_PRIORITY_REQUIRED",
    "QOS_FALLBACK_FORBIDDEN",
    "QOS_ORDERING_REQUIRED",
    "QOS_OVERLOAD_INVALID",
    "QOS_PLANE_REQUIRED",
    "QOS_PROFILE_ID_REQUIRED",
    "QOS_RETENTION_REQUIRED",
    "QOS_ROUTE_REQUIRED",
    "REALM_REQUIRED",
    "REALM_ROUTE_MISMATCH",
    "REJECTED_CANDIDATE_LOCAL_HOLD_FORBIDDEN",
    "REMOTE_JKU_FORBIDDEN",
    "REVOCATION_EPOCH_INVALID",
    "SECURITY_ALGORITHM_NOT_EXACT",
    "SECURITY_EPOCH_INVALID",
    "SECURITY_PROFILE_INVALID",
    "SESSION_KIND_MISMATCH",
    "SIGNATURE_LENGTH_INVALID",
    "SIGNATURE_NOT_VALID",
    "STABLE_CORE_DIGEST_INVALID",
    "STABLE_CORE_DIGEST_MISMATCH",
    "STABLE_CORE_DIGEST_MISSING_OR_NULL",
    "STREAM_DECLARATION_NOT_LIVE",
    "STREAM_EPOCH_ALREADY_LIVE",
    "STREAM_EPOCH_REQUIRED",
    "STREAM_SEQUENCE_START_INVALID",
    "UNPROTECTED_HEADER_FORBIDDEN",
    "WIRE_VERSION_MISMATCH",
];

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Corpus {
    pub(crate) schema: String,
    pub(crate) schema_version: u64,
    pub(crate) task: String,
    pub(crate) candidate: String,
    pub(crate) wire_version: String,
    pub(crate) decision_set_binding: DecisionSetBinding,
    pub(crate) source_binding: SourceBinding,
    pub(crate) limits: Limits,
    pub(crate) closed_values: ClosedValues,
    pub(crate) diagnostic_registry: Vec<String>,
    pub(crate) claim_boundary: ClaimBoundary,
    pub(crate) cases: Vec<Case>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct DecisionSetBinding {
    pub(crate) schema: String,
    pub(crate) registry_path: String,
    pub(crate) digest_algorithm: String,
    pub(crate) domain_hex: String,
    pub(crate) projection_encoding: String,
    pub(crate) projection_members: Vec<String>,
    pub(crate) decision_members: Vec<String>,
    pub(crate) projection_byte_length: usize,
    pub(crate) projection_sha256: String,
    pub(crate) sha256: String,
    pub(crate) semantic_closure: Value,
    pub(crate) effect: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct SourceBinding {
    fence_language: String,
    fence_capture: String,
    path_root: String,
    sha256_encoding: String,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(crate) struct Limits {
    pub(crate) maximum_corpus_bytes: usize,
    pub(crate) maximum_aggregate_adr_bytes: usize,
    pub(crate) maximum_adr_bytes: usize,
    pub(crate) maximum_json_fence_bytes: usize,
    pub(crate) maximum_fixture_bytes: usize,
    pub(crate) maximum_json_depth: usize,
    pub(crate) maximum_json_nodes: usize,
    pub(crate) maximum_object_members: usize,
    pub(crate) maximum_array_items: usize,
    pub(crate) maximum_key_utf8_bytes: usize,
    pub(crate) maximum_string_utf8_bytes: usize,
    pub(crate) maximum_total_string_utf8_bytes: usize,
    pub(crate) maximum_integer_characters: usize,
    pub(crate) allow_floats: bool,
    pub(crate) expected_case_count: usize,
    pub(crate) expected_mutation_count: usize,
    pub(crate) minimum_mutations_per_case: usize,
    pub(crate) maximum_mutations_per_case: usize,
    pub(crate) maximum_engine_output_bytes: usize,
    pub(crate) engine_timeout_seconds: u64,
}

impl Limits {
    pub(crate) fn json(self, maximum_input_bytes: usize) -> JsonLimits {
        JsonLimits {
            maximum_input_bytes,
            maximum_json_depth: self.maximum_json_depth,
            maximum_json_nodes: self.maximum_json_nodes,
            maximum_object_members: self.maximum_object_members,
            maximum_array_items: self.maximum_array_items,
            maximum_key_utf8_bytes: self.maximum_key_utf8_bytes,
            maximum_string_utf8_bytes: self.maximum_string_utf8_bytes,
            maximum_total_string_utf8_bytes: self.maximum_total_string_utf8_bytes,
            maximum_integer_characters: self.maximum_integer_characters,
            allow_floats: self.allow_floats,
        }
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ClosedValues {
    scope: Vec<Scope>,
    polarity: Vec<Polarity>,
    profile_result: Vec<ProfileResult>,
    production_admission: Vec<ProductionAdmission>,
    patch_target: Vec<PatchTarget>,
    patch_operation: Vec<PatchOperation>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ClaimBoundary {
    adrs_accepted: bool,
    normative_contract_changed: bool,
    production_admission_implemented: bool,
    interoperability_established: bool,
    independent_evidence_satisfied: bool,
    external_gate_satisfied: bool,
    release_authorized: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Case {
    pub(crate) id: String,
    pub(crate) source: Source,
    pub(crate) scope: Scope,
    pub(crate) profile: String,
    pub(crate) polarity: Polarity,
    pub(crate) expected_profile_result: ProfileResult,
    pub(crate) production_admission: ProductionAdmission,
    pub(crate) bounded_fixture: Value,
    pub(crate) expected_diagnostics: Vec<String>,
    pub(crate) payload_interpreted: bool,
    pub(crate) mutations: Vec<Mutation>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Source {
    pub(crate) adr: String,
    pub(crate) json_fence_ordinal: usize,
    pub(crate) fence_byte_length: usize,
    pub(crate) fence_sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Mutation {
    pub(crate) id: String,
    purpose: String,
    pub(crate) patch: Patch,
    pub(crate) expected_profile_result: ProfileResult,
    pub(crate) production_admission: ProductionAdmission,
    pub(crate) expected_diagnostics: Vec<String>,
    pub(crate) payload_interpreted: bool,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Patch {
    pub(crate) target: PatchTarget,
    pub(crate) op: PatchOperation,
    pub(crate) path: String,
    pub(crate) value: Option<Value>,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum Scope {
    AuthenticatedWireObject,
    DecodedHeaderFragment,
    NonNcpIntentCorrelationFragment,
    NonWireInternalState,
    ProposedExtensionEnvelope,
    ProposedSemanticProjection,
    ProposedWireFragment,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum Polarity {
    Negative,
    Positive,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum ProfileResult {
    MatchNonAuthorizingExcerpt,
    MatchNonWireExcerpt,
    Reject,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum ProductionAdmission {
    NotApplicable,
    NotEvaluated,
    Reject,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum PatchTarget {
    BoundedFixture,
    Document,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, Ord, PartialEq, PartialOrd)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub(crate) enum PatchOperation {
    Add,
    Remove,
    Replace,
}

impl Corpus {
    pub(crate) fn validate(&self, corpus_bytes: usize) -> EngineResult<()> {
        if self.schema != CORPUS_SCHEMA
            || self.schema_version != 1
            || self.task != "B01"
            || self.candidate != "1.0.0-rc.1"
            || self.wire_version != "1.0"
        {
            return Err(EngineError::corpus(
                "corpus identity fields do not match v1",
            ));
        }
        if corpus_bytes > self.limits.maximum_corpus_bytes {
            return Err(EngineError::corpus(
                "corpus exceeds its declared byte limit",
            ));
        }
        self.validate_source_binding()?;
        self.validate_decision_set_binding()?;
        self.validate_limits()?;
        self.validate_closed_values()?;
        self.validate_claim_boundary()?;
        ensure_unique_nonempty("diagnostic registry", &self.diagnostic_registry)?;
        if !self
            .diagnostic_registry
            .iter()
            .map(String::as_str)
            .eq(DIAGNOSTIC_REGISTRY.iter().copied())
        {
            return Err(EngineError::corpus(
                "diagnostic registry differs from the closed engine vocabulary",
            ));
        }
        if self.cases.len() != self.limits.expected_case_count {
            return Err(EngineError::corpus(format!(
                "case count is {}; expected {}",
                self.cases.len(),
                self.limits.expected_case_count
            )));
        }

        let registry = self
            .diagnostic_registry
            .iter()
            .map(String::as_str)
            .collect::<BTreeSet<_>>();
        let mut case_ids = BTreeSet::new();
        let mut mutation_ids = BTreeSet::new();
        let mut used_diagnostics = BTreeSet::new();
        let mut fence_bindings = BTreeSet::new();
        let mut previous_coordinate: Option<(&str, usize)> = None;
        for case in &self.cases {
            validate_identifier("case", &case.id)?;
            if !case_ids.insert(case.id.as_str()) {
                return Err(EngineError::corpus(format!(
                    "duplicate case id {:?}",
                    case.id
                )));
            }
            if case.source.json_fence_ordinal == 0 {
                return Err(EngineError::corpus(format!(
                    "case {:?} has zero fence ordinal",
                    case.id
                )));
            }
            if !fence_bindings.insert((case.source.adr.as_str(), case.source.json_fence_ordinal)) {
                return Err(EngineError::corpus(format!(
                    "duplicate source fence binding for case {:?}",
                    case.id
                )));
            }
            if previous_coordinate.is_some_and(|coordinate| {
                coordinate >= (case.source.adr.as_str(), case.source.json_fence_ordinal)
            }) {
                return Err(EngineError::corpus(
                    "case source coordinates are not in strict deterministic order",
                ));
            }
            previous_coordinate = Some((case.source.adr.as_str(), case.source.json_fence_ordinal));
            validate_case_identity(case)?;
            if case.polarity == Polarity::Positive && !case.payload_interpreted {
                return Err(EngineError::corpus(format!(
                    "positive case {:?} does not interpret its bounded payload",
                    case.id
                )));
            }
            let case_namespace = case
                .id
                .split_once('.')
                .map(|(prefix, _)| prefix)
                .ok_or_else(|| {
                    EngineError::corpus(format!("case {:?} has no ADR namespace", case.id))
                })?;
            validate_sha256("fence", &case.source.fence_sha256)?;
            if case.source.adr.is_empty() {
                return Err(EngineError::corpus(format!(
                    "case {:?} has an empty source identity",
                    case.id
                )));
            }
            validate_expected_diagnostics(&case.id, &case.expected_diagnostics, &registry)?;
            used_diagnostics.extend(case.expected_diagnostics.iter().map(String::as_str));
            validate_expected_observation(
                &case.id,
                case.expected_profile_result,
                case.production_admission,
                &case.expected_diagnostics,
            )?;
            match (case.polarity, case.expected_profile_result) {
                (Polarity::Positive, ProfileResult::Reject)
                | (Polarity::Negative, ProfileResult::MatchNonAuthorizingExcerpt)
                | (Polarity::Negative, ProfileResult::MatchNonWireExcerpt) => {
                    return Err(EngineError::corpus(format!(
                        "case {:?} polarity and expected result conflict",
                        case.id
                    )));
                }
                (Polarity::Positive, _) | (Polarity::Negative, ProfileResult::Reject) => {}
            }
            if (case.scope == Scope::NonWireInternalState)
                != (case.expected_profile_result == ProfileResult::MatchNonWireExcerpt)
            {
                return Err(EngineError::corpus(format!(
                    "case {:?} non-wire scope and match result conflict",
                    case.id
                )));
            }
            if case.mutations.len() < self.limits.minimum_mutations_per_case
                || case.mutations.len() > self.limits.maximum_mutations_per_case
            {
                return Err(EngineError::corpus(format!(
                    "case {:?} mutation count is outside declared bounds",
                    case.id
                )));
            }
            for mutation in &case.mutations {
                validate_identifier("mutation", &mutation.id)?;
                if mutation
                    .id
                    .strip_prefix(case_namespace)
                    .and_then(|suffix| suffix.strip_prefix('.'))
                    .is_none()
                {
                    return Err(EngineError::corpus(format!(
                        "mutation {:?} is not namespaced to case {:?}",
                        mutation.id, case.id
                    )));
                }
                if mutation.purpose.trim().is_empty()
                    || mutation.purpose.len() > MAXIMUM_MUTATION_PURPOSE_UTF8_BYTES
                {
                    return Err(EngineError::corpus(format!(
                        "mutation {:?} has an invalid purpose",
                        mutation.id
                    )));
                }
                validate_patch_path(&mutation.patch.path)?;
                if !mutation_ids.insert(mutation.id.as_str()) {
                    return Err(EngineError::corpus(format!(
                        "duplicate mutation id {:?}",
                        mutation.id
                    )));
                }
                match (mutation.patch.op, mutation.patch.value.is_some()) {
                    (PatchOperation::Remove, false)
                    | (PatchOperation::Add | PatchOperation::Replace, true) => {}
                    _ => {
                        return Err(EngineError::corpus(format!(
                            "mutation {:?} has an invalid op/value combination",
                            mutation.id
                        )));
                    }
                }
                validate_expected_diagnostics(
                    &mutation.id,
                    &mutation.expected_diagnostics,
                    &registry,
                )?;
                used_diagnostics.extend(mutation.expected_diagnostics.iter().map(String::as_str));
                if mutation.expected_profile_result != ProfileResult::Reject {
                    return Err(EngineError::corpus(format!(
                        "mutation {:?} is not an expected fail-closed contrast",
                        mutation.id
                    )));
                }
                validate_expected_observation(
                    &mutation.id,
                    mutation.expected_profile_result,
                    mutation.production_admission,
                    &mutation.expected_diagnostics,
                )?;
                if !mutation_changes_expected_observation(case, mutation) {
                    return Err(EngineError::corpus(format!(
                        "mutation {:?} is not observable against its base case",
                        mutation.id
                    )));
                }
            }
        }
        if mutation_ids.len() != self.limits.expected_mutation_count {
            return Err(EngineError::corpus(format!(
                "mutation count is {}; expected {}",
                mutation_ids.len(),
                self.limits.expected_mutation_count
            )));
        }
        validate_global_registry_coverage(&case_ids, &mutation_ids, &used_diagnostics, &registry)?;
        Ok(())
    }

    fn validate_source_binding(&self) -> EngineResult<()> {
        if self.source_binding.fence_language != "json"
            || self.source_binding.fence_capture
                != "content_between_top_level_exact_json_fence_lines_excluding_one_terminal_line_ending"
            || self.source_binding.path_root != "repository"
            || self.source_binding.sha256_encoding != "lowercase_hex"
        {
            return Err(EngineError::corpus(
                "source binding is not the closed v1 binding",
            ));
        }
        Ok(())
    }

    fn validate_decision_set_binding(&self) -> EngineResult<()> {
        let binding = &self.decision_set_binding;
        let expected_projection_members = [
            "schema",
            "candidate",
            "wire_version",
            "review_policy",
            "semantic_closure",
            "decisions",
        ];
        let expected_decision_members = [
            "id",
            "title",
            "path",
            "module_paths",
            "content_sha256",
            "bytes",
            "source_set",
            "required_reviews",
            "defect_ids",
        ];
        if binding.schema != "ncp.b01-decision-set.v1"
            || binding.registry_path != "docs/adr/decision-registry.proposed.v1.json"
            || binding.digest_algorithm != "sha256(domain || u64be(projection_bytes) || projection)"
            || binding.domain_hex != "6e63702e6230312d6465636973696f6e2d7365742e763100"
            || binding.projection_encoding != "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE"
            || binding.projection_members != expected_projection_members.map(str::to_owned).to_vec()
            || binding.decision_members != expected_decision_members.map(str::to_owned).to_vec()
            || binding.projection_byte_length == 0
            || binding.projection_byte_length > 262_144
            || !valid_semantic_closure_binding(&binding.semantic_closure)
            || binding.effect != "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY"
        {
            return Err(EngineError::corpus(
                "decision-set binding is missing or differs from the closed v1 recipe",
            ));
        }
        validate_sha256("decision projection", &binding.projection_sha256)?;
        validate_sha256("decision set", &binding.sha256)
    }

    fn validate_limits(&self) -> EngineResult<()> {
        let limits = self.limits;
        let expected = Limits {
            maximum_corpus_bytes: 262_144,
            maximum_aggregate_adr_bytes: 2_097_152,
            maximum_adr_bytes: 262_144,
            maximum_json_fence_bytes: 131_072,
            maximum_fixture_bytes: 16_384,
            maximum_json_depth: 32,
            maximum_json_nodes: 100_000,
            maximum_object_members: 4_096,
            maximum_array_items: 4_096,
            maximum_key_utf8_bytes: 128,
            maximum_string_utf8_bytes: 65_536,
            maximum_total_string_utf8_bytes: 131_072,
            maximum_integer_characters: 32,
            allow_floats: false,
            expected_case_count: 25,
            expected_mutation_count: EXPECTED_MUTATION_COUNT,
            minimum_mutations_per_case: 2,
            maximum_mutations_per_case: 24,
            maximum_engine_output_bytes: 262_144,
            engine_timeout_seconds: 120,
        };
        if limits != expected {
            return Err(EngineError::corpus(
                "declared limits differ from the closed v1 limits",
            ));
        }
        Ok(())
    }

    fn validate_closed_values(&self) -> EngineResult<()> {
        expect_exact_set(
            "scope",
            &self.closed_values.scope,
            &[
                Scope::AuthenticatedWireObject,
                Scope::DecodedHeaderFragment,
                Scope::NonNcpIntentCorrelationFragment,
                Scope::NonWireInternalState,
                Scope::ProposedExtensionEnvelope,
                Scope::ProposedSemanticProjection,
                Scope::ProposedWireFragment,
            ],
        )?;
        expect_exact_set(
            "polarity",
            &self.closed_values.polarity,
            &[Polarity::Negative, Polarity::Positive],
        )?;
        expect_exact_set(
            "profile_result",
            &self.closed_values.profile_result,
            &[
                ProfileResult::MatchNonAuthorizingExcerpt,
                ProfileResult::MatchNonWireExcerpt,
                ProfileResult::Reject,
            ],
        )?;
        expect_exact_set(
            "production_admission",
            &self.closed_values.production_admission,
            &[
                ProductionAdmission::NotApplicable,
                ProductionAdmission::NotEvaluated,
                ProductionAdmission::Reject,
            ],
        )?;
        expect_exact_set(
            "patch_target",
            &self.closed_values.patch_target,
            &[PatchTarget::BoundedFixture, PatchTarget::Document],
        )?;
        expect_exact_set(
            "patch_operation",
            &self.closed_values.patch_operation,
            &[
                PatchOperation::Add,
                PatchOperation::Remove,
                PatchOperation::Replace,
            ],
        )
    }

    fn validate_claim_boundary(&self) -> EngineResult<()> {
        let boundary = &self.claim_boundary;
        if boundary.adrs_accepted
            || boundary.normative_contract_changed
            || boundary.production_admission_implemented
            || boundary.interoperability_established
            || boundary.independent_evidence_satisfied
            || boundary.external_gate_satisfied
            || boundary.release_authorized
        {
            return Err(EngineError::corpus(
                "claim boundary must keep every authority and release claim false",
            ));
        }
        Ok(())
    }
}

fn validate_global_registry_coverage(
    case_ids: &BTreeSet<&str>,
    mutation_ids: &BTreeSet<&str>,
    used_diagnostics: &BTreeSet<&str>,
    registry: &BTreeSet<&str>,
) -> EngineResult<()> {
    if !case_ids.is_disjoint(mutation_ids) {
        return Err(EngineError::corpus(
            "case and mutation identifiers must be globally unique",
        ));
    }
    if used_diagnostics != registry {
        return Err(EngineError::corpus(
            "diagnostic registry must exactly cover the v1 corpus expectations",
        ));
    }
    Ok(())
}

fn valid_semantic_closure_binding(value: &Value) -> bool {
    let Some(closure) = value.as_object() else {
        return false;
    };
    if closure.len() != 2 {
        return false;
    }
    [
        (
            "source",
            "docs/adr/decision-closure.source.v1.json",
            262_144_u64,
        ),
        (
            "json_schema",
            "docs/adr/decision-closure.source.schema.v1.json",
            262_144_u64,
        ),
    ]
    .into_iter()
    .all(|(member, expected_path, maximum_bytes)| {
        let Some(identity) = closure.get(member).and_then(Value::as_object) else {
            return false;
        };
        identity.len() == 3
            && identity.get("path").and_then(Value::as_str) == Some(expected_path)
            && identity
                .get("bytes")
                .and_then(Value::as_u64)
                .is_some_and(|bytes| (1..=maximum_bytes).contains(&bytes))
            && identity
                .get("sha256")
                .and_then(Value::as_str)
                .is_some_and(valid_sha256)
    })
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

pub(crate) fn validate_patch_path(path: &str) -> EngineResult<()> {
    if path.is_empty() || path.len() > MAXIMUM_PATCH_PATH_UTF8_BYTES || !path.starts_with('/') {
        return Err(EngineError::corpus(
            "patch path is not a bounded non-root JSON Pointer",
        ));
    }
    let mut bytes = path.bytes();
    while let Some(byte) = bytes.next() {
        if byte == b'~' && !bytes.next().is_some_and(|escape| b"01".contains(&escape)) {
            return Err(EngineError::corpus(
                "patch path contains an invalid JSON Pointer escape",
            ));
        }
    }
    Ok(())
}

fn mutation_changes_expected_observation(case: &Case, mutation: &Mutation) -> bool {
    mutation.expected_profile_result != case.expected_profile_result
        || mutation.production_admission != case.production_admission
        || mutation.expected_diagnostics != case.expected_diagnostics
        || mutation.payload_interpreted != case.payload_interpreted
}

fn validate_expected_observation(
    owner: &str,
    result: ProfileResult,
    production: ProductionAdmission,
    diagnostics: &[String],
) -> EngineResult<()> {
    if (result == ProfileResult::Reject) == diagnostics.is_empty() {
        return Err(EngineError::corpus(format!(
            "{owner:?} result and diagnostics conflict"
        )));
    }
    if result == ProfileResult::Reject && production == ProductionAdmission::NotEvaluated {
        return Err(EngineError::corpus(format!(
            "{owner:?} marks a rejected profile as NOT_EVALUATED"
        )));
    }
    Ok(())
}

pub(crate) fn validate_bounded_fixture(profile: &str, fixture: &Value) -> EngineResult<()> {
    let fixture = fixture
        .as_object()
        .ok_or_else(|| EngineError::corpus(format!("fixture for {profile:?} must be an object")))?;
    match profile {
        "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "digest_algorithm",
                    "expected_commander_principal_id",
                    "expected_ncp_version",
                    "expected_session_kind",
                ],
                profile,
            )?;
            require_fixture_literal_string(fixture, "digest_algorithm", "sha256", profile)?;
            require_fixture_literal_string(fixture, "expected_ncp_version", "1.0", profile)?;
            require_fixture_literal_string(
                fixture,
                "expected_session_kind",
                "open_plant_session",
                profile,
            )?;
            require_fixture_string(fixture, "expected_commander_principal_id", profile)
        }
        "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "digest_algorithm",
                    "expected_stable_core_digest",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_literal_string(fixture, "digest_algorithm", "sha256", profile)?;
            require_fixture_prefixed_sha256(fixture, "expected_stable_core_digest", profile)
        }
        "ADR003_FLATTENED_FORWARDING_WRAPPER_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "expected_signature_bytes",
                    "required_algorithm",
                    "signature_verifies",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_literal_string(fixture, "required_algorithm", "Ed25519", profile)?;
            require_fixture_positive_safe_integer(fixture, "expected_signature_bytes", profile)?;
            require_fixture_literal_bool(fixture, "signature_verifies", false, profile)
        }
        "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "expected_audience",
                    "expected_route",
                    "required_algorithm",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_literal_string(fixture, "required_algorithm", "Ed25519", profile)?;
            require_fixture_string(fixture, "expected_audience", profile)?;
            require_fixture_string(fixture, "expected_route", profile)
        }
        "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1" => {
            expect_fixture_keys(
                fixture,
                &["expected_state", "output_allocation_permitted"],
                profile,
            )?;
            require_fixture_literal_string(
                fixture,
                "expected_state",
                "PENDING_INTENT_ONLY",
                profile,
            )?;
            require_fixture_literal_bool(fixture, "output_allocation_permitted", false, profile)
        }
        "ADR005_DECLARE_STREAM_EXCERPT_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_publisher_principal_id",
                    "authenticated_realm_key",
                    "expected_route",
                    "live_declaration_epoch_ids",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_string(fixture, "authenticated_publisher_principal_id", profile)?;
            require_fixture_string(fixture, "expected_route", profile)?;
            require_fixture_string_array(fixture, "live_declaration_epoch_ids", profile)
        }
        "ADR005_UNDECLARED_FRAME_V1" => {
            expect_fixture_keys(
                fixture,
                &["authenticated_realm_key", "live_declaration_epoch_ids"],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_string_array(fixture, "live_declaration_epoch_ids", profile)
        }
        "ADR006_BODY_LEASE_EXCERPT_V1" | "ADR006_STALE_SELF_ISSUED_LEASE_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "current_lease",
                    "enrolled_body_principal_id",
                    "evaluation_utc_ms",
                ],
                profile,
            )?;
            require_fixture_string(fixture, "enrolled_body_principal_id", profile)?;
            require_fixture_positive_safe_integer(fixture, "evaluation_utc_ms", profile)?;
            let lease = fixture
                .get("current_lease")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    EngineError::corpus(format!(
                        "{profile:?} fixture current_lease must be an object"
                    ))
                })?;
            let lease_label = format!("{profile}.current_lease");
            expect_fixture_keys(
                lease,
                &[
                    "holder_entity_id",
                    "holder_principal_id",
                    "lease_id",
                    "session_generation",
                    "term",
                ],
                &lease_label,
            )?;
            for key in [
                "holder_entity_id",
                "holder_principal_id",
                "lease_id",
                "session_generation",
            ] {
                require_fixture_string(lease, key, profile)?;
            }
            require_fixture_positive_safe_integer(lease, "term", profile)
        }
        "ADR007_DISPOSITION_QUERY_PROJECTION_V1" | "ADR008_RAW_CHUNK_PROJECTION_V1" => {
            expect_fixture_keys(fixture, &[], profile)
        }
        "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1" | "ADR007_INVALID_DISPOSITION_V1" => {
            expect_fixture_keys(fixture, &["nonterminal_states", "terminal_states"], profile)?;
            require_fixture_string_array(fixture, "nonterminal_states", profile)?;
            require_fixture_string_array(fixture, "terminal_states", profile)
        }
        "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "expected_route",
                    "extension_assessor_principal_id",
                    "extension_receiver_principal_id",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_string(fixture, "expected_route", profile)?;
            require_fixture_string(fixture, "extension_assessor_principal_id", profile)?;
            require_fixture_string(fixture, "extension_receiver_principal_id", profile)
        }
        "ADR008_GALADRIEL_POLICY_INJECTION_V1" => {
            expect_fixture_keys(
                fixture,
                &["authenticated_realm_key", "extension_assessor_principal_id"],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_string(fixture, "extension_assessor_principal_id", profile)
        }
        "ADR009_SECURITY_STATE_PROJECTION_V1" | "ADR009_INVALID_SECURITY_STATE_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_authority_realm",
                    "maximum_security_epoch",
                    "required_key_algorithm",
                    "required_profile",
                ],
                profile,
            )?;
            let realm = fixture
                .get("authenticated_authority_realm")
                .and_then(Value::as_object)
                .ok_or_else(|| {
                    EngineError::corpus(format!(
                        "{profile:?} fixture authenticated_authority_realm must be an object"
                    ))
                })?;
            expect_fixture_keys(
                realm,
                &["server_authority_principal", "stable_realm_id"],
                &format!("{profile}.authenticated_authority_realm"),
            )?;
            require_fixture_string(realm, "server_authority_principal", profile)?;
            require_fixture_string(realm, "stable_realm_id", profile)?;
            require_fixture_positive_safe_integer(fixture, "maximum_security_epoch", profile)?;
            require_fixture_literal_string(fixture, "required_key_algorithm", "Ed25519", profile)?;
            require_fixture_literal_string(
                fixture,
                "required_profile",
                "ncp-production-ingress-v1",
                profile,
            )
        }
        "ADR010_ACTION_QOS_PROFILE_V1" | "ADR010_INVALID_ACTION_QOS_PROFILE_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "expected_route",
                    "maximum_capacity_per_stream",
                    "required_fail_safe_priority",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_string(fixture, "expected_route", profile)?;
            require_fixture_positive_safe_integer(fixture, "maximum_capacity_per_stream", profile)?;
            require_fixture_string_array(fixture, "required_fail_safe_priority", profile)
        }
        "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "evaluation_utc_ms",
                    "expected_audience",
                    "expected_issuer",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_positive_safe_integer(fixture, "evaluation_utc_ms", profile)?;
            require_fixture_string(fixture, "expected_audience", profile)?;
            require_fixture_string(fixture, "expected_issuer", profile)
        }
        "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1" => {
            expect_fixture_keys(
                fixture,
                &[
                    "authenticated_realm_key",
                    "enrolled_body_principal_id",
                    "gated_commander_principal_id",
                ],
                profile,
            )?;
            validate_realm_fixture(fixture.get("authenticated_realm_key"), profile)?;
            require_fixture_string(fixture, "enrolled_body_principal_id", profile)?;
            require_fixture_string(fixture, "gated_commander_principal_id", profile)
        }
        "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1" => expect_fixture_keys(fixture, &[], profile),
        _ => Err(EngineError::corpus(format!(
            "fixture has unknown profile {profile:?}"
        ))),
    }
}

fn validate_realm_fixture(value: Option<&Value>, label: &str) -> EngineResult<()> {
    let realm = value.and_then(Value::as_object).ok_or_else(|| {
        EngineError::corpus(format!(
            "{label:?} fixture authenticated_realm_key must be an object"
        ))
    })?;
    expect_fixture_keys(
        realm,
        &["server_authority_principal_id", "stable_realm_id"],
        &format!("{label}.authenticated_realm_key"),
    )?;
    require_fixture_string(realm, "server_authority_principal_id", label)?;
    require_fixture_string(realm, "stable_realm_id", label)
}

fn expect_fixture_keys(
    object: &serde_json::Map<String, Value>,
    expected: &[&str],
    label: &str,
) -> EngineResult<()> {
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) {
        return Err(EngineError::corpus(format!(
            "{label:?} fixture has an unknown or missing member"
        )));
    }
    Ok(())
}

fn require_fixture_string(
    object: &serde_json::Map<String, Value>,
    key: &str,
    label: &str,
) -> EngineResult<()> {
    if object
        .get(key)
        .and_then(Value::as_str)
        .is_none_or(str::is_empty)
    {
        return Err(EngineError::corpus(format!(
            "{label:?} fixture member {key:?} must be a non-empty string"
        )));
    }
    Ok(())
}

fn require_fixture_prefixed_sha256(
    object: &serde_json::Map<String, Value>,
    key: &str,
    label: &str,
) -> EngineResult<()> {
    let valid = object
        .get(key)
        .and_then(Value::as_str)
        .and_then(|value| value.strip_prefix("sha256:"))
        .is_some_and(valid_sha256);
    if !valid {
        return Err(EngineError::corpus(format!(
            "{label:?} fixture member {key:?} must be a prefixed lowercase SHA-256"
        )));
    }
    Ok(())
}

fn require_fixture_literal_string(
    object: &serde_json::Map<String, Value>,
    key: &str,
    expected: &str,
    label: &str,
) -> EngineResult<()> {
    if object.get(key).and_then(Value::as_str) != Some(expected) {
        return Err(EngineError::corpus(format!(
            "{label:?} fixture member {key:?} differs from its closed value"
        )));
    }
    Ok(())
}

fn require_fixture_literal_bool(
    object: &serde_json::Map<String, Value>,
    key: &str,
    expected: bool,
    label: &str,
) -> EngineResult<()> {
    if object.get(key).and_then(Value::as_bool) != Some(expected) {
        return Err(EngineError::corpus(format!(
            "{label:?} fixture member {key:?} differs from its closed value"
        )));
    }
    Ok(())
}

fn require_fixture_positive_safe_integer(
    object: &serde_json::Map<String, Value>,
    key: &str,
    label: &str,
) -> EngineResult<()> {
    const MAXIMUM_SAFE_INTEGER: u64 = 9_007_199_254_740_991;
    if object
        .get(key)
        .and_then(Value::as_u64)
        .is_none_or(|value| value == 0 || value > MAXIMUM_SAFE_INTEGER)
    {
        return Err(EngineError::corpus(format!(
            "{label:?} fixture member {key:?} must be a positive safe integer"
        )));
    }
    Ok(())
}

fn require_fixture_string_array(
    object: &serde_json::Map<String, Value>,
    key: &str,
    label: &str,
) -> EngineResult<()> {
    let values = object.get(key).and_then(Value::as_array).ok_or_else(|| {
        EngineError::corpus(format!("{label:?} fixture member {key:?} must be an array"))
    })?;
    let mut unique = BTreeSet::new();
    for value in values {
        let value = value
            .as_str()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                EngineError::corpus(format!(
                    "{label:?} fixture member {key:?} must contain non-empty strings"
                ))
            })?;
        if !unique.insert(value) {
            return Err(EngineError::corpus(format!(
                "{label:?} fixture member {key:?} contains a duplicate"
            )));
        }
    }
    Ok(())
}

fn validate_case_identity(case: &Case) -> EngineResult<()> {
    let expected = match case.id.as_str() {
        "adr001.open-plant-session.kind-separation.v1" => (
            "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
            Scope::ProposedWireFragment,
            Polarity::Positive,
            "ADR-001",
            1,
        ),
        "adr001.plant-session.simulation-field-confusion.v1" => (
            "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
            Scope::ProposedWireFragment,
            Polarity::Negative,
            "ADR-001",
            2,
        ),
        "adr002.realm-bound-contract-identity.v1" => (
            "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
            Scope::ProposedWireFragment,
            Polarity::Positive,
            "ADR-002",
            1,
        ),
        "adr002.compact-hash-substitution.v1" => (
            "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
            Scope::ProposedWireFragment,
            Polarity::Negative,
            "ADR-002",
            2,
        ),
        "adr003.flattened-jws-placeholder.v1" => (
            "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
            Scope::AuthenticatedWireObject,
            Polarity::Negative,
            "ADR-003",
            1,
        ),
        "adr003.protected-header-required-member-projection.v1" => (
            "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1",
            Scope::DecodedHeaderFragment,
            Polarity::Positive,
            "ADR-003",
            2,
        ),
        "adr003.unauthenticated-forwarding-wrapper.v1" => (
            "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
            Scope::AuthenticatedWireObject,
            Polarity::Negative,
            "ADR-003",
            3,
        ),
        "adr004.pending-release-reservation-nonallocation.v1" => (
            "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
            Scope::NonWireInternalState,
            Polarity::Positive,
            "ADR-004",
            1,
        ),
        "adr005.declare-stream.excerpt.v1" => (
            "ADR005_DECLARE_STREAM_EXCERPT_V1",
            Scope::ProposedWireFragment,
            Polarity::Positive,
            "ADR-005",
            1,
        ),
        "adr005.undeclared-frame.hostile.v1" => (
            "ADR005_UNDECLARED_FRAME_V1",
            Scope::ProposedWireFragment,
            Polarity::Negative,
            "ADR-005",
            2,
        ),
        "adr006.body-lease.excerpt.v1" => (
            "ADR006_BODY_LEASE_EXCERPT_V1",
            Scope::ProposedWireFragment,
            Polarity::Positive,
            "ADR-006",
            1,
        ),
        "adr006.self-issued-stale-lease.hostile.v1" => (
            "ADR006_STALE_SELF_ISSUED_LEASE_V1",
            Scope::ProposedWireFragment,
            Polarity::Negative,
            "ADR-006",
            2,
        ),
        "adr007.disposition-query.semantic-projection.v1" => (
            "ADR007_DISPOSITION_QUERY_PROJECTION_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Positive,
            "ADR-007",
            1,
        ),
        "adr007.received-disposition.excerpt.v1" => (
            "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1",
            Scope::ProposedWireFragment,
            Polarity::Positive,
            "ADR-007",
            2,
        ),
        "adr007.unknown-disposition.hostile.v1" => (
            "ADR007_INVALID_DISPOSITION_V1",
            Scope::ProposedWireFragment,
            Polarity::Negative,
            "ADR-007",
            3,
        ),
        "adr008.raw-chunk.semantic-projection.v1" => (
            "ADR008_RAW_CHUNK_PROJECTION_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Positive,
            "ADR-008",
            1,
        ),
        "adr008.evaluated-envelope.excerpt.v1" => (
            "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1",
            Scope::ProposedExtensionEnvelope,
            Polarity::Positive,
            "ADR-008",
            2,
        ),
        "adr008.self-policy.hostile.v1" => (
            "ADR008_GALADRIEL_POLICY_INJECTION_V1",
            Scope::ProposedExtensionEnvelope,
            Polarity::Negative,
            "ADR-008",
            3,
        ),
        "adr009.security-state.semantic-projection.v1" => (
            "ADR009_SECURITY_STATE_PROJECTION_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Positive,
            "ADR-009",
            1,
        ),
        "adr009.ambiguous-mutable-security-state.hostile.v1" => (
            "ADR009_INVALID_SECURITY_STATE_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Negative,
            "ADR-009",
            2,
        ),
        "adr010.action-qos-profile.excerpt.v1" => (
            "ADR010_ACTION_QOS_PROFILE_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Positive,
            "ADR-010",
            1,
        ),
        "adr010.best-effort-receipt-free-profile.hostile.v1" => (
            "ADR010_INVALID_ACTION_QOS_PROFILE_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Negative,
            "ADR-010",
            2,
        ),
        "adr011.gated-intent-correlation.excerpt.v1" => (
            "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1",
            Scope::NonNcpIntentCorrelationFragment,
            Polarity::Positive,
            "ADR-011",
            1,
        ),
        "adr011.identity-laundering-command.hostile.v1" => (
            "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1",
            Scope::ProposedWireFragment,
            Polarity::Negative,
            "ADR-011",
            2,
        ),
        "adr011.effect-path-fencing.semantic-projection.v1" => (
            "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1",
            Scope::ProposedSemanticProjection,
            Polarity::Positive,
            "ADR-011",
            3,
        ),
        _ => {
            return Err(EngineError::corpus(format!(
                "unknown case identity {:?}",
                case.id
            )));
        }
    };
    if case.profile != expected.0
        || case.scope != expected.1
        || case.polarity != expected.2
        || case.source.adr != expected.3
        || case.source.json_fence_ordinal != expected.4
    {
        return Err(EngineError::corpus(format!(
            "case {:?} differs from its closed profile/source identity",
            case.id
        )));
    }
    Ok(())
}

fn expect_exact_set<T>(label: &str, actual: &[T], expected: &[T]) -> EngineResult<()>
where
    T: Copy + Ord,
{
    let actual_set = actual.iter().copied().collect::<BTreeSet<_>>();
    let expected_set = expected.iter().copied().collect::<BTreeSet<_>>();
    if actual.len() != actual_set.len() || actual_set != expected_set {
        return Err(EngineError::corpus(format!(
            "closed {label} values differ from engine v1"
        )));
    }
    Ok(())
}

fn ensure_unique_nonempty(label: &str, values: &[String]) -> EngineResult<()> {
    let mut unique = BTreeSet::new();
    for value in values {
        if value.is_empty() || !unique.insert(value.as_str()) {
            return Err(EngineError::corpus(format!(
                "{label} contains an empty or duplicate value"
            )));
        }
    }
    Ok(())
}

fn validate_identifier(label: &str, value: &str) -> EngineResult<()> {
    let mut bytes = value.bytes();
    let first = bytes.next();
    if value.is_empty()
        || value.len() > 160
        || !first.is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        || !bytes
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || b".-".contains(&byte))
        || !value.ends_with(".v1")
    {
        return Err(EngineError::corpus(format!(
            "invalid {label} identifier {value:?}"
        )));
    }
    Ok(())
}

fn validate_sha256(label: &str, value: &str) -> EngineResult<()> {
    if value.len() != 64
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(EngineError::corpus(format!(
            "{label} SHA-256 is not 64 lowercase hexadecimal characters"
        )));
    }
    Ok(())
}

fn validate_expected_diagnostics(
    owner: &str,
    diagnostics: &[String],
    registry: &BTreeSet<&str>,
) -> EngineResult<()> {
    let mut previous: Option<&str> = None;
    for diagnostic in diagnostics {
        if !registry.contains(diagnostic.as_str()) {
            return Err(EngineError::corpus(format!(
                "{owner:?} uses unregistered diagnostic {diagnostic:?}"
            )));
        }
        if previous.is_some_and(|prior| prior >= diagnostic.as_str()) {
            return Err(EngineError::corpus(format!(
                "{owner:?} diagnostics are not strictly sorted and unique"
            )));
        }
        previous = Some(diagnostic);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use serde_json::json;

    use super::{
        mutation_changes_expected_observation, validate_bounded_fixture,
        validate_global_registry_coverage, validate_identifier, Case, Mutation, Patch,
        PatchOperation, PatchTarget, Polarity, ProductionAdmission, ProfileResult, Scope, Source,
    };

    const PENDING_PROFILE: &str = "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1";
    const LEASE_PROFILE: &str = "ADR006_BODY_LEASE_EXCERPT_V1";

    #[test]
    fn fixture_validation_rejects_unknown_members_and_closed_literal_changes() {
        let unknown_member = json!({
            "expected_state": "PENDING_INTENT_ONLY",
            "output_allocation_permitted": false,
            "unexpected": true
        });
        let changed_literal = json!({
            "expected_state": "ACTIVE",
            "output_allocation_permitted": false
        });
        assert!(validate_bounded_fixture(PENDING_PROFILE, &unknown_member).is_err());
        assert!(validate_bounded_fixture(PENDING_PROFILE, &changed_literal).is_err());
    }

    #[test]
    fn fixture_validation_rejects_nested_unknown_members_and_unsafe_integers() {
        let nested_unknown = json!({
            "current_lease": {
                "holder_entity_id": "controller-a",
                "holder_principal_id": "commander-a",
                "lease_id": "lease-a",
                "session_generation": "generation-a",
                "term": 1,
                "unexpected": true
            },
            "enrolled_body_principal_id": "body-a",
            "evaluation_utc_ms": 1
        });
        let unsafe_integer = json!({
            "current_lease": {
                "holder_entity_id": "controller-a",
                "holder_principal_id": "commander-a",
                "lease_id": "lease-a",
                "session_generation": "generation-a",
                "term": 9_007_199_254_740_992_u64
            },
            "enrolled_body_principal_id": "body-a",
            "evaluation_utc_ms": 1
        });
        assert!(validate_bounded_fixture(LEASE_PROFILE, &nested_unknown).is_err());
        assert!(validate_bounded_fixture(LEASE_PROFILE, &unsafe_integer).is_err());
    }

    #[test]
    fn fixture_validation_accepts_the_closed_pending_shape() {
        let fixture = json!({
            "expected_state": "PENDING_INTENT_ONLY",
            "output_allocation_permitted": false
        });
        assert!(validate_bounded_fixture(PENDING_PROFILE, &fixture).is_ok());
    }

    #[test]
    fn corpus_identifier_validation_matches_the_closed_versioned_grammar() {
        assert!(validate_identifier("case", "adr001.example.v1").is_ok());
        assert!(validate_identifier("case", "_adr001.example.v1").is_err());
        assert!(validate_identifier("case", "adr001_example.v1").is_err());
        assert!(validate_identifier("case", "adr001.example").is_err());
    }

    #[test]
    fn global_identifier_and_diagnostic_coverage_is_exact() {
        let case_ids = BTreeSet::from(["case.v1"]);
        let mutation_ids = BTreeSet::from(["mutation.v1"]);
        let registry = BTreeSet::from(["DIAGNOSTIC"]);
        assert!(
            validate_global_registry_coverage(&case_ids, &mutation_ids, &registry, &registry,)
                .is_ok()
        );
        assert!(validate_global_registry_coverage(
            &case_ids,
            &BTreeSet::from(["case.v1"]),
            &registry,
            &registry,
        )
        .is_err());
        assert!(validate_global_registry_coverage(
            &case_ids,
            &mutation_ids,
            &BTreeSet::new(),
            &registry,
        )
        .is_err());
    }

    #[test]
    fn mutation_expectation_must_change_the_observable_base_tuple() {
        let case = Case {
            id: "case.v1".to_owned(),
            source: Source {
                adr: "ADR-004".to_owned(),
                json_fence_ordinal: 1,
                fence_byte_length: 1,
                fence_sha256: "0".repeat(64),
            },
            scope: Scope::NonWireInternalState,
            profile: PENDING_PROFILE.to_owned(),
            polarity: Polarity::Positive,
            expected_profile_result: ProfileResult::MatchNonWireExcerpt,
            production_admission: ProductionAdmission::NotApplicable,
            bounded_fixture: json!({}),
            expected_diagnostics: Vec::new(),
            payload_interpreted: true,
            mutations: Vec::new(),
        };
        let mut mutation = Mutation {
            id: "mutation.v1".to_owned(),
            purpose: "test".to_owned(),
            patch: Patch {
                target: PatchTarget::Document,
                op: PatchOperation::Add,
                path: "/test".to_owned(),
                value: Some(json!(true)),
            },
            expected_profile_result: ProfileResult::MatchNonWireExcerpt,
            production_admission: ProductionAdmission::NotApplicable,
            expected_diagnostics: Vec::new(),
            payload_interpreted: true,
        };
        assert!(!mutation_changes_expected_observation(&case, &mutation));
        mutation.expected_profile_result = ProfileResult::Reject;
        mutation.production_admission = ProductionAdmission::Reject;
        mutation.expected_diagnostics = vec!["PENDING_STATE_INVALID".to_owned()];
        assert!(mutation_changes_expected_observation(&case, &mutation));
    }
}
