/**
 * Neuro-Cybernetic Protocol (NCP) — transport-agnostic TypeScript client.
 *
 * Wire-identical to the Rust (`ncp-core`) and Python peers: every message shape
 * and enum is imported from the canonical, ts-rs-generated bindings (`./generated`,
 * generated from the Rust `ncp-core` types). This file adds only the *client*
 * orchestration (build a request, await the typed reply) and a JSON-wire view of
 * the generated types — it re-declares no message shapes, so a field rename in
 * `ncp-core` breaks this file at compile time.
 *
 * Transport-agnostic: provide any `send(message) => Promise<reply>` (see `ws.ts`
 * for a WebSocket implementation; a Zenoh/native transport can implement the same
 * `Send`).
 */
/** The protocol version this client stamps on every request (`ncp_version`). */
export const NCP_VERSION = '0.1';
export class NeuroSimClient {
    send;
    constructor(send) {
        this.send = send;
    }
    /** Open a session: declare what to record and what to stimulate. */
    async open(sessionId, network, record, stimulus, sim = {}) {
        const reply = await this.send({
            kind: 'open_session',
            ncp_version: NCP_VERSION,
            session_id: sessionId,
            network,
            record: { targets: record },
            stimulus: { targets: stimulus },
            sim,
            bindings: [],
        });
        return reply;
    }
    /** Advance one chunk; optionally inject `stimulus`; returns an observation frame. */
    async step(sessionId, stimulus = {}, advanceMs) {
        const reply = await this.send({
            kind: 'step_request',
            ncp_version: NCP_VERSION,
            session_id: sessionId,
            advance_ms: advanceMs ?? null,
            stimulus: {
                kind: 'stimulus_frame',
                ncp_version: NCP_VERSION,
                session_id: sessionId,
                values: stimulus,
            },
        });
        return reply;
    }
    /** Batch: advance `durationMs` holding `stimulus`; returns an observation frame. */
    async run(sessionId, durationMs, stimulus = {}) {
        const reply = await this.send({
            kind: 'run_request',
            ncp_version: NCP_VERSION,
            session_id: sessionId,
            duration_ms: durationMs,
            stimulus: {
                kind: 'stimulus_frame',
                ncp_version: NCP_VERSION,
                session_id: sessionId,
                values: stimulus,
            },
        });
        return reply;
    }
    /** Close the session. */
    async close(sessionId) {
        const reply = await this.send({
            kind: 'close_session',
            ncp_version: NCP_VERSION,
            session_id: sessionId,
        });
        return reply;
    }
}
//# sourceMappingURL=client.js.map