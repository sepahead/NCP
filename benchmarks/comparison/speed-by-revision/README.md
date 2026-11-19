# Speed of NCP 2 by revision

This directory holds a diagnostic, not a preregistered protocol. It tests no hypothesis.

[Comparison protocol 3](../README.md#results-of-protocol-3) found that one small call of
revision 7 took 1.2 times as long in Rust and 1.5 times as long in Python as with the SDKs
of comparison protocol 2. That comparison has only two points. This diagnostic times the SDKs
of each revision between them, to find which revision changed the time and by how much.

The runner was committed and pushed (commit `47529d3`) before its recorded runs.

## Method

The diagnostic times eight commits:

| Commit | SDKs | Date |
| --- | --- | --- |
| `c701f56` | Comparison protocol 2 | 2 November 2026 |
| `5300f70` | Revision 1 | 11 November 2026 |
| `8940721` | Revision 2 | 13 November 2026 |
| `9f58e7a` | Revision 3 | 13 November 2026 |
| `2e24ef5` | Revision 4 | 13 November 2026 |
| `7edc3f9` | Revision 5 | 14 November 2026 |
| `28fb8cc` | Revision 6 | 15 November 2026 |
| `727289e` | Revision 7 | 17 November 2026 |
| `9df6b71` | Revision 7 with the speed changes | 19 November 2026 (second run only) |

The SDK code did not change between `727289e` and the commit of comparison protocol 3.

The first run, in the directory `results`, timed the first eight commits. The speed changes of
`9df6b71` came from its findings. A second run, in the directory `results-2`, times all nine
commits with the same method, so that the effect of the speed changes is measured with
alternating runs. The runner of the second run was committed before that run.

For each commit, [`run_bisection.py`](run_bisection.py) exports `python/` and `rust/` with
`git archive`. Each run uses the client and the echo owner of the same commit:

- **Rust:** the examples `bench_client` and `echo_owner` of the Rust SDK, built with
  `cargo build --release --locked --examples`. A run makes 2,000 warm-up calls and then
  20,000 timed calls.
- **Python:** [`py_client.py`](py_client.py) and `python/tests/echo_owner.py` of the
  commit, with Python 3.15.0. A run makes 300 warm-up calls and then 3,000 timed calls.
  The client uses the interface that its SDK has, because revision 3 changed the
  interfaces.

Each call sends the request `spikes` with `n` equal to 0 over a pipe to a child owner, as
`bench_client` does. The owner answers with the body `{"count": 13}`.

The runs alternate:

- In each of 20 rounds, the runs of all commits in both languages start in a random order,
  with the seed 20261119. A slow period of the computer thus falls on all commits alike.
- The conditions are those of comparison protocols 3 and 4 ([`conditions.py`](../../conditions.py)).
  Before each run, the one-minute load average is below 8 and a core runs at 4.0 GHz or more.
  The computer can run on battery with 10 percent or more.
- A disturbed run starts again, up to three attempts. The records keep every attempt.

The measure of a run is the median of its call times. For each commit and language, the
summary gives the median and the quartiles of the run medians.

### The second parse in the Python decoder

Since 23 October 2026 (commit `d7aa89f`), the Python frame decoder parses a frame a second
time when its text contains `-0` that a regular expression matches. The second parse tells
the integer `-0`, which the specification forbids, from the same characters in a string.
The expression also matches characters in a string. Every frame carries the session
identifier, a random UUID. When a group of the UUID starts with `0` and a letter other than
`e`, every frame of the session pays the second parse. Before the runs, this occurred in 12,
15, and 8 of 300 sessions with the SDKs of protocol 2, revision 2, and revision 7: about 4
percent, as the probability 2/16 × 5/16 of two such groups predicts.

The Python client counts the parses of its decoder during the warm-up calls, without the
timed calls. The summary gives runs with the second parse separately, and keeps them out of
the medians. The Rust decoder reads `-0` as a token and has no second parse.

### Function calls

`run_bisection.py count` runs the Python client and owner under `cProfile`, with sessions of
1,000 and 3,000 calls. The difference of the two sessions, divided by 2,000, gives the
function calls for each exchange, in the client and in the owner. A built-in function counts
for the module that called it. A session with the second parse is drawn again. Function
calls are a measure of work that does not depend on the load of the computer. They are not
times.

## Limits

- One computer: Apple M4 Max with macOS 26.5.1. One call at a time, over pipes only.
- The clients are not those of the comparison harness. Compare the steps between commits
  in this diagnostic, not its absolute times with those of protocols 2 and 3.
- The diagnostic makes no correction for many comparisons and tests no hypothesis.

## Run it

```sh
python3 benchmarks/comparison/speed-by-revision/run_bisection.py prepare WORK
python3 benchmarks/comparison/speed-by-revision/run_bisection.py run WORK OUT --rounds 20 --python python3
python3 benchmarks/comparison/speed-by-revision/run_bisection.py count WORK OUT --python python3
python3 benchmarks/comparison/speed-by-revision/run_bisection.py report OUT
```

`WORK` holds the exported trees and the builds. `OUT` receives `schedule.json`,
`runs.jsonl`, `counts.json`, `summary.json`, and `summary.md`.

## Results

The runs took place on 19 November 2026, with the runner at commit `47529d3`. All 320 runs
completed on the power adapter, and none was disturbed. The one-minute load average before a
run was at most 5.95. The directory [`results`](results/summary.md) holds every run.

The table gives the median of the 20 run medians for each commit. The function calls are those
of the client and the owner together.

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

- **Revision 3 made the call slower.** In Rust, revision 3 adds 0.9 µs of the 1.0 µs between
  protocol 2 and revision 7. In Python, it adds 19.6 µs of 24.7 µs.
- **Revisions 1, 2, and 4 to 7 are within the spread of the runs.** In Python, the quartiles of
  the run medians of revisions 3 to 7 overlap: 59.7 to 65.7 µs for revision 3, and 63.3 to
  67.0 µs for revision 7. In Rust, they are 10.2 to 10.7 µs for both.
- **The function calls agree.** Revision 3 adds 92 Python calls to each exchange. Revisions 4 to
  7 add 7, five of them in the owner's message checks.

Revision 3 adds these Python calls to each exchange (client, owner):

| Module | Client | Owner | Work |
| --- | ---: | ---: | --- |
| `dataclasses` and generated `__init__` | +29 | +14 | Copies of the immutable state: two in the client, one in the owner |
| `ncp/frame.py` | +12.5 | +12.5 | Selection of SHA-256 or HMAC-SHA-256 for each frame, and a new parse layer |
| `ncp/messages.py` | +10 | +10 | The form check of each response and of each request |
| `ncp/contract.py` | | +5 | The schema check of each request body |
| `ncp/events.py` | +1 | +1 | One observer event for each call |
| `ncp/client.py`, `ncp/owner.py`, `ncp/exchange.py`, `ncp/binding.py` | −2 | −1 | The drivers moved from `exchange.py` to the state machines |

### Second run

The second run took place on 19 November 2026, with the runner at commit `47a61a4`, on the power adapter. All 360 runs completed, and none was disturbed. The directory [`results-2`](results-2/summary.md) holds every run.

| Commit | SDKs | Rust median (µs) | Step | Python median (µs) | Step | Python calls for each exchange |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `c701f56` | Protocol 2 | 9.1 | | 35.3 | | 190 |
| `5300f70` | Revision 1 | 9.1 | +0.0 | 35.8 | +0.5 | 193 |
| `8940721` | Revision 2 | 9.0 | −0.0 | 37.1 | +1.2 | 193 |
| `9f58e7a` | **Revision 3** | **9.7** | **+0.7** | **60.5** | **+23.4** | **286** |
| `2e24ef5` | Revision 4 | 9.7 | −0.0 | 59.5 | −1.0 | 290 |
| `7edc3f9` | Revision 5 | 9.7 | +0.0 | 59.4 | −0.0 | 288 |
| `28fb8cc` | Revision 6 | 9.8 | +0.1 | 61.1 | +1.7 | 292 |
| `727289e` | Revision 7 | 9.8 | +0.0 | 60.0 | −1.1 | 292 |
| `9df6b71` | **Speed changes** | **9.8** | **−0.0** | **53.6** | **−6.4** | **245** |

- **The first run holds again.** Revision 3 is again the one large step: 0.7 µs in Rust and 23.4 µs in Python.
- **The speed changes recover a part of the Python cost.** They remove 6.4 µs of the 22.9 µs that revisions 3 to 7 added in Python, and 47 of the 99 function calls that they added to each exchange.
- **The Rust changes have no measurable effect on one call.** The Rust changes remove copies of strings and of the response body, and the events that the default observer drops. Over a pipe, their effect is below the spread of the runs.
- The absolute times are lower than in the first run in both languages. Both runs were on the power adapter. The median one-minute load average before a run was 3.8, against 4.9 in the first run. The steps between commits agree.

### Ratios against the comparison benchmark

This diagnostic finds revision 7 1.11 times slower in Rust and 1.60 times slower in Python than
the SDKs of protocol 2. Comparison protocol 3 found 1.22 and 1.69 (11.0 against 9.0 µs, 65.6
against 38.8 µs). The clients differ: protocol 3 used the clients of the comparison harness.
Revision 3 is the one large step in both measurements.

### The second parse

Four Python runs drew a session with the second parse: one with the SDKs of protocol 2, two of
revision 5, and one of revision 6. Their medians were 2.4 to 3.6 µs above the median of their
commit. Four runs are too few for an exact cost.
