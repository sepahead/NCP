#!/usr/bin/env bash
# repin-ncp.sh — re-pin every NCP consumer to a single target tag, in one command.
#
# Consumers re-pinned (each skipped gracefully if its dir is missing):
#   1. crebain                      — src-tauri/Cargo.toml (ncp-core, ncp-zenoh tags),
#                                      package.json (#<tag>, KEEPING the @sepehrmn/ncp key),
#                                      then `bun install` (regen bun.lock) + refresh src-tauri/Cargo.lock.
#   2. pid_vla/crates/ncp-observer  — Cargo.toml (ncp-core, ncp-zenoh tags) + refresh that
#                                      crate's OWN Cargo.lock (it is excluded from pid_vla's
#                                      default workspace).
#   3. Paper2Brain                  — delegate to its own scripts/sync_ncp_mirror.sh <tag>;
#                                      NEVER hand-edit the vendored mirror.
#
# This script edits files + refreshes lockfiles ONLY. It does NOT git-commit, push, or
# stage anything. It prints a per-repo summary and the suggested review/commit commands.
#
# NOTE: this re-pins NCP consumers only. The pid_vla/pid-rs git submodule is a SEPARATE
# concern (it tracks pid-rs's own tags, not NCP tags) and is intentionally NOT touched here.
#
# Usage:
#   scripts/repin-ncp.sh <tag> [base-dir]
#     <tag>       NCP git tag to pin to, e.g. v0.2.6 (matches v<MAJOR>.<MINOR>.<PATCH>[-pre][+build]).
#     [base-dir]  Directory holding the sibling repos. Defaults to the parent of the NCP repo
#                 (i.e. this script lives in <base-dir>/NCP/scripts/repin-ncp.sh).
#
# Conventions: canonical remote is https://github.com/sepahead/NCP. macOS-portable in-place
# edits via `perl -pi -e`. No AI/agent attribution anywhere.
set -euo pipefail

# ── Args & layout ────────────────────────────────────────────────────────────
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $(basename "$0") <tag> [base-dir]" >&2
  exit 2
fi

TAG="$1"

# Validate the tag: a v-prefixed semver, optionally with a -prerelease and/or +build suffix
# (e.g. v0.2.6, v0.2.6-rc.1, v0.2.6-rc.1+build.5). Rejects things like v0.2, 0.2.6, v0.2.6.foo.
if [[ ! "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.]+)?(\+[0-9A-Za-z.]+)?$ ]]; then
  echo "ERROR: tag '$TAG' is not a valid NCP tag (expected like v0.2.6 or v0.2.6-rc.1)." >&2
  exit 2
fi

# NCP repo root = parent of this script's dir; base-dir defaults to NCP's parent.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NCP_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BASE_DIR="${2:-$(cd "$NCP_ROOT/.." && pwd)}"

if [[ ! -d "$BASE_DIR" ]]; then
  echo "ERROR: base-dir '$BASE_DIR' does not exist." >&2
  exit 2
fi
# Normalise base-dir to an absolute path so all downstream paths are absolute.
BASE_DIR="$(cd "$BASE_DIR" && pwd)"

CREBAIN_DIR="$BASE_DIR/crebain"
PID_VLA_DIR="$BASE_DIR/pid_vla"
PAPER2BRAIN_DIR="$BASE_DIR/Paper2Brain"

# Locate bun (prefer ~/.bun/bin/bun, else PATH).
BUN_BIN=""
if [[ -x "$HOME/.bun/bin/bun" ]]; then
  BUN_BIN="$HOME/.bun/bin/bun"
elif command -v bun >/dev/null 2>&1; then
  BUN_BIN="$(command -v bun)"
fi

# ── Summary bookkeeping ──────────────────────────────────────────────────────
# Each entry: "<repo>\t<status>\t<detail>"
SUMMARY=()
# Suggested review/commit commands, one block per touched repo.
REVIEW_CMDS=()
# Track whether any consumer ended in a degraded state (edited but a lock-refresh failed/skipped).
HAD_WARNINGS=0

add_summary() { SUMMARY+=("$1"$'\t'"$2"$'\t'"$3"); }

note()  { printf '  . %s\n' "$1"; }
hdr()   { printf '\n== %s ==\n' "$1"; }
warn()  { printf '  ! %s\n' "$1" >&2; HAD_WARNINGS=1; }

# Portable in-place edit: rewrite the NCP tag ONLY on Cargo dependency lines that point at
# sepahead/NCP. The leading dep-line shape (`<name> = { ... git = "...sepahead/NCP" ...`) is
# required so a comment that merely mentions `tag = "..."` and sepahead/NCP is never touched.
# Cargo.toml form:  ncp-core = { git = "https://github.com/sepahead/NCP", tag = "vX.Y.Z", ... }
repin_cargo_manifest() {
  local file="$1"
  perl -pi -e 'if (/^\s*[A-Za-z0-9_-]+\s*=\s*\{.*git\s*=\s*"[^"]*sepahead\/NCP"/) { s{(tag\s*=\s*")[^"]*(")}{${1}'"$TAG"'${2}}g; }' "$file"
}

# package.json form:  "@sepehrmn/ncp": "github:sepahead/NCP#vX.Y.Z"
# Only the #<tag> fragment changes; the @sepehrmn/ncp key is preserved.
repin_package_json() {
  local file="$1"
  perl -pi -e 's{(github:sepahead/NCP#)[^"]*}{${1}'"$TAG"'}g' "$file"
}

echo "Re-pinning all NCP consumers to tag: $TAG"
echo "  base-dir : $BASE_DIR"
echo "  NCP repo : $NCP_ROOT"

# ── 1) crebain ───────────────────────────────────────────────────────────────
hdr "crebain"
if [[ ! -d "$CREBAIN_DIR" ]]; then
  warn "crebain not found at $CREBAIN_DIR — skipping."
  add_summary "crebain" "SKIPPED" "directory missing: $CREBAIN_DIR"
else
  CREBAIN_CARGO="$CREBAIN_DIR/src-tauri/Cargo.toml"
  CREBAIN_PKG="$CREBAIN_DIR/package.json"
  crebain_touched=0

  if [[ -f "$CREBAIN_CARGO" ]]; then
    repin_cargo_manifest "$CREBAIN_CARGO"
    note "rewrote ncp-core / ncp-zenoh tag -> $TAG in src-tauri/Cargo.toml"
    crebain_touched=1
  else
    warn "missing $CREBAIN_CARGO"
  fi

  if [[ -f "$CREBAIN_PKG" ]]; then
    repin_package_json "$CREBAIN_PKG"
    note "rewrote @sepehrmn/ncp pin -> github:sepahead/NCP#$TAG in package.json (key kept)"
    crebain_touched=1
  else
    warn "missing $CREBAIN_PKG"
  fi

  # Refresh bun.lock so package.json + lock move together (else the TS peer splits).
  # A bun failure must NOT abort the whole run — warn, mark, and carry on.
  if [[ -f "$CREBAIN_PKG" && -n "$BUN_BIN" ]]; then
    note "running 'bun install' to regenerate bun.lock ..."
    if ( cd "$CREBAIN_DIR" && "$BUN_BIN" install ); then
      note "bun.lock refreshed"
    else
      warn "'bun install' failed in crebain/ — bun.lock NOT refreshed; re-run 'bun install' there before committing"
    fi
  elif [[ -f "$CREBAIN_PKG" ]]; then
    warn "bun not found (~/.bun/bin/bun or PATH) — bun.lock NOT refreshed; run 'bun install' in crebain/ manually"
  fi

  # Refresh the Rust lockfile for the two NCP crates only.
  # A cargo failure (e.g. offline) must NOT abort the run — warn, mark, and carry on.
  if [[ -f "$CREBAIN_CARGO" ]]; then
    if command -v cargo >/dev/null 2>&1; then
      note "refreshing src-tauri/Cargo.lock (cargo update -p ncp-core -p ncp-zenoh) ..."
      if ( cd "$CREBAIN_DIR" && cargo update -p ncp-core -p ncp-zenoh --manifest-path src-tauri/Cargo.toml ); then
        note "src-tauri/Cargo.lock refreshed"
      else
        warn "cargo update failed in crebain/ — src-tauri/Cargo.lock NOT refreshed; re-run before committing"
      fi
    else
      warn "cargo not found — src-tauri/Cargo.lock NOT refreshed"
    fi
  fi

  if [[ "$crebain_touched" -eq 1 ]]; then
    add_summary "crebain" "REPINNED" "src-tauri/Cargo.toml + Cargo.lock, package.json + bun.lock -> $TAG"
    REVIEW_CMDS+=("# crebain
  git -C \"$CREBAIN_DIR\" diff -- src-tauri/Cargo.toml src-tauri/Cargo.lock package.json bun.lock
  git -C \"$CREBAIN_DIR\" add src-tauri/Cargo.toml src-tauri/Cargo.lock package.json bun.lock
  git -C \"$CREBAIN_DIR\" commit -m \"chore: re-pin NCP to $TAG\"")
  else
    add_summary "crebain" "SKIPPED" "no NCP manifest/package.json found under $CREBAIN_DIR"
  fi
fi

# ── 2) pid_vla/crates/ncp-observer ───────────────────────────────────────────
hdr "pid_vla/crates/ncp-observer"
OBSERVER_DIR="$PID_VLA_DIR/crates/ncp-observer"
if [[ ! -d "$OBSERVER_DIR" ]]; then
  warn "ncp-observer not found at $OBSERVER_DIR — skipping."
  add_summary "pid_vla/ncp-observer" "SKIPPED" "directory missing: $OBSERVER_DIR"
else
  OBSERVER_CARGO="$OBSERVER_DIR/Cargo.toml"

  if [[ -f "$OBSERVER_CARGO" ]]; then
    repin_cargo_manifest "$OBSERVER_CARGO"
    note "rewrote ncp-core / ncp-zenoh tag -> $TAG in crates/ncp-observer/Cargo.toml"

    # ncp-observer is excluded from pid_vla's default workspace and owns its Cargo.lock.
    # A cargo failure must NOT abort the run — warn, mark, and carry on.
    if command -v cargo >/dev/null 2>&1; then
      note "refreshing crates/ncp-observer/Cargo.lock (cargo update -p ncp-core -p ncp-zenoh) ..."
      if ( cd "$PID_VLA_DIR" && cargo update -p ncp-core -p ncp-zenoh --manifest-path crates/ncp-observer/Cargo.toml ); then
        note "crates/ncp-observer/Cargo.lock refreshed"
      else
        warn "cargo update failed in pid_vla/ — crates/ncp-observer/Cargo.lock NOT refreshed; re-run before committing"
      fi
    else
      warn "cargo not found — crates/ncp-observer/Cargo.lock NOT refreshed"
    fi

    add_summary "pid_vla/ncp-observer" "REPINNED" "crates/ncp-observer/Cargo.toml + Cargo.lock -> $TAG"
    REVIEW_CMDS+=("# pid_vla (ncp-observer)
  git -C \"$PID_VLA_DIR\" diff -- crates/ncp-observer/Cargo.toml crates/ncp-observer/Cargo.lock
  git -C \"$PID_VLA_DIR\" add crates/ncp-observer/Cargo.toml crates/ncp-observer/Cargo.lock
  git -C \"$PID_VLA_DIR\" commit -m \"chore: re-pin NCP observer to $TAG\"")
  else
    warn "missing $OBSERVER_CARGO"
    add_summary "pid_vla/ncp-observer" "SKIPPED" "Cargo.toml missing: $OBSERVER_CARGO"
  fi
fi

# ── 3) Paper2Brain (delegate to its own mirror sync) ─────────────────────────
hdr "Paper2Brain"
SYNC_SCRIPT="$PAPER2BRAIN_DIR/scripts/sync_ncp_mirror.sh"
P2B_REVIEW="# Paper2Brain
  git -C \"$PAPER2BRAIN_DIR\" diff -- ncp/.mirror-ref
  git -C \"$PAPER2BRAIN_DIR\" add ncp
  git -C \"$PAPER2BRAIN_DIR\" commit -m \"chore: re-sync NCP mirror to $TAG\"
  # then verify: ( cd \"$PAPER2BRAIN_DIR\" && scripts/check_ncp_mirror_drift.sh )"

if [[ ! -d "$PAPER2BRAIN_DIR" ]]; then
  warn "Paper2Brain not found at $PAPER2BRAIN_DIR — skipping."
  add_summary "Paper2Brain" "SKIPPED" "directory missing: $PAPER2BRAIN_DIR"
elif [[ ! -f "$SYNC_SCRIPT" ]]; then
  warn "$SYNC_SCRIPT missing — cannot re-pin Paper2Brain mirror; skipping."
  add_summary "Paper2Brain" "SKIPPED" "scripts/sync_ncp_mirror.sh missing"
else
  # The sync script may or may not have its +x bit; either way, run it via bash so the
  # delegation works regardless of the executable flag. A failure must NOT abort the run.
  if [[ ! -x "$SYNC_SCRIPT" ]]; then
    warn "sync_ncp_mirror.sh is not marked executable — running via 'bash'."
  fi
  note "delegating to scripts/sync_ncp_mirror.sh $TAG (do NOT hand-edit the mirror) ..."
  if bash "$SYNC_SCRIPT" "$TAG"; then
    add_summary "Paper2Brain" "REPINNED" "ncp/ mirror + ncp/.mirror-ref -> $TAG (via sync_ncp_mirror.sh)"
    REVIEW_CMDS+=("$P2B_REVIEW")
  else
    warn "sync_ncp_mirror.sh failed for $TAG — Paper2Brain mirror NOT updated"
    add_summary "Paper2Brain" "FAILED" "sync_ncp_mirror.sh $TAG returned non-zero"
  fi
fi

# ── Final per-repo summary ───────────────────────────────────────────────────
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
  for block in "${REVIEW_CMDS[@]}"; do
    printf '%s\n\n' "$block"
  done
else
  echo ""
  echo "Nothing was re-pinned (all consumers missing/failed under $BASE_DIR)."
fi

if [[ "$HAD_WARNINGS" -ne 0 ]]; then
  echo "One or more steps were skipped or failed (see '!' lines above). Review before committing." >&2
fi
