#!/usr/bin/env python3
"""Run the content campaign (see PROTOCOL-CONTENT.md). Resumable and safe to interrupt.

Usage: content_run.py RESULTS_DIR --prefix CONDA_PREFIX [--protocol 1|2] [--smoke]
Three blocks, each with every configuration once in a shuffled order; each finished
trial is appended to RESULTS_DIR/trials.jsonl and synced to disk.
Protocol 1 (PROTOCOL-CONTENT.md) checks NCP 1.0.1 and MUSIC; protocol 2 (PROTOCOL-CONTENT-2.md)
checks the NCP 2 Python and Rust hosts and adds Brunel with 10,000 neurons.
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
SEED = 20261025
BLOCKS = 3
# Protocol: its file, its harness, and the seed of the order of each block.
PROTOCOLS = {
    "1": ("PROTOCOL-CONTENT.md", "content.py", SEED),
    "2": ("PROTOCOL-CONTENT-2.md", "content2.py", 20261102),
}


def configurations(protocol: str = "1") -> list[dict]:
    configs = [{"network": network, "n": 1000, "threads": threads, "delta_ms": delta,
                "name": f"{network}-t{threads}-d{delta:g}"}
               for network in ("alpha", "brunel", "aeif") for threads in (1, 2, 4, 8) for delta in (1.0, 5.0)]
    if protocol == "2":
        configs += [{"network": "brunel", "n": 10000, "threads": threads, "delta_ms": delta,
                     "name": f"brunel-n10000-t{threads}-d{delta:g}"}
                    for threads in (1, 2, 4, 8) for delta in (1.0, 5.0)]
    return configs


def build_ncp2_host(work: Path) -> Path:
    """Build the NCP 2 Rust host of this commit, as run3.py does."""
    subprocess.run(["cargo", "build", "--release", "--locked", "--quiet", "--manifest-path",
                    str(HERE / "harness" / "ncp2-rust" / "Cargo.toml")],
                   check=True, env=dict(os.environ, CARGO_TARGET_DIR=str(work / "target")))
    return work / "target" / "release" / "ncp2-nest-host"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--protocol", choices=sorted(PROTOCOLS), default="1")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    protocol_file, harness, order_seed = PROTOCOLS[args.protocol]
    configs = {config["name"]: config for config in configurations(args.protocol)}
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(order_seed)
        order = []
        for block in range(1 if args.smoke else BLOCKS):
            names = sorted(configs)
            rng.shuffle(names)
            order += [{"block": block, "config": name, "seed": SEED + block} for name in names]
        status = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"], capture_output=True,
                                text=True).stdout
        schedule_path.write_text(json.dumps({
            "protocol": protocol_file,
            "protocol_sha256": hashlib.sha256((HERE / protocol_file).read_bytes()).hexdigest(),
            "seed": SEED, "order_seed": order_seed, "smoke": args.smoke, "created_utc": now(),
            "worktree_clean": status == "",
            "commit": subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                                     text=True).stdout.strip(),
            "order": order}, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    if schedule.get("protocol", "PROTOCOL-CONTENT.md") != protocol_file:
        sys.exit(f"{args.results} holds {schedule.get('protocol', 'PROTOCOL-CONTENT.md')}, not {protocol_file}")
    trials_path = args.results / "trials.jsonl"
    done = set()
    if trials_path.exists():
        done = {(row["block"], row["config"]) for row in map(json.loads, trials_path.read_text().splitlines())
                if row}
    env = dict(os.environ, PREFIX=str(args.prefix),
               PYTHONPATH=f"{HERE / 'harness'}{os.pathsep}{ROOT / 'local/python'}", PYTHONDONTWRITEBYTECODE="1")
    if args.protocol == "2":
        env.update(NCP2_PYTHON=str(ROOT / "python"), NCP2_HOST=str(build_ncp2_host(args.results / ".work")))
    for index, entry in enumerate(schedule["order"]):
        if (entry["block"], entry["config"]) in done:
            continue
        config = configs[entry["config"]]
        work = args.results / ".work" / f"{entry['block']}-{entry['config']}"
        started, load = now(), os.getloadavg()[0]
        process = subprocess.run([sys.executable, str(HERE / "harness" / harness), config["network"],
                                  str(config["n"]), str(config["threads"]), f"{config['delta_ms']:g}",
                                  str(entry["seed"]), str(work)], capture_output=True, text=True, env=env,
                                 timeout=3600)
        row = {"block": entry["block"], "config": entry["config"], "load1_before": round(load, 2),
               "started_utc": started, "finished_utc": now(), "returncode": process.returncode}
        if process.returncode == 0:
            row.update(json.loads(process.stdout.strip().splitlines()[-1]))
        else:
            row["stderr_tail"] = process.stderr.strip().splitlines()[-4:]
        shutil.rmtree(work, ignore_errors=True)
        with trials_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        exact = {key: value for key, value in row.items() if key.endswith("_exact")}
        print(f"[{index + 1}/{len(schedule['order'])}] {entry['config']} block {entry['block']}: {exact}", flush=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
