# `@sepahead/ncp` — NCP TypeScript types + client

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
import { NeuroSimClient, WebSocketNeuroSim } from '@sepahead/ncp'
import type { ObservationFrameReply, SensorFrame } from '@sepahead/ncp'

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
dependency (`"@sepahead/ncp": "github:sepahead/NCP#<tag>"`) without a build step on
the consumer side. Rebuild and commit `dist` whenever the types or client change.

## Plant-side safety port (wire 0.6)

Since wire 0.6 the TS peer ships the plant-side safety surface (`src/safety.ts`), so a
TypeScript body can enforce the action-plane contract locally instead of delegating every
decision to a Rust peer:

- **`SafetyGovernor`** — the latching action-plane governor (speed clamp, geofence →
  latched ESTOP, stale-sensor HOLD); an **inbound ESTOP latches** until a supervisor
  `reset()`.
- **`CommandWatchdog`** — the `ttl_ms` deadline backstop; it refreshes only on a
  strictly-advancing `seq` and HOLDs when the deadline lapses.
- **`ActionBuffer`** + **`maxHorizonLen`** — packetized-predictive-control horizon
  replay, capped at `N ≤ ttl_ms / horizon_dt_ms` so a replay never outlives its own
  `ttl_ms`.
- **`assertWireFrame`** — the one-call ingress gate (kind + `ncp_version` + `seq` bound)
  a TS subscriber runs before trusting a frame.

The client also **hard-gates every reply's `ncp_version`**: wire 0.6 makes `ncp_version`
mandatory on every message, so a wire-incompatible reply is rejected and a mismatched-minor
peer fails closed rather than being silently mis-decoded. The peer replays the **full
`govern` corpus** plus seq/ttl/latch self-checks in `scripts/check-behavior.mjs`.

## Coverage

This package exports **wire types + client orchestration**: the generated message
types (`src/generated/*.ts`), the `NeuroSimClient` (`open`/`step`/`run`/`close`),
the WebSocket transport, the cross-language decision functions
(`checkVersion`, `contractStatus`, `assertScientificBoundary`), and — since wire 0.6 —
the plant-side safety port (see above). This is the surface a TS peer needs to be
wire-identical to the Rust/Python/C++ peers.

The following `ncp-core` modules remain **not** exported in TypeScript (they are
Rust-core-only): the rate codec (`CodecSpec`, `encode`/`decode`), the bulk column codec
(`ncp-core::bulk`), the in-process bus, the control-loop runner (`NeuroControlLoop`), and
`LinkMonitor`. The action-plane safety port (`SafetyGovernor`, `CommandWatchdog`,
`ActionBuffer`, `maxHorizonLen`, `assertWireFrame`) **is** now exported (see above); a TS
consumer builds requests via the client, enforces the action plane locally with the safety
port, and delegates codec/bus decisions to the Rust peer on the other end of the wire.
