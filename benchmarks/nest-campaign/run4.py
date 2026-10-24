#!/usr/bin/env python3
"""Run protocol 4 of the NEST campaign: protocol 3's design, controlled conditions, and the time of
every step (see PROTOCOL-4.md).

Usage: run4.py RESULTS_DIR --prefix CONDA_PREFIX --ncp1 NCP1_CHECKOUT [--smoke] [--only REGEX]

Before each run, the runner waits until the computer draws power from its adapter, its thermal
pressure is nominal, a core runs at CLOCK_MIN_GHZ or more (harness/ncp2-rust/src/bin/clock-probe.rs),
and the one-minute load average is below LOAD_LIMIT. After the run, it checks that the computer did
not sleep and that the other conditions still hold, the load average excepted; if not, it marks the
record as disturbed and repeats the run, at most MAX_ATTEMPTS times in all.

Each arm writes the duration of every step to the files that NCP_WORK_TIMES and NCP_CALL_TIMES
name (harness/common.py). The runner stores their summaries in the record and deletes the files.
The run is resumable as with run.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as campaign  # noqa: E402
import run3  # noqa: E402

ROOT = HERE.parents[1]
PROTOCOL = "PROTOCOL-4.md"
ORDER_SEED = 20261027
LOAD_LIMIT = 8.0  # half of the 16 cores of the computer
CLOCK_MIN_GHZ = 4.0  # an M4 Max performance core runs at up to 4.5 GHz, and at about 3.1 GHz in Low Power Mode
MAX_ATTEMPTS = 3
SLEEP_LIMIT_S = 0.5


def conditions(probe: Path) -> dict:
    """Power source, thermal pressure (0 is nominal), clock of a core, and the one-minute load average.
    The clock is the larger of two probes, in case the scheduler puts one on an efficiency core."""
    power = campaign.out(["pmset", "-g", "batt"]).splitlines()[0]
    thermal = campaign.out(["notifyutil", "-g", "com.apple.system.thermalpressurelevel"]).split()[-1]
    clock = max(float(campaign.out([str(probe)])) for _ in range(2))
    return {"ac_power": "AC Power" in power, "thermal_pressure": int(thermal), "clock_ghz": clock,
            "load1": round(os.getloadavg()[0], 2)}


def steady(now: dict) -> bool:
    return now["ac_power"] and now["thermal_pressure"] == 0 and now["clock_ghz"] >= CLOCK_MIN_GHZ


def wait_for_conditions(probe: Path) -> tuple[dict, float]:
    started, reported = time.monotonic(), time.monotonic()
    while True:
        now = conditions(probe)
        if steady(now) and now["load1"] < LOAD_LIMIT:
            return now, time.monotonic() - started
        if time.monotonic() - reported > 300:
            print(f"waiting: {now}", flush=True)
            reported = time.monotonic()
        time.sleep(5)


def clocks() -> tuple[float, float]:
    """CLOCK_MONOTONIC counts time asleep on macOS; CLOCK_UPTIME_RAW does not."""
    return time.clock_gettime(time.CLOCK_MONOTONIC), time.clock_gettime(time.CLOCK_UPTIME_RAW)


def distribution(values: list[int]) -> dict:
    """Mean, median, and nearest-rank quantiles of durations in nanoseconds, in microseconds."""
    ordered = sorted(values)

    def rank(p: float) -> float:
        return ordered[max(0, math.ceil(p * len(ordered)) - 1)] / 1000

    return {"n": len(ordered), "mean_us": statistics.fmean(ordered) / 1000,
            "median_us": statistics.median(ordered) / 1000, "p90_us": rank(0.90), "p99_us": rank(0.99),
            "max_us": ordered[-1] / 1000}


def step_times(work_file: Path, call_file: Path, arm: str) -> dict:
    """The summaries of one run's step times. `overhead` is what the coupling adds to a step: for an NCP
    arm, the host's call minus the owner's NEST work of the same step; for a chunked-pipe arm, the raw
    round trip."""
    record = {}
    work = json.loads(work_file.read_text()) if work_file.exists() else None
    calls = json.loads(call_file.read_text()) if call_file.exists() else None
    if work:
        record["work_us"] = distribution(work)
    if calls:
        record["call_us"] = distribution(calls)
        if arm.startswith("chunked-pipe"):
            record["overhead_us"] = record["call_us"]
        elif work and len(work) == len(calls):
            record["overhead_us"] = distribution([c - w for c, w in zip(calls, work, strict=True)])
        else:
            record["step_times_error"] = "the host and the owner recorded different numbers of steps"
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--ncp1", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--only", default=None, help="regular expression on configuration names (smoke only)")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    work = args.results / ".work"
    paths = run3.build(work, args.ncp1)
    probe = work / "target" / "release" / "clock-probe"
    configs = {config["name"]: config for config in run3.design()}
    if args.only:
        configs = {name: config for name, config in configs.items() if re.search(args.only, name)}
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(ORDER_SEED)
        blocks = 1 if args.smoke else run3.BLOCKS
        order = []
        for block in range(blocks):
            names = sorted(configs)
            rng.shuffle(names)
            order += [{"block": block, "config": name, "seed": run3.SEED + block} for name in names]
        protocol = HERE / PROTOCOL
        schedule = {
            "protocol": PROTOCOL,
            "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest() if protocol.exists() else None,
            "seed": run3.SEED, "order_seed": ORDER_SEED, "blocks": blocks, "smoke": args.smoke, "only": args.only,
            "load_limit": LOAD_LIMIT, "clock_min_ghz": CLOCK_MIN_GHZ, "max_attempts": MAX_ATTEMPTS,
            "sleep_limit_s": SLEEP_LIMIT_S,
            "commit": campaign.out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "worktree_clean": campaign.out(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
            "ncp1_commit": campaign.out(["git", "-C", str(args.ncp1), "rev-parse", "HEAD"]),
            "created_utc": campaign.now(), "configurations": len(configs), "order": order,
        }
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
        (args.results / "environment.json").write_text(json.dumps(campaign.environment(args.prefix), indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    runs_path = args.results / "runs.jsonl"
    attempts: dict = {}
    done = set()
    if runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                key = (row["block"], row["config"])
                attempts[key] = attempts.get(key, 0) + 1
                if not row["disturbed"] or attempts[key] >= MAX_ATTEMPTS:
                    done.add(key)
    work_file, call_file = work / "times-work.json", work / "times-call.json"
    timing_env = {"NCP_WORK_TIMES": str(work_file), "NCP_CALL_TIMES": str(call_file)}
    total = len(schedule["order"])
    for index, entry in enumerate(schedule["order"]):
        key = (entry["block"], entry["config"])
        config = configs[entry["config"]]
        while key not in done:
            before, waited = wait_for_conditions(probe)
            work_file.unlink(missing_ok=True)
            call_file.unlink(missing_ok=True)
            continuous, uptime = clocks()
            started = campaign.now()
            result = run3.run_config(config, entry["seed"], args.prefix, paths, work, timing_env)
            finished = campaign.now()
            continuous_after, uptime_after = clocks()
            after = conditions(probe)
            slept = (continuous_after - continuous) - (uptime_after - uptime)
            disturbed = slept > SLEEP_LIMIT_S or not steady(after)
            attempts[key] = attempts.get(key, 0) + 1
            # The configuration's fields come last: a host reports its own arm name (for example
            # ncp2-rs-count), and the protocol's arm name must win.
            row = {"block": entry["block"], "config": entry["config"], "seed": entry["seed"],
                   "attempt": attempts[key], "disturbed": disturbed, "slept_s": round(slept, 3),
                   "waited_s": round(waited, 1), "before": before, "after": after,
                   "load1_before": before["load1"], "started_utc": started, "finished_utc": finished,
                   **result, **step_times(work_file, call_file, config["arm"]),
                   **{k: config[k] for k in ("part", "arm", "network", "n", "threads", "delta_ms")}}
            with runs_path.open("a") as handle:
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            print(f"[{index + 1}/{total}] block {entry['block']} {entry['config']}: rc={row['returncode']} "
                  f"wall={row.get('wall_s')}" + (" disturbed" if disturbed else ""), flush=True)
            if not disturbed or attempts[key] >= MAX_ATTEMPTS:
                done.add(key)
    work_file.unlink(missing_ok=True)
    call_file.unlink(missing_ok=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
