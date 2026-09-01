#!/usr/bin/env python3
"""Preflight one private B01 review bundle without admitting or retaining it."""

from __future__ import annotations

# Disable bytecode before any import can resolve a repository module.
# ruff: noqa: E402, I001
import os
import sys

os.environ["GIT_NO_LAZY_FETCH"] = "1"
os.environ["GIT_OPTIONAL_LOCKS"] = "0"
sys.dont_write_bytecode = True

import argparse
import copy
import json
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX hosts
    fcntl = None

import generate_b01_reviewer_kit as reviewer_kit

ROOT = Path(__file__).resolve().parents[1]
RESPONSE_MEMBER = "response.json"
EVIDENCE_PREFIX = "evidence/implementation/reviews/B01/"
MAX_BUNDLE_NODES = 2_048
MAX_BUNDLE_DEPTH = 32
MAX_COMPONENT_BYTES = 255
MAX_RELATIVE_BYTES = 512
MAX_ABSOLUTE_ROOT_BYTES = 4_096
MAX_ABSOLUTE_ROOT_COMPONENTS = 128
MAX_GIT_CONTROL_BYTES = 4_096
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600


class PrivateBundleError(RuntimeError):
    """The private bundle cannot produce a safe structural candidate."""


def fail(message: str) -> NoReturn:
    raise PrivateBundleError(message)


def _stat_fingerprint(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_uid,
        value.st_gid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_gid,
    )


def _object_identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _read_git_control_file(path: Path) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOCTTY", 0),
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 1 <= before.st_size <= MAX_GIT_CONTROL_BYTES
        ):
            fail("NCP Git metadata has an unsupported control-file shape")
        remaining = before.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                fail("NCP Git metadata ended before its opened byte size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            fail("NCP Git metadata grew beyond its opened byte size")
        raw = b"".join(chunks)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or _stat_fingerprint(before) != _stat_fingerprint(
            after
        ):
            fail("NCP Git metadata changed during private-bundle preflight")
        return raw
    except PrivateBundleError:
        raise
    except OSError as error:
        fail(f"cannot inspect NCP Git metadata (errno={error.errno})")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _git_control_path(raw: bytes, *, prefix: bytes, base: Path) -> Path:
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1 or not raw.startswith(prefix):
        fail("NCP Git metadata has a noncanonical control-file value")
    try:
        value = raw[len(prefix) : -1].decode("utf-8")
    except UnicodeDecodeError:
        fail("NCP Git metadata control path is not UTF-8")
    if not value or "\x00" in value:
        fail("NCP Git metadata control path is empty or malformed")
    path = Path(value)
    candidate = path if path.is_absolute() else base / path
    return Path(os.path.realpath(candidate))


def _protected_directory_objects() -> set[tuple[int, int]]:
    marker = ROOT / ".git"
    try:
        marker_stat = os.lstat(marker)
    except OSError as error:
        fail(f"cannot locate NCP Git metadata (errno={error.errno})")
    if stat.S_ISDIR(marker_stat.st_mode):
        git_directory = marker
    elif stat.S_ISREG(marker_stat.st_mode):
        git_directory = _git_control_path(
            _read_git_control_file(marker),
            prefix=b"gitdir: ",
            base=ROOT,
        )
    else:
        fail("NCP Git metadata marker is not a regular file or directory")

    common_control = git_directory / "commondir"
    try:
        common_stat = os.lstat(common_control)
    except FileNotFoundError:
        common_directory = git_directory
    except OSError as error:
        fail(f"cannot locate NCP common Git metadata (errno={error.errno})")
    else:
        if not stat.S_ISREG(common_stat.st_mode):
            fail("NCP common Git metadata marker is not a regular file")
        common_directory = _git_control_path(
            _read_git_control_file(common_control),
            prefix=b"",
            base=git_directory,
        )

    identities: set[tuple[int, int]] = set()
    for path in (ROOT, git_directory, common_directory):
        try:
            value = os.stat(path)
        except OSError as error:
            fail(f"cannot inspect a protected NCP directory (errno={error.errno})")
        if not stat.S_ISDIR(value.st_mode):
            fail("a protected NCP path is not a physical directory")
        identities.add(_object_identity(value))
    return identities


def _require_private_directory(value: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != DIRECTORY_MODE
    ):
        fail("bundle directories must be owner-owned mode 0700 physical directories")


def _require_private_file(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != FILE_MODE
        or value.st_nlink != 1
    ):
        fail("bundle leaves must be owner-owned mode 0600 single-link regular files")


def _directory_flags() -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if (
        fcntl is None
        or no_follow is None
        or directory is None
        or os.open not in os.supports_dir_fd
        or os.stat not in os.supports_dir_fd
        or os.stat not in os.supports_follow_symlinks
    ):
        fail("platform lacks required no-follow directory-descriptor operations")
    return os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)


def _reject_git_marker(directory_descriptor: int) -> None:
    try:
        os.stat(".git", dir_fd=directory_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as error:
        fail(f"cannot inspect a bundle ancestor for Git metadata (errno={error.errno})")
    fail("bundle root is inside a Git worktree or repository")


def _canonical_absolute_root(path: Path) -> tuple[Path, tuple[str, ...]]:
    try:
        raw = os.fspath(path)
    except TypeError:
        fail("bundle root must be one absolute physical path")
    if type(raw) is not str or not raw or "\x00" in raw:
        fail("bundle root must be one absolute physical path")
    try:
        encoded = raw.encode("utf-8")
    except UnicodeEncodeError:
        fail("bundle root must use valid UTF-8")
    absolute = Path(raw)
    parts = absolute.parts
    if (
        not 1 <= len(encoded) <= MAX_ABSOLUTE_ROOT_BYTES
        or not absolute.is_absolute()
        or len(parts) < 2
        or len(parts) - 1 > MAX_ABSOLUTE_ROOT_COMPONENTS
        or parts[0] != os.sep
        or os.path.abspath(raw) != raw
        or any(part in {"", ".", ".."} for part in parts[1:])
        or any(part.casefold() == ".git" for part in parts[1:])
        or any(len(part.encode("utf-8")) > MAX_COMPONENT_BYTES for part in parts[1:])
    ):
        fail("bundle root must be one canonical absolute path outside Git metadata")
    return absolute, tuple(parts[1:])


def _open_bundle_root(path: Path) -> tuple[int, Path, tuple[int, ...]]:
    absolute, parts = _canonical_absolute_root(path)
    flags = _directory_flags()
    protected = _protected_directory_objects()
    current = -1
    try:
        current = os.open(os.sep, flags)
        for component in parts:
            child = os.open(component, flags, dir_fd=current)
            opened = os.fstat(child)
            listed = os.stat(component, dir_fd=current, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or stat.S_ISLNK(listed.st_mode)
                or _directory_identity(opened) != _directory_identity(listed)
            ):
                os.close(child)
                fail("bundle root contains a symbolic or unstable ancestor")
            if _object_identity(opened) in protected:
                os.close(child)
                fail("bundle root is physically inside NCP or its Git metadata")
            try:
                _reject_git_marker(child)
            except PrivateBundleError:
                os.close(child)
                raise
            os.close(current)
            current = child
        _require_private_directory(os.fstat(current))
        fcntl.flock(current, fcntl.LOCK_SH | fcntl.LOCK_NB)
        return current, absolute, _directory_identity(os.fstat(current))
    except PrivateBundleError:
        if current >= 0:
            os.close(current)
        raise
    except OSError as error:
        if current >= 0:
            os.close(current)
        fail(f"cannot open and lock the private bundle root (errno={error.errno})")


def _rejoin_bundle_root(path: Path, expected: tuple[int, ...]) -> None:
    descriptor = -1
    try:
        descriptor, _absolute, observed = _open_bundle_root(path)
        if observed != expected:
            fail("bundle root changed during preflight")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _canonical_bundle_member(value: str) -> tuple[str, ...]:
    if type(value) is not str:
        fail("bundle member path must be canonical text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        fail("bundle member path must use valid UTF-8")
    candidate = PurePosixPath(value)
    if (
        not 1 <= len(encoded) <= MAX_RELATIVE_BYTES
        or candidate.is_absolute()
        or value != candidate.as_posix()
        or "\\" in value
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or any(part in {"", ".", ".."} for part in candidate.parts)
        or any(
            len(part.encode("utf-8")) > MAX_COMPONENT_BYTES for part in candidate.parts
        )
    ):
        fail("bundle member path is not one canonical relative POSIX path")
    return candidate.parts


def _open_member_parent(root_descriptor: int, relative: str) -> tuple[int, str]:
    parts = _canonical_bundle_member(relative)
    if len(parts) > MAX_BUNDLE_DEPTH:
        fail("bundle member path exceeds the directory-depth limit")
    flags = _directory_flags()
    current = os.dup(root_descriptor)
    child = -1
    try:
        for component in parts[:-1]:
            child = os.open(component, flags, dir_fd=current)
            opened = os.fstat(child)
            listed = os.stat(component, dir_fd=current, follow_symlinks=False)
            _require_private_directory(opened)
            if stat.S_ISLNK(listed.st_mode) or _directory_identity(
                opened
            ) != _directory_identity(listed):
                os.close(child)
                fail("bundle member has a symbolic or unstable directory")
            os.close(current)
            current = child
            child = -1
        return current, parts[-1]
    except PrivateBundleError:
        if child >= 0:
            os.close(child)
        os.close(current)
        raise
    except OSError as error:
        if child >= 0:
            os.close(child)
        os.close(current)
        fail(f"cannot open a private bundle member directory (errno={error.errno})")


def _read_member(
    root_descriptor: int,
    relative: str,
    *,
    maximum_bytes: int,
    phase_hook: Callable[[str], None] | None = None,
) -> tuple[bytes, tuple[int, ...]]:
    parent = -1
    descriptor = -1
    try:
        parent, leaf = _open_member_parent(root_descriptor, relative)
        before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        _require_private_file(before)
        if not 1 <= before.st_size <= maximum_bytes:
            fail("bundle member byte size is outside its closed bound")
        if phase_hook is not None:
            phase_hook(f"before-open:{relative}")
        descriptor = os.open(
            leaf,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOCTTY", 0),
            dir_fd=parent,
        )
        opened = os.fstat(descriptor)
        _require_private_file(opened)
        if _stat_fingerprint(opened) != _stat_fingerprint(before):
            fail("bundle member changed before its descriptor opened")
        remaining = opened.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                fail("bundle member ended before its opened byte size")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            fail("bundle member grew beyond its opened byte size")
        raw = b"".join(chunks)
        if phase_hook is not None:
            phase_hook(f"after-read:{relative}")
        after = os.fstat(descriptor)
        final = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        _require_private_file(after)
        _require_private_file(final)
        fingerprint = _stat_fingerprint(opened)
        if fingerprint != _stat_fingerprint(after) or fingerprint != _stat_fingerprint(
            final
        ):
            fail("bundle member or path changed during its read")
        return raw, fingerprint
    except PrivateBundleError:
        raise
    except OSError as error:
        fail(f"cannot read a private bundle member (errno={error.errno})")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent >= 0:
            os.close(parent)


def _expected_directories(files: set[str]) -> set[str]:
    directories: set[str] = set()
    for relative in files:
        parts = _canonical_bundle_member(relative)
        for end in range(1, len(parts)):
            directories.add(PurePosixPath(*parts[:end]).as_posix())
    return directories


def _inventory_tree(
    root_descriptor: int,
    expected_files: set[str],
) -> dict[str, tuple[int, ...]]:
    expected_directories = _expected_directories(expected_files)
    observed_files: dict[str, tuple[int, ...]] = {}
    observed_directories: set[str] = set()
    node_count = 0

    def visit(descriptor: int, prefix: tuple[str, ...]) -> None:
        nonlocal node_count
        if len(prefix) > MAX_BUNDLE_DEPTH:
            fail("bundle directory depth exceeds its closed bound")
        try:
            entries = os.scandir(descriptor)
            with entries:
                for entry in entries:
                    node_count += 1
                    if node_count > MAX_BUNDLE_NODES:
                        fail("bundle node count exceeds its closed bound")
                    name = entry.name
                    if (
                        type(name) is not str
                        or name in {"", ".", ".."}
                        or "/" in name
                        or "\\" in name
                        or len(name.encode("utf-8")) > MAX_COMPONENT_BYTES
                    ):
                        fail("bundle contains a noncanonical directory entry")
                    relative = PurePosixPath(*prefix, name).as_posix()
                    value = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                    if stat.S_ISLNK(value.st_mode):
                        fail("bundle contains a symbolic link")
                    if stat.S_ISDIR(value.st_mode):
                        if relative not in expected_directories:
                            fail("bundle contains an unreferenced directory")
                        _require_private_directory(value)
                        flags = _directory_flags()
                        child = os.open(name, flags, dir_fd=descriptor)
                        try:
                            opened = os.fstat(child)
                            _require_private_directory(opened)
                            if _directory_identity(opened) != _directory_identity(
                                value
                            ):
                                fail("bundle directory changed during inventory")
                            observed_directories.add(relative)
                            visit(child, (*prefix, name))
                            final = os.stat(
                                name, dir_fd=descriptor, follow_symlinks=False
                            )
                            if _directory_identity(final) != _directory_identity(
                                opened
                            ):
                                fail("bundle directory changed during inventory")
                        finally:
                            os.close(child)
                    elif stat.S_ISREG(value.st_mode):
                        if relative not in expected_files:
                            fail("bundle contains an unreferenced file")
                        _require_private_file(value)
                        observed_files[relative] = _stat_fingerprint(value)
                    else:
                        fail("bundle contains an unsupported special file")
        except PrivateBundleError:
            raise
        except (OSError, UnicodeError) as error:
            errno = error.errno if isinstance(error, OSError) else None
            fail(f"cannot inventory the private bundle (errno={errno})")

    visit(root_descriptor, ())
    if (
        set(observed_files) != expected_files
        or observed_directories != expected_directories
    ):
        fail("bundle tree differs from the exact response-derived roster")
    return observed_files


def _snapshot_bundle(
    root_descriptor: int,
    expected_files: set[str],
    *,
    phase_hook: Callable[[str], None] | None = None,
) -> tuple[dict[str, bytes], dict[str, tuple[int, ...]]]:
    inventory = _inventory_tree(root_descriptor, expected_files)
    raw: dict[str, bytes] = {}
    aggregate = 0
    for relative in sorted(expected_files):
        maximum = (
            reviewer_kit.MAX_RESPONSE_BYTES
            if relative == RESPONSE_MEMBER
            else 1024 * 1024
        )
        content, fingerprint = _read_member(
            root_descriptor,
            relative,
            maximum_bytes=maximum,
            phase_hook=phase_hook,
        )
        if fingerprint != inventory[relative]:
            fail("bundle member changed after inventory")
        raw[relative] = content
        if relative != RESPONSE_MEMBER:
            aggregate += len(content)
            if aggregate > reviewer_kit.MAX_EVIDENCE_BUNDLE_BYTES:
                fail("bundle evidence exceeds the 16 MiB aggregate limit")
    return raw, inventory


def _response_paths(response: dict[str, Any]) -> set[str]:
    paths = set()
    for reference in reviewer_kit.response_evidence_references(response):
        relative = reference["path"]
        parts = _canonical_bundle_member(relative)
        if not relative.startswith(EVIDENCE_PREFIX) or parts[:4] != (
            "evidence",
            "implementation",
            "reviews",
            "B01",
        ):
            fail("response evidence path leaves the private B01 bundle namespace")
        paths.add(relative)
    return paths


def preflight_bundle(
    bundle_root: Path,
    *,
    phase_hook: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    root_descriptor = -1
    stage = "BUNDLE_ROOT"
    try:
        root_descriptor, absolute_root, root_identity = _open_bundle_root(bundle_root)
        stage = "RESPONSE_SCHEMA"
        initial_response, _ = _read_member(
            root_descriptor,
            RESPONSE_MEMBER,
            maximum_bytes=reviewer_kit.MAX_RESPONSE_BYTES,
            phase_hook=phase_hook,
        )
        response = reviewer_kit.parse_object(
            initial_response,
            "private response.json",
            reviewer_kit.MAX_RESPONSE_BYTES,
        )
        stage = "LOCAL_CONTEXT"
        kit = reviewer_kit.build_kit()
        reviewer_kit.require_retained_kit(kit, reviewer_kit.generated_bytes(kit))
        reviewer_kit.validate_current_review_capture(kit)
        stage = "RESPONSE_SCHEMA"
        response_schema_raw = reviewer_kit.read_file(
            reviewer_kit.RESPONSE_SCHEMA_RELATIVE,
            reviewer_kit.MAX_SCHEMA_BYTES,
        )
        response_schema = reviewer_kit.parse_object(
            response_schema_raw,
            reviewer_kit.RESPONSE_SCHEMA_RELATIVE,
            reviewer_kit.MAX_SCHEMA_BYTES,
        )
        reviewer_kit.schema_validate(
            response_schema,
            response,
            "private B01 response",
            reviewer_kit.RESPONSE_SCHEMA_ID,
        )
        stage = "EVIDENCE_ROSTER"
        expected_files = {RESPONSE_MEMBER, *_response_paths(response)}
        first_raw, first_inventory = _snapshot_bundle(
            root_descriptor,
            expected_files,
            phase_hook=phase_hook,
        )
        if first_raw[RESPONSE_MEMBER] != initial_response:
            fail("response.json changed before the complete bundle snapshot")
        overrides = {
            relative: content
            for relative, content in first_raw.items()
            if relative != RESPONSE_MEMBER
        }
        stage = "SUBJECT_BINDING"
        matching_slots = [
            slot for slot in kit["slots"] if slot["slot_id"] == response.get("slot_id")
        ]
        if (
            len(matching_slots) != 1
            or response.get("subject_binding") != matching_slots[0]["subject_binding"]
        ):
            fail("SUBJECT_BINDING: response does not bind one current slot")
        stage = "EVIDENCE_IDENTITY"
        reviewer_kit.evidence_bundle_value(response, overrides)
        stage = "REGISTRY_REPLAY"
        candidate = reviewer_kit.materialize_private_response(
            first_raw[RESPONSE_MEMBER],
            response,
            kit,
            overrides,
        )
        if phase_hook is not None:
            phase_hook("candidate-ready")
        stage = "BUNDLE_STABILITY"
        second_raw, second_inventory = _snapshot_bundle(
            root_descriptor,
            expected_files,
            phase_hook=phase_hook,
        )
        if first_raw != second_raw or first_inventory != second_inventory:
            fail("private bundle changed during structural preflight")
        _rejoin_bundle_root(absolute_root, root_identity)
        return candidate
    except reviewer_kit.ReviewerKitError:
        fail(f"{stage}: checked review operation failed closed")
    finally:
        if root_descriptor >= 0:
            os.close(root_descriptor)


def _write_private(root: Path, path: Path, content: bytes) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        fail("self-test output escaped its private fixture root")
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        current.mkdir(mode=DIRECTORY_MODE, exist_ok=True)
        current.chmod(DIRECTORY_MODE)
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
        FILE_MODE,
    )
    try:
        os.write(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fixture(kit: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    role = b'{"kind":"role-authorization"}\n'
    receipt = b'{"kind":"external-review-receipt"}\n'
    response = {
        "schema": reviewer_kit.RESPONSE_SCHEMA,
        "slot_id": kit["slots"][0]["slot_id"],
        "subject_binding": copy.deepcopy(kit["slots"][0]["subject_binding"]),
        "review_id": "private-preflight-self-test",
        "reviewer": {
            "identity": "urn:example:human-reviewer",
            "identity_kind": "PERSON",
            "independence_claimed": False,
            "implementation_owner_identities": ["urn:example:ncp-owner"],
        },
        "decision": "REJECT",
        "conditions": [],
        "role_authorization": {
            "url": "https://review.example/role/self-test",
            "path": "evidence/implementation/reviews/B01/role-self-test.json",
            "sha256": reviewer_kit.sha256(role),
            "bytes": len(role),
            "media_type": "application/json",
        },
        "independence_assessment": None,
        "external_receipt": {
            "url": "https://review.example/receipt/self-test",
            "path": "evidence/implementation/reviews/B01/receipt-self-test.json",
            "sha256": reviewer_kit.sha256(receipt),
            "bytes": len(receipt),
            "media_type": "application/json",
        },
        "timestamp_utc": "2026-09-01T12:00:00Z",
        "supersedes": None,
    }
    return response, {
        response["role_authorization"]["path"]: role,
        response["external_receipt"]["path"]: receipt,
    }


def _install_fixture(
    root: Path,
    response: dict[str, Any],
    evidence: dict[str, bytes],
    *,
    response_raw: bytes | None = None,
) -> None:
    root.chmod(DIRECTORY_MODE)
    _write_private(
        root,
        root / RESPONSE_MEMBER,
        reviewer_kit.generated_bytes(response)
        if response_raw is None
        else response_raw,
    )
    for relative, content in evidence.items():
        _write_private(root, root / relative, content)


def _must_fail(
    action: Callable[[], Any],
    label: str,
    expected_message: str | None = None,
) -> None:
    try:
        action()
    except PrivateBundleError as error:
        if expected_message is not None and expected_message not in str(error):
            fail(f"{label} failed without the expected bounded diagnostic")
        return
    fail(f"hostile private-bundle self-test unexpectedly passed: {label}")


def _case_alias(path: Path) -> Path | None:
    parts = list(path.parts)
    for index, component in enumerate(parts[1:], start=1):
        for character_index, character in enumerate(component):
            if not character.isascii() or not character.isalpha():
                continue
            changed = (
                component[:character_index]
                + character.swapcase()
                + component[character_index + 1 :]
            )
            candidate_parts = [*parts]
            candidate_parts[index] = changed
            candidate = Path(candidate_parts[0], *candidate_parts[1:])
            try:
                if candidate != path and os.path.samefile(candidate, path):
                    return candidate
            except OSError:
                pass
    return None


def _must_reject_protected_path(path: Path, label: str) -> None:
    try:
        descriptor, _absolute, _identity = _open_bundle_root(path)
    except PrivateBundleError as error:
        if str(error) != "bundle root is physically inside NCP or its Git metadata":
            fail(f"{label} failed for the wrong reason")
        return
    os.close(descriptor)
    fail(f"hostile protected-path self-test unexpectedly passed: {label}")


def self_test() -> None:
    kit = reviewer_kit.build_kit()
    reviewer_kit.require_retained_kit(kit, reviewer_kit.generated_bytes(kit))
    response, evidence = _fixture(kit)
    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        first = preflight_bundle(root)
        second = preflight_bundle(root)
        if reviewer_kit.generated_bytes(first) != reviewer_kit.generated_bytes(second):
            fail("repeated exact-bundle preflight is not deterministic")
        expected_raw = reviewer_kit.raw_response_identity(
            reviewer_kit.generated_bytes(response)
        )
        if first["response_identity"]["raw"] != expected_raw:
            fail("candidate raw response identity differs from independent hashing")

    spaced = reviewer_kit.generated_bytes(response).rstrip() + b" \n"
    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence, response_raw=spaced)
        changed = preflight_bundle(root)
        if (
            changed["response_identity"]["raw"]["sha256"]
            == first["response_identity"]["raw"]["sha256"]
            or changed["response_identity"]["semantic"]
            != first["response_identity"]["semantic"]
        ):
            fail("raw and semantic response identities do not separate byte spelling")

    hostile = copy.deepcopy(response)
    hostile["subject_binding"]["sha256"] = "0" * 64
    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, hostile, evidence)
        _must_fail(
            lambda: preflight_bundle(root),
            "wrong subject binding",
            "SUBJECT_BINDING",
        )

    hostile = copy.deepcopy(response)
    hostile["schema"] = "ncp.b01-review-response.v1"
    del hostile["subject_binding"]
    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, hostile, evidence)
        _must_fail(
            lambda: preflight_bundle(root),
            "v1 response rejection",
            "RESPONSE_SCHEMA",
        )

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        changed_evidence = dict(evidence)
        changed_evidence[response["external_receipt"]["path"]] += b" "
        _install_fixture(root, response, changed_evidence)
        _must_fail(
            lambda: preflight_bundle(root),
            "evidence identity mismatch",
            "EVIDENCE_IDENTITY",
        )

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        missing = dict(evidence)
        missing.pop(next(iter(missing)))
        _install_fixture(root, response, missing)
        _must_fail(lambda: preflight_bundle(root), "missing evidence")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        _write_private(root, root / "extra.json", b"{}\n")
        _must_fail(lambda: preflight_bundle(root), "unreferenced file")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        alias = root / "response-alias.json"
        os.link(root / RESPONSE_MEMBER, alias)
        _must_fail(lambda: preflight_bundle(root), "hard-linked response")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        receipt = root / response["external_receipt"]["path"]
        replacement = root / "private-receipt.json"
        receipt.rename(replacement)
        receipt.symlink_to(replacement)
        _must_fail(lambda: preflight_bundle(root), "symbolic evidence leaf")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        (root / RESPONSE_MEMBER).chmod(0o640)
        _must_fail(lambda: preflight_bundle(root), "non-private response mode")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        root.chmod(0o750)
        _must_fail(lambda: preflight_bundle(root), "non-private bundle-root mode")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        receipt = root / response["external_receipt"]["path"]
        receipt.unlink()
        os.mkfifo(receipt, mode=FILE_MODE)
        _must_fail(lambda: preflight_bundle(root), "FIFO evidence leaf")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        replaced = False

        def replace_response_with_fifo(phase: str) -> None:
            nonlocal replaced
            if phase == f"before-open:{RESPONSE_MEMBER}" and not replaced:
                replaced = True
                target = root / RESPONSE_MEMBER
                target.unlink()
                os.mkfifo(target, mode=FILE_MODE)

        _must_fail(
            lambda: preflight_bundle(root, phase_hook=replace_response_with_fifo),
            "pre-open FIFO response replacement",
        )
        if not replaced:
            fail("pre-open FIFO replacement self-test hook did not execute")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        replaced = False

        def replace_response_file(phase: str) -> None:
            nonlocal replaced
            if phase == f"before-open:{RESPONSE_MEMBER}" and not replaced:
                replaced = True
                target = root / RESPONSE_MEMBER
                raw = target.read_bytes()
                target.unlink()
                _write_private(root, target, raw)

        _must_fail(
            lambda: preflight_bundle(root, phase_hook=replace_response_file),
            "pre-open regular response replacement",
        )
        if not replaced:
            fail("pre-open regular replacement self-test hook did not execute")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        replaced = False

        def replace_response_after_read(phase: str) -> None:
            nonlocal replaced
            if phase == f"after-read:{RESPONSE_MEMBER}" and not replaced:
                replaced = True
                target = root / RESPONSE_MEMBER
                raw = target.read_bytes()
                target.unlink()
                _write_private(root, target, raw)

        _must_fail(
            lambda: preflight_bundle(root, phase_hook=replace_response_after_read),
            "post-read regular response replacement",
        )
        if not replaced:
            fail("post-read regular replacement self-test hook did not execute")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        evidence_directory = root / "evidence"
        replacement = root / "private-evidence"
        evidence_directory.rename(replacement)
        evidence_directory.symlink_to(replacement.name, target_is_directory=True)
        _must_fail(lambda: preflight_bundle(root), "symbolic evidence directory")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        parent = Path(os.path.realpath(temporary))
        root = parent / "bundle"
        root.mkdir(mode=DIRECTORY_MODE)
        _install_fixture(root, response, evidence)
        alias = parent / "bundle-link"
        alias.symlink_to(root.name, target_is_directory=True)
        _must_fail(lambda: preflight_bundle(alias), "symbolic bundle root")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        root = Path(os.path.realpath(temporary))
        _install_fixture(root, response, evidence)
        mutated = False

        def mutate_after_candidate(phase: str) -> None:
            nonlocal mutated
            if phase == "candidate-ready" and not mutated:
                mutated = True
                target = root / response["external_receipt"]["path"]
                target.write_bytes(target.read_bytes() + b" ")
                target.chmod(FILE_MODE)

        _must_fail(
            lambda: preflight_bundle(root, phase_hook=mutate_after_candidate),
            "post-candidate bundle mutation",
        )
        if not mutated:
            fail("bundle mutation self-test hook did not execute")

    _must_fail(lambda: preflight_bundle(Path("relative")), "relative bundle root")
    _must_fail(
        lambda: _canonical_bundle_member(f"{EVIDENCE_PREFIX}line\nbreak.json"),
        "newline in evidence path",
    )
    _must_fail(
        lambda: _canonical_bundle_member(f"{EVIDENCE_PREFIX}nul\x00byte.json"),
        "NUL in evidence path",
    )
    _must_fail(
        lambda: preflight_bundle(Path(os.sep, *("x" for _ in range(129)))),
        "over-deep absolute bundle root",
    )
    _must_reject_protected_path(ROOT, "direct repository root")
    _must_reject_protected_path(ROOT / "evidence", "direct repository descendant")
    case_alias = _case_alias(ROOT)
    if case_alias is not None:
        _must_reject_protected_path(case_alias, "case-aliased repository root")

    with tempfile.TemporaryDirectory(prefix="ncp-b01-preflight-") as temporary:
        parent = Path(os.path.realpath(temporary))
        worktree = parent / "other-worktree"
        worktree.mkdir(mode=DIRECTORY_MODE)
        _write_private(worktree, worktree / ".git", b"gitdir: elsewhere\n")
        root = worktree / "private-bundle"
        root.mkdir(mode=DIRECTORY_MODE)
        _install_fixture(root, response, evidence)
        _must_fail(
            lambda: preflight_bundle(root),
            "bundle inside another Git worktree",
            "inside a Git worktree or repository",
        )


def print_candidate(candidate: dict[str, Any]) -> None:
    print(json.dumps(candidate, ensure_ascii=True, sort_keys=True, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bundle",
        type=Path,
        help="absolute owner-mode-restricted off-repository review bundle",
    )
    parser.add_argument("--self-test", action="store_true", help="run hostile controls")
    args = parser.parse_args()
    if args.bundle is None and not args.self_test:
        parser.error("one of --bundle or --self-test is required")
    try:
        if args.self_test:
            self_test()
        if args.bundle is not None:
            candidate = preflight_bundle(args.bundle)
            print(
                "SENSITIVE UNAUTHENTICATED CANDIDATE — use only in the private "
                "external-verifier channel; no admission or authority",
                file=sys.stderr,
            )
            print_candidate(candidate)
        elif args.self_test:
            print("B01 private-bundle preflight self-test: PASS")
        return 0
    except PrivateBundleError as error:
        print(f"B01 private-bundle preflight failed: {error}", file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ValueError):
        print(
            "B01 private-bundle preflight failed: private input or local I/O "
            "failed closed",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
