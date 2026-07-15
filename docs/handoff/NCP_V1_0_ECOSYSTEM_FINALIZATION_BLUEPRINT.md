# NCP 1.0 ecosystem finalization blueprint

> **Document status:** living, non-normative implementation handoff. This file is
> evidence bookkeeping and a work plan. It is not the NCP specification, a release
> authorization, a certification, a tag, or proof that an external gate ran.
>
> **Candidate status at the reviewed boundary:** `NO_GO`. NCP package
> `1.0.0-rc.1`, wire `1.0`, and compact proto hash `163acc57d8a62b66` remain
> unreleased. The latest immutable release is `v0.8.0`, which is a different wire.
>
> **Editing rule:** update a task from `OPEN` only in the same coherent commit that
> adds or binds its evidence. Record the exact commit, commands, results, artifact
> digests, reviewer, and residual `NOT_RUN` obligations. Commit and push each
> coherent, passing part with a professional message. Never use a status edit as a
> substitute for implementation or independent review.

## 1. Objective and non-negotiable interpretation

The objective is to make the first stable NCP 1.0 contract internally coherent,
secure by construction, implementable in independent languages, usable by the
named ecosystem, and evolvable without silently changing its stable core. The
reviewed ecosystem is:

- canonical NCP in `sepahead/NCP`;
- the active Engram implementation in private `sepahead/Paper2Brain`, including
  its Python-native NCP runtime and source mirror;
- `sepahead/haldir`;
- `sepahead/galadriel`;
- `sepahead/crebain` (the old `sepehrmn/crebain` URL redirects here);
- the local Crebain Galadriel-producer branch/worktree;
- `sepahead/prisoma`; and
- the public `sepahead` profile/selected-work presentation.

“Final” cannot honestly mean that no future defect, cryptographic transition,
hardware class, or scientific need will ever exist. The implementable meaning is:

1. freeze a small stable 1.0 core only after its safety and interoperability
   obligations are met;
2. define content-addressed, default-deny extension points so new optional behavior
   does not mutate that core;
3. require a new major wire rather than reinterpreting a stable field;
4. retain explicit revocation, deprecation, and emergency-response mechanisms; and
5. make every claim traceable to exact source, installed artifacts, configuration,
   test evidence, and independent review.

Passing local tests, copying protocol files, changing manifests, completing this
blueprint, or freezing a candidate baseline does not release or certify NCP 1.0.

## 2. Source and evidence boundary

### 2.1 Canonical NCP cut

The initial audit is bound to the following exact clean NCP source:

| Axis | Value |
|---|---|
| repository | `git@github.com:sepahead/NCP.git` |
| branch | `main` |
| commit | `8ce57bbd28b0f252dab1275f50a72861a60cbeec` |
| package candidate | `1.0.0-rc.1` |
| stable wire | `1.0` |
| compact proto hash | `163acc57d8a62b66` |
| complete normative SHA-256 | `9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90` |
| mandatory corpus SHA-256 | `83bdcfae2e07f1c69efa87279f0b3c27392be83f31b292647cddd10eb35226b3` |
| checked-in build identity | `unreleased-worktree` |
| release decision | `NO_GO`; `release_allowed=false` |

The hosted candidate evidence documented in
[`../1.0-candidate-receipts.md`](../1.0-candidate-receipts.md) is bound to earlier
implementation cut `ef357d20692f707e185495dcfd16b16556fec264`, not automatically
to every later commit. Re-run and rebind evidence after any normative change.

### 2.2 Supplied Engram review archive

The supplied archive was found at
`/Users/torusprime/Downloads/engram-review-20260715-1504.zip` and inspected from a
safe extraction under `/tmp`. Its review identity is:

| Axis | Value |
|---|---|
| archive SHA-256 | `ed80122a960eaa72f452929f520ba237d73a12249e6123224766762154225dd9` |
| entries | 1,920 |
| uncompressed bytes | 27,815,546 |
| traversal/absolute-path violations | 0 |
| recorded source commit | `92853d2fe6e8ced7e98e2f272a34bfc0067dce57` |
| recorded branch | `main` |
| recorded state | `DIRTY` |
| bundle creation | 2026-07-15 15:04:03 UTC |
| Engram NCP mirror commit | `d0c130424414e5483f0834228a548fd1e6e4adba` |
| mirrored package/wire | `1.0.0-rc.1` / `1.0` |
| mirrored complete digest | `10b81f8dfec289dc553c320430ab3fefea0f0bb2002b6e85415383119445555b` |

The inspected `backend/neurocontrol` and `ncp` source content matched the active
Engram worktree at the review point, excluding ignored build/cache output. That is
useful development evidence only. It is not an installed artifact, clean source
cut, live peer result, or consumer certification. The mirror predates the canonical
NCP cut above and must eventually be repinned through Engram's mirror tooling after
the final NCP source is committed and pushed.

### 2.3 Mutable ecosystem snapshot

The following was sampled at 2026-07-15 20:14:05 UTC. Other agents are actively
working outside NCP; every migration task must refresh this table before editing and
must preserve unrelated work.

| Project | Local branch | Initial commit | Initial tracked/untracked changes | NCP state |
|---|---|---|---:|---|
| NCP | `main` | `8ce57bbd28b0f252dab1275f50a72861a60cbeec` | 0 | unreleased wire-1.0 candidate |
| Engram / Paper2Brain | `main` | `92853d2fe6e8ced7e98e2f272a34bfc0067dce57` | 168 | active dirty native-1.0 work; stale NCP mirror |
| Haldir | `wip/current-file-review-ledger` | `bb6c0a7b27bbc57fe9935f80e22d06ca3b60e8ba` | 0 | exact immutable `v0.8.0` adapter |
| Galadriel | `main` | `f541f3eda7cfdc81a3277c3d6fecc91245179f24` | 0 | exact `v0.8.0`; optional sidecar/tap |
| Crebain | `main` | `3e3ee5d0b75269b8f5f634485871069c89a9a474` | 0 | exact `v0.8.0`; dormant bridge |
| Crebain producer clone | `feat/galadriel-integration-refresh` | `113ee70d5660daf90bb373bd7857d4b3f2f56784` | 0 | exact `v0.8.0`; duplicated producer work |
| Prisoma | `main` | `b0185d98aea8bb6512926d9a8365ba8140fd07c0` | 0 | exact `v0.8.0`; workspace-excluded observer |
| sepahead profile | `main` | `80a5c1d5af3a7b85d2a683921dd31e2bdf0406ce` | 2 | generated selected-work presentation; preserve dirty state |

The current NCP consumer-pin scan correctly fails because Engram is on the 1.0
candidate while all other declared consumers are on the incompatible 0.8 line.
That mismatch is migration evidence, not a guard to weaken.

## 3. Authority, precedence, and completion semantics

### 3.1 Normative precedence

The complete normative source list and precedence come only from
[`../../contract/manifest.v1.json`](../../contract/manifest.v1.json). This blueprint
may identify a defect and prescribe a change; it cannot override the manifest,
protocol, proto, schemas, registries, or conformance corpus.

For a wire-visible change, the implementation commit must update together, as
applicable:

1. the normative prose and registries;
2. `proto/ncp.proto`;
3. source Rust types and validators;
4. generated JSON Schemas and generated TypeScript;
5. canonical messages, positive/negative behavior vectors, and mandatory coverage;
6. FFI fixtures and package-owned copied testdata through generators;
7. the compact proto hash and complete normative digest;
8. the unreleased candidate baseline;
9. migration documentation and consumer pin tooling; and
10. every affected package README, security statement, limitation, and release gate.

Never hand-edit generated schemas, generated TypeScript, copied testdata, or a
generated manifest. Change its source and run the owning generator.

### 3.2 Status vocabulary

Use only these task states:

- `OPEN`: work or evidence is absent.
- `IN_PROGRESS`: an owner and branch exist, but acceptance is not met.
- `BLOCKED`: a named prerequisite outside the task cannot currently be satisfied.
- `LOCAL_PASS`: exact repository-local acceptance passed; external obligations are
  still explicit.
- `EXTERNAL_PASS`: the named external campaign passed with retained evidence.
- `INDEPENDENT_PASS`: a disjoint implementation/reviewer reproduced the result.
- `COMPLETE`: every acceptance criterion and required review for that task passed.

Do not use “done,” “certified,” or “verified” without the qualifying scope. A
model-checked abstraction is not a verified implementation. A successful Zenoh
`put` is not delivery or actuation. An NCP ESTOP is not a physical safety
certification. A simulation is not calibrated posterior evidence.

### 3.3 Evidence receipt required for every status change

Every task status change must append a receipt with all of:

```text
task_id:
old_status:
new_status:
repository:
branch:
source_commit:
source_tree:
normative_digest_before:
normative_digest_after:
commands:
exit_codes:
test_counts_and_skips:
artifact_paths_and_sha256:
environment_and_toolchain:
reviewer_identity_and_independence:
external_gates_run:
external_gates_not_run:
residual_risks:
rollback_or_recovery:
commit:
push_remote_and_ref:
timestamp_utc:
```

Receipts belong in a machine-checkable ledger added during blueprint task `B00`.
Free-form prose alone cannot promote a state.

## 4. Mandatory ten-lens review

Every task in this blueprint must be reviewed through all ten lenses. “Not
applicable” requires a concrete reason and reviewer; it is not a shortcut.

| Lens | Required question |
|---|---|
| L1 Contract and semantics | Does the task preserve one unambiguous normative meaning across prose, proto, schemas, code, vectors, generated packages, and routes? |
| L2 Security and authority | Which verified principal, role, plane, session, key, lease, and manifest authorizes this action; can unknown, missing, stale, replayed, or downgraded input grant anything? |
| L3 Safety and plant boundary | What hazard can this create; where is final actuator authority; what is the bounded fail-safe behavior under ambiguity, expiry, restart, and ESTOP? |
| L4 Distributed systems | What happens under duplication, loss, delay, reorder, partition, process restart, clock movement, split brain, concurrency, and partial commit? |
| L5 Resource and real-time bounds | Are bytes, nesting, allocations, queues, work, deadlines, clocks, sequence space, disk, memory, and CPU bounded before semantic allocation; how does overload fail? |
| L6 Interoperability and migration | Can two independently installed implementations agree exactly; how are 0.8 history, incompatible peers, extensions, rollback, and mixed fleets handled without silent translation? |
| L7 Science and statistics | Does the task preserve provenance and non-claims; are simulations, calibration, PID validity, missing variables, estimands, uncertainty, and benchmark statistics represented honestly? |
| L8 Implementation and operations | Is the API hard to misuse; are configuration, observability, deployment, operator recovery, accessibility, documentation, and support paths executable and clear? |
| L9 Verification and evidence | Which invariant is proved or tested, at what abstraction; are negative cases, independent languages, model/refinement checks, fuzzing, artifacts, hashes, and zero-skip rules retained? |
| L10 Lifecycle and governance | Who owns the change, keys, namespace, release, incident response, revocation, dependencies, provenance, licenses, deprecation, and long-term compatibility? |

The existing max-effort ledger retains twenty open lenses for tasks `T000`–`T145`.
This blueprint does not close, replace, or weaken that ledger. `B00` must map the
ten lenses above to the existing twenty-lens taxonomy and require the stricter
obligation when they overlap.

## 5. First-principles findings that block a stable 1.0 freeze

These findings were reproduced against the exact source and consumer cuts above.
They are architecture inputs, not implementation completion.

### F01 — one session opening currently has two contradictory jobs

`OpenSession` is explicitly a neural simulation request: it requires a
`NetworkRef`, recording specification, stimulus specification, simulation
configuration, and simulation provenance in the response. The reference topology
simultaneously describes Engram as the commander/hub that opens sessions with
robot/UAV bodies. A physical Crebain body neither owns an Engram neural network nor
resolves NEST record/stimulus configuration.

This cannot be repaired by documenting that “body” has two meanings. Before the
stable freeze, split the generic session core from typed session extensions:

- a **simulation-service session**, in which an authenticated client commander
  asks a simulator body/service to open, step, run, observe, and close a neural
  simulation; and
- a **plant-control session**, in which an authenticated controller/commander and
  physical or simulated plant body negotiate channels, plant profile, rates,
  security, streams, authority, and lifecycle without neural-model fields.

Both can reuse bounded session references, identity, security, lifecycle,
idempotency, and receipts, but their request kinds, required fields, capabilities,
and authorization rules must be mutually exclusive. A frame from one session type
must never be accepted in the other merely because the `session_id` matches.

### F02 — observers have no authenticated attach protocol

Prisoma and Galadriel are intended read-only observers. Current stable transport
helpers require an exact `SessionRef`, while raw fleet/session subscriptions are
explicitly untrusted. There is no stable request by which an authenticated observer
can learn the current server-issued generation, session kind, full contract
identity, security state, plant profile, negotiated channels, participants, and
declared streams. Inferring the generation from the first data frame would let
traffic choose its own authorization context.

Add an authenticated, read-only observer attachment/descriptor exchange. It must
return a bounded descriptor for an already-live session, bind the responder and
requester identities, enumerate only permitted planes/channels, carry a finite
attachment lifetime or revocation epoch, and never grant commander/operator
authority. “Describe” without access control is insufficient because descriptors
can expose topology and enable subscriptions.

### F03 — stream epochs are normative but stream declaration is not executable

The protocol says a receiver declaration binds one epoch and that exhaustion or
restart requires a fresh authenticated declaration. No stable declaration message
or transcript currently establishes that state. Consumers therefore need
out-of-band inference. Engram's current Python runtime can silently mint a new
observation epoch at sequence exhaustion, contradicting the rule that the exhausted
publisher becomes silent until a fresh declaration.

Add explicit declare/redeclare/retire stream operations, with publisher principal,
plane, route, session generation, epoch, schema/channel set, sequence start,
security state, transcript digest, and bounded operation context. A declaration is
not authority to publish on another plane. Sequence exhaustion must stop output
until a successful fresh declaration; it must not rotate silently.

### F04 — compact proto identity is advisory and incomplete

The compact `CONTRACT_HASH` covers the proto and is intentionally advisory. It does
not identify the complete normative contract, behavior corpus, security registries,
or generated package semantics. Stable 1.0 certification cannot accept two peers
that merely share `ncp_version="1.0"` while disagreeing on safety behavior.

Define a hard, wire-visible stable-core digest and a separate complete release
identity. The stable-core digest must cover every wire-semantic input and remain
immutable after release. The complete release digest may also bind normative
documentation. Handshakes and session descriptors must carry both; a native stable
session fails closed on stable-core mismatch. Optional extensions use separate
content-addressed manifests and explicit negotiation. The compact hash remains a
diagnostic, never the hard compatibility proof.

### F05 — capabilities are not cryptographically bound into the session transcript

Capabilities exist, but the stable lifecycle does not establish one unambiguous
negotiation transcript whose digest is echoed by both session-opening parties,
observers, stream declarations, leases, and receipts. A channel/profile/capability
swap between discovery and opening must be detectable.

Define deterministic transcript construction from exact canonical capability
offers, selections, identities, security state, session type, stable-core digest,
plant profile, channels, and extension manifests. The server-issued session
response commits the transcript digest. All later declarations, authority leases,
observer descriptors, and terminal receipts bind that digest.

### F06 — transport principal proof is unavailable in the reference Zenoh callback

The `production-secure` profile correctly refuses to start because the current
Zenoh subscriber/query callback does not expose the authenticated certificate
principal needed to bind `IdentityClaim`. Zenoh source IDs are not certificate
principals. Default-deny ACL configuration and successful TLS setup do not by
themselves give the application a per-message verified actor.

Do not weaken the identity rule. Task `A06` must implement and independently review
a production security envelope or a trusted terminating ingress that produces an
application-visible authenticated actor. The recommended stable design is a
domain-separated, end-to-end signed canonical payload using a tightly profiled JWS
representation and an enrolled key manifest, while retaining TLS 1.3 and
default-deny ACLs for hop confidentiality and route minimization. The profile must:

- allow exactly one pinned signature algorithm in the first release (Ed25519 via
  JOSE `EdDSA`), never accept `none`, caller-selected algorithms, unprotected
  security headers, remote key URLs, or algorithm/key confusion;
- sign the exact canonical NCP payload and protected context containing the exact
  route, message class, stable-core digest, security-state digest, key epoch,
  issuer/principal, intended audience, and profile type;
- resolve `kid` only in a bounded, locally authenticated, content-addressed
  deployment manifest that maps keys to principal/entity/role/planes and validity;
- require the signed identity to equal the inner claim and authorization manifest;
- apply session/stream/operation replay rules after signature and route binding but
  before side effects;
- fail closed on key expiry, revocation, ambiguity, missing audience, unknown
  critical fields, invalid UTF-8/base64, duplicate JSON keys, or size excess;
- support overlap-based rotation without accepting a retired epoch; and
- retain cross-language known-answer, mutation, substitution, confusion,
  downgrade, and performance evidence.

This recommendation uses standardized JWS framing rather than inventing signature
serialization. It still requires a security architecture review, threat model,
cryptographic library review, and measured deadline impact. If that review selects
a terminating ingress instead, the ADR must prove equivalent per-message actor,
route, rotation, revocation, anti-confusion, and provenance properties; generic
Zenoh ACL inference is not equivalent.

Primary standards and substrate references:

- [RFC 7515: JSON Web Signature](https://www.rfc-editor.org/info/rfc7515/)
- [RFC 8037: EdDSA for JOSE](https://www.rfc-editor.org/info/rfc8037/)
- [RFC 8725: algorithm, issuer, audience, and cross-type validation guidance](https://www.rfc-editor.org/info/rfc8725/)
- [RFC 8446: TLS 1.3](https://www.rfc-editor.org/info/rfc8446/)
- [Zenoh `Sample` API](https://docs.rs/zenoh/latest/zenoh/sample/index.html)
- [Zenoh default configuration and ACL model](https://github.com/eclipse-zenoh/zenoh/blob/main/DEFAULT_CONFIG.json5)

### F07 — the plant cannot report a protocol-level command disposition

A successful publisher call is not proof that the body received, admitted, applied,
rejected, superseded, expired, or physically stopped on a command. Haldir's Gate
receipt proves Gate processing, not plant execution. Current NCP documents correctly
admit this limitation, but the named physical-body use case needs a generic,
authenticated body-issued disposition before the stable core freezes.

Add a bounded command-disposition message on the observation/control telemetry
surface. It must bind the exact command publisher stream position, command digest,
session/transcript, plant body identity, body-local monotonic disposition sequence,
and one closed state such as `received`, `rejected`, `superseded`, `expired`,
`admitted`, `applied`, `failed`, or `unknown_after_boundary`. Define which states
are terminal and forbid a later stronger claim after an ambiguous terminal state
without a new command. “Applied” means the defined software/hardware boundary
accepted the command at a recorded instant; it never means the physical world
achieved the requested state. A separate stop disposition can report the boundary
latch but cannot certify a universal physical zero-safe condition.

### F08 — authority coordination does not yet close multi-writer topology

The authority lease model is strong locally, but the specification still admits
unresolved “who steps when” and multi-writer coordination. Stable 1.0 must define a
single current authority term per session generation and plane, deterministic
transfer/revocation, exact holder identity, and what happens to in-flight commands
and lifecycle operations at the boundary. A controller cannot acquire action
authority merely because it can publish a valid frame.

The formal model and implementation must prove that two distinct principals cannot
both hold live action authority for the same session/term under the modeled clock
and fault assumptions. If plant and simulation sessions have separate authority,
their terms and operations must remain disjoint.

### F09 — extension traffic currently occupies stable NCP routes

Galadriel and Crebain use a project-owned `SidecarEnvelope` with kind
`galadriel_pid_observation` on an NCP named perception route. The code explicitly
states that this payload is not an NCP normative message and has no server-issued
generation. Native NCP 1.0 cannot permit non-NCP payloads on a stable typed NCP
route, because subscribers would apply NCP route/session/security assumptions to a
different contract.

Move the project-owned sidecar to a separately versioned extension namespace whose
route cannot be mistaken for stable NCP. If Galadriel data is also required on NCP,
write a narrow adapter that emits a valid standard `SensorFrame` or
`ObservationFrame` with negotiated named channels, live session generation,
declared stream, exact units/schema, and authenticated producer. Do not add
Galadriel-specific scientific fields or kinds to the generic NCP core.

### F10 — one Crebain ESTOP path bypasses full envelope validation

Both inspected Crebain worktrees contain a legacy path that recognizes raw JSON
`mode="estop"` and constructs a minimal ESTOP before full wire validation. NCP 1.0
permits authenticated ESTOP to omit only the authority lease. It does not permit a
malformed, wrong-session, wrong-route, wrong-principal, incompatible, or oversized
envelope to reach the latch.

Delete the bypass during native-1.0 migration. Apply byte/structure limits,
duplicate-key rejection, exact kind/version, full typed validation, verified actor
and plane, exact route/session generation, declared stream, and security state
before ESTOP latch mutation. Then permit the validated ESTOP to omit a lease so a
stale lease cannot suppress a fail-safe request.

### F11 — Engram and Prisoma scientific documentation has a semantic conflict

Engram architecture prose says Prisoma can replace absent language variable `L`
with zeros. Prisoma's current scientific contract says absent `L` is excluded,
never backfilled, and an abstention has no numeric placeholder. Zero-filling changes
the estimand and can create spurious statistical structure.

The integration must transmit an explicit availability/missingness contract and
exclude unavailable axes. Preserve `calibrated_posterior=false` and
`is_simulation_output=true`; protocol success cannot promote a population, measure,
estimator, or application gate.

### F12 — formal verification is not yet part of canonical NCP

NCP has extensive executable tests and bounded state-machine checks, but no
canonical `formal/` program. Haldir has a bounded TLA+ authority model and Prisoma
has narrow Z3 obligations; neither proves NCP or transfers automatically to it.

Add bounded TLA+/TLC models for distributed lifecycle/authority and SMT or
exhaustive transition obligations for narrow algebraic properties. Add refinement
tests that execute the same traces against Rust. State exact assumptions and model
bounds. A green model checker proves only the encoded abstraction; it does not
prove cryptography, code refinement, hardware safety, liveness outside fairness
assumptions, or release readiness.

### F13 — dependencies and registry identities remain release blockers

The locked Zenoh graph retains `RUSTSEC-2026-0041` through `lz4_flex`. Compression
is disabled and checked, but the advisory remains a publication hold until the
upstream graph is patched or a separately reviewed policy decision is made. The
intended crates.io `ncp-core` and PyPI `ncp` names currently refer to unrelated
projects. A stable release cannot rely on names the publisher does not control.

Select owned, collision-free package names, test fresh installs, update every
manifest/import/document/generated package reference coherently, and retain
registry ownership evidence before publication. Never describe an unpublished
local archive as the registry package.

### F14 — current “wire 0.8” comments leak into present 1.0 surfaces

Several source comments and generated schema descriptions say “Wire 0.8” for
fields retained in the 1.0 candidate. Historical origin is useful, but current
generated API descriptions can be read as saying the field is not a 1.0
requirement. Change source comments to “introduced in 0.8; retained/required in
1.0” where historically relevant, regenerate all derived artifacts, and keep
frozen 0.8 baselines untouched.

## 6. Ecosystem-specific audit conclusions

### 6.1 Engram / Paper2Brain

Engram has the only active native-1.0 consumer work. Its Python implementation
already contains server-issued generations, leases, operation digests,
idempotency/receipts, bounded caches/tombstones, explicit ESTOP generation cuts,
and fail-closed limits. Those are valuable implementation inputs, not authority to
fork NCP.

Required direction:

- keep canonical protocol changes in NCP first; pass, commit, and push them before
  running Engram's mirror sync;
- update Engram's mirror, Python runtime, descriptor, fixtures, schemas, transport,
  examples, and tests in one migration series;
- model Engram's simulation-service role separately from Engram's controller role
  toward Crebain/Haldir;
- replace silent observation-epoch rollover with explicit stream redeclaration;
- make arbitrary `NCP_CONTRACT_ROOT` overrides development-only and impossible in
  a certification/install path;
- keep `production-secure` unavailable until the selected authenticated-envelope
  or terminating-ingress design is implemented and live-tested;
- correct the Prisoma missing-`L` description; and
- obtain installed-artifact, cross-process, real-NEST, live-security, and fault
  evidence without claiming posterior calibration or paper reproduction.

### 6.2 Haldir

Retain `haldir-ncp08` and its frozen evidence as immutable history. Create a
parallel native `haldir-ncp10` adapter; do not rewrite old fixtures to look current.
Haldir cannot be a transparent NCP identity proxy because native 1.0 does not grant
delegation. It must be the enrolled NCP commander/lease holder/command publisher;
upstream signed controller intents remain Haldir-local inputs.

The native adapter must bind the exact live generation, session transcript, plant
profile, security state, declared command stream, authority lease, source frame,
channels/units, and route. Preserve one allocator across Active/HOLD/ESTOP. After
an ambiguous fail-safe publish, block Active until a fresh-position fail-safe is
definitely accepted at the declared boundary. Use NCP command dispositions when
available, while keeping Haldir's local CBOR evidence out of NCP stable wire.

### 6.3 Galadriel

Galadriel remains read-only. Move its project-owned envelopes out of stable NCP
keyspace, retain their independent schema/version, and separately implement an NCP
observer adapter if standard NCP frames are needed. A payload `producer_id` is a
claim, not a signature. The native observer must attach through the authenticated
descriptor exchange and bind exact generation, session type, transcript, streams,
channels, profile, full contract identity, and verified producer provenance.

If the sidecar remains on its own extension bus, its handoff/backpressure policy may
remain project-owned. If it consumes an NCP plane, it must implement that plane's
specified queue and loss-accounting policy exactly rather than relabeling
`DropNewest` as NCP behavior.

### 6.4 Crebain and the producer branch

Migrate canonical `sepahead/crebain` first. Rebase or retire the producer branch
afterward; do not maintain two consumer-specific NCP forks. Remove the minimal raw
ESTOP bypass. Crebain's plant body must own the content-addressed plant profile,
safe actions, local watchdog, hardware/local ESTOP boundary, reset generation cut,
command admission, and command dispositions. NCP input cannot directly actuate
hardware without the plant governor.

Keep the bridge dormant/off by default until its Tauri commands, configuration,
security, and plant-authority composition are intentionally registered and tested.
Move Galadriel project envelopes to their extension route or translate to standard
NCP frames as specified above.

### 6.5 Prisoma

Retain the complete wire-0.8 fault observatory as frozen historical evidence. Add a
separate wire-1.0 observer, fixtures, manifests, and fault corpus rather than
relabelling 0.8 outputs. Join data only after authenticated observer attachment and
exact generation/stream declarations. A raw session wildcard subscription remains
diagnostic and cannot authorize dataset inclusion.

Preserve Prisoma's run log as source of truth and four scientific gates. Missing
variables are excluded, never zero-filled. Transport integrity is not delivery
completeness, PID validity, causal identification, calibration, or application
validity. Existing SMT proofs apply only to their encoded publication semantics.

### 6.6 Public repositories and selected work

The public `sepahead/engram` repository is a placeholder distinct from the active
private `Paper2Brain` implementation. Public profile text must not imply that the
placeholder is the installed native-1.0 peer. The current NCP GitHub description is
accurate because it says HEAD is an unreleased, release-blocked candidate and
`v0.8.0` is latest.

Do not change descriptions, topics, cards, ecosystem diagrams, or README release
language until their corresponding migration/release evidence exists. After a real
release, update the source generator/data for the profile cards and diagrams, then
regenerate; do not hand-edit generated SVG or generated README blocks. Galadriel
may be shown as an optional/read-only extension consumer only with that boundary
visible. Every repository card should distinguish research intent, implemented
surface, and certification status.

## 7. Blueprint progress index

This index tracks construction of the blueprint itself. It does not track NCP
release completion.

| Part | Scope | Status | Evidence |
|---|---|---|---|
| P0 | mandated NCP documents and boundary | `LOCAL_PASS` | source cut and digest recorded above |
| P1 | archive, local consumers, and public metadata inventory | `LOCAL_PASS` | archive digest and mutable snapshot recorded above |
| P2 | first-principles blockers and ecosystem conclusions | `LOCAL_PASS` | findings F01–F14 above; implementation remains open |
| P3 | target 1.0 architecture and normative decision records | `IN_PROGRESS` | to be added |
| P4 | formal, executable, statistical, security, and fault verification program | `OPEN` | to be added |
| P5 | exact implementation task DAG and per-repository file/runbook detail | `OPEN` | to be added |
| P6 | release, package, documentation, GitHub, rollback, and incident runbook | `OPEN` | to be added |
| P7 | triple review, repository gate, commit, and push receipts | `OPEN` | to be added |

The implementation task IDs will use prefixes `B` (bookkeeping/decisions), `N`
(canonical NCP), `F` (formal/verification), `E` (Engram), `H` (Haldir), `C`
(Crebain), `G` (Galadriel), `P` (Prisoma), `X` (cross-ecosystem campaigns), and
`R` (release/public metadata). Dependencies, ten-lens findings, acceptance, and
receipts will be explicit for every task.
