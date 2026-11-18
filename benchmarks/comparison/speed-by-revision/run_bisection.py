#!/usr/bin/env python3
"""Speed bisection of NCP 2 by revision: a diagnostic, not a preregistered protocol (README.md).

It times one small call, client and echo owner of the same commit over a pipe, for the SDKs of
comparison protocol 2 and of each revision 1 to 7, in Rust and in Python. The runs of all
commits alternate in a random order in each round, under the conditions of ../../conditions.py,
so that a slow period of the computer falls on all commits alike.

Usage:
  run_bisection.py prepare WORK   export python/ and rust/ of each commit (git archive), and build
                                  the Rust examples and the clock probe
  run_bisection.py run WORK OUT [--rounds R] [--seed S] [--python PY]
  run_bisection.py count WORK OUT [--python PY]
                                  Python function calls for each exchange, client and owner
  run_bisection.py report OUT     summary.json and summary.md from runs.jsonl and counts.json
"""

from __future__ import annotations

import argparse
import collections
import io
import json
import os
import platform
import pstats
import random
import shutil
import statistics
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
import conditions  # noqa: E402

# (commit, label, date). The first is the commit of comparison protocol 2 (results-2/schedule.json);
# the others are the commits that completed each revision of the specification and both SDKs.
COMMITS = [
    ("c701f568cdaf5fd9f97d36bd13108eb9f0e573d2", "protocol 2", "2026-11-02"),
    ("5300f70", "revision 1", "2026-11-11"),
    ("8940721", "revision 2", "2026-11-13"),
    ("9f58e7a", "revision 3", "2026-11-13"),
    ("2e24ef5", "revision 4", "2026-11-13"),
    ("7edc3f9", "revision 5", "2026-11-14"),
    ("28fb8cc", "revision 6", "2026-11-15"),
    ("727289e", "revision 7", "2026-11-17"),
]
RUST_CALLS, RUST_WARMUP = 20_000, 2_000
PYTHON_CALLS, PYTHON_WARMUP = 3_000, 300
COUNT_CALLS = (1_000, 3_000)


def short(commit: str) -> str:
    return commit[:7]


def git(*args: str) -> bytes:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True).stdout


def prepare(work: Path) -> None:
    for commit, label, _ in COMMITS:
        tree = work / "trees" / short(commit)
        if not tree.exists():
            tree.mkdir(parents=True)
            archive = git("archive", "--format=tar", commit, "python", "rust")
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(tree, filter="data")
        env = dict(os.environ, CARGO_TARGET_DIR=str(work / "target"))
        subprocess.run(
            ["cargo", "build", "--quiet", "--release", "--locked", "--examples"],
            cwd=tree / "rust",
            env=env,
            check=True,
        )
        out = work / "bin" / short(commit)
        out.mkdir(parents=True, exist_ok=True)
        for name in ("bench_client", "echo_owner"):
            shutil.copy2(work / "target" / "release" / "examples" / name, out / name)
        print(f"{short(commit)} {label}: built", flush=True)
    probe = ROOT / "benchmarks" / "nest-campaign" / "harness" / "ncp2-rust7" / "Cargo.toml"
    env = dict(os.environ, CARGO_TARGET_DIR=str(work / "probe-target"))
    subprocess.run(
        ["cargo", "build", "--quiet", "--release", "--locked", "--manifest-path", str(probe), "--bin", "clock-probe"],
        env=env,
        check=True,
    )


def one_run(work: Path, commit: str, language: str, python: str) -> dict:
    if language == "rust":
        binaries = work / "bin" / short(commit)
        argv = [
            str(binaries / "bench_client"),
            str(RUST_CALLS),
            str(RUST_WARMUP),
            "0",
            "--",
            str(binaries / "echo_owner"),
        ]
        env = None
    else:
        argv = [python, "-s", str(HERE / "py_client.py"), str(PYTHON_CALLS), str(PYTHON_WARMUP)]
        env = dict(os.environ, PYTHONPATH=str(work / "trees" / short(commit) / "python"))
    done = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=600)
    if done.returncode != 0:
        raise SystemExit(f"{short(commit)} {language} failed: {done.stderr[-2000:]}")
    result = json.loads(done.stdout.strip().splitlines()[-1])
    result.pop("quantiles_us", None)
    return result


def run(work: Path, out: Path, rounds: int, seed: int, python: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    probe = work / "probe-target" / "release" / "clock-probe"
    python_version = subprocess.run(
        [python, "-c", "import sys; print(sys.version.split()[0])"], capture_output=True, text=True, check=True
    ).stdout.strip()
    head = git("rev-parse", "HEAD").decode().strip()
    clean = not git("status", "--porcelain", "--", str(HERE.relative_to(ROOT))).strip()
    (out / "schedule.json").write_text(
        json.dumps(
            {
                "commits": [{"commit": c, "label": label, "date": date} for c, label, date in COMMITS],
                "rounds": rounds,
                "seed": seed,
                "rust": {
                    "calls": RUST_CALLS,
                    "warmup": RUST_WARMUP,
                    "client": "rust/examples/bench_client.rs",
                    "owner": "rust/examples/echo_owner.rs",
                    "build": "cargo build --release --locked --examples",
                },
                "python": {
                    "calls": PYTHON_CALLS,
                    "warmup": PYTHON_WARMUP,
                    "version": python_version,
                    "client": "benchmarks/comparison/speed-by-revision/py_client.py",
                    "owner": "python/tests/echo_owner.py",
                },
                "request": 'spikes {"step": i, "n": 0}, over a pipe to a child owner',
                "runner_commit": head,
                "runner_clean": clean,
                "machine": platform.machine(),
                "system": f"{platform.system()} {platform.release()}",
                "conditions": {
                    "load_limit": conditions.LOAD_LIMIT,
                    "clock_min_ghz": conditions.CLOCK_MIN_GHZ,
                    "end_clock_min_ghz": conditions.END_CLOCK_MIN_GHZ,
                    "max_attempts": conditions.MAX_ATTEMPTS,
                    "require_ac": False,
                },
                "created_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=1,
        )
        + "\n"
    )
    rng = random.Random(seed)
    with (out / "runs.jsonl").open("a") as sink:
        for round_index in range(rounds):
            jobs = [(commit, language) for commit, _, _ in COMMITS for language in ("rust", "python")]
            rng.shuffle(jobs)
            for commit, language in jobs:
                for attempt in range(1, conditions.MAX_ATTEMPTS + 1):
                    before, waited = conditions.wait(probe, require_ac=False)
                    clocks_before = conditions.clocks()
                    started = datetime.now(timezone.utc).isoformat()
                    result = one_run(work, commit, language, python)
                    clocks_after = conditions.clocks()
                    after = conditions.read(probe)
                    disturbed, slept = conditions.disturbed(clocks_before, clocks_after, after, require_ac=False)
                    record = {
                        "round": round_index,
                        "commit": short(commit),
                        "language": language,
                        "attempt": attempt,
                        "disturbed": disturbed,
                        "slept_s": round(slept, 3),
                        "waited_s": round(waited, 1),
                        "started_utc": started,
                        "before": before,
                        "after": after,
                        **result,
                    }
                    sink.write(json.dumps(record) + "\n")
                    sink.flush()
                    if not disturbed:
                        break
            print(f"round {round_index + 1} of {rounds} done", flush=True)


def module_of(filename: str) -> str | None:
    name = filename.replace("\\", "/")
    if name == "~":
        return None
    if "/ncp/" in name:
        return "ncp/" + name.rsplit("/ncp/", 1)[1]
    if "/json/" in name:
        return "json"
    if name.endswith("/dataclasses.py"):
        return "dataclasses"
    if name.startswith("<string>"):
        return "generated __init__"
    return "other"


def calls_by_module(path: Path) -> collections.Counter:
    """Calls of each module in a profile; a built-in function counts for the module that called it."""
    totals: collections.Counter = collections.Counter()
    for (file, _, _), (_, calls, _, _, callers) in pstats.Stats(str(path)).stats.items():
        module = module_of(file)
        if module is not None:
            totals[module] += calls
            continue
        for (caller_file, _, _), caller_values in callers.items():
            totals[module_of(caller_file) or "built-in"] += caller_values[1]
    return totals


def frame_loads(path: Path) -> int:
    """Calls of json.loads made by the frame decoder."""
    for (file, _, name), (_, _, _, _, callers) in pstats.Stats(str(path)).stats.items():
        if name == "loads" and file.replace("\\", "/").endswith("/json/__init__.py"):
            return sum(v[1] for (cf, _, _), v in callers.items() if cf.replace("\\", "/").endswith("/ncp/frame.py"))
    return 0


def count(work: Path, out: Path, python: str) -> None:
    """Python function calls for each exchange: the difference between sessions of 3,000 and 1,000
    calls, divided by 2,000, in the client and in the owner. A session whose frames the decoder
    parsed a second time is drawn again, so that every commit is counted on the usual path."""
    out.mkdir(parents=True, exist_ok=True)
    scratch = work / "profiles"
    scratch.mkdir(parents=True, exist_ok=True)
    results = {}
    for commit, label, _ in COMMITS:
        env = dict(os.environ, PYTHONPATH=str(work / "trees" / short(commit) / "python"))
        profiles = {}
        for calls in COUNT_CALLS:
            for draw in range(1, 11):
                client = scratch / f"client-{short(commit)}-{calls}.prof"
                owner = scratch / f"owner-{short(commit)}-{calls}.prof"
                subprocess.run(
                    [
                        python,
                        "-s",
                        "-m",
                        "cProfile",
                        "-o",
                        str(client),
                        str(HERE / "py_client.py"),
                        str(calls),
                        "0",
                        str(owner),
                    ],
                    env=env,
                    check=True,
                    capture_output=True,
                    timeout=600,
                )
                # One parse for each frame: about one for each call. The second parse doubles it.
                if frame_loads(client) < 1.5 * calls and frame_loads(owner) < 1.5 * calls:
                    break
            else:
                raise SystemExit(f"{short(commit)}: no session without the second parse in 10 draws")
            profiles[calls] = {"client": calls_by_module(client), "owner": calls_by_module(owner), "draws": draw}
        low, high = COUNT_CALLS
        entry = {"label": label, "draws": [profiles[low]["draws"], profiles[high]["draws"]]}
        for side in ("client", "owner"):
            modules = set(profiles[low][side]) | set(profiles[high][side])
            per = {m: (profiles[high][side][m] - profiles[low][side][m]) / (high - low) for m in sorted(modules)}
            entry[side] = {m: round(v, 2) for m, v in per.items() if abs(v) >= 0.005}
            entry[f"{side}_total"] = round(sum(per.values()), 2)
        results[short(commit)] = entry
        print(f"{short(commit)} {label}: client {entry['client_total']}, owner {entry['owner_total']}", flush=True)
    (out / "counts.json").write_text(json.dumps(results, indent=1) + "\n")


def report(out: Path) -> None:
    runs = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines() if line.strip()]
    kept = [r for r in runs if not r["disturbed"]]
    counts = json.loads((out / "counts.json").read_text()) if (out / "counts.json").exists() else {}
    labels = {short(c): label for c, label, _ in COMMITS}
    summary = {"runs": len(runs), "kept": len(kept), "disturbed": len(runs) - len(kept), "languages": {}}
    lines = [
        "| Commit | SDKs | Rust median (µs) | Step | Python median (µs) | Step | Python calls per exchange |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    previous = {}
    rows = {}
    for commit, label, _ in COMMITS:
        key = short(commit)
        row = {}
        for language in ("rust", "python"):
            mine = [r for r in kept if r["commit"] == key and r["language"] == language]
            usual = [r for r in mine if not r.get("second_parse")]
            medians = sorted(r["median_us"] for r in usual)
            q1, q2, q3 = (
                statistics.quantiles(medians, n=4) if len(medians) >= 4 else (None, statistics.median(medians), None)
            )
            row[language] = {
                "runs": len(mine),
                "second_parse_runs": len(mine) - len(usual),
                "median_us": round(q2, 2),
                "q1_us": q1 and round(q1, 2),
                "q3_us": q3 and round(q3, 2),
                "p99_median_us": round(statistics.median(r["p99_us"] for r in usual), 2),
            }
            if language == "python" and mine:
                slow = [r["median_us"] for r in mine if r.get("second_parse")]
                row[language]["second_parse_median_us"] = round(statistics.median(slow), 2) if slow else None
        rows[key] = row
        cells = []
        for language in ("rust", "python"):
            value = row[language]["median_us"]
            step = "" if language not in previous else f"{value - previous[language]:+.1f}"
            previous[language] = value
            cells += [f"{value:.1f}", step]
        c = counts.get(key)
        calls = f"{c['client_total'] + c['owner_total']:.0f}" if c else ""
        lines.append(f"| `{key}` | {labels[key]} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {calls} |")
    first, last = short(COMMITS[0][0]), short(COMMITS[-1][0])
    for language in ("rust", "python"):
        steps = []
        for (a, _, _), (b, label, _) in zip(COMMITS, COMMITS[1:]):
            steps.append(
                {
                    "to": short(b),
                    "label": label,
                    "step_us": round(rows[short(b)][language]["median_us"] - rows[short(a)][language]["median_us"], 2),
                }
            )
        total = rows[last][language]["median_us"] - rows[first][language]["median_us"]
        summary["languages"][language] = {
            "ratio_last_to_first": round(rows[last][language]["median_us"] / rows[first][language]["median_us"], 3),
            "total_step_us": round(total, 2),
            "steps": steps,
        }
    summary["rows"] = rows
    summary["counts"] = counts
    (out / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    for language in ("rust", "python"):
        s = summary["languages"][language]
        print(
            f"{language}: {s['ratio_last_to_first']}x, "
            + ", ".join(f"{x['label']} {x['step_us']:+.2f}" for x in s["steps"])
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("work", type=Path)
    p = sub.add_parser("run")
    p.add_argument("work", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--rounds", type=int, default=15)
    p.add_argument("--seed", type=int, default=20261119)
    p.add_argument("--python", default=sys.executable)
    p = sub.add_parser("count")
    p.add_argument("work", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--python", default=sys.executable)
    p = sub.add_parser("report")
    p.add_argument("out", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.work.resolve())
    elif args.command == "run":
        run(args.work.resolve(), args.out.resolve(), args.rounds, args.seed, args.python)
    elif args.command == "count":
        count(args.work.resolve(), args.out.resolve(), args.python)
    else:
        report(args.out.resolve())


if __name__ == "__main__":
    main()
