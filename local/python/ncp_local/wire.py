"""Independent bounded JSON, typed digests, and private-channel framing.

The structural scanner derives from NCP's independent Python smoke peer.
It checks decoded key identity and resource limits before generic object decoding.
No Rust extension, generated decoder, or FFI path is used.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import os
import select
import struct
import time
from typing import Any, BinaryIO

MAX_FRAME_BYTES = 65_536
MAX_NESTING_DEPTH = 32
MAX_OBJECTS = 4_096
MAX_ARRAYS = 4_096
MAX_TOTAL_MEMBERS = 16_384
MAX_TOTAL_ARRAY_ITEMS = 262_144
MAX_OBJECT_MEMBERS = 4_096
MAX_ARRAY_ITEMS = 65_536
MAX_KEY_BYTES = 128
MAX_STRING_BYTES = 65_536
MAX_TOTAL_STRING_BYTES = 1_048_576
MAX_SEQUENCE = 9_007_199_254_740_991
MAX_FINITE_NUMBER_MAGNITUDE = 1e300
MAX_PROJECTION_BYTES = 2_097_152
DIGEST_DOMAINS = frozenset(
    {
        "ncp.local.request.v1",
        "ncp.local.response.v1",
        "ncp.local.profile.v1",
        "ncp.local.snapshot.v1",
        "ncp.local.plan.v1",
        "ncp.local.capture.v1",
    }
)


class LocalError(RuntimeError):
    """One closed protocol code, without untrusted payload details."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"local NCP error: {code}")


class LocalPreflightError(LocalError):
    """The client rejected this call before attempting any channel write.

    This local disposition is not a peer response or evidence of peer state.
    Once a write is attempted, failures use execution_unknown instead.
    """


class BoundedJsonError(LocalError):
    """A universal ingress rejection found before object decoding."""

    def __init__(self, limit_code: str, detail: str) -> None:
        self.limit_code = limit_code
        super().__init__("wire")


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
        elif token == "-" or (
            token is not None and token.isascii() and token.isdigit()
        ):
            self._parse_number()
        else:
            self._fail("NCP-LIMIT-009", "expected a JSON value")

    def _parse_literal(self, literal: str) -> None:
        if not self.text.startswith(literal, self.position):
            self._fail(
                "NCP-LIMIT-009", f"invalid JSON literal starting with {literal[0]!r}"
            )
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
            while (
                (digit := self._peek()) is not None
                and digit.isascii()
                and digit.isdigit()
            ):
                self.position += 1
        else:
            self._fail("NCP-LIMIT-009", "invalid JSON number integer part")

        if self._peek() == ".":
            self.position += 1
            digit = self._peek()
            if digit is None or not digit.isascii() or not digit.isdigit():
                self._fail("NCP-LIMIT-009", "JSON fraction requires a digit")
            while (
                (digit := self._peek()) is not None
                and digit.isascii()
                and digit.isdigit()
            ):
                self.position += 1

        if self._peek() in {"e", "E"}:
            self.position += 1
            if self._peek() in {"+", "-"}:
                self.position += 1
            digit = self._peek()
            if digit is None or not digit.isascii() or not digit.isdigit():
                self._fail("NCP-LIMIT-009", "JSON exponent requires a digit")
            while (
                (digit := self._peek()) is not None
                and digit.isascii()
                and digit.isdigit()
            ):
                self.position += 1

        spelling = self.text[start : self.position]
        if not any(marker in spelling for marker in ".eE"):
            magnitude = spelling.lstrip("-")
            if len(magnitude) > 16 or (
                len(magnitude) == 16 and magnitude > "9007199254740991"
            ):
                self._fail("NCP-LIMIT-006", "integer exceeds the exact JSON range")
        value = float(spelling)
        if not math.isfinite(value) or abs(value) > MAX_FINITE_NUMBER_MAGNITUDE:
            self._fail("NCP-LIMIT-006", "number exceeds the finite magnitude budget")

    def _take_hex_unit(self) -> int:
        end = self.position + 4
        digits = self.text[self.position : end]
        if len(digits) != 4 or any(
            character not in "0123456789abcdefABCDEF" for character in digits
        ):
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
                        decoded = chr(
                            0x10000 + ((unit - 0xD800) << 10) + (low - 0xDC00)
                        )
                    elif 0xDC00 <= unit <= 0xDFFF:
                        self._fail("NCP-LIMIT-008", "unpaired low surrogate")
                    else:
                        decoded = chr(unit)
                else:
                    self._fail("NCP-LIMIT-008", "invalid JSON escape")
            else:
                if ord(character) <= 0x1F:
                    self._fail(
                        "NCP-LIMIT-008", "unescaped control character in JSON string"
                    )
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
            if (
                local_items > MAX_ARRAY_ITEMS
                or self.array_items > MAX_TOTAL_ARRAY_ITEMS
            ):
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


def preflight(payload: bytes) -> None:
    """Admit structural bytes without creating the JSON object tree."""
    if type(payload) is not bytes or not payload or len(payload) > MAX_FRAME_BYTES:
        raise LocalError("capacity")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise BoundedJsonError("NCP-LIMIT-008", "invalid UTF-8") from error
    _Scanner(text).scan()


def decode(payload: bytes) -> Any:
    """Decode only after preflight; preserve the sign of lexical integer -0."""
    preflight(payload)
    return json.loads(
        payload, parse_int=lambda token: -0.0 if token == "-0" else int(token)
    )


def _check_value(value: Any, depth: int, counts: dict[str, int]) -> None:
    # This validates programmatic values before JSONEncoder can allocate tokens.
    if depth > MAX_NESTING_DEPTH:
        raise LocalError("capacity")
    counts["nodes"] += 1
    if counts["nodes"] > 279_000:
        raise LocalError("capacity")
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float):
        if type(value) is int and abs(value) > MAX_SEQUENCE:
            raise LocalError("wire")
        if not math.isfinite(value) or abs(value) > MAX_FINITE_NUMBER_MAGNITUDE:
            raise LocalError("wire")
        return
    if type(value) is str:
        if len(value) > MAX_STRING_BYTES:
            raise LocalError("capacity")
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError as error:
            raise LocalError("wire") from error
        counts["strings"] += size
        if size > MAX_STRING_BYTES or counts["strings"] > MAX_TOTAL_STRING_BYTES:
            raise LocalError("capacity")
        return
    if type(value) is list:
        counts["arrays"] += 1
        counts["items"] += len(value)
        if (
            depth == MAX_NESTING_DEPTH
            or len(value) > MAX_ARRAY_ITEMS
            or counts["arrays"] > MAX_ARRAYS
            or counts["items"] > MAX_TOTAL_ARRAY_ITEMS
        ):
            raise LocalError("capacity")
        for item in value:
            _check_value(item, depth + 1, counts)
        return
    if type(value) is dict:
        counts["objects"] += 1
        counts["members"] += len(value)
        if (
            depth == MAX_NESTING_DEPTH
            or len(value) > MAX_OBJECT_MEMBERS
            or counts["objects"] > MAX_OBJECTS
            or counts["members"] > MAX_TOTAL_MEMBERS
        ):
            raise LocalError("capacity")
        for key, item in value.items():
            if type(key) is not str:
                raise LocalError("wire")
            if len(key) > MAX_KEY_BYTES:
                raise LocalError("capacity")
            _check_value(key, depth + 1, counts)
            if len(key.encode("utf-8")) > MAX_KEY_BYTES:
                raise LocalError("capacity")
            _check_value(item, depth + 1, counts)
        return
    raise LocalError("wire")


def check_value(value: Any) -> None:
    _check_value(
        value, 0, dict(nodes=0, strings=0, arrays=0, items=0, objects=0, members=0)
    )


def encode(value: Any) -> bytes:
    """Serialize supported values while retaining at most one bounded wire frame."""
    check_value(value)
    output = bytearray()
    encoder = json.JSONEncoder(
        ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    for token in encoder.iterencode(value):
        encoded = token.encode("utf-8")
        if len(encoded) > MAX_FRAME_BYTES - len(output):
            raise LocalError("capacity")
        output.extend(encoded)
    payload = bytes(output)
    preflight(payload)
    return payload


def local_digest(domain: str, value: Any) -> str:
    """Hash the domain-separated typed binary64 projection, independently."""
    if domain not in DIGEST_DOMAINS:
        raise LocalError("wire")
    check_value(value)
    output = bytearray(domain.encode("ascii") + b"\0")

    def append(data: bytes) -> None:
        if len(data) > MAX_PROJECTION_BYTES - len(output):
            raise LocalError("capacity")
        output.extend(data)

    def string(text: str) -> None:
        data = text.encode("utf-8")
        append(b"\x04" + struct.pack(">Q", len(data)))
        append(data)

    def visit(item: Any) -> None:
        if item is None:
            append(b"\x00")
        elif type(item) is bool:
            append(b"\x02" if item else b"\x01")
        elif type(item) in (int, float):
            append(b"\x03" + struct.pack(">d", float(item)))
        elif type(item) is str:
            string(item)
        elif type(item) is list:
            append(b"\x05" + struct.pack(">Q", len(item)))
            for child in item:
                visit(child)
        else:
            append(b"\x06" + struct.pack(">Q", len(item)))
            for key in sorted(item, key=lambda key: key.encode("utf-8")):
                string(key)
                visit(item[key])

    visit(value)
    return hashlib.sha256(output).hexdigest()


def digest_without(domain: str, value: dict[str, Any], member: str) -> str:
    return local_digest(
        domain, {key: item for key, item in value.items() if key != member}
    )


def _fd(stream: BinaryIO) -> int | None:
    try:
        return stream.fileno()
    except (AttributeError, OSError):
        return None


def _wait(fd: int, deadline: float, *, writing: bool = False) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LocalError("execution_unknown")
    ready = select.select(
        [] if writing else [fd], [fd] if writing else [], [], remaining
    )
    if not ready[0 if not writing else 1]:
        raise LocalError("execution_unknown")


def _read_exact(
    reader: BinaryIO, length: int, deadline: float | None, *, clean_eof: bool = False
) -> bytes:
    output = bytearray()
    fd = _fd(reader) if deadline is not None else None
    if deadline is not None and fd is None and not isinstance(reader, io.BytesIO):
        raise LocalError("wire")
    while len(output) < length:
        if fd is not None:
            _wait(fd, deadline)
            chunk = os.read(fd, length - len(output))
        else:
            chunk = reader.read(length - len(output))
        if not chunk:
            if clean_eof and not output:
                return b""
            raise LocalError("wire")
        if len(chunk) > length - len(output):
            raise LocalError("wire")
        output.extend(chunk)
    return bytes(output)


def read_local_frame(
    reader: BinaryIO, *, deadline: float | None = None
) -> bytes | None:
    """Read u32BE length before any payload allocation. Empty EOF is explicit."""
    header = _read_exact(reader, 4, deadline, clean_eof=True)
    if not header:
        return None
    length = struct.unpack(">I", header)[0]
    if length == 0 or length > MAX_FRAME_BYTES:
        raise LocalError("capacity")
    return _read_exact(reader, length, deadline)


def write_local_frame(
    writer: BinaryIO, payload: bytes, *, deadline: float | None = None
) -> None:
    """Write one complete frame. A deadline requires an OS pipe or BytesIO."""
    if type(payload) is not bytes or not payload or len(payload) > MAX_FRAME_BYTES:
        raise LocalError("capacity")
    fd = _fd(writer) if deadline is not None else None
    if deadline is not None and fd is None and not isinstance(writer, io.BytesIO):
        raise LocalError("wire")
    for part in (struct.pack(">I", len(payload)), payload):
        view = memoryview(part)
        while view:
            if fd is not None:
                _wait(fd, deadline, writing=True)
                # PIPE_BUF-sized writes cannot wait for an entire large frame.
                count = os.write(fd, view[:512])
            else:
                count = writer.write(view)
            if count is None or count <= 0 or count > len(view):
                raise LocalError("wire")
            view = view[count:]
    writer.flush()
