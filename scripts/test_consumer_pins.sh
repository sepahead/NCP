#!/usr/bin/env bash
# Focused regression tests for tag- and immutable-revision consumer descriptors.
# Fixture bodies are single-quoted so their variables expand only when executed.
# shellcheck disable=SC2016
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKER="$SCRIPT_DIR/check-consumer-pins.sh"
REPINNER="$SCRIPT_DIR/repin-ncp.sh"
REV="2f5bd586d4bb20c90362bb6f5698b7f64057ba4e"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

resolved_release="$(git -C "$SCRIPT_DIR/.." rev-parse --verify 'refs/tags/v0.8.0^{commit}' 2>/dev/null || true)"
if [[ "$resolved_release" != "$REV" ]]; then
  echo "ERROR: consumer pin regressions require local tag v0.8.0 at $REV; got ${resolved_release:-<missing>}" >&2
  echo "       CI checkout must fetch tags (actions/checkout fetch-depth: 0)." >&2
  exit 1
fi

# Deterministic cargo stand-in: optionally fail, or refresh the lockfile with
# the source supplied by the test. This keeps the regression suite offline.
mkdir -p "$tmp/fake-bin"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  '[ "${FAKE_CARGO_FAIL:-0}" = 1 ] && exit 1' \
  'manifest=' \
  'while [ "$#" -gt 0 ]; do' \
  '  if [ "$1" = "ncp-zenoh" ] && [ "${FAKE_CARGO_REJECT_ZENOH:-0}" = 1 ]; then exit 1; fi' \
  '  if [ "$1" = "--manifest-path" ]; then shift; manifest=$1; fi' \
  '  shift' \
  'done' \
  'if [ -n "${FAKE_CARGO_LOCK_LINE:-}" ]; then' \
  '  printf "%s\n" "$FAKE_CARGO_LOCK_LINE" > "$(dirname "$manifest")/Cargo.lock"' \
  'fi' > "$tmp/fake-bin/cargo"
chmod +x "$tmp/fake-bin/cargo"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'if [ -n "${FAKE_BUN_ARGS_FILE:-}" ]; then' \
  '  printf "%s\n" "$@" > "$FAKE_BUN_ARGS_FILE"' \
  'fi' \
  'if [ -n "${FAKE_BUN_CWD_FILE:-}" ]; then' \
  '  pwd -P > "$FAKE_BUN_CWD_FILE"' \
  'fi' > "$tmp/fake-bin/bun"
chmod +x "$tmp/fake-bin/bun"
# Keep the Python 3.11+ interpreter that provides stdlib tomllib while replacing
# cargo. macOS /usr/bin/python3 may be older than the release-gate interpreter.
PYTHON_DIR="$(dirname "$(command -v python3)")"
FAKE_PATH="$tmp/fake-bin:$PYTHON_DIR:/usr/bin:/bin"

init_git_repo() {
  local repo="$1" physical existing_root
  physical="$(cd "$repo" && pwd -P)"
  existing_root="$(git -C "$physical" rev-parse --show-toplevel 2>/dev/null || true)"
  if [[ -n "$existing_root" ]] &&
    [[ "$(cd "$existing_root" && pwd -P)" == "$physical" ]]; then
    return
  fi
  git -C "$physical" init -q
  git -C "$physical" symbolic-ref HEAD refs/heads/main
  git -C "$physical" config user.name "NCP Test"
  git -C "$physical" config user.email "ncp-test@example.invalid"
  git -C "$physical" add -- .
  git -C "$physical" commit -qm "test fixture"
}

prepare_repin_base() {
  local base="$1" descriptor repo
  shopt -s nullglob dotglob
  for descriptor in "$base"/*/.ncp-consumer; do
    repo="$(dirname "$descriptor")"
    [[ -L "$repo" ]] || init_git_repo "$repo"
  done
  shopt -u nullglob dotglob
}

mkdir -p "$tmp/tag-consumer" "$tmp/rev-consumer" "$tmp/python-consumer" \
  "$tmp/mirror-rev-consumer/ncp"
printf '%s\n' 'cargo_tag Cargo.toml' 'cargo_lock Cargo.lock' > "$tmp/tag-consumer/.ncp-consumer"
printf '%s\n' 'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v0.8.0" }' > "$tmp/tag-consumer/Cargo.toml"
printf '%s\n' "source = \"git+https://github.com/sepahead/NCP?tag=v0.8.0#$REV\"" > "$tmp/tag-consumer/Cargo.lock"

printf '%s\n' \
  "cargo_rev Cargo.toml v0.8.0 $REV" \
  "cargo_lock_rev Cargo.lock v0.8.0 $REV" > "$tmp/rev-consumer/.ncp-consumer"
printf '%s\n' \
  "ncp-core = { version = \"=0.8.0\", git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
  "ncp-zenoh = { version = \"0.8.0\", git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" > "$tmp/rev-consumer/Cargo.toml"
printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  '[[package]]' 'name = "ncp-zenoh"' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" > "$tmp/rev-consumer/Cargo.lock"

printf '%s\n' 'python_wire protocol.py v0.8.0' > "$tmp/python-consumer/.ncp-consumer"
printf '%s\n' 'NCP_VERSION = "0.8"' > "$tmp/python-consumer/protocol.py"

printf '%s\n' "mirror_rev ncp/.mirror-rev v0.8.0 $REV" > "$tmp/mirror-rev-consumer/.ncp-consumer"
printf '%s\n' "$REV" > "$tmp/mirror-rev-consumer/ncp/.mirror-rev"

pin_report="$("$CHECKER" v0.8.0 "$tmp")"
if ! grep -Fq \
  "mirror-rev-consumer/ncp/.mirror-rev immutable revision = $REV (consumer-declared release v0.8.0)" \
  <<<"$pin_report"; then
  echo "ERROR: immutable mirror pin report omitted its declared release/revision" >&2
  exit 1
fi

printf '%s\n' '0000000000000000000000000000000000000000' > "$tmp/mirror-rev-consumer/ncp/.mirror-rev"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a tampered immutable mirror revision passed its descriptor" >&2
  exit 1
fi
printf '%s \n' "$REV" > "$tmp/mirror-rev-consumer/ncp/.mirror-rev"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a mirror revision with trailing metadata/whitespace was accepted" >&2
  exit 1
fi
printf '%s\n' "$REV" > "$tmp/mirror-rev-consumer/ncp/.mirror-rev"

# An offline mirror check does not require the consumer-declared candidate label
# to exist as a local tag. This is the immutable pre-tag handoff use case; the
# successful check proves local bytes/metadata agreement, not release status.
UNRELEASED_TAG='v999.0.0-rc.1'
UNRELEASED_REV='1111111111111111111111111111111111111111'
mkdir -p "$tmp/untagged-mirror-base/untagged-mirror/ncp"
printf '%s\n' \
  "mirror_rev ncp/.mirror-rev $UNRELEASED_TAG $UNRELEASED_REV" \
  > "$tmp/untagged-mirror-base/untagged-mirror/.ncp-consumer"
printf '%s\n' "$UNRELEASED_REV" > "$tmp/untagged-mirror-base/untagged-mirror/ncp/.mirror-rev"
"$CHECKER" "$UNRELEASED_TAG" "$tmp/untagged-mirror-base" >/dev/null
prepare_repin_base "$tmp/untagged-mirror-base"
if PATH="$FAKE_PATH" "$REPINNER" "$UNRELEASED_TAG" "$tmp/untagged-mirror-base" >/dev/null 2>&1; then
  echo "ERROR: revision repin accepted an unavailable local release tag" >&2
  exit 1
fi

printf '%s\n' 'NCP_VERSION = "0.7"' > "$tmp/python-consumer/protocol.py"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a stale Python runtime wire passed its declared release" >&2
  exit 1
fi
printf '%s\n' 'NCP_VERSION = "0.8"' > "$tmp/python-consumer/protocol.py"

printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  '[[package]]' 'name = "ncp-zenoh"' \
  'source = "git+https://github.com/sepahead/NCP?rev=0000000000000000000000000000000000000000#0000000000000000000000000000000000000000"' > "$tmp/rev-consumer/Cargo.lock"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a mismatched second lock source was accepted" >&2
  exit 1
fi

printf '%s\n' \
  "ncp-core = { git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
  'ncp-zenoh = { git = "https://github.com/sepahead/NCP", rev = "0000000000000000000000000000000000000000" }' > "$tmp/rev-consumer/Cargo.toml"
printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  '[[package]]' 'name = "ncp-zenoh"' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" > "$tmp/rev-consumer/Cargo.lock"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a mismatched second manifest dependency was accepted" >&2
  exit 1
fi

printf '%s\n' \
  "ncp-core = { git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
  'ncp-zenoh = { git = "https://github.com/sepahead/NCP", tag = "v0.8.0" }' > "$tmp/rev-consumer/Cargo.toml"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a non-revision second manifest dependency was accepted" >&2
  exit 1
fi

for invalid_version in '=0.7.0' '^0.8.0' '~0.8.0' '>=0.8.0' '0.8.*'; do
  printf '%s\n' \
    "ncp-core = { version = \"=0.8.0\", git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
    "ncp-zenoh = { version = \"$invalid_version\", git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" > "$tmp/rev-consumer/Cargo.toml"
  if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
    echo "ERROR: incompatible/ranged Cargo version $invalid_version was accepted" >&2
    exit 1
  fi
done

# A tag-only fleet must not require the target tag in the local NCP checkout.
mkdir -p "$tmp/tag-only-base/tag-only"
printf '%s\n' 'cargo_tag Cargo.toml' > "$tmp/tag-only-base/tag-only/.ncp-consumer"
printf '%s\n' 'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v0.8.0" }' > "$tmp/tag-only-base/tag-only/Cargo.toml"
prepare_repin_base "$tmp/tag-only-base"
PATH="$FAKE_PATH" "$REPINNER" v9.9.9 "$tmp/tag-only-base" >/dev/null 2>&1
"$CHECKER" v9.9.9 "$tmp/tag-only-base" >/dev/null

# Tag-mode Cargo descriptors cover every NCP dependency and lock source. A
# first-match implementation would accept these mismatched second entries.
mkdir -p "$tmp/tag-multi-base/tag-multi"
printf '%s\n' 'cargo_tag Cargo.toml' 'cargo_lock Cargo.lock' \
  > "$tmp/tag-multi-base/tag-multi/.ncp-consumer"
printf '%s\n' \
  'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  'ncp-zenoh = { git = "https://github.com/sepahead/NCP", tag = "v1.1.0" }' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.toml"
printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  '[[package]]' 'name = "ncp-zenoh"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.lock"
if "$CHECKER" v1.0.0 "$tmp/tag-multi-base" >/dev/null 2>&1; then
  echo "ERROR: a mismatched second tag-mode manifest dependency was accepted" >&2
  exit 1
fi
printf '%s\n' \
  'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  'ncp-zenoh = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.toml"
printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  '[[package]]' 'name = "ncp-zenoh"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.1.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.lock"
if "$CHECKER" v1.0.0 "$tmp/tag-multi-base" >/dev/null 2>&1; then
  echo "ERROR: a mismatched second tag-mode lock source was accepted" >&2
  exit 1
fi
printf '%s\n' \
  'ncp-core = { version = "=1.0.0", git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  'ncp-zenoh = { version = "0.8.0", git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.toml"
printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  '[[package]]' 'name = "ncp-zenoh"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.lock"
if "$CHECKER" v1.0.0 "$tmp/tag-multi-base" >/dev/null 2>&1; then
  echo "ERROR: a tag-mode Cargo version inconsistent with its release label was accepted" >&2
  exit 1
fi
printf '%s\n' \
  'ncp-core = { version = "=1.0.0", git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  'ncp-zenoh = { version = "1.0.0", git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.toml"
"$CHECKER" v1.0.0 "$tmp/tag-multi-base" >/dev/null

printf '%s\n' \
  '[[package]]' 'name = "ncp-core"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  '[[package]]' 'name = "ncp-zenoh"' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.lock"
if "$CHECKER" v1.0.0 "$tmp/tag-multi-base" >/dev/null 2>&1; then
  echo "ERROR: contradictory resolved commits passed one tag-mode lock descriptor" >&2
  exit 1
fi
printf '%s\n' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#abc"' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.lock"
if "$CHECKER" v1.0.0 "$tmp/tag-multi-base" >/dev/null 2>&1; then
  echo "ERROR: an abbreviated tag-mode lock revision was accepted" >&2
  exit 1
fi
printf '%s\n' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  > "$tmp/tag-multi-base/tag-multi/Cargo.lock"

# Agreement uses the stable major after 1.0, but the exact minor before 1.0.
mkdir -p "$tmp/agreement-base/consumer-a" "$tmp/agreement-base/consumer-b"
printf '%s\n' 'mirror_ref .mirror-ref' > "$tmp/agreement-base/consumer-a/.ncp-consumer"
printf '%s\n' 'mirror_ref .mirror-ref' > "$tmp/agreement-base/consumer-b/.ncp-consumer"
printf '%s\n' 'v1.0.0' > "$tmp/agreement-base/consumer-a/.mirror-ref"
printf '%s\n' 'v1.1.0' > "$tmp/agreement-base/consumer-b/.mirror-ref"
"$CHECKER" "" "$tmp/agreement-base" >/dev/null
printf '%s\n' 'v2.0.0' > "$tmp/agreement-base/consumer-b/.mirror-ref"
if "$CHECKER" "" "$tmp/agreement-base" >/dev/null 2>&1; then
  echo "ERROR: different stable majors were accepted as one wire line" >&2
  exit 1
fi
printf '%s\n' 'v0.8.0' > "$tmp/agreement-base/consumer-a/.mirror-ref"
printf '%s\n' 'v0.9.0' > "$tmp/agreement-base/consumer-b/.mirror-ref"
if "$CHECKER" "" "$tmp/agreement-base" >/dev/null 2>&1; then
  echo "ERROR: different pre-1.0 minors were accepted as one wire line" >&2
  exit 1
fi
printf '%s\n' 'v0.8.7' > "$tmp/agreement-base/consumer-b/.mirror-ref"
"$CHECKER" "" "$tmp/agreement-base" >/dev/null

# Descriptors fail closed before custom commands run when they contain no pin row,
# malformed/unknown directives, or noncanonical release labels.
mkdir -p "$tmp/invalid-desc-base/only-command/scripts"
printf '%s\n' 'repin_cmd scripts/run.sh {TAG}' \
  > "$tmp/invalid-desc-base/only-command/.ncp-consumer"
printf '%s\n' '#!/bin/sh' 'touch command-ran' \
  > "$tmp/invalid-desc-base/only-command/scripts/run.sh"
chmod +x "$tmp/invalid-desc-base/only-command/scripts/run.sh"
prepare_repin_base "$tmp/invalid-desc-base"
if "$CHECKER" v1.0.0 "$tmp/invalid-desc-base" >/dev/null 2>&1; then
  echo "ERROR: a descriptor with no pin-bearing row passed the checker" >&2
  exit 1
fi
if PATH="$FAKE_PATH" "$REPINNER" v1.0.0 "$tmp/invalid-desc-base" >/dev/null 2>&1; then
  echo "ERROR: the repinner accepted a descriptor with no pin-bearing row" >&2
  exit 1
fi
if [[ -e "$tmp/invalid-desc-base/only-command/command-ran" ]]; then
  echo "ERROR: descriptor validation happened after the custom command ran" >&2
  exit 1
fi

mkdir -p "$tmp/invalid-directive-base/typo"
printf '%s\n' 'mirror_ref .mirror-ref' 'miror_ref .mirror-ref' \
  > "$tmp/invalid-directive-base/typo/.ncp-consumer"
printf '%s\n' 'v1.0.0' > "$tmp/invalid-directive-base/typo/.mirror-ref"
if "$CHECKER" v1.0.0 "$tmp/invalid-directive-base" >/dev/null 2>&1; then
  echo "ERROR: an unsupported descriptor directive was ignored" >&2
  exit 1
fi
printf '%s\n' 'mirror_ref .mirror-ref' > "$tmp/invalid-directive-base/typo/.ncp-consumer"
printf '%s\n' 'v01.0.0' > "$tmp/invalid-directive-base/typo/.mirror-ref"
if "$CHECKER" v01.0.0 "$tmp/invalid-directive-base" >/dev/null 2>&1; then
  echo "ERROR: a noncanonical release label was accepted" >&2
  exit 1
fi

# Every directive has an exact shape. Checker-only rows cannot omit their
# release metadata or smuggle extra operands ahead of a custom mutation.
mkdir -p "$tmp/arity-base/missing-python-tag" "$tmp/arity-base/extra-mirror"
printf '%s\n' \
  'python_wire protocol.py' \
  'repin_cmd touch MUTATED' > "$tmp/arity-base/missing-python-tag/.ncp-consumer"
printf '%s\n' 'NCP_VERSION = "1.0"' > "$tmp/arity-base/missing-python-tag/protocol.py"
printf '%s\n' 'mirror_ref .mirror-ref unexpected' \
  > "$tmp/arity-base/extra-mirror/.ncp-consumer"
printf '%s\n' 'v1.0.0' > "$tmp/arity-base/extra-mirror/.mirror-ref"
prepare_repin_base "$tmp/arity-base"
if "$CHECKER" v1.0.0 "$tmp/arity-base" >/dev/null 2>&1; then
  echo "ERROR: malformed descriptor arity passed the checker" >&2
  exit 1
fi
if PATH="$FAKE_PATH" "$REPINNER" v1.0.0 "$tmp/arity-base" >/dev/null 2>&1; then
  echo "ERROR: malformed descriptor arity passed repinner preflight" >&2
  exit 1
fi
if [[ -e "$tmp/arity-base/missing-python-tag/MUTATED" ]]; then
  echo "ERROR: a custom command ran before exact descriptor-shape validation" >&2
  exit 1
fi

# All direct npm NCP sources are covered even when an alias uses an arbitrary
# key; every Cargo alias/package and Python assignment is covered as well.
mkdir -p "$tmp/alias-base/npm-alias" "$tmp/alias-base/cargo-alias" \
  "$tmp/alias-base/python-duplicate"
printf '%s\n' 'npm_tag package.json' > "$tmp/alias-base/npm-alias/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"arbitrary-ncp-alias":"github:sepahead/NCP#v1.0.0","ncp-shadow":"github:sepahead/NCP#v1.1.0"}}' \
  > "$tmp/alias-base/npm-alias/package.json"
printf '%s\n' 'cargo_tag Cargo.toml' > "$tmp/alias-base/cargo-alias/.ncp-consumer"
printf '%s\n' \
  'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  'shadow = { package = "ncp-zenoh", git = "https://github.com/evil/NCP", tag = "v1.0.0" }' \
  > "$tmp/alias-base/cargo-alias/Cargo.toml"
printf '%s\n' 'python_wire protocol.py v1.0.0' \
  > "$tmp/alias-base/python-duplicate/.ncp-consumer"
printf '%s\n' 'NCP_VERSION = "1.0"' 'NCP_VERSION = "1.1"' \
  > "$tmp/alias-base/python-duplicate/protocol.py"
prepare_repin_base "$tmp/alias-base"
if "$CHECKER" v1.0.0 "$tmp/alias-base" >/dev/null 2>&1; then
  echo "ERROR: an aliased npm/Cargo source or duplicate Python wire escaped coverage" >&2
  exit 1
fi
before_alias="$(shasum -a 256 "$tmp/alias-base/npm-alias/package.json" "$tmp/alias-base/cargo-alias/Cargo.toml" | shasum -a 256)"
if PATH="$FAKE_PATH" "$REPINNER" v1.0.0 "$tmp/alias-base" >/dev/null 2>&1; then
  echo "ERROR: a noncanonical aliased NCP origin passed repinner preflight" >&2
  exit 1
fi
after_alias="$(shasum -a 256 "$tmp/alias-base/npm-alias/package.json" "$tmp/alias-base/cargo-alias/Cargo.toml" | shasum -a 256)"
if [[ "$before_alias" != "$after_alias" ]]; then
  echo "ERROR: repinner changed files after an aliased-origin preflight failure" >&2
  exit 1
fi

# SemVer numeric prerelease identifiers forbid leading zeroes. Reject the target
# before descriptor commands can execute, and reject the same labels in pin files.
mkdir -p "$tmp/semver-base/consumer"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd touch MUTATED' \
  > "$tmp/semver-base/consumer/.ncp-consumer"
printf '%s\n' 'v1.0.0' > "$tmp/semver-base/consumer/.mirror-ref"
prepare_repin_base "$tmp/semver-base"
for invalid_tag in v1.0.0-01 v1.0.0-rc.01; do
  printf '%s\n' "$invalid_tag" > "$tmp/semver-base/consumer/.mirror-ref"
  if "$CHECKER" "$invalid_tag" "$tmp/semver-base" >/dev/null 2>&1; then
    echo "ERROR: noncanonical prerelease $invalid_tag passed the checker" >&2
    exit 1
  fi
  if PATH="$FAKE_PATH" "$REPINNER" "$invalid_tag" "$tmp/semver-base" >/dev/null 2>&1; then
    echo "ERROR: noncanonical prerelease $invalid_tag passed the repinner" >&2
    exit 1
  fi
done
if [[ -e "$tmp/semver-base/consumer/MUTATED" ]]; then
  echo "ERROR: invalid target validation happened after a custom command" >&2
  exit 1
fi

# Syntax-aware hostile corpus. Each case is isolated so one rejection cannot mask
# another; repinner rejection must happen before its consumer command or any byte
# change. These are all valid encodings a raw line/value regex can misread.
tree_digest() {
  find "$1" -type f ! -path '*/.git/*' -exec shasum -a 256 {} \; | LC_ALL=C sort | shasum -a 256 | awk '{print $1}'
}
repository_digest() {
  find "$1" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort | shasum -a 256 | awk '{print $1}'
}
assert_hostile_preflight() {
  local base="$1" label="$2" before after
  prepare_repin_base "$base"
  if "$CHECKER" v1.0.0 "$base" >/dev/null 2>&1; then
    echo "ERROR: hostile consumer case passed checker: $label" >&2
    exit 1
  fi
  before="$(tree_digest "$base")"
  if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$base" >/dev/null 2>&1; then
    echo "ERROR: hostile consumer case passed repinner preflight: $label" >&2
    exit 1
  fi
  after="$(tree_digest "$base")"
  if [[ "$before" != "$after" ]] || find "$base" -name MUTATED -print -quit | grep -q .; then
    echo "ERROR: hostile preflight changed consumer bytes or ran a command: $label" >&2
    exit 1
  fi
}

# Discovery is physical: a sibling-shaped symlink must never let the checker or
# repinner escape the requested base and inspect/mutate an outside repository.
mkdir -p "$tmp/symlink-root-base" "$tmp/symlink-root-outside"
printf '%s\n' 'npm_tag package.json' 'repin_cmd touch MUTATED' \
  > "$tmp/symlink-root-outside/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.0.0"}}' \
  > "$tmp/symlink-root-outside/package.json"
init_git_repo "$tmp/symlink-root-outside"
ln -s "$tmp/symlink-root-outside" "$tmp/symlink-root-base/consumer"
if "$CHECKER" v1.0.0 "$tmp/symlink-root-base" >/dev/null 2>&1; then
  echo "ERROR: checker followed a symlink consumer root outside the base" >&2
  exit 1
fi
outside_before="$(tree_digest "$tmp/symlink-root-outside")"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/symlink-root-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted a symlink consumer root outside the base" >&2
  exit 1
fi
if [[ "$outside_before" != "$(tree_digest "$tmp/symlink-root-outside")" ]] || \
  [[ -e "$tmp/symlink-root-outside/MUTATED" ]]; then
  echo "ERROR: symlink-root preflight changed bytes outside the base" >&2
  exit 1
fi

mkdir -p "$tmp/hostile-comment/consumer"
printf '%s\n' 'cargo_tag Cargo.toml' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-comment/consumer/.ncp-consumer"
printf '%s\n' \
  'ncp-core = "1.0.0" # git = "https://github.com/sepahead/NCP", tag = "v1.0.0"' \
  > "$tmp/hostile-comment/consumer/Cargo.toml"
assert_hostile_preflight "$tmp/hostile-comment" "comment-only Cargo source/tag"

mkdir -p "$tmp/hostile-quoted-cargo/consumer"
printf '%s\n' 'cargo_tag Cargo.toml' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-quoted-cargo/consumer/.ncp-consumer"
printf '%s\n' \
  'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  "'shadow' = { package = 'ncp-zenoh', git = 'https://github.com/sepahead/NCP', tag = 'v1.1.0' }" \
  > "$tmp/hostile-quoted-cargo/consumer/Cargo.toml"
assert_hostile_preflight "$tmp/hostile-quoted-cargo" "quoted-key/literal-string Cargo drift"

mkdir -p "$tmp/hostile-selector/consumer"
printf '%s\n' 'cargo_tag Cargo.toml' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-selector/consumer/.ncp-consumer"
printf '%s\n' \
  "ncp-core = { git = \"https://github.com/sepahead/NCP\", tag = \"v1.0.0\", rev = \"$REV\" }" \
  > "$tmp/hostile-selector/consumer/Cargo.toml"
assert_hostile_preflight "$tmp/hostile-selector" "Cargo tag+rev multi-selector"

mkdir -p "$tmp/hostile-lock-selector/consumer"
printf '%s\n' 'cargo_lock Cargo.lock' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-lock-selector/consumer/.ncp-consumer"
printf '%s\n' \
  "source = \"git+https://github.com/sepahead/NCP?tag=v1.0.0&rev=$REV#$REV\"" \
  > "$tmp/hostile-lock-selector/consumer/Cargo.lock"
assert_hostile_preflight "$tmp/hostile-lock-selector" "Cargo.lock ambiguous selector query"

mkdir -p "$tmp/hostile-npm/consumer"
printf '%s\n' 'npm_tag package.json' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-npm/consumer/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.0.0","ssh-alias":"git+ssh://git@github.com/sepahead/NCP.git#v1.1.0","escaped-alias":"github:sepahead/\u004eCP\u0023v1.1.0","encoded-url-alias":"github:sepahead%2f%4e%43%50#v1.1.0"}}' \
  > "$tmp/hostile-npm/consumer/package.json"
assert_hostile_preflight "$tmp/hostile-npm" "alternate/escaped npm aliases"

mkdir -p "$tmp/hostile-mode/consumer"
printf '%s\n' \
  'cargo_tag Cargo.toml' \
  "cargo_lock_rev Cargo.lock v1.0.0 $REV" \
  'repin_cmd touch MUTATED' > "$tmp/hostile-mode/consumer/.ncp-consumer"
printf '%s\n' \
  'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  > "$tmp/hostile-mode/consumer/Cargo.toml"
printf '%s\n' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  > "$tmp/hostile-mode/consumer/Cargo.lock"
assert_hostile_preflight "$tmp/hostile-mode" "tag-manifest/rev-lock mode mix"

# A stable-major fleet may intentionally contain v1.0 and v1.1 consumers, but
# one consumer's own manifest/lock/runtime rows must name one exact release.
mkdir -p "$tmp/hostile-consumer-release/consumer"
printf '%s\n' \
  'cargo_tag Cargo.toml' \
  'npm_tag package.json' \
  'repin_cmd touch MUTATED' > "$tmp/hostile-consumer-release/consumer/.ncp-consumer"
printf '%s\n' \
  'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v1.0.0" }' \
  > "$tmp/hostile-consumer-release/consumer/Cargo.toml"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.1.0"}}' \
  > "$tmp/hostile-consumer-release/consumer/package.json"
if "$CHECKER" "" "$tmp/hostile-consumer-release" >/dev/null 2>&1; then
  echo "ERROR: one consumer passed with inconsistent stable release labels" >&2
  exit 1
fi
assert_hostile_preflight "$tmp/hostile-consumer-release" "per-consumer release disagreement"

ALT_REV='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
mkdir -p "$tmp/hostile-revision/consumer"
printf '%s\n' \
  "cargo_rev Cargo.toml v1.0.0 $REV" \
  "cargo_lock_rev Cargo.lock v1.0.0 $ALT_REV" \
  'repin_cmd touch MUTATED' > "$tmp/hostile-revision/consumer/.ncp-consumer"
printf '%s\n' \
  "ncp-core = { git = \"https://github.com/sepahead/NCP\", rev = \"$REV\", version = \"1.0.0\" }" \
  > "$tmp/hostile-revision/consumer/Cargo.toml"
printf '%s\n' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$ALT_REV#$ALT_REV\"" \
  > "$tmp/hostile-revision/consumer/Cargo.lock"
assert_hostile_preflight "$tmp/hostile-revision" "one release mapped to two revisions"

mkdir -p "$tmp/hostile-fleet-lock/consumer-a" "$tmp/hostile-fleet-lock/consumer-b"
printf '%s\n' 'cargo_lock Cargo.lock' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-fleet-lock/consumer-a/.ncp-consumer"
printf '%s\n' 'cargo_lock Cargo.lock' 'repin_cmd touch MUTATED' \
  > "$tmp/hostile-fleet-lock/consumer-b/.ncp-consumer"
printf '%s\n' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' \
  > "$tmp/hostile-fleet-lock/consumer-a/Cargo.lock"
printf '%s\n' \
  'source = "git+https://github.com/sepahead/NCP?tag=v1.0.0#bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"' \
  > "$tmp/hostile-fleet-lock/consumer-b/Cargo.lock"
assert_hostile_preflight "$tmp/hostile-fleet-lock" "fleet tag-lock commit disagreement"

# tomllib handles comments plus quoted keys/literal strings correctly. Inspection
# accepts the valid form; the generic formatter refuses an exotic lexical rewrite
# before mutation unless that consumer supplies its own repin_cmd.
mkdir -p "$tmp/toml-syntax-base/quoted"
printf '%s\n' 'cargo_tag Cargo.toml' > "$tmp/toml-syntax-base/quoted/.ncp-consumer"
printf '%s\n' \
  "'shadow' = { package = 'ncp-core', git = 'https://github.com/sepahead/NCP', tag = 'v1.0.0', version = '1.0.0' } # tag = 'v9.9.9'" \
  > "$tmp/toml-syntax-base/quoted/Cargo.toml"
prepare_repin_base "$tmp/toml-syntax-base"
"$CHECKER" v1.0.0 "$tmp/toml-syntax-base" >/dev/null
quoted_before="$(tree_digest "$tmp/toml-syntax-base")"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/toml-syntax-base" >/dev/null 2>&1; then
  echo "ERROR: generic repinner claimed an unsupported quoted/literal TOML rewrite" >&2
  exit 1
fi
if [[ "$quoted_before" != "$(tree_digest "$tmp/toml-syntax-base")" ]]; then
  echo "ERROR: unsupported quoted/literal TOML changed before fail-closed rejection" >&2
  exit 1
fi

# bun.lock JSONC is decoded (including escapes) rather than searched as raw text.
mkdir -p "$tmp/bun-jsonc-base/good" "$tmp/bun-jsonc-hostile/bad"
printf '%s\n' 'npm_lock bun.lock' > "$tmp/bun-jsonc-base/good/.ncp-consumer"
printf '%s\n' \
  '{"workspaces":{"":{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.0.0",},},},}' \
  > "$tmp/bun-jsonc-base/good/bun.lock"
"$CHECKER" v1.0.0 "$tmp/bun-jsonc-base" >/dev/null
printf '%s\n' 'npm_lock bun.lock' 'repin_cmd touch MUTATED' \
  > "$tmp/bun-jsonc-hostile/bad/.ncp-consumer"
printf '%s\n' \
  '{"workspaces":{"":{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.0.0","x":"github:sepahead/\u004eCP\u0023v1.1.0",},},},}' \
  > "$tmp/bun-jsonc-hostile/bad/bun.lock"
assert_hostile_preflight "$tmp/bun-jsonc-hostile" "escaped bun.lock alias"

mkdir -p "$tmp/bun-resolution-hostile/bad"
printf '%s\n' 'npm_lock bun.lock' 'repin_cmd touch MUTATED' \
  > "$tmp/bun-resolution-hostile/bad/.ncp-consumer"
printf '%s\n' \
  '{"workspaces":{"":{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.0.0"}}},"packages":{"a":["@sepahead/ncp@github:sepahead/NCP#aaaaaaa"],"b":["@sepahead/ncp@github:sepahead/NCP#bbbbbbb"]}}' \
  > "$tmp/bun-resolution-hostile/bad/bun.lock"
assert_hostile_preflight "$tmp/bun-resolution-hostile" "contradictory bun resolved commits"

mkdir -p "$tmp/npm-duplicate-key-hostile/bad"
printf '%s\n' 'npm_tag package.json' 'repin_cmd touch MUTATED' \
  > "$tmp/npm-duplicate-key-hostile/bad/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v1.0.0","@sepahead/ncp":"github:sepahead/NCP#v1.0.0"}}' \
  > "$tmp/npm-duplicate-key-hostile/bad/package.json"
assert_hostile_preflight "$tmp/npm-duplicate-key-hostile" "duplicate JSON dependency key"

# The npm rewriter replaces decoded string tokens, preserving the rest of the JSON
# bytes even when the canonical source was written with Unicode escapes.
mkdir -p "$tmp/npm-rewrite-base/encoded" "$tmp/no-home"
printf '%s\n' 'npm_tag package.json' > "$tmp/npm-rewrite-base/encoded/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/\u004eCP\u0023v0.8.0"},"kept":"\\u004eCP"}' \
  > "$tmp/npm-rewrite-base/encoded/package.json"
prepare_repin_base "$tmp/npm-rewrite-base"
FAKE_BUN_ARGS_FILE="$tmp/npm-bun-args" HOME="$tmp/no-home" PATH="$FAKE_PATH" \
  "$REPINNER" v9.9.9 "$tmp/npm-rewrite-base" >/dev/null 2>&1
"$CHECKER" v9.9.9 "$tmp/npm-rewrite-base" >/dev/null
if ! grep -Fq '"@sepahead/ncp":"github:sepahead/NCP#v9.9.9"' \
  "$tmp/npm-rewrite-base/encoded/package.json"; then
  echo "ERROR: decoded npm source token was not rewritten canonically" >&2
  exit 1
fi
if ! grep -Fq '"kept":"\\u004eCP"' "$tmp/npm-rewrite-base/encoded/package.json"; then
  echo "ERROR: npm token rewrite changed an unrelated JSON string" >&2
  exit 1
fi
if [[ "$(tr '\n' ' ' < "$tmp/npm-bun-args")" != "install --lockfile-only --ignore-scripts " ]]; then
  echo "ERROR: bun lock refresh installed packages or allowed lifecycle scripts" >&2
  exit 1
fi

# A package descriptor may live below the consumer root. The standard Bun refresh
# must execute beside that package.json instead of mutating an unrelated root lock.
mkdir -p "$tmp/nested-npm-base/consumer/packages/client"
printf '%s\n' 'npm_tag packages/client/package.json' \
  > "$tmp/nested-npm-base/consumer/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v0.8.0"}}' \
  > "$tmp/nested-npm-base/consumer/packages/client/package.json"
prepare_repin_base "$tmp/nested-npm-base"
FAKE_BUN_CWD_FILE="$tmp/nested-npm-cwd" HOME="$tmp/no-home" PATH="$FAKE_PATH" \
  "$REPINNER" v9.9.9 "$tmp/nested-npm-base" >/dev/null 2>&1
nested_npm_dir="$(cd "$tmp/nested-npm-base/consumer/packages/client" && pwd -P)"
if [[ "$(<"$tmp/nested-npm-cwd")" != "$nested_npm_dir" ]]; then
  echo "ERROR: nested npm re-pin refreshed Bun from the consumer root" >&2
  exit 1
fi
"$CHECKER" v9.9.9 "$tmp/nested-npm-base" >/dev/null

# HOME is optional when Bun is available through PATH.
mkdir -p "$tmp/no-home-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/no-home-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/no-home-base/consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'printf "%s\n" "$1" > .mirror-ref' \
  > "$tmp/no-home-base/consumer/scripts/repin.sh"
chmod +x "$tmp/no-home-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/no-home-base"
env -u HOME PATH="$FAKE_PATH" \
  "$REPINNER" v0.8.0 "$tmp/no-home-base" >/dev/null 2>&1
"$CHECKER" v0.8.0 "$tmp/no-home-base" >/dev/null

# A source-looking string outside a dependency table is ambiguous to a lexical
# formatter. The checker may inspect the actual dependency, but generic preflight
# refuses the rewrite before changing either occurrence.
mkdir -p "$tmp/npm-rewrite-ambiguous/consumer"
printf '%s\n' 'npm_tag package.json' \
  > "$tmp/npm-rewrite-ambiguous/consumer/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v0.8.0"},"metadata":{"upstream":"github:sepahead/NCP#v0.8.0"}}' \
  > "$tmp/npm-rewrite-ambiguous/consumer/package.json"
prepare_repin_base "$tmp/npm-rewrite-ambiguous"
"$CHECKER" v0.8.0 "$tmp/npm-rewrite-ambiguous" >/dev/null
ambiguous_before="$(tree_digest "$tmp/npm-rewrite-ambiguous")"
if HOME="$tmp/no-home" PATH="$FAKE_PATH" \
  "$REPINNER" v9.9.9 "$tmp/npm-rewrite-ambiguous" >/dev/null 2>&1; then
  echo "ERROR: generic npm repinner accepted a source-looking metadata string" >&2
  exit 1
fi
if [[ "$ambiguous_before" != "$(tree_digest "$tmp/npm-rewrite-ambiguous")" ]]; then
  echo "ERROR: ambiguous npm preflight changed package bytes" >&2
  exit 1
fi

# Revision re-pins must update the manifest, lockfile, descriptor metadata, and
# an exact trailing release comment to the requested local release tag.
mkdir -p "$tmp/rev-repin-base/rev-repin"
printf '%s\n' \
  'cargo_rev Cargo.toml v0.7.0 0000000000000000000000000000000000000000 # exact release' \
  'cargo_lock_rev Cargo.lock v0.7.0 0000000000000000000000000000000000000000' > "$tmp/rev-repin-base/rev-repin/.ncp-consumer"
printf '%s\n' 'ncp-core = { git = "https://github.com/sepahead/NCP", rev = "0000000000000000000000000000000000000000", version = "=0.7.0" } # v0.7.0' > "$tmp/rev-repin-base/rev-repin/Cargo.toml"
printf '%s\n' 'source = "git+https://github.com/sepahead/NCP?rev=0000000000000000000000000000000000000000#0000000000000000000000000000000000000000"' > "$tmp/rev-repin-base/rev-repin/Cargo.lock"
prepare_repin_base "$tmp/rev-repin-base"
FAKE_CARGO_REJECT_ZENOH=1 \
  FAKE_CARGO_LOCK_LINE="source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/rev-repin-base" >/dev/null 2>&1
"$CHECKER" v0.8.0 "$tmp/rev-repin-base" >/dev/null
if ! grep -q '# v0.8.0$' "$tmp/rev-repin-base/rev-repin/Cargo.toml"; then
  echo "ERROR: the exact trailing release comment was not refreshed" >&2
  exit 1
fi
if ! grep -Fq 'version = "=0.8.0"' "$tmp/rev-repin-base/rev-repin/Cargo.toml"; then
  echo "ERROR: revision repin weakened an exact Cargo version constraint" >&2
  exit 1
fi

# A vendored mirror can use the same immutable tag-to-revision metadata without
# trusting a movable branch. The consumer-owned sync receives both placeholders;
# the generic repinner updates only descriptor metadata and verifies the pin file.
mkdir -p "$tmp/mirror-repin-base/mirror-repin/ncp" "$tmp/mirror-repin-base/mirror-repin/scripts"
printf '%s\n' \
  'mirror_rev ncp/.mirror-rev v0.7.0 0000000000000000000000000000000000000000 # exact release' \
  'repin_cmd scripts/sync.sh {TAG} {REV}' > "$tmp/mirror-repin-base/mirror-repin/.ncp-consumer"
printf '%s\n' '0000000000000000000000000000000000000000' > "$tmp/mirror-repin-base/mirror-repin/ncp/.mirror-rev"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  '[ "$#" -eq 2 ]' \
  'printf "%s\n" "$2" > ncp/.mirror-rev' \
  'printf "%s %s\n" "$1" "$2" > sync-invocation.txt' > "$tmp/mirror-repin-base/mirror-repin/scripts/sync.sh"
chmod +x "$tmp/mirror-repin-base/mirror-repin/scripts/sync.sh"
prepare_repin_base "$tmp/mirror-repin-base"
PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/mirror-repin-base" >/dev/null 2>&1
"$CHECKER" v0.8.0 "$tmp/mirror-repin-base" >/dev/null
if ! grep -Fqx \
  "mirror_rev ncp/.mirror-rev v0.8.0 $REV # exact release" \
  "$tmp/mirror-repin-base/mirror-repin/.ncp-consumer"; then
  echo "ERROR: immutable mirror descriptor metadata was not refreshed" >&2
  exit 1
fi
if ! grep -Fqx "v0.8.0 $REV" "$tmp/mirror-repin-base/mirror-repin/sync-invocation.txt"; then
  echo "ERROR: consumer mirror sync did not receive exact {TAG}/{REV} substitutions" >&2
  exit 1
fi

# A failed lock refresh must make the command fail and restore every tracked byte.
mkdir -p "$tmp/rev-fail-base/rev-fail"
printf '%s\n' \
  'cargo_rev Cargo.toml v0.7.0 0000000000000000000000000000000000000000' \
  'cargo_lock_rev Cargo.lock v0.7.0 0000000000000000000000000000000000000000' > "$tmp/rev-fail-base/rev-fail/.ncp-consumer"
printf '%s\n' 'ncp-core = { version = "0.7.0", git = "https://github.com/sepahead/NCP", rev = "0000000000000000000000000000000000000000" }' > "$tmp/rev-fail-base/rev-fail/Cargo.toml"
printf '%s\n' 'source = "git+https://github.com/sepahead/NCP?rev=0000000000000000000000000000000000000000#0000000000000000000000000000000000000000"' > "$tmp/rev-fail-base/rev-fail/Cargo.lock"
prepare_repin_base "$tmp/rev-fail-base"
rev_fail_before="$(tree_digest "$tmp/rev-fail-base/rev-fail")"
if FAKE_CARGO_FAIL=1 PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/rev-fail-base" >/dev/null 2>&1; then
  echo "ERROR: a failed Cargo lock refresh returned success" >&2
  exit 1
fi
if [[ "$rev_fail_before" != "$(tree_digest "$tmp/rev-fail-base/rev-fail")" ]] ||
  [[ -n "$(git -C "$tmp/rev-fail-base/rev-fail" status --porcelain=v1)" ]]; then
  echo "ERROR: a failed Cargo lock refresh was not rolled back cleanly" >&2
  exit 1
fi

# A consumer-owned mirror sync is not a runtime migration. The repinner must
# stay red when the mirror advances but the Python peer still speaks the old wire.
mkdir -p "$tmp/mirror-runtime-base/mirror-runtime/ncp" "$tmp/mirror-runtime-base/mirror-runtime/scripts"
printf '%s\n' \
  'mirror_ref ncp/.mirror-ref' \
  'python_wire protocol.py v0.7.0' \
  'repin_cmd scripts/sync.sh {TAG}' > "$tmp/mirror-runtime-base/mirror-runtime/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/mirror-runtime-base/mirror-runtime/ncp/.mirror-ref"
printf '%s\n' 'NCP_VERSION = "0.7"' > "$tmp/mirror-runtime-base/mirror-runtime/protocol.py"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'printf "%s\n" "$1" > ncp/.mirror-ref' > "$tmp/mirror-runtime-base/mirror-runtime/scripts/sync.sh"
chmod +x "$tmp/mirror-runtime-base/mirror-runtime/scripts/sync.sh"
prepare_repin_base "$tmp/mirror-runtime-base"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/mirror-runtime-base" >/dev/null 2>&1; then
  echo "ERROR: a mirror-only bump hid a stale Python runtime wire" >&2
  exit 1
fi
if [[ "$(tr -d '[:space:]' < "$tmp/mirror-runtime-base/mirror-runtime/ncp/.mirror-ref")" != "v0.7.0" ]] ||
  [[ -n "$(git -C "$tmp/mirror-runtime-base/mirror-runtime" status --porcelain=v1)" ]]; then
  echo "ERROR: failed post-repin verification did not restore the mirror consumer" >&2
  exit 1
fi

# Git cleanliness is a fleet-wide preflight. A dirty later consumer must prevent
# an earlier clean consumer's command from running.
mkdir -p "$tmp/dirty-preflight-base/clean/scripts" "$tmp/dirty-preflight-base/dirty/scripts"
for consumer in clean dirty; do
  printf '%s\n' \
    'mirror_ref .mirror-ref' \
    'repin_cmd scripts/repin.sh {TAG}' \
    > "$tmp/dirty-preflight-base/$consumer/.ncp-consumer"
  printf '%s\n' 'v0.7.0' > "$tmp/dirty-preflight-base/$consumer/.mirror-ref"
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "%s\n" "$1" > .mirror-ref' \
    'touch command-ran' \
    > "$tmp/dirty-preflight-base/$consumer/scripts/repin.sh"
  chmod +x "$tmp/dirty-preflight-base/$consumer/scripts/repin.sh"
done
prepare_repin_base "$tmp/dirty-preflight-base"
touch "$tmp/dirty-preflight-base/dirty/untracked-input"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/dirty-preflight-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted a dirty consumer worktree" >&2
  exit 1
fi
if [[ -e "$tmp/dirty-preflight-base/clean/command-ran" ]] ||
  [[ "$(tr -d '[:space:]' < "$tmp/dirty-preflight-base/clean/.mirror-ref")" != "v0.7.0" ]]; then
  echo "ERROR: a clean consumer mutated before fleet cleanliness preflight completed" >&2
  exit 1
fi

# A descriptor-shaped directory is not sufficient: every consumer must be the
# root of an actual Git worktree before any consumer command can run.
mkdir -p "$tmp/non-git-preflight-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/non-git-preflight-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/non-git-preflight-base/consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'touch command-ran' \
  > "$tmp/non-git-preflight-base/consumer/scripts/repin.sh"
chmod +x "$tmp/non-git-preflight-base/consumer/scripts/repin.sh"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/non-git-preflight-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted a consumer outside a Git worktree" >&2
  exit 1
fi
if [[ -e "$tmp/non-git-preflight-base/consumer/command-ran" ]]; then
  echo "ERROR: Git-repository validation happened after a consumer command" >&2
  exit 1
fi

# Pathlib discovery includes hidden direct children, so the shell transaction must
# cover that same fleet rather than silently omitting a validated hidden consumer.
mkdir -p "$tmp/hidden-consumer-base/.consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/hidden-consumer-base/.consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/hidden-consumer-base/.consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'printf "%s\n" "$1" > .mirror-ref' \
  > "$tmp/hidden-consumer-base/.consumer/scripts/repin.sh"
chmod +x "$tmp/hidden-consumer-base/.consumer/scripts/repin.sh"
prepare_repin_base "$tmp/hidden-consumer-base"
PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/hidden-consumer-base" >/dev/null 2>&1
"$CHECKER" v0.8.0 "$tmp/hidden-consumer-base" >/dev/null

# Ignored descriptor targets do not make a worktree visibly dirty, so preflight
# must reject them as unrecoverable before the custom command can run.
mkdir -p "$tmp/ignored-pin-base/consumer/scripts"
printf '%s\n' '.mirror-ref' > "$tmp/ignored-pin-base/consumer/.gitignore"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/ignored-pin-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/ignored-pin-base/consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'touch command-ran' \
  > "$tmp/ignored-pin-base/consumer/scripts/repin.sh"
chmod +x "$tmp/ignored-pin-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/ignored-pin-base"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/ignored-pin-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted an ignored, untracked descriptor target" >&2
  exit 1
fi
if [[ -e "$tmp/ignored-pin-base/consumer/command-ran" ]]; then
  echo "ERROR: tracked-target validation happened after a consumer command" >&2
  exit 1
fi

# Assume-unchanged and skip-worktree entries can hide bytes from status/diff and
# cannot be reconstructed from HEAD without first clearing their index flags.
mkdir -p "$tmp/index-flags-base/assume/scripts" "$tmp/index-flags-base/sparse/scripts"
for consumer in assume sparse; do
  printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
    > "$tmp/index-flags-base/$consumer/.ncp-consumer"
  printf '%s\n' 'v0.7.0' > "$tmp/index-flags-base/$consumer/.mirror-ref"
  printf '%s\n' '#!/bin/sh' 'touch command-ran' \
    > "$tmp/index-flags-base/$consumer/scripts/repin.sh"
  chmod +x "$tmp/index-flags-base/$consumer/scripts/repin.sh"
done
prepare_repin_base "$tmp/index-flags-base"
git -C "$tmp/index-flags-base/assume" update-index --assume-unchanged .mirror-ref
git -C "$tmp/index-flags-base/sparse" update-index --skip-worktree .mirror-ref
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/index-flags-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted hidden or sparse index state" >&2
  exit 1
fi
if find "$tmp/index-flags-base" -name command-ran -print -quit | grep -q .; then
  echo "ERROR: index-state validation happened after a consumer command" >&2
  exit 1
fi

# Branch validation also precedes every consumer command.
mkdir -p "$tmp/branch-preflight-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/branch-preflight-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/branch-preflight-base/consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'touch command-ran' \
  > "$tmp/branch-preflight-base/consumer/scripts/repin.sh"
chmod +x "$tmp/branch-preflight-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/branch-preflight-base"
git -C "$tmp/branch-preflight-base/consumer" checkout -qb topic
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/branch-preflight-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted a consumer away from main" >&2
  exit 1
fi
if [[ -e "$tmp/branch-preflight-base/consumer/command-ran" ]]; then
  echo "ERROR: branch validation happened after a consumer command" >&2
  exit 1
fi

# Command-placeholder validation is also fleet-wide. A later command cannot
# borrow revision metadata from another descriptor or fail after an earlier run.
mkdir -p "$tmp/command-preflight-base/consumer-a/scripts" \
  "$tmp/command-preflight-base/consumer-b/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/command-preflight-base/consumer-a/.ncp-consumer"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {REV}' \
  > "$tmp/command-preflight-base/consumer-b/.ncp-consumer"
for consumer in consumer-a consumer-b; do
  printf '%s\n' 'v0.7.0' > "$tmp/command-preflight-base/$consumer/.mirror-ref"
  printf '%s\n' '#!/bin/sh' 'touch command-ran' \
    > "$tmp/command-preflight-base/$consumer/scripts/repin.sh"
  chmod +x "$tmp/command-preflight-base/$consumer/scripts/repin.sh"
done
prepare_repin_base "$tmp/command-preflight-base"
if PATH="$FAKE_PATH" "$REPINNER" --dry-run v0.8.0 "$tmp/command-preflight-base" >/dev/null 2>&1; then
  echo "ERROR: dry-run accepted {REV} without consumer revision metadata" >&2
  exit 1
fi
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/command-preflight-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted {REV} without consumer revision metadata" >&2
  exit 1
fi
if find "$tmp/command-preflight-base" -name command-ran -print -quit | grep -q .; then
  echo "ERROR: command-placeholder validation happened after a consumer command" >&2
  exit 1
fi

# Dry-run performs the same preflight and lists exact declared paths/actions, but
# executes no command and leaves every repository byte clean.
mkdir -p "$tmp/dry-run-base/dry-run/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' $'repin_cmd\tscripts/repin.sh {TAG}' \
  > "$tmp/dry-run-base/dry-run/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/dry-run-base/dry-run/.mirror-ref"
printf '%s\n' \
  '#!/bin/sh' \
  'printf "%s\n" "$1" > .mirror-ref' \
  'touch command-ran' \
  > "$tmp/dry-run-base/dry-run/scripts/repin.sh"
chmod +x "$tmp/dry-run-base/dry-run/scripts/repin.sh"
prepare_repin_base "$tmp/dry-run-base"
dry_run_before="$(repository_digest "$tmp/dry-run-base/dry-run")"
dry_run_output="$(PATH="$FAKE_PATH" "$REPINNER" --dry-run v0.8.0 "$tmp/dry-run-base")"
if [[ "$dry_run_before" != "$(repository_digest "$tmp/dry-run-base/dry-run")" ]] ||
  [[ -e "$tmp/dry-run-base/dry-run/command-ran" ]] ||
  [[ -n "$(git -C "$tmp/dry-run-base/dry-run" status --porcelain=v1)" ]]; then
  echo "ERROR: dry-run mutated a consumer" >&2
  exit 1
fi
if ! grep -Fq 'planned path: dry-run/.mirror-ref' <<<"$dry_run_output" ||
  ! grep -Fq 'would run consumer repin_cmd: scripts/repin.sh v0.8.0' <<<"$dry_run_output"; then
  echo "ERROR: dry-run omitted an exact planned path or action" >&2
  exit 1
fi

# Mutating runs use a per-worktree advisory lock. An existing owner must prevent
# all commands without removing or replacing that owner's lock.
mkdir -p "$tmp/locked-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/locked-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/locked-base/consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'touch command-ran' \
  > "$tmp/locked-base/consumer/scripts/repin.sh"
chmod +x "$tmp/locked-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/locked-base"
locked_git_dir="$(git -C "$tmp/locked-base/consumer" rev-parse --absolute-git-dir)"
mkdir "$locked_git_dir/ncp-repin.lock"
printf '%s\n' 'external-owner' > "$locked_git_dir/ncp-repin.lock/owner"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/locked-base" >/dev/null 2>&1; then
  echo "ERROR: repinner ignored an existing consumer transaction lock" >&2
  exit 1
fi
if [[ -e "$tmp/locked-base/consumer/command-ran" ]] ||
  [[ "$(<"$locked_git_dir/ncp-repin.lock/owner")" != "external-owner" ]]; then
  echo "ERROR: lock refusal ran a command or disturbed another lock owner" >&2
  exit 1
fi
rm -rf "$locked_git_dir/ncp-repin.lock"

# A failure in the second consumer rolls the first consumer and failure-created
# untracked files back to their initial clean commits.
mkdir -p "$tmp/transaction-base/consumer-a/scripts" "$tmp/transaction-base/consumer-b/scripts"
for consumer in consumer-a consumer-b; do
  printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
    > "$tmp/transaction-base/$consumer/.ncp-consumer"
  printf '%s\n' 'v0.7.0' > "$tmp/transaction-base/$consumer/.mirror-ref"
done
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'printf "%s\n" "$1" > .mirror-ref' \
  'touch created-a' \
  > "$tmp/transaction-base/consumer-a/scripts/repin.sh"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'printf "%s\n" "$1" > .mirror-ref' \
  'touch created-b' \
  'exit 1' \
  > "$tmp/transaction-base/consumer-b/scripts/repin.sh"
chmod +x "$tmp/transaction-base/consumer-a/scripts/repin.sh" \
  "$tmp/transaction-base/consumer-b/scripts/repin.sh"
prepare_repin_base "$tmp/transaction-base"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/transaction-base" >/dev/null 2>&1; then
  echo "ERROR: multi-consumer transaction succeeded after a consumer command failed" >&2
  exit 1
fi
for consumer in consumer-a consumer-b; do
  if [[ "$(tr -d '[:space:]' < "$tmp/transaction-base/$consumer/.mirror-ref")" != "v0.7.0" ]] ||
    [[ -e "$tmp/transaction-base/$consumer/created-a" ]] ||
    [[ -e "$tmp/transaction-base/$consumer/created-b" ]] ||
    [[ -n "$(git -C "$tmp/transaction-base/$consumer" status --porcelain=v1)" ]]; then
    echo "ERROR: transaction rollback did not restore $consumer" >&2
    exit 1
  fi
done

# Failure rollback clears transaction-created assume/skip flags before restoring
# tracked bytes, so the post-state is the exact ordinary index state from preflight.
mkdir -p "$tmp/index-rollback-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/index-rollback-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/index-rollback-base/consumer/.mirror-ref"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'printf "%s\n" "$1" > .mirror-ref' \
  'git update-index --assume-unchanged .mirror-ref' \
  'exit 1' \
  > "$tmp/index-rollback-base/consumer/scripts/repin.sh"
chmod +x "$tmp/index-rollback-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/index-rollback-base"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/index-rollback-base" >/dev/null 2>&1; then
  echo "ERROR: failed index-flag command returned success" >&2
  exit 1
fi
if [[ "$(tr -d '[:space:]' < "$tmp/index-rollback-base/consumer/.mirror-ref")" != "v0.7.0" ]] ||
  [[ "$(git -C "$tmp/index-rollback-base/consumer" ls-files -v .mirror-ref)" != "H .mirror-ref" ]] ||
  [[ -n "$(git -C "$tmp/index-rollback-base/consumer" status --porcelain=v1)" ]]; then
  echo "ERROR: rollback did not restore ordinary tracked/index state" >&2
  exit 1
fi

# Branch/HEAD drift can belong to a concurrent actor. Automatic rollback must not
# force-reset a new commit that appeared during the transaction.
mkdir -p "$tmp/head-drift-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/head-drift-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/head-drift-base/consumer/.mirror-ref"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'printf "%s\n" "$1" > .mirror-ref' \
  'git add -- .mirror-ref' \
  'git commit -qm "concurrent fixture commit"' \
  'exit 1' \
  > "$tmp/head-drift-base/consumer/scripts/repin.sh"
chmod +x "$tmp/head-drift-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/head-drift-base"
head_before="$(git -C "$tmp/head-drift-base/consumer" rev-parse HEAD)"
head_drift_git_dir="$(git -C "$tmp/head-drift-base/consumer" rev-parse --absolute-git-dir)"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/head-drift-base" >/dev/null 2>&1; then
  echo "ERROR: failed command with HEAD drift returned success" >&2
  exit 1
fi
if [[ "$(git -C "$tmp/head-drift-base/consumer" rev-parse HEAD)" == "$head_before" ]] ||
  [[ "$(tr -d '[:space:]' < "$tmp/head-drift-base/consumer/.mirror-ref")" != "v0.8.0" ]] ||
  [[ -e "$head_drift_git_dir/ncp-repin.lock" ]]; then
  echo "ERROR: rollback erased a new HEAD or leaked its advisory lock" >&2
  exit 1
fi

# A consumer command cannot smuggle staged state into a successful result. The
# invariant failure restores both the index and worktree to the recorded commit.
mkdir -p "$tmp/staged-command-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/staged-command-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/staged-command-base/consumer/.mirror-ref"
printf '%s\n' \
  '#!/bin/sh' \
  'set -eu' \
  'printf "%s\n" "$1" > .mirror-ref' \
  'git add -- .mirror-ref' \
  'touch created-by-command' \
  > "$tmp/staged-command-base/consumer/scripts/repin.sh"
chmod +x "$tmp/staged-command-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/staged-command-base"
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/staged-command-base" >/dev/null 2>&1; then
  echo "ERROR: repinner accepted staged state from a consumer command" >&2
  exit 1
fi
if [[ "$(tr -d '[:space:]' < "$tmp/staged-command-base/consumer/.mirror-ref")" != "v0.7.0" ]] ||
  [[ -e "$tmp/staged-command-base/consumer/created-by-command" ]] ||
  [[ -n "$(git -C "$tmp/staged-command-base/consumer" status --porcelain=v1)" ]]; then
  echo "ERROR: staged-command rollback did not restore the index and worktree" >&2
  exit 1
fi

# A successful transaction suggests only exact Git-visible paths and never a
# repository-wide staging shortcut.
mkdir -p "$tmp/exact-path-base/consumer/scripts"
printf '%s\n' 'mirror_ref .mirror-ref' 'repin_cmd scripts/repin.sh {TAG}' \
  > "$tmp/exact-path-base/consumer/.ncp-consumer"
printf '%s\n' 'v0.7.0' > "$tmp/exact-path-base/consumer/.mirror-ref"
printf '%s\n' '#!/bin/sh' 'printf "%s\n" "$1" > .mirror-ref' \
  > "$tmp/exact-path-base/consumer/scripts/repin.sh"
chmod +x "$tmp/exact-path-base/consumer/scripts/repin.sh"
prepare_repin_base "$tmp/exact-path-base"
exact_output="$(PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/exact-path-base")"
exact_consumer="$(cd "$tmp/exact-path-base/consumer" && pwd -P)"
exact_git_dir="$(git -C "$tmp/exact-path-base/consumer" rev-parse --absolute-git-dir)"
if grep -Fq 'git add -A' <<<"$exact_output"; then
  echo "ERROR: repinner suggested repository-wide staging" >&2
  exit 1
fi
if ! grep -Fq \
  "git -C $exact_consumer add -- .mirror-ref" \
  <<<"$exact_output"; then
  echo "ERROR: repinner did not suggest the exact changed path" >&2
  exit 1
fi
if ! git -C "$tmp/exact-path-base/consumer" diff --cached --quiet --; then
  echo "ERROR: repinner staged consumer changes" >&2
  exit 1
fi
if [[ -e "$exact_git_dir/ncp-repin.lock" ]]; then
  echo "ERROR: successful transaction leaked its advisory lock" >&2
  exit 1
fi

echo "consumer pin descriptor tests passed"
