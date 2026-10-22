#!/usr/bin/env python3
"""Compute the protocol's measures from a run record (see PROTOCOL.md).

Usage: analyze.py RESULTS_JSON OUT_JSON. Standard library only.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict


def main() -> None:
    record = json.loads(open(sys.argv[1]).read())
    runs = record["runs"]
    by_config: dict[str, list[dict]] = defaultdict(list)
    for run in runs:
        by_config[run["config"]].append(run)
    invalid = [run for run in runs if run["returncode"] != 0 or (run.get("mode") == "client" and not run.get("valid"))]
    summary = {}
    for name, items in sorted(by_config.items()):
        if items[0].get("mode") == "phases":
            totals = [run["total_mean_us"] for run in items]
            parts = {part: statistics.median(run["mean_us"][part] for run in items) for part in items[0]["mean_us"]}
            summary[name] = {"rounds": len(items), "total_mean_us_median": statistics.median(totals),
                             "total_mean_us_min": min(totals), "total_mean_us_max": max(totals), "parts_us": parts}
            continue
        medians = [run["timing"]["median_us"] for run in items if "timing" in run]
        summary[name] = {"rounds": len(medians), "median_us": statistics.median(medians), "min_us": min(medians),
                         "max_us": max(medians),
                         "p99_us_median": statistics.median(run["timing"]["p99_us"] for run in items if "timing" in run)}
    ratios = {}
    for name in summary:
        if "-released" not in name or name.startswith("phases"):
            continue
        current = name.replace("-released", "-current")
        released_runs = {run["round"]: run["timing"]["median_us"] for run in by_config[name]}
        current_runs = {run["round"]: run["timing"]["median_us"] for run in by_config[current]}
        per_round = [released_runs[r] / current_runs[r] for r in sorted(released_runs) if r in current_runs]
        ratios[name.replace("-released", "")] = {"per_round": per_round, "median": statistics.median(per_round),
                                                 "min": min(per_round), "max": max(per_round),
                                                 "current_lower_every_round": all(x > 1 for x in per_round)}
    hypotheses = {
        "H1": {"criterion": "rust-rust n=0 median paired ratio >= 5",
               "value": ratios["rust-rust-n0"]["median"], "holds": ratios["rust-rust-n0"]["median"] >= 5},
        "H2": {"criterion": "rust-rust n=127 median paired ratio >= 3",
               "value": ratios["rust-rust-n127"]["median"], "holds": ratios["rust-rust-n127"]["median"] >= 3},
        "H3": {"criterion": "rust-rust n=500 current lower in every round",
               "value": ratios["rust-rust-n500"]["per_round"],
               "holds": ratios["rust-rust-n500"]["current_lower_every_round"]},
    }
    analysis = {"schema": "ncp.local-sdk-exchange-analysis.v1", "protocol_sha256": record["protocol_sha256"],
                "transcripts_identical": record["transcripts_identical"],
                "python_sources_identical_to_release": record["python_sources_identical_to_release"],
                "runs": len(runs), "invalid_runs": [run["config"] + f" round {run['round']}" for run in invalid],
                "summary": summary, "paired_ratios_released_over_current": ratios, "hypotheses": hypotheses}
    open(sys.argv[2], "w").write(json.dumps(analysis, indent=1) + "\n")
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"], value["value"])


if __name__ == "__main__":
    main()
