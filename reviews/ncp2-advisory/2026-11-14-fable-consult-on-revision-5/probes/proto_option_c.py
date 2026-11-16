"""Probe of the scratch prototype of option (c) (profile revision 4, proposed): open reports,
ncp.lockstep.take takes with a term. Usage: probe.py PROTOTYPE_PYTHON_SDK_DIR"""
import sys
sys.path.insert(0, sys.argv[1]); sys.dont_write_bytecode = True
import ncp
from ncp import lockstep as L

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}'
)
KEY = bytes(range(32))
class World:
    position = 0
    def validate(self, request): pass
    def execute(self, request):
        self.position += request.body["dx"]; return {"position": self.position}
    def state(self): return f"p{self.position}"
class Wire:
    lossy = False; local = True
    def __init__(self, owner): self.owner, self.sent, self.replies, self.hold = owner, [], [], False
    def send(self, frame):
        self.sent.append(bytes(frame))
        if not self.hold: self.replies.append(self.owner.handle(frame))
    def receive(self, bound, timeout):
        if not self.replies: raise TimeoutError("no frame before the time limit")
        return self.replies.pop(0)
    def close(self): pass
def client(wire, features=True):
    return ncp.Client(wire, CONTRACT, features={"ncp.lockstep": {}} if features else None, key=KEY, timeout=0.01)
def show(frame):
    m = ncp.decode(frame, ncp.DEFAULT_BOUND, key=KEY).message
    return f'{m["outcome"]} {m["code"]} {str(m["body"])[:70]}'

world = World(); core = ncp.Lockstep(world, ["step"])
def owner(): return ncp.Owner(CONTRACT, core, key=KEY)

print("C1. a monitor opens with the feature and takes nothing")
o_live = owner(); w_live = Wire(o_live); live = ncp.LockstepClient(client(w_live)); live.step("step", {"dx": 1})
monitor = client(Wire(owner())); monitor.open()
print("    monitor's report:", monitor.enabled["ncp.lockstep"], "| holder is still the live opening:", core.holder == live.client.nonce)
live.step("step", {"dx": 1}); print("    live client stepped to tick", core.tick)

print("C2. a replayed copy of the live client's open, and of its take, on a new connection")
o3 = owner()
print("    replayed open ->", show(o3.handle(w_live.sent[0]))[:40], "| holder unchanged:", core.holder == live.client.nonce)
print("    replayed take in the copy's opening ->", show(o3.handle(w_live.sent[1])))
live.step("step", {"dx": 1}); print("    live client stepped to tick", core.tick)

print("C3. a delayed take of an abandoned opening arrives after a newer take")
o_a = owner(); w_a = Wire(o_a); abandoned = client(w_a); abandoned.open(); w_a.hold = True
try: abandoned.call(L.TAKE, {"term": abandoned.enabled["ncp.lockstep"]["term"]})
except ncp.Ended as e: print("    take in the abandoned opening:", e.code, "executed:", e.executed.value)
newer = ncp.LockstepClient(client(Wire(owner())))        # the client opens again and takes
print("    newer opening holds:", core.holder == newer.client.nonce, "| term", core.term)
print("    delayed take ->", show(o_a.handle(w_a.sent[-1])), "| holder unchanged:", core.holder == newer.client.nonce)

print("C4. the same delayed take when no newer take happened: it succeeds once, and the next take sees it")
o_b = owner(); w_b = Wire(o_b); b = client(w_b); b.open(); w_b.hold = True
try: b.call(L.TAKE, {"term": b.enabled["ncp.lockstep"]["term"]})
except ncp.Ended: pass
c = client(Wire(owner())); c.open()                       # report read before the delayed take arrives
print("    delayed take ->", show(o_b.handle(w_b.sent[-1]))[:60])
stepper = ncp.LockstepClient(c)                           # its take names the old term: declined once, then ok
print("    the live client's take succeeded after one declined attempt | holder:", core.holder == c.nonce, "| term", core.term)

print("C5. a feature operation without the feature, and with a closed contract")
plain = client(Wire(owner()), features=False); plain.open()
try: plain.call(L.TAKE, {"term": core.term})
except ncp.Declined as d: print("    take in a session without the feature -> declined", d.code)
try: plain.call("ncp.other.thing", {})
except ncp.Declined as d: print("    ncp.other.thing -> declined", d.code)
