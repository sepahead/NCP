"""Dependency-free NCP bounded-JSON admission for the pure-Python smoke peer.

This module is intentionally independent of the Rust/PyO3 implementation. It
caps the newline-framed byte read before decoding, scans structure and decoded
string/key identity before ``json.loads`` can allocate a generic tree, and then
parses only the already-admitted document.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO


ROOT = Path(__file__).resolve().parents[1]


class BoundedJsonError(RuntimeError):
    """One exact universal-ingress rejection."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise BoundedJsonError("NCP-LIMIT-007", f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def _reject_constant(value: str) -> None:
    raise BoundedJsonError("NCP-LIMIT-006", f"non-finite JSON number {value!r}")


_LIMIT_DOCUMENT = json.loads(
    (ROOT / "contract/limits.v1.json").read_text(encoding="utf-8"),
    object_pairs_hook=_reject_duplicate_pairs,
    parse_constant=_reject_constant,
)
if not isinstance(_LIMIT_DOCUMENT, dict) or _LIMIT_DOCUMENT.get("schema") != "ncp.resource-limits.v1":
    raise RuntimeError("contract/limits.v1.json has an unexpected schema")
JSON_LIMITS: dict[str, Any] = _LIMIT_DOCUMENT["json"]

MAX_FRAME_BYTES = int(JSON_LIMITS["max_frame_bytes"])
MAX_NESTING_DEPTH = int(JSON_LIMITS["max_nesting_depth"])
MAX_OBJECTS = int(JSON_LIMITS["max_objects"])
MAX_ARRAYS = int(JSON_LIMITS["max_arrays"])
MAX_TOTAL_MEMBERS = int(JSON_LIMITS["max_total_members"])
MAX_TOTAL_ARRAY_ITEMS = int(JSON_LIMITS["max_total_array_items"])
MAX_OBJECT_MEMBERS = int(JSON_LIMITS["max_object_members"])
MAX_ARRAY_ITEMS = int(JSON_LIMITS["max_array_items"])
MAX_KEY_BYTES = int(JSON_LIMITS["max_key_bytes"])
MAX_STRING_BYTES = int(JSON_LIMITS["max_string_bytes"])
MAX_TOTAL_STRING_BYTES = int(JSON_LIMITS["max_total_string_bytes"])
MAX_CHANNELS = int(JSON_LIMITS["max_channels"])
MAX_METADATA_ENTRIES = int(JSON_LIMITS["max_metadata_entries"])
SAFE_INTEGER_MIN = int(JSON_LIMITS["safe_integer_min"])
SAFE_INTEGER_MAX = int(JSON_LIMITS["safe_integer_max"])
MAX_FINITE_NUMBER_MAGNITUDE = Decimal(str(JSON_LIMITS["max_finite_number_magnitude"]))


def _utf8_width(character: str) -> int:
    point = ord(character)
    if point <= 0x7F:
        return 1
    if point <= 0x7FF:
        return 2
    if point <= 0xFFFF:
        return 3
    return 4


class _Scanner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.position = 0
        self.objects = 0
        self.arrays = 0
        self.members = 0
        self.array_items = 0
        self.string_bytes = 0

    def _fail(self, code: str, detail: str) -> None:
        raise BoundedJsonError(code, f"at character {self.position}: {detail}")

    def _peek(self) -> str | None:
        return self.text[self.position] if self.position < len(self.text) else None

    def _skip_whitespace(self) -> None:
        while self._peek() in {" ", "\n", "\r", "\t"}:
            self.position += 1

    def _expect(self, expected: str) -> None:
        if self._peek() != expected:
            self._fail("NCP-LIMIT-009", f"expected {expected!r}")
        self.position += 1

    def scan(self) -> None:
        self._parse_value(0)
        self._skip_whitespace()
        if self.position != len(self.text):
            self._fail("NCP-LIMIT-009", "trailing JSON data")

    def _parse_value(self, depth: int) -> None:
        self._skip_whitespace()
        if depth > MAX_NESTING_DEPTH:
            self._fail("NCP-LIMIT-002", "JSON nesting depth exceeded")
        token = self._peek()
        if token == "{":
            self._parse_object(depth + 1)
        elif token == "[":
            self._parse_array(depth + 1)
        elif token == '"':
            self._parse_string(capture=False)
        elif token == "t":
            self._parse_literal("true")
        elif token == "f":
            self._parse_literal("false")
        elif token == "n":
            self._parse_literal("null")
        elif token == "-" or (token is not None and token.isascii() and token.isdigit()):
            self._parse_number()
        else:
            self._fail("NCP-LIMIT-009", "expected a JSON value")

    def _parse_literal(self, literal: str) -> None:
        if not self.text.startswith(literal, self.position):
            self._fail("NCP-LIMIT-009", f"invalid JSON literal starting with {literal[0]!r}")
        self.position += len(literal)

    def _parse_number(self) -> None:
        start = self.position
        if self._peek() == "-":
            self.position += 1
        token = self._peek()
        if token == "0":
            self.position += 1
            following = self._peek()
            if following is not None and following.isascii() and following.isdigit():
                self._fail("NCP-LIMIT-009", "JSON numbers may not have leading zeroes")
        elif token is not None and token.isascii() and token in "123456789":
            while (digit := self._peek()) is not None and digit.isascii() and digit.isdigit():
                self.position += 1
        else:
            self._fail("NCP-LIMIT-009", "invalid JSON number integer part")

        if self._peek() == ".":
            self.position += 1
            digit = self._peek()
            if digit is None or not digit.isascii() or not digit.isdigit():
                self._fail("NCP-LIMIT-009", "JSON fraction requires a digit")
            while (digit := self._peek()) is not None and digit.isascii() and digit.isdigit():
                self.position += 1

        if self._peek() in {"e", "E"}:
            self.position += 1
            if self._peek() in {"+", "-"}:
                self.position += 1
            digit = self._peek()
            if digit is None or not digit.isascii() or not digit.isdigit():
                self._fail("NCP-LIMIT-009", "JSON exponent requires a digit")
            while (digit := self._peek()) is not None and digit.isascii() and digit.isdigit():
                self.position += 1

        spelling = self.text[start : self.position]
        try:
            value = Decimal(spelling)
        except InvalidOperation as error:
            raise BoundedJsonError("NCP-LIMIT-009", "invalid JSON number") from error
        if not value.is_finite() or abs(value) > MAX_FINITE_NUMBER_MAGNITUDE:
            self._fail("NCP-LIMIT-006", "number exceeds the finite magnitude budget")

    def _take_hex_unit(self) -> int:
        end = self.position + 4
        digits = self.text[self.position : end]
        if len(digits) != 4 or any(character not in "0123456789abcdefABCDEF" for character in digits):
            self._fail("NCP-LIMIT-008", "invalid JSON Unicode escape")
        self.position = end
        return int(digits, 16)

    def _parse_string(self, *, capture: bool) -> str | None:
        self._expect('"')
        output: list[str] | None = [] if capture else None
        decoded_bytes = 0
        while True:
            character = self._peek()
            if character is None:
                self._fail("NCP-LIMIT-009", "unterminated JSON string")
            self.position += 1
            if character == '"':
                break
            if character == "\\":
                escape = self._peek()
                if escape is None:
                    self._fail("NCP-LIMIT-009", "unterminated JSON escape")
                self.position += 1
                simple = {
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "b": "\b",
                    "f": "\f",
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                }
                if escape in simple:
                    decoded = simple[escape]
                elif escape == "u":
                    unit = self._take_hex_unit()
                    if 0xD800 <= unit <= 0xDBFF:
                        if self.text[self.position : self.position + 2] != "\\u":
                            self._fail("NCP-LIMIT-008", "unpaired high surrogate")
                        self.position += 2
                        low = self._take_hex_unit()
                        if not 0xDC00 <= low <= 0xDFFF:
                            self._fail("NCP-LIMIT-008", "unpaired high surrogate")
                        decoded = chr(0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00))
                    elif 0xDC00 <= unit <= 0xDFFF:
                        self._fail("NCP-LIMIT-008", "unpaired low surrogate")
                    else:
                        decoded = chr(unit)
                else:
                    self._fail("NCP-LIMIT-008", "invalid JSON escape")
            else:
                if ord(character) <= 0x1F:
                    self._fail("NCP-LIMIT-008", "unescaped control character in JSON string")
                decoded = character

            decoded_bytes += _utf8_width(decoded)
            limit = MAX_KEY_BYTES if capture else MAX_STRING_BYTES
            if decoded_bytes > limit:
                self._fail("NCP-LIMIT-005", "JSON string exceeds its byte limit")
            if output is not None:
                output.append(decoded)

        self.string_bytes += decoded_bytes
        if self.string_bytes > MAX_TOTAL_STRING_BYTES:
            self._fail("NCP-LIMIT-005", "aggregate JSON string budget exceeded")
        return "".join(output) if output is not None else None

    def _parse_object(self, depth: int) -> None:
        if depth > MAX_NESTING_DEPTH:
            self._fail("NCP-LIMIT-002", "JSON nesting depth exceeded")
        self.objects += 1
        if self.objects > MAX_OBJECTS:
            self._fail("NCP-LIMIT-003", "object count exceeded")
        self._expect("{")
        self._skip_whitespace()
        if self._peek() == "}":
            self.position += 1
            return
        keys: set[str] = set()
        local_members = 0
        while True:
            self._skip_whitespace()
            key = self._parse_string(capture=True)
            assert key is not None
            if key in keys:
                self._fail("NCP-LIMIT-007", f"duplicate decoded key {key!r}")
            keys.add(key)
            local_members += 1
            self.members += 1
            if local_members > MAX_OBJECT_MEMBERS or self.members > MAX_TOTAL_MEMBERS:
                self._fail("NCP-LIMIT-003", "object member budget exceeded")
            self._skip_whitespace()
            self._expect(":")
            self._parse_value(depth)
            self._skip_whitespace()
            if self._peek() == ",":
                self.position += 1
                continue
            if self._peek() == "}":
                self.position += 1
                return
            self._fail("NCP-LIMIT-009", "expected ',' or '}'")

    def _parse_array(self, depth: int) -> None:
        if depth > MAX_NESTING_DEPTH:
            self._fail("NCP-LIMIT-002", "JSON nesting depth exceeded")
        self.arrays += 1
        if self.arrays > MAX_ARRAYS:
            self._fail("NCP-LIMIT-004", "array count exceeded")
        self._expect("[")
        self._skip_whitespace()
        if self._peek() == "]":
            self.position += 1
            return
        local_items = 0
        while True:
            local_items += 1
            self.array_items += 1
            if local_items > MAX_ARRAY_ITEMS or self.array_items > MAX_TOTAL_ARRAY_ITEMS:
                self._fail("NCP-LIMIT-004", "array item budget exceeded")
            self._parse_value(depth)
            self._skip_whitespace()
            if self._peek() == ",":
                self.position += 1
                continue
            if self._peek() == "]":
                self.position += 1
                return
            self._fail("NCP-LIMIT-009", "expected ',' or ']'")


def _enforce_named_collection_limits(value: Any) -> None:
    if isinstance(value, int) and not isinstance(value, bool):
        if not SAFE_INTEGER_MIN <= value <= SAFE_INTEGER_MAX:
            raise BoundedJsonError("NCP-LIMIT-006", "integer exceeds the exact JSON range")
    elif isinstance(value, dict):
        for name, member in value.items():
            if name == "channels" and isinstance(member, dict) and len(member) > MAX_CHANNELS:
                raise BoundedJsonError("NCP-LIMIT-003", "channel map exceeds max_channels")
            if name in {"meta", "metadata"} and isinstance(member, dict) and len(member) > MAX_METADATA_ENTRIES:
                raise BoundedJsonError(
                    "NCP-LIMIT-003", "metadata map exceeds max_metadata_entries"
                )
            _enforce_named_collection_limits(member)
    elif isinstance(value, list):
        for member in value:
            _enforce_named_collection_limits(member)


def parse_bounded_json_line(reader: BinaryIO) -> Any:
    """Read and parse one newline-delimited canonical JSON frame."""

    framed = reader.readline(MAX_FRAME_BYTES + 2)
    if not framed:
        raise BoundedJsonError("NCP-LIMIT-009", "connection closed without a reply")
    if not framed.endswith(b"\n"):
        code = "NCP-LIMIT-001" if len(framed) > MAX_FRAME_BYTES else "NCP-LIMIT-009"
        detail = (
            "JSON frame byte limit exceeded before newline"
            if code == "NCP-LIMIT-001"
            else "JSON frame is not newline terminated"
        )
        raise BoundedJsonError(code, detail)
    payload = framed[:-1]
    if payload.endswith(b"\r"):
        payload = payload[:-1]
    if len(payload) > MAX_FRAME_BYTES:
        raise BoundedJsonError("NCP-LIMIT-001", "JSON frame byte limit exceeded")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise BoundedJsonError("NCP-LIMIT-008", "JSON frame is not strict UTF-8") from error

    _Scanner(text).scan()
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except BoundedJsonError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as error:
        raise BoundedJsonError("NCP-LIMIT-009", "JSON parser rejected admitted syntax") from error
    _enforce_named_collection_limits(value)
    return value
