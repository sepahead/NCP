# ADR-002 — Separate contract identity and release authorization

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
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

The earlier draft registry could not retain a review or derive `ACCEPTED`. B01
required accepted same-digest reviews, but B02 owned the later rebaseline
authorization and depended on B01. That evidence-state cycle made truthful B01
closure impossible without changing the checker or bypassing a required gate.

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

`ContractIdentity` is deliberately realm-independent. The same exact protocol
artifact can serve more than one authority realm without changing its
stable-core, release, corpus, or extension-contract digest. Runtime use is
different. ADR-001 `AuthorityRealmKey` is the canonical tuple of server
authority principal and stable realm ID. It excludes rotating security epochs,
registry incarnations, transaction-store incarnations, and every session
generation.

Every realm-scoped negotiation request, response, acceptance, session descriptor,
session-open result, transcript, transcript receipt, and deployed conformance or
qualification receipt shall carry `authority_realm_key: AuthorityRealmKey` as a
direct canonical member. Its canonical bytes and digest include that typed
member. The value cannot be inferred from a route string, endpoint, certificate,
manifest name, session ID, generation, parent record, or local configuration.
Negotiation resolves the key from authenticated server authority before it
creates session state. Each peer then requires exact equality across the
authenticated ingress context, request, response, selected audience, descriptor,
and transcript.

The negotiation transcript binds both the realm-independent `ContractIdentity`
and the resolved `AuthorityRealmKey`. This does not make the realm a member of
the stable core. It makes one deployment of that stable core non-replayable into
another realm. A projection may omit the realm only when its schema is explicitly
realm-independent, such as a stable-core membership or release-artifact identity.
A projection of realm-scoped evidence that omits or changes the realm rejects.

Portable consumer state and evidence use the exact foreign key
`(AuthorityRealmKey, session_kind, logical_session_id, generation)`. Equal
principal, session kind, textual session ID, generation, contract identity, and
payload bytes under different realm keys are distinct facts. They cannot merge,
deduplicate, resume, inherit policy, or satisfy one another's receipt chain.
The tuple has one canonical representation in a realm-scoped object:
`authority_realm_key` is its direct first member, followed by the three session
coordinates. A second copied realm value is not another source of truth; if a
schema carries one for compatibility, exact equality is mandatory and any
disagreement rejects.

The draft registry remains outside `contract/`. It computes one domain-separated
decision-set digest from exact ADR bytes, structured role obligations, defect
mappings, and review-policy identity. The policy identity contains its version
and the exact generator and output-schema hashes and byte lengths. A policy
change therefore invalidates earlier reviews instead of silently weakening
acceptance.

Review records bind the decision-set digest, exact ADR digest and byte length,
source commit and tree, current review-packet digest, and content-addressed
evidence. The generator resolves the commit as a real Git commit and checks its
tree and ADR blob. The registry derives `PROPOSED` or non-normative `ACCEPTED`.
No source status string can authorize acceptance.

The review packet has no self-hash. Before capture starts, one machine-readable
`CURRENT` block binds the exact decision set, policy, Git source, claim boundary,
promotion block, and complete ADR role inventory. External requests and review
records content-address the immutable packet bytes. A superseded, template,
missing, duplicate, or mismatched block cannot support a review record.

An ADR edit makes an earlier review stale. Explicit supersession preserves review
history without counting an old record. An active rejection or unresolved
condition blocks acceptance. A conditional acceptance counts only after the same
reviewer closes each condition against the same subject and exact retained
evidence.

The structural checks validate hashes, bounds, Git objects, role coverage, and
review-chain rules. A role that requires independence needs both an explicit
claim and a separate retained content-addressed assessment. These checks still
do not prove external authorship, role authority, or independence. B01 therefore
retains the exact external receipts and separate independence evidence.

B02 separately authorizes the deliberate rebaseline. B03 owns the bounded
registry allocations. N01 alone can verify those predecessors, write the accepted
`contract/decision-registry.v1.json`, and regenerate the complete contract
identity. A non-normative `ACCEPTED` status never removes the promotion block.

A release authorization record binds exact source commit, tree, stable-core
digest, release digest, corpus digest, package subjects, signatures, and gate
receipts. It cannot be inferred from a green local build, a Git tag name, a
manifest edit, or a matching version string.

The release-authorization record is a realm-independent publication decision.
It does not acquire a synthetic realm field. If its evidence set contains a
deployed, session-scoped receipt, that receipt retains its direct
`AuthorityRealmKey`; the bundle cannot strip, rewrite, or aggregate that field.

## Rejected alternatives

- Keep the compact proto hash as the hard identity: incomplete and collision
  inappropriate for the complete contract.
- Treat any `1.x` peer as compatible: permits semantic drift under the same
  authority-bearing wire family.
- Put every extension into the stable core: prevents optional evolution and
  creates consumer-specific forks.
- Let a proposed registry enter `contract/` with `"status":"PROPOSED"`: the path
  is already normative under the current generator.
- Store only manual status strings or generic reviewer counts: this permits an
  optimistic pass and cannot invalidate a stale same-digest review.
- Make B01 wait for its B02 descendant: this creates an uncloseable evidence and
  authorization cycle.
- Treat release authorization as a wire field: a peer cannot self-authorize a
  package or publication.

## Illustrative wire example

This is a realm-bound negotiation envelope. The `ContractIdentity` values inside
it remain realm-independent.

```json
{
  "authority_realm_key": {
    "server_authority_principal_id": "ncp-authority-a",
    "stable_realm_id": "realm-a"
  },
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

Native session opening rejects a missing or mismatched stable-core digest or
`AuthorityRealmKey`, even when the wire version and compact diagnostic hash
match.

## Actors and state transitions

`DRAFT -> PROPOSED -> REVIEWED_SAME_DIGEST -> ACCEPTED_NON_NORMATIVE ->
REBASELINE_AUTHORIZED -> ALLOCATED -> NORMATIVE_PROMOTION ->
CANDIDATE_FROZEN -> EXTERNALLY_AUTHORIZED -> PUBLISHED`.

No later state can be inferred from an earlier state. An ADR edit returns that
ADR to `PROPOSED`. A stable-core byte change after candidate freeze creates a new
candidate identity. A released core is immutable; security prohibition is
published as a separate revocation/deprecation record.

Runtime negotiation has a separate fail-closed order:

`AUTHENTICATED_REALM_RESOLVED -> REALM_BOUND_OFFER ->
CONTRACT_IDENTITIES_MATCHED -> REALM_BOUND_TRANSCRIPT_COMMITTED ->
SESSION_STATE_CREATED`.

A missing, default, unknown, wildcard, or mismatched realm stops before contract
comparison can create session state. A later realm change retires the session;
it is never a transcript rebind.

## Bounds and resource behavior

Digests use fixed algorithms and lengths. Source-path sets, path lengths, file
counts, file sizes, extension counts, and manifest sizes are bounded. Digest
construction is domain-separated and length-prefixed. No remote URL or payload
selects the hash algorithm.

## Threat and hazard analysis

This decision prevents same-version semantic substitution, optional-extension
confusion, RC label reuse, corpus mismatch, optimistic publication, and a copied
manifest being mistaken for installed compatibility. It also prevents a
ratification artifact from requiring evidence that its own schema forbids or from
depending on a descendant authorization task. It does not attest source custody,
reviewer identity, role authority, reviewer independence, builder integrity,
signatures, or independent reproduction. Those remain external gates.

Direct realm binding also prevents a valid transcript, descriptor, deployed
receipt, or consumer cache entry from being replayed into a second authority
realm. A route-only or parent-only binding is insufficient because portable
evidence can outlive either container. Realm checks run before session-index
lookup or semantic allocation, so a foreign realm cannot probe or merge a local
session namespace.

## Formal properties

- Equal stable-core digests imply byte-equal generated membership under the
  specified digest construction.
- Stable-core, release, corpus, and extension-contract identities are unchanged
  when only `AuthorityRealmKey` changes.
- A stable-core mismatch cannot reach session state.
- An extension digest cannot satisfy the stable-core field.
- Every realm-scoped negotiation or session transcript contains one direct,
  non-default `AuthorityRealmKey` equal to the authenticated server realm.
- The transcript digest changes when only `AuthorityRealmKey` changes.
- An exact-byte transcript replay at another authenticated realm rejects. A
  separately valid transcript whose non-realm fields are identical but whose
  server-authority-principal or stable-realm-ID coordinate changes is a distinct
  lineage and cannot merge.
- No realm-scoped projection, receipt, or consumer foreign key can drop,
  default, wildcard, or rewrite `AuthorityRealmKey`.
- Two requests with identical principal, session kind, logical session ID,
  generation, contract fields, and bytes but different realm keys cannot share
  negotiation, replay, resumption, cache, or evidence state.
- No local evidence state implies external release authorization.
- A proposed ADR hash cannot appear in the accepted registry.
- No review record counts for a different ADR or decision-set digest.
- No review record counts after its packet or review-policy identity changes.
- An unresolved commit, tree, ADR blob digest, or ADR byte length fails
  structurally instead of becoming a stale review.
- No active rejection, unresolved condition, stale record, or superseded record
  can contribute to `ACCEPTED`.
- Non-normative acceptance cannot create the normative registry or authorize a
  rebaseline.

## Migration

The current compact hash remains visible only as a labeled diagnostic until the
rebaseline. The next candidate introduces the hard stable-core identity and
updates all peer types, fixtures, schemas, generated bindings, and consumers
together. The same migration adds the direct realm member to negotiation,
descriptor, transcript, deployed-receipt, and consumer foreign-key schemas.
Cross-realm replay and realm-dropping projection mutants are mandatory. Historical
0.8 identities remain frozen.

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

<a id="ncp-b01-selector-allocation-adr-002-v1"></a>

The exact stable-core file set still requires its named post-acceptance enumeration. Realm identity remains mandatory in every realm-scoped contract and receipt.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

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

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes. Owner rebaseline authorization remains a separate B02 gate.
