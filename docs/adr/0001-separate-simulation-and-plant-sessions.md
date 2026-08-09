# ADR-001 — Separate simulation-service and plant-control sessions

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
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

Neutral `AuthorityRealmKey` is the canonical tuple of server authority principal
and stable realm ID. One realm owns one `AuthorityTransactionDomainKey`, whose
canonical value is exactly that realm key. ADR-004
`ObserverAuthorityRealmKey` is an exact typed alias/projection; the optional
observer role does not define or own the server, plant or simulation authority
namespace.

The server's independently administered provisioning authority owns one bounded
`AuthorityRealmEnrollmentRegistryHead` through one
`InstalledAuthorityRealmEnrollmentRegistrySelector`. It is the higher-authority
anti-ABA root for `(server_authority_principal, stable_realm_id)` and is not
stored inside a realm that it enrolls. Its entries are
`RESERVED_FOR_EXACT_STORE | INSTALLED |
LOST_DOMAIN_ISOLATION_PREPARING | LOST_DOMAIN_ISOLATION_CUT_WAITING |
PERMANENTLY_RETIRED` and are never removed or reused.

`AUTHORITY_REALM_ENROLLMENT_REGISTRY_GENESIS_FROM_PROVISIONING_AUTHORITY` is its
sole bootstrap. Receipt-free
`AuthorityRealmEnrollmentRegistryGenesisFact` binds the configured provisioning-
authority principal, exact durable registry store/selector identity, finite map
bounds, `AuthorityRealmEnrollmentRegistryQualificationReceipt`, empty map, and
selector absence plus never-used proof; it excludes the
candidate and later receipt. The candidate binds that fact. Post-commit
`AuthorityRealmEnrollmentRegistryGenesisReceipt` binds the fact and exact
installed head/selector. Final non-authorizing
`AuthorityRealmEnrollmentRegistryGenesisPersistenceManifest` binds the exact
genesis receipt/sidecar bytes last; the store exposes no partial bootstrap. The root-of-trust configuration and store qualification
are deployment inputs, not caller data. After any use, a missing selector, second
genesis, replay or empty reset is corruption and blocks every new realm
enrollment.

`AuthorityRealmEnrollmentRegistryQualification` binds that independently
administered store/selector, provisioning authority, strict-serializable CAS and
crash recovery, trusted monotonic-clock lineage, bounded commit position and
hard entry/byte/work limits. Every post-genesis event constructs an
`AuthorityRealmEnrollmentRegistryCASCondition` over the exact expected root head/
version, operation identity, receipt-free fact, complete entry mutation and
reserve delta. Its candidate binds the fact and condition. The winning
`AuthorityRealmEnrollmentRegistryCommitReceipt` binds prior/installed heads,
selector version and checked-next commit position; every specialized reservation,
confirmation, cut or retirement receipt depends on it. A final non-authorizing
`AuthorityRealmEnrollmentRegistryPersistenceManifest` binds the complete durable
bundle last. Reply loss returns the retained exact operation/receipt; conflicting
reuse rejects.

ADR-001 and ADR-007 do not pass bare authority-bearing receipts between atomic
stores. Every such hop uses one
`ProtectedFacilityAuthorityCrossStoreReceiptEnvelope`, followed by one
receipt-free `FacilityAuthorityCrossStoreReceiptVerificationEvidence` at the
consumer. This bridge is limited to facility/realm enrollment, independent
facility-commit anchoring and restrictive closure. It does not carry an ADR-009
security-authority artifact and cannot
satisfy an ADR-009 currentness condition.

The envelope binds all of the following:

- one closed `FacilityAuthorityCrossStoreReceiptArtifactKind`, the exact
  canonical inner receipt or evidence bytes and digest, its producer event and
  operation ID, and the producer's prior/installed selector heads, store
  incarnation, commit position and generic commit receipt;
- the exact source authority principal, source role, facility or realm key,
  selector/store identity and unbroken genesis-to-installed history commitment;
- one exact audience: target authority principal, role, facility or realm key,
  selector/store incarnation, consuming event, logical object key and replay
  scope;
- the signer principal, certificate/key identifier, signature suite, dedicated
  ADR-009 `SECURITY_COMMIT_RECEIPT_AUTHENTICATION` key use, complete signing-key
  history, the exact event authorization current at the source commit, and the
  exact signer authorization current at export; management, currentness and
  enforcement keys cannot substitute;
- closed `FacilityAuthorityCrossStoreReceiptReplayMode`
  `EXACTLY_ONCE | BOUNDED_ENROLLMENT_REUSE`, with a
  never-reused consumption key for the first branch or an exact enrollment key,
  hard use counters and current producer-side enrollment state for the second;
  and
- the expected verified `production-secure` transport principal at delivery.
  `dev-loopback-insecure`, a caller identity field or certificate subject text
  cannot satisfy this binding.

After the inner source commit and its transaction/evidence persistence manifest,
the source writes the envelope and then writes
`FacilityAuthorityCrossStoreExportPersistenceManifest` last. That manifest binds
the complete inner-receipt, envelope, signer-history and source-lineage bundle.
The source exposes none of the bundle before the manifest is durable. The target
verification evidence binds that exact manifest, successful canonical digest and
signature checks, exact key-use and manifest-history validation, source-history
anti-rollback validation, audience equality, verified transport-principal
equality, replay-mode validation, and the target consumption-index
nonmembership or installed bounded-enrollment counter. It excludes the target
candidate, installed head and receipt. The target fact contains the verification
evidence and inner digest, never an independently supplied inner receipt. Its
winning CAS permanently records the consumption key or checked-next bounded use.
The canonical record is
`FacilityAuthorityCrossStoreReceiptConsumptionIndex`.
Reply loss returns that installed result. An unmanifested envelope, a valid
signature for another audience/event, a historical enrollment after drain, a
second inner representation, or a bare inner receipt grants nothing.

The closed artifact-kind surface for the ADR-001/ADR-007 independent-store bridge
is:

`HIGHER_REALM_TO_TARGET_DOMAIN_ENROLLMENT_RESERVATION |
TARGET_DOMAIN_TO_HIGHER_REALM_GENESIS_CANCELLATION |
TARGET_DOMAIN_TO_HIGHER_REALM_GENESIS |
HIGHER_REALM_TO_TARGET_DOMAIN_ENROLLMENT_CONFIRMATION |
TARGET_DOMAIN_TO_HIGHER_REALM_RETIREMENT |
FACILITY_HIGHER_REGISTRY_ENROLLMENT_RESERVATION |
HIGHER_FACILITY_RESERVE_INSTALLATION |
FACILITY_HIGHER_REGISTRY_ENROLLMENT_CONFIRMATION |
FACILITY_HIGHER_REGISTRY_ENROLLMENT_CANCELLATION |
FACILITY_HIGHER_REGISTRY_DRAIN_REQUEST |
HIGHER_FACILITY_REGISTRY_DRAIN_ACKNOWLEDGMENT |
HIGHER_FACILITY_REGISTRY_RETIREMENT |
FACILITY_REALM_PENDING_INTENT_ENVELOPE |
HIGHER_REALM_PENDING_INTENT_RESERVATION |
HIGHER_REALM_PENDING_INTENT_CANCELLATION |
FACILITY_CAPACITY_RESERVATION |
FACILITY_CAPACITY_RELEASE |
HIGHER_RESERVATION_AUTHORIZATION |
FACILITY_AUTHORIZATION_CONSUMPTION |
FACILITY_UNUSED_AUTHORIZATION |
FACILITY_AUTHORIZATION_CLOSURE |
HIGHER_LOST_REALM_ISOLATION_PREPARATION |
FACILITY_LOST_REALM_FULL_SET_FENCE |
FACILITY_TERMINAL_CAPACITY_CLOSURE |
FACILITY_TERMINAL_AUTHORIZATION_NONMEMBERSHIP |
FACILITY_TERMINAL_REALM_PARTITION |
INDEPENDENT_LOST_FACILITY_COMPONENT_ISOLATION |
FACILITY_COMMIT_TO_INDEPENDENT_LINEAGE_ANCHOR |
INDEPENDENT_LINEAGE_ANCHOR_APPEND_TO_FACILITY_COMMIT_CONSUMER |
INDEPENDENT_LINEAGE_ANCHOR_FINAL_TO_LOST_FACILITY_ISOLATION |
HIGHER_PRIOR_REALM_PERMANENT_RETIREMENT |
FACILITY_TO_LOCAL_ENROLLMENT_RESERVATION |
LOCAL_TO_FACILITY_GENESIS_OR_RETIREMENT_CLOSURE |
FACILITY_TO_LOCAL_ENROLLMENT_CONFIRMATION |
LOCAL_TO_FACILITY_FINALIZATION_CLOSURE`.

The first five kinds are not facility/higher-registry kinds. Their closed
concrete discriminants, directions and audiences are exactly:

- `AuthorityRealmEnrollmentReservationReceipt` plus its inseparable one-use
  marker: higher enrollment-registry store to the reservation-bound target
  domain store. The source emits two audience-specific envelopes, one for
  `AUTHORITY_TRANSACTION_DOMAIN_GENESIS_FROM_ENROLLMENT` and one for
  `CANCEL_AUTHORITY_TRANSACTION_DOMAIN_GENESIS_BEFORE_CREATION`. Both name the
  same target bootstrap selector/store incarnation and the same
  `EXACTLY_ONCE` consumption key, so only one event can consume the marker.
- `AuthorityTransactionDomainGenesisCancellationReceipt`: the installed target
  domain bootstrap lineage to the exact higher enrollment-registry event
  `CANCEL_RESERVED_AUTHORITY_REALM_ENROLLMENT_BEFORE_DOMAIN_GENESIS`.
- `AuthorityTransactionDomainGenesisReceipt`: the installed target domain
  lineage to `CONFIRM_AUTHORITY_REALM_ENROLLMENT` at that exact higher registry.
- `AuthorityRealmEnrollmentConfirmationReceipt`: that higher registry to
  `ACTIVATE_AUTHORITY_TRANSACTION_DOMAIN_AFTER_REALM_CONFIRMATION` at the exact
  target domain selector/store incarnation.
- `AuthorityTransactionDomainRetirementReceipt`: that target domain lineage to
  `PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT` at the exact higher registry.

All five use `EXACTLY_ONCE`, a never-reused logical-object consumption key and
the generic history, audience, signer, ADR-009
`SECURITY_COMMIT_RECEIPT_AUTHENTICATION` key-use, verified-transport and target
CAS checks above. Their concrete discriminants cannot be substituted for one
another or for a facility/higher discriminant. A producer commits its generic
receipt, then its dependent specialized receipt, then the complete source
persistence manifest. A domain-bootstrap producer additionally commits its
outcome-specific final persistence manifest after the common transaction
manifest. Only then can the producer
commit the audience-specific protected envelope and, last, the cross-store
export manifest. The envelope binds all artifacts plus complete source and
signing-key histories. The consumer verifies that crash-complete chain before
its fact can enter a CAS. A specialized receipt without every required source
manifest, an envelope exported before the last such manifest, a marker recorded
under different keys for genesis and cancellation, or an envelope for the other
audience rejects.

Each aggregate kind has a second closed
`FacilityAuthorityCrossStoreConcreteReceiptKind` allocated from the exact
producer receipts named by these ADRs. A schema-closure check
rejects an ADR-001/ADR-007 consumer edge whose atomic store differs from its
producer store unless that exact concrete discriminant is present in this union.
It also rejects use of the envelope for an in-store subordinate edge, an
ADR-009 artifact, or a non-authorizing informational message.

Before it admits an entry, the higher root reserves an exact
`AuthorityRealmEnrollmentRegistryRetirementBudget` for target-store ambiguity,
full-envelope cut, maximum-survival waiting record and permanent tombstone. New
enrollment stops before finite entry, byte or commit-position capacity can consume
that reserve. Checked counter/deadline overflow never wraps. Ordinary enrollment
cannot consume closure units, and loss of this higher selector never permits a
replacement root to reuse any old realm key.

Receipt-free `AuthorityRealmEnrollmentReservationFact` binds exact typed
nonmembership, the authenticated provisioning-authority request, proposed realm ID,
target selector/store and the fields below while excluding its candidate and
receipt. `RESERVE_AUTHORITY_REALM_ENROLLMENT` consumes that fact, permanently
burns the fresh realm ID, and binds one exact
cryptographically authenticated transaction-manager/store identity, never-used
store incarnation, qualification digest, one-use genesis marker and immutable
`AuthorityRealmIsolationEnvelope`. The envelope conservatively upper-bounds
every credential namespace, listener/endpoint/route, remote release horizon,
physical jurisdiction/footprint and participant class the realm can ever admit.
Domain qualification and every participant/jurisdiction admission prove exact
containment in it. Adding an identity or physical path outside the envelope
requires a new realm. A failed or lost bootstrap cannot redirect that
reservation to another store. Post-CAS
`AuthorityRealmEnrollmentReservationReceipt` binds the fact, exact prior and
installed higher-root heads, installed reservation entry and one-use marker.
Only its protected export with that marker can cross into the target store.

Before any domain genesis, exact target-store event
`CANCEL_AUTHORITY_TRANSACTION_DOMAIN_GENESIS_BEFORE_CREATION` can consume only
the protected and verified reservation envelope and its one-use marker. It is
one of the two closed target-bootstrap outcomes defined below. It atomically
installs the reserved domain selector with an
`AuthorityTransactionDomainGenesisCanceledTombstone` and terminal
`GENESIS_CANCELED_BEFORE_CREATION` head. Its
`AuthorityTransactionDomainGenesisCancellationReceipt` depends on the generic
target-store commit receipt and binds the reservation verification, exact
store/selector, typed absence plus never-used proof and installed tombstone. A
final `AuthorityTransactionDomainGenesisCancellationPersistenceManifest` makes
that branch exportable. Genesis and cancellation compare the same target-store
selector and consume the same marker; a delayed loser cannot commit.
Higher-root
`CANCEL_RESERVED_AUTHORITY_REALM_ENROLLMENT_BEFORE_DOMAIN_GENESIS` consumes only
the protected cancellation receipt and changes
`RESERVED_FOR_EXACT_STORE -> PERMANENTLY_RETIRED` with
`EXACT_DOMAIN_GENESIS_CANCELLATION_RECEIPT`. A caller claim, bare receipt or
remote absence read cannot cancel the reservation.

`CONFIRM_AUTHORITY_REALM_ENROLLMENT` consumes the protected exact
domain-genesis receipt and changes only that reservation to `INSTALLED`. Its
`AuthorityRealmEnrollmentConfirmationReceipt` binds the reservation, exact
domain-genesis lineage and prior/installed higher-root heads.
`PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT` consumes the protected exact
final domain-retirement receipt and installs its permanent tombstone. The normal
retirement fact also binds a complete authorization-map partition in which every entry is
`CANCELED_BEFORE_AUTHORIZATION | CANCELED_UNUSED |
FACILITY_RESERVATION_CLOSED`; a pending cancellation, issued authorization or
consumed facility authorization remains a closure obligation.
`PENDING_FACILITY_CAPACITY` also remains a closure obligation until its
AUTHORIZE-or-CANCEL outcome is terminal. It accepts
`RESERVED_FOR_EXACT_STORE` only for the exact unconfirmed-empty-domain
cancellation branch, and accepts that same branch from `INSTALLED` when higher-
root confirmation committed before local cancellation. Every confirmed-drain
branch requires `INSTALLED`. From `RESERVED_FOR_EXACT_STORE`, confirmation and
unconfirmed-domain retirement compare the same higher selector, so exactly one
wins; if confirmation wins, the same retirement receipt remains consumable from
`INSTALLED`. A late confirmation can never revive a retired entry.
The permanent tombstone retains the complete authorization map and authenticated
membership/nonmembership proof material for later queries. Nonmembership cannot
close facility capacity because every valid facility reserve has a prior higher
intent entry. A root digest or remote absence read is insufficient.
A second selector,
unlogged certificate, reused marker, different store identity or reconstructed
empty registry rejects. Loss or corruption of this higher-authority registry
blocks new realm enrollment; it does not permit local genesis. Its finite
capacity, durability, key custody and independent recovery are provider
qualification gates and are **NOT RUN** for this candidate.

An installed realm entry also owns one bounded canonical physical-jurisdiction
authorization map. Its closed entry state is
`PENDING_FACILITY_CAPACITY |
PREAUTHORIZATION_CANCELLATION_PENDING_FACILITY_RELEASE |
ISSUED_PENDING_FACILITY | CONSUMED_BY_FACILITY_RESERVATION |
CANCELED_BEFORE_AUTHORIZATION | CANCELED_UNUSED |
FACILITY_RESERVATION_CLOSED | FACILITY_REALM_FENCED`. Entries are never removed
or reused.

The facility first admits the higher registry lineage and reserves the reciprocal
abort path. The facility head owns one
`PhysicalActuationFacilityHigherRegistryEnrollmentHead`, written only by the
sole facility selector and keyed by the exact tuple of higher provisioning
principal, higher registry selector/store incarnation, higher genesis/history
digest and facility key. Its states are
`RESERVE_PREPARED | CONFIRMED_ACTIVE | DRAIN_ONLY |
PERMANENTLY_RETIRED`; entries are never removed, redirected or reused.
Terminal state binds closed
`PhysicalActuationFacilityHigherRegistryEnrollmentTerminalCause`
`UNCONFIRMED_CANCELED | CONFIRMED_DRAIN_RETIRED`.
`PREPARE_PHYSICAL_ACTUATION_FACILITY_HIGHER_REGISTRY_ENROLLMENT` is its sole
insertion. It proves typed key nonmembership, independently verifies the higher
registry qualification and current manifest authority, reserves one unique
pending-intent cap and all abort/fence/retained-tombstone costs, and emits a
protected `PhysicalActuationFacilityHigherRegistryEnrollmentReservationReceipt`.
No higher root or caller can write this entry or choose its reserve.

The higher registry head owns the reciprocal
`AuthorityRealmFacilityPendingIntentReserveBindingMap`, written only by the
higher selector and keyed by that same tuple.
`INSTALL_AUTHORITY_REALM_REGISTRY_FACILITY_PENDING_INTENT_RESERVE` consumes the
protected reservation verification, proves map nonmembership, installs
`FACILITY_RESERVE_INSTALLED`, the exact cap/cost vector and facility lineage, and
emits protected
`AuthorityRealmFacilityPendingIntentReserveInstallationReceipt`.
Its permanent successor retains the matching facility terminal cause.
`CONFIRM_PHYSICAL_ACTUATION_FACILITY_HIGHER_REGISTRY_ENROLLMENT` consumes that
protected receipt and alone changes the facility entry
`RESERVE_PREPARED -> CONFIRMED_ACTIVE`; its protected
`PhysicalActuationFacilityHigherRegistryEnrollmentConfirmationReceipt` is the
bounded-reuse artifact required by every higher pending-intent insertion. The
higher intent CAS compares its own installed reciprocal entry and checked
per-registry and per-realm counters. Thus neither half can self-authorize, two
receipts cannot reserve the same lineage, and a copied reserve cannot be charged
to another facility or higher selector.

Before facility CONFIRM, exact
`CANCEL_PREPARED_PHYSICAL_ACTUATION_FACILITY_HIGHER_REGISTRY_ENROLLMENT` races it
on the facility selector. If cancellation wins, it changes only
`RESERVE_PREPARED -> PERMANENTLY_RETIRED`, retains the key/reserve tombstone and
emits a protected
`PhysicalActuationFacilityHigherRegistryEnrollmentCancellationReceipt`.
Confirmation can no longer exist, so no higher pending-intent CAS can pass.
Higher exact
`CANCEL_AUTHORITY_REALM_REGISTRY_FACILITY_PENDING_INTENT_RESERVE_BEFORE_CONFIRMATION`
consumes that protected cancellation. From closed prior branch
`NO_RECIPROCAL_BINDING | FACILITY_RESERVE_INSTALLED`, it installs the permanent
binding tombstone or changes the installed binding to
`PERMANENTLY_RETIRED`. Higher INSTALL and cancellation compare the same map key:
whichever wins first, delayed INSTALL cannot revive it. The higher cancellation
receipt claims no facility commit and needs no reply before the facility can
release the unconfirmed reserve floor.

Each confirmed higher-registry entry has a bounded per-realm
`PhysicalActuationFacilityHigherRealmPendingIntentEnvelope` map. Only
`ADMIT_PHYSICAL_ACTUATION_FACILITY_HIGHER_REALM_PENDING_INTENT_ENVELOPE` can add
an `ADMITTED_OPEN` entry; its other states are `DRAIN_ONLY |
PERMANENTLY_RETIRED`. It binds the exact realm key and immutable isolation envelope, a hard
pending count, per-member maximum cost, explicit-empty-root cost and the
prospective local retained-inventory bound. Its facility CAS reserves the
complete composed fence cost defined by ADR-007 and emits the protected
envelope. Exact
`INSTALL_AUTHORITY_REALM_FACILITY_PENDING_INTENT_ENVELOPE` records that envelope
as `INSTALLED_OPEN` in the matching installed higher realm before the first
pending intent; the reciprocal higher states are `INSTALLED_OPEN | FROZEN |
PERMANENTLY_RETIRED`. Every
pending-intent CAS compares that record, consumes one checked count, and binds
the protected facility enrollment confirmation. A new realm-envelope entry,
larger cap, changed facility/slot/footprint envelope, or reuse after either side
enters drain requires a new never-used key and fresh admission; it cannot widen
an installed entry. Higher lost-domain PREPARE atomically changes the matching
entry `INSTALLED_OPEN -> FROZEN` with the authorization-map freeze. Normal
realm retirement requires its zero-unresolved partition and changes it to
`PERMANENTLY_RETIRED`. The corresponding facility drain/retirement edges preserve
the same key and consume those protected higher results; neither side can reopen
the entry.

Drain is a two-root close, not an expiration. Facility
`BEGIN_PHYSICAL_ACTUATION_FACILITY_HIGHER_REGISTRY_ENROLLMENT_DRAIN` changes only
`CONFIRMED_ACTIVE -> DRAIN_ONLY`, freezes the complete per-realm envelope set,
changes each `ADMITTED_OPEN -> DRAIN_ONLY`, and emits a protected drain request. Higher
`BEGIN_AUTHORITY_REALM_REGISTRY_FACILITY_PENDING_INTENT_RESERVE_DRAIN` consumes
it, changes only `FACILITY_RESERVE_INSTALLED -> DRAIN_ONLY`, and emits the
protected acknowledgment after the same higher CAS changes every reciprocal
`INSTALLED_OPEN -> FROZEN` and has disabled every insertion. Restrictive
terminalization remains legal.
`PERMANENTLY_RETIRE_AUTHORITY_REALM_REGISTRY_FACILITY_PENDING_INTENT_RESERVE`
alone changes that higher entry `DRAIN_ONLY -> PERMANENTLY_RETIRED` after an
exact zero-unresolved partition and permanent per-realm envelope tombstones; it
emits the protected higher retirement receipt. Facility retirement can
use exact
`PERMANENTLY_RETIRE_PHYSICAL_ACTUATION_FACILITY_HIGHER_REGISTRY_ENROLLMENT` to
retire the admitted lineage and release only its non-retained reserve
after protected verification of that receipt and terminal local
capacity/authorization inventory; that facility CAS changes every `DRAIN_ONLY`
subentry to `PERMANENTLY_RETIRED`. If either root is lost, the reserve is not
reused; the applicable full physical-isolation and fresh-facility-key path is
required.

The higher root reserves each authorization identity before the facility can
charge capacity. Receipt-free
`AuthorityRealmPhysicalJurisdictionAuthorizationIntentReservationFact` binds
typed map nonmembership, the authenticated provisioning request, the exact
facility, slot, footprint/conflict component, target local domain/store,
immutable isolation envelope, and one permanently reserved higher-root
`AuthorityRealmPhysicalJurisdictionFacilityCapacityIntentReserve` with closed
purpose `AUTHORIZE_OR_CANCEL`. It also binds ADR-007
protected abort-reserve enrollment confirmation and per-realm pending-intent
envelope verification for this higher registry, and a checked pending count
within both caps. The authorization
identity is globally unique
within the realm map before any facility marker exists. Exact
`PREPARE_AUTHORITY_REALM_PHYSICAL_JURISDICTION_FACILITY_CAPACITY_INTENT` installs
only `PENDING_FACILITY_CAPACITY`, only from an `INSTALLED` realm entry before
isolation preparation, and emits
`AuthorityRealmPhysicalJurisdictionAuthorizationIntentReservationReceipt`.
This state grants no facility, slot, epoch, hardware, or physical authority.

ADR-007 facility event
`RESERVE_PHYSICAL_ACTUATION_FACILITY_AUTHORIZATION_CAPACITY` must first issue one
exact `PhysicalActuationFacilityAuthorizationCapacityReservationReceipt`. The
receipt binds a never-reused capacity-reservation key, intended authorization
identity, realm, facility, slot, footprint/conflict component and target local
domain/store. Its fact consumes protected verification of the exact higher-root
intent-reservation receipt. It
also binds the checked facility charge that already covers the
larger of the consumed and unused terminal records, the member's full
realm-isolation partition bytes/work, and the transaction-space contribution
needed to fence the complete resulting facility-realm entry. A receipt whose
addition would exceed a facility-global limit or a per-realm full-fence
transaction limit does not exist.

The facility marker and receipt do not expire unilaterally. Reply loss queries
the exact facility operation and returns the same marker; a conflicting retry
rejects. Higher unavailability leaves capacity charged until exact cancellation,
unused/consumed closure, higher-realm retirement, lost-realm isolation or
facility retirement.

Exact
`ABORT_AUTHORITY_REALM_PHYSICAL_JURISDICTION_FACILITY_CAPACITY_INTENT` accepts only
`PENDING_FACILITY_CAPACITY`. It changes that entry to
`PREAUTHORIZATION_CANCELLATION_PENDING_FACILITY_RELEASE` and emits
`AuthorityRealmPhysicalJurisdictionCapacityReservationCancellationReceipt`.
Reservation authorization and intent cancellation compare the same higher
selector and map entry. The ADR-007 release event consumes this cancellation
receipt only through its protected verification. If no facility capacity entry exists, it installs a permanent
authorization-intent abort tombstone before it returns its release receipt. If
the matching held entry exists, it closes that entry. A delayed facility reserve
then loses to the tombstone or creates the exact held entry that the same
idempotent release operation closes. No cross-store commit order can leave an
authorization-capable orphan.

`AUTHORIZE_AUTHORITY_REALM_PHYSICAL_JURISDICTION_RESERVATION` consumes protected
verification of that exact one-use capacity receipt and the matching local
intent-reservation receipt. It can
change only `PENDING_FACILITY_CAPACITY` to
`ISSUED_PENDING_FACILITY`, and only while the realm entry is `INSTALLED`. Its
receipt-free fact binds the capacity reservation and the same
never-reused authorization identity, exact ADR-007 facility key, slot,
footprint/conflict component, target local domain/store and containment in the
immutable realm isolation envelope. It also binds the authenticated facility
qualification/head evidence used for admission. That external evidence is not a
cross-store compare. A historical capacity receipt can therefore create no
facility authority after facility drain or retirement; at most it creates a
higher entry that must close against the retained terminal facility inventory.
The higher receipt grants no physical or local reservation authority by itself.
Post-CAS
`AuthorityRealmPhysicalJurisdictionReservationAuthorizationReceipt` binds the
fact, capacity-reservation key and installed higher-root head.

ADR-007 event
`RELEASE_PHYSICAL_ACTUATION_FACILITY_AUTHORIZATION_CAPACITY_AFTER_HIGHER_CANCELLATION`
consumes protected verification of that cancellation receipt and emits
`PhysicalActuationFacilityAuthorizationCapacityReleaseReceipt`. Exact
`CONFIRM_AUTHORITY_REALM_PHYSICAL_JURISDICTION_CAPACITY_RELEASE` consumes
protected verification whose inner artifact selects closed
`AuthorityRealmPhysicalJurisdictionCapacityReservationReleaseEvidence`:
`EXACT_FACILITY_CAPACITY_RELEASE_RECEIPT |
TERMINAL_FACILITY_CAPACITY_RESERVATION_CLOSURE`. It changes only the matching pending
entry to `CANCELED_BEFORE_AUTHORIZATION`. The terminal branch binds the exact
ADR-007
`PhysicalActuationFacilityTerminalCapacityReservationClosureEvidence` over the
never-reopening facility root and its exact retained abort tombstone, closed
capacity entry, or terminal intended-identity nonmembership branch. The
nonmembership branch structurally forbids a capacity key and is legal only
because the facility root cannot reopen. A remote absence read cannot release
capacity or finish the higher cancellation.
After higher lost-domain preparation freezes membership, no authorization or
preauthorization-cancellation insertion is legal.
`CONFIRM_AUTHORITY_REALM_PHYSICAL_JURISDICTION_CAPACITY_RELEASE`,
`CONFIRM_AUTHORITY_REALM_PHYSICAL_JURISDICTION_RESERVATION_CONSUMPTION` and
`CLOSE_AUTHORITY_REALM_PHYSICAL_JURISDICTION_RESERVATION_AUTHORIZATION` remain
legal only as receipt-bound restrictive successors of entries in that frozen
set. They cannot add an identity or change the frozen facility partition.

ADR-007 facility reservation PREPARE must consume protected verification of this
exact receipt and its embedded protected capacity-reservation verification,
atomically change the matching facility
capacity entry from held to consumed, record the authorization identity in the
facility root and emit
`PhysicalActuationFacilityReservationAuthorizationConsumptionReceipt`.
`CONFIRM_AUTHORITY_REALM_PHYSICAL_JURISDICTION_RESERVATION_CONSUMPTION` consumes
protected verification of that exact receipt and changes the matching higher entry from
`ISSUED_PENDING_FACILITY` to `CONSUMED_BY_FACILITY_RESERVATION`.
Same-operation retry returns the installed state. A receipt for another facility,
slot, realm or authorization identity rejects.

Exact
`CLOSE_AUTHORITY_REALM_PHYSICAL_JURISDICTION_RESERVATION_AUTHORIZATION` consumes
one closed
`AuthorityRealmPhysicalJurisdictionReservationAuthorizationClosureEvidence`:
`FACILITY_UNUSED_AUTHORIZATION_TOMBSTONE |
FACILITY_RESERVATION_CLOSED_NORMALLY |
TERMINAL_FACILITY_NONMEMBERSHIP`. The first branch changes an issued entry to
`CANCELED_UNUSED` and consumes protected verification of ADR-007
`PhysicalActuationFacilityUnusedReservationAuthorizationReceipt`. The second
consumes protected verification of
`PhysicalActuationFacilityReservationAuthorizationClosureReceipt` and changes a
consumed entry to `FACILITY_RESERVATION_CLOSED`; if facility consumption and
closure both committed before higher confirmation, it can make that same
terminal transition directly from `ISSUED_PENDING_FACILITY`. The last branch is
legal only from a terminal, never-reopening facility root whose complete
retained capacity-reservation, authorization and slot inventory proves that this
exact authorization was never consumed; it also installs `CANCELED_UNUSED`.
Every branch binds the exact facility selector ancestry, capacity-reservation key
and permanent authorization tombstone or terminal nonmembership proof. A remote
absence read, local retirement claim, facility slot label or historical higher
head cannot substitute.

External isolation uses a close-before-cut handshake. Exact
`BEGIN_AUTHORITY_REALM_EXTERNAL_ISOLATION_AFTER_DOMAIN_STATE_LOSS` changes
`RESERVED_FOR_EXACT_STORE | INSTALLED` to
`LOST_DOMAIN_ISOLATION_PREPARING`, binds the exact unrecoverable-state cause and
last-authenticated-domain evidence defined below, freezes authorization-map
membership and issues the complete facility-key/authorization partition. The
frozen partition preserves already `CANCELED_BEFORE_AUTHORIZATION |
CANCELED_UNUSED | FACILITY_RESERVATION_CLOSED` entries and requires every
pending preauthorization cancellation to reach its exact terminal release
branch. Each `PENDING_FACILITY_CAPACITY` entry must reach the same exact
no-entry-or-held facility closure. It classifies each issued or consumed entry
by exact facility,
authorization identity and capacity-reservation key.

For every named facility, closed
`AuthorityRealmFacilityIsolationClosureEvidence` is
`EXACT_LOST_REALM_FULL_SET_FENCE_RECEIPT |
TERMINAL_FACILITY_FULL_SET_PARTITION_EVIDENCE |
LOST_FACILITY_STATE_COMPLETE_COMPONENT_ISOLATION`. The first branch consumes
protected verification of the preparation receipt at the active facility
selector. ADR-007 races all later
reservation PREPARE operations there, freezes the complete local capacity and
consumed set, permanently fences the realm, and returns one
`PhysicalActuationFacilityRealmIsolationFenceReceipt`. A PREPARE that committed
first appears in that receipt's complete consumed-authorization/slot partition
and reaches physical isolation or hardware retirement. A facility fence that
committed first makes the PREPARE lose. Every facility identity index entry has
one matching frozen higher-map entry. Omission or identity mismatch rejects.

The second branch is legal only after the facility root is permanently retired.
`PhysicalActuationFacilityTerminalRealmAuthorizationPartitionEvidence` binds the
exact frozen higher set to that terminal root's complete retained capacity,
authorization, realm and slot inventory. A facility-retirement-origin local-set
fence receipt alone cannot satisfy this branch.

The third branch consumes ADR-007
protected verification for
`LostPhysicalActuationFacilityStateCompleteComponentIsolationEvidence`. It is
legal only when the facility selector/store is lost or ambiguous and cannot
produce either other branch. Its exact-root branch requires independently
authenticated final facility high-water and no-successor evidence; otherwise it
must use the explicit unknown-root branch seeded by the complete immutable
inventory `U`. It binds the full possible inventory, exact frozen higher set,
and a pairwise-disjoint canonical least-fixed-point component partition whose
union is exactly `U`, with one complement proof per component,
independently qualified physical isolation, permanent retirement of every
possible old facility/hardware identity and credential, and a no-resume barrier.
It claims no facility CAS, terminal facility root, or local realm semantic
retirement. A stale root without the full immutable envelope cannot satisfy it.

Receipt-free
`AuthorityRealmFacilityIsolationAuthorizationProjectionFact` binds the frozen
authorization map, one exact closure-evidence branch for every facility in the
realm envelope, and a total per-entry projection. Its closed classification is
`PRESERVE_TERMINAL |
NOT_CONSUMED_BY_FACILITY |
CONSUMED_OR_POSSIBLY_CONSUMED_COMPONENT_FENCED`. The first classification
preserves an already terminal entry byte-for-byte. The second requires exact
capacity abort/release, unused evidence, terminal facility inventory, or the
lost-facility no-resume proof for an identity that never left the pending higher
state. It maps
`PENDING_FACILITY_CAPACITY |
PREAUTHORIZATION_CANCELLATION_PENDING_FACILITY_RELEASE` to
`CANCELED_BEFORE_AUTHORIZATION`, and maps `ISSUED_PENDING_FACILITY` to
`CANCELED_UNUSED`. The third classification requires an exact consumed mapping
or the lost-facility branch's conservative possibly-consumed component proof.
It maps `ISSUED_PENDING_FACILITY |
CONSUMED_BY_FACILITY_RESERVATION` to `FACILITY_REALM_FENCED`.
An incompatible prior state, omitted entry, duplicate entry, changed identity or
unproved classification rejects.

Only when the projection fact proves an exact terminal bijection from the frozen
authorization map to
preserved terminal entries, facility-unused tombstones or fenced consumed
reservations, and every facility in the envelope has its matching closed
full-set isolation evidence, can
`INSTALL_AUTHORITY_REALM_EXTERNAL_ISOLATION_CUT_AFTER_DOMAIN_STATE_LOSS`
commit. The candidate binds the projection fact and higher-root CAS condition.
The winning higher-root transaction installs the projected map and writes every
new `FACILITY_REALM_FENCED` entry. Its generic registry commit receipt precedes
`AuthorityRealmFacilityIsolationAuthorizationProjectionReceipt`; that receipt
binds the exact installed map root and precedes
`AuthorityRealmExternalIsolationCutReceipt`. Every facility-produced branch in
the projection fact arrives through exact protected verification. The
persistence manifest is last.
No facility receipt or local claim can write the higher-map state. A
reservation-only realm with no physical authorization uses explicit empty roots.
No higher isolation receipt can coexist with a facility root that still permits
same-realm reservation or re-enrollment.

Local domain retirement is not always reachable. Closed
`AuthorityRealmUnrecoverableStateCause` is `DOMAIN_SELECTOR_LOST |
REQUIRED_CORE_OR_CLOSURE_GRAPH_UNRECOVERABLE |
STORE_ATOMICITY_OR_COMMIT_CONTINUITY_INVALID`. The second branch applies when a
lost lineage, namespace, target, quarantine, body or other required dependency
makes exact local closure impossible even though the domain selector is readable.
The third applies when the local store can no longer make a trustworthy
restrictive CAS. None can be self-certified by reconstructed local state. The
BEGIN event above binds one exact cause, enrollment/store identity, immutable
isolation envelope
and closed `AuthorityRealmLastAuthenticatedDomainEvidence`:
`RESERVATION_ONLY_NO_AUTHENTICATED_DOMAIN_COMMITMENT |
EXACT_LAST_AUTHENTICATED_DOMAIN_COMMITMENT`. The reservation-only branch covers a
target store lost before genesis or with an ambiguous genesis result; it does not
claim non-genesis from remote absence. The later
`INSTALL_AUTHORITY_REALM_EXTERNAL_ISOLATION_CUT_AFTER_DOMAIN_STATE_LOSS`
consumes the exact preparation receipt, the
`AuthorityRealmFacilityIsolationAuthorizationProjectionFact`, complete closed
facility full-set isolation-evidence set and permanent revocation/withdrawal of every
envelope credential and endpoint, and ADR-007 qualified isolation of every
physical path in the complete envelope. Its higher-root transaction records one
`AuthorityRealmExternalIsolationCutReceipt` with the complete cut inventory and
trusted provisioning-authority monotonic clock/incarnation at the linearization
instant `t0`, and moves the entry to `LOST_DOMAIN_ISOLATION_CUT_WAITING`.
It accepts only `LOST_DOMAIN_ISOLATION_PREPARING`. BEGIN accepts
`RESERVED_FOR_EXACT_STORE | INSTALLED` because a reserved target store can
contain an unconfirmed pending domain. BEGIN races late confirmation on the same
higher selector and isolates the full envelope in either branch.

The later disjoint higher-root event
`PERMANENTLY_RETIRE_AUTHORITY_REALM_ENROLLMENT_AFTER_DOMAIN_STATE_LOSS` consumes
`AuthorityRealmLostDomainIsolationFact`. The fact binds that cut receipt, the
envelope-wide maximum post-cut authority-survival duration fixed by the original
enrollment envelope/qualification, including clock drift, no-extension rules and
in-flight transport, and a commit-bound
`EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE` evaluation proving
`now >= t0 + maximum_survival_duration` on the same trusted clock lineage. Wall
UTC, loss-detection time, a last domain timestamp or a pre-commit sample cannot
substitute. Clock restart requires a qualified no-later bridge; absent or
ambiguous continuity leaves the entry waiting forever. Checked deadline addition
overflow also leaves it waiting; it never wraps or chooses a shorter horizon.
Equality at the exact representable deadline is the first passing instant. Its completeness does not
depend on the possibly stale last domain head. It installs the same permanent realm tombstone with closed evidence
`LOST_DOMAIN_PROVED_PERMANENTLY_ISOLATED`, explicitly records that no normal
domain-retirement receipt exists, and claims no semantic closure for lost state.
The closed `AuthorityRealmEnrollmentRetirementEvidence` is
`EXACT_DOMAIN_GENESIS_CANCELLATION_RECEIPT |
EXACT_DOMAIN_RETIREMENT_RECEIPT | LOST_DOMAIN_PROVED_PERMANENTLY_ISOLATED`;
each higher-root event accepts exactly its named branch and structurally forbids
the other branches. If the lost-domain proof is
missing or any snapshot/credential/physical path can resume, the higher entry
stays `RESERVED_FOR_EXACT_STORE | INSTALLED` if preparation never committed,
`LOST_DOMAIN_ISOLATION_PREPARING` while any authorization or facility fence is
unresolved, or `LOST_DOMAIN_ISOLATION_CUT_WAITING` after the cut. None of those
states permits replacement or reuse of the realm ID.

Local participant fencing remains available only when the intact domain can
still reach every exact dependency closure required by FINALIZE. If a lost
participant leaves a live namespace, target or other uncloseable predecessor,
the provider must use the full-envelope higher-root path above; it cannot invent
the missing local tombstone. That path permanently retires the realm without
claiming local semantic closure and makes replacement reachable only after the
external cut and survival horizon pass.

Each `AuthorityTransactionDomainKey` owns one bounded
`LogicalSessionNamespaceRegistryHead` through one
`LogicalSessionNamespaceRegistrySelector`. Its canonical map key is the exact
tuple `(authority_transaction_domain_key, source_session_kind,
source_logical_session_id)`. Its closed root phase is
`OPEN_NAMESPACE | DOMAIN_RETIREMENT_SEALED`, and its closed entry state is
`PENDING_ANCHOR_CAPACITY_RESERVATION | PENDING_NAMESPACE_GENESIS |
LIVE_NAMESPACE | PERMANENTLY_RETIRED`.

For the independent-anchor profile, closed
`PREPARE_SOURCE_LOGICAL_SESSION_NAMESPACE_ANCHOR_CAPACITY_RESERVATION` is the
sole typed-nonmembership insertion. Its receipt-free
`SourceLogicalSessionNamespaceAnchorReservationIntentFact` binds the
authenticated source owner and realm authority, exact namespace, typed registry
nonmembership and never-used proof, prepartitioned anchor owner-lifetime slot,
reservation/allocation operation identities, all preallocated selector
incarnations, profile, fixed capacities/policies, intended independent anchor
authority/failure domain/credential and source-side lifetime-slot counter. The
registry CAS advances that never-reset counter and installs
`PENDING_ANCHOR_CAPACITY_RESERVATION` with no lineage, source-index or anchor
head. Its post-CAS
`SourceLogicalSessionNamespaceAnchorReservationIntentReceipt` binds the
installed entry and registry commit.
`SourceLogicalSessionNamespaceAnchorReservationIntentProjection` is returned
only to the intended anchor in
`ProtectedSourceLogicalSessionNamespaceAnchorReservationIntentEnvelope` under
`DURABLE_HISTORICAL_COMMIT / INDEPENDENT_ANCHOR_AUTHORITY /
SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT`, with its exact family manifest,
producer completion, delivery capsule and both scoped proofs. Reply-loss retry
returns the same bundle.

Only after that source intent commits can the owner obtain the exact verified
`ProtectedIndependentAnchorNamespaceCapacityReservationEnvelope`, selected
reservation family, anchor-producer completion, delivery capsule and both
scoped proofs under
`DURABLE_HISTORICAL_COMMIT /
PENDING_SOURCE_NAMESPACE_ANCHOR_BOOTSTRAP /
ANCHOR_NAMESPACE_CAPACITY_RESERVATION`. Its projection binds the prospective
source namespace and every preallocated selector/incarnation, profile, fixed
capacity/policy, source-owner quota, global capacity charge and anchor
reservation-registry coordinate. It grants no source or anchor authority and
does not prove source allocation. A reservation for a different source owner,
namespace, profile, selector, quota or capacity charge cannot substitute.
Its nonterminal entry blocks normal semantic anchor-authority-domain retirement.
Only protected source cancellation after allocation, anchor materialization
followed by permanent source isolation, or whole-realm higher-root isolation can
end the operational obligation. The higher-root path does not claim a local
reservation terminal or reclaim its capacity. Timeout, lost return and
disappearance cannot terminalize it.
Exact `ALLOCATE_SOURCE_LOGICAL_SESSION_NAMESPACE` has two closed prestates.
The source-retirement-only profile inserts from typed map nonmembership. The
independent-anchor profile changes the exact
`PENDING_ANCHOR_CAPACITY_RESERVATION` intent to
`PENDING_NAMESPACE_GENESIS`; typed absence cannot substitute. Its receipt-free
`SourceLogicalSessionNamespaceAllocationFact` binds the authenticated source
owner and realm authority; exact namespace key; typed registry nonmembership
and never-used proof for the retirement-only branch or the exact installed
intent/receipt and lifetime slot for the anchor branch; preallocated lineage
selector, source-index selector and never-reused incarnations; manifest-fixed
registry, byte and terminal reserves;
and one immutable
`ObserverGrantPermanentNoLiveAcceptanceAvailabilityProfile`. The independent-
anchor profile additionally binds the intended anchor authority/key, store,
selector incarnation, failure domain, credential selection, fixed anchor
capacities/policies, exact verified capacity-reservation hierarchy and
preallocated protected-output identities. The source-
retirement-only profile forbids every anchor field. The fact excludes the
candidate, installed entry and receipts.

The one registry CAS installs `PENDING_NAMESPACE_GENESIS` with those exact
fields and no lineage or source-index head.
`SourceLogicalSessionNamespaceAllocationReceipt` binds the fact, installed
pending entry, registry heads/commit and reservation accounting. For the
independent-anchor profile,
`SourceLogicalSessionNamespaceAllocationProjection` binds the allocation fact
and receipt digests, installed pending-entry projection, exact preallocated
selectors/incarnations, profile and intended anchor. It omits private registry
counters, preserves the exact anchor reservation key/receipt digest and is
delivered to only that anchor in
`ProtectedSourceLogicalSessionNamespaceAllocationEnvelope`,
`DURABLE_HISTORICAL_COMMIT / INDEPENDENT_ANCHOR_AUTHORITY /
SOURCE_NAMESPACE_ALLOCATION_BOOTSTRAP`, through one
pre-manifest, one
`SourceLogicalSessionNamespaceAllocationPublicationManifest`, the mandatory
producer completion, one delivery capsule and both scoped proofs. All are
durable before exposure. This protected allocation hierarchy is the sole legal
input to anchor genesis and the return audience's prospective namespace
bootstrap. A bare allocation receipt, guessed selector, changed profile or
different anchor rejects.

`REGISTER_SOURCE_LOGICAL_SESSION_LINEAGE` consumes the exact pending allocation
entry and receipt and changes it to `LIVE_NAMESPACE`. In the same
authority-domain transaction it
executes subordinate
`LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY` and
`OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX_GENESIS_FROM_SOURCE_LINEAGE_REGISTRATION`.
Receipt-free `ObserverGrantSourceIssuanceIndexGenesisFact` binds the full source
namespace, allocation receipt, typed index-selector absence and never-used proof, fixed sparse-tree
suite/context, canonical empty issuance root and eligible-root set, fixed
issuance/eligible-root/byte caps, proof-node retention, idempotency bounds,
availability profile, per-enrollment closure-reserve policy, terminal freeze
reserve and intended `SOURCE_ISSUANCE_OPEN` projection. The independent-anchor
profile additionally binds the exact verified anchor-genesis hierarchy under
`PENDING_SOURCE_NAMESPACE_ANCHOR_BOOTSTRAP`. It requires the prospective
namespace, lineage/source-index/anchor selector incarnations, profile, anchor
authority, capacity and policy fields, reservation-registry key, reservation
receipt digest and allocation identity to equal the pending allocation
byte-for-byte. A genesis projection with a different reservation ancestry
cannot register the namespace. The retirement-only profile forbids the
anchor-genesis hierarchy. The fact excludes the CAS condition, candidates,
installed heads and receipts.

The common CAS installs the new lineage selector at `NO_GENERATION`, the
generation-independent
`InstalledObserverGrantSourceIssuanceIndexSelector` at
`SOURCE_ISSUANCE_OPEN`, and both exact participant entries/reserves through
fresh `CANDIDATE_PARTICIPANT_ADMISSION`, while it replaces the exact pending
namespace entry with its LIVE projection. It compares the pending allocation
entry and typed absence plus never-used proof for both selectors. The lineage
and index candidates bind their respective genesis facts and the common
condition, never one another. Neither head is usable between native genesis and
registry admission. A caller-created selector, a second namespace-registry or
source-index selector, typed namespace absence, a mismatched pending allocation,
post-registration index creation, or a prior permanent tombstone rejects.
Security rotation and every permitted registry successor preserve the complete
entry projection. The bounded map never evicts or reuses a key;
it retains authoritative entry bytes or complete membership/nonmembership proof
material for every admitted key. A chain or Merkle root without retained proof
material is insufficient. Before source-key/tombstone capacity would consume its
retirement reserve, the whole authority transaction domain enters drain-only.
Capacity exhaustion refuses new logical-session IDs. Only after the old domain's
permanent realm tombstone can a newly enrolled stable realm key admit a textually
equal caller logical ID; the full namespace key is different and the old realm
can never answer it.

Closed
`CANCEL_PENDING_SOURCE_LOGICAL_SESSION_NAMESPACE_ANCHOR_RESERVATION_INTENT`
is the only pre-reservation abandonment edge. Its receipt-free
`SourceLogicalSessionNamespaceAnchorReservationIntentCancellationFact` binds the
exact pending intent/receipt, owner, anchor lifetime slot and all preallocated
coordinates; typed absence of lineage/source-index participant admissions;
cancellation cause; retained no-reuse projection; and the precharged protected
output identities. One source registry CAS installs `PERMANENTLY_RETIRED /
ANCHOR_CAPACITY_RESERVATION_INTENT_CANCELED` and
`SourceLogicalSessionNamespaceAnchorReservationIntentCancellationReceipt`.
Allocation and intent cancellation compare the same source registry selector:
cancellation-first makes allocation lose forever.

The same producer derives
`SourceLogicalSessionNamespaceAnchorReservationIntentCancellationProjection`
and delivers it only to the intended anchor in
`ProtectedSourceLogicalSessionNamespaceAnchorReservationIntentCancellationEnvelope`
under `PERMANENT_CLOSURE_TOMBSTONE / INDEPENDENT_ANCHOR_AUTHORITY /
SOURCE_NAMESPACE_ANCHOR_RESERVATION_INTENT_CANCELLATION`, with its family
manifest, producer completion, delivery capsule and both scoped proofs. The
projection binds the intent, permanent source tombstone, owner lifetime slot,
reservation key and every coordinate. It does not claim that an anchor
reservation exists. At the anchor, reservation and cancellation import compare
the same slot and coordinate indexes: either order reaches the same retained
terminal entry. A delayed reservation request loses after cancellation import.
Missing cancellation delivery leaves either no anchor state or a bounded
reservation; exact retry remains available. Timeout, disappearance and a bare
source receipt cannot cancel anchor state.

Closed `CANCEL_PENDING_SOURCE_LOGICAL_SESSION_NAMESPACE` is the only
pre-genesis abandonment edge. Its receipt-free
`SourceLogicalSessionNamespaceAllocationCancellationFact` binds the exact
pending entry/allocation receipt, authenticated allocating owner, typed absence
of both preallocated selector heads and participant admissions, cancellation
cause, retained no-reuse projection and permanent tombstone reserve. One
registry CAS installs `PERMANENTLY_RETIRED /
PENDING_NAMESPACE_GENESIS_CANCELED` and
`SourceLogicalSessionNamespaceAllocationCancellationReceipt`. Under the
independent-anchor profile, the same producer derives
`SourceLogicalSessionNamespaceAllocationCancellationProjection` over the
allocation fact/receipt, installed permanent tombstone, exact preallocated
anchor selector/incarnation, capacity-reservation ancestry and cancellation
commit. It delivers that
projection only to the intended anchor as
`ProtectedSourceLogicalSessionNamespaceAllocationCancellationEnvelope` under
`PERMANENT_CLOSURE_TOMBSTONE / INDEPENDENT_ANCHOR_AUTHORITY /
SOURCE_NAMESPACE_ALLOCATION_CANCELLATION`, with one
`SourceLogicalSessionNamespaceAllocationCancellationPublicationManifest`, the
producer completion, delivery capsule and both scoped proofs. The projection
cannot cancel a different allocation or any LIVE namespace. Registration and
cancellation compare the same registry selector: registration-first makes
cancellation use normal source retirement; cancellation-first makes genesis
lose forever. Reply-loss retry returns the exact installed cancellation and,
when applicable, protected-output bundle.
Anchor genesis that raced ahead remains a nonauthorizing retained anchor
artifact and cannot revive the canceled source namespace. Unknown owner,
different allocation, selector presence, participant presence, reuse,
deletion, timeout-only cancellation or capacity reclamation rejects. An
abandoned pending entry therefore consumes bounded historical capacity; it is
never evicted or silently reused.

The common transaction receipt precedes the lineage native-genesis,
source-index native-genesis and two participant-admission receipts.
`ObserverGrantSourceIssuanceIndexGenesisReceipt` binds the genesis fact,
installed selector/head, allocation receipt, LIVE namespace entry, participant
entry, qualification and common receipt. The crash-complete persistence manifest binds the exact complete
bundle last. Reply-loss replay returns that bundle without a second namespace,
lineage, index or participant admission. A changed allocation, profile, cap,
empty root, selector, suite or namespace rejects.

Each server authority/realm then owns one durable
`LogicalSessionGenerationLineageHead` for each canonical `(logical_session_id,
session_kind)` through one `InstalledLogicalSessionGenerationLineageSelector`.
The head binds a never-reused lineage incarnation, strict version, retained
generation no-reuse set, exact current child-generation branch and prior head.
Its closed branch is
`NO_GENERATION | GENERATION_ALLOCATED_PENDING_CHILD_GENESIS | GENERATION_LIVE |
GENERATION_PARTIAL_RETIREMENT_PREPARED | GENERATION_RETIRING |
GENERATION_FINALIZED | SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED |
SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED`. A generation UUID is opaque and is
never ordered, but membership and equality are authoritative.

Every selector that an ADR-001 transition claims to compare atomically shares
one exact `AuthorityTransactionDomainKey` and never-reused transaction-store
incarnation. The server authority enrolls that key with one content-addressed
`AuthorityTransactionDomainQualification`, exact closed static
`AuthorityTransactionDomainParticipantRolePolicyAndBounds` and independent
`AuthorityTransactionDomainQualificationReceipt` before it creates a lineage.
The qualification binds the transaction manager and durable store identity,
strict-serializable multi-selector compare-and-swap semantics, one linearization
point, atomic crash-complete publication, recovery behavior, failure model, and
hard participant/byte bounds. A transaction can compare or publish only
selectors under the same key and store incarnation and within those bounds. A
pre-read, post-read, cache, replica, saga, eventually consistent exchange, or
prepared-but-not-atomically-committed distributed exchange is not an atomic
compare. Logical selector owners remain distinct; shared transaction placement
does not transfer their authority. Each write-selector owner authorizes its exact
event-specific mutation. Each read-only participant owner instead pre-enrolls a
narrow selector/version compare policy in the qualification. The transaction
manager enforces the exact per-role read/write ACL and cannot mutate a read-only
participant or treat compare enrollment as mutation authority.

Each such operation constructs one receipt-free
`AuthorityTransactionCASCondition`. It binds a canonical complete read set of
common authority-transaction-domain key, transaction-store incarnation,
qualification digest/version/receipt, transaction-manager identity and exact
participant-role assignment. For each participant it then binds selector type,
key, owner, expected version and head, plus the exact write-selector set and
event-specific receipt-free fact and
`PreCASAuthoritySemanticCommitment` digests. Every common field must be exactly
equal across the complete participant set. A pre-CAS commitment is a closed
typed class that structurally excludes the CAS condition, every candidate/
successor, every current-or-later receipt and every post-candidate sidecar. It
may bind a typed `PriorInstalledEvidenceReceipt` only when that receipt's commit
is strictly earlier in the same authenticated ancestry or is exact independently
authenticated external evidence required by the event, and the condition binds
its identity/currentness relationship to the expected prestate. A fact follows
the same rule. The condition likewise excludes every candidate/successor digest,
post-candidate sidecar and current-or-later receipt. Candidate heads can bind the
fact, pre-CAS commitments and condition; they never bind a later artifact.

A distinct closed `PostCandidateInstalledStateSidecar` class contains only
receipt-free objects whose meaning requires one or more complete candidate or
installed heads. A sidecar can bind candidates, the fact, pre-CAS commitments
and condition, plus the fact's exact `PriorInstalledEvidenceReceipt` set, but no
current-or-later transaction or dependent receipt. It is constructed after every
candidate that it binds and is never an input to the CAS condition or any
candidate. A type cannot belong to both classes. The event schema declares the
canonical complete sidecar set, including typed empty, and rejects an undeclared,
missing or extra object. This partition prevents a generic “semantic commitment”
field from silently creating
`candidate -> commitment -> condition -> candidate`.

Apart from the two typed-absence domain-bootstrap outcomes below, the only
exception to an expected selector version/head is the closed
`LOST_REGISTERED_PARTICIPANT_EVIDENCE_ONLY` disposition. It names
the registered lost entry and isolation fact but is excluded from the actual
selector read/write set; all current participants still have exact expected
heads. Unknown currentness cannot be encoded as a wildcard.

The winning atomic publication emits one `AuthorityTransactionCommitReceipt`
over the condition, exact prior and installed selector set, exact installed
candidate-head digests, the canonical complete post-candidate sidecar set, a
monotonic transaction commit position and an
`AuthorityTransactionInstalledStateRoot`. That root contains only installed
selector/head digests and declared receipt-free sidecar commitments; it excludes
the transaction receipt and every dependent post-commit receipt. Every affected
selector-specific commit receipt depends on the transaction receipt. A final
non-authorizing `AuthorityTransactionPersistenceManifest` binds the exact
transaction receipt and complete selector-specific receipt/sidecar byte set. It
is exposed with the installed state only after the entire atomic bundle is
durable, and no earlier object binds it. Missing or extra participants, a partial
bundle, a candidate that binds its future receipt, or independently authoritative
participant heads reject. A distributed transaction manager can qualify only
when its single durable commit decision has those atomic visibility and recovery
semantics.

The commit position uses a manifest-selected bounded unsigned domain, starts at
its exact genesis value, advances by one, and never wraps, rolls back or reuses a
value. One `AuthorityTransactionDomainStateHead` and
`InstalledAuthorityTransactionDomainSelector` own that high-water and the closed
domain state `GENESIS_CANCELED_BEFORE_CREATION |
PENDING_REALM_CONFIRMATION | ACTIVE | RETIREMENT_DRAIN_ONLY |
PERMANENTLY_RETIRED`. The first value is a retained alternative-bootstrap
tombstone, not an empty or reusable domain. Every domain
transaction conditionally compares and advances that selector in the same atomic
publication; a store-native value whose order/no-reuse semantics are not part of
the qualification cannot substitute.

That domain head also owns the canonical bounded
`AuthorityTransactionDomainParticipantRegistry`. Its exact immutable key is only
`(authority_transaction_domain_key, selector_type, selector_key,
selector_incarnation)`. The value binds the one participant role, logical owner,
read/write ACL, `AuthorityTransactionDomainParticipantAdmissionCommitment` and
closed state `REGISTERED_ACTIVE | TERMINAL_RETAINED |
LOST_STATE_PERMANENTLY_FENCED`. The pre-transaction commitment
binds the exact realm-isolation-envelope subset reserved for that participant,
the admission origin, selector identity, owner/ACL and the complete intended
initial semantic projection. For the fresh branch it binds the exact owner-
authorized native-genesis fact, but structurally excludes the candidate selector/
head digest, `AuthorityTransactionCASCondition` and every receipt. For the
existing-selector branch it instead binds the exact already-installed selector/
head and its prior native-genesis receipt; it excludes the new transaction and
every receipt that depends on that transaction. A selector identity can occur in exactly
one entry across all live entries and tombstones; changing role, owner or ACL
cannot create another key. The static qualification
defines permitted role classes and maxima. The live registry defines the actual
instances. Each operation's `AuthorityTransactionDomainParticipantSet` is the
exact applicable subset derived from those installed entries, never a caller
list. Its closed participation disposition is
`CURRENT_SELECTOR_PARTICIPANT | LOST_REGISTERED_PARTICIPANT_EVIDENCE_ONLY`.
The second disposition is legal only for exact participant-loss detection and
fencing events after the registered selector's current head cannot be obtained.
It is an evidence-only exclusion from the transaction read/write selector set,
not a claimed compare of the missing selector.

The bootstrap `AUTHORITY_TRANSACTION_DOMAIN_STATE` self-entry uses distinct
receipt-free `AuthorityTransactionDomainSelfAdmissionCommitment`. It binds the
stable domain-selector identity, owner/ACL, qualification and
`AuthorityTransactionDomainGenesisFact`, and structurally excludes the candidate
domain-head digest. The domain-genesis receipt later attests the installed self-
entry and head. Applying the ordinary candidate-head binding to that self-entry
is a forbidden digest cycle.

`REGISTER_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT` has two closed admission
branches: `INSTALL_FRESH_SELECTOR_WITH_NATIVE_GENESIS |
ENROLL_BOOTSTRAP_OR_GENESIS_ONLY_EXISTING_SELECTOR`. The fresh branch is the sole
`CANDIDATE_PARTICIPANT_ADMISSION` exception to deriving a participant from an
installed registry entry. Its non-authorizing candidate requires typed never-used
selector absence, exact owner-authorized native genesis, a qualification-
permitted role/key/ACL and closure reserve; it becomes ordinary only when the
domain-state CAS atomically installs selector and entry. The existing branch
requires an exact native genesis receipt, genesis-only non-authorizing history,
same store/domain incarnation and an explicit bootstrap reservation. An already
authorizing, remotely stored or historically mutated selector must retire and be
re-enrolled; it cannot be imported by assertion. The registration transaction
atomically installs or admits the selector, registry entry and worst-case closure
reserve. Its CAS condition binds the admission commitment, native-genesis fact or
prior installed-genesis evidence, and exact read/write selector identities, but
no candidate digest. The fresh native selector/head candidate and domain-state
candidate each bind the condition, commitment and native-genesis fact. This
acyclic order is `fact/commitment -> condition -> candidates -> transaction
receipt -> native/admission receipts`; neither a candidate nor the condition can
be reached again from an earlier node.
Post-commit `AuthorityTransactionDomainParticipantAdmissionReceipt` binds the
installed entry, applicable native genesis receipt and
`AuthorityTransactionCommitReceipt`; no candidate object binds it. Core
participants created in domain genesis use the same receipt-free commitments and
are attested only by the later domain-genesis receipt.
The closed `AuthorityTransactionDomainParticipantRetirementEvidence` is
`EXACT_TERMINAL_HEAD | LOST_STATE_PROVED_PERMANENTLY_ISOLATED`.
`TERMINALIZE_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT` consumes the exact
terminal selector head/receipt of a non-core, non-domain-self participant and
changes the entry to `TERMINAL_RETAINED` while recomputing reserve. The domain-
self, namespace, target-history and quarantine core entries cannot take this
generic event; exact-present cores and the self-entry terminate atomically in a
domain cancellation/finalization transaction below.
For `LOCAL_SECURITY_ENFORCEMENT`, the exact terminal evidence is the ADR-009
`DOMAIN_RETIRED` head and
`SecurityAuthorityDomainRetirementReceipt`. The security-retirement guard
requires that participant to remain `REGISTERED_ACTIVE` until the receipt
commits; requiring its earlier terminalization would create a closure cycle.
For `OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX`, exact terminal evidence is the
`SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED` head,
`ObserverGrantSourceIssuanceIndexCommitReceipt`,
`ObserverGrantSourceIssuanceNamespaceClosureReceipt` and matching
`SourceLogicalSessionRetirementReceipt`. Generic participant terminalization
can retain that selector only after those receipts commit. Loss or ambiguity of
the index cannot satisfy semantic source retirement, stable-key absence or a
namespace closure proof. It requires the higher-root isolation path for the
affected source/realm, while a separately preinstalled independent exposure
anchor can support only its narrower no-exposure/no-live-acceptance result.
Distinct
`FENCE_LOST_AUTHORITY_TRANSACTION_DOMAIN_PARTICIPANT_AFTER_ISOLATION` consumes
`AuthorityTransactionDomainParticipantLostStateIsolationFact`: last
authenticated selector/head and bounded possible-obligation inventory, typed
store-level missing/ambiguous evidence, plus role-specific independent permanent
isolation. Its CAS includes the domain-state selector and every intact
participant required for reserve and closure accounting. The lost registered
entry appears as `LOST_REGISTERED_PARTICIPANT_EVIDENCE_ONLY`; it has no expected
head/version and cannot be in the write set. If the qualified store exposes an
atomic corruption marker or slot-absence predicate, the condition binds that
predicate as separate store evidence; otherwise it does not claim a selector
compare. Body-control and actuation-domain roles require ADR-007 complete
physical-footprint isolation. Local-security loss requires withdrawal of the
full realm credential/endpoint envelope and, for a plant-capable realm, complete
physical fencing/isolation. Proven disjoint observer or simulation roles can use
their exact envelope subset and no-resume horizon. An unknown role defaults to
full-realm isolation.
Loss of a namespace, lineage, target-history or quarantine core participant
requires isolation of the full realm envelope, not a narrow participant subset.
Loss of `AUTHORITY_TRANSACTION_DOMAIN_STATE` cannot take this event because its
selector is the CAS root; it routes only through the higher provisioning-root
domain-loss sequence above.
Authenticated missing/ambiguous participant detection first selects
`PARTICIPANT_STATE_LOST_OR_AMBIGUOUS` on
`BEGIN_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT`; that domain-selector event moves
`ACTIVE -> RETIREMENT_DRAIN_ONLY` while preserving the registered uncertain
entry. It uses the same evidence-only disposition and never waits for unavailable
selector currentness. The later participant-fence event is legal only in drain-only and only
with complete isolation evidence. It installs
`LOST_STATE_PERMANENTLY_FENCED`, preserves the uncertainty and claims no semantic
closure. If proof never arrives, the domain remains drain-only forever. Neither
event has a return-to-ACTIVE edge, and both consume reserved closure capacity.
Neither event can register an already used selector key, widen its ACL or omit
the domain-state participant. Realm-global namespace,
target-history and quarantine selectors are core participants installed during
domain genesis; lineage and child selectors register through their exact creation
transactions. ADR-001 lineage/child genesis, ADR-007 jurisdiction genesis and
ADR-009 local-security genesis are subordinate to one of these exact admission
branches; no selector can become usable between native genesis and participant
admission.

`AUTHORITY_TRANSACTION_DOMAIN_GENESIS_FROM_ENROLLMENT` and
`CANCEL_AUTHORITY_TRANSACTION_DOMAIN_GENESIS_BEFORE_CREATION` are the two and
only bootstrap exceptions to the already-installed-selector rule. Closed
`AuthorityTransactionDomainBootstrapOutcome` is
`CREATE_PENDING_DOMAIN | CANCEL_BEFORE_DOMAIN_CREATION`. They use the reserved
`InstalledAuthorityTransactionDomainSelector` itself as the one-shot target
bootstrap selector; no parallel bootstrap namespace can race or later reset it.

Common receipt-free `AuthorityTransactionDomainBootstrapFact` binds the exact
protected reservation verification evidence and inner digest, higher reservation
lineage and one-use marker, shared consumption key, target principal, domain key,
reserved selector/store identity, never-used store incarnation, transaction
manager, `AuthorityTransactionDomainQualificationReceipt`, exact selector typed
absence plus never-used proof, exact genesis commit position, operation identity
and one outcome. It excludes every candidate, installed root, commit receipt and
manifest. The CREATE branch contains the complete initial participant/reserve
inventory in `AuthorityTransactionDomainGenesisFact`. The CANCEL branch instead
proves typed absence of every subordinate selector and contains the exact
`AuthorityTransactionDomainGenesisCanceledTombstone`; it cannot carry a
participant, reserve or authorizing projection.

The bootstrap form of `AuthorityTransactionCASCondition` compares the reserved
domain-selector absence and the unconsumed shared marker under that exact
qualified target store/incarnation. Each branch's candidate binds the common
fact, branch fact and condition. The winning strict-serializable publication
installs the domain selector at the genesis commit position and permanently
records the same `FacilityAuthorityCrossStoreReceiptConsumptionIndex` key.
CREATE installs state `PENDING_REALM_CONFIRMATION`, the exact reserve, subordinate
empty `LogicalSessionNamespaceRegistryHead`/selector, observer target-history
selector and unresolved-target quarantine selector with their core participant
entries. CANCEL installs state `GENESIS_CANCELED_BEFORE_CREATION`, the immutable
cancellation tombstone, an empty non-authorizing participant projection and no
subordinate selector. Thus genesis and cancellation compare one absence and one
marker in one target-store commit; at most one can win.

Both outcomes emit `AuthorityTransactionCommitReceipt` over exact prior absence,
installed selector/head/root, checked commit position and marker consumption.
CREATE then emits `AuthorityTransactionDomainGenesisReceipt`; it binds the
enrollment verification, qualification, facts, installed heads/selectors and
receipt-free installed-state root, and core selector-specific receipts depend on
it. CANCEL emits
`AuthorityTransactionDomainGenesisCancellationReceipt` over the corresponding
generic receipt, installed terminal head and tombstone. The complete specialized
receipt/sidecar set is durable in `AuthorityTransactionPersistenceManifest`.
Branch-final non-authorizing
`AuthorityTransactionDomainGenesisPersistenceManifest` or
`AuthorityTransactionDomainGenesisCancellationPersistenceManifest`, respectively,
binds that complete bootstrap bundle last. No earlier object binds either
manifest or its own receipt. Only after the branch-final manifest can the
specialized receipt enter its exact protected cross-store export to the higher
registry.

Recovery completes or returns the one installed bundle. Exact operation/content
reply-loss replay returns its retained receipt and manifests without a second
commit or export consumption. Reuse with another operation, outcome, inner
digest, marker or selector rejects. If either branch won, a delayed other branch,
selector absence, selector loss, second bootstrap or alleged empty reset is
corruption and cannot authorize or retire the realm by assertion.

`ACTIVATE_AUTHORITY_TRANSACTION_DOMAIN_AFTER_REALM_CONFIRMATION` consumes the
protected exact higher-root `AuthorityRealmEnrollmentConfirmationReceipt` and
alone moves `PENDING_REALM_CONFIRMATION -> ACTIVE`. Pending permits only that
activation, exact query/recovery or
`CANCEL_UNCONFIRMED_AUTHORITY_TRANSACTION_DOMAIN`; no participant can admit,
publish, reserve, open a gate or invoke. Cancellation requires the original empty
namespace/target/quarantine roots, no non-core participant and no created
obligation. It installs `PERMANENTLY_RETIRED` with closed retirement branch
`UNCONFIRMED_EMPTY_DOMAIN` and emits the exact domain-retirement receipt that the
higher registry can consume from `RESERVED_FOR_EXACT_STORE` or `INSTALLED` as
defined above. In the same transaction it changes each pristine namespace,
target-history and quarantine root to `DOMAIN_RETIREMENT_SEALED` and changes
those three core participant entries plus the domain-self entry from
`REGISTERED_ACTIVE` to `TERMINAL_RETAINED`. Receipt-free
`AuthorityTransactionDomainUnconfirmedCancellationFact` binds their
exact genesis-only prior heads and complete empty-map proofs, excludes every
candidate, and the transaction/domain-retirement receipt attests the installed
sealed heads and entries. Local cancellation is legal without a higher-root currentness
read: it can race local activation even after higher confirmation. Activation
and cancellation compare the same pending domain head. Higher confirmation and
higher lost/retirement transitions independently race on their one selector;
their exact state mapping leaves no committed domain-retirement receipt
unconsumable.

Before the domain admits any participant, it reserves an exact
`AuthorityTransactionDomainRetirementBudget` of commit positions, transaction
bytes, log/storage bytes and scheduler work. The budget is a canonical sum of the
manifest-defined worst-case fence, ambiguity closure, child/source permanent
retirement, source-issuance-index freeze/proof retention/root-audience closure,
observer publication-or-quarantine, physical-domain isolation/retirement and
final domain-tombstone costs for every currently registered
participant, plus one independently reserved margin. Every participant admission
atomically increases the reserve before it becomes usable. Every later transition
that creates or enlarges a grant, target, outbox item, operation, pending
ambiguity, participant, physical-domain or other closure obligation also
increases the exact reserve in its same domain transaction before the obligation
becomes current. No successor can increase worst-case retirement cost without
that update. Every terminal change recomputes the reserve from retained
obligations. Ordinary, simulation and observer work cannot consume reserved
units.

`BEGIN_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT` is the sole
`ACTIVE -> RETIREMENT_DRAIN_ONLY` edge. It runs before the next non-retirement
commit could cross `maximum_commit_position - exact_reserved_positions`, closes
new lineage/participant allocation and authority widening, and uses the reserve
to fence and drain every live plant, simulation and observer participant. The
closed `AuthorityTransactionDomainRetirementCause` is
`CAPACITY_THRESHOLD | ADMINISTRATIVE_REALM_RETIREMENT |
PARTICIPANT_STATE_LOST_OR_AMBIGUOUS |
ACTIVE_QUALIFICATION_WITHDRAWN_RESTRICTIVE_CLOSE_STILL_QUALIFIED`; each branch
binds exact cause evidence and forbids the others. The last branch requires an
independently prequalified restrictive-close mode whose atomicity, durability,
domain-selector currentness and commit-position continuity remain intact. A
store or transaction-manager fault that invalidates any of those properties
cannot self-attest BEGIN or FINALIZE; it routes to the higher-root domain-loss
isolation sequence. The
domain can seal unresolved remote observer obligations into their bounded
non-authorizing quarantine, but it cannot relabel them closed. Exact
`FINALIZE_AUTHORITY_TRANSACTION_DOMAIN_RETIREMENT` consumes the canonical
complete non-self participant partition. Every non-core entry is already
`TERMINAL_RETAINED | LOST_STATE_PERMANENTLY_FENCED`. Each namespace, observer-
target-history and unresolved-quarantine core is either exact-present and
seal-ready or already `LOST_STATE_PERMANENTLY_FENCED`; exact-present namespace
maps contain only permanent namespace tombstones, target maps contain only the
two permanent source-target tombstones, and quarantine maps contain only sealed
unresolved or archived non-authorizing tombstones. The physical-jurisdiction
partition proves realm-local jurisdiction/arbiter entries terminal or unowned
and the old facility epoch still FENCED; it does not require facility handover,
release or a new realm. Requiring those later cross-root events here would create
a retirement cycle.

Receipt-free `AuthorityTransactionDomainRetirementFinalizationFact` binds that
complete partition, the exact prior core heads, remaining-budget proof and
intended sealed projections while
excluding candidates. Its one authority-domain transaction changes every exact-
present core root to `DOMAIN_RETIREMENT_SEALED`, changes each corresponding core
participant entry and the still-`REGISTERED_ACTIVE` domain-self entry to
`TERMINAL_RETAINED`, and installs domain state `PERMANENTLY_RETIRED`. Lost core
entries remain lost-state fenced and no missing root is reconstructed. The
domain-self selector has no generic terminalization or lost-self branch; if it is
missing, only the higher provisioning-root lost-domain sequence can proceed.
`AuthorityTransactionDomainRetirementReceipt` attests the finalization fact,
installed core/self partition and branch. The independently administered
realm-enrollment registry later consumes its protected exact export to install
its permanent tombstone; it is not part of the domain transaction. No event
leaves that state or resets its counter. An exhausted, corrupt or under-
sized domain cannot invent closure capacity: all software plant authority stays
fenced, affected hardware requires the qualified isolation/lost-state path, and
the realm cannot be reused.

The closed `AuthorityTransactionDomainRetirementBranch` is
`UNCONFIRMED_EMPTY_DOMAIN | CONFIRMED_DOMAIN_DRAIN`. Cancellation accepts only
the first, requires the exact pristine-core/domain-self terminalization partition
above, and structurally forbids every non-core participant or dynamic-obligation
closure field. Normal drain finalization accepts only the second and requires the
complete partitions above. The retirement receipt binds that branch; the higher
registry cannot substitute one for the other.

The neutral `AuthorityRealmKey`, its `AuthorityTransactionDomainKey` and the
ADR-004 observer alias have the same canonical server-principal/stable-realm-ID
value. They exclude rotating security epochs, registry incarnations and every
generation. The lineage head, realm-global target-history selector and all required
child selectors in that realm share the key. Each logical source's
generation-independent observer source-issuance-index selector shares that same
key and transaction-store incarnation. A plant creation additionally
requires the exact ADR-007 jurisdiction registry, arbiter and body selector and
the local ADR-009 security-authority selector to share it. One realm can contain
multiple physical jurisdictions only when all of them use that same qualified
transaction domain; otherwise each jurisdiction needs a distinct stable realm.
A jurisdiction enrollment cannot be caller-rebound to a server's key. A missing,
mismatched, over-bound or unqualified domain keeps plant generation reservation,
genesis, confirmation, activation and command admission closed. Moving a realm,
lineage or jurisdiction to a different key, store incarnation or qualification
requires its permanent retirement and a new stable realm/lineage enrollment; it
is not a live rebind and cannot reconstruct anti-ABA history. The candidate
repository supplies no runtime qualification result, and this proposed
requirement does not satisfy any external release gate.

The closed participant roles are
`AUTHORITY_TRANSACTION_DOMAIN_STATE | LOGICAL_SESSION_NAMESPACE_REGISTRY |
LOGICAL_SESSION_LINEAGE | SIMULATION_SESSION_STATE |
BODY_SESSION_CONTROL | OBSERVER_AUTHORIZATION | OBSERVER_TARGET_HISTORY |
OBSERVER_UNRESOLVED_TARGET_QUARANTINE |
OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX |
ACTUATION_DOMAIN_REGISTRY_AND_ARBITER | LOCAL_SECURITY_ENFORCEMENT`.
`AUTHORITY_TRANSACTION_DOMAIN_STATE` is mandatory in every non-genesis
transaction; namespace registration and permanent retirement also require
`LOGICAL_SESSION_NAMESPACE_REGISTRY`. Namespace registration freshly admits
`LOGICAL_SESSION_LINEAGE | OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX`. Permanent
source retirement additionally requires
`LOGICAL_SESSION_LINEAGE | OBSERVER_GRANT_SOURCE_ISSUANCE_INDEX |
OBSERVER_TARGET_HISTORY |
OBSERVER_UNRESOLVED_TARGET_QUARANTINE`, and the observer child when it remains a
retained participant. The event scope derives every other exact applicable role.
A participant role is a
transaction placement and compare-set obligation, not authority to mutate the
participant. Multiple distinct selector keys can have the same role class; only
a duplicate exact selector/role assignment or one selector identity under a
second role, owner or ACL rejects. Unknown, missing or inapplicable event
participants also reject.

ADR-004 source-index enrollment and challenge operations use the source index as
an exact participant, not as a remote pre-read.
`ENROLL_OBSERVER_ROOT_IN_SOURCE_ISSUANCE_INDEX` writes the source-index selector,
read-compares the current source-lineage and local-security selectors, and
advances the domain selector in one transaction. Its candidate binds the exact
registered-root and, when applicable, anchor-enrollment evidence fixed by the
enrollment fact. `ISSUE_OBSERVER_GRANT_REQUEST_FRESHNESS_CHALLENGE` writes
the observer-authorization and source-index selectors, read-compares the
current source-lineage, realm-global target-history and local-security
selectors, and advances the domain selector in one transaction. Both native
candidates bind the same
`ObserverGrantSourceIssuanceAppendFact` and common CAS condition.
`CANCEL_OBSERVER_GRANT_REQUEST_BEFORE_ACCEPTANCE` with
`ABSENT_INTENT_TOMBSTONE` writes both observer authorization and the
`CANCELED_BEFORE_ISSUANCE` source-index entry; its available-slot branch writes
observer authorization while read-comparing the exact
`CHALLENGE_ISSUED` member. Both cancellation branches also read-compare the
current source-lineage and local-security selectors so that a concurrent source
cut has one order with the tombstone. Attach, renewal and reattachment
acceptance read-compare the current source-lineage, realm-global target-history,
local-security and index selectors, with the index in `SOURCE_ISSUANCE_OPEN` and
the exact stable-key/entry/challenge/slot equality, while their native authority
and grant selectors mutate. A missing participant, open-phase mismatch,
member-kind substitution, stale root, split store or candidate that binds a
sibling fact rejects the entire transaction.

`LOGICAL_SESSION_GENERATION_LINEAGE_GENESIS_FROM_SERVER_AUTHORITY` consumes the
one-use registry insertion marker and can install `NO_GENERATION` only as the
subordinate transition of the winning namespace registration.
`ALLOCATE_FIRST_LOGICAL_SESSION_GENERATION` requires that exact installed empty
head and typed retained-set nonmembership. `ALLOCATE_SUCCESSOR_LOGICAL_SESSION_GENERATION`
requires the exact prior child's terminal finalization receipt and complete
role-specific closure checkpoints. Both construct a receipt-free
`LogicalSessionGenerationCreationFact`, allocate a fresh never-used UUID and
one marker for every member of a closed `RequiredGenerationChildRoleSet`, and
compare-and-swap the lineage head to
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS`. Their post-CAS
`LogicalSessionGenerationCreationReceipt` is the only authority for each matching
child genesis transition. The role set is derived exactly from creation scope:
`SIMULATION_SERVICE` requires
`{SIMULATION_SESSION_STATE, OBSERVER_AUTHORIZATION_STATE}` and `PLANT_CONTROL`
requires `{BODY_SESSION_CONTROL_STATE, OBSERVER_AUTHORIZATION_STATE}`. Duplicate,
missing, extra or inapplicable roles reject.

Each `RequiredGenerationChildSelectorMarker` is an embedded lineage-head member
keyed exactly by `(SessionRef, RequiredGenerationChildRole)`, not an independent
selector. Closed `RequiredGenerationChildSelectorMarkerState` is
`ALLOCATED | CONSUMED | UNUSED_TOMBSTONED`. Allocation installs `ALLOCATED`.
`CONSUMED` permanently binds the role, native child-selector identity/
incarnation, native child-genesis fact digest and checked transaction commit
position. `UNUSED_TOMBSTONED` permanently binds the applicable all-absent abort
or prepared-partial-retirement transition. No state resets, disappears or
changes role.

Closed `RequiredGenerationChildGenesisTransactionProfile` maps roles to native
events exactly:

| Required child role | Native child-genesis event |
|---|---|
| `SIMULATION_SESSION_STATE` | `SIMULATION_SESSION_STATE_GENESIS_FROM_GENERATION_CREATION` |
| `BODY_SESSION_CONTROL_STATE` | `BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION` |
| `OBSERVER_AUTHORIZATION_STATE` | `OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION` |

Every mapped event constructs one receipt-free
`RequiredGenerationChildGenesisJointFact`. It binds the exact generation
creation fact/receipt, allocated marker and expected parent head, mapped role/
event, role-native child-genesis fact, child-selector typed absence plus
never-used proof, common domain qualification and exact role-native additional
participants. Its authority-transaction condition writes the parent lineage
selector, native child selector and mandatory transaction-domain selector in one
CAS. The parent remains `GENERATION_ALLOCATED_PENDING_CHILD_GENESIS` while only
the mapped marker becomes `CONSUMED`; the child installs its exact initial head;
the domain advances its checked commit position. The event cannot consume
another role's marker, install only one side, or use a child-local transaction.

The generic transaction receipt precedes
`RequiredGenerationChildMarkerConsumptionReceipt`, which binds the joint fact,
prior/installed parent heads, allocated-to-consumed marker, installed child
selector/head and generic commit. The role-native child-genesis receipt depends
on that marker receipt, and the final persistence manifest retains the complete
bundle. Exact reply loss returns it without a second child or marker transition;
changed role, event, child bytes or operation identity rejects. Different-role
child genesi serialize on the same parent selector: a loser reselects the
unchanged allocated marker in the new parent head. Partial-retirement PREPARE,
abort and parent confirmation compare that same parent head, so no trace can
contain an installed child with an allocated/tombstoned marker or a consumed
marker without its child.

`CONFIRM_LOGICAL_SESSION_GENERATION_GENESIS` then installs
`GENERATION_LIVE` only after consuming the complete exact child-genesis receipt
set. For a plant generation, it additionally consumes the ADR-007
`BodyActuationDomainGenerationReconciliationReceipt`; a body genesis that
still mirrors reserved domains is not live. Reply loss resumes the same allocated
generation. The post-CAS
`LogicalSessionGenerationGenesisConfirmationReceipt` binds the creation fact/
receipt, complete required-child marker/receipt bijection, role-specific confirmation evidence and
prior/installed lineage heads. It is the only parent-confirmation evidence that
any defined child post-parent activation or authority-widening edge accepts.
Every such edge also conditionally compares that the exact installed lineage
head still names this generation in `GENERATION_LIVE`. It cannot allocate a
sibling.

The creation fact and receipt bind one closed
`LogicalSessionGenerationCreationScope`:
`SIMULATION_SERVICE | PLANT_CONTROL`. Both branches bind the server's exact
observer-authorization policy/configuration, authority-transaction-domain key
and qualification digest for their required empty observer child. The simulation
branch binds its service principal and configuration digest
and structurally forbids a body, plant profile or actuation domain. The plant branch binds the exact body
principal/enrollment, ADR-007 `PhysicalActuationJurisdictionKey` and registry
incarnation, content-addressed plant-profile digest and exactly one
`ActuationAuthorityDomainKey`, plus exact equality between the transaction-domain
bindings of the parent, required children, local security authority and enrolled
jurisdiction registry. Zero, multiple, wrong-jurisdiction, wrong-transaction-
domain or caller-substituted keys reject. `AttachObserver` allocates no ADR-001 generation and
accepts no observer logical-session ID; it uses the already-live source
generation's observer child and ADR-004 realm-global target history.
A creation receipt from one branch cannot initialize or reserve resources for
another branch.

`BEGIN_LOGICAL_SESSION_GENERATION_RETIREMENT` is the only `GENERATION_LIVE ->
GENERATION_RETIRING` edge. It consumes a receipt-free
`LogicalSessionGenerationRetirementFact` with the exact current child-head set and
retirement authorization. Before any child genesis, the authority constructs one
receipt-free `LogicalSessionGenerationAbortIntent` over the exact allocated
lineage head, creation receipt, complete required marker set and typed
nonmembership of every required child selector. For a plant generation, ADR-007 reservation cancellation consumes
that intent first and races body genesis at the exact domain selector. The disjoint
`ABORT_LOGICAL_SESSION_GENERATION_BEFORE_CHILD_GENESIS` edge consumes the same
intent plus the cancellation receipt (or typed reservation nonmembership) and can move
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS -> GENERATION_RETIRING` only with
typed nonmembership of every required child selector and a tombstone for every
unused child marker. A missing selector is not nonmembership. A plant abort also
requires the ADR-007 reservation-cancellation receipt, or proof
that no reservation transaction installed; it cannot abandon a physical-domain
owner.

If at least one required child selector installed but parent confirmation did not,
the authority first constructs a receipt-free
`LogicalSessionGenerationPartialRetirementFact`. It binds a canonical complete
partition of required roles into installed child genesis/head/marker-consumption
entries and unused-marker plus typed-selector-nonmembership entries, typed
nonmembership of parent confirmation and every applicable plant-domain branch.
`PREPARE_PARTIAL_LOGICAL_SESSION_GENERATION_RETIREMENT` uses the bound authority
transaction domain to atomically compare the exact parent, complete child-
selector partition and, for plant control, the exact domain-registry
reservation/owner branch or typed reservation nonmembership. It is the only
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS ->
GENERATION_PARTIAL_RETIREMENT_PREPARED` edge. Its post-CAS
`LogicalSessionGenerationPartialRetirementPreparationReceipt` freezes that
partition. Every child genesis and parent confirmation requires the allocated-
pending head in a transaction under the same domain key. Therefore either child
genesis wins first and PREPARE rebases, or PREPARE wins and every stale child or
confirmation write loses at its commit point. The prepared phase is permanently
non-authorizing and has no edge back to allocated or live. Reservation and body-
genesis transactions use the same rule. Therefore reservation or body genesis
first makes a stale PREPARE lose and rebase, while PREPARE first makes their
delayed writes lose. A read of the parent before an independently committing
child or domain write does not meet this rule and cannot start plant genesis.

`BEGIN_PARTIAL_LOGICAL_SESSION_GENERATION_RETIREMENT` is then the only
`GENERATION_PARTIAL_RETIREMENT_PREPARED -> GENERATION_RETIRING` edge. It consumes
the exact preparation receipt and applicable plant-domain arbitration receipt,
moves the parent to retiring and tombstones every frozen unused marker. Installed
children then use their exact restrictive retirement/finalization paths; BEGIN
does not claim those later closures. For plant control its closed domain-
arbitration branch is `BODY_CHILD_ABSENT_RESERVATION_CANCELED |
BODY_CHILD_INSTALLED_RESERVED_PARTIAL_FENCED |
BODY_CHILD_INSTALLED_OWNED_RECONCILED`. The absent branch consumes the ADR-007
reservation-cancellation receipt with either exact cause. If the domain is still
reserved, the partial-parent/body-absent cancellation event must win; an earlier
all-children-absent cancellation can also remain valid if another child genesis
won before parent abort. Typed reservation nonmembership is legal only when no
reservation ever installed.
The reserved branch consumes the partial-retirement fence receipt. The owned
branch consumes exact domain confirmation and body reconciliation; if
confirmation won before PREPARE but reconciliation did not, the prepared phase
permits only that non-authorizing reconciliation before BEGIN. It remains HOLD/
FENCED and grants no live authority.

After BEGIN, an installed body child requires complete body retirement and
boundary closure, followed by exactly one domain branch:
`RELEASE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_AFTER_PARTIAL_BODY_RETIREMENT` when
the partial fence won, or normal
`BEGIN_ACTUATION_AUTHORITY_DOMAIN_OWNER_HANDOVER` when confirmation won. Thus a
lost reply or either race winner remains restrictive without becoming an
unbounded lineage sink.

The reserved-domain branch is not a direct release from genesis FENCED state.
Before the parent partial-retirement CAS, the same receipt-free partial-
retirement fact must win ADR-007
`FENCE_RESERVED_ACTUATION_AUTHORITY_DOMAIN_FOR_PARTIAL_BODY_RETIREMENT` and
produce `ActuationAuthorityDomainReservedPartialRetirementFenceReceipt`. The
parent CAS consumes that receipt. Domain confirmation competes on the same
reserved registry head: confirmation first selects reconcile-then-normal-
retirement, while the fence first makes stale confirmation impossible.
Readable physical-quiescence retirement or qualified lost-arbiter isolation must
first move the jurisdiction entry to ADR-007
`RESERVED_PARTIAL_RETIREMENT_RETIRED` and emit
`ActuationAuthorityDomainReservedPartialRetirementReceipt`. The body finalizer
consumes that receipt and matching exact-or-lost boundary closure. Only its
terminal body receipt can then release the reserved entry. This order makes body
closure and domain release jointly reachable without relabeling a live or lost
arbiter as unused.

The child finalizers, role-specific simulation or body closure, applicable
actuation-domain release or owner-handover closure, and the ADR-004 observer
server-authority cut plus complete durable pending-target root then let
`FINALIZE_LOGICAL_SESSION_GENERATION_IN_LINEAGE` install
`GENERATION_FINALIZED`. Remote observer distributed-authorization closure,
retained-transport quiescence and target publication are not parent-finalization
prerequisites. Old observer authority is exact-generation scoped, and each
pending realm-global target entry blocks only that target until its later
closure and publication. Its closed finalization branch is
`LIVE_CHILD_FINALIZED | CHILD_GENESIS_ABORTED |
PARTIAL_CHILD_GENESIS_RETIRED`; each branch requires and forbids its exact
evidence. The post-CAS `LogicalSessionGenerationFinalizationReceipt`
binds the prior/installed lineage heads, branch and complete closure-set root.
No successor allocation can race a writable predecessor, and two
`NO_PREDECESSOR_GENERATION` claims cannot race outside this selector.

Permanent source retirement has a closed preparation origin:
`NEVER_ALLOCATED_NAMESPACE | FINALIZED_SOURCE_GENERATION`. From
`NO_GENERATION`, `ALLOCATE_FIRST_LOGICAL_SESSION_GENERATION` and
`PREPARE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT` compete on the same
lineage-selector version. The never-allocated branch requires an empty retained-
generation set, no creation receipt or child selector, and an empty exact target-
key set. From `GENERATION_FINALIZED`, successor allocation and the same
preparation event likewise compete; the finalized branch requires the terminal
generation, finalization receipt and its complete retained ancestry. Allocation
moves directly to a fresh allocated-pending generation. Preparation moves to
`SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED`; whichever commit wins makes the
other lose.

Receipt-free `SourceLogicalSessionRetirementPreparationFact` binds the closed
origin, full namespace key, applicable terminal-generation/finalization evidence,
expected parent/namespace heads, and the stable canonical complete target-key and
immutable-ancestry set only. It does not preclassify a target as published or
sealed. It also binds the exact open source-issuance-index selector/head,
availability profile and proof that final freeze, sparse-proof retention and
root-specific closure reserves remain intact. It does not freeze or snapshot the
later index root/count; terminal retirement rereads them. For the
finalized-source branch, every target in that set must already
have passed exact ADR-004 parent-finalization reconciliation and therefore be
currently `SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION |
CHECKPOINT_PUBLISHED`; an earlier parent-retired/current-generation phase rejects.
It excludes the CAS condition, prepared successor and every post-commit
receipt. The prepared lineage candidate binds that fact and its authority-
transaction CAS condition. Post-commit
`SourceLogicalSessionRetirementPreparationReceipt` binds the fact, parent
selector identity, prior/prepared versions and heads, exact namespace/target
compare set, observed source-index selector/head/profile/reserve and
authority-transaction commit receipt. Prepared grants no
authority and has no allocation or return edge. Publication may still win after
preparation; terminal retirement rereads the same target key in the exact current
target-history selector and derives its final branch there.

For a finalized plant source, the preparation transaction also proves that its
physical domain is already unowned/retired or executes the exact ADR-007 no-
successor release/retirement branch from owner-handover state. The never-
allocated branch proves that no domain reservation ever existed. Neither branch
can strand a successor reservation or move a live/open domain. A store/domain
migration therefore cannot use source retirement to bypass physical isolation,
terminal body closure or the jurisdiction registry.

The realm owns one bounded
`ObserverUnresolvedTargetQuarantineHead` through one
`InstalledObserverUnresolvedTargetQuarantineSelector`. Its deterministic
`ObserverUnresolvedTargetQuarantineShardKey` derives from the authority-domain
key and a manifest-fixed shard index. Its closed root phase is
`OPEN_QUARANTINE | DOMAIN_RETIREMENT_SEALED`. Each exact
`(source namespace key, target key)` entry is
`SEALED_UNRESOLVED | ARCHIVED_NONAUTHORIZING_TOMBSTONE` and binds
the original source generation, last active target head, pending remote-
obligation inventory, source-retirement preparation and immutable authorization
policy. Neither state is a publication, closure or attach result. The selector,
shard count, entry/payload bytes and archive work participate in the same
authority-domain qualification and retirement budget. At cap, source retirement
uses its reserved quarantine capacity or triggers whole-domain drain; it never
drops an unresolved target.

`FINALIZE_SOURCE_LOGICAL_SESSION_PERMANENT_RETIREMENT` is the sole terminal
event. Receipt-free `SourceLogicalSessionPermanentRetirementFact` binds the exact
preparation receipt; authenticated cause; current complete target-key/head
partition; intended published/sealed tombstone projections and quarantine
entries; prior domain, lineage, namespace, target-history, quarantine and
source-issuance-index heads; exact
`ObserverGrantSourceIssuanceIndexFinalizationAssessment` and
`ObserverGrantSourceClosureAudienceAssessment`; intended frozen-index projection
with its exact retained root-admission registry, eligible-root audience subset
and pending/canceled terminalization partition; and the canonical complete
mutation/preservation inventory. Under
`SOURCE_RETIREMENT_OR_INDEPENDENT_CHALLENGE_EXPOSURE_ANCHOR`, it also binds the
preallocated identity and bounded retention/retry reserve for one minimized
cooperative anchor-retirement projection, its anchor-audience envelope, family,
pre-manifest, producer completion and delivery capsule. It excludes the CAS
condition, all candidate heads and every post-commit receipt. Each lineage,
namespace, target-history, quarantine and
`ObserverGrantSourceIssuanceIndexFinalizationCandidate` binds this fact and the
common CAS condition. The index candidate additionally binds its exact prior
selector/head, final sparse root/count/proof-node root, complete retained
root-admission registry root/count, eligible-root subset root/count,
pending-to-frozen/canceled-preserved bijection, capacity projection and
`SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED` result. No candidate binds another
candidate or receipt. The event's authority-domain transaction consumes that
fact and a canonical
complete `ObserverSourceTargetRetirementBranch` partition over every stable
observer target: `PUBLISHED | SEALED_UNRESOLVED`. The published branch binds its
existing exact publication receipt and changes that target entry to
`SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE`. The unresolved branch accepts
only a current
`SOURCE_GENERATION_FINALIZED_PENDING_CHECKPOINT_PUBLICATION` entry, executes subordinate
`SEAL_UNRESOLVED_OBSERVER_TARGETS`, removes no evidence, grants no closure, and
installs bounded `ObserverUnresolvedTargetQuarantineEntry` objects plus an
`ObserverUnresolvedTargetQuarantineCommitment` over the complete per-source
batch and prior/installed quarantine-shard roots. That commitment is a
`PostCandidateInstalledStateSidecar`: the authority-transaction receipt and
persistence manifest bind it, but the CAS condition and candidates do not.
Subordinate
`RECLAIM_SOURCE_OBSERVER_TARGET_HISTORY_DURING_PERMANENT_RETIREMENT` consumes the
same complete bijection and replaces every source-owned active target entry with
the applicable `SOURCE_PERMANENTLY_RETIRED_PUBLISHED_TOMBSTONE |
SOURCE_PERMANENTLY_RETIRED_SEALED_UNRESOLVED_TOMBSTONE` projection. It frees only
the active-map capacity whose evidence is now retained by the publication or
quarantine branch; each bounded permanent key tombstone remains. Checkpoint
publication and sealing compare the same realm-global target-history selector.
Publication first is reclassified as `PUBLISHED` by the terminal retry. Sealing
first makes the publication CAS lose forever.
The same atomic publication compares and mutates the target-history and
quarantine and source-index selectors, changes the index to
`SOURCE_ISSUANCE_FROZEN_PERMANENTLY_RETIRED` while preserving its complete
root-admission registry and eligible-root audience subset, changes the lineage
state to
`SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED`, and changes its namespace entry
from `LIVE_NAMESPACE` to `PERMANENTLY_RETIRED`.

The post-commit `SourceLogicalSessionRetirementReceipt` binds the terminal fact,
preparation,
closed origin, retired lineage-selector successor, namespace-registry successor,
complete published/sealed partition, quarantine commitment when applicable, and
`namespace_reuse_forbidden=true`. It also binds the prior/frozen source-index
selectors/heads, final root/count/proof-node root, finalization/audience
assessments, frozen root-admission registry, eligible-root audience,
pending/canceled terminalization partition and index commit receipt.
Post-commit `ObserverGrantSourceIssuanceNamespaceClosureReceipt` depends on the
common transaction and source-retirement receipts and binds the same installed
index coordinates; neither receipt appears in the fact or a candidate. The
crash-complete persistence manifest retains the complete selector-specific
receipt/sidecar set before any closure projection is exposed.
Under the independent-anchor profile, post-commit
`SourceLogicalSessionCooperativeAnchorRetirementProjection` binds the exact
source-retirement and frozen-index closure-receipt digests, retired
namespace/lineage selectors and tombstones, final source-index
selector/head/root, complete accepted-grant closure assessment, no-successor
result, anchor authority/selector incarnation, availability profile and
operation. It excludes target history, observer identities, private counters
and payloads. The source publishes it only through
`ProtectedSourceLogicalSessionCooperativeAnchorRetirementEnvelope`, one
source-owned family, the precommitted pre-manifest, mandatory producer
completion, selected delivery capsule and both scoped proofs under
`PERMANENT_CLOSURE_TOMBSTONE / INDEPENDENT_ANCHOR_AUTHORITY /
SOURCE_NAMESPACE_COOPERATIVE_RETIREMENT`. This projection authorizes only the
matching anchor's cooperative terminalization. It is not permanent-isolation,
Byzantine-containment, observer closure or release evidence. A missing delivery
leaves the anchor reservation charged; timeout cannot substitute.
`FINALIZED_SOURCE_GENERATION` requires the
exact terminal generation/finalization fields;
`NEVER_ALLOCATED_NAMESPACE` structurally forbids them and proves the empty
generation/target sets. The receipt attests that the same atomic commit already
performed the target-history reclamation. It authorizes only later non-
authoritative payload cleanup and realm/domain retirement; it cannot authorize
the state change that it proves. No
event allocates a successor, revives the namespace, changes a sealed target to
published, or moves the lineage to another transaction domain. Later exact
remote closure can create only `ObserverQuarantineLateClosureEvidence` through
`RECORD_QUARANTINED_OBSERVER_TARGET_LATE_CLOSURE` with
`ARCHIVE_ENRICHMENT_ONLY_NO_AUTHORITY`. This is an authenticated, content-
addressed, deduplicated append to the external evidence archive, not an authority-
domain transaction or selector mutation. It remains legal after domain
retirement because no authority object depends on it. It preserves every sealed
authorization field, active-history absence, publication status and namespace
tombstone. Exact
`ARCHIVE_AND_RECLAIM_OBSERVER_QUARANTINE_ENTRY` can replace the hot payload with
`ARCHIVED_NONAUTHORIZING_TOMBSTONE` only after independently verified immutable
archive persistence and only while the authority domain can still commit that
compaction. The tombstone retains the source/target key, sealed digest,
archive locator/digest and proof needed for permanent rejection. It does not
change the target to published or free the bounded tombstone key. Domain
retirement can perform the same archival compaction from unresolved state without
claiming late closure.

Each lineage carries one role-specific
`LogicalSessionGenerationInheritedCheckpointRoot`. The first allocation can use
`NO_PREDECESSOR_GENERATION` only from the original `NO_GENERATION` head with an
empty retained-generation set. Every successor creation fact instead binds the
exact predecessor checkpoint root and finalization receipt. Its observer-
authorization component is the ADR-004 complete server-cut/pending-target
checkpoint-fact root plus the exact observer-child and parent finalization
receipts for this simulation-service or plant-control source lineage. It does not
wait for per-target publication receipts; those mutate only the independent
realm-global target registry. There is no separate observer ADR-001 lineage.
An aborted generation with no installed child preserves the inherited root
byte-for-byte. A parent-unconfirmed partial generation also preserves it because
its observer child never became ACTIVE and could create no attachment target
entry. A live generation can replace it only with the complete role-specific
superseding checkpoint selected by that finalization. Thus an aborted or partial
generation cannot erase an older
`REATTACH_FORBIDDEN` result, and no later generation can claim
`NO_PREDECESSOR_GENERATION` again.

Loss or corruption of the lineage head/selector blocks new generation creation;
an empty head cannot be reconstructed. Resource bounds limit retained
generations and child markers. Exhaustion closes the logical session ID and does
not reuse a generation.

A simulation session:

- requires simulation configuration and returns mandatory
  `SimProvenance` with `is_simulation_output=true` and
  `calibrated_posterior=false`;
- grants only bounded simulation-operation authority issued by the simulation
  responder;
- has no plant profile, action authority lease, actuator route, or plant
  disposition meaning.

A simulation profile may explicitly declare a bounded imputation policy for a
missing model input or readout. The result must preserve the missingness and the
selected policy in simulation provenance. It remains
`is_simulation_output=true`, `calibrated_posterior=false`, and ineligible for
plant authority. A codec midpoint, zero, or range endpoint is a real numeric
value. It is not an implicit neutral value and cannot silently replace a missing
input in an Active plant command.

Its required child is one bounded `SimulationSessionStateHead` through
`InstalledSimulationSessionStateSelector`. Closed `SIMULATION_ROOT` is
`PENDING_PARENT_CONFIRMATION | ACTIVE | RETIRED_DRAIN_ONLY | TERMINAL`.
`SIMULATION_SESSION_STATE_GENESIS_FROM_GENERATION_CREATION` alone consumes the
matching ADR-001 creation receipt and simulation child marker. Its common
authority-domain transaction changes that exact parent-lineage marker from
`ALLOCATED` to `CONSUMED` while it installs the configured pending head and emits
`SimulationSessionGenerationGenesisReceipt`
after `RequiredGenerationChildMarkerConsumptionReceipt` for parent confirmation.
After the parent CAS,
`ACTIVATE_SIMULATION_SESSION_AFTER_PARENT_CONFIRMATION` consumes the exact
`LogicalSessionGenerationGenesisConfirmationReceipt`, verifies the installed
lineage is this generation in `GENERATION_LIVE`, and installs ACTIVE. The head binds the simulation configuration, responder
principal, bounded operation/job registry, output streams, resource grants,
source-local delivery/observer references and retained tombstones. ADR-004 remote
authorization and transport obligations remain in the separate observer child
and realm-global target registry. It contains no plant
profile, domain, lease, command or actuator field.

The simulation head alone owns bounded `SimulationJobRegistry`,
`SimulationOutputStreamRegistry`, `SimulationResourceGrantRegistry`,
`SimulationSourceLocalDeliveryRegistry` and
`SimulationSourceLocalObserverReferenceRegistry`. None has an independent
selector. Their closed member states are:

- `SimulationJobState`: `PENDING | RUNNING | TERMINAL`;
- `SimulationOutputStreamState`: `OPEN | TERMINAL`;
- `SimulationResourceGrantState`: `LIVE | TERMINAL`;
- `SimulationSourceLocalDeliveryState`: `LIVE | TERMINAL`; and
- `SimulationSourceLocalObserverReferenceState`: `LIVE | TERMINAL`.

Closed `SimulationSessionSubresourceEventKind` is exactly:

`CREATE_SIMULATION_JOB |
START_SIMULATION_JOB |
RECORD_SIMULATION_JOB_PROGRESS |
TERMINALIZE_SIMULATION_JOB |
OPEN_SIMULATION_OUTPUT_STREAM |
APPEND_SIMULATION_OUTPUT_STREAM_ITEM |
TERMINALIZE_SIMULATION_OUTPUT_STREAM |
ISSUE_SIMULATION_RESOURCE_GRANT |
CONSUME_SIMULATION_RESOURCE_GRANT_QUOTA |
TERMINALIZE_SIMULATION_RESOURCE_GRANT |
CREATE_SIMULATION_SOURCE_LOCAL_DELIVERY |
ADVANCE_SIMULATION_SOURCE_LOCAL_DELIVERY |
TERMINALIZE_SIMULATION_SOURCE_LOCAL_DELIVERY |
REGISTER_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE |
TERMINALIZE_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE`.

An unknown, unset or default event value rejects before registry lookup or
semantic allocation. It is not an alias for creation, replay or terminalization.

Its complete reachability relation is:

| Event | Required prior member | Installed member |
|---|---|---|
| `CREATE_SIMULATION_JOB` | typed never-used key nonmembership | `PENDING` job |
| `START_SIMULATION_JOB` | `PENDING` job | `RUNNING` job |
| `RECORD_SIMULATION_JOB_PROGRESS` | `RUNNING` job | checked-next `RUNNING` job |
| `TERMINALIZE_SIMULATION_JOB` | `PENDING` or `RUNNING` job | `TERMINAL` job |
| `OPEN_SIMULATION_OUTPUT_STREAM` | typed never-used key nonmembership | `OPEN` stream |
| `APPEND_SIMULATION_OUTPUT_STREAM_ITEM` | `OPEN` stream | checked-next `OPEN` stream |
| `TERMINALIZE_SIMULATION_OUTPUT_STREAM` | `OPEN` stream | `TERMINAL` stream |
| `ISSUE_SIMULATION_RESOURCE_GRANT` | typed never-used key nonmembership | `LIVE` grant |
| `CONSUME_SIMULATION_RESOURCE_GRANT_QUOTA` | `LIVE` grant with positive remainder | checked-next `LIVE` grant |
| `TERMINALIZE_SIMULATION_RESOURCE_GRANT` | `LIVE` grant | `TERMINAL` grant |
| `CREATE_SIMULATION_SOURCE_LOCAL_DELIVERY` | typed never-used key nonmembership | `LIVE` delivery |
| `ADVANCE_SIMULATION_SOURCE_LOCAL_DELIVERY` | `LIVE` delivery | checked-next `LIVE` delivery |
| `TERMINALIZE_SIMULATION_SOURCE_LOCAL_DELIVERY` | `LIVE` delivery | `TERMINAL` delivery |
| `REGISTER_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE` | typed never-used key nonmembership | `LIVE` observer reference |
| `TERMINALIZE_SIMULATION_SOURCE_LOCAL_OBSERVER_REFERENCE` | `LIVE` observer reference | `TERMINAL` observer reference |

No other member edge exists. A quota consumption that reaches zero uses the
grant-terminal event and includes that final consumption; it cannot install a
zero-remainder LIVE grant. Changing immutable job, stream, grant, delivery or
observer-reference identity requires terminalizing the old member and allocating
a fresh never-used key. A terminal member never reopens or disappears.

Each event has one receipt-free closed branch of
`SimulationSessionSubresourceMutationFact` and one receipt-free
`SimulationSessionSubresourceCandidate`. The fact binds exact event and
operation/idempotency identity, subresource type/key, prior membership proof and
state, immutable payload/configuration digest, dependency keys, authorizing
simulation-responder principal and bounded simulation grant, expected simulation
root/head/version, applicable parent-currentness evidence, common
authority-domain qualification, checked counters/reserve delta and intended
root-member state. A nonterminal fact binds typed-empty terminal-cascade state; a
terminal fact binds the exact
`SimulationSessionSubresourceTerminalCascade` defined below.
Parent-currentness evidence is exactly the parent LIVE head for an ACTIVE
mutation or the frozen parent-retirement head/evidence for restrictive
drain-only terminalization. It excludes the candidate, condition and every
current-or-later receipt or manifest. The candidate binds the fact, condition and
the same typed-empty-or-exact terminal-cascade digest; it excludes all receipts
and manifests.

The condition compares the sole
`InstalledSimulationSessionStateSelector`, exact expected simulation head and
parent selector in the same authority-domain transaction. Widening/self-mutation
requires ACTIVE plus parent `GENERATION_LIVE`. Restrictive terminalization in
drain-only instead compares the exact parent-retirement head/evidence frozen by
`RETIRE_SIMULATION_SESSION_GENERATION`. As the only subresource-bearing write
selector, the winning CAS advances the simulation selector/head, its embedded
exact registry member set and bounded
`SimulationSessionSubresourceOperationIndex`. The mandatory
`InstalledAuthorityTransactionDomainSelector` advances its checked transaction
commit position under the common rule; the parent selector is an exact read-only
currentness participant. A registry value, map write, output append, quota
decrement or progress update outside that CAS is non-authoritative. There is no
subresource selector, post-read repair or split-commit exception.

Creation, START, progress, append, quota consumption, delivery advance and
observer registration require ACTIVE. Terminal events are legal in ACTIVE or
`RETIRED_DRAIN_ONLY`; the latter permits only exact replay/query and restrictive
terminalization. Stream appends bind a checked-next sequence and mandatory
`SimProvenance` with `is_simulation_output=true` and
`calibrated_posterior=false`. Grant facts bind finite operation classes, quota
and deadline and structurally exclude every plant role, route, lease, token or
authority. Progress and delivery-advance facts bind a checked-next sequence;
quota consumption binds a positive decrement no larger than the prior
remainder. Every dependency key resolves in the same expected simulation head to
the required nonterminal member state. Cross-session, absent, terminal or
caller-invented dependencies reject. The qualification fixes allowed
resource-class dependency edges; insertion of an edge that makes a cycle
rejects. A member's dependency set is immutable, and its reverse-dependent index
is a canonical derivation in the same simulation head. Delivery and
observer-reference facts bind their exact local dependency; terminal local state
makes no ADR-004 remote publication, transport-quiescence or authorization-
closure claim.

Closed `SimulationSessionSubresourceTerminalCause` is
`JOB_COMPLETED | JOB_FAILED | JOB_CANCELED |
STREAM_CLOSED |
GRANT_EXHAUSTED | GRANT_EXPIRED | GRANT_REVOKED |
DELIVERY_COMPLETED | DELIVERY_FAILED | DELIVERY_CANCELED |
OBSERVER_REFERENCE_RELEASED | SESSION_RETIREMENT`.
The immutable `SimulationSessionSubresourceTerminalCausePolicy` maps the
event's exact authenticated reason evidence to one unique direct-root cause.
The caller does not select a cause enum. In ACTIVE, the direct root uses only a
resource-class cause. In drain-only, every newly terminalized member uses
`SESSION_RETIREMENT`. `JOB_COMPLETED` requires prior RUNNING; a prior PENDING job
can only cancel or retire.

Receipt-free `SimulationSessionSubresourceTerminalCascade` binds the initiating
terminal event, expected simulation head/version, initiating resource and one
canonical ordered vector of
`SimulationSessionSubresourceTerminalCascadeEntry`. An entry binds resource
class/key, exact prior member bytes/state and dependency set, derived terminal
cause and exact receipt-free installed tombstone. The vector is exactly the
initiating member plus every nonterminal member transitively dependent on it in
the installed dependency DAG. It contains no terminal, unrelated, duplicate or
caller-added member. It uses the lexicographically least reverse-topological
order under canonical `(resource_class, resource_key)` bytes. Thus every valid
graph has one encoding and dependents precede their prerequisites.

For an ACTIVE cascade, the root cause comes from the installed cause policy.
Every other entry uses the fixed resource-class mapping
`job -> JOB_CANCELED`,
`stream -> STREAM_CLOSED`,
`grant -> GRANT_REVOKED`,
`delivery -> DELIVERY_CANCELED` and
`observer reference -> OBSERVER_REFERENCE_RELEASED`.
For a drain-only cascade, every entry instead uses `SESSION_RETIREMENT`.
The terminal fact and candidate bind this exact cascade; the installed simulation
head's operation-index entry binds its digest and installs every named tombstone,
and the specialized receipt binds the same cascade and complete prior/installed
member set. A stream or grant therefore cannot terminalize while leaving a LIVE
transitive dependent, and a dependent cannot be smuggled into an unrelated
terminal operation. Unknown cause, omitted/extra dependent, wrong cause or
canonical order, caller-supplied current state, cycle or default enum value
rejects before CAS.

The generic `AuthorityTransactionCommitReceipt` precedes one
`SimulationSessionSubresourceCommitReceipt`, which binds the exact event/fact,
prior and installed simulation heads, exact terminal cascade or typed-empty
value, complete registry/dependency mutation, operation-index entry, checked
counters and generic commit. Final non-authorizing
`AuthorityTransactionPersistenceManifest` binds the complete generic/specialized
receipt and sidecar set. `SimulationSessionSubresourcePersistenceManifest` then
binds that manifest and exact bundle last; no state or output is exposed before it
is durable. The operation index maps the never-reused
`SimulationSessionSubresourceOperationKey`, exactly
`(AuthorityTransactionDomainKey, SessionRef, operation_id)`, to the exact fact
digest, event, resource key and checked commit position. The retained durable
bundle at that position supplies the receipt and manifests without making a
candidate bind its future receipt. Exact reply-loss replay returns that
receipt/manifest without a second mutation. Changed event, bytes, key,
dependency, sequence, quota or terminal cause under the same operation identity
rejects. A crash before CAS preserves the prior bundle. A crash after CAS but
before either manifest completes the one deterministic durable bundle without
exposure; it never retries the semantic mutation.

Qualification fixes per-registry member/byte limits, fact/candidate/receipt
bounds, work, stream items/bytes, job progress count, grant quota, delivery
advances, operation-index retention and commit-position width. Simulation-child
genesis reserves the fixed retirement/finalization bundles and base closure
partition. Each new member then reserves its maximum terminal operation-index
entry, receipt, tombstone and incremental retirement-partition cost before
insertion.
Qualification also fixes a maximum terminal dependency-cascade member/byte
count. Creating a member or dependency edge proves that every terminal cascade
reachable in the resulting DAG and its retirement-partition contribution fit
both that bound and the retained restrictive reserve; otherwise creation rejects.
Checked arithmetic never wraps, and terminal tombstones/operation identities or
restrictive reserve are not evicted or borrowed to admit work. Equality at a
bound passes; cap-plus-one rejects before mutation. Pending-parent state grants
no subresource or output authority. TERMINAL permits exact retained query/replay
only; it admits no mutation or identity reuse.

`RETIRE_SIMULATION_SESSION_GENERATION` moves pending-parent or ACTIVE to
drain-only. Its closed `SimulationSessionRetirementParentEvidence` is
`PARTIAL_PARENT_GENESIS |
CONFIRMED_PARENT_BEFORE_SIMULATION_ACTIVATION | ACTIVE_PARENT_RETIREMENT`.
The partial branch consumes the exact parent partial-retirement fact/receipt.
The confirmed-before-activation branch consumes both the parent confirmation and
the later parent-retirement receipt. The ACTIVE branch consumes the exact parent
retirement receipt. Every branch compares the parent, simulation child and
domain-state selectors in one authority-domain condition. A confirmation or
parent-retirement transition that wins first changes the expected parent head;
the losing child transition must reselect the matching evidence branch. Thus no
commit can leave a live parent with a retired required simulation child.

The winning retirement closes widening admission and installs one
`SimulationSessionSubresourceRetirementPartition`: a canonical bijection to every
job, stream, grant, delivery and source-local observer-reference member in the
same simulation head, plus a canonical commitment to every prior operation-index
entry. It freezes each member's prior state and exact dependent set, and each
indexed operation's exact retained-result locator, without dropping or inventing
either class. Drain-only terminal events update this partition, the operation
index and the embedded registries in the same simulation-selector CAS.
It does not wait for ADR-004 remote target publication.
Exact
`FINALIZE_SIMULATION_SESSION_GENERATION` alone installs TERMINAL after the
complete partition covers every registry member, every covered member is
terminal, every indexed operation has its retained exact result and all terminal
tombstones fit the reserved bounds. It emits
`SimulationSessionGenerationFinalizationReceipt`. Parent lineage retirement and
finalization consume those exact receipts. The partial-parent-genesis path uses
the same restrictive child retirement; a random empty simulation head or missing
selector cannot substitute. These names and the complete closure partition are
B03 allocations, not claims that simulation results are valid or calibrated.

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

The parent lineage is
`NO_GENERATION -> GENERATION_ALLOCATED_PENDING_CHILD_GENESIS ->
GENERATION_LIVE -> GENERATION_RETIRING -> GENERATION_FINALIZED` for a confirmed
generation. A partial generation instead takes
`GENERATION_ALLOCATED_PENDING_CHILD_GENESIS ->
GENERATION_PARTIAL_RETIREMENT_PREPARED -> GENERATION_RETIRING ->
GENERATION_FINALIZED`. Only `GENERATION_FINALIZED`
can allocate one successor, which re-enters the allocated-pending branch with a
fresh UUID, or instead enter
`SOURCE_LOGICAL_SESSION_RETIREMENT_PREPARED ->
SOURCE_LOGICAL_SESSION_PERMANENTLY_RETIRED`. The successor and retirement-
preparation edges race on the same exact head; the terminal source branch has no
exit. Original `NO_GENERATION` can also enter that retirement pair instead of
allocating its first generation. Child-genesis failure remains in the allocated-pending branch
for exact recovery or authenticated retirement; it cannot return to empty.

## Bounds and resource behavior

Each request has an exact byte, member, string, collection, channel, extension,
and allocation bound before semantic allocation. Simulation network/stimulus
bounds and plant channel/profile bounds are separate. Enabling both roles does
not merge their quotas or permit one role to starve the other's safety path.
Each authority transaction domain also has immutable maximum selector-
participant and durable-bundle byte counts. The provider checks those bounds
before it constructs a generation fact. Exhaustion or a required selector
outside the domain rejects creation or keeps the existing generation
non-authorizing; it cannot silently drop a compare condition.
For a plant-capable domain, the manifest reserves transaction, log, storage and
scheduler capacity for fencing, watchdog, ESTOP reconciliation, retirement and
recovery. Observer and simulation quotas cannot consume that reserve. An observer
transaction performs only its bounded local compare/mutation and never remains
open across signing, network, boundary I/O or remote closure. Overload rejects or
delays non-control work before it can starve a safety transition. These are
provider qualification requirements, not evidence that this candidate has passed
them.

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
- One logical session/kind has at most one allocated or writable generation.
- First and successor generation creation consume the installed parent lineage
  selector; a child-local selector or random UUID cannot publish a generation.
- Every required-child genesis atomically installs the mapped child, changes its
  exact embedded parent marker `ALLOCATED -> CONSUMED` and advances the mandatory
  domain selector. Neither half can exist alone, and confirmation consumes the
  complete marker/child-receipt bijection.
- Successor allocation requires exact predecessor finalization and every
  role-specific closure checkpoint. Generation loss never recreates empty state.
- Successor allocation and permanent source retirement have one order on the
  finalized lineage head. Permanent retirement atomically installs the namespace
  tombstone and complete published-or-sealed target partition; neither the text
  logical ID nor an unresolved remote observer can revive it.
- Source namespace allocation is the sole absent-to-pending edge under the
  source-retirement-only profile. Under the independent-anchor profile, source
  intent is the sole absent-to-pending edge. A committed source intent must
  precede the non-borrowable anchor-capacity reservation, and its verified
  protected return must precede allocation. Intent cancellation and allocation
  compare the same source registry selector. Anchor reservation and
  intent-cancellation import compare the same owner lifetime slot and
  coordinate indexes. Either order reaches one retained anchor terminal, and a
  canceled intent can never allocate. Allocation, anchor genesis, source
  registration and later cancellation preserve that exact intent/reservation
  ancestry. Registration and pending-allocation cancellation compare the same
  source registry selector. Registration installs the preallocated
  lineage/index exactly once. Cancellation installs a permanent never-activated
  tombstone. Every delivery order either reaches one LIVE source/anchor bundle
  or leaves only bounded nonauthorizing evidence.
  Protected cancellation import and anchor genesis compare the same
  preallocated anchor selector and reservation entry. Either order installs the
  same permanent anchor terminal state. Missing reservation return prevents
  source allocation. Missing cancellation evidence retains a bounded
  nonauthorizing reservation or orphan. No timeout or anchor receipt can revive
  or infer cancellation of an allocation.
- A plant generation binds exactly one enrolled actuation-authority domain. The
  jurisdiction-global registry serializes every reservation against the complete enrolled
  conflict neighborhood; profile-selected names cannot bypass physical overlap.
- Every claimed parent/child/domain/security race has one commit order through
  the generation's qualified authority transaction domain. A separately sampled
  current head cannot satisfy a conditional compare.
- Higher enrollment genesis, reservation, target-store domain genesis/cancel,
  higher confirmation and local activation form two explicit CAS lineages. Every
  target bootstrap uses the same qualified domain selector, typed absence,
  one-use marker and consumption key; each outcome has generic and specialized
  receipts plus final manifests. Every crash/reply-loss interleaving returns that
  bundle or has a permanent restrictive exit; no remote absence read creates or
  cancels a realm.
- Every authority-bearing cross-store hop has one protected, crash-complete
  source export and exact target audience. Signature/key-use, manifest and key
  history, source lineage, replay scope and verified transport principal all
  validate before the target CAS. A bare inner receipt, ADR-009 artifact,
  unmanifested export or right receipt for the wrong consumer event grants
  nothing.
- Authority-transaction content is acyclic: prior facts/evidence and pre-CAS
  commitments precede the condition; candidates precede declared post-candidate
  sidecars; the transaction receipt precedes specialized receipts and the final
  persistence manifest. Ordinary and self participant admissions cannot bind a
  candidate back into an earlier commitment.
- Unconfirmed cancellation and confirmed finalization atomically terminalize the
  domain-self and exact-present core entries. Confirmed finalization seals the
  namespace/target/quarantine roots and never waits for facility release. A lost
  domain-self cannot self-finalize.
- Unrecoverable domain-selector, required closure-graph or store-atomicity state
  can retire a realm only through the higher root. Preparation freezes every
  higher-issued physical-jurisdiction authorization. Each facility selector then
  permanently fences the realm and resolves its exact raced slot/epoch set before
  the higher cut, full immutable-envelope isolation and no-resume horizon. This
  path claims no missing local semantic closure.
- The higher root first installs one globally unique
  `PENDING_FACILITY_CAPACITY` identity and reserves its AUTHORIZE-or-CANCEL
  terminal outcome. This requires the reciprocal facility-selected higher-
  registry reserve and per-realm pending envelope. Facility HELD consumes its
  protected receipt. Intent abort and
  facility reserve can commit in either order because the facility release
  installs a no-capacity abort tombstone or closes the matching held entry.
- A higher physical-jurisdiction authorization cannot exist without consuming
  one exact facility-issued capacity reservation. That reservation precharges
  the larger consumed/unused terminal outcome, its isolation member and its
  contribution to a complete per-realm fence transaction. Exact global cap fits;
  cap-plus-one and aggregate multi-realm oversubscription cannot emit a receipt.
- A higher authorization alone grants no facility or hardware authority.
  Facility PREPARE either atomically consumes the matching held capacity entry
  and records the authorization identity, or loses to preauthorization release,
  an exact unused tombstone, realm fence or facility retirement. The higher map
  confirms consumption or consumes exact normal/unused/terminal closure
  evidence. Normal realm retirement has no pending cancellation, issued or
  consumed entry.
- Lost-domain isolation always freezes and partitions the complete higher
  authorization set. An active facility emits its full-set fence receipt. A
  retired facility instead proves the same complete set against its terminal
  retained inventory. If the facility selector is lost, independently qualified
  evidence uses an authenticated final-high-water/no-successor root or the
  unknown-root branch, partitions all immutable inventory `U` into disjoint
  components, retires the full possible hardware/facility identity set and
  proves a no-resume barrier. Its earlier local-set retirement receipt cannot
  substitute.
- The higher isolation-cut CAS is the sole writer of
  `FACILITY_REALM_FENCED`. It consumes a total projection fact, installs the
  projected map, and emits the generic commit, projection and cut receipts in
  that order. No facility receipt or local claim can write the higher entry.
- A facility-authority lost-realm slot retirement depends on the higher
  preparation and frozen full set, not the later cut or realm tombstone.
  Therefore the facility full-set fence and the higher cut have an acyclic
  dependency order.
- A remote observer boundary cannot block source successor allocation or
  actuation-domain handover after the exact observer server cut and complete
  pending-target root. Before permanent source retirement, its stable target
  remains attach-blocked until distributed authorization closure, transport
  quiescence and publication all complete. A target sealed by permanent source
  retirement is instead permanently non-authorizing and nonpublishing; later
  archive evidence cannot reopen it.
- Allocated-pending state has a total restrictive exit: pre-child abort or
  installed-child partial retirement. Neither branch erases an inherited
  checkpoint or abandons a reserved physical domain.
- Simulation activation, parent confirmation/retirement and simulation-child
  retirement have one common order. The closed parent-evidence branch must match
  the installed parent head; no trace can retain `GENERATION_LIVE` beside a
  retired required simulation child.
- The closed simulation subresource event union reaches all 11 declared member
  states and no others. Every creation, self-mutation and terminal edge advances
  the sole simulation selector with exact applicable parent currentness: LIVE
  for ACTIVE work and the frozen parent-retirement head/evidence for drain-only
  terminalization. Drain-only admits only replay/query and terminal closure;
  finalization consumes the complete terminal partition. No registry-local write
  or split CAS has authority.

A bounded model shall include unknown kinds, cross-kind frame injection, same
logical session ID with distinct generations, two first-generation allocators,
predecessor-finalization versus successor-allocation races, lost child-genesis
reply, pre-child abort versus child genesis, partial genesis versus confirmation,
simulation activation/retirement versus parent confirmation/retirement,
partial PREPARE versus every child genesis and delayed domain reservation, domain
confirmation versus reserved-partial fence, observer-only partial genesis with a
body-absent reservation cancellation,
overlapping-domain reservations under different keys, checkpoint carry across an
aborted generation, restart, lineage-state loss, and dual-role deployment. It
shall also mutate the transaction-domain key on each participant, commit a stale
reservation or child genesis after PREPARE, inject write skew through a pre-read,
exceed the participant and byte bounds by one, and crash before and after the
single atomic publication. Each mutation must reject or recover the one installed
bundle; none can produce a frozen partition plus an unrecorded child or domain
owner. Simulation-subresource reachability tests visit every declared table edge
and all 11 states, then inject unknown event/state/cause values, wrong-prior
edges, missing or duplicate registry keys, omitted dependencies, zero-remainder
LIVE grants, reopened tombstones, sequence/quota overflow, reply loss and
cap-plus-one. Cascade mutants omit or add a transitive dependent, reorder the
canonical vector, use a caller-selected/wrong-class cause, replace a drain cause
with a non-retirement cause, insert a dependency cycle, or bind different
cascade digests in fact/candidate/head/receipt. Split-CAS mutants write a
registry without the simulation head, advance simulation without applicable
parent currentness, divide dependent terminalization across commits or omit one
retirement-partition member. All reject or recover the single installed bundle.
Participant mutants re-register the same selector under a different role,
ACL or owner; use a candidate before admission commits; re-admit a terminal
tombstone; run fresh selector genesis without the domain-state CAS; and import an
ADR-007 or ADR-009 selector without its exact native genesis receipt. Required-
child-genesis mutants install a child without consuming its marker, consume a
marker without installing the child, swap roles/events, omit the parent or
domain selector, reuse a tombstoned marker, or replay changed child bytes. All
reject.
Bootstrap
tests cover higher-registry genesis replay/sibling creation, target-store genesis
versus pre-genesis cancellation on the shared selector/marker, higher confirmation
versus reserved retirement/
external cut, higher intent PREPARE/abort versus facility capacity reserve/
release and normal realm retirement in every cross-store order, higher
authorization versus facility PREPARE,
explicit unused cancellation, facility-realm fencing and healthy facility
retirement, terminal-facility nonmembership before and after late higher
authorization, and same-realm re-enrollment. Capacity vectors require exact cap
success, cap-plus-one rejection, checked-add overflow rejection, exact retry
without a second charge, and interleaved reservations for multiple realms whose
aggregate would oversubscribe one facility. Full-set mutants substitute a
facility-retirement local-set receipt for a lost-domain higher-set proof, omit
one late authorization or capacity key, and mismatch one consumed slot; all
reject. Additional mutants let a facility receipt write
`FACILITY_REALM_FENCED`, omit the projection receipt, reverse the generic-commit/
projection/cut receipt DAG, or require the higher cut before facility-authority
lost-realm slot retirement. Lost-facility mutants omit one possible component,
complement edge, old identity, credential or no-resume barrier; claim an exact
last root without authenticated final high-water/no-successor; overlap two
components; or make their union smaller or larger than `U`. All reject.
Reciprocal-enrollment tests duplicate or redirect a higher lineage, let either
root self-write the other's reserve, race higher INSTALL and facility CONFIRM
against unconfirmed cancellation in every order, insert an intent before both
confirmations, exceed the per-realm count, race drain against insertion, reuse a retired
enrollment, and compose unresolved higher pending, local retained and explicit
empty-root costs at exact fence cap and cap-plus-one. Cross-store mutants pass a
bare receipt or unmanifested envelope, change audience/event, signer/key use,
manifest/key history, source lineage, replay scope or verified transport
principal, and replay each exactly-once artifact. All reject before target
mutation.
Bootstrap mutants omit cancellation's installed selector/generic commit, split
the genesis/cancel key or marker, omit a branch-final manifest, reset a terminal
selector, swap any foundational concrete discriminant or reverse its source/
audience. All reject without consuming a second marker.
Local activation versus unconfirmed cancellation, lost confirmation
reply, exact deadline equality, checked horizon overflow and clock restart are
also covered.
Digest mutants make either the self-admission or ordinary participant-admission
commitment bind its candidate and must fail DAG-cycle validation. Closure mutants
leave the self/core entries active, demand unavailable lost-selector currentness,
or let a store self-attest retirement after losing atomicity. All reject. A
positive lost-core trace uses the full-envelope higher-root path and never invents
a namespace/source tombstone.
Plant-capable tests also saturate observer transactions, logs and storage
while fencing, watchdog, ESTOP reconciliation and retirement consume their
reserved capacity. They suspend signing and remote observer I/O and prove that no
authority transaction remains held across either wait. Namespace tests race
successor allocation with permanent-retirement preparation, publication with
unresolved sealing, parent-finalization reconciliation with preparation, and
same-text-ID registration after the tombstone. Preparation from
`SOURCE_AUTHORIZATION_RETIRED_PENDING_PARENT_FINALIZATION` rejects. One
positive trace prepares with an unresolved target, lets publication win, and
then successfully derives the published branch at terminal retirement. Its dual
lets sealing win and proves that stale publication loses. Tests fill
the source-key map and transaction position to cap and cap-plus-one, enlarge each
closure-obligation class, and crash at every domain/source retirement commit.
Only a new stable realm key after the old domain tombstone can admit the same text
ID; no test resets a counter or drops retained membership proof material. A
consumer mutant keys only by text ID and attempts to merge or reattach old- and
new-realm histories while old bytes can still drain; it must reject the missing
full realm/kind/generation identity.

## Migration

The immutable wire-0.8 history remains unchanged. The current overloaded
candidate request becomes unsupported development input after explicit B02
rebaseline authorization. Engram migrates its responder and commander adapters
separately. Crebain implements only plant-control types. Gateways terminate trust,
label source and target identity, and reject ambiguous mappings.

A new stable realm is a hard logical-source discontinuity even when it reuses the
same textual logical-session ID. Consumers key state, caches, dispositions,
observer history and provenance by the full `(AuthorityRealmKey, session_kind,
logical_session_id, generation)` identity. No continuity, reattachment,
non-overlap or inherited-policy claim crosses realms. A bounded old observer
boundary can still drain previously authorized old-realm bytes while the new
realm exists. A deployment policy that requires zero overlap must wait for exact
old distributed closure/transport quiescence or forbid new-realm textual-ID
reuse; realm retirement alone does not claim that drain.

## Operational recovery

Restart restores only the matching typed state store. If state kind, generation,
contract identity, or security state is uncertain, use the exact pre-child abort
or child retirement/finalization path. A fresh generation is legal only after
the parent lineage consumes that closure; a plant successor additionally requires
the exact domain release/handover lineage. A recovered simulation service cannot restore a plant
lease; a recovered plant session cannot infer simulation state.
Loss or ambiguity of the authority-domain selector, namespace registry,
qualification or retained proof material blocks every widening transition and
new registration. Recovery restores the exact installed bundle or completes the
qualified physical-isolation and permanent-domain-retirement response; it never
replays genesis, changes the realm key or resets the commit position.

## Compatibility and rollback

This is a pre-release breaking correction and requires a new candidate identity
after B02 authorization. Rollback is to the last pushed release-blocked candidate
and its consumer pins, never to a mixed message contract. Released `v0.8.0`
artifacts remain immutable.

## Open questions

<a id="ncp-b01-selector-allocation-adr-001-v1"></a>

No open question can change the simulation/plant separation or the fail-closed lineage decision.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: one kind has one session meaning.
2. Security: credentials and routes are non-fungible across kinds.
3. Safety: only the plant body grants action; protocol success is not physical
   safety.
4. Lifecycle: cross-kind transition and implicit recovery are impossible.
5. Resources: simulation and plant budgets remain independently finite.
6. Migration: 0.8 and the old RC terminate explicitly.
7. Science: simulation output remains uncalibrated, advisory, and labeled.
8. Operations: dual-role deployments expose separate endpoints and diagnostics.
9. Evidence: cross-kind negative vectors and independent live roles are required.
10. Governance: NCP owns generic session types; consumers own optional adapters.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes. Model advice is non-evidence.
