/**
 * Neuro-Cybernetic Protocol (NCP) — transport-agnostic TypeScript client.
 *
 * Wire-identical to the normative `proto/ncp.proto` contract (proto-native) and the
 * Rust (`ncp-core`) and Python peers: every reply and enum type is imported from
 * the generated bindings (`./generated`, the ts-rs output of the `ncp-core`
 * reference types). This file adds only the *client* orchestration (build a
 * request, await the typed reply) and a JSON-wire view of the generated types.
 * Request envelopes are built as object literals — keep their fields in sync with
 * the generated request types (`OpenSession`/`StepRequest`/`RunRequest`/`CloseSession`).
 *
 * Transport-agnostic: provide any `send(message) => Promise<reply>` (see `ws.ts`
 * for a WebSocket implementation; a Zenoh/native transport can implement the same
 * `Send`).
 */

import type {
  AuthorityLease,
  ChannelValue,
  ErrorFrame as GeneratedErrorFrame,
  GatewayAttribution,
  IdentityClaim,
  NetworkRef,
  Observation,
  ObservationFrame,
  OperationContext,
  RecordTarget,
  SessionClosed,
  SessionOpened,
  SimConfig,
  StimulusTarget,
} from './generated/index.js'
import { requestDigest, sha256Hex, verifyRequestDigest } from './request-digest.js'

/** The protocol version this client stamps on every request (`ncp_version`).
 * Wire 0.8 splits the overloaded `seq` into a per-stream `stream` position + a
 * correlation-only `source`, adds `session` (generation) + `session_id` on every
 * session-scoped frame, and retires the top-level `seq`/`last_seq`. */
export const NCP_VERSION = '1.0'

/**
 * This peer's contract-hash (`ncp_core::CONTRACT_HASH` — FNV-1a of the canonicalized
 * proto). Pinned, cross-language-anchored to the Rust/Python peers and verified
 * against the proto in those peers' CI. Carried in `open()` and compared to the
 * server's reply as an **advisory** signal (see `contractStatus`): a mismatch is
 * surfaced, not thrown — `ncp_version` is the hard compatibility gate.
 */
export const NCP_CONTRACT_HASH = '163acc57d8a62b66'

/** Exact integer range shared by every JSON implementation (binary64 included). */
export const JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991
export const JSON_SAFE_INTEGER_MIN = -JSON_SAFE_INTEGER_MAX
export const MAX_HORIZON_STEPS = 65_536
export const MAX_CHANNELS = 4_096
const MAX_CLIENT_GENERATIONS = 4_096
const MAX_CLIENT_OBSERVATION_POSITIONS = 4_096

/** Closed stable wire-1.0 error-code registry. Keep this in exact parity with
 * `contract/errors.v1.json`; the shared mandatory corpus exercises rejection of
 * missing and unknown values in every implementation. */
export const NCP_ERROR_CODES = [
  'NCP-AUTH-001',
  'NCP-AUTH-002',
  'NCP-AUTH-003',
  'NCP-AUTH-004',
  'NCP-AUTH-005',
  'NCP-AUTH-006',
  'NCP-LEASE-001',
  'NCP-LEASE-002',
  'NCP-LEASE-003',
  'NCP-LEASE-004',
  'NCP-OP-001',
  'NCP-OP-002',
  'NCP-OP-003',
  'NCP-OP-004',
  'NCP-OP-005',
  'NCP-OP-006',
  'NCP-LIMIT-001',
  'NCP-LIMIT-002',
  'NCP-LIMIT-003',
  'NCP-LIMIT-004',
  'NCP-LIMIT-005',
  'NCP-LIMIT-006',
  'NCP-LIMIT-007',
  'NCP-LIMIT-008',
  'NCP-LIMIT-009',
  'NCP-PROFILE-001',
  'NCP-PROFILE-002',
  'NCP-PLANT-001',
  'NCP-PLANT-002',
  'NCP-PLANT-003',
  'NCP-STATE-001',
  'NCP-STATE-002',
  'NCP-STATE-003',
  'NCP-VERSION-001',
  'NCP-FEATURE-001',
  'NCP-AUDIT-001',
  'NCP-AUDIT-002',
  'NCP-GATEWAY-001',
  'NCP-GATEWAY-002',
  'NCP-WIRE-001',
  'NCP-INTERNAL-001',
] as const
export type NcpErrorCode = (typeof NCP_ERROR_CODES)[number]
const REGISTERED_ERROR_CODES = new Set<string>(NCP_ERROR_CODES)

/** Advisory comparison of a peer-advertised contract hash to ours. Mirrors
 *  `ncp_core::contract_status` — never throws; `null` = match or not advertised, a
 *  string = an advisory message describing the mismatch (for logging/telemetry). */
export function contractStatus(peerHash: string | null | undefined): string | null {
  if (peerHash == null || peerHash === NCP_CONTRACT_HASH) return null
  return (
    `NCP contract-hash differs: peer ${JSON.stringify(peerHash)}, ours ` +
    `${JSON.stringify(NCP_CONTRACT_HASH)} — versions compatible so the session ` +
    `proceeds, but the peers are on different contract revisions (advisory)`
  )
}

/** Thrown when a peer's `ncp_version` is unparseable or incompatible (the HARD
 *  compatibility gate — distinct from the advisory contract-hash check). */
export class NcpVersionError extends Error {}

/** Parse a wire version into `[major, minor]`, mirroring `ncp_core::check_version`'s
 *  parser: 1 or 2 canonical ASCII-decimal u64 components with no leading zeroes,
 *  trailing junk, or third component (semver patch is not part of the wire id). A
 *  missing minor ("1") is minor 0; anything else throws — never silently coerced
 *  to 0 (that would turn the fail-closed guard fail-open the moment our own minor
 *  is 0). */
function parseMajorMinor(version: string): [bigint, bigint] {
  const fail = (): never => {
    throw new NcpVersionError(`unparseable ncp_version ${JSON.stringify(version)}`)
  }
  const parts = version.split('.')
  if (parts.length < 1 || parts.length > 2) fail()
  const part = (s: string | undefined): bigint => {
    // Language-neutral grammar: canonical ASCII decimal (no leading zeroes),
    // bounded by u64::MAX.
    // BigInt preserves the full Rust range instead of imposing JS's 2^53 limit.
    if (
      s === undefined ||
      s.length > 20 ||
      !/^[0-9]+$/.test(s) ||
      (s.length > 1 && s.startsWith('0'))
    ) {
      return fail()
    }
    const value = BigInt(s)
    if (value > 18_446_744_073_709_551_615n) return fail()
    return value
  }
  return [part(parts[0]), parts.length === 2 ? part(parts[1]) : 0n]
}

/**
 * The HARD wire-compatibility gate — `true` if `version` can speak our wire.
 * Mirrors `ncp_core::check_version` exactly so the TS peer accepts/rejects the same
 * versions as the Rust/Python/C++ peers: for a pre-1.0 wire (major 0) the protocol
 * has no stability guarantee, so BOTH major and minor must match (`0.3 ≠ 0.4`); for
 * a stable wire (major ≥ 1) the major alone decides. An unparseable version always
 * throws [`NcpVersionError`]; an incompatible-but-parseable version throws when
 * `strict`, else returns `false`. This is the gate `contractStatus` is explicitly
 * NOT — the contract hash is advisory; the version is fail-closed.
 */
export function checkVersion(version: string, strict = false): boolean {
  const [gotMajor, gotMinor] = parseMajorMinor(version)
  const [wantMajor, wantMinor] = parseMajorMinor(NCP_VERSION)
  const compatible =
    wantMajor === 0n ? gotMajor === wantMajor && gotMinor === wantMinor : gotMajor === wantMajor
  if (!compatible) {
    if (strict) {
      throw new NcpVersionError(`NCP version mismatch: got ${version}, want ${NCP_VERSION}`)
    }
    return false
  }
  return true
}

/** Thrown when a frame violates the NCP scientific-boundary discriminators. */
export class NcpScientificBoundaryError extends Error {}

/**
 * Enforce the **mandatory, fail-closed scientific-boundary discriminators** on an
 * inbound `observation_frame` (or a `session_opened.provenance` block): NCP output is
 * a *control artifact*, never a validated reproduction, so `is_simulation_output` MUST
 * be `true` and `calibrated_posterior` MUST be `false`. A TS consumer should call this
 * on frames it reads so a peer cannot quietly hand it a frame claiming calibrated /
 * non-simulation status. Mirrors the boundary pins `ncp_core::validate` enforces in the
 * Rust/Python/C++ peers. Throws [`NcpScientificBoundaryError`] on a violation.
 */
export function assertScientificBoundary(frame: Record<string, unknown>): void {
  const kind = frame.kind
  // The discriminators live top-level on observation_frame, and inside
  // session_opened.provenance.
  const carrier =
    kind === 'session_opened' && frame.provenance && typeof frame.provenance === 'object'
      ? (frame.provenance as Record<string, unknown>)
      : frame
  const boundaryKind = kind === 'observation_frame' || kind === 'session_opened'
  if (!boundaryKind && !('is_simulation_output' in carrier) && !('calibrated_posterior' in carrier)) {
    return // not a boundary-carrying frame (e.g. a control reply)
  }
  if (carrier.is_simulation_output !== true) {
    throw new NcpScientificBoundaryError(
      `NCP boundary: is_simulation_output must be true (got ${JSON.stringify(carrier.is_simulation_output)}) — output is a control artifact, not a validated reproduction`,
    )
  }
  if (carrier.calibrated_posterior !== false) {
    throw new NcpScientificBoundaryError(
      `NCP boundary: calibrated_posterior must be false (got ${JSON.stringify(carrier.calibrated_posterior)})`,
    )
  }
}

const REQUIRED: Record<string, readonly string[]> = {
  capabilities: [
    'command_channels',
    'control_rate_hz',
    'controller_id',
    'gateway_permitted',
    'identity',
    'kind',
    'ncp_version',
    'role',
    'safety',
    'security_profile',
    'security_state_digest',
    'sensor_channels',
    'stable_capabilities',
  ],
  close_session: ['authority', 'kind', 'ncp_version', 'operation', 'session', 'session_id'],
  command_frame: ['kind', 'ncp_version', 'session', 'session_id', 'stream'],
  control_status: [
    'kind',
    'loop_latency_ms',
    'mode',
    'ncp_version',
    'safety_ok',
    'session',
    'session_id',
    'stream',
    't',
  ],
  error: ['code', 'error', 'kind', 'ncp_version'],
  link_status: [
    'burst',
    'kind',
    'loss_rate',
    'lost',
    'ncp_version',
    'received',
    'session',
    'session_id',
    'stream',
    't',
  ],
  observation_frame: [
    'calibrated_posterior',
    'is_simulation_output',
    'kind',
    'ncp_version',
    'records',
    'session',
    'session_id',
    'stream',
  ],
  open_session: [
    'gateway_permitted',
    'identity',
    'kind',
    'ncp_version',
    'network',
    'security_profile',
    'security_state_digest',
    'session_id',
  ],
  run_request: [
    'authority',
    'duration_ms',
    'kind',
    'ncp_version',
    'operation',
    'session',
    'session_id',
  ],
  sensor_frame: ['kind', 'ncp_version', 'session', 'session_id', 'stream'],
  session_closed: ['kind', 'ncp_version', 'ok', 'receipt', 'session', 'session_id'],
  session_opened: [
    'backend',
    'gateway_permitted',
    'identity',
    'kind',
    'ncp_version',
    'ok',
    'security_profile',
    'security_state_digest',
    'session_id',
    'state_version',
  ],
  step_request: ['authority', 'kind', 'ncp_version', 'operation', 'session', 'session_id'],
  stimulus_frame: ['kind', 'ncp_version', 'session', 'session_id'],
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function requireRecord(value: unknown, path: string): Record<string, unknown> {
  if (!isRecord(value)) throw new Error(`${path} must be an object`)
  return value
}

/** Wire 0.8: a canonical lowercase UUIDv4 (`stream.epoch` / `session.generation`). */
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
function requireUuidV4(value: unknown, path: string): void {
  if (typeof value !== 'string' || !UUID_V4.test(value)) {
    throw new Error(`${path} must be a canonical lowercase UUIDv4`)
  }
}

const SHA256_HEX = /^[0-9a-f]{64}$/
const MAX_AUTHORITY_LEASE_MS = 60_000
const CORE_STABLE_CAPABILITIES = [
  'ncp.core.canonical-json.v1',
  'ncp.core.lifecycle.v1',
  'ncp.core.authority-lease.v1',
  'ncp.core.idempotent-mutation.v1',
  'ncp.core.plant-profile.v1',
] as const
const KNOWN_STABLE_CAPABILITIES = new Set<string>([
  ...CORE_STABLE_CAPABILITIES,
  'ncp.transport.zenoh.v1',
])

const KNOWN_NETWORK_REF_KINDS = new Set(['handle', 'builtin', 'model_id', 'spec'])
const KNOWN_SIM_MODES = new Set(['stream', 'batch'])
const KNOWN_OBSERVABLES = new Set(['spikes', 'V_m', 'rate', 'weight', 'binary_state'])
const KNOWN_STIMULUS_KINDS = new Set([
  'current_pA',
  'rate_hz',
  'spike_times',
  'weight_set',
  'rate_inject',
])
const KNOWN_CHANNEL_KINDS = new Set(['scalar', 'vec3', 'quat', 'array'])

function exceedsUtf8ByteLength(value: string, maximum: number): boolean {
  let bytes = 0
  for (const scalar of value) {
    const codePoint = scalar.codePointAt(0)!
    // `for...of` combines a valid surrogate pair into one scalar. A remaining
    // surrogate is therefore unpaired invalid Unicode and must fail closed.
    if (codePoint >= 0xd800 && codePoint <= 0xdfff) return true
    bytes += codePoint <= 0x7f ? 1 : codePoint <= 0x7ff ? 2 : codePoint <= 0xffff ? 3 : 4
    if (bytes > maximum) return true
  }
  return false
}

function requireBoundedId(value: unknown, path: string): string {
  const identity = requireNonemptyString(value, path)
  if (
    exceedsUtf8ByteLength(identity, 128) ||
    /[/*$#?\s\u0000-\u001f\u007f-\u009f]/u.test(identity)
  ) {
    throw new Error(`${path} must be a bounded canonical identity segment`)
  }
  return identity
}

function requireSha256(value: unknown, path: string): string {
  if (typeof value !== 'string' || !SHA256_HEX.test(value)) {
    throw new Error(`${path} must be 64 lowercase hexadecimal characters`)
  }
  return value
}

function requireIdentityClaim(
  value: unknown,
  path: string,
  expectedPlane?: string,
  expectedRole?: string,
): Record<string, unknown> {
  const claim = requireRecord(value, path)
  requireBoundedId(claim.principal_id, `${path}.principal_id`)
  requireBoundedId(claim.entity_id, `${path}.entity_id`)
  const role = requireNonemptyString(claim.role, `${path}.role`)
  if (!['commander', 'body', 'observer', 'operator'].includes(role)) {
    throw new Error(`${path}.role is unknown and cannot authorize this message`)
  }
  if (expectedRole !== undefined && role !== expectedRole) {
    throw new Error(`${path}.role ${JSON.stringify(role)} does not match the envelope role`)
  }
  const plane = requireNonemptyString(claim.plane, `${path}.plane`)
  if (!['control', 'perception', 'action', 'observation'].includes(plane)) {
    throw new Error(`${path}.plane is unknown and cannot authorize this message`)
  }
  if (expectedPlane !== undefined && plane !== expectedPlane) {
    throw new Error(`${path}.plane ${JSON.stringify(plane)} does not match the message plane`)
  }
  return claim
}

function requireSecurityNegotiation(message: Record<string, unknown>, path: string): void {
  const profile = requireNonemptyString(message.security_profile, `${path}.security_profile`)
  if (profile !== 'dev-loopback-insecure' && profile !== 'production-secure') {
    throw new Error(`${path}.security_profile is not a registered NCP 1.0 profile`)
  }
  requireSha256(message.security_state_digest, `${path}.security_state_digest`)
}

function requireGatewayAttribution(message: Record<string, unknown>, path: string): void {
  if (typeof message.gateway_permitted !== 'boolean') {
    throw new Error(`${path}.gateway_permitted must be a boolean`)
  }
  if (message.gateway === undefined || message.gateway === null) return
  if (message.gateway_permitted !== true) {
    throw new Error(`${path}.gateway attribution is forbidden when gateway_permitted=false`)
  }
  const gateway = requireRecord(message.gateway, `${path}.gateway`)
  requireBoundedId(gateway.gateway_id, `${path}.gateway.gateway_id`)
  if (gateway.source_wire !== '0.8') {
    throw new Error(`${path}.gateway.source_wire must identify legacy wire 0.8`)
  }
}

function requireSessionEpoch(message: Record<string, unknown>, path: string): string {
  const session = requireRecord(message.session, `${path}.session`)
  requireUuidV4(session.generation, `${path}.session.generation`)
  return session.generation as string
}

function requireAuthorityLease(
  value: unknown,
  path: string,
  expectedEpoch: string,
): Record<string, unknown> {
  const lease = requireRecord(value, path)
  requireUuidV4(lease.session_epoch, `${path}.session_epoch`)
  requireUuidV4(lease.lease_id, `${path}.lease_id`)
  if (lease.session_epoch !== expectedEpoch) {
    throw new Error(`${path}.session_epoch does not match the message session generation`)
  }
  assertSafeInteger(lease.term, `${path}.term`)
  if ((lease.term as number) <= 0) throw new Error(`${path}.term must be > 0`)
  for (const field of [
    'issuer_principal_id',
    'holder_principal_id',
    'holder_entity_id',
  ] as const) {
    requireBoundedId(lease[field], `${path}.${field}`)
  }
  assertSafeInteger(lease.issued_at_utc_ms, `${path}.issued_at_utc_ms`)
  assertSafeInteger(lease.expires_at_utc_ms, `${path}.expires_at_utc_ms`)
  const issued = lease.issued_at_utc_ms as number
  const expires = lease.expires_at_utc_ms as number
  if (issued < 0 || expires <= issued || expires - issued > MAX_AUTHORITY_LEASE_MS) {
    throw new Error(`${path} must have a positive bounded UTC lease interval`)
  }
  return lease
}

function requireOperationContext(
  value: unknown,
  path: string,
  expectedEpoch: string,
): Record<string, unknown> {
  const operation = requireRecord(value, path)
  requireUuidV4(operation.operation_id, `${path}.operation_id`)
  requireUuidV4(operation.session_epoch, `${path}.session_epoch`)
  if (operation.session_epoch !== expectedEpoch) {
    throw new Error(`${path}.session_epoch does not match the message session generation`)
  }
  requireSha256(operation.request_digest, `${path}.request_digest`)
  assertSafeInteger(operation.expected_state_version, `${path}.expected_state_version`)
  if ((operation.expected_state_version as number) < 0) {
    throw new Error(`${path}.expected_state_version must be non-negative`)
  }
  assertSafeInteger(operation.deadline_utc_ms, `${path}.deadline_utc_ms`)
  if ((operation.deadline_utc_ms as number) <= 0) {
    throw new Error(`${path}.deadline_utc_ms must be positive`)
  }
  if (typeof operation.retry !== 'boolean') throw new Error(`${path}.retry must be a boolean`)
  return operation
}

function requireResponderReceipt(
  value: unknown,
  path: string,
  context: 'terminal' | 'success' | 'error' = 'terminal',
): Record<string, unknown> {
  const receipt = requireRecord(value, path)
  requireUuidV4(receipt.operation_id, `${path}.operation_id`)
  requireSha256(receipt.request_digest, `${path}.request_digest`)
  requireSha256(receipt.result_digest, `${path}.result_digest`)
  if (!['succeeded', 'rejected', 'cancelled'].includes(String(receipt.outcome))) {
    throw new Error(`${path}.outcome must be a known terminal outcome`)
  }
  if (context === 'success' && receipt.outcome !== 'succeeded') {
    throw new Error(`${path}.outcome must be succeeded on a successful RPC reply`)
  }
  if (context === 'error' && receipt.outcome !== 'rejected' && receipt.outcome !== 'cancelled') {
    throw new Error(`${path}.outcome must be rejected or cancelled on an ErrorFrame`)
  }
  assertSafeInteger(receipt.state_version, `${path}.state_version`)
  if ((receipt.state_version as number) < 0) throw new Error(`${path}.state_version must be non-negative`)
  assertSafeInteger(receipt.committed_at_utc_ms, `${path}.committed_at_utc_ms`)
  if ((receipt.committed_at_utc_ms as number) <= 0) {
    throw new Error(`${path}.committed_at_utc_ms must be positive`)
  }
  requireBoundedId(receipt.responder_principal_id, `${path}.responder_principal_id`)
  requireBoundedId(receipt.responder_entity_id, `${path}.responder_entity_id`)
  return receipt
}

/** Wire 1.0: a transport-neutral session_id (1..=64 UTF-8 bytes, safe key segment). */
function requireSessionId(value: unknown, path: string): void {
  if (typeof value !== 'string' || value.length === 0 || exceedsUtf8ByteLength(value, 64)) {
    throw new Error(`${path} must be 1..=64 bytes`)
  }
  if (
    /[/*$#?]/u.test(value) ||
    /\s/u.test(value) ||
    Array.from(value).some(
      (c) => c.charCodeAt(0) < 0x20 || (c.charCodeAt(0) >= 0x7f && c.charCodeAt(0) <= 0x9f),
    )
  ) {
    throw new Error(`${path} must be a safe single key segment`)
  }
}

/** Wire 1.0: a `StreamPosition` — epoch (UUIDv4) + seq (>= minSeq, JSON-safe). */
function requireStreamPosition(value: unknown, path: string, minSeq: number): void {
  const pos = requireRecord(value, path)
  requireUuidV4(pos.epoch, `${path}.epoch`)
  assertSafeInteger(pos.seq, `${path}.seq`)
  if ((pos.seq as number) < minSeq) throw new Error(`${path}.seq must be >= ${minSeq}`)
}

function requireNonemptyString(value: unknown, path: string): string {
  if (typeof value !== 'string' || value.length === 0) {
    throw new Error(`${path} must be a non-empty string`)
  }
  return value
}

const WIRE_CONTROL_CHARACTERS = /[\u0000-\u001f\u007f-\u009f]/u

/** Rust `char::is_control` parity for the JSON identifiers NCP constrains.
 * JavaScript's common C0/DEL-only regex misses the C1 range U+0080..U+009F. */
export function hasWireControlCharacters(value: string): boolean {
  return WIRE_CONTROL_CHARACTERS.test(value)
}

function requireCleanNonemptyString(value: unknown, path: string): string {
  const text = requireNonemptyString(value, path)
  if (hasWireControlCharacters(text)) {
    throw new Error(`${path} must contain no control characters`)
  }
  return text
}

function assertOptionalString(value: unknown, path: string): void {
  if (value === undefined || value === null) return
  if (typeof value !== 'string') throw new Error(`${path} must be a string or null`)
}

function assertStringArray(value: unknown, path: string): void {
  if (value === undefined) return
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== 'string')) {
    throw new Error(`${path} must be an array of strings`)
  }
}

function assertStringMap(value: unknown, path: string): void {
  if (value === undefined) return
  const entries = requireRecord(value, path)
  for (const [key, entry] of Object.entries(entries)) {
    if (typeof entry !== 'string') {
      throw new Error(`${path}[${JSON.stringify(key)}] must be a string`)
    }
  }
}

function assertSafeInteger(value: unknown, path: string, nullable = false): void {
  if (nullable && value === null) return
  if (typeof value !== 'number' || !Number.isSafeInteger(value)) {
    throw new Error(
      `${path} must be an exact JSON integer in [${JSON_SAFE_INTEGER_MIN}, ${JSON_SAFE_INTEGER_MAX}]`,
    )
  }
}

function assertFiniteNumber(value: unknown, path: string, nullable = false): number {
  if (nullable && value === null) return 0
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${path} must be ${nullable ? 'a finite number or null' : 'a finite number'}`)
  }
  return value
}

function assertSafeIntegerArray(value: unknown, path: string): void {
  if (value === undefined) return
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`)
  value.forEach((entry, index) => assertSafeInteger(entry, `${path}[${index}]`))
}

function assertFiniteNumberArray(value: unknown, path: string): void {
  if (value === undefined) return
  if (!Array.isArray(value)) throw new Error(`${path} must be an array`)
  value.forEach((entry, index) => assertFiniteNumber(entry, `${path}[${index}]`))
}

function assertSafeIntegerMap(value: unknown, path: string): void {
  if (value === undefined) return
  const entries = requireRecord(value, path)
  for (const [key, entry] of Object.entries(entries)) {
    assertSafeInteger(entry, `${path}[${JSON.stringify(key)}]`)
  }
}

function assertChannelMap(value: unknown, path: string, requireData = false): void {
  if (value === undefined) {
    if (requireData) throw new Error(`${path} must contain at least one channel`)
    return
  }
  const channels = requireRecord(value, path)
  if (requireData && Object.keys(channels).length === 0) {
    throw new Error(`${path} must contain at least one channel`)
  }
  for (const [name, raw] of Object.entries(channels)) {
    if (name.length === 0 || hasWireControlCharacters(name)) {
      throw new Error(`${path} channel name ${JSON.stringify(name)} must be non-empty and contain no control characters`)
    }
    const channel = requireRecord(raw, `${path}.${name}`)
    if (channel.data !== undefined || requireData) {
      if (
        !Array.isArray(channel.data) ||
        (requireData && channel.data.length === 0) ||
        channel.data.some((sample) => typeof sample !== 'number' || !Number.isFinite(sample))
      ) {
        throw new Error(`${path}.${name}.data must be a non-empty array of finite numbers`)
      }
    }
    assertOptionalString(channel.unit, `${path}.${name}.unit`)
  }
}

function assertSessionId(message: Record<string, unknown>, kind: string): void {
  requireSessionId(message.session_id, `${kind}.session_id`)
}

/** Full TypeScript ingress gate for the shared validation contract. Unknown object
 * fields remain allowed; known fields are type/value checked exactly like the Rust
 * reference, including nested stimulus identity and safe JSON integers. */
export function assertNcpMessage(value: unknown, expectedKind?: string): asserts value is Record<string, unknown> {
  const message = requireRecord(value, 'NCP message')
  const kind = requireNonemptyString(message.kind, 'NCP message.kind')
  if (expectedKind !== undefined && kind !== expectedKind) {
    throw new Error(`NCP kind mismatch: expected ${JSON.stringify(expectedKind)}, got ${JSON.stringify(kind)}`)
  }
  const required = REQUIRED[kind]
  if (required === undefined) throw new Error(`unknown NCP message kind ${JSON.stringify(kind)}`)
  for (const field of required) {
    if (!(field in message)) throw new Error(`${kind}: required field ${JSON.stringify(field)} is missing`)
  }
  if (typeof message.ncp_version !== 'string') {
    throw new NcpVersionError(`${kind}: ncp_version must be a string`)
  }
  checkVersion(message.ncp_version, true)

  if (
    [
      'open_session',
      'session_opened',
      'step_request',
      'run_request',
      'stimulus_frame',
      'observation_frame',
      'close_session',
      'session_closed',
      'sensor_frame',
      'command_frame',
      'control_status',
      'link_status',
    ].includes(kind)
  ) {
    assertSessionId(message, kind)
  }
  const sessionEpoch = [
    'step_request',
    'run_request',
    'stimulus_frame',
    'observation_frame',
    'close_session',
    'session_closed',
    'sensor_frame',
    'command_frame',
    'control_status',
    'link_status',
  ].includes(kind)
    ? requireSessionEpoch(message, kind)
    : undefined

  switch (kind) {
    case 'open_session': {
      requireIdentityClaim(message.identity, 'open_session.identity', 'control', 'commander')
      requireSecurityNegotiation(message, 'open_session')
      requireGatewayAttribution(message, 'open_session')
      const network = requireRecord(message.network, 'open_session.network')
      const networkKind = requireNonemptyString(network.kind, 'open_session.network.kind')
      if (!KNOWN_NETWORK_REF_KINDS.has(networkKind)) {
        throw new Error(
          'open_session.network.kind is unknown and cannot select model-loading behavior',
        )
      }
      requireNonemptyString(network.ref, 'open_session.network.ref')
      assertOptionalString(network.model_name, 'open_session.network.model_name')
      assertSafeIntegerMap(network.population_sizes, 'open_session.network.population_sizes')
      if (network.params !== undefined) {
        for (const [key, number] of Object.entries(requireRecord(network.params, 'open_session.network.params'))) {
          assertFiniteNumber(number, `open_session.network.params[${JSON.stringify(key)}]`)
        }
      }
      const sim = message.sim === undefined ? undefined : requireRecord(message.sim, 'open_session.sim')
      if (sim !== undefined) {
        if (sim.seed !== undefined) assertSafeInteger(sim.seed, 'open_session.sim.seed', true)
        for (const [field, allowZero, nullable] of [
          ['dt_ms', false, false],
          ['chunk_ms', false, false],
          ['duration_ms', true, true],
        ] as const) {
          const value = sim[field]
          if (value === undefined || (nullable && value === null)) continue
          const number = assertFiniteNumber(value, `open_session.sim.${field}`)
          if (number < 0 || (!allowZero && number === 0)) {
            throw new Error(
              `open_session.sim.${field} must be ${allowZero ? '>=' : '>'} 0`,
            )
          }
        }
        if (sim.mode !== undefined) {
          const simMode = requireNonemptyString(sim.mode, 'open_session.sim.mode')
          if (!KNOWN_SIM_MODES.has(simMode)) {
            throw new Error('open_session.sim.mode must be stream or batch')
          }
        }
      }
      const record = message.record === undefined ? undefined : requireRecord(message.record, 'open_session.record')
      const recordTargets = record?.targets
      if (recordTargets !== undefined) {
        if (!Array.isArray(recordTargets)) throw new Error('open_session.record.targets must be an array')
        recordTargets.forEach((raw, index) => {
          const target = requireRecord(raw, `open_session.record.targets[${index}]`)
          requireNonemptyString(target.port, `open_session.record.targets[${index}].port`)
          requireNonemptyString(target.target, `open_session.record.targets[${index}].target`)
          const observable = requireNonemptyString(
            target.observable,
            `open_session.record.targets[${index}].observable`,
          )
          if (!KNOWN_OBSERVABLES.has(observable)) {
            throw new Error(
              `open_session.record.targets[${index}].observable is unknown and cannot configure recording`,
            )
          }
          assertSafeIntegerArray(target.ids, `open_session.record.targets[${index}].ids`)
          assertStringArray(target.recordables, `open_session.record.targets[${index}].recordables`)
          if (target.cadence_ms !== undefined) {
            const cadence = assertFiniteNumber(target.cadence_ms, `open_session.record.targets[${index}].cadence_ms`)
            if (cadence <= 0) throw new Error(`open_session.record.targets[${index}].cadence_ms must be > 0`)
          }
        })
      }
      const stimulus =
        message.stimulus === undefined
          ? undefined
          : requireRecord(message.stimulus, 'open_session.stimulus')
      const stimulusTargets = stimulus?.targets
      if (stimulusTargets !== undefined) {
        if (!Array.isArray(stimulusTargets)) throw new Error('open_session.stimulus.targets must be an array')
        stimulusTargets.forEach((raw, index) => {
          const target = requireRecord(raw, `open_session.stimulus.targets[${index}]`)
          requireNonemptyString(target.port, `open_session.stimulus.targets[${index}].port`)
          requireNonemptyString(target.target, `open_session.stimulus.targets[${index}].target`)
          const stimulusKind = requireNonemptyString(
            target.kind,
            `open_session.stimulus.targets[${index}].kind`,
          )
          if (!KNOWN_STIMULUS_KINDS.has(stimulusKind)) {
            throw new Error(
              `open_session.stimulus.targets[${index}].kind is unknown and cannot select stimulus behavior`,
            )
          }
          assertSafeIntegerArray(target.ids, `open_session.stimulus.targets[${index}].ids`)
          if (target.params !== undefined) {
            for (const [name, value] of Object.entries(requireRecord(target.params, `open_session.stimulus.targets[${index}].params`))) {
              assertFiniteNumber(value, `open_session.stimulus.targets[${index}].params[${JSON.stringify(name)}]`)
            }
          }
        })
      }
      if (message.bindings !== undefined) {
        if (!Array.isArray(message.bindings)) throw new Error('open_session.bindings must be an array')
        message.bindings.forEach((raw, index) => {
          const binding = requireRecord(raw, `open_session.bindings[${index}]`)
          requireNonemptyString(binding.port, `open_session.bindings[${index}].port`)
          const direction = requireNonemptyString(binding.direction, `open_session.bindings[${index}].direction`)
          if (direction !== 'record' && direction !== 'stimulus') {
            throw new Error(`open_session.bindings[${index}].direction must be "record" or "stimulus"`)
          }
          const entity = requireRecord(binding.entity, `open_session.bindings[${index}].entity`)
          requireNonemptyString(entity.path, `open_session.bindings[${index}].entity.path`)
          const entityRole = requireNonemptyString(
            entity.role,
            `open_session.bindings[${index}].entity.role`,
          )
          if (!['system', 'actor', 'sensor', 'actuator'].includes(entityRole)) {
            throw new Error(
              `open_session.bindings[${index}].entity.role is unknown and cannot select binding semantics`,
            )
          }
          assertStringMap(entity.meta, `open_session.bindings[${index}].entity.meta`)
        })
      }
      assertOptionalString(message.contract_hash, 'open_session.contract_hash')
      break
    }
    case 'session_opened': {
      requireIdentityClaim(message.identity, 'session_opened.identity', 'control', 'body')
      requireSecurityNegotiation(message, 'session_opened')
      requireGatewayAttribution(message, 'session_opened')
      const backend = requireNonemptyString(message.backend, 'session_opened.backend')
      assertSafeInteger(message.state_version, 'session_opened.state_version')
      if ((message.state_version as number) < 0) {
        throw new Error('session_opened.state_version must be non-negative')
      }
      if (typeof message.ok !== 'boolean') throw new Error('session_opened.ok must be a boolean')
      assertSafeIntegerMap(message.resolved, 'session_opened.resolved')
      if (message.ok) {
        requireSessionEpoch(message, 'session_opened')
        const provenance = requireRecord(message.provenance, 'session_opened.provenance')
        requireNonemptyString(provenance.network_ref, 'session_opened.provenance.network_ref')
        const provenanceBackend = requireNonemptyString(provenance.backend, 'session_opened.provenance.backend')
        if (provenanceBackend !== backend) {
          throw new Error('session_opened.provenance.backend must equal session_opened.backend')
        }
        if (provenance.advisory_only !== true) {
          throw new Error('session_opened.provenance.advisory_only must be explicitly true')
        }
        if (provenance.seed !== undefined) assertSafeInteger(provenance.seed, 'session_opened.provenance.seed', true)
        assertOptionalString(provenance.note, 'session_opened.provenance.note')
        assertScientificBoundary(message)
        if (message.error !== undefined && message.error !== null) {
          throw new Error('session_opened.error must be null when ok=true')
        }
      } else {
        requireNonemptyString(message.error, 'session_opened.error')
        if (message.provenance !== undefined && message.provenance !== null) {
          throw new Error('session_opened.provenance must be null when ok=false')
        }
        if (message.session !== undefined && message.session !== null) {
          throw new Error('session_opened.session must be null when ok=false')
        }
      }
      assertOptionalString(message.contract_hash, 'session_opened.contract_hash')
      break
    }
    case 'session_closed':
      if (message.ok !== true) throw new Error('session_closed.ok must be true; failures use ErrorFrame')
      requireResponderReceipt(message.receipt, 'session_closed.receipt', 'success')
      break
    case 'error':
      if (
        typeof message.code !== 'string' ||
        !REGISTERED_ERROR_CODES.has(message.code)
      ) {
        throw new Error('error.code must be registered in contract/errors.v1.json')
      }
      requireNonemptyString(message.error, 'error.error')
      if (message.request_kind !== undefined && message.request_kind !== null) {
        requireNonemptyString(message.request_kind, 'error.request_kind')
      }
      {
        const hasSessionId = message.session_id !== undefined && message.session_id !== null
        const hasSession = message.session !== undefined && message.session !== null
        if (hasSessionId) assertSessionId(message, 'error')
        if (hasSessionId !== hasSession) {
          throw new Error('error.session_id and error.session must be present or null together')
        }
        if (hasSession) requireSessionEpoch(message, 'error')
      }
      if (message.receipt !== undefined && message.receipt !== null) {
        if (message.session_id === undefined || message.session_id === null) {
          throw new Error('error.receipt requires the exact session_id/session generation pair')
        }
        requireResponderReceipt(message.receipt, 'error.receipt', 'error')
      }
      break
    case 'run_request': {
      requireOperationContext(message.operation, 'run_request.operation', sessionEpoch!)
      requireAuthorityLease(message.authority, 'run_request.authority', sessionEpoch!)
      const duration = assertFiniteNumber(message.duration_ms, 'run_request.duration_ms')
      if (duration <= 0) throw new Error('run_request.duration_ms must be > 0')
      if (message.stimulus !== undefined && message.stimulus !== null) {
        assertNcpMessage(message.stimulus, 'stimulus_frame')
        if ((message.stimulus as Record<string, unknown>).session_id !== message.session_id) {
          throw new Error('run_request.stimulus session_id does not match outer request')
        }
        if (
          ((message.stimulus as Record<string, unknown>).session as Record<string, unknown>).generation !==
          sessionEpoch
        ) {
          throw new Error('run_request.stimulus session.generation does not match outer request')
        }
      }
      verifyRequestDigest(message)
      break
    }
    case 'step_request': {
      requireOperationContext(message.operation, 'step_request.operation', sessionEpoch!)
      requireAuthorityLease(message.authority, 'step_request.authority', sessionEpoch!)
      if (message.advance_ms !== undefined && message.advance_ms !== null && assertFiniteNumber(message.advance_ms, 'step_request.advance_ms') < 0) {
        throw new Error('step_request.advance_ms must be >= 0')
      }
      if (message.stimulus !== undefined && message.stimulus !== null) {
        assertNcpMessage(message.stimulus, 'stimulus_frame')
        if ((message.stimulus as Record<string, unknown>).session_id !== message.session_id) {
          throw new Error('step_request.stimulus session_id does not match outer request')
        }
        if (
          ((message.stimulus as Record<string, unknown>).session as Record<string, unknown>).generation !==
          sessionEpoch
        ) {
          throw new Error('step_request.stimulus session.generation does not match outer request')
        }
      }
      verifyRequestDigest(message)
      break
    }
    case 'close_session':
      requireOperationContext(message.operation, 'close_session.operation', sessionEpoch!)
      requireAuthorityLease(message.authority, 'close_session.authority', sessionEpoch!)
      verifyRequestDigest(message)
      break
    case 'stimulus_frame':
      if (message.t !== undefined) assertFiniteNumber(message.t, 'stimulus_frame.t')
      assertChannelMap(message.values, 'stimulus_frame.values')
      break
    case 'sensor_frame':
    case 'command_frame':
    case 'observation_frame': {
      requireStreamPosition(message.stream, `${kind}.stream`, 1)
      requireUuidV4(
        requireRecord(message.session, `${kind}.session`).generation,
        `${kind}.session.generation`,
      )
      requireSessionId(message.session_id, `${kind}.session_id`)
      if (message.source !== undefined && message.source !== null) {
        requireStreamPosition(message.source, `${kind}.source`, 1)
      }
      if (message.t !== undefined) assertFiniteNumber(message.t, `${kind}.t`)
      if (kind === 'sensor_frame') {
        if (message.frame_id !== undefined) {
          requireCleanNonemptyString(message.frame_id, 'sensor_frame.frame_id')
        }
        assertChannelMap(message.channels, 'sensor_frame.channels')
      }
      if (kind === 'command_frame') {
        if (message.frame_id !== undefined) {
          requireCleanNonemptyString(message.frame_id, 'command_frame.frame_id')
        }
        assertChannelMap(message.channels, 'command_frame.channels')
        if (message.mode !== undefined) requireNonemptyString(message.mode, 'command_frame.mode')
        if (message.ttl_ms !== undefined) {
          assertFiniteNumber(message.ttl_ms, 'command_frame.ttl_ms')
        }
        if (message.mode === 'active') {
          requireAuthorityLease(message.authority, 'command_frame.authority', sessionEpoch!)
          const ttl = assertFiniteNumber(message.ttl_ms, 'command_frame.ttl_ms')
          if (ttl <= 0) throw new Error('command_frame Active ttl_ms must be > 0')
          assertChannelMap(message.channels, 'command_frame.channels', true)
        } else if (message.authority !== undefined && message.authority !== null) {
          requireAuthorityLease(message.authority, 'command_frame.authority', sessionEpoch!)
        }
        if (message.horizon !== undefined) {
          if (!Array.isArray(message.horizon)) throw new Error('command_frame.horizon must be an array')
          if (message.horizon.length > MAX_HORIZON_STEPS) {
            throw new Error(`command_frame.horizon exceeds the ${MAX_HORIZON_STEPS}-step resource ceiling`)
          }
          message.horizon.forEach((step, index) =>
            assertChannelMap(step, `command_frame.horizon[${index}]`, message.mode === 'active'),
          )
          if (message.mode === 'active' && message.horizon.length > 0) {
            const dt = assertFiniteNumber(message.horizon_dt_ms, 'command_frame.horizon_dt_ms')
            if (dt <= 0) throw new Error('command_frame predictive horizon requires horizon_dt_ms > 0')
            const ttl = message.ttl_ms as number
            if (
              message.horizon.length > MAX_HORIZON_STEPS ||
              message.horizon.length > Math.max(Math.ceil(ttl / dt) - 1, 0)
            ) {
              throw new Error(
                `command_frame.horizon future steps must occur strictly before ttl_ms and N <= ${MAX_HORIZON_STEPS}`,
              )
            }
          }
        }
        if (message.horizon_dt_ms !== undefined && message.horizon_dt_ms !== null) {
          assertFiniteNumber(message.horizon_dt_ms, 'command_frame.horizon_dt_ms')
        }
      }
      if (kind === 'observation_frame') {
        if (message.receipt !== undefined && message.receipt !== null) {
          requireResponderReceipt(message.receipt, 'observation_frame.receipt', 'success')
        }
        if (message.sim_time_ms !== undefined) {
          assertFiniteNumber(message.sim_time_ms, 'observation_frame.sim_time_ms')
        }
        assertScientificBoundary(message)
        const records = requireRecord(message.records, 'observation_frame.records')
        for (const [recordKey, raw] of Object.entries(records)) {
          if (recordKey.length === 0 || hasWireControlCharacters(recordKey)) {
            throw new Error(`observation record-series key ${JSON.stringify(recordKey)} must be non-empty and contain no control characters`)
          }
          const record = requireRecord(raw, `observation_frame.records[${JSON.stringify(recordKey)}]`)
          requireNonemptyString(record.port, `observation_frame.records[${JSON.stringify(recordKey)}].port`)
          requireNonemptyString(record.target, `observation_frame.records[${JSON.stringify(recordKey)}].target`)
          const observable = requireNonemptyString(
            record.observable,
            `observation_frame.records[${JSON.stringify(recordKey)}].observable`,
          )
          if (!KNOWN_OBSERVABLES.has(observable)) {
            throw new Error(
              `observation_frame.records[${JSON.stringify(recordKey)}].observable is unknown`,
            )
          }
          assertFiniteNumberArray(record.times, `observation_frame.records[${JSON.stringify(recordKey)}].times`)
          assertFiniteNumberArray(record.values, `observation_frame.records[${JSON.stringify(recordKey)}].values`)
          assertSafeIntegerArray(record.senders, `observation_frame.records[${JSON.stringify(recordKey)}].senders`)
          assertOptionalString(record.unit, `observation_frame.records[${JSON.stringify(recordKey)}].unit`)
          assertOptionalString(
            record.recordable,
            `observation_frame.records[${JSON.stringify(recordKey)}].recordable`,
          )
          const times = Array.isArray(record.times) ? record.times.length : 0
          const values = Array.isArray(record.values) ? record.values.length : 0
          const senders = Array.isArray(record.senders) ? record.senders.length : 0
          if (values > 0 && senders > 0) throw new Error(`observation record ${JSON.stringify(recordKey)} carries values and senders`)
          if ((times > 0 || values > 0 || senders > 0) && times !== Math.max(values, senders)) {
            throw new Error(`observation record ${JSON.stringify(recordKey)} has mismatched parallel arrays`)
          }
        }
      }
      break
    }
    case 'control_status': {
      requireStreamPosition(message.stream, 'control_status.stream', 1)
      assertFiniteNumber(message.t, 'control_status.t')
      if (message.sim_time_ms !== undefined) {
        assertFiniteNumber(message.sim_time_ms, 'control_status.sim_time_ms')
      }
      const latency = assertFiniteNumber(message.loop_latency_ms, 'control_status.loop_latency_ms')
      if (latency < 0) throw new Error('control_status.loop_latency_ms must be >= 0')
      requireNonemptyString(message.mode, 'control_status.mode')
      if (typeof message.safety_ok !== 'boolean') throw new Error('control_status.safety_ok must be boolean')
      assertOptionalString(message.note, 'control_status.note')
      break
    }
    case 'link_status': {
      requireStreamPosition(message.stream, 'link_status.stream', 1)
      for (const field of ['received', 'lost'] as const) {
        assertSafeInteger(message[field], `link_status.${field}`)
      }
      const hasObservedStream = message.observed_stream !== undefined && message.observed_stream !== null
      const hasLastArrival = message.last_arrival_seq !== undefined && message.last_arrival_seq !== null
      if (hasObservedStream !== hasLastArrival) {
        throw new Error('link_status.observed_stream and last_arrival_seq must be present together')
      }
      if (hasObservedStream) {
        requireStreamPosition(message.observed_stream, 'link_status.observed_stream', 1)
      }
      if (hasLastArrival) {
        assertSafeInteger(message.last_arrival_seq, 'link_status.last_arrival_seq')
        if ((message.last_arrival_seq as number) < 1) {
          throw new Error('link_status.last_arrival_seq must be >= 1')
        }
        const observed = message.observed_stream as Record<string, unknown>
        if ((message.last_arrival_seq as number) > (observed.seq as number)) {
          throw new Error('link_status.last_arrival_seq cannot exceed observed_stream.seq')
        }
      }
      if ((message.received as number) < 0 || (message.lost as number) < 0) {
        throw new Error('link_status received/lost must be >= 0')
      }
      assertFiniteNumber(message.t, 'link_status.t')
      const loss = assertFiniteNumber(message.loss_rate, 'link_status.loss_rate')
      if (loss < 0 || loss > 1) throw new Error('link_status.loss_rate must be in [0, 1]')
      if (typeof message.burst !== 'boolean') throw new Error('link_status.burst must be boolean')
      break
    }
    case 'capabilities': {
      const controllerId = requireBoundedId(message.controller_id, 'capabilities.controller_id')
      const role = requireNonemptyString(message.role, 'capabilities.role')
      const principalRole = {
        controller: 'commander',
        plant: 'body',
        observer: 'observer',
        operator: 'operator',
      }[role]
      if (principalRole === undefined) {
        throw new Error('capabilities.role is unknown and cannot negotiate authority')
      }
      const identity = requireIdentityClaim(
        message.identity,
        'capabilities.identity',
        'control',
        principalRole,
      )
      if (identity.entity_id !== controllerId) {
        throw new Error('capabilities.controller_id must equal capabilities.identity.entity_id')
      }
      requireSecurityNegotiation(message, 'capabilities')
      requireGatewayAttribution(message, 'capabilities')
      if (!Array.isArray(message.stable_capabilities)) {
        throw new Error('capabilities.stable_capabilities must be an array')
      }
      if (message.stable_capabilities.length > 64) {
        throw new Error('capabilities.stable_capabilities exceeds the 64-entry limit')
      }
      const stableCapabilities = new Set<string>()
      message.stable_capabilities.forEach((raw, index) => {
        const capability = requireNonemptyString(
          raw,
          `capabilities.stable_capabilities[${index}]`,
        )
        if (!KNOWN_STABLE_CAPABILITIES.has(capability)) {
          throw new Error(
            `capabilities.stable_capabilities contains unknown or non-stable capability ${JSON.stringify(capability)}`,
          )
        }
        if (stableCapabilities.has(capability)) {
          throw new Error(
            `capabilities.stable_capabilities contains duplicate ${JSON.stringify(capability)}`,
          )
        }
        stableCapabilities.add(capability)
      })
      for (const capability of CORE_STABLE_CAPABILITIES) {
        if (!stableCapabilities.has(capability)) {
          throw new Error(
            `capabilities.stable_capabilities omits required core capability ${JSON.stringify(capability)}`,
          )
        }
      }
      if (message.plant_profile_digest !== undefined && message.plant_profile_digest !== null) {
        requireSha256(message.plant_profile_digest, 'capabilities.plant_profile_digest')
      }
      if (
        role === 'plant' &&
        (message.plant_profile_digest === undefined || message.plant_profile_digest === null)
      ) {
        throw new Error('plant capabilities require a content-addressed plant_profile_digest')
      }
      const rate = assertFiniteNumber(message.control_rate_hz, 'capabilities.control_rate_hz')
      if (rate <= 0) throw new Error('capabilities.control_rate_hz must be > 0')
      for (const field of ['sensor_channels', 'command_channels'] as const) {
        if (!Array.isArray(message[field])) throw new Error(`capabilities.${field} must be an array`)
        if (message[field].length > MAX_CHANNELS) throw new Error(`capabilities.${field} exceeds the ${MAX_CHANNELS}-channel limit`)
        const names = new Set<string>()
        ;(message[field] as unknown[]).forEach((raw, index) => {
          const channel = requireRecord(raw, `capabilities.${field}[${index}]`)
          const name = requireNonemptyString(channel.name, `capabilities.${field}[${index}].name`)
          const channelKind = requireNonemptyString(channel.kind, `capabilities.${field}[${index}].kind`)
          if (names.has(name)) throw new Error(`capabilities.${field} contains duplicate channel ${JSON.stringify(name)}`)
          names.add(name)
          if (channel.size !== undefined && channel.size !== null) {
            assertSafeInteger(channel.size, `capabilities.${field}[${index}].size`)
            if ((channel.size as number) <= 0) throw new Error(`capabilities.${field}[${index}].size must be > 0`)
          }
          assertOptionalString(channel.unit, `capabilities.${field}[${index}].unit`)
          const requirement = requireNonemptyString(channel.requirement, `capabilities.${field}[${index}].requirement`)
          if (requirement !== 'required' && requirement !== 'optional') {
            throw new Error(`capabilities.${field}[${index}].requirement must explicitly be required or optional`)
          }
          if (!KNOWN_CHANNEL_KINDS.has(channelKind)) {
            throw new Error(`capabilities.${field}[${index}].kind is unknown and cannot negotiate channel semantics`)
          }
          assertOptionalString(channel.description, `capabilities.${field}[${index}].description`)
        })
      }
      assertOptionalString(message.codec_id, 'capabilities.codec_id')
      const safety = requireRecord(message.safety, 'capabilities.safety')
      const timeout = assertFiniteNumber(safety.command_timeout_ms, 'capabilities.safety.command_timeout_ms')
      if (timeout <= 0) throw new Error('capabilities.safety.command_timeout_ms must be > 0')
      for (const field of ['max_speed_mps', 'max_tilt_rad', 'geofence_radius_m'] as const) {
        if (safety[field] !== undefined && safety[field] !== null) {
          if (assertFiniteNumber(safety[field], `capabilities.safety.${field}`) < 0) {
            throw new Error(`capabilities.safety.${field} must be >= 0`)
          }
        }
      }
      break
    }
  }
}

/**
 * JSON-wire view of a canonical type. ts-rs emits Rust `i64` fields (ids,
 * `population_sizes`, `senders`, `resolved`, `seq`, `seed`, …) as `bigint` for
 * precision-safety, but `JSON.stringify` cannot serialize a `bigint` and
 * `JSON.parse` yields `number`; NCP uses small integers, so the JSON wire uses
 * `number` (see `ncp-core/bindings/README.md`). `Wire<T>` maps `bigint → number`
 * recursively so the generated shapes stay wire-identical to the contract while
 * remaining JSON-(de)serializable.
 */
export type Wire<T> = T extends bigint
  ? number
  : T extends Array<infer U>
    ? Array<Wire<U>>
    : T extends object
      ? { [K in keyof T]: Wire<T[K]> }
      : T

// JSON-wire aliases of the reply types consumers read back off the wire.
export type SessionOpenedReply = Wire<SessionOpened>
export type SessionClosedReply = Wire<SessionClosed>
export type ObservationFrameReply = Wire<ObservationFrame>
export type ObservationData = Wire<Observation>
export type ErrorFrame = Omit<Wire<GeneratedErrorFrame>, 'code'> & { code: NcpErrorCode }

/**
 * Construction views. The canonical message types are maximally strict (ts-rs
 * marks every Rust field required), but the JSON Schemas default most fields, so
 * for *building* a request we make the defaulted members optional while keeping
 * the discriminating members required. The client fills the envelope
 * (`kind`, `ncp_version`, `session_id`, empty `bindings`).
 */
export type ChannelInput = Pick<Wire<ChannelValue>, 'data'> & Partial<Wire<ChannelValue>>
export type NetworkInput = Pick<Wire<NetworkRef>, 'kind' | 'ref'> & Partial<Wire<NetworkRef>>
export type RecordInput = Pick<Wire<RecordTarget>, 'port' | 'target' | 'observable'> &
  Partial<Wire<RecordTarget>>
export type StimulusInput = Pick<Wire<StimulusTarget>, 'port' | 'target' | 'kind'> &
  Partial<Wire<StimulusTarget>>
export type SimInput = Partial<Wire<SimConfig>>

/** Authenticated transport context supplied by the caller. Payload claims never
 * authenticate themselves; the transport adapter must bind this claim to its
 * verified peer identity before it sends an NCP message. */
export type ClientNegotiation = {
  identity: Wire<IdentityClaim>
  security_profile: 'dev-loopback-insecure' | 'production-secure'
  security_state_digest: string
  gateway_permitted: boolean
  gateway?: Wire<GatewayAttribution> | null
}

/** Exactly-once and authority context required for every lifecycle mutation. */
export type MutationInput = {
  operation: Omit<Wire<OperationContext>, 'request_digest'> & { request_digest?: string }
  authority: Wire<AuthorityLease>
}

function sealMutationRequest<T extends { operation: Record<string, unknown> }>(request: T): T {
  const supplied = request.operation.request_digest
  request.operation.request_digest = ''
  const digest = requestDigest(request)
  if (supplied !== undefined && supplied !== '' && supplied !== digest) {
    throw new Error('NCP mutation operation.request_digest does not match the constructed request')
  }
  request.operation.request_digest = digest
  return request
}

/** Any transport: serialize `message`, deliver it to the NCP session service, and
 *  resolve with the reply payload (already parsed from the wire). */
export type Send = (message: Record<string, unknown>) => Promise<unknown>

function unwrap<T>(
  reply: unknown,
  requestKind: string,
  expectedKind: string,
  expectedSessionId: string,
  expectedGeneration?: string,
  expectedOperation?: Wire<OperationContext>,
): T {
  assertNcpMessage(reply)
  if (reply.kind === 'error') {
    const error = reply as ErrorFrame
    if (error.request_kind != null && error.request_kind !== requestKind) {
      throw new Error(
        `NCP error request_kind mismatch: expected ${JSON.stringify(requestKind)}, got ${JSON.stringify(error.request_kind)}`,
      )
    }
    if (error.session_id != null && error.session_id !== expectedSessionId) {
      throw new Error(
        `NCP error session mismatch: expected ${JSON.stringify(expectedSessionId)}, got ${JSON.stringify(error.session_id)}`,
      )
    }
    if (
      expectedGeneration !== undefined &&
      error.session != null &&
      error.session.generation !== expectedGeneration
    ) {
      throw new Error(
        `NCP error generation mismatch: expected ${JSON.stringify(expectedGeneration)}, got ${JSON.stringify(error.session.generation)}`,
      )
    }
    if (expectedOperation !== undefined && error.receipt != null) {
      assertReceiptCorrelation(error.receipt, expectedOperation, 'error.receipt')
    }
    throw new Error(`NCP error ${error.code}: ${error.error}`)
  }
  const kind = reply.kind
  if (kind !== expectedKind) {
    throw new Error(
      `NCP reply kind mismatch: expected ${JSON.stringify(expectedKind)}, got ${JSON.stringify(kind)}`,
    )
  }
  // Wire 0.6: every reply must carry a COMPATIBLE ncp_version — an absent or
  // incompatible version fails closed here (never coerced), so a stale-wire
  // peer cannot silently mis-decode into this client. (`open()` additionally
  // runs the advisory contract-hash comparison.)
  const ver = (reply as { ncp_version?: unknown }).ncp_version
  if (typeof ver !== 'string') {
    throw new NcpVersionError('NCP reply carries no ncp_version (mandatory since wire 0.6)')
  }
  checkVersion(ver, true)
  const sessionId = (reply as { session_id?: unknown }).session_id
  if (sessionId !== expectedSessionId) {
    throw new Error(
      `NCP reply session mismatch: expected ${JSON.stringify(expectedSessionId)}, got ${JSON.stringify(sessionId)}`,
    )
  }
  if (expectedGeneration !== undefined) {
    const generation = (reply as { session?: { generation?: unknown } }).session?.generation
    if (generation !== expectedGeneration) {
      throw new Error(
        `NCP reply generation mismatch: expected ${JSON.stringify(expectedGeneration)}, got ${JSON.stringify(generation)}`,
      )
    }
  }
  if (expectedOperation !== undefined) {
    const receipt = (reply as { receipt?: unknown }).receipt
    assertReceiptCorrelation(receipt, expectedOperation, `${expectedKind}.receipt`)
    if (
      expectedKind === 'observation_frame' &&
      (reply as { source?: unknown }).source != null
    ) {
      throw new Error('NCP step/run RPC observation reply must omit observation-plane source')
    }
  }
  if (expectedKind === 'observation_frame') {
    const streamPos = (reply as { stream?: { seq?: unknown } }).stream
    const seq = streamPos?.seq
    if (typeof seq !== 'number' || !Number.isSafeInteger(seq) || seq < 1) {
      throw new Error(`NCP observation reply carries invalid stream.seq ${JSON.stringify(seq)}`)
    }
  }
  if (expectedKind === 'observation_frame' || expectedKind === 'session_opened') {
    assertScientificBoundary(reply as Record<string, unknown>)
  }
  return reply as T
}

function assertReceiptCorrelation(
  receipt: unknown,
  operation: Wire<OperationContext>,
  path: string,
): void {
  const validated = requireResponderReceipt(receipt, path)
  if (validated.operation_id !== operation.operation_id) {
    throw new Error(`${path}.operation_id does not match the request operation`)
  }
  if (validated.request_digest !== operation.request_digest) {
    throw new Error(`${path}.request_digest does not match the request operation`)
  }
}

const REPLAY_FINGERPRINT_DOMAIN = 'ncp.observation-replay-fingerprint.v1\0'
const replayFingerprintEncoder = new TextEncoder()

/** Deterministic, key-order-independent projection of the complete parsed reply.
 * This intentionally retains unknown fields: the client returns them to its
 * caller, so changing one at an already accepted stream position must fail even
 * though the typed canonical projection would discard it. */
function replayProjection(value: unknown, depth = 0): string {
  if (depth > 32) throw new Error('NCP observation reply fingerprint exceeds the nesting-depth budget')
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) {
      throw new Error('NCP observation reply fingerprint contains a non-finite number')
    }
    return Object.is(value, -0) ? '-0' : JSON.stringify(value)
  }
  if (typeof value === 'string') {
    for (let index = 0; index < value.length; index++) {
      const unit = value.charCodeAt(index)
      if (unit >= 0xd800 && unit <= 0xdbff) {
        const next = value.charCodeAt(index + 1)
        if (!(next >= 0xdc00 && next <= 0xdfff)) {
          throw new Error('NCP observation reply fingerprint contains an unpaired high surrogate')
        }
        index += 1
      } else if (unit >= 0xdc00 && unit <= 0xdfff) {
        throw new Error('NCP observation reply fingerprint contains an unpaired low surrogate')
      }
    }
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    const items: string[] = []
    for (let index = 0; index < value.length; index++) {
      if (!Object.hasOwn(value, index)) {
        throw new Error('NCP observation reply fingerprint contains a sparse non-JSON array')
      }
      items.push(replayProjection(value[index], depth + 1))
    }
    if (Object.keys(value).length !== value.length) {
      throw new Error('NCP observation reply fingerprint contains a non-JSON array property')
    }
    return `[${items.join(',')}]`
  }
  if (typeof value !== 'object' || value === undefined) {
    throw new Error(`NCP observation reply fingerprint contains unsupported ${typeof value} value`)
  }
  const prototype = Object.getPrototypeOf(value)
  if (prototype !== Object.prototype && prototype !== null) {
    throw new Error('NCP observation reply fingerprint contains a non-JSON object')
  }
  if (Object.getOwnPropertySymbols(value).length !== 0) {
    throw new Error('NCP observation reply fingerprint contains a non-JSON symbol key')
  }
  const object = value as Record<string, unknown>
  const entries = Object.keys(object)
    .sort()
    .map((key) => `${replayProjection(key, depth)}:${replayProjection(object[key], depth + 1)}`)
  return `{${entries.join(',')}}`
}

function observationReplyFingerprint(frame: ObservationFrameReply): string {
  const projection = REPLAY_FINGERPRINT_DOMAIN + replayProjection(frame)
  return sha256Hex(replayFingerprintEncoder.encode(projection))
}

export class NeuroSimClient {
  /** session_id -> the server-issued generation, learned at open(). */
  private readonly generations = new Map<string, string>()
  /** Non-evicting retired/seen generations; a logical session never revives one. */
  private readonly seenGenerations = new Map<string, Set<string>>()
  /** Global count backing the bounded non-evicting generation fence. */
  private seenGenerationCount = 0
  /** Per-live-generation observation epoch/high-water and full-reply replay state. */
  private readonly observationFences = new Map<
    string,
    { generation: string; epoch: string; highWater: number; replyFingerprints: Map<number, string> }
  >()
  /** Global retained position count across all live generation fences. */
  private observationPositionCount = 0
  /** Current in-flight open attempt per logical session. */
  private readonly openings = new Map<string, symbol>()
  /** Total in-flight opens, including superseded attempts for the same session. */
  private inFlightOpenCount = 0
  constructor(
    private readonly send: Send,
    private readonly negotiation: ClientNegotiation,
  ) {}

  /** Open a session: declare what to record and what to stimulate. */
  async open(
    sessionId: string,
    network: NetworkInput,
    record: RecordInput[],
    stimulus: StimulusInput[],
    sim: SimInput = {},
  ): Promise<SessionOpenedReply> {
    // The JSON wire carries int64 as a JSON number, so a seed above 2^53 would
    // lose precision before it reaches NEST. Fail fast rather than silently
    // diverge the RNG. (See proto/ncp.proto header.)
    if (sim.seed != null && !Number.isSafeInteger(sim.seed)) {
      throw new Error(`NCP: sim.seed must be a safe integer (<= 2^53-1); got ${sim.seed}`)
    }
    const request = {
      kind: 'open_session',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      network,
      record: { targets: record },
      stimulus: { targets: stimulus },
      sim,
      bindings: [],
      contract_hash: NCP_CONTRACT_HASH,
      identity: this.negotiation.identity,
      security_profile: this.negotiation.security_profile,
      security_state_digest: this.negotiation.security_state_digest,
      gateway_permitted: this.negotiation.gateway_permitted,
      gateway: this.negotiation.gateway ?? null,
    }
    assertNcpMessage(request, 'open_session')
    if (this.inFlightOpenCount >= MAX_CLIENT_GENERATIONS) {
      throw new Error('NCP client opening fence reached its non-evicting capacity')
    }
    // An attempted reopen retires the client-local binding before any transport
    // wait. If the process, transport, or peer fails mid-open, subsequent
    // mutations must fail locally until a new successful SessionOpened supplies
    // a generation; retaining the prior generation would turn uncertainty into a
    // stale-session retry.
    const attempt = Symbol(sessionId)
    this.retireGeneration(sessionId)
    this.openings.set(sessionId, attempt)
    this.inFlightOpenCount += 1
    try {
      const reply = await this.send(request)
      if (this.openings.get(sessionId) !== attempt) {
        throw new Error(
          `NCP session ${JSON.stringify(sessionId)} open result was superseded by a newer attempt`,
        )
      }
      const opened = unwrap<SessionOpenedReply>(
        reply,
        'open_session',
        'session_opened',
        sessionId,
      )
      if (!opened.ok || opened.session == null) {
        throw new Error(`NCP session open failed: ${opened.error ?? 'peer supplied no reason'}`)
      }
      if (
        opened.security_profile !== this.negotiation.security_profile ||
        opened.security_state_digest !== this.negotiation.security_state_digest ||
        opened.gateway_permitted !== this.negotiation.gateway_permitted ||
        opened.gateway?.gateway_id !== this.negotiation.gateway?.gateway_id ||
        opened.gateway?.source_wire !== this.negotiation.gateway?.source_wire
      ) {
        throw new Error('NCP session security negotiation does not match the precommitted request')
      }
      // Advisory contract-hash check (the reply half): log a mismatch, do not throw —
      // the version is the hard gate (mirrors the NCP session-service contract).
      const advisory = contractStatus((opened as { contract_hash?: string | null }).contract_hash)
      if (advisory) console.warn(`[ncp] ${advisory}`)
      const generation = opened.session.generation
      const existingSeen = this.seenGenerations.get(sessionId)
      if (existingSeen?.has(generation) === true) {
        throw new Error(
          `NCP session ${JSON.stringify(sessionId)} attempted to revive retired generation ${JSON.stringify(generation)}`,
        )
      }
      if (this.seenGenerationCount >= MAX_CLIENT_GENERATIONS) {
        throw new Error(
          `NCP session ${JSON.stringify(sessionId)} exceeded the non-evicting generation fence capacity`,
        )
      }
      let seen = existingSeen
      if (seen === undefined) {
        seen = new Set<string>()
        this.seenGenerations.set(sessionId, seen)
      }
      seen.add(generation)
      this.seenGenerationCount += 1
      this.generations.set(sessionId, generation)
      return opened
    } finally {
      this.inFlightOpenCount -= 1
      if (this.openings.get(sessionId) === attempt) this.openings.delete(sessionId)
    }
  }

  private retireGeneration(sessionId: string): void {
    this.generations.delete(sessionId)
    const observation = this.observationFences.get(sessionId)
    if (observation !== undefined) {
      this.observationPositionCount -= observation.replyFingerprints.size
      this.observationFences.delete(sessionId)
    }
  }

  private requireOpenGeneration(sessionId: string): string {
    const generation = this.generations.get(sessionId)
    if (generation === undefined) {
      throw new Error(
        `NCP session ${JSON.stringify(sessionId)} has no live generation in this client instance; open it after startup or restart before mutating`,
      )
    }
    return generation
  }

  private requireCurrentGeneration(sessionId: string, expected: string): void {
    if (this.generations.get(sessionId) !== expected) {
      throw new Error(
        `NCP session ${JSON.stringify(sessionId)} generation changed while a mutation was in flight; its result is stale`,
      )
    }
  }

  private acceptObservationPosition(
    sessionId: string,
    generation: string,
    frame: ObservationFrameReply,
  ): void {
    const { epoch, seq } = frame.stream
    const receipt = frame.receipt
    if (receipt == null) {
      throw new Error('NCP mutation observation reply carries no responder receipt')
    }
    // A receipt's result_digest is not independently recomputable at this
    // boundary. Bind terminal retries to the complete reply so an identical
    // receipt cannot mask changed result content at an accepted position.
    const fingerprint = observationReplyFingerprint(frame)
    const fence = this.observationFences.get(sessionId)
    if (fence === undefined) {
      if (seq !== 1) {
        throw new Error('NCP first observation reply for a fresh session generation must use stream.seq 1')
      }
      if (this.observationPositionCount >= MAX_CLIENT_OBSERVATION_POSITIONS) {
        throw new Error('NCP observation replay fence reached its non-evicting capacity')
      }
      this.observationFences.set(sessionId, {
        generation,
        epoch,
        highWater: 1,
        replyFingerprints: new Map([[1, fingerprint]]),
      })
      this.observationPositionCount += 1
      return
    }
    if (fence.generation !== generation || fence.epoch !== epoch) {
      throw new Error('NCP observation reply changed generation or stream epoch without a fresh open')
    }
    if (seq > fence.highWater) {
      if (this.observationPositionCount >= MAX_CLIENT_OBSERVATION_POSITIONS) {
        throw new Error('NCP observation replay fence reached its non-evicting capacity')
      }
      fence.highWater = seq
      fence.replyFingerprints.set(seq, fingerprint)
      this.observationPositionCount += 1
      return
    }
    if (seq <= fence.highWater && fence.replyFingerprints.get(seq) === fingerprint) {
      return
    }
    throw new Error(
      `NCP observation stream position is replayed, reordered, or non-increasing: high-water ${fence.highWater}, got ${seq}`,
    )
  }

  /** Advance one chunk; optionally inject `stimulus`; returns an observation frame. */
  async step(
    sessionId: string,
    mutation: MutationInput,
    stimulus: Record<string, ChannelInput> = {},
    advanceMs?: number,
  ): Promise<ObservationFrameReply> {
    const generation = this.requireOpenGeneration(sessionId)
    const request = sealMutationRequest({
      kind: 'step_request',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      session: { generation },
      operation: { ...mutation.operation },
      authority: mutation.authority,
      advance_ms: advanceMs ?? null,
      stimulus: {
        kind: 'stimulus_frame',
        ncp_version: NCP_VERSION,
        session_id: sessionId,
        session: { generation },
        values: stimulus,
      },
    })
    assertNcpMessage(request, 'step_request')
    const reply = await this.send(request)
    this.requireCurrentGeneration(sessionId, generation)
    const observation = unwrap<ObservationFrameReply>(
      reply,
      'step_request',
      'observation_frame',
      sessionId,
      generation,
      request.operation as Wire<OperationContext>,
    )
    this.acceptObservationPosition(sessionId, generation, observation)
    return observation
  }

  /** Batch: advance `durationMs` holding `stimulus`; returns an observation frame. */
  async run(
    sessionId: string,
    durationMs: number,
    mutation: MutationInput,
    stimulus: Record<string, ChannelInput> = {},
  ): Promise<ObservationFrameReply> {
    const generation = this.requireOpenGeneration(sessionId)
    const request = sealMutationRequest({
      kind: 'run_request',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      session: { generation },
      operation: { ...mutation.operation },
      authority: mutation.authority,
      duration_ms: durationMs,
      stimulus: {
        kind: 'stimulus_frame',
        ncp_version: NCP_VERSION,
        session_id: sessionId,
        session: { generation },
        values: stimulus,
      },
    })
    assertNcpMessage(request, 'run_request')
    const reply = await this.send(request)
    this.requireCurrentGeneration(sessionId, generation)
    const observation = unwrap<ObservationFrameReply>(
      reply,
      'run_request',
      'observation_frame',
      sessionId,
      generation,
      request.operation as Wire<OperationContext>,
    )
    this.acceptObservationPosition(sessionId, generation, observation)
    return observation
  }

  /** Close the session. */
  async close(sessionId: string, mutation: MutationInput): Promise<SessionClosedReply> {
    const generation = this.requireOpenGeneration(sessionId)
    const request = sealMutationRequest({
      kind: 'close_session',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      session: { generation },
      operation: { ...mutation.operation },
      authority: mutation.authority,
    })
    assertNcpMessage(request, 'close_session')
    // A close attempt makes the prior generation unavailable immediately. A
    // timeout or lost reply leaves the outcome unknown; it never restores local
    // mutation authority. A concurrent successful open may install a new
    // generation without a late close result deleting it.
    this.retireGeneration(sessionId)
    const reply = await this.send(request)
    return unwrap<SessionClosedReply>(
      reply,
      'close_session',
      'session_closed',
      sessionId,
      generation,
      request.operation as Wire<OperationContext>,
    )
  }
}
