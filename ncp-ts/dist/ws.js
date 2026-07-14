/**
 * WebSocket transport for the NCP client. The session service replies to each
 * message in order, so requests are correlated FIFO. Use this `send` with
 * `NeuroSimClient`, or implement `Send` over another bus (e.g. Zenoh) instead.
 */
import { BoundedJsonError, JSON_LIMITS, parseBoundedJson, preflightJson, } from './bounded-json.js';
const MAX_TIMER_DELAY_MS = 2_147_483_647;
const WRITE_DRAIN_POLL_MS = 10;
/** Resource and deadline defaults for the experimental WebSocket binding. */
export const WEBSOCKET_TRANSPORT_DEFAULTS = Object.freeze({
    maxPendingRequests: 128,
    maxOutboundFrameBytes: JSON_LIMITS.maxFrameBytes,
    connectTimeoutMs: 10_000,
    writeTimeoutMs: 10_000,
    readTimeoutMs: 30_000,
    requestTimeoutMs: 60_000,
});
export class WebSocketNeuroSim {
    ws;
    options;
    writeQueue = [];
    pendingResponses = [];
    opened = false;
    closeStarted = false;
    writeInProgress = false;
    closedError = null;
    connectTimer = null;
    writeTimer = null;
    writePollTimer = null;
    constructor(url, options = {}) {
        this.options = {
            connectTimeoutMs: WebSocketNeuroSim.validTimeout(options.connectTimeoutMs, WEBSOCKET_TRANSPORT_DEFAULTS.connectTimeoutMs, 'connectTimeoutMs'),
            writeTimeoutMs: WebSocketNeuroSim.validTimeout(options.writeTimeoutMs, WEBSOCKET_TRANSPORT_DEFAULTS.writeTimeoutMs, 'writeTimeoutMs'),
            readTimeoutMs: WebSocketNeuroSim.validTimeout(options.readTimeoutMs, WEBSOCKET_TRANSPORT_DEFAULTS.readTimeoutMs, 'readTimeoutMs'),
            requestTimeoutMs: WebSocketNeuroSim.validTimeout(options.requestTimeoutMs, WEBSOCKET_TRANSPORT_DEFAULTS.requestTimeoutMs, 'requestTimeoutMs'),
        };
        this.ws = new WebSocket(url);
        // Canonical NCP is a JSON text protocol. Selecting ArrayBuffer for any
        // unexpected binary frame lets us inspect its byteLength without a copy and
        // reject it explicitly; a Blob would otherwise hide its size behind async I/O.
        this.ws.binaryType = 'arraybuffer';
        this.ws.onopen = () => {
            if (this.closedError)
                return;
            this.opened = true;
            this.clearConnectTimer();
            this.pumpWrites();
        };
        this.ws.onmessage = (event) => {
            const request = this.pendingResponses.shift();
            if (!request) {
                this.failTransport(new Error('unsolicited NCP WebSocket reply'), true);
                return;
            }
            try {
                // Parse inside the handler. A malformed frame makes FIFO correlation
                // unknowable, so it terminates the transport rather than allowing any
                // later frame to satisfy a different request.
                if (typeof event.data !== 'string') {
                    if (event.data instanceof ArrayBuffer && event.data.byteLength > JSON_LIMITS.maxFrameBytes) {
                        throw new BoundedJsonError('NCP-LIMIT-001', JSON_LIMITS.maxFrameBytes, 'binary WebSocket reply exceeds the JSON frame byte limit');
                    }
                    throw new Error('binary WebSocket replies are not canonical NCP JSON text');
                }
                this.resolveRequest(request, parseBoundedJson(event.data));
            }
            catch (error) {
                this.pendingResponses.unshift(request);
                this.failTransport(new Error(`NCP reply was not valid JSON: ${WebSocketNeuroSim.messageOf(error)}`), true);
            }
        };
        this.ws.onerror = () => {
            this.failTransport(new Error('NCP WebSocket error'), true);
        };
        this.ws.onclose = () => {
            this.closeStarted = true;
            this.failTransport(new Error('NCP WebSocket closed'), false);
        };
        this.connectTimer = setTimeout(() => {
            this.failTransport(new Error(`NCP WebSocket connect timeout after ${this.options.connectTimeoutMs} ms`), true);
        }, this.options.connectTimeoutMs);
    }
    static messageOf(error) {
        return error instanceof Error ? error.message : String(error);
    }
    static validTimeout(value, defaultValue, name) {
        const timeout = value ?? defaultValue;
        if (!Number.isSafeInteger(timeout) || timeout <= 0 || timeout > MAX_TIMER_DELAY_MS) {
            throw new RangeError(`${name} must be a positive timer-safe integer`);
        }
        return timeout;
    }
    static encode(message) {
        try {
            const payload = JSON.stringify(message);
            if (typeof payload !== 'string') {
                throw new TypeError('message did not serialize to a JSON object');
            }
            preflightJson(payload);
            return payload;
        }
        catch (error) {
            throw new Error(`NCP outbound message was not valid bounded JSON: ${WebSocketNeuroSim.messageOf(error)}`);
        }
    }
    outstandingCount() {
        return this.writeQueue.length + this.pendingResponses.length;
    }
    clearConnectTimer() {
        if (this.connectTimer !== null)
            clearTimeout(this.connectTimer);
        this.connectTimer = null;
    }
    clearWriteMonitor() {
        if (this.writeTimer !== null)
            clearTimeout(this.writeTimer);
        if (this.writePollTimer !== null)
            clearTimeout(this.writePollTimer);
        this.writeTimer = null;
        this.writePollTimer = null;
        this.writeInProgress = false;
    }
    clearRequestTimers(request) {
        if (request.requestTimer !== null)
            clearTimeout(request.requestTimer);
        if (request.readTimer !== null)
            clearTimeout(request.readTimer);
        request.requestTimer = null;
        request.readTimer = null;
    }
    resolveRequest(request, reply) {
        if (request.settled)
            return;
        request.settled = true;
        this.clearRequestTimers(request);
        request.resolve(reply);
    }
    rejectRequest(request, error) {
        if (request.settled)
            return;
        request.settled = true;
        this.clearRequestTimers(request);
        request.reject(error);
    }
    /** Reject and drop every queued request; new sends fail fast afterwards. */
    failTransport(error, closeSocket) {
        if (!this.closedError)
            this.closedError = error;
        this.opened = false;
        this.clearConnectTimer();
        this.clearWriteMonitor();
        const failure = this.closedError;
        for (const request of this.writeQueue.splice(0))
            this.rejectRequest(request, failure);
        for (const request of this.pendingResponses.splice(0))
            this.rejectRequest(request, failure);
        if (closeSocket && !this.closeStarted) {
            this.closeStarted = true;
            try {
                this.ws.close();
            }
            catch {
                // The transport is already terminal; a close exception cannot restore it.
            }
        }
    }
    startReadTimer(request) {
        request.readTimer = setTimeout(() => {
            // Once bytes have been sent, retaining the socket would let a late FIFO
            // reply satisfy a later request. Terminate the whole transport instead.
            this.failTransport(new Error(`NCP WebSocket read timeout after ${this.options.readTimeoutMs} ms`), true);
        }, this.options.readTimeoutMs);
    }
    monitorWriteDrain() {
        if (this.writeInProgress || this.closedError)
            return;
        this.writeInProgress = true;
        this.writeTimer = setTimeout(() => {
            this.failTransport(new Error(`NCP WebSocket write timeout after ${this.options.writeTimeoutMs} ms`), true);
        }, this.options.writeTimeoutMs);
        const poll = () => {
            if (this.closedError)
                return;
            if (this.ws.bufferedAmount === 0) {
                this.clearWriteMonitor();
                this.pumpWrites();
                return;
            }
            this.writePollTimer = setTimeout(poll, Math.min(WRITE_DRAIN_POLL_MS, this.options.writeTimeoutMs));
        };
        this.writePollTimer = setTimeout(poll, Math.min(WRITE_DRAIN_POLL_MS, this.options.writeTimeoutMs));
    }
    pumpWrites() {
        if (!this.opened || this.closedError || this.writeInProgress)
            return;
        while (this.writeQueue.length > 0 && !this.closedError) {
            const request = this.writeQueue.shift();
            if (!request || request.settled)
                continue;
            this.pendingResponses.push(request);
            try {
                this.ws.send(request.payload);
                request.payload = '';
            }
            catch (error) {
                this.failTransport(new Error(`NCP send failed: ${WebSocketNeuroSim.messageOf(error)}`), true);
                return;
            }
            if (!request.settled)
                this.startReadTimer(request);
            if (this.ws.bufferedAmount > 0) {
                this.monitorWriteDrain();
                return;
            }
        }
    }
    /** Transport-agnostic bounded `send` for `NeuroSimClient`. */
    send = (message) => {
        if (this.closedError)
            return Promise.reject(this.closedError);
        if (this.outstandingCount() >= WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests) {
            return Promise.reject(new Error(`NCP WebSocket pending request capacity exceeded (${WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests})`));
        }
        let payload;
        try {
            payload = WebSocketNeuroSim.encode(message);
        }
        catch (error) {
            return Promise.reject(error instanceof Error
                ? error
                : new Error(`NCP outbound encoding failed: ${WebSocketNeuroSim.messageOf(error)}`));
        }
        // A hostile `toJSON` can re-enter `send`, so recheck capacity and terminal
        // state after serialization before reserving the FIFO position.
        if (this.closedError)
            return Promise.reject(this.closedError);
        if (this.outstandingCount() >= WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests) {
            return Promise.reject(new Error(`NCP WebSocket pending request capacity exceeded (${WEBSOCKET_TRANSPORT_DEFAULTS.maxPendingRequests})`));
        }
        return new Promise((resolve, reject) => {
            const request = {
                payload,
                resolve,
                reject,
                requestTimer: null,
                readTimer: null,
                settled: false,
            };
            request.requestTimer = setTimeout(() => {
                this.failTransport(new Error(`NCP WebSocket request timeout after ${this.options.requestTimeoutMs} ms`), true);
            }, this.options.requestTimeoutMs);
            this.writeQueue.push(request);
            this.pumpWrites();
        });
    };
    close() {
        this.failTransport(new Error('NCP WebSocket closed by client'), true);
    }
}
//# sourceMappingURL=ws.js.map