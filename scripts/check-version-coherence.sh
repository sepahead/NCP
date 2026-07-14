#!/usr/bin/env bash
# check-version-coherence.sh — assert this repo's release version is coherent
# across every place it is recorded, and (optionally) that a release tag points
# at the commit it claims to.
#
# READ-ONLY: this script never writes to the repo, runs no builds, and performs
# no network calls. It only reads tracked files and (for the optional tag check)
# the local git object database.
#
# What "coherent" means here:
#   - the Cargo workspace package version (Cargo.toml [workspace.package].version,
#     falling back to [package].version for a single-crate repo)
#   - both root and ncp-ts npm package.json versions
#   - the ncp-core/ncp-zenoh workspace path-dependency version pins
#   - the CITATION.cff "version"
#   must all be byte-equal. A release that bumps one but forgets another is the
#   classic "moved tag / stale metadata" footgun this guard exists to catch.
#   - generated Rust/TypeScript normative digests must agree, and every checked-in
#     TypeScript source/runtime/declaration plus the Rust default must retain the
#     non-certifying `unreleased-worktree` build identity. Exact revision injection
#     happens only in the isolated release builder.
#
# With an optional <tag> argument it additionally asserts:
#   - the ref is an annotated tag object (lightweight release tags are rejected)
#     and peels cleanly to a commit. Historical immutability itself is enforced by
#     remote tag protection; Git stores no prior ref target for a local script to
#     compare after a move.
#   - the version embedded in the tag name (the numeric part of e.g. v0.2.8)
#     equals the coherent in-tree version, so no lockfile/manifest disagrees
#     with the tag.
#
# Usage:
#   scripts/check-version-coherence.sh [--self-test] [tag]
#
# Exit codes: 0 = coherent; 1 = mismatch / missing required file; 2 = bad usage.

set -euo pipefail

usage() {
  cat <<'EOF'
check-version-coherence.sh — assert release-version coherence (read-only).

Usage:
  check-version-coherence.sh [--self-test] [tag]

  tag   Optional. A release tag (e.g. v0.2.8). When given, the script also
        verifies the tag peels to the commit it points at (no moved tag) and
        that the tag's version matches the in-tree version.

With no tag, the script only asserts internal coherence at HEAD.

Exit codes: 0 = coherent; 1 = mismatch / missing required file; 2 = bad usage.
EOF
}

TAG=""
SELF_TEST=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --self-test) SELF_TEST=1 ;;
    -*)        echo "ERROR: unknown option '$arg'" >&2; echo >&2; usage >&2; exit 2 ;;
    *)
      if [[ -n "$TAG" ]]; then
        echo "ERROR: too many arguments" >&2; echo >&2; usage >&2; exit 2
      fi
      TAG="$arg" ;;
  esac
done

release_tag_matches_version() {
  [[ "$1" == "v$2" ]]
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- version extractors (read-only; first match wins) -----------------------

# Cargo: prefer the workspace package version, else a single-crate [package].
# We look in the repo-root Cargo.toml first, then src-tauri/Cargo.toml (Tauri
# apps keep the crate manifest there).
cargo_version() {
  local f
  for f in "$REPO_ROOT/Cargo.toml" "$REPO_ROOT/src-tauri/Cargo.toml"; do
    [[ -f "$f" ]] || continue
    # Pull version from [workspace.package] or [package], whichever appears.
    awk '
      /^\[workspace\.package\]/ { sec="wp"; next }
      /^\[package\]/            { sec="pkg"; next }
      /^\[/                     { sec="" ; next }
      (sec=="wp" || sec=="pkg") && /^[[:space:]]*version[[:space:]]*=/ {
        line=$0
        sub(/^[^=]*=[[:space:]]*/, "", line)
        gsub(/["\x27]/, "", line)        # strip both " and '"'"'
        sub(/[[:space:]].*$/, "", line)  # drop trailing comment/space
        print line
        exit
      }
    ' "$f"
    return
  done
}

# npm: package.json "version": "x.y.z"
npm_version() {
  local f="$REPO_ROOT/package.json"
  [[ -f "$f" ]] || return
  awk -F'"' '/^[[:space:]]*"version"[[:space:]]*:/ { print $4; exit }' "$f"
}

ncp_ts_npm_version() {
  local f="$REPO_ROOT/ncp-ts/package.json"
  [[ -f "$f" ]] || return
  awk -F'"' '/^[[:space:]]*"version"[[:space:]]*:/ { print $4; exit }' "$f"
}

workspace_dep_version() {
  local dep="$1" f="$REPO_ROOT/Cargo.toml"
  [[ -f "$f" ]] || return
  DEP="$dep" perl -ne '
    if (/^\s*\Q$ENV{DEP}\E\s*=.*\bversion\s*=\s*"([^"]+)"/) {
      print "$1\n";
      exit;
    }
  ' "$f"
}

# CITATION.cff: a top-level `version:` key. Values may be quoted or bare.
cff_version() {
  local f="$REPO_ROOT/CITATION.cff"
  [[ -f "$f" ]] || return
  awk '
    /^version[[:space:]]*:/ {
      line=$0
      sub(/^version[[:space:]]*:[[:space:]]*/, "", line)
      gsub(/["\x27]/, "", line)
      sub(/[[:space:]]*#.*$/, "", line)
      sub(/[[:space:]]+$/, "", line)
      print line
      exit
    }
  ' "$f"
}

json_candidate() {
  local f="$1"
  [[ -f "$f" && ! -L "$f" ]] || return
  python3 - "$f" <<'PY'
import json
import sys

def no_duplicates(pairs):
    value = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(f"duplicate key {key!r}")
        value[key] = member
    return value

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle, object_pairs_hook=no_duplicates)
candidate = value.get("candidate")
if not isinstance(candidate, str) or not candidate:
    raise SystemExit(1)
print(candidate)
PY
}

# README.md citation block: a `version = {x.y.z}` line inside the bibtex example.
# This is documentation a user copies verbatim, so a stale value here misleads
# every downstream citation — exactly the drift this guard exists to catch.
readme_bibtex_version() {
  local f="$REPO_ROOT/README.md"
  [[ -f "$f" ]] || return
  awk '
    /^[[:space:]]*version[[:space:]]*=[[:space:]]*\{/ {
      line=$0
      sub(/^[^{]*\{/, "", line)   # drop up to the opening brace
      sub(/\}.*$/, "", line)      # drop the closing brace and trailing
      gsub(/[[:space:]]/, "", line)
      print line
      exit
    }
  ' "$f"
}

CARGO_VER="$(cargo_version || true)"
NPM_VER="$(npm_version || true)"
NCP_TS_NPM_VER="$(ncp_ts_npm_version || true)"
NCP_CORE_DEP_VER="$(workspace_dep_version ncp-core || true)"
NCP_ZENOH_DEP_VER="$(workspace_dep_version ncp-zenoh || true)"
CFF_VER="$(cff_version || true)"
README_VER="$(readme_bibtex_version || true)"
SURFACE_CANDIDATE="$(json_candidate "$REPO_ROOT/contract/surface.v1.json" 2>/dev/null || true)"
GATES_CANDIDATE="$(json_candidate "$REPO_ROOT/contract/release-gates.v1.json" 2>/dev/null || true)"
MANIFEST_CANDIDATE="$(json_candidate "$REPO_ROOT/contract/manifest.v1.json" 2>/dev/null || true)"

echo "Version coherence (repo: $REPO_ROOT)"
echo
printf '  %-22s %s\n' "Cargo (workspace/pkg)" "${CARGO_VER:-<not present>}"
printf '  %-22s %s\n' "npm (package.json)"     "${NPM_VER:-<not present>}"
printf '  %-22s %s\n' "npm (ncp-ts)"           "${NCP_TS_NPM_VER:-<not present>}"
printf '  %-22s %s\n' "dep pin (ncp-core)"      "${NCP_CORE_DEP_VER:-<not present>}"
printf '  %-22s %s\n' "dep pin (ncp-zenoh)"     "${NCP_ZENOH_DEP_VER:-<not present>}"
printf '  %-22s %s\n' "CITATION.cff"           "${CFF_VER:-<not present>}"
printf '  %-22s %s\n' "README bibtex"          "${README_VER:-<not present>}"
printf '  %-22s %s\n' "surface candidate"      "${SURFACE_CANDIDATE:-<not present>}"
printf '  %-22s %s\n' "gate candidate"         "${GATES_CANDIDATE:-<not present>}"
printf '  %-22s %s\n' "manifest candidate"     "${MANIFEST_CANDIDATE:-<not present>}"
echo

problems=()

[[ -f "$REPO_ROOT/ncp-ts/package.json" && -z "$NCP_TS_NPM_VER" ]] && \
  problems+=("ncp-ts/package.json exists but has no readable version")
[[ -f "$REPO_ROOT/Cargo.toml" && -z "$NCP_CORE_DEP_VER" ]] && \
  problems+=("Cargo.toml has no readable ncp-core path-dependency version pin")
[[ -f "$REPO_ROOT/Cargo.toml" && -z "$NCP_ZENOH_DEP_VER" ]] && \
  problems+=("Cargo.toml has no readable ncp-zenoh path-dependency version pin")

# Collect the versions that are actually present; require at least one source
# of truth and that all present sources agree.
present_labels=()
present_values=()
[[ -n "$CARGO_VER" ]] && { present_labels+=("Cargo"); present_values+=("$CARGO_VER"); }
[[ -n "$NPM_VER"   ]] && { present_labels+=("npm");   present_values+=("$NPM_VER"); }
[[ -n "$NCP_TS_NPM_VER" ]] && { present_labels+=("ncp-ts npm"); present_values+=("$NCP_TS_NPM_VER"); }
[[ -n "$NCP_CORE_DEP_VER" ]] && { present_labels+=("ncp-core dep pin"); present_values+=("$NCP_CORE_DEP_VER"); }
[[ -n "$NCP_ZENOH_DEP_VER" ]] && { present_labels+=("ncp-zenoh dep pin"); present_values+=("$NCP_ZENOH_DEP_VER"); }
[[ -n "$CFF_VER"   ]] && { present_labels+=("CITATION.cff"); present_values+=("$CFF_VER"); }
[[ -n "$README_VER" ]] && { present_labels+=("README bibtex"); present_values+=("$README_VER"); }

if [[ "${#present_values[@]}" -eq 0 ]]; then
  echo "ERROR: no version source found (no Cargo.toml / package.json / CITATION.cff version)" >&2
  exit 1
fi

CANON="${present_values[0]}"
for i in "${!present_values[@]}"; do
  if [[ "${present_values[$i]}" != "$CANON" ]]; then
    problems+=("${present_labels[$i]} version '${present_values[$i]}' != '${CANON}' (${present_labels[0]})")
  fi
done

for label_and_value in \
  "contract surface:$SURFACE_CANDIDATE" \
  "release-gate registry:$GATES_CANDIDATE" \
  "normative manifest:$MANIFEST_CANDIDATE"; do
  label="${label_and_value%%:*}"
  value="${label_and_value#*:}"
  if [[ -z "$value" ]]; then
    problems+=("$label has no readable candidate identity")
  elif [[ "$value" != "$CANON" ]]; then
    problems+=("$label candidate '$value' != coherent package version '$CANON'")
  fi
done

SEMVER_RE='^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-([0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*))?(\+[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?$'
PACKAGE_WIRE=""
if [[ "$CANON" =~ $SEMVER_RE ]]; then
  PACKAGE_WIRE="${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
  prerelease="${BASH_REMATCH[5]:-}"
  if [[ -n "$prerelease" ]]; then
    IFS='.' read -r -a prerelease_parts <<< "$prerelease"
    for identifier in "${prerelease_parts[@]}"; do
      if [[ "$identifier" =~ ^[0-9]+$ && "$identifier" != "0" && "$identifier" == 0* ]]; then
        problems+=("coherent package version '$CANON' has a noncanonical numeric prerelease identifier")
      fi
    done
  fi
else
  problems+=("coherent package version '$CANON' is not canonical SemVer")
fi

# --- wire-version coherence (separate axis from SDK semver) ------------------
# The ncp_version *wire* string (e.g. "0.3") is bumped in BOTH the Rust reference
# (ncp-core) and the TypeScript peer (ncp-ts); a release that bumps one but not the
# other ships peers that fail-closed-reject each other (the exact drift that left
# ncp-ts at "0.2" after the 0.3 wire bump). Assert they agree when both are present.
core_wire() {
  local f="$REPO_ROOT/ncp-core/src/messages.rs"
  [[ -f "$f" ]] || return
  grep -m1 -oE 'NCP_VERSION: &str = "[^"]+"' "$f" | grep -oE '"[^"]+"' | tr -d '"'
}
ts_wire() {
  local f="$REPO_ROOT/ncp-ts/src/client.ts"
  [[ -f "$f" ]] || return
  grep -m1 -oE "NCP_VERSION = '[^']+'" "$f" | grep -oE "'[^']+'" | tr -d "'"
}
# The language-neutral behavior corpus is the SINGLE cross-language source of wire
# truth (ncp-core/tests/behavior_conformance.rs and the Python/TS replays pin their
# constants to it). Assert it agrees with the Rust + TS constants here too, so a
# release that bumps a peer but not the corpus (or vice versa) is caught.
corpus_wire() {
  local f="$REPO_ROOT/conformance/behavior/vectors.json"
  [[ -f "$f" ]] || return
  grep -m1 -oE '"ncp_version"[[:space:]]*:[[:space:]]*"[^"]+"' "$f" | grep -oE '"[^"]+"$' | tr -d '"'
}
CORE_WIRE="$(core_wire || true)"
TS_WIRE="$(ts_wire || true)"
CORPUS_WIRE="$(corpus_wire || true)"
if [[ -n "$CORE_WIRE" ]]; then
  printf '  %-22s %s\n' "wire (ncp-core)" "$CORE_WIRE"
  [[ -n "$TS_WIRE" ]] && printf '  %-22s %s\n' "wire (ncp-ts)" "$TS_WIRE"
  [[ -n "$CORPUS_WIRE" ]] && printf '  %-22s %s\n' "wire (corpus)" "$CORPUS_WIRE"
  if [[ -n "$TS_WIRE" && "$TS_WIRE" != "$CORE_WIRE" ]]; then
    problems+=("ncp-ts wire NCP_VERSION '$TS_WIRE' != ncp-core '$CORE_WIRE'")
  fi
  if [[ -n "$CORPUS_WIRE" && "$CORPUS_WIRE" != "$CORE_WIRE" ]]; then
    problems+=("behavior corpus ncp_version '$CORPUS_WIRE' != ncp-core '$CORE_WIRE'")
  fi
  if [[ -n "$PACKAGE_WIRE" && "$CORE_WIRE" != "$PACKAGE_WIRE" ]]; then
    problems+=("ncp-core wire NCP_VERSION '$CORE_WIRE' != package major.minor '$PACKAGE_WIRE'")
  fi
fi

# --- CONTRACT_HASH coherence across the bindings ----------------------------
# Every peer pins the same CONTRACT_HASH constant (cross-language anchor; each
# recomputes it from its own proto in CI). A release that bumps one but not the
# others ships peers that log spurious contract-mismatch advisories. Assert the
# Rust (ncp-core) and TS (ncp-ts) constants agree when both are present.
core_hash() {
  local f="$REPO_ROOT/ncp-core/src/messages.rs"
  [[ -f "$f" ]] || return
  grep -m1 -oE 'CONTRACT_HASH: &str = "[^"]+"' "$f" | grep -oE '"[^"]+"' | tr -d '"'
}
ts_hash() {
  local f="$REPO_ROOT/ncp-ts/src/client.ts"
  [[ -f "$f" ]] || return
  grep -m1 -oE "NCP_CONTRACT_HASH = '[^']+'" "$f" | grep -oE "'[^']+'" | tr -d "'"
}
corpus_hash() {
  local f="$REPO_ROOT/conformance/behavior/vectors.json"
  [[ -f "$f" ]] || return
  grep -m1 -oE '"contract_hash"[[:space:]]*:[[:space:]]*"[^"]+"' "$f" | grep -oE '"[^"]+"$' | tr -d '"'
}
CORE_HASH="$(core_hash || true)"
TS_HASH="$(ts_hash || true)"
CORPUS_HASH="$(corpus_hash || true)"
if [[ -n "$CORE_HASH" ]]; then
  printf '  %-22s %s\n' "CONTRACT_HASH (core)" "$CORE_HASH"
  [[ -n "$TS_HASH" ]] && printf '  %-22s %s\n' "CONTRACT_HASH (ts)" "$TS_HASH"
  [[ -n "$CORPUS_HASH" ]] && printf '  %-22s %s\n' "CONTRACT_HASH (corpus)" "$CORPUS_HASH"
  if [[ -n "$TS_HASH" && "$TS_HASH" != "$CORE_HASH" ]]; then
    problems+=("ncp-ts NCP_CONTRACT_HASH '$TS_HASH' != ncp-core '$CORE_HASH'")
  fi
  if [[ -n "$CORPUS_HASH" && "$CORPUS_HASH" != "$CORE_HASH" ]]; then
    problems+=("behavior corpus contract_hash '$CORPUS_HASH' != ncp-core '$CORE_HASH'")
  fi
fi

# --- complete normative-contract identity ----------------------------------
# CONTRACT_HASH above covers only the compact protobuf surface. Installable
# peers also expose the SHA-256 of the complete normative source set. Require
# both generated bindings to match the generated language-neutral manifest so
# package introspection can never silently report a stale contract identity.
core_normative_digest() {
  local f="$REPO_ROOT/ncp-core/src/contract_identity.rs"
  [[ -f "$f" ]] || return
  awk '
    /^pub const NORMATIVE_CONTRACT_DIGEST:/ { in_constant=1 }
    in_constant { print }
    in_constant && /;/ { exit }
  ' "$f" | grep -m1 -oE '[0-9a-f]{64}'
}
ts_normative_digest() {
  local f="$REPO_ROOT/ncp-ts/src/contract-identity.ts"
  [[ -f "$f" ]] || return
  awk -F"'" '/^export const NCP_NORMATIVE_CONTRACT_DIGEST =/ { print $2; exit }' "$f"
}
manifest_normative_digest() {
  local f="$REPO_ROOT/contract/manifest.v1.json"
  [[ -f "$f" ]] || return
  awk -F'"' '/"contract_digest_sha256"[[:space:]]*:/ { print $4; exit }' "$f"
}
ts_identity_package_version() {
  local f="$REPO_ROOT/ncp-ts/src/contract-identity.ts"
  [[ -f "$f" ]] || return
  awk -F"'" '/^export const NCP_PACKAGE_VERSION =/ { print $2; exit }' "$f"
}
core_build_identity_default() {
  local f="$REPO_ROOT/ncp-core/src/contract_identity.rs"
  [[ -f "$f" ]] || return
  awk -F'"' '/None =>/ { print $2; exit }' "$f"
}
ts_build_identity_default() {
  local f="$REPO_ROOT/ncp-ts/src/contract-identity.ts"
  [[ -f "$f" ]] || return
  awk -F"'" '/^export const NCP_BUILD_IDENTITY =/ { print $2; exit }' "$f"
}
ts_dist_build_identity() {
  local f="$REPO_ROOT/ncp-ts/dist/contract-identity.js"
  [[ -f "$f" ]] || return
  awk -F"'" '/^export const NCP_BUILD_IDENTITY =/ { print $2; exit }' "$f"
}
ts_declaration_build_identity() {
  local f="$REPO_ROOT/ncp-ts/dist/contract-identity.d.ts"
  [[ -f "$f" ]] || return
  awk -F'"' '/^export declare const NCP_BUILD_IDENTITY =/ { print $2; exit }' "$f"
}

CORE_NORMATIVE_DIGEST="$(core_normative_digest || true)"
TS_NORMATIVE_DIGEST="$(ts_normative_digest || true)"
MANIFEST_NORMATIVE_DIGEST="$(manifest_normative_digest || true)"
TS_IDENTITY_PACKAGE_VER="$(ts_identity_package_version || true)"
CORE_BUILD_IDENTITY_DEFAULT="$(core_build_identity_default || true)"
TS_BUILD_IDENTITY_DEFAULT="$(ts_build_identity_default || true)"
TS_DIST_BUILD_IDENTITY="$(ts_dist_build_identity || true)"
TS_DECLARATION_BUILD_IDENTITY="$(ts_declaration_build_identity || true)"

printf '  %-22s %s\n' "full digest (core)" "${CORE_NORMATIVE_DIGEST:-<not present>}"
printf '  %-22s %s\n' "full digest (ts)" "${TS_NORMATIVE_DIGEST:-<not present>}"
printf '  %-22s %s\n' "full digest (manifest)" "${MANIFEST_NORMATIVE_DIGEST:-<not present>}"
printf '  %-22s %s\n' "build identity (core)" "${CORE_BUILD_IDENTITY_DEFAULT:-<not present>}"
printf '  %-22s %s\n' "build identity (ts)" "${TS_BUILD_IDENTITY_DEFAULT:-<not present>}"
printf '  %-22s %s\n' "build identity (dist)" "${TS_DIST_BUILD_IDENTITY:-<not present>}"
printf '  %-22s %s\n' "build identity (.d.ts)" "${TS_DECLARATION_BUILD_IDENTITY:-<not present>}"

for label_and_value in \
  "ncp-core generated digest:$CORE_NORMATIVE_DIGEST" \
  "ncp-ts generated digest:$TS_NORMATIVE_DIGEST" \
  "normative contract manifest digest:$MANIFEST_NORMATIVE_DIGEST"; do
  label="${label_and_value%%:*}"
  value="${label_and_value#*:}"
  if [[ ! "$value" =~ ^[0-9a-f]{64}$ ]]; then
    problems+=("$label is missing or is not a lowercase 64-hex SHA-256")
  fi
done
if [[ -n "$CORE_NORMATIVE_DIGEST" && -n "$TS_NORMATIVE_DIGEST" \
   && "$CORE_NORMATIVE_DIGEST" != "$TS_NORMATIVE_DIGEST" ]]; then
  problems+=("ncp-ts full normative digest '$TS_NORMATIVE_DIGEST' != ncp-core '$CORE_NORMATIVE_DIGEST'")
fi
if [[ -n "$CORE_NORMATIVE_DIGEST" && -n "$MANIFEST_NORMATIVE_DIGEST" \
   && "$CORE_NORMATIVE_DIGEST" != "$MANIFEST_NORMATIVE_DIGEST" ]]; then
  problems+=("contract manifest full digest '$MANIFEST_NORMATIVE_DIGEST' != ncp-core '$CORE_NORMATIVE_DIGEST'")
fi
if [[ "$TS_IDENTITY_PACKAGE_VER" != "$CANON" ]]; then
  problems+=("ncp-ts generated package identity '$TS_IDENTITY_PACKAGE_VER' != coherent package version '$CANON'")
fi
for label_and_value in \
  "ncp-core generated default:$CORE_BUILD_IDENTITY_DEFAULT" \
  "ncp-ts generated source:$TS_BUILD_IDENTITY_DEFAULT" \
  "ncp-ts runtime dist:$TS_DIST_BUILD_IDENTITY" \
  "ncp-ts declaration dist:$TS_DECLARATION_BUILD_IDENTITY"; do
  label="${label_and_value%%:*}"
  value="${label_and_value#*:}"
  if [[ "$value" != "unreleased-worktree" ]]; then
    problems+=("$label must retain the checked-in non-certifying 'unreleased-worktree' sentinel (got '$value')")
  fi
done

# --- optional tag check -----------------------------------------------------
if [[ -n "$TAG" ]]; then
  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERROR: not inside a git work tree; cannot check tag '$TAG'" >&2
    exit 1
  fi
  if ! release_tag_matches_version "$TAG" "$CANON"; then
    problems+=("release tag must be exactly 'v$CANON'; got '$TAG'")
  fi
  if ! git -C "$REPO_ROOT" rev-parse -q --verify "refs/tags/$TAG" >/dev/null 2>&1; then
    problems+=("tag '$TAG' does not exist in this repository")
  else
    tag_type="$(git -C "$REPO_ROOT" cat-file -t "refs/tags/$TAG" 2>/dev/null || true)"
    if [[ "$tag_type" != "tag" ]]; then
      problems+=("tag '$TAG' is '$tag_type', not an annotated tag object")
    fi
    # The ref as it stands (for an annotated tag this is the tag OBJECT sha).
    ref_target="$(git -C "$REPO_ROOT" rev-parse "refs/tags/$TAG" 2>/dev/null || true)"
    # Peel to the commit it ultimately names.
    peeled_commit="$(git -C "$REPO_ROOT" rev-parse "refs/tags/${TAG}^{commit}" 2>/dev/null || true)"
    # What the tag ref points to, peeled the same way via the ref object.
    deref_commit="$(git -C "$REPO_ROOT" rev-list -n1 "refs/tags/${TAG}^{commit}" 2>/dev/null || true)"
    head_commit="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true)"
    tag_payload="$(git -C "$REPO_ROOT" cat-file -p "refs/tags/$TAG" 2>/dev/null || true)"
    direct_object="$(printf '%s\n' "$tag_payload" | awk '/^object / { print $2; exit }')"
    direct_type="$(printf '%s\n' "$tag_payload" | awk '/^type / { print $2; exit }')"
    embedded_tag="$(printf '%s\n' "$tag_payload" | awk '/^tag / { sub(/^tag /, ""); print; exit }')"

    echo "  tag '$TAG':"
    printf '    ref target       %s\n' "$ref_target"
    printf '    peeled commit    %s\n' "$peeled_commit"
    echo

    if [[ "$peeled_commit" != "$deref_commit" ]]; then
      problems+=("tag '$TAG' peels inconsistently ($peeled_commit vs $deref_commit) — moved/corrupt tag")
    fi
    if [[ -z "$peeled_commit" || ! "$peeled_commit" =~ ^[0-9a-f]{40}$ ]]; then
      problems+=("tag '$TAG' does not peel to one lowercase 40-hex commit")
    elif [[ "$peeled_commit" != "$head_commit" ]]; then
      problems+=("tag '$TAG' peels to '$peeled_commit', not checked HEAD '$head_commit'")
    fi
    if [[ "$direct_type" != "commit" || "$direct_object" != "$head_commit" ]]; then
      problems+=("tag '$TAG' must directly name checked HEAD as a commit (no nested tag/object)")
    fi
    if [[ "$embedded_tag" != "$TAG" ]]; then
      problems+=("annotated tag object's embedded name '$embedded_tag' != ref label '$TAG'")
    fi
    if [[ -n "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all 2>/dev/null || true)" ]]; then
      problems+=("tag verification requires a clean worktree/index including no untracked files")
    fi
  fi
fi

if [[ "$SELF_TEST" -eq 1 ]]; then
  release_tag_matches_version "v1.0.0-rc.1" "1.0.0-rc.1" || {
    problems+=("internal tag-label self-test rejected an exact release label")
  }
  for hostile in release-1.0.0 ncp-v1.0.0 v1.0.0-extra v01.0.0; do
    if release_tag_matches_version "$hostile" "1.0.0"; then
      problems+=("internal tag-label self-test accepted '$hostile'")
    fi
  done
fi

if [[ "${#problems[@]}" -ne 0 ]]; then
  echo "MISMATCH:" >&2
  for p in "${problems[@]}"; do
    echo "  - $p" >&2
  done
  exit 1
fi

if [[ -n "$TAG" ]]; then
  echo "OK: versions coherent at '$CANON' and tag '$TAG' is consistent"
else
  if [[ "$SELF_TEST" -eq 1 ]]; then
    echo "OK: versions coherent at '$CANON'; hostile tag-label self-test passed"
  else
    echo "OK: versions coherent at '$CANON'"
  fi
fi
