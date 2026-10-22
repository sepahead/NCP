#!/usr/bin/env python3
"""Compute the measures and hypotheses of protocol 2 (see PROTOCOL-2.md).

Usage: analyze2.py RESULTS_JSON OUT_JSON. Standard library only.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict


def main() -> None:
    record = json.loads(open(sys.argv[1]).read())
    by_config: dict[str, list[dict]] = defaultdict(list)
    for run in record["runs"]:
        by_config[run["config"]].append(run)
    invalid = [f"{run['config']} round {run['round']}" for run in record["runs"]
               if run["returncode"] != 0 or (run.get("mode") == "client" and not run.get("valid"))]
    summary = {}
    for name, items in sorted(by_config.items()):
        if items[0].get("mode") == "phases":
            totals = [run["total_mean_us"] for run in items]
            summary[name] = {"rounds": len(items), "total_mean_us_median": statistics.median(totals),
                             "parts_us": {part: statistics.median(run["mean_us"][part] for run in items)
                                          for part in items[0]["mean_us"]}}
            continue
        medians = [run["timing"]["median_us"] for run in items]
        summary[name] = {"rounds": len(medians), "median_us": statistics.median(medians), "min_us": min(medians),
                         "max_us": max(medians),
                         "p99_us_median": statistics.median(run["timing"]["p99_us"] for run in items)}
    ratios = {}
    for name in by_config:
        if "-released-" not in name or name.startswith("phases"):
            continue
        released = {run["round"]: run["timing"]["median_us"] for run in by_config[name]}
        current = {run["round"]: run["timing"]["median_us"] for run in by_config[name.replace("-released-", "-current-")]}
        per_round = [released[r] / current[r] for r in sorted(released)]
        ratios[name.replace("-released", "")] = {"per_round": per_round, "median": statistics.median(per_round),
                                                 "min": min(per_round), "max": max(per_round)}
    hypotheses = {
        "H1": {"criterion": "rust-rust n=0 median paired ratio >= 6", "value": ratios["rust-rust-n0"]["median"]},
        "H2": {"criterion": "python-python n=0 median paired ratio >= 2.5",
               "value": ratios["python-python-n0"]["median"]},
        "H3": {"criterion": "python-python n=127 median paired ratio >= 2.5",
               "value": ratios["python-python-n127"]["median"]},
        "H4": {"criterion": "current lower than released in every round for all eleven pairs",
               "value": {key: min(value["per_round"]) for key, value in sorted(ratios.items())}},
    }
    hypotheses["H1"]["holds"] = hypotheses["H1"]["value"] >= 6
    hypotheses["H2"]["holds"] = hypotheses["H2"]["value"] >= 2.5
    hypotheses["H3"]["holds"] = hypotheses["H3"]["value"] >= 2.5
    hypotheses["H4"]["holds"] = len(ratios) == 11 and all(value["min"] > 1 for value in ratios.values())
    analysis = {"schema": "ncp.local-sdk-exchange-analysis.v2", "protocol_sha256": record["protocol_sha256"],
                "rust_transcripts_identical": record["rust_transcripts_identical"],
                "python_transcripts_identical": record["python_transcripts_identical"],
                "runs": len(record["runs"]), "invalid_runs": invalid, "summary": summary,
                "paired_ratios_released_over_current": ratios, "hypotheses": hypotheses}
    open(sys.argv[2], "w").write(json.dumps(analysis, indent=1) + "\n")
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"])


if __name__ == "__main__":
    main()
