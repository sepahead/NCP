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
    /**
     * Local elapsed time from the start of one controller tick through final
     * safety governance. This excludes transport-slot admission, network
     * delivery, body admission, body disposition, physical effect, and
     * observation delivery.
     */
    loop_latency_ms: number;
    /**
     * Publisher-reported logical health. The reference loop clears this for a
     * latched ESTOP, configuration fault, invalid rate or clock, or retired
     * controller. A transient HOLD can coexist with `true`. This field does not
     * certify physical safety or achieved effect.
     */
    safety_ok: boolean;
    note: string | null;
    /**
     * This status stream's own incarnation + strictly positive position. A
     * publisher never repeats the JSON-safe maximum; it becomes silent until a
     * fresh declaration mints another epoch.
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