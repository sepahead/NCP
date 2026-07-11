import type { EntityBinding } from "./EntityBinding.js";
import type { NetworkRef } from "./NetworkRef.js";
import type { RecordSpec } from "./RecordSpec.js";
import type { SimConfig } from "./SimConfig.js";
import type { StimulusSpec } from "./StimulusSpec.js";
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
     * Caller's [`CONTRACT_HASH`], carried in the handshake as an **advisory**
     * identity signal (see [`ContractStatus`]): a mismatch is logged, not rejected —
     * `ncp_version` is the hard compatibility gate. Defaults to our own hash so
     * every session advertises it; `None` (serialized `null`) = not advertised.
     */
    contract_hash: string | null;
};
//# sourceMappingURL=OpenSession.d.ts.map