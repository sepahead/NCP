#!/usr/bin/env python3
"""Fail closed on the reviewed Zenoh/lz4_flex advisory disposition.

RUSTSEC-2026-0041 affects lz4_flex's block decompression APIs.  Zenoh 1.9.0
contains the affected call behind its ``transport_compression`` feature, but its
dependency constraint cannot select a patched lz4_flex release.  NCP therefore
keeps compression and Zenoh default features disabled, verifies the *resolved*
feature graph, and treats any dependency or feature drift as a fresh security
review.  This is an exposure reduction, not a claim that the vulnerable package
is absent or that arbitrary downstream Cargo feature unification is safe.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ADVISORY = "RUSTSEC-2026-0041"
ZENOH_VERSION = "1.9.0"
LZ4_FLEX_VERSION = "0.10.0"
DECLARED_ZENOH_FEATURES = {
    "shared-memory",
    "transport_tcp",
    "transport_tls",
    "transport_udp",
}
RESOLVED_ZENOH_FEATURES = DECLARED_ZENOH_FEATURES | {"zenoh-shm"}
FORBIDDEN_FEATURES = {"default", "transport_compression"}


class ExposureError(ValueError):
    """The locked dependency graph no longer matches the reviewed disposition."""


def _table(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ExposureError(f"cannot parse {path}: {error}") from error
    if not isinstance(value, dict):
        raise ExposureError(f"{path} must contain a TOML table")
    return value


def _packages(lock: dict[str, Any], name: str) -> list[dict[str, Any]]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise ExposureError("Cargo.lock has no package array")
    return [
        package
        for package in packages
        if isinstance(package, dict) and package.get("name") == name
    ]


def _one_package(lock: dict[str, Any], name: str, version: str) -> None:
    matches = _packages(lock, name)
    versions = sorted(
        str(package.get("version")) for package in matches if "version" in package
    )
    if versions != [version]:
        raise ExposureError(
            f"Cargo.lock {name} versions are {versions!r}; expected reviewed {version!r}"
        )


def _package_by_name_version(
    metadata: dict[str, Any], name: str, version: str
) -> dict[str, Any]:
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise ExposureError("cargo metadata has no packages array")
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == name
        and package.get("version") == version
    ]
    if len(matches) != 1:
        raise ExposureError(
            f"cargo metadata must contain exactly one {name} {version}; found {len(matches)}"
        )
    return matches[0]


def _resolved_node(metadata: dict[str, Any], package_id: str) -> dict[str, Any]:
    resolve = metadata.get("resolve")
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(nodes, list):
        raise ExposureError("cargo metadata has no resolved nodes")
    matches = [node for node in nodes if isinstance(node, dict) and node.get("id") == package_id]
    if len(matches) != 1:
        raise ExposureError(f"resolved package node count for {package_id!r} is {len(matches)}")
    return matches[0]


def _features(node: dict[str, Any], label: str) -> set[str]:
    value = node.get("features")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ExposureError(f"{label} resolved features are malformed")
    features = set(value)
    forbidden = sorted(features & FORBIDDEN_FEATURES)
    if forbidden:
        raise ExposureError(f"{label} enables forbidden feature(s): {forbidden}")
    return features


def _dependency_ids(node: dict[str, Any]) -> set[str]:
    deps = node.get("deps")
    if not isinstance(deps, list):
        raise ExposureError("resolved node dependencies are malformed")
    identifiers: set[str] = set()
    for dep in deps:
        if not isinstance(dep, dict) or not isinstance(dep.get("pkg"), str):
            raise ExposureError("resolved node contains a malformed dependency")
        identifiers.add(dep["pkg"])
    return identifiers


def validate(
    deny: dict[str, Any],
    lock: dict[str, Any],
    manifest: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    advisories = deny.get("advisories")
    ignored = advisories.get("ignore") if isinstance(advisories, dict) else None
    if not isinstance(ignored, list) or ADVISORY not in ignored:
        raise ExposureError(
            f"deny.toml must explicitly retain the reviewed {ADVISORY} disposition"
        )
    if ignored.count(ADVISORY) != 1:
        raise ExposureError(f"deny.toml must mention {ADVISORY} exactly once")

    _one_package(lock, "zenoh", ZENOH_VERSION)
    _one_package(lock, "zenoh-transport", ZENOH_VERSION)
    _one_package(lock, "lz4_flex", LZ4_FLEX_VERSION)

    dependencies = manifest.get("dependencies")
    zenoh = dependencies.get("zenoh") if isinstance(dependencies, dict) else None
    if not isinstance(zenoh, dict):
        raise ExposureError("ncp-zenoh must declare Zenoh with an explicit dependency table")
    if zenoh.get("version") != "1.9":
        raise ExposureError("ncp-zenoh Zenoh requirement drifted from reviewed 1.9")
    if zenoh.get("default-features") is not False:
        raise ExposureError("ncp-zenoh must keep Zenoh default features disabled")
    declared = zenoh.get("features")
    if not isinstance(declared, list) or not all(isinstance(item, str) for item in declared):
        raise ExposureError("ncp-zenoh Zenoh feature declaration is malformed")
    declared_set = set(declared)
    if len(declared) != len(declared_set):
        raise ExposureError("ncp-zenoh Zenoh feature declaration contains a duplicate")
    if declared_set != DECLARED_ZENOH_FEATURES:
        raise ExposureError(
            "ncp-zenoh Zenoh features drifted; an explicit dependency exposure review is required"
        )

    zenoh_package = _package_by_name_version(metadata, "zenoh", ZENOH_VERSION)
    transport_package = _package_by_name_version(metadata, "zenoh-transport", ZENOH_VERSION)
    lz4_package = _package_by_name_version(metadata, "lz4_flex", LZ4_FLEX_VERSION)
    zenoh_id = zenoh_package.get("id")
    transport_id = transport_package.get("id")
    lz4_id = lz4_package.get("id")
    if not all(isinstance(value, str) for value in (zenoh_id, transport_id, lz4_id)):
        raise ExposureError("cargo metadata package IDs are malformed")

    zenoh_node = _resolved_node(metadata, zenoh_id)
    transport_node = _resolved_node(metadata, transport_id)
    zenoh_features = _features(zenoh_node, "zenoh")
    transport_features = _features(transport_node, "zenoh-transport")
    if zenoh_features != RESOLVED_ZENOH_FEATURES:
        raise ExposureError(
            f"zenoh resolved features drifted: {sorted(zenoh_features)!r}"
        )
    if transport_features != RESOLVED_ZENOH_FEATURES:
        raise ExposureError(
            f"zenoh-transport resolved features drifted: {sorted(transport_features)!r}"
        )
    if lz4_id not in _dependency_ids(transport_node):
        raise ExposureError("reviewed zenoh-transport to lz4_flex edge is absent")


def _metadata(repo: Path) -> dict[str, Any]:
    try:
        process = subprocess.run(
            ["cargo", "metadata", "--format-version", "1", "--locked"],
            cwd=repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise ExposureError(f"cannot execute cargo metadata: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise ExposureError(f"cargo metadata --locked failed: {detail}")
    try:
        value = json.loads(process.stdout)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ExposureError(f"cargo metadata returned invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ExposureError("cargo metadata root must be an object")
    return value


def _fixture() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    zenoh_id = "registry#zenoh@1.9.0"
    transport_id = "registry#zenoh-transport@1.9.0"
    lz4_id = "registry#lz4_flex@0.10.0"
    deny = {"advisories": {"ignore": [ADVISORY]}}
    lock = {
        "package": [
            {"name": "zenoh", "version": ZENOH_VERSION},
            {"name": "zenoh-transport", "version": ZENOH_VERSION},
            {"name": "lz4_flex", "version": LZ4_FLEX_VERSION},
        ]
    }
    manifest = {
        "dependencies": {
            "zenoh": {
                "version": "1.9",
                "default-features": False,
                "features": sorted(DECLARED_ZENOH_FEATURES),
            }
        }
    }
    metadata = {
        "packages": [
            {"name": "zenoh", "version": ZENOH_VERSION, "id": zenoh_id},
            {
                "name": "zenoh-transport",
                "version": ZENOH_VERSION,
                "id": transport_id,
            },
            {"name": "lz4_flex", "version": LZ4_FLEX_VERSION, "id": lz4_id},
        ],
        "resolve": {
            "nodes": [
                {"id": zenoh_id, "features": sorted(RESOLVED_ZENOH_FEATURES), "deps": []},
                {
                    "id": transport_id,
                    "features": sorted(RESOLVED_ZENOH_FEATURES),
                    "deps": [{"pkg": lz4_id}],
                },
                {"id": lz4_id, "features": [], "deps": []},
            ]
        },
    }
    return deny, lock, manifest, metadata


def self_test() -> None:
    import copy

    deny, lock, manifest, metadata = _fixture()
    validate(deny, lock, manifest, metadata)
    hostile: list[tuple[str, tuple[dict[str, Any], ...]]] = []

    case = tuple(copy.deepcopy(value) for value in (deny, lock, manifest, metadata))
    case[0]["advisories"]["ignore"] = []
    hostile.append(("missing advisory disposition", case))

    case = tuple(copy.deepcopy(value) for value in (deny, lock, manifest, metadata))
    case[2]["dependencies"]["zenoh"]["default-features"] = True
    hostile.append(("default features", case))

    case = tuple(copy.deepcopy(value) for value in (deny, lock, manifest, metadata))
    case[3]["resolve"]["nodes"][0]["features"].append("transport_compression")
    hostile.append(("resolved compression", case))

    case = tuple(copy.deepcopy(value) for value in (deny, lock, manifest, metadata))
    case[3]["resolve"]["nodes"][1]["deps"] = []
    hostile.append(("missing dependency edge", case))

    for label, values in hostile:
        try:
            validate(*values)
        except ExposureError:
            continue
        raise AssertionError(f"hostile self-test unexpectedly passed: {label}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            self_test()
        repo = args.repo.resolve()
        validate(
            _table(repo / "deny.toml"),
            _table(repo / "Cargo.lock"),
            _table(repo / "ncp-zenoh" / "Cargo.toml"),
            _metadata(repo),
        )
        print(
            "OK dependency exposure: Zenoh 1.9.0 transport_compression/default "
            "features disabled; RUSTSEC-2026-0041 remains tracked and release-blocking"
        )
    except (ExposureError, AssertionError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
