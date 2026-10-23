#!/usr/bin/env python3
"""Differential fuzzing of frame decoders: the Python reference against another decoder.

Each case is a frame: a valid frame from a random message, a frame whose JSON text was edited
at random, or a frame whose header, attachment lengths, or padding were changed. Edited frames
get correct padding and digests, so they reach the JSON and attachment checks. Both decoders
must accept or reject each frame alike, and accepted frames must decode to the same message
(integers and floats kept apart), identity, and array bytes.

Usage: fuzz.py --decoder PATH [--cases 200000] [--seed 20261023] [--save DIR]
The decoder is a program like the Rust example `decode_corpus`: decoder CORPUS BOUND.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))
from ncp import frame as F  # noqa: E402

BOUND = F.MAX_BOUND
INTS = [0, 1, -1, 7, 2**31, -(2**31), 2**32, 2**53 - 1, -(2**53 - 1), 10**15, 123456789012345]
FLOATS = [0.0, -0.0, 0.1, -2.5, 1e300, -1e-300, 5e-324, 2.2250738585072014e-308, 1.7976931348623157e308,
          1e16, 9007199254740993.0, 0.30000000000000004, 1.5e-7]
STRINGS = ["", "a", "é", "😀", "\u0000", "\"\\/", " ", "﻿", "ncp.array", "att", "a\nb", "\u007f", "日本"]
TOKENS = ["{", "}", "[", "]", '"', ",", ":", "-", "+", ".", "e", "E", "0", "1", "9", " ", "\t", "\n", "\r",
          "true", "false", "null", "NaN", "Infinity", "-Infinity", "\\u", "\\ud83d", "\\ude00", "\\ud83d\\ude00",
          "\\u0000", '\\"', "\\\\", "\\x", "\\/", "é", "\x00", "\x1f", "-0", "-0.0", "0.0", "1e400", "1e-400",
          "9007199254740991", "9007199254740992", "-9007199254740992", "18446744073709551616", "1E2", "01",
          '"ncp.array"', '"att"', '"dtype"', '"shape"', '"u8"', '"f64"', "﻿", '"a"', '"a":1', "[[[[", "]]]]"]
RAW = [b"\xff", b"\xc0\x80", b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\xef\xbb\xbf", b"\x80", b"\xe2\x82"]


def random_value(rng: random.Random, depth: int, arrays: list[F.Array]) -> object:
    roll = rng.random()
    if depth >= 4 or roll < 0.55:
        kind = rng.randrange(7)
        if kind == 0:
            return rng.choice(INTS) if rng.random() < 0.6 else rng.randint(-(2**53 - 1), 2**53 - 1)
        if kind == 1:
            return rng.choice(FLOATS) if rng.random() < 0.6 else rng.uniform(-1e6, 1e6)
        if kind == 2:
            return rng.choice(STRINGS) + "".join(chr(rng.choice([rng.randint(32, 126), rng.randint(0xA0, 0xD7FF),
                                                                  rng.randint(0xE000, 0x10FFFF)])) for _ in range(rng.randrange(4)))
        if kind == 3:
            return rng.random() < 0.5
        if kind == 4:
            return None
        if kind == 5 and len(arrays) < 6:
            dtype = rng.choice(list(F.DTYPES))
            size = F.DTYPES[dtype][1]
            shape = [rng.randrange(4) for _ in range(rng.randrange(3))]
            count = 1
            for n in shape:
                count *= n
            item = F.Array(dtype, shape, bytes(rng.randrange(256) for _ in range(count * size)))
            arrays.append(item)
            return item
        return rng.choice(INTS)
    if roll < 0.78:
        return [random_value(rng, depth + 1, arrays) for _ in range(rng.randrange(4))]
    return {rng.choice(STRINGS) + str(i): random_value(rng, depth + 1, arrays) for i in range(rng.randrange(4))}


def wrap(text: bytes, attachments: bytes = b"") -> bytes:
    payload = text + b" " * ((8 - (12 + len(text)) % 8) % 8)
    body = struct.pack(">4sII", F.MAGIC, len(payload), len(attachments)) + payload + attachments
    return body + hashlib.sha256(body).digest()


def split(frame: bytes) -> tuple[bytes, bytes]:
    _, json_length, attachment_length = F.HEADER.unpack_from(frame)
    return frame[12:12 + json_length].rstrip(b" "), frame[12 + json_length:12 + json_length + attachment_length]


def edit_text(rng: random.Random, text: bytes) -> bytes:
    for _ in range(rng.randint(1, 3)):
        position = rng.randrange(len(text) + 1)
        piece = rng.choice(RAW) if rng.random() < 0.08 else rng.choice(TOKENS).encode("utf-8")
        action = rng.randrange(3)
        if action == 0:
            text = text[:position] + piece + text[position:]
        elif action == 1:
            text = text[:position] + piece + text[position + rng.randint(1, 3):]
        else:
            text = text[:position] + text[position + rng.randint(1, 4):]
    return text


TRICKY = [b"0", b"1", b"-1", b"-0", b"9007199254740991", b"9007199254740992", b"4294967296", b"1e2", b"1.0",
          b"null", b"true", b'"u8"', b'"f64"', b'"c64"', b'["u8"]', b"[]", b"[1]", b"[0]", b"[[1]]", b"{}",
          b'"\\ud83d"', b"[4294967296,4294967296]", b"[9007199254740992,0]", b"[2,2]", b"[1,0]"]


def array_case(rng: random.Random) -> bytes:
    """A frame with array references whose members and nesting are chosen to probe the rules."""
    count = rng.randint(1, 3)
    references, attachments, lengths = [], [], []
    for index in range(count):
        n = rng.choice([0, 1, 2, 4])
        dtype = rng.choice([b'"u8"', b'"u16"', b'"f64"'])
        members = {b"dtype": dtype, b"shape": b"[%d]" % n, b"att": b"%d" % index}
        if rng.random() < 0.5:
            members[rng.choice(list(members))] = rng.choice(TRICKY)
        if rng.random() < 0.1:
            members[b"extra"] = b"1"
        if rng.random() < 0.1:
            members.pop(rng.choice(list(members)))
        spec = b"{" + b",".join(b'"%s":%s' % item for item in members.items()) + b"}"
        depth = rng.choice([0, 1, 2, 58, 59, 60, 61, 62])
        references.append(b"[" * depth + b'{"ncp.array":' + spec + b"}" + b"]" * depth)
        size = {b'"u8"': 1, b'"u16"': 2, b'"f64"': 8}[dtype] * n
        attachments.append(bytes(rng.randrange(256) for _ in range(size)))
        lengths.append(size)
    if rng.random() < 0.1:
        lengths[rng.randrange(count)] += rng.choice([-1, 1, 8])
    region = b""
    for index, data in enumerate(attachments):
        if index and len(region) % 8:
            region += bytes(8 - len(region) % 8)
        region += data
    text = (b"{" + b",".join(b'"r%d":%s' % (i, r) for i, r in enumerate(references))
            + b',"att":[' + b",".join(b"%d" % max(0, n) for n in lengths) + b"]}")
    return wrap(text, region)


def make_case(rng: random.Random) -> bytes:
    if rng.random() < 0.2:
        return array_case(rng)
    arrays: list[F.Array] = []
    message = {f"k{i}": random_value(rng, 1, arrays) for i in range(rng.randrange(1, 5))}
    try:
        frame = F.encode(message)
    except F.FrameError:
        frame = F.encode({"k": 1})
    roll = rng.random()
    if roll < 0.15:
        return frame
    text, attachments = split(frame)
    if roll < 0.80:
        return wrap(edit_text(rng, text), attachments)
    if roll < 0.90 and attachments:
        region = bytearray(attachments)
        region[rng.randrange(len(region))] ^= 1 << rng.randrange(8)
        return wrap(text, bytes(region))
    if roll < 0.95:
        body = bytearray(frame[:-32])
        offset = rng.choice([4, 8])
        value = struct.unpack_from(">I", body, offset)[0] + rng.choice([-8, -1, 1, 8])
        struct.pack_into(">I", body, offset, max(0, value) & 0xFFFFFFFF)
        return bytes(body) + hashlib.sha256(body).digest()
    damaged = bytearray(frame)
    damaged[rng.randrange(len(damaged))] ^= 1 << rng.randrange(8)
    return bytes(damaged)


def plain(value, decoded):
    if isinstance(value, F.Array):
        index = next(i for i, item in enumerate(decoded.arrays) if item is value)  # not by equal content
        return {"ncp.array": {"dtype": value.dtype, "shape": list(value.shape), "att": index}}
    if isinstance(value, dict):
        return {k: plain(v, decoded) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v, decoded) for v in value]
    return value


def same(a, b) -> bool:
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return a == b and (a != 0 or str(a) == str(b))
    return a == b


def python_result(frame: bytes) -> dict:
    try:
        decoded = F.decode(frame, BOUND)
    except F.FrameError as error:
        return {"ok": False, "error": str(error)}
    except Exception as error:  # a crash is a finding, not a rejection
        return {"ok": "crash", "error": f"{type(error).__name__}: {error}"}
    message = plain(decoded.message, decoded)
    return {"ok": True, "identity": decoded.identity, "message": message,
            "arrays": [bytes(item.data).hex() for item in decoded.arrays]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--decoder", required=True)
    parser.add_argument("--cases", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--save", help="directory for the frames on which the decoders differ")
    args = parser.parse_args()
    rng = random.Random(args.seed)
    frames = [make_case(rng) for _ in range(args.cases)]
    with tempfile.NamedTemporaryFile(suffix=".corpus", delete=False) as handle:
        for frame in frames:
            handle.write(struct.pack(">I", len(frame)) + frame)
        corpus = handle.name
    try:
        output = subprocess.run([args.decoder, corpus, str(BOUND)], capture_output=True, check=True).stdout
    finally:
        os.unlink(corpus)
    # Split on newlines only: str.splitlines would also split at U+2028 and other characters
    # that JSON strings may hold unescaped.
    lines = output.decode("utf-8").split("\n")[:-1]
    if len(lines) != len(frames):
        print(f"the decoder printed {len(lines)} lines for {len(frames)} frames")
        return 1
    accepted = differences = 0
    for index, (frame, line) in enumerate(zip(frames, lines)):
        other = json.loads(line)
        mine = python_result(frame)
        if mine["ok"] is True:
            accepted += 1
        agree = mine["ok"] == other["ok"] and (mine["ok"] is not True or (
            mine["identity"] == other["identity"] and mine["arrays"] == other["arrays"]
            and same(mine["message"], other["message"])))
        if not agree:
            differences += 1
            if differences <= 10:
                print(f"case {index}: python {mine.get('ok')} ({mine.get('error', '')}), "
                      f"other {other.get('ok')} ({other.get('error', '')})\n  frame {frame.hex()}")
            if args.save:
                os.makedirs(args.save, exist_ok=True)
                with open(os.path.join(args.save, f"case-{index}.bin"), "wb") as out:
                    out.write(frame)
    print(f"fuzz: {len(frames)} frames, {accepted} accepted by Python, {differences} differences")
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main())
