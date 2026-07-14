import type { AuthorityLease } from "./AuthorityLease.js";
import type { OperationContext } from "./OperationContext.js";
import type { SessionRef } from "./SessionRef.js";
import type { StimulusFrame } from "./StimulusFrame.js";
/**
 * Advance one chunk; optional stimulus; returns an `ObservationFrame`.
 */
export type StepRequest = {
    ncp_version: string;
    kind: string;
    session_id: string;
    advance_ms: number | null;
    stimulus: StimulusFrame | null;
    /**
     * (0.8) REQUIRED: targets an open incarnation; `(session_id, generation)` live pair.
     */
    session: SessionRef;
    operation: OperationContext;
    authority: AuthorityLease;
};
//# sourceMappingURL=StepRequest.d.ts.map