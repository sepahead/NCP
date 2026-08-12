# Mandatory NCP 1.0 agent resumption brief

> **STOP: every agent working on NCP or an NCP consumer must read this entire file,**
> the linked live ledger, the blueprint, and that repository's instructions before
> resuming. This generated brief records coordination state; it is not authority to
> tag, publish, certify, rewrite another agent's changes, or clear an external gate.

## What the prior work actually established

The prior pass produced a deep, implementation-grade audit and dependency DAG. It
did **not** implement the 20 identified architectural defects, migrate the consumers,
or make NCP 1.0 releasable. Treating blueprint completion as product completion was the
central imperfection. The live ledger now makes that distinction executable.

The candidate remains unreleased and **NO_GO**. The immutable `v0.8.0` release is a
different wire. No local test, copied mirror, branch pin, model review, or generated
document can substitute for installed-peer, live security, physical-boundary,
independent-review, clean-room, signing, publication, or consumer-role evidence.

## Mandatory reading order

1. The repository's `AGENTS.md` and any scoped nested instructions.
2. [`NCP_1_0_TASK_LEDGER.md`](NCP_1_0_TASK_LEDGER.md) and its JSON source.
3. [`NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md`](../handoff/NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md).
4. NCP `README.md`, `NEURO_CYBERNETIC_PROTOCOL.md`, `docs/1.0-scope.md`,
   `SECURITY.md`, and `RELEASE_READINESS.md` before a protocol-facing change.
5. The target consumer's owning runtime, security, scientific, and integration docs.

## Provisional topology boundary — ratify ADR-011 before code

- NCP is a project-neutral protocol/provider, not an application orchestrator and not
  a dependency on any consumer application.
- X05 is proposed protocol infrastructure, not a tenth X03 role receipt. Signature,
  identity, revocation, and currentness requirements remain non-authorizing blueprint
  material. This repository-local checker has no X05 acceptance parser, cryptographic
  dependency, or trust-root configuration path and cannot admit X05 or any other
  external/independent pass. X05 stays OPEN until a separately authenticated,
  independently qualified verifier boundary is implemented and explicitly integrated.
- Crebain remains standalone and is the sole plant body/actuator authority when its
  optional NCP adapter is enabled. It issues epochs, leases and dispositions.
  A commander-side codec produces intent only. Engram or Haldir must reject an
  incomplete, sparse, non-finite, or unit-inconsistent plant-eligible Active output;
  Crebain independently resolves the exact installed profile, validates the final
  channel set, arity, unit, range, session, lease and horizon, and owns the body-local
  HOLD/ESTOP action. A midpoint or zero is not implicit safety.
- Engram's simulation responder and plant commander are separate optional roles with
  disjoint types, principals, manifests, endpoints and state. Simulation grants never
  satisfy plant authority.
- Direct Engram command and Haldir-gated command are mutually exclusive for one
  plant/session term. In gated mode Engram sends a Haldir-local signed intent; Haldir
  creates a new NCP command under its own principal and obtains Crebain's lease.
- Galadriel's NCP observer is read-only. A separate default-off registered assessor
  extension may push raw advisory evidence with `RECORD_ONLY` or
  `REQUEST_DENY_TIGHTEN` under a distinct principal. Only a separately authenticated,
  Haldir-owned admission profile can derive an applied bounded `DENY_TIGHTEN` effect.
  The result can remove permission, never grant it or actuate.
- Prisoma is a workspace-excluded read-only capture/offline-analysis consumer and is
  never in the control path. Missing evidence is recorded, never interpolated.
- pid-rs remains a protocol-neutral leaf library. Galadriel/Prisoma may depend on it
  through exact optional consumer-owned adapters; pid-rs never depends on NCP or an
  application, and no PID result/log grants identity, capability or authority.
- V11 assigns source-owned atlas work only to NCP and each exact consumer producer.
  Cortexel is outside that ownership set and has no NCP atlas import task, protocol,
  runtime, semantic, evidence, observer, authority, or role-receipt edge. Its existing
  `FigureRequestV1` workflow remains unrelated to NCP architecture assets.

The complete build/start/runtime/trust matrix, orthogonal deployment state, handover
sequence, monotonicity proof and failure campaign are in blueprint section 7.15. This
boundary is proposed design input, not accepted protocol or implementation evidence.

## Current coordination state

Blueprint SHA-256: `df3e412ff000e7e7970d8129e8333790c38b1305d95ff2afa09c47e8142a0246`.

Can this ledger grant release authorization? **false**.

| Task | State | Repository | Rollback or recovery |
|---|---|---|---|
| `B01` | `IN_PROGRESS` | NCP | Return to the last pushed dependency-valid commit, invalidate exact descendant receipts, and preserve unrelated work. |

### Active recovery checkpoint

#### `B01` — Decide and ratify ADR-001 through ADR-011

ADR-003, ADR-004, ADR-005, ADR-006, ADR-007, ADR-010, ADR-011, the D18 migration model, the D19 ratification/promotion state machine, and consumer task scopes were amended after cross-repository review. The amendments define metadata counting, generic versus checked Active admission, plant value and unit preservation, restrictive body-local effect ordering, and hostile replay causality and freshness. Earlier commits, issue requests, model results, and clean gates bind superseded bytes only. They remain historical non-passing working evidence. The latest packet subject binds clean pushed source commit 99672dd48bffe3f8504d4fb66d5a7c9140b122cf and decision-set digest 794c90203c662f1e12d78844c8ac8dcfc0162b0d3813b7df04cbe2e10cdd835a. It is superseded and has zero review records. Composite local runs covered every command in `scripts/check.sh`. One uninterrupted attempt stopped only when crates.io timed out during the Python source-distribution build. The exact failed step and remaining suffix then passed separately. The exact clean B01 runner passed. The bounded 22-case, 90-mutation semantic replay passed. A hostile `dict`-subclass self-test requires one fresh replay-oracle build before caller-controlled serialization and rejects candidate influence on that oracle. These local results do not satisfy B01's independent evidence floor and are not passing task evidence. The Ed25519 screen uses a fixed-sample p95 computational tripwire of 100,000 microseconds for thread and process CPU. Maximum CPU and wall time remain observational. This coordination entry has no task source commit, same-digest request, owner or independent review, command receipt, or artifact receipt. All ADRs remain PROPOSED, and B01 remains IN_PROGRESS. Obtain qualifying same-digest reviews and external adjudications before a passing B01 receipt. Do not create the normative registry, start descendants, or infer release readiness.

Current residual risks:

- All eleven ADRs remain PROPOSED and have no qualifying owner or independent same-digest review; B01 has not reached any passing evidence class.
- The local low-overhead architecture is a maintainer-side recommendation. It records direct design and implementation conflicts but does not override the exact ADR sources, close a question, select wire, or satisfy B01 review. The ADR set must reconcile the recommendation before a new review subject can be issued.
- The generated registry is intentionally non-normative and outside contract/; promotion and the deliberate candidate rebaseline remain blocked.
- The 22 JSON fences remain proposed profile excerpts, not accepted production wire. The current exact-cut local replay passes all 22 cases and rejects 90 registered bounded mutations in separate Rust and TypeScript engines. This is non-authorizing local evidence; no passing B01 receipt exists.
- The semantic-closure gate is OPEN. The current 22-case corpus contains excerpts, not complete proposed wire positives and single-delta hostile counterparts for every ADR source. Open semantic questions, unbounded B03 deferral envelopes, and absent parser-result artifacts block acceptance. Later B03 selections remain downstream.
- B01 inventories the full 72-file set under 72-file and 8 MiB caps, including this architecture. Python imports precede its first snapshot, so this is not pre-import attestation or complete execution provenance. The root lock pins TypeScript 5.9.2. Installed TypeScript, Rust, Cargo, and Bun identities are unretained. CI pins Rust 1.88.0 and Bun 1.3.14 without provenance. The reader rejects leaf links and in-read changes. Privileged parent replacement is outside the claim.
- The latest review subject binds clean pushed source commit 99672dd48bffe3f8504d4fb66d5a7c9140b122cf, has zero reviews, and is superseded. Review capture is disabled during semantic-closure work. No owner review, independent review, external adjudication, or passing B01 receipt exists. Canonical formal work, refinement, and every downstream implementation remain open.
- The declared 256-entry metadata ceiling has no accepted trusted-message-class and decoded-path registry or equal Rust, TypeScript, and Python preallocation enforcement. The current Python developer reader applies a post-parse name heuristic. N01, N02, N03, N06, N07, N08, B02, and B03 remain open.
- Checked codec paths can invent missing midpoint or zero values, accept sparse components, and select a unit by mapping order. The existing plant helper is not integrated into Active admission, and the `PlantCommand` projection erases units. ADR-007 restrictive effect ordering must remain unchanged. N01, N03, N05, N07, N08, B02, B03, E04, H02, and C02 remain open.
- The idempotency cache can evict terminal no-reuse state before its retention deadline. Pending entries have no execution deadline or runtime terminalization path, so a lost backend can retain capacity indefinitely while deletion risks a second mutation. B02, B03, N03, N05, N06, and N07 remain open.
- Idempotency lookup revalidates the expired request deadline and live lease before cache access, so a known terminal result can become unavailable. The Zenoh pending slot can also replace accepted command bytes at one reported stream position before publication. Neither behavior satisfies the selected no-reuse architecture.
- OpenSession has no idempotency context. A concurrent replacement open can discard an older reply without retiring the server generation it created. No durable realm issuer proves UUIDv4 generation no-reuse across restart. Session creation needs one logical-session owner, reserved operation identity, retained result, and durable generation reservation. B02, B03, N01, N03, N05, N06, and N07 remain open.
- The current authority lease omits the direct realm, plant-profile, declared-action-stream, and security-state bindings selected for the body owner. AuthorityMachine also lets a commander self-issue the first lease and renew a commander-issued lease. Its ESTOP reset has no installed plant-profile or deployment-interlock input, and its state-version increment saturates instead of retiring at a selected finite boundary. B02, B03, N03, N05, N07, and N08 remain open.
- The current AuthorityManifest authenticates a principal to a complete plane but carries no exact route, audience, frame-class, session-kind, or operation allow-list. AuthenticatedActor is also caller-constructible and has no inseparable installed-state currentness capability. B01 must reconcile the prepared grant boundary before B02, B03, N01, N03, N05, N06, N07, and N08 can implement or qualify production admission.
- The current runtime has no single body-generation owner, receiver-owned single-use executor capability, or deployment-fenced owner incarnation. A restart or process handoff therefore has no selected actuator-capable split-brain boundary. B01 must reconcile the semantic requirement, and B03 plus dependency-ready implementation tasks must select and implement the exact local or cross-process handoff.
- The current runtime lacks three selected cross-boundary orders: a durable exact-byte outbox for mutating B-over-A forwarding, source-owned observer release against revocation, and deployment-wide reservation of physical effect paths. Without them, crash ambiguity can duplicate mutation, revoked bytes can escape without a known order, and separate realms can target the same hardware. B01 must reconcile these before B03 and dependency-ready implementation work select exact profiles.
- The current Rust and TypeScript handshake paths accept any 1.x wire and treat an absent or different compact proto hash as advisory. They do not enforce the exact supported wire plus stable-core identity selected by the low-overhead architecture. B01 must reconcile that identity rule before B02, B03, N01, N03, N05, N06, and N07 can implement or qualify it.
- Stable route helpers reject key-expression delimiters but select no per-segment byte ceiling, realm segment count, complete route ceiling, or portable character grammar. Current message schemas also leave route identity strings at the universal string limit. B01 and B03 must select one cross-binding identity profile before native role qualification.
- The TypeScript WebSocket client bounds pending-request count but has no aggregate queued-payload byte reservation. Zenoh bounds observation and RPC work by entry count but not aggregate retained bytes. Its observation-drop counter can wrap, and it retains subscriber handles and worker tasks without a session-level entry ceiling. B02, B03, N01, N03, N05, N06, and N07 remain open.
- The core decode_validated path builds a generic JSON tree, clones and typed-deserializes it for shape validation, then typed-deserializes it again for the result. The selected ingress needs one bounded typed decode. B02, B03, N01, N03, N05, N06, and N07 remain open.
- The Zenoh package enables TCP, UDP, TLS, and shared-memory links in every build. Several bus and Zenoh paths use panic assertions after generic validation. The selected installed profile needs an exact link-feature footprint and one fallible typed extraction path. B02, B03, N01, N03, N05, N06, and N07 remain open.
- The Zenoh RPC semaphore retains its permit until a synchronous `spawn_blocking` handler returns, and that handler cannot be preempted. All 128 permits can remain occupied indefinitely despite the count bound. The gateway also wraps this already-blocking handler in a redundant `block_in_place` call. B02, B03, N01, N03, N05, N06, and N07 remain open.
- `ZenohBus::session`, `put`, and `subscribe` expose raw transport operations, while `ZenohBus::from_session` creates the same wrapper from a host-owned session. These paths can bypass typed NCP route, frame, and plane admission. A production adapter needs a separate receiver-owned type with no raw protected-namespace publisher. B02, B03, N01, N03, N05, N06, and N07 remain open.
- The local ActionBuffer latches ESTOP before complete wire validation. ActionBuffer and the stream fence also adopt the first admitted epoch instead of comparing with a prepared declaration. LinkMonitor permits a CUSUM threshold above its 256-sample work bound, normalizes invalid parameters, and exposes no counter-saturation state.
- The C ABI discovers a NUL-terminated JSON length before applying the frame bound. The Python binding accepts an allocated string and builds a generic JSON value before the typed value. Installed ingress needs explicit bounded bytes and one typed decode. B02, B03, N01, N03, N05, N06, and N07 remain open.
- Descriptor scans establish pin coherence only. They do not define the canonical historical handoff-surface inventory, discover role subjects, or issue a role receipt. The current nine-role inventory contains absent and legacy-wire implementations, the thesis descriptor is auxiliary non-peer audit tooling, trusted repository/build/deployment scans and independent scope adjudication are NOT RUN, and N07 remains open.
- The local Ed25519 probe uses a fixed-sample p95 computational tripwire for thread CPU and process CPU at 100,000 microseconds. Maximum CPU and wall time remain observational. The probe records clock metadata, exact PyNaCl project and `uv.lock` identities, and the uv runner digest and version. The probe runs actual result-validator mutations. End-to-end latency, shared-resource behavior, and performance qualification remain NOT RUN.
- Five usable exact Fable 5 consultations bind earlier decision bytes and are historical non-normative challenge input only. Five failed or incomplete attempts returned no complete usable answer, and no model response counts as review, proof, interoperability, or evidence.
- The current 1.0.0-rc.1 normative digest and compact hash are unchanged; external security, plant, consumer, performance, supply-chain, and release gates remain NOT RUN or blocked.

Dependency-ready open tasks: none.

Do not start a descendant merely because its files are convenient. Provider changes
land and pass first; consumers then bind exact immutable provider commits. Cross-repo
work is never one atomic Git transaction.

## Preserved stopped-agent state

| Repository | Branch | HEAD | Dirty paths | Required handling |
|---|---|---|---:|---|
| NCP | `main` | `6e82783667554b8d8b433261e6b8ae588e94d89f` | 0 | Clean provider intake at 6e82783667554b8d8b433261e6b8ae588e94d89f; B00 owns only the listed ledger, generated-view, instruction, and gate-wiring paths. |
| Engram / Paper2Brain | `main` | `92853d2fe6e8ced7e98e2f272a34bfc0067dce57` | 168 | Preserve all 168 stopped-agent paths; do not stage, reset, clean, or bulk-format them during provider work. |
| Haldir | `wip/current-file-review-ledger` | `bb6c0a7b27bbc57fe9935f80e22d06ca3b60e8ba` | 0 | Clean stopped-agent branch; do not change it before its dependency-ready H01 intake. |
| Galadriel | `main` | `f541f3eda7cfdc81a3277c3d6fecc91245179f24` | 0 | Clean main baseline; do not change it before dependency-ready G01. |
| Crebain | `main` | `3e3ee5d0b75269b8f5f634485871069c89a9a474` | 0 | Clean canonical body baseline; keep separate from the producer worktree. |
| Crebain Galadriel producer | `feat/galadriel-integration-refresh` | `113ee70d5660daf90bb373bd7857d4b3f2f56784` | 0 | Clean feature worktree; reconcile only in C04 after canonical C01-C03. |
| Prisoma | `main` | `b0185d98aea8bb6512926d9a8365ba8140fd07c0` | 0 | Clean main baseline; preserve v0.8 history while adding a parallel 1.0 observer. |
| pid-rs | `main` | `1410c8808f1b4e51c76fef395360976e715d2df6` | 0 | Clean standalone estimator/run-log baseline; preserve its protocol-neutral dependency direction and refresh consumer pins only in dependency-ready Galadriel/Prisoma tasks. |
| Cortexel | `main` | `5d900d41d41a68ca1bf537c8590b1f8753d85168` | 0 | Clean excluded non-peer baseline; preserve the stable FigureRequestV1 no-NCP-adapter boundary. Cortexel is outside NCP implementation, consumer qualification, and V11 atlas ownership. |
| sepahead profile | `main` | `80a5c1d5af3a7b85d2a683921dd31e2bdf0406ce` | 2 | Preserve the two unrelated untracked tool directories; edit only canonical sources when R08 is evidence-ready. |

Dirty repositories are inherited work. Do not stash, reset, clean, bulk-format,
checkout over, or stage unrelated paths. Re-inventory immediately before editing
because this table is an intake snapshot, not a lock.

### Current Crebain reconciliation note

The intake rows above remain historical. A 2026-08-01 read-only reconciliation
found canonical Crebain `origin/main` at
`43df8418f1b17b773acdc85533b7fba431dc5468`. That lineage already contains the
producer commits `dec8dcaf2ed62744a2f6f15ace955fbfaf152f0a` and
`99626d00df0cf0d05372b5e505f01e5619169f3f`. No local or remote branch ref
contains the intake-only producer commit
`113ee70d5660daf90bb373bd7857d4b3f2f56784`. GitHub's retained
`refs/pull/31/head` still exposes it as merged PR history. C04 remains OPEN
behind C03; its
scope is to verify the consolidated canonical lineage and retire stale branch
references, not to infer a missing producer implementation or a role receipt.

## Three perspectives required for every change

1. **Protocol/security correctness:** exact semantics, verified actor, authority,
   session/stream fencing, fail-closed unknowns, bounded parsing, and plant hazards.
2. **Consumer/runtime usability:** independent implementation, hard-to-misuse APIs,
   migration, recovery, observability, backpressure, packaging, and operator workflow.
3. **Operational/scientific evidence:** honest simulation/PID/calibration boundaries,
   reproducible tests, independent review, retained artifacts, lifecycle ownership,
   and explicit `NOT_RUN` external gates.

These perspectives summarize—not replace—the blueprint's mandatory ten-lens review.

## Required resume sequence

1. Fetch remote state read-only and re-record branch, HEAD, tree, status, submodules,
   toolchain, and ownership instructions for every repository in scope.
2. Run the ledger self-test and generated-view check before changing status.
3. Add a characterization/negative test before a new accept path and a positive test
   before a new fail-closed path where practical.
4. Change sources and generators; never hand-edit generated schemas, bindings,
   manifests, mirrors, diagrams, plots, or baselines.
5. Run focused gates, inspect the whole diff, then run each repository's complete
   applicable gate. A skip or missing tool is not a pass.
6. Retain structured tool versions and bounded command-output artifacts; every
   passing command and remote-ref verification must name a content-checked artifact.
7. Commit one coherent passing slice with a professional message, push immediately,
   verify the remote object, then add its exact receipt and regenerate this brief.
8. Stop on ambiguity, counterexamples, unsafe downgrade, private forks, dirty-file
   overlap, irreproducible generation, or rollback failure. Record the blocker.

## Commands before handoff

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
    python3 scripts/check_markdown_links.py
    scripts/check.sh
)
```

`scripts/check.sh` creates the same pinned evidence environment and then runs
the complete local gate. A focused pass does not replace that handoff gate.

The final handoff must state exactly what is locally established, externally
established, independently reproduced, blocked, and not run. Never call NCP perfect,
eternal, production-safe, physically certified, or scientifically validated.
