#!/usr/bin/env python3
"""Run protocol 3 of the NEST campaign: NCP 2 against NCP 1.0.1 and MUSIC (see PROTOCOL-3.md).

Usage: run3.py RESULTS_DIR --prefix CONDA_PREFIX --ncp1 NCP1_CHECKOUT [--smoke] [--only REGEX]

CONDA_PREFIX holds NEST 3.10.0 with MPI and MUSIC. NCP1_CHECKOUT is a checkout of the tag
sdk-v1.0.1. The run is resumable as with run.py: the schedule, the environment, and every run are
written to RESULTS_DIR as they happen. The MUSIC arm, the local arms, and the environment record
are those of run.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as campaign  # noqa: E402

ROOT = HERE.parents[1]
HARNESS = HERE / "harness"
PROTOCOL = "PROTOCOL-3.md"
ORDER_SEED = 20261026
SEED = campaign.SEED  # the network seed of block b is SEED + b, as in protocols 1 and 2
BLOCKS = 3
COUNT_ARMS = ("mono", "chunked", "chunked-pipe", "ncp2-py", "ncp2-rs", "ncp-py-1.0.1", "ncp-rs-1.0.1", "music")
PIPE_ARMS = ("chunked-pipe", "chunked-pipe-spikes")
SPIKE_ARMS = (
    "chunked-spikes",
    "chunked-pipe-spikes",
    "ncp2-py-spikes",
    "ncp2-rs-spikes",
    "ncp-py-1.0.1-spikes",
    "ncp-rs-1.0.1-spikes",
    "music",
)
# NCP 1.0.x refuses some steps of this configuration: their results exceed its 65,536-byte frame.
EXCLUDE = (r"^D4-brunel-n10000-t4-d5-ncp-",)


def design() -> list[dict]:
    configs = []

    def add(part, arms, network, sizes, threads, deltas):
        for n in sizes:
            for t in threads:
                for d in deltas:
                    for arm in arms:
                        configs.append(
                            {"part": part, "arm": arm, "network": network, "n": n, "threads": t, "delta_ms": float(d)}
                        )

    add("D1", COUNT_ARMS, "brunel", (1000, 10000), (1, 4, 8), (1, 5, 20))
    for network in ("alpha", "aeif"):
        add("D2", COUNT_ARMS, network, (1000,), (1, 4), (1, 20))
    add("D3", COUNT_ARMS, "brunel", (250, 2500, 25000), (8,), (1,))
    add("D4", SPIKE_ARMS, "brunel", (1000, 10000), (4,), (1, 5))
    for config in configs:
        config["name"] = (
            f"{config['part']}-{config['network']}-n{config['n']}-t{config['threads']}"
            f"-d{config['delta_ms']:g}-{config['arm']}"
        )
    return [config for config in configs if not any(re.search(pattern, config["name"]) for pattern in EXCLUDE)]


def build(work: Path, ncp1: Path) -> dict:
    """Build the NCP 1.0.1 Rust host and the NCP 2 Rust host."""
    work.mkdir(parents=True, exist_ok=True)
    project = work / "ncp1-host"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(HARNESS / "rust" / "src", project / "src")
    (project / "Cargo.toml").write_text(
        (HARNESS / "rust" / "Cargo.toml.in").read_text().replace("@NCP_LOCAL@", str(ncp1 / "local" / "rust"))
    )
    env = dict(os.environ, CARGO_TARGET_DIR=str(work / "target"))
    # As in protocols 1 and 2: the released SDK's own dependencies, from the local cache.
    subprocess.run(
        ["cargo", "build", "--release", "--offline", "--quiet", "--manifest-path", str(project / "Cargo.toml")],
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
            str(HARNESS / "ncp2-rust" / "Cargo.toml"),
        ],
        check=True,
        env=env,
    )
    return {
        "ncp1_python": ncp1 / "local" / "python",
        "ncp2_python": ROOT / "python",
        "ncp1_host": work / "target/release/ncp-nest-campaign-host",
        "ncp2_host": work / "target/release/ncp2-nest-host",
    }


def run_config(
    config: dict, block_seed: int, prefix: Path, paths: dict, work: Path, extra_env: dict | None = None
) -> dict:
    py = str(prefix / "bin" / "python")
    spec = [config["network"], str(config["n"]), str(config["threads"]), f"{config['delta_ms']:g}", str(block_seed)]
    arm = config["arm"]
    payload = "spikes" if arm.endswith("-spikes") else "count"
    sdk = "2" if arm.startswith("ncp2") else "1.0.1" if arm.startswith("ncp") else None
    python_dir = paths["ncp2_python"] if sdk == "2" else paths["ncp1_python"]
    env = {
        "HOME": os.environ["HOME"],
        "PATH": f"{prefix}/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(work),
        "PYTHONPATH": f"{HARNESS}{os.pathsep}{python_dir}",
        "OMP_NUM_THREADS": str(config["threads"]),
        "PYNEST_QUIET": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        **(extra_env or {}),
    }
    if arm in campaign.LOCAL_ARMS:
        command = [py, "-s", str(HARNESS / "local_arm.py"), arm] + spec
    elif arm in PIPE_ARMS:
        command = [py, "-s", str(HARNESS / "pipe_arm.py"), arm] + spec
    elif arm.startswith("ncp2-py"):
        command = [py, "-s", str(HARNESS / "ncp2_host.py"), payload] + spec
    elif arm.startswith("ncp2-rs"):
        command = (
            [str(paths["ncp2_host"]), payload]
            + spec
            + [str(HARNESS / "ncp2_contract.json"), py, "-s", str(HARNESS / "ncp2_owner.py")]
        )
    elif arm.startswith("ncp-py"):
        command = [py, "-s", str(HARNESS / "py_host.py"), payload] + spec
    elif arm.startswith("ncp-rs"):
        command = [str(paths["ncp1_host"]), payload] + spec + [py, "-s", str(HARNESS / "endpoint.py")]
    else:
        return campaign.run_music(config, block_seed, prefix, env, work)
    try:
        process = subprocess.run(
            command, capture_output=True, text=True, env=env, cwd=HARNESS, timeout=campaign.RUN_LIMIT_S
        )
    except subprocess.TimeoutExpired:
        return {"returncode": "timeout", "sdk": sdk}
    result = json.loads(process.stdout.strip().splitlines()[-1]) if process.returncode == 0 else {}
    result.update({"returncode": process.returncode, "sdk": sdk})
    if process.returncode != 0:
        result["stderr_tail"] = process.stderr.strip().splitlines()[-4:]
    return result


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
    paths = build(work, args.ncp1)
    configs = {config["name"]: config for config in design()}
    if args.only:
        configs = {name: config for name, config in configs.items() if re.search(args.only, name)}
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(ORDER_SEED)
        blocks = 1 if args.smoke else BLOCKS
        order = []
        for block in range(blocks):
            names = sorted(configs)
            rng.shuffle(names)
            order += [{"block": block, "config": name, "seed": SEED + block} for name in names]
        schedule = {
            "protocol": PROTOCOL,
            "protocol_sha256": hashlib.sha256((HERE / PROTOCOL).read_bytes()).hexdigest(),
            "seed": SEED,
            "order_seed": ORDER_SEED,
            "blocks": blocks,
            "smoke": args.smoke,
            "only": args.only,
            "commit": campaign.out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "worktree_clean": campaign.out(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
            "ncp1_commit": campaign.out(["git", "-C", str(args.ncp1), "rev-parse", "HEAD"]),
            "created_utc": campaign.now(),
            "configurations": len(configs),
            "order": order,
        }
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
        (args.results / "environment.json").write_text(json.dumps(campaign.environment(args.prefix), indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    runs_path = args.results / "runs.jsonl"
    done = set()
    if runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                done.add((row["block"], row["config"]))
    total = len(schedule["order"])
    for index, entry in enumerate(schedule["order"]):
        if (entry["block"], entry["config"]) in done:
            continue
        config = configs[entry["config"]]
        load = os.getloadavg()[0]
        started = campaign.now()
        result = run_config(config, entry["seed"], args.prefix, paths, work)
        # The configuration's fields come last: a host reports its own arm name (for example
        # ncp2-rs-count), and the protocol's arm name must win.
        row = {
            "block": entry["block"],
            "config": entry["config"],
            "seed": entry["seed"],
            "load1_before": round(load, 2),
            "started_utc": started,
            "finished_utc": campaign.now(),
            **result,
            **{k: config[k] for k in ("part", "arm", "network", "n", "threads", "delta_ms")},
        }
        with runs_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(
            f"[{index + 1}/{total}] block {entry['block']} {entry['config']}: "
            f"rc={row['returncode']} wall={row.get('wall_s')}",
            flush=True,
        )
    print("complete", flush=True)


if __name__ == "__main__":
    main()
