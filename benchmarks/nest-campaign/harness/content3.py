"""Spikes and membrane potentials through NCP 2 revision 7 against NEST alone (see
../PROTOCOL-CONTENT-3.md).

Usage: content3.py NETWORK N THREADS DELTA_MS SEED OUT_DIR
       content3.py --self-test   (shows that the comparison detects each kind of difference)
Runs three processes for one configuration and compares exact multisets:
  reference  NEST alone (dump_events7.py), one Simulate of the whole run;
  ncp2_py    the NCP 2 Python host (ncp2_host7.py), one Simulate and one exchange per interval;
  ncp2_rs    the NCP 2 Rust host (harness/ncp2-rust7), the same.
A spike is (neuron, step, the bits of its offset); a sample of the membrane potential is (neuron,
step, the bits of its value), with the neuron counted from the first neuron of the network.
Prints one JSON line. Needs PREFIX (conda prefix with NEST), NCP2_PYTHON (the NCP 2 Python SDK
directory), and NCP2_HOST7 (the Rust host binary) in the environment.
"""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(command: list[str], env: dict, cwd: Path) -> str:
    process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd, timeout=3600)
    if process.returncode:
        raise SystemExit(f"{command[:3]} failed: {process.stderr[-800:]}")
    return process.stdout


def bits(value) -> bytes:
    """The eight bytes of a float64; a value that is not a number (null from JSON) has no bits."""
    return struct.pack("<d", value) if isinstance(value, float) else b"not a float64"


def multisets(events: dict) -> tuple[Counter, Counter]:
    first = events["first"]
    spikes = Counter(zip((s - first for s in events["senders"]), events["steps"], map(bits, events["offsets"])))
    vm = Counter(zip((s - first for s in events["vm_senders"]), events["vm_steps"], map(bits, events["vm_values"])))
    return spikes, vm


def compare(name: str, reference: tuple[Counter, Counter], received: tuple[Counter, Counter], emitted: dict) -> dict:
    row = {}
    for kind, expected, got in (("spikes", reference[0], received[0]), ("vm", reference[1], received[1])):
        row[f"{name}_{kind}"] = sum(got.values())
        row[f"{name}_{kind}_missing"] = sum((expected - got).values())
        row[f"{name}_{kind}_extra"] = sum((got - expected).values())
        row[f"{name}_{kind}_exact"] = got == expected
    row[f"{name}_owner_sent_equals_received"] = emitted["owner_sent"] == {
        "spikes": row[f"{name}_spikes"], "vm": row[f"{name}_vm"]}
    row[f"{name}_child_exit"] = emitted["child_exit"]
    return row


def self_test() -> None:
    """Each change of one received event, and nothing else, must make the comparison inexact."""
    events = {"first": 11, "senders": [11, 12, 12, 40], "steps": [3, 3, 9, 20], "offsets": [0.0, 0.025, 0.0, 0.0999],
              "vm_senders": [11, 11, 12], "vm_steps": [1, 2, 1], "vm_values": [-70.0, -69.99999999999999, -65.5]}
    reference = multisets(events)
    emitted = {"owner_sent": {"spikes": 4, "vm": 3}, "child_exit": 0}
    assert all(value for key, value in compare("x", reference, multisets(events), emitted).items()
               if key.endswith("_exact") or key.endswith("_received"))
    changes = {
        "a spike lost": ("senders", lambda e: {**e, **{k: e[k][:-1] for k in ("senders", "steps", "offsets")}}),
        "a spike twice": ("senders", lambda e: {**e, **{k: e[k] + e[k][-1:] for k in ("senders", "steps", "offsets")}}),
        "another neuron": ("senders", lambda e: {**e, "senders": [11, 12, 13, 40]}),
        "another step": ("senders", lambda e: {**e, "steps": [3, 3, 9, 21]}),
        "an offset one ulp off": ("senders", lambda e: {**e, "offsets": [0.0, math.nextafter(0.025, 1), 0.0, 0.0999]}),
        "-0.0 for 0.0": ("senders", lambda e: {**e, "offsets": [-0.0, 0.025, 0.0, 0.0999]}),
        "a potential one ulp off": ("vm", lambda e: {**e, "vm_values": [-70.0, -69.99999999999999,
                                                                         math.nextafter(-65.5, 0)]}),
        "a potential that is not a number": ("vm", lambda e: {**e, "vm_values": [-70.0, None, -65.5]}),
        "a sample lost": ("vm", lambda e: {**e, **{k: e[k][:-1] for k in ("vm_senders", "vm_steps", "vm_values")}}),
    }
    for label, (kind, change) in changes.items():
        row = compare("x", reference, multisets(change(events)), emitted)
        assert not row[f"x_{'spikes' if kind == 'senders' else 'vm'}_exact"], label
    print(f"self-test: the comparison detects all {len(changes)} kinds of difference")


def main() -> None:
    if sys.argv[1:] == ["--self-test"]:
        return self_test()
    network, n, threads, delta, seed, out = (
        sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), Path(sys.argv[6]))
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
    reference_file = out / "reference.json"
    run([py, "-s", str(HERE / "dump_events7.py"), json.dumps(spec), str(reference_file)], env, HERE)
    reference = multisets(json.loads(reference_file.read_text()))
    row = {**spec, "reference_spikes": sum(reference[0].values()), "reference_vm": sum(reference[1].values()),
           "reference_off_grid": sum(count for (_, _, offset), count in reference[0].items()
                                     if offset != struct.pack("<d", 0.0))}
    hosts = {
        "ncp2_py": [py, "-s", str(HERE / "ncp2_host7.py"), *arguments, str(out / "ncp2_py.json")],
        "ncp2_rs": [os.environ["NCP2_HOST7"], *arguments, str(out / "ncp2_rs.json"),
                    str(HERE / "ncp2_contract.json"), py, "-s", str(HERE / "ncp2_owner7.py")],
    }
    for name, command in hosts.items():
        emitted = json.loads(run(command, env, HERE).strip().splitlines()[-1])
        received = multisets(json.loads((out / f"{name}.json").read_text()))
        row.update(compare(name, reference, received, emitted))
    print(json.dumps(row))


if __name__ == "__main__":
    main()
