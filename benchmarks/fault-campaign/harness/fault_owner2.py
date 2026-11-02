"""Python NCP 2 echo owner with injectable faults and an execution log (see ../PROTOCOL-2.md).

Usage: fault_owner2.py    (serves one session on standard input and output)
The contract is that of the reference echo owners in python/tests and rust/examples: `echo`
returns the request body, `spikes` returns N spikes as two arrays, and `fail` raises.
Environment:
  NCP_EXECUTION_LOG  a file to which each execution appends its request body as one JSON line,
                     before it runs
  FAULT_DELAY_S      seconds that each execution sleeps (default 0)
  FAULT_STALL_K      the step k that sleeps FAULT_STALL_S seconds
  FAULT_OVERSIZE_K   the step k whose result is larger than 65,536 bytes
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python"))
import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}'
)


def spikes(n: int) -> tuple[bytes, bytes]:
    """N spikes from the benchmark generator: senders 1 to 1000 (u32), times 0.1 to 10.0 ms (f64)."""
    state, senders, times = 0x2545F4914F6CDD1D, [], []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        senders.append((state >> 33) % 1000 + 1)
        times.append(((state >> 20) % 100) / 10.0 + 0.1)
    return struct.pack(f"<{n}I", *senders), struct.pack(f"<{n}d", *times)


def env_int(name: str) -> int | None:
    value = os.environ.get(name)
    return int(value) if value else None


class FaultEcho:
    def __init__(self) -> None:
        path = os.environ.get("NCP_EXECUTION_LOG")
        self.log = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600) if path else None
        self.delay = float(os.environ.get("FAULT_DELAY_S", "0"))
        self.stall_k, self.stall_s = env_int("FAULT_STALL_K"), float(os.environ.get("FAULT_STALL_S", "0"))
        self.oversize_k = env_int("FAULT_OVERSIZE_K")

    def validate(self, op, body) -> None:
        if not isinstance(body, dict) or type(body.get("k")) is not int:
            raise ncp.BodyInvalid("the body needs an integer k")
        if op == "spikes" and not (type(body.get("n")) is int and 0 <= body["n"] <= 1 << 16):
            raise ncp.BodyInvalid("n must be an integer from 0 to 65536")

    def execute(self, op, body):
        if self.log is not None:  # one write per line, so a killed owner leaves whole lines
            os.write(self.log, (json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n").encode())
        if self.delay:
            time.sleep(self.delay)
        k = body["k"]
        if k == self.stall_k:
            time.sleep(self.stall_s)
        if op == "fail":
            raise RuntimeError("injected failure")
        if k == self.oversize_k:
            return {"k": k, "blob": "x" * 70_000}
        if op == "spikes":
            senders, times = spikes(body["n"])
            return {"k": k, "senders": ncp.Array("u32", [body["n"]], senders), "times": ncp.Array("f64", [body["n"]], times)}
        return body


def main() -> None:
    owner = ncp.Owner(CONTRACT.application, CONTRACT.identity, FaultEcho(), CONTRACT.operations)
    ncp.serve_stdio(owner)


if __name__ == "__main__":
    main()
