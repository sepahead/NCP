# NCP — Neuro-Cybernetic Protocol

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
    <img src="assets/logo-light.svg" width="180" alt="NCP: opposed contract rails with separate request and outcome paths.">
  </picture>
</p>

<p align="center"><a href="assets/archive/logos/README.md">Logo design archive</a></p>

NCP connects independently owned simulations and tools through exact, bounded data contracts.
The [modular local SDK](local/modular/README.md) lets a host select installed applications without requiring a fixed project bundle.
NCP owns message identity, retained outcomes, acknowledgements, and byte-buffer lifetime.
Each application owns its operations, observations, units, clocks, and accepted values.

**Release status: unreleased.**
The SDK and applications have source controls and selected native evidence.
Complete qualification of their declared installed combinations and final product v1 remain open.
Read the [architecture, interface mathematics, evidence, and remaining work](local/modular/STATUS.md) for the current modular scope.

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
| [CREBAIN city sources](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-city-sources) | Control 1–256 entities in one world with separately selected world-fixed sensor sources. | Native cases retain their declared delivery and fault bounds. Complete resource and continuous-contact qualification remain open. |
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
- Qualify declared many-drone workloads, including continuous-contact and complete resource requirements.
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

Engram's reference application targets NEST Simulator 3.9.0.
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
Its retained [light diagram](docs/diagrams/overview-light.svg) and [dark diagram](docs/diagrams/overview-dark.svg) describe the broader candidate's proposed admission architecture.
Those historical diagrams do not describe an implemented local-v1 runtime or close their original gates.

## Implementations and verification

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
- [System-design PDF build and comparison](docs/publication/README.md)
- [Closed-loop identity, timing, and stability](docs/implementation/CLOSED_LOOP_MATH.md)
- [Documentation style](DOCUMENTATION_STYLE.md)
- [Contribution workflow](CONTRIBUTING.md)
- [Versioning policy](VERSIONING.md)

NCP uses either the [MIT](LICENSE-MIT) or [Apache-2.0](LICENSE-APACHE) license.
Use an immutable release's citation metadata when citing that release.
Repository HEAD and the local candidate are not published release evidence.
