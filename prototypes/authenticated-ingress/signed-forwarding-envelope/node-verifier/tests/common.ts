import { Buffer } from "node:buffer";
import {
  createHash,
  generateKeyPairSync,
  sign,
  type KeyObject,
} from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  CLOCK_POLICY,
  MANIFEST_SCHEMA,
  PAYLOAD_MEDIA_TYPE,
  PROFILE,
  REQUEST_SCHEMA,
  TYPE,
} from "../src/verifier.js";

export const NOW = 1_700_000_000_000;
export const AUDIENCE = "crebain-body-1";
export const ISSUER = "controller-principal-1";
export const ENTITY = "pid-controller-1";
export const CARRIER = "ingress-forwarder-1";
export const CARRIER_ENTITY = "ingress-process-1";
export const ROUTE = "ncp/plant/body-1/command";
export const STABLE_CORE = "1".repeat(64);
export const SECURITY_STATE = "2".repeat(64);
export const FORWARDING_EPOCH = "30000000-0000-4000-8000-000000000003";

export type MessageClass = "command_frame" | "step_request";
export type MutableDocument = Record<string, any>;

export interface Material {
  readonly privateKey: KeyObject;
  readonly publicKey: Buffer;
  readonly payload: Buffer;
  readonly manifest: MutableDocument;
  readonly ncp: MutableDocument;
  readonly endpoint: MutableDocument;
  readonly carrier: MutableDocument;
  readonly request: MutableDocument;
}

export function sha256Hex(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

export function b64url(bytes: Uint8Array): string {
  return Buffer.from(bytes).toString("base64url");
}

function sorted(value: any): any {
  if (Array.isArray(value)) return value.map(sorted);
  if (value !== null && typeof value === "object") {
    const output: MutableDocument = {};
    for (const key of Object.keys(value).sort()) output[key] = sorted(value[key]);
    return output;
  }
  return value;
}

export function canonicalJson(value: any): Buffer {
  return Buffer.from(JSON.stringify(sorted(value)), "utf8");
}

export function clone<T>(value: T): T {
  return structuredClone(value);
}

export function buildEnvelope(
  privateKey: KeyObject,
  ncp: MutableDocument,
  payload: Buffer,
): Buffer {
  const protectedBytes = canonicalJson({
    alg: "Ed25519",
    crit: ["ncp"],
    ncp,
    typ: TYPE,
  });
  const protectedB64 = b64url(protectedBytes);
  const payloadB64 = b64url(payload);
  const signature = sign(
    null,
    Buffer.from(`${protectedB64}.${payloadB64}`, "ascii"),
    privateKey,
  );
  return canonicalJson({
    payload: payloadB64,
    protected: protectedB64,
    signature: b64url(signature),
  });
}

export function requestBytes(request: MutableDocument): Buffer {
  return canonicalJson(request);
}

export function envelopeDocument(request: MutableDocument): MutableDocument {
  return JSON.parse(
    Buffer.from(String(request.envelope), "base64url").toString("utf8"),
  ) as MutableDocument;
}

export function protectedDocument(request: MutableDocument): MutableDocument {
  const envelope = envelopeDocument(request);
  return JSON.parse(
    Buffer.from(String(envelope.protected), "base64url").toString("utf8"),
  ) as MutableDocument;
}

export function replaceEnvelope(
  request: MutableDocument,
  envelope: Uint8Array,
): MutableDocument {
  const copy = clone(request);
  copy.envelope = b64url(envelope);
  return copy;
}

export function rebuild(
  value: Material,
  options: {
    readonly privateKey?: KeyObject;
    readonly payload?: Buffer;
    readonly manifest?: MutableDocument;
    readonly ncp?: MutableDocument;
    readonly endpoint?: MutableDocument;
    readonly carrier?: MutableDocument;
    readonly synchronizeManifest?: boolean;
  } = {},
): MutableDocument {
  const privateKey = options.privateKey ?? value.privateKey;
  const payload = options.payload ?? value.payload;
  const manifest = clone(options.manifest ?? value.manifest);
  const ncp = clone(options.ncp ?? value.ncp);
  const endpoint = clone(options.endpoint ?? value.endpoint);
  const carrier = clone(options.carrier ?? value.carrier);
  const manifestBytes = canonicalJson(manifest);
  const digest = sha256Hex(manifestBytes);
  if (options.synchronizeManifest !== false) {
    ncp.key_manifest_sha256 = digest;
    ncp.key_manifest_generation = manifest.generation;
    endpoint.key_manifest_sha256 = digest;
    endpoint.key_manifest_generation = manifest.generation;
    carrier.key_manifest_sha256 = digest;
    carrier.key_manifest_generation = manifest.generation;
  }
  const envelope = buildEnvelope(privateKey, ncp, payload);
  return {
    carrier,
    endpoint,
    envelope: b64url(envelope),
    manifest: b64url(manifestBytes),
    manifest_sha256: digest,
    now_utc_ms: NOW,
    schema: REQUEST_SCHEMA,
  };
}

export function material(messageClass: MessageClass = "command_frame"): Material {
  const { privateKey, publicKey: publicKeyObject } = generateKeyPairSync("ed25519");
  const publicKey = Buffer.from(
    publicKeyObject.export({ format: "raw-public" }) as Uint8Array,
  );
  const payload = readFileSync(
    resolve(
      process.cwd(),
      "../../../../conformance/vectors",
      `${messageClass}.json`,
    ),
  );
  const payloadValue = JSON.parse(payload.toString("utf8")) as MutableDocument;
  const kid = sha256Hex(publicKey);
  const manifest: MutableDocument = {
    audience: AUDIENCE,
    clock_policy: CLOCK_POLICY,
    default_deny: true,
    generation: 1,
    keys: [
      {
        entity_id: ENTITY,
        grants: [
          {
            message_class: messageClass,
            plane: "control",
            route: ROUTE,
          },
        ],
        issuer: ISSUER,
        key_epoch: 1,
        kid,
        public_key: b64url(publicKey),
        role: "commander",
      },
    ],
    schema: MANIFEST_SCHEMA,
  };
  const manifestBytes = canonicalJson(manifest);
  const manifestDigest = sha256Hex(manifestBytes);
  const stream =
    messageClass === "command_frame"
      ? {
          epoch: payloadValue.stream.epoch,
          sequence: payloadValue.stream.seq,
        }
      : null;
  const operation =
    messageClass === "step_request"
      ? {
          expected_state_version: payloadValue.operation.expected_state_version,
          operation_id: payloadValue.operation.operation_id,
          request_digest: payloadValue.operation.request_digest,
        }
      : null;
  const ncp: MutableDocument = {
    audience: AUDIENCE,
    clock_policy: CLOCK_POLICY,
    expires_at_utc_ms: NOW + 4_000,
    forwarding_epoch: FORWARDING_EPOCH,
    forwarding_sequence: 1,
    issued_at_utc_ms: NOW,
    issuer: ISSUER,
    key_epoch: 1,
    key_manifest_generation: 1,
    key_manifest_sha256: manifestDigest,
    kid,
    message_class: messageClass,
    payload_media_type: PAYLOAD_MEDIA_TYPE,
    payload_operation: operation,
    payload_sha256: sha256Hex(payload),
    payload_stream: stream,
    plane: "control",
    profile: PROFILE,
    recovery_epoch: 1,
    route: ROUTE,
    security_state_sha256: SECURITY_STATE,
    session_generation: payloadValue.session.generation,
    session_id: payloadValue.session_id,
    stable_core_sha256: STABLE_CORE,
  };
  const endpoint: MutableDocument = {
    audience: AUDIENCE,
    key_manifest_generation: 1,
    key_manifest_sha256: manifestDigest,
    max_clock_skew_ms: 1_000,
    max_ttl_ms: 5_000,
    message_class: messageClass,
    mode: "b-over-a-forwarding",
    plane: "control",
    recovery_epoch: 1,
    route: ROUTE,
    security_state_sha256: SECURITY_STATE,
    stable_core_sha256: STABLE_CORE,
  };
  const carrier: MutableDocument = {
    audience: AUDIENCE,
    entity_id: CARRIER_ENTITY,
    key_manifest_generation: 1,
    key_manifest_sha256: manifestDigest,
    message_class: messageClass,
    plane: "control",
    principal_id: CARRIER,
    profile: "b-over-a-forwarding",
    route: ROUTE,
    security_state_sha256: SECURITY_STATE,
    stable_core_sha256: STABLE_CORE,
    transport_role: "forwarder",
  };
  const partial = {
    privateKey,
    publicKey,
    payload,
    manifest,
    ncp,
    endpoint,
    carrier,
  };
  return {
    ...partial,
    request: rebuild(partial as Material),
  };
}
