"""Long NCP 2 sessions with clients of constant memory (see ../PROTOCOL-2.md).

Usage: soak2.py KIND CALLS
KIND: python-python  the Python client below with harness/fault_owner2.py;
      python-rust    the Python client below with the Rust echo owner (RUST_OWNER);
      rust-rust      bench_client --keep-every 1000 (RUST_CLIENT) with the Rust echo owner.
The sampler reads the resident memory and the open descriptors of the client and of the owner
every 0.5 s. Prints one JSON line with the client's result and the samples.

soak2.py client OWNER CALLS runs the Python client: one session of CALLS `echo` calls, each
checked, keeping the time of every 1000th call.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEEP_EVERY = 1000


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


def client(owner: str, calls: int) -> None:
    sys.path.insert(0, str(HERE.parents[2] / "python"))
    import ncp

    contract = ncp.Contract.from_bytes(
        b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}'
    )
    command = [os.environ["RUST_OWNER"]] if owner == "rust" else [sys.executable, "-s", str(HERE / "fault_owner2.py")]
    channel, process = ncp.spawn(command)
    session = ncp.Client(channel, application="echo", contract=contract.identity, timeout=10)
    session.open()
    kept, valid, clock = [], True, time.perf_counter_ns
    for k in range(1, calls + 1):
        started = clock()
        body = {"k": k}
        valid = valid and session.call("echo", body).body == body
        if k % KEEP_EVERY == 0:
            kept.append((clock() - started) / 1000)
    session.close()
    process.wait(timeout=10)
    print(json.dumps({"calls": calls, "kept": len(kept), "median_us": statistics.median(kept), "valid": valid}))


def main() -> None:
    if sys.argv[1] == "client":
        return client(sys.argv[2], int(sys.argv[3]))
    kind, calls = sys.argv[1], int(sys.argv[2])
    if kind == "rust-rust":
        command = [os.environ["RUST_CLIENT"], str(calls), "0", "0", "--keep-every", str(KEEP_EVERY), "--", os.environ["RUST_OWNER"]]
    else:
        command = [sys.executable, "-s", __file__, "client", kind.split("-")[1], str(calls)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    samples, owner = [], None
    started = time.monotonic()
    while process.poll() is None:
        owner = owner or child_of(process.pid)
        samples.append(
            {
                "t": round(time.monotonic() - started, 2),
                "client_rss_kb": rss_kb(process.pid),
                "owner_rss_kb": rss_kb(owner) if owner else None,
                "client_fds": descriptors(process.pid),
                "owner_fds": descriptors(owner) if owner else None,
            }
        )
        time.sleep(0.5)
    lines = process.stdout.read().strip().splitlines()
    result = json.loads(lines[-1]) if process.returncode == 0 and lines else None
    if result is not None and kind == "rust-rust":
        result["valid"] = True  # bench_client checks every response and fails on a wrong one
    print(
        json.dumps(
            {
                "kind": kind,
                "calls": calls,
                "seconds": round(time.monotonic() - started, 2),
                "returncode": process.returncode,
                "result": result,
                "samples": samples,
            }
        )
    )


if __name__ == "__main__":
    main()
