# ADR-004 module — Cross-store observer closure and enrollment

> Status: PROPOSED and non-normative. Parent: ADR-004.

This maintained module is part of the bounded ADR-004 review source set. The decision registry binds its exact bytes with the parent decision. Read the parent first. This split changes review shape, not protocol meaning or release status.

## Source issuance and independent exposure-anchor closure

The independent challenge-exposure anchor is installed protocol
infrastructure. It is not an observer, consumer, extension role, or source
subprocess. The profile is unavailable until X05 externally qualifies the exact
installed subject.

The qualification binds one domain-separated digest for the exact provider,
corpus, installed source, Galadriel, Prisoma, policy, anchor-separation,
campaign, and limitation subjects. Each retained qualification, adjudication,
policy, ecosystem, fetch, revocation, and separation record is parsed as its
exact JSON schema. Its authentication binds the exact payload digest, issuer
control tuple, trust manifest, credential-issuance receipt, credential
signature, payload signature, and one exact zero-skip `PASS` verification
output. Trust, credential, verification, and receipt instants have strict
signed-64-bit ancestry and bounded validity.

Each source, anchor, issuer, adjudicator, fetcher, and revocation control tuple
records authority, owner, operator, authenticated principal, key fingerprint,
credential, security epoch, store, selector incarnation, and failure domain.
Owner and operator differ within a tuple. Required independent tuples differ by
kind and across the complete identity sets. Any same-field or cross-field alias
rejects.

The signed installed policy subjects bind finite clock, clock-relation,
capacity, retention, isolation, and publication policies to the exact
deployment manifest. The source, Galadriel, and Prisoma ecosystem subjects bind
their latest dependency receipts and exact retained build, deployment, and
installation artifacts. The live campaign binds the provider commit and tree,
deployment identity, build artifact, and deployment manifest before it executes
bootstrap, enrollment, append, relay, closure, rotation, revocation, fault, and
recovery. Each operation retains one exact zero-skip command output as a blob at
the passing receipt commit.

One independent security-and-operations adjudicator must issue signed `PASS`
for the qualification-subject digest. A separately controlled issuer signs the
external receipt. A separately controlled fetcher retains a redirect-free fetch
and exact fetched bytes. Separately controlled revocation authority and registry
subjects bind the same receipt and qualification digest.

All qualification, adjudication, fetch, revocation, receipt, expiry, and local
evaluation instants fit signed-64-bit Unix nanoseconds and use strict ordering.
Installed maxima have hard ceilings. Equality at a currentness maximum,
overflow, cap-plus-one, multi-decade validity, future evidence, expiry, and a
stale revocation check reject. This structural validation does not establish
organizational independence, live revocation, or installed-deployment truth.
Those facts require the external X05 gate. This infrastructure does not count
toward the nine consumer and extension role receipts.

Every logical source also has one generation-independent
`ObserverGrantSourceIssuanceIndexHead` through
`InstalledObserverGrantSourceIssuanceIndexSelector`. ADR-001 creates this
selector with the source lineage and retains it through every generation. The
closed index phase is `SOURCE_ISSUANCE_OPEN |
SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED`. The head binds the full source
namespace key, never-reused incarnation, positive version/prior, fixed entry and
byte caps, a fixed observer-root-admission cap, exact pending/eligible/frozen
counters, bounded idempotency map, canonical root-admission registry root/count,
canonical eligible-root audience set root/count, canonical issuance-entry
root/count, complete retained proof-node roots, exact closure reserve and phase.
The closed root-admission entry phase is `PENDING_ANCHOR_ENROLLMENT |
ELIGIBLE | CANCELED_BEFORE_SOURCE_CONFIRMATION |
FROZEN_BEFORE_SOURCE_CONFIRMATION`. Both registries are append-only while open.
No event deletes, rekeys, reuses or evicts an entry. Root-admission capacity
exhaustion blocks new eligibility publication. Issuance capacity exhaustion
blocks challenge issuance and forces source retirement before the reserved
freeze position is consumed.
Closed `ObserverGrantSourceIssuanceIndexEntryKind` is
`CHALLENGE_ISSUED | CANCELED_BEFORE_ISSUANCE`. The first binds the exact
generation-local challenge slot. The second burns a stable key whose
authenticated absent-intent cancellation won before challenge issuance; it
forbids every challenge and slot field. Both survive all successor generations.

`ObserverGrantSourceIssuanceStableKey` is the domain-separated canonical
projection of the authority realm, source kind and logical-session ID,
authenticated requester principal and observer-root incarnation, request
operation, request kind and logical-target key. It excludes the source
generation so the same logical request cannot be reissued in a successor
generation.

The source index also retains one immutable
`ObserverGrantSourceIssuanceEligibleObserverRootEntry` for every external
observer-root incarnation that can prepare an operation for this source
namespace. Closed
`PUBLISH_OBSERVER_ROOT_CHALLENGE_EXPOSURE_ANCHOR_ENROLLMENT_ELIGIBILITY`
is required first under the independent-anchor profile. Its receipt-free
`ObserverGrantChallengeExposureAnchorEnrollmentEligibilityFact` binds the LIVE
source namespace/allocation, open source-index head, exact ADR-009
registered-root hierarchy and current observer-role eligibility, root/store
incarnations, preallocated source-index and anchor entry keys, profile, fixed
expiry/currentness, capacity delta and protected output identities. One
source-domain CAS installs bounded
`ObserverGrantChallengeExposureAnchorEnrollmentEligibilityEntry /
PENDING_ANCHOR_ENROLLMENT` in the source index, reserves the eventual eligible
root and closure output capacity, and emits
`ObserverGrantChallengeExposureAnchorEnrollmentEligibilityReceipt`. The pending
entry grants no PREPARE, challenge issuance or observer authority.

Its post-CAS
`ObserverGrantChallengeExposureAnchorEnrollmentEligibilityProjection` binds the
receipt, LIVE namespace/allocation identity, root registration/activation and
role, source-index/anchor coordinates, profile and exclusive validity cutoff.
It also binds the complete qualified clock-relation value and its canonical
semantic digest. A relation name alone is not an identity.
It is delivered only to the intended anchor in
`ProtectedObserverGrantChallengeExposureAnchorEnrollmentEligibilityEnvelope`
under `EPHEMERAL_AUTHORITY_WINDOW / INDEPENDENT_ANCHOR_AUTHORITY /
OBSERVER_ROOT_ENROLLMENT_ELIGIBILITY`, with one family manifest, producer
completion, delivery capsule and both scoped proofs. Exact retry returns the
same hierarchy. Source freeze or role/security fencing prevents a new
eligibility publication and makes source confirmation lose; a later anchor
entry remains nonauthorizing until the source consumes its notification.
Closed
`CANCEL_PENDING_ANCHOR_ENROLLMENT_ELIGIBILITY_AFTER_CUTOFF` races source
confirmation on that same root-admission entry. It requires the exact pending
entry, a fresh qualified source-clock sample whose conservative lower anchor
image is at or after the eligibility cutoff, and current source-security,
registration and role comparisons. Its one source-domain CAS changes only that
entry to permanent `CANCELED_BEFORE_SOURCE_CONFIRMATION`, retains the
eligibility publication/anchor-coordinate digests and no-reuse tombstone,
releases only the source closure-output delta that is no longer reachable, and
advances the exact counters. It neither proves anchor non-enrollment nor
reclaims anchor capacity. Confirmation-first makes cancellation lose;
cancellation-first makes a delayed notification lose.
Cancellation binds the exact current security/registration/role selectors but
does not require the old eligibility state to remain authorizing. A restrictive
role or security change, or permanent retirement of the registered root, can
still narrow the pending entry. The current-status input is a closed union of
eligible and restrictive/fenced/retired states. Unknown, malformed or unowned
current state rejects. Confirmation, by contrast, requires the original
eligible registration/role/security ancestry to remain current.
Permanent source-index freeze partitions every root-admission entry in its same
source-domain CAS. It retains each `ELIGIBLE` entry in the closure audience and
changes each `PENDING_ANCHOR_ENROLLMENT` entry to permanent,
nonauthorizing `FROZEN_BEFORE_SOURCE_CONFIRMATION` at the same key. An existing
`CANCELED_BEFORE_SOURCE_CONFIRMATION` entry remains byte-equal. Both terminal
branches retain the eligibility publication and possible anchor-entry
coordinate, stay outside the closure audience and make delayed notification or
confirmation lose. Any anchor-side enrollment remains a bounded orphan and
keeps its anchor reserve until exact anchor retirement or permanent
source-isolation closure; source cancellation or freeze does not fabricate
anchor receipt or delivery state.

Closed
`ENROLL_OBSERVER_ROOT_IN_SOURCE_ISSUANCE_INDEX` is the only insertion event. Its
receipt-free `ObserverGrantSourceIssuanceObserverRootEnrollmentFact` binds the
expected open index head, exact ADR-009 registered-root hierarchy and current
observer-role eligibility, source namespace, root/store/selector incarnations,
availability profile, intended entry, capacity delta and preallocated output
identities. Under the independent-anchor profile it also consumes the exact
pending eligibility entry and the verified complete anchor source-notification
hierarchy, and requires the byte-equal anchor eligible-root entry. That
hierarchy consists of the protected source-notification envelope, its family
manifest, shared pre-manifest and producer completion, selected delivery
capsule, both scoped proofs and passing cross-store delivery verification. The
source-only profile forbids all pending-eligibility and anchor fields and
inserts directly from root-key nonmembership. The index candidate binds the
fact and common ADR-001 CAS condition. One source-domain transaction
read-compares the current source-lineage and local-security selectors. Under
the independent-anchor profile it consumes the exact pending entry, replaces it
at the same key with the eligible-root entry, transfers the already reserved
non-borrowable closure envelope/proof/retry capacity without charging it again,
and advances the index selector. Under the source-only profile it appends the
eligible-root entry, charges that reserve and advances the selector. Either
transaction installs all of its writes or none. Freeze-first, wrong role,
retired registration, changed incarnation, duplicate-different entry, a
missing or mismatched pending eligibility, missing anchor enrollment,
counter drift or cap-plus-one rejects.

Post-CAS `ObserverGrantSourceIssuanceObserverRootEnrollmentReceipt` is private
source evidence. Non-authorizing post-CAS
`ObserverGrantSourceIssuanceObserverRootEnrollmentProjection` binds its digest,
the immutable eligible-root entry, source namespace/index lineage, availability
profile and, when applicable, the anchor enrollment-entry digest. It excludes
the eligible-root count, sibling identities and private counters.
`ProtectedObserverGrantSourceIssuanceObserverRootEnrollmentEnvelope` uses
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`.
`ObserverGrantSourceIssuanceObserverRootEnrollmentPublicationManifest` owns the
one observer-root family; one pre-manifest and mandatory completion finish that
producer under `PREDECESSOR_INSTALLED /
SOURCE_SECURITY_AUTHORITY_TRUST` and the exact current source-security
manifest-authorization ancestry. The selected capsule, both scoped proofs and
passing verification are the root's durable eligibility evidence. Exact retry
returns the same hierarchy. Registration alone, a caller assertion or a
different source namespace does not make a root eligible.

`OBSERVER_GRANT_SPARSE_MERKLE_SHA256_V1` is the only 1.0 suite for the source
issuance index and independent exposure anchor. It uses SHA-256 and the closed
hash context `STABLE_KEY | SOURCE_ISSUANCE_INDEX |
INDEPENDENT_EXPOSURE_ANCHOR`; only the last two values are tree contexts. The
contexts are not interchangeable. Define
`LP(v) = U128_BE(length_in_octets(v)) || v` and
`E(tag, context, fields...) = LP(ASCII(tag)) ||
LP(ASCII("OBSERVER_GRANT_SPARSE_MERKLE_SHA256_V1")) ||
LP(ASCII(context)) || LP(field_1) ... LP(field_n)`. Define
`D(tag, context, fields...) = SHA256(E(tag, context, fields...))`. The exact
tags are `NCP1/OGSM/KEY`, `NCP1/OGSM/ENTRY`, `NCP1/OGSM/EMPTY`,
`NCP1/OGSM/PRESENT`, `NCP1/OGSM/NODE` and
`NCP1/OGSM/COUNT-COMMITMENT`.

Stable-key bytes use the exact strict projection above and canonical-digest
domain `ncp.observer-grant.source-issuance-stable-key.v1` from
`contract/canonical-digest.v1.json`. The raw 32-octet path is
`D("NCP1/OGSM/KEY", "STABLE_KEY", canonical_stable_key_bytes)`.
Source-index and anchor entry bytes use their complete self-excluding strict
projections and respective domains
`ncp.observer-grant.source-issuance-entry.v1` and
`ncp.observer-grant.challenge-exposure-anchor-entry.v1`.
For tree context `c`, the entry digest is
`D("NCP1/OGSM/ENTRY", c, canonical_entry_bytes)`, a present leaf is
`D("NCP1/OGSM/PRESENT", c, raw_key_digest, entry_digest)`, and the empty
leaf is `empty[0] = D("NCP1/OGSM/EMPTY", c, U64_BE(0))`.
For height `h` from the leaves, where `1 <= h <= 256`, an internal node is
`D("NCP1/OGSM/NODE", c, U64_BE(h), left, right)` and
`empty[h]` applies that equation to `empty[h - 1]` twice. Root traversal
consumes raw-key bits most-significant first: bit 0 is the high bit of octet 0
and bit 255 is the low bit of octet 31.

`ObserverGrantSourceIssuanceStableKeyNonmembershipProof`,
`ObserverGrantSourceIssuanceStableKeyMembershipProof` and
`ObserverGrantChallengeExposureAnchorStableKeyNonmembershipProof` and
`ObserverGrantChallengeExposureAnchorStableKeyMembershipProof` use one exact
8,272-octet canonical binary body. Octets 0 through 7 are ASCII `NCOGSPV1`.
Octet 8 is `0x01` for `SOURCE_ISSUANCE_INDEX` or `0x02` for
`INDEPENDENT_EXPOSURE_ANCHOR`. Octet 9 is `0x00` for nonmembership or `0x01`
for membership. Octets 10 through 15 are zero. Octets 16 through
47 are the frozen root, octets 48 through 79 are the raw key digest, and octets
80 through 8271 are 256 consecutive raw 32-octet sibling hashes. Sibling 0 is
adjacent to the leaf and sibling 255 is adjacent to the root. Nonmembership
verification starts with `empty[0]`. Membership is legal only for the source
or anchor context selected by the proof type and starts with the present leaf
recomputed from the separately supplied canonical source-index or anchor entry.
A cross-context entry or proof rejects. For proof index `i` from 0 through 255, it uses
raw-key bit `255 - i`; zero hashes `(current, sibling[i])`, and one hashes
`(sibling[i], current)`, with node height `i + 1`. The final value must equal the
encoded frozen root.

The proof does not carry the exact member count. The local closure receipt keeps
that count. Each protected closure envelope carries only the fixed capacity
class, whose strict projection uses canonical-digest domain
`ncp.observer-grant.sparse-index-capacity-class.v1`, and
`D("NCP1/OGSM/COUNT-COMMITMENT", c, independent_32_octet_salt,
U64_BE(exact_count), frozen_root, canonical_capacity_class_bytes)`. The producer
retains the salt for authorized audit opening. A verifier does not need the
count or salt for nonmembership. It compares the proof's frozen root
byte-for-byte with the root in the verified protected closure envelope.

Any other body length, magic, context byte, proof kind, reserved value, sibling
order, bit order, root or canonical projection rejects. A parser must not accept repeated
digest fields or ASCII hexadecimal in place of the fixed raw sibling block.
Distinct stable-key projections with the same path digest, or distinct entry
projections with the same entry digest, make the namespace unusable and force
restrictive retirement; they never overwrite or alias an entry. Mandatory
vectors cover empty and one-entry trees in both contexts, source membership,
anchor membership, the first and last path bits, malformed lengths, nonzero reserved bytes,
reversed siblings, context or proof-kind substitution, wrong canonical
projections and collision handling. The
source and anchor retain their exact maps and proof nodes for the full
namespace-tombstone lifetime.

`ISSUE_OBSERVER_GRANT_REQUEST_FRESHNESS_CHALLENGE` constructs one receipt-free
`ObserverGrantSourceIssuanceAppendFact`. It binds the expected open source-index
head/selector, exact enrolled observer-root member and enrollment-receipt
ancestry, exact stable-key nonmembership, intended index entry, expected
generation-local outer/freshness heads, challenge commitment, operation and
capacity delta. Under the anchor profile, the enrolled source member's bound
anchor-notification digest and the independently verified source-notification
hierarchy must match. The index entry binds the stable key, source generation, local
freshness-slot key, challenge-commitment digest and installed availability
intent under `CHALLENGE_ISSUED`; it excludes candidates and receipts. The
source-index candidate and
generation-local candidates bind the same fact, never one another. One qualified
ADR-001 transaction compares both selectors, appends the source entry and
installs the local `AVAILABLE` slot or installs neither.
`ObserverGrantSourceIssuanceIndexCommitReceipt` and the local freshness commit
bind their respective prior/installed heads and common transaction receipt. A
conforming delivery path cannot expose the challenge before that crash-complete
transaction, publication hierarchy and retention record are durable. This rule
does not claim containment after compromise of the qualified source authority.
Acceptance requires the same installed source-index entry. Cancellation from proved local
nonmembership races issuance in one authority-domain transaction over the
generation outer selector and source index. Cancellation-first atomically
installs `CANCELED_BEFORE_ISSUANCE` plus the generation-local absent-intent
tombstone, so issuance in this or a successor generation loses. Issuance-first
installs `CHALLENGE_ISSUED`, so the absent variant loses and the available-slot
variant must close that exact slot. Every later slot state preserves the source
index member.

Each source namespace installs one closed
`ObserverGrantPermanentNoLiveAcceptanceAvailabilityProfile`:
`SOURCE_RETIREMENT_ONLY |
SOURCE_RETIREMENT_OR_INDEPENDENT_CHALLENGE_EXPOSURE_ANCHOR`. The second profile
binds a pre-enrolled independent anchor authority, store/selector incarnation,
credential, failure domain, fixed capacities, clock/relation policy, isolation
qualification policy and publication policy before the source issuance index
can enter `SOURCE_ISSUANCE_OPEN`. Unknown/default profile, post-issuance anchor
enrollment, same-failure-domain authority, unbounded capacity, a
source-controlled anchor key or an isolation policy that the source can satisfy
alone rejects. Under `SOURCE_RETIREMENT_ONLY`, abrupt source loss cannot resolve
a prepared intent. It remains fail-closed until cooperative source retirement
produces the stronger frozen-index proof.

Closed event
`INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_REGISTRY_GENESIS_FROM_ANCHOR_AUTHORITY_ENROLLMENT`
is the only registry genesis. Its receipt-free
`IndependentAnchorNamespaceReservationRegistryGenesisFact` consumes the exact
active anchor-authority enrollment and qualification, typed registry-selector
absence and never-used proof, and a manifest-fixed complete authorized
source-owner set. For each owner, it binds one finite lifetime slot set and
non-borrowable participant/byte quota. It also binds the global count/byte caps,
fixed registry overhead and non-borrowable anchor-domain retirement reserve.
Checked integer sums require all owner quota maxima plus fixed overhead and the
retirement reserve to be at most their respective global caps. Duplicate owner,
slot or quota keys, overflow, a missing owner, a caller-selected quota or
aggregate oversubscription rejects before semantic allocation.

One anchor-domain CAS installs
`InstalledIndependentAnchorNamespaceReservationRegistrySelector`,
`IndependentAnchorNamespaceReservationRegistryHead / OPEN_RESERVATIONS`, the
complete zeroed owner/global counters, empty never-reused coordinate indexes and
the exact participant/reserve entries. Post-CAS
`IndependentAnchorNamespaceReservationRegistryGenesisReceipt` binds the fact,
candidate, installed selector/head and common transaction receipt. The fact,
condition, candidate and installed head exclude that receipt. No reservation,
anchor selector or cancellation tombstone can precede this genesis.

Each independent anchor authority owns one bounded
`IndependentAnchorNamespaceReservationRegistryHead` through
`InstalledIndependentAnchorNamespaceReservationRegistrySelector`. Its exact key
is the prepartitioned `(anchor_authority_key, source_owner_key,
source_owner_lifetime_slot)`. The immutable entry value binds the prospective
source realm/domain/principal, namespace, reservation-intent and later
allocation operations, preallocated lineage/source-index/anchor selector
incarnations and profile. Operation identity is not part of map absence and
cannot create a second reservation for the same slot. The head also owns
never-reused indexes for the source namespace and each lineage, source-index
and anchor-selector incarnation. Every reservation or cancellation-first
tombstone mutates the entry and all four indexes in one CAS. A coordinate
already owned by any other slot rejects. The head binds manifest-fixed global count/byte caps, a
non-borrowable anchor-domain retirement reserve, and one prepartitioned
count/byte quota with retained counters for each authorized source owner. One
owner cannot borrow another owner's quota. The closed entry state is
`RESERVED_PENDING_ANCHOR_GENESIS | MATERIALIZED |
TERMINAL_RETAINED`. Closed terminal cause is
`SOURCE_RESERVATION_INTENT_CANCELED |
SOURCE_NAMESPACE_ALLOCATION_CANCELED |
SOURCE_COOPERATIVELY_RETIRED |
SOURCE_PERMANENTLY_ISOLATED`. Each cause accepts only its exact hierarchy and
structurally forbids the other causes' claims. Entries and selector identities
are never deleted, reused or rekeyed.

Closed event
`RESERVE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_NAMESPACE_CAPACITY` consumes
the exact verified
`ProtectedSourceLogicalSessionNamespaceAnchorReservationIntentEnvelope`,
source-intent family, producer completion, delivery capsule and both scoped
proofs from the authenticated manifest-authorized source owner. The intent was
committed under the source namespace selector before this request and before
source namespace allocation. One anchor-domain transaction compares the active
domain, reservation registry, unused owner lifetime slot, all four never-used
coordinate indexes, typed never-used per-namespace selector absence and exact
global and source-owner participant/byte capacity. It installs
`IndependentAnchorNamespaceCapacityReservationEntry /
RESERVED_PENDING_ANCHOR_GENESIS` and non-borrowable worst-case genesis,
cancellation-terminalization and source-isolation reserves. Its post-CAS
`IndependentAnchorNamespaceCapacityReservationReceipt` binds the exact proposed
intent/operation, coordinates, owner slot/quota, global capacity charge,
prior/installed registry heads and installed coordinate-index entries.
`IndependentAnchorNamespaceCapacityReservationProjection` is returned only to
that source in
`ProtectedIndependentAnchorNamespaceCapacityReservationEnvelope`,
`IndependentAnchorNamespaceCapacityReservationPublicationManifest`, one
pre-manifest, producer completion, delivery capsule and both scoped proofs under
`DURABLE_HISTORICAL_COMMIT /
PENDING_SOURCE_NAMESPACE_ANCHOR_BOOTSTRAP /
ANCHOR_NAMESPACE_CAPACITY_RESERVATION`. Exact retry returns the same hierarchy.
A changed proposal, selector alias, owner-quota or global-capacity overflow,
post-allocation reservation, missing source intent or caller-supplied token
rejects.

Closed event
`FINALIZE_INDEPENDENT_ANCHOR_NAMESPACE_RESERVATION_AFTER_SOURCE_INTENT_CANCELLATION`
consumes the exact verified
`ProtectedSourceLogicalSessionNamespaceAnchorReservationIntentCancellationEnvelope`
and its permanent source tombstone. It accepts exactly two anchor entry
prestates. From typed entry/coordinate-index absence, it consumes the
prepartitioned owner lifetime slot and installs all four coordinate indexes plus
`TERMINAL_RETAINED / SOURCE_RESERVATION_INTENT_CANCELED`. From
`RESERVED_PENDING_ANCHOR_GENESIS`, it changes that exact entry to the same
terminal cause and consumes its precharged cancellation reserve. The owner
quota at registry genesis covers one worst-case terminal entry and all index
entries for every lifetime slot, so cancellation-first cannot lose to an
unrelated owner's work or a later ordinary reservation. `MATERIALIZED`, a
different slot/intent/coordinate, an unverified envelope or cap-plus-one owner
slot rejects. Exact retry returns
`IndependentAnchorNamespaceReservationIntentCancellationFinalizationReceipt`.
Cancellation-first makes a delayed reservation lose to the terminal entry.
Reservation-first makes cancellation close it. No anchor genesis or source
allocation can consume the canceled source intent.

The reservation is nonauthorizing and does not expire into a claim that the
source did not allocate. If its protected return is lost or the source
disappears, it remains charged and blocks anchor-authority-domain retirement.
Normal semantic retirement requires every reservation entry to be terminal.
The ADR-001 higher-root lost-domain path can permanently isolate the whole
anchor realm, but it does not fabricate local reservation terminalization or
release capacity. Loss detection, timeout, operator assertion, failed delivery,
source disappearance or anchor-domain retirement intent cannot substitute.
Registry and byte caps therefore bound abandoned reservations; cap exhaustion
rejects new independent-anchor allocations rather than overcommitting
cancellation closure.

`CREATE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR` creates
`InstalledObserverGrantChallengeExposureAnchorSelector` and version 1
`ObserverGrantChallengeExposureAnchorHead` in the independent anchor domain.
The head binds the source namespace and availability-profile digests, anchor
authority/store/selector/failure-domain incarnations, exact independent
credential selection, fixed entry/audience/byte caps, exact counters, bounded
idempotency map, eligible-observer-root set root/count, challenge-entry sparse
root/count/proof-node root, complete writer/admission policy, privacy/retention
policies and closed phase
`ANCHOR_OPEN | ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE |
ANCHOR_TERMINAL_AFTER_SOURCE_NAMESPACE_CANCELLATION`. Genesis is one qualified
anchor-domain transaction. It compares typed selector absence, the active
anchor-domain head, its bounded participant registry and exact
`RESERVED_PENDING_ANCHOR_GENESIS` reservation entry. It atomically installs the
selector and exact owner/ACL participant entry while changing that reservation
to `MATERIALIZED`; all capacity already belongs to the reservation. A
free-standing selector, unreserved capacity check or store-only insert is
invalid. Genesis also requires the exact verified
`ProtectedSourceLogicalSessionNamespaceAllocationEnvelope`, allocation family,
producer completion, delivery capsule and both scoped proofs. Every source
namespace, preallocated index/anchor incarnation, profile, authority, capacity,
policy, credential and reservation field must match the protected allocation
projection.
The bare receipt or a different allocation cannot substitute. A concurrent
source-side cancellation can still make this nonauthorizing anchor genesis
orphaned; it always makes later source registration lose. Its
`ObserverGrantChallengeExposureAnchorGenesisReceipt` remains a private anchor
audit artifact. Non-authorizing post-CAS
`ObserverGrantChallengeExposureAnchorGenesisProjection` binds its digest, the
empty roots, fixed policies and source namespace without private counters. It is
returned to the source only through
`ProtectedObserverGrantChallengeExposureAnchorGenesisEnvelope`,
`ObserverGrantChallengeExposureAnchorGenesisPublicationManifest`, the common
public pre-manifest and producer completion, both scoped proofs and passing
verification as
`DURABLE_HISTORICAL_COMMIT /
PENDING_SOURCE_NAMESPACE_ANCHOR_BOOTSTRAP /
ANCHOR_GENESIS_PROJECTION` under exact `INDEPENDENT_ANCHOR` credential
selection. The source profile binds that
verified immutable genesis bundle before it opens issuance.

For `ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE`, the independent closed
evidence state is `COOPERATIVE_ONLY | ISOLATION_ONLY |
COOPERATIVE_AND_ISOLATION`. It records which complete cause hierarchies have
been installed; it does not change the first terminalization cause, frozen
entry root or observer closure outputs.

Closed event
`FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_SOURCE_NAMESPACE_CANCELLATION`
consumes the exact verified
`ProtectedSourceLogicalSessionNamespaceAllocationCancellationEnvelope`,
selected cancellation family, source-producer completion, delivery capsule and
both scoped proofs. All source namespace, allocation, anchor selector,
incarnation, audience and cancellation-tombstone fields must match. Timeout,
typed remote absence, a bare receipt or a cancellation for a LIVE/different
namespace cannot substitute. The event has exactly two semantic cases. From
typed never-used anchor-selector absence plus the exact
`RESERVED_PENDING_ANCHOR_GENESIS` entry, it atomically installs the preallocated
selector and participant entry directly as
`ANCHOR_TERMINAL_AFTER_SOURCE_NAMESPACE_CANCELLATION`. From `ANCHOR_OPEN`, it
requires the exact genesis-only head with empty eligible-root, challenge-entry,
admission and in-flight sets plus the matching `MATERIALIZED` reservation, then
installs that same terminal state. Both cases change the reservation to
`TERMINAL_RETAINED / SOURCE_NAMESPACE_ALLOCATION_CANCELED`, consume its
precharged permanent-tombstone reserve and emit one private
`ObserverGrantChallengeExposureAnchorSourceCancellationFinalizationReceipt`.
Cancellation-import-first makes delayed anchor genesis lose to selector
presence. Genesis-first makes cancellation import close the empty orphan.
Enrollment or append cannot legally precede source registration, and every
later anchor mutation loses to the terminal state. Exact retry returns the
installed receipt. If the protected cancellation never arrives, the absent or
open orphan remains nonauthorizing and consumes its bounded reservation; the
anchor cannot infer cancellation or reclaim the identity. Permanent source
isolation finalization similarly changes a `MATERIALIZED` reservation to
`TERMINAL_RETAINED / SOURCE_PERMANENTLY_ISOLATED` in its same anchor-domain
transaction.

Every anchor mutation uses one acyclic graph. Receipt-free
`ObserverGrantChallengeExposureAnchorTransitionFact` binds one exact
event-specific subfact, expected selector/head, mutation projection, capacity
delta, deterministic output inventory and preallocated opaque output identities.
It excludes the `AuthorityTransactionCASCondition`, candidate, installed head
and every receipt. The CAS condition binds the fact and complete read/write
participant set. `ObserverGrantChallengeExposureAnchorTransitionCandidate`
binds the fact and condition, prior selector/head, resulting semantic projection
and counters; it excludes installed coordinates and receipts. The CAS installs
the candidate-derived successor head. Only then does
`ObserverGrantChallengeExposureAnchorCommitReceipt` bind the fact, candidate,
prior/installed heads and common `AuthorityTransactionCommitReceipt`. Every
specialized receipt and publication artifact depends on that commit receipt and
never appears in a fact, condition, candidate or installed head.

The anchor head contains an append-only
`ObserverGrantChallengeExposureAnchorEligibleObserverRootEntry` registry.
`ENROLL_OBSERVER_ROOT_IN_CHALLENGE_EXPOSURE_ANCHOR` admits one exact observer
root/incarnation only while the head is `ANCHOR_OPEN`. It consumes and verifies
the exact
`ProtectedObserverGrantChallengeExposureAnchorEnrollmentEligibilityEnvelope`,
its one-family manifest, pre-manifest, source producer completion, selected
delivery capsule, both scoped proofs and passing cross-store delivery
verification. The protected source projection must bind this anchor audience,
the exact LIVE source namespace/allocation, open source-index incarnation,
registered-root hierarchy, current observer-role eligibility, root/store
incarnations, preallocated source-index and anchor entry keys, profile,
capacity delta and unexpired cutoff under the profile's qualified clock
relation. A bare root registration, activation receipt, observer-audience
envelope, caller assertion or different source projection cannot substitute
for that hierarchy. Reuse, removal and aliasing are forbidden. Enrollment
charges non-borrowable reserve for that root's eventual closure envelope, proof
and retry bytes. Its
`ObserverGrantChallengeExposureAnchorObserverRootEnrollmentReceipt` remains a
private anchor audit artifact. Non-authorizing post-CAS
`ObserverGrantChallengeExposureAnchorObserverRootEnrollmentProjection` binds its
digest, exact immutable root entry and anchor lineage without the global
eligible-root count.
`ObserverGrantChallengeExposureAnchorSourceEnrollmentNotificationProjection`
binds the same receipt, profile, root/incarnation and entry digests but omits
observer-local state. The root projection is delivered only through
`ProtectedObserverGrantChallengeExposureAnchorObserverRootEnrollmentEnvelope`,
`DURABLE_HISTORICAL_COMMIT / SINGLE_REGISTERED_EXTERNAL_ROOT`, and one
`ObserverGrantChallengeExposureAnchorObserverRootEnrollmentPublicationManifest`
family. The source projection is delivered only through
`ProtectedObserverGrantChallengeExposureAnchorSourceEnrollmentNotificationEnvelope`,
`DURABLE_HISTORICAL_COMMIT /
SOURCE_NAMESPACE_INDEPENDENT_ANCHOR_RETURN /
OBSERVER_ROOT_ENROLLMENT_NOTIFICATION`, and one
`ObserverGrantChallengeExposureAnchorSourceEnrollmentNotificationPublicationManifest`
family. One pre-manifest declares exactly those two disjoint families and one
shared completion authenticates them under `INDEPENDENT_ANCHOR`. The observer
and source cannot consume each other's audience projection. Local source-index
enrollment then consumes the verified source-notification bundle and binds its
byte-equal entry digest. The anchor entry and observer projection alone grant no
PREPARE, challenge issuance or source-index eligibility; source confirmation is
the second stage of enrollment and loses to source freeze, registration
retirement or role fencing. Local
`PREPARE_OBSERVER_GRANT_REQUEST_INTENT` binds both the verified anchor
root-audience enrollment bundle and the later verified source-index
root-enrollment bundle. The source challenge issuer reads the installed
source-index eligible-root entry and retains the verified anchor
source-notification ancestry. Thus both final closure audiences come from their
respective complete enrollment registries, not from challenge entries; the root
that needs proof of zero entries is still present in both.

For the anchor profile,
`ANCHOR_OBSERVER_GRANT_CHALLENGE_BEFORE_EXPOSURE` runs only after the source
challenge producer has durably completed. Its event-specific
`ObserverGrantChallengeExposureAnchorAppendFact` binds the expected open anchor
head, exact eligible-root entry, stable-key nonmembership, intended
`ObserverGrantChallengeExposureAnchorEntry`, the verified anchor-audience
`ProtectedObserverGrantChallengeExposureAnchorCommitmentEnvelope`, selected
`ObserverGrantChallengeExposureAnchorCommitmentPublicationManifest`, shared
source-producer completion, delivery capsule and both scoped proofs,
source-index entry/commit ancestry, challenge commitment, requester, observer
root, paired-frame admission key, deadlines and capacity delta. The anchor projection contains the raw
stable-key digest, challenge-commitment digest, source-index entry/commit
digests, intended observer-root identity, paired-frame admission key, deadlines
and source-producer coordinate. It contains no challenge secret or requester-visible challenge
bytes. The fact also binds exact
`QualifiedObserverGrantChallengeExposureAnchorClockRelation`, source/anchor
clock identities and incarnations, both applicability horizons, and the
conservative lower/earlier anchor-clock image of
`SERVER_OBSERVER_REQUEST_ACCEPT_NOT_AFTER`. The anchor entry binds those
immutable source artifacts, the raw stable-key digest and the paired-frame
admission key. It excludes the
anchor candidate and every later receipt.
The relation's canonical semantic digest covers its identifier, both clock
identities and restart incarnations, reference coordinates, lower/upper offset
envelope, maximum relative-rate bound and both exclusive applicability
horizons. The offset envelope must cover the worst-case rate drift from the
reference coordinates over the complete horizons. Every enrollment,
confirmation, cancellation, append, admission and handoff compares the complete
relation value and digest. Reusing its identifier with changed offsets, rate,
horizon or restart incarnation rejects. All mapping uses checked bounded
integer arithmetic; overflow, underflow and a sample or mapped image outside
either horizon reject before a cutoff comparison.
The winning anchor CAS installs that entry under
`INDEPENDENT_EXPOSURE_ANCHOR`; append-first therefore preserves membership in
every successor root.

Post-CAS `ObserverGrantChallengeExposureAnchorAppendReceipt` remains private
anchor audit evidence. Non-authorizing post-CAS
`ObserverGrantChallengeExposureAnchorMemberProjection` binds its digest, exact
installed member, frozen source challenge commitment, paired-frame admission
key and anchor root, but not the global entry count or proof-node root.
The non-authorizing post-CAS
`ObserverGrantChallengeExposureAnchorAcceptanceAdmissionProjection` binds the
same receipt, member, stable-key, source-challenge, paired-frame admission key,
root and cutoff digests. It also binds one
`AnchorObserverAudienceOpaqueRelayBinding` over the exact sibling
observer-audience projection/envelope identity, canonical envelope-body digest,
canonical envelope-authentication-set digest, expected observer family key and
producer coordinate. This one-way binding is constructed after the observer
envelope and its authentication, but before the source projection and envelope.
It excludes the later observer family manifest, producer completion manifest,
delivery capsule and every digest of those objects. It authenticates the exact
observer envelope that the later relay capsule must contain, but does not grant the source
`SINGLE_REGISTERED_EXTERNAL_ROOT` audience-consumption evidence.
`ProtectedObserverGrantChallengeExposureAnchorReceiptEnvelope` wraps that
projection and uses
`EPHEMERAL_AUTHORITY_WINDOW / SINGLE_REGISTERED_EXTERNAL_ROOT`; its validity is
no later than that conservative mapped anchor cutoff.
`ProtectedObserverGrantChallengeExposureAnchorAcceptanceAdmissionEnvelope`
wraps the second projection for
`EPHEMERAL_AUTHORITY_WINDOW /
SOURCE_NAMESPACE_INDEPENDENT_ANCHOR_RETURN /
PAIRED_FRAME_ACCEPTANCE_ADMISSION`. One
`ObserverGrantChallengeExposureAnchorPublicationManifest` owns the observer
family; one
`ObserverGrantChallengeExposureAnchorAcceptanceAdmissionPublicationManifest`
owns the source family. The pre-manifest declares exactly those two disjoint
families and one completion authenticates them under `INDEPENDENT_ANCHOR`.
Observer and source cannot consume each other's projection. The append CAS and
later paired-frame admission do not reuse one sampled deadline result. Append
samples the named anchor clock at its CAS and requires that instant to be
`STRICTLY_BEFORE` the conservative anchor cutoff. Admission samples the named
source clock at its own CAS, applies the same qualified clock relation, and
requires the conservative upper/later anchor-clock image of that source sample
to be `STRICTLY_BEFORE` the cutoff. The relation, both clock incarnations,
sample, image, cutoff and applicability horizons enter the admission fact and
condition. Equality, either clock restart, an inapplicable mapping or
uncertainty that erases positive time rejects. No raw source monotonic instant
is compared with an anchor instant. Both families, the source-audience capsule,
retention record and exact retry bytes become durable before admission.

The registered observer retrieves its exact observer-audience
`CrossStoreProtectedOutputDeliveryCapsule` from the anchor under the verified
observer principal. It submits those canonical bytes to the source as bounded
untrusted opaque admission input. The source applies the capsule byte limit and
performs closed
`ObserverGrantAnchorObserverAudienceOpaqueRelayTransportVerification`. This
transport-only verification canonically parses the capsule framing; verifies
the anchor credential, observer envelope authentication, observer-family
manifest, common completion manifest and both membership proofs; requires the
producer, pre-manifest, credential, family and completion coordinates to equal
the already verified source-audience hierarchy; and requires the enclosed
observer envelope identity, canonical body digest and authentication-set digest
to equal `AnchorObserverAudienceOpaqueRelayBinding`. It does not evaluate the
observer principal predicate, accept the inner observer projection, authorize a
topology opening or produce observer-audience verification evidence. A changed,
truncated, extended, noncanonical, cross-producer or proof-invalid capsule
rejects before frame allocation. Missing observer-capsule bytes leave the
delivery gate pending. The observer later performs the full observer-audience
and inner-projection verification. Because the binding excludes both final
capsules and the completion manifest, the producer graph remains acyclic:
observer envelope, source envelope, both family manifests, common completion,
then delivery capsules.

Closed event `ADMIT_OBSERVER_GRANT_PAIRED_CHALLENGE_FRAME` is the sole
independent-anchor delivery edge. Its receipt-free
`ObserverGrantPairedChallengeFrameAdmissionFact` binds the expected source
authorization selector/head, exact `AVAILABLE /
ANCHOR_PAIRED_FRAME_PENDING` slot, open source-index selector/head and exact
issuance member; the preallocated admission key; the source producer's locally
retained exact observer-capsule bytes/coordinate; the verified source-audience
anchor hierarchy; its exact `AnchorObserverAudienceOpaqueRelayBinding`; passing
transport-only relay verification; and one fully buffered frame. The source
compares its source capsule with the locally retained bytes and records the
transport-verified anchor capsule byte-for-byte. It does not create or consume
observer-audience verification evidence. The frame binds those byte-identical
source and anchor observer capsules, their producer coordinates, stable key,
requester connection and replay domain. It never contains the source-audience
projection. The observer alone performs full audience and inner-projection
verification of both observer capsules after handoff and before it creates an
attempt. The fact also binds both clock incarnations, the
mapped cutoff, commit-time source sample, conservative upper/later anchor image,
one strict-before evaluation, exact record/capacity delta and the qualified
colocated queue implementation. It excludes the candidate,
installed head and every receipt.

One ADR-001 condition compares the source authorization and source-index
selectors in their enrolled source authority domain. The source authorization
candidate atomically changes the slot gate to
`ANCHOR_PAIRED_FRAME_ADMITTED` and installs the exact immutable
`ObserverGrantPairedChallengeFrameAdmissionRecord` in the subordinate
authoritative requester-facing queue. This queue and the freshness map are
projections of the same selector, and the CAS is the queue-admission
linearization; a later writer is not an authority edge. A remote queue, second
database or best-effort outbox cannot substitute. Post-CAS
`ObserverGrantPairedChallengeFrameAdmissionReceipt` binds the fact, prior and
installed outer/freshness/admission-registry projections, unchanged exact
source-index member and common transaction receipt. Candidate and installed
head exclude that receipt. The admitted record, not the receipt, is the
linearized queue authority. A crash after that commit is conservatively
`MAY_HAVE_BEEN_EXPOSED`; it is never evidence of successful delivery.

Pending retry or query returns only closed non-secret status
`ANCHOR_ADMISSION_PENDING` and no challenge, envelope, capsule or frame bytes.
Initial dequeue and every admitted retry use one qualified serialized handoff
primitive. This primitive is not a claimed atomic database-and-network
transaction. It acquires the selector shard's exclusive dispatch token,
read-compares the installed gate/record, requester connection, clock
incarnations and qualified relation, takes a fresh source-clock sample, and
requires its conservative upper/later anchor image to be
`STRICTLY_BEFORE` the installed cutoff. It keeps that token until the
transport reports that it accepted zero bytes or at least one byte, or until
the independent watchdog completes the full fence specified below. Every
terminal writer must acquire the same token before its selector CAS. No bytes
can enter another queue, process or transport buffer before this critical
section. A multi-leader dispatcher, expiring lease that leaves an old writer
able to use a socket, or store-only lock does not qualify. The primitive returns
the installed byte-identical frame only for its may-have-been-exposed delivery
result. Its zero-byte and fenced-outcome-unknown results return no frame bytes.
Equality, a changed connection/key/frame, terminalization-first or clock
restart also returns no frame bytes. Once the transport accepts any byte, the
result is conservatively `MAY_HAVE_BEEN_EXPOSED`, including partial write,
connection loss or crash; a later terminal outcome never claims otherwise.

The qualification also binds a finite manifest-fixed critical-section bound,
nonblocking kernel-enqueue semantics and an independently enforced dispatcher/
socket fence. Closed
`ObserverGrantPairedChallengeFrameHandoffQuiescenceResult` is
`ZERO_BYTES_ACCEPTED_TOKEN_RELEASED |
MAY_HAVE_BEEN_EXPOSED_TOKEN_RELEASED |
OUTCOME_UNKNOWN_DISPATCHER_AND_SOCKET_FENCED`. The first two require the
transport call to return within the bound. The outcome-unknown branch requires
the watchdog to make the unique dispatcher and every aliased descriptor unable
to enqueue later bytes before it releases or recovers the token; it is always
classified `MAY_HAVE_BEEN_EXPOSED`. A timeout signal, canceled future, expired
lease or process-health guess without that socket fence is not quiescence.
Cutoff evaluation and a nonblocking enqueue occur in the same bounded critical
section; a transport whose enqueue can complete after that section or after a
failed cutoff does not qualify. If the fence cannot be proved, the record
remains admitted and terminalization remains blocked; the deployment must
disable the anchor profile rather than claim bounded recovery.

Terminal or consumed query returns only its exact terminal/consumed commits and
creates no new exposure. Cancellation, expiry, clock cut, acceptance and source
finalization compare the same outer selector and partition every
pending/admitted record and queue handoff. A transport that cannot colocate the
authoritative queue or provide this finite serialized handoff in the source transaction
domain cannot enable the anchor profile.

The observer verifies both capsules before it creates a request attempt. Source
acceptance read-compares the admitted gate and exact admission record, verifies
the separately retained source-audience capsule and source-index member, and
requires the request to echo the same admission key, frame digest and anchor
entry identity. An issued but unanchored or anchor-appended-but-unadmitted
challenge can therefore be neither validly exposed nor accepted.

Cooperative source retirement uses closed event
`FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_COOPERATIVE_SOURCE_RETIREMENT`.
It consumes the exact
`ProtectedSourceLogicalSessionCooperativeAnchorRetirementEnvelope`, selected
source family, pre-manifest, producer completion, delivery capsule, both scoped
proofs and passing cross-store verification under
`INDEPENDENT_ANCHOR_AUTHORITY /
SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT`. The projection must bind this anchor
authority/selector, namespace-allocation operation, capacity-reservation entry
and profile, the matching permanently retired source namespace and lineage,
frozen source-index head/root and closure receipt, complete accepted-grant
closure, no successor and exact source-retirement receipt. The source derives
those anchor coordinates from its immutable verified namespace-allocation
binding before issuance opens. A caller-selected or sibling anchor cannot be an
export audience, even when it names the same source namespace. A bare
retirement receipt, observer-audience source-closure envelope, timeout, source
unreachability or permanent-isolation assertion cannot substitute.

Receipt-free
`ObserverGrantCooperativeSourceRetirementAnchorFinalizationFact` binds that
verified hierarchy, the current anchor head, exact reservation entry,
deterministic output inventory and
`ObserverGrantChallengeExposureAnchorFinalizationAssessment`. The assessment
proves the complete eligible-root and challenge-entry inventories, retained
sparse proof nodes, complete anchor writer/replica/outbox set, empty anchor
mutation/delivery in-flight sets and sufficient precharged closure reserve. It
does not contain or imply the independent permanent-isolation inventory. One
anchor-domain CAS preserves the exact eligible-root and entry maps, changes the
head to `ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE /
COOPERATIVE_ONLY`, changes the
matching reservation from `MATERIALIZED` to `TERMINAL_RETAINED /
SOURCE_COOPERATIVELY_RETIRED`. The transaction does not refund or decrement the
precharged owner/global participant counters or byte charge. The retained
terminal entry, proofs, publication and retry continue to consume that exact
charge. Only permanent retirement of the complete anchor authority domain can
make the domain's capacity unavailable for reuse and reclaim its storage as one
closed unit. Append-first
places the member in the retained final root. Cooperative-closure-first makes
later enrollment, append, exposure and acceptance-supporting output lose.
Exact retry returns the same post-CAS
`ObserverGrantChallengeExposureAnchorClosureReceipt`, which binds
`COOPERATIVE_SOURCE_PERMANENT_RETIREMENT`, the source-retirement projection
digest, final anchor head/root, audience, proof-node root and common transaction
receipt and forbids isolation evidence. A different source retirement, head or
finalization partition rejects.

Abrupt recovery uses closed event
`FINALIZE_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_AFTER_PERMANENT_SOURCE_ISOLATION`.
Its receipt-free
`ObserverGrantPermanentAcceptanceAuthorityIsolationFact` binds the exact
availability profile, current anchor head and a manifest-fixed canonical
bijection over every reachable authority surface and its permanent terminal
evidence. Closed `ObserverGrantAcceptanceCapabilitySurfaceKind` is
`SOURCE_LINEAGE_NAMESPACE_AND_INDEX |
SOURCE_GENERATION_FRESHNESS_AND_GRANT_REGISTRIES |
CHALLENGE_SIGNING_PUBLICATION_AND_DELIVERY |
REQUEST_INGRESS_VALIDATION_AND_ACCEPTANCE |
GRANT_SIGNING_REGISTRY_AND_RETRY |
REPLICA_BACKUP_RESTORE_AND_RECOVERY |
RESTART_SUCCESSOR_AND_ALTERNATE_BOOTSTRAP |
DERIVED_AUTHORITY_CONSUMER |
BODY_OR_PLANT_ACTUATOR_AUTHORITY`. The last kind is mandatory when any derived
grant can authorize a physical effect. The inventory covers every process,
credential/HSM member, store, selector, replica, cache, outbox, queue, in-flight
operation, recovery image, failover, alternate endpoint and derived consumer.
For each surface outside the anchor transaction domain, the fact consumes the
exact
`ProtectedObserverGrantAcceptanceCapabilitySurfaceIsolationEnvelope`, selected
`ObserverGrantAcceptanceCapabilitySurfaceIsolationPublicationManifest`, that
producer's completion and capsule, both scoped proofs and passing verification
under the manifest-fixed non-source trust origin and
`PERMANENT_CLOSURE_TOMBSTONE / INDEPENDENT_ANCHOR_AUTHORITY /
OBSERVER_GRANT_ACCEPTANCE_CAPABILITY_SURFACE_ISOLATION`. The protected
projection binds the concrete surface, prior authority coordinate, permanent
terminal cut, credential destruction/revocation evidence, replica/recovery
partition and no-successor result. Anchor-owned surfaces instead participate
directly in the anchor CAS. A physical branch consumes the body or plant
final-authority isolation envelope; a protocol-layer assertion cannot
substitute. Each accepting credential is irreversibly destroyed or revoked
under that evidence, every state/recovery path is permanently terminal, every
in-flight set is empty or terminally denied, and no restart, successor, restore
or bypass can recreate acceptance. Unknown kinds, a missing surface or
hierarchy component, source-only testimony, reversible administrative disablement
or an unbounded inventory rejects.

The isolation fact also binds
`ObserverGrantChallengeExposureAnchorFinalizationAssessment`. That assessment
proves the exact eligible-root and challenge-entry inventories, retained sparse
proof nodes, complete anchor writer/replica/outbox set, empty anchor mutation and
delivery in-flight sets and reserved output capacity. The isolation fact
separately binds the installed qualified independent-isolation evidence;
the common assessment does not make that cause-specific claim. Enrollment,
append and closure compare the same
anchor selector. Append-first places the member in the final root.
Closure-first installs
`ANCHOR_FROZEN_AFTER_TERMINAL_SOURCE_CLOSURE / ISOLATION_ONLY`, so later enrollment, append,
exposure and acceptance-supporting output lose. The anchor candidate binds the
isolation and finalization facts and preserves the exact entry root. The
post-CAS `ObserverGrantChallengeExposureAnchorClosureReceipt` binds those facts,
the final head/root, local exact count/proof-node root, complete audience set,
closed cause and common transaction receipt. Its cause-specific input is a
closed union: `COOPERATIVE_SOURCE_PERMANENT_RETIREMENT` binds the exact
cooperative source-retirement hierarchy and fact and forbids every isolation
field; `PERMANENT_SOURCE_ACCEPTANCE_AUTHORITY_ISOLATION` binds the exact
isolation fact/evidence and forbids every cooperative-retirement field.

Closed
`REFINE_FROZEN_OBSERVER_GRANT_CHALLENGE_EXPOSURE_ANCHOR_WITH_MISSING_SOURCE_CLOSURE_EVIDENCE`
is the only frozen-head self-edge. From `COOPERATIVE_ONLY`, it consumes the
complete independently qualified permanent-isolation fact/evidence and changes
only the evidence state to `COOPERATIVE_AND_ISOLATION`. From
`ISOLATION_ONLY`, it consumes the complete verified cooperative
source-retirement hierarchy/fact and makes the same change. One anchor-domain
CAS read-compares the frozen head, retained reservation and cause hierarchy.
It preserves the first terminalization cause, reservation cause/counters,
frozen eligible-root and challenge-entry roots, observer closure receipt and
all published bytes. It emits only a retained local
`ObserverGrantChallengeExposureAnchorClosureEvidenceRefinementReceipt`; it
creates no new authority, observer family or revised closure claim. Same-cause
exact retry returns the prior receipt. A changed hierarchy, downgrade, second
root, reopen or incomplete cause rejects. Independently discovered evidence
therefore narrows audit truth monotonically without rewriting the closure that
already resolved protocol work.

For a nonempty eligible-root set, one non-authorizing post-CAS
`ObserverGrantChallengeExposureAnchorNamespaceClosureProjection` per root binds
the closure-receipt digest, anchor context and frozen root, fixed capacity class,
salted hiding count commitment, availability profile, closed cause, exact
cooperative source-retirement or independent-isolation assessment digest,
exact audience and operation. Its cause is
`COOPERATIVE_SOURCE_PERMANENT_RETIREMENT |
PERMANENT_SOURCE_ACCEPTANCE_AUTHORITY_ISOLATION`; each branch requires its
matching exact evidence and structurally forbids the other branch. It excludes the exact count,
proof-node root and count salt. Its
`ProtectedObserverGrantChallengeExposureAnchorNamespaceClosureEnvelope` uses
`PERMANENT_CLOSURE_TOMBSTONE / SINGLE_REGISTERED_EXTERNAL_ROOT`. One
`CrossStoreProducerPreManifestBundleCommitment` binds the complete shared
receipt/sidecar set and one-family envelope partition.
`ObserverGrantChallengeExposureAnchorNamespaceClosurePublicationManifest` owns
that family, and the mandatory completion authenticates it last under the exact
`INDEPENDENT_ANCHOR` selection. Retention and exact retry become durable before
exposure. A proved-empty eligible set emits no hierarchy. Every enrolled root
can later retrieve its immutable closure capsule plus one deterministic unsigned
`ObserverGrantChallengeExposureAnchorStableKeyResolutionProof` against the
frozen root. Its closed kind is
`FROZEN_ANCHOR_KEY_NONMEMBERSHIP |
FROZEN_ANCHOR_KEY_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED`.
The first carries
`ObserverGrantChallengeExposureAnchorStableKeyNonmembershipProof`. It proves no
anchor-qualified exposure for that stable key; it does not prove that the source
never issued an unanchored challenge. The second carries
`ObserverGrantChallengeExposureAnchorStableKeyMembershipProof` and the exact
canonical anchor entry. It proves that the anchor append committed and that the
closure hierarchy permanently removes every acceptance path. It says only
`MAY_HAVE_BEEN_EXPOSED_BUT_ACCEPTANCE_PERMANENTLY_CLOSED`; it does not prove
queue admission, remote receipt, nonacceptance or absence of a formerly live
grant. The query selects membership or nonmembership from the retained exact map
and creates no receipt, signature, manifest or mutation.


## External composite-state enrollment and retirement

Every standalone composite root has one durable anti-ABA enrollment in its
owner trust domain's bounded `ExternalCompositeStateEnrollmentRegistryHead`.
Only `InstalledExternalCompositeStateEnrollmentRegistrySelector` selects that
head, whose phase is `OPEN_ENROLLMENT | RETIREMENT_DRAIN_ONLY | TERMINAL`.

Sole genesis
`EXTERNAL_COMPOSITE_STATE_ENROLLMENT_REGISTRY_GENESIS_FROM_OWNER_TRUST_ROOT`
uses receipt-free `ExternalCompositeStateEnrollmentRegistryGenesisFact`. It
binds typed absence, never-used incarnation, authenticated owner/trust digest,
exact transaction manager/store,
`ExternalCompositeStateEnrollmentStoreQualification`, role schema, quotas, and
`ExternalCompositeStateEnrollmentClosureReserve`. Qualification proves one
crash-complete parent-plus-role CAS, receipts, and manifest. Per allocation, the
reserve holds a pre-genesis-cancel or final-retirement position. Per
source-registered role, it also precharges the maximum emergency work-set CAS,
subordinate receipts, protected return, verification, and manifest with
restrictive priority/counter headroom. Missing either closure path rejects.
ADR-009 verifies the reserve, especially for
`LOCAL_TERMINAL_EVIDENCE_REQUIRED`. Rebind replenishes it, and capacity cannot
borrow mandatory-fence positions.

`TRUSTED_DELIVERY_BOUNDARY` also fixes
`TrustedDeliveryBoundaryNoInstallTombstoneReserve`, with one count/byte-bounded
position per sequence in the matched ADR-009 root/ledger incarnation and cap.
Confirmation requires exact cap equality and per-position space for the largest
fact, entry, commit, receipt, and tombstone. Direct no-install, complete
emergency, and final retirement consume each position once. Ordinary work
cannot. Exact cap succeeds. Cap-plus-one rejects before append, and map
exhaustion cannot erase a grant or block its no-install record.

Sealed role keys are `TRUSTED_DELIVERY_BOUNDARY | OBSERVER_ADMISSION |
CONSUMER_SEMANTIC_CAPTURE`. Entry state is the sole one-use marker:
`ALLOCATED_NEVER_USED | INSTALLED | PERMANENTLY_RETIRED`. Entries are never
removed or reused, and no parallel Boolean, nonce, or field can disagree.

The closed role-to-direct-realm field product is:

| Role | Direct `AuthorityRealmKey` field |
|---|---|
| `TRUSTED_DELIVERY_BOUNDARY` | `REQUIRED_EXACTLY_ONE` |
| `OBSERVER_ADMISSION` | `REQUIRED_EXACTLY_ONE` |
| `CONSUMER_SEMANTIC_CAPTURE` | `FORBIDDEN_MULTI_REALM_EVIDENCE_ONLY` |

Capture binds each immutable input's original realm in evidence/segment state.
Its parent grants no direct provider realm. Missing, extra, defaulted, or
role-inconsistent presence rejects.
The two source-registered roles also bind one exact ADR-009
`ExternalSecurityEnforcementRootPublicationManifestCredentialCommitment` and
owner-authenticated
`ExternalCompositeStateEnrollmentManifestCredentialProofOfPossessionSet` for
its
`CROSS_STORE_PUBLICATION_MANIFEST_AUTHENTICATION` key. The set binds the
allocation operation, role/root/owner/store/incarnation, algorithm, threshold,
fresh owner-enrollment challenge and replay domain. It has one
fingerprint/key-epoch possession member for every threshold key.
`CONSUMER_SEMANTIC_CAPTURE` binds typed inapplicability and structurally forbids
that credential product. Missing, default, message-selected, cross-role or
wrong-use credentials reject.
`ALLOCATE_EXTERNAL_COMPOSITE_STATE_ENROLLMENT` constructs
`ExternalCompositeStateEnrollmentAllocationFact` over exact owner/trust state,
role-root key, state incarnation, selector, role-table direct-realm presence,
manifest-credential product, qualification, entry transition, and closure
position. Its winning CAS installs `ALLOCATED_NEVER_USED` with that immutable
product.

Allocation, cancellation, role genesis and final retirement use receipt-free
`ExternalCompositeStateEnrollmentCASCondition` over expected parent
head/version, exact absent-or-installed role selector/head/version,
qualification, closed read/write set, and reserve delta. The DAG emits
`ExternalCompositeStateEnrollmentRegistryCommitReceipt`. Allocation also emits
`ExternalCompositeStateEnrollmentAllocationReceipt`, binding the parent result
and selector version plus the exact manifest-credential commitment/proof or
typed inapplicability. Only that receipt's digest derives the prospective
ADR-009 key and exact `PENDING_REGISTRATION_BOOTSTRAP` protected envelope. The
envelope binds allocation ancestry, intended source realm/domain/lineage,
operation, key and the same credential product, and grants only deny-only
pending creation.
`ExternalCompositeStateEnrollmentRegistryPersistenceManifest` binds the bundle,
selected envelope bytes, and signer ancestry last. Recovery returns the same
qualified deterministic or retained append-only envelope. Otherwise only
cancellation remains. Pre-read, losing, foreign-role, bare-allocation, and
two-store substitutes reject.

Every child CAS binds
`ExternalCompositeStateEnrollmentParentCurrentnessCondition` over exact parent
selector/head/version, entry key/state, and trust digest. Closed
`ExternalCompositeStateEnrollmentRoleEventClass` is
`NEW_AUTHORITY_OR_ADMISSION |
PREAUTHORIZED_IMMUTABLE_OBLIGATION_DRAIN |
RESTRICTIVE_FENCE_OR_REVOCATION |
EVIDENCE_RETENTION_NO_NEW_AUTHORITY |
CLOCK_RESTART_NO_EXTENSION |
ROLE_FINALIZATION`.

The parent-phase product is exact:

| Parent phase / entry | Permitted child event classes |
|---|---|
| `OPEN_ENROLLMENT / INSTALLED` | Every class, subject to the role's native guards |
| `RETIREMENT_DRAIN_ONLY / INSTALLED` | All classes except `NEW_AUTHORITY_OR_ADMISSION` |
| `TERMINAL` or `PERMANENTLY_RETIRED` | None |

Allocation and unused cancellation are parent-only over
`ALLOCATED_NEVER_USED`. Drain classes can fence/revoke, map time without
extension, retain admitted evidence, drain committed outbox, close keyed work,
and finalize. They cannot create grants, admissions, segments, reservations,
outputs, callbacks, mutations, delivery rights, or stronger results. The
closed union in this module assigns exactly one class per event. The retained
selector matrix is diagnostic only. Unknown, absent, or multiple classes reject.
`FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_EMERGENCY` is exactly
`RESTRICTIVE_FENCE_OR_REVOCATION` and consumes emergency reserve.
`REBIND_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_AFTER_EMERGENCY` is exactly
`NEW_AUTHORITY_OR_ADMISSION`. Drain rejects it. Success replenishes
successor-authority reserve.

“Sole” child selector means sole mutable role root. It does not remove the
parent read.

Parent BEGIN conflicts with every child read. After it, only the drain row can
commit. Missing, rolled-back, sibling, or unverifiable parent state denies
despite a child open label. Sole exception
`FENCE_EXTERNAL_COMPOSITE_ROLE_ON_PARENT_LOSS` installs only native deny/drain
from qualified `ExternalCompositeStateEnrollmentParentLossIsolationEvidence`.
It cannot invent a tombstone or replacement. Restored ancestry permits only the
phase-product successor. Permanent loss requires a separately enrolled parent
and retained orphan evidence binding last parent head/selector, exact
child/authority footprint, loss mode, isolation, and permanent no-resume.

`BEGIN_EXTERNAL_COMPOSITE_STATE_ENROLLMENT_REGISTRY_RETIREMENT` alone changes
`OPEN_ENROLLMENT -> RETIREMENT_DRAIN_ONLY`.
`ExternalCompositeStateEnrollmentRegistryRetirementPreparationFact` binds
parent head, complete entry set, and closed
`ExternalCompositeStateEnrollmentRegistryRetirementCause`:
`CAPACITY_EXHAUSTED |
OWNER_TRUST_WITHDRAWAL_RESTRICTIVE_CLOSE_STILL_QUALIFIED |
ADMINISTRATIVE_RETIREMENT`. The commit freezes that set and emits
`ExternalCompositeStateEnrollmentRegistryRetirementPreparationReceipt`.
The withdrawal branch requires an independently prequalified restrictive-close
authority, intact selector/durability continuity, and a close-signing credential
that the exact ADR-009 source entry still accepts. A revoked, compromised,
unknown, or message-selected credential cannot produce source terminal evidence.
The source must use its derivation horizon or retain
`LOCAL_TERMINAL_EVIDENCE_REQUIRED`. Unknown causes, allocation, and genesis
reject in drain. Only unused cancellation, exact installed-role drain classes,
atomic role finalization, and parent FINAL remain.

`FINALIZE_EXTERNAL_COMPOSITE_STATE_ENROLLMENT_REGISTRY_RETIREMENT` alone changes
drain to irreversible `TERMINAL`.
`ExternalCompositeStateEnrollmentRegistryRetirementFinalizationFact` binds the
exact frozen-entry/permanent-tombstone bijection, retained roots, and reconciled
reserve. Its CAS emits the parent commit,
`ExternalCompositeStateEnrollmentRegistryRetirementFinalizationReceipt`, and
manifest. Any set/tombstone/reserve mismatch rejects. Terminal has no successor.

For `TRUSTED_DELIVERY_BOUNDARY | OBSERVER_ADMISSION`, exact ADR-009 order is
`local allocation -> REGISTERED_PENDING_LOCAL_GENESIS +
RegisteredExternalSecurityEnforcementRootReceipt ->
PENDING_SOURCE_CONFIRMATION/FENCED_DENY local genesis -> REGISTERED_ACTIVE +
RegisteredExternalSecurityEnforcementRootActivationReceipt -> fresh-attested
newer CURRENT local import`.
`REGISTER_EXTERNAL_SECURITY_ENFORCEMENT_ROOT` consumes allocation and
`CONFIRM_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_LOCAL_GENESIS` consumes exact local
installation. ADR-009 exclusively defines immutable fields, deadlines,
feasibility and one-use rules for
`RegisteredExternalSecurityEnforcementRootKey`,
`QualifiedExternalAuthorityDerivationHorizonPolicy`,
`AuthenticatedExternalSecurityEnforcementRootGenesisCurrentnessAttestation` and
`ISSUE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_GENESIS_CURRENTNESS_ATTESTATION`.
ADR-004 preserves exact registry/audience/store/selector ancestry. Pending grants
nothing. Only the post-CAS event consumes the genesis marker. Retired, reused,
late, or unmappable input cannot install `CURRENT_IMPORT`.

Local genesis compares the parent, changes
`ALLOCATED_NEVER_USED -> INSTALLED`, and installs the role selector,
`PENDING_SOURCE_CONFIRMATION` outer root, `FENCED_DENY` mirror and exact
allocation-committed publication-manifest credential in the parent entry,
native outer head and imported-security state. The transaction verifies local
possession and exact equality of use, fingerprint, epoch, algorithm, threshold,
validity and historical-verification/rotation policy. A proposal, message key or
different locally available key cannot substitute. Its bundle emits the native
publication receipt,
`ImportedRealmSecurityMirrorTransitionReceipt`, parent commit,
`ExternalCompositeStateEnrollmentInstallationReceipt`, and final manifest.
Source inputs are one closed
`ExternalCompositeStateEnrollmentImportedSecurityGenesisEvidence` containing
exactly two completed ADR-009 producer bundles. The registration bundle
contributes the exact
`ProtectedRegisteredExternalSecurityEnforcementRootReceiptEnvelope`, selected
`RegisteredExternalSecurityEnforcementRootPublicationManifest`, shared
completion, delivery capsule, two scoped proofs, inner pending receipt and
passing verification. The later currentness bundle contributes exact
`ProtectedSecurityAuthorityCommitReceiptEnvelope /
PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / ATTESTATION_ISSUANCE`, selected
`ExternalSecurityCurrentnessCommitPublicationManifest`,
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`, selected
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest`, their shared
completion, both delivery capsules and scoped proofs, matching inner attestation,
passing verification and qualified clock relation. Every digest and
registered-root audience must match across both bundles. Cross-producer
completion substitution, one currentness family, a bare receipt or a digest of a
missing bundle rejects. The candidate binds only the complete
`RealmSecurityDeadlineConditionIntentSetRoot` and qualified profiles.
Both mapped genesis/confirmation deadlines are strict-future. Receipts and
manifest, but no successor, bind exact
`RealmSecurityDeadlineConditionEvaluationSetRoot`. Pre-lock samples, bare
inners/receipts, one family without completion, wrong audiences, and historically
unqualified signers reject.

Every enrollment-related local-to-source return uses one
`ProtectedExternalCompositeStateEnrollmentReturnEnvelope` with closed payload:
`LOCAL_DENY_ONLY_GENESIS_INSTALLATION |
PRE_GENESIS_CANCELLATION |
PLANNED_FENCE |
FINAL_RETIREMENT |
PERMANENT_HISTORICAL_REFINEMENT`. It binds the exact native/parent heads,
commits and receipt, registered key/root, source operation and replay domain.
`LOCAL_DENY_ONLY_GENESIS_INSTALLATION` also binds the installed
publication-manifest credential and its equality proof to the allocation/source
registration commitment; every other payload preserves or historically names
that credential ancestry as applicable.
Genesis installation, pre-genesis cancellation and deny-only pending final
retirement require ADR-009
`REGISTERED_SOURCE_AUTHORITY / PENDING_GENESIS_BOOTSTRAP_RETURN`.
Planned fence and active/retirement final return require
`REGISTERED_SOURCE_AUTHORITY / ACTIVE_OR_RETIREMENT_RETURN`; permanent
refinement requires `PERMANENT_HISTORICAL_REFINEMENT`. Cross-phase or
cross-payload fields reject.
`ExternalCompositeStateEnrollmentReturnPublicationManifest`, the exact ADR-001
persistence-manifest specialization, authenticates the envelope and complete
local bundle last. Each source consumer requires that manifest, membership and
passing verification; a bare installation, cancellation, fence or final receipt
cannot confirm or close source state.

ADR-009 receipt-free
`ExternalSecurityEnforcementRootLocalGenesisConfirmationFact` binds exact
installation/native commit, installed selector/head/incarnation, mirror key,
initial fence, owner/store, installed publication-manifest credential, its
allocation/source commitment equality, protected envelopes and verification;
proposals do not substitute, and CONFIRM is strict-before its fixed deadline.
PREPARE closes
REGISTER/CONFIRM: confirm-first snapshots the active root; prepare-first
terminalizes pending source. Local remains deny-only until tombstone import and
retirement; emergency has the same no-reactivation result.

The planned set is exactly `REGISTERED_ACTIVE | RETIREMENT_PENDING`; pending is
excluded/non-authorizing and takes
`SOURCE_SEMANTIC_CHANGE_BEFORE_ACTIVATION` when PREPARE/emergency wins. Planned
activation/recovery applies complete per-entry reauthorize-or-retire; predecessor
manifests cannot resurrect.

ADR-009 owns sequence, cap, horizon and restart contracts for
`ISSUE_REALM_SECURITY_CURRENTNESS_ATTESTATION`,
`ExternalSecurityCurrentnessIssuanceHead`,
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationReceipt`,
`AuthenticatedRealmSecurityCurrentnessAttestation`,
`IMPORT_AUTHENTICATED_REALM_SECURITY_SUCCESSOR`,
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope`,
`QualifiedRealmSecurityImportClockRelation`, `external_authority_horizon_not_after`,
`APPLY_REALM_SECURITY_ATTESTATION_CLOCK_RESTART`,
`RealmSecurityAttestationClockRestartReceipt` and
`LOCAL_TERMINAL_EVIDENCE_REQUIRED`. `CURRENT_IMPORT` requires a strictly newer
per-key head plus unchanged global `CURRENT`, exact
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope`
and selected
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`
hierarchy, exact durable `ProtectedSecurityAuthorityCommitReceiptEnvelope` and
`ExternalSecurityCurrentnessCommitPublicationManifest` family, exact ephemeral
`ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope` and
`InstalledRealmSecurityCurrentnessAttestationPublicationManifest` family, their
shared currentness completion, both capsules/proofs, audience, ancestry and
clock proofs. Active sequence starts at 1, increments once, differs
from genesis nonce and is exact-retry stable; cap-plus-one, reuse, loss, expiry
equality or either lineage alone denies. Horizon is monotonic; restart advances
all extant heads by one complete no-extension map, preserves the permanent marker
and never re-dates authority.

Mirror state implements the closed ADR-009
`ImportedRealmSecurityRegisteredEntryEvidence` by
`ImportedRealmSecurityCurrentnessEvidence` product. Only `CURRENT` plus
`CURRENT_AUTHORIZATION_HIERARCHY` and
`COMPLETE_CURRENTNESS_HIERARCHY` installs `CURRENT_IMPORT`.
`NO_CURRENTNESS_HIERARCHY_FENCE_ONLY` imports the authenticated newer
global/root coordinate but installs `FENCED_DENY` and no deadline. Exact pending
or retirement-pending hierarchy fences. A non-`CURRENT` global descendant can
fence through `NO_ENTRY_PROJECTION_FENCE_ONLY`, but cannot claim a per-root
state or acknowledge a directive. Exact never-activated or active-retirement
permanent hierarchy retires that root; exact global `DOMAIN_RETIRED` can retire
without a root projection. The strictest result wins; unknown, incomplete or
impossible products reject.

`CANCEL_EXTERNAL_COMPOSITE_STATE_ENROLLMENT_BEFORE_ROLE_GENESIS` can change
`ALLOCATED_NEVER_USED -> PERMANENTLY_RETIRED` only with typed role-selector
nonmembership, unused marker and proof that genesis did not commit. It emits
`ExternalCompositeStateEnrollmentPreGenesisCancellationReceipt`.

ADR-009 then uses
`CANCEL_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`
or
`EXPIRE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_REGISTRATION_BEFORE_LOCAL_ACTIVATION`.
Closed `ExternalSecurityEnforcementRootNeverActivatedClosureEvidence` is
`LOCAL_PRE_GENESIS_CANCELED |
LOCAL_DENY_ONLY_ROOT_FINALLY_RETIRED |
SOURCE_CONFIRMATION_DEADLINE_ELAPSED |
SOURCE_SEMANTIC_CHANGE_BEFORE_ACTIVATION |
SOURCE_DOMAIN_RETIREMENT_DRAIN_BEFORE_ACTIVATION`. Cancellation accepts only the
first two receipts, expiry only the third at/after its fixed deadline, and
PREPARE/emergency only the fourth. Domain drain alone accepts the fifth. Each
terminalizes only pending state, emits
`ExternalSecurityEnforcementRootNeverActivatedClosureReceipt`, retains the key
and forbids activation evidence. A local root can install the matching permanent
mirror state only from exact
`ProtectedExternalSecurityEnforcementRootNeverActivatedClosureEnvelope`,
`ExternalSecurityEnforcementRootNeverActivatedClosurePublicationManifest`,
producer completion, capsule, both scoped proofs and passing verification under
`PERMANENT_CLOSURE_TOMBSTONE / SINGLE_REGISTERED_EXTERNAL_ROOT`. The hierarchy
origin must equal the selected evidence branch. Global history alone can fence,
but cannot prove this per-root terminal state.

Final role retirement atomically installs its terminal head and parent
`PERMANENTLY_RETIRED` tombstone, emitting
`ExternalCompositeStateEnrollmentFinalRetirementReceipt`. The persistence
manifest binds both heads/receipts last; otherwise the role stays deny/drain.

For an active source entry,
`BEGIN_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT` first installs
`RETIREMENT_PENDING` and stops attestations. The local product import claims that
per-root state only from exact
`ProtectedExternalSecurityEnforcementRootRetirementPendingEnvelope`,
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest`, producer
completion, capsule, both scoped proofs and passing verification with the exact
closed origin. Global restrictive ancestry without that hierarchy can still
fence, but cannot capture a root high-water. The local root then
drains/finalizes. The normal
`FINALIZE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_RETIREMENT` branch consumes the
exact protected `FINAL_RETIREMENT` return envelope, publication manifest and
passing verification before the source tombstone. The local permanent mirror
then requires exact
`ProtectedExternalSecurityEnforcementRootRetirementEnvelope`,
`ExternalSecurityEnforcementRootRetirementPublicationManifest`, producer
completion, capsule, both scoped proofs and passing verification for that
tombstone. Exact
`SOURCE_DERIVED_AUTHORITY_HORIZON_ELAPSED_NO_FUTURE_AUTHORITY` is legal for a
`RETIREMENT_PENDING` entry in source `CURRENT | DOMAIN_RETIREMENT_DRAIN` when
the qualified policy bounds every derivation and its final boundary enforces
expiry. Unbounded/ambiguous/unenforceable authority records
`LOCAL_TERMINAL_EVIDENCE_REQUIRED` and requires the local receipt. Retained
immutable evidence is non-authorizing. Source/local commits remain separate.

`CONSUMER_SEMANTIC_CAPTURE` creates no live provider authority. It accepts only
admitted immutable evidence, does not source-register, but still consumes parent
allocation/reserve at genesis/final retirement.

No transaction spans source and local stores. Registration, deny-only genesis,
confirmation and activation are separate receipt-linked commits. Missing role
state after parent `INSTALLED`, rollback, sibling genesis, entry-state replay or
recreated absence is corruption, never empty authority/evidence state.

Canonical `TrustedDeliveryReleaseStateHead` is the sole composite delivery-
authority root, never a snapshot beside effective selectors. Each incarnation
serves one `AuthorityRealmKey`; another realm needs a distinct parent-enrolled
root/selector/state/credential namespace. It binds realm, boundary principal/
instance/domain, strict incarnation/version/prior, ADR-009
`ImportedRealmSecurityMirror`, local clock,
`TrustedDeliveryBoundaryGrantMapHead`, release sequence/output slots,
`TrustedDeliveryBoundaryNoInstallTombstoneReserveHead` and bounded outbox/drain.
Closed phase is
`PENDING_SOURCE_CONFIRMATION | OPEN_AUTHORITY |
EMERGENCY_FENCED_CLOSURE_PENDING |
EMERGENCY_FENCED_RECOVERY_REQUIRED | RETIRED_DRAIN_ONLY | TERMINAL`.
Only open permits grant prepare/activation, reservation create/commit or output-
slot allocation; drain-only is irreversible closure and terminal has no edge.
Recovery-required is non-authorizing, binds the complete predecessor terminal/
no-restart partition, and permits evidence retention, finalization, newer fence,
retirement or guarded recovered-source rebind. Closure-pending is non-authorizing
without claiming preadmitted work closed; it permits only restrictive closure,
retention, retirement or permanent isolation and cannot satisfy complete-fence
recovery.

The reserve head binds immutable allocation/incarnation, exact cap and canonical
positions keyed by ADR-009
`(RegisteredExternalSecurityEnforcementRootKey, grant-ledger incarnation,
allocated_grant_sequence)`, not ADR-004 issuance sequence. State is
`AVAILABLE | CONSUMED_DIRECT_NO_INSTALL | CONSUMED_EMERGENCY_CLOSURE |
CONSUMED_FINAL_RETIREMENT | RETIRED_NEVER_ISSUED`. Genesis makes every position
available. Direct no-install, complete emergency and final retirement consume
each issued position once in their release-selector CAS; final retirement also
retires high-water-proved unissued positions. Outer heads/facts/receipts bind
prior/installed roots, giving crash/retry and competing closure paths one
occupancy truth; receipt-only debit, double consume or reuse rejects.

Canonical bounded `TrustedDeliveryBoundaryGrantKey` is complete
`(AuthorityRealmKey, source_session_kind, logical_session_id, generation,
registry incarnation, {requester principal, grant-lineage incarnation},
issuance sequence, grant digest)`. Its `TrustedDeliveryBoundaryGrantStateHead`
value binds strict version/prior, descriptor revision/digest, installed
activation, revocation, exact `boundary_prepare_close`,
`boundary_release_not_after`, `boundary_latest_server_activation_at`, positive
conservative `boundary_minimum_activation_budget_upper`, and phase
`PREPARED_BOUNDARY_GRANT | LIVE_BOUNDARY_GRANT |
TERMINAL_BOUNDARY_GRANT | TRANSPORT_QUIESCENT_BOUNDARY_GRANT`. Prepared binds
its fact, live the server activation-set receipt, terminal the local terminal
fact/cause, and quiescent closed
`TrustedDeliveryBoundaryGrantQuiescentOrigin`:
`TRANSPORT_DRAIN_PROVED | NEVER_INSTALLED_ZERO_WORK`; these bind respectively
the quiescence fact, or no-install fact, pending-never-LIVE proof, permanent key
tombstone and zero-work roots. Each entry owns bounded pending reservations/pre-
release commitments and has no selector.

Every map key equals the root realm. Its common mirror binds authenticated source
head/selector/version/commit, semantic/security/revocation epochs, never-used
local incarnation/version, propagation and exclusive
`security_mirror_not_after`.
`INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE` uses the release selector,
monotonic source ancestry and exact affected grants/reservations; release needs
that mirror strict-before cutoff. Only first
`IMPORT_AUTHENTICATED_REALM_SECURITY_SUCCESSOR` with active registration, fresh
attestation and clock relation takes
`PENDING_SOURCE_CONFIRMATION/FENCED_DENY -> OPEN_AUTHORITY/CURRENT_IMPORT`;
refresh, registration alone and same-head import cannot.

When the imported source head is ADR-009 `PREPARED_CHANGE`, the exact
`FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_PREPARED_CHANGE` semantic case
consumes its root-addressed
`ProtectedPlannedSecurityExternalEnforcementFenceDirectiveEnvelope`, selected
`PlannedSecurityExternalEnforcementFenceDirectivePublicationManifest`, producer
completion, delivery capsule, both scoped proofs and passing verification. The
directive's global head/commit, candidate, target membership/projection,
registered local incarnation and captured child tuple must match the local
root. The local CAS installs `FENCED_DENY`, closes the complete
predecessor-authorized release set and co-commits
`PlannedSecurityExternalEnforcementFenceReceipt`. A remote prepared head,
source-history envelope or mirror receipt without this directive hierarchy and
installed release-root result cannot satisfy planned source activation.
Here `security_mirror_not_after` is the ADR-009 mirror's sole trusted local
expiry, not a second caller-controlled deadline.

For ADR-009 `EMERGENCY_FENCED_RECOVERY_REQUIRED`, exact
`FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_EMERGENCY` consumes the source
commit/head through the root-addressed
`ProtectedExternalSecurityEnforcementRootEmergencyFenceDirectiveEnvelope`,
selected
`ExternalSecurityEnforcementRootEmergencyFenceDirectivePublicationManifest`,
producer completion, delivery capsule, both scoped proofs and passing
verification. Its matching incident, registered-root capture, required epoch
and child tuple are exact. The global
`DURABLE_HISTORICAL_COMMIT / SOURCE_SECURITY_DOMAIN_HISTORY` envelope remains
ancestry-only and cannot replace the directive.
Restrictive import needs no fresh authority window. Its mode is
`IMPORT_NEW_EMERGENCY_AND_CLOSE |
CLOSE_ALREADY_IMPORTED_SAME_INCIDENT`: the latter preserves the already
authenticated mirror coordinate but must advance the outer selector. A bare
message, expiry, same-head no-op or generic mirror receipt emits no closure.

Receipt-free `ExternalCompositeEmergencyAuthorityClosureCommitment` binds the
parent condition, prior outer selector/head, mirror, incident/epoch/capture and
canonical complete `ExternalCompositeEmergencyAuthorityWorkSetCommitment`.
That set covers every predecessor grant, request, reservation, outbox/drain
attempt, declaration, frame admission, callback and derived action/effect. Each
key has one `ExternalCompositeEmergencyAuthorityWorkDisposition`:

`PREEXISTING_TERMINAL_NO_RESTART |
TERMINALIZED_BY_THIS_CAS_NO_RESTART |
RETAINED_IMMUTABLE_EVIDENCE_NO_ACTION |
COMPLETED_AMBIGUOUS_EFFECT_NO_RETRY |
ROLE_SPECIFIC_TERMINAL_OR_PERMANENT_ISOLATION`.

The set also binds the captured ADR-009 grant-ledger head/version,
next/optional-last sequence, finite-boundary-summary branch and open-marker
root. Each marker consumes its audience-bound protected specialized grant
receipt, passing verification and ledger ancestry, then maps bijectively to a
local work identity or no-install tombstone. A bare ledger commit proves only
ancestry. Each disposition binds exact predecessor/successor evidence and proves
no work remains executable, callback-capable or restartable. Ambiguous means
completed with no retry, never no-effect, delivery, success or safety. A live
delivery/effect/callback, omitted child or partial set blocks closure; retained
evidence has no action right.

The release selector (delivery) or admission selector (observer) CAS
installs/preserves mirror `FENCED_DENY`, applies the partition and installs
`EMERGENCY_FENCED_RECOVERY_REQUIRED`. A consecutive incident repeats this edge
at the newer epoch and proves no reopen.
`ExternalCompositeEmergencyAuthorityClosureReceipt` follows outer/subordinate
commits and binds both heads, set/disposition roots, incident/capture and
no-open-work result; installed heads exclude it.
`ExternalCompositeEmergencyAuthorityClosurePublicationManifest`, the exact
ADR-001 persistence-manifest specialization, binds its protected return envelope
and complete local bundle last. The return uses
`DURABLE_HISTORICAL_COMMIT / REGISTERED_SOURCE_AUTHORITY /
ACTIVE_OR_RETIREMENT_RETURN` with exact source/root/ancestry/operation/replay.
The source requires that manifest, membership and passing verification. It is
non-authorizing and incident-specific.

For an existing `TERMINAL` root,
`ExternalCompositeTerminalMarkerGrantClosureAssessment` binds its final head,
parent tombstone/receipt, captured ledger and protected grant receipts. Its
bijection is `LOCAL_LINEAGE_RETAINED_TERMINAL |
PERMANENT_LOCAL_TERMINAL_PROVES_NEVER_INSTALLED`, proved from the final
inventory/no-install map. It is a bounded deterministic receipt-free proof from
that committed head/map, protected final-retirement receipt and captured set;
it has no writer, selector mutation, receipt or envelope. Verification
recomputes the authenticated bijection. Unknown/ambiguous/missing history or a
nonterminal root requires qualified permanent isolation and grants no work.

Only `REBIND_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_AFTER_EMERGENCY` restores
authority. It consumes the immutable ADR-009
`ExternalSecurityRecoveryRebindAncestryCommitment`, incident/closure receipt,
latest `CURRENT` head/receipt, exact
`ProtectedExternalSecurityEnforcementRootCurrentManifestAuthorizationEnvelope`,
selected
`ExternalSecurityEnforcementRootCurrentManifestAuthorizationPublicationManifest`,
producer completion, delivery capsule, both scoped proofs and passing
verification. It separately consumes the exact durable
`ProtectedSecurityAuthorityCommitReceiptEnvelope /
PER_KEY_CURRENTNESS_ISSUANCE_COMMIT / ATTESTATION_ISSUANCE` and selected
`ExternalSecurityCurrentnessCommitPublicationManifest` family, the exact
ephemeral `ProtectedInstalledRealmSecurityCurrentnessAttestationEnvelope` and
selected `InstalledRealmSecurityCurrentnessAttestationPublicationManifest`
family, their shared currentness-producer completion, both delivery capsules,
both scoped proofs, passing verification, matching inner attestation and
qualified clock relation. Every coordinate, audience, ancestry digest and
current-authorization digest must match across the authorization and currentness
hierarchies. Authorization is the base
`EMERGENCY_RECOVERY_REAUTHORIZATION` or a
gap-free descendant `PLANNED_SUCCESSOR_REAUTHORIZATION`; changed incarnation,
gap, newer incident or retirement rejects. Its proof is
`INSTALLED_LOCAL_EMERGENCY_COMPLETE_CLOSURE |
SOURCE_CAPTURED_FINITE_HORIZON_ELAPSED`. The first takes
`EMERGENCY_FENCED_RECOVERY_REQUIRED -> OPEN_AUTHORITY | OPEN_ADMISSION`. The
second forbids `LOCAL_TERMINAL_EVIDENCE_REQUIRED` and takes
`OPEN_AUTHORITY | OPEN_ADMISSION` with `FENCED_DENY`, or
`EMERGENCY_FENCED_CLOSURE_PENDING`, to the matching open phase only when the
same CAS proves no live/restartable predecessor work. Rebind installs
`CURRENT_IMPORT`, retains tombstones/evidence, replenishes closure reserve and
starts new identities. The local predecessor proves nonterminal/nonisolated
eligibility; the disconnected source does not. Generic refresh,
terminal/isolation, retired source, stale/incomplete proof or bare attestation
cannot rebind.

The delivery outer head partitions all retained commitments, outbox identities,
drain lineages, dispositions, and tombstones by grant, with globally unique
output slots/attempts. G0 obligations cannot relabel to G1 or observer B.
Bounded retired-key eviction requires retention plus exact origin:
`TRANSPORT_DRAIN_PROVED` needs its quiescence receipt, while
`NEVER_INSTALLED_ZERO_WORK` needs its no-install receipt, zero roots, and source
aggregate. Eviction retains full key/item/attempt tombstones. Capacity denies
prepare or retires the boundary, never drops live, draining, or unproved entries.

Ordinary transitions mutate one key and preserve siblings. Shared
security/clock/retirement/descriptor cuts mutate one complete bounded affected
set in one outer CAS and preserve all others.
`TrustedDeliveryBoundaryBulkTerminalTransitionFact` binds that set and one
`TrustedDeliveryBoundaryTerminalTransitionFact` per key. Each entry binds its
subfact plus preallocated receipt/envelope identity; the complete fact binds one
opaque closure-manifest identity, exact output counts and reserve, and the
map/outer bind the fact. The winner stores one per-key
`TrustedDeliveryBoundaryTerminalInstallationReceipt` binding its subfact,
outer/map commits and prior/installed entry while excluding the later protected
return. That envelope binds the receipt. It qualifies as that key's
`TERMINAL_ACKED`. All protected returns then use the one batch bundle above.
Partial sets, reused subfacts, and envelope-only receipts reject.

Only `InstalledTrustedDeliveryReleaseSelector` selects the self- and
successor-excluding outer head. Every grant, revocation, security, descriptor,
clock, reservation, release, drain, and quiescence mutation uses it. Referenced
state is evidence until installed. Under the common DAG:

- `TrustedDeliveryReleaseStateCommitReceipt` binds prior/installed outer heads,
  exact selector identity/incarnation/version/digest, installation commitment,
  evaluations, and transition kind
- entry mutation also emits
  `TrustedDeliveryBoundaryGrantMapCommitReceipt`, binding prior/installed
  map/entry heads, that publication receipt, and sibling preservation.

No separate revocation, entry, or outbox selector exists.
`RELEASE_STATE_GENESIS_FROM_UNINITIALIZED` consumes parent allocation,
`ALLOCATED_NEVER_USED`, the exact
`ExternalCompositeStateEnrollmentImportedSecurityGenesisEvidence` defined
above, and typed never-used selector absence in one qualified local transaction.
`UNINITIALIZED` means only that
pre-CAS absence. It installs one realm, `PENDING_SOURCE_CONFIRMATION`,
authenticated `FENCED_DENY`, and empty grant/outbox/drain maps. Absence is not
`NO_BOUNDARY_GRANT`. The closed transition union is:

- `RELEASE_STATE_GENESIS_FROM_UNINITIALIZED`;
- `RETIRE_TRUSTED_DELIVERY_BOUNDARY_AUTHORITY`;
- `FINALIZE_TRUSTED_DELIVERY_BOUNDARY_RETIREMENT`;
- `PREPARE_BOUNDARY_GRANT`;
- `ACTIVATE_PREPARED_BOUNDARY_GRANT`;
- `TERMINATE_BOUNDARY_GRANT`;
- `INSTALL_BOUNDARY_GRANT_NO_INSTALL_TOMBSTONE`;
- `BULK_TERMINATE_BOUNDARY_GRANTS`;
- `INSTALL_TRUSTED_DELIVERY_SECURITY_MIRROR_UPDATE`;
- `FENCE_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_FOR_EMERGENCY`;
- `REBIND_EXTERNAL_SECURITY_ENFORCEMENT_ROOT_AFTER_EMERGENCY`;
- `RESERVE_TRUSTED_DELIVERY_RELEASE`;
- `CANCEL_TRUSTED_DELIVERY_RELEASE_RESERVATION`;
- `COMMIT_TRUSTED_DELIVERY_RELEASE`;
- `START_EXTERNAL_TRANSPORT_DRAIN`;
- `RESOLVE_EXTERNAL_TRANSPORT_DRAIN`;
- `MARK_BOUNDARY_GRANT_TRANSPORT_QUIESCENT`;
- `APPLY_BOUNDARY_CLOCK_RESTART`;
- `EVICT_FINALIZED_TRUSTED_DELIVERY_OUTBOX_RETENTION`; and
- `EVICT_QUIESCENT_BOUNDARY_GRANT_ENTRY`.

Genesis takes typed absence to `PENDING_SOURCE_CONFIRMATION`. The first qualified
CURRENT import takes it to `OPEN_AUTHORITY`. One-way
`RETIRE_TRUSTED_DELIVERY_BOUNDARY_AUTHORITY` takes
`PENDING_SOURCE_CONFIRMATION | OPEN_AUTHORITY |
EMERGENCY_FENCED_CLOSURE_PENDING | EMERGENCY_FENCED_RECOVERY_REQUIRED` to
`RETIRED_DRAIN_ONLY`. One outer CAS terminalizes every nonterminal grant,
cancels/tombstones every pending reservation and pre-release commitment, and
byte-preserves every committed release, outbox item, output slot, drain lineage,
disposition, and never-reuse tombstone. Its bulk fact and receipts bind both
phases and complete sets. Partial or omitted members and any committed-item
cancel, rewrite, or relabel reject.

Receipt-free `TrustedDeliveryBoundaryAuthorityRetirementFact` binds operation
inputs, prior outer/map heads and selector version, closed predecessor, boundary
identity/generation, current security/descriptor/clock context, and closed cause
`PARENT_AUTHORITY_RETIRED | BOUNDARY_INSTANCE_RETIRED |
CAPACITY_EXHAUSTED | SECURITY_STATE_UNRECOVERABLE |
DESCRIPTOR_DOMAIN_RETIRED | CLOCK_CONTINUITY_UNAVAILABLE |
LOCAL_OPERATOR_RETIREMENT`. It also binds:

- the complete affected-grant set and one
  `TrustedDeliveryBoundaryTerminalTransitionFact` per nonterminal key
- complete pending-reservation and pre-release cancellation-tombstone sets
- complete preserved released-item, output-slot, drain, disposition, retention,
  and never-reuse partitions.

It excludes successor, selector digest, commits, and receipts. Foreign/empty
causes and caller subsets reject. Each affected key receives
`TrustedDeliveryBoundaryTerminalInstallationReceipt`.
`TrustedDeliveryBoundaryAuthorityRetirementReceipt` binds the fact,
prior/installed outer/map heads, drain-only phase, new selector, generic/map
commits, complete keyed terminal receipts, cancellation tombstones, and
preserved roots. Missing per-key bijection rejects.

Drain-only forbids grant prepare/activation, reservation create/commit, release,
and output-slot allocation. It permits only retained-obligation closure:
never-prepared reservation tombstone, byte/identity-preserving eligible drain
start/resolve, quiescence, existing bounded retry-right closure, retention,
tombstone-preserving finalized-item or quiescent-entry eviction, and
finalization. Restrictive input can stop this work, never add retry, reopen, or
release.

`FINALIZE_TRUSTED_DELIVERY_BOUNDARY_RETIREMENT` takes drain-only to `TERMINAL`
only with no nonterminal/nonquiescent grant, terminal no-retry disposition for
each item/attempt, satisfied retention, and all permanent tombstones in the
candidate. Ambiguous sends remain retained. Authorized retry must be exhausted
or closed. Finalization allocates no grant, reservation, release, item, attempt,
or output slot. It requires closed
`TrustedDeliveryBoundaryRetirementSourceGrantCutEvidence`:
`SOURCE_RETIREMENT_PENDING_CAPTURED_HIGH_WATER |
QUALIFIED_PERMANENT_SOURCE_GRANT_ISOLATION`. The normal branch binds the exact
ADR-009
`ProtectedExternalSecurityEnforcementRootRetirementPendingEnvelope`, selected
`ExternalSecurityEnforcementRootRetirementPendingPublicationManifest`, producer
completion, delivery capsule, both scoped proofs, inner
`ExternalSecurityEnforcementRootRetirementPendingReceipt` and passing verification,
registered-root/ledger incarnation, maximum and captured
exclusive-next/optional-last sequence, open-marker root, and source coordinates.
It proves
`RETIREMENT_PENDING` blocks later append. Isolation instead covers source
issuance/ledger stores and selectors, signing, network release, recovery, and
every successor/restart path. Absence, timeout, local fence, and lost contact are
insufficient.

Receipt-free `TrustedDeliveryBoundaryRetirementFinalizationFact` binds operation,
exact prior drain-only outer/map/selector, complete grant/quiescence and
item/disposition/retry inventories, empty active-attempt proof, retention,
tombstones, source cut, and complete reserve-position partition.

- With captured high-water, each position through last sequence bijects to its
  terminal/quiescent lineage and consumed state. Remaining issued `AVAILABLE`
  becomes `CONSUMED_FINAL_RETIREMENT`. Positions above last become
  `RETIRED_NEVER_ISSUED`. Absent last means all positions are above it.
- With isolation, all remaining `AVAILABLE` becomes
  `CONSUMED_FINAL_RETIREMENT`, without a never-issued claim.

Both preserve consumed positions and bind prior/candidate
`TrustedDeliveryBoundaryNoInstallTombstoneReserveHead`. Dynamic sets are
canonical keyed key/digest evidence, never all-clear Booleans. The fact excludes
successors, selectors, commits, and receipts.
`TrustedDeliveryBoundaryRetirementFinalizationReceipt` binds it, exact
prior/installed outer/map heads, terminal phase, new selector,
`TrustedDeliveryReleaseStateCommitReceipt`, closure/tombstone roots and both
reserve roots. The empty/quiescent map is byte-preserved with no map commit;
missing, stale, partial, summarized, and post-eviction evidence reject.

Conformance races source append against retirement. Append-first raises
high-water, so local finalization accounts for the grant and reserve position.
Retirement-first makes append lose. Older high-water, another ledger
incarnation, or isolation with any reachable issuance/restart path rejects.

The same local transaction installs boundary `TERMINAL`, changes its exact parent
entry `INSTALLED -> PERMANENTLY_RETIRED`, and emits
`ExternalCompositeStateEnrollmentRegistryCommitReceipt` and
`ExternalCompositeStateEnrollmentFinalRetirementReceipt`. The parent manifest
binds both selectors, both publication receipts, and the boundary finalization
receipt last. Neither terminal half commits alone.


## Local namespace-closure import and prepared-intent resolution

The local composite head's
`ObserverGrantImportedSourceNamespaceClosureRegistry` is keyed by exact source
namespace, source-index incarnation, observer-root incarnation and verified
source-index enrollment digest. Its value is monotonic
`ObserverGrantImportedSourceNamespaceClosureTombstone`, whose closed
`ObserverGrantImportedSourceNamespaceClosureEvidenceState` is
`SOURCE_ONLY | ANCHOR_ONLY | SOURCE_AND_ANCHOR`. It retains separate optional
exact source-index and independent-anchor closure hierarchies, local enrollment
ancestry, every import commit and the latest complete operation partition. An
existing origin can only return the byte-identical retry. Importing the missing
origin changes `SOURCE_ONLY | ANCHOR_ONLY` to `SOURCE_AND_ANCHOR`; it never
replaces, weakens or deletes prior evidence. Conflicting roots, profiles,
enrollment ancestry or key-exact proofs reject the refinement. Manifest-fixed
capacity reserves one product tombstone and worst-case first-import plus
refinement partition work for every locally usable source enrollment;
operation-map saturation cannot consume that reserve.

Closed event `IMPORT_OBSERVER_GRANT_SOURCE_NAMESPACE_PERMANENT_CLOSURE` consumes
the root-audience source-index or anchor closure hierarchy and constructs
receipt-free `ObserverGrantSourceNamespaceClosureImportFact` over the current
sole observer-admission selector/head. Its
`ObserverGrantSourceNamespaceClosureOperationPartition` is a canonical
bijection over every retained operation for that source namespace. Each
`ObserverGrantSourceNamespaceClosureOperationPartitionEntry` has one closed
kind:
`RESOLVE_PREPARED_SOURCE_NO_CHALLENGE |
RESOLVE_PREPARED_ANCHOR_NONMEMBERSHIP |
RESOLVE_PREPARED_ANCHOR_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED |
PRESERVE_OPERATION_PHASE_PENDING_EXACT_TERMINAL_RESULT |
PRESERVE_RESOLVED_OR_INSTALLED_CLOSED_HISTORY`.
Each resolve branch carries its key-exact proof and installs the matching
operation resolution, verified outcome and stable-key tombstone in this same
CAS. The anchor branches exhaust membership and nonmembership for every
prepared key. The source branch resolves only a nonissued or
`CANCELED_BEFORE_ISSUANCE` key; an issued key stays in the exact-terminal-result
partition. That branch preserves the operation phase byte-for-byte and installs
only its monotonic `EXACT_TERMINAL_EVIDENCE_PENDING` partition marker. The
imported namespace tombstone blocks BEGIN, so a preserved `INTENT_PREPARED`
operation cannot send. A pending/ambiguous attempt, consumed slot or
not-yet-proved-closed grant also stays in that partition and continues to block
its target. Already resolved or proved-closed history is preserved
byte-for-byte. On a later missing-origin refinement, the complete partition is
recomputed under both retained hierarchies. Only operations marked pending can
gain a stronger exact resolution; every resolved/installed operation remains
byte-identical. In particular, anchor membership or nonmembership can resolve a
source-issued prepared intent without claiming source nonissuance. Omission,
duplication, cross-source entries, a summary count, origin downgrade or a
proof/outcome mismatch rejects the whole import.

`ObserverGrantSourceNamespaceClosureImportCandidate` binds the fact, prior head,
resulting tombstone and complete resulting operation projections. The one local
CAS installs them together. Its root edge is an authority-narrowing self-edge
from `ACTIVE`, `RETIRED_DRAIN_ONLY` or `TERMINAL` to that same phase and advances
the sole selector version. It grants no ordinary work in drain-only or terminal
state.
`ObserverGrantSourceNamespaceClosureImportReceipt` is post-CAS and binds the
fact, candidate, prior/installed heads and common transaction receipt. Closure
import and PREPARE therefore race on the same local selector: import-first makes
every later PREPARE for that exact namespace/enrollment lose; PREPARE-first
places the operation in the import partition. The tombstone also forbids BEGIN
for a previously prepared operation. Such an operation can only take its exact
resolution path. This local race, not a nonexistent cross-store CAS, prevents
post-closure stable-key exhaustion without blocking unrelated source
namespaces.

`PREPARE_OBSERVER_GRANT_REQUEST_INTENT` installs the exact receipt-free intent,
stable key and observer challenge in the local composite head before the first
challenge-issuance network send. Its winning local-selector transaction
recomputes the complete target-exclusivity proof, consumes the exact verified
`ProtectedObserverGrantSourceIssuanceObserverRootEnrollmentEnvelope`, selected
family, source-producer completion, capsule, both scoped proofs and passing
verification, and atomically installs the request operation. The enrollment
projection must name this source namespace, observer root/incarnation,
availability profile and source-index lineage. Under the anchor profile it also
consumes the matching verified anchor root-enrollment hierarchy and requires
the two bound anchor-entry digests to be byte-equal. Two distinct keys for the
same target cannot both PREPARE. It also read-compares typed absence of the
matching imported source-namespace closure tombstone; a caller cannot reuse an
old enrollment hierarchy after local closure import.
It grants no local or server authority. The target remains blocked while the
intent is prepared. If the caller abandons
before it receives a valid exported challenge, it sends the same intent/key to
`CANCEL_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE` and waits for the installed
`CANCELED_UNUSED` commit. The observer then constructs receipt-free
`ObserverGrantRequestIntentResolutionFact` over the prepared intent and exact
prior local composite head/selector, protected terminal-result envelope,
passing verification, unused-slot payload and freshness-registry/outer heads
and commits. Only
`RESOLVE_OBSERVER_GRANT_REQUEST_INTENT_WITHOUT_CHALLENGE` can consume that fact
and remove the prepared local intent. `EXPIRED_UNUSED` is also eligible only
through that envelope's exact terminal slot and commits.
If permanent source retirement or isolation makes such a slot result
unobtainable, the only alternative is receipt-free local
`ObserverGrantPreparedIntentPermanentResolutionEvidence`. Its closed origin is
`SOURCE_INDEX_FROZEN_NO_CHALLENGE |
INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_NONMEMBERSHIP_AFTER_SOURCE_TERMINAL_CLOSURE |
INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED_AFTER_SOURCE_TERMINAL_CLOSURE`.
The three branches are disjoint and cannot substitute artifacts.

`SOURCE_INDEX_FROZEN_NO_CHALLENGE` consumes the exact
`ProtectedObserverGrantSourceIssuanceNamespaceClosureEnvelope`, unwrapped
`ObserverGrantSourceIssuanceNamespaceClosureProjection`, selected
`ObserverGrantSourceIssuanceNamespaceClosurePublicationManifest`, producer
completion, delivery capsule, both scoped proofs and passing cross-store
verification. It also consumes exact
`ObserverGrantSourceIssuanceStableKeyNoChallengeProof`. Every artifact must match
the source namespace, lineage tombstones, stable key, observer-root audience,
suite/context, frozen root, fixed capacity class and closure-receipt digest.
`FROZEN_KEY_NONMEMBERSHIP` proves the key is absent.
`FROZEN_CANCELED_BEFORE_ISSUANCE_MEMBERSHIP` proves exact membership of the
canonical no-challenge entry and its local tombstone. This branch proves that no
challenge was or can later be issued for that stable key.

`INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_NONMEMBERSHIP_AFTER_SOURCE_TERMINAL_CLOSURE` is
legal only under the preinstalled anchor profile. It consumes the exact
`ProtectedObserverGrantChallengeExposureAnchorNamespaceClosureEnvelope`,
unwrapped
`ObserverGrantChallengeExposureAnchorNamespaceClosureProjection`, selected
`ObserverGrantChallengeExposureAnchorNamespaceClosurePublicationManifest`,
producer completion, delivery capsule, both scoped proofs and passing
verification under the enrolled independent-anchor trust, plus exact
`ObserverGrantChallengeExposureAnchorStableKeyNonmembershipProof`. The projection
and proof must match the profile, source namespace, anchor lineage, observer-root
audience, stable key, anchor context, frozen root, capacity class and permanent
acceptance-closure assessment. Its cause is exact cooperative source permanent
retirement or qualified permanent acceptance-authority isolation; one cause's
evidence cannot substitute for the other. This branch proves no anchor-qualified challenge
was exposed for the key and no source acceptance capability remains. It does not
claim that the source never created an unanchored challenge. The ordinary
observer relies on the anchor threshold's signed isolation attestation; only an
authorized audit opening reconstructs the complete retained surface-isolation
evidence. NCP does not turn that attestation into physical certification.

`INDEPENDENT_EXPOSURE_ANCHOR_FROZEN_MEMBERSHIP_ACCEPTANCE_PERMANENTLY_CLOSED_AFTER_SOURCE_TERMINAL_CLOSURE`
consumes the same closure hierarchy and exact
`ObserverGrantChallengeExposureAnchorStableKeyMembershipProof` plus the
canonical matching anchor entry. The entry and proof must match the stable key,
source-index commitment, observer root, paired-frame admission key, anchor root
and cause-specific permanent closure assessment. It proves only that the anchor append
committed and every source acceptance capability is now permanently closed. Its
closed truth is
`MAY_HAVE_BEEN_EXPOSED_BUT_ACCEPTANCE_PERMANENTLY_CLOSED`; it does not claim
that paired-frame admission, remote receipt or prior acceptance did or did not
occur. The cause-specific assessment proves that every acceptance path and
derived-authority branch that could formerly have won is terminal.

Each branch is legal only from `INTENT_PREPARED` with typed absence of every
server freshness challenge, server slot, request attempt and grant. The same
local CAS installs
`ObserverGrantPreparedIntentPermanentResolutionTombstone` under the stable key,
so every delayed challenge or response for that key rejects forever. It changes
the outcome to the branch-exact verified state and moves the operation to
`RESOLVED_WITHOUT_INSTALLATION`. ATTACH preserves `PENDING_FIRST_ATTACH`,
REATTACH preserves TERMINAL, and RENEW is legal only after exact G0 closure and
preserves TERMINAL. Temporary disconnection, timeout, open-index
nonmembership, an unsigned proof without the verified frozen closure hierarchy,
one retired generation with a live successor, `CHALLENGE_ISSUED`, `AVAILABLE`,
`CONSUMED_BY_ACCEPTED_REQUEST` or a present local attempt is insufficient. A
different intent, key, observer challenge, root, proof context or evidence
origin rejects.

## Current read authority and admitted historical capture

The installed, issuer-retained `ObserverReadCapability` is the current bounded
read authority. Each use validates its exact observer principal, verified
transport context, manifest entry, session, scope set, security and revocation
epochs, issuer snapshot, operations, and exclusive deadline. A capability ID,
copied seal, accepted grant, or prior decision cannot substitute for that
current check.

For one permitted operation, the boundary derives an exact
`CanonicalObserverReadScope` and
`ObserverBoundaryReadScopeMembership`. It then seals one
`SealedObserverReadAuthorizationDecision`. That decision is preflight evidence
only. Its authority effect is
`PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED`, so the decision cannot authorize a
later release by replay.

The shared local validator takes the expected observer principal as a trusted
input. It rejects a decision for a different principal, even when all other
fields and the synthetic seal are internally consistent. For a history query,
the request digest is derived from the complete validated canonical scope,
including its clock incarnation and bounded window. Security and revocation
epochs must be positive portable safe integers. The local HMAC helper accepts
one exact 32-byte immutable fixture key. This key constraint improves
deterministic test separation; it is not a wire-key profile or cryptographic
qualification. The bridge rejects non-scalar Unicode and integers outside the
portable safe range before it computes a canonical digest.

At release, the boundary rechecks the current capability or installed grant,
scope membership, source identity, session generation, security and revocation
state, deadline, recipient, transport context, and exact payload. The
release-time result is bound through the reservation, release receipt, immutable
outbox item, and delivery. A queued request loses if any required current value
changes before this cut.

Receiver admission performs its own current grant, descriptor, transport,
security, time, declaration, and replay checks. Only a successful receiver
admission can create `DeliveredAdmissionEvidenceCapsule`. The capsule binds the
exact producer frame, delivery, admission head and receipt, admission cut, and
retained payload bytes. Its authority effect is
`HISTORICAL_EVIDENCE_ONLY_NO_FUTURE_READ_AUTHORITY`.

A later security cut can leave an admitted capsule valid as immutable historical
evidence. The capsule cannot authorize a new read, release, callback, admission,
command, or lifecycle operation. A sealed decision or capsule is never treated
as proof of current security state.

`DeterministicExtractionContract` applies bounded decoding, one exact member
path, one source-value kind, one output encoding, and an optional frozen
transform to retained admitted bytes.
`DeterministicExtractionReceipt` binds the contract, capsule, payload digest and
length, extracted source bytes, canonical output bytes, transform, and replay
digest. Missing, substituted, over-limit, or differently transformed input
rejects.

The current B01 synthetic fixture produces seven capsules and seven extraction
receipts for `A[a0]`, `D[d_left,d_right]`, `L[l0]`, and `V[v0]`. This is local,
non-normative evidence only. It does not demonstrate a genuine native-1.0
Prisoma language channel. Prisoma eligibility and estimator execution therefore
remain blocked.

Live issuer cryptography, transport-principal binding, external revocation,
installed interoperability, Prisoma role qualification, and release gates
remain **NOT RUN**.

## Selector resource ownership

Each selector owns its declared currentness, primary-root, state-domain, and
subordinate-head resources. An event can `WRITE` or `RESERVE` only resources
owned by that event's selector. It can `CONDITIONAL_COMPARE` a foreign resource
without acquiring write authority.

The event's `common_case_mutates` set equals its `WRITE` and `RESERVE` effect set
exactly. An unresolved resource, alias, duplicate backing, cross-owner mutation,
missing mutation, or extra mutation rejects. Empty-state labels are not resource
identities.

A joint-selector transaction profile names every writing participant
bijectively. Each participant has a nonempty local write footprint and writes
only its own resources. The profile coordinates those local writes. It does not
make a cross-store edge, cross-repository update, or consumer migration one
atomic transaction.

The B01 resource projection binds definitions, effects, derived mutations,
profile references, and joint participants in one domain-separated commitment.
This is local structural closure. It is not semantic review, implementation
refinement, installed atomicity, external evidence, or release authorization.

## Illustrative user-level attach input

This pre-intent API input carries no current generation, descriptor, security
state, challenge or grant. Verified transport identity selects the requester;
the server resolves current context only after the durable
`ATTACH_LOGICAL_TARGET` intent.

```json
{"ncp_version":"1.0","kind":"attach_observer","session_id":"plant-alpha",
"requested_access":[{"operation":"subscribe","plane":"observation",
"route":"ncp/session/plant-alpha/observation","message_class":"ObservationFrame",
"channel":"pose_position","extension":"none"}],
"identity":{"principal_id":"prisoma-observer-a","entity_id":"prisoma-capture-a",
"role":"observer"},"operation_id":"2b8f8e42-6ad5-4d4e-8eb4-d0e814182fc1"}
```

## Invalid or hostile example

```json
{"ncp_version":"1.0","kind":"attach_observer","session_id":"plant-alpha",
"requested_access":[{"operation":"publish","plane":"action",
"route":"ncp/session/plant-alpha/command/motor","message_class":"CommandFrame",
"channel":"motor","extension":"none"}],
"identity":{"principal_id":"prisoma-observer-a","entity_id":"prisoma-capture-a",
"role":"observer"},"operation_id":"387383f5-da96-4c85-90db-f6dc85420385"}
```

`publish` is not observer-read authority and rejects without descriptor
disclosure. Hostile fixtures independently reject wildcard/ungranted/
unauthenticated reads, unknown operations, literal publish, cross-session or
cross-principal lifecycle calls, and pre-grant access.

## Actors and state transitions

`DETACHED -> ATTACHING -> ATTACHED -> RENEWING -> ATTACHED -> REVOKED/EXPIRED
-> DETACHED -> ATTACHING`; the last edge is fresh
`REATTACH_FROM_TERMINAL_GRANT`, never resurrection.

External-root commits are separately receipt-linked:
the exact source/local bootstrap, emergency, guarded-rebind and one-way
retirement products defined above; no cross-store arrow is one transaction.
Every final local terminal edge installs its parent tombstone. Restrictive cuts
reject queued unadmitted frames, and FORBIDDEN continuation cannot widen.

## Bounds and resource behavior

All dynamic content and arithmetic is bounded before semantic allocation.
Issuance state, not a prunable tail, enforces uniqueness; exhaustion retires
before evidence loss. End-to-end resource isolation needs live evidence.

## Threat and hazard analysis

Reads remain sensitive. Privacy, retention, least privilege, revocation and
shared-resource isolation remain deployment obligations. The independent anchor
proves only its own ordered append and the later permanent acceptance cut. It
does not contain a Byzantine or credential-compromised source that leaks bytes
outside the qualified delivery path, and it never converts anchor membership
into proof of delivery or acceptance.
