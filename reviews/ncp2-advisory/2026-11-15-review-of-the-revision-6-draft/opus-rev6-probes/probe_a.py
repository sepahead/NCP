"""Probe (a): a declined body with large or non-JSON `ncp.` members, Python SDK, byte stream."""
import socket, sys, threading
sys.path.insert(0, sys.argv[1] + "/python")
import ncp
from ncp import frame as F

C = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"a","version":"1","operations":{"op":{}},"streams":{}}')

class App:
    def __init__(self, members): self.members = members
    def validate(self, request): raise ncp.Declined("no", body=self.members)
    def execute(self, request): return {}

def run(label, members, bound=ncp.DEFAULT_BOUND):
    a, b = socket.socketpair()
    owner = ncp.Owner(C, App(members), observer=ncp.LogObserver() if False else None)
    how = []
    t = threading.Thread(target=lambda: how.append(ncp.serve(owner, ncp.StreamChannel.from_socket(a))))
    t.start()
    client = ncp.Client(ncp.StreamChannel.from_socket(b), C, bound=bound, timeout=5)
    client.open()
    try:
        client.call("op", {})
        print(f"{label}: ok?!")
    except ncp.Declined as d:
        print(f"{label}: Declined code={d.code} body-keys={sorted(d.body)}")
    except ncp.Ended as e:
        print(f"{label}: Ended code={e.code} executed={e.executed.value} detail={e.detail[:60]!r}")
    except Exception as e:
        print(f"{label}: {type(e).__name__}: {str(e)[:80]}")
    t.join(5)
    print(f"   owner serve() ended as {how}, owner admitted seq high={owner.state.high}")

run("small ncp member (control)", {"ncp.x": 1})
run("ncp member of 2 MB (> 1 MiB JSON)", {"ncp.big": "a" * 2_000_000})
run("ncp member that JSON cannot carry (a set)", {"ncp.set": {1, 2}})
run("ncp member with an integer above 2^53-1", {"ncp.n": 2**60})
run("ncp member of 100 kB, session bound 65,536", {"ncp.mid": "a" * 100_000}, bound=65_536)
run("a non-string member name", {1: 2})
