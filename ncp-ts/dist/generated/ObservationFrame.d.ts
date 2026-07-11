import type { Observation } from "./Observation.js";
/**
 * The returned neural data, keyed by a unique record-series name. The nested
 * `Observation.port` identifies the negotiated record port; distinct
 * `recordable` series from one port therefore remain representable. `t` is
 * producer-local monotonic seconds (the plane form echoes `SensorFrame.t`);
 * `sim_time_ms` is authoritative simulation time.
 */
export type ObservationFrame = {
    ncp_version: string;
    kind: string;
    session_id: string;
    /**
     * Wire 0.6 (normative): a frame **published on the observation plane** MUST
     * echo the driving `SensorFrame.seq` (`>= 1`), so a split-plane observer can
     * align `(V,L,D,A)` on `seq` (not arrival time) — an unstamped plane frame
     * forces observers into a degraded recency-only join. `0` is reserved for
     * the pure pull/sim-service RPC reply path (no controller seq exists there).
     */
    seq: bigint;
    t: number;
    sim_time_ms: number;
    records: {
        [key in string]: Observation;
    };
    calibrated_posterior: boolean;
    is_simulation_output: boolean;
};
//# sourceMappingURL=ObservationFrame.d.ts.map