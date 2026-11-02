"""Spike content through NCP 2 against NEST's recorder (see ../PROTOCOL-CONTENT-2.md).

Usage: content2.py NETWORK N THREADS DELTA_MS SEED OUT_DIR
Runs three processes for one configuration and compares exact (neuron, time) multisets:
  reference  NEST alone, one Run, the recorder's complete events;
  ncp2-py    the NCP 2 Python host (ncp2_host.py) with the payload `spikes`;
  ncp2-rs    the NCP 2 Rust host (harness/ncp2-rust) with the payload `spikes`.
Both hosts drive the NEST owner ncp2_owner.py and keep every received (sender, step) pair.
Prints one JSON line. Needs PREFIX (conda prefix with NEST), NCP2_PYTHON (the NCP 2 Python SDK
directory), and NCP2_HOST (the Rust host binary) in the environment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(command: list[str], env: dict, cwd: Path) -> str:
    process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd, timeout=1800)
    if process.returncode:
        raise SystemExit(f"{command[:3]} failed: {process.stderr[-600:]}")
    return process.stdout


def compare(name: str, reference: Counter, first: int, collected: dict, emitted: dict) -> dict:
    # The owner reports times in steps of the 0.1 ms resolution.
    received = Counter((s - first, round(k / 10, 4)) for s, k in zip(collected["senders"], collected["steps"]))
    return {
        f"{name}_spikes": sum(received.values()),
        f"{name}_missing": sum((reference - received).values()),
        f"{name}_extra": sum((received - reference).values()),
        f"{name}_exact": received == reference,
        f"{name}_count_equals_recorded": emitted["spikes"] == emitted["recorded"],
    }


def main() -> None:
    network, n, threads, delta, seed, out = (
        sys.argv[1],
        int(sys.argv[2]),
        int(sys.argv[3]),
        float(sys.argv[4]),
        int(sys.argv[5]),
        Path(sys.argv[6]),
    )
    out.mkdir(parents=True, exist_ok=True)
    prefix = Path(os.environ["PREFIX"])
    py = str(prefix / "bin" / "python")
    env = {
        "HOME": os.environ["HOME"],
        "PATH": f"{prefix}/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "TMPDIR": str(out),
        "PYTHONPATH": f"{HERE}{os.pathsep}{os.environ['NCP2_PYTHON']}",
        "OMP_NUM_THREADS": str(threads),
        "PYNEST_QUIET": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    spec = {"network": network, "n": n, "threads": threads, "delta_ms": delta, "seed": seed}
    arguments = [network, str(n), str(threads), f"{delta:g}", str(seed)]
    # Reference: one Run with the complete recorder events.
    reference_file = out / "reference.json"
    run([py, "-s", str(HERE / "dump_events.py"), json.dumps(spec), str(reference_file)], env, HERE)
    reference = json.loads(reference_file.read_text())
    first = reference["first"]
    expected = Counter((s - first, round(t, 4)) for s, t in zip(reference["senders"], reference["times"]))
    row = {**spec, "reference_spikes": sum(expected.values())}
    hosts = {
        "ncp2_py": [py, "-s", str(HERE / "ncp2_host.py"), "spikes", *arguments],
        "ncp2_rs": [
            os.environ["NCP2_HOST"],
            "spikes",
            *arguments,
            str(HERE / "ncp2_contract.json"),
            py,
            "-s",
            str(HERE / "ncp2_owner.py"),
        ],
    }
    for name, command in hosts.items():
        collect_file = out / f"{name}.json"
        stdout = run(command, dict(env, NCP_COLLECT_OUT=str(collect_file)), HERE)
        emitted = json.loads(stdout.strip().splitlines()[-1])
        row.update(compare(name, expected, first, json.loads(collect_file.read_text()), emitted))
    print(json.dumps(row))


if __name__ == "__main__":
    main()
