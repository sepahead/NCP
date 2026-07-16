# ADR-008 — Separate stable routes from Galadriel extensions

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: protocol reviewer, Galadriel owner, Crebain owner

## Context

Project-owned Galadriel sidecar payloads currently appear on routes that look like
stable NCP perception routes even though their envelope is not a normative NCP
message and lacks the native session contract. This creates route/type/security
confusion. Galadriel also needs a separate optional assessment path to Haldir
without turning the observer into a control principal.

## Proposed decision

Stable NCP routes accept only stable NCP message kinds. Optional project payloads
use a registered extension namespace:

```text
{realm}/extension/{extension_id}/{manifest_digest}/{deployment_or_session}/...
```

Each extension has a content-addressed manifest that binds owner, schema digests,
literal route templates, producer/consumer roles, security profile, stable-core
compatibility, bounds, QoS, retention, privacy, and deprecation policy.

Galadriel uses two distinct optional surfaces:

1. a read-only NCP observer under ADR-004 for standard NCP observations and
   dispositions; and
2. separately credentialed extension producers/consumers for Galadriel-owned
   evidence.

The Galadriel-to-Haldir assessment extension is default-off, push-only, and has
the closed effects `RECORD_ONLY` and `DENY_TIGHTEN`. It cannot encode `ALLOW`,
commands, leases, dispositions, lifecycle operations, or ESTOP. Haldir combines
it with local policy by meet: assessment may preserve or remove permission,
never create it.

Observer and assessor credentials, principals, key roots, processes, manifests,
routes, replay state, and queues are disjoint. Core wildcard subscriptions do not
match extension routes.

Crebain may publish standard NCP frames and Galadriel extension data through
separate declarations and bounded non-blocking queues. Extension absence,
slowness, or overload never blocks control, action, watchdog, or dispositions.

## Rejected alternatives

- Carry non-NCP bytes on a stable NCP route.
- Add Galadriel-specific scientific fields or kinds to the stable core.
- Reuse observer credentials for assessment.
- Allow assessment pull/callbacks inside the authorization critical section.
- Treat Galadriel as completely control-neutral when deny-tightening is enabled;
  it has a bounded negative control consequence and must be described honestly.

## Illustrative extension envelope

```json
{
  "extension_id": "org.sepahead.galadriel.assessment",
  "manifest_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "schema_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "producer_principal_id": "galadriel-assessor-a",
  "audience_principal_id": "haldir-assessment-receiver-a",
  "session_generation": "00000000-0000-4000-8000-0000000000a2",
  "assessment_sequence": 18,
  "effect": "DENY_TIGHTEN",
  "expires_at_utc_ms": 1784200030000
}
```

## Invalid or hostile example

```json
{
  "extension_id": "org.sepahead.galadriel.assessment",
  "producer_principal_id": "galadriel-observer-a",
  "effect": "ALLOW",
  "command": {
    "mode": "active"
  }
}
```

This fails schema, principal-role, and semantic validation.

## Actors and state transitions

Extension:

`UNREGISTERED -> REGISTERED_DISABLED -> ENABLED -> ROTATING/REVOKED ->
DISABLED`.

Assessment:

`ABSENT -> RECEIVED -> VERIFIED -> RECORDED/APPLIED_DENY -> EXPIRED/RETRACTED`.

Per-message meet-only semantics are insufficient across lifecycle changes.
Permission widening caused by deny retraction, expiry, assessment-mode disable,
base-policy widening, or restart reconstruction requires an explicit
authenticated, monotonically versioned Haldir policy/widening transition and an
audit record. A restart that cannot restore applied deny state follows the
declared absence policy and cannot silently erase a deny into a new ALLOW.

## Bounds and resource behavior

Manifest bytes, schema bytes, payload bytes, extension count, sequences, TTL,
queue depth, CPU budget, log volume, and retained gaps are finite. Control/action
capacity is reserved independently. Unknown extension bytes are rejected before
semantic allocation.

## Threat and hazard analysis

This prevents route confusion, credential reuse, observer actuation, extension
starvation of control, stale/replayed deny evidence, and lifecycle widening.
Deny-only advice can still reduce availability or create denial of service;
operators must see that consequence and may configure record-only or
deny-new-missions absence policy without creating permission.

## Formal properties

- Stable core routes never accept extension envelopes and vice versa.
- Assessment effect is never greater than local Haldir permission.
- Observer credentials cannot authenticate assessment traffic.
- No assessment transition directly creates an NCP command or body authority.
- Observer/extension overload cannot delay plant fail-safe paths.
- Effective permission never widens without an authenticated Haldir transition.

## Migration

Galadriel owns extension schemas and adapter packages. Crebain moves sidecar
publication to the registered route or emits a valid standard NCP frame via a
narrow adapter. Existing mixed-route traffic is rejected by native 1.0.

## Operational recovery

On manifest, replay-state, or deny-state uncertainty, reject new assessments and
apply the configured non-widening absence posture. Applied state is restored from
durable Haldir records or missions remain denied/preserved until an authenticated
transition resolves it. Gaps and drops are counted.

## Compatibility and rollback

Extensions are optional and separately versioned. Disabling an extension does
not alter stable-core compatibility, but it also cannot silently retract applied
deny state. Rollback restores an earlier exact extension manifest and explicit
policy revision.

## Open questions

Namespace ownership and exact schema IDs are B03 inputs. The disjoint route,
credential, effect, and non-widening rules are closed.

## Ten-lens review

1. Semantics: stable and extension payloads have disjoint meanings.
2. Security: owner, route, schema, audience, and credentials bind exactly.
3. Safety: advice cannot grant or actuate; denial consequences remain visible.
4. Lifecycle: enable, expiry, restart, retract, and widening are explicit.
5. Resources: extension work cannot starve control.
6. Migration: registered manifests enable independent agreement.
7. Science: advisory output remains non-calibrating and provenance-labelled.
8. Operations: gaps, drops, absence policy, and key rotation are observable.
9. Evidence: confusion, replay, monotonicity, load, and live freshness tests run.
10. Governance: Galadriel owns schema/namespace; Haldir owns final local policy.

## Ratification record

No qualifying protocol, Galadriel, or Crebain review is recorded.
