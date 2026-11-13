"""Stand-in modules of a closed loop, for the modular-composition test (../test_composition.py).

Usage: modules.py MODULE SEED
MODULE is one of:
  neural    an owner: 32 leaky integrate-and-fire neurons with weights drawn from SEED; `step`
            takes the time step t and four inputs and returns the neurons that fired, as a u32 array
  body      an owner: a point robot in a 10 m by 10 m box; `step` takes t and a command [forward,
            turn] and returns its position, heading, and the distances to the four walls
  monitor   an owner that observes: `check` takes t, the position, and the command, and says whether
            the robot is within 1 m of a wall; it never changes the loop
  recorder  a stream subscriber: it reads stream frames from its standard input, checks their chain,
            appends each accepted body as one JSON line to RECORDER_OUT, and writes a summary to
            RECORDER_OUT.summary when its input ends
The owners serve their standard input and output. FAULT=MODULE:KIND:STEP injects one fault when
the module meets time step STEP: `kill` (the process kills itself after it has changed its state,
so the step is executed but unanswered), `stall` (it sleeps FAULT_STALL_S seconds), or `raise` (the
handler raises). Standard library and the NCP 2 Python SDK only.
"""

from __future__ import annotations

import json
import math
import os
import random
import signal
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import ncp  # noqa: E402

NEURONS = 32
CONTRACTS = {
    name: ncp.Contract.from_bytes(
        json.dumps(
            {"ncp_contract": 1, "application": name, "version": "1", "operations": {op: {}}, "streams": {}},
            separators=(",", ":"),
        ).encode()
    )
    for name, op in (("neural", "step"), ("body", "step"), ("monitor", "check"))
}
RECORD_CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"record","version":"1","operations":{},"streams":{"loop":{}}}'
)


def fault_for(module: str) -> tuple[str, int] | None:
    """The fault that FAULT names for this module, if any: (kind, step)."""
    value = os.environ.get("FAULT", "")
    if not value:
        return None
    name, kind, step = value.split(":")
    return (kind, int(step)) if name == module else None


class Faulty:
    """Inject the module's fault at its step, around the state change of `change`."""

    def __init__(self, module: str) -> None:
        self.fault = fault_for(module)
        self.stall_s = float(os.environ.get("FAULT_STALL_S", "3"))

    def before(self, t: int) -> None:
        if self.fault and self.fault[1] == t:
            if self.fault[0] == "stall":
                time.sleep(self.stall_s)
            elif self.fault[0] == "raise":
                raise RuntimeError(f"injected failure at step {t}")

    def after(self, t: int) -> None:
        if self.fault and self.fault == ("kill", t):
            os.kill(os.getpid(), signal.SIGKILL)


def check_step(body: object, keys: set[str]) -> dict:
    if type(body) is not dict or not keys <= body.keys() or type(body["t"]) is not int:
        raise ncp.Declined(f"the body needs {sorted(keys)}")
    return body


class Neural(Faulty):
    def __init__(self, seed: int) -> None:
        super().__init__("neural")
        rng = random.Random(seed)
        self.w_in = [[rng.uniform(0.0, 0.6) for _ in range(4)] for _ in range(NEURONS)]
        self.w_rec = [
            [rng.uniform(-0.3, 0.3) if rng.random() < 0.2 else 0.0 for _ in range(NEURONS)] for _ in range(NEURONS)
        ]
        self.v = [0.0] * NEURONS
        self.fired: list[int] = []

    def validate(self, request: ncp.Request) -> None:
        check_step(request.body, {"t", "input"})

    def execute(self, request: ncp.Request) -> dict:
        body = request.body
        t = body["t"]
        self.before(t)
        recurrent = [sum(self.w_rec[i][j] for j in self.fired) for i in range(NEURONS)]
        drive = [sum(w * x for w, x in zip(self.w_in[i], body["input"], strict=True)) for i in range(NEURONS)]
        self.v = [0.9 * self.v[i] + drive[i] + recurrent[i] for i in range(NEURONS)]
        self.fired = [i for i in range(NEURONS) if self.v[i] > 1.0]
        for i in self.fired:
            self.v[i] = 0.0
        self.after(t)
        return {"t": t, "fired": ncp.Array("u32", (len(self.fired),), struct.pack(f"<{len(self.fired)}I", *self.fired))}


class Body(Faulty):
    def __init__(self, seed: int) -> None:
        super().__init__("body")
        rng = random.Random(seed + 1)
        self.x, self.y, self.heading = rng.uniform(3, 7), rng.uniform(3, 7), rng.uniform(0, 2 * math.pi)

    def validate(self, request: ncp.Request) -> None:
        check_step(request.body, {"t", "command"})

    def execute(self, request: ncp.Request) -> dict:
        body = request.body
        t = body["t"]
        self.before(t)
        forward, turn = body["command"]
        self.heading = (self.heading + 0.3 * turn) % (2 * math.pi)
        self.x = min(10.0, max(0.0, self.x + 0.2 * forward * math.cos(self.heading)))
        self.y = min(10.0, max(0.0, self.y + 0.2 * forward * math.sin(self.heading)))
        self.after(t)
        return {
            "t": t,
            "position": [self.x, self.y],
            "heading": self.heading,
            "sensors": [self.x / 10, (10 - self.x) / 10, self.y / 10, (10 - self.y) / 10],
        }


class Monitor(Faulty):
    def __init__(self, seed: int) -> None:
        super().__init__("monitor")

    def validate(self, request: ncp.Request) -> None:
        check_step(request.body, {"t", "position", "command"})

    def execute(self, request: ncp.Request) -> dict:
        body = request.body
        t = body["t"]
        self.before(t)
        x, y = body["position"]
        near = min(x, 10 - x, y, 10 - y) < 1.0
        self.after(t)
        return {"t": t, "near_wall": near}


def record(seed: int) -> None:
    """Subscribe to the loop stream on standard input until it ends."""
    out = Path(os.environ["RECORDER_OUT"])
    fault = fault_for("recorder")
    subscriber = ncp.Subscriber({RECORD_CONTRACT.identity})
    channel = ncp.StreamChannel.from_fds(0, 1)
    accepted, problems = 0, []
    with out.open("w") as handle:
        while True:
            try:
                frame = channel.receive(ncp.MAX_BOUND, None)
            except (ncp.ChannelClosed, EOFError):
                break
            delivery = subscriber.receive(frame)
            if delivery.status != "accepted" or delivery.lost:
                problems.append(f"{delivery.status}, {delivery.lost} lost")
                continue
            body = delivery.message["body"]
            if fault and fault == ("kill", body["t"]):
                os.kill(os.getpid(), signal.SIGKILL)
            handle.write(json.dumps(body, sort_keys=True) + "\n")
            handle.flush()
            accepted += 1
    out.with_suffix(".summary").write_text(json.dumps({"accepted": accepted, "problems": problems}) + "\n")


def main() -> None:
    module, seed = sys.argv[1], int(sys.argv[2])
    if module == "recorder":
        return record(seed)
    handler = {"neural": Neural, "body": Body, "monitor": Monitor}[module](seed)
    contract = CONTRACTS[module]
    owner = ncp.Owner(contract, handler)
    ncp.serve_stdio(owner)


if __name__ == "__main__":
    main()
