# Standalone implementation handoff review

This directory records the repository audit against the supplied
`NCP_V1_0_STANDALONE_IMPLEMENTATION_HANDOFF`. It is evidence bookkeeping, not a
normative protocol source, release manifest, certification, or authorization to
publish.

- [`audit-inputs.json`](audit-inputs.json) freezes the exact initial NCP source
  cut, handoff artifact hashes, local toolchain, hosted-CI receipt, downstream
  revisions, and known external-gate state used for the review.
- [`task-review.v1.json`](task-review.v1.json) maps the exact source-ledger task
  index `T000` through `T119` to inspected implementation coverage, retained
  evidence, gaps, and residual risk. Every task remains `OPEN`.

## Supervisor comments

Each task has a `supervisor_comment` member. Leave it `null` when there is no
comment, or replace `null` with a non-empty JSON string. Comments are review
input only: they do not change task state, prove an acceptance criterion, waive
a dependency, satisfy an external gate, or authorize a release.

Run the structural and source-index guard after editing comments:

```bash
python3 scripts/check_handoff_review.py
```

The requested `0.9` release is intentionally not implemented as a version-label
change. Repository HEAD is a package/wire `1.0` candidate, so a genuine `0.9`
release requires a separately reviewed normative rebaseline and coordinated
consumer migration. No DOI or Zenodo archive is assigned. Historical tags are
retained because released-baseline and migration checks use them as immutable
evidence.

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
