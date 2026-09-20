# Retained gate results for independent review

This file reports local observations. Complete local execution logs are not published in this repository.
The separate private handoff bundle contains selected gate and preparation artifacts, identified by its manifest.
Artifact hashes in `STATE.json` identify retained bytes. Unavailable bytes remain independently unverifiable.

## Review packet checks

The packet checks cover maintained Markdown links, authored-file whitespace, and source references.
Original inputs are checked by byte length and SHA-256.
The supplied acceptance plan retains its extra trailing blank line, which the archive-inclusive whitespace check reports.
Historical inputs remain unchanged. These packet checks do not qualify either application candidate.

## NCP candidate

- Commit: `2287198dd421ab2408f4426bdce1eccc8944cf20`.
- Tree: `c1d9e6243223e7f710f52722a93d1fd529093ec3`.
- Command: `bash scripts/check.sh`.
- Result: **FAIL**, exit code 1, after 3,590.2492767500225 seconds.
- Outer allowance: 21,600 seconds. This run did not reach that limit.
- Candidate source and index bytes were unchanged.

The terminal output was:

```text
=== standalone local SDK + installed Python/Rust controls ===
Would reformat: scripts/test_local_sdk_gate.py
1 file would be reformatted, 1 file already formatted
```

Pinned Ruff `0.15.21` requires this existing assertion to wrap:

```python
with self.assertRaisesRegex(
    RuntimeError, "historical reference changed"
):
```

The correction is not applied on this review branch.
After correcting it, regenerate any affected source inventories and rerun the applicable complete gate.
Earlier passing sections cannot replace the missing terminal result.

Two earlier preparation attempts failed before useful full execution.
A third attempt was deliberately cancelled because its outer allowance was too short.
All remain separate retained observations. They supply no full-gate pass.

## Prisoma helper

The review branch contains two source changes over `56e835d7d6979df0a2ffeac6050e3860ddf8b1ea`.
The implementation built through a source distribution and installed wheel.
All 48 installed Python controls passed after a test-only fixture correction.
Focused Ruff checks passed. The first failed test run remains retained.

Capability projection verification fails because generated views are stale.
Candidate verification fails with `LIVE_SOURCE_DRIFT`.
The full development gate and native owned-helper campaign remain **NOT RUN**.
The existing published base's [nine-job CI run](https://github.com/sepahead/prisoma/actions/runs/35441764005) passed.
That result does not qualify this unmerged helper.

## Other completed source milestones

- Galadriel's [source CI](https://github.com/sepahead/galadriel/actions/runs/35440660367) passed for `a42f066`.
- Its [independent adapter CI](https://github.com/sepahead/galadriel/actions/runs/35440660366) passed.
- Its [fuzz and four mutation shards](https://github.com/sepahead/galadriel/actions/runs/35440660370) passed. The observational baseline job was skipped.
- Haldir's [main CI](https://github.com/sepahead/haldir/actions/runs/35441417914) and [formal checks](https://github.com/sepahead/haldir/actions/runs/35441417893) passed for `e51eaa8`.
- CREBAIN's [source CI](https://github.com/sepahead/crebain/actions/runs/35439488023) passed for `d397905`.

These are source milestones, not final NCP v1, physical-model, controller, or deployment qualification.
