import type { Mode } from "./Mode.js";
/**
 * Controller → plant / telemetry: loop health and mode. `t` is producer-local
 * monotonic seconds and is never compared across peers.
 */
export type ControlStatus = {
    ncp_version: string;
    kind: string;
    seq: bigint;
    t: number;
    mode: Mode;
    sim_time_ms: number;
    loop_latency_ms: number;
    safety_ok: boolean;
    note: string | null;
};
//# sourceMappingURL=ControlStatus.d.ts.map