#!/usr/bin/env python3
"""Compute the measures and hypotheses of the pipelined benchmark (see PROTOCOL.md).

Usage: analyze.py RESULTS_DIR. Writes RESULTS_DIR/analysis.json. Standard library only.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    results = Path(sys.argv[1])
    rows = [json.loads(line) for line in (results / "runs.jsonl").read_text().splitlines() if line.strip()]
    schedule = json.loads((results / "schedule.json").read_text())
    by = defaultdict(dict)
    invalid = []
    for row in rows:
        if row["returncode"] != 0 or not row.get("valid"):
            invalid.append(f"{row['config']} block {row['block']}")
            continue
        by[row["config"]][row["block"]] = row["timing"]["median_us"]
    summary = {name: {"blocks": len(values), "median_us": statistics.median(values.values()),
                      "min_us": min(values.values()), "max_us": max(values.values())}
               for name, values in sorted(by.items())}
    pairs = {}
    for name in by:
        if "-pipelined-" not in name:
            continue
        sequential = name.replace("-pipelined-", "-sequential-")
        blocks = sorted(set(by[name]) & set(by[sequential]))
        ratios = [by[sequential][b] / by[name][b] for b in blocks]
        differences = [by[sequential][b] - by[name][b] for b in blocks]
        pairs[name.replace("-pipelined", "")] = {
            "ratio_median": statistics.median(ratios), "ratio_min": min(ratios), "ratio_max": max(ratios),
            "difference_us_median": statistics.median(differences), "difference_us_min": min(differences),
            "pipelined_lower_every_block": all(d > 0 for d in differences), "blocks": len(blocks)}
    expected_blocks = schedule["blocks"]
    hypotheses = {
        "H1": {"criterion": "rust-rust n=0: pipelined lower in each block",
               "holds": pairs["rust-rust-n0"]["pipelined_lower_every_block"]
               and pairs["rust-rust-n0"]["blocks"] == expected_blocks},
        "H2": {"criterion": "python-python n=0: pipelined lower in each block",
               "holds": pairs["python-python-n0"]["pipelined_lower_every_block"]
               and pairs["python-python-n0"]["blocks"] == expected_blocks},
        "H3": {"criterion": "rust-rust n=0: median difference at least 3 us",
               "value": pairs["rust-rust-n0"]["difference_us_median"],
               "holds": pairs["rust-rust-n0"]["difference_us_median"] >= 3},
    }
    analysis = {"protocol_sha256": schedule["protocol_sha256"], "runs": len(rows), "invalid_runs": invalid,
                "summary": summary, "pairs": pairs, "hypotheses": hypotheses}
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"])


if __name__ == "__main__":
    main()
