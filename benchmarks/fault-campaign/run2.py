#!/usr/bin/env python3
"""Run protocol 2 or 3 of the fault campaign, for NCP 2 (see PROTOCOL-2.md and PROTOCOL-3.md).
Resumable and safe to interrupt.

Usage: run2.py RESULTS_DIR [--protocol 2|3] [--smoke]
Writes RESULTS_DIR/schedule.json once: three blocks; each block holds every trial of the plan
in an order shuffled with a fixed seed. Each finished trial is appended to
RESULTS_DIR/trials.jsonl and synced to disk; a later call skips finished trials. The NCP 2 Rust
examples are built into RESULTS_DIR/.work with cargo.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# Protocol: its file and the seed of the order of its blocks. Protocol 3 differs from protocol 2
# in the harness (the relay's own seed) and in the analysis of the soaks.
PROTOCOLS = {"2": ("PROTOCOL-2.md", 20261103), "3": ("PROTOCOL-3.md", 20261104)}
BLOCKS = 3
# (scenario, owner, trials per block)
PLAN = [
    (f"{mode}-{direction}", owner, count)
    for mode, count in (("flip", 200), ("truncate", 60), ("duplicate", 30))
    for direction in ("c2o", "o2c")
    for owner in ("python", "rust")
]
PLAN += [(scenario, owner, count) for scenario, count in (("kill-owner", 40), ("kill-client", 20)) for owner in ("python", "rust")]
PLAN += [("stall", "python", 10), ("oversize-response", "python", 20)]
PLAN += [(scenario, owner, 20) for scenario in ("oversize-request", "backend-raise") for owner in ("python", "rust")]
PLAN += [("soak", kind, 1) for kind in ("python-python", "python-rust", "rust-rust")]
SOAK_CALLS = {"python-python": 200_000, "python-rust": 1_000_000, "rust-rust": 1_000_000}
TRIAL_LIMIT_S = 120
SOAK_LIMIT_S = 1800


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def build(work: Path) -> Path:
    """Build the NCP 2 Rust examples of this commit and return their directory. One short session
    runs each binary once: macOS checks a new binary at its first start, which can take seconds."""
    subprocess.run(
        ["cargo", "build", "--release", "--locked", "--quiet", "--examples", "--manifest-path", str(ROOT / "rust" / "Cargo.toml")],
        check=True,
        env=dict(os.environ, CARGO_TARGET_DIR=str(work / "target")),
    )
    examples = work / "target" / "release" / "examples"
    subprocess.run([str(examples / "bench_client"), "10", "0", "0", "--", str(examples / "echo_owner")], check=True, capture_output=True)
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default="2")
    parser.add_argument("--smoke", action="store_true", help="one trial of each scenario and owner, short soaks")
    args = parser.parse_args()
    protocol, seed = PROTOCOLS[args.protocol]
    args.results.mkdir(parents=True, exist_ok=True)
    examples = build(args.results / ".work")
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(seed)
        order = []
        for block in range(1 if args.smoke else BLOCKS):
            entries = [
                {"scenario": scenario, "owner": owner}
                for scenario, owner, count in PLAN
                for _ in range(1 if args.smoke else count)
            ]
            rng.shuffle(entries)
            order += [dict(entry, block=block, index=i, seed=rng.randrange(2**31)) for i, entry in enumerate(entries)]
        schedule = {
            "protocol": protocol,
            "protocol_sha256": hashlib.sha256((HERE / protocol).read_bytes()).hexdigest(),
            "seed": seed,
            "smoke": args.smoke,
            "commit": out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "worktree_clean": out(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
            "python": sys.version.split()[0],
            "rustc": out(["rustc", "--version"]),
            "created_utc": now(),
            "order": order,
        }
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    if schedule["protocol"] != protocol:
        sys.exit(f"{schedule_path} belongs to {schedule['protocol']}")
    trials_path = args.results / "trials.jsonl"
    done = set()
    if trials_path.exists():
        done = {
            (row["block"], row["index"]) for row in map(json.loads, trials_path.read_text().splitlines()) if row
        }
    env = dict(
        os.environ,
        RUST_OWNER=str(examples / "echo_owner"),
        RUST_CLIENT=str(examples / "bench_client"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for position, entry in enumerate(schedule["order"]):
        if (entry["block"], entry["index"]) in done:
            continue
        load = round(os.getloadavg()[0], 2)
        started = now()
        if entry["scenario"] == "soak":
            calls = 20_000 if schedule["smoke"] else SOAK_CALLS[entry["owner"]]
            command = [sys.executable, "-s", str(HERE / "harness" / "soak2.py"), entry["owner"], str(calls)]
            limit = SOAK_LIMIT_S
        else:
            command = [sys.executable, "-s", str(HERE / "harness" / "fault_client2.py"), entry["scenario"], str(entry["seed"]), entry["owner"]]
            limit = TRIAL_LIMIT_S
        try:
            process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=limit)
            code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as expired:
            code, stdout, stderr = "timeout", "", str(expired)
        row = {**entry, "load1_before": load, "started_utc": started, "finished_utc": now(), "returncode": code}
        lines = stdout.strip().splitlines()
        if code == 0 and lines:
            row["result"] = json.loads(lines[-1])
        else:
            row["stderr_tail"] = stderr.strip().splitlines()[-6:]
        with trials_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        result = row.get("result", {})
        summary = result.get("error") if "error" in result else result.get("owner_exited", code)
        print(f"[{position + 1}/{len(schedule['order'])}] {entry['scenario']} {entry['owner']}: {summary}", flush=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
