"""The modular-composition test of NCP 2 (design record, section 7): stand-in neural, body,
monitor, and recorder modules in a closed loop (composition/host.py, composition/modules.py).

The host runs the loop with every subset of the optional modules, the monitor and the
recorder, without a fault and with a fault in each module present: the module kills itself
after a change of state, stalls past the client's time limit, or raises. The test checks that

- a fault in a required module, the neural module or the body, ends the run at its step, with
  the outcome that the specification gives (executed `unknown`), and no later step runs;
- a fault in an optional module never stops the loop, and the host reports where it lost it;
- every transcript verifies, except that the request at which a module was killed or stalled
  has no response;
- the recorder received an unbroken chain of every step that it acknowledged;
- two runs with the same seed give the same message bodies;
- the optional modules do not change the bodies of the neural module and the body; and
- a run with a fault has, before the fault, the bodies of the run without it.

Standard library and the NCP 2 Python SDK only. The 40 runs take about half a minute.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ncp  # noqa: E402

SEED = 20261103
STEPS = 40
SUBSETS = ("", "monitor", "recorder", "monitor,recorder")
EXPECTED = {"kill": "ended:closed:unknown", "stall": "ended:timeout:unknown", "raise": "ended:owner_failure:unknown"}


def plan() -> list[tuple[str, str]]:
    """(optional modules, fault) of every run. Each fault falls on a step drawn from its name."""
    runs = []
    for subset in SUBSETS:
        runs += [(subset, "none"), (subset, "none")]
        modules = ["neural", "body"] + [m for m in subset.split(",") if m]
        for module in modules:
            for kind in ("kill",) if module == "recorder" else ("kill", "stall", "raise"):
                step = random.Random(f"{subset}/{module}/{kind}").randrange(3, STEPS - 2)
                runs.append((subset, f"{module}:{kind}:{step}"))
    return runs


def bodies(path: Path) -> list[str]:
    """The bodies of a transcript's frames, in order, with arrays as lists."""

    def plain(value):
        if isinstance(value, ncp.Array):
            return {"array": value.dtype, "values": value.tolist()}
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [plain(v) for v in value]
        return value

    out = []
    for record in ncp.transcript.read(path):
        decoded = ncp.decode(record.frame, ncp.MAX_BOUND)
        message = decoded.message
        if message.get("op") in ("open", "close") or message.get("body") == {}:
            continue
        out.append(json.dumps(plain(message["body"]), sort_keys=True))
    return out


class CompositionTests(unittest.TestCase):
    runs: dict[int, dict] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(tempfile.mkdtemp(prefix="ncp-composition-"))
        cls.plan = plan()

        def run(index: int) -> dict:
            subset, fault = cls.plan[index]
            work = cls.root / str(index)
            work.mkdir()
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            command = [
                sys.executable,
                "-s",
                str(HERE / "composition" / "host.py"),
                str(SEED),
                str(STEPS),
                subset,
                fault,
                str(work),
            ]
            subprocess.run(command, check=True, timeout=120, env=env)
            report = json.loads((work / "report.json").read_text())
            report["work"] = work
            return report

        with ThreadPoolExecutor(max_workers=8) as pool:
            cls.runs = dict(enumerate(pool.map(run, range(len(cls.plan)))))

    def each(self, kind: str):
        for index, (subset, fault) in enumerate(self.plan):
            if (fault == "none") == (kind == "none"):
                yield index, subset, fault, self.runs[index]

    def test_a_fault_in_a_required_module_ends_the_run_at_its_step(self) -> None:
        seen = 0
        for _, subset, fault, report in self.each("fault"):
            module, kind, step = fault.split(":")
            if module not in ("neural", "body"):
                continue
            seen += 1
            with self.subTest(subset=subset, fault=fault):
                self.assertEqual(report["ended"], {"module": module, "t": int(step), "view": EXPECTED[kind]})
                self.assertEqual(report["steps_done"], int(step) - 1)
                self.assertFalse(report["completed"])
        self.assertEqual(seen, 4 * 6)

    def test_a_fault_in_an_optional_module_never_stops_the_loop(self) -> None:
        seen = 0
        for _, subset, fault, report in self.each("fault"):
            module, kind, step = fault.split(":")
            if module not in ("monitor", "recorder"):
                continue
            seen += 1
            with self.subTest(subset=subset, fault=fault):
                self.assertTrue(report["completed"])
                lost = report["lost"][module]
                if module == "monitor":
                    self.assertEqual(lost, {"t": int(step), "view": EXPECTED[kind]})
                else:  # a stream has no response: the host learns of the loss at a later write or at the end
                    self.assertGreaterEqual(lost["t"], int(step))
                    self.assertLessEqual(lost["t"], STEPS + 1)
                    lines = (report["work"] / "recorder.jsonl").read_text().splitlines()
                    self.assertEqual([json.loads(line)["t"] for line in lines], list(range(1, int(step))))
        self.assertEqual(seen, 2 * 3 + 2 * 1)

    def test_runs_without_a_fault_complete_and_the_recorder_receives_every_step(self) -> None:
        for _, subset, _, report in self.each("none"):
            with self.subTest(subset=subset):
                self.assertTrue(report["completed"])
                self.assertEqual(report["lost"], {})
                if "recorder" in subset:
                    summary = json.loads((report["work"] / "recorder.summary").read_text())
                    self.assertEqual(summary, {"accepted": STEPS, "problems": []})

    def test_every_transcript_verifies(self) -> None:
        for _, subset, fault, report in self.each("none"):
            for path in report["work"].glob("*.ncpt"):
                with self.subTest(subset=subset, fault=fault, transcript=path.name):
                    sessions = ncp.verify_transcript(path)
                    self.assertTrue(all(s.complete and not s.problems for s in sessions.values()), sessions)
        for _, subset, fault, report in self.each("fault"):
            module, kind, step = fault.split(":")
            for path in report["work"].glob("*.ncpt"):
                with self.subTest(subset=subset, fault=fault, transcript=path.name):
                    (session,) = ncp.verify_transcript(path).values()
                    unanswered = path.stem == module and kind in ("kill", "stall")
                    self.assertEqual(session.problems, [f"seq {step}: no response"] if unanswered else [])

    def test_the_same_seed_gives_the_same_bodies(self) -> None:
        for subset in SUBSETS:
            first, second = [r for _, s, _, r in self.each("none") if s == subset]
            for name in ("neural", "body", "monitor"):
                path = first["work"] / f"{name}.ncpt"
                if path.exists():
                    with self.subTest(subset=subset, module=name):
                        self.assertEqual(bodies(path), bodies(second["work"] / f"{name}.ncpt"))

    def test_optional_modules_do_not_change_the_loop(self) -> None:
        reference = next(r for _, s, _, r in self.each("none") if s == "")
        for _, subset, _, report in self.each("none"):
            for name in ("neural", "body"):
                with self.subTest(subset=subset, module=name):
                    self.assertEqual(
                        bodies(report["work"] / f"{name}.ncpt"), bodies(reference["work"] / f"{name}.ncpt")
                    )

    def test_a_fault_leaves_the_steps_before_it_unchanged(self) -> None:
        reference = next(r for _, s, _, r in self.each("none") if s == "")
        for _, subset, fault, report in self.each("fault"):
            step = int(fault.split(":")[2])
            for name in ("neural", "body"):
                with self.subTest(subset=subset, fault=fault, module=name):
                    before = 2 * (step - 1)  # a request and a response for each earlier step
                    got = bodies(report["work"] / f"{name}.ncpt")[:before]
                    self.assertEqual(got, bodies(reference["work"] / f"{name}.ncpt")[:before])


if __name__ == "__main__":
    unittest.main()
