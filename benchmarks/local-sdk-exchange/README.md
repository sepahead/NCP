# Local SDK exchange benchmark

This directory holds a benchmark of 22 October 2026.
It measures one lockstep call of the local SDKs: one request with its verified response, and one acknowledgement with its verified response.
It compares the released Rust SDK 1.0.0 with a proposed change, and it separates the transport time from the SDK time.

The result describes these implementations under an echo workload on one computer.
It gives no real-time bound and no worst-case bound. It does not rank NCP against another protocol.

> [!IMPORTANT]
> The measured Rust change is a proposal. `scripts/check_local_sdk.py` pins the local SDK sources to the historical reference revision `de751d4`.
> The change can reach `main` only after the owner moves that revision.

## Computer, software, and times

| Component | Value |
| --- | --- |
| Computer | Apple MacBook Pro, model identifier Mac16,5, system firmware 18000.120.36 |
| Chip | Apple M4 Max: 16 CPU cores (12 performance, 4 efficiency) |
| Memory | 128 GB |
| Operating system | macOS 26.5.1 (25F80), Darwin 25.5.0 |
| Power | Mains power |
| Other load | Normal use with other programs. The 1-minute load average was 4.8 to 16.3 before the runs. |
| Rust | rustc 1.96.0, cargo 1.96.0, release profile |
| Python endpoints | Python 3.11.15. The driver `run.py` ran under Python 3.14.6. |
| Released sources | Tag `sdk-v1.0.0` at commit `4d2bee0` |
| Current sources | Commit `deb276b`, which differs from the release only in the Rust digest code |
| Timed runs | 2026-10-22, 19:10:36 to 19:17:29 UTC |

[`results/results.json`](results/results.json) records the binary and lockfile digests, all 125 runs, and the load before each run.

## Protocol and validity

[`PROTOCOL.md`](PROTOCOL.md) fixed the question, configurations, workload, design, measures, and hypotheses before the recorded runs.
Its SHA-256 is in [`PROTOCOL.sha256`](PROTOCOL.sha256), and `run.py` recorded the same digest.
The protocol states the exploratory runs that set its thresholds.

All validity checks passed:

- The released and the current Rust owner wrote the same 48-line transcript for a fixed script of valid, retried, queried, and rejected requests.
  It includes every output frame and every verification result.
- The Python package of this checkout is byte-identical to the release.
- All 125 runs were valid. Each call returned `committed`, each acknowledgement returned `acknowledged`, and each response passed verification.

## Results

The table gives the median of the five run medians and, in brackets, the lowest and highest run median, in microseconds per call.

| Configuration | Spikes per step | Released 1.0.0 | Current | Released ÷ current |
| --- | --- | --- | --- | --- |
| Rust client, Rust owner | 0 | 359 [358, 366] | 49 [41, 52] | 7.4 (6.9 to 8.9) |
| Rust client, Rust owner | 13 | 372 [364, 381] | 52 [52, 58] | 7.0 (6.4 to 7.3) |
| Rust client, Rust owner | 127 | 403 [395, 411] | 80 [77, 93] | 5.0 (4.4 to 5.2) |
| Rust client, Rust owner | 500 | 516 [513, 530] | 189 [184, 193] | 2.8 (2.7 to 2.9) |
| Rust client, Python owner | 0 | 979 [969, 981] | 663 [649, 665] | 1.5 (1.5 to 1.5) |
| Rust client, Python owner | 127 | 2416 [2393, 2787] | 2088 [2067, 2144] | 1.2 (1.1 to 1.4) |
| Python client, Rust owner | 0 | 860 [859, 861] | 844 [841, 854] | 1.0 (1.0 to 1.0) |
| Python client, Rust owner | 127 | 2179 [2148, 2196] | 2180 [2168, 2225] | 1.0 (1.0 to 1.0) |

The ratio column gives the median and range of the five paired ratios.
Python clients and owners use the released Python SDK in both columns.

| Configuration | Spikes per step | Median per call |
| --- | --- | --- |
| Python client, Python owner | 0 | 1525 [1517, 1538] |
| Python client, Python owner | 13 | 1841 [1838, 1854] |
| Python client, Python owner | 127 | 4260 [4212, 4284] |
| Framed echo of 512 bytes, Rust | none | 7.3 [5.1, 7.5] |
| Framed echo of 512 bytes, Python | none | 14.3 [7.6, 14.9] |

### Hypotheses

| Hypothesis | Criterion | Value | Holds |
| --- | --- | --- | --- |
| H1 | Without spikes, median paired ratio at least 5 | 7.41 | yes |
| H2 | With 127 spikes, median paired ratio at least 3 | 5.00 | yes |
| H3 | With 500 spikes, current lower in every round | ratios 2.67 to 2.85 | yes |

### Where the Rust time goes

The `phases` configurations time each part of one call in one process, without a channel.
The values are means over 3000 calls, as the median of the five runs, in microseconds.

| Part | Released, 0 spikes | Current, 0 spikes | Released, 127 spikes | Current, 127 spikes |
| --- | --- | --- | --- | --- |
| Seal request | 2.6 | 1.1 | 2.7 | 1.1 |
| Encode request | 0.4 | 0.3 | 0.4 | 0.3 |
| Owner handles step | 11.8 | 6.9 | 36.5 | 26.6 |
| Decode and verify response | 154.2 | 6.0 | 171.9 | 21.3 |
| Seal and encode acknowledgement | 3.2 | 1.5 | 3.2 | 1.5 |
| Owner handles acknowledgement | 11.1 | 6.5 | 11.3 | 6.6 |
| Decode and verify acknowledgement | 154.2 | 6.1 | 155.9 | 6.1 |
| **Total** | **337.4** | **28.3** | **381.9** | **63.6** |

In the released SDK, each verification derived the profile digest again from the 41 KB descriptor.
Decoding and verifying one response took 154 µs, against 6 µs with the proposal.
The two verifications of one call took 91 percent of its time.

## Interpretation

The transport is not the cost. A framed echo between two processes takes 7 µs in Rust and 14 µs in Python.
A lockstep call needs two such round trips.

In the released Rust SDK, a repeated derivation of a constant took most of the time.
The proposal removes that repetition and some copies. It keeps every check and the exact wire bytes.
A Rust lockstep call without spikes then takes 49 µs, of which about 28 µs is processing and the rest is the two round trips.

In Python, the processing on both sides takes almost all of the 1.5 ms.
A call from a Python client to a Rust owner takes about 0.85 ms.
A call from the proposed Rust client to a Python owner takes about 0.66 ms.
Most of this time is the pure-Python structural scan of each JSON frame, which runs several times per call, and the pure-Python digest projection.
This benchmark does not measure a Python change.

## Limits

- One computer in normal use, with load from other programs.
- An echo owner. A simulation owner adds its own work.
- Pipes between two processes on one host.
- One Python interpreter for the Python endpoints.
- Five rounds give no confidence level.

## Reproduce

From a checkout with the tag `sdk-v1.0.0` and a populated Cargo registry:

```text
python3 benchmarks/local-sdk-exchange/run.py OUT.json --python PYTHON [--smoke]
python3 benchmarks/local-sdk-exchange/analyze.py OUT.json ANALYSIS.json
```

`run.py` builds the harness against the released and the current sources and checks the transcripts before any timed run.
