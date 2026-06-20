import type { EntityBinding } from "./EntityBinding";
import type { NetworkRef } from "./NetworkRef";
import type { RecordSpec } from "./RecordSpec";
import type { SimConfig } from "./SimConfig";
import type { StimulusSpec } from "./StimulusSpec";
/**
 * Request a simulation: declare what to record and what to stimulate.
 */
export type OpenSession = {
    ncp_version: string;
    kind: string;
    session_id: string;
    network: NetworkRef;
    record: RecordSpec;
    stimulus: StimulusSpec;
    sim: SimConfig;
    bindings: Array<EntityBinding>;
    /**
     * Caller's [`CONTRACT_HASH`], carried in the handshake so a peer can
     * fail-closed-reject a post-agreement schema mutation. Defaults to our own
     * hash so every session advertises it; `None` (serialized `null`) = not
     * advertised, accepted within a compatible `ncp_version`.
     */
    contract_hash: string | null;
};
//# sourceMappingURL=OpenSession.d.ts.map