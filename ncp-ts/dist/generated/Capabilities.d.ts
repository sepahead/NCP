import type { ChannelSpec } from "./ChannelSpec.js";
import type { GatewayAttribution } from "./GatewayAttribution.js";
import type { IdentityClaim } from "./IdentityClaim.js";
import type { Role } from "./Role.js";
import type { SafetyLimits } from "./SafetyLimits.js";
/**
 * Handshake: who the controller is and what it speaks.
 */
export type Capabilities = {
    ncp_version: string;
    kind: string;
    controller_id: string;
    role: Role;
    control_rate_hz: number;
    sensor_channels: Array<ChannelSpec>;
    command_channels: Array<ChannelSpec>;
    codec_id: string | null;
    safety: SafetyLimits;
    identity: IdentityClaim;
    security_profile: string;
    security_state_digest: string;
    stable_capabilities: Array<string>;
    /**
     * `false` means native 1.0 only. A gateway is never inferred from absence.
     */
    gateway_permitted: boolean;
    plant_profile_digest: string | null;
    gateway: GatewayAttribution | null;
};
//# sourceMappingURL=Capabilities.d.ts.map