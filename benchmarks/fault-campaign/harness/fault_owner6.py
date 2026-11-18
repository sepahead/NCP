"""The Python owner of fault-campaign protocol 6 (see ../PROTOCOL-6.md), for revision 7 of the SDKs.

Usage: fault_owner6.py unix PATH    a server: prints "ready unix:PATH"
       fault_owner6.py tcp          a server on a loopback port: prints "ready tcp:HOST:PORT"
A server gives each connection its own owner and handler, and runs until it is killed.

The handler is that of fault_owner2.py, which protocols 2 to 5 used with revision 2 of the SDKs,
ported to the owner interface of revision 7: `validate` and `execute` take an `ncp.Request`, and
a handler declines a body with `ncp.Declined`. `echo` returns the request body, `spikes` returns N
spikes as two arrays, and `fail` raises.
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
import threading
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

    def validate(self, request: ncp.Request) -> None:
        body = request.body
        if not isinstance(body, dict) or type(body.get("k")) is not int:
            raise ncp.Declined("the body needs an integer k")
        if request.op == "spikes" and not (type(body.get("n")) is int and 0 <= body["n"] <= 1 << 16):
            raise ncp.Declined("n must be an integer from 0 to 65536")

    def execute(self, request: ncp.Request):
        op, body = request.op, request.body
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


def make_owner() -> ncp.Owner:
    return ncp.Owner(CONTRACT, FaultEcho())


def main() -> None:
    if sys.argv[1] == "unix":
        ncp.UnixServer(make_owner, sys.argv[2]).start()
        print(f"ready unix:{sys.argv[2]}", flush=True)
    else:
        server = ncp.TcpServer(make_owner).start()
        host, port = server.address[:2]
        print(f"ready tcp:{host}:{port}", flush=True)
    threading.Event().wait()  # serve until killed


if __name__ == "__main__":
    main()
