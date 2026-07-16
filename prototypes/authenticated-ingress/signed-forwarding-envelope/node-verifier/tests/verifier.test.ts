import { Buffer } from "node:buffer";
import { generateKeyPairSync } from "node:crypto";
import assert from "node:assert/strict";
import test from "node:test";
import { PrototypeError, type ErrorCode } from "../src/errors.js";
import {
  parseKeyManifest,
  RESULT_SCHEMA,
  verifyRequest,
} from "../src/verifier.js";
import {
  AUDIENCE,
  CARRIER,
  CARRIER_ENTITY,
  ENTITY,
  ISSUER,
  NOW,
  ROUTE,
  b64url,
  canonicalJson,
  clone,
  envelopeDocument,
  material,
  protectedDocument,
  rebuild,
  replaceEnvelope,
  requestBytes,
  sha256Hex,
  type Material,
  type MutableDocument,
} from "./common.js";

function assertReject(
  code: ErrorCode,
  action: () => unknown,
): PrototypeError {
  let caught: PrototypeError | undefined;
  assert.throws(action, (error: unknown) => {
    assert(error instanceof PrototypeError);
    caught = error;
    assert.equal(error.code, code);
    return true;
  });
  return caught!;
}

function verify(value: Material, request = value.request) {
  return verifyRequest(requestBytes(request));
}

test("accepts both message profiles and returns facts without authority", () => {
  for (const messageClass of ["command_frame", "step_request"] as const) {
    const value = material(messageClass);
    const result = verify(value);
    assert.equal(result.schema, RESULT_SCHEMA);
    assert.equal(result.signer_principal_id, ISSUER);
    assert.equal(result.signer_entity_id, ENTITY);
    assert.equal(result.signer_role, "commander");
    assert.equal(result.carrier_principal_id, CARRIER);
    assert.equal(result.carrier_entity_id, CARRIER_ENTITY);
    assert.equal(result.carrier_transport_role, "forwarder");
    assert.equal(result.carrier_profile, "b-over-a-forwarding");
    assert.equal(result.route, ROUTE);
    assert.equal(result.audience, AUDIENCE);
    assert.equal(result.payload_sha256, sha256Hex(value.payload));
    assert.equal(Object.hasOwn(result, "authority"), false);
    assert.equal(Object.hasOwn(result, "lease"), false);
    if (messageClass === "command_frame") {
      assert.deepEqual(result.payload_stream, {
        epoch: "3ef6f0ad-8ee6-4c6a-9e3f-86dc9ce849a1",
        sequence: 7,
      });
      assert.equal(result.payload_operation, null);
    } else {
      assert.equal(result.payload_stream, null);
      assert.deepEqual(result.payload_operation, {
        expected_state_version: 1,
        operation_id: "10000000-0000-4000-8000-000000000001",
        request_digest:
          "cf0d5f7440ea8ed8c5c8326182905ba66ceecca92ffccd592d56f9b9a42fe9df",
      });
    }
  }
});

test("rejects hostile JSON, encoding, and integer ambiguity", () => {
  const value = material();
  const cases: Array<[Buffer, ErrorCode]> = [
    [Buffer.from("x"), "json"],
    [Buffer.concat([Buffer.from([0xef, 0xbb, 0xbf]), requestBytes(value.request)]), "encoding"],
    [Buffer.from('{"schema":"x","sch\\u0065ma":"y"}'), "json"],
    [Buffer.from('{"schema":"\\ud800"}'), "json"],
    [Buffer.from([0xff]), "encoding"],
  ];
  for (const [bytes, code] of cases) {
    assertReject(code, () => verifyRequest(bytes));
  }

  const padded = clone(value.request);
  padded.envelope = `${String(padded.envelope)}=`;
  assertReject("encoding", () => verify(value, padded));

  const envelope = envelopeDocument(value.request);
  const protectedBytes = Buffer.from(String(envelope.protected), "base64url")
    .toString("ascii")
    .replace('"forwarding_sequence":1', '"forwarding_sequence":9007199254740992');
  envelope.protected = b64url(Buffer.from(protectedBytes, "ascii"));
  const changed = replaceEnvelope(value.request, canonicalJson(envelope));
  assertReject("bounds", () => verify(value, changed));

  const parsed = envelopeDocument(value.request);
  const duplicateOuter = Buffer.from(
    `{"payload":"${String(parsed.payload)}","payload":"${String(parsed.payload)}",` +
      `"protected":"${String(parsed.protected)}","signature":"${String(parsed.signature)}"}`,
    "ascii",
  );
  assertReject("json", () => verify(value, replaceEnvelope(value.request, duplicateOuter)));
});

test("rejects algorithm, unprotected key, changed bytes, and noncanonical S", () => {
  const value = material();
  const cases: MutableDocument[] = [];

  const wrongAlgorithm = protectedDocument(value.request);
  wrongAlgorithm.alg = "EdDSA";
  const wrongAlgorithmEnvelope = envelopeDocument(value.request);
  wrongAlgorithmEnvelope.protected = b64url(canonicalJson(wrongAlgorithm));
  cases.push(replaceEnvelope(value.request, canonicalJson(wrongAlgorithmEnvelope)));

  const remoteKey = protectedDocument(value.request);
  remoteKey.jwk = { kty: "OKP" };
  const remoteProtected = b64url(canonicalJson(remoteKey));
  const remotePayload = b64url(value.payload);
  const remoteEnvelope = envelopeDocument(value.request);
  remoteEnvelope.protected = remoteProtected;
  remoteEnvelope.payload = remotePayload;
  cases.push(replaceEnvelope(value.request, canonicalJson(remoteEnvelope)));

  const changedPayload = Buffer.from(value.payload);
  changedPayload[changedPayload.length - 2] =
    changedPayload[changedPayload.length - 2]! ^ 1;
  const changedEnvelope = envelopeDocument(value.request);
  changedEnvelope.payload = b64url(changedPayload);
  cases.push(replaceEnvelope(value.request, canonicalJson(changedEnvelope)));

  const scalarEnvelope = envelopeDocument(value.request);
  const signature = Buffer.from(String(scalarEnvelope.signature), "base64url");
  const order =
    (1n << 252n) + 27742317777372353535851937790883648493n;
  let scalar = 0n;
  for (let index = 63; index >= 32; index -= 1) {
    scalar = (scalar << 8n) | BigInt(signature[index]!);
  }
  scalar += order;
  for (let index = 32; index < 64; index += 1) {
    signature[index] = Number(scalar & 0xffn);
    scalar >>= 8n;
  }
  scalarEnvelope.signature = b64url(signature);
  cases.push(replaceEnvelope(value.request, canonicalJson(scalarEnvelope)));

  for (const request of cases) {
    assert.throws(() => verify(value, request), PrototypeError);
  }
});

test("rejects manifest widening, extra fields, and small-order keys", () => {
  const value = material();
  const extra = clone(value.manifest);
  extra.keys[0].extra = true;
  const extraBytes = canonicalJson(extra);
  assertReject("profile", () =>
    parseKeyManifest(extraBytes, sha256Hex(extraBytes)),
  );

  const wildcard = clone(value.manifest);
  wildcard.keys[0].grants[0].route = "ncp/*";
  const wildcardBytes = canonicalJson(wildcard);
  assertReject("profile", () =>
    parseKeyManifest(wildcardBytes, sha256Hex(wildcardBytes)),
  );

  const smallOrder = clone(value.manifest);
  const zeroKey = Buffer.alloc(32);
  smallOrder.keys[0].public_key = b64url(zeroKey);
  smallOrder.keys[0].kid = sha256Hex(zeroKey);
  const ncp = clone(value.ncp);
  ncp.kid = smallOrder.keys[0].kid;
  const request = rebuild(value, { manifest: smallOrder, ncp });
  assertReject("crypto", () => verify(value, request));
});

test("rejects carrier/signer confusion, mismatched routing, clock, payload, and direct mode", () => {
  const value = material();
  const requests: MutableDocument[] = [];

  const wrongCarrier = clone(value.carrier);
  wrongCarrier.route = "ncp/other";
  requests.push(rebuild(value, { carrier: wrongCarrier }));

  const signerCarrier = clone(value.carrier);
  signerCarrier.principal_id = ISSUER;
  requests.push(rebuild(value, { carrier: signerCarrier }));

  const signerEntityCarrier = clone(value.carrier);
  signerEntityCarrier.entity_id = ENTITY;
  requests.push(rebuild(value, { carrier: signerEntityCarrier }));

  const stale = clone(value.ncp);
  stale.expires_at_utc_ms = NOW - 1;
  requests.push(rebuild(value, { ncp: stale }));

  const wrongRoute = clone(value.ncp);
  wrongRoute.route = "ncp/other";
  requests.push(rebuild(value, { ncp: wrongRoute }));

  const payloadValue = JSON.parse(value.payload.toString("utf8")) as MutableDocument;
  payloadValue.session_id = "different-session";
  const payload = canonicalJson(payloadValue);
  const payloadMismatch = clone(value.ncp);
  payloadMismatch.payload_sha256 = sha256Hex(payload);
  requests.push(rebuild(value, { payload, ncp: payloadMismatch }));

  const direct = clone(value.endpoint);
  direct.mode = "a-direct";
  requests.push(rebuild(value, { endpoint: direct }));

  for (const request of requests) {
    assert.throws(() => verify(value, request), PrototypeError);
  }
});

test("key rotation overlap is exact and removed keys have no fallback", () => {
  const value = material();
  const next = generateKeyPairSync("ed25519");
  const nextPublic = Buffer.from(
    next.publicKey.export({ format: "raw-public" }) as Uint8Array,
  );
  const nextEntry = clone(value.manifest.keys[0]);
  nextEntry.kid = sha256Hex(nextPublic);
  nextEntry.public_key = b64url(nextPublic);
  nextEntry.key_epoch = 2;

  const overlap = clone(value.manifest);
  overlap.generation = 2;
  overlap.keys.push(nextEntry);
  const oldRequest = rebuild(value, { manifest: overlap });
  assert.equal(verify(value, oldRequest).kid, value.manifest.keys[0].kid);

  const nextNcp = clone(value.ncp);
  nextNcp.kid = nextEntry.kid;
  nextNcp.key_epoch = 2;
  const nextRequest = rebuild(value, {
    privateKey: next.privateKey,
    manifest: overlap,
    ncp: nextNcp,
  });
  assert.equal(verify(value, nextRequest).kid, nextEntry.kid);

  const removed = clone(overlap);
  removed.generation = 3;
  removed.keys = [nextEntry];
  const removedRequest = rebuild(value, { manifest: removed });
  assertReject("manifest", () => verify(value, removedRequest));
});

test("request, endpoint, carrier, header, and manifest fields are exact", () => {
  const value = material();
  for (const field of ["request", "endpoint", "carrier"] as const) {
    const request = clone(value.request);
    if (field === "request") request.extra = true;
    else request[field].extra = true;
    assertReject("profile", () => verify(value, request));
  }

  const header = protectedDocument(value.request);
  header.extra = true;
  const outer = envelopeDocument(value.request);
  outer.protected = b64url(canonicalJson(header));
  assertReject("profile", () =>
    verify(value, replaceEnvelope(value.request, canonicalJson(outer))),
  );

  const digestMismatch = clone(value.request);
  digestMismatch.manifest_sha256 = "0".repeat(64);
  assertReject("manifest", () => verify(value, digestMismatch));
});

test("route literals are ASCII rather than merely one-byte encoded", () => {
  const value = material();
  const route = "ncp/plánt/body-1/command";
  const manifest = clone(value.manifest);
  manifest.keys[0].grants[0].route = route;
  const ncp = clone(value.ncp);
  ncp.route = route;
  const endpoint = clone(value.endpoint);
  endpoint.route = route;
  const carrier = clone(value.carrier);
  carrier.route = route;
  const request = rebuild(value, { manifest, ncp, endpoint, carrier });
  assertReject("profile", () => verify(value, request));
});
