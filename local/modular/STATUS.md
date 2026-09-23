# Modular applications: architecture, evidence, and remaining work

Status: development components with selected native observations. No complete modular-product release is declared.
This guide separates implemented interfaces, measured cases, and remaining requirements.
The owning application documents retain their exact source identities and qualification limits.

The [modular owner contract](owner.md) and [core descriptor](../../ncp-core/src/modular_profile.v1.json) define the SDK behavior.
The earlier [fixed-role reference](../../docs/local-v1/README.md) has a different descriptor and acceptance mapping.
Its four required owners are not dependencies of every modular application.

## What each component owns

| Component | Implemented responsibility | What it does not supply |
| --- | --- | --- |
| NCP | Bounded frames, exact requests, retained outcomes, acknowledgements, byte buffers, and independent Rust/Python codecs. | Simulator physics, sensor interpretation, process launch, experiment design, or model quality. |
| CREBAIN | Body dynamics, selected sensor production, typed observations, and the installed producer lifecycle. | Neural execution, canonical experiment ordering, or a learned world model. |
| Engram | A persistent NEST network, typed currents, fixed projections, and delayed spike-count readouts. | Body physics or compulsory capture and monitoring. |
| Prisoma transcript | Original request/response capture and terminal exchange verification. | Producer launch, action selection, or scientific acceptance. |
| Prisoma Agent Bridge | Canonical records for sensor execution, forecast commitments, and separately restored labels. | Simulator ownership, arbitrary checkpoint authority, or general model-quality qualification. |
| Host application | Selected peers, bindings, policy, deadlines, and composition budgets. | Authority to reinterpret an unknown application contract. |

The host selects an application before opening its channel.
Requests cannot install a schema, select an executable, or introduce an arbitrary method call.
One endpoint can expose several sensor instances.
Endpoint count, sensor count, agent count, and experimental-variable count are different quantities.

CREBAIN can run without Engram, Prisoma, or a monitor.
The neural application can run without a body or capture package.
Capture accepts selected peers without requiring a fixed project roster.
Every supported combination still needs its own installed qualification.

## Target: a paper-driven experiment

The intended Engram workflow starts with a PDF and ends with a reported experiment.
Engram owns source interpretation, supported model construction, experiment orchestration, and the final report.
NCP supplies the contracts between selected participants. It is not a central orchestration process.

| Target stage | Owner | Required boundary |
| --- | --- | --- |
| Extract and review paper evidence | Engram prepares; the researcher reviews | Separate stated source evidence from defaults, assumptions, and external advice before constructing the network and experiment. |
| Construct the network and experiment | Engram | Select supported neuron, synapse, stimulus, recording, and comparison contracts. |
| Configure the simulated environment | Engram selects; CREBAIN executes | Preserve scene identity, units, sensor rosters, action semantics, and resource limits. |
| Run the closed loop | Engram coordinates the selected controller and body | Use neural or other supported control through the selected application contract. |
| Record and evaluate | Engram and optional Prisoma services | Keep original execution evidence, forecasts, targets, and evaluation rules distinct. |
| Inspect possible sensor tampering | Optional Galadriel adapter | Return advisory consistency evidence or abstention. An anomaly does not prove an attack or grant command authority. |
| Report the result | Engram | State the tested hypothesis, observations, uncertainty, failures, and remaining limitations. |

This is the target workflow, not a claim that arbitrary PDFs already produce correct reproductions.
Extracted candidate evidence requires review before network and experiment construction.
Current native cases use explicit network plans, scenes, sensor configurations, and small control policies.
Those examples do not restrict every future application to their fixed neural controller.
Each new controller or environment still needs its own admitted contract and evidence.
Simulation records retain `calibrated_posterior=false`.
Galadriel supports cybersecurity experiments through sensor-consistency analysis.
Engram, CREBAIN, and Prisoma can run without it.
Its full core and existing scalar NCP adapter have different input capabilities.

## CREBAIN and Prisoma data flow

CREBAIN owns the world, dynamics, sensor generation, and accepted native checkpoint state.
Prisoma owns experiment ordering, candidates, forecasts, targets, comparison rules, and outcome lineage.
NCP carries their declared operations and original observation bytes.

| Stage | Executing owner | Required distinction |
| --- | --- | --- |
| Select a command | Host policy or Prisoma experiment | A proposal is not an applied action. |
| Record a canonical request | Prisoma Agent Bridge, when selected | The request record precedes dispatch. |
| Capture and dispatch | Selected transcript hook and NCP client | Capture preserves original bytes before forwarding. |
| Reserve and advance | CREBAIN's Rust owner and native environment | Required output storage precedes body mutation. |
| Read and verify | Independent sensor client | Every due payload must match its typed and byte manifests. |
| Release source buffers | The selected client workflow | Buffer release differs from request acknowledgement and durable capture. |
| Record the response | Prisoma Agent Bridge, when selected | The canonical response joins the observed execution receipt. |
| Finish and retire | Each application, transcript, and process owner | Application, storage, and process completion remain separate. |

CREBAIN's incremental `SensorSession` keeps source buffers live through the batch context.
Prisoma's `SensorExperiment` returns immutable observations after captured reads, source-buffer release, and canonical response synchronization.
These APIs expose different lifetime boundaries.
Their [calling guides](https://github.com/sepahead/prisoma/tree/main/integrations/agent-bridge) define those boundaries explicitly.

The ordinary sensor interface excludes privileged CPU checkpoints and counterfactual records from observation payloads.
The separate checkpoint-family application retains the actual native checkpoint object and keeps its parent live until every admitted branch closes.
Distinct NCP bindings identify restored branches. One native child runs at a time.
Copied audit data and caller hashes cannot create checkpoint authority.

Prisoma's family adapter records original forecast commitments before canonical continuation and restored labels.
Each branch has its own journal, joined through one canonical timeline and a closed capture index.
The E1 study checks selected-action pressure bytes, target arithmetic, final CPU equality, and unchanged parent state.
Ordinary predictors receive observations without checkpoint or evaluation capabilities.
These execution checks do not establish general forecast quality or policy benefit.

Use the owning diagrams and detailed guides:

- [CREBAIN typed sensor transfer](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-ground-sensors), including its scalable sensor-flow diagram.
- [CREBAIN live checkpoint family](https://github.com/sepahead/crebain/blob/main/integrations/ncp-force-ground-sensors/FAMILY.md), including checkpoint authority and restoration limits.
- [CREBAIN city sources](https://github.com/sepahead/crebain/tree/main/integrations/ncp-force-city-sources), including whole-roster actions and world-fixed sensor recipients.
- [Prisoma recorded execution](https://github.com/sepahead/prisoma/tree/main/integrations/agent-bridge), including wide and mobile diagrams.
- [Prisoma family collection](https://github.com/sepahead/prisoma/blob/main/integrations/agent-bridge/FAMILY.md), including canonical ordering and separate branch journals.
- [Prisoma experiment ordering](https://github.com/sepahead/prisoma/blob/main/docs/EXPERIMENT_WORKFLOW.md), including the exact-fork reference boundary.
- [Engram installed host (private source)](https://github.com/sepahead/Paper2Brain/blob/main/packages/ncp-nest/HOST.md), requiring private repository access.

## Interface mathematics

These equations explain byte and clock contracts.
They do not validate sensor physics, learned forecasts, or controller stability.

### Complete payloads and bounded chunks

Let $B$ be the integer payload length, with $1\leq B\leq8{,}388{,}608$ bytes.
Let $C=32{,}768$ bytes be the maximum decoded chunk length.
The required chunk count is

$$
K=\left\lceil\frac{B}{C}\right\rceil.
$$

Here, $K$ is a positive integer.
Each accepted chunk must have the expected index, offset, decoded length, and hash.
The complete payload hash must also match before the receiver accepts the payload.
Acknowledging a response frees its retained response frame, not its referenced sensor buffer.

The [SDK bounds](README.md#working-state-bounds) admit at most 8,388,608 bytes per payload and sixteen endpoints per composition.
Producer and receiver storage count independently.
These bounds describe logical reservations, not total process or graphics memory.

### Sensor clocks

The current force-ground body advances at 120 ticks per second.
Its acoustic model produces 16,000 samples per second.
For body tick $k$, starting at $k=1$, the pressure sample interval is

$$
\left[
\left\lfloor\frac{(k-1)16000}{120}\right\rfloor,
\left\lfloor\frac{k16000}{120}\right\rfloor
\right).
$$

The interval endpoints are sample indices, not timestamps.
The first three ticks contain 133, 133, and 134 samples.
Each three-tick group therefore contains exactly 400 samples and spans 25 milliseconds of simulated time.
Each camera separately declares its identity, dimensions, and capture period.
A camera that is not due differs from an unconfigured camera or a failed required observation.

### Optional neural coupling

The example policy advances NEST once per three completed body ticks.
It holds the selected body target between those neural updates.
It sums the 400 finite binary64 pressure samples exactly before selecting the next neural input.
This discrete policy tests interface causality and supplies no learned-control claim.

The selected neural step is $\Delta=25{,}000$ microseconds, with recording delay $d=1{,}000$ microseconds.
For an executed end time $t$, the complete spike window is $(a,b]$, where

$$
a=\max(0,t-\Delta-d),\qquad b=t-d.
$$

Here, $a$, $b$, and $t$ use integer microseconds.
Completed steps satisfy $t\geq\Delta$ and $b>a$.
For $n$ neurons and $s$ spikes in that window, the per-neuron rate is

$$
r=\frac{s\,10^6}{n(b-a)}\ \mathrm{Hz}.
$$

Here, $n$ is a positive population size, $s$ is a nonnegative spike count, and $r$ is the mean rate per neuron.
A complete zero count means observed silence.
A pending window supplies no complete count or rate.
The [neural evidence (private source)](https://github.com/sepahead/Paper2Brain/blob/main/packages/ncp-nest/docs/RECURRENT_EVIDENCE.md) defines the exact model, circuit, inputs, and comparisons.

## Implemented and observed

| Surface | Implemented | Retained observation | Remaining limit |
| --- | --- | --- | --- |
| Generic SDK | Closed application types, bounded buffers, selected input leases, exact outcomes, and independent Rust/Python implementations. | Source and fresh installed-wheel gates include cross-language controls and the selected 8 MiB structural transfer. | Structural parity does not qualify native application semantics or resource usage. |
| Neural application | Ordinary `neural_session` with optional transcript capture. | Seven installed sessions passed 700 readout comparisons. All 153 tests passed in the selected joint package environment. | That environment does not prove every minimal installation or supported combination. |
| Body application | Typed sensor client, explicit runtime installer, and ordinary `body_session`. | The September 19 installed campaign observed microphone-only and complete-sensor CLI runs, plus two body/neural arms. | These selected cases do not qualify every admitted configuration or resource maximum. |
| Optional capture | Original frames, complete acknowledgements, and terminal verification. | Separate body and neural runs reconstructed their captured exchanges and payloads. | A journal does not establish canonical experiment ordering or model quality. |
| Historical canonical sensor execution | Prisoma Agent Bridge joins commands, receipts, transcript spans, and original sensor bytes. | The September 10 case reconstructed eight commands, 150 exchanges, and 1,542,400 sensor bytes. | This historical case does not qualify later family or city contracts. |
| [M1 transfer](https://github.com/sepahead/prisoma/blob/main/integrations/agent-bridge/evidence/M1_NATIVE_2026-09-23.md) | Installed body-only and canonical execution with original-byte readback. | The September 23 arms matched all 44 payloads and 4,326,400 bytes. | Fault cases retain incomplete captures and their original cleanup results. |
| [Engram host (private source)](https://github.com/sepahead/Paper2Brain/blob/main/packages/ncp-nest/docs/NATIVE_HOST_EVIDENCE.md) | Actual guarded CLI execution through body and neural NCP applications. | Both September 23 arms completed 24 body ticks and eight NEST steps. Fresh direct NEST matched all 64 count/rate values. | The reference shares NEST's numerical engine. Complete Engram bootstrap and paper reproduction remain unqualified. |
| [E1 restored-label study](https://github.com/sepahead/prisoma/blob/main/integrations/agent-bridge/evidence/E1_NATIVE_2026-09-23.md) | Canonical forecast commitments, selected execution, restored labels, and frozen comparison rules. | Eight qualification cases and 112 study episodes completed. The forecast result was null or inconclusive. | The constant comparison failed the useful margin. The study supplies no general model-quality or selected-policy benefit claim. |
| [City source delivery](https://github.com/sepahead/crebain/blob/main/integrations/ncp-force-city-sources/evidence/NATIVE_CITY_2026-09-23.md) | A separate typed contract for 1–256 entities and up to twelve selected sources. | Native delivery and fault cases retained 153 original payloads totaling 30,121,184 bytes. | Sensor delivery does not qualify continuous contact absence, complete resource use, or every admitted configuration. |
| [M1 timing](https://github.com/sepahead/prisoma/blob/main/integrations/agent-bridge/evidence/M1_PERFORMANCE_2026-09-23.md) | Fixed schedule and complete timing accounting across direct, NCP, and canonical routes. | All 192 executions completed. All 4,608 route deadlines and 4,608 export deadlines were missed. | No real-time qualification or isolated protocol-cost claim follows. |

Earlier rows retain their historical observations. The dated application records identify each later campaign's exact source and runtime.
Do not combine observations from different identities into one completed release campaign.
Public digest summaries identify retained private artifacts. They do not replace the original captures for replay.

The [installed body evidence](https://github.com/sepahead/crebain/blob/main/integrations/ncp-force-ground-sensors/evidence/owned-installed-native-2026-09-19.json) binds CREBAIN source `a5037a23a8e55d39ca0f09da2c25853c5209467b`.
The microphone-only CLI run completed 24 ticks, 24 payloads, and 25,600 payload bytes.
The complete-sensor CLI run completed 24 ticks, 44 payloads, and 4,326,400 payload bytes.
Both coupled arms completed 24 body ticks and eight neural steps.
Optional capture preserved 496 exchanges and identical payloads and coupled outcomes.
A fresh direct NEST comparison matched 64 count/rate values, and the changed-count control rejected.
The direct reference shares NEST's numerical engine and supplies no independent physical-model validation.

Selected lifetime controls observed process retirement without emergency cleanup.
Renderer loss still returns `cleanup_confirmed=false` from the body API, with one completed tick and the second tick attempted.
That failed session emits no successful `Finish`.
External observation of process disappearance does not rewrite the API's unresolved cleanup result.

## Remaining work

| Required work | Why it remains | Completion evidence |
| --- | --- | --- |
| Extend installed body qualification | The completed campaign covers selected configurations and faults. Renderer-loss cleanup remains unresolved in the API result. | Additional claims need exact installed bytes, declared cases, retained failures, and the required lifecycle evidence. |
| Qualify advertised optional combinations | The dated body, canonical, neural-host, family, and city campaigns select different installed artifacts and configurations. | Clean documented installations and native runs for each advertised combination. |
| Measure the complete resource envelope | Selected large transfers and timing records do not measure all process, graphics, allocation, and storage costs. | Frozen workloads, retained failures, complete resource observations, and declared operating limits. |
| Qualify many-entity operating claims | The separate city contract admits 256 entities. Its selected native cases do not establish continuous contact absence or universal configuration support. | Exact installed action/sensor routing, controller, contact, and resource evidence for each claim. |
| Establish model or policy benefit | E1 completed its forecast and restored-label path but missed the frozen useful-margin requirement. | Separate frozen studies for further claims, with retained null results, model selection, original labels, and comparison evidence. |
| Add a selected modular monitor | Earlier fixed-role Galadriel controls do not supply a qualified monitor for every current sensor application. | Its installed typed contract, actual inputs, explicit abstentions, and separate composition qualification. |
| Publish a scoped product | SDK package versions and selected runs do not establish release acceptance. | A consistent supported matrix, resolved acceptance evidence, immutable artifacts, and reproducible installation. |

The existing [70-case mapping](../../docs/local-v1/acceptance-70.md) preserves the earlier fixed-profile requirements.
Its draft status is not a current count of completed modular work.
Exclusions require their own explicit scope and rejection controls.
The [broader candidate](../../docs/1.0-scope.md) retains its separate remote, security, and release requirements.

## Related project boundaries

| Project | Current role | Required distinction |
| --- | --- | --- |
| [Galadriel](https://github.com/sepahead/galadriel) | Optional advisory sensor-consistency monitoring for cybersecurity and tampering research, with a standalone core and fixed-profile scalar adapter. | Its existing adapter cannot directly assess raw RGB, pressure, or radiance arrays. Statistical inconsistency is not proof of an attack. |
| [Haldir](https://github.com/sepahead/haldir) | Experimental command-authorization reference with a retained wire-0.8 adapter. | No qualified modular gate exists. Its local-NED velocity contract differs from CREBAIN's current body targets. |
| [Manwe](https://github.com/sepahead/manwe) | Perception research tools, numerical references, and checked model-interface candidates. | No implemented CREBAIN, Prisoma, Galadriel, or Engram/NCP adapter is claimed. |
| [Cortexel](https://github.com/sepahead/cortexel) | Validated figure requests and deterministic SVG rendering, including a detached NEST-capture adapter. | Its figure catalog supplies no NCP adapter or live simulation owner. Rendering does not authenticate source evidence. |

These projects retain independent setup, architecture, mathematical, and evidence contracts.
Their presence in an ecosystem diagram does not install or qualify a runtime connection.

## Verification entrypoints

Run the maintained SDK gate with Python 3.11 or later:

```sh
python3 -I scripts/check_local_sdk.py --python python3
```

The gate checks projections, source stability, independent controls, package construction, and installed package origins.
The complete repository source gate additionally owns dependency policy and documentation checks.
Each application guide supplies its additional gates and native prerequisites.
Passing a source gate grants no scientific or release authority.
