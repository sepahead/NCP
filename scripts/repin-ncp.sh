#!/usr/bin/env bash
# repin-ncp.sh — re-pin every NCP consumer to a single target tag, transactionally.
#
# Consumers are discovered through sibling `.ncp-consumer` descriptors. Before
# any write or consumer command, every descriptor, declared path, repository root,
# branch, worktree, standard tool, and required revision tag is validated. A failed
# mutation restores every touched consumer whose branch and HEAD still match its
# recorded clean Git state.
#
# `.ncp-consumer` lines understood here:
#   cargo_tag  <Cargo.toml>
#   cargo_rev  <Cargo.toml> <tag> <40-hex-rev>
#   npm_tag    <package.json>
#   mirror_rev <pin-file> <tag> <40-hex-rev>
#   cargo_lock / cargo_lock_rev / npm_lock / mirror_ref / python_wire
#   repin_cmd  <cmd ... {TAG} ... {REV}>
#
# The script edits files and refreshes lockfiles only. It never commits, pushes,
# or stages consumer changes.
#
# Usage:
#   scripts/repin-ncp.sh [--dry-run] <tag> [base-dir]
#
# `--dry-run` performs the complete fail-closed preflight and prints exact declared
# paths/actions, but runs no consumer command and writes no consumer file.
set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi
if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $(basename "$0") [--dry-run] <tag> [base-dir]" >&2
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
REQUIRED_BRANCH="main"

# Locate bun (prefer ~/.bun/bin/bun, else PATH).
BUN_BIN=""
if [[ -n "${HOME:-}" && -x "$HOME/.bun/bin/bun" ]]; then
  BUN_BIN="$HOME/.bun/bin/bun"
elif command -v bun >/dev/null 2>&1; then
  BUN_BIN="$(command -v bun)"
fi

SUMMARY=()
CONSUMER_DIRS=()
CONSUMER_NAMES=()
CONSUMER_HEADS=()
CONSUMER_BRANCHES=()
CONSUMER_GIT_DIRS=()
CONSUMER_TOUCHED=()
CHANGED_PATHS=()
LOCK_DIRS=()
TRANSACTION_ACTIVE=0
ROLLBACK_RUNNING=0
LOCKS_ACTIVE=0

add_summary() { SUMMARY+=("$1"$'\t'"$2"$'\t'"$3"); }
note() { printf '  . %s\n' "$1"; }
hdr() { printf '\n== %s ==\n' "$1"; }
warn() { printf '  ! %s\n' "$1" >&2; }
git_read() { GIT_OPTIONAL_LOCKS=0 git "$@"; }

assert_normal_index() {
  local consumer_dir="$1" consumer_name="$2" entry tag
  if ! git_read -C "$consumer_dir" ls-files -v -z >/dev/null; then
    warn "could not inspect the Git index in $consumer_name"
    return 1
  fi
  while IFS= read -r -d '' entry; do
    tag="${entry:0:1}"
    if [[ "$tag" != "H" ]]; then
      warn "$consumer_name has unsupported Git index state '$tag' (sparse/hidden/unmerged entries are unsafe for a transaction)"
      return 1
    fi
  done < <(git_read -C "$consumer_dir" ls-files -v -z)
}

clear_special_index_flags() {
  local consumer_dir="$1" entry tag
  local special_paths=()
  git_read -C "$consumer_dir" ls-files -v -z >/dev/null || return 1
  while IFS= read -r -d '' entry; do
    tag="${entry:0:1}"
    [[ "$tag" == "H" ]] || special_paths+=("${entry:2}")
  done < <(git_read -C "$consumer_dir" ls-files -v -z)
  if [[ "${#special_paths[@]}" -gt 0 ]]; then
    git -C "$consumer_dir" update-index \
      --no-assume-unchanged --no-skip-worktree -- "${special_paths[@]}"
  fi
}

release_consumer_locks() {
  [[ "$LOCKS_ACTIVE" -eq 1 ]] || return 0
  local failures=0 lock_dir owner
  for lock_dir in "${LOCK_DIRS[@]}"; do
    owner="$lock_dir/owner"
    if [[ -f "$owner" ]] && [[ "$(<"$owner")" == "$$" ]]; then
      if ! rm -f -- "$owner" || ! rmdir -- "$lock_dir"; then
        echo "ERROR: could not release consumer transaction lock $lock_dir" >&2
        failures=1
      fi
    else
      echo "ERROR: consumer transaction lock ownership changed at $lock_dir" >&2
      failures=1
    fi
  done
  LOCKS_ACTIVE=0
  return "$failures"
}

acquire_consumer_locks() {
  local index lock_dir
  LOCKS_ACTIVE=1
  for ((index = 0; index < ${#CONSUMER_GIT_DIRS[@]}; index++)); do
    lock_dir="${CONSUMER_GIT_DIRS[$index]}/ncp-repin.lock"
    if ! mkdir -- "$lock_dir"; then
      echo "ERROR: ${CONSUMER_NAMES[$index]} is already locked for an NCP re-pin ($lock_dir)" >&2
      return 1
    fi
    if ! printf '%s\n' "$$" > "$lock_dir/owner"; then
      echo "ERROR: could not record ownership of consumer transaction lock $lock_dir" >&2
      rm -f -- "$lock_dir/owner"
      rmdir -- "$lock_dir" 2>/dev/null || true
      return 1
    fi
    LOCK_DIRS+=("$lock_dir")
  done
}

# Syntax-aware in-place edits use the same parser as the read-only checker. Each
# candidate is semantically validated before its atomic replacement.
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
repin_package_json() {
  python3 "$PIN_GUARD" rewrite-npm "$1" --tag "$TAG"
}

collect_changed_paths() {
  local consumer_dir="$1" path
  CHANGED_PATHS=()
  while IFS= read -r -d '' path; do
    CHANGED_PATHS+=("$path")
  done < <(git_read -C "$consumer_dir" diff --no-renames --ignore-submodules=none --name-only -z HEAD --)
  while IFS= read -r -d '' path; do
    CHANGED_PATHS+=("$path")
  done < <(git_read -C "$consumer_dir" ls-files --others --exclude-standard -z)
}

rollback_transaction() {
  [[ "$TRANSACTION_ACTIVE" -eq 1 ]] || return 0
  [[ "$ROLLBACK_RUNNING" -eq 0 ]] || return 1
  ROLLBACK_RUNNING=1
  TRANSACTION_ACTIVE=0
  trap '' HUP INT TERM
  local failures=0 consumer_failed index consumer_dir expected_branch expected_head
  local status current_branch current_head
  printf '\nRolling back consumer worktrees...\n' >&2
  for ((index = 0; index < ${#CONSUMER_DIRS[@]}; index++)); do
    [[ "${CONSUMER_TOUCHED[$index]}" -eq 1 ]] || continue
    consumer_dir="${CONSUMER_DIRS[$index]}"
    expected_branch="${CONSUMER_BRANCHES[$index]}"
    expected_head="${CONSUMER_HEADS[$index]}"
    consumer_failed=0
    current_branch="$(git_read -C "$consumer_dir" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    current_head="$(git_read -C "$consumer_dir" rev-parse --verify HEAD 2>/dev/null || true)"
    if [[ "$current_branch" != "$expected_branch" || "$current_head" != "$expected_head" ]]; then
      echo "ERROR: refusing automatic rollback in $consumer_dir because branch or HEAD changed during the transaction" >&2
      failures=1
      consumer_failed=1
    else
      if ! clear_special_index_flags "$consumer_dir" ||
        ! git -c core.hooksPath=/dev/null -C "$consumer_dir" reset --hard -q "$expected_head"; then
        echo "ERROR: could not restore tracked files and index in $consumer_dir" >&2
        failures=1
        consumer_failed=1
      fi
      if ! git -C "$consumer_dir" clean -ffdq; then
        echo "ERROR: could not remove transaction-created Git-visible paths in $consumer_dir" >&2
        failures=1
        consumer_failed=1
      fi
    fi
    if ! status="$(git_read -C "$consumer_dir" status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"; then
      echo "ERROR: could not inspect rollback status in $consumer_dir" >&2
      failures=1
      consumer_failed=1
      status="__UNAVAILABLE__"
    fi
    if ! current_branch="$(git_read -C "$consumer_dir" symbolic-ref --quiet --short HEAD 2>/dev/null)"; then
      current_branch=""
    fi
    if ! current_head="$(git_read -C "$consumer_dir" rev-parse --verify HEAD 2>/dev/null)"; then
      current_head=""
    fi
    if [[ -n "$status" || "$current_branch" != "$expected_branch" || "$current_head" != "$expected_head" ]]; then
      echo "ERROR: rollback verification failed in $consumer_dir" >&2
      failures=1
      consumer_failed=1
    fi
    if ! assert_normal_index "$consumer_dir" "${CONSUMER_NAMES[$index]}"; then
      echo "ERROR: rollback index-state verification failed in $consumer_dir" >&2
      failures=1
      consumer_failed=1
    fi
    if [[ "$consumer_failed" -eq 0 ]]; then
      printf '  . restored %s\n' "${CONSUMER_NAMES[$index]}" >&2
    fi
  done
  ROLLBACK_RUNNING=0
  return "$failures"
}

finish_on_exit() {
  local status="$1"
  if [[ "$status" -ne 0 && "$TRANSACTION_ACTIVE" -eq 1 ]]; then
    if ! rollback_transaction; then
      status=1
    fi
  fi
  if ! release_consumer_locks; then
    status=1
  fi
  trap - EXIT
  exit "$status"
}

assert_transaction_invariants() {
  local index="$1" consumer_dir current_branch current_head
  consumer_dir="${CONSUMER_DIRS[$index]}"
  current_branch="$(git_read -C "$consumer_dir" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  current_head="$(git_read -C "$consumer_dir" rev-parse --verify HEAD 2>/dev/null || true)"
  if [[ "$current_branch" != "${CONSUMER_BRANCHES[$index]}" || "$current_head" != "${CONSUMER_HEADS[$index]}" ]]; then
    warn "consumer command changed branch or HEAD in ${CONSUMER_NAMES[$index]}"
    return 1
  fi
  if ! git_read -C "$consumer_dir" diff --cached --quiet --ignore-submodules=none --; then
    warn "consumer command staged changes in ${CONSUMER_NAMES[$index]}"
    return 1
  fi
  assert_normal_index "$consumer_dir" "${CONSUMER_NAMES[$index]}"
}

assert_pristine_consumer() {
  local index="$1" consumer_dir status
  consumer_dir="${CONSUMER_DIRS[$index]}"
  assert_transaction_invariants "$index" || return 1
  if ! status="$(git_read -C "$consumer_dir" status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"; then
    warn "could not inspect ${CONSUMER_NAMES[$index]} after locking"
    return 1
  fi
  if [[ -n "$status" ]]; then
    warn "${CONSUMER_NAMES[$index]} changed during transaction preflight"
    return 1
  fi
}

print_exact_command() {
  local consumer_dir="$1" action="$2" path
  shift 2
  printf '  git -C %q %s --' "$consumer_dir" "$action"
  for path in "$@"; do
    printf ' %q' "$path"
  done
  printf '\n'
}

echo "Re-pinning all NCP consumers to tag: $TAG"
echo "  base-dir : $BASE_DIR"
echo "  NCP repo : $NCP_ROOT"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "  mode     : dry-run (no writes or consumer commands)"
fi

shopt -s nullglob dotglob
descriptors=("$BASE_DIR"/*/.ncp-consumer)
shopt -u nullglob dotglob
if [[ "${#descriptors[@]}" -eq 0 ]]; then
  echo "No consumers found under $BASE_DIR (no */.ncp-consumer descriptors). Nothing to do." >&2
  echo "A consumer registers by committing a .ncp-consumer file to its repo root (see INTEGRATING.md)." >&2
  exit 1
fi

# Validate the complete descriptor fleet before inspecting or mutating repositories.
if ! python3 "$PIN_GUARD" preflight "$BASE_DIR"; then
  echo "No consumers were modified because descriptor validation failed." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: required tool 'git' is unavailable." >&2
  exit 1
fi
if [[ ! -x "$SCRIPT_DIR/check-consumer-pins.sh" ]]; then
  echo "ERROR: required post-repin checker is missing or not executable." >&2
  exit 1
fi

# Every discovered consumer must be the clean root of a main-branch Git worktree.
# Descriptors and declared pin/check targets must be tracked so every relevant
# mutation is visible in the exact-path report and recoverable from recorded HEAD.
# Collect every error so the entire fleet is preflighted before returning.
git_preflight_failed=0
for desc in "${descriptors[@]}"; do
  consumer_dir="$(cd "$(dirname "$desc")" && pwd -P)"
  consumer_name="$(basename "$consumer_dir")"
  git_root="$(git_read -C "$consumer_dir" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -z "$git_root" ]]; then
    echo "ERROR: $consumer_name is not a Git worktree" >&2
    git_preflight_failed=1
    continue
  fi
  git_root="$(cd "$git_root" && pwd -P)"
  if [[ "$git_root" != "$consumer_dir" ]]; then
    echo "ERROR: $consumer_name descriptor is not at its Git worktree root" >&2
    git_preflight_failed=1
    continue
  fi
  branch="$(git_read -C "$consumer_dir" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [[ "$branch" != "$REQUIRED_BRANCH" ]]; then
    echo "ERROR: $consumer_name must be on branch '$REQUIRED_BRANCH' (found '${branch:-detached}')" >&2
    git_preflight_failed=1
    continue
  fi
  head="$(git_read -C "$consumer_dir" rev-parse --verify HEAD 2>/dev/null || true)"
  if [[ -z "$head" ]]; then
    echo "ERROR: $consumer_name has no committed HEAD" >&2
    git_preflight_failed=1
    continue
  fi
  worktree_status="$(git_read -C "$consumer_dir" status --porcelain=v1 --untracked-files=all --ignore-submodules=none)"
  if [[ -n "$worktree_status" ]]; then
    echo "ERROR: $consumer_name has staged, unstaged, untracked, or dirty-submodule changes" >&2
    git_preflight_failed=1
    continue
  fi
  if ! assert_normal_index "$consumer_dir" "$consumer_name"; then
    git_preflight_failed=1
    continue
  fi
  git_dir="$(git_read -C "$consumer_dir" rev-parse --absolute-git-dir 2>/dev/null || true)"
  if [[ -z "$git_dir" || ! -d "$git_dir" ]]; then
    echo "ERROR: $consumer_name Git administrative directory is unavailable" >&2
    git_preflight_failed=1
    continue
  fi
  git_dir="$(cd "$git_dir" && pwd -P)"
  tracked_path_failed=0
  if ! git_read -C "$consumer_dir" ls-files --error-unmatch -- .ncp-consumer >/dev/null 2>&1; then
    echo "ERROR: $consumer_name/.ncp-consumer is not tracked at HEAD" >&2
    tracked_path_failed=1
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    IFS=$' \t' read -r -a fields <<< "$line"
    [[ "${#fields[@]}" -ge 2 ]] || continue
    [[ "${fields[0]}" != "repin_cmd" ]] || continue
    if ! git_read -C "$consumer_dir" ls-files --error-unmatch -- "${fields[1]}" >/dev/null 2>&1; then
      echo "ERROR: $consumer_name/${fields[1]} is declared but not tracked at HEAD" >&2
      tracked_path_failed=1
    fi
  done < "$desc"
  if [[ "$tracked_path_failed" -ne 0 ]]; then
    git_preflight_failed=1
    continue
  fi
  CONSUMER_DIRS+=("$consumer_dir")
  CONSUMER_NAMES+=("$consumer_name")
  CONSUMER_HEADS+=("$head")
  CONSUMER_BRANCHES+=("$branch")
  CONSUMER_GIT_DIRS+=("$git_dir")
  CONSUMER_TOUCHED+=(0)
done
if [[ "$git_preflight_failed" -ne 0 ]]; then
  echo "No consumers were modified because Git preflight failed." >&2
  exit 1
fi

# Parse fleet-wide command, tool, and revision requirements before any rewrite.
# A revision placeholder is meaningful only when that same descriptor carries
# immutable revision metadata; another consumer's revision row cannot supply it.
has_revision_consumer=0
needs_cargo=0
needs_bun=0
command_preflight_failed=0
for desc in "${descriptors[@]}"; do
  consumer_name="$(basename "$(dirname "$desc")")"
  repin_cmd=""
  consumer_has_repin_cmd=0
  consumer_revision_pinned=0
  consumer_needs_cargo=0
  consumer_needs_bun=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    IFS=$' \t' read -r -a fields <<< "$line"
    [[ "${#fields[@]}" -ge 2 ]] || continue
    case "${fields[0]}" in
      cargo_tag) consumer_needs_cargo=1 ;;
      cargo_rev) consumer_needs_cargo=1; consumer_revision_pinned=1 ;;
      cargo_lock_rev|mirror_rev) consumer_revision_pinned=1 ;;
      npm_tag) consumer_needs_bun=1 ;;
      repin_cmd)
        consumer_has_repin_cmd=1
        repin_cmd="${line#*repin_cmd}"
        repin_cmd="${repin_cmd#"${repin_cmd%%[![:space:]]*}"}"
        ;;
    esac
  done < "$desc"
  if [[ "$consumer_revision_pinned" -eq 1 ]]; then
    has_revision_consumer=1
  fi
  if [[ "$consumer_has_repin_cmd" -eq 0 ]]; then
    if [[ "$consumer_needs_cargo" -eq 1 ]]; then
      needs_cargo=1
    fi
    if [[ "$consumer_needs_bun" -eq 1 ]]; then
      needs_bun=1
    fi
  fi
  if [[ "$repin_cmd" == *'{REV}'* && "$consumer_revision_pinned" -ne 1 ]]; then
    echo "ERROR: $consumer_name repin_cmd requests {REV}, but its descriptor has no revision-pinned row" >&2
    command_preflight_failed=1
  fi
done
if [[ "$command_preflight_failed" -ne 0 ]]; then
  echo "No consumers were modified because command preflight failed." >&2
  exit 1
fi
if [[ "$has_revision_consumer" -eq 1 ]]; then
  if ! command -v perl >/dev/null 2>&1; then
    echo "ERROR: perl is required to update revision-pinned descriptors." >&2
    exit 1
  fi
  if ! TAG_REV="$(git_read -C "$NCP_ROOT" rev-parse --verify "refs/tags/${TAG}^{commit}" 2>/dev/null)"; then
    echo "ERROR: revision-pinned consumers require local tag '$TAG', but it is unavailable." >&2
    exit 2
  fi
fi
if [[ "$needs_cargo" -eq 1 ]] && ! command -v cargo >/dev/null 2>&1; then
  echo "ERROR: cargo is required by at least one standard consumer re-pin." >&2
  exit 1
fi
if [[ "$needs_bun" -eq 1 && -z "$BUN_BIN" ]]; then
  echo "ERROR: bun is required by at least one standard consumer re-pin." >&2
  exit 1
fi

# A dry run stops after the same complete preflight and prints exact declared
# paths plus the commands that a mutating run would execute.
if [[ "$DRY_RUN" -eq 1 ]]; then
  for ((consumer_index = 0; consumer_index < ${#descriptors[@]}; consumer_index++)); do
    desc="${descriptors[$consumer_index]}"
    consumer_name="${CONSUMER_NAMES[$consumer_index]}"
    hdr "$consumer_name"
    cargo_tomls=()
    cargo_rev_tomls=()
    cargo_locks=()
    npm_jsons=()
    npm_locks=()
    declared_paths=()
    repin_cmd=""
    consumer_revision_pinned=0
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%%#*}"
      IFS=$' \t' read -r -a fields <<< "$line"
      [[ "${#fields[@]}" -ge 2 ]] || continue
      case "${fields[0]}" in
        cargo_tag) cargo_tomls+=("${fields[1]}"); declared_paths+=("${fields[1]}") ;;
        cargo_rev) cargo_rev_tomls+=("${fields[1]}"); declared_paths+=("${fields[1]}"); consumer_revision_pinned=1 ;;
        cargo_lock|cargo_lock_rev)
          cargo_locks+=("${fields[1]}")
          declared_paths+=("${fields[1]}")
          if [[ "${fields[0]}" == "cargo_lock_rev" ]]; then
            consumer_revision_pinned=1
          fi
          ;;
        npm_tag) npm_jsons+=("${fields[1]}"); declared_paths+=("${fields[1]}") ;;
        npm_lock) npm_locks+=("${fields[1]}"); declared_paths+=("${fields[1]}") ;;
        mirror_ref|mirror_rev|python_wire)
          declared_paths+=("${fields[1]}")
          if [[ "${fields[0]}" == "mirror_rev" ]]; then
            consumer_revision_pinned=1
          fi
          ;;
        repin_cmd)
          repin_cmd="${line#*repin_cmd}"
          repin_cmd="${repin_cmd#"${repin_cmd%%[![:space:]]*}"}"
          ;;
      esac
    done < "$desc"
    if [[ -n "$repin_cmd" ]]; then
      cmd="${repin_cmd//\{TAG\}/$TAG}"
      cmd="${cmd//\{REV\}/$TAG_REV}"
      note "would run consumer repin_cmd: $cmd"
    else
      for rel in ${cargo_tomls[@]+"${cargo_tomls[@]}"}; do
        note "would rewrite $rel for tag $TAG"
        note "would run cargo update with manifest $rel"
      done
      for rel in ${cargo_rev_tomls[@]+"${cargo_rev_tomls[@]}"}; do
        note "would rewrite $rel for $TAG ($TAG_REV)"
        note "would run cargo update with manifest $rel"
      done
      for rel in ${npm_jsons[@]+"${npm_jsons[@]}"}; do
        note "would rewrite $rel for tag $TAG"
        note "would run bun install --lockfile-only --ignore-scripts in $consumer_name/$(dirname "$rel")"
      done
    fi
    if [[ "$consumer_revision_pinned" -eq 1 ]] &&
      { [[ -n "$repin_cmd" ]] || [[ "${#cargo_rev_tomls[@]}" -gt 0 ]]; }; then
      note "would rewrite .ncp-consumer revision metadata for $TAG ($TAG_REV)"
      declared_paths+=(".ncp-consumer")
    fi
    for rel in ${declared_paths[@]+"${declared_paths[@]}"}; do
      note "planned path: $consumer_name/$rel"
    done
  done
  echo ""
  echo "Dry-run complete. No consumer commands, writes, staging, commits, or pushes were performed."
  exit 0
fi

trap 'finish_on_exit $?' EXIT
trap 'exit 130' HUP INT TERM
if ! acquire_consumer_locks; then
  exit 1
fi
for ((consumer_index = 0; consumer_index < ${#CONSUMER_DIRS[@]}; consumer_index++)); do
  if ! assert_pristine_consumer "$consumer_index"; then
    echo "No consumers were modified because a repository changed while locks were acquired." >&2
    exit 1
  fi
done
TRANSACTION_ACTIVE=1

for ((consumer_index = 0; consumer_index < ${#descriptors[@]}; consumer_index++)); do
  desc="${descriptors[$consumer_index]}"
  consumer_dir="${CONSUMER_DIRS[$consumer_index]}"
  consumer_name="${CONSUMER_NAMES[$consumer_index]}"
  hdr "$consumer_name"

  if ! assert_pristine_consumer "$consumer_index"; then
    warn "$consumer_name changed before its re-pin began"
    exit 1
  fi
  CONSUMER_TOUCHED[consumer_index]=1

  cargo_tomls=()
  cargo_rev_tomls=()
  npm_jsons=()
  repin_cmd=""
  consumer_revision_pinned=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    IFS=$' \t' read -r -a fields <<< "$line"
    [[ "${#fields[@]}" -ge 2 ]] || continue
    case "${fields[0]}" in
      cargo_tag) cargo_tomls+=("${fields[1]}") ;;
      cargo_rev) cargo_rev_tomls+=("${fields[1]}"); consumer_revision_pinned=1 ;;
      cargo_lock_rev|mirror_rev) consumer_revision_pinned=1 ;;
      npm_tag) npm_jsons+=("${fields[1]}") ;;
      repin_cmd)
        repin_cmd="${line#*repin_cmd}"
        repin_cmd="${repin_cmd#"${repin_cmd%%[![:space:]]*}"}"
        ;;
    esac
  done < "$desc"

  if [[ -n "$repin_cmd" ]]; then
    if [[ "$repin_cmd" == *'{REV}'* ]] &&
      { [[ "$consumer_revision_pinned" -ne 1 ]] || [[ -z "$TAG_REV" ]]; }; then
      warn "repin_cmd requests {REV}, but the descriptor has no revision-pinned row"
      exit 1
    fi
    cmd="${repin_cmd//\{TAG\}/$TAG}"
    cmd="${cmd//\{REV\}/$TAG_REV}"
    note "running consumer repin_cmd: $cmd"
    if ! (cd "$consumer_dir" && bash -c "$cmd"); then
      warn "repin_cmd failed in $consumer_name"
      exit 1
    fi
    if [[ "$consumer_revision_pinned" -eq 1 ]]; then
      update_revision_descriptor "$desc"
      note "updated revision-pin descriptor metadata -> $TAG ($TAG_REV)"
    fi
  else
    for rel in ${cargo_tomls[@]+"${cargo_tomls[@]}"}; do
      f="$consumer_dir/$rel"
      repin_cargo_manifest "$f"
      note "rewrote ncp-core/ncp-zenoh tag/version -> $TAG in $rel"
      note "refreshing lockfile with cargo update for $rel ..."
      # ncp-zenoh always resolves ncp-core from the same NCP source, while a
      # core-only consumer has no ncp-zenoh package ID. Updating the shared core
      # package refreshes either graph without naming an absent optional package.
      if ! (cd "$consumer_dir" && cargo update -p ncp-core --manifest-path "$rel"); then
        warn "cargo update failed in $consumer_name ($rel)"
        exit 1
      fi
    done

    repinned_revision=0
    for rel in ${cargo_rev_tomls[@]+"${cargo_rev_tomls[@]}"}; do
      f="$consumer_dir/$rel"
      repin_cargo_rev_manifest "$f"
      repinned_revision=1
      note "rewrote ncp-core/ncp-zenoh rev/version -> $TAG ($TAG_REV) in $rel"
      note "refreshing lockfile with cargo update for $rel ..."
      if ! (cd "$consumer_dir" && cargo update -p ncp-core --manifest-path "$rel"); then
        warn "cargo update failed in $consumer_name ($rel)"
        exit 1
      fi
    done
    if [[ "$repinned_revision" -eq 1 ]]; then
      update_revision_descriptor "$desc"
      note "updated revision-pin descriptor metadata -> $TAG ($TAG_REV)"
    fi

    for rel in ${npm_jsons[@]+"${npm_jsons[@]}"}; do
      f="$consumer_dir/$rel"
      repin_package_json "$f"
      note "rewrote @scope/ncp pin -> #$TAG in $rel"
      note "regenerating the bun lockfile without installing packages or running scripts ..."
      npm_dir="$(dirname "$rel")"
      if ! (cd "$consumer_dir/$npm_dir" && "$BUN_BIN" install --lockfile-only --ignore-scripts); then
        warn "bun install failed in $consumer_name"
        exit 1
      fi
    done
  fi

  assert_transaction_invariants "$consumer_index"
  collect_changed_paths "$consumer_dir"
  if [[ "${#CHANGED_PATHS[@]}" -gt 0 ]]; then
    add_summary "$consumer_name" "REPINNED" "$(printf '%s ' "${CHANGED_PATHS[@]}")-> $TAG"
  else
    add_summary "$consumer_name" "SKIPPED" "already pinned or no re-pinnable target changed"
  fi
done

hdr "Post-repin verification"
if ! "$SCRIPT_DIR/check-consumer-pins.sh" "$TAG" "$BASE_DIR"; then
  warn "consumer pin verification failed after re-pin"
  exit 1
fi
for ((consumer_index = 0; consumer_index < ${#CONSUMER_DIRS[@]}; consumer_index++)); do
  assert_transaction_invariants "$consumer_index"
done
TRANSACTION_ACTIVE=0

hdr "Summary — re-pin to $TAG"
printf '\n%-22s %-9s %s\n' "REPO" "STATUS" "DETAIL"
printf -- '%-22s %-9s %s\n' "----" "------" "------"
for row in "${SUMMARY[@]}"; do
  IFS=$'\t' read -r repo status detail <<< "$row"
  printf '%-22s %-9s %s\n' "$repo" "$status" "$detail"
done

echo ""
echo "No commits, pushes, or staging were performed. Files and lockfiles were edited in place."
printed_review=0
for ((consumer_index = 0; consumer_index < ${#CONSUMER_DIRS[@]}; consumer_index++)); do
  consumer_dir="${CONSUMER_DIRS[$consumer_index]}"
  consumer_name="${CONSUMER_NAMES[$consumer_index]}"
  collect_changed_paths "$consumer_dir"
  [[ "${#CHANGED_PATHS[@]}" -gt 0 ]] || continue
  if [[ "$printed_review" -eq 0 ]]; then
    echo ""
    echo "Suggested exact-path review / commit commands:"
    echo ""
    printed_review=1
  fi
  printf '# %s\n' "$consumer_name"
  print_exact_command "$consumer_dir" "status --short" "${CHANGED_PATHS[@]}"
  print_exact_command "$consumer_dir" "diff" "${CHANGED_PATHS[@]}"
  print_exact_command "$consumer_dir" "add" "${CHANGED_PATHS[@]}"
  printf '  git -C %q commit -m %q\n\n' "$consumer_dir" "chore: re-pin NCP to $TAG"
done
if [[ "$printed_review" -eq 0 ]]; then
  echo ""
  echo "Nothing changed; all discovered consumers already matched the requested pin."
fi
