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
import { checkVersion, NcpVersionError } from './client.js';
/** Upper bound on an enforced command ttl (ms) — mirrors `safety.rs::MAX_TTL_MS`:
 *  the wire field is unbounded, but the plant-side deadline must stay finite. */
export const MAX_TTL_MS = 60_000;
/** How many consecutive `command_timeout_ms` deadlines of TOTAL sensor silence
 *  escalate the non-latching staleness HOLD to a latched ESTOP (mirrors
 *  `safety.rs::LINK_LOSS_ESTOP_FACTOR`). */
export const LINK_LOSS_ESTOP_FACTOR = 20;
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
    /** Record an accepted command at local time `nowS` with its `ttl_ms` and `seq`. */
    onCommand(nowS, ttlMs, seq) {
        if (!(seq >= 1))
            return; // unstamped/invalid (incl. NaN) never refreshes liveness
        if (seq <= this.lastSeq && (seq === this.lastSeq || !this.shouldHold(nowS))) {
            return; // duplicate (always), or stale/reordered while the stream is LIVE
        }
        this.lastSeq = seq;
        this.lastRecvS = nowS;
        // Bound the enforced ttl: non-finite -> 0 (immediately stale); clamp to the
        // finite ceiling so one command cannot keep the plant live indefinitely.
        this.ttlS = Number.isFinite(ttlMs) ? Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / 1000 : 0;
    }
    /** True if the plant must fail safe to HOLD (no command, expired, bad clock). */
    shouldHold(nowS) {
        const t = this.lastRecvS;
        if (t === null)
            return true;
        return (!Number.isFinite(nowS) ||
            !Number.isFinite(t) ||
            this.ttlS <= 0 ||
            nowS < t || // backward clock step: fail closed
            nowS - t > this.ttlS);
    }
}
/** Cap a horizon length to its deadline (`N <= ttl_ms / horizon_dt_ms`); a
 *  non-finite ttl/dt (or dt <= 0) returns 0 — mirrors `resilience.rs`. */
export function maxHorizonLen(ttlMs, horizonDtMs) {
    if (!Number.isFinite(ttlMs) || !Number.isFinite(horizonDtMs) || horizonDtMs <= 0)
        return 0;
    return Math.max(Math.floor(ttlMs / horizonDtMs), 0);
}
/**
 * Plant-side packetized-predictive-control buffer — mirrors
 * `ncp_core::ActionBuffer`: holds the latest command + horizon, replays through
 * dropouts, fails safe once expired or drained; ESTOP latches regardless of
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
        if (command.mode === 'estop') {
            this.estop = true; // latch even if the frame is stale/out-of-order/unstamped
        }
        const seq = command.seq ?? 0;
        if (!(seq >= 1))
            return; // unstamped/invalid seq: never buffered (ESTOP latched above)
        if (seq <= this.lastSeq && (seq === this.lastSeq || !this.watchdog.shouldHold(nowS))) {
            return; // duplicate (always), or stale/reordered while LIVE (ESTOP latched above)
        }
        this.lastSeq = seq;
        this.watchdog.onCommand(nowS, command.ttl_ms ?? 200, seq);
        this.recvS = nowS;
        this.latest = command;
    }
    /** Clear a latched ESTOP (supervisor authority). */
    reset() {
        this.estop = false;
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
    estop = false;
    configFailClosed;
    constructor(limits, positionChannel = 'pose_position', velocityChannel = 'velocity_setpoint', commandChannels = ['velocity_setpoint'], sensorChannels = []) {
        this.limits = limits;
        this.positionChannel = positionChannel;
        this.velocityChannel = velocityChannel;
        this.commandChannels = commandChannels;
        if (this.commandChannels.length === 0)
            this.commandChannels = [this.velocityChannel];
        const geofenceBad = (this.limits.geofence_radius_m ?? 0) > 0 &&
            sensorChannels.length > 0 &&
            !sensorChannels.includes(this.positionChannel);
        const speedBad = (this.limits.max_speed_mps ?? 0) > 0 && !this.commandChannels.includes(this.velocityChannel);
        this.configFailClosed = geofenceBad || speedBad;
    }
    /** Resolve the enforced channels from the negotiated `Capabilities` (position =
     *  first sensor channel, velocity = first command channel, HOLD/zero set =
     *  every declared command channel) — mirrors `SafetyGovernor::from_capabilities`. */
    static fromCapabilities(caps) {
        const commandChannels = caps.command_channels.map((c) => c.name);
        const sensorChannels = caps.sensor_channels.map((c) => c.name);
        return new SafetyGovernor(caps.safety, sensorChannels[0] ?? 'pose_position', commandChannels[0] ?? 'velocity_setpoint', commandChannels, sensorChannels);
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
        for (const [name, cv] of Object.entries(command.channels ?? {})) {
            out[name] = { data: new Array(Math.max(cv.data.length, 1)).fill(0), unit: cv.unit ?? null };
        }
        for (const name of this.commandChannels) {
            if (!(name in out)) {
                out[name] =
                    name === this.velocityChannel
                        ? { data: [0, 0, 0], unit: 'm/s' }
                        : { data: [0], unit: null };
            }
        }
        return out;
    }
    safeFrame(command, mode) {
        return {
            kind: 'command_frame',
            ncp_version: command.ncp_version,
            seq: command.seq ?? 0,
            t: command.t ?? 0,
            frame_id: 'world',
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
        if (this.configFailClosed)
            return this.safeFrame(command, 'hold');
        // Only `active` may actuate (defense-in-depth with ActionBuffer's allowlist).
        if (command.mode !== 'active')
            return this.safeFrame(command, 'hold');
        // A configured-but-nonsensical geofence/speed limit fails CLOSED.
        const badLimit = (v) => v != null && (!Number.isFinite(v) || v < 0);
        if (badLimit(this.limits.geofence_radius_m) || badLimit(this.limits.max_speed_mps)) {
            this.configFailClosed = true;
            return this.safeFrame(command, 'hold');
        }
        const timeoutMs = this.limits.command_timeout_ms;
        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            this.configFailClosed = true;
            return this.safeFrame(command, 'hold');
        }
        // Staleness backstop (default-deny; NaN/backward clocks fail closed).
        const timeoutS = timeoutMs / 1000;
        const stale = lastSensorS == null ||
            !Number.isFinite(nowS) ||
            !Number.isFinite(lastSensorS) ||
            nowS < lastSensorS ||
            nowS - lastSensorS > timeoutS;
        if (stale) {
            // Sustained TOTAL silence escalates HOLD -> latched ESTOP.
            if (lastSensorS != null &&
                Number.isFinite(nowS) &&
                Number.isFinite(lastSensorS) &&
                nowS >= lastSensorS) {
                const deadlineS = Math.min(timeoutS * LINK_LOSS_ESTOP_FACTOR, MAX_TTL_MS / 1000);
                if (nowS - lastSensorS > deadlineS) {
                    this.estop = true;
                    return this.safeFrame(command, 'estop');
                }
            }
            return this.safeFrame(command, 'hold');
        }
        // Geofence: a configured positive radius MUST be evaluable (fail closed).
        const radius = this.limits.geofence_radius_m;
        if (radius != null && radius > 0) {
            const pos = sensor?.channels?.[this.positionChannel];
            if (pos === undefined)
                return this.safeFrame(command, 'hold');
            if (pos.data.length === 0)
                return this.safeFrame(command, 'hold');
            const r = Math.sqrt(pos.data.reduce((s, c) => s + c * c, 0));
            if (!Number.isFinite(r) || r > radius) {
                this.estop = true;
                return this.safeFrame(command, 'estop');
            }
        }
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
                    safeLen = i;
                    break;
                }
            }
            out.horizon.length = safeLen;
        }
        // Geofence horizon look-ahead: truncate the open-loop horizon near the fence.
        if (radius != null && radius > 0 && out.horizon.length > 0) {
            const pos = sensor?.channels?.[this.positionChannel];
            if (pos !== undefined) {
                const r = Math.sqrt(pos.data.reduce((s, c) => s + c * c, 0));
                const dtS = (command.horizon_dt_ms ?? 0) / 1000;
                const n = out.horizon.length;
                const margin = maxSpeed != null && maxSpeed > 0 && dtS > 0 ? maxSpeed * n * dtS : Infinity;
                if (Number.isFinite(r) && r > radius - margin)
                    out.horizon = [];
            }
        }
        return out;
    }
    /** Magnitude-clamp the velocity channel in place; `false` = unenforceable
     *  (absent channel / non-finite magnitude) and the caller must fail safe. */
    clampVelocity(channels, maxSpeed) {
        const vel = channels[this.velocityChannel];
        if (vel === undefined)
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
}
/** Minimum wire-legal `seq` per data-plane kind (wire 0.6). */
const MIN_SEQ = {
    sensor_frame: 1,
    command_frame: 1,
    observation_frame: 0,
};
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
    if (typeof seq !== 'number' || !Number.isInteger(seq) || seq < minSeq) {
        throw new Error(`${expectedKind}: seq ${JSON.stringify(seq)} invalid (wire 0.6 requires an integer >= ${minSeq})`);
    }
}
//# sourceMappingURL=safety.js.map