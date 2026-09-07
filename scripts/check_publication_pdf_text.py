#!/usr/bin/env python3
"""Compare body lexical text and ordered, source-bound diagram Form glyphs.

This is a trusted publication build check, not an arbitrary-PDF sandbox.
See docs/publication/README.md for the extraction and resource limits.
"""

import argparse
import math
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pypdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_PAGES = 128
MAX_OPERATIONS = 100_000
MAX_FIGURES = 32
SVG_NS = "{http://www.w3.org/2000/svg}"
# Closed operator sets for this TeX/librsvg publication profile. In particular,
# alternate-text marked content and invisible-text modes are not admitted.
PAGE_OPERATORS = {
    item.encode("ascii")
    for item in "BT Do ET G J Q RG S TJ Td Tf Tj Tm cm d f g l m q re rg w".split()
}
FORM_OPERATORS = {
    item.encode("ascii")
    for item in (
        "B BT CS Do ET J M Q RG S SCN TJ Td Tf Tj Tm W c cm cs d f "
        "gs h j l m n q re rg scn sh w"
    ).split()
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def bounded_bytes(path: Path) -> bytes:
    require(
        path.is_file() and path.stat().st_size <= MAX_FILE_BYTES,
        f"oversized or absent file: {path}",
    )
    data = path.read_bytes()
    require(len(data) <= MAX_FILE_BYTES, f"file grew beyond limit: {path}")
    return data


def canonical_text(text: str) -> tuple[int, str]:
    require("\ufffd" not in text, "replacement character in extracted text")
    pages = text.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    require(0 < len(pages) <= MAX_PAGES, "invalid extracted page count")
    normalized = [re.sub(r"\s+", " ", page).strip() for page in pages]
    require(all(normalized), "empty extracted body page")
    return len(pages), " ".join(normalized)


def ordered_glyphs(text: str) -> str:
    require("\ufffd" not in text, "replacement character in diagram")
    result = re.sub(r"\s", "", text)
    require(bool(result), "empty diagram text")
    return result


def source_roster(
    source: Path, diagrams: Path, expected: list[str]
) -> list[tuple[str, str]]:
    tex = bounded_bytes(source).decode("utf-8")
    names = re.findall(r"\\NcpFigure\{[^}]+\}\{[^}]+\}\{([a-z-]+)\.pdf\}", tex)
    require(tex.count(r"\NcpFigure{") == len(names), "unclassified figure source call")
    require(
        0 < len(names) <= MAX_FIGURES and len(names) == len(set(names)),
        "invalid figure source roster",
    )
    require(
        sorted(names) == sorted(expected) and len(expected) == len(set(expected)),
        "figure source/build roster differs",
    )
    roster = []
    for name in names:
        svg = ET.fromstring(bounded_bytes(diagrams / f"{name}.svg"))
        require(svg.tag == SVG_NS + "svg", "unexpected source diagram root")
        labels = ["".join(node.itertext()) for node in svg.iter(SVG_NS + "text")]
        require(bool(labels), f"source has no text labels: {name}")
        roster.append((name, ordered_glyphs("".join(labels))))
    return roster


def extract(path: Path, mode: str, output: Path) -> str:
    subprocess.run(["pdftotext", mode, str(path), str(output)], check=True, timeout=60)
    return bounded_bytes(output).decode("utf-8")


def matrix(values: list) -> tuple[float, ...]:
    require(len(values) == 6, "invalid graphics matrix")
    result = tuple(float(value) for value in values)
    require(all(math.isfinite(value) for value in result), "nonfinite graphics matrix")
    return result


def multiply(a: tuple, b: tuple) -> tuple:
    # PDF row-vector affine composition: concatenate a before b.
    return (
        a[0] * b[0] + a[1] * b[2],
        a[0] * b[1] + a[1] * b[3],
        a[2] * b[0] + a[3] * b[2],
        a[2] * b[1] + a[3] * b[3],
        a[4] * b[0] + a[5] * b[2] + b[4],
        a[4] * b[1] + a[5] * b[3] + b[5],
    )


def project(path: Path, roster: list[tuple[str, str]], output: Path) -> tuple:
    bounded_bytes(path)
    reader = PdfReader(path, strict=True)
    require(not reader.is_encrypted, "encrypted PDF is unsupported")
    require(0 < len(reader.pages) <= MAX_PAGES, "invalid PDF page count")
    body = PdfWriter()
    placements = []
    for page_number, page in enumerate(reader.pages, start=1):
        stream = page.get_contents()
        require(
            stream is not None and len(stream.operations) <= MAX_OPERATIONS,
            "absent or oversized page stream",
        )
        objects = page["/Resources"].get("/XObject", DictionaryObject()).get_object()
        require(len(objects) <= 1, "multiple or unclassified page XObjects")
        used = set()
        kept = []
        transform = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        stack = []
        for args, operator in stream.operations:
            require(operator in PAGE_OPERATORS, "unclassified page operator")
            if operator == b"q":
                stack.append(transform)
                require(len(stack) <= 128, "graphics stack exceeds limit")
            elif operator == b"Q":
                require(bool(stack), "unbalanced graphics stack")
                transform = stack.pop()
            elif operator == b"cm":
                transform = multiply(matrix(args), transform)
            if operator != b"Do":
                kept.append((args, operator))
                continue
            require(
                len(args) == 1 and args[0] in objects and args[0] not in used,
                "unknown or repeated page XObject",
            )
            used.add(args[0])
            require(len(placements) < len(roster), "extra diagram Form")
            form = objects[args[0]].get_object()
            require(
                form.get("/Type") == "/XObject"
                and form.get("/Subtype") == "/Form"
                and form.get("/FormType") == 1,
                "unsupported page XObject type",
            )
            require(
                set(form)
                <= {
                    "/Type",
                    "/Subtype",
                    "/FormType",
                    "/BBox",
                    "/Group",
                    "/Resources",
                    "/Filter",
                    "/Length",
                },
                "unexpected diagram Form structure",
            )
            bbox = tuple(float(value) for value in form["/BBox"])
            require(
                len(bbox) == 4
                and all(math.isfinite(value) for value in bbox)
                and bbox[2] > bbox[0]
                and bbox[3] > bbox[1],
                "invalid diagram bounds",
            )
            form_stream = ContentStream(form, reader)
            require(
                len(form_stream.operations) <= MAX_OPERATIONS,
                "diagram stream exceeds limit",
            )
            require(
                all(
                    operator in FORM_OPERATORS for _, operator in form_stream.operations
                ),
                "unclassified diagram operator",
            )
            nested = form["/Resources"].get("/XObject", DictionaryObject()).get_object()
            require(
                all(
                    item.get_object().get("/Subtype") == "/Image"
                    for item in nested.values()
                ),
                "unclassified nested diagram XObject",
            )
            # Preserve the entire Form, including its internal images and resources.
            # Only the top-level source-bound invocation is removed from the body.
            name, expected_glyphs = roster[len(placements)]
            figure_writer = PdfWriter()
            target = figure_writer.add_blank_page(
                width=bbox[2] - bbox[0], height=bbox[3] - bbox[1]
            )
            target[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/XObject"): DictionaryObject(
                        {NameObject("/Figure"): form.clone(figure_writer)}
                    )
                }
            )
            invocation = DecodedStreamObject()
            invocation.set_data(
                f"q 1 0 0 1 {-bbox[0]} {-bbox[1]} cm /Figure Do Q".encode("ascii")
            )
            target.replace_contents(invocation)
            figure_path = output / f"{name}.pdf"
            figure_writer.write(figure_path)
            actual = extract(figure_path, "-raw", output / f"{name}.txt")
            require(
                ordered_glyphs(actual) == expected_glyphs,
                f"ordered source diagram glyphs differ: {name}",
            )
            placements.append((name, page_number, bbox, transform))
        require(not stack, "unbalanced page graphics stack")
        require(used == set(objects), "unused or missing page XObject invocation")
        target = body.add_page(page)
        replacement = ContentStream(None, body)
        replacement.operations = kept
        target.replace_contents(replacement)
    require(len(placements) == len(roster), "missing diagram Form")
    body_path = output / "body.pdf"
    body.write(body_path)
    body_text = canonical_text(extract(body_path, "-layout", output / "body.txt"))
    require(body_text[0] == len(reader.pages), "body extraction page count differs")
    return body_text, placements


def compare(
    built: Path, committed: Path, roster: list[tuple[str, str]], output: Path
) -> None:
    projections = []
    for name, path in (("built", built), ("committed", committed)):
        destination = output / name
        destination.mkdir()
        projections.append(project(path, roster, destination))
    require(
        projections[0][0] == projections[1][0],
        "ordered body/math lexical text or page count differs",
    )
    require(
        projections[0][1] == projections[1][1],
        "ordered diagram placement or bounds differ",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("built", type=Path)
    parser.add_argument("committed", type=Path)
    parser.add_argument("source", type=Path)
    parser.add_argument("diagrams", type=Path)
    parser.add_argument("figures", nargs="+")
    args = parser.parse_args()
    require(
        pypdf.__version__ == "6.7.4",
        "install exact scripts/requirements-publication.txt in a private environment",
    )
    roster = source_roster(args.source, args.diagrams, args.figures)
    with tempfile.TemporaryDirectory(prefix="ncp-pdf-text-") as temporary:
        compare(args.built, args.committed, roster, Path(temporary))
    print(
        f"OK: body/math lexical text and {len(roster)} "
        "ordered source-bound diagram Forms match"
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"NCP publication text check: {error}") from error
