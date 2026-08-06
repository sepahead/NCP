# Plasticity vocabulary and integration boundary

> **Candidate boundary:** this is an informative design note for the unreleased,
> release-blocked NCP `1.0.0-rc.1` candidate. It does not claim that NCP reproduces
> a paper, validates learning, provides a calibrated posterior, or has completed a
> native-1.0 plasticity integration.

NCP can describe neural populations, record requests, and stimulus requests. The
wire also reserves `weight` and `weight_set` vocabulary. Vocabulary is not runtime
support: a provider must declare, implement, test, and retain evidence for each
accepted observable and stimulus.

## Current wire vocabulary

- `NetworkRef.population_sizes` names populations and their sizes. A size of `1`
  can describe one neuron.
- `NetworkRef.params` carries bounded model parameters. Their meaning is
  provider-specific and must be declared.
- `RecordTarget.ids` can select members of a target when the provider supports
  that selection.
- `RecordTarget.observable="weight"` can request a weight observation.
- `StimulusTarget.kind="weight_set"` can request a weight mutation.
- `current_pA`, `rate_hz`, `spike_times`, and `rate_inject` describe input
  mechanisms. They do not assign reward, error, or neuromodulation semantics by
  themselves.

An unknown/default value cannot grant mutation authority or make an unsupported
operation succeed. Negotiation and provider validation must reject a request that
the installed backend cannot execute.

## Provider evidence boundary

The NCP [implementation ledger](docs/implementation/NCP_1_0_TASK_LEDGER.md)
records Engram's native-1.0 provider migration as open. NCP retains no public,
installed, source-bound qualification receipt for that provider's record,
stimulus, or plasticity support. Private consumer source is not a public citation
or NCP release artifact.

Do not infer support from similar names. A neuron-model recordable named `w` can
be an analog state variable; it is not evidence that a provider reads or changes
synaptic connection weights. NCP has no retained native-1.0 evidence for explicit
spike-train injection, weight readback, weight mutation, or a closed plasticity
loop.

## What a plasticity integration would require

Short-term plasticity, spike-timing-dependent plasticity, and reward-modulated
plasticity can live inside a simulator or device model. NCP can carry the inputs
and outputs only after the provider defines an exact mapping.

| Required surface | Minimum evidence |
|---|---|
| Plastic network | Content-addressed model and topology, supported synapse types, parameter bounds, and deterministic construction rules |
| Weight observation | Exact connection selection, ordering, units, output bounds, and tests that exclude recorder/device connections |
| Weight mutation | Exact target selection, authority and idempotency context, finite bounds, mutation receipt, and replay behavior |
| Reward mapping | Explicit mapping from a named input channel to a declared modulation mechanism; ordinary rate/current input is not implicitly a reward |
| Learning loop | Installed provider and consumer, session/lease enforcement, bounded timing, retained traces, and scientific validation separate from protocol conformance |

A possible application can map a body outcome to a declared modulation input and
observe a declared plastic state after simulation steps. That is an application
design, not behavior supplied automatically by NCP. The body remains final actuator
authority, and learning output cannot bypass the plant profile, live session generation,
authority lease, or command safety gates.

## Scientific boundary

Plasticity traces are simulation or control artifacts. Keep
`is_simulation_output=true` and `calibrated_posterior=false` on wire-1.0
observations. Protocol success does not prove learning efficacy, biological
validity, posterior calibration, paper reproduction, or safe physical behavior.
