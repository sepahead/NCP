#!/usr/bin/env python3
"""Run the bounded soaks (see PROTOCOL-SOAK.md). Resumable.

Usage: soak_run.py RESULTS_DIR --prefix CONDA_PREFIX
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
from pathlib import Path

import run as campaign

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261027
CALLS = {"rust": 1_000_000, "python": 200_000}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--prefix", type=Path, required=True)
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    rust = campaign.build_rust(args.results / ".work")
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(SEED)
        order = []
        for block in range(3):
            kinds = ["rust", "python"]
            rng.shuffle(kinds)
            order += [{"block": block, "kind": kind, "id": len(order) + i} for i, kind in enumerate(kinds)]
        schedule_path.write_text(json.dumps({
            "protocol_sha256": hashlib.sha256((HERE / "PROTOCOL-SOAK.md").read_bytes()).hexdigest(),
            "seed": SEED, "created_utc": now(), "order": order}, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    path = args.results / "trials.jsonl"
    done = {json.loads(line)["id"] for line in path.read_text().splitlines() if line.strip()} if path.exists() else set()
    env = dict(os.environ, RUST_HARNESS=str(rust),
               PIPELINED_HARNESS_PY=str(ROOT / "benchmarks/pipelined-ack/harness/python"),
               PYTHONPATH=f"{ROOT / 'benchmarks/pipelined-ack/harness/python'}{os.pathsep}{ROOT / 'local/python'}",
               PYTHONDONTWRITEBYTECODE="1")
    for entry in schedule["order"]:
        if entry["id"] in done:
            continue
        started = now()
        process = subprocess.run([str(args.prefix / "bin/python"), "-s", str(HERE / "harness/soak_bounded.py"),
                                  entry["kind"], str(CALLS[entry["kind"]])], capture_output=True, text=True,
                                 env=env, timeout=3600)
        row = {**entry, "started_utc": started, "finished_utc": now(), "returncode": process.returncode,
               "result": json.loads(process.stdout.strip().splitlines()[-1]) if process.returncode == 0 else {}}
        with path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    shutil.rmtree(args.results / ".work", ignore_errors=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
