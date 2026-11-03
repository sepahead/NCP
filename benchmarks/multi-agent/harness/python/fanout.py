"""Part F of the multi-agent benchmark (../../PROTOCOL.md) with a Python host.

Usage: fanout.py N ROUNDS WARMUP MODE WAIT_US OWNER
OWNER is the Rust harness binary; its owners run as `OWNER owner WAIT_US` (NCP 2) or
`OWNER raw-owner WAIT_US` (no protocol). One round sends one request to each of the N owners
and waits for all responses. MODE is all (ncp.call_all), pool (a pool of N threads that lasts
the whole run, one call for each), split (a pool of min(N, 8) threads that lasts the whole run,
each using ncp.call_all on a contiguous share of the sessions), sequential (one call after
another), or raw (pipes without a protocol: every message is written before the first response
is read). Prints one JSON line; times in
microseconds. Exits with an error on any wrong response.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ncp

SPLIT_THREADS = 8  # half of the 16 cores of the benchmark computer, as in the Rust host
ECHO = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{}},"streams":{}}'
)


def summary(times: list[float]) -> dict:
    """The same order statistics as the Rust harness."""
    times = sorted(times)

    def pick(q: float) -> float:
        return times[round((len(times) - 1) * q)]

    return {
        "n": len(times),
        "median_us": pick(0.5),
        "p05_us": pick(0.05),
        "p95_us": pick(0.95),
        "p99_us": pick(0.99),
        "mean_us": sum(times) / len(times),
        "max_us": times[-1],
    }


def body(round_number: int, agent: int) -> dict:
    return {"round": round_number, "agent": agent}


def run_ncp(n: int, total: int, mode: str, wait_us: int, owner: str) -> list[float]:
    clients, processes = [], []
    for _ in range(n):
        channel, process = ncp.spawn([owner, "owner", str(wait_us)])
        client = ncp.Client(channel, application="echo", contract=ECHO.identity)
        client.open()
        clients.append(client)
        processes.append(process)
    workers = {"pool": n, "split": min(n, SPLIT_THREADS)}.get(mode)
    pool = ThreadPoolExecutor(max_workers=workers) if workers else None
    shares = [range(j * n // workers, (j + 1) * n // workers) for j in range(workers)] if workers else []
    times = []
    try:
        for r in range(total):
            bodies = [body(r, agent) for agent in range(n)]
            started = time.perf_counter_ns()
            if mode == "all":
                results = ncp.call_all(clients, "echo", bodies)
            elif mode == "pool":
                assert pool is not None
                results = list(pool.map(lambda i, bodies=bodies: clients[i].call("echo", bodies[i]), range(n)))
            elif mode == "split":
                assert pool is not None

                def share_call(share: range, bodies: list[dict] = bodies) -> list:
                    if len(share) == 1:  # a thread with one session calls it, as in the Rust host
                        return [clients[share[0]].call("echo", bodies[share[0]])]
                    return ncp.call_all([clients[i] for i in share], "echo", [bodies[i] for i in share])

                results = [result for part in pool.map(share_call, shares) for result in part]
            else:
                results = [client.call("echo", b) for client, b in zip(clients, bodies, strict=True)]
            times.append((time.perf_counter_ns() - started) / 1000)
            for result, expected in zip(results, bodies, strict=True):
                if isinstance(result, Exception) or result.body != expected:
                    raise SystemExit(f"wrong response: {result!r}")
    finally:
        if pool is not None:
            pool.shutdown()
    for client in clients:
        client.close()
    for process in processes:
        if process.wait(timeout=30) != 0:
            raise SystemExit("an owner failed")
    return times


def read_exactly(fd: int, count: int) -> bytes:
    parts, missing = [], count
    while missing:
        chunk = os.read(fd, missing)
        if not chunk:
            raise SystemExit("a raw owner closed its output")
        parts.append(chunk)
        missing -= len(chunk)
    return b"".join(parts)


def run_raw(n: int, total: int, wait_us: int, owner: str) -> list[float]:
    processes = [
        subprocess.Popen([owner, "raw-owner", str(wait_us)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        for _ in range(n)
    ]
    inputs = [process.stdin.fileno() for process in processes]  # type: ignore[union-attr]
    outputs = [process.stdout.fileno() for process in processes]  # type: ignore[union-attr]
    times = []
    for r in range(total):
        messages = []
        for agent in range(n):
            payload = json.dumps(body(r, agent), separators=(",", ":")).encode()
            messages.append(struct.pack("<I", len(payload)) + payload)
        started = time.perf_counter_ns()
        for fd, message in zip(inputs, messages, strict=True):
            view = memoryview(message)
            while view:
                view = view[os.write(fd, view) :]
        received = [read_exactly(fd, len(message)) for fd, message in zip(outputs, messages, strict=True)]
        times.append((time.perf_counter_ns() - started) / 1000)
        if received != messages:
            raise SystemExit("wrong response")
    for process in processes:
        process.stdin.close()  # type: ignore[union-attr]
        if process.wait(timeout=30) != 0:
            raise SystemExit("a raw owner failed")
        process.stdout.close()  # type: ignore[union-attr]
    return times


def main() -> None:
    n, rounds, warmup, mode, wait_us, owner = (
        int(sys.argv[1]),
        int(sys.argv[2]),
        int(sys.argv[3]),
        sys.argv[4],
        int(sys.argv[5]),
        sys.argv[6],
    )
    if mode not in ("all", "pool", "split", "sequential", "raw"):
        raise SystemExit(f"unknown mode {mode}")
    total = warmup + rounds
    times = run_raw(n, total, wait_us, owner) if mode == "raw" else run_ncp(n, total, mode, wait_us, owner)
    report = {"part": "F", "host": "python", "mode": mode, "n": n, "wait_us": wait_us}
    report.update({"rounds": rounds, "warmup": warmup, "round": summary(times[warmup:])})
    print(json.dumps(report))


if __name__ == "__main__":
    main()
