#!/usr/bin/env bash
# Complete local NCP preflight. This intentionally builds and exercises every
# shipped binding from the committed lockfiles; it is slower than a normal edit
# loop. A green result is local evidence only and cannot satisfy external gates,
# authorize a tag, or certify a release.
set -euo pipefail

cd "$(dirname "$0")/.."

tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/ncp-check.XXXXXX")"
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT

step() { printf '\n=== %s ===\n' "$1"; }
require_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'required local-preflight tool is missing: %s\n' "$1" >&2
        exit 1
    fi
}

require_tool cargo
require_tool python3
require_tool c++
require_tool bun
require_tool npm
require_tool buf

step "format + whitespace integrity"
cargo fmt --all -- --check
git diff --check
python3 scripts/gen_diagrams.py --check

step "NCP 1.0 implementation ledger + mandatory resumption views"
python3 scripts/check_implementation_ledger.py --self-test
python3 scripts/generate_implementation_ledger.py --check
python3 scripts/generate_decision_registry.py --self-test --check

step "bounded pure-Python line ingress + runner status"
python3 -m unittest -v e2e.test_bounded_json e2e.test_runner_status
python3 -m py_compile \
    e2e/bounded_json.py e2e/nest_five_networks.py \
    e2e/run_cross_language_e2e.py e2e/test_bounded_json.py \
    e2e/test_runner_status.py scripts/check_implementation_ledger.py \
    scripts/generate_implementation_ledger.py \
    scripts/generate_decision_registry.py scripts/check_adr_examples.py

step "workspace clippy (warnings denied; Python links in its dedicated gate)"
cargo clippy --workspace --exclude ncp-python --all-targets --locked -- -D warnings

step "workspace build + tests"
cargo build --workspace --exclude ncp-python --locked
cargo test --workspace --exclude ncp-python --locked

step "ncp-core TypeScript generation feature"
cargo test -p ncp-core --features ts --locked
node ncp-ts/scripts/sync-bindings.mjs

step "ncp-python type check"
cargo check -p ncp-python --locked

step "C/C++ ABI demo"
c++ -std=c++17 -I ncp-cpp/include ncp-cpp/examples/demo.cpp \
    -L target/debug -lncp_cpp -Wl,-rpath,"$PWD/target/debug" \
    -o "$tmp_dir/ncp-demo"
"$tmp_dir/ncp-demo"

step "Python wheel + required behavior corpus + smoke tests"
python3 -m venv "$tmp_dir/venv"
"$tmp_dir/venv/bin/python" -m pip install --disable-pip-version-check \
    maturin==1.14.1 pytest==9.1.1
cargo fetch --locked
CARGO_INCREMENTAL=0 "$tmp_dir/venv/bin/maturin" build -m ncp-python/Cargo.toml \
    --features extension-module --release --locked --offline --strip \
    --out "$tmp_dir/wheels"
"$tmp_dir/venv/bin/python" -m pip install --disable-pip-version-check \
    --no-index --find-links "$tmp_dir/wheels" ncp
NCP_REQUIRE_BINDING=1 "$tmp_dir/venv/bin/python" scripts/check_behavior_vectors.py
"$tmp_dir/venv/bin/python" -m pytest ncp-python/tests -q

step "Python sdist locked-source closure"
PATH="$tmp_dir/venv/bin:$PATH" \
    "$tmp_dir/venv/bin/python" scripts/build_candidate_dossier.py \
        --sdist-preflight "$(git rev-parse HEAD)"

step "TypeScript generated source + prebuilt dist are reproducible"
git diff --binary -- ncp-core/bindings ncp-ts/src/generated ncp-ts/dist \
    > "$tmp_dir/ts-before.diff"
bun install --frozen-lockfile
bun run regen
git diff --binary -- ncp-core/bindings ncp-ts/src/generated ncp-ts/dist \
    > "$tmp_dir/ts-after.diff"
cmp "$tmp_dir/ts-before.diff" "$tmp_dir/ts-after.diff"
bun run check:behavior
bun run check:integers
"$tmp_dir/venv/bin/python" scripts/check_cross_language_canonical_json.py
bun run check:ws
bun run check:package

step "deterministic historical plot tooling"
"$tmp_dir/venv/bin/python" -m pip install --disable-pip-version-check \
    -r scripts/requirements-plot.txt
"$tmp_dir/venv/bin/python" scripts/plot_perf.py --self-test --check

step "retained threat, latent-path, and traceability audit artifacts"
python3 scripts/generate_audit_artifacts.py --self-test
python3 scripts/check_audit_artifacts.py --self-test

step "handoff, proto, schema, JSON/binary corpus, and wire baselines"
python3 scripts/check_handoff_review.py --self-test
python3 scripts/generate_max_effort_handoff_index.py --self-test
python3 scripts/check_max_effort_handoff_review.py --self-test
python3 scripts/generate_max_effort_review_template.py --check
python3 scripts/generate_file_review_ledger.py --self-test
python3 scripts/generate_file_review_ledger.py --check
python3 scripts/generate_convergence_manifest.py --self-test --check
python3 scripts/check_markdown_links.py --self-test
python3 scripts/check_markdown_links.py
python3 scripts/check_proto_schema_parity.py
python3 scripts/check_conformance_vectors.py
python3 scripts/generate_conformance_manifest.py
python3 scripts/generate_contract_manifest.py --self-test
python3 scripts/generate_contract_manifest.py
python3 scripts/check_request_digests.py
python3 scripts/check_profile_digests.py
python3 scripts/check_released_baselines.py --self-test
python3 scripts/check_released_baselines.py
python3 scripts/check_buf_breaking.py --self-test
python3 scripts/check_buf_breaking.py
python3 scripts/check_buf_generator_pins.py --self-test
python3 scripts/check_wire_baseline.py --self-test
python3 scripts/check_wire_baseline.py
python3 scripts/check_wire_baseline.py --verify-current-cut
python3 scripts/check_schema_defaults.py
python3 scripts/check_release_gates.py --self-test
python3 scripts/check_release_gates.py
scripts/test_consumer_pins.sh
cargo run -q -p ncp-core --features schema --bin gen-schemas -- \
    "$tmp_dir/schemas-fresh"
diff -ru -x README.md "$tmp_dir/schemas-fresh" schemas

step "ACL authority model + verifier proof logic"
python3 scripts/check_acl_template.py
python3 scripts/verify_acl_deployment.py --self-test
python3 scripts/validate_security_profile.py --self-test
cargo run --quiet -p ncp-core --bin validate-plant-profile -- deploy/plant-profiles/*.json

step "version metadata coherence"
scripts/check-version-coherence.sh --self-test
scripts/check-version-coherence.sh

step "Rust crate archive self-containment"
python3 scripts/check_rust_packages.py --self-test
python3 scripts/check_rust_packages.py --offline
python3 scripts/build_candidate_dossier.py --self-test

step "dependency, license, and source policy"
python3 scripts/check_dependency_exposure.py --self-test
if ! cargo deny --version >/dev/null 2>&1; then
    printf 'cargo-deny is required; install it with: cargo install cargo-deny --locked\n' >&2
    exit 1
fi
if [[ "$(cargo deny --version)" != "cargo-deny 0.19.9" ]]; then
    printf 'cargo-deny 0.19.9 is required; found: %s\n' "$(cargo deny --version)" >&2
    exit 1
fi
export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"
export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
current_advisory_home="$tmp_dir/advisory-current-home"
pinned_advisory_home="$tmp_dir/advisory-pinned-home"
mkdir -p "$current_advisory_home" "$pinned_advisory_home"
export NCP_CURRENT_ADVISORY_DB_PATH="$current_advisory_home/.cargo/advisory-dbs"
python3 scripts/prepare_current_advisory_database.py --self-test
python3 scripts/prepare_current_advisory_database.py \
    --destination "$NCP_CURRENT_ADVISORY_DB_PATH" \
    --receipt "$tmp_dir/current-advisory-database-receipt.v1.json"
HOME="$current_advisory_home" \
    cargo deny --locked --offline --all-features check --disable-fetch
HOME="$current_advisory_home" \
    python3 scripts/generate_supply_chain_evidence.py \
        --validate-current-advisories
find "$current_advisory_home/.cargo/advisory-dbs" \
    -mindepth 1 -maxdepth 1 -type d -name 'advisory-db-*' -print \
    > "$tmp_dir/current-advisory-databases"
if [[ "$(wc -l < "$tmp_dir/current-advisory-databases" | tr -d ' ')" != "1" ]]; then
    printf 'current advisory scan did not prepare exactly one database\n' >&2
    exit 1
fi
current_advisory_database="$(sed -n '1p' "$tmp_dir/current-advisory-databases")"
export NCP_ADVISORY_DB_PATH="$pinned_advisory_home/.cargo/advisory-dbs"
python3 scripts/prepare_advisory_database.py \
    --source-database "$current_advisory_database" \
    --destination "$NCP_ADVISORY_DB_PATH"
HOME="$pinned_advisory_home" \
    cargo deny --locked --offline --all-features check --disable-fetch
HOME="$pinned_advisory_home" \
    python3 scripts/generate_supply_chain_evidence.py --self-test --check

step "repo-less exact-commit candidate preflight"
export NCP_PINNED_ADVISORY_HOME="$pinned_advisory_home"
python3 scripts/build_candidate_dossier.py \
    --archive-preflight "$(git rev-parse HEAD)"

step "protobuf lint + build"
buf lint
buf build

printf '\nNCP LOCAL PREFLIGHT PASSED — EXTERNAL RELEASE GATES REMAIN NOT RUN\n'
