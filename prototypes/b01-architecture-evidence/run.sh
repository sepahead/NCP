#!/usr/bin/env bash
# Quarantined B01 pre-ratification runner. A pass grants no acceptance or release claim.
set -euo pipefail
umask 077

cd "$(dirname "$0")"

adr_semantics_root="adr-example-semantics"
adr_semantics_manifest="$adr_semantics_root/rust/Cargo.toml"
signed_forwarding_project="../authenticated-ingress/signed-forwarding-envelope"
repository_root="$(cd ../.. && pwd -P)"
temporary_parent="${TMPDIR:-/tmp}"
if [[ "$temporary_parent" != /* ]]; then
  echo "ERROR: TMPDIR must be absolute" >&2
  exit 1
fi
temporary_parent="$(cd -- "$temporary_parent" && pwd -P)" || {
  echo "ERROR: TMPDIR must resolve to an available directory" >&2
  exit 1
}
case "$temporary_parent/" in
  "$repository_root/"*)
    echo "ERROR: TMPDIR must resolve outside the repository" >&2
    exit 1
    ;;
esac
adr_semantics_tmp="$(mktemp -d "$temporary_parent/ncp-b01-adr.XXXXXX")"
cleanup() { rm -rf -- "$adr_semantics_tmp"; }
trap cleanup EXIT
adr_semantics_tmp="$(cd -- "$adr_semantics_tmp" && pwd -P)"
case "$adr_semantics_tmp/" in
  "$repository_root/"*)
    echo "ERROR: temporary work directory resolved inside the repository" >&2
    exit 1
    ;;
esac
export TMPDIR="$adr_semantics_tmp"
export PYTHONPYCACHEPREFIX="$adr_semantics_tmp/pycache"
export RUFF_CACHE_DIR="$adr_semantics_tmp/ruff-cache"
export UV_PROJECT_ENVIRONMENT="$adr_semantics_tmp/signed-forwarding-envelope-venv"
python_runtime="$(
  python3 -I -S -B -c \
    'import sys; print(f"{sys.implementation.name}:{sys.version_info.major}.{sys.version_info.minor}")'
)"
if [[ "$python_runtime" != "cpython:3.14" ]]; then
  echo "ERROR: the B01 runner requires outer CPython 3.14" >&2
  exit 1
fi

uv sync --offline --locked --no-dev --project "$signed_forwarding_project"

source_probe_bytes=$(wc -c <source_issuance_index_probe.py)
if ((source_probe_bytes > 524288)); then
  echo "ERROR: source-index probe exceeds immutable 512 KiB cap" >&2
  exit 1
fi

python3 -m compileall -q .
ruff format --check -- ./*.py
ruff check --select E,F,I,N,S,UP -- ./*.py
cargo fetch --manifest-path "$adr_semantics_manifest" --locked
cargo fmt --manifest-path "$adr_semantics_manifest" -- --check
CARGO_TARGET_DIR="$adr_semantics_tmp/target" \
  cargo clippy --manifest-path "$adr_semantics_manifest" \
    --all-targets --locked --offline -- -D warnings
CARGO_TARGET_DIR="$adr_semantics_tmp/target" \
  cargo test --manifest-path "$adr_semantics_manifest" --locked --offline
(
  cd "$adr_semantics_root/typescript"
  bun run typecheck
)
python3 adr_example_semantics.py --self-test
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
