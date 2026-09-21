# NCP review and implementation handoff

**September 20, 2026. Final NCP v1 remains incomplete.**

This handoff must survive the current Codex session.
The [independent review request](INDEPENDENT_REVIEW_REQUEST.md) defines the questions, requirements, and evidence limits.
The [source roster](reviews/v1-independent-20260920/STATE.json) fixes the repository snapshots and private Engram supplement.
The [gate summary](reviews/v1-independent-20260920/GATE_SUMMARY.md) separates passing source milestones from unfinished candidates.

## 1. Transfer these materials

Give the reviewer this GitHub branch and `NCP-review-and-implementation-handoff-20260920.zip`.
The ZIP stays private. It contains the pinned Engram supplement and selected unpublished implementation preparation.
Its README and manifest identify every included file, source, hash, and limit.
The original `NCP-independent-review-private-engram-20260920.zip` remains unchanged inside that bundle.
Extract it separately to read the `engram/` source paths referenced by the review request.

All other project sources are public.
The two review branches preserve unfinished code that is absent from `main`:

| Repository | Review branch | Implementation to inspect |
| --- | --- | --- |
| NCP | `review/ncp-v1-independent-20260920` | `2287198dd421ab2408f4426bdce1eccc8944cf20`; later branch commits add handoff documents |
| Prisoma | `review/ncp-owned-session-20260920` | `dd756d2ddd88777c75a3f7cdf7834fbc8b4dc09e` |

Preserve these branches until the review and useful implementation work are integrated.
Do not depend on an old temporary checkout or an active conversation.
The failed NCP gate's temporary build directories were removed after source preservation and observed-process checks.

## 2. Reviewer output

Return one Markdown review with stable finding IDs.
For each finding, identify the pinned source, failed requirement, shortest counterexample, consequence, proposed repair, and decisive verification.
Separate observed defects, deductions, design choices, missing measurements, and unavailable evidence.
Rank the five most important findings.
Choose the supported v1 compositions and explain each exclusion.
Do not silently remove the user's many-entity, modular-sensor, or embodied-experiment requirements.

Use the twelve lenses and ten alternatives in the review request.
Question those alternatives if a better design exists.
A council opinion cannot replace a failed scientific, security, provenance, or release gate.
Record the reviewed commit IDs and the private bundle's SHA-256 in the returned review.

The implementation agent must receive that review together with this handoff and the private ZIP.

## 3. Implementation intake

1. Read each affected repository's current `README.md` and `AGENTS.md`.
2. Inventory current branches, worktrees, staged changes, unstaged changes, and remote heads.
3. Fetch the two review branches without replacing another contributor's working state.
4. Compare current `main` with the pinned snapshots before applying any change.
5. Record each review finding as accepted, rejected, or deferred, with its reason and verification requirement.
6. Reconcile useful code at the component or hunk level.
7. Run the owning milestone's complete applicable gate.
8. Commit and push finished milestones to `main`.
9. Verify the remote commit and retain the exact gate result.

Some exact-source gates require a clean local successor commit before execution.
Create that local commit when required. Push or promote it to `main` only after its complete gate passes.
Use an isolated checkout when tests build pinned dependencies.
Keep those dependency sources and pins unchanged.
Do not merge either review branch merely because it is available remotely.
Retain failed attempts. A corrected rerun is a new observation.

## 4. Immediate unfinished work

### NCP candidate

Published `main` is `e61f4d0e90f717d0631addc0802a26c3fd590cce` at this snapshot.
Candidate `2287198` has a known test-source formatting defect.
Pinned Ruff `0.15.21` requires the multiline assertion shown in the gate summary.
The complete gate stopped there after 3,590.25 seconds.
Later installed-SDK, packaging, and policy results are unavailable for that attempt.

Inspect the historical-source exclusion before retaining it.
It excludes only the root workspace lock from the historical SDK comparison.
Current source stability and dependency checks must still cover that lock.
After the repair, regenerate affected inventories through their owning generators.
Do not edit generated evidence by hand or change frozen historical SDK bytes.
The audit generator covers tracked source files, including any handoff documents retained in the implementation commit.

Use the focused source controls while editing:

```sh
python3 -I scripts/test_local_sdk_gate.py
python3 scripts/generate_audit_artifacts.py --self-test --write
python3 scripts/generate_audit_artifacts.py --self-test --check
python3 scripts/check_audit_artifacts.py --self-test
python3 scripts/check_markdown_links.py --self-test
python3 scripts/check_markdown_links.py
```

Before promoting the candidate, run the complete gate:

```sh
bash scripts/check.sh
```

Read that script's prerequisites before scheduling it.
Use the pinned formatter and dependency tools.
Supply-chain regeneration requires the script's prepared advisory environment, not an arbitrary local RustSec checkout.
The prior run used a six-hour outer allowance and two Cargo jobs.
Its unchanged inner limits remained authoritative. The run failed normally, not by timeout.
A focused pass cannot substitute for the required complete result.

### Prisoma owned sensor helper

Published `main` is `56e835d7d6979df0a2ffeac6050e3860ddf8b1ea` at this snapshot.
The review branch changes `crebain.py` and adds `test_owned_crebain.py` under `integrations/agent-bridge/`.
It also contains a short review request.
Its source distribution, installed wheel, 48 installed Python controls, and focused lint checks passed.
These results do not qualify native execution.

The helper enters CREBAIN's `body_session` during the synchronized canonical Prepare callback.
Explicit Finish must join body completion, capture finalization, and canonical finalization.
Caught dispatch failures remain latched. Cleanup must preserve distinct earlier failures.
Review these properties before extending the implementation.

The capability projection is stale, and the candidate audit reports `LIVE_SOURCE_DRIFT`.
The complete development gate and native owned-helper campaign are **NOT RUN**.
Use the owning generator and candidate workflow after deciding which changes to retain.
Do not rewrite a source hash merely to convert a failure into a pass.

Relevant commands are:

```sh
uv sync --locked --group ui
just capability-matrix
just capability-matrix-check
just docs-audit
just release-candidate-audit
just application-bridge-check /absolute/path/to/isolated-installed-python
just check
```

The Python argument must select a fresh installed candidate wheel, not a source-tree import.
Read `justfile` and the Agent Bridge guide for additive checks and dependency prerequisites.
The candidate capture workflow follows the source commit. It is not a shortcut for a pre-commit audit failure.

The private bundle preserves a proposed native campaign and worker drafts.
They are **unexecuted preparation**, with local path and custody dependencies.
They are not a portable runner or a qualification receipt.
Reconstruct the prerequisite closure, review the workers, and freeze a fresh execution plan before use.
The draft calls its 24-GiB admission floor free memory, but the retained driver checks free disk space.
Correct that description in the successor plan. Define any RAM admission separately and preserve the original frozen preparation.
The old Prisoma gate wrapper points to the prior local checkout and a Python 3.13 environment.
That checkout now contains published `main`, not the review candidate.
Create a fresh runner bound to the successor checkout and its selected installed Python environment.
Keep the raw M1 body fixture separate from the earlier coupled-neural schedule.
Their exchange budgets are 476 and 496, respectively.

## 5. Choose the next useful product milestone

Let the independent review determine the implementation order.
The strongest current candidates are:

1. Close the two source candidates' gates and native lifecycle gaps.
2. Complete one bounded CREBAIN–Prisoma experiment with forecasts, selected actions, independent branch labels, and matched baselines.
3. Measure transport cost and tail latency for explicitly declared sensor workloads.
4. Extend and qualify the body profile for the requested many-entity experiments.
5. Qualify optional monitoring or authorization through their own contracts.

These items are priorities to assess, not permission to advertise unfinished capabilities.
Native city support for 1–256 drones does not qualify the current single-drone NCP sensor application.
Existing LeWM inference does not complete the embodied experiment.
Galadriel remains optional. Its evidence grants no command authority or proof of attack.
Haldir's current velocity semantics require reconciliation before use with force-ground commands.
Engram's complete PDF-to-embodied-experiment workflow remains a target.

## 6. Protected work and release boundaries

Do not edit PID-RS, its pins, schemas, branches, or another agent's checkout.
Do not alter Engram KG, ingestion, oMLX, or their active branches and worktrees.
Original shared checkouts can contain unrelated staged or unstaged changes.
Repository names and branch names do not prove ownership.

Completed source milestones are pushed to the `main` snapshots in the roster.
That statement is not final product, controller, performance, deployment, or scientific qualification.
The local modular SDK, earlier four-owner reference, and broader wire-1.0 candidate remain distinct surfaces.
Existing package versions do not establish a final ecosystem v1 release.

Check official Zenoh releases and resolved features before removing either project's retained dependency repair.
The dated upstream finding is recorded in the review request.
An agent review cannot close NCP's qualified-human-review issue.

For every completion claim, name the exact tested scope and remaining limits.
Remove a review branch only after its useful code, rejected alternatives, and audit evidence are preserved.
