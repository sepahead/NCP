/**
 * Caller-provided exactly-once context for a state-mutating lifecycle RPC.
 */
export type OperationContext = {
    operation_id: string;
    request_digest: string;
    session_epoch: string;
    expected_state_version: bigint;
    deadline_utc_ms: bigint;
    retry: boolean;
};
//# sourceMappingURL=OperationContext.d.ts.map