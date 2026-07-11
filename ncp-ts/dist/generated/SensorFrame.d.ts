import type { ChannelValue } from "./ChannelValue.js";
import type { SessionRef } from "./SessionRef.js";
import type { StreamPosition } from "./StreamPosition.js";
/**
 * Plant → controller: the latest sensed state. Carries `seq`/`t` so a command
 * can be stamped with the sensor it was computed from (the correspondence the
 * split perception/action planes must preserve — join on `seq`, not arrival).
 *
 * Wire 0.6 (normative): publishers MUST stamp `seq` starting at `1`, strictly
 * increasing per stream. `seq = 0` is "unstamped" — receivers drop it (it is
 * also the serde default, so a default-constructed frame is not wire-legal
 * until stamped). `t` is producer-local monotonic seconds and is never compared
 * across peers.
 */
export type SensorFrame = {
    ncp_version: string;
    kind: string;
    t: number;
    frame_id: string;
    channels: {
        [key in string]: ChannelValue;
    };
    /**
     * Wire 0.8: this sensor stream's own incarnation + position — the ONLY sequence
     * loss/`LinkMonitor`/`ActionBuffer` accounting reads. The origin: no `source`;
     * downstream `command`/`observation` `source` copies THIS `stream` position.
     */
    stream: StreamPosition;
    /**
     * The live session incarnation this stream belongs to (server-issued generation).
     */
    session: SessionRef;
    /**
     * Logical session id (transport-neutral); MUST equal the routing key's session
     * segment. Carried in-payload so a non-keyed transport can interpret the frame.
     */
    session_id: string;
};
//# sourceMappingURL=SensorFrame.d.ts.map