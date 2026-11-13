#!/usr/bin/env python3
"""Generate conformance/vectors.json from the rules of spec/NCP-2.md.

The expected results come from the specification, written out below case by case. Valid frames
are encoded with the Python SDK; every implementation must decode them to the stated message
and identity, so the encoder is checked too. Invalid frames are built byte by byte.

The file holds these parts. Each implementation runs the parts that it implements.

  frames       decoding: valid frames with their message, identity, and arrays; invalid frames
  messages     the member rules of section 6: request, response, and stream shapes
  auth         authenticated frames (section 13.2)
  scenarios    owner rules (sections 7.1 to 7.3): requests in order and the expected outcome
  clients      client rules (section 7.6): events and the expected verdict and state
  streams      subscriber rules (section 8)
  transcripts  transcript files (section 10) and the expected verification
  contracts    contract documents (section 11): valid or not
  schemas      schema checks (section 11.1): a schema, a value, and whether it matches

Usage: generate.py [OUTPUT ...]   (default: vectors.json next to this file and the copy in the
Python package, python/ncp/vectors.json, which `python -m ncp conformance` uses)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python"))
import ncp  # noqa: E402
from ncp import client as C  # noqa: E402
from ncp import frame as F  # noqa: E402
from ncp import transcript as T  # noqa: E402

REVISION = 3
SESSION = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b"
NONCE = "00112233445566778899aabbccddeeff"
KEY = bytes(range(32))
CONTRACT = (
    b'{"ncp_contract":1,"application":"conformance","version":"2","operations":{"step":{},"fail":{},'
    b'"big":{},"flaky":{},"typed":{"ncp.schema":{"request":{"type":"object","required":["n"],'
    b'"properties":{"n":{"type":"integer","minimum":0,"maximum":9},"v":{"ncp.array":{"dtype":"f64",'
    b'"shape":[null]}}},"additionalProperties":false}}}},"streams":{"sensor":{}}}'
)
CONTRACT_ID = hashlib.sha256(CONTRACT).hexdigest()
HANDLER = {
    "step": 'result {"echo": body}; the body {"invalid": true} is declined as body_invalid',
    "fail": "raises: owner_failure",
    "big": 'result {"blob": "z" repeated body.size times}',
    "flaky": "the first validation of each owner declines with body_invalid; every later validation accepts; "
    'result {"echo": body}',
    "typed": 'result {"echo": body}; the request schema of the contract applies',
}


def raw(text: bytes, attachments: bytes = b"", pad: bytes | None = None, key: bytes | None = None) -> bytes:
    """A frame around exact JSON bytes, with a correct digest."""
    payload = text + (b" " * ((8 - (12 + len(text)) % 8) % 8) if pad is None else pad)
    body = struct.pack(">4sII", F.MAGIC, len(payload), len(attachments)) + payload + attachments
    digest = hashlib.sha256(body).digest() if key is None else hmac.new(key, body, hashlib.sha256).digest()
    return body + digest


def attachments_frame(count: int) -> bytes:
    """A frame with `count` empty u8 arrays, each with its own attachment of length 0."""
    arrays = b",".join(b'{"ncp.array":{"dtype":"u8","shape":[0],"att":%d}}' % i for i in range(count))
    return raw(b'{"att":[' + b",".join([b"0"] * count) + b'],"v":[' + arrays + b"]}")


def plain(value, decoded):
    if isinstance(value, F.Array):
        index = next(i for i, item in enumerate(decoded.arrays) if item is value)  # not by equal content
        return {"ncp.array": {"dtype": value.dtype, "shape": list(value.shape), "att": index}}
    if isinstance(value, dict):
        return {k: plain(v, decoded) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v, decoded) for v in value]
    return value


# Frames and messages above this size are stored compactly; see frame_field.
LARGE = 65536


def frame_field(frame: bytes) -> str | dict:
    """A frame as the vectors store it: hexadecimal, or, for a large frame with long runs of one
    byte, {"parts": [[HEX, COUNT], ...]}: the frame is the bytes of each HEX repeated COUNT times,
    in order. The runners read both forms."""
    if len(frame) < LARGE:
        return frame.hex()
    parts: list[list] = []
    literal = bytearray()
    start = 0
    while start < len(frame):
        end = start
        while end < len(frame) and frame[end] == frame[start]:
            end += 1
        if end - start >= 64:
            if literal:
                parts.append([literal.hex(), 1])
                literal = bytearray()
            parts.append([frame[start : start + 1].hex(), end - start])
        else:
            literal += frame[start:end]
        start = end
    if literal:
        parts.append([literal.hex(), 1])
    return {"parts": parts} if 2 * len(json.dumps(parts)) < 2 * len(frame) // 2 else frame.hex()


def valid(name: str, frame: bytes, bound: int = F.HANDSHAKE_BOUND) -> dict:
    decoded = F.decode(frame, bound)
    case = {
        "name": name,
        "frame": frame_field(frame),
        "bound": bound,
        "valid": True,
        "message": plain(decoded.message, decoded),
        "identity": decoded.identity,
        "arrays": [bytes(item.data).hex() for item in decoded.arrays],
    }
    if len(json.dumps(case["message"])) > LARGE:
        del case["message"]  # the identity and the arrays check a frame this large
    return case


def invalid(name: str, frame: bytes, bound: int = F.HANDSHAKE_BOUND) -> dict:
    try:
        F.decode(frame, bound)
    except F.FrameError:
        pass
    else:
        raise AssertionError(f"the Python decoder accepts the invalid vector {name!r}")
    return {"name": name, "frame": frame_field(frame), "bound": bound, "valid": False}


def frames() -> list[dict]:
    cases = [
        valid("minimal object", F.encode({})),
        valid(
            "request without attachments",
            F.encode(
                {"ncp": 2, "session": SESSION, "seq": 1, "op": "step", "ack": "a" * 64, "body": {"x": 1.5, "s": "é∑😀"}}
            ),
        ),
        valid("numbers", F.encode({"i": 9007199254740991, "n": -9007199254740991, "f": 1e300, "g": -2.5e-308, "z": 0})),
        valid("unicode escapes are decoded", raw(b'{"a":"\\u00e9\\ud83d\\ude00"}')),
        valid(
            "arrays of every dtype",
            F.encode({"v": [F.Array(d, [2], bytes(range(s * 2))) for d, (_, s, _) in F.DTYPES.items()]}),
        ),
        valid(
            "zero-length and empty-shape arrays",
            F.encode({"e": F.Array("f64", [0], b""), "s": F.Array("i32", [], struct.pack("<i", -7))}),
        ),
        valid("nested array reference", F.encode({"a": [{"b": {"c": F.Array("u8", [3], b"xyz")}}]})),
        valid("one empty array: att [0] and A = 0", F.encode({"e": F.Array("f64", [0], b"")})),
        valid(
            "empty attachment after an unaligned one",
            F.encode({"a": F.Array("u8", [1], b"a"), "b": F.Array("u8", [0], b"")}),
        ),
        valid("negative zero float", F.encode({"a": -0.0})),
        # JSON text "\\ud83d/": an escaped backslash, then the letters ud83d. No surrogate.
        valid("escaped backslash before u and hex digits", F.encode({"a": "\\ud83d/", "\\udc00": 1})),
        valid("escaped backslash, then an escaped solidus", raw(b'{"a":"\\\\ud83d\\/"}')),
        valid("white space between tokens", raw(b'{ "a" : [ 1 , 2 ] }')),
        # 12 + J is a multiple of 8, so the largest JSON region is 1 MiB minus 4 bytes.
        valid("the largest JSON region: 1 MiB minus 4 bytes", raw(b'{"a":"' + b"x" * (F.MAX_JSON - 16) + b'"}'), F.MAX_BOUND),
        # Section 5, rule 4: at most 1024 attachments.
        valid("1024 attachments", attachments_frame(1024)),
    ]
    good = F.encode({"a": 1})

    def array_at(lists: int) -> bytes:
        # The object is level 1, the lists levels 2 to lists + 1, then the array reference,
        # its spec, and its shape list: the shape list is at level lists + 4.
        return (
            b'{"a":'
            + b"[" * lists
            + b'{"ncp.array":{"dtype":"u8","shape":[1],"att":0}}'
            + b"]" * lists
            + b',"att":[1]}'
        )

    cases.append(valid("array shape list at level 64", raw(array_at(60), b"x")))
    cases.append(valid("63 nested arrays inside the object (64 levels)", raw(b'{"a":' + b"[" * 63 + b"]" * 63 + b"}")))
    over_json = raw(b'{"a":"' + b"x" * (F.MAX_JSON - 8) + b'"}')
    cases += [
        invalid("64 nested arrays inside the object (65 levels)", raw(b'{"a":' + b"[" * 64 + b"]" * 64 + b"}")),
        invalid("array shape list at level 65", raw(array_at(61), b"x")),
        invalid(
            "dtype that is a list", raw(b'{"att":[1],"v":{"ncp.array":{"dtype":["u8"],"shape":[1],"att":0}}}', b"x")
        ),
        invalid(
            "shape element 2^53 with a zero product",
            raw(b'{"att":[0],"v":{"ncp.array":{"dtype":"u8","shape":[9007199254740992,0],"att":0}}}'),
        ),
        invalid("digest", good[:-1] + bytes([good[-1] ^ 1])),
        invalid("magic version 1", b"NCP\x01" + good[4:]),
        invalid("json region not aligned", raw(b"{}", pad=b"")),
        invalid("eight spaces of padding", raw(b'{"a":1}', pad=b" " * 9)),
        invalid("padding of tabs and newlines", raw(b'{"a":1}', pad=b"\t\n\r\n ")),
        invalid("leading spaces", raw(b"        " + b'{"a":1}')),
        invalid("padding of zero bytes", raw(b'{"a":1}', pad=b"\x00")),
        invalid("a JSON region of 1 MiB plus 4 bytes", over_json, F.MAX_BOUND),
        invalid("trailing byte", good + b"\x00"),
        invalid("exceeds the bound", F.encode({"a": "x" * 70_000})),
        invalid("duplicate member", raw(b'{"a":1,"a":1}')),
        invalid("integer 2^53", raw(b'{"a":9007199254740992}')),
        invalid("negative integer 2^53", raw(b'{"a":-9007199254740992}')),
        invalid("integer beyond 64 bits", raw(b'{"a":100000000000000000000}')),
        invalid("integer written as -0", raw(b'{"a":-0}')),
        # JSON text "\\ud83d\ude00": an escaped backslash, the letters ud83d, then an unpaired
        # low surrogate escape.
        invalid("unpaired low surrogate after an escaped backslash", raw(b'{"a":"\\\\ud83d\\ude00"}')),
        invalid(
            "sequence number written as -0",
            raw(b'{"ncp":2,"session":"' + SESSION.encode() + b'","seq":-0,"op":"open","ack":null,"body":{}}'),
        ),
        invalid(
            "shape product beyond 64 bits",
            raw(b'{"att":[0],"v":{"ncp.array":{"dtype":"u8","shape":[4294967296,4294967296],"att":0}}}'),
        ),
        valid(
            "a dimension 0 makes the number of elements 0, also beside large dimensions",
            raw(b'{"att":[0],"v":{"ncp.array":{"dtype":"u8","shape":[1099511627776,1099511627776,0],"att":0}}}'),
        ),
        valid(
            "a shape of 32 dimensions",
            raw(b'{"att":[1],"v":{"ncp.array":{"dtype":"u8","shape":[' + b",".join([b"1"] * 32) + b'],"att":0}}}', b"x"),
        ),
        invalid(
            "a shape of 33 dimensions",
            raw(b'{"att":[1],"v":{"ncp.array":{"dtype":"u8","shape":[' + b",".join([b"1"] * 33) + b'],"att":0}}}', b"x"),
        ),
        invalid("float beyond binary64", raw(b'{"a":1e400}')),
        invalid("NaN literal", raw(b'{"a":NaN}')),
        invalid("Infinity literal", raw(b'{"a":Infinity}')),
        invalid("unpaired high surrogate", raw(b'{"a":"\\ud83d"}')),
        invalid("unpaired low surrogate", raw(b'{"a":"\\ude00"}')),
        invalid("byte order mark", raw(b'\xef\xbb\xbf{"a":1}')),
        invalid("invalid UTF-8", raw(b'{"a":"\xff"}')),
        invalid("top-level array", raw(b"[1]")),
        invalid("trailing garbage", raw(b'{"a":1}x')),
        invalid("att null", raw(b'{"att":null}')),
        invalid("att without attachments", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}')),
        invalid("attachments without att", raw(b'{"a":1}', b"abcd")),
        invalid("attachment without array", raw(b'{"att":[4]}', b"abcd")),
        invalid("array without attachment", raw(b'{"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}')),
        invalid(
            "array length mismatch", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u16","shape":[4],"att":0}}}', b"abcd")
        ),
        invalid("unknown dtype", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"c64","shape":[1],"att":0}}}', b"abcd")),
        invalid(
            "attachment used twice",
            raw(
                b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}},'
                b'"w":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}',
                b"abcd",
            ),
        ),
        invalid(
            "array object with another member",
            raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0},"x":1}}', b"abcd"),
        ),
        invalid("negative shape", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[-4],"att":0}}}', b"abcd")),
        invalid("1025 attachments", attachments_frame(1025)),
        invalid(
            "nonzero padding between attachments",
            raw(
                b'{"att":[1,1],"v":{"ncp.array":{"dtype":"u8","shape":[1],"att":0}},'
                b'"w":{"ncp.array":{"dtype":"u8","shape":[1],"att":1}}}',
                b"a\x01\x00\x00\x00\x00\x00\x00b",
            ),
        ),
    ]
    return cases


def messages() -> list[dict]:
    """Member rules of section 6. Each frame decodes; `valid` says whether the message has the
    stated form."""
    request = {"ncp": 2, "session": SESSION, "seq": 1, "op": "step", "ack": "b" * 64, "body": {}}
    response = {"ncp": 2, "session": SESSION, "seq": 1, "request": "c" * 64, "outcome": "ok", "code": None, "body": {}}
    stream = {"ncp": 2, "stream": "sensor/a", "seq": 2, "prev": "d" * 64, "contract": CONTRACT_ID, "body": {}}

    def case(kind: str, name: str, message: dict, ok: bool, text: bytes | None = None) -> dict:
        frame = F.encode(message) if text is None else raw(text)
        return {"kind": kind, "name": name, "frame": frame.hex(), "valid": ok}

    def text_of(message: dict, old: bytes, new: bytes) -> bytes:
        text = json.dumps(message, separators=(",", ":")).encode()
        assert text.count(old) == 1, (old, text)
        return text.replace(old, new)

    nameless = {**response, "session": None, "seq": None, "request": None, "outcome": "ended", "code": "bad_frame"}
    return [
        case("request", "a request", request, True),
        case("request", "ncp 3 has the request form; the owner rejects it", {**request, "ncp": 3}, True),
        case("request", "ncp -1", request, False, text_of(request, b'"ncp":2', b'"ncp":-1')),
        case("request", "ncp 2.0", request, False, text_of(request, b'"ncp":2', b'"ncp":2.0')),
        case("request", "ncp true", request, False, text_of(request, b'"ncp":2', b'"ncp":true')),
        case("request", "session in upper case", {**request, "session": SESSION.upper()}, False),
        case("request", "session of UUID version 1", {**request, "session": SESSION[:14] + "1" + SESSION[15:]}, False),
        case("request", "negative seq", {**request, "seq": -1}, False),
        case("request", "op with an upper-case letter", {**request, "op": "Step"}, False),
        case("request", "op of 65 characters", {**request, "op": "a" * 65}, False),
        case("request", "op of 64 characters", {**request, "op": "a" * 64}, True),
        case("request", "ack that is not an identity", {**request, "ack": "B" * 64}, False),
        case("request", "an extra member", {**request, "extra": 1}, False),
        case("request", "a missing member", {k: v for k, v in request.items() if k != "body"}, False),
        case("foreign", "protocol 3 with other members", {"ncp": 3, "session": SESSION, "seq": 1, "later": [1]}, True),
        case("foreign", "protocol 3 with the request form", {**request, "ncp": 3}, True),
        case("foreign", "protocol 2 is not foreign", request, False),
        case("foreign", "protocol 3 without seq", {"ncp": 3, "session": SESSION, "later": [1]}, False),
        case("foreign", "protocol 3 with a session that is not a UUID", {"ncp": 3, "session": "x", "seq": 1}, False),
        case("foreign", "ncp true", request, False, text_of(request, b'"ncp":2', b'"ncp":true')),
        case("response", "an ok response", response, True),
        case("response", "ok with a code", {**response, "code": "x"}, False),
        case("response", "a declined response", {**response, "outcome": "declined", "code": "body_invalid"}, True),
        case(
            "response",
            "declined with a body that is not an object",
            {**response, "outcome": "declined", "code": "body_invalid", "body": 1},
            False,
        ),
        case("response", "rejected without a code", {**response, "outcome": "rejected"}, False),
        case(
            "response",
            "rejected with a session that is not a UUID",
            {**response, "session": "x", "outcome": "rejected", "code": "seq_gap"},
            False,
        ),
        case("response", "a code with a capital letter", {**response, "outcome": "ended", "code": "Owner_failure"}, False),
        case("response", "an unknown code", {**response, "outcome": "ended", "code": "later_reason"}, True),
        case("response", "an unknown outcome", {**response, "outcome": "maybe", "code": "x"}, False),
        case("response", "an ended response that names no request", nameless, True),
        case("response", "ok that names no request", {**nameless, "outcome": "ok", "code": None}, False),
        case("response", "partly null names", {**nameless, "seq": 1}, False),
        case("stream", "a stream message", stream, True),
        case("stream", "the first message", {**stream, "seq": 1, "prev": None}, True),
        case("stream", "a first message with prev", {**stream, "seq": 1}, False),
        case("stream", "seq 0", {**stream, "seq": 0, "prev": None}, False),
        case("stream", "ncp 3", {**stream, "ncp": 3}, False),
        case("stream", "ncp 2.0", stream, False, text_of(stream, b'"ncp":2', b'"ncp":2.0')),
        case("stream", "a stream identifier with a space", {**stream, "stream": "a b"}, False),
    ]


def auth() -> list[dict]:
    """Authenticated frames (section 13.2), with the key of the file."""
    message = {"ncp": 2, "session": SESSION, "seq": 0, "op": "open", "ack": None, "body": {}}
    keyed = F.encode(message, key=KEY)
    plain_frame = F.encode(message)
    damaged = keyed[:20] + bytes([keyed[20] ^ 1]) + keyed[21:]
    other = F.encode(message, key=bytes(reversed(KEY)))
    return [
        {"name": "a frame with the key", "frame": keyed.hex(), "valid_with_key": True, "valid_without_key": False,
         "identity": F.identity(keyed)},
        {"name": "a frame with SHA-256", "frame": plain_frame.hex(), "valid_with_key": False, "valid_without_key": True,
         "identity": F.identity(plain_frame)},
        {"name": "a damaged frame with the key", "frame": damaged.hex(), "valid_with_key": False,
         "valid_without_key": False, "identity": None},
        {"name": "a frame with another key", "frame": other.hex(), "valid_with_key": False, "valid_without_key": False,
         "identity": None},
    ]


# Owner scenarios. In a body, an object {"array": DTYPE, "values": [...]} stands for an array of
# section 5 with these values and the shape [len(values)]. Each step: seq, op, body, ack ("last" =
# identity of the last kept response,
# "stale" = the kept response before it, "none" = null, "other" = 64 zeros), and the expected
# (outcome, code). "repeat": index of an earlier step whose frame is sent again; its response must
# be the identical bytes when it was kept. "stop": the harness stops the owner (rule 7.3.10); an
# implementation that offers no stop through its interface skips the scenario. "owner": a fresh
# owner from here on.
def scenarios() -> list[dict]:
    open_step = {"seq": 0, "op": "open", "ack": "none", "open": {"bound": F.HANDSHAKE_BOUND}, "expect": ["ok", None]}
    return [
        {
            "name": "happy path, ping, and close",
            "steps": [
                open_step,
                {"seq": 1, "op": "step", "body": {"x": 1}, "ack": "last", "expect": ["ok", None]},
                {"seq": 2, "op": "ncp.ping", "body": {}, "ack": "last", "expect": ["ok", None]},
                {"seq": 3, "op": "step", "body": {"x": 2}, "ack": "last", "expect": ["ok", None]},
                {"seq": 4, "op": "close", "body": {}, "ack": "last", "expect": ["ok", None]},
                {"seq": 5, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "session_ended"]},
                {"repeat": 4, "expect": ["ok", None]},
            ],
        },
        {
            "name": "protocol rejections change nothing; a declined request advances the session",
            "steps": [
                open_step,
                {"seq": 1, "op": "step", "body": {}, "ack": "none", "expect": ["rejected", "ack_missing"]},
                {"seq": 1, "op": "step", "body": {}, "ack": "other", "expect": ["rejected", "ack_mismatch"]},
                {"seq": 2, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "seq_gap"]},
                {"seq": 1, "op": "open", "body": {}, "ack": "last", "expect": ["rejected", "already_open"]},
                {"seq": 1, "op": "missing", "body": {}, "ack": "last", "expect": ["declined", "unknown_op"]},
                {"repeat": 5, "expect": ["declined", "unknown_op"]},
                {"seq": 2, "op": "step", "body": {"invalid": True}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {"seq": 3, "op": "step", "body": {"x": 1}, "ack": "last", "expect": ["ok", None]},
                {"repeat": 8, "expect": ["ok", None]},
                {"seq": 3, "op": "step", "body": {"x": 2}, "ack": "stale", "expect": ["rejected", "seq_conflict"]},
                {"repeat": 5, "expect": ["rejected", "seq_stale"]},
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"bound": F.HANDSHAKE_BOUND},
                    "expect": ["rejected", "seq_stale"],
                },
                {"seq": 4, "op": "step", "body": {"x": 3}, "ack": "stale", "expect": ["rejected", "ack_mismatch"]},
                {"seq": 4, "op": "step", "body": {"x": 3}, "ack": "last", "expect": ["ok", None]},
            ],
        },
        {
            "name": "a declined request keeps its answer when the application would now accept it",
            "steps": [
                open_step,
                {"seq": 1, "op": "flaky", "body": {"n": 1}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {"repeat": 1, "expect": ["declined", "body_invalid"]},
                {"seq": 2, "op": "flaky", "body": {"n": 2}, "ack": "last", "expect": ["ok", None]},
                {"repeat": 1, "expect": ["rejected", "seq_stale"]},
            ],
        },
        {
            "name": "open rules",
            "steps": [
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "ncp": 3,
                    "drop": ["op", "ack", "body"],
                    "extra": {"later": [1]},
                    "expect": ["rejected", "wrong_protocol"],
                },
                {"seq": 0, "op": "step", "body": {}, "ack": "none", "expect": ["rejected", "not_open"]},
                {"seq": 1, "op": "step", "body": {}, "ack": "other", "expect": ["ended", "session_expired"]},
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"contract": "0" * 64, "bound": F.HANDSHAKE_BOUND},
                    "expect": ["rejected", "contract_mismatch"],
                },
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"application": "other", "bound": F.HANDSHAKE_BOUND},
                    "expect": ["rejected", "contract_mismatch"],
                },
                {"seq": 0, "op": "open", "ack": "none", "open": {"bound": 1000}, "expect": ["rejected", "bound_unacceptable"]},
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"bound": F.MAX_BOUND + 1},
                    "expect": ["rejected", "bound_unacceptable"],
                },
                {"seq": 0, "op": "open", "ack": "none", "open": {"omit": "bound"}, "expect": ["rejected", "body_invalid"]},
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"bound": F.HANDSHAKE_BOUND, "extra": {"later": 1}},
                    "expect": ["rejected", "body_invalid"],
                },
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"bound": F.HANDSHAKE_BOUND, "run": "r" * 257},
                    "expect": ["rejected", "body_invalid"],
                },
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"bound": F.HANDSHAKE_BOUND, "features": {"Later": {}}},
                    "expect": ["rejected", "body_invalid"],
                },
                {
                    "seq": 0,
                    "op": "open",
                    "ack": "none",
                    "open": {"bound": F.MAX_BOUND, "run": "r" * 256, "features": {"later.feature": {"x": 1}}},
                    "expect": ["ok", None],
                    "open_bound": F.HANDSHAKE_BOUND,
                    "open_features": {},
                },
                {"repeat": 11, "expect": ["ok", None]},
                {
                    "seq": 1,
                    "op": "step",
                    "body": {},
                    "ack": "last",
                    "session": "other",
                    "expect": ["rejected", "wrong_session"],
                },
                {"seq": 1, "op": "step", "body": {}, "ack": "last", "ncp": 3, "expect": ["rejected", "wrong_protocol"]},
                {
                    "seq": 1,
                    "op": "step",
                    "body": {},
                    "ack": "last",
                    "ncp": 3,
                    "drop": ["op", "ack"],
                    "extra": {"later": [1]},
                    "expect": ["rejected", "wrong_protocol"],
                },
            ],
        },
        {
            "name": "owner failure ends the session",
            "steps": [
                open_step,
                {"seq": 1, "op": "fail", "body": {}, "ack": "last", "expect": ["ended", "owner_failure"]},
                {"repeat": 1, "expect": ["ended", "owner_failure"]},
                {"seq": 2, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "session_ended"]},
            ],
        },
        {
            "name": "result too large ends the session",
            "steps": [
                open_step,
                {
                    "seq": 1,
                    "op": "big",
                    "body": {"size": F.HANDSHAKE_BOUND},
                    "ack": "last",
                    "expect": ["ended", "result_too_large"],
                    "body_has": ["size", "bound"],
                },
                {"seq": 2, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "session_ended"]},
            ],
        },
        {
            "name": "the request schema of the contract",
            "steps": [
                open_step,
                {"seq": 1, "op": "typed", "body": {"n": 3}, "ack": "last", "expect": ["ok", None]},
                {"seq": 2, "op": "typed", "body": {"n": 10}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {"seq": 3, "op": "typed", "body": {"n": 3.0}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {"seq": 4, "op": "typed", "body": {}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {"seq": 5, "op": "typed", "body": {"n": 1, "m": 1}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {"seq": 6, "op": "typed", "body": {"n": 1, "v": [1.0]}, "ack": "last", "expect": ["declined", "body_invalid"]},
                {
                    "seq": 7,
                    "op": "typed",
                    "body": {"n": 1, "v": {"array": "f64", "values": [1.0, 2.0]}},
                    "ack": "last",
                    "expect": ["ok", None],
                },
                {
                    "seq": 8,
                    "op": "typed",
                    "body": {"n": 1, "v": {"array": "f32", "values": [1.0]}},
                    "ack": "last",
                    "expect": ["declined", "body_invalid"],
                },
            ],
        },
        {
            "name": "a stopping owner admits nothing new",
            "api": ["stop"],
            "steps": [
                open_step,
                {"seq": 1, "op": "step", "body": {"x": 1}, "ack": "last", "expect": ["ok", None]},
                {"stop": True},
                {"repeat": 1, "expect": ["ok", None]},
                {"seq": 2, "op": "step", "body": {"x": 2}, "ack": "last", "expect": ["ended", "shutdown"]},
                {"repeat": 4, "expect": ["ended", "shutdown"]},
                {"owner": "stopping"},
                {"seq": 0, "op": "open", "ack": "none", "open": {"bound": F.HANDSHAKE_BOUND}, "expect": ["rejected", "refused"]},
            ],
        },
    ]


# Client scenarios (section 7.6). Steps:
#   {"do": "open" | "call" | "close" | "ping", "op": ..., "body": ...}  the client makes a request
#        "expect": "sent" (a frame) or "usage" (refused before sending)
#   {"reply": {"outcome", "code", "body"}, "to": "own" | "other_seq" | "other_request" |
#        "other_session" | "nameless" | "nameless_bound" | "garbage", "expect": verdict}
# "nameless" sets session, seq, and request to null; "nameless_bound" also sets the body to the
# client's session and its acknowledgement, as an owner's nameless response bound to its chain.
#   {"timeout": true, "expect": verdict}   {"closed": true, "expect": verdict}
# A verdict: {"kind": "ok" | "declined" | "rejected" | "ended" | "ignored" | "resend",
# "code", "executed"} and, after it, the state {"seq", "opened", "ended"}.
def clients() -> list[dict]:
    open_ok = {"outcome": "ok", "code": None, "body": {"bound": F.HANDSHAKE_BOUND, "nonce": NONCE, "features": {}}}

    def state(seq: int, opened: bool = True, ended: bool = False) -> dict:
        return {"seq": seq, "opened": opened, "ended": ended}

    opened = [
        {"do": "open", "expect": "sent"},
        {"reply": open_ok, "to": "own", "expect": {"kind": "ok"}, "state": state(0)},
    ]
    return [
        {
            "name": "ok and declined both advance",
            "lossy": False,
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent", "request": {"seq": 1, "ack": "last"}},
                {"reply": {"outcome": "ok", "code": None, "body": {"r": 1}}, "to": "own", "expect": {"kind": "ok"},
                 "state": state(1)},
                {"do": "call", "op": "step", "body": {}, "expect": "sent", "request": {"seq": 2, "ack": "last"}},
                {"reply": {"outcome": "declined", "code": "body_invalid", "body": {"detail": "no"}}, "to": "own",
                 "expect": {"kind": "declined", "code": "body_invalid", "executed": "no"}, "state": state(2)},
                {"do": "call", "op": "step", "body": {}, "expect": "sent", "request": {"seq": 3, "ack": "last"}},
                {"reply": {"outcome": "declined", "code": "later_reason", "body": {}}, "to": "own",
                 "expect": {"kind": "declined", "code": "later_reason", "executed": "no"}, "state": state(3)},
            ],
        },
        {
            # Rule 7.6.4: the owner lost the session, and a delayed copy of `open` opened it again.
            # An earlier copy of the request may have executed in the lost opening.
            "name": "a rejection of a request other than open ends the session, possibly executed",
            "lossy": True,
            "cases": [["ack_mismatch"], ["seq_gap"], ["seq_stale"], ["later_reason"]],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent", "request": {"seq": 1, "ack": "last"}},
                {"reply": {"outcome": "rejected", "code": "$code", "body": {}}, "to": "own",
                 "expect": {"kind": "ended", "code": "$code", "executed": "unknown"}, "state": state(0, ended=True)},
                {"do": "call", "op": "step", "body": {}, "expect": "usage"},
            ],
        },
        {
            "name": "ended codes and what executed",
            "lossy": False,
            "cases": [
                ["owner_failure", "unknown"],
                ["session_expired", "unknown"],
                ["result_too_large", "yes"],
                ["shutdown", "no"],
                ["bad_frame", "no"],
                ["later_end", "unknown"],
            ],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ended", "code": "$code", "body": {}}, "to": "own",
                 "expect": {"kind": "ended", "code": "$code", "executed": "$executed"}, "state": state(0, ended=True)},
                {"do": "call", "op": "step", "body": {}, "expect": "usage"},
            ],
        },
        {
            # Rule 7.6.2: a nameless frame says "not executed" only when it is bound to the chain
            # of the request; it can be replayed from another connection, also under a key.
            "name": "a nameless response that is not bound to the chain: possibly executed",
            "lossy": False,
            "cases": [["bad_frame", "unknown"], ["shutdown", "unknown"], ["result_too_large", "unknown"],
                      ["later_end", "unknown"]],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ended", "code": "$code", "body": {}}, "to": "nameless",
                 "expect": {"kind": "ended", "code": "$code", "executed": "$executed"}, "state": state(0, ended=True)},
            ],
        },
        {
            "name": "a nameless response bound to the chain of the request",
            "lossy": False,
            "cases": [["bad_frame", "no"], ["shutdown", "no"], ["result_too_large", "unknown"],
                      ["later_end", "unknown"]],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ended", "code": "$code", "body": {}}, "to": "nameless_bound",
                 "expect": {"kind": "ended", "code": "$code", "executed": "$executed"}, "state": state(0, ended=True)},
            ],
        },
        {
            "name": "a nameless response on a lossy binding is ignored",
            "lossy": True,
            "cases": [["bad_frame"], ["shutdown"]],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ended", "code": "$code", "body": {}}, "to": "nameless_bound",
                 "expect": {"kind": "ignored"}, "state": state(0)},
                {"reply": {"outcome": "ok", "code": None, "body": {}}, "to": "own", "expect": {"kind": "ok"},
                 "state": state(1)},
            ],
        },
        {
            "name": "a frame that does not belong to the request, on a byte stream",
            "lossy": False,
            "cases": [["other_seq"], ["other_request"], ["other_session"]],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ok", "code": None, "body": {}}, "to": "$code",
                 "expect": {"kind": "ended", "code": "local.protocol", "executed": "unknown"},
                 "state": state(0, ended=True)},
            ],
        },
        {
            "name": "a frame that does not belong to the request, on a lossy binding",
            "lossy": True,
            "cases": [["other_seq"], ["other_request"], ["other_session"], ["garbage"]],
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ok", "code": None, "body": {}}, "to": "$code", "expect": {"kind": "ignored"},
                 "state": state(0)},
                {"reply": {"outcome": "ok", "code": None, "body": {}}, "to": "own", "expect": {"kind": "ok"},
                 "state": state(1)},
            ],
        },
        {
            "name": "a bad frame on a byte stream",
            "lossy": False,
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"reply": {"outcome": "ok", "code": None, "body": {}}, "to": "garbage",
                 "expect": {"kind": "ended", "code": "local.bad_frame", "executed": "unknown"},
                 "state": state(0, ended=True)},
            ],
        },
        {
            "name": "time limits",
            "lossy": True,
            "retries": 2,
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"timeout": True, "expect": {"kind": "resend"}, "state": state(0)},
                {"timeout": True, "expect": {"kind": "resend"}, "state": state(0)},
                {"timeout": True, "expect": {"kind": "ended", "code": "local.timeout", "executed": "unknown"},
                 "state": state(0, ended=True)},
            ],
        },
        {
            "name": "a time limit on a byte stream",
            "lossy": False,
            "retries": 3,
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"timeout": True, "expect": {"kind": "ended", "code": "local.timeout", "executed": "unknown"},
                 "state": state(0, ended=True)},
            ],
        },
        {
            "name": "the binding closes",
            "lossy": False,
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"closed": True, "expect": {"kind": "ended", "code": "local.closed", "executed": "unknown"},
                 "state": state(0, ended=True)},
            ],
        },
        {
            "name": "open responses that break section 7.1",
            "lossy": False,
            "cases": [["nonce"], ["no_nonce"], ["bound"], ["features"]],
            "steps": [
                {"do": "open", "expect": "sent"},
                {"reply": {"outcome": "ok", "code": None, "body": "$code"}, "to": "own",
                 "expect": {"kind": "ended", "code": "local.protocol", "executed": "unknown"},
                 "state": state(0, opened=False, ended=True)},
            ],
            "bodies": {
                "nonce": {"bound": F.HANDSHAKE_BOUND, "nonce": "XYZ", "features": {}},
                # an owner of an earlier revision, without a nonce
                "no_nonce": {"bound": F.HANDSHAKE_BOUND, "features": {}},
                "bound": {"bound": F.MAX_BOUND, "nonce": NONCE, "features": {}},
                "features": {"bound": F.HANDSHAKE_BOUND, "nonce": NONCE, "features": []},
            },
        },
        {
            "name": "a rejected open leaves no session; the same open can follow",
            "lossy": False,
            "steps": [
                {"do": "open", "expect": "sent"},
                {"reply": {"outcome": "rejected", "code": "refused", "body": {}}, "to": "own",
                 "expect": {"kind": "rejected", "code": "refused"}, "state": state(0, opened=False)},
                {"do": "call", "op": "step", "body": {}, "expect": "usage"},
                {"do": "open", "expect": "sent", "same_as_first": True},
                {"reply": open_ok, "to": "own", "expect": {"kind": "ok"}, "state": state(0)},
            ],
        },
        {
            "name": "close ends the session",
            "lossy": False,
            "steps": opened
            + [
                {"do": "close", "expect": "sent", "request": {"seq": 1, "ack": "last"}},
                {"reply": {"outcome": "ok", "code": None, "body": {}}, "to": "own", "expect": {"kind": "ok"},
                 "state": state(1, ended=True)},
                {"do": "call", "op": "step", "body": {}, "expect": "usage"},
            ],
        },
        {
            "name": "one request at a time",
            "lossy": False,
            "steps": opened
            + [
                {"do": "call", "op": "step", "body": {}, "expect": "sent"},
                {"do": "call", "op": "step", "body": {}, "expect": "usage"},
                {"do": "call", "op": "Bad", "body": {}, "expect": "usage"},
            ],
        },
    ]


def streams() -> list[dict]:
    def chain(name: str, count: int, end: bool = False) -> list[bytes]:
        sent, prev = [], None
        for seq in range(1, count + 1):
            body = {"i": seq, **({"ncp.end": {}} if end and seq == count else {})}
            frame = F.encode(
                {"ncp": 2, "stream": name, "seq": seq, "prev": prev, "contract": CONTRACT_ID, "body": body}
            )
            prev = F.identity(frame)
            sent.append(frame)
        return sent

    a = chain("sensor/a", 5)
    b = chain("sensor/b", 3, end=True)
    other = F.encode(
        {"ncp": 2, "stream": "sensor/a", "seq": 5, "prev": F.identity(a[3]), "contract": CONTRACT_ID, "body": {"i": 0}}
    )
    forged = F.encode({"ncp": 2, "stream": "sensor/a", "seq": 6, "prev": "0" * 64, "contract": CONTRACT_ID, "body": {}})
    after = F.encode(
        {"ncp": 2, "stream": "sensor/b", "seq": 4, "prev": F.identity(b[2]), "contract": CONTRACT_ID, "body": {}}
    )
    foreign = F.encode({"ncp": 2, "stream": "x", "seq": 1, "prev": None, "contract": "0" * 64, "body": {}})
    malformed = F.encode({"ncp": 2, "stream": "x", "seq": 2, "prev": None, "contract": CONTRACT_ID, "body": {}})
    late = chain("sensor/late", 4)
    order = [
        (a[0], "accepted", 0, False),
        (a[0], "repeat", 0, False),
        (a[3], "accepted", 2, False),
        (a[1], "repeat", 0, False),
        (other, "accepted", 0, False),
        (a[4], "conflict", 0, False),
        (forged, "broken_chain", 0, False),
        (late[2], "joined", 0, False),
        (late[3], "accepted", 0, False),
        (b[0], "accepted", 0, False),
        (b[1], "accepted", 0, False),
        (b[2], "accepted", 0, True),
        (b[2], "repeat", 0, False),
        (after, "conflict", 0, False),
        (foreign, "unknown_contract", 0, False),
        (malformed, "bad_frame", 0, False),
        (b"junk", "bad_frame", 0, False),
    ]
    return [{"frame": frame.hex(), "status": status, "lost": lost, "end": end} for frame, status, lost, end in order]


class _VectorHandler:
    def __init__(self) -> None:
        self.validated = 0

    def validate(self, request: ncp.Request) -> None:
        if request.op == "step" and isinstance(request.body, dict) and request.body.get("invalid") is True:
            raise ncp.Declined("invalid")

    def execute(self, request: ncp.Request) -> object:
        return {"echo": request.body}


class _Direct:
    """A lossless channel to an owner in this process."""

    lossy = False

    def __init__(self, owner: ncp.Owner, tap: T.Tap) -> None:
        self.owner, self.tap, self.inbox = owner, tap, []

    def send(self, frame: bytes) -> None:
        self.tap.record(T.SENT, frame)
        self.inbox.append(self.owner.handle(frame))

    def receive(self, bound: int, timeout: float | None) -> bytes:
        frame = self.inbox.pop(0)
        self.tap.record(T.RECEIVED, frame)
        return frame


def transcripts() -> list[dict]:
    contract = ncp.Contract.from_bytes(CONTRACT)
    directory = tempfile.mkdtemp(prefix="ncp-vectors-")

    def record(name: str, key: bytes | None = None) -> bytes:
        path = os.path.join(directory, name)
        ticks = iter(range(0, 10**9, 1000))
        tap = T.Tap(path, recorder="conformance", key=key, clock=lambda: next(ticks), started="2026-11-13T00:00:00.000000000Z")
        owner = ncp.Owner(contract, _VectorHandler(), max_bound=F.HANDSHAKE_BOUND, nonce=lambda: NONCE, key=key)
        client = ncp.Client(_Direct(owner, tap), contract, bound=F.HANDSHAKE_BOUND, session=SESSION, key=key)
        client.open()
        client.call("step", {"x": 1})
        try:
            client.call("step", {"invalid": True})
        except ncp.Declined:
            pass
        client.call("step", {"x": 2})
        client.close()
        tap.close()
        with open(path, "rb") as handle:
            return handle.read()

    original = record("t.ncpt")
    keyed = record("k.ncpt", KEY)
    parsed = T.read(os.path.join(directory, "t.ncpt"))
    header_end = 8 + 4 + struct.unpack(">I", original[8:12])[0]

    def rewrite(records: list[T.Record], end: bytes | None = b"keep") -> bytes:
        data = bytearray(original[:header_end])
        for item in records:
            data += T.RECORD.pack(item.kind, item.time_ns, len(item.frame)) + item.frame + (item.chain or b"")
        if end == b"keep":
            data += original[-(T.RECORD.size + 32) :]
        return bytes(data)

    def resealed(records: list[T.Record]) -> bytes:
        """The records with a chain recomputed from the start: a consistent file without a key."""
        data = bytearray(original[:header_end])
        chain = hashlib.sha256(original[:header_end]).digest()
        for item in records:
            head = T.RECORD.pack(item.kind, item.time_ns, len(item.frame))
            chain = hashlib.sha256(chain + head + item.frame[-32:]).digest()
            data += head + item.frame + chain
        head = T.RECORD.pack(T.END, records[-1].time_ns + 1, 0)
        chain = hashlib.sha256(chain + head + struct.pack(">Q", len(records))).digest()
        return bytes(data + head + chain)

    rec = parsed.records
    declined_at = next(
        i for i, item in enumerate(rec) if F.decode(item.frame, F.MAX_BOUND).message.get("outcome") == "declined"
    )
    flipped = [T.Record(3 - item.kind, item.time_ns, item.frame, item.chain) for item in rec]
    one_flipped = [T.Record(3 - item.kind if i == declined_at else item.kind, item.time_ns, item.frame, item.chain)
                   for i, item in enumerate(rec)]
    late_time = [T.Record(item.kind, item.time_ns + (5 if i == 2 else 0), item.frame, item.chain) for i, item in enumerate(rec)]
    v1 = bytearray(T.MAGIC_V1)
    for item in rec:
        v1 += T.RECORD.pack(item.kind, item.time_ns, len(item.frame)) + item.frame
    session = {"role": "client", "requests": 5, "declined": 1, "complete": True}

    def message_of(item: T.Record) -> dict:
        return F.decode(item.frame, F.MAX_BOUND).message

    # A second, different ok response to the first step, received after the first one.
    first_ok = message_of(rec[3])
    assert first_ok["outcome"] == "ok" and message_of(rec[2])["op"] == "step"
    other_ok = F.encode({**first_ok, "body": {"x": 99}})
    two_answers = rec[:4] + [T.Record(T.RECEIVED, rec[3].time_ns, other_ok)] + rec[4:]

    # An owner's transcript (every direction flipped) with a request of seq 5 after the open.
    gap_request = F.encode({"ncp": 2, "session": SESSION, "seq": 5, "op": "step", "ack": F.identity(rec[1].frame),
                            "body": {}})

    def gap_answer(outcome: str, code: str | None) -> bytes:
        return F.encode({"ncp": 2, "session": SESSION, "seq": 5, "request": F.identity(gap_request),
                         "outcome": outcome, "code": code, "body": {}})

    def owner_with(answer: bytes) -> list[T.Record]:
        moment = flipped[1].time_ns
        return flipped[:2] + [T.Record(T.RECEIVED, moment, gap_request), T.Record(T.SENT, moment, answer)] + flipped[2:]

    owner_session = {**session, "role": "owner"}
    short = rec[:2] + [T.Record(T.RECEIVED, rec[1].time_ns, b"0123456789")] + rec[2:]

    def expect(ok: bool, *, closed: bool = True, truncated: bool = False, chain_ok: bool | None = True,
               problems: bool | None = None, sessions: list[dict] | None = None, version: int = 2) -> dict:
        return {
            "ok": ok,
            "version": version,
            "closed": closed,
            "truncated": truncated,
            "chain_ok": chain_ok,
            "sessions": sessions if sessions is not None else [{**session, "problems": False}],
        }

    cases = [
        ("a complete session", original, None, expect(True)),
        ("with the key", keyed, KEY, expect(True)),
        ("keyed, read without the key", keyed, None, expect(False, chain_ok=None)),
        ("the declined exchange removed, chain not recomputed", rewrite(rec[:declined_at - 1] + rec[declined_at + 1 :]),
         None, expect(False, chain_ok=False, sessions=[{**session, "requests": 4, "declined": 0, "problems": True}])),
        ("the declined exchange removed, chain recomputed", resealed(rec[:declined_at - 1] + rec[declined_at + 1 :]),
         None, expect(False, sessions=[{**session, "requests": 4, "declined": 0, "problems": True}])),
        ("the last exchange and the end record removed", rewrite(rec[:-2], end=None), None,
         expect(False, closed=False, sessions=[{**session, "requests": 4, "complete": False, "problems": False}])),
        ("every direction flipped", rewrite(flipped), None,
         expect(False, chain_ok=False, sessions=[{**session, "role": "owner", "problems": False}])),
        # Without a key, an editor can make any consistent file: this one reads as the owner's.
        ("every direction flipped, chain recomputed", resealed(flipped), None,
         expect(True, sessions=[{**session, "role": "owner", "problems": False}])),
        ("one response's direction flipped, chain recomputed", resealed(one_flipped), None,
         expect(False, sessions=[{**session, "problems": True}])),
        ("a time changed", rewrite(late_time), None, expect(False, chain_ok=False)),
        ("the last record torn", original[: header_end + 10] , None,
         expect(False, closed=False, truncated=True, sessions=[])),
        ("cut inside the end record", original[:-10], None,
         expect(False, closed=False, truncated=True, sessions=[{**session, "problems": False}])),
        ("version 1", bytes(v1), None, expect(True, closed=False, chain_ok=None, version=1)),
        ("version 1, verified with a key", bytes(v1), KEY, expect(False, closed=False, chain_ok=None, version=1)),
        ("without a key, verified with a key", original, KEY, expect(False)),
        ("two different ok responses to one request, chain recomputed", resealed(two_answers), None,
         expect(False, sessions=[{**session, "problems": True}])),
        ("an owner rejects a request with a gap, chain recomputed", resealed(owner_with(gap_answer("rejected", "seq_gap"))),
         None, expect(True, sessions=[{**owner_session, "problems": False}])),
        ("an owner admits a request with a gap, chain recomputed", resealed(owner_with(gap_answer("ok", None))),
         None, expect(False, sessions=[{**owner_session, "requests": 6, "problems": True}])),
        ("a received record shorter than a digest, chain recomputed", resealed(short), None, expect(False)),
    ]
    out = []
    for name, data, key, expected in cases:
        path = os.path.join(directory, "case.ncpt")
        with open(path, "wb") as handle:
            handle.write(data)
        report = T.verify(path, key=key)
        observed = summary(report)
        if observed != expected:
            raise AssertionError(f"transcript vector {name!r}: the Python verifier gives {observed}, not {expected}")
        out.append({"name": name, "file": data.hex(), "key": None if key is None else key.hex(), "expect": expected})
    return out


def summary(report: T.Report) -> dict:
    """The part of a verification that every verifier must agree on."""
    return {
        "ok": report.ok,
        "version": report.version,
        "closed": report.closed,
        "truncated": report.truncated_at is not None,
        "chain_ok": report.chain_ok,
        "sessions": [
            {
                "role": s.role,
                "requests": s.requests,
                "declined": s.declined,
                "complete": s.complete,
                "problems": bool(s.problems),
            }
            for s in report.sessions.values()
        ],
    }


def contracts() -> list[dict]:
    base = {"ncp_contract": 1, "application": "a", "version": "1", "operations": {"step": {}}, "streams": {}}

    def doc(value: object) -> str:
        return json.dumps(value, separators=(",", ":"))

    cases = [
        ("a contract", doc(base), True),
        ("other top-level members", doc({**base, "description": "x"}), True),
        ("ncp_contract true", doc(base).replace('"ncp_contract":1', '"ncp_contract":true'), False),
        ("ncp_contract 1.0", doc(base).replace('"ncp_contract":1', '"ncp_contract":1.0'), False),
        ("ncp_contract 2", doc({**base, "ncp_contract": 2}), False),
        ("no version", doc({k: v for k, v in base.items() if k != "version"}), False),
        ("empty application", doc({**base, "application": ""}), False),
        ("operation open", doc({**base, "operations": {"open": {}}}), False),
        ("operation close", doc({**base, "operations": {"close": {}}}), False),
        ("operation ncp.x", doc({**base, "operations": {"ncp.x": {}}}), False),
        ("operation Open!", doc({**base, "operations": {"Open!": {}}}), False),
        ("operation that is not an object", doc({**base, "operations": {"step": 1}}), False),
        ("stream type Bad", doc({**base, "streams": {"Bad": {}}}), False),
        ("duplicate member", '{"ncp_contract":1,"ncp_contract":1,"application":"a","version":"1","operations":{},"streams":{}}', False),
        ("a request schema", doc({**base, "operations": {"step": {"ncp.schema": {"request": {"type": "object"}}}}}), True),
        ("an unknown schema keyword", doc({**base, "operations": {"step": {"ncp.schema": {"request": {"pattern": "x"}}}}}), False),
        ("an unknown schema part", doc({**base, "operations": {"step": {"ncp.schema": {"reply": {}}}}}), False),
        ("a stream body schema", doc({**base, "streams": {"s": {"ncp.schema": {"body": {"type": "object"}}}}}), True),
        ("a type that is not known", doc({**base, "operations": {"step": {"ncp.schema": {"request": {"type": "float"}}}}}), False),
        ("an array schema with a bad dtype",
         doc({**base, "operations": {"step": {"ncp.schema": {"request": {"ncp.array": {"dtype": "c64", "shape": []}}}}}}), False),
        ("a byte order mark", "\ufeff" + doc(base), False),
    ]
    out = []
    for name, text, ok in cases:
        try:
            ncp.Contract.from_bytes(text.encode("utf-8"))
            accepted = True
        except ValueError:
            accepted = False
        if accepted != ok:
            raise AssertionError(f"contract vector {name!r}: Python gives {accepted}")
        out.append({"name": name, "document": text, "valid": ok})
    return out


def schemas() -> list[dict]:
    """Each case: a schema, a frame whose message is {"value": V}, and whether V matches."""
    cases = [
        ({"type": "integer"}, 1, True),
        ({"type": "integer"}, 1.0, False),
        ({"type": "number"}, 1, True),
        ({"type": "number"}, 1.5, True),
        ({"type": "boolean"}, 0, False),
        ({"type": ["string", "null"]}, None, True),
        ({"type": "object"}, [], False),
        ({"enum": [1, "a"]}, 1.0, False),
        ({"enum": [1, "a"]}, "a", True),
        ({"const": {"a": [1, 2]}}, {"a": [1, 2]}, True),
        ({"const": {"a": [1, 2]}}, {"a": [2, 1]}, False),
        ({"minimum": 0, "maximum": 9}, 9, True),
        ({"minimum": 0, "maximum": 9}, 9.5, False),
        ({"exclusiveMinimum": 0}, 0, False),
        ({"exclusiveMaximum": 1.5}, 1.4, True),
        ({"minimum": 0}, "a string", True),
        ({"minLength": 2, "maxLength": 3}, "😀😀", True),
        ({"maxLength": 1}, "ab", False),
        ({"items": {"type": "integer"}, "minItems": 1}, [1, 2], True),
        ({"items": {"type": "integer"}}, [1, "2"], False),
        ({"maxItems": 1}, [1, 2], False),
        ({"required": ["a"], "properties": {"a": {"type": "string"}}}, {"a": "x"}, True),
        ({"required": ["a"]}, {"b": 1}, False),
        ({"properties": {"a": {"type": "string"}}, "additionalProperties": False}, {"a": "x", "b": 1}, False),
        ({"additionalProperties": {"type": "integer"}}, {"a": 1, "b": 2}, True),
        ({"additionalProperties": {"type": "integer"}}, {"a": 1, "b": "2"}, False),
        ({"ncp.array": {"dtype": "f64", "shape": [None, 3]}}, F.Array("f64", [2, 3], bytes(48)), True),
        ({"ncp.array": {"dtype": ["u8", "i8"], "shape": [2]}}, F.Array("i8", [2], b"ab"), True),
        ({"ncp.array": {"dtype": "f64", "shape": [None, 3]}}, F.Array("f64", [3, 2], bytes(48)), False),
        ({"ncp.array": {"dtype": "f64", "shape": [6]}}, F.Array("f32", [6], bytes(24)), False),
        ({"ncp.array": {"dtype": "f64", "shape": [1]}}, [1.0], False),
        ({"type": "object"}, F.Array("u8", [1], b"x"), True),
        ({"type": "object", "required": ["x"], "additionalProperties": False}, F.Array("u8", [1], b"x"), True),
        ({"const": {"ncp.array": {"dtype": "u8", "shape": [1], "att": 0}}}, F.Array("u8", [1], b"x"), False),
        ({"description": "free text", "title": "t"}, 5, True),
    ]
    out = []
    from ncp import contract as K

    for schema, value, ok in cases:
        K.compile_schema(schema)
        frame = F.encode({"value": value})
        decoded = F.decode(frame, F.MAX_BOUND)
        result = K.check(schema, decoded.message["value"]) is None
        if result != ok:
            raise AssertionError(f"schema vector {schema}: Python gives {result}")
        out.append({"schema": schema, "frame": frame.hex(), "valid": ok})
    return out


def main() -> None:
    outputs = sys.argv[1:] or [os.path.join(HERE, "vectors.json"), os.path.join(ROOT, "python", "ncp", "vectors.json")]
    vectors = {
        "spec": "spec/NCP-2.md",
        "revision": REVISION,
        "contract": CONTRACT.decode(),
        "contract_identity": CONTRACT_ID,
        "session": SESSION,
        "nonce": NONCE,
        "key": KEY.hex(),
        "handler": HANDLER,
        "frames": frames(),
        "messages": messages(),
        "auth": auth(),
        "scenarios": scenarios(),
        "clients": clients(),
        "streams": streams(),
        "transcripts": transcripts(),
        "contracts": contracts(),
        "schemas": schemas(),
    }
    text = json.dumps(vectors, indent=1, ensure_ascii=False) + "\n"
    for output in outputs:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text)
    counts = ", ".join(f"{len(vectors[k])} {k}" for k in ("frames", "messages", "auth", "scenarios", "clients",
                                                          "streams", "transcripts", "contracts", "schemas"))
    print(f"wrote {', '.join(outputs)}: {counts}")


if __name__ == "__main__":
    main()
