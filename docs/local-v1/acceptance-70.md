# All 70 acceptance cases

Status: draft mapping. Every release row remains open.

Generated from [acceptance-70.source.json](acceptance-70.source.json).
The source retains each original case, priority, and requirement from the supplied acceptance plan.
A component test pointer is evidence of an available test surface, not an immutable release receipt.
An excluded profile needs a tested rejection boundary and is never recorded as a passing implementation.

The [reference profile](README.md#local-requirements) defines each `LV1-*` requirement.
The [open final product requirements](README.md#open-final-v1-requirements) also require modular compositions and declared multimodal profiles.
The complete installed campaign must retain exact commands, inputs, outputs, source identities, and failure dispositions.

Supplied acceptance plan SHA-256: `26674219d478830d544acca6eb1d19d894d459aa1180def6a7801ca246af2116`.

## Coverage at a glance

| Cases | Topic | Reference-profile gate |
| --- | --- | --- |
| 01-05 | Causality and clocks | Exact native schedule and declared clock scope |
| 06-10 | Positions and delivery | Exact cursor, explicit unsupported streaming profiles |
| 11-15 | Stateful retry | Retention, conflict, capacity, and uncertain-state retirement |
| 16-20 | Meaning and missingness | Fixed units, layouts, numeric domains, and evidence availability |
| 21-25 | NEST | Persistent native update, readout, and measured resource behavior |
| 26-30 | CREBAIN | Entity routing, direct oracle, and explicit simulation-only modes |
| 31-35 | Prisoma | Full pair closure, capacity, and terminal completeness |
| 36-40 | Resources | Aggregate bounds, process containment, measured cost, cleanup |
| 41-45 | Identity | Installed roles, generation cuts, no downgrade, exact profile |
| 46-50 | Usability | Honest timing, independent installation, clean reproduction |
| 51-70 | Expanded boundary | NCP-only ownership, exact numerics, guards, and recovery |

## 01. Drive a known plant observation through neural input, one neural advance, controller output, and one plant advance.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Every returned observation and applied action has the declared step index and causal predecessor. No action is applied a step early or late.

**Local requirement:** `LV1-02`, `LV1-15`.

**Required control:** Drive an actual source through one NEST advance, proposal, CREBAIN application, and next snapshot. Verify every causal digest and index.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 02. Request a neural/plant cadence that cannot be represented by the selected common integer timebase.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Preparation rejects it; there is no silent rounding or accumulated drift.

**Local requirement:** `LV1-01`, `LV1-03`.

**Required control:** Reject fractional or incompatible step, resolution, and delay grids before preparation. Accept the exact supported grid.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 03. Mix timestamps from unrelated monotonic clock domains.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** The runtime refuses unsupported age/one-way-latency calculations. Logical time remains independent of wall-clock measurements.

**Local requirement:** `LV1-03`, `LV1-10`.

**Required control:** Use logical microseconds only. Reject unsupported wall-clock age or unrelated-domain configuration without inventing latency.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 04. Receive a valid advancing sensor, stall the control loop past its freshness budget, then consume the pending sample.

Priority: **P0**. Local disposition: `excluded`. Release status: **OPEN**.

**Original requirement:** Original receive time is retained; consuming the frame does not make it fresh again. This bounds post-ingress waiting; test 55 covers body-source-to-application age.

**Local requirement:** `LV1-03`, `LV1-10`.

**Required control:** Real-time freshness budgets are outside this profile. Reject that selection and retain logical sample identity during a paused request.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 05. Execute the same prepared deterministic case at different wall-clock pacing rates, without changing logical inputs.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Results satisfy the declared reproducibility policy. Wall-clock pacing does not silently change the numerical experiment.

**Local requirement:** `LV1-03`, `LV1-15`.

**Required control:** Repeat identical logical inputs with varied wall-clock pauses. Compare full native outputs under the declared numerical policy.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 06. Deliver every 200 Hz sensor sample while a 50 Hz controller intentionally consumes only the latest.

Priority: **P0**. Local disposition: `excluded`. Release status: **OPEN**.

**Original requirement:** Ingress loss remains zero. Coalescing is counted separately. No loss-triggered emergency latch is set solely by downsampling.

**Local requirement:** `LV1-02`, `LV1-10`.

**Required control:** Independent sensor/controller rates and latest-value coalescing are not negotiated. Reject those cadence or queue fields before preparation.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 07. Inject genuine ingress gaps, duplicates, and bounded reordering separately.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Counters distinguish the cases; duplicates cannot refresh freshness or conceal missing positions. Attribution is not stronger than the evidence.

**Local requirement:** `LV1-05`, `LV1-06`.

**Required control:** Reject gaps and changed retries. Replay exact retained responses. Verify no duplicate mutation or artificial time refresh.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 08. Use a very large accepted loss-detector threshold and a huge sequence gap.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Configuration is rejected or the bounded-time mathematical update gives the correct restrictive result. No iteration cap silently suppresses the threshold crossing.

**Local requirement:** `LV1-05`, `LV1-13`.

**Required control:** Local steps use a bounded exact cursor, not a configurable loss detector. Reject huge sequence jumps before execution.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 09. Deliver an old generation after reconnect, including an emergency command.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** It cannot change the new generation's state. Restart requires a new prepared binding.

**Local requirement:** `LV1-01`, `LV1-07`.

**Required control:** Replay old run and endpoint generations after a fresh launch. Require rejection before role or backend state changes.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 10. Replace an unsent latest-value command while a recorder observes controller proposals.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Candidate identity, transport admission, actual publication, and application remain distinguishable. One published stream position never acquires conflicting committed payloads.

**Local requirement:** `LV1-02`, `LV1-09`.

**Required control:** Local execution has no unsent latest-value queue. Capture proposal and applied values separately, and reject queue-profile selection.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 11. Lose a successful step reply and resend the identical operation identity and payload.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The retained outcome is returned; the neural simulator and plant are not advanced again.

**Local requirement:** `LV1-06`.

**Required control:** Lose an actual successful step reply and retrieve identical retained bytes. Confirm native mutation counts remain one.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 12. Reuse an operation identity with changed input bytes or semantic content.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Conflict is rejected before mutation. Canonicalization policy is explicit.

**Local requirement:** `LV1-05`, `LV1-06`.

**Required control:** Reuse a retained identity with changed semantic input. Reject conflict before mutation and document typed canonicalization.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 13. Fill the outcome store while all retained outcomes are still contractually owed.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** New mutations are rejected before execution, or an explicitly negotiated acknowledgement releases retention. Required outcomes are not silently evicted.

**Local requirement:** `LV1-06`, `LV1-13`.

**Required control:** Hold the single owed result and submit a successor. Reject before execution until its exact digest is acknowledged.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 14. Query a retained result after the original execution deadline or lease expires.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** An authorized result-lookup policy can recover the outcome without granting new mutation authority. Unauthorized callers receive no protected result.

**Local requirement:** `LV1-06`, `LV1-10`.

**Required control:** Allow lookup through the still-owned private channel after mutation retirement. Remote principals and leases are excluded and grant no lookup capability.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 15. Kill, time out, or cancel a backend after execution starts but before commit can be established.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The result is marked indeterminate and that mutable generation is retired. Cancellation is not reported as rollback. No retry advances uncertain state again.

**Local requirement:** `LV1-07`, `LV1-13`.

**Required control:** Kill, stall, and cancel real owners after mutation starts. Retire coupled state and classify an unresolved effect as indeterminate.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 16. Transport a six-component position/velocity observation and a three-component acceleration action.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Units and frames remain component-correct. Position is not labeled as velocity, and velocity setpoints are not silently treated as acceleration.

**Local requirement:** `LV1-01`, `LV1-09`.

**Required control:** Verify exact six-component position/velocity and three-component acceleration layouts. Reject unit or axis substitution.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 17. Omit a required population readout whose configured command range is [0, 10].

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The absence is explicit. It cannot become an apparently observed Active command of 5 merely through midpoint substitution.

**Local requirement:** `LV1-04`.

**Required control:** Remove required recording evidence. Require explicit failure or declared missingness, never a fabricated midpoint Active value.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 18. Compare an available zero-valued signal, an unavailable signal, an empty spike window, and missing recording evidence.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** All four retain their distinct meanings through NCP and Prisoma.

**Local requirement:** `LV1-04`, `LV1-08`.

**Required control:** Carry available zero, absent observation, declared empty spike window, and missing recorder evidence through capture as distinct states.

**Current evidence:** `focused_component_tests_passed`. The working native adapter passed 13 native, 14 scalar, and one documentation test. Only the directly exercised assertions receive component credit. Publication and actual producer evidence are open.

[Implementation or component-test pointer](https://github.com/sepahead/galadriel/tree/main/crates/galadriel-local-adapter). This link does not identify an immutable qualified release.

## 19. Prepare duplicate, sparse, contradictory-unit, or reordered component mappings.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Invalid layouts are rejected before running. Accepted permutations have explicit immutable mappings and identical interpreted meaning.

**Local requirement:** `LV1-01`, `LV1-05`.

**Required control:** Reject duplicate, sparse, reordered, and contradictory layouts. The initial profile admits only its exact frozen layout.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 20. Inject non-finite values, overflowing counters, wrong arity, invalid availability padding, and forbidden numeric ranges.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Bounded rejection occurs before state mutation. An invalid frame is not repaired into valid actuation.

**Local requirement:** `LV1-05`, `LV1-14`.

**Required control:** Reject non-finite numbers, oversized counters, wrong arity, nonzero unavailable padding, and forbidden ranges before mutation.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 21. Execute many control steps with a prepared persistent NEST network.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The network is built and prepared according to the selected adapter contract, not reset or rebuilt per tick. Neural state persists. A single Prepare across all steps is required only when the qualified update mechanism permits it.

**Local requirement:** `LV1-03`, `LV1-15`.

**Required control:** Run a persistent actual NEST network over many steps. Count network construction and preserve neural state under the selected update mechanism.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 22. Change each supported stimulus parameter between successive Run calls in the exact selected NEST build.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Measured neuron/device behavior proves the input actually takes effect in the promised interval. Unsupported mutations are rejected at preparation.

**Local requirement:** `LV1-03`, `LV1-15`.

**Required control:** Vary every admitted stimulus between actual Run calls. Measure effects in the specified interval and reject unsupported mutations.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 23. Place spikes exactly on observation-window boundaries and, where supported, off-grid timestamps.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Every event is counted once under the declared endpoint convention; precise offsets are not silently rounded away.

**Local requirement:** `LV1-03`, `LV1-14`.

**Required control:** Place events on each readout endpoint and verify exactly one count. Reject unsupported off-grid model or timing selections.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 24. Compare long-run per-step extraction cost for counters and bounded event tails.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Cost and retained memory do not grow with total historical recording length when only a bounded current window is requested. Counter reset semantics are handled explicitly.

**Local requirement:** `LV1-13`, `LV1-17`.

**Required control:** Measure bounded current-window extraction over short and long runs. Demonstrate storage and work independent of historical event count.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 25. Repeat the adapter workload with declared thread/MPI configurations and transport/observer contention.

Priority: **P1**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Reproducibility and deadline claims remain scoped to measured configurations. Simulator workers do not silently consume all service capacity needed for feedback.

**Local requirement:** `LV1-03`, `LV1-17`.

**Required control:** Qualify the exact thread/MPI placement and interference tested. Reject undeclared execution configurations and publish no broader deadline claim.

**Current evidence:** `operational_not_run_in_this_draft`. A source implementation or synthetic test cannot replace the exact persistent-NEST native campaign.

## 26. Run one-, two-, and three-entity cases through the selected real CREBAIN adapter.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Roster ordering, per-entity state, and action routing remain exact. No cross-entity substitution occurs.

**Local requirement:** `LV1-09`, `LV1-15`.

**Required control:** Run actual one-, two-, and three-entity CREBAIN cases. Compare identity, state, innovation sources, and routed actions for every entity.

**Current evidence:** `operational_not_run_in_this_draft`. The actual body and isolated direct-oracle comparison need an immutable installed run receipt.

## 27. Compare a direct closed-loop baseline against the NCP-bound loop using the same controller, inputs, seeds, and schedule.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Trajectory and event differences satisfy the declared numerical policy; transport introduction does not change the experiment unintentionally. The direct oracle is an isolated test target, unreachable as an alternative path in the distributed runtime.

**Local requirement:** `LV1-15`.

**Required control:** Compare matched direct-oracle and NCP runs using identical actual kernels, controller, seeds, and logical schedule. Keep the oracle unreachable in deployment.

**Current evidence:** `operational_not_run_in_this_draft`. The actual body and isolated direct-oracle comparison need an immutable installed run receipt.

## 28. Remove one entity's observation while others remain valid.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Missingness and fallback are per entity. Valid peers are neither fabricated nor inadvertently discarded.

**Local requirement:** `LV1-04`, `LV1-09`.

**Required control:** Remove one entity's observation. Verify that its missingness remains explicit while valid peers retain their actual observations and actions.

**Current evidence:** `focused_component_tests_passed`. The working native adapter passed 13 native, 14 scalar, and one documentation test. Only the directly exercised assertions receive component credit. Publication and actual producer evidence are open.

[Implementation or component-test pointer](https://github.com/sepahead/galadriel/tree/main/crates/galadriel-local-adapter). This link does not identify an immutable qualified release.

## 29. Trigger HOLD and emergency behavior for every declared plant profile.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** The runtime applies the profile-specific behavior. Zero acceleration is not represented as a universal physical stop.

**Local requirement:** `LV1-09`, `LV1-10`.

**Required control:** Exercise active and zero_acceleration simulation modes. Reject physical HOLD/ESTOP profiles and never label zero acceleration a physical stop.

**Current evidence:** `operational_not_run_in_this_draft`. The actual body and isolated direct-oracle comparison need an immutable installed run receipt.

## 30. Expire or revoke command authority at the actual application boundary.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** An accepted or queued command cannot bypass current application-time authority and freshness checks. Simulator-only credentials cannot authorize physical actuation.

**Local requirement:** `LV1-07`, `LV1-10`.

**Required control:** Retire the local endpoint before a queued mutation and reject further work. Physical leases and application-time authority are excluded without fallback.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 31. Record a successful step end to end.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Evidence binds input snapshot, neural request/result, controller proposal, admitted/applied action, output snapshot, and outcome without conflating them.

**Local requirement:** `LV1-02`, `LV1-08`.

**Required control:** Bind source snapshot, exact neural response, proposal, body response, applied action, next snapshot, and capture outcome in one step pair.

**Current evidence:** `operational_not_run_in_this_draft`. The native Prisoma capture, terminal closure, and fault campaign need an immutable installed run receipt.

## 32. Remove every event belonging to one whole step.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The terminal plan/progress record reveals incomplete capture. A self-consistent retained subset is not declared complete.

**Local requirement:** `LV1-08`.

**Required control:** Delete one complete captured step while retaining valid neighbors. Require terminal count and contiguous-prefix verification to fail.

**Current evidence:** `operational_not_run_in_this_draft`. The native Prisoma capture, terminal closure, and fault campaign need an immutable installed run receipt.

## 33. Deliver observation and command events out of order, twice, and with conflicting payloads.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Bounded joins, duplicate handling, and conflicts are explicit; arrival order does not fabricate causality.

**Local requirement:** `LV1-06`, `LV1-08`.

**Required control:** Reorder, duplicate, and conflict complete captured pairs. Reject invalid joins without using arrival order as causality.

**Current evidence:** `operational_not_run_in_this_draft`. The native Prisoma capture, terminal closure, and fault campaign need an immutable installed run receipt.

## 34. Exceed recording capacity under the lossless logical-time profile.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The host pauses at a defined boundary or terminates the capture/run according to policy. It does not silently lose records while claiming completeness.

**Local requirement:** `LV1-08`, `LV1-13`.

**Required control:** Exhaust lossless capture capacity before the next step. Verify neither neural nor body owner mutates without its reservation.

**Current evidence:** `operational_not_run_in_this_draft`. The native Prisoma capture, terminal closure, and fault campaign need an immutable installed run receipt.

## 35. Exceed recording capacity under the real-time best-effort profile.

Priority: **P1**. Local disposition: `excluded`. Release status: **OPEN**.

**Original requirement:** Feedback stays within its selected resource policy; drops and affected completeness claims are explicitly recorded. Recorder lag is not mislabeled as simulator or network failure.

**Local requirement:** `LV1-08`, `LV1-10`.

**Required control:** Reject real-time best-effort capture mode before preparation. The selected profile cannot silently drop records.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 36. Send maximum-size accepted observation messages to all permitted subscribers.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Aggregate bytes, not only item counts, stay within declared reservations including retained buffer ownership.

**Local requirement:** `LV1-13`.

**Required control:** Exercise maximum admitted frame sizes across all four channels and result slots. Measure aggregate owned buffers rather than item counts alone.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 37. Use a slow, continuously busy, panicking, and non-returning observer callback.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Observer work cannot monopolize the control executor. Containment and teardown policy are demonstrated, not inferred from an async function name.

**Local requirement:** `LV1-07`, `LV1-13`.

**Required control:** Stall, panic, and never return from an actual monitor process. Demonstrate bounded containment and cleanup without a command-capable callback in the coordinator.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 38. Saturate lifecycle/backend requests with slow or stuck operations.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Admission remains bounded. Per-backend mutation is serialized, and terminal cleanup/containment has a defined path.

**Local requirement:** `LV1-06`, `LV1-13`.

**Required control:** Saturate the single operation/result slot with slow and stuck calls. Measure serialized execution, rejection, and bounded process teardown.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 39. Instrument a warmed-up small-frame step with allocation, copy, serialization, and profile-hash counters.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The selected fast-path budget is met; unexpected repeated work is a test failure rather than an undocumented optimization opportunity.

**Local requirement:** `LV1-13`, `LV1-17`.

**Required control:** Instrument allocations, copies, serialization, and descriptor hashing on warmed steps. Declare and enforce the measured local budget.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 40. Repeatedly prepare, run, cancel, finish, and disconnect sessions.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Threads, tasks, subscribers, handles, memory, and generation state return to their declared baseline or bounded retained state.

**Local requirement:** `LV1-07`, `LV1-13`.

**Required control:** Repeat native prepare, run, finish, cancel, and disconnect cycles. Check process, descriptor, memory, and generation-state baselines.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 41. Use a valid certificate or local capability for the wrong principal, route, operation, role, or session kind.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Receiver-owned authorization rejects it; a payload identity claim cannot substitute for authenticated origin.

**Local requirement:** `LV1-01`, `LV1-10`.

**Required control:** Use a valid installed local channel with the wrong role, operation, run, or generation. Reject before execution. Do not describe payload labels as authentication.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 42. Rotate/revoke a principal while messages are queued.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Each admission is tied to a defined immutable policy generation, and the selected revocation boundary is enforced consistently.

**Local requirement:** `LV1-07`, `LV1-10`.

**Required control:** Rotate local process generations and reject queued old work. Remote principal and certificate rotation remain excluded and unqualified.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 43. Request an unavailable secure profile or attempt downgrade to an unauthenticated binding.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Connection/admission fails closed. Local research transport is selected explicitly, never as a silent fallback.

**Local requirement:** `LV1-10`.

**Required control:** Reject remote secure or downgrade selections before launch. Require explicit local profile selection with no automatic fallback.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 44. Run horizon vectors at exact expiry, beyond the maximum TTL, and with a non-finite ratio.

Priority: **P1**. Local disposition: `excluded`. Release status: **OPEN**.

**Original requirement:** Independent implementations produce identical acceptance and executable-window decisions.

**Local requirement:** `LV1-10`, `LV1-14`.

**Required control:** Action horizons and TTL scheduling are outside the local application. Reject horizon fields. Retain separate broad-candidate horizon conformance without importing its claims.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 45. Omit or alter the selected semantic/profile identity during preparation.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** A prepared strict session cannot form from advisory compatibility alone. Optional-feature negotiation does not change already-prepared meaning.

**Local requirement:** `LV1-01`, `LV1-10`.

**Required control:** Reject missing, changed, or unregistered profile/plan identities before preparation. Later inputs cannot change prepared meaning.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 46. Measure complete sample-to-application latency and each internal stage.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Report p50, p99, p99.9, maximum observed, deadlines, and failures. A timer ending before serialization or publication is not called closed-loop latency.

**Local requirement:** `LV1-17`.

**Required control:** Measure complete source-to-body-response timing and separate stages. Publish p50, p99, p99.9, maximum, sample count, failures, and measurement limits.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 47. Compare matched direct and NCP runs, including instrumentation overhead.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Attribute transport/integration cost with a justified paired methodology; do not subtract unrelated percentile summaries.

**Local requirement:** `LV1-15`, `LV1-17`.

**Required control:** Use paired matched direct and NCP trials. Measure instrumentation cost. Do not subtract unrelated percentile summaries.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 48. Exercise scheduled arrivals during stalls, background load, and slow recording.

Priority: **P1**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Missed work and delay are counted against the intended schedule. The benchmark does not hide stalls by generating less offered work.

**Local requirement:** `LV1-10`, `LV1-17`.

**Required control:** Scheduled real-time arrivals are excluded. Measure deliberate stalls in logical-time runs and reject a real-time scheduling profile.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 49. Install and build CREBAIN/Prisoma consumers outside the NCP workspace, from the intended published artifacts.

Priority: **P2**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Dependency pins, patches, features, names, schemas, and bindings work without undocumented workspace inheritance.

**Local requirement:** `LV1-16`.

**Required control:** Install CREBAIN and Prisoma outside the NCP workspace from exact intended artifacts. Reject hidden path dependencies and inherited root patches.

**Current evidence:** `installed_gate_open`. Clean external builds, artifact identities, and full native runs have not been qualified by this documentation draft.

## 50. Reproduce the complete chosen-profile run from clean artifacts and retained inputs.

Priority: **P2**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Another operator obtains the declared behavior and scoped performance results. Unsupported profiles remain visibly unsupported.

**Local requirement:** `LV1-16`.

**Required control:** Reproduce the complete selected run from clean artifacts and retained inputs. Keep all unsupported profiles visibly rejected.

**Current evidence:** `installed_gate_open`. Clean external builds, artifact identities, and full native runs have not been qualified by this documentation draft.

## 51. Run Engram against all approved ecosystem peers with only NCP endpoints enabled.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The full declared workflow succeeds without Host API, custom HTTP/IPC, direct engine import, shared storage, or file-polling integration. NEST remains private to its owner.

**Local requirement:** `LV1-02`, `LV1-18`.

**Required control:** Run the actual Engram host with native NCP endpoints for all selected peers. Trace communication and keep NEST private to its owning process.

**Current evidence:** `installed_gate_open`. Clean external builds, artifact identities, and full native runs have not been qualified by this documentation draft.

## 52. Attempt each forbidden cross-project path deliberately.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Package policy and runtime sandboxing reject the bypass. Log the rejection without granting access through a helper process or broad inherited credential.

**Local requirement:** `LV1-18`.

**Required control:** Attempt direct engine imports, private HTTP/IPC, shared-store writes, file polling, and helper-process bypasses. Require enforced package and OS-boundary rejection.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 53. Move a control-loop object between execution threads with different thread-local elapsed origins.

Priority: **P1**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Time remains in one defined domain or migration is disallowed explicitly. A valid move does not create false expiry or a spurious clock-rewind hold.

**Local requirement:** `LV1-03`, `LV1-13`.

**Required control:** A mutable owner stays in its declared execution context. Reject or test any thread-migration mode. Logical time cannot inherit a thread-local clock origin.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 54. Encode endpoints of a finite positive range narrower than machine epsilon near one.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** The upper endpoint maps to the declared upper output, or preparation rejects the explicitly unsupported scale. Unit changes do not silently collapse valid ranges.

**Local requirement:** `LV1-05`, `LV1-14`.

**Required control:** Retain exact endpoint arithmetic tests in the generic codec. The local fixed-layout application must reject unsupported arbitrary encoding scales.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 55. Delay a body-originated source grant by 15 ms in each direction with a 20 ms budget.

Priority: **P0**. Local disposition: `excluded`. Release status: **OPEN**.

**Original requirement:** Final application rejects expiry relative to the original body event. No receiver or relay restarts the deadline.

**Local requirement:** `LV1-03`, `LV1-10`.

**Required control:** Physical source-age grants and 20 ms wall-clock budgets are unsupported. Reject this selection rather than restarting a deadline or claiming physical freshness.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 56. Return a grant from a different source, generation, authority term, or evicted record.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** No application occurs from a guessed or substituted reference. A receiver never falls back to the newest grant.

**Local requirement:** `LV1-01`, `LV1-02`.

**Required control:** Reject substituted snapshot, response, run, or generation digests. Local execution has no newest-grant fallback or admitted physical authority term.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 57. Cut execution after each neural/body commit and before each receipt or pair closure.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The maximal known closed prefix is preserved. The uncertain suffix is explicitly classified and no dependent step advances an unresolved coupled generation.

**Local requirement:** `LV1-07`, `LV1-08`.

**Required control:** Cut each real owner after commit and before response or pair closure. Preserve the maximal known closed prefix and block its uncertain suffix.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 58. Lose a committed response, then retrieve it after the result was acknowledged or while still retained.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Retained exact payload and receipt are replayed when owed. After payload release, high-water state prevents re-execution and the declared unavailable outcome is returned.

**Local requirement:** `LV1-06`, `LV1-07`.

**Required control:** Retrieve owed exact bytes before acknowledgement. After release, require unavailable with unchanged mutation high-water state.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 59. Force result serialization or byte-reservation failure after a backend mutation.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The outcome is never labeled rejected-before-execution. Required containment or retirement occurs and no alternate operation ID retries the uncertain effect.

**Local requirement:** `LV1-07`, `LV1-13`.

**Required control:** Force reservation failure before mutation and serialization failure after mutation. Preserve the distinct rejection and indeterminate classes.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 60. Select Haldir-gated mode, then attempt direct Engram command and gate-timeout fallback.

Priority: **P0**. Local disposition: `excluded`. Release status: **OPEN**.

**Original requirement:** CREBAIN rejects Engram as commander. Gate failure follows the prepared restrictive policy; it does not activate a parallel direct route.

**Local requirement:** `LV1-10`.

**Required control:** Reject Haldir-gated plan selection before any endpoint preparation. Attempt direct-command and gate-timeout fallback and require no run to begin.

**Current evidence:** `focused_component_tests_passed`. The working native adapter passed 13 native, 14 scalar, and one documentation test. Only the directly exercised assertions receive component credit. Publication and actual producer evidence are open.

[Implementation or component-test pointer](https://github.com/sepahead/galadriel/tree/main/crates/galadriel-local-adapter). This link does not identify an immutable qualified release.

## 61. Feed the Galadriel adapter missing uncertainty, wrong units, invalid covariance, or an unsupported detector profile.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The actual selected detector contract rejects or abstains explicitly. It does not fabricate uncertainty or label absent assessment nominal.

**Local requirement:** `LV1-05`, `LV1-11`.

**Required control:** Reject absent required source uncertainty, wrong units, malformed covariance, or a wrong detector profile. Preserve actual scalar research insufficiency and no fabricated nominal report.

**Current evidence:** `focused_component_tests_passed`. The working native adapter passed 13 native, 14 scalar, and one documentation test. Only the directly exercised assertions receive component credit. Publication and actual producer evidence are open.

[Implementation or component-test pointer](https://github.com/sepahead/galadriel/tree/main/crates/galadriel-local-adapter). This link does not identify an immutable qualified release.

## 62. Submit a favorable or forged Galadriel assessment without independently granted action authority.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** No lease, permission widening, final command, or reset capability is created. Advisory composition is monotone with respect to existing permission.

**Local requirement:** `LV1-10`, `LV1-12`.

**Required control:** Forge favorable monitor output and request command, lease, or reset operations. Require fixed-role rejection and no change to body authority.

**Current evidence:** `focused_component_tests_passed`. The working native adapter passed 13 native, 14 scalar, and one documentation test. Only the directly exercised assertions receive component credit. Publication and actual producer evidence are open.

[Implementation or component-test pointer](https://github.com/sepahead/galadriel/tree/main/crates/galadriel-local-adapter). This link does not identify an immutable qualified release.

## 63. Compare asynchronous monitoring and step-bound online-guard profiles under reordered assessments.

Priority: **P0**. Local disposition: `partial_exclusion`. Release status: **OPEN**.

**Original requirement:** Monitoring cannot affect state. The guard consumes only its declared exact-step dependency and has explicit missing/stale/abstention policy.

**Local requirement:** `LV1-11`, `LV1-12`.

**Required control:** Admit only exact-step record-only monitoring. Reject online-guard and asynchronous-control profiles. Reordered assessments cannot control a body step.

**Current evidence:** `focused_component_tests_passed`. The working native adapter passed 13 native, 14 scalar, and one documentation test. Only the directly exercised assertions receive component credit. Publication and actual producer evidence are open.

[Implementation or component-test pointer](https://github.com/sepahead/galadriel/tree/main/crates/galadriel-local-adapter). This link does not identify an immutable qualified release.

## 64. Give a private worker, presentation panel, or extension parser an attempted out-of-role request.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** It has neither credentials nor inherited handles that allow role escalation, command publication, or direct access to another project's mutable state.

**Local requirement:** `LV1-10`, `LV1-18`.

**Required control:** Audit inherited descriptors and credentials, then attempt out-of-role requests from workers and presentation code. Protocol role tests alone do not prove OS isolation.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 65. Rebuild the real Engram host and all adapters from the recorded repository identities.

Priority: **P2**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The executable host, not a placeholder repository, is used. Dirty or mismatched builds and unrecorded private patches cannot receive a qualification receipt.

**Local requirement:** `LV1-16`.

**Required control:** Build executable Paper2Brain/Engram and every selected adapter from recorded immutable objects. Reject dirty, mismatched, or privately patched artifacts.

**Current evidence:** `installed_gate_open`. Clean external builds, artifact identities, and full native runs have not been qualified by this documentation draft.

## 66. Remove or conflict the terminal run record while all retained individual rows remain valid.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Capture completeness is unresolved or invalid, not inferred from the apparently consistent subset. Planned versus completed counts stay distinct.

**Local requirement:** `LV1-08`.

**Required control:** Remove or conflict the terminal run record after valid individual rows exist. Require incomplete or invalid capture, never inferred completeness.

**Current evidence:** `operational_not_run_in_this_draft`. The native Prisoma capture, terminal closure, and fault campaign need an immutable installed run receipt.

## 67. Saturate observer and result reservations before the next lossless logical step.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Admission pauses or rejects before neural/body mutation. Reservation release after acknowledgement is bounded and cannot be counted twice.

**Local requirement:** `LV1-06`, `LV1-08`, `LV1-13`.

**Required control:** Saturate capture and retained-result reservations before a new step. Reject before mutation and prove acknowledgement cannot release capacity twice.

**Current evidence:** `operational_not_run_in_this_draft`. The native Prisoma capture, terminal closure, and fault campaign need an immutable installed run receipt.

## 68. Make a GUI projection stale, altered, or disconnected while the NCP data path remains active.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** No agent/controller consumes the presentation projection as authoritative input. UI status cannot refresh source grants or authority.

**Local requirement:** `LV1-12`, `LV1-18`.

**Required control:** Alter or disconnect a presentation projection during a native run. Verify it has no authoritative read or command path and cannot refresh state.

**Current evidence:** `acceptance_gate_open`. This row specifies required evidence. No passing result is asserted.

## 69. Request oversized simulation creation or embedded executable code through an external data field.

Priority: **P0**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** The bounded model-creation contract rejects unsupported resource requests and code execution. Cancellation/cleanup does not leak an uncontrolled worker.

**Local requirement:** `LV1-01`, `LV1-05`, `LV1-13`.

**Required control:** Reject excess entity/step/resource requests and executable code fields before creating a simulator. Demonstrate bounded worker cleanup.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.

## 70. Run independent decoders against exact integers, changed semantic identities, unknown enums, duplicate keys, availability padding, and horizon boundaries.

Priority: **P1**. Local disposition: `required`. Release status: **OPEN**.

**Original requirement:** Every advertised public path agrees with the chosen contract. Unknown diagnostic data cannot become executable control semantics; private dialects fail qualification.

**Local requirement:** `LV1-05`, `LV1-14`.

**Required control:** Run independent Rust and Python decoders over integers, profile identities, enums, duplicate keys, padding, and rejected horizon fields. Reject semantic disagreement.

**Current evidence:** `component_test_sources_present`. Local Rust owner and shared-data controls exist. Independent Python controls remain a separate implementation. The exact immutable operating gate is open.

[Implementation or component-test pointer](../../ncp-core/tests/local.rs). This link does not identify an immutable qualified release.
