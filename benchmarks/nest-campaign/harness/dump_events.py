"""NEST alone, one Run; writes the recorder's complete events. Usage: dump_events.py SPEC_JSON OUT"""
import json
import sys

import nest

import networks
from common import T_BIO_MS

spec = json.loads(sys.argv[1])
networks.configure(nest, spec["threads"], spec["seed"])
neurons, recorder = networks.build(nest, spec["network"], spec["n"], spec["delta_ms"])
nest.Simulate(T_BIO_MS)
events = recorder.events
with open(sys.argv[2], "w") as handle:
    json.dump({"first": neurons[0].global_id, "senders": [int(s) for s in events["senders"]],
               "times": [float(t) for t in events["times"]]}, handle)
