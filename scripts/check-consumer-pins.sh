#!/usr/bin/env bash
# Report the NCP pin each downstream consumer currently references and verify they
# agree. READ-ONLY: this script never writes to any repo, runs no builds, and makes
# no network/git calls — it only inspects pin files on disk. Use it as a pre-flight
# or CI guard around an NCP tag bump.
#
# Consumers inspected (all siblings of this NCP repo under base-dir):
#   - crebain/src-tauri/Cargo.toml   ncp-core / ncp-zenoh  git tag
#   - crebain/src-tauri/Cargo.lock   resolved  NCP?tag=<tag>
#   - crebain/package.json           "@sepehrmn/ncp": "github:sepahead/NCP#<tag>"
#   - crebain/bun.lock               same dep spec (#<tag>) + the resolved commit
#   - pid_vla/crates/ncp-observer/Cargo.toml   ncp-core / ncp-zenoh git tag
#   - Paper2Brain/ncp/.mirror-ref    vendored-mirror pin
#
# The npm scope key "@sepehrmn/ncp" is a deliberate import alias for a
# github:sepahead/NCP dependency — only the trailing "#<tag>" is the pin.
#
# Tracks sepahead/NCP#8 (drift-guarded pins).
set -euo pipefail

usage() {
  cat <<'EOF'
check-consumer-pins.sh — report and verify the NCP pin each consumer references.

READ-ONLY: inspects pin files only. No writes, no builds, no git/network calls.

Usage:
  check-consumer-pins.sh [expected-tag] [base-dir]

  expected-tag   If given, every consumer MUST reference exactly this tag;
                 the script exits non-zero otherwise.
  base-dir       Directory holding the sibling repos (NCP, crebain, pid_vla,
                 Paper2Brain). Defaults to the parent of this NCP checkout.

  With no expected-tag the script only checks the consumers agree with one
  another; it exits non-zero if they disagree.

Consumers inspected:
  crebain/src-tauri/Cargo.toml   ncp-core / ncp-zenoh git tag
  crebain/src-tauri/Cargo.lock   resolved NCP?tag=<tag>
  crebain/package.json           "@sepehrmn/ncp": "github:sepahead/NCP#<tag>"
  crebain/bun.lock               same dep spec (#<tag>) + the resolved commit
  pid_vla/crates/ncp-observer/Cargo.toml   ncp-core / ncp-zenoh git tag
  Paper2Brain/ncp/.mirror-ref    vendored-mirror pin

Exit codes: 0 = ok; 1 = mismatch / missing / unresolved pin; 2 = bad usage.
EOF
}

# --- argument parsing (positional, but trap -h/--help and stray flags) --------
EXPECTED=""
BASE_DIR=""
positional=()
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    -*)        echo "ERROR: unknown option '$arg'" >&2; echo >&2; usage >&2; exit 2 ;;
    *)         positional+=("$arg") ;;
  esac
done
if [[ "${#positional[@]}" -ge 1 ]]; then EXPECTED="${positional[0]}"; fi
if [[ "${#positional[@]}" -ge 2 ]]; then BASE_DIR="${positional[1]}"; fi
if [[ "${#positional[@]}" -gt 2 ]]; then
  echo "ERROR: too many arguments" >&2; echo >&2; usage >&2; exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NCP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -z "$BASE_DIR" ]]; then BASE_DIR="$(cd "$NCP_ROOT/.." && pwd)"; fi

if [[ ! -d "$BASE_DIR" ]]; then
  echo "ERROR: base-dir '$BASE_DIR' is not a directory" >&2
  exit 2
fi
BASE_DIR="$(cd "$BASE_DIR" && pwd)"

# Consumer file locations (relative to BASE_DIR).
CREBAIN_CARGO_TOML="$BASE_DIR/crebain/src-tauri/Cargo.toml"
CREBAIN_CARGO_LOCK="$BASE_DIR/crebain/src-tauri/Cargo.lock"
CREBAIN_PKG_JSON="$BASE_DIR/crebain/package.json"
CREBAIN_BUN_LOCK="$BASE_DIR/crebain/bun.lock"
OBSERVER_CARGO_TOML="$BASE_DIR/pid_vla/crates/ncp-observer/Cargo.toml"
MIRROR_REF="$BASE_DIR/Paper2Brain/ncp/.mirror-ref"

# Parallel arrays describing each (sub-)consumer row: a human label and the tag we
# extracted (or a sentinel: "__MISSING__" = file absent, "__UNRESOLVED__" = file
# present but no pin matched).
LABELS=()
TAGS=()

# add_row LABEL TAG
add_row() {
  LABELS+=("$1")
  TAGS+=("$2")
}

# Extract the first capture group of a Perl regex from a file, or a sentinel.
# The regex is passed via the environment so Perl compiles it directly — no need
# to escape "/" and no shell-injection into the // delimiters. We use Perl (not
# grep -P) because BSD/macOS grep lacks -P.
# Args: <file> <perl-regex-with-one-capture-group>
first_match() {
  local file="$1" re="$2"
  [[ -f "$file" ]] || { printf '%s' "__MISSING__"; return; }
  local out
  out="$(RE="$re" perl -ne 'if (/$ENV{RE}/) { print "$1\n"; exit }' "$file" 2>/dev/null || true)"
  if [[ -z "$out" ]]; then
    printf '%s' "__UNRESOLVED__"
  else
    printf '%s' "$out"
  fi
}

# ---- crebain/src-tauri/Cargo.toml : ncp-core / ncp-zenoh git tag ----
# e.g.  ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v0.2.6", ... }
crebain_toml_tag="$(first_match "$CREBAIN_CARGO_TOML" \
  '^\s*ncp-(?:core|zenoh)\b.*\bgit\s*=\s*"[^"]*/NCP".*\btag\s*=\s*"([^"]+)"')"
add_row "crebain/src-tauri/Cargo.toml (ncp-core/ncp-zenoh tag)" "$crebain_toml_tag"

# ---- crebain/src-tauri/Cargo.lock : resolved NCP?tag=<tag> ----
crebain_lock_tag="$(first_match "$CREBAIN_CARGO_LOCK" \
  'git\+https://github\.com/sepahead/NCP\?tag=([^#"]+)')"
add_row "crebain/src-tauri/Cargo.lock (resolved NCP?tag=)" "$crebain_lock_tag"

# ---- crebain/package.json : "@sepehrmn/ncp": "github:sepahead/NCP#<tag>" ----
crebain_pkg_tag="$(first_match "$CREBAIN_PKG_JSON" \
  '"\@sepehrmn/ncp"\s*:\s*"github:sepahead/NCP#([^"]+)"')"
add_row "crebain/package.json (@sepehrmn/ncp #tag)" "$crebain_pkg_tag"

# ---- crebain/bun.lock : the spec entry (#<tag>) ----
# The top spec block carries the human pin: "@sepehrmn/ncp": "github:sepahead/NCP#<tag>".
# The resolved-package entry uses the form "@sepehrmn/ncp@github:..." (with an
# extra "@" before "github"), so this spec regex (key followed by ':') will not
# match it.
crebain_bun_tag="$(first_match "$CREBAIN_BUN_LOCK" \
  '"\@sepehrmn/ncp"\s*:\s*"github:sepahead/NCP#([^"]+)"')"
add_row "crebain/bun.lock (@sepehrmn/ncp spec #tag)" "$crebain_bun_tag"

# bun.lock also records the resolved commit (NCP#<sha>) — informational only; a
# commit sha is never equal to a tag string, so we surface it as a note rather
# than a row that must match. Pull it from the resolved entry, not the spec.
crebain_bun_commit=""
if [[ -f "$CREBAIN_BUN_LOCK" ]]; then
  crebain_bun_commit="$(RE='"\@sepehrmn/ncp\@github:sepahead/NCP#([0-9a-f]{7,40})"' \
    perl -ne 'if (/$ENV{RE}/) { print "$1\n"; exit }' "$CREBAIN_BUN_LOCK" 2>/dev/null || true)"
fi

# ---- pid_vla/crates/ncp-observer/Cargo.toml : ncp-core / ncp-zenoh git tag ----
observer_tag="$(first_match "$OBSERVER_CARGO_TOML" \
  '^\s*ncp-(?:core|zenoh)\b.*\bgit\s*=\s*"[^"]*/NCP".*\btag\s*=\s*"([^"]+)"')"
add_row "pid_vla/crates/ncp-observer/Cargo.toml (ncp-core/ncp-zenoh tag)" "$observer_tag"

# ---- Paper2Brain/ncp/.mirror-ref : vendored mirror pin ----
mirror_tag="__MISSING__"
if [[ -f "$MIRROR_REF" ]]; then
  mirror_tag="$(tr -d '[:space:]' < "$MIRROR_REF")"
  [[ -n "$mirror_tag" ]] || mirror_tag="__UNRESOLVED__"
fi
add_row "Paper2Brain/ncp/.mirror-ref (vendored mirror pin)" "$mirror_tag"

# ---------------------------------------------------------------------------
# Render the table.
# ---------------------------------------------------------------------------
render_tag() {
  case "$1" in
    __MISSING__)    printf '<file not found>' ;;
    __UNRESOLVED__) printf '<no pin matched>' ;;
    *)              printf '%s' "$1" ;;
  esac
}

# Column width for the label column.
maxw=0
for l in "${LABELS[@]}"; do
  (( ${#l} > maxw )) && maxw=${#l}
done

echo "NCP consumer pins (base-dir: $BASE_DIR)"
echo
printf '  %-*s  %s\n' "$maxw" "CONSUMER" "PIN"
printf '  %-*s  %s\n' "$maxw" "$(printf '%.0s-' $(seq 1 "$maxw"))" "----------------"
for i in "${!LABELS[@]}"; do
  printf '  %-*s  %s\n' "$maxw" "${LABELS[$i]}" "$(render_tag "${TAGS[$i]}")"
done
if [[ -n "$crebain_bun_commit" ]]; then
  echo
  printf '  note: crebain/bun.lock resolved commit = %s (informational)\n' "$crebain_bun_commit"
fi
echo

# ---------------------------------------------------------------------------
# Verdict.
# ---------------------------------------------------------------------------
rc=0
problems=()

# Any unresolved/missing pin is always a failure.
for i in "${!LABELS[@]}"; do
  case "${TAGS[$i]}" in
    __MISSING__)
      problems+=("${LABELS[$i]}: file not found")
      rc=1 ;;
    __UNRESOLVED__)
      problems+=("${LABELS[$i]}: file present but no NCP pin matched")
      rc=1 ;;
  esac
done

# Collect the set of concrete (resolved) tags actually seen.
concrete_tags=()
for t in "${TAGS[@]}"; do
  case "$t" in
    __MISSING__|__UNRESOLVED__) : ;;
    *) concrete_tags+=("$t") ;;
  esac
done

if [[ -n "$EXPECTED" ]]; then
  # Strict mode: every resolved consumer must equal EXPECTED.
  for i in "${!LABELS[@]}"; do
    case "${TAGS[$i]}" in
      __MISSING__|__UNRESOLVED__) : ;; # already reported above
      *)
        if [[ "${TAGS[$i]}" != "$EXPECTED" ]]; then
          problems+=("${LABELS[$i]}: pinned to '${TAGS[$i]}', expected '$EXPECTED'")
          rc=1
        fi ;;
    esac
  done
  if [[ "$rc" -eq 0 ]]; then
    echo "OK: all consumers pin NCP $EXPECTED"
  fi
else
  # Agreement mode: all resolved consumers must share one tag.
  if [[ "${#concrete_tags[@]}" -eq 0 ]]; then
    # No resolvable pin anywhere — nothing to agree on (failures already noted).
    :
  else
    uniq_tags="$(printf '%s\n' "${concrete_tags[@]}" | sort -u)"
    n_uniq="$(printf '%s\n' "$uniq_tags" | grep -c . || true)"
    if [[ "$n_uniq" -gt 1 ]]; then
      problems+=("consumers disagree; tags seen: $(printf '%s ' $uniq_tags)")
      rc=1
    elif [[ "$rc" -eq 0 ]]; then
      echo "OK: all consumers agree on NCP ${concrete_tags[0]}"
    fi
  fi
fi

if [[ "$rc" -ne 0 ]]; then
  echo "MISMATCH:" >&2
  for p in "${problems[@]}"; do
    echo "  - $p" >&2
  done
  echo >&2
  echo "  To re-pin, bump each consumer's manifest AND its lockfile to the target tag:" >&2
  echo "    - crebain: edit src-tauri/Cargo.toml + package.json, then re-run" >&2
  echo "      'cargo update -p ncp-core -p ncp-zenoh --manifest-path src-tauri/Cargo.toml'" >&2
  echo "      and 'bun install' (package.json + bun.lock must move together)." >&2
  echo "    - pid_vla: edit crates/ncp-observer/Cargo.toml, then 'cargo update -p ncp-core" >&2
  echo "      -p ncp-zenoh --manifest-path crates/ncp-observer/Cargo.toml'." >&2
  echo "    - Paper2Brain: run its own scripts/sync_ncp_mirror.sh <tag>; do NOT hand-edit" >&2
  echo "      the mirror (engram regenerates ncp/schemas and a drift guard checks it)." >&2
fi

exit "$rc"
