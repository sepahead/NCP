# ADR-003 — Authenticate production ingress before interpretation

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: two independent security/cryptography reviewers,
  transport implementer

## Context

Pinned Zenoh `1.9.0` does not expose the verified certificate principal on each
stable application callback. Zenoh source IDs and payload `IdentityClaim` values
are sender-controlled metadata. Direct `production-secure` therefore correctly
fails closed.

B04 established local feasibility for a terminating TLS 1.3 ingress and for a
strict flattened-JWS forwarding envelope. It did not establish production
security, live rotation/revocation, key custody, containment, or external review.

## Proposed decision

Production input shall use one non-negotiable endpoint profile selected by trusted
configuration:

1. **A-direct:** a distinct terminating TLS 1.3 ingress derives the operation
   actor from the verified client leaf certificate and a content-addressed,
   default-deny manifest. The same process passes an unforgeable internal
   authenticated context with the same bounded payload bytes to NCP admission.
2. **B-over-A forwarding:** only where the original operation signer cannot
   remain the transport peer. A authenticates a carrier restricted to an exact
   forwarding grant; a strict flattened JWS authenticates a distinct operation
   signer. Both axes are mandatory and congruent.

Direct Zenoh `production-secure` remains unavailable until an exactly pinned API
exposes callback-visible verified principal evidence and passes fresh review.

The signed profile accepts exactly the fully specified JOSE algorithm
`Ed25519` registered by RFC 9864, never deprecated polymorphic `EdDSA`, `none`,
remote key URLs, embedded keys, unprotected headers, compact/general
serialization, detached payloads, or caller-selected algorithms. Protected
context binds exact route, plane, message class, profile, issuer, audience,
stable-core digest, security-state digest, key manifest and epoch, validity
interval, session generation, payload digest, and applicable stream or operation
replay context.

Authentication precedes semantic interpretation and never grants a session,
lease, lifecycle transition, operation outcome, disposition, or plant action.

## Rejected alternatives

- Trust payload identity, Zenoh source ID, connection topology, certificate common
  name, or router ACL inference at the application boundary.
- Enable production mode with a warning when actor binding is unavailable.
- Negotiate A-direct versus B-over-A from the received message.
- Let a carrier and signer share principal/entity identity.
- Invent custom signature framing instead of a strict reviewed JWS profile.
- Count B04's local prototypes as production evidence.

## Illustrative wire wrapper

The inner payload remains a generic NCP message. Proposed forwarding syntax:

```json
{
  "protected": "ZXhhY3QtYmFzZTY0dXJsLXByb3RlY3RlZA",
  "payload": "ZXhhY3QtYmFzZTY0dXJsLW5jcC1wYXlsb2Fk",
  "signature": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
}
```

The strings above are illustrative only and do not form a valid signature.

## Invalid or hostile example

```json
{
  "protected": "eyJhbGciOiJFZERTQSJ9",
  "payload": "e30",
  "signature": "",
  "header": {
    "jku": "https://attacker.invalid/keyset.json"
  }
}
```

This rejects before payload interpretation.

## Actors and state transitions

A-direct:

`LISTENING -> TLS_VERIFIED -> MANIFEST_BOUND -> FRAME_BOUNDED ->
AUTHENTICATED_CONTEXT -> NCP_ADMISSION`.

B-over-A adds:

`CARRIER_VERIFIED -> SIGNED_FRAME_BOUNDED -> SIGNER_MANIFEST_BOUND ->
SIGNATURE_VERIFIED -> REPLAY_COMMITTED -> CONGRUENCE_CHECKED -> NCP_ADMISSION`.

Any failure transitions to `REJECTED` with no authenticated context. Rotation or
revocation atomically retires affected mappings and connections.

## Bounds and resource behavior

TLS versions, frame bytes, JSON nodes/depth/members, protected bytes, payload
bytes, strings, integers, base64url, manifest entries, keys, replay scopes,
queues, diagnostics, verification time, and recovery work are finite. Bounds are
checked before expensive parsing, signature verification, allocation, logging,
or side effects.

## Threat and hazard analysis

The design addresses self-authentication, algorithm confusion, route/audience
substitution, carrier identity laundering, replay, stale keys, manifest rollback,
and partial-frame delivery. The ingress and key store remain trusted computing
base components. Memory corruption, host compromise, CA/key custody, trusted
time, multi-host replay consensus, and plant consequences of denial remain
external risks.

## Formal properties

- No payload field can construct an authenticated actor.
- Every admitted production message has exactly one configured profile.
- B-over-A admission implies distinct authorized carrier and signer identities.
- Route, plane, class, audience, and digests agree across transport, wrapper,
  manifest, and inner message.
- Replay commit occurs before handoff; uncertain durable state rejects.
- Authentication success alone cannot satisfy an authority predicate.

## Migration

No current shipping adapter changes in B01. N04 implements the accepted envelope
and N06 integrates it while preserving direct-Zenoh fail-closed behavior. All
bindings receive the same public corpus; live profiles remain unavailable until
external security gates pass.

## Operational recovery

Manifest ambiguity, state loss, rollback, key removal, clock uncertainty, or
replay-store corruption stops admission. Recovery is an authenticated
out-of-band owner operation with a distinct recovery epoch/store identity; an
in-band message cannot self-authorize it.

## Compatibility and rollback

Endpoints pin one exact profile; no fallback exists. Rollback restores the prior
disabled production path or a complete reviewed ingress release, never an
unauthenticated compatibility mode.

## Open questions

Independent reviewers must decide whether the in-process A-direct capability
boundary requires a process-isolated handoff in production. That deployment
choice may strengthen containment but cannot weaken the authenticated actor,
route, manifest, and exact-byte invariants.

## Ten-lens review

1. Semantics: profile and authenticated actor meanings are exact.
2. Security: verification precedes interpretation; downgrade is unavailable.
3. Safety: ingress grants no lease or plant success.
4. Lifecycle: rotation, revocation, restart, and replay recovery fail closed.
5. Resources: every encoding and verification layer is bounded.
6. Migration: all languages share exact vectors; direct Zenoh stays disabled.
7. Science: signatures authenticate provenance but do not validate claims.
8. Operations: configuration, alarms, key rotation, and recovery are explicit.
9. Evidence: independent crypto review and live rotation/revocation remain gates.
10. Governance: manifest, keys, ingress, incidents, and deprecation have owners.

## Ratification record

No qualifying independent security review is recorded. B04 is local feasibility
evidence only.
