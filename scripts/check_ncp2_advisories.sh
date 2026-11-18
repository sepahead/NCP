#!/bin/sh
# The advisory gate of NCP 2: cargo-deny checks the lockfiles of the Rust core crate
# (rust/Cargo.lock) and of the Rust Zenoh binding (bindings/zenoh/rust/Cargo.lock) against the
# RustSec advisory database, with the policies scripts/ncp2-deny-core.toml and
# scripts/ncp2-deny-zenoh.toml: advisories, licenses, banned features, and sources.
#
# The core has no exception. Each exception of the binding must match a package of its lockfile,
# and one of them holds only while Zenoh's compression is off: a self-test enables that feature
# in a copy of the binding's manifest and requires the policy to refuse it.
#
# The workflow .github/workflows/ncp2-advisories.yml runs this script on each change of a lockfile
# or a policy, and every week, because a new advisory can apply to a lockfile that did not change.
#
# Usage: scripts/check_ncp2_advisories.sh [--offline]
# Needs cargo-deny 0.19.9. Without --offline, cargo-deny first fetches the current database into
# $HOME/.cargo/advisory-dbs (needs the network); with --offline, it uses the database there and
# cargo resolves the lockfiles without the network.
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$root"

offline=""
case "${1:-}" in
    "") ;;
    --offline) offline="--offline" ;;
    *) echo "usage: scripts/check_ncp2_advisories.sh [--offline]" >&2; exit 2 ;;
esac

version=$(cargo deny --version)
if [ "$version" != "cargo-deny 0.19.9" ]; then
    echo "this gate needs cargo-deny 0.19.9, found: $version" >&2
    exit 1
fi

# deny MANIFEST POLICY LOG [fetch]: run every check of cargo-deny and keep its output in LOG.
# Only a call with "fetch", and not --offline, lets cargo-deny update the database first.
deny() {
    database_flag="--disable-fetch"
    [ "${4:-}" = fetch ] && [ -z "$offline" ] && database_flag=""
    # shellcheck disable=SC2086 # $offline and $database_flag are single flags or empty
    cargo deny --manifest-path "$1" --locked $offline --all-features \
        check --config "$root/$2" $database_flag >"$3" 2>&1
}

for crate in core zenoh; do
    case $crate in
        core) manifest=rust/Cargo.toml ;;
        zenoh) manifest=bindings/zenoh/rust/Cargo.toml ;;
    esac
    echo "== $manifest with scripts/ncp2-deny-$crate.toml"
    update=""
    [ $crate = core ] && update=fetch
    if ! deny "$manifest" "scripts/ncp2-deny-$crate.toml" "$work/$crate.txt" $update; then
        cat "$work/$crate.txt" >&2
        echo "the advisory gate failed for $manifest" >&2
        exit 1
    fi
    if grep -q "advisory-not-detected" "$work/$crate.txt"; then
        cat "$work/$crate.txt" >&2
        echo "an exception of scripts/ncp2-deny-$crate.toml matches no package of the lockfile: remove it" >&2
        exit 1
    fi
    grep "advisories ok" "$work/$crate.txt"
done

database=$(find "$HOME/.cargo/advisory-dbs" -mindepth 1 -maxdepth 1 -type d -name 'advisory-db-*' 2>/dev/null | head -n 1)
if [ -n "$database" ]; then
    echo "RustSec database revision: $(git -C "$database" rev-parse HEAD 2>/dev/null || echo unknown)"
fi

echo "== self-test: the binding's policy refuses Zenoh's compression"
# A copy of the binding's manifest that enables zenoh/transport_compression, beside links to its
# sources, its lockfile, and the core crate. Features are not in the lockfile, so it still holds.
mkdir -p "$work/tree/bindings/zenoh/rust"
ln -s "$root/rust" "$work/tree/rust"
for entry in Cargo.lock README.md src examples; do
    ln -s "$root/bindings/zenoh/rust/$entry" "$work/tree/bindings/zenoh/rust/$entry"
done
sed 's/features = \["transport_tcp", "transport_tls"\]/features = ["transport_tcp", "transport_tls", "transport_compression"]/' \
    bindings/zenoh/rust/Cargo.toml >"$work/tree/bindings/zenoh/rust/Cargo.toml"
if cmp -s bindings/zenoh/rust/Cargo.toml "$work/tree/bindings/zenoh/rust/Cargo.toml"; then
    echo "self-test: the Zenoh dependency of bindings/zenoh/rust/Cargo.toml changed; update the self-test" >&2
    exit 1
fi
if deny "$work/tree/bindings/zenoh/rust/Cargo.toml" scripts/ncp2-deny-zenoh.toml "$work/mutant.txt"; then
    echo "self-test failed: the binding's policy admits zenoh-transport/transport_compression" >&2
    exit 1
fi
if ! grep -q "feature-banned" "$work/mutant.txt" || ! grep -q "transport_compression" "$work/mutant.txt"; then
    cat "$work/mutant.txt" >&2
    echo "self-test failed: the policy refused the copy for another reason" >&2
    exit 1
fi
echo "the policy refuses zenoh-transport/transport_compression"

echo "NCP 2 advisory gate passed"
