#!/usr/bin/env bash
# Focused regression tests for tag- and immutable-revision consumer descriptors.
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
  '  if [ "$1" = "--manifest-path" ]; then shift; manifest=$1; fi' \
  '  shift' \
  'done' \
  'if [ -n "${FAKE_CARGO_LOCK_LINE:-}" ]; then' \
  '  printf "%s\n" "$FAKE_CARGO_LOCK_LINE" > "$(dirname "$manifest")/Cargo.lock"' \
  'fi' > "$tmp/fake-bin/cargo"
chmod +x "$tmp/fake-bin/cargo"
printf '%s\n' '#!/bin/sh' 'exit 0' > "$tmp/fake-bin/bun"
chmod +x "$tmp/fake-bin/bun"
# Keep the Python 3.11+ interpreter that provides stdlib tomllib while replacing
# cargo. macOS /usr/bin/python3 may be older than the release-gate interpreter.
PYTHON_DIR="$(dirname "$(command -v python3)")"
FAKE_PATH="$tmp/fake-bin:$PYTHON_DIR:/usr/bin:/bin"

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
  '{"dependencies":{"@sepehrmn/ncp":"github:sepahead/NCP#v1.0.0","ncp-shadow":"github:sepahead/NCP#v1.1.0"}}' \
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
  find "$1" -type f -exec shasum -a 256 {} \; | LC_ALL=C sort | shasum -a 256 | awk '{print $1}'
}
assert_hostile_preflight() {
  local base="$1" label="$2" before after
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
HOME="$tmp/no-home" PATH="$FAKE_PATH" \
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

# A source-looking string outside a dependency table is ambiguous to a lexical
# formatter. The checker may inspect the actual dependency, but generic preflight
# refuses the rewrite before changing either occurrence.
mkdir -p "$tmp/npm-rewrite-ambiguous/consumer"
printf '%s\n' 'npm_tag package.json' \
  > "$tmp/npm-rewrite-ambiguous/consumer/.ncp-consumer"
printf '%s\n' \
  '{"dependencies":{"@sepahead/ncp":"github:sepahead/NCP#v0.8.0"},"metadata":{"upstream":"github:sepahead/NCP#v0.8.0"}}' \
  > "$tmp/npm-rewrite-ambiguous/consumer/package.json"
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

# A failed lock refresh must make the command fail and the post-state remain
# visibly inconsistent to the read-only checker.
mkdir -p "$tmp/rev-fail-base/rev-fail"
printf '%s\n' \
  'cargo_rev Cargo.toml v0.7.0 0000000000000000000000000000000000000000' \
  'cargo_lock_rev Cargo.lock v0.7.0 0000000000000000000000000000000000000000' > "$tmp/rev-fail-base/rev-fail/.ncp-consumer"
printf '%s\n' 'ncp-core = { version = "0.7.0", git = "https://github.com/sepahead/NCP", rev = "0000000000000000000000000000000000000000" }' > "$tmp/rev-fail-base/rev-fail/Cargo.toml"
printf '%s\n' 'source = "git+https://github.com/sepahead/NCP?rev=0000000000000000000000000000000000000000#0000000000000000000000000000000000000000"' > "$tmp/rev-fail-base/rev-fail/Cargo.lock"
if FAKE_CARGO_FAIL=1 PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/rev-fail-base" >/dev/null 2>&1; then
  echo "ERROR: a failed Cargo lock refresh returned success" >&2
  exit 1
fi
if "$CHECKER" v0.8.0 "$tmp/rev-fail-base" >/dev/null 2>&1; then
  echo "ERROR: the stale lockfile passed after a failed refresh" >&2
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
if PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/mirror-runtime-base" >/dev/null 2>&1; then
  echo "ERROR: a mirror-only bump hid a stale Python runtime wire" >&2
  exit 1
fi
if [[ "$(tr -d '[:space:]' < "$tmp/mirror-runtime-base/mirror-runtime/ncp/.mirror-ref")" != "v0.8.0" ]]; then
  echo "ERROR: the consumer-owned mirror sync did not run" >&2
  exit 1
fi

echo "consumer pin descriptor tests passed"
