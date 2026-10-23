"""An echo owner for tests and benchmarks: returns the request body."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{}},"streams":{}}')


class Echo:
    def validate(self, op, body):
        if op == "echo" and isinstance(body, dict) and body.get("invalid"):
            raise ncp.BodyInvalid("invalid requested")

    def execute(self, op, body):
        if op == "fail":
            raise RuntimeError("requested failure")
        return body


def make_owner(max_bound=ncp.MAX_BOUND):
    return ncp.Owner("echo", CONTRACT.identity, Echo(), CONTRACT.operations, max_bound=max_bound)


if __name__ == "__main__":
    ncp.serve_stdio(make_owner())
