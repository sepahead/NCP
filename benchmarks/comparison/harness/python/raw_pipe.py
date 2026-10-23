"""The floor: length-prefixed bytes over a pipe pair, with no protocol.

raw_pipe.py server                       (answers requests on stdin and stdout)
raw_pipe.py client CALLS WARMUP SPIKES -- SERVER COMMAND...
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys

from common import Responder, check, measure, report, request


def read_exactly(fd: int, size: int) -> bytes:
    parts, remaining = [], size
    while remaining:
        chunk = os.read(fd, min(remaining, 1 << 20))
        if not chunk:
            raise EOFError
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def server() -> None:
    read_fd, write_fd = sys.stdin.fileno(), sys.stdout.fileno()
    respond = Responder()
    while True:
        try:
            header = read_exactly(read_fd, 4)
        except EOFError:
            return
        response = respond(read_exactly(read_fd, struct.unpack(">I", header)[0]))
        write_all(write_fd, struct.pack(">I", len(response)) + response)


def client() -> None:
    separator = sys.argv.index("--")
    calls, warmup, spikes = (int(value) for value in sys.argv[2:5])
    process = subprocess.Popen(sys.argv[separator + 1:], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    write_fd, read_fd = process.stdin.fileno(), process.stdout.fileno()

    def call(index: int) -> None:
        data = request(index, spikes)
        write_all(write_fd, struct.pack(">I", len(data)) + data)
        length = struct.unpack(">I", read_exactly(read_fd, 4))[0]
        check(data, read_exactly(read_fd, length), spikes)

    times = measure(call, calls, warmup)
    process.stdin.close()
    process.wait(timeout=30)
    process.stdout.close()
    report(times, warmup=warmup, spikes=spikes)


if __name__ == "__main__":
    server() if sys.argv[1] == "server" else client()
