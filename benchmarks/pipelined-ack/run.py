#!/usr/bin/env python3
"""Run the pipelined-acknowledgement benchmark (see PROTOCOL.md). Resumable.

Usage: run.py RESULTS_DIR --python PYTHON [--smoke]

The first call writes RESULTS_DIR/schedule.json: three blocks, each with every
configuration once, in an order shuffled with a fixed seed. Each finished run is
appended to RESULTS_DIR/runs.jsonl and synced to disk. A later call with the same
directory skips the runs that are already recorded, so a lost session or a reboot
loses at most the run in progress. Validity checks run before the timed runs and
are recorded in RESULTS_DIR/validity.json. Standard library only; needs cargo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261023
BLOCKS, CALLS, WARMUP = 3, 3000, 500
SIZES = (0, 127)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command: list[str], **kwargs) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs).stdout.strip()


def build(work: Path) -> Path:
    project = work / "harness"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(HERE / "harness" / "rust" / "src", project / "src")
    template = (HERE / "harness" / "rust" / "Cargo.toml.in").read_text()
    (project / "Cargo.toml").write_text(template.replace("@NCP_LOCAL@", str(ROOT / "local/rust")))
    env = dict(os.environ, CARGO_TARGET_DIR=str(work / "target"))
    subprocess.run(["cargo", "build", "--release", "--offline", "--quiet", "--manifest-path",
                    str(project / "Cargo.toml")], check=True, env=env)
    return work / "target" / "release" / "ncp-local-exchange-bench"


def configurations(python: str, binary: Path) -> list[dict]:
    harness = HERE / "harness" / "python"
    py_owner = [python, "-s", str(harness / "owner.py")]
    rust_owner = [str(binary), "owner"]
    configs = []
    for n in SIZES:
        for mode in ("sequential", "pipelined"):
            configs.append({"name": f"rust-rust-{mode}-n{n}", "command": [str(binary), mode, str(n)],
                            "owner": rust_owner})
            configs.append({"name": f"rust-python-{mode}-n{n}", "command": [str(binary), mode, str(n)],
                            "owner": py_owner})
        for mode in ("sdk", "sequential", "pipelined"):
            client = [python, "-s", str(harness / "client.py"), mode, str(n)]
            configs.append({"name": f"python-python-{mode}-n{n}", "command": client, "owner": py_owner})
            configs.append({"name": f"python-rust-{mode}-n{n}", "command": client, "owner": rust_owner})
    return configs


def validity(python: str) -> dict:
    model = HERE / "model"
    env = dict(os.environ, PYTHONPATH=f"{ROOT / 'local/python'}{os.pathsep}{model}", PYTHONDONTWRITEBYTECODE="1")
    record = {}
    work = Path(os.environ.get("TMPDIR", "/tmp"))
    for name, command in (
        ("model_check", [python, "-s", str(model / "model_check.py"), "--steps", "4", "--faults", "2"]),
        ("model_check_faults3", [python, "-s", str(model / "model_check.py"), "--steps", "3", "--faults", "3"]),
        ("mutation_self_test", [python, "-s", str(model / "model_check.py"), "--self-test"]),
        ("conformance", [python, "-s", str(model / "conformance.py"), "--traces", "20000", "--seed", "7"]),
    ):
        report = work / f"pipelined-{name}.json"
        if name.startswith("model_check"):
            command = command + ["--json", str(report)]
        process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=model)
        entry = {"returncode": process.returncode, "stdout": process.stdout.strip().splitlines()}
        if name.startswith("model_check") and process.returncode == 0:
            # Required verdicts: v1 clients clean; the pipelined client breaks only the v1 client rule.
            verdicts = {row["variant"]: sorted(row["violations"]) for row in json.loads(report.read_text())}
            entry["verdicts"] = verdicts
            if verdicts != {"sequential": [], "deferred": [], "pipelined": ["P6"]}:
                entry["returncode"] = 1
        record[name] = entry
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    blocks, calls, warmup = (1, 200, 50) if args.smoke else (BLOCKS, CALLS, WARMUP)
    args.results.mkdir(parents=True, exist_ok=True)
    work = args.results / ".work"
    work.mkdir(exist_ok=True)
    binary = build(work)
    configs = {config["name"]: config for config in configurations(args.python, binary)}
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(SEED)
        order = []
        for block in range(blocks):
            names = sorted(configs)
            rng.shuffle(names)
            order += [{"block": block, "config": name} for name in names]
        schedule = {"protocol_sha256": hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest(),
                    "seed": SEED, "blocks": blocks, "calls": calls, "warmup": warmup, "smoke": args.smoke,
                    "commit": out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]), "created_utc": now(),
                    "order": order}
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
        validity_record = validity(args.python)
        validity_record["environment"] = {
            "computer": out(["sysctl", "-n", "hw.model"]), "chip": out(["sysctl", "-n", "machdep.cpu.brand_string"]),
            "os": out(["sw_vers", "-productVersion"]), "kernel": platform.release(),
            "rustc": out(["rustc", "--version"]),
            "python_endpoints": out([args.python, "-c", "import sys; print(sys.version.split()[0])"]),
            "power": out(["pmset", "-g", "batt"]).splitlines()[0]}
        (args.results / "validity.json").write_text(json.dumps(validity_record, indent=1) + "\n")
        if any(entry["returncode"] != 0 for key, entry in validity_record.items() if key != "environment"):
            sys.exit("a validity check failed; no timed runs")
    schedule = json.loads(schedule_path.read_text())
    runs_path = args.results / "runs.jsonl"
    done = set()
    if runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done.add((row["block"], row["config"]))
    for entry in schedule["order"]:
        key = (entry["block"], entry["config"])
        if key in done:
            continue
        config = configs[entry["config"]]
        command = config["command"] + [str(schedule["calls"]), str(schedule["warmup"])] + config["owner"]
        env = dict(os.environ, PYTHONPATH=f"{ROOT / 'local/python'}{os.pathsep}{HERE / 'harness/python'}",
                   PYTHONDONTWRITEBYTECODE="1")
        load = os.getloadavg()[0]
        started = now()
        process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=HERE)
        result = json.loads(process.stdout.strip().splitlines()[-1]) if process.returncode == 0 else {}
        row = {"block": entry["block"], "config": entry["config"], "returncode": process.returncode,
               "load1_before": round(load, 2), "started_utc": started, "finished_utc": now(),
               "stderr_tail": process.stderr.strip().splitlines()[-3:], **result}
        with runs_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(f"block {entry['block']} {entry['config']}: {row.get('timing', {}).get('median_us', 'failed')}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    print("complete")


if __name__ == "__main__":
    main()
