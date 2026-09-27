#!/usr/bin/env bash
# Check the discrete arithmetic of the NCP system-design report with Lean 4 core.
# A pass proves the stated arithmetic facts only. It is not protocol, security,
# safety, stability, or release evidence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
LEAN_DIR="docs/publication/lean"
SOURCE="$LEAN_DIR/NcpDesign.lean"
EXPECTED_VERSION="4.23.0"

if [[ "$#" != "0" ]]; then
    echo "usage: $0" >&2
    exit 2
fi
if ! command -v lean >/dev/null 2>&1; then
    echo "NCP design Lean check: missing command: lean" >&2
    exit 2
fi
if [[ ! -f "$ROOT/$SOURCE" ]]; then
    echo "NCP design Lean check: source is missing: $SOURCE" >&2
    exit 1
fi

# Run from the Lean directory, so elan selects the pinned lean-toolchain file.
cd "$ROOT/$LEAN_DIR"
version="$(lean --version)"
case "$version" in
    "Lean (version $EXPECTED_VERSION,"*) ;;
    *)
        echo "NCP design Lean check: expected Lean $EXPECTED_VERSION, found: $version" >&2
        exit 2
        ;;
esac

# The file must not weaken the kernel check.
forbidden='\b(sorry|admit|axiom|native_decide|implemented_by|extern|unsafe|opaque)\b'
if grep -nE "$forbidden" NcpDesign.lean >&2; then
    echo "NCP design Lean check: the file uses a forbidden construct" >&2
    exit 1
fi

output="$(lean NcpDesign.lean 2>&1)" || {
    printf '%s\n' "$output" >&2
    echo "NCP design Lean check: Lean rejected the file" >&2
    exit 1
}
if [[ -n "$output" ]]; then
    printf '%s\n' "$output" >&2
    echo "NCP design Lean check: Lean reported a warning or message" >&2
    exit 1
fi

theorems="$(grep -cE '^theorem ' NcpDesign.lean)"
echo "OK: NCP design arithmetic is Lean-checked ($theorems theorems; $version)"
