import type { ChannelValue } from "./ChannelValue.js";
/**
 * The values to inject this step (keyed by stimulus port). `t` is
 * producer-local monotonic seconds and is never compared across peers.
 */
export type StimulusFrame = {
    ncp_version: string;
    kind: string;
    session_id: string;
    t: number;
    values: {
        [key in string]: ChannelValue;
    };
};
//# sourceMappingURL=StimulusFrame.d.ts.map