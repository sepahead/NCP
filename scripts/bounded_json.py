#!/usr/bin/env python3
"""Bound JSON resources and physical file reads before semantic validation.

The parser performs an iterative JSON grammar and resource preflight before it
calls the standard-library JSON decoder. The decoder remains the source of the
native Python value, but it never receives an input that exceeds the explicit
limits supplied by its caller.

The file reader returns one stable snapshot of a non-symlink regular file. It
opens every path component with fail-closed POSIX directory-descriptor
operations, checks the leaf size before allocation, and verifies the opened
inode and path after the read.
"""

from __future__ import annotations

import json
import math
import os
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, NoReturn

_JSON_WHITESPACE = frozenset(" \t\r\n")
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_MAX_PATH_UTF8_BYTES = 16 * 1024
_MAX_PATH_COMPONENTS = 256
_MAX_PATH_COMPONENT_UTF8_BYTES = 255
_SIMPLE_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


class BoundedJsonError(ValueError):
    """Input is not bounded JSON or a file is not one stable snapshot."""


def _fail(message: str) -> NoReturn:
    raise BoundedJsonError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _bounded_native_utf8_length(
    value: Any,
    *,
    maximum: int,
    label: str,
) -> int:
    _require(type(value) is str, f"{label}: text type is not exact")
    _require(len(value) <= maximum, f"{label}: text exceeds {maximum} UTF-8 bytes")
    total = 0
    for character in value:
        code_point = ord(character)
        _require(
            not 0xD800 <= code_point <= 0xDFFF,
            f"{label}: text is not a Unicode scalar sequence",
        )
        total += (
            1
            if code_point <= 0x7F
            else 2
            if code_point <= 0x7FF
            else 3
            if code_point <= 0xFFFF
            else 4
        )
        _require(
            total <= maximum,
            f"{label}: text exceeds {maximum} UTF-8 bytes",
        )
    return total


@dataclass(frozen=True, slots=True)
class JsonLimits:
    """Immutable allocation and shape limits for one JSON document.

    The root JSON value has depth zero. ``maximum_items`` counts JSON values,
    including array and object containers, but does not count object member
    names. String limits count decoded UTF-8 bytes, including object keys.
    """

    maximum_bytes: int
    maximum_depth: int
    maximum_items: int
    maximum_object_members: int
    maximum_array_items: int
    maximum_key_utf8_bytes: int
    maximum_string_utf8_bytes: int
    maximum_total_string_utf8_bytes: int
    maximum_integer_chars: int
    maximum_float_chars: int
    allow_floats: bool = False

    def __post_init__(self) -> None:
        positive = (
            "maximum_bytes",
            "maximum_items",
            "maximum_key_utf8_bytes",
            "maximum_string_utf8_bytes",
            "maximum_total_string_utf8_bytes",
            "maximum_integer_chars",
            "maximum_float_chars",
        )
        nonnegative = (
            "maximum_depth",
            "maximum_object_members",
            "maximum_array_items",
        )
        for field in positive:
            value = getattr(self, field)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        for field in nonnegative:
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field} must be a nonnegative integer")
        if type(self.allow_floats) is not bool:
            raise ValueError("allow_floats must be boolean")
        for field in (
            "maximum_key_utf8_bytes",
            "maximum_string_utf8_bytes",
            "maximum_total_string_utf8_bytes",
            "maximum_integer_chars",
            "maximum_float_chars",
        ):
            if getattr(self, field) > self.maximum_bytes:
                raise ValueError(f"{field} cannot exceed maximum_bytes")
        if self.maximum_key_utf8_bytes > self.maximum_total_string_utf8_bytes:
            raise ValueError(
                "maximum_key_utf8_bytes cannot exceed the aggregate string budget"
            )
        if self.maximum_string_utf8_bytes > self.maximum_total_string_utf8_bytes:
            raise ValueError(
                "maximum_string_utf8_bytes cannot exceed the aggregate string budget"
            )


@dataclass(frozen=True, slots=True)
class FileSnapshotLimits:
    """Immutable byte bounds for one physical regular-file snapshot."""

    minimum_bytes: int
    maximum_bytes: int

    def __post_init__(self) -> None:
        if type(self.minimum_bytes) is not int or self.minimum_bytes < 0:
            raise ValueError("minimum_bytes must be a nonnegative integer")
        if type(self.maximum_bytes) is not int or self.maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be a positive integer")
        if self.minimum_bytes > self.maximum_bytes:
            raise ValueError("minimum_bytes cannot exceed maximum_bytes")


def _validate_json_limits_exact(limits: Any) -> JsonLimits:
    if type(limits) is not JsonLimits:
        _fail("JSON limits type is not exact")
    try:
        JsonLimits.__post_init__(limits)
    except (AttributeError, MemoryError, OverflowError, TypeError, ValueError) as error:
        _fail(f"JSON limits were forged or mutated: {error}")
    return limits


def _validate_file_limits_exact(limits: Any) -> FileSnapshotLimits:
    if type(limits) is not FileSnapshotLimits:
        _fail("file snapshot limits type is not exact")
    try:
        FileSnapshotLimits.__post_init__(limits)
    except (AttributeError, MemoryError, OverflowError, TypeError, ValueError) as error:
        _fail(f"file snapshot limits were forged or mutated: {error}")
    return limits


@dataclass(frozen=True, slots=True)
class JsonMetrics:
    """Shape metrics produced independently before and after native parsing."""

    items: int
    maximum_depth: int
    objects: int
    arrays: int
    object_members: int
    array_items: int
    string_utf8_bytes: int


@dataclass(slots=True)
class _ContainerFrame:
    kind: str
    depth: int
    state: str
    count: int
    keys: set[str] | None


@dataclass(slots=True)
class _MetricAccumulator:
    items: int = 0
    maximum_depth: int = 0
    objects: int = 0
    arrays: int = 0
    object_members: int = 0
    array_items: int = 0
    string_utf8_bytes: int = 0

    def frozen(self) -> JsonMetrics:
        return JsonMetrics(
            items=self.items,
            maximum_depth=self.maximum_depth,
            objects=self.objects,
            arrays=self.arrays,
            object_members=self.object_members,
            array_items=self.array_items,
            string_utf8_bytes=self.string_utf8_bytes,
        )


def _bounded_add_string_bytes(
    metrics: _MetricAccumulator,
    byte_count: int,
    *,
    limits: JsonLimits,
    label: str,
) -> None:
    metrics.string_utf8_bytes += byte_count
    _require(
        metrics.string_utf8_bytes <= limits.maximum_total_string_utf8_bytes,
        f"{label}: total decoded JSON string content exceeds "
        f"{limits.maximum_total_string_utf8_bytes} UTF-8 bytes",
    )


def _decoded_scalar_utf8_bytes(code_point: int) -> int:
    if code_point <= 0x7F:
        return 1
    if code_point <= 0x7FF:
        return 2
    if code_point <= 0xFFFF:
        return 3
    return 4


def _scan_string(
    text: str,
    start: int,
    *,
    maximum_utf8_bytes: int,
    capture: bool,
    label: str,
) -> tuple[int, str | None, int]:
    """Scan one JSON string and return its exclusive end and decoded byte count."""

    index = start + 1
    decoded_bytes = 0
    decoded: list[str] | None = [] if capture else None
    while index < len(text):
        character = text[index]
        if character == '"':
            return (
                index + 1,
                "".join(decoded) if decoded is not None else None,
                decoded_bytes,
            )
        if ord(character) < 0x20:
            _fail(f"{label}: JSON string contains an unescaped control character")
        if character != "\\":
            try:
                width = len(character.encode("utf-8"))
            except UnicodeEncodeError as error:
                _fail(f"{label}: JSON string is not Unicode scalar text: {error}")
            decoded_bytes += width
            _require(
                decoded_bytes <= maximum_utf8_bytes,
                f"{label}: decoded JSON string exceeds "
                f"{maximum_utf8_bytes} UTF-8 bytes",
            )
            if decoded is not None:
                decoded.append(character)
            index += 1
            continue

        index += 1
        _require(index < len(text), f"{label}: JSON string ends after an escape")
        escape = text[index]
        if escape in _SIMPLE_ESCAPES:
            decoded_character = _SIMPLE_ESCAPES[escape]
            decoded_bytes += 1
            _require(
                decoded_bytes <= maximum_utf8_bytes,
                f"{label}: decoded JSON string exceeds "
                f"{maximum_utf8_bytes} UTF-8 bytes",
            )
            if decoded is not None:
                decoded.append(decoded_character)
            index += 1
            continue
        _require(escape == "u", f"{label}: JSON string contains an invalid escape")
        _require(
            index + 4 < len(text),
            f"{label}: JSON string contains a truncated Unicode escape",
        )
        encoded = text[index + 1 : index + 5]
        _require(
            len(encoded) == 4
            and all(character in _HEX_DIGITS for character in encoded),
            f"{label}: JSON string contains an invalid Unicode escape",
        )
        code_point = int(encoded, 16)
        index += 5
        if 0xD800 <= code_point <= 0xDBFF:
            _require(
                index + 5 < len(text)
                and text[index : index + 2] == "\\u"
                and all(
                    character in _HEX_DIGITS
                    for character in text[index + 2 : index + 6]
                ),
                f"{label}: JSON string contains an unpaired high surrogate",
            )
            low = int(text[index + 2 : index + 6], 16)
            _require(
                0xDC00 <= low <= 0xDFFF,
                f"{label}: JSON string contains an unpaired high surrogate",
            )
            code_point = 0x10000 + ((code_point - 0xD800) << 10) + (low - 0xDC00)
            index += 6
        elif 0xDC00 <= code_point <= 0xDFFF:
            _fail(f"{label}: JSON string contains an unpaired low surrogate")
        decoded_bytes += _decoded_scalar_utf8_bytes(code_point)
        _require(
            decoded_bytes <= maximum_utf8_bytes,
            f"{label}: decoded JSON string exceeds {maximum_utf8_bytes} UTF-8 bytes",
        )
        if decoded is not None:
            decoded.append(chr(code_point))
    _fail(f"{label}: JSON string is unterminated")


def _validate_integer_token(
    integer_lexeme: str,
    *,
    limits: JsonLimits,
    label: str,
) -> int:
    _require(
        len(integer_lexeme) <= limits.maximum_integer_chars,
        f"{label}: JSON integer exceeds {limits.maximum_integer_chars} characters",
    )
    _require(
        integer_lexeme != "-0",
        f"{label}: negative-zero JSON integer is forbidden",
    )
    try:
        return int(integer_lexeme)
    except (OverflowError, ValueError) as error:
        _fail(f"{label}: JSON integer is invalid: {error}")


def _validate_float_token(token: str, *, limits: JsonLimits, label: str) -> float:
    _require(limits.allow_floats, f"{label}: JSON floating-point values are forbidden")
    _require(
        len(token) <= limits.maximum_float_chars,
        f"{label}: JSON floating-point token exceeds "
        f"{limits.maximum_float_chars} characters",
    )
    try:
        exact = Decimal(token)
        parsed = float(token)
    except (InvalidOperation, OverflowError, ValueError) as error:
        _fail(f"{label}: JSON floating-point value is invalid: {error}")
    _require(
        exact.is_finite() and math.isfinite(parsed),
        f"{label}: JSON floating-point value is non-finite",
    )
    _require(
        exact.is_zero() or parsed != 0.0,
        f"{label}: JSON floating-point value underflows binary64",
    )
    _require(
        not (exact.is_zero() and token.startswith("-")),
        f"{label}: negative-zero JSON floating-point value is forbidden",
    )
    return parsed


def _scan_number(
    text: str,
    start: int,
    *,
    limits: JsonLimits,
    label: str,
) -> tuple[int, bool]:
    index = start
    scan_limit = max(
        limits.maximum_integer_chars,
        limits.maximum_float_chars if limits.allow_floats else 0,
    )

    def require_scan_bound() -> None:
        _require(
            index - start <= scan_limit,
            f"{label}: JSON number token exceeds {scan_limit} characters",
        )

    if text[index] == "-":
        index += 1
        require_scan_bound()
        _require(index < len(text), f"{label}: JSON number ends after its sign")
    _require(index < len(text), f"{label}: JSON number is incomplete")
    if text[index] == "0":
        index += 1
        require_scan_bound()
        _require(
            index >= len(text) or not ("0" <= text[index] <= "9"),
            f"{label}: JSON number contains a leading zero",
        )
    else:
        _require(
            "1" <= text[index] <= "9",
            f"{label}: JSON number has an invalid integer component",
        )
        while index < len(text) and "0" <= text[index] <= "9":
            index += 1
            require_scan_bound()

    is_float = False
    if index < len(text) and text[index] == ".":
        is_float = True
        index += 1
        require_scan_bound()
        fraction_start = index
        while index < len(text) and "0" <= text[index] <= "9":
            index += 1
            require_scan_bound()
        _require(
            index > fraction_start,
            f"{label}: JSON number has an empty fractional component",
        )
    if index < len(text) and text[index] in "eE":
        is_float = True
        index += 1
        require_scan_bound()
        if index < len(text) and text[index] in "+-":
            index += 1
            require_scan_bound()
        exponent_start = index
        while index < len(text) and "0" <= text[index] <= "9":
            index += 1
            require_scan_bound()
        _require(
            index > exponent_start,
            f"{label}: JSON number has an empty exponent",
        )

    _require(
        index >= len(text) or text[index] in _JSON_WHITESPACE or text[index] in ",]}",
        f"{label}: JSON number is followed by an invalid character",
    )
    token = text[start:index]
    if is_float:
        _validate_float_token(token, limits=limits, label=label)
    else:
        _validate_integer_token(token, limits=limits, label=label)
    return index, is_float


def _preflight_json_text(
    text: str,
    *,
    limits: JsonLimits,
    label: str,
) -> JsonMetrics:
    """Validate JSON grammar and all allocation limits without recursive descent."""

    index = 0
    stack: list[_ContainerFrame] = []
    metrics = _MetricAccumulator()
    root_done = False

    def skip_whitespace(position: int) -> int:
        while position < len(text) and text[position] in _JSON_WHITESPACE:
            position += 1
        return position

    def count_value(depth: int) -> None:
        metrics.items += 1
        _require(
            metrics.items <= limits.maximum_items,
            f"{label}: JSON item count exceeds {limits.maximum_items}",
        )
        _require(
            depth <= limits.maximum_depth,
            f"{label}: JSON nesting exceeds root-depth-0 limit {limits.maximum_depth}",
        )
        metrics.maximum_depth = max(metrics.maximum_depth, depth)

    def complete_value() -> None:
        nonlocal root_done
        if not stack:
            root_done = True
            return
        parent = stack[-1]
        if parent.kind == "array":
            _require(
                parent.state in {"first-or-end", "value"},
                f"{label}: internal array-state mismatch",
            )
        else:
            _require(
                parent.state == "value",
                f"{label}: internal object-state mismatch",
            )
        parent.state = "comma-or-end"

    def start_value(position: int, depth: int) -> int:
        character = text[position]
        count_value(depth)
        if character == "{":
            metrics.objects += 1
            stack.append(
                _ContainerFrame(
                    kind="object",
                    depth=depth,
                    state="first-key-or-end",
                    count=0,
                    keys=set(),
                )
            )
            return position + 1
        if character == "[":
            metrics.arrays += 1
            stack.append(
                _ContainerFrame(
                    kind="array",
                    depth=depth,
                    state="first-or-end",
                    count=0,
                    keys=None,
                )
            )
            return position + 1
        if character == '"':
            end, _, byte_count = _scan_string(
                text,
                position,
                maximum_utf8_bytes=limits.maximum_string_utf8_bytes,
                capture=False,
                label=label,
            )
            _bounded_add_string_bytes(
                metrics,
                byte_count,
                limits=limits,
                label=label,
            )
            complete_value()
            return end
        if character == "t" and text.startswith("true", position):
            complete_value()
            return position + 4
        if character == "f" and text.startswith("false", position):
            complete_value()
            return position + 5
        if character == "n" and text.startswith("null", position):
            complete_value()
            return position + 4
        if any(
            text.startswith(token, position)
            for token in ("NaN", "Infinity", "-Infinity")
        ):
            _fail(f"{label}: non-finite JSON value is forbidden")
        if character == "-" or "0" <= character <= "9":
            end, _ = _scan_number(
                text,
                position,
                limits=limits,
                label=label,
            )
            complete_value()
            return end
        _fail(f"{label}: JSON value starts with an invalid character at {position}")

    index = skip_whitespace(index)
    _require(index < len(text), f"{label}: JSON input is empty")
    while True:
        index = skip_whitespace(index)
        if root_done:
            _require(
                index == len(text),
                f"{label}: JSON contains data after its root value",
            )
            return metrics.frozen()
        if not stack:
            _require(index < len(text), f"{label}: JSON root value is missing")
            index = start_value(index, 0)
            continue

        frame = stack[-1]
        _require(
            index < len(text),
            f"{label}: JSON {frame.kind} is unterminated",
        )
        character = text[index]
        if frame.kind == "array":
            if frame.state in {"first-or-end", "value"}:
                if character == "]" and frame.state == "first-or-end":
                    stack.pop()
                    index += 1
                    complete_value()
                    continue
                frame.count += 1
                metrics.array_items += 1
                _require(
                    frame.count <= limits.maximum_array_items,
                    f"{label}: JSON array exceeds {limits.maximum_array_items} items",
                )
                index = start_value(index, frame.depth + 1)
                continue
            _require(
                frame.state == "comma-or-end",
                f"{label}: internal array-state mismatch",
            )
            if character == ",":
                frame.state = "value"
                index += 1
                continue
            if character == "]":
                stack.pop()
                index += 1
                complete_value()
                continue
            _fail(f"{label}: JSON array requires a comma or closing bracket")

        if frame.state in {"first-key-or-end", "key"}:
            if character == "}" and frame.state == "first-key-or-end":
                stack.pop()
                index += 1
                complete_value()
                continue
            _require(character == '"', f"{label}: JSON object key must be a string")
            end, key, byte_count = _scan_string(
                text,
                index,
                maximum_utf8_bytes=limits.maximum_key_utf8_bytes,
                capture=True,
                label=label,
            )
            _require(key is not None, f"{label}: internal key-decoding failure")
            frame.count += 1
            metrics.object_members += 1
            _require(
                frame.count <= limits.maximum_object_members,
                f"{label}: JSON object exceeds {limits.maximum_object_members} members",
            )
            _require(frame.keys is not None, f"{label}: internal object-key mismatch")
            _require(
                key not in frame.keys,
                f"{label}: duplicate JSON object key {key!r}",
            )
            frame.keys.add(key)
            _bounded_add_string_bytes(
                metrics,
                byte_count,
                limits=limits,
                label=label,
            )
            frame.state = "colon"
            index = end
            continue
        if frame.state == "colon":
            _require(character == ":", f"{label}: JSON object key requires a colon")
            frame.state = "value"
            index += 1
            continue
        if frame.state == "value":
            index = start_value(index, frame.depth + 1)
            continue
        _require(
            frame.state == "comma-or-end",
            f"{label}: internal object-state mismatch",
        )
        if character == ",":
            frame.state = "key"
            index += 1
            continue
        if character == "}":
            stack.pop()
            index += 1
            complete_value()
            continue
        _fail(f"{label}: JSON object requires a comma or closing brace")


def _bounded_native_integer(value: int, *, limits: JsonLimits, label: str) -> None:
    digit_budget = limits.maximum_integer_chars - (1 if value < 0 else 0)
    _require(
        digit_budget > 0
        and value.bit_length() <= ((digit_budget * 3_322 + 999) // 1_000),
        f"{label}: JSON integer exceeds {limits.maximum_integer_chars} characters",
    )
    try:
        encoded = str(value)
    except (MemoryError, ValueError) as error:
        _fail(f"{label}: JSON integer cannot be bounded: {error}")
    _require(
        len(encoded) <= limits.maximum_integer_chars,
        f"{label}: JSON integer exceeds {limits.maximum_integer_chars} characters",
    )


def validate_native_json_tree(
    value: Any,
    *,
    limits: JsonLimits,
    label: str,
) -> JsonMetrics:
    """Validate a native, unaliased JSON tree without recursive traversal."""

    _validate_json_limits_exact(limits)
    stack: list[tuple[Any, int]] = [(value, 0)]
    seen_containers: set[int] = set()
    metrics = _MetricAccumulator()
    while stack:
        item, depth = stack.pop()
        item_type = type(item)
        metrics.items += 1
        _require(
            metrics.items <= limits.maximum_items,
            f"{label}: JSON item count exceeds {limits.maximum_items}",
        )
        _require(
            depth <= limits.maximum_depth,
            f"{label}: JSON nesting exceeds root-depth-0 limit {limits.maximum_depth}",
        )
        metrics.maximum_depth = max(metrics.maximum_depth, depth)

        if item_type is dict:
            identity = id(item)
            _require(
                identity not in seen_containers,
                f"{label}: JSON tree contains a shared or cyclic object",
            )
            seen_containers.add(identity)
            metrics.objects += 1
            _require(
                len(item) <= limits.maximum_object_members,
                f"{label}: JSON object exceeds {limits.maximum_object_members} members",
            )
            metrics.object_members += len(item)
            _require(
                metrics.items + len(stack) + len(item) <= limits.maximum_items,
                f"{label}: JSON item count exceeds {limits.maximum_items}",
            )
            for key, child in reversed(tuple(item.items())):
                _require(
                    type(key) is str,
                    f"{label}: JSON object key is not a native string",
                )
                byte_count = _bounded_native_utf8_length(
                    key,
                    maximum=limits.maximum_key_utf8_bytes,
                    label=f"{label}: JSON object key",
                )
                _bounded_add_string_bytes(
                    metrics,
                    byte_count,
                    limits=limits,
                    label=label,
                )
                stack.append((child, depth + 1))
            continue
        if item_type is list:
            identity = id(item)
            _require(
                identity not in seen_containers,
                f"{label}: JSON tree contains a shared or cyclic array",
            )
            seen_containers.add(identity)
            metrics.arrays += 1
            _require(
                len(item) <= limits.maximum_array_items,
                f"{label}: JSON array exceeds {limits.maximum_array_items} items",
            )
            metrics.array_items += len(item)
            _require(
                metrics.items + len(stack) + len(item) <= limits.maximum_items,
                f"{label}: JSON item count exceeds {limits.maximum_items}",
            )
            stack.extend((child, depth + 1) for child in reversed(item))
            continue
        if item_type is str:
            byte_count = _bounded_native_utf8_length(
                item,
                maximum=limits.maximum_string_utf8_bytes,
                label=f"{label}: JSON string",
            )
            _bounded_add_string_bytes(
                metrics,
                byte_count,
                limits=limits,
                label=label,
            )
            continue
        if item_type is bool or item is None:
            continue
        if item_type is int:
            _bounded_native_integer(item, limits=limits, label=label)
            continue
        if item_type is float:
            _require(
                limits.allow_floats,
                f"{label}: JSON floating-point values are forbidden",
            )
            _require(
                math.isfinite(item),
                f"{label}: JSON floating-point value is non-finite",
            )
            _require(
                item != 0.0 or math.copysign(1.0, item) > 0.0,
                f"{label}: negative-zero JSON floating-point value is forbidden",
            )
            encoded = repr(item)
            _require(
                len(encoded) <= limits.maximum_float_chars,
                f"{label}: JSON floating-point token exceeds "
                f"{limits.maximum_float_chars} characters",
            )
            continue
        _fail(
            f"{label}: value of type {item_type.__name__!r} is not a native JSON value"
        )
    return metrics.frozen()


def parse_json_bytes(
    raw: bytes,
    *,
    limits: JsonLimits,
    label: str,
) -> Any:
    """Parse one resource-bounded UTF-8 JSON document into a native tree."""

    _validate_json_limits_exact(limits)
    _require(type(raw) is bytes, f"{label}: JSON input must be native bytes")
    _require(raw, f"{label}: JSON input is empty")
    _require(
        len(raw) <= limits.maximum_bytes,
        f"{label}: JSON input exceeds {limits.maximum_bytes} bytes",
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail(f"{label}: JSON input is not valid UTF-8: {error}")
    preflight_metrics = _preflight_json_text(text, limits=limits, label=label)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            _require(
                key not in result,
                f"{label}: duplicate JSON object key {key!r}",
            )
            result[key] = item
        return result

    def reject_constant(token: str) -> NoReturn:
        _fail(f"{label}: non-finite JSON constant {token!r} is forbidden")

    try:
        value = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
            parse_float=lambda token: _validate_float_token(
                token,
                limits=limits,
                label=label,
            ),
            parse_int=lambda token: _validate_integer_token(
                token,
                limits=limits,
                label=label,
            ),
        )
    except BoundedJsonError:
        raise
    except (json.JSONDecodeError, RecursionError, ValueError) as error:
        _fail(f"{label}: JSON decoder rejected preflighted input: {error}")
    postflight_metrics = validate_native_json_tree(
        value,
        limits=limits,
        label=label,
    )
    _require(
        postflight_metrics == preflight_metrics,
        f"{label}: JSON preflight/native-tree metrics disagree",
    )
    return value


def _stat_fingerprint(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
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


FileReadPhaseHook = Callable[[str], None]


def read_bounded_regular_file(
    path: Path,
    *,
    limits: FileSnapshotLimits,
    label: str,
    phase_hook: FileReadPhaseHook | None = None,
) -> bytes:
    """Read one stable non-symlink regular-file snapshot without path races."""

    _validate_file_limits_exact(limits)
    try:
        raw_path = os.fspath(path)
    except TypeError as error:
        _fail(f"{label}: file path is invalid: {error}")
    _require(type(raw_path) is str, f"{label}: file path must be exact text")
    _bounded_native_utf8_length(
        raw_path,
        maximum=_MAX_PATH_UTF8_BYTES,
        label=f"{label}: file path",
    )
    _require(raw_path and "\x00" not in raw_path, f"{label}: file path is invalid")
    absolute_text = os.path.abspath(raw_path)
    _bounded_native_utf8_length(
        absolute_text,
        maximum=_MAX_PATH_UTF8_BYTES,
        label=f"{label}: absolute file path",
    )
    absolute = Path(absolute_text)
    parts = absolute.parts
    _require(
        absolute.is_absolute() and len(parts) >= 2 and parts[0] == os.sep,
        f"{label}: only absolute POSIX file paths are supported",
    )
    components = parts[1:]
    _require(
        len(components) <= _MAX_PATH_COMPONENTS
        and all(component not in {"", ".", ".."} for component in components),
        f"{label}: file path contains an invalid component",
    )
    for component in components:
        _bounded_native_utf8_length(
            component,
            maximum=_MAX_PATH_COMPONENT_UTF8_BYTES,
            label=f"{label}: file path component",
        )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    _require(
        no_follow is not None
        and directory is not None
        and os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks,
        f"{label}: platform lacks fail-closed directory-descriptor operations",
    )
    directory_flags = os.O_RDONLY | directory | no_follow | getattr(os, "O_CLOEXEC", 0)
    descriptors: list[int] = []
    file_descriptor = -1
    close_error: OSError | None = None
    try:
        descriptors.append(os.open(os.sep, directory_flags))
        directory_fingerprints = [_directory_fingerprint(os.fstat(descriptors[0]))]
        for component in components[:-1]:
            parent = descriptors[-1]
            child = os.open(component, directory_flags, dir_fd=parent)
            opened = os.fstat(child)
            listed = os.stat(
                component,
                dir_fd=parent,
                follow_symlinks=False,
            )
            _require(
                stat.S_ISDIR(opened.st_mode)
                and not stat.S_ISLNK(listed.st_mode)
                and _directory_fingerprint(opened) == _directory_fingerprint(listed),
                f"{label}: ancestor is not one stable physical directory",
            )
            descriptors.append(child)
            directory_fingerprints.append(_directory_fingerprint(opened))

        parent = descriptors[-1]
        leaf = components[-1]
        before = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        _require(
            stat.S_ISREG(before.st_mode) and not stat.S_ISLNK(before.st_mode),
            f"{label}: expected one non-symlink regular file",
        )
        _require(
            limits.minimum_bytes <= before.st_size <= limits.maximum_bytes,
            f"{label}: file size is outside "
            f"{limits.minimum_bytes}..{limits.maximum_bytes} bytes",
        )
        if phase_hook is not None:
            phase_hook("pre-open")
        file_descriptor = os.open(
            leaf,
            os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent,
        )
        opened = os.fstat(file_descriptor)
        _require(
            stat.S_ISREG(opened.st_mode)
            and _stat_fingerprint(opened) == _stat_fingerprint(before),
            f"{label}: file changed before its inode was opened",
        )

        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 1024 * 1024))
            _require(chunk, f"{label}: file ended before its opened size")
            chunks.append(chunk)
            remaining -= len(chunk)
        _require(
            os.read(file_descriptor, 1) == b"",
            f"{label}: file grew beyond its opened size",
        )
        content = b"".join(chunks)
        if phase_hook is not None:
            phase_hook("read-complete")
        after = os.fstat(file_descriptor)
        final_leaf = os.stat(leaf, dir_fd=parent, follow_symlinks=False)
        _require(
            _stat_fingerprint(opened)
            == _stat_fingerprint(after)
            == _stat_fingerprint(final_leaf),
            f"{label}: file or path changed while its bytes were read",
        )
        _require(
            limits.minimum_bytes <= len(content) <= limits.maximum_bytes,
            f"{label}: snapshot size is outside "
            f"{limits.minimum_bytes}..{limits.maximum_bytes} bytes",
        )

        for index, component in enumerate(components[:-1]):
            current = os.stat(
                component,
                dir_fd=descriptors[index],
                follow_symlinks=False,
            )
            _require(
                not stat.S_ISLNK(current.st_mode)
                and _directory_fingerprint(current)
                == directory_fingerprints[index + 1]
                == _directory_fingerprint(os.fstat(descriptors[index + 1])),
                f"{label}: ancestor changed while its bytes were read",
            )
        return content
    except BoundedJsonError:
        raise
    except OSError as error:
        _fail(f"{label}: cannot read a stable regular-file snapshot: {error}")
    finally:
        if file_descriptor >= 0:
            try:
                os.close(file_descriptor)
            except OSError as error:
                close_error = error
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError as error:
                if close_error is None:
                    close_error = error
        if close_error is not None and sys.exc_info()[0] is None:
            _fail(f"{label}: cannot close snapshot descriptors: {close_error}")


def _must_fail(action: Callable[[], Any], expected: str) -> None:
    try:
        action()
    except BoundedJsonError as error:
        _require(
            expected in str(error),
            f"bounded-JSON self-test expected {expected!r}, got {str(error)!r}",
        )
        return
    raise AssertionError(f"bounded-JSON self-test unexpectedly passed: {expected}")


def run_self_test() -> None:
    """Run exact-boundary, parser-order, numeric, and file-race tests."""

    limits = JsonLimits(
        maximum_bytes=4096,
        maximum_depth=2,
        maximum_items=16,
        maximum_object_members=2,
        maximum_array_items=2,
        maximum_key_utf8_bytes=3,
        maximum_string_utf8_bytes=3,
        maximum_total_string_utf8_bytes=6,
        maximum_integer_chars=3,
        maximum_float_chars=6,
        allow_floats=False,
    )

    if parse_json_bytes(b"[[0]]", limits=limits, label="depth exact") != [[0]]:
        raise AssertionError("bounded-JSON exact-depth value changed")
    _must_fail(
        lambda: parse_json_bytes(b"[[[0]]]", limits=limits, label="depth plus one"),
        "nesting",
    )
    item_limits = replace(
        limits,
        maximum_items=3,
        maximum_array_items=4,
    )
    parse_json_bytes(b"[0,1]", limits=item_limits, label="items exact")
    _must_fail(
        lambda: parse_json_bytes(
            b"[0,1,2]",
            limits=item_limits,
            label="items plus one",
        ),
        "item count",
    )
    member_limits = replace(limits, maximum_object_members=2)
    parse_json_bytes(b'{"a":0,"b":1}', limits=member_limits, label="members exact")
    _must_fail(
        lambda: parse_json_bytes(
            b'{"a":0,"b":1,"c":2}',
            limits=member_limits,
            label="members plus one",
        ),
        "object exceeds",
    )
    array_limits = replace(limits, maximum_array_items=2)
    parse_json_bytes(b"[0,1]", limits=array_limits, label="array exact")
    _must_fail(
        lambda: parse_json_bytes(
            b"[0,1,2]",
            limits=array_limits,
            label="array plus one",
        ),
        "array exceeds",
    )
    parse_json_bytes(
        '{"€":0}'.encode(),
        limits=limits,
        label="key bytes exact",
    )
    _must_fail(
        lambda: parse_json_bytes(
            '{"😀":0}'.encode(),
            limits=limits,
            label="key bytes plus one",
        ),
        "decoded JSON string exceeds",
    )
    parse_json_bytes(
        '"€"'.encode(),
        limits=limits,
        label="value bytes exact",
    )
    _must_fail(
        lambda: parse_json_bytes(
            '"😀"'.encode(),
            limits=limits,
            label="value bytes plus one",
        ),
        "decoded JSON string exceeds",
    )
    aggregate_limits = replace(limits, maximum_string_utf8_bytes=4)
    parse_json_bytes(
        '{"€":"€"}'.encode(),
        limits=aggregate_limits,
        label="aggregate strings exact",
    )
    _must_fail(
        lambda: parse_json_bytes(
            '{"€":"😀"}'.encode(),
            limits=aggregate_limits,
            label="aggregate strings plus one",
        ),
        "total decoded JSON string content",
    )
    parse_json_bytes(b"-99", limits=limits, label="integer chars exact")
    _must_fail(
        lambda: parse_json_bytes(
            b"-999",
            limits=limits,
            label="integer chars plus one",
        ),
        "number token exceeds",
    )
    float_limits = replace(limits, allow_floats=True)
    parse_json_bytes(b"1.0e+2", limits=float_limits, label="float chars exact")
    _must_fail(
        lambda: parse_json_bytes(
            b"1.0e+20",
            limits=float_limits,
            label="float chars plus one",
        ),
        "number token exceeds",
    )
    _must_fail(
        lambda: parse_json_bytes(b"1.0", limits=limits, label="integer-only"),
        "floating-point values are forbidden",
    )
    _must_fail(
        lambda: parse_json_bytes(
            b"1e9999",
            limits=replace(float_limits, maximum_float_chars=16),
            label="float overflow",
        ),
        "non-finite",
    )
    _must_fail(
        lambda: parse_json_bytes(
            b"1e-9999",
            limits=replace(float_limits, maximum_float_chars=16),
            label="float underflow",
        ),
        "underflows",
    )
    _must_fail(
        lambda: parse_json_bytes(
            b"-0.0",
            limits=float_limits,
            label="negative zero",
        ),
        "negative-zero",
    )
    _must_fail(
        lambda: parse_json_bytes(b"-0", limits=limits, label="integer negative zero"),
        "negative-zero",
    )
    large_numeric_limit = JsonLimits(
        maximum_bytes=1_000_000,
        maximum_depth=0,
        maximum_items=1,
        maximum_object_members=0,
        maximum_array_items=0,
        maximum_key_utf8_bytes=1,
        maximum_string_utf8_bytes=1,
        maximum_total_string_utf8_bytes=1,
        maximum_integer_chars=1_000_000,
        maximum_float_chars=1,
    )
    validate_native_json_tree(
        1,
        limits=large_numeric_limit,
        label="large configured numeric ceiling",
    )
    try:
        replace(limits, maximum_integer_chars=limits.maximum_bytes + 1)
    except ValueError:
        pass
    else:
        raise AssertionError("numeric token limit may not exceed raw-byte budget")
    _must_fail(
        lambda: validate_native_json_tree(
            -0.0,
            limits=float_limits,
            label="native negative zero",
        ),
        "negative-zero",
    )
    _must_fail(
        lambda: validate_native_json_tree(
            1 << 1_000_000,
            limits=limits,
            label="native huge integer",
        ),
        "integer exceeds",
    )
    _must_fail(
        lambda: validate_native_json_tree(
            "x" * 1_000_000,
            limits=limits,
            label="native huge string",
        ),
        "text exceeds",
    )

    class JsonLimitsAlias(JsonLimits):
        pass

    alias_limits = JsonLimitsAlias(
        **{field.name: getattr(limits, field.name) for field in fields(JsonLimits)}
    )
    _must_fail(
        lambda: parse_json_bytes(b"0", limits=alias_limits, label="limits subclass"),
        "limits type is not exact",
    )
    forged_limits = replace(limits)
    object.__setattr__(forged_limits, "maximum_items", -1)
    _must_fail(
        lambda: validate_native_json_tree(
            0,
            limits=forged_limits,
            label="forged limits",
        ),
        "forged or mutated",
    )
    for token in (b"NaN", b"Infinity", b"-Infinity"):
        _must_fail(
            lambda token=token: parse_json_bytes(
                token,
                limits=float_limits,
                label="non-finite literal",
            ),
            "non-finite",
        )
    _must_fail(
        lambda: parse_json_bytes(
            "١".encode(),
            limits=limits,
            label="non-ASCII digit",
        ),
        "invalid character",
    )
    _must_fail(
        lambda: parse_json_bytes(
            b'{"a":0,"\\u0061":1}',
            limits=replace(limits, maximum_total_string_utf8_bytes=8),
            label="escaped duplicate",
        ),
        "duplicate JSON object key",
    )
    _must_fail(
        lambda: parse_json_bytes(
            b'"\\uD800"',
            limits=limits,
            label="unpaired surrogate",
        ),
        "unpaired high surrogate",
    )
    _must_fail(
        lambda: parse_json_bytes(
            b"\xff",
            limits=limits,
            label="invalid UTF-8",
        ),
        "not valid UTF-8",
    )
    exact_raw = b'{"a":0}'
    parse_json_bytes(
        exact_raw,
        limits=replace(limits, maximum_bytes=len(exact_raw)),
        label="bytes exact",
    )

    original_loads = json.loads

    def forbidden_loads(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("json.loads ran before hostile preflight rejection")

    json.loads = forbidden_loads
    try:
        _must_fail(
            lambda: parse_json_bytes(
                exact_raw,
                limits=replace(limits, maximum_bytes=len(exact_raw) - 1),
                label="bytes plus one",
            ),
            "JSON input exceeds",
        )
        _must_fail(
            lambda: parse_json_bytes(
                b"[[[0]]]",
                limits=limits,
                label="preflight before parser",
            ),
            "nesting",
        )
        _must_fail(
            lambda: parse_json_bytes(
                b"9999",
                limits=limits,
                label="number before parser",
            ),
            "number token exceeds",
        )
    finally:
        json.loads = original_loads

    import tempfile

    with tempfile.TemporaryDirectory(prefix="ncp-bounded-json-") as temporary:
        root = Path(temporary).resolve(strict=True)
        regular = root / "regular.json"
        regular.write_bytes(exact_raw)
        snapshot_limits = FileSnapshotLimits(
            minimum_bytes=1,
            maximum_bytes=len(exact_raw),
        )
        forged_snapshot_limits = replace(snapshot_limits)
        object.__setattr__(forged_snapshot_limits, "maximum_bytes", 0)
        _must_fail(
            lambda: read_bounded_regular_file(
                regular,
                limits=forged_snapshot_limits,
                label="forged file limits",
            ),
            "forged or mutated",
        )

        class FileSnapshotLimitsAlias(FileSnapshotLimits):
            pass

        _must_fail(
            lambda: read_bounded_regular_file(
                regular,
                limits=FileSnapshotLimitsAlias(
                    minimum_bytes=1,
                    maximum_bytes=len(exact_raw),
                ),
                label="file limits subclass",
            ),
            "limits type is not exact",
        )
        if (
            read_bounded_regular_file(
                regular,
                limits=snapshot_limits,
                label="regular snapshot",
            )
            != exact_raw
        ):
            raise AssertionError("bounded file snapshot changed stable bytes")

        oversized = root / "oversized.json"
        oversized.write_bytes(exact_raw + b" ")
        phases: list[str] = []
        _must_fail(
            lambda: read_bounded_regular_file(
                oversized,
                limits=snapshot_limits,
                label="oversized snapshot",
                phase_hook=phases.append,
            ),
            "file size",
        )
        if phases:
            raise AssertionError("oversized file reached its pre-open phase")

        leaf_symlink = root / "leaf.json"
        leaf_symlink.symlink_to(regular.name)
        _must_fail(
            lambda: read_bounded_regular_file(
                leaf_symlink,
                limits=snapshot_limits,
                label="leaf symlink",
            ),
            "non-symlink regular file",
        )
        physical = root / "physical"
        physical.mkdir()
        (physical / "value.json").write_bytes(exact_raw)
        linked = root / "linked"
        linked.symlink_to(physical, target_is_directory=True)
        _must_fail(
            lambda: read_bounded_regular_file(
                linked / "value.json",
                limits=snapshot_limits,
                label="ancestor symlink",
            ),
            "stable regular-file snapshot",
        )
        directory = root / "directory.json"
        directory.mkdir()
        _must_fail(
            lambda: read_bounded_regular_file(
                directory,
                limits=snapshot_limits,
                label="directory leaf",
            ),
            "non-symlink regular file",
        )
        if hasattr(os, "mkfifo"):
            fifo = root / "fifo.json"
            os.mkfifo(fifo)
            _must_fail(
                lambda: read_bounded_regular_file(
                    fifo,
                    limits=snapshot_limits,
                    label="FIFO leaf",
                ),
                "non-symlink regular file",
            )

        pre_open_race = root / "pre-open-race.json"
        displaced = root / "pre-open-race.displaced"
        pre_open_race.write_bytes(exact_raw)

        def replace_before_open(phase: str) -> None:
            if phase == "pre-open":
                pre_open_race.rename(displaced)
                pre_open_race.write_bytes(exact_raw)

        _must_fail(
            lambda: read_bounded_regular_file(
                pre_open_race,
                limits=snapshot_limits,
                label="pre-open replacement",
                phase_hook=replace_before_open,
            ),
            "changed before",
        )

        read_race = root / "read-race.json"
        read_race.write_bytes(exact_raw)

        def mutate_after_read(phase: str) -> None:
            if phase == "read-complete":
                read_race.write_bytes(b'{"b":1}')

        _must_fail(
            lambda: read_bounded_regular_file(
                read_race,
                limits=snapshot_limits,
                label="read mutation",
                phase_hook=mutate_after_read,
            ),
            "changed while",
        )


if __name__ == "__main__":
    run_self_test()
    print("OK bounded JSON: preflight, native-tree, and stable-file hostile tests")
