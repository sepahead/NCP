# System-design publication checks

The [manuscript](ncp-system-design.tex), [style](ncp-report.sty), and generated SVGs own the [system-design PDF](../../output/pdf/ncp-system-design.pdf).
This document describes the broader candidate design.
Its publication checks grant no runtime, scientific, or release authority.

## Commands

Install LaTeX, latexmk, librsvg, Latin Modern fonts, and Poppler.
The complete repository gate prepares its private Python environment automatically.
For the focused cross-toolchain check, prepare the pinned parser from the repository root:

```sh
python3 -m venv /tmp/ncp-publication-venv
/tmp/ncp-publication-venv/bin/python -m pip install \
  --disable-pip-version-check --require-hashes --only-binary=:all: \
  -r scripts/requirements-publication.txt
NCP_PUBLICATION_PYTHON=/tmp/ncp-publication-venv/bin/python \
  scripts/check_ncp_system_design_pdf.sh --cross-toolchain
```

Use a fresh private environment path when that example path already exists.
Remove the environment after the check.
The parser has no runtime package dependencies.
Its exact wheel digest is in [requirements-publication.txt](../../scripts/requirements-publication.txt).

The same-toolchain check remains byte-exact:

```sh
scripts/check_ncp_system_design_pdf.sh --check
```

After an intended publication source change, regenerate the PDF with `--write`.
Inspect every rendered page before publication.
Neither `--check` nor `--write` requires the cross-toolchain Python parser.

## Comparison boundary

Both modes retain warning, embedded-font, equation-audit, A4 geometry, and source-set identity checks.
Cross-toolchain comparison also requires the same nonempty page count.
It permits body text to reflow between pages while preserving global lexical order.
Whitespace runs become one space, so `1 2` still differs from `12`.
This rule covers body text, captions, running heads, and mathematics.

Linux and macOS can select different diagram fonts.
Their text extractors can insert different spaces or geometrically reorder nearby labels.
The cross-toolchain helper separates each complete top-level diagram Form from the body.
It preserves all internal Form content and resources during extraction.
Each diagram's ordered non-whitespace glyphs must match its source SVG text roster.
Every symbol, digit, and hyphen remains significant.
The nine unique figure calls must match the build roster in source order.
Figure page, bounds, and effective placement matrix must match between PDFs.
Unknown, unused, duplicated, missing, or extra top-level XObjects fail the check.
Unexpected Form structure or operators also fail the check.
Alternate-text tags, invisible-text modes, and nested Form XObjects are outside the admitted projection.

Exact SVG bytes remain in the source-set commitment.
Their label spellings and lexical spaces remain source-bound.
The diagram extraction comparison does not prove painted whitespace, font identity, or visual equality.
Internal raster effects remain inside their complete source-bound Form.
The check does not independently validate their pixels.
Rendered inspection remains a separate requirement.

## Limits and controls

The helper accepts project-owned publication files only.
It limits each file to 16 MiB, each document to 128 pages, and the source roster to 32 figures.
Each page or diagram stream permits at most 100,000 parsed operations.
Each Poppler extraction has a 60-second deadline.
The pinned parser can allocate before traversal checks.
These limits do not provide arbitrary-PDF memory or code isolation.
Existing CI and repository process limits remain separate.

Every cross-toolchain invocation runs [paired controls](../../scripts/test_publication_pdf_text.py).
They cover lexical boundaries, valid reflow, diagram glyph changes, ordered coverage, and unexpected structures.
The original Linux failure was diagram extraction order and spacing.
The repair preserves the manuscript, SVGs, committed PDF, and same-toolchain byte comparison.
