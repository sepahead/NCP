#!/usr/bin/env python3
"""Draw the figures of protocol 5 of the NEST campaign from its analysis.

Usage: figures.py RESULTS_DIR

Reads RESULTS_DIR/analysis.json, written by analyze4.py, and writes four SVG files to
RESULTS_DIR/figures: overhead_{light,dark}.svg for part D1 at Δ = 1 ms and spikes_{light,dark}.svg
for part D4. Each point is the median over the three blocks of a run's median overhead per
exchange; each bar spans the smallest and the largest block value. The descriptions in the files
are computed from the same numbers. Needs matplotlib (the versions in
../comparison/requirements.txt). The SVG files are deterministic.
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

# The themes of ../comparison/analyze.py, so that the figures of both campaigns match.
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "accent": "#2a78d6",
        "other": "#898781",
        "floor": "#c3c2b7",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#f0efec",
        "ink2": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "accent": "#3987e5",
        "other": "#898781",
        "floor": "#52514e",
    },
}

# Arm, label, colour role, marker, filled. Colour, shape, and fill together identify an arm.
ARMS = [
    ("chunked-pipe", "Raw round trip, no protocol", "floor", "D", True),
    ("ncp2-rs", "NCP 2, Rust host", "accent", "o", True),
    ("ncp2-py", "NCP 2, Python host", "accent", "s", False),
    ("ncp-rs-1.0.1", "NCP 1.0.1, Rust host", "other", "o", True),
    ("ncp-py-1.0.1", "NCP 1.0.1, Python host", "other", "s", False),
]
OFFSETS = [-0.24, -0.12, 0.0, 0.12, 0.24]
X_LIMITS = (5, 3000)


def style(theme: dict) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "svg.fonttype": "path",
            "svg.hashsalt": "ncp2-nest-campaign",
            "figure.facecolor": theme["surface"],
            "axes.facecolor": theme["surface"],
            "savefig.facecolor": theme["surface"],
            "text.color": theme["ink"],
            "axes.labelcolor": theme["ink2"],
            "axes.edgecolor": theme["axis"],
            "xtick.color": theme["muted"],
            "ytick.color": theme["ink2"],
            "axes.titlecolor": theme["ink"],
            "axes.titlesize": 9,
            "axes.titleweight": "bold",
            "axes.linewidth": 0.6,
        }
    )


def marker_style(theme: dict, role: str, marker: str, filled: bool) -> dict:
    colour = theme[role]
    return {
        "marker": marker,
        "markersize": 4.6,
        "markeredgewidth": 1.1,
        "color": colour,
        "markerfacecolor": colour if filled else theme["surface"],
        # The raw round trip is drawn in the light floor colour, so its outline carries the contrast.
        "markeredgecolor": theme["muted"] if role == "floor" else colour,
    }


def save(figure, path: Path, title: str, description: str) -> None:
    figure.savefig(path, format="svg", metadata={"Date": None, "Creator": None})
    plt.close(figure)
    text = path.read_text()
    start = text.index("<svg")
    end = text.index(">", start)
    head = text[start:end].replace("<svg", '<svg role="img" aria-labelledby="title desc"', 1)
    text = (
        text[:start] + head + ">\n" + f'<title id="title">{escape(title)}</title>\n'
        f'<desc id="desc">{escape(description)}</desc>' + text[end + 1 :]
    )
    path.write_text(text)


def rows_of(analysis: dict, part: str, delta: float | None) -> list[dict]:
    rows = [
        entry
        for entry in analysis["step_measures"].values()
        if entry["part"] == part and entry["network"] == "brunel" and (delta is None or entry["delta_ms"] == delta)
    ]
    return sorted(rows, key=lambda e: (e["n"], e["delta_ms"], e["threads"]))


def span(rows: list[dict], arm: str) -> str:
    """The smallest and the largest median of an arm over the rows, in whole µs."""
    values = [entry["overhead_median_us"][arm]["median"] for entry in rows if arm in entry["overhead_median_us"]]
    low, high = (int(value + 0.5) for value in (min(values), max(values)))
    return f"{low:,} to {high:,} µs"


def draw(rows: list[dict], suffix: str, theme: dict, path: Path, title: str, description: str, label) -> None:
    style(theme)
    figure, axis = plt.subplots(figsize=(6.8, 0.55 + 0.42 * len(rows)), layout="constrained")
    for position, entry in enumerate(rows):
        y = len(rows) - 1 - position
        for (arm, _, role, marker, filled), offset in zip(ARMS, OFFSETS):
            value = entry["overhead_median_us"].get(arm + suffix)
            if value is None:
                continue
            axis.errorbar(
                value["median"],
                y + offset,
                xerr=[[value["median"] - value["min"]], [value["max"] - value["median"]]],
                fmt="none",
                ecolor=theme["muted"] if role == "floor" else theme[role],
                elinewidth=1.0,
                capsize=0,
            )
            axis.plot(value["median"], y + offset, linestyle="none", **marker_style(theme, role, marker, filled))
        if any(entry["overhead_median_us"].get(arm + suffix) is None for arm, *_ in ARMS):
            # Placed where the NCP 1.0.1 points of the other rows are, so it overlaps no point.
            axis.text(
                1000,
                y + 0.06,
                "NCP 1.0.1 not run: some steps\nexceed its 64 KiB frame",
                ha="center",
                va="center",
                fontsize=7,
                linespacing=1.15,
                color=theme["ink2"],
            )
    axis.set_yticks(range(len(rows)))
    axis.set_yticklabels([label(entry) for entry in reversed(rows)])
    axis.set_ylim(-0.6, len(rows) - 0.4)
    axis.set_xscale("log")
    axis.set_xlim(*X_LIMITS)
    axis.xaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    axis.xaxis.set_minor_formatter(NullFormatter())
    axis.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    axis.set_xlabel("Time that the coupling adds to one exchange (µs, logarithmic scale)")
    axis.grid(axis="x", which="major", color=theme["grid"], linewidth=0.6)
    axis.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.tick_params(axis="y", length=0)
    axis.set_title(title, loc="left")
    handles = [
        Line2D([], [], linestyle="none", label=name, **marker_style(theme, role, marker, filled))
        for _, name, role, marker, filled in ARMS
    ]
    # Three columns, filled column by column: the raw round trip, then NCP 2, then NCP 1.0.1.
    handles.insert(1, Line2D([], [], linestyle="none", marker="none", label=" "))
    figure.legend(
        handles=handles,
        loc="outside lower center",
        ncol=3,
        frameon=False,
        fontsize=7.5,
        handletextpad=0.3,
        columnspacing=1.2,
    )
    save(figure, path, title, description)


def main() -> None:
    results = Path(sys.argv[1])
    analysis = json.loads((results / "analysis.json").read_text())
    if analysis["protocol"] != "PROTOCOL-5.md":
        sys.exit(f"figures.py draws protocol 5, not {analysis['protocol']}")
    out = results / "figures"
    out.mkdir(exist_ok=True)
    d1 = rows_of(analysis, "D1", 1.0)
    d4 = rows_of(analysis, "D4", None)
    note = "Each point is the median of three blocks; its bar spans the block values."
    d1_text = (
        "Brunel network with 1,000 and 10,000 neurons on 1, 4, and 8 NEST threads, one exchange after every "
        f"1 ms of simulated time. NCP 2 adds {span(d1, 'ncp2-rs')} with a Rust host and {span(d1, 'ncp2-py')} "
        f"with a Python host. NCP 1.0.1 adds {span(d1, 'ncp-rs-1.0.1')} and {span(d1, 'ncp-py-1.0.1')}. "
        f"A raw round trip without a protocol takes {span(d1, 'chunked-pipe')}. {note}"
    )
    d4_text = (
        "Brunel network on 4 NEST threads; each exchange returns the spikes of its step. "
        f"NCP 2 adds {span(d4, 'ncp2-rs-spikes')} with a Rust host and {span(d4, 'ncp2-py-spikes')} with a "
        f"Python host. NCP 1.0.1 adds {span(d4, 'ncp-rs-1.0.1-spikes')} and {span(d4, 'ncp-py-1.0.1-spikes')}; "
        "with 10,000 neurons at 5 ms it was not run, because some steps exceed its 64 KiB frame. "
        f"A raw round trip without a protocol takes {span(d4, 'chunked-pipe-spikes')}. {note}"
    )
    for name, theme in THEMES.items():
        draw(
            d1,
            "",
            theme,
            out / f"overhead_{name}.svg",
            "Time that the coupling adds to each 1 ms step of a NEST network",
            d1_text,
            lambda e: f"{e['n']:,} neurons, {e['threads']} thread{'s' if e['threads'] > 1 else ''}",
        )
        draw(
            d4,
            "-spikes",
            theme,
            out / f"spikes_{name}.svg",
            "Time that the coupling adds when each step returns its spikes",
            d4_text,
            lambda e: f"{e['n']:,} neurons, {e['delta_ms']:g} ms steps",
        )
    print(d1_text)
    print(d4_text)


if __name__ == "__main__":
    main()
