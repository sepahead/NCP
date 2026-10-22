"""Lockstep client for the local Python SDK (see ../../PROTOCOL.md).

Usage: client.py N CALLS WARMUP CMD [ARG...]
The owner command receives the binding as its last argument. `LocalClient.call`
sends one request, verifies the response, acknowledges it, and verifies the
acknowledgement. Prints one JSON line.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from ncp_local import LocalBinding, LocalClient


def summary(samples: list[float]) -> dict:
    ordered = sorted(samples)
    at = lambda q: ordered[round((len(ordered) - 1) * q)] * 1e6  # noqa: E731
    return {"calls": len(ordered), "median_us": at(0.5), "p05_us": at(0.05), "p95_us": at(0.95),
            "p99_us": at(0.99), "min_us": at(0.0), "max_us": at(1.0)}


def main() -> None:
    n, calls, warmup, command = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]
    binding = LocalBinding.fresh("neural")
    child = subprocess.Popen(command + [json.dumps(binding.as_dict())], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, bufsize=0)
    client = LocalClient(binding, child.stdout, child.stdin, timeout_s=60)
    assert client.call("prepare", {"n": n})["outcome"] == "committed"
    samples, received = [], 0
    for index in range(warmup + calls):
        started = time.perf_counter()
        response = client.call("step", {"stimulus": 0})
        elapsed = time.perf_counter() - started
        if response["outcome"] != "committed":
            raise RuntimeError(response["code"])
        body = response["body"]
        received = body["count"] if n == 0 else len(body["senders"])
        if index >= warmup:
            samples.append(elapsed)
    client.call("finish", {})
    child.stdin.close()
    status = child.wait(timeout=60)
    print(json.dumps({"mode": "client", "language": "python", "n": n, "valid": received == (13 if n == 0 else n),
                      "owner_exit": status, "timing": summary(samples)}))


if __name__ == "__main__":
    main()
