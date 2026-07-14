import type { AuthorityLease } from "./AuthorityLease.js";
import type { OperationContext } from "./OperationContext.js";
import type { SessionRef } from "./SessionRef.js";
export type CloseSession = {
    ncp_version: string;
    kind: string;
    session_id: string;
    /**
     * (0.8) REQUIRED: a delayed close for an old incarnation must not close a reopen.
     */
    session: SessionRef;
    operation: OperationContext;
    authority: AuthorityLease;
};
//# sourceMappingURL=CloseSession.d.ts.map