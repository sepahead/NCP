#!/usr/bin/env python3
"""Generate NCP's bespoke "Instrument Datasheet" SVG diagrams (light + dark).

Replaces the flat Mermaid diagrams with hand-composed, GitHub-<img>-safe SVGs:
one semantic design system, depth (gradients + soft shadow + restrained glow),
bespoke duotone icons, an 8px drafting grid, and a prominent vermillion
body-gated ACTION trace where the subject includes actuation. Two committed files per diagram
(``*-light.svg`` + ``*-dark.svg``), embedded via a ``prefers-color-scheme``
``<picture>`` (mirrors docs/plots/). Core plane hues follow the performance-plot
palette so diagrams and benchmarks read as one instrument.

Output: docs/diagrams/{overview,topology,ecosystem,versioning,fsm,sequence,
        admission,runtime,lifecycle}-{light,dark}.svg
Run:    python3 scripts/gen_diagrams.py [--check]    (from repo root)

Pure stdlib. GitHub-safe: gradients/filters/patterns/markers/real <text> only —
no <script>, <foreignObject>, external href/font/CSS, animation, or interactivity.
"""

from __future__ import annotations
import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_IDENTITY = json.loads(
    (ROOT / "contract" / "manifest.v1.json").read_text(encoding="utf-8")
)
CANDIDATE_VERSION = CONTRACT_IDENTITY["candidate"]
WIRE_VERSION = CONTRACT_IDENTITY["wire_version"]
CONTRACT_HASH = CONTRACT_IDENTITY["wire_proto_contract_hash_fnv1a64"]
if not all(
    isinstance(value, str) and value
    for value in (CANDIDATE_VERSION, WIRE_VERSION, CONTRACT_HASH)
):
    raise ValueError("contract manifest has incomplete diagram identity")
WIRE_MAJOR = WIRE_VERSION.split(".", 1)[0]
if not WIRE_MAJOR.isascii() or not WIRE_MAJOR.isdigit():
    raise ValueError("contract manifest wire version has no canonical major")
CURRENT_META = (
    f"NCP · UNRELEASED {CANDIDATE_VERSION} · WIRE {WIRE_VERSION} · "
    f"COMPACT PROTO HASH {CONTRACT_HASH}"
)

EXPECTED_PLANE_KEY_GRAMMAR = (
    "{realm}/rpc/{request_kind} | "
    "{realm}/session/{session_id}/{sensor|command}[/{channel}] | "
    "{realm}/session/{session_id}/observation"
)
PLANE_CONTRACT = json.loads(
    (ROOT / "contract" / "planes.v1.json").read_text(encoding="utf-8")
)
PLANE_KEY_GRAMMAR = PLANE_CONTRACT.get("key_grammar")
if PLANE_KEY_GRAMMAR != EXPECTED_PLANE_KEY_GRAMMAR:
    raise ValueError("plane contract key grammar changed; review every diagram route")
RPC_ROUTE, SESSION_ROUTE_TEMPLATE, OBSERVATION_ROUTE = PLANE_KEY_GRAMMAR.split(" | ")
if SESSION_ROUTE_TEMPLATE.count("{sensor|command}") != 1:
    raise ValueError("plane contract has no singular sensor/command route selector")
SENSOR_ROUTE = SESSION_ROUTE_TEMPLATE.replace("{sensor|command}", "sensor")
COMMAND_ROUTE = SESSION_ROUTE_TEMPLATE.replace("{sensor|command}", "command")

SVG_ACCESSIBILITY = {
    "overview": (
        "NCP protocol function overview",
        f"Informative proposed B01 overview for the UNRELEASED {CANDIDATE_VERSION} "
        "candidate. It shows five shared gates: raw bounds, authenticated ingress, "
        "wire and stable-core identity, session and stream checks, and typed delivery. "
        "Action adds a sixth, conditional body-effect predicate. The four planes are "
        "bounded. Direct production-secure Zenoh ingress is unavailable. This is not "
        "implementation, release, or certification evidence.",
    ),
    "topology": (
        "NCP commander-body topology",
        f"Informative topology for the UNRELEASED {CANDIDATE_VERSION} candidate. "
        "It shows the commander, body, observer, and four core planes. It is not a "
        "release, interoperability qualification, or certification claim.",
    ),
    "ecosystem": (
        "NCP ecosystem integration map",
        f"Informative ecosystem map for the UNRELEASED {CANDIDATE_VERSION} candidate. "
        "It shows optional adapter dependency direction and the authority boundary for "
        "Engram, Haldir, Crebain, Galadriel, and Prisoma. It also shows that pid-rs "
        "remains protocol-neutral and has no NCP role edge. "
        "It is not a release, consumer qualification, or certification claim.",
    ),
    "versioning": (
        "NCP version and identity gate",
        f"Informative proposed native-session gate for the UNRELEASED {CANDIDATE_VERSION} "
        f"candidate and wire {WIRE_VERSION}. Canonical same-major parsing and the exact "
        "stable-core digest are both required. Release, corpus, extension, package, and "
        "compact-proto identities do not independently authorize a native session. "
        "This diagram is not an implementation, release, or certification claim.",
    ),
    "fsm": (
        "NCP plant-admission state model",
        f"Informative plant-admission model for the UNRELEASED {CANDIDATE_VERSION} "
        "candidate. It distinguishes normalized wire candidates from installed plant-profile "
        "actions, including ACTIVE, HOLD, latched ESTOP, configuration failure, local no-wire "
        "failure, publisher-position admission, and generation-cut reset. It is not a release "
        "claim or physical-safety certification.",
    ),
    "sequence": (
        "NCP simulation-session sequence",
        f"Informative proposed simulation-session sequence for the UNRELEASED "
        f"{CANDIDATE_VERSION} candidate. It traces the native wire and stable-core gate, "
        "simulation open, bounded step or run, result, and close messages. It grants no "
        "plant authority and is not an implemented wire, release, interoperability, or "
        "certification claim.",
    ),
    "admission": (
        "NCP body command admission",
        f"Informative proposed B01 low-overhead target for the UNRELEASED {CANDIDATE_VERSION} "
        "candidate. It is not the implemented contract. It shows raw bounds, authentication, "
        "one decode, no-reuse, ESTOP latching, admission, and the body effect gate. "
        "It is not a release, interoperability, or physical-safety certification claim.",
    ),
    "runtime": (
        "NCP low-overhead runtime path",
        f"Informative proposed B01 runtime path for the UNRELEASED {CANDIDATE_VERSION} "
        "candidate. It separates prepare-once work from a bounded frame path, a short "
        "owner transition, and an unlocked handoff. Its latency and memory equations "
        "are symbolic design bounds, not measurements. It is not implementation, "
        "release, performance qualification, or certification evidence.",
    ),
    "lifecycle": (
        "NCP session lifecycle mutation owner",
        f"Informative proposed B01 lifecycle model for the UNRELEASED {CANDIDATE_VERSION} "
        "candidate. One namespace slot serializes each operation through pending, ambiguous, "
        "and terminal commit. Terminal commit publishes the reserved result and high-water "
        "before releasing the slot. Exact retries compare retained coordinates and bytes. "
        "Shared finite stores avoid per-session services. This is not implementation, release, "
        "or certification evidence.",
    ),
}

# ───────────────────────────── theme tokens ─────────────────────────────
DARK = dict(
    name="dark",
    bg_top="#11161d",
    bg_bot="#0d1117",
    surf_top="#161b22",
    surf_bot="#11161d",
    surf_chip="#1b232c",
    border="#30363d",
    grid="#8b949e",
    grid_dot_op=0.5,
    grid_major_op=0.22,
    tprim="#e6edf3",
    tsec="#c9d1d9",
    tmut="#8b949e",
    control="#3a9ad9",
    perception="#56b4e9",
    action="#e8783c",
    action_hi="#ff8a4c",
    observation="#8b949e",
    contract="#a78bfa",
    contract_lo="#8c72d9",
    active="#33c295",
    hold="#f0b429",
    configfail="#e08cbf",
    fsm_active_text="#33c295",
    fsm_hold_text="#f0b429",
    fsm_configfail_text="#e08cbf",
    fsm_action_text="#e8783c",
    fsm_active_badge="#33c295",
    fsm_active_badge_text="#06281e",
    fsm_estop_badge_text="#0d1117",
    fsm_hero_ink="#0d1117",
    shadow="#05070b",
    shadow_op=0.6,
    shadow_dy=4,
    shadow_sd=7,
    halo_op=0.40,
    glow_flood="#ff8a4c",
    glow_op=0.9,
    glow_double=True,
    bus_stops=[
        ("0", "#e8783c", "0.85"),
        ("0.5", "#ff8a4c", "1"),
        ("1", "#e8783c", "0.85"),
    ],
    fsm_bus_stops=[
        ("0", "#e8783c", "0.85"),
        ("0.5", "#ff8a4c", "1"),
        ("1", "#e8783c", "0.85"),
    ],
    wash_op=0.06,
)
LIGHT = dict(
    name="light",
    bg_top="#ffffff",
    bg_bot="#f3f5f8",
    surf_top="#ffffff",
    surf_bot="#eef1f5",
    surf_chip="#eef1f5",
    border="#d0d7de",
    grid="#57606a",
    grid_dot_op=0.5,
    grid_major_op=0.26,
    tprim="#1b2733",
    tsec="#24292f",
    tmut="#57606a",
    control="#0072B2",
    perception="#56B4E9",
    action="#D55E00",
    action_hi="#D55E00",
    observation="#999999",
    contract="#6D28D9",
    contract_lo="#5b21b6",
    active="#009E73",
    hold="#E69F00",
    configfail="#CC79A7",
    fsm_active_text="#006B4F",
    fsm_hold_text="#8A5A00",
    fsm_configfail_text="#8C3F6F",
    fsm_action_text="#8C3B00",
    fsm_active_badge="#007A59",
    fsm_active_badge_text="#ffffff",
    fsm_estop_badge_text="#0d1117",
    fsm_hero_ink="#1b2733",
    shadow="#1b2733",
    shadow_op=0.18,
    shadow_dy=3,
    shadow_sd=5,
    halo_op=0.22,
    glow_flood="#D55E00",
    glow_op=0.4,
    glow_double=False,
    bus_stops=[("0", "#D55E00", "1"), ("0.5", "#D55E00", "1"), ("1", "#b94f00", "1")],
    fsm_bus_stops=[
        ("0", "#F07A32", "1"),
        ("0.5", "#F58A45", "1"),
        ("1", "#E66F24", "1"),
    ],
    wash_op=0.05,
)

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"


# ───────────────────────────── primitives ─────────────────────────────
def _relative_luminance(color: str) -> float:
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError(f"expected six-digit hex color, got {color!r}")
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(foreground: str, background_color: str) -> float:
    foreground_luminance = _relative_luminance(foreground)
    background_luminance = _relative_luminance(background_color)
    lighter = max(foreground_luminance, background_luminance)
    darker = min(foreground_luminance, background_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _composite_color(foreground: str, background_color: str, opacity: float) -> str:
    if not 0 <= opacity <= 1:
        raise ValueError(f"opacity must be in [0, 1], got {opacity}")
    foreground_channels = [
        int(foreground[index : index + 2], 16) for index in (1, 3, 5)
    ]
    background_channels = [
        int(background_color[index : index + 2], 16) for index in (1, 3, 5)
    ]
    channels = [
        round(opacity * front + (1 - opacity) * back)
        for front, back in zip(foreground_channels, background_channels)
    ]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def contrast_ink(*background_colors: str) -> str:
    """Select one normal-text ink that clears 4.5:1 on every background."""
    candidates = ("#0d1117", "#ffffff")
    ink = max(
        candidates,
        key=lambda candidate: min(
            _contrast_ratio(candidate, background) for background in background_colors
        ),
    )
    minimum = min(_contrast_ratio(ink, background) for background in background_colors)
    if minimum < 4.5:
        raise ValueError(
            "no black-or-white text ink clears 4.5:1 on " + ", ".join(background_colors)
        )
    return ink


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def semantic_text_color(theme: dict, hue: str) -> str:
    """Return a semantic text color with at least normal-text contrast."""
    if theme["name"] == "dark":
        return hue
    return {
        theme["control"]: "#005F8A",
        theme["perception"]: "#006A94",
        theme["action"]: "#8C3B00",
        theme["observation"]: "#595959",
        theme["contract"]: "#6D28D9",
        theme["active"]: "#006B4F",
        theme["hold"]: "#8A5A00",
        theme["configfail"]: "#8C3F6F",
    }.get(hue, hue)


def T(
    x,
    y,
    s,
    size,
    weight=400,
    fill="#000",
    *,
    family=SANS,
    anchor="start",
    track=0,
    italic=False,
    op=None,
    mono=False,
):
    fam = MONO if mono else family
    style = "italic" if italic else "normal"
    extra = f' letter-spacing="{track}"' if track else ""
    opa = f' fill-opacity="{op}"' if op is not None else ""
    return (
        f'<text x="{x}" y="{y}" font-family="{fam}" font-size="{size}" '
        f'font-weight="{weight}" font-style="{style}" fill="{fill}"{opa} '
        f'text-anchor="{anchor}"{extra} text-rendering="geometricPrecision">{esc(s)}</text>'
    )


def rect(
    x, y, w, h, rx=0, fill="none", stroke="none", sw=0, dash=None, op=None, filt=None
):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' fill-opacity="{op}"' if op is not None else ""
    f = f' filter="url(#{filt})"' if filt else ""
    s = f' stroke="{stroke}" stroke-width="{sw}"' if stroke != "none" else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"{s}{d}{o}{f}/>'


def line(
    x1, y1, x2, y2, stroke, sw, dash=None, cap="round", op=None, marker=None, filt=None
):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    o = f' stroke-opacity="{op}"' if op is not None else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    f = f' filter="url(#{filt})"' if filt else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
        f'stroke-width="{sw}" stroke-linecap="{cap}"{d}{o}{m}{f}/>'
    )


def path(
    d,
    stroke="none",
    sw=0,
    fill="none",
    cap="round",
    join="round",
    op=None,
    marker=None,
    filt=None,
    dash=None,
):
    o = f' stroke-opacity="{op}"' if op is not None else ""
    m = f' marker-end="url(#{marker})"' if marker else ""
    f = f' filter="url(#{filt})"' if filt else ""
    dd = f' stroke-dasharray="{dash}"' if dash else ""
    s = (
        f' stroke="{stroke}" stroke-width="{sw}" stroke-linecap="{cap}" stroke-linejoin="{join}"'
        if stroke != "none"
        else ""
    )
    return f'<path d="{d}" fill="{fill}"{s}{dd}{o}{m}{f}/>'


# ───────────────────────────── defs kit ─────────────────────────────
def defs(th, *, include_fsm=False) -> str:
    bus = "".join(
        f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>'
        for o, c, op in th["bus_stops"]
    )
    fsm_gradient = ""
    if include_fsm:
        fsm_bus = "".join(
            f'<stop offset="{o}" stop-color="{c}" stop-opacity="{op}"/>'
            for o, c, op in th["fsm_bus_stops"]
        )
        fsm_gradient = (
            '  <linearGradient id="fsmAction" x1="0" y1="0" x2="1" y2="0">'
            f"{fsm_bus}</linearGradient>\n"
        )
    glow_merge = (
        '<feMergeNode in="g"/><feMergeNode in="g"/><feMergeNode in="SourceGraphic"/>'
        if th["glow_double"]
        else '<feMergeNode in="g"/><feMergeNode in="SourceGraphic"/>'
    )
    glow_in = "SourceGraphic" if th["glow_double"] else "SourceAlpha"
    return f'''<defs>
  <linearGradient id="pageBg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{th["bg_top"]}"/><stop offset="1" stop-color="{th["bg_bot"]}"/>
  </linearGradient>
  <linearGradient id="surface" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{th["surf_top"]}"/><stop offset="1" stop-color="{th["surf_bot"]}"/>
  </linearGradient>
  <linearGradient id="busAction" x1="0" y1="0" x2="1" y2="0">{bus}</linearGradient>
{fsm_gradient}  <linearGradient id="contractHero" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{th["contract"]}"/><stop offset="1" stop-color="{th["contract_lo"]}"/>
  </linearGradient>
  <radialGradient id="gridDot" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{th["grid"]}" stop-opacity="{th["grid_dot_op"]}"/>
    <stop offset="1" stop-color="{th["grid"]}" stop-opacity="0"/>
  </radialGradient>
  <pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse">
    <circle cx="2" cy="2" r="1.4" fill="url(#gridDot)"/>
  </pattern>
  <pattern id="gridMajor" width="110" height="110" patternUnits="userSpaceOnUse">
    <path d="M110 0H0V110" fill="none" stroke="{th["grid"]}" stroke-width="0.75" stroke-opacity="{th["grid_major_op"]}"/>
  </pattern>
  <filter id="soft" x="-40%" y="-40%" width="180%" height="180%" color-interpolation-filters="sRGB">
    <feDropShadow dx="0" dy="{th["shadow_dy"]}" stdDeviation="{th["shadow_sd"]}" flood-color="{th["shadow"]}" flood-opacity="{th["shadow_op"]}"/>
  </filter>
  <filter id="halo" x="-60%" y="-60%" width="220%" height="220%" color-interpolation-filters="sRGB">
    <feGaussianBlur stdDeviation="3"/>
  </filter>
  <filter id="glow" x="-90%" y="-90%" width="280%" height="280%" color-interpolation-filters="sRGB">
    <feGaussianBlur in="{glow_in}" stdDeviation="3.4" result="b"/>
    <feFlood flood-color="{th["glow_flood"]}" flood-opacity="{th["glow_op"]}"/>
    <feComposite in2="b" operator="in" result="g"/>
    <feMerge>{glow_merge}</feMerge>
  </filter>
  <marker id="arrowAction" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["action"]}"/></marker>
  <marker id="arrowControl" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["control"]}"/></marker>
  <marker id="replyControl" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M2,1.5 L9,5.5 L2,9.5" fill="none" stroke="{th["control"]}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></marker>
  <marker id="arrowPercep" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["perception"]}"/></marker>
  <marker id="tapObserve" markerUnits="userSpaceOnUse" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto"><circle cx="5" cy="5" r="3.2" fill="none" stroke="{th["observation"]}" stroke-width="1.5"/></marker>
  <marker id="arrowContract" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["contract"]}"/></marker>
  <marker id="submoduleArrow" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M2,1.5 L9,5.5 L2,9.5" fill="none" stroke="{th["observation"]}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></marker>
  <marker id="arrowActive" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["active"]}"/></marker>
  <marker id="arrowEstop" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["action"]}" stroke="#ffd9c2" stroke-width="0.6"/></marker>
  <marker id="arrowHold" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["hold"]}"/></marker>
  <marker id="arrowMut" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["tmut"]}"/></marker>
  <marker id="arrowConfig" markerUnits="userSpaceOnUse" markerWidth="12" markerHeight="12" refX="9" refY="5.5" orient="auto"><path d="M1,1 L9,5.5 L1,10 Z" fill="{th["configfail"]}"/></marker>
  <filter id="glowContract" x="-90%" y="-90%" width="280%" height="280%" color-interpolation-filters="sRGB">
    <feGaussianBlur in="{glow_in}" stdDeviation="3.4" result="b"/>
    <feFlood flood-color="{th["contract"]}" flood-opacity="{th["glow_op"]}"/>
    <feComposite in2="b" operator="in" result="g"/>
    <feMerge>{glow_merge}</feMerge>
  </filter>
  <filter id="glowActive" x="-90%" y="-90%" width="280%" height="280%" color-interpolation-filters="sRGB">
    <feGaussianBlur in="{glow_in}" stdDeviation="3.4" result="b"/>
    <feFlood flood-color="{th["active"]}" flood-opacity="{th["glow_op"]}"/>
    <feComposite in2="b" operator="in" result="g"/>
    <feMerge>{glow_merge}</feMerge>
  </filter>
</defs>'''


# ───────────────────────────── bespoke icons (24x24 → placed) ─────────────────────────────
def _icon(inner, x, y, size, hue):
    s = size / 24.0
    return (
        f'<g transform="translate({x},{y}) scale({s:.4f})" fill="none" stroke="{hue}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{inner}</g>'
    )


def ic_brain(x, y, size, hue):
    inner = (
        f'<path d="M9.5 5.2A3.2 3.2 0 0 0 4 7.6a3 3 0 0 0-1 5.6a3.2 3.2 0 0 0 4 3.6a2.6 2.6 0 0 0 2.5 1.6"/>'
        f'<path d="M14.5 5.2A3.2 3.2 0 0 1 20 7.6a3 3 0 0 1 1 5.6a3.2 3.2 0 0 1-4 3.6a2.6 2.6 0 0 1-2.5 1.6"/>'
        f'<path d="M12 5v13.4"/>'
        f'<circle cx="12" cy="5" r="0.5" fill="{hue}" stroke="{hue}"/>'
        f'<circle cx="7.5" cy="9" r="0.5" fill="{hue}" stroke="{hue}"/>'
        f'<circle cx="16.5" cy="9" r="0.5" fill="{hue}" stroke="{hue}"/>'
        f'<circle cx="8" cy="14" r="0.5" fill="{hue}" stroke="{hue}"/>'
        f'<circle cx="16" cy="14" r="0.5" fill="{hue}" stroke="{hue}"/>'
        f'<path d="M12 8.2 7.5 9M12 8.2 16.5 9M12 12.5 8 14M12 12.5 16 14"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_robot(x, y, size, hue):
    inner = (
        f'<rect x="5" y="8" width="14" height="11" rx="3"/>'
        f'<path d="M12 8V5"/>'
        f'<circle cx="12" cy="3.6" r="1.4" fill="{hue}" stroke="none"/>'
        f'<circle cx="9" cy="12.5" r="1.2" fill="{hue}" stroke="none"/>'
        f'<circle cx="15" cy="12.5" r="1.2" fill="{hue}" stroke="none"/>'
        f'<path d="M9.5 16h5"/><path d="M5 12.5H3M19 12.5h2"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_eye(x, y, size, hue):
    inner = (
        '<path d="M2.5 12c2.2-4 6-6 9.5-6s7.3 2 9.5 6c-2.2 4-6 6-9.5 6s-7.3-2-9.5-6Z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_key(x, y, size, hue):
    inner = (
        '<circle cx="7.5" cy="7.5" r="3.5"/><path d="M10 10l8.5 8.5"/>'
        '<path d="M16 16l2-2M18.5 18.5l2-2"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_lock(x, y, size, hue):
    inner = '<rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/><path d="M12 14.5v2.5"/>'
    return _icon(inner, x, y, size, hue)


def ic_power(x, y, size, hue):
    inner = '<path d="M12 3v8"/><path d="M7.6 6.2a8 8 0 1 0 8.8 0"/>'
    return _icon(inner, x, y, size, hue)


def ic_pause(x, y, size, hue):
    inner = '<path d="M9 6v12M15 6v12"/>'
    return _icon(inner, x, y, size, hue)


def ic_warn(x, y, size, hue):
    inner = (
        f'<path d="M12 4.3 20.6 19.2a1 1 0 0 1-0.87 1.5H4.27a1 1 0 0 1-0.87-1.5L12 4.3Z"/>'
        f'<path d="M12 10v3.6"/><circle cx="12" cy="16.8" r="1.05" fill="{hue}" stroke="none"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_antenna(x, y, size, hue):
    inner = (
        f'<path d="M12 13v7"/><circle cx="12" cy="11" r="1.6" fill="{hue}" stroke="none"/>'
        f'<path d="M8.8 14.2a4.5 4.5 0 0 1 0-6.4M15.2 7.8a4.5 4.5 0 0 1 0 6.4"/>'
        f'<path d="M6.5 16.5a7.8 7.8 0 0 1 0-11M17.5 5.5a7.8 7.8 0 0 1 0 11"/><path d="M9.5 20h5"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_book(x, y, size, hue):
    inner = (
        '<path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H19v15H6.5A1.5 1.5 0 0 0 5 20.5Z"/>'
        '<path d="M5 5.5v15"/><path d="M9 8h6M9 11h6"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_gauge(x, y, size, hue):
    inner = (
        f'<path d="M3.5 17.5a8.5 8.5 0 0 1 17 0"/><path d="M12 17.5 16.2 11.8"/>'
        f'<circle cx="12" cy="17.5" r="1.5" fill="{hue}" stroke="none"/>'
    )
    return _icon(inner, x, y, size, hue)


def ic_break(x, y, size, hue):
    inner = f'<path d="M13 3 L8.5 11 H12.5 L10 21 L17 10 H12.5 L15 3 Z" fill="{hue}" fill-opacity="0.18"/>'
    return _icon(inner, x, y, size, hue)


def ic_noentry(x, y, size, hue):
    inner = '<circle cx="12" cy="12" r="8.5"/><path d="M6.5 12 H17.5"/>'
    return _icon(inner, x, y, size, hue)


def ic_play(x, y, size, hue):
    inner = f'<circle cx="12" cy="12" r="8.5"/><path d="M10 8 L16 12 L10 16 Z" fill="{hue}" stroke="none"/>'
    return _icon(inner, x, y, size, hue)


def ic_approx(x, y, size, hue):
    inner = '<path d="M3 9.5q3 -3.5 6 0t6 0"/><path d="M3 15q3 -3.5 6 0t6 0"/>'
    return _icon(inner, x, y, size, hue)


def ic_octagon(x, y, size, hue):
    inner = '<path d="M8.5 3.5 H15.5 L20.5 8.5 V15.5 L15.5 20.5 H8.5 L3.5 15.5 V8.5 Z"/><path d="M7.5 12 H16.5"/>'
    return _icon(inner, x, y, size, hue)


def ic_terminal(x, y, size, hue):
    inner = '<rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M7 10l3 2.5-3 2.5"/><path d="M12.5 15h4.5"/>'
    return _icon(inner, x, y, size, hue)


def ic_wave(x, y, size, hue):
    inner = (
        '<rect x="3" y="5" width="18" height="14" rx="2.5"/>'
        '<path d="M6 12h2l1.5-3 2 6 1.5-4 1 1h3"/>'
    )
    return _icon(inner, x, y, size, hue)


def diamond(cx, cy, d, th, ring_hue):
    """Rounded decision diamond (rotated rounded square) with soft shadow + identity ring."""
    L = d * 1.414
    x, y = cx - L / 2, cy - L / 2
    tr = f"rotate(45 {cx} {cy})"
    return (
        f'<g transform="{tr}">'
        + rect(x, y, L, L, rx=16, fill="url(#surface)", stroke="none", filt="soft")
        + rect(x, y, L, L, rx=16, fill="none", stroke=th["border"], sw=1.5)
        + rect(
            x + 5,
            y + 5,
            L - 10,
            L - 10,
            rx=12,
            fill="none",
            stroke=ring_hue,
            sw=2,
            op=0.85,
        )
        + "</g>"
    )


# ───────────────────────────── components ─────────────────────────────
def background(th, w, h):
    return (
        rect(0, 0, w, h, fill="url(#pageBg)")
        + rect(0, 0, w, h, fill="url(#gridMajor)")
        + rect(0, 0, w, h, fill="url(#grid)")
    )


def reg_ticks(th, x, y, w, h):
    """Two 6px L-bracket registration ticks at opposite (TR + BL) corners."""
    c = th["tmut"]
    tr = path(f"M{x + w - 6},{y} L{x + w},{y} L{x + w},{y + 6}", stroke=c, sw=1, op=0.5)
    bl = path(f"M{x},{y + h - 6} L{x},{y + h} L{x + 6},{y + h}", stroke=c, sw=1, op=0.5)
    return tr + bl


def card(
    th, x, y, w, h, rail_hue, designator, *, dashed=False, glow=False, filled=None
):
    """Surface card: soft shadow, optional dashed enclosure, left accent rail, designator well."""
    out = []
    if filled:
        out.append(
            rect(
                x,
                y,
                w,
                h,
                rx=12,
                fill=filled,
                stroke=th["border"],
                sw=1.5,
                filt="glow" if glow else "soft",
            )
        )
    else:
        stroke = rail_hue if dashed else th["border"]
        dash = "5 4" if dashed else None
        op = 0.7 if dashed else None
        # shadow + surface
        out.append(
            rect(x, y, w, h, rx=12, fill="url(#surface)", stroke="none", filt="soft")
        )
        out.append(
            rect(
                x, y, w, h, rx=12, fill="none", stroke=stroke, sw=1.5, dash=dash, op=op
            )
        )
    # accent rail (skip for filled hero where the fill IS the identity)
    if not filled:
        out.append(rect(x + 6, y + 12, 4, h - 24, rx=2, fill=rail_hue))
    out.append(reg_ticks(th, x, y, w, h))
    # designator well
    dw, dh = 26, 15
    out.append(
        rect(
            x + 14,
            y + 10,
            dw,
            dh,
            rx=4,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    out.append(
        T(x + 27, y + 20.5, designator, 10, 700, th["tsec"], mono=True, anchor="middle")
    )
    return "".join(out)


def svg_open(w, h, visual_id):
    title, description = SVG_ACCESSIBILITY[visual_id]
    title_id = f"ncp-{visual_id}-title"
    description_id = f"ncp-{visual_id}-desc"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{SANS}" role="img" '
        f'aria-labelledby="{title_id} {description_id}">'
        f'<title id="{title_id}">{esc(title)}</title>'
        f'<desc id="{description_id}">{esc(description)}</desc>'
    )


def sheet_meta(th, x, y, s):
    return T(x, y, s, 10, 600, th["tmut"], mono=True, anchor="end", track=0.8)


def title_block(th, title, eyebrow, w):
    out = [T(28, 50, title, 24, 800, th["tprim"], track=-0.3)]
    out.append(T(29, 64, eyebrow, 10.5, 600, th["tmut"], track=1.0))
    out.append(line(28, 74, w - 28, 74, th["border"], 1, cap="butt"))
    return "".join(out)


# ───────────────────────────── 1. TOPOLOGY (hero) ─────────────────────────────
def topology(th):
    W, H = 860, 610
    s = [svg_open(W, H, "topology"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "TOPOLOGY",
            "PROPOSED B01 TARGET  ·  4 CORE QoS PLANES  ·  READ-ONLY OBSERVER",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))

    # node coords
    U1 = (44, 252, 200, 96)  # commander  (center 144,300)
    U2 = (616, 252, 200, 96)  # body       (center 716,300)
    O1 = (298, 466, 264, 76)  # observer (lower bay)

    # ---- edges (painted bottom-up: OBSERVATION, PERCEPTION, CONTROL, then ACTION on top) ----
    # OBSERVATION O1 — the Body is the canonical publisher of the read-only stream.
    obs = th["observation"]
    s.append(
        path(
            "M716,348 L716,438 Q716,442 712,442 L504,442 Q500,442 500,446 L500,466",
            stroke=obs,
            sw=1.5,
            dash="3 3",
            marker="tapObserve",
        )
    )
    # PERCEPTION P1 (body → commander), dashed, lane y=210 (risers offset from CONTROL)
    per = th["perception"]
    s.append(
        path(
            "M680,252 L680,210 L184,210 L184,252",
            stroke=per,
            sw=2.5,
            dash="6 4",
            marker="arrowPercep",
        )
    )
    # CONTROL C1 (commander ⇄ body), solid, lane y=168, bidirectional
    ctl = th["control"]
    s.append(
        path(
            "M120,252 L120,168 L740,168 L740,252",
            stroke=ctl,
            sw=2.5,
            marker="arrowControl",
        )
    )
    s.append(
        path("M120,240 L120,248", stroke=ctl, sw=2.5, marker="replyControl")
    )  # reply chevron pointing into commander
    # ACTION A1 — the hero bus, dead-straight at y=300
    act = th["action"]
    # fat translucent halo (a bbox filter degenerates on a flat line), then solid bright core
    s.append(line(244, 300, 620, 300, act, 12, op=0.22))
    s.append(line(244, 300, 620, 300, th["action_hi"], 4.5, marker="arrowAction"))
    for tx in (300, 372, 444, 516):
        s.append(line(tx, 295, tx, 305, act, 1, op=0.7))

    # ---- cards ----
    s.append(card(th, *U1, th["control"], "U1"))
    s.append(ic_brain(58, 286, 24, th["control"]))
    s.append(T(90, 300, "NEST brain", 14, 700, th["tprim"]))
    s.append(T(90, 316, "the commander", 10.5, 500, th["tsec"]))
    s.append(T(90, 329, "point + rate neurons", 10.5, 500, th["tsec"]))

    s.append(card(th, *U2, th["observation"], "U2"))
    s.append(ic_robot(630, 286, 24, th["observation"]))
    s.append(T(662, 300, "robot / UAV body", 14, 700, th["tprim"]))
    s.append(T(662, 316, "generic plant role", 10.5, 500, th["tsec"]))
    s.append(T(662, 329, "qualification: NOT RUN", 10.5, 500, th["tsec"]))

    s.append(card(th, *O1, th["observation"], "O1", dashed=True))
    s.append(ic_eye(312, 494, 22, th["observation"]))
    s.append(T(342, 500, "analysis / observer client", 14, 700, th["tprim"]))
    s.append(T(342, 515, "manifest-authorized · read-only tap", 10.5, 500, th["tsec"]))

    # ---- plane label chips (knockout pill on the edge) ----
    def chip(cx, cy, w, desig, dh_hue, concept, key, body, h=30):
        x = cx - w / 2
        y = cy - h / 2
        o = [
            rect(x - 1.5, y - 1.5, w + 3, h + 3, rx=9, fill=th["bg_bot"]),  # knockout
            rect(x, y, w, h, rx=8, fill=th["surf_chip"], stroke=th["border"], sw=1),
            rect(x + 6, y + 7, 16, 16, rx=3, fill=dh_hue),
            T(
                x + 14,
                y + 18.5,
                desig,
                9,
                700,
                contrast_ink(dh_hue),
                mono=True,
                anchor="middle",
            ),
            T(
                x + 28,
                y + 13,
                concept,
                10.5,
                700,
                semantic_text_color(th, dh_hue),
                track=1.0,
            ),
            T(x + 28, y + 25, key, 9.5, 500, th["tmut"], mono=True),
        ]
        if body:
            o.append(
                T(x + 28 + len(concept) * 7 + 14, y + 13, body, 9.5, 500, th["tsec"])
            )
        return "".join(o)

    s.append(
        chip(
            430,
            168,
            320,
            "C1",
            ctl,
            "CONTROL",
            RPC_ROUTE,
            "reliable · request/reply · queryable",
        )
    )
    s.append(
        chip(
            430,
            210,
            370,
            "P1",
            per,
            "PERCEPTION",
            SENSOR_ROUTE,
            "best-effort-replace-latest · lossy",
        )
    )
    s.append(
        chip(
            430, 442, 350, "O1", obs, "OBSERVATION", OBSERVATION_ROUTE, "body publishes"
        )
    )

    # ---- THE HERO: ACTION chip (the one glow) ----
    aw, ah = 360, 96
    ax = int(430 - aw / 2)
    ay = 326
    s.append(line(430, 300, 430, ay, act, 2))  # connector bus → chip
    s.append(
        rect(
            ax, ay, aw, ah, rx=10, fill="url(#surface)", stroke=act, sw=1.5, filt="glow"
        )
    )
    s.append(rect(ax, ay, aw, ah, rx=10, fill=act, op=th["wash_op"]))
    # header row: designator · ACTION eyebrow · right tags
    s.append(rect(ax + 14, ay + 13, 20, 20, rx=4, fill=act))
    s.append(
        T(
            ax + 24,
            ay + 27,
            "A1",
            10,
            700,
            contrast_ink(act),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            ax + 42,
            ay + 27,
            "ACTION",
            12,
            700,
            semantic_text_color(th, act),
            track=1.6,
        )
    )
    s.append(
        T(
            ax + aw - 16,
            ay + 27,
            "express · RealTime · body-gated",
            9,
            600,
            semantic_text_color(th, act),
            anchor="end",
            op=0.95,
        )
    )
    # wire key row
    s.append(T(ax + 14, ay + 46, COMMAND_ROUTE, 8.5, 500, th["tmut"], mono=True))
    # Mode-pill row. Keep this aligned with the current wire enum.
    py = ay + 56
    s.append(T(ax + 14, py + 13, "mode", 9, 600, th["tmut"], mono=True))
    pills = [
        ("active", True, th["active"]),
        ("hold", False, th["hold"]),
        ("estop", True, th["action"]),
    ]
    px = ax + 50
    for label, filled, col in pills:
        pw = 10 + len(label) * 6.4
        if filled is True:
            s.append(rect(px, py, pw, 19, rx=6, fill=col))
        elif filled is None:
            s.append(rect(px, py, pw, 19, rx=6, fill=col, stroke=th["border"], sw=1))
        else:
            s.append(rect(px, py, pw, 19, rx=6, fill="none", stroke=col, sw=1.3))
        text_color = contrast_ink(col) if filled else semantic_text_color(th, col)
        s.append(
            T(
                px + pw / 2,
                py + 13,
                label,
                9,
                700,
                text_color,
                anchor="middle",
                mono=True,
            )
        )
        px += pw + 7
    s.append(
        T(
            px + 4,
            py + 13,
            "· Init rejects · grant deadline",
            8,
            600,
            semantic_text_color(th, th["hold"]),
            mono=True,
        )
    )
    # footnote
    s.append(
        T(
            ax + 14,
            ay + ah - 10,
            "body final authority · profile-declared actions · no universal zero",
            8.5,
            500,
            th["tmut"],
            italic=True,
            track=0.2,
        )
    )

    # ---- bottom legend rail ----
    ly = 568
    s.append(
        rect(28, ly, W - 56, 28, rx=8, fill=th["surf_chip"], stroke=th["border"], sw=1)
    )
    legend = [
        ("A1", act, "ACTION", "heaviest · body-gated", 4, None),
        ("C1", ctl, "CONTROL", "reliable · queryable", 2.5, None),
        ("P1", per, "PERCEPTION", "best-effort", 2.5, "6 4"),
        ("O1", obs, "OBSERVATION", "read-only tap", 1.5, "3 3"),
    ]
    lx = 48
    for desig, hue, concept, tail, sw, dash in legend:
        text_color = semantic_text_color(th, hue)
        s.append(T(lx, ly + 18, desig, 10, 700, text_color, mono=True))
        s.append(line(lx + 22, ly + 14, lx + 44, ly + 14, hue, sw, dash=dash))
        s.append(T(lx + 52, ly + 18, concept, 10.5, 700, text_color, track=0.6))
        lx += 196
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 2. ECOSYSTEM ─────────────────────────────
def ecosystem(th):
    W, H = 980, 680
    s = [svg_open(W, H, "ecosystem"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "ECOSYSTEM",
            "PROPOSED B01 ROLE MAP  ·  OPTIONAL THIN ADAPTERS  ·  QUALIFICATION NOT RUN",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))
    ctr, obs, ctl, act = (
        th["contract"],
        th["observation"],
        th["control"],
        th["action"],
    )
    hero_ink = contrast_ink(th["contract"], th["contract_lo"])

    left_x, right_x, card_w, card_h = 36, 680, 264, 104
    row_y = (112, 264, 416)
    hx, hy, hw, hh = 350, 220, 280, 208

    # Consumer adapters depend on NCP. Route every rail into the hub boundary.
    # The protocol-neutral library has no NCP edge.
    left_targets = (260, row_y[1] + card_h / 2, 390)
    for y, target_y in zip(row_y, left_targets, strict=True):
        cy = y + card_h / 2
        bend_x = hx - 18
        s.append(
            path(
                f"M{left_x + card_w},{cy} L{bend_x - 10},{cy} "
                f"Q{bend_x},{cy} {bend_x},{cy + (10 if target_y > cy else -10)} "
                f"L{bend_x},{target_y} L{hx},{target_y}",
                stroke=ctr,
                sw=2,
                marker="arrowContract",
            )
        )
    right_targets = (260, row_y[1] + card_h / 2)
    for y, target_y in zip(row_y[:2], right_targets, strict=True):
        cy = y + card_h / 2
        bend_x = hx + hw + 18
        s.append(
            path(
                f"M{right_x},{cy} L{bend_x + 10},{cy} "
                f"Q{bend_x},{cy} {bend_x},{cy + (10 if target_y > cy else -10)} "
                f"L{bend_x},{target_y} L{hx + hw},{target_y}",
                stroke=ctr,
                sw=2,
                marker="arrowContract",
            )
        )

    def role_card(
        x, y, designator, hue, icon, name, line_one, line_two, *, dashed=False
    ):
        s.append(card(th, x, y, card_w, card_h, hue, designator, dashed=dashed))
        s.append(icon(x + 18, y + 41, 24, hue))
        s.append(T(x + 54, y + 44, name, 14, 700, th["tprim"]))
        s.append(T(x + 18, y + 70, line_one, 9.5, 600, th["tsec"]))
        s.append(T(x + 18, y + 87, line_two, 9, 500, th["tmut"], mono=True))

    role_card(
        left_x,
        row_y[0],
        "E1",
        ctl,
        ic_brain,
        "Engram",
        "simulation responder / optional commander",
        "direct command XOR Haldir-local intent",
    )
    role_card(
        left_x,
        row_y[1],
        "H1",
        th["hold"],
        ic_key,
        "Haldir",
        "optional gate and NCP commander",
        "policy can deny · never body authority",
    )
    role_card(
        left_x,
        row_y[2],
        "C1",
        act,
        ic_robot,
        "Crebain",
        "NCP body · final software authority",
        "plant profile + effect-path fencing",
    )
    role_card(
        right_x,
        row_y[0],
        "G1",
        obs,
        ic_eye,
        "Galadriel",
        "read-only observer / advisory producer",
        "advice preserves or removes permission",
    )
    role_card(
        right_x,
        row_y[1],
        "P1",
        obs,
        ic_book,
        "Prisoma",
        "read-only capture and offline science",
        "no mutation · gaps remain visible",
    )
    role_card(
        right_x,
        row_y[2],
        "L1",
        th["tmut"],
        ic_book,
        "pid-rs",
        "protocol-neutral estimator library",
        "no NCP dependency or role receipt",
        dashed=True,
    )

    # HERO contract hub.
    cx = hx + hw / 2
    s.append(
        rect(
            hx,
            hy,
            hw,
            hh,
            rx=12,
            fill="url(#contractHero)",
            stroke=th["border"],
            sw=1.5,
            filt="glowContract",
        )
    )
    s.append(rect(hx + 14, hy + 13, hw - 28, 2, rx=1, fill="#ffffff", op=0.5))
    s.append(rect(hx + 16, hy + 14, 26, 15, rx=4, fill="#ffffff", op=0.16))
    s.append(T(hx + 29, hy + 24.5, "U1", 10, 700, hero_ink, mono=True, anchor="middle"))
    s.append(ic_key(cx - 14, hy + 30, 28, hero_ink))
    s.append(T(cx, hy + 82, "NCP", 18, 800, hero_ink, anchor="middle"))
    s.append(
        T(
            cx,
            hy + 99,
            "unreleased 1.0 candidate",
            11,
            600,
            hero_ink,
            anchor="middle",
            op=0.92,
        )
    )
    s.append(
        T(
            cx,
            hy + 120,
            "core · transports · bindings · gateway",
            9.5,
            600,
            hero_ink,
            anchor="middle",
            op=0.9,
            mono=True,
        )
    )
    s.append(line(hx + 22, hy + 128, hx + hw - 22, hy + 128, "#ffffff", 1, op=0.18))
    s.append(
        T(
            cx,
            hy + 140,
            "consumers own thin optional role adapters",
            8.5,
            500,
            hero_ink,
            anchor="middle",
            op=0.76,
            mono=True,
        )
    )
    s.append(rect(cx - 72, hy + 147, 144, 15, rx=6, fill="#ffffff", op=0.13))
    s.append(
        T(
            cx,
            hy + 157.5,
            f"WIRE {WIRE_VERSION} · PROTO {CONTRACT_HASH[:8]} · RELEASE BLOCKED",
            9,
            700,
            hero_ink,
            anchor="middle",
            mono=True,
        )
    )

    # Authority and no-edge laws.
    ly = 558
    s.append(
        rect(28, ly, W - 56, 86, rx=8, fill=th["surf_chip"], stroke=th["border"], sw=1)
    )
    s.append(rect(28, ly, 4, 86, rx=2, fill=act))
    s.append(
        T(
            46,
            ly + 20,
            "AUTHORITY · Crebain remains final software body authority. Direct Engram and Haldir-gated command are mutually exclusive per term.",
            9.5,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            46,
            ly + 42,
            "MONOTONICITY · Galadriel advice can only preserve or remove Haldir permission. Observers gain no command or lifecycle authority.",
            9.5,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            46,
            ly + 64,
            "NO EDGE · pid-rs remains protocol-neutral. It has no NCP package, runtime, documentation-import, or role edge.",
            9.5,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            W - 46,
            ly + 80,
            "solid rail = optional NCP adapter dependency · no consumer qualification completed",
            8.5,
            500,
            th["tmut"],
            anchor="end",
            italic=True,
        )
    )
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 3. VERSIONING ─────────────────────────────
def versioning(th):
    W, H = 820, 520
    s = [svg_open(W, H, "versioning"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "VERSION GATE",
            f"PROPOSED B01 TARGET  ·  CANONICAL {WIRE_MAJOR} OR {WIRE_MAJOR}.<MINOR>  ·  EXACT STABLE CORE",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))
    ctr, verm, grn, ctl, obs = (
        th["contract"],
        th["action"],
        th["active"],
        th["control"],
        th["observation"],
    )

    # ---- edges (painted under cards) ----
    s.append(path("M276,260 L364,260", stroke=ctl, sw=2.5, marker="arrowControl"))
    for tx in (300, 324, 348):
        s.append(line(tx, 256, tx, 264, ctl, 1, op=0.7))
    # reject fork (up)
    s.append(
        path(
            "M508,260 L532,260 Q540,260 540,252 L540,154 Q540,146 548,146 L568,146",
            stroke=verm,
            sw=3,
            marker="arrowEstop",
        )
    )
    # accept fork (down) — the ONE halo
    s.append(line(540, 268, 540, 350, grn, 11, op=0.22))
    s.append(
        path(
            "M508,260 L532,260 Q540,260 540,268 L540,342 Q540,350 548,350 L568,350",
            stroke=grn,
            sw=3,
            marker="arrowActive",
        )
    )
    # advisory drop (dashed)
    s.append(
        path("M678,400 L678,432", stroke=obs, sw=1.5, dash="3 3", marker="tapObserve")
    )

    # ---- N1 native 1.x offer; immutable 0.8 never enters this gate ----
    bx, by, bw, bh = 56, 196, 220, 128
    s.append(card(th, bx, by, bw, bh, ctr, "S0"))
    s.append(ic_break(bx + 16, by + 38, 24, ctr))
    s.append(T(bx + 48, by + 46, "NATIVE 1.x OFFER", 14, 700, th["tprim"]))
    s.append(
        T(bx + 48, by + 61, "0.8 cannot enter or upgrade here", 10, 500, th["tsec"])
    )
    s.append(
        T(
            bx + 18,
            by + 86,
            "unreleased candidate · canonical version",
            9.5,
            500,
            th["tmut"],
            mono=True,
        )
    )
    s.append(
        T(
            bx + 18,
            by + 103,
            "compact proto diagnostic:",
            9.5,
            500,
            th["tmut"],
            mono=True,
        )
    )
    s.append(T(bx + 18, by + 116, CONTRACT_HASH, 9.5, 700, ctr, mono=True))

    # ---- N2 GATE (diamond) ----
    s.append(diamond(440, 260, 76, th, ctr))
    s.append(ic_key(426, 212, 26, ctr))
    s.append(
        T(440, 253, "wire + core", 11.5, 700, th["tprim"], mono=True, anchor="middle")
    )
    s.append(T(440, 268, "HARD", 9.5, 700, ctr, anchor="middle", track=0.6))
    s.append(T(440, 281, "both pass", 9.5, 600, th["tsec"], anchor="middle"))
    s.append(
        T(
            440,
            294,
            "FAIL-CLOSED",
            9.5,
            700,
            semantic_text_color(th, verm),
            anchor="middle",
            track=0.6,
        )
    )

    # ---- N3 REJECT ----
    rx_, ry, rw, rh = 568, 96, 220, 100
    s.append(card(th, rx_, ry, rw, rh, verm, "R0"))
    s.append(ic_noentry(rx_ + rw - 40, ry + 8, 22, verm))
    s.append(rect(rx_ + 18, ry + 40, 9, 9, rx=2, fill=verm))
    s.append(T(rx_ + 33, ry + 48, "REJECTED", 14, 700, th["tprim"]))
    s.append(
        T(rx_ + 18, ry + 66, "invalid wire or core mismatch", 10.5, 500, th["tsec"])
    )
    s.append(
        T(
            rx_ + 18,
            ry + 84,
            "no native session · gateway may terminate",
            9,
            500,
            th["tmut"],
            mono=True,
        )
    )

    # ---- N4 ACCEPT (hero, green glow) ----
    ax, ay, aw, ah = 568, 300, 220, 100
    s.append(
        rect(
            ax,
            ay,
            aw,
            ah,
            rx=12,
            fill="url(#surface)",
            stroke="none",
            filt="glowActive",
        )
    )
    s.append(rect(ax, ay, aw, ah, rx=12, fill="none", stroke=grn, sw=1.5))
    s.append(rect(ax + 6, ay + 12, 4, ah - 24, rx=2, fill=grn))
    s.append(reg_ticks(th, ax, ay, aw, ah))
    s.append(
        rect(
            ax + 14,
            ay + 10,
            26,
            15,
            rx=4,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    s.append(
        T(ax + 27, ay + 20.5, "A0", 10, 700, th["tsec"], mono=True, anchor="middle")
    )
    s.append(ic_play(ax + aw - 40, ay + 8, 22, grn))
    s.append(T(ax + 18, ay + 50, "SESSION MAY OPEN", 14, 700, th["tprim"]))
    s.append(
        T(
            ax + 18,
            ay + 68,
            f"canonical {WIRE_MAJOR} or {WIRE_MAJOR}.<minor> + exact core",
            10.5,
            500,
            th["tsec"],
        )
    )
    s.append(
        T(
            ax + 18,
            ay + 86,
            "both hard checks pass",
            9.5,
            500,
            th["tmut"],
            mono=True,
        )
    )

    # ---- N5 ADVISORY ----
    vx, vy, vw, vh = 568, 432, 220, 56
    s.append(
        rect(vx, vy, vw, vh, rx=10, fill="url(#surface)", stroke="none", filt="soft")
    )
    s.append(rect(vx, vy, vw, vh, rx=10, fill="none", stroke=th["border"], sw=1.5))
    s.append(rect(vx + 6, vy + 10, 4, vh - 20, rx=2, fill=obs, op=0.7))
    s.append(
        rect(
            vx + 14,
            vy + 9,
            26,
            15,
            rx=4,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    s.append(
        T(vx + 27, vy + 19.5, "H0", 10, 700, th["tmut"], mono=True, anchor="middle")
    )
    s.append(ic_approx(vx + 46, vy + 16, 18, obs))
    s.append(T(vx + 70, vy + 25, "other identities", 12, 600, th["tprim"], mono=True))
    s.append(
        T(
            vx + 70,
            vy + 40,
            "evidence only · no native authority",
            9.5,
            500,
            th["tmut"],
            italic=True,
        )
    )

    # ---- edge chips ----
    def echip(cx, cy, sq_hue, eyebrow, key, w=150):
        h = 22
        x, y = cx - w / 2, cy - h / 2
        return (
            rect(x - 1.5, y - 1.5, w + 3, h + 3, rx=8, fill=th["bg_bot"])
            + rect(x, y, w, h, rx=8, fill=th["surf_chip"], stroke=th["border"], sw=1)
            + rect(x + 7, y + 6, 10, 10, rx=2, fill=sq_hue)
            + T(
                x + 22,
                y + 15,
                eyebrow,
                9.5,
                700,
                semantic_text_color(th, sq_hue),
            )
            + T(
                x + 22 + len(eyebrow) * 6.3 + 8,
                y + 15,
                key,
                9,
                500,
                th["tmut"],
                mono=True,
            )
        )

    s.append(echip(320, 260, ctl, "", "negotiate", w=84))
    # Fork conditions are shown on the destination cards.

    # ---- legend ----
    ly = 500
    items = [
        (verm, "■", "HARD", "wire/core mismatch → reject"),
        (grn, "▶", "OPEN", "both checks → session"),
        (obs, "≈", "EVIDENCE", "no native authority"),
    ]
    lx = 40
    for hue, gly, concept, tail in items:
        text_color = semantic_text_color(th, hue)
        s.append(T(lx, ly + 4, gly, 10, 700, text_color))
        s.append(T(lx + 14, ly + 4, concept, 10, 700, text_color, track=0.4))
        s.append(T(lx + 14 + len(concept) * 7 + 6, ly + 4, tail, 9, 500, th["tmut"]))
        lx += 248
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 4. SAFETY FSM ─────────────────────────────
def fsm(th):
    W, H = 820, 586
    s = [svg_open(W, H, "fsm"), defs(th, include_fsm=True), background(th, W, H)]
    s.append(
        title_block(
            th,
            "PLANT ADMISSION · STATE MODEL",
            "PROPOSED B01 TARGET  ·  ATTRIBUTED WIRE CANDIDATES  ·  ESTOP LATCHES",
            W,
        )
    )
    # The long state-model heading uses the full title rail. Put the exact
    # candidate identity on its own rail below the header divider.
    s.append(sheet_meta(th, W - 28, 90, CURRENT_META))
    grn, amb, verm, pink, obs = (
        th["active"],
        th["hold"],
        th["action"],
        th["configfail"],
        th["observation"],
    )
    active_text = th["fsm_active_text"]
    hold_text = th["fsm_hold_text"]
    configfail_text = th["fsm_configfail_text"]
    action_text = th["fsm_action_text"]
    ink = th["fsm_hero_ink"]

    # mode-enum ribbon (top-right, under sheet-meta)
    rx0 = W - 28
    for label, fill, txt, filled in reversed(
        [
            ("init · reject", None, th["surf_chip"], None),
            ("active", th["fsm_active_badge"], th["fsm_active_badge_text"], True),
            ("hold", amb, hold_text, False),
            ("estop", verm, th["fsm_estop_badge_text"], True),
        ]
    ):
        pw = 10 + len(label) * 6.2
        rx0 -= pw
        if filled is True:
            s.append(rect(rx0, 60, pw, 18, rx=6, fill=fill))
        elif filled is None:
            s.append(rect(rx0, 60, pw, 18, rx=6, fill=txt, stroke=th["border"], sw=1))
            txt = th["tsec"]
        else:
            s.append(rect(rx0, 60, pw, 18, rx=6, fill="none", stroke=fill, sw=1.2))
        s.append(T(rx0 + pw / 2, 72.5, label, 9, 700, txt, anchor="middle", mono=True))
        rx0 -= 7

    def klabel(cx, cy, trigger, eyebrow=None, ehue=None, compact=False):
        if compact and eyebrow:
            w = round(len(eyebrow) * 6.0 + len(trigger) * 5.3 + 24)
            x, y = cx - w / 2, cy - 9
            return (
                rect(
                    x,
                    y,
                    w,
                    18,
                    rx=6,
                    fill=th["bg_bot"],
                    op=0.92,
                    stroke=th["border"],
                    sw=0.8,
                )
                + T(x + 8, y + 13, eyebrow, 9, 700, ehue)
                + T(
                    round(x + 8 + len(eyebrow) * 6.0 + 6),
                    y + 13,
                    trigger,
                    9,
                    500,
                    th["tmut"],
                    mono=True,
                )
            )
        w = round(max(len(trigger) * 5.3, (len(eyebrow) * 6.3 if eyebrow else 0)) + 16)
        h = 30 if eyebrow else 18
        x, y = cx - w / 2, cy - h / 2
        o = [
            rect(
                x,
                y,
                w,
                h,
                rx=6,
                fill=th["bg_bot"],
                op=0.92,
                stroke=th["border"],
                sw=0.8,
            )
        ]
        ty = y + 13
        if eyebrow:
            o.append(T(x + 8, ty, eyebrow, 9.5, 700, ehue, track=0.4))
            ty += 13
        o.append(T(x + 8, ty, trigger, 9, 500, th["tmut"], mono=True))
        return "".join(o)

    # ---- state geometry ----
    AC = (96, 150, 200, 72)  # ACTIVE  (96-296, 150-222) cy186
    HD = (430, 150, 200, 72)  # HOLD    (430-630)
    ES = (430, 330, 212, 86)  # ESTOP   (430-642, 330-416) cy373  HERO
    CF = (96, 330, 200, 72)  # CONFIG-FAIL-CLOSED
    GC = (400, 444, 260, 52)  # successful reset boundary / retired generation

    # ---- edges (painted first) ----
    s.append('<circle cx="110" cy="120" r="4" fill="%s"/>' % obs)
    s.append(
        '<circle cx="110" cy="120" r="7" fill="none" stroke="%s" stroke-width="1.3"/>'
        % obs
    )
    s.append(T(110, 108, "OPEN", 8.5, 700, th["tmut"], mono=True, anchor="middle"))
    s.append(
        path("M110,127 C110,100 500,100 500,150", stroke=amb, sw=2, marker="arrowHold")
    )  # E0 valid open→HOLD
    s.append(
        path(
            "M100,127 C58,127 58,366 96,366",
            stroke=pink,
            sw=2,
            dash="5 3",
            marker="arrowConfig",
        )
    )  # E0b invalid open→CONFIG
    s.append(
        path(
            "M214,150 C214,120 250,120 250,150",
            stroke=grn,
            sw=2.5,
            marker="arrowActive",
        )
    )  # E1 self
    s.append(
        path("M296,172 L430,172", stroke=amb, sw=2.5, marker="arrowHold")
    )  # E2 ACTIVE→HOLD
    s.append(
        path("M430,200 L296,200", stroke=grn, sw=2.5, marker="arrowActive")
    )  # E3 HOLD→ACTIVE
    # E4 ACTIVE→ESTOP (hero: halo + 4px busAction)
    s.append(
        path(
            "M296,206 L360,206 Q368,206 368,214 L368,360 Q368,368 376,368 L430,368",
            stroke=verm,
            sw=9,
            op=th["halo_op"],
            filt="halo",
        )
    )
    s.append(
        path(
            "M296,206 L360,206 Q368,206 368,214 L368,360 Q368,368 376,368 L430,368",
            stroke="url(#busAction)",
            sw=4,
            marker="arrowEstop",
        )
    )
    for ty in (250, 300, 350):
        s.append(line(363, ty, 373, ty, verm, 1, op=0.7))
    s.append(
        path("M530,222 L530,330", stroke=verm, sw=3.5, marker="arrowEstop")
    )  # E5 HOLD→ESTOP
    s.append(
        path(
            "M642,356 C680,356 680,392 642,392",
            stroke=verm,
            sw=3.5,
            marker="arrowEstop",
        )
    )  # E6 self latched
    # E7 reset retires the old generation; a fresh generation re-enters non-actuating HOLD.
    s.append(
        path("M536,416 L536,444", stroke=verm, sw=2.5, dash="4 3", marker="arrowEstop")
    )
    s.append(
        path(
            "M660,470 L704,470 Q712,470 712,462 L712,194 Q712,186 704,186 L630,186",
            stroke=amb,
            sw=2,
            dash="5 4",
            marker="arrowHold",
        )
    )
    s.append(
        path(
            "M170,402 C170,440 206,440 206,402",
            stroke=pink,
            sw=2,
            dash="5 3",
            marker="arrowConfig",
        )
    )  # E9 self

    # ---- state cards ----
    s.append(card(th, *AC, grn, "S1"))
    s.append(ic_play(AC[0] + AC[2] - 38, AC[1] + 9, 22, grn))
    s.append(T(AC[0] + 18, AC[1] + 34, "ACTIVE", 14, 700, th["tprim"]))
    s.append(
        T(AC[0] + 18, AC[1] + 50, "valid command · live authority", 10, 500, th["tsec"])
    )
    s.append(T(AC[0] + 18, AC[1] + 64, "Mode::Active", 9, 500, th["tmut"], mono=True))

    s.append(card(th, *HD, amb, "S2"))
    s.append(ic_pause(HD[0] + HD[2] - 38, HD[1] + 9, 22, amb))
    s.append(T(HD[0] + 18, HD[1] + 34, "HOLD", 14, 700, th["tprim"]))
    s.append(
        rect(
            HD[0] + 70, HD[1] + 24, 88, 15, rx=7, fill=th["surf_chip"], stroke=amb, sw=1
        )
    )
    s.append(
        T(HD[0] + 114, HD[1] + 34.5, "NON-LATCHING", 8, 700, hold_text, anchor="middle")
    )
    s.append(
        T(
            HD[0] + 18,
            HD[1] + 50,
            "non-actuating until all gates pass",
            10,
            500,
            th["tsec"],
        )
    )
    s.append(
        T(
            HD[0] + 18,
            HD[1] + 64,
            "bounded HOLD candidate · no action claim",
            9,
            500,
            th["tmut"],
            mono=True,
        )
    )

    s.append(card(th, *CF, pink, "S4", dashed=True))
    s.append(ic_warn(CF[0] + CF[2] - 38, CF[1] + 9, 22, pink))
    s.append(T(CF[0] + 18, CF[1] + 32, "CONFIG-FAIL-CLOSED", 12.5, 700, th["tprim"]))
    s.append(
        rect(
            CF[0] + 18,
            CF[1] + 40,
            96,
            15,
            rx=7,
            fill=th["surf_chip"],
            stroke=pink,
            sw=1,
        )
    )
    s.append(
        T(
            CF[0] + 66,
            CF[1] + 50.5,
            "safety_ok=false",
            8,
            700,
            configfail_text,
            anchor="middle",
            mono=True,
        )
    )
    s.append(T(CF[0] + 122, CF[1] + 51, "permanent", 9.5, 500, th["tsec"]))
    s.append(
        T(
            CF[0] + 18,
            CF[1] + 65,
            "HOLD candidate / no frame · no effect",
            8.5,
            500,
            th["tmut"],
            mono=True,
        )
    )

    # ESTOP hero (filled vermillion + glow + 4 corner lock-ticks)
    ex, ey, ew, eh = ES
    s.append(
        rect(
            ex,
            ey,
            ew,
            eh,
            rx=10,
            fill="url(#fsmAction)",
            stroke="#ffd9c2",
            sw=2,
            filt="glow",
        )
    )
    for lx, ly, dx, dy in [
        (ex, ey, 1, 1),
        (ex + ew, ey, -1, 1),
        (ex, ey + eh, 1, -1),
        (ex + ew, ey + eh, -1, -1),
    ]:
        s.append(
            path(
                f"M{lx + 9 * dx},{ly} L{lx},{ly} L{lx},{ly + 9 * dy}",
                stroke="#ffd9c2",
                sw=1.6,
                op=0.9,
            )
        )
    s.append(rect(ex + 14, ey + 11, 26, 15, rx=4, fill=th["surf_chip"]))
    s.append(
        T(ex + 27, ey + 21.5, "S3", 10, 700, th["tsec"], mono=True, anchor="middle")
    )
    s.append(ic_octagon(ex + ew - 40, ey + 10, 24, ink))
    s.append(T(ex + 18, ey + 44, "ESTOP", 15, 800, ink))
    s.append(T(ex + 18, ey + 61, "LATCHED · bounded ESTOP candidate", 10.5, 600, ink))
    s.append(
        T(ex + 18, ey + 77, "reset never restores authority", 9.5, 500, ink, mono=True)
    )

    # Successful reset is a generation cut, not a transition inside the old session.
    s.append(card(th, *GC, verm, "G2", dashed=True))
    s.append(
        T(GC[0] + 46, GC[1] + 23, "BODY-LOCAL / OOB RESET = CUT", 11, 700, th["tprim"])
    )
    s.append(
        T(
            GC[0] + 18,
            GC[1] + 40,
            "retire gen · authority + lease · streams · buffer",
            8,
            500,
            th["tmut"],
            mono=True,
        )
    )

    # ---- edge labels ----
    s.append(
        klabel(
            300, 108, "valid config · governor open", "→ HOLD", hold_text, compact=True
        )
    )
    s.append(
        klabel(
            250,
            134,
            "fresh sensor · live authority",
            "ACTIVE",
            active_text,
            compact=True,
        )
    )
    s.append(klabel(363, 172, "invalid or stale", "HOLD", hold_text, compact=True))
    s.append(
        klabel(
            363,
            238,
            "sensor + live lease + active cmd",
            "LOCAL GOVERNOR GATES",
            active_text,
            compact=True,
        )
    )
    s.append(
        klabel(
            476,
            282,
            "geofence breach · reported loss burst · sustained sensor silence",
            "ESTOP TRIGGERS",
            action_text,
        )
    )
    s.append(
        klabel(
            700,
            318,
            "exact replay · no new latch",
            "LATCHED",
            action_text,
            compact=True,
        )
    )
    s.append(
        klabel(
            670, 430, "fresh generation → HOLD", "RESET CUT", hold_text, compact=True
        )
    )
    s.append(
        klabel(
            140,
            282,
            "invalid channel / config",
            "MISCONFIG",
            configfail_text,
            compact=True,
        )
    )

    # ---- invariant band ----
    iy = 526
    s.append(
        rect(28, iy, W - 56, 44, rx=8, fill=th["surf_chip"], stroke=th["border"], sw=1)
    )
    s.append(rect(28, iy, 4, 44, rx=2, fill=verm))
    s.append(
        T(
            44,
            iy + 17,
            "INVARIANT · Output is only a bounded wire candidate. The body selects an installed plant-profile action. NCP defines no universal zero.",
            8.5,
            500,
            th["tsec"],
            italic=True,
        )
    )
    s.append(
        T(
            44,
            iy + 33,
            "Unattributable envelope or no representable candidate → local latch + error / no frame. No protocol result proves physical effect.",
            8.5,
            500,
            th["tsec"],
            italic=True,
        )
    )
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 5. SEQUENCE ─────────────────────────────
def sequence(th):
    W, H = 820, 640
    s = [svg_open(W, H, "sequence"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "SIMULATION SESSION",
            "PROPOSED B01 TARGET  ·  OPEN → STEP / RUN → CLOSE  ·  SIMULATION ONLY",
            W,
        )
    )
    # The long sequence heading uses the full title rail. Put the exact
    # candidate identity on its own rail below the header divider.
    s.append(sheet_meta(th, W - 28, 88, CURRENT_META))
    ctl, obs, ctr, verm, grn, pink = (
        th["control"],
        th["observation"],
        th["contract"],
        th["action"],
        th["active"],
        th["configfail"],
    )
    CLx, SVx = 246, 574

    # phase-group frames (recessive wells)
    for fy, fh, tag, thue, note in [
        (
            176,
            124,
            "OPEN",
            ctl,
            f"canonical {WIRE_MAJOR} or {WIRE_MAJOR}.<minor> + exact stable core",
        ),
        (
            320,
            168,
            "loop  [per operation]",
            verm,
            "step / run ⟳ result · provenance every response",
        ),
        (508, 92, "CLOSE", ctl, "fenced mutation + receipt"),
    ]:
        s.append(
            rect(
                210,
                fy,
                400,
                fh,
                rx=10,
                fill=th["surf_chip"],
                op=0.32,
                stroke=th["border"],
                sw=0.8,
                dash="2 3",
            )
        )
        tw = 22 + len(tag) * 6.0
        s.append(rect(210, fy, tw, 18, rx=6, fill=thue))
        s.append(T(218, fy + 13, tag, 9.5, 700, contrast_ink(thue), mono=True))
        s.append(T(210 + tw + 10, fy + 13, note, 9, 500, th["tmut"], italic=True))

    # lifelines
    s.append(line(CLx, 156, CLx, 604, th["border"], 1.5, dash="4 4", op=0.7))
    s.append(line(SVx, 156, SVx, 604, th["border"], 1.5, dash="4 4", op=0.7))
    # activation bars per phase
    for ay, ah in [(208, 92), (360, 124), (532, 64)]:
        for lx in (CLx, SVx):
            s.append(
                rect(
                    lx - 5,
                    ay,
                    10,
                    ah,
                    rx=3,
                    fill=th["surf_chip"],
                    stroke=th["border"],
                    sw=1,
                )
            )

    # actor cards
    s.append(card(th, 156, 92, 180, 64, ctl, "C0"))
    s.append(ic_terminal(300, 104, 22, ctl))
    s.append(T(200, 120, "CLIENT", 14, 700, th["tprim"]))
    s.append(T(200, 136, "authorized simulation caller", 10, 500, th["tsec"]))
    s.append(card(th, 484, 92, 180, 64, obs, "S0"))
    s.append(ic_wave(628, 104, 22, obs))
    s.append(T(528, 120, "RESPONDER", 14, 700, th["tprim"]))
    s.append(T(528, 136, "bounded simulation service", 10, 500, th["tsec"]))

    # message chip helper (2-line: eyebrow + mono key)
    def mchip(cx, cy, desig, hue, eyebrow, key, w):
        x, y = cx - w / 2, cy - 15
        return (
            rect(x - 1.5, y - 1.5, w + 3, 33, rx=8, fill=th["bg_bot"])
            + rect(x, y, w, 30, rx=8, fill=th["surf_chip"], stroke=th["border"], sw=1)
            + rect(x + 7, y + 7, 16, 16, rx=3, fill=hue)
            + T(
                x + 15,
                y + 18.5,
                desig,
                8.5,
                700,
                contrast_ink(hue),
                mono=True,
                anchor="middle",
            )
            + T(
                x + 30,
                y + 13,
                eyebrow,
                9.5,
                700,
                semantic_text_color(th, hue),
                track=0.4,
            )
            + T(x + 30, y + 24, key, 8.5, 500, th["tmut"], mono=True)
        )

    # OPEN gate note on SERVER lifeline
    s.append(
        rect(
            486,
            230,
            172,
            44,
            rx=10,
            fill="url(#surface)",
            stroke=th["border"],
            sw=1.25,
            filt="soft",
        )
    )
    s.append(rect(486 + 6, 230 + 8, 4, 28, rx=2, fill=ctr))
    s.append(
        T(
            498,
            246,
            f"canonical wire HARD · major={WIRE_MAJOR}",
            8,
            500,
            th["tmut"],
            mono=True,
        )
    )
    s.append(
        T(
            498,
            262,
            "stable_core HARD · compact hash diagnostic",
            8,
            500,
            th["tmut"],
            mono=True,
        )
    )

    # E1 OpenSession →
    s.append(line(251, 214, 569, 214, ctl, 2.5, marker="arrowControl"))
    s.append(
        mchip(
            410,
            214,
            "C1",
            ctl,
            "OpenSession  →",
            "version · stable core · security profile/digest",
            300,
        )
    )
    # E2 SessionOpened ← (+ outcome pills)
    s.append(line(569, 288, 251, 288, ctl, 2.5, dash="4 4", marker="replyControl"))
    s.append(
        mchip(
            410,
            288,
            "C2",
            ctl,
            "SessionOpened  ←",
            "session{generation} · state_version · provenance",
            300,
        )
    )
    s.append(rect(282, 302, 132, 16, rx=6, fill=grn))
    s.append(
        T(
            348,
            313,
            "ok=true → opens",
            8.5,
            700,
            contrast_ink(grn),
            anchor="middle",
            mono=True,
        )
    )
    s.append(rect(420, 302, 150, 16, rx=6, fill="none", stroke=pink, sw=1.2))
    s.append(
        T(
            495,
            313,
            "ok=false → NO session",
            8.5,
            700,
            semantic_text_color(th, pink),
            anchor="middle",
            mono=True,
        )
    )
    # E3 StepRequest / RunRequest →
    s.append(line(251, 372, 569, 372, ctl, 2.5, marker="arrowControl"))
    s.append(
        mchip(
            410,
            372,
            "C3",
            ctl,
            "StepRequest / RunRequest  →",
            "session · operation · authority · stimulus",
            300,
        )
    )

    # E4 ObservationFrame ← (CONTROL reply, not plant authority)
    s.append(line(569, 432, 251, 432, ctl, 2.5, dash="4 4", marker="replyControl"))
    cw, ch, cy0 = 236, 38, 414
    cx0 = 410 - cw / 2
    s.append(rect(cx0 - 1.5, cy0 - 1.5, cw + 3, ch + 3, rx=10, fill=th["bg_bot"]))
    s.append(rect(cx0, cy0, cw, ch, rx=10, fill="url(#surface)", stroke=ctl, sw=1.5))
    s.append(rect(cx0, cy0, cw, ch, rx=10, fill=ctl, op=th["wash_op"]))
    s.append(rect(cx0 + 8, cy0 + 8, 16, 16, rx=3, fill=ctl))
    s.append(
        T(
            cx0 + 16,
            cy0 + 19.5,
            "O1",
            8.5,
            700,
            contrast_ink(ctl),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            cx0 + 30,
            cy0 + 15,
            "ObservationFrame  ←",
            10,
            700,
            semantic_text_color(th, ctl),
            track=0.3,
        )
    )
    s.append(
        T(
            cx0 + 30,
            cy0 + 27,
            "session · request position · terminal result",
            8.5,
            500,
            th["tsec"],
            mono=True,
        )
    )
    # provenance invariant pills
    py = cy0 + ch + 5
    s.append(rect(254, py, 160, 17, rx=6, fill=grn))
    s.append(
        T(
            334,
            py + 12,
            "is_simulation_output = true",
            8.5,
            700,
            contrast_ink(grn),
            anchor="middle",
            mono=True,
        )
    )
    s.append(rect(420, py, 150, 17, rx=6, fill=pink))
    s.append(
        T(
            493,
            py + 12,
            "calibrated_posterior = false",
            8.5,
            700,
            contrast_ink(pink),
            anchor="middle",
            mono=True,
        )
    )
    s.append(
        T(
            410,
            py + 30,
            "fixed provenance invariants on every frame — the honesty boundary",
            9,
            500,
            th["tmut"],
            italic=True,
            anchor="middle",
        )
    )

    # E5 CloseSession → / E6 SessionClosed ←
    s.append(line(251, 540, 569, 540, ctl, 2.5, marker="arrowControl"))
    s.append(
        mchip(
            410,
            540,
            "C4",
            ctl,
            "CloseSession  →",
            "session · operation · authority",
            230,
        )
    )
    s.append(line(569, 580, 251, 580, ctl, 2.5, dash="4 4", marker="replyControl"))
    s.append(
        mchip(
            410,
            580,
            "C5",
            ctl,
            "SessionClosed  ←",
            "session · receipt · terminal",
            250,
        )
    )

    # legend
    ly = 618
    s.append(line(40, ly, 64, ly, ctl, 2.5, marker="arrowControl"))
    s.append(T(72, ly + 4, "CONTROL · request/reply", 9, 600, th["tsec"]))
    s.append(line(300, ly, 324, ly, ctl, 2.5, dash="4 4", marker="replyControl"))
    s.append(
        T(
            332,
            ly + 4,
            "CONTROL reply · provenance-bearing simulation result",
            9,
            600,
            th["tsec"],
        )
    )
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 6. BODY ADMISSION ─────────────────────────────
def admission(th):
    W, H = 980, 600
    s = [svg_open(W, H, "admission"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "BODY COMMAND ADMISSION",
            "PROPOSED B01 TARGET · BOUND ONCE · PREALLOCATED LATCH",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))

    control = th["control"]
    active = th["active"]
    hold = th["hold"]
    action = th["action"]
    muted = th["observation"]

    def stage(x, rail, designator, heading, detail, note):
        out = [card(th, x, 130, 166, 86, rail, designator)]
        out.append(T(x + 18, 165, heading, 12, 700, th["tprim"]))
        out.append(T(x + 18, 184, detail, 9, 600, th["tsec"], mono=True))
        out.append(T(x + 18, 200, note, 9, 500, th["tmut"], mono=True))
        return "".join(out)

    stages = (
        (28, control, "B0", "RAW BOUNDS", "checked size · class", "no semantic state"),
        (
            218,
            control,
            "A1",
            "AUTHENTICATE",
            "principal · manifest",
            "snapshot capability",
        ),
        (
            408,
            active,
            "D1",
            "DECODE ONCE",
            "prepared layout",
            "Init / unknown → reject",
        ),
        (
            598,
            hold,
            "C1",
            "CONTEXT / LOOKUP",
            "route · session · position",
            "publisher · digest",
        ),
        (
            788,
            active,
            "S1",
            "GRANT / CHECK",
            "range · replay · no-reuse",
            "action · lease · expiry",
        ),
    )
    for values in stages:
        s.append(stage(*values))

    s.append(line(194, 173, 218, 173, control, 2.5, marker="arrowControl"))
    s.append(line(384, 173, 408, 173, control, 2.5, marker="arrowControl"))
    s.append(line(574, 173, 598, 173, active, 2.5, marker="arrowActive"))
    s.append(line(764, 173, 788, 173, active, 2.5, marker="arrowActive"))

    s.append(card(th, 218, 326, 220, 92, muted, "I1", dashed=True))
    s.append(T(268, 354, "INVALIDATING STATE", 12, 700, th["tprim"]))
    s.append(
        T(
            236,
            375,
            "lease · security · HOLD · ESTOP",
            9,
            600,
            th["tsec"],
            mono=True,
        )
    )
    s.append(T(236, 393, "handover · retirement", 9, 500, th["tmut"], mono=True))

    s.append(card(th, 468, 326, 210, 92, action, "L1"))
    s.append(ic_octagon(482, 345, 26, action))
    s.append(T(520, 354, "LOCAL ESTOP LATCH", 12.5, 800, th["tprim"]))
    s.append(
        T(
            486,
            375,
            "authorized · fresh · profile-bound",
            9,
            600,
            th["tsec"],
            mono=True,
        )
    )
    s.append(
        T(
            486,
            393,
            "new · stale · conflict",
            9,
            500,
            th["tmut"],
            mono=True,
        )
    )
    s.append(
        path(
            "M812,216 L812,258 Q812,266 804,266 L581,266 Q573,266 573,326",
            stroke=action,
            sw=3,
            marker="arrowEstop",
        )
    )

    s.append(card(th, 708, 306, 246, 132, action, "G1"))
    s.append(ic_lock(724, 326, 28, action))
    s.append(T(764, 340, "BODY EFFECT GATE", 14, 800, th["tprim"]))
    s.append(
        T(726, 366, "installed action → driver fence", 9, 600, th["tsec"], mono=True)
    )
    s.append(
        T(
            726,
            384,
            "token → one in-flight lane",
            9,
            600,
            th["tsec"],
            mono=True,
        )
    )
    s.append(
        T(
            726,
            402,
            "ESTOP latch orders with invalidation",
            9,
            500,
            th["tmut"],
            mono=True,
        )
    )
    s.append(
        T(
            726,
            420,
            "completion terminalizes · then release",
            9,
            500,
            th["tmut"],
            mono=True,
        )
    )

    s.append(
        path(
            "M871,216 L871,274 Q871,282 863,282 L839,282 Q831,282 831,306",
            stroke=active,
            sw=3,
            marker="arrowActive",
        )
    )
    s.append(
        path(
            "M328,418 L328,448 Q328,456 336,456 L823,456 Q831,456 831,448 L831,438",
            stroke=muted,
            sw=2.5,
            marker="arrowMut",
        )
    )
    s.append(line(678, 388, 708, 388, action, 2.5, marker="arrowEstop"))

    s.append(
        rect(
            28,
            478,
            924,
            78,
            rx=10,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    s.append(rect(28, 478, 5, 78, rx=2, fill=action))
    s.append(
        T(
            48,
            500,
            "ORDERING",
            10,
            800,
            semantic_text_color(th, action),
            track=1.0,
        )
    )
    s.append(
        T(
            128,
            500,
            "Grant reserves completion. One conflict attribution is fixed.",
            10,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            128,
            522,
            "Per-stream high-water and grant tombstones bind no-reuse.",
            10,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            48,
            544,
            "BOUNDARY · Invalidation orders with token use or latching. Handoff proves software admission only.",
            9.5,
            500,
            th["tmut"],
            italic=True,
        )
    )
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 7. PROTOCOL OVERVIEW ─────────────────────────────
def overview(th):
    W, H = 1060, 684
    s = [svg_open(W, H, "overview"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "NCP FUNCTION",
            "FIVE SHARED GATES  ·  ACTION ADDS THE BODY EFFECT GATE  ·  FOUR PLANES",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))

    control = th["control"]
    perception = th["perception"]
    action = th["action"]
    observation = th["observation"]
    active = th["active"]
    contract = th["contract"]

    stage_x = (28, 232, 436, 640, 844)
    stages = (
        (
            "G0",
            control,
            "BOUND RAW BYTES",
            "frame · depth · members",
            "before semantic allocation",
        ),
        (
            "G1",
            control,
            "AUTHENTICATE",
            "transport principal · manifest",
            "audience · route · profile",
        ),
        (
            "G2",
            contract,
            "WIRE + CORE",
            f"canonical {WIRE_MAJOR}.x · exact stable core",
            "unknown / default → reject",
        ),
        (
            "G3",
            active,
            "SESSION + STREAM",
            "generation · epoch · position",
            "lease · deadline · no-reuse",
        ),
        (
            "G4",
            active,
            "TYPED DELIVERY",
            "prepared layout · finite queue",
            "callback after admission",
        ),
    )

    for index, (designator, hue, heading, detail, note) in enumerate(stages):
        x = stage_x[index]
        s.append(card(th, x, 108, 188, 104, hue, designator))
        s.append(T(x + 18, 147, heading, 11.5, 750, th["tprim"]))
        s.append(T(x + 18, 170, detail, 8.5, 600, th["tsec"], mono=True))
        s.append(T(x + 18, 191, note, 8.5, 500, th["tmut"], mono=True))
        if index < len(stages) - 1:
            marker = "arrowContract" if index == 1 else "arrowActive"
            hue_out = contract if index == 1 else active
            s.append(
                line(x + 188, 160, stage_x[index + 1], 160, hue_out, 2.5, marker=marker)
            )

    lane_text_hues = {
        hue: semantic_text_color(th, hue)
        for hue in (control, perception, action, observation, contract, active)
    }

    def lane(y, designator, hue, name, actors, policy, outcome, *, hero=False):
        x, w, h = 28, 1004, 54
        fill = "url(#surface)" if hero else th["surf_chip"]
        s.append(
            rect(
                x,
                y,
                w,
                h,
                rx=9,
                fill=fill,
                stroke=hue if hero else th["border"],
                sw=1.6 if hero else 1,
                filt="glow" if hero else None,
            )
        )
        if hero:
            s.append(rect(x, y, w, h, rx=9, fill=hue, op=th["wash_op"]))
        s.append(rect(x + 7, y + 9, 4, h - 18, rx=2, fill=hue))
        s.append(rect(x + 18, y + 17, 26, 20, rx=4, fill=hue))
        badge_ink = contrast_ink(hue)
        s.append(
            T(
                x + 31,
                y + 31,
                designator,
                9.5,
                800,
                badge_ink,
                mono=True,
                anchor="middle",
            )
        )
        s.append(T(x + 58, y + 31, name, 11, 800, lane_text_hues[hue], track=0.8))
        s.append(T(x + 214, y + 31, actors, 9.5, 600, th["tsec"]))
        s.append(T(x + 505, y + 31, policy, 9, 500, th["tmut"], mono=True))
        outcome_w = 166
        outcome_x = x + w - outcome_w - 14
        s.append(
            rect(
                outcome_x,
                y + 13,
                outcome_w,
                28,
                rx=8,
                fill=th["surf_chip"],
                stroke=hue,
                sw=1.2,
            )
        )
        s.append(
            T(
                outcome_x + outcome_w / 2,
                y + 31,
                outcome,
                8.5,
                700,
                lane_text_hues[hue],
                mono=True,
                anchor="middle",
            )
        )

    lane(
        252,
        "C1",
        control,
        "CONTROL",
        "commander ⇄ body",
        "bounded · reject overflow",
        "request / reply",
    )
    lane(
        316,
        "P1",
        perception,
        "PERCEPTION",
        "body → commander",
        "replace latest · expose loss",
        "lossy stream",
    )
    lane(
        380,
        "A1",
        action,
        "ACTION",
        "commander / operator → body",
        "severity: ESTOP > HOLD > Active",
        "BODY EFFECT GATE",
        hero=True,
    )
    lane(
        444,
        "O1",
        observation,
        "OBSERVATION",
        "body → read-only observer",
        "drop oldest · count gaps",
        "no authority",
    )

    band_y = 530
    s.append(
        rect(
            28,
            band_y,
            W - 56,
            122,
            rx=10,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    s.append(rect(28, band_y, 5, 122, rx=2, fill=action))
    rows = (
        (
            "STATUS",
            action,
            "Direct stable-1.0 Zenoh cannot bind the verified remote principal. The production-secure profile is unavailable.",
        ),
        (
            "BOUNDARY",
            contract,
            "NCP defines a contract and admission rules. It is not a broker, actuator, or physical-safety certification.",
        ),
        (
            "EVIDENCE",
            observation,
            "Local tests do not complete independent peers, live security, performance, provenance, or role qualification.",
        ),
    )
    for index, (label, hue, text) in enumerate(rows):
        y = band_y + 27 + index * 34
        text_hue = lane_text_hues.get(hue, hue)
        s.append(T(48, y, label, 9.5, 800, text_hue, track=0.8))
        s.append(T(136, y, text, 9.5, 600, th["tsec"]))
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 8. LOW-OVERHEAD RUNTIME ─────────────────────────────
def runtime(th):
    W, H = 1060, 650
    s = [svg_open(W, H, "runtime"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "LOW-OVERHEAD RUNTIME",
            "PREPARE ONCE  ·  BOUND AND DECODE ONCE  ·  SHORT OWNER TRANSITION",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))

    control = th["control"]
    active = th["active"]
    hold = th["hold"]
    action = th["action"]
    observation = th["observation"]
    contract = th["contract"]

    s.append(card(th, 28, 102, 1004, 78, contract, "P0"))
    s.append(ic_gauge(50, 130, 24, contract))
    s.append(T(86, 134, "PREPARE ONCE", 13, 800, th["tprim"], track=0.5))
    s.append(
        T(
            222,
            134,
            "manifest · security snapshot · routes · layouts · queue and deadline profiles",
            9.5,
            600,
            th["tsec"],
            mono=True,
        )
    )
    s.append(
        T(
            86,
            158,
            "compile immutable handles and bounded shared tables before publishers, subscriptions, callbacks, or actuator resources",
            9,
            500,
            th["tmut"],
            mono=True,
        )
    )

    stage_x = (28, 202, 376, 550, 724, 898)
    stages = (
        ("B0", control, "RAW BOUND", "checked bytes", "scratch only"),
        ("A1", control, "CAPABILITY", "snapshot lookup", "no caller evidence"),
        ("D2", active, "DECODE ONCE", "prepared layout", "one owned frame"),
        ("L3", hold, "EXACT LOOKUP", "route · session · position", "indexed state"),
        ("O4", action, "OWNER STEP", "fixed transition", "short lock"),
        ("H5", active, "HANDOFF", "bounded plane queue", "external work unlocked"),
    )
    for index, (designator, hue, heading, detail, note) in enumerate(stages):
        x = stage_x[index]
        s.append(card(th, x, 230, 150, 96, hue, designator, glow=index == 4))
        s.append(T(x + 18, 268, heading, 10.5, 800, th["tprim"]))
        s.append(T(x + 18, 289, detail, 8, 600, th["tsec"], mono=True))
        s.append(T(x + 18, 307, note, 8, 500, th["tmut"], mono=True))
        if index < len(stages) - 1:
            marker = "arrowEstop" if index == 3 else "arrowActive"
            hue_out = action if index == 3 else active
            s.append(
                line(x + 150, 278, stage_x[index + 1], 278, hue_out, 2.5, marker=marker)
            )

    for target_x in (277, 451, 625):
        s.append(
            path(
                f"M{target_x},180 L{target_x},214 Q{target_x},222 {target_x + 8},222 L{target_x + 8},230",
                stroke=contract,
                sw=1.5,
                dash="4 3",
                marker="arrowContract",
            )
        )

    s.append(line(742, 340, 856, 340, action, 2.5))
    s.append(line(742, 334, 742, 346, action, 2.5))
    s.append(line(856, 334, 856, 346, action, 2.5))
    s.append(
        T(
            799,
            360,
            "owner lock only",
            8.5,
            700,
            semantic_text_color(th, action),
            mono=True,
            anchor="middle",
        )
    )

    panels = (
        (
            28,
            control,
            "HOT PATH EXCLUDES",
            "manifest or profile parsing",
            "storage · backend · device calls",
        ),
        (
            376,
            contract,
            "STATE SHAPE",
            "shared fixed-capacity tables",
            "no service object per session",
        ),
        (
            724,
            observation,
            "PLANE ISOLATION",
            "finite queue for each plane",
            "no borrowing action capacity",
        ),
    )
    for index, (x, hue, heading, detail, note) in enumerate(panels):
        s.append(card(th, x, 390, 308, 96, hue, f"R{index + 1}"))
        s.append(T(x + 50, 423, heading, 11, 800, th["tprim"]))
        s.append(T(x + 20, 449, detail, 9, 600, th["tsec"], mono=True))
        s.append(T(x + 20, 468, note, 9, 500, th["tmut"], mono=True))

    band_y = 518
    s.append(
        rect(
            28,
            band_y,
            W - 56,
            104,
            rx=10,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    s.append(rect(28, band_y, 5, 104, rx=2, fill=active))
    s.append(
        T(
            48,
            band_y + 24,
            "LATENCY",
            9.5,
            800,
            semantic_text_color(th, active),
            track=0.8,
        )
    )
    s.append(
        T(
            134,
            band_y + 24,
            "T_hot = T_bound + T_auth + T_decode + T_lookup + T_owner + T_handoff",
            10,
            700,
            th["tprim"],
            mono=True,
        )
    )
    s.append(
        T(
            48,
            band_y + 52,
            "MEMORY",
            9.5,
            800,
            semantic_text_color(th, contract),
            track=0.8,
        )
    )
    s.append(
        T(
            134,
            band_y + 52,
            "M_NCP,bounded ≤ M_prepared + M_step,total + M_ext,total + M_aux",
            10,
            700,
            th["tprim"],
            mono=True,
        )
    )
    s.append(
        T(
            48,
            band_y + 82,
            "BOUNDARY · Every term uses a finite B03 profile and checked arithmetic. These are symbolic targets, not measurements.",
            9.0,
            500,
            th["tmut"],
            italic=True,
        )
    )
    s.append("</svg>")
    return "".join(s)


# ───────────────────────────── 9. LIFECYCLE OWNER ─────────────────────────────
def lifecycle(th):
    W, H = 1060, 764
    s = [svg_open(W, H, "lifecycle"), defs(th), background(th, W, H)]
    s.append(
        title_block(
            th,
            "SESSION LIFECYCLE OWNER",
            "ONE SLOT PER NAMESPACE  ·  EXACT RETRY  ·  NO NEW OPERATION AFTER AMBIGUITY",
            W,
        )
    )
    s.append(sheet_meta(th, W - 28, 48, CURRENT_META))

    control = th["control"]
    active = th["active"]
    hold = th["hold"]
    action = th["action"]
    observation = th["observation"]
    contract = th["contract"]

    state_x = (38, 286, 534, 782)
    state_data = (
        ("F0", observation, "FREE", "no lifecycle slot", "no external effect"),
        ("P1", control, "PENDING", "durable reservation", "lineage + capacity held"),
        ("A2", hold, "AMBIGUOUS", "effect is unknown", "same operation fenced"),
        (
            "T3",
            active,
            "TERMINAL COMMIT",
            "result + high-water durable",
            "slot release is atomic",
        ),
    )

    s.append(line(218, 178, 286, 178, control, 3, marker="arrowControl"))
    s.append(line(466, 178, 534, 178, hold, 3, marker="arrowHold"))
    s.append(line(714, 178, 782, 178, active, 3, marker="arrowActive"))
    s.append(
        path(
            "M466,138 L490,138 Q500,138 500,128 L500,110 Q500,100 510,100 L850,100 Q860,100 860,110 L860,128",
            stroke=active,
            sw=2.2,
            marker="arrowActive",
        )
    )
    s.append(
        T(
            650,
            94,
            "definitive authenticated result",
            8.5,
            700,
            semantic_text_color(th, active),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            252,
            166,
            "reserve",
            8,
            700,
            semantic_text_color(th, control),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            500,
            166,
            "unknown",
            8,
            700,
            semantic_text_color(th, hold),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            748,
            166,
            "reconcile",
            8,
            700,
            semantic_text_color(th, active),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        path(
            "M872,228 L872,262 Q872,274 860,274 L140,274 Q128,274 128,262 L128,228",
            stroke=control,
            sw=2.2,
            marker="arrowControl",
        )
    )
    s.append(
        T(
            530,
            267,
            "publish retained result + high-water · release active slot",
            8.5,
            700,
            semantic_text_color(th, control),
            mono=True,
            anchor="middle",
        )
    )

    for index, (designator, hue, heading, detail, note) in enumerate(state_data):
        x = state_x[index]
        s.append(card(th, x, 128, 180, 100, hue, designator, glow=index == 2))
        s.append(T(x + 18, 166, heading, 13, 800, th["tprim"]))
        s.append(T(x + 18, 190, detail, 9, 600, th["tsec"], mono=True))
        s.append(T(x + 18, 210, note, 8.5, 500, th["tmut"], mono=True))

    s.append(
        T(
            128,
            301,
            "capacity failure → reject · no state · no effect",
            8.5,
            600,
            semantic_text_color(th, observation),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            530,
            301,
            "different coordinate or bytes → reject · no mutation",
            8.5,
            700,
            semantic_text_color(th, action),
            mono=True,
            anchor="middle",
        )
    )
    s.append(
        T(
            872,
            301,
            "exact retry → retained-pool result",
            8.5,
            700,
            semantic_text_color(th, active),
            mono=True,
            anchor="middle",
        )
    )

    s.append(rect(38, 322, 480, 62, rx=9, fill=th["surf_chip"], stroke=active, sw=1.2))
    s.append(rect(45, 333, 4, 40, rx=2, fill=active))
    s.append(
        T(
            62,
            346,
            "CURRENT POLICY",
            9.5,
            800,
            semantic_text_color(th, active),
            track=0.8,
        )
    )
    s.append(
        T(
            184,
            346,
            "gates result disclosure and every widening transition",
            9,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            62,
            368,
            "rotation cannot rekey, reexecute, or alter retained evidence",
            8.5,
            500,
            th["tmut"],
            mono=True,
        )
    )

    s.append(rect(542, 322, 480, 62, rx=9, fill=th["surf_chip"], stroke=action, sw=1.2))
    s.append(rect(549, 333, 4, 40, rx=2, fill=action))
    s.append(
        T(
            566,
            346,
            "RESTRICTIVE CLEANUP",
            9.5,
            800,
            semantic_text_color(th, action),
            track=0.8,
        )
    )
    s.append(
        T(
            726,
            346,
            "continues after initiating authority is revoked",
            9,
            600,
            th["tsec"],
        )
    )
    s.append(
        T(
            566,
            368,
            "current policy cannot erase required reconciliation or retirement",
            8.5,
            500,
            th["tmut"],
            mono=True,
        )
    )

    store_x = (28, 282, 536, 790)
    stores = (
        (
            "C0",
            contract,
            "PREPARED CONTEXT",
            "exact identity + route bytes",
            "content address + durable ref",
        ),
        (
            "N1",
            control,
            "NAMESPACE SLOT",
            "≤ 1 active lifecycle mutation",
            "prior generation retained",
        ),
        (
            "R2",
            active,
            "TERMINAL RESULT POOL",
            "finite count + byte profile",
            "retired never reexecutes",
        ),
        (
            "O3",
            hold,
            "ORDINAL HIGH-WATER",
            "issuer epoch + checked ordinal",
            "overflow seals the epoch",
        ),
    )
    s.append(line(258, 458, 282, 458, contract, 2.2, marker="arrowContract"))
    s.append(line(512, 458, 536, 458, active, 2.2, marker="arrowActive"))
    s.append(line(766, 458, 790, 458, hold, 2.2, marker="arrowHold"))
    for index, (designator, hue, heading, detail, note) in enumerate(stores):
        x = store_x[index]
        s.append(card(th, x, 410, 230, 100, hue, designator))
        s.append(T(x + 18, 448, heading, 10.5, 800, th["tprim"]))
        s.append(T(x + 18, 472, detail, 8.5, 600, th["tsec"], mono=True))
        s.append(T(x + 18, 492, note, 8.5, 500, th["tmut"], mono=True))

    band_y = 546
    s.append(
        rect(
            28,
            band_y,
            W - 56,
            176,
            rx=10,
            fill=th["surf_chip"],
            stroke=th["border"],
            sw=1,
        )
    )
    s.append(rect(28, band_y, 5, 176, rx=2, fill=contract))
    rules = (
        (
            "SINGLE FLIGHT",
            "N_active(realm, kind, logical_id) ≤ 1",
            control,
        ),
        (
            "EXACT RETRY",
            "retry ⇔ c = cᵣ ∧ b = bᵣ ∧ k = kᵣ ∧ o = oᵣ",
            active,
        ),
        (
            "NO REUSE",
            "o_high = 0 initially  ·  o_next = checked_add(o_high, 1)  ·  overflow ⇒ seal epoch",
            hold,
        ),
        (
            "SERVICE SHAPE",
            "threads/session = sockets/session = dedicated stores/session = 0",
            observation,
        ),
    )
    for index, (label, formula, hue) in enumerate(rules):
        y = band_y + 29 + index * 34
        s.append(T(48, y, label, 9.5, 800, semantic_text_color(th, hue), track=0.7))
        s.append(T(190, y, formula, 10, 700, th["tprim"], mono=True))
    s.append(
        T(
            48,
            band_y + 158,
            "BOUNDARY · B03 selects every numeric ceiling, durable store, atomicity profile, rollover proof, and retention interval.",
            9.2,
            500,
            th["tmut"],
            italic=True,
        )
    )
    s.append("</svg>")
    return "".join(s)


DIAGRAMS = {
    "overview": overview,
    "topology": topology,
    "ecosystem": ecosystem,
    "versioning": versioning,
    "fsm": fsm,
    "sequence": sequence,
    "admission": admission,
    "runtime": runtime,
    "lifecycle": lifecycle,
}

DIAGRAM_OWNERS = {
    "overview": ROOT / "README.md",
    "topology": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
    "ecosystem": ROOT
    / "docs"
    / "handoff"
    / "NCP_V1_0_ECOSYSTEM_FINALIZATION_BLUEPRINT.md",
    "versioning": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
    "fsm": ROOT / "RESILIENCE.md",
    "sequence": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
    "admission": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
    "runtime": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
    "lifecycle": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
}

PUBLIC_SVG_PATHS = (
    ROOT / "assets" / "logo-light.svg",
    ROOT / "assets" / "logo-dark.svg",
    *(
        ROOT / "docs" / "diagrams" / f"{name}-{theme}.svg"
        for name in DIAGRAMS
        for theme in ("light", "dark")
    ),
    ROOT / "docs" / "plots" / "overlap_light.svg",
    ROOT / "docs" / "plots" / "overlap_dark.svg",
    ROOT / "docs" / "plots" / "realtime_light.svg",
    ROOT / "docs" / "plots" / "realtime_dark.svg",
)


def _local_name(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def public_svg_accessibility_problems() -> list[str]:
    """Audit the exact direct-view accessibility contract for all public SVGs."""
    expected_count = 2 + len(DIAGRAMS) * 2 + 4
    if (
        len(PUBLIC_SVG_PATHS) != expected_count
        or len(set(PUBLIC_SVG_PATHS)) != expected_count
    ):
        return [
            f"public SVG inventory must contain exactly {expected_count} unique assets"
        ]

    problems = []
    actual_paths = {
        *ROOT.joinpath("assets").glob("*.svg"),
        *ROOT.joinpath("docs", "diagrams").glob("*.svg"),
        *ROOT.joinpath("docs", "plots").glob("*.svg"),
    }
    expected_paths = set(PUBLIC_SVG_PATHS)
    for path in sorted(actual_paths - expected_paths):
        problems.append(f"unregistered public SVG {path.relative_to(ROOT).as_posix()}")
    for path in PUBLIC_SVG_PATHS:
        label = path.relative_to(ROOT).as_posix()
        if not path.is_file():
            problems.append(f"missing public SVG {label}")
            continue
        if path.is_symlink():
            problems.append(f"{label}: public SVG must be a regular in-tree file")
            continue
        source = path.read_text(encoding="utf-8")
        lowered_source = source.casefold()
        is_protocol_diagram = path.parent == ROOT / "docs" / "diagrams"
        if "<!entity" in lowered_source:
            problems.append(f"{label}: entity declarations are not allowed")
        if is_protocol_diagram and "<!doctype" in lowered_source:
            problems.append(f"{label}: document type declarations are not allowed")
        if "<?xml-stylesheet" in lowered_source:
            problems.append(f"{label}: external XML stylesheets are not allowed")
        try:
            root = ET.fromstring(source)
        except ET.ParseError as error:
            problems.append(f"invalid XML in {label}: {error}")
            continue
        if _local_name(root.tag) != "svg":
            problems.append(f"{label}: document root is not svg")
            continue
        for attribute in ("width", "height", "viewBox"):
            if not root.get(attribute):
                problems.append(f"{label}: root is missing {attribute}")
        if root.get("role") != "img":
            problems.append(f'{label}: root must have role="img"')
        if root.get("aria-label") is not None:
            problems.append(
                f"{label}: remove aria-label; aria-labelledby is authoritative"
            )

        titles = [node for node in root if _local_name(node.tag) == "title"]
        descriptions = [node for node in root if _local_name(node.tag) == "desc"]
        if len(titles) != 1 or len(descriptions) != 1:
            problems.append(f"{label}: root needs exactly one direct title and desc")
            continue

        title_id = titles[0].get("id")
        description_id = descriptions[0].get("id")
        labelledby = root.get("aria-labelledby", "").split()
        id_counts = {}
        fragment_references = set()
        for node in root.iter():
            if _local_name(node.tag) in {"script", "foreignObject"}:
                problems.append(
                    f"{label}: {_local_name(node.tag)} is not allowed in a public SVG"
                )
            for attribute, value in node.attrib.items():
                local_attribute = _local_name(attribute)
                if local_attribute.casefold().startswith("on"):
                    problems.append(
                        f"{label}: event-handler attributes are not allowed"
                    )
                if local_attribute == "base":
                    problems.append(f"{label}: XML base attributes are not allowed")
                if local_attribute == "href":
                    if not value.startswith("#") or len(value) == 1:
                        problems.append(
                            f"{label}: external or empty resource reference is not allowed"
                        )
                    else:
                        fragment_references.add(value[1:])
            node_id = node.get("id")
            if node_id:
                id_counts[node_id] = id_counts.get(node_id, 0) + 1
        if (
            not title_id
            or not description_id
            or title_id == description_id
            or id_counts.get(title_id) != 1
            or id_counts.get(description_id) != 1
            or labelledby != [title_id, description_id]
        ):
            problems.append(
                f"{label}: aria-labelledby must name direct title then desc"
            )

        title = " ".join("".join(titles[0].itertext()).split())
        description = " ".join("".join(descriptions[0].itertext()).split())
        if not title or len(title.split()) > 10:
            problems.append(f"{label}: title must be nonempty and at most 10 words")
        if not description or len(description.split()) > 55:
            problems.append(f"{label}: desc must be nonempty and at most 55 words")
        if (
            "UNRELEASED" not in description
            or "certification" not in description.casefold()
        ):
            problems.append(
                f"{label}: desc must state UNRELEASED and non-certification status"
            )

        if "@import" in lowered_source:
            problems.append(f"{label}: external CSS resource is not allowed")
        css_url_starts = re.findall(r"url\s*\(", source, flags=re.IGNORECASE)
        css_urls = list(
            re.finditer(r"url\s*\(\s*([^)]*?)\s*\)", source, flags=re.IGNORECASE)
        )
        if len(css_urls) != len(css_url_starts):
            problems.append(f"{label}: malformed CSS resource reference")
        for match in css_urls:
            target = match.group(1).strip()
            if len(target) >= 2 and target[0] == target[-1] and target[0] in "\"'":
                target = target[1:-1].strip()
            if not target.startswith("#") or len(target) == 1:
                problems.append(
                    f"{label}: external or empty CSS resource is not allowed"
                )
        for fragment in sorted(fragment_references):
            if id_counts.get(fragment) != 1:
                problems.append(
                    f"{label}: resource fragment #{fragment} must resolve exactly once"
                )

        has_motion = "<animate" in source or "animation:" in source
        if has_motion and "prefers-reduced-motion: reduce" not in source:
            problems.append(f"{label}: motion has no reduced-motion rule")
    return problems


def topology_contract_problems() -> list[str]:
    """Keep the current topology aligned with the normative plane grammar."""
    problems = []
    required = (
        RPC_ROUTE,
        SENSOR_ROUTE,
        COMMAND_ROUTE,
        OBSERVATION_ROUTE,
        "Init rejects",
        "qualification: NOT RUN",
    )
    forbidden = (
        "{realm}/session/{id}",
        "[/{name}]",
        "example: Crebain",
    )
    for theme in (LIGHT, DARK):
        source = topology(theme)
        for text in required:
            if text not in source:
                problems.append(f"{theme['name']} topology omits {text!r}")
        for text in forbidden:
            if text in source:
                problems.append(f"{theme['name']} topology retains stale text {text!r}")
    return problems


def architecture_diagram_problems() -> list[str]:
    """Keep the new overview and low-overhead figures claim-complete."""
    problems = []
    required_by_diagram = {
        "overview": (
            "BOUND RAW BYTES",
            "AUTHENTICATE",
            "WIRE + CORE",
            "SESSION + STREAM",
            "TYPED DELIVERY",
            "BODY EFFECT GATE",
            "production-secure profile is unavailable",
        ),
        "runtime": (
            "PREPARE ONCE",
            "DECODE ONCE",
            "OWNER STEP",
            "external work unlocked",
            "T_hot = T_bound + T_auth + T_decode + T_lookup + T_owner + T_handoff",
            "M_NCP,bounded ≤ M_prepared + M_step,total + M_ext,total + M_aux",
            "These are symbolic targets, not measurements.",
        ),
        "lifecycle": (
            "FREE",
            "PENDING",
            "AMBIGUOUS",
            "TERMINAL",
            "different coordinate or bytes → reject · no mutation",
            "publish retained result + high-water · release active slot",
            "threads/session = sockets/session = dedicated stores/session = 0",
            "B03 selects every numeric ceiling",
        ),
    }
    for name, required in required_by_diagram.items():
        function = DIAGRAMS[name]
        for theme in (LIGHT, DARK):
            source = function(theme)
            for text in required:
                if esc(text) not in source:
                    problems.append(f"{theme['name']} {name} omits {text!r}")
    return problems


def diagram_reference_problems() -> list[str]:
    """Require one maintained owner document for every generated diagram pair."""
    if set(DIAGRAM_OWNERS) != set(DIAGRAMS):
        return ["diagram owner inventory must equal the generated diagram inventory"]
    problems = []
    for name, owner in DIAGRAM_OWNERS.items():
        label = owner.relative_to(ROOT).as_posix()
        try:
            source = owner.read_text(encoding="utf-8")
        except FileNotFoundError:
            problems.append(f"{name} diagram owner is missing: {label}")
            continue
        for theme in ("light", "dark"):
            filename = f"{name}-{theme}.svg"
            if filename not in source:
                problems.append(f"{label} does not reference {filename}")
    return problems


def fsm_contrast_problems() -> list[str]:
    """Check normal text against every actual FSM solid or gradient background."""
    problems = []
    for theme in (LIGHT, DARK):
        checks = []
        for token in (
            "fsm_active_text",
            "fsm_hold_text",
            "fsm_configfail_text",
            "fsm_action_text",
            "tprim",
            "tsec",
            "tmut",
        ):
            for background_token in (
                "bg_top",
                "bg_bot",
                "surf_top",
                "surf_bot",
                "surf_chip",
            ):
                checks.append(
                    (
                        f"{token} on {background_token}",
                        theme[token],
                        theme[background_token],
                    )
                )
        checks.extend(
            (
                (
                    "active badge",
                    theme["fsm_active_badge_text"],
                    theme["fsm_active_badge"],
                ),
                ("ESTOP badge", theme["fsm_estop_badge_text"], theme["action"]),
            )
        )
        for offset, stop, opacity_text in theme["fsm_bus_stops"]:
            try:
                opacity = float(opacity_text)
            except ValueError:
                problems.append(
                    f"{theme['name']} FSM hero gradient stop {offset} has invalid opacity {opacity_text!r}"
                )
                continue
            if not 0 < opacity <= 1:
                problems.append(
                    f"{theme['name']} FSM hero gradient stop {offset} opacity must be in (0, 1]"
                )
                continue
            underlays = ("bg_top", "bg_bot") if opacity < 1 else (None,)
            for underlay in underlays:
                actual_stop = (
                    _composite_color(stop, theme[underlay], opacity)
                    if underlay is not None
                    else stop
                )
                suffix = f" over {underlay}" if underlay is not None else ""
                checks.append(
                    (
                        f"ESTOP hero gradient stop {offset}{suffix}",
                        theme["fsm_hero_ink"],
                        actual_stop,
                    )
                )

        for label, foreground, background_color in checks:
            ratio = _contrast_ratio(foreground, background_color)
            if ratio < 4.5:
                problems.append(
                    f"{theme['name']} FSM {label} contrast {ratio:.2f}:1 is below 4.5:1 "
                    f"({foreground} on {background_color})"
                )
    return problems


def architecture_contrast_problems() -> list[str]:
    """Check semantic text and badge contrast in every generated sheet."""
    problems = []
    for theme in (LIGHT, DARK):
        semantic_tokens = (
            "control",
            "perception",
            "action",
            "observation",
            "contract",
            "active",
            "hold",
            "configfail",
        )
        for token in semantic_tokens:
            foreground = semantic_text_color(theme, theme[token])
            for background_token in (
                "bg_top",
                "bg_bot",
                "surf_top",
                "surf_bot",
                "surf_chip",
            ):
                background_color = theme[background_token]
                ratio = _contrast_ratio(foreground, background_color)
                if ratio < 4.5:
                    problems.append(
                        f"{theme['name']} architecture {token} text on "
                        f"{background_token} contrast {ratio:.2f}:1 is below 4.5:1 "
                        f"({foreground} on {background_color})"
                    )

                wash_background = _composite_color(
                    theme[token], background_color, theme["wash_op"]
                )
                wash_ratio = _contrast_ratio(foreground, wash_background)
                if wash_ratio < 4.5:
                    problems.append(
                        f"{theme['name']} architecture {token} text on "
                        f"{background_token} with semantic wash contrast "
                        f"{wash_ratio:.2f}:1 is below 4.5:1 "
                        f"({foreground} on {wash_background})"
                    )

            badge_ink = contrast_ink(theme[token])
            badge_ratio = _contrast_ratio(badge_ink, theme[token])
            if badge_ratio < 4.5:
                problems.append(
                    f"{theme['name']} architecture {token} badge contrast "
                    f"{badge_ratio:.2f}:1 is below 4.5:1 "
                    f"({badge_ink} on {theme[token]})"
                )

        gradient_ink = contrast_ink(theme["contract"], theme["contract_lo"])
        for stop_token in ("contract", "contract_lo"):
            ratio = _contrast_ratio(gradient_ink, theme[stop_token])
            if ratio < 4.5:
                problems.append(
                    f"{theme['name']} contract gradient text on {stop_token} "
                    f"contrast {ratio:.2f}:1 is below 4.5:1 "
                    f"({gradient_ink} on {theme[stop_token]})"
                )

        # Inspect generated text, not only the palette helpers. A raw semantic
        # token that needs the light-theme text override is always a defect.
        raw_to_token = {theme[token]: token for token in semantic_tokens}
        for name, function in DIAGRAMS.items():
            root = ET.fromstring(function(theme))
            for node in root.iter():
                if _local_name(node.tag) != "text":
                    continue
                fill = node.get("fill")
                token = raw_to_token.get(fill)
                if token is None or semantic_text_color(theme, fill) == fill:
                    continue
                content = " ".join("".join(node.itertext()).split())
                problems.append(
                    f"{theme['name']} {name} text {content!r} uses raw "
                    f"low-contrast semantic token {token}"
                )
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed SVGs differ from deterministic generator output",
    )
    args = parser.parse_args()

    outdir = os.path.join("docs", "diagrams")
    if not args.check:
        os.makedirs(outdir, exist_ok=True)
    stale = []
    for name, fn in DIAGRAMS.items():
        for th in (LIGHT, DARK):
            svg = fn(th)
            p = os.path.join(outdir, f"{name}-{th['name']}.svg")
            if args.check:
                try:
                    with open(p, encoding="utf-8") as f:
                        committed = f.read()
                except FileNotFoundError:
                    stale.append(f"missing {p}")
                    continue
                if committed != svg:
                    stale.append(f"stale {p}")
            else:
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(svg)
                print(f"wrote {p}  ({len(svg)} bytes)")

    stale.extend(fsm_contrast_problems())
    stale.extend(architecture_contrast_problems())
    stale.extend(topology_contract_problems())
    stale.extend(architecture_diagram_problems())
    stale.extend(diagram_reference_problems())
    stale.extend(public_svg_accessibility_problems())

    if stale:
        for problem in stale:
            print(problem)
        print("run: python3 scripts/gen_diagrams.py")
        raise SystemExit(1)
    if args.check:
        print(
            f"OK: {len(DIAGRAMS) * 2} generated diagrams are current; "
            f"{len(PUBLIC_SVG_PATHS)} public SVGs meet the direct-view accessibility contract; "
            "architecture and FSM text contrast is at least 4.5:1"
        )


if __name__ == "__main__":
    main()
