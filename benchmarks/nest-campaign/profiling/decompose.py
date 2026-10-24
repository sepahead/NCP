"""The parts of each step from the timestamps of timed_owner.py or fake_owner.py (see README.md).

Usage: decompose.py MARKS_FILE
"""

from __future__ import annotations

import json
import statistics
import sys

PARTS = ("pre", "work", "pack", "encode", "send", "away")


def main() -> None:
    steps, current, previous_send = [], None, None
    for kind, start, end in json.load(open(sys.argv[1])):
        if kind == "r":  # a request has arrived: the previous step is complete
            if current is not None and "send" in current and previous_send is not None:
                current["away"] = end - previous_send
                steps.append(current)
            current = {"arrived": end}
        elif kind == "w":
            current["pre"], current["work"] = start - current["arrived"], end - start
        elif kind == "p":
            current["pack"], current["packed"] = end - start, end
        elif kind == "s":
            if "packed" in current:
                current["encode"], current["send"] = start - current["packed"], end - start
            previous_send = end
    steps = steps[1:]  # the first step follows prepare
    for part in PARTS:
        values = sorted(step[part] / 1000 for step in steps)
        print(
            f"{part:7} median {statistics.median(values):9.1f} µs   p90 {values[int(0.9 * len(values))]:9.1f}   "
            f"p99 {values[int(0.99 * len(values))]:9.1f}"
        )
    print(f"steps   {len(steps)}")


if __name__ == "__main__":
    main()
