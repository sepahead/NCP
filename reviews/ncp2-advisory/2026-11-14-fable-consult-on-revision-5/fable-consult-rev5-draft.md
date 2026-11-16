# Fable consult, NCP 2 revision 5 — DRAFT (work in progress)

Status: advisory, non-normative, certifies nothing. Read-only review.
Marks: [C] confirmed (read or ran), [S] suspected.

## State at restart (2026-11-14)

- Durable directory was empty at restart; nothing from an earlier attempt survived.
- [C] Worktree `.ncp2-hardening` is at base `df13a28` with revision 5 uncommitted:
  33 files changed, 552 insertions, 88 deletions (`git diff --stat`).
- [C] Changed SDK files: `python/ncp/{contract,lockstep,owner}.py`,
  `rust/src/{contract,lockstep,owner}.rs`, tests `python/tests/test_ncp.py`,
  `rust/tests/sessions.rs`; spec `spec/NCP-2.md`, `spec/NCP-2-LOCKSTEP.md`,
  `spec/ncp2-rules.json`; `scripts/check_ncp2_rules.py`; vectors.
- Coordinator note: both NCP 2 gates passed on revision 5 (not verified by me);
  release build and record generators will run in the worktree next, so all
  code runs only in scratch copies.

## Plan

1. Read rev4 review sections D1, D3, D7, 4.4, 5b, 5c and the rev4 probes.
2. Read the revision-5 diff (SDKs, spec, rules, tests).
3. Q1: copy `python/ spec/ model/ conformance/ bindings/` to a `mktemp -d` scratch;
   rerun rev4 probes with `python3 -I -B`; write new probes for residual paths
   (non-holder steps, false recovery verdicts, byte-stream servers, Zenoh
   workers, restart with restored clock, racing `request`). Rust: read, and run
   if an offline build is possible with a scratch `CARGO_TARGET_DIR`.
4. Q2: design the next profile revision (option (c)): admission rule, term,
   client algorithm, interactions with 7.1.8, 13.2, Zenoh resends; exact text.
5. Q3: lockstep model-check plan after reading `model/simulate.py`.
6. Q4: four figure specs after reading `scripts/gen_diagrams.py` NCP 2 functions.
7. Write `fable-consult-rev5.md`; return summary.

## Findings so far

(none yet — sections are appended below as each one is finished)

## Q1 progress (checkpoint 1)

Scratch: a `mktemp -d` copy of `python/ spec/ model/ conformance/ bindings/zenoh scripts/{check_ncp2_rules,gen_diagrams}.py` from the worktree (revision 5, uncommitted). All runs `python3 -I -B`.

Rev4 probes rerun against the revision-5 Python SDK [C]:

| Probe | Revision 4 | Revision 5 |
| --- | --- | --- |
| `lockstep_replay_safety_check.py` (scenario 1) | delayed s -> ok, tick 2, verdict NO false | delayed s -> `declined body_invalid the opening does not hold the ticks...`, tick 1, position 1; "the verdict NO stayed true" |
| `lockstep_same_session_id.py` (scenario 2) | delayed s -> ok, tick 2 | delayed s -> declined, tick 1, position 1 |
| `lockstep_stale_open.py` (scenario 3, liveness) | B fenced | B still fenced: `declined: the opening does not hold the ticks` (documented in profile section 7 "Copies of open") |
| `schema_vs_profile.py` (D3) | declined `body_invalid` | `step ran`, tick 1 |

Read so far [C]: `python/ncp/lockstep.py`, `python/ncp/owner.py`, `rust/src/lockstep.rs`, `rust/src/owner.rs` (full), diff of spec/profile/rules/check script.

Notes to verify next:
- Python `_open` and Rust `open` draw the nonce before `handler.open`; failure after `handler.open` (encode error; a wrapper that refuses after Lockstep.open) leaves a holder nonce of no opening: liveness only [S].
- Holder safety now rests on assumption A4 (no two openings share a nonce). `Owner(nonce=...)` accepts a fixed source; Rust fallback RNG without /dev/urandom (rev4 D11).
- Rust `Lockstep::validate` sets `running`, mutex released until `execute`; Python holds `_lock` across validate..execute with a thread-local flag.
- Zenoh servers and byte-stream servers still to read.

## Q1 progress (checkpoint 2) — residual R1 CONFIRMED

**R1 [C, probe `probes/zenoh_same_session_first_step.py`]: on the Zenoh binding, a recovery with the SAME session identifier gives a false NO when the uncertain step is the first request of its session.**
The recovery `open` (same identifier, same body) is the same frame as the first `open`. The Zenoh server holds the session (one worker per identifier), so rule 7.3.5 returns the KEPT `open` response: same opening, same nonce, no takeover. Output:

```text
1. s (seq 1) is delayed; the call ended: local.timeout executed: unknown
2. recovery with the same session identifier -> verdict no | same nonce as the first opening: True | same open frame: True | sessions held: 1
3. delayed s arrives -> ok None  | owner tick 1 | position 10
RESULT: the verdict NO was false: s ran
--- control: new session identifier
2. recovery with a new session identifier -> verdict no | same nonce ...: False | sessions held: 2
3. delayed s arrives -> declined body_invalid the opening does not hold the ticks ... | owner tick 0 | position 0
RESULT: the verdict NO stayed true
```

The probe drives the real `ncp_zenoh.Server._on_query` and worker threads; only the Zenoh transport is a stub (`probes/stubs/zenoh`). The Rust server has the same routing (`bindings/zenoh/rust/src/lib.rs` `route`: an existing worker gets the frame; owner rule 5 answers with `kept`) [C by reading, not run].
Contradicts profile revision 3, rule 6.3 last sentence ("This holds also if the new session uses the session identifier of the old one") and the Holder term ("a client that uses the same identifier again on another connection, opens the session again with another nonce"): true on byte streams, false on Zenoh.
With seq > 1 the same `open` gets `seq_stale` (rejected), so no verdict: the hole is exactly "first request uncertain".
Fix now: `recover` MUST refuse a client whose opening has the nonce of the old session (compare nonces; binding-independent), and the profile must require a new session identifier (core rule 7.1.1) instead of claiming that reuse is safe. Option (c) closes it structurally: `take` and the delayed step compete for seq 1 of the same opening.

## Q1 progress (checkpoint 3) — R2..R5 CONFIRMED (probe `probes/lockstep_residuals.py`)

Note: revision 5 was committed in the worktree as `7edc3f9` while I worked; my scratch copy is byte-equal to it for `python/ncp`, `spec`, `model`, both Zenoh bindings (checked with `diff -rq`).

```text
R2. recover() with a client that was opened BEFORE the uncertain step was sent
   recover(standby) -> verdict no | holder is the standby opening: False
   delayed s -> ok None  | tick 1 => the verdict NO was FALSE
R3. a nonce source that repeats (assumption A4 broken): scenario 1 of D1 again
   recovery -> verdict no ; replayed open on C3 -> ok ; delayed s on C1 -> ok | tick 1 => the verdict NO was FALSE
R4. the owner restarts with tick T and ANOTHER state; recover() compares only the tick
   s (tick 2) uncertain | the client knows tick 1 state p1
   recover -> verdict no | the client now holds state p500 (no error raised)
R5. an open that takes the ticks and then opens no session (a wrapper refuses after Lockstep.open)
   second open -> rejected refused | holder is still the live opening: False
   live client's next step -> declined ... | a REJECTED open took the ticks
```

- R2 [C]: `recover(client)` accepts an already-open client (`if not client.opened: client.open()` in both SDKs). Its `enabled` tick was read before the step; the stepping opening took the ticks after it. False NO. API hazard; fix: `recover` must send the `open` itself (refuse an open client), or (c).
- R3 [C]: the fix rests on assumption A4 (nonce uniqueness). `Owner(nonce=...)` accepts any source. A model check must use a counter, not a constant. Profile section 7 should name A4.
- R4 [C]: rule 6.3 and `recover` test only the tick for NO. A restart to the same tick with another state gives NO and silently adopts the other state. Documented as "current state" semantics, but the client can detect it: compare the state digest (and R) that it knew at tick T.
- R5 [C]: an `open` that is then rejected can take the ticks (wrapper order; also an encode failure after `handler.open` in both SDKs [S]). Liveness only. Contradicts 7.1.4 "After a rejection, the owner stays without a session" in spirit and property 6 "rejected changes nothing" for profile state.
- Rust: tests `a_copy_of_an_old_open_does_not_give_the_ticks_back` and `a_recovery_with_the_same_session_identifier_fences_the_old_opening` cover scenarios 1 and 2 in byte-stream shape only [C read]; R1 (Zenoh shape) is covered in neither SDK.

## Q1 progress (checkpoint 4) — Rust

- [C ran] `cargo test --offline --locked --release --test sessions -- lockstep ticks opening ...` in a scratch copy of `rust/` with a scratch target directory: 8 passed, 0 failed (log: `rust_lockstep.log`). Includes both new revision-5 tests.
- [C ran] `probes/probe_rev5.rs` (placed in the scratch crate's `tests/`): 
  - `R1 rust: verdict No; same nonce as the first opening: true` then `delayed s -> "ok" | owner tick 1`. One `Owner` for a session identifier (as `bindings/zenoh/rust/src/lib.rs` keeps it) answers the recovery `open` with its kept response. The Rust Zenoh server itself was not run (needs Zenoh); its `route` was read.
  - `R2 rust: verdict No; delayed s -> "ok" | owner tick 1`.

## Q2 design decisions (checkpoint 5; full text follows in the final report)

- Admission: option (i). Core rule: a *feature operation* `F.N` (F starts with `ncp.`, N has no `.`) belongs to feature F = the name before the last `.`; rule 7.3.12 executes it only when the owner enabled F for the session, with the profile in the place of the application and no contract schema; otherwise `declined unknown_op` — the same answer that every owner of revision 5 gives today, so the change is permissive only. New section 15 rule 3; one bullet in 7.3.12; one sentence in 7.1.8 (profiles MUST NOT change state that outlives the session when `open` is accepted).
  - (ii) rejected: every adopter's contract identity changes; the name cannot start with `ncp.` (11.1), so tools cannot recognise it; lockstep operations are already owner configuration, not contract content.
  - (iii) considered and rejected: take riding on the first step (a `declined` step would have changed the holder); implicit takeover on the first admitted request (`ncp.ping` returns `{}`, so no final values); a generic `ncp.feature` operation (same as (i) with the name in the body).
- Term: owner-issued counter E, 0..2^53-1, +1 at each successful take; `take` is compare-and-swap on it. Safety does NOT need the term (take is admitted in one opening, at most once); the term gives stability: a delayed take of an abandoned opening cannot remove a newer holder. No restore needed for safety (no opening survives a restart); MAY restore with T,S,R; the holder is never restored.
- `open` with the feature: reports `{tick,state,request,term}` from one instant; changes nothing; conforms to 7.1.8; monitors can read the clock without fencing the stepper.
- `ncp.lockstep.take` body `{"term": E}`; waits for a running step; term mismatch -> `declined body_invalid` (+ current term in the body); else holder := this opening, term := E+1, `ok {tick,state,request,term}` final.
- Client: start = open + take (2 RT), base tick/state from the take response; recovery = new session (new identifier) + take, verdict ONLY from the take response (tick u & R = id -> ran; tick u-1 & same state digest -> never; else possibly); lost take response -> open again + take, no verdict needed for a take; declined take -> retry (same session with the reported term, or a new session), at most 3 times.
- Zenoh R1 closes structurally: steps have seq >= 2, so a same-identifier `open` gets `seq_stale` once the take was admitted; if the take itself (seq 1) is uncertain, the retried take is the same frame.
- Lean: no proof change; `known` already abstracts "served in this session" (optionally move it into `Behavior`). Rules data: revision 6 only, no new code. Vectors: negative owner vectors (`ncp.lockstep.take`, `ncp.x`, `ncp.ping.x` without the feature -> `declined unknown_op`).

## Checkpoint 6 — prototype of option (c) validated in scratch

`prototype/option-c.diff` (140 lines against revision 5: `owner.py` 12 lines, `lockstep.py` the rest). Not a patch for the repository; it is evidence that the design below is implementable and what it changes.

All probes against the prototype [C ran]:

| Probe | Revision 5 | Prototype of (c) |
| --- | --- | --- |
| scenario 1, scenario 2 | verdict true | verdict true |
| scenario 3 (replayed old `open`) | live client fenced | `B stepped`, tick 3: nothing taken |
| R1 Zenoh, same identifier | FALSE NO | recovery `open` -> `Rejected: seq_stale` (take was seq 1, step seq 2): no verdict, no false one |
| R2 pre-opened client | FALSE NO | verdict no, standby holds, delayed s declined: true |
| R3 repeating nonce | FALSE NO | delayed s declined (a copy of `open` takes nothing; its response differs by the term) |
| R4 other state at the same tick | NO, adopts `p500` | `ProtocolError`: no verdict (state digest compared) |
| C1 monitor | n/a (would fence) | reads `{tick,state,request,term}`, live client keeps stepping |
| C2 replayed `open` + replayed `take` | n/a | `open` ok, holder unchanged; `take` -> `rejected ack_mismatch` |
| C3 delayed take after a newer take | n/a | `declined body_invalid {'ncp.lockstep': {'term': 2}, 'detail': 'term: the term is 2'}`, holder unchanged |
| C4 delayed take before a newer take | n/a | succeeds once; the live client's take is declined once, then ok (term 4) |
| C5 `ncp.lockstep.take` without the feature; `ncp.other.thing` | `declined unknown_op` | `declined unknown_op` |

SDK tests against the prototype: 87 run, 84 pass or skip as before, 3 fail, all three assert the takeover in `open` (`test_a_takeover_waits_for_a_checked_step_and_reads_its_tick`, `test_a_copy_of_an_old_open_does_not_give_the_ticks_back`, one more LockstepTests case).

## Checkpoint 7 — a prototype lockstep checker exists and works (Q3)

`checker/lockstep_check.py` (scratch prototype, about 330 lines, same structure as `model/simulate.py`): real `ncp.owner.step` + real `ncp.Lockstep` handler (clock copied in and out of the world), pure `ncp.client` machine, verdict from the real `LockstepClient.recover`. One stepping client (open, [take,] step, step; at most 3 sessions), shapes `stream` (one owner per connection; a copy arrives on a new connection) and `zenoh` (one owner per session identifier), free delay/reorder/time limit, faults: copy of any sent frame, loss, expiry (zenoh), restart with the clock kept, another client that takes the ticks and steps once.

Measured [C ran, `python3 -I -B`]:

| Run | Worlds | Result |
| --- | --- | --- |
| revision 5 SDK (profile 3), 0 faults, S1-S4 | 2,148 | hold |
| revision 5 SDK, 1 fault, S1-S4 (no L1) | 45,881 | hold |
| revision 5 SDK, 1 fault, with L1 | - | L1 violated: `open -> owner -> L takes a response -> a copy of a frame` (the documented liveness loss) |
| revision 5 SDK, zenoh, same session identifier, 0 faults | - | S1 violated: `L sends open -> owner -> L takes a response -> L sends step -> time limit -> L sends open -> owner -> owner` = finding R1, found by search |
| prototype of (c) (profile 4), 0 faults | 9,662 | S1-S4, L1, progress hold |
| prototype of (c), 1 fault, new identifiers | 283,846 | hold |
| prototype of (c), 1 fault, same identifier | 126,523 | hold |
| self-test profile 4, 1 fault | 6 of 6 | holder_by_session (S2, needs the same-identifier variant), constant_nonce (L1), takeover_in_open (L1), take_without_term (L1), verdict_from_open_report (S1), verdict_ignores_request (S1) |
| self-test profile 3, 1 fault | 3 of 3 | holder_by_session (S2), constant_nonce (S2), verdict_ignores_request (S1) |

Two faults: running (one step). Reference: `model/simulate.py` has 51,205 worlds per 4-call script at 1 fault on the message network and 2,591,544 in total at 2 faults.

## Checkpoint 8 — Q3 SECTION (final text)

### Q3. A model check of the lockstep profile

**Verdict.** Adopt it as `model/lockstep.py`, built on the structure of `model/simulate.py`. A working prototype is in `checker/lockstep_check.py` of this directory. It found R1 by search, it shows the liveness loss of profile revision 3 as a violated property, it passes on the prototype of option (c), and it detects six of six mutants.

**Measured** (prototype of (c), `python3 -I -B`, idle machine, [C ran]):

| Run | Worlds | Time | Memory |
| --- | --- | --- | --- |
| 1 fault, both shapes, 2 steps | 283,846 | 8.3 s | small |
| 1 fault, both shapes, 2 steps, same session identifier | 126,523 | 3.8 s | small |
| self-test, 6 mutants, 1 fault | 6 of 6 | 8.9 s | small |
| 2 faults, zenoh shape, 1 step | 656,101 | 216 s on a loaded machine | - |
| 2 faults, zenoh shape, 2 steps | 1,388,036 | 53 s | 1.1 GB |
| 2 faults, stream shape, 1 step | 2,357,682 | 68 s | 1.9 GB |
| 2 faults, stream shape, 2 steps | (running; estimate 5 million, 150 s, 4 GB) | | |
| revision 5 SDK (profile 3), 1 fault, S1 to S4 | 45,881 | 1.4 s | small |

Reference, same machine and session: `model/simulate.py --faults 2` gave 2,591,544 worlds and 12 of 12 mutants (logs `model_f2.log`, `model_selftest.log`).
Every property held in every run of the prototype of (c). About 0.8 KB of memory for each world.

**Actors.**

- L, one stepping client: `open`, `take`, then N steps (N = 2). After a step that is possibly executed, a declined step, a declined take, or a failed `open`, L opens the next session; at most 3 sessions. Two variants: a new session identifier for each session, and the same identifier for all.
- The owner side: one clock (tick, state, request, holder, term, and the application's position) and one owner state for each connection (shape `stream`) or each session identifier (shape `zenoh`).
- The network: a bag of frames in flight. Delay, reordering, and the client's time limit are free; they are not faults.
- B, a second stepping client, as one compound fault: it opens, takes, and steps once.

**Faults** (budget 1 for the quick gate, 2 for the full gate, as `simulate.py`): a copy of any frame that L sent (zenoh: to the service; stream: on a new connection, or on an earlier copy's connection); loss of a request or a response; expiry of one session (zenoh); a restart of the owner that keeps its clock and loses the holder; B.

**State.** `World(clock, owners, to_owner, to_client, cl, sent, openings, opened, holder, executed, verdicts, faults, timed, replays, others)`, a frozen dataclass, used directly as the key. `cl` is L's program state: phase, session index, `ClientState`, base tick and state, logical step, the uncertain step, the term, the attempts, and two ghosts (holds, opening).

**Properties.**

| | Property | Catches |
| --- | --- | --- |
| S1 truthful | A step with the verdict "not executed" never executes, then or later. "Executed" is true. An `ok` belongs to an executed step. | holder by session name; verdict from the `open` report; verdict that ignores R |
| S2 holder | A step executes only in the opening that took the ticks last. | holder by session name; repeated nonce |
| S3 ticks | The executed steps produce the ticks 1, 2, 3, and so on, once each. | a skipped tick check |
| S4 one verdict | With one stepping client and a kept clock, each recovery that completes gives a verdict. | a state comparison that is too strict; a lost R |
| S5 open reads | Accepting `open` changes no clock member (add this; it is one comparison). | takeover in `open` |
| L1 stable | While the owner still holds L's current opening and L accepted its take, no other frame takes the ticks. This is liveness under replay in a form that a bounded search can check. | takeover in `open`; take without a term check; repeated nonce |
| progress | Without faults and time limits, L finishes its script. | a decline that is not kept; a client that never takes |

**Mutants that the self-test must detect** (the prototype has the first six):

1. `holder_by_session`: the handler sees the session identifier as the nonce (revision 4 of the SDKs). Needs the same-identifier variant under profile 4.
2. `constant_nonce`.
3. `takeover_in_open`: profile revision 3.
4. `take_without_term`: the take always succeeds.
5. `verdict_from_open_report`: the client decides from the `open` response.
6. `verdict_ignores_request`: "executed" when the tick matches and R does not. Needs fault B.
7. Add `step_skips_holder_check` (S2), `take_keeps_term` (the term does not rise; L1), and `recovery_skips_state_check` with a restart to another state (S1), once the restart fault has that variant.

**What to keep from `checker/lockstep_check.py`.**

- Keep: the world and client encoding; `owner_step` with the clock copied into the real `ncp.Lockstep` before each `ncp.owner.step` and read back after it, with its cache; both shapes; the fault set; S1 to S4, L1, and progress; the mutant table and the self-test over both identifier variants; the `--max-worlds` guard; the trace in each violation.
- Change before it enters the repository:
  1. Remove `--profile 3` and `--no-l1`; revision 3 stays only as the mutant `takeover_in_open`.
  2. `recovered()` builds a `LockstepClient` shell to reach the real verdict code, and `react()` restates L's program (when to take, when to try again). Move both into the SDK as pure functions, as `ncp.client` did for the core: `lockstep.verdict(uncertain, known_state, clock)` and a small client machine. Then the checker restates no rule, and the Rust SDK can mirror the same functions.
  3. Carry the opening as a ghost tag on each response in flight. The prototype finds L's opening by the identity of the `open` response, which is ambiguous under the `constant_nonce` mutant (it is caught, but by L1 with a misleading text).
  4. Add S5, the three mutants above, and a restart variant that restores an older clock.
  5. Import `Violation`, `require`, `add`, `without`, and `distinct` from `simulate.py`, or copy them; keep the file standalone like `simulate.py`.
  6. Put the run in `scripts/check_ncp2.sh` after `simulate.py`: 1 fault and the self-test in the quick gate (under 25 s), 2 faults in the full gate (estimate 5 to 6 minutes for both shapes and both identifier variants, 4 GB).
- Not covered, by construction: each owner step is atomic, so the wait of a take for a running step (profile rule 5.2) is outside the search. The threaded SDK tests keep that (`test_a_takeover_waits_for_a_checked_step_and_reads_its_tick`, adapted to `take`). The Rust `Lockstep` is not driven; give it the mutant traces as tests.

**Reuse `simulate.py`'s structure?** Yes: the same BFS, world dataclass, `Machines` with one injected defect, caches, and self-test. Do not merge the files: the lockstep check has several openings, a shared clock, and a client program above the core client, and its budget and scripts differ.

## Checkpoint 9 — Q2 SECTION (final text)

### Q2. Lockstep profile revision 4 and the core rule that admits it

All of this ran as a prototype (`prototype/option-c.diff`, probes C1 to C5, and the checker of Q3). Text in the boxes below is proposed normative text, written to be adapted directly.

#### Q2.1 Decision: how the core admits the take

**Option (i), a core rule for feature operations.** Reasons:

- The answer for an owner that does not serve the profile is `declined` with `unknown_op`, which every owner of revision 5 gives today for `ncp.lockstep.take` [C, probe C5]. The rule only permits; it changes no existing answer. No new code, no new outcome.
- No contract changes. With option (ii), each adopter's contract identity changes, the name cannot start with `ncp.` (section 11, rule 1), tools cannot recognise a takeover in a transcript, and the application author owns a rule that is not theirs. The lockstep operations are already owner configuration (`Lockstep(handler, ["step"])`), not contract content.
- From the core's view, the profile is the application for that operation: rule 7.3.12 applies unchanged (decline, fail, result, kept response). The Lean model needs no new case.
- The authority profile needs the same hook (`ncp.authority.acquire`), and rounds can use it for a join.

Considered and rejected as option (iii): a take that rides on the first step (a `declined` step would have changed the holder, against section 7.4); an implicit takeover at the first admitted request (`ncp.ping` must answer `{}`, so it cannot return the final clock); one generic operation `ncp.feature` with the name in the body (the same rule, harder to read in a transcript).

#### Q2.2 Core text (NCP 2 revision 6)

**Section 7.1, rule 8.** Replace the rule with:

> 8. An opening is not at most once: a delayed copy of `open` can open the session again after the owner lost it (rule 7.6.4), and on the byte-stream binding a copy of `open` on another connection opens a session there. What an owner does when it accepts `open` must therefore be safe to repeat. A profile MUST NOT let the acceptance of `open` change state that outlives the session, and an application SHOULD NOT. Such a change belongs in a request other than `open`, for example a feature operation (section 15, rule 3): an owner admits that request at most once, and only in the opening whose `open` response the request acknowledges (section 7.7, property 1).

**Section 7.3, rule 12.** Insert one bullet after the `ncp.ping` bullet, and extend the next one:

> - For a feature operation (section 15, rule 3) of a feature that the owner enabled for this session, apply the rest of this rule with the profile that defines the feature in the place of the application. The contract and its schemas (section 11) do not apply to the request.
> - If the contract has no such operation, respond `declined` with `unknown_op`. This includes every other operation whose name starts with `ncp.`.

**Section 15.** Add rule 3:

> 3. Feature operations. An operation name `F.N` is a feature operation of the feature `F` if `F` starts with `ncp.` and `N` contains no `.`. The feature of such an operation is therefore its name before the last `.`. `ncp.ping` is not a feature operation. The profile that defines the feature defines the operation, its body, and its result. An owner executes a feature operation only in a session for which it enabled the feature (rule 7.3.12). In every other session, the operation gets `declined` with `unknown_op`, as an operation that the contract does not have. A contract cannot name a feature operation (section 11, rule 1).

**Section 17**, row Lockstep: "Each step names the tick that it advances to and the state that it answers. One opening holds the ticks; a client takes them with a request and learns from the response whether its last step ran."

**Other sources.**

| Source | Change |
| --- | --- |
| `spec/ncp2-rules.json` | `"revision": 6`. No code changes: `unknown_op` and `body_invalid` cover every answer. |
| Both SDKs, `_call` / `call` | Before the contract lookup: `feature = op up to the last "."`; if it starts with `ncp.` and is in the session's enabled features, skip the contract lookup and the schema check and call the handler. 8 lines in Python (see the prototype). Also let a handler add members whose names start with `ncp.` to the body of a `declined` response: Python `Declined(detail, body=...)` exists and the owner drops the body today; Rust needs a variant, for example `Invalid::DeclinedWith(String, Map)`. |
| `formal/NCP2/Model.lean` | No structural change and no proof change. `App.known` already means "the operations that rule 7.3.12 serves"; say in its comment that this covers the contract and the feature operations of the enabled features. Optional and more general: move `known` into `Behavior`, so that it can differ for each opening. The oracle needs no new input: a feature operation without its feature is `unknown`, and with it is `step`. |
| `conformance/generate.py` | Owner scenario steps, in a session without the feature: `ncp.lockstep.take` with `{"term": 0}`, `ncp.nosuch`, and `ncp.ping.x`, each `["declined", "unknown_op"]`, and one `repeat` of the first. The positive path has no vector while profiles have none (section 14); the SDK tests and the model check cover it. |
| `conformance/requirements.json` | The new MUST of 7.1.8 (profiles): reference the lockstep check's property S5. The new sentence of 7.3.12: the vectors above and one SDK test in each language. |
| `model/simulate.py` | Optional: add `("ncp.lockstep.take", {"term": 0})` with `declined unknown_op` to the script `operations`. It raises that script's world count. |

#### Q2.3 The term

- **Who issues it.** The owner. It is part of the clock, next to the tick, the state digest, and R. A client never invents a term; it copies the last one that the owner told it.
- **Range.** An integer from 0 to 9,007,199,254,740,991 (the limit `max_integer`). It rises by exactly 1 at each take that runs, and never at another time.
- **What it is for.** Safety does not need it: an owner admits a take at most once and only in the opening that the take acknowledges, so no copy takes anything. The term gives stability. The take is a compare-and-swap on the term, so a take that was made before another take ran is declined when it arrives late [C, probe C3; mutant `take_without_term` breaks L1].
- **On "term moved".** The response is `declined`, `body_invalid`, with the body `{"detail": "term: the term is 8", "ncp.lockstep": {"term": 8}}`. The client sends the take again in the same session with that term, or opens a new session. It stops after 3 takes without an `ok` and reports that another client takes the ticks.
- **Restart.** No opening survives a restart (rule 7.1.5), so no take or step of an earlier opening can be admitted afterwards, and a take names a term that its own opening reported. The properties therefore hold with any term after a restart. The owner MAY restore the term together with T, S, and R; otherwise it starts at 0. The holder is never restored. A client MUST NOT assume that terms rise across a restart.

#### Q2.4 The profile text (revision 4, sections 1 to 8)

> ## 1. Purpose
>
> A simulation step changes state that outlives the session: the world advances by one tick for each step.
> NCP 2 tells a client whether its last request executed. But if a session ends with its last step possibly executed, for example because the connection broke or a time limit passed, the session cannot tell the client whether the world advanced.
> This profile numbers the steps of the owner's state with ticks that outlive sessions. One opening at a time holds the ticks, and only it can step. A client takes the ticks with a request inside its opening. The response gives the final tick and the request that produced it. A client that lost a session therefore learns from a new session whether its last step ran, and no copy of the old step can run afterwards. An `open` only reports the tick. It takes nothing, so a copy of an `open` changes nothing.
>
> ## 2. Terms
>
> | Term | Meaning |
> | --- | --- |
> | Tick | The number of lockstep steps that the owner's state has applied. The owner names the tick of its state when it starts, 0 by default. |
> | State digest | A string of 1 to 128 characters that the application derives from its state after each step, or `null`. Equal states give equal digests. |
> | Lockstep operation | An operation of the contract that the owner serves under this profile. |
> | Clock | The owner's tick T, its state digest S, the identity R of the request whose step produced T, or `null`, and its term E. The owner keeps one clock for its state, across all sessions. |
> | Holder | The opening (specification, section 2) that can step the owner's state: the opening whose take ran last (rule 5.3). At most one opening is the holder. No opening is the holder when the owner starts. A session identifier does not name one opening (specification, rule 7.1.8). |
> | Term | The number of takes that ran: an integer from 0 to 9,007,199,254,740,991. |
> | Take | The feature operation `ncp.lockstep.take` (specification, section 15, rule 3). |
>
> ## 3. Feature
>
> 1. A client asks for the profile with the feature `ncp.lockstep` and an empty object as its parameters in its `open` request (specification, section 7.1). An owner ignores members of these parameters.
> 2. An owner that serves the profile enables the feature with the parameters `{"tick": T, "state": S, "request": R, "term": E}`: its clock at one instant between two steps (rule 5.1).
> 3. **`open` reads.** Accepting an `open` MUST NOT change the clock or the holder (specification, rule 7.1.8). The clock in an `open` response is a report. It is not final: a step of the holder can run after it.
> 4. A client MUST NOT send a take or a lockstep step in a session whose `open` response does not enable the feature with these four members. Parameters without `term` come from an owner of an earlier revision of this profile; the client then ends the session.
>
> ## 4. Requests
>
> 1. The body of a take MUST be an object with exactly the member `term`: the term that the owner told the client last in this session, in the `open` response or in a later response.
> 2. The body of a request of a lockstep operation MUST be an object with the member `ncp.tick`: an object with exactly the members `tick`, the tick that the step advances to, and `state`, the state digest that the step answers.
> 3. A client sets `tick` to the tick of the last clock that it accepted in this session plus 1, and `state` to the state digest of that clock. That clock is the body of the `ok` response to its take, or `ncp.tick` in the `ok` response to its last step after that. It is never the clock of the `open` response.
>
> ## 5. Owner rules
>
> The owner keeps one clock and one holder for its state, across all sessions.
>
> 1. **One at a time.** From the check of a take (rule 2) or of a lockstep step (rule 4) to the end of its execution, the owner MUST NOT check or execute another take or lockstep step of any session, and MUST NOT read the clock for an `open` response. A take therefore waits for a step that is running.
> 2. **Take, check.** The owner declines a take with `body_invalid` (specification, section 7.3, rule 12) if its body is not as rule 4.1 says, or if `term` is not the owner's term. Nothing changes. After a wrong term, the body of the response MUST have the member `ncp.lockstep` with the value `{"term": E}`, the owner's term. An owner whose term is 9,007,199,254,740,991 declines every take.
> 3. **Take, execution.** Otherwise the opening of the request's session becomes the holder, and the owner raises its term by 1. The body of the `ok` response is `{"tick": T, "state": S, "request": R, "term": E}`: the clock after the take. This clock is final for every other opening: rule 4 declines each of their steps until one of them takes the ticks. The owner MUST identify the holder by its opening, for example by its nonce, and MUST NOT identify it by the session identifier.
> 4. **Step, check.** The owner declines a request of a lockstep operation with `body_invalid` if the body has no `ncp.tick` member as rule 4.2 defines it, if the opening of the request's session is not the holder, if `tick` is not the owner's tick plus 1, or if `state` is not the owner's state digest. The request never executes. If the opening is not the holder, the body of the response MUST have the member `ncp.lockstep` with the value `{"term": E}`.
> 5. **Step, execution.** Otherwise the owner executes the step. The step counts as executed when the owner starts to execute it, also if the application then fails (specification, section 7.3, rule 12). The owner then sets its tick to `tick`, its state digest to the application's digest of the new state, or `null` if the application cannot give one, and R to the identity of the request. The term does not change. The body of the `ok` response is an object: the application's result, with the member `ncp.tick` set to `{"tick": T, "state": S, "request": R}`.
> 6. Other operations do not change the clock or the holder.
> 7. **Restart.** An owner that restarts holds no session (specification, rule 7.1.5), and no opening is the holder. It MAY restore its clock. It MUST then restore T, S, and R from one saved clock that belongs to the application state that it restored. It MAY restore E with them; otherwise its term is 0. An owner that restores no clock starts at its initial tick, with R `null`.
> 8. **Details.** The member `detail` of a `declined` response SHOULD be one of these texts, with the number in place of N or E:
>
>    | Check | `detail` |
>    | --- | --- |
>    | Rule 2, body | `member: a take needs the body {"term": E}` |
>    | Rule 2, term | `term: the term is E` |
>    | Rule 4, body | `member: a lockstep step needs "ncp.tick": {"tick": T, "state": S}` |
>    | Rule 4, holder | `holder: this opening does not hold the ticks; send ncp.lockstep.take` |
>    | Rule 4, tick | `tick: the next tick is N` |
>    | Rule 4, state | `state: the step answers another state` |
>
>    A client MUST NOT act on `detail`. It acts on the outcome and on the member `ncp.lockstep`.
>
> ## 6. Client rules
>
> 1. **Start.** A client that steps sends a take with the term of the `open` response, before its first step. After the `ok` response, its opening is the holder, and the body is the owner's clock. The client MUST check that `term` in the body is the term of its request plus 1. A client that only reads the clock, for example a monitor, sends no take.
> 2. **A declined take.** A `declined` response to a take whose body has `ncp.lockstep` means that another take ran after the owner told the client the term. The client MAY send a take again in the same session, with the term of that body. It SHOULD stop after 3 takes without an `ok` response, and report that another client takes the ticks.
> 3. After an `ok` response to a step, the client MUST check that `ncp.tick` names the tick of its request and the identity of its request. The client then knows the owner's tick and state digest.
> 4. After a `declined` response to a step, the step did not run, and it never will. If the body has `ncp.lockstep`, another opening took the ticks. The client MAY take them again (rules 1 and 2). It can then send the step again, as a new request, if the clock of the take is the clock that the step answered.
> 5. **Recovery.** If a step is possibly executed (specification, section 7.7, property 7), the client opens a new session with the feature and a new session identifier (specification, rule 7.1.1), and sends a take there (rule 1). It MUST send that take after the step became possibly executed. The client reaches its verdict from the body of the `ok` response to that take, and from no other response:
>    - If the body names the tick of the step and, as `request`, the identity of its request, the step ran.
>    - If the body names the tick of the step minus 1 and, as `state`, the state digest that the step answered, the step did not run, and it never will. The client can send it again in the new session.
>    - Any other body means that the owner's state changed in another way, for example by the step of another client or by a restart. The client MUST then treat the step as possibly executed.
> 6. **A take without a response.** If a take is possibly executed, the client opens a new session and sends a take there. It needs no verdict for the old take: the new take makes the new opening the holder in both cases, and rule 5.2 declines the old take if it arrives later.
>
> ## 7. Properties and limits
>
> These properties hold under the assumptions A1 to A4 of the specification (section 7.7).
>
> - **One verdict for each step.** If the owner keeps its clock while the client recovers, recovery turns every step that is possibly executed into a step that ran or a step that did not run and never will. The take of the recovery runs after every step that the owner checked before it (rule 5.1). After it, the old opening is not the holder, and it cannot become the holder again: only a take in the old opening could do that, and the client sent its last request there.
> - **One stepping opening.** Only the holder can step.
> - **`open` takes nothing.** A copy of an `open`, also a delayed or a replayed one, opens a session and reads the clock. It changes nothing outside its session. A monitor reads the clock without an effect on the stepping client.
> - **A take belongs to one opening.** A take acknowledges the `open` response of its opening, which holds a fresh nonce. An owner admits it at most once, and only in that opening (specification, section 7.7, property 1). A party that can only deliver copies of frames cannot take the ticks, also when frames are authenticated (specification, section 13.2). A party that can make frames can: use a key, or a binding that admits only the two endpoints (assumption A2).
> - **A stable holder.** After a take ran, every take that a client made before it names an earlier term, and rule 5.2 declines it. A take of an abandoned session can still run if it arrives before the next take. That next take is then declined once, and succeeds with the term of the response.
> - **Cost.** One more round trip for each session that steps: `open`, take, then the steps. A recovery has its verdict after two round trips.
> - **Several clients.** Clients that step the same owner take the ticks from each other, and a recovery that finds another client's step gives no verdict. The term shows each takeover. Use one stepping client, or the [rounds profile](../../../spec/NCP-2-ROUNDS.md).
> - **Failures.** A step whose application fails counts as executed (rule 5.5), because the application can have changed its state before it failed. Recovery then says that the step ran; the state digest says what the state is.
> - **Restarts.** The verdict describes the owner's current state. A step that ran before a restart to an older clock shows as "did not run", because its effect is not in the current state. If a step has effects outside the owner's state, such as the motion of an actuator, this verdict does not say whether those effects happened. A restart to the same tick with another state gives no verdict (rule 6.5).
> - **What a copy still costs.** A copy of `open` uses one session of the owner until that session ends or expires. A party that can stop frames can stop the stepping.
> - **Evidence.** Both SDKs test this profile. An exhaustive bounded check drives the Python SDK with one stepping client, copies of every frame, loss, expiry, a restart, and a second client (`model/lockstep.py`). The profile is not proved.
>
> ## 8. Example
>
> ```text
> open request body:   {"application": "world", "contract": "…", "bound": 1048576,
>                       "features": {"ncp.lockstep": {}}}
> open response body:  {"bound": 1048576, "application": "world", "contract": "…",
>                       "implementation": "…", "nonce": "…",
>                       "features": {"ncp.lockstep": {"tick": 41, "state": "9f2c",
>                                                     "request": "5d0e…", "term": 7}}}
> take request:        op "ncp.lockstep.take", body {"term": 7}
> take response body:  {"tick": 41, "state": "9f2c", "request": "5d0e…", "term": 8}
> step request body:   {"dt_ms": 10, "ncp.tick": {"tick": 42, "state": "9f2c"}}
> step response body:  {"observation": [0.1, 0.2],
>                       "ncp.tick": {"tick": 42, "state": "77ab", "request": "a71b…"}}
> ```
>
> Here `a71b…` is the identity of the step request. If the step response is lost, the client opens a new session and sends a take with the term of its `open` response, 8. The body `{"tick": 42, "state": "77ab", "request": "a71b…", "term": 9}` says that the step ran. The body `{"tick": 41, "state": "9f2c", "request": "5d0e…", "term": 9}` says that it did not run and never will.
> A take with the old term 7 gets `declined` with `body_invalid` and the body `{"detail": "term: the term is 9", "ncp.lockstep": {"term": 9}}`.

Section 9.1 of the profile, "Revision 4", then says: the takeover moved from `open` to the take; the term; the state digest in the verdict "did not run"; a new session identifier in recovery; and that revision 3 lost liveness under a copy of `open` and, on the Zenoh binding with a reused session identifier, the verdict (finding R1).

#### Q2.5 The client algorithm

```text
start(session):                                   round trips
    r = open(features = {"ncp.lockstep": {}})     1
    c = r.features["ncp.lockstep"]; require integer c.term
    clock = take(session, c.term)                 1   (+1 for each "term moved")
    tick, state = clock.tick, clock.state         never from the open response

take(session, term):
    3 times at most:
        send ncp.lockstep.take {"term": term}
        ok:        require body.term == term + 1; return body
        declined:  if body["ncp.lockstep"].term is an integer: term = it; next try
                   otherwise fail: a defect of the client
        possibly executed, or ended:
                   session = a new session; term = the term of its open response; next try
    fail: "another client takes the ticks"

step(op, body):                                   1
    send op with body + {"ncp.tick": {"tick": tick + 1, "state": state}}
    ok:        check ncp.tick.tick == tick + 1 and ncp.tick.request == identity of the request
               tick, state = ncp.tick.tick, ncp.tick.state
    declined:  the step never runs. If body["ncp.lockstep"].term is an integer:
                   clock = take(session, that term)
                   if (clock.tick, clock.state) == (tick, state): the caller can send the step again
                   else: tick, state = clock.tick, clock.state; report that the clock moved
    possibly executed:
               recover(u = tick + 1, identity, answered = state)

recover(u, identity, answered):                   2 to the verdict, 3 to the repeated step
    session = a new session with a new identifier
    clock = start(session)                        the take is sent after the step ended
    if clock.tick == u and clock.request == identity:        verdict "ran"
    elif clock.tick == u - 1 and clock.state == answered:    verdict "did not run, never will"
    else:                                                    verdict "possibly executed"
    tick, state = clock.tick, clock.state
```

| Case | Revision 3 of the profile | Revision 4 |
| --- | --- | --- |
| Start to the first step's result | 2 round trips | 3 |
| Each later step | 1 | 1 |
| Recovery to the verdict | 1 | 2 |
| Recovery to the repeated step's result | 2 | 3 |
| A lost take response, Zenoh | - | 0 more openings: the same frame again gets the kept response |
| A lost take response, byte stream | - | 2 (a new session and its take) |
| "Term moved" | - | 1 |

SDK surface: `LockstepClient(client)` opens and takes; add a way to read the clock without a take, for a monitor; `recover(client)` always sends the take itself, so a client that was opened earlier is safe (finding R2). The owner holds its lock from the check of a take to its end, as for a step. In the Rust SDK the take must wait on the condition variable while a step is reserved, where `open` waits today; `open` then only reads.

#### Q2.6 Interactions

| With | Result |
| --- | --- |
| Rule 7.1.8 | The profile now conforms literally: accepting `open` reads and changes nothing. A copy of `open` gives a report. Finding R5 (an `open` that takes the ticks and is then rejected) cannot happen. |
| Authenticated frames, 13.2 | The sentence "a request replayed to another session or opening fails the checks of rules 7.3.4 to 7.3.9" now covers everything that changes the holder. `open` is the only request that a copy can run again, and it changes nothing. Without a key and on an open binding, any party can make an `open` and a take: that is outside assumption A2, as today. |
| Zenoh, a copy of `open` | Rule 7.3.5: the kept response while `high` is 0, `seq_stale` after the take. No effect in both cases. |
| Zenoh, a copy of the take (rule 7.6.6) | The kept response, with the clock of the moment when the take ran. A verdict from it stays true, also if a third opening took the ticks since: the old opening was fenced at that moment and stays fenced. |
| Zenoh, the same session identifier (finding R1) | Closed by structure. A step has `seq` 2 or more, so the same `open` gets `seq_stale` once the take ran [C, probe]. If the take itself is the uncertain request, the repeated take is the same frame and runs once. The checker's same-identifier variant holds in 126,523 worlds. Still require a new identifier: it is core rule 7.1.1. |
| Zenoh, expiry | The holder's session can expire. Its next step gets `session_expired`: possibly executed. Recovery gives "did not run". |
| A revision-5 client and a revision-6 owner | Every step is declined with the `holder:` detail. Truthful and without progress. |
| A revision-6 client and a revision-5 owner | No `term` in the `open` response: the client ends the session (rule 3.4). The old owner took the ticks when it accepted that `open`. No consumer uses the profile, so a clean break is acceptable. |

#### Q2.7 What stays true, and what is still lost under replay

Stays true, with copies, delay, loss, expiry, and restarts: one verdict for each step; ticks once each and in order; `declined` is final; only the holder steps. New in revision 4: a copy of `open` takes nothing; no stored frame takes the ticks after the live client's take; a monitor can read the clock.

Still lost:

1. A copy of `open` uses a session slot of the owner until it ends or expires (core rule 7.1.8).
2. A take of an abandoned session can run once if it arrives before the next take. The cost is one declined take.
3. A party that can stop frames stops the stepping. No rule can change that.
4. A party that can make frames (no key, an open binding) can take the ticks.
5. After a restart, a verdict describes the current state only.
6. Two real clients still take the ticks from each other; the term now shows it.

## Checkpoint 10 — two-fault result, and Q4 SECTION (final text)

Two faults, stream shape, 2 steps (prototype of (c)): 5,257,680 worlds, 13,027,723 transitions, 152 s, 4.5 GB; every property holds (`ls_f2_stream_2step.log`). With the zenoh shape (1,388,036 worlds, 53 s): 6,645,716 worlds in 205 s for the new-identifier variant.

### Q4. Figures

Figures (a) and (b) exist as drawing code that passes the generator's own checks: `figures/new_figures.py`, with `ncp2-lockstep-{light,dark}.svg`, `ncp2-verdicts-{light,dark}.svg`, and previews at 860 px. I ran it against a scratch copy of `scripts/gen_diagrams.py`: `problems()`, `contrast_problems()`, `text_rule_problems()`, and `accessibility_problems()` report nothing for both figures in both themes [C ran]. At 860 px the smallest text is 12.9 px (24 units of 1600). Figures (c) and (d) are specifications; I measured their longest strings with the generator's `measure()`.

Common rules for all four: canvas `WIDTH` 1600; `header(c, eyebrow, heading, status)`; the status pill reads the revision from `spec/ncp2-rules.json` (`f"REVISION {RULES['revision']}"`), so a stale figure fails the check; codes come from the same file, never from a list in the generator; the `desc` ends with `NCP 2 is UNRELEASED. It is not release or certification evidence.` and has at most 55 words. Register each in `DIAGRAMS`, `DIAGRAM_OWNERS` (`docs/NCP-2-GUIDE.md`), and `REQUIRED_TEXT`.

#### (a) `ncp2-lockstep`: recovery and takeover, before and after the fix

- **Layout** (the pattern of `ncp2_call`). Two head cards: `Client`, subtitle `Steps the world`, at x 52, width 300; `Owner`, subtitle `Keeps one clock`, at x 560, width 300, accent turquoise. A lifeline under each. At x 900, width 648, four numbered cards; each event is drawn beside its card.
- **Status pill:** `REVISION 6`. **Eyebrow:** `NCP 2 LOCKSTEP`. **Heading:** `A lost step gets one verdict, and it stays true`.
- **Events** (requests lapis, responses turquoise, frames from the network pomegranate):

  | # | Card title and body | Drawing |
  | --- | --- | --- |
  | 1 | `A step is on its way`: `The client sends step s for tick 42 in its first opening. No response arrives in time. The call ends: s possibly ran.` | Arrow from the client line to a pill `DELAYED` at x 470, label `step s, tick 42` |
  | 2 | `Recover in a new session`: `The client opens a new session. The open response reports the clock and takes nothing. A take request, which acknowledges that response, makes the new opening the holder and returns the final clock: tick 41. The client concludes that s did not run, and never will.` (card height 352) | Four messages, 80 units apart: `open, a new session`; `ok, report: tick 41, term 7`; `take, term 7`; `ok, final: tick 41, term 8` |
  | 3 | `A copy of the first open`: `A party on the path sends the first open again, on a third connection. The owner accepts it as a third opening, with the same session name and a new nonce.` | Pill `COPY OF THE FIRST OPEN`, arrow to the owner line |
  | 4 | `The delayed step arrives`: `Step s reaches the first opening, whose owner still waits for its next request. What happens depends on what the holder is.` | Pill `STEP s ARRIVES`, arrow to the owner line |

- **Below the lifelines:** eyebrow `WHEN THE DELAYED STEP ARRIVES`, then `card_row` with two cards:
  - `The holder is a session name`, subtitle `Until revision 4`, accent pomegranate: `The copy of open made the session name the holder again. Step s ran, and the world moved to tick 42. The verdict that s did not run was false.`
  - `The holder is an opening`, subtitle `From revision 6`, accent turquoise: `The second opening holds the ticks, and the copy of open took nothing. Step s is declined and never runs. The verdict stays true.`
- **Note** `WHAT A COPY CAN STILL DO`: `A copy of open opens a session and reads the clock. It cannot take the ticks: a take must acknowledge the open response of its own opening, which holds a fresh nonce. An exhaustive check of the Python SDK with up to two faults found no false verdict. The profile is not proved.` Use the third sentence only when `model/lockstep.py` runs in the gate. Until then: `The profile is neither model checked nor proved.`
- **Alt text:** `A time line of a client and an owner in four steps: a step is delayed, the client recovers in a new session and takes the ticks with a request, a copy of the first open arrives, and the delayed step arrives. Two cards compare the result: with a session name as the holder the step ran after the verdict that it did not; with an opening as the holder it is declined.`
- **Required text:** `did not run`, `new nonce`, `take, term 7`.
- **If drawn for revision 5** (takeover in `open`): event 2 has only the first two messages, with the label `ok: tick 41`; the second result card reads `The copy of open took the ticks from the second opening, so the live client must open again. Step s is still declined, and the verdict stays true.`

#### (b) `ncp2-verdicts`: the verdict map

- **Layout.** Three cards of equal height at y + 10: x 52 width 330; x 414 width 470; x 916 width 632. Inside each card, under its body text, groups of chips: a group label in `SMALL`, then one rounded box for each code (height 46, pitch 54, fill `tint`, stroke in the card's accent, text `CELL`). One chip in a row in the first two cards, two in a row in the third.
- **Status pill:** the revision of the rules file. **Eyebrow:** `NCP 2 VERDICTS`. **Heading:** `Every answer has one place`.
- **Columns**, generated from the members `client`, `outcome`, and `open` of each code:

  | Card (title, subtitle, accent, body) | Groups and chips |
  | --- | --- |
  | `Executed`, `It ran once`, turquoise: `The owner executed the request one time.` | `ok`: `ok`. `ended`: `result_too_large` |
  | `Not executed`, `It never runs`, lapis: `The owner did not execute the request, and it never will.` | `declined`: `unknown_op`, `body_invalid`. `ended`: `shutdown *`, `bad_frame *`. `rejected, in reply to open`: `body_invalid`, `contract_mismatch`, `bound_unacceptable`, `refused` |
  | `Possibly executed`, `The honest unknown`, pomegranate: `The client cannot know. At most one request of a session ends here, and it is the last one.` | `rejected, in reply to another request`: the ten codes `wrong_protocol` to `already_open`. `ended`: `session_expired`, `owner_failure`, and one wide chip `a code that the client does not know`. `local events`: the four `local.` codes |

- **Note** `HOW TO READ IT`, two paragraphs: `A client acts on the outcome first and on the code second. After a code that it does not know: rejected means that the frame was not admitted, declined means that the request never executes, and ended means possibly executed.` and `* In a response that names no request, bad_frame and shutdown count as not executed only when the body binds the response to the client's chain. Otherwise the request is possibly executed.`
- **Alt text:** `Three columns sort every NCP 2 answer by what the client may conclude. Executed: ok and result_too_large. Not executed: the declined codes, shutdown, bad_frame, and a rejected open. Possibly executed: every other rejection, owner_failure, session_expired, a code that the client does not know, and the four local events.`
- **Required text:** `result_too_large`, `session_expired`, `local.timeout`.
- **Use.** It replaces the lower eight cards of `ncp2-outcomes`, or stands next to that figure in the guide. One open point: the first card is half empty. Narrow it to 300 and widen the third, or accept it; the empty space also says that few answers mean "executed".

#### (c) `ncp2-ladder`: the owner decision ladder (specification)

- **Layout.** One row for each of the rules 1 to 10, top to bottom. In each row: a check box at x 52, width 620, with a number badge and a question in `TITLE_NARROW`; an arrow of 56 units to the right; an exit box at x 728, width 820, with the answer in `CELL`. A vertical arrow of 34 units joins each check box to the next; this is the path of a frame that passes. Rows with two exit lines (1, 3, 5, 10) are 92 units high, the others 62.
- **No verdict column.** The exit box's stroke gives the client's verdict for a request other than `open`: pomegranate for possibly executed, lapis for not executed, turquoise for the kept response, `muted` for a row with two answers. Three `legend_line` samples under the heading say so: `possibly executed`, `not executed`, `the first answer again`.
- **Status pill:** the revision. **Eyebrow:** `NCP 2 OWNER RULES`. **Heading:** `A frame leaves at the first check that fails`.
- **Rows.** The codes of rows 2 to 10 come from the rules file by their `rule` member (`7.3.N`).

  | # | Question | Exit |
  | --- | --- | --- |
  | 1 | `Is the frame bad?` | `byte stream: ended: bad_frame; Zenoh: no answer` |
  | 2 | `Is ncp not 2?` | `rejected: wrong_protocol` |
  | 3 | `Does the owner hold no session?` | `open with seq 0: start a session (section 7.1)` and `otherwise rejected: not_open, or ended: session_expired` |
  | 4 | `Is it another session?` | `rejected: wrong_session` |
  | 5 | `Is seq equal to high?` | `the same request: the kept response again` and `another request: rejected: seq_conflict` |
  | 6 | `Is seq below high?` | `rejected: seq_stale` |
  | 7 | `Is seq above high + 1?` | `rejected: seq_gap` |
  | 8 | `Has the session ended?` | `rejected: session_ended` |
  | 9 | `Is ack missing or wrong?` | `rejected: ack_missing, ack_mismatch` |
  | 10 | `Is it open, or does the owner stop?` | `rejected: already_open; ended: shutdown` |

- **Rule 11** is a band across the full width, drawn like a `note` (fill `note`, saffron bar at the left): `11  Admitted. The owner keeps every response from here on, and its answer never changes.`
- **Rule 12** is a card `12  Execute` with four chips in two rows of two (each 732 wide): `ok: the result` (turquoise), `declined: unknown_op, body_invalid` (lapis), `ended: result_too_large` (turquoise), `ended: owner_failure` (pomegranate). From revision 6, a fifth, small line of text under the title: `A feature operation of an enabled feature goes to its profile.`
- **Rule 13** is the last line of the same card: `13  Keep the response. After ended, or after close, the session is over.`
- **Note** `WHY THE ORDER MATTERS`: `A copy of the last admitted request leaves at check 5 with the kept response, so it never executes twice. Every check before check 11 changes no state. A rejected request other than open still means possibly executed for the client: the owner can have lost the session and opened it again.`
- **Alt text:** `Thirteen checks in the order of section 7.3 of the specification. A frame leaves at the first check that fails, with the outcome and code shown beside it. A frame that passes ten checks is admitted, and the owner keeps every answer from that point.`
- **Required text:** `kept`, `seq_stale`, `ack_mismatch`. Estimated height 1,750 units.

#### (d) `ncp2-transcript`: the transcript file (redesign, specification)

- **Status pill:** `TRANSCRIPT VERSION 2`. **Eyebrow:** `NCP 2 TRANSCRIPT`. **Heading:** `One file, two hash chains`.
- **Row 1, the file,** as the byte bar of `ncp2_frame` (height 112, title in `SEGMENT`, size in `SEGMENT_NOTE`, offset labels in `SMALL` above): `Magic` / `8 bytes` (lapis, width 190); `Header` / `4 + L bytes` (lapis, 260); `Record 1` / `45 + n bytes` (turquoise, 330); `Record 2` / `45 + n bytes` (turquoise, 330); `…` (rule color, 104); `End record` / `45 bytes` (bronze, 252).
- **Row 2, one record,** a second bar 90 units below, joined to `Record 2` by one connector: `Kind` / `1 byte` (150); `Time` / `8 bytes` (250); `Length` / `4 bytes` (200); `Frame` / `n bytes` (568); `Chain value` / `32 bytes` (304, bronze). Under it, two lines in `BODY`: `Kind: 1 sent, 2 received, 3 end. Time: nanoseconds since the recorder started. Frame: the exact bytes.` and `chain value = D(chain value before ‖ kind ‖ time ‖ length ‖ digest of the frame)`.
- **Row 3, eyebrow `THE FRAMES OF ONE SESSION`:** four boxes of width 210 at the x positions of `c1` to `c4` below, as in the present figure (`SMALL` over `TITLE_NARROW`): `request 0` / `open`; `response 0` / `ok`; `request 1` / `step`; `response 1` / `ok`. Arrows point backward, from each box to the box at its left: turquoise from a response to its request, lapis from a request to the response before it. Legend under the row: `request: a response names its request` (turquoise) and `ack: a request names the response before it` (lapis).
- **Row 4, eyebrow `THE CHAIN OVER THE RECORDS`:** six boxes of width 210 with gaps of 47: `c0` / `magic and header`; `c1`; `c2`; `c3`; `c4`; `end` / `counts the records`. Arrows in `muted` point backward from each box to the one before it. One unlabelled vertical connector joins each frame of row 3 to the chain box under it. Legend: `chain value: covers the record before it`.
- **Note** `WHAT A VERIFIER CHECKS`: `Every frame digest and every chain value; the order of seq and ack; that two answers to one request are the same bytes. A changed, removed, or reordered record breaks the chain over the records. A program records a frame before it sends it, so the file holds every request that the peer may have run. Without a key, anyone can write a file that verifies: transcripts are not signed.`
- **Alt text:** `The layout of a transcript file: magic, header, records, and an end record, with one record opened into kind, time, length, frame, and chain value. Two rows show the two hash chains: the frames of a session name each other backward by ack and request, and each record's chain value covers the record before it.`
- **Required text:** keep `before it sends it` and `not signed`. Estimated height 1,400 units.

## Checkpoint 11 — the final report is written

`fable-consult-rev5.md` is complete: verdict, what I ran, sections 1 to 4, the ranked next steps, and the list of files. Sections 2 to 4 are the final texts of checkpoints 8 to 10 with the measured two-fault numbers. One run is still open: the same-identifier variant with two faults (`ls_f2_same_identifier.log`); its result goes into the table of section 3 when it ends.
Note: on 15 November the worktree showed uncommitted changes in `python/ncp/lockstep.py`, `messages.py`, `owner.py`, and the tests (the implementation of option (c), I assume). I did not review them.

## Checkpoint 12 — closed

- Same-identifier variant, two faults (prototype of (c)): stream 1,995,372 + zenoh 138,275 = 2,133,647 worlds, 73 s, every property holds (`ls_f2_same_identifier.log`). Full two-fault gate: 8,779,363 worlds, 278 s, 4.5 GB peak.
- Figure (c), the owner ladder, also exists as code in `figures/new_figures.py` and passes the generator's checks in both themes (1600 x 1903).
- `fable-consult-rev5.md` holds these results. Nothing is open on my side.
