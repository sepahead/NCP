#!/usr/bin/env python3
"""Evaluate content protocol 3 (see PROTOCOL-CONTENT-3.md).

Usage: analyze_content3.py RESULTS_DIR [CONTENT_2_RESULTS_DIR]
Writes RESULTS_DIR/analysis.json and prints the tables. Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

HOSTS = ("ncp2_py", "ncp2_rs")
HYPOTHESES = {
    "K1": "In every trial, the NCP 2 Python host receives exactly the reference multiset of spikes, offsets bit for bit.",
    "K2": "In every trial, the NCP 2 Rust host receives exactly the reference multiset of spikes, offsets bit for bit.",
    "V1": "In every trial, the NCP 2 Python host receives exactly the reference multiset of membrane potential samples, bit for bit.",
    "V2": "In every trial, the NCP 2 Rust host receives exactly the reference multiset of membrane potential samples, bit for bit.",
    "S1": "In every trial, each owner sent what its host received, and each owner exited with status 0.",
    "K3": "For each configuration of content protocol 2, the reference spike total of each block equals that of protocol 2.",
}


def main() -> None:
    results = Path(sys.argv[1])
    earlier = Path(sys.argv[2]) if len(sys.argv) > 2 else results.parent / "results-content-2"
    schedule = json.loads((results / "schedule.json").read_text())
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    failed = [f"{r['config']} block {r['block']}" for r in rows if r["returncode"] != 0]
    ran = [r for r in rows if r["returncode"] == 0]
    violations: dict[str, list[str]] = defaultdict(list)
    for row in ran:
        label = f"{row['config']} block {row['block']}"
        for host, k, v in (("ncp2_py", "K1", "V1"), ("ncp2_rs", "K2", "V2")):
            if not row[f"{host}_spikes_exact"]:
                violations[k].append(f"{label}: missing {row[f'{host}_spikes_missing']}, extra {row[f'{host}_spikes_extra']}")
            if not row[f"{host}_vm_exact"]:
                violations[v].append(f"{label}: missing {row[f'{host}_vm_missing']}, extra {row[f'{host}_vm_extra']}")
            if not row[f"{host}_owner_sent_equals_received"] or row[f"{host}_child_exit"] != 0:
                violations["S1"].append(f"{label}: {host}")
    reference_2 = {}
    trials_2 = earlier / "trials.jsonl"
    if trials_2.exists():
        for line in trials_2.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("returncode") == 0:
                    reference_2[(row["block"], row["config"])] = row["reference_spikes"]
    compared = 0
    for row in ran:
        key = (row["block"], row["config"])
        if key in reference_2:
            compared += 1
            if reference_2[key] != row["reference_spikes"]:
                violations["K3"].append(f"{row['config']} block {row['block']}: {row['reference_spikes']} != {reference_2[key]}")
    expected_k3 = 32 * 3
    all_ran = not failed and len(rows) == len(schedule["order"])
    decided = {
        name: {"criterion": text, "violations": violations.get(name, []),
               "holds": all_ran and not violations.get(name) and (name != "K3" or compared == expected_k3)}
        for name, text in HYPOTHESES.items()
    }
    by_network: dict[str, dict] = {}
    for row in ran:
        entry = by_network.setdefault(f"{row['network']}, {row['n']} neurons", {
            "trials": 0, "spikes_min": None, "spikes_max": 0, "vm_samples": 0, "off_grid": 0, "exact_trials": 0})
        entry["trials"] += 1
        spikes = row["reference_spikes"]
        entry["spikes_min"] = spikes if entry["spikes_min"] is None else min(entry["spikes_min"], spikes)
        entry["spikes_max"] = max(entry["spikes_max"], spikes)
        entry["vm_samples"] += row["reference_vm"]
        entry["off_grid"] += row["reference_off_grid"]
        entry["exact_trials"] += all(row[f"{h}_{kind}_exact"] for h in HOSTS for kind in ("spikes", "vm"))
    totals = {
        "spikes_compared": sum(row[f"{h}_spikes"] for row in ran for h in HOSTS),
        "vm_compared": sum(row[f"{h}_vm"] for row in ran for h in HOSTS),
        "reference_spikes": sum(row["reference_spikes"] for row in ran),
        "reference_vm": sum(row["reference_vm"] for row in ran),
        "off_grid_spikes": sum(row["reference_off_grid"] for row in ran),
    }
    analysis = {
        "protocol": schedule["protocol"],
        "protocol_sha256": schedule["protocol_sha256"],
        "commit": schedule["commit"],
        "worktree_clean": schedule["worktree_clean"],
        "rows": len(rows),
        "scheduled": len(schedule["order"]),
        "failed_to_run": failed,
        "started": min((r["started_utc"] for r in rows), default=None),
        "finished": max((r["finished_utc"] for r in rows), default=None),
        "load1_before": [min((r["load1_before"] for r in rows), default=None), max((r["load1_before"] for r in rows), default=None)],
        "k3_compared": compared,
        "totals": totals,
        "by_network": dict(sorted(by_network.items())),
        "hypotheses": decided,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for name, entry in sorted(by_network.items()):
        print(f"{name:32s} {entry}")
    print("totals:", totals, "K3 compared:", compared)
    for name, entry in decided.items():
        print(name, "holds" if entry["holds"] else "does not hold", entry["violations"][:5])


if __name__ == "__main__":
    main()
