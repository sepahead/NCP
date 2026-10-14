"""Shared network, parameters and timing helpers for the NEST coupling benchmark."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARAMS = json.loads((HERE / "params.json").read_text())
T_BIO_MS = 2000.0


def configure(nest) -> None:
    nest.ResetKernel()
    nest.verbosity = nest.VerbosityLevel.ERROR
    nest.resolution = 0.1
    nest.local_num_threads = 1
    nest.rng_seed = PARAMS["seed"]


def build(nest, delta_ms: float):
    """1,000 neurons, one Poisson drive each, 100 recurrent inputs each; every delay is delta."""
    n = PARAMS["n"]
    neurons = nest.Create("iaf_psc_alpha", n)
    drive = nest.Create("poisson_generator", n, params={"rate": PARAMS["drive_rate_hz"]})
    nest.Connect(drive, neurons, "one_to_one", {"weight": PARAMS["drive_weight_pa"], "delay": delta_ms})
    nest.Connect(neurons, neurons,
                 {"rule": "fixed_indegree", "indegree": PARAMS["indegree"], "allow_autapses": False},
                 {"weight": PARAMS["rec_weight_pa"], "delay": delta_ms})
    recorder = nest.Create("spike_recorder")
    nest.Connect(neurons, recorder)
    return neurons, recorder


class Reader:
    """n_events-delta readback. NEST 3.10 forbids clearing a recorder between Prepare and
    Cleanup, so each read copies the event arrays and keeps the part not yet seen."""

    def __init__(self, recorder) -> None:
        self.recorder = recorder
        self.seen = 0

    def take(self) -> tuple[list[int], list[float]]:
        n = self.recorder.n_events
        if n == self.seen:
            return [], []
        ev = self.recorder.events
        senders = [int(s) for s in ev["senders"][self.seen:n]]
        times = [float(t) for t in ev["times"][self.seen:n]]
        self.seen = n
        return senders, times


def load1() -> float:
    return os.getloadavg()[0]


def now() -> float:
    return time.perf_counter()
