#!/usr/bin/env python3
"""Synchronize crate-local copies of NCP's package-test fixtures and licenses.

The normative copies remain at the repository root. Rust crate archives cannot
read sibling repository paths after Cargo extracts them, so publishable crates
carry exact snapshots under ``testdata/``. Run with ``--write`` after changing a
schema, proto, conformance vector, deployment template, or root license; the
default check mode fails on missing, stale, or unexpected snapshot files.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUST_CRATES = ("ncp-core", "ncp-zenoh", "ncp-cpp", "ncp-python", "ncp-gateway")
TESTDATA_ROOTS = (
    ROOT / "ncp-core/testdata",
    ROOT / "ncp-zenoh/testdata",
    ROOT / "ncp-cpp/testdata",
)


def fixture_pairs() -> list[tuple[Path, Path]]:
    """Return every canonical-source to package-snapshot mapping."""

    pairs: list[tuple[Path, Path]] = []

    def copy_tree_files(
        source_dir: str, pattern: str, destinations: tuple[str, ...]
    ) -> None:
        sources = sorted((ROOT / source_dir).glob(pattern))
        if not sources:
            raise RuntimeError(f"no canonical fixtures matched {source_dir}/{pattern}")
        for source in sources:
            if source.is_file():
                for destination in destinations:
                    pairs.append((source, ROOT / destination / source.name))

    copy_tree_files(
        "schemas",
        "*.json",
        ("ncp-core/testdata/schemas",),
    )
    copy_tree_files(
        "conformance/vectors",
        "*",
        (
            "ncp-core/testdata/conformance/vectors",
            "ncp-cpp/testdata/conformance/vectors",
        ),
    )
    pairs.extend(
        (
            (
                ROOT / "conformance/request-digest/v1.json",
                ROOT / "ncp-core/testdata/conformance/request-digest.json",
            ),
            (
                ROOT / "conformance/request-digest/v1.json",
                ROOT / "ncp-cpp/testdata/conformance/request-digest.json",
            ),
            (
                ROOT / "conformance/security-state-digest/v1.json",
                ROOT / "ncp-core/testdata/conformance/security-state-digest.json",
            ),
            (
                ROOT / "conformance/plant-profile/v1.json",
                ROOT / "ncp-core/testdata/conformance/plant-profile.json",
            ),
            (
                ROOT / "conformance/manifest.v1.json",
                ROOT / "ncp-core/testdata/conformance/manifest.v1.json",
            ),
            (
                ROOT / "conformance/manifest.v1.json",
                ROOT / "ncp-zenoh/testdata/conformance/manifest.v1.json",
            ),
            (
                ROOT / "conformance/manifest.v1.json",
                ROOT / "ncp-cpp/testdata/conformance/manifest.v1.json",
            ),
            (
                ROOT / "conformance/migration/v0.8-to-v1.0/channel-requirement.json",
                ROOT
                / "ncp-core/testdata/conformance/migration/channel-requirement.json",
            ),
            (
                ROOT
                / "conformance/migration/v0.8-to-v1.0/wire-0.8-reconstructable-capture.json",
                ROOT
                / "ncp-core/testdata/migration/wire-0.8-reconstructable-capture.json",
            ),
            (
                ROOT / "conformance/behavior/vectors.json",
                ROOT / "ncp-core/testdata/conformance/behavior/vectors.json",
            ),
            (
                ROOT / "conformance/behavior/vectors.json",
                ROOT / "ncp-zenoh/testdata/conformance/behavior/vectors.json",
            ),
            (
                ROOT / "conformance/behavior/vectors.json",
                ROOT / "ncp-cpp/testdata/conformance/behavior/vectors.json",
            ),
            (
                ROOT / "proto/ncp.proto",
                ROOT / "ncp-core/testdata/proto/ncp.proto",
            ),
            (
                ROOT / "contract/errors.v1.json",
                ROOT / "ncp-core/testdata/contract/errors.v1.json",
            ),
            (
                ROOT / "contract/canonical-digest.v1.json",
                ROOT / "ncp-core/testdata/contract/canonical-digest.v1.json",
            ),
            (
                ROOT / "contract/security-state-digest.v1.json",
                ROOT / "ncp-core/testdata/contract/security-state-digest.v1.json",
            ),
            (
                ROOT / "contract/plant-profile.v1.json",
                ROOT / "ncp-core/testdata/contract/plant-profile.v1.json",
            ),
            (
                ROOT / "deploy/zenoh-access-control.json5",
                ROOT / "ncp-zenoh/testdata/deploy/zenoh-access-control.json5",
            ),
            (
                ROOT / "deploy/zenoh-client-secure.json5",
                ROOT / "ncp-zenoh/testdata/deploy/zenoh-client-secure.json5",
            ),
        )
    )

    for crate in RUST_CRATES:
        for license_name in ("LICENSE-MIT", "LICENSE-APACHE"):
            pairs.append((ROOT / license_name, ROOT / crate / license_name))

    return pairs


def unexpected_testdata_files(expected: set[Path]) -> list[Path]:
    unexpected: list[Path] = []
    for testdata_root in TESTDATA_ROOTS:
        if not testdata_root.exists():
            continue
        unexpected.extend(
            path
            for path in testdata_root.rglob("*")
            if (path.is_file() or path.is_symlink()) and path not in expected
        )
    return sorted(unexpected)


def check() -> int:
    pairs = fixture_pairs()
    expected = {destination for _, destination in pairs}
    failures: list[str] = []
    for source, destination in pairs:
        if not source.is_file():
            failures.append(f"canonical source is missing: {source.relative_to(ROOT)}")
        elif destination.is_symlink():
            failures.append(
                f"snapshot must be a regular file, not a symlink: "
                f"{destination.relative_to(ROOT)}"
            )
        elif not destination.is_file():
            failures.append(f"snapshot is missing: {destination.relative_to(ROOT)}")
        elif source.read_bytes() != destination.read_bytes():
            failures.append(
                f"snapshot drifted from {source.relative_to(ROOT)}: "
                f"{destination.relative_to(ROOT)}"
            )

    failures.extend(
        f"unexpected managed snapshot: {path.relative_to(ROOT)}"
        for path in unexpected_testdata_files(expected)
    )

    if failures:
        sys.stderr.write("Rust package testdata/license sync failed:\n")
        for failure in failures:
            sys.stderr.write(f"  - {failure}\n")
        sys.stderr.write(
            "Run `python3 scripts/sync_rust_package_testdata.py --write` "
            "and review the copied bytes.\n"
        )
        return 1

    print(f"Rust package snapshots are synchronized ({len(pairs)} files).")
    return 0


def write() -> int:
    pairs = fixture_pairs()
    expected = {destination for _, destination in pairs}
    for stale in unexpected_testdata_files(expected):
        stale.unlink()
    for source, destination in pairs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    print(f"Synchronized {len(pairs)} Rust package fixture/license files.")
    return check()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="replace crate-local snapshots with the canonical root files",
    )
    args = parser.parse_args()
    return write() if args.write else check()


if __name__ == "__main__":
    raise SystemExit(main())
