import type { ChannelKind } from "./ChannelKind.js";
import type { ChannelRequirement } from "./ChannelRequirement.js";
/**
 * Declares a named channel a controller produces or consumes.
 */
export type ChannelSpec = {
    name: string;
    kind: ChannelKind;
    unit: string | null;
    size: bigint | null;
    requirement: ChannelRequirement;
    description: string | null;
};
//# sourceMappingURL=ChannelSpec.d.ts.map