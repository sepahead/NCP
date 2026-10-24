"""NEST owner for the NCP 2 arms: serves one session on its standard input and output.

Usage (started by a host): ncp2_owner.py
`prepare` carries the network, size, threads, interval, seed, and payload. Each `step` advances one
interval and returns the spike count, or the new spikes as two arrays: `senders` (u32) and `steps`
(i64, in steps of the 0.1 ms resolution). `finish` returns the recorder total so that the host can
check it.
"""

from __future__ import annotations

import os
import sys

# The protocol owns file descriptor 1. Keep a private copy for frames before NEST is imported, and
# send every other write, including NEST's start-up banner from C or Python, to standard error.
FRAMES_OUT = os.dup(1)
os.dup2(2, 1)
sys.stdout = sys.stderr
os.environ.setdefault("PYNEST_QUIET", "1")

import array  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

import nest  # noqa: E402

import ncp  # noqa: E402
import networks  # noqa: E402
from common import save_times, tick  # noqa: E402

HERE = Path(__file__).resolve().parent
CONTRACT = ncp.Contract.load(HERE / "ncp2_contract.json")


def little_endian(values: array.array) -> bytes:
    if sys.byteorder == "big":
        values.byteswap()
    return values.tobytes()


class Nest:
    def __init__(self) -> None:
        self.spec: dict | None = None
        self.recorder = None
        self.reader = None
        self.spike_files: str | None = None
        self.prepared = False
        self.work: list[int] = []

    def validate(self, op: str, body) -> None:
        if op == "prepare":
            if (
                type(body) is not dict
                or body.get("network") not in networks.NETWORKS
                or body.get("payload") not in ("count", "spikes")
                or self.prepared
            ):
                raise ncp.BodyInvalid("prepare body")
        elif op == "step":
            if body != {"stimulus": 0} or not self.prepared:
                raise ncp.BodyInvalid("step body, or step before prepare")

    def execute(self, op: str, body):
        if op == "prepare":
            self.spec = dict(body)
            networks.configure(nest, int(body["threads"]), int(body["seed"]))
            if body["payload"] == "spikes":
                self.spike_files = tempfile.mkdtemp(prefix="ncp-nest-spikes-")
            _, self.recorder = networks.build(
                nest, body["network"], int(body["n"]), float(body["delta_ms"]), self.spike_files
            )
            self.reader = networks.Reader(nest, self.spike_files)
            nest.Prepare()
            self.prepared = True
            return {"prepared": True}
        if op == "step":
            start = tick()
            nest.Run(float(self.spec["delta_ms"]))
            if self.spec["payload"] == "count":
                count = self.reader.count()
                self.work.append(tick() - start)
                return {"count": count}
            senders, steps = self.reader.take()
            self.work.append(tick() - start)
            count = len(senders)
            return {
                "senders": ncp.Array("u32", [count], little_endian(array.array("I", senders))),
                "steps": ncp.Array("i64", [count], little_endian(array.array("q", steps))),
            }
        # finish
        total = int(self.recorder.n_events) if self.recorder is not None else 0
        self.retire()
        save_times("NCP_WORK_TIMES", self.work)
        return {"recorded": total}

    def retire(self) -> None:
        if self.prepared:
            nest.Cleanup()
            self.prepared = False
        if self.spike_files is not None:
            shutil.rmtree(self.spike_files, ignore_errors=True)
            self.spike_files = None


def main() -> None:
    owner = ncp.Owner(CONTRACT.application, CONTRACT.identity, Nest(), CONTRACT.operations)
    ncp.serve(owner, ncp.StreamChannel.from_fds(0, FRAMES_OUT))


if __name__ == "__main__":
    main()
