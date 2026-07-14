# Stepwise NEST integration and historical real-time-factor notes

> **Evidence boundary:** this note documents the stepwise NEST architecture and
> historical measurements. It does not certify the unreleased NCP
> `1.0.0-rc.1` artifacts, a hard-real-time deadline, secure live transport, or
> current Engram interoperability. Engram's native-1.0 migration is in progress,
> but the release-bound performance/live-simulator campaign is **NOT RUN**.

**Architectural capability:** a compatible backend can exchange data with a
*running* NEST kernel without tearing it down or rebuilding the network, using NEST's own
`Prepare()` → `Run(chunk)` → `Cleanup()` stepwise model with a persistent kernel.
This repository does not ship or certify a current NEST service, and the installed
live integration campaign is `NOT RUN`. Similar boundary exchange does not imply
latency, throughput, semantics, or interoperability equivalence with MUSIC.

The sections below retain an architectural review and historical external-backend
observations. They are migration input, not evidence about current consumer bytes.

### 1. Historically reviewed backend pattern
The external backend inspected for this note used `Prepare()` once, `Run()` per
step, and `Cleanup()` at close. Those consumer bytes are not shipped or pinned here;
current behavior must be verified in the consumer repository and installed artifact.

### 2. Kernel-state persistence — is the network rebuilt between reads?
In the historically inspected implementation, `ResetKernel()` occurred at `open()`.
Between `step()`s
there is no reset and no re-`Create`; the populations, recorders, generators and
all neuron state persist. Simulation time advances monotonically across chunks
(`sim_time_ms += advance_ms`). This describes that implementation, not a current
certification or proof for every backend.

### 3. Data readback — streaming deltas or re-reading history?
The historically inspected `step()` read each recorder's events and sliced `[last:]`, returning
**only the events since the previous step** — a streaming delta per chunk. The
other inspected control code read `n_events` counts, computing rate from
the **count delta** without materializing an event array. Both patterns need
duration and exact-version verification. The stable 1.0 observation plane carries
observation deltas only in
canonical-JSON `ObservationFrame`s. `ncp-core::BulkBlock` is a bounded packed
little-endian local/offline codec (~2× smaller in the measured fixture), not a
transport frame; proto `BulkObservation` is excluded from stable 1.0. A future
negotiated envelope would be a separate contract change (see
[`PERFORMANCE.md`](PERFORMANCE.md), #6).

### 4. Runtime input injection — can you stimulate mid-simulation?
The inspected pattern updated a generator **before** the next `Run` chunk. Whether
the loop meets wall-clock time is separate. The
mechanism differs per generator. `dc_generator.amplitude` is read live, so
`set(amplitude=)` between `Run`s takes effect immediately. A Poisson **rate**,
however, is baked into the generator at calibration (`Prepare()`), so setting
`poisson_generator.rate` via `device.set()` *after* `Prepare()` was silently
ignored in the historical probe. The rate was instead
**scheduled** ahead of the clock: the historically reviewed backend drove `rate_hz` via an
`inhomogeneous_poisson_generator` (and `rate_inject` via `step_rate_generator`)
with `rate_times`/`rate_values` at `biological_time + dt`. That behavior must be
reverified against the exact installed NEST/backend combination.

### 5. Granularity — continuous, or quantized?
The inspected NEST integration exchanged at `chunk_ms` boundaries. MUSIC also has
discrete exchange intervals, but its published end-to-end toolchain latency is a
different estimand; it cannot be used to quantify NCP's chunk trade-off.

### 6. Concurrency — can you read *during* a Run (mid-tick)?
The inspected PyNEST call was synchronous: read/inject occurred between `Run`
calls, not during one. This does not establish identical scheduling semantics or
concurrency behavior for MUSIC or another backend.

### 7. Real-time pacing — does it keep up with wall-clock?
`NeuroControlLoop` can pace to a target `rate_hz`, but sleeping cannot make a slow
backend meet a deadline. Neither the NCP candidate nor this note guarantees real
time, and no comparison with MUSIC or neuromorphic hardware follows from pacing.

### 8. Transport & reach — local only, or networked/multi-language?
MUSIC uses MPI within a co-launched allocation. NCP 1.0 names Zenoh as its stable
transport binding; the localhost gateway is lifecycle-only and WebSocket remains
experimental. Rust and TypeScript contain independent decisions, while Python and
C/C++ use Rust FFI and do not count as independent peers. No installed live-peer
matrix is complete.

Published MUSIC closed-loop measurements and the historical NCP per-exchange
measurements in this repository estimate different quantities under different
topologies, workloads, clocks, and software stacks. They cannot support a claim that
one system's closed loop is faster. The defensible architectural comparison is that
MUSIC coordinates co-launched simulators on a shared clock, while NCP exposes one
simulator through a heterogeneous network protocol. A release-bound comparison needs
one preregistered end-to-end estimand, matched workloads and hardware, raw samples,
uncertainty, and independent reproduction; that evidence is **NOT RUN**.

### 9. Multi-simulator coupling — NEST↔NEURON↔… with a shared clock?
Shared-clock multi-simulator coupling is outside the stable NCP 1.0 scope. This is
an architectural boundary, not a recommendation or comparative quality claim.

### 10. "Stopping" semantics — does returning control between chunks count as stopping?
Between `Run` chunks, control returns and the inspected kernel is paused until the
next call. That is persistent-state stepwise execution, not uninterrupted wall-clock
execution. Do not describe it as identical to MUSIC without matched scheduler and
state-transition evidence.

## Final answer

NCP's interfaces can support a persistent-state, stepwise NEST backend, and its
Zenoh streaming planes avoid per-tick lifecycle RPC. This repository does not prove
that a current installed backend meets real-time deadlines, preserves all scientific
semantics, or interoperates with independent live peers. Multi-simulator shared-clock
coupling remains outside stable 1.0.

**Caveats / good practice.** Use the `NestController` `n_events`-delta readback for
long runs (the `NestSession` path slices a growing events array — O(history) per
step). Pick `chunk_ms` for your latency/throughput point as you would a MUSIC tick.
Historical per-exchange transport measurements are informative only; do not compare
them directly with MUSIC closed-loop latency. See [`RATIONALE.md`](RATIONALE.md) →
"Why existing solutions were insufficient" for the architectural comparison.

Choosing between NCP, MUSIC, or another system requires the deployment's functional
scope and matched evidence. NCP claims no cross-system performance superiority.

---

## Chunking review boundary: `Prepare`, `Run`, and `min_delay`

A recurring, reasonable worry: *NEST has a `calibrate()` step that runs in C++ every
time the simulation starts/resumes; MUSIC seems to run "continuously" without it, but
NCP runs in `Run(chunk)` slices — so doesn't NCP re-pay `calibrate()` every chunk,
making big networks slower and harder to code (delays, plasticity)?*

For a correctly implemented Prepare-once loop, node preparation is expected outside
the per-`Run` inner loop. The exact cost and semantics remain version- and
backend-specific; this note is not proof that a current consumer implements them.

### 1. `calibrate()` is now `pre_run_hook()`, and it runs once per `Prepare()`, not per `Run()`

In NEST 3.4 the per-node lifecycle hook formerly called `calibrate()` was renamed
**`pre_run_hook()`** (alongside `init_state()` / `init_buffers()`). It precomputes the
time-step-dependent constants a node needs — e.g. the exact integration propagators for
`iaf_psc_alpha` (`exp(-h/tau_m)` and friends), which depend on the resolution `h` and
the neuron's time constants.

The key fact is **where** it is called. NEST's stepwise API splits the lifecycle
deliberately:

| Call | What it does | Cost |
|---|---|---|
| `nest.Prepare()` | prepares the connection infrastructure and **calls `pre_run_hook()` on every node** (the calibration) | once |
| `nest.Run(t)` | advances the kernel by `t` — integrate + deliver spikes at `min_delay` boundaries | per chunk; **no node `pre_run_hook`** |
| `nest.Cleanup()` | tears the prepared state down | once |

The NEST 3.9 source historically inspected for this note placed node
calibration in `nestkernel/node_manager.cpp`, `NodeManager::prepare_node_()` —
literally `n->init(); n->pre_run_hook();` — which is reached **only** from
`prepare_nodes()`, and `prepare_nodes()` is called **only** from
`SimulationManager::prepare()` (guarded by the "Prepare called twice." throw).
`SimulationManager::run()`, before it advances, calls **only** `io_manager.pre_run_hook()`
— a *different*, cheap hook that flushes recorder/IO-backend buffers — and **never**
`prepare_nodes()`. That reading suggests a node's `pre_run_hook()` occurs per
`Prepare()`, not per `Run()`. NEST is not dependency-pinned here, so the installed
source and behavior must be rechecked.

`nest.Simulate(t)` is *defined as* `Prepare(); Run(t); Cleanup()`. So the behaviour you
remember — "`calibrate()` ran every time I started/resumed" — is exactly what a
**`Simulate()`-per-chunk loop** does: it re-prepares (re-calibrates) and re-cleans-up on
every call. That is a real and well-known anti-pattern.

The historically reviewed external backend (`backends.py`: `NestBackend.open()` →
`NestSession.step()` → `close()`) calls `nest.Prepare()` **once** at session open,
`nest.Run(chunk)` for each control tick, and `nest.Cleanup()` **once** at close. The
kernel stays "prepared" across every chunk; `pre_run_hook()` fires once, at open, and
never again for the life of the session. (This is the entire reason the
`Prepare`/`Run`/`Cleanup` API was introduced — to lift calibration out of the inner
loop for stepwise use.) Those external paths are not current NCP artifacts.

The repository includes a local benchmark/probe for this hypothesis.
[`scripts/bench_chunk_overhead.py`](scripts/bench_chunk_overhead.py) times three
patterns on a real network and labels them:

- **monolithic** — `Prepare(); Run(T); Cleanup()` (one `Run`).
- **chunked-efficient** — `Prepare()` **once**, `Run(chunk)` in a loop, `Cleanup()` at
  the end. *"The only added cost is the per-`Run()` call overhead."* ← the NCP pattern.
- **chunked-naive** — `nest.Simulate(chunk)` per chunk = `Prepare()`+`Run()`+`Cleanup()`
  **every chunk**. *Shown to illustrate the expected preparation cost.*

The observed gap is consistent with preparation occurring outside each `Run`, but
the benchmark does not isolate every causal component. Probe the installed NEST with
[`scripts/verify_nest_chunking.py`](scripts/verify_nest_chunking.py): it counts NEST's
`"Preparing N node(s) for simulation."` log line (emitted by `prepare_nodes()`) and
checks whether `Prepare()` + repeated `Run()` and repeated `Simulate()` produce the
expected preparation-log counts.

### 2. Cross-system scheduler semantics are not established here

MUSIC has runtime ticks and NEST has internal scheduling slices, but this repository
does not bind a current MUSIC/NEST source pair or run a matched scheduler trace.
Therefore it does not claim identical preparation, pause, delivery, or exchange
semantics.

Historical source notes reported that MUSIC port setup was part of
the **same once-per-`Prepare` calibration** — `SimulationManager::prepare()` carries the
comment *"we use calibrate to map the ports of MUSIC devices, which has to be done before
enter_runtime"*. They also described NEST
advances under MUSIC by calling `music_runtime->tick()` once per `min_delay` slice (the
NEST MUSIC tutorial's runtime loop: *simulate a slice → `tick()` to communicate →
repeat*) and described internal execution as sliced into `min_delay` intervals:
`run()` clamps `to_step_ = std::min(from_step_ +
to_do_, kernel().connection_manager.get_min_delay())` and gathers/delivers spikes only at
slice end. These notes may guide a new comparison; they are not retained as
independent confirmations or equivalence evidence.

No claim is made that NCP and MUSIC use identical execution models, differ only by
transport, or have a closed-loop latency ordering. A matched end-to-end experiment
is required.

### 3. Scoped chunk-equivalence checks

The historically reviewed NEST implementation held in-flight spikes in delivery-time
buffers: a
spike emitted at `t` on a synapse of delay `d` is delivered at `t + d` even when a
`Run()` returns control at an intervening boundary. Chunk boundaries therefore do not
directly retime an already scheduled synaptic event. Bit-identical whole-run behavior
still depends on the chunk schedule satisfying NEST's `min_delay` and RNG constraints,
and on stimuli being scheduled reproducibly; the caveats below are part of this claim.

`bench_chunk_overhead.py` enforces this: with a fixed RNG seed it **asserts bit-identical
total spike counts** between monolithic and chunked-efficient (`--strict` exits non-zero
on any divergence) for the measured, aligned configurations. That regression supports
those configurations; it does not prove identity for an arbitrary chunk size. The
companion probe locally compares spike times and STDP weights under the same
preconditions. Neither is a general scientific-equivalence proof.

### 4. `min_delay` is one required integration constraint

Historically reviewed NEST documentation and source use **`min_delay`** (the
smallest synaptic delay) in scheduling and inter-thread/rank spike exchange. Its
exact performance and scientific consequences depend on the installed model and
version; no universal optimal multiple is asserted here.

The exact installed NEST build must validate allowable chunk values and interaction
with resolution, RNGs, devices, plasticity, and delays. MUSIC timing is not evidence
for that NCP choice.

### 5. Per-`Run` cost is workload-dependent

Entry/exit, buffer, event, device, and communication costs can depend on model size,
event rate, thread/rank layout, and devices. The historical benchmark does not prove
a fixed or vanishing per-`Run` fraction, and no MUSIC equivalence follows.

### 6. Candidate integration checklist

Subject to verification against the exact installed NEST/backend pair, a candidate
stepwise integration should:

1. `nest.Prepare()` **once** per session (calibrates once); never `nest.Simulate()` in
   the loop.
2. `nest.Run(chunk)` per tick, with `chunk` an **integer multiple of `min_delay`**
   (read it from `nest.GetKernelStatus("min_delay")`). Prefer a *large* throughput chunk
   and choose it only after semantic and performance tests.
3. Verify each stimulus device between `Run`s. In the historical probe,
   `dc_generator.amplitude` updates took effect, while a Poisson **rate** behaved differently:
   a `poisson_generator`'s rate is fixed at calibration, so a post-`Prepare`
   `set(rate=)` was ignored in the historical probe. The inspected backend used a
   **scheduled-time generator** whose next value is scheduled at
   `biological_time + dt`: `inhomogeneous_poisson_generator` for a Poisson spike
   source (`rate_hz`), `step_rate_generator` for a rate-based input (`rate_inject`),
   `step_current_generator` for a scheduled current. Verify each device rather than
   generalizing. NEST documentation for the installed version governs whether and
   how `SetStatus` may be used between `Prepare()` and `Cleanup()`.
4. `nest.Cleanup()` **once** at session close.

> **Two implementer caveats (correctness, not speed).** (a) If `chunk_ms` is **not** an
> integer multiple of `min_delay` *and* the network has multiple RNG sources, NEST's own
> *"requested simulation time is not an integer multiple of the minimal delay"* applies
> and chunked vs monolithic results can diverge. Reject unsupported durations and
> prove the selected schedule with the exact model rather than promising bit identity.
> (b) Evaluate scheduled-time
> generators (step 3) over live `device.set()` for stimulus where exact reproducibility
> matters.

Chunk size, transport, simulator work, and scheduling all contribute to end-to-end
latency; this note does not rank them universally.

### 7. Local installed-NEST probe

The historical values report NEST 3.8.0. No NEST release or consumer backend is
pinned by this repository. A runnable local probe is provided for an installed NEST:

[`scripts/verify_nest_chunking.py`](scripts/verify_nest_chunking.py) compares
preparation counts, timing, spike times, and STDP weights in its bounded fixture. A
pass applies only to that local fixture/version and is neither a backend integration
test nor release/scientific certification. See its header for exact commands.

---

## Historical real-time-factor sweep

Neither NCP nor this note guarantees real time. The retained developer sweep uses
the *real-time factor* `rt = bio_time / wall_time`: `rt >= 1.0` means the sampled
kernel integrates faster than real time (the precondition for a live loop);
`rt < 1.0` means the loop lags and is only usable offline.

`rt` is one admission metric. Chunk size, model, events, devices, threads/ranks,
hardware, transport, security, and consumer work all affect the full live loop.

### Method

Brunel-style balanced random network (the NEST standard scaling benchmark):
`iaf_psc_alpha`, 0.8N excitatory / 0.2N inhibitory, **fixed indegree** held
constant across N (`fixed_indegree`, CE=400 from E + CI=100 from I ⇒ ~500
recurrent synapses/neuron), inhibition-dominated (g=5), per-neuron Poisson drive
tuned for an async-irregular **~13 Hz** regime. Readback is a `spike_recorder` on
a 1000-neuron readout subset only (mimics an NCP `RecordSpec`; recording overhead
was not isolated). Build is
**outside** the timer; only `nest.Simulate(T_bio)` is timed; one untimed warmup,
then up to 3 timed reps with the **MIN wall** reported. NEST 3.8.0, OpenMP-only,
single MPI rank, 16 physical cores, 128 GB RAM. Attempt the same procedure with
[`scripts/bench_realtime.py`](scripts/bench_realtime.py).

The full benchmark methodology — this real-time sweep plus the chunk-overhead and
I/O-overlap/GIL benchmarks, with the timing protocol, correctness/equivalence
checks, exact commands, environment, and caveats (including the `conda run`
stdout-buffering caveat: run the env interpreter directly with `-u`) — is
documented once in
[`PERFORMANCE.md` → Benchmark methodology & reproducibility](PERFORMANCE.md#benchmark-methodology--reproducibility).
This section keeps the sizing results; see there for the method shared across all
three benchmarks.

### Real-time factor vs network size and threads

`rt` (bio-s per wall-s); **bold** = real time or faster.

| N (neurons) | ~synapses | T=1 | T=2 | T=4 | T=8 | T=16 |
|---|---|---|---|---|---|---|
| 10 000 | 5.0 M | 0.32 | 0.63 | **1.18** | **2.01** | **2.13** |
| 50 000 | 25 M | 0.033 | 0.063 | 0.14 | 0.30 | 0.35 |
| 100 000 | 50 M | 0.014 | 0.032 | 0.066 | 0.13 | 0.17 |
| 200 000 | 100 M | 0.0065 | 0.013 | 0.027 | 0.054 | 0.071 |

(N=200000 used T_bio=500 ms; `rt` scaled to its own bio time. N=100000 T=1 and
N=200000 T=1 ran a single timed rep, having exceeded a 60 s/rep skip threshold.)

### Historical sampled grid — not a capacity frontier

* **In this retained grid, `rt >= 1` appears only at N=10000 and T>=4.** Within
  N=10000 the sampled crossing sits between T=2 (0.63x) and T=4 (1.18x).
* **No sampled N>=50000 configuration reaches `rt >= 1`.** The closest is N=50000 at
  T=16 = 0.35x (~2.85x slower than real time).
* The ~17k–20k crossing drawn between 10k and 50k is an interpolation over an
  unsampled range. It is not a practical ceiling, admission threshold, or capacity
  measurement.

Fixed indegree makes total synapse count linear in N by construction. The sampled
`rt` trend is descriptive and must not be extrapolated. Retained firing rates were
12.3–13.5 Hz; this is a regime diagnostic, not proof of statistical invariance.

### Thread-scaling efficiency

Efficiency = speedup(T) / T relative to the same-N T=1 baseline.

| N | T=2 | T=4 | T=8 | T=16 |
|---|---|---|---|---|
| 50 000 | 1.89x (0.95) | 4.09x (**1.02**) | 8.98x (**1.12**) | 10.51x (0.66) |
| 10 000 | 1.94x (0.97) | 3.64x (0.91) | 6.22x (0.78) | 6.60x (0.41) |

* **The retained minima show ratios above 100% efficiency at T=4/T=8 for N=50k.**
  With at most three timed repetitions (and one for some cells), no uncertainty,
  and no independent reproduction, this is descriptive rather than a
  reproducibility claim. Cache effects are one hypothesis, not a demonstrated cause.
* The retained T=16 ratios are lower (0.66 for 50k and 0.41 for 10k). Hardware
  saturation, memory bandwidth, and event synchronization are hypotheses; the run
  did not isolate causes. Do not extrapolate the sparse grid.

### Retained resource observations

* **Memory:** reported RSS peaked ~5 GB at N=200000 / 100M synapses on the local
  128 GB host; this is not a release memory bound.
* **Build time** grew
  0.34 s (5M syn) → 7.2 s (50M) → 14.9 s (100M) at T=1, ~linear in synapse count.
  It is outside the timer, but at N=200000 the one-time build is a real fraction of
  any short run.
* The retained simulated-time/wall-time ratio includes the combined timed workload;
  it does not isolate a universal binding constraint.

### Concrete guidance

1. **Treat 4–8 threads as a starting point for this historical setup only.** That is
   where the retained minima show the highest ratios. Re-measure the exact model,
   artifact, NEST build, and hardware rather than assuming the result generalizes.
2. **Measure admission on the exact deployment.** Do not turn the interpolated
   10k–20k crossing into a neuron/synapse limit. Bind model, NEST build, package,
   hardware, load, security profile, and uncertainty before admitting a live loop.
3. **Accept non-real-time for offline.** If the science needs 50k+ neurons and the
   loop need not be live, `rt < 1` is fine — just do not advertise the session as
   real time. No open-session budget admission check is implemented; the integration
   must measure its own artifact/hardware combination and label it honestly.
4. **Shrink the chunk for latency, not for throughput.** `chunk_ms` trades latency
   against per-`Run()` overhead and can therefore change the achieved real-time
   factor even when the modeled-time result remains invariant under the conditions
   above.

### Caveats

* Numbers report **NEST 3.8.0 (OpenMP-only, single MPI rank, 16 cores)**, this
  connectivity, and this firing regime. No current NEST version or environment is
  release-pinned by this repository; later versions require a new run.
* The ~17k–20k crossing at T=16 is interpolated (no sample between 10k and 50k)
  and is not capacity evidence.
* `fire_hz` is reported from the first-rep event count, not the min-wall rep
  and therefore is not paired with the retained timing sample.
* A second local check of the N=50000 cell differed by roughly 7–12%. It was not an
  independent clean-room reproduction, and raw receipts for the full original grid
  are absent.
