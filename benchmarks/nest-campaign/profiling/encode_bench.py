"""The codec pieces of one spike exchange, warm and without NEST (see README.md).

Usage: encode_bench.py PYTHON_SDK_DIR [SPIKES]
Times, in the interpreter that runs it, the packing of the spike lists, the encoding and decoding of
the response, its SHA-256 digest, and the encoding and decoding of the step request, with the
message layouts of the NCP 2 Python SDK (python/ncp/exchange.py).
"""

from __future__ import annotations

import array
import hashlib
import random
import ssl
import sys
import time

sys.path.insert(0, sys.argv[1])
import ncp  # noqa: E402
from ncp import frame  # noqa: E402

SPIKES = int(sys.argv[2]) if len(sys.argv) > 2 else 1787
SESSION, IDENTITY = "ab" * 32, "cd" * 32
rng = random.Random(1)
senders = sorted(rng.randrange(1, 10001) for _ in range(SPIKES))
steps = [rng.randrange(0, 20000) for _ in range(SPIKES)]


def bench(name: str, function, repetitions: int = 3000) -> None:
    function()
    best = []
    for _ in range(5):
        start = time.perf_counter_ns()
        for _ in range(repetitions):
            function()
        best.append((time.perf_counter_ns() - start) / repetitions / 1000)
    print(f"{name:42} {min(best):8.2f} µs")


def pack() -> tuple[bytes, bytes]:
    return array.array("I", senders).tobytes(), array.array("q", steps).tobytes()


def request() -> dict:
    return {"ncp": 2, "session": SESSION, "seq": 7, "op": "step", "ack": IDENTITY, "body": {"stimulus": 0}}


packed = pack()
body = {"senders": ncp.Array("u32", [SPIKES], packed[0]), "steps": ncp.Array("i64", [SPIKES], packed[1])}
response = {"ncp": 2, "session": SESSION, "seq": 7, "request": IDENTITY, "outcome": "ok", "code": None, "body": body}
response_frame, request_frame = frame.encode(response), frame.encode(request())
print(
    f"Python {sys.version.split()[0]}, {ssl.OPENSSL_VERSION}; response {len(response_frame)} bytes, "
    f"request {len(request_frame)} bytes"
)
bench("pack the two spike arrays", pack)
bench("encode the response", lambda: frame.encode(response))
bench("SHA-256 of the response", lambda: hashlib.sha256(response_frame).digest())
bench("decode the response", lambda: frame.decode(response_frame, 1 << 26))
bench("encode the request", lambda: frame.encode(request()))
bench("decode the request", lambda: frame.decode(request_frame, 1 << 26))
