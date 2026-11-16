"""Probe: a strict request schema (additionalProperties false) declines every lockstep step,
because the profile's reserved body member ncp.tick is not exempt from the schema."""
import sys
sys.path.insert(0, sys.argv[1]); sys.dont_write_bytecode = True
import ncp

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{"ncp.schema":'
    b'{"request":{"type":"object","required":["dx"],"properties":{"dx":{"type":"integer"}},'
    b'"additionalProperties":false}}}},"streams":{}}'
)
class World:
    position = 0
    def validate(self, request): pass
    def execute(self, request):
        self.position += request.body["dx"]; return {"position": self.position}
    def state(self): return f"p{self.position}"
class Wire:
    lossy = False; local = True
    def __init__(self, owner): self.owner, self.replies = owner, []
    def send(self, frame): self.replies.append(self.owner.handle(frame))
    def receive(self, bound, timeout): return self.replies.pop(0)
    def close(self): pass

lockstep = ncp.Lockstep(World(), ["step"])
stepper = ncp.LockstepClient(ncp.Client(Wire(ncp.Owner(CONTRACT, lockstep)), CONTRACT, features={"ncp.lockstep": {}}))
try:
    stepper.step("step", {"dx": 1})
    print("step ran")
except ncp.Declined as declined:
    print("declined:", declined.code, "|", declined.detail)
print("tick:", lockstep.tick)
