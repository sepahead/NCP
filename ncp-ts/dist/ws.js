/**
 * WebSocket transport for the NCP client. The session service replies to each
 * message in order, so requests are correlated FIFO. Use this `send` with
 * `NeuroSimClient`, or implement `Send` over another bus (e.g. Zenoh) instead.
 */
export class WebSocketNeuroSim {
    ws;
    pending = [];
    ready;
    settleReady;
    closedError = null;
    constructor(url = 'ws://127.0.0.1:28471/api/neurocontrol/ws') {
        this.ws = new WebSocket(url);
        let settleReady;
        this.ready = new Promise((resolve) => {
            settleReady = resolve;
        });
        this.settleReady = settleReady;
        this.ws.onopen = () => this.settleReady();
        this.ws.onmessage = (event) => {
            const pending = this.pending.shift();
            if (!pending)
                return;
            try {
                // Parse inside the handler so one malformed frame rejects exactly the
                // request it was dequeued for, keeping FIFO correlation in sync.
                pending.resolve(JSON.parse(event.data));
            }
            catch (error) {
                pending.reject(new Error(`NCP reply was not valid JSON: ${WebSocketNeuroSim.messageOf(error)}`));
            }
        };
        // A close or error must settle both the connection wait and every in-flight
        // request. `ready` intentionally resolves on failure: `closedError` carries
        // the actual rejection and avoids an unobserved rejected promise when a
        // socket fails before the caller has sent its first request.
        this.ws.onerror = () => {
            const error = new Error('NCP WebSocket error');
            this.failAll(error);
            this.settleReady();
        };
        this.ws.onclose = () => {
            this.failAll(new Error('NCP WebSocket closed'));
            this.settleReady();
        };
    }
    static messageOf(error) {
        return error instanceof Error ? error.message : String(error);
    }
    /** Reject and drop every queued request; new sends fail fast afterwards. */
    failAll(error) {
        if (!this.closedError) {
            this.closedError = error;
        }
        while (this.pending.length > 0) {
            this.pending.shift().reject(this.closedError);
        }
    }
    /** Transport-agnostic `send` for `NeuroSimClient`. */
    send = async (message) => {
        await this.ready;
        if (this.closedError) {
            throw this.closedError;
        }
        return new Promise((resolve, reject) => {
            const request = { resolve, reject };
            this.pending.push(request);
            try {
                this.ws.send(JSON.stringify(message));
            }
            catch (error) {
                const index = this.pending.indexOf(request);
                if (index !== -1)
                    this.pending.splice(index, 1);
                reject(new Error(`NCP send failed: ${WebSocketNeuroSim.messageOf(error)}`));
            }
        });
    };
    close() {
        this.failAll(new Error('NCP WebSocket closed by client'));
        this.settleReady();
        this.ws.close();
    }
}
//# sourceMappingURL=ws.js.map