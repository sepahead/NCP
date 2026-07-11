import type { EntityRef } from "./EntityRef.js";
/**
 * Binds a client entity to a stimulus or record port.
 */
export type EntityBinding = {
    entity: EntityRef;
    port: string;
    /**
     * `"stimulus"` | `"record"`.
     */
    direction: string;
};
//# sourceMappingURL=EntityBinding.d.ts.map