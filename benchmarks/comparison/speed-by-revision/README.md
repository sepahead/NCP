# Speed of NCP 2 by revision

This directory holds a diagnostic, not a preregistered protocol. It tests no hypothesis.

[Comparison protocol 3](../README.md#results-of-protocol-3) found that one small call of
revision 7 took 1.2 times as long in Rust and 1.5 times as long in Python as with the SDKs
of comparison protocol 2. That comparison has only two points. This diagnostic times the SDKs
of each revision between them, to find which revision changed the time and by how much.

The runner was committed and pushed before its recorded runs.

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

The SDK code did not change between `727289e` and the commit of comparison protocol 3.

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

- In each of 20 rounds, the 16 runs (eight commits, two languages) start in a random order,
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

The results follow in a later commit, in the directory `results`.
