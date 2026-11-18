"""One timed run of the speed bisection in Python (see README.md).

PYTHONPATH selects the Python SDK of one commit. This client starts the Python echo owner of the
same commit (python/tests/echo_owner.py) as a child over a pipe, opens a session, and makes
WARMUP and then CALLS calls of the operation `spikes` with no spikes, as `bench_client` of the
Rust SDK does. It prints one JSON line with the statistics of the timed calls in microseconds.

The interfaces of the SDK changed in revision 3; the client uses the one that the SDK has.

During the warm-up calls only, it counts the calls of json.loads in the frame decoder of the
client. Above one call for each response, the decoder parsed each response a second time (the
check for a negative zero, README.md). The timed calls run without the counter.

Usage: py_client.py CALLS WARMUP [OWNER_PROFILE]
With OWNER_PROFILE, the owner runs under cProfile and writes its profile there.
"""

from __future__ import annotations

import inspect
import json
import statistics
import sys
import time
from pathlib import Path

import ncp
import ncp.frame as frame_module

CONTRACT = (
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}'
)


class CountingJson:
    """Forwards to the json module and counts the calls of loads."""

    def __init__(self, inner):
        self.inner = inner
        self.loads_calls = 0

    def loads(self, *args, **kwargs):
        self.loads_calls += 1
        return self.inner.loads(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def main() -> None:
    calls, warmup = int(sys.argv[1]), int(sys.argv[2])
    owner = Path(ncp.__file__).resolve().parents[1] / "tests" / "echo_owner.py"
    argv = [sys.executable, "-s", str(owner)]
    if len(sys.argv) > 3:
        argv = [sys.executable, "-s", "-m", "cProfile", "-o", sys.argv[3], str(owner)]
    spawned = ncp.spawn(argv)
    channel = spawned[0] if isinstance(spawned, tuple) else spawned
    contract = ncp.Contract.from_bytes(CONTRACT)
    if "application" in inspect.signature(ncp.Client).parameters:
        client = ncp.Client(channel, application=contract.application, contract=contract.identity)
    else:
        client = ncp.Client(channel, contract)
    client.open()

    counter = CountingJson(frame_module.json)
    frame_module.json = counter
    expected = None
    for index in range(warmup):
        body = client.call("spikes", {"step": index, "n": 0}).body
        expected = body if expected is None else expected
        assert body == expected, body
    frame_module.json = counter.inner

    times = []
    bodies_equal = True
    for index in range(warmup, warmup + calls):
        start = time.perf_counter_ns()
        body = client.call("spikes", {"step": index, "n": 0}).body
        times.append(time.perf_counter_ns() - start)
        bodies_equal = bodies_equal and (expected is None or body == expected)
    client.close()
    assert bodies_equal, "a response body differed from the first"

    micro = sorted(t / 1000 for t in times)
    print(
        json.dumps(
            {
                "calls": calls,
                "warmup": warmup,
                "median_us": statistics.median(micro),
                "mean_us": statistics.fmean(micro),
                "p05_us": micro[len(micro) * 5 // 100],
                "p95_us": micro[len(micro) * 95 // 100],
                "p99_us": micro[len(micro) * 99 // 100],
                "min_us": micro[0],
                "body": expected,
                "loads_per_response": counter.loads_calls / warmup if warmup else None,
                "second_parse": bool(warmup) and counter.loads_calls > 1.5 * warmup,
            }
        )
    )


if __name__ == "__main__":
    main()
