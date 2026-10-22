#!/usr/bin/env python3
"""Run protocol 2 of the local SDK exchange benchmark (see PROTOCOL-2.md).

Usage: run2.py OUT_JSON --python PYTHON [--smoke]

It reuses the build, run, and environment functions of run.py. It compares the
released sdk-v1.0.0 sources with this checkout in Rust, in Python, and across the
two languages, after both transcript checks. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
import tempfile
from pathlib import Path

import run as base

HERE = base.HERE
ROOT = base.ROOT
RUST_SIZES = (0, 13, 127, 500)
PYTHON_SIZES = (0, 13, 127)
MIXED_SIZES = (0, 127)


def python_transcript(python: str, python_dir: Path) -> str:
    env = dict(os.environ, PYTHONPATH=str(python_dir), PYTHONDONTWRITEBYTECODE="1")
    return base.out([python, "-s", str(HERE / "harness/python/transcript.py")], env=env)


def configurations(python: str, binaries: dict[str, str], python_dirs: dict[str, Path]) -> list[dict]:
    harness = HERE / "harness" / "python"
    configs = [{"name": "raw-rust", "command": [binaries["current"], "raw", str(base.RAW_BYTES)],
                "python_path": f"{python_dirs['current']}{os.pathsep}{harness}"},
               {"name": "raw-python", "command": [python, "-s", str(harness / "raw.py"), str(base.RAW_BYTES)],
                "python_path": f"{python_dirs['current']}{os.pathsep}{harness}"}]
    for variant, binary in binaries.items():
        path = f"{python_dirs[variant]}{os.pathsep}{harness}"
        py_owner = [python, "-s", str(harness / "owner.py")]
        py_client = [python, "-s", str(harness / "client.py")]
        for n in RUST_SIZES:
            configs.append({"name": f"rust-rust-{variant}-n{n}", "command": [binary, "client", str(n)],
                            "owner": [binary, "owner"], "python_path": path})
        for n in PYTHON_SIZES:
            configs.append({"name": f"python-python-{variant}-n{n}", "command": py_client + [str(n)],
                            "owner": py_owner, "python_path": path})
        for n in MIXED_SIZES:
            configs.append({"name": f"python-rust-{variant}-n{n}", "command": py_client + [str(n)],
                            "owner": [binary, "owner"], "python_path": path})
            configs.append({"name": f"rust-python-{variant}-n{n}", "command": [binary, "client", str(n)],
                            "owner": py_owner, "python_path": path})
            configs.append({"name": f"phases-{variant}-n{n}", "command": [binary, "phases", str(n)],
                            "python_path": path})
    return configs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--python", required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    rounds, calls, warmup = (1, 200, 50) if args.smoke else (base.ROUNDS, base.CALLS, base.WARMUP)
    with tempfile.TemporaryDirectory(prefix="ncp-sdk-bench-") as temporary:
        work = Path(temporary)
        tag_commit = base.extract_release(work / "released")
        python_dirs = {"released": work / "released/local/python", "current": ROOT / "local/python"}
        builds = {"released": base.build("released", work / "released/local/rust", work),
                  "current": base.build("current", ROOT / "local/rust", work)}
        rust_transcripts = {variant: base.out([info["binary"], "transcript"]) for variant, info in builds.items()}
        py_transcripts = {variant: python_transcript(args.python, path) for variant, path in python_dirs.items()}
        digest = lambda text: hashlib.sha256(text.encode()).hexdigest()  # noqa: E731
        record = {
            "schema": "ncp.local-sdk-exchange-benchmark.v2",
            "protocol_sha256": hashlib.sha256((HERE / "PROTOCOL-2.md").read_bytes()).hexdigest(),
            "smoke": args.smoke, "seed": base.SEED, "rounds": rounds, "calls": calls, "warmup": warmup,
            "release_tag": base.TAG, "release_commit": tag_commit,
            "current_commit": base.out(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "current_dirty_paths": base.out(["git", "-C", str(ROOT), "status", "--porcelain", "--", "local",
                                             "ncp-core"]).splitlines(),
            "builds": {variant: {k: v for k, v in info.items() if k != "binary"} for variant, info in builds.items()},
            "rust_transcript_lines": len(rust_transcripts["current"].splitlines()),
            "rust_transcript_sha256": {k: digest(v) for k, v in rust_transcripts.items()},
            "rust_transcripts_identical": rust_transcripts["released"] == rust_transcripts["current"],
            "python_transcript_lines": len(py_transcripts["current"].splitlines()),
            "python_transcript_sha256": {k: digest(v) for k, v in py_transcripts.items()},
            "python_transcripts_identical": py_transcripts["released"] == py_transcripts["current"],
            "environment": base.environment(args.python),
            "started_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runs": [],
        }
        if not (record["rust_transcripts_identical"] and record["python_transcripts_identical"]):
            args.out.write_text(json.dumps(record, indent=1) + "\n")
            sys.exit("transcripts differ; no timed runs")
        configs = configurations(args.python, {k: v["binary"] for k, v in builds.items()}, python_dirs)
        rng = random.Random(base.SEED)
        for round_index in range(rounds):
            order = configs[:]
            rng.shuffle(order)
            for config in order:
                result = base.run_once(config, calls, warmup)
                result["round"] = round_index
                record["runs"].append(result)
                print(f"round {round_index} {config['name']}: "
                      f"{result.get('timing', {}).get('median_us', result.get('total_mean_us', 'failed'))}", flush=True)
        record["finished_utc"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.out.write_text(json.dumps(record, indent=1) + "\n")


if __name__ == "__main__":
    main()
