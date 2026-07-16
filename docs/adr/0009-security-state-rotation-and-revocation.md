# ADR-009 — Bind semantic security state, rotation, and revocation

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: security reviewer, operations reviewer, supply-chain
  reviewer

## Context

Hashing one configuration file or relying on a key ID does not identify the
complete public trust state that governs a session. Rotation, revocation,
manifest membership, audiences, algorithms, profiles, and ACLs can change after
discovery. Peers need a deterministic semantic identity and an explicit
transition rather than stale continuation.

## Proposed decision

The `security_state_digest` shall cover a canonical semantic projection of:

- named transport/authentication profile and exact profile version;
- enrolled principals, entities, roles, planes, literal route/class grants, and
  audiences;
- signing/certificate key fingerprints, fully specified algorithms, key epochs,
  validity intervals, and allowed uses;
- trust roots and authenticated manifest identities;
- revocation set digest and monotonically increasing revocation epoch;
- ACL/authority manifest digests;
- replay/recovery domain identities and clock policy;
- privacy/redaction policy identifiers relevant to attached observers; and
- the stable-core and accepted extension manifest identities to which the state
  applies.

Every session descriptor, stream declaration, authority lease, observer grant,
authenticated envelope, and receipt binds the exact security-state digest and
security epoch.

Rotation uses a bounded overlap:

1. publish and authenticate a new semantic state;
2. establish a new security epoch and exact overlap interval;
3. rebind or reattach sessions, streams, leases, and grants explicitly;
4. stop accepting the retired key/state at the declared boundary; and
5. retain a signed audit/revocation record.

Emergency revocation advances the revocation epoch, closes affected connections,
rejects retired keys immediately at the enforcement boundary, and forces explicit
recovery. Unknown or rolled-back state fails closed.

## Rejected alternatives

- Digest raw file bytes while ignoring semantic equivalence or included files.
- Accept a known `kid` without exact current manifest and key epoch.
- Continue a session across security-state change with only a warning.
- Allow key overlap without a finite end or accept retired epochs for replay.
- Fetch keys or trust state from message-supplied remote URLs.

## Illustrative semantic projection

```json
{
  "profile": "ncp-production-ingress-v1",
  "security_epoch": 12,
  "revocation_epoch": 4,
  "principals": [
    {
      "principal_id": "crebain-body-a",
      "role": "body",
      "planes": [
        "control",
        "action",
        "observation"
      ]
    }
  ],
  "key_epochs": [
    {
      "kid": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "algorithm": "Ed25519",
      "epoch": 3
    }
  ]
}
```

## Invalid or hostile example

```json
{
  "profile": "production-secure",
  "algorithm": "EdDSA",
  "kid": "current",
  "revocation_epoch": 0
}
```

Ambiguous algorithm, mutable key name, and missing semantic membership reject.

## Actors and state transitions

`CURRENT(epoch n) -> PREPARED(epoch n+1) -> OVERLAP(n,n+1) ->
CURRENT(n+1) -> RETIRED(n)`.

Emergency path:

`CURRENT -> REVOKING -> REVOKED -> RECOVERY_REQUIRED`.

No message can self-advance security or recovery epochs.

## Bounds and resource behavior

Principal, route, key, root, revocation, extension, digest-input, overlap,
connection-close, rebind, audit, and verification work are finite. Projection is
deterministic and duplicate-free before hashing.

## Threat and hazard analysis

This addresses key/algorithm confusion, manifest rollback, stale grants,
indefinite overlap, revoked-key continuation, and partial reconfiguration.
Emergency revocation can reduce availability and force HOLD; that operational
hazard must be tested. Key custody, CA compromise, trusted time, and signed
provenance remain external gates.

## Formal properties

- Equal semantic state produces equal digest in every implementation.
- A changed authorizing member changes the digest.
- A message under a retired security/revocation epoch is never accepted.
- Rebinding cannot widen a principal beyond the new manifest.
- An unknown state cannot preserve authority.

## Migration

N04 generates the projection and vectors; N06 integrates atomic rebind/revoke.
Consumers compare exact state and reattach rather than interpreting raw provider
configuration.

## Operational recovery

On state mismatch, corruption, or rollback, stop admission and enter the
plane-appropriate denial/HOLD posture. Restore only from an authenticated,
content-addressed state with a newer authorized recovery transition.

## Compatibility and rollback

Rollback to a previous security state requires an explicit new epoch and
authorization; it is not a numeric decrement or byte restore. Released security
history remains auditable even when deployment is prohibited.

## Open questions

Exact projection member encodings are N04 inputs. They may add non-authorizing
diagnostics but cannot omit any authority-bearing semantic member listed here.

## Ten-lens review

1. Semantics: state identity covers meaning, not one filename.
2. Security: algorithms, keys, routes, roles, audiences, and revocation bind.
3. Safety: trust uncertainty cannot preserve plant authority.
4. Lifecycle: overlap, retire, revoke, and recovery are explicit.
5. Resources: state and transition work are bounded.
6. Migration: portable vectors make independent equality testable.
7. Science: authenticity cannot validate scientific claims.
8. Operations: rotation and emergency procedures are executable.
9. Evidence: live planned rotation/revocation remains an external gate.
10. Governance: roots, manifests, keys, incidents, and retention have owners.

## Ratification record

No qualifying security, operations, or supply-chain review is recorded.
