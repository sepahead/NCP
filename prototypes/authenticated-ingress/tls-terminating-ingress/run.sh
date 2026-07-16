#!/usr/bin/env bash
# Quarantined local-feasibility runner. A passing run is not production evidence.
set -euo pipefail

cd "$(dirname "$0")"

python3 verify_features.py
python3 -m unittest discover -s tests -p 'test_*.py'
cargo fmt --all -- --check
cargo clippy --locked --all-targets --all-features -- -D warnings -D clippy::perf
cargo test --locked
cargo doc --locked --no-deps
cargo test --locked --test ingress live_result -- --exact --nocapture 2>&1 \
  | python3 verify_result.py
