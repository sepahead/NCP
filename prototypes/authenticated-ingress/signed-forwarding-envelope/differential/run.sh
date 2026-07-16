#!/usr/bin/env bash
# Process-isolated differential gate. A pass grants no production or release claim.
set -euo pipefail
umask 077

cd "$(dirname "$0")/.."

uv run --locked python differential/verify_corpus.py
uv run --locked python differential/run_differential.py
