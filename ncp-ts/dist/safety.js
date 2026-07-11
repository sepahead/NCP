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
// Extension-full specifier so the EMITTED dist/safety.js resolves under plain
// node ESM (the behavior runner imports dist/*.js directly; see
// scripts/check-behavior.mjs) — tsc still type-resolves this to ./client.ts.
import { assertNcpMessage, checkVersion, hasWireControlCharacters, MAX_HORIZON_STEPS, NCP_VERSION, NcpVersionError, } from './client.js';
/** Upper bound on an enforced command ttl (ms) — mirrors `safety.rs::MAX_TTL_MS`:
 *  the wire field is unbounded, but the plant-side deadline must stay finite. */
export const MAX_TTL_MS = 60_000;
/** How many consecutive `command_timeout_ms` deadlines of TOTAL sensor silence
 *  escalate the non-latching staleness HOLD to a latched ESTOP (mirrors
 *  `safety.rs::LINK_LOSS_ESTOP_FACTOR`). */
export const LINK_LOSS_ESTOP_FACTOR = 20;
const POSITION_CHANNEL = 'pose_position';
const VELOCITY_CHANNEL = 'velocity_setpoint';
const POSITION_UNIT = 'm';
const VELOCITY_UNIT = 'm/s';
const SAFETY_VECTOR_WIDTH = 3;
function compatibleSafetyVec3(spec, expectedUnit) {
    if (spec === undefined || spec.kind !== 'vec3' || spec.unit !== expectedUnit)
        return false;
    const size = spec.size;
    return size == null || size === SAFETY_VECTOR_WIDTH || size === BigInt(SAFETY_VECTOR_WIDTH);
}
/**
 * Plant-side deadline backstop enforcing `CommandFrame.ttl_ms` — mirrors
 * `ncp_core::CommandWatchdog` exactly, including the wire-0.6 seq discipline:
 * `seq < 1` (unstamped) NEVER refreshes liveness; a duplicate never refreshes; a
 * strictly-lower `seq` re-anchors a restarted stream only once the stream is
 * already expired (the plant is safely holding).
 */
export class CommandWatchdog {
    lastRecvS = null;
    ttlS = 0;
    lastSeq = 0;
    clockHighWaterS = null;
    clockFaulted = false;
    observeClock(nowS) {
        if (!Number.isFinite(nowS)) {
            this.clockFaulted = true;
            return false;
        }
        if (this.clockHighWaterS !== null && nowS < this.clockHighWaterS) {
            this.clockFaulted = true;
            return false;
        }
        this.clockHighWaterS = nowS;
        return true;
    }
    /** Record an accepted command at local time `nowS` with its `ttl_ms` and `seq`. */
    onCommand(nowS, ttlMs, seq) {
        if (!this.observeClock(nowS))
            return;
        if (!Number.isSafeInteger(seq) || seq < 1)
            return;
        const recoveringClock = this.clockFaulted;
        if (seq <= this.lastSeq &&
            (seq === this.lastSeq || (!recoveringClock && !this.shouldHold(nowS)))) {
            return; // duplicate (always), or stale/reordered while the stream is LIVE
        }
        this.lastSeq = seq;
        this.lastRecvS = nowS;
        // Bound the enforced ttl: non-finite -> 0 (immediately stale); clamp to the
        // finite ceiling so one command cannot keep the plant live indefinitely.
        this.ttlS = Number.isFinite(ttlMs) ? Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / 1000 : 0;
        this.clockFaulted = false;
    }
    /** True if the plant must fail safe to HOLD (no command, expired, bad clock). */
    shouldHold(nowS) {
        if (!this.observeClock(nowS) || this.clockFaulted)
            return true;
        const t = this.lastRecvS;
        if (t === null)
            return true;
        return (!Number.isFinite(nowS) ||
            !Number.isFinite(t) ||
            this.ttlS <= 0 ||
            nowS < t || // backward clock step: fail closed
            nowS - t >= this.ttlS);
    }
}
/** Cap a horizon length to its deadline (`N <= ttl_ms / horizon_dt_ms`); a
 *  non-finite ttl/dt (or dt <= 0) returns 0 — mirrors `resilience.rs`. */
export function maxHorizonLen(ttlMs, horizonDtMs) {
    if (!Number.isFinite(ttlMs) || !Number.isFinite(horizonDtMs) || horizonDtMs <= 0)
        return 0;
    const steps = Math.floor(Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / horizonDtMs);
    if (!Number.isFinite(steps))
        return 0;
    return Math.min(Math.max(steps, 0), MAX_HORIZON_STEPS);
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
    latest = null;
    recvS = 0;
    watchdog = new CommandWatchdog();
    estop = false;
    lastSeq = 0;
    onCommand(nowS, command) {
        // Fail-safe priority: HOLD/INIT/future non-actuating modes clear buffered
        // actuation even when malformed, stale, or duplicate. Dropping one would
        // leave the previous Active horizon running until ttl.
        if (command.mode !== 'active')
            this.latest = null;
        if (command.mode === 'estop') {
            this.estop = true; // latch even if the frame is stale/out-of-order/unstamped
        }
        try {
            assertWireFrame(command, 'command_frame');
        }
        catch {
            return; // ESTOP already latched; every other invalid envelope is ignored
        }
        const seq = command.seq ?? 0;
        if (!Number.isSafeInteger(seq) || seq < 1)
            return;
        if (seq <= this.lastSeq && (seq === this.lastSeq || !this.watchdog.shouldHold(nowS))) {
            return; // duplicate (always), or stale/reordered while LIVE (ESTOP latched above)
        }
        this.lastSeq = seq;
        if (command.mode !== 'active')
            return;
        this.watchdog.onCommand(nowS, command.ttl_ms ?? 200, seq);
        this.recvS = nowS;
        // Rust takes ownership of the accepted frame. Clone here so a JavaScript
        // caller cannot mutate channels/mode/horizon after validation and change
        // live actuation without a new sequence number or watchdog update.
        this.latest = structuredClone(command);
    }
    /** Clear a latched ESTOP and discard all pre-ESTOP command state. A fresh
     * validated Active command is required before actuation resumes. */
    reset() {
        this.estop = false;
        this.latest = null;
        this.recvS = 0;
        this.watchdog = new CommandWatchdog();
        this.lastSeq = 0;
    }
    isEstopped() {
        return this.estop;
    }
    /** The setpoint channels to apply at `nowS`, or `null` to fail safe (HOLD). */
    active(nowS) {
        if (this.estop)
            return null;
        if (this.watchdog.shouldHold(nowS))
            return null;
        const cmd = this.latest;
        if (cmd === null)
            return null;
        // ALLOWLIST, not denylist: only `active` actuates (init/hold/estop and any
        // future mode fail safe to HOLD).
        if (cmd.mode !== 'active')
            return null;
        const dt = cmd.horizon_dt_ms ?? 0;
        const horizon = cmd.horizon ?? [];
        if (!(dt > 0) || horizon.length === 0)
            return structuredClone(cmd.channels);
        const tick = Math.floor(((nowS - this.recvS) * 1000) / dt);
        if (tick <= 0)
            return structuredClone(cmd.channels);
        const step = horizon[tick - 1];
        return step === undefined ? null : structuredClone(step);
    }
    shouldHold(nowS) {
        return this.active(nowS) === null;
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
    limits;
    positionChannel;
    velocityChannel;
    commandChannels;
    positionContractValid;
    velocityContractValid;
    estop = false;
    configFailClosed;
    constructor(limits, positionChannel = POSITION_CHANNEL, velocityChannel = VELOCITY_CHANNEL, commandChannels = [VELOCITY_CHANNEL], sensorChannels = [], positionContractValid = true, velocityContractValid = true) {
        this.limits = limits;
        this.positionChannel = positionChannel;
        this.velocityChannel = velocityChannel;
        this.commandChannels = commandChannels;
        this.positionContractValid = positionContractValid;
        this.velocityContractValid = velocityContractValid;
        if (this.commandChannels.length === 0)
            this.commandChannels = [this.velocityChannel];
        const geofenceBad = (this.limits.geofence_radius_m ?? 0) > 0 &&
            sensorChannels.length > 0 &&
            !sensorChannels.includes(this.positionChannel);
        const speedBad = ((this.limits.max_speed_mps ?? 0) > 0 ||
            (this.limits.geofence_radius_m ?? 0) > 0) &&
            !this.commandChannels.includes(this.velocityChannel);
        const badLimit = (v) => v != null && (!Number.isFinite(v) || v < 0);
        const timeoutBad = !Number.isFinite(this.limits.command_timeout_ms) || this.limits.command_timeout_ms <= 0;
        const validChannelName = (name) => name.length > 0 && !hasWireControlCharacters(name);
        const channelConfigBad = !validChannelName(this.positionChannel) ||
            !validChannelName(this.velocityChannel) ||
            this.commandChannels.some((name) => !validChannelName(name)) ||
            sensorChannels.some((name) => !validChannelName(name)) ||
            new Set(this.commandChannels).size !== this.commandChannels.length ||
            new Set(sensorChannels).size !== sensorChannels.length;
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
                    !this.velocityContractValid);
    }
    /** Resolve explicit canonical safety channels from negotiated `Capabilities`.
     *  Enabled limits require width-3 `vec3` specs in canonical SI units; declaration
     *  order never selects a safety input. Mirrors Rust `from_capabilities`. */
    static fromCapabilities(caps) {
        const commandChannels = caps.command_channels.map((c) => c.name);
        const sensorChannels = caps.sensor_channels.map((c) => c.name);
        const positionContractValid = compatibleSafetyVec3(caps.sensor_channels.find((channel) => channel.name === POSITION_CHANNEL), POSITION_UNIT);
        const velocityContractValid = compatibleSafetyVec3(caps.command_channels.find((channel) => channel.name === VELOCITY_CHANNEL), VELOCITY_UNIT);
        return new SafetyGovernor(caps.safety, POSITION_CHANNEL, VELOCITY_CHANNEL, commandChannels, sensorChannels, positionContractValid, velocityContractValid);
    }
    /** Clear a latched ESTOP (supervisor authority; config fail-closed is NOT cleared). */
    reset() {
        this.estop = false;
    }
    isEstopped() {
        return this.estop;
    }
    /** Latch ESTOP when the link monitor reports a sustained loss burst (a jam). */
    noteLink(burst) {
        if (burst)
            this.estop = true;
    }
    safetyOk() {
        return !this.estop && !this.configFailClosed;
    }
    zeroedChannels(command) {
        const out = {};
        const rawChannels = command?.channels;
        const entries = typeof rawChannels === 'object' && rawChannels !== null && !Array.isArray(rawChannels)
            ? Object.entries(rawChannels)
            : [];
        for (const [name, raw] of entries) {
            if (name.length === 0 || hasWireControlCharacters(name))
                continue;
            const cv = typeof raw === 'object' && raw !== null && !Array.isArray(raw)
                ? raw
                : {};
            const data = Array.isArray(cv.data) ? cv.data : [];
            const unit = typeof cv.unit === 'string' || cv.unit === null ? cv.unit : null;
            out[name] =
                name === this.velocityChannel
                    ? { data: new Array(SAFETY_VECTOR_WIDTH).fill(0), unit: VELOCITY_UNIT }
                    : { data: new Array(Math.max(data.length, 1)).fill(0), unit };
        }
        for (const name of this.commandChannels) {
            if (name.length === 0 || hasWireControlCharacters(name))
                continue;
            if (!(name in out)) {
                out[name] =
                    name === this.velocityChannel
                        ? { data: [0, 0, 0], unit: VELOCITY_UNIT }
                        : { data: [0], unit: null };
            }
        }
        return out;
    }
    safeFrame(command, mode) {
        const raw = command;
        const seq = typeof raw.seq === 'number' &&
            Number.isSafeInteger(raw.seq) &&
            raw.seq >= 1 &&
            raw.seq <= Number.MAX_SAFE_INTEGER
            ? raw.seq
            : 1;
        const t = typeof raw.t === 'number' && Number.isFinite(raw.t) ? raw.t : 0;
        const frameId = typeof raw.frame_id === 'string' &&
            raw.frame_id.length > 0 &&
            !hasWireControlCharacters(raw.frame_id)
            ? raw.frame_id
            : 'world';
        return {
            kind: 'command_frame',
            ncp_version: NCP_VERSION,
            seq,
            t,
            frame_id: frameId,
            mode,
            ttl_ms: 200,
            channels: this.zeroedChannels(command),
            horizon: [],
            horizon_dt_ms: null,
        };
    }
    /**
     * Apply safety to `command` against the latest `sensor`. `nowS`/`lastSensorS`
     * are wall-clock seconds (the plant's own clock). Returns a fresh frame; ESTOP
     * latches (call {@link reset} to clear).
     */
    govern(command, sensor, nowS, lastSensorS) {
        // Latched ESTOP dominates everything until a supervisor reset.
        if (this.estop)
            return this.safeFrame(command, 'estop');
        // An INBOUND ESTOP-mode command is itself a fail-safe: LATCH and propagate
        // (zeroed ESTOP out), never downgrade to a non-latching HOLD.
        if (command.mode === 'estop') {
            this.estop = true;
            return this.safeFrame(command, 'estop');
        }
        if (((this.limits.geofence_radius_m ?? 0) > 0 && !this.positionContractValid) ||
            (((this.limits.max_speed_mps ?? 0) > 0 ||
                (this.limits.geofence_radius_m ?? 0) > 0) &&
                !this.velocityContractValid)) {
            this.configFailClosed = true;
        }
        // A configured-but-nonsensical geofence/speed limit fails CLOSED.
        const badLimit = (v) => v != null && (!Number.isFinite(v) || v < 0);
        if (badLimit(this.limits.geofence_radius_m) ||
            badLimit(this.limits.max_speed_mps) ||
            badLimit(this.limits.max_tilt_rad)) {
            this.configFailClosed = true;
        }
        const timeoutMs = this.limits.command_timeout_ms;
        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            this.configFailClosed = true;
        }
        if (this.configFailClosed)
            return this.safeFrame(command, 'hold');
        // A timestamp alone is not proof of perception liveness. Validate the
        // sensor independently so a malformed/absent frame enters the same stale
        // path (including total-silence escalation) as no frame at all.
        let validatedSensor = sensor;
        try {
            if (validatedSensor !== null) {
                assertWireFrame(validatedSensor, 'sensor_frame');
            }
        }
        catch {
            validatedSensor = null;
        }
        // Staleness backstop (default-deny; NaN/backward clocks fail closed).
        // A huge-but-finite timeout must not disable freshness indefinitely. Preserve
        // it on the wire, but cap local enforcement like the Rust reference.
        const timeoutS = Math.min(timeoutMs, MAX_TTL_MS) / 1000;
        const stale = validatedSensor === null ||
            lastSensorS == null ||
            !Number.isFinite(nowS) ||
            !Number.isFinite(lastSensorS) ||
            nowS < lastSensorS ||
            nowS - lastSensorS >= timeoutS;
        if (stale) {
            // Sustained TOTAL silence escalates HOLD -> latched ESTOP.
            if (lastSensorS != null &&
                Number.isFinite(nowS) &&
                Number.isFinite(lastSensorS) &&
                nowS >= lastSensorS) {
                const deadlineS = Math.min(timeoutS * LINK_LOSS_ESTOP_FACTOR, MAX_TTL_MS / 1000);
                if (nowS - lastSensorS >= deadlineS) {
                    this.estop = true;
                    return this.safeFrame(command, 'estop');
                }
            }
            return this.safeFrame(command, 'hold');
        }
        // Kept as an explicit fail-closed narrowing guard even though `stale`
        // already includes this condition.
        if (validatedSensor === null)
            return this.safeFrame(command, 'hold');
        // Geofence: a configured positive radius MUST be evaluable (fail closed).
        const radius = this.limits.geofence_radius_m;
        if (radius != null && radius > 0) {
            const pos = validatedSensor.channels?.[this.positionChannel];
            if (pos === undefined)
                return this.safeFrame(command, 'hold');
            if (!this.validSafetyVector(pos, POSITION_UNIT))
                return this.safeFrame(command, 'hold');
            const r = Math.sqrt(pos.data.reduce((s, c) => s + c * c, 0));
            if (!Number.isFinite(r) || r > radius) {
                this.estop = true;
                return this.safeFrame(command, 'estop');
            }
        }
        // Freshness, total-silence escalation, and the CURRENT geofence state run
        // before command validation/mode checks. A HOLD or malformed non-ESTOP
        // command must never hide a collapsed link or an already-breached boundary.
        try {
            assertWireFrame(command, 'command_frame');
        }
        catch {
            return this.safeFrame(command, 'hold');
        }
        // Only `active` may actuate (defense-in-depth with ActionBuffer's allowlist).
        if (command.mode !== 'active')
            return this.safeFrame(command, 'hold');
        const out = structuredClone(command);
        out.horizon = out.horizon ?? [];
        const maxSpeed = this.limits.max_speed_mps;
        if (maxSpeed != null && maxSpeed > 0) {
            if (!this.clampVelocity(out.channels, maxSpeed))
                return this.safeFrame(command, 'hold');
            // Clamp every predictive horizon step too; truncate at the first
            // unclampable step so replay HOLDs rather than emitting unbounded output.
            let safeLen = out.horizon.length;
            for (let i = 0; i < out.horizon.length; i++) {
                if (!this.clampVelocity(out.horizon[i], maxSpeed)) {
                    // An empty horizon means legacy "replay tick 0 until ttl", not
                    // "drain after tick 0". Reject instead of truncating index 0 to an
                    // actively replayed command.
                    if (i === 0)
                        return this.safeFrame(command, 'hold');
                    safeLen = i;
                    break;
                }
            }
            out.horizon.length = safeLen;
        }
        // Project the exact canonical velocity trajectory over every interval that
        // ActionBuffer can apply before ttl. Current in-bounds position alone is not
        // enough: the legacy no-horizon form replays tick 0 for the entire ttl.
        if (radius != null && radius > 0) {
            const pos = validatedSensor.channels?.[this.positionChannel];
            const commandFrame = command.frame_id ?? 'world';
            const sensorFrame = validatedSensor.frame_id ?? 'world';
            if (commandFrame !== sensorFrame ||
                pos === undefined ||
                !this.enforceGeofenceTrajectory(out, pos, radius)) {
                return this.safeFrame(command, 'hold');
            }
        }
        return out;
    }
    enforceGeofenceTrajectory(command, position, radius) {
        const projected = [...position.data];
        const ttlS = Math.min(command.ttl_ms ?? 0, MAX_TTL_MS) / 1000;
        if (!Number.isFinite(ttlS) || ttlS <= 0)
            return false;
        const horizon = command.horizon ?? [];
        if (horizon.length === 0) {
            return this.advanceGeofencePosition(projected, command.channels, ttlS, radius);
        }
        const dtS = (command.horizon_dt_ms ?? 0) / 1000;
        if (!Number.isFinite(dtS) || dtS <= 0)
            return false;
        const tickZeroS = Math.min(ttlS, dtS);
        if (!this.advanceGeofencePosition(projected, command.channels, tickZeroS, radius)) {
            return false;
        }
        let remainingS = Math.max(ttlS - tickZeroS, 0);
        let safeLen = horizon.length;
        for (let i = 0; i < horizon.length; i++) {
            if (remainingS <= 0)
                break;
            const durationS = Math.min(remainingS, dtS);
            if (!this.advanceGeofencePosition(projected, horizon[i], durationS, radius)) {
                if (i === 0)
                    return false;
                safeLen = i;
                break;
            }
            remainingS = Math.max(remainingS - durationS, 0);
        }
        horizon.length = safeLen;
        return true;
    }
    advanceGeofencePosition(position, channels, durationS, radius) {
        const velocity = channels[this.velocityChannel];
        if (velocity === undefined ||
            !this.validSafetyVector(velocity, VELOCITY_UNIT) ||
            !Number.isFinite(durationS) ||
            durationS < 0) {
            return false;
        }
        for (let i = 0; i < SAFETY_VECTOR_WIDTH; i++) {
            position[i] = position[i] + velocity.data[i] * durationS;
        }
        const norm = Math.sqrt(position.reduce((sum, value) => sum + value * value, 0));
        return Number.isFinite(norm) && norm <= radius;
    }
    /** Magnitude-clamp the velocity channel in place; `false` = unenforceable
     *  (absent channel / wrong unit or width / non-finite magnitude) and the caller
     *  must fail safe. */
    clampVelocity(channels, maxSpeed) {
        const vel = channels[this.velocityChannel];
        if (vel === undefined || !this.validSafetyVector(vel, VELOCITY_UNIT))
            return false;
        const mag = Math.sqrt(vel.data.reduce((s, c) => s + c * c, 0));
        if (!Number.isFinite(mag))
            return false;
        if (mag > maxSpeed) {
            const k = maxSpeed / mag;
            vel.data = vel.data.map((c) => c * k);
        }
        return true;
    }
    validSafetyVector(channel, expectedUnit) {
        return (channel.unit === expectedUnit &&
            channel.data.length === SAFETY_VECTOR_WIDTH &&
            channel.data.every(Number.isFinite));
    }
}
/** Minimum wire-legal `seq` per data-plane kind (wire 0.6). */
const MIN_SEQ = {
    sensor_frame: 1,
    command_frame: 1,
    observation_frame: 0,
};
function isRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}
/** Structural channel validation for programmatic JS objects. JSON.parse itself
 * rejects NaN/Infinity, but callers may hand the safety API an object directly;
 * accepting one that Rust serde would reject breaks cross-language parity. */
function assertChannels(value, path) {
    if (value === undefined)
        return; // Rust wire default: empty map
    if (!isRecord(value))
        throw new Error(`${path} must be an object`);
    for (const [name, raw] of Object.entries(value)) {
        if (!isRecord(raw))
            throw new Error(`${path}.${name} must be an object`);
        const data = raw.data;
        if (data !== undefined) {
            if (!Array.isArray(data) ||
                data.some((sample) => typeof sample !== 'number' || !Number.isFinite(sample))) {
                throw new Error(`${path}.${name}.data must be an array of finite numbers`);
            }
        }
        const unit = raw.unit;
        if (unit !== undefined && unit !== null && typeof unit !== 'string') {
            throw new Error(`${path}.${name}.unit must be a string or null`);
        }
    }
}
function assertOptionalFinite(value, path, nullable = false) {
    if (value === undefined || (nullable && value === null))
        return;
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        throw new Error(`${path} must be ${nullable ? 'a finite number or null' : 'a finite number'}`);
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
export function assertWireFrame(frame, expectedKind) {
    assertNcpMessage(frame, expectedKind);
    if (frame.kind !== expectedKind) {
        throw new Error(`NCP kind mismatch: expected ${JSON.stringify(expectedKind)}, got ${JSON.stringify(frame.kind)}`);
    }
    const ver = frame.ncp_version;
    if (typeof ver !== 'string') {
        throw new NcpVersionError(`${expectedKind}: frame carries no ncp_version (mandatory since wire 0.6)`);
    }
    checkVersion(ver, true);
    const minSeq = MIN_SEQ[expectedKind];
    const seq = frame.seq;
    if (typeof seq !== 'number' || !Number.isSafeInteger(seq) || seq < minSeq) {
        throw new Error(`${expectedKind}: seq ${JSON.stringify(seq)} invalid (wire 0.6 requires a safe integer >= ${minSeq})`);
    }
    if (expectedKind === 'sensor_frame' || expectedKind === 'command_frame') {
        assertChannels(frame.channels, `${expectedKind}.channels`);
    }
    if (expectedKind === 'command_frame') {
        if (frame.mode !== undefined && typeof frame.mode !== 'string') {
            throw new Error('command_frame.mode must be a string');
        }
        assertOptionalFinite(frame.t, 'command_frame.t');
        assertOptionalFinite(frame.ttl_ms, 'command_frame.ttl_ms');
        assertOptionalFinite(frame.horizon_dt_ms, 'command_frame.horizon_dt_ms', true);
        if (frame.horizon !== undefined) {
            if (!Array.isArray(frame.horizon))
                throw new Error('command_frame.horizon must be an array');
            frame.horizon.forEach((step, index) => assertChannels(step, `command_frame.horizon[${index}]`));
        }
    }
}
//# sourceMappingURL=safety.js.map