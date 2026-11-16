# Advisory review of NCP 2 revision 4 — DRAFT (work in progress)

Status of this file: draft 2, updated mid-review on 14 November 2026 (D3 re-rated to HIGH after the coordinator's probe; S2, S4, S7 added). It records everything found so far.
The final report is `fable-review-rev4.md` in the same directory.
This review is read-only and advisory. It is non-normative and certifies nothing (security, safety, interoperability, or release readiness).

Reviewed: NCP worktree `.ncp2-hardening` at `44bc3ca` (plus the uncommitted consumer table in `docs/design/NCP-2-MIGRATION.md`), CREBAIN `a1df34c`, Prisoma `6d5dde0`, Galadriel `2cc4b4f` (branch `ncp2-local-adapter-rev4`), Haldir `origin/main` `221c045` through Git objects.

Marks: **[C]** confirmed (I read the code or text, or ran the command). **[S]** suspected (reasoned, not reproduced).

---

## What I ran (all outside the repositories, on a `git archive` copy in the scratch directory)

| Command | Result |
| --- | --- |
| `python3 -I scripts/check_ncp2_rules.py` | `rules: 21 codes, 4 local codes, and 14 limits agree in the data, the specification, both SDKs, and the Lean model` |
| `python3 -I scripts/check_ncp2_requirements.py` | `84 requirements of spec/NCP-2.md, 250 references to checks, 3 untested with a reason` |
| `python3 -I python/tests/test_ncp.py` | 84 tests OK (3 skipped: they need the Rust examples) |
| `test_rounds.py`, `test_conformance.py`, `test_composition.py` | 10, 9, and 7 tests OK |
| `python3 -I model/simulate.py --faults 1` | 105,464 worlds; every property holds |
| `python3 -I model/simulate.py --faults 2` | 2,591,544 worlds in 90 s; every property holds |
| `python3 -I model/simulate.py --faults 2 --self-test` | 12 of 12 known defects detected |
| `cargo test --locked --release --offline` in `rust/` (target directory in scratch) | 36 passed, 0 failed |
| `python3 -B scripts/gen_diagrams.py --check` (in the worktree, check mode, writes nothing) | `OK: 44 diagram files are current; text fits, connectors attach, contrast is at least 4.5:1, and the accessibility contract holds` |
| Probe `probes/lockstep_stale_open.py` | A replayed old `open` takes the ticks from the live holder (finding D3) |
| Probe `probes/schema_vs_profile.py` | A closed request schema declines every lockstep step (finding D4) |

Not run: the Lean build, the Rust-against-Lean oracle traces, differential fuzzing, the Zenoh gate, and every benchmark.

### Probe outputs, verbatim

`lockstep_stale_open.py` (two sessions share one `ncp.Lockstep`; frames are authenticated with a shared key; a third party replays the first session's `open` frame on a new connection):

```text
A stepped to tick 1 holder is A: True
B stepped to tick 2 holder is B: True
replayed old open -> ok | holder is now A's old session: True
B's next step -> declined: the session does not hold the ticks: it did not ask for ncp.lockstep, or a later session took them over
tick stays 2
```

`schema_vs_profile.py` (a contract whose `step` request schema has `"additionalProperties": false`, served under `ncp.Lockstep`):

```text
declined: body_invalid | request schema: $: the member 'ncp.tick' is not allowed
tick: 0
```

---

## 2. Design and architecture findings so far

### D1. HIGH — The tag freezes parts of the design that no consumer has used [C]

- Evidence. `spec/NCP-2.md:4`: "The tag `v2.0.0` freezes this text ... An erratum corrects the text and changes no behavior." `docs/release/NCP-2.0.0.md` owner step 1: "Create the tag `v2.0.0` on the commit that holds this record."
- Evidence. The only on-wire NCP 2 consumer is CREBAIN's loop over pipes. Its API use (grep of `ncp::` in `src-tauri/crates/ncp-simulation`): `spawn`, `PipeChild`, `serve_stdio`, `Owner`, `Client`, `call_all`, `Tap`, `transcript::verify`, `Contract::from_bytes`, `declined`. Prisoma's `ncp-loop-capture` and Galadriel's `galadriel-local-adapter` use only `ncp::frame::` and `ncp::transcript::`: they read transcript files offline.
- Evidence. No consumer uses streams (`Publisher`, `Subscriber`), the Zenoh binding, the lockstep profile, the rounds profile, contract schemas (`ncp.schema`: 0 matches in both CREBAIN contracts), or authenticated frames.
- Why it matters. Every remaining migration (Galadriel `galadriel-ncp`, Prisoma `ncp-observer`, CREBAIN's application, Haldir) needs exactly the unused parts: streams, Zenoh, authentication, and a fenced holder. Findings D3, D4, and D5 are defects in those parts that the first consumer would have met.
- Fix. Choose one before the tag: (a) tag the exercised core (frames, exchange, byte-stream binding, transcripts, contracts) as 2.0 and mark section 8, section 9.2, section 11.1, and both profiles "provisional: may change in 2.1"; or (b) hold the tag until one stream consumer (Galadriel's sidecar) and the authority profile for Haldir run end to end.

### D2. MEDIUM — `declined` has one application code and free text; profiles overload it [C]

- Evidence. `python/ncp/owner.py:278-281`: a handler's `Declined` always becomes the code `body_invalid`. `spec/NCP-2-LOCKSTEP.md` rule 5.1 and `spec/NCP-2-ROUNDS.md` rule 4.1 use `body_invalid` for "not the holder", "wrong tick", "member excluded", "wrong round"; the reason is "SHOULD ... in its member `detail`", free text of at most 256 characters.
- Evidence. `python/ncp/lockstep.py:84-92` and CREBAIN's `nest_controller.py:155` (`f"tick_index must be {last + 1}"`) put state into English strings.
- Why it matters. A client cannot branch on a reason without parsing prose. A body that is valid, but refused because of the owner's state, is not `body_invalid`. The Haldir mapping needs machine-readable denial reasons (lease expired, not holder, ESTOP latched). A rounds member that reconnects cannot learn the current round except from `detail`.
- Fix. Add one `declined` code for state conflicts (for example `conflict`) and a `reason` member in the body: a name, with `ncp.` reserved for profiles (`ncp.lockstep.not_holder`, `ncp.lockstep.tick`, `ncp.rounds.excluded`). Clients already act on the outcome of unknown codes (section 7.5), so this is compatible for revision-4 clients.

### D3. HIGH — Lockstep recovery can say "did not run, and it never will" for a step that then runs [C, three probes]

Correction of draft 1: draft 1 said "Safety holds". That was wrong. The coordinator's scenario is correct, and I reproduced it with my own probe.

- Cause. Both SDKs name the holder by the session identifier, not by the opening: `python/ncp/lockstep.py:70` (`self.holder = info.session`) and `:84` (`request.session != self.holder`); `rust/src/lockstep.rs:99` and `:126`. A session identifier does not name one opening: rule 7.1.8 says that a copy of `open` can open the session again, and on a byte stream every connection has its own owner object.
- Scenario 1, a replayed `open` (`probes/lockstep_replay_safety_check.py`, and the coordinator's `lockstep_replay_safety.py`, both run against `44bc3ca`):

  ```text
  1. s is delayed; A's call ended: local.timeout executed: unknown
  2. recovery on C2 -> verdict no | owner tick 1
  3. replayed first open of A on C3 -> ok | nonce differs from C1's: True
  4. delayed s on C1 -> ok None  | owner tick 2 | position 11
  RESULT: the verdict NO was false: s ran
  ```

  The delayed step arrives on the first connection, whose owner still holds the first opening, so its `ack` matches. The holder is A's session name again, so the step passes rule 5.1. Authenticated frames do not help: the replayed `open` and the delayed step are frames that the client made (section 13.2).
- Scenario 2, no third party (`probes/lockstep_same_session_id.py`): the client recovers on a new connection with the same session identifier, which both SDKs accept (`ncp.Client(..., session=...)`). The fence then excludes nothing:

  ```text
  s is delayed on C1; the call ended: local.timeout
  recovery on C2 with the same session identifier -> verdict no
  delayed s on C1 -> ok | owner tick 2 | position 11
  ```

- Scenario 3, liveness only (`probes/lockstep_stale_open.py`, output in the first section): a replayed old `open` takes the ticks from the live holder, whose next step is declined.
- Why it matters. This breaks the profile's first property ("One verdict for each step") and is the same class as finding 29, which revision 4 meant to close. No consumer uses the profile yet. The profile is "neither model checked nor proved".
- Fixes compared.

  | Fix | Safety | Replay liveness | Wire change | Client cost |
  | --- | --- | --- | --- | --- |
  | (a) The holder is the opening (its nonce, or the identity of its `open` response) | Restored: my probe with a wrapper that keys the holder by the opening gives `declined ... this opening does not hold the ticks`, and the verdict stays true | Still lost: a replayed `open` takes the ticks | None | None. SDK only: the handler must learn the opening in `open` and in each request |
  | (b) A client-chosen term in the feature parameters; the owner grants only a higher term | Restored only together with (a), or while every `open` carries a term | Restored | Profile revision 3 | The client must keep a counter that outlives its sessions and its crashes, or learn the highest term from a refusal and open again |
  | (c) Takeover by a request inside the new opening, for example the operation `ncp.lockstep.take` | Restored (it includes (a): the request is admitted in one opening) | Restored: the request must acknowledge the new `open` response, which holds a fresh nonce, so no stored frame can be that request | Profile revision 3 | One more round trip for each session that steps; no state in the client |

- Recommendation. Do (a) now: it is a correction of both SDKs, changes no frame, and alone makes the verdict true again. Then make (c) revision 3 of the profile: `open` with the feature only reports; the first request `ncp.lockstep.take` takes the ticks, waits for a running step, and returns the tick, the state digest, and the request. Then `open` changes nothing outside its session, as rule 7.1.8 requires, and the nonce works as a challenge that only the live client can answer. Add an owner-issued term to (c): the `open` response names the current term, and `take` names it; a late `take` of an abandoned opening then fails. I do not recommend (b) alone: it gives the client durable state, and `open` still has an effect on other sessions. Model check the profile before it is frozen: two openings of one session identifier, a delayed step, and a replayed `open` are enough to find scenario 1.
- The same term-fenced holder is what the authority profile needs (section 4).

### D4. MEDIUM — Contract schemas reject the reserved body members of the profiles [C, probe]

- Evidence. Probe output above. `spec/NCP-2.md` section 11, rule 4: the owner declines a body that does not match the schema "before it calls the application". Section 15 reserves `ncp.` members "at any level of a body" for profiles. Section 11.1: with `additionalProperties: false`, "the value MUST NOT have members outside `properties`". The profile handler runs after the schema check (`python/ncp/owner.py:260-264`, then `handler.validate`).
- Why it matters. Two features of the release candidate fail when they are used together, and the specification does not say that a contract must list `ncp.tick` or `ncp.round`. No test covers the combination.
- Fix. In section 11.1: `properties`, `required`, and `additionalProperties` do not apply to members whose names start with `ncp.`; the profile that defines a member checks it. Add a schema vector. The same rule protects later profiles.

### D5. MEDIUM — Streams cannot yet carry the sensor and advisory families [C for each fact; S for the conclusion]

- No stream type on the wire. Rule 8.4: "NCP does not say which stream type of the contract a message belongs to".
- Stream body schemas are never checked. `python/ncp/stream.py:123-149` holds contract identities only; section 11, rule 4 covers operations only.
- No announcement, no liveness rule, no time. A late subscriber gets `joined` and knows nothing about the publisher, the run, or the stream type. "Freshness and rate limits belong to the stream's contract" (section 8).
- Authentication is a group key. Section 13.2 gives one shared key; every subscriber can make a publisher's messages. A monitor of "possible sensor tampering" (Galadriel) cannot tell a publisher from another subscriber.
- After any loss, `prev` is not checked (rule 8.8), so a message inserted with a larger `seq` is accepted (the design record, section 6, says so).
- No consumer, no fault campaign, no benchmark on the Zenoh binding.
- Fix. Write a stream profile before the freeze (section 4 below), or mark section 8 provisional.

### D6. MEDIUM — NCP 2 has no peer identity [C]

- Evidence. `OpenInfo` (`python/ncp/owner.py:85-92`) has `session`, `contract`, `run`, `features`: nothing about the peer. One key for each owner and server: "Each owner that `make_owner` returns must have the same key" (`bindings/zenoh/python/ncp_zenoh/__init__.py`, `Server` docstring). Rounds: a member is bound to the first session that names it (rule 4.2). The NCP 1 overview figure states "The pinned Zenoh 1.9.0 callback does not expose the verified peer principal".
- Why it matters. NCP 1.0 required "Bind each payload identity to the verified transport principal" (AGENTS.md). NCP 2 moved all of this to bindings that do not report the principal to the application. Haldir's lease names a holder principal. On a Zenoh service, any admitted peer can hold up to `max_sessions` (4,096) sessions and threads.
- Fix. State the convention: the key is the principal, so one service and one key for each pair of principals. Where the binding knows the peer (Unix peer credentials, the TLS client certificate), pass it to the `open` handler. No wire change.

### D7. MEDIUM — Three wire-incompatible revisions share one version [C]

- Evidence. `python/pyproject.toml:7` and `rust/Cargo.toml:3`: `2.0.0` at revisions 2, 3, and 4. `python/ncp/owner.py:33`: `IMPLEMENTATION = "ncp-python/2.0.0"`; the `open` response and every transcript header carry it. `conformance/generate.py:42`: `REVISION = 3`, so `conformance/vectors.json` says `"revision": 3` while `conformance/README.md` says "revision 4". `spec/ncp2-rules.json` has no revision member. `evidence/release/ncp-2.0.0/SHA256SUMS` changed in `9f58e7a`, `2e24ef5`, and `44bc3ca` for the same file names.
- Why it matters. A transcript, a wheel, or an `open` response cannot say which revision's rules made it. Consumers pin by Git commit, which works only while everyone builds from source.
- Fix. Until the tag: `2.0.0-rc.4` (Cargo) and `2.0.0rc4` (Python), the same string in `IMPLEMENTATION`, a `revision` member in `ncp2-rules.json`, and a check that the specification, the rules, and `generate.py` agree.

### D8. LOW to MEDIUM — An exchange has no urgency, deadline, or cancellation [C, by design]

- Evidence. Rule 7.6.1: one request at a time. `docs/design/NCP-1-SHORTCOMINGS.md` row 15: cancellation "By design". `docs/design/NCP-2-COMPARISON.md`: "time limits are local to the client". Zenoh channel: the same frame again after 1 s, three times.
- Why it matters. It decides how the command family maps: an ESTOP cannot overtake a step in the same session; a repeated command frame can be stale; the owner cannot know that a request is late.
- Fix. No core change. The authority profile gives ESTOP its own session and puts a validity time in the command body (section 4).

### D9. LOW to MEDIUM — Contract identity covers prose, and only the owner can offer alternatives [C]

- Evidence. Section 11: identity is the SHA-256 of the exact bytes. CREBAIN's contracts describe every member in English sentences inside the contract, without `ncp.schema`. Rule 7.1.4.2 lets an owner accept several contracts; a client sends one.
- Why it matters. A corrected typo in a description is a new identity and a `contract_mismatch`. The upgrade order is forced (owners first; subscribers before publishers) and is not documented as a procedure.
- Fix. Guidance: keep the identity-bearing document to names and schemas; publish prose next to it. Document the upgrade order.

### D10. LOW — The Zenoh servers restate owner rules outside `step` [C]

- Evidence. `bindings/zenoh/python/ncp_zenoh/__init__.py`, `_answer` and `_on_query`: `wrong_protocol`, `session_expired`, `not_open`, and `refused` are made by the server, although `ncp.owner.refuse` exists. `largest` only grows. `model/README.md`: the "message" network drives `owner.step`, not the Zenoh server.
- Why it matters. Decision 26 ("pure state machines") does not cover the code that the remaining consumers will run. That code has unit tests only.
- Fix. Route every frame of an unknown session through `step` with an empty state; drive the server class from the model check with a fake Zenoh session.

### D11. LOW — The Rust SDK falls back to a weak random source without an error [C]

- Evidence. `rust/src/lib.rs:53-73`: if `/dev/urandom` cannot be opened or read, nonces and session identifiers come from `RandomState`, a counter, and the time. Rule 7.1.5: "MUST choose each nonce from at least 128 bits of a cryptographically secure random generator". `KNOWN_LIMITATIONS.md` names only systems without `/dev/urandom`; an exhausted descriptor table or a sandbox without `/dev` takes the same path on Unix.
- Why it matters. At most once needs unique nonces, and the fallback is very likely unique, so the effect is small. But a MUST is broken silently.
- Fix. Return an error, or use `getrandom`.

### D12. LOW — Rounds: no recovery, no negotiation, first-claim members [C]

- Evidence. `spec/NCP-2-ROUNDS.md`: the profile uses no feature, the `open` response says nothing about the current round, a member that lost its response cannot get its result of that round, and rule 4.2 binds a member to the first session that names it. Rust has no rounds (`rust/src` has no `rounds.rs`).
- Fix. A feature `ncp.rounds` whose response parameters give the last closed round and the member's last applied request, as lockstep does.

---

## 3. Shortcomings and gaps so far

### S1. HIGH — The evidence is for revision 2 and for reliable byte streams; the hard cases are on the lossy binding [C]

- Evidence. `KNOWN_LIMITATIONS.md`: benchmarks and the fault campaign "ran with revision 2 ... not ... for revisions 3 and 4, not on Linux, and not with the Zenoh binding". `benchmarks/fault-campaign/README.md`, protocols 2 to 5: pipes, Unix sockets, TCP only.
- Evidence. Revision 2 passed all 8,730 fault trials. Revision 2 also had three truthfulness defects (design record, findings 17 to 19), and the exhaustive model check found one "in its first run". The campaign's fault classes (bit flips, truncation, repeats, kills, stalls, sizes) do not include an owner restart with delayed copies, session expiry, or replayed frames.
- Why it matters. The README's correctness headline rests on a campaign that could not see the defects that revisions 3 and 4 fixed. On a byte stream, one connection is one session, so at most once is nearly structural there.
- Fix. Rerun on revision 4. Add a fault campaign on the Zenoh binding with restarts, expiry, delayed and repeated `open`, and replay. Say in the README what the campaign cannot detect.

### S2. HIGH — One author wrote the specification, both SDKs, the vectors, the Lean model, and the model check [C]

- Evidence. `conformance/generate.py:1-6`: "The expected results come from the specification, written out below case by case. Valid frames are encoded with the Python SDK". Line 1033-1036: the generator fails if the Python verifier disagrees with an expected transcript result. So the expected results are hand-written, which is good, but by the same author, and no vector can exist that the Python SDK fails.
- Evidence. Each outside look found defects: the review before revision 3 (11 decisions), the review of revision 3 (13 findings, 2 critical), and this review (D3, D4). The core exchange now seems to converge (I found no core defect); the profiles and streams do not.
- Fix. A third implementation of the decoder, the owner, and the client by another author (a small Go or TypeScript one would do), run through `python -m ncp conformance`, the oracle traces, and the fuzzer. Until then, say "two implementations by one author" wherever "both SDKs agree" is given as evidence.

### S7. MEDIUM — The main CI workflow is red on every recent push [C, `gh run list` and `gh run view`, read-only]

- Evidence. At `44bc3ca`: workflows `NCP 2` and `NCP 2 Zenoh binding` succeed. Workflow `CI` fails, as on at least the eleven pushes before it (back to `3965892`, 11 November). Failing jobs at `44bc3ca`: "publication diagrams + PDF" (step "Rebuild and compare the system-design PDF": `pypdf.errors.PdfReadError: Multiple definitions in dictionary at byte 0x460c for key /Group`) and "current policy + pinned supply replay" (`cargo deny`: `advisories FAILED`, in the tree of `ncp-zenoh v1.0.0-rc.1` with `zenoh v1.9.0` and `quinn v0.11.9`).
- Why it matters. A branch that is always red hides the next real failure. The advisories are in the NCP 1 remote family that Haldir, Galadriel, Prisoma, and CREBAIN still pin, so they are also a reason to finish the migration.
- Fix. Repair or retire the PDF comparison; record the advisories as accepted for the frozen NCP 1 code with an expiry date, or remove `ncp-zenoh` 1.0 from the default policy job.

### S3. MEDIUM — The newest rules have the weakest checks [C]

- The Lean client model (`formal/NCP2/ClientModel.lean`) is the Zenoh-style client. It has no response that names no request, so the chain binding of revision 4 (rule 7.6.2) is checked by the bounded model check of the Python client and by 16 client vectors only.
- The stream network of the model check reaches 165 worlds; the message network 1.28 million.
- The mutant `owner_declined_not_kept` is "caught by progress", not by property 5: the model's application always gives the same verdict for a body, so the case that motivated `declined` (finding 17) is covered by Lean's `DeclinedIsFinal` only.
- Both profiles: SDK tests only, no vectors, no model check (their own sections say so).

### S4. MEDIUM — No release gates are defined for NCP 2, and two documents order the release differently [C]

- Evidence. `grep -n -i "ncp 2\|ncp2\|v2\.0"` finds nothing in `GOVERNANCE.md`, `RELEASE_READINESS.md`, `ROADMAP.md`, `CONTRIBUTING.md`, or `contract/release-gates.v1.json`. The only list is the "Checks" paragraph of `docs/release/NCP-2.0.0.md` (the two gates and the release build) and the "Not run" line of `KNOWN_LIMITATIONS.md`.
- Evidence. `docs/design/NCP-2-DESIGN.md` section 9 and `docs/design/NCP-2-MIGRATION.md` section 5 put the release after the consumers have moved and NCP 1 has left the main branch. `docs/release/NCP-2.0.0.md` prepares the tag "on the commit that holds this record".
- Fix. One short list of gates for `v2.0.0` in `RELEASE_READINESS.md`, each PASS, FAIL, or NOT RUN: the two gates on Linux and macOS, the campaigns again on the tagged revision, one consumer of each pattern that the tag freezes, and the items that stay NOT RUN by decision (external review, signatures, SBOM).

### S5. MEDIUM — Documents that overstate, understate, or are stale [C]

| Where | Defect |
| --- | --- |
| `docs/NCP-2-GUIDE.md:73` | The alt text says "Three cards for the outcomes ok, rejected, and ended, and six cards"; the figure has four outcomes and eight cards. |
| `docs/NCP-2-GUIDE.md:117-118` | 9.1 µs, 38.6 µs, 37.9 µs, 457.8 µs (comparison protocol 1, on battery); the figure `ncp2-why` on the same page and the README say 9.0, 38.8, 36.1, 469 (protocol 2). |
| `README.md:44`, `docs/NCP-2-GUIDE.md:116,169` | "Revision 3 changed the session rules ... have not run again": revision 4 also changed the owner and the client. |
| `docs/design/NCP-2-DESIGN.md:3` | The status line stops at revision 3. |
| `docs/design/NCP-1-SHORTCOMINGS.md:11,33` | "a specification of 362 lines and 3,876 lines of code" (commit `6424fb8`); the specification now has 551 lines plus 169 lines of profiles. |
| `scripts/gen_diagrams.py` (`ncp2_outcomes`) | "an exhaustive check of the real SDKs": only the Python client and owner run in it (`model/README.md`, Limits). |
| `scripts/gen_diagrams.py` (`ncp2_bindings`) | TCP "or with TLS on both sides": the Rust SDK has no TLS (`KNOWN_LIMITATIONS.md`). No lockstep profile in the figure. |
| `conformance/README.md` | "revision 4" for vectors that say `"revision": 3`. |
| `KNOWN_LIMITATIONS.md` | The title is "Known limitations of the NCP 1.0 candidate"; the NCP 2 limits are a section inside it. |

Understated: nothing in the NCP documents says that an exchange gives Haldir the authenticated application acknowledgement that its NCP 1.0 path lacks (section 4).

### S6. LOW — A TypeScript SDK is probably not needed [C]

- Evidence. CREBAIN's TypeScript imports from `@sepahead/ncp`: `ActionBuffer`, `NCP_VERSION`, the type `CommandLike`, and a version guard (`src/hooks/*.ts`, `src/neuro/versionGuard.ts`). These are helpers, not a wire client.

---

## 4. Ecosystem and migration — notes so far (to be written out)

Facts collected:

- Galadriel NCP 1 (`crates/galadriel-ncp`, 27.8k lines): a read-only subscriber of a named sensor route (`.../sensor/galadriel-pid`) with its own `SidecarEnvelope`, plus a monitor route for producer lifecycle, frame closure, and liveness. It uses `ncp_core::Keys`, `ContractStatus`, and `ncp_zenoh::ZenohBus` only. Its payload is "not an NCP wire message".
- Prisoma NCP 1 (`crates/ncp-observer`): a passive tap on the sensor, command, and observation planes; it joins on the driving sensor `StreamPosition {epoch, seq}`.
- CREBAIN's application: `Mode` (Active, Hold, Estop), `ActionBuffer`, `SessionRef`, `AuthorityLease`, `SessionOpened`, `validate_rpc_reply_for`.
- Haldir (`docs/NCP-COMPATIBILITY.md`, `crates/haldir-ncp10/src/lease.rs`, `docs/AUTHORITY-GRAPH.md` on `origin/main`): the Gate issues an NCP 1.0 commander lease (term from a durable boot counter times 2^24, interval 15 to 60 s, rotation at two thirds) to the transport principal and final route of its exclusive-route ACL evidence, and carries it on every command. "The body returns no authority feedback under rc.1". A local publisher `Ok` "stops as application-unobserved ... this path has no enforced in-transit age bound or authenticated application acknowledgement". Its journal states are Called, UnknownAfterPublish, ReturnedError. Haldir's own authority is COSE/Ed25519: signed intents, mission leases, admissions, revocations.
- NCP 1.0 `AuthorityLease`: `session_epoch`, `term`, `lease_id`, `issuer_principal_id`, `holder_principal_id`, `holder_entity_id`, `issued_at_utc_ms`, `expires_at_utc_ms`; at most 60 s; expiry by the receiver's monotonic clock.

Direction of the proposal:

- Message families go into contracts and profiles, not into the core.
- Sensor streams and advisories: NCP 2 streams on the Zenoh binding, with a small stream profile (stream type, announcement in an exchange, heartbeat, end).
- Commands with authority: an exchange with the body as owner and the Gate as its one client. The response is the authenticated acknowledgement; "possibly executed" is UnknownAfterPublish; record-before-send is Called.
- The lease binds to NCP 2 as an authority profile: a term-fenced holder (the lockstep holder with terms, time, and a signed token), bound to the session opening; ESTOP on its own session.
- A passive tap cannot see exchanges. Observers read transcripts, or the body publishes a mirror stream.

---

## 5. Figures — audit so far

Generators: `scripts/gen_diagrams.py` (44 files in `docs/diagrams`), `scripts/plot_perf.py` (`docs/plots`), `benchmarks/comparison/analyze.py`, `benchmarks/multi-agent/figures.py`, `benchmarks/nest-campaign/figures.py`, `docs/local-v1/build.py`. `docs/figures/*.svg` say "exported figure; regenerate from its source", and no generator for them is in the repository.

Every tracked SVG outside `assets/archive` has `role="img"`, one `<title>`, one `<desc>`, and `aria-labelledby` [C, `svg_audit.txt`].

### NCP 2 diagrams (`docs/diagrams/ncp2-*`, light and dark)

| File | Used in | Verdict | Defects |
| --- | --- | --- | --- |
| `ncp2-call` | README, guide | Keep, small fix | Accurate for revision 4 (nonce in card 1). The `open` response label says only "ok, session frame size". No `declined`. README alt says "acknowledgement", guide and figure say "receipt". |
| `ncp2-frame` | guide | Keep | Accurate. Does not show the padding (0 to 7 spaces) or the HMAC variant of the digest. |
| `ncp2-outcomes` | guide | Fix | Figure is current (four outcomes, eight cards); the guide's alt text is stale. "exhaustive check of the real SDKs" overstates (Python only). Cards only: no visual link from event to outcome to verdict. |
| `ncp2-transcript` | guide | Redesign | Shows the session chain, not the transcript: no header, no record fields (kind, time, length, chain value), no end record. Arrows run forward in time; hash references run backward. |
| `ncp2-bindings` | guide | Redesign | Six cards of prose and no drawing. No lockstep profile. TLS claim not true for Rust. Mixes bindings, a pattern, and a profile at one level. |
| `ncp2-loop` | README | Keep | Clear. A result card, dated 12 November 2026 (revision 3 pin at that date; CREBAIN recorded the loop again under revision 4 in `a1df34c`): state the revision. |
| `ncp2-why` | guide | Redesign or remove | A table drawn as a picture, next to the same table in Markdown. Sixteen "Not built in" cells; one-sided. Numbers agree with `results-2/summary.md` [C]. |

### Benchmark plots

| File | Used in | Verdict | Defects |
| --- | --- | --- | --- |
| `comparison/results-2/figures/integrity_*` | README, guide, benchmark README | Keep, small fix | Clear dot plot. At README width the labels are about 9 px. At 1 MiB the claim "fastest" rests on dots that nearly overlap. Text is drawn as paths (not selectable). No revision in the title. |
| `comparison/results-2/figures/calls_*` | not referenced from Markdown (the benchmark README shows `results/`) | Fix | The Rust panel omits gRPC over a Unix socket (35.9 µs), the fastest gRPC arm at N = 0, although the README table has it. |
| `comparison/results-2/figures/{decomposition,tails,versions}_*` | not referenced | Keep or reference | Good. Unused: the READMEs show the protocol-1 versions. |
| `comparison/results/figures/{calls,decomposition,tails}_*` | benchmark README | Keep | Protocol 1 (battery). |
| `comparison/results/figures/versions_*` | guide, benchmark README | Fix | The guide should use `results-2/versions_*` to match its other numbers. |
| `multi-agent/results/figures/fanout_*` | benchmark README | Keep, small fix | Five series in four panels; the y axes differ between the Rust and the Python column. |
| `multi-agent/results/figures/{rounds,mpi}_*` | benchmark README | Keep | Clear. |
| `nest-campaign/results-5/figures/overhead_*` | README, guide, benchmark README | Keep | Clear. |
| `nest-campaign/results-5/figures/spikes_*` | benchmark README | Keep | Clear; the missing NCP 1.0.1 row is explained in the plot. |

All benchmark plots: revision 2 of the SDKs; none says so in the figure.

### NCP 1 figures (viewed; one row each in the final report)

`docs/diagrams/{system-map, evidence-ladder, overview, exchange, payload-transfer, closed-loop, queue-admission, topology, runtime, lifecycle, sequence, admission, ecosystem, versioning, fsm}`, `docs/local-v1/{architecture,step-order}.svg`, `docs/figures/*.svg`, `docs/plots/*.svg`, the logos, and the PDFs. They pass the generator's checks. Each NCP 1 diagram has a status badge ("PROPOSED DESIGN", "CANDIDATE WIRE 1.0", "IMPLEMENTED SDK", "CURRENT RUNTIME"), but none says "NCP 1" in its title, and the NCP 2 diagrams have no badge for "release candidate, revision 4". `system-map` and `evidence-ladder` sit in the README below the NCP 2 section. The single-theme SVGs (`docs/local-v1`, `docs/figures`) have a white background rectangle, so they stay readable in dark mode but do not follow the theme. `topology`, `admission`, and `fsm` hold design knowledge that the authority profile for NCP 2 must carry over (four planes; ESTOP, HOLD, Active admission; the ESTOP latch): keep them as sources until that profile has its own figure.

Resolved since draft 1: the Galadriel row of the uncommitted migration table now names `20ddc41` on `main` (pull request 59, merged at 17:10 UTC), which I confirmed read-only with `gh api repos/sepahead/galadriel/commits/main`.

### New figures (titles so far)

1. NCP 2 ecosystem map: who is client, owner, publisher, subscriber, and transcript reader, and what has moved.
2. Layers of NCP 2: frame, messages, exchange and stream, bindings, profiles, contracts.
3. Owner decision ladder (rules 7.3.1 to 7.3.13) with the code and the client's verdict at each exit.
4. Verdict map: every code and local event to executed, not executed, or possibly executed.
5. Lost session and reopening: why the nonce and rule 7.6.4 exist.
6. Lockstep recovery and takeover.
7. Rounds timeline.
8. Transcript file layout.
9. Evidence map for NCP 2: which property has a proof, a model check, vectors, a fault campaign, and at which revision.
10. Authority over NCP 2 (Haldir Gate, body, lease terms, ESTOP session).
11. Security by binding (who can read, who can send, what protects).

---

## 7. Found sound so far

- The owner rules in the text, in `python/ncp/owner.py`, and in `formal/NCP2/Model.lean` have the same order; `step` is a pure function.
- The chain binding of responses that name no request (revision 4, finding 28): I tried to build a case in which a bound `bad_frame` or `shutdown` response exists for a request that then executes, on one connection and across connections, and found none.
- The model check and its mutation test reproduce exactly as documented (2,591,544 worlds; 12 of 12).
- `formal/README.md`, `model/README.md`, `bindings/zenoh/README.md`, and `KNOWN_LIMITATIONS.md` state their own limits accurately.
- The diagram generator checks text fit, contrast of at least 4.5:1 in both themes, titles, descriptions, and stale files.
- The why-table numbers match `benchmarks/comparison/results-2/summary.md`.
- With two owners on one Zenoh key, verdicts stay truthful (liveness is lost, not safety) [S, reasoned].

---

Draft closed on 14 November 2026: the complete report is `fable-review-rev4.md` in this directory. Where the two differ, the report is correct (the report renumbers the findings: the lockstep finding is D1, the freeze is D2, schemas are D3, decline reasons are D4).
