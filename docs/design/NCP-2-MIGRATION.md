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

### Consumers of revision 4

State on 14 November 2026. Each pin names the NCP commit of the NCP 2 core that the consumer uses.

| Consumer | On NCP 2 | Still on NCP 1 |
| --- | --- | --- |
| CREBAIN | The native simulation and its closed loop (`src-tauri/crates/ncp-simulation`, pin `2e24ef5`) and the NEST controller (`integrations/ncp2-nest-controller`), on `main` at `a1df34c` | The application (`src-tauri`, feature `ncp`) and `ncp-headless` on the wire-1.0 candidate; `@sepahead/ncp` in `src/neuro`; the force-city and ground-sensor integrations on `ncp-local` 1.0.0 |
| Prisoma | The loop capture (`crates/ncp-loop-capture`, pin `2e24ef5`), on `main` at `6d5dde0` | `crates/ncp-observer` on the wire-1.0 candidate; the Agent Bridge and the modular transcript |
| Galadriel | The local adapter, which assesses CREBAIN loop runs (`crates/galadriel-local-adapter`, feature `ncp-loop`, pin `2e24ef5`), on `main` at `20ddc41` | `crates/galadriel-ncp` and its CLI on the wire-1.0 candidate |
| Haldir | None | `crates/haldir-ncp10` and `crates/haldir-transport-zenoh` on the wire-1.0 candidate |
| Engram | None | The vendored wire-1.0 workspace and its protocol module |

The remaining NCP 1 users share the wire-1.0 message families: sensor streams, advisories, and commands. They move together once NCP 2 contracts or profiles for those families exist (section 3, step 3).
Haldir's NCP pin lies inside the protected boundary of its signed lineage epoch 21. Moving it needs an epoch-22 transition, which the owner delivers, and a design of the Gate's commander lease over NCP 2, which has no authority machine.

## 8. From revision 4 to revision 5 of NCP 2

Revision 5 (14 November 2026) closes the findings of the design record, [section 14](NCP-2-DESIGN.md#14-revision-5). No consumer of revision 4 serves the lockstep profile or a contract with `ncp.schema`, so none must move its pin for these findings. A program that serves either moves.

### What changes on the wire

- `additionalProperties` no longer applies to members whose names start with `ncp.` (section 11.1). An owner of revision 5 admits a body with such a member that a closed schema of revision 4 declined.
- Lockstep profile revision 3: no message changes. The owner names the holder by its opening, so a copy of an earlier `open` no longer gives that opening the ticks again.
- The conformance vectors say revision 5, and `spec/ncp2-rules.json` names the revision.

### Python (`ncp`)

| Revision 4 | Revision 5 |
| --- | --- |
| `ncp.OpenInfo(session, contract, run, features)` | Also `nonce`: the nonce of the opening |
| `ncp.Request(op, body, arrays, seq, session, identity, contract, run, features)` | Also `nonce`: the nonce of the opening of the session |
| `ncp.Lockstep.holder`: a session identifier | The nonce of the opening that holds the ticks |
| `ncp.contract.check` with `additionalProperties` | Members whose names start with `ncp.` are exempt; `ncp.contract.RESERVED` |

### Rust (`ncp`)

| Revision 4 | Revision 5 |
| --- | --- |
| `OpenInfo { session, contract, run, features }` | Also `nonce: &str` |
| `Request { op, body, seq, session, identity, contract, run, features, decoded }` | Also `nonce: &str` |
| `lockstep::Clock::holder`: a session identifier | The nonce of the opening that holds the ticks |
| — | `contract::RESERVED` |

The Rust core also depends on `getrandom` 0.3.4. The lockfile of the Zenoh binding already holds it. The NCP 2 crates of the consumers (CREBAIN's `ncp-simulation`, Prisoma's `ncp-loop-capture`, and Galadriel's local adapter) add it when they move their pins, with `r-efi`, `wasip2`, and `wit-bindgen`, which only UEFI and WASI targets build. The core panics if the generator of the operating system fails, instead of using a weaker source.

### Contract upgrades

A contract's identity is the digest of its exact bytes, so a corrected word in a description is a new contract. Keep the document that the identity covers to names and schemas, and publish the prose next to it. To change a contract, let the owners accept both the old and the new contract first (rule 7.1.4.2), then move the clients. For streams, move the subscribers first, then the publishers.

### Open work after revision 5

The advisory review of revision 4 proposed this work, in this order:

Before the tag, the owner decides which parts it freezes. The review recommends a tag for the exercised core (frames, messages, the exchange, the byte-stream binding, transcripts, and contract identity), with sections 8, 9.2, and 11.1 and both profiles marked provisional, because no consumer uses them yet.

1. Lockstep: a takeover by a request inside the new opening, with a term that the owner issues, so that a copy of `open` takes nothing (rule 7.1.8); a model check of both profiles before they are frozen. Revision 6 did this for the lockstep profile (section 9); the rounds profile still has no model check.
2. Decline reasons that a program can read: a code for a refusal by the owner's state, and a `reason` member.
3. A stream profile for sensors and advisories: the stream type in the stream identifier, an announcement of live streams, start and liveness, time, and one key for each publisher. Galadriel's `galadriel-ncp` is its first subscriber.
4. An authority profile for commands: the body is the owner; the Gate acquires a lease with a term and a token bound to the opening; each response gives the remaining time; ESTOP has its own session. Then CREBAIN's application, and Haldir with its epoch-22 transition.
5. A fault campaign and a benchmark on the Zenoh binding, and the campaigns again on the revision that the tag names.
6. A convention for principals: one key, and one service, for each pair of programs whose frames must be told apart. Revision 6 states it in section 13.2; passing the binding's peer to the application stays open.

## 9. From revision 5 to revision 6 of NCP 2

Revision 6 (15 November 2026) closes the findings of the design record, [section 15](NCP-2-DESIGN.md#15-revision-6). Its wire changes concern only the lockstep profile and operations whose names start with `ncp.`; no consumer uses either, so none must move its pin.

### What changes on the wire

- Feature operations (section 15, rule 3): an operation `F.N` of a feature `F` that the session enabled goes to the profile; in every other session it is `declined` with `unknown_op`, as every owner of revision 5 answers it. A `declined` body can carry members whose names start with `ncp.`.
- Lockstep profile revision 4. The `open` response reports `{"tick", "state", "request", "term"}` and takes nothing. A stepping client sends `ncp.lockstep.take` with `{"term": E}` before its first step; the response is the final clock. A take whose term moved, or a step that the holder check declines, carries `{"ncp.lockstep": {"term": E}}`. A client of profile revision 3 never takes the ticks, so the owner declines all its steps; a client of revision 4 ends a session with an owner that reports no term.
- The owner leaves out `ncp.` members of a `declined` body that would not fit the session bound, and refuses an `open` whose response would not fit 65,536 bytes (rules 7.3.12 and 7.1.5).

### Python (`ncp`)

| Revision 5 | Revision 6 |
| --- | --- |
| `ncp.Lockstep(handler, ops, tick=..., state=..., request=...)`: `open` takes the ticks; the state digest starts as `None` | `open` reports; `ncp.lockstep.take` takes them; also `term`, `term=` to restore it, and `clock()`. Without `state=`, the digest starts as the application's `state()`. `tick` and `term` are at most 2**53 − 1 |
| `ncp.LockstepClient(client)` reads the report | Also takes the ticks; also `request`, the request that produced the tick, `term`, the term that the owner told last, and `take()`, which takes the ticks again in the same session |
| `LockstepClient.recover(client)`: verdict from the report, by the tick; `ProtocolError` without a verdict | Verdict from the take, by the whole clock: `ncp.lockstep.judge`. Without a verdict, it returns `Executed.UNKNOWN`; with every verdict, it goes on in the new session. If the take is declined, it ends that session and raises |
| `LockstepClient.step` after an `ok` without the tick: `ProtocolError` | Ends the session and raises `Ended` with `local.protocol`, executed `YES`; so does a take or a step whose clock lacks a member |
| — | `ncp.lockstep.take(client, term=None)`, which returns the clock and the new term, `ncp.lockstep.report(client)`, `TAKE`, `TAKE_ATTEMPTS`, `MAX_TERM`, `MAX_TICK` |
| — | `ncp.messages.feature_of(op)` |
| A handler's `Declined(detail, body=...)`: the owner kept only `detail` | The owner also keeps the members of `body` whose names start with `ncp.` |

### Rust (`ncp`)

| Revision 5 | Revision 6 |
| --- | --- |
| `lockstep::Clock { tick, state, request, holder }` | Also `term` |
| `LockstepClient { tick, state, uncertain }` | Also `request` and `term`; `new` also takes the ticks; `take()` takes them again in the same session |
| `LockstepClient::recover`: `Error::Usage` without a verdict | `Ok(Executed::Unknown)` without a verdict; with every verdict, it goes on in the new session. If the take is declined, it ends that session and fails |
| `LockstepClient::step` after an `ok` without the tick: `Error::Usage`, whose `executed()` is No | Ends the session and returns `Error::Ended` with `local.protocol`, executed Yes; so does a take or a step whose clock lacks a member |
| `Lockstep::new`: the state digest starts as `None` | The application's `state()`; it panics if that digest does not have 1 to 128 characters |
| — | `lockstep::{TAKE, TAKE_ATTEMPTS, MAX_TERM, MAX_TICK, Known, take, judge}`; `take(client, term)` returns the clock and the new term; `judge` returns `Executed`; `Lockstep::restored(stepper, ops, tick, state, request, term)` |
| `Invalid::{Declined, Failed}` | Also `Invalid::DeclinedWith`, made with `declined_with` |
| — | `messages::feature_of` |

### Open work after revision 6

An advisory design review of revision 6 (16 November 2026, read-only, not certification evidence) found no defect in the exchange. It ranks the work that the remaining consumers need, in this order:

1. Before the tag, the owner decides which parts it freezes. The review recommends a freeze of sections 3 to 7 without 6.3, rules 1 to 9 of section 9.1, sections 10, 12, 14, and 15, section 11 without 11.1, and the rules of section 13.2 that say where the authentication code sits. Streams (sections 6.3 and 8), the Zenoh binding, schemas, the key and TLS guidance, and both profiles stay provisional, each with its own revision. Text to add before a freeze: a verifier ignores unknown members of a transcript header; a client ignores unknown members of a body whose outcome is not `ok`; one key for each address; the revision of a profile in its feature parameters; a new key prefix for an incompatible Zenoh revision; and the supported platforms.
2. The revision in the implementation string, for example `ncp-python/2.0.0-rc.6`, so that an `open` response and a transcript say which rules made them. The tagged commit then says `2.0.0`.
3. The fault campaign and one benchmark block on the tagged revision, and a decoder, owner, and client by another author for the frozen parts.
4. Lockstep revision 5: a history identity in the clock, so that a recovery after a restore to an earlier saved clock gives no verdict instead of "did not run"; the revision of the profile on the wire; reasons for its refusals; and openings that may only read. Then CREBAIN's world, which already checks a tick and a state digest in its own contract, as its first consumer.
5. Decline reasons that programs can read: a body member `ncp.reason` with a registered name.
6. A stream profile for sensors and advisories: the stream type in the identifier, a start message, time, liveness, explicit gaps and drops, references by identity, and an announcement. First users: Galadriel and CREBAIN's world.
7. An authority profile for commands, in which the body is the owner and issues a lease with a term; the peer of the binding reaches the `open` handler. First users: CREBAIN's application and Haldir with its epoch 22.
8. Rounds revision 3, with a recovery, a clock, and a chained round identity, when a consumer needs many agents in one world.
9. A composition document whose identity a run names, so that a set of transcripts can show that it is the complete record of one declared run.
