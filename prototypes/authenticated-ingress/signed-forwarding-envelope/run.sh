#!/usr/bin/env bash
# Quarantined local-feasibility runner. A pass grants no production or release claim.
set -euo pipefail
umask 077

cd "$(dirname "$0")"

uv lock --check
uv sync --locked
uv run --locked python verify_profile.py
uv run --locked ruff format --check .
uv run --locked ruff check .
uv run --locked python -m compileall -q differential prototype tests
uv run --locked python -m unittest discover -s tests -p 'test_*.py'
./node-verifier/run.sh
./differential/run.sh
uv run --locked python tests/live_result.py 2>&1 | uv run --locked python verify_result.py
