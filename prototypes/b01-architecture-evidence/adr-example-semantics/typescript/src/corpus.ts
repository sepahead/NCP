import { canonicalJsonBytes } from "./canonical-json.ts";
import type { JsonValue } from "./strict-json.ts";

export type Scope =
  | "AUTHENTICATED_WIRE_OBJECT"
  | "DECODED_HEADER_FRAGMENT"
  | "NON_WIRE_INTERNAL_STATE"
  | "PROPOSED_EXTENSION_ENVELOPE"
  | "PROPOSED_SEMANTIC_PROJECTION"
  | "PROPOSED_WIRE_FRAGMENT";

export type Polarity = "NEGATIVE" | "POSITIVE";

export type ProfileResult =
  | "MATCH_NON_AUTHORIZING_EXCERPT"
  | "MATCH_NON_WIRE_EXCERPT"
  | "REJECT";

export type ProductionAdmission =
  | "NOT_APPLICABLE"
  | "NOT_EVALUATED"
  | "REJECT";

export type PatchTarget = "BOUNDED_FIXTURE" | "DOCUMENT";
export type PatchOperationName = "ADD" | "REMOVE" | "REPLACE";

export interface CorpusLimits {
  readonly maximumCorpusBytes: number;
  readonly maximumAggregateAdrBytes: number;
  readonly maximumAdrBytes: number;
  readonly maximumJsonFenceBytes: number;
  readonly maximumFixtureBytes: number;
  readonly maximumJsonDepth: number;
  readonly maximumJsonNodes: number;
  readonly maximumObjectMembers: number;
  readonly maximumArrayItems: number;
  readonly maximumKeyUtf8Bytes: number;
  readonly maximumStringUtf8Bytes: number;
  readonly maximumTotalStringUtf8Bytes: number;
  readonly maximumIntegerCharacters: number;
  readonly expectedCaseCount: number;
  readonly expectedMutationCount: number;
  readonly minimumMutationsPerCase: number;
  readonly maximumMutationsPerCase: number;
  readonly maximumEngineOutputBytes: number;
  readonly engineTimeoutSeconds: number;
}

export interface SourceBinding {
  readonly adr: string;
  readonly jsonFenceOrdinal: number;
  readonly fenceByteLength: number;
  readonly fenceSha256: string;
}

export interface DecisionSetBinding {
  readonly schema: "ncp.b01-decision-set.v1";
  readonly registryPath: "docs/adr/decision-registry.proposed.v1.json";
  readonly digestAlgorithm: "sha256(domain || u64be(projection_bytes) || projection)";
  readonly domainHex: string;
  readonly projectionEncoding: "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE";
  readonly projectionMembers: readonly string[];
  readonly decisionMembers: readonly string[];
  readonly projectionByteLength: number;
  readonly projectionSha256: string;
  readonly sha256: string;
  readonly semanticClosure: JsonObject;
  readonly effect: "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY";
  readonly json: JsonObject;
}

export interface CorpusPatch {
  readonly target: PatchTarget;
  readonly op: PatchOperationName;
  readonly path: string;
  readonly value?: JsonValue;
}

export interface CorpusMutation {
  readonly id: string;
  readonly purpose: string;
  readonly patch: CorpusPatch;
  readonly expectedProfileResult: ProfileResult;
  readonly productionAdmission: ProductionAdmission;
  readonly expectedDiagnostics: readonly string[];
  readonly payloadInterpreted: boolean;
}

export interface CorpusCase {
  readonly id: string;
  readonly source: SourceBinding;
  readonly scope: Scope;
  readonly profile: string;
  readonly polarity: Polarity;
  readonly expectedProfileResult: ProfileResult;
  readonly productionAdmission: ProductionAdmission;
  readonly boundedFixture: JsonValue;
  readonly expectedDiagnostics: readonly string[];
  readonly payloadInterpreted: boolean;
  readonly mutations: readonly CorpusMutation[];
}

export interface Corpus {
  readonly limits: CorpusLimits;
  readonly decisionSetBinding: DecisionSetBinding;
  readonly diagnosticRegistry: ReadonlySet<string>;
  readonly cases: readonly CorpusCase[];
}

type JsonObject = { [key: string]: JsonValue };

const HEX_SHA256 = /^[0-9a-f]{64}$/;
const IDENTIFIER = /^[a-z0-9][a-z0-9.-]*\.v1$/;
const PROFILE = /^ADR(?:00[1-9]|01[01])_[A-Z0-9_]+_V1$/;
const DIAGNOSTIC = /^[A-Z][A-Z0-9_]*$/;
const MAXIMUM_MUTATION_PURPOSE_UTF8_BYTES = 512;
const MAXIMUM_PATCH_PATH_UTF8_BYTES = 512;
const encoder = new TextEncoder();

interface ClosedCaseIdentity {
  readonly profile: string;
  readonly scope: Scope;
  readonly polarity: Polarity;
  readonly adr: string;
  readonly ordinal: number;
}

const CLOSED_CASE_IDENTITIES: Readonly<Record<string, ClosedCaseIdentity>> = {
  "adr001.open-plant-session.kind-separation.v1": {
    profile: "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "POSITIVE",
    adr: "ADR-001",
    ordinal: 1,
  },
  "adr001.plant-session.simulation-field-confusion.v1": {
    profile: "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "NEGATIVE",
    adr: "ADR-001",
    ordinal: 2,
  },
  "adr002.realm-bound-contract-identity.v1": {
    profile: "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "POSITIVE",
    adr: "ADR-002",
    ordinal: 1,
  },
  "adr002.compact-hash-substitution.v1": {
    profile: "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "NEGATIVE",
    adr: "ADR-002",
    ordinal: 2,
  },
  "adr003.flattened-jws-placeholder.v1": {
    profile: "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
    scope: "AUTHENTICATED_WIRE_OBJECT",
    polarity: "NEGATIVE",
    adr: "ADR-003",
    ordinal: 1,
  },
  "adr003.protected-header-required-member-projection.v1": {
    profile: "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1",
    scope: "DECODED_HEADER_FRAGMENT",
    polarity: "POSITIVE",
    adr: "ADR-003",
    ordinal: 2,
  },
  "adr003.unauthenticated-forwarding-wrapper.v1": {
    profile: "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
    scope: "AUTHENTICATED_WIRE_OBJECT",
    polarity: "NEGATIVE",
    adr: "ADR-003",
    ordinal: 3,
  },
  "adr004.pending-release-reservation-nonallocation.v1": {
    profile: "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
    scope: "NON_WIRE_INTERNAL_STATE",
    polarity: "POSITIVE",
    adr: "ADR-004",
    ordinal: 1,
  },
  "adr004.sensor-projection.anti-laundering.v1": {
    profile: "ADR004_SENSOR_PROJECTION_ANTI_LAUNDERING_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-004",
    ordinal: 2,
  },
  "adr005.declare-stream.excerpt.v1": {
    profile: "ADR005_DECLARE_STREAM_EXCERPT_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "POSITIVE",
    adr: "ADR-005",
    ordinal: 1,
  },
  "adr005.undeclared-frame.hostile.v1": {
    profile: "ADR005_UNDECLARED_FRAME_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "NEGATIVE",
    adr: "ADR-005",
    ordinal: 2,
  },
  "adr005.sensor-availability.source-bound.v1": {
    profile: "ADR005_SENSOR_AVAILABILITY_SOURCE_BOUND_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-005",
    ordinal: 3,
  },
  "adr005.sensor-availability.detached-mask.hostile.v1": {
    profile: "ADR005_SENSOR_AVAILABILITY_DETACHED_MASK_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "NEGATIVE",
    adr: "ADR-005",
    ordinal: 4,
  },
  "adr006.body-lease.excerpt.v1": {
    profile: "ADR006_BODY_LEASE_EXCERPT_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "POSITIVE",
    adr: "ADR-006",
    ordinal: 1,
  },
  "adr006.self-issued-stale-lease.hostile.v1": {
    profile: "ADR006_STALE_SELF_ISSUED_LEASE_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "NEGATIVE",
    adr: "ADR-006",
    ordinal: 2,
  },
  "adr007.disposition-query.semantic-projection.v1": {
    profile: "ADR007_DISPOSITION_QUERY_PROJECTION_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-007",
    ordinal: 1,
  },
  "adr007.received-disposition.excerpt.v1": {
    profile: "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "POSITIVE",
    adr: "ADR-007",
    ordinal: 2,
  },
  "adr007.unknown-disposition.hostile.v1": {
    profile: "ADR007_INVALID_DISPOSITION_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "NEGATIVE",
    adr: "ADR-007",
    ordinal: 3,
  },
  "adr007.unavailable-source-restrictive-action.v1": {
    profile: "ADR007_UNAVAILABLE_SOURCE_RESTRICTIVE_ACTION_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-007",
    ordinal: 4,
  },
  "adr008.extension-envelope.semantic-projection.v1": {
    profile: "ADR008_EXTENSION_ENVELOPE_PROJECTION_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-008",
    ordinal: 1,
  },
  "adr008.evaluated-envelope.excerpt.v1": {
    profile: "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1",
    scope: "PROPOSED_EXTENSION_ENVELOPE",
    polarity: "POSITIVE",
    adr: "ADR-008",
    ordinal: 2,
  },
  "adr008.self-policy.hostile.v1": {
    profile: "ADR008_GALADRIEL_POLICY_INJECTION_V1",
    scope: "PROPOSED_EXTENSION_ENVELOPE",
    polarity: "NEGATIVE",
    adr: "ADR-008",
    ordinal: 3,
  },
  "adr008.sensor-condition-detail.semantic-projection.v1": {
    profile: "ADR008_SENSOR_CONDITION_DETAIL_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-008",
    ordinal: 4,
  },
  "adr009.security-state.semantic-projection.v1": {
    profile: "ADR009_SECURITY_STATE_PROJECTION_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-009",
    ordinal: 1,
  },
  "adr009.ambiguous-mutable-security-state.hostile.v1": {
    profile: "ADR009_INVALID_SECURITY_STATE_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "NEGATIVE",
    adr: "ADR-009",
    ordinal: 2,
  },
  "adr010.action-qos-profile.excerpt.v1": {
    profile: "ADR010_ACTION_QOS_PROFILE_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-010",
    ordinal: 1,
  },
  "adr010.best-effort-receipt-free-profile.hostile.v1": {
    profile: "ADR010_INVALID_ACTION_QOS_PROFILE_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "NEGATIVE",
    adr: "ADR-010",
    ordinal: 2,
  },
  "adr010.perception-queue-missingness.semantic-projection.v1": {
    profile: "ADR010_PERCEPTION_QUEUE_MISSINGNESS_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-010",
    ordinal: 3,
  },
  "adr011.registered-haldir-intent.extension-envelope.v1": {
    profile: "ADR011_REGISTERED_HALDIR_INTENT_ENVELOPE_V1",
    scope: "PROPOSED_EXTENSION_ENVELOPE",
    polarity: "POSITIVE",
    adr: "ADR-011",
    ordinal: 1,
  },
  "adr011.identity-laundering-command.hostile.v1": {
    profile: "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1",
    scope: "PROPOSED_WIRE_FRAGMENT",
    polarity: "NEGATIVE",
    adr: "ADR-011",
    ordinal: 2,
  },
  "adr011.effect-path-fencing.semantic-projection.v1": {
    profile: "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-011",
    ordinal: 3,
  },
  "adr011.prepared-frame-publisher-boundary.semantic-projection.v1": {
    profile: "ADR011_PREPARED_FRAME_PUBLISHER_BOUNDARY_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-011",
    ordinal: 4,
  },
  "adr011.x02-fleet-availability-layout.v1": {
    profile: "ADR011_X02_FLEET_AVAILABILITY_LAYOUT_V1",
    scope: "PROPOSED_SEMANTIC_PROJECTION",
    polarity: "POSITIVE",
    adr: "ADR-011",
    ordinal: 5,
  },
};
const CLOSED_DIAGNOSTIC_REGISTRY = [
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
  "EXTENSION_ACTIVATION_TIME_BINDING_REQUIRED",
  "EXTENSION_AMBIENT_FETCH_CREDENTIAL_FORBIDDEN",
  "EXTENSION_ATTACHMENT_FETCH_AUTHORITY_INVALID",
  "EXTENSION_ATTACHMENT_REDIRECT_FORBIDDEN",
  "EXTENSION_ATTACHMENT_REFERENCE_BOUNDS_REQUIRED",
  "EXTENSION_ATTACHMENT_STORE_ENROLLMENT_REQUIRED",
  "EXTENSION_ATTACHMENT_VERIFICATION_REQUIRED",
  "EXTENSION_CALLBACK_BOUNDARY_STATE_REQUIRED",
  "EXTENSION_CALLBACK_RIGHT_CONSUMPTION_REQUIRED",
  "EXTENSION_CALLBACK_VALIDATION_ORDER_INVALID",
  "EXTENSION_CANONICAL_NUMBER_POLICY_INVALID",
  "EXTENSION_CORE_OR_REGISTERED_REQUIRED",
  "EXTENSION_DUPLICATE_KEY_POLICY_INVALID",
  "EXTENSION_GENERIC_CHUNK_PROTOCOL_FORBIDDEN",
  "EXTENSION_ID_MISMATCH",
  "EXTENSION_INLINE_ATTACHMENT_FORBIDDEN",
  "EXTENSION_MANIFEST_DIGEST_MISMATCH",
  "EXTENSION_MANIFEST_SELECTION_REQUIRED",
  "EXTENSION_ONE_ENVELOPE_REQUIRED",
  "EXTENSION_PARTIAL_ATTACHMENT_USE_FORBIDDEN",
  "EXTENSION_POLICY_FIELD_FORBIDDEN",
  "EXTENSION_POST_FETCH_CURRENTNESS_RECHECK_REQUIRED",
  "EXTENSION_PRODUCER_ROLE_INVALID",
  "EXTENSION_RECEIVER_ACTIVATION_INCARNATION_REQUIRED",
  "EXTENSION_RECEIVER_ROLE_INVALID",
  "EXTENSION_RESERVATION_ORDER_INVALID",
  "EXTENSION_RETIRED_RESULT_DISCLOSURE_FORBIDDEN",
  "EXTENSION_SCHEMA_VERSION_MISMATCH",
  "EXTENSION_SEMANTIC_ENCODING_INVALID",
  "EXTENSION_SVG_PROTOCOL_INPUT_FORBIDDEN",
  "EXTENSION_TERMINAL_LOOKUP_ORDER_INVALID",
  "EXTENSION_TERMINAL_TOMBSTONE_REQUIRED",
  "EXTENSION_UNKNOWN_MEMBER_POLICY_INVALID",
  "EXTENSION_WIRE_URL_FORBIDDEN",
  "FAIL_SAFE_EARLY_EFFECT_MODE_INVALID",
  "FAIL_SAFE_EFFECT_BOUNDARY_RECHECK_REQUIRED",
  "FAIL_SAFE_PRIORITY_INVALID",
  "HOLD_ADMISSION_ORDER_INVALID",
  "INTENT_AUDIENCE_MISMATCH",
  "INTENT_DEADLINE_INVALID",
  "INTENT_ENVELOPE_SHAPE_INVALID",
  "INTENT_EXPIRED",
  "INTENT_FRESHNESS_CLOCK_MISMATCH",
  "INTENT_FRESHNESS_GRANT_INSTALLATION_RECEIPT_MISMATCH",
  "INTENT_FRESHNESS_GRANT_MISMATCH",
  "INTENT_FRESHNESS_SLOT_INVALID",
  "INTENT_ISSUER_MISMATCH",
  "INTENT_REPLAY_COORDINATE_INVALID",
  "INTENT_REQUESTED_EFFECT_INVALID",
  "INTENT_SESSION_MISMATCH",
  "INTENT_SIGNATURE_COVERAGE_INVALID",
  "INTENT_SOURCE_UNION_INVALID",
  "INTENT_VALIDITY_INVALID",
  "KEY_EPOCH_MEMBERSHIP_REQUIRED",
  "KEY_ID_NOT_CONTENT_ADDRESSED",
  "LEASE_ISSUER_NOT_BODY",
  "LEASE_NOT_CURRENT",
  "MESSAGE_KIND_MISMATCH",
  "NCP_VERSION_MISMATCH",
  "OUTPUT_ALLOCATION_FLAG_INVALID",
  "PENDING_STATE_ALLOCATES_OUTPUT",
  "PENDING_STATE_INVALID",
  "PERCEPTION_AUTHENTICATED_PRODUCER_POSITION_PRESERVATION_REQUIRED",
  "PERCEPTION_AVAILABLE_ZERO_OBSERVATION_REQUIRED",
  "PERCEPTION_GAP_UNAVAILABILITY_INFERENCE_FORBIDDEN",
  "PERCEPTION_ITEM_DIGEST_UNITY_REQUIRED",
  "PERCEPTION_ITEM_INDIVISIBILITY_REQUIRED",
  "PERCEPTION_ITEM_PARTIAL_MUTATION_FORBIDDEN",
  "PERCEPTION_ITEM_POSITION_UNITY_REQUIRED",
  "PERCEPTION_ITEM_QUEUE_SLOT_UNITY_REQUIRED",
  "PERCEPTION_ITEM_SUPERSESSION_UNITY_REQUIRED",
  "PERCEPTION_LOSS_GAP_COLLAPSE_FORBIDDEN",
  "PERCEPTION_MISSINGNESS_STATES_INVALID",
  "PERCEPTION_PRODUCER_POST_ASSIGNMENT_POSITION_CONSUMED_REQUIRED",
  "PERCEPTION_PRODUCER_PRE_ASSIGNMENT_VALIDATION_REQUIRED",
  "PERCEPTION_QUEUE_MISSINGNESS_PROJECTION_INVALID",
  "PERCEPTION_RECEIVER_MALFORMED_ADMISSION_FORBIDDEN",
  "PERCEPTION_RECEIVER_MALFORMED_CALLBACK_FORBIDDEN",
  "PERCEPTION_RECEIVER_MALFORMED_PIN_FORBIDDEN",
  "PERCEPTION_RECEIVER_POSITION_ROLLBACK_FORBIDDEN",
  "PERCEPTION_UNAVAILABLE_OBSERVATION_FORBIDDEN",
  "PERCEPTION_ZERO_OMISSION_INFERENCE_FORBIDDEN",
  "PLANT_CONTAINS_SIMULATION_ONLY_MEMBER",
  "PLANT_PROFILE_MISSING",
  "PLANT_SECURITY_CONTEXT_MISSING",
  "POST_EFFECT_ADMISSION_MODE_INVALID",
  "PREPARED_APPLICATION_MUTABLE_ALIAS_FORBIDDEN",
  "PREPARED_APPLICATION_PUBLISHER_EXCLUSIVITY_REQUIRED",
  "PREPARED_AVAILABILITY_BYTE_COUNT_FORMULA_REQUIRED",
  "PREPARED_AVAILABILITY_GROUP_PARTITION_REQUIRED",
  "PREPARED_AVAILABILITY_INLINE_REQUIRED",
  "PREPARED_CALLER_UNAVAILABLE_SLOT_WRITE_FORBIDDEN",
  "PREPARED_CLOCK_OWNERSHIP_FORBIDDEN",
  "PREPARED_COMPLETE_FRAME_WRITE_REQUIRED",
  "PREPARED_DETACHED_BUFFER_REBIND_FORBIDDEN",
  "PREPARED_EQUAL_VALUE_DETECTION_OVERCLAIM",
  "PREPARED_EXACT_BYTE_TRANSFER_REQUIRED",
  "PREPARED_FINAL_POSITION_REQUIRED",
  "PREPARED_FOREIGN_SLOT_HANDLE_FORBIDDEN",
  "PREPARED_HOT_FRAME_TAG_FORBIDDEN",
  "PREPARED_LAYOUT_BOUND_TRANSPORT_SLOT_REQUIRED",
  "PREPARED_LAYOUT_INSTANCE_REQUIRED",
  "PREPARED_NON_SENSOR_AVAILABILITY_BYTES_INVALID",
  "PREPARED_NON_SENSOR_GROUP_COUNT_INVALID",
  "PREPARED_PRE_SEAL_DETECTION_OVERCLAIM",
  "PREPARED_PROFILE_RULES_REQUIRED",
  "PREPARED_RAW_APPLICATION_PUBLISHER_FORBIDDEN",
  "PREPARED_RECEIVER_ATTESTATION_OVERCLAIM",
  "PREPARED_RECEIVER_POST_OPEN_DETECTION_OVERCLAIM",
  "PREPARED_SEALED_BYTE_PROTECTION_REQUIRED",
  "PREPARED_SEALED_RECORD_MUTATION_FORBIDDEN",
  "PREPARED_SENDER_PRE_SEAL_DETECTION_OVERCLAIM",
  "PREPARED_SENSOR_LAYOUT_POSITIVE_GROUP_COUNT_REQUIRED",
  "PREPARED_SEPARATE_APPLICATION_CREDENTIAL_HOLDER_FORBIDDEN",
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
  "SENSOR_AVAILABILITY_BITMAP_REQUIRED",
  "SENSOR_AVAILABILITY_DETACHED_FORBIDDEN",
  "SENSOR_AVAILABILITY_DIGEST_BINDING_REQUIRED",
  "SENSOR_AVAILABILITY_GROUP_DECISION_REQUIRED",
  "SENSOR_AVAILABILITY_POSITION_ORDER_REQUIRED",
  "SENSOR_AVAILABILITY_PROJECTION_INVALID",
  "SENSOR_AVAILABILITY_SOURCE_DUPLICATION_FORBIDDEN",
  "SENSOR_AVAILABLE_GROUP_COMPLETENESS_REQUIRED",
  "SENSOR_COMPATIBILITY_AVAILABILITY_INFERENCE_FORBIDDEN",
  "SENSOR_COMPATIBILITY_AVAILABILITY_PRESERVATION_REQUIRED",
  "SENSOR_CONDITION_DETAIL_ABSENCE_RESULT_INVALID",
  "SENSOR_CONDITION_DETAIL_ACTION_BLOCKING_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_AUTHORITY_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_AVAILABILITY_AUTHORITY_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_AVAILABLE_UNKNOWN_REJECTION_REQUIRED",
  "SENSOR_CONDITION_DETAIL_BITMAP_REPETITION_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_CONTRADICTION_REJECTION_REQUIRED",
  "SENSOR_CONDITION_DETAIL_DUPLICATE_REJECTION_REQUIRED",
  "SENSOR_CONDITION_DETAIL_ENTRY_BOUNDS_REQUIRED",
  "SENSOR_CONDITION_DETAIL_ENTRY_ORDER_REQUIRED",
  "SENSOR_CONDITION_DETAIL_ENTRY_SHAPE_INVALID",
  "SENSOR_CONDITION_DETAIL_FAILURE_SCOPE_REQUIRED",
  "SENSOR_CONDITION_DETAIL_LAYOUT_REPETITION_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_OPTIONALITY_REQUIRED",
  "SENSOR_CONDITION_DETAIL_PERCEPTION_BLOCKING_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_PROJECTION_INVALID",
  "SENSOR_CONDITION_DETAIL_REASON_BOUNDS_REQUIRED",
  "SENSOR_CONDITION_DETAIL_RECORD_SHAPE_INVALID",
  "SENSOR_CONDITION_DETAIL_RESOURCE_ISOLATION_REQUIRED",
  "SENSOR_CONDITION_DETAIL_SCALAR_REPETITION_FORBIDDEN",
  "SENSOR_CONDITION_DETAIL_SOURCE_CURRENTNESS_REJECTION_REQUIRED",
  "SENSOR_CONDITION_DETAIL_SOURCE_REQUIRED",
  "SENSOR_CONDITION_DETAIL_SOURCE_RESOLUTION_ORDER_REQUIRED",
  "SENSOR_CONDITION_DETAIL_UNKNOWN_REASON_REJECTION_REQUIRED",
  "SENSOR_LIVE_SOURCE_PIN_EVICTION_FORBIDDEN",
  "SENSOR_POST_ASSIGNMENT_FAILURE_GAP_REQUIRED",
  "SENSOR_PROJECTION_ANTI_LAUNDERING_INVALID",
  "SENSOR_PROJECTION_AVAILABILITY_BINDING_REQUIRED",
  "SENSOR_PROJECTION_AVAILABLE_INPUT_REQUIRED",
  "SENSOR_PROJECTION_LAYOUT_REBIND_REQUIRED",
  "SENSOR_PROJECTION_ORIGIN_IDENTITY_REQUIRED",
  "SENSOR_PROJECTION_PLACEHOLDER_LAUNDERING_FORBIDDEN",
  "SENSOR_PROJECTION_TIGHTEN_ONLY_REQUIRED",
  "SENSOR_PROJECTION_UNAVAILABLE_UPGRADE_FORBIDDEN",
  "SENSOR_RECEIVER_REJECTION_POSITION_ROLLBACK_FORBIDDEN",
  "SENSOR_SOURCE_PIN_CAPACITY_RESERVATION_REQUIRED",
  "SENSOR_SOURCE_PIN_RESTART_CLOSURE_REQUIRED",
  "SENSOR_SOURCE_PIN_RETENTION_REQUIRED",
  "SENSOR_UNAVAILABLE_GROUP_VALUE_FORBIDDEN",
  "SENSOR_UNAVAILABLE_PLACEHOLDER_EXPOSURE_FORBIDDEN",
  "SENSOR_UNAVAILABLE_PLACEHOLDER_INTERNAL_REQUIRED",
  "SESSION_KIND_MISMATCH",
  "SIGNATURE_LENGTH_INVALID",
  "SIGNATURE_NOT_VALID",
  "SOURCE_DEPENDENCY_OVERLAP_PREPARATION_REJECTION_REQUIRED",
  "SOURCE_GROUP_DEPENDENCY_LAYOUT_BINDING_REQUIRED",
  "SOURCE_PIN_AVAILABILITY_REQUIRED",
  "SOURCE_RESTRICTED_ACTIVE_DISPOSITION_INVALID",
  "SOURCE_RESTRICTIVE_ACTION_REQUIRED",
  "SOURCE_RESTRICTIVE_ACTION_UNIVERSAL_ZERO_FORBIDDEN",
  "SOURCE_RESTRICTIVE_COMMAND_ATOMIC_REJECT_REQUIRED",
  "SOURCE_RESTRICTIVE_PROJECTION_INVALID",
  "STABLE_CORE_DIGEST_INVALID",
  "STABLE_CORE_DIGEST_MISMATCH",
  "STABLE_CORE_DIGEST_MISSING_OR_NULL",
  "STREAM_DECLARATION_NOT_LIVE",
  "STREAM_EPOCH_ALREADY_LIVE",
  "STREAM_EPOCH_REQUIRED",
  "STREAM_SEQUENCE_START_INVALID",
  "UNPROTECTED_HEADER_FORBIDDEN",
  "WIRE_VERSION_MISMATCH",
  "X02_ALL_AVAILABLE_VECTOR_INVALID",
  "X02_AVAILABILITY_BITMAP_POLARITY_INVALID",
  "X02_AVAILABILITY_BIT_ORDER_INVALID",
  "X02_AVAILABILITY_BYTE_COUNTS_INVALID",
  "X02_AVAILABILITY_GROUP_WIDTH_INVALID",
  "X02_AVAILABILITY_PADDING_INVALID",
  "X02_COMMAND_SCALAR_WIDTH_INVALID",
  "X02_COMPOSITE_SESSION_REQUIRED",
  "X02_DEPENDENCY_OVERLAP_PREPARATION_REJECTION_REQUIRED",
  "X02_EXHAUSTIVE_MASKS_INVALID",
  "X02_FIRST_UNAVAILABLE_VECTOR_INVALID",
  "X02_FLEET_AVAILABILITY_PROJECTION_INVALID",
  "X02_GROUP_COMMAND_SLOT_MAP_INVALID",
  "X02_LANE_STATE_SEQUENCE_INVALID",
  "X02_MUSIC_CLOCK_OWNERSHIP_FORBIDDEN",
  "X02_ONE_NEST_KERNEL_REQUIRED",
  "X02_SENSOR_SCALAR_WIDTH_INVALID",
  "X02_UNAVAILABLE_PLACEHOLDER_BITS_INVALID",
  "X02_WASHOUT_FAULT_RETURN_INVALID",
] as const;
const ROOT_KEYS = [
  "candidate",
  "cases",
  "claim_boundary",
  "closed_values",
  "decision_set_binding",
  "diagnostic_registry",
  "limits",
  "schema",
  "schema_version",
  "source_binding",
  "task",
  "wire_version",
] as const;

const DECISION_BINDING_KEYS = [
  "decision_members",
  "digest_algorithm",
  "domain_hex",
  "effect",
  "projection_byte_length",
  "projection_encoding",
  "projection_members",
  "projection_sha256",
  "registry_path",
  "schema",
  "semantic_closure",
  "sha256",
] as const;

const PROJECTION_MEMBERS = [
  "schema",
  "candidate",
  "wire_version",
  "review_policy",
  "semantic_closure",
  "decisions",
] as const;

const SEMANTIC_CLOSURE_KEYS = ["json_schema", "source"] as const;
const ARTIFACT_IDENTITY_KEYS = ["bytes", "path", "sha256"] as const;

const DECISION_MEMBERS = [
  "id",
  "title",
  "path",
  "module_paths",
  "content_sha256",
  "bytes",
  "source_set",
  "required_reviews",
  "defect_ids",
] as const;

const SOURCE_BINDING_KEYS = [
  "fence_capture",
  "fence_language",
  "path_root",
  "sha256_encoding",
] as const;

const LIMIT_KEYS = [
  "allow_floats",
  "engine_timeout_seconds",
  "expected_case_count",
  "expected_mutation_count",
  "maximum_adr_bytes",
  "maximum_aggregate_adr_bytes",
  "maximum_array_items",
  "maximum_corpus_bytes",
  "maximum_engine_output_bytes",
  "maximum_integer_characters",
  "maximum_json_depth",
  "maximum_json_fence_bytes",
  "maximum_fixture_bytes",
  "maximum_json_nodes",
  "maximum_key_utf8_bytes",
  "maximum_object_members",
  "maximum_string_utf8_bytes",
  "maximum_total_string_utf8_bytes",
  "maximum_mutations_per_case",
  "minimum_mutations_per_case",
] as const;

const CLOSED_VALUE_KEYS = [
  "patch_operation",
  "patch_target",
  "polarity",
  "production_admission",
  "profile_result",
  "scope",
] as const;

const CLAIM_KEYS = [
  "adrs_accepted",
  "external_gate_satisfied",
  "independent_evidence_satisfied",
  "interoperability_established",
  "normative_contract_changed",
  "production_admission_implemented",
  "release_authorized",
] as const;

const CASE_KEYS = [
  "bounded_fixture",
  "expected_diagnostics",
  "expected_profile_result",
  "id",
  "mutations",
  "payload_interpreted",
  "polarity",
  "production_admission",
  "profile",
  "scope",
  "source",
] as const;

const SOURCE_KEYS = [
  "adr",
  "fence_byte_length",
  "fence_sha256",
  "json_fence_ordinal",
] as const;

const MUTATION_KEYS = [
  "expected_diagnostics",
  "expected_profile_result",
  "id",
  "patch",
  "payload_interpreted",
  "production_admission",
  "purpose",
] as const;

const PATCH_WITH_VALUE_KEYS = ["op", "path", "target", "value"] as const;
const PATCH_WITHOUT_VALUE_KEYS = ["op", "path", "target"] as const;

const SCOPES: readonly Scope[] = [
  "AUTHENTICATED_WIRE_OBJECT",
  "DECODED_HEADER_FRAGMENT",
  "NON_WIRE_INTERNAL_STATE",
  "PROPOSED_EXTENSION_ENVELOPE",
  "PROPOSED_SEMANTIC_PROJECTION",
  "PROPOSED_WIRE_FRAGMENT",
];
const POLARITIES: readonly Polarity[] = ["NEGATIVE", "POSITIVE"];
const PROFILE_RESULTS: readonly ProfileResult[] = [
  "MATCH_NON_AUTHORIZING_EXCERPT",
  "MATCH_NON_WIRE_EXCERPT",
  "REJECT",
];
const PRODUCTION_ADMISSIONS: readonly ProductionAdmission[] = [
  "NOT_APPLICABLE",
  "NOT_EVALUATED",
  "REJECT",
];
const PATCH_TARGETS: readonly PatchTarget[] = ["BOUNDED_FIXTURE", "DOCUMENT"];
const PATCH_OPERATIONS: readonly PatchOperationName[] = ["ADD", "REMOVE", "REPLACE"];

const REGISTERED_LIMITS: CorpusLimits = Object.freeze({
  maximumCorpusBytes: 262_144,
  maximumAggregateAdrBytes: 2_097_152,
  maximumAdrBytes: 262_144,
  maximumJsonFenceBytes: 131_072,
  maximumFixtureBytes: 16_384,
  maximumJsonDepth: 32,
  maximumJsonNodes: 100_000,
  maximumObjectMembers: 4_096,
  maximumArrayItems: 4_096,
  maximumKeyUtf8Bytes: 128,
  maximumStringUtf8Bytes: 65_536,
  maximumTotalStringUtf8Bytes: 131_072,
  maximumIntegerCharacters: 32,
  expectedCaseCount: 33,
  expectedMutationCount: 289,
  minimumMutationsPerCase: 2,
  maximumMutationsPerCase: 32,
  maximumEngineOutputBytes: 262_144,
  engineTimeoutSeconds: 120,
});

export class CorpusError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CorpusError";
  }
}

export function validateCorpus(value: JsonValue): Corpus {
  const root = requiredObject(value, "corpus");
  exactKeys(root, ROOT_KEYS, "corpus");
  exactString(root, "schema", "ncp.b01-adr-example-semantics-corpus.v1", "corpus");
  exactInteger(root, "schema_version", 1, "corpus");
  exactString(root, "task", "B01", "corpus");
  exactString(root, "candidate", "1.0.0-rc.1", "corpus");
  exactString(root, "wire_version", "1.0", "corpus");

  validateSourceBinding(requiredObject(root.source_binding, "source_binding"));
  const limits = validateLimits(requiredObject(root.limits, "limits"));
  validateClosedValues(requiredObject(root.closed_values, "closed_values"));
  const decisionSetBinding = validateDecisionSetBinding(
    requiredObject(root.decision_set_binding, "decision_set_binding"),
    limits,
  );

  const diagnosticValues = stringArray(root.diagnostic_registry, "diagnostic_registry");
  requireSortedUnique(diagnosticValues, "diagnostic_registry");
  for (const diagnostic of diagnosticValues) {
    if (!DIAGNOSTIC.test(diagnostic)) {
      fail(`diagnostic_registry contains invalid identifier ${JSON.stringify(diagnostic)}`);
    }
  }
  if (
    diagnosticValues.length !== CLOSED_DIAGNOSTIC_REGISTRY.length ||
    diagnosticValues.some(
      (diagnostic, index) => diagnostic !== CLOSED_DIAGNOSTIC_REGISTRY[index],
    )
  ) {
    fail("diagnostic_registry differs from the closed engine vocabulary");
  }
  const diagnosticRegistry = new Set(diagnosticValues);

  const claims = requiredObject(root.claim_boundary, "claim_boundary");
  exactKeys(claims, CLAIM_KEYS, "claim_boundary");
  for (const key of CLAIM_KEYS) {
    if (claims[key] !== false) fail(`claim_boundary.${key} must be false`);
  }

  const rawCases = requiredArray(root.cases, "cases");
  if (rawCases.length !== limits.expectedCaseCount) {
    fail(`cases has ${rawCases.length} entries; expected ${limits.expectedCaseCount}`);
  }
  const cases = rawCases.map((entry, index) =>
    validateCase(entry, index, limits, diagnosticRegistry),
  );
  validateCorpusRelationships(cases, limits, diagnosticRegistry);
  return { limits, decisionSetBinding, diagnosticRegistry, cases };
}

function validateDecisionSetBinding(
  value: JsonObject,
  limits: CorpusLimits,
): DecisionSetBinding {
  exactKeys(value, DECISION_BINDING_KEYS, "decision_set_binding");
  exactString(value, "schema", "ncp.b01-decision-set.v1", "decision_set_binding");
  exactString(
    value,
    "registry_path",
    "docs/adr/decision-registry.proposed.v1.json",
    "decision_set_binding",
  );
  exactString(
    value,
    "digest_algorithm",
    "sha256(domain || u64be(projection_bytes) || projection)",
    "decision_set_binding",
  );
  exactString(
    value,
    "projection_encoding",
    "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE",
    "decision_set_binding",
  );
  exactString(
    value,
    "effect",
    "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY",
    "decision_set_binding",
  );
  const domainHex = requiredString(value.domain_hex, "decision_set_binding.domain_hex");
  if (domainHex !== "6e63702e6230312d6465636973696f6e2d7365742e763100") {
    fail("decision_set_binding.domain_hex is not the registered v1 domain");
  }
  exactStringArray(
    value.projection_members,
    PROJECTION_MEMBERS,
    "decision_set_binding.projection_members",
  );
  exactStringArray(
    value.decision_members,
    DECISION_MEMBERS,
    "decision_set_binding.decision_members",
  );
  const semanticClosure = validateSemanticClosureBinding(value.semantic_closure);
  const projectionByteLength = positiveInteger(
    value.projection_byte_length,
    "decision_set_binding.projection_byte_length",
  );
  if (projectionByteLength > limits.maximumCorpusBytes) {
    fail("decision_set_binding.projection_byte_length exceeds its bound");
  }
  return {
    schema: "ncp.b01-decision-set.v1",
    registryPath: "docs/adr/decision-registry.proposed.v1.json",
    digestAlgorithm: "sha256(domain || u64be(projection_bytes) || projection)",
    domainHex,
    projectionEncoding: "UTF8_JSON_SORTED_KEYS_COMPACT_ENSURE_ASCII_FALSE",
    projectionMembers: PROJECTION_MEMBERS,
    decisionMembers: DECISION_MEMBERS,
    projectionByteLength,
    projectionSha256: sha256String(
      value.projection_sha256,
      "decision_set_binding.projection_sha256",
    ),
    sha256: sha256String(value.sha256, "decision_set_binding.sha256"),
    semanticClosure,
    effect: "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY",
    json: value,
  };
}

function validateSemanticClosureBinding(value: JsonValue | undefined): JsonObject {
  const closure = requiredObject(value, "decision_set_binding.semantic_closure");
  exactKeys(closure, SEMANTIC_CLOSURE_KEYS, "decision_set_binding.semantic_closure");
  validateArtifactIdentity(
    closure.source,
    "decision_set_binding.semantic_closure.source",
    "docs/adr/decision-closure.source.v1.json",
    REGISTERED_LIMITS.maximumCorpusBytes,
  );
  validateArtifactIdentity(
    closure.json_schema,
    "decision_set_binding.semantic_closure.json_schema",
    "docs/adr/decision-closure.source.schema.v1.json",
    REGISTERED_LIMITS.maximumCorpusBytes,
  );
  return closure;
}

function validateArtifactIdentity(
  value: JsonValue | undefined,
  label: string,
  path: string,
  maximumBytes: number,
): void {
  const identity = requiredObject(value, label);
  exactKeys(identity, ARTIFACT_IDENTITY_KEYS, label);
  exactString(identity, "path", path, label);
  const byteLength = positiveInteger(identity.bytes, `${label}.bytes`);
  if (byteLength > maximumBytes) {
    fail(`${label}.bytes exceeds the artifact bound`);
  }
  sha256String(identity.sha256, `${label}.sha256`);
}

function validateSourceBinding(value: JsonObject): void {
  exactKeys(value, SOURCE_BINDING_KEYS, "source_binding");
  exactString(value, "fence_language", "json", "source_binding");
  exactString(
    value,
    "fence_capture",
    "content_between_top_level_exact_json_fence_lines_excluding_one_terminal_line_ending",
    "source_binding",
  );
  exactString(value, "path_root", "repository", "source_binding");
  exactString(value, "sha256_encoding", "lowercase_hex", "source_binding");
}

function validateLimits(value: JsonObject): CorpusLimits {
  exactKeys(value, LIMIT_KEYS, "limits");
  if (value.allow_floats !== false) fail("limits.allow_floats must be false");
  const integer = (key: string): number => positiveInteger(value[key], `limits.${key}`);
  const limits: CorpusLimits = {
    maximumCorpusBytes: integer("maximum_corpus_bytes"),
    maximumAggregateAdrBytes: integer("maximum_aggregate_adr_bytes"),
    maximumAdrBytes: integer("maximum_adr_bytes"),
    maximumJsonFenceBytes: integer("maximum_json_fence_bytes"),
    maximumFixtureBytes: integer("maximum_fixture_bytes"),
    maximumJsonDepth: integer("maximum_json_depth"),
    maximumJsonNodes: integer("maximum_json_nodes"),
    maximumObjectMembers: integer("maximum_object_members"),
    maximumArrayItems: integer("maximum_array_items"),
    maximumKeyUtf8Bytes: integer("maximum_key_utf8_bytes"),
    maximumStringUtf8Bytes: integer("maximum_string_utf8_bytes"),
    maximumTotalStringUtf8Bytes: integer("maximum_total_string_utf8_bytes"),
    maximumIntegerCharacters: integer("maximum_integer_characters"),
    expectedCaseCount: integer("expected_case_count"),
    expectedMutationCount: integer("expected_mutation_count"),
    minimumMutationsPerCase: integer("minimum_mutations_per_case"),
    maximumMutationsPerCase: integer("maximum_mutations_per_case"),
    maximumEngineOutputBytes: integer("maximum_engine_output_bytes"),
    engineTimeoutSeconds: integer("engine_timeout_seconds"),
  };
  if (limits.minimumMutationsPerCase > limits.maximumMutationsPerCase) {
    fail("minimum_mutations_per_case exceeds maximum_mutations_per_case");
  }
  if (limits.maximumJsonFenceBytes > limits.maximumAdrBytes) {
    fail("maximum_json_fence_bytes exceeds maximum_adr_bytes");
  }
  for (const key of Object.keys(REGISTERED_LIMITS) as (keyof CorpusLimits)[]) {
    if (limits[key] !== REGISTERED_LIMITS[key]) {
      fail(`limits.${key} differs from the registered v1 bound`);
    }
  }
  return limits;
}

function validateClosedValues(value: JsonObject): void {
  exactKeys(value, CLOSED_VALUE_KEYS, "closed_values");
  exactStringArray(value.scope, SCOPES, "closed_values.scope");
  exactStringArray(value.polarity, POLARITIES, "closed_values.polarity");
  exactStringArray(value.profile_result, PROFILE_RESULTS, "closed_values.profile_result");
  exactStringArray(
    value.production_admission,
    PRODUCTION_ADMISSIONS,
    "closed_values.production_admission",
  );
  exactStringArray(value.patch_target, PATCH_TARGETS, "closed_values.patch_target");
  exactStringArray(
    value.patch_operation,
    PATCH_OPERATIONS,
    "closed_values.patch_operation",
  );
}

function validateCase(
  value: JsonValue,
  index: number,
  limits: CorpusLimits,
  diagnostics: ReadonlySet<string>,
): CorpusCase {
  const label = `cases[${index}]`;
  const object = requiredObject(value, label);
  exactKeys(object, CASE_KEYS, label);
  const id = identifier(object.id, `${label}.id`);
  const source = validateCaseSource(requiredObject(object.source, `${label}.source`), label, limits);
  const scope = enumString(object.scope, SCOPES, `${label}.scope`);
  const profile = requiredString(object.profile, `${label}.profile`);
  if (!PROFILE.test(profile)) fail(`${label}.profile is not a closed profile identifier`);
  const polarity = enumString(object.polarity, POLARITIES, `${label}.polarity`);
  const identity = CLOSED_CASE_IDENTITIES[id];
  if (identity === undefined) fail(`${label}.id is not a closed v1 case identity`);
  if (
    profile !== identity.profile ||
    scope !== identity.scope ||
    polarity !== identity.polarity ||
    source.adr !== identity.adr ||
    source.jsonFenceOrdinal !== identity.ordinal
  ) {
    fail(`${label} differs from its closed profile/source identity`);
  }
  const expectedProfileResult = enumString(
    object.expected_profile_result,
    PROFILE_RESULTS,
    `${label}.expected_profile_result`,
  );
  const productionAdmission = enumString(
    object.production_admission,
    PRODUCTION_ADMISSIONS,
    `${label}.production_admission`,
  );
  const boundedFixture = requiredObject(object.bounded_fixture, `${label}.bounded_fixture`);
  canonicalJsonBytes(boundedFixture, limits.maximumFixtureBytes);
  const expectedDiagnostics = diagnosticArray(
    object.expected_diagnostics,
    `${label}.expected_diagnostics`,
    diagnostics,
  );
  const payloadInterpreted = requiredBoolean(
    object.payload_interpreted,
    `${label}.payload_interpreted`,
  );
  const rawMutations = requiredArray(object.mutations, `${label}.mutations`);
  if (
    rawMutations.length < limits.minimumMutationsPerCase ||
    rawMutations.length > limits.maximumMutationsPerCase
  ) {
    fail(
      `${label}.mutations count is outside ${limits.minimumMutationsPerCase}..${limits.maximumMutationsPerCase}`,
    );
  }
  const mutations = rawMutations.map((entry, mutationIndex) =>
    validateMutation(entry, `${label}.mutations[${mutationIndex}]`, diagnostics),
  );
  const caseNamespace = source.adr.toLowerCase().replace("-", "");
  const profileNamespace = source.adr.replace("-", "");
  if (!id.startsWith(`${caseNamespace}.`)) {
    fail(`${label}.id is not namespaced to ${source.adr}`);
  }
  if (!profile.startsWith(`${profileNamespace}_`)) {
    fail(`${label}.profile is not namespaced to ${source.adr}`);
  }
  if (polarity === "POSITIVE" && payloadInterpreted !== true) {
    fail(`${label} positive case does not interpret its bounded payload`);
  }
  const mutationIds = mutations.map((mutation) => mutation.id);
  requireUnique(mutationIds, `${label}.mutation ids`);
  for (const mutation of mutations) {
    if (!mutation.id.startsWith(`${caseNamespace}.`)) {
      fail(`${label} mutation ${mutation.id} is not namespaced to ${source.adr}`);
    }
    if (
      mutation.expectedProfileResult === expectedProfileResult &&
      mutation.productionAdmission === productionAdmission &&
      mutation.payloadInterpreted === payloadInterpreted &&
      mutation.expectedDiagnostics.length === expectedDiagnostics.length &&
      mutation.expectedDiagnostics.every(
        (diagnostic, diagnosticIndex) => diagnostic === expectedDiagnostics[diagnosticIndex],
      )
    ) {
      fail(`${label} mutation ${mutation.id} has no observable expected effect`);
    }
  }
  validateExpectationConsistency(
    expectedProfileResult,
    productionAdmission,
    expectedDiagnostics,
    `${label} base expectation`,
  );
  if (
    (polarity === "POSITIVE" && expectedProfileResult === "REJECT") ||
    (polarity === "NEGATIVE" && expectedProfileResult !== "REJECT")
  ) {
    fail(`${label}.polarity disagrees with its base profile result`);
  }
  if (
    (scope === "NON_WIRE_INTERNAL_STATE") !==
    (expectedProfileResult === "MATCH_NON_WIRE_EXCERPT")
  ) {
    fail(`${label}.scope disagrees with its base profile result`);
  }
  return {
    id,
    source,
    scope,
    profile,
    polarity,
    expectedProfileResult,
    productionAdmission,
    boundedFixture,
    expectedDiagnostics,
    payloadInterpreted,
    mutations,
  };
}

function validateCaseSource(
  value: JsonObject,
  caseLabel: string,
  limits: CorpusLimits,
): SourceBinding {
  const label = `${caseLabel}.source`;
  exactKeys(value, SOURCE_KEYS, label);
  const adr = requiredString(value.adr, `${label}.adr`);
  if (!/^ADR-0(?:0[1-9]|1[01])$/.test(adr)) {
    fail(`${label}.adr is not ADR-001 through ADR-011`);
  }
  const jsonFenceOrdinal = positiveInteger(
    value.json_fence_ordinal,
    `${label}.json_fence_ordinal`,
  );
  const fenceByteLength = positiveInteger(
    value.fence_byte_length,
    `${label}.fence_byte_length`,
  );
  if (fenceByteLength > limits.maximumJsonFenceBytes) {
    fail(`${label}.fence_byte_length exceeds its bound`);
  }
  const fenceSha256 = sha256String(value.fence_sha256, `${label}.fence_sha256`);
  return {
    adr,
    jsonFenceOrdinal,
    fenceByteLength,
    fenceSha256,
  };
}

function validateMutation(
  value: JsonValue,
  label: string,
  diagnostics: ReadonlySet<string>,
): CorpusMutation {
  const object = requiredObject(value, label);
  exactKeys(object, MUTATION_KEYS, label);
  const patch = validatePatch(requiredObject(object.patch, `${label}.patch`), `${label}.patch`);
  const expectedProfileResult = enumString(
    object.expected_profile_result,
    PROFILE_RESULTS,
    `${label}.expected_profile_result`,
  );
  if (expectedProfileResult !== "REJECT") {
    fail(`${label} is not an expected fail-closed contrast`);
  }
  const productionAdmission = enumString(
    object.production_admission,
    PRODUCTION_ADMISSIONS,
    `${label}.production_admission`,
  );
  const expectedDiagnostics = diagnosticArray(
    object.expected_diagnostics,
    `${label}.expected_diagnostics`,
    diagnostics,
  );
  validateExpectationConsistency(
    expectedProfileResult,
    productionAdmission,
    expectedDiagnostics,
    label,
  );
  const purpose = requiredString(object.purpose, `${label}.purpose`);
  if (
    purpose.trim().length === 0 ||
    encoder.encode(purpose).byteLength > MAXIMUM_MUTATION_PURPOSE_UTF8_BYTES
  ) {
    fail(`${label}.purpose is blank or exceeds its UTF-8 byte bound`);
  }
  return {
    id: identifier(object.id, `${label}.id`),
    purpose,
    patch,
    expectedProfileResult,
    productionAdmission,
    expectedDiagnostics,
    payloadInterpreted: requiredBoolean(
      object.payload_interpreted,
      `${label}.payload_interpreted`,
    ),
  };
}

function validatePatch(value: JsonObject, label: string): CorpusPatch {
  const operation = enumString(value.op, PATCH_OPERATIONS, `${label}.op`);
  exactKeys(
    value,
    operation === "REMOVE" ? PATCH_WITHOUT_VALUE_KEYS : PATCH_WITH_VALUE_KEYS,
    label,
  );
  const path = requiredString(value.path, `${label}.path`);
  if (
    !path.startsWith("/") ||
    encoder.encode(path).byteLength > MAXIMUM_PATCH_PATH_UTF8_BYTES ||
    /~(?:[^01]|$)/.test(path)
  ) {
    fail(`${label}.path must be a bounded non-root JSON Pointer`);
  }
  const target = enumString(value.target, PATCH_TARGETS, `${label}.target`);
  return operation === "REMOVE"
    ? { target, op: operation, path }
    : { target, op: operation, path, value: value.value as JsonValue };
}

function validateExpectationConsistency(
  result: ProfileResult,
  production: ProductionAdmission,
  diagnostics: readonly string[],
  label: string,
): void {
  if (result === "REJECT" && diagnostics.length === 0) {
    fail(`${label} rejects without a closed diagnostic`);
  }
  if (result !== "REJECT" && diagnostics.length !== 0) {
    fail(`${label} matches while carrying rejection diagnostics`);
  }
  if (production === "NOT_EVALUATED" && result === "REJECT") {
    fail(`${label} marks a rejected profile as NOT_EVALUATED`);
  }
}

function validateCorpusRelationships(
  cases: readonly CorpusCase[],
  limits: CorpusLimits,
  diagnosticRegistry: ReadonlySet<string>,
): void {
  requireUnique(cases.map((entry) => entry.id), "case ids");
  const expectedCaseIds = Object.keys(CLOSED_CASE_IDENTITIES);
  const actualCaseIds = cases.map((entry) => entry.id);
  if (
    actualCaseIds.length !== expectedCaseIds.length ||
    expectedCaseIds.some((identifier) => !actualCaseIds.includes(identifier))
  ) {
    fail("case inventory differs from the closed v1 identities");
  }
  const mutationIds = cases.flatMap((entry) => entry.mutations.map((mutation) => mutation.id));
  requireUnique(mutationIds, "global mutation ids");
  if (mutationIds.length !== limits.expectedMutationCount) {
    fail("v1 corpus mutation count differs from its closed declared total");
  }
  const allIds = [...cases.map((entry) => entry.id), ...mutationIds];
  requireUnique(allIds, "case and mutation ids");
  const usedDiagnostics = new Set(
    cases.flatMap((entry) => [
      ...entry.expectedDiagnostics,
      ...entry.mutations.flatMap((mutation) => mutation.expectedDiagnostics),
    ]),
  );
  if (
    usedDiagnostics.size !== diagnosticRegistry.size ||
    [...diagnosticRegistry].some((diagnostic) => !usedDiagnostics.has(diagnostic))
  ) {
    fail("diagnostic_registry must exactly cover the v1 corpus expectations");
  }
  requireUnique(
    cases.map((entry) => `${entry.source.adr}#${entry.source.jsonFenceOrdinal}`),
    "source fence bindings",
  );
  let previous = "";
  for (const entry of cases) {
    const orderKey = `${entry.source.adr}#${String(entry.source.jsonFenceOrdinal).padStart(8, "0")}`;
    if (orderKey <= previous) fail("cases must be ordered by source path and fence ordinal");
    previous = orderKey;
  }
}

function diagnosticArray(
  value: JsonValue | undefined,
  label: string,
  registry: ReadonlySet<string>,
): readonly string[] {
  const values = stringArray(value, label);
  requireSortedUnique(values, label);
  for (const diagnostic of values) {
    if (!registry.has(diagnostic)) fail(`${label} contains unregistered diagnostic ${diagnostic}`);
  }
  return values;
}

function exactStringArray(
  value: JsonValue | undefined,
  expected: readonly string[],
  label: string,
): void {
  const actual = stringArray(value, label);
  if (actual.length !== expected.length || actual.some((item, index) => item !== expected[index])) {
    fail(`${label} does not equal the required closed value list`);
  }
}

function stringArray(value: JsonValue | undefined, label: string): string[] {
  const array = requiredArray(value, label);
  return array.map((entry, index) => requiredString(entry, `${label}[${index}]`));
}

function enumString<T extends string>(
  value: JsonValue | undefined,
  options: readonly T[],
  label: string,
): T {
  const candidate = requiredString(value, label);
  if (!(options as readonly string[]).includes(candidate)) {
    fail(`${label} is outside its closed value set`);
  }
  return candidate as T;
}

function identifier(value: JsonValue | undefined, label: string): string {
  const candidate = requiredString(value, label);
  if (!IDENTIFIER.test(candidate) || encoder.encode(candidate).byteLength > 160) {
    fail(`${label} is not a bounded lowercase versioned identifier`);
  }
  return candidate;
}

function sha256String(value: JsonValue | undefined, label: string): string {
  const candidate = requiredString(value, label);
  if (!HEX_SHA256.test(candidate)) fail(`${label} is not lowercase SHA-256 hex`);
  return candidate;
}

function exactString(
  object: JsonObject,
  key: string,
  expected: string,
  label: string,
): void {
  if (object[key] !== expected) fail(`${label}.${key} must equal ${JSON.stringify(expected)}`);
}

function exactInteger(
  object: JsonObject,
  key: string,
  expected: number,
  label: string,
): void {
  if (object[key] !== expected) fail(`${label}.${key} must equal ${expected}`);
}

function positiveInteger(value: JsonValue | undefined, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
    fail(`${label} must be a positive safe integer`);
  }
  return value;
}

function requiredBoolean(value: JsonValue | undefined, label: string): boolean {
  if (typeof value !== "boolean") fail(`${label} must be Boolean`);
  return value;
}

function requiredString(value: JsonValue | undefined, label: string): string {
  if (typeof value !== "string" || value.length === 0) fail(`${label} must be a non-empty string`);
  return value;
}

function requiredArray(value: JsonValue | undefined, label: string): JsonValue[] {
  if (!Array.isArray(value)) fail(`${label} must be an array`);
  return value;
}

function requiredObject(value: JsonValue | undefined, label: string): JsonObject {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be an object`);
  }
  return value;
}

function exactKeys(object: JsonObject, keys: readonly string[], label: string): void {
  const actual = Object.keys(object).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(`${label} has an unknown or missing member`);
  }
}

function requireUnique(values: readonly string[], label: string): void {
  if (new Set(values).size !== values.length) fail(`${label} must be unique`);
}

function requireSortedUnique(values: readonly string[], label: string): void {
  requireUnique(values, label);
  const sorted = [...values].sort();
  if (values.some((value, index) => value !== sorted[index])) {
    fail(`${label} must be lexicographically sorted`);
  }
}

function fail(message: string): never {
  throw new CorpusError(message);
}
