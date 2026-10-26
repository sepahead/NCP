# Moving the consumers to NCP 2

Status: plan of 26 October 2026, from a read-only inventory of each consumer's `main` branch.
NCP 1 stays available until the last consumer has moved; the NCP 1 code in this repository is removed only then.

## 1. Where each consumer uses NCP 1 today

NCP 1 has two surfaces that consumers use: the released local SDK `ncp-local` (1.0.0 and 1.0.1, under `local/`) and the unreleased wire-1.0 candidate (`ncp-core`, `ncp-zenoh`, the TypeScript package `@sepahead/ncp`, at commit `2819dae`).
The counts are source references on `main`, without vendored copies; they size the work, they do not measure it.

| Consumer (main) | Wire-1.0 candidate | Local SDK | Other | Change rules |
| --- | --- | --- | --- | --- |
| CREBAIN (`61a2884`) | `src-tauri` and `crates/ncp-headless` behind the `ncp` feature: 136 `ncp_core::`, 4 `ncp_zenoh::`; frontend `@sepahead/ncp`: 30 references | native body adapter on 1.0.1; 60 `ncp_local::` | the force-city and ground-sensor integrations keep `ncp-local` 1.0.0 at `c0465d4` on purpose | unsigned commits; agents may merge |
| Galadriel (`9514ca1`) | `crates/galadriel-ncp` (features `ncp`, `ncp-live`): 21 `ncp_core::`, 8 `ncp_zenoh::` | `crates/galadriel-local-adapter` on 1.0.1: 8 `ncp_local::` | release records bind the lockfiles | signed branch, pull request, squash merge |
| Prisoma (`f2c507e`) | `crates/ncp-observer`: 12 `ncp_core::`, 1 `ncp_zenoh::` | `crates/ncp-local-capture` on 1.0.1: 12 `ncp_local::`; `integrations/ncp-transcript` (Python, `c0465d4`) | capability matrix and release candidate bind sources | agents may push to `main` |
| Haldir (`49c03ac`) | `crates/haldir-ncp10` (feature `real-ncp`) and `crates/haldir-transport-zenoh`: 26 `ncp_core::` | none | epoch records; pinned RustSec snapshot | owner-approved, signed fast-forward only |
| Engram / Paper2Brain (`91b7bc6`) | a vendored copy of the wire-1.0 workspace in `ncp/`; 13 `ncp_core::` outside it | none | CI blocked by the hosting spending limit; verify locally | push to `main`, no pull requests |

## 2. What NCP 2 offers in their place

| NCP 1 use | NCP 2 equivalent | Gap |
| --- | --- | --- |
| `ncp-local` lockstep client and owner | `ncp::Client` and `ncp::Owner` (Rust crate `ncp`, Python package `ncp`), one round trip per call, acknowledgement in the next request | none for local pipes, Unix sockets and TCP |
| Typed messages of the wire-1.0 candidate | NCP 2 frames: JSON region, attachments, digest identity; operations and streams named by a contract document | each consumer writes its own contract; no generated types |
| Zenoh transport (`ncp-zenoh`) | the Zenoh binding of specification 9.2 | **not implemented**: no SDK has it yet |
| Sensor streams | NCP 2 streams (sequenced, hash-chained, loss reported) | none in the SDKs |
| Transcripts | NCP 2 transcripts and the offline verifier | none |
| TypeScript `@sepahead/ncp` | none | **no TypeScript SDK** |

## 3. Order and reasons

1. **Prisoma `ncp-local-capture` and `integrations/ncp-transcript`.** Local lockstep use that maps directly to the byte-stream binding; Prisoma can push to `main`, and its transcript work builds on NCP 2 transcripts.
2. **Galadriel `galadriel-local-adapter`.** The same mapping; the adapter is independent of the rest of Galadriel. A signed pull request with a new license record for the changed lock.
3. **CREBAIN native body adapter.** Local use; the frozen integrations at `c0465d4` stay as they are, and a new NCP 2 integration is added next to them if needed.
4. **The NCP 2 Zenoh binding**, as an optional package that is not part of the core SDKs. It unblocks Galadriel `ncp-live`, Prisoma `ncp-observer`, CREBAIN `src-tauri` and Haldir `haldir-transport-zenoh`. It is built with TLS only and without QUIC (design record, decision 9).
5. **Galadriel `galadriel-ncp`, Prisoma `ncp-observer`, CREBAIN `src-tauri`.** After step 4.
6. **Haldir.** Last, because each change needs an owner-approved signed fast-forward and an epoch record; NCP is optional for Haldir.
7. **Engram.** Replace the vendored wire-1.0 copy with the NCP 2 SDK; the NEST coupling of `benchmarks/nest-campaign` shows the NCP 2 owner inside NEST.
8. **A TypeScript SDK or a bridge**, only if the CREBAIN frontend still needs NCP after the Rust side has moved.

## 4. Artifacts that must not change

Dated evidence and frozen descriptors stay byte for byte: CREBAIN's host vector and its integrations pinned at `c0465d4`, Prisoma's legacy descriptor, and Galadriel's claim record CLM-008.
A migration adds new files next to them; it never edits them.

## 5. When a consumer has moved

- No dependency on `ncp-local`, `ncp-core`, `ncp-zenoh` or `@sepahead/ncp` remains in its manifests or lockfiles, except in frozen artifacts.
- Its own gates pass, run locally where hosted CI is unavailable, with the evidence recorded.
- Its documentation describes the NCP 2 contract it uses.
- This table is updated.

When every row is done, the NCP 1 code (`local/`, `ncp-core`, `ncp-zenoh`, `ncp-ts`, `ncp-cpp`, `ncp-gateway`, `ncp-python`) leaves this repository, after the owner decides whether to tag an archive of it.
