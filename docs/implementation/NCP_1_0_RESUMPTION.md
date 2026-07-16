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

Blueprint SHA-256: `7bf9d689839b26c1c3c577097a8fe9713a4d0340170b2641b7e420d1039953d5`.

Can this ledger grant release authorization? **false**.

| Task | State | Repository | Resume condition |
|---|---|---|---|
| `B04` | `IN_PROGRESS` | NCP prototypes | Return to the last pushed dependency-valid commit, invalidate exact descendant receipts, and preserve unrelated work. |

### Active recovery checkpoint

#### `B04` — Prove authenticated-ingress and independent-parser feasibility

B04 checkpoint 2026-07-16T10:03:30Z: the pinned Zenoh conclusion is pushed at clean remote-equal `599aa398d0c55025baf2ae03d36d8b6540598fdf`. `docs/research/authenticated-ingress-feasibility.md`, linked from the root README, now records exact primary sources, direct-Zenoh fail-closed, A as primary, B as deferred forwarding-only, profile exclusivity, hostile cases, three perspectives, ten lenses, no-gos, and next actions. A narrow exact `claude-fable-5` maximum-effort call ended normally and non-normatively; its raw SSE hash and usage are in that document. Independent first-principles review adopted only advice consistent with the pinned source and executable fail-closed boundary. Five upstream raw source paths returned HTTP 200. Markdown, spelling, prose, generated-view, and hostile-ledger checks pass. Visual QA at 1440x1000 and 390x844 in light/dark found exact viewport width, no uncontained overflow or page/console errors, contained wide tables/code, and clear typography, contrast, wrapping, and hierarchy. This closes only the design section review; it proves no implementation property. On resume regenerate and check audit/link/supply-chain views, commit/push this design checkpoint, and verify clean remote equality. Then build the exact-Zenoh live negative probe, explain its result in the ledger, and rerun protocol/security/plant, consumer/runtime, and operations/science/evidence review before A. Apply the same section gate after A before B. Prototypes remain quarantined, non-shipping, non-authoritative, and outside the stable wire; B04 cannot pass before all hostile results, measurements, result-based reviews, and complete local preflight are retained.

Current residual risks:

- The pinned Zenoh 1.9.0 application callback surface and the A/B prototype plan have now been source-reviewed and documented, but no retained live negative probe, authenticated-ingress implementation, independent-parser result, resource measurement, or terminal feasibility result exists yet.
- No B04 prototype may change the normative contract, ship in an NCP package, grant runtime identity or authority, or count as live production-security evidence.
- Two isolated native non-Rust implementations can demonstrate implementation diversity but do not create an independent human reviewer identity.
- Fable advice is optional non-normative design input and cannot count as a parser, reviewer, proof, or gate result.
- Ingress co-tenancy, manifest provenance and atomic rotation, durable replay recovery authority, exact forwarding congruence, and crypto/parser dependency independence remain unproved prototype falsification targets.

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
