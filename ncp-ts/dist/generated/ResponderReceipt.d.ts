import type { OperationOutcome } from "./OperationOutcome.js";
/**
 * Authenticated responder receipt returned by a state-mutating lifecycle RPC.
 */
export type ResponderReceipt = {
    operation_id: string;
    request_digest: string;
    result_digest: string;
    outcome: OperationOutcome;
    state_version: bigint;
    committed_at_utc_ms: bigint;
    responder_principal_id: string;
    responder_entity_id: string;
};
//# sourceMappingURL=ResponderReceipt.d.ts.map