"""Run one trial of fault-campaign protocol 7 (see ../PROTOCOL-7.md): NCP 2 revision 7 over the Zenoh
binding, with the faults of a network that can lose, repeat, delay, and replay a message, and with
owners that die and restart. Prints one JSON line.

Usage: zenoh_fault7.py SCENARIO SEED OWNER
OWNER: python (bindings/zenoh/python/tests/zenoh_echo_owner.py) or rust (the binding's example
zenoh_echo_owner, RUST_ZENOH_OWNER). The owner runs as its own process and logs every execution
before it runs. The client is the NCP 2 Python client over a ZenohChannel whose `send` and
`receive` apply the faults of the plan drawn from SEED. A session is open, six `echo` steps, and
close: eight requests with seq 0 to 7.

Faults, each applied to the first sending of one request, chosen by its seq:
  drop-query       the query never leaves the client;
  drop-reply       the reply never reaches the client;
  duplicate-query  the query leaves twice;
  delay-reply      the reply reaches the client only after the client's time limit;
  replay-request   after the first sending of request k, the frame of an earlier request j leaves again;
  replay-open      the same with j = 0, the frame of `open`;
  two-faults       two different faults of the six above, on two requests;
  restart-owner    the owner process is killed just before or just after the first sending of request k,
                   and started again with the same service before the client sends anything more;
  kill-owner       the same, and the owner is not started again.
The views, the execution log, and the invariants are those of fault_client6.py.
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
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / "python"), str(ROOT / "bindings" / "zenoh" / "python")]

import ncp  # noqa: E402
import ncp_zenoh  # noqa: E402
import zenoh  # noqa: E402
from fault_client6 import DOCUMENTED, check, executions  # noqa: E402
from ncp import frame as F  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"sleep":{},"spikes":{}},"streams":{}}'
)
STEPS = 6
REQUESTS = STEPS + 2  # open, six steps, close
TIMEOUT_S = 0.5  # the client's time limit for each reply, after which it sends the same frame again
RETRIES = 10
NETWORK = ("drop-query", "drop-reply", "duplicate-query", "delay-reply", "replay-request", "replay-open")
SCENARIOS = NETWORK + ("two-faults", "restart-owner", "kill-owner")


def seq_of(frame: bytes) -> int:
    return F.decode(frame, F.MAX_BOUND).message["seq"]


class FaultChannel(ncp_zenoh.ZenohChannel):
    """A ZenohChannel that applies each fault of `faults` once: {seq: [(kind, j)]}."""

    def __init__(self, session, service: str, faults: dict[int, list[tuple[str, int]]], kill=None) -> None:
        super().__init__(session, service)
        self.faults = faults
        self.kill = kill  # called with "before" or "after" around the first sending of a request
        self.first: dict[int, bytes] = {}
        self.applied: list[str] = []

    def _take(self, seq: int, kinds: tuple[str, ...]) -> tuple[str, int] | None:
        for fault in self.faults.get(seq, []):
            if fault[0] in kinds:
                self.faults[seq].remove(fault)
                self.applied.append(f"{fault[0]}@{seq}")
                return fault
        return None

    def send(self, frame: bytes) -> None:
        seq = seq_of(frame)
        first = seq not in self.first
        self.first.setdefault(seq, frame)
        if first and self._take(seq, ("drop-query",)):
            return
        if first and self._take(seq, ("kill-before",)):
            self.kill()
        super().send(frame)
        if not first:
            return
        if self._take(seq, ("kill-after",)):
            self.kill()
        if self._take(seq, ("duplicate-query",)):
            super().send(frame)
        replay = self._take(seq, ("replay-request", "replay-open"))
        if replay:
            super().send(self.first[replay[1]])

    def receive(self, bound: int, timeout: float | None) -> bytes:
        frame = super().receive(bound, timeout)
        seq = seq_of(frame)
        if self._take(seq, ("drop-reply",)):
            raise TimeoutError("the reply was lost")
        if self._take(seq, ("delay-reply",)):
            # The reply arrives again after the client's time limit, behind the reply to the repeat.
            threading.Timer(1.5 * TIMEOUT_S, self._replies.put, (frame,)).start()
            raise TimeoutError("the reply is late")
        return frame


def owner_command(owner: str, service: str, endpoint: str) -> list[str]:
    if owner == "rust":
        return [os.environ["RUST_ZENOH_OWNER"], service, endpoint]
    return [sys.executable, "-s", str(ROOT / "bindings" / "zenoh" / "python" / "tests" / "zenoh_echo_owner.py"),
            service, endpoint]


def start_owner(command: list[str], env: dict) -> subprocess.Popen:
    """Start an owner; it prints "ready" and serves until its standard input closes."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env,
                               start_new_session=True)
    if process.stdout.readline().strip() != "ready":  # type: ignore[union-attr]
        process.kill()
        raise RuntimeError(f"{command[0]} did not start")
    return process


def stop(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    process.wait()
    for stream in (process.stdin, process.stdout):
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def plan_of(scenario: str, rng: random.Random) -> tuple[dict, dict]:
    """The faults by seq, and their description."""
    def one(kind: str) -> tuple[int, tuple[str, int]]:
        if kind in ("replay-request", "replay-open"):
            k = rng.randrange(1, REQUESTS)
            return k, (kind, 0 if kind == "replay-open" else rng.randrange(0, k))
        return rng.randrange(REQUESTS), (kind, -1)

    faults: dict[int, list[tuple[str, int]]] = {}
    if scenario in NETWORK:
        kinds = [scenario]
    elif scenario == "two-faults":
        kinds = rng.sample(NETWORK, 2)
    else:
        seq, when = rng.randrange(REQUESTS), rng.choice(("before", "after"))
        return {seq: [(f"kill-{when}", -1)]}, {"kill": {"seq": seq, "when": when}}
    described = []
    for kind in kinds:
        seq, fault = one(kind)
        while seq in faults:  # two faults fall on two requests, so that neither hides the other
            seq, fault = one(kind)
        faults[seq] = [fault]
        described.append({"kind": kind, "seq": seq, "replayed": fault[1]})
    return faults, {"faults": described}


def run_session(client: ncp.Client) -> tuple[dict[int, str], int, int | None, str | None]:
    """Open, six echo steps, and close, as fault_client6.run_session with echo steps only."""
    views: dict[int, str] = {}
    wrong, last_sent, error = 0, None, None
    try:
        client.open()
        for k in range(1, STEPS + 1):
            body = {"k": k, "v": [k, k * k], "s": f"step {k}"}
            last_sent = k
            try:
                result = client.call("echo", body)
            except ncp.Declined as caught:
                views[k] = f"declined:{caught.code}"
                raise
            except ncp.Rejected as caught:
                views[k] = f"rejected:{caught.code}"
                raise
            except ncp.Ended as caught:
                views[k] = f"ended:{caught.code}:{caught.executed.value}"
                raise
            if result.body == body:
                views[k] = "ok"
            else:
                views[k] = "wrong"
                wrong += 1
        last_sent = None
        client.close()
        views[STEPS + 1] = "closed"
    except DOCUMENTED as caught:
        error = f"{type(caught).__name__}:{getattr(caught, 'code', '')}"
    except Exception as caught:  # an exception that the SDK documents for no case: report it
        error = f"undocumented:{type(caught).__name__}:{caught}"
    return views, wrong, last_sent, error


def main() -> None:
    scenario, seed, owner = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    rng = random.Random(seed)
    faults, plan = plan_of(scenario, rng)
    work = Path(tempfile.mkdtemp(prefix="ncp7", dir="/tmp"))
    log = work / "executions.jsonl"
    env = dict(os.environ, NCP_EXECUTION_LOG=str(log))
    service = f"fault7-{os.getpid()}-{seed}"
    endpoint = f"tcp/127.0.0.1:{free_port()}"
    command = owner_command(owner, service, endpoint)
    report: dict = {"scenario": scenario, "seed": seed, "owner": owner, "plan": plan}
    process = None
    session = None
    try:
        process = start_owner(command, env)
        config = zenoh.Config()
        config.insert_json5("mode", '"peer"')
        config.insert_json5("scouting/multicast/enabled", "false")
        config.insert_json5("connect/endpoints", json.dumps([endpoint]))
        session = zenoh.open(config)
        restarted = threading.Event()

        def kill() -> None:
            nonlocal process
            stop(process)
            if scenario == "restart-owner":
                process = start_owner(command, env)
                restarted.set()

        channel = FaultChannel(session, service, faults, kill)
        client = ncp.Client(channel, CONTRACT, timeout=TIMEOUT_S, retries=RETRIES)
        started = time.monotonic()
        views, wrong, last_sent, error = run_session(client)
        seconds = time.monotonic() - started
        time.sleep(1.5 * TIMEOUT_S)  # a late reply or a replayed frame can still execute nothing
        stop(process)
        process = None
        executed = executions(log)
        steps = {k: v for k, v in views.items() if 1 <= k <= STEPS}
        completed = error is None and len(steps) == STEPS and all(v == "ok" for v in steps.values())
        report.update({
            "views": {str(k): v for k, v in sorted(views.items())},
            "error": error,
            "completed": completed,
            "wrong_accepted": wrong,
            "executed": executed,
            "invariants": check(steps, executed, last_sent),
            "applied": channel.applied,
            "unapplied": sorted(f"{kind}@{seq}" for seq, items in channel.faults.items() for kind, _ in items),
            "restarted": restarted.is_set(),
            "seconds": round(seconds, 4),
        })
        print(json.dumps(report))
    finally:
        stop(process)
        if session is not None:
            session.close()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
