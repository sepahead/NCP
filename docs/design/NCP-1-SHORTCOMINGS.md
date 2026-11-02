# What NCP 2 changes from NCP 1

Status: record of 2 November 2026. It lists each known shortcoming of NCP 1, what NCP 2 does about it, and how that is checked.
The [specification](../../spec/NCP-2.md) is normative, and the [design record](NCP-2-DESIGN.md) gives the reasons for each decision.
The sources of the shortcomings are NCP 1's [known limitations](../../KNOWN_LIMITATIONS.md), the campaigns in [`benchmarks/`](../../benchmarks), and the two reviews of 23 October 2026 in [`reviews/`](reviews).

## In short

NCP 1 grew into three overlapping protocols with about 59,000 lines of code.
A call needed two round trips, a result above 64 KiB ended the run, and the remote family brought most of the dependencies and every security advisory of October 2026.
NCP 2 replaces the three with one protocol: a specification of 362 lines and 3,876 lines of code in Rust and Python.
A call is 4 to 165 times faster than with NCP 1.0.1, and coupled to NEST, an exchange adds 23 to 32 µs instead of 228 to 248 µs. A frame can carry up to 64 MiB, and the owner's rules are proved in Lean.

Some work is still open. Section 8 lists it.

## Status words

| Word | Meaning |
| --- | --- |
| Fixed | NCP 2 removes the shortcoming. The last column says how this is checked. |
| By design | NCP 2 leaves the function to the applications on purpose. The row says where it belongs now. |
| Open | NCP 2 still has the shortcoming or has not shown the fix yet. Section 8 plans the work. |
| Deferred | No current user needs it. The [design record](NCP-2-DESIGN.md#114-planned-and-deferred-profiles) states when to reconsider it. |

Line counts are of the source files at commit `6424fb8`, without tests, generated files, and build outputs.

## 1. Structure and size

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 1 | Three overlapping protocol families: the lockstep local profile, the modular local profile, and the wire-1.0 candidate | One protocol with two patterns, exchange and stream, and two bindings, byte stream and Zenoh | Fixed | Specification, sections 1 and 6 to 9 |
| 2 | The lockstep and modular families each implemented admission, kept results, and acknowledgements | One exchange core | Fixed | Specification, section 7 |
| 3 | About 59,000 lines of code in Rust, C++, TypeScript, and Python | 2,302 lines of Rust, 1,574 lines of Python, and a specification of 362 lines | Fixed | Line counts at `6424fb8` |
| 4 | The 41 kB descriptor mixed the protocol with one reference experiment's data types | Applications describe their operations and streams in their own contract documents, identified by their digest | Fixed | Specification, section 11 |
| 5 | Two version lines, for the SDK and for the wire | One version, NCP 2, for the protocol and both SDKs | Fixed | Design record, decision 13 |
| 6 | The names "local", "modular", and "wire 1.0" did not explain themselves | Exchange, stream, byte-stream binding, Zenoh binding | Fixed | Specification, section 2 |
| 7 | The remote family carried the Zenoh dependency tree and every RustSec advisory of October 2026 | The Python SDK uses only the standard library; the Rust SDK uses `serde`, `serde_json`, `sha2`, and `socket2`. Zenoh is only in the optional binding | Fixed for the core | `python/pyproject.toml`, `rust/Cargo.toml`; on 2 November 2026, none of the repository's 131 open Dependabot alerts concerned them |

## 2. Exchange semantics and speed

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 8 | A call needed two round trips: the request and a separate acknowledgement | The next request carries the identity of the last response. One round trip per call, and the session becomes a hash chain | Fixed | Lean proofs in [`formal/`](../../formal); model check in [`model/`](../../model) |
| 9 | One call took 35.6 µs in Rust and 466 µs in Python | 9.1 µs in Rust and 38.6 µs in Python | Fixed | [Comparison benchmark](../../benchmarks/comparison/README.md), H1 and H2 |
| 10 | Coupled to NEST, an exchange cost 0.23 to 0.29 ms with the Rust host | 0.032 ms, the median of six configurations (target: at most 0.10 ms). Measured inside the processes, an exchange adds 23 to 32 µs, against 228 to 248 µs for NCP 1.0.1 | Fixed | [NEST campaign](../../benchmarks/nest-campaign/README.md#results-of-protocol-5), protocol 5, G2 and G6 |
| 11 | Opening a wire-1.0 session had no idempotency: a lost reply could leave a second session | `open` is request 0 of the exchange. The owner keeps its response and sends it again for an identical repeated `open` | Fixed | Specification, rules 7.1 and 7.3.5 |
| 12 | A result above the frame bound ended the run with `execution_unknown`, although the step had run | `result_too_large` says that the step executed and gives the size and the bound | Fixed | Specification, rules 7.3.13 and 7.5 |
| 13 | A small closed set of codes; a new code would break old peers | Each code has an outcome class. A receiver uses the outcome of a code that it does not know | Fixed | Specification, section 7.5 |
| 14 | A step longer than the client's time limit looked like a stalled peer, and there was no progress signal | The byte-stream binding has no protocol time limit for a response. The client chooses its own limit | Fixed | Specification, section 9.1 |
| 15 | Cancelling a running step was not defined | A step runs to its end. An application that needs cancellation defines an operation for it; closing the connection ends the session with the step possibly executed | By design | Specification, rules 7.6.7 and 9.1.7 |
| 16 | Exactly-once claims of the wire-1.0 idempotency cache needed durable restart evidence | Each call executes at most once, and after a failure at most one call of a session is possibly executed. A session does not survive a crash of its owner | Deferred: session resume | Design record, section 11.4 |

## 3. Data and limits

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 17 | One fixed frame bound of 64 KiB for every application | The client requests a bound at `open`, from 64 KiB to 64 MiB; the reference SDKs use 1 MiB | Fixed | Specification, sections 7.1 and 12 |
| 18 | Bulk data needed the modular family's separate buffer system | Every frame can carry binary attachments, aligned to 8 bytes and read in place | Fixed | Specification, section 5 |
| 19 | Spikes travelled as lists of JSON numbers, and digests needed a canonical form | Arrays travel as attachments, and the digest covers the exact bytes | Fixed | Comparison benchmark: the speed-up grows with the number of spikes |
| 20 | At 10,000 neurons and 5 ms, the spike result exceeded 64 KiB and the run failed | NCP 2 carried every step of that kind, and both hosts received exactly NEST's spikes. Measured inside the processes, an exchange adds 119 µs; from the wall times, 0.200 ms, above the target of 0.15 ms | Fixed | NEST campaign, protocols 3 and 5 (G3, G7), and content protocol 2 (96 trials) |
| 21 | The lockstep run plan allowed at most three entities | NCP limits only frames: the bound, 1024 attachments, and the limits of section 12 | Fixed | Specification, section 12 |

## 4. Change over time

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 22 | Each edit of the descriptor made a new, incompatible profile, with no rule for optional extensions | The protocol grows without a new version: unknown codes are read by their outcome, clients ignore unknown members of the `open` response, and names that start with `ncp.` are reserved | Fixed for the protocol | Specification, sections 7.1, 7.5, and 15 |
| 23 | Wire-1.0 enumerations were closed and rejected unknown values | As row 22 | Fixed | As row 22 |

## 5. Evidence and tests

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 24 | The model check and the conformance tests were in a benchmark folder, not in the gate | The model conformance of both owners runs in the gate and in CI on Linux and macOS | Fixed | `scripts/check_ncp2.sh`, `.github/workflows/ncp2.yml` |
| 25 | No fuzz target for the local SDK | Differential fuzzing of both decoders: 200,000 cases in each gate run | Fixed | `conformance/fuzz.py` |
| 26 | Only the report arithmetic was checked in Lean | The owner rules are a Lean model. Twelve claims are proved with Lean's standard axioms only, and six model defects show what each claim constrains | Fixed | [`formal/`](../../formal) |
| 27 | The complete gate took about 65 minutes | The NCP 2 gate takes about 17 seconds | Fixed | `scripts/check_ncp2.sh` |
| 28 | Fault and soak campaigns covered only NCP 1.0.1 | The model check covers lost, repeated, delayed, and changed frames and crashes. Campaigns with real processes for NCP 2 have not run yet | Open | Section 8 |
| 29 | No independent second implementation | Two SDKs share the conformance vectors, but one author wrote both | Open | Section 8 |
| 30 | No modular-composition test of the ecosystem | The design record plans one; it does not exist yet | Open | Section 8 |
| 31 | Installed packages and supply-chain records were missing for a release | The NCP 2 packages have not been built as release artifacts yet | Open | Section 8 |

## 6. Security and authority

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 32 | The production-secure identity binding for Zenoh was not implemented | On networks that are not trusted, the Zenoh binding MUST use TLS with client certificates and access control. The binding is not implemented yet | Open | Specification, rule 9.2.6; section 8 |
| 33 | Plane-wide authority grants, plant-safety governors, an ESTOP reset, and a body-generation owner were inside the protocol, several of them incomplete | NCP checks integrity and gives a hash-chained record. Applications add signed authority in their contracts; Haldir gates commands to physical machines | By design | Specification, section 13 |
| 34 | The local audit chain was not signed | Transcripts prove which frames one program sent and received and in which order. They do not prove who produced them; signing belongs to the application | By design | Specification, sections 10 and 13 |

## 7. Documentation and languages

| # | Shortcoming of NCP 1 | What NCP 2 does | Status | Check |
| --- | --- | --- | --- | --- |
| 35 | The README led with evidence boundaries instead of the purpose | The specification and the SDK READMEs start with the purpose. A guide for readers without a background in protocols is planned | Open | Section 8 |
| 36 | Legacy files sat next to current documents | The NCP 1 code and documents stay on the main branch until the last consumer has moved; then they leave it | Open | [Migration plan](NCP-2-MIGRATION.md) |
| 37 | The reasons for the design were spread over many files | The design record collects them, and the comparison benchmark measures the alternatives | Fixed | Design record |
| 38 | Wire 1.0 had TypeScript and C++ packages | NCP 2 has no TypeScript or C++ package. A frame is plain bytes that any language can make; CREBAIN's web interface needs a TypeScript client or a bridge | Open | Section 8 |

## 8. What is still open

These items follow from the open rows above and from the [design record](NCP-2-DESIGN.md).
They are the remaining work before the release of NCP 2.0.

1. Real-process fault and soak campaigns for both SDKs and every binding (row 28).
2. A modular-composition test: a host with neural, body, monitor, and recorder modules in every subset of the optional ones, with faults, and a check of every transcript (row 30).
3. The multi-agent and MPI benchmarks, with the rounds helper (design record, sections 8 and 11.4).
4. The Zenoh binding with mutual TLS and access control (row 32).
5. A TypeScript client or a bridge for CREBAIN's web interface, if it still needs NCP after its Rust side has moved (row 38).
6. The moves of the consumers to NCP 2, then the removal of the NCP 1 code from the main branch (row 36).
7. Release artifacts and supply-chain records for both packages (row 31); the tag and the publication are owner actions.
8. A guide for readers without a background in protocols, with figures (row 35).
9. Comparison protocol 2: the comparison with other systems on the power adapter, and with the same integrity check in every arm.

Protocol 5 also left one question open that is not a shortcoming of NCP 1: whether a coupling slows NEST's own work. At 10,000 neurons, that work varied between runs by more than the time of an exchange (hypotheses G1 and G3).

An independent second implementation (row 29) needs another author; it is not in this list.
