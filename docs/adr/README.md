# NCP 1.0 architecture decision review

This directory contains the non-normative architecture decisions for task `B01`.
The registry currently derives **PROPOSED** for every decision. None of these
documents changes the current unreleased, release-blocked `1.0.0-rc.1`
normative contract, compact proto hash, runtime authority, release status, or
external evidence state.

[`B01_REVIEW_PACKET.md`](B01_REVIEW_PACKET.md) is the current review packet. It
binds the eleven proposed ADRs to clean pushed source commit
`f376f212268b2da4d43975052d692e5f1be50ecb` and decision-set digest
`794c90203c662f1e12d78844c8ac8dcfc0162b0d3813b7df04cbe2e10cdd835a`.
It contains no review records. No qualifying review or independent
adjudication is recorded. All eleven decisions remain **PROPOSED**, and B01
remains `IN_PROGRESS`.

The current candidate remains wire `1.0` with compact proto contract hash
`163acc57d8a62b66`. The immutable `v0.8.0` release remains a different wire and
is not edited or silently translated by these records.

## Staging rule

The generated non-normative review registry is
[`decision-registry.proposed.v1.json`](decision-registry.proposed.v1.json). Its
source is
[`decision-registry.source.v1.json`](decision-registry.source.v1.json). Both live
outside `contract/` deliberately.

The current contract-manifest generator includes every
`contract/*.v1.json` file except its own output in the complete normative digest.
Therefore a proposed decision registry in `contract/` would silently become
normative. That is forbidden.

The registry can derive non-normative `ACCEPTED` without changing an ADR file.
The source contains no manual decision status. This rule prevents a status-line
edit from changing the reviewed digest.

Promotion to `contract/decision-registry.v1.json` remains blocked even when all
ADRs are accepted. N01 can promote only after all of these conditions hold:

1. every ADR is `ACCEPTED`;
2. every role obligation has enough distinct same-subject acceptance records;
3. no normative open question remains;
4. the proposed wire examples parse in the two independent prototype parsers;
5. the required preliminary models and resource probes have no unresolved
   counterexample under their declared bounds;
6. B02 retains explicit owner authorization for the exact decision-set digest
   and B01 ratification-receipt digest;
7. B03 closes its exact bounded registry allocations; and
8. N01 mechanically verifies the hashes, writes the accepted registry,
   regenerates the complete contract identity, and rejects a stale or blocked
   entry.

A status string inside `contract/` is not a staging boundary. Path exclusion plus
content-hash verification is the boundary.
N01 promotion is an exact mechanical projection, not a hand-edited copy. The
normative registry provenance must bind the frozen staging registry, decision
set, B02 authorization receipt, B03 allocation receipt and registry set, plus
the exact committed promotion generator and normative registry schema. The
regenerated contract manifest must bind both normative registry files.

This proposed non-normative separation addresses defect D19. The earlier
evidence model required B01 acceptance but could not store a review or derive
acceptance. It also made B01 depend logically on its B02 descendant.

## B01 machine-review surfaces

The expanded selector-closure authoring source and its compact form describe
the current non-normative architecture model. The external allocation inventory
uses owner-free semantic identities. Mechanical origins are committed
separately from non-authorizing usage and reference signals. The v4 review
profile contains the exact cross-language commitment rules and known-answer
vectors for identities, origin/signal evidence, semantic shape, semantic
subject, document rows, ADR source sets, and provenance.

The allocation proposal is a deterministic review aid. It retains every model
unit, origin, signal, prose match, ambiguity, and suggested destination. A
route is not an allocation. `UNMAPPED_SHARED` is an explicit fail-closed result.
The proposal cannot accept an ADR, authenticate a reviewer, or grant protocol
or release authority. Its source record binds the compact model, ADR corpus,
schema, and complete repository compiler source set.

A standard-library Node verifier recomputes the artifact-declared commitments
without importing the Python implementation. This is local
implementation-diversity evidence only. It is not an independent peer,
external review, consumer qualification, or release gate.

The observer read/capture bridge profile also remains non-normative and
synthetic. Its closed canonical-commitment suite fixes type domains,
normalization, resource limits, digest framing, and known-answer vectors. The
bridge retains and checks caller-supplied dispatch-attempt bytes against the
atomically committed outbox bytes. These checks do not qualify a live transport
or cryptographic deployment.

## Transaction and receipt terms

The same rule applies to each proposed ADR. `Post-CAS` states content dependency
order inside one serialized durable transaction. It does not permit a second
transaction after state commit.

Allocate stable receipt identity, signer/key version, clock context, and
deterministic inputs before the transaction. A deadline-sensitive fact and
candidate successor bind only receipt-free condition intents: exact
store/authority, transition/operation, prior state/head and prior selector
version, security state, clock, deadline/comparator, and timing-proof profile.
They do not bind a future sample, linearization instant, predicate result,
installed successor, installed selector version, commit, or receipt. Evaluate
security, clock, and the canonical complete intent set inside the transaction.
The integrated intent binds the guarantee identity. The bounded intent binds the
qualified bound, qualification-source digest, and enforcement policy, but not a
future enforcement, abort, or recheck result.
The intent-set and evaluation-set roots are explicit registered artifacts. Every
fact, successor, commit, receipt, and staged object uses the same typed digest;
an ad hoc tuple digest cannot substitute.

The timing proof is closed to an integrated transaction-manager linearization
guarantee or an independently qualified hard completion bound. The integrated
branch assigns one trusted authorization-linearization instant at the exact
serialization point where the selector compare-and-swap wins and guarantees
that every successfully committed transaction orders the selector change and
all applicable deadline predicates there; its completion bound is exactly zero.
The bounded branch binds one trusted sample, hard bound through signing and
durable commit, checked sum, qualification digest, and enforced abort or final
atomic recheck evidence. The store produces that evidence; an opaque caller hash
does not qualify. Fields from the other branch reject. All members of one set
use the same tagged profile and proof instance. The installed
heads, selector version, clock incarnation, and post-linearization evaluations
then freeze. Every evaluation binds its intent digest, installed successor
digest, and installed selector version. The transaction recomputes canonical set
roots, requires one transaction/store/timing instance and count, and verifies an
exact intent/evaluation digest bijection. Generic commits and complete signed
specialized receipt bytes bind those evaluations in dependency order. A
successor never binds an instant or result that does not exist until its own
linearization.

The closed transition-kind schema, not caller input, fixes every required
evaluation, generic commit, selector, specialized receipt type, and outbox item.
Every mutation of a composite selector has one enumerated transition kind and
receipt-free fact; an unnamed internal phase cannot mutate authoritative state.
Transition-specific internal constructors and semantic validators check every
context and content link; a matching type name alone is insufficient. The
schema derives each dynamic receipt/item cardinality from an authoritative
receipt-free fact or prior installed inventory. Canonical keyed entries require
an exact key/digest bijection; parallel digest tuples and fixture-sized
cardinality are invalid. The generic commit binds prior/installed heads, the
operation commitment, and intent/evaluation roots but not a future selector
digest. The installed selector binds the generic commit
and installed head. Specialized receipts bind the selector, generic commit, and
evaluations. Before evaluation, construct one registered receipt-free operation
commitment over the fact, candidate successor and prior context. The successor
does not bind that later commitment. The complete content order is
`intent -> fact -> candidate successor -> operation commitment -> evaluation
set -> generic commit -> selector -> specialized receipt`.

Build and validate one immutable, type-domain-separated transaction bundle
under one non-reentrant store lock before publication. Recheck the exact frozen
base immediately before publication; callbacks cannot reenter store mutation.
Canonical-copy or reject caller-owned mutable values.
Persist the selector, installed heads, post-linearization evaluations, commits,
specialized receipt bytes, and any applicable complete outbox item in that same
transaction. Publish the bundle atomically and commit durably.
Only then expose or emit a receipt or item. A losing transaction exposes nothing.
A post-commit follow-up cannot mint a missing receipt.
The transition record binds the complete receipt-free candidate commitment.
The signed generic and specialized receipts bind that same commitment.
After lost acknowledgement, only the same operation identity with that exact
commitment returns the stored record and receipt bytes; conflicting reuse
rejects.

An ordinary time sample before lock acquisition, signing, write-ahead-log
flush, or durable commit is not an authorization-linearization instant. If the
store cannot provide the integrated guarantee above, authorization requires an
independently qualified hard upper bound from its last trusted in-transaction
sample through signing and durable commit. The transaction binds that bound and
its qualification, requires `sample + bound < exclusive deadline`, and
fail-closed aborts or performs a final atomic deadline recheck if the bound can
be exceeded. A configured estimate does not qualify. A zero bound is valid only
with the integrated transaction-manager guarantee. Tests stall signing and
durable commit across equality and require rejection under the fallback profile.

Successor heads exclude post-CAS evaluations, commits, selectors, receipts, and
items that bind those successors. This exclusion prevents a content cycle. A
candidate head alone grants no authority; the complete installed chain is
required. Recovery validates the complete immutable bundle before it selects
and returns the exact persisted bytes, or it fails closed under the applicable
decision. Digest preimages use closed canonical artifact type identifiers and
schema versions registered to exact types, not runtime class names.

## Decision set

| ADR | Proposed decision | Required reviewer roles before acceptance |
|---|---|---|
| [ADR-001](0001-separate-simulation-and-plant-sessions.md) | Separate simulation-service and plant-control session contracts. | NCP maintainer, Engram owner, Crebain body owner, independent protocol reviewer |
| [ADR-002](0002-contract-identity-and-release-authorization.md) | Separate wire, stable-core, release, corpus, extension, and authorization identities. | Protocol reviewer, release/supply-chain reviewer |
| [ADR-003](0003-authenticated-production-ingress.md) | Use an authenticated terminating ingress, with signed forwarding only as an explicit two-axis forwarding profile. | Two independent security/cryptography reviewers, transport implementer |
| [ADR-004](0004-observer-attach-grants-and-revocation.md) | Add authenticated bounded observer attach, descriptors, grants, privacy, and revocation. | Prisoma owner, Galadriel owner, security reviewer |
| [ADR-005](0005-declared-stream-lifecycle.md) | Declare, retire, and redeclare every stream; exhaustion never rotates implicitly. | Distributed-systems reviewer, all stream consumer owners |
| [ADR-006](0006-body-issued-authority-and-time.md) | Make plant authority body-issued, term-fenced, bounded, and monotonic-time enforced. | Safety reviewer, distributed-systems reviewer, Haldir owner, Crebain owner |
| [ADR-007](0007-command-disposition-journal.md) | Add body-issued bounded command dispositions, durable query, and explicit ambiguity. | Plant/safety reviewer, Haldir owner, Crebain owner |
| [ADR-008](0008-extension-namespace-and-galadriel-separation.md) | Separate stable NCP routes from registered Galadriel extension routes and credentials. | Protocol reviewer, Galadriel owner, Haldir owner, Crebain owner |
| [ADR-009](0009-security-state-rotation-and-revocation.md) | Bind semantic security state, key rotation, revocation, and reattachment explicitly. | Security reviewer, operations reviewer, supply-chain reviewer |
| [ADR-010](0010-plane-qos-retention-and-overload.md) | Specify finite per-plane QoS, retention, priority, overload, and observer isolation. | Real-time/performance reviewer, consumer reviewers |
| [ADR-011](0011-ecosystem-topology-and-handover.md) | Ratify standalone-first dependency direction, per-surface migration identity, exclusive commander modes, body-coordinated handover, deny-only assessment, and pid-rs neutrality. | Every named consumer owner, pid-rs owner, independent security/distributed-systems reviewer, release/package-tooling reviewer, Crebain plant/safety reviewer |

Two decisions use maintained companion modules:

- [ADR-004 cross-store observer closure and enrollment](modules/adr-004-cross-store-observer-closure-and-enrollment.md)
- [ADR-009 cross-store producer and compromise evidence](modules/adr-009-cross-store-producer-and-compromise-evidence.md)

The source registry assigns these two paths explicitly. Every other decision has
an empty `module_paths` list. An unlisted module path fails registry generation.

## Common state and digest rules

The `content_sha256` field remains the SHA-256 of the exact main ADR bytes.
Companion module bytes do not change that field.

Each decision also has a domain-separated source-set digest. Its projection
contains the decision ID and an ordered source list. The main ADR is first.
Each module follows in `module_paths` order. Each entry binds its kind, path,
SHA-256, and byte length.

The decision-set digest binds each complete source set. It also binds the
ordered ADR identities, review obligations, defect mappings, review policy,
generator, and output schema. A source, module, or review-policy change makes an
earlier review stale.

Each main ADR and module is limited to 256 KiB. The complete parent-and-module
Markdown corpus has a 2 MiB limit. The generator rejects symlink and hard-linked
worktree source files. The commit resolver requires each reviewed source to be a
regular Git blob.

JSON examples keep their separate 128 KiB parser limit. A larger Markdown file
does not increase that parser budget.

Any ADR or obligation edit makes an earlier review stale. The generator retains
stale and superseded records as history, but these records never count.

Each role obligation has:

- a stable `role_id` and label;
- a minimum number of distinct reviewer identities; and
- an explicit independence requirement.

Each review record must bind:

- a stable issuer-and-subject reviewer identity;
- the exact role and implementation-owner identities;
- the decision-set digest, source-set digest, and exact main ADR identity;
- the reviewed source commit, tree, and current packet digest;
- `ACCEPT`, `REJECT`, or `ACCEPT_WITH_CONDITIONS`;
- content-addressed role-authorization and external-review receipts;
- an independence claim and a separate content-addressed assessment when the
  role requires independence;
- all conditions, resolution evidence, and reviewer closure receipts;
- the review timestamp; and
- an explicit predecessor when it supersedes a review.

Supersession chains must advance in time and cannot fork or cycle. One reviewer
cannot have parallel active chains for one ADR and role.

An active rejection blocks acceptance. An unresolved condition also blocks
acceptance. A resolved condition counts only when the same reviewer closes it
against the same main ADR, source-set, and decision-set digests.

The generator resolves the named commit as a real Git commit. It checks the
named tree and every ADR source blob against the recorded digest and byte
length. It also checks the packet digest against the current packet bytes.

With zero reviews, the repository can retain a superseded packet or a packet
template. Before review capture starts, the packet must have exactly one
machine-readable lifecycle block in state `CURRENT` and exactly one `CURRENT`
subject block. The lifecycle block, not surrounding prose, controls whether
review capture is permitted. The subject binds the current decision-set and
policy identities, Git source, zero-review decision-source identity, claim
boundary, promotion block, and complete ADR and role inventory. The named commit
must contain the exact current generator, output schema, zero-review decision
source, main ADR bytes, and module bytes. The subject does not contain the
packet's own digest.
Each external request and review record binds the packet bytes instead.

Create the subject only with:

```bash
python3 scripts/generate_decision_registry.py --emit-review-subject <40-character-commit>
```

The command fails if the commit does not contain every exact reviewed input.

Retained evidence uses an absolute HTTPS receipt URL and a repository-relative
regular file. The record binds its SHA-256, byte length, and media type. A URL,
hash, `independence_claimed=true` value, or structurally valid assessment does
not prove authorship, role authority, or independence. B01 must retain and
independently assess that external evidence. Role authorization and the review
receipt use separate retained files; an independence assessment uses a third
file when required. Review, role-authorization, independence, and
condition-closure receipt paths, URLs, and byte digests are exclusive across
review records. Per-file, aggregate-byte, and unique-file limits prevent
evidence references from amplifying local validation work.
The later B01 ledger adjudications and B02 owner authorization also retain
exclusive, content-addressed external receipts. Their decision artifacts and
receipt bytes must exist as exact blobs in the pushed passing commit.
Every content-addressed registry review-evidence file must remain a regular
current file and resolve as the exact same blob in the pushed B01 receipt
commit. The packet's zero-review source commit must be a strict ancestor of that
pushed commit.

No model-generated advice counts as a reviewer, approval, proof, or evidence.
Exact Fable 5 consultations used to challenge the drafts are recorded only as
non-normative design inputs in
[`../research/b01-fable-architecture-consultations.md`](../research/b01-fable-architecture-consultations.md):

- five usable exact-model consultations are recorded, ending with the cutover
  and review-packet challenge response SHA-256
  `080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`;
- five other exact-model or configuration attempts failed or returned incomplete
  text and are recorded as failed consultations, not advice.

The drafts accept useful counterexamples but reject suggestions that conflict
with current NCP semantics. In particular, `SessionRef.generation` and
`StreamPosition.epoch` are opaque UUIDv4 equality fences, never ordered counters,
and Prisoma is never part of the command path.

## Review lenses

Every ADR contains explicit decisions for all ten blueprint lenses:

1. protocol semantics;
2. security and trust;
3. safety and plant boundary;
4. distributed lifecycle;
5. resources and real time;
6. interoperability and migration;
7. science and statistics;
8. implementation and operations;
9. verification and evidence; and
10. lifecycle and governance.

The three mandatory review perspectives are also preserved:

- protocol, security, and plant correctness;
- consumer and runtime usability; and
- operations, science, and evidence honesty.

## Verify

Run:

```bash
python3 scripts/generate_decision_registry.py --self-test --check
python3 scripts/check_adr_examples.py --self-test
python3 scripts/check_markdown_links.py
python3 scripts/generate_audit_artifacts.py --self-test
python3 scripts/check_audit_artifacts.py --self-test
```

The following command must fail while any ADR lacks complete current reviews:

```bash
python3 scripts/generate_decision_registry.py --require-all-accepted
```

The generator can derive a non-normative `ACCEPTED` status from structurally
complete records. Its checks do not prove the external reviewer facts. They
cannot satisfy B01's independent evidence floor, authorize a candidate
rebaseline, promote into `contract/`, or release NCP 1.0.
