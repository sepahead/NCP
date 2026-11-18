#!/usr/bin/env python3
"""Analyze protocol 4 of the comparison benchmark (see PROTOCOL-4.md): NCP 2 in Rust against
iceoryx2 over shared memory.

Usage: analyze_shm.py RESULTS_DIR
Writes RESULTS_DIR/analysis.json, RESULTS_DIR/summary.md, and RESULTS_DIR/figures/shm_{light,dark}.svg.
It uses the statistics of analyze.py: per configuration, the median of the block medians, and the
range of the block medians.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import analyze as A
import matplotlib.pyplot as plt

NCP2 = (("ncp2-rust-rust-pipe", "NCP 2, pipe"), ("ncp2-rust-rust-unix", "NCP 2, Unix socket"),
        ("ncp2-rust-rust-tcp", "NCP 2, TCP"))
PANELS = (
    ("Without an added check", (("iox2-rust-shm", "iceoryx2, shared memory"),) + NCP2 + (("raw-rust-pipe", "Raw pipe"),)),
    ("With SHA-256 at both ends", (("iox2-rust-shm-sha256", "iceoryx2, shared memory"),) + NCP2
     + (("raw-rust-pipe-sha256", "Raw pipe"),)),
)
SMALL = (0, 127, 1788)


def decide(stats: dict, blocks: int) -> dict:
    """Q1: without an added check, iceoryx2 is faster than NCP 2 over every link, at N of 0, 127,
    and 1788, in every block. Q2: with the same check at both ends, iceoryx2 is faster than NCP 2
    over a pipe at N of 0, 127, and 1788, in every block."""
    q1 = [A.lower_in_every_block(stats, f"iox2-rust-shm-n{n}", f"{arm}-n{n}", blocks) for n in SMALL for arm, _ in NCP2]
    q2 = [A.lower_in_every_block(stats, f"iox2-rust-shm-sha256-n{n}", f"ncp2-rust-rust-pipe-n{n}", blocks) for n in SMALL]
    return {"Q1": {"comparisons": q1, "supported": all(c["holds"] for c in q1)},
            "Q2": {"comparisons": q2, "supported": all(c["holds"] for c in q2)}}


def figure(stats: dict, theme: dict, path: Path) -> None:
    subtitle = ("One Rust client and one Rust server on one laptop; the time of one call with N spikes back. "
                "Dot: median of three block medians; bar: their range. iceoryx2 polls without sleeping at both ends.")
    figure, axes = plt.subplots(1, 2, figsize=(A.WIDTH, 4.2 + A.header_height(subtitle, 1)), sharey=True)
    colours = {"iox2": theme["accent2"], "ncp2": theme["accent"], "raw": theme["floor"]}
    styles = {"NCP 2, pipe": "-", "NCP 2, Unix socket": "--", "NCP 2, TCP": ":"}
    handles = {}
    for axis, (title, arms) in zip(axes, PANELS, strict=True):
        for arm, label in arms:
            xs, ys, lows, highs = [], [], [], []
            for index, n in enumerate(A.SPIKES):
                entry = stats.get(f"{arm}-n{n}", {})
                if "statistic_us" in entry:
                    xs.append(index)
                    ys.append(entry["statistic_us"])
                    lows.append(entry["statistic_us"] - entry["range_us"][0])
                    highs.append(entry["range_us"][1] - entry["statistic_us"])
            colour = colours[arm.split("-")[0]]
            line = axis.errorbar(xs, ys, yerr=[lows, highs], color=colour, linestyle=styles.get(label, "-"),
                                 linewidth=2.0, marker="o", markersize=6, capsize=0)
            handles.setdefault(label, line)
        axis.set_yscale("log")
        axis.yaxis.set_major_formatter(A.FuncFormatter(lambda v, _: f"{v:g}"))
        axis.yaxis.set_minor_formatter(A.NullFormatter())
        axis.set_xticks(range(len(A.SPIKES)))
        axis.set_xticklabels([f"{n:,}" for n in A.SPIKES])
        axis.set_xlabel("spikes back per call (N)")
        axis.grid(axis="y", which="major", color=theme["grid"], linewidth=0.8)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        axis.set_title(title, loc="left")
    axes[0].set_ylabel("time of one call (µs, log scale)")
    rect, legend_y = A.frame(figure, theme, "NCP 2 and iceoryx2 between two Rust processes", subtitle, legend_rows=1)
    figure.legend(list(handles.values()), list(handles), loc="upper left", bbox_to_anchor=(0.1 / A.WIDTH, legend_y),
                  ncol=5, frameon=False, fontsize=A.SMALL, columnspacing=1.2)
    figure.tight_layout(rect=rect, w_pad=1.6)
    A.save(figure, path, "NCP 2 and iceoryx2 between two Rust processes",
           "Two panels, without and with a SHA-256 check at both ends: the time of one call with 0, 127, 1788, and "
           "87381 spikes back, on a log scale, for iceoryx2 over shared memory, NCP 2 over a pipe, a Unix socket, and "
           "TCP, and a raw pipe. Values are in summary.md.")


def main() -> None:
    results = Path(sys.argv[1])
    rows, schedule, validity = A.load(results)
    final = A.final_rows(rows)
    stats = A.statistics_by_config(final, schedule["blocks"])
    decisions = decide(stats, schedule["blocks"])
    started = min(row["started_utc"] for row in rows)
    analysis = {
        "context": {"protocol": schedule["protocol"], "protocol_sha256": schedule["protocol_sha256"],
                    "commit": schedule["commit"], "worktree_clean": schedule["worktree_clean"], "runs": len(rows),
                    "started": started, "finished": max(row["finished_utc"] for row in rows),
                    "disturbed_attempts": sum(1 for row in rows if row.get("disturbed")),
                    "power": sorted({row.get("power", "not recorded") for row in rows})},
        "environment": validity.get("environment", {}),
        "configurations": stats,
        "hypotheses": decisions,
    }
    (results / "analysis.json").write_text(json.dumps(analysis, indent=1, sort_keys=True) + "\n")
    lines = ["# Comparison benchmark: results of protocol 4", "",
             f"Runs: {len(rows)}; commit `{schedule['commit'][:7]}`; from {started}.", "",
             "| Arm | " + " | ".join(f"N = {n}" for n in A.SPIKES) + " |", "| --- |" + " ---: |" * len(A.SPIKES)]
    seen = set()
    for _, arms in PANELS:
        for arm, label in arms:
            if arm in seen:  # the NCP 2 arms belong to both panels
                continue
            seen.add(arm)
            cells = []
            for n in A.SPIKES:
                entry = stats.get(f"{arm}-n{n}", {})
                cells.append(f"{entry['statistic_us']:.3g} ({entry['range_us'][0]:.3g} to {entry['range_us'][1]:.3g})"
                             if "statistic_us" in entry else "not measured")
            lines.append(f"| `{arm}` | " + " | ".join(cells) + " |")
    lines += ["", "Statistic in µs: the median of the three block medians, with their range.", ""]
    for name, entry in decisions.items():
        lines.append(f"- {name}: {'supported' if entry['supported'] else 'not supported'}")
    (results / "summary.md").write_text("\n".join(lines) + "\n")
    A.SOURCE = (f"Comparison benchmark, protocol 4, {started[:10]}, one laptop. NCP 2 SDKs of commit "
                f"{schedule['commit'][:7]}, revision 7; iceoryx2 0.10.0. Values: {results.name}/summary.md.")
    figures = results / "figures"
    figures.mkdir(exist_ok=True)
    for mode, theme in A.THEMES.items():
        A.style(theme)
        figure(stats, theme, figures / f"shm_{mode}.svg")
    for name, entry in decisions.items():
        print(f"{name}: {'supported' if entry['supported'] else 'not supported'}")


if __name__ == "__main__":
    main()
