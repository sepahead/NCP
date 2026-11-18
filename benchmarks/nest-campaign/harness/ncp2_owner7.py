"""NEST owner of content protocol 3 (see ../PROTOCOL-CONTENT-3.md), on revision 7 of the SDKs.

Usage (started by a host): ncp2_owner7.py
Serves one session on its standard input and output. `prepare` carries the network, size,
threads, interval, and seed, and returns the global id of the first neuron. Each `step`
simulates one interval with `nest.Simulate` and returns every event of that interval as six
arrays: the spikes (`senders` u32, `steps` i64 in steps of the 0.1 ms resolution, `offsets`
f64 in ms) and the membrane potential (`vm_senders` u32, `vm_steps` i64, `vm_values` f64 in mV);
then it clears the devices. A step whose number of spikes differs from NEST's kernel counter
fails. `finish` returns the totals that the owner sent.

A body that no state accepts is declined with `body_invalid`; a valid request in the wrong state
(a second `prepare`, a `step` before `prepare`) is declined with `conflict` and a reason.
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

from pathlib import Path  # noqa: E402

import nest  # noqa: E402
import numpy  # noqa: E402

import ncp  # noqa: E402
import networks7  # noqa: E402

HERE = Path(__file__).resolve().parent
CONTRACT = ncp.Contract.load(HERE / "ncp2_contract.json")
SPEC = {"network", "n", "threads", "delta_ms", "seed"}
ARRAYS = networks7.ARRAYS


def array(values, dtype: str, layout: str) -> ncp.Array:
    data = numpy.ascontiguousarray(numpy.asarray(values), dtype=layout)
    return ncp.Array(dtype, [len(data)], data.tobytes())


class Nest:
    def __init__(self) -> None:
        self.spec: dict | None = None
        self.recorder = None
        self.meter = None
        self.sent = {"spikes": 0, "vm": 0}

    def validate(self, request: ncp.Request) -> None:
        op, body = request.op, request.body
        if op == "prepare":
            if (
                type(body) is not dict
                or set(body) != SPEC
                or body["network"] not in networks7.NETWORKS
                or not all(type(body[key]) is int and body[key] > 0 for key in ("n", "threads", "seed"))
                or type(body["delta_ms"]) not in (int, float)
                or not body["delta_ms"] > 0
            ):
                raise ncp.Declined("prepare: network, n, threads, delta_ms, seed")
            if self.spec is not None:
                raise ncp.Declined("prepared already", code="conflict", reason="nest.prepared")
        elif op in ("step", "finish"):
            if body != {}:
                raise ncp.Declined(f"{op}: the body is an empty object")
            if self.spec is None:
                raise ncp.Declined(f"{op} before prepare", code="conflict", reason="nest.unprepared")

    def execute(self, request: ncp.Request):
        op, body = request.op, request.body
        if op == "prepare":
            self.spec = dict(body)
            networks7.configure(nest, body["threads"], body["seed"])
            neurons, self.recorder, self.meter = networks7.build(
                nest, body["network"], body["n"], float(body["delta_ms"])
            )
            return {"first": int(neurons[0].global_id)}
        if op == "step":
            nest.Simulate(float(self.spec["delta_ms"]))
            counted = int(nest.GetKernelStatus("local_spike_counter"))
            events = networks7.events(self.recorder, self.meter)
            networks7.clear(self.recorder, self.meter)
            if len(events["senders"]) != counted:
                raise RuntimeError(f"the recorder holds {len(events['senders'])} spikes, the kernel counted {counted}")
            self.sent["spikes"] += counted
            self.sent["vm"] += len(events["vm_values"])
            return {name: array(events[name], dtype, layout) for name, dtype, layout in ARRAYS}
        return dict(self.sent)  # finish


def main() -> None:
    ncp.serve(ncp.Owner(CONTRACT, Nest()), ncp.StreamChannel.from_fds(0, FRAMES_OUT))


if __name__ == "__main__":
    main()
