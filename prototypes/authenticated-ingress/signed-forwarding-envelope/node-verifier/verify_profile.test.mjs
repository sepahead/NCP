import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { verifyBoundary } from "./verify_profile.mjs";

const exact = {
  packageDocument: JSON.parse(readFileSync("package.json", "utf8")),
  lock: JSON.parse(readFileSync("package-lock.json", "utf8")),
  source: readFileSync("src/verifier.ts", "utf8"),
  tsconfig: JSON.parse(readFileSync("tsconfig.json", "utf8")),
  nodeVersion: process.versions.node,
  opensslVersion: process.versions.openssl,
};

test("profile verifier accepts the exact reviewed boundary", () => {
  verifyBoundary(exact);
});

test("profile verifier rejects dependency version drift", () => {
  const mutant = structuredClone(exact);
  mutant.packageDocument.devDependencies.typescript = "^5.9.2";
  assert.throws(() => verifyBoundary(mutant));
});

test("profile verifier rejects lock integrity drift", () => {
  const mutant = structuredClone(exact);
  mutant.lock.packages["node_modules/typescript"].integrity = "sha512-mutant";
  assert.throws(() => verifyBoundary(mutant));
});

test("profile verifier rejects compiler strictness drift", () => {
  const mutant = structuredClone(exact);
  mutant.tsconfig.compilerOptions.noUncheckedIndexedAccess = false;
  assert.throws(() => verifyBoundary(mutant));
});

test("profile verifier rejects removal of strict source checks", () => {
  for (const fragment of [
    "character.codePointAt(0)! > 0x7f",
    "pointHasSmallOrder(publicKey)",
    "littleEndian(scalarS) >= L",
  ]) {
    const mutant = {
      ...exact,
      source: exact.source.replace(fragment, "removedReviewedCheck"),
    };
    assert.throws(() => verifyBoundary(mutant));
  }
});

test("profile verifier rejects forbidden private-key selection", () => {
  const mutant = {
    ...exact,
    source: `${exact.source}\ncreatePrivateKey(attackerInput);\n`,
  };
  assert.throws(() => verifyBoundary(mutant));
});
