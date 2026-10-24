# NEST campaign

What it costs to couple NEST 3.10.0 to a peer process with NCP 1.0.x, NCP 2, and MUSIC 1.2.1, for three networks, four network sizes, one to eight NEST threads, exchange intervals of 1, 5, and 20 ms, and two payloads; and whether each coupling delivers the exact spikes.
All runs used the NEST 3.10.0 build described in [`../nest-coupling`](../nest-coupling), with Open MPI 5.0.10 and MUSIC 1.2.1, on an Apple MacBook Pro (Mac16,5, M4 Max) with macOS 26.5.1, from 22 to 24 October 2026.

Five protocols were fixed before their runs:

| Protocol | Question | Runs | Status |
| --- | --- | --- | --- |
| [`PROTOCOL.md`](PROTOCOL.md) (run 1) | Cost of the coupling with NCP 1.0.x and MUSIC | 573, of which 9 failed closed | Superseded: the readback dominated the cost (see below) |
| [`PROTOCOL-2.md`](PROTOCOL-2.md) | The same, with a readback of constant cost | 558 | The timing results for NCP 1.0.x and MUSIC |
| [`PROTOCOL-CONTENT.md`](PROTOCOL-CONTENT.md) | Exact delivery of every spike | 72 trials | The content results |
| [`PROTOCOL-3.md`](PROTOCOL-3.md) | Cost of the coupling with NCP 2, against NCP 1.0.1 and MUSIC | 774 in run 1 | Content valid; timing disturbed (see below) |
| [`PROTOCOL-4.md`](PROTOCOL-4.md) | Protocol 3 under controlled conditions, with the time of every step | not yet run | Waits for the processor to run at full clock again |

[`summary.md`](summary.md) holds the tables of protocols 1, 2, and the content part; `summary.py` writes it from the analysis files. [`results-3/summary.md`](results-3/summary.md) holds those of protocol 3.

## Measures

`chunked` runs NEST in intervals of Δ in one process and reads the spike count after each; an NCP arm does the same through a host that calls the NEST owner once per interval.
The NCP cost per exchange is O = (W(NCP arm) − W(`chunked`)) / (2000/Δ), where W is the wall time of a run with 2 s of simulated time, paired within a block.
The MUSIC cost per run is W(`music`) − W(`mono`), where `mono` runs the 2 s in one call.
Both are differences of wall times of separate processes, so their noise grows when the network's own run time is long and the number of exchanges is small (for example 10,000 neurons at Δ = 20 ms: 100 exchanges); some medians are then negative.
Protocol 4 therefore also times every step inside the processes. Its overhead of a step is the host's call minus the owner's NEST work of the same step, or the raw round trip of a `chunked-pipe` arm, which sends the result to an echo process after each interval without a protocol.

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

## Protocol 3, run 1

All 774 runs of 23 October 2026 (19:00 to 20:48 UTC) were valid. Every NCP host received exactly the spikes that NEST recorded, the recorded counts agreed across arms within each configuration and block (G4), and they equal protocol 2's totals (G5). NCP 2 delivered steps of Brunel with 10,000 neurons at Δ = 5 ms, which NCP 1.0.x refuses.

The timing of the run is disturbed:

- The computer ran on battery for the first 30 minutes.
- During block 1, its lid was closed for 7.5 minutes. The computer then slept for 5 to 8 s in each minute, and its thermal pressure rose to level 4 several times.
- The one-minute load average before a run had a median of 6.6. Its six highest values, 38 to 125, fell between 19:34 and 19:36 UTC, while the computer slept and woke; their cause is not established.
- The reference became slower and stayed slower. `mono` of Brunel with 1000 neurons and 1 thread took 0.675 s in block 0 and in protocol 2, 0.934 s in block 2, and 0.877 s on 24 October. On 24 October the processor ran at about 3.1 GHz on one core and 2.9 GHz on all cores (an M4 Max performance core is rated at up to 4.5 GHz), with High Power selected and the power adapter connected.

The `chunked` reference took as long as in protocol 2 in block 0 (median ratio 1.00), and 26 % and 37 % longer in the medians of blocks 1 and 2, with single runs up to 14 times longer. Single block values of the cost per exchange therefore lie between −172 and +272 ms.

| # | Hypothesis | Holds |
| --- | --- | --- |
| G1 | At Δ = 1 ms in D1, NCP 2 costs less per exchange than NCP 1.0.1, for each host language, size, and thread count, in every block. | no; the timing is disturbed |
| G2 | The median of the six median costs per exchange of NCP 2 with the Rust host at Δ = 1 ms in D1 is at most 0.10 ms. | yes: 0.036 ms |
| G3 | Each D4 configuration of NCP 2 with the Rust host has a median cost per exchange of at most 0.15 ms. | no; the timing is disturbed |
| G4 | Every run is valid, and the recorded counts agree across arms. | yes |
| G5 | The recorder totals equal those of protocol 2. | yes |

The records stay in [`results-3/`](results-3) as they were written.

## Protocol 4

Protocol 4 repeats protocol 3 and adds the time of every step. Before each run, `run4.py` waits for the power adapter, nominal thermal pressure, a core at 4.0 GHz or more, and a load average below 8. It repeats a run during which the computer slept or the conditions failed. A block whose `chunked` reference drifts more than 10 % from protocol 2 leaves the timing hypotheses unadjudicated.
It has not run yet, because the processor has stayed limited to about 3.1 GHz since 23 October.
Its smoke runs, under that limit, gave median overheads per exchange of 29 and 35 µs for NCP 2 with the Rust host, against 13 and 14 µs for the raw round trip and 299 and 313 µs for NCP 1.0.1; [`profiling/`](profiling) explains why the owner's protocol code is slower inside the NEST process than without NEST. These numbers are not results.

Corrections to the background text of [`PROTOCOL-4.md`](PROTOCOL-4.md), found on 24 October 2026 before any run; the rules of the protocol are not affected:

- It says that other programs raised the load average up to 125. The highest values fell while the computer slept and woke with its lid closed; their cause is not established.
- It says that the processor ran at up to 4.5 GHz before. That is the rating of the chip; no clock was measured before 24 October. The measured evidence is the slower `mono` reference.
- It says that the owner's protocol code runs two to four times slower inside the NEST process. Against the owner without NEST, the profile gives 1.6 times with a count and 2.3 to 3.2 times with spikes.

The gate's clock threshold of 4.0 GHz has not yet been observed at full speed. Before the first run, the clock probe must be read with the processor at full speed; if it reads less than 4.0 GHz, a deviation is recorded here before the run starts.

## Why run 1 is superseded

In PyNEST 3.10, each read of a spike recorder's `n_events` or `events` copies all events recorded so far.
Run 1 read the recorder after every interval, so the read grew with the run and dominated both the `chunked` reference and the NCP arms: with 10,000 neurons, 4 threads, and Δ = 1 ms, `nest.Run` took 1.36 ms per interval and the read added 8.6 ms.
Protocol 2 reads the count from the kernel's `local_spike_counter` and the new spikes from the recorder's ASCII files, at a constant cost per interval, and checks both against the recorder total.
Run 1's results stay in [`results/`](results) as a record; its differences are unbiased but too noisy for the NCP cost of large networks. Its 9 failed runs are the NCP runs of Brunel with 10,000 neurons at Δ = 5 ms in D4, which NCP 1.0.x refused because a step's result exceeded its frame.

## Files

| Path | Content |
| --- | --- |
| `PROTOCOL*.md`, `PROTOCOL*.sha256` | The fixed protocols and their digests |
| `run.py`, `content_run.py`, `run3.py`, `run4.py` | The runners; each resumes after an interruption |
| `analyze.py`, `analyze_content.py`, `summary.py`, `analyze3.py`, `analyze4.py` | The analyses and the tables |
| `harness/` | The networks, the NEST owners, the Python and Rust hosts of NCP 1.0.1 and NCP 2, the raw round trip, the MUSIC peer, the content checks, and the clock probe |
| `results/`, `results-2/`, `results-content/`, `results-3/` | Schedules, environments, every run, and the analyses |
| `music-threads/` | The reproduction of the MUSIC result with more than one thread |
| `profiling/` | Where the time of an NCP 2 exchange goes inside the NEST process |
