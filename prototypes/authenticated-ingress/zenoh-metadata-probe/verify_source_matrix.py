#!/usr/bin/env python3
"""Verify the exact registry source behind the quarantined Zenoh probe."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MATRIX_PATH = ROOT / "source-matrix.v1.json"
MANIFEST_PATH = ROOT / "Cargo.toml"
LOCK_PATH = ROOT / "Cargo.lock"
EXPECTED_SCHEMA = "ncp.prototype.zenoh-source-matrix.v1"
CRATES_IO_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"


class VerificationError(ValueError):
    """The locally resolved Zenoh input differs from the reviewed input."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"cannot load {path.name}: {error}") from error
    if not isinstance(value, dict):
        raise VerificationError(f"{path.name} must contain one object")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cargo_metadata() -> dict[str, Any]:
    try:
        output = subprocess.check_output(
            [
                "cargo",
                "metadata",
                "--locked",
                "--format-version",
                "1",
                "--manifest-path",
                str(MANIFEST_PATH),
            ],
            cwd=ROOT,
            text=True,
        )
        value = json.loads(output)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        raise VerificationError(f"cargo metadata failed: {error}") from error
    if not isinstance(value, dict):
        raise VerificationError("cargo metadata root is not an object")
    return value


def one_zenoh_package(metadata: dict[str, Any], version: str) -> dict[str, Any]:
    packages = [
        package
        for package in metadata.get("packages", [])
        if isinstance(package, dict)
        and package.get("name") == "zenoh"
        and package.get("version") == version
    ]
    if len(packages) != 1:
        raise VerificationError(
            f"expected one zenoh {version} package, found {len(packages)}"
        )
    package = packages[0]
    if package.get("source") != CRATES_IO_SOURCE:
        raise VerificationError(
            "zenoh did not resolve from the reviewed crates.io source"
        )
    return package


def one_package(packages: Any, name: str, version: str, label: str) -> dict[str, Any]:
    if not isinstance(packages, list):
        raise VerificationError(f"{label} package array is malformed")
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == name
        and package.get("version") == version
    ]
    if len(matches) != 1:
        raise VerificationError(f"{label} does not contain one exact {name} {version}")
    return matches[0]


def verify_manifest_patch(manifest: dict[str, Any], backport: dict[str, Any]) -> None:
    patch = manifest.get("patch")
    crates_io = patch.get("crates-io") if isinstance(patch, dict) else None
    transport = (
        crates_io.get("zenoh-transport") if isinstance(crates_io, dict) else None
    )
    expected = {
        "git": backport.get("repository"),
        "rev": backport.get("revision"),
    }
    if transport != expected:
        raise VerificationError("Cargo.toml Zenoh transport patch identity differs")


def verify_lock(
    lock: dict[str, Any], crate: dict[str, Any], backport: dict[str, Any]
) -> None:
    packages = lock.get("package")
    zenoh = one_package(
        packages, str(crate.get("name")), str(crate.get("version")), "Cargo.lock"
    )
    if zenoh.get("checksum") != crate["crates_io_checksum_sha256"]:
        raise VerificationError("Cargo.lock Zenoh checksum differs from the matrix")

    transport = one_package(
        packages,
        str(backport.get("name")),
        str(backport.get("version")),
        "Cargo.lock",
    )
    if transport.get("source") != backport.get("cargo_source"):
        raise VerificationError(
            "Cargo.lock Zenoh transport source differs from the matrix"
        )
    if "checksum" in transport:
        raise VerificationError(
            "Cargo.lock Git transport must not claim a registry checksum"
        )

    lz4 = one_package(
        packages,
        "lz4_flex",
        str(backport.get("lz4_flex_version")),
        "Cargo.lock",
    )
    if lz4.get("source") != CRATES_IO_SOURCE or lz4.get("checksum") != backport.get(
        "lz4_flex_checksum_sha256"
    ):
        raise VerificationError("Cargo.lock lz4_flex identity differs from the matrix")


def verify_backport_metadata(
    metadata: dict[str, Any], backport: dict[str, Any]
) -> None:
    packages = metadata.get("packages")
    transport = one_package(
        packages,
        str(backport.get("name")),
        str(backport.get("version")),
        "cargo metadata",
    )
    if transport.get("source") != backport.get("cargo_source"):
        raise VerificationError(
            "resolved Zenoh transport source differs from the matrix"
        )
    if transport.get("rust_version") != backport.get("rust_version"):
        raise VerificationError(
            "resolved Zenoh transport Rust floor differs from the matrix"
        )
    lz4 = one_package(
        packages,
        "lz4_flex",
        str(backport.get("lz4_flex_version")),
        "cargo metadata",
    )
    if lz4.get("source") != CRATES_IO_SOURCE:
        raise VerificationError("resolved lz4_flex source differs from the matrix")


def verify_vcs(crate_root: Path, crate: dict[str, Any]) -> None:
    vcs = load_json(crate_root / ".cargo_vcs_info.json")
    if vcs.get("path_in_vcs") != crate["path_in_vcs"]:
        raise VerificationError("crate path_in_vcs differs from the matrix")
    git = vcs.get("git")
    if not isinstance(git, dict) or git.get("sha1") != crate["upstream_commit_sha1"]:
        raise VerificationError("crate upstream Git identity differs from the matrix")


def verify_feature_boundary(metadata: dict[str, Any]) -> None:
    packages = {
        package["id"]: package
        for package in metadata.get("packages", [])
        if isinstance(package, dict) and isinstance(package.get("id"), str)
    }
    nodes = metadata.get("resolve", {}).get("nodes", [])
    matches = [
        node
        for node in nodes
        if isinstance(node, dict)
        and packages.get(node.get("id"), {}).get("name") == "zenoh-transport"
        and packages.get(node.get("id"), {}).get("version") == "1.9.0"
    ]
    if len(matches) != 1:
        raise VerificationError(
            "cannot identify one resolved zenoh-transport 1.9.0 node"
        )
    features = matches[0].get("features")
    if not isinstance(features, list):
        raise VerificationError("zenoh-transport feature list is unavailable")
    if "transport_compression" in features:
        raise VerificationError("Zenoh transport compression must remain disabled")


def verify_files(crate_root: Path, files: Any) -> None:
    if not isinstance(files, list) or not files:
        raise VerificationError("source matrix files must be a non-empty array")
    seen: set[str] = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise VerificationError(f"files[{index}] is not an object")
        relative = item.get("path")
        expected_hash = item.get("sha256")
        fragments = item.get("required_fragments")
        if not isinstance(relative, str) or not relative or relative in seen:
            raise VerificationError(f"files[{index}].path is missing or duplicated")
        seen.add(relative)
        source = (crate_root / relative).resolve()
        try:
            source.relative_to(crate_root.resolve())
        except ValueError as error:
            raise VerificationError(
                f"reviewed source path escapes the crate root: {relative}"
            ) from error
        if not source.is_file():
            raise VerificationError(f"reviewed source file is missing: {relative}")
        if sha256(source) != expected_hash:
            raise VerificationError(f"source hash differs: {relative}")
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise VerificationError(f"cannot read {relative}: {error}") from error
        if not isinstance(fragments, list) or not fragments:
            raise VerificationError(f"files[{index}].required_fragments is empty")
        for fragment in fragments:
            if not isinstance(fragment, str) or not fragment or fragment not in text:
                raise VerificationError(f"required fragment missing from {relative}")


def main() -> int:
    matrix = load_json(MATRIX_PATH)
    if matrix.get("schema") != EXPECTED_SCHEMA:
        raise VerificationError("source matrix schema is not exact")
    crate = matrix.get("crate")
    if not isinstance(crate, dict):
        raise VerificationError("source matrix crate entry is not an object")
    backport = matrix.get("zenoh_transport_backport")
    if not isinstance(backport, dict):
        raise VerificationError("source matrix backport entry is not an object")
    try:
        manifest_table = tomllib.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        lock_table = tomllib.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise VerificationError(f"cannot load probe Cargo inputs: {error}") from error
    verify_manifest_patch(manifest_table, backport)
    verify_lock(lock_table, crate, backport)
    metadata = cargo_metadata()
    package = one_zenoh_package(metadata, str(crate.get("version")))
    verify_backport_metadata(metadata, backport)
    manifest = Path(str(package["manifest_path"])).resolve()
    crate_root = manifest.parent
    verify_vcs(crate_root, crate)
    verify_feature_boundary(metadata)
    verify_files(crate_root, matrix.get("files"))
    print(
        "OK exact Zenoh source matrix: "
        f"{crate['version']} checksum={crate['crates_io_checksum_sha256']} "
        f"upstream={crate['upstream_commit_sha1']} "
        f"backport={backport['revision']} lz4_flex={backport['lz4_flex_version']} "
        f"files={len(matrix['files'])}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except VerificationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
