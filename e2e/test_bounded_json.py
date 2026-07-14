from __future__ import annotations

import io
import unittest

from e2e.bounded_json import (
    MAX_FRAME_BYTES,
    MAX_NESTING_DEPTH,
    BoundedJsonError,
    parse_bounded_json_line,
)


class BoundedJsonLineTests(unittest.TestCase):
    def test_valid_lf_and_crlf_frames(self) -> None:
        self.assertEqual(parse_bounded_json_line(io.BytesIO(b'{"ok":true}\n')), {"ok": True})
        self.assertEqual(parse_bounded_json_line(io.BytesIO(b'{"ok":true}\r\n')), {"ok": True})

    def test_oversized_and_unterminated_frames_fail_before_parse(self) -> None:
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-001"):
            parse_bounded_json_line(io.BytesIO(b" " * (MAX_FRAME_BYTES + 1) + b"\n"))
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-009"):
            parse_bounded_json_line(io.BytesIO(b'{"ok":true}'))

    def test_duplicate_decoded_key_and_depth_fail(self) -> None:
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-007"):
            parse_bounded_json_line(io.BytesIO(b'{"a":1,"\\u0061":2}\n'))
        nested = ("[" * (MAX_NESTING_DEPTH + 1) + "0" + "]" * (MAX_NESTING_DEPTH + 1) + "\n").encode()
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-002"):
            parse_bounded_json_line(io.BytesIO(nested))

    def test_invalid_utf8_and_surrogate_escape_fail(self) -> None:
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-008"):
            parse_bounded_json_line(io.BytesIO(b'"\xff"\n'))
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-008"):
            parse_bounded_json_line(io.BytesIO(b'"\\ud800"\n'))

    def test_number_and_string_budgets_fail(self) -> None:
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-006"):
            parse_bounded_json_line(io.BytesIO(b"9007199254740992\n"))
        with self.assertRaisesRegex(BoundedJsonError, "NCP-LIMIT-005"):
            parse_bounded_json_line(io.BytesIO(("\"" + "x" * 65_537 + "\"\n").encode()))


if __name__ == "__main__":
    unittest.main()
