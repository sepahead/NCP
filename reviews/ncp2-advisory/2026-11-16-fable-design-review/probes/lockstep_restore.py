"""Probe L1: a step that ran before a restore to an earlier saved clock gets the verdict NO.

Usage: python3 -I -B lockstep_restore.py SDK_PYTHON_DIR
The scenario follows profile rule 5.7 exactly: the owner restores T, S, R from one saved clock
that belongs to the application state that it restored. Nothing here is a defect of the SDK
against the profile; the probe shows what the profile's verdict means.
"""
import sys

sys.path.insert(0, sys.argv[1])
import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}'
)


class World:
    def __init__(self, position=0):
        self.position, self.effects = position, []

    def validate(self, request):
        pass

    def execute(self, request):
        self.position += request.body["dx"]
        self.effects.append(("actuator moved", request.body["dx"]))  # an effect outside the state
        return {"position": self.position}

    def state(self):
        return f"p{self.position}"


class Channel:
    lossy, local = False, True

    def __init__(self, owner):
        self.owner, self.queue, self.lose_responses = owner, [], False

    def send(self, frame):
        response = self.owner.handle(frame)
        if self.lose_responses:
            raise ConnectionResetError("the response is lost")
        self.queue.append(response)

    def receive(self, bound, timeout):
        if not self.queue:
            raise TimeoutError
        return self.queue.pop(0)

    def close(self):
        pass


def client(lockstep):
    return ncp.Client(Channel(ncp.Owner(CONTRACT, lockstep)), CONTRACT, features={"ncp.lockstep": {}})


world = World()
lockstep = ncp.Lockstep(world, ["step"])
stepper = ncp.LockstepClient(client(lockstep))
stepper.step("step", {"dx": 2})
saved = (world.position, lockstep.clock())  # the application saves its state with the clock
print("1. checkpoint saved at", saved[1])

stepper.client.channel.lose_responses = True
try:
    stepper.step("step", {"dx": 1})
except ncp.Ended as ended:
    print("2. step for tick 2:", ended.code, "executed:", ended.executed, "| owner tick:", lockstep.tick,
          "| effects:", world.effects)

# The owner process restarts and restores the checkpoint (rule 5.7).
position, clock = saved
restored_world = World(position)
restored = ncp.Lockstep(restored_world, ["step"], tick=clock["tick"], state=clock["state"],
                        request=clock["request"], term=clock["term"])
verdict = stepper.recover(client(restored))
print("3. after the restore, recover() ->", verdict, "| the owner executed that step once before the restart: True")
print("RESULT: the verdict is", verdict, "for a step that executed; the profile defines this as",
      '"not in the current state" (section 7, Restarts).')
