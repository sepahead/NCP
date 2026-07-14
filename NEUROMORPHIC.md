# NCP for neuromorphic hardware — and for sim-before-deploy

> **Candidate boundary:** this is an informative integration design for unreleased
> NCP `1.0.0-rc.1`, not evidence that any neuromorphic adapter, hardware target,
> real-time path, or physical safety case has been certified. Remaining wire-0.8
> clients require the breaking 1.0 migration.

Engram's integration layer, not NCP core, defines a `SimulationBackend` trait in
`backends.py`: NEST today, while the **wire contract knows nothing about NEST**. It
speaks neural record/stimulus
(`V_m`/`spikes`/`rate`, `current_pA`/`rate_hz`/`spike_times`) against named
populations, advanced in `Run`-style chunks. A **neuromorphic chip** can expose a
similar application surface, but current wire 1.0 requires every observation to be
raw simulation output with `is_simulation_output=true` and explicitly excludes
experimental recordings. Physical-device output cannot be relabelled as simulation
output. The shared vocabulary is therefore design input for a future provenance-
aware extension, not evidence that a chip is an interchangeable native-1.0 backend.

## Where NCP helps

### 1. One interface, swap the substrate (the headline use)
A robot/UAV client and an analysis/observer client are written against
NCP, not against NEST. A future contract can preserve most record/stimulus and
lifecycle semantics across simulation and hardware, but it must add a closed,
fail-closed provenance discriminator before physical-chip observations are legal.
Device capabilities, plant profile, timing, and safety evidence also require
renegotiation and testing. The useful goal is a stable application abstraction—not
an untrue claim that current wire 1.0 already makes the substrate interchangeable.

Candidate future backend adapters could mirror `NestBackend`'s
`Prepare`/`Run(chunk)`/`Cleanup` plus record/stimulus mapping:
- **Intel Loihi 2 via Lava** — Lava `Process` graphs with `run(RunSteps/RunContinuous)`
  map onto NCP `open`/`step`/`run`; inject via Lava input ports (≈ NCP stimulus),
  read via output ports / probes (≈ NCP record). Real-time / faster-than-real-time.
- **SpiNNaker / SpiNNaker 2 via sPyNNaker (PyNN)** — PyNN `run(t)` is the chunked
  advance; `pop.record(...)` and `pop.set(...)` are the record/stimulus surface;
  SpiNNaker's real-time operation suits the control loop.
- **BrainScaleS-2** — analog, ~10³–10⁴× accelerated: excellent for fast design
  sweeps, but its I/O cadence differs; NCP's `chunk_ms` and the resilience layer
  still frame the exchange.
- **Akida / other event-based accelerators** — same record/stimulus mapping where
  a spiking I/O API exists.

These sketches need a provenance-aware protocol revision plus new conformance and
device evidence; implementing only the existing trait is insufficient.

### 2. Sim-before-deploy workflow
The standard neuromorphic path is develop and validate in simulation, then deploy to
chip. NCP can keep much of the application workflow stable, but current wire 1.0
ends at the simulation boundary:
1. **Develop** the closed loop (sensor → SNN → command) against the **NEST**
   backend over NCP — fast iteration, full observability, the `NeuroControlLoop`.
2. **Validate** the streaming control plane and resilience layer
   (`ActionBuffer`, `LinkMonitor`) while retaining simulation provenance.
3. **Deploy** only through a future provenance-aware chip binding. Application
   channel mappings may remain stable, but the wire identity, evidence, device
   timing, and safety case must be renegotiated and retested.

### 3. Differential (sim-vs-hardware) testing — for free
The same declared channel surface can drive an offline or future-protocol A/B: replay
one stimulus trace into NEST and a chip, then compare simulation observations with
separately labelled device observations. Current `ObservationFrame`s cannot carry
the chip half honestly: setting `is_simulation_output=true` would mislabel physical
output, while setting it false violates wire 1.0. Any fidelity comparison therefore
needs an out-of-band device record today or a future provenance-aware frame. It is a
comparison, not validation that either substrate reproduces a paper.

### 4. Hardware-in-the-loop (HIL)
Under a future device-provenance extension, a chip can serve a robot or physics-sim
client. The resilience layer (`RESILIENCE.md`) would then be load-bearing because
chip↔host and host↔robot are real, lossy links. Current action-buffer, TTL, HOLD, and
link-monitor concepts remain useful, but their simulation tests do not certify the
future hardware path or make it native wire 1.0.

### 5. An information-theoretic analysis client as a sim-to-hardware fidelity metric
An analysis/observer client (e.g. one computing Partial Information Decomposition /
PID) can consume a future provenance-aware `(V,L,D,A)` observation stream. Run the
same analysis against separately labelled NEST and chip records to get an
**information-theoretic** comparison: does the chip preserve the same
unique/redundant/synergistic information flow {sensors → action} as the simulator,
or does device noise/quantization destroy a synergistic channel? That is a far
sharper "did porting to hardware change the computation?" test than trace RMSE.

## Honest limits
- These backend adapters are **not yet implemented** — `NestBackend` is the only
  live one. Current NCP 1.0 does not admit physical-device observations without
  mislabelling them; a `LavaBackend` / `SpiNNakerBackend` therefore requires a
  separately specified provenance extension, not only adapter code.
- Chips constrain models (fixed neuron types, fan-in, weight precision); a model
  that runs in NEST may need adaptation for silicon. NCP doesn't hide that — it
  makes the *interface* constant, not the model.
- Hard real-time guarantees come from the chip + its host stack (SpiNNaker is
  strong here), not from NCP; NCP provides the chunked exchange, QoS, and
  fail-safe around it.
