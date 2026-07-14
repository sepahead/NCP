#!/usr/bin/env python3
"""Historical NCP developer-performance figures (non-normative).

Emits four SVGs into ``docs/plots/`` (created if missing):

    docs/plots/overlap_light.svg   docs/plots/overlap_dark.svg
    docs/plots/realtime_light.svg  docs/plots/realtime_dark.svg

Generate with the exact dependencies in ``requirements-plot.txt``::

    python3 scripts/plot_perf.py
    python3 scripts/plot_perf.py --check

It regenerates every SVG and prints the two GitHub ``<picture>`` embed blocks to
stdout (one per figure), ready to paste into PERFORMANCE.md / README.md.

DATA IS HISTORICAL AND NON-NORMATIVE. The fallback values below transcribe old
developer runs described in ``PERFORMANCE.md`` and ``NEST_REALTIME.md``. They are
not raw release evidence, calibration, capacity certification, or a performance
gate for ``1.0.0-rc.1``.

DATA PROVENANCE. Each benchmark script (``bench_realtime.py``, ``bench_overlap.py``,
``bench_gil_overlap.py``, ``bench_chunk_overhead.py``) now accepts ``--out <file>``
to persist its JSON results. When complete data files exist under
``docs/plots/data/``, this script validates and reads them instead of the fallback.
When absent, generation emits the explicitly labelled historical fallback. A
future release campaign must retain raw data and provenance separately.

    python3 scripts/bench_realtime.py --out docs/plots/data/realtime.json [flags]
    python3 scripts/bench_gil_overlap.py --out docs/plots/data/gil_overlap.json [flags]
    python3 scripts/plot_perf.py  # picks up the data files automatically

Honesty invariants baked into the figures (a regression in any is a bug):
  * Overlap falloff curve uses S(work) = (compute + work) / max(compute, work),
    compute = 8.0 ms  (NOT the doc's literal max/sum, which is inverted).
  * 1.68x is an IDEALIZED CEILING (off-GIL serialize only); it is drawn hollow /
    hatched with a verbatim caveat and sits visibly *below* the analytic 1.80x.
    A naive Python-serialize thread lands at ~1.08x (the realistic, solid bar).
  * Only the three N=10000 cells at T>=4 (1.18/2.01/2.13x) reach real time;
    no N>=50000 point is ever marked real-time.
  * The ~17-20k crossing is INTERPOLATED (no sample between 10k and 50k):
    hollow marker, annotated as such, never a solid measured point.
  * Each figure carries its OWN regime caption (the two benches differ).

Deps: stdlib + numpy + matplotlib only (no seaborn).
"""

from __future__ import annotations

import argparse
import filecmp
import json
import math
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless / file-only backend; no display needed

import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
import matplotlib.ticker as mticker
import numpy as np

EXPECTED_MATPLOTLIB = "3.11.0"
EXPECTED_NUMPY = "2.4.2"

# --------------------------------------------------------------------------- #
# 1. HISTORICAL FALLBACK DATA (non-normative; see module docstring)
# --------------------------------------------------------------------------- #

# (A) I/O-overlap speedup — PERFORMANCE.md L164-166.
#     (label, speedup_x, kind)  kind in {"measured", "ceiling"}.
OVERLAP_BARS = [
    ("serial (Run, then transport)", 1.00, "measured"),
    ("Python thread during Run", 1.08, "measured"),
    ("native thread (C/Rust/PyO3) in Run", 1.68, "ceiling"),  # IDEALIZED
]

# (B) Diminishing-returns falloff — analytic overlap ceiling, compute fixed.
#     S(work) = (COMPUTE_MS + work) / max(COMPUTE_MS, work).
#     NOTE: PERFORMANCE.md L186's inline literal is max/sum (inverted) — that is
#     the doc's typo, NOT this script's. Do not "fix" the direction back.
COMPUTE_MS = 8.0
FALLOFF_ANCHORS = [(10.0, 1.80), (0.6, 1.075), (0.1, 1.0125)]  # doc anchors on the curve
MEASURED_OVERLAP_PT = (10.0, 1.68)  # native-thread MEASURED — sits BELOW analytic 1.80

# (C) Real-time factor grid — NEST_REALTIME.md L375-378.
#     rt = bio-s / wall-s, at T = 1, 2, 4, 8, 16 threads.
THREADS = [1, 2, 4, 8, 16]
RT = {
    10000: [0.32, 0.63, 1.18, 2.01, 2.13],
    50000: [0.033, 0.063, 0.14, 0.30, 0.35],
    100000: [0.014, 0.032, 0.066, 0.13, 0.17],
    200000: [0.0065, 0.013, 0.027, 0.054, 0.071],
}
# Which N=10000 cells reached real time (T >= 4): mark these filled, above rt=1.
RT_LIVE_THREADS = (4, 8, 16)
# ~17-20k crossing at T=16 is an INTERPOLATION (no sample 10k-50k). Hollow only.
LIVE_CEILING_XY = (16, 1.0)  # placed at the T=16 column on the rt=1 line

REGIME_RT = (
    "HISTORICAL LOCAL RUN — NOT RELEASE-BOUND · NEST 3.8.0 · OpenMP · 16 cores · ~500 syn/neuron "
    "· ~13 Hz async-irregular"
)
REGIME_OVERLAP = (
    "HISTORICAL SYNTHETIC STAND-IN — NOT TRANSPORT EVIDENCE · 8000-neuron net · ~8 ms compute + 10 ms work / 20 ms chunk "
    "· 30 chunks · bench_gil_overlap.py (NEST 3.8.0)"
)

ROOT = Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "docs" / "plots"
DATADIR = OUTDIR / "data"

# --------------------------------------------------------------------------- #
# 1b. OPTIONAL STRICT DATA-FILE OVERRIDE
# --------------------------------------------------------------------------- #

_rt_data_path = DATADIR / "realtime.json"
_gil_data_path = DATADIR / "gil_overlap.json"

class PlotDataError(ValueError):
    """A benchmark input cannot support the figure's stated regime."""


def _object_no_duplicates(pairs):
    value = {}
    for key, member in pairs:
        if key in value:
            raise PlotDataError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def _load_json(path: Path):
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlotDataError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise PlotDataError(f"{path} must contain one JSON object")
    return value


def _positive_number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlotDataError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise PlotDataError(f"{label} must be finite and positive")
    return number


def _realtime_override(value):
    if (
        set(value) != {"nest_version", "grid"}
        or not isinstance(value["nest_version"], str)
        or not value["nest_version"].strip()
    ):
        raise PlotDataError("realtime.json has an unexpected top-level shape")
    rows = value["grid"]
    if not isinstance(rows, list):
        raise PlotDataError("realtime.json grid must be an array")
    expected_pairs = {(n, thread) for n in RT for thread in THREADS}
    actual = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PlotDataError(f"realtime grid row {index} must be an object")
        n, thread = row.get("n"), row.get("threads")
        if (
            isinstance(n, bool)
            or not isinstance(n, int)
            or isinstance(thread, bool)
            or not isinstance(thread, int)
        ):
            raise PlotDataError(f"realtime grid row {index} has invalid n/threads")
        pair = (n, thread)
        if pair in actual:
            raise PlotDataError(f"realtime grid duplicates {pair}")
        actual[pair] = _positive_number(
            row.get("realtime_factor"), f"realtime grid {pair} factor"
        )
    if set(actual) != expected_pairs:
        missing = sorted(expected_pairs - set(actual))
        extra = sorted(set(actual) - expected_pairs)
        raise PlotDataError(
            f"realtime grid must contain the exact plotted matrix; missing={missing}, extra={extra}"
        )
    return {n: [actual[(n, thread)] for thread in THREADS] for n in RT}


def _gil_override(value):
    required = {
        "nest_version",
        "compute_ms",
        "chunk_ms",
        "work_ms",
        "n_chunks",
        "threads",
        "n",
        "serial_s",
        "native_overlap_s",
        "py_thread_overlap_s",
        "native_speedup",
        "py_thread_speedup",
    }
    if (
        set(value) != required
        or not isinstance(value["nest_version"], str)
        or not value["nest_version"].strip()
    ):
        raise PlotDataError("gil_overlap.json has an unexpected top-level shape")
    expected_regime = {
        "chunk_ms": 20.0,
        "work_ms": 10.0,
        "n_chunks": 30,
        "threads": 8,
        "n": 8000,
    }
    for key, expected in expected_regime.items():
        if value[key] != expected:
            raise PlotDataError(
                f"gil_overlap.json {key}={value[key]!r} does not match the plotted regime {expected!r}"
            )
    native = _positive_number(value["native_speedup"], "native_speedup")
    python = _positive_number(value["py_thread_speedup"], "py_thread_speedup")
    return native, python


def load_overrides() -> str:
    global MEASURED_OVERLAP_PT
    sources = []
    if _rt_data_path.is_file():
        RT.update(_realtime_override(_load_json(_rt_data_path)))
        sources.append("validated realtime.json")
    if _gil_data_path.is_file():
        native, python = _gil_override(_load_json(_gil_data_path))
        OVERLAP_BARS[2] = (
            "native thread (synthetic off-GIL work)",
            native,
            "ceiling",
        )
        OVERLAP_BARS[1] = ("Python thread during Run", python, "measured")
        MEASURED_OVERLAP_PT = (10.0, native)
        sources.append("validated gil_overlap.json")
    if sources:
        return ", ".join(sources)
    return "historical fallback constants (non-normative; raw receipts absent)"

# --------------------------------------------------------------------------- #
# 2. THEME TOKENS  (GitHub light / dark canvases; design-system §4 / §5)
# --------------------------------------------------------------------------- #

LIGHT = dict(
    name="light",
    face="#ffffff",
    text="#24292f",
    spine="#57606a",
    grid="#d0d7de",
    ref="#57606a",       # rt=1.0 + 1.68x ceiling chrome (6.39:1 on white)
    ceiling="#57606a",
    muted="#57606a",
    hatch_edge="#0B0F14",  # hatched-bar edge on light
)
DARK = dict(
    name="dark",
    face="#0d1117",
    text="#c9d1d9",
    spine="#8b949e",
    grid="#30363d",
    ref="#8b949e",       # 6.15:1 on #0d1117 — NOT #57606a (2.96:1, too dim)
    ceiling="#8b949e",
    muted="#8b949e",
    hatch_edge="#c9d1d9",  # hatched-bar edge on dark
)

# The honesty bbox edge is fixed grey (visible on BOTH canvases); the fill always
# matches the figure face so it never blows out on dark.
BBOX_EC = "#8b949e"

# --------------------------------------------------------------------------- #
# 3. SERIES PALETTE  (color + marker + linestyle bound per series, theme-stable)
#    Okabe-Ito. Marker AND linestyle are mandatory on BOTH themes (orange/sky
#    are sub-3:1 as thin lines on white — color alone is never enough).
# --------------------------------------------------------------------------- #

# Per-theme hue for each Okabe-Ito role.
HUE = {
    "light": dict(blue="#0072B2", verm="#D55E00", green="#009E73", purple="#CC79A7"),
    "dark": dict(blue="#56B4E9", verm="#E8783C", green="#33C295", purple="#E08CBF"),
}

# rt-plot N -> series role (FIXED mapping; identical markers/linestyles per theme).
RT_SERIES = {
    10000: dict(role="blue", marker="o", ls="-", label="N=10k"),
    50000: dict(role="verm", marker="s", ls="--", label="N=50k"),
    100000: dict(role="green", marker="^", ls="-", label="N=100k"),
    200000: dict(role="purple", marker="D", ls="-.", label="N=200k"),
}

YELLOW_FORBIDDEN = "#F0E442"  # documented: never used in these plots (dark-only accent)

# --------------------------------------------------------------------------- #
# 4. HELPERS
# --------------------------------------------------------------------------- #


def _rc() -> None:
    """Global rcParams shared by every figure (Tufte data-ink defaults)."""
    plt.rcParams.update(
        {
            "font.family": ["DejaVu Sans"],
            "svg.fonttype": "none",  # keep text as text in the SVG (selectable/sharp)
            "svg.hashsalt": "ncp-historical-performance-v1",
            "axes.linewidth": 1.0,
        }
    )


def _normalize_svg(path: Path) -> None:
    """Remove generator-only line-end whitespace while preserving one final newline."""
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text(
        "\n".join(line.rstrip() for line in lines) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def apply_theme(fig, ax, T) -> None:
    """Despine top+right, faint y-grid behind data, themed spines/ticks/labels."""
    fig.set_facecolor(T["face"])
    ax.set_facecolor(T["face"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(T["spine"])
        ax.spines[s].set_linewidth(1.0)
    # which="both" so MINOR ticks recolor too — matplotlib leaves minor ticks at
    # their #000000 default otherwise, and they vanish on the #0d1117 dark canvas.
    ax.tick_params(which="both", colors=T["text"], labelsize=10)
    ax.grid(axis="y", color=T["grid"], linewidth=0.6, zorder=0)
    ax.xaxis.label.set_color(T["text"])
    ax.yaxis.label.set_color(T["text"])


def hero_title(ax, text, T, fontsize=15) -> None:
    """Bold title with a subtle face-colored halo (SVG-safe; data is untouched)."""
    t = ax.set_title(text, fontsize=fontsize, fontweight="bold", color=T["text"], pad=12)
    t.set_path_effects(
        [path_effects.withStroke(linewidth=2.5, foreground=T["face"])]
    )


def direct_label(ax, x, y, text, color, *, dx=5, dy=0, fontsize=9, weight="normal", ha="left"):
    """Label a series at its right end instead of using a legend."""
    ax.annotate(
        text,
        xy=(x, y),
        xytext=(dx, dy),
        textcoords="offset points",
        va="center",
        ha=ha,
        color=color,
        fontsize=fontsize,
        fontweight=weight,
        zorder=6,
    )


def honesty_box(ax, xy, xytext, text, T, *, fontsize=9):
    """Boxed caveat annotation with an arrow to the referenced point."""
    ax.annotate(
        text,
        xy=xy,
        xytext=xytext,
        textcoords="data",
        fontsize=fontsize,
        color=T["text"],
        ha="left",
        va="center",
        bbox=dict(boxstyle="round,pad=0.4", fc=T["face"], ec=BBOX_EC, lw=0.8, alpha=0.95),
        arrowprops=dict(arrowstyle="->", color=BBOX_EC, lw=1.0),
        zorder=7,
    )


def regime_caption(fig, text, T) -> None:
    """Mandatory per-figure regime line (each figure states its OWN regime)."""
    fig.text(
        0.5,
        0.012,
        text,
        ha="center",
        va="bottom",
        fontsize=8,
        color=T["muted"],
        style="italic",
    )


# --------------------------------------------------------------------------- #
# 5. FIGURE 1 — overlap_*.svg  (2-panel: hero falloff curve + companion bars)
# --------------------------------------------------------------------------- #


def fig_overlap(T, outdir: Path) -> Path:
    theme = T["name"]
    C = HUE[theme]
    c_blue = C["blue"]
    c_verm = C["verm"]

    fig, (axL, axR) = plt.subplots(
        1, 2, figsize=(8.0, 4.5), gridspec_kw={"width_ratios": [1.6, 1.0]}
    )

    # ----- LEFT panel (HERO): diminishing-returns falloff curve (B) -----
    apply_theme(fig, axL, T)
    axL.set_xscale("log")
    axL.set_xlim(0.05, 12)
    # 1.95 (was 1.9) so the analytic curve's top doesn't clip flush at the frame
    # and read as "data ends here"; the asymptote → 2.0 is implied above.
    axL.set_ylim(1.0, 1.95)
    axL.set_xlabel("transport-work per chunk (ms, log)", fontsize=12)
    axL.set_ylabel("overlap speedup (×)", fontsize=12)
    # Shortened so the 15pt bold hero fits inside the 1.6-ratio left panel and
    # never reaches the right panel's title band (was: "… single-digit-% win").
    hero_title(axL, "Historical overlap model: diminishing synthetic gain", T, fontsize=14)

    # Shaded sub-ms rate-loop regime (where the real T_ncp lives).
    axL.axvspan(0.05, 1.0, color=c_verm, alpha=0.08, zorder=0)
    # Raised (was y=1.045) so it clears the "1.01× @ 0.1 ms" anchor label in the
    # crowded lower-left cell; the two no longer share a row.
    axL.text(
        0.062,
        1.12,
        "rate-loop regime (T_ncp)\nbenefit ≈ single-digit %",
        fontsize=9,
        color=T["muted"],
        va="bottom",
        ha="left",
        zorder=1,
    )

    # Analytic ceiling curve: S(work) = (compute + work) / max(compute, work).
    work = np.logspace(np.log10(0.05), np.log10(12), 400)
    S = (COMPUTE_MS + work) / np.maximum(COMPUTE_MS, work)
    axL.plot(work, S, color=c_blue, lw=2.0, ls="-", zorder=4)
    # Label the curve in the OPEN band above its mid-section (anchored at a mid
    # point, text nudged up-left). Was at the curve's right END with dx=+4, which
    # bled into the right panel; a left nudge there crossed the steep curve — so
    # the label lives mid-curve where there is clear whitespace inside axL.
    _alx = 2.6
    _aly = (COMPUTE_MS + _alx) / max(COMPUTE_MS, _alx)
    axL.annotate(
        "analytic ceiling",
        xy=(_alx, _aly),
        xytext=(-2, 26),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=9,
        color=c_blue,
        zorder=6,
    )

    # Three doc anchors as filled blue dots on the curve.
    for wx, wy in FALLOFF_ANCHORS:
        axL.plot([wx], [wy], marker="o", color=c_blue, ms=6, ls="none", zorder=5)
    axL.annotate(
        "1.80× @ 10 ms",
        xy=(10.0, 1.80),
        xytext=(-6, 8),
        textcoords="offset points",
        ha="right",
        va="bottom",
        fontsize=9,
        color=c_blue,
        zorder=6,
    )
    # Pushed right of its marker (was offset 8,10 up — that climbed into the
    # regime caption); now sits on the baseline beside the (0.1, 1.0125) dot.
    axL.annotate(
        "1.01× @ 0.1 ms",
        xy=(0.1, 1.0125),
        xytext=(10, -2),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=9,
        color=c_blue,
        zorder=6,
    )

    # MEASURED native-thread point (10, 1.68): HOLLOW vermillion square, sits
    # visibly BELOW the analytic 1.80 dot. The gap IS the honesty.
    mx, my = MEASURED_OVERLAP_PT
    axL.plot(
        [mx], [my], marker="s", mfc="none", mec=c_verm, mew=1.8, ms=9, ls="none", zorder=6
    )
    # Label to the lower-RIGHT of the hollow square (was lower-left, ha="right",
    # which ran under the honesty box). The x>10, y<1.68 cell is open whitespace.
    axL.annotate(
        "1.68× measured\n(below ideal)",
        xy=(mx, my),
        xytext=(7, -8),
        textcoords="offset points",
        ha="left",
        va="top",
        fontsize=8.5,
        color=c_verm,
        zorder=6,
    )

    # Honesty callout pointing at the realistic (0.1, 1.0125) end. Text rewrapped
    # to short lines so the box stays inside axL's xlim and never crosses the
    # gutter into the right panel (was two long lines that bled right).
    honesty_box(
        axL,
        xy=(0.1, 1.0125),
        xytext=(0.115, 1.60),
        text=(
            "idealized ceiling —\n"
            "off-GIL serialize only;\n"
            "~1.08× w/ Python serialize,\n"
            "→ ~1.01× at 0.1 ms work"
        ),
        T=T,
        fontsize=8.5,
    )

    # ----- RIGHT panel (companion): 3 horizontal bars (A), zero-baselined -----
    apply_theme(fig, axR, T)
    axR.grid(False)  # horizontal bars: y-grid is noise here
    bars = sorted(OVERLAP_BARS, key=lambda r: r[1])  # ascending by speedup
    ypos = np.arange(len(bars))
    short = {
        "serial (Run, then transport)": "serial",
        "Python thread during Run": "Python thread",
        "native thread (C/Rust/PyO3) in Run": "native thread",
    }
    # Slimmer bars (0.5, was the 0.8 default) open a clear whitespace gap between
    # rows for the per-bar captions below, so nothing overprints a neighbour.
    BAR_H = 0.5
    for i, (label, val, kind) in enumerate(bars):
        if kind == "ceiling":
            # Hatched = provisional ceiling (pre-attentively "different").
            axR.barh(
                i,
                val,
                height=BAR_H,
                color="none",
                edgecolor=c_verm,
                hatch="///",
                linewidth=1.4,
                zorder=3,
            )
            # second pass for a crisp themed border on the hatch
            axR.barh(i, val, height=BAR_H, color="none", edgecolor=T["hatch_edge"], linewidth=1.0, zorder=4)
        else:
            axR.barh(i, val, height=BAR_H, color=c_verm, edgecolor="none", zorder=3)
        axR.annotate(
            f"{val:.2f}×",
            xy=(val, i),
            xytext=(4, 0),
            textcoords="offset points",
            va="center",
            ha="left",
            fontsize=9.5,
            fontweight="bold",
            color=T["text"],
            zorder=6,
        )

    axR.set_xlim(0, 2.0)  # zero baseline — magnitude bars MUST start at 0
    axR.set_ylim(-0.6, len(bars) - 0.4)
    axR.set_yticks(ypos)
    axR.set_yticklabels([short[b[0]] for b in bars], fontsize=10)
    axR.set_xticks([])  # values are direct-labeled; keep only the break-even line
    # Demoted from a bold 12pt title to a smaller, non-bold subtitle and dropped
    # BELOW the left hero's band (placed inside-axes near the top, ha-left) so the
    # two titles never share a horizontal stripe and cannot overprint.
    axR.text(
        0.0,
        1.04,
        "overlap @ 10 ms work (best case)",
        transform=axR.transAxes,
        fontsize=10,
        fontweight="normal",
        color=T["muted"],
        ha="left",
        va="bottom",
    )

    # Break-even reference (achromatic chrome — NOT a data hue).
    axR.axvline(1.0, color=T["ref"], ls=":", lw=1.2, zorder=2)
    axR.annotate(
        "baseline 1.00×",
        xy=(1.0, -0.55),
        xytext=(0, 0),
        textcoords="offset points",
        ha="center",
        va="top",
        fontsize=8,
        color=T["muted"],
        zorder=6,
    )

    # Per-bar realistic-vs-ceiling captions. Each is dropped into the WHITESPACE
    # gap just below its own bar (ceiling→gap above Python; Python→gap above
    # serial) so the two no longer overprint each other or the y-tick labels.
    for i, (label, val, kind) in enumerate(bars):
        if val == 1.08:
            axR.annotate(
                "naive Python serialize lands here",
                xy=(val, i),
                xytext=(0.06, i - 0.52),
                textcoords="data",
                fontsize=8,
                color=T["muted"],
                ha="left",
                va="center",
                zorder=6,
            )
        elif kind == "ceiling":
            axR.annotate(
                "off-GIL ceiling (ctypes stand-in) —\nnot measured transport",
                xy=(val, i),
                xytext=(0.06, i - 0.55),
                textcoords="data",
                fontsize=8,
                color=T["muted"],
                ha="left",
                va="center",
                zorder=6,
            )

    regime_caption(fig, REGIME_OVERLAP, T)
    # Wider gutter so the left-panel direct-labels / honesty box cannot bleed
    # into the right panel, and so the two titles have breathing room.
    fig.subplots_adjust(bottom=0.16, wspace=0.46)

    name = f"overlap_{theme}"
    out = outdir / f"{name}.svg"
    fig.savefig(
        out,
        format="svg",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        metadata={"Date": None, "Creator": "NCP plot_perf.py"},
    )
    plt.close(fig)
    _normalize_svg(out)
    return out


# --------------------------------------------------------------------------- #
# 6. FIGURE 2 — realtime_*.svg  (single panel rt-vs-threads) — README HERO
# --------------------------------------------------------------------------- #


def fig_realtime(T, outdir: Path) -> Path:
    theme = T["name"]
    C = HUE[theme]

    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    apply_theme(fig, ax, T)

    ax.set_yscale("log")
    # Floor 0.004 (was 0.005) so the lowest marker (N=200k, T=1, rt=0.0065) lifts
    # clear of the frame and the disclosure caption can sit beneath it.
    ax.set_ylim(0.004, 3)
    ax.set_xscale("log", base=2)
    ax.set_xlim(0.9, 18)
    ax.set_xticks(THREADS)
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlabel("OpenMP threads", fontsize=12)
    ax.set_ylabel("real-time factor   rt = bio-s / wall-s", fontsize=12)
    hero_title(
        ax,
        "Historical local sweep — only sampled 10k series crosses rt=1",
        T,
    )

    # Sub-real-time floor: "below the line = offline" reads pre-attentively.
    ax.axhspan(0.004, 1.0, color="#8b949e", alpha=0.08, zorder=0)

    # The N-series. N=10k is the protagonist (full saturation, thicker).
    for N, spec in RT_SERIES.items():
        color = C[spec["role"]]
        ys = RT[N]
        is_hero = N == 10000
        lw = 2.2 if is_hero else 1.6
        alpha = 1.0 if is_hero else 0.85
        ax.plot(
            THREADS,
            ys,
            color=color,
            marker=spec["marker"],
            ls=spec["ls"],
            lw=lw,
            ms=6,
            alpha=alpha,
            markerfacecolor=color,
            zorder=5 if is_hero else 4,
        )
        # Mark only the N=10000 real-time cells (T>=4) with emphasized filled markers.
        if is_hero:
            for t in RT_LIVE_THREADS:
                yt = ys[THREADS.index(t)]
                ax.plot(
                    [t], [yt], marker=spec["marker"], color=color, ms=9, mec=color,
                    mew=1.0, ls="none", zorder=6,
                )
        # Direct end-labels (no legend).
        if is_hero:
            direct_label(
                ax, THREADS[-1], ys[-1],
                "N=10k · 2.13× @ 16 threads",
                color, dx=6, dy=4, weight="bold",
            )
        else:
            direct_label(ax, THREADS[-1], ys[-1], spec["label"], color, dx=6, dy=0)

    # rt = 1.0 reference SPINE — grey chrome (vermillion is the N=50k DATA series).
    ax.axhline(1.0, color=T["ref"], ls="--", lw=1.5, zorder=2)
    ax.text(
        THREADS[-1], 1.0, "  real-time (rt = 1.0)",
        va="bottom", ha="right", color=T["ref"], fontsize=9, zorder=6,
    )

    # Interpolated crossing: hollow marker + caveat. NEVER a solid point.
    lx, ly = LIVE_CEILING_XY
    ax.plot([lx], [ly], marker="o", mfc="none", mec=T["muted"], mew=1.5, ms=10, ls="none", zorder=6)
    # Dropped lower and shifted left (was xytext=(7.2, 0.30)) so the box sits in
    # the gap BELOW the N=50k line and no longer occludes the N=50k end-label /
    # marker at x=16; the arrow still reaches the hollow ceiling dot at (16, 1.0).
    ax.annotate(
        "~17–20k crossing:\ninterpolated (no sample 10k–50k)",
        xy=(lx, ly),
        xytext=(2.0, 0.185),
        textcoords="data",
        fontsize=8.5,
        color=T["muted"],
        ha="left",
        va="center",
        bbox=dict(boxstyle="round,pad=0.3", fc=T["face"], ec=BBOX_EC, lw=0.8, alpha=0.95),
        arrowprops=dict(arrowstyle="->", color=BBOX_EC, lw=1.0),
        zorder=7,
    )

    # Normalization-honesty disclosure (so the 500 ms row isn't a hidden
    # apples-to-oranges). Dropped to y=0.0046 (was 0.0068, which kissed the
    # N=200k T=1 marker at 0.0065) so caption and lowest marker don't touch.
    ax.text(
        0.95,
        0.0046,
        "rt normalized per bio-time (N=200k used T_bio=500 ms)",
        fontsize=8,
        color=T["muted"],
        ha="left",
        va="bottom",
        zorder=6,
    )

    regime_caption(fig, REGIME_RT, T)
    fig.subplots_adjust(bottom=0.16, right=0.86)

    name = f"realtime_{theme}"
    out = outdir / f"{name}.svg"
    fig.savefig(
        out,
        format="svg",
        bbox_inches="tight",
        facecolor=fig.get_facecolor(),
        metadata={"Date": None, "Creator": "NCP plot_perf.py"},
    )
    plt.close(fig)
    _normalize_svg(out)
    return out


# --------------------------------------------------------------------------- #
# 7. EMBED MARKDOWN  (printed to stdout — paste into README / PERFORMANCE.md)
# --------------------------------------------------------------------------- #

EMBED_REALTIME = """<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="docs/plots/realtime_dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/plots/realtime_light.svg">
  <img alt="Historical non-release-bound local real-time-factor sweep versus OpenMP threads. Only the sampled N=10,000 series crosses rt=1; larger sampled series remain below it. The hollow ~17–20k crossing is interpolated across an unsampled range and is not capacity evidence. NEST 3.8.0 developer run." src="docs/plots/realtime_light.svg">
</picture>"""

EMBED_OVERLAP = """<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="docs/plots/overlap_dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/plots/overlap_light.svg">
  <img alt="Historical synthetic overlap illustration. The left panel shows an analytic ceiling versus modeled work; the right panel compares retained serial and Python-thread values with a hatched 1.68x off-GIL busy-spin stand-in. This is not measured NCP transport or release performance evidence." src="docs/plots/overlap_light.svg">
</picture>"""


# --------------------------------------------------------------------------- #
# __main__
# --------------------------------------------------------------------------- #


def self_test() -> None:
    grid = [
        {"n": n, "threads": thread, "realtime_factor": RT[n][index]}
        for n in RT
        for index, thread in enumerate(THREADS)
    ]
    value = {"nest_version": "test", "grid": grid}
    if _realtime_override(value) != RT:
        raise AssertionError("valid realtime fixture changed values")
    truncated = {"nest_version": "test", "grid": grid[:-1]}
    try:
        _realtime_override(truncated)
    except PlotDataError:
        pass
    else:
        raise AssertionError("partial realtime grid unexpectedly passed")

    gil = {
        "nest_version": "test",
        "compute_ms": 8.0,
        "chunk_ms": 20.0,
        "work_ms": 10.0,
        "n_chunks": 30,
        "threads": 8,
        "n": 8000,
        "serial_s": 0.586,
        "native_overlap_s": 0.348,
        "py_thread_overlap_s": 0.541,
        "native_speedup": 1.68,
        "py_thread_speedup": 1.08,
    }
    if _gil_override(gil) != (1.68, 1.08):
        raise AssertionError("valid GIL fixture changed values")
    gil["n"] = 9000
    try:
        _gil_override(gil)
    except PlotDataError:
        pass
    else:
        raise AssertionError("mislabeled GIL regime unexpectedly passed")

    try:
        json.loads('{"a":1,"a":2}', object_pairs_hook=_object_no_duplicates)
    except PlotDataError:
        pass
    else:
        raise AssertionError("duplicate JSON key unexpectedly passed")


def _generate(outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    _rc()
    written = []
    for theme in (LIGHT, DARK):
        written.append(fig_overlap(theme, outdir))
        written.append(fig_realtime(theme, outdir))
    return written


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if matplotlib.__version__ != EXPECTED_MATPLOTLIB or np.__version__ != EXPECTED_NUMPY:
            raise PlotDataError(
                "plot dependency versions differ: "
                f"matplotlib={matplotlib.__version__} numpy={np.__version__}; "
                f"expected {EXPECTED_MATPLOTLIB}/{EXPECTED_NUMPY}"
            )
        if args.self_test:
            self_test()
        source = load_overrides()
        if args.check:
            with tempfile.TemporaryDirectory() as directory:
                fresh = _generate(Path(directory))
                for generated in fresh:
                    committed = OUTDIR / generated.name
                    if not committed.is_file() or not filecmp.cmp(
                        generated, committed, shallow=False
                    ):
                        raise PlotDataError(
                            f"{committed.relative_to(ROOT)} differs from deterministic generation"
                        )
            print(f"OK historical plots reproducible from {source}")
            return 0

        written = _generate(OUTDIR)
        print(f"Wrote {len(written)} non-normative SVG(s) from {source}:")
        for path in written:
            print(f"  {path.relative_to(ROOT)}")

        print("\n--- PERFORMANCE.md / README historical realtime figure ---\n")
        print(EMBED_REALTIME)
        print("\n--- PERFORMANCE.md historical overlap figure ---\n")
        print(EMBED_OVERLAP)
        return 0
    except (PlotDataError, OSError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
