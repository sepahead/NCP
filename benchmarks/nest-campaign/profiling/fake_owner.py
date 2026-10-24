"""An owner with the contract of ../harness/ncp2_owner.py but without NEST (see README.md).

Usage: as ncp2_owner.py, with FAKE_CONTRACT naming ../harness/ncp2_contract.json and MARKS_OUT the
file for the timestamps. Each step returns the count 1787, or 1787 fixed spikes packed as the NEST
owner packs them: the mean number of spikes per step of Brunel with 10,000 neurons at 5 ms.
"""

from __future__ import annotations

import os

FRAMES_OUT = os.dup(1)
os.dup2(2, 1)

import array  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import ncp  # noqa: E402

SPIKES = 1787
CONTRACT = ncp.Contract.load(Path(os.environ["FAKE_CONTRACT"]))
rng = random.Random(1)
SENDERS = sorted(rng.randrange(1, 10001) for _ in range(SPIKES))
STEPS = [rng.randrange(0, 20000) for _ in range(SPIKES)]
MARKS: list[tuple[str, int, int]] = []
tick = time.perf_counter_ns


class Fake:
    payload = "count"

    def validate(self, op: str, body) -> None:
        pass

    def execute(self, op: str, body):
        if op == "prepare":
            self.payload = body["payload"]
            return {"prepared": True}
        if op != "step":
            return {"recorded": 0}
        start = tick()
        if self.payload == "count":
            MARKS.extend([("w", start, start), ("p", start, start)])
            return {"count": SPIKES}
        senders, steps = array.array("I", SENDERS).tobytes(), array.array("q", STEPS).tobytes()
        MARKS.extend([("w", start, start), ("p", start, tick())])
        return {"senders": ncp.Array("u32", [SPIKES], senders), "steps": ncp.Array("i64", [SPIKES], steps)}


def main() -> None:
    channel = ncp.StreamChannel.from_fds(0, FRAMES_OUT)
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
        ncp.serve(ncp.Owner(CONTRACT.application, CONTRACT.identity, Fake(), CONTRACT.operations), channel)
    finally:
        with open(os.environ["MARKS_OUT"], "w") as handle:
            json.dump(MARKS, handle)


if __name__ == "__main__":
    main()
