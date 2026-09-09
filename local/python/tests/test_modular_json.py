"""Compare modular ingress with the unchanged historical JSON scanner."""

import json
import math
import random
import unittest
from unittest.mock import patch

from ncp_local import modular_wire as modular
from ncp_local import wire as reference


def scan_outcome(scanner_type, text):
    scanner = scanner_type(text)
    try:
        scanner.scan()
        outcome = ("accepted",)
    except reference.BoundedJsonError as error:
        outcome = (error.code, error.limit_code)
    return outcome + (
        scanner.position,
        scanner.objects,
        scanner.arrays,
        scanner.members,
        scanner.array_items,
        scanner.string_bytes,
    )


class ModularJsonTests(unittest.TestCase):
    def assert_same_scan(self, text):
        expected = scan_outcome(reference._Scanner, text)
        self.assertEqual(scan_outcome(modular._ModularScanner, text), expected)
        if expected[0] == "accepted":
            payload = text.encode("utf-8")
            self.assertEqual(
                repr(modular.parse(payload)), repr(reference.decode(payload))
            )

    def test_all_ascii_characters_preserve_key_and_value_grammar(self):
        for point in range(128):
            with self.subTest(point=point):
                self.assert_same_scan('{"value":"a' + chr(point) + 'z"}')
                self.assert_same_scan('{"a' + chr(point) + 'z":1}')
        self.assertEqual(modular.parse(b'"\x7f"'), "\x7f")

    def test_complete_and_partial_prefixes_preserve_byte_limits_and_errors(self):
        for capture, limit in ((True, 128), (False, 65_536)):
            for remaining in range(-2, 6):
                for suffix in ("", "é", "\\u00e9", "😀", "\\ud83d\\ude00", "\\n", "a"):
                    text = '"' + "a" * (limit - remaining) + suffix + '"'
                    for total in (0, reference.MAX_TOTAL_STRING_BYTES - 1):
                        states = []
                        for scanner_type in (
                            reference._Scanner,
                            modular._ModularScanner,
                        ):
                            scanner = scanner_type(text)
                            scanner.string_bytes = total
                            try:
                                outcome = (
                                    "accepted",
                                    scanner._parse_string(capture=capture),
                                )
                            except reference.BoundedJsonError as error:
                                outcome = (error.code, error.limit_code)
                            states.append(
                                outcome + (scanner.position, scanner.string_bytes)
                            )
                        self.assertEqual(
                            states[0], states[1], (capture, remaining, suffix, total)
                        )
        for ending in ("", "\\", "\\q", "\\ud800", "\\udc00", "\\ud800\\u0041", "\x00"):
            self.assert_same_scan('{"v":"' + "a" * 100 + ending)

    def test_frozen_seeded_unicode_and_byte_mutations_preserve_admission(self):
        rng = random.Random(20260909)
        alphabet = list("abcdefghijklmnopqrstuvwxyz0123456789 ") + [
            '"',
            "\\",
            "\n",
            "\t",
            "é",
            "€",
            "😀",
            "\x7f",
        ]
        for index in range(2500):
            value = "".join(rng.choice(alphabet) for _ in range(rng.randrange(300)))
            record = {
                "a": value,
                "nested": [
                    index % 17,
                    -0.0,
                    None,
                    bool(index % 2),
                    {"key": value[:20]},
                ],
            }
            payload = json.dumps(
                record, ensure_ascii=bool(index % 2), separators=(",", ":")
            ).encode()
            offset = rng.randrange(len(payload))
            mutation = (
                payload[:offset] + bytes([rng.randrange(256)]) + payload[offset + 1 :]
            )
            for raw in (payload, mutation):
                try:
                    text = raw.decode("utf-8")
                except UnicodeError:
                    with self.assertRaises(modular.ModularError):
                        modular.parse(raw)
                else:
                    self.assert_same_scan(text)

    def test_rejections_precede_generic_object_decoding(self):
        cases = (
            b'{"a":1,"\\u0061":2}',
            b'{"' + b"a" * 129 + b'":0}',
            b'{"v":"' + b"a" * 100,
            b'{"v":"\\ud800"}',
            b'{"v":"\xff"}',
            b'{"v":9007199254740992}',
            b'{"v":1e301}',
            b"[" * 33 + b"0" + b"]" * 33,
            b'"' + b"a" * 65_535 + b'"',
        )
        for payload in cases:
            with patch("ncp_local.modular_wire.json.loads") as decode:
                with self.assertRaises(modular.ModularError):
                    modular.parse(payload)
                decode.assert_not_called()
        with patch("ncp_local.modular_wire.json.loads", wraps=json.loads) as decode:
            result = modular.parse(b'{"' + b"a" * 128 + b'":-0}')
            decode.assert_called_once()
            self.assertEqual(math.copysign(1, result["a" * 128]), -1)

    def test_frame_admission_and_memoryview_conversion_remain_bounded(self):
        valid = b'"' + b"a" * 65_534 + b'"'
        self.assertEqual(modular.parse(memoryview(valid)), "a" * 65_534)
        for payload in (b"", bytearray(b"null"), "null", memoryview(valid + b" ")):
            with self.assertRaises(modular.ModularError) as caught:
                modular.parse(payload)
            self.assertEqual(caught.exception.code, "capacity")
