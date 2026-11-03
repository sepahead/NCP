#!/usr/bin/env python3
"""Draw the figures of the multi-agent benchmark from analysis.json.

Usage: figures.py RESULTS_DIR

Writes RESULTS_DIR/figures/{fanout,rounds,mpi}_{light,dark}.svg. Each point is the median of the
block medians of one configuration; its bar spans the smallest and the largest block median.
Needs matplotlib (../comparison/requirements.txt).
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
from matplotlib.ticker import FixedLocator, FuncFormatter, LogLocator, NullFormatter  # noqa: E402

# The themes of ../comparison/analyze.py and ../nest-campaign/figures.py.
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
SESSIONS = (1, 4, 16, 64, 256)
# Mode, label, colour role, marker, filled, line style. Colour, shape, fill, and line together
# identify a mode, so the figure does not depend on colour alone.
MODES = [
    ("all", "call_all (one thread)", "accent", "o", True, "-"),
    ("split", "8 threads, each with call_all", "accent", "^", False, "--"),
    ("pool", "one thread for each session", "other", "s", True, "-"),
    ("sequential", "one call after another", "other", "v", False, ":"),
    ("raw", "plain pipes, no protocol", "floor", "D", True, "-"),
]


def style(theme: dict) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "svg.fonttype": "path",
            "svg.hashsalt": "ncp2-multi-agent",
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


def log_axes(axis, theme: dict, xlabel: str | None, ylabel: str | None) -> None:
    axis.set_xscale("log", base=2)
    axis.xaxis.set_major_locator(FixedLocator(SESSIONS))
    axis.xaxis.set_minor_formatter(NullFormatter())
    axis.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    axis.set_yscale("log")
    axis.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 3.0)))
    axis.yaxis.set_minor_formatter(NullFormatter())
    axis.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    axis.grid(which="major", color=theme["grid"], linewidth=0.6)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)
    if xlabel:
        axis.set_xlabel(xlabel)
    if ylabel:
        axis.set_ylabel(ylabel)


def series(
    axis, theme: dict, points: list[tuple[float, dict]], role: str, marker: str, filled: bool, line: str
) -> None:
    """Points (x, configuration), with their block ranges, joined by a line."""
    points = [(x, entry) for x, entry in points if entry and "statistic_us" in entry]
    if not points:
        return
    xs = [x for x, _ in points]
    ys = [entry["statistic_us"] for _, entry in points]
    colour = theme["muted"] if role == "floor" else theme[role]
    axis.plot(xs, ys, linestyle=line, linewidth=1.6 if role == "accent" and line == "-" else 1.0, color=colour)
    for x, entry in points:
        low, high = entry["range_us"]
        axis.plot([x, x], [low, high], color=colour, linewidth=1.0)
    axis.plot(xs, ys, linestyle="none", **marker_style(theme, role, marker, filled))


def fanout(configs: dict, theme: dict, path: Path) -> None:
    style(theme)
    figure, axes = plt.subplots(2, 2, figsize=(6.8, 5.6), layout="constrained", sharex=True)
    for row, wait_us in enumerate((0, 1000)):
        for column, host in enumerate(("rust", "python")):
            axis = axes[row][column]
            for mode, _, role, marker, filled, line in MODES:
                points = [(n, configs.get(f"F-{host}-{mode}-n{n}-w{wait_us}")) for n in SESSIONS]
                series(axis, theme, points, role, marker, filled, line)
            log_axes(
                axis,
                theme,
                "owners (N)" if row == 1 else None,
                "time of one round (µs, logarithmic)" if column == 0 else None,
            )
            wait = "answer at once" if wait_us == 0 else "wait 1 ms first"
            axis.set_title(f"{host.capitalize()} host, owners {wait}", loc="left")
    handles = [
        Line2D(
            [],
            [],
            linestyle=line,
            color=theme["muted"] if role == "floor" else theme[role],
            label=label,
            **{k: v for k, v in marker_style(theme, role, marker, filled).items() if k != "color"},
        )
        for _, label, role, marker, filled, line in MODES
    ]
    figure.legend(handles=handles, loc="outside lower center", ncol=3, frameon=False, fontsize=7.5)
    save(
        figure,
        path,
        "One host and N owners: the time of one round",
        "Four panels: a Rust host and a Python host, with owners that answer at once or wait 1 ms. Each shows "
        "the median time of one round, one request to each of 1 to 256 owners, for call_all, eight threads "
        "that each use call_all, one thread for each session, one call after another, and plain pipes "
        "without a protocol. Bars span the three block medians.",
    )


def rounds(configs: dict, hypotheses: dict, theme: dict, path: Path) -> None:
    style(theme)
    figure, axis = plt.subplots(figsize=(6.8, 3.4), layout="constrained")
    same = "the same final state in every run" if hypotheses["R2"]["holds"] else "final states as analysed"
    differ = "final states that differ between runs" if hypotheses["R3"]["holds"] else "final states as analysed"
    arms = [
        ("rounds", f"Rounds: {same}", "accent", "o", True, "-"),
        ("arrival", f"Order of arrival: {differ}", "other", "s", False, "--"),
    ]
    for mode, _, role, marker, filled, line in arms:
        series(axis, theme, [(n, configs.get(f"R-{mode}-n{n}")) for n in SESSIONS], role, marker, filled, line)
    log_axes(axis, theme, "agents (N)", "time of one round (µs, logarithmic)")
    axis.set_title("N agents and one Python owner", loc="left")
    handles = [
        Line2D(
            [],
            [],
            linestyle=line,
            color=theme[role],
            label=label,
            **{k: v for k, v in marker_style(theme, role, marker, filled).items() if k != "color"},
        )
        for _, label, role, marker, filled, line in arms
    ]
    figure.legend(handles=handles, loc="outside lower center", ncol=2, frameon=False, fontsize=7.5)
    save(
        figure,
        path,
        "N agents and one owner: rounds and the order of arrival",
        "The median time of one round with 1 to 256 agents that share one Python owner, which applies "
        "their requests in rounds, in a fixed order, or each request when it arrives. Bars span the three "
        "block medians.",
    )


def mpi(configs: dict, theme: dict, path: Path) -> None:
    style(theme)
    figure, axes = plt.subplots(1, 3, figsize=(6.8, 2.8), layout="constrained")
    labels = ["no MPI", "1", "2", "4", "8"]
    for axis, (spikes, name) in zip(
        axes, ((0, "0 spikes"), (1788, "1788 spikes"), (87381, "87381 spikes, 1 MiB")), strict=True
    ):
        for x, ranks in enumerate((0, 1, 2, 4, 8)):
            entry = configs.get(f"M-ranks{ranks}-spikes{spikes}")
            if not entry or "statistic_us" not in entry:
                continue
            role = "floor" if ranks == 0 else "accent"
            colour = theme["muted"] if role == "floor" else theme[role]
            low, high = entry["range_us"]
            axis.plot([x, x], [low, high], color=colour, linewidth=1.0)
            axis.plot([x], [entry["statistic_us"]], linestyle="none", **marker_style(theme, role, "o", True))
        axis.set_xticks(range(5))
        axis.set_xticklabels(labels)
        axis.set_xlim(-0.6, 4.6)
        tops = [
            configs[f"M-ranks{r}-spikes{spikes}"]["range_us"][1]
            for r in (0, 1, 2, 4, 8)
            if f"M-ranks{r}-spikes{spikes}" in configs
        ]
        axis.set_ylim(0, 1.1 * max(tops) if tops else 1)  # room above the highest bar
        axis.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
        axis.grid(axis="y", color=theme["grid"], linewidth=0.6)
        axis.set_axisbelow(True)
        for side in ("top", "right"):
            axis.spines[side].set_visible(False)
        axis.set_title(name, loc="left")
        axis.set_xlabel("MPI ranks")
    axes[0].set_ylabel("time of one call (µs)")
    save(
        figure,
        path,
        "The rank-0 owner of an MPI program: the time of one call",
        "Three panels, for 0, 1788, and 87381 spikes per call. Each shows the median time of one call to "
        "an owner without MPI and to an owner made of 1, 2, 4, or 8 MPI ranks that serves the session "
        "from rank 0. Bars span the three block medians.",
    )


def main() -> None:
    results = Path(sys.argv[1])
    analysis = json.loads((results / "analysis.json").read_text())
    configs, hypotheses = analysis["configurations"], analysis["hypotheses"]
    out = results / "figures"
    out.mkdir(exist_ok=True)
    for name, theme in THEMES.items():
        fanout(configs, theme, out / f"fanout_{name}.svg")
        rounds(configs, hypotheses, theme, out / f"rounds_{name}.svg")
        mpi(configs, theme, out / f"mpi_{name}.svg")
    print(f"figures written to {out}")


if __name__ == "__main__":
    main()
