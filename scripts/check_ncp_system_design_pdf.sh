#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE="docs/publication/ncp-system-design.tex"
STYLE="docs/publication/ncp-report.sty"
COMMITTED="output/pdf/ncp-system-design.pdf"
SOURCE_DATE_EPOCH_VALUE="1790467200"
MODE="${1:---check}"

case "$MODE" in
    --write | --check | --cross-toolchain) ;;
    *)
        echo "usage: $0 [--write|--check|--cross-toolchain]" >&2
        exit 2
        ;;
esac

commands=(cmp kpsewhich latexmk lualatex pdfinfo pdffonts pdftotext python3 rsvg-convert)
for command in "${commands[@]}"; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "NCP system-design PDF check: missing command: $command" >&2
        exit 2
    fi
done

for path in "$ROOT/$SOURCE" "$ROOT/$STYLE"; do
    if [[ ! -f "$path" ]]; then
        echo "NCP system-design PDF check: source is missing: ${path#"$ROOT/"}" >&2
        exit 1
    fi
done

TMP_ROOT="${TMPDIR:-/tmp}"
BUILD_DIR="$(mktemp -d "$TMP_ROOT/ncp-system-design-pdf.XXXXXX")"
cleanup() {
    rm -rf -- "$BUILD_DIR"
}
trap cleanup EXIT

# The report includes the light SVG of each figure once, in this set. The
# cross-toolchain check compares this roster with the \NcpFigure calls in source
# order.
figures=(
    admission
    closed-loop
    ecosystem
    evidence-ladder
    exchange
    fsm
    lifecycle
    overview
    payload-transfer
    queue-admission
    runtime
    sequence
    system-map
    topology
    versioning
)

# Figures render with exactly these font files. A private font configuration
# keeps host fonts out, so a missing file cannot become a silent substitute.
figure_fonts=(
    SourceSansPro-Regular.otf
    SourceSansPro-Semibold.otf
    SourceSansPro-Bold.otf
    SourceSansPro-RegularIt.otf
    SourceSansPro-SemiboldIt.otf
    lmroman10-regular.otf
    lmroman10-italic.otf
)
FONT_DIR="$BUILD_DIR/figure-fonts"
mkdir -p "$FONT_DIR/files" "$FONT_DIR/cache"
for font in "${figure_fonts[@]}"; do
    located="$(kpsewhich "$font" || true)"
    if [[ -z "$located" || ! -f "$located" ]]; then
        echo "NCP system-design PDF check: figure font is missing: $font" >&2
        exit 2
    fi
    cp "$located" "$FONT_DIR/files/$font"
done
cat >"$FONT_DIR/fonts.conf" <<EOF
<?xml version="1.0"?>
<fontconfig>
  <reset-dirs/>
  <dir>$FONT_DIR/files</dir>
  <cachedir>$FONT_DIR/cache</cachedir>
</fontconfig>
EOF

figure_files=("${figures[@]/%/-light}")
for figure in "${figure_files[@]}"; do
    input="$ROOT/docs/diagrams/$figure.svg"
    output="$BUILD_DIR/$figure.pdf"
    if [[ ! -f "$input" ]]; then
        echo "NCP system-design PDF check: figure is missing: docs/diagrams/$figure.svg" >&2
        exit 1
    fi
    FONTCONFIG_FILE="$FONT_DIR/fonts.conf" FONTCONFIG_PATH="$FONT_DIR" \
        PANGOCAIRO_BACKEND=fc HOME="$FONT_DIR" \
        rsvg-convert --format=pdf --output "$output" "$input"
    if ! pdffonts "$output" | awk '
        NR > 2 {
            name = $1
            sub(/^[A-Z]{6}\+/, "", name)
            if (name !~ /^(SourceSansPro-(Regular|Semibold|Bold|It|SemiboldIt)|LMRoman10-(Regular|Italic))$/) bad = 1
            if ($(NF - 4) != "yes") bad = 1
        }
        END { exit bad }
    '; then
        pdffonts "$output" >&2
        echo "NCP system-design PDF check: $figure uses an unexpected or unembedded font" >&2
        exit 1
    fi
done

PUBLICATION_SOURCE_DIGEST="$({ python3 - "$ROOT" "$SOURCE" "$STYLE" "${figure_files[@]}" <<'PY'
import sys
from hashlib import sha256
from pathlib import Path

root = Path(sys.argv[1])
relative_paths = [Path(sys.argv[2]), Path(sys.argv[3])]
relative_paths.extend(Path("docs/diagrams") / f"{name}.svg" for name in sys.argv[4:])

hasher = sha256()
hasher.update(b"ncp.publication-source-set.v2\0")
for relative_path in sorted(relative_paths, key=lambda path: path.as_posix()):
    encoded_path = relative_path.as_posix().encode("utf-8")
    content = (root / relative_path).read_bytes()
    hasher.update(len(encoded_path).to_bytes(8, "big"))
    hasher.update(encoded_path)
    hasher.update(len(content).to_bytes(8, "big"))
    hasher.update(content)
print(hasher.hexdigest())
PY
} 2>&1)" || {
    printf '%s\n' "$PUBLICATION_SOURCE_DIGEST" >&2
    exit 1
}

EQUATION_COUNT="$({ python3 - "$ROOT/$SOURCE" <<'PY'
import re
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
equation_labels = re.findall(r"\\label\{(eq:[^}]+)\}", source)
if not equation_labels:
    raise SystemExit("NCP system-design PDF check: no numbered equations found")
if len(equation_labels) != len(set(equation_labels)):
    raise SystemExit("NCP system-design PDF check: duplicate equation label")

try:
    audit_start = source.index(r"\caption{Equation audit.")
    audit_end = source.index(r"\end{longtable}", audit_start)
except ValueError as error:
    raise SystemExit(
        "NCP system-design PDF check: equation-audit table is missing"
    ) from error

positions = {label: index for index, label in enumerate(equation_labels)}
covered: list[str] = []
for line in source[audit_start:audit_end].splitlines():
    references = re.findall(r"\\eqref\{(eq:[^}]+)\}", line)
    if not references:
        continue
    if len(references) == 1:
        if references[0] not in positions:
            raise SystemExit(
                "NCP system-design PDF check: audit references an unknown equation"
            )
        covered.append(references[0])
        continue
    if len(references) != 2:
        raise SystemExit(
            "NCP system-design PDF check: audit row must name one equation or one range"
        )
    first = positions.get(references[0])
    last = positions.get(references[1])
    if first is None or last is None or first > last:
        raise SystemExit(
            "NCP system-design PDF check: audit contains an invalid equation range"
        )
    covered.extend(equation_labels[first : last + 1])

if covered != equation_labels:
    raise SystemExit(
        "NCP system-design PDF check: equation audit is incomplete, duplicated, or out of order"
    )
print(len(equation_labels))
PY
} 2>&1)" || {
    printf '%s\n' "$EQUATION_COUNT" >&2
    exit 1
}

TRAILER_ID="$(printf '%s' "${PUBLICATION_SOURCE_DIGEST:0:32}" | tr 'a-f' 'A-F')"
{
    printf '\\renewcommand{\\NcpPublicationSourceDigest}{%s}\n' "$PUBLICATION_SOURCE_DIGEST"
    printf '\\renewcommand{\\NcpPublicationTrailerId}{%s}\n' "$TRAILER_ID"
} >"$BUILD_DIR/ncp-publication-identity.tex"

cp "$ROOT/$SOURCE" "$BUILD_DIR/ncp-system-design.tex"
cp "$ROOT/$STYLE" "$BUILD_DIR/ncp-report.sty"

(
    cd "$BUILD_DIR"
    SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH_VALUE" FORCE_SOURCE_DATE=1 TZ=UTC LC_ALL=C \
        latexmk \
        -lualatex \
        -interaction=nonstopmode \
        -halt-on-error \
        -outdir="$BUILD_DIR" \
        "$BUILD_DIR/ncp-system-design.tex" \
        >"$BUILD_DIR/latexmk.stdout" 2>&1
) || {
    cat "$BUILD_DIR/latexmk.stdout" >&2
    echo "NCP system-design PDF check: LaTeX build failed" >&2
    exit 1
}

LOG="$BUILD_DIR/ncp-system-design.log"
BUILT="$BUILD_DIR/ncp-system-design.pdf"

rejected='(^| )(LaTeX|LaTeX Font|Package [^ ]+) Warning:|Overfull \\hbox|Underfull \\hbox|Overfull \\vbox|Underfull \\vbox|undefined references|Fatal error|Missing character'
if grep -E "$rejected" "$LOG" >/dev/null; then
    grep -E "$rejected" "$LOG" >&2
    echo "NCP system-design PDF check: LaTeX log contains a rejected diagnostic" >&2
    exit 1
fi

pdftotext -layout "$BUILT" "$BUILD_DIR/built.txt"
sentinels=(
    "NCP System Design"
    "MODULAR SDK IMPLEMENTED"
    "Finite memory and queue isolation"
    "Ten-lens review"
    "NOT RUN"
    "The equations are design accounting, not"
)
for sentinel in "${sentinels[@]}"; do
    if ! grep -F -- "$sentinel" "$BUILD_DIR/built.txt" >/dev/null; then
        echo "NCP system-design PDF check: rendered-text sentinel is absent: $sentinel" >&2
        exit 1
    fi
done

RENDERED_EQUATION_COUNT="$({
    sed -n 's/^NCP-EQUATION-COUNT=\([0-9][0-9]*\)$/\1/p' "$LOG"
} | tail -n 1)"
if [[ -z "$RENDERED_EQUATION_COUNT" || "$RENDERED_EQUATION_COUNT" != "$EQUATION_COUNT" ]]; then
    echo "NCP system-design PDF check: numbered and audited equation counts differ" >&2
    exit 1
fi

pdfinfo "$BUILT" >"$BUILD_DIR/built.info.full"
if ! grep -F "source-set-sha256:$PUBLICATION_SOURCE_DIGEST" \
    "$BUILD_DIR/built.info.full" >/dev/null; then
    echo "NCP system-design PDF check: source-set commitment is absent" >&2
    exit 1
fi
if ! grep -F 'Page size:       595.276 x 841.89 pts (A4)' \
    "$BUILD_DIR/built.info.full" >/dev/null; then
    echo "NCP system-design PDF check: page geometry is not A4" >&2
    exit 1
fi
if ! grep -F 'JavaScript:      no' "$BUILD_DIR/built.info.full" >/dev/null; then
    echo "NCP system-design PDF check: PDF contains or may contain JavaScript" >&2
    exit 1
fi

if ! pdffonts "$BUILT" | awk '
    NR > 2 { seen = 1; if ($(NF - 4) != "yes") bad = 1 }
    END { exit (!seen || bad) }
'; then
    echo "NCP system-design PDF check: PDF has a missing or non-embedded font" >&2
    exit 1
fi

case "$MODE" in
    --write)
        mkdir -p "$ROOT/$(dirname "$COMMITTED")"
        cp "$BUILT" "$ROOT/$COMMITTED"
        ;;
    --check)
        if [[ ! -f "$ROOT/$COMMITTED" ]]; then
            echo "NCP system-design PDF check: committed PDF is missing" >&2
            exit 1
        fi
        if ! cmp -s "$BUILT" "$ROOT/$COMMITTED"; then
            echo "NCP system-design PDF check: committed PDF is stale or not reproducible" >&2
            exit 1
        fi
        ;;
    --cross-toolchain)
        if [[ ! -f "$ROOT/$COMMITTED" ]]; then
            echo "NCP system-design PDF check: committed PDF is missing" >&2
            exit 1
        fi
        # Body and mathematics keep lexical boundaries. Each complete figure Form
        # joins its ordered SVG glyph roster. Same-toolchain --check stays byte-exact.
        publication_python="${NCP_PUBLICATION_PYTHON:-python3}"
        "$publication_python" "$ROOT/scripts/test_publication_pdf_text.py"
        "$publication_python" "$ROOT/scripts/check_publication_pdf_text.py" \
            "$BUILT" "$ROOT/$COMMITTED" "$ROOT/$SOURCE" \
            "$ROOT/docs/diagrams" "${figures[@]}"
        pdfinfo "$BUILT" | grep -E '^(Pages|Page size):' >"$BUILD_DIR/built.info"
        pdfinfo "$ROOT/$COMMITTED" | grep -E '^(Pages|Page size):' \
            >"$BUILD_DIR/committed.info"
        if ! cmp -s "$BUILD_DIR/built.info" "$BUILD_DIR/committed.info"; then
            echo "NCP system-design PDF check: page geometry differs" >&2
            exit 1
        fi
        if ! pdfinfo "$ROOT/$COMMITTED" \
            | grep -F "source-set-sha256:$PUBLICATION_SOURCE_DIGEST" >/dev/null; then
            echo "NCP system-design PDF check: committed source-set commitment differs" >&2
            exit 1
        fi
        ;;
esac

DIGEST="$({ shasum -a 256 "$BUILT" 2>/dev/null || sha256sum "$BUILT"; } | awk '{print $1}')"
PAGES="$(pdfinfo "$BUILT" | awk '/^Pages:/ {print $2}')"
RSVG_VERSION="$(rsvg-convert --version | sed -n '1p')"
LATEXMK_VERSION="$(latexmk -v | sed -n '1p')"

echo "OK: NCP system-design PDF is warning-free ($PAGES pages, $EQUATION_COUNT audited equations, $DIGEST)"
echo "toolchain: $LATEXMK_VERSION; $RSVG_VERSION"
