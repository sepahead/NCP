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
  ChannelValue,
  ErrorFrame as GeneratedErrorFrame,
  NetworkRef,
  Observation,
  ObservationFrame,
  RecordTarget,
  SessionClosed,
  SessionOpened,
  SimConfig,
  StimulusTarget,
} from './generated/index.js'

/** The protocol version this client stamps on every request (`ncp_version`).
 * Wire 0.8 splits the overloaded `seq` into a per-stream `stream` position + a
 * correlation-only `source`, adds `session` (generation) + `session_id` on every
 * session-scoped frame, and retires the top-level `seq`/`last_seq`. */
export const NCP_VERSION = '0.8'

/**
 * This peer's contract-hash (`ncp_core::CONTRACT_HASH` — FNV-1a of the canonicalized
 * proto). Pinned, cross-language-anchored to the Rust/Python peers and verified
 * against the proto in those peers' CI. Carried in `open()` and compared to the
 * server's reply as an **advisory** signal (see `contractStatus`): a mismatch is
 * surfaced, not thrown — `ncp_version` is the hard compatibility gate.
 */
export const NCP_CONTRACT_HASH = 'd1b50a2d8a265276'

/** Exact integer range shared by every JSON implementation (binary64 included). */
export const JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991
export const JSON_SAFE_INTEGER_MIN = -JSON_SAFE_INTEGER_MAX
export const MAX_HORIZON_STEPS = 65_536

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
 *  parser: 1 or 2 dot-separated base-10 components, no trailing junk, no third
 *  component (semver patch is not part of the wire id). A missing minor ("1") is
 *  minor 0; anything else throws — never silently coerced to 0 (that would turn the
 *  fail-closed guard fail-open the moment our own minor is 0). */
function parseMajorMinor(version: string): [bigint, bigint] {
  const fail = (): never => {
    throw new NcpVersionError(`unparseable ncp_version ${JSON.stringify(version)}`)
  }
  const parts = version.split('.')
  if (parts.length < 1 || parts.length > 2) fail()
  const part = (s: string | undefined): bigint => {
    // Language-neutral grammar: ASCII decimal digits only, bounded by u64::MAX.
    // BigInt preserves the full Rust range instead of imposing JS's 2^53 limit.
    if (s === undefined || s.length > 20 || !/^[0-9]+$/.test(s)) return fail()
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
    'kind',
    'ncp_version',
    'role',
    'safety',
    'sensor_channels',
  ],
  close_session: ['kind', 'ncp_version', 'session', 'session_id'],
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
  error: ['error', 'kind', 'ncp_version'],
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
  open_session: ['kind', 'ncp_version', 'network', 'session_id'],
  run_request: ['duration_ms', 'kind', 'ncp_version', 'session', 'session_id'],
  sensor_frame: ['kind', 'ncp_version', 'session', 'session_id', 'stream'],
  session_closed: ['kind', 'ncp_version', 'ok', 'session', 'session_id'],
  session_opened: ['backend', 'kind', 'ncp_version', 'ok', 'session_id'],
  step_request: ['kind', 'ncp_version', 'session', 'session_id'],
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

/** Wire 0.8: a transport-neutral session_id (1..=64 bytes, safe key segment). */
function requireSessionId(value: unknown, path: string): void {
  if (typeof value !== 'string' || value.length === 0 || value.length > 64) {
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

/** Wire 0.8: a `StreamPosition` — epoch (UUIDv4) + seq (>= minSeq, JSON-safe). */
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

function assertOptionalBoolean(value: unknown, path: string): void {
  if (value === undefined) return
  if (typeof value !== 'boolean') throw new Error(`${path} must be a boolean`)
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
  const sessionId = requireNonemptyString(message.session_id, `${kind}.session_id`)
  if (/[/*$#?\s\u0000-\u001f\u007f-\u009f]/u.test(sessionId)) {
    throw new Error(`${kind}.session_id must be a safe single key segment`)
  }
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
    ['open_session', 'session_opened', 'step_request', 'run_request', 'stimulus_frame', 'observation_frame', 'close_session', 'session_closed', 'link_status'].includes(kind)
  ) {
    assertSessionId(message, kind)
  }

  switch (kind) {
    case 'open_session': {
      const network = requireRecord(message.network, 'open_session.network')
      requireNonemptyString(network.kind, 'open_session.network.kind')
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
        if (sim.mode !== undefined) requireNonemptyString(sim.mode, 'open_session.sim.mode')
      }
      const record = message.record === undefined ? undefined : requireRecord(message.record, 'open_session.record')
      const recordTargets = record?.targets
      if (recordTargets !== undefined) {
        if (!Array.isArray(recordTargets)) throw new Error('open_session.record.targets must be an array')
        recordTargets.forEach((raw, index) => {
          const target = requireRecord(raw, `open_session.record.targets[${index}]`)
          requireNonemptyString(target.port, `open_session.record.targets[${index}].port`)
          requireNonemptyString(target.target, `open_session.record.targets[${index}].target`)
          requireNonemptyString(target.observable, `open_session.record.targets[${index}].observable`)
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
          requireNonemptyString(target.kind, `open_session.stimulus.targets[${index}].kind`)
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
          requireNonemptyString(entity.role, `open_session.bindings[${index}].entity.role`)
          assertStringMap(entity.meta, `open_session.bindings[${index}].entity.meta`)
        })
      }
      assertOptionalString(message.contract_hash, 'open_session.contract_hash')
      break
    }
    case 'session_opened': {
      const backend = requireNonemptyString(message.backend, 'session_opened.backend')
      if (typeof message.ok !== 'boolean') throw new Error('session_opened.ok must be a boolean')
      assertSafeIntegerMap(message.resolved, 'session_opened.resolved')
      if (message.ok) {
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
      }
      assertOptionalString(message.contract_hash, 'session_opened.contract_hash')
      break
    }
    case 'session_closed':
      if (message.ok !== true) throw new Error('session_closed.ok must be true; failures use ErrorFrame')
      break
    case 'error':
      requireNonemptyString(message.error, 'error.error')
      if (message.request_kind !== undefined && message.request_kind !== null) {
        requireNonemptyString(message.request_kind, 'error.request_kind')
      }
      if (message.session_id !== undefined && message.session_id !== null) {
        assertSessionId(message, 'error')
      }
      break
    case 'run_request': {
      const duration = assertFiniteNumber(message.duration_ms, 'run_request.duration_ms')
      if (duration <= 0) throw new Error('run_request.duration_ms must be > 0')
      if (message.stimulus !== undefined && message.stimulus !== null) {
        assertNcpMessage(message.stimulus, 'stimulus_frame')
        if ((message.stimulus as Record<string, unknown>).session_id !== message.session_id) {
          throw new Error('run_request.stimulus session_id does not match outer request')
        }
      }
      break
    }
    case 'step_request':
      if (message.advance_ms !== undefined && message.advance_ms !== null && assertFiniteNumber(message.advance_ms, 'step_request.advance_ms') < 0) {
        throw new Error('step_request.advance_ms must be >= 0')
      }
      if (message.stimulus !== undefined && message.stimulus !== null) {
        assertNcpMessage(message.stimulus, 'stimulus_frame')
        if ((message.stimulus as Record<string, unknown>).session_id !== message.session_id) {
          throw new Error('step_request.stimulus session_id does not match outer request')
        }
      }
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
          const ttl = assertFiniteNumber(message.ttl_ms, 'command_frame.ttl_ms')
          if (ttl <= 0) throw new Error('command_frame Active ttl_ms must be > 0')
          assertChannelMap(message.channels, 'command_frame.channels', true)
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
              message.horizon.length > Math.floor(ttl / dt)
            ) {
              throw new Error(
                `command_frame.horizon must satisfy N <= ttl_ms / horizon_dt_ms and N <= ${MAX_HORIZON_STEPS}`,
              )
            }
          }
        }
        if (message.horizon_dt_ms !== undefined && message.horizon_dt_ms !== null) {
          assertFiniteNumber(message.horizon_dt_ms, 'command_frame.horizon_dt_ms')
        }
      }
      if (kind === 'observation_frame') {
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
          requireNonemptyString(record.observable, `observation_frame.records[${JSON.stringify(recordKey)}].observable`)
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
      for (const field of ['received', 'lost'] as const) {
        assertSafeInteger(message[field], `link_status.${field}`)
      }
      if (message.last_arrival_seq !== undefined && message.last_arrival_seq !== null) {
        assertSafeInteger(message.last_arrival_seq, 'link_status.last_arrival_seq')
        if ((message.last_arrival_seq as number) < 0) {
          throw new Error('link_status.last_arrival_seq must be >= 0')
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
      requireNonemptyString(message.controller_id, 'capabilities.controller_id')
      requireNonemptyString(message.role, 'capabilities.role')
      const rate = assertFiniteNumber(message.control_rate_hz, 'capabilities.control_rate_hz')
      if (rate <= 0) throw new Error('capabilities.control_rate_hz must be > 0')
      for (const field of ['sensor_channels', 'command_channels'] as const) {
        if (!Array.isArray(message[field])) throw new Error(`capabilities.${field} must be an array`)
        const names = new Set<string>()
        ;(message[field] as unknown[]).forEach((raw, index) => {
          const channel = requireRecord(raw, `capabilities.${field}[${index}]`)
          const name = requireNonemptyString(channel.name, `capabilities.${field}[${index}].name`)
          requireNonemptyString(channel.kind, `capabilities.${field}[${index}].kind`)
          if (names.has(name)) throw new Error(`capabilities.${field} contains duplicate channel ${JSON.stringify(name)}`)
          names.add(name)
          if (channel.size !== undefined && channel.size !== null) {
            assertSafeInteger(channel.size, `capabilities.${field}[${index}].size`)
            if ((channel.size as number) <= 0) throw new Error(`capabilities.${field}[${index}].size must be > 0`)
          }
          assertOptionalString(channel.unit, `capabilities.${field}[${index}].unit`)
          assertOptionalBoolean(channel.optional, `capabilities.${field}[${index}].optional`)
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
export type ErrorFrame = Wire<GeneratedErrorFrame>

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

/** Any transport: serialize `message`, deliver it to the NCP session service, and
 *  resolve with the reply payload (already parsed from the wire). */
export type Send = (message: Record<string, unknown>) => Promise<unknown>

function unwrap<T>(
  reply: unknown,
  requestKind: string,
  expectedKind: string,
  expectedSessionId: string,
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
    throw new Error(`NCP error: ${error.error}`)
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

export class NeuroSimClient {
  constructor(private readonly send: Send) {}

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
    }
    assertNcpMessage(request, 'open_session')
    const reply = await this.send(request)
    const opened = unwrap<SessionOpenedReply>(
      reply,
      'open_session',
      'session_opened',
      sessionId,
    )
    // Advisory contract-hash check (the reply half): log a mismatch, do not throw —
    // the version is the hard gate (mirrors the NCP session-service contract).
    const advisory = contractStatus((opened as { contract_hash?: string | null }).contract_hash)
    if (advisory) console.warn(`[ncp] ${advisory}`)
    return opened
  }

  /** Advance one chunk; optionally inject `stimulus`; returns an observation frame. */
  async step(
    sessionId: string,
    stimulus: Record<string, ChannelInput> = {},
    advanceMs?: number,
  ): Promise<ObservationFrameReply> {
    const request = {
      kind: 'step_request',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      advance_ms: advanceMs ?? null,
      stimulus: {
        kind: 'stimulus_frame',
        ncp_version: NCP_VERSION,
        session_id: sessionId,
        values: stimulus,
      },
    }
    assertNcpMessage(request, 'step_request')
    const reply = await this.send(request)
    return unwrap<ObservationFrameReply>(
      reply,
      'step_request',
      'observation_frame',
      sessionId,
    )
  }

  /** Batch: advance `durationMs` holding `stimulus`; returns an observation frame. */
  async run(
    sessionId: string,
    durationMs: number,
    stimulus: Record<string, ChannelInput> = {},
  ): Promise<ObservationFrameReply> {
    const request = {
      kind: 'run_request',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      duration_ms: durationMs,
      stimulus: {
        kind: 'stimulus_frame',
        ncp_version: NCP_VERSION,
        session_id: sessionId,
        values: stimulus,
      },
    }
    assertNcpMessage(request, 'run_request')
    const reply = await this.send(request)
    return unwrap<ObservationFrameReply>(
      reply,
      'run_request',
      'observation_frame',
      sessionId,
    )
  }

  /** Close the session. */
  async close(sessionId: string): Promise<SessionClosedReply> {
    const request = {
      kind: 'close_session',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
    }
    assertNcpMessage(request, 'close_session')
    const reply = await this.send(request)
    return unwrap<SessionClosedReply>(
      reply,
      'close_session',
      'session_closed',
      sessionId,
    )
  }
}
