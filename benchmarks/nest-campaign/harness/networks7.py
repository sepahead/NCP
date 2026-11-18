"""Networks of content protocol 3 (see ../PROTOCOL-CONTENT-3.md), for revision 7 of the SDKs.

The three networks of the earlier protocols (networks.py, unchanged) and five more NEST models:

- hh: Hodgkin-Huxley neurons (hh_psc_alpha), integrated with an adaptive step;
- izhikevich: the regular-spiking neurons of Izhikevich (2003);
- gif: generalized integrate-and-fire neurons with escape noise (gif_psc_exp), which draw random
  numbers in every step, so that their spikes depend on the random streams of each thread;
- precise: neurons with precise spike times (iaf_psc_exp_ps), which spike between grid points,
  so that each spike carries an offset as a float64;
- brunel_stdp: the Brunel network with spike-timing-dependent plasticity (stdp_synapse) on the
  connections from excitatory neurons, so that the weights change during the run.

Each has 80 percent excitatory and 20 percent inhibitory neurons, recurrent connections whose delay
equals the exchange interval, and a Poisson drive. `build` adds one spike recorder for every neuron
and one multimeter for the membrane potential of the first VM_NEURONS neurons, at every step of
the 0.1 ms resolution. Both record to memory, with time in steps, so that the owner can read the
events of one interval and then clear them, and a spike of the precise model keeps its offset.
"""

from __future__ import annotations

import networks

NETWORKS = networks.NETWORKS + ("hh", "izhikevich", "gif", "precise", "brunel_stdp")
VM_NEURONS = 20
configure = networks.configure
# The arrays of a step response: name, NCP 2 dtype, and NumPy layout.
ARRAYS = (
    ("senders", "u32", "<u4"),
    ("steps", "i64", "<i8"),
    ("offsets", "f64", "<f8"),
    ("vm_senders", "u32", "<u4"),
    ("vm_steps", "i64", "<i8"),
    ("vm_values", "f64", "<f8"),
)


def _recurrent(nest, neurons, delta: float, w_e: float, w_i: float, synapse: dict | None = None) -> None:
    """80 excitatory and 20 inhibitory inputs to each neuron, from 80 and 20 percent of them."""
    n_e = int(0.8 * len(neurons))
    excitatory, inhibitory = neurons[:n_e], neurons[n_e:]
    nest.Connect(excitatory, neurons, {"rule": "fixed_indegree", "indegree": 80, "allow_autapses": False},
                 synapse or {"weight": w_e, "delay": delta})
    nest.Connect(inhibitory, neurons, {"rule": "fixed_indegree", "indegree": 20, "allow_autapses": False},
                 {"weight": w_i, "delay": delta})


def _driven(nest, model: str, n: int, delta: float, rate: float, weight: float, w_e: float, w_i: float):
    neurons = nest.Create(model, n)
    drive = nest.Create("poisson_generator", n, params={"rate": rate})
    nest.Connect(drive, neurons, "one_to_one", {"weight": weight, "delay": delta})
    _recurrent(nest, neurons, delta, w_e, w_i)
    return neurons


def hh(nest, n: int, delta: float):
    """hh_psc_alpha with default parameters; weights in pA."""
    return _driven(nest, "hh_psc_alpha", n, delta, rate=10000.0, weight=60.0, w_e=5.0, w_i=-20.0)


def izhikevich(nest, n: int, delta: float):
    """izhikevich with the default regular-spiking parameters; weights in mV."""
    return _driven(nest, "izhikevich", n, delta, rate=3000.0, weight=3.0, w_e=0.5, w_i=-2.0)


def gif(nest, n: int, delta: float):
    """gif_psc_exp with default parameters; weights in pA."""
    return _driven(nest, "gif_psc_exp", n, delta, rate=3000.0, weight=40.0, w_e=5.0, w_i=-20.0)


def precise(nest, n: int, delta: float):
    """iaf_psc_exp_ps with default parameters; weights in pA."""
    return _driven(nest, "iaf_psc_exp_ps", n, delta, rate=12000.0, weight=30.0, w_e=2.0, w_i=-8.0)


def brunel_stdp(nest, n: int, delta: float):
    """The Brunel network of networks.py, with stdp_synapse on the excitatory connections.

    J = 0.1 mV starts every plastic weight, which can grow to Wmax = 0.3 mV.
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
                 {"synapse_model": "stdp_synapse", "weight": j, "Wmax": 3 * j, "delay": delta})
    nest.Connect(inhibitory, neurons, {"rule": "fixed_indegree", "indegree": c_i, "allow_autapses": False},
                 {"weight": -g * j, "delay": delta})
    return neurons


BUILDERS = {
    "alpha": networks.alpha,
    "brunel": networks.brunel,
    "aeif": networks.aeif,
    "hh": hh,
    "izhikevich": izhikevich,
    "gif": gif,
    "precise": precise,
    "brunel_stdp": brunel_stdp,
}


def build(nest, network: str, n: int, delta: float):
    """Build the network, a spike recorder for every neuron, and a multimeter for the membrane
    potential of the first VM_NEURONS neurons. Returns the neurons, the recorder, and the meter."""
    neurons = BUILDERS[network](nest, n, delta)
    recorder = nest.Create("spike_recorder", params={"record_to": "memory", "time_in_steps": True})
    meter = nest.Create("multimeter", params={"record_from": ["V_m"], "interval": nest.resolution,
                                              "record_to": "memory", "time_in_steps": True})
    nest.Connect(neurons, recorder)
    nest.Connect(meter, neurons[:VM_NEURONS])
    return neurons, recorder, meter


def events(recorder, meter) -> dict:
    """Every event that the two devices hold: spikes as (sender, step, offset) and the membrane
    potential as (sender, step, value). Senders are global node ids."""
    spikes, potential = recorder.get("events"), meter.get("events")
    return {
        "senders": spikes["senders"], "steps": spikes["times"], "offsets": spikes["offsets"],
        "vm_senders": potential["senders"], "vm_steps": potential["times"], "vm_values": potential["V_m"],
    }


def clear(recorder, meter) -> None:
    """Delete the events that the devices hold; NEST allows it only between two simulations."""
    recorder.n_events = 0
    meter.n_events = 0
