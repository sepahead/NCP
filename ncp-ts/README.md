# `@sepehrmn/ncp` — NCP TypeScript types + client

The **canonical TypeScript peer** of the Neuro-Cybernetic Protocol. It bundles:

- **Generated message types** (`src/generated/*.ts`) — the ts-rs output of the Rust
  `ncp-core` reference types, which conform to the normative `proto/ncp.proto` wire
  contract (proto-native), so a TS peer is wire-identical to the Rust and Python
  peers. Do **not** edit these by hand.
- **A transport-agnostic client** (`src/client.ts`) — `NeuroSimClient`
  (`open`/`step`/`run`/`close`) built _on top of_ the generated types, reusing their
  field types for request inputs and reply shapes. Request envelopes are object
  literals, so keep them in sync with the generated request types.
- **A WebSocket transport** (`src/ws.ts`) — `WebSocketNeuroSim`, FIFO-correlated.
  Any other bus (e.g. native Zenoh) can implement the same `Send` interface.

## Use

```ts
import { NeuroSimClient, WebSocketNeuroSim } from '@sepehrmn/ncp'
import type { ObservationFrameReply, SensorFrame } from '@sepehrmn/ncp'

const transport = new WebSocketNeuroSim('ws://127.0.0.1:28471/api/neurocontrol/ws')
const ncp = new NeuroSimClient(transport.send)

await ncp.open(
  'feat-1',
  { kind: 'builtin', ref: 'iaf_psc_alpha', population_sizes: { feat: 1 } },
  [{ port: 'spk', target: 'feat', observable: 'spikes' }],
  [{ port: 'drive', target: 'feat', kind: 'current_pA' }],
)
const obs: ObservationFrameReply = await ncp.step('feat-1', { drive: { data: [500.0], unit: 'pA' } }, 50.0)
await ncp.close('feat-1')
```

## `bigint` vs `number`

ts-rs emits Rust `i64` fields as `bigint` for precision. `JSON.stringify` cannot
serialize a `bigint` and `JSON.parse` yields `number`, so the JSON wire uses
`number`. The exported `Wire<T>` maps `bigint → number` recursively; the client's
request inputs and reply types (`ObservationFrameReply`, …) are already `Wire`-d, so
you work in plain `number` while the generated types stay wire-identical to the contract.

## Regenerating after a Rust type change

```bash
npm run regen   # cargo test -p ncp-core --features ts → sync → tsc build
```

`ncp-ts/dist` is committed so the package is consumable directly as a git
dependency (`"@sepehrmn/ncp": "github:sepahead/NCP#<tag>"`) without a build step on
the consumer side. Rebuild and commit `dist` whenever the types or client change.

## Coverage

This package exports **wire types + client orchestration**: the generated message
types (`src/generated/*.ts`), the `NeuroSimClient` (`open`/`step`/`run`/`close`),
the WebSocket transport, and the cross-language decision functions
(`checkVersion`, `contractStatus`, `assertScientificBoundary`). This is the
surface a TS peer needs to be wire-identical to the Rust/Python/C++ peers.

The following `ncp-core` modules are **not** exported in TypeScript (they are
Rust-core-only): the rate codec (`CodecSpec`, `encode`/`decode`), the safety
governor (`SafetyGovernor`, `CommandWatchdog`), the bulk column codec
(`ncp-core::bulk`), the in-process bus, the control-loop runner
(`NeuroControlLoop`), and the resilience layer (`ActionBuffer`, `LinkMonitor`).
A TS consumer builds requests via the client and delegates safety/codec decisions
to the Rust peer on the other end of the wire.
