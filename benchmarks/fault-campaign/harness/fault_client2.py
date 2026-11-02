"""Run one NCP 2 fault trial, classify its outcome, and check what the client learned (see ../PROTOCOL-2.md).

Usage: fault_client2.py SCENARIO SEED OWNER
SCENARIO: flip-c2o, flip-o2c, truncate-c2o, truncate-o2c, duplicate-c2o, duplicate-o2c, kill-owner,
          kill-client, stall, oversize-response, oversize-request, backend-raise.
OWNER: python (harness/fault_owner2.py) or rust (the echo owner of rust/examples, RUST_OWNER).
A trial is one session with the NCP 2 Python client: open, six steps k = 1 to 6, and close. The
owner appends the body of each execution to an execution log. The trial compares that log with
what the client learned about each step. Prints one JSON line.
"""

from __future__ import annotations

import json
import os
import random
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


def owner_command(kind: str) -> list[str]:
    if kind == "rust":
        return [os.environ["RUST_OWNER"]]
    return [sys.executable, "-s", str(HERE / "fault_owner2.py")]


def executions(log: Path) -> list[int]:
    if not log.exists():
        return []
    return [json.loads(line)["k"] for line in log.read_text().splitlines() if line.strip()]


def check(views: dict[int, str], executed: list[int], last_sent: int | None) -> dict:
    """The invariants of PROTOCOL-2.md for one trial."""
    once = len(executed) == len(set(executed))
    in_order = executed == list(range(1, len(executed) + 1))
    done = set(executed)
    uncertain = {k for k, view in views.items() if view.endswith(":unknown") or view == "protocol_error"}
    known = (
        all(k in done for k, view in views.items() if view in ("ok", "wrong") or view.endswith(":yes"))
        and all(
            k not in done
            for k, view in views.items()
            if (view.startswith("rejected:") and view != "rejected:seq_stale") or view.endswith(":no")
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
                except ValueError:
                    views[-k] = "refused_before_sending"
            op, body = step(k)
            if k == plan.get("fail_k"):
                op, body = "fail", {"k": k}
            last_sent = k
            try:
                result = client.call(op, body)
            except ncp.Rejected as caught:
                views[k] = f"rejected:{caught.code}"
                raise
            except ncp.Ended as caught:
                views[k] = f"ended:{caught.code}:{caught.executed}"
                raise
            except ncp.ProtocolError:
                views[k] = "protocol_error"
                raise
            if correct(op, body, result):
                views[k] = "ok"
            else:
                views[k] = "wrong"
                wrong += 1
        last_sent = None
        client.close()
        views[STEPS + 1] = "closed"
    except (ncp.Rejected, ncp.Ended, ncp.ProtocolError) as caught:
        error = type(caught).__name__
    except Exception as caught:  # an exception that the SDK documents for no case: report it
        error = f"undocumented:{type(caught).__name__}:{caught}"
    return views, wrong, last_sent, error


def kill_client(seed: int, kind: str) -> dict:
    """Kill a running client. Its owner must see the end of its input and exit."""
    rng = random.Random(seed)
    victim = subprocess.Popen(
        [sys.executable, "-s", __file__, "victim", str(seed), kind], stdout=subprocess.PIPE, text=True
    )
    owner_pid = int(victim.stdout.readline())
    time.sleep(rng.uniform(0.0, 0.1))
    victim.send_signal(signal.SIGKILL)
    victim.wait()
    victim.stdout.close()
    started = time.monotonic()
    gone = False
    while time.monotonic() - started < 10:
        try:
            os.kill(owner_pid, 0)
        except ProcessLookupError:
            gone = True
            break
        time.sleep(0.005)
    return {"owner_exited": gone, "owner_exit_seconds": round(time.monotonic() - started, 4)}


def victim(kind: str) -> None:
    channel, process = ncp.spawn(owner_command(kind))
    print(process.pid, flush=True)
    client = ncp.Client(channel, application="echo", contract=CONTRACT.identity, bound=BOUND, timeout=TIMEOUT_S)
    client.open()
    for k in range(1, 100_000):
        client.call("echo", {"k": k})


def main() -> None:
    scenario, seed, kind = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    if scenario == "victim":
        return victim(kind)
    report: dict = {"scenario": scenario, "seed": seed, "owner": kind}
    if scenario == "kill-client":
        report.update(kill_client(seed, kind))
        print(json.dumps(report))
        return
    rng = random.Random(seed)
    work = Path(tempfile.mkdtemp(prefix="ncp2-fault-"))
    log = work / "executions.jsonl"
    env = dict(os.environ, NCP_EXECUTION_LOG=str(log))
    plan: dict = {}
    command = owner_command(kind)
    read_fd = None
    if scenario.startswith(("flip", "truncate", "duplicate")):
        mode, direction = scenario.split("-")
        index = rng.randrange(STEPS + 2)  # open, six steps, and close, in each direction
        # The relay draws its bit or cut from a seed of its own. With the trial seed itself, its
        # first draw repeated the draw of the index above (protocol 2, README).
        plan["relay_seed"] = rng.randrange(2**31)
        read_fd, write_fd = os.pipe()
        env["RELAY_REPORT_FD"] = str(write_fd)
        command = [sys.executable, "-s", str(HERE / "relay2.py"), direction, str(index), mode, str(plan["relay_seed"])] + command
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
    elif scenario == "kill-owner" and kind == "python":
        env["FAULT_DELAY_S"] = "0.02"
    pass_fds = (int(env["RELAY_REPORT_FD"]),) if read_fd is not None else ()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0, env=env, pass_fds=pass_fds)
    if read_fd is not None:
        os.close(int(env["RELAY_REPORT_FD"]))
    stdin, stdout = process.stdin, process.stdout

    def write(data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(stdin.fileno(), view) :]

    def close() -> None:
        for stream in (stdin, stdout):
            try:
                stream.close()
            except OSError:
                pass

    channel = ncp.StreamChannel(lambda n: os.read(stdout.fileno(), n), write, stdout.fileno(), close=close)
    client = ncp.Client(channel, application="echo", contract=CONTRACT.identity, bound=BOUND, timeout=TIMEOUT_S)
    killer = None
    if scenario == "kill-owner":
        # Any moment from the start to the end of the session: about 0.2 s for the Python owner,
        # whose steps sleep 20 ms, and a few milliseconds for the Rust owner.
        window = 0.2 if kind == "python" else 0.005
        plan["kill_after_s"] = round(rng.uniform(0.0, window), 5)
        killer = threading.Timer(plan["kill_after_s"], lambda: process.send_signal(signal.SIGKILL))
        killer.start()
    started = time.monotonic()
    views, wrong, last_sent, error = run_session(client, plan)
    seconds = time.monotonic() - started
    if killer is not None:
        killer.cancel()
    channel.close()
    try:
        exit_code = process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        exit_code = "killed-after-timeout"
    relay = None
    if read_fd is not None:
        with os.fdopen(read_fd) as handle:
            text = handle.read().strip()
            relay = json.loads(text) if text else None
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
            "owner_exit": exit_code,
            "relay": relay,
        }
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
