# Independent review request: NCP v1 and its applications

**Snapshot date: September 20, 2026. Status: review material; final v1 remains incomplete.**

Please challenge the architecture, implementation, mathematical assumptions, and release plan from first principles.
We need a decisive engineering review, not reassurance or a larger list of aspirational features.
Recommend the smallest coherent design that meets the actual product requirements.
Reject unnecessary machinery, unsupported claims, and requirements that belong to another owner.

This request and the public source are on GitHub.
The user supplies the private Engram source through a separate ZIP. No shared local workspace is assumed.
Start with this document, then [the source and evidence roster](reviews/v1-independent-20260920/STATE.json).
The [implementation handoff](IMPLEMENTATION_HANDOFF.md) defines the transfer from your review to the next implementation agent.
The roster fixes commits and distinguishes published work from unfinished candidates.
For this NCP branch, the implementation under review is commit `2287198dd421ab2408f4426bdce1eccc8944cf20`.
This branch adds the review packet; it does not turn that candidate into a passing release.

## 1. Decisions we need from you

Answer these first, in priority order:

1. What exact contract should become stable as NCP v1, and what should remain a separately named application or experimental profile?
2. Which concrete defect could produce duplicate execution, false completion, wrong-time control, silent data loss, or leaked process ownership?
3. What is the shortest credible path from the current applications to a useful embodied world-model experiment?
4. Can the current transport support the required workload without a major redesign? Give a quantitative threshold, not a preference.
5. Which existing gates prevent real failures, and which consume time without increasing confidence proportionally?

Give a release recommendation and an implementation sequence.
Do not infer a completion percentage from test counts or the number of documentation files.
If the full requested scope is incompatible with a short release schedule, state that conflict and propose explicit choices.

## 2. Product requirements and protected work

NCP must connect independently selected applications with little setup friction.
An Engram neural application must work with NCP alone and its explicit NEST prerequisite.
CREBAIN must work standalone, with Prisoma, with neural control, or with selected additional services.
Prisoma may depend on CREBAIN for its embodied environment. CREBAIN must not depend on Prisoma.
Galadriel is optional advisory monitoring for possible sensor tampering. It is not the command authority.
Haldir is an optional authorization research component with a different current command contract.

The intended larger workflow starts with a PDF in Engram.
After evidence review, Engram constructs a supported neural network, configures an experiment, coordinates simulation, and reports results.
That complete paper-to-closed-loop workflow is a target. Current native cases use explicit plans and scenes.
Arbitrary-paper reproduction and calibrated posterior inference are not implemented.

The body roadmap includes many drones, city geometry, Gaussian-splat or mesh cameras, acoustic pressure, and thermal observations.
Sensor selection must stay modular. Two cameras are two sensor instances, even when both use the same modality.
A user who needs two through four sources must not install or configure every possible sensor type.
Radar, inertial, range, and future sensors need extension boundaries, not fabricated implementations or mandatory empty channels.

PID-RS has another active owner. **Do not edit its repository, pins, schemas, or active branches.**
KG, ingestion, and oMLX work in Engram also belongs to another agent.
Review their interface boundaries where necessary, but do not redesign or modify that active work.
Do not infer ownership from a branch name. The source roster identifies our two review branches.

The user permits breaking changes before v1 and does not require migration guides.
The goal is a small durable contract, not a promise that no future version can ever be necessary.

## 3. Read the earlier advice, then challenge it

The supplied [closed-loop review](reviews/v1-independent-20260920/inputs/NCP_closed_loop_review.md.txt),
[PDF](reviews/v1-independent-20260920/inputs/NCP_closed_loop_review.pdf), and
[70-case acceptance plan](reviews/v1-independent-20260920/inputs/NCP_acceptance_plan_70.md.txt) are reproduced byte-for-byte.
Their hashes are in the roster.
The original Markdown files use `.md.txt` archive paths to preserve their wording as historical plain-text inputs.
The roster records their original names. Maintained-prose checks do not qualify these archived inputs.

They were prepared on September 5 and deserve serious consideration.
They are design advice and historical source observations, not current native qualification.
Their acceptance plan spans several operating profiles. It is not a denominator for today's modular release progress.

Please reassess three assumptions:

- Does an exclusive project-to-project NCP boundary simplify authority enough to justify every integration cost?
- Which obligations belong to the local trusted-process profile, and which require a separate remote or adversarial profile?
- Should an optional capture library be a separate process, an in-process service, or both under different contracts?

Do not preserve a topology merely because the earlier plan used it.
Do not remove a scientific or causality requirement merely because implementing it is inconvenient.

## 4. Current architecture and ownership

| Owner | Implemented responsibility | Important boundary |
| --- | --- | --- |
| NCP modular SDK | Closed application contracts, bounded frames, exact requests, retained outcomes, acknowledgments, byte buffers | No central runtime, simulator physics, scientific interpretation, or automatic downloaded decoder |
| Host application | Select peers, policy, identities, deadlines, and composition budgets | No authority to reinterpret an unknown application contract |
| Engram neural application | Persistent NEST network, typed currents, fixed projections, delayed readouts | Small admitted circuit family; not arbitrary generated neuroscience models |
| CREBAIN | Dynamics, sensor production, body action application, installed producer lifecycle | Native city and current NCP force-ground application have different envelopes |
| Prisoma transcript | Capture original request/response bytes and check terminal completeness | Does not establish experiment validity or process retirement |
| Prisoma Agent Bridge | Record canonical commands and responses joined to sensor execution and capture spans | Complete learned forecasts and independent restored labels are not yet joined |
| Galadriel | Statistical sensor-consistency evidence and abstentions | An anomaly is not proof of an attack; its scalar adapter does not consume arbitrary raw sensor tensors |
| Haldir | Experimental intent admission and command authorization | Existing velocity semantics do not match current force-ground targets |
| Manwe | Perception research components | No qualified modular NCP application is claimed |
| Cortexel | Validated figure requests and deterministic SVGs | No live NCP simulation owner is claimed |

Useful entrypoints are the [modular owner contract](local/modular/owner.md),
[architecture and operating bounds](local/modular/STATUS.md), and
[canonical modular descriptor](ncp-core/src/modular_profile.v1.json).
Read the [Prisoma experiment guide](https://github.com/sepahead/prisoma/blob/56e835d7d6979df0a2ffeac6050e3860ddf8b1ea/docs/EXPERIMENT_WORKFLOW.md)
and [CREBAIN environment contract](https://github.com/sepahead/crebain/blob/d397905fe51c687b229a496af3b7dac572595e55/docs/NATIVE_ENVIRONMENT.md) together.

The native city source admits 1–256 drones.
The current typed NCP force-ground application admits one drone and no city solids.
Do not confuse these two facts or describe the NCP application as a qualified many-drone city interface.
The latter permits independently selected RGB, thermal, and microphone instances, with at least one sensor overall.
Microphone-only operation does not start a graphics process.

The earlier fixed-role local reference and broader wire-1.0 candidate remain separate surfaces.
Their names, package versions, obligations, and diagrams still create a substantial usability risk.
Recommend a concrete naming and ownership simplification that preserves useful tested code.

## 5. What has actually been observed

These are bounded local observations. Public summaries are reviewable; most underlying native process logs remain private.
Treat a hash of an inaccessible artifact as a reference, not independently verified evidence.

| Case | Reported observation | Limit |
| --- | --- | --- |
| Installed neural application with optional capture | Seven sessions; 700 exact readout comparisons | Joint package environment; same NEST numerical engine as the reference |
| Isolated neural application | Six sessions; 600 readouts, including six pending results; changed-count control rejects | Only Engram, NCP, NumPy, packaging tools, and an external NEST namespace; no body or capture |
| Installed body CLI | Microphone-only and complete-sensor runs each completed 24 ticks | Selected workload, not every admitted roster or maximum |
| Installed body plus neural control | 24 body ticks, eight neural steps; captured and uncaptured arms | Explicit small policy, not learned control or real-time qualification |
| Complete-sensor body payloads | 44 payloads, 4,326,400 bytes, 3,200 pressure samples | One fixed scene and sensor schedule |
| Coupled capture | 496 exchanges; matching payloads and coupled outcomes | Different action schedule from the raw M1 body fixture |
| Caller loss | Observed owned processes retired without emergency cleanup in the selected case | Observed descendants only; no arbitrary hostile-process containment |
| Renderer loss | Failure after one completed tick; second tick attempted; no successful Finish | Public cleanup result stayed unresolved despite independently observed disappearance |
| Prisoma canonical sensor path | Earlier native case replayed eight commands, 150 exchanges, 1,542,400 sensor bytes | Does not qualify the new owned-session helper or a world-model study |

Read [CREBAIN's installed evidence](https://github.com/sepahead/crebain/blob/d397905fe51c687b229a496af3b7dac572595e55/integrations/ncp-force-ground-sensors/evidence/owned-installed-native-2026-09-19.json).
The Engram implementation is in **private `sepahead/Paper2Brain`**, not the public `sepahead/engram` placeholder.
The separate `NCP-independent-review-private-engram-20260920.zip` contains the selected source and committed evidence from the roster's Engram commit.
The archive's README defines its scope and reading order. Its manifest binds each included source file to that commit.
For private GitHub links, read the corresponding `engram/<repository-relative-path>` inside the archive.
The ZIP is supplied directly by the user and is not uploaded to this public repository.
If neither the private repository nor the ZIP is available, state the implementation blind spot explicitly.
Do not infer neural correctness from the public cross-project summaries.

The isolated neural test used the same six-case reference and compared all 600 readouts.
Its altered-count control changed both the observation and matching journal row, then required reference disagreement.
This checks more than consistency between duplicate records. It still shares NEST's numerical engine.

## 6. Unfinished candidates exposed for review

### NCP candidate on this branch

Candidate `2287198` changes the root Rustls lock and clarifies the modular documentation and SDK gate.
The historical SDK comparison excludes the root workspace lock; current source-stability and dependency checks still cover it.
Please test whether this exclusion is correctly scoped or could hide a meaningful dependency change.

Its complete local gate **failed**, after 3,590.25 seconds.
Pinned Ruff `0.15.21` rejected formatting in `scripts/test_local_sdk_gate.py` near the `historical reference changed` assertion.
This is a test-source formatting defect, not an observed protocol failure.
The gate stopped before its installed-SDK section completed and before later packaging and policy sections ran.
Source and index snapshots were unchanged. Earlier passing sections do not constitute a complete pass.
The [gate summary](reviews/v1-independent-20260920/GATE_SUMMARY.md) identifies the retained failure and exact correction.
This candidate has **not** been promoted to `main`.

### Prisoma owned-session helper

The separate [Prisoma review branch](https://github.com/sepahead/prisoma/tree/review/ncp-owned-session-20260920)
exposes its exact implementation and new lifecycle tests.
Use the immutable head in the roster after resolving that branch.

It enters `body_session` inside the already synchronized canonical Prepare callback.
That arrangement avoids an unrecorded Prepare or a new low-level CREBAIN launch API.
The caller must finish explicitly. Only body Finish, capture finalization, and canonical finalization permit healthy scope exit.
Caught dispatch failures remain latched, and later exceptions must preserve earlier failures.

Reported source-distribution, installation, 48 installed Python controls, and focused lint checks passed.
Capability projections are stale, and the candidate audit reports `LIVE_SOURCE_DRIFT`.
The complete development gate and native helper campaign are unrun.
This branch is review input, not completed functionality advertised on `main`.

## 7. Twelve review lenses and hard questions

### A. Minimal stable contract

What are the irreducible primitives needed by these applications?
Can application profiles own operations, units, and clocks without turning NCP into an opaque RPC tunnel?
Identify any field that merely repeats another commitment, and any missing field whose absence permits an invalid interpretation.
Give a minimal wire/API example for Engram-only, CREBAIN-only, and CREBAIN-plus-Prisoma use.

### B. Effects, recording, and recovery

Model this sequence: canonical request synchronization, application entry, mutation, retained outcome, capture, acknowledgment, buffer release, response synchronization, Finish, retirement.
Find the actual linearization points and identify every interruption cut.
Does the implementation ever claim non-execution when effects may have occurred?
Can a caught exception, retry, released outcome, or restarted process create duplicate execution or false completion?
Give a state-machine proof under stated assumptions, or the shortest failing trace.

Keep application completion, storage completion, and process retirement separate.
Should a canonical log remain complete when cleanup later fails, or does its current terminal language promise too much?
Distinguish exactly-once execution within an admitted generation from recoverable knowledge after a crash.

### C. Timing and closed-loop control

Does the delayed NEST recording window align with the body action phase and sensor interval?
Are sample time, delivery time, logical time, and deadline time ever conflated?
Identify the first required change for sampled real-time control, without weakening deterministic lockstep.

As a small counterexample, consider the dimensionless system `x[k+1] = x[k] + u[k]`.
With `u[k] = -(6/5)x[k]`, its multiplier is `-1/5`, so it is asymptotically stable.
With one-step delayed feedback, its characteristic polynomial is `z² - z + 6/5`.
Its complex roots have squared modulus `6/5`, so it is unstable.
This exact arithmetic illustrates timing sensitivity; it is not a model of the current drone controller.
Require any proposed delay budget to name its plant, controller, sampling rule, uncertainty, and relevant proof or measured bound.

### D. Throughput and resource bounds

Current chunks contain at most 32,768 decoded bytes and use JSON/base64 transport.
For payload size `B` bytes, `K = ceil(B/32768)` chunks are required.
The raw M1 fixture expects 24 ticks, 44 payloads, 168 chunks, and 476 body exchanges.
Its maximum due batch is 385,072 bytes; source admission allows much larger cases.

For tick `k`, let `P(k)` count due payloads and `K(k)` count chunks.
The fixture's body budget is `E(k) = 2 + 2K(k) + 2P(k)` exchanges.
Prepare and Finish add four exchanges.
Verify this accounting against the implementation before using it in a performance model.

At 120 body ticks per second, a wall-clock schedule has about 8.33 milliseconds per tick.
The complete-sensor CLI case took 10.390 seconds for 0.2 simulated seconds, including startup.
This engineering observation supplies no steady-state or tail-latency bound.
What envelope is feasible after serialization, hashing, copies, acknowledgments, rendering, and durable recording?
Compare bounded batching, per-sensor partitioning, multiple outstanding buffers, and a separately qualified shared-memory path.
State the measured crossover that would justify each added complexity.
Logical byte reservations do not bound resident memory, allocator overhead, filesystem latency, or GPU memory.

### E. Ownership under failure

Does the Python context API preserve the primary failure and every distinct cleanup failure exactly once?
What happens when the caller catches error A and later raises B?
Can a normal context exit invoke an unrecorded automatic Finish?
Can an owner lose access to process evidence when Prepare fails before the context yields?
Review cancellation, deadlines, caller death, renderer loss, process identity reuse, and repeated close calls separately.
Propose the smallest correction to unresolved renderer cleanup; do not equate process disappearance with completed effects.

### F. Many entities and sensor extensibility

Where should entity identity, sensor-instance identity, modality, tensor meaning, cadence, missingness, and resource admission reside?
Can one application profile generalize the current single-drone sensor path without contaminating the core protocol?
Would separate body profiles provide a cleaner boundary?
Show how two RGB cameras and one microphone compose without invented channels or changes to PID-RS.
Define what a future radar adapter must prove without pretending radar is implemented now.

### G. Numerical and formal evidence

Which invariants deserve a proof, an executable reference, property tests, native fault injection, or empirical measurement?
Where do the current proofs assume the very implementation property they appear to establish?
Audit integer clocks, binary64 identity, non-finite rejection, chunk arithmetic, and bounded allocation separately.
Give minimal countermodels and positive controls for proposed proofs.
Do not replace simulator validity or latency measurements with successful SMT or finite-state checks.

### H. Useful embodied world-model science

Prisoma should contribute more than Rerun recording and visualization.
Its proposed value is forecast commitment, controlled action selection, matched execution, independent branch labels, and defensible comparisons.
Its LeWM engineering path executes pretrained CPU/MPS inference, but does not supply the complete CREBAIN action/label experiment.

What is the smallest useful experiment that can run locally on this M4 Max?
Define permitted observations, action normalization, forecast horizon, complete checkpoint state, target availability, and independent sampling units.
Require a no-model controller, persistence or simple dynamics baseline, and equal information/resource access.
Choose scores appropriate to point or probabilistic forecasts. Separate forecast accuracy from policy benefit.
Explain how adaptive candidate selection, cloned noise, shared scenes, or target injection could invalidate a result.
Give an informative null result and the stopping rule that would prevent endless model integration work.

For optional partial information decomposition (PID), distinguish physical sensor instances, encoded source variables, and the target.
Require a prediction landmark before target availability and an explicit target-ancestry check.
Compare any claimed benefit with mutual information, conditional mutual information, and task loss under matched inputs.
Explain when repeated cameras, action-conditioned model features, or shared simulation noise invalidate the chosen statistical interpretation.
Retain current high-dimensional and application-validity limits; a successful estimator call does not establish admissibility.

### I. Physics and labels

CREBAIN's unchanged city attitude controller failed bounded tracking tests.
The selected force-ground profile has separate evidence and does not erase that failure.
Direct Rapier snapshot restoration also failed later complete-state equality in inspected larger-body cases.
Current controlled branches use CPU reconstruction and fresh static renderers.
Read the [retained control limitations](https://github.com/sepahead/crebain/blob/d397905fe51c687b229a496af3b7dac572595e55/docs/DETERMINISTIC_DYNAMICS.md#observed-controller-and-angular-model-limits)
and [reconstructed-branch contract](https://github.com/sepahead/crebain/blob/d397905fe51c687b229a496af3b7dac572595e55/docs/NATIVE_ENVIRONMENT.md#exact-cpu-state-and-reconstructed-static-branches).

What minimal physical and state-equivalence evidence is necessary for each proposed study?
Are fresh matched siblings enough, or can renderer state, acoustic history, or hidden controller state confound labels?
Do we need to repair a physics defect before a systems experiment, or simply restrict its interpretation?
State the exact restriction; determinism alone is not physical fidelity.

### J. Security and optional authority

The current modular profile trusts installed applications and private local channels.
Which threats remain inside that scope, and which require a separate deployment profile?
What evidence should Galadriel receive to produce a useful abstention or consistency assessment?
Prevent its alarms from silently granting command authority or becoming proof of attack.
If Haldir is selected later, specify one commander and the exact applied-action contract.
Do not impose a remote security stack on local simulations without identifying the threat it addresses.

### K. Packaging, upstream dependencies, and maintenance

Can immutable Git dependencies and explicit native-runtime installation remain a reasonable v1 user experience?
What should be versioned and distributed together, and what should remain an independent optional package?
Recommend one install path and one minimal example per supported composition.
Avoid a mandatory ecosystem bundle or a central service that exists only to launch two processes.

The September 20 recheck still identified official Zenoh 1.10.1 as the latest release.
Its published transport dependency uses `lz4_flex ^0.10.0`; the relevant RustSec fixes require newer versions.
NCP and CREBAIN retain different bounded repairs.
Review the resolved graphs, feature activation, and removal criteria before replacing either repair with upstream code.
Sources: [release](https://github.com/eclipse-zenoh/zenoh/releases/tag/1.10.1),
[published dependencies](https://crates.io/api/v1/crates/zenoh-transport/1.10.1/dependencies),
[advisory](https://rustsec.org/advisories/RUSTSEC-2026-0041.html),
[upstream issue](https://github.com/eclipse-zenoh/zenoh/issues/2589).

### L. Release process and user comprehension

Does the release process spend more effort tracking qualification than improving product behavior?
Separate essential immutable evidence from repeated inventories and duplicated status documents.
Identify checks that can be cached by content identity without silently replacing an exact required full gate.
Recommend how to expose one truthful status, one architecture explanation, and one usable quickstart.
Inspect the [Sepahead portfolio](https://github.com/sepahead/sepahead/tree/d85fe523c6ee8db30c07be2b581b74337612c6ed)
for misleading connections, implied capabilities, or confusing optional dependencies.
Suggest diagrams only where they clarify ownership, state, timing, or evidence.

## 8. Compare alternatives before recommending a redesign

Consider these ten credible paths. Combine compatible parts if that reduces total complexity.

| Alternative | Main benefit | Failure to rule out |
| --- | --- | --- |
| Keep the modular private-pipe contract | Small trusted-local boundary | Throughput or lifecycle limits prevent intended workloads |
| Release core independently from applications | Clear ownership and cadence | Core compatibility is too weak to make composition dependable |
| Promote the earlier fixed-role profile | Existing reference evidence | Mandatory topology defeats optional composition |
| Prioritize the broader remote candidate | More deployment capabilities | Security and discovery work postpones the useful local product |
| Use one central orchestration process | Simple process graph | Duplicates Engram ownership and creates a required broker |
| Batch operations within the current wire | Lower overhead | Coarser outcomes hide partial execution or buffer ownership |
| Add a shared-memory data plane | Fewer copies for large sensors | Leases, lifetime, identity, and cross-language access become unsafe |
| Split profiles by workload | Explicit simple and large cases | Excess profiles duplicate semantics and complicate users' choices |
| Integrate a learned model before completing branch labels | Early visible model output | Demonstration cannot answer a meaningful scientific question |
| Finish a small exact-fork experiment first | Complete evidence chain | Synthetic success is overclaimed as learned control quality |

For the best three, state assumptions, expected benefit, failure modes, engineering cost, and one decisive experiment.
Choose a design. Do not return only an unranked menu.

## 9. Requested response

Please return:

1. A one-page release judgment with the five most important findings.
2. A table of defects: exact source, counterexample, consequence, minimal repair, and decisive verification.
3. A proposed v1 contract and supported-composition matrix, including explicit exclusions.
4. A ranked implementation plan with dependencies and clear stop conditions.
5. Mathematical claims with defined symbols, units, assumptions, proof limits, and worked examples where useful.
6. A list of inaccessible evidence and conclusions that therefore remain uncertain.

Mark statements as source observations, reproduced results, deductions, or proposals.
For a serious concern, provide an executable reproduction or the smallest precise trace when possible.
Distinguish an implementation bug from a missing measurement, a policy choice, or an unavailable artifact.
Question our assumptions, including this request's framing.
If removing a subsystem or discarding prior work is the strongest option, explain exactly why and what evidence would change that judgment.

The open [action-plane security issue](https://github.com/sepahead/NCP/issues/7)
and [qualified-human-review issue](https://github.com/sepahead/NCP/issues/33) are not closed by an agent council.
Do not grant scientific, human-review, or release authority by implication.
Your task is independent review and advice; publishing or merging further product changes requires the implementation workflow.
