"""Run one trial of fault-campaign protocol 4 (see ../PROTOCOL-4.md) and print one JSON line.

Usage: fault_client4.py SCENARIO SEED OWNER BINDING CLIENT
       fault_client4.py victim ADDRESS        (used by the kill-client scenario)
SCENARIO: the scenarios of fault_client2.py.
OWNER: python (harness/fault_owner4.py) or rust (the echo owner of rust/examples, RUST_OWNER).
BINDING: unix or tcp. The owner runs as a server, and a relay (harness/relay_socket.py)
changes frames between client and owner.
CLIENT: python (the NCP 2 Python SDK, in this process) or rust (harness/rust-client,
RUST_FAULT_CLIENT).
The plan drawn from SEED, the steps, the views, the execution log, and the invariants are those
of fault_client2.py. After a killed client, the trial checks that the owner still serves a new
session within 10 s.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from fault_client2 import BOUND, CONTRACT, STEPS, TIMEOUT_S, check, executions, ncp, run_session  # noqa: E402

SERVE_AGAIN_S = 10.0


def server_command(owner: str, binding: str, path: str) -> list[str]:
    command = [os.environ["RUST_OWNER"]] if owner == "rust" else [sys.executable, "-s", str(HERE / "fault_owner4.py")]
    return command + (["unix", path] if binding == "unix" else ["tcp"])


def start(command: list[str], env: dict, pass_fds: tuple = ()) -> tuple[subprocess.Popen, str]:
    """Start a program that prints "ready ADDRESS". Returns it and the address."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, text=True, env=env, pass_fds=pass_fds, start_new_session=True
    )
    words = process.stdout.readline().split()  # type: ignore[union-attr]
    if len(words) != 2 or words[0] != "ready":
        process.kill()
        raise RuntimeError(f"{command[0]} did not start: {words}")
    return process, words[1]


def stop(process: subprocess.Popen | None) -> int | str | None:
    """Stop a server or relay and its process group. On macOS, `killpg` fails with EPERM while the
    group's only member is a zombie, for example a killed owner that is not yet reaped, and with
    ESRCH once it is reaped; both mean that the group is gone or going (PROTOCOL-5.md)."""
    if process is None:
        return None
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            process.wait()
    if process.stdout is not None:
        process.stdout.close()
    return process.returncode


def python_channel(address: str, timeout: float = 10.0) -> ncp.StreamChannel:
    if address.startswith("unix:"):
        return ncp.connect_unix(address[5:], timeout=timeout)
    host, port = address[4:].rsplit(":", 1)
    return ncp.connect_tcp(host, int(port), timeout=timeout)


def serves_again(address: str) -> tuple[bool, float]:
    """Whether the owner serves a new session, with one step, within SERVE_AGAIN_S."""
    started = time.monotonic()
    try:
        client = ncp.Client(
            python_channel(address), application="echo", contract=CONTRACT.identity, timeout=SERVE_AGAIN_S
        )
        client.open()
        served = client.call("echo", {"k": 0}).body == {"k": 0}
        client.close()
    except (ncp.Rejected, ncp.Ended, ncp.ProtocolError, OSError):
        served = False
    seconds = time.monotonic() - started
    return served and seconds <= SERVE_AGAIN_S, round(seconds, 4)


def kill_client(rng: random.Random, client: str, address: str, env: dict) -> dict:
    """Kill a running client; the owner must still serve a new session."""
    if client == "rust":
        command = [os.environ["RUST_FAULT_CLIENT"], "victim", address]
    else:
        command = [sys.executable, "-s", __file__, "victim", address]
    victim = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, env=env)
    opened = victim.stdout.readline().strip() == "open"  # type: ignore[union-attr]
    time.sleep(rng.uniform(0.0, 0.1))
    victim.send_signal(signal.SIGKILL)
    victim.wait()
    victim.stdout.close()  # type: ignore[union-attr]
    served, seconds = serves_again(address)
    return {"victim_opened": opened, "owner_served_again": served, "serve_again_seconds": seconds}


def victim(address: str) -> None:
    client = ncp.Client(python_channel(address), application="echo", contract=CONTRACT.identity, bound=BOUND)
    client.open()
    print("open", flush=True)
    for k in range(1, 10_000_000):
        client.call("echo", {"k": k})


def rust_session(address: str, plan: dict, work: Path, killer: threading.Timer | None) -> tuple:
    report = work / "report.json"
    command = [os.environ["RUST_FAULT_CLIENT"], address, str(int(TIMEOUT_S * 1000)), json.dumps(plan), str(report)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    connected = process.stdout.readline().strip() == "connected"  # type: ignore[union-attr]
    if killer is not None and connected:
        killer.start()
    try:
        _, stderr = process.communicate(timeout=60)
    except subprocess.TimeoutExpired:
        process.kill()
        _, stderr = process.communicate()
    if not report.exists():
        tail = " | ".join(stderr.strip().splitlines()[-2:])
        return {}, 0, None, f"undocumented:the Rust client exited with {process.returncode}: {tail}"
    data = json.loads(report.read_text())
    views = {int(k): v for k, v in data["views"].items()}
    return views, data["wrong_accepted"], data["last_sent"], data["error"]


def main() -> None:
    if sys.argv[1] == "victim":
        return victim(sys.argv[2])
    scenario, seed, owner, binding, client = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
    report: dict = {"scenario": scenario, "seed": seed, "owner": owner, "binding": binding, "client": client}
    rng = random.Random(seed)
    work = Path(tempfile.mkdtemp(prefix="ncp4", dir="/tmp"))  # socket paths must be short
    log = work / "executions.jsonl"
    env = dict(os.environ, NCP_EXECUTION_LOG=str(log))
    plan: dict = {}
    server = relay = None
    read_fd = None
    try:
        if scenario.startswith(("flip", "truncate", "duplicate")):
            mode, direction = scenario.split("-")
            index = rng.randrange(STEPS + 2)  # open, six steps, and close, in each direction
            plan["relay_seed"] = rng.randrange(2**31)
        elif scenario == "stall":
            plan["stall_k"] = rng.randrange(1, STEPS + 1)
            env.update(FAULT_STALL_K=str(plan["stall_k"]), FAULT_STALL_S=str(3 * TIMEOUT_S))
        elif scenario == "oversize-response":
            plan["oversize_k"] = rng.randrange(1, STEPS + 1)
            env["FAULT_OVERSIZE_K"] = str(plan["oversize_k"])
        elif scenario == "oversize-request":
            plan["oversize_request_k"] = rng.randrange(1, STEPS + 1)
        elif scenario == "backend-raise":
            plan["fail_k"] = rng.randrange(1, STEPS + 1)
        elif scenario == "kill-owner" and owner == "python":
            env["FAULT_DELAY_S"] = "0.02"
        server, address = start(server_command(owner, binding, str(work / "owner.sock")), env)
        if scenario == "kill-client":
            report.update(kill_client(rng, client, address, env))
            print(json.dumps(report))
            return
        target = address
        if "relay_seed" in plan:
            read_fd, write_fd = os.pipe()
            listen = f"unix:{work / 'relay.sock'}" if binding == "unix" else "tcp"
            relay, target = start(
                [
                    sys.executable,
                    "-s",
                    str(HERE / "relay_socket.py"),
                    direction,
                    str(index),
                    mode,
                    str(plan["relay_seed"]),
                    listen,
                    address,
                ],
                dict(env, RELAY_REPORT_FD=str(write_fd)),
                pass_fds=(write_fd,),
            )
            os.close(write_fd)
        killer = None
        if scenario == "kill-owner":
            # Any moment from the start to the end of the session, counted from the connection.
            window = 0.2 if owner == "python" else 0.005
            plan["kill_after_s"] = round(rng.uniform(0.0, window), 5)
            killer = threading.Timer(plan["kill_after_s"], lambda: os.killpg(server.pid, signal.SIGKILL))
        started = time.monotonic()
        if client == "rust":
            views, wrong, last_sent, error = rust_session(target, plan, work, killer)
        else:
            channel = python_channel(target)
            session = ncp.Client(
                channel, application="echo", contract=CONTRACT.identity, bound=BOUND, timeout=TIMEOUT_S
            )
            if killer is not None:
                killer.start()
            views, wrong, last_sent, error = run_session(session, plan)
            channel.close()
        seconds = time.monotonic() - started
        if killer is not None:
            killer.cancel()
        relay_report = None
        if relay is not None:
            try:
                relay.wait(timeout=10)  # it ends when both directions have ended
            except subprocess.TimeoutExpired:
                pass
            stop(relay)
            with os.fdopen(read_fd, closefd=True) as handle:  # type: ignore[arg-type]
                text = handle.read().strip()
            read_fd = None
            relay_report = json.loads(text) if text else None
        stop(server)
        server = None
        executed = executions(log)
        steps = {k: v for k, v in views.items() if 1 <= k <= STEPS}
        completed = error is None and len(steps) == STEPS and all(v == "ok" for v in steps.values())
        report.update(
            {
                "plan": plan,
                "views": {str(k): v for k, v in sorted(views.items())},
                "error": error,
                "completed": completed,
                "wrong_accepted": wrong,
                "executed": executed,
                "invariants": check(steps, executed, last_sent),
                "seconds": round(seconds, 4),
                "relay": relay_report,
            }
        )
        print(json.dumps(report))
    finally:
        stop(relay)
        stop(server)
        if read_fd is not None:
            os.close(read_fd)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
