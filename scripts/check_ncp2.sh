#!/bin/sh
# The local gate of NCP 2 (spec/NCP-2.md). The CI workflow .github/workflows/ncp2.yml runs it too.
#
# Usage: scripts/check_ncp2.sh [--quick]
# PYTHON names the interpreter to test (default python3; NCP 2 needs Python 3.11 or later).
# --quick runs 2,000 model traces and 20,000 fuzzing cases instead of 20,000 and 200,000.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
python=${PYTHON:-python3}
traces=20000
cases=200000
if [ "${1:-}" = "--quick" ]; then
    traces=2000
    cases=20000
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$root"

echo "== Python SDK, Python $("$python" -c 'import sys; print(sys.version.split()[0])')"
"$python" -I python/tests/test_ncp.py
"$python" -I python/tests/test_conformance.py

echo "== Shared vectors: generated, never edited"
"$python" -I conformance/generate.py "$work/vectors.json"
cmp conformance/vectors.json "$work/vectors.json"

echo "== Rust core"
(
    cd rust
    cargo fmt --check
    cargo clippy --locked --all-targets -- -D warnings
    cargo test --locked --release
    cargo build --locked --release --examples
)
examples="$root/rust/target/release/examples"

echo "== Python client with the Rust owner"
NCP_RUST_EXAMPLES="$examples" "$python" -I python/tests/test_ncp.py BindingTests.test_python_client_with_the_rust_owner

echo "== Model conformance of both owners, $traces traces each"
"$python" -I model/conformance.py --traces "$traces"
# One connection per trace: a Unix domain socket, because TCP would run out of ephemeral ports.
"$python" -I model/conformance.py --traces "$traces" --owner "$examples/model_owner" "$work/owner.sock"

echo "== Differential fuzzing of the decoders, $cases cases"
"$python" -I conformance/fuzz.py --decoder "$examples/decode_corpus" --cases "$cases"

echo "NCP 2 gate passed"
