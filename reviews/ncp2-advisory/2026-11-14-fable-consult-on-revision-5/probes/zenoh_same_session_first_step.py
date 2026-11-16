"""Probe R1 (revision 5): the Zenoh server, a recovery that uses the SAME session identifier, and
an uncertain step that is the first request of its session.

The recovery `open` has the same session identifier and the same body as the first `open`, so it
is the same frame. The Zenoh server holds the session (one worker for each session identifier),
so the owner answers with its KEPT `open` response (rule 7.3.5): the same opening, the same nonce,
no takeover. LockstepClient.recover reads tick T and says NO. The delayed step then arrives and
runs: it is the next request of the opening that still holds the ticks.

Usage: probe.py PYTHON_SDK_DIR ZENOH_BINDING_PYTHON_DIR STUB_DIR [new-session]
The real ncp_zenoh.Server routes every frame; only the Zenoh transport is a stub.
"""
import sys, queue, time
sys.dont_write_bytecode = True
sys.path[:0] = [sys.argv[1], sys.argv[2], sys.argv[3]]
import ncp, ncp_zenoh

NEW = len(sys.argv) > 4 and sys.argv[4] == "new-session"
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

class Payload:
    def __init__(self, data): self.data = data
    def to_bytes(self): return self.data
class Query:
    def __init__(self, frame, sink): self.payload, self.sink = Payload(frame), sink
    def reply(self, key, response): self.sink.put(response)
    def drop(self): pass
class FakeZenoh:
    def declare_queryable(self, key, callback, complete=True):
        self.callback = callback
        class Q:
            def undeclare(self): pass
        return Q()

class Channel:
    """A client channel that hands each frame to the real server's _on_query, or holds it back."""
    lossy = True; local = False
    def __init__(self, server): self.server, self.replies, self.sent, self.hold = server, queue.SimpleQueue(), [], False
    def send(self, frame):
        self.sent.append(bytes(frame))
        if not self.hold: self.server._on_query(Query(bytes(frame), self.replies))
    def receive(self, bound, timeout):
        try: return self.replies.get(timeout=timeout)
        except queue.Empty: raise TimeoutError("no reply") from None
    def close(self): pass

world = World(); core = ncp.Lockstep(world, ["step"])
server = ncp_zenoh.Server(FakeZenoh(), "world", lambda: ncp.Owner(CONTRACT, core)).start()
def client(channel, session):
    return ncp.Client(channel, CONTRACT, features={"ncp.lockstep": {}}, session=session, timeout=0.05, retries=1)

c1 = Channel(server); a = ncp.LockstepClient(client(c1, SESSION))
first_nonce = a.client.nonce
c1.hold = True                                   # the first step of the session is delayed
try: a.step("step", {"dx": 10})
except ncp.Ended as ended: print("1. s (seq 1) is delayed; the call ended:", ended.code, "executed:", ended.executed.value)
s = c1.sent[-1]

c2 = Channel(server)
recovery = client(c2, None if NEW else SESSION)
verdict = a.recover(recovery)
print("2. recovery", "with a new session identifier" if NEW else "with the same session identifier",
      "-> verdict", verdict.value, "| same nonce as the first opening:", recovery.nonce == first_nonce,
      "| same open frame:", c2.sent[0] == c1.sent[0], "| sessions held:", server.sessions)

sink = queue.SimpleQueue(); server._on_query(Query(s, sink))
reply = ncp.decode(sink.get(timeout=2), ncp.DEFAULT_BOUND).message
print("3. delayed s arrives ->", reply["outcome"], reply["code"], reply["body"].get("detail", "")[:60],
      "| owner tick", core.tick, "| position", world.position)
false = verdict is ncp.Executed.NO and reply["outcome"] == "ok"
print("RESULT:", "the verdict NO was false: s ran" if false else "the verdict NO stayed true")
server.stop(grace=0.0)
