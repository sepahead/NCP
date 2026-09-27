#!/usr/bin/env python3
"""Paired controls for the source-bound publication text projection."""

import tempfile
import unittest
from pathlib import Path

from check_publication_pdf_text import canonical_text, compare, source_roster
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
)


def pattern_object(data=b"q 0.12 w 1 1 m 5 1 l S Q", resources=None):
    pattern = DecodedStreamObject()
    pattern.update(
        {
            NameObject("/Type"): NameObject("/Pattern"),
            NameObject("/PatternType"): NumberObject(1),
            NameObject("/PaintType"): NumberObject(2),
            NameObject("/TilingType"): NumberObject(1),
            NameObject("/BBox"): ArrayObject([NumberObject(v) for v in (0, 0, 6, 6)]),
            NameObject("/XStep"): NumberObject(6),
            NameObject("/YStep"): NumberObject(6),
            NameObject("/Resources"): resources
            if resources is not None
            else DictionaryObject({NameObject("/Pattern"): DictionaryObject()}),
        }
    )
    pattern.set_data(data)
    return pattern


def pdf(
    path,
    labels=("alpha 1 + 2", "beta 3 - 4"),
    body="body 1 2",
    mutation=None,
    per_page=1,
):
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    fonts = DictionaryObject({NameObject("/F1"): font})
    groups = [labels[i : i + per_page] for i in range(0, len(labels), per_page)]
    for index, group in enumerate(groups):
        page = writer.add_blank_page(width=300, height=400)
        objects = DictionaryObject()
        commands = []
        for slot, label in enumerate(group):
            form = DecodedStreamObject()
            form.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Form"),
                    NameObject("/FormType"): NumberObject(1),
                    NameObject("/BBox"): ArrayObject(
                        [NumberObject(v) for v in (0, 0, 200, 100)]
                    ),
                    NameObject("/Resources"): DictionaryObject(
                        {NameObject("/Font"): fonts}
                    ),
                }
            )
            form.set_data(f"BT /F1 12 Tf 10 50 Td ({label}) Tj ET".encode())
            if mutation == "alternate_text" and index == 0 and slot == 0:
                form.set_data(
                    b"/Span << /ActualText (alpha 1 + 2) >> BDC "
                    b"BT /F1 12 Tf 10 50 Td (wrong) Tj ET EMC"
                )
            if mutation == "invisible_text" and index == 0 and slot == 0:
                form.set_data(b"BT 3 Tr /F1 12 Tf 10 50 Td (alpha 1 + 2) Tj ET")
            if mutation == "image" and index == 0 and slot == 0:
                form[NameObject("/Subtype")] = NameObject("/Image")
            if mutation == "unexpected" and index == 0 and slot == 0:
                form[NameObject("/Ref")] = DictionaryObject()
            name = NameObject(f"/Diagram{slot}")
            objects[name] = form
            commands.append(f"q 1 0 0 1 10 {100 + 120 * slot} cm {name} Do Q")
        if mutation == "unused" and index == 0:
            objects[NameObject("/Unused")] = objects[NameObject("/Diagram0")]
        resources = DictionaryObject(
            {NameObject("/Font"): fonts, NameObject("/XObject"): objects}
        )
        # A decorative page ground: a pattern fill and a low-opacity band.
        states = DictionaryObject(
            {
                NameObject("/G1"): DictionaryObject(
                    {NameObject("/ca"): FloatObject(0.08)}
                )
            }
        )
        if mutation == "graphics_state_key" and index == 0:
            states[NameObject("/G1")][NameObject("/SMask")] = NameObject("/None")
        resources[NameObject("/ExtGState")] = states
        resources[NameObject("/ColorSpace")] = DictionaryObject(
            {
                NameObject("/P"): ArrayObject(
                    [NameObject("/Pattern"), NameObject("/DeviceRGB")]
                )
            }
        )
        cell = pattern_object()
        if mutation == "pattern_text" and index == 0:
            cell = pattern_object(b"BT /F1 12 Tf 1 1 Td (hidden) Tj ET")
        if mutation == "pattern_font" and index == 0:
            cell = pattern_object(
                resources=DictionaryObject({NameObject("/Font"): fonts})
            )
        resources[NameObject("/Pattern")] = DictionaryObject({NameObject("/T1"): cell})
        page[NameObject("/Resources")] = resources
        ground = (
            "q /P cs 0.8 0.8 0.8 /T1 scn 0 0 300 400 re f Q "
            "q /G1 gs 0 0 1 rg 0 390 300 10 re f Q "
        )
        command = " ".join(commands)
        text = f"BT /F1 12 Tf 20 350 Td ({body}) Tj ET"
        if index == 0:
            if mutation == "missing":
                command = ""
            elif mutation == "duplicate":
                command += " /Diagram0 Do"
            elif mutation == "shift":
                command = command.replace("10 100 cm", "20 100 cm")
            elif mutation == "stack":
                command = "Q " + command
            elif mutation == "faded_text":
                text = f"q /G1 gs {text} Q"
            elif mutation == "pattern_filled_text":
                text = f"q /P cs 0 0 0 /T1 scn {text} Q"
            elif mutation == "clip":
                ground += "0 0 10 10 re W n "
        stream = DecodedStreamObject()
        stream.set_data(f"{ground}{text} {command}".encode())
        page.replace_contents(stream)
    writer.write(path)


class PublicationTextControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ncp-pdf-control-")
        self.root = Path(self.temporary.name)
        self.roster = [("first", "alpha1+2"), ("second", "beta3-4")]
        self.good = self.root / "good.pdf"
        pdf(self.good)

    def tearDown(self):
        self.temporary.cleanup()

    def compare_candidate(self, good=None, **kwargs):
        candidate = self.root / "candidate.pdf"
        pdf(candidate, **kwargs)
        compare(candidate, good or self.good, self.roster, self.root)

    def test_valid_projection(self):
        self.compare_candidate()

    def test_two_figures_on_one_page(self):
        paired = self.root / "paired.pdf"
        pdf(paired, per_page=2)
        self.compare_candidate(good=paired, per_page=2)

    def test_figure_page_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "page count|placement"):
            self.compare_candidate(per_page=2)

    def test_body_reflow_and_padding_preserve_lexical_boundaries(self):
        self.assertEqual(
            canonical_text("alpha beta\fgamma delta\f"),
            canonical_text("alpha\fbeta  gamma\n delta\f"),
        )
        self.compare_candidate(body="body  1    2")

    def test_numeric_boundary_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "body/math lexical"):
            self.compare_candidate(body="body 12")

    def test_body_word_order_rejected(self):
        with self.assertRaisesRegex(ValueError, "body/math lexical"):
            self.compare_candidate(body="1 body 2")

    def test_diagram_extraction_spacing_positive(self):
        self.compare_candidate(labels=("alpha  1+2", "beta3 - 4"))

    def test_altered_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "diagram glyphs"):
            self.compare_candidate(labels=("alpha 1 - 2", "beta 3 - 4"))

    def test_altered_digit_rejected(self):
        with self.assertRaisesRegex(ValueError, "diagram glyphs"):
            self.compare_candidate(labels=("alpha 1 + 9", "beta 3 - 4"))

    def test_reordered_forms_rejected(self):
        with self.assertRaisesRegex(ValueError, "diagram glyphs"):
            self.compare_candidate(labels=("beta 3 - 4", "alpha 1 + 2"))

    def test_extra_form_rejected(self):
        with self.assertRaisesRegex(ValueError, "extra diagram"):
            self.compare_candidate(labels=("alpha 1 + 2", "beta 3 - 4", "extra"))

    def test_missing_form_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing diagram"):
            self.compare_candidate(labels=("alpha 1 + 2",))

    def test_missing_invocation_rejected(self):
        with self.assertRaisesRegex(ValueError, "unused or missing"):
            self.compare_candidate(mutation="missing")

    def test_duplicate_invocation_rejected(self):
        with self.assertRaisesRegex(ValueError, "repeated page"):
            self.compare_candidate(mutation="duplicate")

    def test_unused_resource_rejected(self):
        with self.assertRaisesRegex(ValueError, "unused or missing"):
            self.compare_candidate(mutation="unused")

    def test_image_cannot_be_classified_as_diagram(self):
        with self.assertRaisesRegex(ValueError, "unsupported page"):
            self.compare_candidate(mutation="image")

    def test_unexpected_form_structure_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected diagram"):
            self.compare_candidate(mutation="unexpected")

    def test_alternate_text_cannot_hide_painted_text(self):
        with self.assertRaisesRegex(ValueError, "unclassified diagram operator"):
            self.compare_candidate(mutation="alternate_text")

    def test_invisible_text_is_unsupported(self):
        with self.assertRaisesRegex(ValueError, "unclassified diagram operator"):
            self.compare_candidate(mutation="invisible_text")

    def test_faded_body_text_rejected(self):
        with self.assertRaisesRegex(ValueError, "reduced opacity or a pattern"):
            self.compare_candidate(mutation="faded_text")

    def test_pattern_filled_body_text_rejected(self):
        with self.assertRaisesRegex(ValueError, "reduced opacity or a pattern"):
            self.compare_candidate(mutation="pattern_filled_text")

    def test_page_clipping_rejected(self):
        with self.assertRaisesRegex(ValueError, "unclassified page operator"):
            self.compare_candidate(mutation="clip")

    def test_pattern_text_rejected(self):
        with self.assertRaisesRegex(ValueError, "unclassified pattern operator"):
            self.compare_candidate(mutation="pattern_text")

    def test_pattern_font_resource_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected page pattern resources"):
            self.compare_candidate(mutation="pattern_font")

    def test_unexpected_graphics_state_rejected(self):
        with self.assertRaisesRegex(ValueError, "graphics-state entry"):
            self.compare_candidate(mutation="graphics_state_key")

    def test_placement_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "placement"):
            self.compare_candidate(mutation="shift")

    def test_graphics_stack_underflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "graphics stack"):
            self.compare_candidate(mutation="stack")

    def test_invalid_extracted_pages_rejected(self):
        for value in ("", "alpha\f\f", "alpha�\f"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_text(value)

    def test_source_roster_is_closed_and_ordered(self):
        source = self.root / "source.tex"
        source.write_text(
            r"\NcpFigure{second}{Caption.}" "\n" r"\NcpFigure[htbp]{first}{Caption.}"
        )
        for name, glyphs in self.roster:
            (self.root / f"{name}-light.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg"><text>{glyphs}</text></svg>'
            )
        self.assertEqual(
            source_roster(source, self.root, ["first", "second"]),
            [("second-light", "beta3-4"), ("first-light", "alpha1+2")],
        )
        for expected in (["first"], ["first", "first"], ["first", "second", "extra"]):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                source_roster(source, self.root, expected)
        source.write_text(r"\NcpFigure{../outside}{Caption.}")
        with self.assertRaisesRegex(ValueError, "unclassified"):
            source_roster(source, self.root, ["outside"])


if __name__ == "__main__":
    unittest.main()
