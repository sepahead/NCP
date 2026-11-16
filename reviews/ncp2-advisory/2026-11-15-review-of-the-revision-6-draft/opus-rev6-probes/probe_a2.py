"""Class (a), open path: feature parameters from the handler's open are encoded without the
handshake bound of 65,536 bytes that the client applies to the open response (rule 7.1.3)."""
import socket, sys, threading
sys.path.insert(0, sys.argv[1] + "/python")
import ncp
C = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"a","version":"1","operations":{"op":{}},"streams":{}}')
class App:
    def open(self, info): return {"big": {"x": "a" * 70_000}}
    def validate(self, r): pass
    def execute(self, r): return {}
a, b = socket.socketpair()
owner = ncp.Owner(C, App())
t = threading.Thread(target=lambda: ncp.serve(owner, ncp.StreamChannel.from_socket(a)), daemon=True); t.start()
client = ncp.Client(ncp.StreamChannel.from_socket(b), C, features={"big": {}}, timeout=5)
try: client.open(); print("opened?!")
except ncp.Ended as e: print(f"open -> Ended {e.code}, executed={e.executed.value}: {e.detail}")
t.join(2)
print(f"owner holds session: {owner.session is not None}; owner kept open response of {len(owner.state.kept.response) if owner.state.kept else 0} bytes")
