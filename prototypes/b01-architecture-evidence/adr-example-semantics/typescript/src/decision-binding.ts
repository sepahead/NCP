import { canonicalJsonBytes, canonicalJsonText } from "./canonical-json.ts";
import type { CorpusLimits, DecisionSetBinding } from "./corpus.ts";
import { readBoundedRegularFile, sha256 } from "./file-io.ts";
import { strictJsonParse, type JsonLimits, type JsonValue } from "./strict-json.ts";

type JsonObject = { [key: string]: JsonValue };

const DECISION_SOURCE_PATH =
  /^docs\/adr\/(000[1-9]|001[01])-[a-z0-9]+(?:-[a-z0-9]+)*\.md$/;
const SHA256 = /^[0-9a-f]{64}$/;
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
  const registryPath = joinRoot(repositoryRoot, binding.registryPath);
  const registryBytes = await readBoundedRegularFile(
    registryPath,
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
  requireExactJsonValue(
    registry.decision_set,
    registeredIdentity,
    "decision registry decision_set",
  );
  const reviewSubject = requiredObject(
    registry.review_packet_subject,
    "decision registry review_packet_subject",
  );
  requireExactJsonValue(
    reviewSubject.decision_set,
    registeredIdentity,
    "review packet subject decision_set",
  );

  const decisions = requiredArray(registry.decisions, "decision registry decisions");
  const ids = new Set<string>();
  const sources = new Map<string, DecisionSourceBinding>();
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
  const domain = decodeHex(binding.domainHex);
  const lengthPrefix = new Uint8Array(8);
  new DataView(lengthPrefix.buffer).setBigUint64(0, BigInt(projectionBytes.byteLength), false);
  const boundBytes = new Uint8Array(
    domain.byteLength + lengthPrefix.byteLength + projectionBytes.byteLength,
  );
  boundBytes.set(domain, 0);
  boundBytes.set(lengthPrefix, domain.byteLength);
  boundBytes.set(projectionBytes, domain.byteLength + lengthPrefix.byteLength);
  if (sha256(boundBytes) !== binding.sha256) {
    throw new DecisionBindingError("domain-separated decision-set SHA-256 does not match");
  }
  return sources;
}

function decisionIdentity(binding: DecisionSetBinding): JsonObject {
  const identity: JsonObject = Object.create(null) as JsonObject;
  identity.schema = binding.schema;
  identity.digest_algorithm = binding.digestAlgorithm;
  identity.domain_hex = binding.domainHex;
  identity.sha256 = binding.sha256;
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

function joinRoot(root: string, relative: string): string {
  if (!root.startsWith("/") || root.includes("\0")) {
    throw new DecisionBindingError("repository root must be an absolute path without NUL");
  }
  const segments = relative.split("/");
  if (
    relative.startsWith("/") ||
    relative.includes("\0") ||
    segments.some((segment) => segment === "" || segment === "." || segment === "..")
  ) {
    throw new DecisionBindingError("decision registry path is not repository-relative");
  }
  return `${root.replace(/\/+$/, "")}/${relative}`;
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

function requireExactJsonValue(
  value: JsonValue | undefined,
  expected: JsonValue,
  label: string,
): void {
  if (value === undefined || canonicalJsonText(value) !== canonicalJsonText(expected)) {
    throw new DecisionBindingError(`${label} differs from the bound identity`);
  }
}
