#!/usr/bin/env python3
"""Check that the model's owner matches the real Python LocalOwner on random traces.

Each trace is a random sequence of requests and of correct or wrong
acknowledgements. Sequence 1 is `prepare` and later sequences are `step`, as the
v1 owner requires. Both owners receive the same trace; every outcome, code, and
execution count must agree. Usage: conformance.py [--traces 20000] [--seed 1]
"""
from __future__ import annotations

import argparse
import json
import random

from ncp_local import LocalBinding, LocalOwner
from ncp_local.protocol import make_request
from ncp_local.wire import encode

import model_check as model

OUTCOME = {"committed": "committed", "rejected_before_execution": "rejected",
           "unavailable": "unavailable", "acknowledged": "acknowledged"}


class Counting:
    def __init__(self):
        self.executed = []

    def validate(self, operation, body):
        pass

    def execute(self, operation, body):
        self.executed.append(operation)
        return {"step": len(self.executed)}

    def retire(self):
        pass


def run_trace(trace, binding):
    backend = Counting()
    real = LocalOwner(binding, backend)
    abstract_owner = (True, 0, None, None)
    ghost = ((0,) * 6, (), ())
    digests = {}
    for kind, seq, correct in trace:
        if kind == "req":
            operation = "prepare" if seq == 1 else "step"
            frame = ("req", seq)
            request = make_request(binding, seq, operation, {"n": 0} if seq == 1 else {"stimulus": 0})
        else:
            digest = digests.get(seq, "f" * 64) if correct else "e" * 64
            res = model.result_id(seq) if correct and seq in digests else model.WRONG
            frame = ("ack", seq, res)
            request = make_request(binding, seq, "ack", {"result_digest": digest})
        reply = json.loads(real.handle(encode(request)))
        if kind == "req" and reply["outcome"] == "committed":
            digests[seq] = reply["result_digest"]
        abstract_owner, abstract_reply, ghost = model.owner_handle(abstract_owner, frame, ghost)
        real_pair = (OUTCOME[reply["outcome"]], reply["code"])
        model_pair = (abstract_reply[2], abstract_reply[3])
        if real_pair != model_pair:
            return f"{trace}: real {real_pair} model {model_pair} at {(kind, seq, correct)}"
    if len(backend.executed) != sum(ghost[0]):
        return f"{trace}: real executed {len(backend.executed)}, model {sum(ghost[0])}"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--traces", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    binding = LocalBinding.fresh("neural")
    kinds = 0
    for index in range(args.traces):
        trace = []
        for _ in range(rng.randrange(1, 13)):
            if rng.random() < 0.5:
                trace.append(("req", rng.randrange(1, 5), True))
            else:
                trace.append(("ack", rng.randrange(1, 5), rng.random() < 0.7))
        failure = run_trace(trace, binding)
        if failure:
            raise SystemExit("MISMATCH " + failure)
        kinds += len(trace)
    print(f"conformance: {args.traces} traces, {kinds} frames; model owner equals LocalOwner")


if __name__ == "__main__":
    main()
