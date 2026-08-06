# NCP over a degraded link

> **Candidate boundary:** the deterministic library primitives and corpus cases in
> this repository inform the unreleased, release-blocked NCP `1.0.0-rc.1`
> candidate. Combined live delay, loss, duplication, reordering, partition,
> restart, flood, fault, and soak qualification is **NOT RUN**. This document is not
> resilience, anti-jamming, or plant-safety certification.

This design was reviewed against control-over-networks, predictive-control,
freshness, erasure-coding, and information-decomposition concepts. Those bodies of
work provide design questions, not universal thresholds for an unknown plant. NCP
implements only the bounded mechanisms identified below.

## Current implementation and design targets

| Surface | Candidate implementation | Boundary |
|---|---|---|
| Command deadline | `CommandWatchdog` enforces receiver-local TTL and fails closed on invalid time | Each actuator-owning consumer must wire it into the final actuation path |
| Predictive replay | `ActionBuffer` replays a validated `CommandFrame` horizon until it drains or expires | A producer is not supplied; no current Engram/NEST horizon producer is claimed |
| Link telemetry | `LinkMonitor` computes sequence-gap loss and a CUSUM burst indication | It has no clock-based silence detector and does not identify the cause of loss |
| Plant policy | Successful standalone `SafetyGovernor` calls emit normalized, bounded Active, HOLD, or ESTOP wire-shape candidates; an admitted ESTOP, a geofence breach, sustained sensor silence, or `note_link(true)` latches ESTOP | An unattributable stream/session envelope or an unrepresentable bounded safe output latches local ESTOP and returns an error without a wire frame; the governor owns no stream-position allocator or high-water mark, and normalized `seq=1` is not freshness evidence; the owning publisher must supply the next fresh position and perform exact-route and live-generation admission; the governor does not load or execute a plant profile; arrival-probability and goodput gates are not implemented |
| Channel prioritization | Design candidate only | No PID-derived online policy or installed analysis loop exists |
| Duplication or FEC | Deployment study only | NCP ships no duplication controller or erasure/streaming-code module |

## Per-plane failure model

- **Perception plane:** `SensorFrame` uses best-effort DROP. The typed adapter has a
  bounded replace-latest receive slot after transport receipt. A missing sample can
  be tolerated only while the consumer's plant-specific freshness policy remains
  satisfied.
- **Action plane:** `CommandFrame` uses express, DROP, and RealTime priority. A
  command can actuate only while its receiver-local deadline and all identity,
  session, lease, route, stream, plant, and safety gates pass. A conformant plant
  must enter its declared HOLD behavior when the command expires.
- **Control plane:** lifecycle RPC uses reliable/blocking transport behavior. It is
  separate from the deadline-sensitive action path.

Transport delivery does not prove plant receipt or physical action. A successful
put and a local library decision are not actuator acknowledgements. Wire-1.0
`ResponderReceipt` applies to lifecycle step, run, and close operations. A
`CommandFrame` has no operation context, idempotency context, or applied-command
receipt. A deployment can define a body-local actuator receipt, but that receipt is
deployment-local and is not an NCP wire receipt.

## Receiver-local TTL is the backstop

`CommandWatchdog` measures freshness with the plant receiver's monotonic clock. It
refreshes only for a strictly advancing positive sequence. The caller must scope
one watchdog instance to one declared stream epoch; `ActionBuffer` enforces that
epoch binding. Timeout does not reopen a lower sequence. A foreign epoch requires
a fresh declaration, session context, and watchdog instance.

The watchdog treats a non-finite clock or TTL as expired and clamps finite TTL to
`MAX_TTL_MS` (60 seconds). After a clock rewind or non-finite sample, the prior
command stays unusable until the local clock catches up and a new, strictly
advancing command is accepted. Catch-up alone does not revive a stale command. The
watchdog does not revoke or mutate an authority lease.

NCP cannot install this control in hardware that it does not own. The body remains
final actuator authority and must map HOLD to the exact content-addressed plant
profile. No universal zero-safe action exists.

## Predictive horizon: exact timing and bound

`CommandFrame.channels` is tick 0. Zero-based `horizon[i]` is scheduled at receiver
time

```text
received_at + (i + 1) * horizon_dt_ms
```

The watchdog expires inclusively when elapsed time reaches the locally enforced
TTL. Define the calculation as follows for finite `ttl_ms` and finite
`horizon_dt_ms > 0`:

```text
effective_ttl_ms = clamp(ttl_ms, 0, MAX_TTL_MS)
ratio = effective_ttl_ms / horizon_dt_ms
N_max = 0                                             if ratio is non-finite
N_max = min(MAX_HORIZON_STEPS, max(ceil(ratio) - 1, 0)) otherwise
```

`MAX_HORIZON_STEPS` is 65,536. Invalid inputs and a non-finite binary64 ratio permit
zero future steps. A step at the effective TTL boundary is not executable. For
example, `ttl_ms=200` and `horizon_dt_ms=50` permit three future steps, scheduled at
50, 100, and 150 ms. The 200 ms step is expired.

Rust `CommandFrame` validation rejects a horizon longer than this bound. Both Rust
and TypeScript `ActionBuffer` watchdogs clamp the executable window to 60 seconds.
The TypeScript `maxHorizonLen` helper also calculates the clamped bound. However,
the generic TypeScript `assertNcpMessage` path currently uses uncapped `ttl_ms`.
For `ttl_ms > 60_000`, it can accept steps that the watchdog cannot execute. It can
also accept a nonempty horizon when a tiny positive cadence makes the ratio
non-finite. N07 must correct the implementation and add the exact cross-language
corpus cases through the dependency-gated proto, identity, and rebaseline workflow.
Do not use generic TypeScript validation alone as evidence of horizon parity.

`ActionBuffer` returns tick 0 before the first future step, then `horizon[i]` at its
scheduled tick. It returns no setpoint after the horizon drains or the watchdog
expires. A non-`active` frame clears buffered actuation; ESTOP also latches. Reset
retires that buffer's complete session context, so a fresh generation needs a fresh
object.

Predictive replay is open-loop action. It can bridge a bounded dropout, but a model
error or disturbance can make the prediction wrong. The producer and plant must
choose the cadence and horizon from a measured closed-loop profile. Protocol tests
do not prove that any nonzero horizon is safe for a specific plant.

## Plant-side governor and admission

The reference `SafetyGovernor` can clamp the canonical velocity path and project it
over the TTL/horizon window. Invalid configuration, stale or malformed sensor data,
an absent required channel, non-finite values, or a projected geofence crossing
fail closed. An actual geofence breach or `note_link(true)` latches ESTOP.

For a finite, positive configured timeout `T`, sensor data becomes stale after
`min(T, 60 s)`. The sustained-silence ESTOP deadline is
`min(20 × min(T, 60 s), 60 s)` after the last finite sensor timestamp. An invalid
or non-positive timeout sets configuration fail-closed. With a canonical
attributable stream/session envelope and a representable bounded safe frame, that
invalid timeout makes a non-ESTOP input return HOLD without applying the silence
formula. An existing or inbound ESTOP latch remains dominant. This syntax check is
not exact-route or live-generation admission. This is a receiver-local
sensor-freshness rule. It does not identify link failure or jamming.

The governor does not authenticate the sender, create a session, issue an authority
lease, load a plant profile, execute an actuator action, issue a receipt, or prove
physical effect. On success, it returns a normalized, bounded wire-shape candidate
in Active, HOLD, or ESTOP mode. It owns no publisher position allocator or
high-water mark. A normalized `seq=1` satisfies local wire shape only. It does not
establish freshness and must not enter an existing declared stream. The owning
publisher must assign and admit the next fresh position. An unattributable
stream/session envelope or an inability to construct a bounded safe output latches
local ESTOP and returns an error, not a wire frame. Deployment actuation still
requires the verified transport principal, default-deny manifest, exact route and
plane, live session generation, matching bounded lease, admitted command, and
content-addressed plant profile.

An installed body-owned executor must map each successfully returned HOLD or ESTOP
frame to the action declared by that plant profile. The mapped action does not
necessarily de-energize a device.
`SafetyGovernor::reset()` is a body-local primitive, not a stable wire RPC or an
authority transition. A deployment-level reset must retire the old generation,
authority, lease, and stream state before it constructs fresh admission state.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/fsm-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/diagrams/fsm-light.svg">
  <img alt="Informative NCP plant-admission model for the UNRELEASED, release-blocked 1.0.0-rc.1 candidate; not a release or physical-safety certification. A canonical attributable stream/session envelope can produce a normalized, bounded wire-shape candidate. The standalone governor owns no publisher allocator or high-water mark; normalized sequence 1 is not freshness evidence. The owning publisher separately assigns and admits the next fresh position, exact route, and live generation. An unattributable envelope or the absence of any representable bounded safe-frame tier latches local ESTOP and returns an error without a wire frame. The body maps successful HOLD or ESTOP output through the exact plant profile. Reset retires the generation; fresh session, streams, authority, command, and plant gates are required before ACTIVE. NCP defines no universal zero-safe action." src="docs/diagrams/fsm-light.svg" width="820">
</picture>

## Link telemetry: detection is not causation

`LinkMonitor` observes accepted stream sequence positions. It estimates missing
positions over the observed span, reconciles bounded reordering, and applies a
CUSUM change detector. It emits `LinkStatus`; it never actuates.

The detector sees arriving frames only. It has no `max_silence_ms` field, heartbeat,
or clock input, so it cannot distinguish "no change" from a link that went silent
after the last frame. The reference governor has a separate derived timer for
sensor freshness. A deployment that needs an independent link-silence policy must
implement and validate it locally. Adding a stable wire field would be a separate
wire-visible change.

A CUSUM burst is compatible with congestion, routing failure, interference, sender
failure, or jamming. It is not proof of an attacker. The current
LinkMonitor-to-governor trip is only the boolean `burst` signal passed to
`note_link`; the separate governor silence rule derives from sensor freshness.
Plant-specific arrival-probability, goodput, or estimator-feasibility thresholds
remain design targets and must not be described as current runtime gates.

## Channel prioritization is an offline design candidate

Partial Information Decomposition can help an analyst ask which sources contribute
unique, redundant, or synergistic information about a declared target. The result
depends on the estimator, data, target, operating regime, and chosen decomposition.
It does not establish that a channel is safe to drop.

NCP currently has no PID computation or policy-feedback path. A future workflow
could compute candidate priorities from a read-only observation dataset, then
validate a static policy offline and under closed-loop fault tests before a codec
uses it. The policy remains non-normative and cannot grant identity, authority,
capability, or plant action.

## Duplication and coding require a deployment study

NCP ships no Reed-Solomon, RLNC, RaptorQ, or streaming-FEC module. It also does not
prove that coding is unnecessary. Independent-path duplication, small systematic
codes, selective protection, retransmission, or predictive replay can have different
latency and correlated-failure behavior. Select only from measurements for the
exact payload, deadline, topology, outage distribution, and plant.

No application-layer technique recovers data when delivered goodput remains near
zero beyond the validated replay window. Radio-layer anti-jamming mechanisms are
outside NCP. The plant must enter its declared fail-safe behavior when application
freshness or authority expires.

## Consumer integration order

1. Bind the payload identity to the verified transport principal, default-deny
   manifest, route, plane, and live session generation.
2. Validate the complete `CommandFrame`, authority lease, stream epoch/position,
   negotiated channel contract, and plant profile. Do not attach lifecycle
   operation or idempotency context to the action frame.
3. Apply `CommandWatchdog` in the final actuator-owning loop.
4. Use `ActionBuffer` only for a measured and validated predictive horizon.
5. Feed `LinkMonitor` telemetry into an explicit plant policy. If the policy uses
   the current governor hook, document that only `burst=true` causes the latch.
6. Validate operation context, idempotency, and `ResponderReceipt` separately for
   lifecycle step, run, and close RPCs.
7. Map HOLD and ESTOP through the exact plant profile. Label any applied-command or
   body-boundary receipt as deployment-local. Do not infer physical action from
   transport success.
8. Run live fault, delay/loss/reordering, restart, duration, and soak campaigns on
   the installed consumer before making a resilience claim.

A read-only observer can consume telemetry but must not call actuator primitives.
None of these steps supplies a stability certificate, hardware ESTOP certification,
paper reproduction, posterior calibration, or release authorization.
