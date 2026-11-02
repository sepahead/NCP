"""Relay between an NCP 2 client and owner that damages or repeats one frame (see ../PROTOCOL-2.md).

Usage: relay2.py DIRECTION FRAME_INDEX MODE SEED CMD [ARG...]
The relay starts the owner command and forwards NCP 2 frames in both directions: a 12-byte
header, J + A bytes, and a 32-byte digest. Frame FRAME_INDEX (counted from 0) of DIRECTION
(`c2o`, client to owner, or `o2c`) is changed by MODE:
  flip       one random bit of the frame is flipped, anywhere in it;
  truncate   a random proper prefix of the frame is forwarded, and that direction closes;
  duplicate  the frame is forwarded twice;
  none       nothing changes.
The relay reads the lengths from the header that it received, so a flipped length reaches the
receiver unchanged. It writes one JSON line about the change to the descriptor RELAY_REPORT_FD.
"""

from __future__ import annotations

import json
import os
import random
import struct
import subprocess
import sys
import threading

HEADER, DIGEST = 12, 32


def read_exact(fd: int, length: int) -> bytes:
    """Read `length` bytes; fewer only at the end of the stream."""
    parts, remaining = [], length
    while remaining:
        chunk = os.read(fd, min(remaining, 1 << 20))
        if not chunk:
            break
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def region(byte: int, json_length: int, attachments: int) -> str:
    if byte < HEADER:
        return "header"
    if byte < HEADER + json_length:
        return "json"
    if byte < HEADER + json_length + attachments:
        return "attachments"
    return "digest"


def pump(source: int, sink: int, change: dict | None, report: dict) -> None:
    index = 0
    try:
        while True:
            header = read_exact(source, HEADER)
            if len(header) < HEADER:
                if header:
                    os.write(sink, header)
                break
            json_length, attachments = struct.unpack(">II", header[4:12])
            rest = read_exact(source, json_length + attachments + DIGEST)
            frame = header + rest
            if len(rest) < json_length + attachments + DIGEST:
                os.write(sink, frame)  # an incomplete last frame passes as it is
                break
            if change is not None and index == change["index"]:
                rng = random.Random(change["seed"])
                report["frame_bytes"] = len(frame)
                if change["mode"] == "flip":
                    bit = rng.randrange(len(frame) * 8)
                    mutated = bytearray(frame)
                    mutated[bit // 8] ^= 1 << (bit % 8)
                    frame = bytes(mutated)
                    report.update(
                        {"changed": True, "bit": bit, "region": region(bit // 8, json_length, attachments)}
                    )
                elif change["mode"] == "truncate":
                    cut = rng.randrange(1, len(frame))
                    os.write(sink, frame[:cut])
                    report.update({"changed": True, "cut": cut})
                    break
                elif change["mode"] == "duplicate":
                    os.write(sink, frame)
                    report["changed"] = True
            os.write(sink, frame)
            index += 1
    except OSError:
        pass
    finally:
        try:
            os.close(sink)
        except OSError:
            pass


def main() -> None:
    direction, index, mode, seed, command = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4]), sys.argv[5:]
    owner = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    report = {"direction": direction, "index": index, "mode": mode, "changed": False}
    change = {"index": index, "mode": mode, "seed": seed} if mode != "none" else None
    up = threading.Thread(target=pump, args=(0, owner.stdin.fileno(), change if direction == "c2o" else None, report))
    down = threading.Thread(target=pump, args=(owner.stdout.fileno(), 1, change if direction == "o2c" else None, report))
    up.start()
    down.start()
    up.join()
    down.join()
    report["owner_exit"] = owner.wait()
    with os.fdopen(int(os.environ["RELAY_REPORT_FD"]), "w") as out:
        out.write(json.dumps(report) + "\n")


if __name__ == "__main__":
    main()
