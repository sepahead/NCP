# NCP 2 profile: lockstep

Status: a profile of NCP 2.0, release candidate, revision 5 of 17 November 2026. Section 10 lists the changes of each revision.
This document is normative. The key words MUST, MUST NOT, SHOULD, SHOULD NOT, and MAY are to be interpreted as described in RFC 2119 and RFC 8174 when, and only when, they appear in all capitals.
It builds on revision 7 of the [NCP 2 specification](NCP-2.md) and changes nothing in it. The Python SDK implements it as `ncp.Lockstep` (owner) and `ncp.LockstepClient` (client), and the Rust SDK as `ncp::Lockstep` and `ncp::LockstepClient`.

## 1. Purpose

A simulation step changes state that outlives the session: the world advances by one tick for each step.
NCP 2 tells a client whether its last request executed. But if a session ends with its last step possibly executed, for example because the connection broke or a time limit passed, the session cannot tell the client whether the world advanced.
This profile numbers the steps of the owner's state with ticks that outlive sessions. One opening at a time holds the ticks, and only it can step. A client takes the ticks with a request inside its opening, and the response gives the final tick and the request that produced it. A client that lost a session therefore learns from a new session whether its last step ran, and no copy of the old step can run afterwards.
An `open` only reports the tick. It takes nothing, so a copy of an `open` changes nothing (specification, rule 7.1.8).

## 2. Terms

| Term | Meaning |
| --- | --- |
| Tick | The number of lockstep steps that the owner's state has applied: an integer from 0 to 9,007,199,254,740,991. The owner names the tick of its state when it starts, 0 by default. |
| State digest | A string of 1 to 128 characters that the application derives from its state when the owner starts and after each step, or `null`. Equal states give equal digests. |
| History identity | 32 lowercase hexadecimal characters that name one history of the owner's state: the steps that led to it. The owner draws a new one when a step can have started after the state that it restores (rule 5.7). |
| Lockstep operation | An operation of the contract that the owner serves under this profile. |
| Clock | The owner's tick T, its state digest S, the identity R of the request whose step produced T, or `null`, its term E, and its history identity H. The owner keeps one clock for its state, across all sessions. |
| Term | A counter that each take raises by 1 (rule 5.3): an integer from 0 to 9,007,199,254,740,991. It starts at 0, or at the term that the owner restored (rule 5.7). |
| Take | The feature operation `ncp.lockstep.take` (specification, section 15, rule 3). |
| Holder | The opening (specification, section 2) that can step the owner's state: the opening whose take ran last. At most one opening is the holder, and none when the owner starts. A session identifier does not name one opening: a copy of `open`, or a client that uses the same identifier again, opens the session again with another nonce (specification, rule 7.1.8). |
| Reader | An opening that the owner lets only read the clock (rule 3.5). |

## 3. Feature

1. A client asks for the profile with the feature `ncp.lockstep` and the parameters `{"rev": [5]}` in its `open` request: the revisions of this profile that it speaks (specification, section 7.1, and section 17, rule 1). An owner reads only the member `rev` of these parameters. An owner of this revision enables the feature only if `rev` is an array that has the integer 5.
2. An owner that serves the profile enables the feature with the parameters `{"rev": 5, "tick": T, "state": S, "request": R, "term": E, "history": H, "take": B}`: its clock at one instant, and whether the opening may take the ticks. `B` is `false` for a reader and `true` otherwise.
3. **`open` reads.** Accepting an `open` MUST NOT change the clock or the holder (specification, rule 7.1.8). The clock in an `open` response is a report, not a final value: a step of the holder can run after it.
4. A client MUST NOT send a take or a lockstep step in a session whose `open` response does not enable the feature with `rev` 5 and these members. Parameters without them come from an owner of another revision of this profile; the client then ends the session.
5. **Readers.** An owner MAY let an opening only read the clock, for example every opening of a service for monitors, or of a peer that the binding identifies (specification, section 13). It declines each take and each lockstep step of a reader with `body_invalid` and the reason `ncp.lockstep.reader`. A client MUST NOT send a take or a lockstep step in an opening whose report has `"take": false`.

## 4. Requests

1. The body of a take MUST be an object with exactly the member `term`: the term that the owner told the client last in this session, in the `open` response or in a later response.
2. The body of a request of a lockstep operation MUST be an object with the member `ncp.tick`: an object with exactly the members `tick`, the tick that the step advances to, an integer from 0 to 9,007,199,254,740,991, and `state`, the state digest that the step answers, a string of 1 to 128 characters or `null`.
3. A client sets `tick` to the tick of the last clock that it accepted in this session plus 1, and `state` to the state digest of that clock. That clock is the body of the `ok` response to its take, or `ncp.tick` in the `ok` response to its last step after that. It is never the clock of an `open` response.

## 5. Owner rules

The owner keeps one clock and one holder for its state, across all sessions.

1. **One at a time.** From the check of a take (rule 5.2) or of a lockstep step (rule 5.4) to the end of its execution, the owner MUST NOT check or execute another take or lockstep step of any session. A take therefore waits for a step that is running. An `open` response reports the clock as it is before or after a step, never in the middle of one.
2. **Take, check.** The owner declines a take with `body_invalid` (specification, section 7.3, rule 12) if its body is not as rule 4.1 says. It declines it with `conflict` and the reason `ncp.lockstep.term` if `term` is not the owner's term, and the body of the response MUST then have the member `ncp.lockstep` with the value `{"term": E}`, the owner's term. An owner whose term is 9,007,199,254,740,991 declines every take that names it with `conflict` and the reason `ncp.lockstep.limit`: no take can raise that term. Nothing changes.
3. **Take, execution.** Otherwise the take counts as executed: the opening of the request's session becomes the holder, and the owner raises its term by 1. The body of the `ok` response is `{"tick": T, "state": S, "request": R, "term": E, "history": H}`: the clock after the take. This clock is final for every other opening: rule 5.4 declines each of their steps until one of them takes the ticks. The owner MUST identify the holder by its opening, for example by its nonce, and MUST NOT identify it by the session identifier.
4. **Step, check.** The owner declines a request of a lockstep operation with `body_invalid` if the body has no `ncp.tick` member as rule 4.2 defines it. It declines it with `conflict` and a reason, in this order: `ncp.lockstep.holder` if the opening of the request's session is not the holder, and the body of the response MUST then have the member `ncp.lockstep` with the value `{"term": E}`; `ncp.lockstep.limit` if the owner's tick is 9,007,199,254,740,991; `ncp.lockstep.tick` if `tick` is not the owner's tick plus 1, and the body MUST then have the member `ncp.lockstep` with the value `{"next": N}`, where N is the owner's tick plus 1; and `ncp.lockstep.state` if `state` is not the owner's state digest. The request never executes.
5. **Step, execution.** Otherwise the owner executes the step. The step counts as executed when the owner starts to execute it, also if the application then fails (specification, section 7.3, rule 12). The owner then sets its tick to `tick`, its state digest to the application's digest of the new state, or `null` if the application cannot give one, and R to the identity of the request. The term and the history identity do not change. The body of the `ok` response is an object: the application's result, with the member `ncp.tick` set to `{"tick": T, "state": S, "request": R}`.
6. Other operations do not change the clock or the holder. An operation that is not a lockstep operation MUST NOT change the state that the state digest describes: an application whose other operations change that state serves them as lockstep operations. The owner declines every other operation of the feature `ncp.lockstep` with `unknown_op` (specification, section 7.3, rule 12).
7. **Start and restart.** An owner that starts draws a history identity from at least 128 bits of a cryptographically secure random generator, as for a nonce (specification, rule 7.1.5). An owner that restarts holds no session (specification, rule 7.1.5), and no opening is the holder. It MAY restore its clock. It MUST then restore T, S, and R from one saved clock that belongs to the application state that it restored. It MAY restore E with them; otherwise its term is 0. It MUST draw a new history identity, unless no step started after that clock was saved; only then MAY it restore H with it. An owner that restores no clock starts at its initial tick, with S the application's digest of its initial state, R `null`, and a new history identity. An application can save the clock with the state that a step produces: T is `tick` of the step, S its digest of the new state, R the identity of the request, and H the history identity. To restore H, it must know that no later step started, for example because it records the start of each step before it executes it.
8. **Reasons and details.** Each decline of this profile has the code, the reason, and the facts of this table. [`ncp2-rules.json`](ncp2-rules.json) lists the reasons. The member `detail` SHOULD be the text of the table, with the number in place of N or E. In the two rows for a body, E, T, and S stay as they are.

   | Check | Code | `ncp.reason` | `ncp.lockstep` | `detail` |
   | --- | --- | --- | --- | --- |
   | Rule 5.2, body | `body_invalid` | none | none | `member: a take needs the body {"term": E}` |
   | Rule 5.2, term | `conflict` | `ncp.lockstep.term` | `{"term": E}` | `term: the term is E` |
   | Rule 5.2, largest term | `conflict` | `ncp.lockstep.limit` | none | `term: the term is the largest; no take can follow it` |
   | Rule 5.4, body | `body_invalid` | none | none | `member: a lockstep step needs "ncp.tick": {"tick": T, "state": S}` |
   | Rule 5.4, holder | `conflict` | `ncp.lockstep.holder` | `{"term": E}` | `holder: this opening does not hold the ticks; send ncp.lockstep.take` |
   | Rule 5.4, largest tick | `conflict` | `ncp.lockstep.limit` | none | `tick: the tick is the largest; no step can follow it` |
   | Rule 5.4, tick | `conflict` | `ncp.lockstep.tick` | `{"next": N}` | `tick: the next tick is N` |
   | Rule 5.4, state | `conflict` | `ncp.lockstep.state` | none | `state: the step answers another state` |
   | Rule 3.5, reader | `body_invalid` | `ncp.lockstep.reader` | none | `reader: this opening may only read the clock` |
   | Rule 5.6 | `unknown_op` | none | none | `operation: the lockstep profile defines no operation N; it defines ncp.lockstep.take` |

   A client MUST NOT act on `detail`. It acts on the outcome, the code, the reason, and the member `ncp.lockstep` (specification, rule 7.6.8).

## 6. Client rules

1. **Start.** A client that steps sends a take with the term of the `open` response before its first step, in an opening whose report has `"take": true`. After the `ok` response, its opening is the holder, and the body is the owner's clock. The client MUST check that `term` in the body is the term of its request plus 1. A client that only reads the clock, for example a monitor, sends no take.
2. **A declined take.** A take declined with the reason `ncp.lockstep.term` means that another take ran after the owner told the client the term. The client MAY send a take again in the same session, with the term of the member `ncp.lockstep`. It SHOULD stop after 3 takes without an `ok` response, and report that another client takes the ticks.
3. After an `ok` response to a step, the client MUST check that `ncp.tick` names the tick of its request and the identity of its request. The client then knows the owner's clock: the tick, the state digest, R, and the history identity of its take, which a step does not change.
4. After a `declined` response to a step, the step did not run, and it never will. With the reason `ncp.lockstep.holder`, another opening took the ticks, and the client MAY take them again in the same session, with the term of the member `ncp.lockstep` (rules 4.1, 6.1, and 6.2). With the reason `ncp.lockstep.tick` or `ncp.lockstep.state`, the clock that the client knows is not the owner's; a client that follows these rules sees these reasons only after a defect, and a take in the same session gives it the owner's clock.
5. **Recovery.** If a step is possibly executed (specification, section 7.7, property 7), the client opens a new session with the feature and a new session identifier (specification, rule 7.1.1), and sends a take there (rule 6.1). It MUST send that take after the step became possibly executed. The client reaches its verdict from the body of the `ok` response to that take, and from no other response:
   - If the body names the tick of the step and, as `request`, the identity of its request, the step ran.
   - If the body names exactly the clock that the client knew before the step: the tick of the step minus 1, the state digest that the step answered, as `request` the identity of the request that produced that tick, and the same history identity, the step did not run, and it never will. The client can send it again in the new session.
   - Any other body means that the owner's clock changed in another way, for example by the step of another client, or by a restart that drew a new history identity. The client MUST then treat the step as possibly executed. Its opening holds the ticks, and the body is the owner's clock, so the client can go on from it.
6. **A take without a response.** If a take is possibly executed, the client opens a new session and sends a take there. It needs no verdict for the old take: the new take makes the new opening the holder in both cases, and rule 5.2 declines the old take if it arrives later.

## 7. Properties and limits

These properties hold under the assumptions A1 to A4 of the specification (section 7.7).

- **One true verdict for each step.** If the owner keeps its clock and no other client takes the ticks while the client recovers, recovery turns every step that is possibly executed into a step that ran or a step that did not run and never will. The take of the recovery runs after every step that the owner checked before it (rule 5.1). After it, the old opening is not the holder, and it cannot become the holder again: only a take in the old opening could do that, and the client sent its last request there. Every verdict is true, also across restarts: a verdict "did not run" needs the history identity that the client knew, and an owner keeps it only if no step started after the clock that it restored.
- **One stepping opening.** Only the holder can step.
- **`open` takes nothing.** A copy of an `open`, also a delayed or a replayed one, opens a session and reads the clock. It changes nothing outside its session. A monitor reads the clock without an effect on the stepping client, and a reader cannot take the ticks at all.
- **A take belongs to one opening.** A take acknowledges the `open` response of its opening, which holds a fresh nonce. An owner admits it at most once, and only in that opening (specification, section 7.7, property 1). A party that can only deliver copies of frames therefore cannot take the ticks, also when frames are authenticated (specification, section 13.2). A party that can make frames can: use a key, or a binding that admits only the two endpoints (specification, section 7.7, assumption A2), and serve monitors as readers.
- **A stable holder.** After a take ran, every take that a client made before it names an earlier term, and rule 5.2 declines it. A take of an abandoned session can still run if it arrives before the next take; that next take is then declined once, and succeeds with the term of the response. The term keeps the holder stable; the verdicts of rule 6.5 do not depend on it.
- **Reasons.** A client branches on reasons without parsing text: it takes the ticks again after `ncp.lockstep.holder` and after `ncp.lockstep.term`, with the term of the facts, and learns the owner's next tick from the facts of `ncp.lockstep.tick`. No reason changes a verdict: a declined request did not run and never will.
- **Cost.** One more round trip for each session that steps: `open`, take, then the steps. A recovery has its verdict after two round trips.
- **Several clients.** Clients that step the same owner take the ticks from each other, and a recovery that finds another client's step gives no verdict. The term shows each takeover. Use one stepping client, or the [rounds profile](NCP-2-ROUNDS.md).
- **Failures.** A step whose application fails counts as executed (rule 5.5), because the application can have changed its state before it failed. Recovery then says that the step ran; the state digest says what the state is.
- **Restarts.** A restore of the latest saved clock with its history identity follows a clock after which no step started, so "did not run" stays true for the step that the client lost. Every other restore, to an earlier saved clock, to another state, or without the knowledge that no step started, draws a new history identity: a recovery then gives no verdict, never a false "did not run". A step whose effect is in the restored state still shows as "ran". If a step has effects outside the owner's state, such as the motion of an actuator, the verdict "ran" says only that the step started; it does not say that those effects completed.
- **What a copy still costs.** A copy of `open` uses one session of the owner until that session ends or expires. A party that can stop frames can stop the stepping.
- **Evidence.** Both SDKs test this profile, including a copy of an `open`, a copy of a take, a delayed take of an abandoned session, a take that waits for a step, a recovery that reaches the old opening, a restart to another state, a restore to an earlier saved clock, a restart that keeps or draws the history identity, a reader, and the reason and the facts of each decline (`LockstepTests` in `python/tests/test_ncp.py`, and `rust/tests/sessions.rs`). An exhaustive bounded check, [`model/lockstep.py`](../model/README.md), drives the owner and the session client of the Python SDK, with the verdict function of `LockstepClient`, through every reachable state of one stepping client that acts on the reasons, with copies of every frame, loss, expiry, restarts that keep the latest clock with its history identity or with a new one, restore the same tick with another state, or restore an earlier saved clock with a new history identity, and a second client, with up to one fault in the gate and two in an advisory run. It checks that every verdict is true across all of these, and that every reason and its facts are true; its self-test detects seventeen known defects, at least one for each property. The profile is not proved.

## 8. Verification

A verifier of a transcript (specification, section 10.3) that knows that a session used this profile can check these rules of the session, in addition to the rules of the specification:

1. The `open` response enables the feature with `rev` 5, and each later `ok` response to a take has a `term` 1 larger than the `term` of its request.
2. Each `ok` response to a lockstep step has `ncp.tick`, whose `tick` is the `tick` of the request's `ncp.tick` and whose `request` is the identity of the request.
3. Each lockstep step after a take names, in its `ncp.tick`, the tick plus 1 and the state digest of the last clock that the session accepted (rule 4.3): the body of the `ok` response to the take, or `ncp.tick` in the `ok` response to the last step after it.
4. Each decline of the profile has the code, the reason, and the facts of rule 5.8.

Across the sessions of one owner, each step that ran in one history identity advances the tick by 1, and no two steps produce the same tick. A step that ran shows its tick and its request in every later clock of that history until the next step.

## 9. Example

```text
open request body:   {"application": "world", "contract": "…", "bound": 1048576,
                      "features": {"ncp.lockstep": {"rev": [5]}}}
open response body:  {"bound": 1048576, "application": "world", "contract": "…",
                      "implementation": "…", "nonce": "…",
                      "features": {"ncp.lockstep": {"rev": 5, "tick": 41, "state": "9f2c",
                                                    "request": "5d0e…", "term": 7,
                                                    "history": "3a7f…", "take": true}}}
take request:        op "ncp.lockstep.take", body {"term": 7}
take response body:  {"tick": 41, "state": "9f2c", "request": "5d0e…", "term": 8,
                      "history": "3a7f…"}
step request body:   {"dt_ms": 10, "ncp.tick": {"tick": 42, "state": "9f2c"}}
step response body:  {"observation": [0.1, 0.2],
                      "ncp.tick": {"tick": 42, "state": "77ab", "request": "a71b…"}}
```

Here `a71b…` is the identity of the step request. If the step response is lost, the client opens a new session and sends a take with the term of its `open` response, 8. The body `{"tick": 42, "state": "77ab", "request": "a71b…", "term": 9, "history": "3a7f…"}` says that the step ran. The body `{"tick": 41, "state": "9f2c", "request": "5d0e…", "term": 9, "history": "3a7f…"}` says that it did not run and never will. The same clock with another history identity says neither: the owner restored a state after which a step can have started.
A take with the old term 7 gets `declined` with `conflict` and the body `{"detail": "term: the term is 9", "ncp.lockstep": {"term": 9}, "ncp.reason": "ncp.lockstep.term"}`.

## 10. Changes

### 10.1 Revision 5 (17 November 2026)

An advisory design review of revision 4 found that a restore to an earlier saved clock gave the verdict "did not run" for a step that had run, with an effect outside the state, so that the client could run it twice. It also found that a client could not tell the revision of the profile, that four refusals by state shared `body_invalid` and told the client its next tick only in `detail`, and that every opening could take the ticks.

- The history identity (terms, rules 3.2, 5.3, 5.7, and 6.5): "did not run" needs the history identity that the client knew, and an owner keeps it only if no step started after the clock that it restored. Every verdict is now true across restarts.
- Rule 3.1 and 3.4: the revision on the wire, as section 17 of revision 7 of the specification requires.
- Rules 5.2, 5.4, 5.6, and 5.8: the code `conflict` and the reasons `ncp.lockstep.term`, `holder`, `tick`, `state`, `limit`, and `reader`, with their facts, from revision 7 of the specification; `unknown_op` for an operation of the feature that the profile does not define.
- Rule 3.5: readers.
- Rule 4.2: the types of `tick` and `state`, so that `body_invalid` means that no state accepts the body.
- Section 8: what a verifier of a transcript can check.
- Section 7: the model check drives revision 5 with a client that acts on reasons, a strict property S1, and a new property S7 for reasons.

### 10.2 Revision 4 (15 November 2026)

An advisory review of revision 3 found that a recovery could still give a false "did not run". On the Zenoh binding, a recovery that used the session identifier again reached the old opening, whose kept `open` response gave an old report. A client that was opened before the step read an old report. A restart to the same tick with another state passed. A copy of `open` also took the ticks from the live client, and an `open` that the owner then rejected could take them too.

- Rule 3.3: an `open` only reports the clock. The take (rules 5.2 and 5.3), a feature operation of revision 6 of the specification, takes the ticks.
- The term (rules 5.2 and 5.3): a take names the term that it knows, so that a late take of an abandoned session cannot take the ticks from a newer holder.
- Rule 6.5: the verdict comes from the response of the take, "did not run" needs the whole clock that the client knew, and recovery uses a new session identifier.
- Rules 5.4 and 6.4: a step that the holder check declines names the term, so that the client can take the ticks again.
- Rule 5.7 on restarts, and the detail texts of rule 5.8.
- Section 7: a model check of the profile.

A second advisory review of the draft of revision 4 found edge cases at the largest values, at tick 0, and in the SDKs:

- Rules 5.2 and 5.4: an owner at the largest term declines a take without the member `ncp.lockstep`, so that rule 6.2 stays true, and an owner at the largest tick declines every step.
- The terms tick, state digest, and term, and rule 5.7: the state digest at the start is the application's digest of its initial state, so that a restart at tick 0 to another state gives no verdict.
- Rule 5.6: other operations do not change the state that the state digest describes.
- Rules 6.4 and 6.5: a client takes the ticks again with the term of the decline, and after a recovery without a verdict it goes on from the clock of the take.

### 10.3 Revision 3 (14 November 2026)

An advisory review of revision 2 found that both SDKs named the holder by the session identifier. A copy of an earlier `open`, replayed on another connection, or a recovery that used the same session identifier on another connection, then gave an earlier opening the ticks again, and its delayed step ran after the recovery had said that it did not run and never would.

- The term holder and rule 3.3: the holder is an opening, not a session identifier.
- Rule 5.1: the check of the holder names the opening of the request's session.
- Section 7: what a copy of `open` costs.

It planned the change that revision 4 makes: `open` only reports the tick, and a request inside the new opening takes the ticks.

### 10.4 Revision 2 (13 November 2026)

An advisory review of revision 1 found that recovery could say "did not run" for a step that then ran: a copy of the step that was still on its way reached the old session after the new session had read the tick. Revision 2 fences the earlier sessions.

- Rule 3.3 and the term holder: the last session that asked for the feature takes over the ticks, and the owner declines the steps of earlier sessions.
- The member `request` in the parameters of rule 3.2 and in `ncp.tick` (rule 5.3), which client rules 6.1 and 6.3 check.
- Rule 5.3: a step counts as executed also if its application fails.
