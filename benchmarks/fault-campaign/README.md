# Fault campaign

This directory holds a campaign of 22 October 2026 that drives local NCP sessions into the failures that the profile names.
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
