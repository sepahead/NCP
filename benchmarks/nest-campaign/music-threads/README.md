# MUSIC event content with more than one NEST thread

This directory reproduces a finding of 22 October 2026: in this build, the MUSIC event stream from NEST carries the exact spike content only with one NEST thread.

## Setup

NEST 3.10.0 with MPI, MUSIC, and OpenMP, MUSIC 1.2.1, and Open MPI 5.0.10, built by `../../nest-coupling/environment/build-nest-music.sh`, on the Apple MacBook Pro (Mac16,5, M4 Max) of the other benchmark records.
[`music_nest.py`](music_nest.py) builds a network of the [campaign](../PROTOCOL.md), connects every neuron to one `music_event_out_proxy` on its own channel, runs 2 s, and writes NEST's own spike recorder events.
[`music_peer.py`](music_peer.py) receives every event on the matching MUSIC input port and writes each (channel, time) pair.
[`compare.py`](compare.py) starts both under `mpiexec` and compares the two multisets.
Run it with the Python of that environment, whose `bin` directory also holds `mpiexec` and `music`:

```text
PREFIX/bin/python compare.py NETWORK N THREADS DELTA_MS SEED [OUT_DIR]
```

It takes the networks and the MUSIC configuration template from [`../harness`](../harness). It writes its launch scripts, its configuration, and the two event files to OUT_DIR, or else to a temporary directory, which it removes after the comparison. The [content part](../PROTOCOL-CONTENT.md) of the campaign runs it with an OUT_DIR and reads the event files.

Set `CONNECT_FORM=list` to connect all neurons in one call with a channel list, the form of NEST's own MUSIC test `test_event_proxies_issue-696`.

## Observation

| Network | Neurons | Threads | Δ (ms) | Peer channels that carry their neuron's exact spike train | Recorded | Delivered |
| --- | --- | --- | --- | --- | --- | --- |
| `brunel` | 1000 | 1 | 1 | 1000 | 116882 | 116882 |
| `brunel` | 1000 | 2 | 1 | 500 | 116990 | 117010 |
| `brunel` | 1000 | 4 | 1 | 250 | 116893 | 116936 |
| `brunel` | 1000 | 8 | 1 | 125 | 116969 | 117136 |
| `alpha` | 1000 | 4 | 1 | not counted | 25925 | 26048 |

With T threads, n/T of n channels were exact. Most other channels carried a train that matched another neuron's train better than their own.
Even without the channel labels, about 28 percent of the delivered spike times differed from the recorded ones with four threads.
The totals also differed. The single-call connection form gave the same result as the per-neuron form.
NEST's own recorder agreed exactly with a run of NEST alone, so the simulation itself was correct.

NEST's MUSIC test suite passed in this build. Its threaded test checks that the run finishes; it does not compare the delivered events with the simulation.
No NEST or MUSIC documentation that we found limits `music_event_out_proxy` to one thread. NEST 3.4 fixed the connection of MUSIC output proxies across several MPI processes, which is a different case.

## Consequence for coupling benchmarks

The NEST campaign records the delivered count next to NEST's recorded count for MUSIC runs with more than one thread and does not require them to agree.
The timing of those runs measures a coupling that does not deliver the simulated content.
The [content part](../PROTOCOL-CONTENT.md) of the campaign checks the content of MUSIC and of NCP for every network and thread count.
