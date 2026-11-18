"""NEST alone, one Simulate of the whole run; writes every event of the spike recorder and of the
multimeter of networks7.build (content protocol 3). Usage: dump_events7.py SPEC_JSON OUT"""

import json
import sys

import nest

import networks7
from common import T_BIO_MS

spec = json.loads(sys.argv[1])
networks7.configure(nest, spec["threads"], spec["seed"])
neurons, recorder, meter = networks7.build(nest, spec["network"], spec["n"], spec["delta_ms"])
nest.Simulate(T_BIO_MS)
events = networks7.events(recorder, meter)
with open(sys.argv[2], "w") as handle:
    json.dump({"first": int(neurons[0].global_id), **{name: events[name].tolist() for name, _, _ in networks7.ARRAYS}},
              handle)
