/**
 * Canonical NCP (Neuro-Cybernetic Protocol) for TypeScript: the generated,
 * wire-identical message types plus a transport-agnostic client.
 *
 * The types are generated (via ts-rs) from the `ncp-core` reference types, which
 * conform to the normative `proto/ncp.proto` wire contract (proto-native); the
 * client/transport add orchestration only. Rust, Python and TS peers are therefore
 * wire-identical. Do not re-declare these types downstream — import them from here.
 */
// Client orchestration, JSON-wire helpers, and the WebSocket transport.
export { NeuroSimClient, NCP_VERSION, NCP_CONTRACT_HASH, checkVersion, NcpVersionError, contractStatus, assertScientificBoundary, NcpScientificBoundaryError, } from './client';
export { WebSocketNeuroSim } from './ws';
// Plant-side safety + resilience (the ncp-core safety.rs / resilience.rs port,
// behaviour-pinned to the shared corpus) + the wire-0.6 data-plane ingress gate.
export { ActionBuffer, CommandWatchdog, SafetyGovernor, assertWireFrame, maxHorizonLen, LINK_LOSS_ESTOP_FACTOR, MAX_TTL_MS, } from './safety';
//# sourceMappingURL=index.js.map