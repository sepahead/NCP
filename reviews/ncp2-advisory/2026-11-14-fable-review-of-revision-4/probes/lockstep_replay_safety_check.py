"""Independent check of the coordinator's scenario, and of fix (a): the holder is the opening.

Scenario (byte-stream binding: one owner object for each connection, one shared Lockstep):
  1. A opens on C1 and steps to tick 1. A's next step s is delayed on C1; A's call ends, uncertain.
  2. A recovers on C2: the open response names tick 1, so the verdict is NO ("never will").
  3. A copy of A's first open frame is replayed on C3 (a fresh owner): a new opening, same session name.
  4. The delayed s arrives on C1, whose owner still holds A's first opening.
Usage: probe.py PYTHON_SDK_DIR [fixed]
"""
import sys
sys.path.insert(0, sys.argv[1]); sys.dont_write_bytecode = True
import ncp

FIXED = len(sys.argv) > 2 and sys.argv[2] == "fixed"
CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}'
)
KEY = bytes(range(32))

class World:
    def __init__(self): self.position, self.ran = 0, []
    def validate(self, request): pass
    def execute(self, request):
        self.position += request.body["dx"]; self.ran.append(request.identity[:8])
        return {"position": self.position}
    def state(self): return f"p{self.position}"

class ByOpening:
    """Fix (a), as a wrapper for this probe only: the holder is the opening (this handler object,
    one for each owner and so for each accepted open), not the session name."""
    def __init__(self, core): self.core = core
    def open(self, info):
        granted = self.core.open(info)
        if "ncp.lockstep" in info.features:
            self.core.opening = self
        return granted
    def validate(self, request):
        if request.op in self.core.ops and getattr(self.core, "opening", None) is not self:
            raise ncp.Declined("this opening does not hold the ticks")
        self.core.validate(request)
    def execute(self, request): return self.core.execute(request)

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

world = World(); core = ncp.Lockstep(world, ["step"])
def owner(): return ncp.Owner(CONTRACT, ByOpening(core) if FIXED else core, key=KEY)
def client(wire): return ncp.Client(wire, CONTRACT, features={"ncp.lockstep": {}}, key=KEY, timeout=0.01)

owner_c1 = owner(); c1 = Wire(owner_c1); a = ncp.LockstepClient(client(c1))
a.step("step", {"dx": 1})
c1.hold = True
try: a.step("step", {"dx": 10})
except ncp.Ended as ended: print("1. s is delayed; A's call ended:", ended.code, "executed:", ended.executed.value)
s = c1.sent[-1]

verdict = a.recover(client(Wire(owner())))
print("2. recovery on C2 -> verdict", verdict.value, "| owner tick", core.tick)

reply = ncp.decode(owner().handle(c1.sent[0]), ncp.DEFAULT_BOUND, key=KEY).message
print("3. replayed first open of A on C3 ->", reply["outcome"], "| nonce differs from C1's:",
      reply["body"]["nonce"] != owner_c1.state.nonce)

reply = ncp.decode(owner_c1.handle(s), ncp.DEFAULT_BOUND, key=KEY).message
print("4. delayed s on C1 ->", reply["outcome"], reply["code"], reply["body"].get("detail", ""),
      "| owner tick", core.tick, "| position", world.position)
violated = verdict is ncp.Executed.NO and reply["outcome"] == "ok"
print("RESULT:", "the verdict NO was false: s ran" if violated else "the verdict NO stayed true")
