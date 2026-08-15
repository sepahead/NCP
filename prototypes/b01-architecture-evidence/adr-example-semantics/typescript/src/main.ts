import { canonicalJsonBytes, canonicalJsonText } from "./canonical-json.ts";
import {
  validateCorpus,
  type Corpus,
  type CorpusCase,
  type CorpusLimits,
  type CorpusMutation,
  type CorpusPatch,
} from "./corpus.ts";
import {
  verifyDecisionSetBinding,
  type DecisionSourceBinding,
} from "./decision-binding.ts";
import {
  extractExactJsonFences,
  readBoundedRepositoryFile,
  readBoundedRegularFile,
  resolveRepositoryDirectory,
  sha256,
} from "./file-io.ts";
import { applyPatch, type PatchOperation } from "./json-pointer.ts";
import { runSelfTests, type SelfTestReport } from "./self-test.ts";
import { evaluateSemantics, type SemanticResult } from "./semantics.ts";
import { strictJsonParse, type JsonLimits, type JsonValue } from "./strict-json.ts";
import { lstat, readdir } from "node:fs/promises";
import { resolve } from "node:path";

type JsonObject = { [key: string]: JsonValue };

const CORPUS_BOOTSTRAP_LIMITS: JsonLimits = Object.freeze({
  maxBytes: 262_144,
  maxDepth: 32,
  maxNodes: 100_000,
  maxMembers: 4_096,
  maxArrayItems: 4_096,
  maxKeyBytes: 128,
  maxStringBytes: 65_536,
  maxTotalStringBytes: 131_072,
  maxIntegerCharacters: 32,
});

const ENGINE_RELATIVE_ROOT =
  "prototypes/b01-architecture-evidence/adr-example-semantics/typescript";
const MAXIMUM_ENGINE_SOURCE_FILES = 32;
const MAXIMUM_ENGINE_SOURCE_PATH_BYTES = 512;
const MAXIMUM_ENGINE_SOURCE_FILE_BYTES = 262_144;
const MAXIMUM_AGGREGATE_ENGINE_SOURCE_BYTES = 2_097_152;
const encoder = new TextEncoder();

class EngineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "EngineError";
  }
}

interface Arguments {
  readonly corpusPath: string;
  readonly repositoryRoot: string;
  readonly selfTest: boolean;
}

interface VerifiedSource {
  readonly identity: JsonObject;
  readonly sourcePath: string;
  readonly document: JsonValue;
}

interface EvaluatedCase {
  readonly result: JsonObject;
  readonly mutationCount: number;
}

async function main(): Promise<void> {
  const argumentsValue = parseArguments(Bun.argv.slice(2));
  const corpusBytes = await readBoundedRegularFile(
    argumentsValue.corpusPath,
    CORPUS_BOOTSTRAP_LIMITS.maxBytes,
    "ADR semantic corpus",
  );
  const corpusSha256 = sha256(corpusBytes);
  const corpus = validateCorpus(strictJsonParse(corpusBytes, CORPUS_BOOTSTRAP_LIMITS));

  const decisionSources = await verifyDecisionSetBinding(
    argumentsValue.repositoryRoot,
    corpus.decisionSetBinding,
    corpus.limits,
  );
  const verifiedSources = await verifyAdrSources(
    argumentsValue.repositoryRoot,
    corpus,
    decisionSources,
  );
  const engineSourceIdentities = await collectEngineSourceIdentities(
    argumentsValue.repositoryRoot,
  );

  const caseResults: JsonValue[] = [];
  let mutationCount = 0;
  for (const entry of corpus.cases) {
    const verified = verifiedSources.get(entry.id);
    if (verified === undefined) throw new EngineError(`source verification omitted ${entry.id}`);
    const evaluated = evaluateCase(entry, verified.sourcePath, verified.document, corpus);
    caseResults.push(evaluated.result);
    mutationCount += evaluated.mutationCount;
  }

  const output: JsonObject = Object.create(null) as JsonObject;
  output.schema = "ncp.b01-adr-example-semantics-result.v1";
  output.schema_version = 1;
  output.engine = "typescript";
  output.semantic_claim = "local-prototype-only";
  output.corpus_sha256 = corpusSha256;
  output.decision_set_binding = corpus.decisionSetBinding.json;
  output.case_count = corpus.cases.length;
  output.mutation_count = mutationCount;
  output.source_identities = corpus.cases.map((entry) => {
    const source = verifiedSources.get(entry.id);
    if (source === undefined) throw new EngineError(`source identity omitted ${entry.id}`);
    return source.identity;
  });
  output.engine_source_identities = engineSourceIdentities;
  output.cases = caseResults;
  if (argumentsValue.selfTest) {
    output.self_tests = selfTestJson(runSelfTests());
  }

  const serialized = canonicalJsonText(output, corpus.limits.maximumEngineOutputBytes);
  process.stdout.write(`${serialized}\n`);
}

function parseArguments(values: readonly string[]): Arguments {
  let corpusPath: string | undefined;
  let repositoryRoot: string | undefined;
  let selfTest = false;
  for (let index = 0; index < values.length; index += 1) {
    const argument = values[index];
    switch (argument) {
      case "--corpus": {
        if (corpusPath !== undefined) throw new EngineError("--corpus was provided twice");
        const next = values[index + 1];
        if (next === undefined || next.startsWith("--")) {
          throw new EngineError("--corpus requires one path");
        }
        corpusPath = resolve(next);
        index += 1;
        break;
      }
      case "--repo-root": {
        if (repositoryRoot !== undefined) throw new EngineError("--repo-root was provided twice");
        const next = values[index + 1];
        if (next === undefined || next.startsWith("--")) {
          throw new EngineError("--repo-root requires one path");
        }
        repositoryRoot = resolve(next);
        index += 1;
        break;
      }
      case "--self-test":
        if (selfTest) throw new EngineError("--self-test was provided twice");
        selfTest = true;
        break;
      default:
        throw new EngineError(`unknown argument ${JSON.stringify(argument)}`);
    }
  }
  if (corpusPath === undefined || repositoryRoot === undefined) {
    throw new EngineError("--corpus and --repo-root are required");
  }
  return { corpusPath, repositoryRoot, selfTest };
}

async function verifyAdrSources(
  repositoryRoot: string,
  corpus: Corpus,
  decisionSources: ReadonlyMap<string, DecisionSourceBinding>,
): Promise<ReadonlyMap<string, VerifiedSource>> {
  const groups = new Map<string, CorpusCase[]>();
  for (const entry of corpus.cases) {
    const decisionSource = decisionSources.get(entry.source.adr);
    if (decisionSource === undefined) {
      throw new EngineError(
        `${entry.id} source is absent from the bound decision registry`,
      );
    }
    const existing = groups.get(decisionSource.path) ?? [];
    existing.push(entry);
    groups.set(decisionSource.path, existing);
  }
  const results = new Map<string, VerifiedSource>();
  let aggregateBytes = 0;
  for (const [path, entries] of [...groups.entries()].sort(([left], [right]) =>
    left < right ? -1 : left > right ? 1 : 0,
  )) {
    const bytes = await readBoundedRepositoryFile(
      repositoryRoot,
      path,
      corpus.limits.maximumAdrBytes,
      path,
    );
    aggregateBytes += bytes.byteLength;
    if (aggregateBytes > corpus.limits.maximumAggregateAdrBytes) {
      throw new EngineError("aggregate ADR bytes exceed the corpus bound");
    }
    const digest = sha256(bytes);
    const decisionSource = decisionSources.get(entries[0]?.source.adr ?? "");
    if (
      decisionSource === undefined ||
      bytes.byteLength !== decisionSource.byteLength ||
      digest !== decisionSource.sha256
    ) {
      throw new EngineError(`${path} ADR source identity does not match`);
    }
    const fences = extractExactJsonFences(bytes);
    const ordinals = entries.map((entry) => entry.source.jsonFenceOrdinal).sort((a, b) => a - b);
    if (
      fences.length !== entries.length ||
      ordinals.some((ordinal, index) => ordinal !== index + 1)
    ) {
      throw new EngineError(`${path} JSON fence coverage is not exact and contiguous`);
    }
    for (const entry of entries) {
      const fence = fences[entry.source.jsonFenceOrdinal - 1];
      if (fence === undefined) throw new EngineError(`${entry.id} JSON fence is absent`);
      if (
        fence.byteLength !== entry.source.fenceByteLength ||
        sha256(fence) !== entry.source.fenceSha256
      ) {
        throw new EngineError(`${entry.id} JSON fence identity does not match`);
      }
      const document = strictJsonParse(
        fence,
        jsonLimits(corpus.limits, corpus.limits.maximumJsonFenceBytes),
      );
      const identity: JsonObject = Object.create(null) as JsonObject;
      identity.case_id = entry.id;
      identity.path = path;
      identity.json_fence_ordinal = entry.source.jsonFenceOrdinal;
      identity.adr_byte_length = decisionSource.byteLength;
      identity.adr_sha256 = decisionSource.sha256;
      identity.fence_byte_length = entry.source.fenceByteLength;
      identity.fence_sha256 = entry.source.fenceSha256;
      results.set(entry.id, { identity, sourcePath: path, document });
    }
  }
  return results;
}

function evaluateCase(
  entry: CorpusCase,
  sourcePath: string,
  document: JsonValue,
  corpus: Corpus,
): EvaluatedCase {
  const base = evaluateSemantics({
    sourcePath,
    ordinal: entry.source.jsonFenceOrdinal,
    profile: entry.profile,
    document,
    fixture: entry.boundedFixture,
  });
  assertExpected(
    entry.id,
    base,
    entry.expectedProfileResult,
    entry.productionAdmission,
    entry.expectedDiagnostics,
    entry.payloadInterpreted,
    corpus,
  );
  const mutations: JsonValue[] = [];
  for (const mutation of entry.mutations) {
    const mutated = applyMutation(document, entry.boundedFixture, mutation, corpus.limits);
    const result = evaluateSemantics({
      sourcePath,
      ordinal: entry.source.jsonFenceOrdinal,
      profile: entry.profile,
      document: mutated.document,
      fixture: mutated.fixture,
    });
    assertExpected(
      mutation.id,
      result,
      mutation.expectedProfileResult,
      mutation.productionAdmission,
      mutation.expectedDiagnostics,
      mutation.payloadInterpreted,
      corpus,
    );
    mutations.push(resultJson(mutation.id, result));
  }
  const result = resultJson(entry.id, base);
  result.mutations = mutations;
  return { result, mutationCount: mutations.length };
}

function applyMutation(
  document: JsonValue,
  fixture: JsonValue,
  mutation: CorpusMutation,
  limits: CorpusLimits,
): { readonly document: JsonValue; readonly fixture: JsonValue } {
  const operation = toPatchOperation(mutation.patch);
  if (mutation.patch.target === "DOCUMENT") {
    return {
      document: revalidateConstructed(
        applyPatch(document, [operation]),
        limits,
        limits.maximumJsonFenceBytes,
      ),
      fixture,
    };
  }
  return {
    document,
    fixture: revalidateConstructed(
      applyPatch(fixture, [operation]),
      limits,
      limits.maximumFixtureBytes,
    ),
  };
}

function toPatchOperation(patch: CorpusPatch): PatchOperation {
  switch (patch.op) {
    case "ADD":
      return { op: "add", path: patch.path, value: requiredPatchValue(patch) };
    case "REMOVE":
      return { op: "remove", path: patch.path };
    case "REPLACE":
      return { op: "replace", path: patch.path, value: requiredPatchValue(patch) };
  }
}

function requiredPatchValue(patch: CorpusPatch): JsonValue {
  if (!Object.hasOwn(patch, "value")) throw new EngineError("patch value is absent");
  return patch.value as JsonValue;
}

function revalidateConstructed(
  value: JsonValue,
  limits: CorpusLimits,
  maximumBytes: number,
): JsonValue {
  const bytes = canonicalJsonBytes(value, maximumBytes);
  return strictJsonParse(bytes, jsonLimits(limits, maximumBytes));
}

function assertExpected(
  id: string,
  actual: SemanticResult,
  expectedResult: string,
  expectedProductionAdmission: string,
  expectedDiagnostics: readonly string[],
  expectedPayloadInterpreted: boolean,
  corpus: Corpus,
): void {
  for (const diagnostic of actual.diagnostics) {
    if (!corpus.diagnosticRegistry.has(diagnostic)) {
      throw new EngineError(`${id} emitted unknown diagnostic ${diagnostic}`);
    }
  }
  if (
    actual.result !== expectedResult ||
    actual.productionAdmission !== expectedProductionAdmission ||
    actual.payloadInterpreted !== expectedPayloadInterpreted ||
    !stringArraysEqual(actual.diagnostics, expectedDiagnostics)
  ) {
    throw new EngineError(
      `${id} semantic result differs from the bound corpus expectation`,
    );
  }
}

function resultJson(
  id: string,
  result: SemanticResult,
): JsonObject {
  const value: JsonObject = Object.create(null) as JsonObject;
  value.id = id;
  value.profile_result = result.result;
  value.production_admission = result.productionAdmission;
  value.diagnostics = [...result.diagnostics];
  value.payload_interpreted = result.payloadInterpreted;
  return value;
}

async function collectEngineSourceIdentities(
  repositoryRoot: string,
): Promise<JsonValue[]> {
  const sourceDirectory = await resolveRepositoryDirectory(
    repositoryRoot,
    `${ENGINE_RELATIVE_ROOT}/src`,
    "TypeScript source directory",
  );
  const paths = [`${ENGINE_RELATIVE_ROOT}/package.json`, `${ENGINE_RELATIVE_ROOT}/tsconfig.json`];
  for (const path of paths) validateEngineSourcePath(path);

  try {
    const before = await lstat(sourceDirectory);
    if (before.isSymbolicLink() || !before.isDirectory()) {
      throw new EngineError("TypeScript source directory must be a non-symlink directory");
    }
    const entries = await readdir(sourceDirectory, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isSymbolicLink() || !entry.isFile() || !entry.name.endsWith(".ts")) {
        throw new EngineError(
          `unexpected non-TypeScript file in engine source directory: ${JSON.stringify(entry.name)}`,
        );
      }
      const path = `${ENGINE_RELATIVE_ROOT}/src/${entry.name}`;
      validateEngineSourcePath(path);
      if (paths.length === MAXIMUM_ENGINE_SOURCE_FILES) {
        throw new EngineError(
          `TypeScript engine source set exceeds ${MAXIMUM_ENGINE_SOURCE_FILES} files`,
        );
      }
      paths.push(path);
    }
    const after = await lstat(sourceDirectory);
    if (
      before.dev !== after.dev ||
      before.ino !== after.ino ||
      before.mtimeMs !== after.mtimeMs ||
      before.ctimeMs !== after.ctimeMs ||
      after.isSymbolicLink() ||
      !after.isDirectory()
    ) {
      throw new EngineError("TypeScript source directory changed while enumerated");
    }
  } catch (error) {
    if (error instanceof EngineError) throw error;
    const detail = error instanceof Error ? error.message : "unknown directory error";
    throw new EngineError(`TypeScript source directory cannot be enumerated: ${detail}`);
  }

  paths.sort();
  if (paths.length < 3 || paths.some((path, index) => path === paths[index - 1])) {
    throw new EngineError("TypeScript engine source paths are missing or duplicate");
  }
  const identities: JsonValue[] = [];
  let aggregateBytes = 0;
  for (const path of paths) {
    const bytes = await readBoundedRepositoryFile(
      repositoryRoot,
      path,
      MAXIMUM_ENGINE_SOURCE_FILE_BYTES,
      `engine source ${path}`,
    );
    aggregateBytes += bytes.byteLength;
    if (
      !Number.isSafeInteger(aggregateBytes) ||
      aggregateBytes > MAXIMUM_AGGREGATE_ENGINE_SOURCE_BYTES
    ) {
      throw new EngineError(
        `TypeScript engine source set exceeds ${MAXIMUM_AGGREGATE_ENGINE_SOURCE_BYTES} bytes`,
      );
    }
    const identity: JsonObject = Object.create(null) as JsonObject;
    identity.path = path;
    identity.byte_length = bytes.byteLength;
    identity.sha256 = sha256(bytes);
    identities.push(identity);
  }
  return identities;
}

function validateEngineSourcePath(path: string): void {
  if (path.includes("\0") || encoder.encode(path).byteLength > MAXIMUM_ENGINE_SOURCE_PATH_BYTES) {
    throw new EngineError(
      `TypeScript engine source path exceeds ${MAXIMUM_ENGINE_SOURCE_PATH_BYTES} UTF-8 bytes`,
    );
  }
}

function jsonLimits(limits: CorpusLimits, maximumBytes: number): JsonLimits {
  return {
    maxBytes: maximumBytes,
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

function stringArraysEqual(left: readonly string[], right: readonly string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function selfTestJson(report: SelfTestReport): JsonObject {
  const value: JsonObject = Object.create(null) as JsonObject;
  value.executed = report.executed;
  value.detected = report.detected;
  return value;
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? `${error.name}: ${error.message}` : "unknown error";
  process.stderr.write(`${message}\n`);
  process.exitCode = 1;
});
