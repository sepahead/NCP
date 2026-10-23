"""Shared parts of the Python benchmark clients: payloads, timing, and the result line."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
from collections.abc import Callable


def request(index: int, spikes: int) -> bytes:
    """What a non-NCP client sends: the call index and the number of spikes, 16 bytes."""
    return struct.pack("<QQ", index, spikes)


def spikes_bytes(n: int) -> bytes:
    """N spikes from the benchmark generator, as in the NCP echo owners: senders 1 to 1000 as
    little-endian u32, then times 0.1 to 10.0 ms as little-endian f64; 12 bytes per spike."""
    state, senders, times = 0x2545F4914F6CDD1D, [], []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        senders.append((state >> 33) % 1000 + 1)
        times.append(((state >> 20) % 100) / 10.0 + 0.1)
    return struct.pack(f"<{n}I", *senders) + struct.pack(f"<{n}d", *times)


class Responder:
    """The server side of every non-NCP arm: the request header, then N cached spikes."""

    def __init__(self) -> None:
        self.cache: dict[int, bytes] = {}

    def __call__(self, data: bytes) -> bytes:
        n = struct.unpack_from("<QQ", data)[1]
        if n not in self.cache:
            self.cache[n] = spikes_bytes(n)
        return data[:16] + self.cache[n]


def check(sent: bytes, received: bytes, spikes: int) -> None:
    if len(received) != 16 + 12 * spikes or received[:16] != sent:
        raise SystemExit("wrong response")


def measure(call: Callable[[int], None], calls: int, warmup: int) -> list[float]:
    """Time `call(index)` for warmup + calls calls; return the timed calls in microseconds."""
    times = []
    clock = time.perf_counter_ns
    for index in range(warmup + calls):
        started = clock()
        call(index)
        elapsed = clock() - started
        if index >= warmup:
            times.append(elapsed / 1000)
    return times


def report(times: list[float], **fields) -> None:
    ordered = sorted(times)
    pick = lambda q: ordered[round((len(ordered) - 1) * q)]  # noqa: E731
    line = {
        "calls": len(ordered),
        **fields,
        "median_us": pick(0.5),
        "p05_us": pick(0.05),
        "p95_us": pick(0.95),
        "p99_us": pick(0.99),
        "mean_us": sum(ordered) / len(ordered),
        "min_us": ordered[0],
        "max_us": ordered[-1],
        "quantiles_us": [pick(i / 100) for i in range(101)],
    }
    sys.stdout.write(json.dumps(line) + "\n")
    sys.stdout.flush()


def start_server(argv: list[str]) -> tuple[subprocess.Popen, str]:
    """Start a server that prints 'ready ADDRESS' on its first line."""
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True, env=dict(os.environ, PYTHONUNBUFFERED="1"))
    line = process.stdout.readline().split(maxsplit=1)
    if len(line) != 2 or line[0] != "ready":
        process.kill()
        raise SystemExit(f"server did not start: {line!r}")
    return process, line[1].strip()


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    process.stdout.close()
