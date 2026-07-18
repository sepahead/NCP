# Mandatory NCP 1.0 agent resumption brief

> **STOP: every agent working on NCP or an NCP consumer must read this entire file,**
> the linked live ledger, the blueprint, and that repository's instructions before
> resuming. This generated brief records coordination state; it is not authority to
> tag, publish, certify, rewrite another agent's changes, or clear an external gate.

## What the prior work actually established

The prior pass produced a deep, implementation-grade audit and dependency DAG. It
did **not** implement the 17 identified architectural defects, migrate the consumers,
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
- Crebain remains standalone and is the sole plant body/actuator authority when its
  optional NCP adapter is enabled. It issues epochs, leases and dispositions.
- Engram's simulation responder and plant commander are separate optional roles with
  disjoint types, principals, manifests, endpoints and state. Simulation grants never
  satisfy plant authority.
- Direct Engram command and Haldir-gated command are mutually exclusive for one
  plant/session term. In gated mode Engram sends a Haldir-local signed intent; Haldir
  creates a new NCP command under its own principal and obtains Crebain's lease.
- Galadriel's NCP observer is read-only. A separate default-off registered assessor
  extension may push only record-only or deny-tightening evidence to Haldir under a
  distinct principal. It can remove permission, never grant it or actuate.
- Prisoma is a workspace-excluded read-only capture/offline-analysis consumer and is
  never in the control path. Missing evidence is recorded, never interpolated.
- pid-rs remains a protocol-neutral leaf library. Galadriel/Prisoma may depend on it
  through exact optional consumer-owned adapters; pid-rs never depends on NCP or an
  application, and no PID result/log grants identity, capability or authority.

The complete build/start/runtime/trust matrix, orthogonal deployment state, handover
sequence, monotonicity proof and failure campaign are in blueprint section 7.15. This
boundary is proposed design input, not accepted protocol or implementation evidence.

## Current coordination state

Blueprint SHA-256: `34cef2a6d8ca6fd514d412ce3ca69162d7ce8a5a7e3a1ca7601c79ee27705122`.

Can this ledger grant release authorization? **false**.

| Task | State | Repository | Resume condition |
|---|---|---|---|
| `B01` | `IN_PROGRESS` | NCP | Return to the last pushed dependency-valid commit, invalidate exact descendant receipts, and preserve unrelated work. |

### Active recovery checkpoint

#### `B01` — Decide and ratify ADR-001 through ADR-011

The strengthened preliminary probe source is pushed and remote-verified at `81941954f33078aa6a8dd85d70e392aae5469246`. Its exact clean-source run bound tree `dc2c433e5e09cce9f03e981d9cbed44f84e72d00`, the unchanged normative digest `9cae331742d01e9b164e029aa06c644e6b1886176d0816a6ef883af138355c90`, the exact contract-manifest file, Z3 binary, 13 prototype sources, Git cleanliness, and the fifth exact `claude-fable-5` response. It explored 11,444 composition states, 35 deny states, and 1,415 complete wire-cutover states; killed all 23 registered model and four SMT mutations; passed eleven SMT checks; and detected the registered queue/parser/journal/real-Ed25519 faults. ADR-008 is proposed at SHA-256 `1379477feebd886823d1511af5df0b7a7019795aef9ee8023147a4ef0a5f56b6` and ADR-011 at `96d243fd41868a70fc00c0f309a5f87e0058f6fce5308e2c98d147e18f76421f`. The raw exact-source log SHA-256 is `08ba5c52a42b505eb409734b218cf793380778c2f44cc9d151589e2364222c94`; its retained deterministic gzip SHA-256 is `eb885f3c430e41f3386a860fc9cd74e23b4a1244ed94d03db281d7565d371603`, and the canonical retained result SHA-256 is `3f140dad12147500048644899f69893c1dd985d0001c900ec66b18143be51fe7`. The earlier `541e1e7` working result is superseded by changed ADR/prototype bytes and grants no evidence. All retained files remain non-passing working evidence: current commands, artifacts, and reviewers remain empty, every ADR remains PROPOSED, and B01 stays IN_PROGRESS. Next publish the exact review packet and obtain qualifying same-digest owner and independent reviews. Do not create the normative registry, alter ADR bytes or wire sources, start B02/B03/F01/N tasks, or infer release readiness.

Current residual risks:

- All eleven ADRs remain PROPOSED and have no qualifying owner or independent same-digest review; B01 has not reached any passing evidence class.
- The generated registry is intentionally non-normative and outside contract/; promotion and the deliberate candidate rebaseline remain blocked.
- Wire examples remain draft JSON only. Independent Python/Node syntax replay and the exact clean-source preliminary model/resource run pass, but the retained result is bounded non-passing working evidence; canonical formal work, refinement, and every downstream implementation remain open.
- Five usable exact Fable 5 consultations are non-normative challenge input only. Five failed or incomplete attempts returned no complete usable answer, and no model response counts as review, proof, interoperability, or evidence.
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
| sepahead profile | `main` | `80a5c1d5af3a7b85d2a683921dd31e2bdf0406ce` | 2 | Preserve the two unrelated untracked tool directories; edit only canonical sources when R08 is evidence-ready. |

Dirty repositories are inherited work. Do not stash, reset, clean, bulk-format,
checkout over, or stage unrelated paths. Re-inventory immediately before editing
because this table is an intake snapshot, not a lock.

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

```bash
python3 scripts/check_implementation_ledger.py --self-test
python3 scripts/generate_implementation_ledger.py --check
python3 scripts/check_markdown_links.py
scripts/check.sh
```

The final handoff must state exactly what is locally established, externally
established, independently reproduced, blocked, and not run. Never call NCP perfect,
eternal, production-safe, physically certified, or scientifically validated.
