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
| Zenoh transport (`ncp-zenoh`) | the Zenoh binding of specification 9.2 | **not implemented** in either SDK |
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
