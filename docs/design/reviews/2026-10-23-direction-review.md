> Dated record of the review that chose the direction of NCP 2, written on 23 October 2026 and added to the repository on 2 November 2026. Its text is unchanged, except one phrase in row 47, reworded to follow the repository's wording rules. The [design record](../NCP-2-DESIGN.md) and the [specification](../../../spec/NCP-2.md) govern; where this record and they differ, they are current.

# NCP council review, 23 October 2026 (draft for the direction decision)

Method: first-principles review of what NCP must do, which alternatives exist, what is measured,
what can go wrong, and what is surplus. Evidence is from this repository and the October campaigns.

## 1. Purpose

NCP couples independently owned programs in a closed loop, each in its own process:
a neural simulator (NEST), a body or world simulator (CREBAIN), monitors (Galadriel), and
experiment recorders (Prisoma). It must give:

1. typed, bounded messages that each application defines;
2. lockstep steps that run exactly once, with the result kept until the peer acknowledges it, so a
   lost response is retried without running the step again;
3. integrity: a corrupted, foreign, reordered, or repeated message is detected;
4. a known outcome for every fault, never a wrong result accepted;
5. bulk data (images, spike arrays) without unbounded memory;
6. the same bytes from Rust and Python, so runs can be recorded and replayed;
7. a small enough footprint that a research group can audit it.

## 2. Alternatives

| Alternative | What it gives | What it lacks for this purpose |
| --- | --- | --- |
| MUSIC 1.2 | MPI spike and continuous ports for NEST and other simulators; low per-tick cost | No exactly-once retry, no integrity check, one MPI job for all programs; in this build wrong content with more than one NEST thread (C1–C3) |
| FMI 3 co-simulation | Standard step interface (`doStep`) for simulators, wide tool support | In-process shared libraries by design; no neural simulators; distributed use needs extra wrappers; no retained results across process failure |
| HLA (IEEE 1516) | Federated simulation with time management | Heavy runtime infrastructure (RTI); no small auditable core |
| gRPC / protobuf | RPC between processes, many languages | At-most-once by default; no retained-result lockstep; HTTP/2 stack |
| ROS 2 / DDS, Zenoh | Publish/subscribe for robots | No lockstep exactly-once step; large runtime; Zenoh 1.9 brought 436 locked crates and recurring advisories to Galadriel |
| ZeroMQ | Message transport | No semantics at all |

NCP's place: the smallest auditable contract that gives exactly-once lockstep exchange with
integrity between processes in two languages. Measured cost (SDK 1.0.1, echo owner): 31–41 µs per
call in Rust, 335–504 µs in Python. Coupled to NEST, 0.2–0.5 ms per exchange (campaign protocol 2).
Faults: 3816 trials, no wrong result accepted; every damaged frame detected; model check of every
interleaving with five fault kinds finds no violation for the v1 client.

## 3. What NCP is today

| Family | Status | Size | Users |
| --- | --- | --- | --- |
| Lockstep local profile `ncp.local-lockstep.v1` | Released (SDK 1.0.1) | Rust 2.4k, Python 1.7k lines; 41 kB descriptor | CREBAIN native body, Galadriel adapter, Prisoma capture |
| Modular local profile `ncp.modular.request.v1` | In SDK, development status | Rust 3.6k, Python 2.1k lines | CREBAIN integrations, Prisoma Agent Bridge, Engram NEST app |
| Wire 1.0 candidate (`ncp-core`, `ncp-zenoh`, TS, C++) | Unreleased rc.1 | Rust 37.7k, C++ 19.5k, TS 5.8k lines | Galadriel root, Prisoma observer, CREBAIN app, Haldir |

## 4. Lenses (100)

Status: OK = holds with evidence; GAP = missing or weak; RISK = holds today but fragile.

| # | Lens | Status | Finding |
| --- | --- | --- | --- |
| 1 | Exactly-once step | OK | Retained result plus digest-bound ack; model P1–P5 hold |
| 2 | Retry after lost response | OK | Same request returns exact retained bytes |
| 3 | Duplicate request | OK | Same sequence and digest returns retained bytes; changed input is a conflict |
| 4 | Reordering | OK | High-water sequence rejects gaps |
| 5 | Foreign run or generation | OK | Binding identity checked first |
| 6 | Corruption | OK | 3119/3119 damaged frames detected |
| 7 | Truncation | OK | Detected; time limit bounds a lost length prefix |
| 8 | Owner crash | OK | Client sees EOF, reports execution unknown, retires |
| 9 | Client crash | OK | Owner retires and exits (120/120) |
| 10 | Stall | OK | Detected at limit plus about 0.1 s |
| 11 | Oversized request | OK | Refused before any write |
| 12 | Oversized result | GAP | Step ran, result cannot be sent; outcome `execution_unknown` is imprecise; run is lost (D4: 10k neurons, 5 ms) |
| 13 | Result size planning | GAP | Backends cannot ask the SDK for their body budget |
| 14 | Bulk data | RISK | Exists only in the modular family; lockstep users have no path above 64 KiB |
| 15 | Frame bound | RISK | One fixed 64 KiB bound for every application |
| 16 | Memory bound | OK | Frames, buffers, slots bounded |
| 17 | Long runs | OK | Soak: 1,000,000 calls, no growth after warm-up, descriptors constant |
| 18 | Determinism of bytes | OK | Canonical JSON; Rust and Python transcripts identical |
| 19 | Cross-language identity | OK | 48-line Rust and 70-line Python transcripts identical across SDKs |
| 20 | Version identity | OK | Profile digest in every binding |
| 21 | Version evolution | GAP | Any descriptor edit makes a new incompatible profile; no rule for optional extensions |
| 22 | Protocol/application separation | GAP | v1 descriptor carries one reference experiment's schemas (RunPlan ≤ 3 entities, ≤ 1024 steps) |
| 23 | Duplicate semantics | GAP | Lockstep and modular each implement admission, retention, acks |
| 24 | Spec size | RISK | 41 kB descriptor plus prose spread over many files |
| 25 | Code size | RISK | Local 10k lines; remote family 63k lines |
| 26 | Dependencies, Rust SDK | OK | serde, serde_json, sha2 |
| 27 | Dependencies, Python SDK | OK | Standard library only |
| 28 | Dependencies, remote family | RISK | Zenoh tree; 12 new RustSec advisory IDs on 22–23 October 2026 alone |
| 29 | Latency, Rust | OK | 31–41 µs per call |
| 30 | Latency, Python | OK | 335–504 µs per call |
| 31 | Round trips per call | GAP | Two; pipelining is proved safe and saves 1.04–1.40× |
| 32 | Overlap of work | GAP | v1 client rule forbids it |
| 33 | Throughput under load | OK | Campaign under normal machine load |
| 34 | NEST coupling cost | OK | 0.2–0.5 ms per exchange after the readback fix |
| 35 | NEST readback | GAP | PyNEST `n_events` copies all events; NCP NEST owners must use the kernel counter and incremental ASCII reads |
| 36 | NEST threads | OK | NCP content exact for 1–8 threads (C1) |
| 37 | MUSIC comparison | OK | Recorded with the content defect stated |
| 38 | Timeouts | OK | Client time limit |
| 39 | Heartbeat during long steps | GAP | A step longer than the limit is a stall; no progress signal |
| 40 | Cancellation | RISK | `abort` exists; mid-step cancellation is not defined |
| 41 | Resume after crash | OK (excluded) | Excluded by design: fresh generation per launch |
| 42 | Checkpoint/restore | RISK | Application-level only (CREBAIN family) |
| 43 | Multi-party coupling | RISK | Host sequences pairwise sessions; no shared step barrier spec |
| 44 | Time semantics | OK | Logical integer microseconds |
| 45 | Units | OK | Application-owned |
| 46 | Clock skew | OK | No wall clock in protocol |
| 47 | Security, local | OK | Private pipes owned by the process that starts both programs |
| 48 | Security, remote | RISK | Only in the unreleased remote family |
| 49 | Authentication | OK (excluded) | Local trust by design |
| 50 | Authorization (Haldir) | OK | Excluded from the local profile; no Haldir cost locally |
| 51 | Denial of service by peer | OK | Bounds on frames, depth, integers |
| 52 | Integer precision | OK | 2^53 bound |
| 53 | Float handling | OK | Round-trip float; NaN rejected |
| 54 | Unicode | OK | Bounded UTF-8; scanner equivalence 5,138,806 inputs |
| 55 | Parser equivalence | OK | Differential testing old/new scanner |
| 56 | Fuzzing | GAP | Differential tests and fault injection only; the repository has no fuzz or property-test target for the local SDK |
| 57 | Model checking | GAP | Model and conformance exist in a benchmark folder, not in the gate |
| 58 | Formal arithmetic | OK | Lean file for the report arithmetic |
| 59 | Conformance vectors | OK | Cross-language probes in the gate |
| 60 | Installed-wheel testing | OK | Fresh-install suites in the release gate |
| 61 | Reproducible builds | OK | Identical digests from two clean clones |
| 62 | Release provenance | OK | Provenance record, checksums |
| 63 | Signatures | RISK | Unsigned by policy; checksums only |
| 64 | Supply chain | OK | cargo-deny, SBOM, advisory pinning |
| 65 | API ergonomics, Python | OK | `LocalClient.call`, `LocalOwner`, `serve_local` |
| 66 | API ergonomics, Rust | OK | Typed operations and outcomes |
| 67 | Error codes | RISK | Small closed set; oversize result shares `execution_unknown` |
| 68 | Diagnostics | RISK | Codes without a size or phase detail |
| 69 | Logging | OK | Application-owned |
| 70 | Observability of a run | OK | Prisoma transcript capture |
| 71 | Replay | OK | Canonical transcripts |
| 72 | Documentation entry point | GAP | README leads with evidence boundaries, not purpose |
| 73 | Legacy material | GAP | Three handoff files, old essays, prototypes, wire-0.8 history next to current docs |
| 74 | Plain language | GAP | Long qualified sentences; not Simplified Technical English |
| 75 | Diagrams | OK | System map, but alt text still says SDK 1.0.0 |
| 76 | Examples | RISK | Real examples live in application repositories |
| 77 | Onboarding time | GAP | No one-page "use NCP in 10 minutes" |
| 78 | Test speed | RISK | Full gate about 65 min |
| 79 | CI cost | OK | Hosted CI green |
| 80 | Benchmark reproducibility | OK | Preregistered protocols, resumable runners, 3 blocks |
| 81 | Benchmark validity | RISK | Run 1 of the NEST campaign had a readback artefact; protocol 2 corrects it |
| 82 | Scientific claims | OK | Evidence boundaries stated |
| 83 | Use case: neural–body loop | OK | Native tests |
| 84 | Use case: monitor | OK | Galadriel adapter |
| 85 | Use case: capture | OK | Prisoma capture |
| 86 | Use case: many entities | RISK | City contract up to 256 entities; lockstep plan limit is 3 |
| 87 | Use case: large spike payloads | GAP | Lens 12 |
| 88 | Use case: camera images | OK | Modular buffers |
| 89 | Use case: slow simulator step | RISK | Lens 39 |
| 90 | Use case: remote machines | RISK | Remote family unreleased |
| 91 | Use case: real time | OK (excluded) | No real-time claim |
| 92 | Use case: GPU simulators | RISK | Untested |
| 93 | Use case: C++ simulators | RISK | Remote family has C++; local SDK does not |
| 94 | Use case: notebook use | OK | Python stdlib SDK |
| 95 | Governance | OK | Owner decisions recorded |
| 96 | Versioning policy | RISK | Two version lines (SDK, wire) confuse readers |
| 97 | Naming | GAP | "local", "modular", "wire 1.0" are not self-explaining |
| 98 | Maintenance burden | GAP | Three families to keep consistent |
| 99 | Justification statement | GAP | Scattered over RATIONALE.md and reports |
| 100 | Exit strategy | OK | Plain JSON frames; any language can implement the core |

## 5. Ranked findings

1. Three families overlap. Lockstep and modular duplicate exchange semantics; the remote family is
   most of the code and most of the dependency risk.
2. The protocol core and one reference application's data are in one descriptor.
3. Results above 64 KiB lose the run, and the code does not say that the step ran.
4. Two round trips per call; pipelining is proved safe and measured faster.
5. The model check and conformance exist but do not run in the gate.
6. NEST owners pay O(total spikes) per read with the naive readback.
7. Documentation leads with qualifications; legacy files sit next to current ones.

## 6. Options

- **A. Consolidate the local families into one protocol, NCP local 2.** One exchange core (binding,
  sequence, retained result, digest-bound ack, outcomes) with a small descriptor; a declared frame
  bound per binding up to a hard cap; an optional bulk-buffer extension; pipelined client allowed;
  a precise code for a result that ran but cannot be sent; application schemas move to their
  applications. Model check and conformance in the gate. Keep wire 1.0 as a separate remote
  family, clearly labelled, and decide its future with its users later. Consumers in scope migrate;
  Engram needs its own owner to move (it can stay on 1.0.1 meanwhile).
- **B. Option A plus fold the remote family into the same core** as a transport binding. Largest
  reduction in code and dependencies; touches Haldir, Galadriel, Prisoma observer, CREBAIN app.
  Multi-week.
- **C. Keep the families; fix without breaking**: SDK 1.1 body-budget helper, model check in the gate,
  NEST guidance, documentation and legacy clean-up.

Recommendation: A now, with C's non-breaking items done first; B as a separate decision after A.

## 7. Decision and refinement (23 October 2026)

The owner chose option B. A follow-up question about several embodied agents (drones, robots)
with Engram and other projects corrected the first transport answer ("NCP without Zenoh").

Refined outcome:

- One NCP message model (identity binding, sequence, canonical JSON, digest, bounded typed bodies)
  with two interaction patterns:
  - **exchange**: lockstep request/response, retained results, digest-bound acks (simulation steps,
    anything that must never run twice);
  - **stream**: sequence-numbered publications with freshness bounds and loss detection, no retries
    (live sensor data, fan-out to monitors and recorders).
- Two bindings:
  - **stream binding** over pipes and TCP, no extra dependencies (all simulation work);
  - **Zenoh binding**, optional crate, off by default, maintained in NCP, for live multi-robot
    deployments (discovery, routing over lossy links, shared memory, zenoh-pico devices, ROS 2
    robots through rmw_zenoh).
- Leanness comes from removing the duplicate protocol stack (the 33k-line ncp-core for the Zenoh
  path), not from removing Zenoh. Projects that do not run robots never compile Zenoh.
- Safety: simulated loops never actuate hardware; live commands only through Haldir's gate
  (signed intent, lease, TTL) over the live binding. Haldir keeps Zenoh, on the new core.
- New benchmark: multi-agent scaling, 1 to 256 sessions, Rust and Python hosts, pipelining on and
  off, three randomized blocks. Estimate to test: 100 agents need about 3.6 ms per tick with a
  serial Rust host and about 45 ms with a serial Python host.
