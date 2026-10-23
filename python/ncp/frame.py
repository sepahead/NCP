"""Frames: the unit of transfer (specification sections 3 to 5).

A frame is a 12-byte header, a JSON region padded to a multiple of 8, aligned binary
attachments, and the SHA-256 digest of everything before it. Identities are digests of
exact bytes, so NCP needs no canonical encoding.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import sys
from typing import Any

MAGIC = b"NCP\x02"
HEADER = struct.Struct(">4sII")
HEADER_BYTES = 12
DIGEST_BYTES = 32
OVERHEAD = HEADER_BYTES + DIGEST_BYTES
HANDSHAKE_BOUND = 65_536
MAX_BOUND = 67_108_864
DEFAULT_BOUND = 1_048_576
MAX_DEPTH = 64
MAX_INTEGER = 2**53 - 1
MAX_ATTACHMENTS = 1024
ARRAY_KEY = "ncp.array"
# dtype -> (struct code for one element, element size, numpy dtype string)
DTYPES = {
    "u8": ("B", 1, "u1"), "i8": ("b", 1, "i1"), "u16": ("<H", 2, "<u2"), "i16": ("<h", 2, "<i2"),
    "u32": ("<I", 4, "<u4"), "i32": ("<i", 4, "<i4"), "u64": ("<Q", 8, "<u8"), "i64": ("<q", 8, "<i8"),
    "f32": ("<f", 4, "<f4"), "f64": ("<d", 8, "<f8"),
}
_PADDING = tuple(b" " * ((8 - n) % 8) for n in range(8))
_ZEROS = bytes(8)
_SURROGATE_ESCAPE = re.compile(r"\\u[dD][89a-fA-F]")  # may also match after an escaped backslash
_NEGATIVE_ZERO = re.compile(r"-0(?![.eE0-9])")  # may also match inside a string
_SURROGATE = re.compile("[\ud800-\udfff]")


class FrameError(ValueError):
    """A frame that violates sections 3 to 6. The receiver treats it as a bad frame."""


class Array:
    """A typed array carried in an attachment (section 5).

    `data` is a byte view of the little-endian elements. On a received frame, it is a
    zero-copy view into the frame.
    """

    __slots__ = ("dtype", "shape", "data", "_index")

    def __init__(self, dtype: str, shape: tuple[int, ...] | list[int], data: Any) -> None:
        if type(dtype) is not str or dtype not in DTYPES:
            raise FrameError(f"unknown dtype {dtype!r}")
        shape = tuple(shape)
        count = 1
        for n in shape:
            if type(n) is not int or not 0 <= n <= MAX_INTEGER:
                raise FrameError("array shape")
            count *= n
        view = memoryview(data)
        if view.format != "B" or view.ndim != 1:
            view = view.cast("B")
        if len(view) != count * DTYPES[dtype][1]:
            raise FrameError("array length differs from shape and dtype")
        self.dtype, self.shape, self.data, self._index = dtype, shape, view, -1

    @classmethod
    def from_numpy(cls, value: Any) -> "Array":
        """Wrap a numpy array. Non-contiguous or big-endian input is copied once."""
        kind = value.dtype.kind
        if kind not in "uif":
            raise FrameError(f"unsupported numpy dtype {value.dtype}")
        dtype = f"{kind}{value.dtype.itemsize * 8}"
        if dtype not in DTYPES:
            raise FrameError(f"unsupported numpy dtype {value.dtype}")
        little = value.astype(DTYPES[dtype][2], copy=False)
        if not little.flags.c_contiguous:
            little = little.copy(order="C")
        return cls(dtype, little.shape, little.reshape(-1).view("u1").data)

    def to_numpy(self) -> Any:
        """Return a read-only numpy view without a copy."""
        import numpy

        return numpy.frombuffer(self.data, dtype=DTYPES[self.dtype][2]).reshape(self.shape)

    def tolist(self) -> list[Any]:
        """Return the elements as a flat Python list."""
        code, size, _ = DTYPES[self.dtype]
        if size == 1:
            return list(self.data.cast(code))
        return [value for (value,) in struct.iter_unpack(code, self.data)]

    def __eq__(self, other: object) -> bool:
        return (isinstance(other, Array) and self.dtype == other.dtype and self.shape == other.shape
                and self.data == other.data)

    def __repr__(self) -> str:
        return f"Array({self.dtype!r}, {self.shape!r}, <{len(self.data)} bytes>)"


def encode(message: dict[str, Any]) -> bytes:
    """Encode one message as a frame. Arrays in the message become attachments.

    Arrays are `Array` objects or numpy arrays anywhere in the message. The encoder sets the
    `att` member; the caller must not set it.
    """
    if type(message) is not dict:
        raise FrameError("the message is not a dict")
    if "att" in message:
        raise FrameError("the encoder sets att")
    _check_tree(message)
    found: list[Array] = []

    def default(value: Any) -> Any:
        if not isinstance(value, Array):
            numpy = sys.modules.get("numpy")
            if numpy is not None and isinstance(value, numpy.generic):
                scalar = value.item()  # a numpy scalar is sent as a JSON number or boolean
                if type(scalar) is int and not -MAX_INTEGER <= scalar <= MAX_INTEGER:
                    raise FrameError("integer magnitude")
                return scalar
            if hasattr(value, "__array_interface__"):
                value = Array.from_numpy(value)
            else:
                raise TypeError(f"cannot encode {type(value).__name__}")
        found.append(value)
        return {ARRAY_KEY: {"dtype": value.dtype, "shape": list(value.shape), "att": len(found) - 1}}

    try:
        text = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
                          default=default)
        if found:
            if len(found) > MAX_ATTACHMENTS:
                raise FrameError("too many attachments")
            # The text is one JSON object; append the att member before its closing brace.
            text = text[:-1] + ("," if len(text) > 2 else "") + '"att":[' + ",".join(
                str(len(item.data)) for item in found) + "]}"
        payload = text.encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        if isinstance(error, FrameError):
            raise
        raise FrameError(f"cannot encode the message: {error}") from error
    padding = _PADDING[(HEADER_BYTES + len(payload)) % 8]
    parts: list[Any] = [b"", payload, padding]
    attachment_bytes = 0
    for index, item in enumerate(found):
        if index and attachment_bytes % 8:
            pad = 8 - attachment_bytes % 8
            parts.append(_ZEROS[:pad])
            attachment_bytes += pad
        parts.append(item.data)
        attachment_bytes += len(item.data)
    parts[0] = HEADER.pack(MAGIC, len(payload) + len(padding), attachment_bytes)
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part)
    parts.append(digest.digest())
    return b"".join(parts)  # the only copy of the frame bytes


def identity(frame: bytes | bytearray | memoryview) -> str:
    """The identity of a frame: its digest field as 64 lowercase hexadecimal characters."""
    return bytes(frame[-DIGEST_BYTES:]).hex()


def remaining_length(header: bytes | bytearray | memoryview, bound: int) -> int:
    """Check a frame header (section 3) and return the number of bytes that follow it."""
    if len(header) < HEADER_BYTES:
        raise FrameError("short header")
    magic, json_length, attachment_length = HEADER.unpack_from(header)
    if magic != MAGIC:
        raise FrameError("magic")
    if json_length < 2 or (HEADER_BYTES + json_length) % 8:
        raise FrameError("json region length")
    if OVERHEAD + json_length + attachment_length > bound:
        raise FrameError("frame exceeds the bound")
    return json_length + attachment_length + DIGEST_BYTES


class Decoded:
    """A decoded frame: its message, arrays, identity, and exact bytes."""

    __slots__ = ("message", "arrays", "identity", "frame")

    def __init__(self, message: dict[str, Any], arrays: list[Array], identity_hex: str, frame: Any) -> None:
        self.message, self.arrays, self.identity, self.frame = message, arrays, identity_hex, frame


def _reject_constant(name: str) -> Any:
    raise FrameError(f"json constant {name}")


def _check_tree(message: dict[str, Any]) -> None:
    """Check the rules of section 4 that json.dumps does not: member names are strings,
    integers are within 2**53 - 1, and nesting is at most MAX_DEPTH levels."""
    stack: list[tuple[Any, int]] = [(message, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise FrameError("nesting depth")
        if isinstance(item, dict):
            for key in item:
                if type(key) is not str:
                    raise FrameError("member names must be strings")
            children = item.values()
        else:
            children = item
        for child in children:
            kind = type(child)
            if kind is float or kind is str or kind is bool or child is None:
                continue
            if kind is int or isinstance(child, int):
                if not -MAX_INTEGER <= child <= MAX_INTEGER:
                    raise FrameError("integer magnitude")
            elif kind is dict or kind is list or kind is tuple or isinstance(child, (dict, list, tuple)):
                stack.append((child, depth + 1))
            elif depth + 3 > MAX_DEPTH and _is_array(child):
                # {"ncp.array": {"shape": [...]}} nests three levels below its container.
                raise FrameError("nesting depth")


def _is_array(value: Any) -> bool:
    if isinstance(value, Array):
        return True
    numpy = sys.modules.get("numpy")
    return hasattr(value, "__array_interface__") and not (numpy is not None and isinstance(value, numpy.generic))


def _integer(text: str) -> int:
    if text == "-0":
        raise FrameError("negative zero integer")
    value = int(text)
    if -MAX_INTEGER <= value <= MAX_INTEGER:
        return value
    raise FrameError("integer magnitude")


def decode(frame: bytes | bytearray | memoryview, bound: int, *, check_digest: bool = True) -> Decoded:
    """Check and decode one complete frame. Raise FrameError for a bad frame.

    With `check_digest=False`, the decoder does not compare the digest field with the frame
    bytes, and the identity is the digest field as received. Use it only on a pipe pair or a Unix
    domain socket with no other program between the two endpoints (spec section 3, rule 4).
    """
    view = memoryview(frame)
    rest = remaining_length(view, bound)
    if len(view) != HEADER_BYTES + rest:
        raise FrameError("frame length")
    _, json_length, attachment_length = HEADER.unpack_from(view)
    end = HEADER_BYTES + json_length + attachment_length
    if check_digest:
        digest = hashlib.sha256(view[:end]).digest()
        if digest != view[end:]:
            raise FrameError("digest")
    else:
        digest = bytes(view[end:])
    try:
        text = str(view[HEADER_BYTES:HEADER_BYTES + json_length], "utf-8")
    except UnicodeDecodeError as error:
        raise FrameError("json region is not UTF-8") from error
    if text.startswith("\ufeff"):
        raise FrameError("byte order mark")
    arrays_found: list[Array] = []

    def pairs(items: list[tuple[str, Any]]) -> Any:
        result = dict(items)
        if len(result) != len(items):
            raise FrameError("duplicate member name")
        if ARRAY_KEY in result:
            if len(result) != 1:
                raise FrameError("array object with other members")
            spec = result[ARRAY_KEY]
            if type(spec) is not dict or spec.keys() != {"dtype", "shape", "att"}:
                raise FrameError("array members")
            placeholder = Array.__new__(Array)
            placeholder.dtype, placeholder.shape, placeholder._index = spec["dtype"], spec["shape"], spec["att"]
            arrays_found.append(placeholder)
            return placeholder
        return result

    try:
        message = json.loads(text, object_pairs_hook=pairs, parse_constant=_reject_constant)
    except FrameError:
        raise
    except (ValueError, RecursionError) as error:
        raise FrameError("json") from error
    if type(message) is not dict:
        raise FrameError("json value is not an object")
    _check_decoded(message)
    if "-0" in text and _NEGATIVE_ZERO.search(text):
        # -0 written as an integer decodes to 0. Parse again with a callback to tell it apart
        # from the same characters in a string; this is rare, so the usual path stays fast.
        json.loads(text, parse_int=_integer, parse_constant=_reject_constant)
    # json.loads joins escaped surrogate pairs and the UTF-8 decoder refuses encoded surrogates,
    # so a surrogate left in a decoded string comes from an unpaired escape.
    if "\\u" in text and _SURROGATE_ESCAPE.search(text) and _has_surrogate(message):
        raise FrameError("unpaired surrogate")
    arrays = _bind_arrays(message, arrays_found, view[HEADER_BYTES + json_length:end], attachment_length)
    return Decoded(message, arrays, digest.hex(), frame)


def _check_decoded(message: dict[str, Any]) -> None:
    """The rules of section 4 that json.loads does not check: integer magnitude, finite numbers,
    and nesting depth, counting the three levels of each array reference."""
    isfinite = math.isfinite
    stack: list[tuple[Any, int]] = [(message, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_DEPTH:
            raise FrameError("nesting depth")
        for child in (item.values() if type(item) is dict else item):
            kind = type(child)
            if kind is int:
                if not -MAX_INTEGER <= child <= MAX_INTEGER:
                    raise FrameError("integer magnitude")
            elif kind is float:
                if not isfinite(child):
                    raise FrameError("number outside the binary64 range")
            elif kind is dict or kind is list:
                stack.append((child, depth + 1))
            elif kind is Array and depth + 3 > MAX_DEPTH:
                raise FrameError("nesting depth")


def _has_surrogate(value: Any) -> bool:
    stack = [value]
    while stack:
        item = stack.pop()
        kind = type(item)
        if kind is str:
            if _SURROGATE.search(item):
                return True
        elif kind is dict:
            stack.extend(item.keys())
            stack.extend(item.values())
        elif kind is list:
            stack.extend(item)
    return False


def _bind_arrays(message: dict[str, Any], placeholders: list[Array], region: memoryview,
                 attachment_length: int) -> list[Array]:
    if "att" not in message:
        lengths: list[int] = []
    else:
        lengths = message["att"]
        if type(lengths) is not list or len(lengths) > MAX_ATTACHMENTS or not all(
                type(n) is int and n >= 0 for n in lengths):
            raise FrameError("att")
    if not lengths:
        if attachment_length or placeholders:
            raise FrameError("attachments without att")
        return []
    offsets = []
    offset = 0
    for index, length in enumerate(lengths):
        if index and offset % 8:
            pad = 8 - offset % 8
            if region[offset:offset + pad] != _ZEROS[:pad]:
                raise FrameError("nonzero attachment padding")
            offset += pad
        offsets.append(offset)
        offset += length
    if offset != attachment_length:
        raise FrameError("attachment region length")
    bound: list[Array | None] = [None] * len(lengths)
    for placeholder in placeholders:
        index = placeholder._index
        if type(index) is not int or not 0 <= index < len(lengths) or bound[index] is not None:
            raise FrameError("array attachment index")
        if type(placeholder.shape) is not list:
            raise FrameError("array shape")
        real = Array(placeholder.dtype, placeholder.shape,
                     region[offsets[index]:offsets[index] + lengths[index]])
        placeholder.dtype, placeholder.shape, placeholder.data = real.dtype, real.shape, real.data
        bound[index] = placeholder
    if any(item is None for item in bound):
        raise FrameError("attachment without array")
    return bound  # type: ignore[return-value]
