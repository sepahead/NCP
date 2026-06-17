/**
 * Canonical NCP (Neuro-Cybernetic Protocol) for TypeScript: the generated,
 * wire-identical message types plus a transport-agnostic client.
 *
 * The types are generated from the Rust `ncp-core` source of truth via ts-rs;
 * the client/transport add orchestration only. Rust, Python and TS peers are
 * therefore wire-identical. Do not re-declare these types downstream — import
 * them from here.
 */
// Client orchestration, JSON-wire helpers, and the WebSocket transport.
export { NeuroSimClient, NCP_VERSION } from './client';
export { WebSocketNeuroSim } from './ws';
//# sourceMappingURL=index.js.map