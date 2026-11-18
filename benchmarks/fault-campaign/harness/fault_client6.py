"""Run one trial of fault-campaign protocol 6 (see ../PROTOCOL-6.md) and print one JSON line.

Usage: fault_client6.py SCENARIO SEED OWNER BINDING CLIENT
       fault_client6.py victim ADDRESS        (used by the kill-client scenario)
OWNER: python (harness/fault_owner6.py) or rust (the echo owner of rust/examples, RUST_OWNER).
BINDING: unix or tcp. The owner runs as a server, and a relay (harness/relay_socket.py)
changes frames between client and owner.
CLIENT: python (the NCP 2 Python SDK, in this process) or rust (harness/rust-client,
RUST_FAULT_CLIENT).
This is fault_client4.py of protocols 4 and 5, with the parts of fault_client2.py that it used,
ported to revision 7 of the SDKs: the client takes the contract, a declined step has the view
`declined:CODE`, and an ended step names its verdict as `yes`, `no`, or `unknown`. The plan drawn
from SEED, the steps, the execution log, and the invariants are those of protocol 4. After a
killed client, the trial checks that the owner still serves a new session within 10 s.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "python"))
import ncp  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}'
)
STEPS = 6
TIMEOUT_S = 2.0
BOUND = ncp.HANDSHAKE_BOUND  # 65,536 bytes, so that an oversized result is cheap
SPIKES = {2: 127, 4: 1788, 6: 127}
SERVE_AGAIN_S = 10.0
# The errors that the Python SDK documents for a call (Client.call).
DOCUMENTED = (ncp.Declined, ncp.Rejected, ncp.Ended, ncp.UsageError)


def spikes(n: int) -> tuple[bytes, bytes]:
    state, senders, times = 0x2545F4914F6CDD1D, [], []
    for _ in range(n):
        state = (state * 6364136223846793005 + 1442695040888963407) % 2**64
        senders.append((state >> 33) % 1000 + 1)
        times.append(((state >> 20) % 100) / 10.0 + 0.1)
    return struct.pack(f"<{n}I", *senders), struct.pack(f"<{n}d", *times)


def step(k: int) -> tuple[str, dict]:
    if k in SPIKES:
        return "spikes", {"k": k, "n": SPIKES[k]}
    return "echo", {"k": k, "v": [k, k * k], "s": f"step {k}"}


def correct(op: str, body: dict, result: ncp.Result) -> bool:
    """Whether an accepted result is the right one for its request."""
    if op == "echo":
        return result.body == body
    senders, times = spikes(body["n"])
    got = result.body
    return (
        isinstance(got, dict)
        and isinstance(got.get("senders"), ncp.Array)
        and isinstance(got.get("times"), ncp.Array)
        and (got["senders"].dtype, got["senders"].shape, bytes(got["senders"].data)) == ("u32", (body["n"],), senders)
        and (got["times"].dtype, got["times"].shape, bytes(got["times"].data)) == ("f64", (body["n"],), times)
    )


def executions(log: Path) -> list[int]:
    if not log.exists():
        return []
    return [json.loads(line)["k"] for line in log.read_text().splitlines() if line.strip()]


def check(views: dict[int, str], executed: list[int], last_sent: int | None) -> dict:
    """The invariants of PROTOCOL-2.md for one trial, with the outcomes of revision 7: a declined
    step did not execute and never will; a rejection names only an `open`."""
    once = len(executed) == len(set(executed))
    in_order = executed == list(range(1, len(executed) + 1))
    done = set(executed)
    uncertain = {k for k, view in views.items() if view.endswith(":unknown")}
    known = (
        all(k in done for k, view in views.items() if view in ("ok", "wrong") or view.endswith(":yes"))
        and all(
            k not in done
            for k, view in views.items()
            if view.startswith(("declined:", "rejected:")) or view.endswith(":no")
        )
        and len(uncertain) <= 1
        and all(k == last_sent for k in uncertain)
        and all(views.get(k, "").startswith(("ok", "wrong", "ended:")) or k in uncertain for k in done)
    )
    return {"once": once, "in_order": in_order, "known": known}


def run_session(client: ncp.Client, plan: dict) -> tuple[dict[int, str], int, int | None, str | None]:
    """Open, six steps, and close. Returns the view of each step, the wrong results, the last step
    sent, and the error that ended the session early, if any."""
    views: dict[int, str] = {}
    wrong, last_sent, error = 0, None, None
    try:
        client.open()
        for k in range(1, STEPS + 1):
            if k == plan.get("oversize_request_k"):
                try:
                    client.call("echo", {"k": k, "blob": "y" * 70_000})
                    views[-k] = "oversize_sent"
                except ncp.UsageError:
                    views[-k] = "refused_before_sending"
            op, body = step(k)
            if k == plan.get("fail_k"):
                op, body = "fail", {"k": k}
            last_sent = k
            try:
                result = client.call(op, body)
            except ncp.Declined as caught:
                views[k] = f"declined:{caught.code}"
                raise
            except ncp.Rejected as caught:
                views[k] = f"rejected:{caught.code}"
                raise
            except ncp.Ended as caught:
                views[k] = f"ended:{caught.code}:{caught.executed.value}"
                raise
            if correct(op, body, result):
                views[k] = "ok"
            else:
                views[k] = "wrong"
                wrong += 1
        last_sent = None
        client.close()
        views[STEPS + 1] = "closed"
    except DOCUMENTED as caught:
        error = type(caught).__name__
    except Exception as caught:  # an exception that the SDK documents for no case: report it
        error = f"undocumented:{type(caught).__name__}:{caught}"
    return views, wrong, last_sent, error


def server_command(owner: str, binding: str, path: str) -> list[str]:
    command = [os.environ["RUST_OWNER"]] if owner == "rust" else [sys.executable, "-s", str(HERE / "fault_owner6.py")]
    return command + (["unix", path] if binding == "unix" else ["tcp"])


def start(command: list[str], env: dict, pass_fds: tuple = ()) -> tuple[subprocess.Popen, str]:
    """Start a program that prints "ready ADDRESS". Returns it and the address. Its standard input
    is a pipe that stays open until `stop`: the Rust echo owner serves until its standard input
    closes, and a runner without a terminal would give it a closed one (PROTOCOL-6.md)."""
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
        pass_fds=pass_fds,
        start_new_session=True,
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
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            stream.close()
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
        client = ncp.Client(python_channel(address), CONTRACT, timeout=SERVE_AGAIN_S)
        client.open()
        served = client.call("echo", {"k": 0}).body == {"k": 0}
        client.close()
    except (*DOCUMENTED, OSError):
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
    client = ncp.Client(python_channel(address), CONTRACT, bound=BOUND)
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
    work = Path(tempfile.mkdtemp(prefix="ncp6", dir="/tmp"))  # socket paths must be short
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
            session = ncp.Client(channel, CONTRACT, bound=BOUND, timeout=TIMEOUT_S)
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
