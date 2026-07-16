# ADR-001 — Separate simulation-service and plant-control sessions

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: NCP maintainer, Engram owner, Crebain body owner,
  independent protocol reviewer

## Context

The current `OpenSession` contract is a neural-simulation request: it carries an
Engram network reference, recording and stimulus specifications, simulation
configuration, and returns `SimProvenance`. Ecosystem prose also needs NCP to open
plant-control sessions with a Crebain body. A physical or simulated plant does
not resolve Engram network, recording, or stimulus fields, and simulation
resource authority is not plant action authority.

Overloading the existing request would make default values, feature combinations,
or consumer-specific interpretation choose safety-relevant semantics.

## Proposed decision

The next deliberately rebaselined candidate shall define three disjoint session
entry paths:

1. `OpenSimulationSession` / `SimulationSessionOpened` for a bounded simulation
   service;
2. `OpenPlantSession` / `PlantSessionOpened` for a bounded plant-control session;
3. `AttachObserver` / `ObserverAttached` for read-only access to an already-live
   session, as refined by ADR-004.

The two opening requests may reuse common value types for identity, security,
contract identity, session reference, idempotency, and receipts. They shall not
share one message kind with optional type-specific fields.

A simulation session:

- requires simulation configuration and returns mandatory
  `SimProvenance` with `is_simulation_output=true` and
  `calibrated_posterior=false`;
- grants only bounded simulation-operation authority issued by the simulation
  responder;
- has no plant profile, action authority lease, actuator route, or plant
  disposition meaning.

A plant session:

- requires the exact content-addressed plant profile, channel and rate
  negotiation, body identity, security state, and lifecycle contract;
- opens initially without action authority;
- obtains action authority only through a separate body-issued operation under
  ADR-006.

An artifact that implements both Engram roles shall use disjoint types,
principals, key material, manifests, routes, endpoints, state stores, replay
domains, and build features. Responder-only artifacts shall not link command
publication code.

`SimProvenance` is integrity-protected provenance, not an admission credential.
A legitimate plant commander may use simulation output as advisory input under
its own policy, but any resulting NCP command is a new command under the
commander's plant principal and current Crebain lease. No simulation receipt,
principal, route, or store can be converted into plant authority.

## Rejected alternatives

- One generic `OpenSession` with a `session_type` enum and optional union-like
  fields: rejected because missing/default/unknown fields could choose semantics
  and independent implementations could accept contradictory combinations.
- Treating Crebain as a simulation backend: rejected because it collapses plant
  safety and neural-simulation meanings.
- Adding Engram-specific fields to plant messages: rejected because NCP remains
  project-neutral.
- Adding a new wire-wide `world=SIM|PLANT` field to every record: rejected as
  unnecessary if session kinds, credentials, routes, and authority domains are
  disjoint. Deployment isolation remains mandatory and separately evidenced.

## Illustrative wire example

This is proposed syntax, not current candidate wire:

```json
{
  "ncp_version": "1.0",
  "kind": "open_plant_session",
  "session_id": "plant-alpha",
  "plant_profile_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "stable_core_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "security_state_digest": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "commander_identity": {
    "principal_id": "engram-commander-a",
    "entity_id": "controller-a",
    "role": "commander",
    "plane": "control"
  }
}
```

## Invalid or hostile example

```json
{
  "ncp_version": "1.0",
  "kind": "open_plant_session",
  "session_id": "plant-alpha",
  "network": {
    "id": "engram-network"
  },
  "sim": {
    "mode": "batch"
  }
}
```

The plant request rejects simulation-only members and cannot infer the missing
plant profile or security contract.

## Actors and state transitions

Simulation:

`CLOSED -> OPENING_SIMULATION -> INIT_SIMULATION -> ACTIVE_SIMULATION -> CLOSING -> CLOSED`.

Plant:

`CLOSED -> OPENING_PLANT -> INIT/HOLD -> ACTIVE_WITH_BODY_LEASE -> HOLD/ESTOP -> CLOSING -> CLOSED`.

No transition crosses from one session kind to the other. Reuse of a logical
`session_id` creates a fresh server-issued `SessionRef.generation`; generations
are opaque UUIDv4 equality fences and are never ordered.

## Bounds and resource behavior

Each request has an exact byte, member, string, collection, channel, extension,
and allocation bound before semantic allocation. Simulation network/stimulus
bounds and plant channel/profile bounds are separate. Enabling both roles does
not merge their quotas or permit one role to starve the other's safety path.

## Threat and hazard analysis

This decision reduces type confusion, credential reuse, route confusion,
simulation-to-plant authority laundering, state-store replay, and accidental
actuator code inclusion. It does not prove simulation validity, plant safety,
physical response, or secure key custody. A compromised legitimate plant
commander remains capable of proposing harmful commands subject to plant-local
admission and safety enforcement.

## Formal properties

- A message kind belongs to exactly one session kind.
- A simulation grant never satisfies a plant authority predicate.
- A responder-only build has no reachable plant command publisher.
- No accepted plant transition depends on a neural-network field.
- No accepted simulation transition depends on a plant lease or plant profile.

A bounded model shall include unknown kinds, cross-kind frame injection, same
logical session ID with distinct generations, restart, and dual-role deployment.

## Migration

The immutable wire-0.8 history remains unchanged. The current overloaded
candidate request becomes unsupported development input after explicit B02
rebaseline authorization. Engram migrates its responder and commander adapters
separately. Crebain implements only plant-control types. Gateways terminate trust,
label source and target identity, and reject ambiguous mappings.

## Operational recovery

Restart restores only the matching typed state store. If state kind, generation,
contract identity, or security state is uncertain, retire the incarnation and
open a fresh generation. A recovered simulation service cannot restore a plant
lease; a recovered plant session cannot infer simulation state.

## Compatibility and rollback

This is a pre-release breaking correction and requires a new candidate identity
after B02 authorization. Rollback is to the last pushed release-blocked candidate
and its consumer pins, never to a mixed message contract. Released `v0.8.0`
artifacts remain immutable.

## Open questions

No open question may change the separation decision. Exact common-envelope field
factoring and package names are implementation details for N01/N02 and must
preserve disjoint message kinds and authority domains.

## Ten-lens review

1. Semantics: one kind has one session meaning.
2. Security: credentials and routes are non-fungible across kinds.
3. Safety: only the plant body grants action; protocol success is not physical
   safety.
4. Lifecycle: cross-kind transition and implicit recovery are impossible.
5. Resources: simulation and plant budgets remain independently finite.
6. Migration: 0.8 and the old RC terminate explicitly.
7. Science: simulation output remains uncalibrated, advisory, and labelled.
8. Operations: dual-role deployments expose separate endpoints and diagnostics.
9. Evidence: cross-kind negative vectors and independent live roles are required.
10. Governance: NCP owns generic session types; consumers own optional adapters.

## Ratification record

No qualifying review is recorded. Model advice is non-evidence. Any edit changes
the registry digest and invalidates earlier review.
