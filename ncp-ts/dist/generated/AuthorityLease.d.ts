/**
 * One bounded authority term for a single session incarnation. UTC timestamps
 * are receipt/audit bounds; receivers derive a local monotonic expiry deadline.
 */
export type AuthorityLease = {
    session_epoch: string;
    term: bigint;
    lease_id: string;
    issuer_principal_id: string;
    holder_principal_id: string;
    holder_entity_id: string;
    issued_at_utc_ms: bigint;
    expires_at_utc_ms: bigint;
};
//# sourceMappingURL=AuthorityLease.d.ts.map