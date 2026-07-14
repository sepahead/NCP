#!/usr/bin/env python3
"""Build and exercise the distributable Rust crate archives.

All five packageable workspace crates are packaged and inspected. The three
crates with package-sensitive test fixtures are tested from their extracted
archives; the Python binding and gateway are type-checked from theirs. Temporary
Cargo patches point exact unpublished NCP dependencies at the corresponding
extracted archives, leaving the normalized/published manifests untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRATES = ("ncp-core", "ncp-zenoh", "ncp-cpp", "ncp-python", "ncp-gateway")
TEST_CRATES = ("ncp-core", "ncp-zenoh", "ncp-cpp")
CHECK_CRATES = ("ncp-python", "ncp-gateway")
LOCAL_DEPENDENCIES = {
    "ncp-core": (),
    "ncp-zenoh": ("ncp-core",),
    "ncp-cpp": ("ncp-core",),
    "ncp-python": ("ncp-core",),
    "ncp-gateway": ("ncp-core", "ncp-zenoh"),
}


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def cargo_patch_args(dependencies: tuple[str, ...], paths: dict[str, Path]) -> list[str]:
    args: list[str] = []
    for dependency in dependencies:
        # JSON string syntax is valid Cargo config TOML and handles spaces safely.
        value = f"patch.crates-io.{dependency}.path={json.dumps(str(paths[dependency]))}"
        args.extend(("--config", value))
    return args


def extract_archive(archive: Path, destination: Path, expected_prefix: str) -> Path:
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != expected_prefix:
                raise RuntimeError(f"unsafe path in {archive.name}: {member.name}")
        package.extractall(destination)
    return destination / expected_prefix


def assert_archive_surface(crate: str, source: Path, archive_root: Path) -> None:
    required = {
        Path("Cargo.toml"),
        Path("README.md"),
        Path("LICENSE-MIT"),
        Path("LICENSE-APACHE"),
    }
    testdata = source / "testdata"
    if testdata.is_dir():
        required.update(
            path.relative_to(source) for path in testdata.rglob("*") if path.is_file()
        )

    missing = sorted(path for path in required if not (archive_root / path).is_file())
    if missing:
        formatted = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"{crate} archive is missing required files: {formatted}")

    for license_name in ("LICENSE-MIT", "LICENSE-APACHE"):
        if (archive_root / license_name).read_bytes() != (ROOT / license_name).read_bytes():
            raise RuntimeError(f"{crate} archive carries a stale {license_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="pass --offline to Cargo (useful after the workspace gate populated its cache)",
    )
    args = parser.parse_args()

    run([sys.executable, "scripts/sync_rust_package_testdata.py"])
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    version = workspace["workspace"]["package"]["version"]

    with tempfile.TemporaryDirectory(prefix="ncp-package-selftest-") as tmp:
        temp = Path(tmp)
        package_target = temp / "package-target"
        extracted_parent = temp / "extracted"
        extracted_parent.mkdir()
        source_paths = {crate: ROOT / crate for crate in CRATES}
        extracted_paths: dict[str, Path] = {}

        for crate in CRATES:
            command = [
                "cargo",
                "package",
                "--package",
                crate,
                "--allow-dirty",
                "--locked",
                "--no-verify",
                "--target-dir",
                str(package_target),
            ]
            if args.offline:
                command.append("--offline")
            command.extend(cargo_patch_args(LOCAL_DEPENDENCIES[crate], source_paths))
            run(command)

            archive = package_target / "package" / f"{crate}-{version}.crate"
            if not archive.is_file():
                raise RuntimeError(f"Cargo did not produce {archive}")
            prefix = f"{crate}-{version}"
            extracted = extract_archive(archive, extracted_parent, prefix)
            assert_archive_surface(crate, source_paths[crate], extracted)
            extracted_paths[crate] = extracted

        # Keep build artifacts under the same temporary tree as the extraction.
        # `CARGO_MANIFEST_DIR` is compiled into several fixture paths; reusing a
        # target directory across differently named temp extractions can otherwise
        # execute a stale test binary that points at an already-deleted directory.
        test_target = temp / "test-target"
        env = os.environ.copy()
        env["CARGO_TARGET_DIR"] = str(test_target)
        for crate in TEST_CRATES:
            command = [
                "cargo",
                "test",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
            ]
            if args.offline:
                command.append("--offline")
            command.extend(cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths))
            run(command, env=env)

        for crate in CHECK_CRATES:
            command = [
                "cargo",
                "check",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
            ]
            if args.offline:
                command.append("--offline")
            command.extend(cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths))
            run(command, env=env)

    # Catch a canonical fixture changing while the longer archive tests ran.
    run([sys.executable, "scripts/sync_rust_package_testdata.py"])
    print("Rust package archive self-test passed for all five packageable crates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
