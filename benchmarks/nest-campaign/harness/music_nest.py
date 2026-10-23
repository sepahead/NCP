"""MUSIC arm, NEST side: every neuron feeds one event-out proxy on its own channel; the
peer's acknowledgement reaches an isolated parrot neuron. The run specification comes
from BENCH_SPEC (JSON); the result goes to BENCH_OUT."""
from __future__ import annotations

import json
import os

import nest

import networks
from common import T_BIO_MS, load1, now


def main() -> None:
    spec = json.loads(os.environ["BENCH_SPEC"])
    delta = spec["delta_ms"]
    networks.configure(nest, spec["threads"], spec["seed"])
    neurons, recorder = networks.build(nest, spec["network"], spec["n"], delta)
    out_proxy = nest.Create("music_event_out_proxy", params={"port_name": "spikes_out"})
    for channel, neuron in enumerate(neurons):
        nest.Connect(neuron, out_proxy, syn_spec={"music_channel": channel})
    ack_proxy = nest.Create("music_event_in_proxy", params={"port_name": "ack_in", "music_channel": 0})
    sink = nest.Create("parrot_neuron")
    nest.Connect(ack_proxy, sink, syn_spec={"delay": delta})
    load = load1()
    nest.Prepare()
    t0 = now()
    nest.Run(T_BIO_MS)
    t1 = now()
    recorded = int(recorder.n_events)
    nest.Cleanup()
    with open(os.environ["BENCH_OUT"], "w") as handle:
        json.dump({"arm": "music", **spec, "wall_s": t1 - t0, "recorded": recorded,
                   "exchanges": round(T_BIO_MS / delta), "load1": load}, handle)


if __name__ == "__main__":
    main()
