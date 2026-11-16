"""Probe R1: what a rounds member learns after its response is lost.

Usage: python3 -I -B rounds_lost_response.py SDK_PYTHON_DIR
"""
import sys
import threading

sys.path.insert(0, sys.argv[1])
import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"act":{}},"streams":{}}'
)
applied = []


def step(number, inputs):
    applied.append((number, [agent for agent, _ in inputs]))
    return {agent: {"seen": number} for agent, _ in inputs}


rounds = ncp.Rounds(CONTRACT, "act", ["a", "b"], step, deadline=0.3)


class Channel:
    lossy, local = False, True

    def __init__(self, owner):
        self.owner, self.queue, self.lose = owner, [], False

    def send(self, frame):
        response = self.owner.handle(frame)
        if self.lose:
            self.owner.handler.close("lost")
            raise ConnectionResetError("lost")
        self.queue.append(response)

    def receive(self, bound, timeout):
        if not self.queue:
            raise TimeoutError
        return self.queue.pop(0)

    def close(self):
        pass


def session():
    return ncp.Client(Channel(rounds.owner()), CONTRACT)


a, b = session(), session()
a.open(); b.open()
results = {}


def call(name, client, number):
    try:
        results[name] = client.call("act", {"ncp.round": {"agent": name, "round": number}})
    except ncp.CallError as error:
        results[name] = error


# Round 1: the response to agent a is lost after the round applied its request.
a.channel.lose = True
threads = [threading.Thread(target=call, args=(n, c, 1)) for n, c in (("a", a), ("b", b))]
[t.start() for t in threads]; [t.join() for t in threads]
print("1. round 1 applied:", applied, "| a:", type(results["a"]).__name__, getattr(results["a"], "code", ""),
      "executed:", getattr(results["a"], "executed", ""))

# Agent a recovers in a new session. What can it learn?
a2 = session(); a2.open()
print("2. a's new open response features:", a2.enabled, "(no report of the round or of a's last request)")
for number in (1, 2):
    done = {}

    def attempt(n=number):
        try:
            done["r"] = a2.call("act", {"ncp.round": {"agent": "a", "round": n}})
        except ncp.CallError as error:
            done["r"] = error

    t = threading.Thread(target=attempt); t.start()
    if number == 2:  # b plays round 2 so that it can close
        tb = threading.Thread(target=call, args=("b", b, 2)); tb.start(); tb.join()
    t.join()
    r = done["r"]
    if isinstance(r, ncp.CallError):
        print(f"3. a sends round {number} again ->", type(r).__name__, r.code, "| detail:", r.detail,
              "| body members:", sorted(r.body) if isinstance(r.body, dict) else r.body)
    else:
        print(f"3. a sends round {number} -> ok", {k: v for k, v in r.body.items() if k != 'ncp.round_record'})
print("RESULT: a never receives its result of round 1; it learns that round 1 closed only from the free",
      "text of `detail`, and that its request was applied only by inference (round 2 is accepted).")
