#!/usr/bin/env python3
"""Check that the real Python owner answers like the model owner (spec/NCP-2.md, section 7.3).

Random traces of requests drive the model owner and `ncp.Owner` side by side: correct requests,
invalid bodies, repeats of earlier requests, stale acknowledgements, skipped and stale sequence
numbers, application failures, and `close`. For every request, both must give the same outcome
and code, and a repeat must return byte-identical frames.

With --owner COMMAND..., the owner is an external program that prints "port N" or "unix PATH"
and serves one session per connection, such as the Rust example `model_owner`.

Usage: conformance.py [--traces 20000] [--seed 20261023] [--owner COMMAND...]
"""
from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "python"))

import ncp  # noqa: E402
from ncp import frame as F  # noqa: E402
import ncp2_model as M  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}')


class Handler:
    def validate(self, op, body):
        if body.get("version") == "bad":
            raise ncp.BodyInvalid("bad version")

    def execute(self, op, body):
        if body.get("fail"):
            raise RuntimeError("injected failure")
        return {"seq": body["seq"]}


def python_owner():
    owner = ncp.Owner("model", CONTRACT.identity, Handler(), CONTRACT.operations, max_bound=F.HANDSHAKE_BOUND)
    return owner.handle, lambda: None


class ExternalOwner:
    """An owner program that serves one session per TCP connection."""

    def __init__(self, argv: list[str]) -> None:
        self.process = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
        line = self.process.stdout.readline().split(maxsplit=1)
        if len(line) != 2 or line[0] not in ("port", "unix"):
            self.process.kill()
            raise SystemExit(f"the owner printed {line!r}, not 'port N' or 'unix PATH'")
        self.kind, self.address = line[0], line[1].strip()

    def __call__(self):
        if self.kind == "unix":
            channel = ncp.connect_unix(self.address)
        else:
            channel = ncp.connect_tcp("127.0.0.1", int(self.address))

        def handle(frame: bytes) -> bytes:
            channel.send(frame)
            return channel.receive(F.MAX_BOUND, timeout=10)

        return handle, channel.close

    def stop(self) -> None:
        self.process.terminate()
        self.process.wait(timeout=10)
        self.process.stdout.close()


def run_trace(rng: random.Random, length: int, new_owner=python_owner) -> tuple[int, int]:
    """Return (requests compared, repeats compared). Raise AssertionError on a difference."""
    handle, close = new_owner()
    try:
        return _run_trace(rng, length, handle)
    finally:
        close()


def _run_trace(rng: random.Random, length: int, handle) -> tuple[int, int]:
    session = str(uuid.uuid4())
    open_frame = F.encode({"ncp": 2, "session": session, "seq": 0, "op": "open", "ack": None,
                           "body": {"application": "model", "contract": CONTRACT.identity, "bound": F.HANDSHAKE_BOUND}})
    open_response = handle(open_frame)
    open_request = ("q", 0, "open", None)  # distinct from any step request, as the real frames are
    model = (True, 0, (open_request, ("p", 0, open_request, "ok", None, M.OPEN)), False, 0)
    ghost = ((), None, True)
    real_id = {M.OPEN: F.identity(open_response)}  # model response identity -> real identity
    sent: list[tuple[tuple, bytes, bytes]] = [(open_request, open_frame, open_response)]
    accepted = [M.OPEN]
    compared = repeats = 0
    for _ in range(length):
        choice = rng.random()
        if choice < 0.2 and sent:
            request, frame, first = rng.choice(sent)
            fail = False
        else:
            base = len([item for item in accepted]) - 1
            seq = base + 1
            ack = accepted[-1]
            version: object = 0
            fail = False
            roll = rng.random()
            if roll < 0.10:
                version = "bad"
            elif roll < 0.18:
                seq = base + 2
            elif roll < 0.26 and len(accepted) > 1:
                ack = accepted[-2]
            elif roll < 0.30:
                ack = None
            elif roll < 0.34:
                seq = max(base, 1) - 1 if base else 0
            elif roll < 0.38:
                fail = True
            request = ("q", seq, version, ack)
            op = "step"
            body = {"seq": seq, "version": version if version == "bad" else 0, "fail": fail}
            frame = F.encode({"ncp": 2, "session": session, "seq": seq, "op": op,
                              "ack": None if ack is None else real_id.get(ack, "0" * 64), "body": body})
            first = None
        steps = M.owner_step(model, request, ghost, may_fail=fail)
        new_model, model_response, ghost, _ = steps[-1] if fail and len(steps) > 1 else steps[0]
        real = handle(frame)
        message = F.decode(real, F.MAX_BOUND).message
        expected = (model_response[3], model_response[4])
        observed = (message["outcome"], message["code"])
        assert observed == expected, f"{request}: model {expected}, real {observed}"
        if first is not None:
            if expected[0] != "rejected" and real != first and model_response == model[2][1]:
                raise AssertionError(f"{request}: a repeat returned different bytes")
            repeats += 1
        model = new_model
        if expected[0] in ("ok", "ended") and model_response[5] is not None:
            real_id[model_response[5]] = F.identity(real)
            if expected[0] == "ok" and model_response[5] not in accepted:
                accepted.append(model_response[5])
            sent.append((request, frame, real))
        compared += 1
        if expected[0] == "ended":
            break
    return compared, repeats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--traces", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--owner", nargs=argparse.REMAINDER, help="an external owner command")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    external = ExternalOwner(args.owner) if args.owner else None
    new_owner = external or python_owner
    total = repeats = 0
    try:
        for _ in range(args.traces):
            compared, repeated = run_trace(rng, rng.randint(1, 12), new_owner)
            total += compared
            repeats += repeated
    finally:
        if external:
            external.stop()
    name = " ".join(os.path.basename(part) for part in args.owner[:2]) if args.owner else "the Python owner"
    print(f"conformance: {args.traces} traces, {total} requests, {repeats} repeats; "
          f"{name} answers like the model owner")
    return 0


if __name__ == "__main__":
    sys.exit(main())
