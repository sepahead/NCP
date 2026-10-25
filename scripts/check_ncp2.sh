#!/bin/sh
# The local gate of NCP 2 (spec/NCP-2.md). The CI workflow .github/workflows/ncp2.yml runs it too.
#
# Usage: scripts/check_ncp2.sh [--quick]
# PYTHON names the interpreter to test (default python3; NCP 2 needs Python 3.11 or later).
# --quick runs 2,000 model traces and 20,000 fuzzing cases instead of 20,000 and 200,000.
# NCP2_SKIP_LEAN=1 leaves out the Lean proofs and the Lean oracle (they need elan and lake).
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

echo "== Bounded model check of owner, client, and network, with its mutation test"
"$python" -I model/ncp2_model.py --self-test

echo "== Model conformance of both owners, $traces traces each"
"$python" -I model/conformance.py --traces "$traces"
# One connection per trace: a Unix domain socket, because TCP would run out of ephemeral ports.
"$python" -I model/conformance.py --traces "$traces" --owner "$examples/model_owner" "$work/owner.sock"

if [ "${NCP2_SKIP_LEAN:-0}" != "1" ]; then
    echo "== Lean proofs of the owner model, warnings fatal"
    (cd formal && lake build --wfail)
    echo "== Replay of every proof by the Lean kernel, outside the elaborator"
    (cd formal && lake env leanchecker --fresh Audit)
    echo "== Axiom audit: only propext, Classical.choice, and Quot.sound"
    (cd formal && lake env lean Audit.lean) > "$work/axioms.txt"
    cat "$work/axioms.txt"
    if grep -v -e "depends on axioms: \[" -e "does not depend on any axioms" "$work/axioms.txt" | grep -q . ||
        sed -n 's/.*depends on axioms: \[\(.*\)\]/\1/p' "$work/axioms.txt" | tr ',' '\n' |
        sed 's/ //g' | grep -qvxE 'propext|Classical.choice|Quot.sound'; then
        echo "axiom audit failed" >&2
        exit 1
    fi
    # Every claim of Statements.lean needs a theorem of exactly its type and an axiom report.
    claims=$(sed -n 's/^def \([A-Z][A-Za-z]*\) : Prop :=$/\1/p' formal/Statements.lean)
    for claim in $claims; do
        name="$(printf '%s' "${claim%"${claim#?}"}" | tr '[:upper:]' '[:lower:]')${claim#?}"
        if ! grep -qE "^theorem $name : $claim :=" formal/Audit.lean ||
            ! grep -qE "^'NCP2\.Audit\.$name' (depends on axioms|does not depend on any axioms)" "$work/axioms.txt"; then
            echo "claim $claim has no proof or no axiom report in Audit.lean" >&2
            exit 1
        fi
    done
    if [ "$(printf '%s\n' $claims | grep -c .)" -ne "$(grep -cE 'depends on axioms|does not depend on any axioms' "$work/axioms.txt")" ]; then
        echo "Audit.lean reports axioms for a theorem that is not a claim, or misses one" >&2
        exit 1
    fi
    echo "every claim of Statements.lean is proved and audited: $(printf '%s\n' $claims | grep -c .) claims"
    oracle="$root/formal/.lake/build/bin/ncp2-oracle"
    echo "== Both owners against the verified Lean model, $traces traces each"
    "$python" -I model/conformance.py --traces "$traces" --oracle "$oracle"
    "$python" -I model/conformance.py --traces "$traces" --oracle "$oracle" --owner "$examples/model_owner" "$work/oracle.sock"
    echo "== The traces detect each known defect of an owner"
    "$python" -I model/conformance.py --traces "$traces" --self-test --oracle "$oracle"
    echo "== The claims break under each defect of the owner model"
    (cd formal && "$python" -I mutants.py)
fi

echo "== Differential fuzzing of the decoders, $cases cases"
"$python" -I conformance/fuzz.py --decoder "$examples/decode_corpus" --cases "$cases"

echo "NCP 2 gate passed"
