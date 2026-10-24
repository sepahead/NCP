"""Shared arguments and timing for the NEST campaign arms (see ../PROTOCOL.md)."""
from __future__ import annotations

import json
import os
import time

T_BIO_MS = 2000.0


def spec_from(argv: list[str]) -> dict:
    """NETWORK N THREADS DELTA_MS SEED -> run specification."""
    network, n, threads, delta, seed = argv[:5]
    return {"network": network, "n": int(n), "threads": int(threads), "delta_ms": float(delta), "seed": int(seed)}


def emit(record: dict) -> None:
    print(json.dumps(record), flush=True)


def load1() -> float:
    return os.getloadavg()[0]


def now() -> float:
    return time.perf_counter()


def tick() -> int:
    return time.perf_counter_ns()


def save_times(variable: str, times: list[int]) -> None:
    """Write durations in nanoseconds, one per step, to the file that an environment variable names (protocol 4).

    NCP_WORK_TIMES receives the NEST work of each step: `nest.Run` and the readback. NCP_CALL_TIMES
    receives each call as the host sees it, or, in the chunked-pipe arms, each raw round trip."""
    path = os.environ.get(variable)
    if path and times:
        with open(path, "w") as handle:
            json.dump(times, handle)
