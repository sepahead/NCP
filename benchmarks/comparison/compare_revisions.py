#!/usr/bin/env python3
"""Compare the NCP 2 arms of two result sets of the comparison benchmark (protocol 3, exploratory).

Usage: compare_revisions.py BEFORE_RESULTS AFTER_RESULTS
Reads analysis.json of both, for example results-2 (the SDKs before revision 3) and results-3
(revision 7), and writes AFTER_RESULTS/revisions.md: for each NCP 2 arm and N, the statistic of
each set, the ratio, and whether the ranges of the block medians overlap. Standard library only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    before_dir, after_dir = Path(sys.argv[1]), Path(sys.argv[2])
    before = json.loads((before_dir / "analysis.json").read_text())["configurations"]
    after = json.loads((after_dir / "analysis.json").read_text())["configurations"]
    lines = [
        f"# NCP 2 arms: {after_dir.name} against {before_dir.name}",
        "",
        "Exploratory (PROTOCOL-3.md, section 6). Statistic: the median of the three block medians, in µs; "
        "range: the smallest to the largest block median. A ratio below 1 means that the later SDKs are faster.",
        "",
        f"| Configuration | {before_dir.name} | {after_dir.name} | Ratio | Ranges overlap |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for name in sorted(after):
        if not name.startswith("ncp2-") or name not in before:
            continue
        a, b = before[name], after[name]
        if "statistic_us" not in a or "statistic_us" not in b:
            continue
        overlap = a["range_us"][0] <= b["range_us"][1] and b["range_us"][0] <= a["range_us"][1]
        lines.append(f"| `{name}` | {a['statistic_us']:.3g} | {b['statistic_us']:.3g} | "
                     f"{b['statistic_us'] / a['statistic_us']:.2f} | {'yes' if overlap else 'no'} |")
    (after_dir / "revisions.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
