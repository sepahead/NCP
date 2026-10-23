# Comparison benchmark: preregistered protocol

This protocol was fixed before the timed runs. Its SHA-256 digest is in [`PROTOCOL.sha256`](PROTOCOL.sha256), and every result records the digest of the protocol that it followed.

## 1. Question

How long does one call take with NCP 2, with NCP 1.0.1, and with other ways for two programs on one computer to exchange a request and a response?
A call is one request and its response, measured at the client, from before the client builds the request to after it has checked the response.

## 2. Workload

Each call sends a small request with the call index and a spike count N, and gets N spikes back.
A spike is a sender index from 1 to 1000 (an unsigned 32-bit integer) and a time from 0.1 to 10.0 ms (a 64-bit float): 12 bytes.
This is the pattern of a closed loop in which a host sends a stimulus and a neural simulator returns spikes.
The generator is the one of the NCP 1 benchmarks, so that all arms send the same values.
Each owner or server builds the spikes for a value of N once and then reuses them, so that the arms measure the exchange, not the generator.

| N | Response | Reason |
| --- | --- | --- |
| 0 | A small body: `{"count": 13}` for NCP, 16 bytes for the other arms | The cost of the exchange alone |
| 127 | 1,524 bytes of spikes | The payload of the pipelined-acknowledgement benchmark; close to the median of 132 spikes per exchange of the 2,500-neuron Brunel network at 1 ms intervals in the NEST campaign |
| 1788 | 21,456 bytes of spikes | About the median of 1,789 spikes per exchange of the 10,000-neuron Brunel network at 5 ms intervals in the NEST campaign |
| 87381 | 1,048,572 bytes of spikes | About 1 MiB, as for a camera image |

Each arm sends this information in its natural form: typed arrays for NCP 2, JSON lists for NCP 1.0.1, and raw bytes for the other arms.

## 3. Arms

| Arm | Client | Server | Connection |
| --- | --- | --- | --- |
| `ncp2-rust-rust-pipe` | NCP 2 Rust (`rust/examples/bench_client`) | NCP 2 Rust (`rust/examples/echo_owner`) | Pipe pair |
| `ncp2-rust-rust-unix` | NCP 2 Rust | NCP 2 Rust | Unix domain socket |
| `ncp2-rust-rust-tcp` | NCP 2 Rust | NCP 2 Rust | TCP, loopback |
| `ncp2-rust-python-pipe` | NCP 2 Rust | NCP 2 Python (`python/tests/echo_owner.py`) | Pipe pair |
| `ncp2-python-rust-pipe` | NCP 2 Python (`harness/python/ncp2_client.py`) | NCP 2 Rust | Pipe pair |
| `ncp2-python-python-pipe` | NCP 2 Python | NCP 2 Python | Pipe pair |
| `ncp2-python-python-unix` | NCP 2 Python | NCP 2 Python | Unix domain socket |
| `ncp2-python-python-tcp` | NCP 2 Python | NCP 2 Python | TCP, loopback |
| `ncp2-rust-rust-pipe-nocheck` | NCP 2 Rust, digest comparison off | NCP 2 Rust, digest comparison off | Pipe pair |
| `ncp2-python-python-pipe-nocheck` | NCP 2 Python, digest comparison off | NCP 2 Python, digest comparison off | Pipe pair |
| `ncp1-rust-rust-pipe` | NCP 1.0.1 Rust, sequential (the v1 rule) | NCP 1.0.1 Rust | Pipe pair |
| `ncp1-rust-python-pipe` | NCP 1.0.1 Rust | NCP 1.0.1 Python | Pipe pair |
| `ncp1-python-rust-pipe` | NCP 1.0.1 Python, `LocalClient.call` | NCP 1.0.1 Rust | Pipe pair |
| `ncp1-python-python-pipe` | NCP 1.0.1 Python | NCP 1.0.1 Python | Pipe pair |
| `raw-rust-pipe` | Length-prefixed bytes, Rust | The same, Rust | Pipe pair |
| `raw-python-pipe` | Length-prefixed bytes, Python | The same, Python | Pipe pair |
| `grpc-rust-tcp` | gRPC, tonic, one unary method with a protobuf bytes field | The same | TCP, loopback |
| `zenoh-rust-tcp` | Zenoh query and reply, peer mode, no multicast scouting | The same | TCP, loopback |
| `grpc-python-unix` | gRPC, grpcio, raw bytes, no code generation | The same | Unix domain socket |
| `grpc-python-tcp` | The same | The same | TCP, loopback |
| `zmq-python-ipc` | ZeroMQ REQ and REP, pyzmq | The same | `ipc://` |
| `zmq-python-tcp` | The same | The same | TCP, loopback |
| `http-python-tcp` | HTTP/1.1 POST with keep-alive, standard library, TCP_NODELAY at both ends | The same | TCP, loopback |
| `zenoh-python-tcp` | Zenoh query and reply, eclipse-zenoh, peer mode, no multicast scouting | The same | TCP, loopback |

NCP 2 sets 1 MiB send and receive buffers on Unix domain sockets and TCP connections (specification 9.1, rule 8). The other arms keep the defaults of their libraries, which is what their users get without tuning; on macOS, a Unix domain socket has 8 KiB buffers by default.
NCP 1.0.1 arms use N of 0, 127, and 1788 only.
NCP 1.0.1 is measured as released: tag `sdk-v1.0.1`, commit `99e9adc`, with the harness of `benchmarks/pipelined-ack` of that commit, changed only so that the owners build the spike body once (`harness/ncp1/`).
The NCP 2 arms check every response as the other arms do: NCP 2 compares the spike array lengths, NCP 1.0.1 counts the spikes, and the other arms compare the length and the echoed header.

## 4. Computer and software

| Item | Value |
| --- | --- |
| Computer | Apple MacBook Pro (Mac16,5), Apple M4 Max, 16 cores, 128 GB |
| Operating system | macOS 26.5.1 |
| Power | Recorded for each run. At the time of writing: battery at 100 %, High Power Mode (`pmset` powermode 2), no thermal warning |
| Rust | 1.99.1 |
| Python | 3.15.0, with the packages of [`requirements.txt`](requirements.txt): grpcio 1.84.1, pyzmq 27.2.0 (libzmq 4.3.5), eclipse-zenoh 1.10.1 |
| Rust comparison crates | tonic 0.14.6, tonic-prost 0.14.6, prost 0.14.4, tokio 1.54.1, zenoh 1.10.1 (`harness/rust/Cargo.lock`) |
| NCP 2 | The commit that holds this protocol, recorded by each run |

Other programs run on the computer. Each run records the one-minute and five-minute load averages before it starts and the one-minute load average after it ends.

## 5. Design

- Three blocks. Each block runs every configuration (arm and N) once, in an order shuffled with the seed 20261024.
- For N of 0, 127, and 1788: 500 warm-up calls, then 5000 timed calls. For N of 87381: 30 warm-up calls, then 300 timed calls.
- Each run starts its own client and server processes.
- Each run's result is the distribution of the timed call times: the median, the 5th, 95th, and 99th percentiles, the mean, the minimum, the maximum, and, where the arm provides them, the 101 quantiles.
- The statistic of a configuration is the median of its three block medians, with the smallest and largest block median as its range.

## 6. Validity checks

Before any timed run, `run.py` runs these checks and records them in `validity.json`. If one fails, no timed run starts.

1. The NCP 2 Rust tests, and the Python tests with the cross-language test against the Rust owner.
2. The shared conformance vectors in both SDKs.
3. The model conformance test with the Python owner and with the Rust owner: 20,000 random traces each.
4. Differential fuzzing of the two decoders: 200,000 frames.
5. One short run (100 calls) of every configuration, each with a correct response check.

## 7. Exclusions and repeats

A run that exits with an error, or whose response check fails, is recorded and repeated once after all scheduled runs.
If the repeat fails too, the configuration has no result for that block, and the report says so.
No run is excluded for its timing.

## 8. Hypotheses

The pilot runs of 23 October 2026, made while the harness was written, suggested these hypotheses. The pilot results are not part of the results.

| # | Hypothesis | Decision rule |
| --- | --- | --- |
| H1 | NCP 2 is faster than NCP 1.0.1. | For each client and owner language pair over pipes and each N of 0, 127, and 1788, the NCP 2 block median is lower than the NCP 1.0.1 block median in every block (12 comparisons). |
| H2 | NCP 2 meets its design targets. | `ncp2-rust-rust-pipe` at N = 0: statistic at most 15 µs. `ncp2-python-python-pipe` at N = 0 and N = 127: statistic at most 150 µs. |
| H3 | NCP 2 adds little to the floor. | At N = 0, the statistic of `ncp2-rust-rust-pipe` minus that of `raw-rust-pipe` is at most 10 µs. |
| H4 | In Rust, NCP 2 is faster than gRPC and Zenoh. | `ncp2-rust-rust-pipe` is lower than `grpc-rust-tcp` and `zenoh-rust-tcp` at N of 0, 127, and 1788 in every block; `ncp2-rust-rust-tcp` is lower than both at N of 0 and 127 in every block. |
| H5 | In Python, NCP 2 is faster than gRPC and HTTP. | `ncp2-python-python-pipe` is lower than `grpc-python-unix`, `grpc-python-tcp`, and `http-python-tcp` at N of 0, 127, and 1788 in every block. |

Exploratory questions, without a hypothesis: NCP 2 against ZeroMQ and Zenoh in Python; the cost of the digest comparison (the `nocheck` arms); the effect of the connection (pipe, Unix domain socket, TCP); behaviour at 1 MiB, where NCP 2 is expected to be slower than arms without an integrity check by about the time of the SHA-256 digests; and the tails (95th and 99th percentiles).

## 9. Analysis

`analyze.py` reads `runs.jsonl` and writes `analysis.json` with each configuration's statistic and range and each hypothesis's result, and the figures:

1. Call time against N for every arm, one panel for each language.
2. The ratio of NCP 1.0.1 to NCP 2 for each language pair and N.
3. Call time at N = 127 against the floor, with and without the digest comparison.
4. Median, 95th, and 99th percentiles at N = 127.

## 10. What the results do not show

- One computer and one operating system. Pipes on macOS move at most 64 KiB at a time; Linux allows larger pipe buffers, and its results can differ.
- Lockstep calls by one client. Concurrency, many sessions, and clusters are separate benchmarks.
- Call time, not the work of a real owner. A NEST step costs far more than any arm here; the NEST campaign measures the coupling with NEST.
- The other systems in one configuration each, with their default settings. Their tuning options (for example socket buffer sizes, gRPC channel options, or Zenoh's shared memory) can change their results, most at 1 MiB.
- NCP 2 checks integrity and gives exactly-once execution and a hash chain; the other arms do not. The results compare the cost of a call, not equal guarantees.
