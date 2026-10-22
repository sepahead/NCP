"""Framed echo between two Python processes, without NCP (see ../../PROTOCOL.md).

Usage: raw.py SIZE CALLS WARMUP. Uses the SDK's frame functions with a deadline,
as LocalClient does.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from ncp_local.wire import read_local_frame, write_local_frame

from client import summary


def child() -> None:
    reader, writer = sys.stdin.buffer, open(1, "wb", buffering=0)
    while (frame := read_local_frame(reader)) is not None:
        write_local_frame(writer, frame)


def main() -> None:
    size, calls, warmup = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3])
    peer = subprocess.Popen([sys.executable, __file__, "child"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            bufsize=0)
    message, samples = b"x" * size, []
    for index in range(warmup + calls):
        started = time.perf_counter()
        deadline = time.monotonic() + 60
        write_local_frame(peer.stdin, message, deadline=deadline)
        echoed = read_local_frame(peer.stdout, deadline=deadline)
        elapsed = time.perf_counter() - started
        assert echoed == message
        if index >= warmup:
            samples.append(elapsed)
    peer.stdin.close()
    peer.wait(timeout=60)
    print(json.dumps({"mode": "raw", "language": "python", "size": size, "timing": summary(samples)}))


if __name__ == "__main__":
    child() if sys.argv[1:] == ["child"] else main()
