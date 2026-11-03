#!/usr/bin/env python3
"""Run the multi-agent benchmark (see PROTOCOL.md). Resumable.

Usage: run.py RESULTS_DIR --python PYTHON --mpi-env MPI_ENV [--smoke]

PYTHON runs the Python programs of parts F and R (standard library only). MPI_ENV is a conda
environment with Open MPI, mpi4py, and numpy for part M (MPI_ENV/bin/python, MPI_ENV/bin/mpirun).
The first call checks validity (validity.json) and writes the schedule (schedule.json): three
blocks, each with every configuration once, in an order shuffled with a fixed seed. Before each
run, the runner waits for the conditions of ../conditions.py, and it repeats a disturbed run, at
most three times in all. Each finished run is appended to runs.jsonl and synced to disk, so a
lost session loses at most the run in progress; a later call skips recorded runs. Needs cargo.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import random
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
import conditions  # noqa: E402

PROTOCOL = "PROTOCOL.md"
SEED = 20261103
BLOCKS = 3
HOSTS = ("rust", "python")
MODES = ("all", "pool", "split", "sequential", "raw")
SESSIONS = (1, 4, 16, 64, 256)
WAITS_US = (0, 1000)
WORLD_MODES = ("rounds", "arrival")
RANKS = (0, 1, 2, 4, 8)  # 0: the same owner without MPI
SPIKES = (0, 1788, 87381)
ROUNDS = (200, 20)  # measured rounds and warm-up rounds of parts F and R
CALLS = {0: (2000, 100), 1788: (2000, 100), 87381: (300, 30)}  # part M
SMOKE_ROUNDS = (20, 2)
SMOKE_CALLS = (50, 5)
TIMEOUT_S = {"F": 1800, "R": 600, "M": 600}


def now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def out(command: list[str], **kwargs) -> str:
    return subprocess.run(command, capture_output=True, text=True, check=True, **kwargs).stdout.strip()


def cargo_build(manifest: Path, target: Path) -> None:
    command = ["cargo", "build", "--release", "--locked", "--quiet", "--manifest-path", str(manifest)]
    subprocess.run(command, check=True, env=dict(os.environ, CARGO_TARGET_DIR=str(target)))


def build(work: Path) -> dict[str, Path]:
    """Build the harness and the clock probe of the NEST campaign."""
    cargo_build(HERE / "harness" / "rust" / "Cargo.toml", work / "harness-target")
    cargo_build(ROOT / "benchmarks" / "nest-campaign" / "harness" / "ncp2-rust" / "Cargo.toml", work / "probe-target")
    return {
        "harness": work / "harness-target" / "release" / "ncp-multi-agent-bench",
        "clock_probe": work / "probe-target" / "release" / "clock-probe",
    }


def configurations() -> dict[str, dict]:
    configs: dict[str, dict] = {}
    for host in HOSTS:
        for mode in MODES:
            for n in SESSIONS:
                for wait_us in WAITS_US:
                    name = f"F-{host}-{mode}-n{n}-w{wait_us}"
                    configs[name] = {"part": "F", "host": host, "mode": mode, "n": n, "wait_us": wait_us}
    for mode in WORLD_MODES:
        for n in SESSIONS:
            configs[f"R-{mode}-n{n}"] = {"part": "R", "mode": mode, "n": n}
    for ranks in RANKS:
        for spikes in SPIKES:
            configs[f"M-ranks{ranks}-spikes{spikes}"] = {"part": "M", "ranks": ranks, "spikes": spikes}
    return configs


def environment() -> dict[str, str]:
    return {"PYTHONPATH": str(ROOT / "python"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}


def stop(process: subprocess.Popen, timeout: float = 10.0) -> None:
    """Stop a process and its process group."""
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def start_server(command: list[str], env: dict[str, str]) -> tuple[subprocess.Popen | None, str]:
    """Start an owner that prints "ready PATH". Returns it, or None and the reason."""
    server = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, start_new_session=True
    )
    line = server.stdout.readline().split(maxsplit=1)  # type: ignore[union-attr]
    if len(line) != 2 or line[0] != "ready":
        stop(server)
        return None, f"owner did not start: {line!r} {server.stderr.read()[-300:]!r}"  # type: ignore[union-attr]
    return server, ""


def run_client(command: list[str], env: dict[str, str], timeout: float) -> tuple[int, dict, list[str]]:
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, start_new_session=True
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        stop(process)
        return 124, {}, ["timeout"]
    lines = stdout.strip().splitlines()
    result = json.loads(lines[-1]) if process.returncode == 0 and lines else {}
    return process.returncode, result, stderr.strip().splitlines()[-3:]


def run_one(
    config: dict, sizes: tuple[int, int], python: str, mpi_env: Path, binaries: dict[str, Path], env: dict
) -> tuple[int, dict, list[str]]:
    """Run one configuration. Returns (code, result, stderr tail)."""
    measured, warmup = sizes
    harness = str(binaries["harness"])
    part = config["part"]
    if part == "F":
        arguments = [str(config["n"]), str(measured), str(warmup), config["mode"], str(config["wait_us"])]
        if config["host"] == "rust":
            command = [harness, "fanout", *arguments]
        else:
            command = [python, "-s", str(HERE / "harness" / "python" / "fanout.py"), *arguments, harness]
        return run_client(command, env, TIMEOUT_S["F"])
    directory = tempfile.mkdtemp(prefix="ncpma", dir="/tmp")  # socket paths must be short
    socket_path = f"{directory}/s"
    server = None
    try:
        if part == "R":
            owner = [
                python,
                "-s",
                str(HERE / "harness" / "python" / "world_owner.py"),
                config["mode"],
                socket_path,
                str(config["n"]),
            ]
            server, reason = start_server(owner, env)
            if server is None:
                return 1, {}, [reason]
            command = [harness, "agents", str(config["n"]), str(measured), str(warmup), socket_path, config["mode"]]
            code, result, tail = run_client(command, env, TIMEOUT_S["R"])
            server.send_signal(signal.SIGTERM)
            try:
                report, errors = server.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                stop(server)
                return 1, result, ["the world owner did not stop"]
            lines = report.strip().splitlines()
            result["owner"] = json.loads(lines[-1]) if lines else {}
            if server.returncode != 0 or not lines:
                return code or 1, result, tail + errors.strip().splitlines()[-3:]
            return code, result, tail
        script = str(HERE / "harness" / "python" / "mpi_owner.py")
        mpi_python = str(mpi_env / "bin" / "python")
        if config["ranks"] == 0:
            owner = [mpi_python, "-s", script, socket_path, "--no-mpi"]
        else:
            owner = [str(mpi_env / "bin" / "mpirun"), "-n", str(config["ranks"])]
            for name in ("PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED"):
                owner += ["-x", name]  # explicit, although the ranks of one computer inherit them
            owner += [mpi_python, "-s", script, socket_path]
        server, reason = start_server(owner, dict(env, TMPDIR="/tmp"))
        if server is None:
            return 1, {}, [reason]
        command = [harness, "spikes", socket_path, str(config["spikes"]), str(measured), str(warmup)]
        code, result, tail = run_client(command, env, TIMEOUT_S["M"])
        try:
            _, errors = server.communicate(timeout=60)  # rank 0 ends after the client closes
        except subprocess.TimeoutExpired:
            stop(server)
            return code or 1, result, tail + ["the rank-0 owner did not stop"]
        if server.returncode != 0:
            return code or 1, result, tail + errors.strip().splitlines()[-3:]
        return code, result, tail
    finally:
        if server is not None:
            stop(server)
            for stream in (server.stdout, server.stderr):
                if stream is not None:
                    stream.close()
        shutil.rmtree(directory, ignore_errors=True)


def sizes_of(config: dict, smoke: bool) -> tuple[int, int]:
    if config["part"] == "M":
        return SMOKE_CALLS if smoke else CALLS[config["spikes"]]
    return SMOKE_ROUNDS if smoke else ROUNDS


def validity(python: str, mpi_env: Path, binaries: dict[str, Path], configs: dict[str, dict], env: dict) -> dict:
    """The checks that must pass before any timed run: the SDK tests, MPI, and one short run of
    each part."""
    record: dict = {}
    checks = [
        ("python_sdk_tests", [python, "-s", str(ROOT / "python" / "tests" / "test_ncp.py")], {}),
        ("python_rounds_tests", [python, "-s", str(ROOT / "python" / "tests" / "test_rounds.py")], {}),
        (
            "rust_sdk_tests",
            ["cargo", "test", "--release", "--locked", "--quiet", "--manifest-path", str(ROOT / "rust" / "Cargo.toml")],
            {"CARGO_TARGET_DIR": str(binaries["harness"].parents[2] / "sdk-target")},
        ),
        (
            "mpi_python_imports",
            [
                str(mpi_env / "bin" / "python"),
                "-s",
                "-c",
                "import mpi4py, numpy, ncp; print(mpi4py.__version__, numpy.__version__)",
            ],
            {},
        ),
    ]
    for name, command, extra in checks:
        process = subprocess.run(command, capture_output=True, text=True, env=dict(os.environ, **env, **extra))
        record[name] = {
            "returncode": process.returncode,
            "tail": (process.stdout + process.stderr).strip().splitlines()[-3:],
        }
    full_env = dict(os.environ, **env)
    for name in ("F-rust-all-n4-w0", "F-python-all-n4-w0", "R-rounds-n4", "R-arrival-n4", "M-ranks2-spikes1788"):
        sizes = SMOKE_CALLS if configs[name]["part"] == "M" else SMOKE_ROUNDS
        code, result, tail = run_one(configs[name], sizes, python, mpi_env, binaries, full_env)
        record[f"smoke_{name}"] = {"returncode": code, "result": result, "tail": tail}
    return record


def describe_environment(python: str, mpi_env: Path) -> dict:
    def safe(command: list[str]) -> str:
        try:
            return out(command)
        except (OSError, subprocess.CalledProcessError):
            return "unavailable"

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    mpi_python = str(mpi_env / "bin" / "python")
    return {
        "computer": safe(["sysctl", "-n", "hw.model"]),
        "chip": safe(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "cores": safe(["sysctl", "-n", "hw.ncpu"]),
        "performance_cores": safe(["sysctl", "-n", "hw.perflevel0.physicalcpu"]),
        "memory_bytes": safe(["sysctl", "-n", "hw.memsize"]),
        "os": safe(["sw_vers", "-productVersion"]),
        "kernel": platform.release(),
        "somaxconn": safe(["sysctl", "-n", "kern.ipc.somaxconn"]),
        "open_file_limit": list(resource.getrlimit(resource.RLIMIT_NOFILE)),
        "power": (safe(["pmset", "-g", "batt"]).splitlines() or ["unavailable"])[0],
        "rustc": safe(["rustc", "--version"]),
        "cargo": safe(["cargo", "--version"]),
        "python": safe([python, "-c", "import sys; print(sys.version.split()[0])"]),
        "mpi_python": safe([mpi_python, "-c", "import sys; print(sys.version.split()[0])"]),
        "mpi_packages": safe(
            [
                mpi_python,
                "-s",
                "-c",
                "import mpi4py, numpy; print('mpi4py', mpi4py.__version__, 'numpy', numpy.__version__)",
            ]
        ),
        "mpirun": (safe([str(mpi_env / "bin" / "mpirun"), "--version"]).splitlines() or ["unavailable"])[0],
        "ncp_commit": safe(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "ncp_worktree_clean": safe(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
        "cargo_lock_sha256": {
            "sdk": digest(ROOT / "rust" / "Cargo.lock"),
            "harness": digest(HERE / "harness" / "rust" / "Cargo.lock"),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--mpi-env", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true", help="one short block, for testing the runner")
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    work = args.results / ".work"
    work.mkdir(exist_ok=True)
    binaries = build(work)
    configs = configurations()
    env = environment()
    schedule_path = args.results / "schedule.json"
    if not schedule_path.exists():
        record = validity(args.python, args.mpi_env, binaries, configs, env)
        record["environment"] = describe_environment(args.python, args.mpi_env)
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
        schedule = {
            "protocol": PROTOCOL,
            "protocol_sha256": hashlib.sha256((HERE / PROTOCOL).read_bytes()).hexdigest(),
            "seed": SEED,
            "blocks": blocks,
            "smoke": args.smoke,
            "rounds": ROUNDS,
            "calls": {str(k): v for k, v in CALLS.items()},
            "created_utc": now(),
            "commit": out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "worktree_clean": out(["git", "-C", str(ROOT), "status", "--porcelain"]) == "",
            "conditions": {
                "load_limit": conditions.LOAD_LIMIT,
                "clock_min_ghz": conditions.CLOCK_MIN_GHZ,
                "end_clock_min_ghz": conditions.END_CLOCK_MIN_GHZ,
                "max_attempts": conditions.MAX_ATTEMPTS,
                "sleep_limit_s": conditions.SLEEP_LIMIT_S,
            },
            "order": order,
        }
        schedule_path.write_text(json.dumps(schedule, indent=1) + "\n")
    schedule = json.loads(schedule_path.read_text())
    runs_path = args.results / "runs.jsonl"
    done, failed_once, attempts = set(), set(), {}
    if runs_path.exists():
        for line in runs_path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                key = (row["block"], row["config"])
                if row.get("retry"):
                    done.add(key)
                elif row["returncode"] == 0:
                    attempts[key] = attempts.get(key, 0) + 1
                    if not row.get("disturbed") or attempts[key] >= conditions.MAX_ATTEMPTS:
                        done.add(key)
                else:
                    failed_once.add(key)
    # A failed run is repeated once, after all scheduled runs (PROTOCOL.md, exclusions).
    queue = deque(entry for entry in schedule["order"] if (entry["block"], entry["config"]) not in done | failed_once)
    retries = deque(
        dict(entry, retry=True)
        for entry in schedule["order"]
        if (entry["block"], entry["config"]) in failed_once - done
    )
    full_env = dict(os.environ, **env)
    while queue or retries:
        entry = queue.popleft() if queue else retries.popleft()
        key = (entry["block"], entry["config"])
        config = configs[entry["config"]]
        sizes = sizes_of(config, schedule["smoke"])
        while True:
            before, waited = conditions.wait(binaries["clock_probe"])
            load = os.getloadavg()
            started = now()
            clocks_before = conditions.clocks()
            code, result, tail = run_one(config, sizes, args.python, args.mpi_env, binaries, full_env)
            clocks_after = conditions.clocks()
            after = conditions.read(binaries["clock_probe"])
            disturbed, slept = conditions.disturbed(clocks_before, clocks_after, after)
            if code == 0:
                attempts[key] = attempts.get(key, 0) + 1
            row = {"block": entry["block"], "config": entry["config"], **config}
            row.update(
                {
                    "returncode": code,
                    "retry": bool(entry.get("retry")),
                    "attempt": attempts.get(key, 0),
                    "disturbed": disturbed,
                    "slept_s": round(slept, 3),
                    "waited_s": round(waited, 1),
                    "before": before,
                    "after": after,
                    "load1_before": round(load[0], 2),
                    "started_utc": started,
                    "finished_utc": now(),
                    "stderr_tail": tail,
                    "result": result,
                }
            )
            with runs_path.open("a") as handle:
                handle.write(json.dumps(row) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            stats = result.get("round") or result.get("call") or {}
            outcome = f"{stats['median_us']:.1f} us" if "median_us" in stats else f"failed ({code})"
            print(
                f"block {entry['block']} {entry['config']}: {outcome}" + (" disturbed" if disturbed else ""), flush=True
            )
            if code and not entry.get("retry"):
                retries.append(dict(entry, retry=True))
                break
            if code or not disturbed or entry.get("retry") or attempts[key] >= conditions.MAX_ATTEMPTS:
                break
    print("complete")


if __name__ == "__main__":
    main()
