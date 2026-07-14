/**
 * WebSocket transport for the NCP client. The session service replies to each
 * message in order, so requests are correlated FIFO. Use this `send` with
 * `NeuroSimClient`, or implement `Send` over another bus (e.g. Zenoh) instead.
 */
import type { Send } from './client.js';
/** Resource and deadline defaults for the experimental WebSocket binding. */
export declare const WEBSOCKET_TRANSPORT_DEFAULTS: Readonly<{
    maxPendingRequests: 128;
    maxOutboundFrameBytes: 1048576;
    connectTimeoutMs: 10000;
    writeTimeoutMs: 10000;
    readTimeoutMs: 30000;
    requestTimeoutMs: 60000;
}>;
/** Finite deadline overrides for the experimental WebSocket binding. */
export interface WebSocketNeuroSimOptions {
    connectTimeoutMs?: number;
    writeTimeoutMs?: number;
    readTimeoutMs?: number;
    requestTimeoutMs?: number;
}
export declare class WebSocketNeuroSim {
    private readonly ws;
    private readonly options;
    private readonly writeQueue;
    private readonly pendingResponses;
    private opened;
    private closeStarted;
    private writeInProgress;
    private closedError;
    private connectTimer;
    private writeTimer;
    private writePollTimer;
    constructor(url: string, options?: WebSocketNeuroSimOptions);
    private static messageOf;
    private static validTimeout;
    private static encode;
    private outstandingCount;
    private clearConnectTimer;
    private clearWriteMonitor;
    private clearRequestTimers;
    private resolveRequest;
    private rejectRequest;
    /** Reject and drop every queued request; new sends fail fast afterwards. */
    private failTransport;
    private startReadTimer;
    private monitorWriteDrain;
    private pumpWrites;
    /** Transport-agnostic bounded `send` for `NeuroSimClient`. */
    readonly send: Send;
    close(): void;
}
//# sourceMappingURL=ws.d.ts.map