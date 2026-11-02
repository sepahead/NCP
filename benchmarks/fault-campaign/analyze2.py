#!/usr/bin/env python3
"""Evaluate protocol 2 or 3 of the fault campaign (see PROTOCOL-2.md and PROTOCOL-3.md).

Usage: analyze2.py RESULTS_DIR. Writes RESULTS_DIR/analysis.json and prints the tables.
Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

TIMEOUT_S = 2.0
SOAK_FIELDS = ("client_rss_kb", "owner_rss_kb", "client_fds", "owner_fds")


def soak(row: dict, drop_last: bool) -> dict:
    """The memory and descriptor measures of one soak. Protocol 3 leaves out the last sample of the
    descriptor check: it can fall while the processes exit."""
    run = row.get("result") or {}
    samples = [s for s in run.get("samples", []) if all(s[f] is not None for f in SOAK_FIELDS)]
    if row["returncode"] != 0 or not run.get("result") or len(samples) < 10:
        return {"kind": row["owner"], "block": row["block"], "valid": False, "samples": len(samples)}
    end = samples[-1]["t"]
    base = next(s for s in samples if s["t"] >= 0.1 * end)
    later = [s for s in samples if s["t"] >= base["t"]]
    growth = {side: max(s[f"{side}_rss_kb"] for s in later) / base[f"{side}_rss_kb"] - 1.0 for side in ("client", "owner")}
    return {
        "kind": row["owner"],
        "block": row["block"],
        "calls": run["calls"],
        "seconds": run["seconds"],
        "valid": bool(run["result"].get("valid")),
        "median_us": run["result"]["median_us"],
        "samples": len(samples),
        "rss_kb_at_first_tenth": {side: base[f"{side}_rss_kb"] for side in ("client", "owner")},
        "rss_growth_after_first_tenth": growth,
        "descriptors": {
            side: sorted({s[f"{side}_fds"] for s in (later[:-1] if drop_last else later)}) for side in ("client", "owner")
        },
    }


def main() -> None:
    results = Path(sys.argv[1])
    schedule = json.loads((results / "schedule.json").read_text())
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    trials = [row for row in rows if row["scenario"] != "soak"]
    three = schedule["protocol"] == "PROTOCOL-3.md"
    soaks = [soak(row, three) for row in rows if row["scenario"] == "soak"]
    failed_to_run = [f"{r['scenario']} {r['owner']} block {r['block']} #{r['index']}" for r in trials if r["returncode"] != 0]
    ran = [r for r in trials if r["returncode"] == 0]
    table: dict = defaultdict(lambda: defaultdict(int))
    regions: dict = defaultdict(int)
    by_index: dict = defaultdict(lambda: defaultdict(int))  # flips by frame index and region
    violations: dict = defaultdict(list)
    for row in ran:
        result = row["result"]
        key = f"{row['scenario']} {row['owner']}"
        entry = table[key]
        entry["trials"] += 1
        error = result.get("error")
        label = f"{row['scenario']} {row['owner']} block {row['block']} #{row['index']}"
        if row["scenario"] == "kill-client":
            entry["owner_exited"] += bool(result["owner_exited"])
            if not result["owner_exited"]:
                violations["E6"].append(label)
            continue
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
                    by_index[str(relay["index"])][relay["region"]] += 1
            else:
                entry["not_changed"] += 1
        views, plan = result["views"], result["plan"]
        if row["scenario"] == "stall":
            k = plan["stall_k"]
            if views.get(str(k)) != "ended:timeout:unknown" or result["seconds"] > TIMEOUT_S + 1.0:
                violations["E7"].append(f"{label}: {views.get(str(k))}, {result['seconds']} s")
            entry["max_seconds"] = max(entry.get("max_seconds", 0), result["seconds"])
        if row["scenario"] == "oversize-response" and views.get(str(plan["oversize_k"])) != "ended:result_too_large:yes":
            violations["E8"].append(f"{label}: {views.get(str(plan['oversize_k']))}")
        if row["scenario"] == "backend-raise" and views.get(str(plan["fail_k"])) != "ended:owner_failure:unknown":
            violations["E8"].append(f"{label}: {views.get(str(plan['fail_k']))}")
        if row["scenario"] == "oversize-request" and not (
            views.get(str(-plan["oversize_request_k"])) == "refused_before_sending" and result["completed"]
        ):
            violations["E8"].append(label)
    soak_ok = all(
        s["valid"]
        and all(s["rss_growth_after_first_tenth"][side] < 0.10 for side in ("client", "owner"))
        and all(len(s["descriptors"][side]) == 1 for side in ("client", "owner"))
        for s in soaks
    )
    all_ran = not failed_to_run and len(rows) == len(schedule["order"])
    hypotheses = {
        "E1": "No trial accepts a wrong result.",
        "E2": "In every trial, the owner executes each step at most once, in order.",
        "E3": "In every trial, what the client learned about each step is true, and at most one step is uncertain.",
        "E4": "Every failure reaches the application as a documented exception.",
        "E5": "Every flipped or truncated frame ends the session early.",
        "E6": "Every killed client leaves its owner exited within 10 s.",
        "E7": "Every stall ends with a timeout, possibly executed, within the time limit plus 1 s.",
        "E8": "Oversized results end with result_too_large (executed), raising handlers with owner_failure (unknown), "
        "and oversized requests are refused before sending, after which the session completes.",
    }
    decided = {
        name: {"criterion": text, "violations": violations.get(name, []), "holds": all_ran and not violations.get(name)}
        for name, text in hypotheses.items()
    }
    decided["E9"] = {
        "criterion": "In each soak, every call returns the right result, the memory of client and owner grows by "
        "less than 10 % after the first tenth, and their open descriptors stay constant after the first tenth"
        + (", except in the last sample." if three else "."),
        "holds": all_ran and soak_ok and len(soaks) == 3 * (1 if schedule.get("smoke") else 3),
    }
    analysis = {
        "protocol": schedule["protocol"],
        "protocol_sha256": schedule["protocol_sha256"],
        "commit": schedule["commit"],
        "worktree_clean": schedule["worktree_clean"],
        "rows": len(rows),
        "scheduled": len(schedule["order"]),
        "failed_to_run": failed_to_run,
        "by_scenario": {key: dict(value) for key, value in sorted(table.items())},
        "flip_regions": dict(sorted(regions.items())),
        "flip_regions_by_frame_index": {k: dict(sorted(v.items())) for k, v in sorted(by_index.items())},
        "soaks": soaks,
        "hypotheses": decided,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for key, value in sorted(table.items()):
        print(f"{key:28s} {dict(value)}")
    print("flip regions:", dict(regions))
    for s in soaks:
        if s["valid"]:
            g = s["rss_growth_after_first_tenth"]
            print(
                f"soak {s['kind']:14s} block {s['block']} {s['calls']:>8} calls {s['median_us']:.1f} us  "
                f"client +{100 * g['client']:.2f} %  owner +{100 * g['owner']:.2f} %  descriptors {s['descriptors']}"
            )
        else:
            print(f"soak {s['kind']} block {s['block']}: not valid")
    for name, entry in decided.items():
        print(name, "holds" if entry["holds"] else "does not hold", entry.get("violations", [])[:5])


if __name__ == "__main__":
    main()
