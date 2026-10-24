#!/usr/bin/env python3
"""Analyze protocol 4 of the NEST campaign (see PROTOCOL-4.md, Conditions, Measures, and Hypotheses).

Usage: analyze4.py RESULTS_DIR PROTOCOL2_RESULTS_DIR PROTOCOL3_RESULTS_DIR

Writes RESULTS_DIR/analysis.json and RESULTS_DIR/summary.md. The measures of protocol 3 and G1 to
G5 come from analyze3.py; this file adds the conditions, the time of each step, G6, and G7.
Standard library only.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import analyze3
from analyze3 import arm_of, key_of, summary_of

TARGET_SPIKES_US = 150.0  # the design target of G3 (0.15 ms), applied to the overhead in G7
DRIFT_LOW, DRIFT_HIGH = 0.9, 1.1
TIMING_HYPOTHESES = ("G1", "G2", "G3", "G6", "G7")
COUPLED = ("chunked-pipe", "ncp2-rs", "ncp2-py", "ncp-rs-1.0.1", "ncp-py-1.0.1")


def last_attempts(rows: list[dict]) -> list[dict]:
    """The last attempt of each run. Rows are in the order in which they were written."""
    latest: dict = {}
    for row in rows:
        latest[(row["block"], row["config"])] = row
    return list(latest.values())


def valid(row: dict) -> bool:
    """The validity rule of protocol 3 (analyze3.analyze)."""
    arm = arm_of(row)
    if row["returncode"] != 0 or "wall_s" not in row:
        return False
    if arm.startswith("ncp") and (row.get("spikes") != row.get("recorded") or row.get("child_exit") not in (0, None)):
        return False
    return True


def drift(rows: list[dict], protocol2: list[dict]) -> dict:
    """The chunked wall time over protocol 2's, for the same configuration and block."""
    reference = {
        (row["config"], row["block"]): row["wall_s"]
        for row in protocol2
        if row.get("returncode") == 0 and arm_of(row) == "chunked"
    }
    ratios = defaultdict(list)
    for row in rows:
        if valid(row) and arm_of(row) == "chunked" and (row["config"], row["block"]) in reference:
            ratios[row["block"]].append(row["wall_s"] / reference[(row["config"], row["block"])])
    blocks = {str(block): summary_of(values) for block, values in sorted(ratios.items())}
    outside = [block for block, entry in blocks.items() if not DRIFT_LOW <= entry["median"] <= DRIFT_HIGH]
    return {"blocks": blocks, "outside": outside, "admissible": bool(blocks) and not outside}


def step_measures(rows: list[dict]) -> dict:
    """Per configuration: the overhead, the work per step, and the pause effect of each arm."""
    by_key: dict = defaultdict(lambda: defaultdict(dict))  # key -> block -> arm -> row
    for row in rows:
        if valid(row):
            by_key[key_of(row)][row["block"]][arm_of(row)] = row
    measures = {}
    for key, blocks in sorted(by_key.items()):
        part, network, n, threads, delta = key
        suffix = "-spikes" if part == "D4" else ""
        reference = "chunked" + suffix
        entry = {
            "part": part,
            "network": network,
            "n": n,
            "threads": threads,
            "delta_ms": delta,
            "overhead_median_us": {},
            "overhead_p99_us": {},
            "work_median_us": {},
            "pause_effect_us": {},
        }
        arms = sorted({arm for arms in blocks.values() for arm in arms})
        for arm in arms:
            rows_of_arm = {block: arms_[arm] for block, arms_ in blocks.items() if arm in arms_}
            work = {block: row["work_us"]["median_us"] for block, row in rows_of_arm.items() if "work_us" in row}
            if work:
                entry["work_median_us"][arm] = summary_of(list(work.values()))
            overhead = {block: row["overhead_us"] for block, row in rows_of_arm.items() if "overhead_us" in row}
            if overhead:
                median = summary_of([value["median_us"] for value in overhead.values()])
                median["by_block"] = {block: value["median_us"] for block, value in overhead.items()}
                entry["overhead_median_us"][arm] = median
                entry["overhead_p99_us"][arm] = summary_of([value["p99_us"] for value in overhead.values()])
            if arm != reference and work:
                pause = [
                    work[block] - arms_[reference]["work_us"]["median_us"]
                    for block, arms_ in blocks.items()
                    if block in work and reference in arms_ and "work_us" in arms_[reference]
                ]
                if pause:
                    entry["pause_effect_us"][arm] = summary_of(pause)
        measures[analyze3.label(key)] = entry
    return measures


def main() -> None:
    results, protocol2_dir, protocol3_dir = (Path(argument) for argument in sys.argv[1:4])
    schedule = json.loads((results / "schedule.json").read_text())
    every_attempt = analyze3.read_rows(results)
    rows = last_attempts(every_attempt)
    timing_rows = [row for row in rows if not row["disturbed"]]
    protocol2, protocol3 = analyze3.read_rows(protocol2_dir), analyze3.read_rows(protocol3_dir)
    against2 = analyze3.analyze(rows, schedule, protocol2)
    against3 = analyze3.analyze(rows, schedule, protocol3)
    timing = analyze3.analyze(timing_rows, schedule, None)
    conditions = drift(timing_rows, protocol2)
    steps = step_measures(timing_rows)

    hypotheses = {name: timing["hypotheses"][name] for name in ("G1", "G2", "G3")}
    hypotheses["G4"] = against2["hypotheses"]["G4"]
    g5_2, g5_3 = against2["hypotheses"]["G5"], against3["hypotheses"]["G5"]
    hypotheses["G5"] = {
        "criterion": "the recorder totals equal those of protocols 2 and 3 for every configuration "
        "and block that both ran",
        "compared": [g5_2["compared"], g5_3["compared"]],
        "differing": g5_2["differing"] + g5_3["differing"],
        "holds": g5_2["holds"] and g5_3["holds"],
    }
    comparisons = []
    for entry in steps.values():
        if entry["part"] != "D1" or entry["delta_ms"] != 1.0:
            continue
        for new, old in (("ncp2-py", "ncp-py-1.0.1"), ("ncp2-rs", "ncp-rs-1.0.1")):
            a, b = entry["overhead_median_us"].get(new), entry["overhead_median_us"].get(old)
            holds = (
                bool(a and b)
                and len(a["by_block"]) == len(b["by_block"]) == schedule["blocks"]
                and all(a["by_block"][block] < b["by_block"][block] for block in a["by_block"])
            )
            comparisons.append(
                {
                    "config": f"{entry['network']}/{entry['n']}/{entry['threads']}",
                    "new": new,
                    "old": old,
                    "holds": holds,
                }
            )
    hypotheses["G6"] = {
        "criterion": "D1, delta 1 ms: the median overhead of NCP 2 is lower than that of NCP 1.0.1, "
        "for each host language, size, and thread count, in every block",
        "comparisons": comparisons,
        "holds": len(comparisons) == 12 and all(c["holds"] for c in comparisons),
    }
    d4 = {
        f"{entry['n']}/{entry['delta_ms']:g}": entry["overhead_median_us"].get("ncp2-rs-spikes", {}).get("median")
        for entry in steps.values()
        if entry["part"] == "D4"
    }
    hypotheses["G7"] = {
        "criterion": "D4: every ncp2-rs-spikes configuration has a median overhead of at most 0.15 ms",
        "values_us": d4,
        "holds": len(d4) == 4 and all(v is not None and v <= TARGET_SPIKES_US for v in d4.values()),
    }
    if not conditions["admissible"]:
        for name in TIMING_HYPOTHESES:
            hypotheses[name]["holds"] = None
            hypotheses[name]["status"] = "not adjudicated: the reference drifted in block(s) " + ", ".join(
                conditions["outside"] or ["(none compared)"]
            )
    disturbed = [
        {"config": row["config"], "block": row["block"], "attempt": row["attempt"]}
        for row in every_attempt
        if row["disturbed"]
    ]
    analysis = {
        "protocol_sha256": schedule["protocol_sha256"],
        "runs": len(rows),
        "attempts": len(every_attempt),
        "expected_runs": len(schedule["order"]),
        "disturbed_attempts": disturbed,
        "still_disturbed": [
            d
            for d in disturbed
            if (d["block"], d["config"]) in {(row["block"], row["config"]) for row in rows if row["disturbed"]}
        ],
        "waited_s": sum(row.get("waited_s", 0) for row in every_attempt),
        "invalid_runs": against2["invalid_runs"],
        "count_disagreements": against2["count_disagreements"],
        "reference_drift": conditions,
        "step_measures": steps,
        "configurations": timing["configurations"],
        "hypotheses": hypotheses,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    (results / "summary.md").write_text(summary(analysis, timing))
    for name, entry in hypotheses.items():
        state = "not adjudicated" if entry["holds"] is None else "holds" if entry["holds"] else "does not hold"
        print(f"{name}: {state}")


def micro(entry: dict | None) -> str:
    if not entry:
        return "–"
    return f"{entry['median']:.1f} ({entry['min']:.1f}–{entry['max']:.1f})"


def summary(analysis: dict, timing: dict) -> str:
    lines = [
        "# NEST campaign, protocol 4: tables",
        "",
        "Generated by `analyze4.py`. Times of a step in µs: the median over three blocks of each run's value, "
        "with the smallest and largest block value.",
        "",
        f"{analysis['runs']} of {analysis['expected_runs']} runs in {analysis['attempts']} attempts; "
        f"{len(analysis['disturbed_attempts'])} disturbed attempts, {len(analysis['still_disturbed'])} runs "
        f"still disturbed after the last attempt; {len(analysis['invalid_runs'])} invalid runs; "
        f"{len(analysis['count_disagreements'])} disagreements of recorded spike counts; "
        f"{analysis['waited_s'] / 60:.0f} minutes of waiting for the conditions.",
        "",
        "## Drift of the reference",
        "",
        "The `chunked` wall time over protocol 2's, for the same configuration and block.",
        "",
        "| Block | Median | Smallest | Largest | Configurations |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for block, entry in analysis["reference_drift"]["blocks"].items():
        lines.append(
            f"| {block} | {entry['median']:.3f} | {entry['min']:.3f} | {entry['max']:.3f} | {entry['blocks']} |"
        )
    lines += [
        "",
        f"Every block between {DRIFT_LOW} and {DRIFT_HIGH}: "
        f"{'yes' if analysis['reference_drift']['admissible'] else 'no'}.",
        "",
    ]
    for part, suffix, title in (
        ("D1", "", "Brunel network"),
        ("D2", "", "Alpha and adaptive networks"),
        ("D3", "", "Network size, 8 threads, 1 ms"),
        ("D4", "-spikes", "Spikes returned at each step, 4 threads"),
    ):
        arms = [arm + suffix for arm in COUPLED]
        lines += [
            f"## {part}. {title}: overhead per exchange, µs",
            "",
            "Median overhead; below it, in the second table, the 99th percentile.",
            "",
            "| Network | Neurons | Threads | Δ (ms) | " + " | ".join(arms) + " |",
            "| --- | ---: | ---: | ---: |" + " ---: |" * len(arms),
        ]
        entries = [e for e in analysis["step_measures"].values() if e["part"] == part]
        for e in entries:
            lines.append(
                f"| {e['network']} | {e['n']} | {e['threads']} | {e['delta_ms']:g} | "
                + " | ".join(micro(e["overhead_median_us"].get(arm)) for arm in arms)
                + " |"
            )
        lines += [
            "",
            "| Network | Neurons | Threads | Δ (ms) | " + " | ".join(arms) + " |",
            "| --- | ---: | ---: | ---: |" + " ---: |" * len(arms),
        ]
        for e in entries:
            lines.append(
                f"| {e['network']} | {e['n']} | {e['threads']} | {e['delta_ms']:g} | "
                + " | ".join(micro(e["overhead_p99_us"].get(arm)) for arm in arms)
                + " |"
            )
        lines += [
            "",
            f"Work per step of `chunked{suffix}`, and the pause effect of each coupled arm (its work per "
            "step minus that of the reference in the same block), µs:",
            "",
            f"| Network | Neurons | Threads | Δ (ms) | chunked{suffix} work | " + " | ".join(arms) + " |",
            "| --- | ---: | ---: | ---: | ---: |" + " ---: |" * len(arms),
        ]
        for e in entries:
            lines.append(
                f"| {e['network']} | {e['n']} | {e['threads']} | {e['delta_ms']:g} | "
                f"{micro(e['work_median_us'].get('chunked' + suffix))} | "
                + " | ".join(micro(e["pause_effect_us"].get(arm)) for arm in arms)
                + " |"
            )
        lines.append("")
    lines += [
        "# The measures of protocol 3",
        "",
        "Cost per exchange in ms, from the difference of wall times (analyze3.py), on the runs that were not "
        "disturbed.",
        "",
    ]
    lines += analyze3.tables(timing)
    lines += ["", "## Hypotheses", "", "| # | Criterion | Holds |", "| --- | --- | --- |"]
    for name, entry in analysis["hypotheses"].items():
        if entry["holds"] is None:
            state = entry["status"]
        else:
            state = "yes" if entry["holds"] else "no"
        if entry.get("value") is not None:
            state += f" ({entry['value']:.3f} ms)"
        lines.append(f"| {name} | {entry['criterion']} | {state} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
