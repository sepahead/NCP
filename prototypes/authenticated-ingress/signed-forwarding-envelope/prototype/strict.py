"""Strict bounded JSON, base64url, identifier, and digest helpers."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any

JSON_SAFE_INTEGER_MAX = 9_007_199_254_740_991
SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
BASE64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
UUID_V4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
ID_SEGMENT = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,126}[a-z0-9])?\Z")


class ErrorCode(StrEnum):
    """Stable fail-closed prototype error categories."""

    BOUNDS = "bounds"
    JSON = "json"
    ENCODING = "encoding"
    MANIFEST = "manifest"
    PROFILE = "profile"
    CRYPTO = "crypto"
    PAYLOAD = "payload"
    REPLAY = "replay"
    RECOVERY = "recovery"
    STORAGE = "storage"


class PrototypeError(ValueError):
    """One bounded-detail prototype failure."""

    def __init__(self, code: ErrorCode, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class JsonLimits:
    """Pre-allocation JSON limits for one profile document."""

    max_bytes: int
    max_depth: int
    max_nodes: int
    max_members: int
    max_string_bytes: int


class _Preflight:
    def __init__(self, data: bytes, limits: JsonLimits, *, allow_floats: bool) -> None:
        self.data = data
        self.limits = limits
        self.allow_floats = allow_floats
        self.index = 0
        self.nodes = 0

    def run(self) -> None:
        self._space()
        self._value(1)
        self._space()
        if self.index != len(self.data):
            self._fail("trailing bytes after one JSON value")

    def _fail(self, detail: str) -> None:
        raise PrototypeError(ErrorCode.JSON, detail)

    def _space(self) -> None:
        while self.index < len(self.data) and self.data[self.index] in b" \t\r\n":
            self.index += 1

    def _take(self, expected: int) -> None:
        if self.index >= len(self.data) or self.data[self.index] != expected:
            self._fail("invalid JSON token")
        self.index += 1

    def _node(self, depth: int) -> None:
        if depth > self.limits.max_depth:
            raise PrototypeError(ErrorCode.BOUNDS, "JSON nesting depth exceeds the profile limit")
        self.nodes += 1
        if self.nodes > self.limits.max_nodes:
            raise PrototypeError(ErrorCode.BOUNDS, "JSON node count exceeds the profile limit")

    def _value(self, depth: int) -> None:
        self._space()
        self._node(depth)
        if self.index >= len(self.data):
            self._fail("JSON value is truncated")
        byte = self.data[self.index]
        if byte == ord("{"):
            self._object(depth)
        elif byte == ord("["):
            self._array(depth)
        elif byte == ord('"'):
            self._string()
        elif byte == ord("t"):
            self._literal(b"true")
        elif byte == ord("f"):
            self._literal(b"false")
        elif byte == ord("n"):
            self._literal(b"null")
        elif byte == ord("-") or ord("0") <= byte <= ord("9"):
            self._number()
        else:
            self._fail("unknown JSON value token")

    def _object(self, depth: int) -> None:
        self._take(ord("{"))
        self._space()
        if self.index < len(self.data) and self.data[self.index] == ord("}"):
            self.index += 1
            return
        members = 0
        while True:
            members += 1
            if members > self.limits.max_members:
                raise PrototypeError(
                    ErrorCode.BOUNDS,
                    "JSON object member count exceeds the profile limit",
                )
            self._space()
            self._string()
            self._space()
            self._take(ord(":"))
            self._value(depth + 1)
            self._space()
            if self.index >= len(self.data):
                self._fail("JSON object is truncated")
            separator = self.data[self.index]
            self.index += 1
            if separator == ord("}"):
                return
            if separator != ord(","):
                self._fail("JSON object has an invalid separator")

    def _array(self, depth: int) -> None:
        self._take(ord("["))
        self._space()
        if self.index < len(self.data) and self.data[self.index] == ord("]"):
            self.index += 1
            return
        members = 0
        while True:
            members += 1
            if members > self.limits.max_members:
                raise PrototypeError(
                    ErrorCode.BOUNDS,
                    "JSON array length exceeds the profile limit",
                )
            self._value(depth + 1)
            self._space()
            if self.index >= len(self.data):
                self._fail("JSON array is truncated")
            separator = self.data[self.index]
            self.index += 1
            if separator == ord("]"):
                return
            if separator != ord(","):
                self._fail("JSON array has an invalid separator")

    def _string(self) -> None:
        self._take(ord('"'))
        started = self.index
        while self.index < len(self.data):
            byte = self.data[self.index]
            self.index += 1
            if byte == ord('"'):
                if self.index - started - 1 > self.limits.max_string_bytes:
                    raise PrototypeError(
                        ErrorCode.BOUNDS,
                        "JSON string token exceeds the profile limit",
                    )
                return
            if byte < 0x20:
                self._fail("JSON string contains a raw control byte")
            if byte != ord("\\"):
                continue
            if self.index >= len(self.data):
                self._fail("JSON escape is truncated")
            escape = self.data[self.index]
            self.index += 1
            if escape in b'"\\/bfnrt':
                continue
            if escape != ord("u"):
                self._fail("JSON string contains an unknown escape")
            codepoint = self._hex4()
            if 0xD800 <= codepoint <= 0xDBFF:
                if self.data[self.index : self.index + 2] != b"\\u":
                    self._fail("JSON string contains an unpaired high surrogate")
                self.index += 2
                low = self._hex4()
                if not 0xDC00 <= low <= 0xDFFF:
                    self._fail("JSON string contains an invalid surrogate pair")
            elif 0xDC00 <= codepoint <= 0xDFFF:
                self._fail("JSON string contains an unpaired low surrogate")
        self._fail("JSON string is truncated")

    def _hex4(self) -> int:
        if self.index + 4 > len(self.data):
            self._fail("JSON unicode escape is truncated")
        token = self.data[self.index : self.index + 4]
        if any(byte not in b"0123456789abcdefABCDEF" for byte in token):
            self._fail("JSON unicode escape is invalid")
        self.index += 4
        return int(token, 16)

    def _literal(self, literal: bytes) -> None:
        if self.data[self.index : self.index + len(literal)] != literal:
            self._fail("JSON literal is invalid")
        self.index += len(literal)

    def _number(self) -> None:
        started = self.index
        negative = False
        if self.data[self.index] == ord("-"):
            negative = True
            self.index += 1
            if self.index >= len(self.data):
                self._fail("JSON number is truncated")
        if self.data[self.index] == ord("0"):
            self.index += 1
            if self.index < len(self.data) and self.data[self.index] in b"0123456789":
                self._fail("JSON number has a leading zero")
            if negative and (self.index == len(self.data) or self.data[self.index] not in b".eE"):
                self._fail("negative zero integer is forbidden")
        elif self.data[self.index] in b"123456789":
            self.index += 1
            while self.index < len(self.data) and self.data[self.index] in b"0123456789":
                self.index += 1
        else:
            self._fail("JSON number has an invalid integer part")

        fractional = self.index < len(self.data) and self.data[self.index] == ord(".")
        if fractional:
            if not self.allow_floats:
                self._fail("fractional numbers are forbidden in this profile document")
            self.index += 1
            digits = self.index
            while self.index < len(self.data) and self.data[self.index] in b"0123456789":
                self.index += 1
            if self.index == digits:
                self._fail("JSON fraction has no digits")

        exponent = self.index < len(self.data) and self.data[self.index] in b"eE"
        if exponent:
            if not self.allow_floats:
                self._fail("exponent numbers are forbidden in this profile document")
            self.index += 1
            if self.index < len(self.data) and self.data[self.index] in b"+-":
                self.index += 1
            digits = self.index
            while self.index < len(self.data) and self.data[self.index] in b"0123456789":
                self.index += 1
            if self.index == digits:
                self._fail("JSON exponent has no digits")

        if not fractional and not exponent:
            value = int(self.data[started : self.index])
            if abs(value) > JSON_SAFE_INTEGER_MAX:
                raise PrototypeError(
                    ErrorCode.BOUNDS,
                    "JSON integer exceeds the interoperable safe-integer range",
                )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PrototypeError(ErrorCode.JSON, f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _constant(token: str) -> None:
    raise PrototypeError(ErrorCode.JSON, f"non-finite JSON token {token!r} is forbidden")


def _walk_strings(value: Any, limits: JsonLimits, depth: int = 1) -> int:
    if depth > limits.max_depth:
        raise PrototypeError(ErrorCode.BOUNDS, "decoded JSON depth exceeds the profile limit")
    nodes = 1
    if isinstance(value, str):
        if len(value.encode("utf-8")) > limits.max_string_bytes:
            raise PrototypeError(
                ErrorCode.BOUNDS,
                "decoded JSON string exceeds the profile limit",
            )
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise PrototypeError(ErrorCode.ENCODING, "decoded JSON contains a surrogate")
    elif isinstance(value, dict):
        if len(value) > limits.max_members:
            raise PrototypeError(ErrorCode.BOUNDS, "decoded JSON object is too wide")
        for key, child in value.items():
            nodes += _walk_strings(key, limits, depth + 1)
            nodes += _walk_strings(child, limits, depth + 1)
    elif isinstance(value, list):
        if len(value) > limits.max_members:
            raise PrototypeError(ErrorCode.BOUNDS, "decoded JSON array is too wide")
        for child in value:
            nodes += _walk_strings(child, limits, depth + 1)
    if nodes > limits.max_nodes:
        raise PrototypeError(ErrorCode.BOUNDS, "decoded JSON node count exceeds the limit")
    return nodes


def strict_json_loads(
    data: bytes,
    limits: JsonLimits,
    *,
    allow_floats: bool = False,
) -> Any:
    """Parse one bounded strict UTF-8 JSON value after structural preflight."""

    if not data or len(data) > limits.max_bytes:
        raise PrototypeError(
            ErrorCode.BOUNDS,
            f"JSON byte length is outside 1..={limits.max_bytes}",
        )
    if data.startswith(b"\xef\xbb\xbf"):
        raise PrototypeError(ErrorCode.ENCODING, "UTF-8 BOM is forbidden")
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PrototypeError(ErrorCode.ENCODING, f"invalid UTF-8: {error}") from error
    _Preflight(data, limits, allow_floats=allow_floats).run()
    try:
        value = json.loads(
            data,
            object_pairs_hook=_pairs,
            parse_int=int,
            parse_float=Decimal if allow_floats else _constant,
            parse_constant=_constant,
        )
    except PrototypeError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise PrototypeError(ErrorCode.JSON, f"strict JSON parsing failed: {error}") from error
    _walk_strings(value, limits)
    return value


def b64url_encode(data: bytes) -> str:
    """Return canonical unpadded base64url."""

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(value: str, *, maximum: int) -> bytes:
    """Decode canonical unpadded base64url under a decoded-byte bound."""

    if (
        not isinstance(value, str)
        or not value
        or not BASE64URL.fullmatch(value)
        or len(value) % 4 == 1
    ):
        raise PrototypeError(ErrorCode.ENCODING, "base64url token is not canonical")
    estimated = (len(value) * 3) // 4
    if estimated > maximum:
        raise PrototypeError(ErrorCode.BOUNDS, "base64url decoded size exceeds the limit")
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        decoded = base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise PrototypeError(ErrorCode.ENCODING, f"base64url decode failed: {error}") from error
    if len(decoded) > maximum or b64url_encode(decoded) != value:
        raise PrototypeError(ErrorCode.ENCODING, "base64url trailing bits are noncanonical")
    return decoded


def sha256_hex(data: bytes) -> str:
    """Return lowercase SHA-256 of exact bytes."""

    return sha256(data).hexdigest()


def require_sha256(value: Any, field: str) -> str:
    """Return one exact lowercase SHA-256 field."""

    if not isinstance(value, str) or not SHA256_HEX.fullmatch(value):
        raise PrototypeError(ErrorCode.PROFILE, f"{field} is not lowercase SHA-256")
    return value


def require_safe_int(value: Any, field: str, *, positive: bool = False) -> int:
    """Return one JSON-safe integer with an optional positive constraint."""

    if type(value) is not int or abs(value) > JSON_SAFE_INTEGER_MAX:
        raise PrototypeError(ErrorCode.PROFILE, f"{field} is not a JSON-safe integer")
    if positive and value <= 0:
        raise PrototypeError(ErrorCode.PROFILE, f"{field} must be positive")
    if not positive and value < 0:
        raise PrototypeError(ErrorCode.PROFILE, f"{field} must be non-negative")
    return value


def require_uuid_v4(value: Any, field: str) -> str:
    """Return one canonical lowercase UUIDv4."""

    if not isinstance(value, str) or not UUID_V4.fullmatch(value):
        raise PrototypeError(ErrorCode.PROFILE, f"{field} is not a canonical UUIDv4")
    return value


def require_id(value: Any, field: str) -> str:
    """Return one canonical bounded identifier segment."""

    if not isinstance(value, str) or not ID_SEGMENT.fullmatch(value):
        raise PrototypeError(ErrorCode.PROFILE, f"{field} is not a canonical identifier")
    return value


def require_literal(value: Any, field: str, maximum: int) -> str:
    """Return one bounded ASCII literal without wildcard syntax."""

    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("ascii", errors="ignore")) != len(value)
        or len(value) > maximum
        or any(character.isspace() or ord(character) < 0x20 for character in value)
        or any(character in "*?[]{}#" for character in value)
    ):
        raise PrototypeError(ErrorCode.PROFILE, f"{field} is not a bounded literal")
    return value


def exact_members(value: Any, expected: set[str], field: str) -> dict[str, Any]:
    """Require an object with exactly the expected member names."""

    if not isinstance(value, dict) or set(value) != expected:
        raise PrototypeError(
            ErrorCode.PROFILE,
            f"{field} must contain exactly {sorted(expected)}",
        )
    return value
