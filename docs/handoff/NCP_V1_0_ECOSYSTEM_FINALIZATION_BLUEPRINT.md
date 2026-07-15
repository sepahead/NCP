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

- allow exactly one pinned, fully specified signature algorithm in the first
  release (JOSE `Ed25519`), never accept deprecated polymorphic `EdDSA`, `none`,
  caller-selected algorithms, unprotected
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
- [RFC 9864: fully specified JOSE algorithms](https://www.rfc-editor.org/info/rfc9864/)
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

### F15 — required authority leases have no stable wire lifecycle

The Rust authority machine can acquire, renew, transfer, reconnect, and retire a
lease, but the stable wire exposes no RPC that requests or returns those
transitions. A host can inject a process-local `AuthorityLease`; an independent
commander and body cannot establish one using only the advertised stable protocol.
Possession of self-constructed lease bytes must never become the missing protocol.

Add body/service-issued acquire, renew, transfer, release, and status operations.
The requester asks for authority and a bounded duration; the authoritative session
body chooses the term, lease identifier, enforcement deadline, and result. A
transfer needs the current holder or an enrolled overriding operator, but the body
still issues the replacement. Every operation is authenticated, idempotent, bound
to the exact session/transcript/security epoch, and returns a body-issued receipt.
An open session begins non-actuating; opening alone does not create authority.

### F16 — the security-state digest binds paths, not installed public trust state

The current projection hashes configured CA/certificate/private-key path strings
but deliberately not the file bytes. Avoiding private-key serialization is correct;
using a path as the negotiated identity of public trust material is not sufficient.
Two machines can share `/etc/ncp/ca.pem` while holding different trust anchors, and
one path can change after preflight.

Redefine the semantic security-state projection to bind public trust-anchor and
leaf-certificate DER fingerprints, enrolled signing public-key fingerprints and
epochs, authority/ACL/audience manifest digests, revocation-set digest and epoch,
endpoint/service identity, profile, and downgrade policy. Never hash or expose a
private key. Retain file paths only as local deployment evidence, reopen material
with race-resistant handles where supported, and revalidate identity/validity at
use. A changed public trust state requires a controlled security-epoch transition
or fail-safe session retirement; it cannot inherit the old digest.

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

## 7. Required target architecture

This section is the implementation target discovered by the audit. It is not
normative until the corresponding ADRs are reviewed, the canonical sources are
changed together, and the candidate is rebaselined. An ADR may refine a name or
encoding, but it may not remove an invariant below without recording an equally
strong alternative and repeating all dependent reviews.

### 7.1 Architectural laws

The stable 1.0 design must obey these laws:

1. **One meaning per message.** Simulation-service lifecycle and plant-control
   lifecycle are distinct typed protocols over a shared session substrate.
2. **The responder issues incarnation.** The simulator service or plant body issues
   `SessionRef.generation`; no caller or observed frame chooses it.
3. **The body grants action.** The session responder issues and enforces authority
   leases. A commander proposes; it does not self-authorize.
4. **Authentication precedes interpretation.** Production input is bounded, its
   signature and protected route context are verified, and its enrolled actor is
   established before payload identity or semantic fields can authorize anything.
5. **Routes are part of the message context.** A payload valid on one exact route,
   plane, session, message class, or audience is invalid on another.
6. **Negotiation is transcript-bound.** Contract, roles, session type, channels,
   profiles, plant, extensions, and security state cannot change between discovery,
   open, attach, stream declaration, authority, and receipt without an explicit
   revision transition.
7. **Streams are declared.** No data frame creates or rotates a stream epoch.
8. **Unknown never grants.** Unknown/default session types, roles, planes,
   capabilities, security algorithms, disposition states, authority states,
   extensions, and lifecycle states are non-authorizing or rejected as specified.
9. **The plant remains final authority.** A well-formed command is only a proposal
   to the plant governor. NCP cannot certify physical response or universal safety.
10. **Stable core and extensions do not share keyspace.** Project payloads cannot
    masquerade as stable NCP by using a stable route.
11. **Every mutation is idempotent and receipted.** Open, close, step, run, stream,
    authority, observer, rekey, and disposition-query transitions have bounded
    idempotency and explicit unknown-outcome behavior.
12. **Resource admission is pre-allocation.** Every encoding layer, signature
    wrapper, payload, collection, queue, store, retry, trace, and decompression path
    has a finite checked budget before semantic allocation or side effects.

### 7.2 Stable identity hierarchy

Replace the current overloaded identity signals with a hierarchy whose members have
separate purposes:

| Identity | Construction | Wire role | Compatibility rule |
|---|---|---|---|
| `wire_version` | literal `1.0` | major stable protocol selector | exact match |
| `stable_core_digest_sha256` | SHA-256 over a generated manifest of every stable wire-semantic source | hard native-1.0 compatibility identity | exact match before session success |
| `normative_release_digest_sha256` | current complete normative manifest digest | release/citation identity | exact in certified artifact sets; diagnostic during explicitly labelled development only |
| `corpus_digest_sha256` | mandatory conformance manifest/corpus | proves tested expectation set | exact in conformance and certification reports |
| `compact_proto_hash` | existing FNV proto hash | short diagnostic and migration aid | never sufficient to authorize compatibility |
| extension digest | SHA-256 of one extension manifest and schemas | optional feature identity | exact for an accepted extension |
| package build identity | immutable source/tag/attestation subject | installed implementation identity | retained in evidence, not used as protocol authority |

`stable_core_digest_sha256` must be generated, not typed into multiple files. Its
input manifest must include at least the stable proto, message schemas, canonical
encoding rules, typed digest projections, key grammar, planes/QoS, limits, closed
registries, security envelope/profile, authority/lifecycle/idempotency rules,
plant-profile rules, and mandatory behavioral requirements. It must exclude
candidate gate status, generated copies, informative prose, performance results,
and package metadata. The generator records ordered paths and individual SHA-256
digests so two implementations can reproduce it.

After stable `v1.0.0`, those core inputs are immutable. Errata that change behavior
require a new major wire; explanatory text can change only outside the stable-core
input. A vulnerability may deprecate or revoke 1.0 without silently redefining it.

### 7.3 Shared session substrate

Introduce these closed core types. Names are proposed and should be preserved
unless an ADR proves a clearer unambiguous alternative.

#### `SessionType`

```text
unknown              non-authorizing; invalid for open success
simulation_service   neural/model simulation lifecycle
plant_control        controller-to-plant closed-loop lifecycle
```

No “generic” success value is permitted. Future session types are extensions or a
new major core; an old implementation does not reinterpret them.

#### `ContractIdentity`

Required members:

```text
wire_version
stable_core_digest_sha256
normative_release_digest_sha256
corpus_digest_sha256
compact_proto_hash
```

All digests use lowercase fixed-length hexadecimal with exact validation. A missing
member cannot inherit the local value.

#### `InitiationContext`

Pre-session operations need idempotency without fabricating a generation:

```text
operation_id                 canonical UUIDv4, selected once by caller
request_digest_sha256        typed digest of immutable request semantics
deadline_utc_ms              positive JSON-safe integer
retry                        false initially; true only on exact retry
```

The responder keys pre-session idempotency by authenticated principal,
`operation_id`, exact request kind, and request digest. A duplicate exact request
replays the exact terminal response; a conflicting digest fails; an ambiguous
boundary returns `outcome_unknown` and never opens a second generation by guess.
Stores are bounded and durably snapshotted for production.

#### `SessionDescriptor`

A successful open and observer attachment return the same bounded authoritative
descriptor shape:

```text
session                       {session_id, server-issued generation}
session_type                  closed SessionType
descriptor_revision           positive JSON-safe integer, starts at 1
state_version                 positive JSON-safe mutation state
responder_identity            verified body/simulator IdentityClaim
commander_identity            verified enrolled commander IdentityClaim
contract_identity             exact ContractIdentity
security_binding              profile, semantic state digest, security epoch,
                              authority-manifest digest, audience id
negotiation_transcript_digest SHA-256 typed transcript digest
plant_profile_digest          required only for plant_control
simulation_provenance_policy  required only for simulation_service
selected_capabilities         sorted, unique closed stable IDs
selected_extensions           sorted exact ExtensionManifestRefs
sensor_channels               selected ChannelSpecs
command_channels              selected ChannelSpecs
observation_channels          selected ChannelSpecs
created_at_utc_ms             responder clock, diagnostic/audit
status                        non-authorizing lifecycle value at issue
```

The mutually exclusive session-type fields are schema- and semantics-enforced.
Unknown fields remain bounded forward-compatible metadata only and are excluded
from all authorization unless a registered digest projection explicitly includes
them. The descriptor is signed/authenticated as a control-plane response.

### 7.4 Split lifecycle messages

Replace overloaded `open_session` with two request/response pairs.

#### Simulation service

`OpenSimulationSession` on
`{realm}/rpc/open_simulation_session` contains:

- envelope version/kind, `InitiationContext`, `ContractIdentity`, authenticated
  commander identity, security binding, and offered capabilities/extensions;
- requested logical `session_id`;
- current `NetworkRef`, `RecordSpec`, `StimulusSpec`, `SimConfig`, and entity
  bindings; and
- an explicit provenance/non-claim policy that can only select
  `calibrated_posterior=false`, `is_simulation_output=true`, and
  `advisory_only=true` in stable 1.0.

`SimulationSessionOpened` returns success/error, `SessionDescriptor`, resolved
simulation configuration, `SimProvenance`, and a responder receipt. Failure returns
no live `SessionRef`. `StepRequest`, `RunRequest`, `StimulusFrame`, and
`ObservationFrame` are accepted only for this session type. Their exact
authorization and idempotency semantics remain session-scoped.

#### Plant control

`OpenPlantSession` on `{realm}/rpc/open_plant_session` contains:

- the common initiation, identity, security, contract, capability, and extension
  offers;
- requested logical `session_id` and exact intended body entity/audience;
- required and optional sensor, command, status, and disposition `ChannelSpec`
  offers;
- requested rates/deadlines/queue profile within protocol limits; and
- the commander's expected plant-profile digest, or an explicit request for the
  body's descriptor without authority to actuate.

`PlantSessionOpened` is issued by the body and returns the common descriptor, exact
body-owned plant-profile digest, selected channels/rates/QoS, initial non-actuating
state, and receipt. A mismatch in a required channel, unit, arity, profile,
stable-core digest, security state, audience, or capability fails before creating a
live session. Opening never grants an authority lease.

#### Shared close and type-specific operations

`CloseSession` can remain shared because it carries exact `SessionRef`, transcript,
operation context, authenticated commander, and live authority. Its responder
validates the stored session type. `Step` and `Run` reject plant sessions.
Plant-frame publication rejects simulation sessions. An ESTOP reset remains
body-local or separately authenticated out-of-band in 1.0 and always retires the
generation; there is no remote reset RPC.

### 7.5 Capability negotiation and transcript

Replace the controller-specific `Capabilities` ambiguity with typed offer and
selection records:

```text
PeerCapabilityOffer
  identity
  intended_session_type
  role
  stable_capabilities[]
  extension_offers[]
  channel_offers[]
  limits_offer
  contract_identity
  security_binding

CapabilitySelection
  exact accepted stable capabilities
  accepted/rejected extension refs with closed reason
  exact selected channels and limits
  responder identity
```

Stable capabilities are closed, sorted, unique, and role/session-type scoped.
Unknown required capability fails. Unknown optional extension is explicitly
rejected in the response without enabling its behavior. Capability absence never
selects a default that grants a channel, mode, security profile, or authority.

The typed negotiation transcript is the closed canonical projection of:

```text
request kind and initiation request digest
both verified identities and roles
session type and logical session id
ContractIdentity from both parties
security binding and audience
complete offers and exact selection
plant profile or simulation provenance policy
channel names, kinds, units, arities, requirements and limits
extension manifest refs and decisions
responder-issued SessionRef and descriptor revision
```

Hash with a registered domain separator. Both parties retain the exact canonical
projection. All session-scoped mutations, leases, declarations, observer
attachments, frames, security transitions, dispositions, and receipts carry or
derive the exact transcript digest. Tests mutate every member independently.

### 7.6 Observer attachment

Add `AttachObserver` on `{realm}/rpc/attach_observer`. Its pre-session idempotency
context is bound to the observer principal, target logical `session_id`, intended
responder/body, requested planes/channels, and audience. The observer does not
supply a generation; the authenticated body resolves the current live generation.

`ObserverAttached` returns:

- exact `SessionDescriptor` and current descriptor revision;
- an `ObserverGrant` with random grant ID, observer principal/entity, permitted
  exact route set or closed route templates, planes/channels, issued/expiry times,
  security epoch, and revocation epoch;
- all currently active `StreamDescriptor` objects the observer may consume;
- current high-water positions only as diagnostic starting points, never as proof
  that earlier data was complete; and
- a responder receipt.

The grant is read-only and cannot be converted into authority, reset, publish,
open, close, step, run, or stream-declaration rights. The transport ACL or trusted
gateway enforces the same exact routes. Fleet discovery is a separate
deployment-owned directory and cannot leak unauthorized descriptors. Attachment
expiry/revocation stops new delivery and dataset admission but does not fabricate
missing data or erase retained audit evidence.

Add `DetachObserver` as an idempotent cleanup. Body-initiated revocation increments
the revocation epoch and emits an authenticated control/audit event. Reattachment
after session restart returns the new generation; the observer must discard all
old stream admission state.

### 7.7 Executable stream lifecycle

Add these control-plane operations:

```text
DeclareStream  -> StreamDeclared
RetireStream   -> StreamRetired
```

`DeclareStream` is sent by the enrolled publisher and includes exact session,
transcript, descriptor revision, plane, exact route, message kind, proposed fresh
UUIDv4 epoch, starting sequence `1`, complete channel/schema selection, QoS profile,
publisher identity/key epoch, and idempotency context. The body/session authority
validates the publisher role and route, records one immutable descriptor, and
returns a receipt. A publisher may not declare another principal's stream.

One `StreamDescriptor` contains:

```text
stream_id                     stable descriptor UUID, not a sequence
session and session_type
negotiation_transcript_digest
descriptor_revision
plane and exact route
message_kind
publisher principal/entity/role
epoch
first_seq = 1
channel/schema selection
qos and queue/loss policy
security epoch and audience
declared_at_utc_ms
retired flag/reason when applicable
```

Receivers admit a frame only after exact descriptor lookup and signature/actor,
route, session, epoch, kind, channel, transcript, and monotonic sequence checks.
Expiry, silence, HOLD, and reconnect never reset the high-water mark. On process
restart, sequence exhaustion, security transition, schema/channel change, or
publisher change, retire the old descriptor and declare a fresh epoch. Attempting
sequence `2^53-1` consumes it at most once; the publisher becomes silent before
overflow and cannot auto-mint an epoch.

`RetireStream` is authenticated/idempotent and records the final attempted and
definitely published positions separately. It does not promise that subscribers
received the final frame. Session close retires every stream. A retired stream
cannot be reopened or refreshed.

### 7.8 Body-issued authority protocol

Add exact control routes and response kinds:

| Request route | Success response | Purpose |
|---|---|---|
| `{realm}/rpc/acquire_authority` | `AuthorityGranted` | body grants a new strictly higher term to an enrolled commander |
| `{realm}/rpc/renew_authority` | `AuthorityRenewed` | body extends an unexpired current holder under the same term/lease identity |
| `{realm}/rpc/transfer_authority` | `AuthorityTransferred` | current holder or authorized operator asks body to issue a higher term to another enrolled commander |
| `{realm}/rpc/release_authority` | `AuthorityReleased` | holder/operator asks body to retire current authority and enter/remain fail-safe |
| `{realm}/rpc/query_authority` | `AuthorityStatus` | authenticated read of current non-secret authority state; no mutation |

Every mutation contains exact session/transcript/security epoch, operation context,
requester identity, requested holder where applicable, requested bounded duration,
and reason code. The body samples its clocks, enforces maximum duration, chooses the
term and random lease ID, records a monotonic enforcement deadline, and returns a
signed receipted `AuthorityLease`. UTC issue/expiry fields are audit/interchange
metadata; the body never relies on a remote clock to enforce expiry.

Change `AuthorityLease` semantics so its issuer is the authoritative session body,
not a self-asserting commander. It binds body issuer, holder principal/entity,
session generation, transcript, security epoch, term, lease ID, issued/expiry UTC,
and maximum duration. The plant/simulator retains the local monotonic deadline and
state version used to issue it. The holder cannot lengthen, rewrite, or transfer
the lease bytes.

Safety rules:

- initial open state is HOLD/INIT without authority;
- only one unexpired holder exists per session generation and authority plane;
- acquisition requires a term greater than every current/retired term;
- renewal at equality with the enforcement deadline fails and transitions to HOLD;
- transfer/release retires the old lease before the new holder can act;
- an operator may request override only with an explicit manifest bit; the body
  decides and records it;
- reconnect proves the same live lease and security state and cannot extend time;
- revocation, body restart without durable clock/state continuity, ESTOP reset, or
  generation retirement invalidates authority;
- an Active command and Step/Run/Close mutation require the exact current lease;
- authenticated same-session ESTOP may omit the lease only after full envelope,
  route, actor, session, stream, and security admission; and
- lease query/status is non-authorizing and cannot be replayed as a grant.

### 7.9 Production authenticated envelope

For `production-secure`, carry every stable NCP JSON payload in the flattened JWS
JSON Serialization from RFC 7515. The outer object has exactly `protected`,
`payload`, and `signature`; an unprotected `header` member is forbidden. Each value
is bounded base64url without padding. The decoded payload must be the exact NCP
canonical JSON bytes for the typed message; round-trip canonicalization must match
byte-for-byte before semantic acceptance.

The decoded protected header is also required to be exact canonical JSON with this
closed profile:

```text
alg                  exactly `Ed25519` from RFC 9864; reject deprecated `EdDSA`
kid                  bounded enrolled key id; never a URL or filesystem path
typ                  exact NCP signed-envelope media/profile type
cty                  exact canonical NCP JSON content type
crit                 exact sorted set of all ncp_* protected members below
ncp_profile          production-secure
ncp_route            exact actual transport key/selector
ncp_message_class    exact request/response/frame kind class
ncp_stable_digest    exact stable_core_digest_sha256
ncp_security_digest  exact semantic security-state digest
ncp_security_epoch   exact current security epoch
ncp_issuer           exact enrolled principal id
ncp_audience         exact enrolled recipient or audience-group id
ncp_key_epoch        positive registered key epoch
```

Do not accept `alg=none`, another algorithm, a key supplied by the message, `jku`,
`jwk`, `x5u`, embedded certificate chains, omitted/unknown critical fields,
unprotected security metadata, or permissive library defaults. Configure the JWS
library with the one allowed algorithm and resolve `kid` only from the locally
authenticated authority manifest. Validate media type, issuer, audience, message
class, route, digests, epochs, key use, key validity, and revocation independently
of signature success. Require the inner `IdentityClaim` to equal the manifest actor
and protected issuer.

The actual transport route is adapter input, never copied from the envelope. Exact
equality with `ncp_route` is checked before payload semantics. RPC responses use the
requester's principal as audience. Action uses the exact body principal. Pub/sub
perception/observation uses a content-addressed audience group whose manifest
enumerates readers; changing membership changes the security state/epoch and ACL.

TLS 1.3 mutual authentication and default-deny ACLs remain mandatory for remote
production transports to provide confidentiality, endpoint protection, and route
minimization. End-to-end JWS supplies application-visible publisher provenance
through routers; it does not make TLS optional. `dev-loopback-insecure` carries raw
canonical JSON only on loopback/UDS, advertises unmistakable insecure state, and
cannot negotiate, wrap, or downgrade into production.

#### Semantic security-state projection

The new projection must hash semantic public state:

```text
profile and exact endpoint/service identity
TLS minimum/maximum and required mutual-auth policy
sorted trust-anchor DER SHA-256 fingerprints
local leaf public certificate DER fingerprint and identity
sorted signing-key {kid, public-key fingerprint, algorithm, key epoch,
                    principal/entity/role/planes, not-before/not-after, status}
authority manifest digest
audience-group manifest digest
rendered effective ACL digest
revocation-set digest and monotonic revocation epoch
downgrade=false and insecure_status=false
```

Never include secret/private bytes. Configuration paths are recorded separately in
local deployment provenance. Use handles/permissions/HSM or protected keystore as
platform policy requires. At startup and rotation, validate certificate chains,
service names, validity, public-key match, file/keystore protection, ACL equivalence,
and digest before exposing a route.

#### Rotation and revocation

Add an idempotent `RebindSecurity` session operation. Planned rotation may advertise
an overlap key already present in a new authenticated manifest. Both peers verify
the old live context and the new key/security state, the body increments descriptor
revision/security epoch, returns a new transcript-bound descriptor, retires old
stream declarations, and requires redeclaration. The old key stops at the recorded
boundary. Revocation is not an overlap transition: immediately deny the key, move
affected authority to fail-safe, retire affected sessions/streams as policy
requires, and never clear ESTOP.

If a terminating-ingress alternative is selected by reviewed ADR, it must produce
an equivalent signed/local attestation consumed through the same
`AuthenticatedActor` API, preserve original actor and exact route, prevent
multiplexing confusion, survive router topology, and meet the same rotation,
revocation, replay, cross-language, and fault tests. Merely knowing that some client
passed a router ACL is insufficient.

### 7.10 Command disposition and stop evidence

Add `CommandDisposition` as a body-published stable message on the named observation
route:

```text
{realm}/session/{session_id}/observation/command-disposition
```

It contains:

```text
ncp_version and kind
session and session_id
negotiation_transcript_digest
its own declared body stream position
body identity
command publisher stream position
canonical command digest
command mode
closed disposition state and reason code
body-local monotonic event time
optional software/hardware boundary id from plant profile
optional applied setpoint digest (never raw secret payload by default)
state_version
security epoch
```

Closed states and required semantics:

| State | Meaning | Terminal for this boundary? |
|---|---|---|
| `received` | complete command reached the named software ingress | no |
| `rejected` | body rejected it before application; closed reason required | yes |
| `superseded` | a newer admitted command made it inapplicable | yes |
| `expired` | TTL/watchdog made it inapplicable | yes |
| `admitted` | plant governor accepted it for the named application boundary | no |
| `applied` | the named boundary accepted/wrote the setpoint at the recorded instant | yes for that boundary |
| `failed` | a definite boundary error prevented application | yes |
| `unknown_after_boundary` | body cannot distinguish application from failure after an ambiguous boundary | yes; never promote later by guess |
| `stop_latched` | named body-local stop latch entered | yes for the latch only |

Unknown/default state is invalid and non-success. A state transition table forbids
terminal contradiction and skips such as `received -> applied` only when the plant
profile explicitly defines that boundary as atomic. Dispositions are authenticated,
ordered on their own stream, retained in a bounded body journal, and queryable by
exact session/command position/digest through an idempotent control request. A gap
or absent disposition is unknown, never rejection or application.

“Applied” and `stop_latched` explicitly do not prove actuator motion, physical
effect, zero energy, hazard removal, or regulatory safety. Physical sensors,
hardware interlocks, and application-specific certification remain outside NCP.

### 7.11 Stable and extension keyspaces

Revise stable key grammar to enumerate message classes rather than letting payloads
borrow a neighboring route:

```text
{realm}/rpc/{registered_request_kind}
{realm}/session/{session_id}/sensor[/{registered_name}]
{realm}/session/{session_id}/command[/{registered_name}]
{realm}/session/{session_id}/observation[/{registered_name}]
```

Each declared exact route has one stable message kind/schema. A wildcard subscriber
may receive multiple declarations but dispatches only after descriptor lookup; the
route does not infer a kind.

Project-owned extensions live outside `/session`:

```text
{realm}/extension/{extension_id}/{manifest_digest}/{deployment_or_session_segment}/...
```

`extension_id` is an owned, registry-safe reverse-domain identifier or another
reviewed collision-resistant namespace. Every extension has a bounded manifest with
owner, version, digest, schemas, exact routes, encodings, security requirements,
limits, QoS, lifecycle, compatibility, and deprecation. Core ACLs do not grant
extension routes. Core fleet/session wildcards do not match them. An extension
cannot claim NCP core conformance merely because it references a session or is
listed in negotiation.

For Galadriel, use an owned extension ID such as
`org.sepahead.galadriel.observation.v1` only after its manifest and route are
reviewed. If an adapter emits stable NCP, it publishes a separately declared
standard frame; it does not wrap the project envelope on a core route.

### 7.12 Plane, QoS, and backpressure contract

Retain four authority planes but make subprofiles executable:

| Plane | Publisher | Core queue | Required behavior |
|---|---|---|---|
| control | enrolled commander/body/observer for the exact request | bounded 128 default | reliable request/reply, explicit overload rejection, operation deadline and idempotency |
| perception | enrolled body | capacity 1 per declared stream | replace latest; count overwritten positions and expose gaps, never synthesize |
| action | current commander or enrolled operator for allowed fail-safe | capacity 1 per declared stream | severity priority, one allocator across Active/HOLD/ESTOP, consume ambiguous attempts, block Active after ambiguous fail-safe |
| observation data | enrolled body | bounded 64 default | drop oldest and count; scientific consumers mark incomplete |
| observation disposition subprofile | enrolled body | bounded journal plus bounded delivery queue | never silently drop retained terminal state; backpressure/replay query and explicit retention exhaustion |

All capacities are negotiated only downward from protocol/deployment maxima; a
remote offer cannot allocate. Each metric is bounded and low-cardinality. Sequence
loss, local queue drop, transport rejection, retry, redelivery, and journal eviction
are distinct counters. Control overload returns a registered error without partial
state. A data-plane overload never refreshes TTL, lease, watchdog, or liveness.

### 7.13 Extension and future-evolution rules

To make stable 1.0 durable without pretending requirements never change:

1. Freeze core messages, field meanings, keys, digest projections, error meanings,
   and behavioral vectors after release.
2. Permit additive unknown JSON fields only as bounded non-authorizing metadata;
   old peers ignore them and no core decision depends on them.
3. Add optional functionality through exact extension manifests and separate routes.
4. Reject unknown required extensions; explicitly decline unknown optional ones.
5. Never promote an extension into core under wire `1.0`; a future core change is a
   new major wire with an explicit terminating gateway/migration.
6. Keep 0.8 and later released baselines immutable. Gateways label both source and
   target identities, terminate trust, reject ambiguous mappings, and never claim
   transparent interoperability.
7. Publish a deprecation/revocation record separately from immutable protocol
   history. Security response can forbid deployment of an old wire without editing
   what its messages meant.

### 7.14 Required ADR set and ratification gates

Create these ADRs before changing normative files. Each ADR must include considered
alternatives, threat/hazard analysis, state-machine effects, compatibility, limits,
wire examples, failure examples, formal properties, migration, rollback, and all
ten lens decisions.

| ADR | Decision | Required reviewers before `ACCEPTED` |
|---|---|---|
| ADR-001 | split simulation-service and plant-control sessions | NCP maintainer, Engram owner, Crebain body owner, independent protocol reviewer |
| ADR-002 | stable-core/release/corpus identity hierarchy and extension freeze | protocol + release/supply-chain reviewers |
| ADR-003 | production JWS authenticated envelope versus equivalent terminating ingress | two independent security/cryptography reviewers plus transport implementer |
| ADR-004 | observer attach, grants, descriptors, privacy and revocation | Prisoma, Galadriel, security reviewers |
| ADR-005 | explicit stream declaration/retirement and exhaustion | distributed-systems + all stream consumer owners |
| ADR-006 | body-issued authority operations and temporal model | safety, distributed-systems, Haldir, Crebain reviewers |
| ADR-007 | command disposition states, boundary meanings, journal and query | plant/safety, Haldir, Crebain reviewers |
| ADR-008 | extension namespace and Galadriel sidecar separation | protocol, Galadriel, Crebain reviewers |
| ADR-009 | security-state semantic digest, key rotation and revocation | security, operations, supply-chain reviewers |
| ADR-010 | exact per-plane QoS, retention and overload semantics | real-time/performance + consumer reviewers |

Ratification is blocked until:

- every named reviewer role has an identified human or independent team;
- every open question has a recorded decision or explicit exclusion;
- wire examples and negative examples can be represented in Rust and independent
  TypeScript without consumer-specific assumptions;
- the proposed formal models have no obvious counterexample under their declared
  bounds;
- resource estimates fit declared maxima and cryptographic deadlines in preliminary
  benchmarks;
- Engram, Haldir, Galadriel, Crebain, and Prisoma owners confirm their required use
  case is expressible without a private core fork; and
- the owner explicitly authorizes the deliberate pre-release wire rebaseline.

## 8. Verification, formal methods, and evidence program

The verification strategy is layered because no single tool can prove protocol
semantics, Rust implementation, cryptography, a distributed deployment, physical
safety, statistical performance, and scientific validity at once. Each layer has a
named claim boundary and a retained exact-source receipt.

### 8.1 Assurance layers and prohibited inference

| Layer | What it can establish | What it cannot establish by itself |
|---|---|---|
| schema/static validation | bounded shape, required fields, closed values and generated parity | temporal behavior, authentication, delivery, physical effect |
| unit/property/conformance tests | behavior on executed cases and generated domains | unexecuted states, independent interoperability, proof of absence |
| TLA+/TLC | safety/liveness of a finite abstract distributed transition system under stated fairness | code refinement, cryptography, unbounded systems, hardware |
| Z3 SMT obligations | validity/satisfiability of narrow encoded formulas | whole-protocol behavior or correspondence to implementation |
| Kani bounded model checking | bit-precise properties of selected Rust functions within unwind/object bounds | network environment, omitted code, unbounded loops, full distributed liveness |
| cryptographic KAT/negative corpus | library/profile agreement and rejection behavior for cases | private-key protection, CA operations, side channels, future cryptanalysis |
| live fault/security campaign | behavior of exact installed peers/configuration under injected faults | other builds, all networks, permanent physical certification |
| performance experiment | distributions and uncertainty for declared workloads/platforms | universal real-time guarantees or safety |
| consumer certification | exact named consumer/artifact interoperability | unnamed consumers or later commits |

Every report must state the layer and its exclusions. The phrases “formally
verified NCP,” “proved secure,” “zero failure rate,” and “certified safe” are
forbidden unless a narrower object and claim are named immediately.

### 8.2 Canonical formal directory and toolchain

Add a top-level `formal/` with:

```text
formal/README.md
formal/tools.lock.json
formal/tla/NcpSession.tla
formal/tla/NcpSession.cfg
formal/tla/NcpAuthority.tla
formal/tla/NcpAuthority.cfg
formal/tla/NcpStreams.tla
formal/tla/NcpStreams.cfg
formal/tla/NcpOperations.tla
formal/tla/NcpOperations.cfg
formal/tla/NcpObserver.tla
formal/tla/NcpObserver.cfg
formal/tla/NcpDisposition.tla
formal/tla/NcpDisposition.cfg
formal/tla/NcpSecurityEpoch.tla
formal/tla/NcpSecurityEpoch.cfg
formal/tla/NcpComposition.tla
formal/tla/NcpComposition.cfg
formal/smt/*.smt2
formal/kani/README.md
formal/traces/<model>/<configuration>/*.json
formal/results/<tool>/<source-and-config-digest>/*
```

`tools.lock.json` records exact release URL, version, SHA-256, license, runtime,
container digest where used, and the expected version output for TLA+ tools/JRE,
Z3, Kani/CBMC, Rust, and every trace converter. Download helpers require HTTPS,
verify SHA-256 before execution, never use an unpinned `latest` asset in CI, and
support an offline preseeded cache. Generated result directories are immutable
evidence artifacts; normal CI may upload them, while reviewed summary/digest
manifests are committed.

Use the official TLA+ tools/TLC distribution for distributed models, Z3 for narrow
SMT-LIB obligations, and a pinned Kani release for selected Rust transition code.
Kani harnesses must use explicit object and unwind bounds plus `kani::cover` checks
so an over-constrained proof cannot pass vacuously. Sanitizers, Miri, Loom,
property tests, and fuzzers are complementary test tools, not formal proofs.

Primary method references:

- [TLA+ tools and TLC](https://github.com/tlaplus/tlaplus)
- [TLC capabilities](https://lamport.azurewebsites.net/tla/tools.html)
- [Kani usage and proof harnesses](https://model-checking.github.io/kani/usage.html)
- [Z3](https://github.com/Z3Prover/z3)

### 8.3 TLA+ model decomposition

#### `NcpSession`

Model session type, logical ID, server-issued generation, lifecycle, descriptor
revision, transcript, plant/simulation discriminator, open idempotency, close,
reset, restart, and retirement.

Minimum finite constants:

```text
Principals = {body, simulator, commander1, commander2, operator, observer}
SessionIds = {s1}
Generations = {g1, g2}
SessionTypes = {simulation_service, plant_control}
DescriptorRevisions = 0..2
OperationIds = {op1, op2}
```

Exercise duplicate open, same operation with different digest, reply loss,
ambiguous commit, body restart before/after durable commit, close/reopen, ESTOP
reset, stale frame, and wrong session-type operation.

Required invariants:

- `TypeOK`;
- `GenerationIssuedOnlyByResponder`;
- `OneLiveGenerationPerLogicalSessionAtBody`;
- `RetiredGenerationNeverLive`;
- `ResetCutsGenerationAndAuthority`;
- `SimulationOperationNeverTargetsPlantSession`;
- `PlantFrameNeverTargetsSimulationSession`;
- `FailedOpenReturnsNoLiveGeneration`;
- `ExactOpenRetryDoesNotCreateSecondGeneration`; and
- `DescriptorRevisionNeverDecreases`.

#### `NcpAuthority`

Model body-issued terms, lease IDs, holder, requester/operator, UTC metadata,
body-local monotonic deadline, lifecycle, transfer, renewal, release, reconnect,
revocation, restart, and Active/Step/Run/Close admission.

Finite constants include two commanders, an operator, one body, terms `0..3`,
clock `0..4`, two leases, two security epochs, and both session types.

Required invariants:

- `LeaseIssuerIsBody`;
- `AtMostOneLiveHolderPerSessionAndPlane`;
- `ActiveImpliesCurrentGenerationAndUnexpiredLease`;
- `MutationImpliesCurrentLeaseAndIdempotencyContext`;
- `TermStrictlyIncreasesOnAcquireOrTransfer`;
- `RenewalNeverChangesHolderTermOrLeaseId`;
- `ExpiredLeaseNeverRevives`;
- `OldHolderCannotActAfterTransfer`;
- `ReleaseAndRevocationEnterNonActuatingState`;
- `ReconnectNeverExtendsDeadline`;
- `BodyRestartWithoutContinuityInvalidatesLease`;
- `OperatorOverrideRequiresManifestRight`;
- `SerializedLeasePossessionIsInsufficient`; and
- `EstopLeaseExemptionDoesNotBypassFullAdmission`.

#### `NcpStreams`

Model declarations, publisher actor, plane, exact route, epoch, sequence, attempted
versus definitely published position, receive high-water, duplicates, reorder,
silence, restart, exhaustion, retirement, queue overflow, and source correlation.

Required invariants:

- `PublishImpliesLiveDeclaration`;
- `DeclarationActorMatchesPublisher`;
- `RouteKindPlaneSessionTranscriptAllMatch`;
- `SequenceStartsAtOneAndStrictlyIncreases`;
- `AttemptConsumesPositionEvenWhenAmbiguous`;
- `NoSequenceReuse`;
- `NoEpochAdoptionFromFrame`;
- `NoSilentEpochRotation`;
- `RetiredStreamNeverAccepts`;
- `ExpiryOrSilenceNeverReanchorsHighWater`;
- `SourceIsCorrelationNotOwnSequence`;
- `QueueSizeNeverExceedsPlaneCapacity`;
- `AmbiguousFailSafeBlocksActiveUntilFreshFailSafeSuccess`; and
- `EstopPriorityNeverCrossesSessionOrActorBoundary`.

#### `NcpOperations`

Model reservation, immutable request digest, expected state, in-progress,
committed/rejected/cancelled/unknown outcomes, response loss, bounded replay cache,
durable snapshot, restart, principal transfer, and eviction/tombstone behavior.

Required invariants:

- `AtMostOneSemanticExecutionPerOperationKey`;
- `SameKeyDifferentDigestNeverExecutes`;
- `TerminalReceiptMatchesRequestAndResponder`;
- `ReceiptStateVersionNeverPrecedesExpectedState`;
- `AuthorityTransferCannotReplayAnotherPrincipalsResult`;
- `UnknownOutcomeNeverBecomesSuccessByRetryGuess`;
- `EvictionDoesNotPermitDuplicateExecutionWithinRetentionContract`;
- `CapacityExhaustionRejectsBeforeMutation`; and
- `SnapshotRestoreDoesNotWidenAuthorityOrDeadline`.

#### `NcpObserver`

Model attach without caller-supplied generation, body descriptor resolution, route
grant, grant expiry/revocation, detach, session restart, wildcard diagnostic input,
and attempted mutation/publish.

Required invariants:

- `ObserverNeverAcquiresCommanderOperatorOrBodyAuthority`;
- `AttachGenerationComesFromBody`;
- `GrantRoutesSubsetOfManifestAndRequest`;
- `ExpiredOrRevokedGrantAdmitsNoNewFrame`;
- `OldGrantDoesNotFollowNewGeneration`;
- `RawWildcardTrafficNeverCreatesDescriptor`;
- `UnauthorizedDescriptorIsNotDisclosed`; and
- `DetachDoesNotMutateSession`.

#### `NcpDisposition`

Model the command/disposition state graph, body journal, query, terminal states,
missing evidence, journal eviction, body restart, stop latch, and ambiguous
hardware/software boundary.

Required invariants:

- `DispositionReferencesExactlyOneAdmittedCommandIdentity`;
- `OnlyBodyPublishesDisposition`;
- `TerminalStateNeverTransitionsToContradictoryState`;
- `AppliedRequiresAdmittedOrDeclaredAtomicBoundary`;
- `UnknownAfterBoundaryNeverPromotesByGuess`;
- `MissingDispositionNeverMeansAppliedOrRejected`;
- `StopLatchedNeverMeansPhysicalZero`;
- `JournalQueryCannotFabricateEvictedEntry`; and
- `DispositionStreamObeysDeclarationAndSequenceRules`.

#### `NcpSecurityEpoch`

Model key IDs/epochs, manifest state, audience, exact route/message class, stable
digest, JWS verification result, revocation, planned overlap rotation, session
rebind, descriptor revision, stream retirement, and downgrade attempts. Cryptographic
unforgeability is an assumption; signature verification is a boolean relation whose
inputs must all be modeled explicitly.

Required invariants:

- `SemanticAdmissionImpliesSignatureVerified`;
- `VerifiedKeyMapsToExactInnerIdentityRoleAndPlane`;
- `ActualRouteEqualsProtectedRoute`;
- `AudienceAndMessageClassMatchUse`;
- `StableAndSecurityDigestsMatchSession`;
- `RevokedOrExpiredKeyNeverAdmits`;
- `UnknownAlgorithmNeverAdmits`;
- `ProductionNeverAcceptsRawOrInsecureEnvelope`;
- `DevelopmentProfileNeverNegotiatesAsProduction`;
- `OldKeyStopsAtCommittedRotationBoundary`;
- `SecurityChangeRetiresOldStreams`;
- `RevocationForcesFailSafeWithoutClearingEstop`; and
- `ExtensionRouteCannotSatisfyCoreRoutePredicate`.

#### `NcpComposition`

Compose the smaller models with reduced constants. This is the critical place to
find bugs that disappear in isolated proofs: open/authority reply loss, transfer
during stream rollover, observer attach during restart, revocation during ambiguous
Active/HOLD/ESTOP publication, security rotation with pending idempotent operation,
close with missing disposition, and session-type confusion.

Composition invariants include every safety property whose variables cross two
modules. Do not claim the conjunction of isolated model results proves the
composition.

### 8.4 Liveness and fairness boundary

Check liveness only with explicit environment assumptions. At minimum:

- if the body remains alive, clocks advance, a valid control request is delivered,
  and response delivery is weakly fair, the operation eventually reaches a terminal
  response;
- an unexpired holder that continually requests a valid release eventually reaches
  non-actuating state under the same delivery/processing assumptions;
- once the body clock reaches lease expiry, enabled fail-safe processing eventually
  enters HOLD/ESTOP if the body scheduler is weakly fair;
- a close eventually retires streams/session only if its admitted mutation and
  durable commit steps execute; and
- a declared frame is not guaranteed to reach an observer under best-effort QoS.

Do not assert eventual delivery, fail-safe actuation, or recovery during a permanent
partition, crashed body, unfair scheduler, exhausted storage, or failed physical
plant. TLC configurations that check liveness must record fairness operators and
must not use state/action constraints that invalidate the liveness conclusion.

### 8.5 Model non-vacuity, coverage, and review

Every model includes reachability/coverage properties proving that ordinary success
and each important failure state is reachable. A safety property that passes because
no session can open is a failed model review.

For each configuration retain:

```text
TLA+/CFG/tool SHA-256
constants and symmetry sets
worker count and JVM flags
states generated, distinct states and search depth
invariants and liveness properties checked
coverage/reachability counts
warnings
exit status and elapsed resources
counterexample trace when present
```

Run small configurations on every pull request and larger exhaustive configurations
on a protected scheduled/release workflow. Use at least two independently reviewed
constant sets per module, including one with two commanders and a security epoch
transition. A model change invalidates old result receipts.

An independent reviewer must inspect each model for missing actions, over-strong
assumptions, accidental constraints, incorrect fairness, and mismatch with
normative prose before its result can support a release gate.

### 8.6 SMT obligations

Use SMT-LIB with a small bounded command subset and an output/time-limited Python
runner similar in discipline to Prisoma's, but owned by NCP. Register the expected
`sat` or `unsat` result, description, assumptions, and source digest for every
`check-sat`. Include satisfiable premise witnesses to prevent vacuous `unsat`
claims.

Required initial obligations:

| File | Expected result and claim boundary |
|---|---|
| `authority_inductive.smt2` | `unsat` counterexample to one-step preservation of single live body-issued authority under encoded guards |
| `session_type_isolation.smt2` | `unsat` possibility that a typed plant operation is admitted to a simulation session or inverse |
| `operation_at_most_once.smt2` | `unsat` second semantic execution for the same encoded operation key/digest |
| `disposition_terminal.smt2` | `unsat` contradictory transition after an encoded terminal disposition; `sat` witnesses for every legal state |
| `observer_non_authority.smt2` | `unsat` derivation of mutation/publish right from an observer grant |
| `security_admission_order.smt2` | `unsat` semantic callback/latch before bounds, signature, manifest actor, route, audience, digest, session and stream checks in the abstract pipeline |
| `typed_digest_prefix_free.smt2` | `unsat` ambiguous parse for the bounded typed canonical projection grammar; explicitly assumes SHA-256 collision resistance rather than proving it |
| `queue_bounds.smt2` | `unsat` capacity excess under each encoded overflow transition; `sat` witness for every overflow branch |

Solver output is not trusted as prose. The runner rejects model mutation, unexpected
commands, missing results, `unknown`, timeout, stderr excess, output spoofing, and a
different Z3 version. At least one second solver or independently checked algebraic
argument should cover the simplest critical obligations when practical; solver
agreement is not a proof that the encoding matches NCP.

### 8.7 Rust refinement and bounded implementation checking

Refactor the reference implementation so critical transitions are pure functions
over explicit bounded state and typed events. Transport, clocks, entropy, storage,
and audit are injected effects around that core. This makes authorization order and
state changes reviewable and model-checkable.

Add Kani harnesses for:

- session type dispatch and failed-open non-allocation;
- authority acquire/renew/transfer/release with arbitrary bounded terms/clocks;
- operation reservation/commit/retry and snapshot validation;
- stream sequence allocation at `0`, `1`, maximum-1, and maximum;
- action queue severity and ambiguous fail-safe blockade;
- command disposition transition table;
- observer-grant subset and expiry checks;
- typed digest projections and length-prefix bounds;
- JWS/base64 decoded-length arithmetic before allocation; and
- FFI pointer/length/ownership state where Kani supports the used features.

Each harness states its unwind bound, uses cover assertions for all branches, and
has an ordinary Rust regression test for any counterexample. Unsupported Kani
features are explicit gaps, not assumed proofs.

Build a finite refinement harness:

1. TLC dumps the complete state/edge graph for selected small configurations.
2. A digest-bound converter maps abstract actions to a versioned neutral JSON trace
   schema without importing Rust code.
3. The Rust reference executes each admissible trace with deterministic mock clocks,
   entropy, storage, transport and actors.
4. A separately implemented projection compares Rust state with the abstract state
   after every step.
5. Every abstract error/action has coverage; extra Rust-authorizing transitions are
   failures.

The trace converter, projection, and Rust implementation need separate review
because shared code can repeat one bug. Retain all counterexamples and minimize them
without deleting the original trace.

### 8.8 Canonical encoding and cross-language differential verification

The independent TypeScript implementation and a native Python implementation must
implement bounded outer-JWS parsing, protected-header validation, canonical payload
bytes, typed digests, schemas, state transitions needed for their roles, and error
classification without calling the Rust FFI. Rust-backed Python/C bindings remain
useful package/ABI consumers but do not count as independent semantics.

Generate and execute a mandatory corpus containing:

- every stable message, success response and registered error;
- minimum/maximum valid bounds and one-beyond failures at every nesting layer;
- duplicate keys before and after escape decoding;
- invalid UTF-8, surrogate, numeric, negative-zero, non-finite and safe-integer
  cases;
- alternate JSON spellings that canonicalize identically and invalid
  non-canonical signed payloads;
- valid RFC/JWS known-answer vectors and signature/header/payload mutations;
- algorithm confusion, deprecated `EdDSA`, `none`, embedded/remote key, `crit`,
  issuer, audience, route, kind, stable/security digest and key-epoch substitution;
- every session-type cross-product;
- every lifecycle, authority, observer, stream, disposition and security transition;
- stale generation, epoch, lease, descriptor revision and security epoch;
- every plane's overflow, retry, loss/reorder and ambiguity behavior; and
- gateway 0.8 inputs that are safely translatable or must fail closed.

For each vector compare acceptance/error code, normalized typed value, canonical
bytes, request/transcript/payload/security/stable-core digests, state before/after,
receipt, audit projection, and output bytes. The manifest declares the exact
mandatory implementation set; zero silent skips are allowed.

### 8.9 Cryptographic and live security verification

Cryptography is library use plus protocol profiling, not a home-grown primitive.
Before choosing libraries, review maintenance, constant-time claims, unsafe code,
platform support, license, supply chain, MSRV, independent audit, and known
vulnerabilities. Pin exact versions and features; disable remote key retrieval and
all algorithms except `Ed25519` in the profile.

Run known-answer and negative tests from RFC 7515/RFC 8032/RFC 9864 and a pinned,
reviewed Project Wycheproof Ed25519 corpus where applicable. Cross-check Rust,
TypeScript, and native Python signatures in both directions. Zeroize private-key
buffers where the library exposes them, keep keys out of logs/core dumps, and test
permission/HSM/keystore failure paths. Timing tests may detect regressions but do
not prove absence of side channels.

The external production campaign uses exact installed artifacts, a real router,
separate processes and at least two hosts. It must include:

- correct TLS 1.3 mutual authentication and hostname/service identity;
- wrong CA, self-signed leaf, wrong EKU/SAN, expired and not-yet-valid certificate,
  hostname mismatch, weak/disabled TLS version, plaintext and discovery downgrade;
- default-deny ACL, every exact allowed role/plane/route, every cross-role/plane
  denial, wildcard action rejection, and extension/core separation;
- JWS correct path plus every mutation/confusion/substitution case above;
- key overlap rotation with proof of possession and an exact old-key cutoff;
- immediate revocation during idle, Active, pending mutation, stream publication,
  observer delivery, and reconnect;
- authority fail-safe and audit evidence after revocation without clearing ESTOP;
- packet/process/ACL captures that contain no private key or prohibited payload;
- router restart, client reconnect and certificate rotation without identity
  reassignment; and
- a separately controlled emergency-revocation drill.

The campaign report binds certificate public fingerprints, semantic security digest,
authority/ACL/audience/revocation manifests, source/build/package identities,
router image/config, host clocks, commands, captures and outcomes. Test private keys
are ephemeral and destroyed after evidence sealing; production keys are never used.

### 8.10 Fault, concurrency, fuzz, and sanitizer program

Use deterministic schedulers for unit tests and real process/network injection for
external evidence. Cover independently and in combinations:

```text
loss, delay, reorder, duplication, corruption, burst and partition
request accepted/reply lost; publish accepted/outcome ambiguous
commander, body, observer, router and storage process crash/restart
clock equality, advance, rewind indication and monotonic discontinuity
disk full, fsync ambiguity, snapshot truncation/corruption and permission loss
queue saturation, slow subscriber, CPU starvation and memory pressure
authority transfer/expiry/revocation during Active/HOLD/ESTOP
session reset/reopen and stream rollover with stale traffic in flight
security rotation and descriptor revision with pending operations
```

The fault oracle asserts safety state and audit/receipt consistency, not eventual
network delivery. Store injection truth separately from observed response. Replay
every deterministic schedule at least twice and compare semantic digests.

Add coverage-guided targets for bounded raw JSON, flattened JWS, protected headers,
base64, canonicalization, every message decoder, proto/schema parity inputs,
security/plant/extension manifests, snapshot restore, audit chains, gateway capture,
FFI, and stateful operation sequences. Seed with the mandatory corpus and every
historical counterexample.

Release-bound fuzz evidence requires a preregistered duration/CPU budget, exact
fuzzer/toolchain/corpus/source identities, coverage progression, crash/hang/OOM
artifacts, minimization without loss of originals, and rerun confirmation. At
minimum, high-risk parsers receive 24 uninterrupted CPU-hours per target and the
stateful composition receives 72 aggregate CPU-hours on each release platform;
the final campaign owner may increase these numbers but may not shorten them after
seeing results. A coverage plateau is reported, not called exhaustive.

Run ASan/UBSan on C/C++/Rust FFI and native helpers, TSan or Loom for concurrency
where supported, Miri for unsafe/FFI-adjacent Rust models where meaningful, and
platform-specific memory tools. Tool exclusions and unsupported combinations stay
`NOT_RUN`. Threaded FFI stress includes invalid pointers/lengths only inside a safe
test harness that does not invoke undefined behavior before the NCP boundary.

### 8.11 Performance experiment and statistical decision rules

Performance evidence is release-bound and preregistered before measurement. Do not
reuse the repository's informative historical plots as acceptance evidence.

#### Workload matrix

Measure at least:

- raw development and signed production envelopes;
- simulation and plant sessions;
- 1, 10 and 100 active sessions where supported;
- 0, 1, 4 and 16 observers;
- 20, 100, 500 and 1,000 Hz declared streams;
- minimum messages, representative channel sets, 4 KiB, 64 KiB and maximum
  permitted frames;
- success, signature rejection, schema rejection, overload, expiry, ESTOP,
  disposition and idempotent replay paths;
- steady state, burst, queue saturation, router hop, cross-process and cross-host;
- every release OS/architecture and at least the slowest supported body class; and
- rotation/revocation and audit-enabled overhead.

Record separately canonicalization, signing, verification, bounded parse, semantic
validation, governor decision, serialization, transport, queue, application-boundary
and end-to-end latency; CPU, resident/peak memory, allocation count/bytes, bandwidth,
queue depth/drop, and energy where the target can measure it.

#### Acceptance threshold derivation

Do not invent a universal latency number. For each certified plant profile, derive
the protocol budget from its control period, command TTL, watchdog, body-local
governor/application budget, network budget and explicit safety margin. The owner
signs the threshold before data collection. At minimum:

```text
validation + security + queue budget
  < min(declared control period, command TTL, watchdog interval)
    - body computation/application budget
    - network budget
    - preregistered safety margin
```

The release gate uses a one-sided upper confidence bound for the chosen high
quantile (normally p99.9 for active command admission) below that budget on every
certified platform/workload. Report p50/p90/p95/p99/p99.9 and maximum, never only an
average. ESTOP/fail-safe paths have a separately derived stricter budget and cannot
be hidden in aggregate traffic.

#### Sampling and inference

- perform an explicit warm-up determined before measurement;
- use multiple independent process starts and randomized workload order;
- retain raw per-event data or a lossless content-addressed trace subject to privacy;
- account for autocorrelation with block bootstrap or run-level resampling;
- use exact/order-statistic or validated bootstrap confidence intervals for
  quantiles and state the method/coverage;
- report environment, thermal/power state, CPU affinity/governor, clocks, background
  load, compiler flags and package identities;
- correct or clearly scope multiple comparisons across the matrix;
- publish failures/outliers with predefined exclusion rules, never delete them
  post hoc; and
- rerun the complete preregistered cell when an environment fault invalidates it.

For zero observed safety-relevant failures, report the binomial upper confidence
bound (for example, the approximate 95% “rule of three,” `3/n`) rather than “zero
failure rate.” Choose the acceptable bound and required `n` before testing. A
statistical bound never substitutes for a deterministic safety invariant.

### 8.12 Scientific and simulation verification

Protocol conformance tests assert that every simulation output retains
`is_simulation_output=true`, `calibrated_posterior=false`, and the declared model,
backend, seed, numerical environment, network reference, parameters and raw-output
digest. No adapter can flip those flags based on test success.

Prisoma integration tests must include missing language `L`, missing/partial V/D/A,
stream gaps, duplicate/conflicting evidence, observer attach after start, and
revocation. Missing axes are excluded with explicit status; they are never zero,
NaN, empty-vector, or prior-filled placeholders. Dataset publication requires the
visible receipt/run-log contract and records delivery incompleteness separately.

Population, measure, estimator, and application gates remain independent. NCP
transport/security evidence cannot promote a PID result, posterior calibration,
causal claim, paper reproduction, or empirical hypothesis. Statistical changes in
consumer projects require their own preregistration, power, uncertainty, multiple-
comparison and estimator-validity review.

### 8.13 Evidence manifest and reproducibility

Every verification run emits a signed or attestable evidence manifest with:

```text
claim IDs and assurance layer
source commit/tree and dirty-state rejection
stable-core, normative-release and corpus digests
package names/versions/archive SHA-256/build identities
tool/runtime/container/configuration SHA-256
host/OS/architecture and clock source
commands, environment allowlist and exit statuses
test/model/vector counts, skips and expected failures
raw artifact names, sizes and SHA-256
result summary and threshold decision
all NOT_RUN gates and residual risks
reviewer/producer identity and independence
creation/expiry/retention and revocation reference
```

The manifest generator rejects absolute developer paths, secrets, mutable image
tags, dirty worktrees, missing artifacts, duplicate subjects, unregistered claims,
silent skips, and source/digest mismatch. Evidence is immutable; corrections create
a superseding record without deleting history. Independent reproduction starts
from tagged source and documented public inputs in a clean environment, not a copy
of the producer's build directory or caches.

### 8.14 Current formal-tool execution status

At blueprint construction on macOS 26.5.1 arm64:

- Z3 `4.16.0` was present and version-queryable;
- the shell `cargo`/`rustc` were `1.96.0`, which is not the repository's release
  MSRV/toolchain `1.88.0` and therefore is not release evidence;
- Node was `26.3.0`, npm `11.16.0`, Buf `1.71.0`, and protoc `35.0`;
- `/usr/bin/java` existed as a stub but no Java runtime was installed; and
- Kani, TLC, and Apalache commands were unavailable.

No NCP TLA+, Kani, or new SMT model described above has been executed because those
models do not yet exist and the architecture ADRs are unratified. Their state is
`NOT_RUN`, not pass. Z3 availability alone proves nothing. The implementation tasks
must add, pin, review, run, and retain the program before any formal claim.

## 9. Documentation, diagram, graph, and visual-quality program

“Pixel and letter perfect” is an acceptance process, not a subjective claim. For
this release it means that every public document and visual is semantically current,
generated from reviewed source, legible and non-overlapping in every supported
theme and viewport, accessible without color or sight, reproducible from exact
inputs, and approved from retained renders by both automation and a human reviewer.
A generator returning zero is necessary but cannot establish any of those other
properties.

### 9.1 Current tracked inventory and audit result

At the blueprint audit point the repository tracked 47 Markdown files and 16 SVG
files. The SVG set was:

| Class | Tracked files | Current source | Current document use |
|---|---:|---|---|
| logos | 2 light/dark files in `assets/` | no documented deterministic generator | no Markdown reference found |
| protocol diagrams | 10 files: five light/dark pairs in `docs/diagrams/` | `scripts/gen_diagrams.py` | only the safety FSM pair is embedded, in `RESILIENCE.md` |
| historical plots | 4 files: two light/dark pairs in `docs/plots/` | `scripts/plot_perf.py` plus optional recorded data | both pairs are embedded in `PERFORMANCE.md` |

`python3 scripts/gen_diagrams.py --check` passed during blueprint construction. It
establishes that the committed ten diagram SVGs match the current generator; it does
not establish correct architecture, typography, accessibility, embedding, or
release readiness. The pinned historical plot check was deferred to the complete
repository gate because the host Python environment lacked the pinned Matplotlib
dependency; its status remains `NOT_RUN` until that gate produces a receipt.

The first rendered inspection found these open defects and review obligations:

| ID | Asset | Finding | Required disposition |
|---|---|---|---|
| V01 | `versioning-{light,dark}.svg` | the right-aligned metadata beginning `NCP · UNRELEASED` visibly collides with the `VERSION HANDSHAKE` heading | change the generator layout; prove non-overlap in both themes and all render matrices |
| V02 | versioning | it says same-major `1.x` opens and compact `contract_hash` differences are advisory | after ADR-002, depict the exact stable-core compatibility rule and distinct release/corpus identities; never imply an unreviewed future 1.x is compatible |
| V03 | sequence | one lifeline is “body / simulation backend” and one `OpenSession` represents contradictory simulation and plant lifecycles | replace it with separate simulation-service, plant-control, and observer-attach sequences after ADR-001/004 |
| V04 | topology | the single commander/body topology does not expose typed session edges, authenticated observer attach, declared streams, body-issued authority, disposition, or the production envelope | redraw from ratified ADR-001/003/004/005/006/007; keep plane and fail-safe boundaries explicit |
| V05 | ecosystem | it omits Haldir and Galadriel, shows only one Crebain line, and does not distinguish the public Engram placeholder from the private reviewed Paper2Brain implementation | include every in-scope repository and label repository evidence, wire status, migration state, and certification state independently |
| V06 | FSM | it is visually dense and represents only the current candidate admission model | perform bounding-box review and update it for body-issued authority, typed sessions, stream declaration, security epoch/rebind, disposition, and exact ESTOP-reset boundary |
| V07 | topology, ecosystem, versioning, sequence | the generated pairs are not referenced by current Markdown | either embed each in an owner document with exact alt text or delete it and its generator branch; no orphaned release visual |
| V08 | logos | the two variants require background/theme, reduced-motion, accessible-name, unused-definition, and deterministic-source review | define supported logo uses, make visual differences intentional, add a reproducible source or freeze reviewed source with exact provenance, and remove unused or unsafe SVG content |
| V09 | historical plots | they are clearly labelled non-release historical material, but visual inspection is not yet a retained gate | reproduce with pinned dependencies/data, audit labels/contrast/clipping/alt text, and keep them separate from any release-bound benchmark figures |
| V10 | all SVG | direct SVG files have `role="img"`, while generated protocol SVG roots have no internal `<title>` or `<desc>` | decide and test the accessibility contract for both embedded `<img>` and direct-file viewing; prevent conflicting or missing accessible names |

These are release-blocking documentation findings, not permission to hand-edit the
generated SVG files. The source generator, normative architecture, embedding
document, alt text, and tests change together.

### 9.2 Canonical documentation map

Create `docs/documentation-manifest.v1.json` from a reviewed source manifest. It
must list every public Markdown, SVG, graph data file, schema example, and generated
documentation output with:

```text
path and document/visual ID
owner and normative/informative/historical class
source generator and exact inputs, or explicit hand-authored provenance
intended audience and owning section
release/wire/stable-core identity projected into it
light/dark pairing and dimensions
embedding documents and anchor IDs
alt-text source and long-description target
source-data and methodology target for graphs
reviewed terminology and spelling dictionary
last semantic, accessibility, and visual receipt IDs
```

Generate a reciprocal-use index and fail if a public asset is orphaned, if a
document references an unregistered asset, if a light/dark pair is incomplete, or
if one asset is embedded under inconsistent semantic descriptions. Historical
documents and frozen release baselines remain registered as historical and are not
rewritten merely to match current values.

Assign the following minimum owner documents after the ADRs are accepted:

| Visual | Owner document and required truth |
|---|---|
| architecture overview | `README.md`: what NCP is, exact candidate/release boundary, typed session split, supported packages; no certification implication |
| ecosystem status | `README.md` or a dedicated ecosystem page: every named consumer, repository identity, exact pin/migration/certification status, and no private-repository disclosure beyond authorized facts |
| simulation-service sequence | protocol lifecycle section: request/reply, operation idempotency, provenance, result and close |
| plant-control sequence | security/safety section: signed open, generation, stream declarations, body-issued authority, command/disposition, fail-safe and close |
| observer-attach sequence | observer/privacy section: attach resolution, grants, route subset, expiry/revocation, detach and restart behavior |
| production security envelope | `SECURITY.md`: TLS/ACL versus end-to-end signature responsibilities, exact protected fields, validation order, rotation/revocation/rebind |
| authority and stream lifecycle | protocol/state-machine section: body terms/deadlines and publisher-issued declared sequence space without silent rollover |
| plant safety FSM | `RESILIENCE.md`: protocol state versus physical boundary, profile actions, reset and disposition truth |
| version/identity gate | migration/version section: wire, stable-core, normative release and corpus identity; exact hard/advisory decisions |
| release evidence graph | `RELEASE_READINESS.md`: local, external, consumer, publication and post-publication gates without turning `NOT_RUN` into pass |

If one visual becomes too dense, split it. A visual must not carry more concepts
than can remain legible at the minimum supported rendered width. Cross-document
links supply detail; tiny type does not.

### 9.3 Diagram source and layout contract

Keep protocol diagrams as deterministic, text-preserving SVGs generated from code.
Extend `scripts/gen_diagrams.py` or replace it with an equivalently reviewable
generator, but do not hand-edit outputs. The generator must:

1. read candidate/release identities from canonical generated manifests, never
   duplicate them as literals;
2. read labels and alt/long descriptions from one structured semantic source so
   visible and accessible descriptions cannot drift;
3. assign stable, unique element IDs and emit valid XML with a fixed view box,
   explicit width/height, `<title>`, `<desc>`, and a tested accessible-name policy;
4. use only repository-owned or system fallback fonts and never fetch remote fonts,
   images, style sheets, scripts, or resources;
5. forbid executable script, `foreignObject`, event handlers, external URLs,
   embedded raster data unless separately registered, and cross-file ID references;
6. choose font sizes, line heights, padding, corner radii, marker sizes and stroke
   widths from named tokens, with an absolute minimum readable size approved in the
   rendered matrix;
7. wrap text from measured rendered width, not character-count heuristics;
8. reserve non-intersecting title, metadata, content, legend and safe-margin
   regions before placing nodes;
9. route edges so arrowheads, labels and interaction halos do not cross text or
   obscure state boundaries;
10. encode status by text and shape/pattern in addition to hue; and
11. emit light and dark variants from the same geometry and semantic graph unless
    an explicitly tested theme difference is necessary.

The source semantic graph must give every node and edge a unique ID, type, status,
claim tier, source requirement/ADR, short label, full explanation, and allowed
themes. A generator test rejects missing IDs, unreferenced requirements, duplicate
labels with different meanings, disconnected nodes, directionless directed edges,
and a visual status not present in the evidence manifest.

### 9.4 Automated geometry and rendering gate

Add `scripts/check_visuals.py` and self-tests. Use a pinned browser/rendering stack
and at least one independent SVG renderer because a single renderer can hide font
or filter defects. The gate must execute this matrix for every SVG pair:

| Dimension | Required values |
|---|---|
| theme | explicit light and dark; browser `prefers-color-scheme` light/dark |
| native scale | 1x and 2x device-pixel ratio |
| displayed width | intrinsic, 820/860 px as applicable, 640 px, 480 px, and 320 px or the documented minimum if horizontal scrolling is intentional |
| font environment | primary supported system stack and forced final fallback |
| renderer | pinned Chromium plus pinned librsvg or another recorded independent implementation |
| motion | normal and `prefers-reduced-motion: reduce` |

For each matrix cell retain the original SVG, raster render, browser screenshot,
DOM geometry JSON, accessibility-tree excerpt, tool versions and SHA-256. Automated
checks must reject:

- any text/client rectangle outside its view box or declared safe margin;
- intersection of heading, metadata, labels, legends, nodes, arrowheads, or
  forbidden edge/text zones beyond an explicit allowlist;
- glyph clipping, ellipsis, missing-glyph boxes, fallback-induced wrapping, or a
  computed font smaller than its approved token;
- non-finite, negative, zero, or unexpectedly fractional geometry;
- duplicate XML IDs, unresolved references, invalid paint/filter/marker references,
  broken theme pairs, or different semantic text between themes;
- external requests, console/CSP errors, animation after reduced-motion is set, or
  a raster whose painted bounds are unexpectedly blank;
- accessible-name/description mismatch, duplicate announcements, keyboard-focus
  traps, or meaningful information exposed only by color; and
- a pixel-difference beyond reviewed thresholds against the accepted baseline.

Pixel comparison is a regression detector, not the acceptance oracle. Baselines are
created only from a reviewed render receipt and are re-approved when intended
content changes. Anti-aliasing differences are isolated with masks/tolerances that
cannot hide moved text, missing glyphs, clipping, or contrast regression. Include
mutant self-tests that deliberately introduce the V01 title collision, clipped
text, missing font, duplicate ID, broken dark asset, remote URL, blank output,
low-contrast label, color-only state, and inaccessible image; the checker must fail
each mutant for the intended reason.

### 9.5 Contrast, color, and accessibility acceptance

Use WCAG 2.2 AA as the minimum web-document baseline: normal text contrast at
least 4.5:1, large text at least 3:1, and meaningful non-text graphics/state
boundaries at least 3:1 against adjacent colors. Measure actual composited colors,
including opacity, gradients, backgrounds and both themes; checking palette hex
values alone is insufficient.

Every state/plane/decision uses at least two independent cues among label, shape,
line pattern, icon, fill pattern, or position. Test common color-vision deficiency
simulations and monochrome rendering. Do not use animation as the only cue. Honor
reduced motion; disable decorative pulses and retain a static equivalent state.

Every embedded `<img>` has concise alt text that states the conclusion and critical
boundary rather than narrating decoration. Complex diagrams also link to a nearby
text or table containing every node, edge, state, qualifier and exception. Alt text
must include `UNRELEASED`, `NOT RUN`, historical, simulation, or non-certification
qualifiers whenever omission could inflate a claim. Decorative duplicates receive
empty alt text and are hidden from the accessibility tree. Test direct SVG viewing
and embedded viewing separately.

### 9.6 Graph and numerical-figure contract

No graph exists without a machine-readable registered source, an exact generator,
and a methodology note. Each graph records:

```text
dataset/trace ID, SHA-256, schema and provenance
source commit, dirty state, package and environment identity
population/workload, units, transforms and exclusions
sample count and independent-run structure
uncertainty interval and method
interpolation, extrapolation or modeled/synthetic status
release-bound versus historical/informative claim tier
generator/tool/dependency versions and output SHA-256
```

Axes have visible names and units; legends map every mark; scales and zero handling
are explicit; uncertainty is never encoded only by hue; annotations identify
interpolated, unsampled or synthetic values. Tables beside the figure expose exact
plotted values. The checker rejects non-finite values, silent truncation, duplicate
coordinates, inconsistent units, a log scale with non-positive values, missing
cells, a legend/series mismatch, or a graph title/alt text that exceeds the source
claim tier.

Keep existing overlap and realtime plots labelled historical and non-release-bound.
Do not overwrite them with the section 8.11 release experiment. Release-bound plots
receive new IDs, datasets, methodology, filenames and evidence receipts.

### 9.7 Letter-perfect Markdown and prose gate

Add a pinned Markdown/documentation pipeline over the complete registered corpus:

1. validate UTF-8, one trailing newline, no forbidden control/bidi characters,
   normalized line endings, deliberate non-ASCII glyphs, and no trailing space;
2. lint heading hierarchy, unique stable anchors, lists, tables, fences, HTML,
   reference definitions and maximum line policy without rewriting frozen history;
3. spell-check visible prose, diagram strings, alt text, code comments, package
   descriptions and GitHub metadata using a small reviewed technical/proper-name
   dictionary; every exception has a reason;
4. enforce canonical capitalization and spelling: `NCP` for the protocol/project,
   lowercase package/crate/import/route names such as `ncp-core`, and exact
   `Engram`, `Haldir`, `Galadriel`, `Crebain`, `Prisoma`, `Zenoh`, `TLA+`, `Z3`,
   `Kani`, `Ed25519`, `JWS`, `ESTOP`, and `fail-safe` meanings;
5. detect stale wire/version/hash/digest/package values by projecting them from the
   canonical manifests and allowing old values only in explicitly frozen history;
6. validate every relative link, anchor, image, source citation and public URL,
   including case sensitivity and percent encoding, with a controlled network
   policy for external links;
7. compile or execute every declared code sample in the narrowest safe harness and
   schema-validate every JSON/YAML/TOML/protobuf example;
8. compare normative keywords, error names, field names, route templates, defaults,
   limits and state transitions with generated protocol artifacts;
9. render GitHub-flavored Markdown in a pinned GitHub-compatible engine, inspect
   tables/code blocks/images at supported desktop and narrow widths, and retain
   browser screenshots; and
10. fail on draft markers, unresolved TODO/FIXME, broken footnotes, unsupported
    claims, missing status qualifiers, or a generated file changed without its
    generator/input.

Human copy review is performed independently in three passes: technical truth and
claim boundaries; language, spelling, grammar and internal consistency; then final
render reading from first character to last with links and visuals exercised. The
reviewer must not rely on the source diff alone.

### 9.8 Visual receipt and release decision

Each accepted asset has one receipt containing:

```text
visual/document ID and semantic source digest
SVG/Markdown/output SHA-256 and generator/input SHA-256
browser, renderer, OS, fonts and dependency identities
theme/viewport/DPR/motion matrix and artifact digests
geometry, contrast, accessibility, spelling and link results
pixel-baseline ID, masks/tolerances and reason for every accepted difference
human reviewer, review time, independence and signed decision
known limitations and superseded receipt
```

The release visual gate passes only if V01–V10 are closed with receipts; every
registered document/asset has a current automated and independent-human pass; no
orphan, stale identity, missing graph source, overlap, clipping, missing glyph,
contrast failure, accessibility failure, broken link, spelling error, or unreviewed
pixel delta remains; and the final tagged-source clean-room render reproduces the
accepted outputs. Until then the exact status is `NOT_RUN` or `FAIL`, never
“pixel-perfect.”

## 10. Blueprint progress index

This index tracks construction of the blueprint itself. It does not track NCP
release completion.

| Part | Scope | Status | Evidence |
|---|---|---|---|
| P0 | mandated NCP documents and boundary | `LOCAL_PASS` | source cut and digest recorded above |
| P1 | archive, local consumers, and public metadata inventory | `LOCAL_PASS` | archive digest and mutable snapshot recorded above |
| P2 | first-principles blockers and ecosystem conclusions | `LOCAL_PASS` | findings F01–F16 above; implementation remains open |
| P3 | target 1.0 architecture and normative decision records | `LOCAL_PASS` | target laws, messages, security, extensions, and ADR gates in section 7; ADRs remain unratified |
| P4 | formal, executable, statistical, security, and fault verification program | `LOCAL_PASS` | layered program, models, invariants, refinement, security/fault/fuzz and statistical rules in section 8; all new executions remain `NOT_RUN` |
| P4A | documentation, diagram, graph, accessibility, and visual-quality program | `LOCAL_PASS` | current defects V01–V10 and exact automated/human acceptance program in section 9; remediation and release renders remain `NOT_RUN` |
| P5 | exact implementation task DAG and per-repository file/runbook detail | `OPEN` | to be added |
| P6 | release, package, documentation, GitHub, rollback, and incident runbook | `OPEN` | to be added |
| P7 | triple review, repository gate, commit, and push receipts | `OPEN` | to be added |

The implementation task IDs will use prefixes `B` (bookkeeping/decisions), `N`
(canonical NCP), `F` (formal/verification), `E` (Engram), `H` (Haldir), `C`
(Crebain), `G` (Galadriel), `P` (Prisoma), `X` (cross-ecosystem campaigns), and
`R` (release/public metadata). Dependencies, ten-lens findings, acceptance, and
receipts will be explicit for every task.
