#!/usr/bin/env -S python3 -I
"""Build a checksummed, reproducibility-compared candidate artifact dossier.

The builder consumes only one exact committed Git tree, binds package build
identity to that revision, and never tags, signs, or publishes.  Hosted CI may
attest its subjects, but release authorization and independent reproduction stay
separate gates.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import tomllib

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
RETAINED_CONDITIONED_LOCKS = {
    "ncp-zenoh": "qualification/ncp-zenoh.conditioned.Cargo.lock",
    "ncp-gateway": "qualification/ncp-gateway.conditioned.Cargo.lock",
}
RETAINED_LZ4_CRATE = "qualification/lz4_flex-0.11.6.crate"
RETAINED_TWOX_CRATE = "qualification/twox-hash-2.1.3.crate"
RETAINED_UPSTREAM_TRANSPORT_CRATE = "qualification/zenoh-transport-1.9.0.crate"
ARCHIVE_FILE_MANIFEST_SCHEMA = "ncp.archived-source-file-manifest.v1"
NPM_RELEASE_RECEIPT_SCHEMA = "ncp.npm-release-build-receipt.v2"
TYPESCRIPT_CONTROL_PATH = "security/toolchains/typescript-5.9.2.v1.json"
TYPESCRIPT_CONTROL_SCHEMA = "ncp.reviewed-npm-build-tool.v1"
TYPESCRIPT_REGISTRY_TARBALL_EVIDENCE = "REVIEWED_EXPECTED_DIGEST_NOT_BUILD_OBSERVED"
NPM_UNREVIEWED_PACKAGE_GRAPH_FIELDS = (
    "dependencies",
    "optionalDependencies",
    "peerDependencies",
    "peerDependenciesMeta",
    "bundleDependencies",
    "bundledDependencies",
    "workspaces",
    "overrides",
    "resolutions",
    "trustedDependencies",
    "patchedDependencies",
    "catalog",
    "catalogs",
    "packageExtensions",
)
SUPPLY_FILES = (
    "inventory.v1.json",
    "license-report.v1.json",
    "provenance-policy.v1.json",
    "sbom.cdx.json",
    "vulnerability-report.v1.json",
)
PACKAGE_SUBJECT_ROLES = (
    "rust:ncp-core",
    "rust:ncp-zenoh",
    "rust:ncp-cpp",
    "rust:ncp-python",
    "rust:ncp-gateway",
    "python:wheel",
    "python:sdist",
    "npm:repository-root",
    "npm:ncp-ts",
)
FULL_WORKSPACE_MEMBERS = (
    'members = ["ncp-core", "ncp-zenoh", "ncp-gateway", "ncp-python", "ncp-cpp"]'
)
SDIST_WORKSPACE_MEMBERS = 'members = ["ncp-core", "ncp-python"]'
PYTHON_WHEEL_BUILD_ARGS = (
    "maturin",
    "build",
    "-m",
    "ncp-python/Cargo.toml",
    "--features",
    "extension-module",
    "--release",
    "--locked",
    "--offline",
    "--strip",
)
PYTHON_WHEEL_CARGO_ENVIRONMENT = {
    "CARGO_INCREMENTAL": "0",
    "CARGO_NET_OFFLINE": "true",
}
OUTER_CARGO_CONFIG = (
    "net.git-fetch-with-cli=false",
    "net.retry=3",
    "http.timeout=120",
    "http.low-speed-limit=1",
)
AUTHOR = {"name": "Sepehr Mahmoudian"}
REPRODUCIBILITY_COMPARISONS = {
    "rust_source_archives": "LOCAL_PROCESS_PASS_NOT_REEXECUTED",
    "python_wheel_same_platform": "LOCAL_PROCESS_PASS_NOT_REEXECUTED",
    "python_sdist_same_platform": "LOCAL_PROCESS_PASS_NOT_REEXECUTED",
    "python_sdist_build_install_smoke": "LOCAL_PROCESS_PASS_NOT_REEXECUTED",
    "npm_tarballs": "LOCAL_PROCESS_PASS_NOT_REEXECUTED",
}
DOSSIER_VERIFICATION_BOUNDARY = {
    "verifier_recomputed_from_retained_artifacts": [
        "EXACT_DOSSIER_TREE_FILE_HASHES_AND_SIZES",
        "RUST_CRATE_IDENTITIES_AND_EMBEDDED_SOURCE_LITERAL",
        "PYTHON_NPM_FILENAME_AND_RECEIPT_CONSISTENCY",
        "RUST_RETAINED_ARTIFACT_RECEIPT",
        "PACKAGE_SUBJECT_AND_CROSS_RECEIPT_CONSISTENCY",
    ],
    "builder_local_process_attestations": [
        "SOURCE_TO_PACKAGE_DERIVATION",
        "REPRODUCIBILITY_COMPARISONS",
        "PYTHON_INSTALL_AND_BEHAVIOR_PROBES",
        "NPM_BUILD_AND_RUST_IDENTITY_PROBE",
        "OUTER_PREFLIGHT_AND_SOURCE_POINT_CHECKS",
    ],
    "verify_dossier_reexecution": "NOT_PERFORMED",
    "source_to_package_rebuild": "NOT_PERFORMED",
    "independent_reproduction": False,
    "release_authorized": False,
}
SBOM_SCOPE = (
    "Workspace source and resolved dependency inventory; it is retained with the "
    "aggregate dossier and is not an artifact-specific SBOM."
)
CLAIM_BOUNDARY = (
    "Candidate-only build evidence. Archive-alone Cargo metadata resolution was "
    "executed without compilation and observed the vulnerable registry Zenoh/lz4 "
    "fallback. The exact consuming-root transport backport produced only a "
    "CONDITIONAL_PASS; the "
    "self-contained distribution gate remains OPEN_FAIL_CLOSED and NO_GO. No tag, "
    "registry publication, release authorization, independent reproduction, or "
    "signature is implied. Outer preflight, Python, and npm processes receive a "
    "caller-stripped environment with fresh HOME, TMPDIR, Cargo home, and npm cache "
    "paths, disabled user Git/pip/npm configuration, and an exact locked Cargo fetch "
    "before outer compilation is forced offline. The existing Rustup toolchain, "
    "system PATH, installed tools, Node modules, and host trust store remain inputs. "
    "Host network, process, credential, and filesystem isolation are not claimed."
)
DOSSIER_KEYS = {
    "schema",
    "source_revision",
    "source_tree",
    "source_date_epoch",
    "candidate_version",
    "wire_version",
    "normative_contract_digest_sha256",
    "conformance_corpus_digest_sha256",
    "author",
    "release_authorized",
    "reproducibility_comparisons",
    "source_derivations",
    "verification_boundary",
    "toolchain_receipt",
    "artifacts",
    "package_subjects",
    "python_install_receipts",
    "sbom_scope",
    "claim_boundary",
}
TOOLCHAIN_KEYS = {
    "platform",
    "runner_image_os",
    "runner_image_version",
    "cargo",
    "cargo_invocation_sha256",
    "rustc",
    "rustc_verbose",
    "rustc_invocation_sha256",
    "python",
    "python_binary_sha256",
    "git",
    "git_binary_sha256",
    "pip",
    "maturin",
    "node",
    "node_binary_sha256",
    "npm",
    "npm_invocation_sha256",
    "bun",
    "cargo_deny",
}
MAX_CONTROL_JSON_BYTES = 8 * 1024 * 1024
MAX_CHECKSUM_MANIFEST_BYTES = 64 * 1024
MAX_DOSSIER_REGULAR_FILES = 24
MAX_DOSSIER_ENTRIES = 64
MAX_DOSSIER_DEPTH = 6
MAX_DOSSIER_PATH_BYTES = 512
MAX_DOSSIER_FILE_BYTES = 256 * 1024 * 1024
MAX_DOSSIER_TOTAL_BYTES = 1024 * 1024 * 1024
MAX_PACKAGE_SUBJECT_TOTAL_BYTES = 768 * 1024 * 1024
MAX_PACKAGE_SUBJECT_BYTES = {
    **{role: 64 * 1024 * 1024 for role in PACKAGE_SUBJECT_ROLES[:5]},
    "python:wheel": 128 * 1024 * 1024,
    "python:sdist": 256 * 1024 * 1024,
    "npm:repository-root": 64 * 1024 * 1024,
    "npm:ncp-ts": 64 * 1024 * 1024,
}
HASH_CHUNK_BYTES = 1024 * 1024
MAX_SOURCE_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_SOURCE_ARCHIVE_ENTRIES = 20_000
MAX_SOURCE_ARCHIVE_FILES = 10_000
MAX_SOURCE_ARCHIVE_FILE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_ARCHIVE_EXPANDED_BYTES = 1024 * 1024 * 1024
MAX_TYPESCRIPT_CONTROL_BYTES = 64 * 1024
MAX_TYPESCRIPT_PACKAGE_FILES = 1_000
MAX_TYPESCRIPT_PACKAGE_FILE_BYTES = 64 * 1024 * 1024
MAX_TYPESCRIPT_PACKAGE_BYTES = 256 * 1024 * 1024


class DossierError(ValueError):
    """The candidate dossier could not be built without weakening its boundary."""


def _source_derivations(revision: str) -> list[dict[str, Any]]:
    """Return the exact reviewed staging transformations for package identity."""

    return [
        {
            "artifact_roles": ["rust:ncp-core", "python:sdist"],
            "source_path": "ncp-core/src/contract_identity.rs",
            "operation": "replace-exact-sentinel-literal",
            "input": '    None => "unreleased-worktree",',
            "output": f'    None => "{revision}",',
            "boundary": (
                "The exact committed Git tree remains the immutable input; packaging "
                "uses a disposable identity-bearing derivative with only this "
                "replacement."
            ),
        },
        {
            "artifact_roles": ["python:wheel"],
            "source_path": "ncp-core/src/contract_identity.rs",
            "operation": "set-exact-compile-time-build-identity",
            "input": "NCP_BUILD_IDENTITY unset",
            "output": f"NCP_BUILD_IDENTITY={revision}",
            "boundary": (
                "The wheel uses the exact committed Git-tree source bytes. Its "
                "disposable build environment supplies the source revision through "
                "ncp-core's compile-time NCP_BUILD_IDENTITY input; the built wheel "
                "must report that exact identity."
            ),
        },
        {
            "artifact_roles": ["python:sdist"],
            "source_path": "Cargo.toml and Cargo.lock",
            "operation": "reduce-packaged-workspace-and-refresh-lock-offline",
            "input": FULL_WORKSPACE_MEMBERS,
            "output": (
                f"{SDIST_WORKSPACE_MEMBERS}; force offline Cargo.lock garbage "
                "collection by precisely updating the unchanged ncp-python version, "
                "preserve every retained package identity and non-edge field, then "
                "require the refreshed lock unchanged under --locked --offline with "
                "an exact all-feature package closure"
            ),
            "boundary": (
                "The sdist contains only ncp-core and ncp-python. Its derivative "
                "workspace and lock are prepared before packaging so the shipped "
                "lock exactly resolves that closed source set; no dependency is "
                "fetched under CARGO_NET_OFFLINE=true and the exact committed Git "
                "tree remains the immutable input."
            ),
        },
        {
            "artifact_roles": ["npm:repository-root", "npm:ncp-ts"],
            "source_path": "ncp-ts/src/contract-identity.ts",
            "operation": "replace-exact-build-identity-declaration",
            "input": "export const NCP_BUILD_IDENTITY = 'unreleased-worktree'",
            "output": f"export const NCP_BUILD_IDENTITY = '{revision}'",
            "boundary": (
                "The exact committed Git tree remains the immutable input; packaging "
                "uses a disposable identity-bearing derivative with only this "
                "replacement."
            ),
        },
    ]


def _strict_json_object(raw: str, context: str) -> dict[str, Any]:
    """Decode one JSON object while rejecting duplicate keys at every depth."""

    if len(raw.encode("utf-8")) > MAX_CONTROL_JSON_BYTES:
        raise DossierError(f"{context} exceeds the candidate JSON byte limit")

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise DossierError(f"{context} contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_non_finite(token: str) -> Any:
        raise DossierError(f"{context} contains non-finite JSON number {token!r}")

    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_non_finite,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise DossierError(f"cannot parse {context}: {error}") from error
    if not isinstance(value, dict):
        raise DossierError(f"{context} must contain one JSON object")
    return value


def _assert_no_local_absolute_paths(value: Any, *, context: str) -> None:
    if isinstance(value, str):
        if (
            Path(value).is_absolute()
            or value.startswith("\\")
            or value.casefold().startswith("file:")
            or re.match(r"^[A-Za-z]:[\\/]", value)
        ):
            raise DossierError(f"{context} contains a local absolute path")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_no_local_absolute_paths(key, context=context)
            _assert_no_local_absolute_paths(item, context=context)
        return
    if isinstance(value, list):
        for item in value:
            _assert_no_local_absolute_paths(item, context=context)


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> bytes:
    print("+", " ".join(command), flush=True)
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
        )
    except OSError as error:
        raise DossierError(f"cannot execute {command[0]}: {error}") from error
    if process.returncode != 0:
        detail = ""
        if capture and process.stderr is not None:
            detail = process.stderr.decode("utf-8", "replace").strip()
        raise DossierError(
            f"{' '.join(command)} failed with status {process.returncode}"
            + (f": {detail}" if detail else "")
        )
    return process.stdout or b""


def _git_invocation() -> str:
    candidate = shutil.which("git", path=os.environ.get("PATH"))
    if candidate is None:
        raise DossierError("required Git executable is unavailable")
    path = Path(candidate)
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as error:
        raise DossierError(f"cannot resolve Git executable: {error}") from error
    if not stat.S_ISREG(mode):
        raise DossierError("Git executable does not resolve to a regular file")
    return str(resolved)


def _git_environment() -> dict[str, str]:
    system_path = os.pathsep.join(
        path
        for path in ("/usr/bin", "/bin", "/usr/sbin", "/sbin")
        if Path(path).is_dir()
    )
    return {
        "PATH": system_path,
        "HOME": str(ROOT),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "GCM_INTERACTIVE": "never",
    }


def _git(*args: str) -> bytes:
    return _run(
        [_git_invocation(), *args],
        cwd=ROOT,
        env=_git_environment(),
        capture=True,
    )


def _sha256(path: Path, *, maximum: int | None = None) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DossierError(
            f"cannot open regular file for hashing {path}: {error}"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise DossierError(f"hash input is special: {path}")
        if maximum is not None and before.st_size > maximum:
            raise DossierError(f"hash input exceeds the {maximum}-byte limit: {path}")
        observed = 0
        while chunk := os.read(descriptor, HASH_CHUNK_BYTES):
            observed += len(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
        ) or observed != before.st_size:
            raise DossierError(f"hash input changed while it was read: {path}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def _regular_files(
    root: Path,
    *,
    max_files: int | None = None,
    max_entries: int | None = None,
    max_depth: int | None = None,
) -> list[Path]:
    files: list[Path] = []
    entries = 0

    def walk_error(error: OSError) -> None:
        raise DossierError(f"cannot traverse artifact tree {root}: {error}") from error

    for directory, directories, names in os.walk(
        root,
        followlinks=False,
        onerror=walk_error,
    ):
        directory_path = Path(directory)
        depth = len(directory_path.relative_to(root).parts)
        if max_depth is not None and depth > max_depth:
            raise DossierError(f"artifact tree exceeds depth {max_depth}: {directory}")
        directories.sort()
        names.sort()
        entries += len(directories) + len(names)
        if max_entries is not None and entries > max_entries:
            raise DossierError(f"artifact tree exceeds the {max_entries}-entry limit")
        for name in directories:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise DossierError(
                    f"artifact tree contains a linked/special directory: {path}"
                )
        for name in names:
            path = directory_path / name
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode):
                raise DossierError(f"artifact tree contains a link: {path}")
            if not stat.S_ISREG(mode):
                raise DossierError(f"artifact tree contains a special entry: {path}")
            if path.stat().st_nlink != 1:
                raise DossierError(f"artifact tree contains a hardlinked file: {path}")
            files.append(path)
            if max_files is not None and len(files) > max_files:
                raise DossierError(f"artifact tree exceeds the {max_files}-file limit")
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    return files


def _assert_file_size_budget(
    files: list[Path],
    *,
    context: str,
    maximum_file_bytes: int,
    maximum_total_bytes: int,
) -> None:
    total = 0
    for path in files:
        size = path.lstat().st_size
        if size > maximum_file_bytes:
            raise DossierError(
                f"{context} file exceeds the {maximum_file_bytes}-byte limit: {path}"
            )
        total += size
        if total > maximum_total_bytes:
            raise DossierError(
                f"{context} exceeds the {maximum_total_bytes}-byte aggregate limit"
            )


def _bounded_utf8(path: Path, *, context: str, limit: int) -> str:
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
    except OSError as error:
        raise DossierError(f"cannot read {context}: {error}") from error
    if len(raw) > limit:
        raise DossierError(f"{context} exceeds the {limit}-byte limit")
    try:
        return raw.decode("utf-8", "strict")
    except UnicodeError as error:
        raise DossierError(f"cannot decode {context} as UTF-8: {error}") from error


def _assert_exact_file_parent_directories(root: Path, files: list[Path]) -> None:
    expected: set[str] = set()
    for path in files:
        relative = path.relative_to(root)
        for parent in relative.parents:
            if parent != Path("."):
                expected.add(parent.as_posix())
    actual: set[str] = set()

    def walk_error(error: OSError) -> None:
        raise DossierError(
            f"cannot traverse artifact directories {root}: {error}"
        ) from error

    for directory, directories, _names in os.walk(
        root,
        followlinks=False,
        onerror=walk_error,
    ):
        directory_path = Path(directory)
        for name in directories:
            actual.add((directory_path / name).relative_to(root).as_posix())
    if actual != expected:
        raise DossierError(
            "candidate dossier directory set differs from exact file parents: "
            f"extra={sorted(actual - expected)!r}, missing={sorted(expected - actual)!r}"
        )


def _copy_regular_tree(source: Path, destination: Path) -> None:
    destination.mkdir()
    for path in _regular_files(source):
        relative = path.relative_to(source)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        output.chmod(path.lstat().st_mode & 0o777)


def _materialize_validated_tar(
    package: tarfile.TarFile,
    members: list[tarfile.TarInfo],
    destination: Path,
    *,
    context: str,
) -> None:
    """Write a prevalidated regular-file/directory tar without extractall()."""

    for member in members:
        relative = Path(member.name)
        output = destination / relative
        try:
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
                output.chmod(0o755)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            source = package.extractfile(member)
            if source is None:
                raise DossierError(f"{context} file cannot be read: {member.name!r}")
            remaining = member.size
            with source, output.open("xb") as stream:
                while remaining:
                    chunk = source.read(min(HASH_CHUNK_BYTES, remaining))
                    if not chunk:
                        raise DossierError(
                            f"{context} file ended early: {member.name!r}"
                        )
                    stream.write(chunk)
                    remaining -= len(chunk)
                if source.read(1):
                    raise DossierError(
                        f"{context} file exceeds its header size: {member.name!r}"
                    )
            output.chmod(0o755 if member.mode & 0o111 else 0o644)
        except DossierError:
            raise
        except OSError as error:
            raise DossierError(
                f"cannot materialize {context} path {member.name!r}: {error}"
            ) from error


def _directory_snapshot(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            path.lstat().st_mode & 0o777,
            path.stat().st_size,
            _sha256(path),
        )
        for path in _regular_files(root)
    }


def _inject_packaged_source_identity(source: Path, revision: str) -> None:
    identity = source / "ncp-core" / "src" / "contract_identity.rs"
    text = identity.read_text(encoding="utf-8")
    sentinel = '    None => "unreleased-worktree",'
    replacement = f'    None => "{revision}",'
    if text.count(sentinel) != 1 or revision in text:
        raise DossierError(
            "generated Rust build-identity sentinel is missing, duplicated, or pre-injected"
        )
    identity.write_text(text.replace(sentinel, replacement), encoding="utf-8")


def _reduce_sdist_workspace(source: Path) -> None:
    manifest = source / "Cargo.toml"
    text = manifest.read_text(encoding="utf-8")
    if text.count(FULL_WORKSPACE_MEMBERS) != 1 or SDIST_WORKSPACE_MEMBERS in text:
        raise DossierError(
            "full workspace member declaration is missing, duplicated, or already reduced"
        )
    manifest.write_text(
        text.replace(FULL_WORKSPACE_MEMBERS, SDIST_WORKSPACE_MEMBERS),
        encoding="utf-8",
    )


def _toml(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise DossierError(f"cannot parse candidate TOML {path}: {error}") from error
    if not isinstance(value, dict):
        raise DossierError(f"candidate TOML {path} is not a table")
    return value


def _lock_package_records(path: Path) -> dict[tuple[str, str, str], dict[str, Any]]:
    value = _toml(path)
    packages = value.get("package")
    if not isinstance(packages, list) or not packages:
        raise DossierError(f"candidate lock {path} has no package records")
    records: dict[tuple[str, str, str], dict[str, Any]] = {}
    for number, package in enumerate(packages):
        if not isinstance(package, dict):
            raise DossierError(f"candidate lock {path} package {number} is not a table")
        name = package.get("name")
        version = package.get("version")
        source = package.get("source", "")
        if not all(isinstance(item, str) and item for item in (name, version)) or (
            not isinstance(source, str)
        ):
            raise DossierError(
                f"candidate lock {path} package {number} has an invalid identity"
            )
        identity = (name, version, source)
        if identity in records:
            raise DossierError(
                f"candidate lock {path} repeats package identity {identity!r}"
            )
        records[identity] = {
            key: value for key, value in package.items() if key != "dependencies"
        }
    return records


def _sdist_workspace_version(source: Path) -> str:
    workspace = _toml(source / "Cargo.toml").get("workspace")
    python_package = _toml(source / "ncp-python" / "Cargo.toml").get("package")
    if not isinstance(workspace, dict) or not isinstance(python_package, dict):
        raise DossierError("Python sdist workspace/package metadata is incomplete")
    workspace_package = workspace.get("package")
    version = (
        workspace_package.get("version")
        if isinstance(workspace_package, dict)
        else None
    )
    if (
        not isinstance(version, str)
        or not version
        or python_package.get("name") != "ncp-python"
        or python_package.get("version") != {"workspace": True}
    ):
        raise DossierError("Python sdist does not inherit one exact workspace version")
    return version


def _metadata_package_identities(raw: bytes) -> set[tuple[str, str, str]]:
    try:
        value = _strict_json_object(
            raw.decode("utf-8", "strict"), "locked Python sdist Cargo metadata"
        )
    except UnicodeError as error:
        raise DossierError("locked Python sdist metadata is not UTF-8") from error
    packages = value.get("packages")
    if not isinstance(packages, list) or not packages:
        raise DossierError("locked Python sdist metadata has no packages")
    identities: set[tuple[str, str, str]] = set()
    for number, package in enumerate(packages):
        if not isinstance(package, dict):
            raise DossierError(
                f"locked Python sdist metadata package {number} is not an object"
            )
        name = package.get("name")
        version = package.get("version")
        source = package.get("source") or ""
        if not all(isinstance(item, str) and item for item in (name, version)) or (
            not isinstance(source, str)
        ):
            raise DossierError(
                f"locked Python sdist metadata package {number} has an invalid identity"
            )
        identity = (name, version, source)
        if identity in identities:
            raise DossierError(
                f"locked Python sdist metadata repeats package {identity!r}"
            )
        identities.add(identity)
    return identities


def _locked_sdist_metadata(
    source: Path, environment: dict[str, str]
) -> set[tuple[str, str, str]]:
    raw = _run(
        [
            "cargo",
            "metadata",
            "--manifest-path",
            "ncp-python/Cargo.toml",
            "--format-version",
            "1",
            "--offline",
            "--locked",
            "--all-features",
        ],
        cwd=source,
        env=environment,
        capture=True,
    )
    return _metadata_package_identities(raw)


def _refresh_sdist_lock(source: Path, environment: dict[str, str]) -> None:
    before = _directory_snapshot(source)
    lock = source / "Cargo.lock"
    before_packages = _lock_package_records(lock)
    version = _sdist_workspace_version(source)
    _run(
        [
            "cargo",
            "update",
            "--manifest-path",
            "ncp-python/Cargo.toml",
            "--offline",
            "--package",
            f"ncp-python@{version}",
            "--precise",
            version,
        ],
        cwd=source,
        env=environment,
        capture=True,
    )
    after_refresh = _directory_snapshot(source)
    after_packages = _lock_package_records(lock)
    changed = {
        path
        for path in set(before) | set(after_refresh)
        if before.get(path) != after_refresh.get(path)
    }
    if changed != {"Cargo.lock"}:
        raise DossierError(
            "offline sdist lock refresh changed an unexpected source set: "
            f"{sorted(changed)!r}"
        )
    if not set(after_packages) < set(before_packages) or any(
        record != before_packages[identity]
        for identity, record in after_packages.items()
    ):
        raise DossierError(
            "offline sdist lock refresh changed a retained package identity or "
            "non-edge field, added a package, or failed to prune one"
        )
    if _locked_sdist_metadata(source, environment) != set(after_packages):
        raise DossierError(
            "pruned Python sdist lock differs from its all-feature metadata closure"
        )
    if _directory_snapshot(source) != after_refresh:
        raise DossierError("locked sdist metadata verification mutated its source")


def _verify_sdist_workspace(source: Path, environment: dict[str, str]) -> None:
    manifest = (source / "Cargo.toml").read_text(encoding="utf-8")
    if (
        manifest.count(SDIST_WORKSPACE_MEMBERS) != 1
        or FULL_WORKSPACE_MEMBERS in manifest
    ):
        raise DossierError("Python sdist workspace membership is not exact")
    before = _directory_snapshot(source)
    lock_packages = _lock_package_records(source / "Cargo.lock")
    if _locked_sdist_metadata(source, environment) != set(lock_packages):
        raise DossierError(
            "Python sdist lock contains packages outside its all-feature metadata closure"
        )
    if _directory_snapshot(source) != before:
        raise DossierError("locked Python sdist verification mutated its source")


def _prepare_sdist_source(
    source: Path, revision: str, environment: dict[str, str]
) -> None:
    _inject_packaged_source_identity(source, revision)
    _reduce_sdist_workspace(source)
    _refresh_sdist_lock(source, environment)


def _assert_packaged_source_identity(source: Path, revision: str) -> None:
    identity = source / "ncp-core" / "src" / "contract_identity.rs"
    text = identity.read_text(encoding="utf-8")
    if text.count(f'    None => "{revision}",') != 1 or (
        '    None => "unreleased-worktree",' in text
    ):
        raise DossierError("packaged source does not carry the exact build identity")


def _json(path: Path) -> dict[str, Any]:
    raw = _bounded_utf8(path, context=str(path), limit=MAX_CONTROL_JSON_BYTES)
    return _strict_json_object(raw, str(path))


def _json_from_git(revision: str, path: str) -> dict[str, Any]:
    try:
        raw = _git("show", f"{revision}:{path}").decode("utf-8", "strict")
    except UnicodeError as error:
        raise DossierError(f"committed {path} is not valid JSON: {error}") from error
    return _strict_json_object(raw, f"committed {path}")


def _require_exact_policy_bytes(
    *, revision: str, path: str, committed: bytes, running: bytes
) -> None:
    if committed != running:
        raise DossierError(f"running {path} differs from source revision {revision}")


def _exact_source(revision: str) -> tuple[str, int]:
    if not SOURCE_REVISION.fullmatch(revision):
        raise DossierError(
            "source revision must be exactly 40 lowercase hexadecimal characters"
        )
    head = _git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if head != revision:
        raise DossierError(f"source revision {revision} is not exact HEAD {head}")
    execution_policy_paths = (
        "scripts/build_candidate_dossier.py",
        "scripts/check_rust_packages.py",
        "ncp-ts/scripts/build-release.mjs",
        "security/backports/zenoh-transport-lz4-backport.v1.json",
    )
    for path in execution_policy_paths:
        try:
            running = (ROOT / path).read_bytes()
            committed = _git("show", f"{revision}:{path}")
        except OSError as error:
            raise DossierError(
                f"cannot read running execution policy {path}"
            ) from error
        _require_exact_policy_bytes(
            revision=revision,
            path=path,
            committed=committed,
            running=running,
        )
    tree = _git("rev-parse", f"{revision}^{{tree}}").decode().strip()
    timestamp_text = _git("show", "-s", "--format=%ct", revision).decode().strip()
    if not timestamp_text.isdigit():
        raise DossierError("Git commit timestamp is malformed")
    return tree, int(timestamp_text)


def _verify_committed_rust_receipt(
    products: Path, *, version: str, revision: str
) -> dict[str, Any]:
    """Run the exact committed receipt verifier in an isolated child interpreter."""

    if SOURCE_REVISION.fullmatch(revision) is None:
        raise DossierError("Rust receipt policy revision is malformed")
    policy_paths = (
        "scripts/check_rust_packages.py",
        "security/backports/zenoh-transport-lz4-backport.v1.json",
    )
    with tempfile.TemporaryDirectory(prefix="ncp-committed-rust-policy-") as tmp:
        policy_root = Path(tmp)
        for path in policy_paths:
            destination = policy_root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(_git("show", f"{revision}:{path}"))
        module_path = policy_root / "scripts" / "check_rust_packages.py"
        environment = {
            "PATH": _git_environment()["PATH"],
            "HOME": str(policy_root),
            "TMPDIR": str(policy_root),
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
        }
        raw = _run(
            [
                sys.executable,
                "-I",
                str(module_path),
                "--verify-retained-receipt",
                str(products.resolve(strict=True)),
                "--candidate-version",
                version,
                "--receipt-revision",
                revision,
            ],
            cwd=policy_root,
            env=environment,
            capture=True,
        ).decode("utf-8", "strict")
        value = _strict_json_object(raw, "isolated committed Rust receipt verifier")
    if not isinstance(value, dict):
        raise DossierError("committed Rust receipt verifier returned no object")
    return value


def _exact_git_tree_entries(
    revision: str,
) -> tuple[str, dict[str, tuple[str, str, int]]]:
    """Return exact regular-blob mode/object identities for one replacement-free tree."""

    object_format = (
        _git("rev-parse", "--show-object-format").decode("ascii", "strict").strip()
    )
    object_lengths = {"sha1": 40, "sha256": 64}
    if object_format not in object_lengths:
        raise DossierError(f"unsupported Git object format {object_format!r}")
    raw = _git("ls-tree", "-r", "-z", "-l", "--full-tree", revision)
    entries: dict[str, tuple[str, str, int]] = {}
    total_bytes = 0
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            metadata, encoded_path = record.split(b"\t", 1)
            mode, object_type, object_id, size_text = metadata.decode(
                "ascii", "strict"
            ).split()
            path_text = encoded_path.decode("utf-8", "strict")
        except (UnicodeError, ValueError) as error:
            raise DossierError("Git tree contains a malformed entry") from error
        path = Path(path_text)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "." in path.parts
            or not path.parts
            or "\\" in path_text
            or any(
                ord(character) < 32 or ord(character) == 127 for character in path_text
            )
            or path.as_posix() != path_text
        ):
            raise DossierError(f"Git tree contains unsafe path {path_text!r}")
        if (
            object_type != "blob"
            or mode not in {"100644", "100755"}
            or len(object_id) != object_lengths[object_format]
            or re.fullmatch(r"[0-9a-f]+", object_id) is None
            or not size_text.isdigit()
        ):
            raise DossierError(
                f"candidate Git tree contains a link, submodule, or unsupported entry: "
                f"{path_text!r} ({mode} {object_type})"
            )
        if path_text in entries:
            raise DossierError(f"Git tree repeats path {path_text!r}")
        size = int(size_text)
        if size > MAX_SOURCE_ARCHIVE_FILE_BYTES:
            raise DossierError(
                f"candidate Git blob exceeds its byte limit: {path_text!r}"
            )
        total_bytes += size
        if total_bytes > MAX_SOURCE_ARCHIVE_EXPANDED_BYTES:
            raise DossierError("candidate Git tree exceeds its expanded-byte limit")
        entries[path_text] = (mode, object_id, size)
        if len(entries) > MAX_SOURCE_ARCHIVE_FILES:
            raise DossierError("candidate Git tree exceeds its regular-file limit")
    if not entries:
        raise DossierError("candidate Git tree contains no regular files")
    return object_format, entries


def _extract_git_archive(
    revision: str, destination: Path, archive: Path
) -> list[dict[str, Any]]:
    object_format, expected_entries = _exact_git_tree_entries(revision)
    _run(
        [
            _git_invocation(),
            "archive",
            "--format=tar",
            "--output",
            str(archive),
            revision,
        ],
        cwd=ROOT,
        env=_git_environment(),
    )
    if archive.stat().st_size > MAX_SOURCE_ARCHIVE_BYTES:
        raise DossierError("Git archive exceeds its compressed-byte limit")
    with tarfile.open(archive, "r:") as package:
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        archived_files: set[str] = set()
        members: list[tarfile.TarInfo] = []
        expanded_bytes = 0
        for member in package:
            members.append(member)
            if len(members) > MAX_SOURCE_ARCHIVE_ENTRIES:
                raise DossierError("Git archive exceeds its entry limit")
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
                or not path.parts
                or "\\" in member.name
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in member.name
                )
                or path.as_posix() != member.name.rstrip("/")
            ):
                raise DossierError(f"Git archive contains unsafe path {member.name!r}")
            canonical = path.as_posix()
            if canonical in seen:
                raise DossierError(
                    f"Git archive contains duplicate path {member.name!r}"
                )
            seen.add(canonical)
            if member.issym() or member.islnk():
                raise DossierError(
                    f"candidate source archives must not contain links: {member.name!r}"
                )
            if not (member.isfile() or member.isdir()):
                raise DossierError(
                    f"candidate source archive contains special entry {member.name!r}"
                )
            if member.isfile():
                if member.size < 0 or member.size > MAX_SOURCE_ARCHIVE_FILE_BYTES:
                    raise DossierError(
                        f"Git archive file exceeds its byte limit: {canonical!r}"
                    )
                expanded_bytes += member.size
                if expanded_bytes > MAX_SOURCE_ARCHIVE_EXPANDED_BYTES:
                    raise DossierError("Git archive exceeds its expanded-byte limit")
                expected = expected_entries.get(canonical)
                if expected is None:
                    raise DossierError(
                        f"Git archive contains a file outside its exact tree: {canonical!r}"
                    )
                source = package.extractfile(member)
                if source is None:
                    raise DossierError(
                        f"Git archive file cannot be read: {member.name!r}"
                    )
                expected_mode, expected_object_id, expected_size = expected
                if member.size != expected_size:
                    raise DossierError(
                        f"Git archive file size differs from its exact tree: {canonical!r}"
                    )
                object_digest = hashlib.new(object_format)
                object_digest.update(f"blob {member.size}\0".encode("ascii"))
                content_digest = hashlib.sha256()
                observed = 0
                with source:
                    while chunk := source.read(HASH_CHUNK_BYTES):
                        observed += len(chunk)
                        if observed > member.size:
                            raise DossierError(
                                f"Git archive file exceeds its header size: "
                                f"{member.name!r}"
                            )
                        object_digest.update(chunk)
                        content_digest.update(chunk)
                if observed != member.size:
                    raise DossierError(
                        f"Git archive file size changed while reading: {member.name!r}"
                    )
                archived_mode = "100755" if member.mode & 0o111 else "100644"
                if (
                    archived_mode != expected_mode
                    or object_digest.hexdigest() != expected_object_id
                ):
                    raise DossierError(
                        f"Git archive file differs from its exact tree blob: {canonical!r}"
                    )
                archived_files.add(canonical)
                files.append(
                    {
                        "path": canonical,
                        "git_mode": archived_mode,
                        "size_bytes": member.size,
                        "sha256": content_digest.hexdigest(),
                    }
                )
            elif not any(path.startswith(f"{canonical}/") for path in expected_entries):
                raise DossierError(
                    f"Git archive contains an empty directory outside its exact tree: "
                    f"{canonical!r}"
                )
        missing = sorted(set(expected_entries) - archived_files)
        if missing:
            raise DossierError(
                "Git archive omits exact tree files (possible export-ignore drift): "
                f"{missing[:8]!r}"
            )
        _materialize_validated_tar(
            package,
            members,
            destination,
            context="Git archive",
        )
    if not files or [record["path"] for record in files] != sorted(
        record["path"] for record in files
    ):
        raise DossierError("Git archive file list is empty or not path-sorted")
    return files


def _single_file(directory: Path, suffix: str) -> Path:
    matches: list[Path] = []
    for path in sorted(directory.iterdir()):
        if not path.name.endswith(suffix):
            continue
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode):
            raise DossierError(f"package output is not a regular file: {path}")
        matches.append(path)
    if len(matches) != 1:
        raise DossierError(
            f"{directory} contains {len(matches)} files ending in {suffix!r}, expected one"
        )
    return matches[0]


def _compare_directories(first: Path, second: Path, suffix: str) -> None:
    left = {
        path.relative_to(first).as_posix(): _sha256(path)
        for path in _regular_files(first)
        if path.name.endswith(suffix)
    }
    right = {
        path.relative_to(second).as_posix(): _sha256(path)
        for path in _regular_files(second)
        if path.name.endswith(suffix)
    }
    if not left or left != right:
        raise DossierError(
            f"source-identical {suffix} package builds differ: first={left!r}, second={right!r}"
        )


def _extract_sdist(archive: Path, destination: Path) -> Path:
    """Extract a just-built sdist inside the builder-local verification boundary.

    Retained-dossier verification does not parse this archive. The builder invokes
    the locally selected packaging tool before this check, so this function is not
    an untrusted retained-artifact verifier or a process-isolation boundary.
    """

    if archive.stat().st_size > MAX_SOURCE_ARCHIVE_BYTES:
        raise DossierError("Python sdist exceeds its compressed-byte limit")
    with tarfile.open(archive, "r:gz") as package:
        seen: set[str] = set()
        prefixes: set[str] = set()
        members: list[tarfile.TarInfo] = []
        file_count = 0
        expanded_bytes = 0
        for member in package:
            members.append(member)
            if len(members) > MAX_SOURCE_ARCHIVE_ENTRIES:
                raise DossierError("Python sdist exceeds its entry limit")
        for member in members:
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
                or not path.parts
                or "\\" in member.name
                or any(
                    ord(character) < 32 or ord(character) == 127
                    for character in member.name
                )
                or path.as_posix() != member.name.rstrip("/")
            ):
                raise DossierError(f"Python sdist contains unsafe path {member.name!r}")
            canonical = path.as_posix()
            if canonical in seen:
                raise DossierError(
                    f"Python sdist contains duplicate path {member.name!r}"
                )
            seen.add(canonical)
            prefixes.add(path.parts[0])
            if member.issym() or member.islnk():
                raise DossierError(f"Python sdist contains a link: {member.name!r}")
            if not (member.isfile() or member.isdir()):
                raise DossierError(
                    f"Python sdist contains a special entry: {member.name!r}"
                )
            if member.isfile():
                file_count += 1
                expanded_bytes += member.size
                if file_count > MAX_SOURCE_ARCHIVE_FILES:
                    raise DossierError("Python sdist exceeds its regular-file limit")
                if member.size < 0 or member.size > MAX_SOURCE_ARCHIVE_FILE_BYTES:
                    raise DossierError(
                        f"Python sdist file exceeds its byte limit: {canonical!r}"
                    )
                if expanded_bytes > MAX_SOURCE_ARCHIVE_EXPANDED_BYTES:
                    raise DossierError("Python sdist exceeds its expanded-byte limit")
        if len(prefixes) != 1:
            raise DossierError(
                f"Python sdist has {len(prefixes)} top-level paths instead of one"
            )
        _materialize_validated_tar(
            package,
            members,
            destination,
            context="Python sdist",
        )
    root = destination / next(iter(prefixes))
    for required in (
        "Cargo.lock",
        "Cargo.toml",
        "pyproject.toml",
        "ncp-core/Cargo.toml",
        "ncp-python/Cargo.toml",
    ):
        if not (root / required).is_file():
            raise DossierError(f"Python sdist is missing required source {required}")
    return root


def _smoke_python_wheel(
    wheel: Path,
    source: Path,
    revision: str,
    expected_identity: dict[str, str],
    environment: dict[str, str],
    virtual: Path,
    role: str,
    input_subject_role: str,
    input_artifact_sha256: str,
) -> dict[str, Any]:
    _run(
        [sys.executable, "-I", "-m", "venv", str(virtual)],
        cwd=source,
        env=environment,
    )
    python = virtual / "bin" / "python"
    if os.name == "nt":
        python = virtual / "Scripts" / "python.exe"
    _run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            str(wheel),
        ],
        cwd=source,
        env=environment,
    )
    identity = _strict_json_object(
        _run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "import json,ncp; print(json.dumps({"
                    "'build_identity':ncp.BUILD_IDENTITY,"
                    "'package_version':ncp.PACKAGE_VERSION,"
                    "'wire_version':ncp.NCP_VERSION,"
                    "'contract_hash':ncp.CONTRACT_HASH,"
                    "'normative_contract_digest_sha256':ncp.NORMATIVE_CONTRACT_DIGEST"
                    "},sort_keys=True))"
                ),
            ],
            cwd=source,
            env=environment,
            capture=True,
        ).decode("utf-8", "strict"),
        f"installed Python identity for {role}",
    )
    if not isinstance(identity, dict) or identity != expected_identity:
        raise DossierError(
            f"installed Python wheel identity {identity!r} != {expected_identity!r}"
        )
    behavior = (
        _run(
            [
                str(python),
                "-I",
                "scripts/check_behavior_vectors.py",
            ],
            cwd=source,
            env={**environment, "NCP_REQUIRE_BINDING": "1"},
            capture=True,
        )
        .decode("utf-8", "strict")
        .strip()
    )
    if (
        re.fullmatch(
            r"OK check_behavior_vectors: [1-9][0-9]* behavioral \+ 14 canonical wire vectors "
            r"match the ncp binding with zero manifest skips",
            behavior,
        )
        is None
    ):
        raise DossierError(
            f"installed Python wheel behavior receipt is malformed: {behavior!r}"
        )
    return {
        "role": role,
        "input_subject_role": input_subject_role,
        "input_artifact_sha256": input_artifact_sha256,
        "artifact_sha256": _sha256(wheel),
        "identity": identity,
        "behavior_receipt": behavior,
    }


def _build_python_sdist(
    source: Path,
    first: Path,
    second: Path,
    revision: str,
    temporary: Path,
    first_environment: dict[str, str],
    second_environment: dict[str, str],
) -> Path:
    if any(
        environment.get("CARGO_NET_OFFLINE") != "true"
        for environment in (first_environment, second_environment)
    ):
        raise DossierError("Python sdist construction requires CARGO_NET_OFFLINE=true")
    sdist = [
        "maturin",
        "sdist",
        "-m",
        "ncp-python/Cargo.toml",
    ]
    sdist_source_first = temporary / "sdist-source-first"
    sdist_source_second = temporary / "sdist-source-second"
    _copy_regular_tree(source, sdist_source_first)
    _copy_regular_tree(source, sdist_source_second)
    _assert_no_cargo_config_ancestors(sdist_source_first)
    _assert_no_cargo_config_ancestors(sdist_source_second)
    sdist_first_environment = first_environment.copy()
    sdist_first_environment.pop("NCP_BUILD_IDENTITY", None)
    sdist_first_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
    sdist_second_environment = second_environment.copy()
    sdist_second_environment.pop("NCP_BUILD_IDENTITY", None)
    sdist_second_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
    _prepare_sdist_source(sdist_source_first, revision, sdist_first_environment)
    _prepare_sdist_source(sdist_source_second, revision, sdist_second_environment)
    sdist_first_snapshot = _directory_snapshot(sdist_source_first)
    sdist_second_snapshot = _directory_snapshot(sdist_source_second)
    if sdist_first_snapshot != sdist_second_snapshot:
        raise DossierError("independently prepared Python sdist sources differ")
    _run(
        [*sdist, "--out", str(first)],
        cwd=sdist_source_first,
        env=sdist_first_environment,
    )
    _run(
        [*sdist, "--out", str(second)],
        cwd=sdist_source_second,
        env=sdist_second_environment,
    )
    if (
        _directory_snapshot(sdist_source_first) != sdist_first_snapshot
        or _directory_snapshot(sdist_source_second) != sdist_second_snapshot
    ):
        raise DossierError(
            "maturin sdist mutated its reviewed identity-bearing derivative source tree"
        )
    _compare_directories(first, second, ".tar.gz")
    return _single_file(first, ".tar.gz")


def _python_wheel_build_command(output: Path) -> list[str]:
    return [*PYTHON_WHEEL_BUILD_ARGS, "--out", str(output)]


def _build_python(
    source: Path,
    products: Path,
    revision: str,
    source_date_epoch: int,
    temporary: Path,
    environment: dict[str, str],
) -> list[dict[str, Any]]:
    _assert_no_cargo_config_ancestors(source)
    first = temporary / "wheel-first"
    second = temporary / "wheel-second"
    first.mkdir()
    second.mkdir()
    base_environment = environment.copy()
    base_environment.update(PYTHON_WHEEL_CARGO_ENVIRONMENT)
    base_environment.update(
        {
            "NCP_BUILD_IDENTITY": revision,
            "SOURCE_DATE_EPOCH": str(source_date_epoch),
        }
    )
    first_environment = base_environment.copy()
    first_environment["CARGO_TARGET_DIR"] = str(temporary / "python-target-first")
    second_environment = base_environment.copy()
    second_environment["CARGO_TARGET_DIR"] = str(temporary / "python-target-second")
    _run(_python_wheel_build_command(first), cwd=source, env=first_environment)
    _run(_python_wheel_build_command(second), cwd=source, env=second_environment)
    _compare_directories(first, second, ".whl")
    source_distribution = _build_python_sdist(
        source,
        first,
        second,
        revision,
        temporary,
        first_environment,
        second_environment,
    )
    wheel = _single_file(first, ".whl")
    destination = products / "python"
    destination.mkdir()
    shutil.copyfile(wheel, destination / wheel.name)
    shutil.copyfile(source_distribution, destination / source_distribution.name)

    contract = _json(source / "contract" / "manifest.v1.json")
    expected_identity = {
        "build_identity": revision,
        "package_version": _json(source / "package.json")["version"],
        "wire_version": contract["wire_version"],
        "contract_hash": contract["wire_proto_contract_hash_fnv1a64"],
        "normative_contract_digest_sha256": contract["contract_digest_sha256"],
    }

    source_wheel_receipt = _smoke_python_wheel(
        wheel,
        source,
        revision,
        expected_identity,
        first_environment,
        temporary / "wheel-smoke-venv",
        "source-wheel",
        "python:wheel",
        _sha256(wheel),
    )

    sdist_source_parent = temporary / "sdist-source"
    sdist_source_parent.mkdir()
    sdist_source = _extract_sdist(source_distribution, sdist_source_parent)
    _assert_no_cargo_config_ancestors(sdist_source)
    _assert_packaged_source_identity(sdist_source, revision)
    if _sha256(sdist_source / "Cargo.lock") != _sha256(
        temporary / "sdist-source-first" / "Cargo.lock"
    ):
        raise DossierError("Python sdist did not retain its exact prepared lock")
    sdist_wheels = temporary / "sdist-wheel"
    sdist_wheels.mkdir()
    sdist_environment = base_environment.copy()
    sdist_environment.pop("NCP_BUILD_IDENTITY", None)
    sdist_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
    sdist_environment["CARGO_TARGET_DIR"] = str(temporary / "sdist-target")
    _verify_sdist_workspace(sdist_source, sdist_environment)
    _run(
        _python_wheel_build_command(sdist_wheels),
        cwd=sdist_source,
        env=sdist_environment,
    )
    sdist_wheel = _single_file(sdist_wheels, ".whl")
    sdist_wheel_receipt = _smoke_python_wheel(
        sdist_wheel,
        source,
        revision,
        expected_identity,
        sdist_environment,
        temporary / "sdist-smoke-venv",
        "sdist-rebuilt-wheel",
        "python:sdist",
        _sha256(source_distribution),
    )
    return [source_wheel_receipt, sdist_wheel_receipt]


def _sdist_preflight(revision: str) -> None:
    _, source_date_epoch = _exact_source(revision)
    with tempfile.TemporaryDirectory(prefix="ncp-sdist-preflight-") as directory:
        temporary = Path(directory)
        source = temporary / "source"
        source.mkdir()
        _extract_git_archive(revision, source, temporary / "source.tar")
        first = temporary / "first"
        second = temporary / "second"
        first.mkdir()
        second.mkdir()
        base_environment = _sanitized_build_environment(
            temporary,
            os.environ.copy(),
            revision=revision,
            source_date_epoch=source_date_epoch,
        )
        _populate_outer_cargo_cache(source, base_environment)
        first_environment = {
            **base_environment,
            "CARGO_TARGET_DIR": str(temporary / "target-first"),
        }
        second_environment = {
            **base_environment,
            "CARGO_TARGET_DIR": str(temporary / "target-second"),
        }
        source_distribution = _build_python_sdist(
            source,
            first,
            second,
            revision,
            temporary,
            first_environment,
            second_environment,
        )
        extracted_parent = temporary / "extracted"
        extracted_parent.mkdir()
        extracted = _extract_sdist(source_distribution, extracted_parent)
        _assert_no_cargo_config_ancestors(extracted)
        _assert_packaged_source_identity(extracted, revision)
        verification_environment = {
            **base_environment,
            "CARGO_TARGET_DIR": str(temporary / "target-verify"),
        }
        verification_environment.pop("NCP_BUILD_IDENTITY", None)
        verification_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
        _verify_sdist_workspace(extracted, verification_environment)
        prepared_lock = temporary / "sdist-source-first" / "Cargo.lock"
        if _sha256(extracted / "Cargo.lock") != _sha256(prepared_lock):
            raise DossierError(
                "Python sdist did not retain its exact prepared two-crate lock"
            )


def _build_npm(
    products: Path,
    revision: str,
    temporary: Path,
    environment: dict[str, str],
) -> None:
    first = temporary / "npm-first"
    second = temporary / "npm-second"
    script = ROOT / "ncp-ts" / "scripts" / "build-release.mjs"
    _run(
        ["node", str(script), "--source-revision", revision, "--output", str(first)],
        cwd=ROOT,
        env=environment,
    )
    _run(
        ["node", str(script), "--source-revision", revision, "--output", str(second)],
        cwd=ROOT,
        env=environment,
    )
    _compare_directories(first, second, ".tgz")
    first_receipt = _json(first / "npm-release-build-receipt.json")
    second_receipt = _json(second / "npm-release-build-receipt.json")
    if first_receipt != second_receipt:
        raise DossierError("source-identical npm build receipts differ")
    shutil.copytree(first, products / "npm")


def _tool_version(command: list[str], environment: dict[str, str]) -> str:
    output = (
        _run(command, cwd=ROOT, env=environment, capture=True)
        .decode("utf-8", "replace")
        .strip()
    )
    return output.splitlines()[0] if output else "UNKNOWN"


def _tool_output(command: list[str], environment: dict[str, str]) -> str:
    output = (
        _run(command, cwd=ROOT, env=environment, capture=True)
        .decode("utf-8", "replace")
        .strip()
    )
    return output if output else "UNKNOWN"


def _tool_invocation_sha256(command: str, environment: dict[str, str]) -> str:
    candidate = (
        command
        if Path(command).is_absolute()
        else shutil.which(command, path=environment.get("PATH"))
    )
    if candidate is None:
        raise DossierError(f"required candidate tool is unavailable: {command}")
    try:
        resolved = Path(candidate).resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as error:
        raise DossierError(
            f"cannot resolve candidate tool {command}: {error}"
        ) from error
    if not stat.S_ISREG(mode):
        raise DossierError(f"candidate tool is not a regular file: {command}")
    return _sha256(resolved)


def _pip_version(environment: dict[str, str]) -> str:
    version = (
        _run(
            [
                sys.executable,
                "-I",
                "-c",
                "import importlib.metadata; print(importlib.metadata.version('pip'))",
            ],
            cwd=ROOT,
            env=environment,
            capture=True,
        )
        .decode("ascii", "strict")
        .strip()
    )
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version) is None:
        raise DossierError("candidate pip version is malformed")
    return f"pip {version}"


def _artifact_records(products: Path) -> list[dict[str, Any]]:
    files = _regular_files(
        products,
        max_files=MAX_DOSSIER_REGULAR_FILES,
        max_entries=MAX_DOSSIER_ENTRIES,
        max_depth=MAX_DOSSIER_DEPTH,
    )
    _assert_file_size_budget(
        files,
        context="candidate product tree",
        maximum_file_bytes=MAX_DOSSIER_FILE_BYTES,
        maximum_total_bytes=MAX_DOSSIER_TOTAL_BYTES,
    )
    records: list[dict[str, Any]] = []
    for path in files:
        records.append(
            {
                "path": path.relative_to(products.parent).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path, maximum=MAX_DOSSIER_FILE_BYTES),
            }
        )
    return records


def _expected_product_paths(subject_paths: list[str]) -> set[str]:
    return {
        *subject_paths,
        "products/rust/rust-package-receipt.json",
        *(f"products/rust/{path}" for path in RETAINED_CONDITIONED_LOCKS.values()),
        f"products/rust/{RETAINED_LZ4_CRATE}",
        f"products/rust/{RETAINED_TWOX_CRATE}",
        f"products/rust/{RETAINED_UPSTREAM_TRANSPORT_CRATE}",
        "products/npm/npm-release-build-receipt.json",
        *(f"products/supply-chain/{name}" for name in SUPPLY_FILES),
    }


def _assert_exact_product_files(root: Path, subject_paths: list[str]) -> None:
    actual = {
        path.relative_to(root).as_posix() for path in _regular_files(root / "products")
    }
    expected = _expected_product_paths(subject_paths)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise DossierError(
            "candidate product file set is not exact: "
            f"missing={missing!r}, unexpected={unexpected!r}"
        )


def _is_linux_x86_64_wheel_platform(platform_tag: str) -> bool:
    linux_tag = re.compile(
        r"(?:linux|manylinux[0-9]+|manylinux(?:_[0-9]+){2}|musllinux(?:_[0-9]+){2})_x86_64"
    )
    tags = platform_tag.split(".")
    return bool(tags) and all(linux_tag.fullmatch(tag) is not None for tag in tags)


def _canonical_sha512_sri(value: object, *, context: str) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", value) is None
    ):
        raise DossierError(f"{context} is not a canonical SHA-512 SRI value")
    encoded = value.removeprefix("sha512-")
    try:
        digest = base64.b64decode(encoded, validate=True)
    except ValueError as error:
        raise DossierError(f"{context} is not valid base64") from error
    if len(digest) != 64 or base64.b64encode(digest).decode("ascii") != encoded:
        raise DossierError(f"{context} does not encode exactly 64 SHA-512 bytes")
    return value


def _strip_jsonc_comments(raw: str, *, context: str) -> str:
    result = list(raw)
    index = 0
    in_string = False
    escaped = False
    while index < len(result):
        character = result[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            index += 1
            continue
        if character != "/" or index + 1 >= len(result):
            index += 1
            continue
        marker = result[index + 1]
        if marker == "/":
            result[index] = result[index + 1] = " "
            index += 2
            while index < len(result) and result[index] not in "\r\n":
                result[index] = " "
                index += 1
            continue
        if marker == "*":
            result[index] = result[index + 1] = " "
            index += 2
            while index + 1 < len(result) and result[index : index + 2] != ["*", "/"]:
                if result[index] not in "\r\n":
                    result[index] = " "
                index += 1
            if index + 1 >= len(result):
                raise DossierError(f"{context} contains an unterminated comment")
            result[index] = result[index + 1] = " "
            index += 2
            continue
        index += 1
    if in_string:
        raise DossierError(f"{context} contains an unterminated string")
    return "".join(result)


def _remove_jsonc_trailing_commas(raw: str) -> str:
    result: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(raw):
        character = raw[index]
        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue
        if character == ",":
            lookahead = index + 1
            while lookahead < len(raw) and raw[lookahead].isspace():
                lookahead += 1
            if lookahead < len(raw) and raw[lookahead] in "}]":
                index += 1
                continue
        result.append(character)
        index += 1
    return "".join(result)


def _parse_jsonc_object(raw: str, *, context: str) -> dict[str, Any]:
    normalized = _remove_jsonc_trailing_commas(
        _strip_jsonc_comments(raw, context=context)
    )
    return _strict_json_object(normalized, context)


def _validate_typescript_bun_lock(
    lock: dict[str, Any], *, version: str, reviewed_integrity: str
) -> None:
    if set(lock) != {"configVersion", "lockfileVersion", "packages", "workspaces"}:
        raise DossierError("Bun lockfile shape is invalid")
    workspaces = lock.get("workspaces")
    packages = lock.get("packages")
    if (
        lock.get("lockfileVersion") != 1
        or lock.get("configVersion") != 1
        or not isinstance(workspaces, dict)
        or set(workspaces) != {""}
        or not isinstance(packages, dict)
        or set(packages) != {"typescript"}
    ):
        raise DossierError("Bun lockfile workspace or package records are invalid")
    workspace = workspaces[""]
    if (
        not isinstance(workspace, dict)
        or set(workspace) != {"devDependencies", "name"}
        or workspace.get("name") != "@sepahead/ncp"
        or workspace.get("devDependencies") != {"typescript": version}
    ):
        raise DossierError("Bun root TypeScript pin differs from the reviewed source")
    candidates = []
    for key, record in packages.items():
        identity = record[0] if isinstance(record, list) and record else None
        if (
            key == "typescript"
            or key.startswith("typescript@")
            or (isinstance(identity, str) and identity.startswith("typescript@"))
        ):
            candidates.append((key, record))
    if len(candidates) != 1:
        raise DossierError("Bun lockfile must contain exactly one TypeScript package")
    key, record = candidates[0]
    if (
        key != "typescript"
        or not isinstance(record, list)
        or len(record) != 4
        or record[0] != f"typescript@{version}"
        or record[1] != ""
        or record[2] != {"bin": {"tsc": "bin/tsc", "tsserver": "bin/tsserver"}}
        or _canonical_sha512_sri(record[3], context="Bun TypeScript package integrity")
        != reviewed_integrity
    ):
        raise DossierError("Bun TypeScript package record differs from its control")


def _validate_npm_dependency_surface(
    manifest: dict[str, Any], *, context: str
) -> str:
    unexpected = [
        field for field in NPM_UNREVIEWED_PACKAGE_GRAPH_FIELDS if field in manifest
    ]
    if unexpected:
        raise DossierError(
            f"{context} contains unreviewed dependency or package-graph fields: "
            + ", ".join(unexpected)
        )
    development = manifest.get("devDependencies")
    if (
        not isinstance(development, dict)
        or set(development) != {"typescript"}
        or re.fullmatch(
            r"[0-9]+\.[0-9]+\.[0-9]+", str(development.get("typescript"))
        )
        is None
    ):
        raise DossierError(
            f"{context} must contain only one exact TypeScript development pin"
        )
    return development["typescript"]


def _reviewed_typescript_control(
    revision: str,
) -> tuple[dict[str, Any], str, str]:
    """Load the exact source-bound TypeScript control and Bun-lock identity."""

    if SOURCE_REVISION.fullmatch(revision) is None:
        raise DossierError("TypeScript control revision is malformed")
    control_bytes = _git("show", f"{revision}:{TYPESCRIPT_CONTROL_PATH}")
    if len(control_bytes) > MAX_TYPESCRIPT_CONTROL_BYTES:
        raise DossierError("TypeScript source control exceeds its byte limit")
    try:
        control_raw = control_bytes.decode("utf-8", "strict")
    except UnicodeError as error:
        raise DossierError("TypeScript source control is not UTF-8") from error
    control = _strict_json_object(control_raw, "TypeScript source control")
    if json.dumps(control, indent=2, ensure_ascii=True) + "\n" != control_raw:
        raise DossierError("TypeScript source control is not canonical JSON")
    if set(control) != {
        "claim_boundary",
        "normalized_package_tree",
        "package",
        "registry",
        "schema",
        "version",
    }:
        raise DossierError("TypeScript source control shape is invalid")
    registry = control.get("registry")
    tree = control.get("normalized_package_tree")
    if (
        control.get("schema") != TYPESCRIPT_CONTROL_SCHEMA
        or control.get("package") != "typescript"
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", str(control.get("version"))) is None
        or not isinstance(control.get("claim_boundary"), str)
        or not control["claim_boundary"]
        or not isinstance(registry, dict)
        or set(registry)
        != {"integrity_sha512", "tarball_bytes_retained", "tarball_sha256"}
        or re.fullmatch(
            r"sha512-[A-Za-z0-9+/]+={0,2}", str(registry.get("integrity_sha512"))
        )
        is None
        or registry.get("tarball_bytes_retained") is not False
        or re.fullmatch(r"[0-9a-f]{64}", str(registry.get("tarball_sha256"))) is None
        or not isinstance(tree, dict)
        or set(tree) != {"file_count", "manifest_sha256", "record_shape", "total_bytes"}
        or tree.get("record_shape") != ["path", "size_bytes", "sha256"]
        or not isinstance(tree.get("file_count"), int)
        or isinstance(tree.get("file_count"), bool)
        or not 1 <= tree["file_count"] <= MAX_TYPESCRIPT_PACKAGE_FILES
        or not isinstance(tree.get("total_bytes"), int)
        or isinstance(tree.get("total_bytes"), bool)
        or not 1 <= tree["total_bytes"] <= MAX_TYPESCRIPT_PACKAGE_BYTES
        or re.fullmatch(r"[0-9a-f]{64}", str(tree.get("manifest_sha256"))) is None
    ):
        raise DossierError("TypeScript source control identity is invalid")
    _canonical_sha512_sri(
        registry["integrity_sha512"], context="TypeScript source-control integrity"
    )

    bun_lock = _git("show", f"{revision}:bun.lock")
    if len(bun_lock) > MAX_TYPESCRIPT_CONTROL_BYTES:
        raise DossierError("Bun lockfile exceeds its TypeScript-control byte limit")
    try:
        lock_text = bun_lock.decode("utf-8", "strict")
    except UnicodeError as error:
        raise DossierError("Bun lockfile is not UTF-8") from error
    if "\r" in lock_text:
        raise DossierError("Bun lockfile must use canonical LF line endings")
    _validate_typescript_bun_lock(
        _parse_jsonc_object(lock_text, context="Bun lockfile"),
        version=control["version"],
        reviewed_integrity=registry["integrity_sha512"],
    )
    return (
        control,
        hashlib.sha256(control_bytes).hexdigest(),
        hashlib.sha256(bun_lock).hexdigest(),
    )


def _validate_typescript_package_tree(
    value: object, *, control: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != {
        "file_count",
        "total_bytes",
        "manifest_sha256",
        "files",
    }:
        raise DossierError("candidate TypeScript package-tree receipt shape is invalid")
    files = value.get("files")
    if (
        not isinstance(files, list)
        or not files
        or len(files) > MAX_TYPESCRIPT_PACKAGE_FILES
        or value.get("file_count") != len(files)
    ):
        raise DossierError("candidate TypeScript package-tree file count is invalid")
    records: list[dict[str, Any]] = []
    paths: list[str] = []
    total_bytes = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "size_bytes", "sha256"}:
            raise DossierError("candidate TypeScript package-tree record is invalid")
        path = _safe_relative_path(item.get("path"), label="TypeScript package path")
        if not path.isascii() or any(
            ord(character) < 32 or ord(character) > 126 for character in path
        ):
            raise DossierError(
                "candidate TypeScript package path is not canonical printable ASCII"
            )
        size = item.get("size_bytes")
        digest = item.get("sha256")
        if (
            not isinstance(size, int)
            or isinstance(size, bool)
            or size < 0
            or size > MAX_TYPESCRIPT_PACKAGE_FILE_BYTES
            or re.fullmatch(r"[0-9a-f]{64}", str(digest)) is None
        ):
            raise DossierError("candidate TypeScript package-tree identity is invalid")
        total_bytes += size
        if total_bytes > MAX_TYPESCRIPT_PACKAGE_BYTES:
            raise DossierError(
                "candidate TypeScript package tree exceeds its byte limit"
            )
        paths.append(path)
        records.append({"path": path, "size_bytes": size, "sha256": digest})
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise DossierError(
            "candidate TypeScript package paths are not exact and sorted"
        )
    manifest_digest = hashlib.sha256(
        json.dumps(
            records,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    reviewed = control.get("normalized_package_tree")
    if (
        not isinstance(reviewed, dict)
        or value.get("total_bytes") != total_bytes
        or value.get("manifest_sha256") != manifest_digest
        or value.get("file_count") != reviewed.get("file_count")
        or value.get("total_bytes") != reviewed.get("total_bytes")
        or value.get("manifest_sha256") != reviewed.get("manifest_sha256")
    ):
        raise DossierError(
            "candidate TypeScript package tree differs from its reviewed control"
        )
    return records


def _package_subject_records(
    products: Path,
    root_manifest: dict[str, Any],
    version: str,
    revision: str,
    normative_digest: str,
    *,
    require_hosted_wheel: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    nested_manifest = _json_from_git(revision, "ncp-ts/package.json")
    root_typescript = _validate_npm_dependency_surface(
        root_manifest, context="package.json"
    )
    nested_typescript = _validate_npm_dependency_surface(
        nested_manifest, context="ncp-ts/package.json"
    )
    if (
        nested_manifest.get("name") != root_manifest.get("name")
        or nested_manifest.get("version") != version
        or nested_typescript != root_typescript
    ):
        raise DossierError("root and nested npm package identities are incoherent")
    product_files = _regular_files(
        products,
        max_files=MAX_DOSSIER_REGULAR_FILES,
        max_entries=MAX_DOSSIER_ENTRIES,
        max_depth=MAX_DOSSIER_DEPTH,
    )
    _assert_file_size_budget(
        product_files,
        context="candidate product tree",
        maximum_file_bytes=MAX_DOSSIER_FILE_BYTES,
        maximum_total_bytes=MAX_DOSSIER_TOTAL_BYTES,
    )
    expected: list[tuple[str, Path]] = [
        (
            f"rust:{crate}",
            products / "rust" / f"{crate}-{version}.crate",
        )
        for crate in ("ncp-core", "ncp-zenoh", "ncp-cpp", "ncp-python", "ncp-gateway")
    ]
    rust_receipt = _verify_committed_rust_receipt(
        products / "rust", version=version, revision=revision
    )
    rust_archives = rust_receipt.get("archives")
    expected_rust_archives: list[dict[str, object]] = [
        {
            "crate": role.removeprefix("rust:"),
            "path": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for role, path in expected
    ]
    if not isinstance(rust_archives, list) or len(rust_archives) != len(
        expected_rust_archives
    ):
        raise DossierError("candidate Rust package receipt archive set is invalid")
    for recorded, expected_record in zip(
        rust_archives, expected_rust_archives, strict=True
    ):
        if not isinstance(recorded, dict) or any(
            recorded.get(key) != value for key, value in expected_record.items()
        ):
            raise DossierError("candidate Rust package receipt archive set is invalid")
    python_root = products / "python"
    normalized_python_version = re.sub(r"-rc\.([0-9]+)$", r"rc\1", version)
    wheel = _single_file(python_root, ".whl")
    wheel_match = re.fullmatch(
        rf"ncp-{re.escape(normalized_python_version)}-cp311-abi3-([A-Za-z0-9_.]+)\.whl",
        wheel.name,
    )
    if wheel_match is None:
        raise DossierError(
            f"candidate Python wheel identity is unexpected: {wheel.name}"
        )
    if require_hosted_wheel and not _is_linux_x86_64_wheel_platform(
        wheel_match.group(1)
    ):
        raise DossierError(
            "hosted candidate Python wheel is not in the reviewed Linux x86_64 "
            f"platform class: {wheel.name}"
        )
    sdist = _single_file(python_root, ".tar.gz")
    if sdist.name != f"ncp-{normalized_python_version}.tar.gz":
        raise DossierError(
            f"candidate Python sdist identity is unexpected: {sdist.name}"
        )
    expected_npm_name = f"sepahead-ncp-{version}.tgz"
    npm_root = _single_file(products / "npm" / "repository-root", ".tgz")
    npm_nested = _single_file(products / "npm" / "ncp-ts", ".tgz")
    if npm_root.name != expected_npm_name or npm_nested.name != expected_npm_name:
        raise DossierError("candidate npm tarball identity is unexpected")
    npm_receipt = _json(products / "npm" / "npm-release-build-receipt.json")
    typescript_control, typescript_control_sha256, bun_lock_sha256 = (
        _reviewed_typescript_control(revision)
    )
    typescript_registry = typescript_control["registry"]
    expected_receipt_keys = {
        "schema",
        "package_name",
        "package_version",
        "source_revision",
        "build_identity",
        "normative_contract_digest_sha256",
        "node_version",
        "node_executable_sha256",
        "node_executable_pre_post_match",
        "typescript_version",
        "typescript_control_path",
        "typescript_control_sha256",
        "typescript_control_claim_boundary",
        "typescript_lockfile_sha256",
        "typescript_registry_integrity_sha512",
        "typescript_registry_tarball_sha256",
        "typescript_registry_tarball_bytes_retained",
        "typescript_registry_tarball_evidence",
        "typescript_compiler_launcher_sha256",
        "typescript_package_manifest_sha256",
        "typescript_package_tree",
        "typescript_package_tree_pre_post_match",
        "rust_build_identity_probe_passed",
        "artifacts",
    }
    if (
        set(npm_receipt) != expected_receipt_keys
        or npm_receipt.get("schema") != NPM_RELEASE_RECEIPT_SCHEMA
        or npm_receipt.get("package_name") != root_manifest.get("name")
        or npm_receipt.get("source_revision") != revision
        or npm_receipt.get("build_identity") != revision
        or npm_receipt.get("package_version") != version
        or npm_receipt.get("normative_contract_digest_sha256") != normative_digest
        or npm_receipt.get("typescript_version")
        != (root_manifest.get("devDependencies") or {}).get("typescript")
        or npm_receipt.get("typescript_version") != typescript_control.get("version")
        or npm_receipt.get("typescript_control_path") != TYPESCRIPT_CONTROL_PATH
        or npm_receipt.get("typescript_control_sha256") != typescript_control_sha256
        or npm_receipt.get("typescript_control_claim_boundary")
        != typescript_control.get("claim_boundary")
        or npm_receipt.get("typescript_lockfile_sha256") != bun_lock_sha256
        or npm_receipt.get("typescript_registry_integrity_sha512")
        != typescript_registry.get("integrity_sha512")
        or npm_receipt.get("typescript_registry_tarball_sha256")
        != typescript_registry.get("tarball_sha256")
        or npm_receipt.get("typescript_registry_tarball_bytes_retained") is not False
        or npm_receipt.get("typescript_registry_tarball_evidence")
        != TYPESCRIPT_REGISTRY_TARBALL_EVIDENCE
        or any(
            re.fullmatch(r"[0-9a-f]{64}", str(npm_receipt.get(key))) is None
            for key in (
                "node_executable_sha256",
                "typescript_compiler_launcher_sha256",
                "typescript_package_manifest_sha256",
            )
        )
        or not isinstance(npm_receipt.get("node_version"), str)
        or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", npm_receipt["node_version"]) is None
        or npm_receipt.get("node_executable_pre_post_match") is not True
        or npm_receipt.get("typescript_package_tree_pre_post_match") is not True
        or npm_receipt.get("rust_build_identity_probe_passed") is not True
    ):
        raise DossierError("candidate npm receipt identity is invalid")
    typescript_files = _validate_typescript_package_tree(
        npm_receipt.get("typescript_package_tree"), control=typescript_control
    )
    typescript_files_by_path = {item["path"]: item for item in typescript_files}
    if typescript_files_by_path.get("bin/tsc", {}).get("sha256") != npm_receipt.get(
        "typescript_compiler_launcher_sha256"
    ) or typescript_files_by_path.get("package.json", {}).get(
        "sha256"
    ) != npm_receipt.get("typescript_package_manifest_sha256"):
        raise DossierError(
            "candidate TypeScript launcher or package manifest differs from its tree"
        )
    npm_artifacts = npm_receipt.get("artifacts")
    expected_npm_artifacts = {
        ("repository-root", f"repository-root/{expected_npm_name}", _sha256(npm_root)),
        ("ncp-ts", f"ncp-ts/{expected_npm_name}", _sha256(npm_nested)),
    }
    if (
        not isinstance(npm_artifacts, list)
        or len(npm_artifacts) != 2
        or not all(
            isinstance(item, dict) and set(item) == {"package_root", "path", "sha256"}
            for item in npm_artifacts
        )
        or len(
            {
                (item["package_root"], item["path"], item["sha256"])
                for item in npm_artifacts
            }
        )
        != 2
        or {
            (item["package_root"], item["path"], item["sha256"])
            for item in npm_artifacts
        }
        != expected_npm_artifacts
    ):
        raise DossierError("candidate npm receipt artifact set is invalid")
    expected.extend(
        [
            ("python:wheel", wheel),
            ("python:sdist", sdist),
            ("npm:repository-root", npm_root),
            ("npm:ncp-ts", npm_nested),
        ]
    )
    subject_total = 0
    for role, path in expected:
        limit = MAX_PACKAGE_SUBJECT_BYTES[role]
        size = path.lstat().st_size
        if size > limit:
            raise DossierError(
                f"candidate package subject {role} exceeds its {limit}-byte limit"
            )
        subject_total += size
    if subject_total > MAX_PACKAGE_SUBJECT_TOTAL_BYTES:
        raise DossierError(
            "candidate package subjects exceed their aggregate byte limit"
        )
    expected_paths = {path.resolve() for _, path in expected}
    actual_paths = {
        path.resolve()
        for path in _regular_files(products)
        if path.name.endswith((".crate", ".whl", ".tar.gz", ".tgz"))
    }
    if actual_paths != expected_paths:
        raise DossierError(
            "candidate package subject set differs from the exact five-crate, "
            "wheel, sdist, and two-npm-artifact inventory"
        )
    records = [
        {
            "role": role,
            "path": path.relative_to(products.parent).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path, maximum=MAX_PACKAGE_SUBJECT_BYTES[role]),
        }
        for role, path in expected
    ]
    if tuple(record["role"] for record in records) != PACKAGE_SUBJECT_ROLES:
        raise DossierError(
            "candidate package subject roles are incomplete or duplicated"
        )
    return records, rust_receipt


def _assert_rust_toolchain_cross_receipt(
    outer: dict[str, Any], rust_receipt: dict[str, Any]
) -> None:
    qualification = rust_receipt.get("qualification_environment")
    nested = qualification.get("toolchain") if isinstance(qualification, dict) else None
    if not isinstance(nested, dict):
        raise DossierError("nested Rust qualification toolchain is unavailable")
    cargo_lines = str(nested.get("cargo_version", "")).splitlines()
    rustc_lines = str(nested.get("rustc_verbose", "")).splitlines()
    if (
        not cargo_lines
        or not rustc_lines
        or outer.get("cargo") != cargo_lines[0]
        or outer.get("rustc") != rustc_lines[0]
        or outer.get("rustc_verbose") != nested.get("rustc_verbose")
        or outer.get("python") != nested.get("python_version")
        or outer.get("cargo_invocation_sha256") != nested.get("cargo_invocation_sha256")
        or outer.get("rustc_invocation_sha256") != nested.get("rustc_invocation_sha256")
        or outer.get("python_binary_sha256") != nested.get("python_binary_sha256")
        or outer.get("git") != nested.get("git_version")
        or outer.get("git_binary_sha256") != nested.get("git_binary_sha256")
    ):
        raise DossierError(
            "outer dossier and nested Rust qualification toolchains differ"
        )


def _assert_npm_toolchain_cross_receipt(
    outer: dict[str, Any], npm_receipt: dict[str, Any]
) -> None:
    if npm_receipt.get("node_version") != outer.get("node") or npm_receipt.get(
        "node_executable_sha256"
    ) != outer.get("node_binary_sha256"):
        raise DossierError(
            "candidate npm receipt and dossier Node.js identities differ"
        )


def _write_checksums(root: Path) -> None:
    paths = sorted(
        path for path in _regular_files(root) if path.name != "checksums.sha256"
    )
    lines = [f"{_sha256(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    (root / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_relative_path(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > MAX_DOSSIER_PATH_BYTES
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise DossierError(f"{label} is not a plain relative path: {value!r}")
    path = Path(value)
    if (
        path.is_absolute()
        or len(path.parts) > MAX_DOSSIER_DEPTH
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise DossierError(f"{label} is unsafe: {value!r}")
    if path.as_posix() != value:
        raise DossierError(f"{label} is not canonical POSIX: {value!r}")
    return value


def _verify_checksum_manifest(root: Path, dossier_files: list[Path]) -> None:
    manifest = root / "checksums.sha256"
    lines = _bounded_utf8(
        manifest,
        context=str(manifest),
        limit=MAX_CHECKSUM_MANIFEST_BYTES,
    ).splitlines()
    if len(lines) != MAX_DOSSIER_REGULAR_FILES - 1:
        raise DossierError(
            "candidate checksum manifest does not have the exact entry count"
        )
    records: list[tuple[str, str]] = []
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if match is None:
            raise DossierError("candidate checksum manifest has a malformed line")
        digest, path_value = match.groups()
        records.append((digest, _safe_relative_path(path_value, label="checksum path")))
    paths = [path for _digest, path in records]
    if not records or paths != sorted(set(paths)):
        raise DossierError(
            "candidate checksum manifest is empty, unsorted, or duplicated"
        )
    expected = [
        path.relative_to(root).as_posix()
        for path in dossier_files
        if path.name != "checksums.sha256"
    ]
    if paths != expected:
        raise DossierError(
            "candidate checksum manifest does not cover the exact dossier"
        )
    for digest, path_value in records:
        if _sha256(root / path_value, maximum=MAX_DOSSIER_FILE_BYTES) != digest:
            raise DossierError(f"candidate checksum differs for {path_value}")


def _verify_dossier(
    root: Path,
    subject_checksums: Path | None = None,
    *,
    require_hosted_toolchain: bool = False,
) -> None:
    if root.is_symlink() or not root.is_dir():
        raise DossierError(f"candidate dossier is not a plain directory: {root}")
    dossier_files = _regular_files(
        root,
        max_files=MAX_DOSSIER_REGULAR_FILES,
        max_entries=MAX_DOSSIER_ENTRIES,
        max_depth=MAX_DOSSIER_DEPTH,
    )
    if len(dossier_files) != MAX_DOSSIER_REGULAR_FILES:
        raise DossierError("candidate dossier does not have the exact file count")
    _assert_file_size_budget(
        dossier_files,
        context="candidate dossier",
        maximum_file_bytes=MAX_DOSSIER_FILE_BYTES,
        maximum_total_bytes=MAX_DOSSIER_TOTAL_BYTES,
    )
    _assert_exact_file_parent_directories(root, dossier_files)
    _verify_checksum_manifest(root, dossier_files)
    dossier = _json(root / "candidate-dossier.json")
    subject_manifest = _json(root / "package-subjects.v1.json")
    _assert_no_local_absolute_paths(dossier, context="candidate dossier")
    _assert_no_local_absolute_paths(
        subject_manifest,
        context="candidate package-subject manifest",
    )
    if set(dossier) != DOSSIER_KEYS:
        raise DossierError("candidate dossier has an unexpected top-level shape")
    if set(subject_manifest) != {"schema", "source_revision", "subjects"}:
        raise DossierError("candidate package-subject manifest has an unexpected shape")
    if subject_manifest.get("schema") != "ncp.candidate-package-subjects.v1":
        raise DossierError("candidate package-subject manifest schema is invalid")
    if dossier.get("schema") != "ncp.candidate-dossier.v1":
        raise DossierError("candidate dossier schema is invalid")
    revision = dossier.get("source_revision")
    if not isinstance(revision, str) or SOURCE_REVISION.fullmatch(revision) is None:
        raise DossierError("candidate dossier source revision is invalid")
    tree, source_date_epoch = _exact_source(revision)
    root_manifest = _json_from_git(revision, "package.json")
    contract = _json_from_git(revision, "contract/manifest.v1.json")
    conformance = _json_from_git(revision, "conformance/manifest.v1.json")
    version = root_manifest.get("version")
    if not isinstance(version, str) or not version:
        raise DossierError("committed candidate version is malformed")
    if (
        subject_manifest.get("source_revision") != revision
        or dossier.get("source_tree") != tree
        or dossier.get("source_date_epoch") != source_date_epoch
        or dossier.get("candidate_version") != version
        or dossier.get("wire_version") != contract.get("wire_version")
        or dossier.get("normative_contract_digest_sha256")
        != contract.get("contract_digest_sha256")
        or dossier.get("conformance_corpus_digest_sha256")
        != conformance.get("corpus_digest_sha256")
        or dossier.get("author") != AUTHOR
        or dossier.get("release_authorized") is not False
        or dossier.get("reproducibility_comparisons") != REPRODUCIBILITY_COMPARISONS
        or dossier.get("source_derivations") != _source_derivations(revision)
        or dossier.get("verification_boundary") != DOSSIER_VERIFICATION_BOUNDARY
        or dossier.get("sbom_scope") != SBOM_SCOPE
        or dossier.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise DossierError(
            "candidate dossier identity or authorization boundary drifted"
        )
    subjects = subject_manifest.get("subjects")
    if not isinstance(subjects, list) or dossier.get("package_subjects") != subjects:
        raise DossierError("candidate dossier and package-subject manifest differ")
    if (
        tuple(item.get("role") if isinstance(item, dict) else None for item in subjects)
        != PACKAGE_SUBJECT_ROLES
    ):
        raise DossierError(
            "candidate package subject roles are incomplete or reordered"
        )
    subject_paths: list[str] = []
    for item in subjects:
        if not isinstance(item, dict) or set(item) != {
            "role",
            "path",
            "size_bytes",
            "sha256",
        }:
            raise DossierError(
                "candidate package subject record has an unexpected shape"
            )
        path_value = _safe_relative_path(item["path"], label="package subject path")
        path = root / path_value
        if path.is_symlink() or not path.is_file():
            raise DossierError(
                f"candidate package subject is not a regular file: {path_value}"
            )
        size = item.get("size_bytes")
        digest = item.get("sha256")
        role = item.get("role")
        role_limit = MAX_PACKAGE_SUBJECT_BYTES.get(str(role))
        if (
            not isinstance(size, int)
            or size < 0
            or role_limit is None
            or size > role_limit
            or path.stat().st_size != size
        ):
            raise DossierError(
                f"candidate package subject size differs for {path_value}"
            )
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or _sha256(path, maximum=role_limit) != digest
        ):
            raise DossierError(
                f"candidate package subject SHA-256 differs for {path_value}"
            )
        subject_paths.append(path_value)
    if sum(int(item["size_bytes"]) for item in subjects) > (
        MAX_PACKAGE_SUBJECT_TOTAL_BYTES
    ):
        raise DossierError(
            "candidate package subjects exceed their aggregate byte limit"
        )
    if len(subject_paths) != len(set(subject_paths)):
        raise DossierError("candidate package subject paths are duplicated")
    actual_packages = {
        path.relative_to(root).as_posix()
        for path in _regular_files(root / "products")
        if path.name.endswith((".crate", ".whl", ".tar.gz", ".tgz"))
    }
    if actual_packages != set(subject_paths):
        raise DossierError(
            "candidate package subjects do not cover the exact package set"
        )
    independently_derived_subjects, rust_receipt = _package_subject_records(
        root / "products",
        root_manifest,
        version,
        revision,
        str(contract.get("contract_digest_sha256")),
        require_hosted_wheel=require_hosted_toolchain,
    )
    if subjects != independently_derived_subjects:
        raise DossierError("candidate package subjects differ from package receipts")

    _assert_exact_product_files(root, subject_paths)
    expected_artifacts = _artifact_records(root / "products")
    if dossier.get("artifacts") != expected_artifacts:
        raise DossierError(
            "candidate artifact inventory does not cover the exact products"
        )

    toolchain = dossier.get("toolchain_receipt")
    if (
        not isinstance(toolchain, dict)
        or set(toolchain) != TOOLCHAIN_KEYS
        or not all(isinstance(value, str) and value for value in toolchain.values())
        or toolchain.get("maturin") != "maturin 1.14.1"
        or toolchain.get("cargo_deny") != "cargo-deny 0.19.9"
        or re.fullmatch(r"cargo [0-9]+\.[0-9]+\.[0-9]+ .+", toolchain["cargo"]) is None
        or re.fullmatch(r"rustc [0-9]+\.[0-9]+\.[0-9]+ .+", toolchain["rustc"]) is None
        or re.fullmatch(r"Python [0-9]+\.[0-9]+\.[0-9]+", toolchain["python"]) is None
        or re.fullmatch(r"pip [0-9]+\.[0-9]+\.[0-9]+", toolchain["pip"]) is None
        or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", toolchain["node"]) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", toolchain["npm"]) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", toolchain["bun"]) is None
        or re.fullmatch(r"git version [0-9]+\.[0-9]+\.[0-9]+(?: .+)?", toolchain["git"])
        is None
        or any(
            re.fullmatch(r"[0-9a-f]{64}", toolchain[key]) is None
            for key in (
                "cargo_invocation_sha256",
                "rustc_invocation_sha256",
                "python_binary_sha256",
                "git_binary_sha256",
                "node_binary_sha256",
                "npm_invocation_sha256",
            )
        )
        or "host:" not in toolchain["rustc_verbose"]
        or "LLVM version:" not in toolchain["rustc_verbose"]
    ):
        raise DossierError("candidate toolchain receipt is incomplete or malformed")
    if require_hosted_toolchain and (
        not toolchain["platform"].startswith("Linux-")
        or toolchain["runner_image_os"] == "UNSET"
        or toolchain["runner_image_version"] == "UNSET"
        or not toolchain["cargo"].startswith("cargo 1.88.0 ")
        or not toolchain["rustc"].startswith("rustc 1.88.0 ")
        or toolchain["python"] != "Python 3.14.6"
        or toolchain["pip"] != "pip 26.1.2"
        or toolchain["node"] != "v24.18.0"
        or toolchain["npm"] != "11.16.0"
        or toolchain["bun"] != "1.3.14"
        or "host: x86_64-unknown-linux-gnu" not in toolchain["rustc_verbose"]
    ):
        raise DossierError(
            "candidate toolchain differs from the hosted qualification profile"
        )
    _assert_rust_toolchain_cross_receipt(toolchain, rust_receipt)
    npm_receipt = _json(root / "products" / "npm" / "npm-release-build-receipt.json")
    _assert_npm_toolchain_cross_receipt(toolchain, npm_receipt)

    subject_by_role = {item["role"]: item for item in subjects}
    expected_identity = {
        "build_identity": revision,
        "package_version": version,
        "wire_version": contract.get("wire_version"),
        "contract_hash": contract.get("wire_proto_contract_hash_fnv1a64"),
        "normative_contract_digest_sha256": contract.get("contract_digest_sha256"),
    }
    install_receipts = dossier.get("python_install_receipts")
    if not isinstance(install_receipts, list) or [
        item.get("role") if isinstance(item, dict) else None
        for item in install_receipts
    ] != ["source-wheel", "sdist-rebuilt-wheel"]:
        raise DossierError("candidate Python install receipt roles are incomplete")
    for receipt in install_receipts:
        if set(receipt) != {
            "role",
            "input_subject_role",
            "input_artifact_sha256",
            "artifact_sha256",
            "identity",
            "behavior_receipt",
        }:
            raise DossierError(
                "candidate Python install receipt has an unexpected shape"
            )
        input_role = receipt.get("input_subject_role")
        expected_input_role = {
            "source-wheel": "python:wheel",
            "sdist-rebuilt-wheel": "python:sdist",
        }[receipt["role"]]
        if input_role != expected_input_role:
            raise DossierError("candidate Python receipt has an invalid input role")
        input_subject = subject_by_role[input_role]
        if receipt.get("input_artifact_sha256") != input_subject["sha256"]:
            raise DossierError(
                "candidate Python receipt is not bound to its package subject"
            )
        artifact_digest = receipt.get("artifact_sha256")
        if (
            not isinstance(artifact_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", artifact_digest) is None
        ):
            raise DossierError("candidate Python built-wheel digest is malformed")
        if (
            receipt["role"] == "source-wheel"
            and artifact_digest != input_subject["sha256"]
        ):
            raise DossierError(
                "candidate source-wheel receipt digest differs from its subject"
            )
        if (
            receipt.get("identity") != expected_identity
            or re.fullmatch(
                r"OK check_behavior_vectors: [1-9][0-9]* behavioral \+ 14 canonical wire vectors "
                r"match the ncp binding with zero manifest skips",
                str(receipt.get("behavior_receipt")),
            )
            is None
        ):
            raise DossierError(
                "candidate Python install identity or behavior receipt drifted"
            )

    supply = {
        name: _json(root / "products" / "supply-chain" / name) for name in SUPPLY_FILES
    }
    for name in SUPPLY_FILES:
        retained = root / "products" / "supply-chain" / name
        committed = _git("show", f"{revision}:evidence/supply-chain/{name}")
        if retained.read_bytes() != committed:
            raise DossierError(f"retained supply evidence differs from source: {name}")
    if (
        supply["inventory.v1.json"].get("schema") != "ncp.supply-chain-inventory.v1"
        or supply["inventory.v1.json"].get("release_authorized") is not False
        or supply["provenance-policy.v1.json"].get("schema")
        != "ncp.provenance-policy.v1"
        or supply["provenance-policy.v1.json"].get("release_authorized") is not False
        or supply["license-report.v1.json"].get("schema") != "ncp.license-report.v1"
        or supply["vulnerability-report.v1.json"].get("schema")
        != "ncp.vulnerability-report.v1"
        or supply["sbom.cdx.json"].get("bomFormat") != "CycloneDX"
        or supply["sbom.cdx.json"].get("specVersion") != "1.6"
        or (supply["sbom.cdx.json"].get("metadata") or {}).get("authors")
        != [{"name": "Sepehr Mahmoudian"}]
        or any(
            value.get("candidate_version") != version
            for name, value in supply.items()
            if name != "sbom.cdx.json"
        )
        or ((supply["sbom.cdx.json"].get("metadata") or {}).get("component") or {}).get(
            "version"
        )
        != version
    ):
        raise DossierError("candidate supply-chain evidence boundary is malformed")
    provenance_materials = supply["provenance-policy.v1.json"].get("source_materials")
    inventory_inputs = supply["inventory.v1.json"].get("locked_inputs")
    if (
        not isinstance(provenance_materials, dict)
        or not isinstance(inventory_inputs, dict)
        or provenance_materials.get("bun.lock")
        != npm_receipt.get("typescript_lockfile_sha256")
        or inventory_inputs.get("bun.lock")
        != npm_receipt.get("typescript_lockfile_sha256")
        or provenance_materials.get(TYPESCRIPT_CONTROL_PATH)
        != npm_receipt.get("typescript_control_sha256")
        or inventory_inputs.get(TYPESCRIPT_CONTROL_PATH)
        != npm_receipt.get("typescript_control_sha256")
    ):
        raise DossierError(
            "candidate TypeScript receipt differs from retained source materials"
        )
    integrity = str(npm_receipt.get("typescript_registry_integrity_sha512"))
    _canonical_sha512_sri(integrity, context="candidate TypeScript registry integrity")
    try:
        expected_typescript_sha512 = base64.b64decode(
            integrity.removeprefix("sha512-"), validate=True
        ).hex()
    except ValueError as error:
        raise DossierError(
            "candidate TypeScript registry integrity is malformed"
        ) from error
    typescript_components = [
        component
        for component in supply["sbom.cdx.json"].get("components", [])
        if isinstance(component, dict) and component.get("name") == "typescript"
    ]
    if (
        len(typescript_components) != 1
        or typescript_components[0].get("version")
        != npm_receipt.get("typescript_version")
        or typescript_components[0].get("hashes")
        != [{"alg": "SHA-512", "content": expected_typescript_sha512}]
    ):
        raise DossierError(
            "candidate TypeScript receipt differs from the retained CycloneDX component"
        )
    if subject_checksums is not None:
        try:
            relative_root = root.relative_to(ROOT)
        except ValueError as error:
            raise DossierError(
                "attestation subject checksums require a dossier beneath the repository"
            ) from error
        if subject_checksums.exists():
            raise DossierError(
                f"subject checksum output must not exist: {subject_checksums}"
            )
        if root == subject_checksums.parent or root in subject_checksums.parents:
            raise DossierError(
                "subject checksum output must remain outside the checksummed dossier"
            )
        lines = [
            f"{item['sha256']}  {(relative_root / item['path']).as_posix()}"
            for item in subjects
        ]
        aggregate = root / "checksums.sha256"
        lines.append(
            f"{_sha256(aggregate)}  {(relative_root / 'checksums.sha256').as_posix()}"
        )
        subject_checksums.parent.mkdir(parents=True, exist_ok=True)
        subject_checksums.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_archived_manifest(
    path: Path,
    *,
    revision: str,
    tree: str,
    files: list[dict[str, Any]],
) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": ARCHIVE_FILE_MANIFEST_SCHEMA,
                "source_revision": revision,
                "source_tree": tree,
                "files": files,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _existing_absolute_directory(value: str, *, label: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise DossierError(f"{label} must be an absolute directory")
    try:
        resolved = path.resolve(strict=True)
        mode = resolved.stat().st_mode
    except OSError as error:
        raise DossierError(f"cannot resolve {label}: {error}") from error
    if not stat.S_ISDIR(mode):
        raise DossierError(f"{label} must resolve to a directory")
    return resolved


def _new_private_directory(path: Path, *, label: str) -> None:
    try:
        path.mkdir(mode=0o700)
    except OSError as error:
        raise DossierError(f"cannot create fresh {label}: {error}") from error
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode) or any(path.iterdir()):
        raise DossierError(f"fresh {label} is not one empty plain directory")
    path.chmod(0o700)


def _assert_no_cargo_config_ancestors(path: Path) -> None:
    resolved = path.resolve(strict=True)
    for parent in (resolved, *resolved.parents):
        for relative in (Path(".cargo/config"), Path(".cargo/config.toml")):
            candidate = parent / relative
            try:
                mode = candidate.lstat().st_mode
            except FileNotFoundError:
                continue
            kind = "plain" if stat.S_ISREG(mode) else "linked or special"
            raise DossierError(
                f"candidate build inherits {kind} Cargo configuration: {candidate}"
            )


def _sanitized_build_environment(
    temporary: Path,
    inherited: dict[str, str],
    *,
    revision: str,
    source_date_epoch: int,
) -> dict[str, str]:
    """Return the explicit outer package environment and fresh private paths."""

    if SOURCE_REVISION.fullmatch(revision) is None:
        raise DossierError("sanitized build environment received a malformed revision")
    epoch = str(source_date_epoch)
    if re.fullmatch(r"[0-9]{1,20}", epoch) is None:
        raise DossierError("sanitized build environment received a malformed epoch")
    path_value = inherited.get("PATH")
    if not isinstance(path_value, str) or not path_value:
        raise DossierError("candidate build requires one explicit nonempty PATH")

    inherited_home = _existing_absolute_directory(
        inherited.get("HOME", str(Path.home())), label="inherited HOME"
    )
    rustup_candidate = inherited.get("RUSTUP_HOME", str(inherited_home / ".rustup"))

    home = temporary / "outer-home"
    scratch = temporary / "outer-tmp"
    cargo_home = temporary / "outer-cargo-home"
    npm_cache = temporary / "outer-npm-cache"
    for directory, label in (
        (home, "outer HOME"),
        (scratch, "outer TMPDIR"),
        (cargo_home, "outer Cargo home"),
        (npm_cache, "outer npm cache"),
    ):
        _new_private_directory(directory, label=label)

    environment = {
        "PATH": path_value,
        "HOME": str(home),
        "TMPDIR": str(scratch),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "CARGO_HOME": str(cargo_home),
        "CARGO_INCREMENTAL": "0",
        "CARGO_TERM_COLOR": "never",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "GIT_ALLOW_PROTOCOL": "https",
        "GCM_INTERACTIVE": "never",
        "NPM_CONFIG_CACHE": str(npm_cache),
        "NPM_CONFIG_USERCONFIG": os.devnull,
        "PIP_CONFIG_FILE": os.devnull,
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INDEX": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONSAFEPATH": "1",
        "PYO3_PYTHON": sys.executable,
        "SOURCE_DATE_EPOCH": epoch,
        "NCP_BUILD_IDENTITY": revision,
        "NCP_ARCHIVED_SOURCE_REVISION": revision,
    }
    try:
        rustup_home = _existing_absolute_directory(
            rustup_candidate, label="existing Rustup toolchain home"
        )
    except DossierError:
        # A direct, non-rustup toolchain has no Rustup home to retain.
        if "RUSTUP_HOME" in inherited:
            raise
    else:
        environment["RUSTUP_HOME"] = str(rustup_home)

    advisory_home = inherited.get("NCP_PINNED_ADVISORY_HOME")
    if advisory_home is not None:
        pinned_home = _existing_absolute_directory(
            advisory_home, label="pinned advisory HOME"
        )
        environment["NCP_ADVISORY_DB_PATH"] = str(
            _existing_absolute_directory(
                str(pinned_home / ".cargo" / "advisory-dbs"),
                label="pinned advisory database root",
            )
        )
    return environment


def _qualification_environment(environment: dict[str, str]) -> dict[str, str]:
    qualification_environment = environment.copy()
    if "NCP_PINNED_ADVISORY_HOME" in qualification_environment:
        raise DossierError("qualification environment retained advisory HOME")
    advisory_database = qualification_environment.get("NCP_ADVISORY_DB_PATH")
    if advisory_database is not None:
        qualification_environment["NCP_ADVISORY_DB_PATH"] = str(
            _existing_absolute_directory(
                advisory_database,
                label="pinned advisory database root",
            )
        )
    return qualification_environment


def _populate_outer_cargo_cache(
    source: Path,
    environment: dict[str, str],
) -> None:
    """Populate only a fresh, config-free Cargo home, then force outer offline use."""

    if environment.get("CARGO_NET_OFFLINE") is not None:
        raise DossierError("outer Cargo cache must start in an explicit network phase")
    _assert_no_cargo_config_ancestors(source)
    cargo_home = Path(environment.get("CARGO_HOME", ""))
    if (
        not cargo_home.is_absolute()
        or not cargo_home.is_dir()
        or any(cargo_home.iterdir())
    ):
        raise DossierError("outer Cargo cache is not one fresh empty directory")
    before = _directory_snapshot(source)
    command = ["cargo"]
    for value in OUTER_CARGO_CONFIG:
        command.extend(("--config", value))
    command.extend(
        (
            "fetch",
            "--manifest-path",
            str(source / "Cargo.toml"),
            "--locked",
        )
    )
    _run(command, cwd=source, env=environment)
    if _directory_snapshot(source) != before:
        raise DossierError("outer locked Cargo fetch mutated the exact source tree")
    environment["CARGO_NET_OFFLINE"] = "true"


def _archived_preflight(
    source: Path,
    archived_manifest: Path,
    environment: dict[str, str],
) -> None:
    qualification_environment = _qualification_environment(environment)
    _run(
        ["scripts/check-version-coherence.sh"],
        cwd=source,
        env=qualification_environment,
    )
    _run(
        [sys.executable, "-I", "scripts/check_dependency_exposure.py", "--self-test"],
        cwd=source,
        env=qualification_environment,
    )
    _run(
        [
            sys.executable,
            "-I",
            "scripts/generate_supply_chain_evidence.py",
            "--check",
            "--tracked-files-manifest",
            str(archived_manifest),
        ],
        cwd=source,
        env=qualification_environment,
    )


def _archive_preflight(revision: str) -> None:
    tree, source_date_epoch = _exact_source(revision)
    with tempfile.TemporaryDirectory(
        prefix="ncp-candidate-archive-preflight-"
    ) as directory:
        temporary = Path(directory)
        source = temporary / "source"
        source.mkdir()
        files = _extract_git_archive(revision, source, temporary / "source.tar")
        manifest = temporary / "archived-source-files.json"
        _write_archived_manifest(
            manifest,
            revision=revision,
            tree=tree,
            files=files,
        )
        environment = _sanitized_build_environment(
            temporary,
            os.environ.copy(),
            revision=revision,
            source_date_epoch=source_date_epoch,
        )
        _populate_outer_cargo_cache(source, environment)
        _archived_preflight(source, manifest, environment)


def _build(revision: str, output: Path) -> None:
    tree, source_date_epoch = _exact_source(revision)
    if output.exists():
        raise DossierError(f"output must not already exist: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".ncp-candidate-dossier-", dir=output.parent))
    try:
        with tempfile.TemporaryDirectory(prefix="ncp-candidate-build-") as directory:
            temporary = Path(directory)
            source = temporary / "source"
            source.mkdir()
            archived_files = _extract_git_archive(
                revision, source, temporary / "source.tar"
            )
            archived_manifest = temporary / "archived-source-files.json"
            _write_archived_manifest(
                archived_manifest,
                revision=revision,
                tree=tree,
                files=archived_files,
            )
            products = stage / "products"
            products.mkdir()
            environment = _sanitized_build_environment(
                temporary,
                os.environ.copy(),
                revision=revision,
                source_date_epoch=source_date_epoch,
            )
            _populate_outer_cargo_cache(source, environment)

            _archived_preflight(source, archived_manifest, environment)
            _run(
                [
                    sys.executable,
                    "-I",
                    "scripts/check_rust_packages.py",
                    "--output-dir",
                    str(products / "rust"),
                    "--source-revision",
                    revision,
                ],
                cwd=source,
                env=environment,
            )
            python_install_receipts = _build_python(
                source,
                products,
                revision,
                source_date_epoch,
                temporary,
                environment,
            )
            _build_npm(products, revision, temporary, environment)
            # Revalidate every archived byte/mode after all toolchains have run.
            # Any build that mutated its source invalidates the dossier before
            # repository evidence is copied or a PASS receipt is written.
            _archived_preflight(source, archived_manifest, environment)
            supply_destination = products / "supply-chain"
            supply_destination.mkdir()
            for name in SUPPLY_FILES:
                shutil.copyfile(
                    source / "evidence" / "supply-chain" / name,
                    supply_destination / name,
                )

            contract = _json(source / "contract" / "manifest.v1.json")
            conformance = _json(source / "conformance" / "manifest.v1.json")
            records = _artifact_records(products)
            root_manifest = _json(source / "package.json")
            candidate_version = root_manifest["version"]
            package_subjects, rust_receipt = _package_subject_records(
                products,
                root_manifest,
                candidate_version,
                revision,
                contract["contract_digest_sha256"],
            )
            subject_manifest = {
                "schema": "ncp.candidate-package-subjects.v1",
                "source_revision": revision,
                "subjects": package_subjects,
            }
            (stage / "package-subjects.v1.json").write_text(
                json.dumps(subject_manifest, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            toolchain_receipt = {
                "platform": platform.platform(),
                "runner_image_os": os.environ.get("ImageOS", "UNSET"),
                "runner_image_version": os.environ.get("ImageVersion", "UNSET"),
                "cargo": _tool_version(["cargo", "--version"], environment),
                "cargo_invocation_sha256": _tool_invocation_sha256(
                    "cargo", environment
                ),
                "rustc": _tool_version(["rustc", "--version"], environment),
                "rustc_verbose": _tool_output(["rustc", "-vV"], environment),
                "rustc_invocation_sha256": _tool_invocation_sha256(
                    "rustc", environment
                ),
                "python": _tool_version([sys.executable, "--version"], environment),
                "python_binary_sha256": _tool_invocation_sha256(
                    sys.executable, environment
                ),
                "git": _tool_version([_git_invocation(), "--version"], environment),
                "git_binary_sha256": _tool_invocation_sha256(
                    _git_invocation(), environment
                ),
                "pip": _pip_version(environment),
                "maturin": _tool_version(["maturin", "--version"], environment),
                "node": _tool_version(["node", "--version"], environment),
                "node_binary_sha256": _tool_invocation_sha256("node", environment),
                "npm": _tool_version(["npm", "--version"], environment),
                "npm_invocation_sha256": _tool_invocation_sha256("npm", environment),
                "bun": _tool_version(["bun", "--version"], environment),
                "cargo_deny": _tool_version(
                    ["cargo", "deny", "--version"], environment
                ),
            }
            _assert_rust_toolchain_cross_receipt(toolchain_receipt, rust_receipt)
            dossier = {
                "schema": "ncp.candidate-dossier.v1",
                "source_revision": revision,
                "source_tree": tree,
                "source_date_epoch": source_date_epoch,
                "candidate_version": candidate_version,
                "wire_version": contract["wire_version"],
                "normative_contract_digest_sha256": contract["contract_digest_sha256"],
                "conformance_corpus_digest_sha256": conformance["corpus_digest_sha256"],
                "author": AUTHOR,
                "release_authorized": False,
                "reproducibility_comparisons": REPRODUCIBILITY_COMPARISONS,
                "source_derivations": _source_derivations(revision),
                "verification_boundary": DOSSIER_VERIFICATION_BOUNDARY,
                "toolchain_receipt": toolchain_receipt,
                "artifacts": records,
                "package_subjects": package_subjects,
                "python_install_receipts": python_install_receipts,
                "sbom_scope": SBOM_SCOPE,
                "claim_boundary": CLAIM_BOUNDARY,
            }
            _assert_no_local_absolute_paths(dossier, context="candidate dossier")
            _assert_no_local_absolute_paths(
                subject_manifest,
                context="candidate package-subject manifest",
            )
            (stage / "candidate-dossier.json").write_text(
                json.dumps(dossier, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _write_checksums(stage)
            _verify_dossier(stage)
        os.replace(stage, output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _self_test() -> None:
    if not SOURCE_REVISION.fullmatch("a" * 40):
        raise AssertionError("valid source revision rejected")
    if SOURCE_REVISION.fullmatch("A" * 40) or SOURCE_REVISION.fullmatch("a" * 39):
        raise AssertionError("invalid source revision accepted")
    for hostile_path in (
        "/private/tmp/ncp",
        "C:\\Users\\builder\\ncp",
        "\\\\server\\share\\ncp",
        "\\\\?\\C:\\builder\\ncp",
        "\\rooted-on-current-drive",
        "file:///private/tmp/ncp",
    ):
        try:
            _assert_no_local_absolute_paths(
                {"path": hostile_path}, context="path self-test"
            )
        except DossierError:
            pass
        else:
            raise AssertionError(f"local path passed receipt guard: {hostile_path!r}")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        original_home = root / "original-home"
        advisory_home = root / "advisory-home"
        original_home.mkdir()
        (original_home / ".cargo").mkdir()
        (original_home / ".rustup").mkdir()
        advisory_home.mkdir()
        advisory_database = advisory_home / ".cargo" / "advisory-dbs"
        advisory_database.mkdir(parents=True)
        qualified = _qualification_environment(
            {
                "HOME": str(original_home),
                "CARGO_HOME": "/reviewed/cargo",
                "RUSTUP_HOME": "/reviewed/rustup",
                "NCP_ADVISORY_DB_PATH": str(advisory_database),
            }
        )
        if qualified != {
            "HOME": str(original_home),
            "CARGO_HOME": "/reviewed/cargo",
            "RUSTUP_HOME": "/reviewed/rustup",
            "NCP_ADVISORY_DB_PATH": str(advisory_database.resolve()),
        }:
            raise AssertionError("pinned advisory database changed the fresh HOME")

        sanitized = _sanitized_build_environment(
            root,
            {
                "PATH": "/usr/bin:/bin",
                "HOME": str(original_home),
                "CARGO_ENCODED_RUSTFLAGS": "hostile",
                "GITHUB_TOKEN": "hostile",
                "PYTHONPATH": "hostile",
                "NCP_PINNED_ADVISORY_HOME": str(advisory_home),
            },
            revision="a" * 40,
            source_date_epoch=123,
        )
        if (
            sanitized.get("HOME") != str(root / "outer-home")
            or sanitized.get("TMPDIR") != str(root / "outer-tmp")
            or sanitized.get("CARGO_HOME") != str(root / "outer-cargo-home")
            or sanitized.get("RUSTUP_HOME")
            != str((original_home / ".rustup").resolve())
            or sanitized.get("SOURCE_DATE_EPOCH") != "123"
            or sanitized.get("NCP_ARCHIVED_SOURCE_REVISION") != "a" * 40
            or sanitized.get("NCP_ADVISORY_DB_PATH") != str(advisory_database.resolve())
            or "NCP_PINNED_ADVISORY_HOME" in sanitized
            or any(
                key in sanitized
                for key in (
                    "CARGO_ENCODED_RUSTFLAGS",
                    "GITHUB_TOKEN",
                    "PYTHONPATH",
                )
            )
            or any((root / "outer-cargo-home").iterdir())
        ):
            raise AssertionError("candidate outer build environment was not sanitized")
        try:
            _populate_outer_cargo_cache(
                root,
                {**sanitized, "CARGO_NET_OFFLINE": "true"},
            )
        except DossierError:
            pass
        else:
            raise AssertionError("outer Cargo network phase accepted offline mode")
        if OUTER_CARGO_CONFIG != (
            "net.git-fetch-with-cli=false",
            "net.retry=3",
            "http.timeout=120",
            "http.low-speed-limit=1",
        ):
            raise AssertionError("outer Cargo fetch policy drifted")
        with tempfile.TemporaryDirectory(dir=root) as hostile_directory:
            hostile_root = Path(hostile_directory)
            (hostile_root / ".cargo").mkdir()
            (hostile_root / ".cargo" / "config.toml").write_text(
                '[build]\nrustc-wrapper = "hostile"\n', encoding="utf-8"
            )
            nested_source = hostile_root / "source"
            nested_source.mkdir()
            try:
                _assert_no_cargo_config_ancestors(nested_source)
            except DossierError:
                pass
            else:
                raise AssertionError("ancestor Cargo configuration passed isolation")

        (root / "b").write_bytes(b"second")
        (root / "a").write_bytes(b"first")
        _write_checksums(root)
        lines = (root / "checksums.sha256").read_text(encoding="utf-8").splitlines()
        if not lines[0].endswith("  a") or not lines[1].endswith("  b"):
            raise AssertionError("checksum manifest is not path-sorted")
    for unsafe in ("", "../escape", "/absolute", "a/../b", "a\\b", "a\x00b"):
        try:
            _safe_relative_path(unsafe, label="self-test path")
        except DossierError:
            pass
        else:
            raise AssertionError(f"unsafe dossier path passed: {unsafe!r}")
    for ambiguous in (
        '{"release_authorized":true,"release_authorized":false}',
        '{"outer":{"sha256":"a","sha256":"b"}}',
        '{"size_bytes":NaN}',
    ):
        try:
            _strict_json_object(ambiguous, "hostile self-test JSON")
        except DossierError:
            pass
        else:
            raise AssertionError("duplicate JSON key passed candidate parsing")
    valid_npm_manifest = {
        "name": "@sepahead/ncp",
        "version": "1.0.0-rc.1",
        "devDependencies": {"typescript": "5.9.2"},
    }
    if (
        _validate_npm_dependency_surface(
            valid_npm_manifest, context="hostile self-test package.json"
        )
        != "5.9.2"
    ):
        raise AssertionError("valid npm development dependency pin changed")
    for field in NPM_UNREVIEWED_PACKAGE_GRAPH_FIELDS:
        hostile_manifest = json.loads(json.dumps(valid_npm_manifest))
        hostile_manifest[field] = (
            ["evil"]
            if field in {"bundleDependencies", "bundledDependencies"}
            else {"evil": "1.0.0"}
        )
        try:
            _validate_npm_dependency_surface(
                hostile_manifest, context=f"hostile self-test {field}"
            )
        except DossierError:
            pass
        else:
            raise AssertionError(f"npm dependency field passed: {field}")
    reviewed_typescript_files = [
        {"path": "bin/tsc", "size_bytes": 45, "sha256": "a" * 64},
        {"path": "lib/_tsc.js", "size_bytes": 100, "sha256": "b" * 64},
        {"path": "package.json", "size_bytes": 80, "sha256": "c" * 64},
    ]
    reviewed_typescript_manifest = hashlib.sha256(
        json.dumps(
            reviewed_typescript_files,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    reviewed_typescript_control = {
        "normalized_package_tree": {
            "file_count": 3,
            "total_bytes": 225,
            "manifest_sha256": reviewed_typescript_manifest,
        }
    }
    reviewed_typescript_tree = {
        **reviewed_typescript_control["normalized_package_tree"],
        "files": reviewed_typescript_files,
    }
    _canonical_sha512_sri(
        "sha512-CWBzXQrc/qOkhidw1OzBTQuYRbfyxDXJMVJ1XNwUHGROVmuaeiEm3OslpZ1RV96d7SKKjZKrSJu3+t/xlw3R9A==",
        context="hostile self-test TypeScript integrity",
    )
    for invalid_sri in (
        "sha512-YQ==",
        "sha512-not_base64",
        f"sha512-{'A' * 85}===",
    ):
        try:
            _canonical_sha512_sri(
                invalid_sri, context="hostile self-test TypeScript integrity"
            )
        except DossierError:
            pass
        else:
            raise AssertionError(f"malformed TypeScript SRI passed: {invalid_sri}")
    reviewed_integrity = (
        "sha512-CWBzXQrc/qOkhidw1OzBTQuYRbfyxDXJMVJ1XNwUHGROVmuaeiEm3OslpZ1RV96d"
        "7SKKjZKrSJu3+t/xlw3R9A=="
    )
    bun_fixture = (
        "{\n"
        '  "lockfileVersion": 1,\n'
        '  "configVersion": 1,\n'
        '  "workspaces": {\n'
        '    "": {\n'
        '      "name": "@sepahead/ncp",\n'
        '      "devDependencies": {"typescript": "5.9.2",},\n'
        "    },\n"
        "  },\n"
        '  "packages": {\n'
        '    "typescript": ["typescript@5.9.2", "", '
        '{"bin": {"tsc": "bin/tsc", "tsserver": "bin/tsserver"}}, '
        f'"{reviewed_integrity}"],\n'
        "  },\n"
        "}\n"
    )
    parsed_bun_fixture = _parse_jsonc_object(
        bun_fixture, context="hostile self-test Bun lockfile"
    )
    _validate_typescript_bun_lock(
        parsed_bun_fixture,
        version="5.9.2",
        reviewed_integrity=reviewed_integrity,
    )
    for label, hostile_bun in (
        (
            "commented-only TypeScript package",
            bun_fixture.replace('    "typescript": [', '    // "typescript": ['),
        ),
        (
            "duplicate TypeScript package key",
            bun_fixture.replace(
                '  "packages": {\n',
                '  "packages": {\n    "typescript": [],\n',
            ),
        ),
        (
            "Bun root TypeScript pin divergence",
            bun_fixture.replace(
                '"devDependencies": {"typescript": "5.9.2",}',
                '"devDependencies": {"typescript": "5.9.3",}',
            ),
        ),
        (
            "unreviewed Bun package",
            bun_fixture.replace(
                '  "packages": {\n',
                '  "packages": {\n    "evil": ["evil@1.0.0", "", "", "sha512-YQ=="],\n',
            ),
        ),
    ):
        try:
            _validate_typescript_bun_lock(
                _parse_jsonc_object(hostile_bun, context=f"hostile self-test {label}"),
                version="5.9.2",
                reviewed_integrity=reviewed_integrity,
            )
        except DossierError:
            pass
        else:
            raise AssertionError(f"{label} passed Bun lock validation")
    _validate_typescript_package_tree(
        reviewed_typescript_tree, control=reviewed_typescript_control
    )
    non_ascii_typescript_tree = json.loads(json.dumps(reviewed_typescript_tree))
    non_ascii_typescript_tree["files"][0]["path"] = "bin/tésc"
    try:
        _validate_typescript_package_tree(
            non_ascii_typescript_tree, control=reviewed_typescript_control
        )
    except DossierError:
        pass
    else:
        raise AssertionError("non-ASCII TypeScript package path passed")
    mutated_typescript_tree = json.loads(json.dumps(reviewed_typescript_tree))
    mutated_typescript_tree["files"][1]["sha256"] = "d" * 64
    mutated_typescript_tree["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            mutated_typescript_tree["files"],
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    try:
        _validate_typescript_package_tree(
            mutated_typescript_tree, control=reviewed_typescript_control
        )
    except DossierError:
        pass
    else:
        raise AssertionError(
            "mutated TypeScript _tsc.js passed the reviewed package-tree control"
        )
    npm_toolchain = {
        "node": "v24.18.0",
        "node_binary_sha256": "a" * 64,
    }
    npm_receipt = {
        "node_version": "v24.18.0",
        "node_executable_sha256": "a" * 64,
    }
    _assert_npm_toolchain_cross_receipt(npm_toolchain, npm_receipt)
    for field, wrong in (
        ("node_version", "v24.18.1"),
        ("node_executable_sha256", "b" * 64),
    ):
        mutated_npm_receipt = dict(npm_receipt)
        mutated_npm_receipt[field] = wrong
        try:
            _assert_npm_toolchain_cross_receipt(npm_toolchain, mutated_npm_receipt)
        except DossierError:
            pass
        else:
            raise AssertionError(
                f"mutated npm cross-receipt {field} passed toolchain binding"
            )
    _require_exact_policy_bytes(
        revision="a" * 40,
        path="scripts/example.py",
        committed=b"same\n",
        running=b"same\n",
    )
    try:
        _require_exact_policy_bytes(
            revision="a" * 40,
            path="scripts/example.py",
            committed=b"reviewed\n",
            running=b"dirty\n",
        )
    except DossierError:
        pass
    else:
        raise AssertionError("dirty execution-policy helper passed source binding")
    expected_rust_evidence = {
        *(f"products/rust/{path}" for path in RETAINED_CONDITIONED_LOCKS.values()),
        f"products/rust/{RETAINED_LZ4_CRATE}",
        f"products/rust/{RETAINED_TWOX_CRATE}",
        f"products/rust/{RETAINED_UPSTREAM_TRANSPORT_CRATE}",
    }
    if not expected_rust_evidence.issubset(_expected_product_paths([])):
        raise AssertionError("candidate retained Rust evidence set is incomplete")
    derivations = _source_derivations("a" * 40)
    if [record["artifact_roles"] for record in derivations] != [
        ["rust:ncp-core", "python:sdist"],
        ["python:wheel"],
        ["python:sdist"],
        ["npm:repository-root", "npm:ncp-ts"],
    ] or any("a" * 40 not in derivations[index]["output"] for index in (0, 1, 3)):
        raise AssertionError("candidate source-derivation record is incomplete")
    if _python_wheel_build_command(Path("wheel-output")) != [
        "maturin",
        "build",
        "-m",
        "ncp-python/Cargo.toml",
        "--features",
        "extension-module",
        "--release",
        "--locked",
        "--offline",
        "--strip",
        "--out",
        "wheel-output",
    ]:
        raise AssertionError("candidate Python wheel command is not exact release mode")
    if PYTHON_WHEEL_CARGO_ENVIRONMENT != {
        "CARGO_INCREMENTAL": "0",
        "CARGO_NET_OFFLINE": "true",
    }:
        raise AssertionError("candidate Python wheel environment is not reproducible")
    try:
        _build_python_sdist(
            Path("unused-source"),
            Path("unused-first"),
            Path("unused-second"),
            "a" * 40,
            Path("unused-temporary"),
            {},
            {"CARGO_NET_OFFLINE": "true"},
        )
    except DossierError as error:
        if "CARGO_NET_OFFLINE=true" not in str(error):
            raise AssertionError(
                "sdist offline guard returned the wrong error"
            ) from error
    else:
        raise AssertionError(
            "sdist construction accepted a network-capable environment"
        )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "source"
        source.mkdir()
        (source / "Cargo.toml").write_text(
            '[workspace]\nresolver = "2"\n'
            + FULL_WORKSPACE_MEMBERS
            + '\n\n[workspace.package]\nversion = "0.0.0"\n',
            encoding="utf-8",
        )
        for package in (
            "ncp-core",
            "ncp-zenoh",
            "ncp-gateway",
            "ncp-python",
            "ncp-cpp",
        ):
            crate = source / package
            (crate / "src").mkdir(parents=True)
            dependency = ""
            if package == "ncp-python":
                dependency = (
                    "\n[dependencies]\n"
                    'ncp-core = { path = "../ncp-core", version = "0.0.0" }\n'
                )
            version = (
                "version.workspace = true"
                if package == "ncp-python"
                else 'version = "0.0.0"'
            )
            (crate / "Cargo.toml").write_text(
                "[package]\n"
                f'name = "{package}"\n'
                f"{version}\n"
                'edition = "2021"\n' + dependency,
                encoding="utf-8",
            )
            (crate / "src" / "lib.rs").write_text("", encoding="utf-8")
        environment = {
            **os.environ,
            "CARGO_NET_OFFLINE": "true",
            "CARGO_TARGET_DIR": str(root / "target"),
        }
        _run(
            ["cargo", "generate-lockfile", "--offline"],
            cwd=source,
            env=environment,
            capture=True,
        )
        full_lock_bytes = (source / "Cargo.lock").read_bytes()
        full_lock = hashlib.sha256(full_lock_bytes).hexdigest()
        _reduce_sdist_workspace(source)
        _refresh_sdist_lock(source, environment)
        if _sha256(source / "Cargo.lock") == full_lock:
            raise AssertionError(
                "reduced Python sdist retained the full workspace lock"
            )
        _verify_sdist_workspace(source, environment)
        try:
            _reduce_sdist_workspace(source)
        except DossierError:
            pass
        else:
            raise AssertionError("already reduced Python sdist workspace passed")
        (source / "Cargo.lock").write_bytes(full_lock_bytes)
        try:
            _verify_sdist_workspace(source, environment)
        except DossierError:
            pass
        else:
            raise AssertionError("oversized full workspace lock passed sdist closure")
    for accepted in (
        "linux_x86_64",
        "manylinux2014_x86_64",
        "manylinux_2_17_x86_64.manylinux2014_x86_64",
        "musllinux_1_2_x86_64",
    ):
        if not _is_linux_x86_64_wheel_platform(accepted):
            raise AssertionError(f"reviewed hosted wheel platform rejected: {accepted}")
    for rejected in (
        "any",
        "win_amd64",
        "macosx_14_0_arm64",
        "linux_aarch64",
        "manylinux_2_17_aarch64",
        "manylinux_2_x86_64",
        "manylinux_2_17_x86_64.any",
    ):
        if _is_linux_x86_64_wheel_platform(rejected):
            raise AssertionError(f"non-hosted wheel platform passed: {rejected}")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        subject_paths = ["products/python/ncp-test.whl"]
        for relative in _expected_product_paths(subject_paths):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test")
        _assert_exact_product_files(root, subject_paths)
        (root / "products" / "unexpected.bin").write_bytes(b"unexpected")
        try:
            _assert_exact_product_files(root, subject_paths)
        except DossierError:
            pass
        else:
            raise AssertionError(
                "unexpected candidate product file passed verification"
            )
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        oversized = root / "oversized.json"
        oversized.write_bytes(b"12345")
        try:
            _bounded_utf8(oversized, context="hostile self-test", limit=4)
        except DossierError:
            pass
        else:
            raise AssertionError("oversized candidate control file passed")
        crowded = root / "crowded"
        crowded.mkdir()
        for index in range(3):
            (crowded / str(index)).write_bytes(b"test")
        try:
            _regular_files(crowded, max_files=2, max_entries=2, max_depth=1)
        except DossierError:
            pass
        else:
            raise AssertionError("overpopulated candidate tree passed")
        bounded = root / "bounded.bin"
        bounded.write_bytes(b"12345")
        try:
            _assert_file_size_budget(
                [bounded],
                context="hostile self-test",
                maximum_file_bytes=4,
                maximum_total_bytes=8,
            )
        except DossierError:
            pass
        else:
            raise AssertionError("oversized candidate file passed its byte budget")
        try:
            _sha256(bounded, maximum=4)
        except DossierError:
            pass
        else:
            raise AssertionError("oversized hash input passed its byte budget")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--archive-preflight")
    parser.add_argument("--sdist-preflight")
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-dossier", type=Path)
    parser.add_argument("--subject-checksums", type=Path)
    parser.add_argument("--require-hosted-toolchain", action="store_true")
    args = parser.parse_args()
    try:
        if not sys.flags.isolated or not sys.flags.safe_path:
            raise DossierError(
                "candidate dossier policy must run under isolated Python (-I)"
            )
        if args.self_test:
            if (
                args.archive_preflight is not None
                or args.sdist_preflight is not None
                or args.source_revision is not None
                or args.output is not None
                or args.verify_dossier is not None
                or args.subject_checksums is not None
                or args.require_hosted_toolchain
            ):
                raise DossierError("--self-test cannot be combined with build options")
            _self_test()
            print("OK candidate dossier builder self-test")
            return 0
        if args.archive_preflight is not None:
            if (
                args.sdist_preflight is not None
                or args.source_revision is not None
                or args.output is not None
                or args.verify_dossier is not None
                or args.subject_checksums is not None
                or args.require_hosted_toolchain
            ):
                raise DossierError(
                    "--archive-preflight cannot be combined with build options"
                )
            _archive_preflight(args.archive_preflight)
            print("OK candidate dossier archived-source preflight")
            return 0
        if args.sdist_preflight is not None:
            if (
                args.source_revision is not None
                or args.output is not None
                or args.verify_dossier is not None
                or args.subject_checksums is not None
                or args.require_hosted_toolchain
            ):
                raise DossierError(
                    "--sdist-preflight cannot be combined with build options"
                )
            _sdist_preflight(args.sdist_preflight)
            print("OK exact Python sdist lock and byte-reproducibility preflight")
            return 0
        if args.verify_dossier is not None:
            if args.source_revision is not None or args.output is not None:
                raise DossierError(
                    "--verify-dossier cannot be combined with build options"
                )
            checksums = (
                args.subject_checksums.resolve()
                if args.subject_checksums is not None
                else None
            )
            _verify_dossier(
                args.verify_dossier.resolve(),
                checksums,
                require_hosted_toolchain=args.require_hosted_toolchain,
            )
            print("OK candidate dossier and exact attestation subjects verified")
            return 0
        if args.subject_checksums is not None:
            raise DossierError("--subject-checksums requires --verify-dossier")
        if args.require_hosted_toolchain:
            raise DossierError("--require-hosted-toolchain requires --verify-dossier")
        if args.source_revision is None or args.output is None:
            raise DossierError(
                "build requires --source-revision REV --output NEW_DIRECTORY"
            )
        _build(args.source_revision, args.output.resolve())
    except (DossierError, AssertionError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK candidate dossier built at {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
