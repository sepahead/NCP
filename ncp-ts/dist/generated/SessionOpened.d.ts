import type { GatewayAttribution } from "./GatewayAttribution.js";
import type { IdentityClaim } from "./IdentityClaim.js";
import type { SessionRef } from "./SessionRef.js";
import type { SimProvenance } from "./SimProvenance.js";
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
     * Server's [`CONTRACT_HASH`] — the reply half of the handshake (see
     * [`OpenSession::contract_hash`]). A client treats a hash difference as an
     * **advisory** ([`ContractStatus::Mismatch`], logged not rejected); the version
     * is the hard gate. `None` (serialized `null`) = not advertised.
     */
    contract_hash: string | null;
    /**
     * (0.8) Server-ISSUED session incarnation, present iff `ok`; clients echo
     * `session.generation` on every subsequent session-scoped frame.
     */
    session: SessionRef | null;
    /**
     * Authoritative state version after processing the open request. A successful
     * client uses this as the first mutation's `expected_state_version`.
     */
    state_version: bigint;
    /**
     * Authenticated responder claim bound by the transport adapter.
     */
    identity: IdentityClaim;
    security_profile: string;
    security_state_digest: string;
    gateway_permitted: boolean;
    gateway: GatewayAttribution | null;
};
//# sourceMappingURL=SessionOpened.d.ts.map