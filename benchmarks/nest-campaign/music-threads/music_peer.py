import json, os
import music
setup = music.Setup()
stoptime = setup.config("stoptime"); timestep = setup.config("timestep")
events = []
def on_spike(t, _type, index):
    events.append((index, t))
spikes_in = setup.publishEventInput("spikes_in")
spikes_in.map(on_spike, music.Index.GLOBAL, base=0, size=spikes_in.width(), accLatency=2 * timestep)
ack_out = setup.publishEventOutput("ack_out"); ack_out.map(music.Index.GLOBAL, base=0, size=1)
runtime = music.Runtime(setup, timestep)
for t in runtime:
    if t > stoptime:
        break
    ack_out.insertEvent(t, 0, music.Index.GLOBAL)
runtime.finalize()
with open(os.environ["BENCH_PEER_EVENTS"], "w") as h:
    json.dump(events, h)
