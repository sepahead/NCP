"""Sequential and pipelined lockstep clients for the local Python SDK (see ../../PROTOCOL.md).

Usage: client.py MODE N CALLS WARMUP CMD [ARG...]
MODE is `sdk` (LocalClient.call), `sequential`, or `pipelined`. The last two use the
same public functions, so that only the order of frames differs. A pipelined client
breaks the v1 client rule that only a verified acknowledgement advances the sequence;
this harness measures what that rule costs. Prints one JSON line.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

from ncp_local import LocalBinding, LocalClient
from ncp_local.protocol import make_request, verify_response
from ncp_local.wire import decode, encode, read_local_frame, write_local_frame


def summary(samples: list[float]) -> dict:
    ordered = sorted(samples)
    at = lambda q: ordered[round((len(ordered) - 1) * q)] * 1e6  # noqa: E731
    return {"calls": len(ordered), "median_us": at(0.5), "p05_us": at(0.05), "p95_us": at(0.95),
            "p99_us": at(0.99), "min_us": at(0.0), "max_us": at(1.0)}


class Channel:
    def __init__(self, binding, reader, writer):
        self.binding, self.reader, self.writer = binding, reader, writer

    def send(self, request):
        write_local_frame(self.writer, encode(request), deadline=time.monotonic() + 60)

    def receive(self, request):
        response = decode(read_local_frame(self.reader, deadline=time.monotonic() + 60))
        verify_response(response, self.binding, request)
        return response

    def ack_of(self, response):
        return make_request(self.binding, response["sequence"], "ack", {"result_digest": response["result_digest"]})


def main() -> None:
    mode, n, calls, warmup, command = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5:]
    binding = LocalBinding.fresh("neural")
    child = subprocess.Popen(command + [json.dumps(binding.as_dict())], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, bufsize=0)
    samples, received = [], 0
    if mode == "soak":
        # LocalClient.call with a uniform reservoir of 4096 call times, so that memory stays fixed.
        import random
        rng, timed = random.Random(20261022), 0
        client = LocalClient(binding, child.stdout, child.stdin, timeout_s=60)
        assert client.call("prepare", {"n": n})["outcome"] == "committed"
        for index in range(warmup + calls):
            started = time.perf_counter()
            response = client.call("step", {"stimulus": 0})
            elapsed = time.perf_counter() - started
            assert response["outcome"] == "committed"
            received = response["body"]["count"] if n == 0 else len(response["body"]["senders"])
            if index >= warmup:
                timed += 1
                if len(samples) < 4096:
                    samples.append(elapsed)
                elif (slot := rng.randrange(timed)) < 4096:
                    samples[slot] = elapsed
        client.call("finish", {})
    elif mode == "sdk":
        client = LocalClient(binding, child.stdout, child.stdin, timeout_s=60)
        assert client.call("prepare", {"n": n})["outcome"] == "committed"
        for index in range(warmup + calls):
            started = time.perf_counter()
            response = client.call("step", {"stimulus": 0})
            elapsed = time.perf_counter() - started
            assert response["outcome"] == "committed"
            received = response["body"]["count"] if n == 0 else len(response["body"]["senders"])
            if index >= warmup:
                samples.append(elapsed)
        client.call("finish", {})
    else:
        channel = Channel(binding, child.stdout, child.stdin)
        prepare = make_request(binding, 1, "prepare", {"n": n})
        channel.send(prepare)
        prepared = channel.receive(prepare)
        ack = channel.ack_of(prepared)
        channel.send(ack)
        assert channel.receive(ack)["outcome"] == "acknowledged"
        held = None
        for index in range(warmup + calls):
            step = make_request(binding, index + 2, "step", {"stimulus": 0})
            started = time.perf_counter()
            if mode == "sequential":
                channel.send(step)
                response = channel.receive(step)
                assert response["outcome"] == "committed"
                ack = channel.ack_of(response)
                channel.send(ack)
                assert channel.receive(ack)["outcome"] == "acknowledged"
            elif mode == "pipelined":
                previous = channel.ack_of(held) if held is not None else None
                if previous is not None:
                    channel.send(previous)
                channel.send(step)
                if previous is not None:
                    assert channel.receive(previous)["outcome"] == "acknowledged"
                response = channel.receive(step)
                assert response["outcome"] == "committed"
                held = response
            else:
                raise SystemExit(f"unknown mode {mode}")
            elapsed = time.perf_counter() - started
            received = response["body"]["count"] if n == 0 else len(response["body"]["senders"])
            if index >= warmup:
                samples.append(elapsed)
        if held is not None:
            ack = channel.ack_of(held)
            channel.send(ack)
            assert channel.receive(ack)["outcome"] == "acknowledged"
        finish = make_request(binding, warmup + calls + 2, "finish", {})
        channel.send(finish)
        finished = channel.receive(finish)
        ack = channel.ack_of(finished)
        channel.send(ack)
        assert channel.receive(ack)["outcome"] == "acknowledged"
    child.stdin.close()
    status = child.wait(timeout=60)
    print(json.dumps({"mode": mode, "language": "python", "n": n, "valid": received == (13 if n == 0 else n),
                      "owner_exit": status, "timing": summary(samples)}))


if __name__ == "__main__":
    main()
