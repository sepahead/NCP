"""A relay over sockets that damages or repeats one frame (see ../PROTOCOL-4.md).

Usage: relay_socket.py DIRECTION FRAME_INDEX MODE SEED LISTEN CONNECT
The changes of relay2.py, between a client and an owner that talk over a Unix domain socket or
TCP. LISTEN is `unix:PATH` or `tcp` (a loopback port of the system's choice); CONNECT is the
owner's `unix:PATH` or `tcp:HOST:PORT`. The relay prints "ready ADDRESS", accepts one client,
connects to the owner, and forwards frames in both directions until both have ended. Where
relay2.py closes a pipe, this relay shuts down the writing side of the socket. It writes one
JSON line about the change to the descriptor RELAY_REPORT_FD.
"""

from __future__ import annotations

import json
import os
import random
import socket
import struct
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from relay2 import DIGEST, HEADER, read_exact, region  # noqa: E402


def write_all(sock: socket.socket, data: bytes) -> None:
    sock.sendall(data)


def pump(source: socket.socket, sink: socket.socket, change: dict | None, report: dict) -> None:
    index = 0
    fd = source.fileno()
    try:
        while True:
            header = read_exact(fd, HEADER)
            if len(header) < HEADER:
                if header:
                    write_all(sink, header)
                break
            json_length, attachments = struct.unpack(">II", header[4:12])
            rest = read_exact(fd, json_length + attachments + DIGEST)
            frame = header + rest
            if len(rest) < json_length + attachments + DIGEST:
                write_all(sink, frame)  # an incomplete last frame passes as it is
                break
            if change is not None and index == change["index"]:
                rng = random.Random(change["seed"])
                report["frame_bytes"] = len(frame)
                if change["mode"] == "flip":
                    bit = rng.randrange(len(frame) * 8)
                    mutated = bytearray(frame)
                    mutated[bit // 8] ^= 1 << (bit % 8)
                    frame = bytes(mutated)
                    report.update({"changed": True, "bit": bit, "region": region(bit // 8, json_length, attachments)})
                elif change["mode"] == "truncate":
                    cut = rng.randrange(1, len(frame))
                    write_all(sink, frame[:cut])
                    report.update({"changed": True, "cut": cut})
                    break
                elif change["mode"] == "duplicate":
                    write_all(sink, frame)
                    report["changed"] = True
            write_all(sink, frame)
            index += 1
    except OSError:
        pass
    finally:
        try:
            sink.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def listen(spec: str) -> tuple[socket.socket, str]:
    if spec.startswith("unix:"):
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(spec[5:])
        listener.listen(1)
        return listener, spec
    listener = socket.create_server(("127.0.0.1", 0))
    host, port = listener.getsockname()[:2]
    return listener, f"tcp:{host}:{port}"


def connect(spec: str) -> socket.socket:
    if spec.startswith("unix:"):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(spec[5:])
        return sock
    host, port = spec[4:].rsplit(":", 1)
    sock = socket.create_connection((host, int(port)))
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    return sock


def main() -> None:
    direction, index, mode, seed = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
    listener, address = listen(sys.argv[5])
    print(f"ready {address}", flush=True)
    client, _ = listener.accept()
    listener.close()
    if address.startswith("tcp:"):
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    owner = connect(sys.argv[6])
    report = {"direction": direction, "index": index, "mode": mode, "changed": False}
    change = {"index": index, "mode": mode, "seed": seed} if mode != "none" else None
    up = threading.Thread(target=pump, args=(client, owner, change if direction == "c2o" else None, report))
    down = threading.Thread(target=pump, args=(owner, client, change if direction == "o2c" else None, report))
    up.start()
    down.start()
    up.join()
    down.join()
    client.close()
    owner.close()
    with os.fdopen(int(os.environ["RELAY_REPORT_FD"]), "w") as out:
        out.write(json.dumps(report) + "\n")


if __name__ == "__main__":
    main()
