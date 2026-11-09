#!/usr/bin/env python3
"""Evaluate protocol 4 or 5 of the fault campaign (see PROTOCOL-4.md and PROTOCOL-5.md).

Usage: analyze4.py RESULTS_DIR. Writes RESULTS_DIR/analysis.json and prints the tables.
Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

TIMEOUT_S = 2.0

HYPOTHESES = {
    "E1": "No trial accepts a wrong result.",
    "E2": "In every trial, the owner executes each step at most once, in order.",
    "E3": "In every trial, what the client learned about each step is true, and at most one step is uncertain.",
    "E4": "Every failure reaches the application as an error that the client's SDK documents for a call.",
    "E5": "Every flipped or truncated frame ends the session early.",
    "E6": "After every killed client, the owner serves a new session within 10 s.",
    "E7": "Every stall ends with a timeout, possibly executed, within the time limit plus 1 s.",
    "E8": "Oversized results end with result_too_large (executed), raising handlers with owner_failure (unknown), "
    "and oversized requests are refused before sending, after which the session completes.",
}


def main() -> None:
    results = Path(sys.argv[1])
    schedule = json.loads((results / "schedule.json").read_text())
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    failed_to_run = [
        f"{r['scenario']} {r['owner']} owner {r['client']} client {r['binding']} block {r['block']} #{r['index']}"
        for r in rows
        if r["returncode"] != 0
    ]
    ran = [r for r in rows if r["returncode"] == 0]
    table: dict = defaultdict(lambda: defaultdict(int))
    combos: dict = defaultdict(lambda: defaultdict(int))
    regions: dict = defaultdict(int)
    violations: dict = defaultdict(list)
    for row in ran:
        result = row["result"]
        combo = f"{row['owner']} owner, {row['client']} client, {row['binding']}"
        key = f"{row['scenario']} | {combo}"
        entry = table[key]
        entry["trials"] += 1
        combos[combo]["trials"] += 1
        label = f"{key} block {row['block']} #{row['index']}"
        if row["scenario"] == "kill-client":
            entry["owner_served_again"] += bool(result["owner_served_again"])
            if not result["owner_served_again"]:
                violations["E6"].append(label)
            continue
        error = result.get("error")
        entry["completed"] += bool(result["completed"])
        entry["detected"] += error is not None
        entry["wrong_accepted"] += result["wrong_accepted"]
        if result["wrong_accepted"]:
            violations["E1"].append(label)
        invariants = result["invariants"]
        if not (invariants["once"] and invariants["in_order"]):
            violations["E2"].append(label)
        if not invariants["known"]:
            violations["E3"].append(label)
        if error and error.startswith("undocumented"):
            violations["E4"].append(f"{label}: {error}")
        relay = result.get("relay") or {}
        if row["scenario"].startswith(("flip", "truncate")):
            if relay.get("changed"):
                entry["changed"] += 1
                if result["completed"]:
                    violations["E5"].append(label)
                if relay.get("region"):
                    regions[relay["region"]] += 1
            else:
                entry["not_changed"] += 1
        views, plan = result["views"], result["plan"]
        if row["scenario"] == "stall":
            k = plan["stall_k"]
            if views.get(str(k)) != "ended:timeout:unknown" or result["seconds"] > TIMEOUT_S + 1.0:
                violations["E7"].append(f"{label}: {views.get(str(k))}, {result['seconds']} s")
            entry["max_seconds"] = max(entry.get("max_seconds", 0), result["seconds"])
        if (
            row["scenario"] == "oversize-response"
            and views.get(str(plan["oversize_k"])) != "ended:result_too_large:yes"
        ):
            violations["E8"].append(f"{label}: {views.get(str(plan['oversize_k']))}")
        if row["scenario"] == "backend-raise" and views.get(str(plan["fail_k"])) != "ended:owner_failure:unknown":
            violations["E8"].append(f"{label}: {views.get(str(plan['fail_k']))}")
        if row["scenario"] == "oversize-request" and not (
            views.get(str(-plan["oversize_request_k"])) == "refused_before_sending" and result["completed"]
        ):
            violations["E8"].append(label)
    all_ran = not failed_to_run and len(rows) == len(schedule["order"])
    decided = {
        name: {"criterion": text, "violations": violations.get(name, []), "holds": all_ran and not violations.get(name)}
        for name, text in HYPOTHESES.items()
    }
    analysis = {
        "protocol": schedule["protocol"],
        "protocol_sha256": schedule["protocol_sha256"],
        "commit": schedule["commit"],
        "worktree_clean": schedule["worktree_clean"],
        "power": schedule.get("power"),
        "rows": len(rows),
        "scheduled": len(schedule["order"]),
        "failed_to_run": failed_to_run,
        "trials_by_combination": {key: dict(value) for key, value in sorted(combos.items())},
        "by_scenario": {key: dict(value) for key, value in sorted(table.items())},
        "flip_regions": dict(sorted(regions.items())),
        "hypotheses": decided,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for key, value in sorted(table.items()):
        print(f"{key:62s} {dict(value)}")
    print("flip regions:", dict(regions))
    print("trials by combination:", {k: v["trials"] for k, v in sorted(combos.items())})
    for name, entry in decided.items():
        print(name, "holds" if entry["holds"] else "does not hold", entry["violations"][:5])


if __name__ == "__main__":
    main()
