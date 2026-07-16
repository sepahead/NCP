#!/usr/bin/env python3
"""Generate deterministic local supply-chain inventories and review evidence.

This generator deliberately separates reproducible, repository-owned evidence from
the signed and independently reproduced release dossier.  It inventories every
resolved Rust package, the Python/npm surfaces, declared features and generators,
tracked assets/data, licenses, and all advisory findings applicable to Cargo.lock.
It never treats a local scan or an unsigned SBOM as release authorization.
"""

from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "supply-chain"
OUTPUTS = {
    "inventory.v1.json": "ncp.supply-chain-inventory.v1",
    "sbom.cdx.json": "CycloneDX",
    "license-report.v1.json": "ncp.license-report.v1",
    "vulnerability-report.v1.json": "ncp.vulnerability-report.v1",
    "provenance-policy.v1.json": "ncp.provenance-policy.v1",
}
GENERATOR_OUTPUTS = {
    "ncp-core/src/bin/gen-schemas.rs": ["schemas/*.schema.json", "schemas/index.json"],
    "ncp-ts/scripts/build-release.mjs": [
        "candidate npm tarballs",
        "npm release receipt",
    ],
    "ncp-ts/scripts/sync-bindings.mjs": [
        "ncp-ts/src/generated/*.ts",
        "ncp-ts/dist/generated/*.js",
        "ncp-ts/dist/generated/*.d.ts",
    ],
    "scripts/build_candidate_dossier.py": [
        "candidate package dossier",
        "candidate checksums and build receipt",
    ],
    "scripts/check_request_digests.py": [
        "conformance/behavior/vectors.json embedded request digests",
        "conformance/vectors/{step_request,run_request,close_session}.json embedded digests",
    ],
    "scripts/check_rust_packages.py": [
        "candidate Rust crate archives",
        "Rust package checksum receipt",
    ],
    "scripts/check_wire_baseline.py": ["conformance/baseline/v*/ frozen wire cut"],
    "scripts/gen_diagrams.py": ["docs/diagrams/*.svg"],
    "scripts/generate_audit_artifacts.py": ["evidence/audit/*.json"],
    "scripts/generate_conformance_manifest.py": ["conformance/manifest.v1.json"],
    "scripts/generate_convergence_manifest.py": [
        "evidence/convergence/local-convergence.v1.json"
    ],
    "scripts/generate_contract_manifest.py": ["contract/manifest.v1.json"],
    "scripts/generate_decision_registry.py": [
        "docs/adr/decision-registry.proposed.v1.json"
    ],
    "scripts/generate_file_review_ledger.py": [
        "docs/handoff/max-effort-file-review.v2.csv",
        "docs/handoff/max-effort-file-review-manifest.v2.json",
    ],
    "scripts/generate_implementation_ledger.py": [
        "docs/implementation/NCP_1_0_TASK_LEDGER.md",
        "docs/implementation/NCP_1_0_RESUMPTION.md",
    ],
    "scripts/generate_max_effort_handoff_index.py": [
        "docs/handoff/max-effort-source-index.v2.json"
    ],
    "scripts/generate_max_effort_review_template.py": [
        "docs/handoff/max-effort-task-review.v2.json"
    ],
    "scripts/generate_supply_chain_evidence.py": ["evidence/supply-chain/*.json"],
    "scripts/plot_perf.py": ["docs/plots/*.svg"],
    "scripts/render_acl_template.py": ["operator-selected concrete Zenoh ACL config"],
    "scripts/sync_rust_package_testdata.py": ["ncp-{core,zenoh,cpp}/testdata/**"],
}
ASSET_PREFIXES = (
    "assets/",
    "conformance/",
    "deploy/",
    "docs/plots/data/",
    "schemas/",
)
REVIEWED_ADVISORY_FINDINGS = {
    (
        "RUSTSEC-2024-0436",
        "unmaintained",
        "paste",
        "1.0.15",
        (),
    ): "transitive-unmaintained-no-upstream-fix",
    (
        "RUSTSEC-2025-0134",
        "unmaintained",
        "rustls-pemfile",
        "2.2.0",
        (),
    ): "transitive-unmaintained-no-upstream-fix",
    (
        "RUSTSEC-2026-0041",
        "vulnerability",
        "lz4_flex",
        "0.10.0",
        ("CVE-2026-32829", "GHSA-vvp9-7p8x-rfvv"),
    ): "compression-disabled-and-resolved-feature-graph-guarded",
}
REVIEWED_ADVISORY_IDS = {key[0] for key in REVIEWED_ADVISORY_FINDINGS}
ARCHIVE_FILE_MANIFEST_SCHEMA = "ncp.archived-source-file-manifest.v1"
SOURCE_REVISION = re.compile(r"^[0-9a-f]{40}$")
CYCLONEDX_HASH_ALGORITHMS = {
    "MD5",
    "SHA-1",
    "SHA-256",
    "SHA-384",
    "SHA-512",
    "SHA3-256",
    "SHA3-384",
    "SHA3-512",
    "BLAKE2b-256",
    "BLAKE2b-384",
    "BLAKE2b-512",
    "BLAKE3",
}
CYCLONEDX_HASH_HEX_LENGTHS = {
    "MD5": 32,
    "SHA-1": 40,
    "SHA-256": 64,
    "SHA-384": 96,
    "SHA-512": 128,
    "SHA3-256": 64,
    "SHA3-384": 96,
    "SHA3-512": 128,
    "BLAKE2b-256": 64,
    "BLAKE2b-384": 96,
    "BLAKE2b-512": 128,
    "BLAKE3": 64,
}
SRI_TO_CYCLONEDX = {
    "sha256": "SHA-256",
    "sha384": "SHA-384",
    "sha512": "SHA-512",
}
NCP_SBOM_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://github.com/sepahead/NCP/evidence/supply-chain/sbom.cdx.json",
)
CRATES_IO_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"
INTERNAL_BOM_REF_PREFIX = "urn:ncp:workspace:"
INTERNAL_BOM_REF_SURFACES = {"cargo", "npm", "python", "root"}
REVIEWED_SPDX_LICENSE_IDS = {
    "0BSD",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSL-1.0",
    "CDLA-Permissive-2.0",
    "EPL-2.0",
    "ISC",
    "LGPL-2.1-or-later",
    "MIT",
    "MPL-2.0",
    "Unicode-3.0",
    "Unlicense",
    "Zlib",
}
REVIEWED_SPDX_EXCEPTION_IDS = {"LLVM-exception"}
REVIEWED_LEGACY_SPDX_EXPRESSIONS = {
    "Apache-2.0/MIT": "Apache-2.0 OR MIT",
    "MIT/Apache-2.0": "MIT OR Apache-2.0",
    "Unlicense/MIT": "Unlicense OR MIT",
}
MAX_SPDX_TOKENS = 128


class EvidenceError(ValueError):
    """Supply-chain evidence cannot be generated or validated safely."""


def _strict_json(raw: str | bytes, context: str) -> Any:
    """Decode JSON while rejecting duplicate object keys at every depth."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise EvidenceError(f"{context} contains duplicate JSON key {key!r}")
            value[key] = item
        return value

    def reject_non_finite(token: str) -> Any:
        raise EvidenceError(f"{context} contains non-finite JSON number {token!r}")

    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", "strict")
        except UnicodeError as error:
            raise EvidenceError(f"cannot parse {context}: {error}") from error
    try:
        return json.loads(
            raw,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_non_finite,
        )
    except json.JSONDecodeError as error:
        raise EvidenceError(f"cannot parse {context}: {error}") from error


class _SpdxParser:
    """Parse the deliberately bounded SPDX subset reviewed for this lockfile."""

    def __init__(self, tokens: list[str], context: str) -> None:
        self.tokens = tokens
        self.context = context
        self.index = 0
        self.depth = 0

    def parse(self) -> tuple[Any, ...]:
        node = self._parse_or()
        if self._peek() is not None:
            raise EvidenceError(
                f"{self.context} SPDX expression has an unexpected token "
                f"{self._peek()!r}"
            )
        return node

    def _peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise EvidenceError(f"{self.context} SPDX expression ended unexpectedly")
        self.index += 1
        return token

    def _parse_or(self) -> tuple[Any, ...]:
        node = self._parse_and()
        while self._peek() == "OR":
            self._take()
            node = ("or", node, self._parse_and())
        return node

    def _parse_and(self) -> tuple[Any, ...]:
        node = self._parse_with()
        while self._peek() == "AND":
            self._take()
            node = ("and", node, self._parse_with())
        return node

    def _parse_with(self) -> tuple[Any, ...]:
        node = self._parse_primary()
        if self._peek() != "WITH":
            return node
        self._take()
        if node[0] != "license":
            raise EvidenceError(
                f"{self.context} SPDX WITH must apply directly to a license ID"
            )
        exception = self._take()
        if exception not in REVIEWED_SPDX_EXCEPTION_IDS:
            raise EvidenceError(
                f"{self.context} SPDX exception is not reviewed: {exception!r}"
            )
        return ("with", node, exception)

    def _parse_primary(self) -> tuple[Any, ...]:
        token = self._take()
        if token == "(":
            self.depth += 1
            if self.depth > MAX_SPDX_TOKENS // 2:
                raise EvidenceError(
                    f"{self.context} SPDX expression nesting is excessive"
                )
            node = self._parse_or()
            if self._peek() != ")":
                raise EvidenceError(
                    f"{self.context} SPDX expression has an unmatched parenthesis"
                )
            self._take()
            self.depth -= 1
            return ("group", node)
        if token in {"AND", "OR", "WITH", ")"}:
            raise EvidenceError(
                f"{self.context} SPDX expression has an unexpected token {token!r}"
            )
        if token not in REVIEWED_SPDX_LICENSE_IDS:
            raise EvidenceError(
                f"{self.context} SPDX license ID is not reviewed: {token!r}"
            )
        return ("license", token)


def _spdx_tokens(raw: str, context: str) -> list[str]:
    if any(character.isspace() and character != " " for character in raw):
        raise EvidenceError(
            f"{context} SPDX expression contains non-canonical whitespace"
        )
    expression = raw.strip()
    if not expression:
        raise EvidenceError(f"{context} SPDX expression is empty")
    expression = REVIEWED_LEGACY_SPDX_EXPRESSIONS.get(expression, expression)
    tokens: list[str] = []
    position = 0
    while position < len(expression):
        if expression[position] == " ":
            position += 1
            continue
        match = re.match(r"\(|\)|[A-Za-z0-9][A-Za-z0-9.+-]*", expression[position:])
        if match is None:
            raise EvidenceError(
                f"{context} SPDX expression contains an invalid character at "
                f"offset {position}"
            )
        tokens.append(match.group(0))
        if len(tokens) > MAX_SPDX_TOKENS:
            raise EvidenceError(f"{context} SPDX expression has too many tokens")
        position += len(match.group(0))
    return tokens


def _format_spdx(node: tuple[Any, ...], parent_precedence: int = 0) -> str:
    kind = node[0]
    if kind == "license":
        text = str(node[1])
        precedence = 4
    elif kind == "group":
        text = f"({_format_spdx(node[1])})"
        precedence = 4
    elif kind == "with":
        text = f"{_format_spdx(node[1], 3)} WITH {node[2]}"
        precedence = 3
    elif kind in {"and", "or"}:
        precedence = 2 if kind == "and" else 1
        operator = kind.upper()
        text = (
            f"{_format_spdx(node[1], precedence)} {operator} "
            f"{_format_spdx(node[2], precedence)}"
        )
    else:  # pragma: no cover - parser construction makes this unreachable
        raise AssertionError(f"unknown SPDX AST node {kind!r}")
    return f"({text})" if precedence < parent_precedence else text


def _normalize_spdx_expression(raw: object, context: str) -> str:
    if not isinstance(raw, str):
        raise EvidenceError(f"{context} SPDX expression must be a string")
    normalized = _format_spdx(_SpdxParser(_spdx_tokens(raw, context), context).parse())
    reparsed = _format_spdx(
        _SpdxParser(_spdx_tokens(normalized, context), context).parse()
    )
    if reparsed != normalized:
        raise EvidenceError(f"{context} SPDX normalization is not idempotent")
    return normalized


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise EvidenceError(
            f"cannot parse {path.relative_to(ROOT)}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise EvidenceError(f"{path.relative_to(ROOT)} must contain a TOML table")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise EvidenceError(
            f"cannot parse {path.relative_to(ROOT)}: {error}"
        ) from error
    value = _strict_json(raw, str(path.relative_to(ROOT)))
    if not isinstance(value, dict):
        raise EvidenceError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise EvidenceError(f"cannot hash {path.relative_to(ROOT)}: {error}") from error


def _run(command: list[str]) -> bytes:
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise EvidenceError(f"cannot execute {command[0]}: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise EvidenceError(f"{' '.join(command)} failed: {detail}")
    return process.stdout


def _cargo_metadata() -> dict[str, Any]:
    raw = _run(
        [
            "cargo",
            "metadata",
            "--locked",
            "--offline",
            "--all-features",
            "--format-version",
            "1",
        ]
    )
    value = _strict_json(raw, "cargo metadata output")
    if not isinstance(value, dict):
        raise EvidenceError("cargo metadata root must be an object")
    return value


def _safe_repository_path(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise EvidenceError(f"archived source contains an invalid path: {value!r}")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceError(f"archived source contains an unsafe path: {value!r}")
    if path.as_posix() != value:
        raise EvidenceError(f"archived source path is not canonical POSIX: {value!r}")
    return value


def _validate_archived_file_records(
    root: Path, records: list[dict[str, Any]]
) -> list[str]:
    files = [record["path"] for record in records]
    actual: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise EvidenceError(f"archived source contains a link: {relative}")
        if path.is_file():
            actual.append(relative)
        elif not path.is_dir():
            raise EvidenceError(f"archived source contains a special entry: {relative}")

    if len(actual) != len(files) or set(actual) != set(files):
        raise EvidenceError(
            "archived source differs from its exact file manifest: "
            f"missing={sorted(set(files) - set(actual))!r}, "
            f"extra={sorted(set(actual) - set(files))!r}"
        )

    for expected in records:
        relative = expected["path"]
        path = root / relative
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise EvidenceError(f"archived source entry is not a file: {relative}")
        git_mode = "100755" if metadata.st_mode & stat.S_IXUSR else "100644"
        if git_mode != expected["git_mode"]:
            raise EvidenceError(f"archived source mode differs for {relative}")
        if metadata.st_size != expected["size_bytes"]:
            raise EvidenceError(f"archived source size differs for {relative}")
        if _sha256(path) != expected["sha256"]:
            raise EvidenceError(f"archived source SHA-256 differs for {relative}")
    return files


def _archived_tracked_files(manifest_path: Path) -> list[str]:
    revision = os.environ.get("NCP_ARCHIVED_SOURCE_REVISION")
    if revision is None or SOURCE_REVISION.fullmatch(revision) is None:
        raise EvidenceError(
            "--tracked-files-manifest requires NCP_ARCHIVED_SOURCE_REVISION with one exact commit"
        )
    if (ROOT / ".git").exists():
        raise EvidenceError(
            "archived-source inventory must not run inside a Git worktree"
        )
    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise EvidenceError(
            f"cannot parse archived-source file manifest: {error}"
        ) from error
    manifest = _strict_json(raw, "archived-source file manifest")
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema",
        "source_revision",
        "source_tree",
        "files",
    }:
        raise EvidenceError("archived-source file manifest has an unexpected shape")
    if manifest.get("schema") != ARCHIVE_FILE_MANIFEST_SCHEMA:
        raise EvidenceError("archived-source file manifest schema is unsupported")
    if manifest.get("source_revision") != revision:
        raise EvidenceError(
            "archived-source file manifest revision differs from the environment"
        )
    tree = manifest.get("source_tree")
    if not isinstance(tree, str) or re.fullmatch(r"[0-9a-f]{40,64}", tree) is None:
        raise EvidenceError("archived-source file manifest tree identity is malformed")
    files_value = manifest.get("files")
    if not isinstance(files_value, list):
        raise EvidenceError("archived-source file manifest has no file list")
    records: list[dict[str, Any]] = []
    for value in files_value:
        if not isinstance(value, dict) or set(value) != {
            "path",
            "git_mode",
            "size_bytes",
            "sha256",
        }:
            raise EvidenceError("archived-source file record has an unexpected shape")
        path = _safe_repository_path(value.get("path"))
        mode = value.get("git_mode")
        size = value.get("size_bytes")
        digest = value.get("sha256")
        if mode not in {"100644", "100755"}:
            raise EvidenceError(f"archived source has unsupported Git mode for {path}")
        if not isinstance(size, int) or size < 0:
            raise EvidenceError(f"archived source has invalid size for {path}")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise EvidenceError(f"archived source has invalid SHA-256 for {path}")
        records.append(value)
    files = [record["path"] for record in records]
    if files != sorted(set(files)):
        raise EvidenceError(
            "archived-source file manifest must be sorted and duplicate-free"
        )
    return _validate_archived_file_records(ROOT, records)


def _tracked_files(manifest_path: Path | None = None) -> list[str]:
    if manifest_path is not None:
        return _archived_tracked_files(manifest_path)
    if os.environ.get("NCP_ARCHIVED_SOURCE_REVISION") is not None:
        raise EvidenceError(
            "archived-source inventory requires an exact --tracked-files-manifest"
        )
    raw = _run(["git", "ls-files", "--stage", "-z"])
    try:
        entries = [part.decode("utf-8") for part in raw.split(b"\0") if part]
    except UnicodeError as error:
        raise EvidenceError(f"tracked path is not UTF-8: {error}") from error
    paths: list[str] = []
    for entry in entries:
        match = re.fullmatch(r"([0-7]{6}) ([0-9a-f]{40,64}) ([0-3])\t(.+)", entry)
        if match is None:
            raise EvidenceError("git ls-files returned a malformed stage entry")
        mode, _object_id, stage_index, path_value = match.groups()
        path = _safe_repository_path(path_value)
        if stage_index != "0" or mode not in {"100644", "100755"}:
            raise EvidenceError(
                f"tracked path is unmerged, linked, submodule, or special: {path} mode={mode} stage={stage_index}"
            )
        absolute = ROOT / path
        if absolute.is_symlink() or not absolute.is_file():
            raise EvidenceError(f"tracked path is not a regular file: {path}")
        actual_mode = "100755" if absolute.lstat().st_mode & stat.S_IXUSR else "100644"
        if actual_mode != mode:
            raise EvidenceError(f"tracked path mode differs from the Git index: {path}")
        paths.append(path)
    if paths != sorted(paths):
        paths.sort()
    return paths


def _purl(ecosystem: str, name: str, version: str) -> str:
    encoded_version = urllib.parse.quote(version, safe=".-_~")
    if ecosystem == "npm" and name.startswith("@"):
        parts = name.split("/")
        if len(parts) != 2 or not all(parts):
            raise EvidenceError(f"scoped npm package name is malformed: {name!r}")
        namespace, package = parts
        return (
            f"pkg:npm/{urllib.parse.quote(namespace, safe='.-_~')}/"
            f"{urllib.parse.quote(package, safe='.-_~')}@{encoded_version}"
        )
    if "/" in name:
        raise EvidenceError(
            f"package name requires an explicit namespace rule: {ecosystem}:{name}"
        )
    encoded = urllib.parse.quote(name, safe=".-_~")
    return f"pkg:{ecosystem}/{encoded}@{encoded_version}"


def _internal_bom_ref(surface: str, name: str, version: str) -> str:
    if surface not in INTERNAL_BOM_REF_SURFACES:
        raise EvidenceError(f"unknown internal component surface {surface!r}")
    if not isinstance(name, str) or not name:
        raise EvidenceError(f"{surface} internal component name is malformed")
    if not isinstance(version, str) or not version:
        raise EvidenceError(f"{surface} internal component version is malformed")
    encoded_name = urllib.parse.quote(name, safe=".-_~")
    encoded_version = urllib.parse.quote(version, safe=".-_~")
    return f"{INTERNAL_BOM_REF_PREFIX}{surface}:{encoded_name}@{encoded_version}"


def _cargo_packages(
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise EvidenceError("cargo metadata has no package array")
    records: list[dict[str, Any]] = []
    refs: dict[str, str] = {}
    seen: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise EvidenceError("cargo metadata contains a non-object package")
        identifier = package.get("id")
        name = package.get("name")
        version = package.get("version")
        if not all(
            isinstance(value, str) and value for value in (identifier, name, version)
        ):
            raise EvidenceError("cargo package identity is malformed")
        source = package.get("source")
        manifest_path = package.get("manifest_path")
        if source is None:
            if not isinstance(manifest_path, str):
                raise EvidenceError(
                    f"workspace Cargo package {name} has no manifest path"
                )
            try:
                manifest_inside_root = (
                    Path(manifest_path).resolve().is_relative_to(ROOT.resolve())
                )
            except (OSError, RuntimeError) as error:
                raise EvidenceError(
                    f"cannot resolve workspace manifest for {name}: {error}"
                ) from error
            if not manifest_inside_root:
                raise EvidenceError(
                    f"workspace Cargo package {name} escapes the repository"
                )
            reference = _internal_bom_ref("cargo", name, version)
            purl = None
            source_label = "workspace"
        elif source == CRATES_IO_SOURCE:
            reference = _purl("cargo", name, version)
            purl = reference
            source_label = source
        else:
            raise EvidenceError(
                f"Cargo package {name} has an unreviewed non-registry source {source!r}"
            )
        if reference in seen:
            raise EvidenceError(f"ambiguous Cargo component reference {reference}")
        seen.add(reference)
        if identifier in refs:
            raise EvidenceError(f"duplicate Cargo metadata identity {identifier!r}")
        refs[identifier] = reference
        license_expression_raw = package.get("license")
        license_file = package.get("license_file")
        if license_expression_raw is not None and not isinstance(
            license_expression_raw, str
        ):
            raise EvidenceError(
                f"Cargo package {name} {version} has malformed license metadata"
            )
        if license_file is not None and (
            not isinstance(license_file, str) or not license_file
        ):
            raise EvidenceError(
                f"Cargo package {name} {version} has malformed license-file metadata"
            )
        if license_expression_raw is None and license_file is None:
            raise EvidenceError(
                f"Cargo package {name} {version} has no license metadata"
            )
        license_expression_normalized = (
            _normalize_spdx_expression(
                license_expression_raw,
                f"Cargo package {name} {version}",
            )
            if license_expression_raw is not None
            else None
        )
        records.append(
            {
                "bom-ref": reference,
                "name": name,
                "version": version,
                "license_expression_raw": license_expression_raw,
                "license_expression_normalized": license_expression_normalized,
                "license_file_declared": isinstance(license_file, str),
                "source": source_label,
                "purl": purl,
                "internal": source is None,
            }
        )
    records.sort(key=lambda item: item["bom-ref"])
    return records, refs


def _lock_checksums() -> dict[tuple[str, str], str]:
    lock = _read_toml(ROOT / "Cargo.lock")
    packages = lock.get("package")
    if not isinstance(packages, list):
        raise EvidenceError("Cargo.lock has no package array")
    checksums: dict[tuple[str, str], str] = {}
    for package in packages:
        if not isinstance(package, dict):
            raise EvidenceError("Cargo.lock contains a non-table package")
        name = package.get("name")
        version = package.get("version")
        checksum = package.get("checksum")
        if (
            isinstance(name, str)
            and isinstance(version, str)
            and isinstance(checksum, str)
        ):
            checksums[(name, version)] = checksum
    return checksums


def _typescript_component() -> dict[str, Any]:
    manifest = _read_json(ROOT / "package.json")
    dependencies = manifest.get("devDependencies")
    version = dependencies.get("typescript") if isinstance(dependencies, dict) else None
    if not isinstance(version, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+", version
    ):
        raise EvidenceError("package.json must pin one exact TypeScript version")
    lock = (ROOT / "bun.lock").read_text(encoding="utf-8")
    match = re.search(
        rf'"typescript": \["typescript@{re.escape(version)}".*?"(sha512-[A-Za-z0-9+/=]+)"\]',
        lock,
    )
    if match is None:
        raise EvidenceError(
            "bun.lock does not bind the exact TypeScript package integrity"
        )
    algorithm, encoded = match.group(1).split("-", 1)
    cyclonedx_algorithm = SRI_TO_CYCLONEDX.get(algorithm)
    if cyclonedx_algorithm is None:
        raise EvidenceError(f"unsupported TypeScript SRI algorithm {algorithm!r}")
    digest = base64.b64decode(encoded, validate=True).hex()
    license_expression_raw = "Apache-2.0"
    return {
        "bom-ref": _purl("npm", "typescript", version),
        "name": "typescript",
        "version": version,
        "license_expression_raw": license_expression_raw,
        "license_expression_normalized": _normalize_spdx_expression(
            license_expression_raw, "TypeScript"
        ),
        "hash": {"alg": cyclonedx_algorithm, "content": digest},
        "scope": "development",
    }


def _workspace_inventory(
    metadata: dict[str, Any], refs: dict[str, str]
) -> list[dict[str, Any]]:
    root = str(ROOT)
    result: list[dict[str, Any]] = []
    packages = metadata.get("packages")
    if not isinstance(packages, list):
        raise EvidenceError("cargo metadata packages are malformed")
    for package in packages:
        if not isinstance(package, dict) or package.get("source") is not None:
            continue
        identifier = package.get("id")
        if not isinstance(identifier, str) or identifier not in refs:
            raise EvidenceError("workspace package identity is malformed")
        manifest = package.get("manifest_path")
        if not isinstance(manifest, str) or not manifest.startswith(f"{root}/"):
            raise EvidenceError("workspace manifest path escapes the repository")
        dependencies = package.get("dependencies")
        features = package.get("features")
        if not isinstance(dependencies, list) or not isinstance(features, dict):
            raise EvidenceError(
                "workspace package dependency or feature metadata is malformed"
            )
        direct: list[dict[str, Any]] = []
        for dependency in dependencies:
            if not isinstance(dependency, dict):
                raise EvidenceError("workspace dependency metadata is malformed")
            direct.append(
                {
                    "name": dependency.get("name"),
                    "requirement": dependency.get("req"),
                    "kind": dependency.get("kind") or "normal",
                    "optional": dependency.get("optional"),
                    "default_features": dependency.get("uses_default_features"),
                    "features": sorted(dependency.get("features") or []),
                    "target": dependency.get("target"),
                }
            )
        direct.sort(key=lambda item: (item["name"], item["kind"], item["target"] or ""))
        normalized_features: dict[str, list[str]] = {}
        for name, members in sorted(features.items()):
            if not isinstance(name, str) or not isinstance(members, list):
                raise EvidenceError("workspace feature metadata is malformed")
            normalized_features[name] = sorted(str(member) for member in members)
        result.append(
            {
                "name": package.get("name"),
                "version": package.get("version"),
                "bom_ref": refs[identifier],
                "manifest": manifest[len(root) + 1 :],
                "features": normalized_features,
                "direct_dependencies": direct,
            }
        )
    result.sort(key=lambda item: item["name"])
    return result


def _path_label(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _require_regular_generator_candidate(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as error:
        raise EvidenceError(
            f"cannot inspect generator candidate {_path_label(path)}: {error}"
        ) from error
    if stat.S_ISLNK(mode):
        raise EvidenceError(f"generator candidate is a link: {_path_label(path)}")
    if not stat.S_ISREG(mode):
        raise EvidenceError(
            f"generator candidate is not a regular file: {_path_label(path)}"
        )


def _generator_script_candidates(directory: Path) -> list[Path]:
    try:
        directory_mode = directory.lstat().st_mode
    except OSError as error:
        raise EvidenceError(
            f"cannot inspect generator directory {_path_label(directory)}: {error}"
        ) from error
    if stat.S_ISLNK(directory_mode) or not stat.S_ISDIR(directory_mode):
        raise EvidenceError(
            f"generator directory is linked or special: {_path_label(directory)}"
        )
    candidates = sorted(directory.glob("*.py"))
    for candidate in candidates:
        _require_regular_generator_candidate(candidate)
    return candidates


def _generator_inventory(tracked: set[str]) -> list[dict[str, Any]]:
    script_candidates = _generator_script_candidates(ROOT / "scripts")
    mutating_scripts: set[str] = set()
    for item in script_candidates:
        try:
            text = item.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise EvidenceError(
                f"cannot read generator candidate {_path_label(item)}: {error}"
            ) from error
        if any(
            marker in text
            for marker in ('"--write"', '"--output"', '"--output-dir"', '"--freeze"')
        ):
            mutating_scripts.add(item.relative_to(ROOT).as_posix())
    discovered = {
        path
        for path in (
            tracked
            | mutating_scripts
            | {
                item.relative_to(ROOT).as_posix()
                for item in script_candidates
                if item.name.startswith("generate_")
            }
        )
        if re.fullmatch(r"scripts/generate_.*\.py", path)
        or path in mutating_scripts
        or path
        in {
            "ncp-core/src/bin/gen-schemas.rs",
            "ncp-ts/scripts/build-release.mjs",
            "ncp-ts/scripts/sync-bindings.mjs",
            "scripts/gen_diagrams.py",
            "scripts/plot_perf.py",
        }
    }
    expected = set(GENERATOR_OUTPUTS)
    if discovered != expected:
        missing = sorted(expected - discovered)
        unreviewed = sorted(discovered - expected)
        raise EvidenceError(
            f"code-generator inventory drifted; missing={missing!r}, unreviewed={unreviewed!r}"
        )
    return [
        {
            "path": path,
            "sha256": _sha256(ROOT / path),
            "outputs": GENERATOR_OUTPUTS[path],
        }
        for path in sorted(expected)
    ]


def _asset_class(path: str) -> str:
    if path.startswith("conformance/baseline/"):
        return "frozen-release-baseline"
    if path.startswith("conformance/"):
        return "conformance-fixture"
    if path.startswith("schemas/"):
        return "generated-json-schema"
    if path.startswith("deploy/"):
        return "deployment-profile-or-policy"
    if path.startswith("assets/") or path.startswith("docs/plots/data/"):
        return "documentation-asset-or-measurement-input"
    if "/testdata/" in path:
        return "package-test-fixture"
    raise EvidenceError(f"asset classifier has no disposition for {path}")


def _asset_inventory(tracked: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in tracked:
        if path.startswith("evidence/supply-chain/"):
            continue
        if not (path.startswith(ASSET_PREFIXES) or "/testdata/" in path):
            continue
        absolute = ROOT / path
        records.append(
            {
                "path": path,
                "classification": _asset_class(path),
                "size_bytes": absolute.stat().st_size,
                "sha256": _sha256(absolute),
                "license_disposition": "MIT OR Apache-2.0 repository material",
                "provenance": "tracked repository source or reproducible generated output",
            }
        )
    return records


def _workflow_actions(tracked: list[str]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for path in tracked:
        if not path.startswith(".github/workflows/") or not path.endswith(
            (".yml", ".yaml")
        ):
            continue
        text = (ROOT / path).read_text(encoding="utf-8")
        for match in re.finditer(r"(?m)^\s*-?\s*uses:\s*([^\s#]+)", text):
            reference = match.group(1)
            if reference.startswith("./"):
                continue
            if "@" not in reference:
                raise EvidenceError(
                    f"workflow action has no immutable ref: {reference}"
                )
            action, revision = reference.rsplit("@", 1)
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise EvidenceError(
                    f"workflow action is not pinned to a 40-hex commit: {reference}"
                )
            actions.append({"workflow": path, "action": action, "revision": revision})
    actions.sort(key=lambda item: (item["workflow"], item["action"], item["revision"]))
    return actions


def _exact_requirement_file(path: Path) -> list[str]:
    requirements = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for requirement in requirements:
        if "==" not in requirement:
            raise EvidenceError(
                f"{path.relative_to(ROOT)} contains an unpinned requirement {requirement!r}"
            )
    return requirements


def _hashed_requirement_file(path: Path) -> list[dict[str, Any]]:
    logical: list[str] = []
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].strip()
            continue
        logical.append(pending)
        pending = ""
    if pending:
        raise EvidenceError(f"{path.relative_to(ROOT)} ends in a continuation")
    records: list[dict[str, Any]] = []
    for requirement in logical:
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+==[0-9]+\.[0-9]+\.[0-9]+)"
            r"((?:\s+--hash=sha256:[0-9a-f]{64})+)",
            requirement,
        )
        if match is None:
            raise EvidenceError(
                f"{path.relative_to(ROOT)} contains an unpinned or unhashed requirement"
            )
        hashes = re.findall(r"--hash=(sha256:[0-9a-f]{64})", match.group(2))
        if hashes != sorted(set(hashes)):
            raise EvidenceError(
                f"{path.relative_to(ROOT)} requirement hashes are unsorted or duplicated"
            )
        records.append({"requirement": match.group(1), "hashes": hashes})
    if not records:
        raise EvidenceError(f"{path.relative_to(ROOT)} has no hashed requirements")
    return records


def _reviewed_advisory_ignore_set() -> set[str]:
    deny = _read_toml(ROOT / "deny.toml")
    advisories = deny.get("advisories")
    if not isinstance(advisories, dict):
        raise EvidenceError("deny.toml advisory policy is malformed")
    ignored_value = advisories.get("ignore")
    if not isinstance(ignored_value, list) or not all(
        isinstance(item, str) and item for item in ignored_value
    ):
        raise EvidenceError("deny.toml advisory ignore set is malformed")
    ignored = set(ignored_value)
    if len(ignored) != len(ignored_value):
        raise EvidenceError("deny.toml advisory ignore set contains duplicates")
    if ignored != REVIEWED_ADVISORY_IDS:
        raise EvidenceError(
            "deny.toml advisory dispositions differ from reviewed controls"
        )
    return ignored


def _validate_reviewed_advisory_findings(findings: object) -> None:
    if not isinstance(findings, list):
        raise EvidenceError("advisory findings must be an array")
    normalized_findings: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
    expected_fields = {
        "id",
        "category",
        "package",
        "version",
        "aliases",
        "policy_disposition",
    }
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != expected_fields:
            raise EvidenceError("advisory finding has an unexpected shape")
        identifier = finding.get("id")
        category = finding.get("category")
        package = finding.get("package")
        version = finding.get("version")
        aliases_value = finding.get("aliases")
        if not all(
            isinstance(value, str) and value
            for value in (identifier, category, package, version)
        ):
            raise EvidenceError("advisory finding identity is malformed")
        if not isinstance(aliases_value, list) or not all(
            isinstance(alias, str) and alias for alias in aliases_value
        ):
            raise EvidenceError("advisory finding aliases are malformed")
        if aliases_value != sorted(set(aliases_value)):
            raise EvidenceError(
                f"advisory finding aliases are not sorted and unique for {identifier}"
            )
        key = (identifier, category, package, version, tuple(aliases_value))
        disposition = REVIEWED_ADVISORY_FINDINGS.get(key)
        if disposition is None:
            raise EvidenceError(
                f"advisory report contains an undispositioned finding {key!r}"
            )
        if finding.get("policy_disposition") != disposition:
            raise EvidenceError(f"advisory disposition drifted for {key!r}")
        if key in normalized_findings:
            raise EvidenceError("advisory report contains duplicate findings")
        normalized_findings.add(key)
    if normalized_findings != set(REVIEWED_ADVISORY_FINDINGS):
        raise EvidenceError(
            "advisory report differs from the exact reviewed finding records"
        )


def _cargo_advisories() -> dict[str, Any]:
    command = [
        "cargo",
        "deny",
        "-L",
        "debug",
        "--locked",
        "--offline",
        "--all-features",
        "--format",
        "json",
        "check",
        "advisories",
        "--disable-fetch",
        "--audit-compatible-output",
    ]
    try:
        process = subprocess.run(
            command,
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise EvidenceError(f"cannot execute cargo-deny: {error}") from error
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", "replace").strip()
        raise EvidenceError(f"{' '.join(command)} failed: {detail}")

    reports: list[dict[str, Any]] = []
    for line_number, line in enumerate(process.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        value = _strict_json(line, f"cargo-deny advisory output line {line_number}")
        if isinstance(value, dict) and isinstance(value.get("lockfile"), dict):
            reports.append(value)
    if len(reports) != 1:
        raise EvidenceError(
            f"cargo-deny returned {len(reports)} advisory database reports; expected exactly one"
        )
    report = reports[0]

    debug = process.stderr.decode("utf-8", "replace")
    database_paths = set(re.findall(r"Opening advisory database at '([^']+)'", debug))
    if len(database_paths) != 1:
        raise EvidenceError(
            "cargo-deny did not disclose exactly one opened advisory database"
        )
    database_path = Path(next(iter(database_paths))).resolve()
    if not database_path.is_dir():
        raise EvidenceError("cargo-deny advisory database path is not a directory")
    database_revision = (
        _run(
            ["git", "-C", str(database_path), "rev-parse", "--verify", "HEAD^{commit}"]
        )
        .decode("ascii", "strict")
        .strip()
    )
    if SOURCE_REVISION.fullmatch(database_revision) is None:
        raise EvidenceError("RustSec advisory database revision is malformed")
    database_status = _run(
        [
            "git",
            "-C",
            str(database_path),
            "status",
            "--porcelain",
        ]
    )
    if database_status:
        raise EvidenceError("RustSec advisory database is not clean")
    database_urls = (
        _run(
            [
                "git",
                "-C",
                str(database_path),
                "config",
                "--get-all",
                "remote.origin.url",
            ]
        )
        .decode("utf-8", "strict")
        .splitlines()
    )
    if len(database_urls) != 1 or not database_urls[0]:
        raise EvidenceError(
            "RustSec advisory database must configure exactly one origin URL"
        )
    database_url = database_urls[0]
    if database_url.rstrip("/").removesuffix(".git") != (
        "https://github.com/RustSec/advisory-db"
    ):
        raise EvidenceError(
            f"unexpected RustSec advisory database URL {database_url!r}"
        )
    cargo_deny_version = (
        _run(["cargo", "deny", "--version"]).decode("utf-8", "strict").strip()
    )
    if re.fullmatch(r"cargo-deny [0-9]+\.[0-9]+\.[0-9]+", cargo_deny_version) is None:
        raise EvidenceError("cargo-deny version output is malformed")

    findings: list[dict[str, Any]] = []

    def retain(entry: Any, category: str) -> None:
        if not isinstance(entry, dict):
            raise EvidenceError("cargo-deny advisory finding is malformed")
        advisory = entry.get("advisory")
        package = entry.get("package")
        if not isinstance(advisory, dict) or not isinstance(package, dict):
            raise EvidenceError("cargo-deny finding lacks advisory or package identity")
        identifier = advisory.get("id")
        if not isinstance(identifier, str):
            raise EvidenceError("cargo-deny finding lacks an advisory ID")
        aliases_value = advisory.get("aliases")
        if aliases_value is None:
            aliases_value = []
        if not isinstance(aliases_value, list) or not all(
            isinstance(alias, str) and alias for alias in aliases_value
        ):
            raise EvidenceError("cargo-deny advisory aliases are malformed")
        aliases = tuple(sorted(set(aliases_value)))
        if len(aliases) != len(aliases_value):
            raise EvidenceError("cargo-deny advisory aliases contain duplicates")
        package_name = package.get("name")
        package_version = package.get("version")
        if not all(
            isinstance(value, str) and value
            for value in (package_name, package_version)
        ):
            raise EvidenceError("cargo-deny package identity is malformed")
        key = (identifier, category, package_name, package_version, aliases)
        if key not in REVIEWED_ADVISORY_FINDINGS:
            raise EvidenceError(
                "cargo-deny reported an undispositioned finding "
                f"{key!r}; review its exact package/version/aliases before regenerating evidence"
            )
        findings.append(
            {
                "id": identifier,
                "category": category,
                "package": package_name,
                "version": package_version,
                "aliases": list(aliases),
                "policy_disposition": REVIEWED_ADVISORY_FINDINGS[key],
            }
        )

    vulnerabilities = report.get("vulnerabilities")
    if vulnerabilities is None:
        vulnerabilities = []
    if not isinstance(vulnerabilities, list):
        raise EvidenceError("cargo-deny vulnerability report is malformed")
    for entry in vulnerabilities:
        retain(entry, "vulnerability")
    warnings = report.get("warnings")
    if warnings is None:
        warnings = {}
    if not isinstance(warnings, dict):
        raise EvidenceError("cargo-deny warning report is malformed")
    for category, entries in sorted(warnings.items()):
        if not isinstance(entries, list):
            raise EvidenceError("cargo-deny warning category is malformed")
        for entry in entries:
            retain(entry, category)
    findings.sort(key=lambda item: (item["id"], item["package"], item["version"]))
    _validate_reviewed_advisory_findings(findings)
    dependency_count = (report.get("lockfile") or {}).get("dependency-count")
    if not isinstance(dependency_count, int) or dependency_count < 0:
        raise EvidenceError("cargo-deny dependency count is malformed")
    return {
        "dependency_count": dependency_count,
        "findings": findings,
        "scanner": cargo_deny_version,
        "advisory_database": {
            "url": "https://github.com/RustSec/advisory-db",
            "revision": database_revision,
        },
    }


def _build_outputs(
    *,
    tracked_files_manifest: Path | None = None,
) -> dict[str, dict[str, Any]]:
    metadata = _cargo_metadata()
    cargo, refs = _cargo_packages(metadata)
    checksums = _lock_checksums()
    tracked = _tracked_files(tracked_files_manifest)
    tracked_set = set(tracked)
    workspace = _workspace_inventory(metadata, refs)
    root_manifest = _read_json(ROOT / "package.json")
    python_manifest = _read_toml(ROOT / "ncp-python" / "pyproject.toml")
    contract = _read_json(ROOT / "contract" / "manifest.v1.json")

    workspace_package = workspace[0] if workspace else None
    if workspace_package is None:
        raise EvidenceError("Cargo workspace inventory is empty")
    version = workspace_package["version"]
    if any(package["version"] != version for package in workspace):
        raise EvidenceError("workspace package versions are incoherent")
    if root_manifest.get("version") != version:
        raise EvidenceError("npm and Cargo package versions are incoherent")
    npm_name = root_manifest.get("name")
    npm_license_raw = root_manifest.get("license")
    if not isinstance(npm_name, str) or not npm_name:
        raise EvidenceError("npm workspace package identity is malformed")
    npm_license_normalized = _normalize_spdx_expression(
        npm_license_raw, "npm workspace package"
    )
    project = python_manifest.get("project")
    if not isinstance(project, dict) or project.get("dependencies") not in (None, []):
        raise EvidenceError(
            "Python runtime dependency surface changed and needs review"
        )
    python_name = project.get("name")
    if not isinstance(python_name, str) or not python_name:
        raise EvidenceError("Python distribution identity is malformed")
    python_license = project.get("license")
    if (
        not isinstance(python_license, dict)
        or set(python_license) != {"text"}
        or not isinstance(python_license.get("text"), str)
    ):
        raise EvidenceError(
            "Python distribution license must be one reviewed SPDX text expression"
        )
    python_license_raw = python_license["text"]
    python_license_normalized = _normalize_spdx_expression(
        python_license_raw, "Python distribution"
    )

    typescript = _typescript_component()
    npm_ref = _internal_bom_ref("npm", npm_name, version)
    python_ref = _internal_bom_ref("python", python_name, version)
    root_ref = _internal_bom_ref("root", "NCP", version)
    ncp_python_refs = [
        package["bom-ref"]
        for package in cargo
        if package["internal"] and package["name"] == "ncp-python"
    ]
    if len(ncp_python_refs) != 1:
        raise EvidenceError(
            "Python distribution requires exactly one ncp-python workspace component"
        )
    ncp_python_ref = ncp_python_refs[0]

    components: list[dict[str, Any]] = []
    for package in cargo:
        component: dict[str, Any] = {
            "type": "library",
            "bom-ref": package["bom-ref"],
            "name": package["name"],
            "version": package["version"],
            "licenses": [{"expression": package["license_expression_normalized"]}]
            if package["license_expression_normalized"]
            else [{"license": {"name": "declared license file"}}],
            "properties": [{"name": "ncp:cargo-source", "value": package["source"]}],
        }
        if package["purl"] is not None:
            component["purl"] = package["purl"]
        checksum = checksums.get((package["name"], package["version"]))
        if package["internal"]:
            if checksum is not None:
                raise EvidenceError(
                    f"workspace Cargo package unexpectedly has a registry checksum: "
                    f"{package['name']} {package['version']}"
                )
        else:
            if (
                not isinstance(checksum, str)
                or re.fullmatch(r"[0-9a-f]{64}", checksum) is None
            ):
                raise EvidenceError(
                    f"registry Cargo package has no exact lock checksum: "
                    f"{package['name']} {package['version']}"
                )
            component["hashes"] = [{"alg": "SHA-256", "content": checksum}]
        components.append(component)
    components.extend(
        [
            {
                "type": "library",
                "bom-ref": npm_ref,
                "name": npm_name,
                "version": version,
                "licenses": [{"expression": npm_license_normalized}],
            },
            {
                "type": "library",
                "bom-ref": python_ref,
                "name": python_name,
                "version": version,
                "licenses": [{"expression": python_license_normalized}],
            },
            {
                "type": "library",
                "bom-ref": typescript["bom-ref"],
                "name": typescript["name"],
                "version": typescript["version"],
                "scope": "excluded",
                "licenses": [
                    {"expression": typescript["license_expression_normalized"]}
                ],
                "hashes": [typescript["hash"]],
                "purl": typescript["bom-ref"],
            },
        ]
    )
    components.sort(key=lambda item: item["bom-ref"])

    dependencies: list[dict[str, Any]] = []
    resolve = metadata.get("resolve")
    nodes = resolve.get("nodes") if isinstance(resolve, dict) else None
    if not isinstance(nodes, list):
        raise EvidenceError("cargo metadata resolve graph is malformed")
    for node in nodes:
        if not isinstance(node, dict) or node.get("id") not in refs:
            raise EvidenceError("cargo resolve node has unknown identity")
        dependency_refs: list[str] = []
        node_dependencies = node.get("deps")
        if not isinstance(node_dependencies, list):
            raise EvidenceError("cargo resolve node dependency array is malformed")
        for dependency in node_dependencies:
            if not isinstance(dependency, dict) or dependency.get("pkg") not in refs:
                raise EvidenceError("cargo resolve edge has unknown identity")
            dependency_refs.append(refs[dependency["pkg"]])
        dependencies.append(
            {"ref": refs[node["id"]], "dependsOn": sorted(set(dependency_refs))}
        )
    dependencies.extend(
        [
            {"ref": npm_ref, "dependsOn": [typescript["bom-ref"]]},
            {"ref": python_ref, "dependsOn": [ncp_python_ref]},
            {"ref": typescript["bom-ref"], "dependsOn": []},
            {
                "ref": root_ref,
                "dependsOn": sorted(
                    [
                        *[package["bom_ref"] for package in workspace],
                        npm_ref,
                        python_ref,
                    ]
                ),
            },
        ]
    )
    dependencies.sort(key=lambda item: item["ref"])

    _reviewed_advisory_ignore_set()
    advisory_scan = _cargo_advisories()

    license_records = [
        {
            "bom_ref": package["bom-ref"],
            "license_expression_raw": package["license_expression_raw"],
            "license_expression_normalized": package["license_expression_normalized"],
            "license_file_declared": package["license_file_declared"],
        }
        for package in cargo
    ]
    license_records.extend(
        [
            {
                "bom_ref": npm_ref,
                "license_expression_raw": npm_license_raw,
                "license_expression_normalized": npm_license_normalized,
                "license_file_declared": True,
            },
            {
                "bom_ref": python_ref,
                "license_expression_raw": python_license_raw,
                "license_expression_normalized": python_license_normalized,
                "license_file_declared": True,
            },
            {
                "bom_ref": typescript["bom-ref"],
                "license_expression_raw": typescript["license_expression_raw"],
                "license_expression_normalized": typescript[
                    "license_expression_normalized"
                ],
                "license_file_declared": False,
            },
        ]
    )
    license_records.sort(key=lambda item: item["bom_ref"])
    expression_counts = collections.Counter(
        str(item["license_expression_normalized"] or "LICENSE_FILE")
        for item in license_records
    )

    inventory = {
        "schema": OUTPUTS["inventory.v1.json"],
        "candidate_version": version,
        "release_authorized": False,
        "locked_inputs": {
            path: _sha256(ROOT / path)
            for path in sorted(
                {
                    "Cargo.lock",
                    "Cargo.toml",
                    "buf.gen.yaml",
                    "buf.yaml",
                    "bun.lock",
                    "deny.toml",
                    "ncp-python/pyproject.toml",
                    "ncp-ts/package.json",
                    "package.json",
                    "scripts/requirements-candidate-build-linux-x86_64.txt",
                    "scripts/requirements-plot.txt",
                    *[package["manifest"] for package in workspace],
                }
            )
        },
        "workspace_packages": workspace,
        "python_surface": {
            "manifest": "ncp-python/pyproject.toml",
            "build_requirements": (python_manifest.get("build-system") or {}).get(
                "requires"
            ),
            "runtime_dependencies": [],
        },
        "npm_surface": {
            "manifest": "package.json",
            "runtime_dependencies": [],
            "development_dependencies": [
                {"name": "typescript", "version": typescript["version"]}
            ],
        },
        "toolchain_and_build_dependencies": {
            "rust_floor": "1.88.0",
            "python_build_backend": (python_manifest.get("build-system") or {}).get(
                "build-backend"
            ),
            "python_build_requirements": (
                python_manifest.get("build-system") or {}
            ).get("requires"),
            "candidate_builder_pins": _hashed_requirement_file(
                ROOT / "scripts" / "requirements-candidate-build-linux-x86_64.txt"
            ),
            "plot_requirements": _exact_requirement_file(
                ROOT / "scripts" / "requirements-plot.txt"
            ),
            "github_actions": _workflow_actions(tracked),
            "buf_remote_plugins": "validated by scripts/check_buf_generator_pins.py",
        },
        "code_generators": _generator_inventory(tracked_set),
        "assets_datasets_and_fixtures": _asset_inventory(tracked),
    }
    sbom_identity = {
        "candidate_version": version,
        "normative_contract_digest_sha256": contract["contract_digest_sha256"],
        "components": components,
        "dependencies": dependencies,
    }
    sbom_uuid = uuid.uuid5(
        NCP_SBOM_NAMESPACE,
        json.dumps(sbom_identity, sort_keys=True, separators=(",", ":")),
    )
    sbom = {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{sbom_uuid}",
        "version": 1,
        "metadata": {
            "authors": [{"name": "Sepehr Mahmoudian"}],
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": "NCP",
                "version": version,
                "licenses": [{"expression": npm_license_normalized}],
                "properties": [
                    {
                        "name": "ncp:normative-contract-digest-sha256",
                        "value": contract["contract_digest_sha256"],
                    },
                    {"name": "ncp:release-authorized", "value": "false"},
                ],
            },
        },
        "components": components,
        "dependencies": dependencies,
    }
    license_report = {
        "schema": OUTPUTS["license-report.v1.json"],
        "candidate_version": version,
        "policy": {
            "source": "deny.toml",
            "sha256": _sha256(ROOT / "deny.toml"),
            "cargo_default_deny": True,
            "repository_license_files": {
                name: _sha256(ROOT / name) for name in ("LICENSE-MIT", "LICENSE-APACHE")
            },
        },
        "package_count": len(license_records),
        "license_expression_counts": dict(sorted(expression_counts.items())),
        "packages": license_records,
        "qualification_command": (
            "cargo deny --locked --offline --all-features check licenses"
        ),
    }
    vulnerability_report = {
        "schema": OUTPUTS["vulnerability-report.v1.json"],
        "candidate_version": version,
        "lockfile_sha256": _sha256(ROOT / "Cargo.lock"),
        "scanner": advisory_scan["scanner"],
        "advisory_database": advisory_scan["advisory_database"],
        "scan_command": (
            "cargo deny -L debug --locked --offline --all-features --format json "
            "check advisories --disable-fetch --audit-compatible-output"
        ),
        "dependency_count": advisory_scan["dependency_count"],
        "policy_result": "PASS_WITH_EXPLICIT_REVIEWED_DISPOSITIONS",
        "stable_publication_blocked": True,
        "stable_publication_blocker": (
            "RUSTSEC-2026-0041 remains in the resolved graph through Zenoh 1.9.0; "
            "the disabled feature guard bounds local exposure but does not waive the "
            "stable-publication hold."
        ),
        "findings": advisory_scan["findings"],
        "non_rust_runtime_dependencies": {
            "npm": 0,
            "python": 0,
            "finding": "No npm or Python runtime dependency graph exists to scan.",
        },
        "exposure_guard": {
            "path": "scripts/check_dependency_exposure.py",
            "sha256": _sha256(ROOT / "scripts" / "check_dependency_exposure.py"),
        },
    }
    provenance_policy = {
        "schema": OUTPUTS["provenance-policy.v1.json"],
        "candidate_version": version,
        "release_authorized": False,
        "source_materials": {
            "Cargo.lock": _sha256(ROOT / "Cargo.lock"),
            "bun.lock": _sha256(ROOT / "bun.lock"),
            "contract/manifest.v1.json": _sha256(
                ROOT / "contract" / "manifest.v1.json"
            ),
            "conformance/manifest.v1.json": _sha256(
                ROOT / "conformance" / "manifest.v1.json"
            ),
        },
        "candidate_dossier_requirements": [
            "build from one exact full Git commit with a clean archived source tree",
            "record and verifier-bind every exact identity injection used to create disposable package-source derivatives",
            "build all five Rust archives, the abi3 wheel, Python sdist, and both npm tarballs; smoke every locally installable surface",
            "record SHA-256 checksums for every package, SBOM, license report, and scan report",
            "bind the normative contract and conformance corpus digests",
            "retain package-install and behavioral-conformance results",
            "attest package subjects and the CycloneDX SBOM in the hosted build",
        ],
        "publication_preconditions_not_satisfied_locally": [
            "independent clean-room reproduction",
            "registry namespace ownership",
            "authorized release policy",
            "independently verified signatures and revocation path",
        ],
        "claim_boundary": (
            "These deterministic local files are candidate evidence. They are not a "
            "signature, provenance attestation, registry publication, or release approval."
        ),
    }
    return {
        "inventory.v1.json": inventory,
        "sbom.cdx.json": sbom,
        "license-report.v1.json": license_report,
        "vulnerability-report.v1.json": vulnerability_report,
        "provenance-policy.v1.json": provenance_policy,
    }


def _encoded(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _component_properties(component: dict[str, Any]) -> dict[str, str]:
    value = component.get("properties")
    if value is None:
        return {}
    if not isinstance(value, list):
        raise EvidenceError("SBOM component properties must be an array")
    properties: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "value"}:
            raise EvidenceError("SBOM component property has an unexpected shape")
        name = item.get("name")
        content = item.get("value")
        if not isinstance(name, str) or not name or not isinstance(content, str):
            raise EvidenceError("SBOM component property is malformed")
        if name in properties:
            raise EvidenceError(f"SBOM component property is duplicated: {name}")
        properties[name] = content
    return properties


def _validate_component_identity(component: dict[str, Any]) -> str:
    reference = component.get("bom-ref")
    name = component.get("name")
    version = component.get("version")
    if not all(
        isinstance(value, str) and value for value in (reference, name, version)
    ):
        raise EvidenceError("SBOM component identity is malformed")
    if component.get("type") != "library":
        raise EvidenceError("SBOM inventory components must be libraries")
    properties = _component_properties(component)
    if reference.startswith(INTERNAL_BOM_REF_PREFIX):
        remainder = reference.removeprefix(INTERNAL_BOM_REF_PREFIX)
        if ":" not in remainder:
            raise EvidenceError("internal SBOM reference has no surface")
        surface, _encoded_identity = remainder.split(":", 1)
        if surface not in INTERNAL_BOM_REF_SURFACES - {"root"}:
            raise EvidenceError(
                f"internal SBOM component surface is invalid: {surface}"
            )
        if reference != _internal_bom_ref(surface, name, version):
            raise EvidenceError("internal SBOM component reference is not canonical")
        if "purl" in component:
            raise EvidenceError(
                "internal SBOM components must not claim registry PURLs"
            )
        if surface == "cargo":
            if properties.get("ncp:cargo-source") != "workspace":
                raise EvidenceError("internal Cargo component source is not workspace")
        elif "ncp:cargo-source" in properties:
            raise EvidenceError("non-Cargo internal component claims a Cargo source")
        return surface

    purl = component.get("purl")
    if not isinstance(purl, str) or purl != reference:
        raise EvidenceError("external SBOM component PURL identity drifted")
    if purl.startswith("pkg:cargo/"):
        if purl != _purl("cargo", name, version):
            raise EvidenceError("registry Cargo PURL is not canonical")
        if properties.get("ncp:cargo-source") != CRATES_IO_SOURCE:
            raise EvidenceError("registry Cargo component source is not crates.io")
        return "registry-cargo"
    if purl.startswith("pkg:npm/"):
        if name != "typescript" or purl != _purl("npm", name, version):
            raise EvidenceError(
                "TypeScript is the only reviewed external npm component"
            )
        if component.get("scope") != "excluded":
            raise EvidenceError("TypeScript must remain excluded from runtime scope")
        return "typescript"
    raise EvidenceError(f"unreviewed registry PURL surface: {purl!r}")


def _validate_component_hashes(component: dict[str, Any], surface: str) -> None:
    value = component.get("hashes")
    if value is None:
        hashes: list[dict[str, Any]] = []
    elif isinstance(value, list) and value:
        hashes = value
    else:
        raise EvidenceError("SBOM component hashes must be a non-empty array")
    for item in hashes:
        if not isinstance(item, dict) or set(item) != {"alg", "content"}:
            raise EvidenceError("SBOM component hash has an unexpected shape")
        algorithm = item.get("alg")
        content = item.get("content")
        if algorithm not in CYCLONEDX_HASH_ALGORITHMS:
            raise EvidenceError("SBOM contains a non-CycloneDX hash algorithm")
        expected_length = CYCLONEDX_HASH_HEX_LENGTHS[str(algorithm)]
        if (
            not isinstance(content, str)
            or re.fullmatch(rf"[0-9a-f]{{{expected_length}}}", content) is None
        ):
            raise EvidenceError("SBOM contains a malformed hash digest")
    if surface == "registry-cargo":
        if len(hashes) != 1 or hashes[0].get("alg") != "SHA-256":
            raise EvidenceError("registry Cargo component lacks one lockfile SHA-256")
    elif surface == "typescript":
        if len(hashes) != 1 or hashes[0].get("alg") != "SHA-512":
            raise EvidenceError("TypeScript component lacks one lockfile SHA-512")
    elif hashes:
        raise EvidenceError("internal workspace component has an unreviewed hash claim")


def _validate_sbom_graph(
    sbom: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, list[str]],
]:
    components_value = sbom.get("components")
    if not isinstance(components_value, list) or len(components_value) < 3:
        raise EvidenceError("SBOM component inventory is unexpectedly small")
    if not all(isinstance(component, dict) for component in components_value):
        raise EvidenceError("SBOM component inventory contains a non-object")
    components: list[dict[str, Any]] = components_value
    component_refs = [component.get("bom-ref") for component in components]
    if not all(
        isinstance(reference, str) and reference for reference in component_refs
    ):
        raise EvidenceError("SBOM contains a malformed component reference")
    if component_refs != sorted(component_refs):
        raise EvidenceError("SBOM components are not deterministically ordered")
    if len(component_refs) != len(set(component_refs)):
        raise EvidenceError("SBOM contains duplicate component references")

    metadata = sbom.get("metadata")
    root_component = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(root_component, dict):
        raise EvidenceError("SBOM metadata root component is malformed")
    root_ref = root_component.get("bom-ref")
    if not isinstance(root_ref, str) or not root_ref:
        raise EvidenceError("SBOM metadata root reference is malformed")
    if root_ref in set(component_refs):
        raise EvidenceError("SBOM metadata root duplicates an inventory component")
    all_refs = {*component_refs, root_ref}

    dependencies_value = sbom.get("dependencies")
    if not isinstance(dependencies_value, list):
        raise EvidenceError("SBOM dependency graph is missing")
    dependency_refs: list[str] = []
    graph: dict[str, list[str]] = {}
    for node in dependencies_value:
        if not isinstance(node, dict) or set(node) != {"ref", "dependsOn"}:
            raise EvidenceError("SBOM dependency node has an unexpected shape")
        reference = node.get("ref")
        targets = node.get("dependsOn")
        if not isinstance(reference, str) or not reference:
            raise EvidenceError("SBOM dependency node reference is malformed")
        if not isinstance(targets, list) or not all(
            isinstance(target, str) and target for target in targets
        ):
            raise EvidenceError("SBOM dependency target list is malformed")
        if targets != sorted(set(targets)):
            raise EvidenceError("SBOM dependency targets are not sorted and unique")
        if reference in targets:
            raise EvidenceError("SBOM dependency graph contains a self-reference")
        dangling = sorted(set(targets) - all_refs)
        if dangling:
            raise EvidenceError(
                f"SBOM dependency graph has dangling refs: {dangling!r}"
            )
        if reference in graph:
            raise EvidenceError(f"SBOM dependency node is duplicated: {reference}")
        dependency_refs.append(reference)
        graph[reference] = targets
    if dependency_refs != sorted(dependency_refs):
        raise EvidenceError("SBOM dependency nodes are not deterministically ordered")
    if set(graph) != all_refs:
        raise EvidenceError(
            "SBOM dependency node coverage differs from component refs: "
            f"missing={sorted(all_refs - set(graph))!r}, "
            f"extra={sorted(set(graph) - all_refs)!r}"
        )
    reachable = {root_ref}
    pending = [root_ref]
    while pending:
        reference = pending.pop()
        for target in graph[reference]:
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    if reachable != all_refs:
        raise EvidenceError(
            f"SBOM dependency graph has unreachable refs: {sorted(all_refs - reachable)!r}"
        )
    return components, root_component, graph


def _validate_license_report(
    components: list[dict[str, Any]], licenses: dict[str, Any]
) -> None:
    records = licenses.get("packages")
    if not isinstance(records, list):
        raise EvidenceError("license report package records are missing")
    if licenses.get("package_count") != len(components) or len(records) != len(
        components
    ):
        raise EvidenceError("license report and SBOM package counts differ")
    component_by_ref = {component["bom-ref"]: component for component in components}
    expected_fields = {
        "bom_ref",
        "license_expression_raw",
        "license_expression_normalized",
        "license_file_declared",
    }
    record_refs: list[str] = []
    expression_counts: collections.Counter[str] = collections.Counter()
    for record in records:
        if not isinstance(record, dict) or set(record) != expected_fields:
            raise EvidenceError("license report package record has an unexpected shape")
        reference = record.get("bom_ref")
        raw = record.get("license_expression_raw")
        normalized = record.get("license_expression_normalized")
        license_file = record.get("license_file_declared")
        if not isinstance(reference, str) or not reference:
            raise EvidenceError("license report package reference is malformed")
        if not isinstance(license_file, bool):
            raise EvidenceError("license-file declaration must be a boolean")
        if raw is None:
            if normalized is not None or not license_file:
                raise EvidenceError(
                    f"license-only package record is inconsistent for {reference}"
                )
            expected_component_license = [
                {"license": {"name": "declared license file"}}
            ]
            expression_counts["LICENSE_FILE"] += 1
        else:
            expected_normalized = _normalize_spdx_expression(
                raw, f"license report package {reference}"
            )
            if normalized != expected_normalized:
                raise EvidenceError(
                    f"normalized SPDX expression drifted for {reference}"
                )
            expected_component_license = [{"expression": expected_normalized}]
            expression_counts[expected_normalized] += 1
        component = component_by_ref.get(reference)
        if component is None:
            raise EvidenceError(f"license report has an unknown ref: {reference}")
        if component.get("licenses") != expected_component_license:
            raise EvidenceError(
                f"license report and SBOM expression differ for {reference}"
            )
        record_refs.append(reference)
    if record_refs != sorted(record_refs) or len(record_refs) != len(set(record_refs)):
        raise EvidenceError("license package records are not sorted and unique")
    if set(record_refs) != set(component_by_ref):
        raise EvidenceError("license report reference coverage is incomplete")
    if licenses.get("license_expression_counts") != dict(
        sorted(expression_counts.items())
    ):
        raise EvidenceError("license expression counts do not match package records")


def _validate_outputs(outputs: dict[str, dict[str, Any]]) -> None:
    if set(outputs) != set(OUTPUTS):
        raise EvidenceError("generated supply-chain output set is incomplete")
    inventory = outputs["inventory.v1.json"]
    sbom = outputs["sbom.cdx.json"]
    licenses = outputs["license-report.v1.json"]
    vulnerabilities = outputs["vulnerability-report.v1.json"]
    provenance = outputs["provenance-policy.v1.json"]
    if inventory.get("schema") != OUTPUTS["inventory.v1.json"]:
        raise EvidenceError("inventory schema identity drifted")
    if licenses.get("schema") != OUTPUTS["license-report.v1.json"]:
        raise EvidenceError("license-report schema identity drifted")
    if vulnerabilities.get("schema") != OUTPUTS["vulnerability-report.v1.json"]:
        raise EvidenceError("vulnerability-report schema identity drifted")
    if provenance.get("schema") != OUTPUTS["provenance-policy.v1.json"]:
        raise EvidenceError("provenance-policy schema identity drifted")
    if inventory.get("release_authorized") is not False:
        raise EvidenceError("inventory must not authorize a release")
    if provenance.get("release_authorized") is not False:
        raise EvidenceError("provenance policy must not authorize a release")
    version = inventory.get("candidate_version")
    if not isinstance(version, str) or not version:
        raise EvidenceError("inventory candidate version is malformed")
    for report in (licenses, vulnerabilities, provenance):
        if report.get("candidate_version") != version:
            raise EvidenceError("supply-chain candidate versions are incoherent")
    if (
        sbom.get("$schema") != "https://cyclonedx.org/schema/bom-1.6.schema.json"
        or sbom.get("bomFormat") != "CycloneDX"
        or sbom.get("specVersion") != "1.6"
        or sbom.get("version") != 1
    ):
        raise EvidenceError("SBOM identity drifted")

    components, root_component, graph = _validate_sbom_graph(sbom)
    metadata = sbom["metadata"]
    if metadata.get("authors") != [{"name": "Sepehr Mahmoudian"}]:
        raise EvidenceError("SBOM author attribution drifted")
    if (
        root_component.get("type") != "application"
        or root_component.get("name") != "NCP"
        or root_component.get("version") != version
    ):
        raise EvidenceError("SBOM metadata root identity drifted")
    root_ref = _internal_bom_ref("root", "NCP", version)
    if root_component.get("bom-ref") != root_ref or "purl" in root_component:
        raise EvidenceError("SBOM metadata root must use one internal non-PURL ref")
    root_licenses = root_component.get("licenses")
    if (
        not isinstance(root_licenses, list)
        or len(root_licenses) != 1
        or not isinstance(root_licenses[0], dict)
        or set(root_licenses[0]) != {"expression"}
    ):
        raise EvidenceError("SBOM metadata root license is malformed")
    root_license = root_licenses[0].get("expression")
    if root_license != _normalize_spdx_expression(root_license, "SBOM metadata root"):
        raise EvidenceError("SBOM metadata root license is not normalized")

    surfaces: dict[str, list[str]] = collections.defaultdict(list)
    components_by_ref: dict[str, dict[str, Any]] = {}
    for component in components:
        surface = _validate_component_identity(component)
        _validate_component_hashes(component, surface)
        reference = component["bom-ref"]
        surfaces[surface].append(reference)
        components_by_ref[reference] = component
    if len(surfaces["npm"]) != 1 or len(surfaces["python"]) != 1:
        raise EvidenceError(
            "SBOM must contain one npm and one Python workspace surface"
        )
    if not surfaces["cargo"]:
        raise EvidenceError("SBOM has no Cargo workspace components")
    if len(surfaces["typescript"]) != 1:
        raise EvidenceError("SBOM must contain one reviewed TypeScript component")

    ncp_python_refs = [
        reference
        for reference in surfaces["cargo"]
        if components_by_ref[reference].get("name") == "ncp-python"
    ]
    if len(ncp_python_refs) != 1:
        raise EvidenceError("SBOM has no unique ncp-python workspace component")
    python_ref = surfaces["python"][0]
    npm_ref = surfaces["npm"][0]
    typescript_ref = surfaces["typescript"][0]
    if graph[python_ref] != ncp_python_refs:
        raise EvidenceError(
            "Python distribution is not linked to the ncp-python workspace graph"
        )
    if graph[npm_ref] != [typescript_ref]:
        raise EvidenceError("npm workspace is not linked to its TypeScript toolchain")
    expected_root_dependencies = sorted([*surfaces["cargo"], npm_ref, python_ref])
    if graph[root_ref] != expected_root_dependencies:
        raise EvidenceError("SBOM root dependency surface is incomplete")

    workspace_packages = inventory.get("workspace_packages")
    if not isinstance(workspace_packages, list) or not all(
        isinstance(package, dict) for package in workspace_packages
    ):
        raise EvidenceError("inventory workspace packages are malformed")
    workspace_refs = [package.get("bom_ref") for package in workspace_packages]
    if not all(isinstance(reference, str) for reference in workspace_refs):
        raise EvidenceError("inventory workspace package reference is malformed")
    if len(workspace_refs) != len(set(workspace_refs)):
        raise EvidenceError("inventory workspace package references are duplicated")
    if set(workspace_refs) != set(surfaces["cargo"]):
        raise EvidenceError("inventory and SBOM workspace Cargo refs differ")

    _validate_license_report(components, licenses)
    if (
        vulnerabilities.get("policy_result")
        != "PASS_WITH_EXPLICIT_REVIEWED_DISPOSITIONS"
        or vulnerabilities.get("stable_publication_blocked") is not True
        or not isinstance(vulnerabilities.get("stable_publication_blocker"), str)
        or "RUSTSEC-2026-0041" not in vulnerabilities["stable_publication_blocker"]
    ):
        raise EvidenceError(
            "vulnerability report does not retain reviewed findings/publication hold"
        )
    _validate_reviewed_advisory_findings(vulnerabilities.get("findings"))

    serial = sbom.get("serialNumber")
    if not isinstance(serial, str) or not serial.startswith("urn:uuid:"):
        raise EvidenceError("SBOM serial number is malformed")
    try:
        serial_uuid = uuid.UUID(serial.removeprefix("urn:uuid:"))
    except ValueError as error:
        raise EvidenceError("SBOM serial number is not a UUID") from error
    if serial_uuid.version != 5 or serial_uuid.variant != uuid.RFC_4122:
        raise EvidenceError("SBOM serial number is not an RFC-4122 version-5 UUID")
    root_properties = _component_properties(root_component)
    contract_digest = root_properties.get("ncp:normative-contract-digest-sha256")
    if (
        not isinstance(contract_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", contract_digest) is None
    ):
        raise EvidenceError("SBOM normative contract digest is malformed")
    if root_properties.get("ncp:release-authorized") != "false":
        raise EvidenceError("SBOM metadata root must not authorize a release")
    sbom_identity = {
        "candidate_version": version,
        "normative_contract_digest_sha256": contract_digest,
        "components": components,
        "dependencies": sbom["dependencies"],
    }
    expected_uuid = uuid.uuid5(
        NCP_SBOM_NAMESPACE,
        json.dumps(sbom_identity, sort_keys=True, separators=(",", ":")),
    )
    if serial_uuid != expected_uuid:
        raise EvidenceError(
            "SBOM serial number is not bound to its deterministic inputs"
        )


def _self_test() -> None:
    def expect_rejected(label: str, action: Any) -> None:
        try:
            action()
        except EvidenceError:
            return
        raise AssertionError(f"hostile self-test did not fail closed: {label}")

    for ambiguous in (
        '{"release_authorized":true,"release_authorized":false}',
        '{"outer":{"revision":"a","revision":"b"}}',
        '{"dependency_count":Infinity}',
    ):
        expect_rejected(
            "duplicate JSON key",
            lambda ambiguous=ambiguous: _strict_json(
                ambiguous, "hostile self-test JSON"
            ),
        )

    if (
        _asset_class("conformance/baseline/v0.8.0/example.json")
        != "frozen-release-baseline"
    ):
        raise AssertionError("frozen baseline classification regressed")
    if _asset_class("ncp-core/testdata/vector.json") != "package-test-fixture":
        raise AssertionError("package testdata classification regressed")
    if _purl("npm", "@sepahead/ncp", "1.0.0-rc.1") != (
        "pkg:npm/%40sepahead/ncp@1.0.0-rc.1"
    ):
        raise AssertionError("package URL encoding regressed")
    if _internal_bom_ref("npm", "@sepahead/ncp", "1.0.0-rc.1") != (
        "urn:ncp:workspace:npm:%40sepahead%2Fncp@1.0.0-rc.1"
    ):
        raise AssertionError("internal component reference encoding regressed")
    if SRI_TO_CYCLONEDX.get("sha512") != "SHA-512":
        raise AssertionError("CycloneDX SHA-512 spelling regressed")
    expect_rejected("unknown asset class", lambda: _asset_class("unreviewed/model.bin"))
    for unsafe in ("", "../escape", "/absolute", "a/../b", "a\\b"):
        expect_rejected(
            f"unsafe archived-source path {unsafe!r}",
            lambda unsafe=unsafe: _safe_repository_path(unsafe),
        )

    reviewed_expressions = {
        " MIT/Apache-2.0 ": "MIT OR Apache-2.0",
        "Apache-2.0/MIT": "Apache-2.0 OR MIT",
        "Unlicense/MIT": "Unlicense OR MIT",
        "(MIT OR Apache-2.0) AND Unicode-3.0": ("(MIT OR Apache-2.0) AND Unicode-3.0"),
        "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT": (
            "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT"
        ),
        "MIT OR Apache-2.0 AND Zlib": "MIT OR Apache-2.0 AND Zlib",
    }
    for raw, expected in reviewed_expressions.items():
        actual = _normalize_spdx_expression(raw, "self-test")
        if actual != expected:
            raise AssertionError(
                f"SPDX normalization regressed for {raw!r}: {actual!r}"
            )
    for hostile in (
        "",
        "\tMIT",
        "MIT or Apache-2.0",
        "MIT/ISC",
        "GPL-3.0-only",
        "MIT OR",
        "(MIT OR Apache-2.0",
        "(MIT OR Apache-2.0) WITH LLVM-exception",
        "Apache-2.0 WITH Classpath-exception-2.0",
        "MIT Apache-2.0",
        "LicenseRef-private",
        "MIT+",
        "MIT\x00",
        ")",
    ):
        expect_rejected(
            f"hostile SPDX expression {hostile!r}",
            lambda hostile=hostile: _normalize_spdx_expression(
                hostile, "hostile self-test"
            ),
        )

    internal_component = {
        "type": "library",
        "bom-ref": _internal_bom_ref("cargo", "ncp-core", "1.0.0-rc.1"),
        "name": "ncp-core",
        "version": "1.0.0-rc.1",
        "properties": [{"name": "ncp:cargo-source", "value": "workspace"}],
    }
    if _validate_component_identity(internal_component) != "cargo":
        raise AssertionError("internal Cargo component identity regressed")
    poisoned_internal = dict(internal_component)
    poisoned_internal["purl"] = _purl("cargo", "ncp-core", "1.0.0-rc.1")
    expect_rejected(
        "registry PURL on an internal component",
        lambda: _validate_component_identity(poisoned_internal),
    )

    file_only_ref = _internal_bom_ref("cargo", "file-only", "1.0.0")
    expression_ref = _internal_bom_ref("npm", "expression", "1.0.0")
    license_components = sorted(
        [
            {
                "bom-ref": file_only_ref,
                "licenses": [{"license": {"name": "declared license file"}}],
            },
            {
                "bom-ref": expression_ref,
                "licenses": [{"expression": "MIT OR Apache-2.0"}],
            },
        ],
        key=lambda component: component["bom-ref"],
    )
    license_records = sorted(
        [
            {
                "bom_ref": file_only_ref,
                "license_expression_raw": None,
                "license_expression_normalized": None,
                "license_file_declared": True,
            },
            {
                "bom_ref": expression_ref,
                "license_expression_raw": " MIT/Apache-2.0 ",
                "license_expression_normalized": "MIT OR Apache-2.0",
                "license_file_declared": False,
            },
        ],
        key=lambda record: record["bom_ref"],
    )
    license_report_fixture = {
        "package_count": 2,
        "license_expression_counts": {
            "LICENSE_FILE": 1,
            "MIT OR Apache-2.0": 1,
        },
        "packages": license_records,
    }
    _validate_license_report(license_components, license_report_fixture)
    invalid_named_license_components = [
        dict(component) for component in license_components
    ]
    for component in invalid_named_license_components:
        if component["bom-ref"] == file_only_ref:
            component["licenses"] = [{"name": "declared license file"}]
    expect_rejected(
        "non-nested CycloneDX named license",
        lambda: _validate_license_report(
            invalid_named_license_components, license_report_fixture
        ),
    )

    graph_component_refs = sorted(
        [
            _internal_bom_ref("cargo", "ncp-core", "1.0.0-rc.1"),
            _internal_bom_ref("npm", "@sepahead/ncp", "1.0.0-rc.1"),
            _purl("npm", "typescript", "5.9.2"),
        ]
    )
    graph_root_ref = _internal_bom_ref("root", "NCP", "1.0.0-rc.1")

    def graph_fixture(
        *, root_targets: list[str] | None = None, omit_ref: str | None = None
    ) -> dict[str, Any]:
        components = [
            {"bom-ref": reference, "name": reference, "version": "1"}
            for reference in graph_component_refs
        ]
        dependencies = [
            {
                "ref": reference,
                "dependsOn": sorted(root_targets or [])
                if reference == graph_root_ref
                else [],
            }
            for reference in sorted([*graph_component_refs, graph_root_ref])
            if reference != omit_ref
        ]
        return {
            "metadata": {"component": {"bom-ref": graph_root_ref}},
            "components": components,
            "dependencies": dependencies,
        }

    _validate_sbom_graph(graph_fixture(root_targets=graph_component_refs))
    dangling = [*graph_component_refs, "urn:ncp:workspace:cargo:dangling@1"]
    expect_rejected(
        "dangling SBOM dependency target",
        lambda: _validate_sbom_graph(graph_fixture(root_targets=dangling)),
    )
    expect_rejected(
        "missing SBOM dependency node",
        lambda: _validate_sbom_graph(
            graph_fixture(
                root_targets=graph_component_refs, omit_ref=graph_component_refs[0]
            )
        ),
    )
    expect_rejected(
        "unreachable SBOM component",
        lambda: _validate_sbom_graph(
            graph_fixture(root_targets=[graph_component_refs[0]])
        ),
    )
    expect_rejected(
        "duplicate SBOM dependency target",
        lambda: _validate_sbom_graph(
            graph_fixture(
                root_targets=[graph_component_refs[0], graph_component_refs[0]]
            )
        ),
    )

    with tempfile.TemporaryDirectory(prefix="ncp-generator-self-test-") as directory:
        root = Path(directory)
        archive = root / "archived-source"
        flat_migration = archive / "ncp-core" / "src" / "migration.rs"
        nested_migration = archive / "ncp-core" / "src" / "migration" / "capture.rs"
        flat_migration.parent.mkdir(parents=True)
        nested_migration.parent.mkdir()
        flat_migration.write_text("pub mod capture;\n", encoding="utf-8")
        nested_migration.write_text("pub fn validate() {}\n", encoding="utf-8")
        flat_migration.chmod(0o644)
        nested_migration.chmod(0o644)
        archived_records = [
            {
                "path": path.relative_to(archive).as_posix(),
                "git_mode": "100644",
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in (flat_migration, nested_migration)
        ]
        archived_paths = [record["path"] for record in archived_records]
        if archived_paths != sorted(archived_paths):
            raise AssertionError("archived-source self-test paths are not canonical")
        if _validate_archived_file_records(archive, archived_records) != archived_paths:
            raise AssertionError(
                "archived-source validation depends on filesystem traversal order"
            )
        invalid_archived_records = [dict(record) for record in archived_records]
        invalid_archived_records[0]["sha256"] = "0" * 64
        expect_rejected(
            "archived-source content mismatch",
            lambda: _validate_archived_file_records(archive, invalid_archived_records),
        )

        target = root / "regular.py"
        target.write_text("pass\n", encoding="utf-8")
        link = root / "generate_link.py"
        link.symlink_to(target.name)
        expect_rejected(
            "linked generator candidate",
            lambda: _require_regular_generator_candidate(link),
        )
        special_directory = root / "generate_directory.py"
        special_directory.mkdir()
        expect_rejected(
            "directory generator candidate",
            lambda: _require_regular_generator_candidate(special_directory),
        )
        if hasattr(os, "mkfifo"):
            fifo = root / "generate_fifo.py"
            os.mkfifo(fifo)
            expect_rejected(
                "FIFO generator candidate",
                lambda: _require_regular_generator_candidate(fifo),
            )
        real_scripts = root / "real-scripts"
        real_scripts.mkdir()
        linked_scripts = root / "linked-scripts"
        linked_scripts.symlink_to(real_scripts.name, target_is_directory=True)
        expect_rejected(
            "linked generator directory",
            lambda: _generator_script_candidates(linked_scripts),
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--check", action="store_true")
    mode_group.add_argument(
        "--validate-current-advisories",
        action="store_true",
        help=(
            "read-only validation of the exact reviewed findings against the "
            "currently fetched advisory database"
        ),
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--tracked-files-manifest",
        type=Path,
        help="exact file manifest supplied by the archived-source dossier builder",
    )
    args = parser.parse_args()
    try:
        if args.tracked_files_manifest is not None and not args.check:
            raise EvidenceError("--tracked-files-manifest is valid only with --check")
        if args.self_test:
            _self_test()
        if args.validate_current_advisories:
            _reviewed_advisory_ignore_set()
            advisory_scan = _cargo_advisories()
            print(
                "OK current advisory findings validated: "
                f"{len(advisory_scan['findings'])} findings, "
                f"database {advisory_scan['advisory_database']['revision']}"
            )
            return 0
        outputs = _build_outputs(
            tracked_files_manifest=args.tracked_files_manifest,
        )
        _validate_outputs(outputs)
        if args.check:
            for name, value in outputs.items():
                path = EVIDENCE / name
                expected = _encoded(value)
                try:
                    actual = path.read_bytes()
                except OSError as error:
                    raise EvidenceError(
                        f"cannot read {path.relative_to(ROOT)}: {error}"
                    ) from error
                if actual != expected:
                    raise EvidenceError(
                        f"{path.relative_to(ROOT)} is stale; regenerate it"
                    )
        else:
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            for name, value in outputs.items():
                (EVIDENCE / name).write_bytes(_encoded(value))
    except (EvidenceError, AssertionError, OSError, UnicodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    mode = "verified" if args.check else "generated"
    print(
        f"OK supply-chain evidence {mode}: "
        f"{len(outputs['sbom.cdx.json']['components'])} components, "
        f"{len(outputs['inventory.v1.json']['assets_datasets_and_fixtures'])} assets/fixtures"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
