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

import type {
  ChannelValue,
  NetworkRef,
  Observation,
  ObservationFrame,
  RecordTarget,
  SessionClosed,
  SessionOpened,
  SimConfig,
  StimulusTarget,
} from './generated'

/** The protocol version this client stamps on every request (`ncp_version`). */
export const NCP_VERSION = '0.1'

/**
 * JSON-wire view of a canonical type. ts-rs emits Rust `i64` fields (ids,
 * `population_sizes`, `senders`, `resolved`, `seq`, `seed`, …) as `bigint` for
 * precision-safety, but `JSON.stringify` cannot serialize a `bigint` and
 * `JSON.parse` yields `number`; NCP uses small integers, so the JSON wire uses
 * `number` (see `ncp-core/bindings/README.md`). `Wire<T>` maps `bigint → number`
 * recursively so the generated shapes stay the single source of truth while
 * remaining JSON-(de)serializable.
 */
export type Wire<T> = T extends bigint
  ? number
  : T extends Array<infer U>
    ? Array<Wire<U>>
    : T extends object
      ? { [K in keyof T]: Wire<T[K]> }
      : T

// JSON-wire aliases of the reply types consumers read back off the wire.
export type SessionOpenedReply = Wire<SessionOpened>
export type SessionClosedReply = Wire<SessionClosed>
export type ObservationFrameReply = Wire<ObservationFrame>
export type ObservationData = Wire<Observation>

/**
 * Construction views. The canonical message types are maximally strict (ts-rs
 * marks every Rust field required), but the JSON Schemas default most fields, so
 * for *building* a request we make the defaulted members optional while keeping
 * the discriminating members required. The client fills the envelope
 * (`kind`, `ncp_version`, `session_id`, empty `bindings`).
 */
export type ChannelInput = Pick<Wire<ChannelValue>, 'data'> & Partial<Wire<ChannelValue>>
export type NetworkInput = Pick<Wire<NetworkRef>, 'kind' | 'ref'> & Partial<Wire<NetworkRef>>
export type RecordInput = Pick<Wire<RecordTarget>, 'port' | 'target' | 'observable'> &
  Partial<Wire<RecordTarget>>
export type StimulusInput = Pick<Wire<StimulusTarget>, 'port' | 'target' | 'kind'> &
  Partial<Wire<StimulusTarget>>
export type SimInput = Partial<Wire<SimConfig>>

/** Any transport: serialize `message`, deliver it to the NCP session service, and
 *  resolve with the reply payload (already parsed from the wire). */
export type Send = (message: Record<string, unknown>) => Promise<unknown>

export class NeuroSimClient {
  constructor(private readonly send: Send) {}

  /** Open a session: declare what to record and what to stimulate. */
  async open(
    sessionId: string,
    network: NetworkInput,
    record: RecordInput[],
    stimulus: StimulusInput[],
    sim: SimInput = {},
  ): Promise<SessionOpenedReply> {
    const reply = await this.send({
      kind: 'open_session',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
      network,
      record: { targets: record },
      stimulus: { targets: stimulus },
      sim,
      bindings: [],
    })
    return reply as SessionOpenedReply
  }

  /** Advance one chunk; optionally inject `stimulus`; returns an observation frame. */
  async step(
    sessionId: string,
    stimulus: Record<string, ChannelInput> = {},
    advanceMs?: number,
  ): Promise<ObservationFrameReply> {
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
    })
    return reply as ObservationFrameReply
  }

  /** Batch: advance `durationMs` holding `stimulus`; returns an observation frame. */
  async run(
    sessionId: string,
    durationMs: number,
    stimulus: Record<string, ChannelInput> = {},
  ): Promise<ObservationFrameReply> {
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
    })
    return reply as ObservationFrameReply
  }

  /** Close the session. */
  async close(sessionId: string): Promise<SessionClosedReply> {
    const reply = await this.send({
      kind: 'close_session',
      ncp_version: NCP_VERSION,
      session_id: sessionId,
    })
    return reply as SessionClosedReply
  }
}
