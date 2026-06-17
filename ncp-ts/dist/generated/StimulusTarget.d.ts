import type { StimulusKind } from "./StimulusKind";
/**
 * One stimulus input port.
 */
export type StimulusTarget = {
    port: string;
    target: string;
    kind: StimulusKind;
    ids: Array<bigint>;
};
//# sourceMappingURL=StimulusTarget.d.ts.map