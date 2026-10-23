"""MUSIC arm, peer side: counts every spike event and sends one acknowledgement per tick.
Writes its JSON result to BENCH_PEER_OUT."""
from __future__ import annotations

import json
import os

import music

setup = music.Setup()
stoptime = setup.config("stoptime")
timestep = setup.config("timestep")
received = 0


def on_spike(_time, _type, _index):
    global received
    received += 1


spikes_in = setup.publishEventInput("spikes_in")
spikes_in.map(on_spike, music.Index.GLOBAL, base=0, size=spikes_in.width(), accLatency=2 * timestep)
ack_out = setup.publishEventOutput("ack_out")
ack_out.map(music.Index.GLOBAL, base=0, size=1)
runtime = music.Runtime(setup, timestep)
ticks = 0
for t in runtime:
    if t > stoptime:
        break
    ack_out.insertEvent(t, 0, music.Index.GLOBAL)
    ticks += 1
runtime.finalize()
with open(os.environ["BENCH_PEER_OUT"], "w") as handle:
    json.dump({"received": received, "ticks": ticks}, handle)
