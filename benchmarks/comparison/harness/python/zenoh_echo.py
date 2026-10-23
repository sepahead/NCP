"""Zenoh query/reply (eclipse-zenoh), peer mode over TCP loopback, no multicast scouting.

zenoh_echo.py server                         (prints "ready tcp/127.0.0.1:PORT")
zenoh_echo.py client CALLS WARMUP SPIKES
"""
from __future__ import annotations

import os
import socket
import sys
import time

import zenoh

from common import Responder, check, measure, report, request, start_server, stop_server

KEY = "bench/echo"


def config(**endpoints: str) -> zenoh.Config:
    result = zenoh.Config()
    result.insert_json5("mode", '"peer"')
    result.insert_json5("scouting/multicast/enabled", "false")
    for name, endpoint in endpoints.items():
        result.insert_json5(f"{name}/endpoints", f'["{endpoint}"]')
    return result


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def server() -> None:
    endpoint = f"tcp/127.0.0.1:{free_port()}"
    session = zenoh.open(config(listen=endpoint))
    respond = Responder()
    queryable = session.declare_queryable(KEY, lambda query: query.reply(KEY, respond(query.payload.to_bytes())))
    print(f"ready {endpoint}", flush=True)
    try:
        while True:
            time.sleep(3600)
    finally:
        queryable.undeclare()
        session.close()


def client() -> None:
    calls, warmup, spikes = (int(value) for value in sys.argv[2:5])
    process, endpoint = start_server([sys.executable, "-s", os.path.abspath(__file__), "server"])
    session = zenoh.open(config(connect=endpoint))
    try:
        querier = session.declare_querier(KEY, timeout=10.0)
        deadline = time.monotonic() + 10
        while not session.info.peers_zid():  # wait until the link to the server is up
            if time.monotonic() > deadline:
                raise SystemExit("no Zenoh peer")
            time.sleep(0.01)

        def call(index: int) -> None:
            data = request(index, spikes)
            reply = querier.get(payload=data).recv()
            if reply.ok is None:
                raise SystemExit("no reply")
            check(data, reply.ok.payload.to_bytes(), spikes)

        times = measure(call, calls, warmup)
        querier.undeclare()
    finally:
        session.close()
        stop_server(process)
    report(times, warmup=warmup, spikes=spikes, zenoh="eclipse-zenoh")


if __name__ == "__main__":
    server() if sys.argv[1] == "server" else client()
