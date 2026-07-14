/**
 * Neuro-Cybernetic Protocol (NCP) — transport-agnostic TypeScript client.
 *
 * Wire-identical to the normative `proto/ncp.proto` contract (proto-native) and the
 * Rust (`ncp-core`) and Python peers: every reply and enum type is imported from
 * the generated bindings (`./generated`, the ts-rs output of the `ncp-core`
 * reference types). This file adds only the *client* orchestration (build a
 * request, await the typed reply) and a JSON-wire view of the generated types.
 * Request envelopes are built as object literals — keep their fields in sync with
 * the generated request types (`OpenSession`/`StepRequest`/`RunRequest`/`CloseSession`).
 *
 * Transport-agnostic: provide any `send(message) => Promise<reply>` (see `ws.ts`
 * for a WebSocket implementation; a Zenoh/native transport can implement the same
 * `Send`).
 */
import type { AuthorityLease, ChannelValue, ErrorFrame as GeneratedErrorFrame, GatewayAttribution, IdentityClaim, NetworkRef, Observation, ObservationFrame, OperationContext, RecordTarget, SessionClosed, SessionOpened, SimConfig, StimulusTarget } from './generated/index.js';
/** The protocol version this client stamps on every request (`ncp_version`).
 * Wire 0.8 splits the overloaded `seq` into a per-stream `stream` position + a
 * correlation-only `source`, adds `session` (generation) + `session_id` on every
 * session-scoped frame, and retires the top-level `seq`/`last_seq`. */
export declare const NCP_VERSION = "1.0";
/**
 * This peer's contract-hash (`ncp_core::CONTRACT_HASH` — FNV-1a of the canonicalized
 * proto). Pinned, cross-language-anchored to the Rust/Python peers and verified
 * against the proto in those peers' CI. Carried in `open()` and compared to the
 * server's reply as an **advisory** signal (see `contractStatus`): a mismatch is
 * surfaced, not thrown — `ncp_version` is the hard compatibility gate.
 */
export declare const NCP_CONTRACT_HASH = "163acc57d8a62b66";
/** Exact integer range shared by every JSON implementation (binary64 included). */
export declare const JSON_SAFE_INTEGER_MAX = 9007199254740991;
export declare const JSON_SAFE_INTEGER_MIN: number;
export declare const MAX_HORIZON_STEPS = 65536;
export declare const MAX_CHANNELS = 4096;
/** Closed stable wire-1.0 error-code registry. Keep this in exact parity with
 * `contract/errors.v1.json`; the shared mandatory corpus exercises rejection of
 * missing and unknown values in every implementation. */
export declare const NCP_ERROR_CODES: readonly ["NCP-AUTH-001", "NCP-AUTH-002", "NCP-AUTH-003", "NCP-AUTH-004", "NCP-AUTH-005", "NCP-AUTH-006", "NCP-LEASE-001", "NCP-LEASE-002", "NCP-LEASE-003", "NCP-LEASE-004", "NCP-OP-001", "NCP-OP-002", "NCP-OP-003", "NCP-OP-004", "NCP-OP-005", "NCP-OP-006", "NCP-LIMIT-001", "NCP-LIMIT-002", "NCP-LIMIT-003", "NCP-LIMIT-004", "NCP-LIMIT-005", "NCP-LIMIT-006", "NCP-LIMIT-007", "NCP-LIMIT-008", "NCP-LIMIT-009", "NCP-PROFILE-001", "NCP-PROFILE-002", "NCP-PLANT-001", "NCP-PLANT-002", "NCP-PLANT-003", "NCP-STATE-001", "NCP-STATE-002", "NCP-STATE-003", "NCP-VERSION-001", "NCP-FEATURE-001", "NCP-AUDIT-001", "NCP-AUDIT-002", "NCP-GATEWAY-001", "NCP-GATEWAY-002", "NCP-WIRE-001", "NCP-INTERNAL-001"];
export type NcpErrorCode = (typeof NCP_ERROR_CODES)[number];
/** Advisory comparison of a peer-advertised contract hash to ours. Mirrors
 *  `ncp_core::contract_status` — never throws; `null` = match or not advertised, a
 *  string = an advisory message describing the mismatch (for logging/telemetry). */
export declare function contractStatus(peerHash: string | null | undefined): string | null;
/** Thrown when a peer's `ncp_version` is unparseable or incompatible (the HARD
 *  compatibility gate — distinct from the advisory contract-hash check). */
export declare class NcpVersionError extends Error {
}
/**
 * The HARD wire-compatibility gate — `true` if `version` can speak our wire.
 * Mirrors `ncp_core::check_version` exactly so the TS peer accepts/rejects the same
 * versions as the Rust/Python/C++ peers: for a pre-1.0 wire (major 0) the protocol
 * has no stability guarantee, so BOTH major and minor must match (`0.3 ≠ 0.4`); for
 * a stable wire (major ≥ 1) the major alone decides. An unparseable version always
 * throws [`NcpVersionError`]; an incompatible-but-parseable version throws when
 * `strict`, else returns `false`. This is the gate `contractStatus` is explicitly
 * NOT — the contract hash is advisory; the version is fail-closed.
 */
export declare function checkVersion(version: string, strict?: boolean): boolean;
/** Thrown when a frame violates the NCP scientific-boundary discriminators. */
export declare class NcpScientificBoundaryError extends Error {
}
/**
 * Enforce the **mandatory, fail-closed scientific-boundary discriminators** on an
 * inbound `observation_frame` (or a `session_opened.provenance` block): NCP output is
 * a *control artifact*, never a validated reproduction, so `is_simulation_output` MUST
 * be `true` and `calibrated_posterior` MUST be `false`. A TS consumer should call this
 * on frames it reads so a peer cannot quietly hand it a frame claiming calibrated /
 * non-simulation status. Mirrors the boundary pins `ncp_core::validate` enforces in the
 * Rust/Python/C++ peers. Throws [`NcpScientificBoundaryError`] on a violation.
 */
export declare function assertScientificBoundary(frame: Record<string, unknown>): void;
/** Rust `char::is_control` parity for the JSON identifiers NCP constrains.
 * JavaScript's common C0/DEL-only regex misses the C1 range U+0080..U+009F. */
export declare function hasWireControlCharacters(value: string): boolean;
/** Full TypeScript ingress gate for the shared validation contract. Unknown object
 * fields remain allowed; known fields are type/value checked exactly like the Rust
 * reference, including nested stimulus identity and safe JSON integers. */
export declare function assertNcpMessage(value: unknown, expectedKind?: string): asserts value is Record<string, unknown>;
/**
 * JSON-wire view of a canonical type. ts-rs emits Rust `i64` fields (ids,
 * `population_sizes`, `senders`, `resolved`, `seq`, `seed`, …) as `bigint` for
 * precision-safety, but `JSON.stringify` cannot serialize a `bigint` and
 * `JSON.parse` yields `number`; NCP uses small integers, so the JSON wire uses
 * `number` (see `ncp-core/bindings/README.md`). `Wire<T>` maps `bigint → number`
 * recursively so the generated shapes stay wire-identical to the contract while
 * remaining JSON-(de)serializable.
 */
export type Wire<T> = T extends bigint ? number : T extends Array<infer U> ? Array<Wire<U>> : T extends object ? {
    [K in keyof T]: Wire<T[K]>;
} : T;
export type SessionOpenedReply = Wire<SessionOpened>;
export type SessionClosedReply = Wire<SessionClosed>;
export type ObservationFrameReply = Wire<ObservationFrame>;
export type ObservationData = Wire<Observation>;
export type ErrorFrame = Omit<Wire<GeneratedErrorFrame>, 'code'> & {
    code: NcpErrorCode;
};
/**
 * Construction views. The canonical message types are maximally strict (ts-rs
 * marks every Rust field required), but the JSON Schemas default most fields, so
 * for *building* a request we make the defaulted members optional while keeping
 * the discriminating members required. The client fills the envelope
 * (`kind`, `ncp_version`, `session_id`, empty `bindings`).
 */
export type ChannelInput = Pick<Wire<ChannelValue>, 'data'> & Partial<Wire<ChannelValue>>;
export type NetworkInput = Pick<Wire<NetworkRef>, 'kind' | 'ref'> & Partial<Wire<NetworkRef>>;
export type RecordInput = Pick<Wire<RecordTarget>, 'port' | 'target' | 'observable'> & Partial<Wire<RecordTarget>>;
export type StimulusInput = Pick<Wire<StimulusTarget>, 'port' | 'target' | 'kind'> & Partial<Wire<StimulusTarget>>;
export type SimInput = Partial<Wire<SimConfig>>;
/** Authenticated transport context supplied by the caller. Payload claims never
 * authenticate themselves; the transport adapter must bind this claim to its
 * verified peer identity before it sends an NCP message. */
export type ClientNegotiation = {
    identity: Wire<IdentityClaim>;
    security_profile: 'dev-loopback-insecure' | 'production-secure';
    security_state_digest: string;
    gateway_permitted: boolean;
    gateway?: Wire<GatewayAttribution> | null;
};
/** Exactly-once and authority context required for every lifecycle mutation. */
export type MutationInput = {
    operation: Omit<Wire<OperationContext>, 'request_digest'> & {
        request_digest?: string;
    };
    authority: Wire<AuthorityLease>;
};
/** Any transport: serialize `message`, deliver it to the NCP session service, and
 *  resolve with the reply payload (already parsed from the wire). */
export type Send = (message: Record<string, unknown>) => Promise<unknown>;
export declare class NeuroSimClient {
    private readonly send;
    private readonly negotiation;
    /** session_id -> the server-issued generation, learned at open(). */
    private readonly generations;
    constructor(send: Send, negotiation: ClientNegotiation);
    /** Open a session: declare what to record and what to stimulate. */
    open(sessionId: string, network: NetworkInput, record: RecordInput[], stimulus: StimulusInput[], sim?: SimInput): Promise<SessionOpenedReply>;
    /** Advance one chunk; optionally inject `stimulus`; returns an observation frame. */
    step(sessionId: string, mutation: MutationInput, stimulus?: Record<string, ChannelInput>, advanceMs?: number): Promise<ObservationFrameReply>;
    /** Batch: advance `durationMs` holding `stimulus`; returns an observation frame. */
    run(sessionId: string, durationMs: number, mutation: MutationInput, stimulus?: Record<string, ChannelInput>): Promise<ObservationFrameReply>;
    /** Close the session. */
    close(sessionId: string, mutation: MutationInput): Promise<SessionClosedReply>;
}
//# sourceMappingURL=client.d.ts.map