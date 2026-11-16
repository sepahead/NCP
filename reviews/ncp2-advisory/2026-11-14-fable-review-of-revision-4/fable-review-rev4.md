# Advisory review of NCP 2, revision 4

Date: 14 November 2026. Reviewer: an independent, read-only language-model advisor.
This report is non-normative. It informs the maintainer's decisions and certifies nothing: not security, safety, interoperability, or release readiness.

Reviewed sources:

- NCP: worktree `.ncp2-hardening` at `44bc3ca`, the same as `origin/main`, plus the uncommitted consumer table in `docs/design/NCP-2-MIGRATION.md`.
- CREBAIN `a1df34c`; Prisoma `6d5dde0`; Galadriel `2cc4b4f` (same tree as `20ddc41`, now on its `main`); Haldir `origin/main` `221c045`, read through Git objects.

Marks: **[C]** confirmed: I read the code or the text, or ran the command. **[S]** suspected: reasoned, not reproduced.
Paths without a repository name are in the NCP worktree.

---

## 1. Executive verdict

1. The core exchange (sections 3 to 7 of the specification) is sound as far as I could test it. I found no defect in it, and the gate reproduces: 2,591,544 model-check states, 12 of 12 mutants, all SDK tests.
2. The lockstep profile is not sound. Its recovery can say "did not run, and it never will" for a step that then runs, because the holder is a session name and not an opening. Three probes confirm it (D1). Fix the SDKs now; revise the profile before any consumer uses it.
3. Do not freeze the whole text with the tag yet. Streams, the Zenoh binding, contract schemas, and both profiles have no consumer, and three defects sit exactly there (D1, D3, D5).
4. The evidence in the README is for revision 2 of the SDKs on reliable byte streams, by one author. The hard cases (loss, restart, replay) live on the Zenoh binding, which has no fault campaign and no benchmark (S1, S2).
5. The remaining NCP 1 users map to NCP 2 without a change of the frame format. They need two profiles (streams for sensors and advisories; authority for commands) and three small rules in the core (decline reasons, schema exemption for `ncp.` members, a stated principal convention).
6. Haldir: make the body the owner and the Gate its one client. The lease becomes a term-fenced holder that the Gate acquires with a request inside a fresh opening. The response gives Haldir the authenticated acknowledgement that its NCP 1.0 path lacks.
7. Figures: the seven NCP 2 diagrams are accurate for revision 4, with one stale alt text and one overstatement. Three are prose in boxes and should be redrawn. Eleven new figures would make the design reviewable.

---

## What I ran

All runs used a `git archive` copy of `44bc3ca` in the scratch directory, except the diagram check, which runs in check mode and writes nothing.

| Command | Result |
| --- | --- |
| `python3 -I scripts/check_ncp2_rules.py` | `rules: 21 codes, 4 local codes, and 14 limits agree in the data, the specification, both SDKs, and the Lean model` |
| `python3 -I scripts/check_ncp2_requirements.py` | `84 requirements of spec/NCP-2.md, 250 references to checks, 3 untested with a reason` |
| `python3 -I python/tests/test_ncp.py` | 84 tests OK, 3 skipped (they need the Rust examples) |
| `test_rounds.py`, `test_conformance.py`, `test_composition.py` | 10, 9, and 7 tests OK |
| `python3 -I model/simulate.py --faults 1` | 105,464 worlds; every property holds |
| `python3 -I model/simulate.py --faults 2` | 2,591,544 worlds in 90 s; every property holds |
| `python3 -I model/simulate.py --faults 2 --self-test` | 12 of 12 known defects detected |
| `cargo test --locked --release --offline` in `rust/`, target directory in scratch | 36 passed, 0 failed |
| `python3 -B scripts/gen_diagrams.py --check` | `OK: 44 diagram files are current; text fits, connectors attach, contrast is at least 4.5:1, and the accessibility contract holds` |
| `gh run list` and `gh run view` on `sepahead/NCP` (read-only) | At `44bc3ca`: `NCP 2` success, `NCP 2 Zenoh binding` success, `CI` failure (S7) |
| Four probes in `probes/`, and the coordinator's `lockstep_replay_safety.py` | D1 and D3 |

Not run: the Lean build, the owners against the Lean oracle, differential fuzzing, the Zenoh gate, and every benchmark.

---

## 2. Design and architecture flaws

I found no CRITICAL flaw in the core. D1 is critical for the lockstep profile's own claim; I rate it HIGH for the release because no consumer uses the profile.

### D1. HIGH — Lockstep recovery can say "did not run, and it never will" for a step that then runs [C, three probes]

My first draft said that safety holds and only liveness is lost. That was wrong. The coordinator's scenario is correct; I reproduced it with my own probe.

- **Cause.** Both SDKs name the holder by the session identifier: `python/ncp/lockstep.py:70` (`self.holder = info.session`) and `:84` (`request.session != self.holder`); `rust/src/lockstep.rs:99` and `:126`. A session identifier does not name one opening. Rule 7.1.8 says that a copy of `open` can open a session again, and on a byte stream every connection has its own owner object.
- **Scenario 1: a replayed `open`** (`probes/lockstep_replay_safety_check.py`; the coordinator's `lockstep_replay_safety.py` gives the same result):

  ```text
  1. s is delayed; A's call ended: local.timeout executed: unknown
  2. recovery on C2 -> verdict no | owner tick 1
  3. replayed first open of A on C3 -> ok | nonce differs from C1's: True
  4. delayed s on C1 -> ok None  | owner tick 2 | position 11
  RESULT: the verdict NO was false: s ran
  ```

  The delayed step arrives on the first connection. Its owner still holds the first opening, so `ack` matches. The replayed `open` made A's session name the holder again, so the step passes profile rule 5.1. Authenticated frames do not help: both frames are frames that the client made (section 13.2).
- **Scenario 2: no third party** (`probes/lockstep_same_session_id.py`). The client recovers on a new connection with the same session identifier, which both SDKs accept (`ncp.Client(..., session=...)`). The fence excludes nothing:

  ```text
  s is delayed on C1; the call ended: local.timeout
  recovery on C2 with the same session identifier -> verdict no
  delayed s on C1 -> ok | owner tick 2 | position 11
  ```

- **Scenario 3: liveness** (`probes/lockstep_stale_open.py`). A replayed old `open` takes the ticks from the live holder:

  ```text
  replayed old open -> ok | holder is now A's old session: True
  B's next step -> declined: the session does not hold the ticks: it did not ask for ncp.lockstep, or a later session took them over
  ```

- **Scope.** Byte-stream servers, where each connection has its own owner. In the Zenoh servers, one worker holds a session identifier, and a copy of `open` gets the kept response without a second takeover [S, from reading `_on_query`].
- **Why it matters.** The profile's first property ("One verdict for each step") is false. This is the class of finding 29, which revision 4 meant to close. The profile also contradicts rule 7.1.8 of the core: accepting `open` changes state outside the session. The profile is "neither model checked nor proved" (its section 7).
- **Fixes compared.**

  | Fix | Safety | Liveness under replay | Wire change | Cost for the client |
  | --- | --- | --- | --- | --- |
  | (a) The holder is the opening: its nonce, or the identity of its `open` response | Restored. With a wrapper that keys the holder by the opening, my probe gives `declined ... this opening does not hold the ticks`, and the verdict stays true | Still lost: a replayed `open` takes the ticks | None | None. The SDKs must give the handler the opening in `open` and in each request |
  | (b) A client-chosen term in the feature parameters; the owner grants only a higher term | Restored only while every `open` carries a term, or together with (a) | Restored | Profile revision 3 | A counter that outlives the client's sessions and crashes; or one refused `open` to learn the highest term |
  | (c) Takeover by a request inside the new opening, for example `ncp.lockstep.take` | Restored: the request is admitted in one opening, so (a) is included | Restored: the request must acknowledge the new `open` response, which holds a fresh nonce, so no stored frame can be that request | Profile revision 3 | One more round trip for each session that steps. No state in the client |

- **Recommendation.** Do (a) now. It is a correction of both SDKs, changes no frame, and alone makes the verdict true. Then make (c) revision 3 of the profile:
  1. `open` with the feature only reports the tick, the state digest, the request, and the current term. It changes nothing outside its session, as rule 7.1.8 requires.
  2. The request `ncp.lockstep.take` names that term. The owner declines it if the term has moved. Otherwise the owner waits for a running step, makes this opening the holder, raises the term, and returns the final tick, state digest, and request.

  The nonce then works as a challenge that only the live client can answer, and the client needs no durable state. The owner-issued term stops a late `take` of an abandoned opening. I do not recommend (b) alone: it moves durable state into every client, and `open` still acts on other sessions.
- **Also.** Model check the profile before it is frozen. Two openings of one session identifier, one delayed step, and one replayed `open` are enough to find scenario 1. Add both scenarios as SDK tests in both languages.

### D2. HIGH — The tag freezes parts of the design that no consumer has used [C]

- **Evidence.** `spec/NCP-2.md:4`: "The tag `v2.0.0` freezes this text ... An erratum corrects the text and changes no behavior." `docs/release/NCP-2.0.0.md`, owner step 1: tag "the commit that holds this record".
- **Evidence.** The only on-wire consumer is CREBAIN's loop over pipes. Its `ncp::` use in `src-tauri/crates/ncp-simulation`: `spawn`, `PipeChild`, `serve_stdio`, `Owner`, `Client`, `call_all`, `Tap`, `transcript::verify`, `Contract::from_bytes`, `declined`. Prisoma's `ncp-loop-capture` and Galadriel's `galadriel-local-adapter` use `ncp::frame::` and `ncp::transcript::` only: they read transcript files.
- **Evidence.** No consumer uses streams, the Zenoh binding, either profile, authenticated frames, or contract schemas (`ncp.schema`: 0 matches in both CREBAIN contracts, which describe every member in English).
- **Why it matters.** Every remaining migration needs the unused parts. D1, D3, and D5 are defects in those parts that a first consumer would have met in its first week.
- **Fix.** Choose one before the tag:
  - (a) Tag the exercised core (frames, messages, exchange, byte-stream binding, transcripts, contract identity) as 2.0. Mark section 8, section 9.2, section 11.1, and both profiles "provisional: may change in 2.1" in their status lines.
  - (b) Hold the tag until one stream consumer (Galadriel's sidecar) and the authority profile (Haldir) run end to end.

  I prefer (a): it lets CREBAIN, Prisoma, and Galadriel depend on a tag for what they use today.

### D3. MEDIUM — Contract schemas reject the reserved body members of the profiles [C, probe]

- **Evidence.** `probes/schema_vs_profile.py`, a contract whose `step` request schema has `"additionalProperties": false`, served under `ncp.Lockstep`:

  ```text
  declined: body_invalid | request schema: $: the member 'ncp.tick' is not allowed
  tick: 0
  ```

  Section 11, rule 4: the owner declines a body that does not match "before it calls the application". Section 15 reserves `ncp.` members "at any level of a body" for profiles. The profile handler runs after the schema check (`python/ncp/owner.py:260-264`).
- **Why it matters.** Two features of the release candidate fail together, and no text says that a contract must list `ncp.tick` or `ncp.round`. The same conflict waits for every later profile.
- **Fix.** Section 11.1: `properties`, `required`, and `additionalProperties` do not apply to members whose names start with `ncp.`; the profile that defines a member checks it. Add a schema vector and one SDK test for each profile.

### D4. MEDIUM — `declined` has one application code and free text; the profiles overload it [C]

- **Evidence.** `python/ncp/owner.py:278-281`: a handler's `Declined` always becomes `body_invalid`. Lockstep rule 5.1 and rounds rule 4.1 use `body_invalid` for "not the holder", "wrong tick", "member excluded", and "wrong round"; the reason "SHOULD" be in `detail`, which is free text of at most 256 characters. CREBAIN's `nest_controller.py:155` writes `f"tick_index must be {last + 1}"`.
- **Why it matters.** A client cannot branch on a reason without reading prose. A valid body that the owner's state refuses is not `body_invalid`. The authority profile needs machine-readable reasons (lease expired, not holder, ESTOP latched). A rounds member that reconnects can learn the open round only from `detail`.
- **Fix.** Add one `declined` code for a refusal by state, for example `conflict`, and a `reason` member in the body: a name, with `ncp.` reserved for profiles (`ncp.lockstep.not_holder`, `ncp.rounds.excluded`). Revision-4 clients already act on the outcome of a code that they do not know (section 7.5), so old clients keep working.

### D5. MEDIUM — Streams cannot yet carry the sensor and advisory families [C for each fact; S for the conclusion]

- No stream type on the wire. Rule 8.4: "NCP does not say which stream type of the contract a message belongs to."
- No subscriber checks a stream body against its schema. `python/ncp/stream.py:123-149` holds contract identities only; section 11, rule 4 covers operations only.
- No announcement, no liveness rule, and no time. A late subscriber gets `joined` and knows nothing about the publisher, the run, or the stream type.
- Authentication is one shared key. Every subscriber can make the publisher's messages, so a monitor of possible sensor tampering cannot tell the publisher from another subscriber.
- After a loss, `prev` is not checked (rule 8.8), so a message inserted with a larger `seq` is accepted. The design record, section 6, says so.
- No consumer, no fault campaign, and no benchmark exist for streams on Zenoh.
- **Fix.** A stream profile before the freeze (section 4.3), or mark section 8 provisional.

### D6. MEDIUM — NCP 2 has no peer identity [C]

- **Evidence.** `OpenInfo` (`python/ncp/owner.py:85-92`) has `session`, `contract`, `run`, and `features`. One key serves each owner and server: "Each owner that `make_owner` returns must have the same key" (`bindings/zenoh/python/ncp_zenoh/__init__.py`, `Server`). Rounds binds a member to the first session that names it (rule 4.2). On a Zenoh service, each admitted peer can hold up to `max_sessions` (4,096) sessions, each with a thread.
- **Why it matters.** NCP 1.0 required that each payload identity bind to the verified transport principal. NCP 2 leaves this to bindings that do not report the principal to the application. Haldir's lease names a holder.
- **Fix.** State the convention in section 13: a key is a principal, so one service and one key for each pair of principals. Where a binding knows its peer (Unix peer credentials, the TLS client certificate), pass it to the `open` handler. No wire change.

### D7. MEDIUM — Three wire-incompatible revisions share one version [C]

- **Evidence.** `python/pyproject.toml:7` and `rust/Cargo.toml:3`: `2.0.0` at revisions 2, 3, and 4. `python/ncp/owner.py:33`: `IMPLEMENTATION = "ncp-python/2.0.0"`, which every `open` response and every transcript header carries. `conformance/generate.py:42`: `REVISION = 3`, so `conformance/vectors.json` says `"revision": 3` while `conformance/README.md` says "revision 4". `spec/ncp2-rules.json` has no revision. `evidence/release/ncp-2.0.0/SHA256SUMS` changed in `9f58e7a`, `2e24ef5`, and `44bc3ca` for the same file names.
- **Why it matters.** A transcript, a wheel, or an `open` response cannot say which revision's rules made it. Pins by Git commit work only while every consumer builds from source.
- **Fix.** Until the tag: `2.0.0-rc.4` for Cargo and `2.0.0rc4` for Python, the same string in `IMPLEMENTATION`, a `revision` member in `ncp2-rules.json`, and a check that the specification, the rules, and `generate.py` agree.

### D8. LOW to MEDIUM — An exchange has no urgency, deadline, or cancellation [C, by design]

- **Evidence.** Rule 7.6.1: one request at a time. `docs/design/NCP-1-SHORTCOMINGS.md`, row 15: cancellation is "By design". `docs/design/NCP-2-COMPARISON.md`: "time limits are local to the client". The Zenoh channel sends the same frame again after 1 s, at most three times.
- **Why it matters.** It decides how commands map. An ESTOP cannot overtake a step of its session. A repeated command frame can be stale. An owner cannot know that a request is late.
- **Fix.** No core change. The authority profile gives ESTOP its own session and puts a validity time in the command body (section 4.4).

### D9. LOW to MEDIUM — Contract identity covers prose, and only the owner can offer alternatives [C]

- **Evidence.** Section 11: the identity is the SHA-256 of the exact bytes. CREBAIN's contracts hold sentences such as "1 to 3 sorted, unique identifiers: a lowercase letter, then ...". Rule 7.1.4.2 lets an owner accept several contracts; a client names one.
- **Why it matters.** A corrected typo is a new identity and a `contract_mismatch`. The upgrade order is forced (owners before clients, subscribers before publishers) and no document gives it as a procedure.
- **Fix.** Guidance: keep the identity-bearing document to names and schemas, and publish the prose next to it. Write the upgrade procedure into the migration document.

### D10. LOW — The Zenoh servers restate owner rules outside `step` [C]

- **Evidence.** `bindings/zenoh/python/ncp_zenoh/__init__.py`, `_answer` and `_on_query`, and `bindings/zenoh/rust/src/lib.rs:368-372`: the server makes `wrong_protocol`, `session_expired`, `not_open`, and `refused` itself, although `ncp.owner.refuse` exists. `largest` only grows. `model/README.md`: the "message" network drives `owner.step`, not the server class.
- **Why it matters.** Decision 26 ("pure state machines") does not cover the code that the remaining consumers will run. That code has unit tests only.
- **Fix.** Route every frame of a session that the server does not hold through `step` with an empty state. Drive the server class from the model check with a fake Zenoh session.

### D11. LOW — The Rust SDK falls back to a weak random source without an error [C]

- **Evidence.** `rust/src/lib.rs:51-73`: if `/dev/urandom` cannot be opened or read, nonces and session identifiers come from `RandomState`, a counter, and the time. Rule 7.1.5 has a MUST for a cryptographically secure generator. `KNOWN_LIMITATIONS.md` names only systems without `/dev/urandom`; a full descriptor table or a sandbox without `/dev` takes the same path on Unix.
- **Why it matters.** At most once needs unique nonces, and the fallback is very probably unique, so the effect is small. But the SDK breaks a MUST silently.
- **Fix.** Return an error, or use `getrandom`.

### D12. LOW — Rounds: no recovery, no negotiation, first-claim members [C]

- **Evidence.** `spec/NCP-2-ROUNDS.md`: the profile uses no feature; the `open` response says nothing about the open round; a member that lost its response cannot get its result of that round; rule 4.2 binds a member to the first session that names it. The Rust SDK has no rounds.
- **Sound part.** Rounds binds a member to a handler object, one for each owner (`python/ncp/rounds.py:126-137`), so the name-against-opening defect of D1 does not apply here.
- **Fix.** A feature `ncp.rounds` whose response gives the last closed round and the member's last applied request.

---

## 3. Shortcomings and gaps

### S1. HIGH — The evidence is for revision 2 on reliable byte streams; the hard cases are on the lossy binding [C]

- **Evidence.** `KNOWN_LIMITATIONS.md`: the benchmarks and the fault campaign "ran with revision 2 ... not ... for revisions 3 and 4, not on Linux, and not with the Zenoh binding". `benchmarks/fault-campaign/README.md`, protocols 2 to 5: pipes, Unix sockets, and TCP only.
- **Evidence.** Revision 2 passed all 8,730 fault trials. Revision 2 also had three truthfulness defects (design record, findings 17 to 19), and the model check found one "in its first run". The campaign's faults (bit flips, truncation, repeats, kills, stalls, sizes) include no owner restart with delayed copies, no session expiry, and no replay.
- **Why it matters.** The README's correctness headline rests on a campaign that could not see what revisions 3 and 4 fixed. On a byte stream, one connection is one session, so at most once is nearly structural.
- **Fix.** Run the campaigns again on the revision that the tag names. Add a fault campaign on the Zenoh binding: restarts, expiry, delayed and repeated `open`, replay. Say in the README what the campaign cannot detect.

### S2. HIGH — One author wrote the specification, both SDKs, the vectors, the Lean model, and the model check [C]

- **Evidence.** `conformance/generate.py:1-6`: "The expected results come from the specification, written out below case by case. Valid frames are encoded with the Python SDK." Lines 1033 to 1036: the generator stops if the Python verifier disagrees with an expected result. The expected results are hand-written, which is right, but no vector can exist that the Python SDK fails.
- **Evidence.** Each outside look found defects: the review before revision 3 (11 decisions), the review of revision 3 (13 findings, 2 critical), and this review (D1, D3). The core now converges; the profiles and the streams do not.
- **Fix.** A third decoder, owner, and client by another author, run through `python -m ncp conformance`, the oracle traces, and the fuzzer. Until then, write "two implementations by one author" wherever agreement of the SDKs is given as evidence.

### S3. MEDIUM — The newest rules have the weakest checks [C]

- `formal/NCP2/ClientModel.lean` models the client of the Zenoh binding. It has no response that names no request, so the chain binding of revision 4 (rule 7.6.2) rests on the bounded model check of the Python client and on 16 client vectors.
- The model check reaches 165 states on the byte-stream network and 1.28 million on the message network.
- The mutant `owner_declined_not_kept` is "caught by progress", not by property 5. The model's application gives one verdict for each body, so only Lean's `DeclinedIsFinal` covers the case that motivated `declined`.
- Both profiles have SDK tests only: no vectors, no model check, no proof. Their own texts say so.
- **Fix.** Add the nameless response to the Lean client model with a claim for `bad_frame`; give the model's application a state-dependent verdict; model check both profiles.

### S4. MEDIUM — No release gates are defined for NCP 2, and two documents order the release differently [C]

- **Evidence.** A search for `ncp 2`, `ncp2`, and `v2.0` finds nothing in `GOVERNANCE.md`, `RELEASE_READINESS.md`, `ROADMAP.md`, `CONTRIBUTING.md`, or `contract/release-gates.v1.json`. The only list is the "Checks" paragraph of `docs/release/NCP-2.0.0.md`.
- **Evidence.** `docs/design/NCP-2-DESIGN.md`, section 9, and `docs/design/NCP-2-MIGRATION.md`, section 5, put the release after the consumers have moved. `docs/release/NCP-2.0.0.md` prepares the tag now.
- **Fix.** One list of gates for `v2.0.0` in `RELEASE_READINESS.md`, each PASS, FAIL, or NOT RUN: both gates on Linux and macOS; the campaigns on the tagged revision; one consumer of each pattern that the tag freezes; and the items that stay NOT RUN by decision (external review, signatures, SBOM).

### S5. MEDIUM — Documents that overstate, understate, or are stale [C]

| Where | Defect |
| --- | --- |
| `docs/NCP-2-GUIDE.md:73` | The alt text says "Three cards for the outcomes ok, rejected, and ended, and six cards". The figure has four outcomes and eight cards. |
| `docs/NCP-2-GUIDE.md:117-118` | 9.1, 38.6, 37.9, and 457.8 µs (comparison protocol 1, on battery). The figure `ncp2-why` on the same page and the README give 9.0, 38.8, 36.1, and 469 µs (protocol 2). |
| `README.md:44`; `docs/NCP-2-GUIDE.md:116,169` | "Revision 3 changed the session rules ... have not run again." Revision 4 also changed the owner and the client. |
| `docs/design/NCP-2-DESIGN.md:3` | The status line stops at revision 3. |
| `docs/design/NCP-1-SHORTCOMINGS.md:11,33` | "a specification of 362 lines and 3,876 lines of code" at `6424fb8`. Now: 551 lines plus 169 lines of profiles; `python/ncp/*.py` has 4,800 lines and `rust/src/*.rs` 5,997. |
| `scripts/gen_diagrams.py`, `ncp2_outcomes` | "an exhaustive check of the real SDKs". Only the Python client and owner run in it (`model/README.md`, Limits). |
| `scripts/gen_diagrams.py`, `ncp2_bindings` | TCP "or with TLS on both sides": the Rust SDK has no TLS (`KNOWN_LIMITATIONS.md`). The lockstep profile is absent. |
| `conformance/README.md` | "revision 4" for vectors that say `"revision": 3`. |
| `KNOWN_LIMITATIONS.md` | The title is "Known limitations of the NCP 1.0 candidate"; the NCP 2 limits are a section inside. |
| `spec/NCP-2-LOCKSTEP.md`, section 7 | "One verdict for each step" is false at `44bc3ca` (D1). |

Understated: no NCP document says that an exchange gives Haldir the authenticated application acknowledgement that its NCP 1.0 path lacks (section 4.4). That is one of the strongest reasons for the migration.

Resolved during the review: the Galadriel row of the uncommitted migration table now names `20ddc41` on `main`. I confirmed it read-only with `gh api repos/sepahead/galadriel/commits/main`.

### S6. LOW — A TypeScript SDK is probably not needed [C]

- **Evidence.** CREBAIN's TypeScript imports from `@sepahead/ncp`: `ActionBuffer`, `NCP_VERSION`, the type `CommandLike`, and a version guard (`src/hooks/devNcpCommand.ts`, `src/hooks/useDroneController.ts`, `src/neuro/versionGuard.ts`). These are helpers, not a wire client.
- **Fix.** Move `ActionBuffer` into CREBAIN. Decide on a TypeScript client only if the interface must speak frames itself.

### S7. MEDIUM — The main CI workflow is red on every recent push [C]

- **Evidence.** At `44bc3ca`, the workflow `CI` fails, as on at least the eleven pushes before it, back to `3965892` on 11 November. Failing jobs:
  - "publication diagrams + PDF", step "Rebuild and compare the system-design PDF": `pypdf.errors.PdfReadError: Multiple definitions in dictionary at byte 0x460c for key /Group`.
  - "current policy + pinned supply replay": `advisories FAILED`, in the tree of `ncp-zenoh v1.0.0-rc.1` with `zenoh v1.9.0` and `quinn v0.11.9`.
- **Why it matters.** A branch that is always red hides the next real failure. The advisories are in the NCP 1 remote family that four consumers still pin, which is also a reason to finish the migration.
- **Fix.** Repair or retire the PDF comparison. Record the advisories as accepted for the frozen NCP 1 code, with an end date, or take `ncp-zenoh` 1.0 out of the default policy job.

---

## 4. Ecosystem and migration

### 4.1 Principle

The message families of the wire-1.0 candidate belong in contracts and profiles. The frame format and the exchange rules need no change. The core needs three small rules before the freeze, because profiles cannot add them later without pain:

1. A decline reason that a program can read (D4).
2. No schema keyword applies to `ncp.` members (D3).
3. A stated convention for principals: one key and one service for each pair (D6).

### 4.2 Where each family goes

| NCP 1 (wire 1.0) | Users | NCP 2 | Missing today |
| --- | --- | --- | --- |
| Control plane: open, step, close; `OperationContext` for idempotency | CREBAIN application, Engram | Exchange. `open` is request 0; at most once replaces `OperationContext` | Nothing. CREBAIN's native simulation does this |
| Perception plane: `SensorFrame` with `StreamPosition {epoch, seq}` | CREBAIN body; Galadriel's `galadriel-pid` sidecar and monitor envelope; Prisoma `ncp-observer` | Stream. The instance suffix of the stream identifier is the epoch; `seq` and the identity are the position; `ncp.end` is the closure | Stream type, announcement, heartbeat, time, schema check (D5) |
| Observation plane: spikes and membrane potentials | Prisoma `ncp-observer` | Stream with `ncp.array` attachments: a strong fit | As above |
| Advisories | Galadriel raw-advisory publisher; record-only at Haldir | Stream `galadriel.advisory`. Each message names its evidence by stream identifier, `seq`, and identity | The deferred "causal references" member `ncp.refs` now has its first user |
| Action plane: `CommandFrame` with mode, validity, source position, `AuthorityLease` | Haldir commander, Engram plant commander, CREBAIN body | Exchange with the body as owner, under an authority profile | The profile (4.4) |
| Haldir intent extension | Engram to Haldir | Exchange with the Gate as owner; the COSE bytes travel as a `u8` attachment; the response is the decision receipt | Nothing in the core |
| `ActionBuffer`, `LinkMonitor` | CREBAIN | Not protocol. Move into CREBAIN | Nothing |
| Passive tap of the command plane | Prisoma, Galadriel | Not possible: a third party cannot see a Zenoh query or a pipe | Transcripts after the run, or a mirror stream from the body (4.5) |

### 4.3 Sensor streams and advisories: a stream profile

Proposal, with no change of the frame or of section 6.3:

1. **Type.** The stream identifier is `<stream type>/<instance>`. The type is a stream type name of the contract; the SDKs already append `/` and 16 random characters. A subscriber then knows the schema and the largest frame, and checks the body against `ncp.schema.body`.
2. **Announcement.** The publisher's service has an operation that lists its live streams: identifier, type, run, last `seq`, and last identity. Section 8 already points here: "accepts only the stream identifiers that the publishers of the run announce, for example in an exchange". The answer is also the anchor against replayed old streams.
3. **Start and liveness.** Message 1 carries `ncp.start` with the run, the period, and the longest silence. The publisher sends at least one message in each such interval, so a subscriber detects the loss of the last messages.
4. **Time.** One reserved member, for example `ncp.time: {"t_ns": ..., "clock": "sim" | "monotonic" | "utc"}`, so that recorders and monitors need no contract-specific code to order messages.
5. **Authentication.** One key for each publisher. State that every subscriber can forge under a shared key. If a monitor needs evidence against a subscriber, the publisher signs `(stream, seq, identity)` at intervals; that belongs to the application.

First consumer: Galadriel's `galadriel-ncp`. It is read-only and record-only, so it is the cheapest way to exercise streams on Zenoh. Galadriel's lifecycle detector derives one scope "from the admitted producer and exact stream position"; `(stream identifier, seq, identity)` is that position.

### 4.4 Commands with authority: a concrete proposal for Haldir

**Facts from Haldir's `main`** (`docs/NCP-COMPATIBILITY.md`, `crates/haldir-ncp10/src/lease.rs`, `docs/AUTHORITY-GRAPH.md`) [C]:

- The Gate issues an NCP 1.0 commander lease to "the transport principal and final route named by its deployment-bound exclusive-route ACL evidence" and carries it on every command. Terms are `boot_counter · 2^24 + n`. The interval is 15 to 60 s; the Gate moves to a newer term after two thirds.
- "The body returns no authority feedback under rc.1."
- A local publisher `Ok` "stops as application-unobserved: NCP 1.0 starts `ttl_ms` at plant-local arrival, and this path has no enforced in-transit age bound or authenticated application acknowledgement."
- The publication journal has the states Called, UnknownAfterPublish, and ReturnedError.
- Haldir's own authority is separate and stays: COSE and Ed25519 for intents, mission leases, admissions, and revocations.

**Why an exchange and not a stream.** Haldir's journal is an at-most-once exchange in other words:

| Haldir today | NCP 2 |
| --- | --- |
| Called: recorded before the publish | The frame is written to the transcript before it is sent (section 10.2) |
| No authenticated acknowledgement | The response, bound to the request by its identity and to the session by the chain |
| UnknownAfterPublish | "Possibly executed"; a new opening can resolve it (below) |
| ReturnedError | `declined`: never executed |
| No in-transit age bound | The Gate times the round trip on its own clock: the body applied the command between the send and the receipt of the response |

The Gate already writes and syncs a journal record for each command, so one round trip adds little.

**Roles and binding.**

- The body is the owner of a command service. The Gate is its one client. One service and one key for the pair: authenticated frames (section 13.2) protect from end to end across Zenoh routers. This replaces the transport principal that the Zenoh callback of NCP 1 could not report. Mutual TLS and access control (rule 9.2.6) stay as the second layer.
- ESTOP has its own service and key for each enrolled emergency source, so it never waits behind a command (D8).

**The profile, `ncp.authority` (proposed).** The body keeps, across openings: `highest_term`, the holder (an opening, not a session name: D1), the lease deadline on its own monotonic clock, and the ESTOP latch.

1. **`open` with the feature reports and changes nothing**: `{"highest_term": H, "held": true|false, "estop": true|false, "last": R}`, where `R` is the identity of the last authority-bearing request that the body applied.
2. **`ncp.authority.acquire`** is the first request of the opening. Body: the term, the lease identifier, the duration, and a token. The token is the issuer's signature (for Haldir, COSE by the Gate's key) over the service, the contract identity, the term, the duration, and **the identity of this opening's `open` response**. The body declines unless the term is higher than `highest_term`, the duration is within its bound, the token verifies and names this opening, and no ESTOP is latched. Otherwise this opening is the holder, and the response gives `{"term": T, "expires_in_ms": D}` on the body's clock.
   - The lease is bound to one opening by the nonce in the `open` response. A replayed `open` or a replayed `acquire` can take nothing.
   - The request is at most once with a true verdict. The NCP 1.0 problem "a lost renewal could leave Gate holding a lease that the body had let lapse" disappears: the Gate knows whether the acquisition ran.
   - The body's response is the grant. This is the direction of NCP ADR-006 (issuance moves to the body) without a second mechanism.
3. **Rotation** is `acquire` with a newer term, from the same opening or a new one. It is a transfer while the old lease lives and a new acquisition after it lapsed, as the Gate does today.
4. **Authority-bearing operations** are marked in the contract. Each request names its term. The body declines with a reason (`ncp.authority.not_holder`, `.expired`, `.term`, `.estop`) unless this opening holds a live lease of that term. Each `ok` response returns the term and the remaining time: authority feedback on every command. HOLD is such an operation, so it stays attributable.
5. **Validity.** The command body has `valid_for_ms`, counted by the body from receipt. With the round-trip bound, the Gate can commit the action interval without agreement of clocks.
6. **ESTOP** is `ncp.authority.estop` on the ESTOP service. It needs a key, not a lease, and it latches. A reset stays a deployment action outside the profile, as in the NCP 1 figure `fsm`.
7. **Recovery.** After "possibly executed", the Gate opens a new session. `last` in the `open` response says whether its command was applied, as the tick does in lockstep. The Gate then acquires a newer term.
8. **The body stays the final actuator authority.** It can decline any command for its own safety reasons, with a reason.

**Non-repudiation.** A shared key cannot show a third party who made a frame (section 13.2). The token binds the Gate's signature to the opening, and the chain binds every command to the token. If Haldir needs a signature for each command, it puts the digest of its signed decision receipt in the command body, and the body signs its evidence in the response. Both are contract members, not NCP rules.

**What moves in Haldir (epoch 22).**

- A new adapter crate next to `haldir-ncp10`, in modeled and exact modes as today.
- The compatibility artifact pins: the NCP tag, the specification revision, the SHA-256 of `spec/ncp2-rules.json`, the revision of the authority profile, and the identity of the body's contract. NCP 2 checks the contract identity on the wire at every `open`, so the pin is enforced at run time, not only at build time.
- The owner-signed transition commit and the epoch record, which only the owner can deliver.

**Before any of this**: fix D1, D3, and D4; write the profile as a specification; port the state machine of `ncp-core/src/authority.rs`; and model check it with two openings, delayed frames, and replay. D1 shows what an unchecked holder rule costs.

### 4.5 Observers

A passive tap cannot see an exchange. Two replacements:

- **After the run:** the transcripts of the participants. Prisoma's `ncp-loop-capture` and Galadriel's `galadriel-ncp-loop` already work this way.
- **During the run:** the body publishes a mirror stream of what it applied: the request identity, the term, the tick or time, and the action. This is CREBAIN's "accepted/applied evidence" role in Haldir's authority graph. Advisories that name these messages by identity give Prisoma its join key, in place of `StreamPosition`.

### 4.6 Order

1. NCP: D1 fix (a), D3, D4, D7; drafts of the stream and authority profiles; model checks of the profiles.
2. Galadriel `galadriel-ncp` as the first stream subscriber, with CREBAIN's producer surface as the publisher.
3. Prisoma `ncp-observer`: streams and transcripts.
4. CREBAIN's application: the body as owner under the authority profile; `ActionBuffer` moves into CREBAIN; `@sepahead/ncp` goes.
5. Haldir, epoch 22.
6. Engram, with its owner.
7. Then the freeze of streams, the Zenoh binding, and the profiles.

---

## 5. Figures

### 5a. Inventory

Generators: `scripts/gen_diagrams.py` (44 files in `docs/diagrams`), `scripts/plot_perf.py` (`docs/plots`), `benchmarks/comparison/analyze.py`, `benchmarks/multi-agent/figures.py`, `benchmarks/nest-campaign/figures.py`, and `docs/local-v1/build.py`.

Facts for all [C, `svg_audit.txt`]: every tracked SVG outside `assets/archive` has `role="img"`, one `<title>`, one `<desc>`, and `aria-labelledby`. The diagram generator checks text fit, contrast of at least 4.5:1 in both themes, and stale files. It does not compare a figure with the alt text of the page that shows it, which is how the guide's alt text went stale. The benchmark plots draw text as paths (`svg.fonttype: path`), so their text cannot be selected or searched; the `<desc>` of each points to `summary.md`.

**NCP 2 diagrams** (`docs/diagrams/ncp2-*-{light,dark}.svg`)

| File | Used in | Verdict | Defects |
| --- | --- | --- | --- |
| `ncp2-call` | README, guide | Keep, small fix | Accurate for revision 4; card 1 names the nonce. The `open` response label says only "ok, session frame size". No `declined`. The README alt says "acknowledgement"; the guide and the figure say "receipt". |
| `ncp2-frame` | guide | Keep | Accurate. It shows neither the padding of the JSON region nor the HMAC form of the digest. |
| `ncp2-outcomes` | guide | Fix | The figure is current. The guide's alt text is stale. "exhaustive check of the real SDKs" overstates. Twelve cards with no visual link from event to outcome to verdict. |
| `ncp2-transcript` | guide | Redesign | It shows the session chain, not the transcript: no header, no record fields, no end record. The arrows run forward in time; the hash references run backward. |
| `ncp2-bindings` | guide | Redesign | Six cards of prose and no drawing. No lockstep profile. The TLS statement is false for Rust. Bindings, a pattern, and a profile sit at one level. |
| `ncp2-loop` | README | Keep, small fix | Clear. It reports the result of 12 November; CREBAIN recorded the loop again under revision 4 (`a1df34c`). State the revision in the note [S: I did not compare the numbers with the new record]. |
| `ncp2-why` | guide | Redesign or remove | A table drawn as a picture, next to the same table in Markdown. Sixteen cells say "Not built in". The numbers agree with `benchmarks/comparison/results-2/summary.md` [C]. |

None of the seven carries a status badge. The NCP 1 diagrams do ("PROPOSED DESIGN", "CANDIDATE WIRE 1.0").

**Benchmark plots** (each in light and dark)

| File | Used in | Verdict | Defects |
| --- | --- | --- | --- |
| `benchmarks/comparison/results-2/figures/integrity_*` | README, guide, benchmark README | Keep, small fix | Clear. At README width the labels are about 9 px. At 1 MiB the claim "fastest" rests on dots that nearly touch on the log axis. |
| `.../results-2/figures/calls_*` | No Markdown | Fix, then use | The Rust panel omits gRPC over a Unix socket (35.9 µs), the fastest gRPC arm at N = 0; the README table has it. |
| `.../results-2/figures/{decomposition,tails,versions}_*` | No Markdown | Use | Good plots that no page shows. |
| `.../results/figures/{calls,decomposition,tails}_*` | benchmark README | Keep | Protocol 1, on battery. Say so in each caption. |
| `.../results/figures/versions_*` | guide, benchmark README | Fix | The guide should show `results-2/versions_*`, to agree with its other figure. |
| `benchmarks/multi-agent/results/figures/fanout_*` | benchmark README | Keep, small fix | Five series in four panels. The y axes of the Rust and Python columns differ, which misleads a comparison by eye. |
| `.../multi-agent/results/figures/{rounds,mpi}_*` | benchmark README | Keep | Clear. |
| `benchmarks/nest-campaign/results-5/figures/overhead_*` | README, guide, benchmark README | Keep | Clear. Marker shape and color both carry the series. |
| `.../results-5/figures/spikes_*` | benchmark README | Keep | Clear. The plot explains the missing NCP 1.0.1 row. |

All benchmark plots show revision 2 of the SDKs. None says so inside the figure.

**NCP 1 diagrams** (`docs/diagrams/*-{light,dark}.svg`, generated)

| File | Used in | Verdict | Defects |
| --- | --- | --- | --- |
| `system-map` | README | Keep until NCP 1 leaves; relabel | The title does not say "NCP 1". It sits below the NCP 2 section, so a reader can take it for the current system. |
| `evidence-ladder` | README | Keep; add an NCP 2 twin (new figure 9) | It describes the 1.0 candidate. NCP 2 has no evidence figure. |
| `overview` | README, links only | Keep | The link text says that it shows proposed gates. Its note on the Zenoh principal is a source for D6. |
| `exchange`, `payload-transfer` | `local/modular/owner.md`, `STATUS.md` | Keep | NCP 1 modular SDK. Remove with it. |
| `closed-loop` | `docs/implementation/CLOSED_LOOP_MATH.md` | Keep | Independent of the protocol generation. It can serve NCP 2 documents. |
| `queue-admission`, `fsm` | `RESILIENCE.md` | Keep as sources | `fsm` (HOLD, ACTIVE, ESTOP latch) is a source for the authority profile. |
| `topology`, `runtime`, `lifecycle`, `sequence`, `admission`, `versioning` | `docs/implementation/NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md` | Keep as sources | `topology` (four planes) and `admission` (ESTOP, HOLD, Active) are sources for section 4. Remove with NCP 1. |
| `ecosystem` | `docs/handoff/NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md` | Keep; add an NCP 2 twin (new figure 1) | The eleven role subjects are the best list of what must migrate. |

**Other figures**

| File | Used in | Verdict | Defects |
| --- | --- | --- | --- |
| `docs/local-v1/architecture.svg`, `step-order.svg` | README, `docs/local-v1/README.md`, `math-guide.md` | Keep until NCP 1 leaves | One theme only; a white rectangle keeps them readable on a dark page. A third visual style. `step-order` has 12 px text. |
| `docs/figures/nest-coupling.svg`, `nest-3.9.0-stepwise-control.svg`, `nest-3.10.0-stepwise-control.svg` | `NEST_REALTIME.md`, `benchmarks/nest-coupling/README.md` | Keep; add the source | "exported figure; regenerate from its source", and the source is not in the repository. One theme. The smallest text is about 14 px at full width and about 11 px in a README column. |
| `docs/figures/stale-predecessor.svg` | `CLOSED_LOOP_MATH.md` | Keep; reuse | The same missing source. It explains why a step must name the state that it answers, so it fits the lockstep profile. |
| `docs/plots/realtime_*`, `overlap_*` | `PERFORMANCE.md` | Keep | Marked historical (NEST 3.8.0). In `realtime`, the note box crosses the N=50k series. |
| `assets/logo-{light,dark}.svg` | README | Keep | Animated, with a reduced-motion rule. |
| `assets/archive/logos/*` (44 files) | `assets/archive/logos/README.md` | Keep as an archive | The README's second line links to it; that place is worth more for the guide. |
| `output/pdf/ncp-system-design.pdf` | README | Fix or relabel | An NCP 1 document that the README calls "the standalone technical reference". The CI job that rebuilds and compares it fails (S7). |
| `docs/local-v1/ncp-local-v1-guide.pdf` | README | Keep until NCP 1 leaves | NCP 1. |
| `reviews/v1-independent-20260920/inputs/NCP_closed_loop_review.pdf` | `INDEPENDENT_REVIEW_REQUEST.md` | Keep | A review input; do not change it. |
| `evidence/implementation/receipts/B00`, `B04` (9 PNG screenshots) | No Markdown | Keep | Evidence records, not figures. |

**Consistency.** The repository has five visual styles: the generated diagrams, the benchmark plots, the exported `docs/figures`, the historical `docs/plots`, and `docs/local-v1`. The first two are the NCP 2 styles and fit together. The others can leave with NCP 1.

### 5b. New figures

Each should come from `scripts/gen_diagrams.py`, with a light and a dark file and a status badge "NCP 2 · release candidate · revision N".

1. **NCP 2 ecosystem map.** Content: each program as client, owner, publisher, subscriber, or transcript reader; solid lines for what runs on NCP 2 today, dashed for NCP 1. Source: the consumer table of `docs/design/NCP-2-MIGRATION.md` and the eleven roles of `ecosystem`. Alt text: who talks to whom over which pattern, and which five paths have not moved.
2. **Layers of NCP 2.** Content: bytes of a binding, frame, message, exchange or stream, profile, contract; beside each layer, who defines it and where it is checked. Source: specification sections 1, 3, 6 to 9, 11, 17. Alt text: six layers from the binding up to the application's contract; NCP defines the lower four.
3. **Owner decision ladder.** Content: rules 7.3.1 to 7.3.13 as one path, with an exit at each rule that shows the outcome, the code, and the client's verdict; a mark at rule 11, "admitted: kept from here". Source: `spec/ncp2-rules.json`. Alt text: thirteen checks in order; a frame leaves at the first that fails; only a frame that passes ten checks is admitted.
4. **Verdict map.** Content: three columns (executed, not executed, possibly executed); every code and every local event in its column. Source: `spec/ncp2-rules.json`, members `executed` and `client`. Alt text: which answers let a client say that a step ran, did not run, or possibly ran.
5. **A lost session and a second opening.** Content: a time line with an owner restart, a delayed `open`, two nonces, two chains, and the old step that gets `ack_mismatch`. Source: section 7.1, rule 7.6.4, design findings 18 and 19. Alt text: why each opening has a nonce and why a rejected step is "possibly executed".
6. **Lockstep recovery and takeover.** Content: scenario 1 of D1 before and after the fix: two connections, the delayed step, the replayed `open`, the holder. Source: the profile and `probes/lockstep_replay_safety_check.py`. Alt text: a delayed step is declined because the ticks belong to an opening, not to a session name.
7. **Rounds time line.** Content: three agents, one deadline, one excluded member, and the shared record with the request identities. Source: `spec/NCP-2-ROUNDS.md`, section 7. Alt text: each round applies its requests in member order and gives every agent the same record.
8. **Transcript file.** Content: magic, header, records with kind, time, length, frame, and chain value, and the end record; a second lane for the session chain inside the frames. Source: section 10.1. Alt text: two chains, one over the records of the file and one over the requests and responses of a session.
9. **Evidence map of NCP 2.** Content: a matrix of the eight properties, the bindings, and the profiles against proof, model check, vectors, fault campaign, and benchmark; each cell shows the revision or "none". Source: `conformance/requirements.json`, `formal/README.md`, `model/README.md`, the benchmark READMEs. Alt text: which claims have which kind of evidence at which revision; the profiles and the Zenoh binding have the least.
10. **Authority over NCP 2.** Content: the Gate, the body, the `open` with its nonce, `acquire` with term and token, commands with the remaining time, and the ESTOP service beside them. Source: section 4.4. Alt text: a lease is bound to one opening; every command returns the remaining time; ESTOP has its own session.
11. **Security by binding.** Content: section 13.1 as a drawing: for each binding, who can read, who can send, and what protects; a mark where authenticated frames change the answer. Source: section 13.1. Alt text: what each binding protects and where a shared key or TLS is needed.

### 5c. Redesigns

- **`ncp2-transcript`** becomes figure 8. Draw the file. Draw the references as arrows that point backward, labelled "names".
- **`ncp2-bindings`** becomes figure 2 plus a small topology: one client with a pipe, a socket, and a Zenoh service; one publisher with two subscribers. Move rounds and lockstep to a row "profiles". Say "TLS: Python SDK".
- **`ncp2-why`**: remove it from the guide, where the Markdown table is easier to read and to keep true, or redraw it as a matrix with one row for what the others build in and NCP 2 lacks (typed interfaces, deadlines, peer authentication without a shared key), so that it is a comparison.
- **`ncp2-outcomes`**: replace the lower eight cards with figure 4. Keep the four outcome cards.
- **README.** Put figure 1 or figure 2 next to `ncp2-call`. Label `system-map` and `evidence-ladder` "NCP 1".
- **All NCP 2 plots.** Add "SDK revision 2" to the subtitle. Raise the tick label size by two points for the plots that the README shows.
- **Process.** Keep each figure's alt text in the generator and let the check compare it with the page, as it does for file names.

---

## 6. Quick wins and larger work, by value

**Quick wins (hours each)**

1. D1 (a): the holder is the opening, in both SDKs, with the two scenarios as tests.
2. D3: exempt `ncp.` members from schemas; one vector; one test for each profile.
3. D2 (a): mark section 8, section 9.2, section 11.1, and the profiles "provisional" in their status lines, and correct "One verdict for each step" until D1 is closed.
4. D7: pre-release version strings, `REVISION = 4`, a revision in `ncp2-rules.json`, and a check.
5. S5: the guide's alt text and numbers, the three "revision 3" sentences, the line counts, "SDKs" in `ncp2_outcomes`, the TLS line in `ncp2_bindings`, the design record's status line.
6. S4: the gate list for `v2.0.0` in `RELEASE_READINESS.md`.
7. D11: fail closed without a secure random source.
8. S7: repair the PDF comparison; record or remove the NCP 1 advisories.
9. Figures: status badges; "NCP 1" labels; show the `results-2` plots; add gRPC over a Unix socket to `calls`.
10. D6 and D9 as text: the principal convention in section 13 and the upgrade procedure for contracts.

**Larger work (days to weeks)**

1. Lockstep revision 3 with `ncp.lockstep.take`, and a model check of both profiles (D1).
2. Decline reasons through the specification, the rules data, both SDKs, Lean, and the vectors (D4).
3. The stream profile and Galadriel as its first consumer (D5, 4.3).
4. The authority profile, its model check, CREBAIN's body side, and Haldir's epoch 22 (4.4).
5. A fault campaign and a benchmark on the Zenoh binding; all campaigns again on the tagged revision (S1).
6. A third implementation by another author (S2).
7. The Zenoh servers through `step`, inside the model check (D10).
8. The eleven new figures and the three redesigns (5b, 5c).

---

## 7. What I checked and found sound

- **The owner rules.** The text of section 7.3, `python/ncp/owner.py`, and `formal/NCP2/Model.lean` have the same order. `step` is a pure function of the state and one frame [C].
- **The chain binding of responses that name no request** (finding 28). I tried to build a `bad_frame` or `shutdown` response that binds to the client's chain while its request executes: on one connection, across connections, and with two openings of one session name. I found none. The serve loop sends such a response from the thread that handles requests, between frames, and then closes (`python/ncp/binding.py:299-352`), so no request can run beside it [C for the code; S for completeness].
- **The nonce** makes the chains of two openings disjoint. In every scenario of D1, the core rejects or declines correctly; the defect is in the profile's holder, not in the core [C].
- **Rounds** binds members to handler objects, not to session names [C].
- **The gate reproduces** as documented: the rules check, the requirements map, 110 Python tests, 36 Rust tests, and the model check with its mutation test [C].
- **The vectors' expected results are hand-written** from the specification, not computed by an SDK [C].
- **The documents state their own limits accurately**: `formal/README.md`, `model/README.md`, `bindings/zenoh/README.md`, and `KNOWN_LIMITATIONS.md`. The Lean README's mutant table, with its warning about what an `x` means, is better than most published work [C].
- **Hosted CI.** The workflow `NCP 2` runs the gate on Linux and macOS (`.github/workflows/ncp2.yml`), and both NCP 2 workflows pass at `44bc3ca` [C].
- **The diagram generator** is a real control: 44 files current, contrast and text fit checked in both themes [C].
- **The numbers in `ncp2-why`** match `benchmarks/comparison/results-2/summary.md` [C].
- **Two owners on one Zenoh key** cost liveness, not truth: every path that I traced ends in `session_expired`, `ack_mismatch`, or a time limit, each "possibly executed" [S].
- **The decisions that I would not reopen**: exact-byte identities without a canonical form, the acknowledgement in the next request, the outcome `declined`, attachments aligned to 8 bytes, and Zenoh as an option outside the core.

---

## Files of this review

In this directory: `fable-review-rev4.md` (this report), `fable-review-rev4-draft.md` (the drafts), `probes/` (four probes; each takes the path of the SDK's `python` directory), `svg_audit.py` and `svg_audit.txt` (the SVG audit), `png/` (renderings of the figures), `py_gate.log`, `model2.log`, and `rust_test.log` (outputs of the runs).
