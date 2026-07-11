import type { SessionRef } from "./SessionRef.js";
export type CloseSession = {
    ncp_version: string;
    kind: string;
    session_id: string;
    /**
     * (0.8) REQUIRED: a delayed close for an old incarnation must not close a reopen.
     */
    session: SessionRef;
};
//# sourceMappingURL=CloseSession.d.ts.map