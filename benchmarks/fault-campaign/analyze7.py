#!/usr/bin/env python3
"""Evaluate fault-campaign protocol 7 (see PROTOCOL-7.md).
Usage: analyze7.py RESULTS_DIR. Writes RESULTS_DIR/analysis.json and prints the tables. Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

NETWORK = ("drop-query", "drop-reply", "duplicate-query", "delay-reply", "replay-request", "replay-open", "two-faults")
HYPOTHESES = {
    "E1": "No trial accepts a wrong result.",
    "E2": "In every trial, the owner executes each step at most once, in order.",
    "E3": "In every trial, what the client learned about each step is true, and at most one step is uncertain.",
    "E4": "Every failure reaches the application as an error that the client's SDK documents for a call.",
    "Z1": "Every trial with faults of the network only (loss, repetition, delay, replay) completes, with every fault applied.",
    "Z2": "Every trial with a killed owner that is not started again ends early.",
}


def main() -> None:
    results = Path(sys.argv[1])
    schedule = json.loads((results / "schedule.json").read_text())
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    failed = [f"{r['scenario']} {r['owner']} block {r['block']} #{r['index']}" for r in rows if r["returncode"] != 0]
    ran = [r for r in rows if r["returncode"] == 0]
    table: dict = defaultdict(lambda: defaultdict(int))
    views: dict = defaultdict(lambda: defaultdict(int))
    violations: dict = defaultdict(list)
    for row in ran:
        result = row["result"]
        label = f"{row['scenario']} {row['owner']} block {row['block']} #{row['index']}"
        entry = table[f"{row['scenario']} | {row['owner']} owner"]
        entry["trials"] += 1
        entry["completed"] += bool(result["completed"])
        entry["ended_early"] += result["error"] is not None
        entry["restarted"] += bool(result["restarted"])
        for view in result["views"].values():
            if view not in ("ok", "closed"):
                views[row["scenario"]][view] += 1
        if result["wrong_accepted"]:
            violations["E1"].append(label)
        invariants = result["invariants"]
        if not (invariants["once"] and invariants["in_order"]):
            violations["E2"].append(label)
        if not invariants["known"]:
            violations["E3"].append(label)
        if result["error"] and result["error"].startswith("undocumented"):
            violations["E4"].append(f"{label}: {result['error']}")
        if row["scenario"] in NETWORK and (not result["completed"] or result["unapplied"]):
            violations["Z1"].append(f"{label}: {result['error']} unapplied {result['unapplied']}")
        if row["scenario"] == "kill-owner" and result["error"] is None:
            violations["Z2"].append(label)
    all_ran = not failed and len(rows) == len(schedule["order"])
    decided = {name: {"criterion": text, "violations": violations.get(name, []), "holds": all_ran and not violations.get(name)}
               for name, text in HYPOTHESES.items()}
    analysis = {
        "protocol": schedule["protocol"], "protocol_sha256": schedule["protocol_sha256"], "commit": schedule["commit"],
        "worktree_clean": schedule["worktree_clean"], "power": schedule.get("power"), "rows": len(rows),
        "scheduled": len(schedule["order"]), "failed_to_run": failed,
        "started": min((r["started_utc"] for r in rows), default=None),
        "finished": max((r["finished_utc"] for r in rows), default=None),
        "load1_before": [min((r["load1_before"] for r in rows), default=None), max((r["load1_before"] for r in rows), default=None)],
        "by_scenario": {key: dict(value) for key, value in sorted(table.items())},
        "views_other_than_ok": {key: dict(value) for key, value in sorted(views.items())},
        "hypotheses": decided,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for key, value in sorted(table.items()):
        print(f"{key:40s} {dict(value)}")
    for key, value in sorted(views.items()):
        print(f"views, {key:24s} {dict(value)}")
    for name, entry in decided.items():
        print(name, "holds" if entry["holds"] else "does not hold", entry["violations"][:5])


if __name__ == "__main__":
    main()
