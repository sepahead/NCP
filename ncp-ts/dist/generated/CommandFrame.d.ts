import type { ChannelValue } from "./ChannelValue.js";
import type { Mode } from "./Mode.js";
import type { SessionRef } from "./SessionRef.js";
import type { StreamPosition } from "./StreamPosition.js";
/**
 * Controller → plant: the proposed actuation, with `mode`/`ttl_ms` safety
 * metadata.
 *
 * Wire 0.6 (normative): `seq` MUST echo the originating `SensorFrame.seq`
 * (`>= 1`, strictly increasing per stream) — the split-plane V↔A join depends
 * on it, and the plant's anti-replay/anti-stale layers (`ActionBuffer` /
 * `CommandWatchdog`) reject `seq < 1` outright: the pre-0.6 "`seq == 0` always
 * accepted" escape hatch is REMOVED (it let a default-constructed or all-zeros
 * frame refresh liveness and bypass replay rejection on the action plane). `t`
 * echoes the driving `SensorFrame.t` in producer-local monotonic seconds.
 */
export type CommandFrame = {
    ncp_version: string;
    kind: string;
    t: number;
    frame_id: string;
    mode: Mode;
    ttl_ms: number;
    channels: {
        [key in string]: ChannelValue;
    };
    /**
     * Packetized predictive control: future setpoints. `channels` is tick 0;
     * `horizon[i]` applies at tick i+1, spaced `horizon_dt_ms` apart. The
     * actuator replays these through dropouts (see `ActionBuffer`), bounded by
     * `ttl_ms`. Empty = legacy single-step command. Backward compatible: a
     * consumer that ignores `horizon` still reads `channels` (tick 0).
     */
    horizon: Array<{
        [key in string]: ChannelValue;
    }>;
    horizon_dt_ms: number | null;
    /**
     * Wire 0.8: this command stream's own incarnation + position — the sequence
     * `LinkMonitor`/`ActionBuffer` read for loss/dedup/supersession.
     */
    stream: StreamPosition;
    /**
     * The driving `SensorFrame.stream` (correlation only; never loss accounting).
     * Present for a closed-loop Active command; omitted for negotiated open-loop.
     */
    source: StreamPosition | null;
    /**
     * The driving `SensorFrame.t`, for source-age checks; `0.0` = unset.
     */
    source_t: number;
    /**
     * The live session incarnation this command stream belongs to.
     */
    session: SessionRef;
    /**
     * Logical session id (transport-neutral); MUST equal the routing key's session.
     */
    session_id: string;
};
//# sourceMappingURL=CommandFrame.d.ts.map