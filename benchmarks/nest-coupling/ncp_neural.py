"""NEST neural endpoint for the NCP arm: serves ncp_local requests on its private pipes.

Usage (launched by ncp_host.py): ncp_neural.py BINDING_JSON
"""
from __future__ import annotations

import json
import os
import sys

# The protocol owns file descriptor 1. Keep a private copy for frames and send every other
# write, including NEST's start-up banner from C or Python, to standard error.
PROTOCOL_OUT = os.fdopen(os.dup(1), "wb", buffering=0)
os.dup2(2, 1)
sys.stdout = sys.stderr
os.environ.setdefault("PYNEST_QUIET", "1")

import nest  # noqa: E402
from ncp_local import LocalBinding, LocalOwner, serve_local  # noqa: E402

from common import Reader, build, configure  # noqa: E402


class NestBackend:
    def __init__(self) -> None:
        self.reader = None
        self.recorder = None
        self.seen = 0
        self.payload = None
        self.delta = None
        self.prepared = False

    def validate(self, operation: str, body) -> None:
        if operation == "prepare":
            if (type(body) is not dict or type(body.get("delta_ms")) not in (int, float)
                    or body.get("payload") not in ("count", "spikes")):
                raise ValueError("prepare body")
        elif operation == "step":
            if type(body) is not dict or body.get("stimulus") != 0:
                raise ValueError("step body")

    def execute(self, operation: str, body):
        if operation == "prepare":
            self.delta = float(body["delta_ms"])
            self.payload = body["payload"]
            configure(nest)
            _, self.recorder = build(nest, self.delta)
            self.reader = Reader(self.recorder)
            nest.Prepare()
            self.prepared = True
            return {"prepared": True}
        if operation == "step":
            nest.Run(self.delta)
            if self.payload == "count":
                n = self.recorder.n_events
                count, self.seen = n - self.seen, n
                return {"count": count}
            senders, times = self.reader.take()
            return {"senders": senders, "times": times}
        if operation in ("finish", "abort"):
            if self.prepared:
                nest.Cleanup()
                self.prepared = False
            return {"finished": True}
        raise ValueError(operation)

    def retire(self) -> None:
        if self.prepared:
            nest.Cleanup()
            self.prepared = False


def main() -> None:
    binding = LocalBinding.from_dict(json.loads(sys.argv[1]))
    owner = LocalOwner(binding, NestBackend())
    serve_local(owner, sys.stdin.buffer, PROTOCOL_OUT)


if __name__ == "__main__":
    main()
