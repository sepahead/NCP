# NCP 2 design record

Status: decided on 23 October 2026 by the owner (option B of the council review). Revision 3 of the specification, of 13 November 2026, adds the decisions of section 12.
The normative rules are in the [specification](../../spec/NCP-2.md). This record explains why.

## 1. The problem

Research on closed loops couples programs that different people write and run: a neural simulator (NEST, through Engram), a body or world simulator (CREBAIN), monitors (Galadriel), recorders (Prisoma), and, on real machines, an authorization gate (Haldir).
Each program keeps its own process, language, dependencies, and failures.
The coupling must:

1. run each step at most once, also when a response is lost and the request is sent again, and exactly once when a request sent again reaches the same owner;
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
| 14 | The receiver must compute every digest again. | What does the second hash protect? | Only against damage between the endpoints. Identities, the acknowledgement chain, and transcripts need one hash for each frame, and the sender computes it. On a pipe pair or a Unix domain socket with no program in between, a receiver may skip the comparison (specification, section 3, rule 5). The default stays on. Measured with Rust at both ends: 34.9 to 24.6 µs at 1788 spikes, 974 to 568 µs at 1 MiB. |
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
| Consensus inside NCP | Existing implementations do it better (etcd, openraft), and it makes progress only under timing assumptions. NCP can carry their messages. |

## 6. Red-team review

| Attack or fault | Result |
| --- | --- |
| Replay of a frame from another session | `wrong_session` |
| Replay of an earlier request in the same session | `seq_stale`, or the kept response if it is the last one |
| A different request with the same sequence number | `seq_conflict` |
| Acknowledgement of a response that the client did not get | `ack_mismatch`; nothing executes |
| Damaged frame | Digest mismatch: bad frame. A receiver that turned off the comparison on a local binding (specification, section 3, rule 5) does not detect it while the session runs; the transcript verifier does. |
| Peer that computes valid digests for false content | Prevented when both sides share a key: every frame then carries an HMAC that only a holder of the key can make (specification 13.2). Without a key, the bindings authenticate peers (operating system, TLS, Zenoh access control), and applications add signed authority. |
| Copy of a request of an earlier opening, after the owner restarted or forgot the session | `session_expired` while the owner holds no session. Once a delayed copy of `open` opened the session again, `ack_mismatch` or `seq_gap`: each opening has its own nonce, so the chains of two openings share no request. The client ends the session with the request possibly executed (rule 7.6.4). |
| Owner that stops | `shutdown`: the request never runs; a copy of the kept request still gets the kept response |
| Memory exhaustion by length fields | Lengths are checked against the bound before allocation |
| Slow sender | A time limit for each frame (`Limits.frame_timeout` in both SDKs, 30 s by default in the servers), and an optional limit for idle sessions |
| Lost framing on a byte stream | Magic check; the connection closes |
| Parser differences | Duplicate names, large integers, unpaired surrogates, and deep nesting are rejected in both languages |
| Owner that sends a stale response | The client checks `request` and `seq` |
| Two owners on one Zenoh key | Prevented by rule 9.2.5 and Zenoh access control; NCP does not detect it |
| A crash during a step | `owner_failure` or a closed connection: the client treats the step as possibly executed and ends the session |
| Result larger than the bound | `result_too_large` says that the step executed; the client can raise the bound for the next run |
| Lost stream messages | Reported as a gap with the count |
| Changed stream message, or one inserted with the expected `seq` | Broken chain: not accepted. A message inserted with a larger `seq` is accepted and reported as a gap; integrity against insertion rests on the binding's authentication (section 13) |

## 7. Test strategy

Every level runs in the gate, except the campaigns, which run before a release and after each change that can affect their results.

| Level | What it checks | How |
| --- | --- | --- |
| Unit | Each function of each SDK | Standard test runners |
| Conformance | Every requirement of the specification | Shared vectors in `conformance/`: frames, messages, authenticated frames, owner rules, client rules, streams, transcripts, contracts, and schemas. Both SDKs must give identical results. [`conformance/requirements.json`](../../conformance/requirements.json) maps each requirement line of the specification to the vectors, tests, model checks, and Lean claims that test it, and a check keeps the map complete. |
| Cross-language | Rust and Python together | Rust client with Python owner and the reverse, with attachments, over pipes, Unix domain sockets, and TCP |
| Model | The eight properties of section 7.7 in every reachable state | [`model/simulate.py`](../../model/simulate.py) drives the real Python client and owner through every reachable state of bounded runs with lost, repeated, and reordered frames, restarts and stops of the owner, faulty clients, and broken connections; a mutation self-test of eleven defects. [`model/conformance.py`](../../model/conformance.py): the Python and Rust owners answer like the compiled Lean model on random traces with copies, restarts, and stops |
| Proof | Owner and client safety for every sequence of inputs, and progress without faults | Lean 4 models of the owner (rules 7.3.2 to 7.3.13) and of a client that follows section 7.6, with nineteen claims in `formal/`; only Lean's standard axioms; every proof replayed by the kernel; eleven model mutants each break the claim that they target. The SDKs and the codec are tested, not proved. |
| Fuzz | Decoders and message checks under arbitrary input | Differential: `conformance/fuzz.py` sends random, edited, and damaged frames with valid digests, structured array references, and messages with changed members, to both implementations, with bounds around each frame's length. Acceptance, messages, identities, array bytes, and the request, response, and stream forms must be equal, and no implementation may crash. |
| Modular composition | The ecosystem as a set of optional modules | [`python/tests/test_composition.py`](../../python/tests/test_composition.py), in the gate: a host with stand-in neural, body, monitor, and recorder modules, each its own process, in every subset of the optional monitor and recorder, without a fault and with a kill, a stall, or a raising handler in each module present (40 runs of 40 steps). A fault in the neural module or the body ends the run at its step, executed `unknown`; a fault in an optional module never stops the loop; every transcript verifies with the NCP verifier, except the unanswered request of a killed or stalled module; two runs with the same seed give the same message bodies, and optional modules change none of the loop's bodies. Prisoma verifies transcripts once it uses NCP 2 |
| Faults | Behavior under real faults | Bit flips, truncation, repeated frames, killed processes, stalls, oversized frames, and raising handlers. Over pipes, with the Python client and both owners, [fault-campaign protocol 3](../../benchmarks/fault-campaign/README.md#results-of-protocol-3) (4,170 trials); over Unix domain sockets and TCP, with the Python and the Rust client and both owners, [protocol 5](../../benchmarks/fault-campaign/README.md#results-of-protocol-5) (4,560 trials). No wrong result, no step run twice or out of order, and no false report of a step |
| Soak | Resources over long runs | Memory and open descriptors over 10^6 calls. Protocol 3: nine soaks of 200,000 to 1,000,000 calls, memory growth at most 0.69 %, constant descriptors |
| Performance | The targets in section 8 | Preregistered protocols, three shuffled blocks |
| Consumers | Each project's own gates | CI of CREBAIN, Galadriel, Prisoma, Haldir |

## 8. Performance targets and comparisons

Targets for NCP 2 on the same computer as section 3, tested by preregistered protocols:

| Measure | NCP 1.0.1 | NCP 2 target | NCP 2 measured |
| --- | --- | --- | --- |
| Rust client and Rust echo owner, one call | 35.6 µs | ≤ 15 µs | 9.1 µs ([comparison benchmark](../../benchmarks/comparison/README.md), H2); 9.0 µs in protocol 2, with a 99th percentile of 12.4 µs |
| Python client and Python echo owner, one call | 466 µs | ≤ 150 µs | 38.6 µs (H2); 38.8 µs in protocol 2, with a 99th percentile of 52.5 µs |
| NEST coupling, cost per exchange, Rust host | 0.23–0.29 ms | ≤ 0.10 ms | 0.032 ms, the median of six configurations at Δ = 1 ms ([NEST protocol 5](../../benchmarks/nest-campaign/README.md#results-of-protocol-5), G2). Measured inside the processes, an exchange adds 23 to 32 µs, against 228 to 248 µs for NCP 1.0.1 (G6) |
| Spike payloads (D4 of the NEST campaign) | 0.4–1.4 ms, and failure above 64 KiB | ≤ 0.15 ms, no failure | No failure: NCP 2 carried every step, also with 10,000 neurons at 5 ms, and the number of spikes at the host equalled the recorder's total in every run (protocols 3 and 5). Both hosts received exactly NEST's spikes, each neuron and time, in all 96 trials of [content protocol 2](../../benchmarks/nest-campaign/README.md#results-of-content-protocol-2), with up to 8 threads and 10,000 neurons. Measured inside the processes, an exchange adds 36 to 119 µs (protocol 5, G7). From the wall times: 0.044 to 0.054 ms in three configurations, and 0.200 ms with 10,000 neurons at 5 ms, above the target (G3), where NEST's own work varied between runs by more than the time of an exchange. 1788 spikes in one call take 32.8 µs (Rust) and 67.8 µs (Python) without NEST |

In the comparison benchmark, all five preregistered hypotheses held: NCP 2 is 4.2 to 165 times faster than NCP 1.0.1, adds 4.6 µs to a raw pipe, and is faster than gRPC and Zenoh in Rust and than gRPC and HTTP/1.1 in Python up to 1788 spikes. At 1 MiB, systems without an integrity check are faster, by about the time of one SHA-256 digest.

Comparison protocol 2 repeated the benchmark on the power adapter under controlled conditions: H1 to H5 held again, and when gRPC, ZeroMQ, HTTP/1.1, and Zenoh made the same SHA-256 check of each message as NCP 2, the fastest NCP 2 arm was faster than all of them in both languages at every size, 1 MiB included ([results](../../benchmarks/comparison/README.md#results-of-protocol-2)).

The [multi-agent benchmark](../../benchmarks/multi-agent/README.md) held all 13 of its hypotheses. With `call_all`, one host finished a round over 256 owners in 0.92 ms (Rust) and 2.8 ms (Python), 1.9 to 3.8 times faster than one thread for each session or one call after another; NCP 2 added 2.2 µs (Rust) and 9.2 µs (Python) per session to plain pipes. In Rust, eight threads that each use `call_all` on a share of the sessions were faster from 64 owners on; in Python, threads did not help. In rounds, 1 to 256 agents always agreed on the world's state, which did not depend on the order of arrival; rounds cost 1.4 to 1.5 times as much as applying requests on arrival up to 64 agents, and 2.3 times with 256. An MPI owner with 1 to 8 ranks added 4 to 11 µs per call up to 1788 spikes, with every spike exact.

In NEST protocol 5, NCP 2 met the targets for the time measured inside the processes (G6, G7) and for the median cost per exchange (G2). The two hypotheses that compare the wall times of separate runs failed in one configuration each (G1, G3). There, NEST's own work varied between runs by more than the time of an exchange, so whether a coupling slows NEST's own work is open.

Comparisons, with the same workloads, shown as figures in this repository:

- Exchange latency and throughput for payloads from 0 bytes to 1 MiB: NCP 2 (Rust, Python), NCP 1.0.1, gRPC (Rust and Python; the transport that NRP-core recommends), HTTP with JSON (NRP-core's JSON engines), ZeroMQ request and reply, and Zenoh query and reply. A raw pipe echo gives the lower bound.
- NEST coupling: NCP 2, NCP 1.0.1, MUSIC, and a raw round trip to an echo process after each interval, for each network, size, thread count, and interval. The raw round trip is the cost that every coupling through a pipe or a socket pays after each interval, gRPC included; the comparison benchmark measures gRPC on the same payloads, so a gRPC owner of NEST would add little.
- Correct-content throughput: the wall time of a run whose delivered spikes are exact. MUSIC is exact only with one NEST thread in this build; NCP 1.0.1 and NCP 2 are exact with any thread count (content protocols 1 and 2).
- Multi-agent scaling: 1 to 256 sessions, Rust and Python hosts ([multi-agent benchmark](../../benchmarks/multi-agent/README.md), parts F and R).
- MPI: the rank-0 owner pattern with 1 to 8 MPI ranks on one computer (multi-agent benchmark, part M).
- A feature matrix of NCP 2, MUSIC, NRP-core, FMI 3 co-simulation, gRPC, ROS 2, and Zenoh: [NCP 2 compared with other tools](NCP-2-COMPARISON.md).

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

NCP 2 makes each request of a session run at most once, with a known or possibly-executed outcome, and each session verifiable. Applications build coordination between sessions on these properties.
This section states the limits, what NCP gives, the patterns that work with NCP 2 as specified, and the profiles that are planned or deferred.

### 11.1 Limits that no protocol removes

- **Consensus.** No deterministic algorithm reaches agreement on an asynchronous network if one process can crash (Fischer, Lynch, and Paterson, 1985). Raft and Paxos are always safe and make progress only while the network behaves.
- **Atomic commit.** Two-phase commit is safe, but it blocks if the coordinator fails after the participants voted yes. Commit that does not block needs consensus (Gray and Lamport, 2006) or a bound on message delay.
- **Lossy links.** No finite exchange of messages gives two parties common knowledge of a decision (the two generals problem).
- **Physical actions.** A robot cannot undo a movement. For robots, an atomic action means a check of feasibility and a coordinated start, not a rollback.

### 11.2 What NCP gives

- **Retry-safe messages.** Each call executes at most once, and its outcome says whether it executed: yes, no, or unknown. After a failure, at most one call in each session is unknown.
- **Verifiable references.** Identities are SHA-256 digests of exact bytes. A message can name other messages by identity, and no message can name a message that was made after it.
- **Evidence.** Each session is one hash chain. The identity of the last response commits to every admitted exchange of the session (specification, section 7.7, property 8).
- **A vote step.** An owner checks a request (`validate`) before it executes it (`execute`). A declined request changes no state, its answer is kept, and it never executes.

### 11.3 Patterns with NCP 2 as specified

| Pattern | How |
| --- | --- |
| One host, many owners (1 → N) | One session for each owner. The SDKs send one request to each session and wait for all responses (`call_all`): every request goes out before the first response is read, so the owners work at the same time without a thread for each session. Sessions are independent: a failure ends only its own session. |
| Many clients, one owner (N → 1) | One owner process serves one session for each connection. The application decides how requests from different sessions combine. |
| Many to many (N → N) | Sessions for commands, streams for sensors and telemetry. Across computers, the Zenoh binding routes and discovers. |
| Order across sessions | An owner that serves many sessions executes their requests in an order that its application controls. For a replayable order, the application makes the order deterministic (rounds, section 11.4) instead of recording an arrival order. |
| Atomic action across owners | Two-phase commit in the application: `prepare` (validate and hold) to every owner, then `commit` or `abort`. NCP makes each message run at most once and each vote verifiable by its identity. The limits of section 11.1 apply. |
| Replicated owners | An external consensus service, such as etcd or openraft, chooses the active owner. NCP does not include consensus. |
| Clusters | Specification section 16. |

### 11.4 Planned and deferred profiles

| Profile | What it adds | Status and condition |
| --- | --- | --- |
| Rounds | An owner applies round k only when every agent sent it or a deadline passed, in a fixed order, and returns to each agent the identities of the requests that it applied. Multi-agent steps become deterministic and verifiable. | Specified in [`spec/NCP-2-ROUNDS.md`](../../spec/NCP-2-ROUNDS.md) and implemented in the Python SDK (`ncp.Rounds`, `ncp.RoundRecord`). In the multi-agent benchmark, a round took 2.6 ms with 64 agents and 16.6 ms with 256, 1.4 to 2.3 times the cost of applying requests on arrival, and the final state was the same in every run. A member without a request at the deadline is excluded from later rounds, so an agent that stops delays the others once. The record carries the request identities as one `u8` array, 32 bytes for each agent, because every agent receives the whole record and a JSON list of hexadecimal identities would need 67 bytes for each agent and the work of encoding them. Rust follows with its first consumer. |
| Zenoh binding | Routing, discovery, and lossy links for fleets (specification 9.2). | Implemented as optional packages for Python and Rust in [`bindings/zenoh`](../../bindings/zenoh/README.md), with TCP and TLS links only, mutual TLS, access control on both sides, one thread for each session, session expiry (rule 9.2.7), and the stop of rule 9.2.9; not yet measured in a benchmark protocol. |
| Lockstep | Each step names the tick that it advances to and the state that it answers; after a lost session, the `open` response of a new session tells the client whether its last step ran. | Specified in [`spec/NCP-2-LOCKSTEP.md`](../../spec/NCP-2-LOCKSTEP.md) and implemented in both SDKs (`Lockstep`, `LockstepClient`). It turns "possibly executed" into "ran" or "did not run" for an owner that keeps its state, without durable session state. |
| Two-phase actions | Operations `ncp.prepare`, `ncp.commit`, `ncp.abort`, and `ncp.status`, with a deadline and an optional start time. | Deferred until a consumer needs it. Needs a model check with crashes and losses first. |
| Causal references | A body member `ncp.refs` lists the identities that a message depends on; a verifier builds the happens-before graph across transcripts. | Deferred until a tool such as Prisoma needs the graph. Applications can put identities in their bodies today. |
| Session resume | A client continues a session after an owner restart; "unknown" becomes "executed" or "not executed". | Deferred. It needs durable session state before each response (one fsync per call) and an application that restores its own state, which NEST cannot do. For owners that keep their state, the lockstep profile gives the verdict without it. |

Specification section 15 reserves the `ncp.` names for these profiles.

## 12. Revision 3

A review in November 2026 questioned the rules of revisions 1 and 2 from first principles, and an exhaustive check of the SDKs found one more gap. Revision 3 of the specification makes these decisions. Each one changes behavior that a client or an owner can observe, so the consumers of NCP 2 move together with it ([migration plan](NCP-2-MIGRATION.md)).

| # | Finding | Decision | Check |
| --- | --- | --- | --- |
| 17 | A request that the application found invalid got `rejected`, and the owner kept nothing. A delayed copy of it could execute later, if the application then found it valid, although the client had been told that nothing ran. | A new outcome, `declined`: the owner admits the request, keeps the response, and never executes it (rule 7.3.12). `rejected` now means "not admitted", and a client that follows the rules sees it only for `open`. | Lean `DeclinedIsFinal`; model check, property 5; scenario vectors |
| 18 | An owner that restarted, or forgot a session, could open it again from a delayed copy of the `open` request and send byte-identical responses. A copy of a later step of the old opening could then execute again. | Each opening draws a nonce of at least 128 random bits and sends it in its `open` response (section 7.1), so the chains of two openings share no request after `open`. | Lean `OpeningsDisjoint`, with the nonces of assumption A4 as its hypothesis; model check with restarts, property 1; the mutants `constant_nonce` of the Lean model, the oracle traces, and the model check |
| 19 | After such a reopening, a call of the old opening gets `ack_mismatch` or `seq_gap`, although an earlier copy of it may have executed before the loss. Revision 2 told the client that nothing ran. The exhaustive model check of the SDKs found this case in its first run. | Rule 7.6.4: a rejection of a request other than `open` ends the session, and the request is possibly executed. | Lean `RejectedOnlyForOpen`; model check, properties 6 and 7, and the mutant `client_trusts_rejected_call`; client vectors |
| 20 | Without a session, a request with `seq` greater than 0 got `not_open` on byte streams but `session_expired` on Zenoh. | `session_expired`, possibly executed, on every binding (rule 7.3.3). | Scenario vectors; oracle traces |
| 21 | An owner could not stop without leaving its clients unsure. | `shutdown`: a stopping owner answers `ended` with `shutdown` and never admits the request; a copy of the kept request still gets the kept response. Byte streams send a shutdown response that names no request (rules 9.1.9 and 9.2.9). | Lean `NothingAfterStop` and `ShutdownIsFinal`; Zenoh tests of both bindings |
| 22 | Frames were checked but not authenticated. | Optional HMAC-SHA-256 with a key of at least 32 bytes in place of the digest (section 13.2). | Authenticated-frame vectors; session tests |
| 23 | A transcript could lose a rejected frame, a time, or a direction without a trace, because the session chain commits only to admitted exchanges. | Transcript version 2: a header, a chain value for each record, and an end record; with a key, a keyed chain (section 10). | Transcript vectors |
| 24 | A contract named its operations but did not describe their bodies. | Schemas in a closed subset of JSON Schema (section 11.1); the owner declines a body that does not match before it calls the application. | Contract and schema vectors |
| 25 | Profiles had no way to agree on optional behavior. | `features` in `open`; the owner returns the features that it enabled. The lockstep profile uses it. | Session tests |
| 26 | Each SDK mixed the rules with input and output. | Pure state machines: the owner's `step` and the client's `request`, `receive`, `time_out`, and `closed`. The blocking drivers, the Zenoh servers, the model check, and the vectors drive the same functions. | Model check; vectors |
| 27 | The Zenoh servers handled the queries of all sessions on one thread, so the rounds profile could not use them. | One thread for each session (rule 9.2.8), and a stop as rule 9.2.9 says. | Zenoh tests of both bindings |

The decisions keep the frame format of revisions 1 and 2. They change the messages: the `open` response carries a nonce, and responses can have the outcome `declined`.
