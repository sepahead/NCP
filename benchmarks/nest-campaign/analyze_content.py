#!/usr/bin/env python3
"""Summarize the content campaign (see PROTOCOL-CONTENT.md). Usage: analyze_content.py RESULTS_DIR"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def main() -> None:
    results = Path(sys.argv[1])
    rows = [json.loads(line) for line in (results / "trials.jsonl").read_text().splitlines() if line.strip()]
    failed = [f"{r['config']} block {r['block']}" for r in rows if r["returncode"] != 0]
    good = [r for r in rows if r["returncode"] == 0]
    by_threads = defaultdict(lambda: {"trials": 0, "ncp_exact": 0, "music_exact": 0, "channels_exact": []})
    for r in good:
        entry = by_threads[r["threads"]]
        entry["trials"] += 1
        entry["ncp_exact"] += r["ncp_exact"]
        entry["music_exact"] += r["music_exact"]
        entry["channels_exact"].append(r["music_channels_exact"])
    hypotheses = {
        "C1": {"criterion": "NCP host receives exactly the reference in every trial",
               "holds": not failed and all(r["ncp_exact"] for r in good)},
        "C2": {"criterion": "NEST recorder in the MUSIC run equals the reference in every trial",
               "holds": not failed and all(r["music_recorded_equals_reference"] for r in good)},
        "C3": {"criterion": "with one thread, MUSIC delivers exactly the recorded spikes in every trial",
               "holds": not failed and all(r["music_exact"] for r in good if r["threads"] == 1)},
    }
    summary = {threads: {"trials": e["trials"], "ncp_exact": e["ncp_exact"], "music_exact": e["music_exact"],
                         "music_channels_exact_min": min(e["channels_exact"]),
                         "music_channels_exact_max": max(e["channels_exact"])}
               for threads, e in sorted(by_threads.items())}
    (results / "analysis.json").write_text(json.dumps({"trials": len(rows), "failed": failed, "by_threads": summary,
                                                       "hypotheses": hypotheses}, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    for key, value in hypotheses.items():
        print(key, value["criterion"], "->", value["holds"])


if __name__ == "__main__":
    main()
