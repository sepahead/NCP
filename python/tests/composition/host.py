"""The host of the modular-composition test (../test_composition.py): one closed-loop run.

Usage: host.py SEED STEPS OPTIONAL FAULT WORK
OPTIONAL is a comma-separated subset of `monitor` and `recorder` (empty for none). FAULT is
`none` or MODULE:KIND:STEP, passed to the modules (modules.py). WORK is an empty directory for
the transcripts, the recorder's output, and report.json.

In each step t, the host sends the body's sensors to the neural module, turns the neurons that
fired into a command, asks the monitor to check it, if the monitor is present and alive, sends the
command to the body, and publishes a record of the step on a stream to the recorder, if present.
The neural module and the body are required: when one of them fails, the run ends at that step.
The monitor and the recorder are optional: when one of them fails, the run goes on without it.
The report says where the host lost each optional module: the step at which a call failed, for
the monitor, or the step at which a write to the recorder failed, else steps + 1 if the host learned
of the loss only from the recorder's exit status after the run.
Every session is recorded in a transcript. The client's time limit is 1 s.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import ncp  # noqa: E402

sys.path.insert(0, str(HERE))
from modules import CONTRACTS, NEURONS, RECORD_CONTRACT  # noqa: E402

TIME_LIMIT_S = 1.0
# The limit for `open`, which includes the start of the module's process; on a loaded computer, 40
# runs in parallel can take longer than one step's limit to start.
START_LIMIT_S = 30.0
ERRORS = (ncp.CallError,)


def view(error: Exception) -> str:
    if isinstance(error, ncp.Ended):
        return f"ended:{error.code}:{error.executed.value}"
    if isinstance(error, ncp.Declined):
        return f"declined:{error.code}"
    return f"rejected:{getattr(error, 'code', error)}"


def command_of(fired: list[int]) -> list[float]:
    """Forward speed from the first 16 neurons, turn from the difference of the other two eights."""
    forward = sum(1 for i in fired if i < 16) / 16
    turn = (sum(1 for i in fired if 16 <= i < 24) - sum(1 for i in fired if i >= 24)) / 8
    return [forward, turn]


def main() -> None:
    seed, steps, optional, fault, work = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], Path(sys.argv[5])
    optional_set = {name for name in optional.split(",") if name}
    env = dict(os.environ, FAULT="" if fault == "none" else fault, FAULT_STALL_S=str(3 * TIME_LIMIT_S))
    modules = HERE / "modules.py"
    clients: dict[str, ncp.Client] = {}
    processes: dict[str, subprocess.Popen] = {}
    taps: list[ncp.Tap] = []
    for name in ["neural", "body"] + [m for m in ("monitor",) if m in optional_set]:
        tap = ncp.Tap(work / f"{name}.ncpt")
        taps.append(tap)
        # The injected faults log application errors on the module's standard error; keep them
        # out of the gate's output. The channel keeps the last lines in `stderr_tail`.
        channel = ncp.spawn(
            [sys.executable, "-s", str(modules), name, str(seed)], tap=tap, env=env, capture_stderr=True
        )
        client = ncp.Client(channel, CONTRACTS[name], timeout=START_LIMIT_S)
        client.open()
        client.timeout = TIME_LIMIT_S  # each step
        clients[name], processes[name] = client, channel.process
    publisher = recorder = None
    if "recorder" in optional_set:
        recorder = subprocess.Popen(
            [sys.executable, "-s", str(modules), "recorder", str(seed)],
            stdin=subprocess.PIPE,
            env=dict(env, RECORDER_OUT=str(work / "recorder.jsonl")),
            bufsize=0,
        )

        def send(frame: bytes) -> None:
            recorder.stdin.write(frame)  # type: ignore[union-attr]

        publisher = ncp.Publisher("loop", RECORD_CONTRACT.identity, send)
    report: dict = {
        "seed": seed,
        "steps": steps,
        "optional": sorted(optional_set),
        "fault": fault,
        "lost": {},
        "ended": None,
    }
    sensors = [0.5, 0.5, 0.5, 0.5]
    done = 0
    for t in range(1, steps + 1):
        try:
            neural = clients["neural"].call("step", {"t": t, "input": sensors})
        except ERRORS as error:
            report["ended"] = {"module": "neural", "t": t, "view": view(error)}
            break
        fired = neural.body["fired"].tolist()
        command = command_of(fired)
        near_wall = None
        if "monitor" in clients:
            position = [5.0, 5.0] if t == 1 else report["position"]
            try:
                near_wall = (
                    clients["monitor"]
                    .call("check", {"t": t, "position": position, "command": command})
                    .body["near_wall"]
                )
            except ERRORS as error:
                report["lost"]["monitor"] = {"t": t, "view": view(error)}
                del clients["monitor"]
        try:
            body = clients["body"].call("step", {"t": t, "command": command})
        except ERRORS as error:
            report["ended"] = {"module": "body", "t": t, "view": view(error)}
            break
        sensors = body.body["sensors"]
        report["position"] = body.body["position"]
        if publisher is not None:
            try:
                publisher.publish(
                    {
                        "t": t,
                        "fired": len(fired),
                        "command": command,
                        "position": body.body["position"],
                        "near_wall": near_wall,
                    }
                )
            except OSError as error:
                report["lost"]["recorder"] = {"t": t, "view": f"stream:{type(error).__name__}"}
                publisher = None
        done = t
    report["steps_done"] = done
    report["completed"] = done == steps and report["ended"] is None
    for client in clients.values():
        try:
            client.close()
        except ERRORS:
            pass
    if recorder is not None:
        try:
            recorder.stdin.close()  # type: ignore[union-attr]
        except OSError:
            pass
        # A stream has no responses: if no write failed, the host learns of a lost recorder only
        # here, from its exit status. Then "t" is steps + 1: after the last step.
        code = recorder.wait(timeout=30)
        if code != 0 and "recorder" not in report["lost"]:
            report["lost"]["recorder"] = {"t": steps + 1, "view": f"stream:exit {code}"}
    for process in processes.values():
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for tap in taps:
        tap.close()
    report["neurons"] = NEURONS
    (work / "report.json").write_text(json.dumps(report, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
