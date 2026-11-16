"""Probe: no third party. The client recovers with a new connection but the SAME session identifier
(both SDKs accept a caller-chosen identifier: ncp.Client(..., session=...)). The fence of profile
rule 3.3 then excludes nothing, because the holder is the session name. Usage: probe.py PYTHON_SDK_DIR"""
import sys
sys.path.insert(0, sys.argv[1]); sys.dont_write_bytecode = True
import ncp

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}'
)
SESSION = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b"

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

world = World(); core = ncp.Lockstep(world, ["step"])
def client(wire): return ncp.Client(wire, CONTRACT, features={"ncp.lockstep": {}}, session=SESSION, timeout=0.01)

owner_c1 = ncp.Owner(CONTRACT, core); c1 = Wire(owner_c1); a = ncp.LockstepClient(client(c1))
a.step("step", {"dx": 1})
c1.hold = True
try: a.step("step", {"dx": 10})
except ncp.Ended as ended: print("s is delayed on C1; the call ended:", ended.code)
verdict = a.recover(client(Wire(ncp.Owner(CONTRACT, core))))     # C2, same session identifier
print("recovery on C2 with the same session identifier -> verdict", verdict.value)
reply = ncp.decode(owner_c1.handle(c1.sent[-1]), ncp.DEFAULT_BOUND).message
print("delayed s on C1 ->", reply["outcome"], "| owner tick", core.tick, "| position", world.position)
