"""Python NCP host: drives the NEST owner with ncp_local.

Usage: py_host.py {count|spikes} NETWORK N THREADS DELTA_MS SEED
The SDK version is the ncp_local package on PYTHONPATH; the owner uses the same one.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ncp_local import LocalBinding, LocalClient

from common import T_BIO_MS, emit, load1, now, save_times, spec_from, tick

HERE = Path(__file__).resolve().parent


def main() -> None:
    payload, spec = sys.argv[1], spec_from(sys.argv[2:])
    binding = LocalBinding.fresh("neural")
    child = subprocess.Popen([sys.executable, "-s", str(HERE / "endpoint.py"), json.dumps(binding.as_dict())],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=HERE, env=os.environ.copy(),
                             bufsize=0)
    client = LocalClient(binding, child.stdout, child.stdin, timeout_s=300)
    response = client.call("prepare", {**spec, "payload": payload})
    assert response["outcome"] == "committed", response
    steps = round(T_BIO_MS / spec["delta_ms"])
    load = load1()
    spikes = 0
    collect = os.environ.get("NCP_COLLECT_OUT")
    senders, steps_seen = [], []
    calls: list[int] = []
    t0 = now()
    for _ in range(steps):
        start = tick()
        response = client.call("step", {"stimulus": 0})
        calls.append(tick() - start)
        if response["outcome"] != "committed":
            raise RuntimeError(response["code"])
        body = response["body"]
        spikes += body["count"] if payload == "count" else len(body["senders"])
        if collect:
            senders += body["senders"]
            steps_seen += body["steps"]
    t1 = now()
    save_times("NCP_CALL_TIMES", calls)
    if collect:
        with open(collect, "w") as handle:
            json.dump({"senders": senders, "steps": steps_seen}, handle)
    finished = client.call("finish", {})
    child.stdin.close()
    code = child.wait(timeout=120)
    emit({"arm": f"ncp-py-{payload}", **spec, "wall_s": t1 - t0, "spikes": spikes,
          "recorded": finished["body"]["recorded"], "exchanges": steps, "load1": load, "child_exit": code})


if __name__ == "__main__":
    main()
