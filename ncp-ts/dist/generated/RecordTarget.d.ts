import type { Observable } from "./Observable";
/**
 * One recording: client `port` name ← `observable` of `target` population.
 */
export type RecordTarget = {
    port: string;
    target: string;
    observable: Observable;
    ids: Array<bigint>;
    cadence_ms: number;
};
//# sourceMappingURL=RecordTarget.d.ts.map