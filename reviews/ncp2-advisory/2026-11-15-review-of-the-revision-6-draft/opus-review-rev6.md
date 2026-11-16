# NCP 2 revision 6: independent third review

Status: advisory and non-normative. It certifies nothing. Read-only review of the frozen snapshot
`rev6-snapshot` (revision 6 = `git diff c42e346` plus the new files of `revision-6.status`).
This review continues the review that `fable-review-rev6-draft.md` started; it verifies that
review's seven candidate findings, completes the model, parity, and claims review, and looks for
problems elsewhere in NCP 2.

Marks: **[C]** confirmed (I read the code or text, or ran it), **[S]** suspected.
Every run used a scratch copy of the snapshot (Python 3.15.0, cargo 1.99.1 `--offline --locked`,
Apple M4 Max). Probes and logs are in [`opus-rev6-probes/`](opus-rev6-probes/README.txt).

## 1. Verdict

Revision 6 does what it set out to do. Moving the takeover from `open` into the feature operation
`ncp.lockstep.take`, adding the term, and judging recovery from the whole clock in the take's
response closes the false "did not run" of revision 5 in every scenario that the model explores.
I reproduced the gate's model check (426,777 worlds, one fault, every property holds) and ran it
with **two faults** as well: 9,262,193 worlds, every property holds. All lockstep tests pass in
both SDKs, as do the cross-language test and the two new Zenoh routing tests. I found no defect in
the core exchange rules.

The defects are at the edges:

- **One medium defect (N1).** The Rust lockstep client returns `Error::Usage` after requests that
  were sent and executed. `Error::Usage` is documented as "the request was not sent", and
  `Error::executed()` maps it to `No`. After a step that ran, a recovery without a verdict therefore
  reads as "not executed" through the public API.
- **Low defects.** Owner-built responses that carry handler data are encoded with no bound and no
  fallback (a). The `take` helper breaks the MUST of rule 4.1 (N3). The recovery API cannot go on
  after "no verdict" (e). A handler that wraps `Lockstep` can deadlock every session (N7). Ticks
  above 2^53 − 1 are accepted (g).
- **Documentation.** The plain-words guide states a safety property more strongly than the profile
  does and than the model checks (N2). The model README's time is about seven times too short.
  Several profile sentences contradict edge cases: (c), (d), (f), N6. The client MUSTs of the
  profile have no tests (N4).

I recommend fixing N1 and N2 before the tag. The rest can be SDK patches and text corrections in
the profile, which is provisional anyway.

## 2. Candidate findings (a) to (g)

| # | Rating | Summary |
| --- | --- | --- |
| a | **Defect, low** [C] | Profile members and handler-given feature parameters are encoded with no bound and no fallback; the owner blames the client or keeps a response that it cannot deliver |
| b | **Parity and documentation, low** [C] | Rust `open` waits for an executing step, and Python `open` does not; both meet rule 5.1 |
| c | **Documentation, low** [C] | Rule 6.2 is false at the largest term; both SDKs handle that case correctly |
| d | **Documentation, low** [C] | Rule 3.4 says the client "ends the session"; both SDKs raise and leave it open |
| e | **Defect (API), low** [C] | After "no verdict", the `LockstepClient` cannot go on; Rust drops the client that holds the ticks |
| f | **Documentation and design, low** [C] | At tick 0 the state digest is `null`, so a restart to another world at tick 0 gives "did not run" |
| g | **Defect, low** [C] | Ticks above 2^53 − 1 are accepted; every lockstep `open` then fails as a bad frame, and Rust can overflow |

### (a) Declined bodies with large or non-JSON `ncp.` members: defect, low [C], both SDKs

Both owners encode the `declined` response, with the profile members of `Declined(body=...)` or
`declined_with`, without the session bound (`reply(...)` with no `limit` in `python/ncp/owner.py`
`_call`; `small(...)` with `None` in `rust/src/owner.rs` `call`). An encoding failure escapes `step`
as `FrameError`, so the binding applies its **bad-frame rule to a good client frame**.

Probes: `probe_a.py` (Python, over a socket pair with `ncp.serve`) and `opus_probes.rs`
`probe_a_declined_members` (Rust).

| Member | Python result | Rust result |
| --- | --- | --- |
| 2 MB string | `bad_frame` bound to the chain; client: not executed; owner `high` 0 | `owner.handle` → `FrameError("the JSON region of 2000220 bytes exceeds 1048576")`; `high` 0 |
| A `set`, or an integer > 2^53 − 1 | `bad_frame`; `high` 0 | `FrameError("integer magnitude")`; `high` 0 |
| 100 kB, session bound 65,536 | The owner **admits and keeps** a response larger than the bound (`high` 1); client: `local.bad_frame`, executed **unknown** | Same: a response of 100,264 bytes is kept; client: `local.bad_frame`, unknown |
| A member name that is not a string (Python) | `AttributeError` escapes `step` and `serve()`; the thread dies; client: `local.closed` | Not possible (`Map<String, _>`) |

The same class covers the `open` path: `probe_a2.py` shows that an application whose `open` grants
a feature parameter of 70,000 bytes makes the owner **accept the session and keep a 70,448-byte
`open` response**. The client reads that response with the handshake bound of 65,536 bytes
(rule 7.1.3), so it gets `local.bad_frame`, unknown, while the owner holds a session that no
client can use.

All verdicts stay truthful (not executed, or unknown). The faults are these: blame on the client,
a session that ends for a request that was only declined, and a kept response that every copy
replays and no client can read (on Zenoh, every copy then times out). The reference lockstep
members are tiny, so only applications or future profiles that use these public APIs trigger it.

Fix: encode `declined` responses with `limit=state.bound`. If the members cannot be encoded or do
not fit, send the same `declined` response without them. Check that the `open` response fits
65,536 bytes; otherwise reject with `refused`. Ignore member names that are not strings. Spec:
state in rule 7.3.12 (or section 6.2) that a profile can add `ncp.` members to a `declined` body,
and that the response with them MUST fit the session bound. Today only section 15, rule 2 implies
that such members may exist.

### (b) Rust `open` waits for an executing step; Python never waits: parity and documentation, low [C]

`opus_probes.rs` `probe_b_open_waits_for_running_step` runs a 600 ms step. A Rust `open`, started
100 ms into that step, returned after **503 ms** with tick 1. `probe_py.py` (b): the Python `open`
returned after **0 ms** with tick 0.

Both meet rule 5.1 ("before or after a step, never in the middle"). The profile does not promise
that an `open` never waits. The Python comment says that the report "never waits for a step". The
shared test name `a_take_waits_for_a_checked_step_and_an_open_does_not` is true in Rust only for a
step that was checked but not yet executing. The mutex is free between `validate` and `execute`
and held for the whole of `execute`.

More significant for operations: Rust keeps the application and the clock in one
`Mutex<(S, Clock)>`. Every `open`, `close`, and plain operation of every session therefore waits
for a running step. Python passes plain operations, and the application's `open`, through without
a lock. This is against the intent of rule 9.2.8 (sessions independent) for Rust lockstep owners.

Fix: document the Rust behavior (or give the clock its own lock), and rename or split the shared
test.

### (c) Rule 6.2 at the largest term: documentation, low [C]

`probe_py.py` (c): when the term is 2^53 − 1, a take that names that term gets `declined` with
`{"ncp.lockstep": {"term": 9007199254740991}}`, and no other take ran (holder `None`). Rule 6.2
says that such a body "means that another take ran". The detail text `term: the term is E` is also
misleading here. Both SDKs stop correctly, because they stop when the term in the body equals the
term that the take named.

Fix: in rule 5.2, give the largest term its own detail text (for example `term: the largest term`)
and add the member only after a wrong term. Alternatively, qualify rule 6.2 with "with a term other
than the one that the take named".

### (d) Rule 3.4 says that the client "ends the session": documentation, low [C]

`probe_py.py` (d): against an owner that reports no `term`, `ncp.LockstepClient` raises
`ProtocolError` and leaves the session open (`client.ended` is `False`). Rust returns
`Error::Usage` from `reported_term` [C by reading]. No state is at risk: only the `open` was
admitted. The text and the SDKs still disagree.

Fix: let the SDKs close the session, or change rule 3.4 to "the client does not use the profile in
that session".

### (e) After "no verdict", the client cannot go on: defect (API), low [C]

- **Python** (`probe_py.py` (e)). `recover` raises `ProtocolError` after the take ran, so the new
  opening holds the ticks. `stepper.client` stays the old, ended client, `uncertain` stays set, and
  `step` raises `UsageError: the session has ended`. To go on, the caller must know to wrap the new
  client in a new `LockstepClient`. That costs one more take and one declined take: the term went
  from 2 to 4.
- **Rust** (`opus_probes.rs`, first probe). `recover(&mut self, client: Client<C>)` takes the
  client by value and drops it on `Err`. The dropped opening holds the ticks, `uncertain` stays
  `Some(2)`, and `step` returns `Usage("the session has ended")`. Another session and another take
  are needed.

Fix: on "no verdict", adopt the new client and the taken clock, clear `uncertain`, and return
`Executed.UNKNOWN` (Python) or `Ok(Executed::Unknown)` (Rust) instead of an error. This also
removes the false `No` of N1.

### (f) At tick 0 the state digest is `null`: documentation and design, low [C]

`probe_py.py` (f): the client knows `(0, None, None)`, and step 1 runs in the old world (position 2)
before its response is lost. The owner then restarts without a saved clock, with another world
(position 500). The recovery says **"did not run"**.

Profile section 7 says: "A restart to the same tick with another state, or with a clock of another
history, gives no verdict (rule 6.5)." That is false at tick 0, where S and R are `null` in every
history. Both SDKs start S at `null` (`state=None`, `Clock::default()`) and call `state()` only
after a step. The term "state digest" ("derives from its state after each step") leaves the
initial S undefined. Under the profile's restart semantics the verdict describes the current
state, so it is not false there; the sentence in section 7 is.

Fix: let `Lockstep` take the initial S from `state()` when no clock is restored. Define S "at the
start and after each step". Qualify the sentence in section 7.

### (g) Ticks near and above 2^53 − 1: defect, low [C]

`Lockstep(tick=2**60)` (Python) and `Lockstep::restored(tick = 1 << 60 or u64::MAX)` (Rust) are
accepted. The `term` is bounded; the tick is not.

- Every lockstep `open` then fails to encode, which applies the bad-frame rule to a good client
  frame. Rust probe: `open` → `local.closed: bad frame: integer magnitude`. Python probe:
  `FrameError: integer magnitude`.
- At tick 2^53 − 1 the next step cannot be sent: `UsageError: the request cannot be sent: integer
  magnitude` in both SDKs. The profile does not say what happens at the largest tick.
- Rust `validate` at tick `u64::MAX` panics with "attempt to add with overflow"
  (`lockstep.rs:223:72`, debug build) while it holds the mutex, which poisons it. This is reachable
  only through the `Handler` methods (`probe_g_large_ticks`), not through an owner, because the
  take's response can no longer be encoded.

Fix: bound the restored tick at 2^53 − 1 in both constructors, as for the term. Add to rule 5.4 or
5.7 that an owner at tick 2^53 − 1 declines every step.

## 3. New findings, by severity

### N1. Rust lockstep errors claim "not executed" for requests that executed: defect, medium [C]

`rust/src/client.rs` documents `Error::Usage` as "A call that the client refuses before it sends
anything: the request was not sent", and `Error::executed()` returns `Executed::No` for it.
`rust/src/lockstep.rs` returns `Error::Usage` in three places after a request was sent and
executed:

1. **`recover` with no verdict** (`judge` → `Error::Usage("the owner is at tick …")`), after the
   take ran. Probe `opus_probes.rs` `probe_la_recover_no_verdict_reads_as_not_executed`: step 2
   ran (owner tick 2), its response was lost, and another client took the ticks and stepped. The
   result was `recover → Err(Usage(...)), e.executed() = No; step 2 actually ran: true`. The test
   `a_restart_to_the_same_tick_with_another_state_gives_no_verdict` asserts `Err(Error::Usage(_))`
   for this case.
2. **`step` after an `ok` without a matching `ncp.tick`** (`"the result does not carry the next
   tick"`). Probe `probe_la_step_ok_without_tick_reads_as_not_executed`: the client steps an
   operation that the owner does not serve as a lockstep operation, which is a plausible
   configuration mismatch. The owner executes it and answers `ok`; the client gets `Error::Usage`
   with `executed() = No`. The Python run of the same case shows that the application's position
   moved to 7.
3. **`take` after an `ok` with a malformed clock** (`"the response of the take does not carry the
   clock"`) [C by reading].

Why it matters: property 7 exists so that a client is never told "not executed" for a request
that ran. A caller that maps errors to verdicts with `executed()`, the purpose of that accessor,
gets a false "did not run". This is the failure that revision 6 was made to remove. Python raises
`ProtocolError`, which has no `executed` attribute: neutral, but it gives no verdict either.

Fix: add an error variant for profile failures after a send (for example
`Error::Protocol { detail, executed }`): `Yes` for a malformed `ok` to a step or a take, `Unknown`
otherwise. Make `recover` return `Ok(Executed::Unknown)` with the client adopted, as in (e). Add a
test that asserts `executed()` of each of these errors.

### N2. "A step that recovery says did not run never runs" is stronger than the profile: documentation (overclaim), low to medium [C]

The model's S1 states that "a step with the verdict 'did not run' never runs, before or after". The
model explores only restarts that keep the latest clock, or that restore the same tick with
another state. Profile rule 5.7 also allows restarts to an older saved clock and restarts with no
clock. Profile section 7 ("Restarts") says honestly that after such a restart, a step that ran
"shows as 'did not run'".

I added both restarts as faults (`model_probe.py fresh_restart`). S1 fails in both shapes:
`S1: 'did not run' for a step that ran`, with the trace "… L sends step → an owner takes a frame →
a time limit → L sends open → the owner restarts without a saved clock → …". The same happens for
"restarts to the clock saved before the last step".

The guide nevertheless says: "A second check does the same for the lockstep profile, with copies
of every frame, restarts, and a second client: a step that recovery says did not run never runs."
The model README's limits do not say that these restarts are excluded. For a step with effects
outside the owner's state, such as an actuator, the difference matters: a resent step acts twice.

Fix: qualify the guide ("… while the owner keeps its latest clock; after a restart to an older
clock, 'did not run' means that the step is not in the owner's state"). Add the exclusion to the
model README's limits and to the profile's evidence bullet. Consider modelling these restarts with
S1 weakened to the current-state meaning. Consider a history identifier in the clock, so that a
restart that loses steps gives no verdict instead of "did not run".

### N3. The `take` helper breaks the MUST of rule 4.1: defect, low [C]

Rule 4.1: the body of a take MUST name "the term that the owner told the client last in this
session". `ncp.lockstep.take` and Rust `take` always start from the `open` report's term.
`probe_41.py`: after a declined step told the session term 2 (rule 6.4), `take(stepper.client)`
sent **term 0**, was declined, and then sent term 2 (`terms named: [0, 0, 2]`). This is harmless,
but it costs a round trip and one of the three attempts of rule 6.2. `LockstepClient` also has no
method to take the ticks again in its session (rule 6.4); the caller must call the module function
and set `tick`, `state`, and `request` by hand.

Fix: track the last term told (from the take's `ok`, a declined take, and a declined step), pass it
to `take`, and add `LockstepClient.take_again()` or its equivalent.

### N4. The profile's requirements are not mapped, and its client MUSTs are untested: tests, low [C]

`conformance/requirements.json` maps the 85 requirement lines of `spec/NCP-2.md` only. No line of
either profile is mapped; `check_ncp2_requirements.py` reads only `spec/NCP-2.md`. Searching both
test suites finds no test for these lockstep client rules:

- 3.4 (no profile without the four members; `"did not enable"`)
- 6.1 (the term of the take's `ok` is the request's term + 1)
- 6.3 (`ncp.tick` names the request's tick and identity; `"does not carry the next tick"`)
- 6.2, a SHOULD (stop after three takes; `"keeps moving"`)

Each search gives 0 hits in `python/tests/test_ncp.py` and `rust/tests/sessions.rs`. The model does
not exercise these checks either: its stepping program takes the response bodies as they are.
Python has no test that a step waits for a checked take (Rust: `a_step_waits_for_a_checked_take`).
Rust has no test that a rejected `open` takes nothing (Python: `test_a_rejected_open_takes_nothing`).

Fix: extend the requirements check to the profiles, add tests with a misbehaving owner for 3.4,
6.1, 6.2, and 6.3, and add the two missing parity tests.

### N5. The model README's time, and the "two faults NOT RUN" gate: documentation, low [C]

- The model README says "With one fault, the search reaches 426,777 worlds in about 12 seconds".
  My run took **85.9 s** wall and 64.8 s user (36.6 + 23.7 + 20.8 + 4.3 s for the four
  configurations); the previous reviewer measured 79.7 s. Command:
  `time python3 -I -B model/lockstep.py --faults 1`.
- The release record says the lockstep model check with two faults is NOT RUN, and the model README
  says that it "passes 3 million worlds". That is the default `--max-worlds` limit. With
  `--max-worlds 12000000`, the two-fault run completes: stream 5,259,265 + 2,106,563 worlds
  (4 min 57 s) and Zenoh 1,641,006 + 255,359 worlds (2 min 20 s). Every property holds in all
  **9,262,193 worlds** (`model-f2-*.log`). This is advisory evidence, not a gate result. The gate
  could run it, or a nightly job could.

### N6. The lockstep profile text: ambiguities and contradictions, low [C by reading]

1. **Plain operations that change the state.** Rule 5.6 protects only the clock. An operation that
   is not a lockstep operation and changes the stepped state (for example "reset" or "teleport")
   leaves S stale, so the state check of rule 5.4 accepts a resent step against a world that it
   did not answer. Add: operations that are not lockstep operations MUST NOT change the state that
   S describes, or the owner updates S after them.
2. **The term.** The definition "the number of takes that ran" disagrees with rule 5.7, where the
   term restarts at 0 or is restored.
3. **Rule 5.8.** The table says that numbers replace "N or E". In the row for rule 5.2 with a bad
   body, both SDKs keep `E` literally (`member: a take needs the body {"term": E}`). State that `E`
   in that row is literal.
4. **"One verdict for each step"** (section 7). The bullet needs "and no other client takes the
   ticks"; the bullet "Several clients" already says that such a recovery gives no verdict.
5. **Saving the clock** (rule 5.7). No text or API says how an application saves a clock that
   "belongs to the application state". The clock changes after `execute` returns, and there is no
   hook after that update. An application can compute (T + 1, S′, R) inside `execute` from the
   request; say so.
6. **Figures and wording.** See N8.

### N7. Handler composition can deadlock every session, and Rust can hide a poisoned clock: API hazard, low [C]

`Lockstep.validate` takes `_lock` (Python) or sets `running` (Rust), and only `execute` releases
it. The `Handler` contract says that `validate` "must not change any state". A handler that wraps
`Lockstep` and declines after `Lockstep.validate` succeeded leaves the lock held. `probe_n7.py`:
an application quota layered over the profile declines the second step, and a take in another
session is still waiting after 2 s. In Rust, `running` stays `Some` and every later take and step
waits on the condition variable [C by reading].

Separately, Rust `Lockstep::clock()` returns `Clock::default()` (tick 0, term 0, no holder) when
the mutex is poisoned, for example after an application panic [C by reading]. Code that saves the
clock for rule 5.7 then saves tick 0 without an error.

Fix: document that `Lockstep` must be the outermost handler, or release the reservation at the end
of the owner's rule 12 whether `execute` ran or not. Return the poisoned clock from `clock()`
(`PoisonError::into_inner`), or return a `Result`.

### N8. Small claims and figures: documentation, very low [C]

- Spec section 7.7, last paragraph: "[`model/`] checks all eight properties against the reference
  SDKs". Only the Python SDK runs there. The model README says so; the Rust owner is checked
  against the Lean oracle on random traces, not in every reachable state.
- Section 13.2: "a signed token in the contract". A contract is a document identified by its
  digest; a token belongs in the messages that the contract defines.
- `formal/README.md`, "What is not proved", does not say that the Lean model has no features. Its
  `app.known` is fixed for each application, so the per-session routing of feature operations in
  rule 7.3.12 is outside the proofs and the oracle traces. This is benign for the proved
  properties, but the list should say it.
- The ladder figure and the guide say "no check before check 11 changes any state" (the guide:
  "before the admission"). Check 3 opens a session.
- The lockstep figure gives "the holder is an opening" as "From revision 6". Profile revision 3
  (specification revision 5) made the holder an opening; revision 6 made `open` take nothing.
- The verdicts figure lists four codes under "rejected, in reply to open". Any rejection of an
  `open` means that no session is open; the recovery case (`seq_stale` to an `open`) appears only
  under "possibly executed".
- `docs/design/NCP-1-SHORTCOMINGS.md` (modified 16:18) counts 6,184 Rust, 4,929 Python, and 553
  specification lines. The snapshot has 6,191, 4,939, and 554: the sources were edited at 16:30
  to 16:35.

## 4. Python and Rust parity (revision 6)

| Aspect | Status |
| --- | --- |
| Detail texts of profile rule 5.8 | Identical in both SDKs (7 texts) [C by reading] |
| `declined` body | Same filter (names starting with `ncp.`). "detail" is serialized first in both (Python by insertion, Rust by sorted keys) [C by reading] |
| Take and report bodies | Member order differs (Python: tick, state, request, term; Rust: sorted). Harmless: member order has no meaning |
| Errors after a send | **Differ**: Python `ProtocolError`; Rust `Error::Usage` with `executed() == No` (N1) |
| Waiting | **Differ**: Rust `open`, `close`, and plain operations wait for an executing step; Python never waits (b) |
| Constructors | Neither bounds the tick at 2^53 − 1 (g); neither checks that `request` is an identity (Python: any `str`; Rust: any `String`) |
| `recover` after "no verdict" | **Differ**: Python keeps the new client with the caller; Rust drops it (e) |
| API surface | Python has a public `report(client)`; Rust has none (`reported_term` is private). Python `step` raises plain `ValueError` for a body with `ncp.tick`, not `UsageError`; Rust returns `Error::Usage` |
| Tests | Python only: a rejected `open` takes nothing. Rust only: a step waits for a checked take (N4) |
| Application panic | Rust poisons the shared mutex: every later request of every session fails (`"lock"`), and `clock()` returns the default (N7). Python releases the lock in `finally` |

## 5. Model check (`model/lockstep.py`)

**Reproduction [C].** One fault: 426,777 worlds, S1 to S6, L1, and progress hold (`model-f1.log`).
Two faults: 9,262,193 worlds, all hold (N5). Self-test: 9 of 9 detected, each by the same property
as in the previous reviewer's run (`model-selftest.log`, 65 s).

**Vacuity [C].** Every property can fire. S1, S2, S5, S6, and L1 catch the shipped mutants. None of
the nine shipped mutants exercises S3, S4, or progress. My own mutants make each of them fire
(`model_probe.py extra`):

- "the tick moves by two" → S3
- "the judge never decides" → S4
- "every take declined" → progress

Add such mutants to the self-test.

**Mutants caught for the wrong reason [C].**

- `constant_nonce` is reported as **L1** only because two byte-identical `open` responses make
  the ghost choose the wrong opening (`max` over `w.opened`). With L1 off, **S2** catches it with
  **zero** faults (`model_probe.py noL1`). The defect is real, but the property reported is an
  artefact. Fix: take L's opening from the owner key that sent the response.
- `verdict_from_open_report` is caught by S6, because no take ran in the opening when the verdict
  was made. That is a correct encoding of rule 6.5. With S6 off, S1 still catches it in 3 of 4
  configurations; in Zenoh with one session identifier, recovery cannot open at all.

**What each guard protects [C].** With L1 off, `take_without_term` and `take_keeps_term` pass
every safety property. The term guards stability (L1), not truth; this is consistent with design
record decision 47, but worth saying in the profile. `verdict_ignores_state` is caught only by S6,
because S1 alone misses it, so S6 is essential and not redundant.

**Not covered.** The README states some of these; the others should be added:

- Restarts to an older clock or with no clock (N2).
- Application failure in a step (rule 5.5).
- `result_too_large`.
- Stop and shutdown, and bad frames: the `Ended`/`NO` branch of `react` is unreachable.
- More than one stepping client: the other client is atomic and steps once.
- The `LockstepClient` class and `take()` with their response checks: the model re-implements the
  stepping program and shares only `judge`. The changelog's and the profile's "the owner and the
  client of the Python SDK" means the session client machine, not the profile's client.
- Concurrency: stated in the README.
- Rust: stated in the README.

## 6. Claims about revision 6

| Claim | Where | Status |
| --- | --- | --- |
| 426,777 worlds with one fault, every property holds | model README, README ("about 430,000") | **True** [C] |
| "in about 12 seconds" | model README | **False**: 86 s (N5) |
| Self-test detects nine known defects | changelog, model README, profile §7, design #49 | **True** [C]; but `constant_nonce` is attributed to L1 by a ghost artefact (§5) |
| "a step that recovery says did not run never runs" | guide | **Overclaim** (N2) |
| "drives the owner and the client of the Python SDK through every reachable state … restarts" | profile §7, changelog | True for the session client and for restarts that keep the clock; the `LockstepClient` is not driven, and some restarts are not explored |
| "With two faults, the search passes 3 million worlds; the gate runs one" | model README | True: the default limit. The run completes with a higher limit (N5) |
| "The Rust SDK … its tests replay the cases that the search found" | model README | Plausible: the Rust tests mirror the Python cases. The exact case list is not recorded [S] |
| Design #45 to #51: checks named for each decision | design record §15 | True [C]: S5/`takeover_in_open`; L1 and the two term mutants (and only L1, see §5); S1/S6 and three verdict mutants; gate lines 61–63; `restored` and the largest term; text |
| Migration §9 tables (Python and Rust API changes) | migration plan | True [C] |
| Migration §8: items 1 and 6 partly done | migration plan | True |
| "Model check of the lockstep profile: PASS with one fault …; two faults NOT RUN" | release record | True for the gate. Advisory two-fault run passes (N5) |
| "one stepping client with two steps, three sessions, and one fault, and only the Python SDK" | KNOWN_LIMITATIONS | True |
| Evidence list in profile §7 | lockstep profile | True in both SDKs (each case has a test) [C] |
| Line counts | shortcomings | Slightly stale (N8) |
| Section 14: profiles have no vectors; the model checks lockstep | spec | True; one new owner vector checks feature operations of the core |

## 7. Known open work (not defects)

Decline reasons that a program can read; a stream profile; an authority profile; Zenoh fault
campaigns and benchmarks; an implementation by another author; the tag decision. Others: no
model check of the rounds profile, and no TypeScript SDK or Rust rounds profile.

## 8. Commands

From a scratch copy `SNAP` of the snapshot:

```text
python3 -I -B python/tests/test_ncp.py                      # 98 tests OK, 4 skipped
python3 -I -B python/tests/test_ncp.py LockstepTests -v     # 19 OK
CARGO_TARGET_DIR=... cargo test --offline --locked --test sessions        # 49 passed
NCP_RUST_EXAMPLES=$TARGET/debug/examples python3 -I -B python/tests/test_ncp.py \
    BindingTests.test_python_lockstep_client_with_the_rust_lockstep_owner  # OK
$ZENV/bin/python -I -B bindings/zenoh/python/tests/test_zenoh.py LockstepRoutingTests RoutingTests  # 8 OK
python3 -I scripts/check_ncp2_requirements.py; python3 -I scripts/check_ncp2_rules.py  # both OK
time python3 -I -B model/lockstep.py --faults 1             # 426,777 worlds, 85.9 s
python3 -I -B model/lockstep.py --faults 2 --shape stream --max-worlds 12000000   # 7,365,828, all hold
python3 -I -B model/lockstep.py --faults 2 --shape zenoh  --max-worlds 12000000   # 1,896,365, all hold
```

Probes: `opus-rev6-probes/` (`README.txt` lists each one with its finding).
