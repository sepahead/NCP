# Local simulation reference profile

Status: first bounded development profile with component implementations. Final product v1 requirements, profile qualification, and publication remain open.

`ncp.local-lockstep.v1` is the first bounded development profile.
It targets a deterministic local experiment with native project owners and exact outcomes.
It does not declare the broader `1.0.0-rc.1` candidate complete.
The [prior scope](../1.0-scope.md), failed gates, historical receipts, and wire-0.8 baselines remain separate evidence.

The current shared [descriptor](../../ncp-core/local-profile.v1.json) identifies the candidate local contract.
The [release registry](../../local/release.v1.json) registers this exact descriptor and the selected standalone packages.
The descriptor defines contract identity without a publication-status field.
Immutable source, artifact, and operating gates remain required before publication.
This guide cannot override a conflicting registry or grant release authority.

## Open final v1 requirements

The fixed four-owner experiment is a reference control, not the complete final product scope.
Final v1 requires independently selectable adapters and optional project combinations.
No application may require the complete project bundle merely to use one supported adapter.

CREBAIN must support standalone use and declared experiments with many drones and multiple actual sensor modalities.
The sensor scope includes camera/3DGS, audio, and heat profiles with explicit data and operating contracts.
Prisoma must own embodied-agent and world-model experiments and may use CREBAIN as a simulation dependency.
Engram must remain an optional participant in those compositions.

Those requirements remain open until the relevant implementations and independent qualification evidence exist.
The current profile keeps its fixed wire, roles, entity bounds, and registry identity as a reference control.
Its passing controls cannot establish larger-scale or multimodal behavior by implication.

![Four native process owners use the same NCP contract through private channels.](architecture.svg)

Open the SVG directly to zoom without losing text or line detail.
The diagram describes the reference experiment's ownership and permitted communication, not an installed-run receipt.

## Supported reference application envelope

| Surface | Selected meaning | Admission or evidence boundary |
| --- | --- | --- |
| Execution | Local deterministic simulation | `execution_mode=direct_simulation` is required. |
| Qualified host target | Darwin with the selected process sandbox | Other hosts require explicit rejection until separately qualified. |
| Neural owner | Engram owns one persistent NEST network | The exact NEST build, model, stimulus update, and readout interval need native evidence. |
| Body owner | CREBAIN owns simulation and fusion state | One frozen roster contains one through three entities. |
| Evidence owner | Prisoma reserves and captures exact step pairs | Completeness needs every planned pair and the matching terminal record. |
| Monitor owner | Galadriel runs `SubsetMagnitudeV0_9` | Scalar Visual NIS remains insufficient for the unchanged two-modality minimum. |
| Command mode | Direct simulated acceleration | Haldir gating is unsupported and must reject before endpoint preparation. |
| Capture mode | `lossless_bounded` | Capacity must be reserved before dependent neural or body mutation. |
| Monitoring mode | `record_only` | A report grants no action, lease, permission, or reset. |
| Time | Integer logical microseconds | No claim relates independent process clocks by subtraction. |
| Transport | Inherited private process pipes | There is no remote listener or remote authentication claim. |
| Encoding | Bounded JSON with typed canonical digests | Exact binary64 values must survive serialization and parsing. |
| Recovery | Exact retained outcome, then explicit acknowledgement | Uncertain execution retires the coupled generation. Same-generation crash resume is excluded. |

The shared plan contains at most 1,024 coupled steps.
Each step spans 1,000 through 1,000,000 microseconds and is an exact multiple of 1,000 microseconds.
The integration resolution is 1 through 1,000 microseconds and exactly divides the step duration.
The readout delay must be a positive resolution multiple below the step duration.
An application owner can impose stricter installed limits.
The [shared data definitions](../../ncp-core/src/local_data.rs) own the exact accepted layout and numeric domains.

The fixed observation layout is position followed by velocity, in east, north, and up order.
Its units are meters and meters per second.
The action layout contains acceleration in the same axes, in meters per second squared.
`zero_acceleration` can preserve existing velocity.
It is not a physical stop instruction.

## Reference experiment ownership

In this reference experiment, Engram owns orchestration, NEST execution, the prepared controller, and scientific interpretation.
CREBAIN owns its body and fusion kernels.
Prisoma owns its capture state and evidence checks.
Galadriel owns its statistical detector and abstention semantics.
NCP owns shared data contracts, bounded framing, outcome semantics, and independent conformance checks.

The coordinator exchanges project data through the selected NCP endpoints.
An NCP payload cannot contain executable code or an opaque legacy Host API tunnel.
The deployed coordinator must not import peer engines, open their stores, or poll private files as an alternative integration path.
A direct test oracle stays outside the runtime package and cannot become a fallback.

Engram also owns a local dispatch journal for audit.
It records intent before sending, the returned response before coordinator progress, and an unknown outcome after unresolved loss.
This journal is not a peer integration channel, a replacement for Prisoma capture, or authority to resume uncertain state.

Private pipes identify the installed process channel under trusted coordinator custody.
The request cannot select a new role, run, generation, profile, or executable.
Digests detect changes to supplied bytes and labels.
They do not authenticate physical observations or replace operating-system access control.

The candidate Darwin launcher combines a process sandbox, private pipes, and a separate lifecycle guardian.
The sandbox denies network access, child creation, executable replacement, peer signals, and unapproved file access.
Each role receives only its own code/runtime reads, private scratch writes, and three standard descriptors.
The guardian manages child lifetime and receives no application payloads.
Parent death or a declared timeout must terminate the owned child without targeting a reused process identifier.
Development controls exercised actual Darwin filesystem, socket, import, fork, executable replacement, and signal denial.
They also exercised owner death, cancellation, startup-channel failure, and a positive NEST path.
The guardian remains the primary lifetime mechanism.
An additional `ITIMER_REAL` bounds a trusted worker if its guardian dies.
A lost guardian receipt remains unresolved after timer expiry.
This boundary assumes trusted installed applications; it does not isolate arbitrary malicious code or all Mach and process metadata.
Cases 52 and 64 remain open until those operating controls have immutable installed evidence.
An architectural diagram cannot close those cases.

## Local requirements

The identifiers below remain requirements for this registered reference profile.
They supplement its local descriptor within the existing registry scope.
They do not cover the complete final product requirements stated above.
They do not modify prior release gates by implication.

| Identifier | Required behavior |
| --- | --- |
| LV1-01 | Freeze the exact plan, profile, role, run, generation, roster, units, and layouts before mutation. |
| LV1-02 | Admit one causally dependent step at a time and preserve its exact source snapshot. |
| LV1-03 | Use exact logical time and one tested persistent NEST update and readout mechanism. |
| LV1-04 | Preserve available zero, absent evidence, empty recorded windows, and missing recording declarations separately. |
| LV1-05 | Reject malformed, non-finite, out-of-range, oversized, stale, or contradictory inputs before execution. |
| LV1-06 | Retain one complete exact outcome until its result digest is acknowledged. |
| LV1-07 | Never re-execute a released operation. Retire uncertain mutable state and preserve the known closed prefix. |
| LV1-08 | Reserve capture capacity before coupled mutation and verify exact terminal completeness. |
| LV1-09 | Keep entity state, source diagnostics, applied actions, and evidence joins distinct. |
| LV1-10 | Enforce fixed endpoint roles and reject unimplemented profiles without fallback. |
| LV1-11 | Run the actual Galadriel detector with explicit research classification and abstention. |
| LV1-12 | Admit no control effect from Prisoma output, Galadriel output, or a presentation projection. |
| LV1-13 | Bound frames, retained outcomes, plans, sample windows, child lifetimes, and cleanup. |
| LV1-14 | Preserve exact interoperable integers and binary64 values across independent decoders and hashes. |
| LV1-15 | Verify native NEST and CREBAIN behavior against a separately isolated direct oracle. |
| LV1-16 | Record exact installed artifact identities, complete-run evidence, and reproducible qualification commands. |
| LV1-17 | Declare measured latency and resource scope without inventing real-time or statistical guarantees. |
| LV1-18 | Enforce and test the chosen cross-project process and storage boundary. |

## Explicit exclusions

The local profile excludes remote endpoints, physical actuation, Haldir-gated commands, and real-time deadline guarantees.
It also excludes asynchronous latest-value control, action horizons, same-generation crash resume, arbitrary executable models, and calibrated posterior inference.

Each excluded profile needs a rejection test at the earliest owning boundary.
An unavailable Haldir gate cannot activate direct execution.
A failed secure remote connection cannot select local research transport.
Missing scientific evidence cannot activate a numerical or nominal substitute.

The [70-case mapping](acceptance-70.md) preserves each original case and its acceptance requirement.
An exclusion is a supported-scope decision with a required negative control.
It is not a passing result for the excluded behavior.

## Evidence and remaining gates

Native Rust and Python local owner implementations and conformance tests exist.
Galadriel's focused component gate passed 13 native tests, 14 scalar tests, and one documentation test in the working intake.
Those tests include actual detector invocation and a real framed child process.
They are synthetic component controls, not CREBAIN-produced scientific evidence.

The four-project installed NEST campaign, injected process-failure campaign, capture completeness campaign, and distribution gate remain open in this draft.
Mutable component results cannot serve as final release receipts.
Reference-profile publication needs one immutable source and artifact roster.
Each run must bind that roster to inputs, plan, configuration, observed outcomes, and test commands.

Reference-profile qualification must resolve these gates independently:

1. Freeze and register the reference descriptor and supported application matrix.
2. Pass all applicable component and independent decoder checks.
3. Pass real NEST and CREBAIN cases for each declared entity count.
4. Pass failure, retention, capture, and resource-boundary controls.
5. Qualify Darwin sandbox denial, inherited handles, guardian timeout, and parent-death cleanup.
6. Rebuild each consumer from immutable external dependencies.
7. Reproduce the complete run from clean installed artifacts.
8. Publish exact source and artifact identities with their remaining exclusions.

The [decision record](decision.md) explains the alternatives and unresolved review questions.
The [mathematical guide](math-guide.md) explains causality, time, NIS, retention, and completeness with worked examples.

## Maintained SDK source gate

Run the shared SDK gate with Python 3.11 or later:

```sh
python3 -I scripts/check_local_sdk.py --python python3
```

The gate tests the standalone Rust package with Rust 1.96.0 and its 1.88.0 minimum supported version.
It verifies source projections, package construction, and exact Python package bytes through a fresh wheel installation.
Installed Python suites require the native reference, buffer, and request-owner probes.
Missing probes, empty suites, skipped controls, and imports outside that installation fail the gate.
Mandatory gate-integrity controls exercise those checks and owned child-process cleanup.
The source roster and 22 historical reference files must remain unchanged across the run.
Git queries discard inherited Git routing variables and ignore replacement objects.
These comparisons establish observed byte equality, without an atomic snapshot or universal concurrent-mutation guarantee.

The runner bounds each command and the post-kill wait for its direct child.
It retains its private diagnostic directory after failure or unconfirmed cleanup.
The hosted SDK job uploads available command logs and source-roster diagnostics after failure.
These controls do not establish cleanup after the gate process itself dies.

The complete `scripts/check.sh` also tests broad-core feature combinations and scans the standalone lock against current and pinned advisory databases.
Hosted CI uses the same SDK runner and dependency-policy commands.
Python build and test tools use exact version pins; those SDK requirement files do not contain artifact hashes.
A complete bootstrap run requires a fresh, short-path checkout of the exact clean candidate commit.
The separate source-distribution checks archive `HEAD`; an uncommitted SDK run cannot qualify those changed bytes by implication.

Passing this source gate does not qualify installed applications, sensor profiles, scientific outcomes, or a final release.
