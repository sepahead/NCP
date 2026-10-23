import json, subprocess, sys, os
from collections import Counter
py = sys.executable  # run this script with the Python of the NEST 3.10.0 environment
network, n, threads, delta, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
here = os.path.dirname(os.path.abspath(__file__))
for name in ("nest", "peer"):
    p = f"{here}/{name}.sh"; open(p, "w").write(f'#!/bin/sh\nexec "{py}" -s "{here}/music_{name}.py" "$@"\n'); os.chmod(p, 0o755)
cfg = open(f"{here}/music_config.template").read().replace("STOPTIME", "2.000000").replace("TIMESTEP", f"{delta/1000:.6f}").replace("NEST_LAUNCHER", f"{here}/nest.sh").replace("PEER_LAUNCHER", f"{here}/peer.sh").replace("WIDTH", str(n))
open(f"{here}/b.music", "w").write(cfg)
env = dict(os.environ, PATH=f"{prefix}/bin:/usr/bin:/bin", PYTHONPATH=here, PYNEST_QUIET="1", OMP_NUM_THREADS=str(threads),
           BENCH_SPEC=json.dumps({"network": network, "n": n, "threads": threads, "delta_ms": delta, "seed": seed}),
           BENCH_EVENTS=f"{here}/nest-events.json", BENCH_PEER_EVENTS=f"{here}/peer-events.json")
r = subprocess.run([f"{prefix}/bin/mpiexec", "--oversubscribe", "-n", "2", f"{prefix}/bin/music", f"{here}/b.music"], env=env, cwd=here, capture_output=True, text=True)
if r.returncode: print(r.stderr[-800:]); sys.exit(1)
nest_ev = json.load(open(f"{here}/nest-events.json")); peer = json.load(open(f"{here}/peer-events.json"))
first = nest_ev["first"]
rec = Counter((s - first, round(t, 4)) for s, t in zip(nest_ev["senders"], nest_ev["times"]))
got = Counter((i, round(t * 1000, 4)) for i, t in peer)
missing = rec - got; extra = got - rec
print(f"{network} n={n} t={threads} d={delta}: recorded {sum(rec.values())} received {sum(got.values())} missing {sum(missing.values())} extra {sum(extra.values())}")
if missing: print(" missing sample", sorted(missing.items())[:5], "max time", max(t for (_, t) in missing))
if extra: print(" extra sample", sorted(extra.items())[:5])
dup = sum(c - 1 for c in got.values() if c > 1); print(" duplicate peer events", dup)
