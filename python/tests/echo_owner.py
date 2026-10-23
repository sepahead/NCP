"""An echo owner for tests and benchmarks: returns the request body.

echo_owner.py [--no-digest-check]              one session on standard input and output
echo_owner.py [--no-digest-check] unix PATH    one session per connection; prints "ready unix:PATH"
echo_owner.py tcp                              one session per connection; prints "ready tcp:127.0.0.1:PORT"

--no-digest-check turns off the comparison of request digests (spec section 3, rule 4).
"""
import os
import struct
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}')


def spikes(n):
    """N spikes from the benchmark generator: senders 1 to 1000 (u32), times 0.1 to 10.0 ms (f64)."""
    state, senders, times = 0x2545F4914F6CDD1D, [], []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        senders.append((state >> 33) % 1000 + 1)
        times.append(((state >> 20) % 100) / 10.0 + 0.1)
    return struct.pack(f"<{n}I", *senders), struct.pack(f"<{n}d", *times)


class Echo:
    """echo returns the request body; spikes returns N cached spikes; fail raises."""

    def __init__(self):
        self.cache = {}

    def validate(self, op, body):
        if op == "echo" and isinstance(body, dict) and body.get("invalid"):
            raise ncp.BodyInvalid("invalid requested")
        if op == "spikes" and not (isinstance(body, dict) and type(body.get("n")) is int and 0 <= body["n"] <= 1 << 22):
            raise ncp.BodyInvalid("n must be an integer from 0 to 2**22")

    def execute(self, op, body):
        if op == "fail":
            raise RuntimeError("requested failure")
        if op == "spikes":
            n = body["n"]
            if n == 0:
                return {"count": 13}
            if n not in self.cache:
                self.cache[n] = spikes(n)
            senders, times = self.cache[n]
            return {"senders": ncp.Array("u32", [n], senders), "times": ncp.Array("f64", [n], times)}
        return body


def make_owner(max_bound=ncp.MAX_BOUND, check_digests=True):
    return ncp.Owner("echo", CONTRACT.identity, Echo(), CONTRACT.operations, max_bound=max_bound,
                     check_digests=check_digests)


if __name__ == "__main__":
    arguments = sys.argv[1:]
    check = "--no-digest-check" not in arguments
    arguments = [argument for argument in arguments if argument != "--no-digest-check"]
    if not arguments:
        ncp.serve_stdio(make_owner(check_digests=check))
    else:
        if arguments[0] == "unix":
            server = ncp.UnixServer(lambda: make_owner(check_digests=check), arguments[1]).start()
            print(f"ready unix:{arguments[1]}", flush=True)
        else:
            server = ncp.TcpServer(make_owner).start()
            print(f"ready tcp:127.0.0.1:{server.address[1]}", flush=True)
        try:
            while True:
                time.sleep(3600)
        finally:
            server.stop()
