#!/bin/sh
# The gate of the Zenoh binding of NCP 2 (bindings/zenoh, specification section 9.2): the Rust
# crate's format, lint, and tests, the Python package's tests, and the tests across the two
# languages. The CI workflow .github/workflows/ncp2-zenoh.yml runs it.
#
# Usage: scripts/check_ncp2_zenoh.sh
# PYTHON names an interpreter with eclipse-zenoh 1.10.2. Without it, the script makes a virtual
# environment in a temporary directory and installs eclipse-zenoh==1.10.2 there (needs the network).
# The TLS tests need the openssl command.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$root"

if [ -z "${PYTHON:-}" ]; then
    python3 -m venv "$work/venv"
    "$work/venv/bin/pip" install --quiet --disable-pip-version-check "eclipse-zenoh==1.10.2"
    PYTHON="$work/venv/bin/python"
fi
"$PYTHON" -c 'import importlib.metadata as m; v = m.version("eclipse-zenoh"); assert v == "1.10.2", v'
export RUST_LOG="${RUST_LOG:-error}"

echo "== Rust binding: format, lint, examples"
(
    cd bindings/zenoh/rust
    cargo fmt --check
    cargo clippy --locked --all-targets -- -D warnings
    cargo build --locked --examples
)
target=$(cd bindings/zenoh/rust && cargo metadata --locked --format-version 1 --no-deps |
    "$PYTHON" -c 'import json, sys; print(json.load(sys.stdin)["target_directory"])')

echo "== Rust binding tests, with the Python owner"
(cd bindings/zenoh/rust && NCP_ZENOH_PYTHON="$PYTHON" cargo test --locked)

echo "== Python binding tests, with the Rust owner"
NCP_ZENOH_RUST_EXAMPLES="$target/debug/examples" "$PYTHON" -I bindings/zenoh/python/tests/test_zenoh.py

echo "NCP 2 Zenoh gate passed"
