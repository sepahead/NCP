# B01 preliminary architecture evidence — section review

This review applies only to the quarantined files in this directory. The ADRs
remain PROPOSED and retain their exact hash-bound review requirements.

## Three perspectives

### Protocol, security, and plant correctness

- Crebain is the only modeled serializer of plant mode and authority.
- The admission predicate binds active phase, plant domain, term, opaque
  generation equality, opaque stream-epoch equality, exact mode holder, and one
  live lease holder.
- Haldir issue creates a Haldir command. Engram intent has no authority field in
  the abstraction.
- Simulation input, observer grants, pid-rs results, Cortexel exports, and
  Galadriel assessments cannot substitute for the body lease.
- Lifecycle removal of an applied Galadriel deny cannot widen permission until
  an authenticated Haldir policy revision executes.
- An unauthenticated assessor cannot apply even a deny-tightening restriction;
  monotonicity does not authorize denial of service.
- The prototype models software admission only. HOLD, ESTOP, disposition, or a
  green model makes no physical-safety claim.

### Consumer and runtime usability

- Direct Engram and gated Haldir paths are both reachable.
- Legitimate authenticated deny removal and base-policy widening are reachable;
  the model does not obtain safety by making recovery impossible.
- Restarts, stream replacement, expiry, hostile input, and reordering remain
  finite and diagnosable.
- Queue isolation is structural: observation and extension overflow cannot
  consume the prototype control/action queues.
- No optional consumer becomes a startup prerequisite or hidden runtime service.

### Operations, science, and evidence honesty

- Every model records bounds, state/transition counts, maximum depth, action
  coverage, and non-vacuity witnesses.
- Every critical guard has a mutation that must fail.
- SMT premises include satisfiable witnesses before an unsatisfiable
  counterexample query is credited.
- Resource timings are machine-local observations with broad prototype screens,
  not SLOs or universal deadlines.
- Ed25519 authenticates fixed bytes; it does not validate advice, simulation,
  PID quality, calibration, command usefulness, or physical effect.
- Fable advice is retained as challenge input only.

## Assumptions and exclusions

The composition enumerator assumes:

- one bounded plant session;
- one Crebain body;
- at most one direct-to-gated handover in the explored history;
- at most two body-generation changes, two stream-epoch changes, and two
  simultaneously in-flight commands;
- terms from a small finite set;
- arbitrary hostile input can vary one exact fence independently; and
- delivery can be reordered, while cryptographic unforgeability is outside this
  model.

The deny model assumes:

- Haldir owns the local policy revision;
- an applied deny remains effective after expiry, retraction, disable, or
  restart until an authenticated widening transition removes it;
- `RECORD_ONLY` is the meet identity;
- Galadriel has no ALLOW action; and
- absence posture cannot create a new ALLOW.

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
- any release or certification conclusion.

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
- expiry clearing a deny;
- retraction clearing a deny;
- disable clearing a deny;
- restart dropping a deny;
- unauthenticated clearing;
- record-only clearing;
- assessor ALLOW;
- unauthenticated deny tightening; and
- removal of the legitimate authenticated-widening path.

The SMT runner must detect guard removal from:

- handover old-revocation ordering;
- stale-generation admission;
- authenticated widening monotonicity; and
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

A surviving mutation blocks the prototype result.

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
deadline. Its declared budget is only a local pre-ratification screen.

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
