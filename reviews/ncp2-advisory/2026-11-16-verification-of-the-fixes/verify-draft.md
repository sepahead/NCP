# NCP 2 revision 6: verification of the fixes (draft, in progress)

Status: advisory, non-normative, certifies nothing. Read-only review of commit `904f87c`
(revision 6 = `28fb8cc` plus a CI-only change). Scratch copy: `/tmp/ncp-verify`
(`git archive 904f87c`). Probes: `probes/` in this directory.

## Checkpoint 0 (setup)

- Previous review read: findings (a)-(g), N1-N8.
- Scratch copy exported. Next: read spec/NCP-2-LOCKSTEP.md, then lockstep.py / lockstep.rs.

## Checkpoint 1 (model reproduced; first reading of lockstep.py/.rs, owner.py/.rs)

- `model/lockstep.py --faults 1`: 469,268 worlds, all hold, 14.2 s (Python 3.15.0). Matches README.
- `--self-test`: 12/12; constant_nonce now caught by S2 (was L1 artefact); new mutants caught by
  S3 (step_moves_two_ticks), S4 (judge_never_decides), progress (take_always_declined). 11.5 s.
- Candidate new defects to probe:
  - P1 Python `take()` / `step()`: a malformed ok body that lacks `state` or `request` passes the
    `.get()` checks and then raises KeyError on `body["state"]` (take) / `member["state"]` (step),
    after the request executed; not `Ended(local.protocol, YES)`; session not ended. Rust treats a
    missing member as null and accepts it. Parity + incomplete fix of N1 on the Python side.
  - P2 `LockstepClient.take()` (both SDKs): after 3 declined takes, `term` is not updated from the
    last declined body; the next `take()` names a stale term (rule 4.1 MUST; residual of N3).
  - P3 Handler docs: `close(reason)` lists closed/ended/lost/shutdown/expired; owners now call
    `close("refused")` (both SDKs). Doc gap.
  - P4 model excuses (`w.other`, `w.rewound`, `w.older`) are global and permanent; test precise
    versions.

## Checkpoint 2 (SDK probes)

Python (`probes/probe_py.py`, log `probe_py.log`):
- P1 CONFIRMED. Take ok body without `state` (or `request`): `LockstepClient(...)` raises
  `KeyError: 'state'`; the take ran (owner holder = this opening, term 1); `client.ended` False.
  Step ok whose `ncp.tick` lacks `state`: `KeyError`; the step ran (owner tick 1, position 2);
  client tick stays 0, uncertain None, session open; next step declined "tick: the next tick is 2".
- P2 CONFIRMED. After `stepper.take()` fails (terms named 1,2,3; the last decline told 4),
  `stepper.term` stays 1; the next `take()` names [1, 4]. Rule 4.1 MUST. Residual of N3.
- P3 OK: recover after a malformed take keeps `uncertain`; a later recover gives YES.
- P12 (pre-existing, residual of (a)): an app `open` that grants an `Array` parameter: the encode
  passes, then `json.dumps(enabled)` raises TypeError out of `Owner.handle`; app.close not called.
- P13 (parity note): Python owner puts an Array attachment in a declined body; Rust cannot.

Rust (`probes/verify_probes.rs`, log `verify_probes.log`):
- R1: take ok body without `state`/`request` accepted as (0, None, None) [owner S = p0]. Python
  raises KeyError. Parity difference; Rust's leniency gives no false verdict (UNKNOWN at worst).
- R2: step ok `ncp.tick` without `state` accepted (state None); next step declined (state).
- R3 CONFIRMED: same stale term after a failed `take()`: terms named [1, 4].
- R4: `Lockstep::new` with a 200-char initial digest: silently S = None (Python raises ValueError).

## Checkpoint 3 (tests, requirements, texts)

- Python suite 107 OK (4 skipped); LockstepTests 28 OK; Rust `--test sessions` 58 passed.
- check_ncp2_requirements: 86 + 37 entries, 378 refs, 3 untested; rules check OK.
- Mapping weaknesses: 5.6 entry (MUST NOT on applications) "covered" by a test of its last sentence
  only; "A client MUST NOT act on detail" covered by tests whose detail agrees with the member;
  3.1 "an owner ignores members" untested; 5.7 MUST (restore T,S,R from one saved clock) is an
  application duty mapped to a client-side test; 4.3 mapped to model S3 (model's own client code).
  New tests `*profile_members_that_cannot_be_encoded_leave_the_detail` and the new vector
  "an operation of a feature that the session did not enable is unknown" are referenced nowhere;
  rule 15.3 (feature operations) has no entry (no RFC keyword, section 15 not numbered-scanned).
- Line counts in SHORTCOMINGS: Rust 6,328 (claimed 6,324), Python 5,029 (claimed 5,027). Trivial.
- Figures: lockstep card "From revision 6" now right; verdicts adds "any other code"; ladder says
  "Apart from an open at check 3". Verdicts figure still files a rejected `open` under "It never
  runs ... and it never will" although a copy of that open can open the session later (7.1.8).
- Running in background: two-fault model (stream, zenoh) with --max-worlds 60000000.

## Checkpoint 4 (model investigations)

- Two faults reproduced: stream 5,608,895 + 2,478,210 = 8,087,105; zenoh 2,023,082 + 403,949 =
  2,427,031; total 10,514,136 = README / release record. All hold. 4 min 18 s + 1 min 38 s.
- `probes/model_probe.py count` (1 fault): progress is evaluated in exactly ONE world per
  configuration (the unique fault-free, time-limit-free terminal world). Not vacuous (the mutant
  take_always_declined trips it) but it only says "the happy path finishes".
  The weakened S1 branch (older restart) is used: 60 "did not run" verdicts for steps that ran
  before an older restart (50 in zenoh/one id). UNKNOWN verdicts: 948 = 687 other + 170 rewound
  + 91 older.
- `precise`: S4 with a precise excuse (state at the take is neither L's known state nor known +
  its uncertain step, or the state epoch changed) and S6 without `w.other`: the shipped SDK passes
  all four configurations. So the shipped excuses are wider than needed.
- `own` mutant (client gives no verdict unless it made the request that produced its known
  clock): the shipped model passes it everywhere (394 clean UNKNOWNs excused by w.other);
  `own-precise` catches it (S4, trace: other client steps before L takes; L steps; time limit;
  recovery). CONFIRMED: S4's global excuses hide recovery defects that follow an earlier fault.
