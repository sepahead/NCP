#!/usr/bin/env python3
"""Generate NCP's documentation and publication diagrams as light and dark SVG.

The figures use the repository's adaptation of the pid-rs publication design
language: an ivory sheet, lapis and turquoise structure, saffron accent rules,
Source Sans Pro labels, and Latin Modern Roman body text. Every state and
relationship has a text label. Color only repeats that meaning.

The generator measures every label with committed advance widths from the exact
font files (``scripts/diagram_font_metrics.v1.json``). It then checks each
figure before it writes or accepts any byte:

* each label fits inside its container with the primary font and with the
  Arial-metric Liberation fonts that a browser can substitute;
* labels do not overlap each other, connectors, or unrelated boxes;
* connectors start and end on their named boxes and cross no other box;
* text contrast is at least 4.5:1 in both themes;
* each public SVG meets the direct-view accessibility contract.

Output: docs/diagrams/<name>-{light,dark}.svg for every entry in DIAGRAMS.

Run from the repository root:

    python3 scripts/gen_diagrams.py                        # write the SVGs
    python3 scripts/gen_diagrams.py --check                # compare and validate
    python3 scripts/gen_diagrams.py --write-font-metrics   # refresh the widths
    python3 scripts/gen_diagrams.py --check-font-metrics   # compare the widths

The font-metric modes read the installed TeX Live and Liberation font files.
The other modes use only the Python standard library and the committed widths.
The SVGs are presentation material. They carry no protocol semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "diagrams"
METRICS_PATH = ROOT / "scripts" / "diagram_font_metrics.v1.json"

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

EXPECTED_PLANE_KEY_GRAMMAR = (
    "{realm}/rpc/{request_kind} | "
    "{realm}/session/{session_id}/{sensor|command}[/{channel}] | "
    "{realm}/session/{session_id}/observation"
)
PLANE_CONTRACT = json.loads(
    (ROOT / "contract" / "planes.v1.json").read_text(encoding="utf-8")
)
if PLANE_CONTRACT.get("key_grammar") != EXPECTED_PLANE_KEY_GRAMMAR:
    raise ValueError("plane contract key grammar changed; review every diagram route")
RPC_ROUTE, SESSION_ROUTE_TEMPLATE, OBSERVATION_ROUTE = EXPECTED_PLANE_KEY_GRAMMAR.split(
    " | "
)
SENSOR_ROUTE = SESSION_ROUTE_TEMPLATE.replace("{sensor|command}", "sensor")
COMMAND_ROUTE = SESSION_ROUTE_TEMPLATE.replace("{sensor|command}", "command")
CANDIDATE_LABEL = f"UNRELEASED {CANDIDATE_VERSION} · WIRE {WIRE_VERSION}"

# ─────────────────────────────── font metrics ───────────────────────────────

# Each role names one exact font file. The browser stack in SVG_FONT_STACKS can
# substitute the "check" font on a host that lacks the primary font.
FONT_FILES = {
    "sans-400": ("kpsewhich", "SourceSansPro-Regular.otf"),
    "sans-600": ("kpsewhich", "SourceSansPro-Semibold.otf"),
    "sans-700": ("kpsewhich", "SourceSansPro-Bold.otf"),
    "sans-400-italic": ("kpsewhich", "SourceSansPro-RegularIt.otf"),
    "sans-600-italic": ("kpsewhich", "SourceSansPro-SemiboldIt.otf"),
    "serif-400": ("kpsewhich", "lmroman10-regular.otf"),
    "serif-400-italic": ("kpsewhich", "lmroman10-italic.otf"),
    "check-sans-400": ("fc-match", "Liberation Sans:style=Regular"),
    "check-sans-700": ("fc-match", "Liberation Sans:style=Bold"),
    "check-sans-400-italic": ("fc-match", "Liberation Sans:style=Italic"),
    "check-sans-700-italic": ("fc-match", "Liberation Sans:style=Bold Italic"),
    "check-serif-400": ("fc-match", "Liberation Serif:style=Regular"),
    "check-serif-400-italic": ("fc-match", "Liberation Serif:style=Italic"),
}
# Browsers render these fonts when the primary font is absent. Liberation Sans
# and Liberation Serif have Arial and Times New Roman metrics.
CHECK_FONT = {
    "sans-400": "check-sans-400",
    "sans-600": "check-sans-700",
    "sans-700": "check-sans-700",
    "sans-400-italic": "check-sans-400-italic",
    "sans-600-italic": "check-sans-700-italic",
    "serif-400": "check-serif-400",
    "serif-400-italic": "check-serif-400-italic",
}
SVG_FONT_STACKS = {
    "sans": "'Source Sans Pro', 'Source Sans 3', Arial, 'Liberation Sans', "
    "'Helvetica Neue', Helvetica, sans-serif",
    "serif": "'Latin Modern Roman', 'LM Roman 10', 'Times New Roman', "
    "'Liberation Serif', Times, serif",
}
METRIC_CHARACTERS = "".join(chr(code) for code in range(32, 127)) + (
    "·→←↑↓↔≤≥×−–—…≠∑ΔΣτλρ≈′°µ‖∞⇒‘’“”§"
)


def _sfnt_tables(data: bytes) -> dict[str, tuple[int, int]]:
    count = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for index in range(count):
        tag, _checksum, offset, length = struct.unpack(
            ">4sIII", data[12 + 16 * index : 28 + 16 * index]
        )
        tables[tag.decode("latin-1")] = (offset, length)
    return tables


def _sfnt_cmap(data: bytes, tables: dict[str, tuple[int, int]]) -> dict[int, int]:
    offset, _ = tables["cmap"]
    count = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
    ranked = {(3, 10): 0, (0, 4): 1, (3, 1): 2, (0, 3): 3}
    best = None
    for index in range(count):
        platform, encoding, sub = struct.unpack(
            ">HHI", data[offset + 4 + 8 * index : offset + 12 + 8 * index]
        )
        fmt = struct.unpack(">H", data[offset + sub : offset + sub + 2])[0]
        rank = ranked.get((platform, encoding))
        if rank is not None and fmt in (4, 12) and (best is None or rank < best[0]):
            best = (rank, offset + sub, fmt)
    if best is None:
        raise ValueError("font has no Unicode cmap subtable")
    _, base, fmt = best
    mapping: dict[int, int] = {}
    if fmt == 12:
        groups = struct.unpack(">I", data[base + 12 : base + 16])[0]
        for group in range(groups):
            start, end, glyph = struct.unpack(
                ">III", data[base + 16 + 12 * group : base + 28 + 12 * group]
            )
            for code in range(start, end + 1):
                mapping[code] = glyph + code - start
        return mapping
    segments = struct.unpack(">H", data[base + 6 : base + 8])[0] // 2
    width = 2 * segments
    ends = struct.unpack(f">{segments}H", data[base + 14 : base + 14 + width])
    starts = struct.unpack(
        f">{segments}H", data[base + 16 + width : base + 16 + 2 * width]
    )
    deltas = struct.unpack(
        f">{segments}h", data[base + 16 + 2 * width : base + 16 + 3 * width]
    )
    range_base = base + 16 + 3 * width
    ranges = struct.unpack(f">{segments}H", data[range_base : range_base + width])
    for index in range(segments):
        for code in range(starts[index], ends[index] + 1):
            if code == 0xFFFF:
                continue
            if ranges[index] == 0:
                glyph = (code + deltas[index]) & 0xFFFF
            else:
                address = (
                    range_base + 2 * index + ranges[index] + 2 * (code - starts[index])
                )
                glyph = struct.unpack(">H", data[address : address + 2])[0]
                if glyph:
                    glyph = (glyph + deltas[index]) & 0xFFFF
            if glyph:
                mapping[code] = glyph
    return mapping


def _font_record(path: Path) -> dict:
    data = path.read_bytes()
    tables = _sfnt_tables(data)
    head = tables["head"][0]
    units = struct.unpack(">H", data[head + 18 : head + 20])[0]
    hhea = tables["hhea"][0]
    metric_count = struct.unpack(">H", data[hhea + 34 : hhea + 36])[0]
    hmtx = tables["hmtx"][0]
    advances = [
        struct.unpack(">H", data[hmtx + 4 * index : hmtx + 4 * index + 2])[0]
        for index in range(metric_count)
    ]
    os2 = tables["OS/2"][0]
    ascender, descender = struct.unpack(">hh", data[os2 + 68 : os2 + 72])
    cmap = _sfnt_cmap(data, tables)
    widths = {}
    for character in METRIC_CHARACTERS:
        glyph = cmap.get(ord(character))
        if glyph is None:
            continue
        advance = advances[glyph] if glyph < metric_count else advances[-1]
        widths[character] = round(advance * 1000 / units)
    return {
        "file": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "ascender": round(ascender * 1000 / units),
        "descender": round(descender * 1000 / units),
        "widths": widths,
    }


def _locate_font(method: str, name: str) -> Path:
    tool = shutil.which("kpsewhich" if method == "kpsewhich" else "fc-match")
    if tool is None:
        raise SystemExit(f"font lookup tool is absent for {name}")
    command = [tool, name] if method == "kpsewhich" else [tool, "-f", "%{file}", name]
    found = subprocess.run(command, capture_output=True, text=True, check=False)
    path = Path(found.stdout.strip())
    if found.returncode != 0 or not path.is_file():
        raise SystemExit(f"font file is absent: {name}")
    return path


def measured_font_metrics() -> dict:
    fonts = {}
    for role, (method, name) in FONT_FILES.items():
        path = _locate_font(method, name)
        record = _font_record(path)
        if role.startswith("check-") is False and len(record["widths"]) != len(
            METRIC_CHARACTERS
        ):
            missing = "".join(c for c in METRIC_CHARACTERS if c not in record["widths"])
            if role.startswith("sans"):
                raise SystemExit(f"{name} lacks required glyphs: {missing!r}")
        fonts[role] = record
    return {
        "schema": "ncp.diagram-font-metrics.v1",
        "units": "advance width in thousandths of one em",
        "characters": METRIC_CHARACTERS,
        "fonts": fonts,
    }


def _metrics_bytes(metrics: dict) -> bytes:
    return (
        json.dumps(metrics, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    ).encode("utf-8")


FONT_METRICS = (
    json.loads(METRICS_PATH.read_text(encoding="utf-8"))
    if METRICS_PATH.is_file()
    else None
)


def text_width(text: str, role: str, size: float, letter_spacing: float = 0.0) -> float:
    """Return the advance width of text in SVG user units."""
    if FONT_METRICS is None:
        raise SystemExit("run: python3 scripts/gen_diagrams.py --write-font-metrics")
    widths = FONT_METRICS["fonts"][role]["widths"]
    total = 0.0
    for character in text:
        advance = widths.get(character)
        if advance is None:
            if role.startswith("check-"):
                # A host font substitutes one missing symbol. Charge one em.
                advance = 1000
            else:
                raise ValueError(f"font {role} has no measured glyph {character!r}")
        total += advance
    return total * size / 1000 + letter_spacing * len(text)


def font_extent(role: str, size: float) -> tuple[float, float]:
    record = FONT_METRICS["fonts"][role]
    return record["ascender"] * size / 1000, -record["descender"] * size / 1000


# ───────────────────────────────── themes ───────────────────────────────────

LIGHT = {
    "name": "light",
    "sheet": "#F7F3E9",  # ivory
    "card": "#FBF9F3",
    "tint": "#E4EDEE",  # mineral wash for emphasis
    "note": "#D2E0E2",  # mineral blue
    "ink": "#2C3E50",
    "muted": "#4D5C64",
    "lapis": "#1F3F60",
    "turquoise": "#1F6968",
    "mineral": "#D2E0E2",
    "rule": "#C3D3D6",
    "saffron": "#B28218",
    "bronze": "#7A5500",
    "pomegranate": "#743E37",
    "on_accent": "#F7F3E9",
    "hatch": "#B28218",
}
DARK = {
    "name": "dark",
    "sheet": "#131D26",
    "card": "#1A2631",
    "tint": "#1F3340",
    "note": "#1E3240",
    "ink": "#ECE5D5",
    "muted": "#AAB7BE",
    "lapis": "#8DB2D8",
    "turquoise": "#6FC1BD",
    "mineral": "#35495A",
    "rule": "#3D5263",
    "saffron": "#D8AA45",
    "bronze": "#E2B75A",
    "pomegranate": "#E6A095",
    "on_accent": "#10202B",
    "hatch": "#D8AA45",
}
THEMES = (LIGHT, DARK)
TEXT_TOKENS = ("ink", "muted", "lapis", "turquoise", "bronze", "pomegranate")


def _luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# ─────────────────────────────── text styles ────────────────────────────────


@dataclass(frozen=True)
class Style:
    family: str
    size: float
    weight: int = 400
    italic: bool = False
    color: str = "ink"
    spacing: float = 0.0

    @property
    def role(self) -> str:
        role = f"{self.family}-{self.weight}"
        return role + "-italic" if self.italic else role


EYEBROW = Style("sans", 24, 700, color="muted", spacing=2.0)
HEADING = Style("sans", 38, 700, color="lapis")
TITLE = Style("sans", 28, 700)
TITLE_NARROW = Style("sans", 26, 700)
SUBTITLE = Style("sans", 25, 600, color="turquoise")
LABEL = Style("sans", 25, 600, color="muted")
SMALL = Style("sans", 24, 600, color="muted")
BODY = Style("serif", 25)
BODY_ITALIC = Style("serif", 25, italic=True)
BADGE = Style("sans", 24, 700, color="on_accent", spacing=1.0)
MIN_TEXT_SIZE = 24


def esc(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


# ──────────────────────────────── geometry ──────────────────────────────────


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def inset(self, amount: float) -> Box:
        return Box(
            self.x + amount, self.y + amount, self.w - 2 * amount, self.h - 2 * amount
        )

    def contains(
        self, other: Box, margin: float = 0.0, vertical: float | None = None
    ) -> bool:
        vertical = margin if vertical is None else vertical
        return (
            other.x >= self.x + margin - 1e-6
            and other.y >= self.y + vertical - 1e-6
            and other.right <= self.right - margin + 1e-6
            and other.bottom <= self.bottom - vertical + 1e-6
        )

    def intersects(self, other: Box, gap: float = 0.0) -> bool:
        return not (
            other.x >= self.right + gap
            or other.right <= self.x - gap
            or other.y >= self.bottom + gap
            or other.bottom <= self.y - gap
        )

    def on_border(self, x: float, y: float, tolerance: float = 0.6) -> bool:
        inside_x = self.x - tolerance <= x <= self.right + tolerance
        inside_y = self.y - tolerance <= y <= self.bottom + tolerance
        near_x = abs(x - self.x) <= tolerance or abs(x - self.right) <= tolerance
        near_y = abs(y - self.y) <= tolerance or abs(y - self.bottom) <= tolerance
        return (near_x and inside_y) or (near_y and inside_x)


def segment_hits_box(a: tuple[float, float], b: tuple[float, float], box: Box) -> bool:
    """Return true when an open segment passes through a box interior."""
    (x0, y0), (x1, y1) = a, b
    left, top, right, bottom = box.x, box.y, box.right, box.bottom
    t0, t1 = 0.0, 1.0
    dx, dy = x1 - x0, y1 - y0
    for p, q in (
        (-dx, x0 - left),
        (dx, right - x0),
        (-dy, y0 - top),
        (dy, bottom - y0),
    ):
        if abs(p) < 1e-9:
            if q <= 0:
                return False
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 >= t1:
            return False
    # Ignore contact that only touches the boundary at an endpoint.
    return t1 - t0 > 1e-6 and not (t1 - t0) * math.hypot(dx, dy) < 0.5


# ──────────────────────────────── canvas ────────────────────────────────────


@dataclass
class Text:
    x: float
    y: float
    runs: list[tuple[str, Style]]
    anchor: str
    container: str | None
    primary: Box = field(init=False)
    check: Box = field(init=False)

    def __post_init__(self) -> None:
        self.primary = self._box("primary")
        self.check = self._box("check")

    @property
    def content(self) -> str:
        return "".join(text for text, _ in self.runs)

    def width(self, which: str) -> float:
        total = 0.0
        for text, style in self.runs:
            role = style.role if which == "primary" else CHECK_FONT[style.role]
            total += text_width(text, role, style.size, style.spacing)
        return total

    def _box(self, which: str) -> Box:
        width = self.width(which)
        ascent = max(font_extent(style.role, style.size)[0] for _, style in self.runs)
        descent = max(font_extent(style.role, style.size)[1] for _, style in self.runs)
        # Typographic extents include accent room. Use the cap and descender box.
        top = self.y - 0.72 * max(style.size for _, style in self.runs)
        bottom = self.y + 0.22 * max(style.size for _, style in self.runs)
        del ascent, descent
        if self.anchor == "start":
            left = self.x
        elif self.anchor == "middle":
            left = self.x - width / 2
        else:
            left = self.x - width
        return Box(left, top, width, bottom - top)


@dataclass
class Node:
    name: str
    box: Box
    parent: str | None
    solid: bool = True


@dataclass
class Connector:
    name: str
    points: list[tuple[float, float]]
    start: str
    end: str
    color: str
    dashed: bool
    arrow_end: bool
    arrow_start: bool
    width: float
    through: tuple[str, ...] = ()


class Canvas:
    """Collect one figure, then render or validate it for either theme."""

    def __init__(self, name: str, width: float, height: float, title: str, desc: str):
        self.name = name
        self.width = width
        self.height = height
        self.title = title
        self.desc = desc
        self.nodes: dict[str, Node] = {}
        self.texts: list[Text] = []
        self.connectors: list[Connector] = []
        self.shapes: list[tuple] = []
        self.overlays: list[tuple] = []
        self.node("canvas", Box(0, 0, width, height), parent=None, solid=False)

    # Registration ---------------------------------------------------------

    def node(
        self, name: str, box: Box, parent: str | None = "canvas", solid: bool = True
    ) -> Box:
        if name in self.nodes:
            raise ValueError(f"{self.name}: duplicate node {name}")
        self.nodes[name] = Node(name, box, parent, solid)
        return box

    def shape(self, kind: str, overlay: bool = False, **values) -> None:
        (self.overlays if overlay else self.shapes).append((kind, values))

    def text(
        self,
        x: float,
        y: float,
        value: str | list[tuple[str, Style]],
        style: Style = BODY,
        anchor: str = "start",
        container: str | None = "canvas",
    ) -> Text:
        runs = [(value, style)] if isinstance(value, str) else value
        item = Text(x, y, runs, anchor, container)
        self.texts.append(item)
        return item

    def connector(
        self,
        name: str,
        points: list[tuple[float, float]],
        start: str,
        end: str,
        color: str = "turquoise",
        dashed: bool = False,
        arrow_end: bool = True,
        arrow_start: bool = False,
        width: float = 4.0,
        through: tuple[str, ...] = (),
    ) -> None:
        self.connectors.append(
            Connector(
                name,
                points,
                start,
                end,
                color,
                dashed,
                arrow_end,
                arrow_start,
                width,
                through,
            )
        )

    # Rendering ------------------------------------------------------------

    def render(self, theme: dict) -> str:
        colors = sorted(
            {c.color for c in self.connectors if c.arrow_end or c.arrow_start}
        )
        slug = re.sub(r"[^a-z0-9]+", "-", self.name)
        out = [
            f'<svg xmlns="http://www.w3.org/2000/svg" xml:lang="en" width="{fmt(self.width)}" '
            f'height="{fmt(self.height)}" viewBox="0 0 {fmt(self.width)} {fmt(self.height)}" '
            f'role="img" aria-labelledby="{slug}-title {slug}-desc">',
            f'<title id="{slug}-title">{esc(self.title)}</title>',
            f'<desc id="{slug}-desc">{esc(self.desc)}</desc>',
            "<defs>",
            "<style>"
            f".s{{font-family:{SVG_FONT_STACKS['sans']}}}"
            f".r{{font-family:{SVG_FONT_STACKS['serif']}}}"
            "</style>",
        ]
        for color in colors:
            fill = theme[color]
            out.append(
                f'<marker id="{slug}-arrow-{color}" viewBox="0 0 16 14" refX="16" refY="7" '
                'markerWidth="16" markerHeight="14" markerUnits="userSpaceOnUse" '
                f'orient="auto-start-reverse"><path d="M0,0 L16,7 L0,14 z" fill="{fill}"/>'
                "</marker>"
            )
        out.append(
            f'<pattern id="{slug}-hatch" width="12" height="12" patternUnits="userSpaceOnUse" '
            f'patternTransform="rotate(40)"><line x1="0" y1="0" x2="0" y2="12" '
            f'stroke="{theme["hatch"]}" stroke-width="3"/></pattern>'
        )
        out.append("</defs>")
        out.append(
            f'<rect width="{fmt(self.width)}" height="{fmt(self.height)}" fill="{theme["sheet"]}"/>'
        )
        for kind, values in self.shapes:
            out.append(self._shape(kind, values, theme, slug))
        for connector in self.connectors:
            out.append(self._connector(connector, theme, slug))
        for kind, values in self.overlays:
            out.append(self._shape(kind, values, theme, slug))
        for item in self.texts:
            out.append(self._text(item, theme))
        out.append("</svg>")
        return "\n".join(out) + "\n"

    def _shape(self, kind: str, v: dict, theme: dict, slug: str) -> str:
        def color(token: str | None) -> str:
            if token is None:
                return "none"
            if token == "hatch":
                return f"url(#{slug}-hatch)"
            return theme[token]

        if kind == "rect":
            dash = f' stroke-dasharray="{v["dash"]}"' if v.get("dash") else ""
            stroke = (
                f' stroke="{color(v.get("stroke"))}" stroke-width="{fmt(v.get("stroke_width", 3))}"'
                if v.get("stroke")
                else ""
            )
            return (
                f'<rect x="{fmt(v["x"])}" y="{fmt(v["y"])}" width="{fmt(v["w"])}" '
                f'height="{fmt(v["h"])}" rx="{fmt(v.get("rx", 0))}" fill="{color(v.get("fill"))}"'
                f"{stroke}{dash}/>"
            )
        if kind == "line":
            dash = f' stroke-dasharray="{v["dash"]}"' if v.get("dash") else ""
            return (
                f'<path d="M{fmt(v["x1"])} {fmt(v["y1"])} L{fmt(v["x2"])} {fmt(v["y2"])}" '
                f'stroke="{color(v["stroke"])}" stroke-width="{fmt(v.get("width", 2))}" '
                f'fill="none" stroke-linecap="butt"{dash}/>'
            )
        if kind == "circle":
            stroke = (
                f' stroke="{color(v["stroke"])}" stroke-width="{fmt(v.get("stroke_width", 3))}"'
                if v.get("stroke")
                else ""
            )
            return (
                f'<circle cx="{fmt(v["cx"])}" cy="{fmt(v["cy"])}" r="{fmt(v["r"])}" '
                f'fill="{color(v.get("fill"))}"{stroke}/>'
            )
        if kind == "cap":
            # A header bar with rounded top corners that matches its card.
            x, y, w, h, r = v["x"], v["y"], v["w"], v["h"], v["rx"]
            return (
                f'<path d="M{fmt(x)} {fmt(y + h)} L{fmt(x)} {fmt(y + r)} '
                f"Q{fmt(x)} {fmt(y)} {fmt(x + r)} {fmt(y)} L{fmt(x + w - r)} {fmt(y)} "
                f'Q{fmt(x + w)} {fmt(y)} {fmt(x + w)} {fmt(y + r)} L{fmt(x + w)} {fmt(y + h)} Z" '
                f'fill="{color(v["fill"])}"/>'
            )
        raise ValueError(f"unknown shape {kind}")

    def _connector(self, c: Connector, theme: dict, slug: str) -> str:
        d = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in c.points)
        dash = ' stroke-dasharray="12 9"' if c.dashed else ""
        marker = ""
        if c.arrow_end:
            marker += f' marker-end="url(#{slug}-arrow-{c.color})"'
        if c.arrow_start:
            marker += f' marker-start="url(#{slug}-arrow-{c.color})"'
        # Shorten the stroke under an arrowhead so the square cap cannot show.
        return (
            f'<path d="{d}" fill="none" stroke="{theme[c.color]}" '
            f'stroke-width="{fmt(c.width)}" stroke-linejoin="round"{dash}{marker}/>'
        )

    def _text(self, item: Text, theme: dict) -> str:
        parts = []
        for index, (value, style) in enumerate(item.runs):
            attributes = self._style_attributes(style, theme)
            if index == 0:
                first = attributes
            else:
                parts.append(f"<tspan {attributes}>{esc(value)}</tspan>")
                continue
            parts.append(esc(value))
        anchor = "" if item.anchor == "start" else f' text-anchor="{item.anchor}"'
        return (
            f'<text x="{fmt(item.x)}" y="{fmt(item.y)}" {first}{anchor}>'
            + "".join(parts)
            + "</text>"
        )

    @staticmethod
    def _style_attributes(style: Style, theme: dict) -> str:
        family = "s" if style.family == "sans" else "r"
        attributes = [
            f'class="{family}"',
            f'font-size="{fmt(style.size)}"',
            f'fill="{theme[style.color]}"',
        ]
        if style.weight != 400:
            attributes.append(f'font-weight="{style.weight}"')
        if style.italic:
            attributes.append('font-style="italic"')
        if style.spacing:
            attributes.append(f'letter-spacing="{fmt(style.spacing)}"')
        return " ".join(attributes)

    # Validation -----------------------------------------------------------

    def ancestors(self, name: str) -> set[str]:
        result = set()
        current = self.nodes[name].parent
        while current is not None:
            result.add(current)
            current = self.nodes[current].parent
        return result

    def problems(self) -> list[str]:
        problems: list[str] = []
        label = self.name
        canvas = self.nodes["canvas"].box
        for item in self.texts:
            for _, style in item.runs:
                if style.size < MIN_TEXT_SIZE:
                    problems.append(
                        f"{label}: text {item.content!r} is below {MIN_TEXT_SIZE}"
                    )
            container = self.nodes.get(item.container or "canvas")
            if container is None:
                problems.append(
                    f"{label}: text {item.content!r} names an unknown container"
                )
                continue
            margin = 12 if container.name != "canvas" else 20
            if not container.box.contains(item.primary, margin, 6):
                problems.append(
                    f"{label}: text {item.content!r} does not fit {container.name} "
                    f"with {margin} units of padding"
                )
            if not container.box.contains(item.check, 4, 2):
                problems.append(
                    f"{label}: text {item.content!r} does not fit {container.name} "
                    "with the Arial-metric browser font"
                )
            if not canvas.contains(item.check, 8):
                problems.append(f"{label}: text {item.content!r} leaves the canvas")
        for index, first in enumerate(self.texts):
            for second in self.texts[index + 1 :]:
                if first.primary.intersects(second.primary, 2):
                    problems.append(
                        f"{label}: texts {first.content!r} and {second.content!r} overlap"
                    )
                elif first.check.intersects(second.check, 0):
                    problems.append(
                        f"{label}: texts {first.content!r} and {second.content!r} overlap "
                        "with the Arial-metric browser font"
                    )
        solid = [
            node for node in self.nodes.values() if node.solid and node.name != "canvas"
        ]
        for index, first in enumerate(solid):
            for second in solid[index + 1 :]:
                if first.parent != second.parent:
                    continue
                if first.box.intersects(second.box, 0):
                    problems.append(
                        f"{label}: boxes {first.name} and {second.name} overlap"
                    )
        for item in self.texts:
            owner = item.container or "canvas"
            for node in solid:
                if node.name == owner or node.name in self.ancestors(owner):
                    continue
                if owner in self.ancestors(node.name):
                    # A text can sit in its container beside a nested box.
                    if node.box.intersects(item.primary, 2):
                        problems.append(
                            f"{label}: text {item.content!r} overlaps nested box {node.name}"
                        )
                    continue
                if node.box.intersects(item.primary, 2):
                    problems.append(
                        f"{label}: text {item.content!r} overlaps box {node.name}"
                    )
        for connector in self.connectors:
            name = f"{label}: connector {connector.name}"
            start = self.nodes.get(connector.start)
            end = self.nodes.get(connector.end)
            if start is None or end is None:
                problems.append(f"{name} names an unknown endpoint")
                continue
            if not start.box.on_border(*connector.points[0]):
                problems.append(f"{name} does not start on {connector.start}")
            if not end.box.on_border(*connector.points[-1]):
                problems.append(f"{name} does not end on {connector.end}")
            allowed = {connector.start, connector.end, "canvas", *connector.through}
            allowed |= self.ancestors(connector.start) | self.ancestors(connector.end)
            segments = list(zip(connector.points, connector.points[1:]))
            for a, b in segments:
                if a[0] != b[0] and a[1] != b[1]:
                    problems.append(f"{name} has a diagonal segment")
                for node in solid:
                    if node.name in allowed:
                        continue
                    if segment_hits_box(a, b, node.box):
                        problems.append(f"{name} crosses box {node.name}")
                for item in self.texts:
                    if item.container in connector.through:
                        continue
                    if segment_hits_box(a, b, item.primary.inset(-3)):
                        problems.append(f"{name} crosses text {item.content!r}")
            for a, b in segments[1:-1]:
                if math.hypot(b[0] - a[0], b[1] - a[1]) < 12:
                    problems.append(f"{name} has a segment shorter than 12 units")
            if connector.arrow_end:
                a, b = segments[-1]
                if math.hypot(b[0] - a[0], b[1] - a[1]) < 30:
                    problems.append(f"{name} has no room for its arrowhead")
            if connector.arrow_start:
                a, b = segments[0]
                if math.hypot(b[0] - a[0], b[1] - a[1]) < 30:
                    problems.append(f"{name} has no room for its start arrowhead")
        return problems


# ─────────────────────────────── components ────────────────────────────────

WIDTH = 1600
MARGIN = 52
LINE = 33  # body line pitch
TITLE_LINE = 32


def measure(text: str, style: Style) -> float:
    """Return the wider of the primary and browser-substitute widths."""
    return max(
        text_width(text, style.role, style.size, style.spacing),
        text_width(text, CHECK_FONT[style.role], style.size, style.spacing),
    )


NBSP = "\u00a0"


def wrap(text: str, style: Style, width: float) -> list[str]:
    """Wrap on ordinary spaces only. A no-break space keeps a formula together."""
    text = text.replace("NOT RUN", f"NOT{NBSP}RUN")
    lines: list[str] = []
    current = ""
    for word in [part.replace(NBSP, " ") for part in text.split(" ") if part]:
        trial = word if not current else f"{current} {word}"
        if measure(trial, style) <= width:
            current = trial
            continue
        if not current:
            raise ValueError(f"word {word!r} is wider than {width}")
        lines.append(current)
        current = word
        if measure(current, style) > width:
            raise ValueError(f"word {word!r} is wider than {width}")
    if current:
        lines.append(current)
    return lines


def header(
    c: Canvas,
    eyebrow: str,
    heading: str,
    status: str | None = None,
    color: str = "lapis",
) -> float:
    if status:
        pill(c, "status", c.width - MARGIN, 18, status, color, anchor="end")
    c.text(MARGIN, 46, eyebrow, EYEBROW)
    c.shape(
        "line", x1=MARGIN, y1=66, x2=c.width - MARGIN, y2=66, stroke="rule", width=2
    )
    c.shape("line", x1=MARGIN, y1=66, x2=MARGIN + 208, y2=66, stroke="saffron", width=7)
    c.text(MARGIN, 114, heading, HEADING)
    return 146


@dataclass
class CardLayout:
    box: Box
    body_x: float
    body_y: float
    body_width: float


def card(
    c: Canvas,
    name: str,
    x: float,
    y: float,
    w: float,
    title: str | list[str],
    body: str | list[str] = (),
    *,
    h: float | None = None,
    accent: str = "lapis",
    number: str | None = None,
    subtitle: str | None = None,
    parent: str = "canvas",
    tint: bool = False,
    dashed: bool = False,
    title_style: Style = TITLE,
    body_style: Style = BODY,
    extra: float = 0.0,
    rule_offset: float | None = None,
    measure_only: bool = False,
) -> CardLayout | tuple[float, float]:
    """Draw a pid-rs card: accent cap, optional step number, title, rule, and body."""
    pad = 26
    title_x = x + (70 if number else pad)
    title_width = x + w - (22 if number else pad) - title_x
    titles: list[str] = []
    for part in title if isinstance(title, list) else [title]:
        titles.extend(wrap(part, title_style, title_width))
    subtitles = wrap(subtitle, SUBTITLE, w - 2 * pad) if subtitle else []
    body_width = w - 2 * pad
    lines: list[str] = []
    for paragraph in [body] if isinstance(body, str) else body:
        lines.extend(wrap(paragraph, body_style, body_width))
    title_base = y + 60
    subtitle_base = title_base + (len(titles) - 1) * TITLE_LINE + 32
    last_head = (
        subtitle_base + (len(subtitles) - 1) * 30
        if subtitles
        else title_base + (len(titles) - 1) * TITLE_LINE
    )
    rule_y = last_head + 20
    if rule_offset is not None:
        if y + rule_offset + 1e-6 < rule_y:
            raise ValueError(f"{c.name}: card {name} needs a larger rule offset")
        rule_y = y + rule_offset
    body_y = rule_y + 38
    if lines:
        needed = (body_y - y) + (len(lines) - 1) * LINE + 22 + extra
    else:
        needed = rule_y - y + 10 + extra
    if measure_only:
        return needed, rule_y - y
    if h is None:
        h = needed
    elif h + 1e-6 < needed:
        raise ValueError(f"{c.name}: card {name} needs {needed} units of height")
    box = c.node(name, Box(x, y, w, h), parent)
    c.shape(
        "rect",
        x=x,
        y=y,
        w=w,
        h=h,
        rx=14,
        fill="tint" if tint else "card",
        stroke=accent,
        stroke_width=3,
        dash="12 8" if dashed else None,
    )
    if not dashed:
        c.shape("cap", x=x, y=y, w=w, h=14, rx=14, fill=accent)
    if number:
        badge(c, f"{name}-number", x + 38, y + 51, number, accent, parent=name)
    for index, line in enumerate(titles):
        c.text(
            title_x, title_base + index * TITLE_LINE, line, title_style, container=name
        )
    for index, line in enumerate(subtitles):
        c.text(x + pad, subtitle_base + index * 30, line, SUBTITLE, container=name)
    if lines:
        c.shape(
            "line",
            x1=x + pad,
            y1=rule_y,
            x2=x + w - pad,
            y2=rule_y,
            stroke="rule",
            width=2,
        )
        for index, line in enumerate(lines):
            c.text(x + pad, body_y + index * LINE, line, body_style, container=name)
    return CardLayout(box, x + pad, body_y + len(lines) * LINE, body_width)


def badge(
    c: Canvas,
    name: str,
    cx: float,
    cy: float,
    label: str,
    color: str,
    parent: str = "canvas",
    overlay: bool = False,
) -> Box:
    """Draw a filled circle with a short label, such as a step number."""
    radius = max(21.0, measure(label, BADGE) / 2 + 14)
    box = c.node(name, Box(cx - radius, cy - radius, 2 * radius, 2 * radius), parent)
    c.shape("circle", overlay=overlay, cx=cx, cy=cy, r=radius, fill=color)
    c.text(cx, cy + 8.5, label, BADGE, anchor="middle", container=name)
    return box


def card_row(
    c: Canvas,
    y: float,
    specs: list[dict],
    *,
    x: float = MARGIN,
    width: float | None = None,
    gap: float = 32,
) -> list[CardLayout]:
    """Draw equal-width, equal-height cards. Each spec holds card() arguments."""
    width = (c.width - 2 * MARGIN) if width is None else width
    count = len(specs)
    each = (width - (count - 1) * gap) / count

    def arguments(spec: dict) -> dict:
        return {k: v for k, v in spec.items() if k != "name"}

    offset = max(
        card(c, spec["name"], 0, y, each, **arguments(spec), measure_only=True)[1]
        for spec in specs
    )
    height = max(
        card(
            c,
            spec["name"],
            0,
            y,
            each,
            **arguments(spec),
            rule_offset=offset,
            measure_only=True,
        )[0]
        for spec in specs
    )
    layouts = []
    for index, spec in enumerate(specs):
        layouts.append(
            card(
                c,
                spec["name"],
                x + index * (each + gap),
                y,
                each,
                h=height,
                rule_offset=offset,
                **arguments(spec),
            )
        )
    return layouts


def pill(
    c: Canvas,
    name: str,
    x: float,
    y: float,
    label: str,
    color: str,
    *,
    anchor: str = "start",
    parent: str = "canvas",
) -> Box:
    width = measure(label, BADGE) + 34
    left = {"start": x, "middle": x - width / 2, "end": x - width}[anchor]
    box = c.node(name, Box(left, y, width, 38), parent)
    c.shape("rect", x=left, y=y, w=width, h=38, rx=19, fill=color)
    c.text(left + width / 2, y + 25.5, label, BADGE, anchor="middle", container=name)
    return box


def note(
    c: Canvas,
    name: str,
    y: float,
    label: str,
    body: str | list[str],
    *,
    x: float = MARGIN,
    w: float | None = None,
    style: Style = BODY,
) -> Box:
    w = c.width - 2 * MARGIN if w is None else w
    paragraphs = [body] if isinstance(body, str) else list(body)
    lines = []
    for paragraph in paragraphs:
        lines.extend(wrap(paragraph, style, w - 64))
    h = 58 + len(lines) * LINE + 6
    box = c.node(name, Box(x, y, w, h))
    c.shape("rect", x=x, y=y, w=w, h=h, rx=10, fill="note")
    c.shape("rect", x=x, y=y, w=10, h=h, rx=5, fill="saffron")
    c.text(x + 32, y + 38, label, SMALL, container=name)
    for index, line in enumerate(lines):
        c.text(x + 32, y + 76 + index * LINE, line, style, container=name)
    return box


def lines_at(
    c: Canvas,
    x: float,
    y: float,
    text: str | list[str],
    style: Style,
    width: float,
    container: str = "canvas",
    anchor: str = "start",
) -> float:
    paragraphs = [text] if isinstance(text, str) else list(text)
    offset = 0
    for paragraph in paragraphs:
        for line in wrap(paragraph, style, width):
            c.text(
                x, y + offset * LINE, line, style, anchor=anchor, container=container
            )
            offset += 1
    return y + offset * LINE


def legend_line(
    c: Canvas,
    name: str,
    x: float,
    y: float,
    label: str,
    color: str,
    *,
    dashed: bool = False,
) -> float:
    """Draw one legend sample and its label. Return the next free x."""
    c.node(name, Box(x, y - 22, 64, 30), solid=False)
    c.shape(
        "line",
        x1=x,
        y1=y - 8,
        x2=x + 56,
        y2=y - 8,
        stroke=color,
        width=4,
        dash="12 9" if dashed else None,
    )
    label_style = Style("sans", 25, 600, color="ink")
    c.text(x + 70, y, label, label_style)
    return x + 70 + measure(label, label_style) + 44


# ──────────────────────────────── diagrams ─────────────────────────────────

NOT_CERTIFICATION = "It is not release or certification evidence."
SDK_STATUS = "The local SDK 1.0.1 is released; applications and wire 1.0 remain UNRELEASED."


def system_map() -> Canvas:
    c = Canvas(
        "system-map",
        WIDTH,
        900,
        "NCP modular system map",
        "A host selects independent applications and connects each one through "
        "the NCP contract. NCP owns message identity, retained outcomes, "
        "acknowledgements, and bounded byte buffers. Each application owns its "
        f"own state. {SDK_STATUS} {NOT_CERTIFICATION}",
    )
    y = header(c, "SYSTEM MAP", "A host composes independent applications through NCP")
    host = card(
        c,
        "host",
        MARGIN,
        y + 6,
        WIDTH - 2 * MARGIN,
        "Host application",
        "Selects the peers, installs their exact contracts, sets deadlines and "
        "composition budgets, and owns process lifetime.",
        accent="lapis",
    ).box
    band_y = host.bottom + 74
    band = card(
        c,
        "ncp",
        MARGIN,
        band_y,
        WIDTH - 2 * MARGIN,
        "NCP contract and SDK",
        "Each exchange carries one exact request and one retained outcome. "
        "Rust and Python implement the contract independently. NCP runs no central process.",
        accent="turquoise",
        tint=True,
        extra=58,
    ).box
    chips = (
        "Exact requests",
        "Retained outcomes",
        "Digest acknowledgements",
        "Bounded byte buffers",
    )
    chip_x = MARGIN + 26
    for index, label in enumerate(chips):
        box = pill(
            c,
            f"chip-{index}",
            chip_x,
            band.bottom - 60,
            label,
            "turquoise",
            parent="ncp",
        )
        chip_x = box.right + 18
    c.connector(
        "host-ncp", [(host.cx, host.bottom), (host.cx, band.y)], "host", "ncp", "lapis"
    )
    c.text(host.cx + 18, host.bottom + 45, "selects and installs", SMALL)
    apps = [
        dict(
            name="engram",
            title="Engram",
            subtitle="Neural application",
            body="Persistent NEST network, typed currents, and delayed spike-count readouts.",
        ),
        dict(
            name="crebain",
            title="CREBAIN",
            subtitle="Bodies and sensors",
            body="Body dynamics, sensor production, and native checkpoint state.",
        ),
        dict(
            name="prisoma",
            title="Prisoma",
            subtitle="Capture and experiments",
            body="Original-byte capture, experiment order, forecasts, and labels.",
        ),
        dict(
            name="galadriel",
            title="Galadriel",
            subtitle="Consistency monitor",
            body="Advisory evidence or abstention without command authority. "
            "Its modular adapter is open work.",
            accent="muted",
            dashed=True,
        ),
    ]
    app_y = band.bottom + 96
    layouts = card_row(c, app_y, apps)
    for layout, spec in zip(layouts, apps):
        box = layout.box
        optional = spec["name"] == "galadriel"
        c.connector(
            f"ncp-{spec['name']}",
            [(box.cx, band.bottom), (box.cx, box.y)],
            "ncp",
            spec["name"],
            "muted" if optional else "turquoise",
            dashed=optional,
            arrow_start=True,
        )
    tallest = layouts[0].box.h
    bottom = app_y + tallest
    c.height = (
        note(
            c,
            "boundary",
            bottom + 34,
            "BOUNDARY",
            "Each application stays optional. A selected composition must satisfy the "
            "contract and resource limits of every participant. A missing observation "
            "never becomes a zero value.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def lifeline(c: Canvas, name: str, cx: float, top: float, bottom: float) -> Box:
    """Register a lifeline as a thin box so messages attach to its sides."""
    box = c.node(name, Box(cx - 6, top, 12, bottom - top))
    c.shape(
        "line", x1=cx, y1=top, x2=cx, y2=bottom, stroke="muted", width=3, dash="4 8"
    )
    return box


def message(
    c: Canvas,
    name: str,
    source: Box,
    target: Box,
    y: float,
    label: str,
    source_name: str,
    target_name: str,
    color: str = "turquoise",
    dashed: bool = False,
) -> None:
    if source.cx < target.cx:
        points = [(source.right, y), (target.x, y)]
    else:
        points = [(source.x, y), (target.right, y)]
    c.connector(name, points, source_name, target_name, color, dashed=dashed)
    middle = (points[0][0] + points[1][0]) / 2
    c.text(middle, y - 16, label, Style("sans", 25, 600, color="ink"), anchor="middle")


def exchange() -> Canvas:
    c = Canvas(
        "exchange",
        WIDTH,
        1200,
        "NCP modular request and outcome exchange",
        "A client sends one exact request. The owner returns retained bytes for an "
        "exact duplicate, admits new work without side effects, reserves storage, "
        "executes once, and retains the outcome until an exact acknowledgement. "
        f"{SDK_STATUS} {NOT_CERTIFICATION}",
    )
    y = header(
        c, "MODULAR EXCHANGE", "One request, one retained outcome, one acknowledgement"
    )
    step_x = 900
    step_w = WIDTH - MARGIN - step_x
    client_head = card(
        c,
        "client",
        MARGIN,
        y + 6,
        330,
        "Client",
        subtitle="Caller with one pending slot",
    ).box
    owner_head = card(
        c,
        "owner",
        step_x,
        y + 6,
        step_w,
        "Owner",
        subtitle="Closed application owner",
        accent="turquoise",
    ).box
    steps = [
        ("1", "Exact duplicate", "Return the retained bytes. Do not execute again."),
        (
            "2",
            "Pure admission",
            "A rejection leaves the sequence number unused and state unchanged.",
        ),
        (
            "3",
            "Reserve",
            "Resolve inputs and allocate outputs before the sequence number is consumed.",
        ),
        (
            "4",
            "Execute once",
            "Consume the sequence number. A later failure retires the generation.",
        ),
        (
            "5",
            "Retain outcome",
            "Keep the result frame until its exact acknowledgement.",
        ),
        (
            "6",
            "Release frame",
            "The acknowledgement frees the result frame, not the buffers.",
        ),
    ]
    boxes = []
    cursor = owner_head.bottom + 30
    for number, title, body in steps:
        layout = card(
            c,
            f"step-{number}",
            step_x,
            cursor,
            step_w,
            title,
            body,
            number=number,
            accent="lapis" if number == "4" else "turquoise",
        )
        boxes.append(layout.box)
        cursor = layout.box.bottom + 14
    bottom = cursor + 52
    client_line = lifeline(c, "client-line", client_head.cx, client_head.bottom, bottom)
    owner_line = lifeline(c, "owner-line", step_x - 36, owner_head.bottom - 60, bottom)
    c.shape(
        "line",
        x1=step_x - 36,
        y1=owner_head.bottom - 60,
        x2=step_x,
        y2=owner_head.bottom - 60,
        stroke="muted",
        width=3,
        dash="4 8",
    )
    message(
        c,
        "request",
        client_line,
        owner_line,
        boxes[0].y + 50,
        "request: binding, sequence, operation, digest",
        "client-line",
        "owner-line",
        "lapis",
    )
    message(
        c,
        "outcome",
        owner_line,
        client_line,
        boxes[4].y + 50,
        "retained outcome",
        "owner-line",
        "client-line",
    )
    message(
        c,
        "ack",
        client_line,
        owner_line,
        boxes[5].y + 50,
        "acknowledge with the outcome digest",
        "client-line",
        "owner-line",
        "lapis",
    )
    message(
        c,
        "next",
        client_line,
        owner_line,
        bottom - 22,
        "next request names that outcome as predecessor",
        "client-line",
        "owner-line",
        "lapis",
    )
    c.height = (
        note(
            c,
            "boundary",
            bottom + 26,
            "UNCERTAIN DISPATCH",
            "A lost response or acknowledgement keeps the pending evidence. The client "
            "stops that channel. It never retries or reconnects on its own. A query can "
            "read the original retained bytes by sequence and request digest.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def payload_transfer() -> Canvas:
    c = Canvas(
        "payload-transfer",
        WIDTH,
        1100,
        "NCP bounded payload transfer",
        "A receiver reserves the complete declared length, admits only the next "
        "verified chunk, and seals the payload after the complete SHA-256 digest "
        "matches. Chunks are at most 32,768 bytes and payloads at most 8,388,608 bytes. "
        f"{SDK_STATUS} {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "PAYLOAD TRANSFER",
        "Reserve first, then admit verified chunks in order",
        "IMPLEMENTED SDK",
        "turquoise",
    )
    left = card(
        c,
        "producer",
        MARGIN,
        y + 6,
        400,
        "Producer buffer",
        subtitle="Sealed, owned bytes",
        body="The byte manifest binds the length, the payload SHA-256, and the semantic digest.",
    ).box
    right = card(
        c,
        "receiver",
        WIDTH - MARGIN - 400,
        y + 6,
        400,
        "Receiver import",
        subtitle="Reserve, admit, seal",
        body="Reserve the full length first. Seal only when the complete SHA-256 matches.",
        accent="turquoise",
        h=left.h,
    ).box
    strip_x = left.right + 60
    strip_w = right.x - 60 - strip_x
    strip = c.node("chunks", Box(strip_x, left.y + 40, strip_w, 150))
    c.shape(
        "rect",
        x=strip.x,
        y=strip.y,
        w=strip.w,
        h=strip.h,
        rx=14,
        fill="card",
        stroke="rule",
        stroke_width=2,
    )
    c.text(
        strip.x + 24, strip.y + 40, "chunks in index order", LABEL, container="chunks"
    )
    labels = ("0", "1", "2", "…", "last")
    cell_w = (strip.w - 48 - 4 * 14) / 5
    for index, label in enumerate(labels):
        x = strip.x + 24 + index * (cell_w + 14)
        cell = c.node(
            f"cell-{index}", Box(x, strip.y + 66, cell_w, 56), parent="chunks"
        )
        c.shape(
            "rect",
            x=cell.x,
            y=cell.y,
            w=cell.w,
            h=cell.h,
            rx=8,
            fill="tint" if label != "…" else "card",
            stroke="turquoise",
            stroke_width=2,
        )
        c.text(
            cell.cx,
            cell.y + 37,
            label,
            Style("sans", 25, 700, color="ink"),
            anchor="middle",
            container=f"cell-{index}",
        )
    c.connector(
        "to-strip", [(left.right, strip.cy), (strip.x, strip.cy)], "producer", "chunks"
    )
    c.connector(
        "to-receiver",
        [(strip.right, strip.cy), (right.x, strip.cy)],
        "chunks",
        "receiver",
    )
    checks_y = max(left.bottom, right.bottom) + 40
    checks = card_row(
        c,
        checks_y,
        [
            dict(
                name="check-chunk",
                title="Each chunk",
                number="1",
                body="Index, offset, decoded length, canonical base64, and chunk SHA-256 must match.",
            ),
            dict(
                name="check-seal",
                title="Seal",
                number="2",
                body="The complete payload SHA-256 must match. Valid chunk digests cannot replace it.",
            ),
            dict(
                name="check-count",
                title="Chunk count",
                number="3",
                body="The count is the length divided by 32,768 bytes, rounded up. A payload of at most 8,388,608 bytes needs at most 256 chunks.",
            ),
        ],
    )
    c.height = (
        note(
            c,
            "boundary",
            checks[0].box.bottom + 34,
            "LIFETIMES",
            "An acknowledgement releases the result frame only. Buffer release and import "
            "abort are separate operations on one exact named entry. A failed admission "
            "keeps counters, reservations, and stored bytes unchanged.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def evidence_ladder() -> Canvas:
    c = Canvas(
        "evidence-ladder",
        WIDTH,
        1200,
        "NCP evidence classes and permitted claims",
        "Five evidence classes run from source controls to release. Each class "
        "permits only its own claim. The NCP 1.0 candidate has local and selected "
        "native evidence. Its independent and external gates are NOT RUN, and it is "
        f"UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "EVIDENCE CLASSES", "Each claim needs evidence of its own class")
    rungs = [
        (
            "5",
            "Release",
            "Immutable tag, signed artifacts, and provenance.",
            "No wire 1.0 release exists. The latest wire release is v0.8.0 on wire 0.8.",
            "NONE",
            "pomegranate",
        ),
        (
            "4",
            "Independent and external qualification",
            "Live security, independent peers, faults, soak, performance, and supply chain.",
            "All ten external release gates of the 1.0 candidate are NOT RUN.",
            "NOT RUN",
            "pomegranate",
        ),
        (
            "3",
            "Installed native observation",
            "A dated campaign with exact artifacts, configuration, and retained failures.",
            "Permits the observed configuration and workload only.",
            "SELECTED CASES",
            "bronze",
        ),
        (
            "2",
            "Complete local gate",
            "One run of scripts/check.sh on one fixed source cut.",
            "Permits local regression evidence for that cut only.",
            "LOCAL",
            "turquoise",
        ),
        (
            "1",
            "Source controls",
            "Unit, property, and cross-language tests on named sources.",
            "Permits the tested behavior of that source only.",
            "IN CI",
            "turquoise",
        ),
    ]
    cursor = y + 10
    for number, title, what, claim, status, color in rungs:
        tag_width = measure(status, BADGE) + 34
        layout = card(
            c,
            f"rung-{number}",
            MARGIN,
            cursor,
            WIDTH - 2 * MARGIN,
            title,
            [what, claim],
            number=number,
            accent=color if color != "bronze" else "lapis",
            extra=0,
        )
        pill(
            c,
            f"tag-{number}",
            WIDTH - MARGIN - 26,
            cursor + 32,
            status,
            color,
            anchor="end",
            parent=f"rung-{number}",
        )
        del tag_width
        cursor = layout.box.bottom + 16
    c.height = (
        note(
            c,
            "boundary",
            cursor + 18,
            "RULE",
            "A lower class never promotes a claim to a higher class. Protocol success does "
            "not establish physical safety, controller stability, or scientific validity.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def closed_loop() -> Canvas:
    c = Canvas(
        "closed-loop",
        WIDTH,
        1200,
        "NCP closed-loop evidence boundary",
        "A feedback cycle runs from plant state through sensing, a retained source "
        "record, a controller proposal, body admission, and disposition to actuator "
        "input. NCP records three software events. It cannot measure the physical "
        f"response or establish stability. UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "CLOSED LOOP", "Protocol success does not establish loop stability")
    c.text(
        MARGIN,
        y + 12,
        "Tinted boxes mark the three software events that NCP records.",
        SMALL,
    )
    y += 34
    gap = 60
    top = [
        dict(name="plant", title="Plant", body="State x at sample k."),
        dict(
            name="sensor",
            title="Sensor",
            body="Observation from state and disturbance.",
        ),
        dict(
            name="source",
            title="Source record",
            body="Retained at the sample time.",
            tint=True,
            accent="turquoise",
        ),
        dict(
            name="controller",
            title="Controller",
            body="Proposes an action from the record.",
        ),
    ]
    row1 = card_row(c, y + 6, top, gap=gap)
    bottom = [
        dict(
            name="response",
            title="Physical response",
            body="Outside the software record.",
            dashed=True,
            accent="muted",
        ),
        dict(
            name="input", title="Actuator input", body="The plant input u at sample k."
        ),
        dict(
            name="disposition",
            title="Disposition",
            body="Terminal software outcome.",
            tint=True,
            accent="turquoise",
        ),
        dict(
            name="admission",
            title="Body admission",
            body="Accepts before the exclusive deadline.",
            tint=True,
            accent="turquoise",
        ),
    ]
    row2_y = row1[0].box.bottom + 120
    row2 = card_row(c, row2_y, bottom, gap=gap)
    names1 = [spec["name"] for spec in top]
    for a, b, first, second in zip(row1, row1[1:], names1, names1[1:]):
        c.connector(
            f"{first}-{second}",
            [(a.box.right, a.box.cy), (b.box.x, b.box.cy)],
            first,
            second,
        )
    names2 = [spec["name"] for spec in bottom]
    for a, b, first, second in zip(row2[1:], row2, names2[1:], names2):
        c.connector(
            f"{first}-{second}",
            [(a.box.x, a.box.cy), (b.box.right, b.box.cy)],
            first,
            second,
        )
    c.connector(
        "controller-admission",
        [(row1[3].box.cx, row1[3].box.bottom), (row2[3].box.cx, row2[3].box.y)],
        "controller",
        "admission",
    )
    c.connector(
        "response-plant",
        [(row2[0].box.cx, row2[0].box.y), (row1[0].box.cx, row1[0].box.bottom)],
        "response",
        "plant",
        "muted",
        dashed=True,
    )
    c.text(row1[3].box.cx + 20, row1[3].box.bottom + 68, "proposal", SMALL)
    c.text(row1[0].box.cx + 20, row1[0].box.bottom + 68, "next state", SMALL)
    timing = card_row(
        c,
        row2[0].box.bottom + 44,
        [
            dict(
                name="latency",
                title="Latency on one body clock",
                number="1",
                body=[
                    "Admission latency = admission time − sample time.",
                    "Disposition latency = disposition time − sample time.",
                ],
            ),
            dict(
                name="deadline",
                title="Exclusive deadline",
                number="2",
                body=[
                    "Admission at time t is live only when t\u00a0<\u00a0deadline.",
                    "A missing event is undefined, never zero.",
                ],
            ),
        ],
    )
    c.height = (
        note(
            c,
            "boundary",
            timing[0].box.bottom + 34,
            "STABILITY",
            "Stability depends on the plant, controller, sampling, and delay. For the update "
            "x(k+1) = (1 − 2Δ) x(k), a period Δ of 0.1 s keeps 80 percent of the error per "
            "step. A period of 1 s flips its sign without decay. Message delivery is the "
            "same in both cases.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def queue_admission() -> Canvas:
    c = Canvas(
        "queue-admission",
        WIDTH,
        1200,
        "NCP finite plane queue admission",
        "Each plane queue limits both item count and retained bytes. A plane policy "
        "selects allowed victims or rejects. One atomic owner step records the loss, "
        "removes victims, and installs the item. This is proposed design for the "
        f"UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c, "PLANE QUEUE", "Each queue limits both items and bytes", "PROPOSED DESIGN"
    )
    item = card(
        c,
        "item",
        MARGIN,
        y + 40,
        330,
        "New item",
        subtitle="Size in bytes",
        body="The policy examines the item before it retains any byte.",
    ).box
    queue_x = item.right + 80
    queue = c.node("queue", Box(queue_x, y + 40, 560, item.h))
    c.shape(
        "rect",
        x=queue.x,
        y=queue.y,
        w=queue.w,
        h=queue.h,
        rx=14,
        fill="card",
        stroke="lapis",
        stroke_width=3,
    )
    c.shape("cap", x=queue.x, y=queue.y, w=queue.w, h=14, rx=14, fill="lapis")
    c.text(queue.x + 26, queue.y + 60, "Plane queue", TITLE, container="queue")
    c.text(
        queue.x + 26,
        queue.y + 92,
        "Item limit and byte limit",
        SUBTITLE,
        container="queue",
    )
    slot_w = (queue.w - 52 - 5 * 12) / 6
    for index in range(6):
        x = queue.x + 26 + index * (slot_w + 12)
        filled = index < 4
        slot = c.node(
            f"slot-{index}", Box(x, queue.y + 122, slot_w, 52), parent="queue"
        )
        c.shape(
            "rect",
            x=slot.x,
            y=slot.y,
            w=slot.w,
            h=slot.h,
            rx=8,
            fill="tint" if filled else "card",
            stroke="lapis" if filled else "rule",
            stroke_width=2,
        )
    decision = card(
        c,
        "decision",
        queue.right + 80,
        y + 40,
        WIDTH - MARGIN - queue.right - 80,
        "Admission",
        body=[
            "Admit in one atomic step.",
            "Otherwise reject.",
            "The queue stays unchanged.",
        ],
        accent="turquoise",
        h=item.h,
    ).box
    c.connector(
        "item-queue", [(item.right, item.cy), (queue.x, item.cy)], "item", "queue"
    )
    c.connector(
        "queue-decision",
        [(queue.right, item.cy), (decision.x, item.cy)],
        "queue",
        "decision",
    )
    checks = card_row(
        c,
        item.bottom + 44,
        [
            dict(
                name="check-count",
                title="Count",
                number="1",
                body="After the victims leave, one more item must fit the item limit.",
            ),
            dict(
                name="check-bytes",
                title="Bytes",
                number="2",
                body="After the victim bytes leave, the new bytes must fit the byte limit.",
            ),
            dict(
                name="check-loss",
                title="Visible loss",
                number="3",
                body="The loss count plus the victims must fit the loss limit.",
            ),
        ],
    )
    policy = card(
        c,
        "policy",
        MARGIN,
        checks[0].box.bottom + 34,
        WIDTH - 2 * MARGIN,
        "Victim policy by plane",
        body=[
            "Control and extension: select no victim and reject when full.",
            "Perception: replace the latest replaceable item.",
            "Observation: drop the oldest items and count each gap.",
            "Action: displace only work that the severity order permits.",
        ],
        accent="lapis",
    ).box
    c.height = (
        note(
            c,
            "boundary",
            policy.bottom + 34,
            "ISOLATION",
            "No plane borrows the count, byte, or local charge of another plane. "
            "Observation pressure cannot consume reserved action capacity.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def overview() -> Canvas:
    c = Canvas(
        "overview",
        WIDTH,
        1200,
        "NCP admission and plane overview",
        "Five shared gates bound raw bytes, authenticate the transport principal, "
        "check wire and stable core, check session and stream state, and deliver a "
        "typed frame to a finite plane queue. Action adds a body effect gate. "
        f"Proposed design for the UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "ADMISSION OVERVIEW",
        "Five shared gates run in order, and actions add a body gate",
        "PROPOSED DESIGN",
    )
    gates = card_row(
        c,
        y + 10,
        [
            dict(
                name="gate-1",
                title_style=TITLE_NARROW,
                title="Bound raw bytes",
                number="1",
                body="Frame size, depth, and members before semantic allocation.",
            ),
            dict(
                name="gate-2",
                title_style=TITLE_NARROW,
                title="Authenticate",
                number="2",
                body="Verified transport principal and default-deny manifest.",
            ),
            dict(
                name="gate-3",
                title_style=TITLE_NARROW,
                title="Wire and core",
                number="3",
                body="Canonical same-major version and exact stable core.",
            ),
            dict(
                name="gate-4",
                title_style=TITLE_NARROW,
                title="Session and stream",
                number="4",
                body="Live generation, declared epoch, and unused position.",
            ),
            dict(
                name="gate-5",
                title_style=TITLE_NARROW,
                title="Typed delivery",
                number="5",
                body="Prepared layout into one finite plane queue.",
            ),
        ],
        gap=48,
    )
    for index in range(4):
        a, b = gates[index].box, gates[index + 1].box
        c.connector(
            f"gate-{index + 1}-{index + 2}",
            [(a.right, a.cy), (b.x, a.cy)],
            f"gate-{index + 1}",
            f"gate-{index + 2}",
        )
    last = gates[4].box
    effect = card(
        c,
        "gate-6",
        last.x,
        last.bottom + 110,
        last.w,
        "Body effect gate",
        "The body admits the exact command before executor work.",
        number="6",
        accent="lapis",
        tint=True,
    ).box
    c.connector(
        "action-only", [(last.cx, last.bottom), (last.cx, effect.y)], "gate-5", "gate-6"
    )
    c.text(last.cx - 18, last.bottom + 64, "action only", SMALL, anchor="end")
    planes = card(
        c,
        "planes",
        MARGIN,
        last.bottom + 110,
        last.x - 48 - MARGIN,
        "Four core planes",
        body=[
            "Control: commander and body exchange bounded requests. Overflow rejects.",
            "Perception: the body publishes samples. The latest sample replaces older ones.",
            "Action: the lease holder or an enrolled emergency source commands the body.",
            "Observation: the body feeds read-only observers. The oldest item drops first.",
        ],
        h=None,
    ).box
    c.height = (
        note(
            c,
            "status-note",
            max(planes.bottom, effect.bottom) + 34,
            "CURRENT STATUS",
            "Direct production-secure Zenoh ingress fails closed. The pinned Zenoh 1.9.0 "
            "callback does not expose the verified peer principal.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def topology() -> Canvas:
    c = Canvas(
        "topology",
        WIDTH,
        1200,
        "NCP commander, body, and observer topology",
        "A commander and a body exchange control, perception, and action traffic on "
        "four core planes. Observers receive a read-only projection. The body is the "
        "final software authority before the actuator. Candidate wire of the "
        f"UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "TOPOLOGY",
        "Four core planes connect a commander, a body, and observers",
        "CANDIDATE WIRE 1.0",
    )
    lane_top = y + 40
    pitch = 118
    height = 3 * pitch + 40
    commander = card(
        c,
        "commander",
        MARGIN,
        lane_top,
        330,
        "Commander",
        subtitle="Neural or other controller",
        body="Sends Active only with the body-issued lease.",
        h=height,
    ).box
    body = card(
        c,
        "body",
        WIDTH - MARGIN - 330,
        lane_top,
        330,
        "Body",
        subtitle="Robot or UAV plant",
        body=[
            "Final software authority before the actuator.",
            "Role qualification: NOT RUN.",
        ],
        accent="turquoise",
        h=height,
    ).box
    label = Style("sans", 25, 600, color="ink")
    route = Style("sans", 25, 400, color="muted")
    lanes = [
        ("control", "Control: request and reply", RPC_ROUTE, "lapis", True, True),
        (
            "perception",
            "Perception: body to commander",
            SENSOR_ROUTE,
            "turquoise",
            False,
            True,
        ),
        (
            "action",
            "Action: ACTIVE, HOLD, ESTOP. Init rejects.",
            COMMAND_ROUTE,
            "lapis",
            True,
            False,
        ),
    ]
    for index, (name, title, key, color, forward, backward) in enumerate(lanes):
        yy = lane_top + 96 + index * pitch
        points = [(commander.right, yy), (body.x, yy)]
        if forward and not backward:
            c.connector(name, points, "commander", "body", color)
        elif backward and not forward:
            c.connector(name, list(reversed(points)), "body", "commander", color)
        else:
            c.connector(name, points, "commander", "body", color, arrow_start=True)
        middle = (commander.right + body.x) / 2
        c.text(middle, yy - 52, title, label, anchor="middle")
        c.text(middle, yy - 18, key, route, anchor="middle")
    observer = card(
        c,
        "observer",
        WIDTH - MARGIN - 330,
        commander.bottom + 130,
        330,
        "Observer",
        subtitle="Read-only, grant-bound",
        body="Receives a projection. Holds no command authority.",
    ).box
    c.connector(
        "observation",
        [(body.cx, body.bottom), (body.cx, observer.y)],
        "body",
        "observer",
        "turquoise",
    )
    c.text(
        body.cx - 24,
        body.bottom + 54,
        "Observation: body to observers",
        label,
        anchor="end",
    )
    c.text(body.cx - 24, body.bottom + 88, OBSERVATION_ROUTE, route, anchor="end")
    c.height = (
        note(
            c,
            "trust",
            observer.bottom + 34,
            "TRUST BOUNDARY",
            "A direct peer binds the verified transport principal. A forwarder ends one "
            "trust context and opens a new authenticated one. Copied identity bytes are "
            "not transport evidence.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def runtime() -> Canvas:
    c = Canvas(
        "runtime",
        WIDTH,
        1200,
        "NCP prepared runtime and hot path",
        "Preparation compiles immutable handles once. Each frame then passes six "
        "stages: bound, verify, decode once, locate, admit in one short owner step, "
        "and hand off to a finite queue. Proposed design for the UNRELEASED 1.0 "
        f"candidate. Stage ceilings are targets, not measurements. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "PREPARED RUNTIME",
        "Prepare once, then bound, decode, and admit each frame",
        "PROPOSED DESIGN",
    )
    prepare = card(
        c,
        "prepare",
        MARGIN,
        y + 10,
        WIDTH - 2 * MARGIN,
        "Prepare once",
        "Validate the manifest, security snapshot, routes, layouts, and queue and deadline "
        "profiles. Compile immutable handles and reserve shared state before any publisher "
        "or callback exists.",
        accent="turquoise",
        tint=True,
    ).box
    c.text(MARGIN, prepare.bottom + 48, "Each later frame follows this path:", SMALL)
    stages = card_row(
        c,
        prepare.bottom + 72,
        [
            dict(
                name="stage-1",
                title_style=TITLE_NARROW,
                title="Bound",
                number="1",
                body="Check the size before any allocation.",
            ),
            dict(
                name="stage-2",
                title_style=TITLE_NARROW,
                title="Verify",
                number="2",
                body="Resolve the ingress capability.",
            ),
            dict(
                name="stage-3",
                title_style=TITLE_NARROW,
                title="Decode",
                number="3",
                body="Decode once with the prepared layout.",
            ),
            dict(
                name="stage-4",
                title_style=TITLE_NARROW,
                title="Locate",
                number="4",
                body="Find route, session, and position.",
            ),
            dict(
                name="stage-5",
                title_style=TITLE_NARROW,
                title="Admit",
                number="5",
                body="Apply one short owner step.",
                accent="lapis",
            ),
            dict(
                name="stage-6",
                title_style=TITLE_NARROW,
                title="Hand off",
                number="6",
                body="Enqueue after the unlock.",
            ),
        ],
        gap=44,
    )
    for index in range(5):
        a, b = stages[index].box, stages[index + 1].box
        c.connector(
            f"stage-{index + 1}-{index + 2}",
            [(a.right, a.cy), (b.x, a.cy)],
            f"stage-{index + 1}",
            f"stage-{index + 2}",
        )
    notes = card_row(
        c,
        stages[0].box.bottom + 40,
        [
            dict(
                name="outside",
                title="Outside the hot path",
                body="Storage, backend queries, network calls, application callbacks, and device I/O.",
                accent="muted",
            ),
            dict(
                name="cost",
                title="Cost model",
                body="Hot-path time is the sum of the six stage times. Each stage has a selected "
                "ceiling. The sum of the ceilings bounds the path.",
                accent="lapis",
            ),
        ],
    )
    c.height = notes[0].box.bottom + 40
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def lifecycle() -> Canvas:
    c = Canvas(
        "lifecycle",
        WIDTH,
        1200,
        "NCP session lifecycle mutation owner",
        "One slot per namespace moves from free to pending, then to terminal directly "
        "or through ambiguous reconciliation. Terminal commit publishes the result and "
        "high-water before it frees the slot. Exact retries return the retained result. "
        f"Proposed design for the UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "SESSION LIFECYCLE",
        "One slot serializes open, replace, and close per namespace",
        "PROPOSED DESIGN",
    )
    states = card_row(
        c,
        y + 110,
        [
            dict(name="free", title="FREE", body="No active record."),
            dict(
                name="pending",
                title="PENDING",
                body="Durable reservation. Work can run.",
                accent="turquoise",
            ),
            dict(
                name="ambiguous",
                title="AMBIGUOUS",
                body="Effect unknown. Same operation fenced.",
                accent="pomegranate",
            ),
            dict(
                name="terminal",
                title="TERMINAL",
                body="Result and high-water are durable.",
                accent="turquoise",
                tint=True,
            ),
        ],
        gap=110,
    )
    free, pending, ambiguous, terminal = (layout.box for layout in states)

    def lettered(name: str, letter: str, x: float, yy: float, color: str) -> str:
        badge(c, name, x, yy, letter, color, overlay=True)
        return name

    ya = free.cy
    a = lettered("badge-a", "A", (free.right + pending.x) / 2, ya, "lapis")
    c.connector(
        "reserve", [(free.right, ya), (pending.x, ya)], "free", "pending", through=(a,)
    )
    b = lettered("badge-c", "C", (pending.right + ambiguous.x) / 2, ya, "pomegranate")
    c.connector(
        "unknown",
        [(pending.right, ya), (ambiguous.x, ya)],
        "pending",
        "ambiguous",
        "pomegranate",
        through=(b,),
    )
    d = lettered("badge-d", "D", (ambiguous.right + terminal.x) / 2, ya, "turquoise")
    c.connector(
        "reconcile",
        [(ambiguous.right, ya), (terminal.x, ya)],
        "ambiguous",
        "terminal",
        through=(d,),
    )
    top = pending.y - 62
    e = lettered("badge-b", "B", (pending.cx + terminal.cx) / 2, top, "turquoise")
    c.connector(
        "definitive",
        [
            (pending.cx, pending.y),
            (pending.cx, top),
            (terminal.cx, top),
            (terminal.cx, terminal.y),
        ],
        "pending",
        "terminal",
        through=(e,),
    )
    low = free.bottom + 62
    f = lettered("badge-e", "E", (free.cx + terminal.cx) / 2, low, "lapis")
    c.connector(
        "release",
        [
            (terminal.cx, terminal.bottom),
            (terminal.cx, low),
            (free.cx, low),
            (free.cx, free.bottom),
        ],
        "terminal",
        "free",
        "lapis",
        through=(f,),
    )
    legend = card(
        c,
        "legend",
        MARGIN,
        low + 50,
        WIDTH - 2 * MARGIN,
        "Transitions",
        body=[
            "A reserve: make the slot, result cell, and context durable before external work.",
            "B definitive result: commit the terminal record.",
            "C effect unknown: keep the same operation and coordinate fenced.",
            "D reconcile: query the same backend coordinate, then commit.",
            "E release: publish the result and high-water, then free the slot.",
        ],
    ).box
    rules = card_row(
        c,
        legend.bottom + 34,
        [
            dict(
                name="retry",
                title="Exact retry",
                accent="turquoise",
                body="Equal coordinate, request bytes, context bytes, and ordinal return the retained result.",
            ),
            dict(
                name="conflict",
                title="Conflict",
                accent="pomegranate",
                body="Any other combination rejects without mutation.",
            ),
            dict(
                name="capacity",
                title="Capacity failure",
                accent="muted",
                body="A full store rejects with no state and no external effect.",
            ),
        ],
    )
    c.height = (
        note(
            c,
            "shape",
            rules[0].box.bottom + 34,
            "SERVICE SHAPE",
            "Shared finite stores serve all namespaces. No thread, socket, or "
            "store exists per session.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def sequence() -> Canvas:
    c = Canvas(
        "sequence",
        WIDTH,
        1200,
        "NCP simulation session sequence",
        "A client opens one simulation session after the wire and stable-core check. "
        "The simulator reserves a step window, executes positions strictly in order, "
        "and matches each result by generation, position, and request digest. "
        f"Proposed design for the UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "SIMULATION SESSION",
        "Steps run in position order and replies match exactly",
        "PROPOSED DESIGN",
    )
    step_x = 900
    step_w = WIDTH - MARGIN - step_x
    client = card(
        c,
        "client",
        MARGIN,
        y + 6,
        330,
        "Client",
        subtitle="Authorized simulation caller",
    ).box
    sim = card(
        c,
        "simulator",
        step_x,
        y + 6,
        step_w,
        "Simulator",
        subtitle="Bounded simulation service",
        accent="turquoise",
    ).box
    steps = [
        (
            "1",
            "Check identity",
            "Accept a canonical same-major wire and the exact stable core.",
        ),
        (
            "2",
            "Prepare the window",
            "Reserve request slots, response slots, and digest entries first.",
        ),
        (
            "3",
            "Execute in order",
            "Start only the next position. An unresolved call retires the generation.",
        ),
        (
            "4",
            "Match exactly",
            "Compare generation, position, digest, and the retained request bytes.",
        ),
        ("5", "Close", "Stop new steps, settle reserved work, and return a receipt."),
    ]
    boxes = []
    cursor = sim.bottom + 30
    for number, title, body in steps:
        layout = card(
            c,
            f"step-{number}",
            step_x,
            cursor,
            step_w,
            title,
            body,
            number=number,
            accent="turquoise",
        )
        boxes.append(layout.box)
        cursor = layout.box.bottom + 14
    bottom = cursor + 10
    client_line = lifeline(c, "client-line", client.cx, client.bottom, bottom)
    sim_line = lifeline(c, "sim-line", step_x - 36, sim.bottom - 60, bottom)
    c.shape(
        "line",
        x1=step_x - 36,
        y1=sim.bottom - 60,
        x2=step_x,
        y2=sim.bottom - 60,
        stroke="muted",
        width=3,
        dash="4 8",
    )
    message(
        c,
        "open",
        client_line,
        sim_line,
        boxes[0].y + 50,
        "open: version and stable core",
        "client-line",
        "sim-line",
        "lapis",
    )
    message(
        c,
        "opened",
        sim_line,
        client_line,
        boxes[1].y + 50,
        "opened: generation and step window",
        "sim-line",
        "client-line",
    )
    message(
        c,
        "steps",
        client_line,
        sim_line,
        boxes[2].y + 50,
        "steps at positions p, p + 1, p + 2",
        "client-line",
        "sim-line",
        "lapis",
    )
    message(
        c,
        "results",
        sim_line,
        client_line,
        boxes[3].y + 50,
        "result for each position",
        "sim-line",
        "client-line",
    )
    message(
        c,
        "close",
        client_line,
        sim_line,
        boxes[4].y + 50,
        "close, then receipt",
        "client-line",
        "sim-line",
        "lapis",
    )
    c.height = (
        note(
            c,
            "provenance",
            bottom + 26,
            "PROVENANCE",
            "Every result carries is_simulation_output = true and "
            "calibrated_posterior = false. Simulation output never becomes plant "
            "authority.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def admission() -> Canvas:
    c = Canvas(
        "admission",
        WIDTH,
        1300,
        "NCP body command admission",
        "The body bounds, authenticates, and decodes each command once, finds its exact "
        "position, and checks the live grant. ESTOP selects a preallocated latch, HOLD "
        "cuts Active authority, and Active needs a single-use token. Proposed design "
        f"for the UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "BODY COMMAND ADMISSION",
        "The body decides each command before any effect",
        "PROPOSED DESIGN",
    )
    row = card_row(
        c,
        y + 10,
        [
            dict(
                name="raw",
                title_style=TITLE_NARROW,
                title="Raw bounds",
                number="1",
                body="Size and frame class first.",
            ),
            dict(
                name="auth",
                title_style=TITLE_NARROW,
                title="Authenticate",
                number="2",
                body="Principal and exact permission.",
            ),
            dict(
                name="state",
                title_style=TITLE_NARROW,
                title="Session state",
                number="3",
                body="Generation, stream, and security.",
            ),
            dict(
                name="decode",
                title_style=TITLE_NARROW,
                title="Decode once",
                number="4",
                body="One bounded decode.",
            ),
            dict(
                name="position",
                title_style=TITLE_NARROW,
                title="Exact position",
                number="5",
                body="Same bytes return the result.",
            ),
        ],
        gap=48,
    )
    names = ["raw", "auth", "state", "decode", "position"]
    for a, b, first, second in zip(row, row[1:], names, names[1:]):
        c.connector(
            f"{first}-{second}",
            [(a.box.right, a.box.cy), (b.box.x, a.box.cy)],
            first,
            second,
        )
    last = row[4].box
    column_top = last.bottom + 90
    grant_w = 330
    grant_x = WIDTH - MARGIN - grant_w
    modes_x = MARGIN + 360 + 90
    modes_w = grant_x - 90 - modes_x
    modes = []
    cursor = column_top
    for name, title, body, color in (
        (
            "estop",
            "ESTOP",
            "Install or keep the one preallocated latch.",
            "pomegranate",
        ),
        ("hold", "HOLD", "Reserve HOLD and cut Active in one owner step.", "lapis"),
        (
            "active",
            "Active",
            "Check profile, freshness, and source. Issue one token.",
            "turquoise",
        ),
    ):
        layout = card(c, name, modes_x, cursor, modes_w, title, body, accent=color)
        modes.append(layout.box)
        cursor = layout.box.bottom + 24
    column_bottom = modes[-1].bottom
    grant = card(
        c,
        "grant",
        grant_x,
        column_top,
        grant_w,
        "Grant check",
        "The position selects one live grant with an exclusive deadline.",
        number="6",
        h=column_bottom - column_top,
    ).box
    effect = card(
        c,
        "effect",
        MARGIN,
        column_top,
        360,
        "Effect boundary",
        "Installed restrictive actions and the Active executor slot. Device work "
        "starts after this handoff.",
        number="7",
        accent="turquoise",
        tint=True,
        h=column_bottom - column_top,
    ).box
    c.connector(
        "position-grant",
        [(last.cx, last.bottom), (last.cx, grant.y)],
        "position",
        "grant",
    )
    for box, name in zip(modes, ("estop", "hold", "active")):
        c.connector(
            f"grant-{name}", [(grant.x, box.cy), (box.right, box.cy)], "grant", name
        )
        c.connector(
            f"{name}-effect",
            [(box.x, box.cy), (effect.right, box.cy)],
            name,
            "effect",
            "pomegranate" if name == "estop" else "turquoise",
        )
    c.height = (
        note(
            c,
            "rejections",
            column_bottom + 34,
            "REJECTIONS",
            [
                "An absent, Init, or unknown mode is a non-authorizing rejection. "
                "Different bytes at an occupied position are a conflict.",
                "A security cut or expiry creates no remote restrictive effect.",
            ],
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


ROLE_SUBJECTS = (
    "Engram simulation responder",
    "Engram plant commander",
    "Engram Haldir-intent extension publisher",
    "Haldir NCP commander",
    "Haldir Engram-intent extension receiver",
    "Haldir Galadriel-assessment receiver",
    "Galadriel NCP observer",
    "Galadriel raw-advisory publisher",
    "Crebain body",
    "Crebain Galadriel-producer surface",
    "Prisoma NCP observer",
)


def ecosystem() -> Canvas:
    c = Canvas(
        "ecosystem",
        WIDTH,
        1400,
        "NCP ecosystem dependency direction",
        "Consumers depend on NCP through thin role adapters. NCP imports no consumer "
        "code. Eleven role subjects need separate installed qualification, and all are "
        "NOT RUN. Integrated Haldir uses four processes. MUSIC owns shared-clock "
        f"coupling. Proposed design for the UNRELEASED 1.0 candidate. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "ECOSYSTEM",
        "Consumers depend on NCP, and NCP depends on no consumer",
        "PROPOSED DESIGN",
    )
    side_w = 520
    center_x = MARGIN + side_w + 90
    center_w = WIDTH - 2 * MARGIN - 2 * side_w - 180
    right_x = WIDTH - MARGIN - side_w

    def roles(first: int, count: int) -> list[str]:
        return [f"{first + i}  {ROLE_SUBJECTS[first - 1 + i]}" for i in range(count)]

    engram = card(c, "engram", MARGIN, y + 10, side_w, "Engram", body=roles(1, 3)).box
    haldir = card(
        c,
        "haldir",
        MARGIN,
        engram.bottom + 30,
        side_w,
        "Haldir",
        body=roles(4, 3)
        + [
            "Four processes: intent receiver, assessment receiver, policy-state "
            "authority (not an NCP peer), and commander."
        ],
    ).box
    galadriel = card(
        c, "galadriel", right_x, y + 10, side_w, "Galadriel", body=roles(7, 2)
    ).box
    crebain = card(
        c,
        "crebain",
        right_x,
        galadriel.bottom + 30,
        side_w,
        "Crebain",
        body=roles(9, 2),
        accent="turquoise",
    ).box
    prisoma = card(
        c, "prisoma", right_x, crebain.bottom + 30, side_w, "Prisoma", body=roles(11, 1)
    ).box
    column_bottom = max(haldir.bottom, prisoma.bottom)
    ncp = card(
        c,
        "ncp",
        center_x,
        y + 10,
        center_w,
        "NCP",
        subtitle="Neutral provider",
        body=[
            "Contract, bindings, profiles, and packages.",
            "Imports no consumer code.",
        ],
        accent="turquoise",
        tint=True,
        h=column_bottom - y - 10,
    ).box
    for box, name in ((engram, "engram"), (haldir, "haldir")):
        c.connector(f"{name}-ncp", [(box.right, box.cy), (ncp.x, box.cy)], name, "ncp")
    for box, name in (
        (galadriel, "galadriel"),
        (crebain, "crebain"),
        (prisoma, "prisoma"),
    ):
        c.connector(f"{name}-ncp", [(box.x, box.cy), (ncp.right, box.cy)], name, "ncp")
    bottom = card_row(
        c,
        column_bottom + 40,
        [
            dict(
                name="fleet",
                title="Fleet campaign",
                accent="bronze" if False else "lapis",
                body="One composite session for 1, 2, or 3 drones. A sensor frame holds 6N "
                "scalars and a command frame 3N. Open.",
            ),
            dict(
                name="music",
                title="MUSIC",
                accent="muted",
                body="MUSIC alone owns shared-clock coupling. NCP never tunnels it.",
            ),
            dict(
                name="presentation",
                title="Presentation",
                accent="muted",
                body="SVG is presentation only. It carries no protocol meaning or evidence.",
            ),
        ],
    )
    c.height = (
        note(
            c,
            "qualification",
            bottom[0].box.bottom + 34,
            "QUALIFICATION",
            "Each numbered role needs its own installed-artifact and live-transport "
            "receipt. All eleven are NOT RUN. pid-rs is a local library, not an NCP "
            "peer.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def versioning() -> Canvas:
    c = Canvas(
        "versioning",
        WIDTH,
        1200,
        "NCP identity domains and native session gate",
        "Package, wire, stable-core, complete-contract, compact-proto, and release "
        "identities are separate. A native session needs a canonical same-major wire "
        "and the exact stable core. Other identities are evidence only. Candidate of "
        f"the UNRELEASED 1.0 line. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "IDENTITY",
        "Separate identities, and two checks open a native session",
        "CANDIDATE WIRE 1.0",
    )
    left_w = 700
    identities = card(
        c,
        "identities",
        MARGIN,
        y + 10,
        left_w,
        "Identity domains",
        body=[
            f"Package version: {CANDIDATE_VERSION}.",
            f"Wire version: {WIRE_VERSION}. Canonical 1 means 1.0.",
            "Stable-core digest: proposed and not yet allocated.",
            "Complete contract digest: SHA-256 over the normative sources.",
            f"Compact proto hash: {CONTRACT_HASH}, advisory only.",
            "Wire release tag: none for 1.0. The latest wire release is v0.8.0.",
            "The gate reads only the wire version and the stable core.",
        ],
    ).box
    gate_x = MARGIN + left_w + 90
    gate_w = WIDTH - MARGIN - gate_x
    checks = []
    cursor = y + 10
    for number, title, body in (
        (
            "1",
            "Canonical same-major wire",
            "Accept 1 or 1.<minor> in canonical spelling.",
        ),
        (
            "2",
            "Exact stable core",
            "Compare the prepared stable-core identity exactly.",
        ),
    ):
        layout = card(
            c,
            f"check-{number}",
            gate_x,
            cursor,
            gate_w,
            title,
            body,
            number=number,
            accent="turquoise",
        )
        checks.append(layout.box)
        cursor = layout.box.bottom + 20
    outcome_y = max(identities.bottom, checks[-1].bottom) + 90
    outcomes = card_row(
        c,
        outcome_y,
        [
            dict(
                name="open",
                title="Native session may open",
                accent="turquoise",
                tint=True,
                body="Both checks pass.",
            ),
            dict(
                name="reject",
                title="Reject",
                accent="pomegranate",
                body="Either check fails. No native session exists.",
            ),
        ],
        x=gate_x,
        width=gate_w,
        gap=40,
    )
    c.connector(
        "to-open",
        [
            (outcomes[0].box.cx, checks[-1].bottom),
            (outcomes[0].box.cx, outcomes[0].box.y),
        ],
        "check-2",
        "open",
    )
    c.connector(
        "to-reject",
        [
            (outcomes[1].box.cx, checks[-1].bottom),
            (outcomes[1].box.cx, outcomes[1].box.y),
        ],
        "check-2",
        "reject",
        "pomegranate",
    )
    c.text(
        outcomes[0].box.cx - 18,
        checks[-1].bottom + 52,
        "both pass",
        SMALL,
        anchor="end",
    )
    c.text(
        outcomes[1].box.cx - 18,
        checks[-1].bottom + 52,
        "either fails",
        SMALL,
        anchor="end",
    )
    bottom = max(identities.bottom, outcomes[0].box.bottom)
    c.height = (
        note(
            c,
            "migration",
            bottom + 34,
            "WIRE 0.8",
            "Wire 0.8 and wire 1.0 are different protocols. Only a terminating "
            "gateway joins them, and it reports no native match.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def fsm() -> Canvas:
    c = Canvas(
        "fsm",
        WIDTH,
        1300,
        "NCP current plant-admission state model",
        "The current compatibility governor starts in HOLD after valid configuration. "
        "It enters Active only with fresh input and live authority. An admitted ESTOP, a "
        "geofence breach, a link burst, or sustained sensor silence latches ESTOP. Only a "
        "deployment reset leaves ESTOP. Invalid configuration fails closed. Current "
        f"UNRELEASED runtime. {NOT_CERTIFICATION}",
    )
    y = header(
        c,
        "PLANT ADMISSION STATES",
        "The current governor outputs only bounded candidates",
        "CURRENT RUNTIME",
        "turquoise",
    )
    row = card_row(
        c,
        y + 110,
        [
            dict(
                name="config",
                title="CONFIG FAIL-CLOSED",
                accent="pomegranate",
                body="Invalid configuration. A non-ESTOP input returns HOLD.",
            ),
            dict(
                name="hold",
                title="HOLD",
                accent="lapis",
                body="Non-latching. The body applies its installed HOLD action.",
            ),
            dict(
                name="active",
                title="ACTIVE",
                accent="turquoise",
                body="Valid command, fresh sensor, and live authority.",
            ),
        ],
        gap=120,
    )
    config, hold, active = (layout.box for layout in row)
    estop_text = (
        "Only a deployment reset leaves ESTOP. The body applies its installed ESTOP "
        "action."
    )
    reset_text = (
        "Retire the generation, authority, lease, and streams. A new session "
        "starts in HOLD."
    )
    lower_h = max(
        card(
            c,
            "estop",
            hold.x,
            0,
            active.right - hold.x,
            "ESTOP (latched)",
            estop_text,
            measure_only=True,
        )[0],
        card(
            c,
            "reset",
            MARGIN,
            0,
            config.w,
            "Deployment reset",
            reset_text,
            measure_only=True,
        )[0],
    )
    estop = card(
        c,
        "estop",
        hold.x,
        hold.bottom + 150,
        active.right - hold.x,
        "ESTOP (latched)",
        estop_text,
        accent="pomegranate",
        tint=True,
        h=lower_h,
    ).box
    start = c.node("start", Box(hold.cx - 16, y + 30, 32, 32))
    c.shape("circle", cx=start.cx, cy=start.cy, r=16, fill="ink")
    c.text(start.right + 14, start.cy + 9, "start", SMALL)

    def lettered(name: str, letter: str, x: float, yy: float, color: str) -> str:
        badge(c, name, x, yy, letter, color, overlay=True)
        return name

    a = lettered("badge-a", "A", hold.cx + 1, (start.bottom + hold.y) / 2, "lapis")
    c.connector(
        "start-hold",
        [(hold.cx, start.bottom), (hold.cx, hold.y)],
        "start",
        "hold",
        "lapis",
        through=(a,),
    )
    g = lettered(
        "badge-g", "G", (config.cx + hold.cx) / 2 - 60, start.cy, "pomegranate"
    )
    c.connector(
        "start-config",
        [(start.x, start.cy), (config.cx, start.cy), (config.cx, config.y)],
        "start",
        "config",
        "pomegranate",
        through=(g,),
    )
    upper = hold.cy - 30
    lower = hold.cy + 30
    b = lettered("badge-b", "B", (hold.right + active.x) / 2, upper, "turquoise")
    c.connector(
        "hold-active",
        [(hold.right, upper), (active.x, upper)],
        "hold",
        "active",
        through=(b,),
    )
    cc = lettered("badge-c", "C", (hold.right + active.x) / 2, lower, "lapis")
    c.connector(
        "active-hold",
        [(active.x, lower), (hold.right, lower)],
        "active",
        "hold",
        "lapis",
        through=(cc,),
    )
    d1 = lettered("badge-d1", "D", hold.cx, (hold.bottom + estop.y) / 2, "pomegranate")
    c.connector(
        "hold-estop",
        [(hold.cx, hold.bottom), (hold.cx, estop.y)],
        "hold",
        "estop",
        "pomegranate",
        through=(d1,),
    )
    d2 = lettered(
        "badge-d2", "D", active.cx, (active.bottom + estop.y) / 2, "pomegranate"
    )
    c.connector(
        "active-estop",
        [(active.cx, active.bottom), (active.cx, estop.y)],
        "active",
        "estop",
        "pomegranate",
        through=(d2,),
    )
    reset = card(
        c,
        "reset",
        MARGIN,
        estop.y,
        config.w,
        "Deployment reset",
        reset_text,
        accent="muted",
        dashed=True,
        h=estop.h,
    ).box
    e = lettered("badge-e", "E", (reset.right + estop.x) / 2, estop.cy, "muted")
    c.connector(
        "estop-reset",
        [(estop.x, estop.cy), (reset.right, estop.cy)],
        "estop",
        "reset",
        "muted",
        dashed=True,
        through=(e,),
    )
    legend = card(
        c,
        "legend",
        MARGIN,
        estop.bottom + 40,
        WIDTH - 2 * MARGIN,
        "Transitions",
        body=[
            "A valid configuration opens in HOLD. G invalid configuration fails closed.",
            "B fresh sensor, live authority, and a valid Active command enter ACTIVE.",
            "C stale or invalid input returns to HOLD without a latch.",
            "D an admitted ESTOP, geofence breach, link burst, or sensor silence latches ESTOP.",
            "E only a deployment reset leaves ESTOP. It starts a new generation.",
        ],
    ).box
    c.height = (
        note(
            c,
            "invariant",
            legend.bottom + 34,
            "INVARIANT",
            [
                "An unattributable envelope or a missing safe frame latches local ESTOP and "
                "returns an error, not a wire frame.",
                "NCP defines no universal zero-safe action. The plant profile names each action.",
            ],
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def ncp2_call() -> Canvas:
    """NCP 2 for readers without a background in protocols: one session, three calls."""
    c = Canvas(
        "ncp2-call",
        WIDTH,
        1500,
        "An NCP 2 session: one round trip for each step",
        "A client opens a session, sends two steps and a close, and gets one response for each. "
        "Each request carries the identity of the last response as its receipt, so the session "
        f"forms one hash chain. NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "NCP 2 EXCHANGE", "One request and one response for each step")
    notes_x = 900
    notes_w = WIDTH - MARGIN - notes_x
    client_head = card(c, "client", MARGIN, y + 6, 300, "Client", subtitle="Runs the experiment").box
    owner_head = card(
        c, "owner", 560, y + 6, 300, "Owner", subtitle="Runs one program", accent="turquoise"
    ).box
    explanations = [
        (
            "1",
            "Open the session",
            "The client names the application and its contract by identity. The owner answers "
            "with the largest frame size of the session and a fresh nonce, so no two openings "
            "share a chain.",
        ),
        (
            "2",
            "The receipt rides along",
            "Each later request carries the identity of the last response: the SHA-256 fingerprint "
            "of its bytes. That is the acknowledgement, so a step needs one round trip, not two.",
        ),
        (
            "3",
            "A response is lost",
            "On a link that can lose messages, the client sends the same request again. The owner "
            "sends its kept response again and does not execute the step a second time.",
        ),
        (
            "4",
            "One hash chain",
            "Each response names its request, and each request names the response before it. The "
            "identity of the last response commits to the whole session.",
        ),
    ]
    boxes = []
    cursor = owner_head.bottom + 30
    for number, title, body in explanations:
        layout = card(
            c,
            f"step-{number}",
            notes_x,
            cursor,
            notes_w,
            title,
            body,
            number=number,
            accent="lapis" if number == "2" else "turquoise",
        )
        boxes.append(layout.box)
        cursor = layout.box.bottom + 14
    bottom = cursor + 10
    client_line = lifeline(c, "client-line", client_head.cx, client_head.bottom, bottom)
    owner_line = lifeline(c, "owner-line", owner_head.cx, owner_head.bottom, bottom)
    calls = [
        ("open", "open, seq 0, contract identity", "opened", "ok, session frame size"),
        ("step-a", "step, seq 1, receipt of response 0", "result-a", "ok, result of step 1"),
        ("step-b", "step, seq 2, receipt of response 1", "result-b", "ok, result of step 2"),
        ("close", "close, seq 3, receipt of response 2", "closed", "ok, session closed"),
    ]
    for (request, request_label, response, response_label), box in zip(calls, boxes, strict=True):
        middle = box.y + box.h / 2
        message(c, request, client_line, owner_line, middle - 30, request_label, "client-line", "owner-line", "lapis")
        message(c, response, owner_line, client_line, middle + 50, response_label, "owner-line", "client-line")
    c.height = (
        note(
            c,
            "boundary",
            bottom + 26,
            "AFTER A FAILURE",
            "If the owner fails while it executes a step, the response says so, and the step is possibly "
            "executed. If the connection breaks, the request without a response is possibly executed. "
            "In either case, at most one call of the session is uncertain, and the session ends.",
        ).bottom
        + 40
    )
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


SEGMENT = Style("sans", 27, 700, color="on_accent")
SEGMENT_NOTE = Style("sans", 24, 600, color="on_accent")
CELL = Style("sans", 25, 600, color="ink")
CELL_YES = Style("sans", 25, 700, color="turquoise")
CELL_NO = Style("sans", 25, 600, color="muted")
CELL_HEAD = Style("sans", 24, 700, color="lapis")


def _finish(c: Canvas, bottom: float) -> Canvas:
    c.height = bottom + 40
    c.nodes["canvas"].box = Box(0, 0, c.width, c.height)
    return c


def ncp2_frame() -> Canvas:
    """The four parts of one NCP 2 frame and what a receiver checks."""
    c = Canvas(
        "ncp2-frame",
        WIDTH,
        1400,
        "One NCP 2 frame",
        "A frame has a 12-byte header, the JSON text, binary attachments, and a 32-byte SHA-256 digest of all bytes before it. The digest is the frame's identity; a receiver checks it before parsing. "
        f"NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "NCP 2 FRAME", "Every message is one frame with its own fingerprint")
    parts = [
        ("frame-header", "Header", "12 bytes", 246, "lapis", "byte 0"),
        ("frame-json", "JSON text", "J bytes", 492, "turquoise", "12"),
        ("frame-attachments", "Attachments", "A bytes", 492, "turquoise", "12 + J"),
        ("frame-digest", "Digest", "32 bytes", 248, "bronze", "12 + J + A"),
    ]
    x = MARGIN
    bar_y = y + 62
    segments = []
    for name, title, size, width, color, offset in parts:
        c.text(x + 4, bar_y - 16, offset, SMALL)
        box = c.node(name, Box(x, bar_y, width, 112))
        c.shape("rect", x=x, y=bar_y, w=width, h=112, rx=10, fill=color)
        c.text(x + width / 2, bar_y + 50, title, SEGMENT, anchor="middle", container=name)
        c.text(x + width / 2, bar_y + 88, size, SEGMENT_NOTE, anchor="middle", container=name)
        segments.append(box)
        x += width + 6
    cards = card_row(
        c,
        bar_y + 112 + 90,
        [
            dict(
                name="frame-header-card",
                title="Header",
                number="1",
                body="The magic bytes NCP and 2, then J and A as 32-bit lengths. The receiver "
                "compares the frame size, 44 + J + A, with the session's limit before it reads on.",
            ),
            dict(
                name="frame-json-card",
                title="JSON text",
                number="2",
                accent="turquoise",
                body="A request names its session, its number, the operation, the response "
                "before it, and a body. A response names its request, an outcome, and a code.",
            ),
            dict(
                name="frame-attachments-card",
                title="Attachments",
                number="3",
                accent="turquoise",
                body="Binary arrays, such as the neurons and times of spikes. Each starts at a "
                "multiple of 8 bytes, so a program reads it in place, without converting it.",
            ),
            dict(
                name="frame-digest-card",
                title="Digest",
                number="4",
                accent="bronze",
                body="SHA-256 of all bytes before it: the frame's identity. The next request "
                "acknowledges a response by naming it, and transcripts chain frames with it.",
            ),
        ],
    )
    for segment, layout, (name, *_rest) in zip(segments, cards, parts, strict=True):
        middle = segment.bottom + 45
        c.connector(
            f"{name}-explained",
            [(segment.cx, segment.bottom), (segment.cx, middle), (layout.box.cx, middle), (layout.box.cx, layout.box.y)],
            name,
            f"{name}-card",
            "muted",
        )
    bottom = note(
        c,
        "frame-why",
        cards[0].box.bottom + 34,
        "WHY ONE FINGERPRINT",
        "A changed bit anywhere in the frame gives another digest, so a receiver that compares "
        "digests never parses or runs a damaged request; only on a local link may an application "
        "turn the comparison off. The client chooses the size limit when it opens the session: "
        "from 64\u00a0KiB to 64\u00a0MiB, 1\u00a0MiB by default. Text and binary data travel in one frame, with "
        "no Base64 and no second message.",
    ).bottom
    return _finish(c, bottom)


def ncp2_outcomes() -> Canvas:
    """The four outcomes of a response and what happens when something goes wrong."""
    c = Canvas(
        "ncp2-outcomes",
        WIDTH,
        1800,
        "What an NCP 2 response tells the client",
        "Every response is ok, declined, rejected, or ended. Eight cards show what happens to damaged, lost, "
        "repeated, and late messages, after an owner failure, a restart or a stop of the owner, and when the "
        "connection breaks. At most one call is possibly executed. "
        f"NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "NCP 2 OUTCOMES", "Four outcomes, and one honest unknown")
    outcomes = card_row(
        c,
        y + 10,
        [
            dict(
                name="outcome-ok",
                title="ok",
                subtitle="It ran once",
                accent="turquoise",
                body="The owner ran the request once. The body is its result. The session continues.",
            ),
            dict(
                name="outcome-declined",
                title="declined",
                subtitle="It never runs",
                accent="turquoise",
                body="The owner kept the request and did not run it, for example a body that the "
                "application finds invalid. It never runs. The session continues.",
            ),
            dict(
                name="outcome-rejected",
                title="rejected",
                subtitle="Only for open",
                body="The owner opened no session for this open, for example a wrong contract. "
                "For any other request, the client ends the session.",
            ),
            dict(
                name="outcome-ended",
                title="ended",
                subtitle="The session is over",
                accent="pomegranate",
                body="The session cannot continue. The code says whether the request ran, did not "
                "run, or possibly ran.",
            ),
        ],
    )
    label_y = outcomes[0].box.bottom + 66
    c.text(MARGIN, label_y, "WHEN SOMETHING GOES WRONG", EYEBROW)
    events = [
        ("event-damaged", "A message is damaged", "The receiver computes the fingerprint "
         "again and finds a difference. No damaged request runs."),
        ("event-lost", "A message is lost", "The client sends the same request again. The "
         "owner sends its kept response again: the step ran once."),
        ("event-twice", "A message arrives twice", "The owner recognizes the copy and sends "
         "its kept response again. The step ran once."),
        ("event-late", "An old copy arrives late", "The owner rejects it, because a later "
         "request already ran. Nothing runs again."),
        ("event-failure", "The owner fails in a step", "It answers ended with the code "
         "owner_failure. The step possibly ran."),
        ("event-restart", "The owner restarts", "A later request gets session_expired: it "
         "possibly ran. A new opening has a new nonce, so no old copy runs again."),
        ("event-stop", "The owner stops", "It answers ended with the code shutdown. The "
         "request did not run, and it never will."),
        ("event-broken", "The connection breaks", "The session ends. The request without a "
         "response possibly ran."),
    ]
    first = card_row(
        c,
        label_y + 26,
        [dict(name=n, title=t, body=b, accent="lapis") for n, t, b in events[:4]],
    )
    second = card_row(
        c,
        first[0].box.bottom + 28,
        [
            dict(name=n, title=t, body=b, accent="lapis" if n == "event-stop" else "pomegranate")
            for n, t, b in events[4:]
        ],
    )
    bottom = note(
        c,
        "outcome-boundary",
        second[0].box.bottom + 34,
        "POSSIBLY EXECUTED",
        "In a session, at most one call can be possibly executed, and it is always the last one. "
        "Lean proofs cover these rules for a model of the owner and the client, and an exhaustive "
        "check of the real SDKs with up to two faults, in 2.6 million states, found no false report.",
    ).bottom
    return _finish(c, bottom)


def ncp2_transcript() -> Canvas:
    """Write-ahead transcripts and the hash chain that a verifier checks."""
    c = Canvas(
        "ncp2-transcript",
        WIDTH,
        1500,
        "An NCP 2 transcript and its hash chain",
        "A program records each frame before it sends it. Requests and responses name each other by digest, so a session forms one hash chain that a verifier checks. A transcript does not show who produced the frames. "
        f"NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "NCP 2 TRANSCRIPT", "Every session can be checked afterwards")
    steps = card_row(
        c,
        y + 10,
        [
            dict(
                name="transcript-record",
                number="1",
                title="Record first",
                body="The program writes each frame to its transcript before it sends it, and "
                "each received frame once it has arrived whole.",
            ),
            dict(
                name="transcript-chain",
                number="2",
                title="One chain",
                accent="turquoise",
                body="Each request names the response before it, and each response names its "
                "request, by their digests.",
            ),
            dict(
                name="transcript-check",
                number="3",
                title="Check afterwards",
                accent="bronze",
                body="A verifier recomputes every digest and checks the numbers, the "
                "acknowledgements, and the chain over the records. A changed, removed, or reordered "
                "record breaks it.",
            ),
        ],
    )
    frames = [
        ("chain-open", "request 0", "open"),
        ("chain-r0", "response 0", "ok"),
        ("chain-s1", "request 1", "step"),
        ("chain-r1", "response 1", "ok"),
        ("chain-s2", "request 2", "step"),
        ("chain-r2", "response 2", "ok"),
        ("chain-close", "request 3", "close"),
        ("chain-r3", "response 3", "ok"),
    ]
    width, gap, height = 290, (WIDTH - 2 * MARGIN - 4 * 290) / 3, 104
    first_top = steps[0].box.bottom + 110
    second_top = first_top + height + 84
    c.text(MARGIN, first_top - 30, "THE FRAMES OF ONE SESSION, IN ORDER", EYEBROW)
    boxes = []
    for index, (name, upper, lower) in enumerate(frames):
        x = MARGIN + (index % 4) * (width + gap)
        top = first_top if index < 4 else second_top
        request = upper.startswith("request")
        box = c.node(name, Box(x, top, width, height))
        c.shape("rect", x=x, y=top, w=width, h=height, rx=12, fill="tint" if request else "card",
                stroke="lapis" if request else "turquoise", stroke_width=3)
        c.text(x + width / 2, top + 42, upper, SMALL, anchor="middle", container=name)
        c.text(x + width / 2, top + 80, lower, TITLE_NARROW, anchor="middle", container=name)
        boxes.append(box)
    for index, ((a_name, *_), (b_name, *_), a, b) in enumerate(zip(frames, frames[1:], boxes, boxes[1:])):
        if index == 3:
            middle = a.bottom + 42
            points = [(a.cx, a.bottom), (a.cx, middle), (b.cx, middle), (b.cx, b.y)]
        else:
            points = [(a.right, a.cy), (b.x, b.cy)]
        c.connector(f"{a_name}-{b_name}", points, a_name, b_name, "muted", width=3)
    bottom = note(
        c,
        "transcript-boundary",
        boxes[-1].bottom + 50,
        "WHAT A TRANSCRIPT SHOWS",
        "Which frames one program sent and received, in which order. Because a frame is recorded "
        "before it is sent, the transcript holds every request that the peer may have run. It "
        "does not show who produced the frames: transcripts are not signed. With a key, the chain "
        "shows that a holder of the key wrote them. CREBAIN's loop check and Prisoma's capture "
        "read transcripts.",
    ).bottom
    return _finish(c, bottom)


def ncp2_bindings() -> Canvas:
    """The links that carry NCP 2 frames, and the stream and rounds patterns."""
    c = Canvas(
        "ncp2-bindings",
        WIDTH,
        1700,
        "NCP 2 links, streams, and rounds",
        "The same NCP 2 frames travel over a pipe pair, a Unix domain socket, TCP, and Zenoh for networks that can lose messages. Streams carry live data, and rounds let many agents share one owner. "
        f"NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "NCP 2 LINKS", "The same frames and rules over every kind of link")
    links = card_row(
        c,
        y + 10,
        [
            dict(name="link-pipe", title="Pipe pair", subtitle="Child process",
                 body="The owner runs as a child process and speaks on its standard input and "
                 "output. The simplest local link."),
            dict(name="link-unix", title="Unix socket", subtitle="One computer",
                 body="One session for each connection, each in its own thread. File permissions "
                 "decide who may connect."),
            dict(name="link-tcp", title="TCP", subtitle="Trusted network",
                 body="Between computers on a network that you trust, or with TLS on both sides. A "
                 "time limit for each call is an option."),
            dict(name="link-zenoh", title="Zenoh", subtitle="Lossy or open network", accent="turquoise",
                 body="Requests travel as queries. A lost message is sent again, and the owner "
                 "answers with its kept response. Configure mutual TLS and access control on "
                 "both sides."),
        ],
    )
    patterns = card_row(
        c,
        links[0].box.bottom + 40,
        [
            dict(name="pattern-streams", title="Streams", subtitle="Live data", accent="turquoise",
                 body="A publisher numbers its messages, and each names the one before. "
                 "Subscribers see lost, repeated, and changed messages. Nothing is sent again."),
            dict(name="pattern-rounds", title="Rounds", subtitle="Many agents, one world", accent="bronze",
                 body="Many agents share one owner. Each round applies their requests in a fixed "
                 "order, and every agent receives the same record of the round."),
        ],
    )
    bottom = note(
        c,
        "links-dependencies",
        patterns[0].box.bottom + 34,
        "SMALL BY DESIGN",
        "The Python SDK uses only the standard library, and the Rust SDK needs four crates. The "
        "Zenoh binding is a separate, optional package for both languages; the rounds profile "
        "is in the Python SDK.",
    ).bottom
    return _finish(c, bottom)


def ncp2_loop() -> Canvas:
    """Spiking controllers in NEST fly CREBAIN drones over NCP 2, with the result of 12 November 2026."""
    c = Canvas(
        "ncp2-loop",
        WIDTH,
        1500,
        "Spiking controllers in NEST fly simulated drones over NCP 2",
        "A loop host runs spiking controllers in NEST and CREBAIN worlds, each with its own NCP 2 session. Three controllers flew five drones in two worlds to within 2.6 cm of their targets, and the check confirmed all 2,400 controller responses. "
        f"NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "NCP 2 CLOSED LOOP", "Spiking controllers in NEST fly simulated drones, step by step")
    gap = 230
    row = card_row(
        c,
        y + 10,
        [
            dict(name="loop-controllers", title="Controllers", subtitle="Spiking neurons in NEST", accent="turquoise",
                 body="N programs, one session each. Each receives the latest estimate of its drones "
                 "and proposes their accelerations."),
            dict(name="loop-host", title="Loop host", subtitle="crebain-ncp-loop",
                 body="First all controllers, at the same time, then all worlds. One transcript for "
                 "each session."),
            dict(name="loop-worlds", title="Worlds", subtitle="CREBAIN simulator", accent="bronze",
                 body="K programs with 1 to 3 drones each. A world refuses actions computed from "
                 "another state."),
        ],
        gap=gap,
    )
    controllers, host, worlds = (layout.box for layout in row)
    upper, lower = host.y + host.h * 0.30, host.y + host.h * 0.72
    c.connector("loop-host-controllers", [(host.x, upper), (controllers.right, upper)], "loop-host", "loop-controllers", "lapis")
    c.connector("loop-controllers-host", [(controllers.right, lower), (host.x, lower)], "loop-controllers", "loop-host", "turquoise")
    c.connector("loop-host-worlds", [(host.right, lower), (worlds.x, lower)], "loop-host", "loop-worlds", "turquoise")
    c.connector("loop-worlds-host", [(worlds.x, upper), (host.right, upper)], "loop-worlds", "loop-host", "lapis")
    for x, top_label, bottom_label in (
        (controllers.right + 16, ["estimate,", "state digest"], ["accelerations,", "response"]),
        (host.right + 16, ["estimate,", "state digest"], ["accelerations,", "identities"]),
    ):
        for index, line in enumerate(top_label):
            c.text(x, upper - 54 + index * 28, line, SMALL)
        for index, line in enumerate(bottom_label):
            c.text(x, lower + 42 + index * 28, line, SMALL)
    results = card_row(
        c,
        host.bottom + 60,
        [
            dict(name="loop-result-drones", number="1", title="Drones reach their targets", accent="turquoise",
                 body="One controller flew one drone, and three controllers flew five drones in two "
                 "worlds. Each drone started 7.3 to 15.6\u00a0m from its target and ended within 2.6\u00a0cm, "
                 "after 600 steps of 20\u00a0ms."),
            dict(name="loop-result-check", number="2", title="Every action checked", accent="lapis",
                 body="The offline check confirmed all 2,400 controller responses: each applied "
                 "once, from the state it answered, to the drones it named."),
            dict(name="loop-result-repeat", number="3", title="The same again", accent="bronze",
                 body="A second run gave the same results, final states included. NEST ran on "
                 "one thread with a fixed seed."),
        ],
    )
    bottom = note(
        c,
        "loop-limits",
        results[0].box.bottom + 34,
        "LIMITS",
        "Simulated drones and a minimal spiking controller of integrate-and-fire populations, run "
        "with NEST 3.10 on one laptop on 12\u00a0November\u00a02026. No physical drone, safety, or "
        "real-time claim; an Engram network can implement the same controller contract.",
    ).bottom
    return _finish(c, bottom)


def ncp2_why() -> Canvas:
    """The guarantees that a closed loop needs, built into NCP 2, and the call time."""
    c = Canvas(
        "ncp2-why",
        WIDTH,
        1500,
        "Why NCP 2 exists: built-in guarantees and fast calls",
        "A table compares NCP 2 with gRPC, ZeroMQ, Zenoh, and HTTP/1.1. NCP 2 builds in four guarantees that the others do not, and has the fastest small call in Rust and Python. "
        f"NCP 2 is UNRELEASED. {NOT_CERTIFICATION}",
    )
    y = header(c, "WHY NCP 2", "Guarantees built in, and the fastest small call")
    intro_bottom = lines_at(
        c,
        MARGIN,
        y + 20,
        "A closed loop needs each step to run once, a clear answer after a failure, checked "
        "messages, and a record that can be checked. Other tools can add these on top; NCP 2 has "
        "them built in.",
        BODY,
        WIDTH - 2 * MARGIN,
    )
    columns = [
        ("System", 196),
        ("A request sent again runs once", 250),
        ("Says after a failure whether it ran", 250),
        ("Detects a damaged message without TLS", 250),
        ("Session record a verifier checks", 250),
        ("Small call, Rust\u00a0·\u00a0Python", 300),
    ]
    rows = [
        ("NCP 2", True, "9.0 µs · 38.8 µs"),
        ("gRPC", False, "35.9 µs · 114.5 µs"),
        ("ZeroMQ", False, "not measured · 54.6 µs"),
        ("Zenoh", False, "59.5 µs · 65.2 µs"),
        ("HTTP/1.1", False, "not measured · 80.3 µs"),
    ]
    top = intro_bottom + 24
    head_h, row_h = 116, 64
    x = MARGIN
    for index, (title, width) in enumerate(columns):
        name = f"why-head-{index}"
        c.node(name, Box(x, top, width, head_h))
        c.shape("rect", x=x, y=top, w=width, h=head_h, rx=8, fill="note")
        lines = wrap(title, CELL_HEAD, width - 28)
        base = top + head_h / 2 - (len(lines) - 1) * 14 + 8
        for line_index, line in enumerate(lines):
            c.text(x + 14, base + line_index * 28, line, CELL_HEAD, container=name)
        x += width
    for row_index, (system, built_in, time) in enumerate(rows):
        row_y = top + head_h + 8 + row_index * (row_h + 6)
        x = MARGIN
        for index, (_, width) in enumerate(columns):
            name = f"why-{row_index}-{index}"
            c.node(name, Box(x, row_y, width, row_h))
            fill = "tint" if built_in else "card"
            c.shape("rect", x=x, y=row_y, w=width, h=row_h, rx=6, fill=fill)
            if index == 0:
                value, style = system, CELL if not built_in else Style("sans", 25, 700, color="lapis")
            elif index == len(columns) - 1:
                value, style = time, CELL
            else:
                value, style = ("Built in", CELL_YES) if built_in else ("Not built in", CELL_NO)
            c.text(x + 14, row_y + 41, value, style, container=name)
            x += width
    table_bottom = top + head_h + 8 + len(rows) * (row_h + 6)
    bottom = note(
        c,
        "why-notes",
        table_bottom + 28,
        "HOW TO READ IT",
        [
            "Medians of the comparison benchmark on one laptop, with no spikes: NCP 2 over a pipe, "
            "gRPC over a Unix socket, ZeroMQ over ipc, Zenoh and HTTP/1.1 over TCP. With the same "
            "SHA-256 check added to every system, NCP 2 was the fastest at every size up to 1\u00a0MiB.",
            "The others have what NCP 2 lacks: gRPC has typed interfaces with code generation, "
            "streaming calls, and deadlines; gRPC, ZeroMQ, and Zenoh authenticate peers without a "
            "shared key. The comparison document lists each difference with its source.",
            "MUSIC, with which NEST exchanges spikes with other simulators, needs all of them in "
            "one MPI job; in this NEST build it delivered exact spikes only with one NEST thread.",
        ],
    ).bottom
    return _finish(c, bottom)


DIAGRAMS = {
    "system-map": system_map,
    "exchange": exchange,
    "payload-transfer": payload_transfer,
    "evidence-ladder": evidence_ladder,
    "closed-loop": closed_loop,
    "queue-admission": queue_admission,
    "overview": overview,
    "topology": topology,
    "runtime": runtime,
    "lifecycle": lifecycle,
    "sequence": sequence,
    "admission": admission,
    "ecosystem": ecosystem,
    "versioning": versioning,
    "fsm": fsm,
    "ncp2-call": ncp2_call,
    "ncp2-frame": ncp2_frame,
    "ncp2-outcomes": ncp2_outcomes,
    "ncp2-transcript": ncp2_transcript,
    "ncp2-bindings": ncp2_bindings,
    "ncp2-loop": ncp2_loop,
    "ncp2-why": ncp2_why,
}


# ─────────────────────────────── validation ────────────────────────────────

DIAGRAM_OWNERS: dict[str, Path] = {
    "system-map": ROOT / "README.md",
    "exchange": ROOT / "local" / "modular" / "owner.md",
    "payload-transfer": ROOT / "local" / "modular" / "STATUS.md",
    "evidence-ladder": ROOT / "README.md",
    "closed-loop": ROOT / "docs" / "implementation" / "CLOSED_LOOP_MATH.md",
    "queue-admission": ROOT / "RESILIENCE.md",
    "overview": ROOT / "README.md",
    "topology": ROOT
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
    "sequence": ROOT
    / "docs"
    / "implementation"
    / "NCP_1_0_LOW_OVERHEAD_ARCHITECTURE.md",
    "admission": ROOT
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
    "ncp2-call": ROOT / "docs" / "NCP-2-GUIDE.md",
    "ncp2-frame": ROOT / "docs" / "NCP-2-GUIDE.md",
    "ncp2-outcomes": ROOT / "docs" / "NCP-2-GUIDE.md",
    "ncp2-transcript": ROOT / "docs" / "NCP-2-GUIDE.md",
    "ncp2-bindings": ROOT / "docs" / "NCP-2-GUIDE.md",
    "ncp2-loop": ROOT / "README.md",
    "ncp2-why": ROOT / "docs" / "NCP-2-GUIDE.md",
}

# Exact labels that must survive editorial changes, and retired labels that
# must not return. Contract-derived text keeps each figure on its source.
REQUIRED_TEXT: dict[str, tuple[str, ...]] = {
    "topology": (
        RPC_ROUTE,
        SENSOR_ROUTE,
        COMMAND_ROUTE,
        OBSERVATION_ROUTE,
        "Init rejects",
        "NOT RUN",
    ),
    "overview": ("production-secure", "fails closed"),
    "ecosystem": (
        "Four processes",
        "not an NCP peer",
        "6N",
        "3N",
        "MUSIC alone owns shared-clock coupling",
        "SVG is presentation only",
        "All eleven are NOT RUN",
    ),
    "versioning": (CANDIDATE_VERSION, CONTRACT_HASH, "advisory only", "v0.8.0"),
    "fsm": ("NCP defines no universal zero-safe action",),
    "sequence": ("is_simulation_output = true", "calibrated_posterior = false"),
    "lifecycle": ("No thread, socket, or store exists per session",),
    "evidence-ladder": ("NOT RUN",),
    "exchange": ("retained",),
    "payload-transfer": ("32,768", "8,388,608"),
    "ncp2-call": ("receipt of response 0", "possibly executed"),
    "ncp2-frame": ("12 + J + A", "SHA-256"),
    "ncp2-outcomes": ("possibly", "owner_failure"),
    "ncp2-transcript": ("before it sends it", "not signed"),
    "ncp2-bindings": ("kept response", "standard library"),
    "ncp2-loop": ("2,400", "same results"),
    "ncp2-why": ("Built in", "Not built in", "MUSIC"),
}
FORBIDDEN_TEXT: dict[str, tuple[str, ...]] = {
    "ecosystem": ("nine role receipts", "Host API 2"),
    "topology": ("{realm}/session/{id}", "[/{name}]"),
}
# Opaque task codes need a definition that a figure cannot give.
GLOBAL_FORBIDDEN = ("B01", "B02", "B03", "X02", "E1", "M1")
EXACTLY_ONCE: dict[str, tuple[str, ...]] = {"ecosystem": ROLE_SUBJECTS}


def _local_name(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# Every public SVG outside docs/diagrams keeps the same direct-view contract.
OTHER_PUBLIC_SVGS = (
    ROOT / "assets" / "logo-light.svg",
    ROOT / "assets" / "logo-dark.svg",
    ROOT / "docs" / "plots" / "overlap_light.svg",
    ROOT / "docs" / "plots" / "overlap_dark.svg",
    ROOT / "docs" / "plots" / "realtime_light.svg",
    ROOT / "docs" / "plots" / "realtime_dark.svg",
)


def accessibility_problems(
    label: str, source: str, allow_doctype: bool = False
) -> list[str]:
    """Apply the direct-view accessibility and resource contract to one SVG."""
    problems = []
    lowered = source.casefold()
    forbidden_items = [
        ("<!entity", "entity declarations are not allowed"),
        ("<?xml-stylesheet", "external XML stylesheets are not allowed"),
        ("@import", "external CSS resource is not allowed"),
    ]
    if not allow_doctype:
        forbidden_items.append(
            ("<!doctype", "document type declarations are not allowed")
        )
    for forbidden, reason in forbidden_items:
        if forbidden in lowered:
            problems.append(f"{label}: {reason}")
    try:
        root = ET.fromstring(source)
    except ET.ParseError as error:
        return problems + [f"invalid XML in {label}: {error}"]
    if _local_name(root.tag) != "svg":
        return problems + [f"{label}: document root is not svg"]
    for attribute in ("width", "height", "viewBox"):
        if not root.get(attribute):
            problems.append(f"{label}: root is missing {attribute}")
    if root.get("role") != "img":
        problems.append(f'{label}: root must have role="img"')
    if root.get("aria-label") is not None:
        problems.append(f"{label}: remove aria-label; aria-labelledby is authoritative")
    titles = [node for node in root if _local_name(node.tag) == "title"]
    descriptions = [node for node in root if _local_name(node.tag) == "desc"]
    if len(titles) != 1 or len(descriptions) != 1:
        return problems + [f"{label}: root needs exactly one direct title and desc"]
    identifiers: dict[str, int] = {}
    fragments = set()
    for node in root.iter():
        if _local_name(node.tag) in {"script", "foreignObject", "image", "a"}:
            problems.append(f"{label}: {_local_name(node.tag)} is not allowed")
        for attribute, value in node.attrib.items():
            local = _local_name(attribute)
            if local.casefold().startswith("on"):
                problems.append(f"{label}: event-handler attributes are not allowed")
            if local == "base":
                problems.append(f"{label}: XML base attributes are not allowed")
            if local == "href":
                if not value.startswith("#") or len(value) == 1:
                    problems.append(f"{label}: external or empty resource reference")
                else:
                    fragments.add(value[1:])
        identifier = node.get("id")
        if identifier:
            identifiers[identifier] = identifiers.get(identifier, 0) + 1
    title_id, desc_id = titles[0].get("id"), descriptions[0].get("id")
    if (
        not title_id
        or not desc_id
        or identifiers.get(title_id) != 1
        or identifiers.get(desc_id) != 1
        or root.get("aria-labelledby", "").split() != [title_id, desc_id]
    ):
        problems.append(f"{label}: aria-labelledby must name direct title then desc")
    title = " ".join("".join(titles[0].itertext()).split())
    description = " ".join("".join(descriptions[0].itertext()).split())
    if not title or len(title.split()) > 10:
        problems.append(f"{label}: title must be nonempty and at most 10 words")
    if not description or len(description.split()) > 55:
        problems.append(f"{label}: desc must be nonempty and at most 55 words")
    if "UNRELEASED" not in description or "certification" not in description.casefold():
        problems.append(
            f"{label}: desc must state UNRELEASED and non-certification status"
        )
    starts = re.findall(r"url\s*\(", source, flags=re.IGNORECASE)
    urls = list(re.finditer(r"url\s*\(\s*([^)]*?)\s*\)", source, flags=re.IGNORECASE))
    if len(urls) != len(starts):
        problems.append(f"{label}: malformed CSS resource reference")
    for match in urls:
        target = match.group(1).strip().strip("\"'")
        if not target.startswith("#") or len(target) == 1:
            problems.append(f"{label}: external or empty CSS resource")
        else:
            fragments.add(target[1:])
    for fragment in sorted(fragments):
        if identifiers.get(fragment) != 1:
            problems.append(f"{label}: resource fragment #{fragment} must resolve once")
    moves = "<animate" in source or "animation:" in source
    if moves and "prefers-reduced-motion: reduce" not in source:
        problems.append(f"{label}: motion has no reduced-motion rule")
    return problems


def contrast_problems(canvas: Canvas) -> list[str]:
    problems = []
    for theme in THEMES:
        for item in canvas.texts:
            container = canvas.nodes.get(item.container or "canvas")
            background = canvas_background(
                canvas, container.name if container else "canvas", theme
            )
            for _, style in item.runs:
                ratio = contrast_ratio(theme[style.color], background)
                if ratio < 4.5:
                    problems.append(
                        f"{canvas.name} {theme['name']}: text {item.content!r} contrast "
                        f"{ratio:.2f}:1 is below 4.5:1"
                    )
    return problems


def canvas_background(canvas: Canvas, name: str, theme: dict) -> str:
    """Return the fill behind a container, from the rendered shape list."""
    if name == "canvas":
        return theme["sheet"]
    box = canvas.nodes[name].box
    fill = None
    for kind, values in canvas.shapes + canvas.overlays:
        if kind == "circle" and values.get("fill") not in (None, "hatch"):
            if (
                abs(values["cx"] - box.cx) < 0.01
                and abs(values["cy"] - box.cy) < 0.01
                and abs(2 * values["r"] - box.w) < 0.01
            ):
                fill = values["fill"]
            continue
        if kind != "rect" or values.get("fill") in (None, "hatch"):
            continue
        if (
            abs(values["x"] - box.x) < 0.01
            and abs(values["y"] - box.y) < 0.01
            and abs(values["w"] - box.w) < 0.01
            and abs(values["h"] - box.h) < 0.01
        ):
            fill = values["fill"]
    if fill is None:
        parent = canvas.nodes[name].parent or "canvas"
        return canvas_background(canvas, parent, theme)
    return theme[fill]


def text_rule_problems(canvas: Canvas) -> list[str]:
    problems = []
    # Join wrapped lines of one container so a wrapped phrase still matches.
    groups: dict[str, list[str]] = {}
    for item in canvas.texts:
        groups.setdefault(item.container or "canvas", []).append(item.content)
    content = [" ".join(lines) for lines in groups.values()]
    joined = "\n".join(content + [canvas.title, canvas.desc])
    for text in REQUIRED_TEXT.get(canvas.name, ()):
        if text not in joined:
            problems.append(f"{canvas.name}: required text {text!r} is absent")
    for text in FORBIDDEN_TEXT.get(canvas.name, ()) + GLOBAL_FORBIDDEN:
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])", joined):
            problems.append(
                f"{canvas.name}: retired or opaque text {text!r} is present"
            )
    drawn = "\n".join(content)
    for text in EXACTLY_ONCE.get(canvas.name, ()):
        count = len(re.findall(rf"(?<![A-Za-z-]){re.escape(text)}(?![A-Za-z-])", drawn))
        if count != 1:
            problems.append(
                f"{canvas.name}: {text!r} must appear exactly once; found {count}"
            )
    return problems


def owner_problems() -> list[str]:
    if set(DIAGRAM_OWNERS) != set(DIAGRAMS):
        return ["diagram owner inventory must equal the generated diagram inventory"]
    problems = []
    for name, owner in DIAGRAM_OWNERS.items():
        label = owner.relative_to(ROOT).as_posix()
        if not owner.is_file():
            problems.append(f"{name} diagram owner is missing: {label}")
            continue
        source = owner.read_text(encoding="utf-8")
        for theme in THEMES:
            filename = f"{name}-{theme['name']}.svg"
            if filename not in source:
                problems.append(f"{label} does not reference {filename}")
    return problems


def other_public_svg_problems() -> list[str]:
    problems = []
    registered = set(OTHER_PUBLIC_SVGS)
    for directory in (ROOT / "assets", ROOT / "docs" / "plots"):
        for path in sorted(directory.glob("*.svg")):
            if path not in registered:
                problems.append(
                    f"unregistered public SVG {path.relative_to(ROOT).as_posix()}"
                )
    for path in OTHER_PUBLIC_SVGS:
        label = path.relative_to(ROOT).as_posix()
        if not path.is_file() or path.is_symlink():
            problems.append(f"missing or linked public SVG {label}")
            continue
        problems.extend(
            accessibility_problems(
                label,
                path.read_text(encoding="utf-8"),
                allow_doctype=path.parent.name == "plots",
            )
        )
    return problems


def build_all() -> tuple[dict[str, str], list[str]]:
    outputs: dict[str, str] = {}
    problems: list[str] = []
    for name, function in DIAGRAMS.items():
        canvas = function()
        if canvas.name != name:
            problems.append(f"diagram {name} returned canvas {canvas.name}")
        problems.extend(canvas.problems())
        problems.extend(contrast_problems(canvas))
        problems.extend(text_rule_problems(canvas))
        for theme in THEMES:
            filename = f"{name}-{theme['name']}.svg"
            svg = canvas.render(theme)
            problems.extend(accessibility_problems(f"docs/diagrams/{filename}", svg))
            outputs[filename] = svg
    return outputs, problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check", action="store_true", help="compare and validate the committed SVGs"
    )
    mode.add_argument(
        "--write-font-metrics", action="store_true", help="refresh the committed widths"
    )
    mode.add_argument(
        "--check-font-metrics", action="store_true", help="compare the committed widths"
    )
    args = parser.parse_args()

    if args.write_font_metrics or args.check_font_metrics:
        expected = _metrics_bytes(measured_font_metrics())
        if args.write_font_metrics:
            METRICS_PATH.write_bytes(expected)
            print(f"wrote {METRICS_PATH.relative_to(ROOT).as_posix()}")
            return
        if not METRICS_PATH.is_file() or METRICS_PATH.read_bytes() != expected:
            raise SystemExit(
                "committed font metrics differ from the installed font files"
            )
        print("OK: committed diagram font metrics match the installed font files")
        return

    outputs, problems = build_all()
    problems.extend(owner_problems())
    problems.extend(other_public_svg_problems())
    expected_files = set(outputs)
    actual_files = {path.name for path in OUT_DIR.glob("*.svg")}
    if args.check:
        for filename, svg in outputs.items():
            path = OUT_DIR / filename
            if not path.is_file():
                problems.append(f"missing docs/diagrams/{filename}")
            elif path.read_text(encoding="utf-8") != svg:
                problems.append(f"stale docs/diagrams/{filename}")
        for filename in sorted(actual_files - expected_files):
            problems.append(f"unregistered docs/diagrams/{filename}")
    if problems:
        for problem in problems:
            print(problem)
        if args.check:
            print("run: python3 scripts/gen_diagrams.py")
        raise SystemExit(1)
    if args.check:
        print(
            f"OK: {len(outputs)} diagram files are current; text fits, connectors "
            "attach, contrast is at least 4.5:1, and the accessibility contract holds"
        )
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename in sorted(actual_files - expected_files):
        (OUT_DIR / filename).unlink()
        print(f"removed docs/diagrams/{filename}")
    for filename, svg in sorted(outputs.items()):
        (OUT_DIR / filename).write_text(svg, encoding="utf-8", newline="\n")
        print(f"wrote docs/diagrams/{filename} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
