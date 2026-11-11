"""An echo owner on the Zenoh binding, for the cross-language tests of the Rust binding.

Usage: zenoh_echo_owner.py SERVICE LISTEN_ENDPOINT
Serves `ncp/x/SERVICE` in peer mode on LISTEN_ENDPOINT (for example tcp/127.0.0.1:7447), prints
"ready", and serves until its standard input closes. It uses the echo handler of the SDK tests;
each execution appends the request body as one line to NCP_EXECUTION_LOG, if set.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parents[3] / "python"), str(HERE.parents[3] / "python" / "tests")]

import ncp  # noqa: E402
import zenoh  # noqa: E402
from echo_owner import Echo  # noqa: E402

import ncp_zenoh  # noqa: E402

# The test contract of the binding, the same bytes as in test_zenoh.py and the Rust tests.
CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"sleep":{},"spikes":{}},"streams":{}}'
)


class Logged(Echo):
    def execute(self, op, body):
        if op == "sleep":
            time.sleep(body["seconds"])
            return body
        log = os.environ.get("NCP_EXECUTION_LOG")
        if log:
            with open(log, "a") as handle:
                handle.write(json.dumps(body, separators=(",", ":"), default=repr) + "\n")  # arrays as text
        return super().execute(op, body)


def main() -> None:
    service, endpoint = sys.argv[1], sys.argv[2]
    config = zenoh.Config()
    config.insert_json5("mode", '"peer"')
    config.insert_json5("scouting/multicast/enabled", "false")
    config.insert_json5("listen/endpoints", json.dumps([endpoint]))
    session = zenoh.open(config)
    stop, ready = threading.Event(), threading.Event()

    def make_owner() -> ncp.Owner:
        return ncp.Owner(CONTRACT.application, CONTRACT.identity, Logged(), CONTRACT.operations)

    thread = threading.Thread(
        target=ncp_zenoh.serve, args=(session, service, make_owner), kwargs={"stop": stop, "ready": ready}
    )
    thread.start()
    ready.wait(10)
    print("ready", flush=True)
    sys.stdin.read()
    stop.set()
    thread.join()
    session.close()


if __name__ == "__main__":
    main()
