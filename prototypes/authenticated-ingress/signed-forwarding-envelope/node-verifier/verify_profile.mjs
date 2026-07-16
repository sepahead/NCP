#!/usr/bin/env node
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const EXPECTED_NODE = "26.3.0";
const EXPECTED_OPENSSL = "3.6.2";
const EXPECTED = {
  "node_modules/@types/node": {
    integrity:
      "sha512-nxAkRSVkN1Y0JC1W8ky/fTfkGsMmcrRsbx+3XoZE+rMOX71kLYTV7fLXpqud1GpbpP5TuffXFqfX7fH2GgZREw==",
    version: "26.1.1",
  },
  "node_modules/typescript": {
    integrity:
      "sha512-CWBzXQrc/qOkhidw1OzBTQuYRbfyxDXJMVJ1XNwUHGROVmuaeiEm3OslpZ1RV96d7SKKjZKrSJu3+t/xlw3R9A==",
    version: "5.9.2",
  },
  "node_modules/undici-types": {
    integrity:
      "sha512-j375ScV60dom+YkPFIfTLcOiPxkN/buHz5GobjLhixFuANaNs3C9l4GmrWqejgXWJ7BbJcFYpTEUkS1Ge8bpZQ==",
    version: "8.3.0",
  },
};

export function verifyBoundary({
  packageDocument,
  lock,
  source,
  tsconfig,
  nodeVersion,
  opensslVersion,
}) {
  assert.equal(nodeVersion, EXPECTED_NODE, "Node runtime drifted");
  assert.equal(opensslVersion, EXPECTED_OPENSSL, "OpenSSL runtime drifted");
  assert.deepEqual(packageDocument.engines, { node: EXPECTED_NODE });
  assert.deepEqual(packageDocument.devDependencies, {
    "@types/node": "26.1.1",
    typescript: "5.9.2",
  });
  assert.deepEqual(tsconfig, {
    compilerOptions: {
      target: "ES2024",
      lib: ["ES2024"],
      module: "NodeNext",
      moduleResolution: "NodeNext",
      rootDir: ".",
      outDir: "dist",
      strict: true,
      noEmitOnError: true,
      noImplicitReturns: true,
      noUncheckedIndexedAccess: true,
      noUnusedLocals: true,
      noUnusedParameters: true,
      exactOptionalPropertyTypes: true,
      useUnknownInCatchVariables: true,
      forceConsistentCasingInFileNames: true,
      skipLibCheck: false,
      types: ["node"],
    },
    include: ["src/**/*.ts", "tests/**/*.ts"],
  });
  assert.equal(lock.lockfileVersion, 3);
  assert.equal(lock.requires, true);
  assert.deepEqual(Object.keys(lock.packages).sort(), ["", ...Object.keys(EXPECTED)].sort());
  for (const [path, expected] of Object.entries(EXPECTED)) {
    const entry = lock.packages[path];
    assert.equal(entry.version, expected.version, `${path} version drifted`);
    assert.equal(entry.integrity, expected.integrity, `${path} integrity drifted`);
    assert.match(
      entry.resolved,
      /^https:\/\/registry\.npmjs\.org\//,
      `${path} registry drifted`,
    );
  }
  for (const fragment of [
    'header.alg !== "Ed25519"',
    'header.crit[0] !== "ncp"',
    "character.codePointAt(0)! > 0x7f",
    "pointHasSmallOrder(publicKey)",
    "pointHasSmallOrder(encodedR)",
    "littleEndian(scalarS) >= L",
    'format: "raw-public"',
    "entry.issuer === carrier.principalId",
    "entry.entityId === carrier.entityId",
    'entry.role !== "commander"',
    "decoded.toString(\"base64url\") !== value",
  ]) {
    assert(source.includes(fragment), `source invariant missing: ${fragment}`);
  }
  for (const forbidden of [
    'header.alg !== "EdDSA"',
    "createPrivateKey",
    "privateKey",
    "jwk",
    "INSERT OR REPLACE",
  ]) {
    assert(!source.includes(forbidden), `forbidden source surface: ${forbidden}`);
  }
}

function main() {
  try {
    verifyBoundary({
      packageDocument: JSON.parse(readFileSync("package.json", "utf8")),
      lock: JSON.parse(readFileSync("package-lock.json", "utf8")),
      source: readFileSync("src/verifier.ts", "utf8"),
      tsconfig: JSON.parse(readFileSync("tsconfig.json", "utf8")),
      nodeVersion: process.versions.node,
      opensslVersion: process.versions.openssl,
    });
    process.stdout.write(
      "node verifier dependencies, runtime, and source boundary verified\n",
    );
  } catch (error) {
    process.stderr.write(
      `node verifier profile verification failed: ${
        error instanceof Error ? error.message : String(error)
      }\n`,
    );
    process.exitCode = 1;
  }
}

if (
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main();
}
