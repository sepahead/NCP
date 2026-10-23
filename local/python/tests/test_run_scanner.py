"""Compare the run-matching scanner with the unchanged reference scanner."""

import itertools
import json
import random
import unittest

from ncp_local import LocalBinding
from ncp_local import wire
from ncp_local.protocol import make_request


def outcome(kind, text, string_bytes=0):
    scanner = kind(text)
    scanner.string_bytes = string_bytes
    try:
        scanner.scan()
        result = ("accepted",)
    except wire.BoundedJsonError as error:
        result = (error.code, error.limit_code)
    return result + (
        scanner.position,
        scanner.objects,
        scanner.arrays,
        scanner.members,
        scanner.array_items,
        scanner.string_bytes,
    )


class RunScannerTests(unittest.TestCase):
    def assert_same(self, text, string_bytes=0):
        self.assertEqual(
            outcome(wire._RunScanner, text, string_bytes),
            outcome(wire._Scanner, text, string_bytes),
            repr(text[:120]),
        )

    def test_every_short_number_spelling(self):
        for length in range(1, 5):
            for chars in itertools.product("-0123456789.eE+", repeat=length):
                token = "".join(chars)
                for context in ("{}", "[{}]", '{{"a":{}}}', "[{},1]"):
                    self.assert_same(context.format(token))
        for token in (
            "9007199254740991",
            "9007199254740992",
            "-9007199254740992",
            "1e300",
            "1e301",
            "1.0000000000000001e300",
            "1e309",
            "-0",
            "1.e5",
        ):
            self.assert_same("[" + token + "]")

    def test_every_ascii_character_and_string_limit(self):
        for point in range(0x80):
            for template in ('{{"v":"a{}z"}}', '{{"a{}z":1}}', '"{}"', '"a{}'):
                self.assert_same(template.format(chr(point)))
        for limit in (wire.MAX_KEY_BYTES, wire.MAX_STRING_BYTES):
            for remaining in range(-2, 4):
                for suffix in ("", "é", "\\u00e9", "😀", "\\n", "\\", '"'):
                    body = "a" * (limit - remaining) + suffix
                    self.assert_same('{"' + body + '":1}')
                    self.assert_same('["' + body + '"]')
        for total in (0, wire.MAX_TOTAL_STRING_BYTES - 4, wire.MAX_TOTAL_STRING_BYTES):
            for text in ('"abcd"', '"abcde"', '{"k":"v"}'):
                self.assert_same(text, total)

    def test_whitespace(self):
        pieces = [" ", "\n", "\r", "\t", "\x0b", " ", ""]
        for a, b in itertools.product(pieces, repeat=2):
            self.assert_same(f'{a}{{{b}"k"{a}:{b}1{a}}}{b}')
            self.assert_same(f"{a}[{b}1{a},{b}2{a}]{b}")

    def test_mutations_of_request_frames(self):
        binding = LocalBinding.fresh("neural")
        rng = random.Random(20261022)
        body = {
            "senders": [rng.randrange(1, 1001) for _ in range(13)],
            "times": [round(rng.uniform(0, 10), 1) + 0.1 for _ in range(13)],
        }
        text = json.dumps(
            make_request(binding, 1, "step", body),
            separators=(",", ":"),
            ensure_ascii=False,
        )
        self.assert_same(text)
        alphabet = list('{}[],:"\\ -+.eE0129aZ\x00\x1f\x7fé')
        for index in range(len(text)):
            self.assert_same(text[:index] + text[index + 1 :])
            for character in alphabet:
                self.assert_same(text[:index] + character + text[index + 1 :])

    def test_random_documents(self):
        rng = random.Random(7)

        def value(depth):
            kind = rng.random()
            if depth > 34 or kind < 0.25:
                return rng.choice(
                    [0, -0.0, 1, 2**53 - 1, 2**53, 1e300, -1e-300, 0.1, True, None]
                )
            if kind < 0.5:
                return "".join(
                    rng.choice('ab"\\/\b\n\x00\x1féü😀 ')
                    for _ in range(rng.randrange(8))
                )
            if kind < 0.75:
                return [value(depth + 1) for _ in range(rng.randrange(4))]
            return {
                rng.choice("abcé😀"): value(depth + 1) for _ in range(rng.randrange(4))
            }

        for _ in range(5000):
            text = json.dumps(value(0), ensure_ascii=rng.random() < 0.5)
            self.assert_same(text)
            index = rng.randrange(len(text))
            self.assert_same(text[:index] + rng.choice('{}[],:"\\ 0e.-') + text[index:])


if __name__ == "__main__":
    unittest.main()
