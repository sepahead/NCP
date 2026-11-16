# Triage of the verification draft (author, 2026-11-16)

Source: `verify-draft.md` checkpoints 0-4 (Opus 5.5 max, stopped at its weekly limit before a final report).
Base: NCP `main` at `904f87c`. All items below are to be fixed in one commit, then both NCP 2 gates.

| Item | Triage | Planned fix |
| --- | --- | --- |
| P1 Python take/step ok body missing `state`/`request`: KeyError after execution | Confirmed defect | Require the members to be present; missing member = `Ended(local.protocol, YES)` |
| R1/R2 Rust accepts missing members as null | Parity | Same presence check in Rust |
| P2/R3 `LockstepClient.take()` keeps a stale term after 3 declined takes | Confirmed defect (rule 4.1) | Update `term` from the last decline's member, both SDKs; tests |
| P3 `close("refused")` undocumented | Doc | Handler docs in both SDKs |
| P12 Python open granting an Array: TypeError out of `Owner.handle` | Defect (residual of (a)) | JSON copy inside the try; refuse; test |
| P13 Python declined body can carry an Array; Rust cannot | Parity | Keep only JSON members in Python |
| R4 Rust `Lockstep::new` drops an invalid initial digest silently | Parity | Panic with a clear message, as Python raises |
| Mapping: 5.6, "MUST NOT act on detail", 3.1 ignores members, 4.3 model ref, new tests/vector unreferenced, rule 15.3 no entry | Valid | New tests (other ops leave the clock; detail disagrees with member; extra open parameters); refs; scan section 15 |
| Line counts | Trivial | Recount |
| Verdicts figure: a rejected open "never will" | Valid (7.1.8) | Note sentence |
| Model: progress in one world only | Doc | README wording |
| Model: S4/S6 excuses global; `own` mutant passes | Confirmed weakness | Precise S4/S6 excuses from `probes/model_probe.py`; add `own` mutant |

## Status (2026-11-16, author)

All items above are fixed in the worktree `.ncp2-fixes` (branch `ncp2-rev6-fixes`, from `904f87c`), not yet committed:
- SDKs: presence checks (take, step, open report) in both; `_told_term`/`told_term`; `take()` keeps the told term; recover ends the session on a declined take; Python plain-JSON members and open parameters; Rust `Lockstep::new` panics on a bad digest; `close("refused")` documented.
- Tests: 7 new in each SDK (Python LockstepTests 35; Rust sessions 65).
- Model: exact S4 excuse (ghosts known_current/known_epoch, taken with current+epoch, after_step, epoch on rewound), S6 without `w.other`, 13th mutant `verdict_needs_own_request` (caught by S4); 469,268 worlds; 13/13.
- Requirements: section 15 numbered rules (15.1-15.3) mapped; new test refs; 89 + 37 lines, 405 refs.
- Docs: verdicts figure note, model README, CHANGELOG, design rows 59-60, migration rows, line counts.
- Checks so far: Rust 65+11, Python 114, rounds 10, Zenoh 31, quick checks OK. NCP 2 gate running (log gate10-main.log in the job tmp dir).
