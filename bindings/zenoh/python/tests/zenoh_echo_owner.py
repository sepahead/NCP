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
    def execute(self, request):
        if request.op == "sleep":
            time.sleep(request.body["seconds"])
            return request.body
        log = os.environ.get("NCP_EXECUTION_LOG")
        if log:
            with open(log, "a") as handle:
                handle.write(json.dumps(request.body, separators=(",", ":"), default=repr) + "\n")  # arrays as text
        return super().execute(request)


def main() -> None:
    service, endpoint = sys.argv[1], sys.argv[2]
    config = zenoh.Config()
    config.insert_json5("mode", '"peer"')
    config.insert_json5("scouting/multicast/enabled", "false")
    config.insert_json5("listen/endpoints", json.dumps([endpoint]))
    session = zenoh.open(config)
    server = ncp_zenoh.Server(session, service, lambda: ncp.Owner(CONTRACT, Logged())).start()
    print("ready", flush=True)
    sys.stdin.read()
    server.stop(0.0)
    session.close()


if __name__ == "__main__":
    main()
