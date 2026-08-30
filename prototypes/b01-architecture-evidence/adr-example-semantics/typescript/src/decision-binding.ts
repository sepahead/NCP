import { canonicalJsonBytes, canonicalJsonText } from "./canonical-json.ts";
import type { CorpusLimits, DecisionSetBinding } from "./corpus.ts";
import { readBoundedRepositoryFile, sha256 } from "./file-io.ts";
import { strictJsonParse, type JsonLimits, type JsonValue } from "./strict-json.ts";

type JsonObject = { [key: string]: JsonValue };

const DECISION_SOURCE_PATH =
  /^docs\/adr\/(000[1-9]|001[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md$/;
const MODULE_SOURCE_PATH =
  /^docs\/adr\/modules\/adr-(00[1-9]|01[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md$/;
const GIT_OBJECT = /^[0-9a-f]{40}$/;
const SHA256 = /^[0-9a-f]{64}$/;
const REVIEW_PACKET_LIFECYCLE_SCHEMA = "ncp.b01-review-packet-lifecycle.v1";
const REVIEW_SUBJECT_SCHEMA = "ncp.b01-review-subject.v1";
const REVIEW_SUBJECT_DECISION_SOURCE_PATH =
  "docs/adr/decision-registry.source.v1.json";
const MAXIMUM_REVIEW_SUBJECT_DECISION_SOURCE_BYTES = 2_097_152;
const REVIEW_SUBJECT_MEMBERS = [
  "schema",
  "state",
  "normative",
  "claim_boundary",
  "promotion_blocked",
  "decision_set",
  "review_policy",
  "source",
  "decisions",
] as const;
const REVIEW_SUBJECT_SOURCE_MEMBERS = ["commit", "tree", "decision_source"] as const;
const REVIEW_SUBJECT_DECISION_MEMBERS = [
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
const ADR_SOURCE_SET_SCHEMA = "ncp.b01-adr-source-set.v1";
const ADR_SOURCE_SET_DIGEST_ALGORITHM =
  "sha256(domain || u64be(projection_bytes) || projection)";
const ADR_SOURCE_SET_DOMAIN_HEX =
  "6e63702e6230312d6164722d736f757263652d7365742e763100";
const MAXIMUM_ADR_MODULES_PER_DECISION = 8;
const EXPECTED_DECISION_IDS = new Set(
  Array.from({ length: 11 }, (_, index) => `ADR-${String(index + 1).padStart(3, "0")}`),
);

export interface DecisionSourceBinding {
  readonly path: string;
  readonly byteLength: number;
  readonly sha256: string;
}

export class DecisionBindingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "DecisionBindingError";
  }
}

export async function verifyDecisionSetBinding(
  repositoryRoot: string,
  binding: DecisionSetBinding,
  limits: CorpusLimits,
): Promise<ReadonlyMap<string, DecisionSourceBinding>> {
  const registryBytes = await readBoundedRepositoryFile(
    repositoryRoot,
    binding.registryPath,
    limits.maximumCorpusBytes,
    "decision registry",
  );
  const registry = requiredObject(
    strictJsonParse(registryBytes, jsonLimits(limits, limits.maximumCorpusBytes)),
    "decision registry",
  );
  if (registry.normative !== false || registry.promotion_blocked !== true) {
    throw new DecisionBindingError(
      "decision registry must be explicitly non-normative and promotion-blocked",
    );
  }
  const registeredIdentity = decisionIdentity(binding);
  const registryDecisionSet = requiredObject(
    registry.decision_set,
    "decision registry decision_set",
  );
  requireExactJsonValue(
    registryDecisionSet,
    registeredIdentity,
    "decision registry decision_set",
  );
  validateReviewPacketBinding(registry, registeredIdentity);
  await verifyClosureArtifacts(repositoryRoot, binding, limits);

  const decisions = requiredArray(registry.decisions, "decision registry decisions");
  const ids = new Set<string>();
  const sources = new Map<string, DecisionSourceBinding>();
  const allSources: DecisionSourceBinding[] = [];
  const projectedDecisions = decisions.map((entry, index) => {
    const decision = requiredObject(entry, `decision registry decisions[${index}]`);
    const projection: JsonObject = Object.create(null) as JsonObject;
    for (const member of binding.decisionMembers) {
      if (!Object.hasOwn(decision, member)) {
        throw new DecisionBindingError(
          `decision registry decisions[${index}] lacks projected member ${member}`,
        );
      }
      projection[member] = decision[member] as JsonValue;
    }
    const id = requiredString(projection.id, `decision registry decisions[${index}].id`);
    if (!EXPECTED_DECISION_IDS.has(id) || ids.has(id)) {
      throw new DecisionBindingError(
        `decision registry has an unexpected or duplicate decision id ${JSON.stringify(id)}`,
      );
    }
    ids.add(id);
    const path = requiredDecisionPath(
      projection.path,
      id,
      `decision registry decisions[${index}].path`,
    );
    const byteLength = requiredPositiveInteger(
      projection.bytes,
      `decision registry decisions[${index}].bytes`,
    );
    if (byteLength > limits.maximumAdrBytes) {
      throw new DecisionBindingError(
        `decision registry source ${id} exceeds ${limits.maximumAdrBytes} bytes`,
      );
    }
    const contentSha256 = requiredString(
      projection.content_sha256,
      `decision registry decisions[${index}].content_sha256`,
    );
    if (!SHA256.test(contentSha256)) {
      throw new DecisionBindingError(
        `decision registry source ${id} SHA-256 is not lowercase hexadecimal`,
      );
    }
    sources.set(id, { path, byteLength, sha256: contentSha256 });
    validateSourceSet(
      projection.source_set,
      projection.module_paths,
      id,
      path,
      byteLength,
      contentSha256,
      limits,
      allSources,
    );
    return projection;
  });
  if (
    ids.size !== EXPECTED_DECISION_IDS.size ||
    [...EXPECTED_DECISION_IDS].some((id) => !ids.has(id))
  ) {
    throw new DecisionBindingError(
      "decision registry must cover exactly ADR-001 through ADR-011",
    );
  }

  for (const member of ["candidate", "wire_version", "review_policy"] as const) {
    if (!Object.hasOwn(registry, member)) {
      throw new DecisionBindingError(`decision registry lacks projected member ${member}`);
    }
  }
  const projection: JsonObject = Object.create(null) as JsonObject;
  projection.schema = binding.schema;
  projection.candidate = registry.candidate as JsonValue;
  projection.wire_version = registry.wire_version as JsonValue;
  projection.review_policy = registry.review_policy as JsonValue;
  projection.semantic_closure = registryDecisionSet.semantic_closure as JsonValue;
  projection.decisions = projectedDecisions;

  if (
    Object.keys(projection).length !== binding.projectionMembers.length ||
    binding.projectionMembers.some((member) => !Object.hasOwn(projection, member))
  ) {
    throw new DecisionBindingError("decision-set projection members are incomplete");
  }
  const projectionBytes = canonicalJsonBytes(projection);
  if (projectionBytes.byteLength !== binding.projectionByteLength) {
    throw new DecisionBindingError(
      `decision-set projection has ${projectionBytes.byteLength} bytes; expected ${binding.projectionByteLength}`,
    );
  }
  if (sha256(projectionBytes) !== binding.projectionSha256) {
    throw new DecisionBindingError("decision-set projection SHA-256 does not match its binding");
  }
  if (domainSeparatedSha256(binding.domainHex, projectionBytes) !== binding.sha256) {
    throw new DecisionBindingError("domain-separated decision-set SHA-256 does not match");
  }
  await verifyProjectedSources(repositoryRoot, allSources, limits.maximumAggregateAdrBytes);
  return sources;
}

function validateSourceSet(
  value: JsonValue | undefined,
  modulePathsValue: JsonValue | undefined,
  decisionId: string,
  mainPath: string,
  mainByteLength: number,
  mainSha256: string,
  limits: CorpusLimits,
  allSources: DecisionSourceBinding[],
): void {
  const sourceSet = requiredObject(value, `${decisionId} source_set`);
  const entries = requiredArray(sourceSet.sources, `${decisionId} source_set.sources`);
  const modulePaths = requiredArray(modulePathsValue, `${decisionId} module_paths`);
  const expectedSourceSetKeys = [
    "decision_id",
    "digest_algorithm",
    "domain_hex",
    "schema",
    "sha256",
    "sources",
  ];
  if (
    canonicalJsonText(Object.keys(sourceSet).sort()) !== canonicalJsonText(expectedSourceSetKeys) ||
    sourceSet.schema !== ADR_SOURCE_SET_SCHEMA ||
    sourceSet.decision_id !== decisionId ||
    sourceSet.digest_algorithm !== ADR_SOURCE_SET_DIGEST_ALGORITHM ||
    sourceSet.domain_hex !== ADR_SOURCE_SET_DOMAIN_HEX ||
    entries.length < 1 ||
    entries.length > MAXIMUM_ADR_MODULES_PER_DECISION + 1 ||
    modulePaths.length + 1 !== entries.length
  ) {
    throw new DecisionBindingError(`${decisionId} source_set has an invalid identity or size`);
  }
  const decisionNumber = Number(decisionId.slice(4));
  if (!Number.isSafeInteger(decisionNumber) || decisionNumber < 1 || decisionNumber > 11) {
    throw new DecisionBindingError(`${decisionId} source_set has an invalid decision id`);
  }
  const paths = new Set<string>();
  for (const [index, rawEntry] of entries.entries()) {
    const entry = requiredObject(rawEntry, `${decisionId} source_set.sources[${index}]`);
    if (
      Object.keys(entry).length !== 4 ||
      entry.kind !== (index === 0 ? "main" : "module")
    ) {
      throw new DecisionBindingError(`${decisionId} source_set entry has an invalid shape`);
    }
    const path = requiredString(entry.path, `${decisionId} source_set path`);
    const byteLength = requiredPositiveInteger(
      entry.bytes,
      `${decisionId} source_set bytes`,
    );
    const digest = requiredString(entry.sha256, `${decisionId} source_set sha256`);
    if (byteLength > limits.maximumAdrBytes || !SHA256.test(digest) || paths.has(path)) {
      throw new DecisionBindingError(`${decisionId} source_set path or digest is invalid`);
    }
    paths.add(path);
    if (index === 0) {
      if (
        requiredDecisionPath(path, decisionId, `${decisionId} source_set main path`) !==
          mainPath ||
        byteLength !== mainByteLength ||
        digest !== mainSha256
      ) {
        throw new DecisionBindingError(`${decisionId} source_set main entry differs`);
      }
    } else if (
      requiredModulePath(path, decisionId, `${decisionId} source_set module path`) !==
      modulePaths[index - 1]
    ) {
      throw new DecisionBindingError(`${decisionId} source_set module entry differs`);
    }
    allSources.push({ path, byteLength, sha256: digest });
  }
  const sourceSetProjection: JsonObject = Object.create(null) as JsonObject;
  sourceSetProjection.schema = ADR_SOURCE_SET_SCHEMA;
  sourceSetProjection.decision_id = decisionId;
  sourceSetProjection.sources = entries;
  const sourceSetDigest = requiredString(sourceSet.sha256, `${decisionId} source_set sha256`);
  if (
    !SHA256.test(sourceSetDigest) ||
    domainSeparatedSha256(
      ADR_SOURCE_SET_DOMAIN_HEX,
      canonicalJsonBytes(sourceSetProjection),
    ) !== sourceSetDigest
  ) {
    throw new DecisionBindingError(`${decisionId} source_set commitment does not recompute`);
  }
}

async function verifyClosureArtifacts(
  repositoryRoot: string,
  binding: DecisionSetBinding,
  limits: CorpusLimits,
): Promise<void> {
  for (const member of ["source", "json_schema"] as const) {
    const identity = requiredObject(
      binding.semanticClosure[member],
      `semantic closure ${member}`,
    );
    const source: DecisionSourceBinding = {
      path: requiredString(identity.path, `semantic closure ${member} path`),
      byteLength: requiredPositiveInteger(identity.bytes, `semantic closure ${member} bytes`),
      sha256: requiredString(identity.sha256, `semantic closure ${member} sha256`),
    };
    if (source.path === binding.registryPath) {
      throw new DecisionBindingError(
        `semantic closure ${member} cannot alias the decision registry`,
      );
    }
    if (!SHA256.test(source.sha256) || source.byteLength > limits.maximumCorpusBytes) {
      throw new DecisionBindingError(`semantic closure ${member} identity is invalid`);
    }
    await verifyProjectedSource(repositoryRoot, source);
  }
}

async function verifyProjectedSources(
  repositoryRoot: string,
  sources: readonly DecisionSourceBinding[],
  maximumAggregateBytes: number,
): Promise<void> {
  const paths = new Set<string>();
  let aggregateBytes = 0;
  for (const source of sources) {
    if (paths.has(source.path)) {
      throw new DecisionBindingError("projected source path is duplicate");
    }
    paths.add(source.path);
    aggregateBytes += source.byteLength;
    if (!Number.isSafeInteger(aggregateBytes) || aggregateBytes > maximumAggregateBytes) {
      throw new DecisionBindingError("projected sources exceed the aggregate ADR byte bound");
    }
    await verifyProjectedSource(repositoryRoot, source);
  }
}

async function verifyProjectedSource(
  repositoryRoot: string,
  source: DecisionSourceBinding,
): Promise<void> {
  const bytes = await readBoundedRepositoryFile(
    repositoryRoot,
    source.path,
    source.byteLength,
    source.path,
  );
  if (bytes.byteLength !== source.byteLength || sha256(bytes) !== source.sha256) {
    throw new DecisionBindingError(
      `projected source ${JSON.stringify(source.path)} differs from its binding`,
    );
  }
}

export function validateReviewPacketBinding(
  registry: JsonObject,
  registeredIdentity: JsonObject,
): void {
  const reviewRecords = requiredArray(
    registry.review_records,
    "decision registry review_records",
  );
  const lifecycle = requiredObject(
    registry.review_packet_lifecycle,
    "decision registry review_packet_lifecycle",
  );
  if (
    Object.keys(lifecycle).length !== 2 ||
    lifecycle.schema !== REVIEW_PACKET_LIFECYCLE_SCHEMA ||
    !Object.hasOwn(lifecycle, "state")
  ) {
    throw new DecisionBindingError(
      "review packet lifecycle has an invalid schema or member set",
    );
  }
  const state = requiredString(lifecycle.state, "review packet lifecycle state");
  if (state === "CURRENT") {
    const reviewSubject = requiredObject(
      registry.review_packet_subject,
      "decision registry review_packet_subject",
    );
    if (!hasExactMembers(reviewSubject, REVIEW_SUBJECT_MEMBERS)) {
      throw new DecisionBindingError(
        "CURRENT review packet subject has an invalid member set",
      );
    }
    if (
      reviewSubject.schema !== REVIEW_SUBJECT_SCHEMA ||
      reviewSubject.state !== "CURRENT" ||
      reviewSubject.normative !== false ||
      reviewSubject.promotion_blocked !== true
    ) {
      throw new DecisionBindingError(
        "CURRENT review packet subject has invalid fixed semantics",
      );
    }

    const claimBoundary = requiredString(
      registry.claim_boundary,
      "decision registry claim_boundary",
    );
    if (claimBoundary.length === 0) {
      throw new DecisionBindingError("decision registry claim_boundary must not be empty");
    }
    requiredObject(registry.review_policy, "decision registry review_policy");
    const subjectSource = requiredObject(
      reviewSubject.source,
      "review packet subject source",
    );
    if (!hasExactMembers(subjectSource, REVIEW_SUBJECT_SOURCE_MEMBERS)) {
      throw new DecisionBindingError("review packet subject source has an invalid member set");
    }
    const sourceCommit = requiredString(
      subjectSource.commit,
      "review packet subject source commit",
    );
    const sourceTree = requiredString(
      subjectSource.tree,
      "review packet subject source tree",
    );
    if (!GIT_OBJECT.test(sourceCommit) || !GIT_OBJECT.test(sourceTree)) {
      throw new DecisionBindingError(
        "review packet subject source commit or tree is invalid",
      );
    }
    // Review capture changes registry.source. The CURRENT packet keeps its
    // immutable identity, which the registry generator resolves.
    const decisionSource = requiredObject(
      subjectSource.decision_source,
      "review packet subject decision_source",
    );
    if (!hasExactMembers(decisionSource, ["path", "sha256", "bytes"] as const)) {
      throw new DecisionBindingError(
        "review packet subject decision_source has an invalid member set",
      );
    }
    if (
      requiredString(
        decisionSource.path,
        "review packet subject decision_source path",
      ) !== REVIEW_SUBJECT_DECISION_SOURCE_PATH ||
      !SHA256.test(
        requiredString(
          decisionSource.sha256,
          "review packet subject decision_source sha256",
        ),
      )
    ) {
      throw new DecisionBindingError(
        "review packet subject decision_source has an invalid identity",
      );
    }
    const decisionSourceBytes = requiredPositiveInteger(
      decisionSource.bytes,
      "review packet subject decision_source bytes",
    );
    if (decisionSourceBytes > MAXIMUM_REVIEW_SUBJECT_DECISION_SOURCE_BYTES) {
      throw new DecisionBindingError(
        "review packet subject decision_source exceeds its byte envelope",
      );
    }

    requireExactJsonValue(
      reviewSubject.claim_boundary,
      registry.claim_boundary as JsonValue,
      "review packet subject claim_boundary",
    );
    requireExactJsonValue(
      reviewSubject.decision_set,
      registeredIdentity,
      "review packet subject decision_set",
    );
    requireExactJsonValue(
      reviewSubject.review_policy,
      registry.review_policy as JsonValue,
      "review packet subject review_policy",
    );
    const subjectDecisions = requiredArray(
      reviewSubject.decisions,
      "review packet subject decisions",
    );
    const registryDecisions = requiredArray(
      registry.decisions,
      "decision registry decisions",
    );
    if (subjectDecisions.length !== registryDecisions.length) {
      throw new DecisionBindingError(
        "review packet decisions differ from the decision registry",
      );
    }
    for (let index = 0; index < registryDecisions.length; index += 1) {
      const subjectDecision = requiredObject(
        subjectDecisions[index],
        `review packet subject decisions[${index}]`,
      );
      const registryDecision = requiredObject(
        registryDecisions[index],
        `decision registry decisions[${index}]`,
      );
      if (!hasExactMembers(subjectDecision, REVIEW_SUBJECT_DECISION_MEMBERS)) {
        throw new DecisionBindingError(
          `review packet subject decisions[${index}] has an invalid member set`,
        );
      }
      for (const member of REVIEW_SUBJECT_DECISION_MEMBERS) {
        if (!Object.hasOwn(registryDecision, member)) {
          throw new DecisionBindingError(
            `decision registry decisions[${index}] lacks review-subject member ${member}`,
          );
        }
        requireExactJsonValue(
          subjectDecision[member],
          registryDecision[member] as JsonValue,
          `review packet subject decisions[${index}].${member}`,
        );
      }
    }
    return;
  }
  if (state === "SUPERSEDED" || state === "TEMPLATE") {
    if (registry.review_packet_subject !== null) {
      throw new DecisionBindingError("non-current review packet subject must be null");
    }
    if (reviewRecords.length !== 0) {
      throw new DecisionBindingError(
        "non-current review packet cannot retain review records",
      );
    }
    return;
  }
  throw new DecisionBindingError("review packet lifecycle state is not recognized");
}

function decisionIdentity(binding: DecisionSetBinding): JsonObject {
  const identity: JsonObject = Object.create(null) as JsonObject;
  identity.schema = binding.schema;
  identity.digest_algorithm = binding.digestAlgorithm;
  identity.domain_hex = binding.domainHex;
  identity.sha256 = binding.sha256;
  identity.semantic_closure = binding.semanticClosure;
  return identity;
}

function jsonLimits(limits: CorpusLimits, maxBytes: number): JsonLimits {
  return {
    maxBytes,
    maxDepth: limits.maximumJsonDepth,
    maxNodes: limits.maximumJsonNodes,
    maxMembers: limits.maximumObjectMembers,
    maxArrayItems: limits.maximumArrayItems,
    maxKeyBytes: limits.maximumKeyUtf8Bytes,
    maxStringBytes: limits.maximumStringUtf8Bytes,
    maxTotalStringBytes: limits.maximumTotalStringUtf8Bytes,
    maxIntegerCharacters: limits.maximumIntegerCharacters,
  };
}

function decodeHex(value: string): Uint8Array {
  if (!/^(?:[0-9a-f]{2})+$/.test(value)) {
    throw new DecisionBindingError("decision-set domain is not lowercase even-length hex");
  }
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < bytes.length; index += 1) {
    bytes[index] = Number.parseInt(value.slice(index * 2, index * 2 + 2), 16);
  }
  return bytes;
}

function domainSeparatedSha256(domainHex: string, payload: Uint8Array): string {
  const domain = decodeHex(domainHex);
  const lengthPrefix = new Uint8Array(8);
  new DataView(lengthPrefix.buffer).setBigUint64(0, BigInt(payload.byteLength), false);
  const committed = new Uint8Array(domain.byteLength + 8 + payload.byteLength);
  committed.set(domain, 0);
  committed.set(lengthPrefix, domain.byteLength);
  committed.set(payload, domain.byteLength + 8);
  return sha256(committed);
}

function requiredObject(value: JsonValue | undefined, label: string): JsonObject {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new DecisionBindingError(`${label} must be an object`);
  }
  return value;
}

function requiredArray(value: JsonValue | undefined, label: string): JsonValue[] {
  if (!Array.isArray(value)) throw new DecisionBindingError(`${label} must be an array`);
  return value;
}

function requiredString(value: JsonValue | undefined, label: string): string {
  if (typeof value !== "string") throw new DecisionBindingError(`${label} must be a string`);
  return value;
}

function requiredPositiveInteger(value: JsonValue | undefined, label: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value <= 0) {
    throw new DecisionBindingError(`${label} must be a positive safe integer`);
  }
  return value;
}

function hasExactMembers(
  object: JsonObject,
  expected: readonly string[],
): boolean {
  return (
    Object.keys(object).length === expected.length &&
    expected.every((member) => Object.hasOwn(object, member))
  );
}

function requiredDecisionPath(
  value: JsonValue | undefined,
  decisionId: string,
  label: string,
): string {
  const path = requiredString(value, label);
  const match = DECISION_SOURCE_PATH.exec(path);
  if (match?.[1] === undefined) {
    throw new DecisionBindingError(`${label} is outside the ADR source allowlist`);
  }
  const pathDecisionId = `ADR-${String(Number(match[1])).padStart(3, "0")}`;
  if (pathDecisionId !== decisionId) {
    throw new DecisionBindingError(`${label} does not agree with ${decisionId}`);
  }
  return path;
}

function requiredModulePath(
  value: JsonValue | undefined,
  decisionId: string,
  label: string,
): string {
  const path = requiredString(value, label);
  const match = MODULE_SOURCE_PATH.exec(path);
  if (match?.[1] === undefined) {
    throw new DecisionBindingError(`${label} is outside the ADR module allowlist`);
  }
  const pathDecisionId = `ADR-${String(Number(match[1])).padStart(3, "0")}`;
  if (pathDecisionId !== decisionId) {
    throw new DecisionBindingError(`${label} does not agree with ${decisionId}`);
  }
  return path;
}

function requireExactJsonValue(
  value: JsonValue | undefined,
  expected: JsonValue,
  label: string,
): void {
  if (value === undefined || canonicalJsonText(value) !== canonicalJsonText(expected)) {
    throw new DecisionBindingError(`${label} differs from the bound identity`);
  }
}
