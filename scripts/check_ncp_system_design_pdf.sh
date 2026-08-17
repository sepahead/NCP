#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE="docs/publication/ncp-system-design.tex"
STYLE="docs/publication/ncp-report.sty"
COMMITTED="output/pdf/ncp-system-design.pdf"
SOURCE_DATE_EPOCH_VALUE="1786924800"
MODE="${1:---check}"

case "$MODE" in
    --write | --check | --cross-toolchain) ;;
    *)
        echo "usage: $0 [--write|--check|--cross-toolchain]" >&2
        exit 2
        ;;
esac

commands=(cmp latexmk pdfinfo pdffonts pdftotext python3 rsvg-convert)
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

figures=(
    admission-light
    ecosystem-light
    fsm-light
    lifecycle-light
    overview-light
    runtime-light
    sequence-light
    topology-light
    versioning-light
)

for figure in "${figures[@]}"; do
    input="$ROOT/docs/diagrams/$figure.svg"
    output="$BUILD_DIR/$figure.pdf"
    if [[ ! -f "$input" ]]; then
        echo "NCP system-design PDF check: figure is missing: docs/diagrams/$figure.svg" >&2
        exit 1
    fi
    rsvg-convert --format=pdf --output "$output" "$input"
done

PUBLICATION_SOURCE_DIGEST="$({ python3 - "$ROOT" "$SOURCE" "$STYLE" "${figures[@]}" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys

root = Path(sys.argv[1])
relative_paths = [Path(sys.argv[2]), Path(sys.argv[3])]
relative_paths.extend(Path("docs/diagrams") / f"{name}.svg" for name in sys.argv[4:])

hasher = sha256()
hasher.update(b"ncp.publication-source-set.v1\0")
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

printf '\\renewcommand{\\NcpPublicationSourceDigest}{%s}\n' \
    "$PUBLICATION_SOURCE_DIGEST" >"$BUILD_DIR/ncp-publication-identity.tex"

cp "$ROOT/$SOURCE" "$BUILD_DIR/ncp-system-design.tex"
cp "$ROOT/$STYLE" "$BUILD_DIR/ncp-report.sty"

(
    cd "$BUILD_DIR"
    SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH_VALUE" TZ=UTC \
        latexmk \
        -pdf \
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

if grep -E \
    '(^| )(LaTeX|Package [^ ]+) Warning:|Overfull \\hbox|Underfull \\hbox|Overfull \\vbox|Underfull \\vbox|undefined references|Fatal error' \
    "$LOG" >/dev/null; then
    grep -E \
        '(^| )(LaTeX|Package [^ ]+) Warning:|Overfull \\hbox|Underfull \\hbox|Overfull \\vbox|Underfull \\vbox|undefined references|Fatal error' \
        "$LOG" >&2
    echo "NCP system-design PDF check: LaTeX log contains a rejected diagnostic" >&2
    exit 1
fi

pdftotext -layout "$BUILT" "$BUILD_DIR/built.txt"
sentinels=(
    "NCP 1.0 System Design"
    "PROPOSED B01 DESIGN"
    "Finite memory and queue isolation"
    "Twenty-lens design review"
    "NOT RUN"
    "The equations expose the design accounting used here."
)
for sentinel in "${sentinels[@]}"; do
    if ! grep -F -- "$sentinel" "$BUILD_DIR/built.txt" >/dev/null; then
        echo "NCP system-design PDF check: rendered-text sentinel is absent: $sentinel" >&2
        exit 1
    fi
done

EQUATION_COUNT="$({ python3 - "$ROOT/$SOURCE" <<'PY'
from pathlib import Path
import re
import sys

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
        pdftotext -layout "$ROOT/$COMMITTED" "$BUILD_DIR/committed.txt"
        if ! cmp -s "$BUILD_DIR/built.txt" "$BUILD_DIR/committed.txt"; then
            echo "NCP system-design PDF check: extracted layout differs" >&2
            exit 1
        fi
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
