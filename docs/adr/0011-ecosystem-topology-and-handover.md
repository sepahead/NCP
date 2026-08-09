# ADR-011 — Fix ecosystem dependency direction and plant handover

- Decision status: derived from the non-normative decision registry
- Task: `B01`
- Candidate: unreleased, release-blocked `1.0.0-rc.1`
- Normative effect before authorized N01 promotion: none
- Required reviewers: Engram, Haldir, Galadriel, Crebain, Prisoma, and pid-rs
  owners; independent security/distributed-systems reviewer; release and
  package-tooling reviewer; Crebain plant/safety reviewer

## Context

The ecosystem must remain standalone-first while supporting optional native NCP
roles. The unsafe ambiguities are:

- Engram simulation responder versus plant commander;
- direct Engram command versus Haldir-gated command;
- Haldir local permission versus Crebain plant authority;
- Galadriel observer versus deny-tightening assessor;
- observer read scope versus action publication authority;
- standard NCP frames versus project extensions;
- parallel migration adapters versus one consumer-wide pin;
- observation/research consumers accidentally entering the control path; and
- pid-rs or visualization outputs being mistaken for identity, authority, truth,
  calibration, or role qualification.

## Proposed decision

### Dependency direction

NCP is a project-neutral provider and depends on no consumer application.
All application integrations are optional adapters absent from default builds
and startup.

| Component | Standalone boundary | Optional NCP boundary | Authority/evidence boundary |
|---|---|---|---|
| Engram | neural simulation without NCP or other applications | simulation responder and plant commander are separate adapters | simulation state authority is not plant authority |
| Haldir | signed local intent decisions without NCP/Galadriel | NCP commander and default-off Galadriel assessment receiver | local ALLOW/DENY is not body admission or execution |
| Galadriel | local/synthetic cross-sensor analysis | read-only NCP observer and separate assessment extension producer | observations/assessments never grant command or plant authority |
| Crebain | local body/research behavior without NCP | sole NCP body plus separate standard/extension telemetry producers | final software actuator admission and dispositions remain Crebain-owned |
| Prisoma | offline research and run-log analysis | read-only capture of granted perception, command proposal, observation, and disposition routes | never publishes, commands, fills gaps, or enters the control path |
| pid-rs | protocol-neutral library/CLI | called only inside consumer-owned optional adapters | result/log grants no identity, permission, authority, or NCP role receipt |

pid-rs depends on none of NCP, Engram, Haldir, Galadriel, Crebain, or Prisoma.
NCP defines no package, runtime, evidence, observation, control, release, or
documentation-import edge to or from Cortexel.

### Authority-realm identity

ADR-001 `AuthorityRealmKey` is the canonical tuple of server authority principal
and stable realm ID. It excludes rotating security epochs, registry and
transaction-store incarnations, process incarnations, and every session, stream,
lease, policy, adapter, or consumer generation. A package, stable-core contract,
extension contract, and repository surface can remain realm-independent. Their
runtime activation in an NCP authority domain cannot.

Every realm-scoped request, frame, intent, source reference, transfer, lease,
grant, handover fact, command, disposition, observer/capture fact, topology
activation, key, head, selector, reservation, outbox item, transport attempt,
query result, evidence projection, and pre- or post-CAS receipt named by this ADR
carries `authority_realm_key: AuthorityRealmKey` as a direct canonical member.
Its canonical bytes and digest include that member. This includes the Engram,
Haldir, Galadriel, Crebain, and Prisoma runtime identities and their portable
provenance, evaluation, publication, handover, and role-qualification evidence.

A direct member remains required when the object binds a realm-bearing parent.
A receiver cannot infer the realm from a route, endpoint, certificate, manifest
name, deployment domain, surface descriptor, session ID, generation, body lease,
parent head, attachment container, or another receipt. A canonical projection
that drops, defaults, wildcards, or changes the realm is invalid.

Each installed default-deny manifest, audience, literal route grant, credential,
runtime namespace, replay partition, state store, and plant-session activation
binds the exact direct realm. A route's `{realm}` component is only the
canonical projection of the stable realm ID; it cannot supply the
server-authority-principal member or authorize another realm. Missing, unknown,
default, retired, or mismatched realm data rejects before adapter dispatch,
session/source lookup, replay mutation, policy evaluation, queue release,
handover, capture admission, callback, or side effect.

The canonical portable consumer foreign key is exactly
`(AuthorityRealmKey, session_kind, logical_session_id, generation)`. Every
stream, source, disposition, observer history, semantic capture, dataset,
publication, and consumer join uses that foreign key before its local
coordinates. Equal principal, session kind, logical session ID, generation,
stream position, operation, digest, and bytes in different realms are distinct
facts. They cannot merge, deduplicate, resume, inherit authority or policy,
satisfy one another's receipt chain, or claim continuity.
The tuple is encoded once in each canonical realm-scoped object:
`authority_realm_key` is its direct first member and the three session
coordinates complete it. References below to a direct realm and complete
session foreign key do not authorize duplicate, independently variable realm
fields. A compatibility duplicate must be exactly equal or the object rejects.

### Parallel migration surfaces

A consumer repository can retain an executable wire-0.8 adapter while it builds a
separate native-1.0 adapter. If an adapter remains executable or CI-built, the
consumer descriptor shall inventory it.

A surface is one deployable target or package and its exact resolved runtime
dependency closure. Its key binds the repository, canonical root path, target
kind and name, default-feature mode, canonical effective feature set, role, and
activation profile. It also binds the SHA-256 digest of a separate canonical
resolution-context document. That document binds the closed package ecosystem,
host and target triples, resolver, toolchain, build profile, canonical
configuration predicates and effective features, and exact content digests for
lock, package configuration, patches, environment, flags, build scripts, CI
invocation, and deployment invocation. Those source inputs are enumerated by a
separate canonical `ConsumerSurfaceInputManifest`, stored as
`.ncp-surface-inputs.v1.json`. The input manifest and resolution context exclude
the output inventory descriptor `.ncp-consumer`, discovery records, scan
receipts, generated inventory views, and their own later digests. A target's
effective feature set includes
every transitively enabled feature and must equal the context document's feature
set. A changed context creates a different key even when a prior scan produced the
same graph. Two targets under one package root share one root-package identity,
but each target and resolution context remains a separate surface.

Each descriptor entry binds a stable surface ID to the complete key. A checker
uses `surface_` plus the complete lowercase SHA-256 digest of the canonical key,
or an equally strong retained prior ID-to-key binding. An ID cannot silently move
to another key. The closure-root package identity uses the complete lowercase
SHA-256 digest of the canonical repository and root path. Each process,
credential, security-manifest, route, configuration, state, evidence, deployment,
and plant-session identifier uses the complete lowercase SHA-256 digest derived
from the surface ID and its closed identifier class. When that identifier
activates realm-scoped behavior, its derivation and activation record also bind
the exact direct `AuthorityRealmKey`. The realm-independent surface ID does not
supply or imply it. The same surface installed in two realms therefore has
distinct runtime, credential, route, state, evidence, and plant-session
identities. Truncated identity values reject. The entry also binds:

- the closed capability class and wire version;
- provider release state (`candidate` or `immutable_release`);
- subject kind (`git_commit`, `published_package`, or `synchronized_mirror`);
- the candidate or release label and exact source revision;
- package name, source identity, package ID, and artifact digest;
- a closed contract-identity kind, digest domain, SHA-256 digest, compact-hash
  algorithm, and compact hash;
- a closed ecosystem locator kind plus exact manifest, lock, and target-matching
  runtime paths;
- distinct closure-root and exact NCP-provider package identities;
- canonical runtime dependency graph nodes and target-active edges that retain
  the canonical target predicate and resolution-context digest;
- the independently discovered deployment domain and deployment profile;
- process, credential, security-manifest, route, configuration, state, evidence,
  and plant-session namespaces, including their direct realm binding when
  activated; and
- a closed lifecycle status.

The closed surface-lifecycle union is
`HISTORICAL_EXECUTABLE | MIGRATION_CANDIDATE | QUALIFIED_NATIVE | RETIRED`.
`HISTORICAL_EXECUTABLE` means that an older-wire runtime remains executable,
buildable in CI, or deployable. `MIGRATION_CANDIDATE` identifies work toward a
native adapter and grants no native qualification. `QUALIFIED_NATIVE` requires
the exact native-wire role receipts and independent qualification evidence that
this ADR specifies; the enum value alone proves nothing. `RETIRED` requires
independent evidence that the surface is not executable, CI-built, deployed, or
reachable through an active target. Unknown, default, missing, or contradictory
lifecycle values reject. A copied protocol file, source-only adapter, or pending
migration worktree cannot select `QUALIFIED_NATIVE`.

Construction has one directed content graph. Actual package, lock, build,
deployment, and runtime inputs are hashed first. The canonical
`ConsumerSurfaceInputManifest` enumerates those inputs and contains neither its
own digest nor any value derived later. Resolution-context and discovery records
bind that manifest's externally computed digest plus the applicable actual input
digests. Any built package/runtime artifact is then hashed independently; its
bytes cannot embed the output descriptor or its digest. If deployment needs the
descriptor, it carries it as separate metadata. Discovery can bind that artifact
after the context is fixed. The output descriptor `.ncp-consumer` is generated
last from those records. Its bytes and digest are excluded from every surface key,
resolution-context document, discovery record, scanner-input digest, and input
manifest that the descriptor contains. A scanner can read a prior descriptor
only as output to compare; it cannot classify those bytes as package
configuration or use them to derive the new descriptor's identity. Therefore the
graph cannot contain `.ncp-consumer -> digest(.ncp-consumer)`.

Release state, subject kind, and wire are separate dimensions. The current
wire-1.0 candidate can be a commit or synchronized mirror. A future immutable
wire-1.0 release can be a commit, published package, or synchronized mirror. A
label is not identity or trust. Every candidate and immutable subject must match
an exact trusted receipt. The receipt binds repository, release state, subject
kind, wire, label, package and source identities, revision, artifact, and
the complete typed contract identity. A receipt is pin authorization only. It is not
publication, signature, provenance, installed interoperability, or release
evidence. The top-level subject must match the exact resolved NCP-provider node.
Unknown/default release states, subject kinds, roles, capability classes,
lifecycle values, ecosystems, locator kinds, contract-identity kinds or domains,
edge kinds, target predicates, resolution contexts, or descriptor versions
reject.

Wire-0.8 and wire-1.0 do not silently share one digest projection. The historical
wire-0.8 identity is a `frozen_wire_baseline_artifact`: its SHA-256 value identifies
the exact frozen `wire_manifest.json` file, and its compact FNV-1a value is
`d1b50a2d8a265276`. It is not described as a complete normative-source digest. The
wire-1.0 candidate identity is a `complete_normative_contract`: its domain is
`ncp.normative-contract.v1`, its SHA-256 value covers the complete normative
source set, and its compact FNV-1a value is `163acc57d8a62b66`. Receipt and
provider comparisons include the kind, domain, algorithm, digest, and compact
hash.

Pin coherence is checked within each discovered surface. Discovery scans tracked
manifests, workspace targets and feature graphs, direct dependencies, known
lockfiles, build/package scripts, CI invocations, deployment/launch manifests,
activation configuration, and credential/route namespaces. A self-reported
descriptor cannot prove its own completeness. The scanner resolves only runtime,
target-active edges for one complete resolution context. It retains each selected
edge's canonical target predicate and context digest. The checker accepts only a
closed predicate grammar and evaluates each predicate against the context's exact
configuration set. An unknown or false predicate rejects the retained edge. An
exact graph records one resolution result; without its context, it cannot prove
which build it describes or that other contexts were scanned. A development,
build-only, or target-inactive dependency cannot make an NCP runtime surface.

B01 evaluates these rules with bounded synthetic fixture snapshots. Its
caller-supplied scan snapshot and deployment-topology map are model inputs. They
are not repository, build, deployment, or scanner evidence and cannot close D18.
Prospective native-role fixture names are not claims that matching consumer
targets or paths exist in the current sibling repositories.

N07 shall replace those fixtures with trusted scanner input. That input shall bind
the complete canonical content and digest of every `DiscoveryRecord`, not only its
surface key. It shall also bind the scanned repository/tree, tracked manifests,
target and feature graph, host and target triples, resolver and toolchain,
configuration and build-script inputs, lockfiles, environment and flags, CI and
deployment invocations, scanner policy and version, exact scanner source and
artifact revisions, and a scanner-invocation digest. An authenticated scan
receipt shall bind those values to an authorized scanner principal and trust
root. Package scope and deployment scope require independent adjudication. A
record digest computed by the same caller that supplies the record, a
caller-supplied synthetic scan scope or topology, or a set of matching keys cannot
prove completeness, execution state, retirement, or deployment-domain isolation.
B01 does not model that principal, trust root, authenticated receipt, or
independent scope adjudication. The external rescan remains **NOT RUN**.

Every discovered deployable, CI-built, or deployment-activated root whose
resolved closure contains NCP has exactly one surface entry for its complete key.
`contains_ncp` is derived from the resolved closure. It cannot be asserted or
cleared independently. An active root without NCP remains an ordinary discovery
record. It is neither an NCP surface nor an inactive exclusion. An inactive NCP
surface can remain inventoried only with the closed `retired` lifecycle and
independent evidence that it is not executable, CI-built, or activated.
An active or retired NCP surface cannot use the non-target `none` kind.

Shared declarations, root packages, and same-wire provider nodes can appear in
multiple coherent surface closures. Every occurrence must resolve consistently.
Orphaned roots or dependency edges, unreachable nodes, duplicate graph nodes or
edges, cycles, non-runtime or target-inactive edges, noncanonical node/edge order,
noncanonical path aliases, feature-closure drift, and graph or inventory bounds
reject. Discovery content-binds the subject, execution flags, deployment domain,
resolution-context document, ecosystem locator, actual package/build/deployment
manifests, surface-input-manifest digest, lock, runtime entry point, deployment
profile, namespaces, and resolved graph independently of the output descriptor.
It never content-binds `.ncp-consumer` or a digest derived from those output
bytes.

A bounded exclusion can classify only a discovered non-executable, non-CI-built,
non-activated, non-NCP root. It binds the discovery-record or tracked-content
digest, a closed reason, and a reviewer disposition. It cannot hide an eligible
NCP surface. Its closed union forbids surface identity, provider graph, locator,
subject, deployment, and namespace fields. All permitted fields are bounded and
validated before the record digest is recomputed. Built dependency closures or
SBOMs must agree with the inventory. A shared lock file is evaluated by
reachability from each surface root. It is not assigned one global release
identity.

Locator validation is ecosystem-specific. Cargo surfaces bind a package
`Cargo.toml`, the exact applicable `Cargo.lock`, and the selected target. A
synchronized Python mirror binds `.ncp-surface-inputs.v1.json`, the exact actual
Python package/dependency manifest named by it, `ncp/.mirror-ref`, and the exact
Python runtime module. `.ncp-consumer` is the output inventory descriptor and is
not a Python package-configuration input. One ecosystem's locator cannot satisfy
another ecosystem's rules.

One workspace or CI invocation can build and test multiple separate surfaces.
The independently discovered deployment domain scopes runtime-name collisions.
Equal local names in different domains do not imply one shared resource. Equal
names in one domain do. No single deployable target/dependency closure, runtime
entry point, activation or deployment profile, credential set, security manifest,
resolved transport namespace, state store, process, or plant session can activate
incompatible wires.
A shared package root does not authorize two wires in one deployable target or
process. Separate wire surfaces require distinct targets, activation profiles,
runtime entry points, deployment profiles, processes, credentials, security
manifests, routes, state stores, configuration, evidence, and plant-session
namespaces.

Capability isolation uses a complete, reviewed, closed classification. Any pair
that contains a privileged capability isolates by default. This rule also applies
to two surfaces with the same privileged capability. Explicit conflict pairs
include observer/assessor, commander/assessment-receiver, and
simulation-responder/plant-commander. They cannot share an activation profile or
runtime privilege boundary in one deployment domain. Role relabeling cannot
bypass the rule because isolation applies to the closed capability class. An
observer and assessor can share one deployment domain only when every activation,
runtime, deployment-profile, process, credential, security, route, state,
configuration, evidence, and plant-session boundary remains distinct.

A checker or repinner shall not force one release label across surfaces, omit a
discovered surface, or repin frozen 0.8 evidence as 1.0. It first validates the
complete pre-state with the same trusted-receipt policy used for the operation.
The caller supplies the exact installed
`ConsumerSurfaceInventoryStateHead` digest, expected descriptor digest, exact
authorized affected set, and independently authorized receipts for the exact new
subjects. Requested revision or artifact values cannot authorize themselves.

N07 shall replace the current fleet-wide compatible-line assumption in consumer
pin tooling. It shall verify each discovered surface's context-bound target-active
closure and exact provider pin independently. A migration fleet can contain
coherent wire-0.8 surfaces and coherent surfaces on the unreleased wire-1.0
candidate. That mixed inventory is not evidence that all consumers migrated.

The repinner operates on one repository-local inventory authority at a time.
`ConsumerSurfaceInventoryStateHead` binds the stable repository inventory-
authority scope, never-reused inventory-state incarnation, strictly increasing
state version, repository and source-tree identity, trusted descriptor-version
floor, closed inventory-authority status, exact
`ConsumerSurfaceInputManifest`, complete resolution-context and discovery-record
sets, output descriptor digest, subordinate
`trusted_subject_authorization_state_digest`, independently trusted subject
receipts, subordinate `trusted_scanner_authorization_state_digest`, exact current
scanner policy/version and scan-receipt eligibility, every current surface, and
prior inventory head. It excludes its own digest, its own selector/commit
receipt, and all later materialized or deployment evidence.

`TrustedSubjectAuthorizationState` and `TrustedScannerAuthorizationState` are
closed, content-addressed subordinate objects, not opaque caller-selected
digests. Their B03 schemas use one deterministic canonical encoding and bind the
inventory-authority scope/incarnation, repository, authorization domain and
policy/version. Subject state binds the sorted exact authorized subject-receipt
digests plus bounded authenticated grant/revoke evidence. Scanner state binds
the scanner principal, executable and resolved dependency-closure digests,
scanner policy/version, closed scan-receipt eligibility, and bounded
authenticated grant/revoke evidence. Unknown members, unordered/duplicate
entries, unknown eligibility, missing retained revocation, or a digest without
the retained canonical bytes rejects. Neither object has an independent
selector; its change is content of the winning inventory-head successor.

Each revocable subject or scanner authorization entry is keyed by its exact
authority scope, subject/scanner identity and never-used authorization-lineage
incarnation. Subject entries use
`ConsumerSurfaceInventorySubjectAuthorizationKey`; scanner entries use the
distinct `ConsumerSurfaceInventoryScannerAuthorizationKey`. Equal-looking field
values do not make those types interchangeable. Their closed installed state is
`GRANTED | REVOKED_TOMBSTONE | RETIRED`; only complete inventory-authority
retirement creates `RETIRED`.
Revocation changes the exact live key to its permanent tombstone. A later grant
must create a fresh lineage/key, preserve every predecessor tombstone, and bind
an explicit predecessor link plus freshness/inequality proof. A same-key
`REVOKED_TOMBSTONE -> GRANTED` edge, missing tombstone, or lineage reuse rejects.

`InstalledConsumerSurfaceInventoryStateSelector` is the sole currentness root
for that local inventory object. It binds the same scope and incarnation.
An authenticated parent-authority creation receipt allocates a never-used
incarnation and creates its selector in `UNINITIALIZED`.
`SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED` consumes that exact selector
once and installs state version 1. Genesis has no privileged `ACTIVE` default:
it binds the complete initial descriptor, pin, required-authorization and
scanner sets and applies the same
`ConsumerInventoryAuthorizationStatusWitness` function below. An empty
authorization map selects `ACTIVE` only when the complete required set is proved
empty and every descriptor meets the floor. Every successful transition increments both
the selector and state versions by exactly one and emits
`ConsumerSurfaceInventoryStateCommitReceipt` over the prior and installed heads,
selector version, state version, scope, incarnation, repository, and closed
transition kind. A missing selector, recreated or caller-supplied
`UNINITIALIZED`, post-use empty reset, rollback, storage loss, sibling genesis,
or reused incarnation disables repin and fences that inventory authority. It is
not a new genesis.

The closed transition union is
`SURFACE_INVENTORY_GENESIS_FROM_UNINITIALIZED |
SURFACE_INVENTORY_REPIN_COMPARE_AND_SWAP |
DESCRIPTOR_VERSION_FLOOR_ADVANCE |
TRUSTED_SUBJECT_AUTHORIZATION_GRANT |
TRUSTED_SUBJECT_AUTHORIZATION_REVOKE |
TRUSTED_SCANNER_AUTHORIZATION_GRANT |
TRUSTED_SCANNER_AUTHORIZATION_REVOKE |
FENCE_INVENTORY_AUTHORITY | RETIRE_INVENTORY_AUTHORITY`.
The root lifecycle axis is
`UNINITIALIZED | OPEN | FENCED | RETIRED`. The orthogonal authorization-status
axis is `ABSENT | ACTIVE | MIGRATION_REQUIRED_DISABLED |
AUTHORIZATION_REVOKED_DISABLED | RETIRED`; `ABSENT` is valid only with the
uninitialized root and `RETIRED` only with the retired root. Fencing changes the
root from `OPEN` to `FENCED` and preserves the exact prior authorization status
for audit; the root independently denies repin and installed use. Unknown,
default or inconsistent root/status combinations reject.

The descriptor-floor singleton lifecycle is `ABSENT | CURRENT | RETIRED`, keyed
by the exact inventory-authority scope and lineage. `CURRENT` binds the bounded
monotonic numeric descriptor-version floor. `RETIRED` preserves that final
numeric value inside a terminal tombstone; the integer does not become an enum.
Each surface-pin map entry is keyed by consumer repository, surface and
never-used pin lineage. Its lifecycle is `ABSENT | PINNED | RETIRED`; `PINNED`
binds the exact descriptor, subject-receipt requirements and discovery state,
and only complete authority retirement creates `RETIRED`. Typed absence means
exact-key nonmembership with retained no-reuse tombstones, not an omitted or
unknown scalar.

`RETIRE_INVENTORY_AUTHORITY` is one complete bulk closure, not a scalar-key
mutation. Receipt-free `ConsumerInventoryAuthorityRetirementFact` binds the
exact prior inventory head and selector version, authenticated owner retirement
cause, and canonical complete roots for the descriptor-floor, surface-pin,
subject-authorization and scanner-authorization domains. For each keyed domain,
it binds pairwise-disjoint state partitions whose union equals the exact prior
key set. Every `PINNED` surface and every `GRANTED` subject or scanner entry
enters permanent `RETIRED`; an existing `REVOKED_TOMBSTONE` or `RETIRED` entry
is preserved and validated. The authority status and descriptor-version floor
also enter `RETIRED`. Empty domains use explicit empty roots. A caller-selected
subset, one opaque key shared across domains, omitted tombstone, or mixed
unclassified entry rejects.

The same inventory-selector compare-and-swap installs the terminal root and all
subordinate partitions. Post-CAS
`ConsumerInventoryAuthorityRetirementReceipt` binds the fact, exact prior and
installed inventory heads, new selector version, generic inventory commit, and
the same per-domain roots and key-to-outcome bijections. Historical descriptor,
pin, grant, revoke, scan and discovery evidence remains retained, but no live
authorization entry remains under the terminal root. No later transition in
that incarnation can repin, grant, revoke, fence or return to a nonterminal
status.

The repinner starts from one explicit surface and independently resolves its
related repository/lock/NCP-provider closure group. The derived group must equal
the caller-authorized set. It prepares content-addressed post-state source
inputs, then independently rescans those staged manifests, locks, targets,
resolution contexts, target predicates, and runtime selectors. It updates the
surface input manifest first, derives the resolution and discovery records, and
constructs `.ncp-consumer` last. Only after complete post-state validation does
it construct a successor inventory head that updates the NCP-provider node,
top-level subject, trusted subject receipt, and discovery binding for every
affected surface while preserving every unrelated surface and independently
trusted receipt from the validated pre-state.

One repository-local durable transaction compare-and-swaps
`InstalledConsumerSurfaceInventoryStateSelector` and persists the exact
content-addressed staged set, descriptor, successor head, and commit receipt.
Descriptor-floor changes and grant or revocation of revocable trusted-subject or
scanner authorization also compare-and-swap this selector. They preserve
unrelated surfaces and pins. Every nonterminal transition constructs exact
`ConsumerInventoryAuthorizationStatusWitness` from the complete installed
descriptor, pin, required-subject and scanner-authorization sets. The witness
uses this total precedence:

1. If any installed descriptor version is below the trusted floor, status is
   `MIGRATION_REQUIRED_DISABLED`.
2. Otherwise, if any authorization required by an installed pin is absent,
   revoked or mismatched, or the current scanner authorization or eligibility is
   absent, revoked, mismatched or ineligible, status is
   `AUTHORIZATION_REVOKED_DISABLED`.
3. Otherwise, status is `ACTIVE`.

For each required subject-receipt digest, the witness requires exact equality of
authority scope, subject identity and authorization value to one unique current
`GRANTED` lineage. A retained revoked predecessor tombstone does not satisfy the
requirement and does not poison a later fresh regrant. Duplicate live matches or
a grant at a sibling lineage with a different value do not satisfy that exact
digest. The scanner match is likewise exact over authority scope, scanner
principal, executable and resolved-closure digests, scanner policy/version and
scan-receipt eligibility. Any mismatch or ineligible receipt selects the
disabled branch.

Explicit `FENCE_INVENTORY_AUTHORITY` and `RETIRE_INVENTORY_AUTHORITY` enter their
own irreversible root phases before this nonterminal function is considered. A
floor advance at or below every installed descriptor can therefore preserve
`ACTIVE`; one above any installed descriptor disables migration. Revoking a
subject required by an installed pin disables authorization. Revoking an unused
future preauthorization preserves current `ACTIVE` but blocks any future repin
that would require it. Scanner revocation disables because every accepted scan
depends on the current installed scanner eligibility. One grant cannot return
the inventory to `ACTIVE` while another required authorization is absent, and
no grant can override migration-disabled precedence. Every grant, revoke, floor
or repin successor binds the recomputed witness and exact complete-set roots.
Those transitions retain evidence but do not authorize deployment. Only a fully
validated successor whose total witness selects `ACTIVE` can enable later use.
This is the full atomicity claim. It does not make a mutable working tree, a
deployment, a remote Git ref, or another repository part of that transaction.
An implementation that uses an atomic Git-ref update as the local store must
prove the exact expected-ref compare-and-swap and tree identity. Otherwise,
materialization, commit, push, checkout, build, and deployment are later
receipted steps, and installed behavior remains **NOT RUN**. Cross-repository
migration is a staged set of independent local transitions and is never called
atomic. If one repository fails, no fleet-complete state exists; rollback or
forward repair requires a separately authorized transition from each installed
local head.

The transition reports the exact affected group and installed post-state head
and descriptor digests. A compare-and-swap mismatch, missing or extra receipt,
scope expansion, stale identity, failed rescan, changed staged bytes, or output-
descriptor self-dependency rejects. Native cutover still follows the complete
quiesced transition below.

Descriptor version is checked per repository against the trusted floor in the
installed inventory head. The baseline floor for the modeled consumer
repositories is version 2. A repository descriptor cannot lower its own floor
or restore a version-1 interpretation after version 2 is trusted. A future
lowering would require separate authenticated migration authority, an
independent scan, and a new trusted receipt. B01 models no such lowering
authority. A floor-only transition changes no provider pin but advances the same
inventory selector, version and receipt chain. A repin prepared against an older
floor or trusted-subject authorization state loses its compare-and-swap. A
deployment that keeps either currentness root in a separate store must prove an
exact conditional compare in the same local durable transaction; otherwise,
repin is disabled. A scan receipt must be eligible under the scanner
authorization and policy/version in the winning inventory head; this decision
defines no indefinitely valid historical-scan exception. Scanner revocation
before the repin makes it lose. Scanner revocation after a repin has a recorded
order and can disable/fence later use under the installed policy. Actual scanner
execution remains **NOT RUN** without exact evidence. Rollback cannot discard a discovered surface. A
`retired` lifecycle value is valid only when discovery proves that the target is
neither executable, CI-built, nor deployment-activated.

### Engram roles

ADR-001 separation is mandatory. The simulation responder and plant commander
use disjoint types, principals, manifests, endpoints, routes, state/replay
stores, credentials, and features. A responder-only build cannot publish action.

### Direct and gated plant modes

For one exact
`(AuthorityRealmKey, plant session kind, logical session ID, generation)`
identity, only one commander mode may hold a live body lease:

- **DIRECT_ENGRAM:** Engram is the enrolled NCP commander and publishes new NCP
  commands under its current Crebain-issued lease.
- **GATED_HALDIR:** Engram holds no NCP plant lease. It sends a Haldir-local
  signed intent. Haldir authenticates and evaluates that intent, then constructs
  a new NCP command under Haldir's principal, declaration, idempotency context,
  and current Crebain-issued lease.

Every native commander, including direct Engram and gated Haldir, owns a bounded
durable NCP outbox and an installed send-attempt protocol. It fixes the protected
command bytes, direct realm and complete session foreign key, stable idempotency
key, exact installed ADR-007 body freshness grant/slot, stream identity, one
transport-acceptance cutoff no later than the body grant, command TTL, live body
lease when required, authorization/fail-safe freshness and handoff bounds. That
cutoff is the conservative minimum of the mapped absolute bounds and
`checked_add(local_outbox_release_instant,
profile_max_transport_duration)`; the profile value is a duration, never an
absolute timestamp. One earlier attempt-start cutoff subtracts a qualified worst-case duration
through endpoint acceptance. START durably installs the attempt and checks that
earlier cutoff plus current commander security/session/generation/transport-gate
epoch; it is necessary but not delivery evidence.

The qualified transport endpoint atomically checks the unchanged acceptance
cutoff and gate epoch at actual acceptance and emits a queryable receipt over the
exact attempt/bytes/key/time. Equality or later time cannot accept. Timeout,
cancellation or a returned future without authenticated no-acceptance remains
ambiguous. Security/session/retirement cuts fence the transport gate; acceptance
proved before the fence may resolve later, and an old epoch cannot accept after
it. A retry uses the same bytes/key/grant and deadlines; restart, retirement,
drain and reconnection cannot refresh them. Haldir uses the concrete ADR-008
machine. Direct Engram must implement an equivalent Engram-owned outbox, gate,
attempt, acceptance and disposition machine rather than treating a void function,
socket write, broker enqueue or fire-and-forget publish as durable proof. A
low-level `publish_command` primitive is non-authorizing unless this machine wraps
it. The body independently enforces the body-clock grant deadline at admission,
application, watchdog and fail-safe boundary, plus position-slot idempotency, so
honest sender deadlines are not receiver replay defense.

Direct Engram and Haldir use one reviewed
`NcpCommanderPublicationCore` algorithm for immutable outbox construction,
two-cutoff derivation, attempt installation, endpoint query and ambiguity
closure. Reuse stops at the algorithm boundary. A sealed role adapter supplies
the exact commander principal/declaration/lease/freshness grant, store domain,
gate type and receipt types. Direct Engram and Haldir keep disjoint selectors,
state heads, credentials, idempotency namespaces and typed receipts. A generic
core value, role tag, cast, serialized union or copied Haldir receipt cannot make
Engram state current, and the reverse cannot occur. The core has no raw send
method that bypasses attempt installation or endpoint acceptance evidence.

The sealed role adapter also supplies the direct `AuthorityRealmKey`. The core
compares it on every request, outbox item, gate, attempt, endpoint receipt,
disposition, and body query. A role tag or adapter cannot rebind a core object to
another realm.

The frozen current `HaldirIntentV1` cannot carry this native-1.0 evidence. Its
mandatory `NcpSourceRefV1` contains only source key, stream epoch, and sequence;
it omits `AuthorityRealmKey`, session kind and generation,
declaration/content identity, protected transfer, and explicit absence. Do not
reinterpret or expand V1. Retain it for its exact historical/local compatibility
surface and add a separately versioned signed
`HaldirIntentV2`/`haldir.intent.v2` contract for the native-1.0 gated path. The
native profile and route reject V1 and every version downgrade.

`NcpSourceRefV2` is Haldir's exact, non-lossy typed embedding of the ADR-004
`NormativeSourceRef`. Its direct `AuthorityRealmKey` is the first member of the
full `(AuthorityRealmKey, session_kind, logical_session_id, generation)` origin
foreign key; the three session coordinates follow it once, followed by the exact
declaration, stream position, producer, and content identity defined by that
portable reference. It cannot be constructed
from V1, a route, a bare position, arrival time, command-own-stream coordinates,
or a receiver-local receipt. `HaldirIntentV2`, every watermark, and every
source-present decision/publication projection uses this exact type without
dropping the realm.

Before Engram can construct V2, the Haldir policy authority installs and exports
an idempotent `HaldirIntentFreshnessGrant` and installation receipt. The grant
binds the exact direct `AuthorityRealmKey`, complete plant-session foreign key,
authority/endpoint/security, Engram transport and signing principal, intent
route/audience, intent stream epoch, bounded non-overlapping slots, allowed
action/mode ceiling, Haldir clock incarnation, issue tick, exclusive maximum
not-after tick and capacity. Haldir selects the grant ID/range/deadline; retry or
reply loss queries the same result. The grant is freshness evidence only and
grants no Haldir permission or NCP authority.

The V2 signature binds the direct realm, complete session foreign key, exact
grant, installation receipt and selected slot.
Its effective Haldir-clock deadline is
`min(grant.maximum_not_after,
checked_add(grant.issue_tick, canonical_requested_validity_duration))`.
`controller_t_ns` is audit-only, and Haldir receive time never refreshes the
deadline. Engram owns a bounded durable intent outbox with immutable bytes/key,
an earlier attempt-start cutoff and the unchanged Haldir ingress-acceptance
cutoff. The qualified Haldir endpoint atomically checks grant/slot/deadline and
its transport gate at acceptance and installs the intent reservation. Timeout,
cancellation, broker enqueue or local return without the endpoint receipt is
ambiguous. Retry preserves bytes/key/grant/slot/deadlines. Source admission,
policy ALLOW and publication handoff remain no later than the same effective
intent deadline. V1's signed controller timestamp and receive-relative validity
cannot satisfy these native requirements.

The closed Engram intent-transport disposition is
`ACCEPTED_BY_HALDIR_INTENT_INGRESS_BOUNDARY |
REJECTED_BEFORE_HALDIR_INTENT_INGRESS_ACCEPTANCE |
AMBIGUOUS_AFTER_HALDIR_INTENT_TRANSPORT`. Acceptance binds the exact Haldir
ingress reservation commit, direct realm, and complete session foreign key and
proves neither source admission, policy ALLOW nor NCP publication. Rejection
requires authenticated proof that the endpoint did not install the reservation.
Timeout, cancellation or sender-local failure without either proof is the
ambiguous branch and retains the same-key query/resolution obligation. No alias
can call broker acceptance, socket write or Haldir process receipt an
ingress-boundary acceptance.

V2 contains exactly one closed source union:

- `SOURCE_PRESENT` carries one indivisible portable `NcpSourceRefV2` projection
  of `NormativeSourceRef` and matching `ProtectedOriginTransfer`, plus a bounded
  canonically ordered set of full `NcpSourceRefV2`/matching-transfer watermark
  entries; or
- `SOURCE_ABSENT` carries the exact profile-permitted absence reason and forbids
  primary source, transfer, dummy/sentinel source, and source-derived watermarks.

Each watermark is a producer-declared resolved upstream-input position, not
delivery order, authority, or proof of computation/causality. Haldir admits each
full reference/transfer independently before any policy use. The V2 canonical
CBOR preimage and controller signature cover the direct realm, union
discriminant, every portable identity, ordered watermark, attachment digest,
intent/session context, and all existing action/admission fields. Every primary
and watermark source realm must equal the intent and plant-session realm.
Cross-realm origin transfer requires an explicit terminating trust gateway that
creates a new realm-local portable identity and preserves the old identity only
as non-authorizing provenance. Native V2 performs no implicit cross-realm
redisclosure. H01's total conversion and H02's Gate decoder consume the same V2
type; no adapter-local shadow struct is allowed.

When a V2 intent carries a portable `NcpSourceRefV2`, it also carries a bounded
Haldir-local `ProtectedOriginTransfer` in one closed form.
`EXACT_ORIGIN_TRANSFER` binds the exact original protected producer envelope and
declaration/security evidence. `TRUSTED_PROJECTED_ORIGIN_TRANSFER` instead binds
the protected projected frame plus the receiver-independent ADR-004
`TrustedProjectionRecord` from the portable original identity through the exact
projector/policy/transform/audience. It never carries Engram's or another
receiver's `TrustedProjectionProvenance`.
Both forms directly bind the same `AuthorityRealmKey`, intended Haldir
policy-authority intent-ingress audience, intent and plant-session context, and
transfer-policy digest. The integrated policy authority strictly decodes and
independently verifies the applicable producer or trusted-projector chain,
direct-realm equality and transfer authorization, then constructs receipt-free
`HaldirIntentSourceAdmissionFact`. A policy-state successor binds that fact under
the same currentness root as intent replay and decision. After the
compare-and-swap, the generic commit and
`HaldirIntentSourceAdmissionReceipt` bind the fact, prior/installed heads and
selector version. For a projected transfer, the authority then creates its own
`TrustedProjectionProvenance` from the record digest and that installed local
receipt. A losing fact creates no receipt or provenance.
The projected form remains labeled projected and
never claims unavailable original bytes. Engram's signature authenticates the
intent/transfer but cannot replace the underlying proof or widen its audience.
For native 1.0, the original protected envelope or trusted projection record
must already authenticate the exact Haldir policy-authority ingress audience.
Engram cannot
self-author a redisclosure policy, and no after-the-fact audience widening is
accepted. The transfer-policy digest selects only Haldir's bounded acceptance
rules; it grants no disclosure authority.

This source-ingress capability belongs to the Haldir policy authority's existing
authenticated local-intent surface, not the NCP commander surface. It accepts
only an intent-bound attachment and exposes no observer attach, subscription,
query, wildcard route, or generic read transport. Therefore it does not add an
observer role or let policy-authority or commander credentials acquire observer
access. The integrated policy core accepts the source-bearing intent only when
its portable reference matches the exact locally admitted origin or trusted
projection. Missing local evidence rejects or holds the intent; it cannot
silently become explicit source absence. The policy decision passes only the
unchanged portable reference to the commander, never the protected transfer or
Haldir-local receipt. The Haldir command likewise carries only that portable
reference. Crebain and each downstream observer resolve the same portable
identity in their own lineages. Standalone Gate keeps the same ownership in its
separate deployment mode.

Haldir never forwards or re-signs Engram NCP bytes as if identity or authority
transferred. Crebain admits/applies/disposes both modes and remains the sole body
authority.

### Body-coordinated handover

Mode is an attribute of the current body-issued authority term, not an
application toggle. The term, handover fact, every lease/stream retirement and
new grant directly bind the same immutable `AuthorityRealmKey` and complete
session foreign key. Handover uses ADR-006:

`ACTIVE(old mode/holder) -> STOP_OLD_ADMISSION -> HOLD_QUIESCING ->
RETIRE_OLD_LEASE_AND_STREAM -> PERSIST_HIGHER_TERM ->
GRANT_NEW_MODE/HOLDER -> DECLARE_NEW_STREAM -> ACTIVE`.

No old and new lease are live concurrently. Delayed old commands reject on exact
realm, session generation, lease term/ID/holder, declared stream epoch, and
sequence. A handover cannot change realms. Moving a deployment to another realm
requires terminal retirement and a new realm/session lineage. On crash
ambiguity, Crebain restores into HOLD/reconnecting or retires the session
generation; wall-clock lease time never revives authority.

### Galadriel-to-Haldir composition

The optional assessor extension is push-only, default-off, distinctly
credentialed, and limited to advisory record handling or a Haldir-owned
deny-tightening mapping. Handling and permission are different types:

```text
assessment_handling = RECORD_ONLY | ELIGIBLE_RESTRICTION
permission_effect(RECORD_ONLY or advisory absence) = NO_ADDITIONAL_RESTRICTION
effective_permission = local_policy MEET permission_effect
```

`NO_ADDITIONAL_RESTRICTION` is the meet identity/top. In the current binary
lattice its value is `ALLOW`, but it preserves the local decision and is never a
grant from assessment. Required absence maps to the exact profile-owned deny
element. Every eligible restriction is less than or equal to local permission;
unknown or inconsistent handling/effect pairs reject. The exact handling,
mapped effect, profile rule, and meet result are bound in Haldir's admission,
disposition, and installed policy head.

No assessment can create permission. However, lifecycle changes can widen
permission by removing a prior deny. Therefore retraction, expiry, extension
disable, base-policy widening, override, or restart reconstruction requires an
explicit authenticated monotonically versioned Haldir policy transition and
audit record. The configured absence posture may be advisory/no-additional-
restriction or deny-new-missions; it may not turn missing evidence into a new
grant.

Haldir acknowledges each verified assessment with the authenticated bounded
disposition defined by ADR-008. Galadriel may retry using the exact assessment
identity, but missing, delayed, rejected, or overflowed disposition cannot be
interpreted as `APPLIED_DENY`. The acknowledgement reports Haldir-owned policy
state and creates no body authority.

### Read-only and indirect components

Prisoma and Galadriel observers receive only bounded ADR-004 read grants. An exact
grant may expose a command proposal without granting action publication. They
cannot publish, declare streams, mutate plant/session/stream/security/authority
lifecycle, acquire authority, ESTOP, or issue dispositions. Gaps and missing
variables remain explicit. Proposal, admission, applied-boundary state,
authenticated measurement delivery, and physical truth/effect claims remain
separate.

The B01 local model connects the observer-read stages as follows:

`current bounded capability -> sealed preflight decision -> exact release-time
currentness recheck -> delivery -> receiver admission -> immutable historical
capsule`.

The capability is the current bounded read authority. A
`SealedObserverReadAuthorizationDecision` binds the exact preflight result, but
it has no release or future authority. Release requires an exact recheck of the
same capability and currentness inputs. Receiver admission then binds the exact
delivered bytes, admitted cut, and receipt. The delivered admitted capsule is
immutable historical evidence only. It cannot authorize a later read, retry, or
release.

A deterministic extraction contract and receipt bind each local synthetic
observation to retained admitted bytes. The current bridge covers seven samples
in the `A`, `D`, `L`, and `V` slots. These names are local test coordinates; NCP
does not assign scientific meaning to them. The Prisoma-language qualification
remains blocked because the inventory contains no eligible genuine native-1.0
language channel. The blocked path makes zero estimator calls.

Every Galadriel and Prisoma observer grant, admitted frame, source resolution,
semantic segment, capture event, row provenance, dataset/manifest/index/
publication identity, and role receipt directly retains `AuthorityRealmKey` and
the exact consumer foreign key. A consumer-owned transform or aggregation can
add semantics but cannot erase or replace the provider realm. Rows from distinct
realms remain distinct capture roots and cannot be pooled as one source lineage,
even when all other provenance and values are equal.

The local selector resource projection also keeps ownership explicit. A selector
can `WRITE` or `RESERVE` only a resource that it owns. It can use a foreign
resource only as a conditional comparison. The derived mutation set must equal
the mutating effect set. Each joint-transaction (JTX) profile and its event
participants form a bijection, and each participant has a nonempty local write
footprint. This is a local structural closure check. It is not installed
interoperability, concurrency, durability, identity, independent-review, or
release evidence.

The bridge and resource projection use local synthetic models. Live issuer
cryptography, transport-principal binding, external revocation, installed
Galadriel or Prisoma interoperability, genuine Prisoma-language qualification,
role qualification, and every external or release gate remain **NOT RUN**.

pid-rs operates on consumer-supplied protocol-neutral values. Its estimate can be
one input to application policy but has no authenticated actor, lease, command,
or outcome meaning.

NCP defines no runtime, export, observation, control, release, or
documentation-import edge to or from Cortexel.

## Rejected alternatives

- Make NCP depend on, orchestrate, or qualify consumer applications.
- Require NCP for any component's standalone core.
- Let Engram direct and Haldir gated commands contend under one live term.
- Let Haldir forward Engram command bytes or issue body leases/dispositions.
- Let Galadriel encode `ALLOW`, command, ESTOP, or reuse observer credentials.
- Put Prisoma, pid-rs, or Cortexel in the plant command path.
- Add consumer-specific fields to stable NCP messages.
- Force every adapter in one repository to claim one release identity, thereby
  hiding or silently repinning a parallel migration surface.
- Use `.ncp-consumer` as an input to a key, context, discovery record, or scanner
  digest that the same descriptor contains.
- Call a set of independent repository/file/deployment updates one atomic fleet
  repin.
- Infer installed compatibility from copied protocol files, manifests, or local
  tests.
- Reinterpret the frozen weak `HaldirIntentV1` source fields as native-1.0
  evidence or use empty/sentinel V1 values as source absence.
- Infer an authority realm from route, deployment, surface, session, generation,
  parent ancestry, or local configuration.
- Merge or replay same-principal/session/generation/source/bytes state across two
  `AuthorityRealmKey` values.

## Illustrative gated flow

```json
{
  "authority_realm_key": {
    "server_authority_principal_id": "ncp-authority-a",
    "stable_realm_id": "realm-a"
  },
  "intent_id": "80ad94de-e7b7-4b31-8b69-119d89a97511",
  "issuer": "engram-intent-a",
  "audience": "haldir-gate-a",
  "plant_session_generation": "00000000-0000-4000-8000-0000000000a2",
  "requested_effect": "mission-step",
  "expires_at_utc_ms": 1784200030000
}
```

After local ALLOW, Haldir creates a separate NCP `CommandFrame`; the intent is
audit correlation only and is never the command identity or lease.

## Invalid or hostile example

```json
{
  "kind": "command_frame",
  "identity": {
    "principal_id": "engram-commander-a"
  },
  "forwarded_by": "haldir-gate-a",
  "authority": {
    "issuer_principal_id": "haldir-gate-a"
  }
}
```

Haldir cannot transfer Engram identity or self-issue Crebain authority.
The hostile command also omits the required direct `AuthorityRealmKey`.

## Actors and state transitions

The composed model has orthogonal state:

- authority realm: one exact immutable `AuthorityRealmKey`;
- session kind: simulation or plant;
- plant mode: none, direct Engram, or gated Haldir;
- body lifecycle: init, hold, active, estop, closing, retired;
- current body lease: absent or one exact holder/term/ID;
- command stream: absent, live, or retired;
- Galadriel assessment mode: disabled, record-only, or deny-required;
- observer grants: independent bounded attachments; and
- research/visualization sinks: absent or read-only export consumers.

Only Crebain serializes plant mode/lease state. No observer grant or observer-role
process directly participates in body admission or widens permission. Only the
separately authenticated assessor role can deny or tighten Haldir's pre-command
local decision; it cannot create a command, body admission, lease, or authority.
Indirect sink state does not participate in action admission.

No transition changes the authority-realm axis. Realm retirement and enrollment
create distinct composed machines, even when every textual session and principal
identifier is reused.

## Bounds and resource behavior

Realm keys, adapters, principals, endpoints, manifests, leases, intents,
assessments, queues, state stores, retries, handover time, observer grants,
captures, run logs, and exports are finite. Optional components cannot borrow
reserved action/control capacity or become startup prerequisites for unrelated
modes. Per-realm partitions remain under finite deployment-wide limits, so realm
labels cannot multiply resource capacity.

The descriptor parser applies byte, item, graph, path, context, and record limits
before canonical serialization, hashing, graph traversal, or semantic allocation.
Every discovery variant has a closed field set. Unknown or surplus fields cannot
consume unbounded resources or acquire surface meaning.

## Threat and hazard analysis

The decision addresses split brain, identity laundering, stale delayed commands,
simulation authority confusion, deny lifecycle widening, observer actuation,
extension route confusion, research feedback, and hidden dependency cycles.

Direct realm binding also addresses a deeper ABA case: two authority domains can
reuse the same application principals, textual session ID, opaque generation,
stream position, intent ID, and payload bytes. Without the server-principal/
stable-realm tuple in every portable object, a consumer or handover service could
merge valid but unrelated histories. Realm validation therefore precedes every
runtime topology, source, replay, policy, outbox, handover, and capture lookup.

The strongest composed counterexample is: a body/commander handover overlaps a
Haldir restart that loses applied deny state while a delayed old command remains
buffered. If exclusivity is checked only during configuration, deny state fails
open, or the body checks only wall-clock lease expiry, every component can appear
locally plausible while the old authority chain actuates. The ADR-006 exact fence,
body serialization, durable/non-widening Haldir recovery, and continuous mode
invariant jointly reject that trace.

Prisoma and pid-rs must not be inserted into this counterexample's command path;
their required property is precisely that they have no such edge.

NCP does not certify physical safety or a universal safe action. It does not
establish scientific calibration, field validation, or command usefulness.

## Formal properties

A bounded TLA+/state-machine composition shall include two commanders, two body
generations, several lease terms, opaque stream epochs, delayed/reordered/
duplicated commands, crash at every handover step, Haldir restart, Galadriel
mode/TTL/replay, observer load, and state-store uncertainty.

Required invariants:

- Every realm-scoped runtime and portable evidence object named in this ADR has
  one direct non-default `AuthorityRealmKey` in its canonical bytes and digest.
  Realm-independent package, stable-core, extension-contract, and surface
  identities do not satisfy that member.
- Direct realm equality holds across authenticated ingress, default-deny
  manifest, audience, route projection, session descriptor/transcript, source
  reference/transfer, grant/lease, policy state, outbox/transport state,
  handover, disposition, observer/capture state, and every evidence projection.
- Missing, unknown, default, wildcard, retired, mismatched, route-only,
  ancestry-only, or locally inferred realm data causes no replay mutation,
  authority decision, policy evaluation, publication, handover, capture
  admission, callback, or side effect.
- The consumer foreign key is exactly
  `(AuthorityRealmKey, session_kind, logical_session_id, generation)`.
  Galadriel and Prisoma projections, captures, semantic registries, datasets,
  publications, and role receipts cannot drop or rewrite it.
- Two inputs with identical principal, session kind, logical session ID,
  generation, source/declaration/position, operation, digest, and bytes but
  different authenticated realm contexts never merge, deduplicate, resume,
  inherit state, or satisfy one another's receipts.
- An exact command, intent, source, disposition, or capture byte sequence replayed
  at another authenticated realm rejects before runtime lookup. A separately
  valid object with every non-realm member equal but either realm-key coordinate
  changed uses distinct topology and consumer lineages.
- `NcpSourceRefV2` directly and losslessly retains the realm-bearing
  `NormativeSourceRef`; V1, a bare position, route, local receipt, or a V2
  projection without realm cannot substitute.
- at most one commander holds live plant action authority;
- every admitted command matches the exact current realm and body fence;
- every handover fact, old/new lease, stream retirement/declaration, term, and
  receipt has the same direct realm. A realm change requires terminal retirement
  and new enrollment, not handover;
- every direct or gated command send has a durable pre-send attempt under the
  commander's current security/session/generation/gate and two non-extendable
  cutoffs. START checks the earlier feasibility cutoff but is not success. The
  transport endpoint checks the unchanged acceptance cutoff and gate at actual
  acceptance and emits a queryable receipt; equality/later cannot accept, and
  timeout/cancel without endpoint proof is ambiguous. Both cutoffs are no later
  than every mapped command, lease, authorization and handoff absolute bound plus
  checked release-instant-plus-profile-duration. Retry/restart/retirement cannot
  refresh either;
- direct Engram and Haldir can share only the sealed
  `NcpCommanderPublicationCore` algorithm. Their persisted heads/selectors,
  principals, gates, idempotency namespaces and receipts are different types.
  Cross-role state, receipt, key or adapter substitution rejects before send;
- every remote HOLD/ESTOP body-side effect binds an installed body-issued
  freshness grant and exact publisher-position slot, derives one body-clock
  absolute deadline, and consumes the installed pre-cut reservation through a
  severity-aware boundary order. Exact replay creates no durable attempt or
  effect; same-slot equal/lower content cannot invoke again, and HOLD-to-ESTOP is
  the only upgrade. Publisher-local time and envelope-derived content keys grant
  nothing;
- no permission widening occurs without an authenticated Haldir transition;
- a native-1.0 gated intent is V2 and has exactly one signed
  `SOURCE_PRESENT`/`SOURCE_ABSENT` branch; V1, weak references, dummy absence,
  unmatched transfer/reference, altered attachments, and lossy watermark
  substitution reject;
- that V2 signature also binds one installed Haldir-issued intent-freshness grant,
  receipt, direct realm, complete session foreign key, and exact slot. The
  Haldir-clock deadline derives from grant issue time, grant maximum and
  canonical requested validity; sender/receive time cannot refresh it. Engram
  uses a durable intent outbox with start and Haldir endpoint-acceptance cutoffs,
  and source admission, ALLOW and handoff cannot outlive the same deadline;
- no simulation grant satisfies plant authority;
- an observer read grant never satisfies action publication authority;
- NCP exposes no runtime, observation, control, evidence, release, or
  documentation-import edge to or from Cortexel;
- no observer grant, observer-role process, Prisoma, or pid-rs state changes body
  admission or widens pre-command permission; the separate assessor can only
  tighten Haldir's local decision;
- every discovered executable, CI-built, or deployment-activated NCP consumer
  repository/root/target-kind/target/default-feature-mode/effective-feature-set/
  role/activation-profile/resolution-context-digest key has one explicit coherent
  provider identity and one matching canonical resolution-context document;
- every stable surface, closure-root, and privilege-boundary identity retains its
  complete canonical digest;
- every retained graph edge binds its canonical target predicate to the same
  resolution context as its surface, and that predicate evaluates true in the
  context;
- every accepted descriptor version meets the trusted floor in its installed
  repository-local inventory head;
- every candidate or immutable provider subject matches an exact independently
  trusted source, typed contract identity, revision, artifact, and subject-kind
  receipt;
- descriptor-floor, subject-authorization, scanner-authorization and repin
  changes have one order through the installed repository inventory selector.
  A repin prepared under an older floor, subject authorization or scanner
  authorization loses; no separate check-then-CAS store can authorize it;
- incompatible wire surfaces cannot share one deployable dependency closure,
  process, deployment profile, or plant session in one deployment domain;
- a repin changes only its compare-and-swap-bound, explicitly authorized closure
  group in one installed repository-local inventory head and preserves all
  unrelated subjects and receipts;
- `.ncp-consumer` is an output leaf: no surface key, resolution context,
  discovery record, scanner input, or surface-input manifest that it contains
  binds its bytes or digest;
- a build/package artifact bound by discovery excludes the output descriptor and
  its digest; the resolution context binds inputs, not that resulting artifact;
- a cross-repository migration has no atomic fleet state and cannot become
  complete from a partially installed set;
- extension overload cannot block body fail-safe/disposition work; and
- every accepted command has a body disposition/query path.

## Migration

Provider ADRs and rebaseline land first. Consumer tasks then implement separate
optional adapters against exact immutable NCP commits. Engram migrates responder
and commander roles separately; Haldir adds a native commander and separate
assessment receiver; Galadriel adds observer and assessor roles; Crebain adds the
body and separate producers; Prisoma adds read-only capture. pid-rs and Cortexel
receive no NCP peer role or aggregate qualification receipt.

The native migration adds direct `AuthorityRealmKey` members to every
realm-scoped runtime and portable evidence schema above. All consumers migrate
their foreign keys to
`(AuthorityRealmKey, session_kind, logical_session_id, generation)` before they
accept native evidence. Mandatory cross-project mutants keep principal, session,
generation, stream/source position, operation, digest, and bytes equal while
changing only the authenticated realm context. Other mutants drop realm from
`NcpSourceRefV2`, a Galadriel or Prisoma projection, a Haldir grant/evaluation/
publication receipt, a handover fact, or a runtime namespace. All reject before
state mutation.

The provider shall version the consumer descriptor and pin tooling before any
parallel consumer task starts. Haldir, Galadriel, Crebain, and Prisoma then record
each retained executable wire-0.8 surface and each native-1.0 surface separately.
Engram records its native-1.0 surfaces. Its frozen wire-0.8 inventory is currently
non-executable historical migration input, not a consumer surface; if a build or
CI path restores it, discovery requires a separate entry. Omission of a discovered
legacy surface is a pin-check failure, not a migration shortcut.

Haldir preserves `HaldirIntentV1` bytes and meaning. H01 adds V2 in parallel and
H02 moves only the native-1.0 gated route/profile to V2. Engram E06 emits only V2.
No migration rewrites stored V1 evidence, aliases V1 to V2, or accepts V1 on the
native route. Canonical-CBOR/signature fixtures cover both versions independently.

The native cutover is a complete body-profile transition, never dual-stack
admission. Crebain enters HOLD, closes the v0.8 admission plane, stops old
listeners/publishers/principals, drains or rejects bounded in-flight queues, and
persists terminal v0.8 deployment state before opening native 1.0 admission with
an explicit installed `AuthorityRealmKey`, fresh session generation,
security-state digest, stream epochs, and exactly one body lease. Rollback is
another complete quiesced cut with a fresh compatible v0.8 session/stream
incarnation; it never reopens pre-cutover listeners, replay state, queues, or
traffic. Generation and epoch UUIDs are compared only for exact equality;
persisted authority/deployment terms provide their separately defined ordering.
A realm move is not rollback or cutover within one lineage.

## Operational recovery

Each mode has explicit startup diagnostics and no hidden fallback. Missing
optional components leave their mode unavailable without breaking standalone
cores. Handover ambiguity stays HOLD and is reconciled through body queries.
Assessment uncertainty follows non-widening Haldir policy. Observer/capture/export
gaps remain visible.

Recovery restores only state whose direct realm equals the installed endpoint,
selector, manifest, and session descriptor. It never rehomes a lease, intent
slot, source reference, policy latch, outbox obligation, disposition, observer
history, or capture segment into another realm.

## Compatibility and rollback

Cross-repository work is not atomic. Each repository commits and pushes one
passing slice, then pins the exact prior provider/consumer subject. Rollback uses
complete compatible cuts and preserves immutable 0.8 history. No movable `main`
pin, copied file, or manifest-only repin establishes migration.

## Open questions

<a id="ncp-b01-selector-allocation-adr-011-v1"></a>

Exact extension identities, package feature names, and consumer inventory allocations remain implementation inputs. Topology ownership, handover, package coherence, and fail-closed consumer qualification rules are closed.

Future B03 allocation names and reviewed exclusions will be maintained in the
[external selector-allocation inventory](selector-allocation.authoring.v1.json)
under this stable ADR anchor. The current inventory is incomplete, has not been
reviewed, and contains no allocation or exclusion rows. It is coordination
evidence only and grants no release or gate status.

## Ten-lens review

1. Semantics: every edge, payload, role, and owner has one meaning.
2. Security: realm and actor identities cannot transfer through forwarding or
   optional adapters.
3. Safety: Crebain remains sole body/final software actuator authority.
4. Lifecycle: handover, restart, TTL, mode, and absence are explicit.
5. Resources: optional roles cannot starve control or become hidden prerequisites.
6. Migration: provider-first, per-surface exact pins avoid hidden adapters,
   private forks, and mixed runtime wires.
7. Science: command proposals, dispositions, simulation/PID/observer/figure
   outputs retain distinct non-claim boundaries.
8. Operations: standalone modes, recovery, diagnostics, and incident ownership
   are executable.
9. Evidence: composed faults and nine exact NCP role receipts remain distinct;
   pid-rs and Cortexel receive no peer receipt.
10. Governance: each adapter/schema/key/namespace/support boundary has an owner.

## Ratification record

The non-normative decision registry records exact review evidence and derives the
current decision status. This invariant text does not change when review state
changes. Exact Fable 5 advice is challenge input only and does not satisfy a
reviewer role.
