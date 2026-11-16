"""Probe: a replayed copy of an old `open` (feature ncp.lockstep) takes the ticks from the live holder.
Read-only use of the SDK copy in the scratch directory."""
import sys
sys.path.insert(0, sys.argv[1])
sys.dont_write_bytecode = True
import ncp

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}'
)
KEY = bytes(range(32))  # authenticated frames: replay is still possible (spec 13.2)

class World:
    def __init__(self): self.position = 0
    def validate(self, request): pass
    def execute(self, request):
        self.position += request.body.get("dx", 0)
        return {"position": self.position}
    def state(self): return f"p{self.position}"

class Wire:
    """A lossless in-memory channel that records the frames the client sends."""
    lossy = False
    local = True
    def __init__(self, owner):
        self.owner, self.sent, self.replies = owner, [], []
    def send(self, frame):
        self.sent.append(bytes(frame))
        self.replies.append(self.owner.handle(frame))
    def receive(self, bound, timeout):
        return self.replies.pop(0)
    def close(self): pass

lockstep = ncp.Lockstep(World(), ["step"])          # one clock for every session of the owner

# Session A: opens with the feature and steps once. An observer on the path keeps the open frame.
wire_a = Wire(ncp.Owner(CONTRACT, lockstep, key=KEY))
a = ncp.LockstepClient(ncp.Client(wire_a, CONTRACT, features={"ncp.lockstep": {}}, key=KEY))
a.step("step", {"dx": 1})
old_open = wire_a.sent[0]
print("A stepped to tick", lockstep.tick, "holder is A:", lockstep.holder == a.client.state.session)

# Session B: the live client now (for example after A's connection was lost). It takes over.
wire_b = Wire(ncp.Owner(CONTRACT, lockstep, key=KEY))
b = ncp.LockstepClient(ncp.Client(wire_b, CONTRACT, features={"ncp.lockstep": {}}, key=KEY))
b.step("step", {"dx": 1})
print("B stepped to tick", lockstep.tick, "holder is B:", lockstep.holder == b.client.state.session)

# A party on the path replays A's old open frame on a new connection (a fresh Owner, as a server makes).
replayed = ncp.Owner(CONTRACT, lockstep, key=KEY)
response = ncp.decode(replayed.handle(old_open), ncp.DEFAULT_BOUND, key=KEY).message
print("replayed old open ->", response["outcome"], "| holder is now A's old session:",
      lockstep.holder == a.client.state.session)

# The live client B is fenced: its next step is declined, although nobody else steps.
try:
    b.step("step", {"dx": 1})
    print("B stepped (unexpected)")
except ncp.Declined as declined:
    print("B's next step -> declined:", declined.detail)
print("tick stays", lockstep.tick)
