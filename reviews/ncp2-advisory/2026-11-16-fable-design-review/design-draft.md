# NCP 2 design review of 16 November 2026: working draft (checkpoints)

Reviewer: advisory language model, read-only. Non-normative. Cannot certify security, safety,
interoperability, scale, or release readiness.
Subject: `.ncp2-hardening` at `904f87c` (= `origin/main`), specification revision 6 (`28fb8cc`),
lockstep profile revision 4, rounds profile revision 2.
Final report goes to `design-review.md` in this directory.

## Checkpoint 1 (documents group A read: spec, both profiles, design record, migration, shortcomings, known limitations, release record, guide, README top)

### Facts noted (so that work can resume from this file)

- Spec §1 names two patterns: exchange and stream. Exchange has a complete state machine (§7), 8
  properties, Lean + model checks. Streams (§8) are 12 subscriber rules + §6.3 message; no
  publisher state machine, no announcement, no liveness, no time, no type name on the wire (§8.4
  says "NCP does not say which stream type of the contract a message belongs to").
- Profiles (§17): rounds (rev 2, Python only, no model check, no feature negotiation - uses a body
  member `ncp.round` without an `open` feature) and lockstep (rev 4, both SDKs, model check with 12
  mutants, uses feature `ncp.lockstep` + feature operation `ncp.lockstep.take`).
- Feature operations (§15 rule 3): `F.N` with F starting `ncp.`; go to the profile, not the
  contract; `declined/unknown_op` when the feature is not enabled.
- `declined` codes: only `unknown_op` and `body_invalid`. Lockstep overloads `body_invalid` for
  "not the holder", "wrong term", "wrong tick", "wrong state" and disambiguates by presence of the
  member `ncp.lockstep` in the declined body. Rounds overloads `body_invalid` for 8 causes with
  only `detail` text (and the lockstep spec says a client MUST NOT act on `detail`).
- §13.2: a key names a group; NCP gives the application no peer identity. §13.1: "Applications
  that need authority for physical actions add their own signed authority".
- Migration §7: the remaining NCP 1 users share wire-1.0 message families (sensor streams,
  advisories, commands); they move together once NCP 2 contracts or profiles exist. Haldir needs
  an epoch-22 transition and "a design of the Gate's commander lease over NCP 2, which has no
  authority machine".
- Migration §8 open work: (1) lockstep take - done in rev 6; rounds has no model check;
  (2) decline reasons; (3) stream profile; (4) authority profile; (5) Zenoh fault campaign and
  benchmark, campaigns on tagged revision; (6) principal convention - text done, passing binding
  peer to the application open.
- Release record gates: NOT RUN = benchmarks/fault campaign on tagged revision; Zenoh fault
  campaign; Zenoh benchmark; a consumer of streams / Zenoh / schemas / authenticated frames /
  feature operations / each profile; rounds model check; other-author implementation; external
  review; signatures/SBOM/provenance. OPEN = what the tag freezes.
- Known limitations (NCP 2 block): SDKs not proved; bounded model checks (4 calls, 2 faults;
  lockstep 2 steps, 3 sessions, 1 fault in gate); one author; evidence of revision 2; no TS SDK;
  Rust has no TLS for TCP and no rounds; Windows untested; no session resume; streams no delivery.
- Consumers on NCP 2 today: CREBAIN native sim + NEST controller (exchange over byte stream,
  rev 4 pin), Prisoma loop capture (transcripts), Galadriel local adapter (assesses loop runs).
  None uses streams, Zenoh, schemas, HMAC, feature ops, lockstep, or rounds.
- Lockstep §7 "Restarts": a step that ran before a restart to an older clock shows as "did not
  run" - verdict describes the owner's current state. This is the question-4 topic (history
  identity).
- Rounds: members fixed at start; excluded forever; no recovery for a possibly-executed round
  request; no feature negotiation; timing-dependent admission; record is per-round only (no chain
  between rounds).

### Early observations to test against the code and earlier reviews

1. The product boundary in AGENTS.md says "many entities and multiple sensor modalities",
   "independently selectable adapters", "optional compositions", "declared profiles". NCP 2's
   spec has no notion of entity, modality, adapter, or composition. The split
   exchange/profiles/bindings covers the *exchange* well; the *stream* half is a frame format plus
   subscriber rules without a session, a contract check that binds publisher to subscriber
   ahead of time, or a "declared profile" mechanism (features exist only in `open`).
2. Profiles have two different attachment mechanisms (feature at `open` for lockstep; ad hoc body
   members for rounds). A third (streams) has none. There is no profile registry/versioning: the
   feature name `ncp.lockstep` does not carry the profile revision; revision is detected by
   member presence (`term`).
3. Authority: spec says by-design out of scope, but migration §8 item 4 plans an authority profile.
   The principal problem (no peer identity to the application) is the structural gap for it.

## Checkpoint 2 (earlier reviews read; code read: stream.py, rounds.py, lockstep.py, Zenoh binding outline; NCP 1 proto families; Haldir and Galadriel needs)

### Inputs read
- `2026-11-14-rev4/fable-review-rev4.md` (D1-D12, S1-S7; section 4.3 stream sketch; 4.4 authority sketch).
- `2026-11-14-rev5/fable-consult-rev5.md` (R1-R5; take design; model plan; figures a-d).
- `2026-11-15-rev6/opus-review-rev6.md` head; `2026-11-16-rev6-verify/*` (SDK defects under repair: NOT my scope).
- Haldir `origin/main` `221c045`: `docs/AUTHORITY-GRAPH.md`, `docs/NCP-COMPATIBILITY.md` (read through git objects).
- Galadriel `origin/main` `20ddc41`: `crates/galadriel-ncp` lib head and monitor envelope v2 schema outline.
- NCP 1 `proto/ncp.proto`: StreamPosition, AuthorityLease, SensorFrame, CommandFrame, ControlStatus, LinkStatus.

### Facts that the designs must serve
- Haldir Gate conjunction needs: lease id/term, lease remaining time > 0, trusted state within an age
  bound and admitted "through strict capture-time and source-position progression (prior source
  epochs retained as non-evicting tombstones)", Gate output sequence never reused, journal states
  Called / UnknownAfterPublish / ReturnedError, "no enforced in-transit age bound or authenticated
  application acknowledgement" today, lease interval 15-60 s with rotation at two thirds, terms
  from a durable boot counter, plant returns "accepted/applied evidence" (future).
- Galadriel sidecar needs: producer id, epoch, sequence, modality enum (visual, thermal, acoustic,
  radar, lidar, radiofrequency), heartbeat with declared_interval_ms and declared_deadline_ms,
  queue health with dropped_event_count (publisher-side loss), modalityMiss with reason
  (no_measurement, ...), frame summary (closure across modalities), registry digest.
- NCP 1 SensorFrame/CommandFrame carried: stream epoch+seq, session generation, publisher local
  monotonic t, frame_id, source StreamPosition (command -> driving sensor frame), ttl_ms,
  AuthorityLease on every Active command, Mode (only ACTIVE authorizes; unknown mode = HOLD).
- KNOWN_LIMITATIONS (NCP 1 block): "Source-bound sensor availability is not implemented ...
  Ordinary zero values cannot represent unavailable sensor groups." -> the stream profile needs an
  explicit "no measurement" message.
- `python/ncp/stream.py`: Subscriber keeps LRU of `max_streams=1024`; an evicted live stream is
  accepted again as `joined` (silent loss of loss detection at 1025 streams); no type, no schema
  check, no time, no liveness; Publisher appends 16 hex to the name.
- Zenoh binding: streams on `ncp/s/<name>`; no wildcards (rule 9.2.5); `stream_sender(session, name,
  **options)`.
- `python/ncp/rounds.py`: `_release` frees the member only when the session's handler closes; a
  request in `_wait` blocks the session thread; excluded forever; `self.closed` not persisted; one
  `key` for all agents; the "unreachable" branch `agent in self._slots`.
- `IMPLEMENTATION = "ncp-python/2.0.0"` at revision 6 (same string as at revisions 2-5); only
  `spec/ncp2-rules.json` names the revision.
- CREBAIN has a "checkpoint family": "Retain a live native checkpoint and serve separately bound
  restored continuations" (README table). So restarts to an earlier clock are a designed use of the
  product, not a corner case -> lockstep's "did not run" after such a restore needs a history
  identity.

### Draft answers so far (to be refined)

Q1 ranking (draft):
1. Streams are the under-designed half, and every remaining NCP 1 consumer is stream- or
   command-shaped.
2. No authority pattern and no peer identity to the application.
3. Profile mechanism: three attachment styles, no profile revision on the wire, profiles compose by
   handler wrapping in the SDK (ordering hazards).
4. No run/composition identity: nothing ties sessions, streams, transcripts of one run together;
   "declared profiles for many entities and modalities" has no document in NCP 2.
5. No time base anywhere outside transcripts.
6. Evidence sits on revision 2 and reliable byte streams; the lossy binding has no campaign.
7. Live observation of exchanges by third parties is impossible; only post-run transcripts.
8. Local (no Zenoh) fan-out of streams has no binding rule: CREBAIN standalone needs it.

Q4 (draft): lockstep: (a) history identity for restarts/restores; (b) no admission control on who
may take (last take wins); (c) the holder machine should be shared with the authority profile;
(d) tick has no relation to stream time. Rounds: (a) no recovery of verdict or result; (b) no
feature, no report, no revision; (c) first-claim members, one key; (d) permanent exclusion, deadline
not announced; (e) no restart story (no clock); (f) record has no identity and no chain; O(N^2)
bytes per round; (g) Zenoh time limit vs deadline unstated.

Q2 (draft, details in the final report): stream profile within the frozen 6.3 message (type in the
identifier `T/E/I`, start message as root, `ncp.t`, `ncp.alive`, `ncp.void`, `ncp.dropped`,
`ncp.refs`, announcement by feature operation `ncp.streams.list` with per-pair authenticated
anchors (seq, identity) as the answer to group-key forgery, tombstones, no LRU). Authority profile:
acquire inside the opening with owner-issued term CAS + token over exact bytes naming the open
response identity, `remaining_ms`/`now_ms` in every response, `not_after_ms` on the body's clock for
an enforced in-transit bound, stop on its own service with a pre-opened session, count+last for the
recovery verdict, history changes at restart and at latch reset. Decline reasons: one new declined
code `conflict` + `reason` name (ncp.-prefixed for profiles) + profile member with the facts to
proceed; registry in ncp2-rules.json.

## Checkpoint 3 (probes and a prototype run; figures inspected)

All runs in scratch copies (`/tmp/ncp-design` = `git archive 904f87c`; `/tmp/ncp-design-proto` and
`/tmp/ncp-design-base` for the prototype), `python3 -I -B`. Nothing written in any repository.

### Probes (in `probes/`, logs beside them)
- `lockstep_restore.py` [C]: step for tick 2 runs (owner tick 2, effect list has two entries), the
  response is lost, the owner restarts and restores the checkpoint of tick 1 exactly as rule 5.7
  says; `recover()` returns `no`. The verdict "did not run, and it never will" is given for a
  step that executed once. Documented in profile section 7 ("Restarts"); the guide says "the
  client learns whether its last step ran".
- `rounds_lost_response.py` [C]: agent a's response of round 1 is lost after the round applied
  its request. New session: `open` response enables nothing (`{}`); sending round 1 again gives
  `declined body_invalid`, detail "round 1 is not open; the next round is 2", body members
  `['detail']` only; round 2 is then accepted. a never receives its result of round 1 and learns
  that it was applied only by inference.
- `stream_lru.py` [C]: with `max_streams=4`, a fifth stream evicts the first; a replayed copy of
  the first stream's message 1 is then `accepted` again, and loss counting restarts. A new
  subscriber accepts an old message 3 as `joined`.

### Prototype: a history identity in the lockstep clock (in `prototype/`)
- SDK diff (`sdk-history.diff`, 4 lines): `Lockstep(history=...)`, random 32 hex by default; the
  clock (open report and take response) carries `history`.
- Model diff (`model-history.diff`): the clock carries an epoch; known/taken tuples carry the
  history; `LS.judge` unchanged (tuple equality now includes the history); S1 made strict (the
  weakening for restarts to an earlier saved clock removed); restarts to another state or to an
  earlier clock draw a new history; a restart with the latest clock keeps it (`NCP_KEEP_HISTORY=1`)
  or draws a new one (`=0`).
- Results, one fault, both shapes, both identifier variants:
  - baseline with counters (original SDK): 469,268 worlds, all hold (matches the gate). Verdict
    events `('no', 'older', 'ran')`: 60 + 60 + 60 + 50 = 230: "did not run" for a step that ran
    before a restore, accepted by the weakened S1.
  - history, keep on latest-clock restart: 469,268 worlds; S1 strict, S2-S6, L1, progress hold;
    the 230 events are now `unknown`; no `('no', *, 'ran')` event remains. Self-test: 12 of 12.
  - history, every restart draws a new one: 471,556 worlds; all hold.
  - mutant "judge ignores the history": caught by strict S1 with the trace of the restore scenario.

### Figures inspected (PNG renderings in `png/`)
- `ncp2-bindings`: unchanged since revision 4: six prose cards, no status pill, no lockstep, links
  and a pattern and a profile on one level.
- `ncp2-transcript`: unchanged: session chain with forward arrows, no file layout, no status pill.
- `ncp2-outcomes`: four outcome cards + eight event cards; now overlaps with `ncp2-verdicts`.
- `ncp2-verdicts`, `ncp2-ladder`, `ncp2-lockstep`: present with REVISION 6 pills. The lockstep
  heading "A lost step gets one verdict, and it stays true" is stronger than profile section 7
  (no verdict with another client; "did not run" after a restore).
- The publication (`docs/publication/ncp-system-design.tex`, 15 figures) is an NCP 1 document; it
  has no NCP 2 section and no NCP 2 figure.

### Other facts checked
- Transcript header: both verifiers require only `chain`; the specification does not say whether
  unknown header members are allowed. State the extension rule before the freeze.
- No peer identity plumbing in either SDK (`grep` for peer credentials / peer certificates: none).
- `stream_sender` passes Zenoh options through; the specification does not say that a stream put
  must not block the publisher.
- `Rounds.owner()` builds its own `Owner` with a private handler: rounds cannot be combined with
  `Lockstep` (or a later authority handler) in the SDK.
- Requirements map: section 8 has 12 entries and 17 stream vectors; `formal/README.md`: "Sections 8
  to 10 are tested, not modeled".
- NCP 1 manuscript, "Plant command admission": "The body issues live authority and command
  freshness. A serialized lease grants no authority. Arrival never starts or extends a remote
  command lifetime." -> the authority profile must have the body issue the freshness window.
  Key insight for the design: a request that acknowledges response n-1 was made after the body
  built response n-1 (it contains that response's identity), so the body can bound the age of
  request n on its own clock alone.

## Checkpoint 4 (before writing the final report)

- CREBAIN `origin/main` `a071ea7`, `src-tauri/crates/ncp-simulation/contracts/crebain.body.v1.json`
  [C]: the `step` request has `tick_index` ("the next step, one more than the last"),
  `source_state_digest` ("must equal the owner's current state digest"), and `proposals`
  ("[{response, drone_ids}]: for each controller response that this step applies, its identity");
  `prepare` has schedule rows with `sensor_available` and `actuator_available`. The members are
  described in English, without `ncp.schema`. The pin is `rev = 2e24ef5...`, `version = "=2.0.0"`.
  => The first consumer built, in its own contract, the tick and state of the lockstep profile
  (without holder or recovery), causal references by identity, and availability flags. This is
  the best evidence for `ncp.tick`, `ncp.refs`, and `ncp.void`, and it shows that the profile has
  no consumer because the consumer could not wait for it.
- Authority design decision: each authority response carries a random `grant` and a `window_ms`;
  the next authority-bearing request acknowledges that response (rule 7.3.9), so it was made after
  the body built it; the body admits it only inside the window on its own clock. This is the
  "freshness grant" of the NCP 1 design, with no clock value on the wire.
- Decline reasons: name the member `ncp.reason` (reserved prefix), so that it can be added after a
  tag without a collision with application members of declined bodies.
- Final report structure: summary; what I ran; Q1 architecture; Q2 profiles (common rules, decline
  reasons, streams, authority); Q3 tag; Q4 lockstep and rounds; Q5 figures; order of work; sound
  parts; files.

## Checkpoint 5 (final)

- `design-review.md` is complete (692 lines): summary, what I ran, sections 1 to 7, files.
- Re-read once on the coordinator's request and corrected in place: the tag summary (section 6.3
  outside the freeze; section 13.2 split after rule 4, because section 10 names the keyed chain);
  the schema keywords that section 11.1 lacks (`anyOf`, `allOf`, named definitions: those are the
  ones that I saw in Galadriel's envelope); the CREBAIN checkpoint family is on NCP 1 today; the
  second outside effect after a restore is by rule 6.5, not shown by the probe; removed a sentence
  about the comparison document, which I did not read; added the missing rounds rows of the reason
  table; `window_ms` in the authority report; `ncp.lease` also in `declined` responses.
- `main` moved to `4e5a6de` after my snapshot (coordinator's message). I did not read it. The report
  says so in its header, marks every result as of `904f87c`, and recommends none of the items that
  `4e5a6de` fixes. The history prototype must be redone on the model of `4e5a6de` (13 mutants, exact
  S4 excuse).
- No new investigation was started after the coordinator's message.
