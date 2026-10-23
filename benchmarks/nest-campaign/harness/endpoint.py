"""NEST owner for the NCP arms: serves ncp_local requests on its private pipes.

Usage (started by a host): endpoint.py BINDING_JSON
`prepare` carries the network, size, threads, interval, seed, and payload. Each `step`
advances one interval and returns the spike count or the new spikes. `finish` returns
the recorder total so that the host can check it.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

# The protocol owns file descriptor 1. Keep a private copy for frames and send every other
# write, including NEST's start-up banner from C or Python, to standard error.
PROTOCOL_OUT = os.fdopen(os.dup(1), "wb", buffering=0)
os.dup2(2, 1)
sys.stdout = sys.stderr
os.environ.setdefault("PYNEST_QUIET", "1")

import nest  # noqa: E402
from ncp_local import LocalBinding, LocalOwner, serve_local  # noqa: E402

import networks  # noqa: E402


# Fault campaign only: raise inside this step number (counted from 1). Unset in every
# performance run.
RAISE_STEP = int(os.environ.get("NCP_FAULT_RAISE_STEP", "0"))


class NestBackend:
    def __init__(self) -> None:
        self.spec = None
        self.recorder = None
        self.reader = None
        self.spike_files = None
        self.prepared = False
        self.steps = 0

    def validate(self, operation: str, body) -> None:
        if operation == "prepare":
            if (type(body) is not dict or body.get("network") not in networks.NETWORKS
                    or body.get("payload") not in ("count", "spikes")):
                raise ValueError("prepare body")
        elif operation == "step" and body != {"stimulus": 0}:
            raise ValueError("step body")

    def execute(self, operation: str, body):
        if operation == "prepare":
            self.spec = dict(body)
            networks.configure(nest, int(body["threads"]), int(body["seed"]))
            if body["payload"] == "spikes":
                self.spike_files = tempfile.mkdtemp(prefix="ncp-nest-spikes-")
            _, self.recorder = networks.build(nest, body["network"], int(body["n"]), float(body["delta_ms"]),
                                              self.spike_files)
            self.reader = networks.Reader(nest, self.spike_files)
            nest.Prepare()
            self.prepared = True
            return {"prepared": True}
        if operation == "step":
            self.steps += 1
            if self.steps == RAISE_STEP:
                raise RuntimeError("injected failure inside a NEST step")
            nest.Run(float(self.spec["delta_ms"]))
            if self.spec["payload"] == "count":
                return {"count": self.reader.count()}
            senders, steps = self.reader.take()
            return {"senders": senders, "steps": steps}
        if operation in ("finish", "abort"):
            total = int(self.recorder.n_events) if self.recorder is not None else 0
            self.retire()
            return {"finished": True, "recorded": total}
        raise ValueError(operation)

    def retire(self) -> None:
        if self.prepared:
            nest.Cleanup()
            self.prepared = False
        if self.spike_files is not None:
            shutil.rmtree(self.spike_files, ignore_errors=True)
            self.spike_files = None


def main() -> None:
    binding = LocalBinding.from_dict(json.loads(sys.argv[1]))
    serve_local(LocalOwner(binding, NestBackend()), sys.stdin.buffer, PROTOCOL_OUT)


if __name__ == "__main__":
    main()
