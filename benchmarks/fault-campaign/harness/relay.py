"""Frame relay between a client and an owner that can damage one frame.

Usage: relay.py DIRECTION FRAME_INDEX MODE SEED CMD [ARG...]
The relay starts the owner command, forwards length-prefixed frames in both directions,
and damages frame FRAME_INDEX (counted from 0) of DIRECTION (`c2o` or `o2c`):
  flip      flip one random bit of the frame, including its four-byte length prefix;
  truncate  forward a random proper prefix of the frame, then close that direction;
  none      forward everything unchanged.
It writes one JSON line describing the damage to the file descriptor named by RELAY_REPORT_FD.
"""
from __future__ import annotations

import json
import os
import random
import struct
import subprocess
import sys
import threading


def read_exact(fd: int, length: int) -> bytes | None:
    data = b""
    while len(data) < length:
        chunk = os.read(fd, length - len(data))
        if not chunk:
            return None if not data else data
        data += chunk
    return data


def pump(source: int, sink: int, damage: dict | None, report: dict) -> None:
    index = 0
    try:
        while True:
            header = read_exact(source, 4)
            if not header or len(header) < 4:
                break
            length = struct.unpack(">I", header)[0]
            payload = read_exact(source, length) or b""
            frame = header + payload
            if damage is not None and index == damage["index"]:
                rng = random.Random(damage["seed"])
                if damage["mode"] == "flip":
                    bit = rng.randrange(len(frame) * 8)
                    mutated = bytearray(frame)
                    mutated[bit // 8] ^= 1 << (bit % 8)
                    frame = bytes(mutated)
                    report.update({"damaged": True, "bit": bit, "byte": bit // 8, "frame_bytes": len(header + payload),
                                   "in_header": bit < 32})
                elif damage["mode"] == "truncate":
                    cut = rng.randrange(1, len(frame))
                    os.write(sink, frame[:cut])
                    report.update({"damaged": True, "cut": cut, "frame_bytes": len(frame)})
                    break
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
    report = {"direction": direction, "index": index, "mode": mode, "damaged": False}
    damage = {"index": index, "mode": mode, "seed": seed} if mode != "none" else None
    up = threading.Thread(target=pump, args=(0, owner.stdin.fileno(), damage if direction == "c2o" else None, report))
    down = threading.Thread(target=pump, args=(owner.stdout.fileno(), 1, damage if direction == "o2c" else None, report))
    up.start()
    down.start()
    up.join()
    down.join()
    code = owner.wait()
    report["owner_exit"] = code
    with os.fdopen(int(os.environ["RELAY_REPORT_FD"]), "w") as out:
        out.write(json.dumps(report) + "\n")


if __name__ == "__main__":
    main()
