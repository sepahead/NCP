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
import type { Mode, SafetyLimits, Capabilities } from './generated/index.js';
/** JSON-wire channel map: `{ name: { data, unit } }`. */
export interface WireChannels {
    [name: string]: {
        data: number[];
        unit?: string | null;
    };
}
/** Structural view of a `StreamPosition` — one frame's stream identity + position. */
export interface StreamPositionLike {
    epoch?: string;
    seq?: number;
}
/** Structural view of a `SessionRef` — one live session incarnation. */
export interface SessionRefLike {
    generation?: string;
}
export interface CommandLike {
    kind?: string;
    ncp_version?: string;
    stream?: StreamPositionLike;
    source?: StreamPositionLike | null;
    source_t?: number;
    session?: SessionRefLike;
    session_id?: string;
    t?: number;
    frame_id?: string;
    mode: Mode;
    ttl_ms?: number;
    channels: WireChannels;
    horizon?: WireChannels[];
    horizon_dt_ms?: number | null;
}
/** Structural (JSON-wire) view of a `SensorFrame` for the governor. */
export interface SensorLike {
    kind?: string;
    ncp_version?: string;
    stream?: StreamPositionLike;
    session?: SessionRefLike;
    session_id?: string;
    t?: number;
    frame_id?: string;
    channels: WireChannels;
}
/** Upper bound on an enforced command ttl (ms) — mirrors `safety.rs::MAX_TTL_MS`:
 *  the wire field is unbounded, but the plant-side deadline must stay finite. */
export declare const MAX_TTL_MS = 60000;
/** How many consecutive `command_timeout_ms` deadlines of TOTAL sensor silence
 *  escalate the non-latching staleness HOLD to a latched ESTOP (mirrors
 *  `safety.rs::LINK_LOSS_ESTOP_FACTOR`). */
export declare const LINK_LOSS_ESTOP_FACTOR = 20;
/**
 * Plant-side deadline backstop enforcing `CommandFrame.ttl_ms` — mirrors
 * `ncp_core::CommandWatchdog` exactly, including the wire-0.6 seq discipline:
 * `seq < 1` (unstamped) NEVER refreshes liveness; a duplicate never refreshes; a
 * strictly-lower `seq` re-anchors a restarted stream only once the stream is
 * already expired (the plant is safely holding).
 */
export declare class CommandWatchdog {
    private lastRecvS;
    private ttlS;
    private lastSeq;
    private clockHighWaterS;
    private clockFaulted;
    private observeClock;
    /** Record an accepted command at local time `nowS` with its `ttl_ms` and `seq`. */
    onCommand(nowS: number, ttlMs: number, seq: number): void;
    /** True if the plant must fail safe to HOLD (no command, expired, bad clock). */
    shouldHold(nowS: number): boolean;
}
/** Cap a horizon length to its deadline (`N <= ttl_ms / horizon_dt_ms`); a
 *  non-finite ttl/dt (or dt <= 0) returns 0 — mirrors `resilience.rs`. */
export declare function maxHorizonLen(ttlMs: number, horizonDtMs: number): number;
/**
 * Plant-side packetized-predictive-control buffer — mirrors
 * `ncp_core::ActionBuffer`: holds the latest command + horizon, replays through
 * dropouts, fails safe once expired or drained; every non-Active mode clears
 * buffered actuation before replay checks, and ESTOP latches regardless of
 * ordering or stamping (a fail-safe is never dropped); wire-0.6 seq discipline
 * as in {@link CommandWatchdog}.
 */
export declare class ActionBuffer {
    private latest;
    private recvS;
    private watchdog;
    private estop;
    private lastSeq;
    onCommand(nowS: number, command: CommandLike): void;
    /** Clear a latched ESTOP and discard all pre-ESTOP command state. A fresh
     * validated Active command is required before actuation resumes. */
    reset(): void;
    isEstopped(): boolean;
    /** The setpoint channels to apply at `nowS`, or `null` to fail safe (HOLD). */
    active(nowS: number): WireChannels | null;
    shouldHold(nowS: number): boolean;
}
/**
 * The action-plane safety governor — mirrors `ncp_core::SafetyGovernor` (HOLD on
 * stale/absent sensor, latched ESTOP on geofence breach / inbound ESTOP / total
 * silence, magnitude speed clamp on tick 0 and every horizon step, geofence
 * horizon look-ahead, config fail-closed on unenforceable/non-finite limits).
 * Behaviour is pinned by the shared `govern` corpus vectors.
 */
export declare class SafetyGovernor {
    limits: Pick<SafetyLimits, 'command_timeout_ms'> & Partial<SafetyLimits>;
    private readonly positionChannel;
    private readonly velocityChannel;
    private commandChannels;
    private readonly positionContractValid;
    private readonly velocityContractValid;
    private estop;
    private configFailClosed;
    constructor(limits: Pick<SafetyLimits, 'command_timeout_ms'> & Partial<SafetyLimits>, positionChannel?: string, velocityChannel?: string, commandChannels?: string[], sensorChannels?: string[], positionContractValid?: boolean, velocityContractValid?: boolean);
    /** Resolve explicit canonical safety channels from negotiated `Capabilities`.
     *  Enabled limits require width-3 `vec3` specs in canonical SI units; declaration
     *  order never selects a safety input. Mirrors Rust `from_capabilities`. */
    static fromCapabilities(caps: {
        command_channels: Capabilities['command_channels'];
        sensor_channels: Capabilities['sensor_channels'];
        safety: SafetyLimits;
    }): SafetyGovernor;
    /** Clear a latched ESTOP (supervisor authority; config fail-closed is NOT cleared). */
    reset(): void;
    isEstopped(): boolean;
    /** Latch ESTOP when the link monitor reports a sustained loss burst (a jam). */
    noteLink(burst: boolean): void;
    safetyOk(): boolean;
    private zeroedChannels;
    private safeFrame;
    /**
     * Apply safety to `command` against the latest `sensor`. `nowS`/`lastSensorS`
     * are wall-clock seconds (the plant's own clock). Returns a fresh frame; ESTOP
     * latches (call {@link reset} to clear).
     */
    govern(command: CommandLike, sensor: SensorLike | null, nowS: number, lastSensorS: number | null): CommandLike;
    private enforceGeofenceTrajectory;
    private advanceGeofencePosition;
    /** Magnitude-clamp the velocity channel in place; `false` = unenforceable
     *  (absent channel / wrong unit or width / non-finite magnitude) and the caller
     *  must fail safe. */
    private clampVelocity;
    private validSafetyVector;
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
export declare function assertWireFrame(frame: Record<string, unknown>, expectedKind: 'sensor_frame' | 'command_frame' | 'observation_frame'): void;
//# sourceMappingURL=safety.d.ts.map