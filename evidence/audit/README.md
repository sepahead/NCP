# Retained candidate audit artifacts

This directory retains machine-checkable review controls for the unreleased,
release-blocked 1.0.0-rc.1 candidate. The records are non-normative: they do
not change wire 1.0, certify an implementation or deployment, satisfy an
external gate, close the broader handoff, authorize publication, or create a
release. No DOI or archive-deposition claim is recorded here.

## Artifacts

- threat-register.v1.json records the current system dimensions, trust
  boundaries, ten mandatory counterfactuals, and 18 threat, misuse, failure, and
  unusual-input cases. Every risk remains explicitly OPEN, with accepted and
  rejected cases, controls, tests, evidence paths, and residual gaps.
- latent-path-inventory.v1.json inventories configured deferred-work,
  warning, workaround, placeholder, unimplemented, dormant, experimental, and
  fallback marker families across Git-indexed and non-ignored untracked UTF-8
  files. It retains the byte count, SHA-256, Git blob identity, and index status
  of every scanned or excluded file. Each occurrence is content-addressed and
  has a reviewed disposition, claim effect, and evidence link. A newly
  unreviewed action path fails the checker.
- requirement-traceability.v1.json covers the exact union of conformance
  requirements, phased release gates, complete contract-surface claims, and
  threat-control requirements. Every node links source, implementation, test,
  retained evidence, verification command, claim tier, status, and explicit
  graph edges.
- manifest.v1.json binds those three generated records and their primary source
  inputs by SHA-256 and byte count.

The JSON files are generated outputs. Change
scripts/generate_audit_artifacts.py, then regenerate and review the complete
diff; do not edit generated records by hand.

## Rebuild and verify

From the repository root:

    python3 scripts/generate_audit_artifacts.py --self-test --write
    python3 scripts/generate_audit_artifacts.py --self-test
    python3 scripts/check_audit_artifacts.py --self-test

The generator performs deterministic hostile scanner checks. The independent
semantic checker rejects duplicate JSON members, stale content and hashes,
missing threat or counterfactual coverage, undispositioned paths, broken source
references, incomplete graph edges, and any local claim substituted for an
external or post-publication gate.

## Evidence boundary

The artifacts demonstrate only that the current repository-owned audit records
are present, reproducible, internally linked, and fail closed under the checked
mutations. They do not supply independent review, live mTLS/ACL/rotation or
revocation evidence, independent installed peers, duration fault/soak/fuzz or
sanitizer campaigns, performance certification, signed supply-chain evidence,
clean-room reproduction, consumer certification, publication evidence, or
post-publication validation. Those items remain NOT RUN or otherwise open
until evidence bound to the exact candidate source and artifact set exists.
