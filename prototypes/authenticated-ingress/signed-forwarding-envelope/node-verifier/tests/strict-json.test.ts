import { Buffer } from "node:buffer";
import assert from "node:assert/strict";
import test from "node:test";
import { PrototypeError, type ErrorCode } from "../src/errors.js";
import {
  decodeCanonicalBase64url,
} from "../src/verifier.js";
import { strictJsonParse, type JsonLimits } from "../src/strict-json.js";

function limits(overrides: Partial<JsonLimits> = {}): JsonLimits {
  return {
    maxBytes: 128,
    maxDepth: 8,
    maxNodes: 32,
    maxMembers: 8,
    maxStringBytes: 32,
    ...overrides,
  };
}

function assertReject(code: ErrorCode, action: () => unknown): void {
  assert.throws(action, (error: unknown) => {
    assert(error instanceof PrototypeError);
    assert.equal(error.code, code);
    return true;
  });
}

test("JSON byte, depth, node, member, and string limits accept exact and reject above", () => {
  const exactBytes = Buffer.from('{"x":1}', "ascii");
  assert.deepEqual(
    strictJsonParse(exactBytes, limits({ maxBytes: exactBytes.length })),
    Object.assign(Object.create(null), { x: 1 }),
  );
  assertReject("bounds", () =>
    strictJsonParse(
      Buffer.concat([exactBytes, Buffer.from(" ")]),
      limits({ maxBytes: exactBytes.length }),
    ),
  );

  strictJsonParse(Buffer.from("[[]]"), limits({ maxDepth: 2 }));
  assertReject("bounds", () =>
    strictJsonParse(Buffer.from("[[[]]]"), limits({ maxDepth: 2 })),
  );

  strictJsonParse(Buffer.from('{"a":1}'), limits({ maxNodes: 3 }));
  assertReject("bounds", () =>
    strictJsonParse(Buffer.from('{"a":1}'), limits({ maxNodes: 2 })),
  );

  strictJsonParse(Buffer.from('["a","b"]'), limits({ maxMembers: 2 }));
  assertReject("bounds", () =>
    strictJsonParse(Buffer.from('["a","b","c"]'), limits({ maxMembers: 2 })),
  );

  strictJsonParse(Buffer.from('"abcd"'), limits({ maxStringBytes: 4 }));
  assertReject("bounds", () =>
    strictJsonParse(Buffer.from('"abcde"'), limits({ maxStringBytes: 4 })),
  );
});

test("integer boundary and ambiguous number grammars reject exactly", () => {
  assert.equal(
    strictJsonParse(Buffer.from("9007199254740991"), limits()),
    9_007_199_254_740_991,
  );
  for (const token of [
    "9007199254740992",
    "-9007199254740992",
    "-0",
    "01",
    "1.0",
    "1e0",
  ]) {
    assert.throws(() => strictJsonParse(Buffer.from(token), limits()));
  }
});

test("base64url accepts exact decoded bounds and rejects trailing-bit ambiguity", () => {
  assert.deepEqual(decodeCanonicalBase64url("AA", 1), Buffer.from([0]));
  assertReject("encoding", () => decodeCanonicalBase64url("AB", 1));
  const exact = Buffer.from("test").toString("base64url");
  assert.deepEqual(decodeCanonicalBase64url(exact, 4), Buffer.from("test"));
  assertReject("bounds", () => decodeCanonicalBase64url(exact, 3));
});
