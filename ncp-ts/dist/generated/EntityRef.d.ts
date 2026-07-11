import type { EntityRole } from "./EntityRole.js";
/**
 * A hierarchical client-side entity address, e.g. `uav1/sensor/cam0`.
 */
export type EntityRef = {
    path: string;
    role: EntityRole;
    meta: {
        [key in string]: string;
    };
};
//# sourceMappingURL=EntityRef.d.ts.map