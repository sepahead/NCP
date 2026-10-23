"""NCP 2 Python benchmark client.

ncp2_client.py CALLS WARMUP SPIKES [--no-digest-check] -- OWNER COMMAND...   (pipes to a child owner)
ncp2_client.py CALLS WARMUP SPIKES [--no-digest-check] --connect unix:PATH|tcp:HOST:PORT

Each call sends a small `spikes` request and gets SPIKES spikes back as a u32 and an f64 array
(or the body {"count": 13} when SPIKES is 0). Prints one JSON line (see common.py).
"""
from __future__ import annotations

import sys

import ncp
from common import measure, report

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}')


def main() -> None:
    arguments = sys.argv[1:]
    check = "--no-digest-check" not in arguments[3:5]
    if not check:
        arguments.remove("--no-digest-check")
    calls, warmup, spikes = (int(value) for value in arguments[:3])
    process = None
    if arguments[3] == "--connect":
        kind, _, address = arguments[4].partition(":")
        if kind == "unix":
            channel = ncp.connect_unix(address)
        else:
            host, _, port = address.rpartition(":")
            channel = ncp.connect_tcp(host, int(port))
    else:
        channel, process = ncp.spawn(arguments[4:])
    bound = max(ncp.DEFAULT_BOUND, 1 << (spikes * 12 + 65536 - 1).bit_length())
    client = ncp.Client(channel, application="echo", contract=CONTRACT.identity, bound=min(bound, ncp.MAX_BOUND),
                        check_digests=check)
    client.open()

    def call(index: int) -> None:
        body = client.call("spikes", {"step": index, "n": spikes}).body
        if spikes:
            if len(body["senders"].data) != spikes * 4 or len(body["times"].data) != spikes * 8:
                raise SystemExit("wrong response")
        elif body != {"count": 13}:
            raise SystemExit("wrong response")

    times = measure(call, calls, warmup)
    client.close()
    if process is not None and process.wait(timeout=30) != 0:
        raise SystemExit("owner failed")
    report(times, warmup=warmup, spikes=spikes)


if __name__ == "__main__":
    main()
