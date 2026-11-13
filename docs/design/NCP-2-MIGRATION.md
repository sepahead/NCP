# Moving the consumers to NCP 2

Status: plan of 26 October 2026, from a read-only inventory of each consumer's `main` branch.
It refines the order in section 9 of the [design record](NCP-2-DESIGN.md#9-migration), which governs; each step leaves every project working.
NCP 1 stays available until the last consumer has moved; the NCP 1 code in this repository is removed only then.

## 1. Where each consumer uses NCP 1 today

NCP 1 has two surfaces that consumers use: the released local SDK `ncp-local` (1.0.0 and 1.0.1, under `local/`) and the unreleased wire-1.0 candidate (`ncp-core`, `ncp-zenoh`, the TypeScript package `@sepahead/ncp`, at commit `2819dae`).
The counts are source references on `main`, without vendored copies and documentation; they size the work, they do not measure it.

| Consumer (main) | Wire-1.0 candidate | Local SDK | Change rules |
| --- | --- | --- | --- |
| CREBAIN (`61a2884`) | The application (`src-tauri`) and `src-tauri/crates/ncp-headless`, behind the `ncp` feature: 135 `ncp_core::`, 4 `ncp_zenoh::`. `@sepahead/ncp` in `src/neuro` and the build scripts: 30 references | `src-tauri/crates/ncp-simulation`, the native responder that owns the simulation kernel, on 1.0.1: 5 `ncp_local::`. The force-city and ground-sensor integrations on 1.0.0 at `c0465d4`: 55 `ncp_local::`; their certificates bind that exact dependency | unsigned commits; agents may merge |
| Galadriel (`9514ca1`) | `crates/galadriel-ncp` (features `ncp`, `ncp-live`) and three uses in `galadriel-cli`: 21 `ncp_core::`, 8 `ncp_zenoh::` | `crates/galadriel-local-adapter` on 1.0.1: 8 `ncp_local::` | signed branch, pull request, squash merge; release records bind the lockfiles |
| Prisoma (`f2c507e`) | `crates/ncp-observer`: 11 `ncp_core::`, 1 `ncp_zenoh::` | `crates/ncp-local-capture` on 1.0.1: 12 `ncp_local::`. The Agent Bridge (`crates/agent-bridge-python`) and the modular transcript (`integrations/ncp-transcript`, Python, `c0465d4`) | agents may push to `main`; the capability matrix and release candidate bind sources |
| Haldir (`49c03ac`) | `crates/haldir-ncp10` (feature `real-ncp`) and `crates/haldir-transport-zenoh`: 21 `ncp_core::` in code | none | owner-approved, signed fast-forward only; epoch records; pinned RustSec snapshot |
| Engram / Paper2Brain (`91b7bc6`) | a vendored copy of the wire-1.0 workspace in `ncp/`, and its Python protocol module (`backend/neurocontrol`): 13 references | none | push to `main`, no pull requests; hosted CI is blocked by the spending limit, so gates run locally |

## 2. What NCP 2 offers in their place

| NCP 1 use | NCP 2 equivalent | Gap |
| --- | --- | --- |
| `ncp-local` lockstep client and owner | `ncp::Client` and `ncp::Owner` in the Rust package `sepahead-ncp-core` (library `ncp`) and the Python package `sepahead-ncp` (module `ncp`): one round trip per call, the acknowledgement in the next request | none: both SDKs bind pipes and child processes, Unix sockets, and TCP |
| Typed messages of the wire-1.0 candidate | NCP 2 frames: JSON region, attachments, digest identity; operations and streams named by a contract document | each consumer writes its own contract; no generated types |
| Zenoh transport (`ncp-zenoh`) | the Zenoh binding of specification 9.2: the optional packages in [`bindings/zenoh`](../../bindings/zenoh/README.md), Python `ncp_zenoh` and Rust `ncp_zenoh` | a session per service and session identifier, not per Zenoh key family; mutual TLS and access control in the Zenoh configuration |
| Sensor streams | NCP 2 streams: sequenced, hash-chained, loss reported (`Publisher`, `Subscriber`) | none |
| Transcripts | NCP 2 transcripts and their offline verifier (`Tap`, `verify`) | none |
| TypeScript `@sepahead/ncp` | none | **no TypeScript SDK** |

## 3. Order and reasons

The steps follow the design record; within a step, the order is a suggestion.

1. **Local users.** Prisoma `ncp-local-capture`, Galadriel `galadriel-local-adapter` and CREBAIN `ncp-simulation`. Each maps directly to the byte-stream binding. Prisoma can push to `main`; Galadriel needs a signed pull request with a new license record for the changed lockfile.
2. **Former modular users.** CREBAIN's force-city and ground-sensor integrations, and Prisoma's Agent Bridge with its modular transcript. Their existing certificates and evidence stay as dated records of the NCP 1 dependency; the moved code needs new evidence of its own.
3. **The NCP 2 Zenoh binding**, as an optional package outside the core SDKs, built with TLS only and without QUIC (design record, decision 9). Then the former wire-1.0 users: Galadriel `galadriel-ncp` and its CLI, Prisoma `ncp-observer`, CREBAIN's application, and Haldir, whose NCP pin needs a new lineage epoch and an owner-approved signed fast-forward.
4. **Engram**, in agreement with its owner: replace the vendored wire-1.0 copy and its protocol module with the NCP 2 SDK. The NEST coupling in [`benchmarks/nest-campaign`](../../benchmarks/nest-campaign) already runs an NCP 2 owner inside NEST.
5. **A TypeScript SDK or a bridge**, only if CREBAIN's `src/neuro` still needs NCP after the Rust side has moved.

## 4. Artifacts that must not change

Dated evidence and frozen descriptors stay byte for byte: CREBAIN's `engram.host.v1` vector and manifest, Prisoma's legacy Host API descriptor (`integrations/engram/manifest.json`), Galadriel's claim record CLM-008, and the certificates and evidence that bind the NCP 1 dependencies.
A migration adds new files next to them; it never edits them.

## 5. When a consumer has moved

- No dependency on `ncp-local`, `ncp-core`, `ncp-zenoh` or `@sepahead/ncp` remains in its manifests or lockfiles, except in frozen artifacts.
- Its own gates pass, run locally where hosted CI is unavailable, with the evidence recorded.
- Its documentation describes the NCP 2 contract it uses.
- This table is updated.

When every row is done, the NCP 1 code (`local/`, `ncp-core`, `ncp-zenoh`, `ncp-ts`, `ncp-cpp`, `ncp-gateway`, `ncp-python`) leaves the main branch. Its last state stays reachable through the tag `ncp-1-archive`, which the owner creates; NCP 2.0 is released after its gates and the owner's approval.

## 6. From revision 2 to revision 3 of NCP 2

Revision 3 of the specification (13 November 2026) changes the session rules (design record, [section 12](NCP-2-DESIGN.md#12-revision-3)) and the interfaces of both SDKs. A consumer of revision 2 moves in one change: its code, its pin of NCP, and its evidence.

### What changes on the wire

- Responses can have the outcome `declined`: the owner admitted the request and never executes it. `rejected` means "not admitted", and a client that follows the rules sees it only for `open`; a rejection of another request ends the session, possibly executed (rule 7.6.4).
- The `open` response carries a `nonce` and the `features` that the owner enabled.
- A request with `seq` greater than 0 of a session that the owner does not hold gets `ended` with `session_expired` on every binding.
- A stopping owner answers `ended` with `shutdown`.
- Optional: frames authenticated with a shared key (HMAC-SHA-256), contract schemas, and transcript version 2. A verifier still reads transcripts of version 1.

### Python (`ncp`)

| Revision 2 | Revision 3 |
| --- | --- |
| `ncp.Owner(application, contract_identity, handler, operations)` | `ncp.Owner(contract, handler)`, where `contract` is an `ncp.Contract`; a list of contracts of one application is allowed |
| Handler `validate(op, body)` and `execute(op, body)` | `validate(request)` and `execute(request)`: `request.op`, `request.body`, `request.arrays`, `request.seq`, `request.identity`, and more |
| `raise ncp.BodyInvalid(...)` in `validate` | `raise ncp.Declined(...)` |
| `ncp.Client(channel, application=..., contract=...)` | `ncp.Client(channel, contract)`; a context manager opens and closes the session |
| `channel, process = ncp.spawn(argv)` | `channel = ncp.spawn(argv)`; closing the channel ends the child |
| `ncp.Rejected` for an invalid body | `ncp.Declined`, with `code` `body_invalid` or `unknown_op`; the session goes on |
| `ncp.Ended` codes `timeout` and `closed` | `local.timeout`, `local.closed`, `local.protocol`, and `local.bad_frame`; `executed` is an `ncp.Executed` (`YES`, `NO`, `UNKNOWN`), which compares equal to `"yes"`, `"no"`, and `"unknown"` |
| `ncp.verify_transcript(path)` returns one report for each session | It returns one `Report`: `ok`, `sessions`, `streams`, and `problems` |
| `ncp.exchange` | `ncp.owner`, `ncp.client`, and `ncp.messages` |
| `ncp_zenoh.serve(...)` on the caller's thread | `ncp_zenoh.Server(...).start()` and `stop(grace)`, one thread for each session; `serve(..., stop=event)` still blocks until the event is set |

### Rust (`ncp`)

| Revision 2 | Revision 3 |
| --- | --- |
| `Owner::new(application, identity, handler, operations, max_bound)` | `Owner::new(contract, handler)`, then `with_max_bound`, `with_key`, `with_observer`; `Owner::with_contracts` for several contracts |
| `Handler::validate(&mut self, op, &Decoded) -> Result<(), String>` | `validate(&mut self, &Request<'_>) -> Result<(), Invalid>`; `declined("why")` makes the error |
| `Handler::execute(&mut self, op, &Decoded) -> Result<Reply, Box<dyn Error>>` | `execute(&mut self, &Request<'_>) -> Result<Reply, AppError>`; `request.body`, `request.op`, `request.owned_arrays()` |
| `Client::new(channel, application, identity)` | `Client::new(channel, &contract)` |
| `let (channel, child) = spawn(command)?` | `let channel = spawn(command)?`; dropping it ends the child |
| `Error::Rejected` for an invalid body; `Error::Ended { code, executed: &str }` | `Error::Declined { code, detail, body }`; `Error::Rejected` only for `open`; `Error::Ended { code, executed: Executed, detail, body }`; `Error::Usage` |
| `Channel::receive -> Result<Vec<u8>, Error>` | `-> Result<Vec<u8>, ChannelError>` (`BadFrame`, `Timeout`, `Closed`) |
| `transcript::verify(path)` | `transcript::verify(path, key)` returns one `Report` |
| `ncp::exchange` | `ncp::owner`, `ncp::client`, and `ncp::messages` |
| `ncp_zenoh::Server::run` on the caller's thread | `Server::declare` serves each session in its own thread; `Server::stop(grace)` |

### Consumers of revision 2

| Consumer | Uses | State |
| --- | --- | --- |
| CREBAIN | The native simulation and its closed loop (`src-tauri/crates/ncp-simulation`, Rust, pinned at `3b51a1b`) and the NEST controller (`integrations/ncp2-nest-controller`, Python) | Moves to revision 3 with a new pin |
| Prisoma, Galadriel, Haldir, Engram | NCP 1 surfaces (section 1) | Move directly to revision 3, in the order of section 3 |

## 7. From revision 3 to revision 4 of NCP 2

Revision 4 (13 November 2026) closes the findings of the design record, [section 13](NCP-2-DESIGN.md#13-revision-4). A consumer of revision 3 moves its pin and, where it uses the interfaces below, its code.

### What changes on the wire

- A response that names no request (`bad_frame`, `shutdown`) carries `{"session": S, "kept": K}` when the owner holds a session. A client trusts it only when both match; on Zenoh it ignores it.
- A request of another protocol version gets `rejected` with `wrong_protocol`, whatever its other members.
- An array shape has at most 32 dimensions.
- A client refuses an `open` response without a valid nonce, so an owner of revision 2 cannot open a session with it.
- Lockstep profile revision 2: the feature parameters and `ncp.tick` carry `request`; only the last session that asked for the feature can step.

### Python (`ncp`)

| Revision 3 | Revision 4 |
| --- | --- |
| `ncp.Ended` | Also `request`: the identity of the request that `executed` is about |
| `ncp.LockstepClient.uncertain`: the tick | `(tick, request identity)` |
| `ncp.Lockstep(handler, ops, tick=..., state=...)` | Also `request=`: the identity that produced a restored tick; `holder` names the session that can step |
| `ncp.TlsConfig` for a client without `server_name` | A client needs `server_name`: `ValueError` otherwise |
| `ncp_zenoh.Server(session, service, make_owner)` | Also `key=`: the server checks every frame with it; each owner needs the same key |

### Rust (`ncp`)

| Revision 3 | Revision 4 |
| --- | --- |
| `Error::Ended { code, executed, detail, body }` | Also `request: Option<String>` |
| `LockstepClient::uncertain: Option<u64>` | `Option<(u64, Option<String>)>` |
| `lockstep::Clock { tick, state }` | Also `request` and `holder` |
| `ncp_zenoh::ServeOptions`, which was `Copy` | Also `key: Option<Key>`; `Clone`, no longer `Copy` |
| — | `messages::foreign`, `frame::elements`, `frame::MAX_RANK` |
