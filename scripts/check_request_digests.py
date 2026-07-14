#!/usr/bin/env python3
"""Verify or mechanically refresh embedded NCP request-digest-v1 values.

This is an independent stdlib implementation of ``contract/request-digest.v1.json``.
It checks every structurally present mutation request in the canonical behavior and
wire corpora. Intentionally malformed non-hex digest fixtures remain untouched and
are rejected by their normal validation vector.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
PATHS = (
    ROOT / "conformance/behavior/vectors.json",
    ROOT / "conformance/vectors/step_request.json",
    ROOT / "conformance/vectors/run_request.json",
    ROOT / "conformance/vectors/close_session.json",
)
VECTOR_PATH = ROOT / "conformance/request-digest/v1.json"
DOMAIN = b"ncp.request-digest.v1\0"
MUTATIONS = {"step_request", "run_request", "close_session"}
MAX_DEPTH = 32
MAX_BYTES = 2_097_152
MAX_NUMBER = 1e300
HEX = frozenset("0123456789abcdef")


class DigestError(ValueError):
    pass


def _parse_int_preserve_negative_zero(token: str) -> int | float:
    return -0.0 if token == "-0" else int(token, 10)


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise DigestError(f"duplicate JSON key {key!r}")
        value[key] = member
    return value


def _load(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_object_no_duplicates,
        parse_int=_parse_int_preserve_negative_zero,
        parse_constant=lambda token: (_ for _ in ()).throw(
            DigestError(f"non-finite JSON constant {token}")
        ),
    )


def _length(value: int) -> bytes:
    if value < 0 or value >= 1 << 64:
        raise DigestError("projection length is outside u64")
    return struct.pack(">Q", value)


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8", errors="strict")
    return b"\x04" + _length(len(encoded)) + encoded


def _excluded(location: str, key: str) -> bool:
    return (location == "root" and key == "authority") or (
        location == "operation" and key in {"request_digest", "retry"}
    )


def _encode(value: Any, depth: int, location: str) -> bytes:
    if depth > MAX_DEPTH:
        raise DigestError("projection nesting depth exceeded")
    if value is None:
        return b"\x00"
    if value is False:
        return b"\x01"
    if value is True:
        return b"\x02"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if not math.isfinite(number) or abs(number) > MAX_NUMBER:
            raise DigestError("number is outside the finite magnitude budget")
        return b"\x03" + struct.pack(">d", number)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return b"\x05" + _length(len(value)) + b"".join(
            _encode(child, depth + 1, "nested") for child in value
        )
    if isinstance(value, dict):
        entries = sorted(
            ((key, child) for key, child in value.items() if not _excluded(location, key)),
            key=lambda pair: pair[0].encode("utf-8", errors="strict"),
        )
        encoded = [b"\x06", _length(len(entries))]
        for key, child in entries:
            encoded.append(_string(key))
            child_location = "operation" if location == "root" and key == "operation" else "nested"
            encoded.append(_encode(child, depth + 1, child_location))
        return b"".join(encoded)
    raise DigestError(f"unsupported JSON value {type(value).__name__}")


def request_digest(request: dict[str, Any]) -> str:
    if request.get("kind") not in MUTATIONS or not isinstance(request.get("operation"), dict):
        raise DigestError("not a mutation request with an operation object")
    projection = DOMAIN + _encode(request, 0, "root")
    if len(projection) > MAX_BYTES:
        raise DigestError("projection byte budget exceeded")
    return hashlib.sha256(projection).hexdigest()


def _walk(value: Any, pointer: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        if value.get("kind") in MUTATIONS and isinstance(value.get("operation"), dict):
            yield pointer or "/", value
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _walk(child, f"{pointer}/{escaped}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{pointer}/{index}")


def _is_hex_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in HEX for char in value)


def process(path: Path, write: bool) -> list[str]:
    data = _load(path)
    failures: list[str] = []
    changed = False
    for pointer, request in _walk(data):
        operation = request["operation"]
        embedded = operation.get("request_digest")
        if not _is_hex_digest(embedded):
            continue
        expected = request_digest(request)
        if embedded != expected:
            if write:
                operation["request_digest"] = expected
                changed = True
            else:
                failures.append(
                    f"{path.relative_to(ROOT)}#{pointer}/operation/request_digest: "
                    f"got {embedded}, expected {expected}"
                )
    if changed:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return failures


def _apply_case(base: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    request = copy.deepcopy(base)
    for operation in case["patch"]:
        path = operation["path"]
        if not isinstance(path, list) or not path:
            raise DigestError(f"case {case['id']} has an invalid patch path")
        parent: Any = request
        for segment in path[:-1]:
            parent = parent[segment]
        leaf = path[-1]
        if operation["op"] == "set":
            parent[leaf] = operation["value"]
        elif operation["op"] == "remove":
            del parent[leaf]
        else:
            raise DigestError(f"case {case['id']} has unknown patch op {operation['op']!r}")
    return request


def check_vector_file() -> list[str]:
    data = _load(VECTOR_PATH)
    failures: list[str] = []
    for case in data["cases"]:
        got = request_digest(_apply_case(data["base_request"], case))
        if got != case["expected_digest"]:
            failures.append(
                f"{VECTOR_PATH.relative_to(ROOT)} case {case['id']}: "
                f"got {got}, expected {case['expected_digest']}"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="refresh valid embedded digests")
    args = parser.parse_args()
    failures = [failure for path in PATHS for failure in process(path, args.write)]
    failures.extend(check_vector_file())
    if failures:
        print("request-digest-v1 corpus drift:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("Run scripts/check_request_digests.py --write and review.", file=sys.stderr)
        return 1
    checked = sum(
        1
        for path in PATHS
        for _, request in _walk(_load(path))
        if _is_hex_digest(request["operation"].get("request_digest"))
    )
    print(
        f"request-digest-v1 corpus values are exact "
        f"({checked} embedded requests + request-digest conformance vectors)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
