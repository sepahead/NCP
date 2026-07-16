"""Exact and adjacent strict-parser and base64url boundary tests."""

from __future__ import annotations

import unittest

from prototype.strict import (
    JSON_SAFE_INTEGER_MAX,
    ErrorCode,
    JsonLimits,
    PrototypeError,
    b64url_decode,
    b64url_encode,
    strict_json_loads,
)


def limits(**overrides: int) -> JsonLimits:
    values = {
        "max_bytes": 128,
        "max_depth": 8,
        "max_nodes": 32,
        "max_members": 8,
        "max_string_bytes": 32,
    }
    values.update(overrides)
    return JsonLimits(**values)


class StrictBoundaryTests(unittest.TestCase):
    def test_json_limits_accept_exact_and_reject_above(self) -> None:
        exact_bytes = b'{"x":1}'
        self.assertEqual(
            strict_json_loads(exact_bytes, limits(max_bytes=len(exact_bytes))),
            {"x": 1},
        )
        with self.assertRaisesRegex(PrototypeError, "byte length"):
            strict_json_loads(exact_bytes + b" ", limits(max_bytes=len(exact_bytes)))

        strict_json_loads(b"[[]]", limits(max_depth=2))
        with self.assertRaisesRegex(PrototypeError, "depth"):
            strict_json_loads(b"[[[]]]", limits(max_depth=2))

        strict_json_loads(b'{"a":1}', limits(max_nodes=3))
        with self.assertRaisesRegex(PrototypeError, "node count"):
            strict_json_loads(b'{"a":1}', limits(max_nodes=2))

        strict_json_loads(b'["a","b"]', limits(max_members=2))
        with self.assertRaisesRegex(PrototypeError, "length"):
            strict_json_loads(b'["a","b","c"]', limits(max_members=2))

        strict_json_loads(b'"abcd"', limits(max_string_bytes=4))
        with self.assertRaisesRegex(PrototypeError, "string token"):
            strict_json_loads(b'"abcde"', limits(max_string_bytes=4))

    def test_integer_boundary_and_ambiguous_grammars(self) -> None:
        self.assertEqual(
            strict_json_loads(str(JSON_SAFE_INTEGER_MAX).encode(), limits()),
            JSON_SAFE_INTEGER_MAX,
        )
        cases = {
            str(JSON_SAFE_INTEGER_MAX + 1).encode(): ErrorCode.BOUNDS,
            str(-JSON_SAFE_INTEGER_MAX - 1).encode(): ErrorCode.BOUNDS,
            b"-0": ErrorCode.JSON,
            b"01": ErrorCode.JSON,
            b"1.0": ErrorCode.JSON,
            b"1e0": ErrorCode.JSON,
        }
        for token, code in cases.items():
            with self.subTest(token=token), self.assertRaises(PrototypeError) as caught:
                strict_json_loads(token, limits())
            self.assertEqual(caught.exception.code, code)

    def test_base64url_exact_bound_and_trailing_bits(self) -> None:
        self.assertEqual(b64url_decode("AA", maximum=1), b"\x00")
        with self.assertRaisesRegex(PrototypeError, "trailing bits"):
            b64url_decode("AB", maximum=1)
        encoded = b64url_encode(b"test")
        self.assertEqual(b64url_decode(encoded, maximum=4), b"test")
        with self.assertRaises(PrototypeError) as caught:
            b64url_decode(encoded, maximum=3)
        self.assertEqual(caught.exception.code, ErrorCode.BOUNDS)


if __name__ == "__main__":
    unittest.main()
