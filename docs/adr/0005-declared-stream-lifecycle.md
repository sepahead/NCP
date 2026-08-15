# ADR-005 — Declare and retire every stream explicitly

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: distributed-systems reviewer and all stream consumer owners

## Context

NCP frames carry a stream epoch and sequence, but the current stable contract does
not establish an authenticated declaration operation. Some consumer code can
adopt a first frame or silently mint a fresh epoch at sequence exhaustion. That
lets traffic create authorization state and contradicts the rule that exhausted
publishers stop until redeclared.

## Proposed decision

Every streamed plane shall use explicit authenticated operations:

- `DeclareStream` proposes one fresh stream incarnation;
- `StreamDeclared` returns the receiver-issued declaration receipt that
  authorizes that exact proposal;
- `RetireStream` permanently closes the incarnation;
- `RedeclareStream` creates a fresh opaque UUIDv4 epoch after retirement,
  restart, publisher change, schema change, or exhaustion.

ADR-001 `AuthorityRealmKey` is the canonical tuple of server authority principal
and stable realm ID. It excludes rotating security epochs, registry or store
incarnations, and every session, declaration, stream, or receiver-evidence
generation. Every realm-scoped operation request, result, stream frame, key,
head, selector, fact, commitment, tombstone, checkpoint, provenance object,
query result, and pre- or post-CAS receipt in this ADR carries
`authority_realm_key: AuthorityRealmKey` as a direct canonical member. Its
canonical bytes and digest include the member.

This rule includes `DeclareStream`, `StreamDeclared`, `RetireStream`,
`RedeclareStream`, the declaration and declaration-generation key,
`DeclarationLedgerHead` and its commit receipt, every generic or role-specific
receiver admission head/selector/receipt, every live or historical
frame-admission head and receipt, `RetirementAnchor`,
`ProviderHistoryProvenance`, every receiver-evidence lineage key/head/receipt,
and `FrameAdmissionTerminalCheckpoint`. It also includes each allocation marker,
transition fact, and specialized receipt that can select or prove one of those
objects. A nested object does not inherit the realm from its container for
portable validation. A realm-scoped projection that omits or changes the direct
member is invalid.

`StreamPosition { epoch, seq }` remains a small equality/ordering value, not a
globally unique identity. Every frame, source reference, admission record, or
history proof that uses it supplies its own direct realm member and full declared
stream identity. A bare position cannot key a cache, replay store, gap ledger,
deduplication set, or consumer join.

A declaration binds the exact `AuthorityRealmKey`, publisher principal/entity,
session ID and generation, plane, literal route, message class,
publisher-proposed opaque stream epoch, starting sequence, channel/schema
selection, transcript, security state, audience, QoS profile, operation context,
and declaration digest. The receiver authorizes the proposal only after it proves
that the epoch is absent from every live declaration and retained retirement
tombstone in that authority realm and session/security domain.

The canonical declaration key includes a never-used declaration-generation
incarnation in addition to its exact
realm/publisher/session/plane/route/class/channel scope. `DECLARE_STREAM`
creates a live entry only from exact key nonmembership. `RETIRE_STREAM` changes
that key to a permanent retired tombstone. `REDECLARE_STREAM` never changes the
retired key back to live. It preserves the old tombstone byte-for-byte, proves a
fresh declaration generation and fresh stream epoch, and creates a version-1
live entry at the new key with an explicit predecessor-tombstone link. Same-key
`RETIRED -> LIVE`, generation/epoch reuse, missing predecessor ancestry, or a
caller-selected “fresh” assertion rejects.

The literal route's realm segment is only the canonical projection of the stable
realm ID. The declaration receiver requires exact agreement among the direct
realm key, authenticated ingress context, installed default-deny manifest,
audience, route projection, session descriptor, transcript, and receiver state.
The route, descriptor, a parent head, or local configuration cannot supply a
missing realm member. Missing, default, wildcard, retired, or mismatched realm
data rejects before declaration lookup, semantic allocation, ledger mutation,
frame admission, callback, or side effect.

`StreamPosition.epoch` is an opaque canonical UUIDv4 compared for equality only.
It is never ordered, incremented, or replaced with `0`. Sequence starts at `1`,
increases strictly within the declared epoch, and remains in the JSON-safe range.

Frames cannot create, rotate, widen, or revive a stream. Sequence exhaustion
makes the publisher silent. Reconnect, HOLD, lease expiry, or a quiet period does
not reset the receiver's high-water mark.

The receiver maintains a durable canonical `DeclarationLedgerHead`. The head
binds its exact realm scope, incarnation/version, prior-head digest, declarations
and tombstones; it excludes its own digest/receipt and every
successor/selector digest. After compare-and-swap,
`DeclarationLedgerHeadCommitReceipt` directly binds the same realm and the prior
and newly installed head digests and applicable composite selector version. A
valid historical ledger, selector response, or receipt cannot become current by
replay. Retirement tombstones are finite. Before
capacity policy would evict any tombstone, the receiver retires and fences the
whole session generation. No new declaration is accepted in that generation.
The replacement session uses a fresh opaque generation and new stream epochs.

For a receiver without a stricter role-specific root, parent creation allocates
one canonical `ReceiverAdmissionStateHead` and
`InstalledReceiverAdmissionStateSelector`. The head binds stable receiver/
realm/session/security scope, exact current descriptor revision/digest, a
never-reused incarnation, strict state version, prior head, the subordinate
declaration ledger, receiver-evidence lineage registry, and a bounded map of
every live, retirement, historical and terminal admission state.
`ReceiverAdmissionStateCommitReceipt` binds the prior/installed composite
heads, realm, and versions. Every declare, retire, redeclare, lineage transition,
live or historical append, retirement-anchor install and terminalization
contends on this selector and preserves every unrelated substate.
Descriptor replacement also contends on this selector and atomically retires or
fences every incompatible declaration/admission substate.
`RECEIVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED` atomically installs
composite version 1, empty declaration-ledger version 1, empty lineage-registry
version 1 and an empty bounded admission map from a parent-created never-used
selector. Post-use absence, reset, rollback, restart loss, sibling genesis or
incarnation reuse fences the receiver scope.

The closed generic receiver transition union is:

- `RECEIVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED`;
- `INSTALL_RECEIVER_STREAM_DECLARATION`;
- `RETIRE_RECEIVER_STREAM_DECLARATION`;
- `INSTALL_RECEIVER_STREAM_REDECLARATION`;
- `INSTALL_RECEIVER_LIVE_ADMISSION_GENESIS`;
- `APPEND_RECEIVER_LIVE_FRAME_ADMISSION`;
- `FREEZE_RECEIVER_LIVE_ADMISSION_FOR_RETIREMENT`;
- `ALLOCATE_RECEIVER_EVIDENCE_LINEAGE`;
- `RETIRE_RECEIVER_EVIDENCE_LINEAGE`;
- `INSTALL_RECEIVER_LATE_ATTACH_ANCHOR`;
- `INSTALL_RECEIVER_HISTORICAL_ADMISSION_GENESIS`;
- `APPEND_RECEIVER_HISTORICAL_FRAME_ADMISSION`;
- `TERMINALIZE_RECEIVER_HISTORICAL_ADMISSION_FROM_HEAD`;
- `TERMINALIZE_RECEIVER_HISTORICAL_ADMISSION_FROM_ANCHOR`;
- `REPLACE_RECEIVER_DESCRIPTOR`;
- `APPLY_RECEIVER_SECURITY_CUT`;
- `RETIRE_RECEIVER_ADMISSION_SCOPE`; and
- `EVICT_FINALIZED_RECEIVER_RETENTION`.

Each transition uses the exact receipt-free content or fact and bounded mutation
footprint specified in this ADR. The retained B01 selector matrix is diagnostic
only and cannot change that meaning. An unknown, default, inferred, or legacy
alias rejects.

The top-level composite genesis allocates the never-used declaration-ledger
incarnation and installs its empty version-1 subordinate head in the same
transaction. Its `DeclarationLedgerHeadCommitReceipt` carries the closed
`GENESIS_FROM_UNINITIALIZED` subordinate transition kind and binds the
prior/installed composite heads. It does not consume a subordinate selector. A
missing composite selector, signed empty ledger, restart, or reused incarnation
after any use is corruption, not genesis, and retires the session generation.

The declaration ledger has no independently authorizing selector. The generic
receiver composite applies only when no stricter role root exists. The body-owned
action-command declaration ledger for a plant session is subordinate to ADR-007
`BodySessionControlStateHead`.
The closed subordinate declaration-ledger transition union is
`GENESIS_FROM_UNINITIALIZED |
COMMAND_DECLARATION_GENESIS_FROM_BODY_SESSION_CREATION |
DECLARE_STREAM | RETIRE_STREAM | REDECLARE_STREAM`.
These kinds never create an independent declaration selector.
`COMMAND_DECLARATION_GENESIS_FROM_BODY_SESSION_CREATION` installs its empty
version-1 head inside the one-use composite session genesis. Every command
`DeclareStream`, `RetireStream`, `RedeclareStream`, authority handover, and
generation retirement compares and swaps
`InstalledBodySessionControlStateSelector`. The resulting
`DeclarationLedgerHeadCommitReceipt` binds the prior and installed declaration
heads, prior and installed body-session-control heads, selector version, and
`BodySessionControlStateCommitReceipt`.

Command admission reads the exact live declaration from the prior composite
head. Its composite successor preserves that declaration head while it installs
the subordinate disposition-journal successor. If declaration retirement,
replacement, authority/lifecycle change, or security/descriptor change orders
first, the expected composite head changes and command admission loses. A
historical declaration or a successful check against an independently changing
selector cannot authorize the append.

Each ingress verifier also maintains one current frame-admission head per
realm, declaration, receiver, and opaque receiver-evidence lineage. The head
binds the direct realm key, declaration digest, receiver principal and
evidence-lineage incarnation, ledger incarnation and state version, highest
contiguous finalized sequence, the bounded set or bitmap of admitted positions
in the declared reorder window, finalized gaps, and prior-head digest. It
excludes its own digest/receipt and successor selector. Admission compares and
swaps the applicable owning composite selector before it emits the generic
`FrameAdmissionHeadCommitReceipt`. A generic receiver uses
`InstalledReceiverAdmissionStateSelector`. In particular, an ADR-004 observer
stores each live frame-admission head inside `ObserverAdmissionStateHead`; grant
renewal,
revocation, expiry, descriptor/security/clock cutover, and frame admission all
compare-and-swap `InstalledObserverAdmissionStateSelector`. A separate frame
selector cannot authorize observer evidence. Its position-specific and generic
receipts directly bind the realm, prior/installed composite heads and selector
version as well as the subordinate frame-head transition.

No standalone declaration, frame, history or lineage-registry selector can
authorize receiver evidence. Declaration retirement/replacement and frame
admission always have one installed local order. If the applicable composite
store cannot perform that compare-and-swap, admission is closed.

For every owner, the applicable commit receipt binds the closed transition kind,
prior and installed state digests, selector version, and receiver-evidence
lineage for genesis, each frame update, and retirement freeze.
A position-specific `FrameAdmissionReceipt` additionally binds the exact stream
position and frame digest to that successful commit. A candidate empty head or
position receipt without the matching commit receipt is not installed evidence.
The closed frame-admission transition union is
`LIVE_GENESIS_FROM_UNINITIALIZED | APPEND_LIVE_FRAME |
RETIREMENT_FREEZE | LATE_ATTACH_GENESIS`.
The `LIVE_GENESIS_FROM_UNINITIALIZED` kind is valid only for a newly authorized
declaration/receiver/evidence-lineage tuple whose winning composite head contains
an exact never-used subordinate allocation marker/key. The same composite
compare-and-swap consumes that marker and installs the live head. It does not
create or consume a subordinate selector. Missing composite state or allocation
evidence for an existing lineage fences that lineage; it never recreates an
empty live head.

The declaration selects one closed sequence policy. `STRICT_MONOTONIC` accepts
only a position greater than the current high-water mark and records any skipped
range as a gap. `BOUNDED_REORDER` can admit a not-yet-seen position only inside
its finite declared window; it finalizes positions and gaps in order. A duplicate,
a conflicting frame digest at one position, or a position behind a finalized gap
rejects regardless of a fresh frame ID. Reconnect, grant renewal, process restart,
or replay of a historical signed head cannot reset this state. If the installed
head is missing, rolled back, ambiguous, or at capacity before safe compaction,
the verifier stops admission and retires the stream or session generation under
the declared policy; it never guesses a new high water.

Declaration retirement first freezes the live-admission head into an
authenticated `RetirementAnchor`. Before the compare-and-swap, the receiver
constructs the anchor from the exact installed live head, its already installed
selector version and last successful `FrameAdmissionHeadCommitReceipt`,
including when the live head is empty. The anchor contains no successor selector
version or `RETIREMENT_FREEZE` receipt. The applicable owning composite selector
then installs the anchor. After the in-transaction compare-and-swap comparison
wins, a new `FrameAdmissionHeadCommitReceipt` with
`RETIREMENT_FREEZE` kind binds the prior live head, installed anchor, selector
version and, for a composite owner, prior/installed composite heads plus generic
commit. The same transaction persists the selector, anchor, generic commit and
complete signed receipt bytes. It exposes the receipt only after durable commit.
The anchor never binds the receipt that installs it and does not delete
the duplicate fence. If an
authenticated descriptor still authorizes post-retirement history, the receiver
can create exactly one bounded `HistoricalAdmissionHead` for that declaration,
receiver, and evidence lineage by compare-and-swap from the retirement anchor.
The retirement transition allocates a never-used `history_state_incarnation` for
that exact anchor and lineage. The first history head binds that incarnation,
`history_state_version = 1`, and the retirement-anchor digest as its predecessor.
Every genesis, history-position update, and closure uses the applicable sole
currentness selector. Each update increments the history state version by
exactly one and binds the exact prior history-head digest. It emits a
`HistoricalAdmissionHeadCommitReceipt` over the incarnation, prior and installed
history state versions, closed transition kind, prior anchor or head, and
installed head or closure state. A generic receiver uses
`InstalledReceiverAdmissionStateSelector`. A role with a stricter owning
composite root updates the historical substate through that composite selector; its
specialized receipt also binds the prior and installed composite heads, selector
version, and generic composite commit. In particular, an ADR-004 observer uses
only `InstalledObserverAdmissionStateSelector`. A signed empty or sibling history
head is not current without the applicable receipt.
The `GENESIS_FROM_RETIREMENT_ANCHOR` kind consumes an exact never-used
historical allocation marker/key in the winning composite head for that anchor
and evidence lineage. It creates no subordinate selector and can occur once.
Absence, restart loss, or a recreated allocation marker after any use fences the
lineage rather than creating a new history head.

The closed historical head transition union is
`GENESIS_FROM_RETIREMENT_ANCHOR | APPEND_HISTORICAL_FRAME |
TERMINALIZE_FROM_HISTORY_HEAD | TERMINALIZE_FROM_RETIREMENT_ANCHOR`.
No historical transition revives live publisher authority.

The trusted history provider is also a receiver under this rule. While the
declaration is live, it admits each history-eligible publisher frame into its own
provider receiver-evidence lineage and retains the immutable frame-admission
receipt. Retirement freezes that provider head into its provider retirement
anchor. A `ProviderHistoryProvenance` reference binds the exact provider,
direct `AuthorityRealmKey`, declaration, stream position, original frame/content
digests, live-admission receipt, provider evidence lineage, retirement anchor,
and current retained ancestry or terminal-checkpoint membership. For a privacy
projection, it also binds the receiver-independent `TrustedProjectionRecord`.
The observing receiver admits that record separately and creates its own
`TrustedProjectionProvenance`; the provider cannot supply the observer's future
receipt.

Every post-retirement history delivery must carry and verify that provenance. A
current query signature, publisher signature created after retirement, query
arrival time, descriptor entry, or observer-local genesis anchor cannot
substitute for proof that the provider admitted the exact original bytes while
the declaration was live. If the provider did not retain that proof, the
position is unavailable or a gap. The observing receiver then advances its own
history-admission head separately; that head prevents duplicate local evidence
but cannot manufacture provider history.

A receiver that first attaches after declaration retirement has no live head to
freeze. It can create an authenticated genesis retirement anchor only for a fresh
receiver-evidence lineage whose separately authenticated installed-current
`ReceiverEvidenceLineageRegistryHead` proves no predecessor. That registry head
binds the direct realm, receiver, registry incarnation/version, active/retired
lineages, and prior-head digest; it excludes its own digest/receipt and successor
selector.
Allocation compare-and-swaps the authority-owned
applicable composite selector. After the in-transaction comparison wins,
`ReceiverEvidenceLineageRegistryCommitReceipt` binds the realm, prior and
installed head digests and selector version. The same transaction persists the
selector, heads and complete signed receipt bytes. It exposes the receipt only
after durable commit.
For a generic receiver, that selector is
`InstalledReceiverAdmissionStateSelector`. For an ADR-004 observer, the lineage-
registry head is
subordinate state inside the installed `ObserverAdmissionStateHead`. Its
allocation, retirement, and first historical admission all compare-and-swap
`InstalledObserverAdmissionStateSelector`; the commit receipt also binds the
prior and installed observer composite heads and selector version. A separate
lineage-registry selector cannot authorize observer evidence.
The top-level composite genesis allocates a never-used registry incarnation and
installs its empty version-1 subordinate registry head in the same transaction.
Its specialized receipt carries `REGISTRY_GENESIS_FROM_UNINITIALIZED` and binds
the prior/installed composite heads; there is no subordinate registry selector.
Storage absence, restart, or incarnation reuse after any committed composite
head is lineage-state loss and cannot recreate an empty registry.
The closed lineage-registry transition union is
`REGISTRY_GENESIS_FROM_UNINITIALIZED | ALLOCATE_EVIDENCE_LINEAGE |
RETIRE_EVIDENCE_LINEAGE`. Each non-genesis transition changes one exact lineage
entry and preserves every sibling.
A historical or sibling empty registry cannot authorize genesis. The anchor binds
the exact declaration tombstone, receiver, lineage, descriptor and history grant,
an empty live-admission summary, and an explicit
`live_delivery_completeness = not_assessed`. It excludes its own installation
receipt and every successor/selector digest. Its installation emits a
`FrameAdmissionHeadCommitReceipt` with the `LATE_ATTACH_GENESIS` transition kind
and initial selector version. It cannot replace a lost, ambiguous, or
rolled-back head for an existing lineage. The body/provider cannot self-attest
that receiver-local absence, and a caller-supplied empty anchor rejects.

The history head binds the exact authorized-history horizon and a bounded
membership summary. It also binds the never-reused history-state incarnation,
strictly increasing history state version, and exact predecessor retirement
anchor or history-head digest. Genesis initializes its membership from the
retirement anchor's bound admission summary: either the live-derived finalized
high water, gap ranges/bitmap and reorder state, or the authenticated empty
genesis summary. It adds a bounded set/bitmap for newly admitted history
positions. It can admit an exact previously unseen position within an
authorized history window, including a former live gap, but it does not rewrite
the live gap or claim live-delivery completeness. A position already admitted
live or through history rejects. Every historical `FrameAdmissionReceipt` binds
the retirement anchor, prior/installed history-head digests, applicable
composite selector version, and matching
`HistoricalAdmissionHeadCommitReceipt`. For an observer, it also binds the
prior/installed `ObserverAdmissionStateHead` digests and generic composite commit.
The canonical history head excludes its own digest/receipt and successor selector.

Only after the authorized history-admission horizon closes does the receiver
construct a receipt-free `FrameAdmissionTerminalCheckpoint`. It binds the
declaration tombstone, retirement anchor (live-derived or authenticated genesis),
optional final installed history head, prior selector version, and the already
installed last `HistoricalAdmissionHeadCommitReceipt` or, when no history head
exists, the already installed retirement-anchor
`FrameAdmissionHeadCommitReceipt`. It also binds receiver-evidence lineage,
history-state incarnation, exact terminal history state version, finalized gaps,
authorized-history reference horizon, and retention state. Terminalization from
history head version N uses terminal version N+1. Direct terminalization from an
anchor uses terminal version 1. It contains no installed terminal selector
version or closure receipt.

One compare-and-swap of the applicable sole composite selector then installs the
checkpoint. A generic receiver uses
`InstalledReceiverAdmissionStateSelector`; an ADR-004 observer replaces the
subordinate history state inside
`ObserverAdmissionStateHead` through
`InstalledObserverAdmissionStateSelector` and preserves every sibling substate.
`TERMINALIZE_FROM_HISTORY_HEAD` consumes the exact current history head.
`TERMINALIZE_FROM_RETIREMENT_ANCHOR` consumes the exact unused historical
allocation marker/key in the current composite head for that anchor when no
history head is permitted. After the in-transaction compare-and-swap comparison
wins,
`HistoricalAdmissionHeadCommitReceipt` binds the prior head or anchor, installed
checkpoint, history-state incarnation, prior and terminal history state versions,
installed selector version, and closed terminalization kind. For a composite
owner, it also binds the prior/installed composite heads and generic commit. The
same transaction persists the selector, checkpoint, generic commit and complete
signed receipt bytes. It exposes the receipt only after durable commit. The
checkpoint never binds that post-CAS receipt.

The checkpoint is retained while any immutable admission receipt or capture
lineage can reference that stream. If bounded checkpoint capacity would force
earlier eviction, the verifier first durably fences and finalizes the affected
receiver-evidence lineage and prevents any later history result from claiming
continuity with it. A fresh lineage can be explicitly authorized, but its
receipts cannot be combined with the fenced lineage to assert lifetime
deduplication or complete capture. If that separation cannot be enforced, the
receiver fences the entire session generation before eviction.

Plane declarations are non-fungible. A perception declaration does not authorize
action publication, and an observer grant does not authorize any declaration.

Portable consumers key stream, gap, admission, disposition, history, projection,
and capture state first by the exact
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` foreign key,
then by declaration and position. Equal publisher, receiver, session text,
generation, declaration generation, stream epoch, sequence, frame bytes, and
receipt digests in different realms remain separate lineages. No replay,
deduplication, resumption, history merge, or continuity proof can cross the realm
boundary.
The tuple is encoded once in each canonical realm-scoped object: its direct
`authority_realm_key` is the first member and the three session coordinates
complete it. A duplicated compatibility field must equal that direct member or
the object rejects.

## Low-overhead stream reconciliation

Each declaration binds one receiver-owned publisher incarnation. A reconnect,
publisher failover, or second simultaneous connection cannot share its allocator,
epoch, grant, or replay state. Retirement is a control transition. Data cannot
create, renew, replace, or retire a declaration.

One lease-bound action declaration accepts Active, explicit HOLD, and any ESTOP
permitted for that authenticated lease holder. An enrolled emergency principal
uses a separate ESTOP-only declaration. Each declaration owns its own position
allocator and replay state. The body owner merges their events without comparing
positions across declarations.

Ordinary HOLD admission retires its live declaration before the installed HOLD
operation runs. In that same transition, policy can preserve a bounded
ESTOP-only escalation snapshot over explicitly authorized unused slots and their
unchanged deadline. The snapshot admits no Active or HOLD work, allocates no new
position, and cannot refresh authority. A later ESTOP must match that preserved
publisher, declaration, stream, security state, slot, and deadline.

The body issues bounded freshness grants before command publication. Each grant
binds:

- one declaration, publisher incarnation, and stream epoch.
- one receiver clock and exclusive deadline.
- one non-overlapping position range and its permitted modes.
- complete reserved state and each required lease coordinate.

The first range starts at position one. A successor starts at the prior range's
exclusive end. Assignment consumes a position before serialization or queue
admission. Later failure creates a visible gap. A position selects at most one
grant, so a compact command repeats no grant, lease, or TTL field.

One command position represents one setpoint and one application attempt. It
does not replay a predictive horizon. A trajectory requires a separate profile
with per-step authority, source, deadline, admission, and disposition rules.

A source-bound Active declaration binds one exact perception declaration and
epoch. The body retains a finite source-publication window by entry count,
aggregate bytes, and receiver-local lifetime. Admission pins the exact matching
record and prepared safety projection. An absent or evicted record rejects. A
timestamp, bare position, digest without values, or latest-value fallback cannot
replace it.

A prepared simulation-step declaration uses the same no-reuse principles. Its
grant binds one receiver clock and one non-refreshing exclusive grant deadline.
It reserves a contiguous request range, strict execution cursor, request and
response slots, exact digest state, aggregate bytes, and one non-refreshing gap
deadline. Grant expiry rejects unconsumed positions and retires the simulation
generation. A response correlates by request position, never FIFO arrival.

B03 can select finite identity names and checked numeric ceilings only. The
reorder limit can be zero only for strict in-order admission. Every other
selected numeric ceiling is positive. Stream-specific queue, byte, deadline,
and retention values use the bounded ADR-010 profile envelope. Every ceiling
must also fit its aggregate byte and owner-state budget. Unknown,
zero-authority, overflowed, uninstalled, or incompatible selections reject
before allocation. B03 cannot change the lifecycle, position, no-reuse, or
correlation meaning above.

## Rejected alternatives

- Adopt the first valid frame's epoch.
- Rotate automatically at sequence maximum.
- Treat epoch UUIDs as ordered counters or timestamps.
- Reset high water after timeout, reconnect, or HOLD.
- Deduplicate only by frame ID while accepting the same stream position again.
- Trust a self-attested or historically signed high-water snapshot as current.
- Share one epoch across different publishers, planes, routes, or message kinds.
- Continue a session generation after forgetting a retired epoch.
- Infer realm from a route, descriptor, parent receipt, session ID, generation,
  or local store instead of carrying the direct `AuthorityRealmKey`.
- Merge same-principal/session/generation/epoch/sequence bytes across realms.

## Illustrative wire example

```json
{
  "ncp_version": "1.0",
  "kind": "declare_stream",
  "authority_realm_key": {
    "server_authority_principal_id": "ncp-authority-a",
    "stable_realm_id": "realm-a"
  },
  "session_id": "plant-alpha",
  "session_generation": "00000000-0000-4000-8000-0000000000a2",
  "plane": "action",
  "route": "realm-a/session/plant-alpha/command/controller-a",
  "message_class": "command_frame",
  "stream_epoch": "00000000-0000-4000-8000-000000000001",
  "sequence_start": 1,
  "publisher_principal_id": "haldir-commander-a"
}
```

## Invalid or hostile example

```json
{
  "ncp_version": "1.0",
  "kind": "command_frame",
  "stream": {
    "epoch": "00000000-0000-4000-8000-000000000099",
    "seq": 1
  },
  "session": {
    "generation": "00000000-0000-4000-8000-0000000000a2"
  }
}
```

A live-ingress frame rejects when no exact live declaration exists, even if its
syntax and session generation are otherwise valid. This example also omits the
required direct `AuthorityRealmKey`, so it rejects before declaration lookup.
Post-retirement historical delivery instead requires the exact retained
declaration tombstone, descriptor window, `ProviderHistoryProvenance`, receiver
retirement anchor, and installed history-admission head.

## Actors and state transitions

`ABSENT -> DECLARING -> LIVE -> RETIRING -> RETIRED`.

Exhaustion, publisher change, security-state change, session retirement, schema
change, or explicit revoke moves to `RETIRED`. A fresh declaration uses a new
epoch and starts at sequence `1`. A retired epoch never returns to `LIVE`.
Every state is scoped by one immutable direct `AuthorityRealmKey`. A realm
change selects a different state machine and cannot transition or restore this
one.

Receiver evidence admission is separate:

`LIVE_ADMISSION -> RETIREMENT_ANCHORED ->
HISTORY_ADMITTING/TERMINAL_CHECKPOINT -> TERMINAL_CHECKPOINT/FENCED`.

A late-attaching fresh lineage starts at an authenticated genesis
`RETIREMENT_ANCHORED` state. None of these receiver states revives publisher
authority.

## Bounds and resource behavior

Declaration bytes, realm keys, streams per
realm/session/principal/plane, channels, schema size, route length, high-water
entries, retirement tombstones, duplicate retention, retirement anchors,
historical-admission heads and membership sets, terminal admission checkpoints,
lineage-registry heads, receiver-evidence lineages, authorized-history horizons,
and operation retries are finite. Capacity
exhaustion rejects
declaration before allocating publisher state. Tombstone or checkpoint capacity
exhaustion fences the affected lineage or whole session generation before
eviction; it does not make an old epoch or position reusable in a continuing
lineage.

## Threat and hazard analysis

This prevents first-frame authority, unauthorized epoch injection, replay after
quiet periods or tombstone eviction, silent rollover, cross-plane use, and
unbounded high-water state. Provider history provenance also prevents a retired
publisher from creating outcome-informed frames and presenting them as
pre-retirement history. State loss can cause denial; it must not cause
acceptance. Durable storage rollback and multi-instance ownership require
external design and testing.

The direct realm member prevents a declaration, first frame, high-water head,
retirement anchor, history proof, or receiver receipt from being transplanted
into another realm that reused the same principals and session/generation text.
Checking only a route or transitive parent would fail once evidence is exported
or projected. Realm validation therefore precedes state-key lookup and semantic
allocation.

## Formal properties

- Every realm-scoped request, result, frame, key, head, selector, fact,
  tombstone, checkpoint, provenance object, and receipt named by this ADR has one
  direct non-default `AuthorityRealmKey` in its canonical bytes.
- That realm key equals the authenticated ingress realm, default-deny manifest
  scope, audience, route projection, descriptor, transcript, declaration,
  owning selector, and every predecessor or successor in its proof chain.
- A canonical projection or consumer index that drops, defaults, wildcards, or
  rewrites the realm is invalid.
- Same-principal, same-session-kind, same-logical-session-ID, same-generation,
  same-declaration, same-epoch, same-sequence, and same-frame bytes under
  different realm keys cannot share a declaration, replay decision, high water,
  gap, receipt, retirement anchor, history lineage, or terminal checkpoint.
- An exact frame-byte replay under another authenticated realm rejects before
  declaration lookup. A separately valid frame with all non-realm fields equal
  but either realm-key coordinate changed belongs to a distinct declaration and
  receiver-evidence lineage.
- A bare `StreamPosition` is never sufficient as a realm-scoped identity.
- Every live-ingress frame maps to exactly one live declaration. Exact historical
  evidence maps to one authenticated retired declaration/tombstone and its
  anchored history-admission head.
- Publisher source sequence for an epoch strictly increases and never wraps.
  Historical positions can arrive out of order; the receiver admission-ledger
  state version still increases by exactly one for each successful compare-and-
  swap.
- A historical admission lineage has one never-reused history-state
  incarnation. Its version starts at 1 and increments by exactly one through
  every head and terminal checkpoint. A stale, sibling, repeated, skipped,
  rolled-back, exhausted or unreceipted version rejects.
- One receiver-evidence lineage admits a stream position at most once. A new
  frame ID, live/history transition, retirement, post-retirement history, or
  terminal-checkpoint compaction cannot bypass the retirement anchor and
  installed live/history admission head.
- Empty live and history genesis states, every admission update, retirement
  freeze, and history closure have an installed-selector transition receipt.
  A losing or sibling empty head, stale closure, or zero-result terminal
  checkpoint cannot become authoritative.
- Retirement anchors and terminal checkpoints are receipt-free pre-CAS content.
  Each binds only already installed predecessor evidence; the post-CAS receipt
  binds the installed anchor/checkpoint and can never be embedded in it.
- Only the top-level role or generic receiver composite genesis consumes a
  parent-allocated `UNINITIALIZED` selector. It atomically installs declaration
  and lineage-registry version-1 heads. Later live and historical genesis
  consume exact never-used subordinate allocation markers/keys in the winning
  composite head. No subordinate selector exists. Missing state after use is
  fenced as corruption and never interpreted as empty genesis.
- A body action-command declaration uses
  `COMMAND_DECLARATION_GENESIS_FROM_BODY_SESSION_CREATION` and the sole
  body-session-control selector instead of an independent declaration selector.
  Declaration retirement and command admission therefore have one installed
  order.
- A retired epoch cannot publish, revive, or redeclare. Its exact retained bytes
  can enter historical evidence only through exact
  `ProviderHistoryProvenance`, the receiver retirement anchor, and the
  history-admission head. A query-time signature or post-retirement publisher
  signature cannot create historical eligibility.
- No frame changes declaration state.
- For a generic receiver, declaration, lineage and live/history admission state
  share `InstalledReceiverAdmissionStateSelector`. A declaration retirement or
  replacement and a frame append therefore have one local order. A pre-change
  append can commit only before that change; a post-change append under the old
  declaration loses. Independent check-then-CAS selectors cannot admit frames.
- Descriptor replacement and generic receiver admission have one local order
  through that selector. An old-descriptor append loses when replacement wins
  first; replacement after an append retains the old evidence but fences it from
  new admission.
- Realm, plane, route, class, session, publisher, and security context match
  exactly.
- A historical declaration or frame-admission head, ledger rollback, or
  tombstone-capacity transition cannot revive an epoch or duplicate a finalized
  position.
- A terminal admission checkpoint remains authoritative for its complete
  reference horizon only when its receipt-free content binds the exact installed
  predecessor history head or retirement anchor, the predecessor selector
  version, and its already installed last commit receipt. Its installation then
  requires the post-CAS terminalization receipt from the applicable sole owning
  composite selector. Eviction first fences the evidence
  lineage, and no later history receipt can claim continuity with that fenced
  lineage.
- A post-retirement history position can enter evidence only through the one
  bounded history head anchored to a live-derived or authenticated genesis
  retirement anchor. It remains historical evidence and cannot erase a recorded
  live gap or imply live completeness.
- A first post-retirement attachment uses an authenticated genesis retirement
  anchor in a proved-fresh evidence lineage selected by the installed-current
  lineage-registry head and records live completeness as `not_assessed`. It
  cannot mask receiver state loss, replay a historical empty registry, or accept
  a sibling lineage-registry head.

## Migration

Publishers add declare/retire operations before emitting native frames. Existing
implicit-adoption helpers are deleted or confined to labeled legacy gateways.
Consumers persist high water and explicit gaps under the full
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` key. The
native corpus includes same-principal/session/generation/bytes different-realm
replay and merge mutants, plus a projection that drops only the realm.

## Operational recovery

If declaration state cannot be proven current after restart, the receiver
rejects frames and retires the session generation. A publisher never guesses
whether a prior declaration committed; it queries by idempotency context and
exact realm. Recovery never attaches a stored declaration or high-water head to
a different realm.

## Compatibility and rollback

This is a pre-release wire/lifecycle correction. Rollback disables the new native
session as a whole; it cannot keep new frames with old implicit adoption.

## Open questions

<a id="ncp-b01-selector-allocation-adr-005-v1"></a>

Exact interface names, sequence and reorder limits, and tombstone capacities
remain implementation-allocation inputs. The lifecycle, admission, retirement,
and no-reuse rules are closed.

B03 selects 1 through 32 canonical interface identities. Each identity matches
`[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?` and can name only an implementation
boundary defined by this ADR. It cannot add a transition or authority path. The
sequence limit is 1 through 9,007,199,254,740,991. The reorder limit is 0 through
4,096, and tombstone capacity is 1 through 65,536. The selected capacities must
also fit their declared aggregate byte and terminal-state budgets.

The reorder limit counts retained positions beyond the next expected position.
Zero selects strict in-order admission and requires no reorder buffer.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: stream creation is an operation, not a frame side effect.
2. Security: realm, publisher, route, plane, class, and session bind exactly.
3. Safety: stale action streams cannot revive.
4. Lifecycle: restart, exhaustion, retire, and redeclare are explicit.
5. Resources: state and tombstones are finite.
6. Migration: gateways label legacy implicit behavior.
7. Science: observation gaps remain exact.
8. Operations: publishers can query ambiguous declarations and recover.
9. Evidence: reorder, replay, exhaustion, restart, ledger rollback, tombstone
   eviction, and cross-plane vectors run.
10. Governance: stream schema and publisher ownership are registered.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes.
