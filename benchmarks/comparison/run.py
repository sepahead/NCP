#!/usr/bin/env python3
"""Run the comparison benchmark (see PROTOCOL.md). Resumable.

Usage: run.py RESULTS_DIR --python PYTHON --ncp1 NCP1_CHECKOUT [--smoke]

PYTHON is the interpreter of the benchmark environment (requirements.txt). NCP1_CHECKOUT is a
checkout of tag sdk-v1.0.1. The first call checks validity (validity.json) and writes the
schedule (schedule.json): three blocks, each with every configuration once, in an order shuffled
with a fixed seed. Each finished run is appended to runs.jsonl and synced to disk, so a lost
session loses at most the run in progress; a later call skips recorded runs. Needs cargo.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SEED = 20261024
BLOCKS = 3
SPIKES = (0, 127, 1788, 87381)
NCP1_SPIKES = (0, 127, 1788)
CALLS = {0: (5000, 500), 127: (5000, 500), 1788: (5000, 500), 87381: (300, 30)}
SMOKE_CALLS = (100, 10)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command: list[str], **kwargs) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs).stdout.strip()


def cargo_build(manifest: Path, target: Path, examples: bool = False) -> None:
    command = ["cargo", "build", "--release", "--locked", "--quiet", "--manifest-path", str(manifest)]
    if examples:
        command.append("--examples")
    subprocess.run(command, check=True, env=dict(os.environ, CARGO_TARGET_DIR=str(target)))


def build(work: Path, ncp1: Path) -> dict[str, Path]:
    """Build the NCP 2 examples, the Rust comparison arms, and the NCP 1.0.1 harness."""
    cargo_build(ROOT / "rust" / "Cargo.toml", work / "ncp2-target", examples=True)
    cargo_build(HERE / "harness" / "rust" / "Cargo.toml", work / "harness-target")
    v1 = work / "ncp1-harness"
    if v1.exists():
        shutil.rmtree(v1)
    shutil.copytree(HERE / "harness" / "ncp1" / "rust" / "src", v1 / "src")
    template = (HERE / "harness" / "ncp1" / "rust" / "Cargo.toml.in").read_text()
    (v1 / "Cargo.toml").write_text(template.replace("@NCP_LOCAL@", str(ncp1 / "local" / "rust")))
    shutil.copy(HERE / "harness" / "ncp1" / "rust" / "Cargo.lock", v1 / "Cargo.lock")
    cargo_build(v1 / "Cargo.toml", work / "ncp1-target")
    examples = work / "ncp2-target" / "release" / "examples"
    return {"bench_client": examples / "bench_client", "echo_owner": examples / "echo_owner",
            "harness": work / "harness-target" / "release" / "ncp-comparison-bench",
            "ncp1": work / "ncp1-target" / "release" / "ncp-local-exchange-bench"}


def configurations(python: str, binaries: dict[str, Path]) -> dict[str, dict]:
    """Every configuration: a client command, and an optional server started before it."""
    py = [python, "-s"]
    harness = HERE / "harness" / "python"
    py_owner = py + [str(ROOT / "python" / "tests" / "echo_owner.py")]
    rust_owner = [str(binaries["echo_owner"])]
    rust_client = [str(binaries["bench_client"])]
    py_client = py + [str(harness / "ncp2_client.py")]
    bench = str(binaries["harness"])
    v1_python = py + [str(HERE / "harness" / "ncp1" / "python" / "client.py"), "sdk"]
    v1_py_owner = py + [str(HERE / "harness" / "ncp1" / "python" / "owner.py")]
    v1_rust = [str(binaries["ncp1"])]
    configs: dict[str, dict] = {}

    def add(name: str, spikes: int, client: list[str], server: list[str] | None = None, family: str = "") -> None:
        configs[f"{name}-n{spikes}"] = {"arm": name, "spikes": spikes, "client": client, "server": server,
                                        "family": family}

    for n in SPIKES:
        args = ["{calls}", "{warmup}", str(n)]
        add("ncp2-rust-rust-pipe", n, rust_client + args + ["--"] + rust_owner, family="ncp2")
        add("ncp2-rust-rust-unix", n, rust_client + args + ["--connect", "{address}"],
            rust_owner + ["unix", "{socket}"], family="ncp2")
        add("ncp2-rust-rust-tcp", n, rust_client + args + ["--connect", "{address}"], rust_owner + ["tcp"],
            family="ncp2")
        add("ncp2-rust-python-pipe", n, rust_client + args + ["--"] + py_owner, family="ncp2")
        add("ncp2-python-rust-pipe", n, py_client + args + ["--"] + rust_owner, family="ncp2")
        add("ncp2-python-python-pipe", n, py_client + args + ["--"] + py_owner, family="ncp2")
        add("ncp2-python-python-unix", n, py_client + args + ["--connect", "{address}"],
            py_owner + ["unix", "{socket}"], family="ncp2")
        add("ncp2-python-python-tcp", n, py_client + args + ["--connect", "{address}"], py_owner + ["tcp"],
            family="ncp2")
        add("raw-rust-pipe", n, [bench, "raw-client"] + args + ["--", bench, "raw-server"], family="floor")
        add("raw-python-pipe", n, py + [str(harness / "raw_pipe.py"), "client"] + args
            + ["--"] + py + [str(harness / "raw_pipe.py"), "server"], family="floor")
        add("grpc-rust-tcp", n, [bench, "grpc-client"] + args + ["{address}"], [bench, "grpc-server"],
            family="other")
        add("zenoh-rust-tcp", n, [bench, "zenoh-client"] + args + ["{address}"], [bench, "zenoh-server"],
            family="other")
        for kind in ("unix", "tcp"):
            add(f"grpc-python-{kind}", n, py + [str(harness / "grpc_echo.py"), "client", kind] + args, family="other")
        for kind in ("ipc", "tcp"):
            add(f"zmq-python-{kind}", n, py + [str(harness / "zmq_echo.py"), "client", kind] + args, family="other")
        add("http-python-tcp", n, py + [str(harness / "http_echo.py"), "client"] + args, family="other")
        add("zenoh-python-tcp", n, py + [str(harness / "zenoh_echo.py"), "client"] + args, family="other")
    for n in NCP1_SPIKES:
        args = [str(n), "{calls}", "{warmup}"]
        add("ncp1-rust-rust-pipe", n, v1_rust + ["sequential"] + args + v1_rust + ["owner"], family="ncp1")
        add("ncp1-rust-python-pipe", n, v1_rust + ["sequential"] + args + v1_py_owner, family="ncp1")
        add("ncp1-python-rust-pipe", n, v1_python + args + v1_rust + ["owner"], family="ncp1")
        add("ncp1-python-python-pipe", n, v1_python + args + v1_py_owner, family="ncp1")
    return configs


def environment(ncp1: Path) -> dict:
    return {
        "PYTHONPATH": os.pathsep.join([str(ROOT / "python"), str(HERE / "harness" / "python"),
                                       str(ncp1 / "local" / "python"), str(HERE / "harness" / "ncp1" / "python")]),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1",
    }


def run_one(config: dict, calls: int, warmup: int, env: dict) -> tuple[int, dict, list[str]]:
    """Start the server if any, run the client, stop the server. Returns (code, result, stderr tail)."""
    socket_directory = tempfile.mkdtemp(prefix="ncpb", dir="/tmp")  # socket paths must be short
    server = None
    replacements = {"{calls}": str(calls), "{warmup}": str(warmup), "{socket}": f"{socket_directory}/s"}
    try:
        if config["server"]:
            command = [replacements.get(part, part) for part in config["server"]]
            server = subprocess.Popen(command, stdout=subprocess.PIPE, text=True, env=env)
            line = server.stdout.readline().split(maxsplit=1)
            if len(line) != 2 or line[0] != "ready":
                return 1, {}, [f"server did not start: {line!r}"]
            replacements["{address}"] = line[1].strip()
        command = [replacements.get(part, part) for part in config["client"]]
        process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=1800)
        lines = process.stdout.strip().splitlines()
        result = json.loads(lines[-1]) if process.returncode == 0 and lines else {}
        return process.returncode, result, process.stderr.strip().splitlines()[-3:]
    except subprocess.TimeoutExpired:
        return 124, {}, ["timeout"]
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
            server.stdout.close()
        shutil.rmtree(socket_directory, ignore_errors=True)


def validity(python: str, binaries: dict[str, Path], configs: dict[str, dict], env: dict) -> dict:
    """The checks that must pass before any timed run."""
    record: dict = {}
    model = ROOT / "model"
    conformance = ROOT / "conformance"
    socket_directory = tempfile.mkdtemp(prefix="ncpv", dir="/tmp")
    checks = [
        ("rust_tests", ["cargo", "test", "--release", "--locked", "--quiet", "--manifest-path",
                        str(ROOT / "rust" / "Cargo.toml")], {"CARGO_TARGET_DIR": str(binaries["echo_owner"].parents[2])}),
        ("python_tests", [python, "-s", str(ROOT / "python" / "tests" / "test_ncp.py")],
         {"NCP_RUST_EXAMPLES": str(binaries["echo_owner"].parent)}),
        ("python_conformance_vectors", [python, "-s", str(ROOT / "python" / "tests" / "test_conformance.py")], {}),
        ("model_conformance_python_owner", [python, "-s", str(model / "conformance.py"), "--traces", "20000"], {}),
        ("model_conformance_rust_owner", [python, "-s", str(model / "conformance.py"), "--traces", "20000",
                                          "--owner", str(binaries["echo_owner"].parent / "model_owner"),
                                          f"{socket_directory}/m"], {}),
        ("differential_fuzzing", [python, "-s", str(conformance / "fuzz.py"), "--decoder",
                                  str(binaries["echo_owner"].parent / "decode_corpus"), "--cases", "200000"], {}),
    ]
    try:
        for name, command, extra in checks:
            process = subprocess.run(command, capture_output=True, text=True, env=dict(os.environ, **env, **extra))
            record[name] = {"returncode": process.returncode,
                            "tail": (process.stdout + process.stderr).strip().splitlines()[-3:]}
    finally:
        shutil.rmtree(socket_directory, ignore_errors=True)
    smoke = {}
    for name, config in sorted(configs.items()):
        code, result, tail = run_one(config, *SMOKE_CALLS, dict(os.environ, **env))
        smoke[name] = {"returncode": code, "median_us": result.get("median_us"), "tail": tail if code else []}
    record["smoke_runs"] = {"returncode": int(any(entry["returncode"] for entry in smoke.values())), "runs": smoke}
    return record


def describe_environment(python: str, ncp1: Path) -> dict:
    def safe(command: list[str]) -> str:
        try:
            return out(command)
        except (OSError, subprocess.CalledProcessError):
            return "unavailable"

    lock_digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()  # noqa: E731
    return {
        "computer": safe(["sysctl", "-n", "hw.model"]), "chip": safe(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "cores": safe(["sysctl", "-n", "hw.ncpu"]), "memory_bytes": safe(["sysctl", "-n", "hw.memsize"]),
        "os": safe(["sw_vers", "-productVersion"]), "kernel": platform.release(),
        "power": safe(["pmset", "-g", "batt"]).splitlines()[0] if safe(["pmset", "-g", "batt"]) else "unavailable",
        "rustc": safe(["rustc", "--version"]), "cargo": safe(["cargo", "--version"]),
        "python": safe([python, "-c", "import sys; print(sys.version.split()[0])"]),
        "python_packages": safe([python, "-m", "pip", "freeze"]).splitlines(),
        "ncp2_commit": safe(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "ncp2_worktree_clean": safe(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
        "ncp1_commit": safe(["git", "-C", str(ncp1), "rev-parse", "HEAD"]),
        "cargo_lock_sha256": {"ncp2": lock_digest(ROOT / "rust" / "Cargo.lock"),
                              "harness": lock_digest(HERE / "harness" / "rust" / "Cargo.lock"),
                              "ncp1_harness": lock_digest(HERE / "harness" / "ncp1" / "rust" / "Cargo.lock")},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--ncp1", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true", help="one short block, for testing the runner")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    work = args.results / ".work"
    work.mkdir(exist_ok=True)
    binaries = build(work, args.ncp1)
    configs = configurations(args.python, binaries)
    env = environment(args.ncp1)
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        record = validity(args.python, binaries, configs, env)
        record["environment"] = describe_environment(args.python, args.ncp1)
        (args.results / "validity.json").write_text(json.dumps(record, indent=1) + "\n")
        failed = [name for name, entry in record.items() if name != "environment" and entry["returncode"]]
        if failed:
            sys.exit(f"validity checks failed: {failed}; no timed runs")
        rng = random.Random(SEED)
        blocks = 1 if args.smoke else BLOCKS
        order = []
        for block in range(blocks):
            names = sorted(configs)
            rng.shuffle(names)
            order += [{"block": block, "config": name} for name in names]
        schedule = {"protocol_sha256": hashlib.sha256((HERE / "PROTOCOL.md").read_bytes()).hexdigest(),
                    "seed": SEED, "blocks": blocks, "smoke": args.smoke, "calls": {str(k): v for k, v in CALLS.items()},
                    "created_utc": now(), "order": order}
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    runs_path = args.results / "runs.jsonl"
    done, failed_once = set(), set()
    if runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                key = (row["block"], row["config"])
                if row["returncode"] == 0 or row.get("retry"):
                    done.add(key)
                else:
                    failed_once.add(key)
    # A failed run is repeated once, after all scheduled runs (PROTOCOL.md, exclusions).
    queue = deque(entry for entry in schedule["order"] if (entry["block"], entry["config"]) not in done | failed_once)
    retries = deque(dict(entry, retry=True) for entry in schedule["order"]
                    if (entry["block"], entry["config"]) in failed_once - done)
    full_env = dict(os.environ, **env)
    while queue or retries:
        entry = queue.popleft() if queue else retries.popleft()
        config = configs[entry["config"]]
        calls, warmup = SMOKE_CALLS if schedule["smoke"] else CALLS[config["spikes"]]
        load = os.getloadavg()
        started = now()
        code, result, tail = run_one(config, calls, warmup, full_env)
        row = {"block": entry["block"], "config": entry["config"], "arm": config["arm"], "family": config["family"],
               "spikes": config["spikes"], "returncode": code, "retry": bool(entry.get("retry")),
               "load1_before": round(load[0], 2), "load5_before": round(load[1], 2), "started_utc": started,
               "finished_utc": now(), "load1_after": round(os.getloadavg()[0], 2), "stderr_tail": tail, **result}
        with runs_path.open("a") as handle:
            handle.write(json.dumps(row) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if code and not entry.get("retry"):
            retries.append(dict(entry, retry=True))
        print(f"block {entry['block']} {entry['config']}: {result.get('median_us', f'failed ({code})')}", flush=True)
    print("complete")


if __name__ == "__main__":
    main()
