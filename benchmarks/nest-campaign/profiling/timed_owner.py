"""The NEST owner of the NCP 2 arms with timestamps at the parts of each step (see README.md).

Usage: as ../harness/ncp2_owner.py, with MARKS_OUT naming the file for the timestamps and the
harness directory on PYTHONPATH.
"""

from __future__ import annotations

import array
import json
import os
import time

import ncp2_owner  # keeps file descriptor 1 for frames and imports NEST, as when it runs as a program
from ncp2_owner import little_endian, nest

import ncp

MARKS: list[tuple[str, int, int]] = []
tick = time.perf_counter_ns


class TimedNest(ncp2_owner.Nest):
    def execute(self, op: str, body):
        if op != "step":
            return super().execute(op, body)
        start = tick()
        nest.Run(float(self.spec["delta_ms"]))
        if self.spec["payload"] == "count":
            count = self.reader.count()
            end = tick()
            MARKS.extend([("w", start, end), ("p", end, end)])
            return {"count": count}
        senders, steps = self.reader.take()
        end = tick()
        packed = (little_endian(array.array("I", senders)), little_endian(array.array("q", steps)))
        MARKS.extend([("w", start, end), ("p", end, tick())])
        count = len(senders)
        return {"senders": ncp.Array("u32", [count], packed[0]), "steps": ncp.Array("i64", [count], packed[1])}


def main() -> None:
    contract = ncp2_owner.CONTRACT
    channel = ncp.StreamChannel.from_fds(0, ncp2_owner.FRAMES_OUT)
    receive, send = channel.receive, channel.send

    def timed_receive(*args, **kwargs):
        start = tick()
        frame = receive(*args, **kwargs)
        MARKS.append(("r", start, tick()))
        return frame

    def timed_send(frame):
        start = tick()
        send(frame)
        MARKS.append(("s", start, tick()))

    channel.receive, channel.send = timed_receive, timed_send
    try:
        ncp.serve(ncp.Owner(contract.application, contract.identity, TimedNest(), contract.operations), channel)
    finally:
        with open(os.environ["MARKS_OUT"], "w") as handle:
            json.dump(MARKS, handle)


if __name__ == "__main__":
    main()
