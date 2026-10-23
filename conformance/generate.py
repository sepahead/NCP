#!/usr/bin/env python3
"""Generate conformance/vectors.json from the rules of spec/NCP-2.md.

The expected results come from the specification, written out below case by case. Valid frames
are encoded with the Python SDK; every implementation must decode them to the stated message
and identity, so the encoder is checked too. Invalid frames are built byte by byte.

Usage: generate.py [OUTPUT]   (default: vectors.json next to this file)
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
from ncp import frame as F  # noqa: E402

SESSION = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b"
CONTRACT = (b'{"ncp_contract":1,"application":"conformance","version":"1",'
            b'"operations":{"step":{},"fail":{},"big":{}},"streams":{"sensor":{}}}')


def raw(text: bytes, attachments: bytes = b"", pad: bool = True) -> bytes:
    payload = text + (b" " * ((8 - (12 + len(text)) % 8) % 8) if pad else b"")
    body = struct.pack(">4sII", F.MAGIC, len(payload), len(attachments)) + payload + attachments
    return body + hashlib.sha256(body).digest()


def valid(name: str, message: dict, arrays_note: str = "") -> dict:
    frame = F.encode(message)
    decoded = F.decode(frame, F.MAX_BOUND)

    def plain(value):
        if isinstance(value, F.Array):
            index = next(i for i, item in enumerate(decoded.arrays) if item is value)  # not by equal content
            return {"ncp.array": {"dtype": value.dtype, "shape": list(value.shape), "att": index}}
        if isinstance(value, dict):
            return {k: plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [plain(v) for v in value]
        return value

    return {"name": name, "frame": frame.hex(), "bound": F.HANDSHAKE_BOUND, "valid": True,
            "message": plain(decoded.message), "identity": decoded.identity,
            "arrays": [bytes(item.data).hex() for item in decoded.arrays], "note": arrays_note}


def invalid(name: str, frame: bytes, bound: int = F.HANDSHAKE_BOUND) -> dict:
    return {"name": name, "frame": frame.hex(), "bound": bound, "valid": False}


def frames() -> list[dict]:
    cases = [
        valid("minimal object", {}),
        valid("request without attachments",
              {"ncp": 2, "session": SESSION, "seq": 1, "op": "step", "ack": "a" * 64, "body": {"x": 1.5, "s": "é∑😀"}}),
        valid("numbers", {"i": 9007199254740991, "n": -9007199254740991, "f": 1e300, "g": -2.5e-308, "z": 0}),
        valid("unicode escapes are decoded", json.loads('{"a":"\\u00e9\\ud83d\\ude00"}')),
        valid("arrays of every dtype", {"v": [F.Array(d, [2], bytes(range(s * 2))) for d, (_, s, _) in F.DTYPES.items()]}),
        valid("zero-length and empty-shape arrays",
              {"e": F.Array("f64", [0], b""), "s": F.Array("i32", [], struct.pack("<i", -7))}),
        valid("nested array reference", {"a": [{"b": {"c": F.Array("u8", [3], b"xyz")}}]}),
        valid("one empty array: att [0] and A = 0", {"e": F.Array("f64", [0], b"")}),
        valid("empty attachment after an unaligned one", {"a": F.Array("u8", [1], b"a"), "b": F.Array("u8", [0], b"")}),
        valid("negative zero float", {"a": -0.0}),
        # JSON text "\\ud83d/": an escaped backslash, then the letters ud83d. No surrogate.
        valid("escaped backslash before u and hex digits", {"a": "\\ud83d/", "\\udc00": 1}),
    ]
    cases += [
        {"name": "escaped backslash, then an escaped solidus", "frame": raw(b'{"a":"\\\\ud83d\\/"}').hex(),
         "bound": F.HANDSHAKE_BOUND, "valid": True, "message": {"a": "\\ud83d/"},
         "identity": hashlib.sha256(raw(b'{"a":"\\\\ud83d\\/"}')[:-32]).hexdigest(), "arrays": [], "note": ""},
    ]
    good = F.encode({"a": 1})

    def array_at(lists: int) -> bytes:
        # The object is level 1, the lists levels 2 to lists + 1, then the array reference,
        # its spec, and its shape list: the shape list is at level lists + 4.
        return (b'{"a":' + b"[" * lists + b'{"ncp.array":{"dtype":"u8","shape":[1],"att":0}}' + b"]" * lists
                + b',"att":[1]}')

    cases.append({"name": "array shape list at level 64", "frame": raw(array_at(60), b"x").hex(),
                  "bound": F.HANDSHAKE_BOUND, "valid": True,
                  "message": json.loads(array_at(60)),
                  "identity": hashlib.sha256(raw(array_at(60), b"x")[:-32]).hexdigest(),
                  "arrays": [b"x".hex()], "note": ""})
    nested_63 = b'{"a":' + b"[" * 63 + b"]" * 63 + b"}"
    nested_64 = b'{"a":' + b"[" * 64 + b"]" * 64 + b"}"
    cases += [
        {"name": "63 nested arrays inside the object (64 levels)", "frame": raw(nested_63).hex(),
         "bound": F.HANDSHAKE_BOUND, "valid": True, "message": json.loads(nested_63),
         "identity": hashlib.sha256(raw(nested_63)[:-32]).hexdigest(), "arrays": [], "note": ""},
        invalid("64 nested arrays inside the object (65 levels)", raw(nested_64)),
        invalid("array shape list at level 65", raw(array_at(61), b"x")),
        invalid("dtype that is a list", raw(b'{"att":[1],"v":{"ncp.array":{"dtype":["u8"],"shape":[1],"att":0}}}', b"x")),
        invalid("shape element 2^53 with a zero product",
                raw(b'{"att":[0],"v":{"ncp.array":{"dtype":"u8","shape":[9007199254740992,0],"att":0}}}')),
        invalid("digest", good[:-1] + bytes([good[-1] ^ 1])),
        invalid("magic version 1", b"NCP\x01" + good[4:]),
        invalid("json region not aligned", raw(b"{}", pad=False)),
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
        invalid("sequence number written as -0",
                raw(b'{"ncp":2,"session":"' + SESSION.encode() + b'","seq":-0,"op":"open","ack":null,"body":{}}')),
        invalid("shape product beyond 64 bits",
                raw(b'{"att":[0],"v":{"ncp.array":{"dtype":"u8","shape":[4294967296,4294967296],"att":0}}}')),
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
        invalid("array length mismatch", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u16","shape":[4],"att":0}}}', b"abcd")),
        invalid("unknown dtype", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"c64","shape":[1],"att":0}}}', b"abcd")),
        invalid("attachment used twice", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}},'
                                             b'"w":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}', b"abcd")),
        invalid("array object with another member", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0},"x":1}}', b"abcd")),
        invalid("negative shape", raw(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[-4],"att":0}}}', b"abcd")),
        invalid("nonzero padding between attachments",
                raw(b'{"att":[1,1],"v":{"ncp.array":{"dtype":"u8","shape":[1],"att":0}},'
                    b'"w":{"ncp.array":{"dtype":"u8","shape":[1],"att":1}}}', b"a\x01\x00\x00\x00\x00\x00\x00b")),
    ]
    return cases


# Owner scenarios. Each step: seq, op, body, ack ("last" = identity of the last ok or ended
# response, "stale" = the response before it, "none" = null, "other" = 64 zeros), and the
# expected (outcome, code). "repeat": index of an earlier step whose frame is sent again; its
# response must be the identical bytes when expect is not rejected.
def scenarios() -> list[dict]:
    open_step = {"seq": 0, "op": "open", "ack": "none", "open": {"bound": F.HANDSHAKE_BOUND}, "expect": ["ok", None]}
    return [
        {"name": "happy path and close", "steps": [
            open_step,
            {"seq": 1, "op": "step", "body": {"x": 1}, "ack": "last", "expect": ["ok", None]},
            {"seq": 2, "op": "step", "body": {"x": 2}, "ack": "last", "expect": ["ok", None]},
            {"seq": 3, "op": "close", "body": {}, "ack": "last", "expect": ["ok", None]},
            {"seq": 4, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "session_ended"]},
            {"repeat": 3, "expect": ["ok", None]},
        ]},
        {"name": "rejections change nothing", "steps": [
            open_step,
            {"seq": 1, "op": "step", "body": {}, "ack": "none", "expect": ["rejected", "ack_missing"]},
            {"seq": 1, "op": "step", "body": {}, "ack": "other", "expect": ["rejected", "ack_mismatch"]},
            {"seq": 2, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "seq_gap"]},
            {"seq": 1, "op": "open", "body": {}, "ack": "last", "expect": ["rejected", "already_open"]},
            {"seq": 1, "op": "missing", "body": {}, "ack": "last", "expect": ["rejected", "unknown_op"]},
            {"seq": 1, "op": "step", "body": {"invalid": True}, "ack": "last", "expect": ["rejected", "body_invalid"]},
            {"seq": 1, "op": "step", "body": {"x": 1}, "ack": "last", "expect": ["ok", None]},
            {"repeat": 7, "expect": ["ok", None]},
            {"seq": 1, "op": "step", "body": {"x": 2}, "ack": "stale", "expect": ["rejected", "seq_conflict"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"bound": F.HANDSHAKE_BOUND}, "expect": ["rejected", "seq_stale"]},
            {"seq": 2, "op": "step", "body": {"x": 3}, "ack": "stale", "expect": ["rejected", "ack_mismatch"]},
            {"seq": 2, "op": "step", "body": {"x": 3}, "ack": "last", "expect": ["ok", None]},
        ]},
        {"name": "open rules", "steps": [
            {"seq": 1, "op": "step", "body": {}, "ack": "other", "expect": ["rejected", "not_open"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"contract": "0" * 64, "bound": F.HANDSHAKE_BOUND}, "expect": ["rejected", "contract_mismatch"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"application": "other", "bound": F.HANDSHAKE_BOUND}, "expect": ["rejected", "contract_mismatch"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"bound": 1000}, "expect": ["rejected", "bound_unacceptable"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"bound": F.MAX_BOUND + 1}, "expect": ["rejected", "bound_unacceptable"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"omit": "bound"}, "expect": ["rejected", "body_invalid"]},
            {"seq": 0, "op": "open", "ack": "none", "open": {"bound": F.MAX_BOUND}, "expect": ["ok", None], "open_bound": F.HANDSHAKE_BOUND},
            {"repeat": 6, "expect": ["ok", None]},
            {"seq": 1, "op": "step", "body": {}, "ack": "last", "session": "other", "expect": ["rejected", "wrong_session"]},
            {"seq": 1, "op": "step", "body": {}, "ack": "last", "ncp": 3, "expect": ["rejected", "wrong_protocol"]},
        ]},
        {"name": "owner failure ends the session", "steps": [
            open_step,
            {"seq": 1, "op": "fail", "body": {}, "ack": "last", "expect": ["ended", "owner_failure"]},
            {"repeat": 1, "expect": ["ended", "owner_failure"]},
            {"seq": 2, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "session_ended"]},
        ]},
        {"name": "result too large ends the session", "steps": [
            open_step,
            {"seq": 1, "op": "big", "body": {"size": F.HANDSHAKE_BOUND}, "ack": "last", "expect": ["ended", "result_too_large"]},
            {"seq": 2, "op": "step", "body": {}, "ack": "last", "expect": ["rejected", "session_ended"]},
        ]},
    ]


def streams() -> list[dict]:
    contract = hashlib.sha256(CONTRACT).hexdigest()
    sent = []
    prev = None
    for seq in range(1, 6):
        frame = F.encode({"ncp": 2, "stream": "sensor/a", "seq": seq, "prev": prev, "contract": contract, "body": {"i": seq}})
        prev = F.identity(frame)
        sent.append(frame)
    forged = F.encode({"ncp": 2, "stream": "sensor/a", "seq": 6, "prev": "0" * 64, "contract": contract, "body": {}})
    foreign = F.encode({"ncp": 2, "stream": "x", "seq": 1, "prev": None, "contract": "0" * 64, "body": {}})
    malformed = F.encode({"ncp": 2, "stream": "x", "seq": 2, "prev": None, "contract": contract, "body": {}})
    order = [(sent[0], "accepted", 0), (sent[0], "repeat", 0), (sent[3], "accepted", 2), (sent[1], "repeat", 0),
             (sent[4], "accepted", 0), (forged, "broken_chain", 0), (foreign, "unknown_contract", 0),
             (malformed, "bad_frame", 0), (b"junk", "bad_frame", 0)]
    return [{"frame": frame.hex(), "status": status, "lost": lost} for frame, status, lost in order]


def main() -> None:
    output = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "vectors.json")
    vectors = {
        "spec": "spec/NCP-2.md",
        "contract": CONTRACT.decode(),
        "contract_identity": hashlib.sha256(CONTRACT).hexdigest(),
        "session": SESSION,
        "handler": {"step": "result {\"echo\": body}; body {\"invalid\": true} is rejected as body_invalid",
                    "fail": "raises: owner_failure",
                    "big": "result {\"blob\": \"z\" repeated body.size times}"},
        "frames": frames(),
        "scenarios": scenarios(),
        "streams": streams(),
    }
    with open(output, "w") as handle:
        json.dump(vectors, handle, indent=1, ensure_ascii=False)
        handle.write("\n")
    print(f"wrote {output}: {len(vectors['frames'])} frames, {len(vectors['scenarios'])} scenarios, "
          f"{len(vectors['streams'])} stream cases")


if __name__ == "__main__":
    main()
