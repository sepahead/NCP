#!/usr/bin/env python3
"""Verify the quarantined prototype's exact dependency and source boundary."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CARGO_TOML = ROOT / "Cargo.toml"
SOURCE = ROOT / "src" / "lib.rs"

EXPECTED_DEPENDENCIES = {
    "getrandom": "=0.3.4",
    "ncp-core": {"version": "=1.0.0-rc.1", "path": "../../../ncp-core"},
    "rustls": {
        "version": "=0.23.40",
        "default-features": False,
        "features": ["ring", "std"],
    },
    "serde": {"version": "=1.0.228", "features": ["derive"]},
    "serde_json": "=1.0.150",
    "sha2": "=0.10.9",
    "tokio": {
        "version": "=1.52.3",
        "features": [
            "io-util",
            "macros",
            "net",
            "rt-multi-thread",
            "sync",
            "time",
        ],
    },
    "tokio-rustls": {
        "version": "=0.26.4",
        "default-features": False,
        "features": ["ring"],
    },
}

EXPECTED_DEV_DEPENDENCIES = {
    "rcgen": {
        "version": "=0.14.8",
        "default-features": False,
        "features": ["pem", "ring"],
    },
    "static_assertions": "=1.1.0",
    "time": "=0.3.47",
}

FORBIDDEN_RESOLVED_FEATURES = {
    "rustls": {
        "aws_lc_rs",
        "aws-lc-rs",
        "brotli",
        "fips",
        "logging",
        "prefer-post-quantum",
        "tls12",
        "zlib",
    },
    "tokio-rustls": {
        "aws_lc_rs",
        "aws-lc-rs",
        "brotli",
        "early-data",
        "fips",
        "logging",
        "tls12",
        "zlib",
    },
}


class VerificationError(ValueError):
    """The source or resolved dependency boundary drifted."""


def verify_manifest(document: dict[str, object]) -> None:
    if document.get("workspace") != {}:
        raise VerificationError("prototype must remain an isolated Cargo workspace")
    if document.get("dependencies") != EXPECTED_DEPENDENCIES:
        raise VerificationError("normal dependencies differ from the exact reviewed set")
    if document.get("dev-dependencies") != EXPECTED_DEV_DEPENDENCIES:
        raise VerificationError("dev dependencies differ from the exact reviewed set")
    package = document.get("package")
    if not isinstance(package, dict):
        raise VerificationError("Cargo package metadata is missing")
    if package.get("publish") is not False or package.get("version") != "0.0.0":
        raise VerificationError("prototype must remain unpublished at version 0.0.0")


def verify_metadata(metadata: dict[str, object]) -> None:
    packages = metadata.get("packages")
    resolve = metadata.get("resolve")
    if not isinstance(packages, list) or not isinstance(resolve, dict):
        raise VerificationError("cargo metadata has no packages or resolution")
    package_by_id = {
        package["id"]: package
        for package in packages
        if isinstance(package, dict) and isinstance(package.get("id"), str)
    }
    nodes = resolve.get("nodes")
    if not isinstance(nodes, list):
        raise VerificationError("cargo metadata has no resolved nodes")

    seen: dict[str, tuple[str, set[str]]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        package = package_by_id.get(node.get("id"))
        if package is None:
            continue
        name = package.get("name")
        version = package.get("version")
        features = node.get("features")
        if isinstance(name, str) and isinstance(version, str) and isinstance(features, list):
            seen[name] = (version, set(features))

    expected_versions = {
        "rustls": "0.23.40",
        "tokio-rustls": "0.26.4",
        "rcgen": "0.14.8",
        "serde": "1.0.228",
        "serde_json": "1.0.150",
        "sha2": "0.10.9",
        "tokio": "1.52.3",
    }
    for name, expected_version in expected_versions.items():
        observed = seen.get(name)
        if observed is None or observed[0] != expected_version:
            raise VerificationError(
                f"{name} resolved to {observed!r}, expected {expected_version}"
            )
    for name, forbidden in FORBIDDEN_RESOLVED_FEATURES.items():
        enabled = seen[name][1]
        overlap = enabled & forbidden
        if overlap:
            raise VerificationError(
                f"{name} resolved forbidden features: {sorted(overlap)}"
            )
    if seen["rustls"][1] != {"ring", "std"}:
        raise VerificationError(
            f"rustls features are not exactly ring+std: {sorted(seen['rustls'][1])}"
        )
    if seen["tokio-rustls"][1] != {"ring"}:
        raise VerificationError(
            "tokio-rustls features are not exactly ring: "
            f"{sorted(seen['tokio-rustls'][1])}"
        )


def verify_source(source: str) -> None:
    required_fragments = [
        ".with_protocol_versions(&[&version::TLS13])",
        ".with_client_cert_verifier(verifier)",
        "config.session_storage = Arc::new(NoServerSessionStorage {});",
        "config.send_tls13_tickets = 0;",
        "config.max_early_data_size = 0;",
        "config.send_half_rtt_data = false;",
        "config.enable_secret_extraction = false;",
        "connection.handshake_kind()",
        "Some(rustls::HandshakeKind::Full)",
        "certificate mapping was removed before final admission",
        "ncp_core::bounded_json::parse_value(payload)",
        "ncp_core::messages::validate(&value)",
        "pub struct PinnedTls13ServerConfig(Arc<ServerConfig>);",
        "tls_config: PinnedTls13ServerConfig,",
        "struct AuthenticatedMessage {\n    context: AuthenticatedContext,\n    payload: Box<[u8]>,",
        "assert_not_impl_any!(\n        AuthenticatedContext:",
        "assert_not_impl_any!(\n        AuthenticatedMessage:",
    ]
    for fragment in required_fragments:
        if fragment not in source:
            raise VerificationError(f"required source invariant missing: {fragment!r}")
    forbidden_fragments = [
        "allow_unauthenticated",
        "with_no_client_auth",
        "unsafe {",
        'extern "C"',
        "impl serde::Serialize for AuthenticatedContext",
        "impl serde::Serialize for AuthenticatedMessage",
        "impl Clone for AuthenticatedContext",
        "impl Clone for AuthenticatedMessage",
        "pub fn into_parts",
        "pub fn into_payload",
        "pub fn context_mut",
        "pub fn payload_mut",
    ]
    for fragment in forbidden_fragments:
        if fragment in source:
            raise VerificationError(f"forbidden source surface found: {fragment!r}")


def load_metadata() -> dict[str, object]:
    process = subprocess.run(
        ["cargo", "metadata", "--locked", "--format-version", "1"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(process.stdout)


def main() -> int:
    try:
        verify_manifest(tomllib.loads(CARGO_TOML.read_text(encoding="utf-8")))
        verify_metadata(load_metadata())
        verify_source(SOURCE.read_text(encoding="utf-8"))
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, VerificationError) as error:
        print(f"TLS-ingress feature verification failed: {error}", file=sys.stderr)
        return 1
    print("TLS-ingress dependency features and protected source boundary verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
