"""Run one fault trial with LocalClient and classify its outcome (see ../PROTOCOL.md).

Usage: fault_client.py SCENARIO SEED OWNER_KIND
SCENARIO: flip-c2o, flip-o2c, truncate-c2o, truncate-o2c, kill-owner, kill-client,
          stall, oversize-response, oversize-request, backend-raise.
OWNER_KIND: python or rust (the Rust echo owner is RUST_OWNER, for frame faults only).
Prints one JSON line. "wrong_accepted" counts verified results that differ from the
expected echo; it must be zero.
"""
from __future__ import annotations

import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from ncp_local import LocalBinding, LocalClient
from ncp_local.wire import LocalError, LocalPreflightError

HERE = Path(__file__).resolve().parent
STEPS = 6
TIMEOUT_S = 2.0


def owner_command(kind: str) -> list[str]:
    if kind == "rust":
        return [os.environ["RUST_OWNER"], "owner"]
    return [sys.executable, "-s", str(HERE / "fault_owner.py")]


def expected(step: int, kind: str) -> dict:
    return {"count": 13, "step": step} if kind == "python" else {"count": 13}


def kill_client(seed: int) -> None:
    """Kill a running client; its owner must see end of file, retire, and exit."""
    rng = random.Random(seed)
    marker = Path(tempfile.mkdtemp()) / "retired.jsonl"
    env = dict(os.environ, FAULT_MARKER=str(marker), FAULT_DELAY_S="0.02")
    victim = subprocess.Popen([sys.executable, "-s", __file__, "victim", str(seed), "python"],
                              stdout=subprocess.PIPE, env=env, text=True)
    owner_pid = int(victim.stdout.readline())
    time.sleep(rng.uniform(0.0, STEPS * 0.02))
    victim.send_signal(signal.SIGKILL)
    victim.wait()
    started = time.monotonic()
    gone = False
    while time.monotonic() - started < 10:
        try:
            os.kill(owner_pid, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.01)
    print(json.dumps({"scenario": "kill-client", "seed": seed, "owner": "python", "owner_exited": gone,
                      "owner_exit_seconds": round(time.monotonic() - started, 4), "owner_retired": marker.exists(),
                      "wrong_accepted": 0}))


def victim(seed: int) -> None:
    binding = LocalBinding.fresh("neural")
    child = subprocess.Popen(owner_command("python") + [json.dumps(binding.as_dict())], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, bufsize=0)
    print(child.pid, flush=True)
    client = LocalClient(binding, child.stdout, child.stdin, timeout_s=TIMEOUT_S)
    client.call("prepare", {})
    for _ in range(STEPS * 10):
        client.call("step", {"stimulus": 0})


def main() -> None:
    scenario, seed, kind = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    if scenario == "kill-client":
        return kill_client(seed)
    if scenario == "victim":
        return victim(seed)
    rng = random.Random(seed)
    binding = LocalBinding.fresh("neural")
    marker = Path(tempfile.mkdtemp()) / "retired.jsonl"
    env = dict(os.environ, FAULT_MARKER=str(marker))
    report = {"scenario": scenario, "seed": seed, "owner": kind}
    relay_report = None
    read_fd = None
    if scenario.startswith(("flip", "truncate")):
        mode, direction = scenario.split("-")
        # A session has 2 frames per call in each direction: prepare, ack, then STEPS steps with acks, finish, ack.
        index = rng.randrange(2 * (STEPS + 2))
        read_fd, write_fd = os.pipe()
        command = [sys.executable, "-s", str(HERE / "relay.py"), direction, str(index), mode, str(seed)] \
            + owner_command(kind) + [json.dumps(binding.as_dict())]
        env["RELAY_REPORT_FD"] = str(write_fd)
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0, env=env,
                                 pass_fds=(write_fd,))
        os.close(write_fd)
    else:
        if scenario == "stall":
            env.update(FAULT_STALL_STEP=str(rng.randrange(1, STEPS + 1)), FAULT_STALL_S=str(TIMEOUT_S * 3))
        if scenario == "oversize-response":
            env["FAULT_OVERSIZE_STEP"] = str(rng.randrange(1, STEPS + 1))
        if scenario == "backend-raise":
            env["FAULT_RAISE_STEP"] = str(rng.randrange(1, STEPS + 1))
        if scenario == "kill-owner":
            env["FAULT_DELAY_S"] = "0.02"
        child = subprocess.Popen(owner_command(kind) + [json.dumps(binding.as_dict())], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, bufsize=0, env=env)
    client = LocalClient(binding, child.stdout, child.stdin, timeout_s=TIMEOUT_S)
    outcomes, wrong, error, committed = [], 0, None, 0
    started = time.monotonic()
    killer = None
    if scenario == "kill-owner":
        # Any moment from start-up to finish: 0.2 s for the Python owner, 3 ms for the Rust owner.
        window = 0.2 if kind == "python" else 0.003
        killer = threading.Timer(rng.uniform(0.0, window), lambda: child.send_signal(signal.SIGKILL))
    oversize_step = rng.randrange(1, STEPS + 1) if scenario == "oversize-request" else None
    if killer is not None:
        killer.start()
    try:
        client.call("prepare", {})
        for step in range(1, STEPS + 1):
            if step == oversize_step:
                try:
                    client.call("step", {"blob": "y" * 70_000})
                    outcomes.append("oversize-sent")
                except LocalPreflightError as caught:
                    outcomes.append("preflight:" + caught.code)
                    continue
            response = client.call("step", {"stimulus": 0})
            outcomes.append(response["outcome"])
            if response["outcome"] == "committed":
                committed += 1
                if response["body"] != expected(committed, kind):
                    wrong += 1
            if response["outcome"] != "committed":
                break
        if not client.retired:
            client.call("finish", {})
            outcomes.append("finished")
    except LocalPreflightError as caught:
        error = "preflight:" + caught.code
    except LocalError as caught:
        error = caught.code
    detect_s = time.monotonic() - started
    try:
        child.stdin.close()
    except OSError:
        pass
    try:
        exit_code = child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        exit_code = "killed-after-timeout"
    if read_fd is not None:
        with os.fdopen(read_fd) as handle:
            text = handle.read().strip()
            relay_report = json.loads(text) if text else None
    report.update({"outcomes": outcomes, "error": error, "retired": client.retired, "wrong_accepted": wrong,
                   "seconds": round(detect_s, 4), "owner_exit": exit_code, "relay": relay_report,
                   "owner_retired": marker.exists()})
    print(json.dumps(report))


if __name__ == "__main__":
    main()
