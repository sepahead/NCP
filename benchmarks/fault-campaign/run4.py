#!/usr/bin/env python3
"""Run protocol 4 or 5 of the fault campaign, for NCP 2 over sockets and with the Rust client
(see PROTOCOL-4.md and PROTOCOL-5.md). Resumable and safe to interrupt.

Usage: run4.py RESULTS_DIR [--protocol 4|5] [--smoke]
Protocol 5 is protocol 4 with the corrected cleanup of harness/fault_client4.py and its own seed.
Writes RESULTS_DIR/schedule.json once: three blocks; each block holds every trial of the plan
in an order shuffled with a fixed seed. Each finished trial is appended to
RESULTS_DIR/trials.jsonl and synced to disk; a later call skips finished trials. The NCP 2 Rust
examples and the Rust fault client are built into RESULTS_DIR/.work with cargo.
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
PROTOCOL = "PROTOCOL-4.md"
SEED = 20261105
# Protocol: its file and the seed of the order of its blocks.
PROTOCOLS = {"4": ("PROTOCOL-4.md", 20261105), "5": ("PROTOCOL-5.md", 20261109)}
BLOCKS = 3
BINDINGS = ("unix", "tcp")
CLIENTS = ("python", "rust")
OWNERS = ("python", "rust")
# (scenario, owners, trials per block for each binding, client, and owner)
SCENARIOS = [
    ("flip-c2o", OWNERS, 40),
    ("flip-o2c", OWNERS, 40),
    ("truncate-c2o", OWNERS, 15),
    ("truncate-o2c", OWNERS, 15),
    ("duplicate-c2o", OWNERS, 10),
    ("duplicate-o2c", OWNERS, 10),
    ("kill-owner", OWNERS, 20),
    ("kill-client", OWNERS, 10),
    ("oversize-request", OWNERS, 10),
    ("backend-raise", OWNERS, 10),
    ("stall", ("python",), 10),
    ("oversize-response", ("python",), 10),
]
PLAN = [
    (scenario, owner, binding, client, count)
    for scenario, owners, count in SCENARIOS
    for owner in owners
    for binding in BINDINGS
    for client in CLIENTS
]
TRIAL_LIMIT_S = 120


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command: list[str]) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True).stdout.strip()


def build(work: Path) -> dict[str, Path]:
    """Build the NCP 2 Rust examples and the Rust fault client of this commit. Each binary runs
    once before the trials: macOS checks a new binary at its first start, which can take seconds."""
    env = dict(os.environ, CARGO_TARGET_DIR=str(work / "target"))
    subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--locked",
            "--quiet",
            "--examples",
            "--manifest-path",
            str(ROOT / "rust" / "Cargo.toml"),
        ],
        check=True,
        env=env,
    )
    subprocess.run(
        [
            "cargo",
            "build",
            "--release",
            "--locked",
            "--quiet",
            "--manifest-path",
            str(HERE / "harness" / "rust-client" / "Cargo.toml"),
        ],
        check=True,
        env=dict(os.environ, CARGO_TARGET_DIR=str(work / "client-target")),
    )
    examples = work / "target" / "release" / "examples"
    client = work / "client-target" / "release" / "fault-client"
    subprocess.run(
        [str(examples / "bench_client"), "10", "0", "0", "--", str(examples / "echo_owner")],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(client)], capture_output=True)  # no arguments: it stops at once
    return {"owner": examples / "echo_owner", "client": client}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default="4")
    parser.add_argument("--smoke", action="store_true", help="one trial of each scenario and combination")
    args = parser.parse_args()
    global PROTOCOL, SEED
    PROTOCOL, SEED = PROTOCOLS[args.protocol]
    args.results.mkdir(parents=True, exist_ok=True)
    binaries = build(args.results / ".work")
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(SEED)
        order = []
        for block in range(1 if args.smoke else BLOCKS):
            entries = [
                {"scenario": scenario, "owner": owner, "binding": binding, "client": client}
                for scenario, owner, binding, client, count in PLAN
                for _ in range(1 if args.smoke else count)
            ]
            rng.shuffle(entries)
            order += [dict(entry, block=block, index=i, seed=rng.randrange(2**31)) for i, entry in enumerate(entries)]
        schedule = {
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
        }
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    if schedule["protocol"] != PROTOCOL:
        sys.exit(f"{schedule_path} belongs to {schedule['protocol']}")
    trials_path = args.results / "trials.jsonl"
    done = set()
    if trials_path.exists():
        done = {(row["block"], row["index"]) for row in map(json.loads, trials_path.read_text().splitlines()) if row}
    env = dict(
        os.environ,
        RUST_OWNER=str(binaries["owner"]),
        RUST_FAULT_CLIENT=str(binaries["client"]),
        PYTHONDONTWRITEBYTECODE="1",
    )
    for position, entry in enumerate(schedule["order"]):
        if (entry["block"], entry["index"]) in done:
            continue
        load = round(os.getloadavg()[0], 2)
        started = now()
        command = [
            sys.executable,
            "-s",
            str(HERE / "harness" / "fault_client4.py"),
            entry["scenario"],
            str(entry["seed"]),
            entry["owner"],
            entry["binding"],
            entry["client"],
        ]
        try:
            process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=TRIAL_LIMIT_S)
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
        summary = result.get("error") if "error" in result else result.get("owner_served_again", code)
        label = f"{entry['scenario']} {entry['owner']} owner, {entry['client']} client, {entry['binding']}"
        print(f"[{position + 1}/{len(schedule['order'])}] {label}: {summary}", flush=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
