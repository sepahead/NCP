"""Preregistered analysis of results.json: medians, minima, paired differences, validity."""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

rec = json.loads(Path(sys.argv[1]).read_text())
runs = rec["runs"]
timed = [r for r in runs if r.get("round") is not None]
by = defaultdict(dict)
invalid = []
for r in timed:
    by[(r["arm"], r["delta_ms"])][r["round"]] = r
    if r.get("returncode") != 0 or r.get("spikes") is None or r.get("received") != r.get("spikes"):
        invalid.append((r["arm"], r["delta_ms"], r["round"], r.get("returncode")))
deltas = sorted({d for _, d in by})
arms = ["mono", "chunked", "chunked-spikes", "ncp", "ncp-spikes", "music"]
# validity: spike counts equal the chunked count for the same delta and round
mism = []
for (arm, d), rounds in by.items():
    for k, r in rounds.items():
        ref = by[("chunked", d)].get(k)
        if ref and r.get("spikes") != ref.get("spikes"):
            mism.append((arm, d, k, r.get("spikes"), ref.get("spikes")))
out = {"rounds": sorted({r["round"] for r in timed}), "invalid": invalid, "count_mismatch": mism, "wall": {}, "paired": {}, "secondary": {}}
for a in arms:
    for d in deltas:
        w = [by[(a, d)][k]["wall_s"] for k in sorted(by[(a, d)])]
        out["wall"][f"{a}@{d:g}"] = {"median": statistics.median(w), "min": min(w), "max": max(w), "n": len(w)}
comps = {"ncp-chunked": ("ncp", "chunked"), "ncp_spikes-chunked_spikes": ("ncp-spikes", "chunked-spikes"),
         "music-mono": ("music", "mono"), "chunked-mono": ("chunked", "mono"), "chunked_spikes-chunked": ("chunked-spikes", "chunked")}
for name, (x, y) in comps.items():
    for d in deltas:
        diffs = [by[(x, d)][k]["wall_s"] - by[(y, d)][k]["wall_s"] for k in sorted(by[(x, d)]) if k in by[(y, d)]]
        steps = round(2000 / d)
        out["paired"][f"{name}@{d:g}"] = {"median_s": statistics.median(diffs), "min_s": min(diffs), "max_s": max(diffs),
                                          "per_exchange_us": statistics.median(diffs) / steps * 1e6, "n": len(diffs)}
for a in ("ncp", "ncp-spikes"):
    for d in deltas:
        r = [by[(a, d)][k] for k in sorted(by[(a, d)])]
        out["secondary"][f"{a}@{d:g}"] = {"rtt_median_ms": statistics.median(x["rtt_median_s"] for x in r) * 1e3,
                                          "rtt_p95_ms": statistics.median(x["rtt_p95_s"] for x in r) * 1e3}
for d in deltas:
    r = [by[("music", d)][k] for k in sorted(by[("music", d)])]
    out["secondary"][f"music@{d:g}"] = {"period_median_ms": statistics.median(x["period_median_s"] for x in r) * 1e3,
                                        "period_p95_ms": statistics.median(x["period_p95_s"] for x in r) * 1e3}
spk = {f"{d:g}": sorted({by[("chunked", d)][k]["spikes"] for k in by[("chunked", d)]}) for d in deltas}
out["spikes_per_delta"] = spk
out["load1"] = {"min": min(r["load1"] for r in timed), "median": statistics.median(r["load1"] for r in timed), "max": max(r["load1"] for r in timed)}
print(json.dumps(out, indent=1))
