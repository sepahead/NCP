/**
 * A typed, versioned failure reply. Error payloads are wire messages too: leaving
 * them unversioned lets a stale or misrouted peer bypass the same identity checks
 * applied to successful replies.
 */
export type ErrorFrame = {
    ncp_version: string;
    kind: string;
    error: string;
    session_id: string | null;
    request_kind: string | null;
};
//# sourceMappingURL=ErrorFrame.d.ts.map