/**
 * Plant-side safety + resilience primitives — the TypeScript port of
 * `ncp-core/src/safety.rs` and `ncp-core/src/resilience.rs`, behaviour-pinned to
 * the same shared corpus (`conformance/behavior/vectors.json`, replayed by
 * `scripts/check-behavior.mjs`) as the Rust / Python / C++ peers.
 *
 * Ships so a TS plant (e.g. a browser/Tauri dev bridge) enforces the SAME
 * fail-safe semantics as every other peer instead of hand-rolling them:
 *
 * - {@link CommandWatchdog} — the `ttl_ms` deadline backstop with wire-1.0 stream
 *   discipline (`stream.seq >= 1`, strictly increasing; expiry never reopens replay).
 * - {@link ActionBuffer} — packetized-predictive-control replay: latest command
 *   + horizon, ttl-bounded, latched ESTOP, `active`-mode allowlist.
 * - {@link SafetyGovernor} — HOLD on stale sensor, latched ESTOP on geofence
 *   breach, inbound ESTOP, a reported loss burst, or sustained sensor silence;
 *   magnitude speed clamp (tick 0 and every horizon step); config fail-closed on
 *   unenforceable limits.
 * - {@link maxHorizonLen} — bound a horizon to its deadline.
 * - {@link assertWireFrame} — the wire-1.0 data-plane ingress gate (compatible
 *   `ncp_version`, stamped `stream.seq`), mirroring `ncp_core::decode_validated`.
 *
 * All numeric behaviour is IEEE-754 double math, identical to the Rust `f64`
 * reference. `seq` is a JSON-wire `number` here (see `Wire<T>` in `client.ts`).
 */
// Extension-full specifier so the EMITTED dist/safety.js resolves under plain
// node ESM (the behavior runner imports dist/*.js directly; see
// scripts/check-behavior.mjs) — tsc still type-resolves this to ./client.ts.
import { assertNcpMessage, checkVersion, hasWireControlCharacters, JSON_SAFE_INTEGER_MAX, MAX_CHANNELS, MAX_HORIZON_STEPS, NCP_VERSION, NcpVersionError, } from './client.js';
import { JSON_LIMITS, preflightJson } from './bounded-json.js';
import { canonicalDataPlaneByteLength, canonicalizeNcpMessage } from './canonical-json.js';
/** Structural (JSON-wire) view of a `CommandFrame` — the fields the safety layer
 *  reads. Accepts a full `Wire<CommandFrame>`; optional members default like the
 *  Rust wire defaults. */
/** A canonical lowercase UUIDv4 (`stream.epoch` / `session.generation`). */
const UUID_V4_SAFETY = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
/** Upper bound on an enforced command ttl (ms) — mirrors `safety.rs::MAX_TTL_MS`:
 *  the wire field is unbounded, but the plant-side deadline must stay finite. */
export const MAX_TTL_MS = 60_000;
/** Factor in the total-silence ESTOP threshold
 *  `min(factor * min(timeout, MAX_TTL_MS), MAX_TTL_MS)` (mirrors
 *  `safety.rs::LINK_LOSS_ESTOP_FACTOR`). */
export const LINK_LOSS_ESTOP_FACTOR = 20;
const POSITION_CHANNEL = 'pose_position';
const VELOCITY_CHANNEL = 'velocity_setpoint';
const POSITION_UNIT = 'm';
const VELOCITY_UNIT = 'm/s';
const SAFETY_VECTOR_WIDTH = 3;
/** A local governor failure for which no NCP wire frame exists. */
export class SafetyGovernError extends Error {
    code;
    constructor(code) {
        super(code === 'unattributable-envelope'
            ? 'safety governor latched locally but cannot emit a wire frame without a canonical attributable stream/session envelope'
            : 'safety governor latched locally because no bounded, semantically valid safe frame could be built');
        this.code = code;
        this.name = 'SafetyGovernError';
    }
}
/** Return a string's UTF-8 length, or `null` for invalid Unicode or an exceeded
 * bound. This avoids allocating an encoded copy of a hostile caller string. */
function boundedUtf8ByteLength(value, maximum) {
    let bytes = 0;
    for (const scalar of value) {
        const codePoint = scalar.codePointAt(0);
        // `for...of` combines a valid surrogate pair. A remaining surrogate is an
        // unpaired code unit and cannot appear in normative UTF-8 JSON.
        if (codePoint >= 0xd800 && codePoint <= 0xdfff)
            return null;
        bytes += codePoint <= 0x7f ? 1 : codePoint <= 0x7ff ? 2 : codePoint <= 0xffff ? 3 : 4;
        if (bytes > maximum)
            return null;
    }
    return bytes;
}
/** Rust `BTreeMap<String, _>` ordering for valid Unicode strings. UTF-8 preserves
 * Unicode scalar order, while JavaScript's default sort compares UTF-16 units. */
function compareUtf8Order(left, right) {
    const leftScalars = left[Symbol.iterator]();
    const rightScalars = right[Symbol.iterator]();
    for (;;) {
        const a = leftScalars.next();
        const b = rightScalars.next();
        if (a.done || b.done)
            return a.done === b.done ? 0 : a.done ? -1 : 1;
        const difference = a.value.codePointAt(0) - b.value.codePointAt(0);
        if (difference !== 0)
            return difference;
    }
}
function compatibleSafetyVec3(spec, expectedUnit) {
    if (spec === undefined ||
        spec.requirement !== 'required' ||
        spec.kind !== 'vec3' ||
        spec.unit !== expectedUnit) {
        return false;
    }
    const size = spec.size;
    return size == null || size === SAFETY_VECTOR_WIDTH || size === BigInt(SAFETY_VECTOR_WIDTH);
}
/**
 * Plant-side deadline backstop enforcing `CommandFrame.ttl_ms` — mirrors
 * `ncp_core::CommandWatchdog` exactly, including wire-1.0 stream discipline:
 * `seq < 1` (unstamped) NEVER refreshes liveness, and a non-advancing sequence
 * never refreshes even after expiry. Publisher restart needs a fresh declaration.
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
    /** Record an accepted command at receiver-local monotonic time `nowS`. */
    onCommand(nowS, ttlMs, seq) {
        if (!this.observeClock(nowS))
            return;
        if (!Number.isSafeInteger(seq) || seq < 1)
            return;
        if (seq <= this.lastSeq)
            return;
        this.lastSeq = seq;
        this.lastRecvS = nowS;
        // Bound the enforced ttl: non-finite -> 0 (immediately stale); clamp to the
        // finite ceiling so one command cannot keep the plant live indefinitely.
        this.ttlS = Number.isFinite(ttlMs) ? Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / 1000 : 0;
        this.clockFaulted = false;
    }
    /** Check expiry with the same receiver-local monotonic clock used by
     * {@link onCommand}. Returns true for no command, expiry, or a clock fault. */
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
/** Cap future horizon entries to the strict watchdog deadline. Entry `i` is due
 *  at `(i + 1) * horizonDtMs`, while expiry is inclusive (`elapsed >= ttlMs`), so
 *  an entry exactly on the TTL boundary is not executable. A non-finite ttl/dt
 *  (or dt <= 0) returns 0 — mirrors `resilience.rs`. */
export function maxHorizonLen(ttlMs, horizonDtMs) {
    if (!Number.isFinite(ttlMs) || !Number.isFinite(horizonDtMs) || horizonDtMs <= 0)
        return 0;
    const steps = Math.max(Math.ceil(Math.min(Math.max(ttlMs, 0), MAX_TTL_MS) / horizonDtMs) - 1, 0);
    if (!Number.isFinite(steps))
        return 0;
    return Math.min(Math.max(steps, 0), MAX_HORIZON_STEPS);
}
/**
 * Plant-side packetized-predictive-control buffer — mirrors
 * `ncp_core::ActionBuffer`: holds the latest command + horizon, replays through
 * dropouts, fails safe once expired or drained; every non-Active mode clears
 * buffered actuation before local replay checks, and ESTOP latches regardless of
 * local ordering. This is not a network ingress gate: bind authenticated actor/
 * plane and the exact current route/session generation before calling it. Sequence
 * discipline then matches {@link CommandWatchdog}.
 */
export class ActionBuffer {
    latest = null;
    recvS = 0;
    watchdog = new CommandWatchdog();
    estop = false;
    lastSeq = 0;
    // One ActionBuffer belongs to one authorized stream declaration.
    activeEpoch = null;
    retired = false;
    /** Ingest at receiver-local monotonic time `nowS`. Use the same clock for
     * {@link active} and {@link shouldHold}. */
    onCommand(nowS, command) {
        if (this.retired)
            return;
        // Within an already-admitted local context, HOLD/INIT/future non-actuating
        // modes clear buffered actuation even when locally stale or duplicate.
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
        const seq = command.stream?.seq ?? 0;
        if (!Number.isSafeInteger(seq) || seq < 1)
            return;
        // Expiry never authorizes a foreign epoch. A restarted publisher requires a
        // fresh session/declaration/ActionBuffer.
        const epoch = command.stream?.epoch ?? '';
        if (this.activeEpoch === null) {
            this.activeEpoch = epoch;
        }
        else if (this.activeEpoch !== epoch) {
            return;
        }
        if (seq <= this.lastSeq)
            return;
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
    /** Clear this local ESTOP latch and permanently retire the old session/stream
     * context. Construct a fresh ActionBuffer after the required generation cut. */
    reset() {
        this.estop = false;
        this.latest = null;
        this.recvS = 0;
        this.watchdog = new CommandWatchdog();
        this.lastSeq = 0;
        this.activeEpoch = null;
        this.retired = true;
    }
    isRetired() {
        return this.retired;
    }
    isEstopped() {
        return this.estop;
    }
    /** The setpoint channels to apply at receiver-local monotonic `nowS`, or
     * `null` to fail safe (HOLD). */
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
        const validChannelName = (name) => name.length > 0 &&
            boundedUtf8ByteLength(name, JSON_LIMITS.maxKeyBytes) !== null &&
            !hasWireControlCharacters(name);
        const channelConfigBad = !validChannelName(this.positionChannel) ||
            !validChannelName(this.velocityChannel) ||
            this.commandChannels.length > MAX_CHANNELS ||
            sensorChannels.length > MAX_CHANNELS ||
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
    /** Clear the local latch after external operator/interlock authorization. This
     * does not authenticate or restore session authority; config failure stays set. */
    reset() {
        this.estop = false;
    }
    isEstopped() {
        return this.estop;
    }
    /** Latch ESTOP when the link monitor reports a sustained loss burst. Possible
     * causes include congestion, interference, sender failure, and jamming. The
     * report does not identify the cause. The installed body executor must map the
     * ESTOP state through its content-addressed plant profile. */
    noteLink(burst) {
        if (burst)
            this.estop = true;
    }
    safetyOk() {
        return !this.estop && !this.configFailClosed;
    }
    zeroedChannels(command, tier) {
        const out = Object.create(null);
        if (tier === 'empty')
            return out;
        let channelCount = 0;
        let totalItems = 0;
        let totalStringBytes = 0;
        const rawChannels = command?.channels;
        const rawChannel = (name) => typeof rawChannels === 'object' &&
            rawChannels !== null &&
            !Array.isArray(rawChannels) &&
            Object.hasOwn(rawChannels, name)
            ? rawChannels[name]
            : undefined;
        const insertZeroedChannel = (name, requestedWidth, requestedUnit) => {
            if (typeof name !== 'string' || Object.hasOwn(out, name) || channelCount >= MAX_CHANNELS) {
                return false;
            }
            const nameBytes = boundedUtf8ByteLength(name, JSON_LIMITS.maxKeyBytes);
            if (name.length === 0 ||
                nameBytes === null ||
                hasWireControlCharacters(name) ||
                totalStringBytes + nameBytes > JSON_LIMITS.maxTotalStringBytes) {
                return false;
            }
            const remainingItems = JSON_LIMITS.maxTotalArrayItems - totalItems;
            const width = Math.min(Math.max(Math.trunc(requestedWidth), 1), JSON_LIMITS.maxArrayItems);
            if (width > remainingItems)
                return false;
            let unit = null;
            let unitBytes = 0;
            if (typeof requestedUnit === 'string') {
                const measured = boundedUtf8ByteLength(requestedUnit, JSON_LIMITS.maxStringBytes);
                if (measured !== null &&
                    totalStringBytes + nameBytes + measured <= JSON_LIMITS.maxTotalStringBytes) {
                    unit = requestedUnit;
                    unitBytes = measured;
                }
            }
            out[name] = { data: new Array(width).fill(0), unit };
            channelCount++;
            totalItems += width;
            totalStringBytes += nameBytes + unitBytes;
            return true;
        };
        // A tier is retained only when every negotiated actuator channel fits. A
        // partial negotiated map has ambiguous plant meaning.
        for (let index = 0; index < this.commandChannels.length; index++) {
            const name = this.commandChannels[index];
            if (typeof name !== 'string')
                return null;
            const raw = rawChannel(name);
            const cv = typeof raw === 'object' && raw !== null && !Array.isArray(raw)
                ? raw
                : {};
            const data = Array.isArray(cv.data) ? cv.data : [];
            if (!insertZeroedChannel(name, name === this.velocityChannel ? SAFETY_VECTOR_WIDTH : data.length, name === this.velocityChannel ? VELOCITY_UNIT : cv.unit)) {
                return null;
            }
        }
        if (tier === 'full-union' &&
            typeof rawChannels === 'object' &&
            rawChannels !== null &&
            !Array.isArray(rawChannels)) {
            const extraNames = [];
            let examined = 0;
            for (const name in rawChannels) {
                if (!Object.hasOwn(rawChannels, name))
                    continue;
                if (++examined > MAX_CHANNELS)
                    return null;
                if (Object.hasOwn(out, name))
                    continue;
                const nameBytes = boundedUtf8ByteLength(name, JSON_LIMITS.maxKeyBytes);
                if (name.length === 0 || nameBytes === null || hasWireControlCharacters(name))
                    continue;
                extraNames.push(name);
            }
            extraNames.sort(compareUtf8Order);
            for (const name of extraNames) {
                const raw = rawChannels[name];
                const cv = typeof raw === 'object' && raw !== null && !Array.isArray(raw)
                    ? raw
                    : {};
                const data = Array.isArray(cv.data) ? cv.data : [];
                if (!insertZeroedChannel(name, data.length, cv.unit))
                    return null;
            }
        }
        return out;
    }
    hasAttributableEnvelope(command) {
        const stream = command.stream;
        const generation = command.session?.generation;
        const sessionId = command.session_id;
        return (typeof stream?.epoch === 'string' &&
            UUID_V4_SAFETY.test(stream.epoch) &&
            typeof generation === 'string' &&
            UUID_V4_SAFETY.test(generation) &&
            typeof sessionId === 'string' &&
            sessionId.length > 0 &&
            boundedUtf8ByteLength(sessionId, 64) !== null &&
            !/[/*$#?]/u.test(sessionId) &&
            !/\s/u.test(sessionId) &&
            !sessionId.includes('\ufeff') &&
            !hasWireControlCharacters(sessionId));
    }
    hasBoundedProgrammaticShape(candidate) {
        let objects = 3; // command, stream, session
        let arrays = 1; // horizon (materialized by canonical projection)
        let members = 18; // command + stream + session fixed projection members
        let arrayItems = 0;
        let stringBytes = 0;
        const addString = (value, maximum = JSON_LIMITS.maxStringBytes) => {
            if (value === undefined || value === null)
                return true;
            if (typeof value !== 'string')
                return false;
            const measured = boundedUtf8ByteLength(value, maximum);
            if (measured === null || stringBytes + measured > JSON_LIMITS.maxTotalStringBytes) {
                return false;
            }
            stringBytes += measured;
            return true;
        };
        const withinCounts = () => objects <= JSON_LIMITS.maxObjects &&
            arrays <= JSON_LIMITS.maxArrays &&
            members <= JSON_LIMITS.maxTotalMembers &&
            arrayItems <= JSON_LIMITS.maxTotalArrayItems;
        const inspectChannelMap = (raw) => {
            if (typeof raw !== 'object' || raw === null || Array.isArray(raw))
                return false;
            objects++;
            let channelCount = 0;
            for (const name in raw) {
                if (!Object.hasOwn(raw, name))
                    continue;
                if (++channelCount > MAX_CHANNELS)
                    return false;
                if (!addString(name, JSON_LIMITS.maxKeyBytes))
                    return false;
                const channel = raw[name];
                if (typeof channel !== 'object' || channel === null || Array.isArray(channel))
                    return false;
                objects++;
                members += 3; // map entry plus `data` and `unit`
                const data = channel.data ?? [];
                if (!Array.isArray(data) || data.length > JSON_LIMITS.maxArrayItems)
                    return false;
                arrays++;
                arrayItems += data.length;
                if (!addString(channel.unit))
                    return false;
                if (!withinCounts())
                    return false;
            }
            return withinCounts();
        };
        if (![
            candidate.kind,
            candidate.ncp_version,
            candidate.stream?.epoch,
            candidate.source?.epoch,
            candidate.session?.generation,
            candidate.session_id,
            candidate.frame_id,
            candidate.mode,
        ].every((value) => addString(value))) {
            return false;
        }
        const authority = candidate.authority;
        if (authority !== undefined && authority !== null) {
            if (typeof authority !== 'object' || Array.isArray(authority))
                return false;
            objects++;
            members += 8;
            for (const key of [
                'session_epoch',
                'lease_id',
                'issuer_principal_id',
                'holder_principal_id',
                'holder_entity_id',
            ]) {
                if (!addString(authority[key]))
                    return false;
            }
        }
        if (candidate.source !== undefined && candidate.source !== null) {
            objects++;
            members += 2;
        }
        if (!inspectChannelMap(candidate.channels))
            return false;
        const horizon = candidate.horizon ?? [];
        if (!Array.isArray(horizon) || horizon.length > MAX_HORIZON_STEPS)
            return false;
        arrayItems += horizon.length;
        for (const step of horizon) {
            if (!inspectChannelMap(step))
                return false;
        }
        return withinCounts();
    }
    normalizeBoundedWireCandidate(candidate) {
        try {
            if (!this.hasBoundedProgrammaticShape(candidate))
                return null;
            canonicalDataPlaneByteLength(candidate, 'command_frame', JSON_LIMITS.maxFrameBytes);
            assertWireFrame(candidate, 'command_frame');
            const canonical = canonicalizeNcpMessage(candidate, 'command_frame');
            preflightJson(canonical);
            const normalized = JSON.parse(canonical);
            const nullPrototypeMap = (map) => {
                const out = Object.create(null);
                for (const name of Object.keys(map))
                    out[name] = map[name];
                return out;
            };
            normalized.channels = nullPrototypeMap(normalized.channels);
            normalized.horizon = (normalized.horizon ?? []).map(nullPrototypeMap);
            return normalized;
        }
        catch {
            return null;
        }
    }
    hasBoundedProgrammaticSensor(candidate) {
        let objects = 3; // sensor, stream, session
        let arrays = 0;
        let members = 11; // canonical sensor + stream + session members
        let arrayItems = 0;
        let stringBytes = 0;
        const addString = (value, maximum) => {
            if (value === undefined || value === null)
                return true;
            if (typeof value !== 'string')
                return false;
            const measured = boundedUtf8ByteLength(value, maximum);
            if (measured === null || stringBytes + measured > JSON_LIMITS.maxTotalStringBytes) {
                return false;
            }
            stringBytes += measured;
            return true;
        };
        if (![
            candidate.kind,
            candidate.ncp_version,
            candidate.stream?.epoch,
            candidate.session?.generation,
            candidate.session_id,
            candidate.frame_id,
        ].every((value) => addString(value, JSON_LIMITS.maxStringBytes))) {
            return false;
        }
        const raw = candidate.channels;
        if (typeof raw !== 'object' || raw === null || Array.isArray(raw))
            return false;
        objects++;
        let channelCount = 0;
        for (const name in raw) {
            if (!Object.hasOwn(raw, name))
                continue;
            if (++channelCount > MAX_CHANNELS)
                return false;
            if (!addString(name, JSON_LIMITS.maxKeyBytes))
                return false;
            const channel = raw[name];
            if (typeof channel !== 'object' || channel === null || Array.isArray(channel))
                return false;
            objects++;
            members += 3;
            const data = channel.data ?? [];
            if (!Array.isArray(data) || data.length > JSON_LIMITS.maxArrayItems)
                return false;
            arrays++;
            arrayItems += data.length;
            if (!addString(channel.unit, JSON_LIMITS.maxStringBytes)) {
                return false;
            }
            if (objects > JSON_LIMITS.maxObjects ||
                arrays > JSON_LIMITS.maxArrays ||
                members > JSON_LIMITS.maxTotalMembers ||
                arrayItems > JSON_LIMITS.maxTotalArrayItems) {
                return false;
            }
        }
        return true;
    }
    isAdmittedSensor(candidate) {
        try {
            if (!this.hasBoundedProgrammaticSensor(candidate))
                return false;
            canonicalDataPlaneByteLength(candidate, 'sensor_frame', JSON_LIMITS.maxFrameBytes);
            assertWireFrame(candidate, 'sensor_frame');
            preflightJson(canonicalizeNcpMessage(candidate, 'sensor_frame'));
            return true;
        }
        catch {
            return false;
        }
    }
    safeFrame(command, mode) {
        const raw = command;
        const rawStream = command.stream;
        // Preserve the exact publisher epoch. Sequence is position, not routing
        // identity: normalize an invalid position to 1 so a fail-safe remains
        // attributable without creating a different stream.
        const stream = {
            epoch: rawStream.epoch,
            seq: typeof rawStream.seq === 'number' &&
                Number.isSafeInteger(rawStream.seq) &&
                rawStream.seq >= 1 &&
                rawStream.seq <= JSON_SAFE_INTEGER_MAX
                ? rawStream.seq
                : 1,
        };
        const t = typeof raw.t === 'number' &&
            Number.isFinite(raw.t) &&
            Math.abs(raw.t) <= JSON_LIMITS.maxFiniteNumberMagnitude
            ? raw.t
            : 0;
        const frameIdBytes = typeof raw.frame_id === 'string'
            ? boundedUtf8ByteLength(raw.frame_id, JSON_LIMITS.maxStringBytes)
            : null;
        const frameId = typeof raw.frame_id === 'string' &&
            raw.frame_id.length > 0 &&
            frameIdBytes !== null &&
            !hasWireControlCharacters(raw.frame_id)
            ? raw.frame_id
            : 'world';
        const rawSource = command.source;
        const sourceT = command.source_t === undefined ? 0 : command.source_t;
        const sourceValid = rawSource != null &&
            typeof rawSource.epoch === 'string' &&
            UUID_V4_SAFETY.test(rawSource.epoch) &&
            typeof rawSource.seq === 'number' &&
            Number.isSafeInteger(rawSource.seq) &&
            rawSource.seq >= 1 &&
            rawSource.seq <= JSON_SAFE_INTEGER_MAX &&
            typeof sourceT === 'number' &&
            Number.isFinite(sourceT) &&
            Math.abs(sourceT) <= JSON_LIMITS.maxFiniteNumberMagnitude;
        for (const tier of ['full-union', 'negotiated-only', 'empty']) {
            try {
                const channels = this.zeroedChannels(command, tier);
                if (channels === null)
                    continue;
                const candidate = {
                    kind: 'command_frame',
                    ncp_version: NCP_VERSION,
                    stream,
                    source: sourceValid ? { epoch: rawSource.epoch, seq: rawSource.seq } : null,
                    source_t: sourceValid ? sourceT : 0,
                    session: { generation: command.session.generation },
                    session_id: command.session_id,
                    t,
                    frame_id: frameId,
                    mode,
                    ttl_ms: 200,
                    channels,
                    horizon: [],
                    horizon_dt_ms: null,
                };
                const normalized = this.normalizeBoundedWireCandidate(candidate);
                if (normalized !== null)
                    return normalized;
            }
            catch {
                continue;
            }
        }
        this.estop = true;
        throw new SafetyGovernError('bounded-safe-frame');
    }
    /**
     * Apply safety to `command` against the latest `sensor`. `nowS`/`lastSensorS`
     * must be readings from the same receiver-local monotonic clock. A successful
     * call returns an attributable, canonical, bounded wire-shape candidate. The
     * standalone governor has no publisher allocator or stream high-water and does
     * not prove that the returned position is fresh. ESTOP latches until
     * {@link reset} clears the local latch.
     *
     * @throws {SafetyGovernError} after latching when the command envelope is not
     * attributable or no deterministic safe-frame tier has a bounded valid wire
     * shape. The caller or transport separately supplies and admits the owning
     * publisher's next fresh position, route, and live session generation.
     */
    govern(command, sensor, nowS, lastSensorS) {
        if (!this.hasAttributableEnvelope(command)) {
            this.estop = true;
            throw new SafetyGovernError('unattributable-envelope');
        }
        // Latched ESTOP dominates everything until an authorized operator resets it.
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
        if (validatedSensor !== null) {
            if (!this.isAdmittedSensor(validatedSensor) ||
                validatedSensor.session?.generation !== command.session?.generation ||
                validatedSensor.session_id !== command.session_id) {
                validatedSensor = null;
            }
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
        // command must never hide sustained sensor silence or an already-breached
        // boundary.
        // Only `active` may actuate (defense-in-depth with ActionBuffer's allowlist).
        if (command.mode !== 'active')
            return this.safeFrame(command, 'hold');
        // Bound and canonicalize the typed input before cloning. Programmatic callers
        // do not necessarily pass through the raw bounded-JSON ingress gate.
        const admitted = this.normalizeBoundedWireCandidate(command);
        if (admitted === null)
            return this.safeFrame(command, 'hold');
        const out = structuredClone(admitted);
        const outHorizon = out.horizon ?? [];
        out.horizon = outHorizon;
        const maxSpeed = this.limits.max_speed_mps;
        if (maxSpeed != null && maxSpeed > 0) {
            if (!this.clampVelocity(out.channels, maxSpeed))
                return this.safeFrame(command, 'hold');
            // Clamp every predictive horizon step too; truncate at the first
            // unclampable step so replay HOLDs rather than emitting unbounded output.
            let safeLen = outHorizon.length;
            for (let i = 0; i < outHorizon.length; i++) {
                if (!this.clampVelocity(outHorizon[i], maxSpeed)) {
                    // An empty horizon means legacy "replay tick 0 until ttl", not
                    // "drain after tick 0". Reject instead of truncating index 0 to an
                    // actively replayed command.
                    if (i === 0)
                        return this.safeFrame(command, 'hold');
                    safeLen = i;
                    break;
                }
            }
            outHorizon.length = safeLen;
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
        // A programmatic object can satisfy field semantics while its serialized
        // form exceeds the whole-frame budget (or grows during normalization). Never
        // return an invalid or over-budget Active frame; replace it with a bounded HOLD.
        return this.normalizeBoundedWireCandidate(out) ?? this.safeFrame(command, 'hold');
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
 * Wire-1.0 data-plane ingress gate — the TS mirror of
 * `ncp_core::decode_validated`: the frame must carry the expected `kind`, a
 * COMPATIBLE `ncp_version` (absent/incompatible throws {@link NcpVersionError} —
 * never coerced to ours), and a stamped `stream.seq >= 1` for every kind. The
 * observation pull/RPC form uses `source` absence, never sequence zero. Call this
 * on every frame read off a data plane and DROP
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
    const stream = frame.stream;
    const seq = stream?.seq;
    if (typeof seq !== 'number' || !Number.isSafeInteger(seq) || seq < 1) {
        throw new Error(`${expectedKind}: stream.seq ${JSON.stringify(seq)} must be a safe integer >= 1`);
    }
    if (typeof stream?.epoch !== 'string' || !UUID_V4_SAFETY.test(stream.epoch)) {
        throw new Error(`${expectedKind}.stream.epoch must be a canonical lowercase UUIDv4`);
    }
    const session = frame.session;
    if (typeof session?.generation !== 'string' || !UUID_V4_SAFETY.test(session.generation)) {
        throw new Error(`${expectedKind}.session.generation must be a canonical lowercase UUIDv4`);
    }
    if (typeof frame.session_id !== 'string' || frame.session_id.length === 0) {
        throw new Error(`${expectedKind}.session_id must be a non-empty string`);
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