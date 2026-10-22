# Local SDK exchange benchmark

This directory holds two recorded runs of 22 October 2026.
They measure one lockstep call of the local SDKs: one request with its verified response, and one acknowledgement with its verified response.
They separate the transport time from the SDK time and compare the released SDK 1.0.0 with SDK 1.0.1.

The results describe these implementations under an echo workload on one computer.
They give no real-time bound and no worst-case bound. They do not rank NCP against another protocol.

| Run | Protocol | Measured sources | Purpose |
| --- | --- | --- | --- |
| 1 | [`PROTOCOL.md`](PROTOCOL.md) | 1.0.0 and the Rust proposal at `deb276b` | Locate the cost and test the Rust proposal |
| 2 | [`PROTOCOL-2.md`](PROTOCOL-2.md) | 1.0.0 and SDK 1.0.1 at `3a3eaf8` | Measure the release in Rust, in Python, and across the languages |

Each protocol was fixed before its recorded runs, and each run recorded the protocol's SHA-256.
Each protocol states the earlier results that set its thresholds.

## Computer, software, and times

| Component | Value |
| --- | --- |
| Computer | Apple MacBook Pro, model identifier Mac16,5, system firmware 18000.120.36 |
| Chip | Apple M4 Max: 16 CPU cores (12 performance, 4 efficiency) |
| Memory | 128 GB |
| Operating system | macOS 26.5.1 (25F80), Darwin 25.5.0 |
| Power | Mains power |
| Other load | Normal use with other programs. The 1-minute load average before each run was 4.8 to 16.3 in run 1 and 4.1 to 7.5 in run 2. |
| Rust | rustc 1.96.0, cargo 1.96.0, release profile |
| Python endpoints | Python 3.11.15. The drivers ran under Python 3.14.6. |
| Released sources | Tag `sdk-v1.0.0` at commit `4d2bee0` |
| Run 1 | 2026-10-22, 19:10:36 to 19:17:29 UTC, 125 runs |
| Run 2 | 2026-10-22, 19:54:36 to 20:01:03 UTC, 140 runs |

[`results/results.json`](results/results.json) and [`results-2/results.json`](results-2/results.json) record the binary and lockfile digests, every run, and the load before each run.

## Validity

All validity checks passed in both runs:

- The released and the current Rust owner printed the same 48-line transcript of valid, retried, queried, and rejected requests, with every output frame and every verification result.
- In run 2, the released and the 1.0.1 Python SDK printed the same 70-line transcript of request bytes, owner outputs, and `LocalClient` frames over real pipes.
- In run 1, the Python package of the measured checkout was byte-identical to the release.
- Every run was valid. Each call returned `committed`, each acknowledgement returned `acknowledged`, and each response passed verification.

## Run 2: SDK 1.0.1

The table gives the median of the five run medians and, in brackets, the lowest and highest run median, in microseconds per call.
Client and owner use the same SDK version in each run.

| Client and owner | Spikes per step | SDK 1.0.0 | SDK 1.0.1 | 1.0.0 ÷ 1.0.1 |
| --- | --- | --- | --- | --- |
| Rust and Rust | 0 | 359 [357, 368] | 41 [36, 43] | 8.9 (8.4 to 10.0) |
| Rust and Rust | 13 | 373 [373, 376] | 48 [40, 49] | 7.7 (7.7 to 9.4) |
| Rust and Rust | 127 | 403 [401, 410] | 74 [73, 77] | 5.5 (5.2 to 5.6) |
| Rust and Rust | 500 | 517 [516, 528] | 163 [158, 165] | 3.2 (3.1 to 3.3) |
| Python and Python | 0 | 1518 [1513, 1542] | 504 [503, 511] | 3.0 (3.0 to 3.0) |
| Python and Python | 13 | 1837 [1834, 1861] | 610 [604, 616] | 3.0 (3.0 to 3.1) |
| Python and Python | 127 | 4252 [4235, 4261] | 1339 [1328, 1344] | 3.2 (3.2 to 3.2) |
| Python client, Rust owner | 0 | 862 [859, 867] | 259 [259, 264] | 3.3 (3.3 to 3.3) |
| Python client, Rust owner | 127 | 2170 [2164, 2194] | 635 [630, 642] | 3.4 (3.4 to 3.5) |
| Rust client, Python owner | 0 | 976 [972, 984] | 227 [226, 229] | 4.3 (4.3 to 4.3) |
| Rust client, Python owner | 127 | 2412 [2390, 2413] | 707 [698, 712] | 3.4 (3.4 to 3.5) |

The ratio column gives the median and range of the five paired ratios.
A framed echo of 512 bytes between two processes took 7 [5, 8] µs in Rust and 15 [12, 15] µs in Python.

### Hypotheses of protocol 2

| Hypothesis | Criterion | Value | Holds |
| --- | --- | --- | --- |
| H1 | Rust and Rust without spikes: median paired ratio at least 6 | 8.90 | yes |
| H2 | Python and Python without spikes: median paired ratio at least 2.5 | 3.01 | yes |
| H3 | Python and Python with 127 spikes: median paired ratio at least 2.5 | 3.18 | yes |
| H4 | Current lower than released in every round, for all eleven pairs | lowest ratio 2.98 | yes |

### Where the Rust time goes

The `phases` configurations time each part of one call in one process, without a channel.
The values are means over 3000 calls, as the median of the five runs, in microseconds.

| Part | 1.0.0, 0 spikes | 1.0.1, 0 spikes | 1.0.0, 127 spikes | 1.0.1, 127 spikes |
| --- | --- | --- | --- | --- |
| Seal request | 2.6 | 1.1 | 2.7 | 1.1 |
| Encode request | 0.4 | 0.3 | 0.4 | 0.3 |
| Owner handles step | 11.7 | 6.3 | 36.6 | 21.8 |
| Decode and verify response | 154.7 | 4.5 | 172.2 | 18.5 |
| Seal and encode acknowledgement | 3.1 | 1.5 | 3.2 | 1.5 |
| Owner handles acknowledgement | 11.1 | 6.5 | 11.2 | 6.6 |
| Decode and verify acknowledgement | 154.5 | 4.5 | 156.6 | 4.4 |
| **Total** | **337.9** | **24.7** | **383.2** | **54.3** |

In SDK 1.0.0, each verification derived the profile digest again from the 41 KB descriptor.
The two verifications took 91 percent of the time of one call.

## Run 1: the Rust proposal

Run 1 measured the first Rust proposal, which did not yet include the typed digests in `verify` and the owner's kept digest.
All 125 runs were valid, and all three hypotheses of protocol 1 hold.

| Client and owner | Spikes per step | SDK 1.0.0 | Proposal | 1.0.0 ÷ proposal |
| --- | --- | --- | --- | --- |
| Rust and Rust | 0 | 359 | 49 | 7.4 (6.9 to 8.9) |
| Rust and Rust | 127 | 403 | 80 | 5.0 (4.4 to 5.2) |
| Rust and Rust | 500 | 516 | 189 | 2.8 (2.7 to 2.9) |
| Python and Python | 0 | 1525 | not measured | |

[`results/analysis.json`](results/analysis.json) holds all measures of run 1.

## Interpretation

The transport is not the cost. Two framed round trips take about 15 µs in Rust and 30 µs in Python.
In SDK 1.0.0, a repeated derivation of a constant took most of a Rust call, and repeated character-by-character scans took most of a Python call.
SDK 1.0.1 removes that repeated work. It keeps every check and every byte on the wire.

A Rust call with SDK 1.0.1 takes about 41 µs: about 25 µs of processing and two round trips of about 7 µs.
A Python call takes about 0.5 ms. The rest of the Python time is spread over several pure-Python passes: value checks, digest projection, encoding, and the remaining scan.
A call from the Rust client to a Python owner takes about 0.23 ms. This is the arrangement of a Rust host that drives a Python simulator.

## Limits

- One computer in normal use, with load from other programs.
- An echo owner. A simulation owner adds its own work.
- Pipes between two processes on one host.
- One Python interpreter for the Python endpoints.
- Five rounds give no confidence level.

## Reproduce

From a checkout with the tag `sdk-v1.0.0` and a populated Cargo registry:

```text
python3 benchmarks/local-sdk-exchange/run2.py OUT.json --python PYTHON [--smoke]
python3 benchmarks/local-sdk-exchange/analyze2.py OUT.json ANALYSIS.json
```

`run.py` and `analyze.py` repeat run 1.
Both runners build the harness against the released and the current sources and check the transcripts before any timed run.
