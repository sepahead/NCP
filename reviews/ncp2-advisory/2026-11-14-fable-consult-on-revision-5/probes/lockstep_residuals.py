"""Probes R2 to R5 (revision 5), byte-stream shape: one owner object for each connection, one
shared Lockstep. Usage: probe.py PYTHON_SDK_DIR"""
import sys
sys.path.insert(0, sys.argv[1]); sys.dont_write_bytecode = True
import ncp

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}'
)

class World:
    def __init__(self, position=0): self.position = position
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

def client(wire, **more): return ncp.Client(wire, CONTRACT, features={"ncp.lockstep": {}}, timeout=0.01, **more)
def outcome(frame): 
    m = ncp.decode(frame, ncp.DEFAULT_BOUND).message
    return f'{m["outcome"]} {m["code"]} {m["body"].get("detail", "")[:48]}'

print("R2. recover() with a client that was opened BEFORE the uncertain step was sent")
world = World(); core = ncp.Lockstep(world, ["step"])
standby = client(Wire(ncp.Owner(CONTRACT, core))); standby.open()          # opened early, with the feature
o1 = ncp.Owner(CONTRACT, core); w1 = Wire(o1); a = ncp.LockstepClient(client(w1))   # the stepping session opens later
w1.hold = True
try: a.step("step", {"dx": 10})
except ncp.Ended as e: print("   s delayed:", e.code)
verdict = a.recover(standby)
print("   recover(standby) -> verdict", verdict.value, "| holder is the standby opening:", core.holder == standby.nonce)
print("   delayed s ->", outcome(o1.handle(w1.sent[-1])), "| tick", core.tick,
      "=> the verdict NO was FALSE" if core.tick == 1 and verdict is ncp.Executed.NO else "")

print("R3. a nonce source that repeats (assumption A4 broken): scenario 1 of D1 again")
world = World(); core = ncp.Lockstep(world, ["step"]); fixed = lambda: "00" * 16
SESSION = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b"
o1 = ncp.Owner(CONTRACT, core, nonce=fixed); w1 = Wire(o1); a = ncp.LockstepClient(client(w1, session=SESSION))
w1.hold = True
try: a.step("step", {"dx": 10})
except ncp.Ended as e: print("   s delayed:", e.code)
verdict = a.recover(client(Wire(ncp.Owner(CONTRACT, core))))               # a good nonce: takes the ticks
print("   recovery -> verdict", verdict.value)
o3 = ncp.Owner(CONTRACT, core, nonce=fixed); print("   replayed open on C3 ->", outcome(o3.handle(w1.sent[0])))
print("   delayed s on C1 ->", outcome(o1.handle(w1.sent[-1])), "| tick", core.tick,
      "=> the verdict NO was FALSE" if core.tick == 1 else "")

print("R4. the owner restarts with tick T and ANOTHER state; recover() compares only the tick")
world = World(); core = ncp.Lockstep(world, ["step"])
w1 = Wire(ncp.Owner(CONTRACT, core)); a = ncp.LockstepClient(client(w1)); a.step("step", {"dx": 1})
w1.hold = True
try: a.step("step", {"dx": 10})
except ncp.Ended as e: print("   s (tick 2) uncertain:", e.code, "| the client knows tick", a.tick, "state", a.state)
restored = ncp.Lockstep(World(position=500), ["step"], tick=1, state="p500")   # another history at tick 1
verdict = a.recover(client(Wire(ncp.Owner(CONTRACT, restored))))
print("   recover -> verdict", verdict.value, "| the client now holds state", a.state, "(it knew p1 at tick 1; no error raised)")

print("R5. an open that takes the ticks and then opens no session (a wrapper refuses after Lockstep.open)")
class Limit:
    """An application wrapper around Lockstep that refuses after the inner open ran."""
    def __init__(self, inner): self.inner, self.refuse = inner, False
    def open(self, info):
        granted = self.inner.open(info)
        if self.refuse: raise ncp.Refused("too many sessions")
        return granted
    def validate(self, r): self.inner.validate(r)
    def execute(self, r): return self.inner.execute(r)
world = World(); core = ncp.Lockstep(world, ["step"]); limit = Limit(core)
b = ncp.LockstepClient(client(Wire(ncp.Owner(CONTRACT, limit)))); b.step("step", {"dx": 1})
limit.refuse = True
try: client(Wire(ncp.Owner(CONTRACT, limit))).open()
except ncp.Rejected as r: print("   second open -> rejected", r.code, "| holder is still the live opening:", core.holder == b.client.nonce)
try: b.step("step", {"dx": 1}); print("   live client stepped")
except ncp.Declined as d: print("   live client's next step -> declined:", d.detail[:40], "| a REJECTED open took the ticks")
