// Behavioral conformance — the TypeScript peer vs the shared decision corpus
// (conformance/behavior/vectors.json), the same corpus the Rust reference is pinned
// to (ncp-core/tests/behavior_conformance.rs) and the Python/C++ peers replay.
//
// Since wire 0.6, ncp-ts ships the plant-side safety port (SafetyGovernor /
// CommandWatchdog / ActionBuffer in `safety.ts`), so this runner replays the FULL
// `govern` and `action_buffer` corpora through the TS safety primitives in
// addition to the full message-validation and handshake functions.
//
// Fail-loud coverage: every corpus function must be either implemented here or in an
// explicit out-of-scope allowlist; a corpus function in NEITHER set is a hard error,
// so a future corpus addition can never silently shrink TS coverage. Reads the single
// repo-root corpus (NOT a vendored copy) and asserts its header pins match ncp-ts's.
//
// Run after `npm run build` (imports the published dist surface):
//   node ncp-ts/scripts/check-behavior.mjs

import { readFileSync, readdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
// Import the public package barrel with Node's native ESM loader. This makes the
// behavioral corpus double as an entrypoint smoke: extensionless or stale dist
// exports fail before any vector can run.
import {
  NCP_VERSION,
  NCP_CONTRACT_HASH,
  checkVersion,
  NcpVersionError,
  contractStatus,
  assertNcpMessage,
  NcpScientificBoundaryError,
  NeuroSimClient,
  ActionBuffer,
  CommandWatchdog,
  SafetyGovernor,
  assertWireFrame,
  maxHorizonLen,
  parseBoundedJson,
  BoundedJsonError,
  JSON_LIMITS,
  requestDigest,
  NCP_ERROR_CODES,
} from '../dist/index.js'

// Wire 0.8: valid canonical UUIDv4 identity for the hand-written fixtures.
const EP = '00000000-0000-4000-8000-000000000001'
const GEN = '00000000-0000-4000-8000-0000000000a2'
const OP = '00000000-0000-4000-8000-0000000000c1'
const DIGEST = 'a'.repeat(64)
const AUTHORITY = {
  session_epoch: GEN,
  term: 1,
  lease_id: '00000000-0000-4000-8000-0000000000b1',
  issuer_principal_id: 'authority',
  holder_principal_id: 'controller',
  holder_entity_id: 'controller',
  issued_at_utc_ms: 1_000,
  expires_at_utc_ms: 61_000,
}
const MUTATION = {
  operation: {
    operation_id: OP,
    session_epoch: GEN,
    expected_state_version: 0,
    deadline_utc_ms: 62_000,
    retry: false,
  },
  authority: AUTHORITY,
}
const NEGOTIATION = {
  identity: {
    principal_id: 'commander-principal',
    entity_id: 'controller',
    role: 'commander',
    plane: 'control',
  },
  security_profile: 'dev-loopback-insecure',
  security_state_digest: 'b'.repeat(64),
  gateway_permitted: false,
}

const here = dirname(fileURLToPath(import.meta.url)) // ncp-ts/scripts
const corpusPath = join(here, '..', '..', 'conformance', 'behavior', 'vectors.json')
const corpus = JSON.parse(readFileSync(corpusPath, 'utf8'))
const manifestPath = join(here, '..', '..', 'conformance', 'manifest.v1.json')
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
const requestDigestPath = join(here, '..', '..', 'conformance', 'request-digest', 'v1.json')
const requestDigestVectors = JSON.parse(readFileSync(requestDigestPath, 'utf8'))
const errorRegistryPath = join(here, '..', '..', 'contract', 'errors.v1.json')
const errorRegistry = JSON.parse(readFileSync(errorRegistryPath, 'utf8'))

const failures = []
const executedIds = new Set()
const check = (cond, msg) => {
  if (!cond) failures.push(msg)
}

// The TS peer's pinned constants must match the corpus header.
check(
  corpus.ncp_version === NCP_VERSION,
  `corpus ncp_version ${corpus.ncp_version} != ncp-ts ${NCP_VERSION}`,
)
check(
  corpus.contract_hash === NCP_CONTRACT_HASH,
  `corpus contract_hash ${corpus.contract_hash} != ncp-ts ${NCP_CONTRACT_HASH}`,
)
check(manifest.wire_version === NCP_VERSION, 'conformance manifest wire version mismatch')
check(manifest.contract_hash === NCP_CONTRACT_HASH, 'conformance manifest contract hash mismatch')
check(
  JSON.stringify(errorRegistry.codes.map(({ code }) => code)) === JSON.stringify(NCP_ERROR_CODES),
  'TypeScript error-code registry differs from contract/errors.v1.json',
)

// Functions ncp-ts implements vs deliberately out-of-scope for the thin client.
// All shared decision families must be explicitly implemented here.
const IMPLEMENTED = new Set([
  'check_version',
  'contract_status',
  'validate',
  'govern',
  'action_buffer',
])
const OUT_OF_SCOPE = new Set([])
for (const fn of Object.keys(corpus.cases)) {
  check(
    IMPLEMENTED.has(fn) || OUT_OF_SCOPE.has(fn),
    `corpus function ${fn} is neither implemented in ncp-ts nor in the out-of-scope ` +
      `allowlist — update ncp-ts/scripts/check-behavior.mjs (do not let it silently drop)`,
  )
}

let covered = 0

const applyDigestCase = (base, vector) => {
  const request = structuredClone(base)
  for (const patch of vector.patch) {
    let parent = request
    for (const segment of patch.path.slice(0, -1)) parent = parent[segment]
    const leaf = patch.path.at(-1)
    if (patch.op === 'set') parent[leaf] = structuredClone(patch.value)
    else if (patch.op === 'remove') delete parent[leaf]
    else throw new Error(`unknown request-digest patch op ${JSON.stringify(patch.op)}`)
  }
  return request
}

for (const vector of requestDigestVectors.cases) {
  let got
  try {
    got = requestDigest(applyDigestCase(requestDigestVectors.base_request, vector))
  } catch (error) {
    failures.push(`request-digest[${vector.id}]: raised ${error}`)
  }
  check(
    got === vector.expected_digest,
    `request-digest[${vector.id}]: got ${got}, expected ${vector.expected_digest}`,
  )
  executedIds.add(`request-digest/${vector.id}`)
  covered++
}

// Canonical wire-shape fixtures — every shipped JSON message kind must pass the
// actual TypeScript ingress gate, not merely overlap with behavior examples.
const vectorsDir = join(here, '..', '..', 'conformance', 'vectors')
let goldenCovered = 0
for (const filename of readdirSync(vectorsDir).filter((name) => name.endsWith('.json')).sort()) {
  const message = JSON.parse(readFileSync(join(vectorsDir, filename), 'utf8'))
  const kind = message.kind
  try {
    assertNcpMessage(message, kind)
    if (['sensor_frame', 'command_frame', 'observation_frame'].includes(kind)) {
      assertWireFrame(message, kind)
    }
  } catch (error) {
    failures.push(`golden[${filename}]: canonical ${JSON.stringify(kind)} rejected: ${error}`)
  }
  executedIds.add(`wire/${kind}/canonical`)
  goldenCovered++
}

// SimConfig has two non-nullable timing controls and two nullable optionals.
// Keep the raw-shape distinction pinned even if the shared corpus is temporarily
// consumed from an older tag that predates these negative vectors.
for (const field of ['dt_ms', 'chunk_ms']) {
  let rejected = false
  try {
    assertNcpMessage(
      {
        kind: 'open_session',
        ncp_version: NCP_VERSION,
        session_id: 'null-sim-timing',
        network: { kind: 'builtin', ref: 'iaf_cond_exp' },
        sim: { [field]: null },
      },
      'open_session',
    )
  } catch {
    rejected = true
  }
  check(rejected, `validate: open_session.sim.${field}=null rejected`)
}

// check_version — full parity with the reference gate.
for (const c of corpus.cases.check_version) {
  const { name, input, expect } = c
  let got
  let threw = false
  try {
    got = checkVersion(input.version, input.strict)
  } catch (e) {
    threw = true
    check(e instanceof NcpVersionError, `check_version[${name}]: threw non-NcpVersionError ${e}`)
  }
  if (expect.error) check(threw, `check_version[${name}]: expected throw, got ${got}`)
  else
    check(
      !threw && got === expect.compatible,
      `check_version[${name}]: want compatible=${expect.compatible}, got ${threw ? '<threw>' : got}`,
    )
  executedIds.add(`behavior/check_version/${name}`)
  covered++
}

// contract_status — ncp-ts collapses match + not_advertised -> null (advisory-clear)
// and mismatch -> an advisory string. Assert the advisory DECISION (warn iff mismatch),
// which is exactly what the client acts on.
for (const c of corpus.cases.contract_status) {
  const { name, input, expect } = c
  const advisory = contractStatus(input.peer_hash)
  check(
    (advisory !== null) === (expect.status === 'mismatch'),
    `contract_status[${name}]: advisory=${JSON.stringify(advisory)} vs expected ${expect.status}`,
  )
  executedIds.add(`behavior/contract_status/${name}`)
  covered++
}

// validate — every vector goes through the full TS ingress gate; data-plane
// vectors additionally exercise the specialized assertWireFrame path.
const hasBoundary = (m) => {
  const carrier = m.kind === 'session_opened' && m.provenance ? m.provenance : m
  return 'is_simulation_output' in carrier || 'calibrated_posterior' in carrier
}
let boundaryCovered = 0
let dataPlaneCovered = 0
for (const c of corpus.cases.validate) {
  const { name, input, expect } = c
  const boundary = hasBoundary(input.message)
  const dataPlane = ['sensor_frame', 'command_frame', 'observation_frame'].includes(input.kind)
  let threw = false
  try {
    assertNcpMessage(input.message, input.kind)
    if (dataPlane) assertWireFrame(input.message, input.kind)
  } catch (e) {
    threw = true
    if (
      boundary &&
      !dataPlane &&
      expect.valid === false &&
      (name.includes('calibrated') || name.includes('not_sim'))
    ) {
      check(e instanceof NcpScientificBoundaryError, `validate[${name}]: threw non-boundary ${e}`)
    }
  }
  check(threw === !expect.valid, `validate[${name}]: throw=${threw} vs expected valid=${expect.valid}`)
  if (boundary) boundaryCovered++
  if (dataPlane) dataPlaneCovered++
  executedIds.add(`behavior/validate/${name}`)
  covered++
}

// govern — the FULL corpus through the TS SafetyGovernor (a fresh governor per
// vector, exactly like the Rust/Python/C++ runners: govern() latches ESTOP).
const velocityMagnitude = (frame) => {
  const data = frame?.channels?.velocity_setpoint?.data
  return Array.isArray(data) ? Math.sqrt(data.reduce((s, c) => s + c * c, 0)) : 0
}
for (const c of corpus.cases.govern) {
  const { name, input, expect } = c
  const gov = new SafetyGovernor({
    max_speed_mps: input.limits.max_speed_mps ?? null,
    max_tilt_rad: input.limits.max_tilt_rad ?? null,
    geofence_radius_m: input.limits.geofence_radius_m ?? null,
    command_timeout_ms: input.limits.command_timeout_ms,
  })
  const got = gov.govern(
    input.command,
    input.sensor ?? null,
    input.now_s,
    input.last_sensor_s ?? null,
  )
  check(got.mode === expect.mode, `govern[${name}]: mode ${got.mode} != ${expect.mode}`)
  if (typeof expect.velocity_setpoint_magnitude === 'number') {
    const mag = velocityMagnitude(got)
    check(
      Math.abs(mag - expect.velocity_setpoint_magnitude) < 1e-9,
      `govern[${name}]: |v| ${mag} != ${expect.velocity_setpoint_magnitude}`,
    )
  }
  executedIds.add(`behavior/govern/${name}`)
  covered++
}

// action_buffer — stateful replay/deadline/ESTOP decisions. This is separate
// from the one-shot governor vectors because ordering and reset behavior are the
// safety properties under test.
for (const c of corpus.cases.action_buffer) {
  const buffer = new ActionBuffer()
  for (const [index, operation] of c.operations.entries()) {
    if (operation.op === 'command') {
      buffer.onCommand(operation.now_s, operation.command)
    } else if (operation.op === 'reset') {
      buffer.reset()
    } else if (operation.op === 'active') {
      const output = buffer.active(operation.now_s)
      check(
        (output !== null) === operation.expect.active,
        `action_buffer[${c.name}][${index}]: active=${output !== null} != ${operation.expect.active}`,
      )
      check(
        buffer.isEstopped() === operation.expect.estopped,
        `action_buffer[${c.name}][${index}]: estopped=${buffer.isEstopped()} != ${operation.expect.estopped}`,
      )
      if (typeof operation.expect.value === 'number') {
        const value = output?.velocity_setpoint?.data?.[0]
        check(
          typeof value === 'number' && Math.abs(value - operation.expect.value) < 1e-12,
          `action_buffer[${c.name}][${index}]: value=${value} != ${operation.expect.value}`,
        )
      }
    } else {
      check(false, `action_buffer[${c.name}][${index}]: unknown op ${operation.op}`)
    }
  }
  executedIds.add(`behavior/action_buffer/${c.name}`)
  covered++
}

// ── Safety self-checks: the wire-1.0 stream/ttl/latch semantics of the TS port ──
// (mirrors the ncp-core unit tests; no test framework in ncp-ts, so asserted here)
{
  // CommandWatchdog: ttl expiry, duplicate no-refresh, unstamped never refreshes.
  const wd = new CommandWatchdog()
  check(wd.shouldHold(0.0), 'watchdog: no command yet -> HOLD')
  wd.onCommand(1.0, 200, 1)
  check(!wd.shouldHold(1.1), 'watchdog: within ttl -> live')
  check(wd.shouldHold(1.3), 'watchdog: past ttl -> HOLD')
  wd.onCommand(2.0, 200, 5)
  wd.onCommand(2.05, 200, 5) // duplicate
  wd.onCommand(2.05, 200, 0) // unstamped
  wd.onCommand(2.05, 200, -3) // negative
  check(wd.shouldHold(2.3), 'watchdog: duplicates/unstamped must not extend the deadline')
  // Expiry never reopens a lower/equal sequence; restart needs fresh state.
  const wd2 = new CommandWatchdog()
  wd2.onCommand(1.0, 200, 1000)
  wd2.onCommand(1.05, 200, 1)
  check(wd2.shouldHold(1.35), 'watchdog: low seq on a LIVE stream must not refresh')
  wd2.onCommand(1.5, 200, 1)
  check(wd2.shouldHold(1.6), 'watchdog: post-expiry lower seq remains rejected')
  wd2.onCommand(2.0, 200, 1000)
  check(wd2.shouldHold(2.05), 'watchdog: equal-seq replay never re-anchors')
  const freshWd = new CommandWatchdog()
  freshWd.onCommand(2.0, 200, 1)
  check(!freshWd.shouldHold(2.05), 'watchdog: a fresh declaration accepts its first seq')

  // Local ActionBuffer: unstamped Active rejected; admitted ESTOP latches; horizon replay.
  const ab = new ActionBuffer()
  ab.onCommand(1.0, {
    kind: 'command_frame',
    ncp_version: NCP_VERSION,
    mode: 'active',
    stream: { epoch: EP, seq: 0 }, session: { generation: GEN }, session_id: 's',
    authority: AUTHORITY,
    ttl_ms: 200,
    channels: { velocity_setpoint: { data: [9] } },
  })
  check(ab.shouldHold(1.0), 'buffer: unstamped Active never actuates')
  ab.onCommand(1.0, {
    kind: 'command_frame',
    ncp_version: NCP_VERSION,
    mode: 'active',
    stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
    authority: AUTHORITY,
    ttl_ms: 200,
    channels: { velocity_setpoint: { data: [-0.1] } },
    horizon: [
      { velocity_setpoint: { data: [-0.2] } },
      { velocity_setpoint: { data: [-0.3] } },
    ],
    horizon_dt_ms: 50,
  })
  const at = (t) => ab.active(t)?.velocity_setpoint?.data?.[0]
  check(at(1.0) === -0.1 && at(1.06) === -0.2 && at(1.11) === -0.3, 'buffer: horizon replays')
  check(ab.shouldHold(1.16), 'buffer: horizon drained -> HOLD')
  check(ab.shouldHold(1.3), 'buffer: past ttl -> HOLD')
  ab.onCommand(2.0, { mode: 'estop', stream: { epoch: EP, seq: 0 }, session: { generation: GEN }, session_id: 's', channels: {} }) // unstamped ESTOP still latches
  check(ab.isEstopped(), 'buffer: an unstamped ESTOP still latches')
  ab.onCommand(2.1, { kind: 'command_frame', ncp_version: NCP_VERSION, mode: 'active', stream: { epoch: EP, seq: 2 }, session: { generation: GEN }, session_id: 's', authority: AUTHORITY, ttl_ms: 200, channels: { velocity_setpoint: { data: [1] } } })
  check(ab.shouldHold(2.1), 'buffer: latched ESTOP suppresses later Active')
  ab.reset()
  check(ab.shouldHold(2.1), 'buffer: reset discards every pre-ESTOP command')
  check(ab.isRetired(), 'buffer: reset retires the old generation context')
  ab.onCommand(2.2, { kind: 'command_frame', ncp_version: NCP_VERSION, mode: 'active', stream: { epoch: EP, seq: 3 }, session: { generation: GEN }, session_id: 's', authority: AUTHORITY, ttl_ms: 200, channels: { velocity_setpoint: { data: [1] } } })
  check(ab.shouldHold(2.2), 'buffer: retired context cannot restore actuation')

  const aliasBuffer = new ActionBuffer()
  const callerOwned = {
    kind: 'command_frame',
    ncp_version: NCP_VERSION,
    mode: 'active',
    stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
    authority: AUTHORITY,
    ttl_ms: 200,
    channels: { velocity_setpoint: { data: [0.25] } },
  }
  aliasBuffer.onCommand(3, callerOwned)
  callerOwned.mode = 'hold'
  callerOwned.channels.velocity_setpoint.data[0] = 99
  check(
    aliasBuffer.active(3)?.velocity_setpoint?.data?.[0] === 0.25,
    'buffer: caller mutation after acceptance cannot alter live actuation',
  )

  // maxHorizonLen bounds.
  check(maxHorizonLen(200, 50) === 3, 'maxHorizonLen: strict integer TTL boundary')
  check(maxHorizonLen(250, 100) === 2, 'maxHorizonLen: non-integer TTL boundary')
  check(maxHorizonLen(100, 100) === 0, 'maxHorizonLen: first future step at expiry is excluded')
  check(maxHorizonLen(Infinity, 50) === 0, 'maxHorizonLen: non-finite ttl -> 0')
  check(maxHorizonLen(200, 0) === 0, 'maxHorizonLen: dt<=0 -> 0')
  check(maxHorizonLen(60_000, 0.5) === 65_536, 'maxHorizonLen: resource ceiling')

  // Universal raw-JSON boundary: duplicate decoded keys and lone surrogates are
  // rejected before JSON.parse can collapse/accept them.
  try {
    parseBoundedJson('{"a":1,"\\u0061":2}')
    check(false, 'bounded JSON: duplicate decoded key accepted')
  } catch (error) {
    check(
      error instanceof BoundedJsonError && error.code === 'NCP-LIMIT-007',
      `bounded JSON: duplicate key wrong error ${String(error)}`,
    )
  }
  try {
    parseBoundedJson('"\\ud800"')
    check(false, 'bounded JSON: lone surrogate accepted')
  } catch (error) {
    check(
      error instanceof BoundedJsonError && error.code === 'NCP-LIMIT-008',
      `bounded JSON: lone surrogate wrong error ${String(error)}`,
    )
  }
  const exactIntegerBoundaries = parseBoundedJson(
    '{"future_extension":{"positive":9007199254740991,"negative":-9007199254740991}}',
  )
  check(
    exactIntegerBoundaries.future_extension.positive === JSON_LIMITS.safeIntegerMax &&
      exactIntegerBoundaries.future_extension.negative === JSON_LIMITS.safeIntegerMin,
    'bounded JSON: exact integer boundaries remain admissible in unknown extensions',
  )
  for (const unsafeInteger of ['9007199254740992', '-9007199254740992']) {
    try {
      parseBoundedJson(`{"future_extension":${unsafeInteger}}`)
      check(false, `bounded JSON: unsafe integer ${unsafeInteger} accepted in unknown extension`)
    } catch (error) {
      check(
        error instanceof BoundedJsonError && error.code === 'NCP-LIMIT-006',
        `bounded JSON: unsafe integer ${unsafeInteger} returned wrong error ${String(error)}`,
      )
    }
  }
  try {
    parseBoundedJson('{"future_extension":9007199254740992.5}')
    check(true, 'bounded JSON: finite non-integer remains governed by the magnitude budget')
  } catch (error) {
    check(false, `bounded JSON: finite non-integer policy changed ${String(error)}`)
  }
  try {
    assertNcpMessage({
      kind: 'error',
      ncp_version: NCP_VERSION,
      code: 'NCP-WIRE-001',
      error: 'invalid',
      session_id: `bad\ud800`,
      session: { generation: GEN },
    })
    check(false, 'validator: unpaired surrogate accepted in an in-memory session_id')
  } catch {
    check(true, 'validator: unpaired surrogate rejected in an in-memory session_id')
  }
  // The outer byte gate must not duplicate an oversized WebSocket string into a
  // full TextEncoder buffer before rejecting it. A throwing encoder proves the
  // admission decision is made by the allocation-free bounded counter.
  const originalTextEncoder = globalThis.TextEncoder
  globalThis.TextEncoder = class RejectingTextEncoder {
    encode() {
      throw new Error('outer frame gate allocated a TextEncoder buffer')
    }
  }
  try {
    try {
      parseBoundedJson(' '.repeat(JSON_LIMITS.maxFrameBytes + 1))
      check(false, 'bounded JSON: oversized frame accepted')
    } catch (error) {
      check(
        error instanceof BoundedJsonError && error.code === 'NCP-LIMIT-001',
        `bounded JSON: oversized frame allocated or returned wrong error ${String(error)}`,
      )
    }
  } finally {
    globalThis.TextEncoder = originalTextEncoder
  }

  // SafetyGovernor capability negotiation: canonical channels win regardless of
  // declaration order, and enabled limits require vec3/width-3/SI-unit specs.
  const safety = {
    max_speed_mps: 1,
    max_tilt_rad: null,
    geofence_radius_m: 10,
    command_timeout_ms: 500,
  }
  const negotiated = SafetyGovernor.fromCapabilities({
    safety,
    sensor_channels: [
      { name: 'imu_accel', kind: 'vec3', unit: 'm/s2', size: null },
      { name: 'pose_position', kind: 'vec3', unit: 'm', size: 3n },
    ],
    command_channels: [
      { name: 'thrust', kind: 'scalar', unit: 'N', size: null },
      { name: 'velocity_setpoint', kind: 'vec3', unit: 'm/s', size: 3n },
    ],
  })
  check(negotiated.safetyOk(), 'governor capabilities: compatible canonical specs negotiate')
  const negotiatedOut = negotiated.govern(
    {
      kind: 'command_frame',
      ncp_version: NCP_VERSION,
      stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
      mode: 'active',
      authority: AUTHORITY,
      ttl_ms: 200,
      channels: { velocity_setpoint: { data: [2, 0, 0], unit: 'm/s' } },
    },
    {
      kind: 'sensor_frame',
      ncp_version: NCP_VERSION,
      stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
      channels: { pose_position: { data: [3, 0, 0], unit: 'm' } },
    },
    1,
    1,
  )
  check(
    negotiatedOut.mode === 'active' && negotiatedOut.channels.velocity_setpoint?.data[0] === 1,
    'governor capabilities: canonical velocity channel is clamped even when declared second',
  )

  for (const position of [
    { name: 'pose_position', kind: 'vec3', unit: null, size: 3n },
    { name: 'pose_position', kind: 'vec3', unit: 'cm', size: 3n },
    { name: 'pose_position', kind: 'scalar', unit: 'm', size: null },
    { name: 'pose_position', kind: 'vec3', unit: 'm', size: 2n },
  ]) {
    const governor = SafetyGovernor.fromCapabilities({
      safety: { ...safety, max_speed_mps: null },
      sensor_channels: [position],
      command_channels: [
        { name: 'velocity_setpoint', kind: 'vec3', unit: 'm/s', size: 3n },
      ],
    })
    check(!governor.safetyOk(), 'governor capabilities: incompatible position fails closed')
  }
  for (const velocity of [
    { name: 'velocity_setpoint', kind: 'vec3', unit: null, size: 3n },
    { name: 'velocity_setpoint', kind: 'vec3', unit: 'km/h', size: 3n },
    { name: 'velocity_setpoint', kind: 'scalar', unit: 'm/s', size: null },
    { name: 'velocity_setpoint', kind: 'vec3', unit: 'm/s', size: 4n },
  ]) {
    const governor = SafetyGovernor.fromCapabilities({
      safety: { ...safety, geofence_radius_m: null },
      sensor_channels: [],
      command_channels: [velocity],
    })
    check(!governor.safetyOk(), 'governor capabilities: incompatible velocity fails closed')
  }
  const reactiveOnlyFence = SafetyGovernor.fromCapabilities({
    safety: { ...safety, max_speed_mps: null },
    sensor_channels: [
      { name: 'pose_position', kind: 'vec3', unit: 'm', size: 3n },
    ],
    command_channels: [],
  })
  check(
    !reactiveOnlyFence.safetyOk(),
    'governor capabilities: geofence requires a projectable velocity contract',
  )
  const invalidConfig = new SafetyGovernor(
    { ...safety, geofence_radius_m: null, max_speed_mps: null },
    'pose_position',
    'velocity\nspoof',
    ['velocity\nspoof'],
    ['pose_position'],
  )
  const configHold = invalidConfig.govern(
    {
      kind: 'command_frame',
      ncp_version: NCP_VERSION,
      stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
      mode: 'active',
      authority: AUTHORITY,
      ttl_ms: 200,
      channels: { velocity_setpoint: { data: [1, 0, 0], unit: 'm/s' } },
    },
    {
      kind: 'sensor_frame',
      ncp_version: NCP_VERSION,
      stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
      channels: { pose_position: { data: [0, 0, 0], unit: 'm' } },
    },
    1,
    1,
  )
  check(configHold.mode === 'hold', 'governor config: invalid channel fails closed')
  try {
    assertWireFrame(configHold, 'command_frame')
  } catch (error) {
    check(false, `governor config: fail-closed HOLD must remain publishable (${error})`)
  }
  const sanitizedEstop = new SafetyGovernor({ command_timeout_ms: 500 }).govern(
    {
      kind: 'command_frame',
      mode: 'estop',
      stream: { epoch: EP, seq: 0 }, session: { generation: GEN }, session_id: 's',
      frame_id: 'world\u0085spoof',
      channels: { 'bad\u0085channel': { data: [1] } },
    },
    null,
    1,
    null,
  )
  check(
    sanitizedEstop.frame_id === 'world' && !('bad\u0085channel' in sanitizedEstop.channels),
    'governor fail-safe output strips C1 control characters',
  )

  // assertWireFrame: the data-plane ingress gate.
  const okFrame = { kind: 'command_frame', ncp_version: NCP_VERSION, stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's' }
  let threw = false
  try {
    assertWireFrame(okFrame, 'command_frame')
  } catch {
    threw = true
  }
  check(!threw, 'assertWireFrame: a stamped, versioned frame passes')
  const rejects = (frame, kind) => {
    try {
      assertWireFrame(frame, kind)
      return false
    } catch {
      return true
    }
  }
  check(
    rejects({ kind: 'command_frame', stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's' }, 'command_frame'),
    'assertWireFrame: version-less frame rejected',
  )
  check(
    rejects({ kind: 'command_frame', ncp_version: '0.5', stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's' }, 'command_frame'),
    'assertWireFrame: stale-wire frame rejected',
  )
  check(
    rejects({ kind: 'command_frame', ncp_version: NCP_VERSION, stream: { epoch: EP, seq: 0 }, session: { generation: GEN }, session_id: 's' }, 'command_frame'),
    'assertWireFrame: unstamped command rejected',
  )
  check(
    rejects({ kind: 'observation_frame', ncp_version: NCP_VERSION, stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's' }, 'command_frame'),
    'assertWireFrame: misrouted kind rejected',
  )
  check(
    !rejects(
      {
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: 1 },
        session: { generation: GEN },
        records: {},
        calibrated_posterior: false,
        is_simulation_output: true,
      },
      'observation_frame',
    ),
    'assertWireFrame: observation stream.seq 1 pull (no source) accepted',
  )
  check(
    rejects(
      {
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: -1 }, session: { generation: GEN }, session_id: 's',
        records: {},
        calibrated_posterior: false,
        is_simulation_output: true,
      },
      'observation_frame',
    ),
    'assertWireFrame: negative observation seq rejected',
  )
  check(
    rejects({ kind: 'command_frame', ncp_version: NCP_VERSION, stream: { epoch: EP, seq: 2 ** 53 }, session: { generation: GEN }, session_id: 's' }, 'command_frame'),
    'assertWireFrame: precision-unsafe seq rejected',
  )
  check(
    rejects(
      {
        kind: 'sensor_frame',
        ncp_version: NCP_VERSION,
        stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
        channels: { pose: { data: 'bad' } },
      },
      'sensor_frame',
    ),
    'assertWireFrame: malformed channel rejected',
  )
}

// NeuroSimClient must validate reply identity/boundary, not just cast `unknown`.
{
  const rejectsAsync = async (promise) => {
    try {
      await promise
      return false
    } catch {
      return true
    }
  }
  const rejectionMessage = async (promise) => {
    try {
      await promise
      return ''
    } catch (error) {
      return String(error)
    }
  }
  const opened = {
    kind: 'session_opened',
    ncp_version: NCP_VERSION,
    session_id: 's',
    ok: true,
    state_version: 0,
    backend: 'test',
    resolved: {},
    provenance: {
      network_ref: 'builtin:test',
      backend: 'test',
      calibrated_posterior: false,
      is_simulation_output: true,
      advisory_only: true,
    },
    error: null,
    contract_hash: NCP_CONTRACT_HASH,
    session: { generation: GEN },
    identity: {
      principal_id: 'body-principal',
      entity_id: 'simulator',
      role: 'body',
      plane: 'control',
    },
    security_profile: NEGOTIATION.security_profile,
    security_state_digest: NEGOTIATION.security_state_digest,
    gateway_permitted: false,
    gateway: null,
  }
  const invoke = async (reply, call) => {
    const client = new NeuroSimClient(
      async (request) =>
        request.kind === 'open_session'
          ? opened
          : typeof reply === 'function'
            ? reply(request)
            : reply,
      NEGOTIATION,
    )
    await client.open('s', { kind: 'builtin', ref: 'test' }, [], [])
    return call(client)
  }
  const receipt = (requestDigestValue) => ({
    operation_id: OP,
    request_digest: requestDigestValue,
    result_digest: 'c'.repeat(64),
    outcome: 'succeeded',
    state_version: 1,
    committed_at_utc_ms: 61_500,
    responder_principal_id: 'body-principal',
    responder_entity_id: 'simulator',
  })
  check(
    await rejectsAsync(
      invoke({
        kind: 'command_frame',
        ncp_version: NCP_VERSION,
        stream: { epoch: EP, seq: 1 }, session: { generation: GEN }, session_id: 's',
      }, (client) => client.close('s', MUTATION)),
    ),
    'client: wrong reply kind rejected',
  )
  check(
    await rejectsAsync(
      invoke({
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 'other',
        stream: { epoch: EP, seq: 1 },
        session: { generation: GEN },
        records: {},
        is_simulation_output: true,
        calibrated_posterior: false,
      }, (client) => client.step('s', MUTATION)),
    ),
    'client: cross-session reply rejected',
  )
  check(
    await rejectsAsync(
      invoke({
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: 1 },
        session: { generation: GEN },
        records: {},
        is_simulation_output: true,
        calibrated_posterior: true,
      }, (client) => client.step('s', MUTATION)),
    ),
    'client: dishonest scientific boundary rejected',
  )
  check(
    (
      await rejectionMessage(
        invoke({
          kind: 'error',
          ncp_version: NCP_VERSION,
          code: 'NCP-WIRE-001',
          error: 'misrouted',
          session_id: 's',
          session: { generation: GEN },
          request_kind: 'close_session',
        }, (client) => client.step('s', MUTATION)),
      )
    ).includes('request_kind mismatch'),
    'client: a typed error is bound to the originating request kind',
  )
  check(
    (
      await rejectionMessage(
        invoke({
          kind: 'error',
          ncp_version: NCP_VERSION,
          code: 'NCP-WIRE-001',
          error: 'cross-session',
          session_id: 'other',
          session: { generation: GEN },
          request_kind: 'step_request',
        }, (client) => client.step('s', MUTATION)),
      )
    ).includes('session mismatch'),
    'client: a typed error is bound to the originating session',
  )
  check(
    !await rejectsAsync(
      invoke((request) => ({
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: 1 },
        session: { generation: GEN },
        records: {},
        is_simulation_output: true,
        calibrated_posterior: false,
        receipt: receipt(request.operation.request_digest),
      }), (client) => client.step('s', MUTATION)),
    ),
    'client: a correlated responder receipt completes a mutation',
  )
  check(
    await rejectsAsync(
      invoke((request) => ({
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: 1 },
        session: { generation: '30000000-0000-4000-8000-000000000099' },
        records: {},
        is_simulation_output: true,
        calibrated_posterior: false,
        receipt: receipt(request.operation.request_digest),
      }), (client) => client.step('s', MUTATION)),
    ),
    'client: a responder receipt on a stale session generation is rejected',
  )
  check(
    await rejectsAsync(
      invoke((request) => ({
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: 1 },
        session: { generation: GEN },
        records: {},
        is_simulation_output: true,
        calibrated_posterior: false,
        receipt: {
          ...receipt(request.operation.request_digest),
          operation_id: '30000000-0000-4000-8000-000000000099',
        },
      }), (client) => client.step('s', MUTATION)),
    ),
    'client: a responder receipt for another operation is rejected',
  )
  check(
    await rejectsAsync(
      invoke((request) => ({
        kind: 'observation_frame',
        ncp_version: NCP_VERSION,
        session_id: 's',
        stream: { epoch: EP, seq: 1 },
        session: { generation: GEN },
        records: {},
        is_simulation_output: true,
        calibrated_posterior: false,
        receipt: { ...receipt(request.operation.request_digest), request_digest: 'd'.repeat(64) },
      }), (client) => client.step('s', MUTATION)),
    ),
    'client: a responder receipt with the wrong request digest is rejected',
  )
}

const requiredTypeScriptIds = new Set(
  manifest.vectors
    .filter(
      (vector) =>
        vector.required === true &&
        vector.stability === 'stable-1.0' &&
        vector.applicability?.implementations?.includes('typescript'),
    )
    .map((vector) => vector.id),
)
for (const id of requiredTypeScriptIds) {
  check(executedIds.has(id), `manifest: required TypeScript vector ${id} was skipped`)
}
for (const id of executedIds) {
  check(requiredTypeScriptIds.has(id), `manifest: unrecognized extra TypeScript vector ${id}`)
}

if (failures.length) {
  console.error(`FAIL ncp-ts behavioral conformance: ${failures.length} vector(s) diverged:`)
  for (const f of failures) console.error(`  - ${f}`)
  process.exit(1)
}
console.log(
  `OK ncp-ts behavioral conformance: ${covered} vectors match (check_version + ` +
    `contract_status + ${boundaryCovered} scientific-boundary + ${dataPlaneCovered} data-plane ` +
    `validate + govern + action_buffer), ${goldenCovered} canonical JSON fixtures pass, ` +
    `plus full-message validation and safety/client self-checks.`,
)
