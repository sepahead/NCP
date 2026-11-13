# NCP 2 compared with other tools

Status: 13 November 2026, for revision 4 of the [NCP 2 specification](../../spec/NCP-2.md).
This document compares NCP 2 with the tools that a closed-loop experiment can use instead. The guarantees table covers tools that exchange requests between processes; co-simulation standards such as DCP, HELICS, and HLA appear where they are stronger. It lists what NCP 2 adds and what it lacks. Each statement about another tool names its primary source, listed at the end. Tools change: check a source before you rely on a statement.

## What a coupling of independent programs needs

A closed loop of independently owned programs, such as a neural simulator, a body simulator, a monitor, and a recorder, needs:

1. a step that runs at most once, also when its request is sent again after a lost response;
2. a true answer after a failure: the step ran, did not run, or possibly ran;
3. detection of damaged messages;
4. a record of the session that a third party can check afterwards;
5. bulk numbers, such as spikes and images, without a conversion of each value;
6. separate processes, languages, and failures for each program.

NCP 2 builds in all six. The other tools can give them when an application adds them on top.

## Guarantees

| Tool | A request sent again runs once | Answer after a failure | Damage detected without TLS | Checkable session record |
| --- | --- | --- | --- | --- |
| NCP 2 | Built in: the owner keeps the last response and answers each copy with it (rule 7.3.5) | Built in: ran, did not run, or possibly ran, with at most one "possibly" per session, and it is the last (section 7.7) | Built in: SHA-256 of each frame (section 3) | Built in: a hash chain over each session, and transcripts with a verifier (section 10) |
| gRPC | Application: the retry policy resends calls, and the server does not detect copies [1, 2] | Application: after `DEADLINE_EXCEEDED`, the operation may have completed [3] | Not built in: TLS when configured [4] | Not built in |
| ZeroMQ (request and reply) | Application: the reliable request-reply patterns resend, and the server must tolerate copies [5] | Application [5] | Not built in: CurveZMQ when configured [6] | Not built in |
| Zenoh (query and queryable) | Application [7] | Application | Not built in: TLS when configured [8] | Not built in |
| HTTP/1.1 | Application: only idempotent methods may be retried automatically [9]; an `Idempotency-Key` header is a draft [10] | Application | Not built in: TLS | Not built in |
| ROS 2 services | Application [11] | Application | Not built in: DDS security when configured [12] | Not built in |
| MUSIC | Not applicable: data flows inside one MPI job [13] | Not applicable | Not built in | Not built in |
| FMI 3.0 co-simulation | Not applicable: the importer calls the FMU in its own process; an FMU can save and restore its state for a rollback [14] | Through the return status of each call [14] | Not applicable | Not built in |
| NRP-core | Not built in: engines communicate through gRPC or JSON over HTTP [17] | Not built in | Not built in | Not built in |

## Where the others are stronger

| Capability | NCP 2 | Tools that build it in |
| --- | --- | --- |
| Peer authentication without a shared key | No: a shared key for HMAC frames (section 13.2), or TLS and Zenoh access control from the binding | gRPC with TLS or ALTS [4], ZeroMQ with CurveZMQ [6], Zenoh with mutual TLS and access control [8], ROS 2 with DDS security [12] |
| Typed interfaces and code generation | No: contracts with JSON schemas (section 11), checked at run time | gRPC with Protocol Buffers [1], ROS 2 interfaces [11], FMI model descriptions [14] |
| Streaming calls, deadlines, and cancellation in the protocol | No: one request at a time; time limits are local to the client | gRPC [1, 18] |
| Coordination of simulated time | No: the application owns its clock; the lockstep profile numbers steps (`spec/NCP-2-LOCKSTEP.md`) | FMI 3.0 importers [14], DCP [15], HELICS [16], HLA [19] |
| Discovery and routing | Only with the optional Zenoh binding | Zenoh [7], ROS 2 [11], HELICS brokers [16] |
| Languages | Python and Rust | gRPC, ZeroMQ, and Zenoh in many languages [1, 5, 7] |
| Maturity | A release candidate; one author wrote both SDKs | All the others have years of production use |

## Speed

The [comparison benchmark](../../benchmarks/comparison/README.md) measured one call between two processes on one laptop, with revision 2 of the SDKs.
With a small result, NCP 2 took 9.0 µs in Rust over a pipe and 38.8 µs in Python; gRPC took 35.9 µs in Rust over a Unix domain socket.
With 1 MiB in each call, the tools without an integrity check were faster than NCP 2, by about the time of its SHA-256 check. When every tool made the same check, NCP 2 was the fastest at every size, in both languages.
These values come from one computer, and they do not show behavior across a network.

## When to use another tool

- Calls inside one process: call the function.
- Exchange between the ranks of one MPI job: MPI, or MUSIC for neural simulators.
- Fan-out of high-rate data to many subscribers, without the need to detect changes: a publish and subscribe system.
- Objects larger than 64 MiB: send them out of band, and put their digest in an NCP message.
- A typed interface in many languages matters more than a checked record: gRPC or ROS 2 services.
- Hard real time, or simulated time across many federates: DCP, HLA, or HELICS.

## Sources

1. gRPC documentation, "Core concepts" and "Retry": https://grpc.io/docs/what-is-grpc/core-concepts/ and https://grpc.io/docs/guides/retry/
2. gRPC proposal A6, "Client retries": https://github.com/grpc/proposal/blob/master/A6-client-retries.md
3. gRPC status codes: https://grpc.github.io/grpc/core/md_doc_statuscodes.html
4. gRPC authentication: https://grpc.io/docs/guides/auth/
5. ZeroMQ guide, chapter 4, "Reliable request-reply patterns": https://zguide.zeromq.org/docs/chapter4/
6. CurveZMQ, ZeroMQ RFC 26: https://rfc.zeromq.org/spec/26/
7. Zenoh documentation: https://zenoh.io/docs/
8. Zenoh access control and TLS: https://zenoh.io/docs/manual/access-control/ and https://zenoh.io/docs/manual/tls/
9. RFC 9110, HTTP Semantics, section 9.2.2, "Idempotent methods": https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2
10. IETF draft, "The Idempotency-Key HTTP Header Field": https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/
11. ROS 2 documentation, "About services": https://docs.ros.org/en/rolling/Concepts/Basic/About-Services.html
12. ROS 2 documentation, "About security": https://docs.ros.org/en/rolling/Concepts/Intermediate/About-Security.html
13. Djurfeldt and others, "Run-time interoperability between neuronal network simulators based on the MUSIC framework", Neuroinformatics 8 (2010) 43–60, doi:10.1007/s12021-010-9064-z
14. Functional Mock-up Interface 3.0: https://fmi-standard.org/
15. Distributed Co-Simulation Protocol (DCP), Modelica Association: https://dcp-standard.org/
16. HELICS documentation: https://docs.helics.org/
17. Neurorobotics Platform: https://neurorobotics.net/
18. gRPC deadlines: https://grpc.io/docs/guides/deadlines/
19. IEEE 1516-2010, High Level Architecture
