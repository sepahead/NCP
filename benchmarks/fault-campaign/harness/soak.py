"""Long lockstep session with memory and descriptor sampling (see ../PROTOCOL.md).

Usage: soak.py {rust|python} CALLS
rust:   the Rust client and Rust owner of benchmarks/pipelined-ack (RUST_HARNESS).
python: LocalClient with the Python echo owner (PIPELINED_HARNESS_PY).
Samples the resident memory and the open descriptors of the client and the owner every
0.5 s. Prints one JSON line with the call-time percentiles and the samples.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time


def rss_kb(pid: int) -> int | None:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return int(out) if out else None


def descriptors(pid: int) -> int | None:
    out = subprocess.run(["lsof", "-n", "-P", "-p", str(pid)], capture_output=True, text=True).stdout
    lines = out.strip().splitlines()
    return len(lines) - 1 if lines else None


def child_of(pid: int) -> int | None:
    out = subprocess.run(["pgrep", "-P", str(pid)], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def main() -> None:
    kind, calls = sys.argv[1], int(sys.argv[2])
    if kind == "rust":
        harness = os.environ["RUST_HARNESS"]
        command = [harness, "sequential", "0", str(calls), "500", harness, "owner"]
    else:
        directory = os.environ["PIPELINED_HARNESS_PY"]
        command = [sys.executable, "-s", f"{directory}/client.py", "sdk", "0", str(calls), "500",
                   sys.executable, "-s", f"{directory}/owner.py"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    samples, owner = [], None
    started = time.monotonic()
    while process.poll() is None:
        owner = owner or child_of(process.pid)
        samples.append({"t": round(time.monotonic() - started, 2), "client_rss_kb": rss_kb(process.pid),
                        "owner_rss_kb": rss_kb(owner) if owner else None,
                        "client_fds": descriptors(process.pid), "owner_fds": descriptors(owner) if owner else None})
        time.sleep(0.5)
    result = json.loads(process.stdout.read().strip().splitlines()[-1])
    print(json.dumps({"kind": kind, "calls": calls, "seconds": round(time.monotonic() - started, 2),
                      "returncode": process.returncode, "result": result, "samples": samples}))


if __name__ == "__main__":
    main()
