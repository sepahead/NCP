#!/usr/bin/env python3
"""Generate or verify the complete NCP 1.0 normative contract manifest.

The manifest intentionally does not hash itself.  Its ``contract_digest_sha256``
is the SHA-256 of a domain-separated, length-prefixed stream containing every
normative source path and its exact bytes.  This avoids path/content boundary
ambiguity and makes the digest reproducible without JSON canonicalization.

The compact proto ``CONTRACT_HASH`` remains a different, wire-visible FNV-1a
compatibility signal.  It is recorded here, but it must never be presented as
the digest of the complete normative contract.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "contract" / "manifest.v1.json"
MESSAGES_RS = ROOT / "ncp-core" / "src" / "messages.rs"
CORE_IDENTITY = ROOT / "ncp-core" / "src" / "contract_identity.rs"
TS_IDENTITY = ROOT / "ncp-ts" / "src" / "contract-identity.ts"
DOMAIN = b"ncp.normative-contract.v1\x00"
SURFACE = ROOT / "contract" / "surface.v1.json"
RELEASE_GATES = ROOT / "contract" / "release-gates.v1.json"
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$",
    re.ASCII,
)
EXPECTED_SHIPPED_CANDIDATE_PACKAGES = [
    "ncp-core",
    "ncp-zenoh",
    "ncp-gateway",
    "ncp-python",
    "ncp-cpp",
    "@sepahead/ncp",
]


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _object_no_duplicates(pairs):
    value = {}
    for key, member in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def load_json(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected regular non-symlink JSON file: {relative(path)}")
    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_object_no_duplicates
    )


def wire_pins() -> tuple[str, str]:
    text = MESSAGES_RS.read_text(encoding="utf-8")
    version = re.search(r'NCP_VERSION:\s*&str\s*=\s*"([^"]+)"', text)
    wire_hash = re.search(r'CONTRACT_HASH:\s*&str\s*=\s*"([^"]+)"', text)
    if not version or not wire_hash:
        raise ValueError("could not read NCP_VERSION and CONTRACT_HASH")
    return version.group(1), wire_hash.group(1)


def package_version() -> str:
    manifest = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    version = manifest.get("workspace", {}).get("package", {}).get("version")
    if not isinstance(version, str):
        raise ValueError("Cargo.toml has no [workspace.package] section")
    match = SEMVER.fullmatch(version)
    if match is None:
        raise ValueError(f"workspace package version is not canonical SemVer: {version!r}")
    prerelease = match.group(4)
    if prerelease and any(
        member.isdigit() and len(member) > 1 and member.startswith("0")
        for member in prerelease.split(".")
    ):
        raise ValueError(f"workspace package prerelease has a leading zero: {version!r}")
    return version


def shipped_candidate_packages() -> list[str]:
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    packages: list[str] = []
    for member in workspace.get("workspace", {}).get("members", []):
        manifest_path = ROOT / member / "Cargo.toml"
        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        package = manifest.get("package", {})
        if package.get("publish") is False:
            continue
        name = package.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"publishable workspace member {member!r} has no package name")
        packages.append(name)

    root_npm = load_json(ROOT / "package.json")
    nested_npm = load_json(ROOT / "ncp-ts" / "package.json")
    npm_name = root_npm.get("name")
    if not isinstance(npm_name, str) or not npm_name:
        raise ValueError("root npm package has no name")
    if nested_npm.get("name") != npm_name:
        raise ValueError("root and ncp-ts npm package names disagree")
    candidate = package_version()
    if root_npm.get("version") != candidate or nested_npm.get("version") != candidate:
        raise ValueError(
            "root and ncp-ts npm versions must equal workspace package version "
            f"{candidate!r}"
        )
    packages.append(npm_name)
    return packages


def validate_candidate_documents(
    surface: dict, release_gates: dict, candidate: str, expected_packages: list[str]
) -> None:
    if surface.get("candidate") != candidate:
        raise ValueError(
            "contract/surface.v1.json candidate must equal the workspace package "
            f"version {candidate!r}; got {surface.get('candidate')!r}"
        )
    if release_gates.get("candidate") != candidate:
        raise ValueError(
            "contract/release-gates.v1.json candidate must equal the workspace package "
            f"version {candidate!r}; got {release_gates.get('candidate')!r}"
        )
    wire_version, _ = wire_pins()
    if surface.get("wire_version") != wire_version:
        raise ValueError(
            "contract/surface.v1.json wire_version must equal ncp-core NCP_VERSION "
            f"{wire_version!r}; got {surface.get('wire_version')!r}"
        )
    actual = surface.get("packages", {}).get("candidate")
    if actual != expected_packages:
        raise ValueError(
            "contract/surface.v1.json candidate packages must exactly equal the "
            "ordered shipped/publishable set "
            f"{expected_packages!r}; got {actual!r}"
        )


def validate_candidate_package_surface() -> None:
    expected = shipped_candidate_packages()
    if expected != EXPECTED_SHIPPED_CANDIDATE_PACKAGES:
        raise ValueError(
            "derived shipped/publishable package set changed; review and update "
            "EXPECTED_SHIPPED_CANDIDATE_PACKAGES explicitly: "
            f"expected {EXPECTED_SHIPPED_CANDIDATE_PACKAGES!r}, derived {expected!r}"
        )
    validate_candidate_documents(
        load_json(SURFACE), load_json(RELEASE_GATES), package_version(), expected
    )


def normative_paths() -> list[Path]:
    paths = [
        *sorted(
            path
            for path in (ROOT / "contract").glob("*.v1.json")
            if path != OUTPUT
        ),
        ROOT / "proto" / "ncp.proto",
        ROOT / "schemas" / "index.json",
        *sorted((ROOT / "schemas").glob("*.schema.json")),
        ROOT / "NEURO_CYBERNETIC_PROTOCOL.md",
        ROOT / "conformance" / "manifest.v1.json",
    ]
    missing = [
        relative(path)
        for path in paths
        if not path.is_file()
        or path.is_symlink()
        or ROOT.resolve() not in path.resolve().parents
    ]
    if missing:
        raise ValueError(f"missing normative source(s): {', '.join(missing)}")
    rels = [relative(path) for path in paths]
    if len(rels) != len(set(rels)):
        raise ValueError("normative source list contains a duplicate path")
    return sorted(paths, key=relative)


def contract_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(DOMAIN)
    for path in paths:
        name = relative(path).encode("utf-8")
        content = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def build_manifest() -> dict[str, object]:
    validate_candidate_package_surface()
    wire_version, wire_contract_hash = wire_pins()
    paths = normative_paths()
    sources = [
        {
            "path": relative(path),
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in paths
    ]
    return {
        "schema": "ncp.normative-contract-manifest.v1",
        "candidate": package_version(),
        "status": "candidate-unreleased-release-blocked",
        "wire_version": wire_version,
        "wire_proto_contract_hash_fnv1a64": wire_contract_hash,
        "contract_digest_algorithm": (
            "sha256(domain || repeated(u64be(path_bytes) || path_utf8 || "
            "u64be(content_bytes) || exact_content))"
        ),
        "contract_digest_domain_hex": DOMAIN.hex(),
        "contract_digest_sha256": contract_digest(paths),
        "normative_precedence": [
            "contract/*.v1.json except contract/manifest.v1.json "
            "(derived digest manifest)",
            "proto/ncp.proto",
            "schemas/index.json and schemas/*.schema.json",
            "NEURO_CYBERNETIC_PROTOCOL.md",
            "conformance/manifest.v1.json",
        ],
        "conflict_policy": (
            "Earlier entries take precedence; any conflict is a release-blocking "
            "contract defect and implementations must fail closed."
        ),
        "normative_sources": sources,
        "informative_implementations": [
            "ncp-core",
            "ncp-zenoh",
            "ncp-python",
            "ncp-cpp",
            "ncp-ts",
            "ncp-gateway",
        ],
        "generated_by": "scripts/generate_contract_manifest.py",
    }


def identity_outputs(manifest: dict[str, object]) -> dict[Path, str]:
    digest = str(manifest["contract_digest_sha256"])
    candidate = package_version()
    core = f'''//! Generated by `scripts/generate_contract_manifest.py`; do not edit by hand.
//!
//! These are implementation/package identity pins, not additional normative
//! sources (which would create a self-referential contract digest).

/// This crate's installable package version.
pub const PACKAGE_VERSION: &str = env!("CARGO_PKG_VERSION");

/// SHA-256 of the complete normative source set in `contract/manifest.v1.json`.
pub const NORMATIVE_CONTRACT_DIGEST: &str =
    "{digest}";

/// Build/source identity supplied by the immutable release builder. The checked-in
/// RC default is deliberately non-certifying and must not be presented as a commit.
/// A raw `NCP_BUILD_IDENTITY` compiler input is not validation or provenance; only
/// the fail-closed release builder validates and binds an exact source revision.
pub const BUILD_IDENTITY: &str = match option_env!("NCP_BUILD_IDENTITY") {{
    Some(identity) => identity,
    None => "unreleased-worktree",
}};

#[cfg(test)]
mod tests {{
    #[test]
    fn build_identity_matches_release_builder_expectation() {{
        let expected = option_env!("NCP_EXPECTED_BUILD_IDENTITY").unwrap_or("unreleased-worktree");
        assert_eq!(super::BUILD_IDENTITY, expected);
    }}
}}
'''
    # Deliberately do not accept an environment variable or CLI override here.
    # Ordinary regeneration must reproduce the checked-in non-certifying sentinel;
    # `ncp-ts/scripts/build-release.mjs` injects only into an exact archived commit.
    ts = f'''// Generated by scripts/generate_contract_manifest.py; do not edit by hand.
// Package/build identity is informative and deliberately outside the normative digest.
export const NCP_PACKAGE_VERSION = '{candidate}'
export const NCP_NORMATIVE_CONTRACT_DIGEST = '{digest}'
export const NCP_BUILD_IDENTITY = 'unreleased-worktree'
'''
    return {CORE_IDENTITY: core, TS_IDENTITY: ts}


def self_test() -> None:
    expected = shipped_candidate_packages()
    candidate = package_version()
    surface = load_json(SURFACE)
    release_gates = load_json(RELEASE_GATES)
    validate_candidate_documents(surface, release_gates, candidate, expected)
    hostile_surface = copy.deepcopy(surface)
    hostile_surface["candidate"] = "9.9.9"
    hostile_gates = copy.deepcopy(release_gates)
    hostile_gates["candidate"] = "9.9.9"
    omitted_package = copy.deepcopy(surface)
    omitted_package["packages"]["candidate"] = expected[:-1]
    stale_wire = copy.deepcopy(surface)
    stale_wire["wire_version"] = "9.9"
    for bad_surface, bad_gates in (
        (hostile_surface, release_gates),
        (surface, hostile_gates),
        (omitted_package, release_gates),
        (stale_wire, release_gates),
    ):
        try:
            validate_candidate_documents(bad_surface, bad_gates, candidate, expected)
        except ValueError:
            continue
        raise AssertionError("hostile candidate/package-surface mutation passed validation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write", action="store_true", help="replace the committed generated manifest"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="also run hostile metadata mutations"
    )
    args = parser.parse_args()

    manifest = build_manifest()
    if args.self_test:
        self_test()
    generated = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    identities = identity_outputs(manifest)
    if args.write:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(generated, encoding="utf-8")
        for path, content in identities.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        print(f"WROTE {relative(OUTPUT)}")
        print(
            "WROTE implementation identity pins: "
            + ", ".join(relative(path) for path in identities)
        )
        return 0

    if not OUTPUT.is_file():
        print(f"ERROR: missing generated {relative(OUTPUT)}", file=sys.stderr)
        return 1
    committed = OUTPUT.read_text(encoding="utf-8")
    if committed != generated:
        print(
            "ERROR: normative contract manifest is stale; run "
            "scripts/generate_contract_manifest.py --write and review the diff",
            file=sys.stderr,
        )
        return 1
    stale_identities = [
        relative(path)
        for path, content in identities.items()
        if not path.is_file() or path.read_text(encoding="utf-8") != content
    ]
    if stale_identities:
        print(
            "ERROR: implementation identity pins are stale: "
            + ", ".join(stale_identities)
            + "; run scripts/generate_contract_manifest.py --write and review",
            file=sys.stderr,
        )
        return 1
    print(
        "OK normative contract manifest: "
        f"{len(manifest['normative_sources'])} sources, "
        f"sha256 {manifest['contract_digest_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
