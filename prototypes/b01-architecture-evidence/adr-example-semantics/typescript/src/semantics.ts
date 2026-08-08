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
  "docs/adr/0005-declared-stream-lifecycle.md#1":
    "ADR005_DECLARE_STREAM_EXCERPT_V1",
  "docs/adr/0005-declared-stream-lifecycle.md#2":
    "ADR005_UNDECLARED_FRAME_V1",
  "docs/adr/0006-body-issued-authority-and-time.md#1":
    "ADR006_BODY_LEASE_EXCERPT_V1",
  "docs/adr/0006-body-issued-authority-and-time.md#2":
    "ADR006_STALE_SELF_ISSUED_LEASE_V1",
  "docs/adr/0007-command-disposition-journal.md#1":
    "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1",
  "docs/adr/0007-command-disposition-journal.md#2":
    "ADR007_INVALID_DISPOSITION_V1",
  "docs/adr/0008-extension-namespace-and-galadriel-separation.md#1":
    "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1",
  "docs/adr/0008-extension-namespace-and-galadriel-separation.md#2":
    "ADR008_GALADRIEL_POLICY_INJECTION_V1",
  "docs/adr/0009-security-state-rotation-and-revocation.md#1":
    "ADR009_SECURITY_STATE_PROJECTION_V1",
  "docs/adr/0009-security-state-rotation-and-revocation.md#2":
    "ADR009_INVALID_SECURITY_STATE_V1",
  "docs/adr/0010-plane-qos-retention-and-overload.md#1":
    "ADR010_ACTION_QOS_PROFILE_V1",
  "docs/adr/0010-plane-qos-retention-and-overload.md#2":
    "ADR010_INVALID_ACTION_QOS_PROFILE_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#1":
    "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1",
  "docs/adr/0011-ecosystem-topology-and-handover.md#2":
    "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1",
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
    case "ADR005_DECLARE_STREAM_EXCERPT_V1":
      adr005Declaration(document, input.fixture, diagnostics);
      break;
    case "ADR005_UNDECLARED_FRAME_V1":
      adr005Undeclared(document, input.fixture, diagnostics);
      break;
    case "ADR006_BODY_LEASE_EXCERPT_V1":
    case "ADR006_STALE_SELF_ISSUED_LEASE_V1":
      adr006(document, input.fixture, diagnostics);
      break;
    case "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1":
    case "ADR007_INVALID_DISPOSITION_V1":
      adr007(document, input.fixture, diagnostics);
      break;
    case "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1":
      adr008Assessment(document, input.fixture, diagnostics);
      break;
    case "ADR008_GALADRIEL_POLICY_INJECTION_V1":
      adr008Policy(document, input.fixture, diagnostics);
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
    case "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1":
      adr011Intent(document, input.fixture, diagnostics);
      break;
    case "ADR011_COMMAND_IDENTITY_AUTHORITY_SEPARATION_V1":
      adr011Command(document, input.fixture, diagnostics);
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
          input.profile === "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1"
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
  if (document.ncp_version !== fixtureString(fixture, "expected_ncp_version")) {
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
  if (document.wire_version !== fixtureString(fixture, "expected_wire_version")) {
    diagnostics.push("WIRE_VERSION_MISMATCH");
  }
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm)) {
    diagnostics.push("AUTHORITY_REALM_KEY_MISSING");
  } else if (!objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_KEY_MISMATCH");
  }
  if (Object.hasOwn(document, "contract_hash")) {
    diagnostics.push("COMPACT_HASH_NOT_COMPATIBILITY_IDENTITY");
  }
  if (document.stable_core_digest === undefined || document.stable_core_digest === null) {
    diagnostics.push("STABLE_CORE_DIGEST_MISSING_OR_NULL");
  } else if (!isPrefixedDigest(document.stable_core_digest)) {
    diagnostics.push("STABLE_CORE_DIGEST_INVALID");
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
        strictJsonParse(decodeBase64Url(protectedValue), HEADER_LIMITS),
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
      signatureLength = decodeBase64Url(document.signature).byteLength;
    } catch (error) {
      if (!(error instanceof Base64UrlError)) throw error;
    }
  }
  if (signatureLength !== expectedSignatureBytes) {
    diagnostics.push("SIGNATURE_LENGTH_INVALID");
  } else {
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

function adr005Declaration(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  if (document.ncp_version !== "1.0") diagnostics.push("NCP_VERSION_MISMATCH");
  if (document.kind !== "declare_stream") diagnostics.push("MESSAGE_KIND_MISMATCH");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm)) {
    diagnostics.push("REALM_REQUIRED");
  } else {
    const expected = fixtureObject(fixture, "authenticated_realm_key");
    if (!objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS)) {
      diagnostics.push("REALM_ROUTE_MISMATCH");
    }
    validateRouteRealm(document.route, realm, diagnostics);
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
  if (!isRealmKey(realm)) {
    diagnostics.push("REALM_REQUIRED");
  } else {
    const expected = fixtureObject(fixture, "authenticated_realm_key");
    if (!objectsExactlyEqualOn(realm, expected, REALM_KEY_FIELDS)) {
      diagnostics.push("REALM_ROUTE_MISMATCH");
    }
    validateRouteRealm(document.route, realm, diagnostics);
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
      if (assessment?.kind !== "EVALUATED_DEFAULT_REPORT") {
        diagnostics.push("ASSESSMENT_MAGNITUDE_REQUIRED");
        continue;
      }
      validateTypedDigest(
        assessment.assessment_binding_identity,
        "galadriel-assessment-binding-v2",
        diagnostics,
      );
      const report = asObject(assessment.report_evidence);
      const verdict = report === undefined ? undefined : asObject(report.verdict);
      if (
        verdict?.verdict !== "attributed_inconsistency" ||
        nonemptyString(verdict?.magnitude) === undefined
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
  if (nonemptyString(document.route) === undefined) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  } else {
    validateRouteRealm(document.route, realm, diagnostics);
  }
}

function adr011Intent(
  document: JsonObject,
  fixture: JsonValue,
  diagnostics: string[],
): void {
  const expectedRealm = fixtureObject(fixture, "authenticated_realm_key");
  const realm = asObject(document.authority_realm_key);
  if (!isRealmKey(realm) || !objectsExactlyEqualOn(realm, expectedRealm, REALM_KEY_FIELDS)) {
    diagnostics.push("AUTHORITY_REALM_MISMATCH");
  }
  if (document.audience !== fixtureString(fixture, "expected_audience")) {
    diagnostics.push("INTENT_AUDIENCE_MISMATCH");
  }
  if (document.issuer !== fixtureString(fixture, "expected_issuer")) {
    diagnostics.push("INTENT_ISSUER_MISMATCH");
  }
  const expires = safeInteger(document.expires_at_utc_ms);
  if (expires === undefined || expires <= fixtureInteger(fixture, "evaluation_utc_ms")) {
    diagnostics.push("INTENT_EXPIRED");
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
      exactFixtureKeys(value, ["authenticated_realm_key", "digest_algorithm", "expected_wire_version"], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureLiteral(value.digest_algorithm, "sha256", profile);
      requireFixtureLiteral(value.expected_wire_version, "1.0", profile);
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
    case "ADR005_UNDECLARED_FRAME_V1":
      exactFixtureKeys(value, [
        "authenticated_publisher_principal_id",
        "authenticated_realm_key",
        "live_declaration_epoch_ids",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.authenticated_publisher_principal_id, profile);
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
    case "ADR007_RECEIVED_DISPOSITION_EXCERPT_V1":
    case "ADR007_INVALID_DISPOSITION_V1":
      exactFixtureKeys(value, ["nonterminal_states", "terminal_states"], profile);
      requireStringArray(value.nonterminal_states, profile);
      requireStringArray(value.terminal_states, profile);
      return;
    case "ADR008_GALADRIEL_ASSESSMENT_ENVELOPE_V1":
    case "ADR008_GALADRIEL_POLICY_INJECTION_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "extension_assessor_principal_id",
        "extension_receiver_principal_id",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureString(value.extension_assessor_principal_id, profile);
      requireFixtureString(value.extension_receiver_principal_id, profile);
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
        "maximum_capacity_per_stream",
        "required_fail_safe_priority",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureInteger(value.maximum_capacity_per_stream, profile, true);
      requireStringArray(value.required_fail_safe_priority, profile);
      return;
    case "ADR011_GATED_INTENT_CORRELATION_EXCERPT_V1":
      exactFixtureKeys(value, [
        "authenticated_realm_key",
        "evaluation_utc_ms",
        "expected_audience",
        "expected_issuer",
        "native_gated_intent_version",
      ], profile);
      validateRealmFixture(value.authenticated_realm_key, profile);
      requireFixtureInteger(value.evaluation_utc_ms, profile, true);
      requireFixtureInteger(value.native_gated_intent_version, profile, true);
      requireFixtureString(value.expected_audience, profile);
      requireFixtureString(value.expected_issuer, profile);
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

function validateRouteRealm(
  routeValue: JsonValue | undefined,
  realm: JsonObject | undefined,
  diagnostics: string[],
): void {
  const route = nonemptyString(routeValue);
  const stableRealm = realm === undefined ? undefined : nonemptyString(realm.stable_realm_id);
  if (route === undefined || stableRealm === undefined || route.split("/")[0] !== stableRealm) {
    diagnostics.push("REALM_ROUTE_MISMATCH");
  }
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

class Base64UrlError extends Error {
  constructor() {
    super("invalid unpadded base64url");
    this.name = "Base64UrlError";
  }
}

function decodeBase64Url(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]*$/.test(value) || value.length % 4 === 1) {
    throw new Base64UrlError();
  }
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  const outputLength = Math.floor((value.length * 6) / 8);
  const output = new Uint8Array(outputLength);
  let accumulator = 0;
  let bits = 0;
  let outputIndex = 0;
  for (const character of value) {
    const digit = alphabet.indexOf(character);
    if (digit < 0) throw new Base64UrlError();
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
