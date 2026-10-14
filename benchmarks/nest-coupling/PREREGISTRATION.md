# Coupling NEST to a peer process: NCP local SDK and MUSIC — preregistration

Fixed on 13 October 2026 before any timed run. Smoke runs that only checked that the code
executes and calibrated the drive rate preceded this file; they are not results. Their
three findings shaped the design and are stated under "Constraints found before the runs".

## Question

On one workstation, how much wall time does it cost to couple a NEST 3.10.0 network to a
separate peer process at a fixed exchange interval Δ, (a) through MUSIC 1.2.1 event ports
in a co-launched MPI job, and (b) through the NCP local lockstep SDK 1.0.0 over private
process pipes, each relative to the same network advanced without that exchange?

## Arms

For each Δ ∈ {1, 2, 5, 10} ms, W(arm, Δ) is the wall-clock time in seconds to advance
T = 2.0 s of biological time with every exchange of that interval. The timed region starts
after `nest.Prepare()` (and, for MUSIC, after NEST has entered the MUSIC runtime, which it
does inside `Prepare`) and ends after the last advance and exchange. Process launch, MPI
and MUSIC setup and network construction are outside it.

| Arm | What happens in the timed region |
|---|---|
| `mono` | One `nest.Run(T)`. NEST slices it internally by its minimum delay Δ. |
| `chunked` | `nest.Run(Δ)` T/Δ times; after each chunk the spike count is read. |
| `chunked-spikes` | As `chunked`, but the new spikes themselves are read (senders and times). |
| `ncp` | A host drives a NEST neural endpoint in a child process with `ncp_local`; each `step` advances Δ and returns the spike count of that step. |
| `ncp-spikes` | As `ncp`, but each `step` returns the new spikes (senders and times). |
| `music` | `mpirun -np 2 music`: NEST runs `nest.Run(T)` with every neuron on one `music_event_out_proxy`; a pymusic peer receives every spike event and sends one acknowledgement event per tick back to a `music_event_in_proxy` that drives an isolated parrot neuron. |

Each host request carries a no-op stimulus; the acknowledgement and the stimulus touch no
neuron of the network, so all arms with the same Δ have identical dynamics.

## Comparisons

- NCP protocol cost: O_ncp(Δ) = W(ncp) − W(chunked), paired within a round.
- NCP transport of spike content: O_ncp-spikes(Δ) = W(ncp-spikes) − W(chunked-spikes).
- MUSIC coupling cost: O_music(Δ) = W(music) − W(mono). MUSIC ticks inside NEST's own
  slicing without returning to Python, so its matched baseline is `mono`.
- Python chunking cost: W(chunked) − W(mono); spike readout cost: W(chunked-spikes) − W(chunked).

Secondary: per-step round-trip time in the NCP arms (median and 95th percentile) and the
peer's per-tick period in the MUSIC arm.

## Workload

1,000 `iaf_psc_alpha` neurons with default parameters; resolution 0.1 ms; one thread; one
NEST rank; `rng_seed` 20261013. Each neuron has its own Poisson generator (6,000 Hz,
10.4 pA) and 100 recurrent excitatory inputs (`fixed_indegree`, 2.0 pA, no autapses);
every connection has delay Δ, so NEST's minimum delay and MUSIC tick equal Δ. The smoke
calibration gives about 12.6 spikes per second per neuron at Δ = 1 ms.

## Design and validity

Five rounds. Each round runs every (arm, Δ) pair once in an order drawn with
`random.Random(20261013 + round)`; one untimed warm-up of every pair precedes the first
round. For a valid run, the spikes received by the peer (or counted by the host) equal the
spikes NEST recorded in the timed interval, and equal the `chunked` count for the same Δ.
An invalid run or a nonzero exit is reported, rerun once, and reported again if it fails.
Each run records the 1-minute load average before its timed region.

## Analysis

All raw values are kept. For each (arm, Δ) the report gives the median and minimum of W
over five rounds; for each comparison it gives the median of the five paired differences
and their range. With five rounds no confidence level is claimed. No hypothesis test is run.

## Constraints found before the runs

1. NEST 3.10 refuses to change recorder parameters between `Prepare` and `Cleanup`, so a
   recorder cannot be cleared between chunks. Reading the spikes of each chunk therefore
   copies the recorder's whole event arrays and keeps the unseen part (the n_events-delta
   readback that NCP's documentation recommends); its cost grows with the run's history.
   The count arms avoid it; the spike arms expose it.
2. NEST 3.10's Python interface does not implement `SetAcceptableLatency` (it raises
   `NotImplementedError`), so NEST's MUSIC input port accepts no latency. MUSIC requires
   latency around a cycle, so the peer's input port declares an acceptable latency of two
   ticks. The MUSIC acknowledgement is therefore pipelined by up to two ticks, whereas the
   NCP lockstep host receives each step's result before it sends the next request.
3. A calibration grid set the drive to 6,000 Hz and 10.4 pA (rates 4.8–45 Hz were seen
   for neighbouring settings).

## Limits fixed in advance

One machine, shared with other processes. A Python implementation of the NCP local SDK,
not the Rust one. MUSIC over Open MPI 5 shared memory. Serial NEST. The two systems serve
different scopes: MUSIC coordinates co-launched simulators on a shared clock with pipelined
latency; the NCP local profile is a lockstep request/response contract with integrity
digests between separately owned applications. The result describes these
implementations under this workload on this host. It does not rank the protocol designs
and gives no real-time or worst-case bound.
