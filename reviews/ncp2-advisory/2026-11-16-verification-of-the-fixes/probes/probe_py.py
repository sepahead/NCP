"""Probes of the revision 6 fixes, Python SDK (advisory; certifies nothing).

Usage: python3 -I -B probe_py.py SNAP   (SNAP = a scratch copy of commit 904f87c)
"""

from __future__ import annotations

import os
import sys
import traceback

SNAP = sys.argv[1]
sys.path.insert(0, os.path.join(SNAP, "python"))

import ncp  # noqa: E402
from ncp import frame as F  # noqa: E402
from ncp import lockstep as LS  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{},"look":{}},"streams":{}}'
)


class Lossless:
    lossy = False
    local = True

    def __init__(self, owner) -> None:
        self.owner, self.queue, self.frames = owner, [], []

    def send(self, frame: bytes) -> None:
        self.frames.append(bytes(frame))
        self.queue.append(self.owner.handle(frame))

    def receive(self, bound: int, timeout):
        if not self.queue:
            raise TimeoutError
        return self.queue.pop(0)

    def close(self) -> None:
        pass


class World:
    def __init__(self) -> None:
        self.position = 0

    def validate(self, request):
        pass

    def execute(self, request):
        self.position += request.body.get("dx", 0)
        return {"position": self.position}

    def state(self):
        return f"p{self.position}"


def session(lockstep) -> ncp.Client:
    return ncp.Client(Lossless(ncp.Owner(CONTRACT, lockstep)), CONTRACT, features={"ncp.lockstep": {}})


def show(label: str, fn) -> None:
    try:
        value = fn()
        print(f"{label}: returned {value!r}")
    except BaseException as error:  # noqa: BLE001
        extra = ""
        if isinstance(error, ncp.Ended):
            extra = f" code={error.code} executed={error.executed}"
        print(f"{label}: raised {type(error).__name__}: {error}{extra}")


print("== P1a: the ok response of a take lacks 'state' (owner broke rule 5.3)")


class NoState(LS.Lockstep):
    def execute(self, request):
        result = super().execute(request)
        if request.op == LS.TAKE:
            result = {k: v for k, v in result.items() if k != "state"}
        return result


ls = NoState(World(), ["step"])
client = session(ls)
show("LockstepClient(...)", lambda: LS.LockstepClient(client))
print("  owner: holder is this opening:", ls.holder == client.nonce, "term", ls.term, "; client.ended:", client.ended)

print("== P1b: the ok response of a take lacks 'request'")


class NoRequest(LS.Lockstep):
    def execute(self, request):
        result = super().execute(request)
        if request.op == LS.TAKE:
            result = {k: v for k, v in result.items() if k != "request"}
        return result


ls = NoRequest(World(), ["step"])
client = session(ls)
show("LockstepClient(...)", lambda: LS.LockstepClient(client))
print("  owner: holder is this opening:", ls.holder == client.nonce, "; client.ended:", client.ended)

print("== P1c: the ok response of a step has ncp.tick without 'state'")


class TickNoState(LS.Lockstep):
    def execute(self, request):
        result = super().execute(request)
        if request.op == "step":
            tick = {k: v for k, v in result["ncp.tick"].items() if k != "state"}
            result = {**result, "ncp.tick": tick}
        return result


ls = TickNoState(World(), ["step"])
client = session(ls)
stepper = LS.LockstepClient(client)
show("stepper.step(...)", lambda: stepper.step("step", {"dx": 2}))
print("  owner tick", ls.tick, "position", ls.handler.position, "; client knows tick", stepper.tick,
      "state", stepper.state, "; uncertain", stepper.uncertain, "; client.ended", client.ended)
show("  next stepper.step(...)", lambda: stepper.step("step", {"dx": 1}))

print("== P2: LockstepClient.take() after three declined takes names a stale term")


class Moving(LS.Lockstep):
    """Another client takes the ticks before each take of this client, three times."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.bumps = 0
        self.named: list[int] = []

    def validate(self, request):
        if request.op == LS.TAKE:
            self.named.append(request.body.get("term"))
            if self.bumps:
                self.bumps -= 1
                with self._clock:
                    self.term += 1  # another take ran
        super().validate(request)


ls = Moving(World(), ["step"])
client = session(ls)
stepper = LS.LockstepClient(client)  # term 1
ls.bumps = 3
show("stepper.take() (3 moving terms)", stepper.take)
print("  owner term", ls.term, "; stepper.term", stepper.term, "; terms named so far", ls.named)
ls.named.clear()
show("stepper.take() again", stepper.take)
print("  terms named by the second take():", ls.named, "; owner term now", ls.term,
      "; told last before it:", "4 (the body of the last decline)")

print("== P3: recover after a malformed take response keeps uncertain (can retry)")


class Breaking(Lossless):
    def __init__(self, owner):
        super().__init__(owner)
        self.broken = False

    def send(self, frame):
        if self.broken:
            self.owner.handle(frame)
            raise ConnectionResetError("broke")
        super().send(frame)


good = LS.Lockstep(World(), ["step"])
channel = Breaking(ncp.Owner(CONTRACT, good))
stepper = LS.LockstepClient(ncp.Client(channel, CONTRACT, features={"ncp.lockstep": {}}))
stepper.step("step", {"dx": 1})
channel.broken = True
show("step (lost response)", lambda: stepper.step("step", {"dx": 1}))
print("  uncertain", stepper.uncertain)


class Skipping(LS.Lockstep):
    pass


# A take response with a wrong term from a second owner object that shares the clock.
class WrongTerm:
    def __init__(self, inner):
        self.inner = inner

    def open(self, info):
        return self.inner.open(info)

    def validate(self, request):
        return self.inner.validate(request)

    def execute(self, request):
        result = self.inner.execute(request)
        if request.op == LS.TAKE:
            result = {**result, "term": result["term"] + 5}
        return result


bad = ncp.Client(Lossless(ncp.Owner(CONTRACT, WrongTerm(good))), CONTRACT, features={"ncp.lockstep": {}})
show("recover(bad owner)", lambda: stepper.recover(bad))
print("  uncertain", stepper.uncertain, "; bad.ended", bad.ended)
show("recover(good owner)", lambda: stepper.recover(session(good)))
print("  tick", stepper.tick, "state", stepper.state, "uncertain", stepper.uncertain)

print("== P12: an application open grants an Array in a feature parameter")


class ArrayGrant:
    def __init__(self):
        self.closed = []

    def open(self, info):
        return {"arr": {"a": F.Array("u8", (4,), b"abcd")}}

    def validate(self, request):
        pass

    def execute(self, request):
        return {}

    def close(self, reason):
        self.closed.append(reason)


app = ArrayGrant()
owner = ncp.Owner(CONTRACT, app)
c = ncp.Client(Lossless(owner), CONTRACT, features={"arr": {}})
show("open with an Array parameter", c.open)
print("  app.closed", app.closed)

print("== P13: Declined body with an Array member (Python owner)")


class ArrayDecline:
    def validate(self, request):
        raise ncp.Declined("no", body={"ncp.x": F.Array("u8", (4,), b"abcd")})

    def execute(self, request):
        return {}


c = ncp.Client(Lossless(ncp.Owner(CONTRACT, ArrayDecline())), CONTRACT)
c.open()
try:
    c.call("step", {})
except ncp.Declined as d:
    print("  declined body:", d.body)
except BaseException as e:  # noqa: BLE001
    print("  raised", type(e).__name__, e)
show("  ping after", lambda: c.ping().body)
