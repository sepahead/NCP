# Advisory reviews of NCP 2

This folder keeps the advisory reviews of NCP 2 revisions 4 to 6 and their working files.
Language models wrote them: Fable 5.2 and Opus 5.5, each read-only, on copies of the repository.
They are advice. They are not normative, and they are not certification evidence: they certify no security, safety, interoperability, scale, or release readiness.

The decisions that followed each review are in the [design record](../../docs/design/NCP-2-DESIGN.md), sections 13 to 15, with the check for each decision.
The work that is still open is in the [migration plan](../../docs/design/NCP-2-MIGRATION.md), "Open work after revision 5" and "Open work after revision 6".

## The reviews

| Date | Reviewer | What it reviewed | Report | What followed |
| --- | --- | --- | --- | --- |
| 14 November 2026 | Fable 5.2, extra high effort | Revision 4 (`44bc3ca`): design, architecture, shortcomings, and figures | [fable-review-rev4.md](2026-11-14-fable-review-of-revision-4/fable-review-rev4.md) | Revision 5 (`7edc3f9`): the lockstep holder is an opening; the schema exemption; design record, section 14 |
| 14 November 2026 | Fable 5.2, extra high effort | Revision 5: the false verdicts that remained in the lockstep profile, a take request, a model check, and figures | [fable-consult-rev5.md](2026-11-14-fable-consult-on-revision-5/fable-consult-rev5.md) | Revision 6 (`28fb8cc`): `ncp.lockstep.take` with a term, feature operations, `model/lockstep.py`, three figures; design record, section 15, rows 45 to 51 |
| 15 November 2026 | Fable 5.2 (stopped at a usage limit), then Opus 5.5, maximum effort | The draft of revision 6 | [opus-review-rev6.md](2026-11-15-review-of-the-revision-6-draft/opus-review-rev6.md) | Fixed in `28fb8cc`; design record, rows 52 to 58 |
| 16 November 2026 | Opus 5.5, maximum effort (stopped at a usage limit after four checkpoints) | The fixes of `28fb8cc` | [verify-draft.md](2026-11-16-verification-of-the-fixes/verify-draft.md) and the author's [triage](2026-11-16-verification-of-the-fixes/triage-by-author.md) | Fixed in `4e5a6de`; design record, rows 59 and 60 |
| 16 November 2026 | Fable 5.2, extra high effort | Revision 6 (`904f87c`): the architecture against the product, the next profiles, the tag scope, design flaws, and figures | [design-review.md](2026-11-16-fable-design-review/design-review.md) | The lockstep figure (`dd135ba`); the ranked open work in the migration plan |

## What each folder holds

- The report, and the reviewer's draft with its checkpoints. The draft shows how the reviewer reached each finding.
- `probes/`: small programs that reproduce a finding on a copy of the SDKs, with their logs.
- `prototype/` and `checker/`: code that tests a proposed design, such as the model check of a take request and of a history identity in the lockstep clock. It is evidence for a design, not a patch for this repository.
- `figures/new_figures.py`: the figure code that the consult proposed. The figures in `docs/diagrams/` come from `scripts/gen_diagrams.py`.
- Logs of the gates, model checks, and tests that the reviewer ran.

## Read them with care

- Each report describes the commit named in its header. Later commits fixed many of the findings; the design record says which.
- A report can be wrong. The author checked each finding against the code before acting on it, and recorded where a reviewer was wrong, for example in the triage of the verification.
- The designs in the last review (decline reasons, a stream profile, an authority profile, rounds revision 3, a history identity) are proposals. None is implemented or checked in this repository.
- Paths are shortened: `<workspace>/` is the folder that holds the repositories, and `<reviews>/` is the original folder of these reviews. The scratch copies of the repository, the build outputs, and the PNG renderings of the reviews are not kept here.
