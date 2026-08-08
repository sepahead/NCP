import type { JsonValue } from "./strict-json.ts";

export type Scope =
  | "AUTHENTICATED_WIRE_OBJECT"
  | "DECODED_HEADER_FRAGMENT"
  | "NON_NCP_INTENT_CORRELATION_FRAGMENT"
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
  readonly path: string;
  readonly jsonFenceOrdinal: number;
  readonly adrByteLength: number;
  readonly adrSha256: string;
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
const SOURCE_PATH = /^docs\/adr\/(00(0[1-9]|1[01]))-[a-z0-9-]+\.md$/;

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
  "sha256",
] as const;

const PROJECTION_MEMBERS = [
  "schema",
  "candidate",
  "wire_version",
  "review_policy",
  "decisions",
] as const;

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
  "adr_byte_length",
  "adr_sha256",
  "fence_byte_length",
  "fence_sha256",
  "json_fence_ordinal",
  "path",
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
  "NON_NCP_INTENT_CORRELATION_FRAGMENT",
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
  maximumJsonDepth: 32,
  maximumJsonNodes: 100_000,
  maximumObjectMembers: 4_096,
  maximumArrayItems: 4_096,
  maximumKeyUtf8Bytes: 256,
  maximumStringUtf8Bytes: 65_536,
  maximumTotalStringUtf8Bytes: 131_072,
  maximumIntegerCharacters: 32,
  expectedCaseCount: 22,
  expectedMutationCount: 90,
  minimumMutationsPerCase: 2,
  maximumMutationsPerCase: 16,
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
    effect: "NON_ACCEPTING_EXACT_SUBJECT_BINDING_ONLY",
    json: value,
  };
}

function validateSourceBinding(value: JsonObject): void {
  exactKeys(value, SOURCE_BINDING_KEYS, "source_binding");
  exactString(value, "fence_language", "json", "source_binding");
  exactString(
    value,
    "fence_capture",
    "content_between_exact_json_fence_markers_excluding_terminal_newline",
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
  const mutationIds = mutations.map((mutation) => mutation.id);
  requireUnique(mutationIds, `${label}.mutation ids`);
  for (const mutation of mutations) {
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
  const path = requiredString(value.path, `${label}.path`);
  const match = SOURCE_PATH.exec(path);
  if (match?.[2] === undefined) fail(`${label}.path is outside the ADR source allowlist`);
  const number = Number(match[2]);
  const adr = requiredString(value.adr, `${label}.adr`);
  if (adr !== `ADR-${String(number).padStart(3, "0")}`) {
    fail(`${label}.adr does not agree with its path`);
  }
  const jsonFenceOrdinal = positiveInteger(
    value.json_fence_ordinal,
    `${label}.json_fence_ordinal`,
  );
  const adrByteLength = positiveInteger(value.adr_byte_length, `${label}.adr_byte_length`);
  if (adrByteLength > limits.maximumAdrBytes) fail(`${label}.adr_byte_length exceeds its bound`);
  const fenceByteLength = positiveInteger(
    value.fence_byte_length,
    `${label}.fence_byte_length`,
  );
  if (fenceByteLength > limits.maximumJsonFenceBytes) {
    fail(`${label}.fence_byte_length exceeds its bound`);
  }
  const adrSha256 = sha256String(value.adr_sha256, `${label}.adr_sha256`);
  const fenceSha256 = sha256String(value.fence_sha256, `${label}.fence_sha256`);
  return {
    adr,
    path,
    jsonFenceOrdinal,
    adrByteLength,
    adrSha256,
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
  return {
    id: identifier(object.id, `${label}.id`),
    purpose: requiredString(object.purpose, `${label}.purpose`),
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
  if (!path.startsWith("/") || path.length > 2_048) {
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
    cases.map((entry) => `${entry.source.path}#${entry.source.jsonFenceOrdinal}`),
    "source fence bindings",
  );
  let previous = "";
  const adrBindings = new Map<string, { bytes: number; sha256: string }>();
  for (const entry of cases) {
    const orderKey = `${entry.source.path}#${String(entry.source.jsonFenceOrdinal).padStart(8, "0")}`;
    if (orderKey <= previous) fail("cases must be ordered by source path and fence ordinal");
    previous = orderKey;
    const known = adrBindings.get(entry.source.path);
    if (
      known !== undefined &&
      (known.bytes !== entry.source.adrByteLength || known.sha256 !== entry.source.adrSha256)
    ) {
      fail(`source bindings disagree for ${entry.source.path}`);
    }
    adrBindings.set(entry.source.path, {
      bytes: entry.source.adrByteLength,
      sha256: entry.source.adrSha256,
    });
  }
  const aggregate = [...adrBindings.values()].reduce((total, binding) => total + binding.bytes, 0);
  if (aggregate > limits.maximumAggregateAdrBytes) {
    fail("aggregate unique ADR byte length exceeds its bound");
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
  if (!IDENTIFIER.test(candidate)) fail(`${label} is not a lowercase versioned identifier`);
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
