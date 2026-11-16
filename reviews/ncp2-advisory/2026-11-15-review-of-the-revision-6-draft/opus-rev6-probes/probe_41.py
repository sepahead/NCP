"""Rule 4.1: a take names the term that the owner told the client LAST in this session."""
import sys
sys.path.insert(0, sys.argv[1] + "/python")
import ncp
from ncp import lockstep as LS
from ncp import frame as F

C = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"w","version":"1","operations":{"step":{}},"streams":{}}')
class World:
    position = 0
    def validate(self, r): pass
    def execute(self, r): self.position += r.body["dx"]; return {"position": self.position}
    def state(self): return f"p{self.position}"
class Mem:
    lossy, local = False, True
    def __init__(self, owner): self.owner, self.inbox, self.sent = owner, [], []
    def send(self, frame):
        m = F.decode(frame, F.MAX_BOUND).message
        if m["op"] == LS.TAKE: self.sent.append(m["body"]["term"])
        self.inbox.append(self.owner.handle(frame))
    def receive(self, bound, timeout): return self.inbox.pop(0)
    def close(self): pass

ls = LS.Lockstep(World(), ["step"])
mk = lambda: ncp.Client(Mem(ncp.Owner(C, ls)), C, features={"ncp.lockstep": {}})
stepper = ncp.LockstepClient(mk())                 # term 0 -> 1
other = ncp.LockstepClient(mk())                   # term 1 -> 2
try: stepper.step("step", {"dx": 1})
except ncp.Declined as d: told = d.body["ncp.lockstep"]["term"]; print(f"step declined; the owner told this session term {told}")
tick, state, request = LS.take(stepper.client)       # rule 6.4: take them again
print(f"terms named by the takes of this session: {stepper.client.channel.sent} (the first take named 0;"
      f" rule 4.1 requires the term told last, {told}); owner term now {ls.term}")
