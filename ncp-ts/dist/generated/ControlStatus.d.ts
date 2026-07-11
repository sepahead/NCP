import type { Mode } from "./Mode.js";
import type { SessionRef } from "./SessionRef.js";
import type { StreamPosition } from "./StreamPosition.js";
/**
 * Controller → plant / telemetry: loop health and mode. `t` is producer-local
 * monotonic seconds and is never compared across peers.
 */
export type ControlStatus = {
    ncp_version: string;
    kind: string;
    t: number;
    mode: Mode;
    sim_time_ms: number;
    loop_latency_ms: number;
    safety_ok: boolean;
    note: string | null;
    /**
     * Wire 0.8: this status stream's own incarnation + position.
     */
    stream: StreamPosition;
    /**
     * The live session incarnation.
     */
    session: SessionRef;
    /**
     * Logical session id (transport-neutral).
     */
    session_id: string;
};
//# sourceMappingURL=ControlStatus.d.ts.map