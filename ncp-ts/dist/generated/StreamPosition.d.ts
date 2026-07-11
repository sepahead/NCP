/**
 * One exact position in ONE logical stream incarnation (`proto/ncp.proto`
 * `StreamPosition`). Wire 0.8 splits the old overloaded top-level `seq` into a
 * frame's OWN [`stream`](SensorFrame) — the only sequence loss/`LinkMonitor`/
 * `ActionBuffer` accounting reads — and a `source` referencing the frame that drove
 * it (correlation only, never loss accounting).
 *
 * `epoch` is an opaque per-incarnation id (canonical lowercase UUIDv4), compared for
 * EQUALITY ONLY — never ordered, never a timestamp. `seq` starts at 1 per epoch,
 * strictly increasing, within `1 ..= JSON_SAFE_INTEGER_MAX`. The `""`/`0` default is
 * "unset" and is not wire-legal until stamped (mirrors the retired `seq` discipline).
 */
export type StreamPosition = {
    epoch: string;
    seq: bigint;
};
//# sourceMappingURL=StreamPosition.d.ts.map