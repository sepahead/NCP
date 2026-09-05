#!/usr/bin/env python3
"""Build local-v1 SVG, Markdown, and optional vector PDF from maintained sources."""

from __future__ import annotations

import argparse
import html
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAVY = "#17324D"
TEAL = "#006D77"
BLUE = "#315D9B"
GRAY = "#526575"
LIGHT = "#F2F6FA"
GOLD = "#9A5A00"


def svg_document(title: str, description: str, width: int, height: int, content: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
<title id="title">{html.escape(title)}</title>
<desc id="desc">{html.escape(description)}</desc>
<defs><marker id="arrow-blue" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{BLUE}"/></marker><marker id="arrow-teal" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{TEAL}"/></marker></defs>
<rect width="{width}" height="{height}" rx="16" fill="white"/>
<g font-family="DejaVu Sans, Arial, sans-serif">{content}</g>
</svg>
'''


def label(x: int, y: int, text: str, size: int = 18, color: str = NAVY, bold: bool = False, anchor: str = "start") -> str:
    weight = "bold" if bold else "normal"
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{html.escape(text)}</text>\n'


def architecture() -> str:
    out = label(40, 42, "Development example: four owners.", 30, bold=True)
    out += f'<rect x="40" y="77" width="930" height="105" rx="12" fill="{NAVY}"/>\n'
    out += label(65, 114, "Engram experiment coordinator", 25, "white", True)
    out += label(65, 149, "Freeze plan  |  order one step  |  retain outcomes  |  close evidence", 20, "white")
    projects = [
        (40, "Engram", "Neural owner", ["Persistent NEST", "Exact readout interval", "Private neural state"], BLUE),
        (280, "CREBAIN", "Body owner", ["Simulation and fusion", "ENU state and actions", "Actual innovation data"], BLUE),
        (520, "Prisoma", "Capture owner", ["Reserve before mutation", "Join complete step pairs", "Verify terminal count"], TEAL),
        (760, "Galadriel", "Monitor owner", ["Actual NIS detector", "Explicit insufficiency", "Record-only output"], TEAL),
    ]
    for x, project, role, lines, color in projects:
        center = x + 105
        out += f'<path d="M {center-9} 184 V 341" fill="none" stroke="{BLUE}" stroke-width="3"/>\n'
        out += f'<polygon points="{center-17},337 {center-1},337 {center-9},351" fill="{BLUE}"/>\n'
        out += f'<path d="M {center+9} 350 V 193" fill="none" stroke="{TEAL}" stroke-width="3"/>\n'
        out += f'<polygon points="{center+1},197 {center+17},197 {center+9},183" fill="{TEAL}"/>\n'
        out += f'<rect x="{x}" y="357" width="210" height="183" rx="11" fill="{LIGHT}" stroke="#C8D5E0"/>\n'
        out += f'<rect x="{x}" y="357" width="210" height="7" rx="3" fill="{color}"/>\n'
        out += label(x + 15, 397, project, 25, bold=True)
        out += label(x + 15, 426, role, 19, color, True)
        for index, line in enumerate(lines):
            out += label(x + 15, 459 + index * 27, line, 16)
    out += f'<rect x="40" y="227" width="930" height="76" rx="10" fill="#E8F3F2" stroke="#7FAFAF"/>\n'
    out += label(505, 257, "Each private channel uses the same NCP contract.", 23, TEAL, True, "middle")
    out += label(505, 286, "Bounded request  +  exact result  +  digest-bound acknowledgement", 18, TEAL, anchor="middle")
    out += f'<rect x="40" y="574" width="930" height="87" rx="10" fill="#FFF7E9" stroke="#D4B57C"/>\n'
    out += label(60, 607, "Outside this profile", 21, GOLD, True)
    out += label(60, 636, "Haldir gating  |  remote endpoints  |  physical actuation  |  real-time guarantees", 19, GOLD)
    return svg_document("NCP development-reference ownership", "This bounded development example has Engram coordinate four native owners through separate private NCP request and result pipes. Neural and body owners mutate their own state. Capture and monitoring cannot command. This example does not define the complete final product scope.", 1000, 680, out)


def step_order() -> str:
    out = label(24, 35, "A closed step retains the complete causal chain.", 28, bold=True)
    cells = [("Source", "x[k]", "immutable snapshot"), ("Neural", "z[k+1]", "actual NEST advance"), ("Proposal", "u[k+1]", "bounded acceleration"), ("Body", "apply", "actual CREBAIN step"), ("Snapshot", "x[k+1]", "next source sample"), ("Closure", "step k+1", "known captured pair")]
    for index, (title, symbol, note) in enumerate(cells):
        x = 20 + index * 162
        out += f'<rect x="{x}" y="68" width="142" height="113" rx="9" fill="{LIGHT}" stroke="#B8CBD8"/>\n'
        out += label(x + 71, 97, title, 22, bold=True, anchor="middle")
        out += label(x + 71, 131, symbol, 23, TEAL, True, "middle")
        out += label(x + 71, 158, note, 12, GRAY, anchor="middle")
        if index < len(cells) - 1:
            out += f'<path d="M {x+144} 122 H {x+154}" stroke="{BLUE}" stroke-width="2"/>\n'
            out += f'<polygon points="{x+151},117 {x+151},127 {x+161},122" fill="{BLUE}"/>\n'
    out += label(500, 219, "One dependent step is outstanding. Capture capacity exists before mutation.", 20, anchor="middle")
    return svg_document("Exact local step order", "Source snapshot, neural advance, proposal, body application, next snapshot, and capture closure are distinct ordered states. A missing or indeterminate pair blocks dependent progress.", 1000, 240, out)


def guide_markdown(source: dict) -> str:
    lines = ["# " + source["title"], "", source["subtitle"] + ".", "", "**Status:** " + source["status"], "", "Generated from [guide.source.json](guide.source.json) by [build.py](build.py).", "The [vector PDF](ncp-local-v1-guide.pdf) contains the same explanations and equations.", ""]
    for page in source["pages"]:
        lines += ["## " + page["title"], "", page["intro"], ""]
        if page.get("figure"):
            lines += [f'![{page["title"]}]({page["figure"]})', ""]
        for equation in page.get("equations", []):
            lines += ["```math", equation["tex"], "```", "", equation["explanation"], ""]
        for section in page.get("sections", []):
            lines += ["### " + section["heading"], "", section["text"], ""]
        if page.get("closing"):
            lines += [page["closing"], ""]
    lines += ["## Review and rebuild", "", "Read the [reference profile](README.md), [decision record](decision.md), and [70-case mapping](acceptance-70.md) before interpreting release status.", "", "The guide explains the supplied closed-loop review's mathematical concerns and the reference native adapter contracts.", "Its examples are illustrative calculations, not corpus, simulator, or deployment qualification receipts.", "", "Install the pinned documentation dependencies from `requirements-docs.txt` into a separate environment.", "Run `python docs/local-v1/build.py --pdf` from the repository root.", "Run `python docs/local-v1/build.py --check` to check the generated SVG and Markdown files.", ""]
    return "\n".join(lines)


def acceptance_markdown(source: dict) -> str:
    cases = source["cases"]
    if [row["id"] for row in cases] != [f"{i:02}" for i in range(1, 71)]:
        raise ValueError("Acceptance mapping must preserve exactly cases 01 through 70")
    if any(row["release_status"] != "open" for row in cases):
        raise ValueError("Draft generator cannot promote acceptance rows without a successor receipt workflow")
    lines = ["# All 70 acceptance cases", "", "Status: draft mapping. Every release row remains open.", "", "Generated from [acceptance-70.source.json](acceptance-70.source.json).", "The source retains each original case, priority, and requirement from the supplied acceptance plan.", "A component test pointer is evidence of an available test surface, not an immutable release receipt.", "An excluded profile needs a tested rejection boundary and is never recorded as a passing implementation.", "", "The [reference profile](README.md#local-requirements) defines each `LV1-*` requirement.", "The [open final product requirements](README.md#open-final-v1-requirements) also require modular compositions and declared multimodal profiles.", "The complete installed campaign must retain exact commands, inputs, outputs, source identities, and failure dispositions.", "", f'Supplied acceptance plan SHA-256: `{source["source"]["sha256"]}`.', "", "## Coverage at a glance", "", "| Cases | Topic | Reference-profile gate |", "| --- | --- | --- |", "| 01-05 | Causality and clocks | Exact native schedule and declared clock scope |", "| 06-10 | Positions and delivery | Exact cursor, explicit unsupported streaming profiles |", "| 11-15 | Stateful retry | Retention, conflict, capacity, and uncertain-state retirement |", "| 16-20 | Meaning and missingness | Fixed units, layouts, numeric domains, and evidence availability |", "| 21-25 | NEST | Persistent native update, readout, and measured resource behavior |", "| 26-30 | CREBAIN | Entity routing, direct oracle, and explicit simulation-only modes |", "| 31-35 | Prisoma | Full pair closure, capacity, and terminal completeness |", "| 36-40 | Resources | Aggregate bounds, process containment, measured cost, cleanup |", "| 41-45 | Identity | Installed roles, generation cuts, no downgrade, exact profile |", "| 46-50 | Usability | Honest timing, independent installation, clean reproduction |", "| 51-70 | Expanded boundary | NCP-only ownership, exact numerics, guards, and recovery |", ""]
    for row in cases:
        lines += [f'## {row["id"]}. {row["case"]}', "", f'Priority: **{row["priority"]}**. Local disposition: `{row["disposition"]}`. Release status: **OPEN**.', "", "**Original requirement:** " + row["original_requirement"], "", "**Local requirement:** " + ", ".join(f'`{item}`' for item in row["local_requirements"]) + ".", "", "**Required control:** " + row["required_control"], "", "**Current evidence:** `" + row["evidence"]["state"] + "`. " + row["evidence"]["note"], ""]
        if row["evidence"].get("source"):
            lines += [f'[Implementation or component-test pointer]({row["evidence"]["source"]}). This link does not identify an immutable qualified release.', ""]
    return "\n".join(lines)


def build_pdf(source: dict, destination: Path) -> None:
    import matplotlib
    matplotlib.use("agg")
    from matplotlib import mathtext
    from reportlab import rl_config
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    from svglib.svglib import svg2rlg
    from svglib.fonts import FontMap

    rl_config.invariant = 1
    matplotlib.rcParams["svg.hashsalt"] = "ncp-local-guide-v1"
    matplotlib.rcParams["mathtext.fontset"] = "dejavusans"
    fonts = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    for name, filename in [("Guide", "DejaVuSans.ttf"), ("GuideBold", "DejaVuSans-Bold.ttf"), ("GuideMono", "DejaVuSansMono.ttf")]:
        pdfmetrics.registerFont(TTFont(name, fonts / filename))
    pdfmetrics.registerFontFamily("Guide", normal="Guide", bold="GuideBold", italic="Guide", boldItalic="GuideBold")
    font_map = FontMap()
    for family in ("DejaVu Sans", "Sans", "Arial", "sans-serif"):
        font_map.register_font(family, str(fonts / "DejaVuSans.ttf"), rlgFontName="Guide")
        font_map.register_font(family, str(fonts / "DejaVuSans-Bold.ttf"), weight="bold", rlgFontName="GuideBold")
    width, height = A4
    content_width = width - 88
    styles = {
        "title": ParagraphStyle("title", fontName="GuideBold", fontSize=24, leading=29, textColor=colors.HexColor(NAVY), spaceAfter=15),
        "intro": ParagraphStyle("intro", fontName="Guide", fontSize=11, leading=16, textColor=colors.HexColor(GRAY), spaceAfter=14),
        "heading": ParagraphStyle("heading", fontName="GuideBold", fontSize=11, leading=15, textColor=colors.HexColor(TEAL), spaceBefore=10, spaceAfter=5, keepWithNext=True),
        "body": ParagraphStyle("body", fontName="Guide", fontSize=10.1, leading=14.5, textColor=colors.HexColor(NAVY), spaceAfter=6, alignment=TA_LEFT),
        "caption": ParagraphStyle("caption", fontName="Guide", fontSize=9.4, leading=13.5, textColor=colors.HexColor(GRAY), spaceAfter=12),
    }

    def paragraph(text: str, style: str):
        return Paragraph(html.escape(text), styles[style])

    def drawing(name: str):
        graphic = svg2rlg(str(ROOT / name), font_map=font_map)
        if graphic is None:
            raise ValueError(f"Cannot decode figure {name}")
        factor = content_width / graphic.width
        graphic.scale(factor, factor)
        graphic.width *= factor
        graphic.height *= factor
        return graphic

    def equation(tex: str):
        buffer = io.BytesIO()
        mathtext.math_to_image("$" + tex + "$", buffer, format="svg", dpi=150, color=NAVY)
        buffer.seek(0)
        graphic = svg2rlg(buffer)
        if graphic is None:
            raise ValueError(f"Cannot render equation {tex}")
        factor = min(content_width / graphic.width, 1.7)
        graphic.scale(factor, factor)
        graphic.width *= factor
        graphic.height *= factor
        graphic.hAlign = "LEFT"
        return graphic

    story = []
    for index, page in enumerate(source["pages"]):
        if index:
            story.append(PageBreak())
        story += [paragraph(page["title"], "title"), paragraph(page["intro"], "intro")]
        if page.get("figure"):
            story += [drawing(page["figure"]), Spacer(1, 10)]
        for item in page.get("equations", []):
            story += [Spacer(1, 7), equation(item["tex"]), Spacer(1, 9), paragraph(item["explanation"], "caption")]
        for section in page.get("sections", []):
            story += [paragraph(section["heading"], "heading"), paragraph(section["text"], "body")]
        if page.get("closing"):
            story += [Spacer(1, 10), paragraph(page["closing"], "body")]

    def furniture(canvas, document):
        canvas.saveState()
        canvas.setFont("GuideBold", 8.3)
        canvas.setFillColor(colors.HexColor(TEAL))
        canvas.drawString(44, height - 28, "NCP  /  DEVELOPMENT REFERENCE")
        canvas.setFont("Guide", 8)
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawRightString(width - 44, height - 28, source["date"])
        canvas.setStrokeColor(colors.HexColor("#D8E2EA"))
        canvas.line(44, 40, width - 44, 40)
        canvas.setFont("Guide", 7.3)
        canvas.setFillColor(colors.HexColor(GOLD))
        canvas.drawString(44, 27, "DEVELOPMENT PROFILE  |  FINAL PRODUCT V1 REQUIREMENTS OPEN")
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawRightString(width - 44, 27, f"{document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(str(destination), pagesize=A4, topMargin=53, bottomMargin=54, leftMargin=44, rightMargin=44, title=source["title"], author="NCP contributors", subject=source["subtitle"], pageCompression=1)
    document.build(story, onFirstPage=furniture, onLaterPages=furniture)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check generated SVG and Markdown without changing files")
    parser.add_argument("--pdf", action="store_true", help="Build the optional mathematical PDF")
    args = parser.parse_args()
    if args.check and args.pdf:
        parser.error("--check and --pdf are separate operations")
    guide = json.loads((ROOT / "guide.source.json").read_text())
    acceptance = json.loads((ROOT / "acceptance-70.source.json").read_text())
    outputs = {"architecture.svg": architecture(), "step-order.svg": step_order(), "math-guide.md": guide_markdown(guide), "acceptance-70.md": acceptance_markdown(acceptance)}
    for name, text in outputs.items():
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_text() != text:
                raise SystemExit(f"Generated document differs: {name}")
        else:
            path.write_text(text)
    if args.pdf:
        build_pdf(guide, ROOT / "ncp-local-v1-guide.pdf")
    print("Checked" if args.check else "Generated", ", ".join(outputs), "and PDF" if args.pdf else "")


if __name__ == "__main__":
    main()
