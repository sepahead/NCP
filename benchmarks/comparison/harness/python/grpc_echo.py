"""gRPC unary calls with raw bytes messages (grpcio, no protobuf code generation).

grpc_echo.py server unix|tcp                 (prints "ready TARGET")
grpc_echo.py client unix|tcp CALLS WARMUP SPIKES
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from concurrent import futures

import grpc

from common import Responder, check, measure, report, request, start_server, stop_server

METHOD = "/bench.Echo/Call"
OPTIONS = [("grpc.max_receive_message_length", 64 << 20), ("grpc.max_send_message_length", 64 << 20)]


def server(kind: str) -> None:
    respond = Responder()
    handler = grpc.method_handlers_generic_handler(
        "bench.Echo", {"Call": grpc.unary_unary_rpc_method_handler(lambda data, context: respond(data))})
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1), options=OPTIONS)
    server.add_generic_rpc_handlers((handler,))
    if kind == "unix":
        directory = tempfile.mkdtemp(prefix="g", dir="/tmp")
        target = f"unix:{directory}/s"
        server.add_insecure_port(target)
    else:
        port = server.add_insecure_port("127.0.0.1:0")
        target = f"127.0.0.1:{port}"
    server.start()
    print(f"ready {target}", flush=True)
    try:
        while True:
            time.sleep(3600)
    finally:
        server.stop(None)


def client(kind: str) -> None:
    calls, warmup, spikes = (int(value) for value in sys.argv[3:6])
    process, target = start_server([sys.executable, "-s", os.path.abspath(__file__), "server", kind])
    try:
        with grpc.insecure_channel(target, options=OPTIONS) as channel:
            stub = channel.unary_unary(METHOD)

            def call(index: int) -> None:
                data = request(index, spikes)
                check(data, stub(data, wait_for_ready=True), spikes)

            times = measure(call, calls, warmup)
    finally:
        stop_server(process)
    report(times, warmup=warmup, spikes=spikes, grpc=grpc.__version__)


if __name__ == "__main__":
    server(sys.argv[2]) if sys.argv[1] == "server" else client(sys.argv[2])
