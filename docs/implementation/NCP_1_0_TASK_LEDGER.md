# NCP 1.0 implementation task ledger

> **Generated file — do not edit.** Edit
> [`task-ledger.v1.json`](../../evidence/implementation/task-ledger.v1.json), then
> use the pinned workflow in **Update and verification** to regenerate with
> `--write` and verify with `--check`.
> This is evidence bookkeeping, not release authorization or certification.

Blueprint SHA-256: `d9bed647de517726ce9149aed76933be6b3a83875d27b16cfe378787d4235a4d`.

Can this ledger grant release authorization? **false**.

## Current decision

The candidate remains **NO_GO**. A local pass means only that a bounded
repository-local acceptance slice passed. External and independent obligations remain
separate, and publication tasks cannot start through a status edit.

| Status | Count |
|---|---:|
| `OPEN` | 57 |
| `IN_PROGRESS` | 1 |
| `BLOCKED` | 0 |
| `LOCAL_PASS` | 2 |
| `EXTERNAL_PASS` | 0 |
| `INDEPENDENT_PASS` | 0 |
| `COMPLETE` | 0 |

Active tasks: `B01`.

Dependency-ready open tasks: none.

The checked execution DAG is graph-theoretically transitively reduced. Each direct
edge adds one ordering constraint; chained content-addressed receipts retain the
complete prerequisite ancestry.

## Active task recovery checkpoints

### `B01` — Decide and ratify ADR-001 through ADR-011

ADR-003, ADR-004, ADR-005, ADR-006, ADR-007, ADR-010, ADR-011, the D18 migration model, the D19 ratification/promotion state machine, and consumer task scopes were amended after cross-repository review. The amendments define metadata counting, generic versus checked Active admission, plant value and unit preservation, restrictive body-local effect ordering, and hostile replay causality and freshness. Earlier commits, issue requests, model results, and clean gates bind superseded bytes only. They remain historical non-passing working evidence. The latest packet subject binds clean pushed source commit 99672dd48bffe3f8504d4fb66d5a7c9140b122cf and decision-set digest 794c90203c662f1e12d78844c8ac8dcfc0162b0d3813b7df04cbe2e10cdd835a. It is superseded and has zero review records. Composite local runs covered every command in `scripts/check.sh`. One uninterrupted attempt stopped only when crates.io timed out during the Python source-distribution build. The exact failed step and remaining suffix then passed separately. The exact clean B01 runner passed. The bounded 22-case, 90-mutation semantic replay passed. A hostile `dict`-subclass self-test requires one fresh replay-oracle build before caller-controlled serialization and rejects candidate influence on that oracle. These local results do not satisfy B01's independent evidence floor and are not passing task evidence. The Ed25519 screen uses a fixed-sample p95 computational tripwire of 100,000 microseconds for thread and process CPU. Maximum CPU and wall time remain observational. This coordination entry has no task source commit, same-digest request, owner or independent review, command receipt, or artifact receipt. All ADRs remain PROPOSED, and B01 remains IN_PROGRESS. Obtain qualifying same-digest reviews and external adjudications before a passing B01 receipt. Do not create the normative registry, start descendants, or infer release readiness.

Current residual risks:

- All eleven ADRs remain PROPOSED and have no qualifying owner or independent same-digest review; B01 has not reached any passing evidence class.
- The generated registry is intentionally non-normative and outside contract/; promotion and the deliberate candidate rebaseline remain blocked.
- The 22 JSON fences remain proposed profile excerpts, not accepted production wire. Separate content-bound Rust and TypeScript profile engines agree on all 22 semantic cases. They reject 90 registered bounded mutations under local non-authorizing profiles.
- The harness identifies incomplete or non-wire examples instead of promoting them. Complete production examples, the syntax-only Python/Node replay, and preliminary model/resource results do not satisfy B01.
- B01 inventories a declared 69-file source/support set under a 72-file cap, leaving three slots. Python imports precede the first snapshot. This is not pre-import attestation or complete execution provenance. The root lock pins TypeScript 5.9.2. Installed TypeScript compiler, Rust, Cargo, and Bun identities are unretained. CI pins Rust 1.88.0 and Bun 1.3.14 without proving provenance. The reader rejects leaf links and in-read changes. Privileged parent-directory replacement is outside this filesystem claim.
- The latest review subject binds clean pushed source commit 99672dd48bffe3f8504d4fb66d5a7c9140b122cf, has zero reviews, and is superseded. Review capture is disabled during semantic-closure work. No owner review, independent review, external adjudication, or passing B01 receipt exists. Canonical formal work, refinement, and every downstream implementation remain open.
- The declared 256-entry metadata ceiling has no accepted trusted-message-class and decoded-path registry or equal Rust, TypeScript, and Python preallocation enforcement. The current Python developer reader applies a post-parse name heuristic. N01, N02, N03, N06, N07, N08, B02, and B03 remain open.
- Checked codec paths can invent missing midpoint or zero values, accept sparse components, and select a unit by mapping order. The existing plant helper is not integrated into Active admission, and the `PlantCommand` projection erases units. ADR-007 restrictive effect ordering must remain unchanged. N01, N03, N05, N07, N08, B02, B03, E04, H02, and C02 remain open.
- Descriptor scans establish pin coherence only. They do not define the canonical historical handoff-surface inventory, discover role subjects, or issue a role receipt. The current nine-role inventory contains absent and legacy-wire implementations, the thesis descriptor is auxiliary non-peer audit tooling, trusted repository/build/deployment scans and independent scope adjudication are NOT RUN, and N07 remains open.
- The local Ed25519 probe uses a fixed-sample p95 computational tripwire for thread CPU and process CPU at 100,000 microseconds. Maximum CPU and wall time remain observational. The probe records clock metadata, exact PyNaCl project and `uv.lock` identities, and the uv runner digest and version. The probe runs actual result-validator mutations. End-to-end latency, shared-resource behavior, and performance qualification remain NOT RUN.
- Five usable exact Fable 5 consultations bind earlier decision bytes and are historical non-normative challenge input only. Five failed or incomplete attempts returned no complete usable answer, and no model response counts as review, proof, interoperability, or evidence.
- The current 1.0.0-rc.1 normative digest and compact hash are unchanged; external security, plant, consumer, performance, supply-chain, and release gates remain NOT RUN or blocked.

## Three required review perspectives

| ID | Perspective | Blueprint lenses | Required question |
|---|---|---|---|
| `P1` | Protocol and security correctness | `L1`, `L2`, `L3` | Does the change preserve exact semantics, verified identity and authority, fail-closed behavior, and the plant safety boundary under hostile or ambiguous input? |
| `P2` | Consumer and runtime usability | `L4`, `L5`, `L6`, `L8` | Can independent consumers implement, operate, observe, recover, migrate, and bound the behavior without private forks or unsafe defaults? |
| `P3` | Operational and scientific evidence | `L5`, `L7`, `L9`, `L10` | Do retained evidence, statistics, non-claims, independent review, release governance, and lifecycle ownership justify exactly the stated status? |

Every task must also pass all ten blueprint lenses. `NOT_APPLICABLE` requires a
specific rationale and reviewer; it is not an omitted review.

## Evidence floors and checked gate names

`LOCAL` is bounded repository evidence only. This checker has no separately
authenticated independent verifier boundary. It therefore rejects every
`EXTERNAL_PASS`, `INDEPENDENT_PASS`, and externally dependent `COMPLETE`
transition before local JSON, URLs, booleans, reviewer labels, Git refs,
remote-tracking observations, or in-process cryptography can affect status.
The catalog retains external and independent floors as work requirements, not as
reachable local states. B01/B02 adjudication remains proposed. X05 signature,
trust-root, qualification, revocation, and currentness acceptance parsers are
absent from this checker, which has no cryptographic dependency or trust-root
configuration path. Local claims cannot promote a task.
B01 stays `IN_PROGRESS`; X05 stays `OPEN`; their external gates stay **NOT RUN**.
A future admission path requires an explicit reviewed checker and schema change
that integrates a separately authenticated and independently qualified verifier.
There is no configuration switch or trust-root entry that enables admission.
Every retained local receipt binds one canonical transition subject. It contains
the task ID, from/to states, requirement-and-acceptance digest, exact repository
policy and unambiguous branch, immutable local source/evidence cuts, exact dependency
receipt generation, task-subject generation, and correlation ID. A receipt copied
to another task, transition, repository, source generation, or dependency cut rejects.
Dependency receipts must be strictly older than the dependent receipt. When both
receipts use one repository, the dependency source cut must be an ancestor of the
dependent source cut. Pass-class source and subject identity cannot change without
an `IN_PROGRESS` reopen and exact descendant invalidation.
The source and strict-descendant evidence cuts identify regular local Git blobs.
Local origin configuration, advertised-object text, and remote-tracking refs are
diagnostic observations only; they do not prove configured-remote reachability.
Reviewer identities must be disjoint from the task-wide implementation-owner union.
That name separation remains local structure and never proves independence.
B03 additionally binds the exact six registry files plus CODEOWNERS. Its bounded
artifact uses canonical ordering. Every allocation resolves one exact committed
registry object through a canonical RFC 6901 pointer and binds that object's checked
kind, identifier, owner, and canonical value digest. Missing, wrong, duplicate, or
alias pointers reject. Identifiers use printable ASCII; case-fold collisions, wildcard
aliases, and overlapping extension prefixes reject.
Every resolved object carries the exact common allocation-metadata projection:
owner and nonempty code-owner tokens, closed stability class, wire/session/actor/plane
applicability, authority
effect and explicit preconditions, bounded constraint IDs, fail-closed unknown/default
behavior, conformance obligations, and an identifier-nonreuse retirement/migration
rule. All B03 allocations apply only to wire 1.0. Unknown wire, session type, actor,
plane, authority proof, bound, identifier, required metadata, or retirement state
grants no authority. Missing common fields, catch-all actors, or granting defaults
reject.
A bounded safe-subset CODEOWNERS parser applies case-sensitive last-match semantics.
Each allocation's exact tokens must equal the effective rule for its registry path;
unsupported negation/escaping/range syntax, an empty late override, or an unmapped
token rejects. This proves repository-text coverage only. It does not prove that an
account or team exists, has permission, reviewed the change, or supplied external
authorization; those gates remain NOT RUN until separate exact evidence exists.
Consumer surface discovery uses separate canonical
`.ncp-surface-inputs.v1.json` / `ConsumerSurfaceInputManifest`. The manifest binds
the repository/root/target/feature/role/activation inputs and exact tracked build,
package, lock, patch, CI, and deployment references. Resolution contexts and
`DiscoveryRecord` values bind that manifest plus the actual build and deployment
manifests. A resolution context binds only pre-build inputs, never a resulting
artifact. Discovery computes the resulting artifact digest separately after the
context. Any discovery-bound artifact excludes `.ncp-consumer` bytes and digest;
the descriptor is sibling metadata generated last. The acyclic order is input
manifest, resolution context, artifact digest, discovery record, then descriptor.
The input-manifest content excludes its own digest and every later
discovery, scan-receipt, generated-view, and inventory-output digest.
`.ncp-consumer` is an output inventory descriptor. It may bind the input
manifest, scan receipt, and discovery-record digests, but its bytes are excluded from
every surface key, context, discovery, and scanner-input digest that it contains.
This removes direct and transitive self-hashes. A synchronized Python mirror locator
binds the surface-input manifest, `ncp/.mirror-ref`, actual package manifest, and
runtime module; it never uses `.ncp-consumer` as a locator input.
Each repository has one `ConsumerSurfaceInventoryStateHead`,
`InstalledConsumerSurfaceInventoryStateSelector`, and
`ConsumerSurfaceInventoryStateCommitReceipt`. The head binds one stable repository
inventory-authority scope, a never-reused inventory-state incarnation, repository and
source-tree identity, descriptor floor, input manifest, complete context/discovery
sets, output descriptor, complete canonical `TrustedSubjectAuthorizationState` and
`TrustedScannerAuthorizationState` values plus their recomputed
`trusted_subject_authorization_state_digest` and
`trusted_scanner_authorization_state_digest`, only
independently trusted subject receipts, current surfaces, closed authority status, and
prior head. Its state version is one at genesis
and exactly prior plus one after
that. It excludes its own digest, selector, commit, successors, and later
materialization or deployment evidence.
`TrustedSubjectAuthorizationState` binds that exact inventory scope/incarnation,
authorization domain, policy digest/version, a bounded sorted unique current set of
authorized subject-receipt digests, and authenticated owner grant/revoke/replacement
evidence ancestry. `TrustedScannerAuthorizationState` binds the same scope/incarnation,
each authorized scanner principal, its content-addressed executing binary and resolved
dependency closure, scan-policy digest/version, receipt-eligibility rule, and
authenticated owner grant/revoke/replacement evidence. Revocation removes an entry
from the current eligible set but retains bounded evidence ancestry. Each state is
canonical subordinate content with no independent selector; its domain-separated
digest is recomputed from that content. A bare digest, caller-provided state, default,
self-grant, stale sibling, or wrong-scope state cannot authorize repin.
`SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED` consumes exactly one authenticated
parent-authority creation receipt and the matching never-used selector in
`UNINITIALIZED`; the receipt, selector, and version-one head bind the same scope,
incarnation, and repository. Every successful transition increments selector and
state versions by exactly one. Missing or recreated selectors, caller-supplied or
post-use `UNINITIALIZED`, reset, rollback, storage loss, sibling genesis, or reused
incarnation fence the authority and disable repin; none is a new genesis.
The total transition union is
`SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED`,
`SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP`, `DESCRIPTOR_VERSION_FLOOR_ADVANCE`,
`TRUSTED_SUBJECT_AUTHORIZATION_GRANT`,
`TRUSTED_SUBJECT_AUTHORIZATION_REVOKE`, `TRUSTED_SCANNER_AUTHORIZATION_GRANT`,
`TRUSTED_SCANNER_AUTHORIZATION_REVOKE`, `FENCE_INVENTORY_AUTHORITY`, or
`RETIRE_INVENTORY_AUTHORITY`. Floor advance, authorization grant/revoke, fence,
scanner authorization grant/revoke, retirement, and repin all compare-and-swap the
same inventory selector and preserve
unrelated pins, surfaces, receipts, and evidence. Commit receipts bind prior and
installed floor, both canonical authorization states and recomputed digests, authorized
sets, authority status, heads, and versions. A separate authorization root is acceptable
only when the inventory CAS
conditionally compares its exact version in the same proven local transaction;
check-then-CAS across stores disables repin.
Repin requires the exact current authorized scanner principal, executing binary and
dependency closure, scan-policy version, grant evidence, and eligible scan receipt.
Scanner revocation before repin makes that CAS lose; repin installed
first remains ordered evidence and the later revocation disables or fences according
to policy. A same-predecessor race has one winner. Local fixture evidence does not
prove a real scanner execution; that external evidence remains `NOT_RUN`.
The closed status is `ACTIVE`, `MIGRATION_REQUIRED_DISABLED`,
`AUTHORIZATION_REVOKED_DISABLED`, `FENCED`, or `RETIRED`. A floor advance above the
current descriptor preserves evidence and atomically enters migration-disabled state;
a subject or scanner revocation similarly preserves evidence and enters
authorization-disabled state. Only a fully validated repin or authorization grant under
the current floor and
authorization state can restore `ACTIVE`. Unknown/default state never activates.
A repin stages and rescans content-addressed inputs first, derives
contexts/discovery next, builds `.ncp-consumer` last, validates the complete post-state,
then compare-and-swaps one repository-local successor while preserving every unrelated
surface and receipt. The transaction covers only that local durable inventory object.
Working-tree changes, Git refs, build, deployment, and other repositories remain later
receipted steps; cross-repository migration is staged, never atomic.
Empty state is never inferred from storage absence. Parent-scope creation allocates
each required child domain with a fresh never-used incarnation and an authority-owned
selector explicitly in `UNINITIALIZED`; the closed domain genesis compare-and-swaps
that state once and emits its normal post-CAS commit receipt. A signed empty head,
sibling genesis, caller-supplied uninitialized marker, post-use absence/reset, restart
loss, or incarnation reuse rejects and invokes the domain fence, HOLD, lineage
retirement, session-generation retirement, or security-domain retirement rule.
The allocation set must include the closed frame-admission sequence-policy values;
`DeclarationLedgerHead`, `InstalledDeclarationLedgerSelector`, and
`DeclarationLedgerHeadCommitReceipt`. For action-command scope,
`COMMAND_DECLARATION_GENESIS_FROM_BODY_SESSION_CREATION` installs the declaration
head under the body-session-control composite; the standalone declaration selector
has no effective currentness authority. The set must also include generic
`ReceiverAdmissionStateHead`, `InstalledReceiverAdmissionStateSelector`, and
`ReceiverAdmissionStateCommitReceipt`; plus `FrameAdmissionHead`,
`InstalledFrameAdmissionSelector`, `FrameAdmissionHeadCommitReceipt`, and the
position-specific `FrameAdmissionReceipt`;
receiver-evidence lineage plus `ReceiverEvidenceLineageRegistryHead`,
`InstalledReceiverEvidenceLineageRegistrySelector`, and
`ReceiverEvidenceLineageRegistryCommitReceipt`; and the retirement anchor, bounded
`HistoricalAdmissionHead`, `InstalledHistoricalAdmissionSelector`,
`HistoricalAdmissionHeadCommitReceipt`, and terminal checkpoint. Canonical heads
bind prior content but exclude their own digest, receipt,
and successor selector. Installed selectors provide currentness; external receipts
bind successful prior-to-installed compare-and-swap transitions. The lineage-registry
head prevents a stale or sibling empty registry from authorizing genesis. Retirement
freezes live admission.
For a receiver without a body or observer stricter root,
`ReceiverAdmissionStateHead` is the sole composite currentness object. It binds a
never-reused scope/incarnation, strict state version and prior head, current
`ObserverDescriptor` revision/digest/lineage, subordinate
declaration and receiver-lineage-registry heads, and a bounded per-stream map of live,
retirement-anchor, history, and terminal states. Declare, retire, redeclare, lineage
allocation/retirement, live append, retirement freeze, late attach, history append,
descriptor replacement, and terminalization all compare-and-swap
`InstalledReceiverAdmissionStateSelector`. Every unrelated declaration, lineage, and
stream substate stays byte-identical. A retirement and frame append from the same
predecessor cannot both install: retire-first makes append lose; append-first requires
retirement to preserve that installed frame. Descriptor replacement races use the
same ordering: descriptor-before-operation invalidates the stale operation, while an
operation installed first is preserved by the later descriptor transition.
Body and observer composite roots remain stricter for their scopes. No standalone
declaration, frame, lineage-registry, or historical selector can authorize receiver
evidence in generic, body, or observer scope. Specialized receipts bind the exact
prior/installed owning composite heads, selector version, and generic composite
commit; the successor head never binds its post-CAS receipts.
Each retirement transition allocates a never-reused `history_state_incarnation` for
the exact anchor and receiver-evidence lineage. The first historical head binds
`history_state_version = 1` and the anchor predecessor; every history update binds
the exact prior head and increments that version by one. Terminalization from head
version N installs a checkpoint at N+1, while direct terminalization from an anchor
uses terminal version 1. `HistoricalAdmissionHeadCommitReceipt` binds the exact
incarnation and prior/installed versions. Repeated, skipped, stale, sibling,
rolled-back, exhausted, or unreceipted versions reject. For an ADR-004 observer,
version advance is subordinate to the observer composite selector only.
The exact one-shot genesis kinds include
`RECEIVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED`, declaration
`GENESIS_FROM_UNINITIALIZED`, live
frame `LIVE_GENESIS_FROM_UNINITIALIZED`, lineage-registry
`REGISTRY_GENESIS_FROM_UNINITIALIZED`, and historical
`GENESIS_FROM_RETIREMENT_ANCHOR`. Each consumes the parent-allocated uninitialized
selector and fresh incarnation once; post-use absence or reuse invokes the applicable
session or lineage fence.
Generic receiver genesis atomically installs composite version 1 with empty
declaration-ledger version 1, empty lineage-registry version 1, and an empty bounded
admission map. It emits the composite commit and subordinate receipts; those
subordinate receipts bind the already installed generic commit. Post-use absence,
reset, storage loss, sibling state, or incarnation reuse fences the receiver scope.
The exact retirement and terminal kinds are `RETIREMENT_FREEZE`,
`LATE_ATTACH_GENESIS`, `TERMINALIZE_FROM_HISTORY_HEAD`, and
`TERMINALIZE_FROM_RETIREMENT_ANCHOR`; an unknown, mixed, inferred, or generic
closure kind rejects.
A late history-only receiver uses an authenticated genesis anchor bound to the
tombstone, receiver, lineage, and exact history grant; it proves no live delivery.
One historical head can admit only unseen positions in its authorized window without
erasing live gaps or completeness. The terminal checkpoint is created only after that
horizon closes. A frame-head commit receipt covers live genesis, every live update,
retirement freeze, and late-attach genesis; a position receipt binds the applicable
head commit. A historical-head commit receipt covers history genesis, every update,
and either exact terminal kind. Before `RETIREMENT_FREEZE`, the receiver constructs
the receipt-free retirement anchor from the exact installed live head, prior selector
version, and already installed last frame-head commit receipt. The anchor excludes
the post-CAS `RETIREMENT_FREEZE` receipt and successor selector version. A late-attach
anchor likewise excludes the post-CAS `LATE_ATTACH_GENESIS` receipt.
Before terminalization, the receiver constructs the receipt-free checkpoint from the
exact installed history head or retirement anchor, prior selector version, and the
already installed last historical-head or anchor frame-head commit receipt. The
checkpoint excludes the post-CAS `HistoricalAdmissionHeadCommitReceipt` and installed
terminal selector version. Only the applicable selector CAS installs the anchor or
checkpoint; its exact closed-kind receipt is emitted afterward. A losing or sibling empty
head, stale closure, or zero-result checkpoint without those receipts rejects. The
checkpoint remains authoritative for its reference horizon; eviction first
fences the lineage, and a fresh lineage cannot be pooled with it as complete or
duplicate-free.
`ObserverAuthorizationStateHead` is the server-side composite currentness root. It
binds the logical session/generation, never-reused scope/incarnation, strict state
version and prior head, current `ObserverDescriptor` revision/digest/lineage with
privacy/security binding, and subordinate `ObserverGrantRegistryHead`. The registry
is the keyed map. Its canonical `ObserverGrantRegistryKey` contains exactly the
requester principal and never-reused grant-lineage ID; it excludes session,
generation, registry incarnation, issuance sequence, and grant digest. Each value is one keyed
`ObserverGrantLedgerHead` in pending-boundary-installation, live, or terminal state.
Same-lineage renewal replaces the value at the byte-identical registry key and
increments issuance sequence in that value; it does not allocate a lineage or retain
G0 and G1 as server-map siblings. Only new-lineage attach inserts a new registry key.
The registry persists next issuance sequence, consumed predecessor/fence audit, and
lineage tombstones. Eviction, compaction, or restart cannot reset sequence or reuse a
lineage.
`InstalledObserverAuthorizationStateSelector` is the sole server currentness root;
`InstalledObserverGrantRegistrySelector` has no effective authority.
The outer head also binds the coordinator clock policy and never-reused
`coordinator_clock_incarnation`. Every clock-dependent pending or live keyed head binds
its coordinator request/close/not-after values in that incarnation. Every boundary plan
also binds each boundary's distinct clock incarnation and authenticated no-extension
mapping. Numeric values from different clock incarnations are never
compared. Exact clock restore preserves the installed deadlines. Otherwise the server
uses exact outer transition `OBSERVER_AUTHORIZATION_CLOCK_RESTART` and first constructs a receipt-free
`ObserverAuthorizationClockRestartTransitionFact` over the exact installed outer and
registry heads, expected selector, old and fresh clock incarnations, and one closed
member branch per affected grant. `MAP_COORDINATOR_DEADLINES_NO_LATER` binds the
authenticated old/new reference, source/target horizons, rates, rounding,
qualification, source receipt, and complete restart ancestry for every clock-dependent
pending/live deadline and terminal-but-closure-pending plan deadline.
`TERMINALIZE_OR_FENCE_AFFECTED_GRANT` atomically installs a nonreleasing result and
retires the generation for an affected live grant when continuity is absent.
Raw tick copy or comparison across incarnations is forbidden. A mapped live entry changes only its clock mapping,
no-later not-after, and restart-fact binding. Any unmapped live entry retires the session
generation. The outer, registry, and bounded affected keyed successors bind that fact;
the generic outer commit binds those successors and the next selector version; the
outer selector binds that generic commit; the specialized registry commit and
`ObserverAuthorizationClockRestartCommitReceipt` follow. The same winning
transaction persists one crash-complete `ObserverGrantTerminalTransitionReceipt` per
terminalized key. The receipt remains
external to the heads and plans. A missing, partial, extending, cross-boundary, or
ambiguous mapping terminalizes affected pending grants and retires every affected live
generation. Ordinary grant operations still change exactly one keyed entry; this
restart changes only the complete bounded clock-dependent set.
Activation and timer terminalization compare the current outer clock incarnation in
that same selector CAS. Server activation must be strictly before both its
installation close and the candidate grant not-after; renewal begin must be strictly
before the predecessor grant not-after. Server expiry uses at-or-after;
deadline equality is expired.
`OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION` atomically installs the
initial descriptor, outer version-one head, and empty registry version one. It emits
the outer and subordinate receipts; the first pending key is added only by attach.
The exact exceptional outer transition set is
`OBSERVER_AUTHORIZATION_STATE_GENESIS_FROM_SESSION_CREATION`,
`OBSERVER_AUTHORIZATION_CLOCK_RESTART`,
`REPLACE_OBSERVER_DESCRIPTOR_OR_PRIVACY`,
`APPLY_OBSERVER_SECURITY_REBOUND_OR_REVOCATION_CUT`, and
`RETIRE_OBSERVER_SESSION_GENERATION`. Unknown, default, inferred, and legacy aliases
reject before successor construction.
The closed server transition set is
`GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED`, `ATTACH_NEW_GRANT_LINEAGE`,
`BEGIN_GRANT_RENEWAL`, `ACTIVATE_PENDING_GRANT`, `TERMINATE_GRANT`, and
`REATTACH_FROM_TERMINAL_GRANT`. Each compare-and-swaps the outer selector, changes
exactly one keyed entry with `ObserverAuthorizationStateCommitReceipt` plus
`ObserverGrantRegistryCommitReceipt`, and preserves unrelated entries byte-identical.
Clock, descriptor, privacy, security, and session cuts are bounded multi-entry
exceptions. `ObserverDescriptorPrivacyReplacementTransitionFact`,
`ObserverSecurityRevocationCutTransitionFact`, and
`ObserverSessionRetirementTransitionFact` are immutable receipt-free pre-CAS facts.
Each binds a preallocated operation ID, exact prior outer/registry/currentness state,
the complete affected key set, and one exact keyed terminal subfact per affected
grant. Its candidate outer, registry, and keyed successors bind the fact and operation
ID. `AuthorityTransitionOperationCommitment` then binds the complete candidate
successor; the generic outer commit, installed selector, specialized registry commit,
and one crash-complete terminal receipt per affected key follow in that order.
Every unaffected entry and tombstone remains byte-identical. Descriptor replacement
cannot substitute security, clock, or session state; a security cut binds the exact
installed security-authority transition and conditionally compares its selector in
the same local transaction; session retirement installs no live, pending, or
reattachable authority. Capacity exhaustion or an unenumerated affected key forces
session retirement. Distributed boundary acknowledgement and confidentiality closure
remain later work. Descriptor-before-operation,
operation-before-descriptor, and same-predecessor races have exactly one installed
order. No separate-store check can substitute.
Server activation emits `ObserverGrantRegistryActivationEntryProof` for the exact
keyed LIVE entry in the then-installed outer and registry heads. Historical or sibling
map entries reject while constructing that proof. The proof is activation provenance,
not present cross-store currentness. A later boundary release must compare its own
locally installed activation, terminal/revocation, security, and deadline state; the
activation proof cannot substitute for that local currentness compare.
`GRANT_REGISTRY_GENESIS_FROM_UNINITIALIZED` installs the empty subordinate registry
inside outer session genesis.
`ATTACH_NEW_GRANT_LINEAGE` adds a never-used key.
Before `BEGIN_GRANT_RENEWAL`, the server constructs receipt-free
`ObserverGrantRenewalTransitionFact`. It binds a preallocated operation ID, exact
prior outer, registry, and live G0 heads, expected versions and currentness, the
candidate G1 plan, grant, full key, and canonical G0-not-after deadline-intent root.
A plan or grant cannot substitute for this fact. The pending G1 successor binds the
fact. `BEGIN_GRANT_RENEWAL` consumes exact live G0 and installs pending G1 by replacing
the value at the same byte-identical `ObserverGrantRegistryKey`; the server registry
does not retain G0 and G1 as siblings. G1 advances issuance without a fresh lineage. Its post-CAS
`ObserverGrantRenewalPredecessorFenceReceipt` binds the fact, operation ID, G0, the
installed G1 keyed, registry, and outer heads, the sole selector, and generic plus
specialized commits.
It is not a G0 server terminal receipt. Every old boundary installs
`TERMINATE_BOUNDARY_GRANT` with `SERVER_RENEWAL_FENCE` bound to that receipt.
The authority completes G0 distributed authorization closure before each distinct,
never-used full G1 boundary key can prepare. Boundary G0 remains a terminal or
transport-quiescent sibling because its full key has the old issuance and digest;
it is never overwritten. The cross-key predecessor relation must recompute from that
authenticated G0 entry and its terminal/closure ancestry; caller-supplied source-grant
or overlap digests prove nothing. A failed preparation cannot restore server G0.
The predecessor must have valid PENDING -> LIVE -> TERMINAL and optional QUIESCENT
ancestry; a fixture cannot insert a terminal/quiescent sibling directly.
`ACTIVATE_PENDING_GRANT` covers initial attach, new-lineage attach, renewal, and
reattach because its exact pending head, plan, and commitment bind the originating
operation; it never infers origin from grant fields. Failed preparation terminates.
`TERMINATE_GRANT` first constructs a receipt-free
`ObserverGrantTerminalTransitionFact` for one exact `VOLUNTARY_DETACH`, `EXPIRED`,
`REVOKED`, `SESSION_RETIRED`, `DESCRIPTOR_REPLACED`, `SECURITY_REBOUND`,
`CAPACITY_RETIRED`, `AUTHORITY_CLOCK_DISCONTINUITY`, or
`BOUNDARY_INSTALLATION_FAILED` reason. Installation failure binds a complete
`ObserverGrantBoundaryInstallationFailureMemberEvidence` set with one exact closed
missing, late, unenumerated, identity/domain substitution, unavailable mapping,
rejection, or noncanonical-set subreason per member. The terminal keyed successor binds
the fact; the registry successor binds that keyed head. The generic outer commit
binds the successors and next selector version; the selector binds that commit; the
specialized registry commit and `ObserverGrantTerminalTransitionReceipt` follow and
remain external to both heads.
One deterministic `ObserverGrantReattachmentPolicyResult`, uniquely keyed by that
terminal receipt and installed policy-rule digest, binds all policy inputs, evaluator
digest, and exactly `REATTACH_ALLOWED` or `REATTACH_FORBIDDEN`. The validator
recomputes it. The same winning terminal transaction persists its signed bytes after
the logical terminal receipt; the terminal head excludes it, and a second or
conflicting result rejects. This is a closed two-value result: aliases such as
`REATTACH_REQUIRES_NEW_GRANT_KEY` reject.
`REATTACH_FROM_TERMINAL_GRANT` alone can
consume an exact terminal head plus `REATTACH_ALLOWED`; it advances issuance sequence
and creates fresh challenge, grant/incarnation, nonce, deadline, and scope.
`REATTACH_FORBIDDEN` cannot be bypassed with a new key.
Renewal, reattach, and activation after descriptor, privacy, security, or principal
replacement, the new commitment consumes the complete prior
`ObserverGrantDistributedAuthorizationClosureReceipt`. It binds one closed
`SERVER_TERMINAL_DECISION` or `SERVER_RENEWAL_PREDECESSOR_FENCE`; the renewal branch
consumes the exact predecessor-fence receipt, not a nonexistent G0 terminal receipt.
Every preserved old boundary
first installs `TERMINATE_BOUNDARY_GRANT`, contributes `TERMINAL_ACKED`, and only then
can install the new `PREPARE_BOUNDARY_GRANT` from its terminal predecessor. A removed,
substituted, or policy-changed boundary contributes either `TERMINAL_ACKED` or proved
`DEADLINE_ELAPSED_UNACKNOWLEDGED`. A partitioned old boundary cannot silently overlap
with a replacement boundary.
Before a grant is constructed, the server fixes one complete
`ObserverGrantBoundaryInstallationPlan`: all required descriptor-and-scope
boundaries, original attach/renew operation, server request time, exclusive
server installation-close/grant-not-after, reviewed
`maximum_boundary_revocation_lag`, positive reviewed
`minimum_boundary_activation_budget`, and shared-clock or authenticated no-extension
mapping per boundary. In one coordinator clock incarnation, original server request
time must be strictly before installation close; equality, inversion, or a cross-incarnation
comparison rejects. Checked arithmetic then requires server installation close
plus that budget to be no later than both grant not-after and original request time
plus the revocation lag. Addition, ceiling, and rate-denominator operations are checked;
nonpositive denominators or overflow reject. Each clock mapping binds either a calibrated
reference instant, distinct coordinator-source and boundary-target applicability
horizons, and correlated offset/rate/rounding bounds, or independently qualified exact
images that bind the same horizons, correlation, qualification, and source receipt.
A calibration source receipt must be no later than the plan request time. Each instant
comparison requires identical clock-domain, policy, and incarnation tags. A duration
horizon uses tagged start/end anchors; a free scalar duration cannot define it.
Every mapped source instant and duration endpoint stays inside the source horizon;
every derived image and checked target result stays inside the target horizon. The
model never orders a coordinator instant against a boundary instant.
Each member is one indivisible principal, never-reused instance, literal live-route or
history-provider domain, deadline policy, and security state. That identity threads
unchanged through plan, preparation, local root, reservation, commitment, and outbox.
Each member binds distinct exclusive
`boundary_prepare_close`, non-authorizing feasibility fields
`boundary_latest_server_activation_at` and
`boundary_minimum_activation_budget_upper`, and `boundary_release_not_after`. The prepare
close is the conservative lower/no-later absolute image of server installation close
and is used only by PREPARE. The latest-activation field is the conservative upper/later
absolute image after bounded offset and mapping uncertainty. The distinct budget field is the budget's
conservative upper boundary-clock duration image
that includes the fastest admissible clock rate, rate uncertainty, and rounding.
Checked arithmetic requires latest activation plus that exact upper-duration field to be no
later than release not-after; it also verifies prepare close <= latest activation <
release not-after. Neither feasibility field is a commit deadline or
authority proof. The release not-after is no later than mapped
grant not-after and mapped original request time plus the lag, after complete positive
uncertainty. Unknown offset sign, rate, rounding, overflow, zero budget, or an inverted
window rejects before any plan-dependent grant or boundary key allocation. These
checks prove nominal time feasibility, not network delivery or availability. The plan
binds the stable registry key and proposed issuance context, but excludes the later
grant digest, full boundary key, successors, commitments, and receipts. The sealed
grant and installed nonreleasing pending chain bind the plan, derive the full boundary
key, and make its candidate identity available to preparation. Before the mapped
prepare close, every enumerated boundary constructs one receipt-free
`TrustedDeliveryBoundaryGrantPreparationFact`. It binds the grant/plan, exact
principal and never-reused boundary instance, security state, literal route/provider
domain, deadline policy, original request constraint, local clock, both deadlines,
both feasibility fields `boundary_latest_server_activation_at` and
`boundary_minimum_activation_budget_upper`,
installed server pending heads, and exact prior installed outer/map heads. It binds
typed absence of the derived never-used full candidate key. Renewal, reattach, or replacement also
binds the distinct cross-key terminal or transport-quiescent predecessor sibling and
whole prior closure. It excludes the local successor, selector, generic
commit, enforcement receipt, and every server-live object. The local candidate
entry successor binds the fact in `PREPARED_BOUNDARY_GRANT`; the map successor binds
that entry, and the outer successor binds the map.
`TrustedDeliveryReleaseStateCommitReceipt` binds the outer successor, deadline
evaluation root, and next selector version. `InstalledTrustedDeliveryReleaseSelector`
binds that generic commit. `TrustedDeliveryBoundaryGrantMapCommitReceipt` then binds
the selector and generic commit. Only after that chain does
`TrustedDeliveryBoundaryGrantEnforcementReceipt` bind the fact, local prior/installed
outer/map/entry heads, selector, generic commit, evaluation root, and the exact
server pending heads. Every boundary-local fact and receipt signer principal and key
must equal the plan member and its installed security state; a server authority key
cannot mint local proof. The server's complete prepared set consumes those exact
local-installed receipts. PREPARE must commit strictly before
`boundary_prepare_close`. Preparation is a durable blocking two-phase promise. Before
`boundary_release_not_after`, only the authenticated server activation or terminal decision lets a
boundary leave prepared state; partition, timeout, or restart cannot unilaterally
abort or reuse its slot. A complete prepared set creates one receipt-free
`ObserverGrantBoundaryInstallationCommitment`. It binds the preallocated activation
operation ID and canonical receipt-free activation deadline-intent root. The live keyed successor binds the
commitment; the registry successor binds that keyed head; the outer
`ObserverAuthorizationStateHead` successor binds the registry successor. The generic
outer commit binds that complete chain, evaluation root, and next selector version.
The outer selector binds the generic commit. The specialized registry commit and then
`ObserverGrantBoundaryInstallationSetReceipt`. No independent registry selector or
CAS exists, and every successor excludes the later receipts.
The server `LIVE` transition is the durable coordinator decision. Each independent
boundary constructs receipt-free `TrustedDeliveryBoundaryGrantActivationFact` from
the exact prepared predecessor, server set receipt, activation-entry proof, both
boundary deadlines, security-currentness condition, and operation. The LIVE successor binds the
fact and receipt-free deadline-intent root. The generic commit then binds the exact
post-linearization evaluation root. The installed selector binds that generic commit;
only then does
`TrustedDeliveryBoundaryGrantActivationReceipt` bind the fact, prior/installed heads,
selector, generic commit, and evaluation root. A delayed
authentic server decision can install only from that exact PREPARED predecessor,
strictly before `boundary_release_not_after`, and when no higher local
terminal/security decision won. The
server receipt and activation-entry proof are inputs to local installation; neither
independently enables release. No
prepared subset authorizes release. Missing, late, unmapped, or partial preparation
terminalizes the grant; each prepared boundary remains blocked and nonreleasing until
it installs the authenticated terminal decision or reaches
`boundary_release_not_after`. This
claims fail-closed confidentiality, not cross-store atomic commit or simultaneous
availability. Delayed contact never starts a fresh lifetime.
Before each deadline-sensitive server, boundary, observer-installation, or evidence-
admission CAS, the receipt-free `AuthorizationDeadlineConditionIntent` binds exact
operation, predecessor, `expected_prior_selector_version`, clock incarnation,
exclusive deadline, closed purpose/kind, and timing-proof policy. The manager policy
binds an installed integrated-guarantee identity and zero bound. The bound policy
binds a positive bound, qualification-source digest, and enforcement policy. Every
intent in one set uses the same tagged profile and proof-instance identity. An opaque
caller hash cannot qualify either branch. That expected prior
version is its only selector-version field. The intent contains no installed
successor digest, installed selector version, authorization-linearization instant,
sample, actual enforcement/abort/recheck result, commit, or receipt. The transition fact and candidate successor bind
the canonical receipt-free `AuthorizationDeadlineConditionIntentSetRoot`. The closed
deadline kinds are
`SERVER_GRANT_INSTALLATION_CLOSE`, `SERVER_GRANT_NOT_AFTER`,
`BOUNDARY_GRANT_PREPARATION_CLOSE`, `BOUNDARY_GRANT_RELEASE_NOT_AFTER`,
`OBSERVER_GRANT_RESPONSE_CLOSE`, and `OBSERVER_GRANT_ADMISSION_NOT_AFTER`. Server
activation checks both server kinds; renewal begin checks the G0
not-after and server expiry uses that kind with the at-or-after comparator. PREPARE
checks both boundary kinds; delayed activation, reservation, and release select boundary
release not-after; local expiry and expiry-only closure use the same release kind with
the at-or-after comparator. Under the store lock, the transaction verifies the exact
prior selector and finalizes the candidate successor. It then constructs one
receipt-free `AuthorityTransitionOperationCommitment` over the preallocated operation
ID, exact prior/currentness conditions, transition fact or content root, complete
candidate successor, and intent root. The successor binds the operation ID, fact, and
intent root, but never its own digest or the later operation-commitment digest. The
store then obtains one store-owned timing sample and creates one
`CommitTimeDeadlineCondition` per intent. Each evaluation
binds the exact intent digest, installed successor digest, installed selector version,
store, transaction, sample, deadline, and result. The canonical
`CommitTimeDeadlineEvaluationSetRoot` binds the typed operation-commitment digest and
proves an exact digest bijection and one common store, transaction, sample, and count.
Positional matching is forbidden.
The only timing tags are `TRANSACTION_MANAGER_LINEARIZATION` and
`QUALIFIED_COMPLETION_BOUND`. The first uses the store-assigned authorization-
linearization instant and a zero bound. The second binds a qualification digest, a
positive enforced hard bound, and success-within-bound or abort evidence. It checks
`sample + bound < exclusive_deadline`; exceedance aborts and installs no selector.
All evaluations use the same tagged profile/proof instance, and store-produced actual
result. An estimate, opaque caller digest, caller sample, pre-CAS sample, or forced
deadline-crossing stall rejects.
The exact content DAG is intent, fact, candidate successor, operation commitment,
evaluation set, generic commit, installed selector, then specialized receipt. The
generic commit binds the operation commitment, evaluation root, and next selector
version but no selector digest. The selector binds that generic commit.
The specialized receipt binds the selector, generic commit, and evaluation root.
The successor never binds its future evaluation. Missing, extra, conflicting, or
intent-mismatched evaluation and every reverse edge or content cycle reject.
Equality rejects authorization and permits expiry.
Every logically post-CAS specialized server or boundary receipt is crash-complete.
The winning durable transaction persists the installed head, generic commit, and
complete signed specialized receipt bytes together. Reconstruction is allowed only
when exact signature bytes, or formally qualified deterministic signing material and
capability that remain authorized, persist with the actual trusted commit-time sample,
condition inputs/result, and every canonical input. A key ID alone is insufficient
after rotation, disablement, or destruction. Recovery cannot choose a new time, key,
identity, signature, or lifetime; ambiguity blocks or terminalizes the operation.
Before any bytes leave, the boundary bounds the complete live payload or complete
history result and uses exact transition `RESERVE_TRUSTED_DELIVERY_RELEASE` to install
`TrustedDeliveryReleaseReservation` over exact bytes,
full grant key and locally installed live entry, activation-entry proof, set receipt,
requester, security/revocation state, boundary clock, both deadlines, and output slot.
The reservation content binds only its receipt-free release-not-after intent root, not
a later evaluation or result. Candidate keyed, map, and outer successors bind the
reservation and intent root. The operation commitment binds those successors; the
post-linearization evaluation root binds that operation commitment; generic commit,
selector, and specialized map receipt then follow in one serialized durable
transaction. Its CAS must commit strictly before `boundary_release_not_after`.
`TrustedDeliveryReleaseStateHead` is the boundary's sole top-level composite root.
It binds shared security, clock, global output-slot allocation, and grant-key-partitioned
outbox, drain, disposition, and tombstone state plus subordinate bounded
`TrustedDeliveryBoundaryGrantMapHead`. The root persists monotonic global release and
output-slot allocators plus per-item attempt sequences and tombstones. Retry, sibling
activity, or overflow cannot reuse a hard-coded sequence or slot value such as one.
`TrustedDeliveryBoundaryGrantKey` is the full
session, generation, registry incarnation, exact requester/lineage registry key,
issuance sequence, and grant digest. Each value is one versioned
`TrustedDeliveryBoundaryGrantStateHead` in exactly `PREPARED_BOUNDARY_GRANT`,
`LIVE_BOUNDARY_GRANT`, `TERMINAL_BOUNDARY_GRANT`, or
`TRANSPORT_QUIESCENT_BOUNDARY_GRANT`. It owns bounded reservations and pre-release
commitments but has no selector. `RELEASE_STATE_GENESIS_FROM_UNINITIALIZED` installs
an empty map; absence is map absence, never a permissive `NO_BOUNDARY_GRANT` entry.
`PREPARE_BOUNDARY_GRANT` inserts a never-used version-one key.
`ACTIVATE_PREPARED_BOUNDARY_GRANT`, `TERMINATE_BOUNDARY_GRANT`, and
`MARK_BOUNDARY_GRANT_TRANSPORT_QUIESCENT` alone install their matching successor
phases. Each entry transition changes one key, preserves every sibling and unrelated
shared item, and emits generic outer plus specialized map commits. Only LIVE can
reserve or release. Shared drain-only transitions preserve the complete map and emit
only the generic outer commit.
The exact remaining release-state kinds are `RESERVE_TRUSTED_DELIVERY_RELEASE`,
`COMMIT_TRUSTED_DELIVERY_RELEASE`, `START_EXTERNAL_TRANSPORT_DRAIN`,
`RESOLVE_EXTERNAL_TRANSPORT_DRAIN`, and `APPLY_BOUNDARY_CLOCK_RESTART`. Unknown,
default, inferred, hidden-internal, and legacy aliases reject.
Each local terminal transition first constructs receipt-free
`TrustedDeliveryBoundaryTerminalTransitionFact` with one closed `SERVER_TERMINAL`,
`SERVER_RENEWAL_FENCE`, `LOCAL_FIXED_DEADLINE_EXPIRED`,
`LOCAL_SECURITY_REVOKED`, `LOCAL_CLOCK_DISCONTINUITY`, or `BOUNDARY_RETIRED` cause.
It binds the prior PREPARED/LIVE entry, both deadlines, local condition, complete
unreleased cancel/tombstone set, and complete retained released-item/active-drain set.
The terminal entry binds only its keyed fact; the map and outer successors bind that
entry. Only after the selector CAS does
`TrustedDeliveryBoundaryTerminalInstallationReceipt` bind the fact, prior/installed
outer/map/entry heads, selector, generic/map commits, retained inventory, and
applicable deadline condition. Shared security, descriptor, or retirement cuts first
construct receipt-free `TrustedDeliveryBoundaryBulkTerminalTransitionFact` containing
one keyed terminal subfact per affected key. Each entry binds only its subfact; the
map/outer heads bind the complete envelope. The winning multi-key transaction persists
one crash-complete terminal-installation receipt per terminalized key. Clock restart
uses its distinct bridge envelope with the same per-key subfact and receipt discipline.
No singular common fact can stand in for keyed facts. No new item can become
release-authorized after its local cut, but retained items still drain unchanged.
`SERVER_TERMINAL` and `SERVER_RENEWAL_FENCE` may install immediately; only
`LOCAL_FIXED_DEADLINE_EXPIRED` requires an at-or-after release-not-after result.
Terminal-first makes a competing activation, reservation, or release lose the shared
selector CAS. Activation or release first orders terminalization later and preserves
every already committed outbox item.
`COMMIT_TRUSTED_DELIVERY_RELEASE` constructs exact bytes, the installed reservation,
and a receipt-free
`TrustedDeliveryReleaseOutboxCommitment` first. It binds the full grant key,
preallocated stable outbox item/idempotency identities and never-reused bounded
attempt namespace plus a fresh receipt-free release-not-after intent root. It excludes
entry/map/outer successors, authority operation commitment, evaluation, selector,
receipts, complete bytes, and full item. Candidate entry, map, and outer successors
bind only that commitment and intent root. The authority operation commitment binds
the candidate successors; the evaluation root binds that operation commitment; generic
outer commit and selector follow. The
`TrustedDeliveryReleaseReceipt` binds the commitment, prior/installed
outer/map/entry heads, selector, generic and map commits, evaluation root, slot,
clock, enforcement, and grant proof. The complete
`TrustedDeliveryReleaseOutbox` item binds its grant key,
commitment, specialized receipt, stable identities, and immutable bytes. One
serialized durable transaction persists all successors, commits, the signed release
receipt, and exact complete item. The complete item remains external to every
candidate successor so it cannot create a receipt/head cycle. The
outbox ownership transfer is the confidentiality-release point. A prior terminal/
revocation transition exposes no bytes; a later one sees an immutable released item.
History is all-or-none and never exposes a canceled, faulted, or crashed prefix.
The same release-state head owns bounded active external-drain attempts and immutable
disposition/key tombstones. Before send, the worker constructs receipt-free
`TrustedDeliveryExternalTransportDrainFact` over the exact retained outbox item and
bytes, full grant key, stable release/idempotency key, transport instance, and bounded
attempt identity. From LIVE or TERMINAL only,
`START_EXTERNAL_TRANSPORT_DRAIN` compare-and-swaps the outer head to install the active
attempt before external send while preserving the map and every entry. After send,
`TrustedDeliveryExternalTransportDisposition` binds the exact fact, item, key,
attempt, transport evidence, and one closed `DELIVERED`, `REJECTED`, or
`AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT` result.
`RESOLVE_EXTERNAL_TRANSPORT_DRAIN` similarly preserves the map while it consumes the
active attempt and atomically installs the disposition and key tombstone. Delivered
requires an authenticated acceptance
receipt; rejected requires definitive authenticated no-acceptance evidence; ambiguous
forbids either definitive result. A crash after send but before resolution recovers as
ambiguous. Active and ambiguous attempts cannot be evicted or have their stable key
reassigned. Retry uses the same item and key only when the transport proves same-key
idempotency; otherwise ambiguity remains terminal. LIVE or TERMINAL permits start or
resolution only for an exact retained already-released item; a transport-quiescent
entry permanently forbids another attempt. This
drain protocol makes no external exactly-once claim and grants no release authority.
The model keeps three cuts separate. The outbox CAS is one-item release authorization.
`ObserverGrantDistributedAuthorizationClosureReceipt` binds exact
`ObserverGrantAuthorizationClosureDecision` as `SERVER_TERMINAL_DECISION` or
`SERVER_RENEWAL_PREDECESSOR_FENCE` and proves that every original planned boundary is
terminal or its `boundary_release_not_after` elapsed. Each member is exactly
`TERMINAL_ACKED` or
`DEADLINE_ELAPSED_UNACKNOWLEDGED`. An acknowledged member binds its terminal receipt
and exact retained-item identity/count/root inventory. An unacknowledged expired member
must mark that inventory `UNKNOWN`; an optional policy upper bound remains non-exact.
Expiry-only evidence proves that the plan's original effective coordinator-source
expiry instant elapsed, then uses its already qualified boundary-clock lower image to
reach `boundary_release_not_after`. That source instant is inside the plan's
coordinator-source horizon; the lower image and deadline are inside its boundary-target
horizon. The proof never extrapolates the mapping to a later current coordinator
sample. Clock-incarnation change needs exact restart-commit ancestry that maps the
original source expiry no later and proves it elapsed. The clock must advance across
suspend. Missing ancestry forces terminal-ack-only closure. The
coordinator cannot infer zero items or an exact root for a partitioned boundary.
Authorization closure can therefore pass with `UNKNOWN`, but it proves neither arrival
cessation nor transport quiescence.
A boundary first constructs receipt-free
`TrustedDeliveryBoundaryTransportQuiescenceFact` from exact terminal entry, outer/map
heads, item inventory, dispositions/tombstones, no-retry state, and authenticated
transport no-pending proof. `MARK_BOUNDARY_GRANT_TRANSPORT_QUIESCENT` changes only that
entry through the outer selector. Generic/map commits precede the post-CAS
`TrustedDeliveryBoundaryTransportQuiescenceReceipt`, which binds the fact,
prior/installed outer/map/entry heads, selector, commits, and exact inventory. A
concurrent drain start or stale fact loses. A tombstone and no-retry state prove only
closure of local resend authority. Every started send also needs authenticated
transport-specific finality or cancellation evidence that it cannot still deliver;
an ambiguous send without that proof blocks quiescence.
`ObserverGrantTransportQuiescenceReceipt` binds the distributed closure and complete
boundary-quiescence set. Unknown/lost boundary state blocks it, possibly forever.
`ObserverDetachCompletionResult` is exactly `DETACH_AUTHORIZATION_CLOSED` or
`DETACH_TRANSPORT_QUIESCENT`; the first binds distributed closure, while the second
also binds grant transport quiescence. Neither proves receiver admission or physical
confidentiality closure, and a generic success boolean is invalid.
An exact clock restore preserves the existing boundary state without a
fabricated bridge. Every bounded no-extension conversion requires an authenticated
`TrustedDeliveryBoundaryClockRestartBridge` and a post-CAS
`TrustedDeliveryBoundaryClockRestartCommitReceipt`. The bridge preserves the exact
boundary principal, same never-reused instance, and literal delivery domain; it
cannot transfer a grant to another boundary instance. It binds prior installed
outer/map heads, old/fresh clock incarnations, policy and uncertainty, and the complete
bounded affected PREPARED/LIVE key set. Each member selects exactly one no-later
deadline mapping or `LOCAL_CLOCK_DISCONTINUITY` terminal branch. One outer-selector CAS
installs the complete mapped/terminal entry set while every unaffected entry and
outbox/drain partition remains byte-identical. Generic outer and multi-entry map
commits precede the restart receipt, and the same winning transaction persists one
crash-complete terminal receipt per terminalized key. Partial per-entry conversion,
sequential old/new-clock mutation, or missing receipt rejects. A new boundary instance
requires old-instance closure followed by fresh preparation and activation. Otherwise
the boundary retires the grant and generation and creates no new reservation, release
commitment, or outbox item. An exact complete outbox item committed before retirement is already an immutable
released obligation; it may drain only with its original bytes and idempotency context.
A crash after the outbox CAS and before drain recovers that exact installed item and
drains it unchanged. Restart never rebases the old deadline or creates a fresh
request-receipt time.
Release requires current verifier time strictly before the local deadline. Deadline
equality is expired. Old request, head, receipt, and clock-incarnation replay reject.
`ObserverAdmissionStateHead` is the observer's sole composite local head. Its closed
grant-state branch is `PENDING_FIRST_ATTACH`, `LIVE`, `LIVE_RENEW_PENDING`,
`DETACH_PENDING`, or `TERMINAL`. Only `LIVE` and the exact unchanged predecessor
inside `LIVE_RENEW_PENDING` can admit. Every other branch structurally forbids
current-grant authority. The head binds a never-reused state incarnation/version,
bounded request operations, attempts and terminal outcomes, the receiver-evidence-lineage
registry, and a bounded map of ADR-005 per-stream frame-admission heads.
`OBSERVER_ADMISSION_STATE_GENESIS_FROM_UNINITIALIZED` consumes one parent-created
never-used selector and atomically installs the empty pending admission root.
Before the first challenge-issuance send, the observer durably PREPAREs one exact
request operation, stable key, intent and target-exclusivity proof. After it verifies
the protected challenge and before the request send, `ObserverGrantRequestAttempt`
durably binds a never-reused attempt ID, attach/renew/reattach kind, target and
predecessor, the prepared operation, fresh challenge, local
clock/request-start time, and distinct exclusive
`observer_grant_response_close` and candidate
`observer_grant_admission_not_after`. Detach first installs
`DETACH_PENDING` and immediately fences queued and future frame admission.
One closed `ObserverGrantRequestOperationResolution` finalizes the exact operation
as prepared-intent resolution without an attempt, attempt resolution without
installation, or installed response. Retry and restart query that installed outcome;
they cannot re-date or reconstruct the challenge from a response. Response
installation uses the `OBSERVER_GRANT_RESPONSE_CLOSE` condition and must commit
strictly before the original response close. It preserves the candidate admission
not-after without redating it.
A live branch binds the challenge, request start/install, exact admission not-after and clock, exact
locally installed live grant, server activation-entry proof, set receipt, descriptor,
and current revocation/security state. Frame/history admission uses
`OBSERVER_GRANT_ADMISSION_NOT_AFTER` and commits strictly before that bound; local
expiry uses the same kind at or after equality. During renewal, unchanged G0 admission
continues only under G0's original admission not-after; candidate G1 uses its attempt's
distinct response close and becomes admissible only after installed resolution.
`InstalledObserverAdmissionStateSelector` serializes grant, revocation, descriptor,
security, clock, request-attempt, resolution, and frame transitions. Each emits
`ObserverAdmissionStateCommitReceipt`; a grant install also emits
`ObserverGrantInstallationReceipt` over the same prior/installed composite heads.
For an ADR-004 observer, the generic ADR-005 frame-admission heads and
`ReceiverEvidenceLineageRegistryHead` are subordinate to this composite root.
`InstalledFrameAdmissionSelector` and
`InstalledReceiverEvidenceLineageRegistrySelector` apply only when no owning role
defines a stricter root. They cannot independently authorize observer evidence.
Observer restart continuation requires a separate no-extension
`ObserverGrantClockRestartBridge` and post-CAS
`ObserverGrantClockRestartCommitReceipt`. Missing exact state or conversion proof
expires the local grant and requires reattachment. Server and observer receipts and
numeric clocks cannot substitute for one another.
Canonical descriptor/grant content is acyclic. The stable descriptor excludes
revocation epoch; the grant, current revocation store, and external enforcement/
admission receipts bind revocation churn. Renewal can reuse a descriptor only while
every descriptor-bound topology/schema/privacy/session/security-state field is
unchanged.
Every history release also carries exact generic `ProviderHistoryProvenance`: trusted
provider, declaration/position, original frame/content, the provider's live
frame-admission receipt and receiver-evidence lineage, its retirement anchor, and
current retained ancestry or terminal-checkpoint membership. A projected history
delivery additionally carries the exact receiver-independent
`TrustedProjectionRecord`. Its protected projector envelope binds the unchanged
original identity, policy, transform, projected bytes and declaration, and intended
audience. Only after local admission does the observer create
`TrustedProjectionProvenance` from that record digest, its own principal/evidence
lineage, and the exact projected-frame admission receipt. Both forms prove only the
projected value.
A current query signature, post-retirement publisher signature, observer genesis,
wrong provider/lineage, or missing retained proof cannot authorize after-the-fact
backfill.
The set also includes the optional body-authority provenance reference type; exact
Galadriel `assessor_incarnation_id`/`assessment_sequence`, `AssessmentScope`,
`GaladrielAssessmentBindingIdentity`,
`GaladrielReleaseSuiteIdentity`, `GaladrielLifecycleReceiptIdentity`,
`GaladrielLifecycleAssessmentVectorIdentity`, `GaladrielLifecycleOutcomeEvidence`,
`GaladrielLifecycleAssessmentEvidence`, `GaladrielSealedDefaultReportEvidence`,
`GaladrielLifecycleLaneAuthorityState`, complete canonical
`GaladrielLifecycleStateSnapshot`,
outer `lifecycle_state_version`,
`GaladrielLifecycleLineageHead`/selector/commit receipt,
`GaladrielLifecycleBoundaryCommitReceipt`,
`GaladrielLifecycleAuthorizationSpanTransition` and commit receipt,
`GaladrielLifecycleCurrentSelectorAttestation`,
`GaladrielLifecycleCompactionBridge`,
`GaladrielAssessmentPublicationCandidateFact`,
closed `PENDING_RECORD_INSTALL`, `RECORD_INSTALLED`, and
`CANCELED_BEFORE_RECORD_INSTALL` candidate states,
`GaladrielAssessmentPublicationRecord`,
subordinate `GaladrielAssessmentHandoffStateHead` and commit receipt, exact
publication reservation and pre-finalize cancellation receipt,
`GaladrielAssessmentReleaseOutbox`, receipt-free
`GaladrielAssessmentReleaseOutboxCommitment`, complete
`GaladrielAssessmentReleaseOutboxItem`, publication release receipt and closed queue
resolution,
`ProtectedAttachmentReference`, `GaladrielNcpSourceAuthorityBinding`,
`GaladrielAssessmentVectorAggregationRule` and evidence, ordered-report, and
NCP adapter-mapping references; Haldir `AssessmentHandling`, `PermissionEffect`,
receiver composite state, single-flight, authority-owned ingress reservation fact,
stamp/profile
selection, evaluation result, mandatory evaluation barrier and commit receipt,
terminal evaluation finalization, permission-preserving head proof, intent-ingress
state/source-admission receipt, policy decision and specialized commit receipt,
closed policy-allow or authenticated-fail-safe publication origin, commander
composite state, two-clock command publication preflight/reservation/fence,
`HaldirPolicyReleaseOutbox`, receipt-free
`HaldirPolicyReleaseOutboxCommitment`, complete
`HaldirPolicyReleaseOutboxItem`, release/
release/resolution, feedback/history, and ingress/source-clock evidence; and the
installed current `HaldirPolicyStateHead`. That canonical head binds monotonic state
and policy revisions, base-policy identity, active monitor profiles, deny latches,
replay and evaluation operations/results, publication reservations/fence/outbox,
and pending/finalized history, but excludes its own digest, receipt, and successor
selector. `InstalledHaldirPolicyStateSelector` is the sole policy currentness root;
`HaldirPolicyStateCommitReceipt` externally binds each successful prior-to-installed
compare-and-swap. Exact `GENESIS_FROM_UNINITIALIZED` is allowed only when that
authority-owned selector proves a never-used policy domain and fresh lineage; it
installs state version 1 with a commit receipt. After any use, absence, ambiguity,
restart, prior deny, sibling state, or reused lineage cannot reset to empty. Effects
remain disabled and permission stays deny-preserving until an authenticated monotonic
recovery. Stale/sibling heads, configuration mismatch, rollback, and
producer/assessor head selection reject.
That policy head also binds one never-reused `policy_clock_incarnation` and every
pending policy deadline in that clock. Numeric values from different incarnations are
never compared. Exact clock restore preserves the head. Otherwise exact transition
`HALDIR_POLICY_CLOCK_RESTART` first constructs receipt-free
`HaldirPolicyClockRestartTransitionFact` over the exact prior
head/selector and either a closed no-later map for every pending allow, evaluation,
reservation, and release deadline or a complete cancellation set. The successor binds
the fact; the policy selector installs it; the generic commit follows; and
`HaldirPolicyClockRestartCommitReceipt` is emitted last. Missing, partial, extending,
or ambiguous conversion cancels pending allow work while preserving base policy, deny
latches, fail-safe eligibility, and restrictive state. Deadline equality is expired.
NCP also allocates `SecurityAuthorityStateHead`,
`InstalledSecurityAuthorityStateSelector`, and
`SecurityAuthorityStateCommitReceipt`, including distinct
`authority_state_version`. External authenticated trust-root enrollment
alone can create a fresh domain/lineage selector in `UNINITIALIZED`.
`PROVISION_FROM_UNINITIALIZED` installs authority state version 1 and security epoch
1. Every later authority selector compare-and-swap increments the authority state
version by exactly one, and the commit receipt binds the prior and installed values.
This mutation version is distinct from the semantic security and revocation epochs;
neither epoch, selector version, time, nor feed version can substitute. A stale,
sibling, repeated, skipped, rolled-back, exhausted, or unreceipted authority version
rejects. Any
later absence, rollback, sibling, restart, or reuse retires the domain's sessions and
requires replacement plus external re-enrollment.
Every security-dependent local composite transition also constructs receipt-free
`LocalSecurityCurrentnessCASCondition` before its operation CAS. The condition binds
the exact operation and authority scopes, expected operation predecessor, and local
durable transaction-store identity. It also binds the security-authority domain and
lineage incarnation, authority-state version, security and revocation epochs, semantic
security-state and installed authority-head digests, installed selector incarnation,
version, and digest, plus the authenticated installed authority head, selector, and
commit source. Every security-dependent consumer successor and every generic and
specialized post-CAS receipt binds the exact condition digest. The receipts also bind
the prior and installed operation heads and the exact security state and selector that
the identified local store compared. One proven local durable transaction
conditionally compares both selectors. A
subordinate security fence with no independent selector instead participates directly
in the owning composite CAS. An omitted, stale, sibling, wrong-store, wrong-source,
remote-only, or changed condition rejects. If the implementation cannot prove a common
local transaction, that
operation surface remains closed. This ordering does not claim instantaneous CA,
revocation-feed, or fleet propagation.
`dev-loopback-insecure` can bind only an IP loopback address or an absolute
Unix-domain socket. Wildcard, unspecified, non-loopback, relative-socket, and
production-profile endpoints reject. Every API, startup diagnostic, status, and
session transcript exposes unmistakable insecure state. `production-secure` can
never negotiate or downgrade into that development profile, and the development
profile grants no production-security or remote-transport claim.
`GaladrielReleaseSuiteIdentity` fixes algorithm `sha256`, derivation domain
`galadriel-release-suite-v1`, lowercase-hex encoding, and the exact 32-byte
`ConfigDigest`. The adapter from `ReleaseSuite::identity()` is total and injective.
A human suite name is diagnostic only. Haldir's profile, admission, and disposition
bind the typed identity; same-name/different-digest and algorithm, domain, encoding,
or length substitutions reject.
`GaladrielAssessmentBindingIdentity` similarly fixes algorithm `sha256`, derivation
domain `galadriel-assessment-binding-v2`, lowercase-hex encoding, and the exact
32-byte `AssessmentDigest`. Its total injective adapter covers the exact scope, suite,
and ordered observations. It cannot depend on a later report or receipt.
`GaladrielLifecycleOutcomeEvidence` carries the exact raw `LifecycleReceipt` and
complete raw `serde_json::to_vec(&assessments)` vector attachments, typed
`GaladrielLifecycleReceiptIdentity` and
`GaladrielLifecycleAssessmentVectorIdentity`, and a complete ordered projection.
Every protected attachment uses one exact `ProtectedAttachmentReference` with
`attachment_id`, `digest`, `byte_length`, and `media_type`. The bytes are local
members of the authenticated envelope. Fetch-later paths and URIs are forbidden.
The outcome also carries the exact NCP source-authority bundle. Each evaluated
assessment carries its adapter-scope mapping receipt and complete source-capture
attachment set. Digest-only source-authority, mapping, or capture fields reject.
The identities freeze the exact SHA-256 `lifecycle-receipt/v0.9\0` and
`lifecycle-assessment/v0.9\0` preimages, big-endian widths, option tags, canonical
receipt sub-JSON, exact suite bytes, and raw-vector length prefix. Vector whitespace
and order are identity-significant. Haldir
recomputes the vector digest, verifies receipt preimage and strict raw shape, and checks
the total raw-to-projection mapping. The protected envelope authenticates the complete
attachment set and aggregate size. A receipt alone authenticates no writer or durable
retention.
`GaladrielSealedDefaultReportEvidence` is the only policy-bearing report form. Its
identity is the typed lifecycle assessment-vector identity, raw attachment digest, and
zero-based member index. The complete raw vector is mandatory. NCP invents no second
per-report digest, separate report attachment, or fake one-member inclusion proof over
the flat vector hash. Haldir reads the exact complete report at that index and never
reconstructs it from projected fields. Literal family
`galadriel_default_report_v1` and a total injective `FusedVerdict` projection use the
exact snake-case variant, bounded unique channels, and required `MagnitudeEvidence`
for `attributed_inconsistency`. The adapter receipt binds the vector/member identity
to every projected field.
Baseline `Verdict`, an unbound tuple, free label, baseline/fused collision, unknown
variant, missing or duplicate channel, omitted or substituted magnitude, and an
unsealed report are ineligible.
`GaladrielLifecycleAssessmentEvidence` is each indexed member of a closed
`EVALUATED_DEFAULT_REPORT` or `LIFECYCLE_ABSTAINED` vector. The evaluated branch binds
the sealed report, scope, binding, suite, track, fusion sequence, and history-reset
state. The abstained branch
binds only suite, track, fusion sequence, and a nonempty bounded unique canonically
ordered unavailable-modality list; it forbids report, scope, binding, and verdict.
`radiofrequency` is exact; `radio_frequency` rejects. Fused
`insufficient_evidence` remains evaluated and profile-ineligible, never abstained.
`AssessmentScope.clock_domain` is exactly `unix_utc`, `monotonic_process`,
`simulation_time`, or `tai`. The adapter is total over those four variants. It rejects
unknown or guessed deployment labels. The extension projection flattens eight
coordinates, but Galadriel runtime serde nests producer and `StreamPosition`; the
mapping is total, reversible, and coordinate-by-coordinate. The terminal sequence is
the largest observation sequence, and terminal time is the largest time at that
sequence.
`NcpCaptureAdapterMapping` records the native mapping. NCP sequence is one-based;
Galadriel sequence is checked `ncp_sequence - 1` within the exact epoch, and the
receipt retains both. NCP source `t` is publisher-local monotonic seconds. It maps to
exact process-monotonic milliseconds only when finite, nonnegative, exactly
representable, JSON-safe, and collision-free within the epoch; receiver UTC, arrival
time, rounding, truncation, and saturation cannot substitute. Galadriel
`state_generation` is local lifecycle state, never an NCP generation.
`GaladrielNcpSourceAuthorityBinding` binds the exact NCP logical session, live
`SessionRef.generation`, observer descriptor revision and digest, source declaration
digest, observer-grant authorization tuple and digest, current security-state digest,
security and revocation epochs, receiver-evidence lineage, and coordinate-mapping
receipt. Its source-authority bundle attachment contains the protected authority
objects. A producer assertion, assessor incarnation, session label, or digest-only
reference cannot substitute.
A receipt alone does not prove detector continuity. Each lane has one exact
`GaladrielLifecycleLaneAuthorityState` over its NCP authority tuple, source position,
state generation, used/retired epochs, warmup/history and ordered authorization spans.
The lineage head contains a bounded canonical lane map and one exact
`GaladrielLifecycleStateSnapshot` reference. That complete content-addressed snapshot
binds schema/encoding, implementation-contract digest, fixed config/suite, every
lane's histories/observations/recent frames/positions/generations/epochs, global
receipt anchor/tip/index/eviction, publication state, and terminal fault. It excludes
its own digest and later head/receipt.
The lineage head also binds an outer `lifecycle_state_version`: genesis is 1 and
every composite selector compare-and-swap increments it by exactly one. This includes
handoff-only candidate/record/reserve/cancel/finalize/queue transitions that preserve
the detector snapshot and inner lifecycle receipt index. The generic lineage commit
binds prior and installed outer versions. The outer version is never the detector
receipt index, selector version, or assessment sequence. A stale, sibling, repeated,
skipped, rolled-back, exhausted, or unreceipted outer version retires the lineage and
stops publication.
Each transition atomically persists the complete canonical snapshot and
compare-and-swaps `GaladrielLifecycleLineageHead` through
`InstalledGaladrielLifecycleLineageSelector`, then emits
`GaladrielLifecycleLineageCommitReceipt`. An assessment-bearing transition first
constructs `GaladrielAssessmentPublicationCandidateFact`. The fact binds the exact
live receipt, vector, projection, source captures, source authority, and outbox
identity. It excludes the later assessment head, commit, and publication record.
The first compare-and-swap installs H1 with the snapshot, lifecycle receipt,
candidate fact, and `PENDING_RECORD_INSTALL`. Only after H1 and its commit C1 exist
can the immutable publication record bind the fact, H1, and C1. A handoff-only second
compare-and-swap from exact H1 installs H2 with that record and `RECORD_INSTALLED`
while preserving H1's snapshot and lane map.
The record excludes installing H2, its selector version, and C2. A lifecycle advance
or invalidation that wins before H2 installs `CANCELED_BEFORE_RECORD_INSTALL` and
makes record installation lose. No record is exposed and no reservation can start
before H2 is installed. Each candidate-state value excludes its own installing
successor, selector, and post-CAS receipt; installed-state evidence binds those
objects separately.
The only genesis consumes a parent-created
`UNINITIALIZED` selector once. Same-lineage restart requires exact restore and
byte-identical snapshot continuation. An incompatible schema/implementation revision,
opaque state digest, lost, ambiguous, sibling, skipped, reset-root, or reused-epoch state
retires the lineage. Both a fresh source epoch and a qualified late attach require
complete warmup. Existing-epoch late attach uses one
`GaladrielLifecycleBoundaryCommitReceipt`. It binds the authorized actor/profile,
descriptor/declaration/grant, installed receiver admission head/high-water, the exact
first new-lineage `LIVE` admission receipt and head commit, zero prior samples, and no
pre-boundary suffix.
The native mutation interface permits only receipted source, reset, timeout, rollover,
assessment, qualified-boundary, and terminal-fault transitions. Compatibility
`clear_histories` is not exposed; any diagnostic invocation retires the lineage and
requires a fresh lineage plus full warmup.
History, replay, same-boundary reuse, and old retained frames reject. Assessor
incarnation does not reset detector lineage. Every genesis, boundary, update, handoff,
assessment, outcome, and admission binds the same exact source-authority object set.
Only an exact same-coordinate-scope grant renewal may preserve lineage and warmup.
It requires the exact affected lane-key set, old/new grant tuples and digests, server
enforcement receipts/activation-entry proofs, observer installation receipts and
prior/installed composite admission heads, a gap-free/non-overlapping per-lane
last-old/first-new frame-admission boundary, and a successful
`GaladrielLifecycleAuthorizationSpanTransition` snapshot/head CAS before the first
new-grant frame enters state. It changes only the current grant member in affected
lanes and preserves every sibling byte-for-byte. Every other independent tuple
change requires an authenticated
new-lineage or reset transition and complete profile-qualified warmup. An unproved
change retires the lineage and is not policy-eligible. A session-generation change
always retires the old source-authority scope.
Every accepted, rejected, and faulted transition persists durably, but a non-assessment
transition need not publish separately. Each envelope binds its assessment head and
commit plus a signing-time `GaladrielLifecycleCurrentSelectorAttestation`. If that
selector advanced, the closed proof is a contiguous `HEAD_CHAIN` or a
`COMPACTION_BRIDGE` with the exact authenticated
`GaladrielLifecycleCompactionBridge`. A historical commit, unexplained non-assessment
receipt, sibling selector, or stale root cannot substitute. Crash recovery queries
the exact installed H1 candidate or H2 publication record; it never infers a record
from an H1 candidate alone. Every outcome and admission
binds the assessment head, commit, attestation, and required ancestry.
The observer-side lifecycle adapter alone holds the observer credential and calls
`verifies_assessments` while the complete serialization-only Galadriel values are live.
It constructs only the publication candidate fact and later immutable authenticated
publication record through a distinct local handoff authority. The assessor holds
only the extension key. It has no
`ObserverReadCapability`, bus handle, or detector store. It strictly verifies the
record and latest currentness. Canonical `GaladrielAssessmentHandoffStateHead` binds
the handoff authority/security/lineage, records and updates, per-assessor sequences,
closed publication-candidate states, candidate facts, installed records,
reservations, cancellation tombstones, outbox commitments, and
`GaladrielAssessmentQueueTransitionFact` values. It excludes release, cancellation,
and publication-resolution receipts.
It is subordinate state inside `GaladrielLifecycleLineageHead`.
`InstalledGaladrielLifecycleLineageSelector` is the sole lifecycle/handoff
currentness root; there is no independent handoff selector. Every candidate install,
record install, advance, invalidation, `RESERVE`, pre-finalize cancellation,
`FINALIZE`, and queue-fact
compare-and-swaps that selector and emits
`GaladrielAssessmentHandoffStateCommitReceipt` over both prior/installed lifecycle
and handoff heads. Lifecycle genesis creates the never-used handoff substate in the
same transaction. A handoff-only successor preserves the detector snapshot/lane map;
a lifecycle successor installs its matching handoff currentness or invalidation.
The lifecycle/handoff head binds one never-reused `assessor_clock_incarnation` and
every reservation, finalization, and local-queue deadline in that clock. Exact restore
preserves those deadlines. Otherwise exact transition
`GALADRIEL_ASSESSOR_CLOCK_RESTART` constructs receipt-free
`GaladrielAssessorClockRestartTransitionFact`, which binds the prior lifecycle/handoff heads,
selector, old/fresh clock incarnations, and either a complete no-later mapping or a
complete cancellation set for pending pre-queue work. The successor heads bind the
fact; the lifecycle selector installs them; generic commits follow; and
`GaladrielAssessorClockRestartCommitReceipt` is emitted last. Missing, partial,
extending, or ambiguous conversion cancels pending release work while preserving
already released immutable local-queue items and bytes. Numeric clocks never cross
incarnations, and deadline equality is expired.
The candidate/record handoff uses the acyclic H1-then-H2 sequence above.
H1 installs `PENDING_RECORD_INSTALL`; H2 installs `RECORD_INSTALLED`; a winning
advance or invalidation installs `CANCELED_BEFORE_RECORD_INSTALL` and exposes no
record. Signed
publication then uses two more compare-and-swap phases. Exact
`GaladrielAssessmentPublicationReservation` binds one sequence and unsigned envelope
preimage, and `RESERVE` is forbidden until the record is installed in H2. After
signing, `FINALIZE` requires the same installed reservation
with no advance or invalidation. Its winning lifecycle-selector CAS binds a trusted
assessor-clock sample in the reservation's current incarnation and requires that sample
to be strictly before the exclusive not-after. Equality, a later sample, or a clock
restart without the installed no-extension mapping atomically cancels/tombstones the
reservation and creates no release or outbox item. It first builds a receipt-free
`GaladrielAssessmentReleaseOutboxCommitment` over the exact signed envelope bytes,
digest, and length,
literal route, Haldir audience, security context, assessor-local deadline, record,
reservation, and sequence. The successor handoff head binds only that commitment.
After its CAS, the generic handoff commit and specialized
`GaladrielAssessmentPublicationReleaseReceipt` bind the transition. The complete
`GaladrielAssessmentReleaseOutboxItem` binds the commitment and release receipt and
carries the immutable signed bytes. One local transaction persists the successor
head, generic commit, release receipt, and complete item while consuming the
sequence. The head never binds the item or post-CAS release. Complete-item ownership
transfer is the publication release point.
A transport worker constructs exactly one two-valued local
`GaladrielAssessmentQueueTransitionFact` and compare-and-swaps the lifecycle selector
to a successor handoff head that binds the fact. The fact excludes the successor
digest, selector, generic commit, resolution, and every external-transport field.
One local durable transaction persists the successor heads, generic commit, exact
local durable extension-queue item when released, and post-CAS
`GaladrielAssessmentPublicationResolution`. The resolution is exactly
`CANCELED_BEFORE_LOCAL_QUEUE` or
`RELEASED_TO_LOCAL_DURABLE_EXTENSION_QUEUE`; it binds the fact, prior/installed
lifecycle and handoff heads, selector version, and generic handoff commit. A lost
local commit reply is recovered from the installed selector and local queue, never
represented as a third local outcome.
A later worker drains the exact immutable local queue item to external transport.
Its separate `GaladrielAssessmentExternalTransportDisposition` binds the queue item,
exact bytes, destination, one idempotency context, and either an authentic transport
receipt or exact sent-attempt uncertainty evidence. Its closed result is `DELIVERED`,
`REJECTED`, or `AMBIGUOUS_AFTER_EXTERNAL_TRANSPORT`. This disposition is outside the
lifecycle transaction, cannot authorize publication or Haldir effect, and cannot
re-sign, resequence, reconstruct, or change bytes. An ambiguous result retries only
when the transport proves same-key idempotency; otherwise it is terminal and explicit.
Publication before `FINALIZE` is prohibited. Advance or invalidation before append
atomically installs a `CANCELED_BEFORE_FINALIZE` tombstone, consumes the sequence,
and creates no outbox or queue result. The successor head binds the tombstone and
excludes the post-CAS `GaladrielAssessmentReservationCancellationReceipt`. That
receipt binds the tombstone, prior/installed lifecycle and handoff heads, selector
version, and generic handoff commit. This branch is distinct from post-finalize
`CANCELED_BEFORE_LOCAL_QUEUE`. Crash or retry resumes or queries the same preimage,
sequence, lifecycle selector, outbox entry, cancellation receipt, and bytes. The
finalized push carries the exact
protected source-authority bundle, per-assessment mapping receipts, and source-capture
attachments that the publication record reserved. Role credentials, processes, stores,
replay state, and queues remain disjoint. The handoff exposes no mutable state.
The initial extension rejects before corresponding allocation above 20 MiB for the
complete envelope, 16 KiB for the receipt, 16 MiB for the raw vector, 1,024 members,
or 256 KiB for one serialized report. Exact boundaries pass; plus one rejects. Valid
oversize results are unpublishable and profile-ineligible, never truncated, sampled,
or cherry-picked. Larger or per-member commitments require a new version and manifest.
The optional producer request is exactly `RECORD_ONLY` or `REQUEST_DENY_TIGHTEN`.
It is non-authoritative; absence or unknown input defaults to record-only, and Haldir
alone derives handling, effect, meet, and any installed restrictive transition.
The installed monitor profile contains static policy, allowlists, calibration,
qualification, exact track population, and one content-addressed closed qualified
`ANY`, `ALL`, or bounded `THRESHOLD` vector rule. It declares handling for evaluated
insufficient, lifecycle abstention, empty/all-nominal/mixed vectors, missing/extra/
duplicate tracks, and inapplicable populations. Missing or inapplicable qualified
rules are record-only.
The receiver-issued `AssessmentAdmissionRecord` is evidence-only. It binds the exact
envelope, assessor replay identity, binding/scope/suite, lifecycle head/currentness,
complete receipt/vector/report and ordered observations, source captures, adapter
mapping, admitted body/session correlation or explicit absence, receiver clock
evidence, receiver single-flight identity, and its expected prior receiver-state
context. It excludes the installed successor, selector, and post-CAS receipts. Its
closed shape forbids profile,
member selection/classification, aggregation result, policy head/revision/deadline,
eligibility, handling, effect, local permission, meet, successor, and commit fields.
`HaldirAssessmentReceiverStateHead` is the receiver's composite root for assessor
high-water and retired commitments, pending evidence preimages, immutable admissions
or rejected terminals, unfinished dispositions, and safe rotation commitments.
`InstalledHaldirAssessmentReceiverStateSelector` is its only currentness root; every
transition emits `HaldirAssessmentReceiverStateCommitReceipt`. Exact
`RECEIVER_STATE_GENESIS_FROM_UNINITIALIZED` consumes one parent-created never-used
selector. The receiver reserves first ingress and persists only evidence preimages
plus the complete immutable record. Same-position same-digest retries resume it;
conflicting content rejects. The successful record-install CAS then emits separate
`HaldirAssessmentAdmissionCurrentnessReceipt` over the record, prior/installed
receiver heads, selector versions, and generic state commit. Policy delivery requires
both record and currentness receipt. Unsafe eviction cannot reset replay state.
On first delivery, the policy-state authority first constructs
`HaldirPolicyIngressReservationFact`. It binds the admission and admission-currentness
digests, authority principal/never-reused instance/clock and first-receive time, and
closed `HaldirPolicyIngressProfileSelection`. It excludes policy heads, selectors,
commits, ingress stamp, barrier, result, and finalization. One compare-and-swap
installs pending policy head H1 over the admission and fact only, then emits generic
commit C1. H1 and C1 exclude the later stamp. After C1, the authority constructs
`HaldirPolicyIngressStamp` over the fact, admission/currentness, exact H1, selector
version, C1, state/permission revisions, and selection. H2 is the first head that may
bind the stamp. `PROFILE_SELECTED` binds the
independently installed profile and an authority-local deadline. `NO_PROFILE` binds
the installed base-policy no-profile rule/source receipt and a distinct local
deadline, forbids profile-derived fields, and advances H1 or a permission-preserving
descendant to terminal H2 as `NO_PROFILE_NOT_EVALUATED`, without a barrier or result.
The only new branch bindings in that H2 are the exact ingress stamp and closed
outcome. H2 excludes its generic state commit and
`HaldirPolicyEvaluationFinalizationCommitReceipt`. Only after the H2 compare-and-swap
succeeds do those two receipts bind the prior and installed heads, selector version,
rule, and not-created marker.
For `PROFILE_SELECTED`, the evaluation barrier is H2 and first binds the stamp.
Receiver, assessor, producer, and commander cannot create the fact, stamp, or restamp.
`AssessmentHandling` is the closed `RECORD_ONLY` or `ELIGIBLE_RESTRICTION` decision;
`PermissionEffect` is a separate closed type. Record-only and non-required advisory
absence map only to `NO_ADDITIONAL_RESTRICTION`, the meet-identity lattice top. Its
internal binary representation can be ALLOW, but it never grants permission or clears
an installed deny. Profile-required absence and eligible restriction map only to the
exact content-addressed profile-owned deny element. Admission, disposition, and policy
head bind handling, effect, and aggregation result; an unknown or mismatched pair
rejects. Every meet is associative, commutative, idempotent, and non-widening.
The authority durably holds one exact exclusive operation for the admission/stamp.
After delay and currentness guards pass and strictly before the selected-profile
deadline, it constructs receipt-free
`HaldirAssessmentEvaluationBarrierFact`. The fact binds the exact admission and
currentness receipt, ingress reservation fact/stamp, selected profile, installed H1 or
permission-preserving current ancestry, authority clock/sample/deadline, every passed
delay/currentness/security/profile/source guard, preserved base-policy/profile/latch/
permission/invalidation inputs, and the durable exclusive token. It excludes H2,
selector, generic commit, barrier receipt, and result. One no-widening
`ASSESSMENT_EVALUATION_BARRIER` CAS advances that exact predecessor to H2, which binds
the fact and preserves the named inputs. At its linearization point, the authority
reverifies the current policy-clock incarnation and a trusted sample strictly before
the installed deadline; equality or a later sample makes the CAS fail. The post-CAS
generic policy commit also binds
the fact and H2. Only then does
`HaldirAssessmentEvaluationBarrierCommitReceipt` bind the fact, H2, selector, and
generic commit. The authority then evaluates exact H2 and creates authenticated
`HaldirPolicyEvaluationResult` over
the selected members, every classification, aggregation/qualification/source-clock
evidence, handling/effect, prebarrier local permission, meet, and barrier. H2 adds no
restriction. The result excludes H2F, H3, selector versions, state-commit receipts,
and its later finalization receipt. Every path then performs one terminal CAS and
releases the exclusive operation with
`HaldirPolicyEvaluationFinalizationCommitReceipt`, which binds the result,
prior/installed composite heads, selector versions, and generic state commit:
`EVALUATED_NO_RESTRICTION` or `EVALUATED_EXPIRED_NO_RESTRICTION` installs
permission-preserving H2F, while `RESTRICTION_COMMITTED` installs restrictive H3.
An independently authorized restrictive preemption terminalizes the same operation as
`PREEMPTED_BY_RESTRICTION`; it cannot use the assessment as its deny proof. Other
invalidation also terminalizes explicitly. A crash cannot leave the operation locked
or create H3 after the original deadline.
`HaldirPermissionPreservingHeadProof` is a bounded authenticated chain from the
decision/reservation head to the current composite policy head. Every link preserves
permission revision, base policy, profiles, latches, and publication-invalidating
state. H3, reload, revocation, widening, sibling state, or an unproved gap rejects.
Same-digest retries return the original stamp, barrier, result, and disposition even
after H1 is historical. A later profile/head cannot reevaluate it. Recovery before
the barrier resumes the exact stamp-bound operation; recovery after either CAS uses
the installed finalization receipt and ancestry without a second aggregation, CAS,
or disposition.
`HaldirAssessmentDisposition` binds the admission, stamp, and result or exact
not-created markers. `NO_RESTRICTIVE_POLICY_MUTATION` is either `NOT_EVALUATED` with
no barrier, or `EVALUATED_NO_RESTRICTION` with the exact H1/H2 barrier, terminal H2F,
and no H3. Both bind the exact terminal result and finalization receipt.
`RESTRICTION_COMMITTED` binds the evaluation result/barrier H2, restrictive H3,
selector version, exact `HaldirPolicyStateCommitReceipt`, finalization receipt, and
current ancestry or retained membership. It is mandatory for `APPLIED_DENY`. A losing
sibling, candidate, or historical receipt is not installed evidence.
The disposition outcome is exactly `RECEIVED_REJECTED`, `RECORDED`,
`PROFILE_INELIGIBLE`, or `APPLIED_DENY`. The first three require
`NO_RESTRICTIVE_POLICY_MUTATION`; only the last accepts exact installed
`RESTRICTION_COMMITTED` evidence. The separate latch lifecycle is
`NO_APPLIED_DENY` to `DENY_LATCHED` to `RECOVERY_PENDING`, then deny remains latched
or reaches `WIDENED_BY_AUTHENTICATED_TRANSITION` only through a separate authenticated
monotonic CAS. Expiry, retraction, disable, or profile change never rewrites a
disposition or clears the latch.
An applied policy effect additionally requires a profile-eligible evaluated default
report. Lifecycle abstention and evaluated `insufficient_evidence` are distinct
profile-ineligible states and cannot apply an effect.
The precondition record cannot depend on its successor.
Assessment dispositions remain immutable. Policy deny-latch recovery is separate,
and widening requires a new authenticated monotonic Haldir transition.
Producer UTC never establishes Haldir freshness. Different scope, suite, order,
incarnation, or capture mapping is non-substitutable.
Native gated source admission uses separately versioned signed `HaldirIntentV2` on
registered `haldir.intent.v2`; the frozen V1 meaning is not reinterpreted and native
profiles reject every downgrade. Its closed `SOURCE_PRESENT` branch carries one
portable `NormativeSourceRef` with matching `ProtectedOriginTransfer` plus bounded
ordered full reference/transfer watermarks. `SOURCE_ABSENT` carries only an exact
profile-permitted reason and forbids dummy sources and source-derived watermarks.
Haldir source admission stays in the integrated policy authority's authenticated
local-intent surface. After strict transfer verification, the authority constructs
receipt-free pre-CAS `HaldirIntentSourceAdmissionFact` over the exact prior policy
head, intent, source reference, and transfer. The successor policy head binds the
fact; only after its CAS do the generic policy commit and
`HaldirIntentSourceAdmissionReceipt` bind the fact, prior/installed heads, selector,
and commit. A losing CAS exposes no receipt. A policy decision can bind only this
post-CAS receipt, never the pre-CAS fact as installed evidence. The
transfer is a closed `EXACT_ORIGIN_TRANSFER` or
`TRUSTED_PROJECTED_ORIGIN_TRANSFER`. The first carries the exact protected original
producer envelope. The second carries protected projected bytes and the exact
receiver-independent `TrustedProjectionRecord` for the unchanged portable original
identity. The policy authority creates distinct local
`TrustedProjectionProvenance` only after its source-admission receipt exists.
Both bind the policy-authority ingress audience, intent, plant context, and transfer
policy. The original envelope or projection record must already authenticate that
exact audience and a current, non-revoked security state. An Engram signature, transfer
policy, local receipt, self-authored issuer, or after-the-fact redisclosure cannot
widen that audience.
`HaldirIntentIngressState` is subordinate to the composite policy head. Strict bounded
decode and its replay-fenced policy-selector CAS precede the receipt. The resulting
policy decision carries only the unchanged portable reference to the commander, not
the protected transfer or local receipt. Neither object
grants observer attach/subscription/query/read transport or command/plant authority;
they create no hidden process privilege and no tenth qualification role.
The policy authority issues one immutable commander-audience
`HaldirPolicyDecisionRecord`. It binds the exact intent/source/policy/replay/deadline
context and structurally forbids future NCP position, bytes, queue, and receipt fields.
One policy-selector CAS consumes the pending intent, commits the decision digest and
history inputs, and emits `HaldirPolicyDecisionCommitReceipt` over prior/installed
composite heads plus the generic state commit. The record excludes its successor and
post-CAS receipt; the commander requires record, receipt, and currentness proof.
Every attempt has one closed `HaldirPublicationAuthorizationOrigin`.
`POLICY_ALLOW_DECISION` binds that exact current decision and its authority-local
validity or a `HaldirPermissionPreservingHeadProof`.
`AUTHENTICATED_FAIL_SAFE_TRIGGER` instead binds one durable watchdog/restart/operator
trigger, current installed restrictive rule, freshness, and exact HOLD or ESTOP; it
forbids Active and synthetic ALLOW. It remains eligible under DENY only by that rule.
`HaldirCommanderPublicationStateHead` is the commander composite root for body
authority, security, allocator/capacity, preflights, consumed positions, queue entries,
and subordinate `HaldirCommanderQueueTransitionFact` values. The post-CAS publication
resolution is excluded from the head. `InstalledHaldirCommanderPublicationSelector` is its only
currentness root. Its one `COMMANDER_PUBLICATION_GENESIS_FROM_UNINITIALIZED` consumes
a never-used selector; every transition emits
`HaldirCommanderPublicationStateCommitReceipt`.
The commander head binds one never-reused `commander_clock_incarnation` and every local
preflight, handoff, queue, and freshness deadline in that clock. Exact restore preserves
the installed state. Otherwise exact transition `HALDIR_COMMANDER_CLOCK_RESTART`
constructs receipt-free
`HaldirCommanderClockRestartTransitionFact`, which binds the exact prior head/selector, old
and fresh clock incarnations, and either a complete no-later mapping or a complete
cancellation set for pending commander-local work. The successor binds the fact; the
commander selector installs it; the generic commit follows; and
`HaldirCommanderClockRestartCommitReceipt` is emitted last. Missing, partial,
extending, or ambiguous conversion cancels pending publication without restoring a
consumed position or widening fail-safe authority. Numeric clocks never cross
incarnations, and deadline equality is expired.
The commander first constructs receipt-free pre-CAS
`HaldirCommanderPublicationPreflight` over exact complete command bytes,
`imported_body_lease_view` plus exact Crebain issuance/currentness receipts and local
freshness/expiry, or permitted ESTOP lease absence, session/
generation, security, consumed stream position, local deadline, bounded queue slot,
and exact authorization origin. A commander-root compare-and-swap installs the
preflight and atomically consumes the position. Only after that CAS do the generic
commander commit and `HaldirCommanderPreflightInstallationReceipt` bind the preflight,
prior/installed commander heads, selector version, and consumed position. The narrow
handoff API and policy authority require both the preflight and that receipt; a losing,
stale, sibling, or unconsumed-position preflight cannot reserve policy, outbox, or
history. This transaction reserves commander-local position, slot, and state only;
it claims neither current cross-store body authority nor a body reservation. The
authority then installs one
`HaldirCommandPublicationReservation` through its common policy selector. It binds
the origin-validity deadline and a separate handoff not-after in the authority clock.
Both must remain exclusive-current; commander and authority numeric clocks are never
compared, and authenticated no-extension mapping can only tighten checks.
`HaldirPublicationFenceState`, the bounded receipt-free commitment
`HaldirPolicyReleaseOutbox`, and
`HaldirPublishedCommandHistoryHead` are subordinate to the composite policy head;
they have no independent currentness selectors. A restrictive change ordered first
marks every affected policy-allow reservation cancel pending. A fail-safe reservation
remains eligible only under its exact current restrictive rule.
A release ordered first constructs one receipt-free
`HaldirPolicyReleaseOutboxCommitment` over the reservation, authorization origin,
preflight, fence, exact command bytes/digest/length, route/audience, release slot,
deadlines, and pending worst-case history. The successor policy head binds the
commitment.
After its CAS, the generic policy commit and specialized
`HaldirCommandPublicationRelease` bind the transition. The complete
`HaldirPolicyReleaseOutboxItem` binds the commitment and release and carries immutable
bytes plus the pending history obligation. One policy-state transaction persists the
successor head, generic commit, specialized release, and complete item. The head never
binds the item or post-CAS release. Complete-item ownership transfer is policy
authorization release, not commander or NCP queue transfer. No crash cut can release
bytes while omitting the worst-case history obligation.
The commander drains that exact authenticated item once. Its local CAS
rechecks the imported receipted body view and local freshness, security, its own
deadline and slot. One commander-state
transaction installs the successor head, state commit receipt, exact queue item, and
acyclic queue-transition fact together; a generic external queue is not assumed
atomic with the selector. The closed post-CAS
`HaldirCommandPublicationResolution` binds that fact, prior/installed commander heads,
and commit receipt, and is
`POLICY_CANCELED_BEFORE_RELEASE`, `LOCAL_CONTEXT_CANCELED`,
`RELEASED_TO_NCP_QUEUE`, or `AMBIGUOUS_AFTER_NCP_QUEUE_BOUNDARY`. Every branch
consumes preflight, reservation, and position. Ambiguity is terminal, blocks Active,
and requires body-disposition reconciliation.
NCP queue release is never Crebain admission or application. The body independently
revalidates its current authority and remains the final actuator authority; B01 adds
no cross-store body reservation API.
One authenticated `HaldirCommandPublicationFeedback` finalizes released/ambiguous
accounting exactly
once. It clears a local-canceled pending entry only with exact proof that no queue
transfer occurred. Missing, conflicting, duplicate, or reordered feedback preserves
worst-case accounting or blocks the next decision. Authority-local feedback receive
time is conservative unless an authenticated no-later mapping tightens it. Feedback
and the next policy decision compare-and-swap the same composite policy selector.
The assessment receiver is a separate process and surface from the commander. Only
narrow authenticated Haldir-local IPC crosses that boundary; activation, credentials,
routes, replay state, and evidence state stay disjoint. Those IPC types remain
Haldir-owned and are not NCP stable-core allocations.
NCP allocates only generic `ConsumerSemanticAxisContractContentRef` and
`ConsumerSemanticCaptureStateHead`, its installed selector and commit receipt,
subordinate `ConsumerSemanticRegistryHead`,
`ConsumerSemanticRegistryHeadCommitReceipt`, and exact
`ConsumerSemanticRegistryCutoverReceipt`, plus
`ConsumerSemanticRegistryTerminalCommitment` and
`ConsumerSemanticRegistryFinalizationReceipt`.
The generic reference binds owner, digest, length, media/schema/canonicalization, and
exact content bytes. It assigns no variable meaning, scientific meaning, or authority.
The composite capture head binds owner/state incarnation and version, the exact
imported `consumer_owner_trust_state_digest`,
registry head, bounded open/closed segment heads and last sample/admission receipts,
retention, and prior head. Its selector is the only currentness root for registry
install, segment open/close, sample append, cutover, retention, and terminalization.
Genesis imports that owner-controlled trust state once. Every ordinary successor
preserves it byte-identical. A trust-root or owner-authorization change fences the
installed capture state and requires an explicitly authorized fresh state incarnation;
a caller-provided, default, stale, or silently replaced trust digest cannot select or
continue a capture lineage.
Before segment open, append, close, or cutover, each candidate segment subhead binds
the exact prior installed composite head/version and prior commit receipt, subordinate
registry digest, and exact registry entry. It excludes the successor composite head
and the commit that installs that successor. The successor composite head then binds
the segment subhead, and the post-CAS composite commit binds the successor. This
ordering prevents a segment/composite/receipt digest cycle.
Registry genesis consumes an owner-created uninitialized composite selector for a
never-used state incarnation and installs version-1 composite and registry heads.
The post-CAS composite commit binds both head transitions. The specialized registry
commit then binds that generic commit; the two receipts never contain each other.
Post-use absence, reset, restart, sibling genesis, or reuse
fences the affected capture lineages. Before a successor registry installs, the
cutover receipt binds prior/installed composite and registry heads and closes every
predecessor-authorized open segment at its exact last sample/admission receipt and
binds the successful composite-head CAS. A concurrent sample commits before the cut
and becomes the exact last sample, or loses and cannot append. The current composite
head authorizes new segments. A capture-time receipt plus retained ancestry preserves
a former-current
head only for its immutable validity interval. Archived ancestry can terminate only
at a receipted terminal commitment. Its canonical content binds the owner/incarnation,
final installed composite/registry heads and state version, selector version, both
last commit receipts, retained ancestry root, closed lineage validity intervals, and
reference horizon. Finalization proves the composite-selector compare-and-swap from
that final head to the terminal commitment. A sibling commitment, stale final head,
missing last
commit, fabricated interval, or empty/zero-entry terminalization without exact genesis
and finalization receipts rejects. Stale, sibling, rollback, provider-issued,
or bundle-self-signed heads cannot authorize new data. NCP does not allocate Prisoma
axis meanings. A body contract and consumer contract need not have equal digests;
equality does not grant mapping authority.
Prisoma allocates receipt-free pre-CAS `PrisomaNativeCaptureEventFact`, closed
post-CAS `PrisomaNativeCaptureEvent`, and bounded
`PrisomaNativeCaptureEventOutboxItem` in its consumer-owned namespace. The fact
contains the exact bounded C-event preimage and excludes every successor, selector,
commit, complete event, and outbox item. The segment successor binds only the fact.
One local transaction installs that successor, generic capture commit, complete event,
and outbox item. The successor never binds the complete event or item; a losing CAS
exposes neither. An idempotent worker drains only the exact item bytes to C, canonical
`runlog.jsonl`, unless C proves it is in the same conditional transactional store.
Reply loss queries the item and double-drain converges on its exact idempotency key.
Changed-byte, sibling, or cross-segment replay rejects. Each event binds the exact
descriptor, grant,
delivery/admission and security currentness, consumer capture head/entry/receipt,
axis contract, segment, frame, action semantics, ordered per-member provenance, and
delivered-byte or normalized-projection reference. A compatibility payload cannot
flatten those objects into string metadata. C cannot cite a future dataset, manifest,
bundle index, publication receipt, or row identity.
Finalization is acyclic and ordered exactly C -> D -> M -> R -> P. D is reconstructed
from closed C alone. M binds C, D, and the exact closed attachment, contract, registry,
lineage, segment, and grant sets. R is the distinct finalized bundle index and generic
pid-runlog audit stream over C, D, and M. P binds D, M, and R. No artifact binds its
own digest or a later artifact. Generic `EmbeddingContract`, `FrameObserved`, and
`EmbeddingCaptured` events exist only as deterministic R derivations, never as raw C
evidence. Independent reconstruction must reproduce D from C and R from C, D, and M.
Prisoma uses one content-addressed closed `LNumericTransformContract`.
`FROZEN_NEURAL_NUMERIC` binds exact instruction content/reference, tokenizer/model
and configuration, serialized graph/opset, sequence/pooling/output rules, dimension,
domain/dtype/conversion/transform, precision/quantization/determinism/thread policy,
and `PrisomaNumericEnvironmentManifest`. That manifest exhaustively binds
the executing binary and host/container image, compiler/toolchain/flags, resolved
loaded transitive/dynamic dependencies, launch arguments and numeric environment,
OS/kernel/libc, driver/firmware, CPU architecture/model/stepping/microcode/enabled ISA,
accelerator vendor/model/revision, provider/backend/runtime/library builds, device
properties, precision/quantization/deterministic-kernel/thread settings, and floating-
point rounding/FTZ/DAZ/denormal/math-kernel state. Every platform field is exact
`APPLICABLE` or reasoned `NOT_APPLICABLE`; null, unknown, default, or generic device
class rejects. Startup self-inspection and loaded-module evidence must match all of it.
`FROZEN_CATEGORICAL_NUMERIC` instead binds exact instruction/category input,
content-addressed vocabulary/category map, unknown/missing policy, parsing/
canonicalization, encoding, output order, dimension, domain/dtype/conversion, and
transform. It structurally forbids neural environment fields.
`PrisomaNumericExecutorStateHead` and its sole installed selector bind consumer owner,
executor/process/state incarnation, exact imported `trust_state_digest` and
`policy_head_digest`, version, pending/terminal one-use
operations, terminal `PrisomaNumericExecutionFact` values, tombstones, and prior head.
Genesis imports both digests from installed owner-controlled state. Every ordinary
successor preserves them byte-identical. A trust or policy-head change fences the
process state and requires a fresh never-used process/state incarnation; a default,
caller-selected, stale, or silently replaced digest cannot qualify execution evidence.
Each execution fact is constructed before compare-and-swap. It binds the one-use
run/operation and input digest, exact executing binary and resolved dependency
closure, runtime self-inspection, and exact output or exclusion result. It contains
no executor head, selector, commit, or later evidence. Exact
`NUMERIC_EXECUTOR_GENESIS_FROM_UNINITIALIZED` consumes a never-used selector.
The terminal successor head binds the fact.
`PrisomaNumericExecutorStateCommitReceipt` binds every successful compare-and-swap
and its prior/installed heads. Post-CAS `PrisomaNumericExecutorEvidence` binds that
fact, the prior/installed heads, selector version, and generic commit. The head and
fact exclude the evidence. A bundle author cannot synthesize it by restating a chosen
environment and vector.
The shared closed `PrisomaNumericTransformExecutionReceipt` has `NEURAL_EXECUTION`,
`CATEGORICAL_EXECUTION`, and `INPUT_EXCLUDED` branches. Every branch binds exact
authenticated executor evidence. Executed branches bind nonempty input, contract/
profile, and finite analysis-vector bytes/digest. Canonical bytes start with
the unsigned eight-byte big-endian dimension. Every member is its exact IEEE 754
binary64 big-endian bit pattern, including the sign of zero; nonfinite values reject.
The neural branch requires exact environment self-inspection and identical
known-answer/capture-replay bytes. The categorical branch recomputes category, index,
encoding, and every output bit from input and map and forbids neural environment data.
Its exact result is `PRESENT_KNOWN` or preregistered `PRESENT_UNKNOWN`; both require
real nonempty bound bytes. A literal `missing` is present data only when registered.
`INPUT_EXCLUDED` binds exactly one `SOURCE_ABSENT`, `EMPTY`, `UNBOUND`, or
`PARSE_FAILED` reason and structurally forbids category, index, output, row, and
estimator fields.
Environment, runtime, map, policy, dimension, order, endian, sign-zero, output, or
nondeterminism mutants reject or start a new qualified segment. No row or estimator
call occurs before complete receipt recomputation. Neither contract nor receipt proves
causality or scientific validity.
The set must allocate receiver-independent `NormativeSourceRef` and
`TrustedProjectionRecord`, plus receiver-owned `ResolvedOriginEvidence`,
`TrustedProjectionProvenance`, and `ResolvedCaptureSourceCorrelation`, separately.
Producer bytes never contain a receiver receipt. Origin bytes establish the portable
identity. The acyclic projected order is projected content/frame, projection record,
protected envelope/signature, receiver admission receipt, then local provenance.
The record binds projector/security state, original identity/digest, content-addressed
policy/transform, exact projected frame/content/declaration, and intended audience; it
contains no self digest, signature, receiver identity, local provenance, or receipt.
Local provenance contains only the record digest, receiver principal/evidence lineage,
and its exact admission receipt. Two receivers can use one audience-compatible record
only by creating distinct local provenance. Every local resolution is a closed
exact-original or trusted-projected form and proves only the delivered form. A driven
frame carries only the portable reference; projection records, provenance, and receipts
remain out of band. A swapped original, policy, transform, projected value, audience,
record, receiver, lineage, or receipt rejects. Future/self cycles, a body-local or
second-receiver receipt, driven-frame position, receiver time, or nearest frame cannot
substitute.
`ResolvedCaptureSourceCorrelation` uses the exact relation label
`producer_declared_resolved_source`. It proves only that a producer-declared portable
source identity resolves to the receiver's exact admitted bytes. It does not prove
internal computational consumption, absence of unrecorded inputs, exclusive influence,
or causality for a command, observation, assessment, or outcome. A stronger dependence
claim requires separate content-bound instrumentation and independent qualification.
`EXPLICIT_ABSENCE` is non-correlating and cannot satisfy a resolved join.
The set must also allocate sole-current
`BodySessionControlStateHead`, `InstalledBodySessionControlStateSelector`, and
`BodySessionControlStateCommitReceipt`, with subordinate
`PlantAuthorityStateHead`, pre-CAS `PlantAuthorityTransitionFact`, post-CAS
`PlantAuthorityStateCommitReceipt`, `PlantAuthorityCurrentnessReceipt`, and
`PLANT_AUTHORITY_GENESIS_FROM_BODY_SESSION_CREATION`; action-command
`DeclarationLedgerHead`,
`DispositionJournalHead`, `DispositionJournalHeadCommitReceipt`, and
`BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION`,
`SecurityAuthorityStateHead`, distinct `authority_state_version`, pre-CAS
`SecurityAuthorityTransitionFact`,
`InstalledSecurityAuthorityStateSelector`,
`SecurityAuthorityStateCommitReceipt`, `PROVISION_FROM_UNINITIALIZED`,
`SecurityStateTransitionAuthorization`, `SecurityRebindJournalRecord`, and
`SecurityRebindJournalCommitReceipt`; immutable reference-only
`CommandAuthorityCandidate`, closed `CommandAuthorityEvidence`,
`CommandIngressAttemptRecord`, `CommandIngressAttemptResolution`,
`BodyAppliedValueRef`, body-owned `BodyAppliedValueStreamDeclaration`,
closed fail-safe side-effect intents, `BodyFailSafeSideEffectReservation`,
`BodyFailSafeSideEffectRecord`, its closed outcome, and
`BodyFailSafeSideEffectResolution`,
distinct `BodyClockRestartBridge` and post-CAS
`BodyClockRestartBridgeCommitReceipt`, the exact application-append/current-ancestry
proof, and
`BodyBoundaryApplicationEvidence`. Raw applied-value bytes exist only as a separately
persisted and verifiable frame/content object on the declared body stream; neither the
disposition nor application receipt embeds them. The evidence is an acyclic post-CAS
receipt over the canonical successful `applied` append-record digest, event sequence,
reference, and prior/installed head transition. It is never embedded or self-hashed in
that append or the value frame. Capture cannot accept `applied` until the receipt also
proves the referenced bytes, current ancestry or retained-compaction membership. A
projected delivery envelope carries the exact receiver-independent
`TrustedProjectionRecord`. Capture creates receiver-local
`TrustedProjectionProvenance` only after admission. The application evidence itself
contains no projection record, future provenance, or admission receipt and proves only
the projected value.
`CommandAuthorityCandidate` preserves exact raw lease-field bytes or syntactic
absence. It is never verified authority. Closed `CommandAuthorityEvidence` keeps the
first `CANDIDATE_NOT_EVALUATED` state, verified body lease, permitted ESTOP lease
absence, and rejected-candidate branch distinct. Only verified body lease or the exact
installed ESTOP-absence rule can admit a command.
Hard byte and shape bounds, the protected envelope, default-deny manifest actor and
action plane, actual route and audience, live session generation, current security
state, and one unambiguous closed mode must pass before any side effect. The body then reserves a fresh
attempt identity and appends `CommandIngressAttemptRecord` with the exact bytes,
context, receive clock, and exactly one closed side-effect intent. `NONE_ACTIVE`
forbids a reservation. `CLEAR_ACTIVE` and `CLEAR_AND_LATCH_ESTOP` require an exact
durable `BodyFailSafeSideEffectReservation` before the local effect. Attempt identity
is not command identity. A valid non-Active attempt clears buffered Active output.
ESTOP also asserts the body-local stop latch before stream, replay, lease, TTL,
source, channel, and profile admission checks.
`BodyFailSafeSideEffectRecord` is a separate non-command append over that attempt and
reservation. It binds the exact intent, named buffer/latch transition, and one
`CONFIRMED_CHANGED`, `CONFIRMED_ALREADY_EFFECTIVE`, or
`UNKNOWN_AFTER_SIDE_EFFECT_BOUNDARY` outcome. This earlier body-local effect grants
no action-queue priority or entry, command admission, disposition, or `stop_latched`.
An ambiguous or unresolved reservation blocks later Active admission.
Full command admission independently requires the complete envelope, manifest, route,
audience, session, declared stream, replay, operation, TTL, source, channel, profile,
authority, and semantic gates. ESTOP action-queue priority, admission, and
`stop_latched` require that full gate; exact permitted ESTOP lease absence is the
only omission. Side-effect reservation, record, or resolution evidence cannot
substitute. Full admission then appends a closed
`CommandIngressAttemptResolution`: new command chain, exact replay of an installed
chain, same-identity content conflict, or rejection before canonical identity. A fresh
same-session stale, sequence-zero, foreign-epoch, or semantically invalid HOLD or
ESTOP applies the fail-safe effect and then uses `received` to `rejected` when it has a
new identity. Exact replay or identity conflict can apply the effect but cannot create
a second `received`. Wrong-context, unsigned, oversize, unverifiable, or ambiguous
candidates create no attempt and have no side effect. An invalid Active candidate has
no fail-safe side effect. Only a fully validated, admitted ESTOP can later reach
`stop_latched`.
A later `BodyFailSafeSideEffectResolution` binds the exact side-effect record and
attempt resolution without rewriting either state machine. A durable unresolved
reservation binds the exact candidate bytes, identity, mode, boundary, and time before
the local effect. Crash recovery starts non-actuating, preserves the latch, and blocks
Active output. It finalizes the exact reservation or retires the generation. Attempt,
effect, and resolution appends preserve unrelated active tips and retained chains.
One `BodySessionControlStateHead` remains stable for the exact body, plant profile,
logical session/generation, and control incarnation. It binds the current descriptor,
transcript, security state and referenced security-selector version, closed plant
lifecycle/latch state, exact subordinate `PlantAuthorityStateHead`, action-command
`DeclarationLedgerHead`, and `DispositionJournalHead`.
`InstalledBodySessionControlStateSelector` is the sole currentness selector. Every
authority acquire/renew/transfer/release/revoke/expiry, HOLD/ESTOP, action-command
declare/retire, disposition, attempt, side-effect, clock, retention, rebind, or
terminal transition compare-and-swaps that composite selector once. Each transition
conditionally verifies the referenced installed security-selector version in the
same proven local transactional store. If that common transaction is unavailable,
normal plant command admission stays closed. Separate remote or before/after checks
and a planned stop cannot qualify the open-admission race. Planned rotation fences
admission through the composite selector; an emergency security-selector advance
makes every pending old-state composite compare-and-swap lose. This local ordering
does not claim instantaneous CA/revocation-feed or fleet propagation. Live measured
mTLS rotation, revocation, and propagation remain external NOT RUN gates. The
generic post-CAS
`BodySessionControlStateCommitReceipt` binds prior and installed composite and
subordinate heads; each specialized authority, declaration, journal, rebind, clock,
or application receipt binds that generic receipt and the same heads.
`PlantAuthorityTransitionFact` is immutable pre-CAS input. Its authority successor
binds the fact, and the composite successor binds that authority successor. A live
lease exists only with the post-CAS authority commit and currentness receipts.
The plant-authority and action-command declaration heads and journal have no
independent effective selector. Command admission verifies their exact prior heads,
lifecycle/latch state, lease currentness, declaration, and security-selector version;
both selector conditions use that same proven local transaction, and any concurrent
change forces its composite compare-and-swap to lose.
`SecurityAuthorityTransitionFact` is the immutable pre-CAS security input. It binds
the prior security head and proposed semantic state, epochs, operation, and policy,
but excludes the successor head, selector, commit receipt, and every per-session
`SecurityStateTransitionAuthorization`. The security successor binds the fact; its
selector CAS produces `SecurityAuthorityStateCommitReceipt`; only then can the
authority issue a per-session authorization for a later composite rebind. Security
heads and facts exclude those authorizations, so an authorization cannot become an
input to the security head that must precede it.
Every historical record binds the state installed
when it appended. Only a committed security-rebind record can change the composite
head's current binding. Its authorization is pre-install evidence only.
Planned mode requires no active tips and retires old
streams, grants, leases, and admission. Emergency mode holds the body, preserves old
tips only as fenced obligations, blocks new admission, permits `received` only to
`rejected` and `admitted` only to a justified non-success terminal, and never permits
`applied`. Retired states are historical-only; compaction retains rebind ancestry.
An ambiguous prior, partial install, sibling, replay, or wrong-selector transition
retires the generation.
`BODY_SESSION_CONTROL_GENESIS_FROM_SESSION_CREATION` is the only empty
initialization. Parent session creation allocates fresh control, plant-authority,
action-command declaration, and journal incarnations. The exact plant-authority and
command-declaration genesis kinds prepare their version-one subordinate heads. The
composite genesis installs them while compare-and-swapping the version-one composite
and sequence-zero
`EMPTY_GENESIS` journal from the explicit uninitialized composite selector. The
generic commit precedes every specialized commit. Later absence, reset, restart,
sibling genesis, or any subordinate incarnation's reuse retires the generation.
Across body-clock incarnations, the canonical non-command bridge is a closed
`FROM_EVENT` or `FROM_EMPTY_HEAD` form. The first names the prior event or bridge;
the second is valid only from the installed sequence-zero `EMPTY_GENESIS` head with
no event digest and empty command maps. A restart after any event or bridge must use
`FROM_EVENT`. Every bridge preserves all active and retained command state and
excludes its own digest, installed head, and receipt. Its successor selects the fresh
clock and commits the bridge digest/kind. Only its
successful post-CAS receipt plus current ancestry establishes journal order; raw
cross-incarnation timestamps do not. A losing sibling,
historical tip, stale root, orphaned content digest, receiver time, optional digest, or
consumer mapping cannot prove application. A missing or
weakened required category, identifier, or invariant blocks N01.

The next two tables inventory future evidence-floor requirements only. No gate ID,
identity count, local receipt, or parser result in these tables is an admissible
external or independent status in the current checker.

| External-floor task | Required checked gate ID |
|---|---|
| `B02` | `owner-rebaseline-authorization` |
| `N09` | `current-advisory-and-registry-identity` |
| `R11` | `owner-approved-stewardship-policy` |
| `X02` | `composed-ecosystem-multi-writer` |
| `X05` | `disjoint-independent-challenge-exposure-anchor-infrastructure` |
| `F04` | `live-security-fault-soak-rotation-revocation` |
| `F05` | `release-performance-resource-visual` |
| `R10` | `incident-response-exercise` |
| `R03` | `signed-tag-remote-draft-release` |
| `R04` | `protected-build-sign-attest-stage` |
| `R05` | `registry-and-github-publication` |
| `R06` | `github-metadata-controls-and-clean-install-docs` |
| `R07` | `consumer-tag-repin-and-revalidation` |
| `R08` | `ecosystem-metadata-and-profile` |
| `R09` | `public-install-and-emergency-revocation` |

| Independent-floor task | Minimum distinct independent identities |
|---|---:|
| `B01` | 2 |
| `F01` | 2 |
| `E05` | 1 |
| `H03` | 1 |
| `H05` | 1 |
| `G03` | 1 |
| `P03` | 1 |
| `C05` | 1 |
| `X00` | 1 |
| `X01` | 2 |
| `X03` | 2 |
| `X04` | 2 |
| `R00` | 2 |
| `R02` | 2 |

## Intake repository snapshot

| Repository | Branch | HEAD | Tree | Dirty paths | Intake disposition |
|---|---|---|---|---:|---|
| NCP | `main` | `6e8278366755` | `cbb9153e5499` | 0 | Clean provider intake at 6e82783667554b8d8b433261e6b8ae588e94d89f; B00 owns only the listed ledger, generated-view, instruction, and gate-wiring paths. |
| Engram / Paper2Brain | `main` | `92853d2fe6e8` | `1625378dcd22` | 168 | Preserve all 168 stopped-agent paths; do not stage, reset, clean, or bulk-format them during provider work. |
| Haldir | `wip/current-file-review-ledger` | `bb6c0a7b27bb` | `2b472937b393` | 0 | Clean stopped-agent branch; do not change it before its dependency-ready H01 intake. |
| Galadriel | `main` | `f541f3eda7cf` | `47aa9b75e988` | 0 | Clean main baseline; do not change it before dependency-ready G01. |
| Crebain | `main` | `3e3ee5d0b752` | `4be236496ef5` | 0 | Clean canonical body baseline; keep separate from the producer worktree. |
| Crebain Galadriel producer | `feat/galadriel-integration-refresh` | `113ee70d5660` | `55eb96da6d98` | 0 | Clean feature worktree; reconcile only in C04 after canonical C01-C03. |
| Prisoma | `main` | `b0185d98aea8` | `0d7287deb631` | 0 | Clean main baseline; preserve v0.8 history while adding a parallel 1.0 observer. |
| pid-rs | `main` | `1410c8808f1b` | `516a2c956494` | 0 | Clean standalone estimator/run-log baseline; preserve its protocol-neutral dependency direction and refresh consumer pins only in dependency-ready Galadriel/Prisoma tasks. |
| Cortexel | `main` | `5d900d41d41a` | `24f96328752d` | 0 | Clean excluded non-peer baseline; preserve the stable FigureRequestV1 no-NCP-adapter boundary. Cortexel is outside NCP implementation, consumer qualification, and V11 atlas ownership. |
| sepahead profile | `main` | `80a5c1d5af3a` | `ed84f1da473e` | 2 | Preserve the two unrelated untracked tool directories; edit only canonical sources when R08 is evidence-ready. |

## Ten-lens mapping to the prior twenty-lens review

| Lens | Name | Prior lenses | Stricter rule |
|---|---|---|---|
| `L1` | Contract and semantics | `L02`, `L04`, `L13`, `L14` | Both taxonomies must pass; disagreement across prose, types, schemas, wire, generated packages, or SemVer remains a failure. |
| `L2` | Security and authority | `L06`, `L07`, `L08`, `L09` | Identity, provenance, cryptography, authority, safety, and hostile-parser obligations all apply; an unknown or missing value grants nothing. |
| `L3` | Safety and plant boundary | `L08`, `L11`, `L19`, `L20` | Authority, lifecycle, human recovery, and counterfactual hazard review all pass; protocol ESTOP never becomes physical certification. |
| `L4` | Distributed systems | `L05`, `L11`, `L12`, `L18` | Ordering, replay, lifecycle, determinism, and ecosystem composition all pass across loss, partition, restart, concurrency, and partial commit. |
| `L5` | Resource and real-time bounds | `L09`, `L10`, `L15` | Parser, resource, deployment, queue, deadline, storage, and overload bounds are explicit before allocation and fail closed. |
| `L6` | Interoperability and migration | `L12`, `L13`, `L14`, `L18` | Reproducibility, API/FFI/SemVer, wire parity, and composition all pass in independent installed implementations without silent translation. |
| `L7` | Science and statistics | `L01`, `L03`, `L06`, `L17` | Claim scope, estimand/statistics, provenance, and evidence quality all pass; missing variables and simulations cannot be promoted. |
| `L8` | Implementation and operations | `L13`, `L15`, `L16`, `L19` | APIs, deployment, observability, recovery, accessibility, and human governance are executable and hard to misuse. |
| `L9` | Verification and evidence | `L03`, `L12`, `L17`, `L20` | Mathematical, reproducibility, evidence-quality, negative, and counterfactual obligations all pass at their stated abstraction only. |
| `L10` | Lifecycle and governance | `L01`, `L06`, `L16`, `L18`, `L19` | Claims, provenance, forensics, ecosystem ownership, human governance, revocation, support, and succession are explicit and current. |

## Dependency-ordered tasks

Requirement IDs identify coordination scope. They do not grant runtime authority,
close a requirement, or change a task's evidence floor.

| Task | Status | Claim tier | Required evidence class | Requirement IDs | Scope | Dependencies | Repository | Source commit | Residual risks |
|---|---|---|---|---|---|---|---|---|---:|
| `B00` | `LOCAL_PASS` | `COORDINATION_ONLY` | `LOCAL` | `B00-ledger-integrity`, `B00-no-optimistic-status`, `B00-resumption-control`, `B00-current-generation-evidence`, `B00-content-bound-receipts` | Create the live implementation and evidence ledger | — | NCP | `6381d2a7cc82` | 4 |
| `B04` | `LOCAL_PASS` | `COORDINATION_ONLY` | `LOCAL` | `B04-acceptance` | Prove authenticated-ingress and independent-parser feasibility | `B00` | NCP prototypes | `3754635404f3` | 6 |
| `B01` | `IN_PROGRESS` | `COORDINATION_ONLY` | `INDEPENDENT` | `B01-acceptance`, `D01`, `D02`, `D03`, `D04`, `D05`, `D06`, `D07`, `D08`, `D09`, `D10`, `D11`, `D12`, `D13`, `D14`, `D15`, `D16`, `D17`, `D18`, `D19`, `D20` | Decide and ratify ADR-001 through ADR-011 | `B04` | NCP | `—` | 12 |
| `B02` | `OPEN` | `COORDINATION_ONLY` | `EXTERNAL` | `B02-acceptance`, `D19` | Authorize and identify the deliberate pre-release rebaseline | `B01` | NCP | `—` | 0 |
| `B03` | `OPEN` | `COORDINATION_ONLY` | `LOCAL` | `B03-acceptance`, `D09`, `D13`, `D19` | Reserve registries, namespaces, error codes, and owners | `B02` | NCP | `—` | 0 |
| `N01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N01-acceptance`, `D04`, `D19` | Establish the single normative source graph and identity projections | `B03` | NCP | `—` | 0 |
| `N02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N02-acceptance`, `D01`, `D02`, `D05`, `D20` | Implement typed simulation, plant, and observer session lifecycles | `N01` | NCP | `—` | 0 |
| `N03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N03-acceptance`, `D03`, `D07`, `D08`, `D15` | Implement declared streams, domain-separated authority, and command disposition | `N02` | NCP | `—` | 0 |
| `N04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N04-acceptance`, `D05`, `D06`, `D16`, `D20` | Implement the production authenticated envelope and semantic security state | `N02` | NCP | `—` | 0 |
| `X00` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `X00-acceptance` | Prototype an early independent non-Rust draft peer | `N03`, `N04` | independent draft-peer environment | `—` | 0 |
| `N05` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N05-acceptance` | Refactor critical Rust behavior into pure checked transition cores | `N03`, `N04` | NCP | `—` | 0 |
| `N06` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N06-acceptance`, `D06`, `D16` | Integrate security and state machines into Zenoh without trusting callbacks | `N05` | NCP | `—` | 0 |
| `N07` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N07-acceptance`, `D04`, `D14`, `D18` | Regenerate and harden all supported language and package surfaces | `N06`, `X00` | NCP | `—` | 0 |
| `N08` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N08-acceptance`, `D04`, `D05`, `D14` | Rebuild conformance, behavior, migration, and fixture coverage | `N07` | NCP | `—` | 0 |
| `N09` | `OPEN` | `IMPLEMENTATION_ONLY` | `EXTERNAL` | `N09-acceptance`, `D13` | Remove supply-chain and package-identity release blockers | `N07` | NCP | `—` | 0 |
| `N10` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `N10-acceptance`, `D09`, `D14`, `V11` | Rewrite normative and user documentation and regenerate visuals | `N08`, `N09` | NCP | `—` | 0 |
| `F01` | `OPEN` | `IMPLEMENTATION_ONLY` | `INDEPENDENT` | `F01-acceptance`, `D12` | Implement and independently review the TLA+ model suite | `N03`, `N04` | NCP | `—` | 0 |
| `F02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `F02-acceptance`, `D05`, `D12` | Implement SMT, Kani, and model-to-Rust refinement checks | `N05`, `F01` | NCP | `—` | 0 |
| `F03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `F03-acceptance`, `D10`, `D12` | Implement differential, property, fuzz, sanitizer, and mutation campaigns | `N08`, `F02` | NCP | `—` | 0 |
| `R01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `R01-acceptance`, `D17` | Create the final untagged 1.0.0 source cut and publication machinery | `N10`, `F03` | NCP | `—` | 0 |
| `R11` | `OPEN` | `GOVERNANCE_OPERATION` | `EXTERNAL` | `R11-acceptance` | Establish durable 1.0 stewardship without pretending software is eternal | `N10` | NCP and ecosystem governance | `—` | 0 |
| `E01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `E01-acceptance`, `D18` | Establish Engram's clean native-1.0 integration baseline | `R01` | Engram | `—` | 0 |
| `H01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `H01-acceptance`, `D18` | Add a parallel haldir-ncp10 adapter without mutating v0.8 history | `R01` | Haldir | `—` | 0 |
| `G01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `G01-acceptance`, `D02`, `D09`, `D18` | Create Galadriel's native-1.0 observer and extension adapter | `R01` | Galadriel | `—` | 0 |
| `C01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `C01-acceptance`, `D01`, `D10`, `D18` | Create Crebain's separate native-1.0 plant adapter and exact pins | `R01` | Crebain | `—` | 0 |
| `P01` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `P01-acceptance`, `D02`, `D03`, `D18` | Add a parallel native-1.0 Prisoma observer | `R01` | Prisoma | `—` | 0 |
| `E02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `E02-acceptance`, `D01` | Split Engram's simulation responder from plant commander types | `E01` | Engram | `—` | 0 |
| `H02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `H02-acceptance`, `D07`, `D08`, `D09`, `D15`, `D18` | Integrate body-issued authority and dispositions into Haldir Gate | `H01` | Haldir | `—` | 0 |
| `H04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `H04-acceptance`, `D09`, `D18`, `V11` | Implement Haldir's isolated optional assessment receiver | `H02`, `G01` | Haldir | `—` | 0 |
| `G02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `G02-acceptance`, `D02`, `D03`, `D20`, `V11` | Bind Galadriel lifecycle and monitoring to authenticated observer state | `G01` | Galadriel | `—` | 0 |
| `C02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `C02-acceptance`, `D07`, `D08`, `D10`, `D15` | Implement Crebain as body-issued authority and disposition source | `C01` | Crebain | `—` | 0 |
| `P02` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `P02-acceptance`, `D11`, `D20`, `V11` | Preserve missing-variable and research-claim semantics in native capture | `P01` | Prisoma | `—` | 0 |
| `E03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `E03-acceptance`, `D03`, `D20` | Implement Engram's authenticated transport and declared streams | `E02` | Engram | `—` | 0 |
| `C03` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `C03-acceptance`, `D03`, `D09` | Migrate Crebain sensor and Galadriel-extension publication | `C02`, `G01` | Crebain | `—` | 0 |
| `E04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `E04-acceptance`, `D08`, `D15` | Implement Engram's direct plant integration | `E03`, `C02` | Engram | `—` | 0 |
| `E06` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `E06-acceptance`, `D08`, `D15`, `D18`, `V11` | Implement Engram's optional Haldir-gated integration | `E04`, `H02` | Engram | `—` | 0 |
| `C04` | `OPEN` | `IMPLEMENTATION_ONLY` | `LOCAL` | `C04-acceptance`, `V11` | Verify the consolidated Galadriel producer lineage and retire stale branch references | `C03` | Crebain canonical repository | `—` | 0 |
| `X01` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `X01-acceptance`, `D04` | Qualify two genuinely independent installed non-Rust peers | `E03` | independent peer lab | `—` | 0 |
| `X05` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | `X05-acceptance`, `D20` | Qualify the disjoint observer challenge-exposure anchor infrastructure | `G02`, `P02`, `X01` | independent challenge-exposure anchor lab | `—` | 0 |
| `X02` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | `X02-acceptance`, `D07`, `D08`, `D20` | Run the composed ecosystem and multi-writer campaign | `E06`, `H04`, `C04`, `X05` | isolated ecosystem lab | `—` | 0 |
| `E05` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `E05-acceptance`, `D11` | Qualify Engram's exact installed native-1.0 roles | `E04`, `X01` | Engram qualification environment | `—` | 0 |
| `H03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `H03-acceptance` | Qualify Haldir's secure commander role | `H02`, `C02`, `X01` | Haldir qualification environment | `—` | 0 |
| `H05` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `H05-acceptance` | Qualify Haldir's optional assessment-receiver role | `X02` | Haldir qualification environment | `—` | 0 |
| `G03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `G03-acceptance` | Qualify Galadriel NCP observer and raw-advisory publisher roles | `X02` | Galadriel qualification environment | `—` | 0 |
| `P03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `P03-acceptance`, `D11` | Migrate the fault observatory and qualify Prisoma's observer role | `X02` | Prisoma qualification environment | `—` | 0 |
| `F04` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | `F04-acceptance`, `D06`, `D16`, `D20` | Execute the live security, fault, soak, rotation, and revocation campaign | `X02` | cross-ecosystem lab | `—` | 0 |
| `C05` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `C05-acceptance`, `D07`, `D10` | Qualify Crebain body and Galadriel-producer surface separately | `E05`, `H03`, `G03` | Crebain qualification environment | `—` | 0 |
| `X03` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `X03-acceptance` | Issue nine exact consumer and extension role qualification receipts | `H05`, `C05`, `P03`, `F04` | cross-ecosystem adjudication | `—` | 0 |
| `X04` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `X04-acceptance`, `D13` | Reproduce the provider and ecosystem from clean rooms | `X03` | independent clean builders | `—` | 0 |
| `F05` | `OPEN` | `QUALIFICATION_REQUIRED` | `EXTERNAL` | `F05-acceptance`, `V11` | Execute release-bound performance, resource, and final visual campaigns | `X04` | cross-ecosystem lab | `—` | 0 |
| `R00` | `OPEN` | `QUALIFICATION_REQUIRED` | `INDEPENDENT` | `R00-acceptance` | Hand the qualified candidate to the release runbook | `F05` | NCP | `—` | 0 |
| `R10` | `OPEN` | `GOVERNANCE_OPERATION` | `EXTERNAL` | `R10-acceptance` | Execute rollback, withdrawal, revocation, and incident response | `F04` | incident-response exercise | `—` | 0 |
| `R02` | `OPEN` | `RELEASE_OPERATION` | `INDEPENDENT` | `R02-acceptance`, `D17` | Issue the signed release-authorization bundle | `R00`, `R10`, `R11` | independent release adjudication | `—` | 0 |
| `R03` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R03-acceptance` | Create and verify the immutable signed tag and draft GitHub Release | `R02` | NCP release environment | `—` | 0 |
| `R04` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R04-acceptance` | Build, compare, sign, attest, and stage final artifacts | `R03` | protected release builders | `—` | 0 |
| `R05` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R05-acceptance`, `D13` | Publish exact registry artifacts and the GitHub Release | `R04` | protected publication environment | `—` | 0 |
| `R06` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R06-acceptance`, `V11` | Update NCP README, GitHub description, topics, and repository controls | `R05` | NCP and GitHub | `—` | 0 |
| `R07` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R07-acceptance`, `D18`, `V11` | Repin and revalidate every consumer against the immutable tag | `R05` | all consumer repositories | `—` | 0 |
| `R08` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R08-acceptance`, `V11` | Update ecosystem repository metadata and the public selected-work profile | `R06`, `R07` | ecosystem GitHub and profile | `—` | 0 |
| `R09` | `OPEN` | `RELEASE_OPERATION` | `EXTERNAL` | `R09-acceptance` | Run post-publication installs and emergency-revocation exercise | `R05` | public install hosts and revocation lab | `—` | 0 |

## V11 ecosystem-atlas ownership

V11 remains coordination scope until each owning task reaches its required evidence
class. Only NCP and the five exact consumer producers own atlas work. Cortexel
is an excluded non-peer and receives no atlas task, NCP role receipt, authority,
observer grant, or runtime edge.

| Task | Status | Repository | Owned atlas slice |
|---|---|---|---|
| `N10` | `OPEN` | NCP | Rewrite normative and user documentation and regenerate visuals |
| `E06` | `OPEN` | Engram | Implement Engram's optional Haldir-gated integration |
| `H04` | `OPEN` | Haldir | Implement Haldir's isolated optional assessment receiver |
| `G02` | `OPEN` | Galadriel | Bind Galadriel lifecycle and monitoring to authenticated observer state |
| `C04` | `OPEN` | Crebain canonical repository | Verify the consolidated Galadriel producer lineage and retire stale branch references |
| `P02` | `OPEN` | Prisoma | Preserve missing-variable and research-claim semantics in native capture |

### V11 evidence consumers

These tasks consume, check, or publish owner-produced atlas evidence. They do not
own a semantic graph or its generated variants.

| Task | Status | Repository | Consumer scope |
|---|---|---|---|
| `F05` | `OPEN` | cross-ecosystem lab | Execute release-bound performance, resource, and final visual campaigns |
| `R06` | `OPEN` | NCP and GitHub | Update NCP README, GitHub description, topics, and repository controls |
| `R07` | `OPEN` | all consumer repositories | Repin and revalidate every consumer against the immutable tag |
| `R08` | `OPEN` | ecosystem GitHub and profile | Update ecosystem repository metadata and the public selected-work profile |

## Status-change receipts

| Task | From | To | Timestamp (UTC) | Correlation ID | Receipt |
|---|---|---|---|---|---|
| `B00` | `OPEN` | `IN_PROGRESS` | `2026-07-16T05:56:27Z` | `ncp-v1-finalization-20260716-b00` | start with no dependencies; receipt not required |
| `B00` | `IN_PROGRESS` | `LOCAL_PASS` | `2026-07-16T08:59:26Z` | `ncp-v1-finalization-20260716-b00-local-pass` | passing receipt for commit `6381d2a7cc82` |
| `B04` | `OPEN` | `IN_PROGRESS` | `2026-07-16T09:18:11Z` | `ncp-v1-finalization-20260716-b04` | dependency-bound start receipt for `B00` at `2026-07-16T09:18:11Z` |
| `B04` | `IN_PROGRESS` | `LOCAL_PASS` | `2026-07-16T17:12:35Z` | `ncp-v1-finalization-20260716-b04-local-pass` | passing receipt for commit `3754635404f3` |
| `B01` | `OPEN` | `IN_PROGRESS` | `2026-07-16T17:53:20Z` | `ncp-v1-finalization-20260716-b01` | dependency-bound start receipt for `B04` at `2026-07-16T17:53:20Z` |

## Update and verification

The focused ledger commands require a disposable environment built from the
hash-locked evidence-tool requirements. The checker intentionally rejects an
ambient Python environment that has missing or unexpected packages. Run the
focused commands in a fail-closed subshell so that it removes the environment
after success or failure.

```bash
(
    set -euo pipefail
    ncp_ledger_root="$(mktemp -d)"
    cleanup_ncp_ledger() { rm -r -- "$ncp_ledger_root"; }
    trap cleanup_ncp_ledger EXIT
    python3 -m venv "$ncp_ledger_root/venv"
    ncp_ledger_python="$ncp_ledger_root/venv/bin/python"
    "$ncp_ledger_python" -m pip install \
        --disable-pip-version-check --require-hashes --only-binary=:all: \
        -r scripts/requirements-evidence-schema.txt
    "$ncp_ledger_python" scripts/check_implementation_ledger.py --self-test
    "$ncp_ledger_python" scripts/generate_implementation_ledger.py --check
    scripts/check.sh
)
```

`scripts/check.sh` creates the same pinned evidence environment and then runs
the complete local gate. A focused pass does not replace that handoff gate.

Raw logs referenced by future receipts must be bounded, repository-relative, and
content-addressed. Credentials, private keys, absolute workstation paths, mutable
source refs, missing outputs, and unexplained skips cannot be evidence. Self-review
cannot satisfy an independent evidence floor.
