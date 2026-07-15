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

## 8. Blueprint progress index

This index tracks construction of the blueprint itself. It does not track NCP
release completion.

| Part | Scope | Status | Evidence |
|---|---|---|---|
| P0 | mandated NCP documents and boundary | `LOCAL_PASS` | source cut and digest recorded above |
| P1 | archive, local consumers, and public metadata inventory | `LOCAL_PASS` | archive digest and mutable snapshot recorded above |
| P2 | first-principles blockers and ecosystem conclusions | `LOCAL_PASS` | findings F01–F14 above; implementation remains open |
| P3 | target 1.0 architecture and normative decision records | `LOCAL_PASS` | target laws, messages, security, extensions, and ADR gates in section 7; ADRs remain unratified |
| P4 | formal, executable, statistical, security, and fault verification program | `OPEN` | to be added |
| P5 | exact implementation task DAG and per-repository file/runbook detail | `OPEN` | to be added |
| P6 | release, package, documentation, GitHub, rollback, and incident runbook | `OPEN` | to be added |
| P7 | triple review, repository gate, commit, and push receipts | `OPEN` | to be added |

The implementation task IDs will use prefixes `B` (bookkeeping/decisions), `N`
(canonical NCP), `F` (formal/verification), `E` (Engram), `H` (Haldir), `C`
(Crebain), `G` (Galadriel), `P` (Prisoma), `X` (cross-ecosystem campaigns), and
`R` (release/public metadata). Dependencies, ten-lens findings, acceptance, and
receipts will be explicit for every task.
