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

step "bounded pure-Python line ingress + runner status"
python3 -m unittest -v e2e.test_bounded_json e2e.test_runner_status
python3 -m py_compile \
    e2e/bounded_json.py e2e/nest_five_networks.py \
    e2e/run_cross_language_e2e.py e2e/test_bounded_json.py \
    e2e/test_runner_status.py

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
"$tmp_dir/venv/bin/maturin" build -m ncp-python/Cargo.toml \
    --features extension-module --locked --out "$tmp_dir/wheels"
"$tmp_dir/venv/bin/python" -m pip install --disable-pip-version-check \
    --no-index --find-links "$tmp_dir/wheels" ncp
NCP_REQUIRE_BINDING=1 "$tmp_dir/venv/bin/python" scripts/check_behavior_vectors.py
"$tmp_dir/venv/bin/python" -m pytest ncp-python/tests -q

step "TypeScript generated source + prebuilt dist are reproducible"
git diff --binary -- ncp-core/bindings ncp-ts/src/generated ncp-ts/dist \
    > "$tmp_dir/ts-before.diff"
bun install --frozen-lockfile
bun run regen
git diff --binary -- ncp-core/bindings ncp-ts/src/generated ncp-ts/dist \
    > "$tmp_dir/ts-after.diff"
cmp "$tmp_dir/ts-before.diff" "$tmp_dir/ts-after.diff"
bun run check:behavior
bun run check:ws
bun run check:package

step "handoff, proto, schema, JSON/binary corpus, and wire baselines"
python3 scripts/check_handoff_review.py --self-test
python3 scripts/generate_max_effort_handoff_index.py --self-test
python3 scripts/check_max_effort_handoff_review.py --self-test
python3 scripts/generate_max_effort_review_template.py --check
python3 scripts/generate_file_review_ledger.py --self-test
python3 scripts/generate_file_review_ledger.py --check
python3 scripts/plot_perf.py --self-test --check
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
python3 scripts/check_rust_packages.py --offline

step "dependency, license, and source policy"
python3 scripts/check_dependency_exposure.py --self-test
if cargo deny --version >/dev/null 2>&1; then
    cargo deny check
else
    printf 'cargo-deny is required; install it with: cargo install cargo-deny --locked\n' >&2
    exit 1
fi

step "protobuf lint + build"
buf lint
buf build

printf '\nNCP LOCAL PREFLIGHT PASSED — EXTERNAL RELEASE GATES REMAIN NOT RUN\n'
