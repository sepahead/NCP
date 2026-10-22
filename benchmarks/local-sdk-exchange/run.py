#!/usr/bin/env python3
"""Run the local SDK exchange benchmark (see PROTOCOL.md).

Usage: run.py OUT_JSON --python PYTHON [--smoke]

It builds the Rust harness against the released `sdk-v1.0.0` sources and against
this checkout, checks that both owners write the same transcript, and then times
every configuration once per round, in a seeded random order within each round.
PYTHON runs the Python endpoints. Standard library only; needs git and cargo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TAG = "sdk-v1.0.0"
SEED = 20261022
ROUNDS, CALLS, WARMUP = 5, 3000, 500
RUST_SIZES = (0, 13, 127, 500)
PYTHON_SIZES = (0, 13, 127)
MIXED_SIZES = (0, 127)
RAW_BYTES = 512


def out(command: list[str], **kwargs) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs).stdout.strip()


def sha256_tree(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}


def extract_release(destination: Path) -> str:
    archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", TAG, "local/rust", "local/python"],
                             capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")
    return out(["git", "-C", str(ROOT), "rev-list", "-n", "1", TAG])


def build(variant: str, sdk: Path, work: Path) -> dict:
    project = work / f"harness-{variant}"
    shutil.copytree(HERE / "harness" / "rust" / "src", project / "src")
    template = (HERE / "harness" / "rust" / "Cargo.toml.in").read_text()
    (project / "Cargo.toml").write_text(template.replace("@NCP_LOCAL@", str(sdk)))
    env = dict(os.environ, CARGO_TARGET_DIR=str(work / f"target-{variant}"))
    subprocess.run(["cargo", "build", "--release", "--offline", "--quiet", "--manifest-path",
                    str(project / "Cargo.toml")], check=True, env=env)
    binary = work / f"target-{variant}" / "release" / "ncp-local-exchange-bench"
    lock = (project / "Cargo.lock").read_bytes()
    return {"binary": str(binary), "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
            "cargo_lock_sha256": hashlib.sha256(lock).hexdigest(),
            "cargo_lock_packages": [line.split('"')[1] + " " + next_line.split('"')[1]
                                    for line, next_line in zip(lock.decode().splitlines(), lock.decode().splitlines()[1:])
                                    if line.startswith("name = ") and next_line.startswith("version = ")]}


def configurations(python: str, binaries: dict[str, str], python_dir: Path) -> list[dict]:
    harness = HERE / "harness" / "python"
    py_owner = [python, "-s", str(harness / "owner.py")]
    configs = [{"name": "raw-rust", "command": [binaries["current"], "raw", str(RAW_BYTES)]},
               {"name": "raw-python", "command": [python, "-s", str(harness / "raw.py"), str(RAW_BYTES)]}]
    for variant, binary in binaries.items():
        for n in RUST_SIZES:
            configs.append({"name": f"rust-rust-{variant}-n{n}", "command": [binary, "client", str(n)],
                            "owner": [binary, "owner"]})
        for n in MIXED_SIZES:
            configs.append({"name": f"python-rust-{variant}-n{n}",
                            "command": [python, "-s", str(harness / "client.py"), str(n)], "owner": [binary, "owner"]})
            configs.append({"name": f"rust-{variant}-python-n{n}", "command": [binary, "client", str(n)],
                            "owner": py_owner})
            configs.append({"name": f"phases-{variant}-n{n}", "command": [binary, "phases", str(n)]})
    for n in PYTHON_SIZES:
        configs.append({"name": f"python-python-n{n}", "command": [python, "-s", str(harness / "client.py"), str(n)],
                        "owner": py_owner})
    for config in configs:
        config["python_path"] = f"{python_dir}{os.pathsep}{harness}"
    return configs


def run_once(config: dict, calls: int, warmup: int) -> dict:
    command = config["command"] + [str(calls), str(warmup)] + config.get("owner", [])
    env = dict(os.environ, PYTHONPATH=config["python_path"], PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONHOME", None)
    load = os.getloadavg()
    started = dt.datetime.now(dt.timezone.utc)
    process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=HERE)
    finished = dt.datetime.now(dt.timezone.utc)
    result = json.loads(process.stdout.strip().splitlines()[-1]) if process.returncode == 0 else {}
    return {"config": config["name"], "returncode": process.returncode, "load1_before": round(load[0], 2),
            "started_utc": started.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "finished_utc": finished.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "stderr_tail": process.stderr.strip().splitlines()[-3:], **result}


def environment(python: str) -> dict:
    def sysctl(name: str) -> str:
        return out(["sysctl", "-n", name])
    hardware = {}
    for line in out(["system_profiler", "SPHardwareDataType"]).splitlines():
        key, sep, value = line.strip().partition(": ")
        if sep and key in ("Model Name", "Model Identifier", "Chip", "Total Number of Cores", "Memory",
                           "System Firmware Version"):
            hardware[key] = value
    return {
        "computer": hardware,
        "performance_cores": int(sysctl("hw.perflevel0.physicalcpu")),
        "efficiency_cores": int(sysctl("hw.perflevel1.physicalcpu")),
        "os": out(["sw_vers", "-productVersion"]) + " (" + out(["sw_vers", "-buildVersion"]) + ")",
        "kernel": platform.release(),
        "rustc": out(["rustc", "--version"]),
        "cargo": out(["cargo", "--version"]),
        "python_endpoints": out([python, "-c", "import sys; print(sys.version.split()[0])"]),
        "driver_python": platform.python_version(),
        "power": out(["pmset", "-g", "batt"]).splitlines()[0],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    rounds, calls, warmup = (1, 200, 50) if args.smoke else (ROUNDS, CALLS, WARMUP)
    protocol_sha256 = hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="ncp-sdk-bench-") as temporary:
        work = Path(temporary)
        tag_commit = extract_release(work / "released")
        python_identical = sha256_tree(work / "released/local/python/ncp_local") == sha256_tree(
            ROOT / "local/python/ncp_local")
        builds = {"released": build("released", work / "released/local/rust", work),
                  "current": build("current", ROOT / "local/rust", work)}
        transcripts = {variant: out([info["binary"], "transcript"]) for variant, info in builds.items()}
        record = {
            "schema": "ncp.local-sdk-exchange-benchmark.v1",
            "protocol_sha256": protocol_sha256,
            "smoke": args.smoke,
            "seed": SEED, "rounds": rounds, "calls": calls, "warmup": warmup,
            "release_tag": TAG, "release_commit": tag_commit,
            "current_commit": out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "current_dirty_paths": out(["git", "-C", str(ROOT), "status", "--porcelain", "--", "local", "ncp-core"])
            .splitlines(),
            "python_sources_identical_to_release": python_identical,
            "builds": {variant: {k: v for k, v in info.items() if k != "binary"} for variant, info in builds.items()},
            "transcript_lines": len(transcripts["current"].splitlines()),
            "transcript_sha256": {variant: hashlib.sha256(text.encode()).hexdigest()
                                  for variant, text in transcripts.items()},
            "transcripts_identical": transcripts["released"] == transcripts["current"],
            "environment": environment(args.python),
            "started_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runs": [],
        }
        if not record["transcripts_identical"]:
            args.out.write_text(json.dumps(record, indent=1) + "\n")
            sys.exit("owner transcripts differ; no timed runs")
        configs = configurations(args.python, {k: v["binary"] for k, v in builds.items()},
                                 ROOT / "local/python")
        rng = random.Random(SEED)
        for round_index in range(rounds):
            order = configs[:]
            rng.shuffle(order)
            for config in order:
                run = run_once(config, calls, warmup)
                run["round"] = round_index
                record["runs"].append(run)
                print(f"round {round_index} {config['name']}: "
                      f"{run.get('timing', {}).get('median_us', run.get('total_mean_us', 'failed'))}", flush=True)
        record["finished_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.out.write_text(json.dumps(record, indent=1) + "\n")


if __name__ == "__main__":
    main()
