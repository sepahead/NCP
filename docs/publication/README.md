# System-design publication checks

The [manuscript](ncp-system-design.tex), [style](ncp-report.sty), and generated light SVGs own the [system-design PDF](../../output/pdf/ncp-system-design.pdf).
The report describes the modular SDK, the fixed-role profile, and the broader `1.0.0-rc.1` candidate.
Its publication checks grant no runtime, scientific, or release authority.

## Build tools

The build uses LuaLaTeX, latexmk, librsvg, and Poppler.
It needs these TeX Live packages: `texlive-latex-base`, `texlive-latex-recommended`, `texlive-latex-extra`, `texlive-luatex`, `texlive-pictures`, and `texlive-fonts-extra`.
It also needs the Latin Modern OpenType fonts from `fonts-lmodern`.
The [CI publication job](../../.github/workflows/ci.yml) installs the exact Debian package set.

## Commands

Run these commands from the repository root.

Check that the committed PDF is byte-exact:

```sh
scripts/check_ncp_system_design_pdf.sh --check
```

After an intended source change, regenerate the PDF:

```sh
scripts/check_ncp_system_design_pdf.sh --write
```

Inspect every rendered page after `--write`.
Neither `--check` nor `--write` requires the cross-toolchain Python parser.

For the cross-toolchain check, prepare the pinned parser in a private environment:

```sh
python3 -m venv /tmp/ncp-publication-venv
/tmp/ncp-publication-venv/bin/python -m pip install \
  --disable-pip-version-check --require-hashes --only-binary=:all: \
  -r scripts/requirements-publication.txt
NCP_PUBLICATION_PYTHON=/tmp/ncp-publication-venv/bin/python \
  scripts/check_ncp_system_design_pdf.sh --cross-toolchain
```

If that example path already exists, use a fresh private path.
Remove the environment after the check.
The parser has no runtime package dependencies.
Its exact wheel digest is in [requirements-publication.txt](../../scripts/requirements-publication.txt).

## Figures

The generator [`scripts/gen_diagrams.py`](../../scripts/gen_diagrams.py) owns every figure in [`docs/diagrams/`](../diagrams/).
It writes a light and a dark SVG for each figure.
The PDF uses the light SVGs.
Markdown documents show the SVG that matches the reader's color scheme.
Run `python3 scripts/gen_diagrams.py --check` to confirm that the committed SVGs are current.

The generator measures each label with committed font metrics.
[`scripts/diagram_font_metrics.v1.json`](../../scripts/diagram_font_metrics.v1.json) records the advance widths and the SHA-256 digest of each font file.
The check rejects a label that does not fit its box and two labels that overlap.
It rejects a connector that does not end on its boxes, and a connector that crosses another box.
It also rejects text contrast below 4.5:1 and an SVG that breaks the accessibility contract.

The SVG files are vector graphics.
Open a figure file directly to zoom without loss.
The README, the modular guides, the closed-loop note, and the resilience guide link both theme files below each figure.

## Arithmetic check

The Lean 4 file [`lean/NcpDesign.lean`](lean/NcpDesign.lean) checks the discrete arithmetic of the report.
It uses Lean core only.
It rejects `sorry`, `admit`, `axiom`, `native_decide`, and other unchecked constructs.

Install Lean 4.23.0 and put its `bin` directory on `PATH`.
Then run the check:

```sh
scripts/check_ncp_design_lean.sh
```

The CI job downloads the Lean 4.23.0 release archive and checks its SHA-256 digest.
A pass proves the stated arithmetic facts.
It does not prove protocol behavior, security, safety, or controller stability.

## Deterministic identity

Each build uses a fixed `SOURCE_DATE_EPOCH` and suppresses dates and build paths.
A domain-separated SHA-256 commitment covers the manuscript, the style, and the 15 light figure SVGs.
The PDF keywords carry that commitment.
The PDF trailer ID is the first 128 bits of the commitment.
The build rejects LaTeX warnings, overfull and underfull boxes, and undefined references.
It also requires embedded fonts, A4 pages, no JavaScript, and a complete equation audit.

## Comparison boundary

Both modes keep the warning, embedded-font, equation-audit, A4 geometry, and source-set identity checks.
The cross-toolchain comparison also requires the same nonempty page count.
Body text can reflow between pages, but its global lexical order must not change.
Whitespace runs become one space, so `1 2` still differs from `12`.
This rule covers body text, captions, running heads, and mathematics.

Linux and macOS can select different diagram fonts.
Their text extractors can insert different spaces or reorder nearby labels.
The helper therefore separates each complete top-level diagram Form from the body.
It keeps all internal Form content and resources during extraction.
The ordered non-whitespace glyphs of each diagram must match its light source SVG.
Every symbol, digit, and hyphen stays significant.

The fifteen figure calls must match the build roster in source order.
Figure page, bounds, and placement matrix must match between the two PDFs.
A page can hold at most four figure Forms.
Unknown, unused, duplicated, missing, or extra top-level XObjects fail the check.
Unexpected Form structure or operators also fail the check.
Alternate-text tags, invisible-text modes, page clipping, and nested Form XObjects are outside the admitted projection.

The decorative page ground uses path, pattern, and opacity operators.
A page graphics state can carry only opacity values.
A pattern cell can contain path operators only, with no font, image, or text.
Body text painted with reduced opacity or with a pattern color fails the check.

Exact SVG bytes remain in the source-set commitment.
The diagram comparison does not prove painted whitespace, font identity, or visual equality.
Rendered inspection remains a separate requirement.

## Limits and controls

The helper accepts project-owned publication files only.
It limits each file to 16 MiB, each document to 128 pages, and the source roster to 32 figures.
Each page, pattern, or diagram stream permits at most 100,000 parsed operations.
Each Poppler extraction has a 60-second deadline.
The pinned parser can allocate memory before traversal checks.
These limits do not provide arbitrary-PDF memory or code isolation.

Every cross-toolchain invocation runs [paired controls](../../scripts/test_publication_pdf_text.py).
They cover lexical boundaries, valid reflow, diagram glyph changes, ordered coverage, and two figures on one page.
They also cover faded or pattern-filled body text, page clipping, and pattern cells with text or fonts.
