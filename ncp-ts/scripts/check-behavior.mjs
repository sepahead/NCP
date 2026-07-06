// Behavioral conformance — the TypeScript peer vs the shared decision corpus
// (conformance/behavior/vectors.json), the same corpus the Rust reference is pinned
// to (ncp-core/tests/behavior_conformance.rs) and the Python/C++ peers replay.
//
// Since wire 0.6, ncp-ts ships the plant-side safety port (SafetyGovernor /
// CommandWatchdog / ActionBuffer in `safety.ts`), so this runner replays the FULL
// `govern` corpus through the TS governor in addition to the handshake/boundary
// functions (checkVersion = the hard version gate, contractStatus = the advisory
// contract check, assertScientificBoundary = the boundary discriminators). The
// required-field half of `validate` remains owned by the full peers; the TS
// data-plane ingress gate is `assertWireFrame`, exercised in the safety
// self-checks at the end of this runner.
//
// Fail-loud coverage: every corpus function must be either implemented here or in an
// explicit out-of-scope allowlist; a corpus function in NEITHER set is a hard error,
// so a future corpus addition can never silently shrink TS coverage. Reads the single
// repo-root corpus (NOT a vendored copy) and asserts its header pins match ncp-ts's.
//
// Run after `npm run build` (imports the published dist surface):
//   node ncp-ts/scripts/check-behavior.mjs

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
// Import the concrete dist/*.js (not the index barrel): tsconfig uses
// `moduleResolution: Bundler`, so the emitted barrel re-exports are extensionless
// and node's native ESM loader cannot resolve them. client.js/safety.js load
// under plain node (their ./generated imports are type-only, erased at compile).
import {
  NCP_VERSION,
  NCP_CONTRACT_HASH,
  checkVersion,
  NcpVersionError,
  contractStatus,
  assertScientificBoundary,
  NcpScientificBoundaryError,
} from '../dist/client.js'
import {
  ActionBuffer,
  CommandWatchdog,
  SafetyGovernor,
  assertWireFrame,
  maxHorizonLen,
} from '../dist/safety.js'

const here = dirname(fileURLToPath(import.meta.url)) // ncp-ts/scripts
const corpusPath = join(here, '..', '..', 'conformance', 'behavior', 'vectors.json')
const corpus = JSON.parse(readFileSync(corpusPath, 'utf8'))

const failures = []
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

// Functions ncp-ts implements vs deliberately out-of-scope for the thin client.
// `validate` is implemented for the scientific-boundary subset only (the
// required-field half is owned by the full peers). `govern` is fully replayed
// through the TS SafetyGovernor since wire 0.6.
const IMPLEMENTED = new Set(['check_version', 'contract_status', 'validate', 'govern'])
const OUT_OF_SCOPE = new Set([])
for (const fn of Object.keys(corpus.cases)) {
  check(
    IMPLEMENTED.has(fn) || OUT_OF_SCOPE.has(fn),
    `corpus function ${fn} is neither implemented in ncp-ts nor in the out-of-scope ` +
      `allowlist — update ncp-ts/scripts/check-behavior.mjs (do not let it silently drop)`,
  )
}

let covered = 0

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
  covered++
}

// validate — the thin client enforces the scientific-BOUNDARY discriminators via
// assertScientificBoundary. Cover the boundary-bearing vectors (a violation must
// throw); the required-field-only vectors are out of the thin client's scope.
const hasBoundary = (m) => {
  const carrier = m.kind === 'session_opened' && m.provenance ? m.provenance : m
  return 'is_simulation_output' in carrier || 'calibrated_posterior' in carrier
}
let boundaryCovered = 0
for (const c of corpus.cases.validate) {
  const { name, input, expect } = c
  if (!hasBoundary(input.message)) continue // required-field-only — out of scope
  let threw = false
  try {
    assertScientificBoundary(input.message)
  } catch (e) {
    threw = true
    check(e instanceof NcpScientificBoundaryError, `validate[${name}]: threw non-boundary ${e}`)
  }
  check(threw === !expect.valid, `validate[${name}]: boundary throw=${threw} vs expected valid=${expect.valid}`)
  boundaryCovered++
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
  covered++
}

// ── Safety self-checks: the wire-0.6 seq/ttl/latch semantics of the TS port ──
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
  // Restart re-anchor: strictly-lower seq only, only after expiry; equal never.
  const wd2 = new CommandWatchdog()
  wd2.onCommand(1.0, 200, 1000)
  wd2.onCommand(1.05, 200, 1)
  check(wd2.shouldHold(1.35), 'watchdog: low seq on a LIVE stream must not refresh')
  wd2.onCommand(1.5, 200, 1) // expired -> re-anchor
  check(!wd2.shouldHold(1.6), 'watchdog: post-expiry restart re-anchors')
  wd2.onCommand(2.0, 200, 1) // equal seq, expired -> NEVER re-anchors
  check(wd2.shouldHold(2.05), 'watchdog: equal-seq replay never re-anchors')

  // ActionBuffer: unstamped rejected, ESTOP latches regardless, horizon replay.
  const ab = new ActionBuffer()
  ab.onCommand(1.0, { mode: 'active', seq: 0, channels: { velocity_setpoint: { data: [9] } } })
  check(ab.shouldHold(1.0), 'buffer: unstamped Active never actuates')
  ab.onCommand(1.0, {
    mode: 'active',
    seq: 1,
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
  ab.onCommand(2.0, { mode: 'estop', seq: 0, channels: {} }) // unstamped ESTOP still latches
  check(ab.isEstopped(), 'buffer: an unstamped ESTOP still latches')
  ab.onCommand(2.1, { mode: 'active', seq: 2, ttl_ms: 200, channels: { velocity_setpoint: { data: [1] } } })
  check(ab.shouldHold(2.1), 'buffer: latched ESTOP suppresses later Active')
  ab.reset()
  ab.onCommand(2.2, { mode: 'active', seq: 3, ttl_ms: 200, channels: { velocity_setpoint: { data: [1] } } })
  check(!ab.shouldHold(2.2), 'buffer: reset restores actuation')

  // maxHorizonLen bounds.
  check(maxHorizonLen(200, 50) === 4, 'maxHorizonLen: exact floor')
  check(maxHorizonLen(Infinity, 50) === 0, 'maxHorizonLen: non-finite ttl -> 0')
  check(maxHorizonLen(200, 0) === 0, 'maxHorizonLen: dt<=0 -> 0')

  // assertWireFrame: the data-plane ingress gate.
  const okFrame = { kind: 'command_frame', ncp_version: NCP_VERSION, seq: 1 }
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
    rejects({ kind: 'command_frame', seq: 1 }, 'command_frame'),
    'assertWireFrame: version-less frame rejected',
  )
  check(
    rejects({ kind: 'command_frame', ncp_version: '0.5', seq: 1 }, 'command_frame'),
    'assertWireFrame: stale-wire frame rejected',
  )
  check(
    rejects({ kind: 'command_frame', ncp_version: NCP_VERSION, seq: 0 }, 'command_frame'),
    'assertWireFrame: unstamped command rejected',
  )
  check(
    rejects({ kind: 'observation_frame', ncp_version: NCP_VERSION, seq: 1 }, 'command_frame'),
    'assertWireFrame: misrouted kind rejected',
  )
  check(
    !rejects({ kind: 'observation_frame', ncp_version: NCP_VERSION, seq: 0 }, 'observation_frame'),
    'assertWireFrame: observation seq 0 (pull path) accepted',
  )
  check(
    rejects({ kind: 'observation_frame', ncp_version: NCP_VERSION, seq: -1 }, 'observation_frame'),
    'assertWireFrame: negative observation seq rejected',
  )
}

const outOfScope = corpus.cases.validate.length - boundaryCovered
if (failures.length) {
  console.error(`FAIL ncp-ts behavioral conformance: ${failures.length} vector(s) diverged:`)
  for (const f of failures) console.error(`  - ${f}`)
  process.exit(1)
}
console.log(
  `OK ncp-ts behavioral conformance: ${covered} vectors match (check_version + ` +
    `contract_status + scientific-boundary + govern) + safety self-checks. ` +
    `${outOfScope} required-field validate vectors out-of-scope for the thin client ` +
    `— gated by ncp-core/ncp-python/ncp-cpp.`,
)
