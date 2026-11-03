"""The Python owner of fault-campaign protocol 4 (see ../PROTOCOL-4.md).

Usage: fault_owner4.py              one session on standard input and output
       fault_owner4.py unix PATH    a server: prints "ready unix:PATH"
       fault_owner4.py tcp          a server on a loopback port: prints "ready tcp:HOST:PORT"
The handler is FaultEcho of fault_owner2.py, with its environment variables; a server gives
each connection its own owner and handler, and runs until it is killed.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fault_owner2 import CONTRACT, FaultEcho, ncp  # noqa: E402


def make_owner() -> ncp.Owner:
    return ncp.Owner(CONTRACT.application, CONTRACT.identity, FaultEcho(), CONTRACT.operations)


def main() -> None:
    if len(sys.argv) == 1:
        ncp.serve_stdio(make_owner())
        return
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
