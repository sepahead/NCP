/**
 * Plant-side safety + resilience primitives — the TypeScript port of
 * `ncp-core/src/safety.rs` and `ncp-core/src/resilience.rs`, behaviour-pinned to
 * the same shared corpus (`conformance/behavior/vectors.json`, replayed by
 * `scripts/check-behavior.mjs`) as the Rust / Python / C++ peers.
 *
 * Ships so a TS plant (e.g. a browser/Tauri dev bridge) enforces the SAME
 * fail-safe semantics as every other peer instead of hand-rolling them:
 *
 * - {@link CommandWatchdog} — the `ttl_ms` deadline backstop with wire-0.6 seq
 *   discipline (`seq >= 1`, strictly increasing; duplicates never refresh; a
 *   strictly-lower seq re-anchors a restarted stream only after expiry).
 * - {@link ActionBuffer} — packetized-predictive-control replay: latest command
 *   + horizon, ttl-bounded, latched ESTOP, `active`-mode allowlist.
 * - {@link SafetyGovernor} — HOLD on stale sensor, latched ESTOP on geofence
 *   breach / inbound ESTOP / link collapse, magnitude speed clamp (tick 0 and
 *   every horizon step), config fail-closed on unenforceable limits.
 * - {@link maxHorizonLen} — bound a horizon to its deadline.
 * - {@link assertWireFrame} — the wire-0.6 data-plane ingress gate (compatible
 *   `ncp_version`, stamped `seq`), mirroring `ncp_core::decode_validated`.
 *
 * All numeric behaviour is IEEE-754 double math, identical to the Rust `f64`
 * reference. `seq` is a JSON-wire `number` here (see `Wire<T>` in `client.ts`).
 */

import type { Mode, SafetyLimits, Capabilities } from './generated/index.js'
// Extension-full specifier so the EMITTED dist/safety.js resolves under plain
// node ESM (the behavior runner imports dist/*.js directly; see
// scripts/check-behavior.mjs) — tsc still type-resolves this to ./client.ts.
import {
  assertNcpMessage,
  checkVersion,
  hasWireControlCharacters,
  MAX_HORIZON_STEPS,
  NCP_VERSION,
  NcpVersionError,
} from './client.js'

/** JSON-wire channel map: `{ name: { data, unit } }`. */
export interface WireChannels {
  [name: string]: { data: number[]; unit?: string | null }
}

/** Structural (JSON-wire) view of a `CommandFrame` — the fields the safety layer
 *  reads. Accepts a full `Wire<CommandFrame>`; optional members default like the
 *  Rust wire defaults. */
/** Wire 0.8: a canonical lowercase UUIDv4 (`stream.epoch` / `session.generation`). */
const UUID_V4_SAFETY = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

/** Structural view of a `StreamPosition` — one frame's stream identity + position. */
export interface StreamPositionLike {
  epoch?: string
  seq?: number
}
/** Structural view of a `SessionRef` — one live session incarnation. */
export interface SessionRefLike {
  generation?: string
}

export interface CommandLike {
  kind?: string
  ncp_version?: string
  stream?: StreamPositionLike
  source?: StreamPositionLike | null
  source_t?: number
  session?: SessionRefLike
  session_id?: string
  t?: number
  frame_id?: string
  mode: Mode
  ttl_ms?: number
  channels: WireChannels
  horizon?: WireChannels[]
  horizon_dt_ms?: number | null
}

/** Structural (JSON-wire) view of a `SensorFrame` for the governor. */
export interface SensorLike {
  kind?: string
  ncp_version?: string
  stream?: StreamPositionLike
  session?: SessionRefLike
  session_id?: string
  t?: number
  frame_id?: string
  channels: WireChannels
}

/** Upper bound on an enforced command ttl (ms) — mirrors `safety.rs::MAX_TTL_MS`:
 *  the wire field is unbounded, but the plant-side deadline must stay finite. */
export const MAX_TTL_MS = 60_000
/** How many consecutive `command_timeout_ms` deadlines of TOTAL sensor silence
 *  escalate the non-latching staleness HOLD to a latched ESTOP (mirrors
 *  `safety.rs::LINK_LOSS_ESTOP_FACTOR`). */
export const LINK_LOSS_ESTOP_FACTOR = 20
const POSITION_CHANNEL = 'pose_position'
const VELOCITY_CHANNEL = 'velocity_setpoint'
const POSITION_UNIT = 'm'
const VELOCITY_UNIT = 'm/s'
const SAFETY_VECTOR_WIDTH = 3

type CapabilityChannel = Capabilities['sensor_channels'][number]

function compatibleSafetyVec3(
  spec: CapabilityChannel | undefined,
  expectedUnit: string,
): boolean {
  if (spec === undefined || spec.kind !== 'vec3' || spec.unit !== expectedUnit) return false
  const size: unknown = spec.size
  return size == null || size === SAFETY_VECTOR_WIDTH || size === BigInt(SAFETY_VECTOR_WIDTH)
}

/**
 * Plant-side deadline backstop enforcing `CommandFrame.ttl_ms` — mirrors
 * `ncp_core::CommandWatchdog` exactly, including the wire-0.6 seq discipline:
 * `seq < 1` (unstamped) NEVER refreshes liveness; a duplicate never refreshes; a
 * strictly-lower `seq` re-anchors a restarted stream only once the stream is
 * already expired (the plant is safely holding).
 */
export class CommandWatchdog {
  private lastRecvS: number | null = null
  private ttlS = 0
  private lastSeq = 0
  private clockHighWaterS: number | null = null
  private clockFaulted = false

  private observeClock(nowS: number): boolean {
    if (!Number.isFinite(nowS)) {
      this.clockFaulted = true
      return false
    }
    if (this.clockHighWaterS !== null && nowS < this.clockHighWaterS) {
      this.clockFaulted = true
      return false
    }
    this.clockHighWaterS = nowS
    return true
  }

  /** Re-anchor the seq discipline for a NEW stream epoch: clear the high-water so
   *  the next command (a restarted publisher counts from 1) is accepted as fresh.
   *  An epoch-aware receiver (`ActionBuffer`) calls this only after it authorizes an
   *  epoch transition; the ttl deadline is refreshed by the `onCommand` that follows. */
  reanchor(): void {
    this.lastSeq = 0
  }

  /** Record an accepted command at local time `nowS` with its `ttl_ms` and `seq`. */
  onCommand(nowS: number, ttlMs: number, seq: number): void {
    if (!this.observeClock(nowS)) return
    if (!Number.isSafeInteger(seq) || seq < 1) return
    const recoveringClock = this.clockFaulted
    if (
      seq <= this.lastSeq &&
      (seq === this.lastSeq || (!recoveringClock && !this.shouldHold(nowS)))
    ) {
      return // duplicate (always), or stale/reordered while the stream is LIVE
    }
    this.lastSeq = seq
    this.lastRecvS = nowS
    // Bound the enforced ttl: non-finite -> 0 (immediately stale); clamp to the
    // finite ceiling so one command cannot keep the plant live indefinitely.
    this.ttlS = Number.isFinite(ttlMs) ? Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / 1000 : 0
    this.clockFaulted = false
  }

  /** True if the plant must fail safe to HOLD (no command, expired, bad clock). */
  shouldHold(nowS: number): boolean {
    if (!this.observeClock(nowS) || this.clockFaulted) return true
    const t = this.lastRecvS
    if (t === null) return true
    return (
      !Number.isFinite(nowS) ||
      !Number.isFinite(t) ||
      this.ttlS <= 0 ||
      nowS < t || // backward clock step: fail closed
      nowS - t >= this.ttlS
    )
  }
}

/** Cap a horizon length to its deadline (`N <= ttl_ms / horizon_dt_ms`); a
 *  non-finite ttl/dt (or dt <= 0) returns 0 — mirrors `resilience.rs`. */
export function maxHorizonLen(ttlMs: number, horizonDtMs: number): number {
  if (!Number.isFinite(ttlMs) || !Number.isFinite(horizonDtMs) || horizonDtMs <= 0) return 0
  const steps = Math.floor(Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / horizonDtMs)
  if (!Number.isFinite(steps)) return 0
  return Math.min(Math.max(steps, 0), MAX_HORIZON_STEPS)
}

/**
 * Plant-side packetized-predictive-control buffer — mirrors
 * `ncp_core::ActionBuffer`: holds the latest command + horizon, replays through
 * dropouts, fails safe once expired or drained; every non-Active mode clears
 * buffered actuation before replay checks, and ESTOP latches regardless of
 * ordering or stamping (a fail-safe is never dropped); wire-0.6 seq discipline
 * as in {@link CommandWatchdog}.
 */
export class ActionBuffer {
  private latest: CommandLike | null = null
  private recvS = 0
  private watchdog = new CommandWatchdog()
  private estop = false
  private lastSeq = 0
  // Wire 0.8 (§7): acceptance keys on (epoch, seq). A FOREIGN epoch must not
  // advance the LIVE stream (no hijack via a fresh high seq under a new random
  // epoch); a RETIRED epoch never revives. Bounded tombstone ring.
  private activeEpoch: string | null = null
  private retiredEpochs: string[] = []

  private static readonly RETIRED_EPOCH_CAP = 256

  private retireEpoch(epoch: string): void {
    if (this.retiredEpochs.includes(epoch)) return
    if (this.retiredEpochs.length >= ActionBuffer.RETIRED_EPOCH_CAP) this.retiredEpochs.shift()
    this.retiredEpochs.push(epoch)
  }

  onCommand(nowS: number, command: CommandLike): void {
    // Fail-safe priority: HOLD/INIT/future non-actuating modes clear buffered
    // actuation even when malformed, stale, or duplicate. Dropping one would
    // leave the previous Active horizon running until ttl.
    if (command.mode !== 'active') this.latest = null
    if (command.mode === 'estop') {
      this.estop = true // latch even if the frame is stale/out-of-order/unstamped
    }
    try {
      assertWireFrame(command as unknown as Record<string, unknown>, 'command_frame')
    } catch {
      return // ESTOP already latched; every other invalid envelope is ignored
    }
    const seq = command.stream?.seq ?? 0
    if (!Number.isSafeInteger(seq) || seq < 1) return
    // Wire 0.8 (§7): epoch-keyed acceptance. A foreign epoch may adopt the stream
    // only as a restart, once the prior stream has EXPIRED; a retired epoch never
    // revives; same-epoch frames fall through to the seq discipline below.
    const epoch = command.stream?.epoch ?? ''
    if (this.activeEpoch === null) {
      this.activeEpoch = epoch
    } else if (this.activeEpoch !== epoch) {
      if (this.retiredEpochs.includes(epoch) || !this.watchdog.shouldHold(nowS)) {
        return // retired epoch, or a foreign epoch while the stream is LIVE
      }
      this.retireEpoch(this.activeEpoch)
      this.activeEpoch = epoch
      this.lastSeq = 0 // re-anchor the seq discipline for the new epoch
      this.watchdog.reanchor()
    }
    if (seq <= this.lastSeq && (seq === this.lastSeq || !this.watchdog.shouldHold(nowS))) {
      return // duplicate (always), or stale/reordered while LIVE (ESTOP latched above)
    }
    this.lastSeq = seq
    if (command.mode !== 'active') return
    this.watchdog.onCommand(nowS, command.ttl_ms ?? 200, seq)
    this.recvS = nowS
    // Rust takes ownership of the accepted frame. Clone here so a JavaScript
    // caller cannot mutate channels/mode/horizon after validation and change
    // live actuation without a new sequence number or watchdog update.
    this.latest = structuredClone(command)
  }

  /** Clear a latched ESTOP and discard all pre-ESTOP command state. A fresh
   * validated Active command is required before actuation resumes. */
  reset(): void {
    this.estop = false
    this.latest = null
    this.recvS = 0
    this.watchdog = new CommandWatchdog()
    this.lastSeq = 0
    // A supervisor reset is a fresh start: forget the active epoch + tombstones.
    this.activeEpoch = null
    this.retiredEpochs = []
  }

  isEstopped(): boolean {
    return this.estop
  }

  /** The setpoint channels to apply at `nowS`, or `null` to fail safe (HOLD). */
  active(nowS: number): WireChannels | null {
    if (this.estop) return null
    if (this.watchdog.shouldHold(nowS)) return null
    const cmd = this.latest
    if (cmd === null) return null
    // ALLOWLIST, not denylist: only `active` actuates (init/hold/estop and any
    // future mode fail safe to HOLD).
    if (cmd.mode !== 'active') return null
    const dt = cmd.horizon_dt_ms ?? 0
    const horizon = cmd.horizon ?? []
    if (!(dt > 0) || horizon.length === 0) return structuredClone(cmd.channels)
    const tick = Math.floor(((nowS - this.recvS) * 1000) / dt)
    if (tick <= 0) return structuredClone(cmd.channels)
    const step = horizon[tick - 1]
    return step === undefined ? null : structuredClone(step)
  }

  shouldHold(nowS: number): boolean {
    return this.active(nowS) === null
  }
}

/**
 * The action-plane safety governor — mirrors `ncp_core::SafetyGovernor` (HOLD on
 * stale/absent sensor, latched ESTOP on geofence breach / inbound ESTOP / total
 * silence, magnitude speed clamp on tick 0 and every horizon step, geofence
 * horizon look-ahead, config fail-closed on unenforceable/non-finite limits).
 * Behaviour is pinned by the shared `govern` corpus vectors.
 */
export class SafetyGovernor {
  private estop = false
  private configFailClosed: boolean

  constructor(
    public limits: Pick<SafetyLimits, 'command_timeout_ms'> & Partial<SafetyLimits>,
    private readonly positionChannel = POSITION_CHANNEL,
    private readonly velocityChannel = VELOCITY_CHANNEL,
    private commandChannels: string[] = [VELOCITY_CHANNEL],
    sensorChannels: string[] = [],
    private readonly positionContractValid = true,
    private readonly velocityContractValid = true,
  ) {
    if (this.commandChannels.length === 0) this.commandChannels = [this.velocityChannel]
    const geofenceBad =
      (this.limits.geofence_radius_m ?? 0) > 0 &&
      sensorChannels.length > 0 &&
      !sensorChannels.includes(this.positionChannel)
    const speedBad =
      ((this.limits.max_speed_mps ?? 0) > 0 ||
        (this.limits.geofence_radius_m ?? 0) > 0) &&
      !this.commandChannels.includes(this.velocityChannel)
    const badLimit = (v: number | null | undefined) =>
      v != null && (!Number.isFinite(v) || v < 0)
    const timeoutBad =
      !Number.isFinite(this.limits.command_timeout_ms) || this.limits.command_timeout_ms <= 0
    const validChannelName = (name: string) =>
      name.length > 0 && !hasWireControlCharacters(name)
    const channelConfigBad =
      !validChannelName(this.positionChannel) ||
      !validChannelName(this.velocityChannel) ||
      this.commandChannels.some((name) => !validChannelName(name)) ||
      sensorChannels.some((name) => !validChannelName(name)) ||
      new Set(this.commandChannels).size !== this.commandChannels.length ||
      new Set(sensorChannels).size !== sensorChannels.length
    this.configFailClosed =
      geofenceBad ||
      speedBad ||
      timeoutBad ||
      channelConfigBad ||
      badLimit(this.limits.max_speed_mps) ||
      badLimit(this.limits.max_tilt_rad) ||
      badLimit(this.limits.geofence_radius_m) ||
      ((this.limits.geofence_radius_m ?? 0) > 0 && !this.positionContractValid) ||
      (((this.limits.max_speed_mps ?? 0) > 0 ||
        (this.limits.geofence_radius_m ?? 0) > 0) &&
        !this.velocityContractValid)
  }

  /** Resolve explicit canonical safety channels from negotiated `Capabilities`.
   *  Enabled limits require width-3 `vec3` specs in canonical SI units; declaration
   *  order never selects a safety input. Mirrors Rust `from_capabilities`. */
  static fromCapabilities(caps: {
    command_channels: Capabilities['command_channels']
    sensor_channels: Capabilities['sensor_channels']
    safety: SafetyLimits
  }): SafetyGovernor {
    const commandChannels = caps.command_channels.map((c) => c.name)
    const sensorChannels = caps.sensor_channels.map((c) => c.name)
    const positionContractValid = compatibleSafetyVec3(
      caps.sensor_channels.find((channel) => channel.name === POSITION_CHANNEL),
      POSITION_UNIT,
    )
    const velocityContractValid = compatibleSafetyVec3(
      caps.command_channels.find((channel) => channel.name === VELOCITY_CHANNEL),
      VELOCITY_UNIT,
    )
    return new SafetyGovernor(
      caps.safety,
      POSITION_CHANNEL,
      VELOCITY_CHANNEL,
      commandChannels,
      sensorChannels,
      positionContractValid,
      velocityContractValid,
    )
  }

  /** Clear a latched ESTOP (supervisor authority; config fail-closed is NOT cleared). */
  reset(): void {
    this.estop = false
  }

  isEstopped(): boolean {
    return this.estop
  }

  /** Latch ESTOP when the link monitor reports a sustained loss burst (a jam). */
  noteLink(burst: boolean): void {
    if (burst) this.estop = true
  }

  safetyOk(): boolean {
    return !this.estop && !this.configFailClosed
  }

  private zeroedChannels(command: CommandLike): WireChannels {
    const out: WireChannels = {}
    const rawChannels: unknown = (command as unknown as { channels?: unknown })?.channels
    const entries =
      typeof rawChannels === 'object' && rawChannels !== null && !Array.isArray(rawChannels)
        ? Object.entries(rawChannels)
        : []
    for (const [name, raw] of entries) {
      if (name.length === 0 || hasWireControlCharacters(name)) continue
      const cv =
        typeof raw === 'object' && raw !== null && !Array.isArray(raw)
          ? (raw as { data?: unknown; unit?: unknown })
          : {}
      const data = Array.isArray(cv.data) ? cv.data : []
      const unit = typeof cv.unit === 'string' || cv.unit === null ? cv.unit : null
      out[name] =
        name === this.velocityChannel
          ? { data: new Array(SAFETY_VECTOR_WIDTH).fill(0), unit: VELOCITY_UNIT }
          : { data: new Array(Math.max(data.length, 1)).fill(0), unit }
    }
    for (const name of this.commandChannels) {
      if (name.length === 0 || hasWireControlCharacters(name)) continue
      if (!(name in out)) {
        out[name] =
          name === this.velocityChannel
            ? { data: [0, 0, 0], unit: VELOCITY_UNIT }
            : { data: [0], unit: null }
      }
    }
    return out
  }

  private safeFrame(command: CommandLike, mode: Mode): CommandLike {
    const raw = command as unknown as {
      t?: unknown
      frame_id?: unknown
    }
    const stream = command.stream ?? { epoch: '', seq: 1 }
    const t = typeof raw.t === 'number' && Number.isFinite(raw.t) ? raw.t : 0
    const frameId =
      typeof raw.frame_id === 'string' &&
      raw.frame_id.length > 0 &&
      !hasWireControlCharacters(raw.frame_id)
        ? raw.frame_id
        : 'world'
    return {
      kind: 'command_frame',
      ncp_version: NCP_VERSION,
      stream,
      source: command.source,
      source_t: command.source_t,
      session: command.session,
      session_id: command.session_id,
      t,
      frame_id: frameId,
      mode,
      ttl_ms: 200,
      channels: this.zeroedChannels(command),
      horizon: [],
      horizon_dt_ms: null,
    }
  }

  /**
   * Apply safety to `command` against the latest `sensor`. `nowS`/`lastSensorS`
   * are wall-clock seconds (the plant's own clock). Returns a fresh frame; ESTOP
   * latches (call {@link reset} to clear).
   */
  govern(
    command: CommandLike,
    sensor: SensorLike | null,
    nowS: number,
    lastSensorS: number | null,
  ): CommandLike {
    // Latched ESTOP dominates everything until a supervisor reset.
    if (this.estop) return this.safeFrame(command, 'estop')
    // An INBOUND ESTOP-mode command is itself a fail-safe: LATCH and propagate
    // (zeroed ESTOP out), never downgrade to a non-latching HOLD.
    if (command.mode === 'estop') {
      this.estop = true
      return this.safeFrame(command, 'estop')
    }
    if (
      ((this.limits.geofence_radius_m ?? 0) > 0 && !this.positionContractValid) ||
      (((this.limits.max_speed_mps ?? 0) > 0 ||
        (this.limits.geofence_radius_m ?? 0) > 0) &&
        !this.velocityContractValid)
    ) {
      this.configFailClosed = true
    }
    // A configured-but-nonsensical geofence/speed limit fails CLOSED.
    const badLimit = (v: number | null | undefined) =>
      v != null && (!Number.isFinite(v) || v < 0)
    if (
      badLimit(this.limits.geofence_radius_m) ||
      badLimit(this.limits.max_speed_mps) ||
      badLimit(this.limits.max_tilt_rad)
    ) {
      this.configFailClosed = true
    }
    const timeoutMs = this.limits.command_timeout_ms
    if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
      this.configFailClosed = true
    }
    if (this.configFailClosed) return this.safeFrame(command, 'hold')

    // A timestamp alone is not proof of perception liveness. Validate the
    // sensor independently so a malformed/absent frame enters the same stale
    // path (including total-silence escalation) as no frame at all.
    let validatedSensor = sensor
    try {
      if (validatedSensor !== null) {
        assertWireFrame(validatedSensor as unknown as Record<string, unknown>, 'sensor_frame')
      }
    } catch {
      validatedSensor = null
    }

    // Staleness backstop (default-deny; NaN/backward clocks fail closed).
    // A huge-but-finite timeout must not disable freshness indefinitely. Preserve
    // it on the wire, but cap local enforcement like the Rust reference.
    const timeoutS = Math.min(timeoutMs, MAX_TTL_MS) / 1000
    const stale =
      validatedSensor === null ||
      lastSensorS == null ||
      !Number.isFinite(nowS) ||
      !Number.isFinite(lastSensorS) ||
      nowS < lastSensorS ||
      nowS - lastSensorS >= timeoutS
    if (stale) {
      // Sustained TOTAL silence escalates HOLD -> latched ESTOP.
      if (
        lastSensorS != null &&
        Number.isFinite(nowS) &&
        Number.isFinite(lastSensorS) &&
        nowS >= lastSensorS
      ) {
        const deadlineS = Math.min(timeoutS * LINK_LOSS_ESTOP_FACTOR, MAX_TTL_MS / 1000)
        if (nowS - lastSensorS >= deadlineS) {
          this.estop = true
          return this.safeFrame(command, 'estop')
        }
      }
      return this.safeFrame(command, 'hold')
    }
    // Kept as an explicit fail-closed narrowing guard even though `stale`
    // already includes this condition.
    if (validatedSensor === null) return this.safeFrame(command, 'hold')

    // Geofence: a configured positive radius MUST be evaluable (fail closed).
    const radius = this.limits.geofence_radius_m
    if (radius != null && radius > 0) {
      const pos = validatedSensor.channels?.[this.positionChannel]
      if (pos === undefined) return this.safeFrame(command, 'hold')
      if (!this.validSafetyVector(pos, POSITION_UNIT)) return this.safeFrame(command, 'hold')
      const r = Math.sqrt(pos.data.reduce((s, c) => s + c * c, 0))
      if (!Number.isFinite(r) || r > radius) {
        this.estop = true
        return this.safeFrame(command, 'estop')
      }
    }

    // Freshness, total-silence escalation, and the CURRENT geofence state run
    // before command validation/mode checks. A HOLD or malformed non-ESTOP
    // command must never hide a collapsed link or an already-breached boundary.
    try {
      assertWireFrame(command as unknown as Record<string, unknown>, 'command_frame')
    } catch {
      return this.safeFrame(command, 'hold')
    }
    // Only `active` may actuate (defense-in-depth with ActionBuffer's allowlist).
    if (command.mode !== 'active') return this.safeFrame(command, 'hold')

    const out: CommandLike = structuredClone(command)
    out.horizon = out.horizon ?? []
    const maxSpeed = this.limits.max_speed_mps
    if (maxSpeed != null && maxSpeed > 0) {
      if (!this.clampVelocity(out.channels, maxSpeed)) return this.safeFrame(command, 'hold')
      // Clamp every predictive horizon step too; truncate at the first
      // unclampable step so replay HOLDs rather than emitting unbounded output.
      let safeLen = out.horizon.length
      for (let i = 0; i < out.horizon.length; i++) {
        if (!this.clampVelocity(out.horizon[i]!, maxSpeed)) {
          // An empty horizon means legacy "replay tick 0 until ttl", not
          // "drain after tick 0". Reject instead of truncating index 0 to an
          // actively replayed command.
          if (i === 0) return this.safeFrame(command, 'hold')
          safeLen = i
          break
        }
      }
      out.horizon.length = safeLen
    }

    // Project the exact canonical velocity trajectory over every interval that
    // ActionBuffer can apply before ttl. Current in-bounds position alone is not
    // enough: the legacy no-horizon form replays tick 0 for the entire ttl.
    if (radius != null && radius > 0) {
      const pos = validatedSensor.channels?.[this.positionChannel]
      const commandFrame = command.frame_id ?? 'world'
      const sensorFrame = validatedSensor.frame_id ?? 'world'
      if (
        commandFrame !== sensorFrame ||
        pos === undefined ||
        !this.enforceGeofenceTrajectory(out, pos, radius)
      ) {
        return this.safeFrame(command, 'hold')
      }
    }
    return out
  }

  private enforceGeofenceTrajectory(
    command: CommandLike,
    position: { data: number[]; unit?: string | null },
    radius: number,
  ): boolean {
    const projected = [...position.data]
    const ttlS = Math.min(command.ttl_ms ?? 0, MAX_TTL_MS) / 1000
    if (!Number.isFinite(ttlS) || ttlS <= 0) return false
    const horizon = command.horizon ?? []
    if (horizon.length === 0) {
      return this.advanceGeofencePosition(projected, command.channels, ttlS, radius)
    }

    const dtS = (command.horizon_dt_ms ?? 0) / 1000
    if (!Number.isFinite(dtS) || dtS <= 0) return false
    const tickZeroS = Math.min(ttlS, dtS)
    if (!this.advanceGeofencePosition(projected, command.channels, tickZeroS, radius)) {
      return false
    }
    let remainingS = Math.max(ttlS - tickZeroS, 0)
    let safeLen = horizon.length
    for (let i = 0; i < horizon.length; i++) {
      if (remainingS <= 0) break
      const durationS = Math.min(remainingS, dtS)
      if (!this.advanceGeofencePosition(projected, horizon[i]!, durationS, radius)) {
        if (i === 0) return false
        safeLen = i
        break
      }
      remainingS = Math.max(remainingS - durationS, 0)
    }
    horizon.length = safeLen
    return true
  }

  private advanceGeofencePosition(
    position: number[],
    channels: WireChannels,
    durationS: number,
    radius: number,
  ): boolean {
    const velocity = channels[this.velocityChannel]
    if (
      velocity === undefined ||
      !this.validSafetyVector(velocity, VELOCITY_UNIT) ||
      !Number.isFinite(durationS) ||
      durationS < 0
    ) {
      return false
    }
    for (let i = 0; i < SAFETY_VECTOR_WIDTH; i++) {
      position[i] = position[i]! + velocity.data[i]! * durationS
    }
    const norm = Math.sqrt(position.reduce((sum, value) => sum + value * value, 0))
    return Number.isFinite(norm) && norm <= radius
  }

  /** Magnitude-clamp the velocity channel in place; `false` = unenforceable
   *  (absent channel / wrong unit or width / non-finite magnitude) and the caller
   *  must fail safe. */
  private clampVelocity(channels: WireChannels, maxSpeed: number): boolean {
    const vel = channels[this.velocityChannel]
    if (vel === undefined || !this.validSafetyVector(vel, VELOCITY_UNIT)) return false
    const mag = Math.sqrt(vel.data.reduce((s, c) => s + c * c, 0))
    if (!Number.isFinite(mag)) return false
    if (mag > maxSpeed) {
      const k = maxSpeed / mag
      vel.data = vel.data.map((c) => c * k)
    }
    return true
  }

  private validSafetyVector(
    channel: { data: number[]; unit?: string | null },
    expectedUnit: string,
  ): boolean {
    return (
      channel.unit === expectedUnit &&
      channel.data.length === SAFETY_VECTOR_WIDTH &&
      channel.data.every(Number.isFinite)
    )
  }
}

/** Minimum wire-legal `seq` per data-plane kind (wire 0.6). */
function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/** Structural channel validation for programmatic JS objects. JSON.parse itself
 * rejects NaN/Infinity, but callers may hand the safety API an object directly;
 * accepting one that Rust serde would reject breaks cross-language parity. */
function assertChannels(value: unknown, path: string): void {
  if (value === undefined) return // Rust wire default: empty map
  if (!isRecord(value)) throw new Error(`${path} must be an object`)
  for (const [name, raw] of Object.entries(value)) {
    if (!isRecord(raw)) throw new Error(`${path}.${name} must be an object`)
    const data = raw.data
    if (data !== undefined) {
      if (
        !Array.isArray(data) ||
        data.some((sample) => typeof sample !== 'number' || !Number.isFinite(sample))
      ) {
        throw new Error(`${path}.${name}.data must be an array of finite numbers`)
      }
    }
    const unit = raw.unit
    if (unit !== undefined && unit !== null && typeof unit !== 'string') {
      throw new Error(`${path}.${name}.unit must be a string or null`)
    }
  }
}

function assertOptionalFinite(value: unknown, path: string, nullable = false): void {
  if (value === undefined || (nullable && value === null)) return
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new Error(`${path} must be ${nullable ? 'a finite number or null' : 'a finite number'}`)
  }
}

/**
 * Wire-0.6 data-plane ingress gate — the TS mirror of
 * `ncp_core::decode_validated`: the frame must carry the expected `kind`, a
 * COMPATIBLE `ncp_version` (absent/incompatible throws {@link NcpVersionError} —
 * never coerced to ours), and a stamped `seq` within the kind's wire bound
 * (`sensor_frame`/`command_frame` >= 1; `observation_frame` >= 0, where 0 is the
 * pull/RPC-reply form). Call this on every frame read off a data plane and DROP
 * frames that throw (log them; never actuate on them).
 */
export function assertWireFrame(
  frame: Record<string, unknown>,
  expectedKind: 'sensor_frame' | 'command_frame' | 'observation_frame',
): void {
  assertNcpMessage(frame, expectedKind)
  if (frame.kind !== expectedKind) {
    throw new Error(
      `NCP kind mismatch: expected ${JSON.stringify(expectedKind)}, got ${JSON.stringify(frame.kind)}`,
    )
  }
  const ver = frame.ncp_version
  if (typeof ver !== 'string') {
    throw new NcpVersionError(
      `${expectedKind}: frame carries no ncp_version (mandatory since wire 0.6)`,
    )
  }
  checkVersion(ver, true)
  const stream = frame.stream as { epoch?: unknown; seq?: unknown } | undefined
  const seq = stream?.seq
  if (typeof seq !== 'number' || !Number.isSafeInteger(seq) || seq < 1) {
    throw new Error(
      `${expectedKind}: stream.seq ${JSON.stringify(seq)} invalid (wire 0.8 requires a safe integer >= 1)`,
    )
  }
  if (typeof stream?.epoch !== 'string' || !UUID_V4_SAFETY.test(stream.epoch)) {
    throw new Error(`${expectedKind}.stream.epoch must be a canonical lowercase UUIDv4`)
  }
  const session = frame.session as { generation?: unknown } | undefined
  if (typeof session?.generation !== 'string' || !UUID_V4_SAFETY.test(session.generation)) {
    throw new Error(`${expectedKind}.session.generation must be a canonical lowercase UUIDv4`)
  }
  if (typeof frame.session_id !== 'string' || frame.session_id.length === 0) {
    throw new Error(`${expectedKind}.session_id must be a non-empty string`)
  }
  if (expectedKind === 'sensor_frame' || expectedKind === 'command_frame') {
    assertChannels(frame.channels, `${expectedKind}.channels`)
  }
  if (expectedKind === 'command_frame') {
    if (frame.mode !== undefined && typeof frame.mode !== 'string') {
      throw new Error('command_frame.mode must be a string')
    }
    assertOptionalFinite(frame.t, 'command_frame.t')
    assertOptionalFinite(frame.ttl_ms, 'command_frame.ttl_ms')
    assertOptionalFinite(frame.horizon_dt_ms, 'command_frame.horizon_dt_ms', true)
    if (frame.horizon !== undefined) {
      if (!Array.isArray(frame.horizon)) throw new Error('command_frame.horizon must be an array')
      frame.horizon.forEach((step, index) =>
        assertChannels(step, `command_frame.horizon[${index}]`),
      )
    }
  }
}
