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
    NameObject,
    NumberObject,
)


def pdf(path, labels=("alpha 1 + 2", "beta 3 - 4"), body="body 1 2", mutation=None):
    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    fonts = DictionaryObject({NameObject("/F1"): font})
    for index, label in enumerate(labels):
        page = writer.add_blank_page(width=300, height=400)
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
        if mutation == "alternate_text" and index == 0:
            form.set_data(
                b"/Span << /ActualText (alpha 1 + 2) >> BDC "
                b"BT /F1 12 Tf 10 50 Td (wrong) Tj ET EMC"
            )
        if mutation == "invisible_text" and index == 0:
            form.set_data(b"BT 3 Tr /F1 12 Tf 10 50 Td (alpha 1 + 2) Tj ET")
        if mutation == "image" and index == 0:
            form[NameObject("/Subtype")] = NameObject("/Image")
        if mutation == "unexpected" and index == 0:
            form[NameObject("/Ref")] = DictionaryObject()
        objects = DictionaryObject({NameObject("/Diagram"): form})
        if mutation == "unused" and index == 0:
            objects[NameObject("/Unused")] = form
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): fonts, NameObject("/XObject"): objects}
        )
        command = "q 1 0 0 1 10 100 cm /Diagram Do Q"
        if index == 0:
            if mutation == "missing":
                command = ""
            elif mutation == "duplicate":
                command += " /Diagram Do"
            elif mutation == "shift":
                command = command.replace("10 100 cm", "20 100 cm")
            elif mutation == "stack":
                command = "Q " + command
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 350 Td ({body}) Tj ET {command}".encode())
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

    def compare_candidate(self, **kwargs):
        candidate = self.root / "candidate.pdf"
        pdf(candidate, **kwargs)
        compare(candidate, self.good, self.roster, self.root)

    def test_valid_projection(self):
        self.compare_candidate()

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
        with self.assertRaisesRegex(ValueError, "unclassified page"):
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

    def test_placement_change_rejected(self):
        with self.assertRaisesRegex(ValueError, "placement"):
            self.compare_candidate(mutation="shift")

    def test_graphics_stack_underflow_rejected(self):
        with self.assertRaisesRegex(ValueError, "graphics stack"):
            self.compare_candidate(mutation="stack")

    def test_invalid_extracted_pages_rejected(self):
        for value in ("", "alpha\f\f", "alpha\ufffd\f"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical_text(value)

    def test_source_roster_is_closed_and_ordered(self):
        source = self.root / "source.tex"
        source.write_text(
            r"\NcpFigure{H}{width}{second.pdf}\NcpFigure{H}{width}{first.pdf}"
        )
        for name, glyphs in self.roster:
            (self.root / f"{name}.svg").write_text(
                f'<svg xmlns="http://www.w3.org/2000/svg"><text>{glyphs}</text></svg>'
            )
        self.assertEqual(
            source_roster(source, self.root, ["first", "second"]), self.roster[::-1]
        )
        for expected in (["first"], ["first", "first"], ["first", "second", "extra"]):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                source_roster(source, self.root, expected)
        source.write_text(r"\NcpFigure{H}{width}{../outside.pdf}")
        with self.assertRaisesRegex(ValueError, "unclassified"):
            source_roster(source, self.root, ["outside"])


if __name__ == "__main__":
    unittest.main()
