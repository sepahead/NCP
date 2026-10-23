"""ZeroMQ REQ/REP (pyzmq) over ipc:// or tcp://.

zmq_echo.py server ipc|tcp                   (prints "ready ENDPOINT")
zmq_echo.py client ipc|tcp CALLS WARMUP SPIKES
"""

from __future__ import annotations

import os
import sys
import tempfile

import zmq
from common import Responder, check, measure, report, request, start_server, stop_server


def server(kind: str) -> None:
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    if kind == "ipc":
        endpoint = f"ipc://{tempfile.mkdtemp(prefix='z', dir='/tmp')}/s"
        socket.bind(endpoint)
    else:
        port = socket.bind_to_random_port("tcp://127.0.0.1")
        endpoint = f"tcp://127.0.0.1:{port}"
    print(f"ready {endpoint}", flush=True)
    respond = Responder()
    while True:
        response = respond(socket.recv())
        socket.send(response, copy=len(response) < 65536)


def client(kind: str) -> None:
    calls, warmup, spikes = (int(value) for value in sys.argv[3:6])
    process, endpoint = start_server([sys.executable, "-s", os.path.abspath(__file__), "server", kind])
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect(endpoint)
    try:

        def call(index: int) -> None:
            data = request(index, spikes)
            socket.send(data)
            check(data, socket.recv(), spikes)

        times = measure(call, calls, warmup)
    finally:
        socket.close(linger=0)
        context.term()
        stop_server(process)
    report(times, warmup=warmup, spikes=spikes, pyzmq=zmq.__version__, libzmq=zmq.zmq_version())


if __name__ == "__main__":
    server(sys.argv[2]) if sys.argv[1] == "server" else client(sys.argv[2])
