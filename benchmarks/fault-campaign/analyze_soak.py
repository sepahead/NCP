#!/usr/bin/env python3
"""Evaluate the bounded soak (see PROTOCOL-SOAK.md).

Usage: analyze_soak.py RESULTS_DIR. Writes RESULTS_DIR/analysis.json. Standard library only.
A sample counts only when it holds the memory and descriptor values of both processes; the
sampler records partial samples while a process starts or exits.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FIELDS = ("client_rss_kb", "owner_rss_kb", "client_fds", "owner_fds")


def main() -> None:
    results = Path(sys.argv[1])
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    trials = []
    for row in rows:
        run = row["result"]
        samples = [s for s in run["samples"] if all(s[f] is not None for f in FIELDS)]
        end = samples[-1]["t"]
        base = next(s for s in samples if s["t"] >= 0.1 * end)
        later = [s for s in samples if s["t"] >= base["t"]]
        growth = {side: max(s[f"{side}_rss_kb"] for s in later) / base[f"{side}_rss_kb"] - 1.0
                  for side in ("client", "owner")}
        descriptors = {side: sorted({s[f"{side}_fds"] for s in samples}) for side in ("client", "owner")}
        deciles = [samples[int(i * (len(samples) - 1) / 10)] for i in range(11)]
        trials.append({
            "block": row["block"], "kind": row["kind"], "calls": run["calls"], "seconds": run["seconds"],
            "valid": row["returncode"] == 0 and run["result"]["valid"],
            "samples": len(samples), "partial_samples": len(run["samples"]) - len(samples),
            "rss_growth_after_first_tenth": growth, "descriptors": descriptors,
            "owner_rss_kb_deciles": [s["owner_rss_kb"] for s in deciles],
            "client_rss_kb_deciles": [s["client_rss_kb"] for s in deciles],
            "timing": run["result"]["timing"],
        })
    s1 = all(t["rss_growth_after_first_tenth"][side] < 0.02 for t in trials for side in ("client", "owner"))
    s2 = all(len(t["descriptors"][side]) == 1 for t in trials for side in ("client", "owner"))
    analysis = {"trials": trials, "hypotheses": {
        "S1": {"criterion": "RSS of client and owner grows < 2 % after the first 10 % of each soak", "holds": s1},
        "S2": {"criterion": "open descriptors of client and owner constant after the first sample", "holds": s2},
    }, "all_valid": all(t["valid"] for t in trials)}
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for t in trials:
        g = t["rss_growth_after_first_tenth"]
        print(f"block {t['block']} {t['kind']:6s} {t['calls']:>8} calls  client +{100 * g['client']:.2f} %  "
              f"owner +{100 * g['owner']:.2f} %  descriptors {t['descriptors']['client']}/{t['descriptors']['owner']}")
    for key, value in analysis["hypotheses"].items():
        print(key, value["criterion"], "->", value["holds"])


if __name__ == "__main__":
    main()
