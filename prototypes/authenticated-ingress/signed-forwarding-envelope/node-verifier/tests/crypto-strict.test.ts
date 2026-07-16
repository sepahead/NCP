import { Buffer } from "node:buffer";
import { createPublicKey, verify as nodeVerify } from "node:crypto";
import assert from "node:assert/strict";
import test from "node:test";
import { PrototypeError } from "../src/errors.js";
import { strictEd25519Verify } from "../src/verifier.js";

const RFC8032_PUBLIC_KEY = Buffer.from(
  "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
  "hex",
);
const RFC8032_SIGNATURE = Buffer.from(
  "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155" +
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
  "hex",
);
const SMALL_ORDER = [
  "00".repeat(32),
  `01${"00".repeat(31)}`,
  "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
  "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
  `ec${"ff".repeat(30)}7f`,
  `ed${"ff".repeat(30)}7f`,
  `ee${"ff".repeat(30)}7f`,
].map((value) => Buffer.from(value, "hex"));

function assertCryptoReject(action: () => unknown): void {
  assert.throws(action, (error: unknown) => {
    assert(error instanceof PrototypeError);
    assert.equal(error.code, "crypto");
    return true;
  });
}

test("accepts the RFC 8032 empty-message known-answer vector", () => {
  assert.equal(
    strictEd25519Verify(RFC8032_PUBLIC_KEY, Buffer.alloc(0), RFC8032_SIGNATURE),
    true,
  );
});

test("prechecks reject a construction Node/OpenSSL accepts natively", () => {
  const zeroKey = Buffer.alloc(32);
  const zeroSignature = Buffer.alloc(64);
  const acceptedMessage = Buffer.from("protected.payload", "ascii");
  const imported = createPublicKey({
    key: zeroKey,
    format: "raw-public",
    asymmetricKeyType: "ed25519",
  });
  assert.equal(nodeVerify(null, acceptedMessage, imported, zeroSignature), true);
  assertCryptoReject(() =>
    strictEd25519Verify(zeroKey, acceptedMessage, zeroSignature),
  );
});

test("rejects every reviewed small-order public-key and R representative", () => {
  for (const point of SMALL_ORDER) {
    assertCryptoReject(() =>
      strictEd25519Verify(point, Buffer.alloc(0), RFC8032_SIGNATURE),
    );
    const signature = Buffer.from(RFC8032_SIGNATURE);
    point.copy(signature, 0);
    assertCryptoReject(() =>
      strictEd25519Verify(RFC8032_PUBLIC_KEY, Buffer.alloc(0), signature),
    );
    const signBitVariant = Buffer.from(point);
    signBitVariant[31] = signBitVariant[31]! ^ 0x80;
    assertCryptoReject(() =>
      strictEd25519Verify(signBitVariant, Buffer.alloc(0), RFC8032_SIGNATURE),
    );
    const signatureSignBitVariant = Buffer.from(RFC8032_SIGNATURE);
    signBitVariant.copy(signatureSignBitVariant, 0);
    assertCryptoReject(() =>
      strictEd25519Verify(
        RFC8032_PUBLIC_KEY,
        Buffer.alloc(0),
        signatureSignBitVariant,
      ),
    );
  }
});

test("rejects noncanonical points and scalar S plus the group order", () => {
  const noncanonical = Buffer.from(`f0${"ff".repeat(30)}7f`, "hex");
  assertCryptoReject(() =>
    strictEd25519Verify(noncanonical, Buffer.alloc(0), RFC8032_SIGNATURE),
  );

  const order =
    (1n << 252n) + 27742317777372353535851937790883648493n;
  const mutated = Buffer.from(RFC8032_SIGNATURE);
  let scalar = 0n;
  for (let index = 63; index >= 32; index -= 1) {
    scalar = (scalar << 8n) | BigInt(mutated[index]!);
  }
  scalar += order;
  for (let index = 32; index < 64; index += 1) {
    mutated[index] = Number(scalar & 0xffn);
    scalar >>= 8n;
  }
  assertCryptoReject(() =>
    strictEd25519Verify(RFC8032_PUBLIC_KEY, Buffer.alloc(0), mutated),
  );
});
