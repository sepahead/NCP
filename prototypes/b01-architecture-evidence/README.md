# B01 preliminary architecture evidence

This directory is a quarantined, non-normative counterexample-discovery and
resource-screening prototype for the eleven **PROPOSED** NCP 1.0 architecture
decisions. It does not accept an ADR, create
`contract/decision-registry.v1.json`, change the current wire, start the
canonical `formal/` program, prove implementation refinement, satisfy
independent review, or authorize release.

The current candidate remains unreleased and release-blocked `1.0.0-rc.1`,
wire `1.0`, compact contract hash `163acc57d8a62b66`, and complete normative
digest
`9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90`.

## Purpose

The B01 ratification gate requires proposed models to have no obvious
counterexample under declared bounds and preliminary resource estimates to fit
declared maxima and local cryptographic screens. The later F01/F02 program still
owns canonical TLA+, large configurations, liveness/fairness, refinement, SMT,
Kani, traces, and independent review.

This prototype therefore asks narrower questions:

1. Can a bounded direct-Engram to gated-Haldir handover, body restart, stream
   restart, lease expiry, hostile fence substitution, and reordered delivery
   admit a stale command?
2. Can Galadriel deny expiry, retraction, disable, restart, record-only input, or
   an unauthorized policy action widen Haldir permission without an
   authenticated monotonically versioned transition?
3. Can a complete v0.8-to-native-1.0 cutover and rollback overlap wire admission,
   activate before quiescence, or revive a pre-cutover incarnation?
4. Do the finite formulas have satisfiable ordinary-success premises, and do
   guard-removal mutations change their registered results?
5. On this machine and fixed corpus, do separate prototype queues remain
   structurally isolated, bounded parsing reject exact over-limit cases, a
   bounded journal preserve required recovery evidence, and real Ed25519
   verification remain inside a declared preliminary screen?
6. Do exact observer-read guards and versioned consumer-surface inventory reject
   operation confusion, stale grants, dishonest projections, omitted roots,
   mixed-wire deployable closures, and untargeted repins while accepting valid
   shared locks and shared same-wire provider nodes?
7. Do freshness deadlines, acceptance linearization, protected-command
   idempotency, restrictive effects, Active watchdogs, retirement drains, and
   Haldir intent freshness remain fail-closed under bounded hostile mutations?

The strongest permitted result is:

> No counterexample was found within the recorded finite models, decision,
> observer-authorization, observer-capture, freshness-and-acceptance, and fixed
> local resource probes; every registered executable mutant was detected, every
> registered hostile input was rejected, and every registered invariant and
> semantic-contrast witness was reached.

## Bounded state enumerator

[`model_check.py`](model_check.py) exhaustively explores three finite models.

### Composition model

The composition state includes:

- direct Engram or gated Haldir mode;
- body phase `ACTIVE`, transfer HOLD, restart HOLD, or expired-lease HOLD;
- a durable transfer latch with exact source, target, base generation, base term,
  base stream position, and phase `REQUESTED`, `QUIESCED`, `RETIRED`,
  `TERM_PERSISTED`, or `COMPLETE`;
- one current body term;
- three deliberately non-chronological generation labels and three stream
  labels, compared only by equality in the correct model;
- zero or one live holder;
- up to two in-flight commands;
- applied/rejected identities; and
- a bounded handover/restart history.

The action set includes legitimate direct and gated issue, body-coordinated
handover through every durable phase, restart/resume at every in-progress
transfer phase, clean/current-holder restart recovery, stream restart, lease
expiry, arbitrary delivery order, and hostile commands differing in exactly one
of generation, term, stream epoch, holder, or simulation/plant domain.

Required non-vacuity witnesses include:

- a fresh command applies;
- hostile and stale commands arrive and reject;
- two commands are simultaneously in flight;
- a formerly valid delayed command rejects while a currently valid fresh command
  remains pending after a handover or restart fence changed;
- direct-to-gated handover completes;
- restart preserves and resumes the exact request, quiesced, retired, and
  term-persisted transfer phases without changing the session generation;
- clean and completed-transfer restart recover only the current holder;
- restart or expiry recovery completes; and
- each independent fence and simulation-domain rejection is reached.

The model kills mutations that omit or order generation, omit term/epoch/holder,
admit simulation as plant, construct a Haldir command under Engram identity, or
overlap old/new holders. Separate crash-phase mutants erase or roll back each
durable transfer phase. Other mutants complete before quiescence, retirement, or
term persistence, or reactivate the old holder.

### Galadriel/Haldir deny model

Permission is represented as:

```text
effective_allow = local_allow AND NOT applied_deny
```

`EXPIRE`, `RETRACT`, and `DISABLE` request removal but retain the applied deny.
Only an authenticated Haldir widening action with a strictly greater policy
revision and completed recovery dwell removes it. Restart preserves the applied
deny. `RECORD_ONLY` is the identity operation. Deny activation independently
requires authenticated raw evidence, an authenticated profile, an independent
profile issuer, valid qualification, eligible non-abstaining evidence, and a
strictly later causal revision. Producer-requested deny, assessor self-admission,
and assessor ALLOW are blocked: meet monotonicity cannot authorize an
unauthenticated or unqualified denial-of-service path.

Required witnesses prove that authenticated deny application, rejected
unauthenticated tightening, pending expiry/retraction/disable, restart
preservation, blocked unauthorized widening, and legitimate authenticated
widening are all reachable. The mutation matrix clears deny state through each
lifecycle edge, accepts unauthenticated tightening, grants assessor ALLOW, or
disables the legitimate widening path; every mutation must fail.

### Complete wire-cutover model

The migration state starts with one v0.8 admission plane, performs a quiesced
cut to a fresh native-1.0 incarnation, and then performs a quiesced rollback to
a fresh v0.8 incarnation. Old and new admission are never open together.
Pre-cutover v0.8 commands remain deliverable as hostile delayed traffic so the
model must reject them both during native 1.0 and after rollback, while fresh
native-1.0 and rollback-v0.8 commands still apply.

The v0.8 incarnation labels are deliberately non-chronological and compared only
for equality. The mutation matrix attempts dual-stack admission, activation
before either quiescence, rollback incarnation reuse, ordered-incarnation
comparison, and cross-wire v0.8 admission during native 1.0; every mutation must
fail.

## Freshness and acceptance falsification probe

[`freshness_acceptance_probe.py`](freshness_acceptance_probe.py) challenges ten
bounded campaigns through ten review lenses: body-clock freshness, acceptance
linearization, durable idempotency and bounds, safety-severity ordering, crash
consistency, the unified physical boundary, profile-specific capacity
retirement, terminal HOLD/ESTOP retirement closure, actuation-authority domain
binding, and transport fencing. Its deterministic baseline executes 547 cases,
rejects 369 hostile inputs, reaches 84 required non-vacuity witnesses, and kills
all 144 registered single-defect mutants.

The probe distinguishes attempt start from authenticated transport acceptance.
It retains one original strict acceptance deadline across retries and requires
authenticated order against later gates. It preserves ambiguity when endpoint
evidence cannot prove acceptance or non-acceptance. Exact protected replay and a
same-ID identity conflict allocate no new attempt, operation, or conflict
position. Every restrictive entry path uses one executable sequence: arbiter
pending operation, exact-token path-specific body mirror, one severity-aware
physical invocation, arbiter resolution, and body completion. The paths include
initial HOLD, initial ESTOP, HOLD-to-ESTOP upgrade, retirement-drain ESTOP, and
the profile-selected capacity-retirement action, which is at least HOLD in this
fixture. The capacity path uses its cause-owned pending-operation mirror before
invocation and the generic `RESTRICTIVE_RESULT_MIRROR` consumer after arbiter
resolution; it cannot impersonate a fail-safe reservation or completion.
Upgrade, drain, and capacity retirement use distinct pre-reserved chain tokens
and fresh fence epochs. The sole drain ESTOP token closes its remote edge after
use; the model does not invent a second NCP fallback actuation. Exact replay and
recovery at each durable cut reuse the installed operation without a second
physical invocation. A pending ESTOP forces a delayed HOLD to a definitive
no-effect result. Active value/watchdog updates are atomic and persistent.
Pre-START cuts terminalize admitted work, and Haldir intent uses receiver-issued
freshness.

Each plant generation binds exactly one scalar
`ActuationAuthorityDomainKey` and one matching arbiter mirror. A domain can
represent a qualified atomic multi-actuator boundary, but one atomic-success
claim cannot cross domain keys. Independent domains require independent
sessions. One `InstalledActuationAuthorityDomainSelector` per
`PhysicalActuationJurisdictionKey` incarnation owns the bounded registry and
complete enrolled conflict graph across all body principals. The graph includes
Active, HOLD, ESTOP, watchdog, interlock, reset, and shared-bus footprints.
Overlapping differently named domains cannot both reserve. Disjoint domains can
both reserve only through serialized selector compare-and-swap operations.
Creation receipts select the domain key; caller substitution rejects. A topology
change requires the complete prior-domain fence, qualified physical isolation,
and full re-enrollment. Domain, scope, ownership, topology, selector, footprint,
and receipt-version fields reject bounded unknown, default, malformed, and
oversize values before registry allocation. Only one incarnation of a physical
jurisdiction can remain live at a time.

The retirement-closure campaign makes ambiguous HOLD a distinct terminal
`HOLD_OUTCOME_UNKNOWN` state. `HOLD_PENDING` cannot finalize. Exact-arbiter
retirement preserves an already terminal HOLD result exactly. A lost-arbiter
branch requires qualified physical-isolation evidence and can close pending
HOLD only as `HOLD_OUTCOME_UNKNOWN`, never as effective HOLD. Non-specialized
retirement rejects both `ESTOP_LATCHED` and `ESTOP_OUTCOME_UNKNOWN`; only the
explicit `OPERATOR_RESET_AND_RETIRE_GENERATION` authorization can consume those
floors. Unknown union values reject, and finalization revalidates the installed
closure evidence instead of trusting a caller-constructed typed object.

The result pins a deterministic semantic digest and is mandatory in the
aggregate result. Omission, drift, a surviving mutant, or an optimistic claim
causes verification to fail. This synthetic state-and-receipt probe does not
select normative terminal enums, change the contract, qualify a live transport,
establish physical safety, prove production deadlines, or authorize release.

## Observer, capture, and consumer-surface decision probes

[`observer_authorization_probe.py`](observer_authorization_probe.py) directly
executes a bounded ADR-004 authorization cut across one server authority and two
independent delivery-boundary authorities. The direct scenario covers server and
boundary genesis, a fresh grant-lineage attach, exact two-member preparation,
the server `LIVE` decision, both local activations, one reservation, one atomic
complete outbox release, and one definitive external-drain disposition. Its
result records 3 server transitions, 10 boundary transitions, 71 reached staged
artifact type domains, 5 closed read-route classes, and 161 named hostile
rejections. It also issues one issuer-retained, sealed, read-only
`ObserverReadCapability`. It admits one read decision and one exact retry. The
hostile matrix
includes exact deadline equality, plan/grant and capability substitution,
forged prepared-member evidence, unauthorized scope, forged release/outbox
links, schema and recovery drift, every pre-publication fault cut, and
post-publication acknowledgement loss.

Store enrollment returns the writer and a separate recovery authority. A writer
handle cannot mint its own recovery admission. Each admission is immutable,
one-use, and bound to the exact durable persistence root, snapshot version,
recovery sequence, recovery ID, next writer epoch, trusted clock sample, clock
source policy, and bounded exclusive lease. Recovery fences the prior writer.
Copied, replaced, stale, sibling-root, and replayed admissions reject.

The authorization probe uses deterministic synthetic envelopes and a synthetic
HMAC fixture. It tests exact-byte retention, typed canonical-domain separation,
transport-principal and connection binding, current session/security/revocation
checks, replay fencing, and recovery closure. It is not issuer cryptographic
qualification. It does not demonstrate private-key custody, live principal
binding, external revocation propagation, or interoperability. The real Ed25519
resource probe is separate.

[`observer_read_capture_bridge.py`](observer_read_capture_bridge.py) is an exact
source dependency of both observer probes. It defines the canonical read scope,
boundary membership, sealed read-decision, currentness, release, commit, and
dispatch types. The capability remains the current bounded read authority. The
sealed decision is preflight evidence only. It carries
`PREFLIGHT_ONLY_RELEASE_RECHECK_REQUIRED`.

The delivery boundary rechecks the exact capability or installed grant. The
check also binds scope, membership, source, session generation, security state,
revocation state, recipient, and release quota. A typed currentness artifact
binds the installed state heads and the prior release count. The release CAS
installs only the next count and rejects a count above the decision limit.

Authorization ingress, release-recipient verification, and dispatch use separate
authenticated contexts. Each local time comparison binds one clock incarnation.
A qualified conservative mapping converts a coordinator deadline to the
boundary clock. The effective release deadline is the minimum of all current
local deadlines.

The full release-CAS validator issues one typed validation receipt. The atomic
outbox receipt requires that exact receipt before commit. It binds the prior
storage head, CAS successor, stable outbox artifact, and installed storage head.
Separately retained state binds the expected receipt and both state heads.
Dispatch requires the same committed artifact, receipt, transaction, and
installed head.

`START_EXTERNAL_TRANSPORT_DRAIN` does not claim that bytes crossed a transport.
The probe uses a separate coordinator-locked synthetic enqueue operation. That
operation compares the exact live grant, attempt, writer epoch, lease, payload,
destination, security state, clock, and derived gate epoch before it records one
synthetic enqueue-attempt record. Terminal-first, enqueue-first, replay, and
exact-deadline tests cover both serialization orders. This record is synthetic
same-process evidence only. The probe does not establish filesystem durability,
fsync, restart recovery, or a live transport.

The committed artifact contains the exact immutable payload bytes. Commit
recomputes their SHA-256 digest and byte length. Dispatch receives distinct
caller-supplied transport-attempt bytes and compares them byte-for-byte with that
committed artifact before it recomputes the digest and length. The authorization
drain fact and the capture delivery and reservation retain those caller-supplied
bytes. The bridge rejects payload substitution, length substitution, split writes, forged
commit receipts, stale currentness, quota reuse, and clock-incarnation
substitution.

An ambiguous transport result preserves a stable physical-destination identity.
It does not preserve stale gate authority. Each retry binds the same recipient,
connection, replay domain, security cut, item, and deadline, but derives a new
exact gate digest and epoch. It also uses a new verification event and attempt
identity. The receiver-deduplication proof binds the prior ambiguous attempt and
the stable destination.

The bridge publishes one closed machine-readable canonical-commitment suite.
The suite fixes every normalization envelope, scalar domain, type reference and
field order, collection order, UTF-8 and JSON rule, resource bound, digest
frame, and known-answer vector. Both probes emit the same suite and its
domain-separated digest. Their hostile runner rejects all 672 suite mutations,
including every leaf, ordered sequence, required top-level section, unknown
member, and substituted digest. This is local synthetic implementation
evidence. It is not an external signature or independent interoperability
result.

The enclosing bridge profile rejects all 310 registered leaf, sequence,
top-level, unknown-member, and commitment-triple mutations.

The known-answer vectors distinguish Unicode scalar ordering from UTF-16 code
unit ordering with U+E000 and U+10000. They also fix quotation-mark and
backslash escapes, all five short control escapes, one additional U+00XX
control escape, U+2028, U+2029, astral UTF-8, and composed and decomposed text
without normalization.

Runtime commitment input uses exact structurally closed containers and exact
registered frozen-artifact forms. The emitter accepts frozen maps, frozen lists,
tuples, exact registered frozen artifacts, and closed scalars. It rejects mutable
dictionaries and lists, subclasses, unregistered or non-frozen artifacts, shared
mutable input, and cycles. A private authoring conversion is available only for
an exclusively owned, unpublished graph. Class, registry, instance, and wrapper
backing stability remain caller obligations. The conversion checks depth, nodes,
items, field count, string and payload bytes, aggregate scalar bytes, and
canonical output bytes before or during bounded allocation.
The emitter does not allocate a normalized object tree, and it does not
preflight the complete graph. It checks each scalar or output chunk before the
corresponding bounded allocation. It clears partial output on failure.

Registration requires the exact shared empty field-metadata sentinel. It does
not enumerate a caller mapping. It also proves structural equivalence to the
generated frozen `__setattr__` and `__delattr__` code. Their candidate-class and
`FrozenInstanceError` closures must be exact. The registry pins the functions,
code, closures, globals, builtins, dataclass parameters, fields, and class
bindings.

Each public artifact traversal validates global registry alignment. Before it
reads the first reached instance of each class, it revalidates that class shape.
It reads each field of every instance once through `object.__getattribute__`.
The selected-artifact snapshot API revalidates its selected class on every call.
This reached-class amortization applies to `FrozenTypeRegistry`. An exact
mutable dictionary registry has no prior pins, so each traversal captures all
of its class shapes before use.
A non-slot artifact must have one exact native instance dictionary. Its keys
must equal the pinned field names. Frozen-map and frozen-list backing is also
read once per traversal. Public error classes cannot define a caller-controlled
constructor.

This is same-process integrity evidence only. The caller must prevent concurrent
class, registry, instance, or wrapper-backing mutation. The caller must preserve
canonicalizer and interpreter code integrity through call return. The snapshot
is not atomic. The canonicalizer is not an adversarial in-process sandbox.

The selector checker binds every probe and shared dependency by path, byte
length, and SHA-256. It also binds each exact stdout result and the complete
execution profile. The fixed loader validates the complete frame and compiles
all sources before it executes the dependency order. It starts a fresh Python
interpreter with isolated/no-site/no-bytecode/UTF-8 flags, an empty temporary
directory, a cleared environment, monotone kernel limits, and a best-effort RSS
watchdog. The kernel CPU limit stays separate from the wall-clock limit. The
wall-clock limit is exactly twice the CPU limit to allow finite scheduler
delay. This allowance does not increase the CPU limit. On a wall-clock timeout
or an exceptional caller exit, the checker kills and reaps the fresh probe
process group. This is local exact-source evidence, not an OS sandbox. It does not
isolate the network, absolute filesystem paths, syscalls, or a new process
session. Python, its standard library, the dynamic runtime, and the kernel are
not content-bound. Launch assumes a single-threaded POSIX parent for
`preexec_fn` limits. A descendant that creates another process session can
escape process-group termination.

The shared validator also binds the trusted expected observer principal. It
derives each history-request digest from the complete validated history scope.
It bounds both epochs to portable safe integers and accepts only an exact
32-byte immutable synthetic fixture key. The authorization hostile matrix
re-signs substitutions with the fixture key, so these checks do not pass only
because a stale authentication tag fails.

The capture probe retains that scope, membership, decision, and release-recheck
identity through delivery and receiver admission. It creates a
`DeliveredAdmissionEvidenceCapsule` only after admission succeeds. The capsule
binds the exact frame, delivery, admission head and receipt, admission cut, and
retained payload bytes. Its authority effect is
`HISTORICAL_EVIDENCE_ONLY_NO_FUTURE_READ_AUTHORITY`. A later security cut can
leave this capsule valid as immutable history, but the capsule cannot authorize
another read, callback, release, or admission.

Each `DeterministicExtractionContract` applies bounded decoding and one exact
member path to retained admitted payload bytes. Its receipt binds the capsule,
source bytes, declared output dimension and type, canonical binary64 output,
and any frozen transform. The executor derives the output from retained bytes;
the caller cannot supply the final vector. Source and output objects publish in
one same-process atomic content-store transaction or not at all. The synthetic
current-axis fixture produces seven capsules and seven replay receipts for
`A[a0]`, `D[d_left,d_right]`, `L[l0]`, and `V[v0]`.

The two probes execute in separate fresh interpreter processes and do not pass a
live runtime object between them. Their exact shared source and deterministic
result bindings close the local model's prior type and semantic gap. They do not prove
an installed issuer, live transport, independent interoperability, or consumer
qualification.

[`source_issuance_index_probe.py`](source_issuance_index_probe.py) challenges the
bounded source-issuance and eligible-root closure model. Its deterministic
result admits 20 scenarios, rejects 188 hostile cases, reaches 71 invariants and
27 witnesses, and registers 77 typed artifacts. The hostile matrix rejects enum,
scalar, container, and foreign-enum subclass capture. It also rejects required
`None` substitution while preserving declared optional absence. The probe is a
finite local abstraction. It is not protocol, implementation, transport,
interoperability, plant-safety, independent-review, certification, or release
evidence.

[`observer_capture_probe.py`](observer_capture_probe.py) retains the bounded
observer/capture and Prisoma integration challenge. Its legacy draft and V2
authorization implementations were removed. The retained observer-admission
state machine now uses one closed transition-kind dispatcher in construction and
recovery validation. The hostile matrix rejects
`UNKNOWN_UNALLOCATED_MUTATION`. Its canonicalizer rejects non-string mapping
keys and requires exact base runtime types. It gives all 262 registered capture
and shared bridge dataclass types explicit, one-to-one stable digest domains.
Its versioned typed encoder separates artifact, mapping, tuple, list, and byte
domains. Int/string-key, base-type-subclass, tuple/list, bytes/mapping,
artifact/mapping, root same-shape-type, and nested same-shape-type collision
attempts are direct hostile controls.

Its deterministic result contains 249 targeted cases: 186 lifecycle decisions
(36 admitted and 150 rejected) plus 63 capture-action decisions. It executes and
kills 10 logic mutants with zero survivors. It records 22 semantic contrasts
without presenting them as mutants, rejects 444 hostile inputs, and reaches 73
invariant witnesses. Prisoma estimation remains blocked before eligibility,
with one candidate row, zero eligible rows, and zero estimator calls. The local
fixture does not demonstrate a genuine native-1.0 language channel.

The observer-attachment architecture challenge treats observer authorization as
a required child of each source simulation or plant generation. `AttachObserver`
allocates no ADR-001 generation and accepts no caller observer-session, source-
generation, or authorization-registry namespace. The realm derives one target
key from the authority, source session kind, source logical-session ID, and
authenticated requester. Unknown or default target components reject. The key
excludes generation, request, and scope. One
source-generation authorization registry retains concurrent targets, while one
realm-global target history preserves the same target across source-generation
rollover.

Source finalization requires the exact server-registry cut and a complete durable
pending-target root. It does not wait for retained transport. Distributed
authorization closure and retained-transport quiescence instead gate the later
checkpoint publication for the matching target. A partitioned old boundary does
not block a new plant-control generation or physical-domain handover. It does
block the same target from attach, renew, or reattach until publication.
An unrelated target can attach in the new source generation. These are bounded
synthetic results, not live interoperability evidence.

The fail-safe ingress challenge resolves exact protected replay and command-ID
conflict before any fresh durable attempt or restrictive operation. Its HOLD
and ESTOP branches record the five distinct physical-boundary transitions:
arbiter pending operation, body reservation mirror, physical invocation,
arbiter resolution, and body completion. Admission occurs only after body
completion. A sixth durable transition then associates `hold_effective` or
`stop_latched` without a second physical effect. Each branch emits the exact
token, fence epoch, one-invocation count, stage digests, association digest, and
installed journal head. Recovery reuses the original operation, token, fence
epoch, scalar actuation-domain key, reservation, and physical-invocation record.
This observer fixture executes the initial HOLD and ESTOP branches. It rejects
zero/multiple generation-domain bindings, caller-selected mirror substitution,
and cross-domain atomic-success claims. The freshness probe separately
challenges upgrade, drain, and profile-specific capacity-retirement paths
against the same five-stage order. Neither probe qualifies a live boundary.

The Haldir commander result now means only
`RELEASED_TO_LOCAL_DURABLE_NCP_OUTBOX`. The transport acceptance branch requires
an acceptance receipt. The pre-acceptance rejection branch requires definitive
no-acceptance evidence. The ambiguity branch requires reconciliation. No branch
records an executed transport disposition or receipt.

The legacy capture result is explicitly **not qualified as selector-closure
evidence**. Its Galadriel lifecycle has 68 head/commit pairs but records only
the uninitialized and final selectors. Its Galadriel candidate still references
handoff genesis and does not execute a distinct `PENDING_RECORD_INSTALL` H1
before the record-install H2. Its Prisoma success path uses three legacy generic
transition names, and its four `INPUT_EXCLUDED` facts have no winning terminal
CAS. Its Haldir selected-profile path has no receipt-free intent-source fact,
policy-ingress reservation fact, or pre-CAS evaluation-barrier fact. Haldir
`NO_PROFILE` is shape-only. The bounded Haldir commander path executes genesis,
preflight installation, and a local durable outbox transition only. It does not
execute Feedback as a commander-selector transition. Eight negative
qualification controls reject attempts to promote these structural artifacts to
direct selector evidence.

### Selector resource-ownership closure

[`../../scripts/selector_resource_closure.py`](../../scripts/selector_resource_closure.py)
derives a canonical resource projection from the maintained expanded selector
source. Each declared selector, primary root, state-domain view, and registered
subordinate head has one exact owner and backing identity. Empty-state aliases,
case-fold collisions, duplicate backings, and unresolved resources reject.

An event can `WRITE` or `RESERVE` only a resource owned by that event's selector.
It can use `CONDITIONAL_COMPARE` for a foreign owner without acquiring write
authority. The derived `MUTATION_DERIVED` set must equal the event's declared
`common_case_mutates` set exactly.

Each joint-selector transaction profile names every writing participant
bijectively. Each participant has a nonempty local write footprint and writes
only its own resources. The profile coordinates those local writes. It does not
turn a cross-store edge, cross-repository change, or fleet migration into one
atomic transaction.

The canonical projection binds definitions, effects, derived mutations,
security/body profile references, and joint participants in one
domain-separated commitment. This is local structural closure only. It is not
semantic review, implementation refinement, installed atomicity, external
evidence, or release authorization.

[`decision_probe.py`](decision_probe.py) evaluates four bounded abstractions:

The consumer-surface inventory, `DiscoveryRecord` values, trusted-subject receipts,
scan snapshots, and deployment-topology maps are synthetic fixture data constructed
by the probe. They are not snapshots of the sibling repositories, built dependency
closures, CI configuration, or live deployments.

1. 159,744 observer projection combinations bind the verified principal, closed
   read operation, literal route, grant state, descriptor, authenticated original
   reference, projection/policy digests, visible-channel policy, and exact
   full-versus-redacted completeness. Twenty-three executable logic mutants cover
   generic publication plus high-level command, disposition, authority, ESTOP,
   lifecycle, declaration, and assessment operations and must differ from the
   separate oracle.
2. The 186 lifecycle decision cases contain 36 admitted and 150 rejected cases.
   They cover bounded current/history streams, manifest-scoped attach, principal-bound
   renewal, external compare-and-swap ledger heads, UUIDv4 incarnations, receiver
   clocks, authenticated security state, exact provider contracts, and queued
   frame sources. Nine semantic contrasts are not counted as mutants. All 150
   hostile inputs must reject deterministic grant identity, self-issued authority,
   stale or replayed renewal,
   uninstalled receipts, descriptor drift, frame drift, canonical key coercion,
   same-shape artifact substitution, caller-selected observer namespaces, target-
   key kind collisions, and premature target-history publication.
3. Sixty-three targeted action-evidence cases contain 10 consumer-semantic cases
   and 53 fail-safe cases. They keep received proposal, body admission,
   body-boundary application, non-application, authenticated measurement
   delivery, and physical outcome distinct. Exact V/L/D/A segment, source, route,
   position, security-epoch, provider-contract, consumer-contract, and receipt
   joins are challenged. Thirteen semantic contrasts and 294 hostile inputs also
   cover sequential grants, numeric limits, the closed raw journal, the acyclic
   artifact graph, and the wire-1.0 publication-receipt schema.
4. Four valid surfaces and two reviewed non-surface exclusions exercise one shared
   lock, a shared same-wire provider, and two targets under one package root.
   Surface identity includes the exact
   root/target/canonical-feature-set/role/profile tuple and the digest of a separate
   canonical resolution-context document. That document binds ecosystem,
   host/target triples, resolver/toolchain/profile, configuration, lock, package
   configuration, patches, environment, flags, build scripts, CI, and deployment
   invocation inputs. The full key digest forms the stable ID. Root-package and
   privilege-boundary identifiers also retain their full derived digests. Graph
   edges retain their target predicate and context digest. The probe evaluates
   each closed predicate against the bound context and rejects an inactive edge.

   Contract identity is typed. The frozen wire-0.8 `wire_manifest.json` artifact
   SHA and compact hash are not equated with wire-1.0's complete normative-source
   digest and compact hash. The named Galadriel baseline is the actual immutable
   `v0.8.0` Git subject at commit
   `2f5bd586d4bb20c90362bb6f5698b7f64057ba4e`, not a published-package
   surrogate. Its exact Git tree coordinate, source commit, and typed frozen-wire
   identity are bound separately. Receipts bind the complete typed identity.

   Hostile inventories cover omission/duplication, every resolution-context input,
   edge predicate/context drift, contract kind/domain/digest/compact-hash drift,
   provider-graph reachability, subject/discovery drift, same-wire privilege
   collisions, role-only relabeling of one target/build closure, Cargo and
   synchronized-Python-mirror locators, mixed namespaces and wires, invalid
   retirement, active no-target surfaces, frozen-release protection, full-length
   identities, repository-scoped descriptor downgrade floors, the closed
   exclusion union, and shared-lock interpretation. Assessment reception is a
   privileged negative-control capability. A seeded global repin must expose its
   untargeted revision and artifact-digest change.

   Positive witnesses admit an observer and assessor in one deployment domain
   only when their deployable targets/effective build closures, scanned
   capabilities, activation, and privilege boundaries are distinct. A role or
   profile label cannot turn one dual-capability build into isolated artifacts.
   Two wire surfaces under one package root also require distinct deployable
   targets, activation profiles, runtime entry points, processes, and other
   privilege boundaries. They do not model concurrent dual wire in one process.
   One executed global-repin mutant and 172 hostile inputs challenge the inventory
   closure.

The deterministic result separates 24 killed executable logic mutants and 22
semantic contrasts across 159,993 finite cases. It rejects 616 hostile inputs and
reaches 119 invariant witnesses. It derives these totals from the complete emitted
witness arrays. Its real `--self-test` mutates counts, identities, witnesses, and
inventory digests. The
aggregate verifier recomputes the complete canonical decision-probe result. It
also reconciles those totals before it accepts the result. These remain bounded
design probes, not the N07 pin-tool implementation, built-artifact qualification,
live ACL evidence, or D18 closure.

Within this synthetic model, a scan snapshot binds each surface key to the
canonical digest of the complete fixture `DiscoveryRecord`. This tests fixture
reconciliation only. Trusted N07 scanner input must bind the complete canonical
record content and digest, not only the selected keys, and must derive them from
the actual repository/tree, tracked manifests, complete resolution context, target
predicates and feature graph, lockfiles, build scripts, environment/flags, CI,
deployment inputs, scanner policy/version, exact scanner source and artifact
revisions, and the scanner invocation digest. An authenticated receipt must bind
those values to the scanner principal and trust root. Package and deployment scope
need independent adjudication. An exact graph without that context describes one
resolution result but does not prove which build it describes or that another
context was scanned. A caller-supplied synthetic scan scope, scan snapshot,
context, or deployment-topology map is model input, not scanner evidence. This
probe does not model the authenticated scanner authority or independent scope
adjudication, and its external rescan remains **NOT RUN**.
Prospective native-role fixture names are not findings that matching targets or
paths exist in the sibling repositories.

The current fleet pin checker assumes one compatible wire line across consumers.
N07 must replace that fleet-wide assumption with independent, context-bound,
target-active closure and exact-provider-pin verification for every discovered
surface. A mixed wire-0.8/unreleased-wire-1.0 migration inventory can be coherent
for each surface. This does not prove that all consumers migrated.

## Narrow SMT obligations

[`run_smt.py`](run_smt.py) pins local Z3 output to
`Z3 version 4.16.0 - 64 bit` and runs four SMT-LIB files:

| File | Registered checks |
|---|---|
| [`authority_handover.smt2`](smt/authority_handover.smt2) | a complete cut can grant; old and new authority cannot overlap |
| [`stale_admission.smt2`](smt/stale_admission.smt2) | an exact current fence can admit; a stale generation cannot |
| [`assessment_monotonicity.smt2`](smt/assessment_monotonicity.smt2) | authenticated deny recovery and independently qualified profile tightening are satisfiable; unauthenticated local-policy change or raw evidence, producer-requested/self-admitted/unqualified/ineligible/same-revision deny, unauthenticated widening, applied deny without an authenticated applied disposition, and recovery before dwell are not |
| [`non_authority_inputs.smt2`](smt/non_authority_inputs.smt2) | valid body authority is satisfiable; observer/PID/export/simulation state cannot replace a body lease |

Each independent guard has a named single-removal mutant; mutations are not
bundled by file. The runner binds the current Z3 binary and supplies the exact
validated in-memory source to Z3 standard input, so a different on-disk path
cannot race the checked bytes. It rejects output/control commands in the source,
requires exact `check-sat` and push/pop counts, and accepts only the registered
result tokens as the complete stdout. Version drift, `unknown`, timeout, stderr,
oversized/extra output, missing satisfiable premises, or a surviving mutation
fails.

These formulas are intentionally not placed in `formal/`; they are disposable
pre-ratification challenge material, not the F01/F02 source set.

## Resource screens

[`resource_probe.py`](resource_probe.py) performs four screens:

1. Separate control, action, observation, and extension queues use current
   candidate capacities where available. One hundred thousand offers per
   observer-class queue must leave action state intact and cause zero control
   rejection. A seeded shared-budget design must fail.
2. The independent Python bounded parser consumes approximately 32 KiB and
   993 KiB valid arrays, accepts the exact depth limit, and rejects frame+1,
   depth+1, duplicate decoded keys, and unterminated input. Peak traced memory
   and local time are recorded under deliberately broad preliminary screens,
   not production targets.
3. A prototype journal retains at most 128 entries and 65,536 encoded entry
   bytes, rejects the next append, uses the bounded duplicate-rejecting parser
   for restore, round-trips exact recovery-required deny records, and rejects
   truncated or duplicate-key snapshots. A seeded silent-eviction design must
   be detected.
4. [`crypto_probe.py`](crypto_probe.py) uses real PyNaCl Ed25519 verification for
   empty, 64 KiB, and 1,420,000-byte signing inputs. Valid and full-length invalid
   signatures are measured. A 100,000-microsecond p95 tripwire checks both calling
   thread and whole-process CPU and is self-tested with a seeded overrun. Maximum
   CPU and wall elapsed times are retained only as observations because maxima
   include outliers and wall time includes scheduler delay. The result binds exact
   clock properties, the project and lock bytes, the isolated Python executable
   and ABI, installed PyNaCl and CFFI file-manifest digests, the loaded native
   Sodium and CFFI artifacts, and the `uv` runner. The outer resource process has
   a separately bound executable and ABI; it need not have the same Python patch
   release as the locked isolated cryptographic environment. A fresh isolated
   subprocess must reproduce the cryptographic environment identity. The result
   validator rejects seeded metadata, executable, native-artifact, lock, clock,
   and budget mutations. These hashes identify the measured local executions.
   They do not establish package provenance, a production deadline, or
   performance qualification.

Exact numeric journal, extension, disposition, and production-deadline values
remain B03/N03/N05/N06/performance-gate inputs. The prototype values cannot be
copied into the normative contract without those tasks.

## Exact Fable 5 challenges

The original model/resource design was challenged by exact `claude-fable-5`,
terminal `end_turn`, raw response SHA-256
`4de23e2a48bff1c69d50a454e9ba92360a1372bb8812ee8e443617c6df697282`.
A later exact, terminal cutover and review-packet challenge is bound into the
result by response
SHA-256
`080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`.
The later response reported 672 input tokens, 2,156 output tokens, and 69
thinking tokens.

Retained advice includes the two-command stale/fresh witness, hostile
equality-versus-ordering mutation, semantic deny-set shrinking definition,
authenticated widening success witness, authenticated deny-tightening admission,
strict SMT stdout handling, nested result validation, satisfiable SMT premises,
complete wire cuts, explicit assessment disposition, exact review binding, and
seeded faults for every probe. Rejected advice is documented in
[`SECTION_REVIEW.md`](SECTION_REVIEW.md). The model is advice only and satisfies
no reviewer or evidence floor.

## Run

Prerequisites are the repository Python/toolchain, `ruff`, `uv`, exact Z3 4.16.0,
and the already locked signed-forwarding prototype environment.

```bash
./run.sh
```

The runner:

- compiles and lints the Python sources;
- directly executes each standalone observer probe and freshness/acceptance
  probe;
- loads each declared shared probe dependency from its exact bound bytes;
- byte-replays observer authorization and capture under normal and optimized
  interpreters for two unrelated Python hash seeds;
- byte-replays freshness/acceptance results under two unrelated Python hash
  seeds;
- executes 547 freshness/acceptance cases, rejects 369 hostile inputs, reaches
  84 invariant witnesses, and kills all 144 registered single-defect mutants;
- explores the three bounded models and kills thirty-eight mutations;
- evaluates 159,993 observer/lifecycle/action cases plus four valid surfaces and
  two reviewed exclusions; kills 24 executable logic mutants, reaches 22 semantic
  contrasts, rejects 616 hostile inputs, reaches 119 invariant witnesses, and
  reconciles every emitted witness;
- runs nineteen SMT checks and kills thirteen independent formula mutations;
- runs the queue/parser/journal/real-Ed25519 resource screens;
- inventories every prototype source and the shared bounded-JSON implementation
  by SHA-256 through bounded, no-follow directory and file descriptors; it
  limits entries during discovery and rejects symlink and hard-link aliases;
- binds the result to a clean current Git commit/tree and exact current contract
  manifest bytes;
  and
- preflights the single bounded result line for depth, item, member, array,
  string, number, and aggregate limits before native JSON allocation, then
  passes it through [`verify_result.py`](verify_result.py).

A green run is local preliminary evidence only. External mTLS/ACL,
rotation/revocation, installed peers, live plants, fault/soak, fuzz/sanitizers,
performance qualification, signatures, provenance, clean-room reproduction,
consumer role qualification, publication, and post-publication validation
remain **NOT RUN** unless separately evidenced.
