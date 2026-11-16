# NCP 2 revision 6 -- independent third review (DRAFT, in progress)

Status: advisory, non-normative, certifies nothing. Read-only review of the frozen
snapshot `rev6-snapshot` (revision 6 = `git diff c42e346` plus new files).
Marks: [C] confirmed (read or ran), [S] suspected.

## Progress
- 0. Survey of the snapshot: started.
- 0. Read: spec/NCP-2.md (all), spec/NCP-2-LOCKSTEP.md (all), python/ncp/{lockstep,owner,client,messages,frame(encode)}.py,
  python byte-stream serve(), zenoh python Server, rust/src/{lockstep,owner}.rs, rust client Error enum,
  model/lockstep.py (all), diff of tests and docs.

## Leads to probe (before verification)
- L-A: Rust lockstep returns Error::Usage ("the request was not sent"; Error::executed() == No) after a step or take
  executed (malformed ok) and for recover()'s "no verdict" -> a false "not executed" through the public API.
- L-B: model S1 is stronger than the profile: restarts to an older clock or to no clock are not modeled; the
  profile (sec. 7 "Restarts") says such a restart turns a step that ran into "did not run". Guide overclaims.
- L-C: S3, S4, progress have no mutant; check they can fire.
- L-D: model README "426,777 worlds in about 12 seconds" vs ~80 s measured by the previous reviewer.
- L-E: Rust validate/open/close lock the shared mutex for every operation (non-lockstep ops wait for a running
  step); Python passes non-lockstep ops through without a lock (and calls the application's open without one).

## Runs (scratch copy of the snapshot, Python 3.15.0, cargo 1.99.1, Apple M4 Max)
- `python3 -I -B python/tests/test_ncp.py LockstepTests -v`: 19 tests OK [C].
- `cargo test --offline --locked --test sessions` (debug): 49 passed [C].
- `python3 -I -B model/lockstep.py --faults 1`: 426,777 worlds, every property holds; 85.9 s wall, 64.8 s user [C]
  (model/README.md says "in about 12 seconds").
- Probes: /tmp/opus-rev6-probes/probe_a.py, probe_py.py; rust/examples/opus_probes.rs in the scratch copy.

## Candidate findings (a) to (g): verdicts
- (a) DEFECT, low [C] both SDKs. Declined body with ncp. members that cannot be encoded (2 MB, a set, an
  integer > 2^53-1) -> step raises FrameError -> byte stream sends bad_frame bound to the chain (client: not
  executed, true, but the session ends and the client is blamed; owner high stays 0). Members between the
  session bound and 1 MiB -> the owner ADMITS and KEEPS a response larger than the session bound (high=1);
  the client gets local.bad_frame, executed=unknown; on Zenoh every copy replays it. Python only: a non-str
  member name -> AttributeError escapes step and serve() (thread dies; client local.closed).
- (b) DOC/PARITY, low [C]. Rust open waited 503 ms for an executing 600 ms step and reported tick 1; Python
  open returned in 0 ms with tick 0. Both meet rule 5.1 ("before or after a step"). The shared test name
  "an open does not [wait]" is true only for a checked, not yet executing, step in Rust. Rust also makes
  every operation of every session (plain ops, open, close) wait for a running step (one Mutex<(S, Clock)>).
- (c) DOC, low [C]. At term 2^53-1 a declined take carries {"ncp.lockstep": {"term": MAX}} although no take
  ran; rule 6.2 says such a body "means that another take ran". Both SDKs stop (moved == term).
- (d) DOC, low [C]. Python: ProtocolError, client.ended False (session left open); Rust Error::Usage. Rule 3.4
  "the client then ends the session" is not what the SDKs do.
- (e) DEFECT (API), low [C]. Python: after no verdict, stepper.client is the old dead client, uncertain stays,
  step -> UsageError; wrapping the new client costs one more take and one declined take (term 2 -> 4).
  Rust: recover takes the client by value and drops it on Err: the dropped opening holds the ticks.
- (f) DOC/DESIGN, low [C]. Restart at tick 0 to another world without a clock: recover says "did not run"
  (step 1 ran in the old world). Profile sec. 7 says a restart to the same tick with another state gives
  no verdict; false at tick 0 because S starts null (the SDKs never ask state() before the first step).
- (g) DEFECT, low [C]. Python Lockstep(tick=2**60) and Rust restored(tick>=2^53) are accepted; every lockstep
  open then fails to encode -> bad-frame rule (Rust probe: open -> local.closed "integer magnitude"). At
  tick 2^53-1 the next step cannot be sent (UsageError) and the profile says nothing. Rust validate at
  tick u64::MAX panics "attempt to add with overflow" (lockstep.rs:223, debug) while holding the mutex;
  reachable only through the Handler methods, not through an owner.

## New finding (so far)
- N1 DEFECT, medium [C]. Rust lockstep returns Error::Usage, documented "the request was not sent", whose
  executed() is No, after a request executed: recover() with no verdict (probe: step 2 ran, other client
  stepped, recover -> Err(Usage), e.executed() == No); step() after an ok without the tick (probe: 'move'
  executed, Err(Usage), executed() == No); take() after a malformed ok. Python raises ProtocolError (no
  executed attribute), which is neutral.
- N2 DOC (overclaim), low-medium [C]. Model S1 fails for restarts that profile rule 5.7 allows; the model
  never explores them. Scratch faults (model_probe.py fresh_restart): "restart without a saved clock" and
  "restart to the clock saved before the last step" -> S1 "'did not run' for a step that ran" in both shapes.
  The guide says "a step that recovery says did not run never runs"; the model README limits omit this.
- N3 DEFECT (MUST), low [C]. Rule 4.1: a take names the term told LAST in the session. ncp.lockstep.take()
  (and Rust take()) always start from the open report's term: after a declined step told term 2, the
  re-take sent term 0, was declined, then 2 (probe_41.py). Wastes one of the 3 attempts.
- N4 TESTS, low [C]. requirements.json maps only spec/NCP-2.md (85 entries); no profile line is mapped.
  Client MUSTs of the profile without any test in either SDK: 3.4 (report check), 6.1 (term + 1), 6.3
  (ncp.tick names tick and request), 6.2 SHOULD (stop after 3 takes). Python has no test that a step waits
  for a checked take (Rust has a_step_waits_for_a_checked_take).

## Model check (lockstep.py)
- Reproduced 426,777 worlds; self-test 9/9 (previous reviewer's log).
- Live properties: my mutants make S3 (tick moves by two), S4 (judge never decides), progress (every take
  declined) fire; none of the nine shipped mutants exercises S3, S4, or progress.
- constant_nonce is reported as L1 only because two byte-identical open responses make the ghost pick the
  wrong opening (max over w.opened); with L1 off, S2 catches it with zero faults.
- take_without_term and take_keeps_term pass every safety property with L1 off: the term guards stability
  (L1) only. verdict_ignores_state is caught only by S6 (S1 alone misses it). verdict_from_open_report: S1
  catches it without S6 in 3 of 4 configurations.
- Not modeled: restarts to an older clock or no clock; application failure (rule 5.5); result_too_large;
  stop/shutdown and bad frames (the Ended NO branch of react is unreachable); concurrency (stated);
  LockstepClient/take() (the model re-implements the client program; only judge is shared); Rust.
- Two faults (advisory, not gate evidence): `--faults 2 --shape stream --max-worlds 12000000`: 5,259,265 +
  2,106,563 = 7,365,828 worlds, every property holds, 4 min 57 s; `--shape zenoh`: 1,641,006 + 255,359 =
  1,896,365 worlds, every property holds, 2 min 20 s [C]. Release record says two faults NOT RUN; the default
  --max-worlds of 3,000,000 stops the two-fault run, which is why "passes 3 million worlds".
- Cross-language test test_python_lockstep_client_with_the_rust_lockstep_owner: OK (debug examples) [C].
- Zenoh LockstepRoutingTests (2) + RoutingTests: 8 OK with the zenoh venv [C]; they drive Server._on_query.
- check_ncp2_requirements.py: 85 requirements, 262 references, 3 untested with a reason; check_ncp2_rules.py OK.
- Shortcomings doc (mtime 16:18) counts: Rust 6,184 / Python 4,929 / spec 553; snapshot wc -l: 6,191 / 4,939 /
  554 (sources edited 16:30-16:35). Trivial drift.
- Self-test re-run: 9 of 9, same properties as before, 65 s [C].
- N7 probe: probe_n7.py (wrapper declines after Lockstep.validate -> take in another session waits) [C].

## Status
Final report written: opus-review-rev6.md (this draft is superseded by it).
