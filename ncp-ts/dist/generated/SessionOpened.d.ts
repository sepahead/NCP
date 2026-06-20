import type { SimProvenance } from "./SimProvenance";
/**
 * Ack of `open_session` with resolved sizes and provenance.
 */
export type SessionOpened = {
    ncp_version: string;
    kind: string;
    session_id: string;
    ok: boolean;
    backend: string;
    resolved: {
        [key in string]: bigint;
    };
    provenance: SimProvenance | null;
    error: string | null;
    /**
     * Server's [`CONTRACT_HASH`] — the reply half of the symmetric handshake (see
     * [`OpenSession::contract_hash`]). A client rejects a `SessionOpened` whose
     * hash does not match its own. `None` (serialized `null`) = not advertised.
     */
    contract_hash: string | null;
};
//# sourceMappingURL=SessionOpened.d.ts.map