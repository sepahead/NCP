#!/usr/bin/env bash
# Quarantined B01 pre-ratification runner. A pass grants no acceptance or release claim.
set -euo pipefail
umask 077

cd "$(dirname "$0")"

python3 -m compileall -q .
ruff format --check *.py
ruff check --select E,F,I,N,S,UP *.py
python3 model_check.py --self-test >/dev/null
python3 run_smt.py --self-test >/dev/null
python3 resource_probe.py --self-test >/dev/null
python3 run_all.py | python3 verify_result.py --self-test
