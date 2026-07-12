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
FAKE_PATH="$tmp/fake-bin:/usr/bin:/bin"

mkdir -p "$tmp/tag-consumer" "$tmp/rev-consumer" "$tmp/python-consumer"
printf '%s\n' 'cargo_tag Cargo.toml' 'cargo_lock Cargo.lock' > "$tmp/tag-consumer/.ncp-consumer"
printf '%s\n' 'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v0.8.0" }' > "$tmp/tag-consumer/Cargo.toml"
printf '%s\n' 'source = "git+https://github.com/sepahead/NCP?tag=v0.8.0#abc"' > "$tmp/tag-consumer/Cargo.lock"

printf '%s\n' \
  "cargo_rev Cargo.toml v0.8.0 $REV" \
  "cargo_lock_rev Cargo.lock v0.8.0 $REV" > "$tmp/rev-consumer/.ncp-consumer"
printf '%s\n' \
  "ncp-core = { git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
  "ncp-zenoh = { git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" > "$tmp/rev-consumer/Cargo.toml"
printf '%s\n' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" > "$tmp/rev-consumer/Cargo.lock"

printf '%s\n' 'python_wire protocol.py v0.8.0' > "$tmp/python-consumer/.ncp-consumer"
printf '%s\n' 'NCP_VERSION = "0.8"' > "$tmp/python-consumer/protocol.py"

"$CHECKER" v0.8.0 "$tmp" >/dev/null

printf '%s\n' 'NCP_VERSION = "0.7"' > "$tmp/python-consumer/protocol.py"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a stale Python runtime wire passed its declared release" >&2
  exit 1
fi
printf '%s\n' 'NCP_VERSION = "0.8"' > "$tmp/python-consumer/protocol.py"

printf '%s\n' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  'source = "git+https://github.com/sepahead/NCP?rev=0000000000000000000000000000000000000000#0000000000000000000000000000000000000000"' > "$tmp/rev-consumer/Cargo.lock"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a mismatched second lock source was accepted" >&2
  exit 1
fi

printf '%s\n' \
  "ncp-core = { git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
  'ncp-zenoh = { git = "https://github.com/sepahead/NCP", rev = "0000000000000000000000000000000000000000" }' > "$tmp/rev-consumer/Cargo.toml"
printf '%s\n' \
  "source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
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

printf '%s\n' \
  "ncp-core = { version = \"0.8.0\", git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" \
  "ncp-zenoh = { version = \"0.7.0\", git = \"https://github.com/sepahead/NCP\", rev = \"$REV\" }" > "$tmp/rev-consumer/Cargo.toml"
if "$CHECKER" v0.8.0 "$tmp" >/dev/null 2>&1; then
  echo "ERROR: a stale explicit Cargo version was accepted" >&2
  exit 1
fi

# A tag-only fleet must not require the target tag in the local NCP checkout.
mkdir -p "$tmp/tag-only-base/tag-only"
printf '%s\n' 'cargo_tag Cargo.toml' > "$tmp/tag-only-base/tag-only/.ncp-consumer"
printf '%s\n' 'ncp-core = { git = "https://github.com/sepahead/NCP", tag = "v0.8.0" }' > "$tmp/tag-only-base/tag-only/Cargo.toml"
PATH="$FAKE_PATH" "$REPINNER" v9.9.9 "$tmp/tag-only-base" >/dev/null 2>&1
"$CHECKER" v9.9.9 "$tmp/tag-only-base" >/dev/null

# Revision re-pins must update the manifest, lockfile, descriptor metadata, and
# an exact trailing release comment to the requested local release tag.
mkdir -p "$tmp/rev-repin-base/rev-repin"
printf '%s\n' \
  'cargo_rev Cargo.toml v0.7.0 0000000000000000000000000000000000000000 # exact release' \
  'cargo_lock_rev Cargo.lock v0.7.0 0000000000000000000000000000000000000000' > "$tmp/rev-repin-base/rev-repin/.ncp-consumer"
printf '%s\n' 'ncp-core = { git = "https://github.com/sepahead/NCP", rev = "0000000000000000000000000000000000000000", version = "0.7.0" } # v0.7.0' > "$tmp/rev-repin-base/rev-repin/Cargo.toml"
printf '%s\n' 'source = "git+https://github.com/sepahead/NCP?rev=0000000000000000000000000000000000000000#0000000000000000000000000000000000000000"' > "$tmp/rev-repin-base/rev-repin/Cargo.lock"
FAKE_CARGO_LOCK_LINE="source = \"git+https://github.com/sepahead/NCP?rev=$REV#$REV\"" \
  PATH="$FAKE_PATH" "$REPINNER" v0.8.0 "$tmp/rev-repin-base" >/dev/null 2>&1
"$CHECKER" v0.8.0 "$tmp/rev-repin-base" >/dev/null
if ! grep -q '# v0.8.0$' "$tmp/rev-repin-base/rev-repin/Cargo.toml"; then
  echo "ERROR: the exact trailing release comment was not refreshed" >&2
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
