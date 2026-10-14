#!/usr/bin/env python3
"""Run the preregistered NEST coupling benchmark (see PREREGISTRATION.md).

Usage: run_bench.py PREFIX NCP_PYTHON_DIR OUT_JSON [--smoke]
PREFIX is the conda environment holding NEST 3.10.0 with MPI and MUSIC 1.2.1.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DELTAS = [1.0, 2.0, 5.0, 10.0]
ARMS = ["mono", "chunked", "chunked-spikes", "ncp", "ncp-spikes", "music"]
ROUNDS = 5
SEED = 20261013


def environment(prefix: Path, ncp_dir: Path) -> dict:
    py = str(prefix / "bin" / "python")
    def out(cmd):
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    return {
        "nest": out([py, "-c", "import nest; print(nest.__version__)"]).splitlines()[-1],
        "build_info": json.loads(out([py, "-c", "import nest, json; b = nest.build_info; "
                                          "print(json.dumps({k: b[k] for k in ('have_mpi', 'have_music', 'threads_model')}))"])
                                 .splitlines()[-1]),
        "music": out([str(prefix / "bin" / "music"), "--version"]).splitlines()[0],
        "mpi": out([str(prefix / "bin" / "mpiexec"), "--version"]).splitlines()[0],
        "python": out([py, "-c", "import sys; print(sys.version.split()[0])"]),
        "ncp_local_dir": str(ncp_dir),
        "machine": out(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "cores": out(["sysctl", "-n", "hw.ncpu"]),
        "os": platform.platform(),
        "preregistration_sha256": hashlib.sha256((HERE / "PREREGISTRATION.md").read_bytes()).hexdigest(),
        "params": json.loads((HERE / "params.json").read_text()),
    }


def run_once(arm: str, delta: float, prefix: Path, env: dict) -> dict:
    py = str(prefix / "bin" / "python")
    started = time.time()
    if arm in ("mono", "chunked", "chunked-spikes"):
        proc = subprocess.run([py, str(HERE / "arm_local.py"), arm, str(delta)], capture_output=True,
                              text=True, env=env, cwd=HERE)
        result = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 else {}
        result["received"] = result.get("spikes")
    elif arm in ("ncp", "ncp-spikes"):
        payload = "count" if arm == "ncp" else "spikes"
        proc = subprocess.run([py, str(HERE / "ncp_host.py"), str(delta), payload], capture_output=True, text=True,
                              env=env, cwd=HERE)
        result = json.loads(proc.stdout.strip().splitlines()[-1]) if proc.returncode == 0 else {}
        result["received"] = result.get("spikes")
    else:
        work = Path(tempfile.mkdtemp(prefix="music-", dir=env["TMPDIR"]))
        width = json.loads((HERE / "params.json").read_text())["n"]
        launchers = {}
        for name, script in (("nest", "music_nest.py"), ("peer", "music_peer.py")):
            launcher = work / f"{name}.sh"
            launcher.write_text(f'#!/bin/sh\nexec "{py}" "{HERE / script}" "$@"\n')
            launcher.chmod(0o755)
            launchers[name] = str(launcher)
        config = (HERE / "music_config.template").read_text()
        config = (config.replace("STOPTIME", f"{2.0:.6f}").replace("TIMESTEP", f"{delta / 1000.0:.6f}")
                  .replace("NEST_LAUNCHER", launchers["nest"]).replace("PEER_LAUNCHER", launchers["peer"])
                  .replace("WIDTH", str(width)))
        (work / "bench.music").write_text(config)
        run_env = dict(env, BENCH_DELTA_MS=str(delta), BENCH_OUT=str(work / "nest.json"),
                       BENCH_PEER_OUT=str(work / "peer.json"))
        proc = subprocess.run([str(prefix / "bin" / "mpiexec"), "--oversubscribe", "-n", "2",
                               str(prefix / "bin" / "music"), str(work / "bench.music")],
                              capture_output=True, text=True, env=run_env, cwd=work)
        result = {}
        if proc.returncode == 0 and (work / "nest.json").exists() and (work / "peer.json").exists():
            result = json.loads((work / "nest.json").read_text())
            peer = json.loads((work / "peer.json").read_text())
            result.update({"received": peer["received"], "ticks": peer["ticks"],
                           "period_median_s": peer["period_median_s"], "period_p95_s": peer["period_p95_s"]})
    result.update({"arm": arm, "delta_ms": delta, "returncode": proc.returncode,
                   "process_wall_s": time.time() - started,
                   "stderr_tail": proc.stderr[-400:] if proc.returncode else ""})
    return result


def main() -> None:
    prefix, ncp_dir, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    smoke = "--smoke" in sys.argv
    tmp = Path(os.environ.get("BENCH_TMP", tempfile.gettempdir()))
    env = {"HOME": os.environ["HOME"], "PATH": f"{prefix}/bin:/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": str(tmp),
           "PYTHONPATH": f"{HERE}:{ncp_dir}", "OMP_NUM_THREADS": "1"}
    record = {"environment": environment(prefix, ncp_dir), "smoke": smoke, "runs": []}
    pairs = [(a, d) for d in DELTAS for a in ARMS]
    if smoke:
        for arm, delta in [(a, d) for d in (1.0, 10.0) for a in ARMS]:
            record["runs"].append(dict(run_once(arm, delta, prefix, env), round="smoke"))
            print(json.dumps(record["runs"][-1]), flush=True)
    else:
        for arm, delta in pairs:
            run_once(arm, delta, prefix, env)  # warm-up, discarded
        for rnd in range(ROUNDS):
            order = pairs[:]
            random.Random(SEED + rnd).shuffle(order)
            for arm, delta in order:
                result = run_once(arm, delta, prefix, env)
                result["round"] = rnd
                record["runs"].append(result)
                print(json.dumps(result), flush=True)
    out.write_text(json.dumps(record, indent=1) + "\n")


if __name__ == "__main__":
    main()
