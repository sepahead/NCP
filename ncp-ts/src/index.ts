/**
 * Canonical NCP (Neuro-Cybernetic Protocol) for TypeScript: the generated,
 * wire-identical message types plus a transport-agnostic client.
 *
 * The types are generated (via ts-rs) from the `ncp-core` reference types, which
 * conform to the normative `proto/ncp.proto` wire contract (proto-native); the
 * client/transport add orchestration only. Rust, Python and TS peers are therefore
 * wire-identical. Do not re-declare these types downstream — import them from here.
 */

// Canonical, generated message types + enums (the JSON projection of proto/ncp.proto).
export type * from './generated/index.js'
export {
  NCP_BUILD_IDENTITY,
  NCP_NORMATIVE_CONTRACT_DIGEST,
  NCP_PACKAGE_VERSION,
} from './contract-identity.js'

// Client orchestration, JSON-wire helpers, and the WebSocket transport.
export {
  NeuroSimClient,
  NCP_VERSION,
  NCP_CONTRACT_HASH,
  checkVersion,
  NcpVersionError,
  contractStatus,
  assertScientificBoundary,
  assertNcpMessage,
  NcpScientificBoundaryError,
  JSON_SAFE_INTEGER_MAX,
  JSON_SAFE_INTEGER_MIN,
  MAX_HORIZON_STEPS,
  MAX_CHANNELS,
  NCP_ERROR_CODES,
} from './client.js'
export type {
  Send,
  Wire,
  ErrorFrame,
  ChannelInput,
  NetworkInput,
  RecordInput,
  StimulusInput,
  SimInput,
  SessionOpenedReply,
  SessionClosedReply,
  ObservationFrameReply,
  ObservationData,
  ClientNegotiation,
  MutationInput,
  NcpErrorCode,
} from './client.js'
export { WebSocketNeuroSim } from './ws.js'
export {
  BoundedJsonError,
  JSON_LIMITS,
  parseBoundedJson,
  preflightJson,
} from './bounded-json.js'
export type { JsonLimitCode } from './bounded-json.js'
export {
  canonicalRequestProjection,
  requestDigest,
  verifyRequestDigest,
  RequestDigestError,
  REQUEST_DIGEST_DOMAIN_V1,
  MAX_REQUEST_PROJECTION_BYTES,
} from './request-digest.js'

// Plant-side safety + resilience (the ncp-core safety.rs / resilience.rs port,
// behaviour-pinned to the shared corpus) + the wire-1.0 data-plane ingress gate.
export {
  ActionBuffer,
  CommandWatchdog,
  SafetyGovernor,
  assertWireFrame,
  maxHorizonLen,
  LINK_LOSS_ESTOP_FACTOR,
  MAX_TTL_MS,
} from './safety.js'
export type { CommandLike, SensorLike, WireChannels } from './safety.js'
