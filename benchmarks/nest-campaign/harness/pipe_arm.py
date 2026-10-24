"""NEST in intervals with a raw round trip to a peer process after each, without a protocol (protocol 3).

Usage: pipe_arm.py {chunked-pipe|chunked-pipe-spikes} NETWORK N THREADS DELTA_MS SEED

As `chunked` and `chunked-spikes` of local_arm.py, but after each interval the arm sends a
length-prefixed message to `pipe_echo.py` over a pipe pair and waits for it to come back: the spike
count (8 bytes), or the new spikes packed as NCP 2 sends them (u32 senders, then i64 steps). The
difference to an NCP arm is the cost of the protocol; the difference to `chunked` is the cost of a
pause for a round trip between processes after each interval.
"""

from __future__ import annotations

import array
import os
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import nest

import networks
from common import T_BIO_MS, emit, load1, now, save_times, spec_from, tick

HERE = Path(__file__).resolve().parent


def read_exactly(fd: int, size: int) -> bytes:
    parts, remaining = [], size
    while remaining:
        chunk = os.read(fd, min(remaining, 1 << 20))
        if not chunk:
            raise EOFError("the peer closed the pipe")
        parts.append(chunk)
        remaining -= len(chunk)
    return b"".join(parts)


def main() -> None:
    mode, spec = sys.argv[1], spec_from(sys.argv[2:])
    peer = subprocess.Popen(
        [sys.executable, "-s", str(HERE / "pipe_echo.py")], stdin=subprocess.PIPE, stdout=subprocess.PIPE
    )
    write_fd, read_fd = peer.stdin.fileno(), peer.stdout.fileno()
    networks.configure(nest, spec["threads"], spec["seed"])
    spike_files = tempfile.mkdtemp(prefix="ncp-nest-spikes-") if mode == "chunked-pipe-spikes" else None
    _, recorder = networks.build(nest, spec["network"], spec["n"], spec["delta_ms"], spike_files)
    reader = networks.Reader(nest, spike_files)
    load = load1()
    nest.Prepare()
    steps = round(T_BIO_MS / spec["delta_ms"])
    spikes = 0
    work: list[int] = []
    trips: list[int] = []
    t0 = now()
    for _ in range(steps):
        start = tick()
        nest.Run(spec["delta_ms"])
        if mode == "chunked-pipe":
            count = reader.count()
            done = tick()
            message = struct.pack("<Q", count)
        else:
            senders, step_values = reader.take()
            count = len(senders)
            done = tick()
            message = array.array("I", senders).tobytes() + array.array("q", step_values).tobytes()
        frame = struct.pack(">I", len(message)) + message
        view = memoryview(frame)
        while view:
            view = view[os.write(write_fd, view) :]
        echoed = read_exactly(read_fd, 4 + len(message))
        if echoed != frame:
            raise RuntimeError("wrong echo")
        trips.append(tick() - done)
        work.append(done - start)
        spikes += count
    t1 = now()
    save_times("NCP_WORK_TIMES", work)
    save_times("NCP_CALL_TIMES", trips)
    recorded = int(recorder.n_events)
    nest.Cleanup()
    peer.stdin.close()
    peer.wait(timeout=60)
    peer.stdout.close()
    if spike_files:
        shutil.rmtree(spike_files, ignore_errors=True)
    emit(
        {
            "arm": mode,
            **spec,
            "wall_s": t1 - t0,
            "spikes": spikes,
            "recorded": recorded,
            "exchanges": steps,
            "load1": load,
        }
    )


if __name__ == "__main__":
    main()
