# ADR-002 — Separate contract identity and release authorization

- Status: `PROPOSED`
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect while proposed: none
- Required reviewers: protocol reviewer, release and supply-chain reviewer

## Context

The current compact 16-hex proto hash is intentionally advisory and does not
cover schemas, registries, behavior vectors, or other normative semantics.
Matching `ncp_version="1.0"` therefore cannot prove that two peers implement the
same stable core. Conversely, a complete repository digest and a release
authorization answer different questions and must not be overloaded as a wire
compatibility key.

The draft decision registry also cannot enter `contract/` while proposed because
the current manifest glob would make it normative immediately.

## Proposed decision

NCP shall maintain separate content identities:

| Identity | Meaning | Decision use |
|---|---|---|
| `wire_version` | major protocol family | exact supported value; no generic same-major optimism |
| `stable_core_digest` | all required wire semantics and mandatory behavior | exact equality before a native session opens |
| `release_digest` | exact complete normative release source set | artifact/document identity and audit |
| `corpus_digest` | mandatory canonical and behavior vectors | conformance subject identity |
| `extension_manifest_digest` | one optional/required extension contract | exact per-extension negotiation |
| compact proto hash | short diagnostic projection | never sufficient for compatibility or release |
| release authorization record | owner/publisher approval of exact subjects | external publication gate, never a payload grant |

The stable-core membership is generated from reviewed source inputs and becomes
immutable for the released major. Optional extension bytes are excluded from the
stable-core digest and identified independently. Unknown required extensions
reject; unknown optional extensions are explicitly declined.

The draft registry remains outside `contract/`. Mechanical promotion is blocked
until all ADRs are accepted at exact hashes and B02 authorizes the rebaseline.
The accepted `contract/decision-registry.v1.json` becomes part of the complete
release digest only in that same reviewed promotion slice.

A release authorization record binds exact source commit, tree, stable-core
digest, release digest, corpus digest, package subjects, signatures, and gate
receipts. It cannot be inferred from a green local build, a Git tag name, a
manifest edit, or a matching version string.

## Rejected alternatives

- Keep the compact proto hash as the hard identity: incomplete and collision
  inappropriate for the complete contract.
- Treat any `1.x` peer as compatible: permits semantic drift under the same
  authority-bearing wire family.
- Put every extension into the stable core: prevents optional evolution and
  creates consumer-specific forks.
- Let a proposed registry enter `contract/` with `"status":"PROPOSED"`: the path
  is already normative under the current generator.
- Treat release authorization as a wire field: a peer cannot self-certify a
  package or publication.

## Illustrative wire example

```json
{
  "wire_version": "1.0",
  "stable_core_digest": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
  "release_digest": "sha256:2222222222222222222222222222222222222222222222222222222222222222",
  "corpus_digest": "sha256:3333333333333333333333333333333333333333333333333333333333333333",
  "extensions": [
    {
      "id": "org.sepahead.galadriel.observation",
      "manifest_digest": "sha256:4444444444444444444444444444444444444444444444444444444444444444",
      "required": false
    }
  ]
}
```

## Invalid or hostile example

```json
{
  "wire_version": "1.0",
  "contract_hash": "163acc57d8a62b66",
  "stable_core_digest": null
}
```

Native session opening rejects a missing or mismatched stable-core digest even
when the wire version and compact diagnostic hash match.

## Actors and state transitions

`DRAFT -> PROPOSED -> REVIEWED_SAME_DIGEST -> ACCEPTED -> REBASELINE_AUTHORIZED
-> CANDIDATE_FROZEN -> EXTERNALLY_AUTHORIZED -> PUBLISHED`.

No later state can be inferred from an earlier state. An ADR edit returns that
ADR to `PROPOSED`. A stable-core byte change after candidate freeze creates a new
candidate identity. A released core is immutable; security prohibition is
published as a separate revocation/deprecation record.

## Bounds and resource behavior

Digests use fixed algorithms and lengths. Source-path sets, path lengths, file
counts, file sizes, extension counts, and manifest sizes are bounded. Digest
construction is domain-separated and length-prefixed. No remote URL or payload
selects the hash algorithm.

## Threat and hazard analysis

This decision prevents same-version semantic substitution, optional-extension
confusion, RC label reuse, corpus mismatch, optimistic publication, and a copied
manifest being mistaken for installed compatibility. It does not attest source
custody, builder integrity, signatures, or independent reproduction; those
remain external gates.

## Formal properties

- Equal stable-core digests imply byte-equal generated membership under the
  specified digest construction.
- A stable-core mismatch cannot reach session state.
- An extension digest cannot satisfy the stable-core field.
- No local evidence state implies external release authorization.
- A proposed ADR hash cannot appear in the accepted registry.

## Migration

The current compact hash remains visible only as a labelled diagnostic until the
rebaseline. The next candidate introduces the hard stable-core identity and
updates all peer types, fixtures, schemas, generated bindings, and consumers
together. Historical 0.8 identities remain frozen.

## Operational recovery

Digest mismatch is non-retryable without changing one endpoint or using an
explicit terminating gateway. Missing authorization blocks publication without
changing runtime behavior. Registry or digest-generation corruption fails the
build and restores from the last verified source commit.

## Compatibility and rollback

Rollback uses a complete exact candidate cut and its pins. Individual identity
fields cannot be cherry-picked into an older contract. Published releases retain
their original digest and corpus identities indefinitely.

## Open questions

The exact stable-core file membership must be enumerated by N01 after acceptance;
the decision that compatibility uses exact generated membership is closed.

## Ten-lens review

1. Semantics: every identity has one purpose.
2. Security: substitution and downgrade fail closed.
3. Safety: compatibility cannot be inferred for authority-bearing behavior.
4. Lifecycle: draft, freeze, authorization, and publication are distinct states.
5. Resources: digest inputs and algorithms are bounded and fixed.
6. Migration: gateways terminate incompatible wires explicitly.
7. Science: corpus identity cannot create calibration or reproduction claims.
8. Operations: mismatch diagnostics name the exact identity that failed.
9. Evidence: authorization binds exact subjects and independent receipts.
10. Governance: release and extension ownership are explicit.

## Ratification record

No qualifying review or owner rebaseline authorization is recorded.
