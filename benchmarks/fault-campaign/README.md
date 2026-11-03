# Fault campaign

This directory holds four protocols. [Protocols 2, 3, and 4](#protocol-2-ncp-2), at the end, test NCP 2; protocol 4 adds Unix domain sockets, TCP, and the Rust client.
Protocol 1, from here on, is a campaign of 22 October 2026 that drives local NCP 1.0.1 sessions into the failures that the profile names.
It asks two questions: what happens in each failure, and does any failure make a client accept a wrong result.
All trials use SDK 1.0.1 with `LocalClient` and a Python or Rust owner on one computer.

[`PROTOCOL.md`](PROTOCOL.md) fixed the trials, design, outcome classes, and hypotheses before the recorded trials (SHA-256 in [`PROTOCOL.sha256`](PROTOCOL.sha256)).
On 24 October 2026, after the trials, the description of `kill-client` was reworded to the repository's wording rules: it now names the trial process, which kills the client. The text fixed before the trials, whose digest `PROTOCOL.sha256` and the schedule record, is in commit `bbe1d42`; the reworded file has the SHA-256 `c16fc877707f7671f929633ef5ea96c9dfda352982ddd401da91d7511388d863`.
[`PROTOCOL-SOAK.md`](PROTOCOL-SOAK.md) fixed a follow-up for memory growth before its runs.

## Computer, software, and times

The computer is the Apple MacBook Pro (Mac16,5, M4 Max, 128 GB, macOS 26.5.1) of the other benchmark records.
It was in normal use: other programs, a complete repository gate, and a mesh-generation job ran at the same time.
The 3816 trials ran on 22 October 2026 from 20:57:26 to 21:18:02 UTC, at the NCP commit `72967c9` with the harness of this directory.
[`results/trials.jsonl`](results/trials.jsonl) holds every trial, and [`results/analysis.json`](results/analysis.json) the classification.

## How a fault is injected

- [`harness/relay.py`](harness/relay.py) sits between the client and the owner and forwards length-prefixed frames.
  It flips one random bit of one random frame, including the four-byte length prefix, or forwards a random proper prefix of the frame and closes that direction.
- [`harness/fault_owner.py`](harness/fault_owner.py) is a Python echo owner that can stall, return a result larger than the frame, raise inside the backend, and record that it retired.
- [`harness/fault_client.py`](harness/fault_client.py) runs one session of `prepare`, six steps, and `finish`, kills the owner at a random moment when asked, and classifies the outcome.
- [`harness/nest_fault.py`](harness/nest_fault.py) does the same with the NEST owner of the NEST campaign: a 2000-neuron Brunel network with 4 threads.
- [`harness/soak.py`](harness/soak.py) runs one long session and samples the memory and the open descriptors of both processes every 0.5 s.

## Results

| Scenario | Owner | Trials | Outcome |
| --- | --- | --- | --- |
| Bit flip, client to owner | Python, Rust | 600 each | All detected |
| Bit flip, owner to client | Python, Rust | 600 each | All detected |
| Truncated frame, client to owner | Python, Rust | 180 each | All detected |
| Truncated frame, owner to client | Python, Rust | 180 each | All detected |
| Owner killed at a random moment | Python | 120 | 109 detected; in 11 the kill came after `finish` |
| Owner killed at a random moment | Rust | 120 | 111 detected; in 9 the kill came after `finish` |
| Client killed at a random moment | Python | 120 | The owner retired and exited in all 120 |
| Step stalls three times the time limit | Python | 30 | All detected after 2.04 to 2.14 s, with a 2 s limit |
| Result larger than the frame | Python | 60 | All `indeterminate`, then retired |
| Request larger than the frame | Python, Rust | 60 each | All refused before any write; the session then completed |
| Backend raises | Python | 60 | All `indeterminate`, then retired |
| NEST owner raises inside a step | NEST | 30 | All `indeterminate`, then retired |
| NEST owner killed during a step | NEST | 30 | All detected as `execution_unknown` |
| Long session | Rust, Python | 3 each | See below |

"Detected" means that the client raised a local error or received `indeterminate`, and then retired.
No trial accepted a wrong result. Of the 3120 frame trials, 3119 damaged a frame; in one trial the chosen frame index was after the end of the session.
24 of the damaged frames had the flip in the length prefix. A larger length made the reader wait until the client's time limit; a smaller one ended the frame early.

### Hypotheses

| Hypothesis | Criterion | Holds |
| --- | --- | --- |
| F1 | No trial accepts a wrong result | yes |
| F2 | Every damaged frame is detected | yes |
| F3 | Every killed client leaves its owner retired and exited | yes |
| F4 | Every stall is detected within the time limit plus 1 s | yes |
| F5 | Oversized results and raising backends end in `indeterminate` and retirement | yes |
| F6 | Oversized requests are refused before any write | yes |
| F7 | In each soak, the memory of client and owner grows by less than 10 percent after the first tenth, and descriptors stay constant | no |

F7 does not hold, and the cause is the harness.
The Rust soak client kept every call time, 8 bytes per call, so its memory grew by 70 to 75 percent over 300,000 calls.
The Python client kept a list of call times and grew by 9 to 12 percent over 60,000 calls.
The owners grew by at most 3.6 percent, and the open descriptors of both processes stayed constant in all six soaks.
The [bounded soak](PROTOCOL-SOAK.md) repeats the soaks with clients that keep a fixed sample of call times; its results are in [`results-soak`](results-soak).

### Bounded soak

Three blocks ran a Rust soak of 1,000,000 lockstep calls and a Python soak of 200,000 calls on 23 October 2026, from 05:26 to 05:33 UTC.
[`analyze_soak.py`](analyze_soak.py) writes [`results-soak/analysis.json`](results-soak/analysis.json).

| Soak | Calls | Median call (µs) | Client memory growth after the first tenth | Owner memory growth after the first tenth | Open descriptors |
| --- | --- | --- | --- | --- | --- |
| Rust, block 0 | 1,000,000 | 38.5 | 0.60 % | 0.56 % | constant |
| Rust, block 1 | 1,000,000 | 38.8 | 0 % | 0 % | constant |
| Rust, block 2 | 1,000,000 | 35.5 | 0 % | 0 % | constant |
| Python, block 0 | 200,000 | 483.2 | 0.62 % | 1.92 % | constant |
| Python, block 1 | 200,000 | 485.0 | 0.49 % | 0 % | constant |
| Python, block 2 | 200,000 | 483.4 | 0.41 % | 2.29 % | constant |

S2 holds: no process opened or lost a descriptor.
S1 does not hold, because one Python owner grew by 2.29 percent, above the 2 percent limit.
That growth is not a leak: the owner's memory rose from 23,024 to 23,552 kB during the first 40 percent of the soak and then stayed constant for the remaining 120,000 calls.
The other two Python owners show the same step earlier.
After the first tenth, the Rust processes grew by at most 0.6 percent, and in blocks 1 and 2 not at all.

## What this does not show

- The trials cover private pipes between processes on one computer, not a network.
- A bit flip that SHA-256 cannot detect is possible in principle; no trial found one, and none is expected.
- The time limit decides how fast a lost length prefix is detected.
- The soak call times of the third block are slower because the machine was busy; they are not a property of NCP.

## Protocol 2: NCP 2

[`PROTOCOL-2.md`](PROTOCOL-2.md) was fixed on 2 November 2026 (SHA-256 in [`PROTOCOL-2.sha256`](PROTOCOL-2.sha256)).
It drives NCP 2 sessions between the NCP 2 Python client and a Python or a Rust owner into damaged, truncated, and repeated frames, killed owners and clients, stalls, oversized results and requests, and raising handlers, and it adds three soaks.
Each owner logs every execution before it runs, and each trial compares that log with what the client learned: no step may run twice or out of order, and no step may be reported as executed or not executed against the log.

Before this protocol was fixed, a review of the client against specification 7.6, rule 7 found that both SDKs let a closed connection escape as an input/output error and left the client usable; commit `c24ff2f` fixed this.

| Path | Content |
| --- | --- |
| [`run2.py`](run2.py), [`analyze2.py`](analyze2.py) | The runner and the analysis of protocol 2 |
| [`harness/relay2.py`](harness/relay2.py) | The relay that flips, truncates, or repeats one NCP 2 frame |
| [`harness/fault_owner2.py`](harness/fault_owner2.py) | The Python owner with injectable faults and an execution log |
| [`harness/fault_client2.py`](harness/fault_client2.py) | One trial: the session, its classification, and the invariants |
| [`harness/soak2.py`](harness/soak2.py) | The soaks, with memory and descriptor samples |

### Results of protocol 2

The 4,170 trials and 9 soaks ran on 2 November 2026 from 20:04 to 20:17 UTC, from the clean commit `6e8944a`, with Python 3.15.0 and Rust 1.99.1, on the computer above.
Every scheduled trial ran. Other programs were running, with one-minute load averages of 3.0 to 14.6 before a trial, and the computer ran on battery; only the detection time of a stall is a time measure.
[`results-2/trials.jsonl`](results-2/trials.jsonl) holds every trial, and [`results-2/analysis.json`](results-2/analysis.json) the analysis.

| Scenario | Owner | Trials | Completed | Ended early | Wrong results |
| --- | --- | ---: | ---: | ---: | ---: |
| Bit flip, client to owner | Python, Rust | 600 each | 0 | 600 each | 0 |
| Bit flip, owner to client | Python, Rust | 600 each | 0 | 600 each | 0 |
| Truncated frame, client to owner | Python, Rust | 180 each | 0 | 180 each | 0 |
| Truncated frame, owner to client | Python, Rust | 180 each | 0 | 180 each | 0 |
| Repeated frame, client to owner | Python / Rust | 90 each | 9 / 13 | 81 / 77 | 0 |
| Repeated frame, owner to client | Python / Rust | 90 each | 12 / 10 | 78 / 80 | 0 |
| Owner killed at a random time | Python / Rust | 120 each | 14 / 88 | 106 / 32 | 0 |
| Client killed at a random time | Python, Rust | 60 each | The owner exited in all 120, after at most 0.037 s | | |
| Step stalls three times the time limit | Python | 30 | 0 | 30 | 0 |
| Result larger than the session bound | Python | 60 | 0 | 60 | 0 |
| Request larger than the session bound | Python, Rust | 60 each | 60 each | 0 | 0 |
| Handler raises | Python, Rust | 60 each | 0 | 60 each | 0 |

| # | Hypothesis | Holds |
| --- | --- | --- |
| E1 | No trial accepts a wrong result. | yes |
| E2 | In every trial, the owner executes each step at most once, in order. | yes |
| E3 | In every trial, what the client learned is true. | yes |
| E4 | Every failure reaches the application as a documented exception. | yes |
| E5 | Every flipped or truncated frame ends the session before it completes. | yes: 3,120 of 3,120 |
| E6 | Every killed client leaves its owner exited within 10 s. | yes: 120 of 120 |
| E7 | Every stall ends with `timeout`, executed `unknown`, within 3 s of the start of the session. | yes: after 2.03 to 2.04 s |
| E8 | Oversized results, raising handlers, and oversized requests end as stated. | yes |
| E9 | In each soak, every call returns the right result, memory grows by less than 10 % after the first tenth, and open descriptors stay constant after the first tenth. | no: see below |

- **Damaged frames.** Of the 2,400 flipped bits, 1,712 were in the JSON region, 396 in the attachments, 212 in the digest, and 80 in the header. Every damaged request ended its session with `bad_frame`, executed `no`. Every damaged response ended the session with a protocol error, or, when a flip enlarged a length, with a timeout; in both cases the last request was reported as possibly executed, and the log showed that it had executed.
- **Repeated frames.** A byte stream does not repeat frames, so these trials test only safety. No step ran twice. When the repeated frame was the last one of the session, the session completed (44 trials). Otherwise the client met a response that did not answer its next request and ended the session with a protocol error; the step that it had just sent was the uncertain one.
- **Killed owners.** A session with the Rust owner takes a few milliseconds, so the kill often came after the session had ended (88 of 120). In every other trial, the last request was reported as possibly executed, and no other step was uncertain.

**A defect of the harness, found after the runs.** The client chose the frame with `random.Random(seed)`, and the relay drew the bit or the cut with a new `random.Random(seed)` from the same seed.
Both first draws come from the same random number, so a flipped bit or a cut fell into the part of the frame's range that the frame's index selected, unless the relay's first draw fell beyond the end of the frame.
All 80 flips in a header hit the first frame of a direction, the `open` request or response, and 25 of them made a length larger, so that the session ended with a timeout after 2 s; no flip hit the header of a step.
The protocol says that one random bit anywhere in the frame is flipped. Every damaged frame was still detected (E5), but these trials did not cover flips in the header of a step, and the positions were not independent of the frame.
[Protocol 3](PROTOCOL-3.md) repeats the trials with independent draws.

E9 does not hold by its criterion, for one sample. In the second soak of the Rust client, the last sample, at 9.30 s of a 9.91 s soak, read 1 open descriptor of the owner instead of 6: the client had finished its 1,000,000 calls, and the owner was exiting. Every other sample of all nine soaks had constant descriptors, every call returned the right result, and memory grew by at most 0.69 % (client) and 0 % (owner) after the first tenth.
The criterion did not exclude samples taken while the processes exit; this protocol is not changed after its runs.

| Soak | Calls | Median call (µs) | Client memory growth | Owner memory growth | Open descriptors, client / owner |
| --- | ---: | ---: | ---: | ---: | --- |
| Python client, Python owner, blocks 0 to 2 | 200,000 | 35.2, 40.2, 40.2 | 0.06 %, 0 %, 0 % | 0 % | 30 / 24 |
| Python client, Rust owner, blocks 0 to 2 | 1,000,000 | 20.5, 20.6, 20.1 | 0.06 %, 0.06 %, 0.19 % | 0 % | 30 / 6 |
| Rust client, Rust owner, blocks 0 to 2 | 1,000,000 | 9.2, 8.8, 9.0 | 0 %, 0.68 %, 0.69 % | 0 % | 8 / 6, and 1 in the last sample of block 1 |

## Protocol 3: NCP 2, with independent draws

[`PROTOCOL-3.md`](PROTOCOL-3.md) was fixed on 2 November 2026 (SHA-256 in [`PROTOCOL-3.sha256`](PROTOCOL-3.sha256)).
It repeats protocol 2 after the fix of the defect above: the relay draws its bit or cut from a seed of its own.
It also leaves the last sample of each soak out of the check of the open descriptors, because that sample can fall while the processes exit.
`run2.py --protocol 3` runs it.

### Results of protocol 3

The 4,170 trials and 9 soaks ran on 2 November 2026 from 20:24 to 20:44 UTC, from the clean commit `27914c6`, with Python 3.15.0 and Rust 1.99.1, on the computer above.
Every scheduled trial ran. Other programs were running, with one-minute load averages of 2.6 to 30.7 before a trial, and the computer ran on battery.
[`results-3/trials.jsonl`](results-3/trials.jsonl) holds every trial, and [`results-3/analysis.json`](results-3/analysis.json) the analysis.
All nine hypotheses hold.

| Scenario | Owner | Trials | Completed | Ended early | Wrong results |
| --- | --- | ---: | ---: | ---: | ---: |
| Bit flip, client to owner | Python, Rust | 600 each | 0 | 600 each | 0 |
| Bit flip, owner to client | Python, Rust | 600 each | 0 | 600 each | 0 |
| Truncated frame, client to owner | Python, Rust | 180 each | 0 | 180 each | 0 |
| Truncated frame, owner to client | Python, Rust | 180 each | 0 | 180 each | 0 |
| Repeated frame, client to owner | Python / Rust | 90 each | 10 / 12 | 80 / 78 | 0 |
| Repeated frame, owner to client | Python / Rust | 90 each | 7 / 15 | 83 / 75 | 0 |
| Owner killed at a random time | Python / Rust | 120 each | 13 / 76 | 107 / 44 | 0 |
| Client killed at a random time | Python, Rust | 60 each | The owner exited in all 120, after at most 0.064 s | | |
| Step stalls three times the time limit | Python | 30 | 0 | 30 | 0 |
| Result larger than the session bound | Python | 60 | 0 | 60 | 0 |
| Request larger than the session bound | Python, Rust | 60 each | 60 each | 0 | 0 |
| Handler raises | Python, Rust | 60 each | 0 | 60 each | 0 |

| # | Hypothesis | Holds |
| --- | --- | --- |
| E1 | No trial accepts a wrong result. | yes |
| E2 | In every trial, the owner executes each step at most once, in order. | yes |
| E3 | In every trial, what the client learned is true. | yes |
| E4 | Every failure reaches the application as a documented exception. | yes |
| E5 | Every flipped or truncated frame ends the session before it completes. | yes: 3,120 of 3,120 |
| E6 | Every killed client leaves its owner exited within 10 s. | yes: 120 of 120 |
| E7 | Every stall ends with `timeout`, executed `unknown`, within 3 s of the start of the session. | yes: after 2.03 to 2.05 s |
| E8 | Oversized results, raising handlers, and oversized requests end as stated. | yes |
| E9 | In each soak, every call returns the right result, memory grows by less than 10 % after the first tenth, and open descriptors stay constant after the first tenth, except in the last sample. | yes |

- **Damaged frames.** Of the 2,400 flipped bits, 1,661 were in the JSON region, 402 in the attachments, 237 in the digest, and 100 in the header, and every frame position of both directions received header flips (7 to 21 each). A damaged request ended its session with `bad_frame`, executed `no`. When a flip made a length larger (24 frames), the receiver waited for bytes that never came, and the client ended the session after its 2 s time limit with the request possibly executed; the logs show that the 11 such step requests did not execute and the 8 such responses answered steps that did. A damaged response otherwise ended the session with a protocol error, and its step had executed.
- **Repeated frames, killed owners, and the other scenarios** behaved as in protocol 2: no step ran twice, and at most the last step that the client sent was uncertain.
- **Soaks.** The median call times vary with the load of the other programs (for example 20.0 µs in the second Rust soak against 8.7 and 9.4 µs in the others); they are not timing results.

| Soak | Calls | Median call (µs) | Client memory growth | Owner memory growth | Open descriptors, client / owner |
| --- | ---: | ---: | ---: | ---: | --- |
| Python client, Python owner, blocks 0 to 2 | 200,000 | 38.9, 52.9, 34.3 | 0.06 %, 0 %, 0.06 % | 0 %, 0 %, 0.19 % | 30 / 24 |
| Python client, Rust owner, blocks 0 to 2 | 1,000,000 | 20.7, 20.0, 20.5 | 0.06 % each | 0 % | 30 / 6 |
| Rust client, Rust owner, blocks 0 to 2 | 1,000,000 | 9.4, 20.0, 8.7 | 0.69 %, 0 %, 0.67 % | 0 % | 8 / 6 |

## Protocol 4: NCP 2 over sockets and with the Rust client

[`PROTOCOL-4.md`](PROTOCOL-4.md) was fixed on 3 November 2026 (SHA-256 in [`PROTOCOL-4.sha256`](PROTOCOL-4.sha256)).
It runs the scenarios of protocol 3, without the soaks, over a Unix domain socket and over TCP, with the Python client and with a new Rust client ([`harness/rust-client`](harness/rust-client/src/main.rs)), against the Python and the Rust owner: 4,560 trials in three blocks.
The owners run as servers, a relay over sockets ([`harness/relay_socket.py`](harness/relay_socket.py)) changes frames, and after a killed client the trial checks that the owner serves a new session within 10 s.
`run4.py` runs it, and `analyze4.py` applies its criteria.

The results of protocol 4 follow once its trials have run.
