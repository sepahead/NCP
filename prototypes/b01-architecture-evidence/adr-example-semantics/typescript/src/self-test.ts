import { canonicalJsonText } from "./canonical-json.ts";
import { applyPatch, JsonPointerError } from "./json-pointer.ts";
import { evaluateSemantics, SemanticConfigurationError } from "./semantics.ts";
import { strictJsonParse, StrictJsonError, type JsonLimits } from "./strict-json.ts";

const encoder = new TextEncoder();

export interface SelfTestReport {
  readonly executed: number;
  readonly detected: number;
}

export function runSelfTests(): SelfTestReport {
  const report = { executed: 0, detected: 0 };
  const limits: JsonLimits = {
    maxBytes: 256,
    maxDepth: 4,
    maxNodes: 8,
    maxMembers: 4,
    maxArrayItems: 4,
    maxKeyBytes: 8,
    maxStringBytes: 8,
    maxTotalStringBytes: 32,
    maxIntegerCharacters: 16,
  };
  const accepted = strictJsonParse(encoder.encode('{"a":[1,true,null]}'), limits);
  if (!isObject(accepted) || !Array.isArray(accepted.a)) {
    throw new Error("strict parser self-test returned the wrong value");
  }

  expectStrictRejection('{"a":1,"a":2}', limits, "duplicate member guard", report);
  expectStrictRejection('{"a":1.0}', limits, "floating-point guard", report);
  expectStrictRejection('{"a":-0}', limits, "negative-zero guard", report);
  expectStrictRejection('{"a":01}', limits, "leading-zero guard", report);
  expectStrictRejection('{"a":9007199254740992}', limits, "safe-integer guard", report);
  expectStrictRejection('{"a":"123456789"}', limits, "string-byte guard", report);
  expectStrictRejection('{"a":{"b":{"c":{"d":0}}}}', limits, "depth guard", report);
  expectStrictRejection(
    '{"a":1,"b":2,"c":3,"d":4,"e":5}',
    limits,
    "member guard",
    report,
  );
  expectStrictRejection(
    '{"123456789":0}',
    limits,
    "key-byte guard",
    report,
  );
  expectStrictRejection(
    '{"a":"12345678","b":"12345678","c":"12345678","d":"12345678"}',
    limits,
    "total-string-byte guard",
    report,
  );
  expectStrictRejection(
    '{"a":12345678901234567}',
    limits,
    "integer-character guard",
    report,
  );
  expectStrictRejection(
    '{"a":[1,2,3,4,5]}',
    { ...limits, maxNodes: 100 },
    "array-item guard",
    report,
  );
  expectStrictRejection(
    '[1,2]',
    { ...limits, maxNodes: 2 },
    "node-count guard",
    report,
  );
  report.executed += 1;
  try {
    strictJsonParse(new Uint8Array(257), limits);
  } catch (error) {
    if (error instanceof StrictJsonError) report.detected += 1;
    else throw new Error("byte-length guard threw the wrong error type");
  }
  if (report.executed !== report.detected) {
    throw new Error("byte-length guard did not reject");
  }
  expectThrows(
    () => strictJsonParse(new Uint8Array([0x7b, 0x22, 0xff, 0x22, 0x3a, 0x31, 0x7d]), limits),
    StrictJsonError,
    "UTF-8 guard",
    report,
  );
  expectThrows(
    () =>
      strictJsonParse(
        new Uint8Array([0xef, 0xbb, 0xbf, 0x7b, 0x7d]),
        limits,
      ),
    StrictJsonError,
    "UTF-8 BOM guard",
    report,
  );
  report.executed += 1;
  const nestedAtMemberLimit = strictJsonParse(
    encoder.encode('{"a":{"b":1}}'),
    { ...limits, maxMembers: 1 },
  );
  if (
    !isObject(nestedAtMemberLimit) ||
    !isObject(nestedAtMemberLimit.a) ||
    nestedAtMemberLimit.a.b !== 1
  ) {
    throw new Error("per-object member guard rejected valid nested objects");
  }
  report.detected += 1;

  const patched = applyPatch(
    { a: { b: 1 }, list: ["x"] },
    [
      { op: "replace", path: "/a/b", value: 2 },
      { op: "add", path: "/list/-", value: "y" },
      { op: "remove", path: "/list/0" },
    ],
  );
  if (
    !isObject(patched) ||
    !isObject(patched.a) ||
    patched.a.b !== 2 ||
    !Array.isArray(patched.list) ||
    patched.list.length !== 1 ||
    patched.list[0] !== "y"
  ) {
    throw new Error("JSON Pointer self-test returned the wrong value");
  }
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "add", path: "/a", value: 2 }]),
    JsonPointerError,
    "add-overwrite guard",
    report,
  );
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "replace", path: "/missing", value: 2 }]),
    JsonPointerError,
    "missing-target guard",
    report,
  );
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "remove", path: "/~2" }]),
    JsonPointerError,
    "JSON Pointer escape guard",
    report,
  );
  expectThrows(
    () => applyPatch({ a: 1 }, [{ op: "remove", path: "" }]),
    JsonPointerError,
    "root-mutation guard",
    report,
  );
  const prototypeKey = applyPatch({}, [
    { op: "add", path: "/__proto__", value: { polluted: true } },
  ]);
  if (
    !isObject(prototypeKey) ||
    !Object.hasOwn(prototypeKey, "__proto__") ||
    ({} as { polluted?: boolean }).polluted !== undefined
  ) {
    throw new Error("JSON Pointer prototype-key isolation failed");
  }

  expectThrows(
    () =>
      evaluateSemantics({
        sourcePath: "docs/adr/0004-observer-attach-grants-and-revocation.md",
        ordinal: 1,
        profile: "ADR001_PLANT_KIND_SEPARATION_FRAGMENT_V1",
        document: { allocates_output_slot: false, state: "PENDING_INTENT_ONLY" },
        fixture: { expected_state: "PENDING_INTENT_ONLY", output_allocation_permitted: false },
      }),
    SemanticConfigurationError,
    "source-profile binding guard",
    report,
  );
  expectThrows(
    () =>
      evaluateSemantics({
        sourcePath: "docs/adr/0004-observer-attach-grants-and-revocation.md",
        ordinal: 1,
        profile: "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
        document: { allocates_output_slot: false, state: "PENDING_INTENT_ONLY" },
        fixture: {
          expected_state: "PENDING_INTENT_ONLY",
          output_allocation_permitted: false,
          unregistered_default: true,
        },
      }),
    SemanticConfigurationError,
    "fixture closure guard",
    report,
  );
  report.executed += 1;
  const semanticHostile = evaluateSemantics({
    sourcePath: "docs/adr/0004-observer-attach-grants-and-revocation.md",
    ordinal: 1,
    profile: "ADR004_PENDING_RELEASE_RESERVATION_NONALLOCATION_V1",
    document: { allocates_output_slot: true, state: "PENDING_INTENT_ONLY" },
    fixture: { expected_state: "PENDING_INTENT_ONLY", output_allocation_permitted: false },
  });
  if (
    semanticHostile.result !== "REJECT" ||
    semanticHostile.productionAdmission !== "NOT_APPLICABLE" ||
    semanticHostile.diagnostics.join(",") !== "PENDING_STATE_ALLOCATES_OUTPUT"
  ) {
    throw new Error("semantic hostile control escaped its guard");
  }
  report.detected += 1;

  if (canonicalJsonText({ z: 1, a: "é" }) !== '{"a":"é","z":1}') {
    throw new Error("canonical JSON self-test returned unstable bytes");
  }
  report.executed += 1;
  if (
    canonicalJsonText({ "\u{1f600}": 2, "\ue000": 1 }) !==
    '{"\ue000":1,"\u{1f600}":2}'
  ) {
    throw new Error("canonical JSON did not order keys by Unicode scalar value");
  }
  report.detected += 1;
  return report;
}

function expectStrictRejection(
  source: string,
  limits: JsonLimits,
  label: string,
  report: { executed: number; detected: number },
): void {
  expectThrows(
    () => strictJsonParse(encoder.encode(source), limits),
    StrictJsonError,
    label,
    report,
  );
}

function expectThrows(
  action: () => unknown,
  constructor: new (...args: never[]) => Error,
  label: string,
  report: { executed: number; detected: number },
): void {
  report.executed += 1;
  try {
    action();
  } catch (error) {
    if (error instanceof constructor) {
      report.detected += 1;
      return;
    }
    throw new Error(`${label} threw the wrong error type`);
  }
  throw new Error(`${label} did not reject`);
}

function isObject(value: unknown): value is { [key: string]: unknown } {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
