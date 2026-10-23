"""Spike content through NCP and through MUSIC against NEST's recorder (see ../PROTOCOL-CONTENT.md).

Usage: content.py NETWORK N THREADS DELTA_MS SEED OUT_DIR
Runs three processes for one configuration and compares exact (neuron, time) multisets:
  reference  NEST alone, one Run, the recorder's complete events;
  ncp        the Python host with ncp_local 1.0.1 and payload `spikes`; the host keeps every
             delivered (sender, time) pair;
  music      NEST with a MUSIC peer; NEST's recorder and the peer's received events.
Prints one JSON line. Needs PREFIX (conda prefix with NEST and MUSIC) in the environment.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(command, env, cwd):
    process = subprocess.run(command, capture_output=True, text=True, env=env, cwd=cwd, timeout=1800)
    if process.returncode:
        raise SystemExit(f"{command[:3]} failed: {process.stderr[-600:]}")
    return process.stdout


def main() -> None:
    network, n, threads, delta, seed, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), \
        int(sys.argv[5]), Path(sys.argv[6])
    out.mkdir(parents=True, exist_ok=True)
    prefix = Path(os.environ["PREFIX"])
    py = str(prefix / "bin/python")
    env = dict(os.environ, PATH=f"{prefix}/bin:/usr/bin:/bin", PYNEST_QUIET="1", OMP_NUM_THREADS=str(threads))
    spec = {"network": network, "n": n, "threads": threads, "delta_ms": delta, "seed": seed}
    # Reference: one Run with the complete recorder events.
    reference_file, ncp_file = out / "reference.json", out / "ncp.json"
    run([py, "-s", str(HERE / "dump_events.py"), json.dumps(spec), str(reference_file)], env, HERE)
    reference = json.loads(reference_file.read_text())
    first = reference["first"]
    ref = Counter((s - first, round(t, 4)) for s, t in zip(reference["senders"], reference["times"]))
    # NCP: the host keeps every delivered spike.
    run([py, "-s", str(HERE / "py_host.py"), "spikes", network, str(n), str(threads), f"{delta:g}", str(seed)],
        dict(env, NCP_COLLECT_OUT=str(ncp_file)), HERE)
    collected = json.loads(ncp_file.read_text())
    # The owner reports times in steps of the 0.1 ms resolution.
    ncp = Counter((s - first, round(k / 10, 4)) for s, k in zip(collected["senders"], collected["steps"]))
    # MUSIC: NEST recorder events and the peer's received events, through music-threads/compare.py.
    music_dir = out / "music"
    music_dir.mkdir(exist_ok=True)
    for name in ("music_nest.py", "music_peer.py", "compare.py"):
        (music_dir / name).write_text((HERE.parent / "music-threads" / name).read_text())
    for name in ("networks.py", "common.py", "music_config.template"):
        (music_dir / name).write_text((HERE / name).read_text())
    run([sys.executable, str(music_dir / "compare.py"), network, str(n), str(threads), f"{delta:g}", str(seed)],
        dict(env, PYTHONPATH=str(music_dir)), music_dir)
    nest_events = json.loads((music_dir / "nest-events.json").read_text())
    peer_events = json.loads((music_dir / "peer-events.json").read_text())
    mfirst = nest_events["first"]
    recorded = Counter((s - mfirst, round(t, 4)) for s, t in zip(nest_events["senders"], nest_events["times"]))
    delivered = Counter((i, round(t * 1000, 4)) for i, t in peer_events)
    trains, peer = {}, {}
    for (s, t), count in recorded.items():
        trains.setdefault(s, Counter())[t] += count
    for (i, t), count in delivered.items():
        peer.setdefault(i, Counter())[t] += count
    channels_exact = sum(1 for c in range(n) if trains.get(c, Counter()) == peer.get(c, Counter()))
    print(json.dumps({
        **spec,
        "reference_spikes": sum(ref.values()),
        "ncp_spikes": sum(ncp.values()), "ncp_missing": sum((ref - ncp).values()), "ncp_extra": sum((ncp - ref).values()),
        "ncp_exact": ncp == ref,
        "music_recorded": sum(recorded.values()), "music_recorded_equals_reference": recorded == ref,
        "music_delivered": sum(delivered.values()), "music_missing": sum((recorded - delivered).values()),
        "music_extra": sum((delivered - recorded).values()), "music_exact": delivered == recorded,
        "music_channels_exact": channels_exact,
    }))


if __name__ == "__main__":
    main()
