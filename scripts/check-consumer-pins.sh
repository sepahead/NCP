#!/usr/bin/env bash
# Report and verify every discovered consumer's NCP pin. Parsing and coherence
# live in consumer_pin_guard.py so this read-only checker and the mutating repinner
# cannot disagree about TOML, JSON/JSONC, descriptors, selectors, or revisions.
set -euo pipefail

usage() {
  cat <<'EOF'
check-consumer-pins.sh — report and verify the NCP pin each consumer references.

READ-ONLY: inspects pin files only. No writes, no builds, no git/network calls.

Usage:
  check-consumer-pins.sh [expected-tag] [base-dir]

  expected-tag   If given, every consumer MUST reference exactly this tag;
                 the script exits non-zero otherwise.
  base-dir       Directory holding the sibling repos. Defaults to the parent of
                 this NCP checkout.

  With no expected-tag the script checks compatibility-line agreement: pre-1.0
  consumers must share a minor, while stable consumers must share a major.

Consumers are discovered through one regular */.ncp-consumer descriptor. The
checker is read-only and fail-closed for malformed descriptors and pin files.

Exit codes: 0 = ok; 1 = mismatch / missing / unresolved pin; 2 = bad usage.
EOF
}

expected=""
base_dir=""
positional=()
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    -*) echo "ERROR: unknown option '$arg'" >&2; echo >&2; usage >&2; exit 2 ;;
    *) positional+=("$arg") ;;
  esac
done
if [[ "${#positional[@]}" -ge 1 ]]; then expected="${positional[0]}"; fi
if [[ "${#positional[@]}" -ge 2 ]]; then base_dir="${positional[1]}"; fi
if [[ "${#positional[@]}" -gt 2 ]]; then
  echo "ERROR: too many arguments" >&2
  echo >&2
  usage >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ncp_root="$(cd "$script_dir/.." && pwd -P)"
if [[ -z "$base_dir" ]]; then base_dir="$(cd "$ncp_root/.." && pwd -P)"; fi
if [[ ! -d "$base_dir" ]]; then
  echo "ERROR: base-dir '$base_dir' is not a directory" >&2
  exit 2
fi
base_dir="$(cd "$base_dir" && pwd -P)"

exec python3 "$script_dir/consumer_pin_guard.py" check "$base_dir" --expected "$expected"
