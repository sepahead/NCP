"""NEST owner faults through the NCP host (see ../PROTOCOL.md).

Usage: nest_fault.py {nest-raise|nest-kill} SEED
nest-raise: the NEST owner raises inside a random step; the host must see `indeterminate`
            and the owner must retire and exit.
nest-kill:  the host kills the NEST owner during a step; the host must classify the call
            as `execution_unknown` within its time limit.
Runs a 2000-neuron Brunel network with 4 threads and 20 ms intervals. Prints one JSON line.
"""
from __future__ import annotations

import json
import os
import random
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from ncp_local import LocalBinding, LocalClient
from ncp_local.wire import LocalError

CAMPAIGN = Path(os.environ["NEST_CAMPAIGN_HARNESS"])
STEPS = 25


def main() -> None:
    scenario, seed = sys.argv[1], int(sys.argv[2])
    rng = random.Random(seed)
    binding = LocalBinding.fresh("neural")
    env = dict(os.environ)
    raise_step = rng.randrange(1, STEPS + 1) if scenario == "nest-raise" else 0
    env["NCP_FAULT_RAISE_STEP"] = str(raise_step)
    child = subprocess.Popen([sys.executable, "-s", str(CAMPAIGN / "endpoint.py"), json.dumps(binding.as_dict())],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, cwd=CAMPAIGN, env=env, bufsize=0)
    client = LocalClient(binding, child.stdout, child.stdin, timeout_s=30)
    client.call("prepare", {"network": "brunel", "n": 2000, "threads": 4, "delta_ms": 20.0, "seed": seed,
                            "payload": "count"})
    kill_step = rng.randrange(1, STEPS + 1) if scenario == "nest-kill" else 0
    outcomes, error, killed_at = [], None, None
    started = time.monotonic()
    try:
        for step in range(1, STEPS + 1):
            if step == kill_step:
                delay = rng.uniform(0.0, 0.01)
                killer = threading.Timer(delay, lambda: child.send_signal(signal.SIGKILL))
                killer.start()
                killed_at = step
            response = client.call("step", {"stimulus": 0})
            outcomes.append(response["outcome"])
            if response["outcome"] != "committed":
                break
        if not client.retired:
            client.call("finish", {})
    except LocalError as caught:
        error = caught.code
    seconds = time.monotonic() - started
    try:
        child.stdin.close()
    except OSError:
        pass
    try:
        code = child.wait(timeout=30)
    except subprocess.TimeoutExpired:
        child.kill()
        code = "killed-after-timeout"
    print(json.dumps({"scenario": scenario, "seed": seed, "owner": "nest", "raise_step": raise_step or None,
                      "kill_step": killed_at, "outcomes": outcomes, "error": error, "retired": client.retired,
                      "owner_exit": code, "seconds": round(seconds, 4), "wrong_accepted": 0}))


if __name__ == "__main__":
    main()
