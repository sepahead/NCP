#!/usr/bin/env python3
"""Shared, fail-closed parser for NCP consumer pins.

The two public shell entry points deliberately keep their existing UX, while this
module owns descriptor parsing and all syntax-aware inspection.  Cargo manifests
and lockfiles are decoded with :mod:`tomllib`; package.json is decoded as JSON;
bun.lock is decoded as a narrowly normalised JSONC document.  Regexes are used
only after decoding, for canonical release/source *values*, never as a substitute
for parsing TOML or JSON structure.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import stat
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

try:
    import tomllib
except ModuleNotFoundError as exc:  # pragma: no cover - exercised on old hosts
    raise SystemExit(
        "consumer pin checks require Python 3.11+ (stdlib tomllib)"
    ) from exc


CANONICAL_CARGO_ORIGINS = {
    "https://github.com/sepahead/NCP",
    "https://github.com/sepahead/NCP.git",
}
NCP_CRATES = {"ncp-core", "ncp-zenoh"}
PIN_TYPES = {
    "cargo_tag",
    "cargo_lock",
    "cargo_rev",
    "cargo_lock_rev",
    "npm_tag",
    "npm_lock",
    "mirror_ref",
    "mirror_rev",
    "python_wire",
}
TAG_CARGO_TYPES = {"cargo_tag", "cargo_lock"}
REV_CARGO_TYPES = {"cargo_rev", "cargo_lock_rev"}
REV_TYPES = REV_CARGO_TYPES | {"mirror_rev"}
DEPENDENCY_TABLES = {
    "dependencies",
    "dev-dependencies",
    "build-dependencies",
    "dev_dependencies",
    "build_dependencies",
}
NPM_DEPENDENCY_TABLES = {
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
    "resolutions",
    "overrides",
}

_RELEASE_RE = re.compile(
    r"v(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z",
    re.ASCII,
)
_REV_RE = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_WIRE_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z", re.ASCII)
_U64_MAX = 18_446_744_073_709_551_615
_U64_MAX_TEXT = str(_U64_MAX)


class GuardError(ValueError):
    """A deterministic, user-actionable pin-contract error."""


class DuplicateJsonKey(GuardError):
    pass


@dataclass(frozen=True)
class Directive:
    kind: str
    rel: str
    line: int
    tag: str | None = None
    revision: str | None = None
    command: str | None = None


@dataclass
class Consumer:
    name: str
    root: Path
    descriptor: Path
    directives: list[Directive] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    has_repin_command: bool = False


@dataclass
class Evidence:
    tag: str
    revision: str | None = None
    resolved_commit: str | None = None
    npm_resolved: str | None = None


@dataclass
class Row:
    label: str
    pin: str
    error: str | None = None
    note: str | None = None
    evidence: Evidence | None = None
    consumer: str | None = None
    kind: str | None = None


@dataclass
class Scan:
    consumers: list[Consumer]
    rows: list[Row]
    errors: list[str]


def release_label_is_valid(tag: str) -> bool:
    match = _RELEASE_RE.fullmatch(tag)
    if match is None:
        return False
    prerelease = match.group(4)
    if prerelease:
        for identifier in prerelease.split("."):
            if identifier.isascii() and identifier.isdigit() and len(identifier) > 1:
                if identifier.startswith("0"):
                    return False
    return True


def _require_release(tag: str, *, where: str) -> None:
    if not release_label_is_valid(tag):
        raise GuardError(f"{where}: {tag!r} is not a canonical immutable release label")


def _wire_from_release(tag: str) -> str:
    _require_release(tag, where="release")
    match = _RELEASE_RE.fullmatch(tag)
    assert match is not None
    major, minor = match.group(1), match.group(2)
    if any(
        len(component) > len(_U64_MAX_TEXT)
        or (len(component) == len(_U64_MAX_TEXT) and component > _U64_MAX_TEXT)
        for component in (major, minor)
    ):
        raise GuardError(f"release {tag!r} cannot map to a canonical u64 wire version")
    return f"{major}.{minor}"


def _compatibility_line(tag: str) -> str:
    match = _RELEASE_RE.fullmatch(tag)
    if match is None or not release_label_is_valid(tag):
        raise GuardError(f"invalid release label {tag!r}")
    major, minor = match.group(1), match.group(2)
    return f"v0.{minor}" if major == "0" else f"v{major}.x"


def _normalise_crate(name: object) -> str:
    return str(name).replace("_", "-").casefold()


def _looks_like_ncp_repo(value: object) -> bool:
    if not isinstance(value, str):
        return False
    folded = value.casefold().strip()
    # Decode only for detection: an encoded alternate must be inspected and
    # rejected by the strict source parser, not disappear from coverage. Two
    # bounded passes cover the common encoded and double-encoded spellings.
    for _ in range(2):
        decoded = unquote(folded)
        if decoded == folded:
            break
        folded = decoded.casefold()
    folded = folded.replace("\\", "/")
    if re.search(
        r"(?:github\.com[/:]|github:)(?:[^/@:]+@)?sepahead/ncp(?:\.git)?(?:[/?#]|\Z)",
        folded,
    ):
        return True
    if re.search(r"(?:^|[/:])sepahead/ncp(?:\.git)?(?:[/?#]|\Z)", folded):
        return True
    if re.fullmatch(r"sepahead/ncp(?:\.git)?(?:#.*)?", folded):
        return True
    return False


def _looks_like_ncp_npm(value: object) -> bool:
    if not isinstance(value, str):
        return False
    folded = value.casefold().strip()
    return (
        _looks_like_ncp_repo(value)
        or "@sepahead/ncp" in folded
        or re.search(r"(?:^|[:/])sepahead/ncp(?:\.git)?(?:#|\Z)", folded) is not None
    )


def _is_named_ncp(key: object) -> bool:
    if not isinstance(key, str):
        return False
    return key.casefold().rsplit("/", 1)[-1] == "ncp"


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJsonKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_json(text: str, *, where: Path) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_json_object)
    except (json.JSONDecodeError, DuplicateJsonKey) as exc:
        raise GuardError(f"{where}: invalid/ambiguous JSON: {exc}") from exc


def _jsonc_to_json(text: str, *, where: Path) -> str:
    """Remove JSONC comments and trailing commas without touching string bytes."""

    out: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < len(text) and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end < 0:
                raise GuardError(f"{where}: unterminated bun.lock block comment")
            out.append(" ")
            out.extend("\n" for c in text[i : end + 2] if c == "\n")
            i = end + 2
            continue
        out.append(ch)
        i += 1
    if in_string:
        raise GuardError(f"{where}: unterminated bun.lock string")

    raw = "".join(out)
    out = []
    i = 0
    in_string = False
    escaped = False
    while i < len(raw):
        ch = raw[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j < len(raw) and raw[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            value = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise GuardError(f"{path}: invalid/ambiguous TOML: {exc}") from exc
    if not isinstance(value, dict):
        raise GuardError(f"{path}: TOML root must be a table")
    return value


def _safe_declared_file(root: Path, rel: str) -> Path:
    relative = Path(rel)
    if (
        not rel
        or relative.is_absolute()
        or rel in {".", ".."}
        or ".." in relative.parts
    ):
        raise GuardError(f"unsafe declared path {rel!r}")
    physical_root = root.resolve(strict=True)
    candidate = root / relative
    if candidate.is_symlink():
        raise GuardError(f"declared path {rel!r} is a symlink")
    try:
        physical_parent = candidate.parent.resolve(strict=True)
    except OSError as exc:
        raise GuardError(f"declared path {rel!r} has a missing parent") from exc
    try:
        common = Path(os.path.commonpath((physical_root, physical_parent)))
    except ValueError as exc:
        raise GuardError(f"declared path {rel!r} escapes the consumer") from exc
    if common != physical_root:
        raise GuardError(f"declared path {rel!r} escapes the consumer")
    try:
        mode = candidate.stat(follow_symlinks=False).st_mode
    except FileNotFoundError as exc:
        raise FileNotFoundError(rel) from exc
    if not stat.S_ISREG(mode):
        raise GuardError(f"declared path {rel!r} is not a regular file")
    return candidate


def _descriptor_arity(kind: str, count: int) -> bool:
    if kind in {"cargo_tag", "cargo_lock", "npm_tag", "npm_lock", "mirror_ref"}:
        return count == 2
    if kind == "python_wire":
        return count == 3
    if kind in REV_TYPES:
        return count == 4
    if kind == "repin_cmd":
        return count >= 2
    return False


def _parse_descriptor(path: Path) -> Consumer:
    root = path.parent.resolve(strict=True)
    consumer = Consumer(root.name, root, path)
    if path.is_symlink() or not path.is_file():
        consumer.errors.append(f"{path}: descriptor must be a regular non-symlink file")
        return consumer
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        consumer.errors.append(f"{path}: unreadable UTF-8 descriptor: {exc}")
        return consumer
    repin_commands = 0
    for number, raw in enumerate(text.splitlines(), 1):
        body = raw.split("#", 1)[0].strip()
        if not body:
            continue
        fields = body.split()
        kind = fields[0]
        if not _descriptor_arity(kind, len(fields)):
            consumer.errors.append(f"{path}:{number}: invalid arity for {kind!r}")
            continue
        if kind == "repin_cmd":
            repin_commands += 1
            if repin_commands > 1:
                consumer.errors.append(f"{path}:{number}: duplicate repin_cmd")
            command = body[len(kind) :].strip()
            consumer.directives.append(Directive(kind, "", number, command=command))
            consumer.has_repin_command = True
            continue
        tag = fields[2] if len(fields) >= 3 else None
        revision = fields[3] if len(fields) >= 4 else None
        if tag is not None and not release_label_is_valid(tag):
            consumer.errors.append(
                f"{path}:{number}: noncanonical release label {tag!r}"
            )
        if revision is not None and _REV_RE.fullmatch(revision) is None:
            consumer.errors.append(
                f"{path}:{number}: revision must be exact lowercase 40-hex"
            )
        consumer.directives.append(Directive(kind, fields[1], number, tag, revision))
    if not any(item.kind in PIN_TYPES for item in consumer.directives):
        consumer.errors.append(f"{path}: no recognized pin-bearing directive")
    return consumer


def _discover(base: Path) -> list[Consumer]:
    descriptors = sorted(base.glob("*/.ncp-consumer"))
    if not descriptors:
        raise GuardError(
            f"No consumers found under {base} (no */.ncp-consumer descriptors)."
        )
    physical_base = base.resolve(strict=True)
    for descriptor in descriptors:
        logical_root = descriptor.parent
        if logical_root.is_symlink():
            raise GuardError(f"{logical_root}: consumer root must not be a symlink")
        try:
            physical_root = logical_root.resolve(strict=True)
        except OSError as exc:
            raise GuardError(
                f"{logical_root}: consumer root cannot be resolved"
            ) from exc
        if physical_root.parent != physical_base:
            raise GuardError(
                f"{logical_root}: consumer root is not a direct physical child of {physical_base}"
            )
    return [_parse_descriptor(path) for path in descriptors]


def _is_ncp_dependency(key: str, value: object) -> bool:
    if _normalise_crate(key) in NCP_CRATES:
        return True
    if not isinstance(value, dict):
        return False
    if _normalise_crate(value.get("package", "")) in NCP_CRATES:
        return True
    return _looks_like_ncp_repo(value.get("git"))


def _cargo_dependencies(
    data: dict[str, Any],
) -> list[tuple[str, dict[str, Any] | object]]:
    found: list[tuple[str, dict[str, Any] | object]] = []

    def visit(node: object, path: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            return
        is_dependency_table = bool(path) and path[-1] in DEPENDENCY_TABLES
        for key, value in node.items():
            key_text = str(key)
            if is_dependency_table or _is_ncp_dependency(key_text, value):
                if _is_ncp_dependency(key_text, value):
                    found.append((".".join(path + (key_text,)), value))
                    continue
            if isinstance(value, dict):
                visit(value, path + (key_text,))

    visit(data, ())
    return found


def _inspect_cargo_manifest(
    path: Path, mode: str, declared_tag: str | None, declared_rev: str | None
) -> Evidence:
    data = _load_toml(path)
    dependencies = _cargo_dependencies(data)
    if not dependencies:
        raise GuardError(f"{path}: no NCP Cargo dependency found")
    tags: set[str] = set()
    revisions: set[str] = set()
    for location, raw in dependencies:
        if not isinstance(raw, dict):
            raise GuardError(
                f"{path}:{location}: NCP dependency is not an explicit git table"
            )
        origin = raw.get("git")
        if origin not in CANONICAL_CARGO_ORIGINS:
            raise GuardError(
                f"{path}:{location}: noncanonical or missing NCP git origin {origin!r}"
            )
        selectors = [key for key in ("tag", "rev", "branch") if key in raw]
        expected_selector = "tag" if mode == "tag" else "rev"
        if selectors != [expected_selector]:
            raise GuardError(
                f"{path}:{location}: expected exactly one {expected_selector!r} selector; got {selectors}"
            )
        forbidden_sources = [
            key for key in ("path", "registry", "registry-index") if key in raw
        ]
        if forbidden_sources:
            raise GuardError(
                f"{path}:{location}: mixed Cargo sources {forbidden_sources}"
            )
        selector = raw[expected_selector]
        if not isinstance(selector, str):
            raise GuardError(f"{path}:{location}: {expected_selector} must be a string")
        if mode == "tag":
            _require_release(selector, where=f"{path}:{location} tag")
            tags.add(selector)
            effective_tag = selector
        else:
            if _REV_RE.fullmatch(selector) is None:
                raise GuardError(
                    f"{path}:{location}: rev must be exact lowercase 40-hex"
                )
            if declared_rev is None or selector != declared_rev:
                raise GuardError(
                    f"{path}:{location}: revision differs from descriptor metadata"
                )
            if declared_tag is None:
                raise GuardError(
                    f"{path}:{location}: revision mode lacks a declared release"
                )
            tags.add(declared_tag)
            revisions.add(selector)
            effective_tag = declared_tag
        if "version" in raw:
            version = raw["version"]
            expected_version = effective_tag.removeprefix("v")
            if not isinstance(version, str) or version not in {
                expected_version,
                f"={expected_version}",
            }:
                raise GuardError(
                    f"{path}:{location}: explicit Cargo version {version!r} does not equal {expected_version!r}"
                )
    if len(tags) != 1:
        raise GuardError(
            f"{path}: NCP Cargo dependencies disagree on release labels: {sorted(tags)}"
        )
    if mode == "rev" and len(revisions) != 1:
        raise GuardError(
            f"{path}: NCP Cargo dependencies disagree on immutable revision"
        )
    tag = next(iter(tags))
    return Evidence(tag, revision=next(iter(revisions)) if revisions else None)


def _lock_sources(data: dict[str, Any], path: Path) -> list[str]:
    found: list[str] = []
    packages = data.get("package")
    if isinstance(packages, list):
        for index, package in enumerate(packages):
            if not isinstance(package, dict):
                raise GuardError(f"{path}: Cargo.lock package[{index}] is not a table")
            name = package.get("name")
            source = package.get("source")
            named = _normalise_crate(name) in NCP_CRATES
            sourced = _looks_like_ncp_repo(source)
            if named or sourced:
                if not isinstance(source, str):
                    raise GuardError(f"{path}: NCP package {name!r} has no git source")
                found.append(source)
    # Small synthetic fixtures may carry one root source.  Duplicate root keys are
    # rejected by tomllib, so this compatibility path cannot hide multi-source drift.
    root_source = data.get("source")
    if isinstance(root_source, str) and _looks_like_ncp_repo(root_source):
        found.append(root_source)
    return found


def _parse_lock_source(source: str, *, path: Path, mode: str) -> tuple[str, str]:
    if not source.startswith("git+") or "#" not in source or "?" not in source:
        raise GuardError(f"{path}: malformed NCP Cargo.lock source {source!r}")
    locator, resolved = source[4:].rsplit("#", 1)
    origin, query = locator.split("?", 1)
    if origin not in CANONICAL_CARGO_ORIGINS:
        raise GuardError(f"{path}: noncanonical NCP Cargo.lock origin {origin!r}")
    if _REV_RE.fullmatch(resolved) is None:
        raise GuardError(
            f"{path}: resolved Cargo.lock commit must be exact lowercase 40-hex"
        )
    pieces = query.split("&")
    expected = "tag" if mode == "tag" else "rev"
    if len(pieces) != 1 or "=" not in pieces[0]:
        raise GuardError(f"{path}: ambiguous Cargo.lock selector query {query!r}")
    key, value = pieces[0].split("=", 1)
    if key != expected or not value:
        raise GuardError(
            f"{path}: expected exactly one {expected!r} lock selector, got {query!r}"
        )
    return value, resolved


def _inspect_cargo_lock(
    path: Path, mode: str, declared_tag: str | None, declared_rev: str | None
) -> Evidence:
    sources = _lock_sources(_load_toml(path), path)
    if not sources:
        raise GuardError(f"{path}: no NCP Cargo.lock source found")
    selectors: set[str] = set()
    commits: set[str] = set()
    for source in sources:
        selector, commit = _parse_lock_source(source, path=path, mode=mode)
        selectors.add(selector)
        commits.add(commit)
    if len(selectors) != 1:
        raise GuardError(f"{path}: NCP lock selectors disagree: {sorted(selectors)}")
    if len(commits) != 1:
        raise GuardError(f"{path}: NCP lock sources resolve to contradictory commits")
    selector = next(iter(selectors))
    commit = next(iter(commits))
    if mode == "tag":
        _require_release(selector, where=f"{path} lock tag")
        return Evidence(selector, resolved_commit=commit)
    if _REV_RE.fullmatch(selector) is None or declared_rev is None:
        raise GuardError(
            f"{path}: revision lock selector is not exact lowercase 40-hex"
        )
    if selector != declared_rev or commit != declared_rev:
        raise GuardError(
            f"{path}: requested/resolved lock revision differs from descriptor metadata"
        )
    if declared_tag is None:
        raise GuardError(f"{path}: revision lock lacks a declared release")
    return Evidence(declared_tag, revision=declared_rev, resolved_commit=commit)


def _dependency_specs(data: object) -> Iterable[tuple[str, object]]:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in NPM_DEPENDENCY_TABLES and isinstance(value, dict):
                yield from value.items()
            yield from _dependency_specs(value)
    elif isinstance(data, list):
        for value in data:
            yield from _dependency_specs(value)


def _all_string_values(data: object) -> Iterable[str]:
    stack = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str):
            yield value


def _inspect_bun_resolution_records(
    data: object, direct_tag: str, *, path: Path
) -> str | None:
    """Validate every NCP-looking bun resolution string.

    bun's array record uses a short resolved commit in place of the requested tag;
    that identity remains informational because the offline guard cannot prove a
    tag-to-commit mapping. It must nevertheless be canonical and internally
    unambiguous. A tag-bearing record must agree with the direct dependency row.
    """

    commits: set[str] = set()
    for value in _all_string_values(data):
        if not _looks_like_ncp_npm(value):
            continue
        # A resolution record commonly prefixes the source with
        # "@scope/ncp@". Locate the decoded source rather than relying on that key.
        marker = value.find("github:")
        if marker < 0:
            raise GuardError(f"{path}: noncanonical NCP bun resolution {value!r}")
        source = value[marker:]
        match = re.fullmatch(r"github:sepahead/NCP#([^\"#]+)", source, re.ASCII)
        if match is None:
            raise GuardError(f"{path}: noncanonical NCP bun resolution {value!r}")
        identity = match.group(1)
        if release_label_is_valid(identity):
            if identity != direct_tag:
                raise GuardError(
                    f"{path}: bun resolution tag {identity!r} disagrees with direct tag {direct_tag!r}"
                )
        elif re.fullmatch(r"[0-9a-f]{7,40}", identity, re.ASCII):
            commits.add(identity)
        else:
            raise GuardError(
                f"{path}: ambiguous NCP bun resolution identity {identity!r}"
            )
    if commits:
        longest = max(commits, key=len)
        if any(not longest.startswith(value) for value in commits):
            raise GuardError(
                f"{path}: contradictory NCP bun resolved commits {sorted(commits)}"
            )
        return longest
    return None


def _inspect_npm(path: Path, *, bun_lock: bool) -> Evidence:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise GuardError(f"{path}: unreadable UTF-8 npm pin file: {exc}") from exc
    if bun_lock:
        data = _load_json(_jsonc_to_json(raw, where=path), where=path)
    else:
        data = _load_json(raw, where=path)
    tags: set[str] = set()
    seen = 0
    for key, value in _dependency_specs(data):
        if not (_is_named_ncp(key) or _looks_like_ncp_npm(value)):
            continue
        seen += 1
        if not isinstance(value, str):
            raise GuardError(
                f"{path}: NCP npm dependency {key!r} is not a string source"
            )
        match = re.fullmatch(r"github:sepahead/NCP#([^\"#]+)", value, re.ASCII)
        if match is None:
            raise GuardError(
                f"{path}: NCP npm dependency {key!r} uses noncanonical source {value!r}"
            )
        tag = match.group(1)
        _require_release(tag, where=f"{path} npm tag")
        tags.add(tag)
    if seen == 0 or not tags:
        raise GuardError(f"{path}: no direct NCP npm dependency found")
    if len(tags) != 1:
        raise GuardError(
            f"{path}: direct NCP npm dependencies disagree: {sorted(tags)}"
        )
    tag = next(iter(tags))
    resolution = (
        _inspect_bun_resolution_records(data, tag, path=path) if bun_lock else None
    )
    return Evidence(tag, npm_resolved=resolution)


def _inspect_mirror_ref(path: Path) -> Evidence:
    raw = path.read_bytes()
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if b"\n" in raw or b"\r" in raw:
        raise GuardError(f"{path}: mirror ref must contain exactly one canonical tag")
    try:
        tag = raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise GuardError(f"{path}: mirror ref is not ASCII") from exc
    _require_release(tag, where=str(path))
    return Evidence(tag)


def _inspect_mirror_rev(path: Path, tag: str | None, revision: str | None) -> Evidence:
    if tag is None or revision is None:
        raise GuardError(f"{path}: mirror revision descriptor metadata is incomplete")
    _require_release(tag, where=str(path))
    if _REV_RE.fullmatch(revision) is None:
        raise GuardError(
            f"{path}: mirror revision metadata is not exact lowercase 40-hex"
        )
    raw = path.read_bytes()
    if raw not in {revision.encode("ascii"), revision.encode("ascii") + b"\n"}:
        raise GuardError(
            f"{path}: mirror revision file differs from descriptor metadata"
        )
    return Evidence(tag, revision=revision, resolved_commit=revision)


def _inspect_python(path: Path, tag: str | None) -> Evidence:
    if tag is None:
        raise GuardError(f"{path}: Python wire descriptor lacks a release label")
    expected = _wire_from_release(tag)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise GuardError(f"{path}: Python wire module is not parseable: {exc}") from exc
    values: list[str] = []
    for node in ast.walk(tree):
        value: ast.expr | None = None
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if not any(
            isinstance(target, ast.Name) and target.id == "NCP_VERSION"
            for target in targets
        ):
            continue
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            raise GuardError(f"{path}: NCP_VERSION must be assigned a literal string")
        values.append(value.value)
    if not values or len(set(values)) != 1:
        raise GuardError(f"{path}: missing or contradictory NCP_VERSION assignments")
    runtime = values[0]
    match = _WIRE_RE.fullmatch(runtime)
    if match is None or any(
        len(part) > len(_U64_MAX_TEXT)
        or (len(part) == len(_U64_MAX_TEXT) and part > _U64_MAX_TEXT)
        for part in match.groups()
    ):
        raise GuardError(f"{path}: runtime NCP_VERSION {runtime!r} is noncanonical")
    if runtime != expected:
        raise GuardError(
            f"{path}: runtime wire {runtime!r} differs from release {tag!r} ({expected})"
        )
    return Evidence(tag)


def _inspect(directive: Directive, path: Path) -> Evidence:
    if directive.kind == "cargo_tag":
        return _inspect_cargo_manifest(path, "tag", None, None)
    if directive.kind == "cargo_rev":
        return _inspect_cargo_manifest(path, "rev", directive.tag, directive.revision)
    if directive.kind == "cargo_lock":
        return _inspect_cargo_lock(path, "tag", None, None)
    if directive.kind == "cargo_lock_rev":
        return _inspect_cargo_lock(path, "rev", directive.tag, directive.revision)
    if directive.kind == "npm_tag":
        return _inspect_npm(path, bun_lock=False)
    if directive.kind == "npm_lock":
        return _inspect_npm(path, bun_lock=True)
    if directive.kind == "mirror_ref":
        return _inspect_mirror_ref(path)
    if directive.kind == "mirror_rev":
        return _inspect_mirror_rev(path, directive.tag, directive.revision)
    if directive.kind == "python_wire":
        return _inspect_python(path, directive.tag)
    raise GuardError(f"unsupported directive {directive.kind!r}")


def _cargo_rewrite_supported(path: Path, mode: str) -> bool:
    """The in-place rewriter intentionally accepts one conservative lexical form.

    The checker still understands all TOML forms through tomllib.  A repin of an
    exotic but valid form fails *before mutation* and asks the consumer-owned
    command to own that rewrite, rather than risking a formatting-based partial edit.
    """

    text = path.read_text(encoding="utf-8")
    data = _load_toml(path)
    expected = len(_cargo_dependencies(data))
    supported = 0
    selector = "tag" if mode == "tag" else "rev"
    for line in text.splitlines():
        code, _ = _split_toml_comment(line)
        if not re.match(r"^\s*[A-Za-z0-9_-]+\s*=\s*\{.*\}\s*$", code):
            continue
        try:
            parsed = tomllib.loads(code)
        except tomllib.TOMLDecodeError:
            return False
        if len(parsed) != 1:
            return False
        key, value = next(iter(parsed.items()))
        if not _is_ncp_dependency(str(key), value):
            continue
        if (
            not isinstance(value, dict)
            or value.get("git") not in CANONICAL_CARGO_ORIGINS
        ):
            return False
        if not re.search(
            r'\bgit\s*=\s*"https://github\.com/sepahead/NCP(?:\.git)?"', code
        ):
            return False
        if len(re.findall(rf'\b{selector}\s*=\s*"[^"]*"', code)) != 1:
            return False
        expected_versions = 1 if "version" in value else 0
        if len(re.findall(r'\bversion\s*=\s*"[^"]*"', code)) != expected_versions:
            return False
        supported += 1
    return expected > 0 and supported == expected


def _split_toml_comment(line: str) -> tuple[str, str]:
    quote: str | None = None
    escaped = False
    for index, ch in enumerate(line):
        if quote == '"':
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
        elif quote == "'":
            if ch == quote:
                quote = None
        elif ch in {'"', "'"}:
            quote = ch
        elif ch == "#":
            return line[:index], line[index:]
    return line, ""


def _coherence(consumers: list[Consumer], rows: list[Row]) -> list[str]:
    errors: list[str] = []
    by_consumer: dict[str, list[Row]] = {}
    for row in rows:
        if row.consumer:
            by_consumer.setdefault(row.consumer, []).append(row)
    for consumer in consumers:
        modes = {
            "tag" if directive.kind in TAG_CARGO_TYPES else "rev"
            for directive in consumer.directives
            if directive.kind in TAG_CARGO_TYPES | REV_CARGO_TYPES
        }
        if len(modes) > 1:
            errors.append(
                f"{consumer.name}: Cargo manifest/lock directives mix tag and revision modes"
            )
        cargo_tags = {
            row.evidence.tag
            for row in by_consumer.get(consumer.name, [])
            if row.kind in TAG_CARGO_TYPES | REV_CARGO_TYPES
            and row.evidence is not None
        }
        if len(cargo_tags) > 1:
            errors.append(
                f"{consumer.name}: Cargo manifest/lock rows disagree on exact release labels"
            )
        all_tags = {
            row.evidence.tag
            for row in by_consumer.get(consumer.name, [])
            if row.evidence is not None
        }
        if len(all_tags) > 1:
            errors.append(
                f"{consumer.name}: declared manifest/lock/runtime sources disagree on exact release labels"
            )

    revisions_by_tag: dict[str, set[str]] = {}
    for row in rows:
        if row.evidence is None:
            continue
        evidence = row.evidence
        identities = {
            value for value in (evidence.revision, evidence.resolved_commit) if value
        }
        if identities:
            revisions_by_tag.setdefault(evidence.tag, set()).update(identities)
    for tag, revisions in sorted(revisions_by_tag.items()):
        if len(revisions) > 1:
            errors.append(
                f"release {tag} maps to contradictory immutable commits: {', '.join(sorted(revisions))}"
            )
    return errors


def scan(base: Path, *, repin_preflight: bool = False) -> Scan:
    consumers = _discover(base)
    rows: list[Row] = []
    errors: list[str] = []
    for consumer in consumers:
        errors.extend(consumer.errors)
        pin_count = 0
        for directive in consumer.directives:
            if directive.kind == "repin_cmd":
                continue
            pin_count += 1
            label = f"{consumer.name}/{directive.rel} ({directive.kind})"
            try:
                path = _safe_declared_file(consumer.root, directive.rel)
            except FileNotFoundError:
                rows.append(
                    Row(
                        label,
                        "__MISSING__",
                        "file not found",
                        consumer=consumer.name,
                        kind=directive.kind,
                    )
                )
                errors.append(f"{label}: file not found")
                continue
            except GuardError as exc:
                rows.append(
                    Row(
                        label,
                        "__UNRESOLVED__",
                        str(exc),
                        consumer=consumer.name,
                        kind=directive.kind,
                    )
                )
                errors.append(f"{label}: {exc}")
                continue
            try:
                evidence = _inspect(directive, path)
                if (
                    repin_preflight
                    and not consumer.has_repin_command
                    and directive.kind in {"cargo_tag", "cargo_rev"}
                    and not _cargo_rewrite_supported(
                        path, "tag" if directive.kind == "cargo_tag" else "rev"
                    )
                ):
                    raise GuardError(
                        f"{path}: TOML is valid but not safely rewritable in place; add a consumer repin_cmd"
                    )
                if (
                    repin_preflight
                    and not consumer.has_repin_command
                    and directive.kind == "npm_tag"
                ):
                    try:
                        npm_raw = path.read_text(encoding="utf-8")
                    except (OSError, UnicodeError) as exc:
                        raise GuardError(
                            f"{path}: unreadable UTF-8 npm pin file: {exc}"
                        ) from exc
                    _npm_rewrite_spans(path, npm_raw)
            except GuardError as exc:
                rows.append(
                    Row(
                        label,
                        "__UNRESOLVED__",
                        str(exc),
                        consumer=consumer.name,
                        kind=directive.kind,
                    )
                )
                errors.append(f"{label}: {exc}")
                continue
            note = None
            if directive.kind in REV_TYPES:
                note = (
                    f"{consumer.name}/{directive.rel} immutable revision = {directive.revision} "
                    f"(consumer-declared release {directive.tag})"
                )
            elif directive.kind == "python_wire":
                note = (
                    f"{consumer.name}/{directive.rel} Python runtime wire checked against "
                    f"consumer-declared release {directive.tag}"
                )
            elif directive.kind == "npm_lock" and evidence.npm_resolved:
                note = (
                    f"{consumer.name}/{directive.rel} resolved commit = {evidence.npm_resolved} "
                    "(informational)"
                )
            rows.append(
                Row(
                    label,
                    evidence.tag,
                    note=note,
                    evidence=evidence,
                    consumer=consumer.name,
                    kind=directive.kind,
                )
            )
        if pin_count == 0:
            label = f"{consumer.name}/.ncp-consumer (no pin-bearing directives)"
            rows.append(
                Row(
                    label,
                    "__UNRESOLVED__",
                    "no pin-bearing directives",
                    consumer=consumer.name,
                )
            )
    errors.extend(_coherence(consumers, rows))
    return Scan(consumers, rows, list(dict.fromkeys(errors)))


def _render_check(base: Path, expected: str) -> int:
    if expected and not release_label_is_valid(expected):
        print(
            f"ERROR: expected tag {expected!r} is not a canonical immutable NCP release label.",
            file=sys.stderr,
        )
        return 2
    try:
        result = scan(base)
    except GuardError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "A consumer registers by committing a .ncp-consumer file to its repo root; "
            'see INTEGRATING.md §"Registering a consumer".',
            file=sys.stderr,
        )
        return 1

    labels = [row.label for row in result.rows]
    width = max((len(label) for label in labels), default=len("CONSUMER"))
    print(f"NCP consumer pins (base-dir: {base})\n")
    print(f"  {'CONSUMER':<{width}}  PIN")
    print(f"  {'-' * width}  ----------------")
    for row in result.rows:
        shown = {
            "__MISSING__": "<file not found>",
            "__UNRESOLVED__": "<no pin matched>",
        }.get(row.pin, row.pin)
        print(f"  {row.label:<{width}}  {shown}")
    notes = [row.note for row in result.rows if row.note]
    if notes:
        print()
        for note in notes:
            print(f"  note: {note}")
    print()

    problems = list(result.errors)
    for row in result.rows:
        if row.pin == "__MISSING__":
            problems.append(f"{row.label}: file not found")
        elif row.pin == "__UNRESOLVED__":
            problems.append(
                f"{row.label}: {row.error or 'file present but no NCP pin matched'}"
            )
    concrete = [row.pin for row in result.rows if not row.pin.startswith("__")]
    if expected:
        for row in result.rows:
            if not row.pin.startswith("__") and row.pin != expected:
                problems.append(
                    f"{row.label}: pinned to {row.pin!r}, expected {expected!r}"
                )
    elif concrete:
        lines: dict[str, set[str]] = {}
        for tag in concrete:
            try:
                line = _compatibility_line(tag)
            except GuardError as exc:
                problems.append(str(exc))
                continue
            lines.setdefault(line, set()).add(tag)
        if len(lines) > 1:
            problems.append(
                "consumers are on INCOMPATIBLE wire lines: "
                + " ".join(sorted(lines))
                + " (tags: "
                + " ".join(sorted(set(concrete)))
                + ")"
            )

    problems = list(dict.fromkeys(problems))
    if problems:
        sys.stdout.flush()
        print("MISMATCH:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\n  Re-pin each consumer to the target tag (manifest AND lockfile move together),\n"
            "  then re-run. Each consumer owns its re-pin recipe; see its .ncp-consumer and\n"
            "  README. Mirror-style consumers run their own sync script (do NOT hand-edit a mirror).",
            file=sys.stderr,
        )
        return 1

    if expected:
        print(f"OK: all consumers pin NCP {expected}")
    else:
        unique = sorted(set(concrete))
        line = _compatibility_line(unique[0]) if unique else ""
        if len(unique) > 1:
            print(
                f"OK: all consumers are wire-compatible ({line}); release labels differ: "
                + " ".join(unique)
            )
            print("    (pre-1.0 requires one minor; stable releases require one major)")
        elif unique:
            print(f"OK: all consumers pin NCP {unique[0]}")
    return 0


def _atomic_write(path: Path, data: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _rewrite_cargo(path: Path, mode: str, tag: str, revision: str | None) -> None:
    _require_release(tag, where="target tag")
    if mode == "rev" and (revision is None or _REV_RE.fullmatch(revision) is None):
        raise GuardError(
            "revision rewrite requires one exact lowercase 40-hex revision"
        )
    # Validate the old source shape first, then refuse syntax the conservative
    # in-place editor cannot prove it covers completely. Full descriptor/value
    # coherence was already established by the fleet preflight.
    source_data = _load_toml(path)
    source_dependencies = _cargo_dependencies(source_data)
    if not source_dependencies:
        raise GuardError(f"{path}: no NCP Cargo dependency found")
    selector_name = "tag" if mode == "tag" else "rev"
    for location, raw in source_dependencies:
        if not isinstance(raw, dict) or raw.get("git") not in CANONICAL_CARGO_ORIGINS:
            raise GuardError(f"{path}:{location}: noncanonical NCP dependency")
        selectors = [key for key in ("tag", "rev", "branch") if key in raw]
        if selectors != [selector_name]:
            raise GuardError(
                f"{path}:{location}: expected exactly one {selector_name!r} selector; got {selectors}"
            )
        forbidden_sources = [
            key for key in ("path", "registry", "registry-index") if key in raw
        ]
        if forbidden_sources:
            raise GuardError(
                f"{path}:{location}: mixed Cargo sources {forbidden_sources}"
            )
        old_selector = raw[selector_name]
        if not isinstance(old_selector, str):
            raise GuardError(f"{path}:{location}: selector must be a string")
        if mode == "tag":
            _require_release(old_selector, where=f"{path}:{location} tag")
            old_tag = old_selector
        else:
            if _REV_RE.fullmatch(old_selector) is None:
                raise GuardError(
                    f"{path}:{location}: rev must be exact lowercase 40-hex"
                )
            old_tag = None
        if "version" in raw:
            old_version = raw["version"]
            if not isinstance(old_version, str):
                raise GuardError(
                    f"{path}:{location}: explicit version must be a string"
                )
            if mode == "tag" and old_version not in {
                old_tag.removeprefix("v"),
                f"={old_tag.removeprefix('v')}",
            }:
                raise GuardError(f"{path}:{location}: stale explicit version")
    if not _cargo_rewrite_supported(path, mode):
        raise GuardError(f"{path}: Cargo TOML form is not safely rewritable in place")
    target_version = tag.removeprefix("v")
    output: list[str] = []
    changed = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        ending = "\n" if raw_line.endswith("\n") else ""
        line = raw_line[:-1] if ending else raw_line
        code, comment = _split_toml_comment(line)
        parsed_line: dict[str, Any] = {}
        if re.match(r"^\s*[A-Za-z0-9_-]+\s*=\s*\{.*\}\s*$", code):
            try:
                parsed_line = tomllib.loads(code)
            except (
                tomllib.TOMLDecodeError
            ) as exc:  # preflight should make this unreachable
                raise GuardError(
                    f"{path}: inline dependency became unparsable: {exc}"
                ) from exc
        is_ncp_line = False
        semantic_value: dict[str, Any] | None = None
        if len(parsed_line) == 1:
            parsed_key, parsed_value = next(iter(parsed_line.items()))
            if _is_ncp_dependency(str(parsed_key), parsed_value) and isinstance(
                parsed_value, dict
            ):
                is_ncp_line = True
                semantic_value = parsed_value
        if is_ncp_line:
            selector = "tag" if mode == "tag" else "rev"
            value = tag if mode == "tag" else revision
            assert value is not None
            code, count = re.subn(
                rf'(\b{selector}\s*=\s*")[^"]*(")',
                lambda match: f"{match.group(1)}{value}{match.group(2)}",
                code,
            )
            if count != 1:
                raise GuardError(
                    f"{path}: could not rewrite exactly one {selector} selector"
                )
            assert semantic_value is not None
            if "version" in semantic_value:
                version_prefix = (
                    "=" if semantic_value["version"].startswith("=") else ""
                )
                code, version_count = re.subn(
                    r'(\bversion\s*=\s*")[^"]*(")',
                    lambda match: (
                        f"{match.group(1)}{version_prefix}{target_version}{match.group(2)}"
                    ),
                    code,
                )
                if version_count != 1:
                    raise GuardError(
                        f"{path}: could not rewrite exactly one explicit version"
                    )
            if re.fullmatch(r"#\s*v[0-9A-Za-z.+-]+\s*", comment):
                spacing = re.match(r"#\s*", comment)
                assert spacing is not None
                comment = f"{spacing.group(0)}{tag}"
            changed += 1
        output.append(code + comment + ending)
    if changed == 0:
        raise GuardError(f"{path}: no safely rewritable NCP dependency found")
    new_text = "".join(output)
    # Parse and inspect the candidate before the atomic replacement.  For revision
    # mode the descriptor metadata is updated immediately after this command, so
    # inspect directly against the requested target metadata.
    try:
        candidate_data = tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as exc:
        raise GuardError(f"{path}: rewrite produced invalid TOML: {exc}") from exc
    # Reuse the semantic dependency validator without writing a temporary candidate.
    dependencies = _cargo_dependencies(candidate_data)
    if len(dependencies) != changed:
        raise GuardError(f"{path}: rewrite did not cover every NCP dependency")
    for _, value in dependencies:
        assert isinstance(value, dict)
        key = "tag" if mode == "tag" else "rev"
        expected = tag if mode == "tag" else revision
        if value.get(key) != expected:
            raise GuardError(f"{path}: rewrite candidate has stale {key} metadata")
        if "version" in value and value["version"] not in {
            target_version,
            f"={target_version}",
        }:
            raise GuardError(f"{path}: rewrite candidate has stale explicit version")
    _atomic_write(path, new_text)


def _json_string_tokens(raw: str) -> Iterable[tuple[int, int, str]]:
    i = 0
    while i < len(raw):
        if raw[i] != '"':
            i += 1
            continue
        start = i
        i += 1
        escaped = False
        while i < len(raw):
            ch = raw[i]
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                end = i + 1
                try:
                    value = json.loads(raw[start:end])
                except json.JSONDecodeError as exc:
                    raise GuardError(f"invalid JSON string token: {exc}") from exc
                yield start, end, value
                i = end
                break
            i += 1
        else:
            raise GuardError("unterminated JSON string token")


def _npm_rewrite_spans(path: Path, raw: str) -> list[tuple[int, int]]:
    """Return exactly the direct dependency-value spans safe to rewrite.

    The lexical edit preserves package.json formatting, but only when decoded
    JSON proves that every source-looking value token belongs to a recognised
    dependency table. An identical repository string in metadata or scripts is
    ambiguous without a full concrete-syntax tree, so the generic rewriter fails
    closed and lets a consumer-owned ``repin_cmd`` handle that unusual document.
    """

    data = _load_json(raw, where=path)
    semantic_sources: Counter[str] = Counter()
    for key, value in _dependency_specs(data):
        if not (_is_named_ncp(key) or _looks_like_ncp_npm(value)):
            continue
        if isinstance(value, str) and re.fullmatch(
            r"github:sepahead/NCP#[^\"#]+", value, re.ASCII
        ):
            semantic_sources[value] += 1

    spans: list[tuple[int, int]] = []
    lexical_sources: Counter[str] = Counter()
    for start, end, value in _json_string_tokens(raw):
        following = raw[end:].lstrip()
        is_key = following.startswith(":")
        if (
            not is_key
            and isinstance(value, str)
            and re.fullmatch(r"github:sepahead/NCP#[^\"#]+", value, re.ASCII)
        ):
            spans.append((start, end))
            lexical_sources[value] += 1

    if not semantic_sources:
        raise GuardError(f"{path}: no canonical NCP npm dependency source found")
    if lexical_sources != semantic_sources:
        raise GuardError(
            f"{path}: canonical NCP source strings occur outside direct dependency values; "
            "add a consumer repin_cmd"
        )
    return spans


def _rewrite_npm(path: Path, tag: str) -> None:
    _require_release(tag, where="target tag")
    raw = path.read_text(encoding="utf-8")
    _inspect_npm(path, bun_lock=False)
    replacements = [
        (start, end, json.dumps(f"github:sepahead/NCP#{tag}"))
        for start, end in _npm_rewrite_spans(path, raw)
    ]
    if not replacements:
        raise GuardError(f"{path}: no canonical NCP npm source found to rewrite")
    for start, end, value in reversed(replacements):
        raw = raw[:start] + value + raw[end:]
    _load_json(raw, where=path)
    # Semantic target verification happens on a temporary regular file to reuse the
    # complete dependency walker without weakening the atomic replacement.
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.verify.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(raw)
        evidence = _inspect_npm(Path(temporary), bun_lock=False)
        if evidence.tag != tag:
            raise GuardError(f"{path}: npm rewrite candidate did not converge on {tag}")
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    _atomic_write(path, raw)


def _preflight(base: Path) -> int:
    try:
        result = scan(base, repin_preflight=True)
    except GuardError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Shared NCP consumer-pin parser and guard"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-tag")
    validate.add_argument("tag")

    check = sub.add_parser("check")
    check.add_argument("base", type=Path)
    check.add_argument("--expected", default="")

    preflight = sub.add_parser("preflight")
    preflight.add_argument("base", type=Path)

    cargo = sub.add_parser("rewrite-cargo")
    cargo.add_argument("file", type=Path)
    cargo.add_argument("--mode", choices=("tag", "rev"), required=True)
    cargo.add_argument("--tag", required=True)
    cargo.add_argument("--revision")

    npm = sub.add_parser("rewrite-npm")
    npm.add_argument("file", type=Path)
    npm.add_argument("--tag", required=True)

    args = parser.parse_args()
    try:
        if args.command == "validate-tag":
            _require_release(args.tag, where="tag")
            return 0
        if args.command == "check":
            if not args.base.is_dir():
                print(
                    f"ERROR: base-dir {str(args.base)!r} is not a directory",
                    file=sys.stderr,
                )
                return 2
            return _render_check(args.base.resolve(), args.expected)
        if args.command == "preflight":
            return _preflight(args.base.resolve())
        if args.command == "rewrite-cargo":
            _rewrite_cargo(args.file, args.mode, args.tag, args.revision)
            return 0
        if args.command == "rewrite-npm":
            _rewrite_npm(args.file, args.tag)
            return 0
    except (GuardError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
