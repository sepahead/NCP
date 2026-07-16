import { Buffer } from "node:buffer";
import { createHash, createPublicKey, verify as nodeVerify } from "node:crypto";
import { PrototypeError } from "./errors.js";
import {
  exactMembers,
  isJsonObject,
  JSON_SAFE_INTEGER_MAX,
  type JsonObject,
  type JsonValue,
  strictJsonParse,
} from "./strict-json.js";

export const MANIFEST_SCHEMA = "ncp.prototype.forwarding-key-manifest.v1";
export const PROFILE = "ncp.prototype.signed-forwarding-envelope.v1";
export const TYPE = "ncp-forwarding-envelope+jws;v=1";
export const PAYLOAD_MEDIA_TYPE = "application/ncp+json;version=1.0";
export const CLOCK_POLICY = "unix-utc-ms-strict-v1";
export const REQUEST_SCHEMA = "ncp.prototype.signed-forwarding-node-request.v1";
export const RESULT_SCHEMA = "ncp.prototype.signed-forwarding-projection.v1";

export const MAX_OUTER_BYTES = 1_500_000;
export const MAX_PROTECTED_BYTES = 16_384;
export const MAX_PAYLOAD_BYTES = 1_048_576;
export const MAX_MANIFEST_BYTES = 65_536;
export const MAX_REQUEST_BYTES = 2_200_000;

const OUTER_LIMITS = {
  maxBytes: MAX_OUTER_BYTES,
  maxDepth: 3,
  maxNodes: 16,
  maxMembers: 4,
  maxStringBytes: MAX_OUTER_BYTES,
} as const;
const PROTECTED_LIMITS = {
  maxBytes: MAX_PROTECTED_BYTES,
  maxDepth: 6,
  maxNodes: 128,
  maxMembers: 32,
  maxStringBytes: 512,
} as const;
const MANIFEST_LIMITS = {
  maxBytes: MAX_MANIFEST_BYTES,
  maxDepth: 8,
  maxNodes: 2_048,
  maxMembers: 256,
  maxStringBytes: 512,
} as const;
const PAYLOAD_LIMITS = {
  maxBytes: MAX_PAYLOAD_BYTES,
  maxDepth: 32,
  maxNodes: 100_000,
  maxMembers: 4_096,
  maxStringBytes: 65_536,
} as const;
const REQUEST_LIMITS = {
  maxBytes: MAX_REQUEST_BYTES,
  maxDepth: 8,
  maxNodes: 256,
  maxMembers: 64,
  maxStringBytes: 2_000_000,
} as const;

const HEADER_MEMBERS = ["alg", "crit", "ncp", "typ"] as const;
const NCP_MEMBERS = [
  "audience",
  "clock_policy",
  "expires_at_utc_ms",
  "forwarding_epoch",
  "forwarding_sequence",
  "issued_at_utc_ms",
  "issuer",
  "key_epoch",
  "key_manifest_generation",
  "key_manifest_sha256",
  "kid",
  "message_class",
  "payload_media_type",
  "payload_operation",
  "payload_sha256",
  "payload_stream",
  "plane",
  "profile",
  "recovery_epoch",
  "route",
  "security_state_sha256",
  "session_generation",
  "session_id",
  "stable_core_sha256",
] as const;

const SHA256_HEX = /^[0-9a-f]{64}$/;
const BASE64URL = /^[A-Za-z0-9_-]+$/;
const UUID_V4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const ID_SEGMENT = /^[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?$/;
const P = (1n << 255n) - 19n;
const L = (1n << 252n) + 27742317777372353535851937790883648493n;

// Seven compressed representatives used by libsodium 1.0.18-1.0.20. The
// comparison masks the x-sign bit, so both sign encodings are rejected.
const SMALL_ORDER = [
  "00".repeat(32),
  `01${"00".repeat(31)}`,
  "26e8958fc2b227b045c3f489f2ef98f0d5dfac05d3c63339b13802886d53fc05",
  "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a",
  `ec${"ff".repeat(30)}7f`,
  `ed${"ff".repeat(30)}7f`,
  `ee${"ff".repeat(30)}7f`,
].map((value) => Buffer.from(value, "hex"));

export interface Grant {
  readonly route: string;
  readonly plane: string;
  readonly messageClass: string;
}

export interface KeyEntry {
  readonly kid: string;
  readonly publicKey: Buffer;
  readonly issuer: string;
  readonly entityId: string;
  readonly role: string;
  readonly keyEpoch: number;
  readonly grants: readonly Grant[];
}

export interface KeyManifest {
  readonly generation: number;
  readonly digest: string;
  readonly exactBytes: Buffer;
  readonly audience: string;
  readonly clockPolicy: string;
  readonly keys: readonly KeyEntry[];
}

export interface CarrierContext {
  readonly principalId: string;
  readonly entityId: string;
  readonly transportRole: string;
  readonly profile: string;
  readonly route: string;
  readonly plane: string;
  readonly messageClass: string;
  readonly audience: string;
  readonly stableCoreSha256: string;
  readonly securityStateSha256: string;
  readonly keyManifestSha256: string;
  readonly keyManifestGeneration: number;
}

export interface EndpointProfile {
  readonly route: string;
  readonly plane: string;
  readonly messageClass: string;
  readonly audience: string;
  readonly stableCoreSha256: string;
  readonly securityStateSha256: string;
  readonly keyManifestSha256: string;
  readonly keyManifestGeneration: number;
  readonly recoveryEpoch: number;
  readonly mode: string;
  readonly maxTtlMs: number;
  readonly maxClockSkewMs: number;
}

export interface VerifiedProjection {
  readonly schema: typeof RESULT_SCHEMA;
  readonly envelope_sha256: string;
  readonly protected_b64: string;
  readonly payload_b64: string;
  readonly signature_b64: string;
  readonly signer_principal_id: string;
  readonly signer_entity_id: string;
  readonly signer_role: string;
  readonly carrier_principal_id: string;
  readonly carrier_entity_id: string;
  readonly carrier_transport_role: string;
  readonly carrier_profile: string;
  readonly route: string;
  readonly plane: string;
  readonly message_class: string;
  readonly audience: string;
  readonly stable_core_sha256: string;
  readonly security_state_sha256: string;
  readonly kid: string;
  readonly key_epoch: number;
  readonly key_manifest_generation: number;
  readonly key_manifest_sha256: string;
  readonly clock_policy: string;
  readonly issued_at_utc_ms: number;
  readonly expires_at_utc_ms: number;
  readonly recovery_epoch: number;
  readonly forwarding_epoch: string;
  readonly forwarding_sequence: number;
  readonly session_id: string;
  readonly session_generation: string;
  readonly payload_sha256: string;
  readonly payload_stream: null | {
    readonly epoch: string;
    readonly sequence: number;
  };
  readonly payload_operation: null | {
    readonly expected_state_version: number;
    readonly operation_id: string;
    readonly request_digest: string;
  };
}

function sha256Hex(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function stringValue(value: JsonValue | undefined, field: string): string {
  if (typeof value !== "string") {
    throw new PrototypeError("profile", `${field} is not a string`);
  }
  return value;
}

function safeInteger(
  value: JsonValue | undefined,
  field: string,
  positive = false,
): number {
  if (
    typeof value !== "number" ||
    !Number.isSafeInteger(value) ||
    Math.abs(value) > JSON_SAFE_INTEGER_MAX
  ) {
    throw new PrototypeError("profile", `${field} is not a JSON-safe integer`);
  }
  if (positive ? value <= 0 : value < 0) {
    throw new PrototypeError(
      "profile",
      `${field} must be ${positive ? "positive" : "non-negative"}`,
    );
  }
  return value;
}

function sha256Value(value: JsonValue | undefined, field: string): string {
  const text = stringValue(value, field);
  if (!SHA256_HEX.test(text)) {
    throw new PrototypeError("profile", `${field} is not lowercase SHA-256`);
  }
  return text;
}

function idValue(value: JsonValue | undefined, field: string): string {
  const text = stringValue(value, field);
  if (!ID_SEGMENT.test(text)) {
    throw new PrototypeError("profile", `${field} is not a canonical identifier`);
  }
  return text;
}

function uuidV4(value: JsonValue | undefined, field: string): string {
  const text = stringValue(value, field);
  if (!UUID_V4.test(text)) {
    throw new PrototypeError("profile", `${field} is not a canonical UUIDv4`);
  }
  return text;
}

function literal(value: JsonValue | undefined, field: string, maximum: number): string {
  const text = stringValue(value, field);
  if (
    text.length < 1 ||
    text.length > maximum ||
    [...text].some(
      (character) =>
        character.codePointAt(0)! > 0x7f ||
        /\s/.test(character) ||
        character.codePointAt(0)! < 0x20 ||
        "*?[]{}#".includes(character),
    )
  ) {
    throw new PrototypeError("profile", `${field} is not a bounded literal`);
  }
  return text;
}

export function decodeCanonicalBase64url(
  value: JsonValue | string | undefined,
  maximum: number,
): Buffer {
  if (
    typeof value !== "string" ||
    value.length < 1 ||
    !BASE64URL.test(value) ||
    value.length % 4 === 1
  ) {
    throw new PrototypeError("encoding", "base64url token is not canonical");
  }
  if (Math.floor((value.length * 3) / 4) > maximum) {
    throw new PrototypeError("bounds", "base64url decoded size exceeds the limit");
  }
  const decoded = Buffer.from(value, "base64url");
  if (decoded.byteLength > maximum || decoded.toString("base64url") !== value) {
    throw new PrototypeError("encoding", "base64url trailing bits are noncanonical");
  }
  return decoded;
}

function littleEndian(bytes: Uint8Array): bigint {
  let result = 0n;
  for (let index = bytes.byteLength - 1; index >= 0; index -= 1) {
    result = (result << 8n) | BigInt(bytes[index]!);
  }
  return result;
}

function pointIsCanonical(point: Buffer): boolean {
  const copy = Buffer.from(point);
  copy[31] = copy[31]! & 0x7f;
  return littleEndian(copy) < P;
}

function pointHasSmallOrder(point: Buffer): boolean {
  return SMALL_ORDER.some((candidate) => {
    let difference = 0;
    for (let index = 0; index < 31; index += 1) {
      difference |= point[index]! ^ candidate[index]!;
    }
    difference |= (point[31]! & 0x7f) ^ candidate[31]!;
    return difference === 0;
  });
}

export function strictEd25519Verify(
  publicKey: Buffer,
  signingInput: Buffer,
  signature: Buffer,
): boolean {
  if (publicKey.byteLength !== 32 || signature.byteLength !== 64) {
    throw new PrototypeError("crypto", "Ed25519 key or signature length is invalid");
  }
  const encodedR = signature.subarray(0, 32);
  const scalarS = signature.subarray(32);
  if (
    !pointIsCanonical(publicKey) ||
    pointHasSmallOrder(publicKey) ||
    !pointIsCanonical(encodedR) ||
    pointHasSmallOrder(encodedR) ||
    littleEndian(scalarS) >= L
  ) {
    throw new PrototypeError("crypto", "strict Ed25519 encoding checks rejected");
  }
  try {
    const key = createPublicKey({
      key: publicKey,
      format: "raw-public",
      asymmetricKeyType: "ed25519",
    });
    if (key.asymmetricKeyType !== "ed25519") {
      throw new PrototypeError("crypto", "imported key is not Ed25519");
    }
    return nodeVerify(null, signingInput, key, signature);
  } catch (error) {
    if (error instanceof PrototypeError) throw error;
    throw new PrototypeError("crypto", `Node Ed25519 verification failed: ${String(error)}`);
  }
}

export function parseKeyManifest(exactBytes: Buffer, expectedSha256: string): KeyManifest {
  if (exactBytes.byteLength < 1 || exactBytes.byteLength > MAX_MANIFEST_BYTES) {
    throw new PrototypeError("bounds", "manifest byte length is outside the profile bound");
  }
  if (!SHA256_HEX.test(expectedSha256) || sha256Hex(exactBytes) !== expectedSha256) {
    throw new PrototypeError("manifest", "manifest exact-byte digest mismatch");
  }
  const value = exactMembers(
    strictJsonParse(exactBytes, MANIFEST_LIMITS),
    ["audience", "clock_policy", "default_deny", "generation", "keys", "schema"],
    "key manifest",
  );
  if (
    value.schema !== MANIFEST_SCHEMA ||
    value.default_deny !== true ||
    value.clock_policy !== CLOCK_POLICY
  ) {
    throw new PrototypeError("manifest", "manifest profile is unknown or permissive");
  }
  const generation = safeInteger(value.generation, "manifest generation", true);
  const audience = idValue(value.audience, "manifest audience");
  if (!Array.isArray(value.keys) || value.keys.length < 1 || value.keys.length > 64) {
    throw new PrototypeError("manifest", "manifest key count is outside 1..=64");
  }
  const keys: KeyEntry[] = [];
  const kids = new Set<string>();
  const issuerEpochs = new Set<string>();
  const issuerIdentity = new Map<string, string>();
  const entityIssuer = new Map<string, string>();
  for (const [index, raw] of value.keys.entries()) {
    const entry = exactMembers(
      raw,
      ["entity_id", "grants", "issuer", "key_epoch", "kid", "public_key", "role"],
      `manifest keys[${index}]`,
    );
    const kid = sha256Value(entry.kid, `manifest keys[${index}].kid`);
    const publicKey = decodeCanonicalBase64url(entry.public_key, 32);
    if (publicKey.byteLength !== 32 || sha256Hex(publicKey) !== kid) {
      throw new PrototypeError(
        "manifest",
        "manifest public key does not match its content-addressed kid",
      );
    }
    const issuer = idValue(entry.issuer, `manifest keys[${index}].issuer`);
    const entityId = idValue(entry.entity_id, `manifest keys[${index}].entity_id`);
    const role = stringValue(entry.role, `manifest keys[${index}].role`);
    if (!["commander", "body", "observer", "operator"].includes(role)) {
      throw new PrototypeError("manifest", "manifest signer role is unknown");
    }
    const keyEpoch = safeInteger(
      entry.key_epoch,
      `manifest keys[${index}].key_epoch`,
      true,
    );
    if (!Array.isArray(entry.grants) || entry.grants.length < 1 || entry.grants.length > 32) {
      throw new PrototypeError("manifest", "manifest grant count is outside 1..=32");
    }
    const grants: Grant[] = [];
    const seenGrants = new Set<string>();
    for (const [grantIndex, grantRaw] of entry.grants.entries()) {
      const grant = exactMembers(
        grantRaw,
        ["message_class", "plane", "route"],
        `manifest keys[${index}].grants[${grantIndex}]`,
      );
      const route = literal(grant.route, "manifest grant route", 256);
      const plane = stringValue(grant.plane, "manifest grant plane");
      if (!["control", "perception", "action", "observation"].includes(plane)) {
        throw new PrototypeError("manifest", "manifest grant plane is unknown");
      }
      const messageClass = literal(
        grant.message_class,
        "manifest grant message class",
        64,
      );
      const grantKey = `${route}\u0000${plane}\u0000${messageClass}`;
      if (seenGrants.has(grantKey)) {
        throw new PrototypeError("manifest", "manifest contains a duplicate grant");
      }
      seenGrants.add(grantKey);
      grants.push({ route, plane, messageClass });
    }
    const identity = `${entityId}\u0000${role}`;
    if (issuerIdentity.has(issuer) && issuerIdentity.get(issuer) !== identity) {
      throw new PrototypeError(
        "manifest",
        "one issuer cannot change entity or role across key epochs",
      );
    }
    if (entityIssuer.has(entityId) && entityIssuer.get(entityId) !== issuer) {
      throw new PrototypeError(
        "manifest",
        "one entity cannot belong to multiple signer issuers",
      );
    }
    const issuerEpoch = `${issuer}\u0000${keyEpoch}`;
    if (kids.has(kid) || issuerEpochs.has(issuerEpoch)) {
      throw new PrototypeError(
        "manifest",
        "manifest kid and issuer/key-epoch pairs must be unique",
      );
    }
    kids.add(kid);
    issuerEpochs.add(issuerEpoch);
    issuerIdentity.set(issuer, identity);
    entityIssuer.set(entityId, issuer);
    keys.push({
      kid,
      publicKey: Buffer.from(publicKey),
      issuer,
      entityId,
      role,
      keyEpoch,
      grants,
    });
  }
  return {
    generation,
    digest: expectedSha256,
    exactBytes: Buffer.from(exactBytes),
    audience,
    clockPolicy: CLOCK_POLICY,
    keys,
  };
}

function parseCarrier(value: JsonValue | undefined): CarrierContext {
  const object = exactMembers(
    value,
    [
      "audience",
      "entity_id",
      "key_manifest_generation",
      "key_manifest_sha256",
      "message_class",
      "plane",
      "principal_id",
      "profile",
      "route",
      "security_state_sha256",
      "stable_core_sha256",
      "transport_role",
    ],
    "carrier context",
  );
  const plane = stringValue(object.plane, "carrier plane");
  if (!["control", "perception", "action", "observation"].includes(plane)) {
    throw new PrototypeError("profile", "carrier plane is unknown");
  }
  return {
    principalId: idValue(object.principal_id, "carrier principal_id"),
    entityId: idValue(object.entity_id, "carrier entity_id"),
    transportRole: stringValue(object.transport_role, "carrier transport_role"),
    profile: stringValue(object.profile, "carrier profile"),
    route: literal(object.route, "carrier route", 256),
    plane,
    messageClass: literal(object.message_class, "carrier message class", 64),
    audience: idValue(object.audience, "carrier audience"),
    stableCoreSha256: sha256Value(object.stable_core_sha256, "carrier stable-core digest"),
    securityStateSha256: sha256Value(
      object.security_state_sha256,
      "carrier security-state digest",
    ),
    keyManifestSha256: sha256Value(
      object.key_manifest_sha256,
      "carrier key-manifest digest",
    ),
    keyManifestGeneration: safeInteger(
      object.key_manifest_generation,
      "carrier key-manifest generation",
      true,
    ),
  };
}

function parseEndpoint(value: JsonValue | undefined): EndpointProfile {
  const object = exactMembers(
    value,
    [
      "audience",
      "key_manifest_generation",
      "key_manifest_sha256",
      "max_clock_skew_ms",
      "max_ttl_ms",
      "message_class",
      "mode",
      "plane",
      "recovery_epoch",
      "route",
      "security_state_sha256",
      "stable_core_sha256",
    ],
    "endpoint profile",
  );
  const plane = stringValue(object.plane, "endpoint plane");
  if (!["control", "perception", "action", "observation"].includes(plane)) {
    throw new PrototypeError("profile", "endpoint plane is unknown");
  }
  const messageClass = stringValue(object.message_class, "endpoint message class");
  if (!["command_frame", "step_request"].includes(messageClass)) {
    throw new PrototypeError("profile", "prototype message class is unsupported");
  }
  return {
    route: literal(object.route, "endpoint route", 256),
    plane,
    messageClass,
    audience: idValue(object.audience, "endpoint audience"),
    stableCoreSha256: sha256Value(
      object.stable_core_sha256,
      "endpoint stable-core digest",
    ),
    securityStateSha256: sha256Value(
      object.security_state_sha256,
      "endpoint security-state digest",
    ),
    keyManifestSha256: sha256Value(
      object.key_manifest_sha256,
      "endpoint key-manifest digest",
    ),
    keyManifestGeneration: safeInteger(
      object.key_manifest_generation,
      "endpoint key-manifest generation",
      true,
    ),
    recoveryEpoch: safeInteger(object.recovery_epoch, "endpoint recovery_epoch", true),
    mode: stringValue(object.mode, "endpoint mode"),
    maxTtlMs: safeInteger(object.max_ttl_ms, "endpoint maximum TTL", true),
    maxClockSkewMs: safeInteger(object.max_clock_skew_ms, "endpoint clock skew"),
  };
}

function exactGrant(entry: KeyEntry, profile: EndpointProfile): boolean {
  return entry.grants.some(
    (grant) =>
      grant.route === profile.route &&
      grant.plane === profile.plane &&
      grant.messageClass === profile.messageClass,
  );
}

function validateContext(
  ncp: JsonObject,
  profile: EndpointProfile,
  carrier: CarrierContext,
  manifest: KeyManifest,
  nowUtcMs: number,
): { entry: KeyEntry; issued: number; expires: number } {
  if (profile.mode !== "b-over-a-forwarding") {
    throw new PrototypeError("profile", "endpoint is not forwarding-only");
  }
  if (
    carrier.transportRole !== "forwarder" ||
    carrier.profile !== "b-over-a-forwarding"
  ) {
    throw new PrototypeError("profile", "carrier is not pinned to forwarding-only");
  }
  if (
    carrier.route !== profile.route ||
    carrier.plane !== profile.plane ||
    carrier.messageClass !== profile.messageClass ||
    carrier.audience !== profile.audience ||
    carrier.stableCoreSha256 !== profile.stableCoreSha256 ||
    carrier.securityStateSha256 !== profile.securityStateSha256 ||
    carrier.keyManifestSha256 !== profile.keyManifestSha256 ||
    carrier.keyManifestGeneration !== profile.keyManifestGeneration
  ) {
    throw new PrototypeError("profile", "carrier and endpoint profile are incongruent");
  }
  if (
    manifest.digest !== profile.keyManifestSha256 ||
    manifest.generation !== profile.keyManifestGeneration ||
    manifest.audience !== profile.audience
  ) {
    throw new PrototypeError("manifest", "current manifest and endpoint are incongruent");
  }
  if (ncp.profile !== PROFILE || ncp.payload_media_type !== PAYLOAD_MEDIA_TYPE) {
    throw new PrototypeError("profile", "forwarding profile or media type mismatch");
  }
  const expected: Record<string, string | number> = {
    route: profile.route,
    plane: profile.plane,
    message_class: profile.messageClass,
    audience: profile.audience,
    stable_core_sha256: profile.stableCoreSha256,
    security_state_sha256: profile.securityStateSha256,
    key_manifest_sha256: profile.keyManifestSha256,
    key_manifest_generation: profile.keyManifestGeneration,
    recovery_epoch: profile.recoveryEpoch,
    clock_policy: CLOCK_POLICY,
  };
  for (const [field, wanted] of Object.entries(expected)) {
    if (ncp[field] !== wanted) {
      throw new PrototypeError("profile", `protected ${field} mismatch`);
    }
  }
  const kid = sha256Value(ncp.kid, "protected kid");
  const entry = manifest.keys.find((candidate) => candidate.kid === kid);
  if (entry === undefined) {
    throw new PrototypeError("manifest", "kid is absent from the current manifest");
  }
  const issuer = idValue(ncp.issuer, "protected issuer");
  const keyEpoch = safeInteger(ncp.key_epoch, "protected key_epoch", true);
  if (issuer !== entry.issuer || keyEpoch !== entry.keyEpoch) {
    throw new PrototypeError("manifest", "protected signer or key epoch mismatch");
  }
  if (
    entry.issuer === carrier.principalId ||
    entry.entityId === carrier.entityId
  ) {
    throw new PrototypeError(
      "profile",
      "operation signer principal/entity cannot equal its carrier",
    );
  }
  if (entry.role !== "commander") {
    throw new PrototypeError("profile", "prototype command signer is not a commander");
  }
  if (!exactGrant(entry, profile)) {
    throw new PrototypeError("manifest", "signer lacks the exact endpoint grant");
  }
  const issued = safeInteger(ncp.issued_at_utc_ms, "protected issued_at");
  const expires = safeInteger(ncp.expires_at_utc_ms, "protected expires_at");
  if (expires <= issued || expires - issued > profile.maxTtlMs) {
    throw new PrototypeError("profile", "forwarding envelope TTL is invalid");
  }
  if (
    nowUtcMs + profile.maxClockSkewMs < issued ||
    nowUtcMs - profile.maxClockSkewMs > expires
  ) {
    throw new PrototypeError("profile", "forwarding envelope is not currently valid");
  }
  return { entry, issued, expires };
}

function payloadSemantics(
  payload: Buffer,
  ncp: JsonObject,
  profile: EndpointProfile,
): Pick<VerifiedProjection, "payload_stream" | "payload_operation"> {
  const value = strictJsonParse(payload, PAYLOAD_LIMITS, true);
  if (!isJsonObject(value)) {
    throw new PrototypeError("payload", "NCP payload is not an object");
  }
  if (value.ncp_version !== "1.0" || value.kind !== profile.messageClass) {
    throw new PrototypeError("payload", "NCP version or message class mismatch");
  }
  if (value.session_id !== ncp.session_id) {
    throw new PrototypeError("payload", "payload session_id mismatch");
  }
  if (!isJsonObject(value.session) || value.session.generation !== ncp.session_generation) {
    throw new PrototypeError("payload", "payload session generation mismatch");
  }
  if (profile.messageClass === "command_frame") {
    if (ncp.payload_operation !== null) {
      throw new PrototypeError("payload", "streamed command cannot bind an operation");
    }
    const protectedStream = exactMembers(
      ncp.payload_stream,
      ["epoch", "sequence"],
      "protected payload_stream",
    );
    if (!isJsonObject(value.stream)) {
      throw new PrototypeError("payload", "command payload has no stream position");
    }
    const epoch = uuidV4(value.stream.epoch, "payload stream epoch");
    const sequence = safeInteger(value.stream.seq, "payload stream sequence", true);
    if (protectedStream.epoch !== epoch || protectedStream.sequence !== sequence) {
      throw new PrototypeError("payload", "protected stream binding mismatch");
    }
    return {
      payload_stream: { epoch, sequence },
      payload_operation: null,
    };
  }
  if (ncp.payload_stream !== null) {
    throw new PrototypeError("payload", "operation request cannot bind a payload stream");
  }
  const protectedOperation = exactMembers(
    ncp.payload_operation,
    ["expected_state_version", "operation_id", "request_digest"],
    "protected payload_operation",
  );
  if (!isJsonObject(value.operation)) {
    throw new PrototypeError("payload", "step request has no operation context");
  }
  const operationId = uuidV4(value.operation.operation_id, "payload operation_id");
  const expectedStateVersion = safeInteger(
    value.operation.expected_state_version,
    "payload expected_state_version",
  );
  const requestDigest = sha256Value(
    value.operation.request_digest,
    "payload request_digest",
  );
  if (value.operation.session_epoch !== ncp.session_generation) {
    throw new PrototypeError("payload", "operation session generation mismatch");
  }
  if (
    protectedOperation.operation_id !== operationId ||
    protectedOperation.expected_state_version !== expectedStateVersion ||
    protectedOperation.request_digest !== requestDigest
  ) {
    throw new PrototypeError("payload", "protected operation binding mismatch");
  }
  return {
    payload_stream: null,
    payload_operation: {
      operation_id: operationId,
      expected_state_version: expectedStateVersion,
      request_digest: requestDigest,
    },
  };
}

export function verifyEnvelope(
  envelope: Buffer,
  manifest: KeyManifest,
  profile: EndpointProfile,
  carrier: CarrierContext,
  nowUtcMs: number,
): VerifiedProjection {
  if (!Number.isSafeInteger(nowUtcMs) || nowUtcMs < 0) {
    throw new PrototypeError("profile", "current time is not a JSON-safe integer");
  }
  const outer = exactMembers(
    strictJsonParse(envelope, OUTER_LIMITS),
    ["payload", "protected", "signature"],
    "flattened JWS",
  );
  const protectedB64 = stringValue(outer.protected, "flattened JWS protected");
  const payloadB64 = stringValue(outer.payload, "flattened JWS payload");
  const signatureB64 = stringValue(outer.signature, "flattened JWS signature");
  const protectedBytes = decodeCanonicalBase64url(
    protectedB64,
    MAX_PROTECTED_BYTES,
  );
  const payload = decodeCanonicalBase64url(payloadB64, MAX_PAYLOAD_BYTES);
  const signature = decodeCanonicalBase64url(signatureB64, 64);
  if (signature.byteLength !== 64) {
    throw new PrototypeError("crypto", "Ed25519 signature is not exactly 64 bytes");
  }
  const header = exactMembers(
    strictJsonParse(protectedBytes, PROTECTED_LIMITS),
    HEADER_MEMBERS,
    "protected header",
  );
  if (
    header.alg !== "Ed25519" ||
    header.typ !== TYPE ||
    !Array.isArray(header.crit) ||
    header.crit.length !== 1 ||
    header.crit[0] !== "ncp"
  ) {
    throw new PrototypeError("profile", "algorithm, type, or critical profile mismatch");
  }
  const ncp = exactMembers(header.ncp, NCP_MEMBERS, "protected ncp context");
  const { entry, issued, expires } = validateContext(
    ncp,
    profile,
    carrier,
    manifest,
    nowUtcMs,
  );
  const signingInput = Buffer.from(`${protectedB64}.${payloadB64}`, "ascii");
  if (!strictEd25519Verify(entry.publicKey, signingInput, signature)) {
    throw new PrototypeError("crypto", "strict Ed25519 verification rejected");
  }
  const payloadSha256 = sha256Hex(payload);
  if (sha256Value(ncp.payload_sha256, "protected payload digest") !== payloadSha256) {
    throw new PrototypeError("payload", "protected payload digest mismatch");
  }
  const sessionId = idValue(ncp.session_id, "protected session_id");
  const sessionGeneration = uuidV4(
    ncp.session_generation,
    "protected session_generation",
  );
  const forwardingEpoch = uuidV4(ncp.forwarding_epoch, "protected forwarding_epoch");
  const forwardingSequence = safeInteger(
    ncp.forwarding_sequence,
    "protected forwarding_sequence",
    true,
  );
  const payloadContext = payloadSemantics(payload, ncp, profile);
  return {
    schema: RESULT_SCHEMA,
    envelope_sha256: sha256Hex(envelope),
    protected_b64: protectedB64,
    payload_b64: payloadB64,
    signature_b64: signatureB64,
    signer_principal_id: entry.issuer,
    signer_entity_id: entry.entityId,
    signer_role: entry.role,
    carrier_principal_id: carrier.principalId,
    carrier_entity_id: carrier.entityId,
    carrier_transport_role: carrier.transportRole,
    carrier_profile: carrier.profile,
    route: profile.route,
    plane: profile.plane,
    message_class: profile.messageClass,
    audience: profile.audience,
    stable_core_sha256: profile.stableCoreSha256,
    security_state_sha256: profile.securityStateSha256,
    kid: entry.kid,
    key_epoch: entry.keyEpoch,
    key_manifest_generation: manifest.generation,
    key_manifest_sha256: manifest.digest,
    clock_policy: CLOCK_POLICY,
    issued_at_utc_ms: issued,
    expires_at_utc_ms: expires,
    recovery_epoch: profile.recoveryEpoch,
    forwarding_epoch: forwardingEpoch,
    forwarding_sequence: forwardingSequence,
    session_id: sessionId,
    session_generation: sessionGeneration,
    payload_sha256: payloadSha256,
    ...payloadContext,
  };
}

export function verifyRequest(requestBytes: Buffer): VerifiedProjection {
  const request = exactMembers(
    strictJsonParse(requestBytes, REQUEST_LIMITS),
    [
      "carrier",
      "endpoint",
      "envelope",
      "manifest",
      "manifest_sha256",
      "now_utc_ms",
      "schema",
    ],
    "node verifier request",
  );
  if (request.schema !== REQUEST_SCHEMA) {
    throw new PrototypeError("profile", "node verifier request schema is unknown");
  }
  const manifestSha256 = sha256Value(request.manifest_sha256, "request manifest digest");
  const manifestBytes = decodeCanonicalBase64url(
    request.manifest,
    MAX_MANIFEST_BYTES,
  );
  const envelope = decodeCanonicalBase64url(request.envelope, MAX_OUTER_BYTES);
  const profile = parseEndpoint(request.endpoint);
  const carrier = parseCarrier(request.carrier);
  const nowUtcMs = safeInteger(request.now_utc_ms, "request current time");
  const manifest = parseKeyManifest(manifestBytes, manifestSha256);
  return verifyEnvelope(envelope, manifest, profile, carrier, nowUtcMs);
}
