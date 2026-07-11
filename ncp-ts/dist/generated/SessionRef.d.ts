/**
 * One live session incarnation (`proto/ncp.proto` `SessionRef`). The routing
 * `session_id` (carried alongside on every session-scoped frame) remains the logical
 * name; this server-issued `generation` distinguishes one opening of that id from a
 * later reuse, so a stale-session frame is rejectable. The pair
 * `(session_id, generation)` identifies the live instance; `""` = unset.
 */
export type SessionRef = {
    generation: string;
};
//# sourceMappingURL=SessionRef.d.ts.map