#!/usr/bin/env bash
# Quarantined B01 pre-ratification runner. A pass grants no acceptance or release claim.
set -euo pipefail
umask 077

cd "$(dirname "$0")"

source_probe_bytes=$(wc -c <source_issuance_index_probe.py)
if ((source_probe_bytes > 524288)); then
  echo "ERROR: source-index probe exceeds immutable 512 KiB cap" >&2
  exit 1
fi

python3 -m compileall -q .
ruff format --check -- ./*.py
ruff check --select E,F,I,N,S,UP -- ./*.py
python3 bounded_canonical.py --self-test >/dev/null
python3 model_check.py --self-test >/dev/null
python3 source_inventory.py --self-test >/dev/null
python3 observer_authorization_probe.py --self-test >/dev/null
python3 observer_capture_probe.py --self-test >/dev/null
python3 freshness_acceptance_probe.py --self-test >/dev/null
python3 source_issuance_index_probe.py --self-test >/dev/null
python3 -OO source_issuance_index_probe.py --self-test >/dev/null
cmp -s \
  <(python3 source_issuance_index_probe.py) \
  <(python3 -OO source_issuance_index_probe.py) || {
  echo "ERROR: source-index result changes under optimized Python" >&2
  exit 1
}
cmp -s \
  <(
    PYTHONHASHSEED=1 python3 source_issuance_index_probe.py ||
      printf '\n__SOURCE_INDEX_SEED_1_FAILED__\n'
  ) \
  <(
    PYTHONHASHSEED=987654 python3 source_issuance_index_probe.py ||
      printf '\n__SOURCE_INDEX_SEED_987654_FAILED__\n'
  ) || {
  echo "ERROR: source-index result depends on Python hash order" >&2
  exit 1
}
cmp -s \
  <(
    PYTHONHASHSEED=1 python3 -OO source_issuance_index_probe.py ||
      printf '\n__SOURCE_INDEX_OPT_SEED_1_FAILED__\n'
  ) \
  <(
    PYTHONHASHSEED=987654 python3 -OO source_issuance_index_probe.py ||
      printf '\n__SOURCE_INDEX_OPT_SEED_987654_FAILED__\n'
  ) || {
  echo "ERROR: optimized source-index result depends on Python hash order" >&2
  exit 1
}
for observer_probe in observer_authorization_probe.py observer_capture_probe.py; do
  cmp -s \
    <(python3 "$observer_probe") \
    <(python3 -OO "$observer_probe") || {
    echo "ERROR: $observer_probe result changes under optimized Python" >&2
    exit 1
  }
  cmp -s \
    <(
      PYTHONHASHSEED=1 python3 "$observer_probe" ||
        printf '\n__OBSERVER_SEED_1_FAILED__\n'
    ) \
    <(
      PYTHONHASHSEED=987654 python3 "$observer_probe" ||
        printf '\n__OBSERVER_SEED_987654_FAILED__\n'
    ) || {
    echo "ERROR: $observer_probe result depends on Python hash order" >&2
    exit 1
  }
  cmp -s \
    <(
      PYTHONHASHSEED=1 python3 -OO "$observer_probe" ||
        printf '\n__OBSERVER_OPT_SEED_1_FAILED__\n'
    ) \
    <(
      PYTHONHASHSEED=987654 python3 -OO "$observer_probe" ||
        printf '\n__OBSERVER_OPT_SEED_987654_FAILED__\n'
    ) || {
    echo "ERROR: optimized $observer_probe result depends on Python hash order" >&2
    exit 1
  }
done
cmp -s \
  <(
    PYTHONHASHSEED=1 python3 freshness_acceptance_probe.py ||
      printf '\n__FRESHNESS_SEED_1_FAILED__\n'
  ) \
  <(
    PYTHONHASHSEED=987654 python3 freshness_acceptance_probe.py ||
      printf '\n__FRESHNESS_SEED_987654_FAILED__\n'
  ) || {
  echo "ERROR: freshness/acceptance result depends on Python hash order" >&2
  exit 1
}
python3 decision_probe.py --self-test >/dev/null
python3 run_smt.py --self-test >/dev/null
python3 resource_probe.py --self-test >/dev/null
python3 run_all.py | python3 verify_result.py --self-test
