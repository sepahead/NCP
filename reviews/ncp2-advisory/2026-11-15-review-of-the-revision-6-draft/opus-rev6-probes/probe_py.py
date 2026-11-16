"""Probes (b) to (g), and the Python side of lead L-A, against the Python SDK (scratch copy)."""
import sys, threading, time
sys.path.insert(0, sys.argv[1] + "/python")
import ncp
from ncp import lockstep as LS
from ncp import frame as F

C = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"w","version":"1","operations":{"step":{},"move":{}},"streams":{}}')

class World:
    def __init__(self, position=0, sleep=0.0): self.position, self.sleep = position, sleep
    def validate(self, request): pass
    def execute(self, request):
        time.sleep(self.sleep); self.position += request.body["dx"]; return {"position": self.position}
    def state(self): return f"p{self.position}"

class Mem:
    """A lossless in-memory channel; `run_then_cut` runs the next request and loses its response."""
    lossy, local = False, True
    def __init__(self, owner): self.owner, self.inbox, self.run_then_cut, self.cut = owner, [], False, False
    def send(self, frame):
        if self.cut: raise ConnectionResetError("broken")
        response = self.owner.handle(frame)
        if self.run_then_cut: self.cut = True; return
        self.inbox.append(response)
    def receive(self, bound, timeout):
        if self.cut: raise ConnectionResetError("closed")
        if not self.inbox: raise TimeoutError
        return self.inbox.pop(0)
    def close(self): pass

def session(ls, session_id=None):
    return ncp.Client(Mem(ncp.Owner(C, ls)), C, features={"ncp.lockstep": {}}, session=session_id)

print("== (b) Python: does open wait for an executing step?")
ls = LS.Lockstep(World(sleep=0.6), ["step"])
stepper = ncp.LockstepClient(session(ls))
t = threading.Thread(target=lambda: stepper.step("step", {"dx": 1})); t.start(); time.sleep(0.1)
start = time.monotonic(); report = ls.open(ncp.OpenInfo("s", C, None, {"ncp.lockstep": {}}, "n9"))["ncp.lockstep"]
print(f"   open returned after {1000*(time.monotonic()-start):.0f} ms with tick {report['tick']}"); t.join()

print("== (c): at the largest term, a declined take names the same term")
ls = LS.Lockstep(World(), ["step"], term=LS.MAX_TERM)
c = session(ls); c.open()
try: c.call(LS.TAKE, {"term": LS.MAX_TERM})
except ncp.Declined as d: print(f"   take with term {LS.MAX_TERM}: declined, body ncp.lockstep = {d.body.get('ncp.lockstep')}; no other take ran (holder {ls.holder})")

print("== (d): an owner that reports no term (profile revision 3)")
class OldOwner:
    def __init__(self): self.inner = World()
    def open(self, info): return {"ncp.lockstep": {"tick": 0, "state": None, "request": None}}
    def validate(self, r): pass
    def execute(self, r): return {}
c = ncp.Client(Mem(ncp.Owner(C, OldOwner())), C, features={"ncp.lockstep": {}})
try: ncp.LockstepClient(c)
except Exception as e: print(f"   LockstepClient -> {type(e).__name__}: {e}; client.ended={c.ended} (session left open)")

print("== (e) Python: after a recovery without a verdict")
ls = LS.Lockstep(World(), ["step"])
stepper = ncp.LockstepClient(session(ls)); stepper.step("step", {"dx": 2})
stepper.client.channel.run_then_cut = True
try: stepper.step("step", {"dx": 1})
except ncp.Ended as e: print(f"   step 2: executed={e.executed.value}; owner tick {ls.tick}")
other = ncp.LockstepClient(session(ls)); other.step("step", {"dx": 100})
new = session(ls)
try: stepper.recover(new)
except Exception as e: print(f"   recover -> {type(e).__name__} (has .executed: {hasattr(e, 'executed')}); holder is the new opening: {ls.holder == new.nonce}")
print(f"   stepper.client is the old dead client: {stepper.client is not new and stepper.client.ended}; uncertain={stepper.uncertain}")
try: stepper.step("step", {"dx": 1})
except Exception as e: print(f"   stepper.step -> {type(e).__name__}: {e}")
again = ncp.LockstepClient(new)  # what a caller can do: wrap the new client
print(f"   LockstepClient(new): tick {again.tick}, term now {ls.term} (one more take, and a declined one)")

print("== L-A Python: ok step response without the tick")
ls = LS.Lockstep(World(), ["step"])
stepper = ncp.LockstepClient(session(ls))
try: stepper.step("move", {"dx": 7})
except Exception as e: print(f"   step('move') -> {type(e).__name__}: {e} (has .executed: {hasattr(e, 'executed')}); application position {ls.handler.position}")

print("== (f): restart at tick 0 to another world, no clock restored")
ls = LS.Lockstep(World(0), ["step"])
stepper = ncp.LockstepClient(session(ls)); print(f"   the client knows {stepper.tick, stepper.state, stepper.request}")
stepper.client.channel.run_then_cut = True
try: stepper.step("step", {"dx": 2})
except ncp.Ended as e: print(f"   step 1: executed={e.executed.value}; old world position {ls.handler.position}")
restarted = LS.Lockstep(World(500), ["step"])  # a restart without a saved clock, another world
verdict = stepper.recover(session(restarted))
print(f"   recover -> {verdict.value!r} (did not run); new world position {restarted.handler.position}; profile sec. 7 says a restart"
      " to the same tick with another state gives no verdict")

print("== (g) Python: ticks at and above 2^53 - 1")
for tick in (2**53 - 2, 2**60):
    ls = LS.Lockstep(World(), ["step"], tick=tick, state="s")
    c = session(ls)
    try:
        st = ncp.LockstepClient(c); st.step("step", {"dx": 1}); print(f"   tick {tick}: step 1 ok (tick {ls.tick})")
        st.step("step", {"dx": 1})
    except Exception as e: print(f"   tick {tick}: {type(e).__name__}: {str(e)[:90]}")
