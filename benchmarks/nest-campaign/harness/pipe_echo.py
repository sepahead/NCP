"""The peer of the chunked-pipe arms: echoes length-prefixed messages on its standard input and output."""

from __future__ import annotations

import os
import struct
import sys


def read_exactly(fd: int, size: int) -> bytes:
    parts, remaining = [], size
    while remaining:
        chunk = os.read(fd, min(remaining, 1 << 20))
        if not chunk:
            raise EOFError
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def main() -> None:
    read_fd, write_fd = sys.stdin.fileno(), sys.stdout.fileno()
    while True:
        try:
            header = read_exactly(read_fd, 4)
        except EOFError:
            return
        message = header + read_exactly(read_fd, struct.unpack(">I", header)[0])
        view = memoryview(message)
        while view:
            view = view[os.write(write_fd, view) :]


if __name__ == "__main__":
    main()
