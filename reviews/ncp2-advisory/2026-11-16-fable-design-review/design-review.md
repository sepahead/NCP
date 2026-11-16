# NCP 2 design review: architecture, next profiles, tag scope

Date: 16 November 2026. Reviewer: an independent, read-only language-model advisor (Fable 5.2).
This report is non-normative. It informs the maintainer's decisions and certifies nothing: not security, safety, interoperability, scale, or release readiness.

Reviewed source: NCP worktree `.ncp2-hardening` at `904f87c` (equal to `origin/main`): specification revision 6, lockstep profile revision 4, rounds profile revision 2.
Also read, through Git objects and without a change: CREBAIN `a071ea7`, Galadriel `20ddc41`, Haldir `221c045`, and the four earlier advisory reports in `.ncp-fable-reviews/`.
I wrote nothing in any repository. Every run used a `git archive` copy in `/tmp`, with `python3 -I -B`.
The SDK defects of `2026-11-16-rev6-verify/` are out of scope. After my snapshot, `main` moved to `4e5a6de`. The coordinator reports that this commit fixes them: missing clock members end the session in both SDKs, `take()` keeps the told term, the S4 excuse of the model is exact, with 13 mutants, the requirements map covers section 15, and the verdict figure has a note on a rejected `open`. I did not read `4e5a6de`. Every result, count, and line number below is of `904f87c`. This report recommends none of those items as open work.

Marks: **[C]** confirmed: I read the code or the text, or ran the command. **[S]** suspected: reasoned, not reproduced.
Paths without a directory are in the NCP worktree. Paths that start with `probes/`, `prototype/`, or `png/` are in the directory of this report.

---

## Summary

**1. Architecture.** The split into exchange, profiles, and bindings is right for the exchange, and three reviews in a row found no defect in the exchange rules. It is not yet an architecture for the product. Ranked:

1. The stream is the weak half. It has a message format and the twelve rules of section 8, and no type, time, liveness, announcement, or publisher identity. Every NCP 1 use that still has to move is a stream or a command.
2. NCP 2 has no command pattern with authority and gives the application no identity of its peer. This blocks CREBAIN's application, Haldir, and Engram's plant commander.
3. "Profile" has no fixed shape: three ways to attach, no revision on the wire, no rules for a transcript verifier, and the SDKs compose profiles by wrapping handlers, which cannot combine rounds with lockstep.
4. Nothing names a run. Sessions, streams, and transcripts of one composition are joined by convention only, so "declared profiles for many entities and several sensor modalities" has no document that NCP checks.
5. The first consumer built profile features in its own contract: CREBAIN's `step` has `tick_index`, `source_state_digest`, and `proposals` by identity. The profiles have no consumer because the consumer could not wait for them.

**2. The next profiles.** Section 2 gives wire members, rules, failure semantics, a model-check plan, and risks for each.

- Decline reasons: one new `declined` code, `conflict`, and a body member `ncp.reason` with a registered name. The reserved prefix means that it can come after a tag.
- Stream profile: the type in the stream identifier, a start message as the root, `ncp.t`, `ncp.alive`, `ncp.void`, `ncp.dropped`, and `ncp.refs` in the body, and a feature operation `ncp.streams.list` that announces streams and gives authenticated anchors. All of it fits the stream message of section 6.3 without a change.
- Authority profile: the body is the owner. `ncp.authority.acquire` inside the opening, with a term that the body issues and a token over exact bytes that names the `open` response. Every response gives the remaining time, a window, and a random grant. The next command acknowledges that response, so the body can bound the age of a command on its own clock. The stop request has its own service and a session that is opened before it is needed.

**3. Tag.** Tag the exercised core now: sections 3 to 7 without 6.3, 9.1, 10, 11 without 11.1, the frame rules of 13.2, 12, 14, and 15. Keep sections 6.3, 8, 9.2, 11.1, the guidance on keys and TLS in section 13, and both profiles provisional, each with its own revision. One version for several wire revisions is acceptable only before the tag and only while every consumer pins a commit; put the revision into the implementation string now. The gates that matter most before the tag: the fault campaign and one benchmark block on the tagged revision, and a decoder and owner by another author against the vectors.

**4. Remaining design flaws.**

- Lockstep: a restore to an earlier saved clock gives "did not run, and it never will" for a step that ran [C, probe]. A history identity in the clock turns that verdict into "no verdict". A prototype on `904f87c` holds the strict form of property S1 in all 469,268 worlds of the gate's check and keeps 12 of 12 mutants [C].
- Rounds: no recovery of a verdict or a result [C, probe], no clock and no restart rule, members by first claim under one key, exclusion for ever with a deadline that no client is told, and a record without an identity or a chain.

**5. Figures.** Missing: an NCP 2 ecosystem map, a layer figure, the second opening, the transcript file, an evidence map, and a tag-scope map. Misleading: the heading of `ncp2-lockstep`, and `ncp2-bindings`, which is prose in boxes. The publication in the repository is an NCP 1 document with no NCP 2 figure. Section 5 gives a short specification for each.

---

## What I ran

| Command or probe | Result |
| --- | --- |
| `probes/lockstep_restore.py` | The step for tick 2 runs; its response is lost; the owner restores the saved clock of tick 1 as rule 5.7 says; `recover()` returns `no` |
| `probes/rounds_lost_response.py` | The `open` response of the new session enables nothing; round 1 again gives `declined body_invalid` with the body members `['detail']`; round 2 is accepted |
| `probes/stream_lru.py` | A subscriber with `max_streams=4` accepts a replayed first message of an evicted live stream as `accepted` |
| `model/lockstep.py --faults 1` with verdict counters, original SDK (`prototype/baseline_f1.log`) | 469,268 worlds, every property holds. 230 verdict events "did not run" for a step that ran before a restore |
| The same check with a history identity and the strict S1 (`prototype/history_keep_f1.log`) | 469,268 worlds, every property holds. No "did not run" event remains for a step that ran; the 230 events are "no verdict" |
| Its self-test (`prototype/history_selftest.log`) | 12 of 12 known defects detected (the model of `904f87c` has twelve) |
| A judge that ignores the history (`prototype/history_mutant.log`) | Caught by S1 with the trace of the restore |
| Every restart draws a new history (`prototype/history_new_f1.log`) | 471,556 worlds, every property holds |
| `rsvg-convert` on the ten `ncp2-*` diagrams | Renderings in `png/` |

Not run: the gates, the Lean build, the Rust tests, the Zenoh binding, and every benchmark. The designs of section 2 are proposals; none of them is implemented or checked.

---

## 1. Architecture against the product

### 1.1 Is the split right?

For the exchange, yes. One small core, contracts that the applications own, features in `open`, feature operations, and two bindings give each adapter its own process, contract, and failure. A host composes sessions, and the composition test in the gate shows that an optional module never stops the loop. I would not reopen any of this.

The product boundary in `AGENTS.md` asks for more than that: independently selectable adapters, optional compositions, and declared profiles for many entities and several sensor modalities, with CREBAIN standalone, Prisoma for embodied-agent and world-model experiments, and Engram optional.
Against that boundary, the split has three weak joints:

- **"Stream" is a pattern in name only.** Section 1 puts it beside the exchange. The exchange has a start, state, rules for both sides, eight properties, proofs, and a model check. The stream has section 6.3 and section 8.
- **"Profile" carries three different things:** rules for one kind of exchange (lockstep, rounds, and later authority), the missing half of the stream pattern, and the composition of a run.
- **"Binding" holds the only identity that exists,** and it never reaches the application (section 13.2: "NCP gives the application no identity of its peer").

A layer model that names all of it, with the owner of each layer:

| Layer | Defines | Owner | State today |
| --- | --- | --- | --- |
| Binding | Bytes, loss model, peer identity | NCP | Peer identity stops here |
| Frame | Bytes, digest or authentication code, attachments | NCP | Sound |
| Pattern | Exchange; stream | NCP | Exchange sound; stream thin |
| Profile | State that outlives sessions: clock, holder, lease, members; stream start, time, liveness | NCP | Two profiles, no common shape |
| Contract | Operations, stream types, shapes, reasons | Application | Identity sound; schemas unused |
| Composition | The programs, sessions, streams, keys, and profiles of one run | Deployment | Absent |

Two concerns cross the layers and have no owner yet: identity (who is the peer) and time (which clock a value refers to).

### 1.2 Where each consumer stands

| Consumer | Uses of NCP 2 that work today | Needs that have no NCP 2 design |
| --- | --- | --- |
| CREBAIN | The native simulation and the loop host over pipes [C, migration section 7] | Sensor streams for several modalities and up to 256 entities; commands under authority; a history identity for its checkpoint family; a local fan-out without Zenoh |
| Prisoma | Transcripts of loop runs | Streams of spikes and potentials; a run identity across transcripts; references by identity; branches of one world from a checkpoint |
| Galadriel | Transcripts of loop runs | A live subscriber with producer, epoch, sequence, modality, heartbeat, misses, and frame closure; an advisory stream that names its evidence |
| Haldir | None | A commander lease, feedback from the body, an age bound in transit, a stop path, trusted sensor state with time and position progression |
| Engram | An owner inside NEST, in the benchmarks | The plant commander under authority; nothing else in the core |

Two profiles unblock four consumers. That is the strongest argument for their order.

### 1.3 Structural gaps, ranked

**A1. HIGH. The stream pattern cannot carry the sensor and advisory families.** [C]

- No stream type on the wire (rule 8.4: "NCP does not say which stream type of the contract a message belongs to"). No check of a body against the schema of its stream type. No time. No liveness rule. No start that a late subscriber can read.
- A subscriber keeps a bounded table and forgets the stream that it used least recently (rule 8.3). `probes/stream_lru.py`: with four streams of state and five live streams, a replayed copy of an old first message is `accepted`, and loss counting starts again. The default limit is 1024 streams, which is 256 entities with four modalities.
- A key names a group (section 13.2). A monitor of possible sensor tampering cannot tell the publisher from another subscriber.
- Evidence: 17 vectors and 12 requirement lines; `formal/README.md` says "Sections 8 to 10 are tested, not modeled". No consumer, no fault campaign, no benchmark.
- Galadriel's own envelope shows what is missing: `declared_interval_ms`, `declared_deadline_ms`, `dropped_event_count`, a miss with a reason, a frame summary, and a modality name [C, `galadriel-monitor-envelope-v2.schema.json`].
- Recommendation: the stream profile of section 2.3, and section 6.3 and section 8 outside the freeze.

**A2. HIGH. No command pattern with authority, and no peer identity for the application.** [C]

- Section 13.1 leaves authority to applications. The migration plan, section 7, says that Haldir needs "a design of the Gate's commander lease over NCP 2, which has no authority machine".
- Neither SDK passes a peer to the `open` handler (no use of peer credentials or of the peer certificate in `python/ncp/binding.py`, `python/ncp/owner.py`, `rust/src/binding.rs`, `rust/src/owner.rs`).
- A frame has no key identifier, and after the freeze it cannot get one: the header is fixed, and an extra member is a bad frame. The address of the binding therefore selects the key for ever. State this as a rule: one service, or one stream key, for each key.
- Recommendation: the authority profile of section 2.4; pass the binding's peer to the `open` handler where the binding knows it.

**A3. HIGH. A profile has no fixed shape.** [C]

- Lockstep attaches with a feature, a feature operation, and body members. Rounds attaches with body members only. `ncp.ping` and `ncp.end` attach to nothing.
- No profile revision is on the wire. A lockstep client detects revision 4 by the presence of `term` (profile rule 3.4).
- No profile says what a transcript verifier checks. Section 10.3 checks the core only, so a recorder cannot check offline that ticks rise by one or that every agent got the same round record.
- The SDKs compose by wrapping. `python/ncp/lockstep.py`: "Use `Lockstep` as the outermost handler of the owner". `Rounds.owner()` builds its own `Owner` around a private handler, so rounds cannot run with lockstep or with a later authority handler.
- Recommendation: the common rules of section 2.1.

**A4. MEDIUM to HIGH. Nothing names a run or a composition.** [C]

- `run` is an optional string of an `open` request. A stream message has none. A transcript header has none.
- A recorder that holds five transcripts cannot show from the files that they are the complete record of one declared composition.
- Recommendation: a composition document with an identity, like a contract: its programs, services, stream types by entity and modality, contract identities, required features with revisions, and which modules are optional. `run` carries that identity, the stream start carries `run`, and the transcript header gets `run`. This needs no change of the core. It needs one sentence before the freeze: a verifier ignores members of the transcript header that it does not know. Both verifiers already do [C, `python/ncp/transcript.py:233`, `rust/src/transcript.rs:293`]; the specification is silent.

**A5. MEDIUM. The first consumer built the profile features in its own contract.** [C]

- `crebain.body.v1.json`, operation `step`: `tick_index` ("the next step, one more than the last"), `source_state_digest` ("it must equal the owner's current state digest"), and `proposals` ("for each controller response that this step applies, its identity"). `prepare` has `sensor_available` and `actuator_available`.
- These are the tick and state of the lockstep profile without the holder and the recovery, references by identity, and availability. All are described in English; the contract has no `ncp.schema`.
- Why it matters: the profile and the consumer now solve one problem twice, and only the consumer's version runs. The world of CREBAIN is the natural first consumer of lockstep. Its `proposals` are the first use of the deferred `ncp.refs`.

**A6. MEDIUM. No time base.** [C]

- The only times in NCP 2 are the record times of a transcript. Section 8: "Freshness and rate limits belong to the stream's contract", in members that NCP does not read.
- A lockstep tick counts steps. It carries no simulated time and no link to a stream.
- Recommendation: `ncp.t` and a declared clock in the stream profile, and a clock kind `tick` that names the history of a lockstep owner (sections 2.3 and 4.1).

**A7. MEDIUM. A third party cannot observe an exchange while it runs.** [C, section 9]

- Transcripts exist after the run. Haldir's authority graph expects "accepted/applied evidence" from the plant.
- Recommendation: an applied-evidence stream that the owner publishes: for each admitted request its identity, the identity of the response, the outcome, and the clock. It carries identities, not bodies. Define it after the stream profile.

**A8. MEDIUM. The evidence is where the product is not.** [C, `KNOWN_LIMITATIONS.md`, release record]

- The fault campaign and the benchmarks ran on revision 2 over reliable byte streams. The Zenoh binding has no campaign. One author wrote everything.

**A9. LOW to MEDIUM. Streams have no local fan-out.** [C]

- Rule 9.1.10 lets one connection carry streams in one direction. No rule says how a subscriber on the same computer finds and joins a stream without Zenoh. CREBAIN standalone needs that. Section 2.3 gives the announcement an address for it.

**A10. LOW. The schema subset cannot express the consumers' shapes.** [C]

- Section 11.1 has no `anyOf`, no `allOf`, and no named definitions. Galadriel's envelope uses all three. A consumer keeps its full schema in its application, which is acceptable; say so in section 11.

### 1.4 The shortcomings that matter most

1. **The parts that the remaining consumers need are the parts without a design** (A1, A2). Until they exist, four consumers stay on NCP 1, and the NCP 1 code and its advisories stay on the main branch.
2. **Profiles have no common shape and no revision** (A3). This is cheap to fix today and expensive after the first profile consumer.
3. **A verdict of the lockstep profile is false about history after a restore** (section 4.1). CREBAIN's checkpoint family, today on NCP 1, restores checkpoints by design.
4. **The evidence is old and on the easy binding** (A8). The README's correctness numbers describe revision 2.
5. **No run identity** (A4). It decides whether Prisoma can check a composition or only single files.
6. **One author** (A8). Each outside look still finds defects in the newest part.

---

## 2. The next profiles

All three designs keep the frame format, the messages of section 6, and the owner and client rules of section 7. Member and operation names are proposals.
Text in a code block is a wire example. Each design is unimplemented and unchecked.

### 2.1 Rules that every profile should follow

Put these into section 17 of the specification, or into each profile, before a profile has a consumer.

1. **Revision on the wire.** The client's feature parameters list the revisions that it speaks, `{"rev": [4]}`, and the owner's parameters name one, `{"rev": 4, ...}`. An owner that speaks none of them does not enable the feature. Lockstep rule 3.1 already lets an owner ignore members of the client's parameters, so a revision-4 owner accepts this request.
2. **`open` reads.** Rule 7.1.8 has it. Every change of state that outlives a session is a feature operation.
3. **State across sessions has a history.** A profile names the state that outlives sessions and says what a restart does to it (section 4.1).
4. **Reasons.** A profile registers the reasons of its declines (section 2.2).
5. **Verification.** A profile says what a transcript verifier checks: for lockstep, that ticks rise by one, that each step answers the state of the response before it, and that `ncp.tick.request` is the identity of the request.
6. **One holder machine.** Lockstep has a holder with a term. The authority profile needs the same machine with a deadline and a token, and rounds needs it for each member. Specify and model check it once: an opening takes with a request that names the owner's term; the owner identifies the holder by its opening.
7. **SDK.** The owner object runs an ordered list of profiles around the application and owns the lock and the release. A profile is then a set of pure functions, as `ncp.owner.step` is, and the model checks drive the same functions.

### 2.2 Decline reasons that programs can read

**Problem.** `declined` has two codes. Lockstep uses `body_invalid` for four refusals by state, and a client tells them apart by the presence of the member `ncp.lockstep`. Rounds uses `body_invalid` for eight causes with free text only [C, `probes/rounds_lost_response.py`: body members `['detail']`].

**Wire members.**

| Member | Value |
| --- | --- |
| Code `conflict`, outcome `declined` | The request is well formed. The owner's state does not permit it. It never executes. |
| `ncp.reason` in the body of a `declined` response, and of a `rejected` response to `open` | A reason name, in the format of an operation name. A name that starts with `ncp.` belongs to this specification or to a profile: `ncp.<profile>.<name>`. Every other name belongs to the application. |
| `ncp.<profile>` in the same body | An object with the facts that the client needs for a request that can succeed, for example `{"term": 9}` or `{"next": 42}`. |
| `ncp.reasons` in an operation of a contract | Optional. An array of the application reasons that the operation can give. The contract identity then covers them. |

```text
{"outcome": "declined", "code": "conflict",
 "body": {"detail": "holder: this opening does not hold the ticks; send ncp.lockstep.take",
          "ncp.reason": "ncp.lockstep.holder", "ncp.lockstep": {"term": 9}}}
```

**Owner rules.**

1. A handler declines with `body_invalid` or `conflict`, and with a reason. It can give no other code.
2. `body_invalid` means that no state of the owner accepts this body. `conflict` means that another state would.
3. If the members do not fit the session bound (rule 7.3.12), the owner leaves out `ncp.reason` last.
4. The response is kept as every `declined` response is. Its reason never changes.

**Client rules.**

1. A client acts on the outcome, then on the code, then on `ncp.reason`. It treats a reason that it does not know as the code alone. It MUST NOT act on `detail`.
2. No reason changes a verdict. A declined request did not execute and never will, whatever its reason. A reason only tells the client what it can send next.

**Registry.** `spec/ncp2-rules.json` gets the code and a list of reasons for each profile. `scripts/check_ncp2_rules.py` compares it with the profile texts and both SDKs.

| Profile rule | Code | `ncp.reason` | Facts |
| --- | --- | --- | --- |
| Lockstep 5.2, body; 5.4, body | `body_invalid` | none | none |
| Lockstep 5.2, term | `conflict` | `ncp.lockstep.term` | `{"term": E}` |
| Lockstep 5.2 and 5.4, largest value | `conflict` | `ncp.lockstep.limit` | none |
| Lockstep 5.4, holder | `conflict` | `ncp.lockstep.holder` | `{"term": E}` |
| Lockstep 5.4, tick | `conflict` | `ncp.lockstep.tick` | `{"next": T + 1}` |
| Lockstep 5.4, state | `conflict` | `ncp.lockstep.state` | none |
| Lockstep 5.6, other feature operation | `unknown_op` (today `body_invalid`) | none | none |
| Rounds 4.1.1 | `body_invalid` | none | none |
| Rounds 4.1.2 to 4.1.4 | `conflict` | `ncp.rounds.member` | none |
| Rounds 4.1.5 | `conflict` | `ncp.rounds.excluded` | `{"missed": K}` |
| Rounds 4.1.6 | `conflict` | `ncp.rounds.round` | `{"next": K + 1}` |
| Rounds 4.1.7 | `conflict` | `ncp.rounds.stopped` | `{"failed": K}` |
| Rounds 4.1.8 | `conflict` | `ncp.rounds.duplicate` | none |

**Failure semantics.** Nothing new: a declined request is admitted, kept, and final. An owner of revision 6 sends neither member. A client of revision 6 acts on the outcome of a code that it does not know (section 7.5), and the Python client passes any `declined` code through [C, `python/ncp/client.py`, `receive`]. A lockstep client of revision 4 reads `ncp.lockstep` whatever the code [C, `python/ncp/lockstep.py`, `step` and `take`]. The member name has the reserved prefix (section 15, rule 2), so no application body can hold it with another meaning.

**Model check.**

- `model/simulate.py`: give the application a verdict that depends on its state, with `conflict`. Add the mutant `conflict_not_kept`; property 5 must catch it, not progress.
- `model/lockstep.py`: a property "each reason is true": when the owner sends `ncp.lockstep.holder`, the opening is not the holder at that instant, and so on for each reason. Let the client program branch on reasons. Mutants: a wrong reason; a missing fact.
- Vectors: one owner scenario with `conflict`; client vectors with an unknown code and an unknown reason.

**Risks.**

- Reasons grow without a limit and become a second code space. The registry and `ncp.reasons` in the contract bound them.
- Applications use `conflict` for invalid bodies. The harm is small: both mean "not executed".
- A client retries on a reason in a loop. Keep the limit of three takes as a pattern for every profile.

### 2.3 A stream profile for sensors and advisories

**Scope.** A publisher program owns one or more streams. It is also the owner of an exchange service that announces them. The profile adds a type, a start, time, liveness, loss reports, references, and anchors. It does not define units, frames of reference, or fusion: those stay in contracts.

**Wire members.** The stream message of section 6.3 does not change.

| Where | Member | Value |
| --- | --- | --- |
| Stream identifier | `T/E/I` | `T`: a stream type name of the contract. `E`: the source, one or more chunks joined by `/`, for example `uav1/cam0`. `I`: the instance, 16 or more lowercase hexadecimal characters, new for each start (rule 8.2). `T` and `I` contain no `/`, so the split is exact. |
| Contract, stream type | `ncp.stream` | `{"deadline_ms": D, "period_ms": P or null, "clock": "sim", "mono", "utc", or "tick", "unit": "ns", "us", "ms", or "tick", "max_frame": B}`. The contract identity covers it. |
| Message 1, body | `ncp.start` | `{"rev": 1, "run": R or null, "origin": "simulation", "physical", or "replay", "deadline_ms": D, "period_ms": P, "clock": {"kind": ..., "unit": ..., "history": H or null}}`. The body has no other member. The identity of this message is the **root** of the stream. |
| Data message, body | `ncp.t` | An integer: the capture time on the stream's clock. Required in every data and void message. |
| Data message, body | `ncp.dropped` | Optional. The number of samples that the publisher discarded, without a number, since its last message. |
| Any body | `ncp.refs` | Optional. At most 64 references: `{"stream": S, "seq": N, "identity": I}` or `{"request": I}`. |
| Void message, body | `ncp.void` | `{"reason": NAME}`, with `ncp.t`: a sample was due, and the source has none. The message is never a value. |
| Alive message, body | `ncp.alive` | `{}`: nothing was due. `ncp.t` is optional and then says that no later message has an earlier time. |
| End message, body | `ncp.end` | As section 8, rule 12. |
| Feature | `ncp.streams` | In an exchange session with the publisher program. Report: `{"rev": 1}`. |
| Feature operation | `ncp.streams.list` | Body `{"type": T, "source": PREFIX, "stream": S, "after": CURSOR}`, each optional. Result `{"streams": [...], "next": CURSOR or null}`. |
| One entry of `streams` | | `{"stream": S, "root": I1, "last": {"seq": N, "identity": IN}, "ended": false, "at": {"binding": "zenoh", "key": "ncp/s/T/E"}}`. For a local stream: `{"binding": "unix", "path": P}`. |

```text
stream "camera.thermal/uav1/cam0/5f0c9a2e7b1d4c88"
seq 1:  {"ncp.start": {"rev": 1, "run": "8c1f...", "origin": "simulation", "deadline_ms": 200,
                       "period_ms": 50, "clock": {"kind": "tick", "unit": "tick", "history": "a3..."}}}
seq 2:  {"ncp.t": 41, "image": {"ncp.array": {"dtype": "u16", "shape": [120, 160], "att": 0}}}
seq 3:  {"ncp.t": 42, "ncp.void": {"reason": "no_measurement"}}
seq 4:  {"ncp.alive": {}}
```

**Publisher rules.**

1. Each start has a new instance. Message 1 is the start.
2. While the stream has not ended, the publisher sends at least one message in each interval of `deadline_ms`: an alive message if it has nothing else.
3. `ncp.t` never decreases in a stream.
4. A publish never blocks the program. If the binding cannot take a frame, the publisher discards the sample before it numbers it and counts it in `ncp.dropped` of its next message. On Zenoh, it puts with the congestion control that drops.
5. It keeps the root and the `seq` and identity of its last message for `ncp.streams.list`.
6. `origin` is true. A tool that plays a recording publishes a new instance with `origin` `replay`.
7. All frames of its streams carry the publisher's key. The session of `ncp.streams.list` carries the key of the pair of publisher and subscriber.

**Subscriber rules.** They apply after rule 8.5 and replace the unconditional acceptance of rule 8.6.

1. **Announced streams only.** The subscriber accepts a message only if the last list result names its stream as not ended. Every other message is `unannounced` and not accepted. A start of an unannounced stream MAY make the subscriber list again, at a limited rate.
2. **One instance for each type and source.** A newer announced instance replaces the older one, which is never accepted again. The subscriber needs no table of old instances.
3. **No forgetting.** The subscriber fixes its capacity when it subscribes. It refuses a list that exceeds it. It never forgets a live stream.
4. **Type and shape.** The subscriber checks the body against `ncp.schema.body` of `T`. A body that fails counts as received for the chain, is reported as `invalid`, and is not delivered.
5. **Start.** A message with `seq` 1 is accepted only if it is a start and its identity is the announced root. A start with a revision or an `origin` that the subscriber does not know is not accepted.
6. **Time.** A message whose `ncp.t` is less than that of the last accepted message is reported as `time_conflict` and not delivered.
7. **Liveness.** If the subscriber accepts no message of a stream for `deadline_ms` on its own clock, it reports `silent`. The application MUST then treat the last value as stale. The next accepted message reports `resumed`.
8. **Anchors.** A list result gives `last` for each stream. If the subscriber accepted that `seq` with another identity, it reports `forged`. If the identities are equal, every message that chains to it without a gap is anchored.
9. **Not a value.** The subscriber never delivers a void, alive, start, or end message as a sample.
10. **Origin.** A subscriber that needs physical data refuses every other `origin`.

A subscriber that cannot reach the announcement, such as a passive recorder, applies section 8 with rules 4, 6, 7, and 9, and marks everything that it accepts as unanchored.

**Bindings.**

- Zenoh: the key is `ncp/s/T/E`, without the instance and without wildcards (rule 9.2.5). The subscriber subscribes to exactly the announced keys.
- Byte stream: the address in `at` is a listener of the publisher. Each connection carries the streams from the next message on. The publisher closes a connection that does not keep up, and the subscriber sees a gap when it joins again.

**Failure semantics.**

| Event | The subscriber reports | The application |
| --- | --- | --- |
| Messages lost in the middle | `accepted` with the count | Knows exactly how many it missed |
| The last messages lost, or the publisher stalls | `silent` at the deadline | Treats the value as stale |
| The publisher discards samples | `ncp.dropped` in the next message | Knows the loss before the numbering |
| The source has no measurement | A void message | Never reads a zero as a value |
| The publisher restarts | `unannounced`, then a new instance after the next list | The old instance is never accepted again |
| An old stream is played again | `unannounced` | Nothing is delivered |
| A holder of the key inserts or changes a message | `forged` at the next anchor that covers it | Distrusts the segment since the last good anchor |
| The publisher's clock steps back | `time_conflict` | Nothing is delivered |
| More streams than the capacity | An error when it subscribes | No silent loss of state |

**Model check.** A file `model/streams.py` in the pattern of `model/simulate.py`. Make the subscriber a pure function of its state, one frame or one list result, and its clock.

- Actors: one publisher with start, data, void, alive, end, and a restart; the announcement as an atomic read of the publisher; a network that loses, repeats, reorders, and delays past the deadline; a replay of frames of an old instance; a holder of the key that changes or inserts a message; clocks as counters.
- Properties: T1, every delivered body is the body that the publisher sent at that `seq`, without the forger. T2, delivered `seq` and `ncp.t` never go back. T3, delivered plus lost plus invalid equals the span of accepted `seq`. T4, nothing of a replaced, ended, or unannounced instance is delivered. T5, a stream that the subscriber does not report as `silent` had an accepted message within the deadline. T6, the end is final. T7, a changed message that chains to an anchor is reported as `forged` at that anchor. T8, no void or alive message is delivered as a value. T9, no state of an announced stream is lost.
- Mutants: accept an unannounced stream; forget the least recently used stream; skip the `prev` check; count losses wrong by one; an alive message that does not restart the timer; a void as a value; an ignored anchor; an accepted earlier time; an end that is not final; a skipped schema check.
- The stream vectors grow by the new statuses and run against both SDKs.

**Main risks.**

1. **Scope.** The profile can grow into the 41 kB descriptor of NCP 1. Keep units, frames of reference, modalities, and fusion in contracts.
2. **Keys.** A shared key still lets a subscriber forge. Anchors detect it later; they do not prevent it. A consumer that acts on a sample at once needs one key for each pair, or a signature that its contract defines.
3. **Clocks.** `ncp.t` orders the messages of one stream. Two streams compare only if they name one clock: the same `history` for `tick` and `sim`, or `utc` with synchronised hosts.
4. **False `silent`.** A loaded computer delays messages. `silent` fails safe, but it can stop a loop. The contract must choose the deadline for the worst case, not the mean.
5. **Reach.** Anchors need an exchange path to each publisher program. A passive recorder has none.
6. **Two paths for one sample.** In a lockstep simulation, observations come in step results. Use the same body shape with `ncp.t` and `ncp.void` in both places, so that a consumer has one decoder.

**Staging.** Revision 1: the identifier, the start, `ncp.t`, alive, void, the list, and the subscriber rules 1 to 7, 9, and 10. Revision 2: anchors, `ncp.dropped`, and `ncp.refs`. Galadriel's `galadriel-ncp` is the first subscriber, and CREBAIN's world the first publisher.

### 2.4 An authority profile for commands

**Principles that the design keeps.** The body is the owner and the final actuator authority. It issues the lease and the freshness, on its own clock; a serialized lease grants nothing. The arrival of a frame never starts or extends a lifetime. An unknown value grants nothing. The profile defines no safe action: the body does. The stop request is a software request and no physical certification.

**Roles.** The body runs a command service with one commander, for example Haldir's Gate, and a stop service for each stop source. Each service has its own key (section 13.2).

**State of the body across sessions.**

| Member | Meaning |
| --- | --- |
| `history` | 32 hexadecimal characters, new when the body starts and after each reset (section 4.1). |
| `term` | Counts the acquisitions. |
| Holder, deadline | The opening that holds the lease, and the instant on the body's clock at which it ends. |
| `count`, `last` | The number of authority operations that the body applied in this history, and the identity of the last one. |
| `stopped` | The stop latch. |

**Wire members.**

| Where | Member | Value |
| --- | --- | --- |
| Feature | `ncp.authority` | Report, which changes nothing: `{"rev": 1, "history": H, "term": E, "held": true, "remaining_ms": N, "count": C, "last": R, "stopped": false, "lease_ms": [15000, 60000], "window_ms": W, "token": "hmac-sha256"}`. |
| Operation | `ncp.authority.acquire` | Body `{"term": E, "lease_ms": D, "token": {...}}`. Result: the clock after it, `{"history": H, "term": E + 1, "remaining_ms": D, "window_ms": W, "grant": G, "count": C, "last": R, "stopped": false}`. |
| Operation | `ncp.authority.release` | Body `{}`. The lease ends now. Result: the clock. |
| Operation | `ncp.authority.stop` | On a stop service only. Body `{}`. Result `{"stopped": true, "history": H}`. |
| Contract, operation | `ncp.authority` | `{}` marks an operation as an authority operation. The contract identity covers it. |
| Request of an authority operation | `ncp.lease` | `{"term": E, "valid_ms": V}`. |
| Its `ok` or `declined` response | `ncp.lease` | `{"term": E, "remaining_ms": N, "window_ms": W, "grant": G, "count": C}`. |
| Token | | `{"alg": "hmac-sha256", "kid": K, "mac": M}`, or `{"alg": "external", "kid": K, "att": i}` for bytes that the deployment verifies, for example a COSE signature of the Gate. |

The token covers these exact bytes, with no JSON in them: the text `ncp.authority.1`, one zero byte, the 32 bytes of the identity of this opening's `open` response, the term of the request as 8 bytes, and `lease_ms` as 8 bytes, both big-endian. The `open` response holds the nonce, the contract, and the report with the history, so the token names one opening of one body in one history.

```text
open response:   features {"ncp.authority": {"rev": 1, "history": "a3..", "term": 7, "held": false,
                           "remaining_ms": 0, "count": 311, "last": "5d0e..", "stopped": false, ...}}
acquire:         {"term": 7, "lease_ms": 30000, "token": {"alg": "external", "kid": "gate-1", "att": 0}}
  ok:            {"history": "a3..", "term": 8, "remaining_ms": 30000, "window_ms": 200,
                  "grant": "9b41..", "count": 311, "last": "5d0e..", "stopped": false}
set_velocity:    {"v_mm_s": [100, 0, 0], "ncp.lease": {"term": 8, "valid_ms": 100}}
  ok:            {"applied": true, "ncp.lease": {"term": 8, "remaining_ms": 29950, "window_ms": 200,
                                                 "grant": "07c2..", "count": 312}}
```

**Body rules.**

1. **One at a time.** From the check of an acquisition or an authority operation to the end of its execution, the body checks no other one. An acquisition waits for a running command. A stop does not wait: it sets the latch at once.
2. **Acquire, check, in this order.** The body shape (`body_invalid`). The latch (`ncp.authority.stopped`). The term, which must be the body's term (`ncp.authority.term`, with the term). `lease_ms` in the body's range (`ncp.authority.lease`). The token, which must verify with a known algorithm and name this opening, this term, and this `lease_ms` (`ncp.authority.token`, with no further detail). A live lease of another principal (`ncp.authority.held`, with the remaining time).
3. **Acquire, execution.** The opening becomes the holder, the term rises by 1, and the deadline is now plus `lease_ms`. The result is final for every other opening, as the clock of a lockstep take is.
4. **Command, check.** The body declines unless the opening is the holder (`ncp.authority.holder`, with the term), the term matches, the latch is open, the lease is live (`ncp.authority.expired`), the request arrives within `window_ms` after the body built the response that it acknowledges (`ncp.authority.late`), and `valid_ms` is at most the remaining time (`ncp.authority.validity`). Then the application checks the command against its own limits, with its own reasons.
5. **Command, execution.** The command counts as applied when the body starts to execute it. `count` rises, and `last` is the identity of the request. The body applies the command for at most `valid_ms`, and never past the deadline. After that it does what its own plant profile says.
6. **Grant.** Each `ok` or `declined` response to an acquisition or an authority operation carries `ncp.lease` with a new random `grant` of 128 bits. The identity of that response is then not predictable. The next request acknowledges it (rule 7.3.9), so the commander made that request after the body built the response. The age of a command at admission is therefore less than `window_ms` on the body's clock, without any agreement of clocks. The body declines, with `ncp.authority.late`, an authority operation that acknowledges a response without a grant: a commander keeps its reads and pings in another session.
7. **Stop.** The latch closes, the lease ends, and the body does what its plant profile says for a stop. The stop carries no values. The profile has no reset. A reset is an action of the deployment; it starts a new history and ends every session.
8. **Restart.** A body that restarts holds no session, no holder, and no lease. It draws a new history unless it restores `count` and `last` with the state that they belong to. The deployment states whether it starts stopped; the SDK has no default for that argument.
9. **`open` reads.** Accepting an `open` changes nothing (rule 7.1.8).
10. Other operations do not move an actuator.

**Commander rules.**

1. Acquire first. Check that the term is the term of the request plus 1.
2. **Local deadline.** Before each request, read the local clock: `t0`. After the `ok` response, treat the lease as live until `t0` plus `remaining_ms`, less a stated margin for the difference of clock rates, and no longer. The body computed the remaining time after `t0`, so the commander's deadline is never later than the body's.
3. After `late` or `expired`, acquire again in the same session with the term of the decline. After `stopped`, stop: do not acquire again without an action of the deployment.
4. **Recovery.** After a command that is possibly executed, open a new session with a new identifier and acquire. The verdict comes from that response only. `last` equal to the identity of the command: it was applied. `history`, `count`, and `last` equal to what the commander knew before the command: it was not applied and never will be. Anything else: possibly executed.
5. A stop source opens its session when it starts and keeps it alive with `ncp.ping`. A stop is then one round trip. If the session is gone, it opens a new one and sends the stop there.

**Failure semantics.**

| Event | Result |
| --- | --- |
| A command or its response is lost | Possibly executed. Recovery gives applied, not applied, or no verdict. A delayed copy is declined: the new opening holds the lease. |
| A command arrives late | Declined with `late`. The body never applies an old command. |
| The commander stops sending | The last command ends after `valid_ms`, and the lease at its deadline. |
| A copy of an `open`, of an acquisition, or of a token | Takes nothing: the acquisition and the token belong to one opening. |
| Two commanders | The term shows each takeover. Another principal cannot take a live lease. |
| The body restarts | A new history. No lease. The last command has no verdict unless the body restored `count` and `last`. |
| A stop | Every later acquisition and command is declined until a reset. |
| A token with an unknown algorithm, or no token | Declined. A body that accepts no token says `"token": "none"` in every report, and the SDK prints a warning. |

**What Haldir's Gate needs.**

| Need of the Gate [C, Haldir `docs/NCP-COMPATIBILITY.md`, `docs/AUTHORITY-GRAPH.md`] | In this profile |
| --- | --- |
| A lease with a term and an identity, 15 to 60 s, rotated after two thirds | Acquire again with the body's term. The identity of the acquisition request is the lease identity. No boot counter: the body issues the term. |
| "The body returns no authority feedback" | `ncp.lease` in every response |
| "no ... authenticated application acknowledgement" | The response, bound to the request by its identity and to the session by the chain |
| "no enforced in-transit age bound" | The grant and the window of body rule 6 |
| "a lost renewal could leave Gate holding a lease that the body had let lapse" | The acquisition has a true verdict, and commander rule 2 never overestimates |
| Journal states Called, UnknownAfterPublish, ReturnedError | A transcript record before the send; possibly executed with recovery; `declined` |
| "Gate output sequence allocated (never reused)" | `seq` and the hash chain of the session |
| The lease bound to the principal of the exclusive route | The token of the Gate's key over the identity of the `open` response |
| Trusted state with capture-time and source-position progression, and old source epochs as tombstones | The stream profile: `ncp.t`, `seq`, one instance for each source |
| Accepted and applied evidence from the plant | `count` and `last`; later the applied-evidence stream (A7) |
| The pin of epoch 22 | The tag, the revision of the profile, the SHA-256 of `spec/ncp2-rules.json`, and the identity of the body's contract, which every `open` checks on the wire |

Haldir's own authority stays outside NCP: signed intents, mission leases, admissions, revocations, and the policy.

**Model check.** A file `model/authority.py` on the structure of `model/lockstep.py`, with the holder machine of section 2.1 shared.

- Actors: one commander with `open`, acquire, two commands, and recovery; one stop source; a second principal as one fault; the body's clock as a counter with an event "the lease ends" and an event "the window ends".
- Faults: copies of every frame, loss, expiry of a session, a restart that keeps or loses `count` and `last`, a stop at any point, a late delivery.
- Properties: A1, a command is applied only in the holder's opening, under a live lease, inside its window. A2, nothing is applied after a stop in the same history. A3, each verdict of a recovery is true, in the strict form of section 4.1. A4, accepting an `open` changes nothing. A5, no copy of a frame takes the lease. A6, whenever the commander believes that the lease is live, it is live at the body. A7, a stop is admitted in every state of the lease. A8, another principal never takes a live lease. Progress without faults.
- Mutants: at least one for each property, among them a window that starts at arrival, a deadline that the commander counts from the receipt of the response, a token that does not name the opening, and a latch that an acquisition opens.

**Main risks.**

1. **Words.** "Stop" and "lease" invite safety claims. The text must say what `AGENTS.md` says: a protocol control, not a certified stop, and the body decides.
2. **Clocks.** A monotonic clock can stand still while a computer sleeps [S]. A lease would then outlive real time. The body needs a clock that counts suspended time, or it ends every lease when it resumes.
3. **Two leases.** Haldir has a mission lease, and NCP would have a commander lease. Name the NCP one by what it is: authority over one link to one body.
4. **Window tuning.** A window that is too short declines good commands under jitter, and each decline costs one acquisition. Report the window in the `open` report so that a commander can refuse a body that it cannot serve.
5. **One request at a time.** A command that takes long blocks the session. An authority operation must return when the body has accepted the setpoint, not when the motion ends.
6. **Token algorithms.** The Python SDK has only HMAC in its standard library. A signature needs code of the deployment. An unknown algorithm must decline.
7. **No consumer yet.** Write the profile with Haldir's adapter and CREBAIN's body as its two first users, and model check it before either depends on it. Lockstep shows the cost of an unchecked holder rule.

---

## 3. Tag scope

### 3.1 What a `2.0.0` tag should freeze

The rule that I propose: freeze a part only if it has vectors in both SDKs and also a proof, a model check, or a consumer. The reviews of revisions 4, 5, and 6 found no defect in the exchange, and each of them found defects in the lockstep profile or in its code. The core has converged; the rest has not.

| Part of the specification | Proposal | Reason |
| --- | --- | --- |
| Sections 3, 4, 5: frame, JSON region, attachments and arrays | Freeze | Vectors, differential fuzzing, every consumer |
| Sections 6.1 and 6.2: request and response | Freeze | As above |
| Section 7: the exchange, with `features` in `open` | Freeze | Lean claims, the model check, vectors, CREBAIN's loop |
| Section 9.1, rules 1 to 9: byte-stream binding | Freeze | The only binding with a consumer and a fault campaign |
| Section 10: transcripts | Freeze, after text item 1 below | Prisoma and Galadriel read them |
| Section 11 without 11.1: contract document and identity | Freeze | CREBAIN's contracts |
| Section 13.2, rules 1 to 4: where the authentication code sits, how a receiver checks it, and the keyed chain of a transcript | Freeze | Sections 3 and 10 name them, and a frozen frame leaves no other choice later |
| Sections 12, 14, 15, with rule 3 of section 15 | Freeze | Rule 3 is the hook that lets profiles change without the core |
| Sections 6.3 and 8, and rule 9.1.10: streams | Provisional | No consumer, no model; the stream profile decides whether the body is enough |
| Section 9.2: Zenoh binding | Provisional | No fault campaign, no benchmark, no consumer |
| Section 11.1: schemas | Provisional | No consumer contract has `ncp.schema`; the subset can need to grow (A10) |
| Section 13.1, rule 5 of 13.2 with the text on keys and principals, and 13.3: keys, principals, TLS | Provisional | Guidance; the Rust SDK has no TLS; the peer does not reach the application |
| Lockstep revision 4, rounds revision 2 | Provisional | Section 4 |
| Sections 16 and 18 | Informative | Not frozen and not provisional |

This is the recommendation of my revision-4 review, with two changes: section 13.2 is split, and rule 3 of section 15 is in the freeze.

### 3.2 Text that must go in before the freeze

After the tag, an erratum "changes no behavior". These items change what a conforming program may do, so they cannot wait.

1. Section 10.1: a verifier ignores members of the transcript header that it does not know. Both verifiers do; the text is silent. `run` and a key identifier can then be added.
2. Section 6.2: a client ignores members that it does not know in the body of a response whose outcome is not `ok`. `ncp.reason` and profile members can then be added.
3. Section 13.2: one key for each address. A frame has no key identifier, so the service key, the stream key, or the connection selects the key.
4. Section 17, or each profile: the revision of a profile in its feature parameters (section 2.1, item 1).
5. The status line of each provisional section and profile, with its own revision, and one table in the release record: version, revision of the core, revision of each provisional part.
6. Section 9.2: a later revision of the binding that a peer of this one cannot use takes another key prefix than `ncp/x/` and `ncp/s/`.
7. The supported platforms of the tag: Linux and macOS. Windows is not tested.

### 3.3 Is one version for several wire revisions acceptable?

Before the tag, with conditions. Revisions 2 to 6 all carry the version `2.0.0` and the implementation string `ncp-python/2.0.0` or `ncp-rust/2.0.0` [C, `python/ncp/owner.py:34`, `rust/src/owner.rs:23`]. CREBAIN pins `rev = "2e24ef5..."` with `version = "=2.0.0"` [C]. This works only while nothing is published and every consumer builds from a commit.
It already costs something: every `open` response and every transcript header that the consumers recorded says `2.0.0`, so a transcript cannot say which revision's rules made it.

- Now: put the revision into the implementation string, for example `ncp-python/2.0.0-rc.6`, and into pre-release package versions. The tagged commit then says `2.0.0`.
- After the tag: `2.0.0` means exactly one core, and the core has no further revision. A provisional part can change in a minor version, with its revision on the wire where a peer could be confused: the `rev` of a feature, the `rev` of a stream start.
- In the SDKs: state for each module whether it is frozen or provisional, in the README and in the API documentation. A consumer must not learn from a broken build that `Lockstep` was provisional.

### 3.4 Which NOT RUN gates matter most before the tag

Ranked for a tag of the core as in 3.1.

1. **The fault campaign on the tagged revision** (protocol 5: pipes, Unix domain sockets, TCP, both clients, both owners). The README's sentence "no false report of a step" describes revision 2, which had three truthfulness defects that the campaign could not see. Revisions 3 to 6 changed the owner and the client. This is the cheapest gate and the one whose absence a reader notices first.
2. **An implementation by another author, for the frozen parts only**: a decoder, an owner, and a client, run through `python -m ncp conformance`, the oracle traces, and the fuzzer. A freeze promises that the text alone is enough. Every outside look so far found text that said more or less than the code. The frozen core is small enough for this.
3. **One block of the comparison benchmark and of the NEST overhead on the tagged revision.** A check against a regression, and it lets the README name one revision.
4. **Both gates on Linux and macOS in hosted CI at the tagged commit**, recorded.
5. **An external review of the frozen sections.**
6. **Signatures, an SBOM, and provenance**: before the publication, not before the tag. A published crate cannot be replaced.

Not needed for this tag if their parts stay provisional: the fault campaign and the benchmark of the Zenoh binding, the model check of the rounds profile, and a consumer of streams, schemas, and the profiles. They become the gates of the minor version that freezes each part.

---

## 4. Remaining design flaws in the profiles

### 4.1 Lockstep revision 4

**L1. HIGH. After a restore, "did not run, and it never will" is given for a step that ran.** [C, probe and prototype]

- `probes/lockstep_restore.py`: the step for tick 2 executes, with an effect outside the state. The response is lost. The owner restarts and restores the saved clock of tick 1, exactly as rule 5.7 says. `recover()` returns `no`. Rule 6.5 then lets the client send the step again, and the outside effect happens a second time.
- The profile says so (section 7, "Restarts"): the verdict "describes the owner's current state". The model check accepts it with a weaker S1 for this fault: 230 verdict events in the gate's run are "did not run" for a step that ran [C, `prototype/baseline_f1.log`].
- Why it matters. NCP 2's first principle is a true verdict. The guide says that the client "learns whether its last step ran". CREBAIN restores checkpoints by design: its checkpoint family, today on NCP 1, serves "separately bound restored continuations" (README). For a body, the step has effects outside the state.
- The verdict mixes two questions. Is the effect of the step in the owner's state? The clock answers that. Did the step ever execute? After a restore, the owner cannot know.
- **Fix: a history identity in the clock.**
  - The clock is T, S, R, E, and H: 32 lowercase hexadecimal characters that the owner draws at random when it starts.
  - An owner MAY restore H with a saved clock only if no step started after that clock was saved. Otherwise it MUST draw a new one. The SDK draws a new one unless the application passes the old one.
  - Rule 6.5: "did not run" needs the whole clock that the client knew, H included. A clock that differs only in H gives no verdict: the state is the state that the step answered, so the client can send the step again, and the first request stays possibly executed in its records.
  - "Ran" is unchanged: the tick of the step and its identity as R. A restored state that holds the step still says so.
  - Optional: `parent`, `{"history": H0, "tick": T0}`, in the report after a restore. Prisoma can then record a tree of branches of one world, which a world-model experiment needs.
- **Evidence.** A prototype of 4 lines in `python/ncp/lockstep.py` and a model with the strict S1 (`prototype/sdk-history.diff`, `prototype/model-history.diff`). `LS.judge` needs no change, because it compares whole clocks. With one fault: 469,268 worlds, every property holds, no "did not run" for a step that ran, and the 230 events are "no verdict". The self-test detects 12 of 12 mutants. A judge that ignores the history is caught by S1 with the trace of the probe. If every restart draws a new history: 471,556 worlds, every property holds. All of this is on `904f87c`. The model of `4e5a6de` has an exact S4 excuse and 13 mutants, as the coordinator reports; the change must be made and run again on it, with one more mutant: a judge that ignores the history.
- The same member serves the authority profile (a body that restarts) and the stream profile (a clock of kind `tick`).

**L2. MEDIUM. No profile revision on the wire.** [C] A client detects revision 4 by the member `term`. Add `rev` (section 2.1).

**L3. MEDIUM. Four refusals by state share `body_invalid`.** [C] A decline for a wrong tick gives the next tick only in `detail`, which a client MUST NOT act on, so the client needs a take to learn it. Section 2.2 gives each refusal a reason and its facts.

**L4. MEDIUM. Every opening can take.** [C] The profile has no way to say that an opening may only read. A monitor with a defect takes the ticks from the stepping client, and the owner cannot refuse, because the application sees no peer. Fix: the report gets `"take": false` for an opening that the owner lets only read, by its service or by the peer of the binding. A take there is declined with `ncp.lockstep.reader`.

**L5. MEDIUM. The first consumer does not use the profile.** [C, A5] CREBAIN's world checks `tick_index` and `source_state_digest` in its own contract, without a holder and without recovery. Move it to the profile, or the profile stays without a consumer and the world stays without a verdict after a lost step.

**L6. LOW. A tick has no time.** [C] The clock counts steps. Nothing links it to simulated time or to a stream. The clock kind `tick` of the stream profile, with the history, is enough; the profile itself needs no time member.

**L7. LOW. No rules for a transcript verifier** (section 2.1, item 5).

**L8. LOW. Several stepping clients** take the ticks from each other, and recovery gives no verdict. The profile says so. The answer is the rounds profile, which is not ready (4.2).

### 4.2 Rounds revision 2

The profile was "found sound" in the review of revision 3 for what it claims. Its claims are narrow. For the product's many agents in one world, these are design flaws.

**R1. HIGH for use. No recovery.** [C, probe] A member whose response is lost has a request that is possibly executed. In a new session, the `open` response says nothing. The member learns that the round closed from the text "round 1 is not open; the next round is 2", and that its request was applied only because round 2 accepts it. It never gets its result of round 1. If the step failed (rule 4.8), every member is in this state, and the rounds stop for ever.

**R2. HIGH for use. No clock and no restart rule.** [C, `python/ncp/rounds.py`] The owner keeps the last closed round in memory. After a restart, rounds start at 1 with no excluded member, and no state digest tells a client that the world is another one.

**R3. MEDIUM. Members by first claim, under one key.** [C, rule 4.2; `Rounds(..., key=...)`] The first session that names a free member owns it. Every holder of the one key can be every member.

**R4. MEDIUM. Exclusion is for ever, and the deadline is not announced.** [C, rules 4.3 and 4.4] One late request excludes a member for the rest of the run. The deadline starts when the first request arrives, so a fast member starts the clock for a slow one. No response tells a client the deadline. For a world with bodies, the member's entity then stays in the world without a controller.

**R5. MEDIUM. The record has no identity and no chain.** [C, rule 4.5] NCP has no canonical encoding, so two agents cannot compare a record by a digest; they compare its members. No record names the record before it, so agreement on a run needs every record. Each response carries all identities: with 256 agents, about 12 kB in each of 256 responses in every round.

**R6. LOW. No feature, no revision, no reasons** (sections 2.1 and 2.2).

**R7. LOW. Time limits on the Zenoh binding.** [S] A request waits in the owner until its round closes. The Zenoh channel gives up after 4 s by default. A deadline near that limit ends sessions whose requests are still in the round. The profile does not say that the client's limit must exceed the deadline and the time of a step.

**R8. LOW. No model check**, as the release record says.

**A revision 3, in outline.** Make rounds the lockstep clock with members, and reuse the holder machine.

| Member | Value |
| --- | --- |
| Feature `ncp.rounds`, report | `{"rev": 3, "history": H, "closed": K, "id": IK, "deadline_ms": D, "misses": M}` |
| `ncp.rounds.join` | Body `{"agent": NAME, "term": E}`, and a token where members have principals. The opening becomes the member's holder; a newer opening of the member takes over. Result: `{"closed": K, "applied": {"round": k, "request": I} or null, "excluded": false}`. This is the verdict for a lost request. |
| `ncp.rounds.result` | Optional. The kept result of the member's last applied request. |
| Record | `{"round": K, "id": IK, "prev": IK-1, "missing": [...]}`; the list of agents and requests on request. |
| Round identity | `IK` is the SHA-256 of exact bytes: a tag, `IK-1`, K as 8 bytes, and for each applied member in member order its index as 4 bytes and the 32 bytes of its request identity. `I0` covers the history and the member list. |
| Miss rule | A member is excluded after M misses in a row. Until then the world applies its own behaviour for that entity, and `missing` names it. |

One 32-byte value then commits to every request of the run. Each agent can compute it from its own records, and two agents agree on a run when they compare one value. A response no longer grows with the number of agents.
Model check before a consumer: two members, two rounds, the deadline as an event, a lost session, a restart. Properties: one record for all, an order that does not depend on arrival, each request applied at most once, a true verdict from the join, and no member excluded by another member's speed.

---

## 5. Figures

I rendered the ten `ncp2-*` diagrams (`png/`). `ncp2-verdicts`, `ncp2-ladder`, and `ncp2-lockstep` are in and carry the pill `REVISION 6`. `ncp2-bindings`, `ncp2-transcript`, and `ncp2-outcomes` still have the designs that my revision-4 review described. The renderings are of `904f87c`; the note on a rejected `open` that `4e5a6de` adds to `ncp2-verdicts` is not in them. The repository has no NCP 2 figure of the ecosystem, of the layers, or of the evidence.
All new figures come from `scripts/gen_diagrams.py`, in both themes, with the revision pill read from `spec/ncp2-rules.json`.

### 5.1 Misleading or stale

| Figure | Problem | Change |
| --- | --- | --- |
| `ncp2-lockstep` | The heading "A lost step gets one verdict, and it stays true" is stronger than the profile: no verdict with a second client, and "did not run" after a restore (L1) | Heading: "A lost step gets a true verdict, or none". Add a third result card: "The owner restored an earlier state: no verdict". With the history member, the card is exact |
| `ncp2-bindings` | Six cards of prose; links, a pattern, and a profile on one level; no lockstep; no pill | Replace with figure 2 below |
| `ncp2-transcript` | It draws the session chain with arrows forward in time. It does not draw the file | Redraw as specified in the revision-5 consult, figure (d): the file, one record, two chains with arrows that point backward |
| `ncp2-outcomes` | Its eight event cards repeat the table above it and the new verdict map | Keep the four outcome cards; remove the eight; let `ncp2-verdicts` follow |
| `ncp2-why` | A table as a picture beside the same table in Markdown; sixteen cells say "Not built in" | Remove from the guide, or redraw with one row for what the others have and NCP 2 lacks |
| `system-map`, `evidence-ladder` in the README | NCP 1 figures below the NCP 2 section, without "NCP 1" in the title | Label them |
| All benchmark plots | They show revision 2 and do not say so inside the figure | "SDK revision 2" in the subtitle, until they run again |

### 5.2 New figures

**1. `ncp2-ecosystem`: who uses what.** For the README, next to `ncp2-call`.
- Content: CREBAIN, Prisoma, Galadriel, Haldir, and Engram as boxes. Solid lines for what runs on NCP 2 today (loop host to world and controllers; transcripts to Prisoma and Galadriel). Dashed lines for what is on NCP 1 (sensor streams, advisories, commands, the Gate). Each line names its pattern: exchange, stream, transcript.
- Source: migration plan, section 7. Note: "Each program can run without the others."
- Alt text: which programs talk over NCP 2 today, over which pattern, and which five paths still use NCP 1.

**2. `ncp2-layers`: what NCP defines.** For the guide, in place of `ncp2-bindings`.
- Content: the six layers of section 1.1 as a stack: binding, frame, pattern, profile, contract, composition. Beside each: who defines it, and where it is checked (vectors, Lean, model check, tests). Under the stack, a small topology: one client with a pipe, a socket, and a Zenoh service; one publisher with two subscribers.
- Alt text: six layers from the bytes of a link to the composition of a run; NCP defines the lower four.

**3. `ncp2-openings`: why a rejection means "possibly executed".** For the guide and the publication.
- Content: a time line. A step runs in opening 1. The owner restarts. A delayed copy of `open` makes opening 2 with another nonce. The client's copy of the step gets `ack_mismatch`. Two chains in two colours, joined by nothing.
- Source: rules 7.1.5 and 7.6.4, design decisions 18 and 19. This is the rule that readers find hardest, and the model check found it.
- Alt text: two openings of one session name have two nonces and two chains; a step of the first is rejected in the second, and the client cannot know whether it ran.

**4. `ncp2-evidence`: which claim has which evidence.** For the README and the publication.
- Content: a matrix. Rows: the eight properties, the byte-stream binding, the Zenoh binding, streams, transcripts, lockstep, rounds. Columns: proof, model check, vectors, fault campaign, benchmark, consumer. Each cell: the revision, or "none".
- Source: `conformance/requirements.json`, `formal/README.md`, `model/README.md`, the release record.
- Alt text: the exchange has every kind of evidence; the campaign and the benchmarks are of revision 2; streams, the Zenoh binding, and rounds have the least.

**5. `ncp2-scope`: what the tag freezes.** For the release record and the README, once the owner decides.
- Content: the sections of the specification as tiles in two groups, frozen and provisional, each provisional tile with its revision.
- Alt text: the sections that `v2.0.0` freezes and those that can change in a minor version.

**6. `ncp2-rounds`: one round.** For the guide.
- Content: three agents and one owner on a time line; one deadline; one member that misses; the same record on three responses.
- Alt text: each round applies its requests in member order and gives every agent the same record.

**7. `ncp2-security`: what each link protects.** For the guide.
- Content: section 13.1 as a drawing: for each binding, who can read, who can send, and what protects. A mark where a key changes the answer, and the sentence "a key names a group, not one program".

**8. With each new profile.**
- `ncp2-reasons`: outcome, then code, then reason, as a short decision path with one lockstep example.
- `ncp2-stream`: the life of one stream: start, data, a void, an alive, a gap, `silent`, a restart with a new instance, and one anchor.
- `ncp2-authority`: the Gate and the body on a time line: `open`, acquire with the token, two commands with remaining time and window, a late command that is declined, the end of the lease; the stop service beside it.

### 5.3 The publication

`docs/publication/ncp-system-design.tex` is an NCP 1 document: 15 figures, no NCP 2 section [C]. A paper on NCP 2 needs its own set. I propose seven, each at one-column width with at most 40 words inside:

1. The session as one hash chain, from `ncp2-call`.
2. The owner's checks as a state diagram, from `ncp2-ladder`.
3. The verdict map, from `ncp2-verdicts`.
4. The second opening (figure 3 above).
5. Lockstep recovery with the three results: ran, did not run, no verdict.
6. The evidence matrix (figure 4 above), with the sizes of the model checks and the mutants for each property.
7. The measurements: the `integrity` plot and the NEST overhead plot, run again on the tagged revision, with the revision in the caption.

---

## 6. Order of work

1. **Before the tag.** The text items of 3.2. The implementation string with the revision. The fault campaign and one benchmark block on the tagged revision. The heading of `ncp2-lockstep`.
2. **Tag the core** as in 3.1.
3. **Lockstep revision 5:** the history identity (L1), `rev`, reasons, the reader report (L4). Then CREBAIN's world as its first consumer (L5).
4. **Decline reasons** in the specification, the rules data, both SDKs, and the vectors (2.2).
5. **Stream profile revision 1** with its model check; Galadriel's `galadriel-ncp` and CREBAIN's world as first users (2.3).
6. **Authority profile revision 1** with its model check; the peer of the binding in the `open` handler; CREBAIN's body and Haldir's adapter with its epoch 22 (2.4).
7. **Rounds revision 3** with a model check, when a consumer needs many agents in one world (4.2).
8. **The composition document and `run`** (A4), when Prisoma checks a run across transcripts.
9. **The Zenoh campaign and benchmark**, then the freeze of section 9.2, the streams, and the profiles that have consumers.

---

## 7. What I checked and found sound

- **The exchange.** I found nothing to reopen: exact-byte identities, the acknowledgement in the next request, `declined`, the nonce of an opening, feature operations, and the rule that `open` reads.
- **The acknowledgement gives more than at most once.** A request that acknowledges a response was made after that response. The authority profile uses this for a bound on the age of a command.
- **`LS.judge` compares whole clocks.** A new member of the clock, such as the history, needs no change of the verdict code [C, prototype].
- **The gate's lockstep check reproduces at `904f87c`:** 469,268 worlds with one fault [C].
- **The Python client acts on the outcome of any `declined` code** [C, read], so a new code needs no change of a revision-6 client.
- **Both transcript verifiers accept unknown header members** [C, read].
- **The documents state their limits.** The profile's section 7 names the restore case; the release record names each gate that is NOT RUN.

---

## Files of this review

All in `<reviews>/2026-11-16-design/`.

| File | Content |
| --- | --- |
| `design-review.md` | This report |
| `design-draft.md` | The working draft, with every checkpoint |
| `probes/lockstep_restore.py`, `rounds_lost_response.py`, `stream_lru.py`, and their logs | The three probes. Each takes the path of the SDK's `python` directory |
| `prototype/sdk-history.diff`, `prototype/model-history.diff` | The history identity in the lockstep SDK and in the model. Evidence for the design, not a patch for the repository |
| `prototype/lockstep_model_with_history.py`, `prototype/lockstep_model_baseline_counters.py` | The two model files. Each expects the SDK in `../python` |
| `prototype/*.log` | The runs: baseline, history, self-test, the mutant, and a new history at every restart |
| `png/` | Renderings of the ten `ncp2-*` diagrams at 1000 px |
