import type { ProductionAdmission, ProfileResult } from "./corpus.ts";
import {
  strictJsonParse,
  StrictJsonError,
  type JsonLimits,
  type JsonValue,
} from "./strict-json.ts";

export interface SemanticInput {
  readonly sourcePath: string;
  readonly ordinal: number;
  readonly profile: string;
  readonly document: JsonValue;
  readonly fixture: JsonValue;
}

export interface SemanticResult {
  readonly result: ProfileResult;
  readonly productionAdmission: ProductionAdmission;
  readonly diagnostics: readonly string[];
  readonly payloadInterpreted: boolean;
}

type JsonObject = { [key: string]: JsonValue };

const SHA256_PREFIXED = /^sha256:[0-9a-f]{64}$/;
const HEX_256 = /^[0-9a-f]{64}$/;
const PROFILE_BY_SOURCE: Readonly<Record<string, string>> = Object.freeze({
  "docs/adr/0001-separate-simulation-and-plant-sessions.md#1":
    "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
  "docs/adr/0001-separate-simulation-and-plant-sessions.md#2":
    "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
  "docs/adr/0002-contract-identity-and-release-authorization.md#1":
    "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
  "docs/adr/0002-contract-identity-and-release-authorization.md#2":
    "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1",
  "docs/adr/0003-authenticated-production-ingress.md#1":
    "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
  "docs/adr/0003-authenticated-production-ingress.md#2":
    "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1",
  "docs/adr/0003-authenticated-production-ingress.md#3":
    "ADR003_FLATTENED_FORWARDING_WRAPPER_V1",
  "docs/adr/0004-observer-attach-grants-and-revocation.md#1":
    "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
  "docs/adr/0004-observer-attach-grants-and-revocation.md#2":
    "ADR004_SENSOR_PROJECTION_ANTI_LAUNDERING_V1",
  "docs/adr/0005-declared-stream-lifecycle.md#1":
    "ADR005_DECLARE_STREAM_EXCERPT_V1",
  "docs/adr/0005-declared-stream-lifecycle.md#2":
    "ADR005_UNDECLARED_FRAME_V1",
  "docs/adr/0005-declared-stream-lifecycle.md#3":
    "ADR005_SENSOR_AVAILABILITY_SOURCE_BOUND_V1",
  "docs/adr/0005-declared-stream-lifecycle.md#4":
    "ADR005_SENSOR_AVAILABILITY_DETACHED_MASK_V1",
  "docs/adr/0006-body-issued-authority-and-time.md#1":
    "ADR006_BODY_LEASE_EXCERPT_V1",
  "docs/adr/0006-body-issued-authority-and-time.md#2":
    "ADR006_STALE_SELF_ISSUED_LEASE_V1",
  "docs/adr/0007-command-disposition-journal.md#1":
    "ADR007_DISPOSITION_QUERY_PROJECTION_V1",
  "docs/adr/0007-command-disposition-journal.md#2":
    "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1",
  "docs/adr/0007-command-disposition-journal.md#3":
    "ADR007_INVALID_DISPOSITION_V1",
  "docs/adr/0007-command-disposition-journal.md#4":
    "ADR007_UNAVAILABLE_SOURCE_RESTRICTIVE_ACTION_V1",
  "docs/adr/0008-extension-namespace-and-galadriel-separation.md#1":
    "ADR008_EXTENSION_ENVELOPE_PROJECTION_V1",
  "docs/adr/0008-extension-namespace-and-galadriel-separation.md#2":
    "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1",
  "docs/adr/0008-extension-namespace-and-galadriel-separation.md#3":
    "ADR008_GALADRIEL_POLICY_INJECTION_V1",
  "docs/adr/0008-extension-namespace-and-galadriel-separation.md#4":
    "ADR008_SENSOR_CONDITION_DETAIL_V1",
  "docs/adr/0009-security-state-rotation-and-revocation.md#1":
    "ADR009_SECURITY_STATE_PROJECTION_V1",
  "docs/adr/0009-security-state-rotation-and-revocation.md#2":
    "ADR009_INVALID_SECURITY_STATE_V1",
  "docs/adr/0010-plane-qos-retention-and-overload.md#1":
    "ADR010_ACTION_QOS_PROFILE_V1",
  "docs/adr/0010-plane-qos-retention-and-overload.md#2":
    "ADR010_INVALID_ACTION_QOS_PROFILE_V1",
  "docs/adr/0010-plane-qos-retention-and-overload.md#3":
    "ADR010_PERCEPTION_QUEUE_MISSINGNESS_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#1":
    "ADR011_REGISTERED_HALDIR_INTENT_ENVELOPE_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#2":
    "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#3":
    "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#4":
    "ADR011_PREPARED_FRAME_PUBLISHER_BOUNDARY_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#5":
    "ADR011_X02_FLEET_AVAILABILITY_LAYOUT_V1",
});

const HEADER_LIMITS: JsonLimits = Object.freeze({
  maxBytes: 4_096,
  maxDepth: 8,
  maxNodes: 128,
  maxMembers: 64,
  maxArrayItems: 64,
  maxKeyBytes: 128,
  maxStringBytes: 1_024,
  maxTotalStringBytes: 4_096,
  maxIntegerCharacters: 16,
});

export class SemanticConfigurationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SemanticConfigurationError";
  }
}

export function evaluateSemantics(input: SemanticInput): SemanticResult {
  const sourceKey = `${input.sourcePath}#${input.ordinal}`;
  const requiredProfile = PROFILE_BY_SOURCE[sourceKey];
  if (requiredProfile === undefined) {
    throw new SemanticConfigurationError(`unknown source fence ${sourceKey}`);
  }
  if (input.profile !== requiredProfile) {
    throw new SemanticConfigurationError(
      `profile ${input.profile} does not bind source fence ${sourceKey}`,
    );
  }
  const document = requiredObject(input.document, "document");
  validateFixture(input.profile, input.fixture);

  const diagnostics: string[] = [];
  let payloadInterpreted = true;
  let matchingResult: Exclude<ProfileResult, "REJECT"> =
    "MATCH_NON_AUTHORIZING_EXCERPT";
  switch (input.profile) {
    case "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1":
      adr001(document, input.fixture, diagnostics);
      break;
    case "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1":
      adr002(document, input.fixture, diagnostics);
      break;
    case "ADR003_FLATTENED_FORWARDING_WRAPPER_V1":
      adr003Wrapper(document, input.fixture, diagnostics);
      payloadInterpreted = false;
      break;
    case "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1":
      adr003Header(document, input.fixture, diagnostics);
      break;
    case "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1":
      adr004(document, input.fixture, diagnostics);
      matchingResult = "MATCH_NON_WIRE_EXCERPT";
      break;
    case "ADR004_SENSOR_PROJECTION_ANTI_LAUNDERING_V1":
      adr004SensorProjection(document, diagnostics);
      break;
    case "ADR005_DECLARE_STREAM_EXCERPT_V1":
      adr005Declaration(document, input.fixture, diagnostics);
      break;
    case "ADR005_UNDECLARED_FRAME_V1":
      adr005Undeclared(document, input.fixture, diagnostics);
      break;
    case "ADR005_SENSOR_AVAILABILITY_SOURCE_BOUND_V1":
      adr005SensorAvailability(document, diagnostics);
      break;
    case "ADR005_SENSOR_AVAILABILITY_DETACHED_MASK_V1":
      adr005DetachedAvailability(document, diagnostics);
      break;
    case "ADR006_BODY_LEASE_EXCERPT_V1":
    case "ADR006_STALE_SELF_ISSUED_LEASE_V1":
      adr006(document, input.fixture, diagnostics);
      break;
    case "ADR007_DISPOSITION_QUERY_PROJECTION_V1":
      adr007Query(document, diagnostics);
      break;
    case "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1":
    case "ADR007_INVALID_DISPOSITION_V1":
      adr007(document, input.fixture, diagnostics);
      break;
    case "ADR007_UNAVAILABLE_SOURCE_RESTRICTIVE_ACTION_V1":
      adr007UnavailableSource(document, diagnostics);
      break;
    case "ADR008_EXTENSION_ENVELOPE_PROJECTION_V1":
      adr008ExtensionEnvelope(document, diagnostics);
      break;
    case "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1":
      adr008Assessment(document, input.fixture, diagnostics);
      break;
    case "ADR008_GALADRIEL_POLICY_INJECTION_V1":
      adr008Policy(document, input.fixture, diagnostics);
      break;
    case "ADR008_SENSOR_CONDITION_DETAIL_V1":
      adr008SensorConditionDetail(document, diagnostics);
      break;
    case "ADR009_SECURITY_STATE_PROJECTION_V1":
      adr009Projection(document, input.fixture, diagnostics);
      break;
    case "ADR009_INVALID_SECURITY_STATE_V1":
      adr009Invalid(document, input.fixture, diagnostics);
      break;
    case "ADR010_ACTION_QOS_PROFILE_V1":
      adr010Action(document, input.fixture, diagnostics);
      break;
    case "ADR010_INVALID_ACTION_QOS_PROFILE_V1":
      adr010Invalid(document, input.fixture, diagnostics);
      break;
    case "ADR010_PERCEPTION_QUEUE_MISSINGNESS_V1":
      adr010PerceptionQueueMissingness(document, diagnostics);
      break;
    case "ADR011_REGISTERED_HALDIR_INTENT_ENVELOPE_V1":
      adr011RegisteredIntent(document, input.fixture, diagnostics);
      break;
    case "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1":
      adr011Command(document, input.fixture, diagnostics);
      break;
    case "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1":
      adr011EffectPathFencing(document, diagnostics);
      break;
    case "ADR011_PREPARED_FRAME_PUBLISHER_BOUNDARY_V1":
      adr011PreparedPublisher(document, diagnostics);
      break;
    case "ADR011_X02_FLEET_AVAILABILITY_LAYOUT_V1":
      adr011X02FleetAvailability(document, diagnostics);
      break;
    default:
      throw new SemanticConfigurationError(`unknown profile ${input.profile}`);
  }

  const closedDiagnostics = [...new Set(diagnostics)].sort();
  const result = closedDiagnostics.length === 0 ? matchingResult : "REJECT";
  const productionAdmission =
    input.profile === "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1"
      ? "NOT_APPLICABLE"
      : result === "REJECT" ||
          input.profile === "ADR011_REGISTERED_HALDIR_INTENT_ENVELOPE_V1"
        ? "REJECT"
        : "NOT_EVALUATED";
  return {
    result,
    productionAdmission,
    diagnostics: closedDiagnostics,
    payloadInterpreted,
  };
}

function adr001(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const actualMajor = stableWireMajor(document.ncp_version);
  const expectedMajor = stableWireMajor(fixtureString(fixture, "expected_ncp_version"));
  if (actualMajor === undefined || expectedMajor === undefined || actualMajor !== expectedMajor) {
    diagnostics.push("NCP_VERSION_MISMATCH");
  }
  if (document.kind !== fixtureString(fixture, "expected_session_kind")) {
    diagnostics.push("SESSION_KIND_MISMATCH");
  }
  const commander = asObject(document.commander_identity);
  if (
    commander?.principal_id !==
    fixtureString(fixture, "expected_commander_principal_id")
  ) {
    diagnostics.push("COMMANDER_PRINCIPAL_MISMATCH");
  }
  if (Object.hasOwn(document, "network") || Object.hasOwn(document, "sim")) {
    diagnostics.push("PLANT_CONTAINS_SIMULATION_ONLY_MEMBER");
  }
  if (!isPrefixedDigest(document.plant_profile_digest)) {
    diagnostics.push("PLANT_PROFILE_MISSING");
  }
  if (!isPrefixedDigest(document.security_state_digest)) {
    diagnostics.push("PLANT_SECURITY_CONTEXT_MISSING");
  }
}

function adr002(document: JsonObject, fixture: JsonValue, diagnostics: string[]): void {
  if (stableWireMajor(document.wire_version) !== 1n) {
    diagnostics.push("WIRE_VERSION_MISMATCH");
  }
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm)) {
    diagnostics.push("AUTHORITY_REALM_KEY_MISSING");
  } else if (!objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_KEY_MISMATCH");
  }
  const expectedDigest = fixtureString(fixture, "expected_stable_core_digest");
  let stableCoreMatches = false;
  if (document.stable_core_digest === undefined || document.stable_core_digest === null) {
    diagnostics.push("STABLE_CORE_DIGEST_MISSING_OR_NULL");
  } else if (!isPrefixedDigest(document.stable_core_digest)) {
    diagnostics.push("STABLE_CORE_DIGEST_INVALID");
  } else if (document.stable_core_digest !== expectedDigest) {
    diagnostics.push("STABLE_CORE_DIGEST_MISMATCH");
  } else {
    stableCoreMatches = true;
  }
  if (Object.hasOwn(document, "contract_hash") && !stableCoreMatches) {
    diagnostics.push("COMPACT_HASH_NOT_COMPATIBILITY_IDENTITY");
  }
}

function stableWireMajor(value: JsonValue | undefined): bigint | undefined {
  if (typeof value !== "string") return undefined;
  const parts = value.split(".");
  if (parts.length < 1 || parts.length > 2) return undefined;
  const canonical = /^(?:0|[1-9][0-9]*)$/;
  if (!parts.every((part) => part.length <= 20 && canonical.test(part))) return undefined;
  const majorPart = parts[0];
  const minorPart = parts[1];
  if (majorPart === undefined) return undefined;
  try {
    const major = BigInt(majorPart);
    const minor = minorPart === undefined ? 0n : BigInt(minorPart);
    const maximum = 18_446_744_073_709_551_615n;
    if (major === 0n || major > maximum || minor > maximum) return undefined;
    return major;
  } catch {
    return undefined;
  }
}

function adr003Wrapper(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const requiredAlgorithm = fixtureString(fixture, "required_algorithm");
  const protectedValue = nonemptyString(document.protected);
  let protectedHeader: JsonObject | undefined;
  if (protectedValue !== undefined) {
    try {
      protectedHeader = asObject(
        strictJsonParse(decodeBase64Url(protectedValue, HEADER_LIMITS.maxBytes), HEADER_LIMITS),
      );
    } catch (error) {
      if (!(error instanceof StrictJsonError) && !(error instanceof Base64UrlError)) throw error;
    }
  }
  if (protectedHeader === undefined) {
    diagnostics.push("PROTECTED_HEADER_NOT_JSON");
  } else {
    validateAlgorithm(protectedHeader.alg, requiredAlgorithm, diagnostics);
    const realm = asObject(protectedHeader.authority_realm_key);
    if (!isRealmKey(realm)) {
      diagnostics.push("AUTHORITY_REALM_KEY_MISSING");
    } else if (!objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
      diagnostics.push("AUTHORITY_REALM_KEY_MISMATCH");
    }
    if (Object.hasOwn(protectedHeader, "jku")) diagnostics.push("REMOTE_JKU_FORBIDDEN");
  }

  const unprotected = document.header;
  if (unprotected !== undefined) {
    diagnostics.push("UNPROTECTED_HEADER_FORBIDDEN");
    if (Object.hasOwn(asObject(unprotected) ?? Object.create(null), "jku")) {
      diagnostics.push("REMOTE_JKU_FORBIDDEN");
    }
  }

  const expectedSignatureBytes = fixtureInteger(fixture, "expected_signature_bytes");
  let signatureLength: number | undefined;
  if (typeof document.signature === "string") {
    try {
      signatureLength = decodeBase64Url(document.signature, expectedSignatureBytes).byteLength;
    } catch (error) {
      if (!(error instanceof Base64UrlError)) throw error;
    }
  }
  if (signatureLength !== expectedSignatureBytes) {
    diagnostics.push("SIGNATURE_LENGTH_INVALID");
  } else if (!fixtureBoolean(fixture, "signature_verifies")) {
    diagnostics.push("SIGNATURE_NOT_VALID");
  }
}

function adr003Header(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const requiredAlgorithm = fixtureString(fixture, "required_algorithm");
  validateAlgorithm(document.alg, requiredAlgorithm, diagnostics);
  if (Object.hasOwn(document, "jku")) diagnostics.push("REMOTE_JKU_FORBIDDEN");
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm)) {
    diagnostics.push("AUTHORITY_REALM_KEY_MISSING");
  } else if (!objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_KEY_MISMATCH");
  }
  if (document.route !== fixtureString(fixture, "expected_route")) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  }
  if (document.audience !== fixtureString(fixture, "expected_audience")) {
    diagnostics.push("PROTECTED_HEADER_AUDIENCE_MISMATCH");
  }
}

function adr004(document: JsonObject, fixture: JsonValue, diagnostics: string[]): void {
  const allocation = document.allocates_output_slot;
  if (typeof allocation !== "boolean") {
    diagnostics.push("OUTPUT_ALLOCATION_FLAG_INVALID");
  } else if (allocation !== fixtureBoolean(fixture, "output_allocation_permitted")) {
    diagnostics.push("PENDING_STATE_ALLOCATES_OUTPUT");
  }
  if (document.state !== fixtureString(fixture, "expected_state")) {
    diagnostics.push("PENDING_STATE_INVALID");
  }
}

function adr004SensorProjection(document: JsonObject, diagnostics: string[]): void {
  const requirements = [
    ["availability_projection_is_tighten_only", true, "SENSOR_PROJECTION_TIGHTEN_ONLY_REQUIRED"],
    ["optional_detail_can_override_availability", false, "SENSOR_CONDITION_DETAIL_AUTHORITY_FORBIDDEN"],
    ["portable_origin_identity_preserved", true, "SENSOR_PROJECTION_ORIGIN_IDENTITY_REQUIRED"],
    ["projected_available_requires_origin_available_inputs", true, "SENSOR_PROJECTION_AVAILABLE_INPUT_REQUIRED"],
    ["projection_binds_origin_and_projected_availability", true, "SENSOR_PROJECTION_AVAILABILITY_BINDING_REQUIRED"],
    ["slot_removal_or_reorder_requires_new_layout_and_bitmap", true, "SENSOR_PROJECTION_LAYOUT_REBIND_REQUIRED"],
    ["source_unavailable_can_project_available", false, "SENSOR_PROJECTION_UNAVAILABLE_UPGRADE_FORBIDDEN"],
    ["unavailable_placeholder_can_be_observation", false, "SENSOR_PROJECTION_PLACEHOLDER_LAUNDERING_FORBIDDEN"],
  ] as const;
  requireExactProjectionMembers(
    document,
    requirements.map(([field]) => field),
    "SENSOR_PROJECTION_ANTI_LAUNDERING_INVALID",
    diagnostics,
  );
  for (const [field, expected, diagnostic] of requirements) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
}

function adr005Declaration(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  if (stableWireMajor(document.ncp_version) !== 1n) diagnostics.push("NCP_VERSION_MISMATCH");
  if (document.kind !== "declare_stream") diagnostics.push("MESSAGE_KIND_MISMATCH");
  const realm = asObject(document.authority_realm_key);
  const expected = fixtureObject(fixture, "authenticated_realm_key");
  if (
    !isRealmKey(realm) ||
    !objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS) ||
    document.route !== fixtureString(fixture, "expected_route")
  ) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  }
  if (document.sequence_start !== 1) {
    diagnostics.push("STREAM_SEQUENCE_START_INVALID");
  }
  if (
    document.publisher_principal_id !==
    fixtureString(fixture, "authenticated_publisher_principal_id")
  ) {
    diagnostics.push("PUBLISHER_PRINCIPAL_MISMATCH");
  }
  const epoch = nonemptyString(document.stream_epoch);
  if (epoch === undefined) {
    diagnostics.push("STREAM_EPOCH_REQUIRED");
  } else if (fixtureStringArray(fixture, "live_declaration_epoch_ids").includes(epoch)) {
    diagnostics.push("STREAM_EPOCH_ALREADY_LIVE");
  }
}

function adr005Undeclared(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const realm = asObject(document.authority_realm_key);
  const expected = fixtureObject(fixture, "authenticated_realm_key");
  if (!isRealmKey(realm) || !objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS)) {
    diagnostics.push("REALM_REQUIRED");
  }
  const stream = asObject(document.stream);
  const epoch = stream === undefined ? undefined : nonemptyString(stream.epoch);
  const liveEpochs = fixtureStringArray(fixture, "live_declaration_epoch_ids");
  if (epoch === undefined || !liveEpochs.includes(epoch)) {
    diagnostics.push("STREAM_DECLARATION_NOT_LIVE");
  }
}

function adr005SensorAvailability(document: JsonObject, diagnostics: string[]): void {
  const requirements = [
    ["availability_bitmap_mandatory", true, "SENSOR_AVAILABILITY_BITMAP_REQUIRED"],
    ["availability_covered_by_frame_digest", true, "SENSOR_AVAILABILITY_DIGEST_BINDING_REQUIRED"],
    ["group_decision_exactly_once", true, "SENSOR_AVAILABILITY_GROUP_DECISION_REQUIRED"],
    ["available_group_requires_all_values", true, "SENSOR_AVAILABLE_GROUP_COMPLETENESS_REQUIRED"],
    ["unavailable_group_forbids_caller_values", true, "SENSOR_UNAVAILABLE_GROUP_VALUE_FORBIDDEN"],
    ["unavailable_placeholder_is_internal", true, "SENSOR_UNAVAILABLE_PLACEHOLDER_INTERNAL_REQUIRED"],
    ["decoder_exposes_placeholder_values", false, "SENSOR_UNAVAILABLE_PLACEHOLDER_EXPOSURE_FORBIDDEN"],
    ["position_assigned_after_completeness", true, "SENSOR_AVAILABILITY_POSITION_ORDER_REQUIRED"],
    ["post_assignment_failure_emits_gap", true, "SENSOR_POST_ASSIGNMENT_FAILURE_GAP_REQUIRED"],
    ["receiver_rejection_unassigns_producer_position", false, "SENSOR_RECEIVER_REJECTION_POSITION_ROLLBACK_FORBIDDEN"],
    ["live_source_pin_is_evictable", false, "SENSOR_LIVE_SOURCE_PIN_EVICTION_FORBIDDEN"],
    ["live_source_pin_capacity_pre_reserved", true, "SENSOR_SOURCE_PIN_CAPACITY_RESERVATION_REQUIRED"],
    ["pin_retained_until_terminal_disposition_or_evidence_handoff", true, "SENSOR_SOURCE_PIN_RETENTION_REQUIRED"],
    ["restart_restores_pin_or_retires_generation", true, "SENSOR_SOURCE_PIN_RESTART_CLOSURE_REQUIRED"],
    ["compatibility_json_infers_availability_from_zero_or_absence", false, "SENSOR_COMPATIBILITY_AVAILABILITY_INFERENCE_FORBIDDEN"],
    ["compatibility_json_preserves_semantic_availability", true, "SENSOR_COMPATIBILITY_AVAILABILITY_PRESERVATION_REQUIRED"],
    ["source_reference_repeats_bitmap", false, "SENSOR_AVAILABILITY_SOURCE_DUPLICATION_FORBIDDEN"],
  ] as const;
  requireExactProjectionMembers(
    document,
    requirements.map(([field]) => field),
    "SENSOR_AVAILABILITY_PROJECTION_INVALID",
    diagnostics,
  );
  for (const [field, expected, diagnostic] of requirements) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
}

function adr005DetachedAvailability(document: JsonObject, diagnostics: string[]): void {
  requireExactProjectionMembers(
    document,
    ["availability_transport", "availability_covered_by_frame_digest"],
    "SENSOR_AVAILABILITY_DETACHED_FORBIDDEN",
    diagnostics,
  );
  requireProjectionLiteral(
    document,
    "availability_transport",
    "INLINE_STABLE_CORE_SENSOR_FRAME",
    "SENSOR_AVAILABILITY_DETACHED_FORBIDDEN",
    diagnostics,
  );
  requireProjectionBoolean(
    document,
    "availability_covered_by_frame_digest",
    true,
    "SENSOR_AVAILABILITY_DIGEST_BINDING_REQUIRED",
    diagnostics,
  );
}

function adr006(document: JsonObject, fixture: JsonValue, diagnostics: string[]): void {
  if (document.issuer_principal_id !== fixtureString(fixture, "enrolled_body_principal_id")) {
    diagnostics.push("LEASE_ISSUER_NOT_BODY");
  }
  const current = fixtureObject(fixture, "current_lease");
  const currentFields = [
    "session_generation",
    "term",
    "lease_id",
    "holder_principal_id",
    "holder_entity_id",
  ] as const;
  const evaluation = fixtureInteger(fixture, "evaluation_utc_ms");
  const issued = safeInteger(document.issued_at_utc_ms);
  const expires = safeInteger(document.expires_at_utc_ms);
  if (
    !objectsEqualOn(document, current, currentFields) ||
    issued === undefined ||
    expires === undefined ||
    issued < 0 ||
    expires < 0 ||
    issued > evaluation ||
    evaluation >= expires
  ) {
    diagnostics.push("LEASE_NOT_CURRENT");
  }
}

function adr007Query(document: JsonObject, diagnostics: string[]): void {
  requireExactProjectionMembers(
    document,
    [
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
  requireProjectionBoolean(document, "query_coordinate_bound", true, "DISPOSITION_QUERY_COORDINATE_INVALID", diagnostics);
  requireProjectionBoolean(document, "result_projection_omits_authentication", true, "DISPOSITION_RESULT_PROJECTION_INVALID", diagnostics);
  requireProjectionBoolean(document, "retained_requires_complete_chain", true, "DISPOSITION_RETAINED_CHAIN_REQUIRED", diagnostics);
  requireProjectionBoolean(document, "retired_proves_effect", false, "DISPOSITION_RETIRED_EFFECT_FORBIDDEN", diagnostics);
  if (document.early_effect_mode !== "ESTOP_ONLY") {
    diagnostics.push("FAIL_SAFE_EARLY_EFFECT_MODE_INVALID");
  }
  requireProjectionBoolean(document, "estop_reservation_rechecks_currentness", true, "ESTOP_RESERVATION_CURRENTNESS_RECHECK_REQUIRED", diagnostics);
  requireProjectionBoolean(document, "effect_boundary_rechecks_currentness", true, "FAIL_SAFE_EFFECT_BOUNDARY_RECHECK_REQUIRED", diagnostics);
  requireProjectionBoolean(document, "hold_admission_precedes_effect", true, "HOLD_ADMISSION_ORDER_INVALID", diagnostics);
  requireProjectionBoolean(document, "rejected_candidate_cannot_select_local_hold", true, "REJECTED_CANDIDATE_LOCAL_HOLD_FORBIDDEN", diagnostics);
  if (document.post_effect_admission_mode !== "ESTOP_ONLY") {
    diagnostics.push("POST_EFFECT_ADMISSION_MODE_INVALID");
  }
  const expected = [
    "QUERY_FAILURE",
    "RETAINED_DISPOSITION",
    "RETIRED_DISPOSITION_COMMITMENT",
  ];
  const branches = asArray(document.branches);
  if (
    branches === undefined ||
    branches.length !== expected.length ||
    branches.some((branch, index) => branch !== expected[index])
  ) {
    diagnostics.push("DISPOSITION_RESULT_BRANCHES_INVALID");
  }
}

function adr007(document: JsonObject, fixture: JsonValue, diagnostics: string[]): void {
  if (document.kind !== "command_disposition") {
    diagnostics.push("MESSAGE_KIND_MISMATCH");
  }
  const nonterminal = fixtureStringArray(fixture, "nonterminal_states");
  const terminal = fixtureStringArray(fixture, "terminal_states");
  const state = nonemptyString(document.state);
  if (state === undefined || (!nonterminal.includes(state) && !terminal.includes(state))) {
    diagnostics.push("DISPOSITION_STATE_UNKNOWN");
    if (Object.hasOwn(document, "terminal")) {
      diagnostics.push("DISPOSITION_TERMINALITY_INVALID");
    }
    return;
  }
  if (
    Object.hasOwn(document, "terminal") &&
    (typeof document.terminal !== "boolean" || document.terminal !== terminal.includes(state))
  ) {
    diagnostics.push("DISPOSITION_TERMINALITY_INVALID");
  }
}

function adr007UnavailableSource(document: JsonObject, diagnostics: string[]): void {
  requireExactProjectionMembers(
    document,
    [
      "source_pin_retains_availability",
      "unavailable_group_requires_installed_restrictive_lane",
      "group_dependency_map_is_layout_bound",
      "conflicting_dependency_overlap_rejects_preparation",
      "restrictive_action_is_universal_zero",
      "complete_command_rejects_on_lane_mismatch",
      "correctly_restricted_active_disposition",
      "optional_detail_can_authorize",
    ],
    "SOURCE_RESTRICTIVE_PROJECTION_INVALID",
    diagnostics,
  );
  for (const [field, expected, diagnostic] of [
    ["source_pin_retains_availability", true, "SOURCE_PIN_AVAILABILITY_REQUIRED"],
    ["unavailable_group_requires_installed_restrictive_lane", true, "SOURCE_RESTRICTIVE_ACTION_REQUIRED"],
    ["group_dependency_map_is_layout_bound", true, "SOURCE_GROUP_DEPENDENCY_LAYOUT_BINDING_REQUIRED"],
    ["conflicting_dependency_overlap_rejects_preparation", true, "SOURCE_DEPENDENCY_OVERLAP_PREPARATION_REJECTION_REQUIRED"],
    ["restrictive_action_is_universal_zero", false, "SOURCE_RESTRICTIVE_ACTION_UNIVERSAL_ZERO_FORBIDDEN"],
    ["complete_command_rejects_on_lane_mismatch", true, "SOURCE_RESTRICTIVE_COMMAND_ATOMIC_REJECT_REQUIRED"],
    ["optional_detail_can_authorize", false, "SENSOR_CONDITION_DETAIL_AUTHORITY_FORBIDDEN"],
  ] as const) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
  requireProjectionLiteral(
    document,
    "correctly_restricted_active_disposition",
    "APPLIED",
    "SOURCE_RESTRICTED_ACTIVE_DISPOSITION_INVALID",
    diagnostics,
  );
}

function adr008ExtensionEnvelope(document: JsonObject, diagnostics: string[]): void {
  requireExactProjectionMembers(
    document,
    [
      "activation_context_binds_clock_and_expiry",
      "ambient_fetch_credentials_allowed",
      "attachment_redirect_allowed",
      "attachment_ref_grants_fetch_authority",
      "attachment_store_enrollment_required",
      "callback_after_complete_validation",
      "callback_boundary_state_before_entry",
      "callback_right_consumed_with_final_recheck",
      "core_or_registered_extension_required",
      "duplicate_decoded_keys_reject",
      "extension_manifest_selected_before_decode",
      "external_attachment_refs_bounded",
      "generic_chunk_protocol_in_v1",
      "inline_attachment_bytes_allowed",
      "length_and_digest_before_semantic_use",
      "noncanonical_numbers_reject",
      "one_semantic_envelope_per_message",
      "partial_attachment_is_usable",
      "post_fetch_currentness_recheck_required",
      "receiver_activation_incarnation_bound",
      "reserve_before_fetch",
      "retired_context_discloses_result",
      "semantic_encoding",
      "svg_is_protocol_input",
      "terminal_lookup_precedes_work_admission",
      "terminal_tombstone_required",
      "unknown_members_reject",
      "wire_supplied_url_allowed",
    ],
    "EXTENSION_ONE_ENVELOPE_REQUIRED",
    diagnostics,
  );
  if (document.semantic_encoding !== "BOUNDED_CANONICAL_JSON") {
    diagnostics.push("EXTENSION_SEMANTIC_ENCODING_INVALID");
  }
  for (const [field, expected, diagnostic] of [
    ["one_semantic_envelope_per_message", true, "EXTENSION_ONE_ENVELOPE_REQUIRED"],
    ["extension_manifest_selected_before_decode", true, "EXTENSION_MANIFEST_SELECTION_REQUIRED"],
    ["unknown_members_reject", true, "EXTENSION_UNKNOWN_MEMBER_POLICY_INVALID"],
    ["duplicate_decoded_keys_reject", true, "EXTENSION_DUPLICATE_KEY_POLICY_INVALID"],
    ["noncanonical_numbers_reject", true, "EXTENSION_CANONICAL_NUMBER_POLICY_INVALID"],
    ["inline_attachment_bytes_allowed", false, "EXTENSION_INLINE_ATTACHMENT_FORBIDDEN"],
    ["external_attachment_refs_bounded", true, "EXTENSION_ATTACHMENT_REFERENCE_BOUNDS_REQUIRED"],
    ["attachment_store_enrollment_required", true, "EXTENSION_ATTACHMENT_STORE_ENROLLMENT_REQUIRED"],
    ["wire_supplied_url_allowed", false, "EXTENSION_WIRE_URL_FORBIDDEN"],
    ["ambient_fetch_credentials_allowed", false, "EXTENSION_AMBIENT_FETCH_CREDENTIAL_FORBIDDEN"],
    ["attachment_redirect_allowed", false, "EXTENSION_ATTACHMENT_REDIRECT_FORBIDDEN"],
    ["attachment_ref_grants_fetch_authority", false, "EXTENSION_ATTACHMENT_FETCH_AUTHORITY_INVALID"],
    ["reserve_before_fetch", true, "EXTENSION_RESERVATION_ORDER_INVALID"],
    ["length_and_digest_before_semantic_use", true, "EXTENSION_ATTACHMENT_VERIFICATION_REQUIRED"],
    ["partial_attachment_is_usable", false, "EXTENSION_PARTIAL_ATTACHMENT_USE_FORBIDDEN"],
    ["post_fetch_currentness_recheck_required", true, "EXTENSION_POST_FETCH_CURRENTNESS_RECHECK_REQUIRED"],
    ["callback_right_consumed_with_final_recheck", true, "EXTENSION_CALLBACK_RIGHT_CONSUMPTION_REQUIRED"],
    ["callback_after_complete_validation", true, "EXTENSION_CALLBACK_VALIDATION_ORDER_INVALID"],
    ["callback_boundary_state_before_entry", true, "EXTENSION_CALLBACK_BOUNDARY_STATE_REQUIRED"],
    ["core_or_registered_extension_required", true, "EXTENSION_CORE_OR_REGISTERED_REQUIRED"],
    ["svg_is_protocol_input", false, "EXTENSION_SVG_PROTOCOL_INPUT_FORBIDDEN"],
    ["generic_chunk_protocol_in_v1", false, "EXTENSION_GENERIC_CHUNK_PROTOCOL_FORBIDDEN"],
    ["receiver_activation_incarnation_bound", true, "EXTENSION_RECEIVER_ACTIVATION_INCARNATION_REQUIRED"],
    ["activation_context_binds_clock_and_expiry", true, "EXTENSION_ACTIVATION_TIME_BINDING_REQUIRED"],
    ["terminal_lookup_precedes_work_admission", true, "EXTENSION_TERMINAL_LOOKUP_ORDER_INVALID"],
    ["retired_context_discloses_result", false, "EXTENSION_RETIRED_RESULT_DISCLOSURE_FORBIDDEN"],
    ["terminal_tombstone_required", true, "EXTENSION_TERMINAL_TOMBSTONE_REQUIRED"],
  ] as const) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
}

function adr008Assessment(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  if (document.extension_id !== "org.sepahead.galadriel.assessment") {
    diagnostics.push("EXTENSION_ID_MISMATCH");
  }
  if (document.schema_version !== "1") {
    diagnostics.push("EXTENSION_SCHEMA_VERSION_MISMATCH");
  }
  const realm = asObject(document.authority_realm_key);
  const expected = fixtureObject(fixture, "authenticated_realm_key");
  if (
    !isRealmKey(realm) ||
    !objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS) ||
    document.route !== fixtureString(fixture, "expected_route")
  ) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  }
  if (document.producer_principal_id !== fixtureString(fixture, "extension_assessor_principal_id")) {
    diagnostics.push("EXTENSION_PRODUCER_ROLE_INVALID");
  }
  if (
    document.audience_principal_id !==
    fixtureString(fixture, "extension_receiver_principal_id")
  ) {
    diagnostics.push("EXTENSION_RECEIVER_ROLE_INVALID");
  }
  validateTypedDigest(document.release_suite_identity, "galadriel-release-suite-v1", diagnostics);
  for (const key of [
    "manifest_digest",
    "extension_schema_digest",
    "model_digest",
    "configuration_digest",
    "evidence_schema_digest",
  ]) {
    if (!isPrefixedDigest(document[key])) diagnostics.push("DIGEST_ENCODING_INVALID");
  }
  const lifecycle = asObject(document.lifecycle_outcome_evidence);
  const assessments = lifecycle === undefined ? undefined : asArray(lifecycle.assessments);
  if (assessments === undefined || assessments.length === 0) {
    diagnostics.push("ASSESSMENT_MAGNITUDE_REQUIRED");
  } else {
    for (const assessmentValue of assessments) {
      const assessment = asObject(assessmentValue);
      validateTypedDigest(
        assessment?.assessment_binding_identity,
        "galadriel-assessment-binding-v2",
        diagnostics,
      );
      const report = asObject(assessment?.report_evidence);
      const verdict = report === undefined ? undefined : asObject(report.verdict);
      if (
        assessment?.kind !== "EVALUATED_DEFAULT_REPORT" ||
        verdict?.verdict !== "attributed_inconsistency" ||
        nonemptyString(verdict.magnitude) === undefined
      ) {
        diagnostics.push("ASSESSMENT_MAGNITUDE_REQUIRED");
      }
    }
  }
}

function adr008Policy(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const realm = asObject(document.authority_realm_key);
  const expected = fixtureObject(fixture, "authenticated_realm_key");
  if (!isRealmKey(realm) || !objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS)) {
    diagnostics.push("REALM_REQUIRED");
  }
  if (document.producer_principal_id !== fixtureString(fixture, "extension_assessor_principal_id")) {
    diagnostics.push("EXTENSION_PRODUCER_ROLE_INVALID");
  }
  if (
    Object.hasOwn(document, "effect") ||
    Object.hasOwn(document, "calibrated_for_policy") ||
    Object.hasOwn(document, "state_usability")
  ) {
    diagnostics.push("EXTENSION_POLICY_FIELD_FORBIDDEN");
  }
}

function adr008SensorConditionDetail(
  document: JsonObject,
  diagnostics: string[],
): void {
  const requirements = [
    ["available_or_unknown_group_rejects", true, "SENSOR_CONDITION_DETAIL_AVAILABLE_UNKNOWN_REJECTION_REQUIRED"],
    ["complete_normative_source_ref_required", true, "SENSOR_CONDITION_DETAIL_SOURCE_REQUIRED"],
    ["contradictory_group_rejects", true, "SENSOR_CONDITION_DETAIL_CONTRADICTION_REJECTION_REQUIRED"],
    ["detail_can_authorize", false, "SENSOR_CONDITION_DETAIL_AUTHORITY_FORBIDDEN"],
    ["detail_can_block_action", false, "SENSOR_CONDITION_DETAIL_ACTION_BLOCKING_FORBIDDEN"],
    ["detail_can_block_perception", false, "SENSOR_CONDITION_DETAIL_PERCEPTION_BLOCKING_FORBIDDEN"],
    ["detail_can_change_availability", false, "SENSOR_CONDITION_DETAIL_AVAILABILITY_AUTHORITY_FORBIDDEN"],
    ["detail_record_is_optional", true, "SENSOR_CONDITION_DETAIL_OPTIONALITY_REQUIRED"],
    ["detail_repeats_bitmap", false, "SENSOR_CONDITION_DETAIL_BITMAP_REPETITION_FORBIDDEN"],
    ["detail_repeats_layout", false, "SENSOR_CONDITION_DETAIL_LAYOUT_REPETITION_FORBIDDEN"],
    ["detail_repeats_scalars", false, "SENSOR_CONDITION_DETAIL_SCALAR_REPETITION_FORBIDDEN"],
    ["duplicate_group_rejects", true, "SENSOR_CONDITION_DETAIL_DUPLICATE_REJECTION_REQUIRED"],
    ["entries_bounded", true, "SENSOR_CONDITION_DETAIL_ENTRY_BOUNDS_REQUIRED"],
    ["entries_sorted_by_group_ordinal", true, "SENSOR_CONDITION_DETAIL_ENTRY_ORDER_REQUIRED"],
    ["exact_pinned_core_source_resolved_before_entry_checks", true, "SENSOR_CONDITION_DETAIL_SOURCE_RESOLUTION_ORDER_REQUIRED"],
    ["invalid_detail_rejects_extension_only", true, "SENSOR_CONDITION_DETAIL_FAILURE_SCOPE_REQUIRED"],
    ["reason_codes_bounded", true, "SENSOR_CONDITION_DETAIL_REASON_BOUNDS_REQUIRED"],
    ["separate_principal_and_resource_partition", true, "SENSOR_CONDITION_DETAIL_RESOURCE_ISOLATION_REQUIRED"],
    ["unknown_reason_code_rejects", true, "SENSOR_CONDITION_DETAIL_UNKNOWN_REASON_REJECTION_REQUIRED"],
    ["wrong_or_evicted_source_rejects", true, "SENSOR_CONDITION_DETAIL_SOURCE_CURRENTNESS_REJECTION_REQUIRED"],
  ] as const;
  requireExactProjectionMembers(
    document,
    [
      "absent_late_rejected_or_overflowed_result",
      "detail_entry_members",
      "detail_record_members",
      ...requirements.map(([field]) => field),
    ],
    "SENSOR_CONDITION_DETAIL_PROJECTION_INVALID",
    diagnostics,
  );
  requireProjectionLiteral(
    document,
    "absent_late_rejected_or_overflowed_result",
    "REASON_UNAVAILABLE",
    "SENSOR_CONDITION_DETAIL_ABSENCE_RESULT_INVALID",
    diagnostics,
  );
  requireProjectionArray(
    document,
    "detail_entry_members",
    ["group_ordinal", "reason_code"],
    "SENSOR_CONDITION_DETAIL_ENTRY_SHAPE_INVALID",
    diagnostics,
  );
  requireProjectionArray(
    document,
    "detail_record_members",
    ["source", "entries"],
    "SENSOR_CONDITION_DETAIL_RECORD_SHAPE_INVALID",
    diagnostics,
  );
  for (const [field, expected, diagnostic] of requirements) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
}

function requireProjectionBoolean(
  document: JsonObject,
  field: string,
  expected: boolean,
  diagnostic: string,
  diagnostics: string[],
): void {
  if (document[field] !== expected) diagnostics.push(diagnostic);
}

function requireProjectionLiteral(
  document: JsonObject,
  field: string,
  expected: string | number,
  diagnostic: string,
  diagnostics: string[],
): void {
  if (document[field] !== expected) diagnostics.push(diagnostic);
}

function requireProjectionArray(
  document: JsonObject,
  field: string,
  expected: readonly (string | number)[],
  diagnostic: string,
  diagnostics: string[],
): void {
  const actual = asArray(document[field]);
  if (
    actual === undefined ||
    actual.length !== expected.length ||
    actual.some((value, index) => value !== expected[index])
  ) {
    diagnostics.push(diagnostic);
  }
}

function requireProjectionMatrix(
  document: JsonObject,
  field: string,
  expected: readonly (readonly (string | number)[])[],
  diagnostic: string,
  diagnostics: string[],
): void {
  const actual = asArray(document[field]);
  if (
    actual === undefined ||
    actual.length !== expected.length ||
    actual.some((row, rowIndex) => {
      const values = asArray(row);
      const wanted = expected[rowIndex];
      return (
        wanted === undefined ||
        values === undefined ||
        values.length !== wanted.length ||
        values.some((value, valueIndex) => value !== wanted[valueIndex])
      );
    })
  ) {
    diagnostics.push(diagnostic);
  }
}

function requireExactProjectionMembers(
  document: JsonObject,
  expected: readonly string[],
  diagnostic: string,
  diagnostics: string[],
): void {
  const actual = Object.keys(document).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    diagnostics.push(diagnostic);
  }
}

function adr009Projection(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  validateSecurityCommon(document, fixture, diagnostics);
  validateSecurityMembership(document, fixture, diagnostics);
}

function validateSecurityMembership(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const principals = asArray(document.principals);
  const principalIds =
    principals?.map((entry) => nonemptyString(asObject(entry)?.principal_id)) ?? [];
  if (
    principals === undefined ||
    principals.length === 0 ||
    principalIds.some((principalId) => principalId === undefined) ||
    new Set(principalIds).size !== principals.length ||
    principals.some((entry) => {
      const principal = asObject(entry);
      const planes = principal === undefined ? undefined : asArray(principal.planes);
      return (
        principal === undefined ||
        nonemptyString(principal.principal_id) === undefined ||
        nonemptyString(principal.role) === undefined ||
        planes === undefined ||
        planes.length === 0 ||
        !planes.every((plane) => typeof plane === "string" && plane.length > 0) ||
        new Set(planes).size !== planes.length
      );
    })
  ) {
    diagnostics.push("PRINCIPAL_MEMBERSHIP_REQUIRED");
  }
  const keyEpochs = asArray(document.key_epochs);
  if (keyEpochs === undefined || keyEpochs.length === 0) {
    diagnostics.push("KEY_EPOCH_MEMBERSHIP_REQUIRED");
  } else {
    const epochs = keyEpochs.map((entry) => safeInteger(asObject(entry)?.epoch));
    const keyIds = keyEpochs.map((entry) => nonemptyString(asObject(entry)?.kid));
    if (
      epochs.some((epoch) => epoch === undefined || epoch <= 0) ||
      keyIds.some((keyId) => keyId === undefined) ||
      new Set(epochs).size !== keyEpochs.length ||
      new Set(keyIds).size !== keyEpochs.length
    ) {
      diagnostics.push("KEY_EPOCH_MEMBERSHIP_REQUIRED");
    }
    const requiredAlgorithm = fixtureString(fixture, "required_key_algorithm");
    for (const entry of keyEpochs) {
      const key = asObject(entry);
      if (key?.algorithm !== requiredAlgorithm) {
        diagnostics.push("SECURITY_ALGORITHM_NOT_EXACT");
      }
      if (!isPrefixedDigest(key?.kid)) diagnostics.push("KEY_ID_NOT_CONTENT_ADDRESSED");
      if (safeInteger(key?.epoch) === undefined || (key?.epoch as number) <= 0) {
        diagnostics.push("KEY_EPOCH_MEMBERSHIP_REQUIRED");
      }
    }
  }
}

function adr009Invalid(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  validateSecurityCommon(document, fixture, diagnostics);
  validateSecurityMembership(document, fixture, diagnostics);
  if (document.algorithm !== fixtureString(fixture, "required_key_algorithm")) {
    diagnostics.push("SECURITY_ALGORITHM_NOT_EXACT");
  }
  if (!isPrefixedDigest(document.kid)) diagnostics.push("KEY_ID_NOT_CONTENT_ADDRESSED");
}

function validateSecurityCommon(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const expectedRealm = fixtureObject(fixture, "authenticated_authority_realm");
  const realm = asObject(document.authority_realm);
  if (!isAuthorityRealm(realm)) {
    diagnostics.push("AUTHORITY_REALM_KEY_REQUIRED");
  } else if (!objectsExactlyEqualOn(realm, expectedRealm, AUTHORITY_REALM_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_MISMATCH");
  }
  if (document.profile !== fixtureString(fixture, "required_profile")) {
    diagnostics.push("SECURITY_PROFILE_INVALID");
  }
  const maximum = fixtureInteger(fixture, "maximum_security_epoch");
  const securityEpoch = safeInteger(document.security_epoch);
  const revocationEpoch = safeInteger(document.revocation_epoch);
  if (securityEpoch === undefined || securityEpoch <= 0 || securityEpoch > maximum) {
    diagnostics.push("SECURITY_EPOCH_INVALID");
  }
  if (revocationEpoch === undefined || revocationEpoch <= 0 || revocationEpoch > maximum) {
    diagnostics.push("REVOCATION_EPOCH_INVALID");
  }
}

function adr010Action(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  validateQosRealm(document, fixture, diagnostics);
  if (document.profile_id !== "ncp-action-v1") diagnostics.push("QOS_PROFILE_ID_REQUIRED");
  if (document.plane !== "action") diagnostics.push("QOS_PLANE_REQUIRED");
  if (nonemptyString(document.route) === undefined) diagnostics.push("QOS_ROUTE_REQUIRED");
  const capacity = safeInteger(document.capacity_per_stream);
  if (
    capacity === undefined ||
    capacity <= 0 ||
    capacity > fixtureInteger(fixture, "maximum_capacity_per_stream")
  ) {
    diagnostics.push("QOS_CAPACITY_INVALID");
  }
  if (document.ordering !== "strict_stream_sequence") diagnostics.push("QOS_ORDERING_REQUIRED");
  if (document.retention !== "until_terminal_disposition_or_expiry") {
    diagnostics.push("QOS_RETENTION_REQUIRED");
  }
  if (document.overload !== "reject_new_active_and_emit_disposition") {
    diagnostics.push("QOS_OVERLOAD_INVALID");
  }
  const priority = asArray(document.fail_safe_priority);
  if (priority === undefined) {
    diagnostics.push("QOS_FAIL_SAFE_PRIORITY_REQUIRED");
  } else if (!arraysEqual(priority, fixtureStringArray(fixture, "required_fail_safe_priority"))) {
    diagnostics.push("FAIL_SAFE_PRIORITY_INVALID");
  }
  if (Object.hasOwn(document, "fallback")) diagnostics.push("QOS_FALLBACK_FORBIDDEN");
}

function adr010Invalid(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  adr010Action(document, fixture, diagnostics);
}

function adr010PerceptionQueueMissingness(
  document: JsonObject,
  diagnostics: string[],
): void {
  const fields = [
    "authenticated_received_item_may_bear_producer_position",
    "availability_bitmap_and_scalar_storage_indivisible",
    "closed_perception_states",
    "item_digest_count",
    "item_position_count",
    "item_queue_slot_count",
    "item_supersession_decision_count",
    "partial_drop_or_replace_allowed",
    "producer_encode_or_queue_failure_after_assignment_consumes_position",
    "producer_incomplete_or_malformed_rejects_before_position_assignment",
    "received_available_zero_is_observation",
    "received_unavailable_exposes_observation",
    "receiver_malformed_rejection_creates_admission",
    "receiver_malformed_rejection_creates_pin",
    "receiver_malformed_rejection_invokes_typed_callback",
    "receiver_malformed_rejection_rolls_back_producer_position",
    "transport_gap_implies_sensor_unavailable",
    "whole_frame_loss_equals_transport_gap",
    "zero_or_omission_infers_availability",
  ] as const;
  requireExactProjectionMembers(
    document,
    fields,
    "PERCEPTION_QUEUE_MISSINGNESS_PROJECTION_INVALID",
    diagnostics,
  );
  requireProjectionBoolean(
    document,
    "availability_bitmap_and_scalar_storage_indivisible",
    true,
    "PERCEPTION_ITEM_INDIVISIBILITY_REQUIRED",
    diagnostics,
  );
  requireProjectionArray(
    document,
    "closed_perception_states",
    [
      "RECEIVED_AVAILABLE_ZERO",
      "RECEIVED_UNAVAILABLE",
      "MALFORMED_FRAME",
      "TRANSPORT_GAP",
      "WHOLE_FRAME_LOSS",
    ],
    "PERCEPTION_MISSINGNESS_STATES_INVALID",
    diagnostics,
  );
  for (const [field, diagnostic] of [
    ["item_digest_count", "PERCEPTION_ITEM_DIGEST_UNITY_REQUIRED"],
    ["item_position_count", "PERCEPTION_ITEM_POSITION_UNITY_REQUIRED"],
    ["item_queue_slot_count", "PERCEPTION_ITEM_QUEUE_SLOT_UNITY_REQUIRED"],
    ["item_supersession_decision_count", "PERCEPTION_ITEM_SUPERSESSION_UNITY_REQUIRED"],
  ] as const) {
    requireProjectionLiteral(document, field, 1, diagnostic, diagnostics);
  }
  for (const [field, expected, diagnostic] of [
    ["authenticated_received_item_may_bear_producer_position", true, "PERCEPTION_AUTHENTICATED_PRODUCER_POSITION_PRESERVATION_REQUIRED"],
    ["partial_drop_or_replace_allowed", false, "PERCEPTION_ITEM_PARTIAL_MUTATION_FORBIDDEN"],
    ["producer_encode_or_queue_failure_after_assignment_consumes_position", true, "PERCEPTION_PRODUCER_POST_ASSIGNMENT_POSITION_CONSUMED_REQUIRED"],
    ["producer_incomplete_or_malformed_rejects_before_position_assignment", true, "PERCEPTION_PRODUCER_PRE_ASSIGNMENT_VALIDATION_REQUIRED"],
    ["received_available_zero_is_observation", true, "PERCEPTION_AVAILABLE_ZERO_OBSERVATION_REQUIRED"],
    ["received_unavailable_exposes_observation", false, "PERCEPTION_UNAVAILABLE_OBSERVATION_FORBIDDEN"],
    ["receiver_malformed_rejection_creates_admission", false, "PERCEPTION_RECEIVER_MALFORMED_ADMISSION_FORBIDDEN"],
    ["receiver_malformed_rejection_creates_pin", false, "PERCEPTION_RECEIVER_MALFORMED_PIN_FORBIDDEN"],
    ["receiver_malformed_rejection_invokes_typed_callback", false, "PERCEPTION_RECEIVER_MALFORMED_CALLBACK_FORBIDDEN"],
    ["receiver_malformed_rejection_rolls_back_producer_position", false, "PERCEPTION_RECEIVER_POSITION_ROLLBACK_FORBIDDEN"],
    ["transport_gap_implies_sensor_unavailable", false, "PERCEPTION_GAP_UNAVAILABILITY_INFERENCE_FORBIDDEN"],
    ["whole_frame_loss_equals_transport_gap", false, "PERCEPTION_LOSS_GAP_COLLAPSE_FORBIDDEN"],
    ["zero_or_omission_infers_availability", false, "PERCEPTION_ZERO_OMISSION_INFERENCE_FORBIDDEN"],
  ] as const) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
}

function validateQosRealm(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm)) {
    diagnostics.push("AUTHORITY_REALM_KEY_REQUIRED");
    return;
  }
  const expected = fixtureObject(fixture, "authenticated_realm_key");
  if (!objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS)) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  }
  if (document.route !== fixtureString(fixture, "expected_route")) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  }
}

function adr011RegisteredIntent(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  requireExactProjectionMembers(
    document,
    [
      "audience_principal_id",
      "authority_realm_key",
      "controller_t_ns",
      "effective_deadline_tick_ns",
      "extension_id",
      "freshness_grant",
      "intent_id",
      "intent_sequence",
      "intent_stream_epoch",
      "logical_session_id",
      "manifest_digest",
      "plant_session_generation",
      "plant_session_kind",
      "producer_principal_id",
      "requested_effect",
      "requested_validity_ms",
      "route",
      "schema_version",
      "selected_slot",
      "semantic_encoding",
      "signature_coverage",
      "source",
    ],
    "INTENT_ENVELOPE_SHAPE_INVALID",
    diagnostics,
  );
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm) || !objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_MISMATCH");
  }
  for (const [field, fixtureField, diagnostic] of [
    ["extension_id", "expected_extension_id", "EXTENSION_ID_MISMATCH"],
    ["schema_version", "expected_schema_version", "EXTENSION_SCHEMA_VERSION_MISMATCH"],
    ["manifest_digest", "expected_manifest_digest", "EXTENSION_MANIFEST_DIGEST_MISMATCH"],
    ["semantic_encoding", "expected_semantic_encoding", "EXTENSION_SEMANTIC_ENCODING_INVALID"],
    ["route", "expected_route", "REALM_ROUTE_MISMATCH"],
    ["producer_principal_id", "expected_producer_principal_id", "INTENT_ISSUER_MISMATCH"],
    ["audience_principal_id", "expected_audience_principal_id", "INTENT_AUDIENCE_MISMATCH"],
    ["plant_session_kind", "expected_plant_session_kind", "SESSION_KIND_MISMATCH"],
    ["logical_session_id", "expected_logical_session_id", "INTENT_SESSION_MISMATCH"],
    ["plant_session_generation", "expected_plant_session_generation", "INTENT_SESSION_MISMATCH"],
    ["intent_stream_epoch", "expected_intent_stream_epoch", "INTENT_REPLAY_COORDINATE_INVALID"],
  ] as const) {
    if (document[field] !== fixtureString(fixture, fixtureField)) diagnostics.push(diagnostic);
  }
  if (nonemptyString(document.intent_id) === undefined) {
    diagnostics.push("INTENT_REPLAY_COORDINATE_INVALID");
  }
  const sequence = safeInteger(document.intent_sequence);
  if (
    sequence === undefined ||
    sequence <= 0 ||
    sequence !== fixtureInteger(fixture, "expected_intent_sequence")
  ) {
    diagnostics.push("INTENT_REPLAY_COORDINATE_INVALID");
  }
  const grant = asObject(document.freshness_grant);
  requireExactProjectionMembers(
    grant ?? {},
    [
      "allowed_requested_effects",
      "clock_incarnation",
      "digest",
      "first_slot",
      "installation_receipt_digest",
      "issue_tick_ns",
      "last_slot_exclusive",
      "maximum_not_after_tick_ns",
      "maximum_requested_validity_ms",
    ],
    "INTENT_FRESHNESS_GRANT_MISMATCH",
    diagnostics,
  );
  const expectedGrant = fixtureObject(fixture, "expected_freshness_grant");
  for (const [field, diagnostic] of [
    ["digest", "INTENT_FRESHNESS_GRANT_MISMATCH"],
    ["installation_receipt_digest", "INTENT_FRESHNESS_GRANT_INSTALLATION_RECEIPT_MISMATCH"],
    ["clock_incarnation", "INTENT_FRESHNESS_CLOCK_MISMATCH"],
  ] as const) {
    if (grant?.[field] !== expectedGrant[field]) diagnostics.push(diagnostic);
  }
  for (const field of [
    "issue_tick_ns",
    "maximum_not_after_tick_ns",
    "first_slot",
    "last_slot_exclusive",
    "maximum_requested_validity_ms",
  ] as const) {
    if (safeInteger(grant?.[field]) !== safeInteger(expectedGrant[field])) {
      diagnostics.push("INTENT_FRESHNESS_GRANT_MISMATCH");
      break;
    }
  }
  const allowed = asArray(grant?.allowed_requested_effects);
  const expectedAllowedValues = asArray(expectedGrant.allowed_requested_effects);
  const expectedAllowed = expectedAllowedValues?.every((value) => typeof value === "string")
    ? expectedAllowedValues as string[]
    : undefined;
  if (
    allowed === undefined ||
    expectedAllowed === undefined ||
    !arraysEqual(allowed, expectedAllowed)
  ) {
    diagnostics.push("INTENT_REQUESTED_EFFECT_INVALID");
  }
  const firstSlot = safeInteger(grant?.first_slot);
  const lastSlot = safeInteger(grant?.last_slot_exclusive);
  const selectedSlot = safeInteger(document.selected_slot);
  if (
    firstSlot === undefined ||
    lastSlot === undefined ||
    selectedSlot === undefined ||
    firstSlot <= 0 ||
    firstSlot >= lastSlot ||
    selectedSlot < firstSlot ||
    selectedSlot >= lastSlot
  ) {
    diagnostics.push("INTENT_FRESHNESS_SLOT_INVALID");
  }
  if (
    document.requested_effect !== fixtureString(fixture, "expected_requested_effect") ||
    allowed === undefined ||
    !allowed.includes(document.requested_effect)
  ) {
    diagnostics.push("INTENT_REQUESTED_EFFECT_INVALID");
  }
  const issueTick = safeInteger(grant?.issue_tick_ns);
  const maximumDeadline = safeInteger(grant?.maximum_not_after_tick_ns);
  const maximumValidity = safeInteger(grant?.maximum_requested_validity_ms);
  const requestedValidity = safeInteger(document.requested_validity_ms);
  let computedDeadline: number | undefined;
  if (
    issueTick === undefined ||
    maximumDeadline === undefined ||
    maximumValidity === undefined ||
    requestedValidity === undefined ||
    requestedValidity <= 0 ||
    requestedValidity > maximumValidity
  ) {
    diagnostics.push("INTENT_VALIDITY_INVALID");
  } else {
    const duration = requestedValidity * 1_000_000;
    const candidate = issueTick + duration;
    if (!Number.isSafeInteger(duration) || !Number.isSafeInteger(candidate)) {
      diagnostics.push("INTENT_VALIDITY_INVALID");
    } else {
      computedDeadline = Math.min(candidate, maximumDeadline);
    }
  }
  const effectiveDeadline = safeInteger(document.effective_deadline_tick_ns);
  if (effectiveDeadline !== computedDeadline) diagnostics.push("INTENT_DEADLINE_INVALID");
  if (
    effectiveDeadline === undefined ||
    effectiveDeadline <= fixtureInteger(fixture, "evaluation_tick_ns")
  ) {
    diagnostics.push("INTENT_EXPIRED");
  }
  const expectedSource = fixtureObject(fixture, "expected_source");
  const source = asObject(document.source);
  if (
    source === undefined ||
    !objectsExactlyEqualOn(source, expectedSource, ["kind", "reason"]) ||
    Object.keys(source).length !== 2
  ) {
    diagnostics.push("INTENT_SOURCE_UNION_INVALID");
  }
  const signatureCoverage = asArray(document.signature_coverage);
  const expectedCoverage = fixtureStringArray(fixture, "expected_signature_coverage");
  if (
    signatureCoverage === undefined ||
    !arraysEqual(signatureCoverage, expectedCoverage)
  ) {
    diagnostics.push("INTENT_SIGNATURE_COVERAGE_INVALID");
  }
  if (safeInteger(document.controller_t_ns) === undefined) {
    diagnostics.push("INTENT_ENVELOPE_SHAPE_INVALID");
  }
}

function adr011Command(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  if (document.kind !== "command_frame") diagnostics.push("MESSAGE_KIND_MISMATCH");
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm) || !objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_KEY_REQUIRED");
  }
  const identity = asObject(document.identity);
  if (identity?.principal_id !== fixtureString(fixture, "gated_commander_principal_id")) {
    diagnostics.push("COMMAND_IDENTITY_LAUNDERING");
  }
  const authority = asObject(document.authority);
  if (authority?.issuer_principal_id !== fixtureString(fixture, "enrolled_body_principal_id")) {
    diagnostics.push("COMMAND_AUTHORITY_ISSUER_NOT_BODY");
  }
}

function adr011EffectPathFencing(
  document: JsonObject,
  diagnostics: string[],
): void {
  requireExactProjectionMembers(
    document,
    [
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
  for (const [field, expected, diagnostic] of [
    ["endpoint_aliases_normalized", true, "EFFECT_ENDPOINT_ALIAS_NORMALIZATION_REQUIRED"],
    ["overlap_uses_resource_intersection", true, "EFFECT_OVERLAP_CHECK_REQUIRED"],
    ["disjoint_paths_require_independent_fencing_domains", true, "EFFECT_FENCING_DOMAIN_SEPARATION_REQUIRED"],
    ["fencing_token_binds_domain_incarnation", true, "EFFECT_FENCING_DOMAIN_INCARNATION_REQUIRED"],
    ["write_requires_current_fencing_term", true, "EFFECT_WRITE_FENCING_TERM_REQUIRED"],
    ["unfenceable_replacement_requires_isolation", true, "EFFECT_PATH_ISOLATION_REQUIRED"],
    ["handover_allows_live_writer_overlap", false, "EFFECT_HANDOVER_OVERLAP_FORBIDDEN"],
    ["hot_path_evaluates_proof_graph", false, "EFFECT_HOT_PATH_PROOF_GRAPH_FORBIDDEN"],
  ] as const) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
}

function adr011PreparedPublisher(
  document: JsonObject,
  diagnostics: string[],
): void {
  const requirements = [
    ["layout_profile_defines_reusable_rules", true, "PREPARED_PROFILE_RULES_REQUIRED"],
    ["layout_instance_binds_roster_slots_and_resources", true, "PREPARED_LAYOUT_INSTANCE_REQUIRED"],
    ["prepared_publisher_owns_layout_bound_transport_slot", true, "PREPARED_LAYOUT_BOUND_TRANSPORT_SLOT_REQUIRED"],
    ["foreign_or_stale_slot_handle_is_accepted", false, "PREPARED_FOREIGN_SLOT_HANDLE_FORBIDDEN"],
    ["detached_buffer_context_rebind_is_exposed", false, "PREPARED_DETACHED_BUFFER_REBIND_FORBIDDEN"],
    ["all_bound_slots_materialized_once_by_packer", true, "PREPARED_COMPLETE_FRAME_WRITE_REQUIRED"],
    ["caller_writes_unavailable_slots", false, "PREPARED_CALLER_UNAVAILABLE_SLOT_WRITE_FORBIDDEN"],
    ["sensor_layout_requires_positive_group_count", true, "PREPARED_SENSOR_LAYOUT_POSITIVE_GROUP_COUNT_REQUIRED"],
    ["availability_groups_partition_sensor_slots_once", true, "PREPARED_AVAILABILITY_GROUP_PARTITION_REQUIRED"],
    ["availability_bitmap_inline_with_scalar_storage", true, "PREPARED_AVAILABILITY_INLINE_REQUIRED"],
    ["availability_byte_count_is_ceil_group_count_over_8", true, "PREPARED_AVAILABILITY_BYTE_COUNT_FORMULA_REQUIRED"],
    ["packer_is_only_application_direct_publisher", true, "PREPARED_APPLICATION_PUBLISHER_EXCLUSIVITY_REQUIRED"],
    ["final_position_assigned_before_transfer", true, "PREPARED_FINAL_POSITION_REQUIRED"],
    ["exact_serialized_bytes_transferred_once", true, "PREPARED_EXACT_BYTE_TRANSFER_REQUIRED"],
    ["application_mutable_alias_survives_transfer", false, "PREPARED_APPLICATION_MUTABLE_ALIAS_FORBIDDEN"],
    ["raw_application_publisher_exposed", false, "PREPARED_RAW_APPLICATION_PUBLISHER_FORBIDDEN"],
    ["separate_application_signer_or_publisher_holds_credentials", false, "PREPARED_SEPARATE_APPLICATION_CREDENTIAL_HOLDER_FORBIDDEN"],
    ["direct_frame_adds_preparation_tag", false, "PREPARED_HOT_FRAME_TAG_FORBIDDEN"],
    ["transport_record_protection_covers_exact_sealed_bytes", true, "PREPARED_SEALED_BYTE_PROTECTION_REQUIRED"],
    ["sealed_record_mutation_before_open_is_accepted", false, "PREPARED_SEALED_RECORD_MUTATION_FORBIDDEN"],
    ["sender_pre_seal_mutation_claimed_detectable", false, "PREPARED_SENDER_PRE_SEAL_DETECTION_OVERCLAIM"],
    ["receiver_post_open_mutation_claimed_detectable", false, "PREPARED_RECEIVER_POST_OPEN_DETECTION_OVERCLAIM"],
    ["receiver_attests_packer_output", false, "PREPARED_RECEIVER_ATTESTATION_OVERCLAIM"],
    ["pre_seal_same_unit_misassociation_claimed_detectable", false, "PREPARED_PRE_SEAL_DETECTION_OVERCLAIM"],
    ["equal_value_swap_claimed_detectable", false, "PREPARED_EQUAL_VALUE_DETECTION_OVERCLAIM"],
    ["packer_owns_shared_clock_semantics", false, "PREPARED_CLOCK_OWNERSHIP_FORBIDDEN"],
  ] as const;
  requireExactProjectionMembers(
    document,
    [
      ...requirements.map(([field]) => field),
      "non_sensor_layout_availability_group_count",
      "non_sensor_layout_availability_bytes",
    ],
    "PREPARED_APPLICATION_PUBLISHER_EXCLUSIVITY_REQUIRED",
    diagnostics,
  );
  for (const [field, expected, diagnostic] of requirements) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
  requireProjectionLiteral(
    document,
    "non_sensor_layout_availability_group_count",
    0,
    "PREPARED_NON_SENSOR_GROUP_COUNT_INVALID",
    diagnostics,
  );
  requireProjectionLiteral(
    document,
    "non_sensor_layout_availability_bytes",
    0,
    "PREPARED_NON_SENSOR_AVAILABILITY_BYTES_INVALID",
    diagnostics,
  );
}

function adr011X02FleetAvailability(document: JsonObject, diagnostics: string[]): void {
  requireExactProjectionMembers(
    document,
    [
      "bitmap_polarity",
      "bit_order",
      "unused_high_bits_zero",
      "availability_groups_per_drone",
      "sensor_scalars_per_drone",
      "command_scalars_per_drone",
      "availability_bytes_n1_n2_n3",
      "exhaustive_masks_hex_n1_n2_n3",
      "all_available_hex_n1_n2_n3",
      "first_drone_unavailable_hex_n1_n2_n3",
      "group_to_command_slots_n3",
      "conflicting_dependency_overlap_rejected_at_preparation",
      "unavailable_placeholder_f64_bits",
      "lane_state_sequence",
      "fault_during_washout_returns_to",
      "one_composite_session",
      "one_nest_kernel",
      "music_shared_clock_owned",
    ],
    "X02_FLEET_AVAILABILITY_PROJECTION_INVALID",
    diagnostics,
  );
  for (const [field, expected, diagnostic] of [
    ["bitmap_polarity", "ONE_AVAILABLE_ZERO_UNAVAILABLE", "X02_AVAILABILITY_BITMAP_POLARITY_INVALID"],
    ["bit_order", "LSB_FIRST_ROSTER_ORDER", "X02_AVAILABILITY_BIT_ORDER_INVALID"],
    ["availability_groups_per_drone", 1, "X02_AVAILABILITY_GROUP_WIDTH_INVALID"],
    ["sensor_scalars_per_drone", 6, "X02_SENSOR_SCALAR_WIDTH_INVALID"],
    ["command_scalars_per_drone", 3, "X02_COMMAND_SCALAR_WIDTH_INVALID"],
    ["unavailable_placeholder_f64_bits", "0000000000000000", "X02_UNAVAILABLE_PLACEHOLDER_BITS_INVALID"],
  ] as const) {
    requireProjectionLiteral(document, field, expected, diagnostic, diagnostics);
  }
  for (const [field, expected, diagnostic] of [
    ["unused_high_bits_zero", true, "X02_AVAILABILITY_PADDING_INVALID"],
    ["one_composite_session", true, "X02_COMPOSITE_SESSION_REQUIRED"],
    ["one_nest_kernel", true, "X02_ONE_NEST_KERNEL_REQUIRED"],
    ["music_shared_clock_owned", false, "X02_MUSIC_CLOCK_OWNERSHIP_FORBIDDEN"],
  ] as const) {
    requireProjectionBoolean(document, field, expected, diagnostic, diagnostics);
  }
  requireProjectionArray(
    document,
    "availability_bytes_n1_n2_n3",
    [1, 1, 1],
    "X02_AVAILABILITY_BYTE_COUNTS_INVALID",
    diagnostics,
  );
  requireProjectionMatrix(
    document,
    "exhaustive_masks_hex_n1_n2_n3",
    [
      ["00", "01"],
      ["00", "01", "02", "03"],
      ["00", "01", "02", "03", "04", "05", "06", "07"],
    ],
    "X02_EXHAUSTIVE_MASKS_INVALID",
    diagnostics,
  );
  requireProjectionArray(
    document,
    "all_available_hex_n1_n2_n3",
    ["01", "03", "07"],
    "X02_ALL_AVAILABLE_VECTOR_INVALID",
    diagnostics,
  );
  requireProjectionArray(
    document,
    "first_drone_unavailable_hex_n1_n2_n3",
    ["00", "02", "06"],
    "X02_FIRST_UNAVAILABLE_VECTOR_INVALID",
    diagnostics,
  );
  requireProjectionMatrix(
    document,
    "group_to_command_slots_n3",
    [[0, 1, 2], [3, 4, 5], [6, 7, 8]],
    "X02_GROUP_COMMAND_SLOT_MAP_INVALID",
    diagnostics,
  );
  requireProjectionBoolean(
    document,
    "conflicting_dependency_overlap_rejected_at_preparation",
    true,
    "X02_DEPENDENCY_OVERLAP_PREPARATION_REJECTION_REQUIRED",
    diagnostics,
  );
  requireProjectionArray(
    document,
    "lane_state_sequence",
    ["NORMAL", "UNAVAILABLE_RESTRICTIVE", "RECOVERY_WASHOUT", "NORMAL"],
    "X02_LANE_STATE_SEQUENCE_INVALID",
    diagnostics,
  );
  requireProjectionLiteral(
    document,
    "fault_during_washout_returns_to",
    "UNAVAILABLE_RESTRICTIVE",
    "X02_WASHOUT_FAULT_RETURN_INVALID",
    diagnostics,
  );
}

function validateFixture(profile: string, fixture: JsonValue): void {
  const value = requiredObject(fixture, `fixture for ${profile}`);
  switch (profile) {
    case "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1":
      exactFixtureKeys(value, [
        "digest_algorithm",
        "expected_commander_principal_id",
        "expected_ncp_version",
        "expected_session_kind",
      ], profile);
      requireFixtureLiteral(value.digest_algorithm, "sha256", profile);
      requireFixtureLiteral(value.expected_ncp_version, "1.0", profile);
      requireFixtureLiteral(value.expected_session_kind, "open_plant_session", profile);
      requireFixtureString(value.expected_commander_principal_id, profile);
      return;
    case "ADR002_REALM_BOUND_CONTRACT_IDENTITY_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "digest_algorithm",
        "expected_stable_core_digest",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureLiteral(value.digest_algorithm, "sha256", profile);
      if (!isPrefixedDigest(value.expected_stable_core_digest)) {
        throw new SemanticConfigurationError(
          `${profile} fixture requires a prefixed lowercase SHA-256`,
        );
      }
      return;
    case "ADR003_FLATTENED_FORWARDING_WRAPPER_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "expected_signature_bytes",
        "required_algorithm",
        "signature_verifies",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureLiteral(value.required_algorithm, "Ed25519", profile);
      requireFixtureInteger(value.expected_signature_bytes, profile, true);
      requireFixtureLiteral(value.signature_verifies, false, profile);
      return;
    case "ADR003_PROTECTED_HEADER_REQUIRED_MEMBER_PROJECTION_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "expected_audience",
        "expected_route",
        "required_algorithm",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureLiteral(value.required_algorithm, "Ed25519", profile);
      requireFixtureString(value.expected_audience, profile);
      requireFixtureString(value.expected_route, profile);
      return;
    case "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1":
      exactFixtureKeys(value, ["expected_state", "output_allocation_permitted"], profile);
      requireFixtureLiteral(value.expected_state, "PENDING_INTENT_ONLY", profile);
      requireFixtureLiteral(value.output_allocation_permitted, false, profile);
      return;
    case "ADR005_DECLARE_STREAM_EXCERPT_V1":
      exactFixtureKeys(value, [
        "authenticated_publisher_principal_id",
        "authenticated_realm_key",
        "expected_route",
        "live_declaration_epoch_ids",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.authenticated_publisher_principal_id, profile);
      requireFixtureString(value.expected_route, profile);
      requireStringArray(value.live_declaration_epoch_ids, profile);
      return;
    case "ADR005_UNDECLARED_FRAME_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "live_declaration_epoch_ids",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireStringArray(value.live_declaration_epoch_ids, profile);
      return;
    case "ADR006_BODY_LEASE_EXCERPT_V1":
    case "ADR006_STALE_SELF_ISSUED_LEASE_V1": {
      exactFixtureKeys(value, ["current_lease", "enrolled_body_principal_id", "evaluation_utc_ms"], profile);
      requireFixtureString(value.enrolled_body_principal_id, profile);
      requireFixtureInteger(value.evaluation_utc_ms, profile, true);
      const lease = requiredObject(value.current_lease, `${profile}.current_lease`);
      exactFixtureKeys(
        lease,
        ["holder_entity_id", "holder_principal_id", "lease_id", "session_generation", "term"],
        `${profile}.current_lease`,
      );
      for (const key of ["holder_entity_id", "holder_principal_id", "lease_id", "session_generation"] as const) {
        requireFixtureString(lease[key], profile);
      }
      requireFixtureInteger(lease.term, profile, true);
      return;
    }
    case "ADR004_SENSOR_PROJECTION_ANTI_LAUNDERING_V1":
    case "ADR005_SENSOR_AVAILABILITY_SOURCE_BOUND_V1":
    case "ADR005_SENSOR_AVAILABILITY_DETACHED_MASK_V1":
    case "ADR007_DISPOSITION_QUERY_PROJECTION_V1":
    case "ADR007_UNAVAILABLE_SOURCE_RESTRICTIVE_ACTION_V1":
    case "ADR008_EXTENSION_ENVELOPE_PROJECTION_V1":
    case "ADR008_SENSOR_CONDITION_DETAIL_V1":
    case "ADR010_PERCEPTION_QUEUE_MISSINGNESS_V1":
    case "ADR011_X02_FLEET_AVAILABILITY_LAYOUT_V1":
      exactFixtureKeys(value, [], profile);
      return;
    case "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1":
    case "ADR007_INVALID_DISPOSITION_V1":
      exactFixtureKeys(value, ["nonterminal_states", "terminal_states"], profile);
      requireStringArray(value.nonterminal_states, profile);
      requireStringArray(value.terminal_states, profile);
      return;
    case "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "expected_route",
        "extension_assessor_principal_id",
        "extension_receiver_principal_id",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.expected_route, profile);
      requireFixtureString(value.extension_assessor_principal_id, profile);
      requireFixtureString(value.extension_receiver_principal_id, profile);
      return;
    case "ADR008_GALADRIEL_POLICY_INJECTION_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "extension_assessor_principal_id",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.extension_assessor_principal_id, profile);
      return;
    case "ADR009_SECURITY_STATE_PROJECTION_V1":
    case "ADR009_INVALID_SECURITY_STATE_V1": {
      exactFixtureKeys(value, [
        "authenticated_authority_realm",
        "maximum_security_epoch",
        "required_key_algorithm",
        "required_profile",
      ], profile);
      const realm = requiredObject(value.authenticated_authority_realm, `${profile}.authenticated_authority_realm`);
      exactFixtureKeys(realm, [...AUTHORITY_REALM_FIELDS], `${profile}.authenticated_authority_realm`);
      for (const key of AUTHORITY_REALM_FIELDS) requireFixtureString(realm[key], profile);
      requireFixtureInteger(value.maximum_security_epoch, profile, true);
      requireFixtureLiteral(value.required_key_algorithm, "Ed25519", profile);
      requireFixtureLiteral(value.required_profile, "ncp-production-ingress-v1", profile);
      return;
    }
    case "ADR010_ACTION_QOS_PROFILE_V1":
    case "ADR010_INVALID_ACTION_QOS_PROFILE_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "expected_route",
        "maximum_capacity_per_stream",
        "required_fail_safe_priority",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.expected_route, profile);
      requireFixtureInteger(value.maximum_capacity_per_stream, profile, true);
      requireStringArray(value.required_fail_safe_priority, profile);
      return;
    case "ADR011_REGISTERED_HALDIR_INTENT_ENVELOPE_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "evaluation_tick_ns",
        "expected_audience_principal_id",
        "expected_extension_id",
        "expected_freshness_grant",
        "expected_intent_sequence",
        "expected_intent_stream_epoch",
        "expected_logical_session_id",
        "expected_manifest_digest",
        "expected_plant_session_generation",
        "expected_plant_session_kind",
        "expected_producer_principal_id",
        "expected_requested_effect",
        "expected_route",
        "expected_schema_version",
        "expected_semantic_encoding",
        "expected_signature_coverage",
        "expected_source",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureInteger(value.evaluation_tick_ns, profile, true);
      requireFixtureInteger(value.expected_intent_sequence, profile, true);
      for (const key of [
        "expected_audience_principal_id",
        "expected_extension_id",
        "expected_intent_stream_epoch",
        "expected_logical_session_id",
        "expected_manifest_digest",
        "expected_plant_session_generation",
        "expected_plant_session_kind",
        "expected_producer_principal_id",
        "expected_requested_effect",
        "expected_route",
        "expected_schema_version",
        "expected_semantic_encoding",
      ] as const) requireFixtureString(value[key], profile);
      {
        const grant = requiredObject(
          value.expected_freshness_grant,
          `${profile}.expected_freshness_grant`,
        );
        exactFixtureKeys(grant, [
          "allowed_requested_effects",
          "clock_incarnation",
          "digest",
          "first_slot",
          "installation_receipt_digest",
          "issue_tick_ns",
          "last_slot_exclusive",
          "maximum_not_after_tick_ns",
          "maximum_requested_validity_ms",
        ], `${profile}.expected_freshness_grant`);
        for (const key of ["clock_incarnation", "digest", "installation_receipt_digest"] as const) {
          requireFixtureString(grant[key], profile);
        }
        for (const key of [
          "first_slot",
          "issue_tick_ns",
          "last_slot_exclusive",
          "maximum_not_after_tick_ns",
          "maximum_requested_validity_ms",
        ] as const) requireFixtureInteger(grant[key], profile, true);
        requireStringArray(grant.allowed_requested_effects, profile);
      }
      requireStringArray(value.expected_signature_coverage, profile);
      {
        const source = requiredObject(value.expected_source, `${profile}.expected_source`);
        exactFixtureKeys(source, ["kind", "reason"], `${profile}.expected_source`);
        requireFixtureString(source.kind, profile);
        requireFixtureString(source.reason, profile);
      }
      return;
    case "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "enrolled_body_principal_id",
        "gated_commander_principal_id",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.enrolled_body_principal_id, profile);
      requireFixtureString(value.gated_commander_principal_id, profile);
      return;
    case "ADR011_EFFECT_PATH_FENCING_PROJECTION_V1":
      exactFixtureKeys(value, [], profile);
      return;
    case "ADR011_PREPARED_FRAME_PUBLISHER_BOUNDARY_V1":
      exactFixtureKeys(value, [], profile);
      return;
    default:
      throw new SemanticConfigurationError(`fixture has unknown profile ${profile}`);
  }
}

const REALM_KEY_FIELDS = ["server_authority_principal_id", "stable_realm_id"] as const;
const AUTHORITY_REALM_FIELDS = ["server_authority_principal", "stable_realm_id"] as const;

function validateRealmFixture(value: JsonValue | undefined, label: string): void {
  const realm = requiredObject(value, `${label}.authenticated_realm_key`);
  exactFixtureKeys(realm, [...REALM_KEY_FIELDS], `${label}.authenticated_realm_key`);
  for (const key of REALM_KEY_FIELDS) requireFixtureString(realm[key], label);
}

function validateAlgorithm(
  actual: JsonValue | undefined,
  expected: string,
  diagnostics: string[],
): void {
  if (actual === undefined) diagnostics.push("ALGORITHM_LABEL_REQUIRED");
  else if (actual !== expected) diagnostics.push("ALGORITHM_LABEL_FORBIDDEN");
}

function isRealmKey(value: JsonObject | undefined): value is JsonObject {
  return value !== undefined && REALM_KEY_FIELDS.every((key) => nonemptyString(value[key]) !== undefined);
}

function isAuthorityRealm(value: JsonObject | undefined): value is JsonObject {
  return value !== undefined && AUTHORITY_REALM_FIELDS.every((key) => nonemptyString(value[key]) !== undefined);
}

function objectsEqualOn(
  left: JsonObject,
  right: JsonObject,
  fields: readonly string[],
): boolean {
  return fields.every((field) => left[field] === right[field]);
}

function objectsExactlyEqualOn(
  left: JsonObject,
  right: JsonObject,
  fields: readonly string[],
): boolean {
  return (
    Object.keys(left).length === fields.length &&
    Object.keys(right).length === fields.length &&
    objectsEqualOn(left, right, fields)
  );
}

function arraysEqual(left: readonly JsonValue[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function fixtureObject(fixture: JsonValue, key: string): JsonObject {
  return requiredObject(requiredObject(fixture, "fixture")[key], `fixture.${key}`);
}

function fixtureString(fixture: JsonValue, key: string): string {
  const value = requiredObject(fixture, "fixture")[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new SemanticConfigurationError(`fixture.${key} is not a non-empty string`);
  }
  return value;
}

function fixtureStringArray(fixture: JsonValue, key: string): string[] {
  const value = requiredObject(fixture, "fixture")[key];
  if (!Array.isArray(value) || !value.every((entry) => typeof entry === "string" && entry.length > 0)) {
    throw new SemanticConfigurationError(`fixture.${key} is not a string array`);
  }
  return value as string[];
}

function fixtureInteger(fixture: JsonValue, key: string): number {
  const value = requiredObject(fixture, "fixture")[key];
  if (typeof value !== "number" || !Number.isSafeInteger(value)) {
    throw new SemanticConfigurationError(`fixture.${key} is not a safe integer`);
  }
  return value;
}

function fixtureBoolean(fixture: JsonValue, key: string): boolean {
  const value = requiredObject(fixture, "fixture")[key];
  if (typeof value !== "boolean") {
    throw new SemanticConfigurationError(`fixture.${key} is not Boolean`);
  }
  return value;
}

function exactFixtureKeys(value: JsonObject, expected: readonly string[], label: string): void {
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    throw new SemanticConfigurationError(`${label} fixture has an unknown or missing member`);
  }
}

function requireFixtureString(value: JsonValue | undefined, label: string): void {
  if (typeof value !== "string" || value.length === 0) {
    throw new SemanticConfigurationError(`${label} fixture requires a non-empty string`);
  }
}

function requireFixtureLiteral(
  value: JsonValue | undefined,
  expected: JsonValue,
  label: string,
): void {
  if (value !== expected) {
    throw new SemanticConfigurationError(`${label} fixture contains an unexpected closed value`);
  }
}

function requireFixtureInteger(
  value: JsonValue | undefined,
  label: string,
  positive: boolean,
): void {
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    (positive && value <= 0)
  ) {
    throw new SemanticConfigurationError(`${label} fixture requires a bounded safe integer`);
  }
}

function requireStringArray(value: JsonValue | undefined, label: string): void {
  if (
    !Array.isArray(value) ||
    !value.every((entry) => typeof entry === "string" && entry.length > 0) ||
    new Set(value).size !== value.length
  ) {
    throw new SemanticConfigurationError(`${label} fixture requires a unique string array`);
  }
}

function requiredObject(value: JsonValue | undefined, label: string): JsonObject {
  const object = asObject(value);
  if (object === undefined) throw new SemanticConfigurationError(`${label} is not an object`);
  return object;
}

function asObject(value: JsonValue | undefined): JsonObject | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as JsonObject)
    : undefined;
}

function asArray(value: JsonValue | undefined): JsonValue[] | undefined {
  return Array.isArray(value) ? value : undefined;
}

function nonemptyString(value: JsonValue | undefined): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function safeInteger(value: JsonValue | undefined): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) ? value : undefined;
}

function isPrefixedDigest(value: JsonValue | undefined): boolean {
  return typeof value === "string" && SHA256_PREFIXED.test(value);
}

function validateTypedDigest(
  value: JsonValue | undefined,
  expectedDomain: string,
  diagnostics: string[],
): void {
  const identity = asObject(value);
  if (
    identity?.algorithm !== "sha256" ||
    identity.domain !== expectedDomain ||
    identity.encoding !== "lowercase_hex" ||
    typeof identity.digest !== "string" ||
    !HEX_256.test(identity.digest)
  ) {
    diagnostics.push("DIGEST_ENCODING_INVALID");
  }
}

class Base64UrlError extends Error {
  constructor() {
    super("invalid unpadded base64url");
    this.name = "Base64UrlError";
  }
}

function decodeBase64Url(value: string, maximumDecodedBytes: number): Uint8Array {
  if (!Number.isSafeInteger(maximumDecodedBytes) || maximumDecodedBytes < 0) {
    throw new Base64UrlError();
  }
  const outputLength = base64UrlDecodedLength(value);
  if (outputLength > maximumDecodedBytes) throw new Base64UrlError();
  const output = new Uint8Array(outputLength);
  let accumulator = 0;
  let bits = 0;
  let outputIndex = 0;
  for (let index = 0; index < value.length; index += 1) {
    const digit = base64UrlDigit(value.charCodeAt(index));
    if (digit === undefined) throw new Base64UrlError();
    accumulator = accumulator * 64 + digit;
    bits += 6;
    while (bits >= 8) {
      bits -= 8;
      output[outputIndex] = Math.floor(accumulator / 2 ** bits) & 0xff;
      outputIndex += 1;
      accumulator %= 2 ** bits;
    }
  }
  if (accumulator !== 0 || outputIndex !== outputLength) throw new Base64UrlError();
  return output;
}

function base64UrlDecodedLength(value: string): number {
  const remainder = value.length % 4;
  if (remainder === 1) throw new Base64UrlError();
  let finalDigit = 0;
  for (let index = 0; index < value.length; index += 1) {
    const digit = base64UrlDigit(value.charCodeAt(index));
    if (digit === undefined) throw new Base64UrlError();
    finalDigit = digit;
  }
  if (
    (remainder === 2 && (finalDigit & 0x0f) !== 0) ||
    (remainder === 3 && (finalDigit & 0x03) !== 0)
  ) {
    throw new Base64UrlError();
  }
  const fullGroups = Math.floor(value.length / 4);
  return fullGroups * 3 + (remainder === 0 ? 0 : remainder - 1);
}

function base64UrlDigit(code: number): number | undefined {
  if (code >= 0x41 && code <= 0x5a) return code - 0x41;
  if (code >= 0x61 && code <= 0x7a) return code - 0x61 + 26;
  if (code >= 0x30 && code <= 0x39) return code - 0x30 + 52;
  if (code === 0x2d) return 62;
  if (code === 0x5f) return 63;
  return undefined;
}
