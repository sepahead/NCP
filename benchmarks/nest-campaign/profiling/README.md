# Profile of the NCP 2 owner inside NEST

An exploratory profile of 24 October 2026. It is not part of a protocol, and its numbers are not results of the campaign.

## Question

Why does an NCP 2 exchange with the NEST owner cost more than the same exchange without NEST?
In the smoke runs of [protocol 4](../PROTOCOL-4.md), a step of Brunel with 10,000 neurons at Δ = 5 ms returned 1787 spikes on average, a response of about 21.8 kB.
Its overhead was 144 µs with the Rust host. The same response from an owner without NEST took 88 µs.

## Method

| File | What it does |
| --- | --- |
| [`timed_owner.py`](timed_owner.py) | The NEST owner of [`../harness/ncp2_owner.py`](../harness/ncp2_owner.py), with timestamps at the parts of each step |
| [`fake_owner.py`](fake_owner.py) | The same contract without NEST: each step returns the count 1787, or 1787 fixed spikes, packed as the NEST owner packs them |
| [`decompose.py`](decompose.py) | The parts of each step from the timestamps |
| [`encode_bench.py`](encode_bench.py) | The codec pieces alone, warm, without NEST |

The parts of a step, as the owner sees them:

| Part | From | To |
| --- | --- | --- |
| pre | the request has arrived | the work starts: decoding, checks, dispatch |
| work | the work starts | the readback ends (NEST only) |
| pack | the readback ends | the spike lists are packed into byte arrays |
| encode | the arrays are packed | the response is ready to write: arrays, encoding, digest |
| send | the response is ready | it is written to the pipe |
| away | the response is written | the next request has arrived: the host's decoding and encoding, two transfers, two wake-ups |

The Rust host of the campaign (`ncp2-nest-host`, built by `../run4.py`) drives both owners:

```text
PYTHONPATH=../harness:../../../python MARKS_OUT=marks.json \
  ncp2-nest-host spikes brunel 10000 4 5 20261024 ../harness/ncp2_contract.json PREFIX/bin/python -s timed_owner.py
PYTHONPATH=../../../python FAKE_CONTRACT=../harness/ncp2_contract.json MARKS_OUT=marks.json \
  ncp2-nest-host spikes brunel 10000 4 5 1 ../harness/ncp2_contract.json PREFIX/bin/python -s fake_owner.py
python3 decompose.py marks.json
```

## Result

The computer was the MacBook Pro of the campaign, limited to about 3.1 GHz at the time (see protocol 4), so the absolute values are larger than at full clock. The ratios compare runs under the same limit.
Medians in µs over 399 steps, from two NEST runs about an hour apart:

| Part | Spikes, without NEST | Spikes, NEST, 4 threads | Count, without NEST | Count, NEST, 4 threads, Δ = 1 ms |
| --- | ---: | ---: | ---: | ---: |
| pre | 10.1 | 20.1 and 30.9 | 7.5 | 11.5 |
| pack | 33.6 | 29.2 and 31.1 | 0 | 0 |
| encode | 19.7 | 48.9 and 66.2 | 5.1 | 7.7 |
| send | 1.9 | 4.8 and 5.8 | 1.2 | 2.2 |
| away | 27.5 | 43.5 and 52.1 | 10.8 | 14.7 |
| Sum | 92.8 | 146.5 and 186.1 | 24.6 | 36.1 |

Inside the NEST process, the owner's protocol code (pre, encode, and send) took 74 to 103 µs instead of 32 µs with spikes, and 21 µs instead of 14 µs with a count.
Packing did not slow down: it is a tight loop over lists that the readback has just made.
`OMP_WAIT_POLICY=passive` and `KMP_BLOCKTIME=0` changed each part by at most 2 µs, so NEST's waiting threads are not the cause.
The likely cause is that each NEST step evicts the data and code of the Python interpreter from the caches: the network has about 10^7 synapses. This is an inference; the profile does not count cache misses.

Warm and without NEST, in the NEST environment's Python 3.11 with OpenSSL 3.6.5 (`encode_bench.py`): decoding the step request took 4.4 to 5.0 µs, encoding the spike response 16.1 to 17.2 µs, of which 9.4 to 9.6 µs is its SHA-256 digest, and packing 29 to 31 µs.

## Consequence

The design keeps the optional Rust accelerator for the Python SDK unbuilt (design record, section 8).
Warm, a Rust codec could save the codec time that is not hashing, about 3 µs of decoding a request and 7 µs of encoding a spike response, and about 2 µs of hashing, because Rust's `sha2` (2968 MB/s) is faster than the NEST environment's OpenSSL (about 2300 MB/s for this frame).
These are estimates from the warm times, not measurements of a Rust codec; how much of the cold penalty it would remove is not measured.
