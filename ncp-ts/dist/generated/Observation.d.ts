import type { Observable } from "./Observable";
/**
 * Recorded data for one record port. `times`+`values` are parallel for analog;
 * `times`+`senders` are parallel for spikes.
 */
export type Observation = {
    port: string;
    target: string;
    observable: Observable;
    times: Array<number>;
    values: Array<number>;
    senders: Array<bigint>;
    unit: string | null;
};
//# sourceMappingURL=Observation.d.ts.map