#!/usr/bin/env python3
"""Run the fault campaign (see PROTOCOL.md). Resumable and safe to interrupt.

Usage: run.py RESULTS_DIR --prefix CONDA_PREFIX [--smoke]
Writes RESULTS_DIR/schedule.json once: three blocks; each block holds every trial of
the trial plan in an order shuffled with a fixed seed. Each finished trial is appended
to RESULTS_DIR/trials.jsonl and synced to disk; a later call skips finished trials.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261026
BLOCKS = 3
# (scenario, owner, trials per block)
PLAN = [(f"{mode}-{direction}", owner, count) for mode, count in (("flip", 200), ("truncate", 60))
        for direction in ("c2o", "o2c") for owner in ("python", "rust")]
PLAN += [("kill-owner", "python", 40), ("kill-owner", "rust", 40), ("kill-client", "python", 40),
         ("stall", "python", 10), ("oversize-response", "python", 20), ("oversize-request", "python", 20),
         ("oversize-request", "rust", 20), ("backend-raise", "python", 20), ("nest-raise", "nest", 10),
         ("nest-kill", "nest", 10), ("soak", "rust", 1), ("soak", "python", 1)]
SOAK_CALLS = {"rust": 300_000, "python": 60_000}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_rust(work: Path) -> Path:
    source = ROOT / "benchmarks/pipelined-ack/harness/rust"
    project = work / "harness"
    shutil.rmtree(project, ignore_errors=True)
    shutil.copytree(source / "src", project / "src")
    (project / "Cargo.toml").write_text((source / "Cargo.toml.in").read_text()
                                        .replace("@NCP_LOCAL@", str(ROOT / "local/rust")))
    subprocess.run(["cargo", "build", "--release", "--offline", "--quiet", "--manifest-path",
                    str(project / "Cargo.toml")], check=True, env=dict(os.environ, CARGO_TARGET_DIR=str(work / "t")))
    return work / "t/release/ncp-local-exchange-bench"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    rust = build_rust(args.results / ".work")
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(SEED)
        order = []
        for block in range(1 if args.smoke else BLOCKS):
            trials = []
            for scenario, owner, count in PLAN:
                for index in range(1 if args.smoke else count):
                    trials.append({"block": block, "scenario": scenario, "owner": owner,
                                   "seed": SEED + 100_000 * block + 1000 * len(trials) + index})
            rng.shuffle(trials)
            order += trials
        for number, trial in enumerate(order):
            trial["id"] = number
        schedule_path.write_text(json.dumps({
            "protocol_sha256": hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest(),
            "seed": SEED, "smoke": args.smoke, "created_utc": now(),
            "commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                                     text=True).stdout.strip(),
            "order": order}, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    trials_path = args.results / "trials.jsonl"
    done = set()
    if trials_path.exists():
        done = {json.loads(line)["id"] for line in trials_path.read_text().splitlines() if line.strip()}
    py = str(args.prefix / "bin/python")
    harness = HERE / "harness"
    env = dict(os.environ, RUST_OWNER=str(rust), RUST_HARNESS=str(rust),
               PIPELINED_HARNESS_PY=str(ROOT / "benchmarks/pipelined-ack/harness/python"),
               NEST_CAMPAIGN_HARNESS=str(ROOT / "benchmarks/nest-campaign/harness"),
               PATH=f"{args.prefix}/bin:/usr/bin:/bin:/usr/sbin:/sbin", PYNEST_QUIET="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONPATH=os.pathsep.join([str(ROOT / "benchmarks/nest-campaign/harness"),
                                           str(ROOT / "benchmarks/pipelined-ack/harness/python"),
                                           str(ROOT / "local/python")]))
    for trial in schedule["order"]:
        if trial["id"] in done:
            continue
        scenario, owner, seed = trial["scenario"], trial["owner"], str(trial["seed"])
        if scenario == "soak":
            command = [py, "-s", str(harness / "soak.py"), owner, str(SOAK_CALLS[owner])]
        elif scenario.startswith("nest-"):
            command = [py, "-s", str(harness / "nest_fault.py"), scenario, seed]
        else:
            command = [py, "-s", str(harness / "fault_client.py"), scenario, seed, owner]
        started = now()
        try:
            process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=600)
            result = json.loads(process.stdout.strip().splitlines()[-1]) if process.returncode == 0 else {}
            returncode = process.returncode
            tail = process.stderr.strip().splitlines()[-3:] if process.returncode else []
        except subprocess.TimeoutExpired:
            result, returncode, tail = {}, "timeout", []
        row = {"id": trial["id"], "block": trial["block"], "scenario": scenario, "owner": owner,
               "seed": trial["seed"], "started_utc": started, "finished_utc": now(), "returncode": returncode,
               "stderr_tail": tail, "result": result}
        with trials_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    shutil.rmtree(args.results / ".work", ignore_errors=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
