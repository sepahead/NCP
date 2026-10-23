#!/usr/bin/env python3
"""Run the NEST campaign (see PROTOCOL.md). Resumable and safe to interrupt.

Usage: run.py RESULTS_DIR --prefix CONDA_PREFIX [--smoke] [--only REGEX]

CONDA_PREFIX holds NEST 3.10.0 with MPI and MUSIC. The first call writes
RESULTS_DIR/schedule.json: three blocks, each with every configuration once, in an
order shuffled with a fixed seed. Each finished run is appended to
RESULTS_DIR/runs.jsonl and synced to disk. A later call with the same directory skips
the runs that are already recorded. Every run has a time limit. Standard library only;
needs git and cargo.
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
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HARNESS = HERE / "harness"
SEED = 20261024  # network seed of block b is SEED + b in every protocol
BLOCKS = 3
# Protocol file -> order seed and excluded configurations (PROTOCOL-2.md gives the reasons).
PROTOCOLS = {
    "PROTOCOL.md": {"order_seed": 20261024, "exclude": ()},
    "PROTOCOL-2.md": {"order_seed": 20261025, "exclude": (r"^D4-brunel-n10000-t4-d5-",)},
}
TAG = "sdk-v1.0.0"
RUN_LIMIT_S = 1800
LOCAL_ARMS = ("mono", "chunked", "chunked-spikes")
COUNT_ARMS = ("mono", "chunked", "ncp-py-1.0.0", "ncp-py-1.0.1", "ncp-rs-1.0.1", "music")


def design() -> list[dict]:
    configs = []

    def add(part, arms, network, sizes, threads, deltas):
        for n in sizes:
            for t in threads:
                for d in deltas:
                    for arm in arms:
                        configs.append({"part": part, "arm": arm, "network": network, "n": n, "threads": t,
                                        "delta_ms": float(d)})

    add("D1", COUNT_ARMS, "brunel", (1000, 10000), (1, 4, 8), (1, 5, 20))
    for network in ("alpha", "aeif"):
        add("D2", COUNT_ARMS, network, (1000,), (1, 4), (1, 20))
    add("D3", ("mono", "chunked", "ncp-py-1.0.1", "ncp-rs-1.0.1", "music"), "brunel", (250, 2500, 25000), (8,), (1,))
    add("D4", ("chunked-spikes", "ncp-py-1.0.0-spikes", "ncp-py-1.0.1-spikes", "ncp-rs-1.0.1-spikes", "music"),
        "brunel", (1000, 10000), (4,), (1, 5))
    for config in configs:
        config["name"] = (f"{config['part']}-{config['network']}-n{config['n']}-t{config['threads']}"
                          f"-d{config['delta_ms']:g}-{config['arm']}")
    return configs


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command, **kwargs) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs).stdout.strip()


def prepare(work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    released = work / "released"
    if not (released / "local/python/ncp_local").exists():
        archive = subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar", TAG, "local/python"],
                                 capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(released, filter="data")
    project = work / "host"
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(HARNESS / "rust" / "src", project / "src")
    (project / "Cargo.toml").write_text((HARNESS / "rust" / "Cargo.toml.in").read_text()
                                        .replace("@NCP_LOCAL@", str(ROOT / "local/rust")))
    env = dict(os.environ, CARGO_TARGET_DIR=str(work / "target"))
    subprocess.run(["cargo", "build", "--release", "--offline", "--quiet", "--manifest-path",
                    str(project / "Cargo.toml")], check=True, env=env)
    return {"released_python": released / "local/python", "current_python": ROOT / "local/python",
            "rust_host": work / "target/release/ncp-nest-campaign-host"}


def run_config(config: dict, block_seed: int, prefix: Path, paths: dict, work: Path) -> dict:
    py = str(prefix / "bin" / "python")
    spec = [config["network"], str(config["n"]), str(config["threads"]), f"{config['delta_ms']:g}", str(block_seed)]
    sdk = "1.0.0" if "1.0.0" in config["arm"] else "1.0.1"
    python_dir = paths["released_python"] if sdk == "1.0.0" else paths["current_python"]
    env = {"HOME": os.environ["HOME"], "PATH": f"{prefix}/bin:/usr/bin:/bin:/usr/sbin:/sbin",
           "TMPDIR": str(work), "PYTHONPATH": f"{HARNESS}{os.pathsep}{python_dir}",
           "OMP_NUM_THREADS": str(config["threads"]), "PYNEST_QUIET": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    arm = config["arm"]
    payload = "spikes" if arm.endswith("-spikes") else "count"
    if arm in LOCAL_ARMS:
        command = [py, "-s", str(HARNESS / "local_arm.py"), arm] + spec
    elif arm.startswith("ncp-py"):
        command = [py, "-s", str(HARNESS / "py_host.py"), payload] + spec
    elif arm.startswith("ncp-rs"):
        command = [str(paths["rust_host"]), payload] + spec + [py, "-s", str(HARNESS / "endpoint.py")]
    else:
        return run_music(config, block_seed, prefix, env, work)
    try:
        process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=HARNESS,
                                 timeout=RUN_LIMIT_S)
    except subprocess.TimeoutExpired:
        return {"returncode": "timeout"}
    result = {}
    if process.returncode == 0:
        result = json.loads(process.stdout.strip().splitlines()[-1])
    result["returncode"] = process.returncode
    result["sdk"] = sdk if arm.startswith("ncp") else None
    if process.returncode != 0:
        result["stderr_tail"] = process.stderr.strip().splitlines()[-4:]
    return result


def run_music(config: dict, block_seed: int, prefix: Path, env: dict, work: Path) -> dict:
    py = str(prefix / "bin" / "python")
    directory = Path(tempfile.mkdtemp(prefix="music-", dir=work))
    launchers = {}
    for name, script in (("nest", "music_nest.py"), ("peer", "music_peer.py")):
        launcher = directory / f"{name}.sh"
        launcher.write_text(f'#!/bin/sh\nexec "{py}" -s "{HARNESS / script}" "$@"\n')
        launcher.chmod(0o755)
        launchers[name] = str(launcher)
    text = (HARNESS / "music_config.template").read_text()
    text = (text.replace("STOPTIME", f"{2.0:.6f}").replace("TIMESTEP", f"{config['delta_ms'] / 1000.0:.6f}")
            .replace("NEST_LAUNCHER", launchers["nest"]).replace("PEER_LAUNCHER", launchers["peer"])
            .replace("WIDTH", str(config["n"])))
    (directory / "bench.music").write_text(text)
    spec = {"network": config["network"], "n": config["n"], "threads": config["threads"],
            "delta_ms": config["delta_ms"], "seed": block_seed}
    run_env = dict(env, BENCH_SPEC=json.dumps(spec), BENCH_OUT=str(directory / "nest.json"),
                   BENCH_PEER_OUT=str(directory / "peer.json"))
    try:
        process = subprocess.run([str(prefix / "bin/mpiexec"), "--oversubscribe", "-n", "2",
                                  str(prefix / "bin/music"), str(directory / "bench.music")],
                                 capture_output=True, text=True, env=run_env, cwd=directory, timeout=RUN_LIMIT_S)
    except subprocess.TimeoutExpired:
        return {"returncode": "timeout"}
    result = {"returncode": process.returncode, "sdk": None}
    if process.returncode == 0 and (directory / "nest.json").exists() and (directory / "peer.json").exists():
        result.update(json.loads((directory / "nest.json").read_text()))
        peer = json.loads((directory / "peer.json").read_text())
        result.update({"spikes": peer["received"], "ticks": peer["ticks"]})
    else:
        result["stderr_tail"] = process.stderr.strip().splitlines()[-4:]
    shutil.rmtree(directory, ignore_errors=True)
    return result


def environment(prefix: Path) -> dict:
    py = str(prefix / "bin" / "python")
    probe = ("import json, sys, nest; b = nest.build_info; print(json.dumps({'python': sys.version.split()[0], "
             "'nest': nest.__version__, 'mpi': b.get('have_mpi'), 'music': b.get('have_music'), "
             "'threads_model': b.get('threads_model')}))")
    nest_info = json.loads(out([py, "-c", probe], env={**os.environ, "PYNEST_QUIET": "1"}).splitlines()[-1])
    hardware = {}
    for line in out(["system_profiler", "SPHardwareDataType"]).splitlines():
        key, sep, value = line.strip().partition(": ")
        if sep and key in ("Model Name", "Model Identifier", "Chip", "Total Number of Cores", "Memory"):
            hardware[key] = value
    return {"computer": hardware, "os": out(["sw_vers", "-productVersion"]), "kernel": platform.release(),
            "nest": nest_info, "music": out([str(prefix / "bin/music"), "--version"]).splitlines()[0],
            "mpi": out([str(prefix / "bin/mpiexec"), "--version"]).splitlines()[0],
            "rustc": out(["rustc", "--version"]), "power": out(["pmset", "-g", "batt"]).splitlines()[0]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--only", default=None, help="regular expression on configuration names (smoke only)")
    parser.add_argument("--protocol", default="PROTOCOL.md", choices=sorted(PROTOCOLS))
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    work = args.results / ".work"
    paths = prepare(work)
    configs = {config["name"]: config for config in design()}
    protocol = PROTOCOLS[args.protocol]
    configs = {name: config for name, config in configs.items()
               if not any(re.search(pattern, name) for pattern in protocol["exclude"])}
    if args.only:
        configs = {name: config for name, config in configs.items() if re.search(args.only, name)}
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        rng = random.Random(protocol["order_seed"])
        blocks = 1 if args.smoke else BLOCKS
        order = []
        for block in range(blocks):
            names = sorted(configs)
            rng.shuffle(names)
            order += [{"block": block, "config": name, "seed": SEED + block} for name in names]
        schedule = {"protocol": args.protocol,
                    "protocol_sha256": hashlib.sha256((HERE / args.protocol).read_bytes()).hexdigest(),
                    "seed": SEED, "order_seed": protocol["order_seed"], "blocks": blocks, "smoke": args.smoke, "only": args.only,
                    "commit": out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]), "created_utc": now(),
                    "configurations": len(configs), "order": order}
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
        (args.results / "environment.json").write_text(json.dumps(environment(args.prefix), indent=1) + "\n")
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
        key = (entry["block"], entry["config"])
        if key in done:
            continue
        config = configs[entry["config"]]
        load = os.getloadavg()[0]
        started = now()
        result = run_config(config, entry["seed"], args.prefix, paths, work)
        row = {"block": entry["block"], "config": entry["config"], "seed": entry["seed"],
               "load1_before": round(load, 2), "started_utc": started, "finished_utc": now(),
               **{k: config[k] for k in ("part", "arm", "network", "n", "threads", "delta_ms")}, **result}
        with runs_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        print(f"[{index + 1}/{total}] block {entry['block']} {entry['config']}: "
              f"rc={row['returncode']} wall={row.get('wall_s')}", flush=True)
    print("complete", flush=True)


if __name__ == "__main__":
    main()
