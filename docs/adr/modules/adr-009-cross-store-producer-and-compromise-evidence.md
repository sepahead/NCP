# ADR-009 module — Cross-store producer and compromise evidence

> Status: PROPOSED and non-normative. Parent: ADR-009.

This maintained module is part of the bounded ADR-009 review source set. The decision registry binds its exact bytes with the parent decision. Read the parent first. This split changes review shape, not protocol meaning or release status.

The security-artifact anchor and the ADR-004 challenge-exposure anchor are
distinct installed subjects. Shared labels or a common host do not merge them.
A deployment can colocate the functions only as separately qualified
subsubjects. Each parsed, content-addressed subject binds its exact deployment
identity, build, deployment manifest, installation receipt, control tuple,
operator, and emitter. The two control tuples have
different authority, owner, operator, authenticated principal, key fingerprint,
credential, security epoch, store, selector incarnation, and failure domain
values, with complete cross-field alias rejection. Separately retained policy
sets bind each subject. One parsed correlated-failure analysis binds both subject
digests, shared failure modes, and residual risks.

The separate security-anchor qualification receipt names the exact two subject
digests, controls, emitters, correlated-failure analysis, and validity window.
It carries signed `PASS`, an exact issuer control tuple, and retained trust,
credential-issuance, credential-signature, payload-signature, and exact
zero-skip `PASS` verification artifacts. Strict trust, credential, verification,
and receipt ancestry applies. Its issuer is completely disjoint from the source
and both anchor control domains. The X05 security-and-operations adjudicator
also reviews this exact separation subject. A source owner, anchor owner,
operator, emitter, credential holder, or aliased control domain cannot satisfy
either independent role. Missing, stale, equal-boundary, overflowing, or
over-limit qualification keeps positive pre-compromise-anchor use unavailable.

Local schema and semantic checks can prove only the retained structure and
bindings. They cannot prove organizational independence, a live revocation
state, or that the named deployment was installed and exercised. X05 remains an
external gate.

## Cross-store producer, audience, retention, and compromise rules

Every receipt that crosses between the source realm store and an external owner
store travels only as one
`ProtectedCrossStoreSecurityReceiptEnvelope`. The envelope binds the exact inner
artifact type/schema and canonical bytes/digest, emitter principal and
store/selector/head/commit ancestry, source identity, operation,
`CrossStoreSecurityReceiptAudienceBinding`, signing-key fingerprint/epoch,
fully specified algorithm and use,
trust-anchor/manifest/security-state ancestry,
`CrossStoreSecurityArtifactVerificationClass`, class-specific validity and
replay domain. The class is exactly
`EPHEMERAL_AUTHORITY_WINDOW | DURABLE_HISTORICAL_COMMIT |
PERMANENT_CLOSURE_TOMBSTONE`. It contains no remote URL or trust-on-message key
selector.

The closed audience binding is
`SINGLE_REGISTERED_EXTERNAL_ROOT |
REGISTERED_SOURCE_AUTHORITY |
PENDING_REGISTRATION_BOOTSTRAP |
PENDING_SOURCE_NAMESPACE_ANCHOR_BOOTSTRAP |
SOURCE_SECURITY_DOMAIN_HISTORY |
INDEPENDENT_ANCHOR_AUTHORITY |
SOURCE_NAMESPACE_INDEPENDENT_ANCHOR_RETURN`. The single-root branch requires
one exact audience realm/root/key, owner, store and registration ancestry. The
history branch requires the exact source realm/domain/lineage and replay domain,
structurally forbids an audience root and every authority-window field, and is
legal only for `DURABLE_HISTORICAL_COMMIT`. It can authenticate source ancestry
before any external root exists, but grants nothing. A later verifier can use it
only after its own exact registration ancestry binds that source domain. Empty or
future audience sets are therefore never encoded or guessed.
`INDEPENDENT_ANCHOR_AUTHORITY` binds one exact separately enrolled anchor
authority, store, selector/head incarnation, availability/isolation profile,
credential ancestry, disjoint failure-domain enrollment and one closed
`IndependentAnchorAuthorityAudiencePurpose`:
`SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT |
SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT_CANCELLATION |
SOURCE_NAMESPACE_ALLOCATION_BOOTSTRAP |
SOURCE_NAMESPACE_ALLOCATION_CANCELLATION |
SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT |
OBSERVER_ROOT_ENROLLMENT_ELIGIBILITY |
OBSERVER_GRANT_CHALLENGE_COMMITMENT |
OBSERVER_GRANT_ACCEPTANCE_CAPABILITY_SURFACE_ISOLATION`.
Reservation intent and allocation select `DURABLE_HISTORICAL_COMMIT`.
Reservation-intent cancellation, allocation cancellation, cooperative
retirement and surface isolation select `PERMANENT_CLOSURE_TOMBSTONE`;
challenge commitment selects
`EPHEMERAL_AUTHORITY_WINDOW` and structurally forbids challenge secret bytes.
Observer-root enrollment eligibility also selects
`EPHEMERAL_AUTHORITY_WINDOW`; it accepts only the exact
`ObserverGrantChallengeExposureAnchorEnrollmentEligibilityProjection` and
binds its exclusive cutoff, registered-root hierarchy, current observer-role
eligibility and preallocated source-index/anchor coordinates.
Each purpose accepts only its exact inner artifact type and forbids every other
purpose's fields. The reservation-intent branch requires
`PENDING_ANCHOR_CAPACITY_RESERVATION`; its cancellation branch requires the
matching permanent source tombstone and cannot claim that an anchor reservation
exists. The cooperative-retirement branch accepts only
`SourceLogicalSessionCooperativeAnchorRetirementProjection`; it requires the
matching retired namespace/lineage, frozen source-index closure, complete
accepted-grant closure and no-successor result, and structurally forbids
permanent-isolation or Byzantine-containment claims. The audience is
consumable only by that anchor. A registered external root, source authority or
history verifier cannot consume it, and an anchor cannot consume their
audience-bound projection. Unknown, post-operation, source-controlled or
same-failure-domain enrollment rejects.
`PENDING_SOURCE_NAMESPACE_ANCHOR_BOOTSTRAP` is the disjoint return audience for
one source realm/domain/principal before its proposed namespace becomes LIVE.
It selects `DURABLE_HISTORICAL_COMMIT`, grants no authority, and binds one
closed `IndependentAnchorBootstrapReturnPurpose`:
`ANCHOR_NAMESPACE_CAPACITY_RESERVATION |
ANCHOR_GENESIS_PROJECTION`.
The reservation branch binds the authenticated requesting source owner, exact
prospective namespace, lineage/source-index/anchor selector incarnations,
availability profile, anchor reservation-registry key/head/commit, fixed
capacities/policies, operation and replay domain. It carries the protected
anchor reservation receipt and structurally forbids a source allocation
receipt, per-namespace anchor head or authority-window field. Only
`ALLOCATE_SOURCE_LOGICAL_SESSION_NAMESPACE` can consume it.
The genesis branch additionally binds that exact reservation ancestry, the
already committed matching source allocation receipt, installed empty
per-namespace anchor head and genesis receipt. It is legal only for
`REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE`. It structurally forbids every
non-genesis payload and authority-window field. Every branch forbids the other
purpose's fields. A guessed namespace, message-selected recipient, changed
reservation, cross-purpose/post-operation use or any attempt to grant
acceptance authority rejects.

`SOURCE_NAMESPACE_INDEPENDENT_ANCHOR_RETURN` is the disjoint reverse audience
for one independent anchor that the installed source namespace's immutable
availability profile already binds. It binds the recipient source realm,
domain, lineage, store, selector and principal; the emitting anchor authority, key, store,
selector/head incarnation and credential ancestry; the bidirectional profile
enrollment commitment; and one closed
`IndependentAnchorSourceReturnPurpose`:
`OBSERVER_ROOT_ENROLLMENT_NOTIFICATION |
PAIRED_FRAME_ACCEPTANCE_ADMISSION`.
Root enrollment binds one exact source-index eligible-root enrollment identity
and the byte-equal anchor eligible-root entry. It selects
`DURABLE_HISTORICAL_COMMIT`, forbids every authority-window field and grants no
acceptance authority. Paired-frame admission binds one exact source-index
entry/commit, stable key, anchor member, preallocated paired-frame admission
key, intended observer root and mapped source-acceptance cutoff. It alone
selects `EPHEMERAL_AUTHORITY_WINDOW`, whose end is no later than that cutoff.
It is only an input to the source's exact paired-frame admission and request
acceptance predicates; it cannot create, widen or revive source authority.
Every purpose forbids the other purposes' fields. A generic source return,
registered external root, source-history verifier or different anchor cannot
consume this audience branch.
`SOURCE_SECURITY_DOMAIN_HISTORY` proves gap-free global ancestry and can support
a restrictive fence. It never supplies a per-root projection and cannot by
itself confirm, reauthorize, retire or reopen one registered root. Every
root-specific receipt, capture or disposition that crosses stores requires a
`SINGLE_REGISTERED_EXTERNAL_ROOT` envelope in its deterministic family, the
shared producer completion, both scoped membership proofs and passing
verification. An empty root-specific subset structurally omits that family.

`REGISTERED_SOURCE_AUTHORITY` carries return evidence. It binds the recipient
source realm/domain/lineage, store/selector and principal plus the emitting
external root/key/owner/store and one closed
`RegisteredSourceAuthorityReturnPhase`:
`PENDING_GENESIS_BOOTSTRAP_RETURN |
ACTIVE_OR_RETIREMENT_RETURN |
PERMANENT_HISTORICAL_REFINEMENT`.
The pending branch permits only local deny-only genesis confirmation,
pre-genesis cancellation or deny-only final-retirement evidence and binds the
matching pending-registration receipt, key, root and operation. It is
non-authorizing and cannot carry ordinary role output. The active/retirement
branch carries ordinary closure and retained-evidence returns under that exact
entry ancestry. The permanent branch is read-only historical refinement and
cannot mutate authority or support continuation.
It is legal only for `DURABLE_HISTORICAL_COMMIT |
PERMANENT_CLOSURE_TOMBSTONE`, has no authority window and can only narrow or
close the originating registered lineage. Wrong source, unregistered emitter,
cross-phase or cross-root replay, pending ordinary output or ephemeral authority
rejects.

`PENDING_REGISTRATION_BOOTSTRAP` is legal only for a protected ADR-004
`ExternalCompositeStateEnrollmentAllocationReceipt` used by
`REGISTER_EXTERNAL_SECURITY_ENFORCEMENT_ROOT`. It selects
`DURABLE_HISTORICAL_COMMIT`, binds the installed parent
selector/head/commit, predecessor trust/security-manifest ancestry, local
root/owner/store/incarnation, intended source realm/domain/lineage,
operation/replay domain and the exact
prospective `RegisteredExternalSecurityEnforcementRootKey` deterministically
derived from the already committed allocation-receipt digest. It structurally
forbids existing source-registration ancestry, authority-window fields and any
other payload. It excludes the later export persistence manifest, which instead
binds the envelope last. It can create only a deny-only pending source entry; it cannot
confirm, activate, issue currentness or grant authority. Thus this one
post-allocation shape is not an empty or guessed future audience and introduces
no key/envelope digest cycle.

For this rule, a producer is one maximal installed transaction or one
independently committed post-CAS operation. Exact
`CrossStoreProducerCoordinate` identifies a transaction producer by the
transaction-domain identity, common transaction operation identity, producer
event/schema identity, canonical complete pre-CAS fact/candidate-set root,
canonical complete installed-selector-coordinate-set root and common
transaction-receipt digest. It identifies an independent post-CAS producer by
its own operation/event/schema identity and exact
`CrossStoreProducerCommittedResultCoreCoordinate` and digest. That immutable
core is installed before protected outputs and explicitly excludes the public
pre-manifest commitment, all tree openings, manifests/authentications, retention
record, delivery capsules and verifier evidence. The transaction receipt in a
transaction producer coordinate has the same later-output exclusions. Thus a
producer result cannot include the hierarchy whose pre-manifest commitment
binds its coordinate. A joint transaction with multiple facts or installed
selectors still has one producer coordinate. No caller, loop, member handler, output
family or nested helper can select a subset, synthesize another coordinate or
redefine a member as a separate producer. The complete pre-CAS fact/candidate
set binds the deterministic expected-output inventory, per-member identities
and counts and worst-case reserve.

Closed `CrossStoreProducerManifestCredentialSelection` is selected by that
complete fact set before commit:
`GENESIS_CANDIDATE_ENROLLED |
PREDECESSOR_INSTALLED |
DUAL_PREDECESSOR_SUCCESSOR |
OFFLINE_PREDECESSOR_ENROLLED |
PENDING_ALLOCATION_COMMITTED |
INSTALLED_IMPORTED_LOCAL |
PARENT_OWNER |
INDEPENDENT_ANCHOR`. It binds the exact purpose/origin, credential-set digest,
every fingerprint and epoch, algorithm, threshold, policy ancestry and
applicable issuance cutoff. The dual branch requires predecessor and successor
thresholds to authenticate identical canonical bodies; one half is invalid.
The complete producer hierarchy uses one exact selection. Unknown, mixed,
message-selected, cutoff-violating or cross-family selection rejects. Once the
transaction manager fixes commit coordinates, it creates and persists every
required family/completion authentication in the same winning durable bundle
before final selector publication. An independently committed post-CAS
producer does the same in its own committed result. A later signing promise
cannot complete either producer.

Canonical `CrossStoreManifestAuthenticationSet` has closed shape
`SINGLE_SELECTED_CREDENTIAL_AUTHENTICATION |
DUAL_PREDECESSOR_SUCCESSOR_AUTHENTICATION`. The single branch contains one
authentication labeled with the exact selected credential-set digest. The dual
branch contains exactly two authentications in fixed predecessor-then-successor
order, each labeled with its credential-set digest and both over byte-identical
manifest bodies. Each authentication contains the exact threshold member set or
aggregate and its canonical bytes; its set digest covers all labels and bytes.
Missing, duplicate, reordered, cross-body, cross-purpose or one-half-dual
authentication rejects. Every reference below to a family or completion
“authentication” means this full set and its digest.

Every producer that emits protected output first creates all of its commits,
receipts, shared non-manifest sidecars and protected envelopes. Before any
manifest, it constructs one
`CrossStoreProducerPreManifestBundleCommitment`. The producer retains exact
`CrossStoreProducerPreManifestPrivateOpening`. It contains the exact producer
fact/operation/installed coordinates, complete shared receipt/sidecar set,
signer ancestry, exact credential selection, closed deterministic output-family
inventory, exact family-member envelope sets, all exact counts and preallocated
independent tree seeds. It excludes every derived tree root, count salt, slot
map, proof path, family/completion body or authentication. The immutable public
commitment body contains only a preallocated opaque producer identity,
credential-selection digest, privacy-suite identity, pre-enrolled
capacity-policy incarnation and domain-separated salted commitments to that
pre-manifest private opening and exact producer coordinate. Each commitment
salt is an independent 32-octet CSPRNG value retained in that opening. It never
exposes the exact coordinate, fact/candidate or installed-selector roots,
transaction receipt, opening, salt or counts. Recipient-visible coordinates
appear only in that recipient's already-authorized envelope projection.

`CrossStoreProducerOutputFamilyClass` is derived only from the producer
event/schema, protected inner schema and purpose, verification class,
audience-binding branch, credential-selection class and privacy suite.
`CrossStoreProducerOutputFamilyKey` is that class plus the exact
credential-selection digest. An audience instance, caller label, loop iteration
or delivery policy version cannot split a family. All families of one producer
use the same exact credential selection. A mixed-origin or mixed-credential candidate rejects
before semantic mutation; it cannot let one family's trust origin authenticate
or upgrade another family.

`CrossStoreProducerPrivacyCapacityPolicy` maps each closed producer event/schema
and registration incarnation to one family-set capacity class and one member
capacity class for every possible structural output-family class. A rotating
credential-selection digest binds the actual key but does not create an
unbounded policy-map key. It is not an independently
writable selector. Closed `CrossStoreProducerPolicyOwner` is
`SOURCE_SECURITY_HEAD |
REGISTERED_EXTERNAL_ROOT_ENTRY |
LOCAL_IMPORTED_ROOT_HEAD |
PARENT_ENROLLMENT_HEAD |
INDEPENDENT_ANCHOR_HEAD`; the applicable existing owner selector/head stores the
policy digest and full historical incarnation. Only that owner's already
defined transition can replace it. The source manifest, registration or
enrollment fixes the policy before the transaction's actual member and family
counts are known. A producer cannot select the smallest fitting class. Every
nonempty count from one through the registered maximum uses the same fixed
shape; changing a class requires a new owner incarnation. Capacity classes are
powers of two and bind maximum proof and opening byte lengths. The absence of a
hierarchy for a zero-family producer is intentionally observable. A family
count or member count above its registered class rejects before semantic
mutation.

Every family is nonempty. The pre-manifest private opening binds one opaque
operation-scoped no-reuse manifest identity per family, one distinct opaque
`CrossStoreProducerBundleCompletionManifest` identity, exact internal
family/member counts and worst-case reserve. Every opaque producer, family-
manifest and completion-manifest identity is exactly 32 octets. Before the
producer knows its exact coordinate or actual output count, its already
never-reused operation record generates and persists one independent
32-octet CSPRNG identity seed. Domain-separated HMAC-SHA-256 over that secret
seed uses the exact privacy-suite `IDENTITY / PRODUCER_IDENTITY` equation below
to derive producer slot zero, completion slot one and the fixed-capacity
family-identity pool at slots two onward. Thus identities are not counters,
timestamps, coordinates or
unsalted content digests and an external party cannot dictionary-test the
operation identity. Actual family keys sort by ascending unsigned
lexicographic order of their raw 32-octet family-key digests, with canonical key
bytes as the tie-breaker; distinct keys with one digest reject. Sorted rank
`i` consumes pool slot `i+2`. Unused positions are never published, the seed is
never reused by another operation and exact retry retains it. Operation
no-reuse plus distinct domain/slot inputs provides the identity namespace
without a new unbounded global burned-ID registry. Uniqueness is computational
under independent 256-bit seeds and HMAC-SHA-256, not an absolute
cross-operation collision registry. Insufficient pool capacity or a detected
same-operation collision rejects before mutation. The
public commitment and its pre-manifest private opening exclude the commitment's
own digest, every family/completion manifest body/digest/authentication value
and later verification evidence. Every protected envelope belongs to exactly
one family; family artifact sets are disjoint; every shared receipt/sidecar
occurs exactly once in the separate shared set. Omission, duplication, an empty
or caller-split family, an unassigned artifact or cross-producer substitution
rejects. A zero-family producer emits no protected publication hierarchy.

After that commitment, each named type-specific publication or persistence
manifest is one immutable family manifest. Its common canonical body binds the
public pre-manifest body digest, opaque producer identity, exact family key and
manifest identity, credential-selection digest,
`CROSS_STORE_PADDED_MERKLE_SHA256_V1` and fixed-capacity-policy identifiers, a
domain-separated padded family-member root and a hiding count commitment. It
does not contain a recipient, recipient-specific proof, exact count, salt,
private opening or sibling-family information. The producer retains the exact
`CrossStoreFamilyMemberTreeOpening`. Exactly one family manifest exists per family. It
excludes sibling family manifests and the later completion manifest.

Only after every family manifest and its authentication exist does the producer
create `CrossStoreProducerBundleCompletionManifest`. Internally, the producer
retains the exact shared set and family-key-to-family-manifest-body/
authentication bijection. The immutable terminal body binds the public
pre-manifest body digest, opaque producer identity, preallocated completion identity,
credential-selection class and digest,
`CROSS_STORE_PADDED_MERKLE_SHA256_V1`, fixed-capacity-policy and exact
complete-set-predicate schema identities, a domain-separated padded family-set
root, hiding count commitment and
`EXACT_PRODUCER_OUTPUT_SET_ATTESTED`. That signed attestation states that the
generated family keys and protected-envelope partition are the exact canonical
bijection to the pre-manifest expected inventory; the shared set is unchanged;
and every family body is deterministically derived from its precommitted
identity, credential selection, capacity policy, tree seed and member set. The
producer creates and persists exactly one valid canonical authentication set
for that body under the selected credential. Signature algorithms can be
randomized; the chosen authentication bytes were not precommitted, are
committed by the completion family-set root and are returned byte-identically
on retry. The completion family-set opening contains exactly those derived
bodies and retained authentication sets. This is a producer trust assertion,
not a zero-knowledge proof that
an ordinary recipient can independently evaluate. The producer conformance
gate and an authorized auditor verify it by opening the pre-manifest and both
tree layers and recomputing the derivation and bijections. The completion manifest cannot change or
upgrade a family's verification class, audience, authentication origin or key
origin. It excludes its own authentication value and all verifier evidence, is
directly authenticated under the same exact precommitted credential selection
as every family manifest and is never recursively placed in another completion
manifest. A completion manifest is mandatory even for one family. A family
manifest alone is incomplete and non-authorizing. The producer exposes no
output before the completion manifest and its authentication are durable.

`CROSS_STORE_PADDED_MERKLE_SHA256_V1` is the only 1.0 privacy suite. It uses
SHA-256, HMAC-SHA-256 and 32-octet independent CSPRNG seeds. Each tuple field is
encoded as
`LP(value) = U128_BE(length_in_octets(value)) || value`; depth, level, slot and
count use `U64_BE`. Define
`E(tag, scope, fields...)` as
`LP(ASCII(tag)) || LP(ASCII("CROSS_STORE_PADDED_MERKLE_SHA256_V1")) ||
LP(ASCII(scope)) || LP(field_1) ... LP(field_n)`.
Define `D(...) = SHA256(E(...))` and
`M(seed, ...) = HMAC-SHA-256(seed, E(...))`. No raw, omitted or reordered
field is allowed. Exact tags are
`NCP1/CSPM/COORDINATE`,
`NCP1/CSPM/OPENING`,
`NCP1/CSPM/IDENTITY`,
`NCP1/CSPM/SCOPE-CONTEXT`,
`NCP1/CSPM/ENVELOPE-BODY`,
`NCP1/CSPM/ENVELOPE-AUTHENTICATION`,
`NCP1/CSPM/FAMILY-KEY`,
`NCP1/CSPM/FAMILY-BODY`,
`NCP1/CSPM/PRE-MANIFEST-BODY`,
`NCP1/CSPM/CAPACITY-POLICY`,
`NCP1/CSPM/CREDENTIAL-SET`,
`NCP1/CSPM/CREDENTIAL-SELECTION`,
`NCP1/CSPM/MANIFEST-AUTHENTICATION-SET`,
`NCP1/CSPM/FAMILY-MEMBER-ITEM`,
`NCP1/CSPM/FAMILY-SET-ITEM`,
`NCP1/CSPM/ORDER`,
`NCP1/CSPM/SLOT-PERMUTE`,
`NCP1/CSPM/NONCE`,
`NCP1/CSPM/DUMMY`,
`NCP1/CSPM/REAL`,
`NCP1/CSPM/NODE`,
`NCP1/CSPM/COUNT-SALT` and
`NCP1/CSPM/COUNT`. Exact commitment scopes are
`PRODUCER_COORDINATE | PRODUCER_OPENING | PRODUCER_IDENTITY`; exact tree scopes are
`FAMILY_MEMBER_SET | PRODUCER_OUTPUT_FAMILY_SET`; exact component scopes are
`ENVELOPE_COMPONENT | FAMILY_COMPONENT | PRE_MANIFEST_COMPONENT |
POLICY_COMPONENT | CREDENTIAL_COMPONENT | AUTHENTICATION_SET`.

Every `canonical_*_bytes` operand below uses exact
`CanonicalCrossStoreHierarchyCodecV1`: the domain bytes, terminal NUL and
encoded strict projected JSON value defined by
`contract/canonical-digest.v1.json`, before SHA-256. Unknown fields or a value
outside that codec's depth, byte or number limits rejects. The closed
projections and lowercase domains are:

| Operand | Strict projection and canonical-digest domain |
|---|---|
| operation identity | complete operation identity / `ncp.cross-store.operation-identity.v1` |
| producer coordinate | exact self-excluding coordinate / `ncp.cross-store.producer-coordinate.v1` |
| pre-manifest private opening | complete pre-tree private opening / `ncp.cross-store.pre-manifest-private-opening.v1` |
| public pre-manifest body | complete public body / `ncp.cross-store.pre-manifest-public-body.v1` |
| capacity-policy incarnation | complete policy identity, version and fixed class map / `ncp.cross-store.capacity-policy-incarnation.v1` |
| credential set | complete purpose/origin, threshold, ordered member fingerprints/epochs/algorithms and policy ancestry / `ncp.cross-store.manifest-credential-set.v1` |
| credential selection | closed selection class, ordered credential-set digests, continuity/cutoff and policy ancestry / `ncp.cross-store.manifest-credential-selection.v1` |
| protected-envelope body | self-excluding envelope body / `ncp.cross-store.protected-envelope-body.v1` |
| protected-envelope authentication | complete persisted authentication set / `ncp.cross-store.protected-envelope-authentication.v1` |
| family key | complete output-family key / `ncp.cross-store.output-family-key.v1` |
| family-manifest body | self-excluding family body / `ncp.cross-store.family-manifest-body.v1` |
| manifest authentication set | complete canonical set / `ncp.cross-store.manifest-authentication-set.v1` |

The authentication projections include the exact branch enum, algorithm
identifier and parameters, threshold or aggregate shape, ordered signer/member
identities and labels, credential-set digest and every exact persisted
signature/authentication octet. The manifest set is one selected entry or exact
predecessor-then-successor entries. Omitting or reordering a threshold member,
aggregate label or signature changes the bytes and digest.

Opaque identity slot `s` is exactly
`M(identity_seed, IDENTITY, PRODUCER_IDENTITY,
canonical_operation_identity, U64_BE(s))`.
Every `D` or `M` result used by another suite equation is exactly 32 raw octets.
External JSON renders such a value as 64 lowercase hexadecimal characters, but
a parser must validate and decode it before `LP`; hashing the 64 ASCII
characters rejects.

The protected-envelope body digest is
`D(ENVELOPE-BODY, ENVELOPE_COMPONENT,
canonical_self_excluding_envelope_body_bytes)`. Its authentication digest is
`D(ENVELOPE-AUTHENTICATION, ENVELOPE_COMPONENT,
canonical_persisted_envelope_authentication_bytes)`. The family-key digest is
`D(FAMILY-KEY, FAMILY_COMPONENT, canonical_family_key_bytes)`. The family-body
digest is
`D(FAMILY-BODY, FAMILY_COMPONENT,
canonical_self_excluding_family_manifest_body_bytes)`.
The manifest-authentication-set digest is
`D(MANIFEST-AUTHENTICATION-SET, AUTHENTICATION_SET,
canonical_manifest_authentication_set_bytes)`.
The public pre-manifest body digest is
`D(PRE-MANIFEST-BODY, PRE_MANIFEST_COMPONENT,
canonical_public_pre_manifest_body_bytes)`.
The capacity-policy-incarnation digest is
`D(CAPACITY-POLICY, POLICY_COMPONENT,
canonical_capacity_policy_incarnation_bytes)`.
Each credential-set digest is
`D(CREDENTIAL-SET, CREDENTIAL_COMPONENT, canonical_credential_set_bytes)`.
The credential-selection digest is
`D(CREDENTIAL-SELECTION, CREDENTIAL_COMPONENT,
canonical_credential_selection_bytes)`.

The public coordinate commitment is
`D(COORDINATE, PRODUCER_COORDINATE, coordinate_salt,
canonical_coordinate_bytes)`. The public opening commitment is
`D(OPENING, PRODUCER_OPENING, opening_salt,
canonical_private_opening_bytes)`. The salts are independent.
A family-member scope-context digest is
`D(SCOPE-CONTEXT, FAMILY_MEMBER_SET, public_pre_manifest_body_digest,
opaque_producer_identity, family_key_digest, family_manifest_identity,
capacity_policy_incarnation_digest)`. A family-set scope-context digest is
`D(SCOPE-CONTEXT, PRODUCER_OUTPUT_FAMILY_SET, public_pre_manifest_body_digest,
opaque_producer_identity, completion_manifest_identity,
capacity_policy_incarnation_digest)`.

A family-member item digest is
`D(FAMILY-MEMBER-ITEM, FAMILY_MEMBER_SET, scope_context_digest,
protected_envelope_canonical_body_digest,
canonical_envelope_authentication_digest)`. The second digest covers the exact
persisted envelope authentication bytes, so a different valid signature is a
different member. A family-set item digest is
`D(FAMILY-SET-ITEM, PRODUCER_OUTPUT_FAMILY_SET, scope_context_digest,
family_key_digest, family_manifest_canonical_body_digest,
family_manifest_authentication_set_digest)`.

For one scope, sort distinct items by
`M(seed, ORDER, scope, scope_context_digest, item_digest)`, with the item digest
as the tie-breaker. Both comparisons use ascending unsigned lexicographic order
over raw 32-octet values. Independently sort every slot in `0..capacity-1` by
`M(seed, SLOT-PERMUTE, scope, scope_context_digest, U64_BE(slot))`, with the
numeric slot in ascending order as the tie-breaker. Assign sorted item rank `i` to slot-permutation
rank `i`; all remaining permuted slots are dummy. This is a pseudorandom
permutation, not occupancy-dependent probing, so the joint slot distribution
of any fixed authorized item subset does not depend on hidden occupancy under
the HMAC assumption. Each real item's nonce is
`M(seed, NONCE, scope, scope_context_digest, item_digest)`. An unused-slot leaf
is `M(seed, DUMMY, scope, scope_context_digest, U64_BE(slot))`. A real leaf is
`D(REAL, scope, scope_context_digest, U64_BE(slot), item_digest, nonce)`.
Leaves occupy slots `0..capacity-1` from left to right at level zero. A parent
at level `k`, starting with `k=1` above the leaves, is
`D(NODE, scope, scope_context_digest, U64_BE(k), left, right)`. At depth zero,
the only leaf is the root. The count salt is
`M(seed, COUNT-SALT, scope, scope_context_digest)`; the count commitment is
`D(COUNT, scope, scope_context_digest, count_salt,
U64_BE(exact_count))`.

After the public pre-manifest body digest exists, each family deterministically derives
one `CrossStoreFamilyMemberTreeOpening` from its precommitted member set and
seed. It contains that scope seed, derived count salt, exact canonical item set,
slot map and proof paths. After every family manifest authentication exists, the
producer similarly derives one
`CrossStoreProducerFamilySetTreeOpening` from the precommitted family inventory,
family bodies/authentication sets and independent family-set seed. It contains
the analogous family-set material. Neither post-commitment tree opening is a
field of the pre-manifest private opening or changes its public digest. The
family roots authenticate the first class; the completion root authenticates
the second. Authorized audit compares both derived openings to the exact
pre-manifest inventory. The tree-instance key is the exact pair
`(CrossStorePublicationHierarchyPrivacyScope, scope_context_digest)`. The
pre-manifest opening binds one independent seed for every possible nonempty
family-member tree instance and one for the producer family-set instance.
Reuse across two tree-instance keys rejects even when their scope enum is the
same. Capacity is exactly `2^depth`, where `0 <= depth <= 16`.
`CrossStorePaddedMerkleMembershipProof` contains the suite, tree scope,
scope-context digest, capacity-policy incarnation, depth, slot, item digest,
real-leaf nonce and exactly `depth` sibling hashes in leaf-to-root order. It has
no caller-supplied direction bits or root. Before path hashing, the verifier
recomputes the public pre-manifest digest, then recomputes the family-member
scope context and item digest from that digest, the signed family-manifest
fields and the capsule's exact envelope body/authentication. For the family-set
proof, it recomputes the scope context and item digest from the signed
completion fields and selected family body/full authentication-set digest.
Proof suite, scope, context, capacity-policy incarnation, depth and item digest
must equal those recomputed and signed values and the exact authenticated
historical capacity-policy incarnation retained for those manifests. Current
policy can restrict delivery or exact disclosure but cannot reinterpret an old
tree. Missing historical policy ancestry fails closed. Only then does
verification require `slot < 2^depth`,
recompute the real leaf and, for sibling `i`, use bit `i` of `slot` to place the
running hash left for zero or right for one, then compute node level `i+1`. The
final hash must equal the applicable signed manifest root. The depth-zero proof
has no siblings. Its sibling-hash body is at most 512 octets and its entire
canonical body must not exceed
`maximum_cross_store_membership_proof_bytes = 1024`.

An item count above pre-enrolled capacity rejects before mutation. Unknown
suite/version/tag/scope, reused
cross-scope seed, noncanonical field encoding, wrong proof length, duplicate
slot, caller direction bit or root/count mismatch rejects. Two different
canonical artifacts with the same component or item digest also reject before
mutation; they cannot collapse count or multiplicity. The construction
gives computational, not information-theoretic, topology hiding under the
stated SHA-256/HMAC and seed assumptions. Mandatory byte-exact conformance
vectors cover both scopes, depth zero, one real member, one versus capacity,
byte-exact producer/completion/family identity slots, item/slot permutation and
family-key-to-pool-slot assignment, tie-breaking, exact capacity, every
malformed proof field and same-capacity bundles with different hidden sibling
and shared-sidecar sets under an identical authorized view. Multi-capsule,
slot-correlation and colluding-recipient vectors assert the disclosed-union
lower bound and no more. Component vectors reject wrong projection, ordering,
width, uppercase or non-hex external spelling and ASCII-hex in place of raw
digest octets. No
implementation-selected suite is allowed.

Producer-internal recovery uses the retained openings to reconstruct the
byte-identical full hierarchy. Cross-store delivery uses a non-manifest
`CrossStoreProtectedOutputDeliveryCapsule` for each authorized envelope. The
capsule binds the audience and current privacy-policy assessment, envelope,
immutable family-manifest body/authentication, immutable completion-manifest
body/authentication, the canonical public pre-manifest commitment body and its
digest. The verifier recomputes that digest before it trusts the opaque producer
identity, credential-selection digest, suite, capacity-policy incarnation or
either manifest reference. The capsule carries a
fixed-shape member proof from that envelope to the padded family-member root
and a family-manifest proof to the padded family-set root. It never returns
sibling families,
envelopes, receipts, identities, sidecars or the private pre-manifest opening.
In the hiding branch it omits exact counts, scope seeds, count salts, item/slot
sets and sibling leaves; opaque Merkle sibling hashes remain mandatory. It is a
deterministic transport package, not an
authority-bearing artifact: it has no writer, CAS, identity allocation,
receipt, durable map or independent authentication. The signed immutable
envelope/manifests and Merkle proofs authenticate only immutable hierarchy
inclusion. The capsule's privacy metadata is not authority evidence.
Producer-local `CrossStoreTopologyDisclosureAssessmentCoordinate` binds the
exact `CrossStoreProducerPolicyOwner` selector/head/version, complete
authorization/audience-set root, current security head/version and cumulative
incident root, applicable clock/currentness context and complete assessment
digest. The server recomputes it immediately before every response; callers
cannot supply it. The capsule serializes no coordinate, token or control-plane
field. Its internal canonical derivation inputs are that coordinate, envelope
identity, audience and bounded delivery-request digest. Identical full internal
inputs return byte-identical bytes without persisted delivery state or fresh
randomness. Any assessment-affecting change creates a new internal input. A
hiding-only response needs no persistent delivery state. An exact-opening
response uses the separately linearized authorization ledger below. An ordinary
authority verifier treats the privacy branch as non-authorizing and verifies
only the immutable hierarchy. A later coordinate cannot change any producer
artifact or authority result. The response is
bounded by two complete
`maximum_cross_store_membership_proof_bytes = 1024` proof objects, the fixed
manifest/envelope/public-commitment limits and pre-enrolled
`maximum_cross_store_exact_opening_bytes`, which is the total of both optional
scope openings in one capsule. A server checks the complete response buffer
before derivation.

Closed `CrossStorePublicationHierarchyPrivacyProjection` is
`HIERARCHY_EXACT_TOPOLOGY_DISCLOSURE_AUTHORIZED |
HIERARCHY_FIXED_CAPACITY_HIDING_MEMBER_SET`, with closed
`CrossStorePublicationHierarchyPrivacyScope`:
`FAMILY_MEMBER_SET | PRODUCER_OUTPUT_FAMILY_SET`. This selector belongs to the
delivery capsule, not an immutable manifest. Both immutable manifests always
bind their hiding commitments. Exact
`CrossStorePublicationHierarchyDisclosureScopeAssessmentSet` is server-retained,
not serialized in the capsule. It contains one assessment for each scope and
binds the audience, current policy selector/head/version, complete
authorization-set root and the internal assessment coordinate. The capsule
serializes only each scope ID, selected projection branch and branch payload; it
exposes no policy/control-plane coordinate. An exact branch can carry only that
scope-specific tree opening: its exact item/slot set, scope seed and count salt.
It never carries the private pre-manifest opening, shared receipt/sidecar set,
another family's member opening or an unrelated scope seed. The branch requires
installed producer policy plus explicit authorization from every exact audience
principal, root or domain whose topology that scope exposes across every
audience-binding branch. This includes a prospective principal/root in
`PENDING_REGISTRATION_BOOTSTRAP` and the exact history domain in
`SOURCE_SECURITY_DOMAIN_HISTORY`; an empty registered-audience set cannot make
the predicate true. One pre-enrolled shared disclosure domain can substitute
only when its authenticated member set equals that exact complete represented
audience set. Missing, mixed, stale or withdrawn authorization selects hiding
for that scope, never exact disclosure.

Each individual or shared-domain authorization is a signed bounded
`CrossStoreExactTopologyDisclosureAuthorizationLease`. It binds the exact
authorizing principal/root/domain, complete represented audience-set root,
producer policy owner, permitted producer/family/scope projection, issuing
credential and publication evidence, authorizer clock identity/incarnation,
monotonic validity interval, maximum release horizon and withdrawal sequence.
Import binds the producer clock identity/incarnation, qualified
authorizer-to-producer clock relation, its applicability horizon and the
checked conservative upper/later producer-clock image of `valid_not_before`
plus the lower/earlier producer-clock image of `valid_not_after`.
Raw remote time is never compared with producer time. The producer imports the complete
canonical
`CrossStoreExactTopologyDisclosureAuthorizationLeaseSetRoot` into its local
`CrossStoreProducerPolicyOwner` head. A missing, unknown, expired,
not-yet-valid, superseded or non-current lease selects hiding. Every local lease
import, replacement or withdrawal writes that same policy-owner selector.
`release_not_after` is no later than the earliest applicable conservative local
expiry image, security/currentness cutoff and installed maximum release
horizon. Authorization requires producer time at or after every
applicable upper/later start image and strictly before every lower/earlier expiry
image. Expiry equality rejects. A missing, ambiguous, overflowed
or inapplicable clock relation, or a restart that cannot map every retained
lease to a no-later local cutoff, selects hiding. A remote
withdrawal stops exact disclosure when its authenticated cut wins local import,
or when the prior bounded lease expires, whichever comes first. NCP does not
claim instantaneous remote withdrawal across a partition. A policy that
requires that property cannot enable cross-store exact topology disclosure.

Exact disclosure has a separate bounded owner-local
`CrossStoreExactTopologyDisclosureAuthorizationLedger`, with
`CrossStoreExactTopologyDisclosureAuthorizationLedgerHead` and
`InstalledCrossStoreExactTopologyDisclosureAuthorizationLedgerSelector`. The
ledger is colocated and enrolled in the exact policy-owner selector's ADR-001
serializable transaction domain. If that colocation is unavailable, exact
disclosure is disabled. A remote pre-read or best-effort cross-store fence
cannot substitute. The server first materializes the complete capsule in a
private buffer, checks every response bound and captures the complete immutable
assessment/evidence snapshot. It then constructs the receipt-free
`CrossStoreExactTopologyDisclosureAuthorizationFact`, constructs the
`AuthorityTransactionCASCondition` that binds that fact and the complete read
set, and only then constructs the receipt-free
`CrossStoreExactTopologyDisclosureAuthorizationCandidate` that binds the fact
and condition. It compare-and-swaps the disclosure-ledger selector under closed
event
`AUTHORIZE_CROSS_STORE_EXACT_TOPOLOGY_DISCLOSURE`. Its complete
`CrossStoreExactTopologyDisclosureAuthorizationReadConditionSet` binds the
policy-owner selector/head and installed lease-set root, current security
selector/head and cumulative incident root, applicable currentness/clock
selector and incarnation, and the mutable authenticated transport
principal/credential/connection-admission selector. The imported local lease
set is the only audience-authorization input; every authorization import or
withdrawal co-writes the policy-owner selector. Every read selector and the
disclosure-ledger write must be enrolled in that one qualified serializable
ADR-001 domain. If any input cannot participate, exact disclosure is disabled.
The transaction manager validates the complete read set and evaluates
strict-before timing at the CAS linearization point. A pre-read time sample,
remote selector read or later check cannot substitute. The winning disclosure
CAS is the authorization linearization point. No capsule byte can reach
transport before it. If a restrictive policy, lease import/withdrawal,
security/incident/currentness/clock change or connection cut wins first, the
CAS loses and the server recomputes a hiding response. If the disclosure CAS
wins first, the exact byte string can be admitted only to its bound live
connection until its fixed `release_not_after`; a later mutation cannot retract
those already authorized short-lived bytes. It blocks every later exact
authorization under the new state. This ordering does not rewrite an
authenticated manifest.

Receipt-free `CrossStoreExactTopologyDisclosureAuthorizationFact` binds an
all-zero-forbidden, never-reused 32-octet decision identity; ledger owner and
incarnation; expected prior ledger head/selector; idempotency operation and
bounded request digest; opaque producer identity; public pre-manifest, selected
family body/full authentication-set, completion body/full authentication-set
and complete capsule digests plus actual canonical capsule byte length; the exact set of scopes selecting the exact
branch; audience binding, authenticated transport principal, credential, live
connection incarnation and delivery domain; observed policy-owner
selector/head/version and policy digest; complete
authorization-lease-set and represented-audience-set roots; security
head/version and cumulative incident root; clock/currentness context; complete
read-condition-set digest; canonical singleton
`RealmSecurityDeadlineConditionIntentSetRoot` whose sole member is the
receipt-free exact-disclosure deadline intent; complete
assessment digest;
`release_not_after`, fixed `STRICTLY_BEFORE_EXCLUSIVE_DEADLINE` comparator and
maximum response bytes. Hiding
scopes are absent from the exact-scope set. The fact binds the precomputed
encrypted, content-addressed
`CrossStoreExactTopologyDisclosureAuthorizationEvidenceBundle` digest and
excludes the `AuthorityTransactionCASCondition`, every candidate, installed
ledger head/selector, common transaction receipt and every post-CAS receipt.
The exact `AuthorityTransactionCASCondition` binds this fact digest and complete
read-condition set. Distinct
`CrossStoreExactTopologyDisclosureAuthorizationCandidate` binds the fact and CAS
condition digests, exact prior ledger head/selector, next version,
deterministic idempotency result, candidate record/byte deltas and resulting
counters/capacity state. It excludes installed coordinates, evaluations and
receipts. The CAS atomically installs the candidate-derived record and evidence
bundle under a successor ledger head. That
`CrossStoreExactTopologyDisclosureAuthorizationLedgerHead` binds owner,
incarnation, positive version, absent-prior native genesis or exact prior-head
digest, candidate digest, bounded idempotency-result map, used record/byte
counters, fixed record/byte caps and nonterminal/terminal capacity state. Every
successor increments version once, counters exactly and preserves all prior
members. Identity collision, reuse, rollback, fork, counter mismatch or cap-plus-one
selects hiding before mutation. The evidence bundle retains the exact signed lease set,
policy bytes, represented-audience membership evidence,
security/incident/currentness/clock state, qualified time-mapping evidence,
transport-principal/connection admission state and authenticated selector
ancestry for the audit horizon. The fact binds its digest, the candidate binds
the fact, and all three exclude every later receipt. The transaction emits
`CrossStoreExactTopologyDisclosureAuthorizationLedgerCommitReceipt`. That
generic commit receipt binds the prior/installed ledger heads/selectors, event
`AUTHORIZE_CROSS_STORE_EXACT_TOPOLOGY_DISCLOSURE`, the exact common
`AuthorityTransactionCommitReceipt` with its operation/domain coordinate and
exact commit-time
`RealmSecurityDeadlineConditionEvaluationSetRoot`, whose sole member is the
digest-matching evaluation for that singleton intent. A sibling post-CAS
`CrossStoreExactTopologyDisclosureAuthorizationReceipt` binds the candidate and
generic ledger commit. The ledger head, evidence bundle, generic commit and
specialized receipt are bound by the local
`AuthorityTransactionPersistenceManifest`. The complete selector-specific
receipt/sidecar set and that persistence manifest are crash-atomically durable
before transport admission. The installed ledger head excludes all later
receipts and the manifest. Receipt generation is deterministic and recoverable
inside that atomic persistence boundary.
The candidate, evidence and receipts are encrypted, integrity-protected local
audit material. Neither their identities nor any control-plane coordinate is
serialized in the capsule. Authorization audit recomputes the decision from the
complete evidence bundle and receipts. Content audit recomputes the capsule
digest from producer retention. Neither audit proves recipient receipt or
complete network delivery; without independent transport or recipient evidence,
delivery remains **NOT PROVEN**.

The ledger has fixed per-owner record and byte caps plus a non-evicting audit
retention partition. Same-operation retry with identical inputs returns the
byte-identical retained or rederived capsule only on the same still-live
authenticated principal, credential and connection incarnation before
`release_not_after`. A changed request, scope or binding rejects. A crash before
the CAS exposes no bytes and records no authorization. A crash after the CAS,
including an ambiguous transport result, conservatively means the topology
might have been disclosed. Exact transport requires one idempotent atomic
admission of the fully buffered authenticated frame to the exact
connection-bound send queue. Full-frame queue admission must occur strictly
before `release_not_after` under the exact clock identity/incarnation bound by
the candidate; equality or an incarnation mismatch rejects. The queue primitive
atomically validates that incarnation, connection admission state, delivery
domain and exact canonical frame bytes/digest/length against the installed
candidate with the enqueue. Its local decision-identity deduplication rejects
the same identity with different bytes, length or domain. No prefix can enter
that queue before the authorization CAS. A transport that cannot provide atomic
full-frame admission cannot serve the exact branch. Once admitted, later
partial network delivery is classified `MAY_HAVE_DISCLOSED`; the remainder is
never moved to a new connection under that authorization. Queue retry under the
same decision identity deduplicates the already admitted frame. A new
connection cannot reuse that authorization; it
requires a fresh current-policy decision or receives hiding. At deadline
equality, after the deadline, after a clock/currentness incarnation change, or
when hierarchy retention is missing or corrupt,
exact retry is forbidden. Capacity exhaustion, storage or authentication
failure, evidence-bundle loss, selector conflict and audit-ledger rollback or
fork select hiding or no response; none can evict history to admit a new exact
opening. Eventual
exhaustion intentionally disables new exact disclosure while hiding delivery
remains available. The acyclic order is hierarchy and retention -> fully
buffered capsule plus current assessment/evidence snapshot -> disclosure fact
-> CAS condition -> disclosure candidate -> ledger CAS -> authorization
receipts -> transaction persistence manifest -> atomic queue admission. No
producer artifact or capsule refers back to the disclosure ledger.

The server-retained hiding assessment binds the projection scope, manifest
digest, audience, current policy version and fixed privacy-suite ID. Its capsule
branch carries only the scope, manifest-bound proof and suite already fixed by
that manifest. Each immutable
manifest already binds its fixed capacity class, domain-separated padded root
and hiding count commitment salted with policy-minimum entropy retained only
for authorized producer/auditor opening. External capsules structurally omit
exact count, salt and sibling leaves. Real and dummy unused leaves and the
hidden occupancy pattern are computationally indistinguishable only between
worlds with the same fixed authorized view and capacity policy. The leakage
function includes every envelope and family already authorized to the
recipient, their family keys, proof slots, public manifests/roots, capacity
class and capsule count/timing. Multiple authorized capsules or colluding
recipients reveal at least the union of their own members and families; the
protocol does not claim to hide that lower bound. It hides only the count,
identity and shared sidecars outside that union. A
`SINGLE_REGISTERED_EXTERNAL_ROOT` recipient gets only its two scoped proofs.
Authorized audit can obtain the exact pre-manifest, family and completion
openings under separate audit policy; ordinary verification never requires
them. Thus “complete producer bundle” means the exact maximal producer and this
hierarchy, not every future transaction that consumes its output. A preallocated
future identity or reserve does not make a later independently committed
consumer artifact a sidecar of the earlier producer.

The pre-CAS fact allocates exact storage reserve for one immutable
`CrossStoreProducerBundleRetentionRecord` keyed solely by the opaque producer
identity. The pre-manifest private opening binds that reserve, not the record's
later content. After completion-manifest authentication, the producer finalizes
the record with the canonical public commitment body, pre-manifest private
opening, every family-member tree opening, the family-set tree opening, exact
authentication sets and exact retry bytes. The record is producer-private local
persistence metadata, not a protected output, shared sidecar, manifest member
or input to a completeness predicate. The pre-manifest, both manifest levels
and protected envelopes exclude its later content, digest and storage
authentication. Its self-excluding local integrity authentication and the
hierarchy persist in the same winning durable bundle before exposure; a torn
finalization publishes nothing. This order is completion authentication ->
retention finalization -> exposure and is acyclic.

The record is immutable and stored under authenticated encryption with
least-privilege producer/auditor access for the full verifiability life of the
source lineage, including after ephemeral authority expires. It has no mutable
retention state, erasure transition or independently authorizing receipt.
Read-only `CrossStoreProducerBundleRetentionAvailability` is exactly
`AVAILABLE_EXACT | UNAVAILABLE_FAIL_CLOSED` and is derived on every recovery,
delivery and audit from an integrity-checked record read. Missing, corrupt,
undecryptable or nonmatching material selects `UNAVAILABLE_FAIL_CLOSED`: no
capsule, audit opening, authority, positive continuation or positive closure can
be reconstructed from a digest alone. The affected lineage is quarantined or
retired until independent admissible evidence supplies a restrictive
alternative; loss is never interpreted as absence or completion.

`CrossStoreProducerRetentionCapacityPolicy` is stored and versioned by the same
exact `CrossStoreProducerPolicyOwner`; it has no independent writer. It bounds retained producer
count, private-opening bytes, proof-path bytes, exact-retry bytes and encrypted
archive bytes per lineage. It has non-borrowable partitions for ordinary work,
emergency fencing, final retirement and each registered role's closure bundle.
Registration preallocates the applicable closure record/byte positions.
Ordinary issuance stops when free capacity reaches the closure reserve; it
cannot consume that reserve or prevent a restrictive producer. A recovery
successor proves that every required reserve was preserved or replenished
before it reopens issuance. Every producer precharges its partition. Exhaustion
denies the relevant new producer and cannot evict an existing record. Backup,
restore and encryption-key rotation preserve the exact canonical bytes and
producer identity.

In every later type-specific clause, “a manifest binds an envelope, complete
bundle, receipt set or sidecar set” means that the pre-manifest private opening
commits to the expected exact value, the applicable derived tree opening
commits to the canonical output, and the public family body binds only its
padded root and hiding commitment. It never means that a public manifest
enumerates exact artifacts or counts. Exact topology appears only in a
separately authorized delivery opening.

Each family and completion manifest has a canonical self-excluding body that is
content-addressed and producer-authenticated under the exact precommitted
`CROSS_STORE_PUBLICATION_MANIFEST_AUTHENTICATION` credential selection and
retained commit ancestry. Their closed
`CrossStorePublicationManifestAuthenticationOrigin` is
`SOURCE_SECURITY_AUTHORITY_TRUST |
BOOTSTRAP_PARENT_OWNER_TRUST |
PENDING_REGISTRATION_RETURN_TRUST |
INSTALLED_IMPORTED_SECURITY_TRUST |
INDEPENDENT_ANCHOR_DOMAIN_TRUST`. The required producer mapping is:

| Protected producer/output | Credential selection | Required origin and ancestry |
|---|---|---|
| Source security-authority genesis | `GENESIS_CANDIDATE_ENROLLED` | `SOURCE_SECURITY_AUTHORITY_TRUST / ONLINE_PRIMARY`; authenticated genesis enrollment and complete key proof-of-possession set |
| Ordinary source output under predecessor continuity | `PREDECESSOR_INSTALLED` | `SOURCE_SECURITY_AUTHORITY_TRUST / ONLINE_PRIMARY` under the exact installed predecessor policy |
| Source key-change activation under bounded dual continuity | `DUAL_PREDECESSOR_SUCCESSOR` | `SOURCE_SECURITY_AUTHORITY_TRUST / ONLINE_PRIMARY`; predecessor and successor authentication sets over identical bodies |
| Exact allowlisted emergency, compromise declaration, restrictive recovery or domain retirement | `OFFLINE_PREDECESSOR_ENROLLED` | `SOURCE_SECURITY_AUTHORITY_TRUST / OFFLINE_RECOVERY_DOMAIN` under the exact preinstalled predecessor recovery policy |
| Parent allocation bootstrap | `PARENT_OWNER` | `BOOTSTRAP_PARENT_OWNER_TRUST` under the committed parent enrollment/owner-trust credential |
| Never-installed local cancellation | `PENDING_ALLOCATION_COMMITTED` | `PENDING_REGISTRATION_RETURN_TRUST`, exact `PENDING_GENESIS_BOOTSTRAP_RETURN / PRE_GENESIS_CANCELLATION`, and authenticated pending-allocation ancestry; installation and `FINAL_RETIREMENT` fields are forbidden |
| Any installed local-root return, including deny-only genesis, pending final retirement, active/retirement return and permanent history | `INSTALLED_IMPORTED_LOCAL` | `INSTALLED_IMPORTED_SECURITY_TRUST` under the exact source-committed credential installed in local imported-security state; payload and return phase match that installed state |
| Independent artifact anchor | `INDEPENDENT_ANCHOR` | `INDEPENDENT_ANCHOR_DOMAIN_TRUST` under the separately enrolled anchor credential and disjoint enrollment/failure-domain ancestry |

An ordinary verifier resolves the full historical
`CrossStoreProducerManifestCredentialSelection` and every referenced credential
set from its authenticated retained registry by the public selection and
credential-set digests. It recomputes the strict codec digests, then enforces
the exact purpose/origin, threshold, algorithm, policy ancestry, continuity
branch and issuance cutoff before checking the authentication set. A digest is
not a trust anchor or key locator supplied by the message. Missing, ambiguous,
retired-without-history, digest-mismatched or wrong-row registry material fails
closed.

Unknown, mixed, cross-row or cross-phase origin/ancestry rejects. The
authentication receipt/signature cannot be a member of the body that it
authenticates. No
recursive protected-envelope wrapper is required. A producer that has no such
retained authenticated family/completion hierarchy cannot export a conforming
envelope. This
includes return and permanent closure evidence; durable inner bytes or a valid
envelope signature alone are not a crash-complete publication.
Before its semantic CAS, every producer precharges the qualified worst-case
envelopes, public pre-manifest commitment and retained private opening, every
family manifest/authentication, completion manifest/authentication, both padded
roots and hiding commitments, every member/family proof and retained exact-retry
result bytes/signatures. The derived delivery path checks its bounded response
buffer and authorized exact-opening limit before serialization.
Exact capacity can commit; cap plus one rejects before mutation. A committed
transition cannot defer unreserved hierarchy storage to recovery.

In every later protected-output order, “envelope then manifest” is normative
shorthand for all producer commits/receipts/non-manifest sidecars and protected
envelopes, then `CrossStoreProducerPreManifestBundleCommitment`, every
deterministic family manifest/authentication, and the one
`CrossStoreProducerBundleCompletionManifest`/authentication. No order clause can
omit or bypass that expansion. A family manifest without the public commitment
digest,
a completion manifest with a missing/changed family, or a commitment that omits
any producer artifact rejects.

`CrossStoreSecurityReceiptVerificationEvidence` is created only after that
completion manifest. An ordinary verifier binds the exact envelope, public
pre-manifest commitment body and recomputed digest, family manifest, completion
manifest and delivery capsule. It verifies both complete manifest
authentication sets, both scoped membership proofs and the
producer's authenticated exact-completeness attestation against those public
inputs. This proves inclusion and an authenticated producer assertion; it does
not cryptographically prove hidden-set completeness to an ordinary verifier.
The producer conformance gate and an authorized audit verifier open and compare
the retained exact sets and verify the type-specific complete-set/bijection
predicate. Both verifier modes bind the
default-deny source-registry or local-owner trust policy, historical key-use and
revocation disposition, both manifest authentications, verifier clock/context
and canonical verification result. Generic verification cannot invent a
missing, unsigned or unauthenticated family/completion manifest or treat a
partial/torn producer export as complete. The DAG is producer candidates and
commits, receipts/sidecars and protected envelopes, pre-manifest commitment,
all family manifests/authentications, completion manifest/authentication, then
verifier evidence; no earlier artifact binds a later one.

This rule covers the parent allocation, pending registration, genesis
attestation, local installation/confirmation inputs, activation, pre-genesis
cancellation, planned fence and local final-retirement receipts. A receipt-free
local transition fact can bind those protected receipts and verification
evidence, but it cannot authenticate itself. Inner bytes without the envelope,
an envelope for another artifact/audience/operation, an unknown or retired
signing epoch for new issuance, a message-supplied key ID, or a chain outside the
pinned manifest rejects before semantic allocation. A normally
`RETIRED_FOR_NEW_ISSUANCE` key remains valid for historical verification of
artifacts committed before its exact cutoff. Ephemeral currentness artifacts
still expire at their fixed deadline. Durable commit and permanent-tombstone
artifacts have no authority-validity extension and remain permanently
verifiable under retained historical ancestry. They are never re-signed.

A key classified `REVOKED_COMPROMISE` does not silently inherit normal
retirement semantics.
`CompromisedHistoricalSecurityArtifactDisposition` is exactly
`INDEPENDENT_COMMIT_ANCHOR_PROVES_PRECOMPROMISE_ARTIFACT |
RESTRICTIVE_ALTERNATIVE_CLOSURE_REQUIRED |
UNTRUSTED_REJECT`. The first branch requires an independently authenticated,
append-only commit anchor ordered before the conservative compromise cutoff.
The second can only reduce authority or complete a separately qualified
isolation/closure path; it cannot recreate a lost positive grant or support a
positive continuation result such as reattach or fresh admission. Verification
grants only the exact inner receipt's closed meaning and never makes two stores
atomic.

The positive branch uses exact
`IndependentSecurityArtifactCommitAnchor`. Its sole writer,
`INSTALL_INDEPENDENT_SECURITY_ARTIFACT_COMMIT_ANCHOR`, is a separately enrolled,
append-only anchor domain whose signing/receipt keys, store and failure domain
are disjoint from the artifact emitter. The anchor head is hash-chained and
anti-rollback. The event emits exact
`IndependentSecurityArtifactCommitAnchorReceipt`. That receipt binds the
artifact/envelope digests, public pre-manifest commitment digest, exact selected
family-manifest canonical-body digest and authentication, completion-manifest
canonical-body digest and authentication, both scoped padded roots and proof
digests, the completion body's exact
`EXACT_PRODUCER_OUTPUT_SET_ATTESTED` field, exact verification-evidence digest,
original commit coordinates, emitter key/use/manifest ancestry, anchor
predecessor and installed head/selector/version, anchor transaction receipt,
trusted ordering evidence and authenticated monotone anchor-order coordinate.
The selected family and completion must verify as one completed hierarchy
before the anchor CAS; a family manifest alone is ineligible. The receipt
excludes the later protected anchor envelope and the anchor producer's
pre-manifest, family manifest and completion manifest. It also excludes every
future incident identity, compromise set, compromise cutoff and disposition.

Only after that receipt exists can the anchor producer create
`ProtectedIndependentSecurityArtifactCommitAnchorEnvelope`. This is the exact
`ProtectedCrossStoreSecurityReceiptEnvelope` specialization for the anchor
receipt. It selects
`DURABLE_HISTORICAL_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY`, binds the
anchored artifact's exact source realm/domain/lineage and replay domain, and
forbids an audience root and all current-authority window fields.
`CrossStoreProducerPreManifestBundleCommitment` then binds the complete anchor
transaction/receipt/envelope sidecar set.
`IndependentSecurityArtifactCommitAnchorPublicationManifest` is the sole
family manifest for the anchor-envelope family. It selects
`INDEPENDENT_ANCHOR_DOMAIN_TRUST`, binds the protected anchor envelope, complete
anchor transaction/receipt set, anchor signer/enrollment ancestry and padded
member root, then authenticates its self-excluding canonical body. The mandatory
`CrossStoreProducerBundleCompletionManifest` binds that authenticated family
through the padded family-set root and is authenticated last under the same
exact `INDEPENDENT_ANCHOR` credential selection. The anchor receipt and envelope
exclude both later manifests. The anchor event precharges the receipt, envelope, public
pre-manifest commitment/private opening, family manifest/authentication,
completion manifest/authentication, both scoped proofs and exact retry result
before mutation; cap plus one rejects before
installing the anchor.
The positive compromise disposition requires the exact original artifact
envelope/pre-manifest digest/family manifest/completion manifest/verification
and the exact anchor
envelope/pre-manifest digest/family manifest/completion manifest/verification.
Later
`CompromisedHistoricalSecurityArtifactDispositionEvidence` binds those exact
bundles and one authenticated incident declaration. Installed
`SecurityCompromiseIncidentDeclarationPolicy` fixes the sole incident authority,
allowed scope, conservative-cutoff method/schema versions, required input
classes and qualified cross-domain order/clock-relation profiles before an
incident. Every `SecurityAuthorityStateHead` binds one
`SecurityCompromiseIncidentCumulativeStateRoot`; genesis binds the canonical
empty root. Its map retains every declaration and, per affected scope, the
earliest conservative cutoff, complete input ancestry and cumulative
compromised-key set. A successor can only add a declaration, add compromised
keys or move a cutoff earlier; it cannot remove evidence, remove a key or move a
cutoff later.

`DECLARE_SECURITY_COMPROMISE_INCIDENT` is the sole writer. It is an exact global
security-authority CAS, not a parallel incident ledger. It uses
`OFFLINE_RECOVERY_THRESHOLD` and the enrolled offline-recovery management
instance, applies the complete emergency-fence obligation capture, installs
`EMERGENCY_FENCED_RECOVERY_REQUIRED`, and advances the semantic/revocation state
under the counter rules below. Its transition fact/candidate binds the expected
prior security selector/head/version and cumulative root, incident
identity/scope, installed policy, complete method/input-set root, conservative
earliest-possible compromise cutoff, source order/clock domain, complete
affected-key inventory/compromised subset, exact cumulative successor and
exact pending-registration terminalization set, exact captured
active/retirement-pending emergency-directive set, conditional two- to
four-family output inventory, family/completion identities, per-pending-root
closure-envelope identities, per-captured-root directive-envelope identities
and precharged retention/retry reserve. The global and
incident families are always present. The never-activated-closure family is
present if and only if that terminalization set is nonempty. The
emergency-directive family is present if and only if its captured set is
nonempty. The fact excludes installed heads and receipts.

After the global commit receipt, exact
`SecurityCompromiseIncidentDeclarationReceipt` binds the prior/installed
security heads/versions, prior/installed cumulative roots, incident fields,
common transaction receipt and offline-recovery receipt authentication. Its
protected envelope uses
`DURABLE_HISTORICAL_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY`; exact
`CrossStoreProducerPreManifestBundleCommitment` then binds the complete
declaration transaction/receipt/sidecar set, the mandatory
`GLOBAL_SECURITY_AUTHORITY_COMMIT` protected envelope and the distinct incident
declaration envelope, plus every conditional
`ProtectedExternalSecurityEnforcementRootNeverActivatedClosureEnvelope` and
`ProtectedExternalSecurityEnforcementRootEmergencyFenceDirectiveEnvelope`. Exact
`SecurityAuthorityGlobalCommitPublicationManifest` owns the global-commit
family. Exact
`SecurityCompromiseIncidentDeclarationPublicationManifest` uses
`SOURCE_SECURITY_AUTHORITY_TRUST / OFFLINE_RECOVERY_DOMAIN` and binds the
declaration-envelope family.
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest` owns
the conditional pending-root family.
`ExternalSecurityEnforcementRootEmergencyFenceDirectivePublicationManifest`
owns the conditional captured-root family. The mandatory
`CrossStoreProducerBundleCompletionManifest` binds the exact two, three or four
authenticated families and completes the bundle last under the same exact
`OFFLINE_PREDECESSOR_ENROLLED` credential selection. Candidate, global commit,
declaration receipt, all envelopes, public pre-manifest commitment, applicable
family manifests and completion manifest are one-way. The existing global
operation map gives exact retry; reserve exhaustion rejects before the CAS. A
sibling, rollback, version gap, missing family or completion, skipped cumulative
refinement or stale exact retry cannot publish.

The affected-key inventory covers every key/credential referenced by the
artifact emitter policy, artifact envelope/family/completion manifests, anchor
envelope/family/completion manifests and this declaration's offline-recovery
management/receipt/family/completion-manifest policy
ancestry; each is classified exactly once. Every declaration-authentication key
must be known and outside the compromised subset. Omission, duplicate,
self-compromised declaration authority or an anchor signer/manifest credential
in the compromised subset rejects the positive branch.

Cross-store incident evidence uses exact
`ProtectedSecurityCompromiseIncidentDeclarationEnvelope` in
`DURABLE_HISTORICAL_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY` and exact
`SecurityCompromiseIncidentDeclarationPublicationManifest` family manifest.
The disposition evidence requires that envelope, the matching global-commit
envelope, canonical public pre-manifest body/digest, both selected family
manifests/authentication sets, producer completion manifest/authentication,
both delivery capsules/scoped proofs and passing verification, then
read-validates the exact currently installed global
security head and latest applicable cumulative incident root at its source
authorization linearization point. It binds non-supersession of the selected
declaration, complete refinements and exact
`QualifiedSecurityCompromiseAnchorOrderRelation`, including both order/clock
domains, rate/offset/rounding uncertainty, applicability horizons and
conservative interval images, plus the strict-before evaluation. The retained
anchor's latest possible commit must be earlier than the current cumulative
earliest possible compromise cutoff. Equality, incomparable domains, expired
applicability, overflow or uncertainty-erased separation rejects. If current
head/non-supersession is stale or unavailable, only the restrictive or untrusted
disposition is legal. A remote historical verification alone grants no positive
continuation; the later source-authorizing CAS must bind that current read.
Unknown/incomplete method inputs and caller-selected or sibling incident
evidence reject. A bare anchor receipt or anchor head is insufficient. The
anchor receipt, envelope, family manifest and completion manifest cannot
bind that later cutoff and are never regenerated, re-signed or republished for
an incident. The anchor event is legal only after the artifact's authenticated
family and completion manifests exist; that completed hierarchy excludes the
later independent anchor. The anchor's qualification and enrollment must
predate the artifact. The later disposition verifier requires its keys and both
manifest credentials to remain outside the compromise set. A caller timestamp,
transparency URL, audit log from the same key domain or anchor created after the
conservative cutoff cannot select the positive branch. This is an anchor-domain
event, not a security-authority transition, and never mutates or bypasses the
security selector.
