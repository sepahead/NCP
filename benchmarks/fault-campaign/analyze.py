#!/usr/bin/env python3
"""Classify the fault trials and evaluate the hypotheses (see PROTOCOL.md).

Usage: analyze.py RESULTS_DIR. Writes RESULTS_DIR/analysis.json. Standard library only.
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

TIMEOUT_S = 2.0


def classify(row) -> str:
    result = row["result"]
    if row["returncode"] != 0 or not result:
        return "harness-failure"
    if result.get("wrong_accepted"):
        return "wrong-accepted"
    scenario = row["scenario"]
    if scenario == "soak":
        return "completed" if result.get("returncode") == 0 and result["result"].get("valid") else "harness-failure"
    if scenario == "kill-client":
        return "owner-retired" if result["owner_exited"] and result["owner_retired"] else "owner-not-retired"
    outcomes = result.get("outcomes", [])
    if result.get("error") or "indeterminate" in outcomes or any(o.startswith("preflight") for o in outcomes):
        return "detected"
    return "completed"


def main() -> None:
    results = Path(sys.argv[1])
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    schedule = json.loads((results / "schedule.json").read_text())
    table = defaultdict(Counter)
    details = defaultdict(list)
    for row in rows:
        cls = classify(row)
        table[(row["scenario"], row["owner"])][cls] += 1
        details[row["scenario"]].append((row, cls))
    frame = [(row, cls) for scenario, items in details.items() if scenario.split("-")[0] in ("flip", "truncate")
             for row, cls in items]
    damaged = [(row, cls) for row, cls in frame if (row["result"].get("relay") or {}).get("damaged")]
    undamaged = [(row, cls) for row, cls in frame if not (row["result"].get("relay") or {}).get("damaged")]
    stall_seconds = [row["result"]["seconds"] for row, cls in details["stall"] if row["result"]]
    soaks = {}
    for row, cls in details["soak"]:
        samples = row["result"].get("samples", [])
        if not samples:
            continue
        start = max(1, len(samples) // 10)
        def growth(field):
            values = [s[field] for s in samples[start:] if s.get(field)]
            return (max(values) / values[0] - 1.0) if values else None
        def fds(field):
            values = [s[field] for s in samples[start:] if s.get(field) is not None]
            return (min(values), max(values)) if values else None
        soaks.setdefault(row["owner"], []).append({
            "block": row["block"], "calls": row["result"]["calls"], "seconds": row["result"]["seconds"],
            "median_us": row["result"]["result"]["timing"]["median_us"], "p99_us": row["result"]["result"]["timing"]["p99_us"],
            "client_rss_growth": growth("client_rss_kb"), "owner_rss_growth": growth("owner_rss_kb"),
            "client_fds": fds("client_fds"), "owner_fds": fds("owner_fds")})
    def all_detected(scenarios):
        items = [(row, cls) for s in scenarios for row, cls in details[s]]
        return bool(items) and all(cls == "detected" and row["result"].get("retired") for row, cls in items)
    hypotheses = {
        "F1": {"criterion": "no trial accepts a wrong result",
               "holds": not any(cls == "wrong-accepted" for counter in table.values() for cls in counter)},
        "F2": {"criterion": "every damaged frame is detected", "damaged": len(damaged),
               "holds": bool(damaged) and all(cls == "detected" for _, cls in damaged)},
        "F3": {"criterion": "every kill-client trial: owner retired and exited",
               "holds": bool(details["kill-client"]) and all(cls == "owner-retired" for _, cls in details["kill-client"])},
        "F4": {"criterion": "every stall detected within the time limit plus 1 s",
               "max_seconds": max(stall_seconds) if stall_seconds else None,
               "holds": bool(stall_seconds) and all(row["result"].get("error") == "execution_unknown"
                                                    and row["result"]["seconds"] <= TIMEOUT_S + 1.0
                                                    for row, _ in details["stall"])},
        "F5": {"criterion": "oversize-response, backend-raise, nest-raise end in indeterminate and retire",
               "holds": all(row["result"].get("outcomes", [""])[-1] == "indeterminate" and row["result"].get("retired")
                            for s in ("oversize-response", "backend-raise", "nest-raise") for row, _ in details[s])
               and all(details[s] for s in ("oversize-response", "backend-raise", "nest-raise"))},
        "F6": {"criterion": "every oversize request refused before writing, session then completes",
               "holds": bool(details["oversize-request"]) and all(
                   "preflight:capacity" in row["result"].get("outcomes", []) and row["result"].get("error") is None
                   and "finished" in row["result"].get("outcomes", []) for row, _ in details["oversize-request"])},
        "F7": {"criterion": "soak: RSS growth < 10 % after the first 10 %, descriptors constant",
               "holds": bool(soaks) and all(s["client_rss_growth"] is not None and s["client_rss_growth"] < 0.10
                                            and s["owner_rss_growth"] is not None and s["owner_rss_growth"] < 0.10
                                            and s["client_fds"][0] == s["client_fds"][1]
                                            and s["owner_fds"][0] == s["owner_fds"][1]
                                            for runs in soaks.values() for s in runs)},
    }
    analysis = {"protocol_sha256": schedule["protocol_sha256"], "trials": len(rows),
                "expected_trials": len(schedule["order"]),
                "table": {f"{s}/{o}": dict(c) for (s, o), c in sorted(table.items())},
                "frame_faults": {"trials": len(frame), "damaged": len(damaged), "undamaged": len(undamaged),
                                 "damaged_in_length_prefix": sum(1 for row, _ in damaged
                                                                 if row["result"]["relay"].get("in_header"))},
                "stall_seconds": {"median": statistics.median(stall_seconds) if stall_seconds else None,
                                  "max": max(stall_seconds) if stall_seconds else None},
                "kill_owner_steps_before_kill": dict(Counter(len(row["result"].get("outcomes", []))
                                                             for row, _ in details["kill-owner"])),
                "soaks": soaks, "hypotheses": hypotheses}
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"])


if __name__ == "__main__":
    main()
