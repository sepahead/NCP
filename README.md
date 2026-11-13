# NCP — Neuro-Cybernetic Protocol

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img src="assets/logo-light.svg" width="180" alt="NCP: opposed contract rails with separate request and outcome paths.">
  </picture>
</p>

<p align="center"><a href="assets/archive/logos/README.md">Logo design archive</a></p>

NCP couples programs that different people write and run, such as a simulated brain and a simulated body, so that they can work together in steps.
One program, the client, asks another, the owner, to do a step.
NCP makes sure that no step runs twice, that the client learns whether each step ran or, after a failure, that it possibly ran, that damaged messages are detected, and that a record can show exactly what was sent and in which order.
Each application describes its own steps and data in a contract.

## NCP 2

**NCP 2.0 is a release candidate: revision 3 of the specification, and packages of version 2.0.0. The tag and the publication follow.** NCP 2 replaces the three protocol families of NCP 1, below, with one protocol. The projects that use NCP 1 move to NCP 2 before NCP 1 leaves the main branch.
[NCP 2 in plain words](docs/NCP-2-GUIDE.md) explains it with figures for readers without a background in protocols.
The [specification](spec/NCP-2.md) is the exact definition, and the [design record](docs/design/NCP-2-DESIGN.md) gives the reason for each decision and the alternatives that were measured.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/ncp2-call-dark.svg">
  <img alt="A client and an owner exchange four requests and four responses: open, two steps, and close. Each request after open carries the identity of the last response as its acknowledgement, so each step needs one round trip and the session forms one hash chain. After a failure, at most one call of the session is uncertain." src="docs/diagrams/ncp2-call-light.svg" width="860">
</picture>

| Measured on one laptop | NCP 2 | NCP 1.0.1 | Record |
| --- | --- | --- | --- |
| One call with a small result, Rust to Rust | 9.0 µs | 36.1 µs | [Comparison benchmark](benchmarks/comparison/README.md#results-of-protocol-2) |
| One call with a small result, Python to Python | 38.8 µs | 469 µs | [Comparison benchmark](benchmarks/comparison/README.md#results-of-protocol-2) |
| Time added to each 1 ms step of a NEST network, Rust client | 23 to 32 µs | 228 to 248 µs | [NEST campaign](benchmarks/nest-campaign/README.md#results-of-protocol-5) |
| Spikes compared with NEST's recorder | All 42,026,126 exact, in 96 trials with up to 10,000 neurons | All exact in 72 trials with 1000 neurons | [NEST campaign](benchmarks/nest-campaign/README.md#results-of-content-protocol-2) |
| Fault trials with real programs, over pipes, Unix domain sockets, and TCP (SDK revision 2) | 8,730 trials: no wrong result, no step run twice, no false report of a step | 3,816 trials over pipes: no wrong result | [Fault campaign](benchmarks/fault-campaign/README.md#results-of-protocol-5) |
| One round over 256 programs from one host (`call_all`) | 0.92 ms (Rust), 2.8 ms (Python) | not measured | [Multi-agent benchmark](benchmarks/multi-agent/README.md#results) |
| 64 agents sharing one world in rounds, Python owner | 2.6 ms per round; the same final state in every run | no rounds profile | [Multi-agent benchmark](benchmarks/multi-agent/README.md#results) |

Up to 1,788 spikes per call, NCP 2 was also faster than gRPC and Zenoh in Rust, and than gRPC and HTTP in Python; with 1 MiB per call, the systems without an integrity check were faster, by about the time of NCP 2's SHA-256 check.
When every other system made the same SHA-256 check as NCP 2, NCP 2 was the fastest at every size, 1 MiB included, in both languages ([comparison protocol 2](benchmarks/comparison/README.md#results-of-protocol-2)).

- The SDKs: [Python](python/README.md), which uses only the standard library, and [Rust](rust/README.md). The optional [Zenoh binding](bindings/zenoh/README.md), for both languages, carries the same frames between computers, with mutual TLS and access control.
- Nineteen claims about the owner and the client are proved in Lean for every sequence of inputs ([`formal/`](formal/README.md)). The SDKs are not proved: the Python and Rust owners give the same answers as the compiled Lean model on 20,000 random traces, and an exhaustive check drives the real Python client and owner through about 2.6 million states with faults ([`model/`](model/README.md)).
- The measurements in this section were made with revision 2 of the SDKs. Revision 3 changed the session rules and the code of the owner and the client, not the frame format; the benchmarks and the fault campaign have not run again.
- [What NCP 2 changes from NCP 1](docs/design/NCP-1-SHORTCOMINGS.md) maps each known shortcoming of NCP 1 to its fix and its check, and lists the work that is still open.
- [NCP 2 compared with other tools](docs/design/NCP-2-COMPARISON.md) lists what NCP 2 adds, what it lacks, and when another tool fits better, with a source for each statement.
- The projects that use NCP move to NCP 2 one at a time, in the order of the [migration plan](docs/design/NCP-2-MIGRATION.md). NCP 1 stays available until the last one has moved.

## NCP 2 benchmarks: speed, lag, and correctness

Each measurement below comes from a protocol that was fixed, with its SHA-256 fingerprint, before its runs; each protocol ran in three blocks in a shuffled order on one laptop (Apple MacBook Pro, M4 Max, macOS 26.5.1).
A median is the median of the three block medians, and a 99th percentile is the median of the three blocks' 99th percentiles. Each benchmark's README gives every value, the range over the blocks, the conditions, and what the results do not show.

### Time of one call

One call sends a small request and gets N spikes back, 12 bytes each, between two processes on the laptop ([comparison benchmark, protocol 2](benchmarks/comparison/README.md#results-of-protocol-2), on the power adapter, with the clock and the load checked before and after each run).
Each cell gives the median and, after the slash, the 99th percentile, in µs. 99 of 100 calls took at most the 99th percentile, so it shows how long the slow calls take.

| Rust client and server | No spikes | 127 spikes | 1,788 spikes | 1 MiB |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 9.0 / 12.4 | 13.9 / 18.7 | 32.5 / 38.5 | 918 / 981 |
| NCP 2, Unix socket | 9.5 / 12.9 | 14.1 / 18.5 | 33.0 / 37.7 | 872 / 906 |
| gRPC (tonic), Unix socket | 35.9 / 41.1 | 34.5 / 41.6 | 55.6 / 64.2 | 1,200 / 1,315 |
| gRPC (tonic), TCP | 47.9 / 57.1 | 48.2 / 57.4 | 54.7 / 65.3 | 259 / 425 |
| Zenoh, TCP | 59.5 / 86.6 | 60.7 / 96.2 | 63.5 / 97.6 | 371 / 1,710 |
| NCP 1.0.1, pipe | 36.1 / 42.3 | 72.8 / 81.4 | 430 / 450 | not measured |
| Raw pipe, no protocol | 4.5 / 10.4 | 7.5 / 10.6 | 8.4 / 10.6 | 151 / 165 |

| Python client and server | No spikes | 127 spikes | 1,788 spikes | 1 MiB |
| --- | ---: | ---: | ---: | ---: |
| NCP 2, pipe | 38.8 / 52.5 | 49.2 / 62.2 | 67.2 / 81.3 | 909 / 961 |
| NCP 2, Unix socket | 38.9 / 51.3 | 57.2 / 65.3 | 70.2 / 78.7 | 759 / 826 |
| ZeroMQ, ipc | 54.6 / 68.4 | 56.0 / 73.1 | 79.6 / 98.4 | 1,006 / 1,079 |
| Zenoh, TCP | 65.2 / 89.5 | 65.1 / 101.5 | 68.9 / 102.2 | 144 / 192 |
| HTTP/1.1, TCP | 80.3 / 98.9 | 88.5 / 96.2 | 74.7 / 99.6 | 139 / 245 |
| gRPC (grpcio), TCP | 128.7 / 167.5 | 128.7 / 146.4 | 135.0 / 158.9 | 244 / 375 |
| NCP 1.0.1, pipe | 469 / 670 | 1,255 / 1,478 | 11,263 / 11,732 | not measured |
| Raw pipe, no protocol | 9.2 / 13.2 | 9.2 / 13.5 | 11.7 / 14.7 | 186 / 204 |

In Rust, NCP 2 was the fastest protocol up to 1,788 spikes, at the median and at the 99th percentile.
In Python, NCP 2 had the lowest 99th percentile up to 1,788 spikes and the lowest median with no spikes. With 127 and 1,788 spikes, its median was close to that of the fastest other system (ZeroMQ, then Zenoh): lower in this protocol, and higher in [protocol 1](benchmarks/comparison/README.md#exploratory-results), which ran on battery.
At 1 MiB, the other systems make no integrity check of the message, while NCP 2 computes and checks a SHA-256 fingerprint of every message. That check takes most of NCP 2's time there: on a raw pipe in Rust, the same check costs 722 µs.
With the same check added to every system, NCP 2 was the fastest at every size, 1 MiB included: in Rust, 872 µs over a Unix socket against 1,104 µs for Zenoh and 1,137 µs for gRPC over TCP; in Python, 759 µs against 801 µs for Zenoh and 830 µs for HTTP/1.1.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="benchmarks/comparison/results-2/figures/integrity_dark.svg">
  <img src="benchmarks/comparison/results-2/figures/integrity_light.svg" alt="Time of one call when every system checks a SHA-256 fingerprint of each message as NCP 2 does, for Rust and Python and for 0, 127, 1788, and 87381 spikes, on log scales: NCP 2 is the fastest at every size.">
</picture>

### Lag added to a running simulation

Coupled to the NEST simulator, a host asks NEST to advance its network by one step and waits for the result ([NEST campaign, protocol 5](benchmarks/nest-campaign/README.md#results-of-protocol-5)).
The table gives the time that the coupling adds to each exchange, measured inside the processes, for the Brunel network with 1,000 and 10,000 neurons on 1, 4, and 8 threads and one exchange after every 1 ms of simulated time: the range over the six configurations, in µs.

| Coupling | Median | 99th percentile |
| --- | ---: | ---: |
| NCP 2, Rust host | 23 to 32 | 39 to 78 |
| NCP 2, Python host | 50 to 61 | 72 to 109 |
| NCP 1.0.1, Rust host | 228 to 248 | 279 to 324 |
| NCP 1.0.1, Python host | 492 to 524 | 574 to 629 |
| Raw round trip to another process, no protocol | 8 to 11 | 13 to 23 |

When each step also returns its spikes, NCP 2 adds 36 to 119 µs with a Rust host. NCP 1.0.1 adds 434 to 1,365 µs, and it cannot carry the steps of 10,000 neurons at 5 ms, because some of them exceed its 64 KiB message limit.
These times leave out one effect: a coupled NEST can do its own work more slowly than NEST alone. With 10,000 neurons, that effect varied between runs by more than the time of an exchange.
MUSIC, the MPI library with which NEST exchanges spikes with other simulators, needs all coupled programs in one MPI job. From the difference of wall times, it added 0.001 to 0.256 ms per 1 ms step in these configurations, against 0.026 to 0.141 ms for NCP 2 with a Rust host: less in three of the six, all with 4 or 8 NEST threads, and more in the other three. In this NEST build, MUSIC delivered the exact spikes only with one NEST thread; with T threads, only one channel in T carried its exact spike train ([content protocol](benchmarks/nest-campaign/README.md#results-of-the-content-protocol)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="benchmarks/nest-campaign/results-5/figures/overhead_dark.svg">
  <img src="benchmarks/nest-campaign/results-5/figures/overhead_light.svg" alt="Time that each coupling adds to an exchange after every 1 ms step of the Brunel network, on a logarithmic scale: about 8 to 11 µs for a raw round trip, 23 to 32 µs for NCP 2 with a Rust host, 50 to 61 µs with a Python host, and 228 to 524 µs for NCP 1.0.1.">
</picture>

### Correctness

- **Exact data.** Both NCP 2 hosts received exactly the spikes that NEST recorded, each neuron and each time, in all 96 trials of [content protocol 2](benchmarks/nest-campaign/README.md#results-of-content-protocol-2), with 1 to 8 threads and up to 10,000 neurons: 42,026,126 spikes compared. Through the first process of an MPI program, all 521 million spikes that the client checked arrived exactly ([multi-agent benchmark](benchmarks/multi-agent/README.md#results)).
- **Faults.** With revision 2 of the SDKs, in 8,730 trials with real programs over pipes, Unix sockets, and TCP, with Rust and Python on both sides, messages were damaged, cut, or repeated, programs were killed, steps stalled, and messages were too large: no client accepted a wrong result, no owner ran a step twice or out of order, and no client was told something false about a step ([fault campaign, protocols 3 and 5](benchmarks/fault-campaign/README.md#results-of-protocol-5)).
- **One order for many agents.** With the rounds profile, up to 256 agents sharing one world received the same result after every round, and the world ended in the same state in every run ([multi-agent benchmark](benchmarks/multi-agent/README.md#results)).
- **Proofs and checks.** Nineteen claims about the owner and the client are proved in Lean for every sequence of inputs, and eleven injected defects each break the proof of the claim that forbids them. An exhaustive check drives the real Python client and owner through about 2.6 million states with up to two faults: lost, repeated, and reordered messages, restarts and stops of the owner, and wrong requests. The Python and Rust owners give the same answers as the compiled Lean model on 20,000 random traces. Both SDKs pass the same conformance vectors, each requirement of the specification maps to its checks, and the decoders and message checks agree on 200,000 random and damaged messages in every gate run.

### Scale

- One host called 256 owners in one round in 0.92 ms with the Rust SDK and 2.8 ms with the Python SDK (`call_all`).
- 64 agents in rounds on one Python owner took 2.6 ms per round.
- An owner in the first process of an MPI program added 4 to 11 µs to a call with 1 to 8 processes, up to 1,788 spikes.

### Spiking controllers in NEST fly simulated drones

CREBAIN's [closed-loop host](https://github.com/sepahead/crebain/blob/main/docs/NATIVE_NCP_SIMULATION.md) runs controllers and simulated drone worlds, each with its own NCP 2 session.
Each controller here simulates spiking neurons in NEST: unconnected integrate-and-fire populations carry a proportional-derivative signal, computed in Python, as firing rates, and their spike counts give the accelerations.
On 12 November 2026, one controller flew one drone, and three controllers flew five drones in two worlds, to within 2.6 cm of their targets in 600 steps of 20 ms; an offline check of the transcripts confirmed all 2,400 controller responses, and a second run of the one-drone loop gave the same results. The run tests the coupling, not neural control ([evidence](https://github.com/sepahead/crebain/blob/main/integrations/ncp2-nest-controller/README.md)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/ncp2-loop-dark.svg">
  <img src="docs/diagrams/ncp2-loop-light.svg" alt="Three cards joined by arrows: spiking controllers in NEST, the loop host crebain-ncp-loop, and CREBAIN worlds with one to three drones each. Below them, three results: the drones reached their targets, all 2,400 controller responses were checked, and a second run gave the same results. A note lists the limits.">
</picture>

### What these results do not show

They come from one laptop, with programs on one computer. They measure the protocols, not the work of a real simulation, except in the NEST campaign. The other systems ran with their default settings; NCP 2 sets 1 MiB socket buffers, which matters most at 1 MiB. The [Zenoh binding](bindings/zenoh/README.md) and networks between computers have not been measured yet.

## NCP 1: the released local SDK

NCP connects independently owned simulations and tools through exact, bounded data contracts.
The [modular local SDK](local/modular/README.md) lets a host select installed applications without requiring a fixed project bundle.
NCP owns message identity, retained outcomes, acknowledgements, and byte-buffer lifetime.
Each application owns its operations, observations, units, clocks, and accepted values.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/system-map-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/diagrams/system-map-light.svg">
  <img alt="A host selects independent applications and connects each one through the NCP contract. NCP owns message identity, retained outcomes, acknowledgements, and bounded byte buffers. Each application owns its own state. The local SDK 1.0.0 is released; applications and wire 1.0 remain UNRELEASED. It is not release or certification evidence." src="docs/diagrams/system-map-light.svg" width="860">
</picture>

Full-size vector figure: [light](docs/diagrams/system-map-light.svg?raw=true) · [dark](docs/diagrams/system-map-dark.svg?raw=true).

The [NCP System Design report](output/pdf/ncp-system-design.pdf) is the standalone technical reference.
It explains the design, the equations, and the evidence boundary of each scope.
A Lean 4 file checks its discrete arithmetic.

**Release status: local SDK 1.0.1 released; product v1 and wire 1.0 unreleased.**
The standalone `ncp-local` Rust and Python packages are released as version `1.0.1` under the tag `sdk-v1.0.1`, after `1.0.0` under `sdk-v1.0.0`.
The [SDK release record](local/modular/SDK_RELEASE.md) states the released scope, the council decision, and the verification steps.
The applications have source controls and selected native evidence.
Complete qualification of their declared installed combinations and final product v1 remain open.
Read the [architecture, interface mathematics, evidence, and remaining work](local/modular/STATUS.md) for the current modular scope.
The [v1 preparation notes and checklist](local/modular/PREPARATION.md) collect the supported evidence and outstanding prerequisites.
No package-registry upload has taken place.

In the intended paper-driven workflow, Engram extracts candidate evidence from a PDF for review.
After evidence review, Engram constructs a supported network and experiment, configures CREBAIN, and coordinates execution and reporting.
Prisoma experiment services and Galadriel monitoring for possible sensor tampering remain optional.
The other applications can run without Galadriel. An anomaly does not prove an attack.

Current native tests use explicit plans and scenes. They do not establish arbitrary-paper reproduction.
The [target ownership flow](local/modular/STATUS.md#target-a-paper-driven-experiment) distinguishes that goal from current measured behavior.

## Select the applications you need

| Component | Implemented use | Current evidence boundary |
| --- | --- | --- |
| [NCP modular SDK](local/modular/owner.md) | Independent Rust and Python owners and clients for installed application contracts and bounded buffers. | SDK controls do not qualify an application's native behavior or resources. |
| [Engram NEST application (private source)](https://github.com/sepahead/Paper2Brain/tree/main/packages/ncp-nest) | Run a persistent neural network or select the guarded body/neural host CLI. | Native host comparisons retain exact count/rate and payload results. Private repository access is required. |
| [CREBAIN sensor application](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-ground-sensors) | Run an explicitly installed body through `body_session`, or use caller-owned streams through `SensorSession`. | Installed CLI and body/neural cases cover selected workloads. Each advertised configuration needs its own qualification. |
| [CREBAIN checkpoint family](https://github.com/sepahead/crebain/blob/main/integrations/ncp-force-ground-sensors/FAMILY.md) | Retain a live native checkpoint and serve separately bound restored continuations. | The selected E1 study checks original pressure bytes and final CPU equality. It does not restore arbitrary runtime state. |
| [CREBAIN city sources](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-city-sources) | Control 1–256 entities in one world with separately selected world-fixed sensor sources. | Native cases retain delivery and fault bounds, with a separate integration-law hull certificate. Complete resource and general tracking qualification remain open. |
| [Prisoma transcript](https://github.com/sepahead/prisoma/tree/main/integrations/ncp-transcript) | Capture original NCP exchanges from selected peers and verify terminal completeness. | Capture does not launch a simulator or validate an experiment's scientific result. |
| [Prisoma Agent Bridge](https://github.com/sepahead/prisoma/tree/main/integrations/agent-bridge) | Record sensor execution, forecast commitments, and restored labels through the selected application contract. | The native E1 study completed 112 episodes. Its forecast result was null or inconclusive under the frozen useful-margin requirement. |

Engram, CREBAIN, and capture are independently selectable.
A selected composition must satisfy every participating application's contract and resource limits.
The SDK supplies no automatic application discovery, downloaded decoder, or mandatory central runtime.

CREBAIN's scalar sensor application admits one simulated drone and no city solids.
It supports zero through four RGB cameras, thermal cameras, or microphones, with at least one sensor overall.
Camera-free selections require no Node or graphics process.
The [installed body guide](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-ground-sensors/python) explains the runtime prerequisites and lifecycle contract.

The separate city contract adds whole-roster control and source recipients without widening the scalar or checkpoint-family contracts.
The [current evidence](local/modular/STATUS.md#implemented-and-observed) links each campaign to its owning source, workload, result, and limitations.

## Remaining product v1 work

The remaining work includes:

- Complete installed qualification, lifecycle controls, and reproducible distribution for each advertised optional combination.
- Measure the declared workload and resource envelope, including supported sensor sizes and entity counts.
- Qualify declared many-drone workloads within their exact contact, resource, and lifecycle requirements.
- Extend experiment evidence beyond E1's null or inconclusive forecast result before claiming general model quality or policy benefit.
- Qualify additional advertised application roles, including selected monitoring, through their own typed contracts.

These requirements need implementation or operating evidence according to the owning application contract.
Selected demonstrations do not establish real-time operation, controller stability, sensor accuracy, or model quality.

## Earlier four-owner reference control

The earlier `ncp.local-lockstep.v1` reference remains a separate regression control.
Its [release registry](local/release.v1.json) records its fixed roles, packages, and outstanding publication gates.
Its intended tag remains `local-v1.0.0`.
That registry does not qualify the modular applications above or define the complete final product scope.

The broader `1.0.0-rc.1` candidate retains its [separate scope](docs/1.0-scope.md) and release blockers.
The latest published legacy release remains `v0.8.0`, with an incompatible wire.

![Engram owns NEST and sequences private NCP exchanges with the CREBAIN body, Prisoma capture, and record-only Galadriel monitor.](docs/local-v1/architecture.svg)

[Open the scalable architecture SVG](docs/local-v1/architecture.svg).
The figure shows this reference experiment's ownership and communication.
It is not a release receipt.

| Owner | Responsibility | Authority boundary |
| --- | --- | --- |
| Engram | Maintain one NEST network and sequence the experiment. | Own neural execution and scientific interpretation. |
| CREBAIN | Advance simulated bodies and produce actual fusion diagnostics. | Apply the final simulated acceleration. |
| Prisoma | Reserve journal capacity and capture exact causal step pairs. | Verify storage completeness; grant no command authority. |
| Galadriel | Run its actual statistical detector on the supplied diagnostics. | Record results and abstentions; grant no command authority. |
| NCP | Define shared shapes, limits, identities, and outcomes. | Provide a contract and SDKs; own no central runtime process. |

In this reference, the run owner uses separate private process pipes for each peer.
Peer engines and stores cannot become alternative runtime integration paths.
Each request binds the exact profile, role, run, generation, sequence, operation, and body.
The receiver retains its complete outcome until the caller acknowledges that outcome's digest.

Capture reservation precedes dependent neural and body mutation.
A lost response does not establish whether execution occurred.
The owner preserves known results, records unresolved dispatches, and retires uncertain generations.
Same-generation crash resume is excluded.

## Supported reference envelope

| Property | Reference contract |
| --- | --- |
| Host qualification target | Darwin, trusted installed applications, private pipes, and the selected process sandbox. |
| Entities | One through three, with a frozen ordered roster. |
| Run length | At most 1,024 coupled steps. |
| Shared step duration | 1 through 1,000 milliseconds; applications can impose stricter limits. |
| Coordinates | East, north, up; position in meters, velocity in meters per second. |
| Action | Simulated acceleration in meters per second squared. |
| Wire | A four-byte big-endian length followed by at most 65,536 JSON bytes. |
| Identity | Closed typed data and domain-separated digests with exact binary64 round trips. |
| Capture | Bounded lossless capture with complete terminal verification. |
| Monitoring | Record-only output with explicit insufficient-evidence results. |
| Recovery | Exact live result lookup and acknowledgement; no re-execution of a released operation. |

Engram's reference application ran on NEST Simulator 3.9.0.
Engram now targets NEST Simulator 3.10.0, and its active environment has not yet moved.
It supports five fixed neuron profiles and one tested persistent update/readout mechanism.
The [local guide](docs/local-v1/README.md) states the stricter application bounds.

This CREBAIN adapter supplies one Visual modality per entity.
Galadriel's selected detector requires at least two modalities.
A ready Visual channel therefore remains insufficient for a cross-modal verdict.
Three innovation dimensions do not become three modalities.

Haldir-gated execution is unsupported by this profile.
Haldir's existing velocity-command semantics do not define this acceleration interface.
A gated request must fail before preparation.
Remote endpoints, physical actuation, and real-time guarantees are also excluded.

## Learn the reference contract

The [mathematical guide](docs/local-v1/math-guide.md) defines the symbols, units, assumptions, and operating bounds.
It explains delayed spike readout, innovation statistics, exact outcomes, and capture completeness through worked examples.

- [Eight-page vector PDF](docs/local-v1/ncp-local-v1-guide.pdf)
- [Scalable step-order SVG](docs/local-v1/step-order.svg)
- [Exact profile and semantic contract](docs/local-v1/profile-contract.md)
- [Ten-approach reference-profile decision and five review lenses](docs/local-v1/decision.md)
- [Original 70 acceptance requirements and current evidence status](docs/local-v1/acceptance-70.md)

The JSON descriptor is canonical for this reference profile's local wire.
The [release registry](local/release.v1.json) registers that descriptor and its separate publication requirements.
Application profiles own their additional configuration and execution rules.
An inconsistency between these sources and an implementation blocks release.

The older `contract/*.v1.json`, protobuf, schema, and conformance hierarchy continues to govern the broader candidate only.
The [historical overview](https://github.com/sepahead/NCP/blob/11a1931871fbd27235bf53dbb5e55227b78d857e/README.md) preserves that earlier release scope.
The generated [light diagram](docs/diagrams/overview-light.svg?raw=true) and [dark diagram](docs/diagrams/overview-dark.svg?raw=true) show the broader candidate's proposed admission gates.
They do not describe an implemented local-v1 runtime or close any gate.

## Implementations and verification

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/evidence-ladder-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/diagrams/evidence-ladder-light.svg">
  <img alt="Five evidence classes run from source controls to release. Each class permits only its own claim. The NCP 1.0 candidate has local and selected native evidence. Its independent and external gates are NOT RUN, and it is UNRELEASED. It is not release or certification evidence." src="docs/diagrams/evidence-ladder-light.svg" width="860">
</picture>

Full-size vector figure: [light](docs/diagrams/evidence-ladder-light.svg?raw=true) · [dark](docs/diagrams/evidence-ladder-dark.svg?raw=true).

| Package | Selected purpose | Independence |
| --- | --- | --- |
| [Local Rust SDK](local/rust/README.md) | Local framing, installed application contracts, bounded buffers, and outcome ownership. | Rust reference implementation. |
| [Local Python SDK](local/python/README.md) | Equivalent local contracts, buffers, and bounded client/owner behavior. | Independent pure-Python implementation; no Rust FFI. |
| [Broader candidate packages](docs/1.0-scope.md) | Historical migration and broader protocol development. | Separate candidate identities and unpassed release gates. |

The standalone Rust package has no dependency on the broader `ncp-core` candidate.
Its generated projection preserves the exact canonical module bytes.
Only test and example package imports change.
The projection gate checks every selected source and descriptor.

Run the maintained SDK gate with Python 3.11 or later:

```sh
python3 -I scripts/check_local_sdk.py --python python3
```

This gate includes source projections, independent language controls, and fresh installed-wheel checks.
It grants no application or release qualification.

From the repository root, run the focused source and Rust gates:

```sh
python3 scripts/project_local_rust.py --check
cargo test --manifest-path local/rust/Cargo.toml --locked
cargo clippy --manifest-path local/rust/Cargo.toml --all-targets --locked -- -D warnings
```

The [release registry](local/release.v1.json) lists this reference profile's bootstrap and operational requirements.
Final product v1 also requires the open modular and multimodal capabilities stated above.
A source test does not qualify an installed application.
The operational gate must start from immutable, pushed source and exact installed artifacts.
Terminal release evidence follows that gate.

The broader candidate's complete local regression command remains `scripts/check.sh`.
Its separate external gates remain required for a broader release.
Local profile qualification cannot close those gates.

## Scientific and operating limits

Protocol success does not validate a paper reproduction, calibrated posterior, controller stability, or physical safety.
Simulation records retain `calibrated_posterior=false`.
Missing data, malformed output, and unusable traces cannot become successful measurements.

Digests identify supplied bytes and labels.
They are not scientific signatures or loaded-model attestations.
The Darwin boundary assumes trusted installed applications.
It does not isolate arbitrary malicious code or all Mach and process metadata.

The neural controller is a bounded research example.
Its fixed encoding and readout do not claim training, optimality, or state-of-the-art control performance.
Measured timing and resource results must state their exact host, workload, and artifact scope.

## Project documents

- [Modular architecture, mathematics, evidence, and remaining work](local/modular/STATUS.md)
- [Earlier local reference scope, owners, and gates](docs/local-v1/README.md)
- [Broad candidate specification](NEURO_CYBERNETIC_PROTOCOL.md)
- [Broad candidate security contract](SECURITY.md)
- [Broad candidate release ledger](RELEASE_READINESS.md)
- [Frozen wire-0.8 baseline](docs/0.8-current-baseline.md)
- [NCP System Design report](output/pdf/ncp-system-design.pdf)
- [System-design PDF build and comparison](docs/publication/README.md)
- [Closed-loop identity, timing, and stability](docs/implementation/CLOSED_LOOP_MATH.md)
- [Documentation style](DOCUMENTATION_STYLE.md)
- [Contribution workflow](CONTRIBUTING.md)
- [Versioning policy](VERSIONING.md)

Author and maintainer: **[Sepehr Mahmoudian](https://github.com/sepahead)**.

NCP uses either the [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE) license.
Use an immutable release's citation metadata when citing that release.
Repository HEAD and the local candidate are not published release evidence.
