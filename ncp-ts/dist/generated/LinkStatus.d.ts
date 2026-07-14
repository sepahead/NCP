import type { SessionRef } from "./SessionRef.js";
import type { StreamPosition } from "./StreamPosition.js";
/**
 * Link-health telemetry from the seq-gap / CUSUM monitor (published on the
 * control plane). `burst=true` flags sustained loss — a possible jam — at which
 * point the only sound response is to fail safe, not add redundancy. `t` is
 * producer-local monotonic seconds and is never compared across peers.
 */
export type LinkStatus = {
    ncp_version: string;
    kind: string;
    session_id: string;
    t: number;
    received: bigint;
    lost: bigint;
    loss_rate: number;
    burst: boolean;
    /**
     * The LinkStatus stream's own incarnation + strictly positive position —
     * validate this before trusting any reported burst/loss/high-water state.
     */
    stream: StreamPosition;
    /**
     * The MONITORED stream's epoch + forward high-water seq; absent before the first
     * valid observed frame (presence tracks `last_arrival_seq`). Its seq starts at
     * 1 and is the forward high-water.
     */
    observed_stream: StreamPosition | null;
    /**
     * F-16: seq of the last valid in-epoch ARRIVAL (`< observed_stream.seq` under
     * reordering; `==` it on forward arrival). Range starts at 1, cannot exceed the
     * observed high-water, and presence tracks `observed_stream`.
     */
    last_arrival_seq: bigint | null;
    /**
     * The live session incarnation.
     */
    session: SessionRef;
};
//# sourceMappingURL=LinkStatus.d.ts.map