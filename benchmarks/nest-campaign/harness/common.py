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
