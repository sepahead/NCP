# B01 preliminary architecture evidence — section review

This review applies only to the quarantined files in this directory. The ADRs
remain PROPOSED and retain their exact hash-bound review requirements.

## Five review lenses

### Protocol, security, and plant correctness

- Crebain is the only modeled serializer of plant mode and authority.
- A durably requested transfer persists its exact source, target, base fences,
  and phase across restart. Recovery resumes it or retains HOLD; it never restores
  the old holder.
- The admission predicate binds active phase, plant domain, term, opaque
  generation equality, opaque stream-epoch equality, exact mode holder, and one
  live lease holder.
- Haldir issue creates a Haldir command. Engram intent has no authority field in
  the abstraction.
- Simulation input, observer grants, pid-rs results, Cortexel exports, and
  Galadriel assessments cannot substitute for the body lease.
- A live `ObserverReadCapability` is bounded current read authority. A sealed
  read decision is preflight evidence and requires an exact release-time recheck.
- A delivered, admitted capsule is immutable historical evidence only. It grants
  no future read, release, callback, admission, command, or lifecycle authority.
- Lifecycle removal of an applied Galadriel deny cannot widen permission until
  an authenticated Haldir policy revision executes.
- Haldir cannot report an applied Galadriel deny without an authenticated
  disposition bound to that outcome.
- An unauthenticated assessor cannot apply even a deny-tightening restriction;
  monotonicity does not authorize denial of service.
- v0.8 and native-1.0 body admission are mutually exclusive across cutover and
  rollback; rollback uses a fresh opaque incarnation.
- The prototype models software admission only. HOLD, ESTOP, disposition, or a
  green model makes no physical-safety claim.

### Consumer and runtime usability

- Direct Engram and gated Haldir paths are both reachable.
- Legitimate authenticated deny removal and base-policy widening are reachable;
  the model does not obtain safety by making recovery impossible.
- Restarts, stream replacement, expiry, hostile input, and reordering remain
  finite and diagnosable.
- Complete wire cutover and rollback are reachable without making fresh commands
  impossible in either active profile.
- Queue isolation is structural: observation and extension overflow cannot
  consume the prototype control/action queues.
- No optional consumer becomes a startup prerequisite or hidden runtime service.

### Operations, science, and evidence honesty

- Every model records bounds, state/transition counts, maximum depth, action
  coverage, and non-vacuity witnesses.
- Every item counted as a mutant executes altered behavior that must fail.
  Twenty-two observer/capture design contrasts are recorded separately and are
  not mutants.
- SMT premises include satisfiable witnesses before an unsatisfiable
  counterexample query is credited.
- Resource timings are machine-local observations with broad prototype screens,
  not SLOs or universal deadlines.
- The 22 ADR JSON fences have content-addressed, bounded semantic profiles in
  separate Rust and TypeScript engines. A profile match is not production
  admission, ADR acceptance, interoperability, or independent evidence.
- Several positive fences are illustrative fragments. The corpus preserves that
  scope and rejects any attempt to promote them into complete wire evidence.
- Ed25519 authenticates fixed bytes; it does not validate advice, simulation,
  PID quality, calibration, command usefulness, or physical effect.
- Seven deterministic extraction receipts replay retained admitted bytes for
  `A[a0]`, `D[d_left,d_right]`, `L[l0]`, and `V[v0]`.
- Prisoma remains blocked before estimation because the local evidence does not
  demonstrate a genuine native-1.0 language channel.
- Fable advice is retained as challenge input only.

### State-machine, concurrency, and recovery closure

- The standalone authorization probe executes one bounded atomic server and
  two-boundary flow.
- The direct flow has 3 server transitions and 10 boundary transitions.
- The probe stages 71 explicit literal artifact type domains before validation.
- It issues one sealed read-only capability and admits one read plus one exact
  retry in the synthetic issuer domain.
- Both observer probes load the same exact shared scope, boundary-membership,
  and sealed read-decision source.
- Capture binds the release recheck through delivery, receiver admission,
  historical capsule creation, and deterministic extraction receipts.
- Recovery recomputes each schema, operation commitment, authority link, clock
  link, and security link. A separate authority issues one-use admissions that
  bind the exact durable root, next writer epoch, trusted sample, clock-source
  policy, and bounded lease.
- The observer-admission dispatcher accepts five allocated transition kinds.
- The dispatcher rejects `UNKNOWN_UNALLOCATED_MUTATION` before state mutation.
- The capture canonicalizer rejects key and runtime-type coercion. It binds all
  262 declared dataclass types to explicit, one-to-one stable digest domains.
  Its typed encoder separates artifact, mapping, tuple, list, and byte domains.
- The capture result reconciles 186 lifecycle decisions and 63 capture-action
  decisions. It executes and kills 10 logic mutants, reports 22 semantic
  contrasts separately, rejects 444 hostile inputs, and reaches 73 invariant
  witnesses.
- Resource closure requires every `WRITE` and `RESERVE` to target a resource
  owned by the event's selector. Foreign resources are compare-only.
- Each joint transaction profile bijectively names nonempty local-write
  participants. It does not claim cross-store or cross-repository atomicity.
- Exact server-expiry terminalization and boundary consumption of that terminal
  receipt are direct scenarios. Server renewal, restart, rotation, bulk
  closure, and boundary transport quiescence are not direct scenarios.

### Ecosystem integration and evidence qualification

- The standalone authorization probe uses deterministic synthetic envelopes and
  an HMAC fixture. These are not issuer cryptographic qualification.
- The probes share exact artifact source but run in separate fresh interpreter
  processes under the bounded local checker profile. The profile is not an OS
  sandbox or runtime-provenance check. The probes do not pass one installed live
  capability object between runtimes.
- The shared bridge closes a synthetic model boundary only. Live issuer,
  transport, revocation, and independent interoperability evidence is absent.
- The legacy capture probe is not selector-closure evidence.
- Galadriel records 68 lifecycle head/commit pairs, but not selectors 1 through
  67.
- Galadriel does not execute `PENDING_RECORD_INSTALL` H1 before record-install
  H2.
- Prisoma executes a legacy three-transition success path. Four exclusion facts
  have no winning terminal CAS.
- Haldir has no receipt-free intent-source, ingress-reservation, or pre-CAS
  evaluation-barrier fact in this fixture.
- Haldir `NO_PROFILE` is a shape-only witness.
- The Haldir commander executes genesis, preflight installation, and queue
  transition only.
- Eight negative controls reject attempts to use these structural artifacts as
  direct selector evidence.
- Prisoma's native language-channel dependency remains blocked. Live transport,
  external revocation, installed peers, release gates, and every consumer-role
  qualification remain **NOT RUN**.

## Assumptions and exclusions

The composition enumerator assumes:

- one bounded plant session;
- one Crebain body;
- at most one direct-to-gated handover in the explored history;
- at most two body-generation changes, two stream-epoch changes, and two
  simultaneously in-flight commands;
- exact in-progress transfer restart preserves the session generation; clean or
  completed-state restart can move to the next finite generation;
- terms from a small finite set;
- arbitrary hostile input can vary one exact fence independently; and
- delivery can be reordered, while cryptographic unforgeability is outside this
  model.

The deny model assumes:

- Haldir owns the local policy revision;
- raw evidence authentication, profile authentication, independent profile
  issuance, qualification, eligibility, and causal separation are distinct
  admission guards;
- an applied deny remains effective after expiry, retraction, disable, or
  restart until an authenticated widening transition removes it;
- `RECORD_ONLY` is the meet identity;
- Galadriel has no ALLOW action; and
- absence posture cannot create a new ALLOW.

The migration model assumes:

- one bounded body deployment moves v0.8 to native 1.0 and then rolls back;
- wire admission is closed during each bounded quiescence interval;
- pre-cutover commands may remain delayed until either later active profile;
- rollback creates a fresh v0.8 incarnation; and
- opaque incarnation labels have equality meaning only.

The SMT files assume their Boolean/integer abstractions correspond to the prose.
They do not prove that correspondence. The resource screens assume one local
process, current machine load, current locked libraries, and the fixed corpus.

Excluded:

- multi-body consensus or leader election;
- permanent-partition liveness;
- physical actuation or interlocks;
- key custody, CA operation, side channels, trusted-time deployment, and
  multi-host replay consensus;
- actual journal storage/compaction technology;
- normative capacities and production deadlines;
- Rust transition-core refinement;
- canonical TLA+, Kani, large state spaces, fairness, or independent review;
- consumer implementation or installed interoperability; and
- any release or qualification conclusion.

## Strongest counterexample class

The primary composed hostile trace is:

1. an old direct-Engram command remains in flight;
2. Crebain closes old admission and completes the body-coordinated handover;
3. Haldir creates a fresh command under its own current authority;
4. a body or stream restart changes an opaque equality fence;
5. the fresh and stale commands coexist in the bounded pending set; and
6. delivery reorders the stale command after the cut.

The correct model reaches this trace and rejects the stale arrival. Removing
generation, term, epoch, or holder checks; ordering UUID labels; or overlapping
holders produces a counterexample.

The non-vacuity predicate is specific: the rejected command was legitimate when
issued, is stale under the current state, and another simultaneously pending
command satisfies the complete current admission predicate. Two unrelated
hostile commands do not satisfy it.

The coupled Haldir/Galadriel trace is:

1. local policy allows;
2. a verified `DENY_TIGHTEN` applies;
3. expiry, retraction, disable, or restart occurs;
4. an unauthorized action attempts to erase the restriction; and
5. only a later authenticated monotonic policy revision may widen permission.

The correct model reaches both the blocked attempt and legitimate widening.

The wire-migration trace is:

1. a valid v0.8 command remains delayed;
2. old v0.8 admission closes and quiesces before native 1.0 opens;
3. the delayed command rejects under native 1.0 while a fresh 1.0 command applies;
4. native 1.0 closes and quiesces before rollback opens; and
5. rollback uses a fresh opaque v0.8 incarnation, so the pre-cutover command
   still rejects while a fresh rollback command applies.

Opening both admission planes, skipping either quiescence, reviving the old
incarnation, ordering opaque labels, or accepting v0.8 under native 1.0 creates
a detected counterexample.

## Mutation kill matrix

The Python enumerator must detect:

- omitted generation equality;
- ordered generation comparison;
- omitted term;
- omitted stream epoch;
- omitted holder/lease identity;
- simulation admitted as plant;
- Haldir command constructed under Engram principal;
- overlapping handover holders;
- restart loss or rollback of each requested, quiesced, retired, or
  term-persisted transfer latch;
- transfer completion before quiescence, old-authority retirement, or higher-term
  persistence;
- transfer completion under the retired old holder;
- expiry clearing a deny;
- retraction clearing a deny;
- disable clearing a deny;
- restart dropping a deny;
- unauthenticated clearing;
- record-only clearing;
- assessor ALLOW;
- unauthenticated deny tightening; and
- removal of the legitimate authenticated-widening path;
- dual-stack wire admission;
- native-1.0 or rollback activation before quiescence;
- rollback reuse of the pre-cutover v0.8 incarnation;
- ordered comparison of opaque v0.8 incarnation labels; and
- v0.8 admission during native 1.0.

The SMT runner must detect guard removal from:

- handover old-revocation ordering;
- stale-generation admission;
- unauthenticated state preservation, raw-evidence authentication, and
  authenticated recovery dwell;
- independently authenticated and issued, qualified, eligible, causally later
  monitor-admission profiles;
- authenticated applied-deny dispositions and exact applied outcomes; and
- body-lease necessity.

It also rejects source-level output/control commands, mismatched `check-sat` or
push/pop counts, and any stdout other than the exact registered result-token
sequence. The result records the current Z3 executable hash as a local tool
identity; this is not a signed toolchain attestation.

The resource screens must detect:

- a shared observer/control queue budget;
- an unbounded generic parser accepting a frame over the NCP byte limit;
- silent journal eviction of recovery evidence; and
- an artificially seeded Ed25519 screen overrun.

A surviving executed mutation blocks the prototype result. A semantic contrast
is a non-vacuity witness and cannot increase the mutation-kill count.

## Resource-screen interpretation

The queue probe records operation timings but gates only exact structural
isolation, capacity, and overflow counters. Scheduler timing alone cannot prove
priority.

The parser probe records `tracemalloc` peak and elapsed time for two valid sizes.
The memory and time screens are deliberately broad tripwires against accidental
explosion. They are not production qualification and do not replace native
allocator measurements, fuzzing, sanitizers, or independent parsers.

The journal is an in-memory/snapshot abstraction. Reject-on-full demonstrates a
finite non-lossy posture for the fixed corpus, and bounded restore rejects
truncation and duplicate keys. It does not select the later retention policy or
prove crash-safe storage.

The Ed25519 probe measures real PyNaCl verification over maximum-profile-sized
bytes, including full-length invalid signatures. It does not run the whole
ingress pipeline, prove constant-time behavior, or establish a plant command
deadline. Its declared thread- and process-CPU p95 budget is only a fixed-sample
computational tripwire. Maximum CPU and wall elapsed time are recorded but not
gated because maxima include outliers and wall time includes scheduler
preemption. The result also binds each clock's exact properties, the project and
lock bytes, the isolated Python executable and ABI, installed PyNaCl and CFFI
file-manifest digests, the loaded native Sodium and CFFI artifacts, and the `uv`
runner. The outer resource process binds its own executable and ABI separately;
its Python patch release can differ from the locked isolated environment. A fresh
isolated subprocess must reproduce the cryptographic environment identity. These
local hashes do not establish package provenance. Deployment latency and
performance qualification remain separate gates.

## Exact Fable 5 disposition

Exact returned model: `claude-fable-5`. Stop reason: `end_turn`. Raw response
SHA-256:
`4de23e2a48bff1c69d50a454e9ba92360a1372bb8812ee8e443617c6df697282`.

Retained:

- two in-flight commands and a stale-arrival rejection witness;
- non-chronological generation labels plus an ordering mutation;
- semantic widening as a change from denied to allowed;
- restart-drop and lifecycle-clear mutations;
- both blocked unauthorized and successful authenticated widening witnesses;
- satisfiable SMT premises;
- seeded probe faults; and
- the narrow local claim boundary.

Revised or rejected:

- The advice presented deny expiry semantics as an unresolved choice. The
  proposed ADRs already state that expiry/retraction/disable/restart cannot
  silently erase an applied deny; removal requires an authenticated Haldir
  transition. The model therefore exercises that proposal rather than reopening
  it. Human reviewers can still reject the ADR bytes.
- Three generation labels are retained, but labels are never chronological.
  Hostile input changes exactly one fence so an ordering mutation cannot be
  masked by term/epoch mismatch.
- The advice discouraged real cryptography in the resource slice. A stub cannot
  challenge a cryptographic deadline assumption, so the probe uses real locked
  PyNaCl Ed25519 verification while explicitly excluding key management and
  production qualification.
- The prototype is not reusable as the canonical F01 model without a new task,
  review, assumptions, tool pinning, and exact content-bound evidence.

The hardening review later returned exact model `claude-fable-5`, terminal
`end_turn`, raw response SHA-256
`356dcd46bcf4e1ad2bb11a878fe5bcaa75a3ae16fc58eb035c674aa08e286deb`
with 351 input, 1,934 output, and 957 thinking tokens.

Retained from that response:

- make the stale/fresh witness identify a formerly valid stale command and a
  simultaneously current-valid command, rather than two arbitrary hostile
  messages;
- treat unauthenticated deny tightening as a denial-of-service vulnerability and
  kill that mutation;
- reject solver output/control commands and extra stdout;
- enforce strict nested result shapes, clean exact Git/source binding, timestamp
  plausibility, and current contract-manifest bytes; and
- keep direct/gated overlap as an explicit killed mutation.

Revised or rejected from that response:

- It again described opaque generation/epoch identifiers as strictly increasing.
  NCP compares generation and stream-epoch UUIDs only for exact equality.
  Monotonicity belongs to the body authority term, policy revision, and stream
  sequence.
- It described the stale and fresh commands as consecutive. The model instead
  requires simultaneous in-flight coexistence before reordered delivery, which
  is the stronger distributed-systems witness.
- A signed/published Z3 tool attestation and canonical obligation provenance
  registry belong to later F01/F02. This preliminary runner records exact version,
  current executable hash, sources, commands, and stdout without promoting the
  result into the canonical formal program.

The cutover/review-packet challenge later returned exact model
`claude-fable-5`, terminal `end_turn`, raw response SHA-256
`080ad93775d6dec018a08efeadd49b0d57e6162a90f4bc7cf9a8b43199246d32`
with 672 input, 2,156 output, and 69 thinking tokens.

Retained from that response:

- model old-plane shutdown and quiescence before opening a fresh native plane;
- make rollback another complete cut that cannot revive pre-cutover traffic;
- authenticate and bind the Haldir assessment disposition;
- retain Crebain ownership of body state and Haldir ownership of local policy;
  and
- bind independent review to exact ADR/tree/contract/evidence identities and
  explicit non-claims.

Revised or rejected from that response:

- Incarnation UUIDs are equality fences, not counters.
- Crebain does not acquire or verify Haldir-owned policy as body authority.
- Bit-identical builds and clean-room reproducibility remain later release
  evidence, not a preliminary B01 claim.

## Open requirements

This prototype does not satisfy B01. Still required:

- same-digest review by every named owner role;
- at least two qualifying independent identities;
- resolution or explicit exclusion of every ADR open question;
- owner confirmation that each consumer use case is expressible without a
  private core fork;
- explicit pid-rs protocol-neutrality confirmation;
- deliberate pre-release rebaseline authorization;
- later B03 numeric registries/bounds;
- canonical F01/F02 formal/refinement work after dependencies; and
- all external release gates.
