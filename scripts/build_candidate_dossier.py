#!/usr/bin/env python3
"""Build a checksummed, reproducibility-compared candidate artifact dossier.

The builder consumes only one exact committed Git archive, binds package build
identity to that revision, and never tags, signs, or publishes.  Hosted CI may
attest its subjects, but release authorization and independent reproduction stay
separate gates.
"""

from __future__ import annotations

import argparse
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


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_FILE_MANIFEST_SCHEMA = "ncp.archived-source-file-manifest.v1"
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
AUTHOR = {"name": "Sepehr Mahmoudian"}
REPRODUCIBILITY_COMPARISONS = {
    "rust_source_archives": "PASS",
    "python_wheel_same_platform": "PASS",
    "python_sdist_same_platform": "PASS",
    "python_sdist_build_install_smoke": "PASS",
    "npm_tarballs": "PASS",
}
SBOM_SCOPE = (
    "Workspace source and resolved dependency inventory; it is retained with the "
    "aggregate dossier and is not an artifact-specific SBOM."
)
CLAIM_BOUNDARY = (
    "Candidate-only build evidence. No tag, registry publication, release "
    "authorization, independent reproduction, or signature is implied."
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
    "rustc",
    "rustc_verbose",
    "python",
    "pip",
    "maturin",
    "node",
    "npm",
    "bun",
    "cargo_deny",
}
MAX_CONTROL_JSON_BYTES = 8 * 1024 * 1024
MAX_CHECKSUM_MANIFEST_BYTES = 64 * 1024
MAX_DOSSIER_REGULAR_FILES = 19
MAX_DOSSIER_ENTRIES = 64
MAX_DOSSIER_DEPTH = 6
MAX_DOSSIER_PATH_BYTES = 512
HASH_CHUNK_BYTES = 1024 * 1024


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
                "The Git archive remains the immutable input; packaging uses a "
                "disposable identity-bearing derivative with only this replacement."
            ),
        },
        {
            "artifact_roles": ["npm:repository-root", "npm:ncp-ts"],
            "source_path": "ncp-ts/src/contract-identity.ts",
            "operation": "replace-exact-build-identity-declaration",
            "input": "export const NCP_BUILD_IDENTITY = 'unreleased-worktree'",
            "output": f"export const NCP_BUILD_IDENTITY = '{revision}'",
            "boundary": (
                "The Git archive remains the immutable input; packaging uses a "
                "disposable identity-bearing derivative with only this replacement."
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


def _git(*args: str) -> bytes:
    return _run(["git", *args], cwd=ROOT, capture=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_files(
    root: Path,
    *,
    max_files: int | None = None,
    max_entries: int | None = None,
    max_depth: int | None = None,
) -> list[Path]:
    files: list[Path] = []
    entries = 0
    for directory, directories, names in os.walk(root, followlinks=False):
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
            files.append(path)
            if max_files is not None and len(files) > max_files:
                raise DossierError(f"artifact tree exceeds the {max_files}-file limit")
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    return files


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


def _copy_regular_tree(source: Path, destination: Path) -> None:
    destination.mkdir()
    for path in _regular_files(source):
        relative = path.relative_to(source)
        output = destination / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        output.chmod(path.lstat().st_mode & 0o777)


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


def _exact_source(revision: str) -> tuple[str, int]:
    if not SOURCE_REVISION.fullmatch(revision):
        raise DossierError(
            "source revision must be exactly 40 lowercase hexadecimal characters"
        )
    head = _git("rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    if head != revision:
        raise DossierError(f"source revision {revision} is not exact HEAD {head}")
    script_path = "scripts/build_candidate_dossier.py"
    committed = _git("show", f"{revision}:{script_path}")
    if committed != Path(__file__).read_bytes():
        raise DossierError(
            f"running {script_path} differs from source revision {revision}"
        )
    tree = _git("rev-parse", f"{revision}^{{tree}}").decode().strip()
    timestamp_text = _git("show", "-s", "--format=%ct", revision).decode().strip()
    if not timestamp_text.isdigit():
        raise DossierError("Git commit timestamp is malformed")
    return tree, int(timestamp_text)


def _extract_git_archive(
    revision: str, destination: Path, archive: Path
) -> list[dict[str, Any]]:
    _run(
        ["git", "archive", "--format=tar", "--output", str(archive), revision],
        cwd=ROOT,
    )
    with tarfile.open(archive, "r:") as package:
        files: list[dict[str, Any]] = []
        seen: set[str] = set()
        for member in package.getmembers():
            path = Path(member.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "." in path.parts
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
                source = package.extractfile(member)
                if source is None:
                    raise DossierError(
                        f"Git archive file cannot be read: {member.name!r}"
                    )
                content = source.read()
                if len(content) != member.size:
                    raise DossierError(
                        f"Git archive file size changed while reading: {member.name!r}"
                    )
                files.append(
                    {
                        "path": canonical,
                        "git_mode": "100755" if member.mode & 0o111 else "100644",
                        "size_bytes": member.size,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
        package.extractall(destination)
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
    with tarfile.open(archive, "r:gz") as package:
        seen: set[str] = set()
        prefixes: set[str] = set()
        for member in package.getmembers():
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
        if len(prefixes) != 1:
            raise DossierError(
                f"Python sdist has {len(prefixes)} top-level paths instead of one"
            )
        package.extractall(destination)
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
    _run([sys.executable, "-m", "venv", str(virtual)], cwd=source)
    python = virtual / "bin" / "python"
    if os.name == "nt":
        python = virtual / "Scripts" / "python.exe"
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-index",
            str(wheel),
        ],
        cwd=source,
    )
    identity = _strict_json_object(
        _run(
            [
                str(python),
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


def _build_python(
    source: Path,
    products: Path,
    revision: str,
    source_date_epoch: int,
    temporary: Path,
) -> list[dict[str, Any]]:
    first = temporary / "wheel-first"
    second = temporary / "wheel-second"
    first.mkdir()
    second.mkdir()
    base_environment = os.environ.copy()
    base_environment.update(
        {
            "NCP_BUILD_IDENTITY": revision,
            "SOURCE_DATE_EPOCH": str(source_date_epoch),
        }
    )
    base = [
        "maturin",
        "build",
        "-m",
        "ncp-python/Cargo.toml",
        "--features",
        "extension-module",
        "--locked",
        "--offline",
        "--strip",
    ]
    first_environment = base_environment.copy()
    first_environment["CARGO_TARGET_DIR"] = str(temporary / "python-target-first")
    second_environment = base_environment.copy()
    second_environment["CARGO_TARGET_DIR"] = str(temporary / "python-target-second")
    _run([*base, "--out", str(first)], cwd=source, env=first_environment)
    _run([*base, "--out", str(second)], cwd=source, env=second_environment)
    _compare_directories(first, second, ".whl")
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
    _inject_packaged_source_identity(sdist_source_first, revision)
    _inject_packaged_source_identity(sdist_source_second, revision)
    sdist_first_snapshot = _directory_snapshot(sdist_source_first)
    sdist_second_snapshot = _directory_snapshot(sdist_source_second)
    sdist_first_environment = first_environment.copy()
    sdist_first_environment.pop("NCP_BUILD_IDENTITY", None)
    sdist_first_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
    sdist_second_environment = second_environment.copy()
    sdist_second_environment.pop("NCP_BUILD_IDENTITY", None)
    sdist_second_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
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
    wheel = _single_file(first, ".whl")
    source_distribution = _single_file(first, ".tar.gz")
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
    _assert_packaged_source_identity(sdist_source, revision)
    sdist_wheels = temporary / "sdist-wheel"
    sdist_wheels.mkdir()
    sdist_environment = base_environment.copy()
    sdist_environment.pop("NCP_BUILD_IDENTITY", None)
    sdist_environment.pop("NCP_EXPECTED_BUILD_IDENTITY", None)
    sdist_environment["CARGO_TARGET_DIR"] = str(temporary / "sdist-target")
    _run(
        [
            "maturin",
            "build",
            "-m",
            "ncp-python/Cargo.toml",
            "--features",
            "extension-module",
            "--locked",
            "--offline",
            "--strip",
            "--out",
            str(sdist_wheels),
        ],
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


def _build_npm(products: Path, revision: str, temporary: Path) -> None:
    first = temporary / "npm-first"
    second = temporary / "npm-second"
    script = ROOT / "ncp-ts" / "scripts" / "build-release.mjs"
    _run(
        ["node", str(script), "--source-revision", revision, "--output", str(first)],
        cwd=ROOT,
    )
    _run(
        ["node", str(script), "--source-revision", revision, "--output", str(second)],
        cwd=ROOT,
    )
    _compare_directories(first, second, ".tgz")
    first_receipt = _json(first / "npm-release-build-receipt.json")
    second_receipt = _json(second / "npm-release-build-receipt.json")
    if first_receipt != second_receipt:
        raise DossierError("source-identical npm build receipts differ")
    shutil.copytree(first, products / "npm")


def _tool_version(command: list[str]) -> str:
    output = _run(command, cwd=ROOT, capture=True).decode("utf-8", "replace").strip()
    return output.splitlines()[0] if output else "UNKNOWN"


def _tool_output(command: list[str]) -> str:
    output = _run(command, cwd=ROOT, capture=True).decode("utf-8", "replace").strip()
    return output if output else "UNKNOWN"


def _artifact_records(products: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in _regular_files(products):
        records.append(
            {
                "path": path.relative_to(products.parent).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    return records


def _expected_product_paths(subject_paths: list[str]) -> set[str]:
    return {
        *subject_paths,
        "products/rust/rust-package-receipt.json",
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


def _package_subject_records(
    products: Path,
    root_manifest: dict[str, Any],
    version: str,
    revision: str,
    normative_digest: str,
    *,
    require_hosted_wheel: bool = False,
) -> list[dict[str, Any]]:
    expected: list[tuple[str, Path]] = [
        (
            f"rust:{crate}",
            products / "rust" / f"{crate}-{version}.crate",
        )
        for crate in ("ncp-core", "ncp-zenoh", "ncp-cpp", "ncp-python", "ncp-gateway")
    ]
    rust_receipt = _json(products / "rust" / "rust-package-receipt.json")
    if (
        set(rust_receipt)
        != {
            "schema",
            "source_revision",
            "embedded_build_identity",
            "candidate_version",
            "reproducibility_comparison",
            "archives",
        }
        or rust_receipt.get("schema") != "ncp.rust-package-receipt.v1"
        or rust_receipt.get("source_revision") != revision
        or rust_receipt.get("embedded_build_identity") != revision
        or rust_receipt.get("candidate_version") != version
        or rust_receipt.get("reproducibility_comparison") != "PASS"
    ):
        raise DossierError("candidate Rust package receipt identity is invalid")
    rust_archives = rust_receipt.get("archives")
    expected_rust_archives = [
        {
            "crate": role.removeprefix("rust:"),
            "path": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for role, path in expected
    ]
    if rust_archives != expected_rust_archives:
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
    expected_receipt_keys = {
        "schema",
        "package_name",
        "package_version",
        "source_revision",
        "build_identity",
        "normative_contract_digest_sha256",
        "node_version",
        "typescript_version",
        "rust_build_identity_probe_passed",
        "artifacts",
    }
    if (
        set(npm_receipt) != expected_receipt_keys
        or npm_receipt.get("schema") != "ncp.npm-release-build-receipt.v1"
        or npm_receipt.get("package_name") != root_manifest.get("name")
        or npm_receipt.get("source_revision") != revision
        or npm_receipt.get("build_identity") != revision
        or npm_receipt.get("package_version") != version
        or npm_receipt.get("normative_contract_digest_sha256") != normative_digest
        or npm_receipt.get("typescript_version")
        != (root_manifest.get("devDependencies") or {}).get("typescript")
        or not isinstance(npm_receipt.get("node_version"), str)
        or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", npm_receipt["node_version"]) is None
        or npm_receipt.get("rust_build_identity_probe_passed") is not True
    ):
        raise DossierError("candidate npm receipt identity is invalid")
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
            "sha256": _sha256(path),
        }
        for role, path in expected
    ]
    if tuple(record["role"] for record in records) != PACKAGE_SUBJECT_ROLES:
        raise DossierError(
            "candidate package subject roles are incomplete or duplicated"
        )
    return records


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
        if _sha256(root / path_value) != digest:
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
    _verify_checksum_manifest(root, dossier_files)
    dossier = _json(root / "candidate-dossier.json")
    subject_manifest = _json(root / "package-subjects.v1.json")
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
        if not isinstance(size, int) or size < 0 or path.stat().st_size != size:
            raise DossierError(
                f"candidate package subject size differs for {path_value}"
            )
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or _sha256(path) != digest
        ):
            raise DossierError(
                f"candidate package subject SHA-256 differs for {path_value}"
            )
        subject_paths.append(path_value)
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
    independently_derived_subjects = _package_subject_records(
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
        or re.fullmatch(r"pip [0-9]+\.[0-9]+\.[0-9]+ .+", toolchain["pip"]) is None
        or re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", toolchain["node"]) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", toolchain["npm"]) is None
        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", toolchain["bun"]) is None
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
        or not toolchain["pip"].startswith("pip 26.1.2 ")
        or toolchain["node"] != "v24.18.0"
        or toolchain["npm"] != "11.16.0"
        or toolchain["bun"] != "1.3.14"
        or "host: x86_64-unknown-linux-gnu" not in toolchain["rustc_verbose"]
    ):
        raise DossierError(
            "candidate toolchain differs from the hosted qualification profile"
        )
    npm_receipt = _json(root / "products" / "npm" / "npm-release-build-receipt.json")
    if npm_receipt.get("node_version") != toolchain["node"]:
        raise DossierError("candidate npm receipt and dossier Node.js versions differ")

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


def _archived_preflight(
    source: Path,
    archived_manifest: Path,
    environment: dict[str, str],
) -> None:
    qualification_environment = environment.copy()
    advisory_home = environment.get("NCP_PINNED_ADVISORY_HOME")
    if advisory_home is not None:
        advisory_path = Path(advisory_home)
        if not advisory_path.is_absolute() or not advisory_path.is_dir():
            raise DossierError(
                "NCP_PINNED_ADVISORY_HOME is not an existing absolute directory"
            )
        qualification_environment.setdefault(
            "CARGO_HOME",
            str(Path(environment.get("HOME", str(Path.home()))) / ".cargo"),
        )
        qualification_environment["HOME"] = str(advisory_path)
    _run(
        ["scripts/check-version-coherence.sh"],
        cwd=source,
        env=qualification_environment,
    )
    _run(
        [sys.executable, "scripts/check_dependency_exposure.py", "--self-test"],
        cwd=source,
        env=qualification_environment,
    )
    _run(
        [
            sys.executable,
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
        environment = os.environ.copy()
        environment.update(
            {
                "SOURCE_DATE_EPOCH": str(source_date_epoch),
                "NCP_BUILD_IDENTITY": revision,
                "NCP_ARCHIVED_SOURCE_REVISION": revision,
            }
        )
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
            environment = os.environ.copy()
            environment["SOURCE_DATE_EPOCH"] = str(source_date_epoch)
            environment["NCP_BUILD_IDENTITY"] = revision
            environment["NCP_ARCHIVED_SOURCE_REVISION"] = revision

            _archived_preflight(source, archived_manifest, environment)
            _run(
                [
                    sys.executable,
                    "scripts/check_rust_packages.py",
                    "--offline",
                    "--output-dir",
                    str(products / "rust"),
                    "--source-revision",
                    revision,
                ],
                cwd=source,
                env=environment,
            )
            python_install_receipts = _build_python(
                source, products, revision, source_date_epoch, temporary
            )
            _build_npm(products, revision, temporary)
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
            package_subjects = _package_subject_records(
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
                "toolchain_receipt": {
                    "platform": platform.platform(),
                    "runner_image_os": os.environ.get("ImageOS", "UNSET"),
                    "runner_image_version": os.environ.get("ImageVersion", "UNSET"),
                    "cargo": _tool_version(["cargo", "--version"]),
                    "rustc": _tool_version(["rustc", "--version"]),
                    "rustc_verbose": _tool_output(["rustc", "-vV"]),
                    "python": _tool_version([sys.executable, "--version"]),
                    "pip": _tool_version([sys.executable, "-m", "pip", "--version"]),
                    "maturin": _tool_version(["maturin", "--version"]),
                    "node": _tool_version(["node", "--version"]),
                    "npm": _tool_version(["npm", "--version"]),
                    "bun": _tool_version(["bun", "--version"]),
                    "cargo_deny": _tool_version(["cargo", "deny", "--version"]),
                },
                "artifacts": records,
                "package_subjects": package_subjects,
                "python_install_receipts": python_install_receipts,
                "sbom_scope": SBOM_SCOPE,
                "claim_boundary": CLAIM_BOUNDARY,
            }
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
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
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
    derivations = _source_derivations("a" * 40)
    if [record["artifact_roles"] for record in derivations] != [
        ["rust:ncp-core", "python:sdist"],
        ["npm:repository-root", "npm:ncp-ts"],
    ] or any("a" * 40 not in record["output"] for record in derivations):
        raise AssertionError("candidate source-derivation record is incomplete")
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--archive-preflight")
    parser.add_argument("--source-revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-dossier", type=Path)
    parser.add_argument("--subject-checksums", type=Path)
    parser.add_argument("--require-hosted-toolchain", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            if (
                args.archive_preflight is not None
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
                args.source_revision is not None
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
