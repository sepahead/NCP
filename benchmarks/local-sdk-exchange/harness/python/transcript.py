"""Python SDK transcript for a fixed script (see ../../PROTOCOL-2.md).

Prints every request byte string, owner output, and LocalClient frame in hexadecimal,
one per line. The released and the current SDK must print the same lines.
"""
import json
import os
import threading

from ncp_local import LocalBinding, LocalClient, LocalOwner, serve_local
from ncp_local.protocol import make_request
from ncp_local.wire import encode, read_local_frame, write_local_frame, LocalError

class Echo:
    def __init__(self): self.n = 0
    def validate(self, op, body):
        if op == "step" and body.get("bad"): raise LocalError("invalid_input")
    def execute(self, op, body):
        if op == "prepare": self.n = body["n"]; return {"prepared": True}
        if op == "step" and body.get("boom"): raise RuntimeError("boom")
        if op == "step": return {"senders": list(range(1, self.n + 1)), "times": [i / 10 + 0.1 for i in range(self.n)],
                                 "z": -0.0, "big": 9007199254740991, "u": "é😀\n\"", "neg": -1e-300, "huge": 1e300}
        return {"finished": True}
    def retire(self): pass

b = LocalBinding.from_dict({"profile_digest": LocalBinding.fresh("neural").profile_digest,
                            "run_id": "0b0fd6c0-6a0e-4c1b-9d7e-3f2a1b0c9d8e",
                            "generation": "5f4e3d2c-1b0a-4987-a6b5-c4d3e2f1a0b9", "role": "neural"})
lines = []
def emit(label, data): lines.append(label + "\t" + (data.hex() if isinstance(data, bytes) else str(data)))

owner = LocalOwner(b, Echo())
def send(label, seq, op, body, binding=b):
    try:
        req = make_request(binding, seq, op, body)
    except LocalError as e:
        emit(label + " make_request", "error " + e.code); return None
    raw = encode(req); emit(label + " request", raw)
    try:
        out = owner.handle(raw); emit(label + " output", out); return json.loads(out)
    except LocalError as e:
        emit(label + " handle", "error " + e.code); return None

send("step-before-prepare", 1, "step", {})
p = send("prepare", 1, "prepare", {"n": 127})
send("prepare-retry", 1, "prepare", {"n": 127})
send("pending", 2, "step", {})
send("wrong-ack", 1, "ack", {"result_digest": "0" * 64})
send("lookup", 1, "result", {"request_digest": p and json.loads(encode(make_request(b, 1, "prepare", {"n": 127})))["request_digest"]})
send("ack", 1, "ack", {"result_digest": p["result_digest"]})
send("ack-repeat", 1, "ack", {"result_digest": p["result_digest"]})
send("released-retry", 1, "prepare", {"n": 127})
send("role", 2, "capture", {})
send("bad-body", 2, "step", {"bad": True})
foreign = LocalBinding.from_dict({**b.as_dict(), "run_id": "11111111-2222-4333-8444-555555555555"})
send("foreign", 2, "step", {}, foreign)
r = send("step", 2, "step", {"x": [1, 2.5, None, True, {"b": 1, "a": 2}]})
send("gap", 9, "step", {})
send("step-ack", 2, "ack", {"result_digest": r["result_digest"]})
send("boom", 3, "step", {"boom": True})
send("after-boom", 4, "step", {})
send("bad-sequence", 0, "step", {})
send("oversize", 3, "step", {"s": "x" * 70000})

# LocalClient over real pipes, with every frame recorded in both directions.
b2 = LocalBinding.from_dict({**b.as_dict(), "generation": "6f4e3d2c-1b0a-4987-a6b5-c4d3e2f1a0b9"})
c2o_r, c2o_w = os.pipe(); o2c_r, o2c_w = os.pipe(); rec_r, rec_w = os.pipe(); rel_r, rel_w = os.pipe()
owner2 = LocalOwner(b2, Echo())
frames = []
def relay(src, dst, tag):
    reader, writer = os.fdopen(src, "rb", buffering=0), os.fdopen(dst, "wb", buffering=0)
    while (frame := read_local_frame(reader)) is not None:
        frames.append((tag, frame)); write_local_frame(writer, frame)
    writer.close()
t1 = threading.Thread(target=relay, args=(c2o_r, rel_w, "c2o")); t1.start()
t2 = threading.Thread(target=serve_local, args=(owner2, os.fdopen(rel_r, "rb", buffering=0), os.fdopen(rec_w, "wb", buffering=0))); t2.start()
t3 = threading.Thread(target=relay, args=(rec_r, o2c_w, "o2c")); t3.start()
client_writer = os.fdopen(c2o_w, "wb", buffering=0)
client = LocalClient(b2, os.fdopen(o2c_r, "rb", buffering=0), client_writer, timeout_s=10)
client.call("prepare", {"n": 13})
for i in range(5): client.call("step", {"i": i})
client.request("step", {"i": 99}); client.result(); client.acknowledge()
client.call("finish", {})
client_writer.close()
for thread in (t1, t2, t3):
    thread.join()
for tag, frame in frames: emit("client " + tag, frame)
print("\n".join(lines))
