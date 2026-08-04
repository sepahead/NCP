#!/usr/bin/env python3
"""Build and exercise the candidate Rust crate archives.

All five packageable workspace crates are packaged and inspected. The three
crates with package-sensitive test fixtures are tested from their extracted
archives; the Python binding is type-checked and the gateway is type-checked plus
executed for its exact identity receipt. Temporary Cargo patches point exact
unpublished NCP dependencies at the corresponding extracted archives, leaving the
normalized/published manifests untouched.

The normalized ``ncp-zenoh`` and ``ncp-gateway`` archives cannot propagate the
workspace root's Zenoh transport patch. Their generated locks therefore select
the vulnerable published ``lz4_flex 0.10.0`` graph. This checker first resolves
and records that fallback without compiling it, then supplies the exact immutable
transport backport at the consuming test root, regenerates and verifies the
conditioned lock and metadata, and only then compiles offline. That is conditional
package-consumption evidence, not self-contained distribution or release
authorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
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
SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
TARGET_TRIPLE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
ZENOH_CONDITIONAL_CRATES = ("ncp-zenoh", "ncp-gateway")
CRATES_IO_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"
ZENOH_TRANSPORT_VERSION = "1.9.0"
ZENOH_TRANSPORT_REGISTRY_CHECKSUM = (
    "80800c4adc26dbe81418735068541cf39820a95ec988114f04dd014775ba7c97"
)
VULNERABLE_LZ4_VERSION = "0.10.0"
VULNERABLE_LZ4_CHECKSUM = (
    "8b8c72594ac26bfd34f2d99dfced2edfaddfe8a476e3ff2ca0eb293d925c4f83"
)
ZENOH_BACKPORT_GIT = "https://github.com/sepahead/zenoh-transport-lz4-backport"
ZENOH_BACKPORT_REVISION = "6b93b15d0795748b7f76c72eae07f1cda517e762"
ZENOH_BACKPORT_SOURCE = (
    f"git+{ZENOH_BACKPORT_GIT}?rev={ZENOH_BACKPORT_REVISION}#{ZENOH_BACKPORT_REVISION}"
)
FIXED_LZ4_VERSION = "0.11.6"
FIXED_LZ4_CHECKSUM = "373f5eceeeab7925e0c1098212f2fbc4d416adec9d35051a6ab251e824c1854a"
ZENOH_BACKPORT_CONFIG = {
    "patch.crates-io.zenoh-transport.git": ZENOH_BACKPORT_GIT,
    "patch.crates-io.zenoh-transport.rev": ZENOH_BACKPORT_REVISION,
}
RUST_PACKAGE_RECEIPT_SCHEMA = "ncp.rust-package-receipt.v2"


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def run_capture(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> bytes:
    print("+", " ".join(command), flush=True)
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
    )
    return process.stdout


def fetch_locked_archive(
    manifest_path: Path,
    patch_args: list[str],
    *,
    target: str,
    env: dict[str, str],
    cwd: Path,
) -> None:
    """Fetch one exact archive graph before offline metadata or compilation."""

    run(
        [
            "cargo",
            "fetch",
            "--manifest-path",
            str(manifest_path),
            "--locked",
            "--target",
            target,
            *patch_args,
        ],
        env=env,
        cwd=cwd,
    )


def parse_rustc_host(output: bytes) -> str:
    if len(output) > 65_536:
        raise RuntimeError("rustc version output exceeds its bound")
    try:
        text = output.decode("utf-8", "strict")
    except UnicodeError as error:
        raise RuntimeError("rustc version output is not UTF-8") from error
    hosts = [
        line.removeprefix("host: ")
        for line in text.splitlines()
        if line.startswith("host: ")
    ]
    if len(hosts) != 1 or TARGET_TRIPLE.fullmatch(hosts[0]) is None:
        raise RuntimeError("rustc version output has no exact host target")
    return hosts[0]


def rustc_host(env: dict[str, str]) -> str:
    try:
        process = subprocess.run(
            ["rustc", "-vV"],
            env=env,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise RuntimeError(f"cannot execute rustc: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"rustc -vV failed: {detail}")
    return parse_rustc_host(process.stdout)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_regular_tree(source: Path, destination: Path) -> None:
    """Copy one plain tree without following links or accepting special files."""

    destination.mkdir()
    for root, directories, files in os.walk(source, followlinks=False):
        root_path = Path(root)
        relative = root_path.relative_to(source)
        output_root = destination / relative
        output_root.mkdir(exist_ok=True)
        directories.sort()
        files.sort()
        for name in directories:
            path = root_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise RuntimeError(
                    f"package source contains a linked/special directory: {path}"
                )
            (output_root / name).mkdir(exist_ok=True)
        for name in files:
            path = root_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
                raise RuntimeError(
                    f"package source contains a link or special file: {path}"
                )
            shutil.copyfile(path, output_root / name)


def inject_packaged_source_identity(source: Path, revision: str) -> None:
    """Replace the generated non-certifying sentinel in a staged package tree."""

    identity = source / "ncp-core" / "src" / "contract_identity.rs"
    text = identity.read_text(encoding="utf-8")
    sentinel = '    None => "unreleased-worktree",'
    replacement = f'    None => "{revision}",'
    if text.count(sentinel) != 1 or revision in text:
        raise RuntimeError(
            "generated Rust build-identity sentinel is missing, duplicated, or pre-injected"
        )
    identity.write_text(text.replace(sentinel, replacement), encoding="utf-8")


def tree_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    records: dict[str, tuple[int, int, str]] = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise RuntimeError(
                    f"package source contains a link or special entry: {path}"
                )
        for name in files:
            path = directory_path / name
            records[path.relative_to(root).as_posix()] = (
                path.lstat().st_mode & 0o777,
                path.stat().st_size,
                sha256(path),
            )
    return records


def cargo_patch_args(
    dependencies: tuple[str, ...], paths: dict[str, Path]
) -> list[str]:
    args: list[str] = []
    for dependency in dependencies:
        try:
            path = paths[dependency].resolve(strict=True)
        except (KeyError, OSError, RuntimeError) as error:
            raise RuntimeError(
                f"cannot resolve local Cargo patch path for {dependency}"
            ) from error
        if not path.is_dir():
            raise RuntimeError(f"local Cargo patch path is not a directory: {path}")
        # JSON string syntax is valid Cargo config TOML and handles spaces safely.
        # Resolve filesystem aliases before Cargo compares the patch source with
        # its canonical package identity (notably /var versus /private/var on macOS).
        value = f"patch.crates-io.{dependency}.path={json.dumps(str(path))}"
        args.extend(("--config", value))
    return args


def zenoh_backport_patch_args() -> list[str]:
    """Return and validate the exact consuming-root security patch arguments."""

    args: list[str] = []
    for key, value in ZENOH_BACKPORT_CONFIG.items():
        args.extend(("--config", f"{key}={json.dumps(value)}"))
    validate_zenoh_backport_patch_args(args)
    return args


def validate_zenoh_backport_patch_args(args: list[str]) -> None:
    if len(args) != 2 * len(ZENOH_BACKPORT_CONFIG):
        raise RuntimeError("Zenoh backport Cargo patch is absent or incomplete")
    decoded: dict[str, str] = {}
    for index in range(0, len(args), 2):
        if args[index] != "--config" or "=" not in args[index + 1]:
            raise RuntimeError("Zenoh backport Cargo patch argument is malformed")
        key, encoded = args[index + 1].split("=", 1)
        if key in decoded:
            raise RuntimeError("Zenoh backport Cargo patch repeats a key")
        try:
            value = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise RuntimeError(
                "Zenoh backport Cargo patch value is not TOML JSON"
            ) from error
        if not isinstance(value, str):
            raise RuntimeError("Zenoh backport Cargo patch value is not a string")
        decoded[key] = value
    if decoded != ZENOH_BACKPORT_CONFIG:
        raise RuntimeError("Zenoh backport Cargo patch identity drifted")


def one_lock_package(
    lock: dict[str, object], name: str, version: str
) -> dict[str, object]:
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise RuntimeError("Cargo.lock package array is malformed")
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == name
        and package.get("version") == version
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Cargo.lock does not contain one exact {name} {version} package"
        )
    return matches[0]


def load_toml(path: Path) -> dict[str, object]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise RuntimeError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} is not a TOML table")
    return value


def assert_unpatched_archive_fallback(
    crate: str,
    manifest: dict[str, object],
    lock: dict[str, object],
    lock_sha256: str,
) -> dict[str, object]:
    """Prove the normalized archive alone retains the unsafe registry fallback."""

    if crate not in ZENOH_CONDITIONAL_CRATES:
        raise RuntimeError(f"unexpected conditional Zenoh archive: {crate}")
    if "patch" in manifest:
        raise RuntimeError(f"{crate} normalized archive unexpectedly contains a patch")
    if HEX_SHA256.fullmatch(lock_sha256) is None:
        raise RuntimeError(f"{crate} archive Cargo.lock digest is malformed")
    transport = one_lock_package(lock, "zenoh-transport", ZENOH_TRANSPORT_VERSION)
    if (
        transport.get("source") != CRATES_IO_SOURCE
        or transport.get("checksum") != ZENOH_TRANSPORT_REGISTRY_CHECKSUM
    ):
        raise RuntimeError(
            f"{crate} archive no longer demonstrates the reviewed registry fallback"
        )
    dependencies = transport.get("dependencies")
    if not isinstance(dependencies, list) or "lz4_flex" not in dependencies:
        raise RuntimeError(f"{crate} archive lost the transport-to-lz4 dependency edge")
    lz4 = one_lock_package(lock, "lz4_flex", VULNERABLE_LZ4_VERSION)
    if (
        lz4.get("source") != CRATES_IO_SOURCE
        or lz4.get("checksum") != VULNERABLE_LZ4_CHECKSUM
    ):
        raise RuntimeError(
            f"{crate} archive no longer demonstrates the vulnerable lz4 fallback"
        )
    return {
        "crate": crate,
        "cargo_lock_sha256": lock_sha256,
        "advisory": "RUSTSEC-2026-0041",
        "zenoh_transport_source": CRATES_IO_SOURCE,
        "zenoh_transport_checksum_sha256": ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
        "lz4_flex_version": VULNERABLE_LZ4_VERSION,
        "lz4_flex_source": CRATES_IO_SOURCE,
        "lz4_flex_checksum_sha256": VULNERABLE_LZ4_CHECKSUM,
        "compiled": False,
    }


def validate_conditioned_zenoh_lock(lock: dict[str, object]) -> None:
    transports = [
        package
        for package in lock.get("package", [])
        if isinstance(package, dict) and package.get("name") == "zenoh-transport"
    ]
    if len(transports) != 1:
        raise RuntimeError("conditioned lock has an incomplete Zenoh transport set")
    transport = one_lock_package(lock, "zenoh-transport", ZENOH_TRANSPORT_VERSION)
    if transport.get("source") != ZENOH_BACKPORT_SOURCE or "checksum" in transport:
        raise RuntimeError("conditioned lock does not select the exact Zenoh backport")
    dependencies = transport.get("dependencies")
    if not isinstance(dependencies, list) or "lz4_flex" not in dependencies:
        raise RuntimeError("conditioned lock lost the transport-to-lz4 dependency edge")

    lz4_packages = [
        package
        for package in lock.get("package", [])
        if isinstance(package, dict) and package.get("name") == "lz4_flex"
    ]
    if len(lz4_packages) != 1:
        raise RuntimeError("conditioned lock has an incomplete lz4_flex set")
    lz4 = one_lock_package(lock, "lz4_flex", FIXED_LZ4_VERSION)
    if (
        lz4.get("source") != CRATES_IO_SOURCE
        or lz4.get("checksum") != FIXED_LZ4_CHECKSUM
    ):
        raise RuntimeError("conditioned lock does not select exact fixed lz4_flex")


def one_metadata_package(
    metadata: dict[str, object], name: str, version: str
) -> dict[str, object]:
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise RuntimeError("cargo metadata package array is malformed")
    matches = [
        package
        for package in packages
        if isinstance(package, dict)
        and package.get("name") == name
        and package.get("version") == version
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"cargo metadata does not contain one exact {name} {version} package"
        )
    return matches[0]


def validate_conditioned_zenoh_metadata(metadata: dict[str, object]) -> None:
    transport = one_metadata_package(
        metadata, "zenoh-transport", ZENOH_TRANSPORT_VERSION
    )
    lz4 = one_metadata_package(metadata, "lz4_flex", FIXED_LZ4_VERSION)
    zenoh = one_metadata_package(metadata, "zenoh", ZENOH_TRANSPORT_VERSION)
    if transport.get("source") != ZENOH_BACKPORT_SOURCE:
        raise RuntimeError("cargo metadata Zenoh transport source drifted")
    if transport.get("rust_version") != "1.81.0":
        raise RuntimeError("cargo metadata Zenoh transport Rust floor drifted")
    if lz4.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("cargo metadata lz4_flex source drifted")
    if zenoh.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("cargo metadata Zenoh source drifted")

    resolve = metadata.get("resolve")
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(nodes, list):
        raise RuntimeError("cargo metadata resolved nodes are unavailable")
    package_ids = {
        str(package.get("id")): package
        for package in metadata.get("packages", [])
        if isinstance(package, dict) and isinstance(package.get("id"), str)
    }
    transport_id = transport.get("id")
    lz4_id = lz4.get("id")
    zenoh_id = zenoh.get("id")
    if not all(isinstance(item, str) for item in (transport_id, lz4_id, zenoh_id)):
        raise RuntimeError("cargo metadata package identity is malformed")
    resolved = {
        node.get("id"): node
        for node in nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    transport_node = resolved.get(transport_id)
    zenoh_node = resolved.get(zenoh_id)
    if not isinstance(transport_node, dict) or not isinstance(zenoh_node, dict):
        raise RuntimeError("cargo metadata Zenoh nodes are unavailable")
    for label, node in (("Zenoh", zenoh_node), ("Zenoh transport", transport_node)):
        features = node.get("features")
        if not isinstance(features, list) or not all(
            isinstance(feature, str) for feature in features
        ):
            raise RuntimeError(f"{label} resolved feature set is malformed")
        forbidden = {"default", "transport_compression"}.intersection(features)
        if forbidden:
            raise RuntimeError(
                f"{label} enables forbidden features: {sorted(forbidden)}"
            )
    dependency_ids: set[str] = set()
    dependencies = transport_node.get("deps")
    if not isinstance(dependencies, list):
        raise RuntimeError("cargo metadata transport dependency set is malformed")
    for dependency in dependencies:
        if not isinstance(dependency, dict) or not isinstance(
            dependency.get("pkg"), str
        ):
            raise RuntimeError("cargo metadata transport dependency is malformed")
        dependency_ids.add(dependency["pkg"])
    if lz4_id not in dependency_ids or lz4_id not in package_ids:
        raise RuntimeError("cargo metadata lost the exact transport-to-lz4 edge")


def validate_unpatched_zenoh_metadata(metadata: dict[str, object]) -> None:
    """Verify an executed archive-alone resolution exposes the unsafe fallback."""

    transport = one_metadata_package(
        metadata, "zenoh-transport", ZENOH_TRANSPORT_VERSION
    )
    lz4 = one_metadata_package(metadata, "lz4_flex", VULNERABLE_LZ4_VERSION)
    if transport.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("archive-alone metadata did not select registry transport")
    if lz4.get("source") != CRATES_IO_SOURCE:
        raise RuntimeError("archive-alone metadata did not select registry lz4_flex")
    resolve = metadata.get("resolve")
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(nodes, list):
        raise RuntimeError("archive-alone metadata resolved nodes are unavailable")
    transport_id = transport.get("id")
    lz4_id = lz4.get("id")
    if not isinstance(transport_id, str) or not isinstance(lz4_id, str):
        raise RuntimeError("archive-alone metadata package identity is malformed")
    transport_nodes = [
        node
        for node in nodes
        if isinstance(node, dict) and node.get("id") == transport_id
    ]
    if len(transport_nodes) != 1:
        raise RuntimeError("archive-alone metadata transport node is unavailable")
    dependencies = transport_nodes[0].get("deps")
    if not isinstance(dependencies, list) or lz4_id not in {
        dependency.get("pkg")
        for dependency in dependencies
        if isinstance(dependency, dict)
    }:
        raise RuntimeError("archive-alone metadata lost the vulnerable lz4 edge")


def condition_zenoh_archive(
    crate: str,
    extracted_paths: dict[str, Path],
    *,
    offline: bool,
    target: str,
    env: dict[str, str],
) -> tuple[list[str], dict[str, object]]:
    archive_root = extracted_paths[crate]
    manifest_path = archive_root / "Cargo.toml"
    lock_path = archive_root / "Cargo.lock"
    fallback = assert_unpatched_archive_fallback(
        crate,
        load_toml(manifest_path),
        load_toml(lock_path),
        sha256(lock_path),
    )
    local_patch_args = cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths)
    if not offline:
        fetch_locked_archive(
            manifest_path,
            local_patch_args,
            target=target,
            env=env,
            cwd=archive_root,
        )
    unpatched_metadata_command = [
        "cargo",
        "metadata",
        "--manifest-path",
        str(manifest_path),
        "--format-version",
        "1",
        "--locked",
        "--offline",
        "--filter-platform",
        target,
    ]
    unpatched_metadata_command.extend(local_patch_args)
    try:
        unpatched_metadata = json.loads(
            run_capture(unpatched_metadata_command, env=env, cwd=archive_root)
        )
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{crate} archive-alone cargo metadata is not JSON"
        ) from error
    if not isinstance(unpatched_metadata, dict):
        raise RuntimeError(f"{crate} archive-alone cargo metadata is not an object")
    validate_unpatched_zenoh_metadata(unpatched_metadata)
    fallback["resolution_observation"] = "EXECUTED_OBSERVED_VULNERABLE"

    patch_args = [*local_patch_args, *zenoh_backport_patch_args()]
    update = [
        "cargo",
        "update",
        "--manifest-path",
        str(manifest_path),
        "-p",
        f"zenoh-transport@{ZENOH_TRANSPORT_VERSION}",
        "--precise",
        ZENOH_TRANSPORT_VERSION,
    ]
    if offline:
        update.append("--offline")
    update.extend(patch_args)
    run(update, env=env, cwd=archive_root)
    validate_conditioned_zenoh_lock(load_toml(lock_path))
    if not offline:
        fetch_locked_archive(
            manifest_path,
            patch_args,
            target=target,
            env=env,
            cwd=archive_root,
        )

    metadata_command = [
        "cargo",
        "metadata",
        "--manifest-path",
        str(manifest_path),
        "--format-version",
        "1",
        "--locked",
        "--offline",
        "--filter-platform",
        target,
    ]
    metadata_command.extend(patch_args)
    try:
        metadata = json.loads(run_capture(metadata_command, env=env, cwd=archive_root))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{crate} cargo metadata is not JSON") from error
    if not isinstance(metadata, dict):
        raise RuntimeError(f"{crate} cargo metadata is not an object")
    validate_conditioned_zenoh_metadata(metadata)
    return patch_args, fallback


def self_test() -> None:
    import copy

    if parse_rustc_host(b"rustc 1.96.0\nhost: aarch64-apple-darwin\n") != (
        "aarch64-apple-darwin"
    ):
        raise AssertionError("rustc host parser lost the exact target")
    for hostile_host in (b"host: \n", b"host: bad/target\n", b"host: a\nhost: b\n"):
        try:
            parse_rustc_host(hostile_host)
        except RuntimeError:
            pass
        else:
            raise AssertionError("malformed rustc host output passed validation")

    with tempfile.TemporaryDirectory(prefix="ncp-package-path-selftest-") as tmp:
        root = Path(tmp)
        real_parent = root / "real source"
        real_crate = real_parent / "ncp-core"
        real_crate.mkdir(parents=True)
        detour = real_parent / "detour"
        detour.mkdir()
        aliased_paths = [detour / ".." / "ncp-core"]
        alias = root / "source-alias"
        try:
            alias.symlink_to(real_parent, target_is_directory=True)
        except OSError:
            pass
        else:
            aliased_paths.append(alias / "ncp-core")
        for aliased_path in aliased_paths:
            args = cargo_patch_args(("ncp-core",), {"ncp-core": aliased_path})
            if args[:1] != ["--config"] or len(args) != 2:
                raise AssertionError("Cargo patch arguments have an unexpected shape")
            prefix = "patch.crates-io.ncp-core.path="
            if not args[1].startswith(prefix):
                raise AssertionError(
                    "Cargo patch argument lost its exact dependency key"
                )
            encoded = args[1][len(prefix) :]
            if json.loads(encoded) != str(real_crate.resolve(strict=True)):
                raise AssertionError("Cargo patch path retained a filesystem alias")
        try:
            cargo_patch_args(("ncp-core",), {"ncp-core": root / "missing" / "ncp-core"})
        except RuntimeError:
            pass
        else:
            raise AssertionError("missing Cargo patch path passed canonicalization")

    exact_patch = zenoh_backport_patch_args()
    hostile_patches = {
        "absent": [],
        "wrong repository": [
            "--config",
            'patch.crates-io.zenoh-transport.git="https://example.invalid/fork"',
            "--config",
            (f'patch.crates-io.zenoh-transport.rev="{ZENOH_BACKPORT_REVISION}"'),
        ],
        "wrong revision": [
            "--config",
            f'patch.crates-io.zenoh-transport.git="{ZENOH_BACKPORT_GIT}"',
            "--config",
            f'patch.crates-io.zenoh-transport.rev="{"0" * 40}"',
        ],
    }
    validate_zenoh_backport_patch_args(exact_patch)
    for label, hostile in hostile_patches.items():
        try:
            validate_zenoh_backport_patch_args(hostile)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{label} Zenoh root patch passed validation")

    fallback_lock: dict[str, object] = {
        "package": [
            {
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": ZENOH_TRANSPORT_REGISTRY_CHECKSUM,
                "dependencies": ["lz4_flex"],
            },
            {
                "name": "lz4_flex",
                "version": VULNERABLE_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": VULNERABLE_LZ4_CHECKSUM,
            },
        ]
    }
    fallback = assert_unpatched_archive_fallback(
        "ncp-zenoh", {}, fallback_lock, "a" * 64
    )
    if fallback.get("advisory") != "RUSTSEC-2026-0041":
        raise AssertionError("archive fallback evidence lost the advisory identity")
    omitted = copy.deepcopy(fallback_lock)
    omitted["package"] = omitted["package"][:1]
    try:
        assert_unpatched_archive_fallback("ncp-zenoh", {}, omitted, "a" * 64)
    except RuntimeError:
        pass
    else:
        raise AssertionError("archive dependency omission passed validation")

    conditioned_lock: dict[str, object] = {
        "package": [
            {
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": ZENOH_BACKPORT_SOURCE,
                "dependencies": ["lz4_flex"],
            },
            {
                "name": "lz4_flex",
                "version": FIXED_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
                "checksum": FIXED_LZ4_CHECKSUM,
            },
        ]
    }
    validate_conditioned_zenoh_lock(conditioned_lock)
    hostile_locks: dict[str, dict[str, object]] = {}
    registry_fallback = copy.deepcopy(conditioned_lock)
    registry_fallback["package"][0]["source"] = CRATES_IO_SOURCE
    registry_fallback["package"][0]["checksum"] = ZENOH_TRANSPORT_REGISTRY_CHECKSUM
    hostile_locks["registry fallback"] = registry_fallback
    wrong_source_revision = copy.deepcopy(conditioned_lock)
    wrong_source_revision["package"][0]["source"] = (
        f"git+{ZENOH_BACKPORT_GIT}?rev={'0' * 40}#{'0' * 40}"
    )
    hostile_locks["wrong source revision"] = wrong_source_revision
    vulnerable_lock = copy.deepcopy(conditioned_lock)
    vulnerable_lock["package"][1]["version"] = VULNERABLE_LZ4_VERSION
    vulnerable_lock["package"][1]["checksum"] = VULNERABLE_LZ4_CHECKSUM
    hostile_locks["vulnerable dependency"] = vulnerable_lock
    wrong_checksum = copy.deepcopy(conditioned_lock)
    wrong_checksum["package"][1]["checksum"] = "0" * 64
    hostile_locks["wrong fixed checksum"] = wrong_checksum
    missing_edge = copy.deepcopy(conditioned_lock)
    missing_edge["package"][0]["dependencies"] = []
    hostile_locks["missing dependency edge"] = missing_edge
    for label, hostile in hostile_locks.items():
        try:
            validate_conditioned_zenoh_lock(hostile)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"{label} conditioned lock passed validation")

    transport_id = ZENOH_BACKPORT_SOURCE
    lz4_id = f"{CRATES_IO_SOURCE}#lz4_flex@{FIXED_LZ4_VERSION}"
    zenoh_id = f"{CRATES_IO_SOURCE}#zenoh@{ZENOH_TRANSPORT_VERSION}"
    metadata: dict[str, object] = {
        "packages": [
            {
                "id": transport_id,
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": ZENOH_BACKPORT_SOURCE,
                "rust_version": "1.81.0",
            },
            {
                "id": lz4_id,
                "name": "lz4_flex",
                "version": FIXED_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": zenoh_id,
                "name": "zenoh",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
            },
        ],
        "resolve": {
            "nodes": [
                {
                    "id": transport_id,
                    "features": ["transport_tcp"],
                    "deps": [{"pkg": lz4_id}],
                },
                {"id": zenoh_id, "features": ["transport_tcp"], "deps": []},
            ]
        },
    }
    validate_conditioned_zenoh_metadata(metadata)
    hostile_metadata = copy.deepcopy(metadata)
    hostile_metadata["packages"][0]["source"] = CRATES_IO_SOURCE
    try:
        validate_conditioned_zenoh_metadata(hostile_metadata)
    except RuntimeError:
        pass
    else:
        raise AssertionError("registry metadata fallback passed validation")
    hostile_metadata = copy.deepcopy(metadata)
    hostile_metadata["resolve"]["nodes"][0]["features"].append("transport_compression")
    try:
        validate_conditioned_zenoh_metadata(hostile_metadata)
    except RuntimeError:
        pass
    else:
        raise AssertionError("forbidden conditioned feature passed validation")

    fallback_transport_id = (
        f"{CRATES_IO_SOURCE}#zenoh-transport@{ZENOH_TRANSPORT_VERSION}"
    )
    fallback_lz4_id = f"{CRATES_IO_SOURCE}#lz4_flex@{VULNERABLE_LZ4_VERSION}"
    fallback_metadata: dict[str, object] = {
        "packages": [
            {
                "id": fallback_transport_id,
                "name": "zenoh-transport",
                "version": ZENOH_TRANSPORT_VERSION,
                "source": CRATES_IO_SOURCE,
            },
            {
                "id": fallback_lz4_id,
                "name": "lz4_flex",
                "version": VULNERABLE_LZ4_VERSION,
                "source": CRATES_IO_SOURCE,
            },
        ],
        "resolve": {
            "nodes": [
                {
                    "id": fallback_transport_id,
                    "deps": [{"pkg": fallback_lz4_id}],
                }
            ]
        },
    }
    validate_unpatched_zenoh_metadata(fallback_metadata)
    hostile_fallback_metadata = copy.deepcopy(fallback_metadata)
    hostile_fallback_metadata["resolve"]["nodes"][0]["deps"] = []
    try:
        validate_unpatched_zenoh_metadata(hostile_fallback_metadata)
    except RuntimeError:
        pass
    else:
        raise AssertionError(
            "incomplete archive fallback observation passed validation"
        )


def extract_archive(archive: Path, destination: Path, expected_prefix: str) -> Path:
    with tarfile.open(archive, "r:gz") as package:
        seen: set[str] = set()
        for member in package.getmembers():
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
                or not path.parts
                or path.parts[0] != expected_prefix
                or "\\" in member.name
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in member.name
                )
                or path.as_posix() != member.name.rstrip("/")
            ):
                raise RuntimeError(f"unsafe path in {archive.name}: {member.name}")
            canonical = path.as_posix()
            if canonical in seen:
                raise RuntimeError(f"duplicate path in {archive.name}: {member.name}")
            seen.add(canonical)
            if member.issym() or member.islnk():
                raise RuntimeError(f"link in {archive.name}: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise RuntimeError(
                    f"special archive entry in {archive.name}: {member.name}"
                )
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
        if (archive_root / license_name).read_bytes() != (
            ROOT / license_name
        ).read_bytes():
            raise RuntimeError(f"{crate} archive carries a stale {license_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "forbid even exact locked dependency prefetch; both the current and "
            "archive-fallback graphs must already be cached"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "atomically retain verified crate archives and a checksum receipt in this "
            "new directory; also rebuild and compare every archive"
        ),
    )
    parser.add_argument(
        "--source-revision",
        help="exact 40-hex source revision bound into an --output-dir receipt",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        if (
            args.offline
            or args.output_dir is not None
            or args.source_revision is not None
        ):
            parser.error("--self-test cannot be combined with package build options")
        self_test()
        print("Rust package archive checker self-test passed.")
        return 0
    output = args.output_dir.resolve() if args.output_dir is not None else None
    if output is None and args.source_revision is not None:
        parser.error("--source-revision requires --output-dir")
    if output is not None:
        if not SOURCE_REVISION.fullmatch(args.source_revision or ""):
            parser.error(
                "--output-dir requires --source-revision with exactly 40 lowercase hex"
            )
        if output.exists():
            parser.error(f"--output-dir must not already exist: {output}")
        if (ROOT / ".git").exists():
            parser.error(
                "retained archives must be built from build_candidate_dossier.py's "
                "Git archive, not a mutable worktree"
            )
        if os.environ.get("NCP_ARCHIVED_SOURCE_REVISION") != args.source_revision:
            parser.error(
                "retained archive source revision is not bound by the candidate builder"
            )
        output.parent.mkdir(parents=True, exist_ok=True)

    run([sys.executable, "scripts/sync_rust_package_testdata.py"])
    workspace = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    version = workspace["workspace"]["package"]["version"]

    with tempfile.TemporaryDirectory(prefix="ncp-package-selftest-") as tmp:
        temp = Path(tmp)
        package_target = temp / "package-target"
        extracted_parent = temp / "extracted"
        extracted_parent.mkdir()
        package_root = ROOT
        package_snapshot: dict[str, tuple[int, int, str]] | None = None
        if output is not None:
            package_root = temp / "package-source"
            copy_regular_tree(ROOT, package_root)
            inject_packaged_source_identity(package_root, args.source_revision or "")
            package_snapshot = tree_snapshot(package_root)
        source_paths = {crate: package_root / crate for crate in CRATES}
        extracted_paths: dict[str, Path] = {}
        archives: dict[str, Path] = {}

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
            run(command, cwd=package_root)

            archive = package_target / "package" / f"{crate}-{version}.crate"
            if not archive.is_file():
                raise RuntimeError(f"Cargo did not produce {archive}")
            archives[crate] = archive
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
        # Prove the source artifacts carry their identity without relying on the
        # candidate builder's private compiler environment.
        env.pop("NCP_BUILD_IDENTITY", None)
        expected_identity = args.source_revision or "unreleased-worktree"
        env["NCP_EXPECTED_BUILD_IDENTITY"] = expected_identity
        env["CARGO_TARGET_DIR"] = str(test_target)
        host_target = rustc_host(env)
        consumer_patch_args: dict[str, list[str]] = {}
        archive_fallbacks: list[dict[str, object]] = []
        for crate in ZENOH_CONDITIONAL_CRATES:
            patch_args, fallback = condition_zenoh_archive(
                crate,
                extracted_paths,
                offline=args.offline,
                target=host_target,
                env=env,
            )
            consumer_patch_args[crate] = patch_args
            archive_fallbacks.append(fallback)

        if not args.offline:
            for crate in CRATES:
                if crate in ZENOH_CONDITIONAL_CRATES:
                    continue
                fetch_locked_archive(
                    extracted_paths[crate] / "Cargo.toml",
                    cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths),
                    target=host_target,
                    env=env,
                    cwd=extracted_paths[crate],
                )

        for crate in TEST_CRATES:
            command = [
                "cargo",
                "test",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
                "--offline",
                "--target",
                host_target,
            ]
            command.extend(
                consumer_patch_args.get(
                    crate,
                    cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths),
                )
            )
            run(command, env=env, cwd=package_root)

        for crate in CHECK_CRATES:
            command = [
                "cargo",
                "check",
                "--manifest-path",
                str(extracted_paths[crate] / "Cargo.toml"),
                "--locked",
                "--offline",
                "--target",
                host_target,
            ]
            command.extend(
                consumer_patch_args.get(
                    crate,
                    cargo_patch_args(LOCAL_DEPENDENCIES[crate], extracted_paths),
                )
            )
            run(command, env=env, cwd=package_root)

        gateway_command = [
            "cargo",
            "run",
            "--quiet",
            "--manifest-path",
            str(extracted_paths["ncp-gateway"] / "Cargo.toml"),
            "--locked",
            "--offline",
            "--target",
            host_target,
        ]
        gateway_command.extend(consumer_patch_args["ncp-gateway"])
        gateway_command.extend(("--", "--identity-json"))
        gateway_identity = json.loads(
            run_capture(gateway_command, env=env, cwd=package_root)
        )
        contract = json.loads(
            (package_root / "contract" / "manifest.v1.json").read_text(encoding="utf-8")
        )
        expected_gateway_identity = {
            "package": "ncp-gateway",
            "package_version": version,
            "wire_version": contract["wire_version"],
            "compact_proto_hash": contract["wire_proto_contract_hash_fnv1a64"],
            "normative_contract_digest": contract["contract_digest_sha256"],
            "build_identity": expected_identity,
        }
        if gateway_identity != expected_gateway_identity:
            raise RuntimeError(
                "extracted gateway identity differs from its packaged source: "
                f"{gateway_identity!r} != {expected_gateway_identity!r}"
            )

        if output is not None:
            reproduction_target = temp / "reproduction-target"
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
                    str(reproduction_target),
                    "--offline",
                ]
                command.extend(
                    cargo_patch_args(LOCAL_DEPENDENCIES[crate], source_paths)
                )
                run(command, cwd=package_root)
                repeated = reproduction_target / "package" / archives[crate].name
                if sha256(repeated) != sha256(archives[crate]):
                    raise RuntimeError(
                        f"{crate} archive differs across two source-identical builds"
                    )

            if (
                package_snapshot is None
                or tree_snapshot(package_root) != package_snapshot
            ):
                raise RuntimeError(
                    "Cargo package qualification mutated its staged source tree"
                )

            stage = Path(
                tempfile.mkdtemp(prefix=".ncp-rust-artifacts-", dir=output.parent)
            )
            try:
                artifact_records: list[dict[str, object]] = []
                for crate in CRATES:
                    destination = stage / archives[crate].name
                    shutil.copyfile(archives[crate], destination)
                    artifact_records.append(
                        {
                            "crate": crate,
                            "path": destination.name,
                            "size_bytes": destination.stat().st_size,
                            "sha256": sha256(destination),
                        }
                    )
                receipt = {
                    "schema": RUST_PACKAGE_RECEIPT_SCHEMA,
                    "source_revision": args.source_revision,
                    "embedded_build_identity": expected_identity,
                    "candidate_version": version,
                    "reproducibility_comparison": "PASS",
                    "zenoh_consumption": {
                        "status": "CONDITIONAL_PASS",
                        "condition": "EXACT_CONSUMING_ROOT_PATCH_REQUIRED",
                        "package_self_contained": False,
                        "self_contained_distribution_gate": "OPEN_FAIL_CLOSED",
                        "decision": "NO_GO",
                        "release_authorized": False,
                        "affected_archives": list(ZENOH_CONDITIONAL_CRATES),
                        "archive_fallbacks": archive_fallbacks,
                        "qualifying_root_patch": {
                            "repository": ZENOH_BACKPORT_GIT,
                            "revision": ZENOH_BACKPORT_REVISION,
                            "cargo_source": ZENOH_BACKPORT_SOURCE,
                            "lz4_flex_version": FIXED_LZ4_VERSION,
                            "lz4_flex_checksum_sha256": FIXED_LZ4_CHECKSUM,
                            "cargo_verifies_git_signature": False,
                        },
                    },
                    "archives": artifact_records,
                }
                (stage / "rust-package-receipt.json").write_text(
                    json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.replace(stage, output)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise

    # Catch a canonical fixture changing while the longer archive tests ran.
    run([sys.executable, "scripts/sync_rust_package_testdata.py"])
    print(
        "Rust candidate archives verified; ncp-zenoh and ncp-gateway consumption "
        "is conditional on the exact consuming-root backport. The vulnerable "
        "fallback was not compiled; qualification compiled offline. "
        "Self-contained Zenoh package distribution remains NO_GO."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
