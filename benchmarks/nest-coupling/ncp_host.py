"""NCP arm host: launches the NEST neural endpoint and drives it with ncp_local.
Usage: ncp_host.py DELTA_MS {count|spikes}"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

from ncp_local import LocalBinding, LocalClient

from common import T_BIO_MS, load1, now

HERE = Path(__file__).resolve().parent


def main() -> None:
    delta, payload = float(sys.argv[1]), sys.argv[2]
    binding = LocalBinding.fresh("neural")
    child = subprocess.Popen([sys.executable, "-u", str(HERE / "ncp_neural.py"), json.dumps(binding.as_dict())],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=HERE, env=os.environ.copy(),
                             bufsize=0)
    client = LocalClient(binding, child.stdout, child.stdin, timeout_s=300)
    response = client.call("prepare", {"delta_ms": delta, "payload": payload})
    assert response["outcome"] == "committed", response
    steps = round(T_BIO_MS / delta)
    load = load1()
    spikes = 0
    rtt = []
    t0 = now()
    for _ in range(steps):
        s0 = now()
        response = client.call("step", {"stimulus": 0})
        rtt.append(now() - s0)
        if response["outcome"] != "committed":
            raise RuntimeError(response)
        body = response["body"]
        spikes += body["count"] if payload == "count" else len(body["senders"])
    t1 = now()
    response = client.call("finish", {})
    child.stdin.close()
    code = child.wait(timeout=120)
    rtt_sorted = sorted(rtt)
    print(json.dumps({"arm": "ncp" if payload == "count" else "ncp-spikes", "delta_ms": delta, "wall_s": t1 - t0, "spikes": spikes, "load1": load,
                      "child_exit": code, "rtt_median_s": statistics.median(rtt),
                      "rtt_p95_s": rtt_sorted[int(0.95 * (len(rtt_sorted) - 1))], "steps": steps}))


if __name__ == "__main__":
    main()
