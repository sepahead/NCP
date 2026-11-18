#!/usr/bin/env python3
"""Run fault-campaign protocol 7, NCP 2 revision 7 over the Zenoh binding (see PROTOCOL-7.md).
Resumable and safe to interrupt.

Usage: run7.py RESULTS_DIR [--smoke]
Writes RESULTS_DIR/schedule.json once: three blocks; each block holds every trial of the plan in an
order shuffled with a fixed seed. Each finished trial is appended to RESULTS_DIR/trials.jsonl and
synced to disk; a later call skips finished trials. The Rust Zenoh owner is built into
RESULTS_DIR/.work with cargo.
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
sys.path.insert(0, str(HERE / "harness"))
from zenoh_fault7 import NETWORK  # noqa: E402

PROTOCOL = "PROTOCOL-7.md"
SEED = 20261119
BLOCKS = 3
OWNERS = ("python", "rust")
# (scenario, trials per block for each owner)
SCENARIOS = [(name, 20) for name in NETWORK] + [("two-faults", 20), ("restart-owner", 10), ("kill-owner", 10)]
TRIAL_LIMIT_S = 120


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--smoke", action="store_true", help="one trial of each scenario and owner")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    target = args.results / ".work" / "target"
    subprocess.run(["cargo", "build", "--release", "--locked", "--quiet", "--examples", "--manifest-path",
                    str(ROOT / "bindings" / "zenoh" / "rust" / "Cargo.toml")],
                   check=True, env=dict(os.environ, CARGO_TARGET_DIR=str(target)))
    owner = target / "release" / "examples" / "zenoh_echo_owner"
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(SEED)
        order = []
        for block in range(1 if args.smoke else BLOCKS):
            entries = [{"scenario": scenario, "owner": who}
                       for scenario, count in SCENARIOS for who in OWNERS for _ in range(1 if args.smoke else count)]
            rng.shuffle(entries)
            order += [dict(entry, block=block, index=i, seed=rng.randrange(2**31)) for i, entry in enumerate(entries)]
        schedule_path.write_text(json.dumps({
            "protocol": PROTOCOL,
            "protocol_sha256": hashlib.sha256((HERE / PROTOCOL).read_bytes()).hexdigest(),
            "seed": SEED,
            "smoke": args.smoke,
            "commit": out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "worktree_clean": out(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
            "python": sys.version.split()[0],
            "rustc": out(["rustc", "--version"]),
            "power": out(["pmset", "-g", "batt"]).splitlines()[0],
            "created_utc": now(),
            "order": order,
        }, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    trials_path = args.results / "trials.jsonl"
    done = set()
    if trials_path.exists():
        done = {(row["block"], row["index"]) for row in map(json.loads, trials_path.read_text().splitlines()) if row}
    env = dict(os.environ, RUST_ZENOH_OWNER=str(owner), PYTHONDONTWRITEBYTECODE="1")
    for position, entry in enumerate(schedule["order"]):
        if (entry["block"], entry["index"]) in done:
            continue
        load, started = round(os.getloadavg()[0], 2), now()
        command = [sys.executable, "-s", str(HERE / "harness" / "zenoh_fault7.py"), entry["scenario"],
                   str(entry["seed"]), entry["owner"]]
        try:
            process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=TRIAL_LIMIT_S,
                                     stdin=subprocess.DEVNULL)
            code, stdout, stderr = process.returncode, process.stdout, process.stderr
        except subprocess.TimeoutExpired as expired:
            code, stdout, stderr = "timeout", "", str(expired)
        row = {**entry, "load1_before": load, "started_utc": started, "finished_utc": now(), "returncode": code}
        lines = stdout.strip().splitlines()
        if code == 0 and lines:
            row["result"] = json.loads(lines[-1])
        else:
            row["stderr_tail"] = (stderr or "").strip().splitlines()[-6:]
        with trials_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        result = row.get("result", {})
        print(f"[{position + 1}/{len(schedule['order'])}] {entry['scenario']} {entry['owner']} owner: "
              f"{result.get('error')} {result.get('applied')}", flush=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
