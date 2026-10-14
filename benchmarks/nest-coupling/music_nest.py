"""MUSIC arm, NEST side: every neuron feeds one event-out proxy on its own channel; the peer's
acknowledgement reaches an isolated parrot neuron. Writes its JSON result to BENCH_OUT."""
from __future__ import annotations

import json
import os

import nest

from common import T_BIO_MS, Reader, build, configure, load1, now


def main() -> None:
    delta = float(os.environ["BENCH_DELTA_MS"])
    configure(nest)
    neurons, recorder = build(nest, delta)
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
    senders, _ = Reader(recorder).take()
    nest.Cleanup()
    with open(os.environ["BENCH_OUT"], "w") as handle:
        json.dump({"arm": "music", "delta_ms": delta, "wall_s": t1 - t0, "spikes": len(senders), "load1": load},
                  handle)


if __name__ == "__main__":
    main()
