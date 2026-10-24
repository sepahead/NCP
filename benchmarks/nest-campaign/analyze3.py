#!/usr/bin/env python3
"""Analyze protocol 3 of the NEST campaign (see PROTOCOL-3.md, Measures and Hypotheses).

Usage: analyze3.py RESULTS_DIR [PROTOCOL2_RESULTS_DIR]

Writes RESULTS_DIR/analysis.json and RESULTS_DIR/summary.md. With PROTOCOL2_RESULTS_DIR, G5 compares
the recorder totals with protocol 2. Standard library only. analyze4.py reuses `analyze`.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

T_BIO_MS = 2000.0
NCP_ARMS = ("ncp2-py", "ncp2-rs", "ncp-py-1.0.1", "ncp-rs-1.0.1")


def key_of(row: dict) -> tuple:
    return (row["part"], row["network"], row["n"], row["threads"], row["delta_ms"])


def arm_of(row: dict) -> str:
    """The protocol arm, from the configuration name, which ends with it. A host's own arm field
    can differ (for example ncp2-rs-count), so the name is authoritative."""
    return "-".join(row["config"].split("-")[5:])


def label(key: tuple) -> str:
    part, network, n, threads, delta = key
    return f"{part}/{network}/{n}/{threads}/{delta:g}"


def summary_of(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"median": statistics.median(values), "min": min(values), "max": max(values), "blocks": len(values)}


def read_rows(results: Path) -> list[dict]:
    return [json.loads(line) for line in (results / "runs.jsonl").read_text().splitlines() if line.strip()]


def analyze(rows: list[dict], schedule: dict, earlier: list[dict] | None) -> dict:
    """The analysis of protocol 3. `earlier` holds the runs of protocol 2 for G5, or None."""
    runs: dict = defaultdict(dict)  # (configuration key, block) -> arm -> row
    invalid = []
    for row in rows:
        arm = arm_of(row)
        valid = row["returncode"] == 0 and "wall_s" in row
        if valid and arm.startswith("ncp") and row.get("spikes") != row.get("recorded"):
            valid = False
        if valid and arm.startswith("ncp") and row.get("child_exit") not in (0, None):
            valid = False
        if valid:
            runs[(key_of(row), row["block"])][arm] = row
        else:
            invalid.append({"config": row["config"], "block": row["block"], "returncode": row["returncode"],
                            "stderr_tail": row.get("stderr_tail", [])})
    # Recorded spike counts must agree across arms within a configuration and block (MUSIC with more
    # than one thread is compared by NEST's recorder, which is correct; its delivered count is not).
    disagreements = []
    for (key, block), arms in runs.items():
        recorded = {arm: row.get("recorded") for arm, row in arms.items() if row.get("recorded") is not None}
        if len(set(recorded.values())) > 1:
            disagreements.append({"config": label(key), "block": block, "recorded": recorded})
    configurations: dict = {}
    by_key: dict = defaultdict(dict)
    for (key, block), arms in runs.items():
        by_key[key][block] = arms
    for key, blocks in sorted(by_key.items()):
        part, network, n, threads, delta = key
        exchanges = T_BIO_MS / delta
        entry = {"part": part, "network": network, "n": n, "threads": threads, "delta_ms": delta,
                 "exchanges": exchanges, "wall_s_median": {}, "ms_per_exchange": {}, "ms_over_pipe": {},
                 "pause_ms_per_exchange": None, "music": None}
        arm_names = sorted({arm for arms in blocks.values() for arm in arms})
        for arm in arm_names:
            entry["wall_s_median"][arm] = statistics.median(
                [arms[arm]["wall_s"] for arms in blocks.values() if arm in arms])
        for base in NCP_ARMS:
            for suffix, reference in (("", "chunked"), ("-spikes", "chunked-spikes")):
                arm = base + suffix
                values = [(arms[arm]["wall_s"] - arms[reference]["wall_s"]) / exchanges * 1000
                          for arms in blocks.values() if arm in arms and reference in arms]
                cost = summary_of(values)
                if cost:
                    cost["by_block"] = {block: (arms[arm]["wall_s"] - arms[reference]["wall_s"]) / exchanges * 1000
                                        for block, arms in blocks.items() if arm in arms and reference in arms}
                    entry["ms_per_exchange"][arm] = cost
                # Exploratory: the cost of the protocol alone, over the raw round trip of chunked-pipe.
                pipe = reference.replace("chunked", "chunked-pipe")
                own = summary_of([(arms[arm]["wall_s"] - arms[pipe]["wall_s"]) / exchanges * 1000
                                  for arms in blocks.values() if arm in arms and pipe in arms])
                if own:
                    entry["ms_over_pipe"][arm] = own
        for reference in ("chunked", "chunked-spikes"):
            pipe = reference.replace("chunked", "chunked-pipe")
            pause = summary_of([(arms[pipe]["wall_s"] - arms[reference]["wall_s"]) / exchanges * 1000
                                for arms in blocks.values() if pipe in arms and reference in arms])
            if pause:
                entry["pause_ms_per_exchange"] = pause
        music = [arms["music"]["wall_s"] - arms["mono"]["wall_s"] for arms in blocks.values()
                 if "music" in arms and "mono" in arms]
        if music:
            per_run = summary_of(music)
            entry["music"] = {"s_per_run": per_run,
                              "ms_per_exchange": {k: per_run[k] / exchanges * 1000 for k in ("median", "min", "max")}}
        configurations[label(key)] = entry
    hypotheses = {}
    d1_fast = [c for c in configurations.values() if c["part"] == "D1" and c["delta_ms"] == 1.0]
    comparisons = []
    for c in d1_fast:
        for new, old in (("ncp2-py", "ncp-py-1.0.1"), ("ncp2-rs", "ncp-rs-1.0.1")):
            a, b = c["ms_per_exchange"].get(new), c["ms_per_exchange"].get(old)
            holds = (bool(a and b) and len(a["by_block"]) == len(b["by_block"]) == schedule["blocks"]
                     and all(a["by_block"][k] < b["by_block"][k] for k in a["by_block"]))
            comparisons.append({"config": f"{c['network']}/{c['n']}/{c['threads']}", "new": new, "old": old,
                                "holds": holds})
    hypotheses["G1"] = {"criterion": "D1, delta 1 ms: NCP 2 costs less per exchange than NCP 1.0.1, for each host "
                        "language, size, and thread count, in every block", "comparisons": comparisons,
                        "holds": all(c["holds"] for c in comparisons) and len(comparisons) == 12}
    rust = [c["ms_per_exchange"]["ncp2-rs"]["median"] for c in d1_fast if "ncp2-rs" in c["ms_per_exchange"]]
    value = statistics.median(rust) if rust else None
    hypotheses["G2"] = {"criterion": "D1, delta 1 ms: the median of the 6 median costs per exchange of ncp2-rs is at "
                        "most 0.10 ms", "value": value, "holds": value is not None and value <= 0.10}
    d4 = [c for c in configurations.values() if c["part"] == "D4"]
    d4_values = {f"{c['n']}/{c['delta_ms']:g}": c["ms_per_exchange"].get("ncp2-rs-spikes", {}).get("median")
                 for c in d4}
    hypotheses["G3"] = {"criterion": "D4: every ncp2-rs-spikes configuration, Brunel with 10,000 neurons at 5 ms "
                        "included, has a median cost per exchange of at most 0.15 ms", "values": d4_values,
                        "holds": len(d4_values) == 4 and all(v is not None and v <= 0.15 for v in d4_values.values())}
    hypotheses["G4"] = {"criterion": "every run is valid and the recorded counts agree across arms",
                        "invalid": len(invalid), "disagreements": len(disagreements),
                        "holds": not invalid and not disagreements}
    if earlier is not None:
        totals = {}
        for row in earlier:
            if row.get("returncode") == 0 and row.get("recorded") is not None:
                totals[(key_of(row), row["block"])] = row["recorded"]
        compared, differing = 0, []
        for (key, block), arms in runs.items():
            if (key, block) in totals:
                for arm, row in arms.items():
                    if row.get("recorded") is not None:
                        compared += 1
                        if row["recorded"] != totals[(key, block)]:
                            differing.append({"config": label(key), "block": block, "arm": arm})
        hypotheses["G5"] = {"criterion": "the recorder totals equal those of protocol 2 for every configuration and "
                            "block that both ran", "compared": compared, "differing": differing,
                            "holds": compared > 0 and not differing}
    return {"protocol_sha256": schedule["protocol_sha256"], "runs": len(rows),
            "expected_runs": len(schedule["order"]), "invalid_runs": invalid,
            "count_disagreements": disagreements, "configurations": configurations, "hypotheses": hypotheses}


def main() -> None:
    results = Path(sys.argv[1])
    schedule = json.loads((results / "schedule.json").read_text())
    earlier = read_rows(Path(sys.argv[2])) if len(sys.argv) > 2 else None
    analysis = analyze(read_rows(results), schedule, earlier)
    hypotheses = analysis["hypotheses"]
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1) + "\n")
    (results / "summary.md").write_text(summary(analysis))
    for name, entry in hypotheses.items():
        print(f"{name}: {'holds' if entry['holds'] else 'does not hold'}")


def cell(entry: dict | None) -> str:
    if not entry:
        return "–"
    return f"{entry['median']:.3f} ({entry['min']:.3f}–{entry['max']:.3f})"


def summary(analysis: dict) -> str:
    lines = ["# NEST campaign, protocol 3: tables", "",
             "Generated by `analyze3.py`. Cost per exchange in ms: the median over three blocks, with the smallest and "
             "largest block value. MUSIC's cost per run is divided by the number of exchanges of the NCP arms at the "
             "same interval, to compare it on the same scale.", "",
             f"{analysis['runs']} of {analysis['expected_runs']} runs; {len(analysis['invalid_runs'])} invalid; "
             f"{len(analysis['count_disagreements'])} disagreements of recorded spike counts.", ""]
    lines += tables(analysis)
    lines += ["", "## Hypotheses", "", "| # | Criterion | Holds |", "| --- | --- | --- |"]
    for name, entry in analysis["hypotheses"].items():
        extra = f" ({entry['value']:.3f} ms)" if entry.get("value") is not None else ""
        lines.append(f"| {name} | {entry['criterion']} | {'yes' if entry['holds'] else 'no'}{extra} |")
    return "\n".join(lines) + "\n"


def tables(analysis: dict) -> list[str]:
    """The tables of the cost per exchange (parts D1 to D4) and of where the cost goes."""
    lines: list[str] = []
    for part, arms, title in (
        ("D1", ("ncp2-rs", "ncp2-py", "ncp-rs-1.0.1", "ncp-py-1.0.1"), "Brunel network"),
        ("D2", ("ncp2-rs", "ncp2-py", "ncp-rs-1.0.1", "ncp-py-1.0.1"), "Alpha and adaptive networks"),
        ("D3", ("ncp2-rs", "ncp2-py", "ncp-rs-1.0.1", "ncp-py-1.0.1"), "Network size, 8 threads, 1 ms"),
        ("D4", ("ncp2-rs-spikes", "ncp2-py-spikes", "ncp-rs-1.0.1-spikes", "ncp-py-1.0.1-spikes"),
         "Spikes returned at each step, 4 threads"),
    ):
        lines += [f"## {part}. {title}: cost per exchange, ms", "",
                  "| Network | Neurons | Threads | Δ (ms) | " + " | ".join(arms) + " | MUSIC |",
                  "| --- | ---: | ---: | ---: |" + " ---: |" * (len(arms) + 1)]
        for entry in analysis["configurations"].values():
            if entry["part"] != part:
                continue
            music = entry["music"]["ms_per_exchange"] if entry["music"] else None
            lines.append(f"| {entry['network']} | {entry['n']} | {entry['threads']} | {entry['delta_ms']:g} | "
                         + " | ".join(cell(entry["ms_per_exchange"].get(arm)) for arm in arms) + f" | {cell(music)} |")
        lines.append("")
    lines += ["## Where the cost goes (exploratory)", "",
              "Pause: `chunked-pipe` minus `chunked` (or the `-spikes` pair), a raw round trip to a peer process after "
              "each interval. Protocol: an NCP arm minus `chunked-pipe`. In ms per exchange.", "",
              "| Part | Network | Neurons | Threads | Δ (ms) | Pause | NCP 2, Rust host | NCP 2, Python host | "
              "NCP 1.0.1, Rust host | NCP 1.0.1, Python host |",
              "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for entry in analysis["configurations"].values():
        if not (entry["part"] == "D4" or (entry["part"] == "D1" and entry["delta_ms"] == 1.0)):
            continue
        suffix = "-spikes" if entry["part"] == "D4" else ""
        own = [cell(entry["ms_over_pipe"].get(arm + suffix)) for arm in ("ncp2-rs", "ncp2-py", "ncp-rs-1.0.1",
                                                                          "ncp-py-1.0.1")]
        lines.append(f"| {entry['part']} | {entry['network']} | {entry['n']} | {entry['threads']} | "
                     f"{entry['delta_ms']:g} | {cell(entry['pause_ms_per_exchange'])} | " + " | ".join(own) + " |")
    return lines


if __name__ == "__main__":
    main()
