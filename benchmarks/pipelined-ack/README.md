# Pipelined acknowledgement

This directory analyses one possible change to the local lockstep profile: sending the acknowledgement of one call together with the next request.
It holds the design, an exhaustive model check, a test of the model against the real owner, and a timing benchmark.
Nothing here is part of the v1 profile or of an SDK interface.

## The v1 rule and what it costs

The v1 descriptor states that only a verified acknowledgement advances the client's sequence.
A lockstep call is therefore two round trips: the request with its response, then the acknowledgement with its response.
With SDK 1.0.1, a Rust call takes about 41 µs, of which about 15 µs are the two round trips.

## The design

A pipelined client writes acknowledgement n and request n+1 back to back, then reads both responses.
The owner needs no change: it handles frames in order, and it already rejects a new sequence with `result_pending` while a result is retained.
If acknowledgement n fails, request n+1 is therefore rejected before execution.
The client rule changes: the client may send request n+1 after it has sent, but not yet verified, acknowledgement n, and it must treat request n+1 as unknown until it has verified the response.

## Safety

[`model/model_check.py`](model/model_check.py) explores every interleaving of client steps, owner steps, and faults for three clients and checks six properties in every reachable state.

| Property | Meaning |
| --- | --- |
| P1 | The owner executes each sequence at most once. |
| P2 | The owner executes sequences 1, 2, ... without gaps. |
| P3 | The owner executes n+1 only after it accepted the acknowledgement of n with the result identity of n. |
| P4 | A sequence that the client records as committed was executed once, with the recorded result. |
| P5 | A sequence that the client records as not executed was not executed. |
| P6 | The client sends request n+1 only after it verified the response to acknowledgement n (the v1 rule). |

The faults are frame corruption, a valid but wrong acknowledgement, owner crash, client crash, and client timeout.

| Client | Steps, faults | Reachable states | Violated properties |
| --- | --- | --- | --- |
| Sequential (v1) | 4, 2 | 310 | none |
| Deferred (v1-compliant) | 4, 2 | 310 | none |
| Pipelined | 4, 2 | 451 | P6 only |
| Sequential (v1) | 3, 3 | 335 | none |
| Deferred (v1-compliant) | 3, 3 | 335 | none |
| Pipelined | 3, 3 | 553 | P6 only |

The pipelined client keeps every safety property and breaks only the v1 client rule, as designed.
The deferred client sends the acknowledgement without waiting for its response and verifies that response before it sends the next request; on the wire it is the same as the sequential client.

The mutation self-test checks that the model detects defects:

| Deliberate defect | Detected by | Detected with |
| --- | --- | --- |
| The owner executes a new sequence while a result is retained | P3 | the pipelined client only |
| The owner releases a result for any acknowledgement of its sequence | P3 | all three clients |
| A retiring client records dispatched requests as not executed | P5 | all three clients |

The first row is the main finding of the analysis: a pipelined client depends on the owner's `result_pending` guard, which a sequential client never exercises.
A pipelined profile must therefore make that guard a named requirement with its own conformance cases.
[`model/conformance.py`](model/conformance.py) compares the model's owner with the real Python `LocalOwner` on random traces of requests and of correct and wrong acknowledgements.
In the validity run of this record, the two agreed on all 20,000 traces, 130,202 frames, with SDK 1.0.1 (`results/validity.json`).
Development runs before the record, which are not retained, also used SDK 1.0.0.

## Measured benefit

[`PROTOCOL.md`](PROTOCOL.md) fixed the configurations, design, and hypotheses before the timed runs (SHA-256 in [`PROTOCOL.sha256`](PROTOCOL.sha256)).
Every run used SDK 1.0.1 at NCP commit `99e9adc` and an echo owner, with 500 warm-up calls and 3000 timed calls.
The model check, the mutation self-test, and the conformance test ran first and passed; otherwise no timed run would have started.
Three blocks of 20 configurations, each block in a shuffled order, ran on 23 October 2026 from 03:01:54 to 03:03:38 UTC on the Apple MacBook Pro (Mac16,5, M4 Max) of the other records.
The one-minute load average before a run was 2.6 to 4.1, because other programs were running.
[`results/runs.jsonl`](results/runs.jsonl) holds every run and [`results/analysis.json`](results/analysis.json) the summary.

| Client and owner | Spikes per step | Sequential median (µs) | Pipelined median (µs) | Ratio, median of 3 blocks | Pipelined lower in every block |
| --- | --- | --- | --- | --- | --- |
| Rust, Rust | 0 | 35.6 | 31.9 | 1.11 | yes |
| Rust, Rust | 127 | 68.7 | 53.4 | 1.28 | yes |
| Rust, Python | 0 | 209.9 | 203.3 | 1.04 | yes |
| Rust, Python | 127 | 658.0 | 651.3 | 1.01 | yes |
| Python, Rust | 0 | 246.8 | 226.8 | 1.09 | yes |
| Python, Rust | 127 | 601.6 | 545.0 | 1.10 | yes |
| Python, Python | 0 | 466.2 | 335.3 | 1.40 | yes |
| Python, Python | 127 | 1220.6 | 1029.2 | 1.18 | yes |

The medians in the table are the medians of the three block medians.
H1, H2, and H3 hold: pipelining was faster in every block for both same-language pairs without spikes, and the Rust pair saved 3.6 µs, more than the 3 µs threshold.
The `sdk` configurations, which call `LocalClient.call`, took 454 µs and 259 µs for the Python client with the Python and the Rust owner; the sequential harness is within 5 percent of them.

The savings are larger than one round trip, which costs about 7 µs in Rust and 15 µs in Python.
The pipelined client verifies the acknowledgement response while the owner already executes the next request, so the work of the two processes overlaps instead of alternating.
The overlap helps most when both sides do much work per message, as with two Python processes.
A Rust client with a Python owner gains least, because the owner's work dominates and the Rust client has little work to overlap with it.

## Adoption path

Pipelining would need a new profile identity: a new descriptor with the changed client rule and the owner guard as a named requirement, support in both SDKs, cross-language conformance cases, and a release.
This directory provides the safety argument and the measured benefit for that decision. It does not make it.

## What this does not show

- The model has three clients and bounded steps and faults. It is exhaustive within those bounds, not a proof for every length.
- The conformance test compares the model with the Python owner only. A pipelined profile would need the same test for the Rust owner.
- The timing uses echo owners on one computer under load. A simulation step that takes milliseconds makes the saving small in relative terms.
