# Status of NCP 2

This document gives the state of NCP 2 on 19 November 2026 in plain words. It answers two
questions: whether NCP 2 is final and ready for production, and why revision 7 is slower than
the SDKs of comparison protocol 2.

The [release record](release/NCP-2.0.0.md#gates-for-the-tag) lists each gate for the tag with
its evidence. If this document and the release record differ, the release record is correct.

## Summary

NCP 2 is a release candidate. It is not final, and it is not ready for production use.

- The specification is at revision 7. The packages are `2.0.0rc7` (Python) and
  `2.0.0-rc.7` (Rust).
- There is no tag, no published package, and no signature.
- The exchange has strong evidence for its correctness: proofs, model checks, fault campaigns,
  and exact content with NEST. Nearly all of the evidence comes from one computer and one
  author.
- Revision 3 made one small call slower, in both SDKs. The cost was not measured until five days
  later. Section [Why revision 7 is slower](#why-revision-7-is-slower) gives the cause.

## What the evidence shows

| Evidence | Result for revision 7 | Where |
| --- | --- | --- |
| Proofs | Nineteen claims about the owner and a client that obeys the rules, in Lean, with the three standard axioms only. Eleven injected defects each break the claim that forbids them. | [`formal/`](../formal/README.md) |
| Model check of the exchange | The Python client and owner, with up to two faults: 5,150,954 states, every property holds. | [`model/`](../model/README.md) |
| Model check of the lockstep profile | 565,424 worlds with one fault in the gate. 13,621,815 worlds with two faults, outside the gate. | [`model/`](../model/README.md) |
| Fault campaigns | 4,560 trials over Unix domain sockets and TCP (protocol 6) and 960 trials over Zenoh (protocol 7): no wrong result, and every verdict true against the owner's execution log. | [Fault campaign](../benchmarks/fault-campaign/README.md) |
| Exact content with NEST | 216 trials of eight networks of seven NEST neuron models: every spike, offset, and membrane-potential sample arrived bit for bit. | [NEST campaign](../benchmarks/nest-campaign/README.md#results-of-content-protocol-3) |
| Speed | Comparison protocols 3 (420 runs) and 4 (84 runs, against iceoryx2). | [Comparison benchmark](../benchmarks/comparison/README.md) |
| Tests | Both NCP 2 gates run on Linux and macOS in hosted CI on each push. | [`check_ncp2.sh`](../scripts/check_ncp2.sh) |
| Release build | Two builds give the same files. A build at commit `1e08ee6` gave the recorded `SHA256SUMS` again. | [Release record](release/NCP-2.0.0.md#artifacts) |

Limits of this evidence:

- The fault campaigns, the NEST campaign, and the benchmarks ran on one Apple M4 Max computer
  with macOS, mostly over loopback. Only the test gates ran on Linux.
- One author wrote the specification and both SDKs. Model reviews are advisory and are not
  certification evidence.
- Local evidence is not independent evidence.

## What blocks the tag

1. **The scope of the freeze.** The owner decides which parts the tag freezes. This decision
   is OPEN. The advisory design review of revision 6 recommends to freeze the exercised core
   and to keep streams, the Zenoh binding, schemas, the key and TLS guidance, and both profiles
   provisional.
2. **Speed.** Fix the cost of revision 3, or accept it on purpose. Then run the comparison
   benchmark again.
3. **Evidence that is NOT RUN for revision 7:**
   - the NEST and multi-agent timings,
   - a benchmark of the Zenoh binding,
   - a model check of the rounds profile,
   - an implementation by another author,
   - an external review,
   - signatures, an SBOM, and provenance.
4. **Consumers.** No consumer uses streams, the Zenoh binding, contract schemas, authenticated
   frames, feature operations, decline reasons, or a profile.

The design changed quickly. Revisions 1 to 7 came between 11 and 17 November 2026. Revisions 4
to 7 came from advisory reviews:

- Revision 4 changed the exchange: a response that names no request is now bound to the
  session and to the last acknowledged response.
- Revisions 5 and 6 changed the lockstep profile and added feature operations.
- Revision 7 added decline reasons and the code `conflict`.

If the SDKs change before the tag, the fault campaigns, the NEST content runs, and the
comparison benchmark must run again ([migration plan](design/NCP-2-MIGRATION.md#open-work-after-revision-7), item 2).

## What production use needs after the tag

A tag makes NCP 2 a stable version for research use. Production use needs more:

- an implementation by another author and an external review of the specification and of the
  security model,
- signed packages with an SBOM and provenance,
- qualification on Linux, between computers, and under sustained load,
- consumers that use NCP 2 for their main paths.

Three projects use NCP 2 for some of their parts, all at revision 4 (pin `2e24ef5`): CREBAIN
(the native simulation and the NEST controller), Prisoma (the loop capture), and Galadriel (the
local adapter). Haldir, Engram, and the other parts of these projects use NCP 1. They wait for a
stream profile and an authority profile, which do not exist yet ([migration plan](design/NCP-2-MIGRATION.md#open-work-after-revision-7), items 4 and 5).

NCP 2 makes no claim of real-time behavior or of physical safety. An NCP stop is not a
certified emergency stop ([known limitations](../KNOWN_LIMITATIONS.md)).

## Path to the tag

1. The owner decides the scope of the freeze.
2. Fix the cost of revision 3 or accept it, and run the comparison benchmark again.
3. If the SDKs changed, run fault-campaign protocols 6 and 7 and NEST content protocol 3 again.
4. Run the NEST timings with the final revision.
5. Get both gates in hosted CI at the commit that the tag names.
6. The owner tags and publishes ([owner steps](release/NCP-2.0.0.md#owner-steps)).

## Why revision 7 is slower

### The measurement

Comparison protocol 3 found one small call of revision 7 1.2 times slower in Rust and 1.5
times slower in Python than with the SDKs of comparison protocol 2 (11.0 against 9.0 µs, and
65.6 against 38.8 µs). Every other system kept its time within 3 percent. The computer did not
change.

The [speed bisection](../benchmarks/comparison/speed-by-revision/README.md) timed the SDKs of
each revision between the two, in 20 alternating rounds on 19 November 2026 (median of the run
medians, in µs, and Python function calls for each exchange):

| Commit | SDKs | Rust median (µs) | Step | Python median (µs) | Step | Python calls for each exchange |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `c701f56` | Protocol 2 | 9.4 | | 41.2 | | 190 |
| `5300f70` | Revision 1 | 9.4 | +0.0 | 41.6 | +0.4 | 193 |
| `8940721` | Revision 2 | 9.5 | +0.1 | 42.4 | +0.8 | 193 |
| `9f58e7a` | **Revision 3** | **10.4** | **+0.9** | **62.1** | **+19.6** | **285** |
| `2e24ef5` | Revision 4 | 10.3 | −0.1 | 66.5 | +4.4 | 290 |
| `7edc3f9` | Revision 5 | 10.2 | −0.0 | 63.7 | −2.7 | 288 |
| `28fb8cc` | Revision 6 | 10.3 | +0.1 | 62.9 | −0.8 | 292 |
| `727289e` | Revision 7 | 10.4 | +0.1 | 65.9 | +3.0 | 292 |

Revision 3 is the one large step. In Rust, it adds 0.9 µs of the 1.0 µs. In Python, it adds
19.6 µs of 24.7 µs. The steps of revisions 1, 2, and 4 to 7 are within the spread of the runs.
Revision 7 itself added almost nothing: 0.1 µs in Rust, and in Python a step inside the spread.
The release candidate is slower because it contains revision 3.

### Why revision 3 changed the SDKs

Revision 3 was a correctness change. A review of revision 2 from first principles found that a
client could be told something false. An exhaustive check of the SDKs found one more case.
For example, a delayed copy of `open` could open a lost session again. The next call then got a
rejection, and the client said "not executed", although an earlier copy of the request could
have run.

The [design record](design/NCP-2-DESIGN.md#12-revision-3) gives the reason for the new structure:
each SDK mixed the rules with input and output, so that a check could not run the real rules.
Revision 3 rebuilt both SDKs around pure state machines:

- the owner: `step`,
- the client: `request`, `receive`, `time_out`, and `closed`.

A pure state machine takes a state and an input, and returns a new state and an output. It does
no input or output itself. The blocking drivers, the servers, the Zenoh bindings, the model
check, and the vectors all drive the same functions. This design gives the evidence above:

- The model check runs the real Python client and owner through 5,150,954 states.
- The conformance check compares the Python and Rust owners with the compiled Lean model on
  20,000 random traces by default.

### Where the time goes

Revision 3 also added work that every call does. In Python:

- **State copies.** The state of the client and of the owner is an immutable dataclass. Each
  transition makes a new state with `dataclasses.replace`. A call makes two copies in the
  client and one in the owner.
- **Message checks.** The client checks the form of each response (`check_response`), and the
  owner checks the form of each request (`check_request`).
- **Schema check.** The owner checks each request body against the schema of its operation in
  the contract.
- **Keys.** The frame codec selects SHA-256 or HMAC-SHA-256 for each frame, for the optional
  authenticated frames.
- **Events.** The client and the owner each report one event for each call to an observer.

The Rust SDK does the same work: it clones the state in each transition, keeps a copy of each
request frame for a resend, builds an `Event` with owned strings for an observer that by
default prints only errors, and checks each message and each request body.

The Python function calls show the same. Revision 3 adds 92 calls to each exchange: 43 for
state copies, 25 in the frame codec, 20 for message checks, 5 for the schema check, and 2 for
events. Revisions 4 to 7 add 7 more. The [bisection](../benchmarks/comparison/speed-by-revision/README.md#results)
gives the table.

### Was it an experiment

No. Revision 3 was a planned change for correctness and for verification, and it was kept on
purpose. Its cost was not measured, because no benchmark ran with an SDK change:

- The commit of revision 3 says: "The benchmarks and the fault campaign ran with revision 2 of
  the SDKs and have not run again."
- The first measurement of the cost was comparison protocol 3 on 18 November 2026, after
  revision 7.

The gap is in the process, not in the design. A change of the SDKs had no speed check.

### The second parse of the Python decoder

The bisection also found a cost that is older than revision 1. Since 23 October 2026, the Python
frame decoder parses a frame a second time when its text contains `-0` that a regular
expression matches. The check is for the integer `-0`, which the specification forbids. The
expression also matches characters in a string. The session identifier is a random UUID, and
when a group of it starts with `0` and a letter other than `e`, every frame of that session pays
the second parse. This occurs in about 4 percent of sessions.

Four runs of the bisection had such a session. Their medians were 2.4 to 3.6 µs above the
median of their commit. This cost is small, but it makes some Python runs slower at random.

### What can recover the time

These changes can make a call faster without a change of the wire or of a verdict. Each is a
hypothesis until a measurement confirms it:

- In Python, change the state in place in the blocking driver, or copy it without
  `dataclasses.replace`. Keep the pure functions for the model check.
- Build an event only when the observer wants events.
- In Rust, borrow the request frame for a resend, or share it, and do not clone the state.
- In Python, make the check for `-0` ignore the characters inside strings.

A change of the SDKs needs the evidence again: the fault campaigns, the NEST content runs, and
the comparison benchmark. The speed bisection can then run as a check for each change of the
SDKs.
