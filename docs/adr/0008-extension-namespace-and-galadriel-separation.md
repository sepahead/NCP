# ADR-008 — Separate stable routes from Galadriel extensions

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: protocol reviewer, Galadriel owner, Haldir owner, Crebain
  owner

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

ADR-001 `AuthorityRealmKey` is the canonical tuple of server authority principal
and stable realm ID. Its canonical value excludes rotating security epochs,
registry or transaction-store incarnations, process incarnations, and every
session, detector, policy, stream, or publication generation. The `{realm}`
route component is only the canonical route projection of the stable realm ID.
It does not carry the server-authority-principal member and cannot authorize a
realm by itself.

The content-addressed extension contract can be realm-independent. An installed
extension activation is realm-scoped. Its default-deny manifest entry, audience,
route grant, producer and consumer enrollment, replay partition, QoS binding,
and retention policy directly bind one exact `AuthorityRealmKey`. A manifest
cannot grant a wildcard, default, inherited, or caller-selected realm. The same
extension ID and contract digest installed in two realms creates two distinct
runtime authority and evidence domains.

Every realm-scoped request, envelope, frame, portable reference, transfer,
source-authority tuple, key, head, selector, fact, commitment, reservation,
outbox item, queue item, attempt, deadline evaluation, disposition, provenance
object, query result, and pre- or post-CAS receipt named in this ADR carries
`authority_realm_key: AuthorityRealmKey` as a direct canonical member. Its
canonical bytes and digest include that member. This requirement applies even
when the object also binds a realm-bearing parent. Portable validation cannot
infer the realm from a route, endpoint, certificate, manifest name, descriptor,
session/generation, parent head, attachment container, or another receipt. A
canonical projection that drops or changes the realm is invalid.

The required direct member includes these four classes:

- Galadriel lifecycle lane/snapshot/lineage/currentness/boundary/span state and
  every assessment candidate, publication record, reservation, release outbox,
  queue transition, transport gate/attempt/disposition, retirement fact, and
  associated receipt;
- Haldir assessment-receiver admission/replay/currentness/disposition state and
  every policy-ingress, profile-selection, evaluation barrier/result,
  permission-preserving proof, policy-head transition, retirement fact, and
  associated receipt;
- Haldir intent-freshness, protected-source admission, policy decision,
  commander preflight, policy release, local outbox, transport
  gate/attempt/disposition, publication feedback/history, retirement/closure
  state, and associated receipt; and
- every protected extension envelope, `NormativeSourceRef`,
  `ProtectedOriginTransfer`, `TrustedProjectionRecord`,
  `TrustedProjectionProvenance`, source-capture mapping, attachment manifest,
  audience/routing record, and consumer-facing evidence projection used by those
  classes.

Realm-independent value types are limited to contract/schema identities,
cryptographic algorithm/domain identifiers, exact Galadriel release-suite and
assessment-binding identities, raw vector/receipt content digests, closed enum
definitions, and other values whose schema explicitly says that they have no
runtime realm scope. Nesting one of those values in a realm-scoped object does
not remove that object's direct realm requirement.

The raw Galadriel receipt and vector bytes remain exact source artifacts; NCP
does not rewrite their source schema to manufacture a realm field. Their
protected NCP attachment manifest, lifecycle mapping, admission, publication,
and every portable reference to them are realm-scoped objects and carry the
direct realm plus the exact source-byte digest and length. Thus source fidelity
does not create a realm-dropping runtime projection.

Before semantic allocation, each receiver requires exact realm equality across
authenticated ingress, installed default-deny manifest, audience, literal route
projection, protected envelope, session descriptor/transcript, declaration,
source reference/transfer, owning selector, and every retained predecessor.
Missing, unknown, default, wildcard, retired, or mismatched realm data creates no
replay reservation, lifecycle update, policy evaluation, publication
reservation, callback, or side effect.

Portable consumers key every session-derived cache, replay lineage, evidence
graph, policy correlation, and capture join by
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` before any
stream, source, or operation key. Equal principal, session, generation,
incarnation, sequence, digest, and protected bytes in different realms are
distinct facts. They cannot merge, deduplicate, resume, inherit a decision,
close an obligation, or satisfy one another's provenance chain.
The tuple is serialized once: the object's direct `authority_realm_key` is its
first member and the three session coordinates complete it. References below to
the direct realm and complete session foreign key do not permit two divergent
realm values; any compatibility duplicate must compare exactly or reject.

Galadriel uses two distinct optional surfaces:

1. a read-only NCP observer under ADR-004 for standard NCP observations and
   dispositions; and
2. separately credentialed extension producers/consumers for Galadriel-owned
   evidence.

The Galadriel-to-Haldir assessment extension is default-off and push-only. It
transports authenticated raw advisory verdicts and evidence provenance. It
cannot encode an authoritative policy effect, `StateUnusable`, `ALLOW`,
commands, leases, dispositions, lifecycle operations, or ESTOP. An optional
producer field can request `RECORD_ONLY` or `REQUEST_DENY_TIGHTEN`, but that
request is non-authoritative and defaults to record-only handling.

Haldir derives policy eligibility and any restrictive effect. It uses a
separately authenticated, Haldir-owned monitor-admission profile. The profile
is static policy. It binds allowed exact Galadriel schema/model/configuration/
evidence-schema and release-suite identities, scope constraints, the required
adapter-mapping verification rule, deployment population, eligible verdicts,
calibration receipt, freshness and clock-mapping policy, policy-authority-stamped
policy-revision separation,
maximum restriction, dwell, hysteresis, rate limit, recovery, and absence
behavior. The profile issuer is independent of the Galadriel assessor principal.

The extension represents the sealed Galadriel release-suite identity as a typed
`GaladrielReleaseSuiteIdentity`, not a mutable name. It binds algorithm
`sha256`, derivation domain `galadriel-release-suite-v1`, lowercase-hex encoding,
and the exact 32-byte `ConfigDigest`. The Galadriel adapter defines one total,
injective mapping from `ReleaseSuite::identity()`/`ConfigDigest` bytes to that
representation. A human suite name is optional diagnostic text and has no
identity or admission effect.

The extension represents `AssessmentBinding::digest()` as a separate typed
`GaladrielAssessmentBindingIdentity`. It binds algorithm `sha256`, derivation
domain `galadriel-assessment-binding-v2`, lowercase-hex encoding, and the exact
32-byte `AssessmentDigest`. A bare hexadecimal string, a `sha256:` prefix, or a
release-suite digest in this field is not an equivalent identity. The adapter
mapping is total and reversible at the byte boundary.

The extension uses a bounded `GaladrielLifecycleOutcomeEvidence` over one exact
verified `LifecycleReceipt`, the exact raw bytes produced by
`serde_json::to_vec(&assessments)`, and a complete ordered extension projection
of the assessment vector that the receipt's `assessment_digest` covers. The
protected envelope carries both raw attachments and their content digests. Each
projected vector member is a closed `GaladrielLifecycleAssessmentEvidence`:

- `EVALUATED_DEFAULT_REPORT` carries `track_id`, `fusion_seq`, `history_reset`,
  the exact scope and binding, and one sealed `DefaultReport`; or
- `LIFECYCLE_ABSTAINED` carries `track_id`, `fusion_seq`, and a non-empty,
  canonically ordered set of exact Galadriel modalities. It forbids a report,
  scope, binding, verdict, and policy-bearing projection.

Before any cross-process handoff, the observer-side Galadriel lifecycle adapter
must pass its bounded strict receipt decoder, internal digest check, and
`verifies_assessments` against the exact release suite and live in-memory complete
vector. Neither the separate assessor nor a non-Galadriel receiver can invoke
that API because `LifecycleAssessment` and `DefaultReport` are serialization-
only. Haldir instead independently recomputes the documented lifecycle assessment-digest
formula over the exact raw vector bytes and exact suite identity, validates the
raw bytes against the registered strict serialized-shape schema, verifies the
receipt preimage, and verifies a mapping receipt from every raw vector member to
the extension projection. The mapping receipt also binds order, count, raw-vector
attachment and assessment digests, vector member index, and each projected field.

The protected extension envelope authenticates the assessor and the exact
receipt/vector bytes; the Galadriel receipt alone authenticates no writer and
proves no durable retention. Changed whitespace or member order changes the raw
assessment-vector identity and cannot be normalized away. An unknown future
non-exhaustive lifecycle variant rejects until a new extension manifest allocates
it.

The byte formulas are exact. `U64_BE` and `U128_BE` mean unsigned 8-byte and
16-byte big-endian integers. `LP(x) = U128_BE(len(x)) || x`.
`OPT(d) = 0x00` for absence and `0x01 || d` for one 32-byte digest. Then:

```text
assessment_digest =
  SHA256(
    ASCII("galadriel-ncp/lifecycle-assessment/v0.9") || 0x00 ||
    release_suite_config_digest_32 ||
    LP(exact_raw_serde_json_assessment_vector_bytes)
  )

receipt_digest =
  SHA256(
    ASCII("galadriel-ncp/lifecycle-receipt/v0.9") || 0x00 ||
    U64_BE(index) ||
    previous_receipt_digest_32 ||
    LP(producer_id_utf8) ||
    LP(canonical_stream_position_json) ||
    LP(canonical_lifecycle_transition_json) ||
    OPT(frame_digest) ||
    OPT(assessment_digest)
  )
```

The registered Galadriel serialized-shape profile freezes the exact compact JSON
member order, nesting, enum spellings, escaping, integer spelling, and absence
rules produced by the reviewed Galadriel source for the position, transition,
receipt, and assessment vector. It also freezes the exact reviewed
`serde_json`/Ryu finite-`f64` spelling, exponent/case rules, negative-zero
treatment, and numeric bounds. Raw receipt JSON whitespace/member order can
vary only before strict decode and canonical receipt-preimage reserialization;
the protected attachment digest still binds the delivered bytes. Raw assessment-
vector bytes are hashed directly after their 16-byte length prefix, so their
whitespace and order are significant. Cross-language fixtures mutate the length
width, endian, missing NUL, option tag, field order, escaping, suite bytes, and
raw-vector length independently. Float fixtures distinguish `1`, `1.0`, `1e0`,
negative zero, exponent/case substitutions, overflow, and non-finite forms.

One receipt proves internal transition integrity, not detector continuity. For
policy eligibility, the native adapter installs a durable extension-owned
`GaladrielLifecycleLineageHead` through
`InstalledGaladrielLifecycleLineageSelector` and emits
`GaladrielLifecycleLineageCommitReceipt`. The head binds a never-reused detector
lineage, a strictly increasing outer `lifecycle_state_version`, exact suite and
NCP mapping profile, direct `AuthorityRealmKey`, exact
session-kind/logical-session/generation scope, current
`assessor_clock_incarnation`, global lifecycle receipt index/digest, prior head,
and a
bounded canonical map from every detector lane key to
`GaladrielLifecycleLaneAuthorityState`. The outer version starts at 1 and
increments by exactly one on every selector compare-and-swap. The inner global
lifecycle receipt index is a detector transition index and is not a substitute
for the outer version. Each lane state binds the exact NCP
source-authority tuple: direct `AuthorityRealmKey`, session kind, logical session
ID, live `SessionRef.generation`, descriptor revision/digest,
stream-declaration digest, observer-grant authorization tuple/digest,
security-state/security/revocation epochs, receiver-evidence lineage,
coordinate-mapping receipt digest, current source epoch/position and Galadriel
state generation, used/retired source epochs, and bounded history/warm-up
horizon. The lane key contains the full
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` foreign key
before its declared-stream and detector-lane coordinates. The Galadriel nested
`AssessmentScope.session_id` or source epoch is not a substitute for the NCP
realm, session kind, generation, or any other member of this tuple.

The lineage head is also the local publication-coordination composite root: it
binds the exact subordinate `GaladrielAssessmentHandoffStateHead`. Lifecycle
state transitions and handoff publication transitions contend on
`InstalledGaladrielLifecycleLineageSelector`; there is no independently
authoritative handoff selector. A handoff-only successor preserves the detector
snapshot/lane map and inner lifecycle receipt index, but still increments the
outer lifecycle state version by exactly one. Every lifecycle successor also
increments the outer version and atomically installs its matching handoff
currentness or invalidation update. The generic lineage commit receipt binds the
prior and installed outer versions as well as the prior and installed heads and
selector versions.

An assessor-clock restart constructs receipt-free
`GaladrielAssessorClockRestartTransitionFact` and advances the same lifecycle
selector. Its successor either binds an authenticated no-later mapping for every
pending reservation, local-queue, external-attempt and retry deadline or cancels
every pre-release reservation/local-queue transition and terminalizes each unsent
released item whose deadline cannot be mapped without extension. An already
installed external attempt remains a resolution obligation and cannot be invoked
again. Every branch preserves the detector snapshot, lane map and exact released
immutable item. The post-CAS
`GaladrielAssessorClockRestartCommitReceipt` binds the fact, prior/installed
lifecycle heads, selector and generic commit. Without exact restore or this
transition, FINALIZE and local-queue release remain closed.

The head also binds one exact `GaladrielLifecycleStateSnapshot` reference:
schema/version, canonical encoding, digest, byte length, implementation-contract
digest, and complete fixed configuration/release suite, bounded lane map,
per-lane histories/observations/recent frames/positions/state generations,
used/retired epochs, global receipt anchor/tip/index/eviction count, publication
state, and terminal fault. The snapshot contains neither its own digest nor the
later lineage head/receipt. A schema or implementation revision that cannot
restore these exact canonical bytes retires the lineage and requires full
profile-qualified warm-up; it cannot reinterpret an old opaque “state digest.”

The native implementation must add an explicit snapshot/restore and transactional
transition API; observing public outputs from the current detector is
insufficient. Canonical snapshot encoding sorts every map/set key and round-trips
every private state member. Each candidate source/reset/timeout/rollover/
assessment transition runs on an isolated clone or transaction, computes the
inner lifecycle receipt, candidate snapshot and, for an assessment, a
`GaladrielAssessmentPublicationCandidateFact`, then installs the snapshot, fact
and lineage successor atomically. The fact binds the exact receipt/vector/
projection/source preimage needed for publication but contains no lifecycle or
handoff successor head, selector, commit receipt, or later publication record.
An inner receipt/digest/serialization
failure cannot leave mutated unreceipted detector state current. It installs an
outer terminal lineage-fault commitment or retires the lineage.

Each successful global receipt transition names exactly one mapped lane or one
closed global operation and atomically persists the new snapshot and lineage
head before assessment publication. It cannot authenticate one lane under
another lane's authority tuple. Every genesis, late-attach/reset boundary,
currentness update, handoff record, and assessment-bearing head binds the
complete map and snapshot. A generation, descriptor, declaration, security
binding, receiver lineage, mapping receipt, or unbridged grant change in one lane
cannot silently continue that lane or rewrite its siblings.

Routine same-scope grant renewal can continue one detector lineage only through
`GaladrielLifecycleAuthorizationSpanTransition`. The transition binds the exact
affected lane-key set, old and new complete grant authorization tuples/digests,
delivery-boundary enforcement and observer-installation receipts, and the
observer's prior/installed `ObserverAdmissionStateHead` digests and
`InstalledObserverAdmissionStateSelector` version at the renewal cut. For each
affected lane it binds the unchanged
realm/session-kind/logical-session/generation/descriptor/declaration/security/
receiver-lineage/mapping tuple, exact equality of coordinate-stream scope, the
old span's last and new span's first frame-admission receipts/subheads, and proof
of no unaccounted gap, overlap, duplicate, expiry interval, or revoked interval.

The observer composite selector serializes renewal with every old/new frame
admission. The Galadriel transition then atomically compare-and-swaps the
lifecycle head/snapshot before any winning new-grant frame enters detector
state and emits `GaladrielLifecycleAuthorizationSpanCommitReceipt`. The head
records ordered non-overlapping authorization spans and exact per-lane
boundaries. This transition changes only the current grant member in the
affected lane states and preserves already qualified warm-up; it cannot widen
scope, hide lost input, or infer a cut between independent selectors.

Any other tuple change, absent/losing transition, scope change, security change,
or admission gap requires the separately authenticated profile-qualified
reset/new-lineage path with full warm-up or retires the lineage. A generation
or realm change always retires the old source-authority scope. A realm change
also selects a different consumer foreign key and cannot use a same-scope
renewal. Mutating any tuple member independently, a receipt index/root reset,
skipped predecessor, losing sibling, reused epoch, or missing commit receipt is
not continuity. Canonical head content excludes its own digest/commit receipt
and every successor/selector digest; the post-CAS commit receipt binds prior and
installed heads plus selector version.

The only lineage genesis consumes a parent-created `UNINITIALIZED` selector once.
A same-lineage process restart is policy-eligible only after exact durable restore
and continuation from the installed head. Lost, partial, or ambiguous state
retires that lineage. Every new lineage requires full profile-qualified warm-up,
including after a fresh NCP epoch. For an existing epoch, a separately authorized
late-attach/reset boundary binds the actor/profile, exact current descriptor,
stream declaration and observer grant, the installed receiver frame-admission
head/high-water, the exact first live—not retained history, query, or replay—
`FrameAdmissionReceipt` and head commit, the new detector lineage, and a zero
sample count before that position. No pre-boundary source position can enter the
new suffix. The boundary is consumed once; it cannot initialize a sibling
lineage. A producer assertion or a new assessor incarnation does not prove source
currentness or reset detector state.

The native-1.0 adapter seals policy-eligible detector state behind a restricted
mutation interface. Only receipted source-frame, `reset_at`, `timeout_at`, epoch-
rollover, assessment, qualified boundary, and terminal-fault transitions can
change the snapshot/head. The compatibility `LifecycleDetector::clear_histories`
method is not exposed or called through that interface. Any diagnostic path that
does invoke it atomically retires the lineage and requires a new lineage plus
full warm-up; cleared state is never policy-eligible. Compile-time visibility/
trait tests and runtime post-clear negatives enforce this rule.

An assessment envelope binds both the lineage head that installed its lifecycle
receipt and a separately authenticated current-selector attestation at signing
time. If the selector advanced, a bounded head-chain or authenticated compaction
bridge proves ancestry/retained membership from the assessment head to the
attested current head. The chain preserves every accepted, rejected, and faulted
transition plus lane state; a receipt-index gap is valid only when that exact
chain/bridge explains it. An assessment-bearing lifecycle transition atomically
persists the exact `GaladrielLifecycleStateSnapshot`, lifecycle receipt,
publication-candidate fact and first lineage/handoff head H1. Its generic commit
C1 is post-CAS and is not content inside H1. The immutable
`GaladrielAssessmentPublicationRecord` is then constructed from the installed
fact, H1 and C1. A second handoff-only compare-and-swap from exactly H1 installs
H2, whose subordinate handoff state binds that record and whose snapshot/lane
map is byte-identical to H1, then emits C2. No assessor or later `RESERVE` can
observe the record before H2.

If a lifecycle advance or invalidation orders between H1 and H2, it terminalizes
the candidate as `CANCELED_BEFORE_RECORD_INSTALL`; the H2 compare-and-swap loses
and exposes no record. Crash after H1 resumes the same fact and deterministic
record bytes or observes that tombstone. This two-transition construction is
required because one content-addressed head cannot contain a publication record
that itself contains that head. Rejected/faulted transitions need no assessment
envelope, but they remain in the durable head chain. A historical
head in a fresh envelope, sibling current selector, stale compaction root, or
unexplained gap is not policy-eligible. Each Haldir admission record binds the
assessment head/commit, signing-time current attestation, and ancestry/compaction
proof.

Because the transport is push-only, the protected envelope carries every
lineage/currentness object as a bounded attachment: assessment head, head commit
receipt, signing-current head, current-selector attestation, and head-chain or
compaction proof, plus the exact coordinate-mapping receipt and source-authority
objects referenced by those heads. Each attachment reference binds exact digest,
byte length, media type/schema, and attachment ID; the envelope authenticates
the complete set. Haldir verifies all bytes locally before admission. A
digest-only dangling reference, later fetch, cross-envelope cache guess, head
without its commit, attestation without ancestry proof, source-authority tuple
without its locally verifiable objects, or tampered/missing attachment rejects.

Observer and assessor isolation uses one explicit one-way local evidence handoff,
not shared credentials or in-memory Rust values. While the serialization-only
values are live, the observer-side lifecycle adapter verifies them and commits
their exact receipt/vector/projection, source captures and outbox identity into
the publication-candidate fact in H1. After H1/C1 install, the distinct local
handoff authority deterministically constructs
`GaladrielAssessmentPublicationRecord` over that fact and H1/C1 and installs it
only through the H1-to-H2 handoff-only compare-and-swap above.
The record directly binds the `AuthorityRealmKey` and complete session foreign
key from the candidate fact; the handoff authority cannot project either away.
The adapter holds the observer credential but no extension signing key. The
handoff authority/store holds neither credential. Each later lifecycle transition
appends an authenticated current-head/ancestry or invalidation update to the same
bounded handoff lineage through that authority.

Canonical `GaladrielAssessmentHandoffStateHead` binds the handoff-authority
principal/instance/security context, direct `AuthorityRealmKey`, complete
session foreign key, never-reused lineage incarnation, state version, and closed
root phase
`UNINITIALIZED | ACTIVE | FENCED | RETIRED_DRAIN_ONLY | RETIRED`. It also binds
exact lifecycle publication-candidate facts and closed
`PENDING_RECORD_INSTALL | RECORD_INSTALLED |
CANCELED_BEFORE_RECORD_INSTALL` states, installed publication records and
currentness/invalidation updates, a bounded map of assessor
principal/incarnation to next and consumed
assessment sequences, pending `GaladrielAssessmentPublicationReservation`
objects, pre-finalize cancellation tombstones, bounded receipt-free
`GaladrielAssessmentReleaseOutboxCommitment` values and closed
`GaladrielAssessmentQueueTransitionFact` values, and prior head. Each queue fact
binds a complete `GaladrielAssessmentReleaseOutboxItem`, exact queue item or
cancellation and local outcome, but no
prior/installed lifecycle head, selector, commit or later resolution. The head
excludes its own digest/receipt, every successor/selector digest, and each later
release, cancellation or resolution receipt digest.

Lifecycle genesis is the only `UNINITIALIZED -> ACTIVE` edge. Only `ACTIVE` can
create a lifecycle record, reservation or release. `FENCED` is irreversible and
permits only exact restrictive closure and retirement work. Retirement enters
`RETIRED_DRAIN_ONLY`; the complete-inventory finalizer alone enters `RETIRED`,
which has no successor. Every generic, retirement and finalization receipt binds
the exact prior and installed root phases through its heads. A missing phase,
phase/head mismatch, skipped drain-only phase or ordinary event from a non-ACTIVE
root rejects.

`InstalledGaladrielLifecycleLineageSelector` is the sole lifecycle/handoff
currentness root. Publication-candidate transition, publication-record append,
lifecycle currentness advance,
invalidation, `RESERVE`, pre-finalize cancellation, `FINALIZE`, and queue
resolution all compare-and-swap that selector through the narrow handoff API and
emit `GaladrielAssessmentHandoffStateCommitReceipt` over the prior/installed
lifecycle heads and subordinate handoff heads. Lifecycle genesis creates the
never-used handoff substate in the same transaction. Missing, recreated empty,
rolled-back, or sibling substate after use retires the lifecycle/handoff lineage
and cannot reset assessment sequence or currentness.

The assessor process holds the extension key but no `ObserverReadCapability`, raw
NCP/extension bus escape hatch, detector state, or observer credential. Through a
narrow audience-bound local IPC/store reader, it strictly verifies the bounded
publication record, its exact H1/C1-to-H2/C2 installation chain, and latest
installed handoff head/currentness update. `RESERVE` is invalid until
`RECORD_INSTALLED`.
Publication uses a two-phase compare-and-swap. `RESERVE` installs one assessment
sequence and exact unsigned envelope preimage. The assessor signs only that
preimage. `FINALIZE` succeeds only if the reservation remains in the exact
current head and no intervening currentness advance or invalidation canceled it.
The winning transaction conditionally verifies the exact assessor clock
incarnation and evaluates the commit-bound deadline condition below. Equality or
a later linearization instant installs `CANCELED_BEFORE_FINALIZE`, consumes the
reservation/sequence, and exposes no release receipt or outbox item.

Galadriel uses the distinct
`GaladrielReleaseDeadlineConditionIntent`, intent-set root,
`GaladrielCommitTimeReleaseDeadlineCondition`, and evaluation-set root types.
Their closed purposes are `AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE` and
`EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE`; their closed kinds are
`ASSESSMENT_RESERVATION_NOT_AFTER | ASSESSMENT_FINALIZE_NOT_AFTER |
LOCAL_DURABLE_QUEUE_RELEASE_NOT_AFTER |
EXTERNAL_TRANSPORT_ATTEMPT_NOT_AFTER |
EXTERNAL_TRANSPORT_ACCEPTANCE_NOT_AFTER | EXTERNAL_RETRY_RIGHT_NOT_AFTER`. They
use a Galadriel-release digest domain and cannot reuse the observer, body, policy,
retention, retry or quiescence family.
The fact and candidate bind the exact complete intent root. The generic and
specialized commits and release/resolution receipt bind the matching complete
evaluation root in the winning durable bundle. Each evaluation uses the ADR-004
integrated-manager or qualified-completion-bound proof through durable commit.
Authorization is strict-before; the disjoint cancellation/expiry case is
at-or-after. A pre-lock `finalize_now`, transport-worker sample, or static
reservation receipt cannot survive an unbounded stall.

FINALIZE first constructs a receipt-free
`GaladrielAssessmentReleaseOutboxCommitment` over the exact signed bytes/digest/
length, literal route, Haldir audience, extension manifest/security context,
direct `AuthorityRealmKey`, complete session foreign key, assessor clock
incarnation, strict assessor-clock not-after, canonical complete deadline-intent
root, consumed sequence, and reservation. It contains
no lifecycle/handoff successor, selector version, generic commit, release
receipt, or complete outbox item. The candidate handoff
successor binds that commitment. After the compare-and-swap, the generic handoff
commit and `GaladrielAssessmentPublicationReleaseReceipt` bind the
prior/installed lifecycle and handoff heads, selector version, reservation, and
commitment. The complete `GaladrielAssessmentReleaseOutboxItem` binds the
commitment, exact bytes, and post-CAS release receipt; the successor never binds
the complete item or either receipt.

One local durable transaction persists the installed lifecycle/handoff heads,
generic commit, release receipt, and complete outbox item together. A losing
compare-and-swap exposes neither receipt nor bytes. That append is the
publication-release linearization point, not a reusable
authorization token. The transport worker can drain only those exact bytes once.
It locally rechecks its security context and clock incarnation and binds the
fresh `LOCAL_DURABLE_QUEUE_RELEASE_NOT_AFTER` intent,
constructs one
`GaladrielAssessmentQueueTransitionFact`, and compare-and-swaps the lifecycle
selector to a successor that binds that fact. One local durable transaction
persists the successor lifecycle/handoff heads, generic handoff commit, exact
queue item, commit-bound evaluation set and post-CAS resolution. The queue is a bounded durable queue in the
same local transactional store as the selector. The transaction records exactly
`CANCELED_BEFORE_LOCAL_QUEUE |
RELEASED_TO_LOCAL_DURABLE_EXTENSION_QUEUE` in
`GaladrielAssessmentPublicationResolution`. The resolution binds the fact,
prior/installed lifecycle and handoff heads, selector version and generic
handoff commit; the installed head binds the fact but not the resolution. Every
branch consumes the sequence. A commit-reply loss is recovered from the installed
selector and local queue; it is not a third local outcome.

Each released local queue item carries an
`EXTERNAL_TRANSPORT_ACCEPTANCE_NOT_AFTER` equal to the conservative minimum of
the mapped assessment reservation/finalization deadline, local queue-release
deadline, authenticated source-freshness bound, and
`checked_add(local_queue_release_instant,
profile_max_external_transport_duration)`. The profile value is a duration, never
an absolute timestamp. Every member is represented in the adapter's acceptance-
clock domain through a qualified conservative no-later mapping. Its earlier
`EXTERNAL_TRANSPORT_ATTEMPT_NOT_AFTER` subtracts the qualified worst-case duration
from attempt installation through endpoint acceptance, including queue, call,
clock-mapping and completion uncertainty. START is necessary but cannot prove
acceptance. An unavailable mapping, duration upper bound or positive residual
window fails closed instead of dropping a bound. The queue fact, candidate,
winning commit and resolution bind the complete ordered source-bound set and both
deadlines. A later receive, retry, restart, retirement or drain transition cannot
refresh them.

A separate worker drains the local durable extension queue to the external
extension transport. The qualified adapter exposes
`GaladrielAssessmentTransportGateState` as
`OPEN_NORMAL(epoch, context) |
OPEN_DRAIN(epoch, retained_obligation_root, allowed_key_root) |
FENCED(epoch, cause, receipt) | RETIRED`. Epochs never repeat. Lifecycle,
security, session/scope and retirement invalidation obtains a durable gate-fence
receipt before its selector CAS; an old epoch cannot be accepted afterward.
Acceptance before the fence can resolve later with exact order evidence. Missing
order remains ambiguous. `OPEN_NORMAL` accepts only current non-retired work.
`OPEN_DRAIN` accepts only exact key membership in its immutable retirement roots,
under unchanged bytes and deadlines; it creates no publication authority.
Non-authorizing transport state still requires installed currentness.

A boundary fence survives a losing lifecycle-selector CAS. Receipt-free
`GaladrielAssessmentTransportGateFenceFact` binds the exact expected selector/
head, boundary epoch/context, cut cause and affected keyed inventories; the
boundary receipt binds that fact and fence order. If the expected CAS loses,
`REBASE_GALADRIEL_ASSESSMENT_TRANSPORT_GATE_FENCE_AFTER_LOSING_CAS` binds the
losing fact/receipt, newly queried current selector/head and unchanged sibling
inventories, then compare-and-swaps the lifecycle/handoff selector to associate
the already-effective fence. It never rolls the boundary back, changes the cause
or drops an outbox/attempt/disposition/retry key. START and reopen remain disabled
until that rebase wins. A canceled cut can reopen only through a separately
qualified fresh normal epoch after complete terminal-obligation proof.

Before send, the worker constructs receipt-free
`GaladrielAssessmentExternalTransportAttemptFact` over the exact immutable
bytes, queue-item digest, stable release/idempotency key, transport instance,
fresh bounded attempt identity, prior attempt lineage, the applicable retry
authorization or typed first-attempt absence, direct realm, exact current
assessor security/session/scope, current transport-gate epoch, and the complete
attempt-start and acceptance deadline intent sets.
`START_GALADRIEL_ASSESSMENT_EXTERNAL_TRANSPORT_ATTEMPT` compare-and-swaps the
same lifecycle/handoff selector, commit-bound evaluates that complete set,
rechecks the bound security/session/scope and installs one active attempt in the
keyed handoff queue partition before any external call. Equality, later time, changed
currentness, a sibling worker, duplicate attempt identity, stale queue item or
missing required predecessor retry right sends nothing. `OPEN_NORMAL` additionally
requires a current non-retired lifecycle; `OPEN_DRAIN` requires exact membership
in both bound retirement roots. No other gate variant can START. The elapsed/currentness
branch instead uses
`EXPIRE_GALADRIEL_ASSESSMENT_QUEUE_BEFORE_EXTERNAL_TRANSPORT` to install the
typed terminal result `EXPIRED_BEFORE_EXTERNAL_TRANSPORT_ATTEMPT`, complete
at-or-after/currentness evidence and exact queue tombstone without an attempt.
Its specialized receipt binds the prior/installed lifecycle and handoff heads,
selector version, generic commit, evaluation and terminal entry. A label or
worker clock sample cannot select that branch.

The transport acceptance endpoint consumes the exact attempt, immutable bytes,
stable key and gate epoch at most once. At its acceptance linearization point it
evaluates the unchanged complete
`EXTERNAL_TRANSPORT_ACCEPTANCE_NOT_AFTER` set and current gate/context. A
strict-before acceptance emits
`GaladrielAssessmentExternalTransportAcceptanceDeadlineEvaluationReceipt` over
the attempt, bytes/key, endpoint, acceptance instant, complete evaluation and
gate order. Equality or later time cannot accept. An adapter without atomic
deadline-aware acceptance, same-key query and old-epoch fencing keeps extension
publication disabled.

After send, receipt-free
`GaladrielAssessmentExternalTransportDispositionFact` binds that installed
attempt and exactly one result from the closed
`GaladrielAssessmentExternalTransportDisposition` union:
`ACCEPTED_BY_EXTERNAL_TRANSPORT_BOUNDARY |
REJECTED_BEFORE_EXTERNAL_TRANSPORT_ACCEPTANCE |
AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT`.
`RESOLVE_GALADRIEL_ASSESSMENT_EXTERNAL_TRANSPORT_ATTEMPT` compare-and-swaps the
same selector, terminalizes that exact attempt, and installs its disposition in
the bounded lineage. Post-CAS
`GaladrielAssessmentExternalTransportDispositionReceipt` binds the fact,
prior/installed lifecycle and handoff heads, selector version and generic
handoff commit. It cannot authorize publication or alter the signed bytes.

`ACCEPTED_BY_EXTERNAL_TRANSPORT_BOUNDARY` requires the exact authenticated
transport acceptance plus the matching strict-before acceptance-deadline receipt
and gate order. It proves only adapter-boundary acceptance, not Haldir receipt,
processing or policy use. `REJECTED_BEFORE_EXTERNAL_TRANSPORT_ACCEPTANCE`
requires definitive authenticated no-acceptance evidence. Timeout, cancellation,
dropped task or local return without endpoint proof is ambiguous.
`AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT` binds the exact attempt and forbids either
definitive receipt. A crash after attempt installation but before the call can
resolve rejected only with definitive no-acceptance evidence. A crash after the
call but before resolution recovers as ambiguous unless authenticated endpoint
evidence proves one definitive branch. RESOLVE may commit after expiry or a gate
cut. The accepted branch requires exact proof that acceptance ordered before both
deadline and fence. The rejected branch instead requires definitive authenticated
no-acceptance evidence. The ambiguous branch structurally forbids either proof
and retains only its bounded same-key query/retry rights. An ambiguous disposition can create a
successor attempt only when the transport proves same-key idempotency and the
installed bounded retry policy permits it; otherwise it remains terminal with
no retry right. Retry creation is another selector CAS over that exact lineage
and preserves the unchanged acceptance deadline while re-evaluating the earlier
attempt-start cutoff plus the retry-right deadline. The earlier start/retry
deadline wins and equality makes no call; the endpoint still evaluates the
acceptance cutoff.
Unknown/mixed outcomes, uninstalled attempts, concurrent dispositions, changed
bytes, and branch strengthening reject. No branch re-signs or reconstructs
content.

Invalidation and current-head updates serialize through the same selector.
Invalidation before the outbox append atomically installs
`CANCELED_BEFORE_FINALIZE` plus
`GaladrielAssessmentReservationCancellationReceipt`; the successor head binds
the cancellation tombstone, while the post-CAS receipt binds the prior/installed
heads and generic handoff commit. That terminal transition consumes/tombstones
the exact assessment sequence and contains no outbox or queue result. It is
distinct from post-finalize `CANCELED_BEFORE_QUEUE`. Invalidation
after the outbox append orders after an already released immutable item and
cannot rewrite it. A lifecycle-invalidating compare-and-swap and its handoff
invalidation are the same composite transition, so FINALIZE cannot outrun a
winning lifecycle change that has not yet been imported. A crash after reserve/
before sign resumes the same preimage/sequence or observes the installed
cancellation tombstone. A crash or lost reply after finalization queries the
installed lifecycle selector/outbox and drains or resolves that entry; it never
allocates another. Tests cut crashes and invalidation before
reserve, after reserve, after sign, immediately before/after finalization, and at
queue ownership transfer. Queue failure remains explicit. A tampered, stale,
sibling, replayed, invalidated, unlinked, or differently reconstructed record
rejects. The handoff credential grants neither NCP observation nor extension
publication authority by itself.

`RETIRE_GALADRIEL_SESSION_SCOPE` first fences the normal transport-gate epoch,
cancels and tombstones every exact pre-record or pre-finalize operation, and
always installs `RETIRED_DRAIN_ONLY`, including for a canonical empty obligation
inventory. The retirement fact binds the complete retained-obligation and exact
externally startable-key roots. The installed drain head initially keeps external
acceptance fenced. If a finalized outbox item still lacks its local queue
resolution, drain-only permits the exact
`GaladrielAssessmentQueueTransitionFact` transition. For an exact immutable
retained queue item, it also permits
`START_GALADRIEL_ASSESSMENT_EXTERNAL_TRANSPORT_ATTEMPT`,
`RESOLVE_GALADRIEL_ASSESSMENT_EXTERNAL_TRANSPORT_ATTEMPT`, and terminal closure
or exercise of an exact retry right already in the retirement inventory. A
resolution of an attempt that was already in that inventory can derive only the
retry right allowed by its immutable pre-retirement retry policy and stable
idempotency key. A new retained attempt also requires the unchanged strict-before
external-attempt cutoff; drain-only cannot extend either cutoff. Drain-only cannot mint or
widen another retry right, append
lifecycle evidence, reserve or finalize a publication, re-sign content, or
create changed bytes. These keyed queue, attempt, disposition, retry and safe
retention transitions remain in `RETIRED_DRAIN_ONLY`; none can infer global
closure.

`OPEN_GALADRIEL_RETAINED_TRANSPORT_DRAIN` verifies that exact installed drain
head and asks the boundary to install one fresh never-used `OPEN_DRAIN` epoch
bound to those two roots. A receipt-free activation fact binds the installed
drain head/selector and roots; the boundary activation receipt binds that fact/
epoch, the selector successor binds both, and a post-CAS receipt binds the
installed successor without a content cycle. START in drain requires
that receipted epoch and exact allowed-key membership. Any transition that
removes a key or finalizes first fences that drain epoch; acceptance proved before
the fence remains a retained resolution obligation, and after-fence acceptance is
impossible. If activation wins but its selector CAS loses,
`RECONCILE_GALADRIEL_OPEN_DRAIN_ACTIVATION` binds the exact activation fact/
receipt, current drain-only selector/head, unchanged roots and boundary query. It
either compare-and-swaps that already-effective epoch into currentness or fences
it; mismatch or unknown starts nothing and cannot widen roots. Empty or resolve-
only inventories never open a drain epoch.

After every retained local obligation is terminal and required
retention is satisfied, or immediately from the proved empty inventory,
receipt-free
`GaladrielLifecycleRetirementFinalizationFact` binds the exact prior drain-only
head/selector version and canonical complete reservation, outbox, queue,
disposition, retry-right, retention and tombstone inventories.
`FINALIZE_GALADRIEL_LIFECYCLE_RETIREMENT` alone installs `RETIRED`.
It first fences any `OPEN_DRAIN` epoch and binds that fence order.
Post-CAS `GaladrielLifecycleRetirementFinalizationReceipt` binds the fact,
prior/installed heads, selector version and generic lifecycle commit. A missing,
partial or caller-summarized inventory rejects. Retirement never strands an
already released immutable item or reopens publication authority.

Policy-bearing assessment evidence is restricted to the evaluated branch and a
sealed Galadriel `DefaultReport`. `report_family` is the literal
`galadriel_default_report_v1`. Its realm-scoped identity is the direct
`AuthorityRealmKey`, complete session foreign key, exact typed lifecycle
assessment digest, raw-vector attachment digest, and zero-based member index.
That existing Galadriel digest uses domain
`galadriel-ncp/lifecycle-assessment/v0.9\0`, the exact release-suite identity,
and the exact complete serialized vector bytes. NCP does not invent a second
per-report digest or pretend that the flat vector hash supports a one-member
inclusion proof. Haldir retains the complete bounded vector and reads the exact
complete report bytes at that index; it cannot reconstruct an underspecified
report from projected fields.

The verdict payload is a total, injective projection of `FusedVerdict` using its
snake-case variant, exact bounded unique modality list, and required
`MagnitudeEvidence` for `attributed_inconsistency`. Baseline `Verdict`, an
unbound fusion tuple, a free label, or a report with omitted variant fields is
record-only or rejects. The adapter mapping receipt binds the sealed vector/
member identity to every projected field. `FusedVerdict::InsufficientEvidence`
remains an evaluated report and is profile-ineligible; it is never relabelled as
lifecycle abstention.

The extension's flat `AssessmentScope` projection is not Galadriel's nested
Serde shape. The adapter defines a total, reversible, coordinate-by-coordinate
mapping to `AssessmentScope { producer_id, position { identity { epoch {
session_id, epoch_id }, stream_id }, state_generation, sequence, timestamp_ms,
clock_domain } }`. It tests every coordinate independently. The terminal
sequence equals the maximum observation sequence, and the terminal timestamp is
the maximum timestamp among observations at that sequence, as required by
`prepare_release_assessment`.

`AssessmentScope.clock_domain` uses Galadriel's exact closed `ClockDomain`
spelling: `unix_utc`, `monotonic_process`, `simulation_time`, or `tai`. The
adapter mapping is total for those four variants and rejects every unknown
domain. It does not translate a deployment-specific clock label into a runtime
variant by guess.

For native NCP origin frames, one registered adapter profile selects the exact
declared NCP stream that supplies the Galadriel lifecycle coordinate. The mapping
receipt binds both sides. NCP `stream.seq` is one-based; Galadriel lifecycle
sequence is the checked exact value `stream.seq - 1`. Therefore NCP sequence `1`
maps to Galadriel sequence `0`, including after every fresh NCP epoch. NCP
`SensorFrame.t` is source-process-local monotonic seconds. It maps to
`monotonic_process` milliseconds only when its finite, non-negative IEEE-754
value multiplied by 1000 is an exact integer in Galadriel's JSON-safe range and
is strictly increasing where the Galadriel lifecycle requires it. The adapter
does not round, merge two source times, or substitute receiver UTC. Producer,
logical session, live session generation, epoch, and stream come from verified
transport, descriptor, declaration, and frame evidence. `state_generation` is
Galadriel lifecycle state, not an NCP field; a receipt binds its initialization,
checked reset, and change. If there is no unambiguous coordinate stream or any
mapping member is absent or non-representable, the assessment is not
policy-eligible.

The Haldir monitor-admission profile evaluates the complete lifecycle vector,
never a producer-selected report. It binds an exact expected/allowed track scope
and one closed content-addressed aggregation rule. The rule specifies whether a
qualified `ANY`, `ALL`, or bounded `THRESHOLD` over an exact member set can
restrict permission and how evaluated insufficient evidence, lifecycle
abstention, a zero-member vector, missing/extra/duplicate tracks, mixed verdicts,
and an inapplicable population are handled. The only behavior without a matching
independently qualified rule is record-only. The producer cannot select the rule
or omit a sibling. The evidence-only `AssessmentAdmissionRecord` binds the
complete vector identity and bytes. `HaldirPolicyEvaluationResult`, created only
by the policy-state authority, binds the selected member indices, every member
classification, aggregation result, and rule digest. Because the current
Galadriel digest is flat rather than a Merkle root, Haldir retains and validates
the full vector; a one-report attachment cannot prove membership.

Haldir activates profiles only through one separately authenticated installed
current `HaldirPolicyStateHead`. This is the policy authority's composite
transaction root, not a policy snapshot beside independently current evaluation
or publication stores. The head binds the policy authority domain, never-reused
lineage incarnation, direct `AuthorityRealmKey`, exact
session-kind/logical-session/generation scope, closed root phase
`UNINITIALIZED | OPEN | FENCED | RETIRED_DRAIN_ONLY | RETIRED`, current
`policy_clock_incarnation`, strictly increasing
state version, separately increasing permission revision, base-policy digest,
exact active monitor-profile set and digests, applied-deny latch state,
policy-side assessment replay/evaluation-operation map, bounded
`HaldirIntentIngressState` with signed-intent attempts, replay/high-water state,
protected source-ingress preimages, receipt-free
`HaldirIntentIngressReservationFact` values, and receipt-free
`HaldirIntentSourceAdmissionFact` commitments,
`HaldirPublicationFenceState`, bounded
release-outbox commitment/pending-ownership state,
`HaldirPublishedCommandHistoryHead`, and prior-head digest. The complete
`HaldirPolicyReleaseOutboxItem` is an atomically persisted post-CAS sidecar whose
commitment is current through that head; it is not content bound by the
successor. The head excludes its own digest/receipt, every successor/selector
digest, each complete outbox item, and each post-CAS specialized receipt.

Genesis is the only `UNINITIALIZED -> OPEN` edge. Only `OPEN` can create
permission, evaluation, intent-ingress or release work. `FENCED` is irreversible
and permits only restrictive closure and retirement. Retirement enters
`RETIRED_DRAIN_ONLY`; the complete-inventory finalizer alone enters `RETIRED`,
which has no successor. Every generic, retirement and finalization receipt binds
the exact prior and installed root phases through its heads. A missing phase,
phase/head mismatch, skipped drain-only phase or ordinary event from a non-OPEN
root rejects.

`InstalledHaldirPolicyStateSelector` is the sole policy-authority currentness
root. Base/profile/latch/replay changes, evaluation reservation/barrier/
finalization, local-intent/source admission and decision, command-publication
reservation/cancel/release, feedback, and history changes all compare-and-swap
this same selector. Subordinate intent/source, evaluation, fence, outbox, and
history objects are not independently authoritative. Every transition emits
`HaldirPolicyStateCommitReceipt` over the
prior and installed head digests, selector version, closed transition kind and
authorized Haldir actor; specialized receipts bind that generic commit. A signed
historical profile, same-revision sibling head, caller/config-selected profile,
or rollback cannot evaluate new evidence or authorize publication.

A policy-clock restart constructs receipt-free
`HaldirPolicyClockRestartTransitionFact`. Through the same policy selector, its
successor either binds an authenticated no-later mapping for every pending
deadline into the new incarnation or atomically expires/cancels every pending
evaluation, ALLOW decision, publication reservation and receipt-free pre-release
outbox commitment while preserving deny/fail-safe state. An already released
complete outbox item and its worst-case history are immutable obligations and
survive restart; the commander still applies its own clock, body and security
checks. The post-CAS
`HaldirPolicyClockRestartCommitReceipt` binds the fact, prior/installed policy
heads, selector and generic commit. Without exact restore or this transition,
policy remains deny-preserving and cannot create or release Active authority.

`RETIRE_HALDIR_POLICY_STATE` cancels and tombstones every evaluation, local-
intent, publication reservation, and pre-release commitment that has not crossed
its ownership-transfer point. It retains every complete released outbox item,
pending worst-case history entry, and feedback obligation. The root always
enters `RETIRED_DRAIN_ONLY`, including for a canonical empty obligation
inventory. Only exact feedback, history closure,
terminal disposition, safe retention, and restrictive commander-preflight
closure transitions remain legal. A closure can install only an exact
cancellation tombstone or return an already released obligation. It cannot
create ALLOW, a policy decision, a publication reservation, or another release.
Those ordinary keyed closure transitions stay drain-only. After every retained
obligation is terminal and required retention is satisfied, or immediately
from the proved empty inventory, receipt-free
`HaldirPolicyRetirementFinalizationFact` binds the exact prior head/selector
version and canonical complete evaluation, intent, reservation, outbox,
history, feedback, disposition, retry-right, retention and tombstone
inventories, including the complete released-preflight key map used for
post-terminal nonmembership proofs. `FINALIZE_HALDIR_POLICY_RETIREMENT` alone
installs `RETIRED` without discarding the audit ancestry. Post-CAS
`HaldirPolicyRetirementFinalizationReceipt` binds the fact, prior/installed
heads, selector version and generic policy commit. A per-key feedback,
disposition or eviction fact cannot substitute for this global closure proof.

The only empty initialization is the closed
`GENESIS_FROM_UNINITIALIZED` transition. It compares against an
authority-owned selector state that proves the named policy domain and lineage
incarnation were never used, installs revision/state version `1`, and emits the
same `HaldirPolicyStateCommitReceipt`. After any committed head, no empty genesis
is valid. A restart, state loss, missing or ambiguous selector, reused lineage,
prior deny latch, or sibling uninitialized claim keeps assessment effects
disabled and current permission deny-preserving until an authenticated monotonic
recovery or widening transition resolves the state. It never resets to an empty
head.

The assessment receiver has a separate composite currentness root.
`HaldirAssessmentReceiverStateHead` binds receiver principal/instance/security/
clock, direct `AuthorityRealmKey`, exact
session-kind/logical-session/generation scope, a never-reused replay-store
incarnation and state version, closed root phase
`UNINITIALIZED | ACTIVE | FENCED | RETIRED_DRAIN_ONLY | RETIRED`, bounded
assessor-incarnation high-water and retired-incarnation commitments, exact
pending first-ingress preimages, immutable admission or rejected-terminal
records, unfinished dispositions, safe-eviction/rotation commitments, and prior
head. It excludes its own digest, every successor/selector digest, and every
post-CAS receipt digest. `InstalledHaldirAssessmentReceiverStateSelector` is its
only currentness root. `RECEIVER_STATE_GENESIS_FROM_UNINITIALIZED` consumes one
parent-created never-used selector. Each pending, admission, rejection, retry,
disposition, retirement, and safe-rotation transition emits
`HaldirAssessmentReceiverStateCommitReceipt`; missing, empty, rolled-back,
sibling, or reused state after use disables admission rather than resetting a
sequence.

Receiver genesis is the only `UNINITIALIZED -> ACTIVE` edge. Only `ACTIVE` can
reserve or admit assessment ingress. `FENCED` is irreversible and permits only
exact restrictive closure and retirement. Retirement enters
`RETIRED_DRAIN_ONLY`; the complete-inventory finalizer alone enters `RETIRED`,
which has no successor. Every generic, retirement and finalization receipt binds
the exact prior and installed root phases through its heads. A missing phase,
phase/head mismatch, skipped drain-only phase or ordinary event from a non-ACTIVE
root rejects.

Receiver retirement cancels each pending first-ingress preimage and always
installs `RETIRED_DRAIN_ONLY`, including for a canonical empty obligation
inventory. If an admitted record still lacks its external disposition,
drain-only permits only the exact disposition and safe retention
transitions for that installed record. It cannot reserve or admit another
assessment. Ordinary per-record disposition and retention transitions stay
drain-only. After all retained receiver obligations are terminal and required
retention is satisfied, or immediately from the proved empty inventory,
receipt-free
`HaldirAssessmentReceiverRetirementFinalizationFact` binds the exact prior
head/selector version and canonical complete ingress, admission, disposition,
retry-right, retention and tombstone inventories.
`FINALIZE_HALDIR_ASSESSMENT_RECEIVER_RETIREMENT` alone installs `RETIRED`.
Post-CAS `HaldirAssessmentReceiverRetirementFinalizationReceipt` binds the fact,
prior/installed heads, selector version and generic receiver commit. No keyed
disposition or eviction transition can infer or install global retirement.

For each verified envelope, Haldir issues a separate dynamic
`AssessmentAdmissionRecord`. It binds the raw envelope digest, assessor
principal/incarnation/sequence, direct `AuthorityRealmKey`, exact
session-kind/logical-session/generation foreign key, exact sealed Galadriel
`AssessmentBinding`, eight-coordinate `AssessmentScope`, release-suite identity,
exact verified lifecycle receipt and complete ordered lifecycle-assessment
vector, ordered observation/report identity, exact source captures, adapter
proof that maps that scope to admitted NCP captures, installed Galadriel
lifecycle-lineage head and commit receipt, receiver ingress
principal/instance/clock/receive time, exact body/session correlation evidence
or explicit absence, the receiver's single-flight identity, exact installed
pending-preimage receiver-state head, selector version, and reservation commit
receipt. It contains no successor
receiver-state head, admission-currentness receipt, or commit receipt for the
transition that later installs the record. It therefore makes no currentness
claim by itself. It contains
no monitor profile, selected member set,
policy head/revision, profile-derived deadline, eligibility, aggregation result,
handling, permission effect, local permission, meet result, evaluated successor,
or policy commit receipt. Those values belong only to the policy-state authority.
Equal evidence under different scope, suite, terminal position/time, observation
order, source capture, or adapter proof creates a different non-substitutable
admission record.

After it constructs those immutable bytes, the receiver compare-and-swaps a
successor head that binds the admission-record digest and removes the matching
pending preimage. `HaldirAssessmentReceiverStateCommitReceipt` binds the pending
and installed heads. A separate post-CAS
`HaldirAssessmentAdmissionCurrentnessReceipt` binds the admission record,
pending and installed receiver-state heads, selector version, and that generic
commit receipt. Downstream policy ingress requires the record and this
currentness receipt. The head does not bind either receipt, so the graph is
acyclic: pending head, record, successor head, generic commit, then currentness
receipt.

When the policy-state authority first receives that immutable record, it first
constructs a `HaldirPolicyIngressReservationFact`. The fact binds the admission
and exact admission-currentness receipt digests, policy-authority
principal/instance and clock, direct realm and complete session foreign key,
authority-local receive time, and one closed
`HaldirPolicyIngressProfileSelection`. It contains no policy head, selector
version, policy-state commit receipt, ingress stamp, evaluation barrier, result,
or finalization receipt. The authority then compare-and-swaps one pending
evaluation operation keyed by the realm, admission-record and reservation-fact
digests into policy head H1. H1 and its `HaldirPolicyStateCommitReceipt` C1 bind
the admission and reservation fact only. They do not bind the later ingress
stamp.

After C1 succeeds, the authority constructs one authenticated
`HaldirPolicyIngressStamp`. The stamp binds the reservation fact, admission and
admission-currentness receipt, exact installed H1, selector version, C1, state
version, permission revision, direct realm, complete session foreign key, and
profile selection. H2 is the first policy head that can bind the stamp. This
gives the acyclic order
`reservation fact -> H1 -> C1 -> ingress stamp -> H2 -> H2 commit receipt`.
`PROFILE_SELECTED` binds the exact profile digest and its authority-local
profile not-after. `NO_PROFILE` binds the exact installed base-policy
no-profile rule/source receipt and a separate authority-local no-profile
not-after derived from that rule; it contains no profile digest or
profile-derived field.

For `NO_PROFILE`, a second compare-and-swap advances H1 or a bounded
permission-preserving descendant to a terminal H2 that first binds the stamp and
terminalizes the operation as `NO_PROFILE_NOT_EVALUATED`. It emits the generic
policy-state commit receipt and the no-profile branch of
`HaldirPolicyEvaluationFinalizationCommitReceipt`, which binds the reservation
fact, stamp, prior and installed heads, selector version, and generic receipt but
no evaluation result or barrier. It creates no policy effect. For
`PROFILE_SELECTED`, the evaluation barrier below is H2 and is the first head
that binds the stamp. Unknown, mixed, or absent selection branches reject. The
receiver cannot construct or modify the fact or stamp. Same-digest retries query
H1/H2 and deterministically recover the same fact, stamp, and terminal result;
different bytes under the same receiver identity reject.

Evaluation deadlines use the distinct
`HaldirPolicyEvaluationDeadlineConditionIntent`, intent-set root,
`HaldirPolicyCommitTimeEvaluationDeadlineCondition`, and evaluation-set root
types. Their only deadline kind is `PROFILE_EVALUATION_NOT_AFTER`; their closed
purposes are `AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE` and
`EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE`. They use a Haldir-policy-evaluation
digest domain and cannot substitute for observer, body, release, retention or
quiescence conditions. The barrier fact, evaluation result and candidate bind
the exact applicable intent root, but no future evaluation. The winning generic,
barrier/finalization commit and specialized receipt bind the exact complete
commit-time evaluation root. The evaluation uses the ADR-004 integrated-manager
or qualified-completion-bound proof through durable commit. A barrier receipt,
earlier authority-clock sample or result label is not current timing evidence.

Only the policy-state authority classifies members, applies the complete-vector
rule, derives eligibility/handling/effect, reads local permission, computes the
meet, and decides whether to change policy. Its authenticated
`HaldirPolicyEvaluationResult` binds the admission record, ingress stamp, exact
realm and session foreign key, profile, selected member set and classifications,
aggregation rule/result, qualification evidence, source-clock mapping,
eligibility result,
`assessment_handling`, mapped `permission_effect`, local input and meet result.
It binds the exact barrier fact, installed barrier H2 and preserved
evaluation-input ancestry, but
contains no terminal H2F/H3 head, selector version, policy-state commit receipt,
or finalization receipt. The policy authority constructs this immutable result
before the terminal compare-and-swap.
For `PROFILE_SELECTED`, after the profile delay/currentness checks pass and with
a staged strict-before `PROFILE_EVALUATION_NOT_AFTER` intent for the original
stamped profile deadline, the authority first
constructs receipt-free `HaldirAssessmentEvaluationBarrierFact`. The fact binds
the admission/currentness pair, ingress fact/stamp, direct realm and complete
session foreign key, exact profile and H1 ancestry, authority clock/time,
original exclusive deadline, every passed guard, all preserved evaluation
inputs, and the one exclusive operation token. It contains no H2 successor,
selector, generic commit, barrier commit receipt, evaluation result, or
finalization receipt. The candidate H2 binds this fact.
One successful `ASSESSMENT_EVALUATION_BARRIER` compare-and-swap
advances the current H1-or-permission-preserving-descendant head to barrier head
H2, first binds the ingress stamp, admission, profile, H1 ancestry, authority
time and passed
guards, preserves the permission revision, base policy, profiles, latches and
local permission, and emits
the generic policy-state commit. After the in-transaction CAS comparison wins,
`HaldirAssessmentEvaluationBarrierCommitReceipt` binds the fact, exact
prior/installed policy heads, selector version and generic commit. The composite
transaction persists the selector, installed H2, generic commit and complete
signed barrier-receipt bytes. It exposes the receipt only after durable commit.
The composite head records the operation as the sole pending evaluator for that
admission/stamp. A losing or conflicting fact has no barrier receipt and cannot
share an installed H2. This is
single-flight exclusivity, not a global policy-store lock. Restrictive/fail-safe
work and bounded permission-preserving publication operations can advance the
composite head. A base/profile/revocation change atomically invalidates the
pending evaluator; widening waits for its terminalization.

Evaluation reads the exact H2 snapshot outside the short selector transaction.
Every terminal compare-and-swap verifies that the latest installed head still
contains the unchanged pending token and that every H2 descendant preserves the
evaluation inputs. The normal no-restriction and restriction-result cases also
bind the strict-before evaluation for the exact staged intent. The expiry case
instead binds the disjoint at-or-after intent/evaluation for that same typed
deadline; equality selects expiry. No case can require or satisfy both condition
sets. Every path then performs one short terminal
compare-and-swap. The successor head binds the exact
`HaldirPolicyEvaluationResult` digest and releases the exclusive operation:

- `EVALUATED_NO_RESTRICTION` installs permission-preserving head H2F;
- `EVALUATED_EXPIRED_NO_RESTRICTION` installs H2F after the deadline has elapsed
  and can contain no restrictive successor; or
- `RESTRICTION_COMMITTED` installs H3 and increments the permission revision.

The generic `HaldirPolicyStateCommitReceipt` then binds the prior and installed
heads and complete evaluation root. The evaluated branch of the post-CAS
`HaldirPolicyEvaluationFinalizationCommitReceipt` binds the result, terminal
kind, exact prior H2-or-permission-preserving descendant, installed H2F or H3,
selector version, and generic commit receipt. The disjoint no-profile branch
described above binds no result or barrier. For restriction, the evaluated
branch also binds proof that H3 is an ancestor or retained member of the
separately authenticated current head. The successor head binds neither receipt,
so result, successor, generic commit, and finalization receipt form an acyclic
graph.

Thus quiet policy state progresses H1 -> H2 -> permission-preserving descendants
-> H2F, while restriction progresses through the same pending token to H3. H2
and H2F are real state successors but never the deny mutation. A restrictive
transition can atomically consume the token as
`PREEMPTED_BY_RESTRICTION`, install its independently authorized deny, and
persist a terminal no-additional-restriction result for this assessment. A base/
profile/revocation invalidation terminalizes it as invalidated. Neither path can
convert the assessment into its own proof. Crash before barrier resumes/cancels
the same stamped operation. Crash after barrier restores the current descendant
and either completes the same result before its deadline or installs the explicit
expired-no-restriction H2F result; it cannot remain locked forever or produce H3
after expiry. A sibling/losing barrier, profile revocation or currentness loss
yields no restriction and never silently selects another profile.

Evidence-only H2/H2F churn does not by itself invalidate an in-flight command.
`HaldirPermissionPreservingHeadProof` is a bounded authenticated chain from a
decision's policy head to the current composite head in which every transition
preserves the exact permission revision, base-policy/profile/latch digests and
publication-invalidating state. Reservation/release can use that proof; any H3,
base/profile reload, revocation, widening, or unproved gap invalidates it.
Until exact deployment-specific calibration and qualification evidence exists,
the result is record-only.

The policy authority applies bounded admission/evaluation queues, operation
deadlines, and a content-addressed scheduler policy. Fail-safe publication and
restrictive cancel/deny work preempt evidence evaluation. The scheduler caps
consecutive assessment barriers and gives eligible command decision/publication
work bounded service between evaluations when no tightening is pending. On
budget, queue, or deadline exhaustion, new assessment effects become explicit
record-only/drop outcomes; they do not extend the exclusive operation. This is a
local bounded-delay claim, not an absolute system-wide noninterference claim.

The policy-state authority keeps evidence handling separate from the permission lattice.
`assessment_handling` is the closed
`RECORD_ONLY | ELIGIBLE_RESTRICTION` result. `permission_effect` is a separately
typed Haldir lattice element. `RECORD_ONLY` and advisory absence map only to the
lattice top/meet identity, represented as `NO_ADDITIONAL_RESTRICTION`; in the
current binary lattice its value is `ALLOW`, but that value preserves the local
decision and never grants permission. A required-absence profile maps absence to
its exact profile-owned deny element. An eligible restriction maps to the exact
bounded deny element authorized by the profile. Unknown handling/effect pairs or
an effect inconsistent with handling reject.

Haldir computes
`effective_permission = meet(local_permission, permission_effect)`. Thus local
`DENY` met with the identity remains `DENY`, local `ALLOW` met with the identity
remains local `ALLOW`, and every restriction is less than or equal to the local
permission. The policy ingress stamp, evaluation result, disposition, and
installed Haldir policy head bind the handling, mapped lattice value, profile
rule, and result. Haldir also binds each decision to the raw evidence digest,
exact dynamic admission-record and admission-currentness receipt digests,
static monitor-admission profile digest,
the policy revision stamped by the policy authority at ingress, and the strictly
later policy-state version that evaluated it, plus the unchanged or more
restrictive permission revision. The receiver and producer cannot assert either
Haldir version/revision or either Haldir-owned mapping. A producer request alone
has no policy effect.

An observed body-authority term is not a mandatory producer field. Haldir accepts
one only as an optional provenance reference to an exact authenticated
body-issued descriptor or disposition capture that the observer grant permitted.
It revalidates that capture and receipt; the assessor's signed value is not
body-authority evidence. If the reference is absent or unverifiable, it stays
explicitly absent and any profile that requires body-authority correlation treats
the evidence as record-only.

The producer's plant, logical-session, and generation values are correlation
claims, not body-issued session authority. The receiver can admit only the exact
body-issued descriptor/disposition capture and currentness proof carried as
bounded evidence; it does not read the commander's live store. The policy
authority compares the claims with that admitted evidence under the profile. A
mismatch, missing current proof, or producer-only generation remains record-only
or rejects; it cannot select a plant context. Before command publication, the
commander separately binds its exact live body descriptor/session scope into the
one-use authority-created publication reservation and atomic release fence. A
permission snapshot or receiver/policy record cannot rewrite or authorize that
command-side scope.

Every envelope binds the exact field `assessor_incarnation_id`, an opaque
never-reused process-lifecycle identity, and a bounded, strictly increasing
persisted `assessment_sequence` within that incarnation. Haldir deduplicates on
the direct `AuthorityRealmKey`, assessor principal, incarnation, sequence, and
exact envelope digest. Before it creates an admission record or evaluates
policy, Haldir atomically installs a first-ingress single-flight reservation
keyed by `(AuthorityRealmKey, assessor principal, incarnation, sequence)` and
the exact envelope digest. The winning receiver-state compare-and-swap durably
stores the authenticated raw envelope and exact receiver first-ingress
receive/clock stamp, body/session correlation evidence or absence, and every
other evidence-only admission-record preimage. It contains no policy head,
profile, profile deadline, handling, effect, or meet value. After constructing
the admission record from that exact pending state, a second compare-and-swap
stores its digest or one closed rejected terminal result. The same local durable
transaction persists the generic state commit and, for admission, the post-CAS
`HaldirAssessmentAdmissionCurrentnessReceipt`; neither receipt is content inside
the installed head. Only that current winner can issue the record and
currentness receipt.

A same-digest concurrent or later loser discards any locally computed stamps or
record and returns or query-resumes the winner's pending/final admission and
disposition from `InstalledHaldirAssessmentReceiverStateSelector`; it never
creates another admission record. A different digest at that position installs
or returns the exact conflict result. A crash after key reservation but before
record storage reconstructs only from the durable winning preimage and advances
the same head.

The separate policy authority durably reserves the first admission-digest
delivery in a `HaldirPolicyIngressReservationFact`, installs H1/C1 without an
ingress-stamp dependency, then constructs the one post-C1
`HaldirPolicyIngressStamp`. It never trusts a receiver-supplied head or profile.
The profile-selected H2 barrier or no-profile terminal H2 is the first policy
head that binds the stamp. After a crash following any policy compare-and-swap
but before result/disposition persistence, policy-authority recovery returns the
already installed commit receipt/current-head ancestry and receiver recovery
finalizes the original disposition; neither can apply the restriction twice. A
crash after H1 but before H2 reconstructs the same stamp from the fact and C1
without changing H1, profile, deadline, or evidence bytes.

Assessor restart creates a fresh registered incarnation; the identifier never
resets per assessment. State loss, sequence exhaustion, or incarnation-reuse
uncertainty stops publication. The receiver head retains bounded high-water,
retired-incarnation, and unfinished-operation evidence. Before safe replay state
would be evicted, one authenticated rotation transition commits a terminal
retained root and a new producer/manifest security context that cannot accept an
old incarnation, or it disables the affected profile/deployment. Missing
rotation evidence cannot free capacity. A sequence reset or same identity with
different content rejects.

Producer UTC issue/expiry values are audit and declared-duration fields, not
Haldir monotonic freshness authority. The receiver admission record stamps only
its own receive time and clock incarnation. The policy authority independently
stamps its receipt in its own clock and derives the profile not-after no later
than its local receive time plus the profile maximum live duration. The receiver
clock cannot select or extend that deadline. Deployment/source age is eligible
only when the profile supplies an authenticated bounded mapping from the
assessment scope's terminal clock domain to the policy-authority clock, including
uncertainty and maximum source age. Without that mapping, evidence is
record-only. Restart never copies a numeric deadline into a new clock
incarnation; an authenticated conversion must prove no extension or the evidence
expires.

Observer and assessor credentials, principals, key roots, processes, manifests,
routes, replay state, and role-owned queues are disjoint. Their only edge is the
one-way immutable publication-record handoff above, with its own authority,
audience, ledger, and bounds; it exposes neither role's credential, bus handle,
or mutable store. Core wildcard subscriptions do not match extension routes.

Haldir uses three separate deployable targets/processes. The assessment receiver
owns extension ingress, raw evidence, assessor replay, first-ingress reservation,
admission records, and external dispositions; it has no NCP command credential.
The Haldir policy-state authority owns installed monitor profiles,
the integrated base-policy decision core, local-intent replay,
`HaldirPolicyStateHead`/selector, deny latches, assessment-evaluation
single-flight state, command-publication reservations/fences, and policy commit
receipts; it has neither extension-ingress nor NCP command credential. The
commander owns intent-to-command conversion, body authority, stream allocation,
command publication, and body-disposition reconciliation; it cannot evaluate or
store base/monitor policy and has no raw assessment, admission, replay, or
profile store. The pre-integration standalone Gate remains a separate deployment
mode; it is not a fourth process in this integrated topology.

The receiver sends only immutable `AssessmentAdmissionRecord` plus its exact
`HaldirAssessmentAdmissionCurrentnessReceipt` through one narrow authenticated
audience-bound API to the policy authority. The authority returns
only the admission-bound `HaldirPolicyIngressStamp` and later bounded
authenticated `HaldirPolicyEvaluationResult`; neither exposes the profile store
or mutable policy state. The receiver uses that result to finalize the external
assessment disposition.

The integrated policy authority also owns the authenticated local-intent/source
ingress described by ADR-011. Native V2 freshness is receiver-issued. Before an
enrolled sender constructs an intent, the authority idempotently installs
`HaldirIntentFreshnessGrantCommitment` through its sole policy selector. The
commitment binds a body-generated random grant/operation ID, authority and
intended ingress endpoint, direct `AuthorityRealmKey`, complete
plant-session foreign key and security context, authenticated sender,
route/audience, intent stream epoch, bounded non-overlapping slot range, allowed
intent/action classes, authority-clock incarnation, issue tick, exclusive
maximum not-after tick and duration/capacity ceilings. Post-CAS
`HaldirIntentFreshnessGrantInstallationReceipt` exports the exact installed
`HaldirIntentFreshnessGrant`. The request key is stable, but the caller selects no
ID, slot range, authority time or deadline. Reply loss and restart query/import
the exact installed result and cannot allocate or revive another range. The
grant proves freshness capacity only; it grants no policy permission, command
authority or NCP lease.

The signed V2 preimage binds one `HaldirIntentFreshnessProof` over that exact
grant and selected slot. Canonical `requested_validity_ms` is a positive bounded
integer; checked multiplication by 1,000,000 yields its duration in nanoseconds.
Zero, overflow or a value above the grant/profile ceiling rejects. The exclusive
authority-clock deadline is
`min(grant.maximum_not_after,
checked_add(grant.issue_tick, requested_validity_duration_ns))`. Sender-local
`controller_t_ns` remains audit-only and is never compared with the authority
clock. Arrival, reservation, policy evaluation, retry or restart cannot start or
refresh this deadline. The unchanged deadline limits Haldir ingress acceptance,
source admission, policy decision commit and every later publication handoff;
equality is expired.

Engram sends the immutable V2 bytes through the ADR-011 durable intent outbox and
two-cutoff protocol. Its earlier attempt cutoff is a conservative mapped image of
the Haldir deadline minus the qualified worst-case duration through actual Haldir
ingress acceptance. The authoritative cutoff remains the unchanged Haldir-clock
deadline. A qualified `HaldirIntentTransportGateState` fences security/session/
retirement cuts. At the receiver acceptance linearization point, the endpoint
atomically checks the exact grant/slot/deadline and gate epoch and executes
`RESERVE_LOCAL_INTENT_INGRESS`; acceptance and durable reservation cannot be split
by a queue or crash. It emits queryable
`HaldirIntentIngressAcceptanceDeadlineEvaluationReceipt`. Equality or later time
cannot reserve. Timeout, cancellation, broker enqueue or sender return without
authenticated endpoint evidence is ambiguous, not rejection or acceptance; retry
uses the same bytes/key/grant/slot/deadlines.

At that endpoint, the policy authority first bounds and strictly decodes the
protected intent envelope and constructs `HaldirIntentIngressReservationFact`
over the exact bytes/digest, direct realm and complete session foreign key,
authenticated actor, actual route and audience, grant/slot and effective
deadline, transport acceptance/gate evidence, replay and idempotency identities,
policy/security/clock context, expected prior policy head, and one fresh
single-flight key. The fact contains no source result, decision, successor,
selector, or receipt. `RESERVE_LOCAL_INTENT_INGRESS` compare-and-swaps that exact
pending preimage into `HaldirIntentIngressState` and emits the generic policy
commit plus `HaldirIntentIngressReservationCommitReceipt`. A losing reservation
authorizes nothing; exact query returns its winner.

From the installed reservation, the authority verifies actor/audience/manifest/
unchanged effective deadline and the exact original or trusted-projection
transfer, then constructs
receipt-free `HaldirIntentSourceAdmissionFact` or an explicit source-absent fact.
The fact binds the direct realm, complete session foreign key, reservation,
exact prior policy head and source evidence but no successor, selector or
receipt. `ADMIT_INTENT_SOURCE` consumes that pending reservation, and its policy
successor binds the fact. Only after its compare-and-swap do the generic policy
commit and
`HaldirIntentSourceAdmissionReceipt` bind the fact, prior/installed policy heads
and selector version.

If verification rejects, the unchanged exclusive deadline elapses, or the
authenticated caller cancels before source admission, receipt-free
`HaldirIntentIngressRejectionFact` binds the exact installed reservation, bytes,
reason, and event context. `TERMINALIZE_LOCAL_INTENT_INGRESS_WITHOUT_ADMISSION`
atomically removes the pending entry and installs its permanent replay tombstone
plus post-CAS terminal receipt. It creates no source-admission receipt or policy
decision. A same-digest retry returns the installed admission or terminal
outcome; conflicting content, historical/sibling state, a losing fact, or
missing source evidence cannot reach a decision. Neither the commander nor an
inline attachment can create these policy-authority receipts.

A policy ALLOW is represented only by authority-signed
`HaldirPolicyDecisionRecord` for the commander audience. It binds the exact
direct realm and complete session foreign key, authenticated local-intent
bytes/digest, actor/replay operation, requested action and
`HaldirIntentSourceAdmissionReceipt`, exact policy inputs, publication history
and base/monitor head, decision/result/reason, authority clock evaluation time
and exclusive validity deadline, intent/decision single-flight identity, and
expected prior policy-state head. It contains no future NCP stream epoch/
sequence, frame/command ID, protected command digest, body lease, NCP route,
queue slot, or publication claim.

For ALLOW, the decision deadline is no later than both the unchanged effective
intent deadline and the policy profile's local maximum. The decision CAS evaluates
strict-before against that same intent deadline. Equality or later time can only
install the typed expired/no-publication outcome; it cannot turn timely ingress
acceptance into a fresh ALLOW. Source admission, evaluation latency, queueing and
policy restart never extend the intent grant.

The authority constructs the decision record before its state successor, then
one compare-and-swap atomically consumes the pending intent/source admission,
commits the decision digest and history inputs in the successor
`HaldirPolicyStateHead`, and emits `HaldirPolicyDecisionCommitReceipt` over
prior/installed heads and selector version. The record excludes the installed
head/receipt, so the graph is acyclic. The commander requires both record and
commit/currentness proof. The existing mixed `DecisionReceiptV1` cannot cross
this process boundary. DENY creates no policy-allow publication authorization.

Every attempted publication carries one closed
`HaldirPublicationAuthorizationOrigin`:

- `POLICY_ALLOW_DECISION` binds the exact current
  `HaldirPolicyDecisionRecord`, including its authority-clock exclusive validity
  deadline and either its exact policy head or a bounded
  `HaldirPermissionPreservingHeadProof`; or
- `AUTHENTICATED_FAIL_SAFE_TRIGGER` binds a durable watchdog/restart/operator
  fail-safe trigger, installed manifest/plant-profile/session/security rule,
  trigger freshness evidence, and exact HOLD or ESTOP action. It forbids Active,
  ALLOW/result fields and synthetic policy decisions. Because it is restrictive,
  it remains eligible under policy DENY. It still requires verified body
  authority for HOLD or the exact permitted ESTOP lease-absence rule.

This Haldir-originated restrictive path is best-effort while the policy authority,
its store, and the narrow API are available. Their loss blocks new Active and
lease renewal; it does not prove that Haldir published HOLD or ESTOP. Crebain/body
watchdog and action-buffer behavior remain the independent final actuator
authority under the exact plant profile. This fallback grants no publication
authority or bypass, and live evidence must measure it. If a deployment requires
Haldir-originated restrictive publication
while the policy authority is unavailable, it needs a separately designed,
preinstalled body/profile-bound restrictive capability and qualification. No
implicit bypass or cached ALLOW is permitted here.

A historical or merely signed permission snapshot never authorizes command
publication. The commander owns canonical
`HaldirCommanderPublicationStateHead`, which binds commander principal/instance/
security, direct `AuthorityRealmKey`, complete session foreign key, never-reused
state incarnation and version, current `commander_clock_incarnation`, local
body-authority/lease state, NCP security, stream allocator and bounded capacity,
pending/terminal preflights, consumed positions, exact bounded commander-local
NCP outbox entries, installed external NCP transport attempts, dispositions and
retry rights, `HaldirCommanderQueueTransitionFact` values, and prior head. Each
queue fact is constructed before its successor and binds the exact local outbox
item or cancellation, preflight, slot and closed local outcome, but no
prior/installed commander head, selector, commit or later resolution. Each
transport attempt and disposition has a separate immutable fact and installed
lineage described below. The head excludes its own digest/receipt and every
successor/selector digest.
Its closed root phase is
`UNINITIALIZED | OPEN | RETIRING_AWAITING_POLICY_CLOSURE |
RETIRED_DRAIN_ONLY | RETIRED`. Only `OPEN` can install a new preflight or consume
a new stream position. Retirement is one-way; neither closure-wait nor
drain-only state grants publication authority.
`InstalledHaldirCommanderPublicationSelector` is the
only commander currentness root. Body-authority/security/allocator/capacity
changes, preflight, cancel, local outbox transfer, transport attempt/disposition
and retry closure all compare-and-swap it and emit
`HaldirCommanderPublicationStateCommitReceipt`.
`COMMANDER_PUBLICATION_GENESIS_FROM_UNINITIALIZED` consumes one parent-created
never-used selector; missing/recreated/rolled-back state blocks publication.

Commander preflight and local release deadlines use the distinct
`HaldirCommanderReleaseDeadlineConditionIntent`, intent-set root,
`HaldirCommanderCommitTimeReleaseDeadlineCondition`, and evaluation-set root
types. Their closed purposes are `AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE` and
`EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE`; their closed kinds are
`PREFLIGHT_INSTALL_LOCAL_NOT_AFTER | BODY_LEASE_RELEASE_LOCAL_NOT_AFTER |
POLICY_ORIGIN_RELEASE_LOCAL_NOT_AFTER |
POLICY_HANDOFF_RELEASE_LOCAL_NOT_AFTER | COMMANDER_RELEASE_LOCAL_NOT_AFTER |
NCP_TRANSPORT_ATTEMPT_NOT_AFTER | NCP_TRANSPORT_ACCEPTANCE_NOT_AFTER |
NCP_TRANSPORT_RETRY_RIGHT_NOT_AFTER`. They use a commander-release digest domain
and cannot substitute for observer, body, policy, retention or quiescence
conditions. Authenticated no-extension mappings derive the body/policy/transport-
boundary deadlines into the applicable local clock; raw numeric values from
different clocks are never compared. The fact and candidate bind the exact intent
root. The winning generic and specialized commits and event receipt bind the
complete commit-time evaluation root using the ADR-004 integrated-manager or
qualified-completion-bound proof. Static Crebain, policy-release, preflight or
attempt-start receipts remain required inputs but cannot prove that a later local
release or transport acceptance beat its deadline.

A commander-clock restart constructs receipt-free
`HaldirCommanderClockRestartTransitionFact` and advances that same selector. Its
successor either proves an authenticated no-later mapping for every pending
preflight, local-outbox, transport-attempt and retry deadline or marks each
remotely releasable preflight
`CANCEL_AWAITING_POLICY_CLOSURE` while preserving its complete possible-release
obligation and restrictive fail-safe evidence. It terminalizes an unsent outbox
item whose attempt or acceptance cutoff cannot be mapped without extension; it never sends
that item under the new clock. Only a later authenticated
policy-closure outcome can terminalize its cancellation branch. The post-CAS
`HaldirCommanderClockRestartCommitReceipt` binds the fact, prior/installed
commander heads, selector and generic commit. Without exact restore or that
transition, Active publication remains closed and only a fresh post-restart
preflight under the new incarnation can proceed.

The commander first constructs receipt-free
`HaldirCommanderPublicationPreflight`. It binds the authorization-origin union,
operation, exact complete
protected command bytes/digest/length, actual route, body session/generation,
direct `AuthorityRealmKey`, exact complete session foreign key, exact installed
ADR-007 `BodyCommandFreshnessGrant` and selected slot/proof, verified lease
term/ID/holder or permitted ESTOP absence, stream epoch/sequence, Haldir/NCP
security contexts, commander clock/deadline, and one reserved bounded output
slot. It contains no commander successor, selector or commit receipt. A command
without a current matching body grant cannot enter preflight; Haldir cannot
self-issue or extend one.
The commander successor binds the preflight and consumes the stream position.
After that compare-and-swap, a distinct
`HaldirCommanderPreflightInstallationReceipt` binds the preflight, prior and
installed commander heads, selector version, generic commander commit and
consumed position. A losing or sibling preflight has no installation receipt and
cannot consume policy state.

An installed preflight has a closed commander-side phase:
`PREFLIGHT_OPEN | CANCEL_AWAITING_POLICY_CLOSURE |
POLICY_RELEASED_OBLIGATION | TERMINAL`. No local observation can move
`PREFLIGHT_OPEN` directly to canceled `TERMINAL`, because the independently
serialized policy authority may already be committing a release from the
installation receipt. A local context, body-authority, security, deadline or
operator cut first constructs receipt-free
`HaldirCommanderPreflightCancellationIntent`. It binds one exact preflight key,
preflight and installation receipt, operation, exact prior commander head/
selector version, every local queue/release fact known at the cut, and one
closed cause: `LOCAL_CONTEXT_INVALIDATED | BODY_AUTHORITY_INVALIDATED |
SECURITY_INVALIDATED | COMMANDER_DEADLINE_ELAPSED |
LOCAL_OPERATOR_CANCELED | CLOCK_CONTINUITY_UNAVAILABLE`. Unknown, combined or
caller-defined causes reject. `BEGIN_HALDIR_COMMANDER_PREFLIGHT_CANCELLATION` installs
`CANCEL_AWAITING_POLICY_CLOSURE`, blocks all new authority from that preflight,
and retains its position, slot and possible-release obligation.

The policy authority resolves that intent through its sole selector with
receipt-free `HaldirPolicyPreflightCancellationClosureFact` and
`CLOSE_HALDIR_COMMANDER_PREFLIGHT_CANCELLATION`. The shared closed
`HaldirPolicyPreflightClosureOutcome` is exactly
`CANCELED_BEFORE_POLICY_RELEASE | RELEASED_POLICY_OUTBOX_OBLIGATION`. The first
branch binds closed `HaldirPolicyPreflightCancellationEvidence` as either
`KEYED_POLICY_CANCELLATION` or
`TERMINAL_POLICY_AUTHORITY_NONRELEASE`. While policy is live or
`RETIRED_DRAIN_ONLY`, the keyed branch consumes an exact pending reservation or
installs a tombstone for a preflight that has not arrived, permanently
preventing delayed reservation or release. Cancellation closure remains legal
in drain-only solely as a restriction; it cannot create ALLOW, a reservation or
an outbox item. The second outcome binds the exact release, immutable outbox
item and worst-case history entry that won first. The post-CAS
`HaldirPolicyPreflightClosureReceipt` binds the intent, fact,
prior/installed policy heads, selector version, generic policy commit and exact
outcome. This is the per-key outcome receipt; the bulk retirement form emits one
`HaldirPolicyPreflightClosureReceipt` per outcome and one complete-
set receipt.

Policy `RETIRED` is immutable, so it emits no new closure CAS or receipt. For a
preflight that reaches the commander after policy finalization, the terminal-
authority evidence branch instead binds the exact installed terminal policy
head, its `HaldirPolicyRetirementFinalizationReceipt`, complete released-key/
outbox inventory and exact-key nonmembership proof. That proof is valid only
when the terminal ancestry and selector currentness verify and the lineage has
no successor. Exact-key membership selects
`RELEASED_POLICY_OUTBOX_OBLIGATION`, never nonrelease. A terminal status string,
partial inventory, historical drain-only head or newly signed assertion cannot
substitute.

`HaldirCommanderPreflightClosureImportFact` binds that authenticated outcome.
`IMPORT_HALDIR_PREFLIGHT_POLICY_CLOSURE` terminalizes only the cancellation
branch. In the same commander compare-and-swap, that branch emits the
`POLICY_CANCELED_BEFORE_RELEASE` variant of
`HaldirCommandPublicationResolution`. Its typed content binds the cancellation
intent, exact policy closure fact and receipt, branch-specific cancellation
evidence, policy selector currentness, exact preflight/stream position,
prior/installed commander heads, selector version and generic commander commit.
It forbids an authorization origin, policy release, outbox item, command bytes,
queue-transition fact or queue item. The independently verified cancellation
preimage and evidence select this variant; a result label does not.

The released import branch emits no publication resolution. It maps the
preflight to `POLICY_RELEASED_OBLIGATION` and preserves the exact release and
item for queue resolution, feedback and retention; it cannot call the preflight
canceled. `HaldirCommanderPreflightClosureImportReceipt` binds the fact, exact
prior/installed commander heads, selector version and generic commander commit
in both branches and additionally binds the cancellation resolution only in the
cancellation branch. Reply loss queries the same policy operation. A closure
deadline or unreachable policy leaves the non-authorizing
`CANCEL_AWAITING_POLICY_CLOSURE` state retained and raises an alarm; it never
manufactures either outcome.

Commander clock restart and every restrictive body-authority or security cut
apply this same rule to the canonical complete affected-preflight set. They can
atomically mark each key `CANCEL_AWAITING_POLICY_CLOSURE`, but they cannot erase
or terminalize a remotely releasable preflight. A clean no-extension restart may
preserve an open preflight only when it preserves the exact installation and
both local deadline meanings; otherwise each affected key requires the policy-
serialized closure above.

Commander retirement is a distributed terminal handshake, not a local
classification of policy state. Before changing the root, the commander
constructs receipt-free `HaldirCommanderRetirementIntent`. It binds the
retirement operation and authenticated cause, exact prior `OPEN` commander head
and selector version, and the canonical complete keyed set of every installed
preflight that does not already have either an authenticated policy-cancellation
outcome or an exact policy release plus terminal local resolution and feedback.
A merely local cancellation or terminal label does not remove a key from this
set.
For each key it binds the exact preflight, installation receipt, consumed stream
position, output slot, and any locally known policy release/local-outbox state.
It also binds the complete terminal-preflight, local outbox, active and terminal
NCP transport-attempt lineage, disposition, immutable retry policy/right,
body-reconciliation, feedback and retention inventories that the successor must
preserve. Every active attempt is keyed to its exact outbox obligation and
stable idempotency key. It contains no
successor, selector digest, commit or policy outcome.

Before `BEGIN_HALDIR_COMMANDER_PUBLICATION_RETIREMENT` can compare-and-swap, it
obtains the transport boundary's fence receipt for the current `OPEN_NORMAL`
epoch and binds it into the retirement intent. The CAS changes the commander root
from `OPEN` to `RETIRING_AWAITING_POLICY_CLOSURE`, binds that intent/fence, and
immediately rejects new preflights, stream positions, outbox transfers, attempt
starts, retry exercise and publication work. Acceptance proved before the fence
remains an exact resolution obligation; no old-epoch acceptance can occur after
it. The waiting phase permits only
`RESOLVE_HALDIR_NCP_TRANSPORT_ATTEMPT` for an exact active attempt already in the
intent. That resolution can derive, but not exercise, only the retry right
mechanically allowed by the immutable pre-retirement policy, result and stable
idempotency key. Its successor preserves the intent and exact lineage. Its
post-CAS `HaldirCommanderRetirementIntentInstallationReceipt` proves only that
local closure began. The commander cannot infer “not released” from a missing
local policy result because the policy selector can concurrently release from
an earlier preflight installation receipt.
The later policy-closure import binds the installed intent ancestry and
reconciles the advanced current commander head, so a disposition resolved while
waiting cannot be lost or replaced.

The policy authority receives the exact installed retirement intent and receipt
through its narrow authenticated API. It constructs receipt-free
`HaldirPolicyCommanderRetirementClosureFact` over its exact prior policy head
and selector version and the intent's complete preflight-key set. The closed
per-key `HaldirPolicyPreflightClosureOutcome` is exactly one of:

- `CANCELED_BEFORE_POLICY_RELEASE`, which installs a permanent keyed policy
  cancellation tombstone. It consumes an exact pending reservation when one
  exists and also applies when the delayed preflight has never reached policy;
  the tombstone makes every later reservation or release for that key reject;
  or
- `RELEASED_POLICY_OUTBOX_OBLIGATION`, which binds the exact already installed
  release, immutable outbox item and worst-case history entry that the commander
  must reconcile and drain.

`CLOSE_HALDIR_COMMANDER_PREFLIGHTS_FOR_RETIREMENT` compare-and-swaps the sole
policy selector. One case contains two canonical, pairwise-disjoint key
partitions: cancellation and released obligation. Their union must equal the
intent's complete affected-key set. `ABSENT` or `RESERVED` policy state can enter
only the cancellation partition and installs the exact tombstone;
release-outbox state can enter only the released partition and is preserved
byte-for-byte. Thus one bulk CAS can contain both outcomes but no key can have
zero or two outcomes. A release that wins first is returned as the released
branch. A closure that wins first installs the cancellation branch before any
delayed reservation or release can win. The transaction emits one keyed
`HaldirPolicyPreflightClosureReceipt` for each key. The post-CAS
`HaldirPolicyCommanderRetirementClosureReceipt` binds the fact, intent and its
installed receipt, exact prior/installed policy heads and selector version,
generic policy commit, canonical key-to-outcome bijection and complete per-key
receipt bijection. A partial, overlapping, duplicate, stale or caller-summarized
result rejects.

The commander then constructs
`HaldirCommanderRetirementClosureImportFact` from either that complete policy
receipt or, when policy is already immutable `RETIRED`, the exact installed
terminal head/finalization receipt and complete released-key inventory. The
terminal branch derives cancellation only from exact-key nonmembership and
imports exact-key membership as a released obligation. It emits no policy-side
transition or receipt.
`IMPORT_HALDIR_POLICY_RETIREMENT_CLOSURE` compare-and-swaps the commander
selector, terminalizes every cancellation outcome, and imports every released
outbox obligation without changing its bytes, identity, history, output slot or
authorization origin. The same atomic bundle emits one keyed
`HaldirCommandPublicationResolution` with result
`POLICY_CANCELED_BEFORE_RELEASE` for every cancellation-partition member. Each
resolution has the same branch-specific required and forbidden fields as the
ordinary cancellation import above and binds either its exact keyed policy
closure receipt or the terminal-policy nonmembership proof. Released-obligation
members emit no publication resolution until their later queue transfer. Its
post-CAS
`HaldirCommanderRetirementClosureImportReceipt` binds the exact prior/installed
commander heads, selector version, generic commander commit and complete
key-to-outcome import, plus an exact cancellation-key-to-resolution bijection and
an exact released-key no-resolution partition. The root always enters
`RETIRED_DRAIN_ONLY`, including
when the canonical obligation inventory is empty. Import never installs
`RETIRED` directly. The import fact partitions released transport work into
`ACTIVE_ATTEMPT_RESOLVE_ONLY`, `REMOTE_ESTOP_DRAIN_STARTABLE`, and
`UNSENT_RETIREMENT_REJECTION`. The ESTOP partition has cardinality at most one
and requires the exact fail-safe authorization origin, immutable command bytes,
body-installed one-use ESTOP-only grant/slot, stable key and unchanged two
transport deadlines. Active, HOLD, ordinary policy ALLOW, missing grant proof and
every second key are structurally forbidden. An unsent rejection binds the old-
epoch fence and proves that no attempt/acceptance preceded it; it cannot claim
body rejection or application.

`RETIRED_DRAIN_ONLY` permits the exact local-outbox queue transition for a
released obligation, `RESOLVE_HALDIR_NCP_TRANSPORT_ATTEMPT` for an exact active
attempt already in the retirement inventory, disposition/feedback
reconciliation, and safe-retention work. It permits START or retry only for the
single `REMOTE_ESTOP_DRAIN_STARTABLE` key. Before that edge is usable,
`OPEN_HALDIR_RETAINED_ESTOP_TRANSPORT_DRAIN` verifies the installed drain head and
asks the boundary to install a fresh never-used `OPEN_DRAIN` epoch bound to the
ESTOP-obligation and allowed-key roots. A receipt-free activation fact binds the
installed drain head/selector and roots; the boundary receipt binds that fact/
epoch, the selector successor binds both, and the post-CAS receipt binds the
installed successor. Any removal/finalization transition first
fences the drain epoch. Acceptance before that fence remains a resolution
obligation; acceptance after it is impossible. Empty and resolve-only inventories
never open a drain gate. If activation wins but the selector CAS loses,
`RECONCILE_HALDIR_OPEN_DRAIN_ACTIVATION` binds the exact fact/receipt, current
drain-only selector/head, unchanged roots and boundary query. It either installs
that already-effective epoch into currentness or fences it; mismatch/unknown
starts nothing, cannot widen roots and never becomes `OPEN_NORMAL`.

Drain cannot install a preflight, consume a new stream position, acquire a new
policy release, widen a retry right, widen a result, re-sign content or publish
changed bytes. Resolution of an in-inventory attempt can derive only the exact
right allowed by its immutable pre-retirement retry policy; another source cannot
mint one. After all retained outbox, transport-attempt, retry, feedback and
body-reconciliation obligations are terminal and required
retention is satisfied, or immediately for a proved canonical empty inventory,
receipt-free
`HaldirCommanderRetirementFinalizationFact` inventories the complete closure and
tombstone roots with exact key-to-terminal-outcome bijections. It proves no
active transport attempt and no open retry right remain.
`FINALIZE_HALDIR_COMMANDER_PUBLICATION_RETIREMENT` installs
`RETIRED` after fencing any `OPEN_DRAIN` epoch;
`HaldirCommanderRetirementFinalizationReceipt` binds that fact, exact
prior/installed heads, selector version and generic commit.

A bounded closure deadline limits retries and raises an operational alarm; it
does not manufacture a cancellation acknowledgement. Reply loss queries the
same policy selector and operation. Policy unavailability, ambiguous policy
state, deadline expiry or restart leaves the commander non-authorizing in
`RETIRING_AWAITING_POLICY_CLOSURE`, with the complete possible-release set
retained. It cannot reach `RETIRED` or discard a possibly released item until an
authenticated complete policy-closure receipt is installed.

Policy reservation and release deadlines use the distinct
`HaldirPolicyReleaseDeadlineConditionIntent`, intent-set root,
`HaldirPolicyCommitTimeReleaseDeadlineCondition`, and evaluation-set root types.
Their closed purposes are `AUTHORIZATION_BEFORE_EXCLUSIVE_DEADLINE` and
`EXPIRY_AT_OR_AFTER_EXCLUSIVE_DEADLINE`; their closed kinds are
`POLICY_DECISION_RESERVATION_NOT_AFTER |
FAIL_SAFE_TRIGGER_RESERVATION_NOT_AFTER |
POLICY_ORIGIN_RELEASE_NOT_AFTER | POLICY_HANDOFF_RELEASE_NOT_AFTER`. They use a
Haldir-policy-release digest domain and cannot substitute for evaluation,
observer, body, commander, retention or quiescence conditions. Reservation and
release facts and candidates bind the exact applicable intent root. The winning
generic and specialized commits and reservation/release receipt bind the exact
complete commit-time evaluation root. Each uses the ADR-004 integrated-manager
or qualified-completion-bound proof through durable commit. A decision receipt,
ingress timestamp or earlier policy-clock sample is not a release-time proof.

Through a different narrow audience-bound API, the commander sends that immutable
preflight, its installation receipt and exact protected bytes to the policy
authority. The authority first verifies both and then installs one pending
`HaldirCommandPublicationReservation` through
`InstalledHaldirPolicyStateSelector`. For `POLICY_ALLOW_DECISION`, it verifies
the exact current or permission-preserving policy ancestry and that authority
time is commit-bound strictly before the decision validity deadline through
`POLICY_DECISION_RESERVATION_NOT_AFTER`. For
`AUTHENTICATED_FAIL_SAFE_TRIGGER`, it verifies the exact restrictive action and
current installed fail-safe rule and the corresponding commit-bound trigger
freshness condition without requiring ALLOW. It stamps its own
clock/receive time and derives a separate handoff not-after no later than that
receive time plus the bounded handoff policy. The reservation binds the
preflight, its installation receipt and consumed position as well as both the
origin-validity deadline and handoff not-after in the authority clock. Commander
and authority numeric clocks/deadlines are never compared; an authenticated
no-extension mapping can tighten but never replace either local check.

`HaldirPublicationFenceState` is subordinate state committed by the composite
policy head. Before a restrictive policy/profile/revocation transition can
compare-and-swap, the authority marks every affected policy-allow reservation
cancel pending. Fail-safe HOLD/ESTOP remains subject to its exact restrictive
rule. Release verifies current preflight/origin/head, absence of an applicable
retirement cancellation tombstone or other cancel, and
the complete strict-before evaluation pair
`POLICY_ORIGIN_RELEASE_NOT_AFTER` and `POLICY_HANDOFF_RELEASE_NOT_AFTER` in the
winning release bundle; equality with either deadline is expired. A
delayed commander cannot turn an expired ALLOW into a fresh handoff window.

The authority first constructs one receipt-free
`HaldirPolicyReleaseOutboxCommitment` over the authorization origin, both
authority deadlines, exact bytes/digest/length, route/audience/preflight, output
slot, direct `AuthorityRealmKey`, complete session foreign key, canonical
complete release-deadline intent root, and worst-case pending
`HaldirPublishedCommandHistoryHead` entry. It
contains no successor policy head, selector version, generic commit,
`HaldirCommandPublicationRelease`, or complete
`HaldirPolicyReleaseOutboxItem`. The candidate policy
successor binds that commitment and the pending history entry. After the
compare-and-swap, the generic policy-state commit and
`HaldirCommandPublicationRelease` bind the prior/installed composite heads,
selector version, commitment, authorization origin, both authority deadlines,
exact complete deadline-evaluation root, exact bytes/route/audience/preflight,
and pending history entry. The complete
`HaldirPolicyReleaseOutboxItem` binds the commitment, exact bytes, and post-CAS
release; the
successor never binds the complete item or either receipt.

One local durable transaction persists the installed successor, generic commit,
release, complete outbox item, and pending history entry together. Cancellation
first means no release or history entry. The winning outbox append and
pending-history installation are one policy-authorization
ownership-transfer linearization point; there is no crash cut at which bytes are
released but slew/duty history is absent. A later policy change orders after that
already released obligation and cannot rewrite it. The authority owns no NCP
credential, publisher, commander queue, lease state, or claim of actual network
enqueue.

The commander transfers only an authenticated current policy outbox entry into
its matching commander-local durable NCP outbox. The ordinary
`RESOLVE_COMMAND_QUEUE_TRANSFER` case consumes `PREFLIGHT_OPEN` plus the exact
authenticated policy release and immutable item. The cancellation- or
retirement-race case consumes `POLICY_RELEASED_OBLIGATION` plus the same release
and item. No normal release first enters the cancellation handshake, and no
local observation can synthesize either input.

Both cases first construct `HaldirCommanderQueueTransitionFact` over the exact
realm and session foreign key, preflight, policy item, stable
release/idempotency key, local outbox item or cancellation, complete
commander-release deadline-intent root, and one closed local result:
`CANCELED_BEFORE_LOCAL_NCP_OUTBOX` or
`RELEASED_TO_LOCAL_DURABLE_NCP_OUTBOX`. The candidate successor binds that fact.
The winning commander transaction rechecks realm/body/security/currentness and
evaluates the exact complete strict-before commander deadline set, then
compare-and-swaps the selector and atomically persists the successor, generic
commit, local outbox item when present, evaluation set and
`HaldirCommandPublicationResolution`. A local invalidation that wins first
selects cancellation and creates no item. A local outbox append that wins first
terminalizes the preflight and transfers ownership to the retained outbox entry.
There is no ambiguous result at this local atomic boundary.

Each released local outbox item carries two exclusive deadlines. Its
`NCP_TRANSPORT_ACCEPTANCE_NOT_AFTER` is the conservative minimum of the mapped
body-issued command-freshness-grant deadline, authenticated fail-safe-trigger or
policy-decision freshness, body-lease/local-release bound, policy-origin bound,
policy-handoff bound, and
`checked_add(commander_local_outbox_release_instant,
profile_max_ncp_transport_duration)`. The profile value is a duration, never an
absolute timestamp. Every member is represented in the transport-acceptance
clock domain through a qualified conservative no-later mapping. Its earlier
`NCP_TRANSPORT_ATTEMPT_NOT_AFTER` subtracts the qualified worst-case duration from
attempt installation through transport acceptance, including queue, call,
clock-mapping and completion uncertainty. START before that earlier cutoff is
necessary but never proves timely acceptance. An unavailable mapping, duration
upper bound or positive residual window fails closed instead of dropping a
member. The item, queue-transition fact, candidate, winning commit and resolution
bind the complete ordered source-bound set and both derived deadlines. Neither
retirement, drain-only recovery, retry, restart nor a later receive time can
refresh or replace them.

The local queue-transfer variants of `HaldirCommandPublicationResolution` bind
the fact, authorization origin, policy and commander prior/installed heads,
generic commander commit, selector versions, complete deadline evaluations,
exact bytes, and exactly one of the two local results above. The separate
`POLICY_CANCELED_BEFORE_RELEASE` variant is emitted only by the per-key or bulk
import event and has the exact forbidden fields specified above. Verified
preimage, typed evidence and required/forbidden shape derive the discriminant;
the label is never an authorization input. Every variant consumes the preflight
and stream position. Reply loss queries the installed selector and returns the
same item or cancellation. The construction order is authenticated release,
queue fact and intent root, candidate head, commit-bound evaluations, generic
commit, then resolution. No content-addressed object binds a later object that
binds it.

The commander-local outbox is not the external NCP transport. The qualified
adapter exposes durable `HaldirNcpTransportGateState` as
`OPEN_NORMAL(epoch, context) |
OPEN_DRAIN(epoch, retained_estop_obligation_root, allowed_key_root) |
FENCED(epoch, cause, receipt) | RETIRED`; epochs never repeat. A security/session/
generation/retirement cut obtains the boundary's
`HaldirNcpTransportGateFenceReceipt` before its commander-state CAS. An old-epoch
attempt cannot be accepted after that fence. Acceptance proved before the fence
can resolve afterward; missing order remains ambiguous and grants no success.
`OPEN_NORMAL` is forbidden in commander drain. `OPEN_DRAIN` contains at most the
one exact preclassified remote-ESTOP obligation bound to the body's preallocated
ESTOP-only grant/slot. It cannot accept Active, HOLD or an ordinary command key.

A boundary fence survives a losing commander-selector CAS. Receipt-free
`HaldirNcpTransportGateFenceFact` binds the expected selector/head, boundary
epoch/context, cut cause and affected keyed inventories; the boundary fence
receipt binds that fact/order. If the expected CAS loses,
`REBASE_HALDIR_NCP_TRANSPORT_GATE_FENCE_AFTER_LOSING_CAS` binds that exact fact/
receipt, newly queried current selector/head and unchanged sibling inventories,
then compare-and-swaps the commander selector to associate the already-effective
fence. It cannot roll back the fence, change cause, drop an obligation or reopen
normal transport. START remains disabled until rebase wins; a canceled cut needs
a separately qualified fresh normal epoch and complete terminal-obligation proof.

A worker first
constructs receipt-free `HaldirNcpTransportAttemptFact` over the exact immutable
outbox item/bytes, stable release/idempotency key, transport instance, fresh
bounded attempt identity, prior attempt lineage, the applicable installed retry
right or typed first-attempt absence, direct realm, exact current commander
security/session/generation, current transport-gate epoch, and the complete
attempt-start and acceptance deadline intent sets.
`START_HALDIR_NCP_TRANSPORT_ATTEMPT` compare-and-swaps the commander selector and
commit-bound evaluates the attempt-start set, rechecks the bound security/session/
generation/gate and installs one active attempt before any external call. Equality,
later time, changed currentness, a sibling worker, reused attempt identity,
changed bytes, missing retained outbox item or missing required predecessor retry
right cannot send. `OPEN_NORMAL` requires non-retired commander state;
`OPEN_DRAIN` requires the exact single ESTOP allowed-key membership. No other gate
variant can START.
The elapsed/currentness branch instead uses
`EXPIRE_HALDIR_NCP_OUTBOX_BEFORE_TRANSPORT` to install the typed terminal result
`EXPIRED_BEFORE_NCP_TRANSPORT_ATTEMPT`, its complete at-or-after/currentness
evidence and exact outbox tombstone without installing an attempt. The event and
its specialized receipt bind the prior/installed commander heads, selector,
generic commit, deadline evaluation and terminal outbox entry. A label or worker
clock sample cannot choose this branch.

The transport acceptance endpoint consumes the exact installed attempt, bytes,
stable key and gate epoch at most once. At its acceptance linearization point it
evaluates the unchanged complete
`NCP_TRANSPORT_ACCEPTANCE_NOT_AFTER` set and current gate/context. Strict-before
acceptance emits `HaldirNcpTransportAcceptanceDeadlineEvaluationReceipt` over the
attempt, bytes/key, endpoint, acceptance instant, complete evaluation and gate
state. Equality or later time cannot accept. An adapter that cannot make this
check atomic with acceptance, query the same key, or fence an old epoch keeps the
native commander role disabled.

After the call, receipt-free `HaldirNcpTransportDispositionFact` binds that
installed attempt and exactly one result:
`ACCEPTED_BY_NCP_TRANSPORT_BOUNDARY |
REJECTED_BEFORE_NCP_TRANSPORT_ACCEPTANCE |
AMBIGUOUS_AFTER_NCP_TRANSPORT`. `RESOLVE_HALDIR_NCP_TRANSPORT_ATTEMPT`
compare-and-swaps the same selector, terminalizes the attempt, installs its
disposition and emits `HaldirNcpTransportDispositionReceipt` over the fact,
prior/installed commander heads, selector version and generic commit.
`ACCEPTED_BY_NCP_TRANSPORT_BOUNDARY` requires exact authenticated transport
acceptance plus that matching strict-before acceptance-deadline receipt and gate
order. It proves only acceptance by the named transport boundary, not receipt,
admission or application by the NCP body.
`REJECTED_BEFORE_NCP_TRANSPORT_ACCEPTANCE` requires definitive authenticated
evidence that acceptance did not occur. A timeout,
future cancellation, dropped task or local return without endpoint proof is
ambiguous, not rejected. An installed attempt followed by a crash resolves
rejected only with definitive no-acceptance evidence; otherwise it remains
ambiguous. RESOLVE can commit after deadline expiry or a gate/security cut when
the selected branch proves its own evidence: accepted requires pre-deadline/pre-
fence acceptance, rejected requires definitive no-acceptance, and ambiguous
forbids either definitive proof. It never reverts to
`PREFLIGHT_OPEN`.

An ambiguous or rejected disposition creates another attempt only when the
transport proves same-key idempotency, the immutable retry policy permits the
exact predecessor/result, and a bounded installed retry right remains
commit-bound unexpired. Every retry also preserves the unchanged acceptance
deadline and evaluates the unchanged attempt-start cutoff; the earlier of the
start cutoff and retry right wins, and equality makes no call. The acceptance
endpoint still evaluates the unchanged acceptance cutoff. Retry authorization is another
commander-selector CAS; it cannot re-sign, reconstruct bytes, or derive a later
deadline. Without those facts, ambiguity remains a terminal transport
disposition and requires exact body-disposition
reconciliation before any policy history can be weakened. In drain-only, every
attempt that can have preceded the retirement fence remains query/resolve-only.
Every unsent non-ESTOP key and all of its retry rights terminalize without a call.
Only the exact preclassified one-slot ESTOP drain key can START or retry under its
receipted `OPEN_DRAIN` epoch, unchanged start/acceptance deadlines and same-key
idempotency. Drain cannot create fresh publication work.

The policy authority remains sole owner of published-command slew/duty history.
The commander returns authenticated, authority-audience
`HaldirCommandPublicationFeedback` bound to the direct realm, complete session
foreign key, authorization origin, preflight, policy release or cancellation,
local outbox resolution, exact current transport disposition and
body-disposition reconciliation when available. Before policy outbox release,
cancellation creates no history entry. At policy release, the atomic pending
worst-case entry makes every later history-dependent decision treat the attempt
as published. `CANCELED_BEFORE_LOCAL_NCP_OUTBOX` can clear it
only with exact proof that no local ownership transfer occurred. A local outbox
release, accepted transport-boundary or ambiguous transport remains worst-case
until definitive transport/body evidence justifies a narrower terminal history
result.

The authority uses its own feedback-receive time as the conservative effective
time unless an authenticated bounded mapping proves a no-later authority-clock
image. It never copies commander numeric time. Feedback compare-and-swaps the
same policy selector that the next decision uses. Duplicate same-digest feedback
returns the installed result; conflicting, missing, reordered or ambiguous
feedback preserves worst-case history. No released or ambiguous attempt can
vanish. The commander never receives admission/evaluation replay state, and the
policy authority never receives a transport credential or generic publisher. No
process can activate two role surfaces, and the local policy authority is not an
additional NCP peer.

Crebain may publish standard NCP frames and Galadriel extension data through
separate declarations and bounded non-blocking queues. Extension absence,
slowness, or overload cannot enter command/fail-safe queues. Policy-eligible
assessment evaluation shares the bounded policy-authority scheduler described
above; its qualified local claim is bounded nonstarvation, not zero delay.

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
  "schema_version": "1",
  "authority_realm_key": {
    "server_authority_principal_id": "ncp-authority-a",
    "stable_realm_id": "realm-a"
  },
  "manifest_digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "extension_schema_digest": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "producer_principal_id": "galadriel-assessor-a",
  "audience_principal_id": "haldir-assessment-receiver-a",
  "route": "realm-a/extension/org.sepahead.galadriel.assessment/sha256-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/plant-alpha",
  "plant_id": "plant-alpha",
  "logical_session_id": "plant-alpha",
  "observed_session_generation": "00000000-0000-4000-8000-0000000000a2",
  "assessor_incarnation_id": "00000000-0000-4000-8000-0000000000b7",
  "assessment_sequence": 18,
  "release_suite_identity": {
    "algorithm": "sha256",
    "domain": "galadriel-release-suite-v1",
    "encoding": "lowercase_hex",
    "digest": "f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1f1"
  },
  "release_suite_name_diagnostic": "standalone-advisory-v0.9",
  "lifecycle_outcome_evidence": {
    "assessment_lineage_head_attachment": {
      "attachment_id": "assessment-lineage-head-18",
      "digest": "sha256:1515151515151515151515151515151515151515151515151515151515151515",
      "byte_length": 2048,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-lineage-head+json"
    },
    "lineage_commit_receipt_attachment": {
      "attachment_id": "lineage-commit-receipt-18",
      "digest": "sha256:1717171717171717171717171717171717171717171717171717171717171717",
      "byte_length": 1024,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-lineage-commit+json"
    },
    "signing_current_lineage_head_attachment": {
      "attachment_id": "signing-current-lineage-head-18",
      "digest": "sha256:1616161616161616161616161616161616161616161616161616161616161616",
      "byte_length": 2048,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-lineage-head+json"
    },
    "current_selector_attestation_attachment": {
      "attachment_id": "current-selector-attestation-18",
      "digest": "sha256:1414141414141414141414141414141414141414141414141414141414141414",
      "byte_length": 1024,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-current-selector+json"
    },
    "lineage_ancestry_or_compaction_proof_attachment": {
      "attachment_id": "lineage-currentness-proof-18",
      "digest": "sha256:1313131313131313131313131313131313131313131313131313131313131313",
      "byte_length": 4096,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-head-chain+json"
    },
    "ncp_source_authority_bundle_attachment": {
      "attachment_id": "ncp-source-authority-bundle-18",
      "digest": "sha256:1212121212121212121212121212121212121212121212121212121212121212",
      "byte_length": 65536,
      "media_type": "application/vnd.sepahead.ncp-source-authority-bundle+json"
    },
    "receipt_identity": {
      "algorithm": "sha256",
      "domain": "galadriel-ncp/lifecycle-receipt/v0.9\u0000",
      "encoding": "lowercase_hex",
      "digest": "1818181818181818181818181818181818181818181818181818181818181818"
    },
    "receipt_attachment": {
      "attachment_id": "lifecycle-receipt-18",
      "digest": "sha256:1919191919191919191919191919191919191919191919191919191919191919",
      "byte_length": 2048,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-receipt+json"
    },
    "assessment_vector_identity": {
      "algorithm": "sha256",
      "domain": "galadriel-ncp/lifecycle-assessment/v0.9\u0000",
      "encoding": "lowercase_hex",
      "digest": "1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c1c"
    },
    "raw_assessment_vector_attachment": {
      "attachment_id": "raw-assessment-vector-18",
      "digest": "sha256:1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a",
      "byte_length": 32768,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-assessments+json"
    },
    "lifecycle_projection_mapping_receipt_attachment": {
      "attachment_id": "lifecycle-projection-mapping-18",
      "digest": "sha256:1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b1b",
      "byte_length": 4096,
      "media_type": "application/vnd.sepahead.galadriel-lifecycle-projection-map+json"
    },
    "assessments": [
      {
        "kind": "EVALUATED_DEFAULT_REPORT",
        "track_id": 7,
        "fusion_seq": 901,
        "history_reset": false,
        "assessment_scope": {
          "producer_id": "plant-alpha-camera",
          "session_id": "plant-alpha",
          "epoch_id": "00000000-0000-4000-8000-0000000000c1",
          "stream_id": "front-camera",
          "state_generation": 41,
          "terminal_sequence": 901,
          "terminal_timestamp_ms": 42000,
          "clock_domain": "monotonic_process"
        },
        "assessment_binding_identity": {
          "algorithm": "sha256",
          "domain": "galadriel-assessment-binding-v2",
          "encoding": "lowercase_hex",
          "digest": "abababababababababababababababababababababababababababababababab"
        },
        "ordered_observation_digest": "sha256:acacacacacacacacacacacacacacacacacacacacacacacacacacacacacacacac",
        "observation_count": 64,
        "adapter_scope_mapping_receipt_attachment": {
          "attachment_id": "adapter-scope-mapping-receipt-18-0",
          "digest": "sha256:adadadadadadadadadadadadadadadadadadadadadadadadadadadadadadadad",
          "byte_length": 4096,
          "media_type": "application/vnd.sepahead.galadriel-ncp-scope-map+json"
        },
        "report_evidence": {
          "report_family": "galadriel_default_report_v1",
          "assessment_vector_member_index": 0,
          "verdict": {
            "verdict": "attributed_inconsistency",
            "channels": [
              "visual"
            ],
            "magnitude": "elevated"
          }
        },
        "source_capture_attachments": [
          {
            "attachment_id": "source-capture-18-0-0",
            "digest": "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
            "byte_length": 32768,
            "media_type": "application/vnd.sepahead.ncp-admitted-capture+json"
          }
        ]
      }
    ]
  },
  "calibrated_posterior": false,
  "model_digest": "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
  "configuration_digest": "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  "evidence_schema_digest": "sha256:edededededededededededededededededededededededededededededededed",
  "requested_effect": "RECORD_ONLY",
  "issued_at_utc_ms": 1784200021000,
  "expires_at_utc_ms": 1784200030000
}
```

This is one schema-complete evaluated-branch illustration. The exact receipt and
raw assessment-vector bytes are bounded attachments inside the protected
envelope. The complete report bytes occur inside that vector; the vector/member
identity and mapping receipt prevent a detached, partial, or projected
substitution. The source-authority bundle carries the exact descriptor,
declaration, observer grant, security state, receiver-evidence lineage/head
objects and their bounded content manifest. The per-assessment mapping receipt
and every source capture are also local protected attachments, not fetch-later
digests. In this example, an admitted NCP coordinate frame at source sequence
`902` and exact source time `42.0` seconds maps to Galadriel terminal sequence
`901` and timestamp `42000` milliseconds. The example does not claim that the
placeholder identities or artifacts exist.

## Invalid or hostile example

```json
{
  "extension_id": "org.sepahead.galadriel.assessment",
  "producer_principal_id": "galadriel-observer-a",
  "effect": "DENY_TIGHTEN",
  "calibrated_for_policy": true,
  "state_usability": "StateUnusable"
}
```

This fails schema, principal-role, and semantic validation. A producer cannot
self-admit its evidence or select Haldir policy. It also omits the required
direct `AuthorityRealmKey` and cannot reach realm-scoped replay or policy state.

## Actors and state transitions

Extension:

`UNREGISTERED -> REGISTERED_DISABLED -> ENABLED -> ROTATING/REVOKED ->
DISABLED`.

Each installed extension, lifecycle, receiver, policy, and publication machine is
scoped by one immutable direct `AuthorityRealmKey`. A realm change selects a
different machine and consumer foreign key. It cannot be expressed as key
rotation, grant renewal, process restart, policy recovery, or a live handover.

Immutable assessment processing:

`ABSENT -> RECEIVED -> VERIFIED ->
RECEIVED_REJECTED/RECORDED/PROFILE_INELIGIBLE/ADMITTED -> EVALUATED ->
DISPOSITIONED`.

Haldir policy-latch lifecycle:

`NO_APPLIED_DENY -> DENY_LATCHED -> RECOVERY_PENDING ->
DENY_LATCHED/WIDENED_BY_AUTHENTICATED_TRANSITION`.

Assessment expiry, retraction, mode disable, or profile change can start recovery
evaluation, but it does not rewrite an immutable assessment disposition or clear
the latch. Only the separate authenticated monotonic widening transition can
reach `WIDENED_BY_AUTHENTICATED_TRANSITION`.

Haldir returns an authenticated, bounded `HaldirAssessmentDisposition` for every
verified assessment. The disposition binds the direct `AuthorityRealmKey`,
complete session foreign key, assessor principal, exact assessor incarnation,
assessment sequence and digest, sealed assessment binding/scope/suite identity,
exact `AssessmentAdmissionRecord` and
`HaldirAssessmentAdmissionCurrentnessReceipt` digests or rejected-before-
admission marker, receiver-ingress principal/instance/clock/receive evidence,
exact `HaldirPolicyIngressReservationFact`, `HaldirPolicyIngressStamp`, and
`HaldirPolicyEvaluationResult` digests or explicit not-created markers,
policy-authority ingress clock/not-after evidence,
monitor-admission profile digest or explicit no-profile marker, ingress-stamped
`received_under_policy_revision` and installed policy-head digest,
optional verified body-authority provenance or explicit absence, and exactly one
closed outcome: `RECEIVED_REJECTED`, `RECORDED`,
`PROFILE_INELIGIBLE`, or `APPLIED_DENY`. Retry and deduplication use that
identity; a missing disposition never lets Galadriel infer that a deny was
applied. A disposition grants no NCP authority and cannot encode `ALLOW`.

The policy-evidence member is a closed union.
`NO_RESTRICTIVE_POLICY_MUTATION` has two disjoint forms.
`NOT_EVALUATED` carries no barrier/evaluated revision/restrictive commit and
covers rejected-before-policy or the exact no-profile branch; a no-profile result
binds its terminal `HaldirPolicyEvaluationFinalizationCommitReceipt`.
`EVALUATED_NO_RESTRICTION` binds the exact H1-to-H2 evaluation barrier, H2-to-H2F
terminal finalization receipt and evaluation result, including explicit expired,
invalidated or preempted reason, but no H3 restrictive commit.
Both are valid only for `RECEIVED_REJECTED`, `RECORDED`, or
`PROFILE_INELIGIBLE`. `RESTRICTION_COMMITTED` binds the evaluation barrier,
exact evaluated H2, installed restrictive H3, terminal
`HaldirPolicyEvaluationFinalizationCommitReceipt`, selector version, and
`HaldirPolicyStateCommitReceipt`; it is required for `APPLIED_DENY`. If the
selector has advanced, it also carries current-head ancestry or retained-
membership proof. A signed candidate, same-revision sibling/losing barrier,
losing restriction compare-and-swap, historical commit receipt, or caller-
selected head cannot prove `APPLIED_DENY`.

The policy authority stamps `received_under_policy_revision` only after it
authenticates the immutable admission record at its narrow API. The receiver,
envelope, and producer cannot modify that revision or any earlier revision. The
Haldir profile identifies the guards for the no-widening H1-to-H2 evaluation
barrier and any additional delay derived from the producer-declared, receiver-resolved
source position. That correlation proves which source the producer declared and
which exact bytes Haldir resolved. It does not prove that Galadriel's internal
computation consumed the source or that the source caused the assessment. A
producer-supplied revision or authority term cannot satisfy this rule.
Restriction, recovery, and expiry follow the profile's bounded dwell and
hysteresis rules. A stronger computational-dependence or causal claim requires
separate instrumented and independently qualified evidence.

Per-message meet-only semantics are insufficient across lifecycle changes.
Permission widening caused by deny retraction, expiry, assessment-mode disable,
base-policy widening, or restart reconstruction requires an explicit
authenticated, monotonically versioned Haldir policy/widening transition,
successful compare-and-swap of `HaldirPolicyStateHead`, and an audit record. A
restart that cannot restore applied deny state follows the declared absence
policy and cannot silently erase a deny into a new ALLOW.

## Bounds and resource behavior

Manifest bytes, schema bytes, payload bytes, realm keys, extensions per realm,
assessor incarnations, sequences, replay tombstones, unfinished single-flight
operations, UTC audit intervals, local deadlines, clock mappings, queue depth,
CPU budget, log volume, and retained gaps are finite.
Control/action capacity is reserved independently. Unknown extension bytes are
rejected before semantic allocation. Assessment, scope, ordered-input proof,
profile, calibration-receipt, adapter-mapping proof, and disposition sizes and
rates, queues, retry windows, and overflow behavior are bounded. Sequence or
replay-state capacity loss disables the effect before evidence is discarded;
overflow produces an explicit gap or rejected outcome rather than an inferred
applied deny.

The initial extension allocation has hard pre-parse ceilings of 20 MiB for the
complete protected envelope and attachments, 16 KiB for a lifecycle receipt,
16 MiB for the raw assessment vector, 1,024 vector members, and 256 KiB for one
complete serialized report inside the vector. A profile can set smaller limits.
An otherwise valid Galadriel result above a ceiling is unpublishable and
profile-ineligible; the producer does not truncate it and Haldir does not select
one convenient member. Supporting a larger vector or a per-member inclusion
proof requires a separately versioned Galadriel commitment and extension
manifest, not an NCP interpretation of the current flat hash.

## Threat and hazard analysis

This prevents route confusion, credential reuse, observer actuation, extension
starvation of control, producer self-admission, stale/replayed deny evidence,
same-policy-state feedback, and lifecycle widening. Restrictive advice can still reduce
availability or create denial of service. Operators must see that consequence.
Record-only is mandatory until the exact independent profile is qualified.

Direct realm identity prevents a valid Galadriel envelope, lifecycle head,
source transfer, Haldir admission/evaluation, policy decision, command release,
or disposition from being replayed into a realm that reused all other identifiers
and bytes. It also prevents portable projections from losing the
server-authority-principal component hidden by a route-only design. Validation
occurs before replay, detector, receiver, policy, commander, or outbox lookup.

## Formal properties

- Every realm-scoped canonical object named in this ADR has one direct,
  non-default `AuthorityRealmKey` in its canonical bytes and digest. This
  includes every envelope, source/transfer/projection object, lifecycle or
  policy head, selector, fact, reservation, outbox item, queue/transport attempt,
  deadline evaluation, disposition, and receipt.
- The realm is exactly equal across authenticated ingress, default-deny
  extension activation, audience, route projection, protected bytes, session
  descriptor/transcript, declaration, source-authority tuple, owning selector,
  predecessor/successor evidence, and downstream projection.
- A missing, unknown, default, wildcard, retired, mismatched, ancestry-only, or
  route-only realm creates no replay reservation, lifecycle mutation, policy
  evaluation, publication release, callback, or side effect.
- Same-principal, same-session-kind, same-logical-session-ID, same-generation,
  same-incarnation, same-sequence, same-digest, and same-protected-byte attempts
  presented under different realm contexts never share replay, currentness,
  evaluation, publication, disposition, provenance, or retirement state.
- An exact protected extension or intent byte sequence replayed at another
  authenticated realm rejects before state lookup. A separately valid object
  with every non-realm member equal but either realm-key coordinate changed uses
  distinct lifecycle, receiver, policy, commander, and provenance lineages.
- Every portable consumer uses
  `(AuthorityRealmKey, session_kind, logical_session_id, generation)` as the
  session foreign key. A projection that drops or rewrites the realm rejects.
- A contract/schema/release-suite digest remains realm-independent only where its
  schema says so. Installing it does not let a realm-scoped activation omit its
  direct realm.
- Stable core routes never accept extension envelopes and vice versa.
- Producer verdict, self-admission, and requested effect have no direct policy
  authority.
- No assessment changes policy without the exact evidence-only
  `AssessmentAdmissionRecord`, its post-CAS
  `HaldirAssessmentAdmissionCurrentnessReceipt`, authority-created
  `HaldirPolicyIngressReservationFact` and post-H1
  `HaldirPolicyIngressStamp`,
  authenticated Haldir monitor-admission profile and required qualification
  evidence, authority-created `HaldirPolicyEvaluationResult`, and successful
  policy-head compare-and-swap receipt.
- An admitted assessment effect is never greater than local Haldir permission.
- `RECORD_ONLY` is handling, not permission. Its typed effect is only meet
  identity/no additional restriction: `DENY ∧ identity = DENY` and
  `ALLOW ∧ identity =` the pre-existing local `ALLOW`, never an assessment grant.
  Required absence and eligible restriction use only their exact profile-owned
  deny elements; unknown or inconsistent handling/effect pairs reject.
- Observer credentials cannot authenticate assessment traffic.
- The assessor principal cannot authenticate the Haldir admission profile.
- Every successful Galadriel lifecycle-composite compare-and-swap increments
  `lifecycle_state_version` by exactly one. This includes handoff-only
  transitions that preserve the detector snapshot and inner lifecycle receipt
  index. A stale, sibling, repeated, skipped, rolled-back, exhausted or
  unreceipted outer version rejects and cannot publish.
- Haldir's assessment receiver, policy-state authority, and NCP commander are
  three process/credential/store boundaries. The receiver cannot publish NCP,
  the policy authority has no transport credential, and the commander cannot
  read raw assessment/admission/replay state or evaluate policy. The integrated
  policy authority alone owns base/monitor policy and intent replay. Standalone
  Gate is a separate deployment mode, not a hidden fourth integrated process.
  Only the exact narrow evidence-evaluation and publication-fence APIs cross
  those boundaries.
- Native `HaldirIntentV2` binds an installed policy-authority-issued
  `HaldirIntentFreshnessGrant`, installation receipt and exact slot. Its unchanged
  authority-clock deadline is the minimum of the grant maximum and checked
  issue-tick-plus-canonical-requested-validity duration. Sender time and receiver
  arrival never define or refresh it. The actual Haldir ingress endpoint checks
  that deadline/gate and atomically installs the durable intent reservation;
  source admission, ALLOW decision and handoff cannot outlive it. Grant request
  retry returns one authority-selected range, and exact intent retry creates no
  second reservation. V1 provides none of this evidence and is not native-1.0
  proof.
- A permission snapshot never releases command bytes. Commander-owned
  `HaldirCommanderPublicationPreflight` is receipt-free content in the successor
  that binds an `imported_body_lease_view`, exact Crebain issuance/currentness
  receipt and local freshness/expiry, and reserves only commander-local security,
  stream position and bounded queue capacity through the installed commander
  composite selector.
  The post-CAS `HaldirCommanderPreflightInstallationReceipt` proves that it won
  and consumed the position. The closed authorization origin is exact policy
  ALLOW or an authenticated HOLD/ESTOP-only fail-safe trigger. The policy
  authority requires both objects in one reservation through its composite
  selector and verifies both the original authority-origin validity deadline and
  newer handoff deadline; equality with either expires. Deny
  cancellation, exact outbox append and worst-case history installation have one
  atomic order; that append, not a cross-process queue claim, is the policy
  release point. The commander separately commits its local durable queue
  ownership through its composite selector. Stale/sibling head, changed bytes/
  route/context, trigger-to-Active substitution, double use, missing selector, or
  cross-preflight substitution fails closed. Reply loss queries those exact two
  selectors. Every outcome consumes the reservation/stream position; external
  NCP-transport ambiguity blocks Active pending body reconciliation.
- Normal commander publication is reachable without a cancellation round trip.
  `RESOLVE_COMMAND_QUEUE_TRANSFER` consumes either an open preflight with its
  exact policy release/outbox pair or a released obligation imported from a
  cancellation or retirement race. Both cases install one terminal local
  resolution; neither case can infer policy release from local state.
- Local outbox ownership is not external transport acceptance. Every first send
  and retry installs an exact attempt through the current commander selector
  before invocation and commit-bound verifies the unchanged earlier
  `NCP_TRANSPORT_ATTEMPT_NOT_AFTER`, applicable retry right and current security/
  session/generation/gate. That start cutoff subtracts qualified worst-case time
  through endpoint acceptance from the separate
  `NCP_TRANSPORT_ACCEPTANCE_NOT_AFTER`. The acceptance cutoff is the conservative
  minimum of every mapped command, authorization, lease and handoff absolute
  bound plus checked release-instant-plus-profile-duration. START is necessary,
  not success. The endpoint atomically checks the unchanged acceptance cutoff and
  gate and emits a queryable receipt; equality/later cannot accept, and local
  timeout/cancel without endpoint proof is ambiguous. Success means only
  `ACCEPTED_BY_NCP_TRANSPORT_BOUNDARY`, never body receipt/admission/application.
  Retry/restart cannot refresh either cutoff. In retirement, old attempts are
  query/resolve-only, unsent non-ESTOP keys terminalize, and only the exact one-
  slot ESTOP drain key can START under a fresh root-bound `OPEN_DRAIN` epoch.
- The commander selector does not prove current Crebain/body authority across
  stores. Queue release is neither body admission nor application. The body
  revalidates the exact lease/session/security/command under its own installed
  composite and remains final actuator authority; a revocation racing preflight
  or release can therefore make body admission reject.
- Commander retirement cannot infer remote non-release from local absence. It
  first closes local creation, then the policy selector installs exactly one
  cancellation-tombstone or released-outbox outcome for every outstanding
  preflight, and only then can the commander import the complete outcome set.
  A policy release racing closure orders before the outcome and remains a drain
  obligation; closure ordering first permanently rejects the delayed release.
  Timeout or policy ambiguity preserves the non-authorizing closure-wait state
  and complete possible-release set. It never permits direct retirement.
- The same policy-serialized outcome closes every ordinary commander preflight
  cancellation and every clock, body-authority or security cut. Local state can
  block a preflight immediately, but it cannot classify the preflight canceled
  or forget its position/slot until the policy selector installs the exact
  cancellation tombstone. A policy release that won first remains an immutable
  queue, feedback and retention obligation.
- Integrated policy output is one authority-signed
  `HaldirPolicyDecisionRecord` with exact intent/source/policy/replay/deadline and
  no future NCP stream/frame/lease/route/queue member. Its distinct decision
  commit receipt proves atomic intent/source/history consumption in the installed
  policy head. Commander conversion and preflight create later body/NCP facts. A
  DENY or old mixed Gate receipt cannot authorize a policy-allow preflight;
  authenticated fail-safe origin remains separately HOLD/ESTOP-only.
- Authority-owned slew/duty history receives one exact publication-feedback
  transition per origin. Policy outbox release atomically creates its worst-case
  pending history reservation in the same policy-head compare-and-swap. Released
  or queue-ambiguous feedback finalizes it;
  proved local pre-queue cancellation clears it. Missing, duplicate-conflicting,
  reordered or crash-ambiguous feedback remains conservatively counted or blocks
  history-dependent decisions. Commander clock values never select authority
  history time.
- A new policy evaluation uses only the profile selected in the
  policy-authority-created reservation fact and ingress stamp from the
  separately authenticated installed current `HaldirPolicyStateHead`. H1 and C1
  bind the fact but exclude the stamp; H2 is the first head that binds the
  post-C1 stamp. Admission is evidence-only and selects no profile. A stale
  profile or same-revision sibling head cannot evaluate evidence.
- The ingress profile selection is exactly `PROFILE_SELECTED` or `NO_PROFILE`.
  No-profile derives its deadline from an installed base-policy rule and creates
  no evaluation barrier; a second CAS installs a terminal H2 that first binds the
  stamp and terminalizes its operation. A selected profile
  first constructs one receipt-free
  `HaldirAssessmentEvaluationBarrierFact` after its guards pass, then binds it in
  one no-widening H1-to-H2 `ASSESSMENT_EVALUATION_BARRIER`; only the post-CAS
  receipt proves installation. It computes outside a short selector transaction and terminalizes
  exactly once as H2F no-restriction/expired/invalidated/preempted or H3
  restriction. Both finalization and H3 recheck the original exclusive deadline.
  Restrictive/fail-safe work can preempt the pending token; widening cannot.
  Permission-preserving descendants require a bounded exact chain. A sibling
  barrier, concurrent transition, crash, retry or expiry cannot make the
  restriction transition prove its own eligibility or leave the operation
  permanently blocking.
- An empty Haldir policy head can install only once through
  `GENESIS_FROM_UNINITIALIZED` against a selector that proves a never-used policy
  domain and lineage, with `HaldirPolicyStateCommitReceipt`. Restart, state loss,
  a prior deny, sibling genesis, or reused lineage cannot install an empty reset.
- No assessment transition directly creates an NCP command or body authority.
- Loss of the Haldir policy authority/store/API blocks Active and lease renewal
  but is not evidence that a restrictive NCP command was published. Kill/crash
  cuts from trigger through preflight, policy reservation, outbox and commander
  queue prove no Active escape and separately measure the plant-profile body/
  ActionBuffer watchdog fallback. The body remains final actuator authority.
- Fail-safe and restrictive work preempt bounded assessment evaluation. A
  content-addressed scheduler budget caps consecutive barriers and provides
  bounded command service; exhausted assessment work becomes explicit record-
  only/drop. Any system-wide no-delay claim remains an external live gate.
- Effective permission never widens without an authenticated Haldir transition.
- Every profile-set, deny-latch, recovery, or widening change is a successful
  compare-and-swap successor of the installed Haldir policy-state head.
- Evidence cannot affect its ingress-stamped Haldir revision or an earlier
  revision.
- An accepted assessment has one exact assessor
  `(AuthorityRealmKey, session_kind, logical_session_id, generation, principal,
  incarnation, sequence, envelope digest)` identity. Restart,
  rollback, sequence exhaustion, replay-state eviction, or same-position
  conflicting content cannot revive or replace it. Pending preimage, immutable
  admission/rejection, high-water, retirement and safe-rotation evidence advance
  the one installed receiver-state selector; missing or empty state cannot reset
  it.
- Concurrent and later same-digest retries converge across two separate durable
  single-flight domains: the receiver creates one evidence-only admission record
  from its first receive time and immutable evidence preimage; the policy
  authority creates one reservation fact, one post-C1 ingress stamp, one
  evaluation result when applicable, and one winning transition at each required
  H1/H2/terminal compare-and-swap from its own first receive time, selected
  profile, and deadline. Neither process supplies or recomputes the other's fields.
  Duplicate-local values are discarded, and a retry after policy-head
  advancement returns the original result. Receiver recovery after key
  reservation but before record storage reconstructs only its winning record.
  Policy-authority recovery after H1 but before H2 reconstructs the same stamp
  from the reservation fact and C1. Recovery after H2 proves and finalizes the
  already installed transition.
- The sealed Galadriel assessment binding, eight-coordinate scope, release suite,
  lifecycle receipt and complete assessment vector, ordered observations/report,
  and adapter mapping resolve to the exact admitted NCP captures in the dynamic
  evidence-only admission record. An equal verdict with different provenance is
  not equivalent. The separate authority-created evaluation result binds the
  static profile, selected members, classifications, rule, result, handling,
  effect, local input, and meet; admission bytes cannot supply or rewrite them.
- Release-suite equality uses the exact typed SHA-256/domain/digest identity
  mapped from Galadriel `ConfigDigest`. A same-name different digest, wrong
  digest encoding/length, algorithm substitution, or derivation-domain
  substitution rejects.
- Assessment-binding equality uses the exact typed SHA-256/domain/digest identity
  mapped from `AssessmentBinding::digest()`. Prefix, case, length, domain, suite-
  digest, and byte substitutions reject.
- The lifecycle outcome carries the exact raw complete vector bound by the exact
  `LifecycleReceipt` plus a total ordered extension projection. An evaluated
  branch without its report, an abstained branch with any report/scope/binding,
  an omitted or reordered sibling, changed raw whitespace/order under the same
  projection, an unknown lifecycle variant, an empty or non-canonical unavailable-
  modality set, a suite substitution, an attachment substitution, a raw/projected
  report mismatch, or a receipt/vector mismatch rejects. Evaluated
  `insufficient_evidence` stays evaluated and profile-ineligible.
- Lifecycle digest agreement uses the exact NUL-terminated domain, 32-byte suite,
  16-byte big-endian length prefixes, 8-byte big-endian receipt index, canonical
  nested JSON, and one-byte optional-digest tags. A missing prefix, different
  width/endian, raw-receipt hash, normalization of raw-vector bytes, or option-
  encoding substitution rejects.
- Policy eligibility requires one committed installed Galadriel detector-lineage
  head with a canonical bounded lane-to-source-authority map, exact versioned
  lifecycle-state snapshot, and explained receipt/state ancestry to a separately
  attested current selector. Each global receipt changes one named lane or closed
  global operation. Canonically different map insertion order yields the same
  snapshot bytes. Restart in the same source epoch, arbitrary-sequence re-
  initialization, receipt index/root reset, unexplained skipped receipt, old-
  epoch reuse, losing sibling, historical head, stale compaction root, and
  assessor-incarnation substitution cannot establish continuity. State loss
  retires the lineage and stays record-only until its exact qualified recovery
  boundary and full warm-up are complete. Snapshot round-trip must preserve every
  private detector field and the next transition exactly. Inner receipt/digest/
  serialization failure installs a terminal lineage fault or retires the lineage;
  a diagnostic `clear_histories` cannot continue policy eligibility.
- Every Galadriel lineage head, boundary, update, handoff record, and assessment
  binds the exact direct `AuthorityRealmKey`, session kind, NCP logical session,
  live generation, descriptor, declaration, observer grant, security state,
  receiver-evidence lineage, and coordinate-mapping receipt. Galadriel
  `session_id`, source epoch, route, or a mapping profile cannot stand in for
  those values. An independent mutation or substitution of any member rejects.
  A changed realm or generation retires the old scope. Only a same-scope,
  same-context grant renewal with exact
  `GaladrielLifecycleAuthorizationSpanTransition`, both grant receipts, prior/
  installed observer composite admission heads and selector version, gap-free
  old-last/new-first admission boundary, successful lifecycle-head CAS and
  ordered per-lane span commitment can preserve the lineage and warm-up.
  Any other tuple change requires the authenticated new-lineage/reset path and
  full warm-up or retirement.
- Both fresh-epoch and existing-epoch lineage genesis require complete warm-up.
  Existing-epoch late attach uses the exact installed live frame-admission
  high-water and first live receipt; an old retained/history/query frame, a
  boundary before current high-water, pre-boundary suffix member, or reuse of one
  boundary for another lineage rejects.
- Every lifecycle/currentness proof is locally available as a protected bounded
  attachment with exact digest/length/media type. Missing/tampered/cross-envelope
  bytes, digest-only references, head without commit, attestation without
  ancestry/compaction proof, or aggregate attachment overflow rejects.
- Non-assessment rejected/faulted receipts may occur between published outcomes,
  but a durable head chain or authenticated compaction bridge must explain them.
  An assessment-bearing state commit atomically installs snapshot, receipt and a
  publication-candidate fact in H1. A deterministic record over fact/H1/C1 becomes
  visible only after the exact H1-to-H2 handoff CAS. A lifecycle change first
  installs `CANCELED_BEFORE_RECORD_INSTALL`. Crash after H1 resumes the same
  bytes or that tombstone; no content-addressed cycle or silent remake is valid.
- The observer alone receives NCP frames and verifies live serialization-only
  Galadriel values; the assessor alone holds the extension key. Their authenticated
  local handoff exposes one immutable publication record/currentness lineage, not
  credentials, bus handles, detector state, or a bidirectional callback. Tampered,
  stale, sibling, invalidated, duplicate-with-conflict, or crash-reconstructed-
  differently outbox evidence rejects.
- Assessor publication reserves and finalizes against the same exact installed
  lifecycle-lineage selector that commits detector and subordinate handoff state.
  Finalization atomically consumes the sequence and appends exact signed bytes/
  route/audience/security/deadline to the assessor-owned release outbox;
  no bearer authorization exists between finalization and release. Invalidation
  immediately before reserve makes reserve fail, and invalidation/current-head
  advance after reserve but before outbox append installs the distinct
  `CANCELED_BEFORE_FINALIZE` tombstone/receipt. An advance
  after append orders after the immutable released item. Crash before sign
  resumes only the exact preimage/sequence; crash or lost reply after append
  queries and drains/resolves that entry. Queue cancellation, release, and
  ambiguity all consume the sequence and cannot remake bytes. Because lifecycle
  invalidation and handoff update are one composite CAS, FINALIZE cannot outrun
  an already committed but not-yet-imported lifecycle change.
- Each external transport attempt and disposition for a released Galadriel queue
  item is installed through that same lifecycle/handoff selector. Attempt start
  precedes send and commit-bound evaluates the unchanged earlier external-attempt
  cutoff plus current security/session/scope/gate; equality terminalizes without
  send. The separate acceptance cutoff is the conservative minimum of all mapped
  absolute source bounds and checked local-queue-release-instant-plus-profile-
  duration. The endpoint atomically evaluates that unchanged cutoff and gate at
  actual acceptance. Only its queryable strict-before receipt permits
  `ACCEPTED_BY_EXTERNAL_TRANSPORT_BOUNDARY`, which does not prove Haldir receipt
  or policy use. Timeout/cancel without endpoint proof is ambiguous. Disposition
  resolution consumes exactly that active attempt. Concurrent workers, reply
  loss, crash, retry and drain cannot refresh either cutoff. Retirement fences
  the normal gate; only exact retained keys can START under one fresh root-bound
  `OPEN_DRAIN` epoch. External transport state grants no publication authority,
  but it cannot fork outside currentness or disappear before drain-only
  retirement finalization.
- Haldir applies one profile-owned rule to the complete allowed track population.
  It never cherry-picks an alarming member or ignores an abstained, insufficient,
  conflicting, missing, extra, or duplicate sibling. Missing or inapplicable
  aggregation remains record-only, and the authority-created evaluation result
  binds the exact member set, classifications, rule, and result. The receiver
  cannot precompute or assert those fields.
- Policy-bearing verdict evidence is an exact projection of sealed
  `DefaultReport::verdict()` and the complete report bytes at the bound member of
  the exact raw vector. The bytes are present; the receiver never reconstructs
  the report from its projection and no one-member value substitutes for the
  full flat-hashed vector.
  Baseline-vs-fused name collisions, unknown variants, missing or duplicate
  channels, `radio_frequency` in place of `radiofrequency`, missing or
  substituted magnitude, and an unsealed/unbound report reject.
- The flat extension scope maps totally and reversibly to Galadriel's nested
  `AssessmentScope`. Changing any one coordinate changes or invalidates the
  mapping. Its terminal sequence is the maximum observation sequence and its
  terminal timestamp is the maximum timestamp at that sequence.
- The assessment clock domain is one exact Galadriel `ClockDomain` variant.
  Unknown or guessed deployment labels reject.
- The native NCP mapping is exact: source sequence `1` maps to Galadriel `0`,
  source sequence `2` maps to `1`, and each fresh epoch starts again at that
  mapping. Sequence `0`, overflow, off-by-one proof, negative/non-finite time,
  fractional-millisecond time, two source times that would round together,
  JSON-unsafe time, receiver-UTC substitution, and an unreceipted local
  `state_generation` change reject or remain record-only.
- Receipt/vector/member/report/envelope ceilings are checked before corresponding
  allocation. Oversize input is never truncated or reduced to one member.
- Freshness uses the policy-authority ingress stamp, its independent clock and
  profile-derived deadline, plus a profile-authorized bounded source-clock
  mapping. The receiver clock is evidence arrival provenance only. Producer UTC
  expiry cannot select a Haldir deadline, and restart cannot extend one.
- Source correlation proves the producer-declared reference and the exact
  receiver-resolved evidence only. It does not prove internal computational
  consumption or causality. A policy delay based on that position retains this
  limitation unless separately instrumented, qualified evidence proves a
  stronger claim.
- A body-authority correlation is accepted only from an exact authenticated
  body-issued capture and receipt, never from assessor assertion.
- `APPLIED_DENY` is never reported without an authenticated disposition bound to
  the exact assessment/admission record, authority-created ingress stamp and
  evaluation result, selected admission profile, evaluated prior/installed
  policy-head transition, selector version, commit receipt, and current-head
  ancestry or retained membership.

## Migration

Galadriel owns raw advisory extension schemas and adapter packages. Haldir owns
the admission profile, eligibility derivation, `StateUnusable` derivation, and
policy mapping. Crebain moves sidecar publication to the registered route or
emits a valid standard NCP frame via a narrow adapter. Existing mixed-route
traffic is rejected by native 1.0. Native schemas and consumers add direct
`AuthorityRealmKey` members to every realm-scoped Galadriel/Haldir object named
above. They use the full
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` foreign key.
Mandatory mutants hold principal, session, generation, incarnation, sequence,
digest, and protected bytes fixed while changing only the authenticated realm
context. Separate mutants remove the realm from a portable projection, infer it
from the route, or merge two realm partitions. All must reject.

## Operational recovery

On manifest, admission-profile, qualification-receipt, replay-state, or
deny-state uncertainty, reject new policy effects and retain the raw evidence
only when safe bounded recording remains possible. Applied state is restored
from durable Haldir records or missions remain denied/preserved until an
authenticated transition resolves it. Gaps and drops are counted.
Recovery restores only state whose direct realm matches the installed selector
and endpoint. It never rehomes an obligation, receipt, policy latch, or replay
high water into another realm.

## Compatibility and rollback

Extensions are optional and separately versioned. Disabling an extension does
not alter stable-core compatibility, but it also cannot silently retract applied
deny state. A rollback is an authenticated new monotonically increasing Haldir
transition that names the selected earlier manifest/profile content; it never
restores an earlier policy revision or replay snapshot. The transition preserves
or reconstructs applied-deny, assessor-incarnation/high-water, dwell, and recovery
state. If that continuity cannot be proved, effects remain disabled and current
deny state is preserved until an authenticated widening transition resolves it.

## Open questions

<a id="ncp-b01-selector-allocation-adr-008-v1"></a>

One semantic question remains open. The proposed extension ceilings must conform
to the universal 1,048,576-byte structured-message frame limit. The
`sha256:<hex>` content address needs one injective canonical route-segment
encoding. Namespace ownership, exact
schema identities, optional body-authority provenance, assessor replay
identities, and Galadriel adapter-proof references remain B03 allocation inputs.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: stable and extension payloads have disjoint meanings.
2. Security: owner, route, schema, audience, assessor, and independent profile
   issuer bind exactly.
3. Safety: advice cannot self-admit, grant, or actuate; denial consequences
   remain visible.
4. Lifecycle: enable, evidence admission, authority-stamped profile eligibility delay,
   dwell, recovery, expiry, restart, retract, and widening are explicit.
5. Resources: extension work cannot starve control.
6. Migration: registered manifests enable independent agreement.
7. Science: advisory output remains non-calibrating and provenance-labeled;
   policy eligibility requires separate deployment-specific evidence.
8. Operations: gaps, drops, absence policy, and key rotation are observable.
9. Evidence: confusion, replay, monotonicity, load, and live freshness tests run.
10. Governance: Galadriel owns raw schema/namespace; Haldir owns admission and
    final local policy.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes.
