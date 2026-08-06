# NCP and neuromorphic hardware

> **Candidate boundary:** this is an informative integration design for the
> unreleased, release-blocked NCP `1.0.0-rc.1` candidate. It is not evidence for a
> neuromorphic adapter, hardware target, real-time path, physical safety case, or
> completed consumer migration.

NCP wire 1.0 separates a simulation provider from plant perception and action.
`ObservationFrame` is deliberately simulation-only: it requires
`is_simulation_output=true` and `calibrated_posterior=false`. A provider must not
put physical-device output in that frame and relabel it as simulation output.

This boundary does not make neuromorphic hardware unusable. It means that hardware
needs an explicit role and provenance model. A physical device can participate only
through an already valid plant-facing surface, or through a future extension that
defines device provenance, capability negotiation, timing, limits, and evidence.

## Current evidence boundary

The NCP [implementation ledger](docs/implementation/NCP_1_0_TASK_LEDGER.md)
records Engram's native-1.0 provider migration as open. NCP retains no public,
installed, source-bound qualification receipt for a neuromorphic-hardware adapter.
Private consumer source is not a public citation or NCP release artifact.

NCP core does not define a simulator or hardware backend. It defines the contract
that a provider consumes. Any provider-specific record and stimulus mapping needs
its own public support matrix and installed evidence. A simulator adapter is not
proof that another substrate is interchangeable.

## First-principles adapter boundary

A future hardware adapter can reuse an application-level neural vocabulary only
where the meanings match exactly. It must define at least:

- how a content-addressed model and topology are loaded;
- which populations, neuron identifiers, observables, and stimuli are supported;
- units, quantization, precision, fan-in, memory, and output bounds;
- how NCP session time maps to device time and what happens on deadline overrun;
- whether execution is stepped, streamed, accelerated, or wall-clock coupled;
- the provenance of every returned value;
- reset, restart, partial-failure, and ownership behavior; and
- the security and plant-authority boundary around any physical action.

A trait-compatible method name is not enough. The adapter, descriptor, fixtures,
transport behavior, and installed evidence must agree.

## Simulation-before-deployment workflow

1. **Develop in simulation.** Exercise the declared model, inputs, observations,
   and control logic against a simulation provider. Preserve simulation provenance.
2. **Freeze the comparison subject.** Bind the model, topology, channel mapping,
   parameters, software, seeds, and expected numeric tolerances to exact digests.
3. **Port outside the current simulation claim.** Translate the frozen subject to
   the target device with explicit changes for unsupported models, precision,
   timing, and topology.
4. **Qualify the hardware surface.** Use a valid plant-facing NCP role or a reviewed
   provenance-aware extension. Do not emit physical results as wire-1.0 simulation
   observations.
5. **Compare without certifying.** Replay bounded inputs and compare separately
   labelled simulation and device records. A close trace is evidence for that test
   profile only; it is not paper reproduction, posterior calibration, or safety
   certification.

Application channel names can remain stable across steps, but identity,
capabilities, provenance, timing, and safety evidence must be renegotiated for the
hardware target.

## Hardware-in-the-loop boundary

Hardware-in-the-loop adds real links, clocks, queues, and failure modes. The NCP
concepts for TTL, HOLD, ESTOP, stream epochs, and link telemetry can inform that
integration. Unit tests of those primitives do not qualify a device path.

The body remains final actuator authority. NCP ESTOP is a protocol control, not a
physical emergency-stop certification, and there is no universal zero-safe action.
The content-addressed plant profile must define the actual HOLD and ESTOP behavior.

## Analysis boundary

An observer can compare information flow or other metrics across separately
labelled simulation and device records. Such analysis is non-normative. It cannot
grant runtime authority or certify model fidelity, interoperability, security,
real-time behavior, scale, or release readiness.
