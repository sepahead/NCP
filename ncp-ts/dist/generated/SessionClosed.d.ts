import type { SessionRef } from "./SessionRef.js";
export type SessionClosed = {
    ncp_version: string;
    kind: string;
    session_id: string;
    ok: boolean;
    /**
     * (0.8) the incarnation this close concerns; a delayed reply must attribute to it.
     */
    session: SessionRef;
};
//# sourceMappingURL=SessionClosed.d.ts.map