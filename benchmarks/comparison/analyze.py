#!/usr/bin/env python3
"""Analyze the comparison benchmark (see PROTOCOL.md, section 9, and PROTOCOL-2.md).

Usage: analyze.py RESULTS_DIR [--figures DIR]

Reads RESULTS_DIR/runs.jsonl, RESULTS_DIR/schedule.json, and RESULTS_DIR/validity.json. Writes
RESULTS_DIR/analysis.json (statistics and hypothesis results), RESULTS_DIR/summary.md (the same
values as tables), and four figures, each in a light and a dark version, into DIR (default
RESULTS_DIR/figures). For protocol 2 it adds R1 to R3, the arms with the integrity check of NCP 2,
and a fifth figure. The output is deterministic: the same input gives the same bytes.
Needs numpy and matplotlib (requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

SPIKES = (0, 127, 1788, 87381)
NCP1_SPIKES = (0, 127, 1788)
PAIRS = (("rust", "rust"), ("rust", "python"), ("python", "rust"), ("python", "python"))
SPIKE_LABEL = {0: "N = 0", 127: "N = 127", 1788: "N = 1788", 87381: "N = 87381 (1 MiB)"}
LANGUAGE = {"rust": "Rust", "python": "Python"}

# Arms in drawing order (top to bottom) for each language, with their labels.
TIERS = {
    "rust": [
        ("ncp2-rust-rust-pipe", "NCP 2, pipe"),
        ("ncp2-rust-rust-pipe-nocheck", "NCP 2, pipe, no digest check"),
        ("ncp2-rust-rust-unix", "NCP 2, Unix socket"),
        ("ncp2-rust-rust-tcp", "NCP 2, TCP"),
        ("ncp1-rust-rust-pipe", "NCP 1.0.1, pipe"),
        ("grpc-rust-tcp", "gRPC (tonic), TCP"),
        ("zenoh-rust-tcp", "Zenoh, TCP"),
        ("raw-rust-pipe", "Raw pipe, no protocol"),
    ],
    "python": [
        ("ncp2-python-python-pipe", "NCP 2, pipe"),
        ("ncp2-python-python-pipe-nocheck", "NCP 2, pipe, no digest check"),
        ("ncp2-python-python-unix", "NCP 2, Unix socket"),
        ("ncp2-python-python-tcp", "NCP 2, TCP"),
        ("ncp1-python-python-pipe", "NCP 1.0.1, pipe"),
        ("grpc-python-unix", "gRPC (grpcio), Unix socket"),
        ("grpc-python-tcp", "gRPC (grpcio), TCP"),
        ("zmq-python-ipc", "ZeroMQ, ipc"),
        ("zmq-python-tcp", "ZeroMQ, TCP"),
        ("http-python-tcp", "HTTP/1.1, TCP"),
        ("zenoh-python-tcp", "Zenoh, TCP"),
        ("raw-python-pipe", "Raw pipe, no protocol"),
    ],
}

# Protocol 2: the NCP 2 arms against the other arms with the same integrity check (SHA-256 at both ends).
INTEGRITY_TIERS = {
    "rust": [
        ("ncp2-rust-rust-pipe", "NCP 2, pipe"),
        ("ncp2-rust-rust-unix", "NCP 2, Unix socket"),
        ("ncp2-rust-rust-tcp", "NCP 2, TCP"),
        ("grpc-rust-unix-sha256", "gRPC (tonic), Unix socket + SHA-256"),
        ("grpc-rust-tcp-sha256", "gRPC (tonic), TCP + SHA-256"),
        ("zenoh-rust-tcp-sha256", "Zenoh, TCP + SHA-256"),
        ("raw-rust-pipe-sha256", "Raw pipe + SHA-256"),
    ],
    "python": [
        ("ncp2-python-python-pipe", "NCP 2, pipe"),
        ("ncp2-python-python-unix", "NCP 2, Unix socket"),
        ("ncp2-python-python-tcp", "NCP 2, TCP"),
        ("grpc-python-unix-sha256", "gRPC (grpcio), Unix socket + SHA-256"),
        ("grpc-python-tcp-sha256", "gRPC (grpcio), TCP + SHA-256"),
        ("zmq-python-ipc-sha256", "ZeroMQ, ipc + SHA-256"),
        ("zmq-python-tcp-sha256", "ZeroMQ, TCP + SHA-256"),
        ("http-python-tcp-sha256", "HTTP/1.1, TCP + SHA-256"),
        ("zenoh-python-tcp-sha256", "Zenoh, TCP + SHA-256"),
        ("raw-python-pipe-sha256", "Raw pipe + SHA-256"),
    ],
}
# Protocol 2: arms that protocol 1 did not have, for the tables.
NEW_ARMS = {
    "rust": [("grpc-rust-unix", "gRPC (tonic), Unix socket")] + INTEGRITY_TIERS["rust"][3:],
    "python": INTEGRITY_TIERS["python"][3:],
}

# Colors: the validated reference palette of the dataviz method (accent slots 1 and 2, checked for
# color-vision deficiency in both modes), and its chart chrome.
THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "ink2": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "accent": "#2a78d6",
        "accent2": "#eb6834",
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
        "accent2": "#d95926",
        "other": "#898781",
        "floor": "#52514e",
    },
}


# --------------------------------------------------------------------------- statistics


def load(results: Path) -> tuple[list[dict], dict, dict]:
    rows = [json.loads(line) for line in (results / "runs.jsonl").read_text().splitlines() if line.strip()]
    schedule = json.loads((results / "schedule.json").read_text())
    validity = json.loads((results / "validity.json").read_text())
    return rows, schedule, validity


def final_rows(rows: list[dict]) -> dict[tuple[int, str], dict]:
    """The row that counts for each (block, configuration): a success, else the last failure. In
    protocol 2, a later attempt replaces a disturbed success (the last attempt counts)."""
    final: dict[tuple[int, str], dict] = {}
    for row in rows:
        key = (row["block"], row["config"])
        earlier = final.get(key)
        if earlier is None or earlier["returncode"] != 0 or (row["returncode"] == 0 and earlier.get("disturbed")):
            final[key] = row  # the first success stays; a later repeat replaces a failure or a disturbed run
    return final


def statistics_by_config(final: dict[tuple[int, str], dict], blocks: int) -> dict[str, dict]:
    by_config: dict[str, dict] = {}
    for (block, config), row in sorted(final.items()):
        entry = by_config.setdefault(
            config,
            {"arm": row["arm"], "spikes": row["spikes"], "family": row["family"], "blocks": {}, "failed_blocks": []},
        )
        if row["returncode"] == 0 and not row.get("disturbed"):
            entry["blocks"][block] = {k: row[k] for k in ("median_us", "p95_us", "p99_us") if k in row}
        elif row["returncode"] == 0:
            entry.setdefault("disturbed_blocks", []).append(block)  # still disturbed after the last attempt
        else:
            entry["failed_blocks"].append(block)
    for entry in by_config.values():
        medians = [b["median_us"] for b in entry["blocks"].values()]
        entry["complete"] = len(medians) == blocks
        if medians:
            entry["statistic_us"] = statistics.median(medians)
            entry["range_us"] = [min(medians), max(medians)]
            for key in ("p95_us", "p99_us"):
                values = [b[key] for b in entry["blocks"].values() if key in b]
                if values:
                    entry[key.replace("_us", "_statistic_us")] = statistics.median(values)
    return by_config


def block_medians(stats: dict, config: str) -> dict[int, float]:
    return {block: b["median_us"] for block, b in stats.get(config, {}).get("blocks", {}).items()}


def lower_in_every_block(stats: dict, faster: str, slower: str, blocks: int) -> dict:
    a, b = block_medians(stats, faster), block_medians(stats, slower)
    shared = sorted(set(a) & set(b))
    holds = len(shared) == blocks and all(a[k] < b[k] for k in shared)
    return {
        "faster": faster,
        "slower": slower,
        "holds": holds,
        "blocks_compared": len(shared),
        "ratio": round(stats[slower]["statistic_us"] / stats[faster]["statistic_us"], 3) if a and b else None,
    }


def hypotheses(stats: dict, blocks: int) -> dict[str, dict]:
    stat = lambda config: stats.get(config, {}).get("statistic_us")  # noqa: E731
    result: dict[str, dict] = {}
    h1 = [
        lower_in_every_block(stats, f"ncp2-{c}-{o}-pipe-n{n}", f"ncp1-{c}-{o}-pipe-n{n}", blocks)
        for c, o in PAIRS
        for n in NCP1_SPIKES
    ]
    result["H1"] = {"comparisons": h1, "supported": all(c["holds"] for c in h1)}
    checks = [
        ("ncp2-rust-rust-pipe-n0", 15.0),
        ("ncp2-python-python-pipe-n0", 150.0),
        ("ncp2-python-python-pipe-n127", 150.0),
    ]
    h2 = [
        {
            "config": config,
            "statistic_us": stat(config),
            "limit_us": limit,
            "holds": stat(config) is not None and stat(config) <= limit,
        }
        for config, limit in checks
    ]
    result["H2"] = {"checks": h2, "supported": all(c["holds"] for c in h2)}
    added = (
        None
        if stat("ncp2-rust-rust-pipe-n0") is None or stat("raw-rust-pipe-n0") is None
        else (stat("ncp2-rust-rust-pipe-n0") - stat("raw-rust-pipe-n0"))
    )
    result["H3"] = {"added_us": added, "limit_us": 10.0, "supported": added is not None and added <= 10.0}
    h4 = [
        lower_in_every_block(stats, f"ncp2-rust-rust-pipe-n{n}", f"{other}-n{n}", blocks)
        for n in NCP1_SPIKES
        for other in ("grpc-rust-tcp", "zenoh-rust-tcp")
    ]
    h4 += [
        lower_in_every_block(stats, f"ncp2-rust-rust-tcp-n{n}", f"{other}-n{n}", blocks)
        for n in (0, 127)
        for other in ("grpc-rust-tcp", "zenoh-rust-tcp")
    ]
    result["H4"] = {"comparisons": h4, "supported": all(c["holds"] for c in h4)}
    h5 = [
        lower_in_every_block(stats, f"ncp2-python-python-pipe-n{n}", f"{other}-n{n}", blocks)
        for n in NCP1_SPIKES
        for other in ("grpc-python-unix", "grpc-python-tcp", "http-python-tcp")
    ]
    result["H5"] = {"comparisons": h5, "supported": all(c["holds"] for c in h5)}
    return result


def hypotheses_2(stats: dict, blocks: int) -> dict[str, dict]:
    """PROTOCOL-2.md: R1 repeats H1 to H5; R2 and R3 compare NCP 2 with the other arms that make the
    same integrity check, over the same kind of connection."""
    result = hypotheses(stats, blocks)
    result["R1"] = {
        "replicated": [name for name in ("H1", "H2", "H3", "H4", "H5") if result[name]["supported"]],
        "supported": all(result[name]["supported"] for name in ("H1", "H2", "H3", "H4", "H5")),
    }
    r2 = [
        lower_in_every_block(stats, f"ncp2-rust-rust-{kind}-n{n}", f"{other}-n{n}", blocks)
        for n in NCP1_SPIKES
        for kind, other in (("unix", "grpc-rust-unix-sha256"), ("tcp", "grpc-rust-tcp-sha256"), ("tcp", "zenoh-rust-tcp-sha256"))
    ]
    result["R2"] = {"comparisons": r2, "supported": all(c["holds"] for c in r2)}
    r3 = [
        lower_in_every_block(stats, f"ncp2-python-python-{kind}-n{n}", f"grpc-python-{kind}-sha256-n{n}", blocks)
        for n in NCP1_SPIKES
        for kind in ("unix", "tcp")
    ]
    result["R3"] = {"comparisons": r3, "supported": all(c["holds"] for c in r3)}
    return result


def integrity_parts(stats: dict) -> list[dict]:
    """Protocol 2, exploratory: over pipes, the floor, the cost of the integrity check alone (the raw
    pipe with SHA-256 minus the raw pipe), and the rest of NCP 2 (NCP 2 minus the raw pipe with
    SHA-256), which can be negative."""
    parts = []
    for language in ("rust", "python"):
        for n in SPIKES:
            names = (f"raw-{language}-pipe-n{n}", f"raw-{language}-pipe-sha256-n{n}", f"ncp2-{language}-{language}-pipe-n{n}")
            if any("statistic_us" not in stats.get(name, {}) for name in names):
                continue
            floor, sealed, ncp2 = (stats[name]["statistic_us"] for name in names)
            parts.append(
                {
                    "language": language,
                    "spikes": n,
                    "floor_us": floor,
                    "check_us": sealed - floor,
                    "rest_of_ncp2_us": ncp2 - sealed,
                    "ncp2_us": ncp2,
                }
            )
    return parts


def decomposition(stats: dict) -> list[dict]:
    """Where the time of a pipe call goes, for each language and N (figure 3)."""
    parts = []

    def spread(config: str) -> float:
        low, high = stats[config]["range_us"]
        return high - low

    for language in ("rust", "python"):
        for n in SPIKES:
            names = (
                f"raw-{language}-pipe-n{n}",
                f"ncp2-{language}-{language}-pipe-nocheck-n{n}",
                f"ncp2-{language}-{language}-pipe-n{n}",
            )
            if any("statistic_us" not in stats.get(name, {}) for name in names):
                continue
            floor, nocheck, full = (stats[name]["statistic_us"] for name in names)
            protocol, digest = nocheck - floor, full - nocheck
            # A part smaller than the spread of the block medians of its two arms is within the
            # variation between runs, not a measured cost. This flag is descriptive; PROTOCOL.md
            # does not define it.
            within = {
                "protocol": abs(protocol) < max(spread(names[0]), spread(names[1])),
                "digest": abs(digest) < max(spread(names[1]), spread(names[2])),
            }
            parts.append(
                {
                    "language": language,
                    "spikes": n,
                    "floor_us": floor,
                    "protocol_us": max(protocol, 0.0),
                    "digest_us": max(digest, 0.0),
                    "total_us": full,
                    "below_zero": [name for name, value in (("protocol", protocol), ("digest", digest)) if value < 0],
                    "within_variation": sorted(name for name, flag in within.items() if flag),
                }
            )
    return parts


# --------------------------------------------------------------------------- figures


def style(theme: dict) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.5,
            "svg.fonttype": "path",
            "svg.hashsalt": "ncp2-comparison",
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


def color_of(arm: str, theme: dict) -> str:
    if arm.startswith("ncp2-"):
        return theme["accent"]
    if arm.startswith("raw-"):
        return theme["floor"]
    return theme["other"]


def log_axis(axis, theme: dict) -> None:
    axis.set_xscale("log")
    axis.xaxis.set_minor_formatter(NullFormatter())
    axis.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    axis.grid(axis="x", which="major", color=theme["grid"], linewidth=0.6)
    axis.set_axisbelow(True)
    for side in ("top", "right", "left"):
        axis.spines[side].set_visible(False)
    axis.tick_params(axis="y", length=0)


def log_ticks(axis) -> None:
    """Label 1, 2, and 5 times each power of ten on short axes, 1 and 3 times on medium ones."""
    low, high = axis.get_xlim()
    subs = (1.0, 2.0, 5.0) if high / low < 16 else (1.0, 3.0) if high / low < 1000 else (1.0,)
    axis.xaxis.set_major_locator(LogLocator(base=10, subs=subs))


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


CALLS_TEXT = (
    "Time of one call: a small request and N spikes back",
    "Dot: median of three block medians. Line: the smallest to the largest block median. "
    "NCP 2 in blue; other systems in gray; ring: the raw pipe, the floor.",
    "Time of one call for NCP 2 and other systems",
    "Small multiples: rows for Rust and Python, columns for N of 0, 127, 1788, and 87381 spikes. Each panel "
    "shows a dot for the call time of each arm on a log scale, with a line for the range of the block medians. "
    "Values are in summary.md.",
)
INTEGRITY_TEXT = (
    "Time of one call when every system checks integrity as NCP 2 does",
    "Gray arms add a SHA-256 digest to each message, which the receiver checks, as NCP 2 does. "
    "Dot: median of three block medians; line: their range. Ring: raw pipe with the same check.",
    "Time of one call with the same integrity check",
    "Small multiples: rows for Rust and Python, columns for N of 0, 127, 1788, and 87381 spikes. NCP 2 over a "
    "pipe, a Unix socket, and TCP in blue; gRPC, ZeroMQ, HTTP/1.1, Zenoh, and the raw pipe, each with a SHA-256 "
    "digest of every message checked by the receiver, in gray. Values are in summary.md.",
)


def figure_calls(stats: dict, theme: dict, path: Path, tiers: dict = TIERS, text: tuple = CALLS_TEXT) -> None:
    rows = {language: len(arms) for language, arms in tiers.items()}
    figure, axes = plt.subplots(
        2, 4, figsize=(11.5, 7.4), gridspec_kw={"height_ratios": [rows["rust"], rows["python"]]}, sharex="col"
    )
    for column, n in enumerate(SPIKES):
        for row, language in enumerate(("rust", "python")):
            axis = axes[row][column]
            arms = tiers[language]
            for position, (arm, _) in enumerate(arms):
                entry = stats.get(f"{arm}-n{n}")
                y = len(arms) - 1 - position
                if entry is None or "statistic_us" not in entry:
                    axis.text(
                        1.0,
                        y,
                        "not measured",
                        transform=axis.get_yaxis_transform(),
                        ha="right",
                        va="center",
                        fontsize=7,
                        color=theme["muted"],
                    )
                    continue
                low, high = entry["range_us"]
                value = entry["statistic_us"]
                color = color_of(arm, theme)
                axis.plot([low, high], [y, y], color=color, linewidth=1.6, solid_capstyle="round", zorder=2)
                if arm.startswith("raw-"):  # the floor: a ring, so that shape marks it as well as color
                    axis.scatter(
                        [value],
                        [y],
                        s=34,
                        facecolors=theme["surface"],
                        edgecolors=theme["muted"],
                        linewidths=1.4,
                        zorder=3,
                    )
                else:
                    axis.scatter([value], [y], s=34, color=color, zorder=3, linewidths=1.5, edgecolors=theme["surface"])
                if arm.endswith(f"-{language}-pipe") and arm.startswith("ncp2-"):
                    axis.text(high * 1.3, y, f"{value:.3g} µs", va="center", fontsize=7.5, color=theme["ink"])
            axis.set_yticks(range(len(arms)))
            axis.set_yticklabels([label for _, label in reversed(arms)] if column == 0 else [])
            axis.set_ylim(-0.6, len(arms) - 0.4)
            log_axis(axis, theme)
            axis.grid(axis="y", color=theme["grid"], linewidth=0.6)
            if row == 0:
                axis.set_title(SPIKE_LABEL[n], loc="left")
            if row == 1:
                axis.set_xlabel("Call time, µs (log scale)")
        axes[0][0].set_ylabel("Rust client and server", fontsize=9, color=theme["ink"], labelpad=8)
        axes[1][0].set_ylabel("Python client and server", fontsize=9, color=theme["ink"], labelpad=8)
    for column in range(4):
        low = min(axes[r][column].get_xlim()[0] for r in range(2))
        high = max(axes[r][column].get_xlim()[1] for r in range(2))
        axes[0][column].set_xlim(low / 1.2, high * 2.2)
        log_ticks(axes[0][column])
    figure.suptitle(
        text[0],
        x=0.01,
        ha="left",
        fontsize=11,
        fontweight="bold",
        color=theme["ink"],
    )
    figure.text(
        0.01,
        0.945,
        text[1],
        fontsize=8,
        color=theme["ink2"],
    )
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    save(figure, path, text[2], text[3])


def figure_versions(stats: dict, theme: dict, path: Path) -> None:
    rows = []  # (y, label, NCP 1.0.1, NCP 2); a gap of one row separates the language pairs
    y = 0.0
    for c, o in reversed(PAIRS):
        for n in reversed(NCP1_SPIKES):
            a = stats.get(f"ncp1-{c}-{o}-pipe-n{n}", {}).get("statistic_us")
            b = stats.get(f"ncp2-{c}-{o}-pipe-n{n}", {}).get("statistic_us")
            if a is not None and b is not None:
                rows.append((y, f"{LANGUAGE[c]} client, {LANGUAGE[o]} owner, N = {n}", a, b))
                y += 1
        y += 0.6
    figure, axis = plt.subplots(figsize=(8.6, 0.36 * y + 1.5))
    for y, _, a, b in rows:
        axis.plot([b, a], [y, y], color=theme["axis"], linewidth=1.6, solid_capstyle="round", zorder=1)
        axis.scatter([a], [y], s=34, color=theme["other"], zorder=2, linewidths=0)
        axis.scatter([b], [y], s=34, color=theme["accent"], zorder=3, linewidths=0)
        axis.text(a * 1.25, y, f"{a / b:.3g}× faster", va="center", fontsize=7.5, color=theme["ink"])
    axis.set_yticks([row[0] for row in rows])
    axis.set_yticklabels([row[1] for row in rows])
    log_axis(axis, theme)
    axis.set_xlim(min(row[3] for row in rows) / 1.6, max(row[2] for row in rows) * 4.5)
    log_ticks(axis)
    axis.set_xlabel("Call time, µs (log scale)")
    axis.scatter([], [], s=34, color=theme["accent"], label="NCP 2")
    axis.scatter([], [], s=34, color=theme["other"], label="NCP 1.0.1")
    axis.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, frameon=False, fontsize=8)
    axis.set_title("NCP 2 against NCP 1.0.1, over pipes", loc="left", fontsize=11)
    figure.tight_layout()
    save(
        figure,
        path,
        "NCP 2 against NCP 1.0.1",
        "Dumbbell chart: for each language pair and N, the call time of NCP 1.0.1 and of NCP 2 on a log scale, joined "
        "by a line, with the ratio. Values are in summary.md.",
    )


def figure_decomposition(parts: list[dict], theme: dict, path: Path) -> None:
    figure, axes = plt.subplots(1, 4, figsize=(11.5, 2.5))
    for column, n in enumerate(SPIKES):
        axis = axes[column]
        selected = [p for p in parts if p["spikes"] == n]
        for index, part in enumerate(selected):
            y = len(selected) - 1 - index
            left = 0.0
            for key, color in (
                ("floor_us", theme["floor"]),
                ("protocol_us", theme["accent"]),
                ("digest_us", theme["accent2"]),
            ):
                faint = key.removesuffix("_us") in part["within_variation"]
                axis.barh(y, part[key], left=left, height=0.55, color=color, linewidth=0, alpha=0.35 if faint else 1.0)
                left += part[key]
            axis.text(left * 1.03, y, f"{part['total_us']:.3g} µs", va="center", fontsize=7.5, color=theme["ink"])
        axis.set_yticks(range(len(selected)))
        axis.set_yticklabels([LANGUAGE[p["language"]] for p in reversed(selected)] if column == 0 else [])
        axis.set_xlim(0, max((p["total_us"] for p in selected), default=1) * 1.35)
        axis.grid(axis="x", color=theme["grid"], linewidth=0.6)
        axis.set_axisbelow(True)
        for side in ("top", "right", "left"):
            axis.spines[side].set_visible(False)
        axis.tick_params(axis="y", length=0)
        axis.set_title(SPIKE_LABEL[n], loc="left")
        axis.set_xlabel("µs")
    handles = [plt.Rectangle((0, 0), 1, 1, color=theme[key]) for key in ("floor", "accent", "accent2")]
    figure.legend(
        handles,
        ["Raw pipe (floor)", "Rest of NCP 2", "Digest comparison"],
        loc="upper right",
        ncol=3,
        frameon=False,
        fontsize=8,
    )
    figure.suptitle(
        "Where the time of an NCP 2 call goes, over pipes",
        x=0.01,
        ha="left",
        fontsize=11,
        fontweight="bold",
        color=theme["ink"],
    )
    figure.text(
        0.01,
        0.02,
        "Light parts are smaller than the spread of the block medians of their arms: "
        "variation between runs, not a measured cost.",
        fontsize=7.5,
        color=theme["ink2"],
    )
    figure.tight_layout(rect=(0, 0.06, 1, 0.86))
    save(
        figure,
        path,
        "Where the time of an NCP 2 call goes",
        "Stacked horizontal bars for Rust and Python and each N: the raw pipe floor, the rest of NCP 2, and the "
        "digest comparison, each panel on its own linear scale. Parts smaller than the spread of their block "
        "medians are drawn light. Values are in summary.md.",
    )


def figure_tails(stats: dict, theme: dict, path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), gridspec_kw={"width_ratios": [1, 1]})
    markers = (
        ("statistic_us", "o", "Median"),
        ("p95_statistic_us", "^", "95th percentile"),
        ("p99_statistic_us", "s", "99th percentile"),
    )
    for axis, language in zip(axes, ("rust", "python"), strict=True):
        arms = TIERS[language]
        for position, (arm, _) in enumerate(arms):
            entry = stats.get(f"{arm}-n127", {})
            y = len(arms) - 1 - position
            values = [entry.get(key) for key, _, _ in markers]
            if None in values:
                continue
            color = color_of(arm, theme)
            axis.plot([values[0], values[2]], [y, y], color=theme["axis"], linewidth=1.2, zorder=1)
            for value, (_, marker, _) in zip(values, markers, strict=True):
                axis.scatter([value], [y], marker=marker, s=30, color=color, zorder=2, linewidths=0)
        axis.set_yticks(range(len(arms)))
        axis.set_yticklabels([label for _, label in reversed(arms)])
        log_axis(axis, theme)
        log_ticks(axis)
        axis.grid(axis="y", color=theme["grid"], linewidth=0.6)
        axis.set_xlabel("Call time, µs (log scale)")
        axis.set_title(f"{LANGUAGE[language]} client and server", loc="left")
    handles = [
        plt.Line2D([], [], marker=marker, linestyle="none", color=theme["ink2"], markersize=6)
        for _, marker, _ in markers
    ]
    figure.legend(handles, [label for _, _, label in markers], loc="upper right", ncol=3, frameon=False, fontsize=8)
    figure.suptitle(
        "Tails at N = 127: median, 95th, and 99th percentiles",
        x=0.01,
        ha="left",
        fontsize=11,
        fontweight="bold",
        color=theme["ink"],
    )
    figure.tight_layout(rect=(0, 0, 1, 0.9))
    save(
        figure,
        path,
        "Tail call times at N = 127",
        "For each arm, the median, 95th, and 99th percentile call times on a log scale, as circle, triangle, and "
        "square. NCP 2 in blue. Values are in summary.md.",
    )


# --------------------------------------------------------------------------- tables


def summary(stats: dict, result: dict, parts: list[dict], context: dict, integrity: list[dict] | None = None) -> str:
    two = integrity is not None
    lines = [
        "# Comparison benchmark: results" + (" of protocol 2" if two else ""),
        "",
        f"Protocol SHA-256 `{context['protocol_sha256']}`; {context['runs']} runs in {context['blocks']} blocks, "
        f"{context['started']} to {context['finished']} UTC; failed runs that counted: {context['failed']}.",
        f"One-minute load average before the runs: {context['load_min']} to {context['load_max']}. "
        f"Power source: {', '.join(context['power'])}.",
    ]
    if two:
        lines += [
            f"Disturbed attempts: {context['disturbed_attempts']}; runs still disturbed after the last attempt: "
            f"{len(context['still_disturbed'])}{' (' + ', '.join(context['still_disturbed']) + ')' if context['still_disturbed'] else ''}. "
            f"Clock of a core before each run: {context['clock_before'][0]} to {context['clock_before'][1]} GHz; "
            f"after it: {context['clock_after'][0]} to {context['clock_after'][1]} GHz. "
            f"Waiting for the conditions: {context['waited_minutes']} minutes in all.",
        ]
    lines += [
        "",
        "Statistic: the median of three block medians, in µs. Range: the smallest and largest block median.",
        "",
    ]
    tables = [(f"{LANGUAGE[language]} client and server", TIERS[language], language) for language in ("rust", "python")]
    if two:
        tables += [
            (f"{LANGUAGE[language]}: arms of protocol 2", NEW_ARMS[language], language) for language in ("rust", "python")
        ]
    for heading, arms, language in tables:
        lines += [
            f"## {heading}",
            "",
            "| Arm | " + " | ".join(SPIKE_LABEL[n] for n in SPIKES) + " |",
            "| --- |" + " ---: |" * len(SPIKES),
        ]
        for arm, label in arms:
            cells = []
            for n in SPIKES:
                entry = stats.get(f"{arm}-n{n}")
                if entry is None or "statistic_us" not in entry:
                    cells.append("not measured")
                else:
                    low, high = entry["range_us"]
                    cells.append(f"{entry['statistic_us']:.1f} ({low:.1f}–{high:.1f})")
            lines.append(f"| {label} | " + " | ".join(cells) + " |")
        lines.append("")
    lines += [
        "## Mixed languages over pipes",
        "",
        "| Client, owner | N | NCP 2 | NCP 1.0.1 | Ratio |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for c, o in PAIRS:
        for n in NCP1_SPIKES:
            a = stats.get(f"ncp2-{c}-{o}-pipe-n{n}", {}).get("statistic_us")
            b = stats.get(f"ncp1-{c}-{o}-pipe-n{n}", {}).get("statistic_us")
            if a is not None and b is not None:
                lines.append(f"| {LANGUAGE[c]}, {LANGUAGE[o]} | {n} | {a:.1f} | {b:.1f} | {b / a:.3g} |")
    lines += ["", "## Hypotheses", "", "| # | Supported | Detail |", "| --- | --- | --- |"]
    for name, entry in result.items():
        if "comparisons" in entry:
            failed = [f"{c['faster']} not below {c['slower']}" for c in entry["comparisons"] if not c["holds"]]
            detail = f"{len(entry['comparisons']) - len(failed)} of {len(entry['comparisons'])} comparisons hold"
            detail += ("; " + "; ".join(failed)) if failed else ""
        elif "replicated" in entry:
            detail = f"{len(entry['replicated'])} of H1 to H5 hold again" + (
                f": {', '.join(entry['replicated'])}" if entry["replicated"] else ""
            )
        elif "checks" in entry:
            detail = "; ".join(
                f"{c['config']}: {c['statistic_us']:.1f} µs (limit {c['limit_us']:g})"
                for c in entry["checks"]
                if c["statistic_us"] is not None
            )
        else:
            detail = f"{entry['added_us']:.1f} µs added (limit {entry['limit_us']:g})"
        lines.append(f"| {name} | {'yes' if entry['supported'] else 'no'} | {detail} |")
    lines += [
        "",
        "## Where the time of an NCP 2 call goes, over pipes",
        "",
        "| Language | N | Floor | Rest of NCP 2 | Digest comparison | Total |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for part in parts:
        note = f" (below zero: {', '.join(part['below_zero'])}, drawn as zero)" if part["below_zero"] else ""
        mark = {name: "†" if name in part["within_variation"] else "" for name in ("protocol", "digest")}
        lines.append(
            f"| {LANGUAGE[part['language']]} | {part['spikes']} | {part['floor_us']:.1f} | "
            f"{part['protocol_us']:.1f}{mark['protocol']} | {part['digest_us']:.1f}{mark['digest']}{note} | "
            f"{part['total_us']:.1f} |"
        )
    lines += [
        "",
        "† Smaller than the spread of the block medians of the two arms that give the part: variation between runs, "
        "not a measured cost.",
    ]
    if two:
        lines += [
            "",
            "## The integrity check alone, over pipes (exploratory)",
            "",
            "Check: the raw pipe with SHA-256 at both ends minus the raw pipe. Rest of NCP 2: NCP 2 minus the raw pipe "
            "with SHA-256; below zero when NCP 2 is faster than the raw pipe with the same check.",
            "",
            "| Language | N | Raw pipe | Check | Rest of NCP 2 | NCP 2 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for part in integrity:
            lines.append(
                f"| {LANGUAGE[part['language']]} | {part['spikes']} | {part['floor_us']:.1f} | {part['check_us']:.1f} | "
                f"{part['rest_of_ncp2_us']:.1f} | {part['ncp2_us']:.1f} |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--figures", type=Path)
    args = parser.parse_args()
    rows, schedule, validity = load(args.results)
    two = schedule.get("protocol", "PROTOCOL.md") == "PROTOCOL-2.md"
    final = final_rows(rows)
    stats = statistics_by_config(final, schedule["blocks"])
    result = (hypotheses_2 if two else hypotheses)(stats, schedule["blocks"])
    parts = decomposition(stats)
    integrity = integrity_parts(stats) if two else None
    counted = list(final.values())
    context = {
        "protocol_sha256": schedule["protocol_sha256"],
        "runs": len(rows),
        "blocks": schedule["blocks"],
        "failed": sum(1 for row in counted if row["returncode"] != 0),
        "started": min(row["started_utc"] for row in rows),
        "finished": max(row["finished_utc"] for row in rows),
        "load_min": min(row["load1_before"] for row in rows),
        "load_max": max(row["load1_before"] for row in rows),
        "power": sorted({row.get("power", "not recorded") for row in rows}),
    }
    if two:
        measured = [row for row in rows if row.get("before") and row.get("after")]
        context.update(
            {
                "protocol": schedule["protocol"],
                "disturbed_attempts": sum(1 for row in rows if row.get("disturbed")),
                "still_disturbed": sorted(f"{config} block {block}" for (block, config), row in final.items() if row.get("disturbed")),
                "clock_before": [min(r["before"]["clock_ghz"] for r in measured), max(r["before"]["clock_ghz"] for r in measured)],
                "clock_after": [min(r["after"]["clock_ghz"] for r in measured), max(r["after"]["clock_ghz"] for r in measured)],
                "waited_minutes": round(sum(r.get("waited_s", 0.0) for r in rows) / 60),
            }
        )
    analysis = {
        "context": context,
        "environment": validity.get("environment", {}),
        "configurations": stats,
        "hypotheses": result,
        "decomposition": parts,
    }
    if two:
        analysis["integrity"] = integrity
    (args.results / "analysis.json").write_text(json.dumps(analysis, indent=1, sort_keys=True) + "\n")
    (args.results / "summary.md").write_text(summary(stats, result, parts, context, integrity))
    figures = args.figures or args.results / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    for mode, theme in THEMES.items():
        style(theme)
        figure_calls(stats, theme, figures / f"calls_{mode}.svg")
        figure_versions(stats, theme, figures / f"versions_{mode}.svg")
        figure_decomposition(parts, theme, figures / f"decomposition_{mode}.svg")
        figure_tails(stats, theme, figures / f"tails_{mode}.svg")
        if two:
            figure_calls(stats, theme, figures / f"integrity_{mode}.svg", INTEGRITY_TIERS, INTEGRITY_TEXT)
    for name, entry in result.items():
        print(f"{name}: {'supported' if entry['supported'] else 'not supported'}")


if __name__ == "__main__":
    main()
