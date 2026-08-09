# ADR-004 — Attach observers with bounded grants and revocation

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: Prisoma owner, Galadriel owner, NCP/source-provider owner,
  observer-anchor infrastructure owner/operator, security reviewer, independent
  anchor security/distributed-systems reviewer

## Context

Galadriel and Prisoma need read-only access to live observations and command
dispositions. Prisoma also needs exact command proposals for its action axis.
Reading a command proposal is not permission to publish or apply one. Current
consumers cannot securely infer a live server-issued session generation,
negotiated contract, streams, or permitted channels from the first frame.
Traffic cannot choose its own authorization context, and a generic session
description can expose private topology.

## Proposed decision

NCP shall define an authenticated observer lifecycle:

- `AttachObserver` requests access to one already-live typed session;
- `ObserverAttached` returns a body/service-issued descriptor plus a bounded
  read-only grant;
- `RenewObserverGrant`, `DetachObserver`, and body-issued revocation provide
  explicit lifecycle and receipts.

Every cross-store protected output uses the ADR-009 maximal-producer hierarchy.
The producer creates one manifest per nonempty homogeneous family and one final
`CrossStoreProducerBundleCompletionManifest`. In this ADR, “manifest” shorthand
includes the public pre-manifest commitment, selected family manifest,
completion manifest, both authentications, and the delivery capsule with both
membership proofs. A family manifest alone never authorizes output or exposes
sibling topology.

Initial `AttachObserver` names only the authenticated observer's logical session
target and literal requested access. It cannot infer or supply the live
generation, descriptor or security context. The server freshness-challenge
commitment resolves and freezes that exact current context before the final
request envelope exists.

`ObserverDescriptor` binds the exact responder, revision, neutral ADR-001 realm
and transaction domain, store, source, generation, contract and security
digests, stream publishers, schemas, privacy policy, and operation context. A
live or history operation binds a bounded canonical boundary set. History also
enumerates every authorized epoch, publisher, provenance policy, schema, and
semantic contract.

The descriptor is bounded, canonical, and self-excluding. External clock hints
are diagnostic only. Before envelope verification, the receiver recomputes the
closed route, publisher, realm, source, epoch, position, schema, semantic,
privacy, and boundary fields. ADR-005 forbids epoch reuse. Unknown, duplicate,
bad-digest, or wrong-content inputs reject.

`InstalledObserverAuthorizationStateSelector` selects the canonical
`ObserverAuthorizationStateHead`. The head binds its scope, realm, source,
incarnation, version, prior, clock, descriptor, security, authority domain,
store, qualification, participant, and subordinate registries. Nothing is
caller-selected. Each authority mutation compares current
`LOCAL_SECURITY_ENFORCEMENT` and `InstalledSecurityAuthorityStateSelector` in
its CAS. Only the same-domain ADR-009 security cut can co-write them.

Closed `OBSERVER_ROOT` is `PENDING_PARENT_CONFIRMATION | ACTIVE |
RETIRED_DRAIN_ONLY | TERMINAL`. Ordinary work requires ACTIVE. Drain-only permits
terminalization/checkpoint construction but no new authority. `TERMINAL`
forbids every authority-widening or ordinary-work mutation. Independent remote
closure and global reconciliation use explicit `TERMINAL -> TERMINAL`
authority-narrowing self-edges on this same selector, so retained history can
still become more exact. The head also binds the
non-authorizing predecessor-cut/pending-target checkpoint branch.

The bounded freshness map is keyed by the authenticated requester and stable
key. Its states are `AVAILABLE | CONSUMED_BY_ACCEPTED_REQUEST |
CANCELED_UNUSED | EXPIRED_UNUSED`. Slots, commitments, and results are retained,
never reused or evicted. Capacity is reserved before issuance. Exhaustion
denies, or retires the child when no complete local terminal partition exists.
Reset requires all local grants server-terminal and the durable pending-target
root. Global target entries continue to fence remote obligations.

Every freshness slot has one closed
`ObserverGrantChallengeDeliveryGateState`: `DIRECT_DELIVERY_READY |
ANCHOR_PAIRED_FRAME_PENDING | ANCHOR_PAIRED_FRAME_ADMITTED |
DELIVERY_TERMINAL`. Direct and independent-anchor issuance use different
initial states. Only the same-selector paired-frame admission can expose the
byte-identical installed frame. Acceptance, cancellation, expiry, a clock cut,
or retirement makes the gate terminal in the slot-state CAS. A pending gate,
an anchor member, a receipt, a private producer object, or caller-supplied bytes
grant no queue authority.

The outer head also binds a bounded
`ObserverGrantPairedChallengeFrameAdmissionRegistry` under one preallocated,
never-reused `ObserverGrantPairedChallengeFrameAdmissionKey` per anchor
issuance. The linked module defines its immutable record, exact source and
recipient bindings, producer and delivery proofs, cutoff, serialized handoff,
resource reservation, retry, and terminal-partition rules.

The generation-independent source-issuance index, eligible-root registry, independent exposure anchor, padded sparse proofs, paired-frame admission gate and permanent closure projections are defined in the [cross-store observer closure and enrollment module](modules/adr-004-cross-store-observer-closure-and-enrollment.md). That maintained module is a content-bound part of this ADR review source set; all closed states, races and fail-closed outcomes apply here.

The independent-anchor profile requires an installed, externally qualified
protocol-infrastructure subject. It does not count as a consumer role. The
linked module binds its provider, corpus, deployments, policies, ecosystem,
campaign, limitations, identities, credentials, stores, failure domains,
signatures, currentness, and revocation evidence. Same-field and cross-field
aliases reject. Local validation proves structure only. Missing external X05
qualification keeps the profile unavailable.

`OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION` installs version-1
pending outer/freshness/grant heads, descriptor and predecessor/pending-target
branch. One authority-domain CAS consumes exact
`LogicalSessionGenerationCreationReceipt` and `ALLOCATED` child marker, requiring
current `GENERATION_ALLOCATED_PENDING_CHILD_GENESIS`, typed child absence and
`CANDIDATE_PARTICIPANT_ADMISSION`; it installs child selector/head, participant
and closure reserve while advancing the domain. Random/local genesis, replay,
stale parent, split store or domain mismatch rejects.
`ObserverAuthorizationStateCommitReceipt` binds exact versions and
`AuthorityTransactionCommitReceipt`.

The closed outer transition kind is
`OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION |
ACTIVATE_OBSERVER_AUTHORIZATION_AFTER_PARENT_CONFIRMATION |
OBSERVER_GRANT_REQUEST_FRESHNESS_TRANSITION |
OBSERVER_GRANT_REGISTRY_TRANSITION |
OBSERVER_AUTHORIZATION_CLOCK_RESTART |
REPLACE_OBSERVER_DESCRIPTOR_OR_PRIVACY |
APPLY_OBSERVER_SECURITY_REBOUND_OR_REVOCATION_CUT |
RETIRE_OBSERVER_SESSION_GENERATION |
FINALIZE_OBSERVER_SESSION_GENERATION`.
The last three use receipt-free
`ObserverDescriptorPrivacyReplacementTransitionFact`,
`ObserverSecurityRevocationCutTransitionFact`, or
`ObserverSessionRetirementTransitionFact`. Each fact binds the exact prior
descriptor/security/session state, authenticated cause, canonical complete
partition of request slots by `AVAILABLE | CONSUMED_BY_ACCEPTED_REQUEST |
CANCELED_UNUSED | EXPIRED_UNUSED`, complete affected grant-key set, one per-key
terminal subfact, and unchanged siblings. The winning cut changes every affected
`AVAILABLE` slot to `CANCELED_UNUSED` with its exact cut cause, preserves every
unused terminal tombstone, and links each consumed slot to the exact grant
terminalization/closure branch. Its specialized receipt binds the prior and
installed freshness-registry and grant-registry heads and exact partition
cardinalities. Missing, extra, duplicate, differently partitioned or
caller-summarized challenge entries reject the whole cut. No unnamed outer
selector mutation is valid.

`ACTIVATE_OBSERVER_AUTHORIZATION_AFTER_PARENT_CONFIRMATION` alone moves the
pending root to ACTIVE. It consumes the exact ADR-001
`LogicalSessionGenerationGenesisConfirmationReceipt`, verifies that the exact
installed source lineage still names the same source `session_kind`, logical
session ID and generation in `GENERATION_LIVE`, and binds that receipt into the
installed ACTIVE head. The observer and parent selectors plus domain-state
selector are compared through one exact authority-domain condition/commit; a
historical parent receipt without that current compare rejects. It grants no
observer scope by itself. Later challenge and grant transitions still perform
their full checks. No target-history entry can
name this observer child before activation. Parent-pending state can instead move
directly to RETIRED_DRAIN_ONLY through the partial-generation retirement path.

`RETIRE_OBSERVER_SESSION_GENERATION` alone changes
PENDING_PARENT_CONFIRMATION or ACTIVE to RETIRED_DRAIN_ONLY. Its closed
`ObserverSessionRetirementParentEvidence` is
`PARTIAL_PARENT_GENESIS | CONFIRMED_PARENT_BEFORE_OBSERVER_ACTIVATION |
ACTIVE_PARENT_RETIREMENT`. The first two branches require the exact pending child,
their applicable ADR-001 partial-retirement or confirmation plus retirement
receipts, an empty operation registry, and a complete global-registry partition
showing that no target entry names this child incarnation. The ACTIVE branch
requires the exact parent retirement receipt and conditionally compares the
complete target-entry set for this source generation. Its winning transaction
moves that complete set from `CURRENT_SOURCE_GENERATION` to
`SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION`, terminalizes every
request slot and server grant lineage, and preserves every unrelated global
entry. The transition proves a server-authority cut only. It does not claim that
an independent delivery boundary stopped release or that retained transport
drained. Every branch compares the domain-state, parent, observer and applicable
target-history selectors through the exact common authority-domain condition;
the active branch co-mutates observer and target-history selectors and emits one
transaction commit receipt before their specialized receipts. It holds no
transaction open while waiting for a remote boundary.

Receipt-free
`ObserverSessionGenerationFinalizationFact` is constructed only later from the
exact drain head, complete server terminal map, every immutable continuation-
policy assessment that applies to a terminal grant, and a canonical complete map
of remote authorization and transport obligations. The exact closed assessments
are `REATTACH_ELIGIBLE_AFTER_COMPLETE_CLOSURE | REATTACH_FORBIDDEN` and
`FRESH_ATTACH_ELIGIBLE_AFTER_COMPLETE_LINEAGE_CLOSURE |
FORBID_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE`; neither is an ALLOW result. Each
remote obligation retains its exact boundary, grant, installed cutoff and current
aggregation member state/evidence. Checkpoint status is `CLOSED` only for
`TRANSPORT_QUIESCENT`; `UNOBSERVED | AUTH_CLOSED_UNKNOWN | AUTH_CLOSED_EXACT`
remain `PENDING`. Missing obligations reject, but PENDING does not block local
finalization. The fact also
contains canonical `ObserverAttachmentTargetLineageCheckpointCandidate` content
and a complete
`ObserverAttachmentTargetLineageCheckpointCandidateSetRoot`, but forbids the
candidate terminal head and
every finalization, reconciliation, publication or checkpoint receipt.
Each candidate binds immutable obligations and the full finalization-time lattice
snapshot, not a mutable head digest. Later updates preserve it byte-for-byte.
Publication proves monotonic descendant evidence for every PENDING member and
exactly preserves each already-quiescent member.
`FINALIZE_OBSERVER_SESSION_GENERATION` alone consumes that fact, installs
TERMINAL and emits `ObserverSessionGenerationFinalizationReceipt`. TERMINAL means
that this source generation can create no new server observer authority; it is
not a remote-delivery or transport-closure claim. After that CAS, one
`ObserverAttachmentTargetLineageCheckpointFact` for every affected target binds
the installed terminal head, observer finalization receipt, byte-identical
candidate and `ObserverAttachmentTargetLineageCheckpointCandidateSetRoot`. A
missing, extra, duplicate, nonterminal server
grant or policy-inconsistent target rejects. RETIRE cannot mint a final
checkpoint early, and a remote outage cannot hold plant retirement or source-
generation reuse hostage.

The genesis outer event carries subordinate
`GRANT_REQUEST_FRESHNESS_REGISTRY_GENESIS_FROM_UNINITIALIZED` and
`GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED`. The closed request-freshness
transition union is
`ISSUE_OBSERVER_GRANT_REQUEST_FRESHNESS_CHALLENGE |
ADMIT_OBSERVER_GRANT_PAIRED_CHALLENGE_FRAME |
CANCEL_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE |
EXPIRE_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE`. Each uses the same outer
selector and changes one exact request slot or its proved nonmembership plus
only its declared subordinate admission-registry effect while preserving the descriptor,
grant registry and every sibling slot. Every ordinary attach, renewal,
activation, terminalization, or reattachment outer compare-and-swap uses
`OBSERVER_GRANT_REGISTRY_TRANSITION` and carries exactly one registry kind and
one selected registry key. Attach, renewal and reattachment additionally
consume one exact current request-freshness slot from `AVAILABLE` to
`CONSUMED_BY_ACCEPTED_REQUEST` in that same outer compare-and-swap. No separate
acceptance state can become
durable before or after the grant-registry mutation. A bulk clock, descriptor,
security, or session cut uses its distinct outer kind and carries one
`TERMINATE_GRANT` subfact for every member of its canonical complete affected-
key set and terminalizes every affected `AVAILABLE` request slot. The
`AuthorityTransactionCommitReceipt`, `ObserverAuthorizationStateCommitReceipt`
and applicable specialized registry receipts bind both domains and the exact key
cardinality. An implementation cannot substitute a subordinate kind for an
outer kind or omit the wrapper transition.

Before it asks for a server challenge, the observer constructs and durably
records one receipt-free `ObserverGrantRequestIntent`. The intent binds the
authenticated observer principal, stable request key, never-reused observer
challenge, exact `ObserverGrantRequestTargetKey`, requested literal access,
route, destination principal, audience, maximum duration and one closed
`ObserverGrantRequestedSetPolicy`:
`REQUIRE_EXACT_REQUESTED_SET | ALLOW_EXPLICIT_PARTIAL`. Exact is the default.
Its closed kind is
`ATTACH_LOGICAL_TARGET | RENEW_EXACT_PREDECESSOR |
REATTACH_EXACT_TERMINAL_PREDECESSOR`. The initial-attach variant binds only the
logical session target and requester-known request semantics. It structurally
forbids a caller-supplied generation, descriptor/security/revocation state,
resolved stream/declaration/boundary set or predecessor. The server challenge
commitment resolves and freezes those current fields. Renewal binds its exact
known live predecessor and context. Reattachment binds its exact known terminal
predecessor and one closed `ObserverGrantReattachmentOriginEvidence`. The
`CURRENT_GENERATION_TERMINAL` branch requires the eligible assessment,
the exact `ProtectedObserverGrantClosureResultEnvelope /
TRANSPORT_QUIESCENT`, its publication manifest and passing verification, which
bind the distributed-authorization-closure and transport-quiescence receipts,
plus exact `ObserverGrantRoleClosureEvidenceCompleteRecordSetAssessment`,
its canonical `ObserverGrantRoleClosureEvidence`, the required
`COMPLETE_SET_POSITIVE_CONTINUATION_ELIGIBLE` outcome and
`ObserverGrantPositiveContinuationTrustEvidence`; it forbids a final policy
result or publication receipt. The `PUBLISHED_PREDECESSOR_TARGET` branch instead requires
the final `REATTACH_ALLOWED` result and target publication receipt, which already
bind all four cuts and positive-continuation trust, and forbids a
current-generation assessment as authority. Both branches are complete before
challenge issuance.
These source-owned branch bytes cross to the observer only in
`ProtectedObserverGrantReattachmentOriginEvidenceEnvelope`, an ADR-009
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT` specialization for
that exact observer root, grant/target, operation and replay domain. The current
branch binds the protected closure result and manifest, installed role record/
resolution/writer receipt, complete record-set assessment/root, exact
role-resolution envelope/manifest/verification, current-origin publication
receipt and complete-set positive-continuation trust. The
published branch binds the checkpoint result,
publication receipt and their all-four-cuts/trust ancestry.

`PUBLISH_OBSERVER_GRANT_CURRENT_REATTACHMENT_ORIGIN_EVIDENCE` is the sole
producer of the current branch. It is legal only for the exact terminal grant in
an open target-history entry at `CURRENT_SOURCE_GENERATION`. Receipt-free
`ObserverGrantCurrentReattachmentOriginPublicationFact` binds the current
target-history head/entry, terminal key/head/receipt, installed eligible
assessment, exact inner
`ObserverGrantReattachmentOriginEvidence / CURRENT_GENERATION_TERMINAL`,
transport-closure envelope/manifest/verification, exact role
record/resolution/writer receipts,
`ProtectedObserverGrantRoleClosureEvidenceResolutionEnvelope`,
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest` and passing
verification, exact
`ObserverGrantRoleClosureEvidenceCompleteRecordSetAssessment`, its canonical
record and positive outcome, complete-set positive-continuation trust, an absent
bounded per-grant publication-map key, preallocated output identities,
operation/replay domain and reserve. Its exact
`ObserverGrantCurrentReattachmentOriginAssessmentCoordinate` binds the
assessment digest, record-set root, source-security selector/head/version,
cumulative incident root and current manifest-authorization re-read. It excludes
successors, commits, receipts and output bytes.
The fact, envelope and manifest also bind exact
`ObserverGrantCurrentReattachmentOriginWriterSecurityProfile /
CURRENT_ONLINE_PRIMARY_PREDECESSOR_WRITER`: global security phase `CURRENT`,
`PREDECESSOR_THRESHOLD` under the current installed policy, and
`CrossStorePublicationManifestAuthenticationOrigin /
SOURCE_SECURITY_AUTHORITY_TRUST / ONLINE_PRIMARY`. Prepared, rebind-pending,
emergency, drain, retired, dual or offline-recovery substitution rejects; this
positive-output event is never offline-allowlisted.

The target entry owns an append-only bounded
`ObserverGrantCurrentReattachmentOriginPublicationMap` keyed by that full
coordinate, never by record-set root alone. One target-history CAS compares all
coordinate fields to current installed values and inserts only an absent key as
`COMMITTED_CURRENT_ORIGIN`; its
`ObserverGrantCurrentReattachmentOriginPublicationReceipt` binds the installed
map member, target-history commit and common transaction receipt. The envelope
binds that receipt, coordinate and the fact's exact inputs after the CAS.

The accepted-grant reserve precharges the manifest-bounded
`maximum_current_origin_publication_versions` and each member's receipt,
envelope, pre-manifest commitment, manifest, authentication/member proof and
retained exact-retry result. A later record, security head, incident root or
manifest-authorization change leaves every older map member historical and
non-authorizing. A new positive complete assessment may append a fresh
coordinate; restrictive/untrusted/isolation assessment cannot. Exact retry
returns the installed member bytes; changed input rejects. Exhaustion disables
current-origin reattach and never overwrites/reuses a coordinate; checkpoint
publication may still proceed under its own guards. Transport-first and
role-record-first converge on the same fact. Duplicate publishers and source
finalization race on the same target-history/source-currentness condition: one
wins, and finalization-first closes this event. The checkpoint publication event
is the sole producer of `PUBLISHED_PREDECESSOR_TARGET`. Its candidate excludes
the later origin envelope/manifest; after the checkpoint receipt, the retained
publication bundle binds that receipt and exact all-four-cuts/trust result.
Exact retry returns those bytes. It cannot produce the current branch, and a
current-branch bundle cannot replace its checkpoint receipt.

`ObserverGrantReattachmentOriginEvidencePublicationManifest` binds the envelope,
source target-history commits, signer ancestry and exact-retry bytes last.
Observer-side PREPARE/BEGIN requires that manifest, membership and passing
verification; bare assessment, record, result or checkpoint receipt is not
origin evidence.
It explicitly excludes every server challenge/commitment/receipt, server slot,
server clock/cutoff, local send-attempt ID/time/deadline, response, grant,
successor head and post-issuance field. Thus its digest is complete before server
challenge issuance and cannot contain that challenge directly or indirectly.

The canonical `ObserverGrantRequestTargetKey` derives exactly from the typed
`ObserverAuthorityRealmKey` (server authority principal plus stable realm ID),
source `session_kind`, canonical source logical-session ID and authenticated
requester principal. `ObserverAuthorityRealmKey` is exactly the ADR-001
typed alias/projection of neutral `AuthorityRealmKey` and has the same canonical
value as its `AuthorityTransactionDomainKey`; it excludes rotating security
epochs, registry incarnations and source generations. The observer outer selector, realm-global
target-history selector, source lineage and authority-domain selector therefore
share one qualified transaction-domain/store incarnation. Simulation and plant sessions can use the
same logical-session bytes without colliding because `session_kind` is in the
key. The key excludes source generation, requested scope, stream or boundary
members, operation kind, predecessor grant or closure, request key, grant ID and
every observer process or admission-state incarnation. Those request- and
operation-specific fields remain immutable intent and exclusivity-proof inputs,
but they cannot create a new target namespace. Thus `{A}`, `{B}`, `{A,B}`,
initial attach, renewal, reattachment, process restart, source-generation
rollover and skipped source generations for one logical attachment all contend
on the same key. Separate independently enrolled requester principals use
separate keys and remain subject to aggregate manifest quota. The key is not a
hash-only coordinate, free caller label or observer logical-session ID.
Unknown/default source kinds, wrong principals, ambiguous canonicalization and
same-target-different-spelling values reject.

Every local PREPARE, server challenge ISSUE and server request acceptance binds
one receipt-free `ObserverGrantRequestTargetExclusivityProof`. It names the
target and candidate request key, exact installed local or server composite head,
complete bounded current-generation request-operation and freshness maps and, at
the server, the complete current grant registry plus one closed
`ObserverAttachmentTargetHistoryEvidence`:
`NO_TARGET_HISTORY | PUBLISHED_TARGET_CHECKPOINT |
CURRENT_SOURCE_GENERATION_TARGET`. `NO_TARGET_HISTORY` is legal only for the
first challenge transaction and requires exact global map nonmembership.
`PUBLISHED_TARGET_CHECKPOINT` binds the exact installed checkpoint entry,
publication receipt and operation-specific continuation policy.
`CURRENT_SOURCE_GENERATION_TARGET` binds an entry that already names the exact
ACTIVE observer child and LIVE source generation. Each branch contains a
canonical key/digest partition of every same-target current member, retained
terminal history and the only operation-kind-specific eligible predecessor.
Missing history, a pending unpublished checkpoint, wrong source kind or
generation, incomplete partition or stale proof rejects.

The authority/realm owns one bounded
`ObserverAttachmentTargetHistoryRegistryHead` through the sole realm-global
`InstalledObserverAttachmentTargetHistorySelector`. Its canonical map is keyed
directly by `ObserverGrantRequestTargetKey`. The head and selector bind the
realm's exact ADR-001 `AuthorityTransactionDomainKey`, transaction-store
incarnation, qualification digest and registered
`OBSERVER_TARGET_HISTORY` participant role. Its closed root phase is
`OPEN_TARGET_HISTORY | DOMAIN_RETIREMENT_SEALED`; only the open phase permits an
entry mutation. Closed entry phase is
`CURRENT_SOURCE_GENERATION |
SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION |
SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION |
CHECKPOINT_PUBLISHED |
SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE |
SOURCE_PERMANENTLY_RETIRED_SEALED_UNRESOLVED_TOMBSTONE`; map absence is typed
nonmembership, not a permissive
entry. Each entry binds the exact source lineage identity, source generation,
observer-child incarnation, inherited or candidate checkpoint, latest immutable
policy assessments or published results, retained no-reuse ancestry and one
bounded `ObserverGrantClosureAggregationHead` map. That map is keyed by the full
source generation and complete accepted-grant installation identity, never by
the stable target alone. Request acceptance atomically inserts its version-1
entry with the receipt-free accepted-result commitment, preallocated receipt
identity, immutable boundary plan/member identities,
precharged byte/write/signing reserve, empty idempotency-result map and every
boundary member `UNOBSERVED`, plus distinct
`ObserverGrantRoleCompletionState` for that full accepted-grant installation
identity, never one scalar per stable target. Its source of truth is bounded
append-only `ObserverGrantRoleClosureEvidenceRecordSetRoot`, keyed by that grant
identity and one closed `ObserverGrantRoleClosureEvidenceOriginClass`:

`SOURCE_PENDING_NEVER_LIVE |
SOURCE_WHOLE_ROOT_EMERGENCY |
SOURCE_WHOLE_ROOT_FINAL_RETIREMENT |
LOCAL_ROLE_COMPLETION |
FINITE_ROLE_HORIZON_ELAPSED |
QUALIFIED_PERMANENT_ROLE_ISOLATION`.

Each absent key can become one immutable, receipt-free
`ObserverGrantRoleClosureEvidenceRecord`. It excludes the candidate that installs
it and every same-CAS commit, receipt, proof, envelope or manifest. The
record binds preallocated writer-receipt and resolution identities. Its
origin-specific union binds only artifacts already available before that CAS:
pending-never binds its closure commitment/projection and preallocated evidence
identity; whole-root binds the earlier external return envelope/manifest/stored
verification and source close; local completion binds the earlier protected
local envelope/manifest/verification; finite elapsed binds the plan boundary,
clock/restart ancestry and deadline intent, not its later evaluation; isolation
binds the qualified fact/authentication. Cross-origin fields reject.
Post-CAS `ObserverGrantRoleClosureEvidenceRecordResolution` binds the installed
record and target-history commit plus the origin-specific later proof,
evaluation, writer receipt and ADR-009 ledger/lineage receipts. It excludes every
later protected output and final manifest. Exact
`ProtectedObserverGrantRoleClosureEvidenceResolutionEnvelope` binds that
resolution, installed record/target commit, full accepted-grant role identity,
origin-specific proof/evaluation/writer/ledger receipts, exact observer-root
audience, operation and replay domain. It is exactly ADR-009
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`. It excludes
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest`; that exact
type-specific family manifest binds the
`CrossStoreProducerPreManifestBundleCommitment`, complete writer
transaction/receipt/sidecar set, signer ancestry, and either one
resolution/envelope or the reconciliation transaction's canonical
member-to-resolution/envelope bijection. The mandatory ADR-009 completion
manifest authenticates the exact family set last. Every consumer binds the
family-member proof, family-set proof and completion. Passing
`CrossStoreSecurityReceiptVerificationEvidence` is created only afterward.
Every origin's owning writer persists this complete post-resolution hierarchy
in its crash-complete transaction after its required proof/evaluation exists.
The envelope, family manifest and completion manifest bind one closed
`ObserverGrantRoleResolutionWriterSecurityProfile` derived from the installed
source-security phase and writer transaction, never from the message. In
`CURRENT`, it is `ONLINE_PRIMARY_SOURCE_WRITER`, requires
`PREDECESSOR_THRESHOLD` under the exact current installed policy, and selects
`CrossStorePublicationManifestAuthenticationOrigin /
SOURCE_SECURITY_AUTHORITY_TRUST / ONLINE_PRIMARY`. In
`EMERGENCY_FENCED_RECOVERY_REQUIRED | DOMAIN_RETIREMENT_DRAIN`, it is
`OFFLINE_RECOVERY_SOURCE_WRITER`, requires the exact installed-policy allowlist
for this target-history-only closure recovery or retirement writer plus
`OFFLINE_RECOVERY_THRESHOLD`, and selects
`SOURCE_SECURITY_AUTHORITY_TRUST / OFFLINE_RECOVERY_DOMAIN`. `DOMAIN_RETIRED`
permits archive only. `PREPARED_CHANGE` and
`SUCCESSOR_ACTIVE_REBIND_PENDING` wait for `CURRENT`, emergency or drain; this
non-key-changing writer never invokes dual continuity. An offline profile
forbids a ledger mutation or open-marker close. Any phase/profile,
continuity, old-policy, key-origin, class or audience substitution rejects.

The pending-never terminal producer installs no
`SOURCE_PENDING_NEVER_LIVE` role record. Its source/target candidates bind only
the closure commitment plus preallocated record, writer, resolution and output
identities and reserve. Its protected terminal envelopes and
exact applicable source-closure, boundary-decision and ledger-close family
manifests plus mandatory shared completion complete that first producer bundle
and exclude the later proof and second target-history transaction. No family
alone completes it.
The pending-never proof also structurally excludes the later record, commit,
receipt, resolution, envelope, pre-manifest commitment, family/completion
hierarchy and verification. Thus its order is terminal transaction -> terminal
envelopes -> terminal pre-manifest/families/completion/retention ->
pending-never proof -> independent role-record transaction -> resolution
envelope -> role pre-manifest/family/completion/retention -> verification.

The state also binds derived
`ObserverGrantRoleLocalEvidenceStatus`:
`LOCAL_EVIDENCE_ABSENT | VERIFIED_LOCAL_EVIDENCE_RETAINED`, and
`ObserverGrantRoleFiniteHorizonStatus`:
`FINITE_HORIZON_INAPPLICABLE | FINITE_HORIZON_PENDING |
FINITE_HORIZON_ELAPSED`. Both plan modes initialize an empty record set and
local absence; `LOCAL_TERMINAL_CLOSURE_REQUIRED` selects finite inapplicability,
while `FINITE_ENFORCED_FINAL_BOUNDARY` selects finite pending. Adding the local
or finite record derives the corresponding one-way status edge. Source records
join by set union. No record or status can be removed, replaced or downgraded.
Exact record replay consumes no version; a different later record for an
already-retained origin is archive-only. Thus concurrent origin-specific
updates commute. Each record retains its verification/trust disposition;
`RESTRICTIVE_ALTERNATIVE_CLOSURE_REQUIRED` and permanent isolation are always
closure-only and cannot support positive continuation.

Checkpoint publication never selects an arbitrary member of that set. For each
accepted grant, its receipt-free
`ObserverGrantRoleClosureEvidenceCompleteRecordSetAssessment` binds the complete
installed record-set root; a canonical ABSENT/PRESENT partition of all six
origins; every present record, resolution, writer receipt, protected envelope,
pre-manifest commitment, final manifest, membership proof and verification; and
the exact current source-security head, cumulative incident root and manifest
authorization re-read at checkpoint linearization. It classifies every present
record once and derives exactly one closed outcome:
`COMPLETE_SET_POSITIVE_CONTINUATION_ELIGIBLE |
COMPLETE_SET_RESTRICTIVE_CONTINUATION_ONLY`. Any permanent-isolation origin,
`UNTRUSTED_REJECT` or `RESTRICTIVE_ALTERNATIVE_CLOSURE_REQUIRED` forces the
restrictive outcome after a closure-qualified witness exists. The positive
outcome requires every present member to have current positive trust. Missing
resolution/publication evidence, malformed partition or no closure-qualified
record rejects the checkpoint before outcome selection; none is a third success
outcome.

The assessment also derives exactly one canonical closure-proof record. A
qualified permanent-isolation record dominates. Otherwise it selects the first
closure-qualified origin in this fixed order:
`LOCAL_ROLE_COMPLETION |
SOURCE_PENDING_NEVER_LIVE |
SOURCE_WHOLE_ROOT_FINAL_RETIREMENT |
SOURCE_WHOLE_ROOT_EMERGENCY |
FINITE_ROLE_HORIZON_ELAPSED`. It skips an untrusted record but never removes its
restrictive dominance. Because each origin key is unique, the result is total and
unique whenever closure is proved. The assessment binds the evaluator
schema/digest, selected origin/record and matching role-evidence branch. A
caller-selected priority, omitted retained record, alternate branch or different
arrival order for the same final set rejects.

The post-CAS target-history commit resolves that identity
to the accepted receipt bytes. Loss or reconstruction from remote replies retires the
target; map exhaustion denies acceptance. Its
checkpoint terminal branch is
`NO_ACCEPTED_GRANT_IN_SOURCE_GENERATION | TERMINAL_GRANT_HISTORY`. The first
branch proves a complete canceled, expired or never-accepted request partition
and cannot widen an inherited policy. The second binds the complete terminal
grant lineages, server receipts, boundary obligations and policy assessments;
the published phase additionally binds their final results.
Ordinary grant termination co-mutates only its exact aggregation entry to bind a
receipt-free `ObserverGrantAuthorizationClosureDecisionCommitment`; member
lattice state stays unchanged until post-CAS evidence exists. Final ALLOW/FORBID
results enter only through checkpoint publication.
Every mutation emits `ObserverAttachmentTargetHistoryCommitReceipt` over exact
prior/installed registry heads, selector identity/incarnation/version, operation,
receipt-free mutation commitment and common
`AuthorityTransactionCommitReceipt`. Specialized acceptance, terminal,
reconciliation, aggregation, checkpoint and retirement receipts bind it.
Candidates exclude it; the post-CAS bundle uses it to resolve preallocated
accepted-result and terminal-decision receipt identities.

The same realm owns the bounded ADR-001
`ObserverUnresolvedTargetQuarantineHead` through
`InstalledObserverUnresolvedTargetQuarantineSelector`, registered as
`OBSERVER_UNRESOLVED_TARGET_QUARANTINE` under that exact transaction domain.
Its root phase is `OPEN_QUARANTINE | DOMAIN_RETIREMENT_SEALED`. Its shard and
entry bounds, closed `SEALED_UNRESOLVED |
ARCHIVED_NONAUTHORIZING_TOMBSTONE` states, reserve accounting and archive-only
meaning are part of the observer manifest. Neither quarantine state can satisfy
challenge, attach, reattach, renewal, publication or closure.
No target-history or quarantine selector mutation is legal after its
`DOMAIN_RETIREMENT_SEALED` root installs. External
`RECORD_QUARANTINED_OBSERVER_TARGET_LATE_CLOSURE` remains legal because it is an
archive append outside selector currentness and grants no authority.

`ISSUE_OBSERVER_GRANT_REQUEST_FRESHNESS_CHALLENGE` is also the only first-claim
transition for a target in a source generation. It constructs the exact ADR-001
`AuthorityTransactionCASCondition` over the domain-state, source-lineage,
source-issuance-index, local-security, observer-authorization and target-history
participants. In one qualified authority-domain transaction it changes the
source-issuance-index and observer-authorization heads and either inserts an
absent target as `CURRENT_SOURCE_GENERATION`, advances a
`CHECKPOINT_PUBLISHED` target to that phase, or compares an entry already current
for the exact source generation. The published branch advances only when the
requested operation has exact immutable continuation-policy evidence: fresh
attach requires `ALLOW_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE` or proved no prior
accepted grant, and cross-generation reattach requires its exact terminal
predecessor, `REATTACH_ALLOWED` and publication receipt; that receipt already
binds the distributed-authorization and transport-quiescence receipts.
Historical ALLOW is evidence, never timeless authority. Before this challenge
CAS, exact `ObserverGrantContinuationAuthorizationTrustRevalidation` binds the
latest installed source-security head and cumulative incident root,
non-supersession, current manifest authorization and every closure/record/
manifest artifact used by either ALLOW branch. It permits positive continuation
only through unaffected current trust or a qualified pre-compromise anchor.
Missing/stale/restrictive/untrusted revalidation rejects without allocating a
slot.
Renewal cannot cross a source generation. An entry in either pending phase, a
current entry for another generation, or a forbidden policy rejects without
allocating a freshness slot. Request acceptance and every attach, renewal or
reattachment transition conditionally compare the same current global entry,
the exact source parent in `GENERATION_LIVE`, the exact observer child in ACTIVE
and the confirmation receipt bound into that child. Their candidate heads bind
the receipt-free CAS condition. Acceptance inserts the precharged aggregation
entry; terminalization binds only its decision commitment in the common
transaction. Their generic and specialized receipts depend on
the one `AuthorityTransactionCommitReceipt`; the final non-authorizing
persistence manifest attests the complete bundle. A
different domain/store incarnation, missing participant, stale pre-read or store
that cannot make these qualified transactional comparisons keeps observer
attachment disabled.

The authority performs authenticated target resolution, manifest authorization
and privacy-safe requested-set evaluation before that first-claim transaction.
An absent or unauthorized source produces the same bounded rejection class and
allocates no freshness slot, target-history entry or observer descriptor. The
proof exposed to the requester contains no global-map membership or topology
oracle.

Active observer retirement atomically moves the canonical complete claimed-
target set to `SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION` as
specified above. Its target set is a bijection over every claimed key, including
challenge-only, accepted-response-ambiguous, live, pending and terminal grant
branches, and over every accepted grant's complete boundary plan. After the
observer finalization CAS, its checkpoint facts and
`ObserverAttachmentTargetLineageCheckpointCandidateSetRoot` remain
stable even while remote closure is pending. Each accepted-grant candidate
snapshots its exact `ObserverGrantRoleCompletionState`; later target-history
updates can refine that snapshot only along the closed role-evidence lattice and
must preserve an ancestry proof to the candidate. A pending role state does not
block source-generation finalization, but it cannot authorize target checkpoint
publication. ADR-001 parent finalization consumes
that exact root, server cut and observer finalization receipt. It can finalize
the source and release or hand over a physical domain without waiting for an
observer boundary, distributed-closure receipt or transport drain. The source
successor consumes this durable pending root and parent receipt; it does not wait
for target publication. Every old grant and boundary authority is exact-source-
generation scoped, so it cannot authorize successor-generation bytes.

After the parent CAS,
`RECONCILE_OBSERVER_TARGET_HISTORY_AFTER_PARENT_FINALIZATION` consumes a
receipt-free `ObserverTargetHistoryParentFinalizationFact` over the immutable old
observer and parent finalization receipts and the complete
`ObserverAttachmentTargetLineageCheckpointCandidateSetRoot`. It
moves only that complete claimed-target set from
`SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION` to
`SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION`, preserves every
unrelated entry and emits `ObserverTargetHistoryParentFinalizationReceipt`.
Reply loss resumes from the exact installed global head. It never requires the
old parent head to remain current or to be the direct predecessor of a later
source generation.

Each pending target publishes independently. A receipt-free
`ObserverAttachmentTargetCheckpointPublicationFact` contains one closed
`ObserverAttachmentTargetPublicationRemoteEvidence` branch:
`NO_ACCEPTED_GRANT_NO_REMOTE_AUTHORITY |
TERMINAL_GRANT_HISTORY_COMPLETE_CLOSURE`. The no-grant branch requires the
complete canceled, expired or never-accepted request partition plus typed
nonmembership of every grant and boundary plan, and structurally forbids a
distributed-closure or transport-quiescence receipt. The terminal-history branch
requires the exact distributed-authorization-closure receipt and
`ObserverGrantTransportQuiescenceReceipt` for every accepted grant and boundary
plan, carried in the exact
`ProtectedObserverGrantClosureResultEnvelope / TRANSPORT_QUIESCENT` with its
publication manifest and passing verification, plus one exact
`ObserverGrantRoleClosureEvidenceCompleteRecordSetAssessment` and its exact canonical
`ObserverGrantRoleClosureEvidence` per accepted grant. That role evidence has
one closed branch derived from the complete installed record set:
`SOURCE_ROLE_CLOSURE_RECORDED |
LOCAL_ROLE_COMPLETION_RECORDED |
FINITE_ROLE_HORIZON_ELAPSED_RECORDED |
PERMANENT_ROLE_ISOLATION_RECORDED`. The source branch binds a retained
pending-never, whole-root emergency or final-retirement record and every
origin-required proof/receipt; local evidence may still be absent. The local
branch requires `VERIFIED_LOCAL_EVIDENCE_RETAINED`, the exact protected
`ProtectedObserverGrantRoleCompletionEvidenceEnvelope`, its manifest and passing
verification; a marker-mode plan also binds the installed ADR-009 lineage-close
receipt. The finite branch requires a retained finite-elapsed record for the
immutable `FINITE_ENFORCED_FINAL_BOUNDARY` plan and the commit-time proof at or
after its exact `derived_authority_final_boundary_not_after`, including
clock/restart and no-later-authority ancestry. The isolation branch binds only
qualified permanent role isolation. Cross-branch fields, a wall-clock sample,
elapsed lease alone or a mode tag are insufficient.
Each branch binds the installed record, matching
`ObserverGrantRoleClosureEvidenceRecordResolution`, exact
`ProtectedObserverGrantRoleClosureEvidenceResolutionEnvelope`,
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest`,
manifest-membership proof and passing verification. It also binds only its
origin's writer evidence: direct
pending-never uses `ObserverGrantRoleClosureEvidenceAdvanceReceipt` and the
pending-never proof;
local completion uses `ObserverGrantRoleCompletionRecordingReceipt`; whole-root,
finite and isolation reconciliation use
`ObserverGrantRoleSourceClosureReconciliationReceipt`. A nonapplicable writer
receipt is structurally forbidden.

The fact binds the complete assessment, its selected evidence, the exact
candidate, its applicable
immutable continuation-policy assessments, both old
finalization receipts, `ObserverTargetHistoryParentFinalizationReceipt` and the
currently pending
global entry. For a terminal grant, it deterministically derives final
`ObserverGrantReattachmentPolicyResult` and
`ObserverGrantFreshAttachPolicyResult` objects. Their closed results are
`REATTACH_ALLOWED | REATTACH_FORBIDDEN` and
`ALLOW_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE |
FORBID_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE`. An eligible assessment can become
ALLOW only because this fact proves all four cuts: no further server minting,
distributed authorization closure, transport quiescence and receiver-admission
closure. It additionally requires one exact
`ObserverGrantPositiveContinuationTrustEvidence`:
`UNAFFECTED_CURRENT_TRUST_DESCENDANT |
INDEPENDENT_PRECOMPROMISE_ANCHOR`, which covers the complete assessment and
every artifact, membership proof, verification, trust disposition, current
incident root and manifest-authorization re-read that it binds. ALLOW
additionally requires `COMPLETE_SET_POSITIVE_CONTINUATION_ELIGIBLE`.
`COMPLETE_SET_RESTRICTIVE_CONTINUATION_ONLY` can produce only FORBID, even when
a different canonical record proves closure. Missing a qualified witness
rejects before publication. A forbidden assessment remains forbidden. The
no-accepted-grant branch preserves an
inherited policy byte-for-byte, or records exact first-target history without
inventing a terminal-grant result. Then
`PUBLISH_OBSERVER_ATTACHMENT_TARGET_LINEAGE_CHECKPOINT` changes only that target
entry within the target registry to `CHECKPOINT_PUBLISHED`; as every qualified
transaction, it also advances the authority-domain state selector and reserve
accounting. Its receipt-free CAS condition compares the exact pending target,
current local-security selector, domain/store incarnation and publication
inputs. Its post-CAS
`ObserverAttachmentTargetLineageCheckpointReceipt` binds the fact and exact
prior/installed global heads, authority-transaction commit receipt and installed
final policy results. Late
publication compares only the still-pending
target entry and immutable retained ancestry; source generations may have
advanced or been skipped. While the entry remains pending before permanent
source retirement, only that stable realm/source-kind/source-ID/requester target
remains attach-blocked until publication. A sealed permanent tombstone never
publishes and remains permanently non-authorizing. Unrelated targets and control
work have no dependency on its closure and remain available within their
manifest-reserved realm/source/principal quota; finite global capacity is not an
unbounded availability claim. A parent generation aborted before child activation
created no target entry and preserves its inherited checkpoint root byte-for-
byte; it needs no target-history publication branch. Registry exhaustion denies
a new target and never evicts a pending entry or history needed to enforce a
policy result.

ADR-001 permanent source retirement is a separate terminal choice after the
source lineage has no successor. Its receipt-free
`SourceLogicalSessionRetirementPreparationFact` binds the stable complete target-
key/immutable-ancestry set, not a publication-versus-seal classification.
For a finalized source, every member must first pass
`RECONCILE_OBSERVER_TARGET_HISTORY_AFTER_PARENT_FINALIZATION` and be
`SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION |
CHECKPOINT_PUBLISHED`; preparation does not freeze which of those two phases will
win later. Checkpoint publication remains legal after preparation. At
`FINALIZE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT`, the one authority-domain
transaction compares the current domain, namespace, lineage, target-history and
quarantine selectors plus the applicable local-security selector and derives the exact complete
`ObserverSourceTargetRetirementBranch` partition. A target currently
`CHECKPOINT_PUBLISHED` becomes
`SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE`. A still-pending target executes
`SEAL_UNRESOLVED_OBSERVER_TARGETS` only from exact
`SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION`, installs its exact
quarantine entry and
becomes `SOURCE_PERMANENTLY_RETIRED_SEALED_UNRESOLVED_TOMBSTONE`. These branches
are tombstones, not attachable history. Publication-first is retained as
published at terminal retirement; seal-first makes every stale publication CAS
lose.

The event consumes ADR-001 receipt-free
`SourceLogicalSessionPermanentRetirementFact`, which binds that current complete
partition, intended quarantine/tombstone projections, exact mutation inventory
and prior participant heads while excluding candidates and receipts. Every
mutated observer-owned candidate binds the fact and common CAS condition. The
post-commit source retirement receipt depends on the authority transaction
receipt; it cannot appear in any candidate or quarantine tombstone.

The same fact binds the exact current
`ObserverGrantSourceIssuanceIndexHead`, selector and one receipt-free
`ObserverGrantSourceIssuanceIndexFinalizationAssessment`. The assessment binds
the canonical complete retained source-generation set and two disjoint
bijections. Every challenge-bearing freshness slot in every generation maps to
exactly one `CHALLENGE_ISSUED` entry and back. Every generation-local
absent-intent cancellation tombstone maps to exactly one
`CANCELED_BEFORE_ISSUANCE` entry and back. Each issued entry binds its retained
slot, exact terminal or accepted-grant closure ancestry and delivery-gate
history; each canceled entry binds its immutable no-challenge tombstone. Every
anchor-profile issued entry also maps bijectively to either typed absence of an
admission record from an always-pending slot that became terminal before
admission, or its one immutable admitted record and terminal writer partition.
No `AVAILABLE`, pending writer, live admitted queue record or accepted grant
without complete closure is eligible. The assessment also proves that every
challenge exposure/outbox/replica writer is in the same compared transaction
domain or permanently terminal, and that the in-flight exposure set is empty. A
missing generation, slot, index member, proof node, admission record, writer or
closure makes final retirement ineligible.

`ObserverGrantSourceClosureAudienceAssessment` does not derive the eligible
audience from issued challenges, the current ADR-009 registry snapshot or
observed target history. It binds the source index's canonical complete
root-admission registry, partitions every entry exactly once as
`ELIGIBLE | PENDING_ANCHOR_ENROLLMENT |
CANCELED_BEFORE_SOURCE_CONFIRMATION`, and binds the canonical complete
eligible-observer-root subset with a bijection to every retained source-index
root-enrollment receipt/hierarchy. Each pending or canceled entry binds its
eligibility-publication hierarchy, capacity accounting and preallocated anchor
coordinate, and has no root-enrollment receipt. Entries remain after the corresponding
ADR-009 registration becomes retirement-pending or permanently retired; a
root-specific terminal return can narrow retained authority, but cannot erase
its need to resolve an older prepared intent. Enrollment and final freeze
compare the same source-index selector. Enrollment-first enters the complete
projection and consumes its precharged closure reserve. Freeze-first installs
`SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED`, so later source enrollment and
challenge issuance lose. In that same freeze CAS, every pending entry becomes
the retained nonauthorizing `FROZEN_BEFORE_SOURCE_CONFIRMATION` tombstone at
the same key, every already canceled entry remains byte-equal, and neither
terminal branch enters the closure audience. The assessment proves a bijection
from the pre-freeze pending/canceled partition to those frozen states. A lost
anchor notification therefore cannot block source freeze or disappear from the
frozen state. The possible anchor-side enrollment remains a bounded
independent-store orphan until exact anchor retirement or permanent
source-isolation closure. An already enrolled external root can still locally
PREPARE while disconnected because no cross-store CAS can order that action
against source freeze; it is already in the closure audience and resolves the
new stable key against the same frozen root. Once that root imports the verified
namespace closure into its sole local admission selector, every later PREPARE
loses locally; a PREPARE that won first appears in the closure-import partition.
A root without the verified source-index enrollment hierarchy was never
eligible to PREPARE and is not silently added to the closure audience.

The fact binds the intended frozen-index semantic projection, exact
mutation/count/capacity delta, one never-reused
`ObserverGrantSourceIssuanceNamespaceClosureReceipt` identity with storage
reserve, and that assessed complete eligible-root set. It does not contain the
frozen successor candidate or any receipt body. For a nonempty eligible set, it
also preallocates one protected closure-envelope identity per member, one family
identity and complete hierarchy/retention/retry reserve. The producer inventory
then has exactly four cases. A source-only profile with an empty eligible set
has no family, pre-manifest or completion. A source-only profile with a
nonempty eligible set has only the observer-closure family. An anchor profile
with an empty eligible set has only the cooperative anchor-retirement family.
An anchor profile with a nonempty eligible set has those two disjoint families.
Every nonempty case preallocates one shared pre-manifest and one mandatory
producer completion over the exact family set. No case creates a per-family
completion or an empty family.
`ObserverGrantSourceIssuanceIndexFinalizationCandidate` binds the fact and
common CAS-condition digests, prior source-index selector/head and resulting
frozen projection; it excludes installed coordinates and every receipt. The
same authority-domain CAS installs that candidate and changes the source index
to
`SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED` while it installs the lineage and
namespace tombstones. Issuance, acceptance, source restart and successor
allocation all compare that index or lineage; retirement-first makes them lose.
The post-CAS closure receipt binds the fact, finalization candidate,
prior/frozen index heads/selectors, final root,
count and proof-node root, generation/inventory assessment, lineage and
namespace tombstones, frozen eligible-root set, no-successor result,
frozen pending/canceled root-admission set, source-retirement receipt and common
transaction receipt.

One receipt-free
`ObserverGrantSourceIssuanceNamespaceClosureProjection` per eligible observer
root binds the closure-receipt digest, source-retirement commit digest, frozen
root, fixed capacity class, salted hiding count commitment, sparse-Merkle suite,
namespace/lineage tombstones, exact audience and operation. It excludes the
exact count, proof-node root and private count salt. Its
`ProtectedObserverGrantSourceIssuanceNamespaceClosureEnvelope` uses
`PERMANENT_CLOSURE_TOMBSTONE / SINGLE_REGISTERED_EXTERNAL_ROOT`.
For a nonempty producer inventory, one
`CrossStoreProducerPreManifestBundleCommitment` and its retained private opening
bind the exact retirement/closure receipt-sidecar set, eligible-root envelope
set, optional cooperative anchor-retirement envelope, exact one-or-two-family
inventory, fixed capacity policy and `PREDECESSOR_INSTALLED` credential
selection before any manifest is authenticated.
`ObserverGrantSourceIssuanceNamespaceClosurePublicationManifest` owns the one
deterministic observer family when that family is nonempty.
`SourceLogicalSessionCooperativeAnchorRetirementPublicationManifest` owns the
one anchor family under the anchor profile. The mandatory shared completion
authenticates the exact nonempty family set last. The immutable producer
retention record, hierarchy and exact retry bytes
become durable before exposure. A proved-empty eligible audience set emits no
observer-closure family; under the anchor profile it still emits the mandatory
anchor family and shared producer hierarchy. Later stable-key queries return this
immutable closure hierarchy plus one deterministic unsigned
`ObserverGrantSourceIssuanceStableKeyNoChallengeProof`:
`FROZEN_KEY_NONMEMBERSHIP |
FROZEN_CANCELED_BEFORE_ISSUANCE_MEMBERSHIP`. The first contains the exact
nonmembership proof. The second contains the exact membership proof, canonical
`CANCELED_BEFORE_ISSUANCE` entry and its bound local no-challenge tombstone.
`CHALLENGE_ISSUED` is forbidden in this proof and must use the exact retained
slot/grant terminal-result path. Queries create no receipt, signature, manifest
or authority mutation. The source never signs an arbitrary post-retirement
absence query.

Subordinate
`RECLAIM_SOURCE_OBSERVER_TARGET_HISTORY_DURING_PERMANENT_RETIREMENT` compacts
only hot target payload covered by that same complete partition. It retains each
bounded target key, its terminal phase and either publication evidence or exact
quarantine commitment. The same commit installs the source-lineage and namespace
permanent tombstones. Its `AuthorityTransactionCommitReceipt` precedes the
observer, target, quarantine, lineage and namespace receipts; the final
non-authorizing persistence manifest attests the complete crash-visible bundle.
No remote I/O occurs while this transaction is open. A missing key, extra key,
changed immutable ancestry, quarantine-capacity shortfall or transaction-domain
mismatch rejects the whole terminal event and consumes no state.

A sealed quarantine target can never publish or authorize attach. Later exact
remote closure creates only authenticated, content-addressed, deduplicated
`ObserverQuarantineLateClosureEvidence` through external archive event
`RECORD_QUARANTINED_OBSERVER_TARGET_LATE_CLOSURE` with
`ARCHIVE_ENRICHMENT_ONLY_NO_AUTHORITY`. That append is outside selector
currentness and remains possible after authority-domain retirement; it changes
no policy or closure state. Before domain retirement, exact
`ARCHIVE_AND_RECLAIM_OBSERVER_QUARANTINE_ENTRY` can compact a verified archived
payload to `ARCHIVED_NONAUTHORIZING_TOMBSTONE`, retaining the permanent key and
archive proof. Quarantine and retained tombstone caps are finite. Approaching
them consumes the domain's reserved closure path and retires the realm; it never
evicts an unresolved obligation to accept another target.

Initial attach requires no prior current-generation grant lineage for that
target. An absent target is first history. A published target requires either
proved no accepted predecessor grant or an explicit
`ALLOW_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE` result over the latest terminal
predecessor and closure. A current-generation target claimed only by canceled or
expired unused requests can retry after the complete map proves no nonterminal
operation; it does not reset inherited policy. Any retained current-generation
terminal predecessor forces REATTACH. Any checkpoint result other than explicit
ALLOW, including one derived from `REATTACH_FORBIDDEN`, cannot be bypassed with a
fresh key or initial-attach kind. Either permanent source tombstone phase rejects
every challenge/attach operation; map absence cannot bypass the matching
permanently retired namespace entry. Renewal requires its one exact current live
predecessor and no other nonterminal operation. Reattachment requires its exact
latest terminal predecessor and no other nonterminal operation. A current-
generation predecessor uses its eligible assessment plus both closure receipts;
a cross-generation predecessor uses its exact published result and publication
receipt. A canceled or expired unused request entry is retained history but not
an active conflict. A consumed entry remains a conflict until the exact accepted
grant has required closure. The winning transaction recomputes this complete
cross-key predicate; a caller summary, partial scan, different stable key or
stale proof rejects.

The authority then constructs a receipt-free
`ObserverGrantRequestFreshnessChallengeCommitment`. It binds authority and
never-used incarnation; authenticated requester; descriptor, session,
generation, security and revocation; complete intent/digest; literal operation,
stream, route, boundary, destination and audience scope; requested maximum
duration; nonempty `ObserverGrantDurationCeilingSetRoot`; applicable
target/predecessor and preallocated successor lineage; stable key, challenge,
principal sequence, clock/issue anchor, both exclusive cutoffs, qualified
dispatch bound, one-use slot and capacity. Under the independent-anchor profile
it also binds the never-reused
`ObserverGrantPairedChallengeFrameAdmissionKey`; the source-only profile
structurally forbids that field. It also binds one closed
`ObserverGrantRequestContinuationTrustProfile`:
`HISTORICAL_ALLOW_REVALIDATED |
NO_HISTORICAL_ALLOW_REVALIDATION_APPLICABLE`. Historical-ALLOW fresh attach or
either reattach origin selects the first and binds the exact current
`ObserverGrantContinuationAuthorizationTrustRevalidation` digest and
security/incident/manifest-authorization coordinate. First history, proved no
accepted predecessor and renewal select the second and structurally forbid that
evidence. Cross-branch fields reject. Its operation kind is exactly
`ATTACH_LOGICAL_TARGET | RENEW_EXACT_PREDECESSOR |
REATTACH_EXACT_TERMINAL_PREDECESSOR`. It excludes successors, selector, commits
and export. Unknown, wildcard, mismatch or caller-selected current state rejects.
Renewal binds the live predecessor and its original cutoff; reattachment binds
the terminal predecessor, `ObserverGrantReattachmentOriginEvidence` and exact
branch fields. Initial attach resolves the current generation, descriptor,
security, declarations and boundaries at the authority.

The granted subset cannot exceed the literal request or default-deny manifest.
`REQUIRE_EXACT_REQUESTED_SET` rejects any ungrantable member.
`ALLOW_EXPLICIT_PARTIAL` has one canonical
`ObserverGrantRequestedMemberDecision` per request:
`GRANTED | DENIED(reason) | UNAVAILABLE(reason)`. Every downstream artifact
binds the complete root/count. GRANTED carries only the resolved member; DENIED
only `DENIED_OR_NOT_DISCLOSABLE`; UNAVAILABLE only
`NOT_CURRENTLY_AVAILABLE`. Variants are disjoint and expose no hidden member,
free text or internal detail. The authority selects all current IDs, sequence,
clock, cutoffs and slot.

Issuance validates authenticated principal/session and aggregate attachment
quotas and bounded intent before semantic grant allocation. Absent, ambiguous,
unauthorized or non-live targets reject without a slot, challenge or topology
disclosure. One authority-domain transaction recomputes target exclusivity,
read-compares the open source-issuance-index selector, and atomically installs
the source-index entry plus the commitment as an `AVAILABLE` slot. It installs
`DIRECT_DELIVERY_READY` for the source-only profile or
`ANCHOR_PAIRED_FRAME_PENDING` plus its reserved admission-registry capacity for
the anchor profile; two keys for one target cannot both win.

Under the common DAG, publication orders
`AuthorityTransactionCommitReceipt`, `ObserverAuthorizationStateCommitReceipt`,
`ObserverGrantRequestFreshnessRegistryCommitReceipt`, and
`ObserverGrantRequestFreshnessChallengeReceipt`. The specialized receipts bind
prior/installed heads, slot, commitment, selector, deadline evaluation,
authority/security state, selected continuation-trust profile/revalidation and
signing key. Exported
`ObserverGrantRequestFreshnessChallenge` binds the commitment/final receipt and
crosses stores only inside
`ProtectedObserverGrantRequestFreshnessChallengeEnvelope`, an ADR-009
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT` specialization
for the exact observer-admission root, principal, store, selector and
registration ancestry. The envelope binds the complete challenge bytes, both
server cutoffs, fixed validity ending at
`SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER`, source commit ancestry, signing
epoch/use, operation and one-use replay domain.

Under `SOURCE_RETIREMENT_ONLY`, the producer's one
`CrossStoreProducerPreManifestBundleCommitment` declares one deterministic
family. `ObserverGrantRequestFreshnessChallengePublicationManifest` owns the
observer-root challenge-envelope family. Under the independent-anchor profile,
receipt-free `ObserverGrantChallengeExposureAnchorCommitmentProjection` binds
only the stable-key digest, challenge-commitment digest, source-index
entry/commit digests, intended observer-root identity, preallocated paired-frame
admission key, deadlines and source-producer coordinate. It omits all challenge
secret bytes. Its
`ProtectedObserverGrantChallengeExposureAnchorCommitmentEnvelope` uses
`EPHEMERAL_AUTHORITY_WINDOW / INDEPENDENT_ANCHOR_AUTHORITY /
OBSERVER_GRANT_CHALLENGE_COMMITMENT` for the exact pre-enrolled independent
anchor, and
`ObserverGrantChallengeExposureAnchorCommitmentPublicationManifest` owns the
second family. The pre-manifest declares exactly those two families. Both
profiles use one shared producer completion, authenticated last, and one
immutable retention record. An omitted/unexpected family, wrong audience,
cross-family envelope, second same-family manifest or second completion rejects.

The observer verifies its selected family, shared completion, capsule and both
scoped proofs under its installed default-deny mirror before a local attempt.
The anchor verifies only its minimized family and the same completion.
Bare/wrong-audience/expired-at-equality/replayed/partially published input
rejects. The crash-complete source bundle exposes all or none. Under the anchor
profile, the observer-root capsule remains buffered until the independent anchor
append and paired-frame admission above succeed. Source-only same-key retry
returns its exact direct-delivery bytes. Anchor-profile retry returns no
challenge bytes while pending, the installed admission record's exact frame
while admitted, or only installed terminal/consumed commits after closure;
changed intent rejects. The challenge grants no release and acceptance rechecks
current state.

The commitment's `SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER` intent must be
strict-before at durable linearization. Checked arithmetic leaves the positive
submission budget before that cutoff and the qualified dispatch plus positive
boundary-preparation budgets before the fixed
`server_grant_installation_close`; equality, overflow, nonpositive or unavailable
residual rejects. This proves feasibility, not remote availability. A losing or
late issuance allocates and exposes nothing.
Under the independent-anchor profile, the same feasibility proof reserves the
qualified worst-case source publication, source-to-anchor dispatch, anchor CAS,
authentication, retention and two-capsule atomic-admission bounds before the
source acceptance cutoff. The qualified clock relation must cover that full
horizon. A missing bound, a nonpositive residual or a relation that cannot map
the cutoff rejects challenge issuance.
`EXPIRE_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE` requires an installed
AVAILABLE slot. Every cutoff derives from the original issue anchor and cannot
refresh on delivery, retry, query, cancellation, restart or conversion. Clock
restart changes all AVAILABLE slots and their delivery gates to
`CANCELED_UNUSED / DELIVERY_TERMINAL / AUTHORITY_CONTEXT_CUT` without mapping
their instants. The observer must resolve the old slot and use a new intent/key.

Request acceptance is the attach, renewal or reattachment registry transition
itself. The final `ObserverGrantRequestEnvelope` composes the byte-identical
intent, exported server challenge/receipt and installed local request-attempt
identity. Under the independent-anchor profile, it also carries the derived
anchor entry identity, member-projection digest, paired-frame admission key and
frame digest that local observer verification accepted. It does not carry the
source-audience envelope and adds no caller-selected semantic request field. The
winning transaction
authenticates the same principal, recomputes the complete intent digest and
challenge context, rejects any envelope field that does not derive exactly from
those objects, and read-compares
`InstalledObserverGrantSourceIssuanceIndexSelector` in
`SOURCE_ISSUANCE_OPEN` with the exact stable-key member bound by that slot. Under
the anchor profile it additionally consumes the separately retained
`ProtectedObserverGrantChallengeExposureAnchorAcceptanceAdmissionEnvelope`,
selected source family, anchor-producer completion, source-audience capsule and
both scoped proofs. It verifies them under
`SOURCE_NAMESPACE_INDEPENDENT_ANCHOR_RETURN /
PAIRED_FRAME_ACCEPTANCE_ADMISSION` and
requires their anchor entry, stable key, source challenge, admission key,
observer root and cutoff digests to match the request byte-for-byte. The
observer-root envelope cannot substitute. It also read-compares the same outer
head's installed `ObserverGrantPairedChallengeFrameAdmissionRecord`, requires
`ANCHOR_PAIRED_FRAME_ADMITTED`, and matches the record's frame, connection,
source and anchor capsule digests. It proves
the slot current and `AVAILABLE` with its profile-exact delivery gate, evaluates
`SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER` strictly before its fixed cutoff, and
atomically changes the slot to
`CONSUMED_BY_ACCEPTED_REQUEST / DELIVERY_TERMINAL` while installing the exact
pending grant entry. It recomputes target exclusivity against the
then-current complete maps; another issued/consumed operation or wrong
predecessor makes it lose. The installation plan uses the challenge issue
anchor as its original server-local request time and uses the challenge's
installation close byte-for-byte. It cannot choose, shorten or extend that
close. Equality or later selects no grant-registry mutation. A duplicate exact
request returns the installed accepted result; a
different request, principal, scope, predecessor, lineage, security context or
slot rejects. Source-index retirement-first makes this transaction lose.
Acceptance-first remains in the final source-index inventory and must reach its
exact terminal grant-closure branch before source retirement can finalize.
For `HISTORICAL_ALLOW_REVALIDATED`, acceptance recomputes a fresh
`ObserverGrantContinuationAuthorizationTrustRevalidation`; the pending-grant
candidate and receipts bind the winning digest and
security/incident/manifest-authorization coordinate. A change after challenge
issuance therefore loses or revalidates under the new state. The inapplicable
branch cannot import historical evidence.
Renewal acceptance additionally evaluates the unchanged current predecessor's
`SERVER_GRANT_NOT_AFTER` strictly before in the same server transaction. The
observer independently evaluates its receiver-local predecessor deadline; no
numeric instant from those clock domains is compared without the qualified
mapping described below.

Before cancellation, the server constructs a receipt-free
`ObserverGrantRequestFreshnessCancellationFact`. Its closed origin is
`ABSENT_INTENT_TOMBSTONE | AVAILABLE_CHALLENGE_CANCELED`. The absent variant
binds the authenticated intent/key, exact current outer and freshness-registry
heads, exact open source-index head, stable-key nonmembership, intended
`CANCELED_BEFORE_ISSUANCE` source-index entry, reserved capacity units and cause,
and forbids challenge/slot fields. The available variant binds the exact
installed `CHALLENGE_ISSUED` source-index member, commitment/slot, current
delivery gate, current heads and cause. `DIRECT_DELIVERY_READY` forbids an
admission record. `ANCHOR_PAIRED_FRAME_PENDING` binds the reserved admission key
and typed record absence.
`ANCHOR_PAIRED_FRAME_ADMITTED` binds the byte-equal installed admission record
and does not claim nonexposure. Both variants exclude successor heads, selector
versions, commits and receipts. The candidate freshness-registry, outer and
applicable source-index successors bind that fact.

Cancellation and issuance/acceptance race in the same authority domain over the
outer and source-index selectors. Paired-frame admission races them through the
same outer selector. A winning cancel consumes that fact's exact stable-key
nonmembership or `AVAILABLE` state and installs
`CANCELED_UNUSED / DELIVERY_TERMINAL`
with one closed cause
`REQUESTER_CANCELED | CURRENT_CONTEXT_REJECTED | AUTHORITY_CONTEXT_CUT`. The
absent origin atomically appends `CANCELED_BEFORE_ISSUANCE`, binds the exact
intent/stable key and consumes both reserved capacity units, but structurally
forbids challenge, challenge receipt and server slot fields. The available
origin preserves the issued source-index member and terminalizes the exact
installed commitment/slot. Elapsed expiry installs `EXPIRED_UNUSED` only
after an at-or-after evaluation of the same
fixed cutoff. Both preserve proof that no grant entry was installed for that
slot. An absent-to-canceled tombstone closes a prepared intent even when a
challenge-issuance request or response was delayed; later issuance for that key
loses. If acceptance won first, cancel or expiry returns the exact accepted grant
key/head and cannot report noninstallation; the caller must use normal
termination and distributed closure. Query returns the exact closed slot state
and delivery gate. For anchor-profile
`AVAILABLE / ANCHOR_PAIRED_FRAME_PENDING`, it returns only the non-secret
pending status. For `AVAILABLE / ANCHOR_PAIRED_FRAME_ADMITTED`, it returns only
the installed admission record's exact frame. For source-only
`AVAILABLE / DIRECT_DELIVERY_READY`, it returns the exact direct hierarchy.
Every terminal/consumed state returns its receipt and no new challenge frame.
Query is read-only and cannot consume, refresh or reclassify a slot. Loss of unresolved slot state,
receipt, retained slot or tombstone retires the affected session generation; it cannot
be interpreted as absence. A requester cannot acquire a successor challenge for
the same operation/target until the prior slot is terminal or its accepted
grant has the required closure evidence.

Under the common DAG, every freshness mutation emits
`ObserverGrantRequestFreshnessRegistryCommitReceipt` over exact prior/installed
slot, registry and outer heads, edge, cause, selector version and outer receipt.
Acceptance also emits the ordinary grant-registry commit in that transaction.
Query returns installed commits, never an invented result; a challenge receipt
exists only for winning issuance and cannot replace a later terminal/consumed
commit.

After a winning single or bulk `CANCELED_UNUSED | EXPIRED_UNUSED` producer fixes
its coordinates, its fact preallocates one envelope identity per terminalized
slot, one opaque family-manifest identity, one distinct completion-manifest
identity, exact count and reserve. The signer
creates one observer-audience
`ProtectedObserverGrantTerminalResultEnvelope` unused-slot branch per member.
Each binds the exact slot/heads/commits, stable key, request intent, result
commitment, operation and projection, and excludes the later
`ObserverGrantRequestSlotTerminalPublicationManifest`. One
`CrossStoreProducerPreManifestBundleCommitment` binds the complete
slot-to-envelope bijection and receipts. One named family manifest owns that
entire deterministic family; a single transition is its one-member shape. The
mandatory completion manifest authenticates the one-family set last. A bulk
restart never emits per-slot family manifests. A second manifest for the same
family, an extra family or a second completion rejects. Candidates and
installed heads exclude later artifacts. Exact query or retry returns only the
authorized member, its family manifest, the shared completion manifest and the
two-proof delivery capsule. A missing completion, unmanifested or bare commit
cannot resolve observer state.

Coordinator-clock restart uses receipt-free
`ObserverAuthorizationClockRestartTransitionFact` through the same outer
selector. It partitions every freshness slot exactly, changes every `AVAILABLE`
member to `CANCELED_UNUSED` without mapping its cutoffs, preserves unused
terminal members, and links every consumed member to its exact grant branch. It
binds one complete `ObserverAuthorizationClockRestartMap`. Each
`ObserverAuthorizationClockRestartMapEntry` has closed kind
`OBSERVER_AUTHORITY_CUTOFF | OBSERVER_DISTRIBUTED_CLOSURE_HORIZON`. For every
authority-capable PENDING or LIVE grant, the cutoff entry maps each authorization
deadline to its exact conservative lower/earlier image and selects
`OBSERVER_AUTHORITY_CUTOFF_LOWER_IMAGE`; if unavailable, the same CAS selects
`OBSERVER_AUTHORITY_TERMINALIZED_ON_UNMAPPABLE_RESTART`, terminalizes the grant
with `AUTHORITY_CLOCK_DISCONTINUITY` and, when required, retires the generation.
Already TERMINAL-but-not-distributed-closed heads remain byte-for-byte and bind
typed cutoff inapplicability. For every accepted PENDING, LIVE or such TERMINAL
grant, and every retained consumed
`SERVER_RENEWAL_PREDECESSOR_FENCE` predecessor without distributed closure, a
separate closure entry keyed by exact historical grant/plan/issuance maps that
plan's exact original
`min(SERVER_GRANT_NOT_AFTER, server request time +
maximum_boundary_revocation_lag)` effective closure horizon to its exact
upper/later image and selects
`OBSERVER_DISTRIBUTED_CLOSURE_HORIZON_UPPER_IMAGE`; if unavailable it selects
`OBSERVER_CLOSURE_ACK_REQUIRED_ON_UNMAPPABLE_RESTART`, which permanently
forbids deadline-elapsed closure for that member but permits an exact terminal,
no-install, never-LIVE or qualified permanent-isolation proof. Entries bind
field/grant key, both clock incarnations,
applicability horizons, correlated uncertainty, rounding and checked result;
they cannot merge or exchange polarity.
Consumed renewal predecessors bind cutoff inapplicability and remain in the map
until their own closure receipt; a G0/G1 horizon substitution rejects.

The installed restart commit binds the complete map and retains exact ancestry
from each original plan clock through every later incarnation. A protected LIVE
response/boundary decision binds that lower-purpose ancestry and original source
expiry; verification uses the original relation or exact composition, never an
S1 instant in S0. A multi-key clock/descriptor/privacy/security/session cut has
one receipt-free `ObserverGrantTerminalTransitionFact` per exact key and a
complete candidate set. Under the common bundle it emits the shared
`ObserverAuthorizationClockRestartCommitReceipt` when applicable and one
crash-complete `ObserverGrantTerminalTransitionReceipt` per key. Missing restore
or per-key closure evidence keeps attach, renewal and activation closed.

`ObserverGrant` binds:

- the exact authenticated requester principal, descriptor revision, and descriptor
  digest;
- the exact neutral `AuthorityRealmKey`, source session kind, logical session,
  generation, security-state digest, security epoch and current revocation epoch;
- a finite set of exact scope entries. Each entry binds one indivisible
  operation/declared-stream-digest/plane/literal-route/message-class/channel/
  extension/delivery-boundary-member tuple;
- for `history_query`, one bounded requested window within the descriptor's
  authorized history window;
- a never-reused grant ID and grant-lineage incarnation, fresh body-issued
  issuance nonce, strictly increasing issuance sequence, issuance-context digest,
  issue/expiry UTC audit times, exact positive `granted_live_duration`, the
  unchanged requested duration and ceiling-set root, and server/observer
  deadline-policy identifiers; and
- the exact observer-generated operation challenge, server-issued request-
  freshness challenge and receipt, and operation context; and
- the canonical source-local ADR-009 target-set root/count and public target
  roster: exactly the observer-admission root and every boundary root in the
  installation plan. The grant does not embed sibling plans, projections,
  currentness bundles, ledger ancestry or receipts. Each target receives only
  its own member and membership proofs.

Before any grant allocation, checked source-clock arithmetic requires
`0 < granted_live_duration <= requested maximum duration`, no greater than any
member of the bound ceiling set, and
`SERVER_GRANT_NOT_AFTER = challenge issue anchor + granted_live_duration`.
Equality with a ceiling is valid; zero, omission, overflow or a later cutoff
rejects. The grant core, installation plan, source-result commitment, protected
target grant envelopes and accepted LIVE response bind this same tuple. UTC
expiry is audit data and cannot replace it. Thus narrowing is explicit and
authenticated, while retry, dispatch delay and response delay cannot widen the
requested or policy lifetime.

The canonical grant does not contain its own digest, signature/receipt, a
successor head, or either enforcement boundary's numeric deadline. A protected
body/service envelope carries its recomputed digest and signature/receipt. The
grant binds one receipt-free `ObserverGrantBoundaryInstallationPlan`. The plan
is constructed first from the attach/renew/reattach request, stable
`ObserverGrantRegistryKey`, accepted request-freshness slot, proposed issuance
sequence/context, and candidate
grant fields that do not depend on the plan. It does not contain the grant
digest, derived full `TrustedDeliveryBoundaryGrantKey`, any grant-registry or
keyed ledger head, a selector or commit receipt, a boundary receipt, an
activation commitment, or an activation-set receipt. The sealed grant then binds
the plan; its digest derives the full boundary key; and the server pending chain
binds that key. This order prevents a plan/grant fixed point.

After the boundary plan, the server constructs
`ExternalSecurityDerivedAuthorityGrantCore`, one ADR-009
`ExternalSecurityDerivedAuthorityGrantPlan` for the observer root and one for
every enumerated boundary root, then seals their
`ExternalSecurityDerivedAuthorityGrantTargetSetCommitment`. Each member binds
boundary-plan/grant-core digests, exact registered target, least-authority
`ExternalSecurityDerivedAuthorityTargetProjection`, unique security-currentness
deadline intent and receipt-free
`ExternalDerivedAuthorityLocalWorkLineageCommitment`, expected prior
target-ledger head/version/next sequence and closed finite/local-terminal mode;
it excludes future grant digest, candidates, installed heads and receipts. The
sealed grant binds plan, core and target-set root/count, not member bodies. The
retained set then yields
`ExternalSecurityDerivedAuthoritySourceResultCommitment` over that grant and
pending source projection. Server/ledger candidates bind it, the deadline-intent
root and own member without cross-binding. Full work keys derive after the grant
digest from their pre-grant lineage commitment; closure maps each to its installed
key or exact no-install tombstone.

The issuance transaction uses ADR-009
`ExternalSecurityDerivedAuthorityGrantReadConditionSet`, not a global-only
check. At one source-store linearization point it read-validates the global
security selector and every target's per-key currentness bundle, then
compare-and-swaps the observer-authorization selector and every target's
`InstalledExternalSecurityDerivedAuthorityGrantLedgerSelector`. The common
condition binds all candidates, one ADR-009 currentness-expiry intent per target
and exact ADR-004
`SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER` intent. The transaction evaluates
both sets there; equality expires. Evaluation roots bind common/observer/ledger/
specialized receipts and manifest, never candidates. The common receipt precedes
all commits. Partial sets, cross-audience replay, split stores or unqualified
serializability reject. The common DAG order is plans/core -> target set -> sealed
grant -> source result -> candidates -> common/generic commits -> specialized
receipts -> source receipt set -> target envelopes -> manifest; generic commits
exclude the later set.

The pending head binds the grant/target-set root, not post-CAS receipts. The
source retains the complete receipt set; each single-root envelope exposes only
its plan/projection, common transaction coordinate and two ADR-009
`CrossStoreManifestMemberPrivacyProjection` membership proofs. Exact
roots/counts remain source-local; the default hiding branch exposes only fixed
capacity class, padded roots and hiding proofs. Exact count is legal only under
the unanimously authorized exact-topology branch.
Pending output authorizes boundary preparation only. It cannot install observer
admission, and the observer member remains local until the LIVE result.
External retirement, PREPARE,
emergency and grant issuance therefore have one source order. A global-only
condition, matching semantic digest/epoch, bare ledger commit or before/after
check cannot issue a conforming attach, renewal or reattachment grant.

After the server installs the keyed grant in
`PENDING_BOUNDARY_INSTALLATION`, each enumerated boundary first constructs a
receipt-free `TrustedDeliveryBoundaryGrantPreparationFact`. The fact binds the
grant digest, descriptor revision, observer challenge and operation context,
the boundary member's ADR-009 protected grant envelope, passing cross-store
verification, target-plan and source-local-receipt-set membership proofs
through those exact privacy projections, common transaction coordinate,
that boundary's grant-ledger ancestry
and exact `TRUSTED_DELIVERY_BOUNDARY_MEMBER_SCOPE`
`ExternalSecurityDerivedAuthorityTargetProjection`,
exact grant-registry key, exact trusted enforcement-boundary principal and
never-reused instance, boundary security state, literal live-route or history-
provider delivery domain, deadline-policy identifier, original server-local
request time, derived `boundary_prepare_close` and
`boundary_release_not_after`, non-authorizing
`boundary_latest_server_activation_at`, and positive conservative boundary-clock
duration upper image `boundary_minimum_activation_budget_upper` in the exact
boundary clock incarnation, exact installed pending outer
authorization, grant-registry and keyed ledger heads, outer selector version,
the common authority-transaction commit receipt, outer commit receipt and
specialized registry commit receipt, and exact prior installed local
`TrustedDeliveryReleaseStateHead`, grant-map head and proof that the candidate
grant key is absent and never used. For renewal or replacement it also binds the
exact predecessor `ObserverGrantDistributedAuthorizationClosureReceipt` and,
when the same boundary member is preserved, a distinct cross-key predecessor
relation to the exact retained G0 `TERMINAL_BOUNDARY_GRANT` entry or its exact
`TRANSPORT_QUIESCENT_BOUNDARY_GRANT` descendant with terminal/closure ancestry.
The boundary recomputes that relation from the authenticated G0 heads, receipts,
and closure member. A caller-supplied source-grant or overlap digest is not
evidence.
The fact and every prepared/live candidate bind exactly that target projection;
the installed boundary authority is equal to or narrower than it. A full-grant
view, observer projection, sibling-boundary projection or tuple naming another
delivery member rejects before allocation.
Initial attach binds typed inapplicability. The new G1 entry starts at version 1;
the map CAS preserves the G0 sibling and every G0 item/drain byte-for-byte. It
contains no local successor head/map/entry,
selector version, local commit or enforcement receipt, server `LIVE` successor,
server registry commit, activation commitment, or activation-set receipt.

The common DAG installs the fact-bound non-releasing
`PREPARED_BOUNDARY_GRANT` entry, then its map and outer successors, through sole
`InstalledTrustedDeliveryReleaseSelector`.
`TrustedDeliveryReleaseStateCommitReceipt` binds the prior/installed outer heads
and selector version; the map commit binds the prior/installed map/entry heads.
`TrustedDeliveryBoundaryGrantEnforcementReceipt` binds the fact, grant/plan,
those exact local heads, selector and commits; both fixed deadlines; feasibility
and `boundary_minimum_activation_budget_upper`; the canonical
`BOUNDARY_GRANT_PREPARATION_CLOSE` and
`BOUNDARY_GRANT_RELEASE_NOT_AFTER` intents and commit-bound evaluations; and the
exact installed server pending outer/registry/keyed heads, selector and commits.
Both evaluations use one selected boundary-clock timing proof: one
transaction-manager linearization instant, or one trusted sample, hard bound and
enforcement result. The common crash-complete rule permits export only after the
whole bundle is durable.

The pending server entry commits the stable registry key, sealed-grant and plan
digests, derived full boundary key, coordinator clock policy/incarnation and
server deadline policy; every activation or terminal CAS verifies that exact
incarnation. The canonical grant excludes later server/boundary heads and
post-CAS receipts. The preparation fact and receipt name an exact descriptor-
and-grant scope member, commit strictly before `boundary_prepare_close`, and
activation remains strict-before `boundary_release_not_after`. A late-added or
merely reachable gateway, or a different grant lineage, gateway, provider,
boundary instance, security state, route/query domain, deadline policy, clock,
local predecessor or losing CAS, cannot substitute. The observer creates its
separate installation receipt in its own clock domain.

Each preparation, activation, terminal, drain or quiescence receipt uses the
exact boundary principal and a key current in its installed boundary security
state. Coordinator, shared-delivery-server, wrong-boundary or noncurrent keys
cannot mint boundary proof. Export uses ADR-009
`ProtectedCrossStoreSecurityReceiptEnvelope` with the artifact's exact class.
Normal retirement stops new signatures but preserves qualified historical
verification; ephemeral authority expires, compromise takes its conservative
disposition, and old receipts are never re-signed.

Grant activation closes the first-install lifetime gap. The grant binds one
`ObserverGrantBoundaryInstallationPlan` that enumerates the complete required
boundary set, the original attach/renew/reattach operation, server-local request
time copied byte-for-byte from the accepted freshness commitment's issue anchor,
exclusive server-local installation-close time and grant not-after, exact
coordinator clock policy/incarnation, the reviewed
positive `minimum_boundary_activation_budget`, the reviewed
`maximum_boundary_revocation_lag`, and for each boundary its exact clock
incarnation plus either a shared monotonic clock or an authenticated bounded no-
extension mapping from that coordinator incarnation into the boundary clock.
For a nonshared clock, the mapping evidence binds:

- one authenticated calibration reference in both clock incarnations;
- proof that the calibration/source receipt existed no later than the
  server-local request instant in that coordinator incarnation;
- one coordinator-clock source applicability horizon that covers every mapped
  source instant and duration endpoint from request time through
  `min(server grant not-after, server request time +
  maximum_boundary_revocation_lag)`;
- one boundary-clock target applicability horizon that covers every derived
  lower/no-later or upper/later image, duration image, and checked target-domain
  arithmetic result through `boundary_release_not_after`;
- correlated lower and upper offset bounds;
- positive rational minimum and maximum rate bounds;
- the exact rounding rule, qualification identity/digest, and source receipt.

An independently qualified clock mapping may provide conservative instant and
duration images. Every proof binds clock incarnations, source/target horizons,
correlation, qualification, source receipt, and a positive denominator. Free
numeric images reject. Mapped instants, duration anchors/endpoints, derived
images, and arithmetic results must remain in their respective horizons.
Absolute comparisons use one tagged clock incarnation. Duration images prove
`anchor + duration` in the source horizon before extrapolation.

Before allocating a grant, ledger head, boundary key, or reservation, one
coordinator-clock incarnation and checked arithmetic must prove:

- `server request time < server installation-close`
- `server installation-close + minimum_boundary_activation_budget <=
  min(server grant not-after, server request time +
  maximum_boundary_revocation_lag)`.

For each boundary:

- `boundary_prepare_close` is the conservative no-later installation-close image
- `boundary_release_not_after` is no later than both conservative no-later images
  of grant not-after and original request time plus
  `maximum_boundary_revocation_lag`
- `boundary_latest_server_activation_at` is the separate, non-authorizing
  conservative upper/later activation image
- `boundary_minimum_activation_budget_upper` is the positive conservative
  boundary-clock upper image of the minimum budget, using maximum qualified
  clock advance with rate and rounding uncertainty.

No-later images subtract all positive mapping uncertainty. Checked arithmetic
covers request-plus-lag, not-after plus lower offsets, rates, ceiling rounding,
and final sums. Preparation close is not a feasibility bound. Every member must
satisfy `boundary_prepare_close <= boundary_latest_server_activation_at <
boundary_release_not_after` and
`boundary_latest_server_activation_at +
boundary_minimum_activation_budget_upper <= boundary_release_not_after`.
Unknown, nonpositive, overflowing, uncertainty-erased, or inverted budgets and
windows reject before allocation. Request-time equality with exclusive
installation close rejects.

Both boundary deadlines derive from the original operation. Contact, activation,
retry, restart, and renewal response cannot refresh lifetime. Valid preparation
has a reviewed nominal nonzero activation window, without guaranteeing delivery
or partition availability. Immediate post-activation terminalization leaves at
most the reviewed lease, bounded by `maximum_boundary_revocation_lag`.

The keyed grant starts as `PENDING_BOUNDARY_INSTALLATION` and cannot release
bytes. Every enumerated boundary installs its preparation fact in a non-releasing
successor and emits the post-CAS enforcement receipt before its mapped exclusive
`boundary_prepare_close`. Preparation is a durable blocking promise. Before
`boundary_release_not_after`, a boundary can leave that state only by installing the
authenticated server activation or terminal decision through the same local
selector. It cannot time out from preparation, free the slot, or accept a
conflicting grant merely because the server is unreachable. At
`boundary_release_not_after`,
unresolved preparation expires and can never enable release. Restart restores the
exact prepared head, selector, and commit or releases no bytes; it queries the
keyed server decision and retires the affected grant/generation when durable state
is missing or ambiguous.

Receipt-free `ObserverGrantBoundaryInstallationCommitment` binds the exact
plan/grant, pending registry/keyed heads, canonical complete prepared-receipt
set, mapped deadlines, preallocated operation, deadline-intent-set root and
transition kind, plus the exact expected ADR-009
`ExternalSecurityDerivedAuthorityActivationReadConditionSet` over every target
plan member and its distinct
`RealmSecurityDeadlineConditionIntentSetRoot`, with exactly one
`CURRENTNESS_ENVELOPE_VALIDITY_NOT_AFTER` intent per selected latest target
envelope. Renewal/replacement also binds the exact predecessor
`ObserverGrantDistributedAuthorizationClosureReceipt`; genesis/new-lineage
attach binds typed inapplicability. It excludes the `LIVE` successor, installed
selector version, registry commit, activation-set receipt and later
`RealmSecurityDeadlineConditionEvaluationSetRoot`. It binds the exact
conditional output-family inventory, preallocated family/completion identities
and worst-case retention/retry reserve: the observer-response family always has
one member, while the boundary-decision family is present if and only if the
canonical complete boundary set is nonempty. Empty families are forbidden. The common DAG installs its
keyed `LIVE`, registry and outer successors through sole
`InstalledObserverAuthorizationStateSelector`, evaluating the canonical
`SERVER_GRANT_INSTALLATION_CLOSE` and `SERVER_GRANT_NOT_AFTER` intent pair; the
successors bind the intents and expected activation-read set, not a pre-CAS
instant or later validation result. The same transaction validates the complete
read-only global/per-target currentness set and evaluates every realm-security
deadline intent at the LIVE linearization point. Every selected envelope must
be strictly unexpired; equality rejects. The transaction does not append the
ADR-009 grant ledger again.

Publication orders `AuthorityTransactionCommitReceipt`,
`ObserverAuthorizationStateCommitReceipt`,
`ObserverGrantRegistryCommitReceipt`, then
`ObserverGrantBoundaryInstallationSetReceipt`. The latter binds the commitment,
complete prepared set, exact prior/installed outer/registry/keyed heads,
installed selector, all three earlier receipts and both commit-bound
server-deadline evaluations. It also binds the passing activation-read
validation, exact installed target-currentness coordinates and exact ADR-009
`RealmSecurityDeadlineConditionEvaluationSetRoot`. They share one
coordinator-clock timing proof: one
transaction-manager linearization instant, or one trusted sample, hard bound and
enforcement result. Equality with either deadline rejects.

After those coordinates commit, the signer creates one
`ProtectedTrustedDeliveryBoundaryGrantActivationDecisionEnvelope` per boundary
and one `ProtectedObserverGrantAcceptedResponseEnvelope`, each an ADR-009
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT`
`ProtectedCrossStoreSecurityReceiptEnvelope` specialization. Each binds the
`LIVE` heads/commits, activation guard/set receipt, expected activation-read
condition set and passing commit-time target-currentness coordinates,
the exact realm-security deadline-intent/evaluation roots,
its exact target member/projection, both target-set and source-receipt-set
ADR-009 privacy projections/member proofs, and common issuance coordinate, with
no sibling; the observer response
also binds duration. Key-use, replay, predecessor trust/security-manifest,
verification and bare-inner guards apply. Each expires at exact source-clock
`SERVER_GRANT_NOT_AFTER` and excludes its later family manifest. One
`CrossStoreProducerPreManifestBundleCommitment` binds the activation set,
boundary-envelope bijection, sole observer response, source commits, signer
ancestry, both deadline families and complete sidecar set.
`ObserverGrantActivationPublicationManifest` is the sole family manifest for
the observer response.
`TrustedDeliveryBoundaryGrantActivationPublicationManifest` is the sole family
manifest for every boundary-decision envelope and is absent exactly when the
boundary set is empty. The mandatory shared completion manifest authenticates
the exact one- or two-family set last. The common precharged hierarchy is
all-or-none, and no successor binds these post-CAS artifacts.

A boundary can enable release only after its composite state installs that exact
activation-set receipt; its already prepared `boundary_release_not_after` does
not change. An
unenumerated boundary, a missing mapping, a first preparation at or after close,
or an incomplete required set terminalizes the pending grant and sends the
audience-protected terminal decision to every enumerated boundary. A subset of
prepared receipts can never authorize any boundary.

Receipt-free `TrustedDeliveryBoundaryGrantActivationFact` binds the exact
protected decision envelope, passing
`CrossStoreSecurityReceiptVerificationEvidence`, inner set receipt,
`TrustedDeliveryBoundaryGrantActivationPublicationManifest`, shared completion
manifest, delivery capsule, both scoped membership proofs and authenticated
producer completeness assertion, target member/projection, grant key, prepared local
entry/map/outer/selector/version, fixed deadlines, local-security condition and
operation. Its same-CAS clock proof keeps the local cutoff no later than the
conservative source-expiry image, with both cutoffs strict; the fact binds the
receipt-free `BOUNDARY_GRANT_RELEASE_NOT_AFTER` intent and excludes successors
and receipts. Under the common DAG, LIVE/map/outer successors bind it and
`TrustedDeliveryBoundaryGrantActivationReceipt` binds the fact, prior/installed
heads, selector, `TrustedDeliveryReleaseStateCommitReceipt`,
`TrustedDeliveryBoundaryGrantMapCommitReceipt`, envelope, manifest and
verification. The exact complete-set bijection is producer-conformance/auditor
evidence, not an ordinary receiver proof. Torn, missing, extra or wrong-member
publication rejects. Exact
PREPARED state/version, the original `boundary_release_not_after` and absence of
a higher local decision govern the race; `boundary_prepare_close` does not.

Pre-lock, pre-signature, pre-WAL, and pre-commit timestamps do not prove
deadline order. Every deadline-sensitive server, delivery-boundary, and observer
selector CAS therefore evaluates its authorization-linearization predicate in
the same serialized transaction.

The common deadline contract is:

| Artifact | Exact contract |
|---|---|
| receipt-free `AuthorizationDeadlineConditionIntent` | Closed purpose is `AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE | EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE`. Closed kind is `SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER | SERVER_GRANT_INSTALLATION_CLOSE | SERVER_GRANT_NOT_AFTER | BOUNDARY_GRANT_PREPARATION_CLOSE | BOUNDARY_GRANT_RELEASE_NOT_AFTER | OBSERVER_GRANT_RESPONSE_CLOSE | OBSERVER_GRANT_ADMISSION_NOT_AFTER | OBSERVER_RENEWAL_PREDECESSOR_ADMISSION_NOT_AFTER`. Bind store, authority, transition kind, operation, expected prior state/head/selector version, security state, authenticated clock incarnation, deadline, comparator, and proof profile. Exclude samples, results, successors, installed selector versions, commits, and receipts. |
| `AuthorizationDeadlineConditionIntentSetRoot` | Registered root over operation, store, ordered intent digests, and count. The fact, candidate, evaluation set, commits, and receipts reuse its exact staged digest. |
| `AuthorizationDeadlineTimingProof.TRANSACTION_MANAGER_LINEARIZATION` | One indivisible primitive assigns the trusted instant, evaluates all predicates, materializes evaluations and the dependent bundle, and installs the selector. Completion bound is exactly zero. Failure publishes no instant or result. |
| `AuthorizationDeadlineTimingProof.QUALIFIED_COMPLETION_BOUND` | Bind last trusted in-transaction sample, independently qualified hard bound through signing and durable commit, checked sum, qualification digest, and store-produced abort or final atomic-recheck evidence. Caller hashes do not qualify. |
| commit-bound `CommitTimeDeadlineCondition` | Bind exact intent, successor, selector, clock, proof branch, deadline, and result. One transaction/store/proof and canonical order covers the set and recomputes the intent/evaluation bijection. |
| `CommitTimeDeadlineEvaluationSetRoot` | Bind common context and ordered evaluations. Publication and specialized receipts bind it. Successors cannot bind results dependent on their own commit. |

The integrated intent profile binds its guarantee identity. The bounded profile
binds qualified bound, qualification-source digest, and enforcement policy, but
no later enforcement/abort/recheck result. Cross-branch fields reject. Facts and
candidates bind the complete intent root before CAS. The two proof branches each
have one atomic publication and linearization. Authorization uses strict `<`.
Expiry/terminalization uses `>=`. Equality and unknown, missing, extra,
duplicate, conflicting, or mismatched members reject.

The eight observer-authorization kinds above are exhaustive. Body-authority,
policy-window, retry-lifetime, retention, and quiescence deadlines use distinct
typed and digest-domained families, each with an owning-ADR closed purpose/kind
union and distinct intent/evaluation roots. Generic tuples, cross-family roots,
and labels without registered bytes reject. Static installation/currentness
evidence never replaces fresh commit-bound evaluation. Ad hoc or differently
domained set digests reject.

Exact uses are:

| Transition | Conditions |
|---|---|
| attach, renewal, reattachment acceptance and unaccepted-slot expiry | `SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER`, with elapsed form for expiry |
| server activation, expiry, and renewal begin | Activation uses `SERVER_GRANT_INSTALLATION_CLOSE` and `SERVER_GRANT_NOT_AFTER`. Expiry/renewal use the applicable predecessor not-after, with elapsed form for expiry. |
| boundary preparation | `BOUNDARY_GRANT_PREPARATION_CLOSE` and `BOUNDARY_GRANT_RELEASE_NOT_AFTER` |
| boundary activation, reservation, and outbox release | `BOUNDARY_GRANT_RELEASE_NOT_AFTER` |
| observer renewal begin | `OBSERVER_RENEWAL_PREDECESSOR_ADMISSION_NOT_AFTER` |
| observer installation/admission, local expiry, and expiry-only closure | applicable local conditions, with elapsed forms for expiry |

`QUALIFIED_COMPLETION_BOUND` requires checked
`sample + bound < exclusive deadline` or final atomic recheck. Overrun aborts.
Estimated/unbounded latency never qualifies. Only the integrated branch permits
zero. Unknown/default purpose or kind and absent/conflicting duplicate members
reject.

The common transition/publication contract is:

1. Preallocated identity, signer/key, clock, inputs, and recoverable bytes feed a
   closed crash-complete schema fixing intents/evaluations, generic commitment,
   publication/specialized receipts, outbox, protected exports, and manifest.
   `Post-CAS` denotes content order, not a later transaction. Nothing
   authoritative is exposed without the bundle.
2. Each selector mutation has one enumerated kind and receipt-free fact. The
   validator joins operation, heads/versions, evaluations, commitment, selector,
   receipts, outbox links, and one closed semantic-case ID. That ID also joins
   exact preimage, evidence variant/truth conditions, actor, deadline set
   including typed empty, target keys/foreign-key equalities, state edges,
   mutation/effect/version inventory, complete partitions, and receipt graph.
   The checker proves cases disjoint and complete. Type labels, opaque tags,
   asserted `complete`, event supersets, and unjoined actor/deadline strings
   cannot select state.
3. Dynamic members are an exact canonical key/digest bijection derived from the
   fact or installed inventory. Caller subsets/parallel tuples grant nothing.
   A terminal-root case binds the complete subordinate inventory and either
   terminalizes all nonterminal members through disjoint partitions or proves
   exact terminal/quiescent preservation. Finalization binds the same roots.
   Independent domain paths, or any live, pending, retryable, unresolved, or
   required-unretained member, reject.
4. Facts and candidates contain only pre-CAS content. Under one non-reentrant
   lock, the store validates selector/head/version and security/clock
   currentness, applies timing proof, freezes installed head/evaluations, and
   finally rechecks base identity/version. Callbacks cannot reenter or nest a
   mutation. A registry successor is exactly prior map plus the declared
   mutation, and its recomputed root equals the outer root.
5. Receipt-free `AuthorityTransitionOperationCommitment`, built after the
   candidate and before evaluation, binds store/authority, kind, operation,
   expected prior head/version, fact, complete candidate, intent root, and
   schema. Candidate and CAS condition exclude it. For ADR-001 realm-local
   events, it is `PostCandidateInstalledStateSidecar`, never
   `PreCASAuthoritySemanticCommitment`. The authority receipt/installed-state
   root binds it. Including it in the CAS condition creates a digest cycle.
6. Receipt-free `AuthorityTransitionGenericInstallationCommitment` binds that
   operation commitment, prior/installed heads, intent/evaluation roots, and new
   selector version. It excludes the future selector digest. It is an ADR-001
   `PostCandidateInstalledStateSidecar`, not a receipt. The installed selector
   binds it and the head.
7. Publication binds the selector through ADR-001
   `AuthorityTransactionCommitReceipt` for realm-local events or an independently
   qualified root-specific commit receipt for standalone boundary/consumer
   roots. Signed specialized receipts bind selector, installation commitment,
   publication receipt, evaluations, and specialized inputs.

The exact DAG is `intent -> fact -> candidate successor -> operation commitment
-> evaluation set -> generic installation commitment -> selector -> publication
receipt -> specialized receipt`. Direct dependencies are exactly directly bound
typed bytes/digests. Persistence ownership is not an edge. The checker rejects
missing, reversed, cyclic, and case-unjoined conditional edges.
`AuthorityTransitionGenericInstallationCommitment` is never exposed as a commit
receipt, and specialized receipts never precede publication. Historical
“generic commit” means this prepublication commitment unless it names an exact
`*CommitReceipt`.

Bounded construction builds the immutable bundle before publication. Integrated
construction builds the same bundle inside its indivisible primitive. Both have
one linearization, no partial visibility, canonical-copy or rejection of mutable
inputs, semantic-link validation during commit/recovery, and registered
artifact/schema domain separators. Exact-operation and exact-commitment retry
returns retained bytes. Conflicting retry rejects. Losing/faulted transactions
publish nothing. Candidates grant nothing, successors exclude later artifacts,
and post-commit work cannot mint missing artifacts.

Recovery requires committed exact signature bytes or formally qualified,
still-authorized deterministic signing material and capability. A key ID alone
cannot reproduce a receipt after rotation, disablement, or destruction. Recovery
validates the complete bundle and cannot choose a new time, key, identity,
signature, or lifetime. Missing/ambiguous state blocks or terminalizes, never
fabricates.

Boundary installation is blocking two-phase distribution, not a cross-store
transaction. Server `LIVE` is the durable coordinator decision and a bounded
lease, not an instantly revocable register. Every boundary is prepared and
releases only after its own composite installation, although installations may
be delayed or unavailable. This claims no subset authorization and fail-closed
confidentiality, not simultaneous availability. Attach/renew returns after the
coordinator decision. Progress is separate and never called atomic. Reply loss
queries the same head, commitment, and receipt without restarting time.

Local activation ends at fixed `boundary_release_not_after` or an earlier
restrictive CAS. Delay cannot extend it. Server terminalization starts
distributed fencing. Per-member closure requires exact terminal, no-install,
pending-never-LIVE, qualified-isolation, or original-deadline evidence. Faster
partition cutoff requires an independently qualified physical/network credential
or isolation mechanism. A server receipt cannot prove it.

The outbox CAS is the **release-authorization cut**. **Distributed authorization
closure** stops new items without retracting old ones. **Transport quiescence**
also proves terminal disposition, no retry, and no pending delivery for every
retained item. Receiver admission is the fourth cut. Ambiguity proves neither
quiescence nor physical confidentiality closure.

`ObserverGrantDistributedAuthorizationClosureReceipt` proves only the second
cut. It binds the exact `ObserverGrantAuthorizationClosureDecision`, original
complete boundary set/plan and one
`ObserverGrantDistributedAuthorizationClosureMemberEvidence` per member. That
evidence is closed to:
`TERMINAL_ACKED | NO_INSTALL_ZERO_WORK_PROVED |
SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE |
BOUNDARY_PERMANENTLY_ISOLATED |
DEADLINE_ELAPSED_UNACKNOWLEDGED`.
Every member binds its ADR-009 closure mode.
`DEADLINE_ELAPSED_UNACKNOWLEDGED` is legal only for
`FINITE_ENFORCED_FINAL_BOUNDARY`; a
`LOCAL_TERMINAL_CLOSURE_REQUIRED` member forbids elapsed closure and keeps its
marker open until exact role completion.
`TERMINAL_ACKED` binds the exact protected
`TrustedDeliveryBoundaryTerminalInstallationReceipt`, passing cross-store
verification and canonical retained-item identity/count/root inventory.
`NO_INSTALL_ZERO_WORK_PROVED` binds exact
`TrustedDeliveryBoundaryGrantNoInstallEvidence` and zero inventory. Each
evidence branch binds its specified audience-protected receipt envelope and
passing `CrossStoreSecurityReceiptVerificationEvidence`; the direct tombstone
export is `PERMANENT_CLOSURE_TOMBSTONE`. No generic protected-evidence envelope
exists.
`SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE` binds
`ObserverGrantPendingNeverLiveClosureProof` and the exact member/projection; it
proves zero release-capable items without asserting local receipt.
`BOUNDARY_PERMANENTLY_ISOLATED` binds qualified role-specific isolation of the
exact boundary instance, grant, execution authority, credentials, queues,
network release paths and all successor/restart capability. Its retained-item
inventory is `UNKNOWN`; generic absence, loss or root status is insufficient.
Every cross-store acknowledgement binds its audience envelope, verification,
operation and replay domain; a bare local receipt rejects.
`DEADLINE_ELAPSED_UNACKNOWLEDGED` binds authenticated proof that the original
`boundary_release_not_after` elapsed without a no-extension violation. That proof
uses either the plan's shared trusted monotonic clock or a current coordinator
clock sample to prove that the plan's
`min(server grant not-after, server request time +
maximum_boundary_revocation_lag)` source instant has elapsed. The plan's
qualified bounded-drift/no-extension mapping then proves that the boundary clock
had reached at least `boundary_release_not_after` at that mapped source instant.
That source instant is inside the plan's source applicability horizon; the
derived lower image and deadline are inside its target applicability horizon.
The proof does not extrapolate the mapping to the later current coordinator
sample. If the coordinator incarnation changed, the proof also binds the exact
installed `ObserverAuthorizationClockRestartCommitReceipt` ancestry and
`OBSERVER_DISTRIBUTED_CLOSURE_HORIZON` entries that map the original source
effective closure horizon to each exact upper/later image and prove the final
image elapsed.
A lower/earlier authority image cannot prove closure. Missing/unmappable
upper-purpose ancestry forbids only the deadline-elapsed branch; terminal,
no-install, never-LIVE or qualified isolation evidence remains eligible. The
closure receipt binds the exact applicable map entries and restart commits. The
boundary clock policy must advance across suspend. A policy
whose monotonic clock can pause, roll back, lose continuity, or resume behind
the deadline must create a fresh incarnation and require fail-closed authority
contact plus a no-extension bridge before any release. A mere server UTC
timestamp, coordinator progress without a qualified lower-bound mapping, or
unavailable mapping does not qualify. The branch sets retained-item inventory
to explicit `UNKNOWN`; it can carry only a policy capacity/sequence upper bound,
never fabricated item membership. Authorization closure can therefore finish
while a partitioned boundary remains unacknowledged only when that worst-case
expiry is proved. It contains no transport-quiescence claim.

Each boundary first constructs receipt-free
`TrustedDeliveryBoundaryTransportQuiescenceFact` from the exact terminal grant
entry and installed outer/map heads. The fact binds that grant key and boundary
lineage, the canonical retained item root/count, every attempt disposition and
tombstone, no-retry state, and authenticated transport proof that no delivery
remains pending for those stable item identities. It contains no successor,
selector, commit or receipt. `MARK_BOUNDARY_GRANT_TRANSPORT_QUIESCENT` changes
that exact entry to `TRANSPORT_QUIESCENT_BOUNDARY_GRANT` through the sole outer
selector and permanently forbids another attempt for that grant. Only the
post-CAS `TrustedDeliveryBoundaryTransportQuiescenceReceipt` binds the fact,
prior/installed outer/map/entry heads, selector version,
`TrustedDeliveryReleaseStateCommitReceipt` and
`TrustedDeliveryBoundaryGrantMapCommitReceipt`.
A stale/sibling fact or concurrent drain-start loses that CAS. Missing outbox
history, an unresolved active attempt, or
`AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT` without transport-specific no-pending proof
blocks the transition.

`ObserverGrantTransportQuiescenceReceipt` binds the authorization-closure
receipt and one closed `ObserverGrantTransportQuiescenceMemberEvidence` per
original plan member:
`TERMINAL_ENTRY_TRANSPORT_QUIESCENT | NO_INSTALL_ZERO_ITEMS |
SERVER_TERMINAL_FROM_PENDING_NEVER_LIVE_ZERO_ITEMS |
EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT |
PERMANENT_ISOLATION_ZERO_ITEMS`. The first binds the exact boundary-quiescence
receipt. The second binds exact no-install evidence and zero-work roots. The
third binds the exact never-LIVE proof, whose source history makes a release
item impossible for every member.
`EMERGENCY_COMPLETE_CLOSURE_TRANSPORT_QUIESCENT` binds the exact
per-grant protected emergency member and complete item/attempt/retry/no-pending
transport partition. An ambiguous effect qualifies only with transport-specific
completed/no-pending proof and still proves no delivery/success. Fencing or
generic no-open-work alone is insufficient. The last branch is legal only when qualified
isolation evidence also contains a complete exact work partition proving no
installed release item, attempt, retry or pending transport; authority isolation
alone cannot select it. A canonical bijection maps each plan-member key and its
authorization-closure member digest to exactly one same-key quiescence member;
cross-member or cross-branch evidence substitution rejects. The aggregate proves
the third cut, not receiver admission. An expiry-only or
`BOUNDARY_PERMANENTLY_ISOLATED` authorization-closure member with `UNKNOWN`
inventory remains nonquiescent until stronger exact evidence arrives.

Boundary return evidence from a single-key or bulk outer producer crosses stores
only as
`ProtectedTrustedDeliveryBoundaryClosureEvidenceEnvelope`, whose closed inner
kind is `BOUNDARY_TERMINAL_INSTALLATION |
BOUNDARY_NO_INSTALL_TOMBSTONE | BOUNDARY_TRANSPORT_QUIESCENCE |
BOUNDARY_EMERGENCY_CLOSURE | BOUNDARY_FINAL_RETIREMENT`. Each branch binds its
exact receipt, grant/member/projection, local selector and commit ancestry,
operation and replay domain. It uses ADR-009
`REGISTERED_SOURCE_AUTHORITY`.
`BOUNDARY_TERMINAL_INSTALLATION | BOUNDARY_TRANSPORT_QUIESCENCE |
BOUNDARY_EMERGENCY_CLOSURE` selects `DURABLE_HISTORICAL_COMMIT`;
`BOUNDARY_NO_INSTALL_TOMBSTONE | BOUNDARY_FINAL_RETIREMENT` selects
`PERMANENT_CLOSURE_TOMBSTONE`. No caller or batch can change or merge those
verification classes. The source
transaction's named
`TrustedDeliveryBoundaryClosureEvidencePublicationManifest` is the exact
ADR-001 `AuthorityTransactionPersistenceManifest` specialization for this
return producer. Its pre-CAS fact binds the complete affected-key set,
preallocated per-key receipt/envelope identities, the exact conditional
verification-class-to-family-key/manifest-identity map, one distinct
completion-manifest identity, exact counts and hierarchy/retention reserve. The
durable family is present if and only if at least one durable branch is present.
The permanent family is present if and only if at least one permanent branch is
present. Empty families are forbidden.
After all per-key receipts and envelopes exist, one
`CrossStoreProducerPreManifestBundleCommitment` binds the exact
key-to-receipt/envelope bijection, installed local heads/receipts, signer
ancestry, retained retry bytes and complete sidecar set. One named manifest
instance owns each nonempty deterministic verification-class family; a single
key is a one-family, one-member shape. The mandatory completion manifest
authenticates the exact one- or two-family set last. A zero-member closure set
emits no return hierarchy. Per-key or merged-class family manifests, a duplicate
same-family manifest, an unexpected family, a missing or second completion, or
an omitted, duplicate or swapped key rejects.
Each source requires that family manifest, shared completion manifest, its two
scoped proofs and passing
`CrossStoreSecurityReceiptVerificationEvidence`; a bare, torn, wrong-member,
wrong-source, cross-branch or unmanifested local receipt is not aggregation
evidence, and retry discloses no sibling.

`ObserverGrantClosureAggregationHead` has a positive version/prior digest,
bounded operation/result map and one
`ObserverGrantClosureAggregationMemberState` per immutable plan member. The
closed monotonic lattice is
`UNOBSERVED -> AUTH_CLOSED_UNKNOWN -> AUTH_CLOSED_EXACT ->
TRANSPORT_QUIESCENT`, plus direct
`UNOBSERVED -> AUTH_CLOSED_EXACT`. Unknown is legal only for the deadline-elapsed or
authority-isolation closure branches with unknown retained work. Exact binds one
terminal, no-install, pending-never-LIVE or complete-isolation branch and its
protected evidence. A later exact result refines an earlier unknown result while
retaining both evidence digests and receipts; it never rewrites history.
Quiescent binds the exact authorization member it refines and its same-member
zero-work or complete transport disposition. Unknown cannot jump to quiescent.
Thus one member has at most three committed advances: unknown, exact and
quiescent; a direct-exact path has at most two.

One canonical evidence-input record exists for each affected member. It binds
the member key, one lattice edge, one closed native evidence-union tag, the
native evidence digest and the complete retained refinement ancestry. The
affected-set root is a canonical bijection over those records. Each union arm
requires its origin-specific fields and forbids every other arm's fields.
Shared family and completion manifests can serve more than one record only when
each record binds its exact envelope and both scoped membership proofs. A
manifest reference alone is not a member record. An unknown tag, an omitted
forbidden field, a cross-member proof or a refinement that drops the earlier
unknown evidence rejects.

The operation key is a domain-separated digest, not a caller-selected ID. It
binds the authority and source coordinates, exact target-history preimage and
terminal decision, full grant installation identity, accepted-result
commitment, immutable plan-member root, evidence-input commitment, prior and
next member roots, aggregate output and the complete pre-CAS semantic-input
digest. The full grant installation identity includes the registry
incarnation, issuance sequence and grant digest. The semantic-input digest
excludes the operation key and every candidate, receipt and sidecar. For a
member batch, the evidence-input commitment is the affected-member evidence
bijection root. Exact replay consumes no version or capacity; a changed or
non-refining result rejects.

An accepted result whose immutable boundary plan has zero members uses one
separate evidence-input branch. It requires the authenticated accepted-result
receipt and commitment, the domain-separated canonical empty plan-member root,
member count zero, current target history and typed never-aggregated empty head.
It forbids every member, boundary-return, isolation, deadline and transport
evidence field. Its sole mutation installs canonical version-1
`TRANSPORT_QUIESCENT` empty aggregation state. The authorization-closure and
transport-quiescence receipts bind the empty-proof discriminant, proof digest
and empty root. A later request can only return the exact retained operation
and bundle; it cannot install a second empty successor.

`ADVANCE_OBSERVER_GRANT_CLOSURE_AGGREGATION` is the sole boundary-aggregation
writer. Its
receipt-free fact binds the exact current target-history head/entry, grant key,
terminal decision, prior aggregation version, one canonical affected-member set,
protected evidence, its exact publication manifest, envelope-membership proof
and verification, closed lattice edge, candidate member/root projection and
idempotency operation. It excludes successors, commits,
aggregate receipts and exports. One target-history selector CAS preserves every
unaffected target, grant, member, policy assessment and checkpoint candidate.
It is legal in `CURRENT_SOURCE_GENERATION`,
`SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION` and
`SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION`; it grants no
authority and cannot produce an ALLOW policy result.

Closure aggregation never closes an observer-role marker. For a
`LOCAL_TERMINAL_CLOSURE_REQUIRED` plan it compares and preserves the exact
ADR-009 observer marker state; only the dedicated observer-role recording path
can close an open observer marker from local evidence. A delivery-boundary
quiescence update can close only that affected delivery member's
`DELIVERY_TRANSPORT_QUIESCENT` ledger obligation. Authorization closure alone
closes neither role. A `FINITE_ENFORCED_FINAL_BOUNDARY` plan binds typed observer
marker inapplicability. If pending-never, emergency or final whole-root closure
already installed the evidence-compatible terminal observer marker, aggregation
compares and preserves its exact close receipt without a ledger write; a
different terminal state rejects.
This read-only compatibility remains legal while target history is mutable even
after source-entry finalization; domain retirement/sealing permits archive only.
Direct source pending-never-LIVE termination binds the decision commitment and
closes its marker set in the earlier common transaction; only a later
`ADVANCE_OBSERVER_GRANT_CLOSURE_AGGREGATION` can bind the post-CAS proof and
advance member state. Same-operation retry returns the installed bytes; a stale version, evidence downgrade,
cross-member substitution, partial marker set or changed operation loses.

Post-CAS `ObserverGrantClosureAggregationCommitReceipt` binds prior/installed
target-history and aggregation roots, source/ADR-009 coordinates when applicable,
the fact and common transaction receipt. When every member is at least
authorization-closed, the same durable bundle creates the canonical
`ObserverGrantDistributedAuthorizationClosureReceipt`. When every member is
quiescent, it additionally creates `ObserverGrantTransportQuiescenceReceipt`
over the exact earlier authorization-member root and refinement ancestry. Each
receipt is unique for its aggregation version and canonical member root.

The source exports those results only in
`ProtectedObserverGrantClosureResultEnvelope`, with closed kind
`AUTHORIZATION_CLOSED | TRANSPORT_QUIESCENT`; the latter binds both receipts.
One aggregation version emits at most one envelope: if that version proves
quiescence it emits only the stronger `TRANSPORT_QUIESCENT` branch, never a
sibling authorization-only envelope; otherwise a fully authorization-closed
version emits `AUTHORIZATION_CLOSED`. A version that proves neither emits no
protected result bundle.
It is an ADR-009 `DURABLE_HISTORICAL_COMMIT /
SINGLE_REGISTERED_EXTERNAL_ROOT` envelope for the exact observer root and
request attempt. `CrossStoreProducerPreManifestBundleCommitment` binds the
applicable receipt set, envelope, complete aggregation commit and precharged
signing material. The sole
`ObserverGrantClosureResultPublicationManifest` family manifest binds that
commitment and retained exact-retry bytes; the mandatory completion manifest
authenticates the one-family set last. The envelope excludes both manifests. The acyclic chain
is aggregation candidate -> target-history/common commit ->
`ObserverGrantClosureAggregationCommitReceipt` -> aggregate receipt(s) ->
protected envelope -> pre-manifest commitment -> family manifest -> completion
manifest, and each object excludes later objects. A local resolver, detach
result, reattach or checkpoint publication consumes that envelope, its exact
family and completion manifests and passing verification, never bare
aggregate receipts.

Aggregation, generation finalization, checkpoint publication and permanent
target sealing contend on the target-history selector. Publication requires the
latest complete descendant aggregation. A permanent seal moves the exact
unresolved aggregation and idempotency state into quarantine; later evidence is
archive-only and cannot create ALLOW, reattach or local installation authority.
Retired normal keys verify only retained pre-retirement commits; a compromised
key needs ADR-009 independent pre-compromise anchoring or a restrictive
alternative. Evidence accepted through
`RESTRICTIVE_ALTERNATIVE_CLOSURE_REQUIRED` taints its member and aggregate
closure-only: it may terminalize, detach, retire or quarantine, but cannot yield
`REATTACH_ALLOWED`, `ALLOW_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE`, challenge,
reattach or local installation. Only independent pre-compromise anchoring or
unaffected current trust supports positive continuation. Per-target grant/member/write/byte/signature caps and reserved
closure capacity bound this serialization surface. For `N` members, acceptance
precharges at most `1 + 3N` aggregation versions and at most one result envelope,
pre-manifest commitment, family manifest and completion manifest per producing
version. It separately precharges six possible
observer-role evidence-record refinements, each applicable target-history write,
record/writer receipt, proof/evaluation, resolution,
`ProtectedObserverGrantRoleClosureEvidenceResolutionEnvelope`, authenticated
resolution family/completion hierarchy, verification and exact-retry
bytes/signatures. Origin
branches cannot borrow another origin's position. Exact replay consumes no
reserve. Exact cap is legal; cap-plus-one rejects before acceptance.

`ObserverDetachCompletionResult` is a closed result:
`DETACH_AUTHORIZATION_CLOSED | DETACH_TRANSPORT_QUIESCENT`.
It binds canonical `ObserverDetachCompletionMemberSetRoot`, not one scalar grant.
Ordinary LIVE detach contains that grant. Detach from `LIVE_RENEW_PENDING`
contains G0 plus the exact G1 attempt/kind; the set never shrinks. G1 is closed
only by protected unused-slot proof or, if accepted, its protected authorization/
quiescence aggregates. The first result binds authorization closure for every
accepted member and unused proof for each nonaccepted member. The second requires
every accepted member transport-quiescent and every nonaccepted G1 proved
unused. Deadline expiry with `UNKNOWN` can establish only the first; timeout
never proves G1 unused or transport drain. Lost exact state leaves the stronger
result permanently unproved.

The complete grant-installation identity is
`(logical session, session generation, requester principal, grant-lineage
incarnation, registry incarnation, issuance sequence, grant digest)`.
`ObserverGrantRegistryKey` is only the stable
`(requester principal, grant-lineage incarnation)` pair. Renewal replaces the
value at that same server key. Reattachment never changes a
terminal key back to pending: it preserves that terminal entry and creates a
fresh never-used grant-lineage incarnation and server key with an explicit
predecessor link. The exact installed registry head and
current value supply the registry incarnation, issuance sequence, and grant
digest. A boundary uses the complete installation identity as its distinct
`TrustedDeliveryBoundaryGrantKey`. The grant's
`grant_lineage_incarnation` is the same typed field as the registry key's
`grant_lineage_incarnation` and must equal the nested field in every complete
boundary key. There is no second decorative grant incarnation. A grant ID,
grant-lineage incarnation, registry
version, or nonce is never accepted as authority by itself. Issuance sequence is
durably persisted, strictly increases within one grant lineage, and never
resets.

The `security_epoch` is the bounded persisted monotonic JSON-safe integer from
ADR-009. It is not an incarnation UUID. Session generation, stream epoch, grant
ID, grant-lineage incarnation, ledger incarnation, operation ID, issuance nonce,
and receiver clock incarnation remain opaque canonical identifiers compared only
for exact equality.

A renewal can preserve the exact descriptor revision and issue a new grant.
Grant IDs, authorization-incarnation IDs, operation IDs, session generations,
and stream epochs use their canonical opaque identifier types; a bounded integer
cannot substitute for an incarnation. A descriptor-revision, declaration,
publisher, schema, semantic-contract, security-state, plant-profile, privacy-
projection, or allowed delivery-boundary-set change requires a new descriptor
and authenticated reattachment.
Renewal requires the current grant to be live, unexpired, unrevoked, issued to
the verified caller, and bound to the same descriptor revision/digest, session,
generation, security epoch, revocation epoch, and security-state digest.

Concurrent observers do not share one unkeyed current grant. The subordinate
`ObserverGrantRegistryHead` binds the session generation, a never-reused registry
incarnation, state version, prior-head digest, bounded retained lineage
tombstones, and a bounded canonical map keyed by
`(requester principal, grant-lineage incarnation)`. Each map value is an
`ObserverGrantLedgerHead` that binds the exact key, one closed
`PENDING_BOUNDARY_INSTALLATION | LIVE | TERMINAL` state, next issuance sequence,
state version, bounded audit tail of consumed predecessors, and prior keyed-head
digest. A pending renewal binds its exact consumed live predecessor for audit;
that predecessor is not independently current server authority. Both heads
exclude their own digest/receipt and every successor/selector digest.

`InstalledObserverAuthorizationStateSelector` solely owns server descriptor and
grant-map currentness. Attach, renew, detach, revoke, expire, activate and
reattach normally mutate one keyed entry and preserve the descriptor; descriptor/
privacy replacement atomically fences or terminalizes its complete bounded
affected set. `ObserverGrantRegistryCommitReceipt` binds prior/installed
registry, outer and keyed heads, selector version, transition kind,
`AuthorityTransactionCommitReceipt` and
`ObserverAuthorizationStateCommitReceipt`. Every successor preserves other
observers byte-for-byte. `ObserverGrantRegistryActivationEntryProof` proves the
exact activated entry in the then-installed outer/registry; historical or
sibling copies cannot substitute. Boundary release proves its locally installed
decision, local terminal/revocation state and both fixed deadlines, not
independent-store currentness of that historical server head.

The subordinate server registry transition kind is the closed union
`GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED | ATTACH_NEW_GRANT_LINEAGE |
BEGIN_GRANT_RENEWAL | ACTIVATE_PENDING_GRANT | TERMINATE_GRANT |
REATTACH_FROM_TERMINAL_GRANT`. `BEGIN_GRANT_RENEWAL` changes one exact `LIVE`
value at the same `ObserverGrantRegistryKey` to
`PENDING_BOUNDARY_INSTALLATION` with a fresh candidate grant, incremented
issuance sequence, and plan. G0's server ledger head becomes the consumed
historical predecessor of G1; it is not a second current server-map sibling. The
transition stops new server-side release under G0 while the observer can still
admit already released G0 bytes through its separate `LIVE_RENEW_PENDING` state.
Before this compare-and-swap, a receipt-free
`ObserverGrantRenewalTransitionFact` binds a preallocated operation identity,
the exact prior outer/registry/G0 keyed heads and versions, candidate
plan/grant/full boundary key, security/clock currentness, and predecessor
deadline-intent-set root. It also binds prior target-history/aggregation state,
G1's receipt-free accepted-result commitment/preallocated identity and G0's
closure-decision inputs. After the G1 source candidate, the target-history
candidate atomically inserts G1 aggregation version 1 and binds G0
`ObserverGrantAuthorizationClosureDecisionCommitment` without advancing either
member lattice. The common CAS includes the target-history selector; the post-CAS
fence decision resolves G0's commitment. The G1 pending successor binds the fact
and intent root; the pregrant plan stays byte-identical.
Every old-grant boundary then installs
`TERMINATE_BOUNDARY_GRANT` with cause `SERVER_RENEWAL_FENCE` against its exact old
LIVE entry. The server first emits the post-CAS
`ObserverGrantRenewalPredecessorFenceReceipt` over the byte-identical stable
`ObserverGrantRegistryKey`, distinct G0 and G1 full boundary keys, consumed G0
keyed head, installed G1 pending keyed head, prior/installed registry and outer
heads, installed selector version, authority-transaction commit receipt, outer
commit receipt, and specialized registry commit receipt.
The source then publishes the audience-specific boundary and observer terminal
envelopes and complete manifest defined below. Each local transition consumes
its exact envelope and verification, never the bare fence receipt; it
cancels/tombstones old unreleased state and retains old released items/drains.
The authority completes the
predecessor's distributed-
authorization-closure receipt before any boundary prepares the candidate grant
as a genuinely absent, never-used full boundary key while preserving the exact
terminal-or-quiescent G0 boundary sibling. Map non-membership is the absence
proof; no permissive `ABSENT` entry exists. Candidate activation binds both that old
closure receipt and the complete new prepared set. An independent old-grant
boundary remains bounded by its installed predecessor deadline until this
terminal cut or proved expiry; the server transition alone is not a global
release cut.
`ACTIVATE_PENDING_GRANT` is the only
`PENDING_BOUNDARY_INSTALLATION -> LIVE` transition. It is shared by genesis,
new-lineage attach, renewal, and reattach because its proof obligation is
identical. The installed pending head, plan, and activation commitment bind the
exact originating operation; activation never infers that origin from candidate
grant fields. A failed or incomplete preparation uses `TERMINATE_GRANT`; it
cannot silently restore the predecessor or partially activate the candidate.

Grant termination is an explicit keyed transition, not lifecycle prose. The
authority first constructs a receipt-free
`ObserverGrantTerminalTransitionFact`. It binds the actor or trusted timer/event,
exact prior installed observer-authorization, registry and keyed heads, exact
prior live or pending grant, one closed terminal reason, terminal time in the
authority's clock, and revocation state plus the installed reattachment-policy
rule, installed fresh-attach-after-lineage policy rule and their exact inputs. It
contains no policy result, terminal
successor, selector version, registry or outer commit receipt, or terminal
receipt. Terminal, registry and outer candidates follow the common DAG.
After those source candidates, receipt-free
`ObserverGrantAuthorizationClosureDecisionCommitment` binds the fact, terminal
projection, plan and prior target-history aggregation; its target-history
candidate binds that commitment. For a direct
`PENDING_BOUNDARY_INSTALLATION -> TERMINAL` edge only, later receipt-free
`ObserverGrantPendingNeverLiveClosureCommitment` additionally binds that decision
commitment, exact pending source heads/projection, prior target history, every
target's prior ADR-009 ledger/open marker and typed namespace nonexistence
preimages. The target-history candidate binds it; each ADR-009
`ExternalSecurityDerivedAuthorityGrantLineageCloseCommitment` binds it, and each
target-ledger candidate binds that ADR-009 commitment. The common
condition compares observer, target-history and every affected ledger selector
and installs all candidates or none. LIVE-origin/renewal-fence termination
forbids the never-live commitment and closes markers through later role
completion. Both commitments exclude installed heads, receipts, output envelopes
and manifests; no source successor binds a commitment constructed after it.
`ObserverGrantTerminalTransitionReceipt` follows the transaction, outer and
registry commits and binds the fact, exact
prior/installed outer, registry and keyed heads, installed selector version, and
those commits. Only then does the authority create
`ObserverGrantReattachmentPolicyAssessment` with closed
`REATTACH_ELIGIBLE_AFTER_COMPLETE_CLOSURE | REATTACH_FORBIDDEN` outcome over the installed terminal
keyed head, terminal receipt, requester lineage, terminal reason, descriptor/
security scope, installed policy rule, exact inputs, deterministic evaluator
digest and authority source receipt; terminal-receipt/rule digest keys it
uniquely. `ObserverGrantFreshAttachPolicyAssessment` similarly has closed
`FRESH_ATTACH_ELIGIBLE_AFTER_COMPLETE_LINEAGE_CLOSURE |
FORBID_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE` over that same terminal head/receipt,
invariant target/requester, installed rule/inputs, evaluator and authority
receipt. Both recompute deterministically, are immutable, and only assess
post-closure eligibility; neither proves closure or contains ALLOW.
`REATTACH_FORBIDDEN` deterministically requires
`FORBID_FRESH_ATTACH_AFTER_COMPLETE_LINEAGE`. A forbidden result cannot be
widened by a later descriptor/policy update or bypassed with a fresh key.
The crash-complete bundle retains the terminal receipt and both signed
assessments before exposure. Missing/conflicting/duplicate results reject; no
post-commit mint or terminal-head back-edge is legal.

A bulk descriptor, security, clock or session cut applies this same terminal
construction to every member of its canonical affected-key set. Its one outer
bundle contains exactly one keyed terminal receipt, reattachment-policy assessment
and fresh-attach-policy assessment per terminalized lineage, with a complete key-to-
sidecar bijection and no sidecars for unaffected keys. It cannot install terminal
keyed heads while deferring policy assessments to a later transition. Thus observer
finalization and checkpoint construction never infer a missing assessment from a
bulk reason. The enclosing fact also preallocates the complete
`ObserverGrantAuthorizationClosureDecisionSetRoot`, every decision's boundary,
observer and conditional ledger-envelope identities, the exact conditional
family-key-to-manifest-identity map, one distinct completion-manifest identity,
exact counts and reserve. The observer-result family is present for every
nonempty decision set. The boundary family is present if and only if the
canonical union of boundary members is nonempty. The ledger-close family is
present if and only if direct pending-never closure has an affected target
ledger. No other family or empty family is preallocated.

`TERMINATE_GRANT` installs one closed terminal reason:
`VOLUNTARY_DETACH | EXPIRED | REVOKED | SESSION_RETIRED |
DESCRIPTOR_REPLACED | SECURITY_REBOUND | CAPACITY_RETIRED |
AUTHORITY_CLOCK_DISCONTINUITY | BOUNDARY_INSTALLATION_FAILED`. The last reason
binds the exact bounded omitted, late, substituted or rejecting boundary member
set through `ObserverGrantBoundaryInstallationFailureMemberEvidence` and one
closed subreason:
`REQUIRED_BOUNDARY_MISSING | BOUNDARY_PREPARATION_AFTER_CLOSE |
UNENUMERATED_BOUNDARY_PRESENT | BOUNDARY_IDENTITY_SUBSTITUTED |
BOUNDARY_DELIVERY_DOMAIN_SUBSTITUTED |
BOUNDARY_DEADLINE_MAPPING_UNAVAILABLE | BOUNDARY_PREPARATION_REJECTED |
PREPARED_SET_NONCANONICAL`. It applies to initial and renewal installation
failure. Unknown/default rejects. Same-operation retries return the installed terminal receipt; a
conflicting reason, losing sibling, or historical live head cannot terminate or
revive another lineage.

Each `ObserverGrantAuthorizationClosureDecision` has closed source origin
`SERVER_TERMINAL_DECISION | SERVER_RENEWAL_PREDECESSOR_FENCE`. The former binds
the terminal fact, direct prior PENDING/LIVE head, installed terminal head,
receipts and commits; the latter binds consumed G0, installed pending G1,
predecessor-fence receipt and commits. After all coordinates for the single or
bulk producer commit, the signer creates one
`ProtectedTrustedDeliveryBoundaryGrantTerminalDecisionEnvelope` per
decision/boundary and one `ProtectedObserverGrantTerminalResultEnvelope` per
decision, both ADR-009
`PERMANENT_CLOSURE_TOMBSTONE / SINGLE_REGISTERED_EXTERNAL_ROOT`
specializations. A boundary envelope binds the decision, grant/plan/key,
member/projection/proofs and source-security condition/operation; the observer
`GRANT_AUTHORIZATION_CLOSURE_DECISION` branch binds the same decision,
requester/grant and admission projection/proofs. Neither carries siblings.
For each direct pending-never decision, the same producer set also contains exactly one
ADR-009
`PER_KEY_DERIVED_AUTHORITY_GRANT_LEDGER_COMMIT / GRANT_LINEAGE_CLOSE`
envelope per affected target-ledger member and its exact receipt/commit
ancestry; other decision origins forbid that set. One
`CrossStoreProducerPreManifestBundleCommitment` binds the complete
decision-set root, outer/lineage receipts, sidecars and canonical
decision-to-boundary/observer/conditional-ledger-envelope bijections.
The exact nonempty family inventory is:

- `ObserverGrantSourceClosureBoundaryDecisionPublicationManifest` for the
  boundary-decision envelopes;
- `ObserverGrantSourceClosurePublicationManifest` for the observer terminal
  result envelopes; and
- `ExternalSecurityDerivedAuthorityGrantLineageClosePublicationManifest` for
  the conditional ledger-close envelopes, present only for direct
  pending-never closure.

Each named type is the sole manifest for its deterministic family. The shared
mandatory `CrossStoreProducerBundleCompletionManifest` authenticates the exact
conditional set and completes the producer last: ordinary closure has one or
two families, and direct pending-never closure adds the ledger family for two or
three. No family manifest owns the entire producer. A one-lineage transition is
one member in every applicable family, not necessarily one family.
Per-decision manifests, a second manifest
for one family, an unexpected or missing conditional family, a second
completion or a changed family partition rejects. A recipient gets only its
authorized envelope, selected family manifest, shared completion and two-proof
delivery capsule; it receives no sibling decision artifact. The precharged
exact-retry bundle fixes every family/completion identity and authentication
before exposure. Bare, family-only, wrong-audience, unmanifested, cross-branch
or wrong-replay-domain evidence rejects.

For a direct `PENDING_BOUNDARY_INSTALLATION -> TERMINAL` source transition,
`ObserverGrantPendingNeverLiveClosureProof` binds the exact prior and installed
source heads, `ObserverGrantPendingNeverLiveClosureCommitment`, terminal branch,
installed target-ledger successors and close receipts, protected terminal
envelopes, canonical public pre-manifest commitment body/digest, applicable
observer-result, boundary-decision and ledger-close family manifests, the
shared completion manifest and both scoped proofs. The boundary manifest is
required exactly when that source decision has a nonempty boundary set. It also
binds typed nonexistence in every
one-use source artifact namespace root authenticated by those source commits of
a LIVE head, activation-set receipt, boundary activation-decision envelope or
accepted-response envelope for that grant. It is deterministic post-CAS verifier
output recomputed from the installed source and target commits, protected
terminal envelope, direct source-head ancestry, manifest and authenticated
namespace roots. It is neither caller evidence nor inserted into a pre-CAS
candidate or earlier envelope. It proves that PREPARE-only target envelopes never
became release authority; it does not infer noninstallation from silence or
elapsed time. Binding the earlier commitment rather than this proof in any
candidate or marker-close commitment keeps the dependency graph acyclic.
The proof structurally excludes the later role record, target-history
candidate/commit, advance receipt, role-record resolution,
`ProtectedObserverGrantRoleClosureEvidenceResolutionEnvelope`,
`CrossStoreProducerPreManifestBundleCommitment`,
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest`, its completion
manifest and their verification. The earlier completed source hierarchy
excludes them too.

Receipt-free `TrustedDeliveryBoundaryTerminalTransitionFact` has cause
`SERVER_TERMINAL | SERVER_RENEWAL_FENCE | LOCAL_FIXED_DEADLINE_EXPIRED |
LOCAL_SECURITY_REVOKED | LOCAL_CLOCK_DISCONTINUITY | BOUNDARY_RETIRED`. It binds
either the exact protected decision envelope, passing
`CrossStoreSecurityReceiptVerificationEvidence`, inner decision, target
proofs, selected family manifest, shared completion manifest and delivery
capsule, or its authenticated local cause; bare server/fence receipts reject.
It also binds the prior PREPARED/LIVE entry and outer/selector/version,
local-security currentness, both deadlines and applicable commit-time sample,
the complete pending reservation/pre-release cancellation set, and complete
retained released-item/active-drain sets. It excludes successors, commits and
terminal receipt. The common DAG installs its terminal/map/outer successors and
derived partitions.
`TrustedDeliveryBoundaryTerminalInstallationReceipt` binds the fact,
prior/installed outer/map/entry heads, selector,
`TrustedDeliveryReleaseStateCommitReceipt`,
`TrustedDeliveryBoundaryGrantMapCommitReceipt`, tombstones and grant-partitioned
retained sets. Local expiry needs the authenticated persisted clock and elapsed
commit-time condition at or after exact `boundary_release_not_after`.

An enumerated boundary that never prepared the key instead constructs receipt-
free `TrustedDeliveryBoundaryGrantNoInstallTombstoneFact`. It binds the exact
protected terminal-decision envelope and verification, decision branch,
`ObserverGrantPendingNeverLiveClosureProof`, grant/plan/key, target
member/projection/proofs, expected outer/map
head/selector/version, typed exact key nonmembership and never-use proof, and
canonical empty reservation, pre-release, outbox, item, attempt and drain
roots. It also binds the key's dedicated
`TrustedDeliveryBoundaryNoInstallTombstoneReserve` position, prior reserve head
and exact AVAILABLE state, and contains no successor, commit or receipt.
`INSTALL_BOUNDARY_GRANT_NO_INSTALL_TOMBSTONE` uses the sole release selector in
`OPEN_AUTHORITY | RETIRED_DRAIN_ONLY`, consumes that reserved position, and
installs the key directly as a `TRANSPORT_QUIESCENT_BOUNDARY_GRANT` with cause
`SERVER_TERMINAL_NEVER_PREPARED`, zero work roots and a permanent never-use
tombstone while installing the reserve successor
`CONSUMED_DIRECT_NO_INSTALL`. Its post-CAS
`TrustedDeliveryBoundaryGrantNoInstallTombstoneReceipt` binds the fact, exact
prior/installed outer and map heads, installed entry, selector version, generic
and map commit receipts, prior/installed reserve heads and zero-work roots. The transaction
persists them together. Delayed PREPARE and no-install race on the same key and
outer selector: PREPARE first requires ordinary terminalization; tombstone first
makes PREPARE reject forever. Retry returns only the exact installed result.

`TrustedDeliveryBoundaryGrantNoInstallEvidence` is closed to
`DIRECT_NO_INSTALL_TOMBSTONE | EMERGENCY_CLOSURE_NO_INSTALL |
FINAL_TERMINAL_NO_INSTALL`. The first binds that receipt. The second binds the
exact member of a complete
`ExternalCompositeEmergencyAuthorityClosureReceipt` partition. The third binds
the exact `PERMANENT_LOCAL_TERMINAL_PROVES_NEVER_INSTALLED` member of
`ExternalCompositeTerminalMarkerGrantClosureAssessment`, its final head/map and
protected final-retirement receipt. Every branch binds the same source
commitment, pending-never-LIVE proof, grant, target, audience and zero-work
identity plus the exact matching direct/emergency/final reserve-position
successor. A LIVE-origin or renewal-fence decision contradicts no-install
evidence and requires quarantine; generic fenced, terminal or missing status is
insufficient.

The terminal decision goes to every named boundary. An existing entry uses the
terminal path; exact absence uses direct, emergency or final no-install evidence.
All paths reject new reservations and preserve committed items/drains.

Detach remains `DETACH_PENDING` until the authority can create
the complete closure receipt. `DETACH_AUTHORIZATION_CLOSED` stops new release;
only `DETACH_TRANSPORT_QUIESCENT` proves drain. Missing clock state is not
expiry. Reconnect requires current registry/revocation state; a partitioned
boundary remains limited by its original cutoff and local terminal state.

Session-generation creation consumes the exact current ADR-001 logical-session
lineage creation receipt and observer child marker. The common authority-domain
transaction changes that exact parent-lineage marker from `ALLOCATED` to
`CONSUMED`, allocates the never-used outer and registry incarnations, and
installs the empty current registry plus one closed source-lineage checkpoint
branch through
`OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION`. The specialized
registry receipt carries `GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED` for that
subordinate version-1 installation; it consumes no registry selector.
`NO_PREDECESSOR_GENERATION` is legal only for the first logical-session
generation from the original ADR-001 `NO_GENERATION` head and an empty inherited
checkpoint root; it does not assert nonmembership for every possible requester
target in the realm-global map. Otherwise genesis binds the exact predecessor
source finalization receipt and durable pending-target/server-cut root. That root
contains a canonical bounded map of every target claimed by the predecessor,
including immutable checkpoint candidates and all pending remote obligations.
It does not require their later publication receipts and contains no live
authority. An unclaimed inherited entry is carried unchanged, including across
an aborted, partial or skipped source generation. Current target exclusivity
still comes only from the exact realm-global registry comparison. Omission of a
claimed target or boundary plan, loss of a pending obligation, or two writable
source generations rejects successor creation. The first and every later new observer use
`ATTACH_NEW_GRANT_LINEAGE` against the current registry and a never-used lineage
key. The first keyed head and every new-lineage attach use fresh challenges,
IDs, nonces, deadlines, and sequence state. A missing selector in an existing
session, signed empty registry, restart reset, sibling genesis, reused lineage,
or dropped tombstone needed to reject reuse retires all grants and the session
generation; it cannot authorize another first attach.

Ordinary expiry and detach do not force retirement of a still-live session.
Before reattachment, the authority constructs receipt-free
`ObserverGrantReattachmentTransitionFact`. It binds the operation; exact old
terminal key/head and terminal receipt; one closed
`ObserverGrantReattachmentOriginEvidence`:
`CURRENT_GENERATION_TERMINAL | PUBLISHED_PREDECESSOR_TARGET`; current descriptor/
security/revocation/clock
context; the fresh successor lineage key and exact key-nonmembership proof; the
new initial issuance sequence, grant, installation plan and deadline-intent
root; and the explicit predecessor link. It contains no successor registry or
outer head, selector, commit or reattachment receipt.
`REATTACH_FROM_TERMINAL_GRANT` uses the exact terminal keyed head as immutable
predecessor evidence and verifies a fresh attach challenge, current
descriptor/revocation/security state and the exact
`ProtectedObserverGrantReattachmentOriginEvidenceEnvelope`, manifest and
matching inner branch. The current-generation branch consumes the
installed `REATTACH_ELIGIBLE_AFTER_COMPLETE_CLOSURE` assessment, exact
`ProtectedObserverGrantClosureResultEnvelope / TRANSPORT_QUIESCENT`, its
manifest and passing verification, plus `ObserverGrantRoleClosureEvidence` and
`ObserverGrantPositiveContinuationTrustEvidence`. It also consumes the exact
`ObserverGrantRoleClosureEvidenceCompleteRecordSetAssessment`, canonical record
and `COMPLETE_SET_POSITIVE_CONTINUATION_ELIGIBLE` outcome carried by the current
origin bundle. The protected result binds
the distributed-authorization-closure and transport-quiescence receipts. The published-
predecessor branch consumes the exact `REATTACH_ALLOWED` global checkpoint result
and publication receipt, which already bind all four cuts and positive-
continuation trust. At this source-authorizing CAS, both branches require fresh
`ObserverGrantContinuationAuthorizationTrustRevalidation` against the latest
security head, cumulative incident root, non-supersession and manifest
authorization. The current branch additionally requires byte equality between
the installed record-set root and every field of the origin publication's full
assessment coordinate; a stale coordinate rejects and must be republished under
the current positive assessment. Both branches compare the exact global target
entry in `CURRENT_SOURCE_GENERATION`, preserve
the predecessor lineage's issuance high-water, allocate a fresh never-used successor lineage
key, and creates its version-1 `PENDING_BOUNDARY_INSTALLATION` entry with the
new lineage's initial issuance sequence and fresh grant ID/lineage incarnation/
nonce/deadline/scope values. The old terminal entry and no-reuse tombstone remain
byte-for-byte unchanged. The new entry binds the old full key/head and closure
proof as its predecessor, and proves successor-key/lineage inequality and
freshness. It never inherits an old scope or revives an old grant.
`REATTACH_FORBIDDEN` in either an assessment or published result blocks renewal,
successor-lineage reattach and a new lineage for the same principal. It also
fixes the fresh-attach assessment and published result to FORBID. No later policy
transition can widen that installed lineage decision.

After the winning outer CAS, `ObserverGrantReattachmentTransitionReceipt` binds
the fact, preserved old entry/tombstone, created successor key/head, exact prior
and installed registry/outer heads, selector version, generic and registry
commits, and sibling-preservation proof. A receipt that replaces the old key,
omits new-key nonmembership, or binds the old and new lineage as equal rejects.

Reattachment-policy eligibility is not proof that the old distributed
authorization is closed. Before activation after reattachment, privacy or
descriptor replacement, security rebound, or principal rotation, the new
installation commitment accounts for every old boundary. A boundary preserved
with the same principal, instance lineage, delivery domain, and security policy
first installs either the old key's terminal/quiescent successor or, for a
pending-never-LIVE key it never prepared, the exact direct no-install
quiescent tombstone or complete emergency/final equivalent. Only after that
local predecessor record is a member of the distributed-authorization-closure
proof can the boundary commit the new
`PREPARE_BOUNDARY_GRANT` transition from canonical non-membership of the new
full boundary key while preserving that old terminal/quiescent sibling. A
qualified isolation claim cannot replace local state on the same active
instance. Every removed, substituted or policy-changed boundary requires its
exact prior closure member: terminal, no-install, pending-never-LIVE, qualified
isolation or proved original deadline. The new server activation rejects until
the complete old closure proof, required same-instance local predecessor state
and new prepare set are present. Thus a partitioned old boundary cannot remain
live while a replacement silently gains overlapping authority. A policy that intentionally permits bounded rotation
overlap must define a separate closed transition and explicit reviewed overlap
bound; no current transition implies that policy.

The current keyed-entry rule, not an unbounded used-ID set, rejects stale grants.
Pruning an audit tail cannot make an earlier sequence current. If a sequence
would exhaust, the installed registry or keyed head cannot be proved current,
durable state rolls back, or registry/lineage uniqueness is uncertain after
random-generator rollback, the body/service retires every grant and the session
generation before it discards identity history. A stale, rolled-back, consumed,
or dead grant cannot renew; it can be replaced only by the closed terminal
reattachment transition when that transition is allowed.

Every queued delivery binds:

- the exact neutral `AuthorityRealmKey` and full source-kind/logical-session/
  generation identity;
- the exact descriptor revision plus descriptor and grant digests;
- the exact grant-registry key, current registry head/selector proof, and keyed
  ledger head;
- the exact `TrustedDeliveryBoundaryGrantEnforcementReceipt` and installed
  renewal-ledger head;
- the exact `TrustedDeliveryReleaseReceipt` for these complete bytes/result and
  boundary output-queue ownership transfer;
- the exact enforcement-boundary principal/instance, boundary security state,
  literal delivery domain, deadline policy, and clock incarnation named by that
  receipt;
- session, generation, security-state digest, security epoch, and revocation
  epoch;
- the exact grant scope tuple used for that frame;
- the grant's issuer UTC audit interval and maximum duration, and the trusted
  boundary's local not-after deadline and monotonic-clock incarnation; and
- for history, the exact publisher, stream epoch, schema, semantic contract,
  source position, requested window, and `ProviderHistoryProvenance`.

After receipt, the observer's delivery/admission envelope separately binds its
own `ObserverGrantInstallationReceipt`, exact neutral `AuthorityRealmKey`, full
source identity, observer receive/admission times and clock incarnation,
transport principal, and frame-admission transition. Neither
boundary copies numeric time from the other.

Producer bytes and receiver evidence use different identities. A driven command
or observation can carry a producer-authenticated, receiver-independent
`NormativeSourceRef`. It binds the origin session and generation, complete typed
`StreamPosition {epoch, seq}`, stream-declaration digest, origin frame/content
identity, and exact neutral `AuthorityRealmKey` plus source session kind. The
canonical portable source identity is therefore
`(AuthorityRealmKey, source_session_kind, logical_session_id, generation)`; it
cannot be projected to the last three fields.
It never contains an observer admission receipt. An origin
`SensorFrame` does not need a self-referential source field: its authenticated
frame bytes, declaration, and own position establish that portable origin
identity.

`TrustedProjectionRecord` is the transferable, receiver-independent protected
projector evidence for any privacy projection. Its canonical content binds the
projector principal and security state, exact origin `AuthorityRealmKey`, full
source identity, original object identity/digest,
content-addressed projection policy and transform, exact projected
frame/content and declared stream, and intended audience. It contains neither
its own digest/signature nor any receiver admission receipt. The protected
projector envelope authenticates its digest. A recipient must already be in the
record's audience; an intermediary signature or transfer policy cannot widen it.
The acyclic construction order is projected content/frame, projection record,
protected projector envelope/signature, receiver admission receipt, then local
provenance. The projected content/frame contains no projection-record digest,
local provenance, or admission receipt; the record contains no later receipt.

After admission, the receiver records one `ResolvedOriginEvidence` in a closed
union. `EXACT_ORIGIN` binds the portable identity to this receiver's immutable
admission receipt for the exact original protected frame/content.
`TRUSTED_PROJECTED_ORIGIN` binds the same portable identity to
`TrustedProjectionProvenance`: exact `TrustedProjectionRecord` digest, this
receiver principal/evidence lineage, and this receiver's projected-frame
admission receipt. It proves only the declared projection, not the unavailable
original value. Swapping the record, original, policy, projected bytes,
audience, receiver, or receipt rejects. Two named receivers can admit the same
record, but they create distinct local provenance objects and cannot exchange
receipts.

`ResolvedCaptureSourceCorrelation` binds either an admitted origin/projection or
a driven command/observation to one exact local `ResolvedOriginEvidence`. For a
driven object, the receiver verifies its `NormativeSourceRef` against that
evidence, then reuses the same local evidence identity; the driven object's own
receipt cannot replace it. All forms bind the receiver and full
`(AuthorityRealmKey, source_session_kind, logical_session_id, generation)`
identity.
Independent receivers have different admission receipts but resolve the same
portable origin identity. A
driven frame's own stream position is not its driving-source position. Epoch and
sequence cannot be split, recombined, inferred from receiver time, or replaced by
a nearest frame. A frame with neither an admitted origin identity nor a valid
normative source reference records explicit absence and is not eligible for a
join that requires source correlation.

This correlation proves only that the producer declared one exact source and
that this receiver resolved the reference to exact admitted original or
projected bytes. It does not prove that the producer's internal computation
consumed those bytes, that no unrecorded input influenced the result, or that the
source caused a later command, observation, assessment, or outcome. A consumer
must label the relation `producer_declared_resolved_source`. Any stronger
computational-dependence or causal claim requires separately instrumented,
content-bound, and independently qualified evidence.

The trusted body/service or terminating gateway is the confidentiality
enforcement boundary. It first constructs and bounds the complete live payload
or complete history result, including the exact digest and byte length. A
partial history release is invalid.

Before bytes leave, the boundary compare-and-swaps one
`TrustedDeliveryReleaseReservation` as a nonauthorizing pending-intent fence. The
fence binds the exact bytes or result, grant, scope, requester, and descriptor.
It also binds the installed activation proof, generation, local security state,
boundary identity, clock, and exact `boundary_release_not_after`. The fence
binds a receipt-free `BOUNDARY_GRANT_RELEASE_NOT_AFTER` deadline-condition
intent-set root.

The fence can retain an intended release sequence and output slot as advisory
values. The fence does not allocate or consume either value. It does not consume
the read decision or quota. It does not advance an allocator, install a release
counter successor, or expose a release result. Candidate heads preserve those
states. Reservation receipts prove only the pending fence and intent root.

Historical server proof is not live cross-store currentness. The enforcement
receipt binds the original installation-plan time
constraint and derives both boundary deadlines without extension. Delayed
contact, replay, or reinstall cannot reset either deadline. The boundary checks
queued work again at delivery. A pre-expiry request cannot release bytes after
`boundary_release_not_after`. It also cannot release bytes after a local
terminal or revocation transition wins. A remote server transition is not a
completed local boundary cut. The observer SDK is a misuse barrier, not the
hostile-client security boundary.

The external composite-state allocation, registration, imported-security genesis, emergency closure and final-retirement handshake is defined in the [cross-store observer closure and enrollment module](modules/adr-004-cross-store-observer-closure-and-enrollment.md). Its protected audiences, reserves and two-store race rules apply to every standalone root here.

Drain start/resolution and finalized-outbox retention change only the outer
outbox/drain partition and byte-preserve grant map/entries. Quiescent eviction
changes and removes one exact map entry, then installs its permanent full-key
never-reuse tombstone after the required origin proof. Bulk terminalization and
clock restart change only their canonical complete affected-key sets. Every
other entry transition changes one key. Unknown, default, inferred, and legacy
aliases reject.

Only `LIVE_BOUNDARY_GRANT` creates a reservation. Missing or recreated empty
state after use retires the boundary and all grants. Creation proves the exact
keyed candidate in the winning outer head. Reply loss returns that reservation,
never remakes one from changed bytes, time, authority, or a sibling.

Every reservation ends in one complete outbox item or pre-release cancellation.
Receipt-free
`TrustedDeliveryReleaseReservationCancellationFact` binds the exact reservation/
grant, idempotency key, advisory intended output slot, current security/clock,
event time, and cause
`LOCAL_BUILD_FAILURE | DEADLINE_ELAPSED | LOCAL_POLICY_OR_CONTEXT_REJECTED |
CALLER_CANCELED_BEFORE_RELEASE`. It excludes successor, selector, commits,
release receipt, and payload. Unknown, mixed, and post-release causes reject.

`CANCEL_TRUSTED_DELIVERY_RELEASE_RESERVATION` changes only the keyed pending
reservation to a permanent tombstone and emits
`TrustedDeliveryReleaseStateCommitReceipt` and
`TrustedDeliveryBoundaryGrantMapCommitReceipt`, exposes no payload, and
byte-preserves grant phase, siblings, releases/outbox items, and drains.
Committed items, active drains and released slots cannot cancel. Exact recovery
returns the commit/tombstone, never a replacement. Terminal/security cuts may
bulk-cancel only their complete pending sets.

Release specializes the common DAG:
`complete bytes/result + installed reservation ->
TrustedDeliveryReleaseOutboxCommitment -> exact-partition entry/map/outer
candidates -> release-state/map commits -> release receipt -> complete outbox
item`.

The outbox transaction reloads the exact post-reservation outer, map, and entry
heads. It derives the actual release sequence and output slot from those fresh
heads. It also creates fresh grant-currentness evidence, release CAS, and
validated CAS receipt. The atomic outbox CAS alone allocates the actual sequence
and slot. It also consumes the decision and quota and installs the release
counter successor.

The commitment binds the pending fence and the validated release reservation. It
also binds the neutral realm, full source, grant key, stable item, idempotency,
attempt namespace, and payload identity. It binds the actual output slot,
grant, scope, requester, descriptor, activation entry, release clock, and
immutable destination. The destination includes principal, endpoint, audience,
route, transport-security profile, and credential epoch. The commitment also
binds a fresh receipt-free `BOUNDARY_GRANT_RELEASE_NOT_AFTER` intent root.
Candidates bind that root. The transaction enforces one
commitment/item/actual-output-slot tuple.

The commitment excludes successors, selector, commits, release receipt,
complete payload, and outbox item. Successors bind only the commitment.

Two unrelated pending intents can contain the same advisory output slot. Their
outbox commits serialize through the outer selector and allocate distinct actual
slots. A commitment rejects if it treats an advisory slot as authoritative
without comparing the fresh outer head.

`maximum_release_count = 1` is a synthetic bridge bound. It gives no evidence
for larger-quota allocation, capacity, or concurrency. The general algorithm
needs independent manifest-bound proof.

Illustrative non-wire pending state:

```json
{"allocates_output_slot":false,"state":"PENDING_INTENT_ONLY"}
```

`TrustedDeliveryReleaseReceipt` binds commitment, prior/installed
outer/map/entry heads, selector, generic/map commits, queue slot, release
clock/time, enforcement receipt, local activation entry, neutral realm/full
source, and commit-bound deadline evaluation. Complete
`TrustedDeliveryReleaseOutbox` binds grant key, realm/source, commitment, and
release-receipt digest, and carries immutable bytes/result. One boundary-local
selector CAS persists successors, commits, receipt, and item. A loser exposes
nothing. External transport is outside that atomicity and drains only the
unchanged item.

This release cut is valid only if the durable outbox and drain adapter are inside
the named boundary's confidentiality perimeter and the item is cryptographically
or protocol-bound to the destination tuple. If plaintext leaves only at later
transport, that acceptance is the disclosure cut and this profile cannot be
claimed. Endpoint, principal, audience, route, security-profile, and
credential-epoch substitution reject. Drain moves an already authorized
immutable item and cannot choose a recipient.

Drain is not exactly-once without transport-proved same-key idempotency. Each
item fixes two cutoffs in separate
`TrustedDeliveryTransportDeadlineConditionIntent`:
`BOUNDARY_EXTERNAL_TRANSPORT_ACCEPTANCE_NOT_AFTER` is the conservative minimum of
the mapped destination-security/retention bounds and
`checked_add(release_instant, profile_max_transport_duration)`. The profile value
is a duration, never an absolute timestamp. Earlier
`BOUNDARY_EXTERNAL_TRANSPORT_ATTEMPT_NOT_AFTER` subtracts the qualified worst-case
duration from attempt installation through endpoint acceptance. Both use
exclusive comparison in the qualified acceptance clock domain. Neither changes
the release cut or revives authority. Missing mapping, overflow, missing duration
bound, or no positive residual window prevents drain.

The adapter owns durable `TrustedDeliveryExternalTransportGateState`:
`OPEN(epoch, exact_destination_security_context) | FENCED(epoch, cause, receipt) |
RETIRED`. The item binds exact epoch/context. A destination, route, security, or
boundary-authority cut fences that epoch before its release-selector CAS.
Old-epoch acceptance is then impossible. A lost CAS leaves the boundary
restrictive and requires exact-fence rebase over the current selector before
START or reopen. Grant terminalization does not retract a released item, which
still obeys its gate and cutoffs.

Before send, receipt-free `TrustedDeliveryExternalTransportDrainFact` binds
exact outbox bytes/item, grant, destination, stable release/idempotency key,
transport, gate epoch, both cutoff roots, and fresh attempt. The release-selector
CAS installs the bounded attempt and commit-bound checks the earlier cutoff
before the call. START is not acceptance. The named endpoint atomically checks
unchanged acceptance cutoff, destination/security, and gate epoch, then emits
`TrustedDeliveryExternalTransportAcceptanceDeadlineEvaluationReceipt`; equality
or later rejects.

The second selector CAS tombstones the attempt and installs
`TrustedDeliveryExternalTransportDisposition`:
`ACCEPTED_BY_TRUSTED_DELIVERY_TRANSPORT_BOUNDARY |
REJECTED_BEFORE_TRUSTED_DELIVERY_TRANSPORT_ACCEPTANCE |
AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT`. Accepted needs an authenticated
strict-before endpoint receipt and proves only named transport acceptance, never
observer/evidence admission. Rejected needs definitive authenticated
no-acceptance. Ambiguous binds the attempt and neither claim. Post-send crash
recovers ambiguous and does not infer acceptance or rejection. A successor
attempt keeps the exact committed bytes, item, release identity, idempotency key,
destination, and cutoffs. It uses a new attempt identity and the next attempt
sequence. It requires authenticated receiver deduplication proof bound to the
prior ambiguous disposition. Otherwise no retry. A definitive accepted or
rejected disposition forbids resend. The receiver deduplicates by stable release
receipt and item. No branch grants release or changes bytes. This design makes
no external exactly-once claim without transport and receiver qualification.

Terminalization cancels only pre-release work and preserves items/active
attempts. `TERMINATE_BOUNDARY_GRANT` and
`RESOLVE_EXTERNAL_TRANSPORT_DRAIN` share the selector. Terminal-first retains
the attempt and permits only disposition, not concurrent retry/replacement.
Disposition-first retains the result. First drain requires a complete item,
strict-before unchanged attempt cutoff, and LIVE or TERMINAL predecessor whose
fact inventories it as released. Equality/later installs typed terminal
no-attempt. Post-ambiguity retry, including in TERMINAL, keeps item identity and
exact idempotency/retry proof. Terminal, restart, capacity, and slot reuse cannot
evict item/attempt/disposition/tombstone/dedup identity before retention plus
authorization-closure and quiescence receipts.

Durable outbox ownership is boundary release linearization. A local
revocation/expiry/head/security change ordered first exposes nothing. One ordered
after sees a released item. Remote server state has no instantaneous local
order. No check-to-release or head-CAS-to-outbox gap exists. All-or-none history
is one item. A physical prefix is buffered and rejected until full length/digest
verification. Reply loss/restart restores exact selector/head/outbox, never an
uncommitted or incomplete release.

Delivery restart uses exact restore or receipt-free
`TrustedDeliveryBoundaryClockRestartBridge` through the outer selector. It
preserves principal/instance/domain and binds both clocks, uncertainty/policy,
prior outer/map, complete affected keys, and canonical
`TrustedDeliveryBoundaryClockRestartDeadlineMap`. The map covers every affected
grant deadline plus exact imported-mirror `security_mirror_not_after` and mapped
genesis/confirmation deadlines. Each entry binds key/version, old/new values,
and conservative no-later proof. Each PREPARED/LIVE grant uses
`MAP_BOUNDARY_GRANT_DEADLINE_NO_LATER |
TERMINATE_BOUNDARY_GRANT_ON_CLOCK_DISCONTINUITY`. Mapping binds its old receipt,
deadlines/feasibility, no-later prepare/release, recomputed activation/duration
upper image, and exact inequalities
`boundary_prepare_close <= boundary_latest_server_activation_at <
boundary_release_not_after` and
`boundary_latest_server_activation_at +
boundary_minimum_activation_budget_upper <= boundary_release_not_after`.
Equality expires. Unavailable bounds terminalize with exact
cancellations/tombstones and retained item/drain partitions.
The bridge also binds the canonical terminal subset, preallocated per-key
terminal receipt/return-envelope identities, one opaque
`TrustedDeliveryBoundaryClosureEvidencePublicationManifest` family identity,
one distinct completion identity, exact output counts and
hierarchy/retention reserve; a caller cannot choose the subset after the CAS.

One outer CAS installs clock, all affected successors, and unchanged outbox/drain.
Commits precede `TrustedDeliveryBoundaryClockRestartCommitReceipt`. Each
terminal branch also emits
`TrustedDeliveryBoundaryTerminalInstallationReceipt` with
`LOCAL_CLOCK_DISCONTINUITY`. Partial/extended maps, omitted siblings/receipts,
mixed clocks, and changed items reject. Unmappable mirror time installs or
preserves `FENCED_DENY`, closes the complete set, retires affected
grants/generations, and creates no reservation/outbox commitment. Existing
outbox items remain immutable original-key obligations. Restart cannot suppress
or relabel them or derive deadlines from restart/query/UTC/replay. A new boundary
instance cannot use the bridge or inherit preparation. It needs fresh
preparation/activation after old-instance distributed closure.
For a nonempty terminal subset, one pre-manifest commitment binds the exact
key-to-receipt/envelope bijection, one named family manifest owns that
deterministic closure-evidence family and the mandatory completion authenticates
the one-family set last. The hierarchy and retention record become durable
before exposure. An empty terminal subset emits no closure-evidence hierarchy.

Multi-boundary authority requires descriptor/scope enumeration. Each boundary
has its own `TrustedDeliveryBoundaryGrantEnforcementReceipt`, clock, no-later
deadlines, feasibility upper bound and
`boundary_minimum_activation_budget_upper` from the original plan. Complete
`ObserverGrantBoundaryInstallationSetReceipt` precedes LIVE; its source guard
checks complete ADR-009 target/receipt roots against every retained envelope and
boundary receipt without redistributing sibling members, and one bounded CAS
consumes all. No boundary supplies another's time/currentness. Queued items name
their releasing receipt; cross-provider or live/history substitution rejects
despite equal grant, bytes or UTC.

Observer admission is a separate evidence gate with its own local clock and one
composite installed currentness root. It rechecks the grant, descriptor revision/
digest, revocation state, verified transport principal, and receiver-local time
before bytes enter evidence. Issuer UTC timestamps are audit/interchange fields
and bound the declared duration; they are not compared to either monotonic clock.

The local grant state is the closed union
`PENDING_FIRST_ATTACH | LIVE | LIVE_RENEW_PENDING |
RENEW_PENDING_PREDECESSOR_CLOSED | DETACH_PENDING | TERMINAL`.
Only `LIVE` and the unchanged predecessor inside `LIVE_RENEW_PENDING` can admit a
frame. `RENEW_PENDING_PREDECESSOR_CLOSED` retains the exact G1 attempt and G0
closure proof but grants neither G0 nor G1 admission. The other branches
structurally forbid a current-grant authority claim.

The independent outer-root lifecycle is
`PENDING_SOURCE_CONFIRMATION | OPEN_ADMISSION |
EMERGENCY_FENCED_CLOSURE_PENDING |
EMERGENCY_FENCED_RECOVERY_REQUIRED | RETIRED_DRAIN_ONLY | TERMINAL`.
`ObserverAdmissionStateHead` binds exactly one value from this lifecycle.
Only `OPEN_ADMISSION` can start or install a request, grant, declaration or frame
admission. `PENDING_SOURCE_CONFIRMATION` and `RETIRED_DRAIN_ONLY` are deny-only.
The latter permits only exact closure, retention and finalization work.
`EMERGENCY_FENCED_RECOVERY_REQUIRED` is also deny-only. It contains a complete
terminal/no-restart partition for predecessor requests, grants, declarations,
frame admissions, callbacks and derived work, and permits only retained
immutable evidence, a newer emergency fence, retirement, or guarded recovery
rebind.
`EMERGENCY_FENCED_CLOSURE_PENDING` is deny-only but retains an unresolved
incident/work partition. It permits no generic current-state restoration.

Observer initialization uses the external parent registry to allocate one exact
realm, never-used admission-state incarnation, entry state and role selector
with typed selector absence.
`OBSERVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED` consumes that allocation
receipt, exact
`ExternalCompositeStateEnrollmentImportedSecurityGenesisEvidence`, marker and
selector absence once. `UNINITIALIZED` in the event name is not an installed
state. The
local transaction atomically installs
`PENDING_SOURCE_CONFIRMATION`, an authenticated `FENCED_DENY` mirror and
`PENDING_FIRST_ATTACH` with no request attempt and empty receiver substate.
`BEGIN_OBSERVER_GRANT_ATTACH_REQUEST` separately installs the
first exact attempt before network send. Missing, recreated empty, sibling, or
reused state after any use fences the evidence lineage. It cannot synthesize a
no-grant default or another genesis.

The closed observer-admission transition union is:

- `OBSERVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED`;
- `IMPORT_OBSERVER_GRANT_SOURCE_NAMESPACE_PERMANENT_CLOSURE`;
- `PREPARE_OBSERVER_GRANT_REQUEST_INTENT`;
- `RESOLVE_OBSERVER_GRANT_REQUEST_INTENT_WITHOUT_CHALLENGE`;
- `BEGIN_OBSERVER_GRANT_ATTACH_REQUEST`;
- `MARK_OBSERVER_GRANT_REQUEST_SERVER_ACCEPTANCE_AMBIGUOUS`;
- `OBSERVE_OBSERVER_GRANT_TERMINAL_RESULT_PENDING_CLOSURE`;
- `RESOLVE_OBSERVER_GRANT_ATTACH_REQUEST_WITHOUT_INSTALLATION`;
- `INSTALL_OBSERVER_GRANT_FROM_ACCEPTED_RESPONSE`;
- `BEGIN_OBSERVER_GRANT_RENEWAL_REQUEST`;
- `RESOLVE_OBSERVER_GRANT_RENEWAL_WITHOUT_INSTALLATION`;
- `INSTALL_OBSERVER_GRANT_RENEWAL_FROM_ACCEPTED_RESPONSE`;
- `BEGIN_OBSERVER_GRANT_REATTACH_REQUEST`;
- `RESOLVE_OBSERVER_GRANT_REATTACH_REQUEST_WITHOUT_INSTALLATION`;
- `INSTALL_OBSERVER_GRANT_REATTACHMENT_FROM_ACCEPTED_RESPONSE`;
- `BEGIN_OBSERVER_DETACH`;
- `COMPLETE_OBSERVER_DETACH_TRANSPORT_QUIESCENT`;
- `TERMINALIZE_OBSERVER_ADMISSION_GRANT`;
- `INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE`;
- `FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_PREPARED_CHANGE`;
- `FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_EMERGENCY`;
- `REBIND_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_AFTER_EMERGENCY`;
- `INSTALL_OBSERVER_RECEIVED_STREAM_DECLARATION`;
- `RETIRE_OBSERVER_RECEIVED_STREAM_DECLARATION`;
- `INSTALL_OBSERVER_RECEIVED_STREAM_REDECLARATION`;
- `INSTALL_OBSERVER_LIVE_ADMISSION_GENESIS`;
- `APPEND_OBSERVER_LIVE_FRAME_ADMISSION`;
- `FREEZE_OBSERVER_LIVE_ADMISSION_FOR_RETIREMENT`;
- `ALLOCATE_OBSERVER_EVIDENCE_LINEAGE`;
- `RETIRE_OBSERVER_EVIDENCE_LINEAGE`;
- `INSTALL_OBSERVER_LATE_ATTACH_ANCHOR`;
- `INSTALL_OBSERVER_HISTORICAL_ADMISSION_GENESIS`;
- `APPEND_OBSERVER_HISTORICAL_FRAME_ADMISSION`;
- `TERMINALIZE_OBSERVER_HISTORICAL_ADMISSION_FROM_HEAD`;
- `TERMINALIZE_OBSERVER_HISTORICAL_ADMISSION_FROM_ANCHOR`;
- `REPLACE_OBSERVER_ADMISSION_DESCRIPTOR`;
- `APPLY_OBSERVER_ADMISSION_CLOCK_RESTART`;
- `APPLY_OBSERVER_ADMISSION_SECURITY_CUT`;
- `RETIRE_OBSERVER_ADMISSION_SCOPE`;
- `FINALIZE_OBSERVER_ADMISSION_SCOPE_RETIREMENT`; and
- `EVICT_FINALIZED_OBSERVER_ADMISSION_RETENTION`.

The observer installs authenticated publisher declarations in receiver state.
These transitions do not grant the observer publisher authority. Accepted grant
responses install their resolution and live successor in one compare-and-swap.
The install fact consumes the exact
`ProtectedObserverGrantAcceptedResponseEnvelope`, passing verification,
its exact ADR-009 `CrossStoreSecurityReceiptVerificationEvidence`,
`ObserverGrantActivationPublicationManifest`, server `LIVE` heads/commits,
activation guard/set receipt, selected family-member proof, family-set proof,
authenticated `EXACT_PRODUCER_OUTPUT_SET_ATTESTED` producer-completeness
assertion, mandatory completion manifest, delivery capsule, issuance coordinate,
ledger ancestry and
`OBSERVER_ADMISSION_EXACT_SCOPE` projection. Candidate/installed authority
equals that projection and binds every LIVE coordinate. Pending/terminal state,
security/currentness mismatch, sibling/full-grant substitution, bare root or
unproved membership rejects. Ordinary verification checks the signed
completeness assertion and both inclusion paths. Exact inventory bijection is a
separate authorized-audit/conformance opening, not an ordinary recipient proof.

`ProtectedObserverGrantTerminalResultEnvelope` has the closed payload
`UNUSED_REQUEST_SLOT_TERMINAL |
GRANT_AUTHORIZATION_CLOSURE_DECISION`; the latter is the manifest-bound branch
above. Unused binds exact `CANCELED_UNUSED |
EXPIRED_UNUSED` freshness slot, request intent/stable key, requester/target,
outer/freshness-registry heads and commits, operation and source result
commitment. It excludes
`ObserverGrantRequestSlotTerminalPublicationManifest`. Both are ADR-009
permanent single-observer-root envelopes with exact replay/projection; the
manifest binds the unused envelope last. Every driven transition requires it and
passing
`CrossStoreSecurityReceiptVerificationEvidence`; a bare slot, head, receipt,
query result or sibling envelope rejects.

The unused-slot branch uses the matching no-installation transition. Local
response timeout alone does not. It uses
`MARK_OBSERVER_GRANT_REQUEST_SERVER_ACCEPTANCE_AMBIGUOUS`, preserves the exact
attempt and blocks every overlapping attach, renewal or reattachment for that
target. The observer never resolves and installs one response in separate
authoritative transitions. Each event uses the exact receipt-free fact or
content and mutation footprint from the B01 selector-closure matrix. An unknown,
default, inferred, or legacy alias rejects.

Local source-namespace closure import, its same-selector PREPARE race, complete operation partition and proof-exact permanent prepared-intent resolution are defined in the [cross-store observer closure and enrollment module](modules/adr-004-cross-store-observer-closure-and-enrollment.md). Those rules are a content-bound part of this ADR and prevent post-closure key exhaustion without blocking unrelated sources.

Before sending an attach, renewal or reattachment request, observer ingress
verifies the exact
`ProtectedObserverGrantRequestFreshnessChallengeEnvelope`, publication manifest,
inner challenge/receipt and passing cross-store evidence. It also verifies a qualified
`ObserverGrantRequestFreshnessClockRelation` from the challenge's authority-
clock incarnation into the current observer-clock incarnation. The relation
binds distinct source and target applicability horizons, correlated offset/rate
bounds, qualification identity and source receipt. Both horizons cover the
maximum possible `SERVER_GRANT_NOT_AFTER`. It derives conservative upper/later
observer-clock images for both pre-request server cutoffs. Checked
arithmetic must prove
`server_request_accept_not_after <= server_grant_installation_close` in the
server clock and
`upper(server_grant_installation_close) <=
OBSERVER_GRANT_RESPONSE_CLOSE <= OBSERVER_GRANT_ADMISSION_NOT_AFTER` in the
observer clock. For renewal, that upper image must also be no later than the
unchanged predecessor's local admission deadline. These are mapping proofs, not
raw cross-clock comparisons. A missing, stale, horizon-inapplicable,
uncertainty-erased or inverted relation cancels the unused server slot and sends
no grant request.

Observer ingress then records its local monotonic request-start time by compare-
and-swapping `ObserverGrantRequestAttempt` into
`ObserverAdmissionStateHead`. The attempt binds a never-reused attempt ID,
attach/renew/reattach kind, exact target and prior grant/admission head, observer
challenge and stable key copied from the prepared intent, complete server
challenge/commitment/receipt, exact intent, clock relation, both server cutoffs
and their observer-clock images,
observer clock policy/incarnation, request-start time and exclusive local
`OBSERVER_GRANT_RESPONSE_CLOSE` deadline. Reattachment begins only from the
exact local `TERMINAL` predecessor and binds
`ProtectedObserverGrantReattachmentOriginEvidenceEnvelope`, its publication
manifest, membership and passing verification, plus the matching inner
`ObserverGrantReattachmentOriginEvidence` and its current-role or
published-result branch. It cannot use the
initial-attach or renewal variant. The local response close is no later
than the caller's fixed local deadline. It is durable before network send.
Competing attempts cannot share either challenge or both become current. A
server challenge that is already at/effectively beyond either fixed cutoff is
canceled or expires unused; it is never sent to refresh time.

`OBSERVE_OBSERVER_GRANT_TERMINAL_RESULT_PENDING_CLOSURE` consumes an exact
ATTACH/RENEW/REATTACH attempt in `PENDING_RESPONSE |
AMBIGUOUS_SERVER_ACCEPTANCE`, its accepted server slot/grant, protected closure
terminal-result envelope, source decision, source-closure manifest and passing
verification. It changes
only that same-kind operation
`PENDING_RESPONSE | AMBIGUOUS_SERVER_ACCEPTANCE ->
TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE`: ATTACH enters local TERMINAL,
REATTACH preserves its terminal predecessor, and RENEW enters/preserves
`RENEW_PENDING_PREDECESSOR_CLOSED` while binding the G0 fence. It immediately
blocks a delayed LIVE response but does not claim local noninstallation closure.
Evidence-identical retry is a self-edge.
Only the matching attach/renew/reattach without-installation resolver can consume
this phase, and only with both aggregate closure classes plus local
noninstallation/no-frame proof. Security, clock, emergency and retirement cuts
preserve request kind, attempt and evidence and permit only this restrictive
accepted observation/resolution path or direct same-kind protected unused-slot
resolution in deny-only phases; a wrong-kind resolver rejects.

A detach attempt atomically installs `DETACH_PENDING`,
`ObserverDetachCompletionMemberSetRoot` and the frame fence before network send.
From LIVE the set contains that grant. From `LIVE_RENEW_PENDING`, the same CAS
fences G0, permanently blocks G1 response installation and retains the exact G1
attempt/kind; it then drives G0 closure and either protected G1 unused resolution
or accepted-G1 closure. Timeout cannot classify G1. A protected terminal decision
or `AUTHORIZATION_CLOSED` result advances only a restrictive DETACH_PENDING
self-edge and stores `DETACH_AUTHORIZATION_CLOSED`; it is not detach completion.
`COMPLETE_OBSERVER_DETACH_TRANSPORT_QUIESCENT` alone enters TERMINAL. It consumes
the exact member set, `ProtectedObserverGrantClosureResultEnvelope /
TRANSPORT_QUIESCENT` for every accepted member, unused proof for every
nonaccepted member, manifests and passing verifications. Exact retry returns the
same authorization-closed or quiescent result. The winning CAS invokes the
role-completion producer invariant for every accepted member whose local role
first closes. Lost reply/restart never
re-enables admission.

`TERMINALIZE_OBSERVER_ADMISSION_GRANT` likewise consumes the exact protected
closure envelope, decision branch, source-closure and closure-result manifests,
projection and passing verification. From LIVE it enters TERMINAL, fences
admission and invokes the role-completion producer invariant; DETACH_PENDING has
no such edge. A
G0 renewal-fence from `LIVE_RENEW_PENDING` instead enters
`RENEW_PENDING_PREDECESSOR_CLOSED`, preserves the G1 attempt/operation, and
fences G0 while invoking that invariant for G0. A never-installed G1 uses the terminal-result observation event,
never generic terminalization. Wrong requester, G0/G1 swap, bare source
receipt or stale replay loses the sole selector CAS.

An accepted authenticated response is only the protected LIVE response above.
Only `OPEN_ADMISSION/PENDING_RESPONSE` can install; ambiguous or deny-only state
cannot. It binds and consumes that exact current attempt, both challenges, LIVE
outer/registry/keyed heads and commits, activation guard/set receipt, operation
context, target projection and cross-store verification. Reattachment also binds
its origin; renewal binds the exact G0
fence envelope and predecessor closure. Its one CAS installs G1 from either
`LIVE_RENEW_PENDING` while atomically closing G0, or
`RENEW_PENDING_PREDECESSOR_CLOSED` using the retained closure; both orders yield
the same G1 LIVE state and operation `INSTALLED`; the order that first closes G0
invokes the role-completion producer invariant. A pending issuance package is not a response. The local
`ObserverGrantRequestOperationState` has closed phase
`ABSENT | INTENT_PREPARED | PENDING_RESPONSE | AMBIGUOUS_SERVER_ACCEPTANCE |
TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE |
RESOLVED_WITHOUT_INSTALLATION | INSTALLED`. Every transition to either final
phase creates one receipt-free
`ObserverGrantRequestOperationResolution` in the same composite head. Its closed
kind is `INTENT_RESOLUTION_WITHOUT_ATTEMPT |
ATTEMPT_RESOLUTION_WITHOUT_INSTALLATION |
INSTALLED_RESPONSE_RESOLUTION`. The first binds the prepared intent, exact
permanent-resolution evidence and local stable-key tombstone, and forbids an
attempt, server challenge, slot, response and grant. The second binds the exact
attempt and verified protected server query/cancel/closure result and forbids an
installed response. The third binds the exact attempt, protected accepted
response and resulting local grant fields. Every kind binds its closed outcome
and resulting operation/grant-state projection. It excludes the candidate,
installed successor head, selector version,
`ObserverAdmissionStateCommitReceipt` and installation receipt. The successor
binds the resolution; the post-CAS receipts bind the successor.
Same-operation retry returns the installed outcome and receipts; restart cannot
re-date or reconstruct a pending challenge from the response.

Each operation also stores monotonic
`ObserverGrantRequestVerifiedOutcomeState`:
`NO_VERIFIED_SERVER_RESULT_YET |
VERIFIED_ACCEPTED_LIVE |
VERIFIED_ACCEPTED_TERMINAL |
VERIFIED_CANCELED_UNUSED |
VERIFIED_EXPIRED_UNUSED |
VERIFIED_PERMANENT_SOURCE_STABLE_KEY_NOT_ISSUED |
VERIFIED_PERMANENT_ANCHOR_KEY_NOT_EXPOSED_AND_NO_LIVE_ACCEPTANCE |
VERIFIED_PERMANENT_ANCHOR_KEY_MAY_HAVE_BEEN_EXPOSED_ACCEPTANCE_PERMANENTLY_CLOSED`.
PREPARE,
BEGIN and ambiguity preserve the first value. A verified LIVE install changes
it to `VERIFIED_ACCEPTED_LIVE`; protected
accepted-terminal observation changes the first or LIVE value to
`VERIFIED_ACCEPTED_TERMINAL`; protected unused resolution changes the first
value to its exact unused state. Source frozen-index resolution changes only an
intent-prepared first value to
`VERIFIED_PERMANENT_SOURCE_STABLE_KEY_NOT_ISSUED`; independent-anchor resolution
changes it only to its proof-exact nonmembership or membership state:
`VERIFIED_PERMANENT_ANCHOR_KEY_NOT_EXPOSED_AND_NO_LIVE_ACCEPTANCE` or
`VERIFIED_PERMANENT_ANCHOR_KEY_MAY_HAVE_BEEN_EXPOSED_ACCEPTANCE_PERMANENTLY_CLOSED`.
Accepted-and-closed resolution preserves
`VERIFIED_ACCEPTED_TERMINAL`. No other cross-outcome edge exists. A cause label,
operation phase or timeout cannot self-certify this state.

At local response-close equality or later, a pending attempt moves only to
`AMBIGUOUS_SERVER_ACCEPTANCE`. It cannot claim that the server failed to accept,
cannot install a later grant response and cannot free the target for another
grant operation. Missing proof stays ambiguous/closed. The fixed relation prevents
first acceptance/activation after the local window, but ambiguity still covers a
pre-window winner with a lost response.

`RESOLVED_WITHOUT_INSTALLATION` always binds one closed
`ObserverGrantRequestOperationTerminalResolutionCause`:
`SERVER_SLOT_CANCELED_UNUSED |
SERVER_SLOT_EXPIRED_UNUSED |
ACCEPTED_GRANT_FULLY_CLOSED_WITHOUT_LOCAL_INSTALLATION |
PERMANENT_SOURCE_STABLE_KEY_NOT_ISSUED_BEFORE_LOCAL_ATTEMPT |
PERMANENT_ANCHOR_KEY_NOT_EXPOSED_AND_NO_LIVE_ACCEPTANCE_BEFORE_LOCAL_ATTEMPT |
PERMANENT_ANCHOR_KEY_PRESENT_ACCEPTANCE_PERMANENTLY_CLOSED_WITHOUT_LOCAL_ATTEMPT`.
The resolver derives, never accepts, its cause and successor. Canceled/expired
each bind exact attempt, matching protected unused-slot payload/envelope and
`ObserverGrantRequestSlotTerminalPublicationManifest`, freshness outer/registry
heads/commits and passing verification; they forbid grant/aggregate fields and
resolve directly from `PENDING_RESPONSE | AMBIGUOUS_SERVER_ACCEPTANCE`.
Each permanent cause binds the matching closed branch of
`ObserverGrantPreparedIntentPermanentResolutionEvidence`, exact prepared intent,
typed absence of any request attempt and the installed local stable-key
tombstone. It resolves only
`INTENT_PREPARED -> RESOLVED_WITHOUT_INSTALLATION` and forbids every server
slot, server challenge, accepted-grant and aggregate field. Cross-branch cause,
proof or hierarchy substitution rejects.
Accepted-and-closed resolves only from
`TERMINAL_RESULT_OBSERVED_PENDING_CLOSURE`; it binds exact consumed slot/grant,
protected terminal decision and verification plus
`ProtectedObserverGrantClosureResultEnvelope / TRANSPORT_QUIESCENT`, its
manifest, both aggregate receipts, and local noninstallation/no-frame proof. It
also invokes the same-CAS role-completion producer invariant with
`NEVER_INSTALLED_NO_FRAME`. It forbids unused-slot evidence. A cause label without these verifier truth
conditions, cross-branch fields, timeout, local cancel, one boundary receipt or
bare source terminal rejects.

Under `OPEN_ADMISSION` with no stronger cut, unused ATTACH preserves
`PENDING_FIRST_ATTACH`, unused REATTACH preserves TERMINAL, and unused RENEW
restores byte-identical G0 LIVE only when the same CAS compares G0 unchanged and
`STRICTLY_BEFORE` its original
`OBSERVER_RENEWAL_PREDECESSOR_ADMISSION_NOT_AFTER`. Otherwise the applicable
successor is restrictive TERMINAL or DETACH_PENDING. Accepted-and-closed ATTACH/
RENEW converges to TERMINAL; REATTACH preserves TERMINAL. Every emergency or
retired deny-only outer phase preserves itself and permits the same-kind unused
or accepted resolver but never install. Server acceptance consumes G0, so no
accepted cause restores it; pre-acceptance unused renewal can restore it only by
the exact guard above.

Local observer closure constructs receipt-free
`ObserverGrantRoleCompletionFact` with branch
`NEVER_INSTALLED_NO_FRAME | INSTALLED_TERMINAL_NO_NEW_ADMISSION`. Both bind the
exact request/grant, observer ADR-009 plan/projection and local-selector preimage.
Never-installed binds terminal-observed ancestry, the same-kind resolution
fact/projection and a complete empty frame/admission/action partition. Installed
binds the prior installed head, receipt-free terminal fact/projection and intended
terminal partitions for every frame, admission, callback and derived action. The
local successor candidate binds the fact. A bulk local closure binds the
canonical complete `ObserverGrantRoleCompletionFactSetRoot`, one fact and
preallocated receipt/envelope identity per affected accepted grant, the exact
conditional verification-class-to-family-key/manifest-identity map, one
distinct completion identity, exact count and hierarchy/retention reserve.
Post-CAS `ObserverGrantRoleCompletionReceipt` binds
prior/installed admission heads, selector/version, its fact and
`ObserverAdmissionStateCommitReceipt`.

Each receipt returns only in
`ProtectedObserverGrantRoleCompletionEvidenceEnvelope`, an ADR-009
`REGISTERED_SOURCE_AUTHORITY` specialization binding exact source, grant,
observer root, plan/projection, operation, local commits and replay domain.
`NEVER_INSTALLED_NO_FRAME` selects `PERMANENT_CLOSURE_TOMBSTONE`;
`INSTALLED_TERMINAL_NO_NEW_ADMISSION` selects `DURABLE_HISTORICAL_COMMIT`.
No caller or bulk operation can change or merge those verification classes.
One `CrossStoreProducerPreManifestBundleCommitment` binds the complete
single-member or bulk fact/receipt/envelope set and exact member bijection. One
`ObserverGrantRoleCompletionPublicationManifest` instance binds each nonempty
deterministic verification-class family. The permanent family is present if and
only if at least one never-installed member is present. The durable family is
present if and only if at least one installed-terminal member is present. The
mandatory completion manifest authenticates the exact one- or two-family set
last. Each consumer requires its selected family, both scoped proofs and
completion. Earlier objects exclude later ones. A zero-member bulk edge emits no
hierarchy. An empty or merged-class family, duplicate same-family manifest,
unexpected family, missing or second completion, omitted, duplicate, swapped or
cap-plus-one member rejects before mutation. The crash-complete local bundle
retains all before exposure.
This evidence is not a boundary-aggregation member, so accepted-and-closed
resolution has no dependency cycle.

`ADVANCE_OBSERVER_GRANT_ROLE_CLOSURE_EVIDENCE` is the sole non-authorizing
target-history writer for `SOURCE_PENDING_NEVER_LIVE`. It is a second
transaction, never a subordinate of the earlier source/target/ledger terminal
CAS. Only after the terminal producer family/completion hierarchy and
`ObserverGrantPendingNeverLiveClosureProof` exist does receipt-free
`ObserverGrantRoleClosureEvidenceAdvanceFact` bind those exact artifacts, the
source/target/ledger installed coordinates, current target entry and absent
origin key, preallocated record/writer/resolution/output identities and reserve,
deterministic record/status projection, idempotency operation and one closed
`ObserverGrantRoleClosureEvidenceAdvanceEligibilityProfile`:
`CURRENT_EXACT_SOURCE_TERMINAL_DESCENDANT |
SOURCE_AUTHORIZATION_RETIRED_AFTER_OBSERVER_FINALIZATION |
PARENT_FINALIZED_PENDING_CHECKPOINT`. The first binds the current source
generation and exact terminal descendant. The second binds the observer
finalization candidate/receipt and source-authorization retirement coordinate.
The third binds the parent-finalization/reconciliation receipt and retained
pending-checkpoint entry. Cross-branch fields reject. The fact excludes
candidates, commits, receipts and protected output.

One target-history CAS binds that fact and changes only the record set and
derived role status. Post-CAS
`ObserverGrantRoleClosureEvidenceAdvanceReceipt` binds the exact prior/installed
target heads, generic target-history commit, fact, selected eligibility and
installed record. Then the writer creates the record resolution,
role-resolution envelope, `CrossStoreProducerPreManifestBundleCommitment`, sole
role-resolution family manifest and mandatory completion manifest. It exposes
none before the complete second hierarchy is durable. The
eligibility branches map one-to-one, in the order above, to the mutable target
entry phases
`CURRENT_SOURCE_GENERATION |
SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION |
SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION`. Checkpoint,
permanent seal or a changed same-origin record wins by selector order and makes
later input archive-only. Exact replay returns the retained bytes.

For returned local evidence,
`RECORD_OBSERVER_GRANT_ROLE_COMPLETION` first constructs receipt-free
`ObserverGrantRoleCompletionRecordingFact`. It binds the exact prior target
entry/record set, absent `LOCAL_ROLE_COMPLETION` key, protected local envelope,
authenticated family and completion manifests, delivery capsule and passing
verification, plan/grant/projection,
expected ADR-009 marker state, deterministic successor record/status projection,
reserve delta and idempotency operation. It excludes candidates and receipts.
Its closed `ObserverGrantRoleCompletionRecordingProfile` is
`OPEN_MARKER_JOINT_CLOSE |
ALREADY_CLOSED_TARGET_ONLY |
FINITE_NO_MARKER_TARGET_ONLY`. The open profile makes the ADR-009 lineage-close
commitment bind this fact and atomically changes the open marker plus target
record. The already-closed profile uses
`ExternalSecurityDerivedAuthorityClosedMarkerReadCondition`, preserves the exact
pending-never/emergency/final close receipt and changes only target history. The
finite profile proves typed marker inapplicability and also changes only target
history. Wrong plan, terminal origin or local-evidence branch rejects.

The joint post-CAS order is common transaction receipt, generic target-history
and ADR-009 ledger commits, sibling
`ObserverGrantRoleCompletionRecordingReceipt` and lineage-close receipt, record
resolution, the ADR-009 lineage-close envelope and
`ProtectedObserverGrantRoleClosureEvidenceResolutionEnvelope`, one
`CrossStoreProducerPreManifestBundleCommitment`, then exact
`ExternalSecurityDerivedAuthorityGrantLineageClosePublicationManifest` for the
ledger-close family and
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest` for the
role-resolution family. The mandatory shared completion manifest authenticates
both families last, and both verifications follow it. Neither family manifest
owns the other envelope or the entire producer. A target-only recording receipt
binds the target commit plus its exact closed-marker read condition or
finite-plan proof and follows the same suffix with only the role-resolution
family plus mandatory one-family completion; it invents no ledger artifact.
Missing or duplicate applicable family, a second same-family manifest, extra
family, second completion or family-only verification rejects.
The retained idempotency result fixes every applicable receipt identity and byte
string. Candidates bind no future receipt.

`RECONCILE_OBSERVER_GRANT_ROLE_SOURCE_CLOSURE` implements the ADR-009
origin-specific reconciliation contract for whole-root emergency/final,
finite-horizon and qualified-isolation evidence. Its finite branch is the sole
finite-record writer and binds the exact plan, prior record set, absent origin
key, no-further-minting ancestry, clock/restart chain and `AT_OR_AFTER`
commit-time deadline intent/evaluation; it has no marker or lineage-close
receipt. Its bounded complete partition binds the mutable-member count,
preallocated record-resolution/envelope identities for every mutable member,
one opaque operation-scoped family-manifest identity, one distinct
completion-manifest identity, exact output counts and worst-case reserve. It
adds only compatible records to mutable entries, preserves all prior records and
routes published/advanced/sealed members archive-only. The exact
`ObserverGrantRoleSourceClosureReconciliationReceipt` binds the installed union.
For a nonempty mutable set, all member record resolutions and distinct
role-resolution envelopes are sidecars of that one transaction. One
`CrossStoreProducerPreManifestBundleCommitment` binds the aggregate receipt and
the exact member-to-resolution/envelope bijection. The sole
`ObserverGrantRoleClosureEvidenceResolutionPublicationManifest` family manifest
owns the complete role-resolution family; the mandatory completion manifest
authenticates that one-family set last. Each member consumes both scoped
membership proofs and receives no sibling envelope, receipt, identity or
sidecar. A second same-family manifest, extra family or second completion
rejects. A zero-mutable-member
partition performs no target-history write and emits no receipt, protected
output, pre-manifest commitment or family/completion manifest. Archive-only
members cannot mint a continuation artifact. The reserve covers one bounded
batch, both manifest identities and every member; exact cap commits and
cap-plus-one rejects before mutation.
Local recording, source reconciliation, checkpoint publication
and permanent seal race on the same target-history selector; all winning orders
converge by set union. Same-record replay consumes no version. A changed
same-origin record, wrong trust disposition or sealed mutation cannot authorize
continuation.

Every local transition that first proves an accepted observer grant has no
remaining admission, callback or action authority binds the applicable
`ObserverGrantRoleCompletionFact` in that same local selector CAS and retains
its receipt/envelope/family/completion hierarchy. This includes accepted-without-install
resolution, `TERMINALIZE_OBSERVER_ADMISSION_GRANT`, strong detach completion,
either renewal order that first closes G0 while retaining G1, successful G1
install that closes G0, and any bulk security/clock/retirement closure. A local
terminal state without this bundle cannot satisfy observer-role recording,
checkpoint publication, current-generation reattach or retirement.

The observer independently derives local monotonic
`OBSERVER_GRANT_ADMISSION_NOT_AFTER` no later than
`request start + granted_live_duration`. At accepted-response install, the
bound relation maps exact server `SERVER_GRANT_NOT_AFTER` to its conservative
lower/earlier observer-clock image. The local cutoff must be no later than that
image; equality is valid between the two exclusive cutoffs. The same local CAS
verifies the ephemeral response envelope strictly before that bound. If server
activation used a later coordinator incarnation, the response and local fact
also bind the complete installed `OBSERVER_AUTHORITY_CUTOFF` lower-purpose
restart chain from the challenge clock. The observer maps the original source
expiry through its original relation or a checked composition; an S1 value
cannot enter an S0 relation. An accepted attach, renewal or
reattachment installs only when the winning selector transaction proves
`STRICTLY_BEFORE` for the exact canonical base deadline pair
`OBSERVER_GRANT_RESPONSE_CLOSE` and
`OBSERVER_GRANT_ADMISSION_NOT_AFTER` in the same observer clock incarnation.
For renewal, the exact set additionally contains
`OBSERVER_RENEWAL_PREDECESSOR_ADMISSION_NOT_AFTER` copied from the installed
predecessor. The begin-renewal transition and accepted-response transition each
prove it strict-before; neither can replace it with the successor deadline.
Equality with any applicable deadline rejects local installation and moves or
keeps the attempt in `AMBIGUOUS_SERVER_ACCEPTANCE`; local expiry alone never
selects `RESOLVED_WITHOUT_INSTALLATION`. That state has exactly two evidence
classes. An authenticated `CANCELED_UNUSED | EXPIRED_UNUSED` server-slot result
selects its matching unused cause. An authenticated accepted result selects only
the accepted-and-fully-closed cause, with complete grant termination,
distributed authorization closure, transport quiescence, local noninstallation
and no admitted frame. The response cannot omit the stricter request or
predecessor deadline, source expiry, lower image or mapping proof. Canonical
`ObserverAdmissionStateHead` binds the admission-state
incarnation/version, one exact parent-enrolled `AuthorityRealmKey`, the current
local ADR-009 `ImportedRealmSecurityMirror`, and closed local grant-state
branch. A live branch binds the full source identity, grant and installed
server LIVE outer/registry/keyed heads and commits, activation guard/set receipt,
accepted-response envelope, descriptor revision/digest,
challenge, duration, request-start time, installation time, local deadline,
source expiry, lower image/proof, observer
clock policy/incarnation and revocation/security state; a non-live branch forbids
grant/source authority fields except the root realm, security mirror and exact
consumed predecessor evidence required for renewal/detach audit. The head also
binds a bounded map of ADR-005 per-stream
frame-admission heads, the bounded `ReceiverEvidenceLineageRegistryHead`,
prepared/pending/ambiguous/terminal request-operation states, and its prior local
head. It excludes
its own digest, selector, receipt, and every successor.

Boundary and observer mirrors share one ADR-009 contract: exact realm/source
head-selector-version-commit, epochs, mirror incarnation/version, propagation
policy, exclusive `security_mirror_not_after` and monotonic ancestry. Only
`CURRENT × REGISTERED_ACTIVE × CURRENTLY_REAUTHORIZED` plus fresh attestation,
manifest authorization and clock relation authorizes; pending/stale/retiring or
non-`CURRENT` fences, permanent/domain retirement retires, and unknown rejects.
Each realm needs a distinct parent-enrolled root. For observers,
`INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE` uses the sole admission selector and
the complete affected grant/request/unadmitted-frame set. Only first fresh import
changes `PENDING_SOURCE_CONFIRMATION/FENCED_DENY ->
OPEN_ADMISSION/CURRENT_IMPORT`; refresh cannot. Planned fencing co-commits this
root's `PlannedSecurityExternalEnforcementFenceReceipt`. Restrictive permanent
retirement needs no active attestation and can move pending state to
`RETIRED_DRAIN_ONLY` for atomic role/parent finalization.

The native mapping of the closed ADR-009 imported-mirror union is:

| ADR-009 event | Trusted-delivery native transition | Observer native transition | Required installed effect |
|---|---|---|---|
| `IMPORTED_REALM_SECURITY_MIRROR_GENESIS_FROM_AUTHENTICATED_SOURCE_RECEIPT` | `RELEASE_STATE_GENESIS_FROM_UNINITIALIZED` | `OBSERVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED` | Verify exact `ExternalCompositeStateEnrollmentImportedSecurityGenesisEvidence`, including registration hierarchy and both currentness families; install outer `PENDING_SOURCE_CONFIRMATION`, mirror `FENCED_DENY` and its receipt. |
| `IMPORT_AUTHENTICATED_REALM_SECURITY_SUCCESSOR` | `INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` | `INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE` | Verify global/per-key ancestry and both closed ADR-009 evidence dimensions. Exact current-authorization plus `COMPLETE_CURRENTNESS_HIERARCHY` installs `CURRENT_IMPORT`; exact current-authorization plus `NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` imports the newer coordinate as `FENCED_DENY`. Global non-`CURRENT` ancestry without a root projection installs only fence/no-entry-claim. |
| `REFINE_IMPORTED_REALM_SECURITY_MIRROR_WITH_SAME_HEAD_ROOT_EVIDENCE` | `INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` | `INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE` | Preserve the exact imported global head and add one newly verified retirement-pending or permanent root hierarchy. Advance the native outer version; pending stays fenced and permanent routes to retirement. |
| `FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_PREPARED_CHANGE` | Same named trusted-delivery event | Same named observer event | Consume the exact root directive. Import-and-close or close an already imported byte-identical prepared head; both co-commit the local work partition and planned fence receipt. |
| `FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_EMERGENCY` | Same named trusted-delivery event | Same named observer event | Either closed mode preserves `FENCED_DENY`, closes the complete source-ledger/local-work bijection, installs `EMERGENCY_FENCED_RECOVERY_REQUIRED` and emits `ExternalCompositeEmergencyAuthorityClosureReceipt`. |
| `REBIND_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_AFTER_EMERGENCY` | Same named trusted-delivery event | Same named observer event | Installed closure takes recovery-required to open/current. Finite elapsed takes open/fenced or closure-pending to open/current only with no-live-work CAS. Both require the recovery base, latest gap-free `CURRENT` authorization hierarchy and both matching durable/ephemeral currentness families, capsules, proofs and shared completion. |
| `REFRESH_IMPORTED_REALM_SECURITY_MIRROR_CURRENTNESS` | `INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` | `INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE` | Import a newer per-key head against the same accepted global head/authorization, preserving global semantics. Require current-authorization hierarchy, both currentness families/shared completion and clock relation. Same/sibling/mismatched heads reject; expiry fences while retaining ancestry. |
| `FENCE_IMPORTED_REALM_SECURITY_ON_EXPIRY_OR_UNCERTAINTY` | `INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` | `INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE` | Install `FENCED_DENY` at cutoff equality or uncertainty and close the complete not-yet-authorized local work set. |
| `RETIRE_IMPORTED_REALM_SECURITY_MIRROR` | `INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` | `INSTALL_OBSERVER_SECURITY_MIRROR_UPDATE` | Consume exact never-activated or active-retirement permanent hierarchy, including same-global-head refinement, or exact global `DOMAIN_RETIRED`. Install `RETIRED`, move the outer root to drain-only and retain the mirror-key tombstone. |
| `RETAIN_PREVIOUSLY_ADMITTED_EVIDENCE_AFTER_SECURITY_FENCE` | Exact drain, quiescence or retention transition for an already released immutable outbox item | Exact evidence append, closure or retention transition for a pre-fence admission receipt | Preserve `FENCED_DENY`; bind `PreviouslyAdmittedSecurityEvidenceRetentionCommitment`; grant no new release, callback, admission or success. |

Every row advances the one native outer selector or installs its genesis.
Every mirror mutation emits `ImportedRealmSecurityMirrorTransitionReceipt` with
the native outer publication receipt. The retention row preserves the mirror
value but still orders on the same outer selector as every competing local
authority-bearing action. A separate mirror selector or cross-store CAS is
forbidden.

Every row that installs `CURRENT_IMPORT`, and every
`NEW_AUTHORITY_OR_ADMISSION` child CAS that relies on it, binds the applicable
ADR-009 `RealmSecurityDeadlineConditionIntentSetRoot`, including
`IMPORTED_SECURITY_MIRROR_NOT_AFTER`. Its native commit receipts and persistence
manifest bind the matching
`RealmSecurityDeadlineConditionEvaluationSetRoot`. This security family is
distinct from the observer/grant deadline family, although one transaction may
evaluate both at the same authorization-linearization instant. Missing either
set denies; cutoff equality fences.

For planned fencing, an active registered root that is already
`FENCED_DENY` still installs a new native outer successor. The exact
`FENCED_DENY -> FENCED_DENY` case binds the authenticated prepared source head,
`CLOSE_ALREADY_IMPORTED_SAME_PREPARED_CHANGE`, exact protected directive
envelope/family/completion/capsule/proofs and passing verification,
planned-core-scoped `PlannedSecurityExternalEnforcementRootKey`, its one exact
`RegisteredExternalSecurityEnforcementRootKey`, external-root-set commitment
and complete preauthorized-work partition. The planned key cannot relabel,
merge or persist as the source-registry identity. If that partition is empty,
the event binds proved emptiness. It co-commits
`PlannedSecurityExternalEnforcementFenceReceipt`; a no-op, remote receipt or
skipped outer version cannot acknowledge the planned fence.

If the root is disconnected, ADR-009 can instead consume
`PREPARED_CAPTURED_DERIVED_AUTHORITY_HORIZON_ELAPSED` only when PREPARE captured
its exact per-key issuance high-water and every derived local authority has a
finite enforced final boundary. That source evidence does not claim this local
root terminal or mutate it. The old local window expires; successor authority
still requires a later parent-current child CAS importing the successor global
head, fresh per-key attestation and current manifest authorization.

`InstalledObserverAdmissionStateSelector` solely owns receiver grant, descriptor,
security, clock and frame-admission currentness. The common DAG emits
`ObserverAdmissionStateCommitReceipt` over prior/installed heads, exact selector
identity/incarnation/version/digest, installation commitment and evaluations.
Grant install also emits `ObserverGrantInstallationReceipt` over those composite
heads, selector/publication receipt, consumed attempt, grant/descriptor,
accepted-response envelope, server LIVE heads, activation-set receipt, source
expiry and local image/proof. A frame receipt binds its one changed ADR-005 head
and the same composites. Siblings are preserved; subordinate selectors,
peer-chosen time and server/boundary receipts cannot substitute.

`RETIRE_OBSERVER_ADMISSION_SCOPE` changes
`PENDING_SOURCE_CONFIRMATION | OPEN_ADMISSION |
EMERGENCY_FENCED_CLOSURE_PENDING |
EMERGENCY_FENCED_RECOVERY_REQUIRED` to
`RETIRED_DRAIN_ONLY`. It atomically fences every request and frame-admission
path. It preserves already-admitted immutable evidence and the exact closure
obligations for each consumed server request, installed grant, declaration and
evidence lineage.

`FINALIZE_OBSERVER_ADMISSION_SCOPE_RETIREMENT` alone changes
`RETIRED_DRAIN_ONLY` to `TERMINAL`. Its receipt-free
`ObserverAdmissionScopeRetirementFinalizationFact` binds complete keyed proofs
that:

- every request operation has one terminal resolution;
- every accepted server grant is locally installed or has the exact
  accepted-and-fully-closed terminal cause;
- every installed grant has distributed authorization closure and transport
  quiescence;
- every declaration and frame-admission head is terminal;
- every evidence lineage is retained under policy or permanently fenced; and
- the mirror is `FENCED_DENY | RETIRED` with no authority-bearing successor.

The fact additionally binds closed
`ObserverAdmissionRetirementSourceGrantCutEvidence`:
`SOURCE_RETIREMENT_PENDING_CAPTURED_HIGH_WATER |
QUALIFIED_PERMANENT_SOURCE_GRANT_ISOLATION`. The normal branch consumes the exact
ADR-009
`ProtectedExternalSecurityEnforcementRootRetirementPendingEnvelope`, selected
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest`, producer
completion, delivery capsule, both scoped proofs, inner
`ExternalSecurityEnforcementRootRetirementPendingReceipt` and passing
verification for this registered observer root and binds its grant-ledger
incarnation, maximum sequence, captured exclusive-next/optional-last high-water,
open-marker root and selector coordinates. Its complete map accounts for every allocated sequence through that high-water as locally
installed-and-closed or accepted-and-fully-closed-without-installation. The
isolation branch binds permanent isolation of every source issuance, grant,
credential, network and restart path and a complete local no-new-admission
partition; it makes no fabricated source-allocation claim. Missing or stale
high-water, an unaccounted source grant, or generic disconnection blocks local
finalization.

The same qualified local transaction compares the observer selector and exact
parent enrollment entry. It installs the observer `TERMINAL` head and changes
the parent entry from `INSTALLED` to `PERMANENTLY_RETIRED`.
`ObserverAdmissionScopeRetirementFinalizationReceipt`,
`ExternalCompositeStateEnrollmentRegistryCommitReceipt` and
`ExternalCompositeStateEnrollmentFinalRetirementReceipt` bind the one installed
pair. The persistence manifest binds all three receipts last. Neither terminal
state can commit alone.

Authenticated ingress records receive and admission times in that same clock
incarnation. The complete enforcement ordering is
`request start <= install <= receive <= admission <= current verifier time <
OBSERVER_GRANT_ADMISSION_NOT_AFTER`; equality with the admission deadline is
expired. The install step additionally proves `install <
OBSERVER_GRANT_RESPONSE_CLOSE` as specified above. Both
trusted delivery and observer admission must occur while their independently
enforced copy of the exact current grant is live. An earlier receive timestamp
cannot authorize a queued frame after the observer deadline. Reinstalling the
same grant tuple reuses its persisted original request-start/deadline receipt and
cannot reset lifetime. A renewal request and response must both cross their
respective server and observer boundaries before the predecessor deadlines and
the renewal response must satisfy all three canonical observer deadlines; a late
response cannot resurrect the predecessor and requires fresh reattachment.
An observer restart creates a fresh clock incarnation and requires
`ObserverGrantClockRestartBridge` bound to the exact installed prior
head/receipt, grant/server entry, old/new clocks, conversion/uncertainty and
complete `ObserverGrantClockRestartDeadlineMap`. Each entry binds its
grant/attempt or mirror key, deadline kind, old/new value and conservative
no-later proof. A live grant preserves exact source `SERVER_GRANT_NOT_AFTER`
and remaps its lower local image without extension. A pending attempt composes
its stored source relation into the new observer clock across the full source
horizon or remains noninstallable. The bijection covers all live grants/pending requests; renewal's
response-close, successor and predecessor admission cutoffs; and distinct mirror
`security_mirror_not_after`, mapped genesis and mapped confirmation entries.
Missing, extra, duplicate, merged or extended entries reject. The sole-selector
CAS emits
`ObserverGrantClockRestartCommitReceipt` over bridge, prior/installed heads and
selector version. Equality expires; replay/sibling/second conversion rejects.
Unmappable mirror time installs or preserves `FENCED_DENY`; affected grants
expire and reattach waits for a qualified import. Restart/receive/UTC time never
derives a deadline. Frame IDs, positions, sequences, intervals and times are
canonical JSON-safe values before semantic use. A live
subscription does not require a history entitlement. A history result requires
one exact enumerated declared stream digest and bounded window. Independently
authorized tuple components cannot be recombined. Current publisher state cannot
authorize an unenumerated historical publisher or stream epoch. These checks also
apply to bytes queued before renewal or revocation.

The immutable admission receipt binds current descriptor/manifest/grant/server
entry, neutral realm/full source, revocation, transport principal, receiver
clock/time/lineage, prior/installed composite selector/heads and ADR-005 heads;
history also binds `ProviderHistoryProvenance`. ADR-005 owns position/replay/gap/
conflict. One installed stream/lineage head makes live/history at one position
converge on one content identity; conflict alarms. Renewal changes provenance,
not replay. Admission races renewal/revocation on the composite selector, so an
old-grant frame commits before the cut or loses. Capture preserves the original
receipt/content; missing installed currentness records a gap or detaches, and
self-attested high-water is invalid.

Declaration retirement freezes that live head into an authenticated retirement
anchor. While the descriptor still authorizes post-retirement history, one
bounded history-admission head can advance from that anchor for the same
receiver-evidence lineage. Under ADR-005 it admits only unseen positions in the
exact descriptor-authorized window, preserves original gaps, and retains a
terminal checkpoint through the immutable-evidence horizon. Capacity eviction
first fences/finalizes the lineage. A fresh explicit lineage cannot merge with
it to claim continuous or duplicate-free capture.

A receiver first attached after retirement can use an authenticated genesis
retirement anchor only in a proved-fresh evidence lineage selected through the
subordinate `ReceiverEvidenceLineageRegistryHead` in the currently installed
`ObserverAdmissionStateHead`. It binds the declaration tombstone, exact
descriptor revision/history grant, empty local live-admission state, and
`live_delivery_completeness = not_assessed`. It cannot replace lost or ambiguous
state; historical/sibling emptiness does not authorize. Allocation and first
history admission consume the exact never-used substate and race grant/security
cutover and frame heads on `InstalledObserverAdmissionStateSelector`; the
registry has no independent tip.

The observer principal can subscribe or query only within one exact scope entry.
Permission for separate component values does not grant their Cartesian product.
A grant may include read access to exact `CommandFrame` routes when the owner and
privacy policy permit it. That access exposes a command proposal only. The
observer joins it to a body disposition by exact command identity and original
digest, session, and generation. A disposition proves only the state transition
that its authenticated prior-digest chain contains. The accepted transition graph
starts at `received`, can reject there, and can reach an application or terminal
state only through an explicit `admitted` record. A standalone terminal label does
not prove earlier admission. The observer never infers admission, application, or
physical effect from proposal bytes, a terminal label, temporal proximity, or a
missing disposition. Authenticated sensor delivery proves delivery of the bound
measurement bytes; it does not prove physical truth, effect, or causality.

The observer descriptor does not let an assessor self-assert the body's current
authority term. An observer can cite authority state only through an exact
privacy-authorized body-issued descriptor or disposition capture and its
authenticated receipt. ADR-008 does not require that optional correlation:
Haldir stamps its own current policy revision after authenticating assessment
ingress and permits evaluation only at a strictly later revision. If a Haldir
profile requires body-authority correlation and the observer scope contains no
such exact capture, the correlation is explicitly absent and the assessment is
record-only.

NCP assigns no research-axis meaning. Translation uses a consumer-owned,
authenticated trust root and bounded content-addressed registry. Canonical
`ConsumerSemanticCaptureStateHead` binds:

- consumer owner/principal, exact `consumer_owner_trust_state_digest`,
  never-reused incarnation, strictly increasing version, and prior-head digest
- current `ConsumerSemanticRegistryHead`
- bounded open/closed segment heads with exact neutral-realm/full-source keys and
  last sample/admission receipts
- bounded canonical captured `AuthorityRealmKey` set and registry/segment
  retention state.

Both heads exclude self digest/receipt and successor/selector digests.
`InstalledConsumerSemanticCaptureStateSelector` solely owns registry, segment,
append, cutover, retention, and terminal currentness. Under the common DAG,
`ConsumerSemanticCaptureStateCommitReceipt` binds prior/installed heads, exact
selector identity/incarnation/version/digest, installation commitment, and
evaluations. Registry mutation also emits
`ConsumerSemanticRegistryHeadCommitReceipt`, binding prior/installed composite
and registry heads, selector, capture receipt, and affected segments.

Genesis consumes parent allocation, `ALLOCATED_NEVER_USED`, typed absence, and a
never-used incarnation under immutable `consumer_owner_trust_state_digest`.
Provider/body trust, embedded keys, historical/sibling state, and caller
registries grant nothing. Capture phase is
`OPEN_CAPTURE | RETIRED_DRAIN_ONLY | TERMINAL`.
`CAPTURE_STATE_GENESIS_FROM_UNINITIALIZED` takes typed absence, never an
installed `UNINITIALIZED`, to `OPEN_CAPTURE`, makes the parent `INSTALLED`, and
emits parent commit, capture publication/installation receipts, and final
manifest. `FENCE_CAPTURE_ON_OWNER_TRUST_CHANGE` races append/cutover on the sole
selector, closes every open segment at its exact last admitted sample, retires
the incarnation to drain-only, and requires new parent allocation.

Only `TERMINALIZE_CAPTURE_STATE` takes drain-only to terminal. Receipt-free
`ConsumerSemanticCaptureRetirementFinalizationFact` binds the installed
`ConsumerSemanticRegistryTerminalCommitment`, registry-finalization receipt,
complete closed segments, retention, and permanent lineage/tombstones. One
qualified capture/parent-selector transaction installs terminal and changes
parent `INSTALLED -> PERMANENTLY_RETIRED`. It emits
`ConsumerSemanticCaptureRetirementFinalizationReceipt`,
`ExternalCompositeStateEnrollmentRegistryCommitReceipt`, and
`ExternalCompositeStateEnrollmentFinalRetirementReceipt`. The parent manifest
binds both heads and all receipts last. Neither half commits alone.

Capture accepts only installed receiver-admission or other role-qualified
immutable-evidence receipts, never raw provider bytes or provider authority.
Later provider security change requires no remote live comparison and cannot
erase admitted evidence. Each sample/segment preserves its receipt's
realm/security digest. Owner-trust change still races append on the selector.

The closed transition union is:

- `CAPTURE_STATE_GENESIS_FROM_UNINITIALIZED`;
- `INSTALL_SEMANTIC_REGISTRY`;
- `OPEN_CAPTURE_SEGMENT`;
- `APPEND_CAPTURE_SAMPLE`;
- `CLOSE_CAPTURE_SEGMENT`;
- `CUT_OVER_SEMANTIC_REGISTRY`;
- `EVICT_FINALIZED_CAPTURE_RETENTION`;
- `FENCE_CAPTURE_ON_OWNER_TRUST_CHANGE`; and
- `TERMINALIZE_CAPTURE_STATE`.

Registry cutover closes the complete canonical affected-segment set and installs
its successor in one CAS. Generic capture kinds claim no Prisoma-specific
payload. Each event uses the exact fact/content and B01 selector-closure
footprint. Unknown, default, inferred, and legacy aliases reject.

Each registry entry binds exact stream digest, plane/route/class/channel, schema,
provider contract, projection/transform, consumer axis contract, ordered
members, units/arity/frame/domains, neutral `AuthorityRealmKey`, and full source.
Segment open/append/close binds exact prior composite head/version/commit,
registry digest, and entry, independently of provider trust. Acyclic order is
`segment[n] -> composite[n-1]/commit[n-1] -> composite[n] -> post-CAS
commit[n]`. Segments exclude successors, receipts, and inline replacements.
Manifests bind installed composite/registry heads, selector, and receipts.
Historical responses cannot assert currentness.

Append and cutover share the selector. Cutover derives all affected closed
subheads from the prior composite, closes the complete bounded open set at exact
last sample/admission receipts, installs the registry successor, and emits
`ConsumerSemanticRegistryCutoverReceipt` over prior/installed composite and
registry heads, selector version, and closed set. A racing sample is the exact
last pre-cut member or loses. Unproved cutover stops capture. Only successor
segments can open.

Every segment/sample key contains
`(AuthorityRealmKey, source_session_kind, logical_session_id, generation,
declared_stream_digest, stream_epoch, receiver_evidence_lineage)`. Missing or
default realm, realm/descriptor/grant/admission mismatch, or realm-dropping
projection rejects before append. Textually equal values from different realms
remain distinct and cannot share continuity or deduplication lineage.

Registry updates preserve closed-segment verification. Archived validation joins
capture-time receipt and lineage/retention to an installed head or
`ConsumerSemanticRegistryTerminalCommitment`. That commitment binds owner,
state/registry incarnations, final heads/digests/versions, last commits,
ancestry, closed intervals, and retention, while excluding itself,
finalization, and successors. Parent-tombstone `TERMINALIZE_CAPTURE_STATE`
installs it and emits `ConsumerSemanticRegistryFinalizationReceipt` over prior
heads, commitment, selectors, and owner. Later samples reject.
Historical/sibling/rollback/unretained state, interval mismatch, missing
last/genesis/final receipt, and fabricated empty terminal prove nothing. Install
the commitment or fence before discarding proof.

Before translation, the consumer recomputes registry and axis-contract digests
and compares every segment field with the authenticated descriptor, declared
stream, frame, projection, and installed entry. Unknown contract, same-shape
relabel, stream/axis mismatch, transform change, or registry
rollback/sibling/current-head mismatch denies new segments. Archived segments
require exact capture-time receipt and lineage/retention proof. Policy may retain
an exact raw admitted frame as unmapped evidence, never as a guessed axis. The
consumer owns the mapping. Publisher authentication does not endorse it.

When the consumer contract requires cross-stream source correlation, every
member resolves to one exact authenticated local
`ResolvedCaptureSourceCorrelation`. An origin `SensorFrame` derives portable
identity from admitted original bytes or exact `TrustedProjectionRecord` plus
local `TrustedProjectionProvenance`. A driven command/observation's
`NormativeSourceRef` resolves to that same `ResolvedOriginEvidence`. Own-stream
position, receiver-time window, skew tolerance, nearest frame, and bare sequence
do not correlate sources. Missing or unequal epoch, sequence, declaration,
origin content, projection policy/content, or local receipt excludes the join
with an explicit reason. It cannot synthesize a row.

Any privacy-projected origin, command, observation, disposition, history frame,
or body-applied value carries `TrustedProjectionRecord` in its protected
projector envelope. After admission, `TrustedProjectionProvenance` binds that
record digest to this receiver's projected-frame admission receipt. Original
bytes are independently verifiable only when received. Otherwise, the observer
verifies the projection chain and labels the value projected. Redacted or
omitted channels remain missing and cannot be reconstructed from a digest or
treated as complete original bytes.

The exact current-read, historical-capture, extraction, and selector-resource
rules are in the [cross-store observer closure and enrollment
module](modules/adr-004-cross-store-observer-closure-and-enrollment.md). That
module is part of this ADR's content-bound review source set.

Observer grants never authorize publish, command creation, ESTOP, plant/session/
stream/security/authority lifecycle mutation, authority operations, disposition
creation, stream declaration, queryable declaration, or extension assessment. A
sealed `ObserverReadCapability` exposes only attach for its authenticated
principal within manifest-authorized session scope; renew and detach for a grant
issued to that principal; subscribe after that grant becomes live; and bounded
read-only query within the live grant. It does not expose or retain a generic
writable transport, `put`, publisher/queryable/stream declaration, raw session, or
externally aliased generic read/write bus.

Galadriel's optional assessment producer uses a different principal, credentials,
manifest, route, and process boundary under ADR-008/011. Observer credentials
cannot be upgraded or reused.

## Rejected alternatives

NCP rejects designs that infer a generation from traffic, treat TLS as wildcard
authority, return an unfiltered descriptor, reuse assessment credentials, or
continue after grant expiry. NCP also rejects designs that treat a self-sealed or
historical object as current, or infer admission from a terminal disposition.
Each rejected design removes a required authenticated state edge.

The [cross-store observer closure and enrollment
module](modules/adr-004-cross-store-observer-closure-and-enrollment.md) records
the detailed source-index, independent-anchor, enrollment, and closure
alternatives for this decision.

## Invalid or hostile example

A boundary validates a read against grant G1, increments its release counter,
and commits the payload to an outbox in a later transaction. Revocation wins
between the two transactions. The outbox write is invalid because the counter
and immutable item do not share one release-authorization linearization point.

Another dispatcher reads a valid committed item but substitutes a new
connection, replay domain, destination-security cut, transport-gate epoch, or
payload bytes. A copied release receipt does not authorize this dispatch. The
dispatcher must use the exact committed bytes and independently verify the
item's destination tuple, current transport-gate state, and acceptance deadline.
Grant terminalization after the release cut does not change the item and cannot
authorize a substituted destination.

An authenticated clock-mapping object that names an unapproved qualification
receipt, authority, rate, or applicability interval is also invalid. A
self-consistent digest or synthetic seal cannot select the trusted mapping cut.

## Actors and state transitions

The authenticated observer requests a bounded read scope. The source provider
issues and revokes server-side observer authority. Each delivery boundary makes
an independent current-release decision. A consumer can retain only admitted
history. An optional qualified independent anchor records its own ordered
exposure and acceptance evidence. Anchor membership alone proves neither.

The user-level lifecycle is `DETACHED -> ATTACHING -> ATTACHED -> RENEWING ->
ATTACHED -> REVOKED | EXPIRED -> DETACHED`. A later attach creates a fresh
lineage. It does not restore terminal authority. The module linked above defines
the complete source-index, anchor, enrollment, closure, and prepared-intent
transition products.

## Bounds and resource behavior

Every dynamic registry, proof set, retry set, terminal partition, and retained
history window has a finite manifest-bound capacity. A transition reserves its
success and terminal-closure capacity before it creates authority. Exhaustion
denies new work or retires the affected lineage. It cannot evict evidence,
silently reuse an identity, or widen a grant.

All lengths, counts, arithmetic, canonical input, and canonical output are
bounded before semantic allocation. Local model evidence does not qualify the
end-to-end capacity, latency, storage durability, or isolation of a deployment.

## Threat and hazard analysis

Observer data can contain sensitive plant, command, and topology information.
The design assumes an untrusted caller and fails closed on replay, stale state,
identity aliasing, scope substitution, privacy-policy drift, revocation races,
and incomplete evidence. A grant permits reads only. It cannot grant publish,
command, ESTOP, plant, session, stream, security, or authority-lifecycle power.

The independent-anchor profile is not a Byzantine containment boundary. A
compromised source can leak outside the qualified path, and anchor membership
does not prove delivery or acceptance. Privacy, retention, credential custody,
live revocation, resource isolation, and transport enforcement remain deployment
obligations. The module linked above contains the focused cross-store threats and
hazards.

## Formal properties

Exact authority, timing, confidentiality, evidence and recovery properties are
stated with their owning transitions above. The following conformance negatives
do not replace those contracts.

- Preallocation and reserved closure capacity reject overflow, cap-plus-one and
  partial work. Crash-complete bundles restore, restrict or retire; loss never
  means unused.
- Tests cover both race orders/equality and single-field mutations of identity,
  ancestry, scope, clocks, deadlines, duration, audience, boundary, endpoint,
  position and provenance. Faults preserve ambiguity; pending-as-LIVE, bare/
  sibling envelopes, overflow and one-tick extension reject.
- Delayed PREPARE versus no-install tombstone passes in both CAS orders; a
  LIVE-origin/renewal-fence no-install claim rejects and quarantines. Tests cover
  pending-never-LIVE zero items, direct/emergency/final no-install equivalents,
  direct-versus-emergency/final both-order reserve races, crash/replay,
  origin-specific eviction, exact cap/cap-plus-one, and bare/sibling/replayed
  boundary and observer terminal envelopes.
- Renewal delivers the G0 fence and G1 response in both orders; both converge to
  identical G1 LIVE state. G1 terminal, response-close and every security/clock/
  emergency/retirement cut close the predecessor-closed product without a
  wrong-kind resolver or pending-operation tombstone.
- An aggregation version that first proves both authorization closure and
  quiescence emits only the stronger quiescence envelope, one pre-manifest
  commitment and one manifest. A sibling authorization envelope, per-kind or
  second manifest, omitted receipt or changed exact retry rejects.
- Current reattachment-origin publication covers transport-first and role-first,
  duplicate/exact retry, changed-input replay and publication-versus-source-
  finalization in both orders. Bare inner evidence, a wrong role origin,
  post-finalization current publication and reserve cap-plus-one reject. It also
  covers publish -> positive/restrictive/untrusted/isolation record -> reattach,
  record -> publish, both publication/record CAS orders, full-coordinate
  security/incident/manifest refresh, stale-origin replay, maximum versions and
  cap-plus-one; only the exact current positive coordinate can authorize.
  Every non-`CURRENT` phase, dual/offline continuity and online/offline
  manifest-origin substitution rejects this positive producer.
- Every role origin rejects an omitted/swapped record resolution envelope,
  resolution manifest, membership proof or verification. Pending-never tests
  reject a candidate or terminal manifest that binds the later proof/resolution,
  using the earlier terminal manifest as the role-record final manifest, and
  any order other than terminal commit/envelopes/pre-manifest/manifest ->
  pending proof -> independent target-history commit/advance receipt ->
  resolution/envelope/pre-manifest/manifest -> verification.
- Role-record tests mutate all six origin branches at every record-to-verification
  edge, including cap-plus-one. They cover two distinct origins in both orders
  with the same set union, all 15 origin pairs in both orders, every final-set
  permutation by property test, positive plus restrictive/untrusted/isolation
  dominance, empty or unresolved sets, canonical witness priority, changed
  same-origin input as archive-only, all four evidence branches, and
  seal/checkpoint/record races in both orders. Checkpoint and current-origin
  reattach must bind the same complete-set assessment; single-record bypass
  rejects. Tests also cover crash at every DAG edge, current-origin versus
  published-origin envelope substitution, checkpoint receipt/output exact retry,
  and every class, audience,
  source-security phase, continuity and online/offline manifest-origin
  substitution. Joint local-marker tests reject either manifest before record
  resolution, a second final manifest, and an incomplete pre-manifest bundle.
  Bulk local completion and source reconciliation cover zero, one, cap and
  cap-plus-one members; omitted/duplicate/swapped members, foreign aggregate
  receipts, per-member or second manifests, wrong producer coordinates, early
  manifests, crash edges and changed retry bytes reject.
- Unused-slot restart, bulk source closure and boundary terminal/restart return
  producers each cover zero, one, cap and cap-plus-one members; omitted,
  duplicate or swapped members, a per-member/second manifest, artifact reuse
  across commitments, wrong outer coordinate, pre-final-member manifest,
  sibling disclosure and changed retry bytes reject at every crash edge.
- Historical current-origin/checkpoint ALLOW followed by a compromise incident
  affecting any member key rejects without a qualified pre-compromise anchor;
  the exact anchor passes, an unrelated incident passes only with current
  non-supersession, and stale incident-root replay rejects. The same cases apply
  to published-result fresh attach and both reattach origins. A challenge-time
  pass followed by a pre-acceptance incident must revalidate or lose; the
  inapplicable profile cannot carry historical-ALLOW evidence.
- LIVE activation rejects an omitted/swapped target, stale currentness
  descendant, missing realm-security intent/evaluation member and expiry
  equality. Same-key refresh and activation pass in both orders; only the
  commit-time winning read/evaluation set can appear in the response and final
  manifest.
- Allocation/genesis rejects a missing or message-selected publication-manifest
  credential, wrong use/fingerprint/epoch/algorithm/threshold/policy,
  failed/cross-role possession proof, local-install mismatch and a credential on
  `CONSUMER_SEMANTIC_CAPTURE`.
- Under restart uncertainty `[90, 110]`, new source authorization commits stop
  at 90, but old derived-authority closure before 110 rejects. Missing upper
  image forbids elapsed closure but permits exact terminal, no-install,
  never-LIVE or qualified isolation evidence; mixed S1-in-S0 verification
  rejects.
  A pre-restart TERMINAL grant preserves its reason/head and maps only the upper
  closure horizon; it is never terminalized again because a lower map is absent.
  Renewal-fence then restart maps G0's upper horizon before G0 closure and G1
  preparation; omission or G0/G1 horizon swap rejects.
- Source-index tests cover empty genesis, each availability profile, root
  enrollment at zero/one/cap/cap-plus-one, exact retry and changed retry.
  PREPARE without the exact source-index root-enrollment hierarchy rejects.
  Under the anchor profile, omitted, wrong-audience, sibling or mismatched
  anchor enrollment rejects source enrollment and PREPARE. Enrollment versus
  permanent freeze runs in both CAS orders: enrollment-first appears exactly
  once in the frozen closure audience, while freeze-first makes source
  enrollment and challenge issuance lose. A previously enrolled root can
  PREPARE after a disconnected freeze only until local namespace-closure import.
  Import-first rejects every later PREPARE for that namespace. PREPARE-first
  includes the operation exactly once in the import partition and resolves or
  preserves it under its proof-exact branch. Cap and cap-plus-one tests prove
  that reserved import capacity cannot be consumed by prepared operations and
  that one closed namespace cannot exhaust unrelated sources.
  Eligibility publication covers anchor commit followed by lost notification,
  notification retry, cutoff cancellation and source freeze in every relevant
  order. Confirmation-first produces one eligible entry. Cutoff-cancellation-
  first produces one retained `CANCELED_BEFORE_SOURCE_CONFIRMATION` entry.
  Freeze converts every still-pending entry to
  `FROZEN_BEFORE_SOURCE_CONFIRMATION` and preserves every prior canceled entry;
  neither state enters the closure audience or claims anchor non-enrollment.
  An unregistered, retired or stale-role root cannot publish eligibility. A
  relation with the same identifier but changed offset, relative-rate bound,
  applicability horizon, clock restart incarnation or canonical semantic digest
  rejects at enrollment, confirmation, cancellation, append, admission and
  handoff. A rate-undercovered offset interval, cutoff equality, checked
  arithmetic overflow/underflow, horizon expiry, stale security/role state at
  publication or confirmation, delayed notification and changed-entry retry
  reject. After a restrictive security or role change, or registered-root
  retirement, cancellation can still close only the exact pending entry. It must
  bind the exact current source-owned security, registration and role selectors;
  unknown, malformed or unowned current state rejects. The obsolete eligibility
  does not have to remain authorizing for this narrowing event.
  Later ADR-009 root retirement never erases an enrolled audience entry or its
  precharged closure output.
- Issuance-index tests race first issuance, absent-intent cancellation,
  available-slot cancellation, acceptance and permanent freeze in every
  pairwise order across two source generations. They reject a reused stable key,
  generation substitution, issued-versus-canceled member substitution, omitted
  retained generation/slot/tombstone, open-index absence as permanent evidence
  and any frozen assessment whose two entry/slot bijections are incomplete.
  `OBSERVER_GRANT_SPARSE_MERKLE_SHA256_V1` vectors cover the exact 8,272-octet
  body, both tree contexts, source membership/nonmembership, anchor
  membership/nonmembership, empty/one/cap trees, both endpoint bits, every
  reserved/context/kind mutation, reversed siblings, wrong canonical domain and
  raw-versus-ASCII encoding. Source/anchor proof or canonical-entry
  cross-context substitution and every unknown/default suite reject.
- Independent-anchor tests separate the observer, source and anchor audiences
  at bootstrap, enrollment, source issuance, anchor append and closure. No
  audience can consume another's projection. Reservation-first tests cover
  exact capacity, cap-plus-one, selector/key collision, lost return, retry,
  changed proposal, post-allocation reservation and abandoned reservation.
  Allocation without the verified reservation hierarchy rejects.
  Allocation/cancellation and anchor-genesis/source-registration run in both
  cross-store orders; a canceled source allocation never becomes LIVE.
  Protected cancellation import races anchor genesis in both orders and reaches
  the same terminal anchor selector. Wrong reservation, audience, purpose,
  class, LIVE namespace, bare or cross-allocation evidence rejects. Missing
  cancellation delivery leaves a bounded nonauthorizing orphan and never
  permits timeout inference. Cooperative source retirement covers empty and
  nonempty observer audiences, the exact four-case producer inventory, lost and
  retried anchor delivery, append-versus-closure in both orders, mismatched
  anchor/profile/source retirement, cause-specific closure output and
  reservation terminal capacity. It never substitutes for permanent isolation.
  The source derives the cooperative retirement audience from its immutable
  namespace-allocation, anchor-selector and reservation binding. Rebinding or a
  sibling anchor for the same namespace rejects. Cooperative or isolation
  terminalization changes the anchor head and reservation registry in one
  anchor-domain transaction. It retains the complete precharged owner/global
  participant and byte counters. Exact retry is idempotent, and complete-domain
  retirement remains reachable after every reservation is terminal; no
  per-entry refund or reuse occurs.
  Cooperative-first and isolation-first evidence refinement both converge to
  `COOPERATIVE_AND_ISOLATION` without changing the first cause, frozen roots,
  published bytes or reservation accounting. Source issue, anchor append, two-capsule full-frame
  admission, queue handoff, observer attempt and source acceptance are faulted
  at every durability edge. Opaque observer-audience relay tests mutate the
  envelope identity, envelope body/authentication digests, family/completion
  coordinate, membership proof and producer coordinate one field at a time.
  They also reject truncated, extended and cross-producer capsules. Source
  semantic acceptance of the observer projection and observer acceptance of the
  source projection are impossible. Pending retry/query returns no challenge
  bytes. Acceptance requires the admitted gate, exact record, admission key,
  frame/connection/replay equality and source-audience capsule.
  Crash immediately after admission remains may-have-been-exposed; no
  admitted-but-proved-unexposed state exists.
  Append/closure, admission/cancel/finalization and handoff/cutoff races run in
  both orders; equality, clock restart, mapping uncertainty, partial-frame
  admission and source acceptance without any one exact gate artifact reject.
  Handoff tests cover zero-byte return, partial acceptance, bounded transport
  stall, watchdog/socket fencing and outcome unknown. A canceled future,
  expiring lease or unproved descriptor fence cannot release the dispatch token
  or enable the anchor profile.
- Permanent-resolution tests distinguish frozen source nonmembership, exact
  canceled-entry membership, frozen anchor nonmembership and frozen anchor
  membership. An issued source entry never enters a no-challenge branch. Anchor
  absence never claims source nonissuance. Anchor membership maps only to
  `MAY_HAVE_BEEN_EXPOSED_BUT_ACCEPTANCE_PERMANENTLY_CLOSED` and its distinct
  verified outcome/cause; it never claims nonexposure, delivery, nonacceptance
  or successful acceptance. The isolation inventory covers every closed capability-surface
  kind at zero/one/cap/cap-plus-one, missing/duplicate/unknown surfaces,
  replica/restore/restart bypasses and, when applicable, the independently
  verified body/plant final-authority cut. Resolution is legal only before a
  local attempt with typed absence of challenge, slot, attempt and grant; every
  delayed capsule then loses against the same installed stable-key tombstone.
- These are conformance requirements, not live qualification. Independent peers,
  live transport/security, fault/soak/fuzz, performance, provenance, clean-room
  reproduction and role qualifications remain **NOT RUN**.

## Migration

Galadriel and Prisoma require pinned native-1.0 adapters; Prisoma versions every
axis. Raw subscription does not qualify.

## Operational recovery

Restart reattaches against exact descriptor identity. Gaps are not interpolated;
unrestorable authority retires.

## Compatibility and rollback

Old candidates reject unknown messages. Rollback selects a complete compatible
pair or disables the adapter; wildcard trust never returns.

## Open questions

<a id="ncp-b01-selector-allocation-adr-004-v1"></a>

No semantic question remains in this decision. Unknown or default values deny.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Protocol semantics keep attach, grant, and outcome distinct.
2. Security fails identity and freshness closed.
3. Safety prohibits observer actuation.
4. Distributed lifecycle is explicit.
5. Resource use is bounded.
6. Interoperability requires native migration.
7. Science separates delivery from truth and effect.
8. Operations use receipts, not fictitious cross-store atomicity.
9. Verification tests adversarial recovery.
10. Lifecycle governance preserves owner authority.

## Ratification record

The non-normative registry derives review status; review changes do not mutate
this invariant text.
