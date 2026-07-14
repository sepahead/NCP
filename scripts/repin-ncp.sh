#!/usr/bin/env bash
# repin-ncp.sh — re-pin every NCP consumer to a single target tag, in one command.
#
# DECOUPLED BY DESIGN: this script holds **no knowledge of any specific consumer**.
# It discovers consumers by globbing for a `.ncp-consumer` descriptor in each
# sibling repo under base-dir, and applies a standard re-pin recipe per declared
# pin type (or a consumer-supplied `repin_cmd` for custom cases like a vendored
# mirror). Onboarding a new consumer requires ZERO changes here — the consumer
# commits a `.ncp-consumer` to its own repo. See `INTEGRATING.md`.
#
# `.ncp-consumer` lines understood here:
#   cargo_tag  <Cargo.toml>     # rewrite ncp-core/ncp-zenoh `tag = "vX"` and any
#                               #   explicit `version = "X"` constraint, then
#                               #   `cargo update -p ncp-core -p ncp-zenoh --manifest-path <Cargo.toml>`
#   cargo_rev  <Cargo.toml> <tag> <40-hex-rev>  # rewrite exact revision/version,
#                               #   descriptor metadata, and lockfile
#   npm_tag    <package.json>   # rewrite `github:.../NCP#vX` (key kept), then `bun install`
#   mirror_rev <pin-file> <tag> <40-hex-rev> # immutable mirror metadata; the
#                               #   consumer-owned command updates the mirror/pin
#   cargo_lock / cargo_lock_rev / npm_lock / mirror_ref / python_wire  # checker-only
#                               # (runtime wire migrations are deliberately manual)
#   repin_cmd  <cmd ... {TAG} ... {REV}> # consumer-owned command, run in its repo;
#                               #   placeholders are substituted. Use for mirrors/bespoke flows.
#
# This script edits files + refreshes lockfiles ONLY. It does NOT git-commit, push, or
# stage anything. It prints a per-repo summary and the suggested review/commit commands.
#
# Usage:
#   scripts/repin-ncp.sh <tag> [base-dir]
#     <tag>       NCP git tag to pin to, e.g. v0.3.0 (v<MAJOR>.<MINOR>.<PATCH>[-pre][+build]).
#     [base-dir]  Directory holding the sibling repos. Defaults to the parent of the NCP repo.
#
# Conventions: macOS-portable in-place edits via `perl -pi -e`. No AI/agent attribution.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $(basename "$0") <tag> [base-dir]" >&2
  exit 2
fi

TAG="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
NCP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
PIN_GUARD="$SCRIPT_DIR/consumer_pin_guard.py"
if ! python3 "$PIN_GUARD" validate-tag "$TAG" >/dev/null; then
  echo "ERROR: tag '$TAG' is not a valid NCP tag (expected like v0.3.0 or v0.3.0-rc.1)." >&2
  exit 2
fi

BASE_DIR="${2:-$(cd "$NCP_ROOT/.." && pwd)}"
if [[ ! -d "$BASE_DIR" ]]; then
  echo "ERROR: base-dir '$BASE_DIR' does not exist." >&2
  exit 2
fi
BASE_DIR="$(cd "$BASE_DIR" && pwd -P)"

TAG_REV=""

# Locate bun (prefer ~/.bun/bin/bun, else PATH).
BUN_BIN=""
if [[ -x "$HOME/.bun/bin/bun" ]]; then BUN_BIN="$HOME/.bun/bin/bun"
elif command -v bun >/dev/null 2>&1; then BUN_BIN="$(command -v bun)"; fi

SUMMARY=()
REVIEW_CMDS=()
HAD_WARNINGS=0
add_summary() { SUMMARY+=("$1"$'\t'"$2"$'\t'"$3"); }
note()  { printf '  . %s\n' "$1"; }
hdr()   { printf '\n== %s ==\n' "$1"; }
warn()  { printf '  ! %s\n' "$1" >&2; HAD_WARNINGS=1; }

# Syntax-aware in-place edits are delegated to the same parser used by the
# read-only checker. It validates the complete candidate before one atomic replace.
repin_cargo_manifest() {
  python3 "$PIN_GUARD" rewrite-cargo "$1" --mode tag --tag "$TAG"
}
repin_cargo_rev_manifest() {
  python3 "$PIN_GUARD" rewrite-cargo "$1" --mode rev --tag "$TAG" --revision "$TAG_REV"
}
update_revision_descriptor() {
  TAG="$TAG" TAG_REV="$TAG_REV" perl -pi -e '
    chomp;
    if (/^(\s*(?:cargo_(?:rev|lock_rev)|mirror_rev)\s+\S+)(?:\s+\S+\s+\S+)?(\s*(?:#.*)?)$/) {
      $_ = "$1 $ENV{TAG} $ENV{TAG_REV}$2";
    }
    $_ .= "\n";
  ' "$1"
}
# package.json string tokens are decoded before replacement, so JSON escapes and
# arbitrary dependency aliases cannot evade or redirect the rewrite.
repin_package_json() {
  python3 "$PIN_GUARD" rewrite-npm "$1" --tag "$TAG"
}

echo "Re-pinning all NCP consumers to tag: $TAG"
echo "  base-dir : $BASE_DIR"
echo "  NCP repo : $NCP_ROOT"

shopt -s nullglob
descriptors=("$BASE_DIR"/*/.ncp-consumer)
shopt -u nullglob
if [[ "${#descriptors[@]}" -eq 0 ]]; then
  echo "No consumers found under $BASE_DIR (no */.ncp-consumer descriptors). Nothing to do." >&2
  echo "A consumer registers by committing a .ncp-consumer file to its repo root (see INTEGRATING.md)." >&2
  exit 1
fi

# One shared parser validates every descriptor and declared file before the first
# consumer command or write. This includes exact arities, physical paths, TOML/JSON
# decoding, selector exclusivity, origin policy, and fleet revision coherence.
if ! python3 "$PIN_GUARD" preflight "$BASE_DIR"; then
  echo "No consumers were modified because descriptor validation failed." >&2
  exit 1
fi

# Revision-pinned consumers deliberately avoid relying on a movable remote tag.
# Resolve the requested release to its commit only when such a consumer exists;
# tag-only fleets can still be re-pinned from a shallow checkout without tags.
has_revision_consumer=0
for desc in "${descriptors[@]}"; do
  if perl -ne '$found = 1 if /^\s*(?:cargo_(?:rev|lock_rev)|mirror_rev)\s+/; END { exit(!$found) }' "$desc"; then
    has_revision_consumer=1
    break
  fi
done
if [[ "$has_revision_consumer" -eq 1 ]] &&
   ! TAG_REV="$(git -C "$NCP_ROOT" rev-parse --verify "refs/tags/${TAG}^{commit}" 2>/dev/null)"; then
  echo "ERROR: revision-pinned consumers require local tag '$TAG', but it is unavailable." >&2
  exit 2
fi

for desc in "${descriptors[@]}"; do
  consumer_dir="$(cd "$(dirname "$desc")" && pwd -P)"
  consumer_name="$(basename "$consumer_dir")"
  hdr "$consumer_name"

  # Parse the descriptor into typed target lists.
  cargo_tomls=(); cargo_rev_tomls=(); npm_jsons=(); repin_cmd=""; consumer_revision_pinned=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    IFS=$' \t' read -r -a fields <<< "$line"
    [[ "${#fields[@]}" -ge 2 ]] || continue
    case "${fields[0]}" in
      cargo_tag) cargo_tomls+=("${fields[1]}") ;;
      cargo_rev) cargo_rev_tomls+=("${fields[1]}"); consumer_revision_pinned=1 ;;
      cargo_lock_rev|mirror_rev) consumer_revision_pinned=1 ;;
      npm_tag)   npm_jsons+=("${fields[1]}") ;;
      repin_cmd) repin_cmd="${line#*repin_cmd }" ;;   # rest of line, verbatim
    esac
  done < "$desc"

  touched=0
  consumer_failed=0
  review_files=()

  # 1) Consumer-owned custom re-pin (e.g. a vendored mirror's sync script).
  if [[ -n "$repin_cmd" ]]; then
    if [[ "$repin_cmd" == *'{REV}'* ]] &&
       { [[ "$consumer_revision_pinned" -ne 1 ]] || [[ -z "$TAG_REV" ]]; }; then
      warn "repin_cmd requests {REV}, but the descriptor has no revision-pinned row"
      add_summary "$consumer_name" "FAILED" "{REV} requested without revision metadata"
      continue
    fi
    cmd="${repin_cmd//\{TAG\}/$TAG}"
    cmd="${cmd//\{REV\}/$TAG_REV}"
    note "running consumer repin_cmd: $cmd"
    if ( cd "$consumer_dir" && bash -c "$cmd" ); then
      touched=1
      if [[ "$consumer_revision_pinned" -eq 1 ]]; then
        update_revision_descriptor "$desc"
        note "updated revision-pin descriptor metadata -> $TAG ($TAG_REV)"
        add_summary "$consumer_name" "REPINNED" "via repin_cmd -> $TAG ($TAG_REV)"
      else
        add_summary "$consumer_name" "REPINNED" "via repin_cmd -> $TAG"
      fi
      REVIEW_CMDS+=("# $consumer_name (consumer-owned re-pin)
  git -C \"$consumer_dir\" diff
  git -C \"$consumer_dir\" add -A && git -C \"$consumer_dir\" commit -m \"chore: re-pin NCP to $TAG\"")
    else
      warn "repin_cmd failed in $consumer_name — NOT re-pinned"
      add_summary "$consumer_name" "FAILED" "repin_cmd returned non-zero"
    fi
    continue
  fi

  # 2) Standard cargo re-pin.
  # `${arr[@]+"${arr[@]}"}` expands to nothing for an EMPTY array — bash 3.2 (macOS)
  # errors on a bare `"${empty[@]}"` under `set -u`, so a consumer that declares only
  # npm (or only cargo) must not abort the whole run.
  for rel in ${cargo_tomls[@]+"${cargo_tomls[@]}"}; do
    f="$consumer_dir/$rel"
    if [[ -f "$f" ]]; then
      repin_cargo_manifest "$f"; note "rewrote ncp-core/ncp-zenoh tag/version -> $TAG in $rel"; touched=1; review_files+=("$rel")
      if command -v cargo >/dev/null 2>&1; then
        note "refreshing lockfile (cargo update -p ncp-core -p ncp-zenoh --manifest-path $rel) ..."
        if ( cd "$consumer_dir" && cargo update -p ncp-core -p ncp-zenoh --manifest-path "$rel" ); then
          note "Cargo.lock refreshed"
        else warn "cargo update failed in $consumer_name ($rel) — Cargo.lock NOT refreshed; re-run before committing"; consumer_failed=1; fi
      else warn "cargo not found — Cargo.lock NOT refreshed for $consumer_name"; consumer_failed=1; fi
    else warn "declared cargo_tag file missing: $f"; consumer_failed=1; fi
  done

  # 3) Exact-revision Cargo re-pin. The descriptor records the human release
  # tag and immutable commit together so the checker can verify both the
  # manifest and resolved lock source without consulting a remote tag.
  repinned_revision=0
  for rel in ${cargo_rev_tomls[@]+"${cargo_rev_tomls[@]}"}; do
    f="$consumer_dir/$rel"
    if [[ -f "$f" ]]; then
      repin_cargo_rev_manifest "$f"; note "rewrote ncp-core/ncp-zenoh rev/version -> $TAG ($TAG_REV) in $rel"; touched=1; repinned_revision=1; review_files+=("$rel")
      if command -v cargo >/dev/null 2>&1; then
        note "refreshing lockfile (cargo update -p ncp-core -p ncp-zenoh --manifest-path $rel) ..."
        if ( cd "$consumer_dir" && cargo update -p ncp-core -p ncp-zenoh --manifest-path "$rel" ); then
          note "Cargo.lock refreshed"
        else warn "cargo update failed in $consumer_name ($rel) — Cargo.lock NOT refreshed; re-run before committing"; consumer_failed=1; fi
      else warn "cargo not found — Cargo.lock NOT refreshed for $consumer_name"; consumer_failed=1; fi
    else warn "declared cargo_rev file missing: $f"; consumer_failed=1; fi
  done
  if [[ "$repinned_revision" -eq 1 ]]; then
    update_revision_descriptor "$desc"
    review_files+=(".ncp-consumer")
    note "updated revision-pin descriptor metadata -> $TAG ($TAG_REV)"
  fi

  # 4) Standard npm/bun re-pin. (Same bash-3.2 empty-array guard as the cargo loop —
  # a cargo-only consumer like prisoma has no npm_jsons and must not abort here.)
  for rel in ${npm_jsons[@]+"${npm_jsons[@]}"}; do
    f="$consumer_dir/$rel"
    if [[ -f "$f" ]]; then
      repin_package_json "$f"; note "rewrote @scope/ncp pin -> #$TAG in $rel (key kept)"; touched=1; review_files+=("$rel")
      if [[ -n "$BUN_BIN" ]]; then
        note "running 'bun install' to regenerate the lockfile ..."
        if ( cd "$consumer_dir" && "$BUN_BIN" install ); then note "bun lockfile refreshed"
        else warn "'bun install' failed in $consumer_name — lockfile NOT refreshed; re-run before committing"; consumer_failed=1; fi
      else warn "bun not found — lockfile NOT refreshed for $consumer_name; run 'bun install' manually"; consumer_failed=1; fi
    else warn "declared npm_tag file missing: $f"; consumer_failed=1; fi
  done

  if [[ "$touched" -eq 1 ]]; then
    if [[ "$consumer_failed" -eq 1 ]]; then
      add_summary "$consumer_name" "INCOMPLETE" "pin files changed, but a required refresh failed"
    else
      [[ -n "${review_files+x}" ]] && add_summary "$consumer_name" "REPINNED" "$(printf '%s ' "${review_files[@]}")-> $TAG"
    fi
    REVIEW_CMDS+=("# $consumer_name
  git -C \"$consumer_dir\" diff
  git -C \"$consumer_dir\" add -A && git -C \"$consumer_dir\" commit -m \"chore: re-pin NCP to $TAG\"")
  else
    add_summary "$consumer_name" "SKIPPED" "no re-pinnable target found (.ncp-consumer declared none present)"
  fi
done

hdr "Post-repin verification"
if ! "$SCRIPT_DIR/check-consumer-pins.sh" "$TAG" "$BASE_DIR"; then
  warn "consumer pin verification failed after re-pin"
fi

hdr "Summary — re-pin to $TAG"
printf '\n%-22s %-9s %s\n' "REPO" "STATUS" "DETAIL"
printf -- '%-22s %-9s %s\n' "----" "------" "------"
for row in "${SUMMARY[@]}"; do
  IFS=$'\t' read -r repo status detail <<< "$row"
  printf '%-22s %-9s %s\n' "$repo" "$status" "$detail"
done

echo ""
echo "No commits, pushes, or staging were performed. Files + lockfiles were edited in place."
if [[ ${#REVIEW_CMDS[@]} -gt 0 ]]; then
  echo ""
  echo "Suggested review / commit commands (the maintainer pushes to main directly — no PRs):"
  echo ""
  for block in "${REVIEW_CMDS[@]}"; do printf '%s\n\n' "$block"; done
else
  echo ""
  echo "Nothing was re-pinned (no consumers with re-pinnable targets under $BASE_DIR)."
fi
if [[ "$HAD_WARNINGS" -ne 0 ]]; then
  echo "One or more steps were skipped or failed (see '!' lines above). Review before committing." >&2
  exit 1
fi
