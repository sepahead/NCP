# Recovered local changes

This archive preserves 89 non-temporary files from an unpublished local snapshot.
It is historical recovery input, not a tested integration or release candidate.

`manifest.json` identifies the original base, patch digest, and recovered file hashes.
`recovered.patch` contains the exact binary-capable Git diff against that base.
The archive excludes 977 temporary review images. The private recovery bundle retains them.

To inspect the original changes, apply the patch in a separate checkout of the manifest's base commit.
Do not apply it directly to current `main`.
Later commits contain security fixes, regression tests, modular SDKs, and corrected scope documents.
Integration must preserve those changes.

The snapshot includes experimental transport, client, NEST runner, diagram, and mathematical documentation work.
Generated files and task-ledger entries remain historical inputs. They grant no current evidence or completion status.
The archive does not modify runtime code on this branch.

Verification covers patch application, exact recovered-file hashes, and whitespace in this archive's prose.
Runtime, interoperability, security, scientific, and release qualification are **NOT RUN** for this snapshot.

Current reconciliation starts from `e61f4d0e90f717d0631addc0802a26c3fd590cce`.
The separate `review/ncp-v1-independent-20260920` branch retains the earlier implementation candidate and independent-review handoff.
