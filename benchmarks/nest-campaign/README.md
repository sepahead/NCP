# NEST campaign

What it costs to couple NEST 3.10.0 to a peer process with NCP 1.0.x and with MUSIC 1.2.1, for three networks, four network sizes, one to eight NEST threads, exchange intervals of 1, 5, and 20 ms, and two payloads; and whether each coupling delivers the exact spikes.
All runs used the NEST 3.10.0 build described in [`../nest-coupling`](../nest-coupling), with Open MPI 5.0.10 and MUSIC 1.2.1, on an Apple MacBook Pro (Mac16,5, M4 Max) with macOS 26.5.1, from 22 to 23 October 2026.

Three protocols were fixed before their runs:

| Protocol | Question | Runs | Status |
| --- | --- | --- | --- |
| [`PROTOCOL.md`](PROTOCOL.md) (run 1) | Cost of the coupling | 573, of which 9 failed closed | Superseded: the readback dominated the cost (see below) |
| [`PROTOCOL-2.md`](PROTOCOL-2.md) | The same, with a readback of constant cost | 558 | The timing results |
| [`PROTOCOL-CONTENT.md`](PROTOCOL-CONTENT.md) | Exact delivery of every spike | 72 trials | The content results |

[`summary.md`](summary.md) holds every table; `summary.py` writes it from the analysis files.

## Measures

`chunked` runs NEST in intervals of Δ in one process and reads the spike count after each; an NCP arm does the same through a host that calls the NEST owner once per interval.
The NCP cost per exchange is O = (W(NCP arm) − W(`chunked`)) / (2000/Δ), where W is the wall time of a run with 2 s of simulated time, paired within a block.
The MUSIC cost per run is W(`music`) − W(`mono`), where `mono` runs the 2 s in one call.
Both are differences of wall times of separate processes, so their noise grows when the network's own run time is long and the number of exchanges is small (for example 10,000 neurons at Δ = 20 ms: 100 exchanges); some medians are then negative.

## Results of protocol 2

All 558 runs were valid, and every arm recorded the same number of spikes in NEST's own recorder within each configuration and block. The recorder totals equal those of run 1 in all 558 runs (H6).

| # | Hypothesis | Holds |
| --- | --- | --- |
| H1 | At Δ = 1 ms, the Python SDK 1.0.1 costs less per exchange than 1.0.0, for each size and thread count. | yes |
| H2 | The median of the 18 median costs per exchange of the Python SDK 1.0.1 in part D1 is at most 0.6 ms. | yes: 0.52 ms |
| H3 | A Rust host costs less per exchange than a Python host in every configuration of D1. | no |
| H4 | With 25,000 neurons, the Python SDK's cost per exchange is at most twice that with 250 neurons. | yes: 0.57 and 0.50 ms |
| H5 | Every run is valid, and the recorded counts agree across arms. | yes |
| H6 | The recorder totals equal those of run 1. | yes |

- **Cost per exchange.** At Δ = 1 ms in D1, an exchange cost 0.48 to 0.56 ms with the Python SDK 1.0.1, 1.39 to 1.59 ms with 1.0.0, and 0.19 to 0.25 ms with a Rust host and the Python owner. H3 fails in two of the 18 configurations, both with 10,000 neurons at Δ = 20 ms (100 exchanges per run), where the noise described above dominates; in the other 16, the Rust host costs less.
- **Spikes in every step (D4).** Returning the spikes, as JSON numbers, cost 0.8 to 2.6 ms per exchange with the Python SDK. Brunel with 10,000 neurons at Δ = 5 ms is not in protocol 2: some steps had up to 8,112 spikes, more than the 65,536-byte frame of NCP 1.0.x can carry.
- **MUSIC.** MUSIC added 2.0 to 28.7 ms to a 2 s run of the 1000-neuron Brunel and alpha networks, much less than NCP 1.0.x, which makes a round trip between processes for each exchange. With the adaptive (`aeif`) network, it added about 1.1 s with one thread and 0.07 s with four. MUSIC runs inside one MPI job. The timing of MUSIC runs with more than one thread measures a coupling that does not deliver the correct spikes (next section). Part D4 has no `mono` arm, so it gives no MUSIC cost.

## Results of the content protocol

| NEST threads | Trials | NCP exact | MUSIC exact | MUSIC channels with the exact spike train (of 1000) |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 18 | 18 | 18 | 1000 |
| 2 | 18 | 18 | 0 | 500 |
| 4 | 18 | 18 | 0 | 250 |
| 8 | 18 | 18 | 0 | 125 |

NCP delivered exactly the spikes of the reference in every trial, with every thread count.
MUSIC delivered exactly the recorded spikes with one NEST thread; with T threads, only n/T of the n channels carried the exact train of their neuron, while NEST's own recorder was correct.
[`music-threads/`](music-threads) reproduces this with the per-neuron and the channel-list forms of the MUSIC connection.

## Why run 1 is superseded

In PyNEST 3.10, each read of a spike recorder's `n_events` or `events` copies all events recorded so far.
Run 1 read the recorder after every interval, so the read grew with the run and dominated both the `chunked` reference and the NCP arms: with 10,000 neurons, 4 threads, and Δ = 1 ms, `nest.Run` took 1.36 ms per interval and the read added 8.6 ms.
Protocol 2 reads the count from the kernel's `local_spike_counter` and the new spikes from the recorder's ASCII files, at a constant cost per interval, and checks both against the recorder total.
Run 1's results stay in [`results/`](results) as a record; its differences are unbiased but too noisy for the NCP cost of large networks. Its 9 failed runs are the NCP runs of Brunel with 10,000 neurons at Δ = 5 ms in D4, which NCP 1.0.x refused because a step's result exceeded its frame.

## Files

| Path | Content |
| --- | --- |
| `PROTOCOL*.md`, `PROTOCOL*.sha256` | The fixed protocols and their digests |
| `run.py`, `content_run.py` | The runners; each resumes after an interruption |
| `analyze.py`, `analyze_content.py`, `summary.py` | The analyses and the tables |
| `harness/` | The networks, the NEST owner, the Python and Rust hosts, the MUSIC peer, and the content checks |
| `results/`, `results-2/`, `results-content/` | Schedules, environments, every run, and the analyses |
| `music-threads/` | The reproduction of the MUSIC result with more than one thread |
