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

## 10. Dependency-ordered implementation DAG

Every task below starts `OPEN`. The task status describes implementation, not this
blueprint's completeness. An implementer must not mark a task `LOCAL_PASS` merely
because the instructions exist.

### 10.1 Execution and repository-change protocol

The implementation agent must perform these steps for every task, in order:

1. read this blueprint, the repository's `AGENTS.md`, and every prerequisite named
   by that repository before touching a file;
2. record repository path, canonical remote, branch, exact `HEAD`, tree digest,
   dirty/untracked state, submodules, tool versions, and task dependencies;
3. if the repository is dirty, on a non-authorized branch, or being changed by
   another agent, do not stash, clean, reset, checkout, rebase, or overwrite it;
   coordinate with its owner or use an explicitly authorized independent worktree;
4. set the task to `IN_PROGRESS` in this document and the machine ledger from B00,
   commit that status only with the first coherent implementation commit, and do
   not invent evidence before execution;
5. modify source and generators first; never hand-edit generated schemas,
   TypeScript, testdata mirrors, manifests, plots, diagrams, or baselines;
6. run focused tests after each semantic unit, inspect the complete diff including
   generated bytes, and record failures rather than weakening guards;
7. run the task acceptance commands from a clean index/worktree candidate and
   retain exact logs/artifact hashes; a skip, missing tool, timeout, warning promoted
   by policy, or expected-but-unexplained difference is not a pass;
8. update normative prose, migration, security, operations, examples, alt text and
   evidence in the same coherent task where their meaning changes;
9. create a professional imperative commit whose scope matches one reviewable
   semantic unit, for example `core: add body-issued authority lifecycle`; never
   use “WIP,” “fix stuff,” autogenerated prose, or a release claim;
10. push the commit to the authorized remote branch immediately after the focused
    gate passes, record remote/ref/pushed commit in the receipt, and verify the
    remote ref resolves to the same object;
11. never force-push, rewrite a released tag, publish a package, edit GitHub
    metadata, merge to a protected branch, or advance another repository's pin
    unless the corresponding task explicitly authorizes that action; and
12. set the task to `LOCAL_PASS` only after source, tests, docs, receipt, commit and
    push are complete. External and independent requirements remain `NOT_RUN` until
    their own tasks produce evidence.

Cross-repository work is not one atomic Git transaction. Use one correlation ID in
all receipts and PR descriptions, land the provider before consumers, and preserve
a working rollback pin. A consumer commit that depends on an unmerged provider
commit stays on its integration branch and cannot be presented as the consumer's
release state.

### 10.2 Topological order and stop gates

The following levels are the only default execution order. Tasks within a level may
run concurrently only when their file ownership does not overlap and their inputs
are frozen.

```text
L0  B00
L1  B01
L2  B02, B03
L3  N01
L4  N02
L5  N03, N04
L6  N05, F01
L7  N06, F02
L8  N07
L9  N08, N09
L10 N10, F03, E01, H01, G01, C01, P01
L11 E02, H02, G02, C02, P02
L12 E03, C03
L13 E04, C04, X01
L14 X02
L15 E05, H03, G03, P03, F04
L16 C05
L17 X03
L18 X04
L19 F05
L20 R00
L21 remaining R* release and public-metadata tasks
```

Stop the DAG immediately if an accepted ADR changes, a stable-core projection is
ambiguous, an invariant counterexample is unexplained, a security downgrade is
found, a physical-boundary claim is unsupported, a generated artifact cannot be
reproduced, a consumer needs a private core fork, or rollback cannot restore a
known safe candidate. Resolution requires a new decision/receipt and re-execution
of invalidated descendants.

### 10.3 Bookkeeping and ratification tasks

#### B00 — create the live implementation and evidence ledger

**Status:** `OPEN`<br>
**Depends on:** none<br>
**Repository:** NCP<br>
**Create/update:** `docs/implementation/NCP_1_0_TASK_LEDGER.md`,
`evidence/implementation/task-ledger.v1.json`,
`scripts/generate_implementation_ledger.py`, `scripts/check_implementation_ledger.py`,
`scripts/check.sh`, `scripts/README.md`, this blueprint.

Implementation:

- define a strict JSON Schema-backed record for task ID, status, dependencies,
  source/target commits, dirty-state refusal, changed files, requirement/ADR IDs,
  all ten lens dispositions, commands, tool identities, result counts, skips,
  artifacts/hashes, reviewers, commit, push remote/ref, rollback and invalidation;
- map L1–L10 to the existing T000–T145 twenty-lens ledger and require the stricter
  obligation wherever they overlap;
- generate the Markdown view from JSON while preserving a dedicated reviewed
  comment field; reject hand-edited generated status/content;
- allow only the transitions in section 3.2 and require a receipt before every
  transition other than `OPEN` to `IN_PROGRESS`;
- reject unknown task IDs, missing dependencies, cycles, optimistic status,
  self-review where independence is required, non-40-hex commits, mutable refs,
  dirty evidence, missing output, duplicate artifact subjects, and secrets or
  absolute local paths; and
- add self-tests for every rejection plus a clean positive fixture.

Acceptance: generator check, verifier self-test, verifier against the live ledger,
Markdown-link check, and complete local `scripts/check.sh`. Commit and push as
`docs: add NCP 1.0 implementation evidence ledger`.

Ten-lens record:

1. **L1:** one generated ledger is the task-status truth; prose cannot disagree.
2. **L2:** receipts contain identities and public evidence only, never credentials;
   status cannot authorize runtime behavior.
3. **L3:** a green task record cannot waive a hazard or plant gate.
4. **L4:** immutable task/commit keys and invalidation edges handle concurrent and
   partially landed repositories.
5. **L5:** bound record/file/log counts and lengths before loading; large raw logs
   are content-addressed artifacts.
6. **L6:** record exact provider and consumer commits/pins; no branch-name evidence.
7. **L7:** claim tier and statistical/scientific exclusions are mandatory fields.
8. **L8:** documented update/check commands and actionable failures make the ledger
   usable without editing generated views.
9. **L9:** mutant self-tests prove the checker detects false passes and stale data.
10. **L10:** CODEOWNERS, retention, supersession, schema versioning and incident
    correction are explicit.

#### B01 — decide and ratify ADR-001 through ADR-010

**Status:** `OPEN`<br>
**Depends on:** B00<br>
**Repository:** NCP<br>
**Create/update:** `docs/adr/0001-*.md` through `docs/adr/0010-*.md`,
`docs/adr/README.md`, `contract/decision-registry.v1.json`, threat/hazard and
traceability generator sources, B00 ledger.

Implementation:

- create one document per decision listed in section 7.14 with context, exact
  decision, rejected alternatives, wire examples, invalid examples, actor/role and
  state transitions, bounds, threat/hazard changes, formal properties, migration,
  operational recovery, compatibility, rollback and open questions;
- run design review with every role named in section 7.14 and record individual
  reviewer identity, independence, version reviewed, decision and conditions;
- resolve the JWS versus terminating-ingress decision with a concrete threat model
  and proof-of-API feasibility against the pinned Zenoh version; use `Ed25519`, not
  polymorphic `EdDSA`, if the JOSE profile is accepted;
- record the exact stable-core membership and whether any functionality moves to a
  separately versioned required extension; and
- keep every ADR `PROPOSED` until all required roles sign the same content digest.

Acceptance: decision registry/schema check, link/anchor check, threat and
requirement traceability regeneration, wire examples parsed by two independent
prototype parsers, no unresolved decision that changes a normative field. Commit
each independent ADR or tightly coupled ADR group professionally and push; make a
final `docs: ratify NCP 1.0 architecture decisions` commit only when all are
accepted.

Ten-lens record:

1. **L1:** each normative meaning has one accepted decision and explicit precedence.
2. **L2:** security reviewers approve principal, signature, manifest, lease and
   downgrade rules, including protected-route binding.
3. **L3:** plant reviewers approve authority/disposition/ESTOP boundaries without
   implying physical certification.
4. **L4:** decisions cover loss, replay, partition, restart, concurrency and
   ambiguous commit.
5. **L5:** every message/state machine has finite limits and overload behavior.
6. **L6:** independently implementable wire examples and explicit 0.8 termination
   prove migration is not silent compatibility.
7. **L7:** simulation, calibration, provenance and observer data semantics retain
   the non-claim boundary.
8. **L8:** operators receive configuration, observability, rotation and recovery
   consequences, not only type definitions.
9. **L9:** each decision names model invariants, negative vectors and evidence gates.
10. **L10:** reviewer roles, namespace owners, change policy and future extension
    process are accepted before code.

#### B02 — authorize and identify the deliberate pre-release rebaseline

**Status:** `OPEN`<br>
**Depends on:** B01<br>
**Repository:** NCP<br>
**Update:** `docs/1.0-scope.md`, `VERSIONING.md`, `CHANGELOG.md`,
`contract/surface.v1.json`, candidate baseline registry/source, migration docs,
B00 ledger.

Implementation:

- obtain an explicit owner decision that the unreleased `1.0.0-rc.1` baseline may
  be replaced before 1.0; do not mutate the immutable v0.8.0 release;
- reserve a new candidate identifier such as the next RC before code generation,
  apply it consistently to the implementation branch, and do not tag or publish it
  until the content and release gates are ready; never recycle `1.0.0-rc.1` for a
  different stable core;
- define old-candidate disposition: unsupported development snapshot, no transparent
  gateway, and exact archive retention for audit only;
- update compatibility prose so exact wire/stable-core checks are hard while
  normative-release/corpus identities have their ratified diagnostic or gate role;
- list every consumer that must move and preserve a known rollback pin until its
  native migration passes; and
- do not create a v1.0.0 baseline, tag, or release row in this task.

Acceptance: all current/candidate text uses the candidate/release distinction,
frozen 0.8 checks pass byte-for-byte, and no generated file or package claims a new
release. Commit/push `docs: authorize the final NCP 1.0 candidate rebaseline`.

Ten-lens record:

1. **L1:** candidate, wire, stable-core, release and corpus identities remain
   distinct everywhere.
2. **L2:** old RC bytes never gain trust from a reused label or permissive match.
3. **L3:** mixed candidate fleets fail closed before actuation.
4. **L4:** rolling upgrade and rollback terminate sessions/streams/leases explicitly.
5. **L5:** identity checks are fixed-size/bounded and occur before expensive decode.
6. **L6:** v0.8 history is immutable; old RC and new RC are explicitly incompatible.
7. **L7:** candidate movement changes no scientific evidence status.
8. **L8:** operators have exact detection, error, rollback and recovery instructions.
9. **L9:** baseline mutation and label-reuse negative tests are required.
10. **L10:** owner authorization, archive retention and future freeze policy are
    recorded.

#### B03 — reserve registries, namespaces, error codes, and owners

**Status:** `OPEN`<br>
**Depends on:** B01<br>
**Repository:** NCP<br>
**Create/update:** `contract/surface.v1.json`, `contract/errors.v1.json`,
`contract/capabilities.v1.json`, `contract/planes.v1.json`, proposed
`contract/operations.v1.json`, `contract/extensions.v1.json`,
`.github/CODEOWNERS`, governance and integrating docs.

Implementation:

- reserve every new kind, enum, route component, operation, capability, extension
  prefix, error and disposition before code uses it;
- give each entry owner, stability class, session types, actors, planes, authority,
  limits, default/unknown behavior, conformance requirements and retirement rule;
- reserve Galadriel's project extension under its own extension namespace; do not
  legitimize the current standard sensor-route sidecar;
- reject case-fold collisions, Unicode confusables, prefix overlap, aliases,
  wildcard core names, recycled error numbers and an unknown/default that grants;
- make registry validation deterministic and part of manifest generation.

Acceptance: registry self-tests/mutants, exact cross-registry referential integrity,
generated manifest check and CODEOWNERS coverage. Commit/push `contract: reserve NCP
1.0 core and extension namespaces`.

Ten-lens record:

1. **L1:** every surface name resolves to one typed meaning and stability class.
2. **L2:** unknown/unowned names authorize nothing and extension names cannot match
   core admission predicates.
3. **L3:** safety/error/disposition names cannot imply an actuator effect not proven.
4. **L4:** operation and stream names include lifecycle/replay ownership.
5. **L5:** name length, character set, registry size and lookup work are bounded.
6. **L6:** independent peers consume the same registry; no consumer-private core IDs.
7. **L7:** scientific status fields and extension claims have explicit owners/tiers.
8. **L8:** names are diagnosable, documented and stable for telemetry/support.
9. **L9:** collision/confusable/unknown mutants and full manifest coverage are tested.
10. **L10:** allocation, review, deprecation and incident revocation policy has owners.

### 10.4 Canonical NCP implementation tasks

#### N01 — establish the single normative source graph and identity projections

**Status:** `OPEN`<br>
**Depends on:** B02, B03<br>
**Repository:** NCP<br>
**Update/create:** `contract/*.v1.json`, `proto/ncp.proto`,
`ncp-core/src/contract_identity.rs`, `ncp-core/src/canonical_digest.rs`,
`ncp-ts/src/contract-identity.ts`, `scripts/generate_contract_manifest.py`,
`scripts/generate_conformance_manifest.py`, identity fixtures and docs.

Implementation:

- define a typed, domain-separated, length-prefixed projection for
  `stable_core_digest_sha256`; specify path ordering, byte encoding, line endings,
  absent/empty distinction and exactly which immutable core sources it covers;
- retain a distinct full normative-release digest and corpus digest, each with its
  own domain and projection; keep the compact FNV hash only if ADR-002 preserves it
  as a non-security diagnostic;
- add `ContractIdentity` to Rust/proto/JSON with exact fixed lowercase-hex lengths;
  reject missing, uppercase, truncated, prefixed, wrong-algorithm and conflicting
  identity values before session allocation;
- make the manifest generator derive all identities and emit one dependency graph;
  no Rust/TypeScript/Python hard-coded copy is accepted without generated equality;
- add prefix-free projection test vectors including empty, Unicode, reordered,
  duplicate-path, CRLF, maximum-length and deliberate collision-of-concatenation
  examples; and
- change no generated output by hand.

Acceptance: Rust and independent TypeScript/Python recompute identical bytes/digests;
SMT prefix-free obligation, property tests and negative corpus pass; manifests and
version coherence reproduce. Commit/push `contract: define NCP 1.0 stable identity
hierarchy`.

Ten-lens record:

1. **L1:** identity projections have exact source membership and canonical bytes.
2. **L2:** stable-core mismatch hard-fails and no compact hash authenticates data.
3. **L3:** identity failure allocates no plant session or authority.
4. **L4:** session transcript pins identities across retries/restarts/rotation.
5. **L5:** fixed digest sizes and bounded projection input prevent allocation abuse.
6. **L6:** three independent implementations and frozen vectors agree exactly.
7. **L7:** corpus/release identity never upgrades simulation or scientific claims.
8. **L8:** diagnostics name expected/observed identity without leaking secret state.
9. **L9:** differential vectors, property tests and SMT obligation cover ambiguity.
10. **L10:** core membership changes require major-wire governance; extensions have
    separate identities.

#### N02 — implement typed simulation, plant, and observer session lifecycles

**Status:** `OPEN`<br>
**Depends on:** N01<br>
**Repository:** NCP<br>
**Update/create:** `proto/ncp.proto`, `ncp-core/src/messages.rs`, proposed
`ncp-core/src/session.rs`, `ncp-core/src/idempotency.rs`,
`ncp-core/src/request_digest.rs`, `contract/surface.v1.json`, error/limit registries,
schemas/vectors through generators.

Implementation:

- replace overloaded `OpenSession` with `OpenSimulationSession` and
  `OpenPlantSession`, sharing explicit `InitiationContext` but having disjoint
  required fields and responder roles;
- implement `SimulationSessionOpened`, `PlantSessionOpened`, `AttachObserver`,
  `ObserverAttached`, `DetachObserver`, `QuerySessionDescriptor`, and versioned
  `SessionDescriptor` with server/body-issued generation and revision;
- make open/attach/close mutations use exact operation ID, request digest, expected
  state, deadline and durable receipt semantics; the same key/different digest is a
  conflict and ambiguous outcomes remain unknown;
- ensure failed open/attach returns no usable generation, descriptor, grant, route,
  authority, or capability; prevent caller-supplied observer generation;
- make all discriminants closed and reject missing/unknown/default session types;
- define restart/reset/close retirement of generations, grants, streams, leases and
  pending operations in one transition table.

Acceptance: generated parity; exhaustive transition/unit/property vectors;
duplicate/lost-response/restart/cross-type/unauthorized-observer negatives; TLA
`NcpSession`/`NcpObserver` traces replay in Rust. Commit/push `protocol: split NCP
session and observer lifecycles`.

Ten-lens record:

1. **L1:** each session type has one responder, purpose and legal operation set.
2. **L2:** verified actor/role/manifest/transcript gates opening and descriptor
   disclosure; payload identity never self-authenticates.
3. **L3:** plant open starts non-actuating and grants no authority implicitly.
4. **L4:** idempotent retry, generation fencing, restart and ambiguous commit are
   explicit.
5. **L5:** identifiers, descriptors, capabilities, operation cache and deadlines are
   bounded before allocation.
6. **L6:** disjoint messages remove consumer guesses; 0.8 requires a terminating
   labelled migration.
7. **L7:** simulation sessions preserve simulation/provenance flags and no
   calibration claim.
8. **L8:** typed APIs, exact errors, query/recovery and descriptor observability are
   hard to misuse.
9. **L9:** model traces, negative vectors, schema/proto parity and independent peers
   verify every branch.
10. **L10:** lifecycle ownership, retention, close/reset privileges and extension
    evolution are registered.

#### N03 — implement declared streams, body authority, and command disposition

**Status:** `OPEN`<br>
**Depends on:** N01, N02<br>
**Repository:** NCP<br>
**Update/create:** `proto/ncp.proto`, `ncp-core/src/messages.rs`,
`ncp-core/src/stream_fence.rs`, `ncp-core/src/authority.rs`, proposed
`ncp-core/src/disposition.rs`, `ncp-core/src/resilience.rs`, `ncp-core/src/safety.rs`,
operation/capability/plane/error/limit registries and generated artifacts.

Implementation:

- add idempotent `DeclareStream`/`StreamDeclared` and
  `RetireStream`/`StreamRetired`; bind publisher actor/entity, session generation,
  plane, exact key, kind, security/transcript digest, epoch, first sequence,
  capacity/QoS and expiry;
- consume a sequence number before an attempted publish and never reuse it after an
  ambiguous result; at exhaustion require explicit retirement/redeclaration—no
  silent epoch rollover or receiver adoption from an arbitrary frame;
- add body-issued `AcquireAuthority`, `RenewAuthority`, `TransferAuthority`,
  `ReleaseAuthority`, `QueryAuthority` and receipts with monotonically increasing
  term and body-monotonic deadline; serialized lease fields are evidence, not bearer
  capability;
- require current generation, transcript, security epoch, exact actor/plane,
  unexpired live lease, operation context and plant gates for mutating/active paths;
  keep ESTOP full admission while allowing the narrowly ratified lease exception;
- add body-only `CommandDisposition` stream/journal/query with admitted, rejected,
  dispatched, applied-at-declared-boundary, stopped-at-declared-boundary, failed and
  unknown states; define terminal transitions and retention/eviction; and
- specify queue ordering/backpressure so fail-safe traffic cannot be starved but
  also cannot cross session/actor boundaries.

Acceptance: transition tables and vectors; Loom/property/concurrency tests;
sequence maximum/ambiguous publish; two-commanders transfer; restart/clock/expiry;
disposition terminality and missing evidence; TLA authority/stream/disposition
traces replay. Commit/push in reviewable units such as `core: add declared stream
lifecycle`, `core: add body-issued authority lifecycle`, and `core: add command
disposition receipts`.

Ten-lens record:

1. **L1:** stream, lease and disposition state machines match prose/proto/code.
2. **L2:** only the body issues authority/disposition; leases are checked against
   authenticated live state, never trusted from payload possession.
3. **L3:** ambiguity/expiry/revocation/restart enters profile-declared non-actuating
   behavior; disposition never claims physical zero.
4. **L4:** loss, duplication, reorder, partition, rollover, transfer and journal
   eviction have deterministic outcomes.
5. **L5:** queues, sequence space, terms, clocks, journals and operation caches are
   bounded with fail-closed exhaustion.
6. **L6:** canonical vectors make producer/receiver rules independently testable;
   no implicit 0.8 mapping.
7. **L7:** dispositions describe protocol/declared hardware boundaries only and do
   not certify causal or scientific results.
8. **L8:** query APIs, metrics, audit fields and operator recovery expose ambiguity.
9. **L9:** TLA, Kani/Loom, negative corpus and two-writer live tests cover invariants.
10. **L10:** body/stream owners, retention, term exhaustion, revocation and incident
    rules are registered.

#### N04 — implement the production authenticated envelope and semantic security state

**Status:** `OPEN`<br>
**Depends on:** N01, N02, B01 ADR-003/009<br>
**Repository:** NCP<br>
**Update/create:** `ncp-core/src/security.rs`, `ncp-core/src/bounded_json.rs`,
`ncp-core/src/canonical_digest.rs`, proposed `ncp-core/src/jws.rs`,
`contract/security-profiles.v1.json`, `contract/security-state-digest.v1.json`,
security conformance vectors, deploy profiles/templates, `SECURITY.md`.

Implementation:

- implement the accepted flattened JWS JSON profile with exact protected header,
  payload and signature members; require fully specified `alg=Ed25519`, known
  critical headers and exact canonical bytes; reject `EdDSA`, `none`, algorithm/key
  confusion, unprotected security context and duplicate JSON keys;
- bind issuer key/principal/entity/role, audience, route, message kind, plane,
  session/generation, stable-core, transcript, security epoch and bounded freshness
  context in the protected projection before semantic decode;
- enforce validation order: raw byte/depth/token/string/member limits; envelope
  shape/base64 decoded-size arithmetic; algorithm/key/epoch/revocation; signature;
  protected context versus actual delivery; then bounded inner decode and semantics;
- redesign security-state digest around normalized public trust anchors, public
  identity-key mappings, ACL/manifest rights, algorithm profile, revocation and
  epoch—not filesystem paths, private key bytes, timestamps or host-specific names;
- implement planned overlap rotation, emergency revocation, session rebind,
  descriptor revision and old-stream retirement; production never accepts raw
  unsigned messages and development never negotiates as production;
- zeroize secret buffers where owned, prohibit secret logging/core dumps/test
  fixtures, and document HSM/process-boundary expectations without claiming them
  implemented by software.

Acceptance: RFC-derived KATs within quotation limits, independent library agreement,
hostile envelope corpus, cross-route/audience/replay/downgrade/rotation/revocation
tests, no semantic callback before verification, semantic digest portability across
paths/hosts and mutation sensitivity. Commit/push `security: bind NCP messages to
authenticated session context`.

Ten-lens record:

1. **L1:** protected projection and semantic digest have one exact canonical form.
2. **L2:** cryptographic identity is mapped by default-deny manifest; every missing,
   stale, revoked, mismatched or unknown input rejects.
3. **L3:** security failure/revocation drives the ratified non-actuating transition
   and never clears ESTOP.
4. **L4:** replay, rotation overlap, partition, restart and rebind are epoch-fenced.
5. **L5:** hostile input is bounded before base64 allocation, signature work and
   inner decode.
6. **L6:** independent JWS libraries and canonical vectors agree; transport identity
   is not assumed from Zenoh callbacks.
7. **L7:** signatures attest origin/integrity, not model validity or calibration.
8. **L8:** key/ACL configuration, rotation, revocation, audit and recovery are
   executable and secret-safe.
9. **L9:** KATs, negative corpus, TLA security model, live mTLS/ACL campaign and
   independent review produce separate receipts.
10. **L10:** algorithms, keys, CA/manifest owners, expiry, revocation SLAs and crypto
    agility policy are explicit.

#### N05 — refactor critical Rust behavior into pure checked transition cores

**Status:** `OPEN`<br>
**Depends on:** N02, N03, N04<br>
**Repository:** NCP<br>
**Update/create:** `ncp-core/src/{session,authority,stream_fence,idempotency,
disposition,security,resilience,safety}.rs`, `ncp-core/src/audit.rs`, `lib.rs`, tests.

Implementation:

- represent session, operation, stream, authority, disposition and security states
  as closed types with private fields and checked constructors;
- implement pure `State × Event -> Result<State, EffectPlan, Error>` transitions;
  transport, monotonic/UTC clocks, entropy, durable storage, signature verification,
  audit and actuator calls are injected effects;
- order transitions so validation/reservation/durable intent precede irreversible
  effects and success receipts follow the ratified commit boundary; represent
  ambiguous effect outcomes explicitly;
- remove optimistic `Default`, unchecked public field mutation, lossy casts,
  wrapping counters and stringly typed privilege decisions from critical paths;
- add snapshot schema/version/digest with fail-closed restoration and migration;
  restart cannot extend deadlines, revive leases, accept retired generations or
  widen authority;
- make audit records bounded, structured and correlated without payload secrets.

Acceptance: unit/property/mutation/concurrency tests, Miri where supported, zero
unsafe code unless separately justified, Kani harnessability and TLC trace replay.
Run fmt/clippy/tests on every commit and push `core: make NCP admission transitions
explicit and verifiable`.

Ten-lens record:

1. **L1:** private typed states implement the normative transition tables exactly.
2. **L2:** authorization precedes effects and cannot be bypassed via constructors or
   restore.
3. **L3:** effect ambiguity and invalid snapshots choose bounded fail-safe behavior.
4. **L4:** explicit events model retries, crashes, concurrent writers and partial
   durable/effect commit.
5. **L5:** checked arithmetic and bounded containers cover counters, caches, queues
   and snapshots.
6. **L6:** neutral traces/vectors, not Rust internals, define peer behavior.
7. **L7:** provenance flags and receipts cannot be promoted by internal success.
8. **L8:** API types make illegal states difficult; audit/recovery remain operable.
9. **L9:** property, mutation, Kani, Miri/Loom and refinement tests cover each state.
10. **L10:** unsafe/dependency/API ownership and snapshot evolution have review rules.

#### N06 — integrate security and state machines into Zenoh without trusting callbacks

**Status:** `OPEN`<br>
**Depends on:** N04, N05<br>
**Repository:** NCP<br>
**Update/create:** `ncp-zenoh/src/lib.rs`, proposed modules under
`ncp-zenoh/src/`, `ncp-zenoh/tests/`, deploy JSON5/templates,
`scripts/check_acl_template.py`, `scripts/verify_acl_deployment.py`, README/security
docs.

Implementation:

- retain TLS 1.3 mutual authentication and default-deny Zenoh ACL as link/router
  defenses, but require the verified NCP envelope for message-to-principal binding;
- expose separate typed clients/servers for simulation, plant and observer roles;
  raw generic publish/query cannot enter stable semantic callbacks;
- construct actual route and message class from transport delivery and compare them
  to protected context; never accept route/payload declarations as self-proof;
- declare exact RPC keys and stream routes after authenticated session/grant, retain
  undeclare guards, and retire them on generation/security/grant/stream change;
- implement per-plane queues, priority, congestion, retention and deadlines exactly;
  control/data overload cannot refresh leases/watchdogs or starve admitted fail-safe;
- expose development loopback/UDS only behind visibly insecure types/config; reject
  non-loopback endpoints and any production negotiation;
- close and audit on ACL/cert expiry/revocation/rotation faults; no silent reconnect
  reuses a generation, stream or lease.

Acceptance: in-process and cross-process tests, hostile raw publisher, wrong route,
wrong audience, cert/ACL mutants, queue overload, reconnect/restart, zero semantic
callback before signature+manifest+session checks, and external live campaign later.
Commit/push `transport: enforce authenticated typed NCP sessions over Zenoh`.

Ten-lens record:

1. **L1:** typed route builders and message kinds agree with contract registries.
2. **L2:** TLS/ACL and JWS are layered; callback limitations cannot grant identity.
3. **L3:** loss/overload/revocation invokes plant state rules and cannot fake stop.
4. **L4:** query retry, sample duplication/reorder, reconnect and undeclare races are
   covered.
5. **L5:** per-plane byte/message/work queues and decode deadlines are enforced.
6. **L6:** Zenoh configuration/version/features are pinned and independent peers use
   the same wire profile.
7. **L7:** transport delivery never upgrades simulation/scientific evidence.
8. **L8:** deployment templates, metrics, structured errors and recovery are tested.
9. **L9:** unit/in-process/live fault-security receipts remain distinct.
10. **L10:** route/ACL owners, cert rotation, dependency patching and incident actions
    are documented.

#### N07 — regenerate and harden all supported language/package surfaces

**Status:** `OPEN`<br>
**Depends on:** N05, N06<br>
**Repository:** NCP<br>
**Update/create:** `ncp-core/src/bin/gen-schemas.rs`, `schemas/`,
`ncp-core/bindings/`, `ncp-ts/src/generated/`, `ncp-ts/src/*.ts`, `ncp-ts/dist/`,
`ncp-python/`, `ncp-cpp/`, `ncp-gateway/`, build scripts and READMEs.

Implementation:

- generate JSON Schemas and TypeScript from Rust source with closed security/safety
  enums, exact integer/string limits and no optimistic defaults;
- provide high-level TS/Rust/Python/C APIs for typed sessions, observer attach,
  streams, authority and dispositions; unsafe low-level decode/publish is clearly
  named and cannot bypass validation in production;
- make TypeScript bounded parsing preserve safe integers/exact strings and implement
  canonical JWS/identity bytes independently rather than calling Rust for the
  required independent-peer evidence;
- define C ABI ownership, alignment, nullability, length, error-buffer, panic and
  thread-safety contracts for every new type; add ABI version/size negotiation;
- keep Python FFI packaging deterministic and ensure exceptions never turn unknown
  outcomes into success; add typing/stubs where shipped;
- make `ncp-gateway` an explicitly terminating, authenticated, labelled boundary;
  do not implement transparent 0.8↔1.0 authority or safety translation.

Acceptance: generator idempotence, TS build/package/corpus, installed wheel corpus,
C/C++ ABI tests including sanitizers, package archive self-containment, independent
TS canonical/security implementation and no generated drift. Use separate commits
for generators, TS, FFI and gateway when reviewable; push each after focused gates.

Ten-lens record:

1. **L1:** all public APIs/codecs preserve identical field/state meaning.
2. **L2:** safe high-level APIs require verified context; FFI errors/defaults grant
   nothing.
3. **L3:** bindings cannot construct active authority or applied disposition from
   missing/unknown values.
4. **L4:** retry/ambiguous outcome/generation semantics survive language boundaries.
5. **L5:** decoded sizes, integers, buffers, ownership and concurrency are bounded.
6. **L6:** TypeScript is genuinely independent; Python/C wrappers are disclosed as
   Rust-backed and not counted as independent peers.
7. **L7:** provenance/non-calibration flags and missing values remain exact.
8. **L8:** packaging, types, examples, errors and gateway operations are usable.
9. **L9:** differential corpus, ABI sanitizers, installed artifacts and negative
   package tests provide evidence.
10. **L10:** registry names, SemVer, ABI policy, support and deprecation are owned.

#### N08 — rebuild conformance, behavior, migration, and fixture coverage

**Status:** `OPEN`<br>
**Depends on:** N02, N03, N04, N07<br>
**Repository:** NCP<br>
**Update/create:** source vectors under `conformance/`, behavior corpus,
`scripts/generate_conformance_manifest.py`, conformance checkers, crate testdata via
`scripts/sync_rust_package_testdata.py`, `e2e/`, `conformance/README.md`.

Implementation:

- create canonical positive, boundary and negative vectors for every message,
  operation, state transition, protected envelope, digest and error;
- require exact mandatory coverage by actor, session type, plane, transport class
  and implementation; a new stable field/state without vectors fails generation;
- add stateful sequences for duplicate/lost replies, same-key/different-digest,
  restart, stream exhaustion, authority transfer, observer revocation, key rotation,
  disposition ambiguity and overload;
- add malicious raw JSON/base64/Unicode/number/nesting/duplicate-key cases evaluated
  before semantic allocation;
- freeze v0.8 baselines untouched; replace the unreleased candidate baseline only
  through B02-authorized generation and retain the superseded RC digest separately;
- encode 0.8 migration as explicit reconstructability/terminating-gateway cases,
  never as native compatibility.

Acceptance: Rust, independent TS and installed peer corpus with exact zero-skip
coverage; proto/schema parity; fixture sync; baseline and Buf checks; corpus digest
and testdata reproducibility. Commit/push `conformance: cover the final NCP 1.0
state machines`.

Ten-lens record:

1. **L1:** every normative branch maps to a manifest vector and exact clause.
2. **L2:** unknown/missing/stale/replayed/downgraded cases all reject explicitly.
3. **L3:** negative paths assert no allocation/authority/actuation/success.
4. **L4:** stateful traces cover network and restart ambiguity.
5. **L5:** minima/maxima/exhaustion/overload and preallocation rejection are covered.
6. **L6:** independent installed peers and immutable 0.8/migration cases are exact.
7. **L7:** provenance, simulation and missing-data semantics have positive/negative
   vectors.
8. **L8:** errors and recovery actions are observable and documented.
9. **L9:** mandatory manifest coverage rejects deletion, skip and stale fixture.
10. **L10:** corpus IDs are immutable, owned and versioned with supersession rules.

#### N09 — remove supply-chain and package-identity release blockers

**Status:** `OPEN`<br>
**Depends on:** N06, N07<br>
**Repository:** NCP<br>
**Update:** `Cargo.toml`, `Cargo.lock`, `deny.toml`, package manifests/locks,
`scripts/check_dependency_exposure.py`, supply-chain generator/evidence sources,
package READMEs and surface registry.

Implementation:

- eliminate `RUSTSEC-2026-0041` exposure by upgrading/removing the dependency or
  proving the vulnerable code is absent under exact resolved features; do not add a
  broad advisory ignore or enable unreviewed compression/default features;
- resolve crates.io/PyPI/npm package-name ownership/collision before promising
  publication: reserve/rename through ADR and update every package, import, docs,
  candidate surface and consumer plan consistently;
- pin direct security/transport/generator dependencies and audit transitive feature
  activation, MSRV, licenses, sources, yanks, unmaintained advisories and build
  scripts;
- produce deterministic archives, SBOM, license inventory and provenance subjects;
  test extracted/offline builds and installed behavior, not only workspace builds;
- never check private registry tokens, signing keys or host paths into evidence.

Acceptance: current and pinned advisory scans, `cargo deny 0.19.9`, dependency
exposure mutants, archives built twice, extracted offline tests, registry ownership
evidence, SBOM/license/provenance validation. Commit by cause, e.g. `deps: remove
vulnerable transport compression path`, and push each passing unit.

Ten-lens record:

1. **L1:** renames preserve wire names only where explicitly ratified; package and
   protocol identities stay distinct.
2. **L2:** dependency features/build scripts and registry ownership cannot introduce
   an unreviewed trust path.
3. **L3:** dependency changes do not weaken fail-safe or plant boundaries.
4. **L4:** transport/runtime upgrades repeat loss/restart/concurrency tests.
5. **L5:** compression/resource amplification and build/runtime costs are bounded.
6. **L6:** consumer pins and installed packages resolve exact immutable artifacts.
7. **L7:** package availability or benchmark changes imply no scientific validity.
8. **L8:** MSRV/platform/install/offline/support behavior is documented and tested.
9. **L9:** advisory, feature, archive, SBOM and clean-install receipts are retained.
10. **L10:** namespace ownership, update SLA, licenses, provenance and revocation are
    assigned.

#### N10 — rewrite normative and user documentation and regenerate visuals

**Status:** `OPEN`<br>
**Depends on:** N01–N09, accepted ADRs<br>
**Repository:** NCP<br>
**Update/create:** all current protocol/security/release docs, migration/integration
docs, examples, `scripts/gen_diagrams.py`, `docs/diagrams/`, documentation manifest
and visual checker from section 9; preserve frozen historical docs.

Implementation:

- rewrite protocol prose from the final generated contract and decision registry;
  remove stale wire-0.8 comments from current surfaces and overloaded session/hash
  language;
- document exact quick starts for simulation, plant, observer and extension roles,
  each visibly development-only or production-secure as applicable;
- regenerate separate diagrams listed in section 9.2, close V01–V10, embed or delete
  every visual, and supply exact alt/long descriptions;
- compile every code/config example and validate every route, field, error, digest,
  command and status against generated artifacts;
- make limitations prominent: unreleased until release task, no physical
  certification/universal zero-safe, simulation not calibrated, external gates and
  consumers `NOT_RUN` until evidenced;
- update changelog/migration/support/security contact and package READMEs without
  changing GitHub metadata or claiming release.

Acceptance: documentation/visual program section 9 in full, examples compiled,
current identity projection, spelling/terminology/link/accessibility/render receipts,
independent technical/copy/visual review. Commit/push `docs: align NCP 1.0 guidance
and visuals with the final contract`.

Ten-lens record:

1. **L1:** prose/examples/visuals project the generated normative truth exactly.
2. **L2:** security diagrams and quick starts never imply payload self-authentication
   or permit downgrade.
3. **L3:** plant/ESTOP/disposition language states software and physical boundaries.
4. **L4:** retry/restart/partition/ambiguous outcomes and recovery are visible.
5. **L5:** all limits, queues, deadlines and overload behavior are documented.
6. **L6:** role-specific integration and explicit 0.8 migration enable independent
   implementations without a fork.
7. **L7:** simulation, posterior, PID, missing-data and benchmark claims are exact.
8. **L8:** guides, diagrams, errors, deployment and accessibility are executable.
9. **L9:** compiled examples and pixel/letter/claim receipts support every surface.
10. **L10:** document owners, archival policy, support and future extension process
    are clear.

### 10.5 Formal and executable verification implementation tasks

#### F01 — implement and independently review the TLA+ model suite

**Status:** `OPEN`<br>
**Depends on:** N02, N03, N04 transition tables<br>
**Repository:** NCP<br>
**Create/update:** `formal/README.md`, `formal/tools.lock.json`, `formal/tla/*`, trace
exporter, CI workflows, B00 ledger.

Implementation and acceptance are exactly section 8.2–8.5: implement all seven
component models and composition model; small and large configurations; safety,
liveness, fairness, non-vacuity and coverage properties; pinned TLC/JRE; retained
state counts/config/source digests and counterexamples. An independent reviewer
must search for omitted actions, overconstraints and invalid fairness. Every model
counterexample becomes an ADR/code/vector issue before the task can pass. Commit
models by coherent state machine and push after small checks; final commit
`formal: model the composed NCP 1.0 lifecycle` follows reviewed large runs.

Ten-lens record:

1. **L1:** variables/actions refine accepted state tables and stable meanings.
2. **L2:** security/authority invariants forbid unauthenticated or stale admission.
3. **L3:** fail-safe, ESTOP and disposition properties preserve stated boundaries.
4. **L4:** the model explicitly explores loss, reorder, duplication, restart,
   partition abstraction and concurrency.
5. **L5:** finite constants are disclosed and exhaustion states are reachable.
6. **L6:** model actions are neutral and map to independent wire traces.
7. **L7:** model success makes no empirical/scientific claim.
8. **L8:** counterexamples are reproducible and mapped to operational scenarios.
9. **L9:** non-vacuity, coverage, multiple configurations and independent review
   constrain false confidence.
10. **L10:** model/tool owners, version pins, review and invalidation policy are set.

#### F02 — implement SMT, Kani, and model-to-Rust refinement checks

**Status:** `OPEN`<br>
**Depends on:** N01, N05, F01 trace schema<br>
**Repository:** NCP<br>
**Create/update:** `formal/smt/*.smt2`, bounded runner/tests,
`formal/kani/`, Rust proof harnesses behind non-shipping configuration,
`formal/traces/`, converter and refinement executor.

Implementation:

- implement every obligation in section 8.6 with expected result, premise witness,
  timeout/output bounds, exact Z3 version and spoof/unknown rejection;
- add Kani harnesses from section 8.7 with unwind/object bounds and `kani::cover`;
  unsupported paths are explicit gaps;
- export TLC graphs for selected configurations through a digest-bound neutral JSON
  schema, execute them against deterministic Rust effects, and compare an
  independently implemented state projection;
- add negative self-tests by mutating one guard/transition/projection at a time and
  require the corresponding proof/refinement check to fail;
- retain solver/proof counts, bounds, warnings and exact source/tool artifacts.

Acceptance: all registered obligations return expected results with witnesses;
Kani covers intended branches; every selected abstract edge maps or has a reviewed
abstraction reason; mutant suite fails correctly. Commit/push `formal: check NCP
1.0 transition refinements`.

Ten-lens record:

1. **L1:** formulas/harnesses cite exact normative transition/field projections.
2. **L2:** admission-order, authority and observer non-authority obligations are
   central.
3. **L3:** failure/ambiguity branches prove no optimistic plant transition.
4. **L4:** bounded state edges include retry/restart/transfer/rollover interactions.
5. **L5:** every proof bound and arithmetic domain is explicit; no unbounded claim.
6. **L6:** neutral traces decouple the model from Rust internals.
7. **L7:** formal results are not evidence of calibration, efficacy or hardware.
8. **L8:** counterexamples map to readable tests and operator-relevant failures.
9. **L9:** coverage, witnesses, mutants, independent projection and tool pins prevent
   vacuous claims.
10. **L10:** proof maintenance, tool upgrade, exception and invalidation ownership is
    defined.

#### F03 — implement differential, property, fuzz, sanitizer, and mutation campaigns

**Status:** `OPEN`<br>
**Depends on:** N07, N08, F02<br>
**Repository:** NCP<br>
**Create/update:** Rust/TS/FFI test and fuzz targets, corpus seeds, CI/scheduled
workflows, evidence manifests.

Implementation:

- implement independent Rust/TypeScript encode/decode/validation/JWS/digest/state
  differential tests across canonical, generated and hostile corpora;
- add structured generators that preserve outer validity while mutating one
  semantic/security property; shrink failures without dropping the cause;
- fuzz bounded JSON, base64/JWS, schema/proto codecs, FFI pointers/lengths, route
  parsing, snapshots, state transitions and gateway labels with seed/coverage/crash
  retention;
- run ASan/UBSan/LSan/TSan where supported, Miri on pure unsafe-sensitive code,
  Loom for concurrency, and mutation testing for critical guards;
- separate PR smoke duration from scheduled/release duration; a short pass cannot
  satisfy the release campaign.

Acceptance: zero unexplained differential result, sanitizer finding, crash/hang,
data race or surviving critical guard mutant; coverage/seed/tool/source receipts;
all skips fail unless registered as platform gaps with an alternate. Commit/push
`test: add adversarial NCP 1.0 differential campaigns`.

Ten-lens record:

1. **L1:** different implementations agree on bytes, errors and transitions.
2. **L2:** structured mutations attack every trust/admission boundary.
3. **L3:** fuzzed invalid input cannot cause actuation/success or erase ESTOP.
4. **L4:** concurrency/fault schedules exercise races, replay and restart.
5. **L5:** allocation/time/output bounds and OOM/timeout behavior are measured.
6. **L6:** installed independent TypeScript, not only wrappers, participates.
7. **L7:** generated/random cases are test evidence, not empirical validation.
8. **L8:** failures retain minimal reproducers and actionable diagnostics.
9. **L9:** coverage, mutation score, duration, seeds and sanitizer matrices are exact.
10. **L10:** corpus disclosure, CI budget, tool updates and vulnerability handling
    have owners.

#### F04 — execute the live security, fault, soak, rotation, and revocation campaign

**Status:** `OPEN`<br>
**Depends on:** consumer implementations, X01, X02, F03<br>
**Repositories/environment:** NCP plus isolated deployment lab<br>
**Artifacts:** external evidence only; no private keys in Git.

Execute section 8.9–8.10 on exact installed candidate artifacts: independent router,
CA and principals; mTLS/ACL; NCP signatures; wrong cert/key/role/route/audience;
expiry, planned rotation, emergency revocation, ACL change, router/peer restart,
packet loss/duplicate/reorder/delay/partition, queue/disk pressure, clock movement,
operation reply loss, stream exhaustion, authority transfer and prolonged soak.
Record packet/config/log/result artifacts with secrets redacted by construction.
Require fail-safe and recovery behavior at the correct software boundary; use a
non-actuating test plant unless a separate physical-safety authority approves more.

Acceptance: every preregistered scenario has expected/observed/result; no open
critical/high finding; rotations/revocations and recovery succeed; retained exact
receipts independently reviewed. This task is not satisfied by
`verify_acl_deployment.py --self-test`. Commit only public evidence summaries, push
`evidence: record NCP 1.0 live security and fault campaign`.

Ten-lens record:

1. **L1:** deployed configs/artifacts match the exact candidate contract identities.
2. **L2:** live attacks verify layered identity, manifest, route, lease and
   downgrade rejection.
3. **L3:** fault/revocation effects reach the declared non-actuating boundary and do
   not overclaim physical stopping.
4. **L4:** real loss/partition/restart/rotation/concurrency schedules are exercised.
5. **L5:** queue, CPU, memory, disk, latency and recovery bounds are observed.
6. **L6:** independent installed peers and actual router config participate.
7. **L7:** campaign success confers no scientific/model certification.
8. **L8:** operator detection, rotation, revocation, recovery and incident logs are
   usable.
9. **L9:** raw evidence, preregistration, exact artifacts and independent review are
   retained.
10. **L10:** CA/key/router/incident owners, evidence expiry and revocation actions are
    exercised.

#### F05 — execute release-bound performance, resource, and final visual campaigns

**Status:** `OPEN`<br>
**Depends on:** X03, X04, N10, F04<br>
**Repository/environments:** NCP, certified platform matrix<br>
**Update/create:** release performance data/methodology/plots, final section 9 visual
receipts and evidence summaries.

Preregister and execute section 8.11 without changing thresholds after seeing data.
Measure canonical encode/sign/verify/decode/admit, RPCs, command/disposition,
fail-safe, observer load, queue pressure and recovery on every supported platform
and workload. Retain run-level raw data; report quantiles/maximum/confidence bounds,
autocorrelation-aware resampling, failure upper bounds and all outliers. Then run the
complete documentation/visual matrix from section 9 against tagged-source candidate
bytes. Keep historical plots separate.

Acceptance: every preregistered cell meets its derived deadline/resource bound with
the required confidence; no hidden failure/exclusion; V01–V10 closed; every document
and visual has machine and independent-human receipts. Commit/push public,
privacy-safe evidence as `evidence: record NCP 1.0 performance and visual acceptance`.

Ten-lens record:

1. **L1:** measured operations and visual labels map to exact candidate semantics.
2. **L2:** security costs/profile remain enabled; no benchmark-only downgrade.
3. **L3:** fail-safe deadlines are separate and derived from plant profiles.
4. **L4:** load, competing traffic, restart and recovery distributions are included.
5. **L5:** bytes/CPU/memory/disk/queues/latency and overload are quantified.
6. **L6:** installed peer/platform matrix, not a developer workspace, is measured.
7. **L7:** preregistration, uncertainty and claim tiers prevent performance/science
   inflation.
8. **L8:** plots/docs are exact, accessible and useful to deployers.
9. **L9:** raw data, methods, hashes, confidence rules and visual matrices are
   independently reproducible.
10. **L10:** platform support, regression budgets, evidence retention and benchmark
    ownership are assigned.

### 10.6 Consumer and ecosystem tasks

These tasks must not be executed against the mutable snapshot from section 2.3
without a fresh intake receipt. At that snapshot Engram was heavily dirty, Haldir
was on a non-main work branch, and the other repositories could change at any time.
Preserve all concurrent work. A pin edit is the last step of a migration, never the
first and never its proof.

The required role allocation is:

| Repository/surface | Native-1.0 role | Explicitly forbidden inference |
|---|---|---|
| Engram / private Paper2Brain implementation | simulation-service responder; optional plant-session commander/client | not the physical body merely because it computes commands; mirror bytes are not certification |
| Haldir | commander-side authorization/reference monitor and authority requester | not body lease issuer, actuator authority, or an implicit identity delegator |
| Crebain canonical repository | plant body, final software actuator authority, sensor publisher and command-disposition publisher | not certified physical safety; NCP ESTOP is not universal zero-safe |
| Galadriel | authenticated read-only observer of standard observations plus its own advisory extension | extension payload is not a standard NCP sensor/frame and cannot authorize control |
| Prisoma | authenticated read-only research observer and offline evidence producer | capture integrity is not delivery completeness, PID validity, calibration or causal proof |
| Crebain Galadriel-producer integration surface | extension producer running inside the Crebain/body deployment | not a separate canonical repository or a second body identity unless explicitly deployed as one |

#### E01 — establish Engram's clean native-1.0 integration baseline

**Status:** `OPEN`<br>
**Depends on:** N07–N09 candidate provider commit, fresh consumer intake<br>
**Repository:** local `engram`, canonical remote verified at intake<br>
**Update:** `.ncp-consumer`, `ncp/.mirror-ref`, `ncp/` only through
`scripts/sync_ncp_mirror.sh`, `scripts/ncp_mirror_pin.py`, mirror drift tests,
integration ledger.

Implementation:

- wait for the active Engram work to be intentionally committed/pushed or obtain an
  owner-authorized clean worktree; do not reuse the audited dirty tree;
- record the exact Engram base commit and canonical remote, then re-audit all
  `backend/neurocontrol/` changes made since archive commit
  `92853d2fe6e8ced7e98e2f272a34bfc0067dce57`;
- synchronize the complete NCP provider commit through the consumer-owned mirror
  script with a candidate label and exact 40-hex revision; never copy selected
  protocol files or hand-edit `engram/ncp/`;
- require the mirrored tree digest, `.mirror-ref`, provider manifest, stable-core
  digest, release digest, corpus digest and Engram descriptor to agree;
- keep `v0.8.0` and the supplied review archive as historical inputs; do not merge
  old candidate mirror files into the new contract;
- change `.ncp-consumer` only after Engram runtime/tests consume the new identity;
  before that, record the provider commit in the integration branch receipt rather
  than claiming a completed pin.

Acceptance: mirror sync/drift self-tests; exact tree comparison to provider commit;
no hand-edited mirror difference; a clean integration branch; Engram baseline test
suite still passes before semantic migration begins. Commit/push `build: sync the
final NCP 1.0 candidate source`.

Ten-lens record:

1. **L1:** the full mirror and runtime point at one provider identity.
2. **L2:** mirroring grants no trust; runtime signature/manifest gates remain needed.
3. **L3:** no plant or action path activates during a source synchronization.
4. **L4:** rebase and mirror updates are deterministic and reject partial copies.
5. **L5:** mirror size/path/file-count/symlink limits and exact hashes are checked.
6. **L6:** candidate revision is immutable; 0.8 history remains distinct.
7. **L7:** archive/mirror synchronization upgrades no scientific evidence.
8. **L8:** clean-worktree, sync, drift and rollback commands are documented.
9. **L9:** provider-tree comparison and consumer baseline test receipts are retained.
10. **L10:** Engram/NCP owners approve mirror revision, retention and rollback.

#### E02 — split Engram's simulation responder from plant commander types

**Status:** `OPEN`<br>
**Depends on:** E01, N02, N07<br>
**Repository:** Engram<br>
**Update:** `backend/neurocontrol/protocol.py`, `session.py`, `service.py`,
`bridge_server.py`, `backends.py`, `loop.py`, `codec.py`, API bridge files,
examples and focused tests.

Implementation:

- replace Engram's development copies of overloaded `OpenSession`/`SessionOpened`
  with generated/faithful `OpenSimulationSession` and simulation result types;
- keep NEST/network configuration, stimuli, step/run and simulation provenance only
  in the simulation-service lifecycle; the responder issues generation and durable
  operation receipts;
- add a separate plant-control client/commander facade that consumes
  `OpenPlantSession`, body-issued descriptor/generation, declared streams, authority
  and disposition; it must not reuse the simulation backend's responder state;
- use disjoint Python classes, factories, route builders and test fixtures so a
  wrong-session operation is not representable through the high-level API;
- preserve `is_simulation_output=true` and `calibrated_posterior=false` on every
  NEST-derived output and retain complete backend/network/seed/numerical provenance;
- delete stale hard-coded candidate digests only after they are generated/validated
  from the synchronized contract; remove permissive same-major/advisory-stable-core
  language.

Acceptance: Python types/vectors match provider; cross-type calls fail before
backend/plant effects; duplicate/lost reply/restart/close tests; API tests; NEST
focused tests; installed independent Python corpus where counted. Commit/push
`neurocontrol: separate simulation and plant NCP sessions`.

Ten-lens record:

1. **L1:** simulation responder and plant commander have disjoint messages/state.
2. **L2:** neither payload nor backend object authenticates a plant principal.
3. **L3:** plant APIs start non-actuating; simulation success grants no actuator
   authority.
4. **L4:** operation replay, lost responses, restart and generation fencing are
   explicit in both lifecycles.
5. **L5:** models, network inputs, operations, results and caches retain bounds.
6. **L6:** Python behavior matches provider vectors without a private core fork.
7. **L7:** simulation and non-calibration provenance is mandatory and immutable.
8. **L8:** role-specific APIs/examples/errors make misuse obvious.
9. **L9:** independent Python differential and backend side-effect tests cover paths.
10. **L10:** Engram owns simulation semantics; NCP owns the wire; plant owns action.

#### E03 — implement Engram's authenticated transport and declared streams

**Status:** `OPEN`<br>
**Depends on:** E02, N04, N06<br>
**Repository:** Engram<br>
**Update:** `backend/neurocontrol/bus.py`, `transport.py`, `bridge_server.py`,
`profiles.py`, configuration/API auth surfaces, security and bus/transport tests.

Implementation:

- implement the NCP production envelope independently in Python using a reviewed
  library/profile, exact canonical bytes and protected route/session context;
- keep `production-secure` unavailable until message signature, key mapping,
  manifest, route/audience, stable-core, transcript and security epoch are all
  validated before semantic callbacks; do not infer peer identity from Zenoh;
- retain `dev-loopback-insecure` only for loopback/UDS with prominent insecure
  status, distinct types and no production negotiation;
- replace `authorize_epoch(...)`, first-frame adoption and the silent
  `JSON_SAFE_INTEGER_MAX` sensor rollover in `transport.py` with authenticated
  `DeclareStream`/`RetireStream`; at exhaustion stop publication until a declaration
  succeeds;
- bind observation/command/sensor subscriptions to observer or commander grants and
  retire them on generation, grant, descriptor, transcript or security change;
- enforce preallocation JSON/JWS limits and per-plane queue/backpressure behavior;
  data traffic never refreshes a lease/watchdog.

Acceptance: independent crypto KAT/negative corpus; wrong route/key/role/session/
epoch rejects; exhaustion has no silent rollover; rotation/revocation/reconnect
tests; dev profile rejects remote endpoint; no callback before full admission.
Commit/push `neurocontrol: authenticate and declare NCP streams`.

Ten-lens record:

1. **L1:** Python protected bytes/routes/declarations match provider exactly.
2. **L2:** signature plus manifest supplies message identity; no callback trust gap.
3. **L3:** transport failure/revocation blocks active output and preserves ESTOP.
4. **L4:** rollover, reorder, reconnect, rotation and callback races are fenced.
5. **L5:** raw bytes/base64/JSON/queues/sequences and callback work are bounded.
6. **L6:** independent Python and Rust/TS peers agree over live transport.
7. **L7:** delivery/security does not certify simulation or posterior meaning.
8. **L8:** configuration, metrics, rotation, errors and recovery are executable.
9. **L9:** KAT, corpus, concurrency and live fault receipts remain distinct.
10. **L10:** key/manifest/route owners and dependency/security update policy are set.

#### E04 — implement Engram authority, operation, disposition, and plant fail-safe use

**Status:** `OPEN`<br>
**Depends on:** E02, E03, N03, Crebain C02 interface fixture<br>
**Repository:** Engram<br>
**Update:** `backend/neurocontrol/loop.py`, `resilience.py`, `session.py`, `service.py`,
`transport.py`, `profiles.py`, Crebain client example/tests and documentation.

Implementation:

- make the plant client request/renew/transfer/release authority from the body and
  use the body's monotonic-deadline receipt; never mint or self-renew plant authority
  in Engram;
- require current plant generation, transcript/security epoch, declared command
  stream, live lease and operation context before active command publication;
- allocate sequence before attempted publish and treat ambiguous publish as consumed;
  require a fresh successful fail-safe publication before any later active command
  after an ambiguous fail-safe attempt;
- consume `CommandDisposition` and query the body journal after reply/sample loss;
  never infer applied/stopped from publication success, silence or timeout;
- make close release/retire in the ratified order, with unknown outcome visible;
- correct the architecture text that maps absent Prisoma `L` to a zero vector:
  absent/empty L causes explicit exclusion and counting, matching Prisoma.

Acceptance: Engram↔Crebain contract fixtures; two-commanders conflict/transfer;
lease expiry/restart; publish ambiguity; disposition terminal/query/eviction; ESTOP
and reset generation cut; missing-L exclusion docs/tests. Commit/push
`neurocontrol: consume body authority and command dispositions`.

Ten-lens record:

1. **L1:** Engram uses body-issued lease/disposition semantics without local variants.
2. **L2:** possession of serialized lease fields grants nothing without live body
   state and verified context.
3. **L3:** command proposal, body admission, declared apply boundary and physical
   effect remain separate.
4. **L4:** ambiguous publish/result, transfer, restart and journal eviction are
   handled without guessing.
5. **L5:** lease/operation/journal/queue/sequence bounds fail closed.
6. **L6:** fixtures and live tests agree with Crebain and Haldir independently.
7. **L7:** absent L is excluded, not zero-filled; dispositions do not validate PID.
8. **L8:** recovery/query/operator status and audit correlation are documented.
9. **L9:** stateful negative tests and ecosystem traces cover every transition.
10. **L10:** commander, body, operator and evidence ownership is explicit.

#### E05 — certify Engram's exact installed native-1.0 artifact

**Status:** `OPEN`<br>
**Depends on:** E01–E04, X01, X02<br>
**Repository/environment:** Engram and isolated certification environment<br>
**Update:** Engram status/handoff/security docs, `.ncp-consumer`, public-safe evidence.

Build/install from a clean pushed Engram commit and exact NCP artifact; run the full
Engram test/gate suite, independent Python conformance, simulation service, plant
commander against reference/Crebain body, security negatives, faults, resource
bounds and clean-room reproduction. Verify the synchronized mirror is unused as
runtime proof except where explicitly intended. Only after success update the
descriptor/pin and consumer receipt. Keep `production-secure` `NOT_RUN` if no real
security campaign occurred.

Acceptance: exact installed commits/packages/configs and zero skips; all claim
boundaries; external evidence reviewed; provider consumer-pin checker matches.
Commit/push `evidence: record Engram NCP 1.0 consumer certification`.

Ten-lens record:

1. **L1:** installed runtime, mirror, descriptor and provider identities agree.
2. **L2:** production identity/ACL/signature negatives execute live.
3. **L3:** plant campaign is non-actuating or separately authorized and bounded.
4. **L4:** fault/restart/partition/retry behavior is exercised.
5. **L5:** declared platform/resource/latency bounds are measured.
6. **L6:** installed Python and Rust/TS/Crebain interoperability is exact.
7. **L7:** simulation/non-calibration and missing-axis claims remain constrained.
8. **L8:** install/config/operation/recovery/docs are clean-room executable.
9. **L9:** exact logs/hashes/skips/review receipt support only named claims.
10. **L10:** artifact owner/support/security/revocation and expiry are recorded.

#### H01 — add a parallel `haldir-ncp10` adapter without mutating v0.8 history

**Status:** `OPEN`<br>
**Depends on:** N07–N09 provider commit, fresh Haldir intake<br>
**Repository:** Haldir<br>
**Create/update:** `crates/haldir-ncp10/`, root `Cargo.toml`/`Cargo.lock`,
`crates/haldir-contracts/` mappings, `.ncp-consumer`, compatibility docs/tests.

Implementation:

- preserve `crates/haldir-ncp08/` and its frozen `tests/data/ncp-v0.8.0/` bytes;
  create a separate adapter crate and feature for native 1.0;
- pin NCP crates to the exact candidate commit with defaults disabled and reviewed
  features; do not switch a non-main dirty Haldir tree or use movable `main`;
- map Haldir mission/action/identity/lease/status types to NCP plant-session,
  authority request and command types through total fallible conversions;
- make unknown enum/status, lossy unit, missing identity, authority mismatch,
  excessive bound or unrepresentable intent reject; no `Default` grants;
- label v0.8 and v1.0 adapters in public types/logs so one process cannot mix frames
  or evidence accidentally.

Acceptance: both adapter crates build/test independently and together; frozen 0.8
fixtures unchanged; conversion/property/negative vectors; dependency feature audit.
Commit/push `ncp: add a separate NCP 1.0 commander adapter`.

Ten-lens record:

1. **L1:** total conversions preserve exact Haldir/NCP meaning or reject.
2. **L2:** Haldir requests authority; it does not issue body leases or delegate by
   serialized claim.
3. **L3:** rejected/unknown intent never becomes active output.
4. **L4:** adapter exposes operation retry/term/generation/ambiguous outcomes.
5. **L5:** conversion, payload, queue, lease and intent sizes are bounded.
6. **L6:** explicit parallel crates prevent 0.8/1.0 mixed-wire confusion.
7. **L7:** policy/evidence results are not scientific or physical certification.
8. **L8:** feature flags, logs, errors and migration are operable.
9. **L9:** provider corpus plus Haldir property/mutation tests cover conversions.
10. **L10:** adapter owners, pin update and v0.8 retirement policy are recorded.

#### H02 — integrate body-issued authority and dispositions into Haldir Gate

**Status:** `OPEN`<br>
**Depends on:** H01, N03<br>
**Repository:** Haldir<br>
**Update:** `crates/haldir-gate/src/{actor,live_service,publication_coordinator,
startup,lib}.rs`, `haldir-contracts`, `haldir-state`, durable/evidence crates,
authority ADR/docs and tests.

Implementation:

- keep Haldir's local policy authorization distinct from NCP body authority: a
  policy allow may request/acquire/renew a body lease but cannot fabricate one;
- bind every admitted active publication to Haldir decision digest, authenticated
  commander/operator, plant session/generation/transcript, body lease, operation and
  declared stream;
- coordinate multiple local writers through one publication coordinator and reject
  stale term/holder/generation; implement explicit transfer/release and body conflict;
- record command disposition separately from policy decision/publication receipt;
  an allow or successful publish never means applied;
- on policy reload, authority change, security change, disconnect, deadline or
  restart, cease active publication, retire relevant stream/lease and request the
  profile-defined fail-safe path; never clear body ESTOP;
- preserve Haldir's local CBOR/durable evidence as Haldir evidence, correlated to
  but not substituted for NCP receipts.

Acceptance: two writers/operators; deny/error separation; transfer/revocation;
reply loss; durable restart; disposition ambiguity; policy reload race; provider
stateful vectors and Haldir audit verifiers. Commit/push
`gate: bind decisions to body-issued NCP authority`.

Ten-lens record:

1. **L1:** policy decision, body authority, publish receipt and disposition are four
   distinct typed facts.
2. **L2:** authenticated principal/manifest/lease/session gates publication; no
   implicit delegation.
3. **L3:** denial/error/expiry/reload/restart produces non-actuating behavior without
   physical claims.
4. **L4:** multi-writer races, transfer, lost reply and durable restart are explicit.
5. **L5:** policy work, queues, journals, deadlines and evidence storage are bounded.
6. **L6:** NCP vectors and Crebain body responses agree with Haldir mappings.
7. **L7:** Haldir evidence cannot validate PID/model performance.
8. **L8:** operator status explains which of the four facts failed and recovery.
9. **L9:** concurrency/model traces, negative tests and durable receipts are retained.
10. **L10:** policy/commander/operator/body owners and incident rules are explicit.

#### H03 — certify Haldir's secure commander deployment

**Status:** `OPEN`<br>
**Depends on:** H02, C02, X01, X02<br>
**Repository/environment:** Haldir plus isolated router/Crebain or reference body<br>
**Update:** transport crate/config, assurance/compatibility/claim docs and evidence.

Update `crates/haldir-transport-zenoh/` and `deploy/secure-reference-v1/` for the
final NCP envelope/routes/ACLs, then execute a real secure campaign with certificate
identity, route binding, acquire/renew/transfer/release, command/disposition,
revocation, reconnect, overload and fail-safe. Preserve existing v0.8 and Haldir
0.9 evidence as historical; do not overwrite it. Update `.ncp-consumer` only after
the installed-artifact campaign passes.

Acceptance: exact installed commits/configs, live evidence, no callback identity
assumption, full Haldir gates, clean-room build and provider pin match. Commit/push
`evidence: certify Haldir as an NCP 1.0 commander`.

Ten-lens record:

1. **L1:** deployed adapter/transport/docs use the same final contract.
2. **L2:** live TLS/ACL/JWS/manifest/lease negatives reject.
3. **L3:** non-actuating fail-safe and ESTOP boundary are observed, not overclaimed.
4. **L4:** transfer/restart/revocation/partition/overload execute live.
5. **L5:** commander resource/latency/evidence bounds are measured.
6. **L6:** installed Haldir and independent body/peer interoperate.
7. **L7:** certification is protocol-role-specific only.
8. **L8:** deploy/rotate/revoke/recover instructions are exercised.
9. **L9:** exact external receipts and zero skips support the status.
10. **L10:** deployment support, key/policy ownership and expiry are recorded.

#### G01 — create Galadriel's native-1.0 observer and extension adapter

**Status:** `OPEN`<br>
**Depends on:** N07–N09, B03 extension allocation, fresh Galadriel intake<br>
**Repository:** Galadriel<br>
**Create/update:** preferably `crates/galadriel-ncp10/`, root manifests/locks/features,
Galadriel-owned extension schemas, `.ncp-consumer`, migration/docs/tests.

Implementation:

- keep the current `galadriel-ncp` v0.8 adapter/frozen schema available as historical
  migration input; add a clearly separate native-1.0 crate/feature until retirement;
- pin exact candidate NCP artifacts and consume `AttachObserver`, descriptor and
  bounded read-only grants; never infer session generation from the first sensor;
- move `SidecarEnvelope` and `MonitorEnvelope` off
  `{realm}/session/{id}/sensor/{name}` to the registered Galadriel extension keys;
  they are not NCP `SensorFrame`s and must not use stable core routes;
- version/sign the extension envelope and bind producer, extension ID/schema digest,
  actual route, plant session/generation, security epoch and source correlation;
- keep standard `ObservationFrame` ingestion separate; translate only where a
  Galadriel value has a semantically valid NCP standard representation;
- preserve read-only/advisory types and prohibit any command, authority or mutation
  API from the adapter.

Acceptance: route and extension registry vectors; observer attach/revocation;
wrong route/schema/producer/session/source rejects; v0.8 and v1.0 builds cannot mix;
no core sensor route carries sidecar bytes. Commit/push
`ncp: add Galadriel's NCP 1.0 observer extension`.

Ten-lens record:

1. **L1:** standard observations and Galadriel extension payloads are disjoint.
2. **L2:** observer grant/signature/route/producer mapping authorizes read only.
3. **L3:** advisory outputs cannot acquire authority or actuate.
4. **L4:** attach/restart/revoke/gap/reorder/producer epoch are explicit.
5. **L5:** envelope, covariance/vector, reorder, queue and gap bounds remain strict.
6. **L6:** registered extension enables independent producer/consumer agreement;
   v0.8 stays labelled.
7. **L7:** NIS/CUSUM/PID fields retain exact evidentiary and advisory limits.
8. **L8:** feature/config/route/errors and migration are clear.
9. **L9:** extension corpus, schema/semantic negatives and live observer tests run.
10. **L10:** Galadriel owns extension schema/namespace/support/deprecation.

#### G02 — bind Galadriel lifecycle and monitoring to authenticated observer state

**Status:** `OPEN`<br>
**Depends on:** G01, N04, N06<br>
**Repository:** Galadriel<br>
**Update:** native-1.0 equivalents of `assembler.rs`, `config_identity.rs`,
`lifecycle.rs`, `live.rs`, `monitor.rs`, `monitor_live.rs`, `operational_live.rs`,
deploy configs and security/state-machine docs.

Implementation:

- start subscriptions only after `ObserverAttached` returns exact descriptor/grant;
  avoid the current non-atomic two-subscription window by a declared readiness or
  buffering protocol that cannot accept pre-grant evidence;
- verify NCP and extension envelopes before decode/assembly; bind actual route,
  producer identity, session generation, source stream and grant;
- use declared streams and explicit retire/redeclare instead of sidecar-owned
  session-ID restart conventions where NCP state applies;
- preserve bounded serialized ingress, reorder/gap deadlines, fail-stop first fault
  and immutable emitted evidence; grant expiry/revocation terminates delivery;
- distinguish missing delivery, rejected evidence, monitor failure and an advisory
  anomaly; none becomes a plant command.

Acceptance: attach/start atomicity; pre-grant injection; grant expiry/revocation;
route swaps; gaps/reorder/duplicates/restart; queue capacity; fail-stop recovery;
real signed transport later. Commit/push
`observer: bind Galadriel monitoring to NCP grants`.

Ten-lens record:

1. **L1:** lifecycle/assembler state follows descriptor, grant and stream contracts.
2. **L2:** signatures and read-only route subset precede all evidence callbacks.
3. **L3:** monitor faults/anomalies remain advisory and non-actuating.
4. **L4:** startup race, reorder, gap, restart, revocation and close are deterministic.
5. **L5:** line/envelope/vector/reorder/queue/time limits fail stop.
6. **L6:** standard and extension paths agree with Crebain producer vectors.
7. **L7:** missingness, incomparability and advisory statistics remain honest.
8. **L8:** faults/status/reconnect/detach are observable and recoverable by policy.
9. **L9:** property/fault/live tests and exact receipts cover each state.
10. **L10:** grant/extension/monitor/evidence owners and retention are explicit.

#### G03 — certify Galadriel's installed read-only integration

**Status:** `OPEN`<br>
**Depends on:** G01, G02, C03, X01, X02<br>
**Repository/environment:** Galadriel and isolated observer deployment<br>
**Update:** claims/security/producer/deploy docs, release evidence, `.ncp-consumer`.

Run all default/all-feature Galadriel gates, JSONL and live extension corpora,
installed NCP artifacts, Crebain producer, signature/ACL/grant negatives,
gap/reorder/overload/revocation faults and clean-room reproduction. Demonstrate by
API and ACL that Galadriel cannot publish core frames, acquire authority or mutate a
session. Update the pin only after success.

Acceptance: exact artifacts/configs, zero unexplained skips, live read-only proof,
scientific claim audit and independent receipt. Commit/push
`evidence: certify Galadriel's NCP 1.0 read-only adapter`.

Ten-lens record:

1. **L1:** installed extension/observer/docs match provider identity.
2. **L2:** read-only manifest and negative mutation/authority tests execute.
3. **L3:** no path from advisory observation to actuation exists.
4. **L4:** live gaps/reorder/restarts/revocation/overload are tested.
5. **L5:** declared resource/latency bounds are measured.
6. **L6:** installed Galadriel and Crebain/provider peers agree.
7. **L7:** claims/evidence retain advisory and statistical limitations.
8. **L8:** deployment, faults, detach/recovery and docs are executable.
9. **L9:** exact corpus/live/claim receipts support only named role.
10. **L10:** support/security/schema/evidence owners and expiry are recorded.

#### C01 — create Crebain's separate native-1.0 plant adapter and exact pins

**Status:** `OPEN`<br>
**Depends on:** N07–N09, fresh canonical Crebain intake<br>
**Repository:** canonical `sepahead/crebain`, not the producer clone<br>
**Create/update:** explicit `ncp10` feature and `src-tauri/src/ncp10/` (or a renamed
equivalent), `src-tauri/Cargo.toml`/`Cargo.lock`, `package.json`/`bun.lock`,
`.ncp-consumer`, coherence script and migration docs.

Implementation:

- preserve the optional v0.8 adapter as labelled migration input; never resolve
  v0.8 and v1.0 `ncp-core` types into the same feature graph or runtime;
- pin Rust and npm artifacts to one exact candidate commit/archive; avoid tag-only
  or movable refs during candidate integration;
- make native 1.0 a separate feature, module, route/config namespace and UI status;
  a build rejects mutually enabled 0.8/1.0 features;
- inventory every command/sensor/observation/extension path and map only exact
  registered meanings/units/shapes; invalid conversions reject;
- run the default NCP-off product gates to prove the optional integration does not
  silently enter default artifacts.

Acceptance: feature-graph/coherence checks, default-off build, 0.8-only and 1.0-only
build/tests, exact lock/pin, no mixed symbols/routes. Commit/push
`ncp: add a separate native-1.0 plant adapter`.

Ten-lens record:

1. **L1:** v0.8 and v1.0 modules/types/routes are unmistakably separate.
2. **L2:** pin/feature selection grants no runtime authority.
3. **L3:** integration remains inert until body session/plant gates pass.
4. **L4:** mixed-version/restart/config transitions fail closed.
5. **L5:** dependency/features/binary size and adapter bounds are checked.
6. **L6:** exact immutable artifacts and no silent translation support migration.
7. **L7:** research prototype status remains explicit.
8. **L8:** build flags/status/errors/migration/rollback are clear.
9. **L9:** feature mutants and all build matrices produce receipts.
10. **L10:** canonical repo owns the adapter; clone/branch cannot become a fork.

#### C02 — implement Crebain as body-issued authority and disposition source

**Status:** `OPEN`<br>
**Depends on:** C01, N03–N06<br>
**Repository:** Crebain<br>
**Update:** native-1.0 module, `src-tauri/crates/plant-authority/src/{contract,
lifecycle,expiry,deadline_monitor,safe_action,apply_observation,adapter,runtime,
frame_conventions,health}.rs`, daemon/tests, plant/profile docs.

Implementation:

- make plant-authority the sole software body for session generation, authority
  terms/deadlines, command admission, disposition journal and stream declarations;
- acquire/renew/transfer/release through durable, monotonic, single-holder state;
  restart without proved continuity invalidates sessions/leases and enters the
  profile-defined non-actuating state;
- verify full signed envelope, actual route, manifest, session, declared stream,
  sequence, lease, operation, TTL, channel kinds/units/widths/finite values and
  plant profile before every mode—including ESTOP;
- remove `minimal_estop_command`, the raw JSON `mode == "estop"` bypass, and the
  early typed ESTOP bypass in `src-tauri/src/ncp/mod.rs`; unauthenticated malformed
  input cannot latch or actuate. Provide a separately authenticated local/out-of-band
  physical ESTOP interface if required by the plant design;
- define the exact `dispatched`, `applied`, `stopped` and `unknown` boundaries in
  the adapter/runtime and publish signed dispositions only after the declared event;
- ensure reset retires generation, grants, streams, leases, operation state and
  buffers; it never restores remote authority automatically;
- never equate zero velocity with universal safe state; dispatch the content-addressed
  plant profile's HOLD/ESTOP actions and record limitations.

Acceptance: malformed/raw ESTOP rejects before state; valid authorized ESTOP has
priority; active/hold/expiry/revocation/restart/transfer; disposition journal/query;
profile mutation; deadline and apply-boundary tests; non-actuating hardware/mock
campaign. Commit in units, including `plant: remove unauthenticated NCP ESTOP
bypass` and `plant: issue NCP authority and command dispositions`, pushing each.

Ten-lens record:

1. **L1:** body session/lease/admission/disposition matches NCP transition tables.
2. **L2:** every mode needs full verified context; local physical ESTOP is separate.
3. **L3:** body remains final authority; profile actions and physical boundary are
   explicit; reset cannot restore actuation.
4. **L4:** multi-writer, retry, reply loss, restart, transfer and apply ambiguity are
   deterministic.
5. **L5:** envelopes, queues, operations, journals, channels, terms and deadlines are
   bounded.
6. **L6:** Haldir/Engram fixtures and independent peers agree with body receipts.
7. **L7:** command execution/disposition validates no research model or PID claim.
8. **L8:** operator ESTOP/reset/status/query/recovery and audit are executable.
9. **L9:** TLA traces, hostile corpus, plant tests and live campaign cover gates.
10. **L10:** body/profile/hardware/operator/key/journal owners and incident response
    are assigned.

#### C03 — migrate Crebain sensor and Galadriel-extension publication

**Status:** `OPEN`<br>
**Depends on:** C02, G01<br>
**Repository:** Crebain<br>
**Update:** native NCP module, `src-tauri/src/{galadriel_producer,
producer_monitor,sensor_fusion,pid_observation}.rs`, extension schemas/config/docs
and tests.

Implementation:

- declare standard NCP sensor/observation streams through the body and publish only
  valid standard frames on core routes;
- publish `SidecarEnvelope`/monitor data only on registered Galadriel extension
  keys using the extension schema/security/source correlation from G01;
- bind producer identity to the Crebain body deployment/manifest, exact plant
  session generation, declared extension stream and security epoch;
- preserve Galadriel advisory output as observation/evidence; it cannot enter
  plant-authority command admission unless a separately specified, human-approved
  policy consumes it with its own safety evidence—and no such path is implied here;
- handle extension subscriber absence/backpressure without blocking or weakening
  control/fail-safe planes; expose dropped/late/incomplete evidence.

Acceptance: core route rejects sidecar bytes; extension route rejects core confusion;
source correlation, gap/reorder/restart/revocation, queue isolation and Galadriel
interoperability; optional producer-off build. Commit/push
`galadriel: publish advisory evidence on the NCP extension plane`.

Ten-lens record:

1. **L1:** standard frames and extension envelopes have separate exact meanings.
2. **L2:** signed producer/route/session/extension grant is verified.
3. **L3:** observer/advisory traffic cannot authorize actuator behavior.
4. **L4:** producer restart, subscriber absence, reorder/gap and revocation are fenced.
5. **L5:** extension work/queue/vector/envelope bounds cannot starve control.
6. **L6:** Crebain/Galadriel share registered schema/vectors, not copied guesses.
7. **L7:** missing/dropped/advisory/statistical state remains visible.
8. **L8:** producer status/config/errors/disable/recovery are clear.
9. **L9:** route-confusion, load, live and differential tests retain receipts.
10. **L10:** extension/producer/schema/support and retention ownership is explicit.

#### C04 — reconcile and retire the separate Galadriel-producer work branch

**Status:** `OPEN`<br>
**Depends on:** C01–C03, fresh branch comparison<br>
**Repositories:** canonical Crebain plus `crebain-galadriel-producer` worktree/branch<br>
**Current audit input:** branch `feat/galadriel-integration-refresh` at
`113ee70d5660daf90bb373bd7857d4b3f2f56784`; canonical main at the audit point was
`3e3ee5d0b75269b8f5f634485871069c89a9a474`.

Implementation:

- fetch both remotes and make a commit/patch-equivalence inventory; at the audit
  point the producer branch showed three commits beyond its local `main`, while the
  canonical repository already contained related work under different hashes;
- review semantic differences file-by-file; do not blindly merge, rebase or
  cherry-pick duplicate plant/producer changes;
- port only changes still required by C02/C03 onto a fresh canonical integration
  branch, preserving authorship and correlation in commit messages/receipts;
- run the complete canonical Crebain gates and producer-specific campaign there;
- after merge and remote verification, mark the old branch superseded with its final
  commit and replacement commit map; delete a remote branch only with owner
  authorization and after retention/rollback needs are met;
- keep one canonical implementation and one issue/evidence location—no silent
  consumer-specific NCP fork.

Acceptance: patch-equivalence ledger; no lost unique change; no duplicate behavior;
canonical full gates; branch replacement mapping; owner approval. Commit/push
`chore: consolidate the Galadriel producer into canonical Crebain`.

Ten-lens record:

1. **L1:** one canonical producer/plant implementation remains.
2. **L2:** reconciliation cannot reintroduce old authentication/route bypasses.
3. **L3:** plant changes receive fresh hazard review, not equivalence by filename.
4. **L4:** concurrent histories/duplicate patches/rollback are explicitly mapped.
5. **L5:** branch/file/patch inventory is bounded and content-addressed.
6. **L6:** canonical provider/consumer pins replace branch-local assumptions.
7. **L7:** branch evidence is preserved but does not inflate claims.
8. **L8:** maintainers have one source, migration map and recovery point.
9. **L9:** semantic diff, full tests and exact commit map support closure.
10. **L10:** branch deletion/retention/authorship/ownership requires approval.

#### C05 — certify Crebain body and producer integration separately

**Status:** `OPEN`<br>
**Depends on:** C02–C04, H03/E05/G03 as applicable, X01, X02<br>
**Repository/environment:** canonical Crebain and isolated non-actuating plant lab<br>
**Update:** release/security/hazard/NCP/producer docs, `.ncp-consumer`, evidence.

Run default-off and NCP-on complete Crebain gates, installed artifacts, Haldir and
Engram commanders, authority conflict/transfer, signed commands, malformed ESTOP,
fail-safe/deadline/profile/reset/disposition, Galadriel extension, rotation/
revocation, resource/fault/soak and clean-room reproduction. Produce two receipts:
Crebain body role and Crebain Galadriel-producer extension role. Neither receipt is
physical safety, airworthiness, field deployment or research validity.

Acceptance: zero skips in declared matrix, exact artifacts/configs, independent
review, provider pin match and all hazard residuals visible. Commit/push
`evidence: certify Crebain's NCP 1.0 body and extension roles`.

Ten-lens record:

1. **L1:** body and extension receipts bind exact separate surfaces.
2. **L2:** live identity/authority/route/revocation negatives pass.
3. **L3:** non-actuating plant boundary and residual physical hazards are explicit.
4. **L4:** multi-writer/fault/restart/partition/rotation/soak execute.
5. **L5:** plant/producer resource and deadline bounds are measured.
6. **L6:** installed Haldir/Engram/Galadriel/provider peers interoperate.
7. **L7:** protocol role evidence makes no empirical efficacy/PID claim.
8. **L8:** install/operate/ESTOP/reset/recover/disable docs are exercised.
9. **L9:** two exact role receipts, raw evidence and independent review are retained.
10. **L10:** support/security/hazard/profile/hardware/schema ownership and expiry are
    recorded.

#### P01 — add a parallel native-1.0 Prisoma observer

**Status:** `OPEN`<br>
**Depends on:** N07–N09, fresh Prisoma intake<br>
**Repository:** Prisoma<br>
**Create/update:** `crates/ncp-observer10/`, root/exclusion metadata as appropriate,
`.ncp-consumer`, observer docs, tests and research ledgers.

Implementation:

- preserve `crates/ncp-observer/` and its wire-0.8 semantics as historical; create a
  separate native-1.0 crate/binaries until migration is certified;
- pin exact candidate NCP artifacts and use authenticated `AttachObserver`, body
  descriptor/generation, route grant and declared stream state;
- subscribe only to granted sensor/command/observation/disposition routes; expose no
  publish, authority or mutation API and enforce this through feature/dependency
  graph and deployment ACL;
- bind full session generation, stream/source positions, grant/security epoch and
  producer identities; never let the first sensor self-authorize a generation;
- preserve bounded buffers, FIFO/explicit eviction, immutable emitted rows,
  conflicting-evidence invalidation and receipt-last publication.

Acceptance: 0.8 unchanged; 1.0 attach/grant/revoke/restart/route/stream tests;
read-only API/ACL negative tests; exact provider corpus/pin. Commit/push
`ncp: add Prisoma's native-1.0 read-only observer`.

Ten-lens record:

1. **L1:** native observer maps final NCP frames/source/disposition exactly.
2. **L2:** authenticated grant is read-only; raw traffic cannot create session state.
3. **L3:** no control/authority/actuation surface exists.
4. **L4:** attach/restart/gap/reorder/duplicate/revocation/eviction are deterministic.
5. **L5:** payload/vector/in-flight/resident/log/process bounds remain enforced.
6. **L6:** explicit parallel crate preserves 0.8 and avoids mixed-wire capture.
7. **L7:** capture/delivery/population/measure/estimator/application gates stay
   independent.
8. **L8:** observe/detach/fault/status/publication verification is operable.
9. **L9:** corpus, property, fault and read-only tests retain receipts.
10. **L10:** observer/data/privacy/evidence/support/pin owners are assigned.

#### P02 — preserve missing-variable and research-claim semantics in native capture

**Status:** `OPEN`<br>
**Depends on:** P01<br>
**Repository:** Prisoma<br>
**Update:** native observer mapping/observatory, `RESEARCH_VLA_D_NCP.md`,
`LIMITATIONS.md`, `EXPERIMENTS.md`, protocol/evidence ledgers, tests.

Implementation:

- keep V/L/D/A mappings explicit and versioned; absent/empty L, D, V or A excludes
  the tick with reason/count and never becomes zero, NaN, a hash, a prior, or a
  fabricated fixed-width vector;
- pair only by exact declared source correlation/session generation; never arrival
  time, bare sequence or a future/nearest frame;
- represent stream gaps, grant gaps, revocation, late data, conflicting evidence,
  unknown disposition and capture incompleteness independently;
- retain `calibrated_posterior=false` and simulation provenance; no transport/
  capture result advances population, measure, estimator or application gates;
- preregister any actual PID analysis, population support, estimator, missing-data
  policy, multiplicity and uncertainty outside the transport migration.

Acceptance: missing/partial axes, gaps, conflicts, late/reordered frames,
revocation/restart, simulation flags and publication receipt tests; claim/docset
audits reject zero-fill and overclaim. Commit/push
`research: preserve missing-axis semantics for NCP 1.0 capture`.

Ten-lens record:

1. **L1:** mapping/join/missingness has one exact documented meaning.
2. **L2:** only granted verified frames enter capture; no authority is derived.
3. **L3:** research observation cannot affect plant control.
4. **L4:** gaps/reorder/restart/conflict/late evidence never trigger guessed joins.
5. **L5:** axis dimensions, buffers, samples, logs and finalization are bounded.
6. **L6:** source/session identifiers agree with producers and provider vectors.
7. **L7:** missingness, provenance, estimand, uncertainty and gate independence are
   the primary acceptance criteria.
8. **L8:** exclusion counts/reasons and dataset verification are usable.
9. **L9:** negative fixtures, formal publication checks and claim audits run.
10. **L10:** data/privacy/research/publication/retention responsibilities are explicit.

#### P03 — migrate the fault observatory and certify Prisoma's observer role

**Status:** `OPEN`<br>
**Depends on:** P01, P02, X01, X02<br>
**Repository/environment:** Prisoma and isolated read-only deployment<br>
**Update:** native equivalents of `observatory.rs`, `observe.rs`,
`fault_observatory.rs`, README/security/evidence and `.ncp-consumer`.

Port the deterministic offline fault schedules to the final lifecycle and add live
read-only scenarios for attach, descriptor/grant, declared streams, route/security
binding, gaps/reorder/duplicates, revocation, observer restart, producer restart,
unknown disposition and bounded pressure. Replay twice for deterministic cases,
verify receipt-last outputs and run the complete Prisoma claim/governance gates.
Update the consumer pin only after installed-artifact and live read-only evidence.

Acceptance: deterministic outputs/hashes; live read-only proof; no fabricated axes;
full Prisoma gates; clean-room reproduction; independent review. Commit/push
`evidence: certify Prisoma's NCP 1.0 observer`.

Ten-lens record:

1. **L1:** observatory schedules/results match final NCP semantics.
2. **L2:** attach/grant/route/revocation negatives are live and read-only.
3. **L3:** no control surface or physical-safety claim exists.
4. **L4:** deterministic and live fault schedules cover lifecycle/network events.
5. **L5:** memory/disk/process/time/sample bounds are measured/enforced.
6. **L6:** installed Prisoma and independent producers interoperate.
7. **L7:** claim/governance/missingness/publication gates all pass independently.
8. **L8:** operator/researcher capture, verify, detach and recovery are executable.
9. **L9:** exact offline/live/raw/receipt evidence with zero skips is retained.
10. **L10:** observer/data/research/security/support and evidence expiry are recorded.

### 10.7 Cross-ecosystem qualification tasks

#### X01 — qualify two genuinely independent installed non-Rust peers

**Status:** `OPEN`<br>
**Depends on:** N07, N08, E03<br>
**Repositories/environments:** NCP TypeScript package plus independent Engram Python
or another clean-room non-Rust implementation.

The Rust-backed Python and C FFI wrappers do not count. Install the candidate npm
package from its archive in a clean environment and install/run the independent
native Python implementation without importing the Rust codec. Each must parse,
validate, sign/verify, canonicalize, compute identities, execute its supported state
transitions and reject the full mandatory negative corpus. Exercise both against an
installed Rust peer over actual transport and prove package-source independence.

Acceptance: two independent non-Rust implementation receipts, exact package hashes,
zero mandatory-vector skips, byte/error/state equality and live interoperability.
Commit/push public summaries as `evidence: qualify independent NCP 1.0 peers`.

Ten-lens record:

1. **L1:** peers agree on bytes, errors, identities and state outcomes.
2. **L2:** independent signature/manifest/admission implementations reject attacks.
3. **L3:** plant scenarios use a non-actuating reference body.
4. **L4:** retries/reorder/restart/rotation are exercised cross-language.
5. **L5:** each peer enforces the same limits before allocation.
6. **L6:** independence and installed archives satisfy the gate, not shared Rust FFI.
7. **L7:** interop makes no scientific/calibration claim.
8. **L8:** install, configuration, errors and support matrices are reproducible.
9. **L9:** full corpus/live logs/artifact hashes and independence review are retained.
10. **L10:** peer owners, versions, support and revocation are recorded.

#### X02 — run the composed ecosystem and multi-writer campaign

**Status:** `OPEN`<br>
**Depends on:** at least E04, H02, G02, C03, P02, X01<br>
**Environment:** isolated router and non-actuating reference/Crebain body.

Execute compositions, not only pairs:

- Engram simulation responder with an independent client;
- Engram commander and Haldir commander contending for one Crebain body, including
  acquire/conflict/transfer/expiry/restart and disposition query;
- Galadriel and Prisoma attaching read-only during operation, restart, key rotation
  and grant revocation;
- Galadriel extension publication under control/data pressure without starving
  fail-safe/control traffic;
- close/reset/reopen while commands, observations and dispositions are in flight;
- old 0.8 and superseded RC peers attempting connection and failing closed, plus an
  explicitly terminating migration gateway if one is shipped.

Acceptance: all cross-module TLA scenarios have live counterparts; exact expected
state at every participant; no private core fork; no authority split brain; no
observer mutation; bounded resources; independent review. Commit/push
`evidence: record the composed NCP 1.0 ecosystem campaign`.

Ten-lens record:

1. **L1:** all roles observe one session/stream/authority/disposition truth.
2. **L2:** actor/role/manifest/route/lease isolation holds in composition.
3. **L3:** contention/faults remain non-actuating and preserve ESTOP boundary.
4. **L4:** multi-writer, observer, rotation, close/reset and in-flight races execute.
5. **L5:** aggregate queues/CPU/memory/disk/deadlines stay bounded by plane.
6. **L6:** every named consumer and independent peer interoperates without forks.
7. **L7:** observer outputs retain missingness/advisory/non-calibration truth.
8. **L8:** operators can diagnose ownership, failure, recovery and evidence gaps.
9. **L9:** model-to-live scenario map and exact multi-repo receipts are retained.
10. **L10:** cross-repo incident/upgrade/rollback/support coordination is exercised.

#### X03 — issue six exact consumer-role certification receipts

**Status:** `OPEN`<br>
**Depends on:** E05, H03, G03, C05, P03, X02, F04<br>
**Subjects:** Engram; Haldir; Galadriel; Crebain body; Crebain Galadriel-producer
surface; Prisoma.

For each subject issue a distinct receipt binding repository/commit/tree, installed
artifact hashes, NCP identities, configuration/security/plant/extension profiles,
role, tests/scenarios/counts/skips, external campaign IDs, reviewer, limitations,
expiry and revocation. The Crebain producer is a separate role receipt, not falsely
described as a separate repository or independent body. A failure in one receipt
does not get averaged into fleet success.

Acceptance: all six exact subjects pass their mandatory role gates with no critical
open finding or unexplained skip; provider validates signatures/schema/subjects;
receipts cannot be replayed for later commits/configs. Commit/push
`evidence: record six NCP 1.0 consumer role receipts`.

Ten-lens record:

1. **L1:** each receipt identifies one exact role/contract/artifact/configuration.
2. **L2:** each role's allowed/forbidden authority and live security evidence is bound.
3. **L3:** plant versus observer/simulation boundaries remain distinct.
4. **L4:** required lifecycle/fault scenarios are subject-specific and complete.
5. **L5:** platform/resource/deadline scope is explicit.
6. **L6:** all six pass individually; no copied pin or aggregate inference.
7. **L7:** subject claim tiers and scientific exclusions are explicit.
8. **L8:** install/operate/recover/support evidence is attached.
9. **L9:** commands/counts/skips/artifacts/review make each result auditable.
10. **L10:** issuer, owner, expiry, supersession and revocation are enforceable.

#### X04 — reproduce the provider and ecosystem from clean rooms

**Status:** `OPEN`<br>
**Depends on:** X03, N09<br>
**Environment:** at least two independent clean builders, including supported Linux
and another declared platform/architecture.

From tagged-source candidate commits and public inputs only, build all provider
archives twice, verify SBOM/licenses/provenance subjects, install independent peers
and each consumer integration, reproduce conformance/doc/visual artifacts and run
the defined smoke/certification subset. Do not reuse producer caches, build trees,
local sibling paths, secret registries or unrecorded toolchains. Differences require
root cause and rebuilt receipts; normalization cannot hide source/output drift.

Acceptance: bit-for-bit where promised and semantically/exact-manifest equivalent
where platform bytes legitimately differ; all artifacts install offline/under the
declared network policy; subject hashes match release inputs; independent signoff.
Commit/push `evidence: reproduce the NCP 1.0 ecosystem from clean source`.

Ten-lens record:

1. **L1:** rebuilt artifacts project the same normative identities/content.
2. **L2:** build sources/scripts/dependencies/attestations and secret absence are
   verified.
3. **L3:** clean-room tests use safe/non-actuating plant boundaries.
4. **L4:** build/install ordering and partial failure/rollback are exercised.
5. **L5:** build/runtime resource and artifact size limits are recorded.
6. **L6:** platforms/peers/consumers resolve without local siblings or mutable refs.
7. **L7:** reproduction supports software artifacts, not scientific results unless
   separately preregistered/reproduced.
8. **L8:** public build/install/run instructions are sufficient.
9. **L9:** independent builders, exact logs/hashes/diffs and signatures are retained.
10. **L10:** builders, provenance/signing, retention, embargo and revocation are owned.

#### R00 — hand the qualified candidate to the release runbook

**Status:** `OPEN`<br>
**Depends on:** F01–F05, N10, X03, X04<br>
**Repository:** NCP<br>

Freeze exact candidate source/artifacts/receipts and evaluate every release gate
without changing status optimistically. This task does not tag, publish or edit
GitHub metadata. It produces the immutable input set for section 12 and stays
`NOT_RUN` until every dependency is actually complete.

Ten-lens record:

1. **L1:** one frozen candidate identity covers source, contract, corpus and packages.
2. **L2:** security/signature/revocation evidence and residual risks are complete.
3. **L3:** safety/hazard/plant limitations and evidence are visible.
4. **L4:** faults, rollback and incident states have passed qualification.
5. **L5:** supported resource/performance bounds are evidenced.
6. **L6:** installed peers and six consumer subjects are exact.
7. **L7:** scientific/benchmark claims remain properly scoped.
8. **L8:** release/operator/support/documentation inputs are executable.
9. **L9:** every gate receipt is current, independent where required and zero-skip.
10. **L10:** release authority remains human/explicit; freeze cannot self-publish.

## 11. Blueprint progress index

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
| P5 | exact implementation task DAG and per-repository file/runbook detail | `LOCAL_PASS` | dependency order, execution protocol, B/N/F provider tasks, all named consumer tasks, cross-ecosystem qualification and ten-lens records in section 10; implementation remains `OPEN`/`NOT_RUN` |
| P6 | release, package, documentation, GitHub, rollback, and incident runbook | `OPEN` | to be added |
| P7 | triple review, repository gate, commit, and push receipts | `OPEN` | to be added |

The implementation task IDs will use prefixes `B` (bookkeeping/decisions), `N`
(canonical NCP), `F` (formal/verification), `E` (Engram), `H` (Haldir), `C`
(Crebain), `G` (Galadriel), `P` (Prisoma), `X` (cross-ecosystem campaigns), and
`R` (release/public metadata). Dependencies, ten-lens findings, acceptance, and
receipts will be explicit for every task.
