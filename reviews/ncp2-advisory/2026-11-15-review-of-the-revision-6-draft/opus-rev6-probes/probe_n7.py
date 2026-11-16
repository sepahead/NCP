"""N7: Lockstep.validate takes the lock that only execute releases. A handler that wraps the
Lockstep and declines after the Lockstep's validate succeeded leaves the lock held: every later
take and step of every session waits forever."""
import sys, threading
sys.path.insert(0, sys.argv[1] + "/python")
import ncp
from ncp import lockstep as LS
C = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"w","version":"1","operations":{"step":{}},"streams":{}}')
class World:
    position = 0
    def validate(self, r): pass
    def execute(self, r): self.position += r.body["dx"]; return {"position": self.position}
    def state(self): return f"p{self.position}"
class Quota:  # an application policy layered over the profile: at most one step
    def __init__(self, inner): self.inner, self.steps = inner, 0
    def open(self, info): return self.inner.open(info)
    def validate(self, r):
        self.inner.validate(r)
        if r.op == "step" and self.steps >= 1: raise ncp.Declined("quota: one step")
    def execute(self, r):
        if r.op == "step": self.steps += 1
        return self.inner.execute(r)
class Mem:
    lossy, local = False, True
    def __init__(self, owner): self.owner, self.inbox = owner, []
    def send(self, f): self.inbox.append(self.owner.handle(f))
    def receive(self, b, t): return self.inbox.pop(0)
    def close(self): pass
ls = LS.Lockstep(World(), ["step"]); quota = Quota(ls)
st = ncp.LockstepClient(ncp.Client(Mem(ncp.Owner(C, quota)), C, features={"ncp.lockstep": {}}))
st.step("step", {"dx": 1})
try: st.step("step", {"dx": 1})
except ncp.Declined as d: print(f"second step declined by the wrapper: {d.detail}")
done = []
t = threading.Thread(target=lambda: done.append(ncp.LockstepClient(ncp.Client(Mem(ncp.Owner(C, quota)), C, features={"ncp.lockstep": {}}))), daemon=True)
t.start(); t.join(2)
print(f"a take in another session, 2 s later: {'finished' if done else 'still waiting (the lock is held)'}")
