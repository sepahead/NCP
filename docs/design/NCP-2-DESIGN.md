# NCP 2 design record

Status: decided on 23 October 2026 by the owner (option B of the council review).
The normative rules are in the [specification](../../spec/NCP-2.md). This record explains why.

## 1. The problem

Research on closed loops couples programs that different people write and run: a neural simulator (NEST, through Engram), a body or world simulator (CREBAIN), monitors (Galadriel), recorders (Prisoma), and, on real machines, an authorization gate (Haldir).
Each program keeps its own process, language, dependencies, and failures.
The coupling must:

1. run each step exactly once, also when a response is lost and the request is sent again;
2. detect damaged, foreign, repeated, reordered, and missing messages;
3. give a known outcome for every fault and never accept a wrong result;
4. move bulk data, such as spikes and images, without unbounded memory;
5. give the same results from Rust and Python and from any binding;
6. leave a record that proves what crossed the coupling and in which order;
7. add as little time per step as possible;
8. stay small enough for a research group to read and check.

## 2. What existed before

NCP 1 had three overlapping families:

| Family | Status | Size |
| --- | --- | --- |
| Lockstep local profile `ncp.local-lockstep.v1` | Released as SDK 1.0.0 and 1.0.1 | Rust 2.4k, Python 1.7k lines; 41 kB descriptor |
| Modular local profile `ncp.modular.request.v1` | In the SDK, development status | Rust 3.6k, Python 2.1k lines |
| Wire 1.0 candidate (`ncp-core`, `ncp-zenoh`, TypeScript, C++) | Unreleased | Rust 37.7k, C++ 19.5k, TypeScript 5.8k lines |

The lockstep and modular families each implemented admission, kept results, and acknowledgements.
The v1 descriptor mixed the protocol with one reference experiment's data types.
Each lockstep call needed two round trips, and results above 64 KiB ended the run.
The remote family carried most of the code and all of the October RustSec advisories.

## 3. Measured starting point

All values are medians from preregistered campaigns on one Apple M4 Max computer in normal use.

| Measure | NCP 1.0.1 | Source |
| --- | --- | --- |
| Rust client and Rust echo owner, one call | 35.6 µs (two round trips) | `benchmarks/pipelined-ack` |
| Python client and Python echo owner, one call | 466 µs | `benchmarks/pipelined-ack` |
| NEST coupling, cost per exchange, Rust host | 0.23–0.29 ms | `benchmarks/nest-campaign`, protocol 2 |
| NEST coupling, cost per exchange, Python host | 0.48–0.63 ms | same |
| MUSIC, cost per tick | indistinguishable from NEST alone | same |
| MUSIC content with more than one NEST thread | wrong for most channels | `benchmarks/nest-campaign/music-threads` |
| Faults | 3816 trials, no wrong result accepted | `benchmarks/fault-campaign` |

## 4. Assumptions questioned and decisions

Each row names an assumption of NCP 1, the question, and the decision.

| # | Assumption | Question | Decision |
| --- | --- | --- | --- |
| 1 | Programs must run in separate processes. | Is in-process coupling enough? | Keep processes. They give separate languages, dependencies, lifecycles, and failures. Minimize the cost instead. |
| 2 | A call needs a separate acknowledgement round trip. | Can the acknowledgement travel with the next request? | Yes. The next request carries the identity of the last response. One round trip per call, and the session becomes a hash chain. The model check covers it (section 7). |
| 3 | Digests need a canonical encoding or a typed projection. | What must the digest identify? | The exact bytes that crossed the coupling. Hash the frame bytes. No canonical encoding, no value walk, and both languages hash in native code. |
| 4 | JSON numbers and base64 carry bulk data. | What is cheapest for arrays? | Binary attachments, aligned to 8 bytes, referenced from JSON as typed arrays. Receivers read them in place. |
| 5 | One fixed 64 KiB frame bound fits all. | Who knows the right bound? | The session. The client requests a bound at `open`; the owner can lower it; 64 MiB is the largest. |
| 6 | A separate buffer system is needed for bulk data. | Do larger frames and attachments cover the uses? | Yes for spikes, readouts, and camera images up to tens of megabytes. Remove the buffer system. Larger objects travel out of band with a digest in the message. |
| 7 | The protocol defines roles and data types. | Who owns them? | The applications. The core knows only `open`, `close`, and the application's operation names. Contracts are documents identified by their digest. |
| 8 | Remote use needs its own protocol family. | What does remote use need from the protocol? | The same frames over another binding. One core, two bindings. |
| 9 | Zenoh is required. | Which uses need a routing fabric? | Live fleets of robots or drones: discovery, many subscribers, lossy links, embedded devices. Keep Zenoh as an optional binding, built with TLS only, without QUIC. Everything else uses pipes, Unix sockets, or TCP. |
| 10 | Every use is a lockstep call. | Do live sensors need exactly-once? | No. Old sensor values are useless. Streams: sequenced, hash-chained, no retries, loss detected. |
| 11 | Recording is a separate application role. | Can recording be part of every session? | Yes. Any binding can write a transcript; a verifier checks the chain offline. Prisoma builds on this. |
| 12 | The SDKs need many dependencies. | What is the minimum? | Python: standard library only. Rust: `serde`, `serde_json`, `sha2`, and `socket2` for socket buffer sizes (decision 16). Zenoh only in the optional binding. |
| 13 | Two version lines (SDK and wire) are clear. | Do users understand them? | No. One version: NCP 2 for protocol and SDKs. |
| 14 | The receiver must compute every digest again. | What does the second hash protect? | Only against damage between the endpoints. Identities, the acknowledgement chain, and transcripts need one hash for each frame, and the sender computes it. On a pipe pair or a Unix domain socket with no program in between, a receiver may skip the comparison (specification 3.4). The default stays on. Measured with Rust at both ends: 34.9 to 24.6 µs at 1788 spikes, 974 to 568 µs at 1 MiB. |
| 15 | A receiver must know every code. | What happens when a later version adds a code or an `open` response member? | A strict 2.0 client would read the response as a bad frame. Receivers use the outcome of an unknown code, and clients ignore unknown `open` response members (specification 7.5 and 7.1). NCP 2 can grow without a new protocol version. |
| 16 | The kernel's default socket buffers suit NCP. | Do they suit large frames? | No. macOS gives a Unix domain socket 8 KiB buffers. A 1 MiB echo between two Python threads took 1391 µs with them and 121 µs with 1 MiB buffers; over TCP loopback, 335 and 168 µs. Both SDKs set 1 MiB send and receive buffers on Unix domain sockets and TCP connections (specification 9.1, rule 8). The kernel uses the memory only while data waits. In Rust this needs `socket2`, because the standard library cannot set buffer sizes and the crate forbids `unsafe` code. |

## 5. Rejected alternatives

| Alternative | Why it was rejected |
| --- | --- |
| Pipeline acknowledgement and next request as two frames | Works and is proved safe, but piggybacking the acknowledgement in the request does the same with fewer frames and no window between them. |
| CBOR or another binary encoding for the whole message | Needs a library in Python. JSON headers stay small because bulk data is in attachments. |
| Canonical JSON (RFC 8785) | Number formatting differs between languages. Hashing the exact bytes makes canonical form unnecessary. |
| Chunked transfer of large results | Adds a second protocol. Per-session bounds and attachments cover the measured uses. |
| Shared memory for local frames | Fastest for very large data, but adds platform code and lifetime rules. Measure first; add only for a demonstrated need. |
| A Rust accelerator for the Python SDK (a PyO3 module) | Measured warm: decoding a step request takes 4.4 µs, and encoding a 21.8 kB spike response 16.1 µs, of which 9.4 µs is the SHA-256 digest that a Rust codec also computes. A Rust codec could save about 10 to 12 µs of a NEST exchange that costs 30 to 150 µs: the codec time that is not hashing, and about 2 µs of hashing, because Rust's `sha2` is faster than the NEST environment's OpenSSL. Inside the NEST process the owner's code runs 1.6 times (counts) to 3.2 times (spikes) slower than without NEST; how much of that a Rust codec would remove is not measured ([profile](../../benchmarks/nest-campaign/profiling/README.md)). It would add a compiled extension to every Python installation. Reconsider when a profile on a target platform shows the Python codec as most of the coupling cost. |
| gRPC as the transport | At-most-once by default, HTTP/2 stack, no hash chain. NRP-core uses it; we compare against it instead. |
| ROS 2 as the live binding | Large runtime for every user. A later bridge can map NCP streams and commands to ROS 2 for robots that use it. Zenoh on the same network does not make NCP messages ROS 2 messages. |
| Removing Zenoh entirely | Leaves live fleets without discovery and fan-out. Kept as an option instead. |
| No digest | Removes the identities, the acknowledgement chain, and transcripts: the reasons for NCP. |
| A faster hash that is not SHA-256 (BLAKE3, xxHash) | Not in the Python standard library. SHA-256 has hardware support on ARMv8 and x86: 2968 MB/s with `sha2` 0.11 and 3464 MB/s with OpenSSL on the computer of section 3. |
| Hashing each frame while it arrives, to overlap the hash with the transfer | Measured: no gain on pipes (974 to 940 µs at 1 MiB, Rust at both ends). The receiver's copy and hash run in series either way. Only streaming at both ends would overlap the two hashes; that couples the owner to the binding and gains nothing below 64 KiB. |
| A hash chain over transcript records | The session chain already commits to every accepted exchange. A transcript that several sessions share records the arrival order, not the execution order, so it cannot replace a deterministic order (section 11). |
| Consensus inside NCP | Existing implementations do it better (etcd, openraft), and it makes progress only under timing assumptions. NCP can carry their messages. |

## 6. Red-team review

| Attack or fault | Result |
| --- | --- |
| Replay of a frame from another session | `wrong_session` |
| Replay of an earlier request in the same session | `seq_stale`, or the kept response if it is the last one |
| A different request with the same sequence number | `seq_conflict` |
| Acknowledgement of a response that the client did not get | `ack_mismatch`; nothing executes |
| Damaged frame | Digest mismatch: bad frame. A receiver that turned off the comparison on a local binding (specification 3.4) does not detect it while the session runs; the transcript verifier does. |
| Peer that computes valid digests for false content | Not prevented by NCP. Bindings authenticate peers (operating system, TLS); applications add signed authority. |
| Memory exhaustion by length fields | Lengths are checked against the bound before allocation |
| Slow sender | Per-frame time limits in the bindings |
| Lost framing on a byte stream | Magic check; the connection closes |
| Parser differences | Duplicate names, large integers, unpaired surrogates, and deep nesting are rejected in both languages |
| Owner that sends a stale response | The client checks `request` and `seq` |
| Two owners on one Zenoh key | Each owner has its own key; the client checks the session |
| A crash during a step | `owner_failure` or a closed connection: the client treats the step as possibly executed and ends the session |
| Result larger than the bound | `result_too_large` says that the step executed; the client can raise the bound for the next run |
| Lost stream messages | Reported as a gap with the count |
| Changed or inserted stream message | Broken chain: not accepted |

## 7. Test strategy

Every level runs in the gate, except the campaigns, which run before a release and after each change that can affect their results.

| Level | What it checks | How |
| --- | --- | --- |
| Unit | Each function of each SDK | Standard test runners |
| Conformance | Every MUST of the specification | Shared vectors in `conformance/`: frames, arrays, owner rules, client rules, streams, transcripts. Both SDKs must give identical results. |
| Cross-language | Rust and Python together | Rust client with Python owner and the reverse, with attachments, over pipes, Unix domain sockets, and TCP |
| Model | Safety in every reachable state | Exhaustive search with lost, repeated, delayed, and changed frames and crashes; a mutation self-test shows that each property catches a defect; the real owners answer like the model on random traces |
| Fuzz | Decoders under arbitrary input | Differential: `conformance/fuzz.py` sends random, edited, and damaged frames with valid digests, and structured array references, to both decoders. Acceptance, messages, identities, and array bytes must be equal, and no decoder may crash. |
| Modular composition | The ecosystem as a set of optional modules | A host with neural, body, monitor, and recorder modules in every subset of the optional ones; faults injected into each module; Prisoma verifies the transcript of every run; two runs with the same seed give the same message bodies |
| Faults | Behavior under real faults | Bit flips, truncation, killed processes, stalls, oversized frames, and raising backends, for each binding |
| Soak | Resources over long runs | Memory and open descriptors over 10^6 calls |
| Performance | The targets in section 8 | Preregistered protocols, three shuffled blocks |
| Consumers | Each project's own gates | CI of CREBAIN, Galadriel, Prisoma, Haldir |

## 8. Performance targets and comparisons

Targets for NCP 2 on the same computer as section 3, tested by preregistered protocols:

| Measure | NCP 1.0.1 | NCP 2 target | NCP 2 measured |
| --- | --- | --- | --- |
| Rust client and Rust echo owner, one call | 35.6 µs | ≤ 15 µs | 9.1 µs ([comparison benchmark](../../benchmarks/comparison/README.md), H2) |
| Python client and Python echo owner, one call | 466 µs | ≤ 150 µs | 38.6 µs (H2) |
| NEST coupling, cost per exchange, Rust host | 0.23–0.29 ms | ≤ 0.10 ms | 0.036 ms in run 1 of [NEST protocol 3](../../benchmarks/nest-campaign/README.md) (G2), whose timing was disturbed; protocol 4 repeats it |
| Spike payloads (D4 of the NEST campaign) | 0.4–1.4 ms, and failure above 64 KiB | ≤ 0.15 ms, no failure | No failure: every D4 run delivered the exact spikes, also with 10,000 neurons at 5 ms. The cost is not established, because the timing of run 1 was disturbed; protocol 4 repeats it. 1788 spikes in one call take 32.8 µs (Rust) and 67.8 µs (Python) without NEST |

In the comparison benchmark, all five preregistered hypotheses held: NCP 2 is 4.2 to 165 times faster than NCP 1.0.1, adds 4.6 µs to a raw pipe, and is faster than gRPC and Zenoh in Rust and than gRPC and HTTP/1.1 in Python up to 1788 spikes. At 1 MiB, systems without an integrity check are faster, by about the time of one SHA-256 digest.

Comparisons, with the same workloads, shown as figures in this repository:

- Exchange latency and throughput for payloads from 0 bytes to 1 MiB: NCP 2 (Rust, Python), NCP 1.0.1, gRPC (Rust and Python; the transport that NRP-core recommends), HTTP with JSON (NRP-core's JSON engines), ZeroMQ request and reply, and Zenoh query and reply. A raw pipe echo gives the lower bound.
- NEST coupling: NCP 2, NCP 1.0.1, MUSIC, and a raw round trip to an echo process after each interval, for each network, size, thread count, and interval. The raw round trip is the cost that every coupling through a pipe or a socket pays after each interval, gRPC included; the comparison benchmark measures gRPC on the same payloads, so a gRPC owner of NEST would add little.
- Correct-content throughput: the wall time of a run whose delivered spikes are exact. MUSIC is exact only with one NEST thread in this build; NCP is exact with any thread count.
- Multi-agent scaling: 1 to 256 sessions, Rust and Python hosts.
- MPI: the rank-0 owner pattern with 1 to 8 MPI ranks on one computer.
- A feature matrix of NCP 2, MUSIC, NRP-core, FMI 3 co-simulation, gRPC, ROS 2, and Zenoh.

Every figure states the computer, the software versions, the load, and what it does not show.

## 9. Migration

Each step leaves every project working.

1. NCP: the reference SDKs (`python/`, `rust/`), the conformance vectors, the model, the transcript verifier, and the benchmarks, next to the old code.
2. Local users: CREBAIN native body, Galadriel adapter, Prisoma capture.
3. Former modular users: CREBAIN integrations, Prisoma Agent Bridge.
4. The optional Zenoh binding; then the former wire 1.0 users: Galadriel's NCP crate, Prisoma's observer, CREBAIN's application, and Haldir (a new lineage epoch for its NCP pin).
5. Engram's NEST application, in agreement with its owner.
6. Removal of the old families from NCP's main branch. Their last state stays reachable through the tag `ncp-1-archive`.
7. Release of NCP 2.0 after its gates and the owner's approval.

## 10. Risks

| Risk | Control |
| --- | --- |
| The migration touches every project | One project at a time, each with its own gates, and the old SDK stays available until the last user moves |
| Performance targets are not met | Targets are tested, not assumed; a miss is reported with its cause |
| Engram's owner is another agent | NCP 1.0.1 stays usable; the migration is offered, not forced |
| Haldir's lineage | Its NCP move needs an owner-signed epoch like epochs 20 and 21 |
| Hidden users of the TypeScript and C++ code | Checked before removal; a small NCP 2 implementation replaces them where needed |
| Misuse of the optional digest comparison | Off only by an explicit option; the documentation states the conditions; the transcript verifier always compares |

## 11. Coordination across sessions

NCP 2 makes each session exactly-once and verifiable. Applications build coordination between sessions on these properties.
This section states the limits, what NCP gives, the patterns that work with NCP 2 as specified, and the profiles that are planned or deferred.

### 11.1 Limits that no protocol removes

- **Consensus.** No deterministic algorithm reaches agreement on an asynchronous network if one process can crash (Fischer, Lynch, and Paterson, 1985). Raft and Paxos are always safe and make progress only while the network behaves.
- **Atomic commit.** Two-phase commit is safe, but it blocks if the coordinator fails after the participants voted yes. Commit that does not block needs consensus (Gray and Lamport, 2006) or a bound on message delay.
- **Lossy links.** No finite exchange of messages gives two parties common knowledge of a decision (the two generals problem).
- **Physical actions.** A robot cannot undo a movement. For robots, an atomic action means a check of feasibility and a coordinated start, not a rollback.

### 11.2 What NCP gives

- **Retry-safe messages.** Each call executes at most once, and its outcome says whether it executed: yes, no, or unknown. After a failure, at most one call in each session is unknown.
- **Verifiable references.** Identities are SHA-256 digests of exact bytes. A message can name other messages by identity, and no message can name a message that was made after it.
- **Evidence.** Each session is one hash chain. The identity of the last response commits to every accepted exchange of the session (specification, property 7.7.6).
- **A vote step.** An owner checks a request (`validate`) before it executes it (`execute`), and a rejection changes no state.

### 11.3 Patterns with NCP 2 as specified

| Pattern | How |
| --- | --- |
| One host, many owners (1 → N) | One session for each owner. The SDKs send one request to each session and wait for all responses (`call_all`). Sessions are independent: a failure ends only its own session. |
| Many clients, one owner (N → 1) | One owner process serves one session for each connection. The application decides how requests from different sessions combine. |
| Many to many (N → N) | Sessions for commands, streams for sensors and telemetry. Across computers, the Zenoh binding routes and discovers. |
| Order across sessions | An owner that serves many sessions executes their requests in an order that its application controls. For a replayable order, the application makes the order deterministic (rounds, section 11.4) instead of recording an arrival order. |
| Atomic action across owners | Two-phase commit in the application: `prepare` (validate and hold) to every owner, then `commit` or `abort`. NCP makes each message exactly-once and each vote verifiable by its identity. The limits of section 11.1 apply. |
| Replicated owners | An external consensus service, such as etcd or openraft, chooses the active owner. NCP does not include consensus. |
| Clusters | Specification section 16. |

### 11.4 Planned and deferred profiles

| Profile | What it adds | Status and condition |
| --- | --- | --- |
| Rounds | An owner applies round k only when every agent sent it or a deadline passed, in a fixed order, and returns to each agent the identities of the requests that it applied. Multi-agent steps become deterministic and verifiable. | Planned; built with the multi-agent benchmark, which exercises it. Names `ncp.round` and `ncp.round_record`. |
| Zenoh binding | Routing, discovery, and lossy links for fleets (specification 9.2). | Planned, as an optional package. |
| Two-phase actions | Operations `ncp.prepare`, `ncp.commit`, `ncp.abort`, and `ncp.status`, with a deadline and an optional start time. | Deferred until a consumer needs it. Needs a model check with crashes and losses first. |
| Causal references | A body member `ncp.refs` lists the identities that a message depends on; a verifier builds the happens-before graph across transcripts. | Deferred until a tool such as Prisoma needs the graph. Applications can put identities in their bodies today. |
| Session resume | A client continues a session after an owner restart; "unknown" becomes "executed" or "not executed". | Deferred. It needs durable session state before each response (one fsync per call) and an application that restores its own state, which NEST cannot do. |

Specification section 15 reserves the `ncp.` names for these profiles.
