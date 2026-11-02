#!/usr/bin/env python3
"""Summarize the content protocol 2 (see PROTOCOL-CONTENT-2.md).

Usage: analyze_content2.py RESULTS_DIR [CONTENT_RESULTS_DIR]
CONTENT_RESULTS_DIR holds the trials of the content protocol (default: results-content next to
this file); K3 compares the reference totals with it. Writes RESULTS_DIR/analysis.json.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_TRIALS = 96  # 32 configurations, three blocks
HOSTS = ("ncp2_py", "ncp2_rs")


def trials(path: Path) -> list[dict]:
    return [json.loads(line) for line in (path / "trials.jsonl").read_text().splitlines() if line.strip()]


def main() -> None:
    results = Path(sys.argv[1])
    earlier = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "results-content"
    schedule = json.loads((results / "schedule.json").read_text())
    if schedule.get("protocol") != "PROTOCOL-CONTENT-2.md":
        sys.exit(f"{results} does not hold the content protocol 2")
    rows = trials(results)
    failed = [f"{r['config']} block {r['block']}" for r in rows if r["returncode"] != 0]
    good = [r for r in rows if r["returncode"] == 0]
    complete = len(rows) == EXPECTED_TRIALS and not failed

    groups: dict = defaultdict(lambda: {"trials": 0, **{f"{h}_exact": 0 for h in HOSTS}, "spikes": []})
    for r in good:
        entry = groups[f"n{r['n']}/t{r['threads']}"]
        entry["trials"] += 1
        for host in HOSTS:
            entry[f"{host}_exact"] += r[f"{host}_exact"]
        entry["spikes"].append(r["reference_spikes"])
    summary = {
        key: {
            "trials": e["trials"],
            **{f"{h}_exact": e[f"{h}_exact"] for h in HOSTS},
            "reference_spikes_min": min(e["spikes"]),
            "reference_spikes_max": max(e["spikes"]),
        }
        for key, e in sorted(groups.items(), key=lambda item: (int(item[0][1:].split("/")[0]), item[0]))
    }

    before = {(r["block"], r["config"]): r["reference_spikes"] for r in trials(earlier) if r["returncode"] == 0}
    compared = [r for r in good if (r["block"], r["config"]) in before]
    differing = [
        f"{r['config']} block {r['block']}: {r['reference_spikes']} against {before[(r['block'], r['config'])]}"
        for r in compared
        if r["reference_spikes"] != before[(r["block"], r["config"])]
    ]
    hypotheses = {
        "K1": {
            "criterion": "in every trial, the NCP 2 Python host receives exactly the reference multiset",
            "holds": complete and all(r["ncp2_py_exact"] for r in good),
        },
        "K2": {
            "criterion": "in every trial, the NCP 2 Rust host receives exactly the reference multiset",
            "holds": complete and all(r["ncp2_rs_exact"] for r in good),
        },
        "K3": {
            "criterion": "the reference totals of the 24 configurations of the content protocol equal its totals",
            "compared": len(compared),
            "differing": differing,
            "holds": complete and len(compared) == 72 and not differing,
        },
    }
    analysis = {
        "protocol": schedule["protocol"],
        "protocol_sha256": schedule["protocol_sha256"],
        "trials": len(rows),
        "expected_trials": EXPECTED_TRIALS,
        "failed": failed,
        "count_equals_recorded": all(r[f"{h}_count_equals_recorded"] for r in good for h in HOSTS),
        "spikes_compared": sum(r["reference_spikes"] for r in good) * len(HOSTS),
        "by_size_and_threads": summary,
        "hypotheses": hypotheses,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"])


if __name__ == "__main__":
    main()
