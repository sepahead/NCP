"""Networks of the NEST campaign (see ../PROTOCOL.md).

Each builder creates neurons, their input, recurrent connections whose delay equals the
exchange interval delta, and one spike recorder connected to every neuron. With delay
delta, the minimum delay of NEST and the MUSIC tick both equal delta, as in the
preregistered coupling benchmark of 13 October 2026.
"""
from __future__ import annotations

import os

NETWORKS = ("alpha", "brunel", "aeif")


def configure(nest, threads: int, seed: int) -> None:
    nest.ResetKernel()
    nest.verbosity = nest.VerbosityLevel.ERROR
    nest.resolution = 0.1
    nest.local_num_threads = threads
    nest.rng_seed = seed


def alpha(nest, n: int, delta: float):
    """Current-based alpha neurons, one Poisson drive each, 100 recurrent inputs each.

    The parameters of the coupling benchmark of 13 October 2026, with n neurons.
    """
    neurons = nest.Create("iaf_psc_alpha", n)
    drive = nest.Create("poisson_generator", n, params={"rate": 6000.0})
    nest.Connect(drive, neurons, "one_to_one", {"weight": 10.4, "delay": delta})
    nest.Connect(neurons, neurons, {"rule": "fixed_indegree", "indegree": 100, "allow_autapses": False},
                 {"weight": 2.0, "delay": delta})
    return neurons


def brunel(nest, n: int, delta: float):
    """Balanced random network of Brunel (2000), model A, in the asynchronous irregular state.

    80 percent excitatory and 20 percent inhibitory iaf_psc_delta neurons, connection
    probability 0.1 as a fixed indegree, J = 0.1 mV, g = 5, external drive eta = 2 as in
    the NEST example brunel_delta_nest.py.
    """
    n_e, n_i = int(0.8 * n), n - int(0.8 * n)
    c_e, c_i = max(1, int(0.1 * n_e)), max(1, int(0.1 * n_i))
    j, g, eta, tau_m, theta = 0.1, 5.0, 2.0, 20.0, 20.0
    params = {"C_m": 1.0, "tau_m": tau_m, "t_ref": 2.0, "E_L": 0.0, "V_reset": 0.0, "V_m": 0.0, "V_th": theta}
    excitatory = nest.Create("iaf_psc_delta", n_e, params=params)
    inhibitory = nest.Create("iaf_psc_delta", n_i, params=params)
    neurons = excitatory + inhibitory
    nu_th = theta / (j * c_e * tau_m)
    drive = nest.Create("poisson_generator", params={"rate": 1000.0 * eta * nu_th * c_e})
    nest.Connect(drive, neurons, syn_spec={"weight": j, "delay": delta})
    nest.Connect(excitatory, neurons, {"rule": "fixed_indegree", "indegree": c_e, "allow_autapses": False},
                 {"weight": j, "delay": delta})
    nest.Connect(inhibitory, neurons, {"rule": "fixed_indegree", "indegree": c_i, "allow_autapses": False},
                 {"weight": -g * j, "delay": delta})
    return neurons


AEIF_DRIVE_HZ = 7000.0
AEIF_DRIVE_NS = 10.0


def aeif(nest, n: int, delta: float):
    """Conductance-based adaptive exponential neurons (aeif_cond_exp, default parameters).

    80 percent excitatory and 20 percent inhibitory, 100 recurrent inputs each, one Poisson
    drive each. The drive rate comes from a calibration run, recorded in the README.
    """
    n_e = int(0.8 * n)
    neurons = nest.Create("aeif_cond_exp", n)
    excitatory, inhibitory = neurons[:n_e], neurons[n_e:]
    drive = nest.Create("poisson_generator", n, params={"rate": AEIF_DRIVE_HZ})
    nest.Connect(drive, neurons, "one_to_one", {"weight": AEIF_DRIVE_NS, "delay": delta})
    nest.Connect(excitatory, neurons, {"rule": "fixed_indegree", "indegree": 80, "allow_autapses": False},
                 {"weight": 1.0, "delay": delta})
    nest.Connect(inhibitory, neurons, {"rule": "fixed_indegree", "indegree": 20, "allow_autapses": False},
                 {"weight": -4.0, "delay": delta})
    return neurons


def build(nest, network: str, n: int, delta: float, spike_files: str | None = None):
    """Build the network and one spike recorder connected to every neuron.

    With `spike_files`, the recorder writes ASCII files to that directory, with spike times
    in simulation steps, so that `Reader.take` can read only the new spikes.
    """
    neurons = {"alpha": alpha, "brunel": brunel, "aeif": aeif}[network](nest, n, delta)
    recorder = nest.Create("spike_recorder")
    if spike_files is not None:
        nest.SetKernelStatus({"data_path": spike_files, "overwrite_files": True})
        recorder.set(record_to="ascii", label="spikes", time_in_steps=True)
    nest.Connect(neurons, recorder)
    return neurons, recorder


class Reader:
    """Spike readback after each interval, in time that does not grow with the run.

    Reading a recorder's `n_events` or `events` copies all of its events, so a read after
    each interval would cost time in proportion to every spike so far. `count` therefore
    reads the kernel's `local_spike_counter`, the number of spikes in the last `Run`. It
    equals the recorder's count because the recorder records every neuron, and the owner
    checks the total against the recorder once, at the end.

    `take` reads the recorder's ASCII files (see `build`). NEST flushes them after each
    `Run`, one file per thread, so each read starts at the last complete line of each file.
    It checks the number of new spikes against the kernel counter.
    """

    def __init__(self, nest, spike_files: str | None = None) -> None:
        self.nest = nest
        self.spike_files = spike_files
        self.offsets: dict[str, int] = {}

    def count(self) -> int:
        return int(self.nest.GetKernelStatus("local_spike_counter"))

    def take(self) -> tuple[list[int], list[int]]:
        expected = self.count()
        senders: list[int] = []
        steps: list[int] = []
        for name in sorted(os.listdir(self.spike_files)):
            if not (name.startswith("spikes-") and name.endswith(".dat")):
                continue
            path = os.path.join(self.spike_files, name)
            with open(path, "rb") as handle:
                handle.seek(self.offsets.get(path, 0))
                data = handle.read()
            complete = data.rfind(b"\n") + 1
            self.offsets[path] = self.offsets.get(path, 0) + complete
            for line in data[:complete].splitlines():
                if line[:1].isdigit():
                    sender, step = line.split()[:2]
                    senders.append(int(sender))
                    steps.append(int(step))
        if len(senders) != expected:
            raise RuntimeError(f"readback found {len(senders)} new spikes, the kernel counted {expected}")
        return senders, steps
