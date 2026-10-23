import json, os
import nest
import networks
from common import T_BIO_MS
spec = json.loads(os.environ["BENCH_SPEC"])
networks.configure(nest, spec["threads"], spec["seed"])
neurons, recorder = networks.build(nest, spec["network"], spec["n"], spec["delta_ms"])
out_proxy = nest.Create("music_event_out_proxy", params={"port_name": "spikes_out"})
first = neurons[0].global_id
import os as _os
if _os.environ.get("CONNECT_FORM") == "list":
    nest.Connect(neurons, out_proxy, "all_to_all", {"music_channel": [list(range(len(neurons)))]})
else:
    for channel, neuron in enumerate(neurons):
        nest.Connect(neuron, out_proxy, syn_spec={"music_channel": channel})
ack_proxy = nest.Create("music_event_in_proxy", params={"port_name": "ack_in", "music_channel": 0})
sink = nest.Create("parrot_neuron")
nest.Connect(ack_proxy, sink, syn_spec={"delay": spec["delta_ms"]})
nest.Prepare(); nest.Run(T_BIO_MS)
ev = recorder.events
with open(os.environ["BENCH_EVENTS"], "w") as h:
    json.dump({"first": first, "senders": [int(s) for s in ev["senders"]], "times": [float(t) for t in ev["times"]]}, h)
nest.Cleanup()
