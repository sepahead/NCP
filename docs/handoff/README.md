# Handoff reviews

This directory keeps two separate repository audits. They are evidence bookkeeping,
not normative protocol sources, release manifests, certification, or authorization
to publish. Git history preserves each source package; the current max-effort review
does not silently reinterpret the earlier standalone ledger.

## Current max-effort handoff (schema 2.0)

The `NCP_V1_0_CURRENT_HEAD_MAX_EFFORT_HANDOFF` declares tasks `T000` through
`T145` and twenty review lenses per task. Its frozen commit predates the reviewed
repository state, so the audit records both the declared `0ba5ff6` cut and the
explicitly diffed, inventoried, hosted-CI-green `f08c2ad` implementation cut.

- [`max-effort-source-index.v2.json`](max-effort-source-index.v2.json) is an exact
  non-normative extract of the ordered task, dependency, wave, lane, scope, and
  twenty-lens index from the SHA-256-bound external ledger.
- [`max-effort-audit-inputs.v2.json`](max-effort-audit-inputs.v2.json) records the
  handoff package checksums, updated source cut, complete intervening-diff identity,
  793-file inventory, current contract/corpus identities, package/wire boundary,
  handoff defects, and explicit external `NOT_RUN` gates.
- [`max-effort-task-review.v2.json`](max-effort-task-review.v2.json) maps every
  exact task to local implementation leads, acceptance gaps, residual risk, all
  twenty `OPEN` lens states, and a `reviewer_comment`. All 146 tasks remain
  `OPEN`; the decision is `NO_GO`.
- [`max-effort-file-review.v2.csv`](max-effort-file-review.v2.csv) and its
  [`manifest`](max-effort-file-review-manifest.v2.json) bind all 793 tracked paths
  at `f08c2ad` to exact Git blob IDs, SHA-256 digests, the mandated 21 columns,
  balanced review lanes, and the completed internal AI-assisted inspection. They
  explicitly record zero independent reviews and leave every disposition open.

The handoff dependency graph is a strict `T000`→…→`T145` chain even though its wave
document assigns dependent tasks to three parallel lanes. The review therefore
treats task completion as serial while allowing independent file inspection to run
in parallel. It also records that the handoff says 268 vectors, the exact frozen
manifest contains 269 (262 stable plus 7 migration), and the reviewed implementation
manifest contains 282 (275 stable plus 7 migration). The supplied inventory,
evidence-verification, and convergence helpers are not strong enough to establish
release evidence. Repository-owned generated threat, latent-path, supply-chain,
traceability, and local-convergence controls harden that bookkeeping while keeping
every unresolved dependency and external gate explicit.

## Earlier standalone handoff (schema 1.0)

The earlier `NCP_V1_0_STANDALONE_IMPLEMENTATION_HANDOFF` remains separately bound:

- [`audit-inputs.json`](audit-inputs.json) freezes the exact initial NCP source
  cut, handoff artifact hashes, local toolchain, hosted-CI receipt, downstream
  revisions, and known external-gate state used for the review.
- [`task-review.v1.json`](task-review.v1.json) maps the exact source-ledger task
  index `T000` through `T119` to inspected implementation coverage, retained
  evidence, gaps, and residual risk. Every task remains `OPEN`.

## Reviewer comments

Each task in both review ledgers has a `reviewer_comment` member. Leave it `null`
when there is no comment, or replace `null` with a non-empty JSON string. Comments
are review input only: they do not change task state, prove an acceptance criterion,
waive a dependency, satisfy an external gate, or authorize a release.

Run the structural and source-index guard after editing comments:

```bash
python3 scripts/check_handoff_review.py
python3 scripts/check_max_effort_handoff_review.py
python3 scripts/generate_file_review_ledger.py --check
```

The max-effort template generator preserves valid existing comments and can verify
that all other fields remain reproducible:

```bash
python3 scripts/generate_max_effort_review_template.py --check
```

The requested `0.9` release is intentionally not implemented as a version-label
change. Repository HEAD is a package/wire `1.0` candidate, so a genuine `0.9`
release requires a separately reviewed normative rebaseline and coordinated
consumer migration. No DOI or Zenodo archive is assigned. Historical annotated
tags and existing GitHub Release objects are retained as compatibility, migration,
citation, and provenance records. Tags anchor source history; GitHub Release
objects remain editable historical metadata. No erroneous candidate tag exists.

## Independent advisor attempt

On 2026-07-14, the development-only exact `claude-fable-5` advisor was invoked
without tools, MCP, repository-wide context, or a fallback model. Its bounded
context contained only `NEURO_CYBERNETIC_PROTOCOL.md`,
`scripts/check_acl_template.py`, and `scripts/verify_acl_deployment.py`. The
Claude CLI exited with status 1 before producing advice, so no advisor finding
was accepted. The owner-local failure receipt has SHA-256
`d67d1dfdeb59f23a94ae8ed31bbdcb0c3f33977fe0c1369d851cce7aa80ed382`;
it is review bookkeeping, not protocol evidence or a release gate.

After exact-session ACL hardening, a second narrow invocation supplied only
`scripts/check_acl_template.py`, `scripts/render_acl_template.py`, and
`scripts/verify_acl_deployment.py`. It used the same exact-model, zero-tool,
zero-MCP, no-fallback policy and again exited with status 1 before advice. No
finding was accepted. The owner-local failure receipt has SHA-256
`cbf6578a94dcfd7e8e7c7e5457217a2bd6c48caccee8717dd6c9833f2e87ebcf`;
it is likewise development-review bookkeeping only.
