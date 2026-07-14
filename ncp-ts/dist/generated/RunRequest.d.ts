import type { AuthorityLease } from "./AuthorityLease.js";
import type { OperationContext } from "./OperationContext.js";
import type { SessionRef } from "./SessionRef.js";
import type { StimulusFrame } from "./StimulusFrame.js";
/**
 * Batch: advance `duration_ms` holding a stimulus; returns an `ObservationFrame`.
 */
export type RunRequest = {
    ncp_version: string;
    kind: string;
    session_id: string;
    duration_ms: number;
    stimulus: StimulusFrame | null;
    /**
     * (0.8) REQUIRED: targets an open incarnation; `(session_id, generation)` live pair.
     */
    session: SessionRef;
    operation: OperationContext;
    authority: AuthorityLease;
};
//# sourceMappingURL=RunRequest.d.ts.map