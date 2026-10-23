#!/usr/bin/env python3
"""Compute the measures and hypotheses of the NEST campaign (see PROTOCOL.md).

Usage: analyze.py RESULTS_DIR [RUN1_RESULTS_DIR]. Writes RESULTS_DIR/analysis.json. Standard library only.
With RUN1_RESULTS_DIR (protocol 2), H6 compares the recorder totals with run 1.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

T_BIO_S = 2.0


def key_of(row) -> tuple:
    return (row["part"], row["network"], row["n"], row["threads"], row["delta_ms"])


def arm_of(row) -> str:
    """The protocol arm, from the configuration name.

    The runner's own `arm` field omits the SDK version (`ncp-py-count` for both 1.0.0 and
    1.0.1), so the configuration name, which ends with the protocol arm, is authoritative.
    """
    return "-".join(row["config"].split("-")[5:])


def main() -> None:
    results = Path(sys.argv[1])
    rows = [json.loads(line) for line in (results / "runs.jsonl").read_text().splitlines() if line.strip()]
    schedule = json.loads((results / "schedule.json").read_text())
    runs = defaultdict(dict)  # (config key, block) -> arm -> row
    invalid = []
    for row in rows:
        ok = row["returncode"] == 0 and "wall_s" in row
        arm = arm_of(row)
        if ok and arm.startswith("ncp") and row.get("spikes") != row.get("recorded"):
            ok = False
        if ok and arm == "music" and row["threads"] == 1 and row.get("spikes") != row.get("recorded"):
            ok = False
        if not ok:
            invalid.append(f"{row['config']} block {row['block']}")
            continue
        runs[(key_of(row), row["block"])][arm] = row
    # Cross-arm agreement of NEST's own recorded counts.
    disagreements = []
    for (key, block), arms in runs.items():
        counts = {arm: row["recorded"] for arm, row in arms.items()}
        if len(set(counts.values())) > 1:
            disagreements.append({"config": list(key), "block": block, "counts": counts})
    music_delivery = []
    per_exchange = defaultdict(lambda: defaultdict(list))  # config key -> arm -> per-block O in ms
    music_cost = defaultdict(list)
    wall = defaultdict(lambda: defaultdict(list))
    for (key, block), arms in runs.items():
        for arm, row in arms.items():
            wall[key][arm].append(row["wall_s"])
        for arm, row in arms.items():
            if arm.startswith("ncp"):
                reference = arms.get("chunked-spikes" if arm.endswith("-spikes") else "chunked")
                if reference:
                    per_exchange[key][arm].append(1000.0 * (row["wall_s"] - reference["wall_s"]) / row["exchanges"])
        if "music" in arms and "mono" in arms:
            music_cost[key].append(arms["music"]["wall_s"] - arms["mono"]["wall_s"])
        if "music" in arms:
            row = arms["music"]
            music_delivery.append({"config": list(key), "block": block, "threads": row["threads"],
                                   "recorded": row["recorded"], "delivered": row.get("spikes")})
    configs = {}
    for key in sorted(wall):
        entry = {"part": key[0], "network": key[1], "n": key[2], "threads": key[3], "delta_ms": key[4],
                 "wall_s_median": {arm: statistics.median(v) for arm, v in sorted(wall[key].items())},
                 "realtime_factor_median": {arm: statistics.median(v) / T_BIO_S for arm, v in sorted(wall[key].items())},
                 "ncp_ms_per_exchange": {arm: {"median": statistics.median(v), "min": min(v), "max": max(v),
                                               "blocks": len(v)} for arm, v in sorted(per_exchange[key].items())}}
        if music_cost[key]:
            entry["music_s_per_run"] = {"median": statistics.median(music_cost[key]), "min": min(music_cost[key]),
                                        "max": max(music_cost[key])}
        configs["/".join(map(str, key))] = entry

    def median_o(part, arm, **match):
        values = []
        for entry in configs.values():
            if entry["part"] == part and all(entry[k] == v for k, v in match.items()) and arm in entry["ncp_ms_per_exchange"]:
                values.append(entry["ncp_ms_per_exchange"][arm]["median"])
        return values

    h1 = []
    for entry in configs.values():
        if entry["part"] == "D1" and entry["delta_ms"] == 1.0:
            o = entry["ncp_ms_per_exchange"]
            h1.append(o["ncp-py-1.0.1"]["median"] < o["ncp-py-1.0.0"]["median"])
    d1_py = median_o("D1", "ncp-py-1.0.1")
    h3 = [entry["ncp_ms_per_exchange"]["ncp-rs-1.0.1"]["median"] < entry["ncp_ms_per_exchange"]["ncp-py-1.0.1"]["median"]
          for entry in configs.values() if entry["part"] == "D1"]
    d3_small, d3_large = median_o("D3", "ncp-py-1.0.1", n=250), median_o("D3", "ncp-py-1.0.1", n=25000)
    expected_runs = len(schedule["order"])
    hypotheses = {
        "H1": {"criterion": "D1, delta 1 ms: median O of py-1.0.1 < py-1.0.0 for each size and thread count",
               "holds": len(h1) == 6 and all(h1), "configurations": len(h1)},
        "H2": {"criterion": "D1: median of the 18 median O of py-1.0.1 <= 0.6 ms",
               "value": statistics.median(d1_py) if d1_py else None,
               "holds": len(d1_py) == 18 and statistics.median(d1_py) <= 0.6},
        "H3": {"criterion": "D1: median O of rs-1.0.1 < py-1.0.1 for each configuration",
               "holds": len(h3) == 18 and all(h3), "configurations": len(h3)},
        "H4": {"criterion": "D3: median O of py-1.0.1 at n=25000 <= 2 x at n=250",
               "values": [d3_small, d3_large],
               "holds": bool(d3_small and d3_large) and d3_large[0] <= 2 * d3_small[0]},
        "H5": {"criterion": "every run valid and recorded counts agree across arms",
               "holds": not invalid and not disagreements and len(rows) == expected_runs},
    }
    if len(sys.argv) > 2:
        reference = {}
        for line in (Path(sys.argv[2]) / "runs.jsonl").read_text().splitlines():
            row = json.loads(line) if line.strip() else None
            if row and row["returncode"] == 0 and "recorded" in row:
                reference[(row["config"], row["block"])] = row["recorded"]
        compared, differing = 0, []
        for row in rows:
            key = (row["config"], row["block"])
            if row["returncode"] == 0 and "recorded" in row and key in reference:
                compared += 1
                if row["recorded"] != reference[key]:
                    differing.append({"config": key[0], "block": key[1], "run": row["recorded"], "run1": reference[key]})
        hypotheses["H6"] = {"criterion": "recorder totals equal run 1 for every configuration and block both completed",
                            "holds": compared > 0 and not differing, "compared": compared, "differing": differing}
    analysis = {"protocol_sha256": schedule["protocol_sha256"], "runs": len(rows), "expected_runs": expected_runs,
                "invalid_runs": invalid, "count_disagreements": disagreements,
                "music_delivery": music_delivery, "configurations": configs, "hypotheses": hypotheses}
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"], value.get("value", ""))


if __name__ == "__main__":
    main()
