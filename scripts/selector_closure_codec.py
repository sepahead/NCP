#!/usr/bin/env python3
"""Deterministic codec for the non-normative B01 selector-closure source.

This module owns only the compact JSON representation. It does not construct or
validate the selector semantics.
"""

from __future__ import annotations

import copy
import fcntl
import json
import math
import os
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any, NoReturn

# A complete 1.0 allocation oracle exceeds 2 MiB after its required typed
# exclusions. Four MiB retains a bounded read while leaving reviewed growth
# margin below the independent 16 MiB expanded-document ceiling.
MAX_COMPACT_BYTES = 4 * 1024 * 1024
MAX_EXPANDED_BYTES = 16 * 1024 * 1024
MAX_TABLE_ITEMS = 0x10000
# The JSON document root is depth 0. Each array element or object member value
# increments the depth by one. Object member names are not JSON value nodes.
MAX_JSON_DEPTH = 64
MAX_JSON_ITEMS = 1_000_000
MAX_JSON_NUMBER_CHARS = 128
MAX_JSON_STRING_CHARS = 8192
MAX_JSON_TOTAL_STRING_CHARS = MAX_EXPANDED_BYTES

COMPACT_SCHEMA_FILE = "selector-closure.source.schema.v1.json"
COMPACT_SCHEMA_ID = "ncp.b01-selector-closure-source.compact.v1"
ENCODING_KIND = "REPEATED_STRING_AND_SUBTREE_TABLE_V1"
STRING_REFERENCE_PATTERN = r"^@S[0-9A-F]{4}$"
OBJECT_REFERENCE_PATTERN = r"^@O[0-9A-F]{4}$"
STRING_TOKEN = re.compile(STRING_REFERENCE_PATTERN)
OBJECT_TOKEN = re.compile(OBJECT_REFERENCE_PATTERN)
_Metric = tuple[int, int, int, int]

ENVELOPE_KEYS = {
    "$schema",
    "candidate",
    "encoding",
    "normative",
    "payload",
    "schema",
    "task",
}
ENCODING_KEYS = {
    "expanded_document_sha256",
    "kind",
    "object_minimum_canonical_utf8_bytes",
    "object_minimum_repetition",
    "object_table",
    "object_table_sha256",
    "object_token_pattern",
    "string_minimum_length",
    "string_minimum_repetition",
    "string_table",
    "string_table_sha256",
    "string_token_pattern",
}


class SelectorClosureError(Exception):
    """Base class for deterministic codec and indeterminate write failures."""


class SelectorClosureCodecError(ValueError, SelectorClosureError):
    """The compact representation is malformed or exceeds a resource limit."""


class AtomicWriteOutcomeUnknownError(RuntimeError, SelectorClosureError):
    """A write may have crossed install but final identity is unproved."""


def _fail(message: str) -> NoReturn:
    raise SelectorClosureCodecError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _require_exact(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        _fail(f"{label}: expected {expected!r}, got {actual!r}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON contains duplicate object key {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_number(value: str) -> NoReturn:
    _fail(f"JSON contains non-finite number {value!r}")


def _parse_finite_float(value: str) -> float:
    _require(
        len(value) <= MAX_JSON_NUMBER_CHARS,
        f"JSON number exceeds {MAX_JSON_NUMBER_CHARS} characters",
    )
    try:
        decimal_value = Decimal(value)
        parsed = float(value)
    except (InvalidOperation, OverflowError, ValueError) as error:
        _fail(f"JSON contains invalid finite number {value!r}: {error}")
    if not decimal_value.is_finite() or not math.isfinite(parsed):
        _reject_nonfinite_number(value)
    _require(
        decimal_value.is_zero() or parsed != 0.0,
        f"JSON number underflows the bounded float representation: {value!r}",
    )
    return parsed


def _parse_bounded_int(value: str) -> int:
    _require(
        len(value) <= MAX_JSON_NUMBER_CHARS,
        f"JSON integer exceeds {MAX_JSON_NUMBER_CHARS} characters",
    )
    try:
        return int(value)
    except (OverflowError, ValueError) as error:
        _fail(f"JSON contains invalid integer {value!r}: {error}")


def _preflight_json_text(
    text: str,
    *,
    label: str,
    maximum_depth: int = MAX_JSON_DEPTH,
    maximum_items: int = MAX_JSON_ITEMS,
    maximum_number_chars: int = MAX_JSON_NUMBER_CHARS,
    maximum_string_chars: int = MAX_JSON_STRING_CHARS,
    maximum_total_string_chars: int = MAX_JSON_TOTAL_STRING_CHARS,
) -> None:
    """Bound JSON tokens and nesting before the JSON parser allocates.

    String quotas count decoded Python characters, not JSON escape syntax.
    A contiguous escaped UTF-16 surrogate pair therefore counts as one
    character, exactly as it does after ``json.loads``.
    """

    depth = 0
    in_string = False
    escaped = False
    unicode_escape_digits = 0
    unicode_escape_value = 0
    pending_high_surrogate = False
    in_atom = False
    atom_is_number = False
    atom_chars = 0
    item_count = 0
    string_chars = 0
    total_string_chars = 0
    for character in text:
        if in_string:
            if unicode_escape_digits:
                _require(
                    character in "0123456789abcdefABCDEF",
                    f"{label}: JSON string contains an invalid Unicode escape",
                )
                unicode_escape_value = unicode_escape_value * 16 + int(character, 16)
                unicode_escape_digits -= 1
                if unicode_escape_digits == 0:
                    if pending_high_surrogate:
                        if 0xDC00 <= unicode_escape_value <= 0xDFFF:
                            string_chars += 1
                            pending_high_surrogate = False
                        else:
                            string_chars += 1
                            pending_high_surrogate = False
                            if 0xD800 <= unicode_escape_value <= 0xDBFF:
                                pending_high_surrogate = True
                            else:
                                string_chars += 1
                    elif 0xD800 <= unicode_escape_value <= 0xDBFF:
                        pending_high_surrogate = True
                    else:
                        string_chars += 1
                    unicode_escape_value = 0
                    _require(
                        string_chars <= maximum_string_chars,
                        f"{label}: JSON string exceeds "
                        f"{maximum_string_chars} characters",
                    )
            elif escaped:
                escaped = False
                if character == "u":
                    unicode_escape_digits = 4
                    unicode_escape_value = 0
                else:
                    _require(
                        character in '"\\/bfnrt',
                        f"{label}: JSON string contains an invalid escape",
                    )
                    if pending_high_surrogate:
                        string_chars += 1
                        pending_high_surrogate = False
                    string_chars += 1
                    _require(
                        string_chars <= maximum_string_chars,
                        f"{label}: JSON string exceeds "
                        f"{maximum_string_chars} characters",
                    )
            elif character == "\\":
                escaped = True
            elif character == '"':
                if pending_high_surrogate:
                    string_chars += 1
                    pending_high_surrogate = False
                in_string = False
                total_string_chars += string_chars
                _require(
                    string_chars <= maximum_string_chars,
                    f"{label}: JSON string exceeds {maximum_string_chars} characters",
                )
                _require(
                    total_string_chars <= maximum_total_string_chars,
                    f"{label}: total JSON string content exceeds "
                    f"{maximum_total_string_chars} characters",
                )
                string_chars = 0
            else:
                if pending_high_surrogate:
                    string_chars += 1
                    pending_high_surrogate = False
                string_chars += 1
                _require(
                    string_chars <= maximum_string_chars,
                    f"{label}: JSON string exceeds {maximum_string_chars} characters",
                )
            continue
        if in_atom:
            if character.isspace() or character in ",]}:":
                in_atom = False
                atom_is_number = False
                atom_chars = 0
            else:
                atom_chars += 1
                if atom_is_number:
                    _require(
                        atom_chars <= maximum_number_chars,
                        f"{label}: JSON number exceeds "
                        f"{maximum_number_chars} characters",
                    )
                continue
        if character == '"':
            in_string = True
            item_count += 1
            _require(
                item_count <= maximum_items,
                f"{label}: JSON item count exceeds {maximum_items}",
            )
            _require(
                depth <= maximum_depth,
                f"{label}: JSON nesting exceeds {maximum_depth}",
            )
            continue
        if character in "[{":
            _require(
                depth <= maximum_depth,
                f"{label}: JSON nesting exceeds {maximum_depth}",
            )
            depth += 1
            item_count += 1
            _require(
                item_count <= maximum_items,
                f"{label}: JSON item count exceeds {maximum_items}",
            )
        elif character in "]}":
            depth -= 1
            _require(depth >= 0, f"{label}: unmatched closing delimiter")
        elif not character.isspace() and character not in ",:":
            in_atom = True
            atom_is_number = character in "-0123456789"
            atom_chars = 1
            item_count += 1
            _require(
                item_count <= maximum_items,
                f"{label}: JSON item count exceeds {maximum_items}",
            )
            _require(
                depth <= maximum_depth,
                f"{label}: JSON nesting exceeds {maximum_depth}",
            )
            if atom_is_number:
                _require(
                    atom_chars <= maximum_number_chars,
                    f"{label}: JSON number exceeds {maximum_number_chars} characters",
                )
    _require(
        not in_string
        and not escaped
        and unicode_escape_digits == 0
        and not pending_high_surrogate,
        f"{label}: unterminated JSON string",
    )
    _require(depth == 0, f"{label}: unbalanced JSON delimiters")


def validate_json_resource_bounds(
    value: Any,
    *,
    label: str,
    maximum_depth: int = MAX_JSON_DEPTH,
    maximum_items: int = MAX_JSON_ITEMS,
    maximum_number_chars: int = MAX_JSON_NUMBER_CHARS,
    maximum_string_chars: int = MAX_JSON_STRING_CHARS,
    maximum_total_string_chars: int = MAX_JSON_TOTAL_STRING_CHARS,
) -> None:
    """Require a bounded native JSON tree without recursive traversal."""

    stack: list[tuple[Any, int]] = [(value, 0)]
    mutable_seen: set[int] = set()
    item_count = 0
    string_chars = 0
    while stack:
        item, depth = stack.pop()
        item_type = type(item)
        item_count += 1
        _require(
            item_count <= maximum_items,
            f"{label}: JSON item count exceeds {maximum_items}",
        )
        _require(
            depth <= maximum_depth,
            f"{label}: JSON nesting exceeds {maximum_depth}",
        )
        if item_type is str:
            _require(
                len(item) <= maximum_string_chars,
                f"{label}: JSON string exceeds {maximum_string_chars} characters",
            )
            try:
                item.encode("utf-8")
            except UnicodeEncodeError as error:
                _fail(f"{label}: JSON string is not Unicode scalar text: {error}")
            string_chars += len(item)
        elif item_type is list:
            identity = id(item)
            _require(
                identity not in mutable_seen,
                f"{label}: JSON tree shares a mutable array",
            )
            mutable_seen.add(identity)
            _require(
                item_count + len(stack) + len(item) <= maximum_items,
                f"{label}: JSON item count exceeds {maximum_items}",
            )
            stack.extend((child, depth + 1) for child in item)
        elif item_type is dict:
            identity = id(item)
            _require(
                identity not in mutable_seen,
                f"{label}: JSON tree shares a mutable object",
            )
            mutable_seen.add(identity)
            _require(
                item_count + len(stack) + 2 * len(item) <= maximum_items,
                f"{label}: JSON item count exceeds {maximum_items}",
            )
            for key, child in item.items():
                _require(
                    type(key) is str,
                    f"{label}: JSON object key is not a string",
                )
                _require(
                    len(key) <= maximum_string_chars,
                    f"{label}: JSON object key exceeds "
                    f"{maximum_string_chars} characters",
                )
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as error:
                    _fail(
                        f"{label}: JSON object key is not Unicode scalar text: {error}"
                    )
                item_count += 1
                string_chars += len(key)
                _require(
                    string_chars <= maximum_total_string_chars,
                    f"{label}: total JSON string content exceeds "
                    f"{maximum_total_string_chars} characters",
                )
                stack.append((child, depth + 1))
        elif item_type is bool or item is None:
            pass
        elif item_type is int:
            try:
                encoded_number = str(item)
            except (ValueError, MemoryError) as error:
                _fail(f"{label}: JSON integer cannot be bounded: {error}")
            _require(
                len(encoded_number) <= maximum_number_chars,
                f"{label}: JSON integer exceeds {maximum_number_chars} characters",
            )
        elif item_type is float:
            _require(
                math.isfinite(item),
                f"{label}: JSON contains a non-finite number",
            )
            encoded_number = json.dumps(item, allow_nan=False)
            _require(
                len(encoded_number) <= maximum_number_chars,
                f"{label}: JSON number exceeds {maximum_number_chars} characters",
            )
        else:
            _fail(f"{label}: value of type {type(item).__name__!r} is not a JSON value")
        _require(
            item_count <= maximum_items,
            f"{label}: JSON item count exceeds {maximum_items}",
        )
        _require(
            string_chars <= maximum_total_string_chars,
            f"{label}: total JSON string content exceeds "
            f"{maximum_total_string_chars} characters",
        )


def parse_json_bytes(
    raw: bytes,
    *,
    label: str,
    maximum_bytes: int = MAX_EXPANDED_BYTES,
    maximum_depth: int = MAX_JSON_DEPTH,
    maximum_items: int = MAX_JSON_ITEMS,
    maximum_number_chars: int = MAX_JSON_NUMBER_CHARS,
    maximum_string_chars: int = MAX_JSON_STRING_CHARS,
    maximum_total_string_chars: int = MAX_JSON_TOTAL_STRING_CHARS,
) -> Any:
    """Parse bounded UTF-8 JSON and reject duplicate keys and non-finite values."""

    _require(type(raw) is bytes, f"{label}: JSON input must be native bytes")
    limits = {
        "maximum_bytes": maximum_bytes,
        "maximum_depth": maximum_depth,
        "maximum_items": maximum_items,
        "maximum_number_chars": maximum_number_chars,
        "maximum_string_chars": maximum_string_chars,
        "maximum_total_string_chars": maximum_total_string_chars,
    }
    for name, value in limits.items():
        _require(
            type(value) is int and value > 0,
            f"{label}: {name} must be a positive native integer",
        )
    _require(raw, f"{label}: JSON input is empty")
    _require(
        len(raw) <= maximum_bytes,
        f"{label}: JSON input exceeds {maximum_bytes} bytes",
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail(f"{label}: invalid UTF-8: {error}")
    _preflight_json_text(
        text,
        label=label,
        maximum_depth=maximum_depth,
        maximum_items=maximum_items,
        maximum_number_chars=maximum_number_chars,
        maximum_string_chars=maximum_string_chars,
        maximum_total_string_chars=maximum_total_string_chars,
    )
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite_number,
            parse_float=_parse_finite_float,
            parse_int=_parse_bounded_int,
        )
    except (json.JSONDecodeError, RecursionError) as error:
        _fail(f"{label}: invalid JSON: {error}")
    validate_json_resource_bounds(
        parsed,
        label=label,
        maximum_depth=maximum_depth,
        maximum_items=maximum_items,
        maximum_number_chars=maximum_number_chars,
        maximum_string_chars=maximum_string_chars,
        maximum_total_string_chars=maximum_total_string_chars,
    )
    return parsed


PathIOPhaseHook = Callable[[str], None]


def _stat_fingerprint(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_fingerprint(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        stat.S_IFMT(value.st_mode),
    )


def _require_managed_directory(
    descriptor: int,
    *,
    label: str,
) -> os.stat_result:
    """Require the local cooperative-writer boundary used by this codec."""

    value = os.fstat(descriptor)
    _require(stat.S_ISDIR(value.st_mode), f"{label}: parent is not a directory")
    _require(
        value.st_uid in {0, os.geteuid()},
        f"{label}: parent owner is not trusted",
    )
    _require(
        value.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0,
        f"{label}: group/world-writable parent is unsupported",
    )
    return value


def _require_managed_regular_file(
    value: os.stat_result,
    *,
    label: str,
) -> None:
    _require(stat.S_ISREG(value.st_mode), f"{label}: expected a regular file")
    _require(value.st_nlink == 1, f"{label}: hard-linked file is unsupported")
    _require(
        value.st_uid in {0, os.geteuid()},
        f"{label}: file owner is not trusted",
    )
    _require(
        value.st_mode & (stat.S_IWGRP | stat.S_IWOTH) == 0,
        f"{label}: group/world-writable file is unsupported",
    )


def _read_exact_descriptor(
    descriptor: int,
    expected_size: int,
    *,
    label: str,
) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = expected_size
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        _require(chunk, f"{label}: file ended before its opened size")
        chunks.append(chunk)
        remaining -= len(chunk)
    _require(
        os.read(descriptor, 1) == b"",
        f"{label}: file exceeds its opened size",
    )
    return b"".join(chunks)


def _absolute_path_parts(path: Path, *, label: str) -> tuple[Path, tuple[str, ...]]:
    try:
        raw_path = os.fspath(path)
    except TypeError as error:
        _fail(f"{label}: invalid path value: {error}")
    _require(isinstance(raw_path, str), f"{label}: path must be text")
    _require(raw_path != "", f"{label}: empty path is forbidden")
    _require("\x00" not in raw_path, f"{label}: NUL in path is forbidden")
    try:
        absolute_path = Path(os.path.abspath(raw_path))
    except (OSError, TypeError, ValueError) as error:
        _fail(f"{label}: cannot resolve path: {error}")
    parts = absolute_path.parts
    _require(
        absolute_path.is_absolute() and len(parts) >= 2 and parts[0] == os.sep,
        f"{label}: unsupported non-POSIX path {path}",
    )
    relative_parts = tuple(parts[1:])
    _require(
        all(part not in {"", ".", ".."} for part in relative_parts),
        f"{label}: invalid path component in {path}",
    )
    return absolute_path, relative_parts


def _directory_open_flags(*, label: str) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    _require(
        no_follow is not None and directory is not None,
        f"{label}: platform lacks fail-closed directory open flags",
    )
    _require(
        os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks,
        f"{label}: platform lacks fail-closed dirfd operations",
    )
    return os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)


def _open_anchored_parent_directory(
    path: Path,
    *,
    label: str,
) -> tuple[int, Path, str, tuple[tuple[int, ...], ...]]:
    """Walk from the filesystem root without following an ancestor symlink."""

    absolute_path, parts = _absolute_path_parts(path, label=label)
    _require(parts, f"{label}: filesystem root is not a file path")
    directory_flags = _directory_open_flags(label=label)
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.sep, directory_flags))
        fingerprints = [_directory_fingerprint(os.fstat(descriptors[-1]))]
        for component in parts[:-1]:
            next_descriptor = os.open(
                component,
                directory_flags,
                dir_fd=descriptors[-1],
            )
            descriptors.append(next_descriptor)
            opened = os.fstat(next_descriptor)
            listed = os.stat(
                component,
                dir_fd=descriptors[-2],
                follow_symlinks=False,
            )
            _require(
                stat.S_ISDIR(opened.st_mode)
                and _directory_fingerprint(opened) == _directory_fingerprint(listed),
                f"{label}: ancestor changed during open: {component}",
            )
            fingerprints.append(_directory_fingerprint(opened))
        close_error: OSError | None = None
        for descriptor in descriptors[:-1]:
            try:
                os.close(descriptor)
            except OSError as error:
                close_error = error
        if close_error is not None:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            descriptors.clear()
            _fail(f"{label}: cannot close anchored ancestor: {close_error}")
        parent_descriptor = descriptors[-1]
        descriptors.clear()
        return parent_descriptor, absolute_path, parts[-1], tuple(fingerprints)
    except OSError as error:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        _fail(f"{label}: cannot open anchored parent for {path}: {error}")
    except SelectorClosureCodecError:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise


def _verify_anchored_parent_unchanged(
    expected_absolute_path: Path,
    expected_leaf: str,
    expected_fingerprints: tuple[tuple[int, ...], ...],
    *,
    label: str,
) -> None:
    descriptor = -1
    try:
        (
            descriptor,
            absolute_path,
            leaf,
            fingerprints,
        ) = _open_anchored_parent_directory(
            expected_absolute_path,
            label=label,
        )
        _require_managed_directory(descriptor, label=label)
        _require(
            absolute_path == expected_absolute_path
            and leaf == expected_leaf
            and fingerprints == expected_fingerprints,
            f"{label}: ancestor directory chain changed",
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_bounded_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
    phase_hook: PathIOPhaseHook | None = None,
) -> bytes:
    """Return a bounded snapshot of one opened inode under a managed parent."""

    _require(maximum_bytes > 0, f"{label}: maximum_bytes must be positive")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    _require(no_follow is not None, f"{label}: O_NOFOLLOW is unavailable")
    parent_descriptor = -1
    file_descriptor = -1
    close_error: OSError | None = None
    try:
        (
            parent_descriptor,
            absolute_path,
            leaf,
            parent_fingerprints,
        ) = _open_anchored_parent_directory(path, label=label)
        _require_managed_directory(parent_descriptor, label=label)
        fcntl.flock(parent_descriptor, fcntl.LOCK_SH)
        before = os.stat(
            leaf,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _require(not stat.S_ISLNK(before.st_mode), f"{label}: symlink is forbidden")
        _require_managed_regular_file(before, label=label)
        _require(before.st_size > 0, f"{label}: file is empty")
        _require(
            before.st_size <= maximum_bytes,
            f"{label}: exceeds {maximum_bytes} bytes",
        )
        if phase_hook is not None:
            phase_hook("parent-opened")
        file_descriptor = os.open(
            leaf,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow,
            dir_fd=parent_descriptor,
        )
        during = os.fstat(file_descriptor)
        _require_managed_regular_file(during, label=label)
        _require(
            _stat_fingerprint(before) == _stat_fingerprint(during),
            f"{label}: file changed before open",
        )
        opened_path = os.stat(
            leaf,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _require(
            stat.S_ISREG(opened_path.st_mode)
            and not stat.S_ISLNK(opened_path.st_mode)
            and _stat_fingerprint(opened_path) == _stat_fingerprint(during),
            f"{label}: path changed during open",
        )
        raw = _read_exact_descriptor(
            file_descriptor,
            during.st_size,
            label=label,
        )
        after = os.fstat(file_descriptor)
        if phase_hook is not None:
            phase_hook("read-complete")
        after_hook = os.fstat(file_descriptor)
        final_path = os.stat(
            leaf,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _require_managed_regular_file(final_path, label=label)
        _verify_anchored_parent_unchanged(
            absolute_path,
            leaf,
            parent_fingerprints,
            label=label,
        )
    except OSError as error:
        _fail(f"{label}: cannot read {path}: {error}")
    finally:
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except OSError as error:
                close_error = error
        if parent_descriptor >= 0:
            try:
                os.close(parent_descriptor)
            except OSError as error:
                if close_error is None:
                    close_error = error
    if close_error is not None:
        _fail(f"{label}: cannot close opened snapshot descriptors: {close_error}")
    _require(
        _stat_fingerprint(during)
        == _stat_fingerprint(after)
        == _stat_fingerprint(after_hook),
        f"{label}: file changed while read",
    )
    _require(
        stat.S_ISREG(final_path.st_mode)
        and not stat.S_ISLNK(final_path.st_mode)
        and _stat_fingerprint(final_path) == _stat_fingerprint(after),
        f"{label}: path changed while read",
    )
    _require(len(raw) <= maximum_bytes, f"{label}: exceeds {maximum_bytes} bytes")
    _require(raw, f"{label}: file is empty")
    return raw


def read_bounded_regular_file(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    """Read a checked opened-inode snapshot from a managed physical path."""

    return _read_bounded_regular_file(
        path,
        maximum_bytes=maximum_bytes,
        label=label,
    )


def _atomic_write_regular_file(
    path: Path,
    raw: bytes,
    *,
    label: str,
    create_only: bool = False,
    create_mode: int = 0o644,
    expected_current: bytes | None = None,
    phase_hook: PathIOPhaseHook | None = None,
) -> None:
    """Install one leaf, optionally comparing exact current bytes under one lock."""

    _require(type(raw) is bytes, f"{label}: output must be native bytes")
    _require(raw, f"{label}: empty output is forbidden")
    _require(
        expected_current is None
        or (type(expected_current) is bytes and bool(expected_current)),
        f"{label}: expected current value must be nonempty native bytes",
    )
    _require(
        not create_only or expected_current is None,
        f"{label}: create-only and expected-current modes are mutually exclusive",
    )
    _require(
        type(create_mode) is int and create_mode in {0o600, 0o644},
        f"{label}: create mode must be exactly 0600 or 0644",
    )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    _require(no_follow is not None, f"{label}: O_NOFOLLOW is unavailable")
    _require(
        os.rename in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.link in os.supports_dir_fd,
        f"{label}: platform lacks required dirfd install operations",
    )
    _require(
        os.link in os.supports_follow_symlinks,
        f"{label}: platform lacks no-follow hard-link installation",
    )
    parent_descriptor = -1
    file_descriptor = -1
    temporary_name = ""
    install_may_have_crossed = False
    try:
        (
            parent_descriptor,
            absolute_path,
            leaf,
            parent_fingerprints,
        ) = _open_anchored_parent_directory(path, label=label)
        _require_managed_directory(parent_descriptor, label=label)
        fcntl.flock(parent_descriptor, fcntl.LOCK_EX)
        try:
            target_before = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_before = None
        if target_before is not None:
            _require(
                not stat.S_ISLNK(target_before.st_mode),
                f"{label}: output must be a regular non-symlink file",
            )
            _require_managed_regular_file(target_before, label=label)
            _require(
                not create_only,
                f"{label}: create-only output already exists",
            )
            mode = stat.S_IMODE(target_before.st_mode)
        else:
            mode = create_mode
        if expected_current is not None:
            _require(
                target_before is not None
                and target_before.st_size == len(expected_current),
                f"{label}: current file differs from the expected CAS value",
            )
            current_descriptor = -1
            try:
                current_descriptor = os.open(
                    leaf,
                    os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | no_follow,
                    dir_fd=parent_descriptor,
                )
                current_opened = os.fstat(current_descriptor)
                _require_managed_regular_file(current_opened, label=label)
                _require(
                    _stat_fingerprint(current_opened)
                    == _stat_fingerprint(target_before),
                    f"{label}: current file changed before its CAS read",
                )
                current_raw = _read_exact_descriptor(
                    current_descriptor,
                    current_opened.st_size,
                    label=f"{label}: expected-current CAS",
                )
                current_after = os.fstat(current_descriptor)
                current_path = os.stat(
                    leaf,
                    dir_fd=parent_descriptor,
                    follow_symlinks=False,
                )
                _require_managed_regular_file(current_after, label=label)
                _require_managed_regular_file(current_path, label=label)
                _require(
                    _stat_fingerprint(target_before)
                    == _stat_fingerprint(current_opened)
                    == _stat_fingerprint(current_after)
                    == _stat_fingerprint(current_path)
                    and current_raw == expected_current,
                    f"{label}: current file differs from the expected CAS value",
                )
            finally:
                if current_descriptor >= 0:
                    os.close(current_descriptor)
        if phase_hook is not None:
            phase_hook("parent-opened")

        for _ in range(32):
            candidate = f".ncp-{secrets.token_hex(16)}.tmp"
            try:
                file_descriptor = os.open(
                    candidate,
                    os.O_RDWR
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | no_follow,
                    0o600,
                    dir_fd=parent_descriptor,
                )
                temporary_name = candidate
                break
            except FileExistsError:
                continue
        _require(file_descriptor >= 0, f"{label}: temporary-name pool exhausted")
        os.fchmod(file_descriptor, mode)
        pending = memoryview(raw)
        while pending:
            written = os.write(file_descriptor, pending)
            _require(written > 0, f"{label}: temporary write made no progress")
            pending = pending[written:]
        os.fsync(file_descriptor)
        temporary_before = os.fstat(file_descriptor)
        _require_managed_regular_file(temporary_before, label=label)
        _require(
            temporary_before.st_size == len(raw)
            and _read_exact_descriptor(
                file_descriptor,
                len(raw),
                label=f"{label}: temporary output",
            )
            == raw,
            f"{label}: temporary output bytes are not exact",
        )
        if phase_hook is not None:
            phase_hook("temporary-file-fsynced")

        temporary_current = os.fstat(file_descriptor)
        temporary_path = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _require_managed_regular_file(temporary_current, label=label)
        _require_managed_regular_file(temporary_path, label=label)
        _require(
            _stat_fingerprint(temporary_current)
            == _stat_fingerprint(temporary_before)
            == _stat_fingerprint(temporary_path)
            and temporary_current.st_nlink == 1
            and _read_exact_descriptor(
                file_descriptor,
                len(raw),
                label=f"{label}: temporary output",
            )
            == raw,
            f"{label}: temporary output identity changed",
        )

        try:
            target_current = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_current = None
        if target_before is None:
            _require(
                target_current is None,
                f"{label}: output appeared during generation",
            )
        else:
            _require(
                target_current is not None
                and stat.S_ISREG(target_current.st_mode)
                and not stat.S_ISLNK(target_current.st_mode),
                f"{label}: output changed during generation",
            )
            _require_managed_regular_file(target_current, label=label)
            _require(
                _stat_fingerprint(target_current) == _stat_fingerprint(target_before),
                f"{label}: output changed during generation",
            )
        _verify_anchored_parent_unchanged(
            absolute_path,
            leaf,
            parent_fingerprints,
            label=label,
        )
        if phase_hook is not None:
            phase_hook("before-install")

        # Hooks exercise deterministic late races. Cooperative writers also hold
        # this parent lock; uncooperative same-owner mutation is outside the
        # documented boundary and is rechecked here where possible.
        temporary_current = os.fstat(file_descriptor)
        temporary_path = os.stat(
            temporary_name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _require_managed_regular_file(temporary_current, label=label)
        _require_managed_regular_file(temporary_path, label=label)
        _require(
            _stat_fingerprint(temporary_current)
            == _stat_fingerprint(temporary_before)
            == _stat_fingerprint(temporary_path)
            and temporary_current.st_nlink == 1
            and _read_exact_descriptor(
                file_descriptor,
                len(raw),
                label=f"{label}: temporary output",
            )
            == raw,
            f"{label}: temporary output changed before install",
        )
        try:
            target_current = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_current = None
        if target_before is None:
            _require(
                target_current is None,
                f"{label}: output appeared before install",
            )
        else:
            _require(
                target_current is not None,
                f"{label}: output changed before install",
            )
            _require_managed_regular_file(target_current, label=label)
            _require(
                _stat_fingerprint(target_current) == _stat_fingerprint(target_before),
                f"{label}: output changed before install",
            )
        _verify_anchored_parent_unchanged(
            absolute_path,
            leaf,
            parent_fingerprints,
            label=label,
        )

        # Set this flag before the install syscall. A Python signal can run
        # after a successful syscall but before the next Python assignment.
        # From this point, every escaping exception has an indeterminate
        # install outcome.
        install_may_have_crossed = True
        if create_only or target_before is None:
            os.link(
                temporary_name,
                leaf,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            os.unlink(temporary_name, dir_fd=parent_descriptor)
            temporary_name = ""
        else:
            os.rename(
                temporary_name,
                leaf,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            temporary_name = ""
        os.fsync(parent_descriptor)
        if phase_hook is not None:
            phase_hook("parent-directory-fsynced")
        installed = os.stat(
            leaf,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        held_installed = os.fstat(file_descriptor)
        _require(
            not stat.S_ISLNK(installed.st_mode)
            and stat.S_ISREG(installed.st_mode)
            and installed.st_dev == held_installed.st_dev
            and installed.st_ino == held_installed.st_ino
            and installed.st_nlink == 1
            and held_installed.st_nlink == 1
            and installed.st_size == len(raw),
            f"{label}: installed output identity is invalid",
        )
        _require_managed_regular_file(installed, label=label)
        _require(
            _read_exact_descriptor(
                file_descriptor,
                len(raw),
                label=f"{label}: installed output",
            )
            == raw,
            f"{label}: installed output bytes changed",
        )
        final_installed = os.stat(
            leaf,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        final_held_installed = os.fstat(file_descriptor)
        _require_managed_regular_file(final_installed, label=label)
        _require_managed_regular_file(final_held_installed, label=label)
        _require(
            _stat_fingerprint(installed)
            == _stat_fingerprint(held_installed)
            == _stat_fingerprint(final_installed)
            == _stat_fingerprint(final_held_installed),
            f"{label}: installed output changed during final readback",
        )
        _verify_anchored_parent_unchanged(
            absolute_path,
            leaf,
            parent_fingerprints,
            label=label,
        )
    except BaseException as error:
        if install_may_have_crossed:
            if isinstance(error, AtomicWriteOutcomeUnknownError):
                raise
            raise AtomicWriteOutcomeUnknownError(
                f"{label}: install may have crossed for {path}, but final "
                f"identity or durability is unproved: {error}"
            ) from error
        if isinstance(error, SelectorClosureCodecError):
            raise
        if isinstance(error, OSError):
            _fail(f"{label}: atomic write failed before install for {path}: {error}")
        raise
    finally:
        cleanup_error: BaseException | None = None
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except BaseException as error:
                cleanup_error = error
        if temporary_name and parent_descriptor >= 0:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
                os.fsync(parent_descriptor)
            except FileNotFoundError:
                try:
                    # The install syscall may have consumed the temp name
                    # before an asynchronous exception reached Python.
                    os.fsync(parent_descriptor)
                except BaseException as error:
                    if cleanup_error is None:
                        cleanup_error = error
            except BaseException as error:
                # Cleanup failure never masks the pre-install failure. The
                # managed directory may contain an inert private temp inode.
                if cleanup_error is None:
                    cleanup_error = error
        if parent_descriptor >= 0:
            try:
                os.close(parent_descriptor)
            except BaseException as error:
                if cleanup_error is None:
                    cleanup_error = error
        if cleanup_error is not None and install_may_have_crossed:
            raise AtomicWriteOutcomeUnknownError(
                f"{label}: install may have crossed for {path}, but "
                f"descriptor cleanup is unproved: {cleanup_error}"
            ) from cleanup_error


def atomic_write_regular_file(
    path: Path,
    raw: bytes,
    *,
    label: str,
    create_only: bool = False,
    create_mode: int = 0o644,
) -> None:
    """Install bytes under the documented managed-parent boundary."""

    _atomic_write_regular_file(
        path,
        raw,
        label=label,
        create_only=create_only,
        create_mode=create_mode,
    )


def canonical_bytes(value: Any) -> bytes:
    """Return the repository's canonical JSON bytes without a trailing newline."""

    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError, RecursionError) as error:
        _fail(f"value is not canonical JSON: {error}")


def canonical_sha256(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def require_unaliased_mutable_tree(value: Any, *, label: str) -> None:
    """Reject a decoded JSON tree that shares a mutable list or object."""

    seen: set[int] = set()
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            identity = id(item)
            _require(
                identity not in seen,
                f"{label}: decoded tree shares a mutable object",
            )
            seen.add(identity)
            stack.extend(item.values())
        elif isinstance(item, list):
            identity = id(item)
            _require(
                identity not in seen,
                f"{label}: decoded tree shares a mutable array",
            )
            seen.add(identity)
            stack.extend(item)


def bounded_canonical_sha256(
    value: Any,
    *,
    maximum_bytes: int,
    label: str,
) -> tuple[str, int]:
    """Hash canonical JSON incrementally and stop before an oversized expansion."""

    digest = sha256()
    byte_count = 0
    encoder = json.JSONEncoder(
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        for chunk in encoder.iterencode(value):
            encoded = chunk.encode("utf-8")
            byte_count += len(encoded)
            _require(
                byte_count <= maximum_bytes,
                f"{label}: canonical JSON exceeds {maximum_bytes} bytes",
            )
            digest.update(encoded)
    except (TypeError, UnicodeError, ValueError, RecursionError) as error:
        _fail(f"{label}: value is not canonical JSON: {error}")
    return digest.hexdigest(), byte_count


def _require_unique(values: list[Any], label: str) -> None:
    canonical_values = [canonical_bytes(value) for value in values]
    _require(
        len(canonical_values) == len(set(canonical_values)),
        f"{label}: duplicate values",
    )


def _validate_compact_envelope(
    envelope: dict[str, Any],
    *,
    raw: bytes | None,
) -> None:
    _require_exact(set(envelope), ENVELOPE_KEYS, "compact envelope keys")
    _require_exact(envelope["$schema"], COMPACT_SCHEMA_FILE, "compact $schema")
    _require_exact(envelope["schema"], COMPACT_SCHEMA_ID, "compact schema")
    _require_exact(envelope["normative"], False, "compact normative flag")
    _require_exact(envelope["candidate"], "1.0.0-rc.1", "compact candidate")
    _require_exact(envelope["task"], "B01", "compact task")
    _require(isinstance(envelope["payload"], dict), "payload must be an object")

    encoding = envelope["encoding"]
    _require(isinstance(encoding, dict), "encoding must be an object")
    _require_exact(set(encoding), ENCODING_KEYS, "encoding keys")
    _require_exact(encoding["kind"], ENCODING_KIND, "encoding kind")
    _require_exact(
        encoding["string_token_pattern"],
        STRING_REFERENCE_PATTERN,
        "string token pattern",
    )
    _require_exact(
        encoding["object_token_pattern"],
        OBJECT_REFERENCE_PATTERN,
        "object token pattern",
    )
    _require_exact(
        encoding["string_minimum_repetition"],
        2,
        "string repetition floor",
    )
    _require_exact(encoding["string_minimum_length"], 8, "string length floor")
    _require_exact(
        encoding["object_minimum_repetition"],
        2,
        "object repetition floor",
    )
    _require_exact(
        encoding["object_minimum_canonical_utf8_bytes"],
        8,
        "object byte floor",
    )

    string_table = encoding["string_table"]
    object_table = encoding["object_table"]
    _require(isinstance(string_table, list), "string table must be an array")
    _require(isinstance(object_table, list), "object table must be an array")
    _require(
        len(string_table) <= MAX_TABLE_ITEMS,
        "string table exceeds token index space",
    )
    _require(
        len(object_table) <= MAX_TABLE_ITEMS,
        "object table exceeds token index space",
    )
    _require(
        all(isinstance(value, str) for value in string_table),
        "string table contains a non-string",
    )
    _require_unique(string_table, "string table")
    _require(
        all(
            not STRING_TOKEN.fullmatch(value) and not OBJECT_TOKEN.fullmatch(value)
            for value in string_table
        ),
        "string table contains a reserved token literal",
    )
    _require(
        all(isinstance(value, (dict, list)) for value in object_table),
        "object table entries must be arrays or objects",
    )
    _require_unique(object_table, "object table")
    _require_exact(
        canonical_sha256(string_table),
        encoding["string_table_sha256"],
        "string table digest",
    )
    _require_exact(
        canonical_sha256(object_table),
        encoding["object_table_sha256"],
        "object table digest",
    )
    if raw is not None:
        _require_exact(
            raw,
            canonical_bytes(envelope) + b"\n",
            "canonical compact serialization",
        )


def _preflight_compact_expansion(
    payload: Any,
    *,
    strings: list[str],
    objects: list[Any],
    maximum_expanded_bytes: int,
) -> None:
    """Measure the exact decoded tree before allocating expanded subtrees."""

    # size, item count, total string characters, maximum root-relative depth
    memo: dict[int, _Metric] = {}
    active: set[int] = set()

    def checked_metric(
        *,
        size: int,
        items: int,
        string_chars: int,
        depth: int,
    ) -> _Metric:
        _require(
            size <= maximum_expanded_bytes,
            f"expanded document canonical JSON exceeds {maximum_expanded_bytes} bytes",
        )
        _require(
            items <= MAX_JSON_ITEMS,
            f"expanded document JSON item count exceeds {MAX_JSON_ITEMS}",
        )
        _require(
            string_chars <= MAX_JSON_TOTAL_STRING_CHARS,
            "expanded document total JSON string content exceeds "
            f"{MAX_JSON_TOTAL_STRING_CHARS} characters",
        )
        _require(
            depth <= MAX_JSON_DEPTH,
            f"expanded document JSON nesting exceeds {MAX_JSON_DEPTH}",
        )
        return size, items, string_chars, depth

    def string_value(value: str) -> str | None:
        if STRING_TOKEN.fullmatch(value):
            index = int(value[2:], 16)
            if index >= len(strings):
                _fail(f"string token index {index} is out of range")
            return strings[index]
        if OBJECT_TOKEN.fullmatch(value):
            return None
        return value

    def measure_object(index: int) -> _Metric:
        if index >= len(objects):
            _fail(f"object token index {index} is out of range")
        if index in active:
            _fail(f"object table contains a cycle through index {index}")
        if index not in memo:
            _require(
                len(active) <= MAX_JSON_DEPTH,
                (
                    "expanded document root-depth-0 object-table nesting "
                    f"exceeds {MAX_JSON_DEPTH}"
                ),
            )
            active.add(index)
            memo[index] = measure(objects[index])
            active.remove(index)
        return memo[index]

    def measure(value: Any) -> _Metric:
        if isinstance(value, str):
            decoded_string = string_value(value)
            if decoded_string is None:
                return measure_object(int(value[2:], 16))
            return checked_metric(
                size=len(canonical_bytes(decoded_string)),
                items=1,
                string_chars=len(decoded_string),
                depth=0,
            )
        if isinstance(value, list):
            size = 2 + max(0, len(value) - 1)
            items = 1
            string_chars = 0
            depth = 0
            for child in value:
                child_size, child_items, child_strings, child_depth = measure(child)
                size += child_size
                items += child_items
                string_chars += child_strings
                depth = max(depth, child_depth + 1)
                checked_metric(
                    size=size,
                    items=items,
                    string_chars=string_chars,
                    depth=depth,
                )
            return checked_metric(
                size=size,
                items=items,
                string_chars=string_chars,
                depth=depth,
            )
        if isinstance(value, dict):
            size = 2 + max(0, len(value) - 1)
            items = 1
            string_chars = 0
            depth = 0
            decoded_keys: set[str] = set()
            for key, child in value.items():
                decoded_key = string_value(key)
                _require(
                    decoded_key is not None,
                    "decoded object key is not a string",
                )
                _require(
                    decoded_key not in decoded_keys,
                    f"decoded object contains duplicate key {decoded_key!r}",
                )
                decoded_keys.add(decoded_key)
                child_size, child_items, child_strings, child_depth = measure(child)
                size += len(canonical_bytes(decoded_key)) + 1 + child_size
                items += 1 + child_items
                string_chars += len(decoded_key) + child_strings
                depth = max(depth, child_depth + 1)
                checked_metric(
                    size=size,
                    items=items,
                    string_chars=string_chars,
                    depth=depth,
                )
            return checked_metric(
                size=size,
                items=items,
                string_chars=string_chars,
                depth=depth,
            )
        return checked_metric(
            size=len(canonical_bytes(value)),
            items=1,
            string_chars=0,
            depth=0,
        )

    for object_index in range(len(objects)):
        measure_object(object_index)
    size, _, _, _ = measure(payload)
    _require(
        size <= maximum_expanded_bytes,
        f"expanded document canonical JSON exceeds {maximum_expanded_bytes} bytes",
    )


def decode_compact_source(
    envelope: dict[str, Any],
    *,
    maximum_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> dict[str, Any]:
    """Decode a validated compact envelope with index and cycle checks."""

    validate_json_resource_bounds(
        envelope,
        label="compact envelope",
    )
    encoding = envelope["encoding"]
    strings: list[str] = encoding["string_table"]
    objects: list[Any] = encoding["object_table"]
    try:
        _preflight_compact_expansion(
            envelope["payload"],
            strings=strings,
            objects=objects,
            maximum_expanded_bytes=maximum_expanded_bytes,
        )
    except RecursionError as error:
        _fail(f"compact expansion preflight exceeded recursion bounds: {error}")
    memo: dict[int, Any] = {}
    active: set[int] = set()

    def resolve_object(index: int) -> Any:
        if index >= len(objects):
            _fail(f"object token index {index} is out of range")
        if index in active:
            _fail(f"object table contains a cycle through index {index}")
        if index not in memo:
            active.add(index)
            memo[index] = decode(objects[index])
            active.remove(index)
        return memo[index]

    def decode(value: Any) -> Any:
        if isinstance(value, str):
            if STRING_TOKEN.fullmatch(value):
                index = int(value[2:], 16)
                if index >= len(strings):
                    _fail(f"string token index {index} is out of range")
                return strings[index]
            if OBJECT_TOKEN.fullmatch(value):
                return copy.deepcopy(resolve_object(int(value[2:], 16)))
            return value
        if isinstance(value, list):
            return [decode(item) for item in value]
        if isinstance(value, dict):
            decoded: dict[str, Any] = {}
            for key, item in value.items():
                decoded_key = decode(key)
                _require(
                    isinstance(decoded_key, str),
                    "decoded object key is not a string",
                )
                _require(
                    decoded_key not in decoded,
                    f"decoded object contains duplicate key {decoded_key!r}",
                )
                decoded[decoded_key] = decode(item)
            return decoded
        return value

    try:
        expanded = decode(envelope["payload"])
    except RecursionError as error:
        _fail(f"compact object nesting exceeds the decoder limit: {error}")
    _require(isinstance(expanded, dict), "decoded payload must be an object")
    validate_json_resource_bounds(expanded, label="expanded document")
    expanded_digest, _ = bounded_canonical_sha256(
        expanded,
        maximum_bytes=maximum_expanded_bytes,
        label="expanded document",
    )
    _require_exact(
        expanded_digest,
        encoding["expanded_document_sha256"],
        "expanded document digest",
    )
    _require_exact(
        expanded.get("candidate"),
        envelope["candidate"],
        "envelope/payload candidate",
    )
    _require_exact(
        expanded.get("task"),
        envelope["task"],
        "envelope/payload task",
    )
    _require_exact(
        expanded.get("normative"),
        envelope["normative"],
        "envelope/payload normative flag",
    )
    return expanded


def compact_selector_source(
    data: dict[str, Any],
    *,
    maximum_compact_bytes: int = MAX_COMPACT_BYTES,
    maximum_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> dict[str, Any]:
    """Intern repeated strings and structural subtrees without semantic loss."""

    _require(isinstance(data, dict), "expanded selector source must be an object")
    validate_json_resource_bounds(
        data,
        label="expanded selector source",
    )
    expanded_digest, _ = bounded_canonical_sha256(
        data,
        maximum_bytes=maximum_expanded_bytes,
        label="expanded selector source",
    )
    string_counts: Counter[str] = Counter()

    def count_strings(value: Any) -> None:
        if isinstance(value, str):
            if STRING_TOKEN.fullmatch(value) or OBJECT_TOKEN.fullmatch(value):
                _fail(f"literal collides with compact source token namespace: {value}")
            string_counts[value] += 1
        elif isinstance(value, list):
            for item in value:
                count_strings(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                _require(
                    isinstance(key, str),
                    "expanded selector source contains a non-string object key",
                )
                count_strings(key)
                count_strings(item)

    try:
        count_strings(data)
    except RecursionError as error:
        _fail(f"expanded object nesting exceeds the encoder limit: {error}")
    token_json_bytes = len(json.dumps("@S0000").encode("utf-8"))

    def string_interning_saves_bytes(value: str) -> bool:
        encoded_bytes = len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        occurrences = string_counts[value]
        table_entry_bytes = encoded_bytes + 1
        replaced_bytes = occurrences * (encoded_bytes - token_json_bytes)
        return replaced_bytes > table_entry_bytes

    selected_strings = [
        value
        for value, count in string_counts.items()
        if count >= 2 and len(value) >= 8 and string_interning_saves_bytes(value)
    ]
    _require(
        len(selected_strings) <= MAX_TABLE_ITEMS,
        "string table exceeds token index space",
    )
    strings = sorted(
        selected_strings,
        key=lambda value: (-string_counts[value], value),
    )
    string_tokens = {value: f"@S{index:04X}" for index, value in enumerate(strings)}

    def intern_strings(value: Any) -> Any:
        if isinstance(value, str):
            return string_tokens.get(value, value)
        if isinstance(value, list):
            return [intern_strings(item) for item in value]
        if isinstance(value, dict):
            return {
                string_tokens.get(key, key): intern_strings(item)
                for key, item in value.items()
            }
        return value

    string_interned = intern_strings(data)
    subtree_counts: Counter[int] = Counter()
    subtree_values: dict[int, Any] = {}
    subtree_utf8_bytes: dict[int, int] = {}
    subtree_ids_by_key: dict[tuple[Any, ...], int] = {}
    subtree_ids_by_identity: dict[int, int] = {}
    scalar_references: dict[bytes, tuple[str, bytes]] = {}

    def scalar_reference(value: Any) -> tuple[tuple[str, bytes], int]:
        encoded = canonical_bytes(value)
        reference = scalar_references.setdefault(
            encoded,
            ("SCALAR", encoded),
        )
        return reference, len(encoded)

    def analyze_subtree(
        value: Any,
        *,
        root: bool = False,
    ) -> tuple[tuple[str, bytes | int], int]:
        if isinstance(value, list):
            child_metrics = [analyze_subtree(item) for item in value]
            key: tuple[Any, ...] = (
                "ARRAY",
                tuple(reference for reference, _ in child_metrics),
            )
            canonical_size = (
                2 + max(0, len(value) - 1) + sum(size for _, size in child_metrics)
            )
        elif isinstance(value, dict):
            child_metrics = [
                (key, *analyze_subtree(item)) for key, item in sorted(value.items())
            ]
            key = (
                "OBJECT",
                tuple((member, reference) for member, reference, _ in child_metrics),
            )
            canonical_size = (
                2
                + max(0, len(value) - 1)
                + sum(
                    len(canonical_bytes(member)) + 1 + size
                    for member, _, size in child_metrics
                )
            )
        else:
            return scalar_reference(value)

        subtree_id = subtree_ids_by_key.get(key)
        if subtree_id is None:
            subtree_id = len(subtree_ids_by_key)
            subtree_ids_by_key[key] = subtree_id
            subtree_values[subtree_id] = value
            subtree_utf8_bytes[subtree_id] = canonical_size
        else:
            _require_exact(
                subtree_utf8_bytes[subtree_id],
                canonical_size,
                "structurally equal subtree canonical byte size",
            )
        subtree_ids_by_identity[id(value)] = subtree_id
        if not root and canonical_size >= 8:
            subtree_counts[subtree_id] += 1
        return ("SUBTREE", subtree_id), canonical_size

    try:
        analyze_subtree(string_interned, root=True)
    except RecursionError as error:
        _fail(f"expanded object nesting exceeds the encoder limit: {error}")
    selected_subtree_ids = [
        subtree_id
        for subtree_id, count in subtree_counts.items()
        if count >= 2
        and count * (subtree_utf8_bytes[subtree_id] - token_json_bytes)
        > subtree_utf8_bytes[subtree_id] + 1
    ]
    _require(
        len(selected_subtree_ids) <= MAX_TABLE_ITEMS,
        "object table exceeds token index space",
    )
    selected_canonical_bytes: dict[int, bytes] = {}
    ordering_work_bytes = 0
    for subtree_id in selected_subtree_ids:
        encoded = canonical_bytes(subtree_values[subtree_id])
        _require_exact(
            len(encoded),
            subtree_utf8_bytes[subtree_id],
            "subtree canonical byte accounting",
        )
        ordering_work_bytes += len(encoded)
        _require(
            ordering_work_bytes <= maximum_expanded_bytes,
            f"object-table ordering material exceeds {maximum_expanded_bytes} bytes",
        )
        selected_canonical_bytes[subtree_id] = encoded
    selected_subtree_ids.sort(
        key=selected_canonical_bytes.__getitem__,
    )
    object_tokens = {
        subtree_id: f"@O{index:04X}"
        for index, subtree_id in enumerate(selected_subtree_ids)
    }

    def intern_subtrees(value: Any, *, allow_current: bool = True) -> Any:
        if isinstance(value, (list, dict)):
            subtree_id = subtree_ids_by_identity[id(value)]
            if allow_current and subtree_id in object_tokens:
                return object_tokens[subtree_id]
            if isinstance(value, list):
                return [intern_subtrees(item) for item in value]
            return {key: intern_subtrees(item) for key, item in value.items()}
        return value

    object_table = [
        intern_subtrees(subtree_values[subtree_id], allow_current=False)
        for subtree_id in selected_subtree_ids
    ]
    payload = intern_subtrees(string_interned, allow_current=False)
    envelope = {
        "$schema": COMPACT_SCHEMA_FILE,
        "schema": COMPACT_SCHEMA_ID,
        "normative": False,
        "candidate": data.get("candidate"),
        "task": data.get("task"),
        "encoding": {
            "kind": ENCODING_KIND,
            "string_token_pattern": STRING_REFERENCE_PATTERN,
            "object_token_pattern": OBJECT_REFERENCE_PATTERN,
            "string_minimum_repetition": 2,
            "string_minimum_length": 8,
            "object_minimum_repetition": 2,
            "object_minimum_canonical_utf8_bytes": 8,
            "string_table": strings,
            "object_table": object_table,
            "expanded_document_sha256": expanded_digest,
            "string_table_sha256": canonical_sha256(strings),
            "object_table_sha256": canonical_sha256(object_table),
        },
        "payload": payload,
    }
    serialized = canonical_bytes(envelope) + b"\n"
    _require(
        len(serialized) < maximum_compact_bytes,
        "compact selector source exceeds hard cap: "
        f"{len(serialized)} >= {maximum_compact_bytes} bytes",
    )
    return envelope


def serialize_compact_source(
    data: dict[str, Any],
    *,
    maximum_compact_bytes: int = MAX_COMPACT_BYTES,
    maximum_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> bytes:
    envelope = compact_selector_source(
        data,
        maximum_compact_bytes=maximum_compact_bytes,
        maximum_expanded_bytes=maximum_expanded_bytes,
    )
    serialized = canonical_bytes(envelope) + b"\n"
    _validate_compact_envelope(envelope, raw=serialized)
    decoded = decode_compact_source(
        envelope,
        maximum_expanded_bytes=maximum_expanded_bytes,
    )
    _require_exact(decoded, data, "compact encode/decode round trip")
    return serialized


def decode_compact_source_bytes(
    raw: bytes,
    *,
    label: str,
    verify_round_trip: bool = True,
    maximum_compact_bytes: int = MAX_COMPACT_BYTES,
    maximum_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate and decode one immutable compact-source byte snapshot.

    Callers that bind a source digest or byte length must pass the exact bytes
    they committed here.  Reopening a pathname between hashing and decoding can
    otherwise produce a proposal for different bytes, even if a later pathname
    stability check observes the original content again.
    """

    envelope = parse_json_bytes(
        raw,
        label=label,
        maximum_bytes=maximum_compact_bytes - 1,
    )
    _require(isinstance(envelope, dict), "compact source must be an object")
    _validate_compact_envelope(envelope, raw=raw)
    expanded = decode_compact_source(
        envelope,
        maximum_expanded_bytes=maximum_expanded_bytes,
    )
    if verify_round_trip:
        _require_exact(
            compact_selector_source(
                expanded,
                maximum_compact_bytes=maximum_compact_bytes,
                maximum_expanded_bytes=maximum_expanded_bytes,
            ),
            envelope,
            "deterministic compact round trip",
        )
    return envelope, expanded


def load_compact_source(
    path: Path,
    *,
    verify_round_trip: bool = True,
    maximum_compact_bytes: int = MAX_COMPACT_BYTES,
    maximum_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = read_bounded_regular_file(
        path,
        maximum_bytes=maximum_compact_bytes - 1,
        label="compact selector source",
    )
    return decode_compact_source_bytes(
        raw,
        label=str(path),
        verify_round_trip=verify_round_trip,
        maximum_compact_bytes=maximum_compact_bytes,
        maximum_expanded_bytes=maximum_expanded_bytes,
    )


def run_codec_self_test() -> None:
    """Exercise hostile parser bounds and decoded-tree isolation."""

    _require(
        issubclass(SelectorClosureCodecError, SelectorClosureError)
        and issubclass(SelectorClosureCodecError, ValueError),
        "deterministic codec error hierarchy is invalid",
    )
    _require(
        issubclass(AtomicWriteOutcomeUnknownError, SelectorClosureError)
        and issubclass(AtomicWriteOutcomeUnknownError, RuntimeError)
        and not issubclass(
            AtomicWriteOutcomeUnknownError,
            SelectorClosureCodecError,
        ),
        "atomic outcome-unknown error is not retry-distinct",
    )

    def expect_failure(action: Any, label: str) -> None:
        try:
            action()
        except SelectorClosureCodecError:
            return
        _fail(f"codec self-test accepted {label}")

    def expect_outcome_unknown(action: Any, label: str) -> None:
        try:
            action()
        except AtomicWriteOutcomeUnknownError:
            return
        except BaseException as error:
            _fail(
                f"codec self-test returned {type(error).__name__} instead of "
                f"an indeterminate write outcome for {label}"
            )
        _fail(f"codec self-test accepted {label}")

    expect_failure(
        lambda: parse_json_bytes(
            b"null",
            label="encoded-byte-limit",
            maximum_bytes=3,
        ),
        "JSON above its encoded-byte limit",
    )
    expect_failure(
        lambda: parse_json_bytes(b"", label="empty-JSON"),
        "empty JSON input",
    )
    expect_failure(
        lambda: parse_json_bytes(b'{"x":1,"x":2}', label="duplicate-key"),
        "a duplicate key",
    )
    expect_failure(
        lambda: parse_json_bytes(b'{"x":NaN}', label="NaN"),
        "NaN",
    )
    expect_failure(
        lambda: parse_json_bytes(
            b'{"x":"\\ud800"}',
            label="lone-surrogate",
        ),
        "a lone Unicode surrogate",
    )
    for vector_label, encoded_character, decoded_character in (
        ("escaped-backslash", b"\\\\", "\\"),
        ("escaped-quote", b'\\"', '"'),
        ("escaped-control", b"\\u0001", "\x01"),
        ("escaped-surrogate-pair", b"\\ud834\\udd1e", "\U0001d11e"),
    ):
        exact_raw = b'{"x":"' + encoded_character * MAX_JSON_STRING_CHARS + b'"}'
        exact_value = parse_json_bytes(
            exact_raw,
            label=f"{vector_label}-exact-character-limit",
        )
        _require_exact(
            exact_value,
            {"x": decoded_character * MAX_JSON_STRING_CHARS},
            f"{vector_label} decoded character accounting",
        )
        expect_failure(
            lambda encoded_character=encoded_character, vector_label=vector_label: (
                parse_json_bytes(
                    b'{"x":"' + encoded_character * (MAX_JSON_STRING_CHARS + 1) + b'"}',
                    label=f"{vector_label}-character-limit-plus-one",
                )
            ),
            f"{vector_label} one decoded character above its limit",
        )
        expect_failure(
            lambda decoded_character=decoded_character, vector_label=vector_label: (
                validate_json_resource_bounds(
                    {"x": (decoded_character * (MAX_JSON_STRING_CHARS + 1))},
                    label=f"native-{vector_label}-character-limit-plus-one",
                )
            ),
            f"native {vector_label} one decoded character above its limit",
        )
    expect_failure(
        lambda: parse_json_bytes(b'{"x":1e999}', label="overflowing-float"),
        "an overflowing float",
    )
    expect_failure(
        lambda: parse_json_bytes(b'{"x":1e-999}', label="underflowing-float"),
        "an underflowing float",
    )
    expect_failure(
        lambda: parse_json_bytes(
            b'{"x":' + (b"9" * (MAX_JSON_NUMBER_CHARS + 1)) + b"}",
            label="oversized-integer",
        ),
        "an oversized integer",
    )
    expect_failure(
        lambda: parse_json_bytes(
            b'{"x":' + (b"9" * (MAX_JSON_NUMBER_CHARS + 1)) + b".0}",
            label="oversized-float-mantissa",
        ),
        "an oversized float mantissa",
    )
    expect_failure(
        lambda: parse_json_bytes(
            b'{"x":1e' + (b"9" * (MAX_JSON_NUMBER_CHARS + 1)) + b"}",
            label="oversized-float-exponent",
        ),
        "an oversized float exponent",
    )
    # Root depth is zero in the parser, native-tree validator, compact
    # expansion, and semantic commitment suites. Exercise both sides of the
    # exact boundary so that no layer can silently reintroduce root depth one.
    _preflight_json_text(
        "[[null]]",
        label="root-depth-0-small-maximum",
        maximum_depth=2,
    )
    expect_failure(
        lambda: _preflight_json_text(
            "[[[null]]]",
            label="root-depth-0-small-maximum-plus-one",
            maximum_depth=2,
        ),
        "root-depth-0 excess nesting",
    )
    maximum_depth_raw = (
        b'{"x":'
        + (b"[" * (MAX_JSON_DEPTH - 1))
        + b"null"
        + (b"]" * (MAX_JSON_DEPTH - 1))
        + b"}"
    )
    first_rejected_depth_raw = (
        b'{"x":' + (b"[" * MAX_JSON_DEPTH) + b"null" + (b"]" * MAX_JSON_DEPTH) + b"}"
    )
    maximum_depth_value = parse_json_bytes(
        maximum_depth_raw,
        label="root-depth-0-exact-maximum",
    )
    expect_failure(
        lambda: parse_json_bytes(
            first_rejected_depth_raw,
            label="root-depth-0-maximum-plus-one",
        ),
        "the first JSON depth beyond the root-depth-0 maximum",
    )
    validate_json_resource_bounds(
        maximum_depth_value,
        label="programmatic-root-depth-0-exact-maximum",
    )
    first_rejected_depth_value: Any = None
    for _ in range(MAX_JSON_DEPTH):
        first_rejected_depth_value = [first_rejected_depth_value]
    first_rejected_depth_value = {"x": first_rejected_depth_value}
    expect_failure(
        lambda: validate_json_resource_bounds(
            first_rejected_depth_value,
            label="programmatic-root-depth-0-maximum-plus-one",
        ),
        "the first programmatic depth beyond the root-depth-0 maximum",
    )
    expect_failure(
        lambda: _preflight_json_text(
            '"abcd"',
            label="string",
            maximum_string_chars=3,
        ),
        "an oversized string",
    )
    expect_failure(
        lambda: _preflight_json_text(
            "[0,1,2]",
            label="preflight-items",
            maximum_items=3,
        ),
        "too many JSON items before parsing",
    )
    expect_failure(
        lambda: _preflight_json_text(
            "[1234]",
            label="preflight-number",
            maximum_number_chars=3,
        ),
        "an oversized number token before parsing",
    )
    _preflight_json_text(
        "[true,false,null]",
        label="non-number-atoms-with-zero-number-limit",
        maximum_number_chars=0,
    )
    validate_json_resource_bounds(
        [True, False, None],
        label="native-non-number-atoms-with-zero-number-limit",
        maximum_number_chars=0,
    )
    expect_failure(
        lambda: _preflight_json_text(
            "0",
            label="one-character-number-with-zero-number-limit",
            maximum_number_chars=0,
        ),
        "a one-character number above a zero-character limit",
    )
    expect_failure(
        lambda: validate_json_resource_bounds(
            0,
            label="native-one-character-number-with-zero-number-limit",
            maximum_number_chars=0,
        ),
        "a native one-character number above a zero-character limit",
    )
    expect_failure(
        lambda: validate_json_resource_bounds(
            [0, 1, 2],
            label="items",
            maximum_items=3,
        ),
        "too many JSON items",
    )
    expect_failure(
        lambda: validate_json_resource_bounds(
            (0, 1),
            label="non-JSON-tuple",
        ),
        "a Python tuple as a JSON array",
    )
    expect_failure(
        lambda: validate_json_resource_bounds(
            type("HostileList", (list,), {})([0, 1]),
            label="non-native-list",
        ),
        "a list subclass as native JSON",
    )
    expect_failure(
        lambda: validate_json_resource_bounds(
            10**MAX_JSON_NUMBER_CHARS,
            label="programmatic-oversized-integer",
        ),
        "an oversized programmatic integer",
    )

    repeated = {
        "bounded_repeated_key": [
            "bounded repeated value long enough to intern",
            {"nested": "bounded repeated value long enough to intern"},
        ]
    }
    sample = {
        "candidate": "1.0.0-rc.1",
        "task": "B01",
        "normative": False,
        "left": copy.deepcopy(repeated),
        "middle": copy.deepcopy(repeated),
        "right": copy.deepcopy(repeated),
    }
    shared_mutable: list[Any] = []
    aliased_sample = {
        "candidate": "1.0.0-rc.1",
        "task": "B01",
        "normative": False,
        "left": shared_mutable,
        "right": shared_mutable,
    }
    expect_failure(
        lambda: compact_selector_source(aliased_sample),
        "a shared mutable encoder input",
    )
    cyclic_sample: dict[str, Any] = {
        "candidate": "1.0.0-rc.1",
        "task": "B01",
        "normative": False,
    }
    cyclic_sample["cycle"] = cyclic_sample
    expect_failure(
        lambda: compact_selector_source(cyclic_sample),
        "a cyclic encoder input",
    )
    expect_failure(
        lambda: compact_selector_source(
            {
                "candidate": "1.0.0-rc.1",
                "task": "B01",
                "normative": False,
                "tuple": ("not", "json"),
            }
        ),
        "a non-JSON encoder input",
    )
    expect_failure(
        lambda: compact_selector_source(
            {
                "candidate": "1.0.0-rc.1",
                "task": "B01",
                "normative": False,
                "integer": 10**MAX_JSON_NUMBER_CHARS,
            }
        ),
        "an overlong programmatic integer during encoding",
    )
    envelope = compact_selector_source(sample)
    aliased_compact_envelope = copy.deepcopy(envelope)
    shared_compact_object: list[Any] = []
    aliased_compact_envelope["encoding"]["object_table"] = [
        shared_compact_object,
        shared_compact_object,
    ]
    expect_failure(
        lambda: decode_compact_source(aliased_compact_envelope),
        "a shared mutable compact-envelope subtree",
    )
    _require(
        envelope["encoding"]["object_table"],
        "codec self-test did not create an object-table reference",
    )
    duplicate_decoded_key = copy.deepcopy(envelope)
    duplicate_decoded_key["encoding"]["string_table"] = ["duplicate"]
    duplicate_decoded_key["encoding"]["object_table"] = []
    duplicate_decoded_key["payload"] = {
        "duplicate": 1,
        "@S0000": 2,
    }
    expect_failure(
        lambda: decode_compact_source(duplicate_decoded_key),
        "duplicate object keys after string-token expansion",
    )
    out_of_range_token = copy.deepcopy(envelope)
    out_of_range_token["encoding"]["string_table"] = []
    out_of_range_token["encoding"]["object_table"] = []
    out_of_range_token["payload"] = {"value": "@S0000"}
    expect_failure(
        lambda: decode_compact_source(out_of_range_token),
        "an out-of-range compact token",
    )
    cyclic_object_table = copy.deepcopy(envelope)
    cyclic_object_table["encoding"]["string_table"] = []
    cyclic_object_table["encoding"]["object_table"] = [["@O0000"]]
    cyclic_object_table["payload"] = {}
    expect_failure(
        lambda: decode_compact_source(cyclic_object_table),
        "an unreferenced object-table cycle",
    )
    deep_object_table = copy.deepcopy(envelope)
    deep_object_table["encoding"]["string_table"] = []
    deep_object_table["encoding"]["object_table"] = [
        [f"@O{index + 1:04X}"] for index in range(MAX_JSON_DEPTH - 1)
    ] + [[None]]
    deep_object_table["payload"] = {
        "candidate": deep_object_table["candidate"],
        "normative": deep_object_table["normative"],
        "task": deep_object_table["task"],
        "x": "@O0000",
    }
    deep_expanded_member: Any = None
    for _ in range(MAX_JSON_DEPTH):
        deep_expanded_member = [deep_expanded_member]
    deep_expanded_value = {
        "candidate": deep_object_table["candidate"],
        "normative": deep_object_table["normative"],
        "task": deep_object_table["task"],
        "x": deep_expanded_member,
    }
    deep_object_table["encoding"]["string_table_sha256"] = canonical_sha256(
        deep_object_table["encoding"]["string_table"]
    )
    deep_object_table["encoding"]["object_table_sha256"] = canonical_sha256(
        deep_object_table["encoding"]["object_table"]
    )
    deep_object_table["encoding"]["expanded_document_sha256"] = canonical_sha256(
        deep_expanded_value
    )
    _validate_compact_envelope(deep_object_table, raw=None)
    expect_failure(
        lambda: decode_compact_source(deep_object_table),
        "a commitment-valid depth-65 object-table expansion",
    )
    maximum_depth_object_table = [
        [f"@O{index + 1:04X}"] for index in range(MAX_JSON_DEPTH)
    ] + [[]]
    _preflight_compact_expansion(
        "@O0000",
        strings=[],
        objects=maximum_depth_object_table,
        maximum_expanded_bytes=MAX_EXPANDED_BYTES,
    )
    first_rejected_depth_object_table = [
        [f"@O{index + 1:04X}"] for index in range(MAX_JSON_DEPTH + 1)
    ] + [[]]
    expect_failure(
        lambda: _preflight_compact_expansion(
            "@O0000",
            strings=[],
            objects=first_rejected_depth_object_table,
            maximum_expanded_bytes=MAX_EXPANDED_BYTES,
        ),
        "the first compact expansion depth beyond the root-depth-0 maximum",
    )
    expansion_bomb = copy.deepcopy(envelope)
    expansion_bomb["encoding"]["string_table"] = []
    expansion_bomb["encoding"]["object_table"] = [["bounded"]]
    for object_index in range(1, 24):
        prior_token = f"@O{object_index - 1:04X}"
        expansion_bomb["encoding"]["object_table"].append([prior_token, prior_token])
    expansion_bomb["payload"] = "@O0017"
    expect_failure(
        lambda: decode_compact_source(expansion_bomb),
        "an exponentially expanding object table",
    )
    exact_strings = ["expanded-key", "expanded-value"]
    exact_objects = [{"@S0000": ["@S0001", "@S0001"]}]
    exact_payload = {"copies": ["@O0000", "@O0000"]}
    exact_expanded = {
        "copies": [
            {"expanded-key": ["expanded-value", "expanded-value"]},
            {"expanded-key": ["expanded-value", "expanded-value"]},
        ]
    }
    exact_expanded_bytes = len(canonical_bytes(exact_expanded))
    _preflight_compact_expansion(
        exact_payload,
        strings=exact_strings,
        objects=exact_objects,
        maximum_expanded_bytes=exact_expanded_bytes,
    )
    expect_failure(
        lambda: _preflight_compact_expansion(
            exact_payload,
            strings=exact_strings,
            objects=exact_objects,
            maximum_expanded_bytes=exact_expanded_bytes - 1,
        ),
        "an expansion one byte above its exact canonical limit",
    )
    decoded = decode_compact_source(envelope)
    require_unaliased_mutable_tree(decoded, label="codec self-test")
    decoded["left"]["bounded_repeated_key"][1]["nested"] = "changed"
    _require_exact(
        decoded["right"]["bounded_repeated_key"][1]["nested"],
        "bounded repeated value long enough to intern",
        "decoded object-table reference isolation",
    )
    expect_failure(
        lambda: compact_selector_source(
            sample,
            maximum_expanded_bytes=64,
        ),
        "an oversized expanded source during encoding",
    )
    nested_repetition: dict[str, Any] = {
        "leaf": "bounded encoder ordering material",
    }
    for layer in range(32):
        nested_repetition = {
            "child": nested_repetition,
            "layer": layer,
        }
    ordering_work_sample = {
        "candidate": "1.0.0-rc.1",
        "task": "B01",
        "normative": False,
        "left": copy.deepcopy(nested_repetition),
        "right": copy.deepcopy(nested_repetition),
    }
    expect_failure(
        lambda: compact_selector_source(
            ordering_work_sample,
            maximum_expanded_bytes=len(canonical_bytes(ordering_work_sample)),
        ),
        "over-budget cumulative object-table ordering material",
    )
    expect_failure(
        lambda: decode_compact_source(
            envelope,
            maximum_expanded_bytes=64,
        ),
        "an oversized expanded source during decoding",
    )

    def write_test_file(path: Path, raw: bytes) -> None:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    with tempfile.TemporaryDirectory(
        prefix="ncp-selector-codec-path-self-test-"
    ) as directory_name:
        directory = Path(directory_name).resolve(strict=True)
        expect_failure(
            lambda: read_bounded_regular_file(
                Path(f"{directory_name}/bad\x00path"),
                maximum_bytes=64,
                label="codec NUL-path self-test",
            ),
            "a NUL path component",
        )
        stable_directory = directory / "stable"
        stable_directory.mkdir()
        stable_input = stable_directory / "input.json"
        write_test_file(stable_input, b'{"stable":true}\n')
        _require_exact(
            read_bounded_regular_file(
                stable_input,
                maximum_bytes=64,
                label="codec stable read self-test",
            ),
            b'{"stable":true}\n',
            "anchored regular-file read",
        )
        original_read = os.read

        def one_byte_read(descriptor: int, size: int) -> bytes:
            return original_read(descriptor, min(size, 1))

        os.read = one_byte_read
        try:
            _require_exact(
                read_bounded_regular_file(
                    stable_input,
                    maximum_bytes=64,
                    label="codec partial-read self-test",
                ),
                b'{"stable":true}\n',
                "partial descriptor reads",
            )
        finally:
            os.read = original_read

        def premature_eof(_descriptor: int, _size: int) -> bytes:
            return b""

        os.read = premature_eof
        try:
            expect_failure(
                lambda: read_bounded_regular_file(
                    stable_input,
                    maximum_bytes=64,
                    label="codec premature-EOF self-test",
                ),
                "a premature regular-file EOF",
            )
        finally:
            os.read = original_read

        read_close_input = stable_directory / "read-close.json"
        write_test_file(read_close_input, b'{"close":"checked"}\n')
        original_close = os.close
        read_close_injected = False

        def close_regular_read_descriptor(descriptor: int) -> None:
            nonlocal read_close_injected
            is_regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
            original_close(descriptor)
            if is_regular and not read_close_injected:
                read_close_injected = True
                raise OSError("injected read descriptor close failure")

        def arm_read_close_failure(phase: str) -> None:
            if phase == "read-complete":
                os.close = close_regular_read_descriptor

        try:
            expect_failure(
                lambda: _read_bounded_regular_file(
                    read_close_input,
                    maximum_bytes=64,
                    label="codec read-close self-test",
                    phase_hook=arm_read_close_failure,
                ),
                "a read descriptor close failure",
            )
        finally:
            os.close = original_close
        _require(
            read_close_injected,
            "read descriptor close failure hook did not run",
        )

        stable_output = stable_directory / "output.json"
        atomic_write_regular_file(
            stable_output,
            b'{"version":1}\n',
            label="codec stable write self-test",
        )
        atomic_write_regular_file(
            stable_output,
            b'{"version":2}\n',
            label="codec stable replacement self-test",
        )
        _require_exact(
            read_bounded_regular_file(
                stable_output,
                maximum_bytes=64,
                label="codec installed output self-test",
            ),
            b'{"version":2}\n',
            "anchored atomic replacement",
        )
        cas_output = stable_directory / "expected-current-cas.json"
        cas_v1 = b'{"version":"cas-v1"}\n'
        cas_v2 = b'{"version":"cas-v2"}\n'
        atomic_write_regular_file(
            cas_output,
            cas_v1,
            label="codec expected-current CAS seed",
        )
        _atomic_write_regular_file(
            cas_output,
            cas_v2,
            expected_current=cas_v1,
            label="codec expected-current CAS success",
        )
        _require_exact(
            read_bounded_regular_file(
                cas_output,
                maximum_bytes=64,
                label="codec expected-current CAS result",
            ),
            cas_v2,
            "same-dirfd expected-current CAS",
        )
        expect_failure(
            lambda: _atomic_write_regular_file(
                cas_output,
                b'{"version":"must-not-install"}\n',
                expected_current=cas_v1,
                label="codec stale expected-current CAS",
            ),
            "a stale expected-current CAS",
        )
        _require_exact(
            read_bounded_regular_file(
                cas_output,
                maximum_bytes=64,
                label="codec stale CAS unchanged result",
            ),
            cas_v2,
            "failed expected-current CAS leaves bytes unchanged",
        )

        original_working_directory = Path.cwd()
        relative_path_root = directory / "relative-path"
        relative_path_parent = relative_path_root / "parent"
        relative_path_parent.mkdir(parents=True)
        relative_path_output = relative_path_parent / "output.json"
        working_directory_changed = False

        def change_working_directory(phase: str) -> None:
            nonlocal working_directory_changed
            if phase == "before-install":
                working_directory_changed = True
                os.chdir(original_working_directory)

        os.chdir(relative_path_root)
        try:
            _atomic_write_regular_file(
                Path("parent/output.json"),
                b'{"relative":"bound-at-entry"}\n',
                label="codec relative-path self-test",
                phase_hook=change_working_directory,
            )
        finally:
            os.chdir(original_working_directory)
        _require(
            working_directory_changed,
            "relative-path working-directory hook did not run",
        )
        _require_exact(
            relative_path_output.read_bytes(),
            b'{"relative":"bound-at-entry"}\n',
            "entry-bound relative path",
        )

        lock_lifetime_output = stable_directory / "lock-lifetime.json"
        lock_lifetime_checked = False

        def check_parent_lock_lifetime(phase: str) -> None:
            nonlocal lock_lifetime_checked
            if phase != "before-install":
                return
            lock_lifetime_checked = True
            # The executable and argv are locally constructed constants.
            lock_probe = subprocess.run(  # noqa: S603
                [
                    sys.executable,
                    "-c",
                    (
                        "import fcntl, os, sys\n"
                        "descriptor = os.open(sys.argv[1], "
                        "os.O_RDONLY | os.O_DIRECTORY)\n"
                        "try:\n"
                        "    fcntl.flock(descriptor, "
                        "fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
                        "except BlockingIOError:\n"
                        "    raise SystemExit(0)\n"
                        "raise SystemExit(1)\n"
                    ),
                    os.fspath(stable_directory),
                ],
                check=False,
                close_fds=True,
                timeout=10,
            )
            _require_exact(
                lock_probe.returncode,
                0,
                "cooperative parent lock lifetime",
            )

        _atomic_write_regular_file(
            lock_lifetime_output,
            b'{"lock":"held"}\n',
            label="codec lock-lifetime self-test",
            phase_hook=check_parent_lock_lifetime,
        )
        _require(
            lock_lifetime_checked,
            "parent lock-lifetime hook did not run",
        )
        partial_write_output = stable_directory / "partial-write.json"
        original_write = os.write

        def one_byte_write(descriptor: int, value: Any) -> int:
            return original_write(descriptor, value[:1])

        os.write = one_byte_write
        try:
            atomic_write_regular_file(
                partial_write_output,
                b'{"partial":"write"}\n',
                label="codec partial-write self-test",
            )
        finally:
            os.write = original_write
        _require_exact(
            partial_write_output.read_bytes(),
            b'{"partial":"write"}\n',
            "partial descriptor writes",
        )

        create_only_output = stable_directory / "create-only.json"
        create_only_durable_shape_seen = False

        def inspect_create_only_install(phase: str) -> None:
            nonlocal create_only_durable_shape_seen
            if phase != "parent-directory-fsynced":
                return
            create_only_durable_shape_seen = True
            installed = create_only_output.stat()
            _require(
                installed.st_nlink == 1,
                "create-only output retained a temporary hardlink",
            )
            _require(
                not list(stable_directory.glob(".ncp-*.tmp")),
                "create-only output fsynced before temporary-name removal",
            )

        _atomic_write_regular_file(
            create_only_output,
            b'{"created":true}\n',
            label="codec create-only self-test",
            create_only=True,
            phase_hook=inspect_create_only_install,
        )
        _require(
            create_only_durable_shape_seen,
            "create-only directory-fsync hook did not run",
        )
        expect_failure(
            lambda: atomic_write_regular_file(
                create_only_output,
                b'{"clobbered":true}\n',
                label="codec create-only collision self-test",
                create_only=True,
            ),
            "a create-only destination collision",
        )
        _require_exact(
            create_only_output.read_bytes(),
            b'{"created":true}\n',
            "create-only collision target",
        )

        directory_fsync_output = stable_directory / "directory-fsync.json"
        original_fsync = os.fsync
        directory_fsync_injected = False

        def fail_directory_fsync(descriptor: int) -> None:
            nonlocal directory_fsync_injected
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                directory_fsync_injected = True
                raise OSError("injected directory fsync failure")
            original_fsync(descriptor)

        def arm_directory_fsync_failure(phase: str) -> None:
            if phase == "before-install":
                os.fsync = fail_directory_fsync

        try:
            expect_outcome_unknown(
                lambda: _atomic_write_regular_file(
                    directory_fsync_output,
                    b'{"installed":"unknown-durability"}\n',
                    label="codec directory-fsync-failure self-test",
                    create_only=True,
                    phase_hook=arm_directory_fsync_failure,
                ),
                "a create-only directory fsync failure",
            )
        finally:
            os.fsync = original_fsync
        _require(
            directory_fsync_injected,
            "directory fsync failure hook did not run",
        )
        _require_exact(
            directory_fsync_output.read_bytes(),
            b'{"installed":"unknown-durability"}\n',
            "directory fsync failure installed bytes",
        )
        _require(
            directory_fsync_output.stat().st_nlink == 1
            and not list(stable_directory.glob(".ncp-*.tmp")),
            "directory fsync failure left an invalid link shape",
        )

        preinstall_hook_output = stable_directory / "preinstall-hook.json"
        preinstall_hook_ran = False

        def fail_before_install(phase: str) -> None:
            nonlocal preinstall_hook_ran
            if phase == "temporary-file-fsynced":
                preinstall_hook_ran = True
                raise RuntimeError("injected pre-install hook failure")

        try:
            _atomic_write_regular_file(
                preinstall_hook_output,
                b'{"must":"not-install"}\n',
                label="codec pre-install-hook self-test",
                phase_hook=fail_before_install,
            )
        except RuntimeError:
            pass
        else:
            _fail("codec self-test accepted a pre-install hook failure")
        _require(
            preinstall_hook_ran
            and not preinstall_hook_output.exists()
            and not list(stable_directory.glob(".ncp-*.tmp")),
            "pre-install hook failure did not clean up exactly",
        )

        postinstall_hook_output = stable_directory / "postinstall-hook.json"
        postinstall_hook_ran = False

        def fail_after_directory_fsync(phase: str) -> None:
            nonlocal postinstall_hook_ran
            if phase == "parent-directory-fsynced":
                postinstall_hook_ran = True
                raise RuntimeError("injected post-install hook failure")

        expect_outcome_unknown(
            lambda: _atomic_write_regular_file(
                postinstall_hook_output,
                b'{"installed":"before-hook-failure"}\n',
                label="codec post-install-hook self-test",
                phase_hook=fail_after_directory_fsync,
            ),
            "a post-install hook failure",
        )
        _require(postinstall_hook_ran, "post-install hook did not run")
        _require_exact(
            postinstall_hook_output.read_bytes(),
            b'{"installed":"before-hook-failure"}\n',
            "post-install hook failure output",
        )

        cleanup_close_output = stable_directory / "cleanup-close.json"
        original_close = os.close
        cleanup_close_injected = False

        def close_installed_descriptor(descriptor: int) -> None:
            nonlocal cleanup_close_injected
            is_regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
            original_close(descriptor)
            if is_regular and not cleanup_close_injected:
                cleanup_close_injected = True
                raise OSError("injected installed descriptor close failure")

        def arm_cleanup_close_failure(phase: str) -> None:
            if phase == "parent-directory-fsynced":
                os.close = close_installed_descriptor

        try:
            expect_outcome_unknown(
                lambda: _atomic_write_regular_file(
                    cleanup_close_output,
                    b'{"installed":"before-close-failure"}\n',
                    label="codec cleanup-close self-test",
                    phase_hook=arm_cleanup_close_failure,
                ),
                "an installed descriptor close failure",
            )
        finally:
            os.close = original_close
        _require(
            cleanup_close_injected,
            "installed descriptor close failure hook did not run",
        )
        _require_exact(
            cleanup_close_output.read_bytes(),
            b'{"installed":"before-close-failure"}\n',
            "installed descriptor close failure output",
        )

        interrupted_install_output = stable_directory / "interrupted-install.json"
        write_test_file(interrupted_install_output, b'{"installed":"old"}\n')
        original_rename = os.rename
        original_fsync = os.fsync
        install_interrupted = False
        interrupted_install_directory_fsyncs = 0

        def rename_then_interrupt(
            source: Any,
            destination: Any,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
        ) -> None:
            nonlocal install_interrupted
            original_rename(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
            )
            install_interrupted = True
            raise KeyboardInterrupt("injected post-rename interruption")

        def count_interrupted_install_fsync(descriptor: int) -> None:
            nonlocal interrupted_install_directory_fsyncs
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                interrupted_install_directory_fsyncs += 1
            original_fsync(descriptor)

        def arm_interrupted_install(phase: str) -> None:
            if phase == "before-install":
                os.rename = rename_then_interrupt
                os.fsync = count_interrupted_install_fsync

        try:
            expect_outcome_unknown(
                lambda: _atomic_write_regular_file(
                    interrupted_install_output,
                    b'{"installed":"before-interruption"}\n',
                    label="codec interrupted-install self-test",
                    phase_hook=arm_interrupted_install,
                ),
                "an interruption after a successful rename",
            )
        finally:
            os.rename = original_rename
            os.fsync = original_fsync
        _require(
            install_interrupted,
            "post-rename interruption hook did not run",
        )
        _require_exact(
            interrupted_install_directory_fsyncs,
            1,
            "post-rename interruption recovery directory fsync",
        )
        _require_exact(
            interrupted_install_output.read_bytes(),
            b'{"installed":"before-interruption"}\n',
            "post-rename interruption output",
        )
        _require(
            not list(stable_directory.glob(".ncp-*.tmp")),
            "post-rename interruption left a temporary path",
        )

        interrupted_link_output = stable_directory / "interrupted-link.json"
        original_link = os.link
        original_fsync = os.fsync
        link_interrupted = False
        interrupted_link_directory_fsyncs = 0

        def link_then_interrupt(
            source: Any,
            destination: Any,
            *,
            src_dir_fd: int | None = None,
            dst_dir_fd: int | None = None,
            follow_symlinks: bool = True,
        ) -> None:
            nonlocal link_interrupted
            original_link(
                source,
                destination,
                src_dir_fd=src_dir_fd,
                dst_dir_fd=dst_dir_fd,
                follow_symlinks=follow_symlinks,
            )
            link_interrupted = True
            raise KeyboardInterrupt("injected post-link interruption")

        def count_interrupted_link_fsync(descriptor: int) -> None:
            nonlocal interrupted_link_directory_fsyncs
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                interrupted_link_directory_fsyncs += 1
            original_fsync(descriptor)

        def arm_interrupted_link(phase: str) -> None:
            if phase == "before-install":
                os.link = link_then_interrupt
                os.fsync = count_interrupted_link_fsync

        try:
            expect_outcome_unknown(
                lambda: _atomic_write_regular_file(
                    interrupted_link_output,
                    b'{"installed":"before-link-interruption"}\n',
                    label="codec interrupted-link self-test",
                    create_only=True,
                    phase_hook=arm_interrupted_link,
                ),
                "an interruption after a successful create-only link",
            )
        finally:
            os.link = original_link
            os.fsync = original_fsync
        _require(
            link_interrupted,
            "post-link interruption hook did not run",
        )
        _require_exact(
            interrupted_link_directory_fsyncs,
            1,
            "post-link interruption recovery directory fsync",
        )
        _require_exact(
            interrupted_link_output.read_bytes(),
            b'{"installed":"before-link-interruption"}\n',
            "post-link interruption output",
        )
        _require(
            interrupted_link_output.stat().st_nlink == 1
            and not list(stable_directory.glob(".ncp-*.tmp")),
            "post-link interruption left an invalid link shape",
        )

        temp_rebind_output = stable_directory / "temp-rebind.json"
        temp_rebound = False

        def rebind_temporary_name(phase: str) -> None:
            nonlocal temp_rebound
            if phase != "temporary-file-fsynced" or temp_rebound:
                return
            temp_rebound = True
            candidates = list(stable_directory.glob(".ncp-*.tmp"))
            _require_exact(
                len(candidates),
                1,
                "temporary rebind candidate count",
            )
            candidates[0].unlink()
            write_test_file(candidates[0], b'{"hostile":0}\n')

        expect_failure(
            lambda: _atomic_write_regular_file(
                temp_rebind_output,
                b'{"trusted":1}\n',
                label="codec temporary-rebind self-test",
                phase_hook=rebind_temporary_name,
            ),
            "a rebound temporary pathname",
        )
        _require(temp_rebound, "temporary-rebind hook did not run")
        _require(
            not temp_rebind_output.exists(),
            "temporary rebind installed an output",
        )
        _require(
            not list(stable_directory.glob(".ncp-*.tmp")),
            "temporary rebind left a named temporary file",
        )

        hardlink_alias = stable_directory / "hardlink-alias"
        write_test_file(hardlink_alias, b'{"trusted":1}\n')
        hardlink_output = stable_directory / "hardlink-output"
        hardlink_rebound = False

        def inject_temporary_hardlink(phase: str) -> None:
            nonlocal hardlink_rebound
            if phase != "temporary-file-fsynced" or hardlink_rebound:
                return
            hardlink_rebound = True
            candidates = list(stable_directory.glob(".ncp-*.tmp"))
            _require_exact(
                len(candidates),
                1,
                "temporary hardlink candidate count",
            )
            candidates[0].unlink()
            os.link(hardlink_alias, candidates[0])

        expect_failure(
            lambda: _atomic_write_regular_file(
                hardlink_output,
                b'{"trusted":1}\n',
                label="codec temporary-hardlink self-test",
                phase_hook=inject_temporary_hardlink,
            ),
            "a hardlink-rebound temporary pathname",
        )
        _require(hardlink_rebound, "temporary-hardlink hook did not run")
        _require(
            not hardlink_output.exists(),
            "temporary hardlink installed an output",
        )
        _require_exact(
            hardlink_alias.read_bytes(),
            b'{"trusted":1}\n',
            "hardlink injection alias",
        )

        leaf_symlink = stable_directory / "leaf-symlink"
        leaf_symlink.symlink_to(stable_input)
        expect_failure(
            lambda: read_bounded_regular_file(
                leaf_symlink,
                maximum_bytes=64,
                label="codec leaf-symlink self-test",
            ),
            "a leaf symlink",
        )
        expect_failure(
            lambda: atomic_write_regular_file(
                leaf_symlink,
                b"replacement\n",
                label="codec output-symlink self-test",
            ),
            "an output symlink",
        )

        ancestor_symlink = directory / "ancestor-symlink"
        ancestor_symlink.symlink_to(stable_directory, target_is_directory=True)
        expect_failure(
            lambda: read_bounded_regular_file(
                ancestor_symlink / stable_input.name,
                maximum_bytes=64,
                label="codec ancestor-symlink self-test",
            ),
            "an ancestor symlink",
        )

        parent_mode_read_directory = directory / "parent-mode-read"
        parent_mode_read_directory.mkdir(mode=0o700)
        parent_mode_read_input = parent_mode_read_directory / "input"
        write_test_file(parent_mode_read_input, b"trusted\n")
        parent_mode_read_changed = False

        def loosen_read_parent(phase: str) -> None:
            nonlocal parent_mode_read_changed
            if phase == "read-complete":
                parent_mode_read_changed = True
                parent_mode_read_directory.chmod(0o777)

        try:
            expect_failure(
                lambda: _read_bounded_regular_file(
                    parent_mode_read_input,
                    maximum_bytes=64,
                    label="codec parent-mode-read self-test",
                    phase_hook=loosen_read_parent,
                ),
                "a parent that became world-writable during read",
            )
        finally:
            parent_mode_read_directory.chmod(0o700)
        _require(
            parent_mode_read_changed,
            "parent-mode read hook did not run",
        )

        parent_mode_write_directory = directory / "parent-mode-write"
        parent_mode_write_directory.mkdir(mode=0o700)
        parent_mode_write_output = parent_mode_write_directory / "output"
        write_test_file(parent_mode_write_output, b"original\n")
        parent_mode_write_changed = False

        def loosen_write_parent(phase: str) -> None:
            nonlocal parent_mode_write_changed
            if phase == "before-install":
                parent_mode_write_changed = True
                parent_mode_write_directory.chmod(0o777)

        try:
            expect_failure(
                lambda: _atomic_write_regular_file(
                    parent_mode_write_output,
                    b"must-not-install\n",
                    label="codec parent-mode-write self-test",
                    phase_hook=loosen_write_parent,
                ),
                "a parent that became world-writable before install",
            )
        finally:
            parent_mode_write_directory.chmod(0o700)
        _require(
            parent_mode_write_changed,
            "parent-mode write hook did not run",
        )
        _require_exact(
            parent_mode_write_output.read_bytes(),
            b"original\n",
            "parent-mode write target",
        )
        _require(
            not list(parent_mode_write_directory.glob(".ncp-*.tmp")),
            "parent-mode write failure left a temporary file",
        )

        read_race_directory = directory / "read-race"
        read_race_directory.mkdir()
        read_race_input = read_race_directory / "input"
        write_test_file(read_race_input, b"original\n")
        moved_read_directory = directory / "read-race-moved"
        read_race_swapped = False

        def swap_read_ancestor(phase: str) -> None:
            nonlocal read_race_swapped
            if phase != "parent-opened" or read_race_swapped:
                return
            read_race_swapped = True
            read_race_directory.rename(moved_read_directory)
            read_race_directory.mkdir()
            write_test_file(read_race_input, b"replacement\n")

        expect_failure(
            lambda: _read_bounded_regular_file(
                read_race_input,
                maximum_bytes=64,
                label="codec ancestor-read-race self-test",
                phase_hook=swap_read_ancestor,
            ),
            "an ancestor replacement during read",
        )
        _require(read_race_swapped, "ancestor read-race hook did not run")
        _require_exact(
            (moved_read_directory / "input").read_bytes(),
            b"original\n",
            "held read directory content",
        )
        _require_exact(
            read_race_input.read_bytes(),
            b"replacement\n",
            "replacement read directory content",
        )

        read_leaf_race = stable_directory / "read-leaf-race"
        read_leaf_replacement = stable_directory / "read-leaf-replacement"
        write_test_file(read_leaf_race, b"original\n")
        write_test_file(read_leaf_replacement, b"replaced\n")
        read_leaf_swapped = False

        def swap_read_leaf(phase: str) -> None:
            nonlocal read_leaf_swapped
            if phase != "read-complete" or read_leaf_swapped:
                return
            read_leaf_swapped = True
            os.replace(read_leaf_replacement, read_leaf_race)

        expect_failure(
            lambda: _read_bounded_regular_file(
                read_leaf_race,
                maximum_bytes=64,
                label="codec leaf-read-race self-test",
                phase_hook=swap_read_leaf,
            ),
            "a leaf replacement at read completion",
        )
        _require(read_leaf_swapped, "leaf read-race hook did not run")
        _require_exact(
            read_leaf_race.read_bytes(),
            b"replaced\n",
            "replacement read leaf",
        )

        write_race_directory = directory / "write-race"
        write_race_directory.mkdir()
        write_race_output = write_race_directory / "output"
        write_test_file(write_race_output, b"original\n")
        moved_write_directory = directory / "write-race-moved"
        write_race_swapped = False

        def swap_write_ancestor(phase: str) -> None:
            nonlocal write_race_swapped
            if phase != "temporary-file-fsynced" or write_race_swapped:
                return
            write_race_swapped = True
            write_race_directory.rename(moved_write_directory)
            write_race_directory.mkdir()
            write_test_file(write_race_output, b"replacement\n")

        expect_failure(
            lambda: _atomic_write_regular_file(
                write_race_output,
                b"new-output\n",
                label="codec ancestor-write-race self-test",
                phase_hook=swap_write_ancestor,
            ),
            "an ancestor replacement during atomic write",
        )
        _require(write_race_swapped, "ancestor write-race hook did not run")
        _require_exact(
            (moved_write_directory / "output").read_bytes(),
            b"original\n",
            "held write directory target",
        )
        _require_exact(
            write_race_output.read_bytes(),
            b"replacement\n",
            "replacement write directory target",
        )
        _require(
            not list(moved_write_directory.glob(".ncp-*.tmp")),
            "atomic-write race left a temporary file",
        )

        target_race_output = stable_directory / "target-race-output"
        target_race_replacement = stable_directory / "target-race-replacement"
        write_test_file(target_race_output, b"original\n")
        write_test_file(target_race_replacement, b"replacement\n")
        target_race_swapped = False

        def swap_install_target(phase: str) -> None:
            nonlocal target_race_swapped
            if phase != "before-install" or target_race_swapped:
                return
            target_race_swapped = True
            os.replace(target_race_replacement, target_race_output)

        expect_failure(
            lambda: _atomic_write_regular_file(
                target_race_output,
                b"new-output\n",
                label="codec target-write-race self-test",
                phase_hook=swap_install_target,
            ),
            "a destination replacement before install",
        )
        _require(target_race_swapped, "target write-race hook did not run")
        _require_exact(
            target_race_output.read_bytes(),
            b"replacement\n",
            "destination race target",
        )

        target_hardlink_output = stable_directory / "target-hardlink-output"
        target_hardlink_alias = stable_directory / "target-hardlink-alias"
        write_test_file(target_hardlink_output, b"original\n")
        target_hardlink_injected = False

        def hardlink_install_target(phase: str) -> None:
            nonlocal target_hardlink_injected
            if phase != "before-install" or target_hardlink_injected:
                return
            target_hardlink_injected = True
            os.link(target_hardlink_output, target_hardlink_alias)

        expect_failure(
            lambda: _atomic_write_regular_file(
                target_hardlink_output,
                b"must-not-install\n",
                label="codec target-hardlink self-test",
                phase_hook=hardlink_install_target,
            ),
            "a destination hardlink added before install",
        )
        _require(
            target_hardlink_injected,
            "target hardlink hook did not run",
        )
        _require_exact(
            target_hardlink_output.read_bytes(),
            b"original\n",
            "target hardlink output",
        )
        target_hardlink_alias.unlink()
        _require(
            not list(stable_directory.glob(".ncp-*.tmp")),
            "target hardlink failure left a temporary file",
        )

        appearance_output = stable_directory / "create-only-appearance"
        appearance_injected = False

        def inject_create_only_target(phase: str) -> None:
            nonlocal appearance_injected
            if phase != "before-install" or appearance_injected:
                return
            appearance_injected = True
            write_test_file(appearance_output, b"other-writer\n")

        expect_failure(
            lambda: _atomic_write_regular_file(
                appearance_output,
                b"generated\n",
                label="codec create-only-appearance self-test",
                create_only=True,
                phase_hook=inject_create_only_target,
            ),
            "a create-only target that appeared before install",
        )
        _require(appearance_injected, "create-only appearance hook did not run")
        _require_exact(
            appearance_output.read_bytes(),
            b"other-writer\n",
            "create-only appearance target",
        )

        late_parent_directory = directory / "late-parent-race"
        late_parent_directory.mkdir()
        late_parent_output = late_parent_directory / "output"
        write_test_file(late_parent_output, b"original\n")
        moved_late_parent = directory / "late-parent-race-moved"
        late_parent_swapped = False

        def swap_parent_before_install(phase: str) -> None:
            nonlocal late_parent_swapped
            if phase != "before-install" or late_parent_swapped:
                return
            late_parent_swapped = True
            late_parent_directory.rename(moved_late_parent)
            late_parent_directory.mkdir()
            write_test_file(late_parent_output, b"replacement\n")

        expect_failure(
            lambda: _atomic_write_regular_file(
                late_parent_output,
                b"new-output\n",
                label="codec late-parent-write-race self-test",
                phase_hook=swap_parent_before_install,
            ),
            "an ancestor replacement immediately before install",
        )
        _require(late_parent_swapped, "late parent-race hook did not run")
        _require_exact(
            (moved_late_parent / "output").read_bytes(),
            b"original\n",
            "late parent-race held target",
        )
        _require_exact(
            late_parent_output.read_bytes(),
            b"replacement\n",
            "late parent-race replacement target",
        )

        postinstall_parent_directory = directory / "postinstall-parent-race"
        postinstall_parent_directory.mkdir()
        postinstall_parent_output = postinstall_parent_directory / "output"
        write_test_file(postinstall_parent_output, b"original\n")
        moved_postinstall_parent = directory / "postinstall-parent-race-moved"
        postinstall_parent_swapped = False

        def swap_parent_after_fsync(phase: str) -> None:
            nonlocal postinstall_parent_swapped
            if phase != "parent-directory-fsynced" or postinstall_parent_swapped:
                return
            postinstall_parent_swapped = True
            postinstall_parent_directory.rename(moved_postinstall_parent)
            postinstall_parent_directory.mkdir()
            write_test_file(postinstall_parent_output, b"replacement\n")

        expect_outcome_unknown(
            lambda: _atomic_write_regular_file(
                postinstall_parent_output,
                b"new-output\n",
                label="codec postinstall-parent-race self-test",
                phase_hook=swap_parent_after_fsync,
            ),
            "an ancestor replacement after directory fsync",
        )
        _require(
            postinstall_parent_swapped,
            "postinstall parent-race hook did not run",
        )
        _require_exact(
            (moved_postinstall_parent / "output").read_bytes(),
            b"new-output\n",
            "postinstall parent-race held target",
        )
        _require_exact(
            postinstall_parent_output.read_bytes(),
            b"replacement\n",
            "postinstall parent-race replacement target",
        )
