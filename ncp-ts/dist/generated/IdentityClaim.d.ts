import type { Plane } from "./Plane.js";
import type { PrincipalRole } from "./PrincipalRole.js";
/**
 * Payload claim that an authenticated transport adapter binds to its verified
 * peer identity. The claim never authenticates itself.
 */
export type IdentityClaim = {
    principal_id: string;
    entity_id: string;
    role: PrincipalRole;
    plane: Plane;
};
//# sourceMappingURL=IdentityClaim.d.ts.map