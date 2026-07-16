#!/usr/bin/env bash
# Quarantined local-feasibility runner. A passing run is not production evidence.
set -euo pipefail

cd "$(dirname "$0")"

python3 verify_source_matrix.py
python3 -m unittest discover -s tests -p 'test_*.py'
cargo fmt --all -- --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
cargo run --locked --quiet | python3 verify_result.py
