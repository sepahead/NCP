import hashlib
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

from ncp_local import modular_wire as w
from ncp_local import modular_owner as owner
from ncp_local import modular_client as client
from ncp_local import modular_buffer as buffer
from ncp_local.modular_profile import CORE_DESCRIPTOR


class WireTests(unittest.TestCase):
    def test_ascii_accounting_matches_independent_encoded_pair_extents(self):
        for first in range(128):
            for second in range(128):
                value = chr(first) + chr(second)
                for quoted in (False, True):
                    encoded = json.dumps(value, ensure_ascii=False).encode() if quoted else value.encode()
                    extent = len(encoded)
                    self.assertEqual(w._string_extent(value, extent, quoted=quoted), extent)
                    with self.assertRaises(w.ModularError) as rejected:
                        w._string_extent(value, extent - 1, quoted=quoted)
                    self.assertEqual(rejected.exception.code, "capacity")

    def test_string_accounting_preserves_unicode_and_error_order(self):
        for value in ("", "μ", "😀", "aμ", "\x00μ", '"μ\\'):
            for quoted in (False, True):
                encoded = json.dumps(value, ensure_ascii=False).encode() if quoted else value.encode()
                self.assertEqual(w._string_extent(value, len(encoded), quoted=quoted), len(encoded))
        for value, limit, expected in (("a\ud800", 0, "capacity"), ("a\ud800", 1, "wire"),
                                       ("\ud800a", 0, "wire"), ("μ\ud800", 1, "capacity"),
                                       ("μ\ud800", 2, "wire")):
            with self.assertRaises(w.ModularError) as rejected:
                w._string_extent(value, limit)
            self.assertEqual(rejected.exception.code, expected)
        class LegacyString(str):
            def isascii(self): raise AssertionError("Subclass method must not run")
        self.assertEqual(w._string_extent(LegacyString("abc"), 5, quoted=True), 5)
        self.assertEqual(w._string_extent("abc", 3.0), 3)

    def test_descriptor_response_dispositions_cover_every_closed_combination(self):
        descriptor = json.loads(CORE_DESCRIPTOR)
        accepted = 0
        checked = 0
        binding = buffer.BufferBinding("1" * 64, "2" * 64,
            "10000000-0000-4000-8000-000000000001", "10000000-0000-4000-8000-000000000002",
            "10000000-0000-4000-8000-000000000003")
        for operation in w.Name:
            for outcome in w.Outcome:
                disposition = descriptor["response_dispositions"][outcome.value]
                for code in w.Code:
                    for kind in w.BodyKind:
                        expected_body = disposition.get("operation_bodies", {}).get(operation.value)
                        if operation.value in disposition.get("operations", []): expected_body = disposition["body"]
                        expected = code.value in descriptor["outcome_codes"][outcome.value] and expected_body == kind.value
                        data = w.AckStamp(1, "3" * 64, "4" * 64) if kind == w.BodyKind.ACKNOWLEDGED else None
                        response = w.Response(binding, 1, operation, "3" * 64, outcome, code, w.Body(kind, data))
                        try: response.check_shape(); actual = True
                        except w.ModularError: actual = False
                        self.assertEqual(actual, expected, (operation, outcome, code, kind))
                        accepted += actual
                        checked += 1
        self.assertEqual((accepted, checked), (105, 10_296))

    def test_descriptor_logical_bounds_match_components_and_composition_admission(self):
        b = json.loads(CORE_DESCRIPTOR)["bounds"]
        self.assertEqual(b["endpoint_logical_working_extent_excluding_payload"], owner.ENDPOINT_LOGICAL_OVERHEAD)
        self.assertEqual(owner.ENDPOINT_LOGICAL_OVERHEAD, 131_072 + 32_768 + 16_384 + 6 * 65_536 + 3 * 65_536 + 131_072 + 32_768 + 5 * 65_536)
        self.assertEqual(b["additional_client_logical_bytes"], client.CLIENT_LOGICAL_OVERHEAD)
        self.assertEqual(client.CLIENT_LOGICAL_OVERHEAD, 6 * 65_536 + 3 * 65_536 + 131_072 + 32_768 + 5 * 65_536 + 4_096)
        self.assertEqual(b["sixteen_clients_additional_logical_bytes"], 16 * client.CLIENT_LOGICAL_OVERHEAD)
        self.assertEqual(b["input_spec_encoded_bytes"], buffer.INPUT_SPEC_BYTES)
        self.assertEqual(b["input_spec_slots"], buffer.LIVE_SLOTS)
        self.assertEqual(b["additional_input_metadata_logical_bytes"], buffer.INPUT_METADATA_BYTES)
        self.assertEqual(buffer.INPUT_METADATA_BYTES, 2 * buffer.LIVE_SLOTS * buffer.INPUT_SPEC_BYTES + 4_096)
        self.assertEqual(b["owner_frame_extents"], b["retained_frames"] + b["ingress_frames"] + b["output_staging_frames"] + b["egress_verification_frame_extents"] + b["framing_conversion_frame_extents"])
        self.assertEqual(b["parsed_value_extents"], 3)
        self.assertEqual(b["decoded_source_utf8_bytes"] + b["scanner_token_utf8_bytes"] + b["scalar_base64_utf8_bytes"], 5 * 65_536)
        self.assertEqual(b["additional_import_metadata_logical_bytes"], owner.IMPORT_METADATA_LOGICAL_BYTES)
        self.assertEqual(b["import_metadata_record_encoded_bytes"], owner.IMPORT_METADATA_BYTES)
        self.assertEqual(owner.composition_budget((0,) * 16), (0, 20_185_088))
        self.assertEqual(owner.composition_budget((buffer.ENDPOINT_BYTES,) * 4 + (0,) * 12), (268_435_456, 20_185_088))
        with self.assertRaises(buffer.BufferError): owner.composition_budget((0,) * 17)
        with self.assertRaises(buffer.BufferError): owner.composition_budget((buffer.ENDPOINT_BYTES,) * 4 + (1,))

    def test_immutable_projection_charges_compact_json_before_materialization(self):
        accepted = (9_007_199_254_740_991,) * 3_855
        self.assertLessEqual(len(json.dumps(accepted, separators=(",", ":")).encode()), w.FRAME_BYTES)
        self.assertEqual(w.immutable_value(accepted), list(accepted))
        for value in ((9_007_199_254_740_991,) * 4_096, "\x00" * 10_923, "😀" * 16_384):
            with self.subTest(kind=type(value).__name__):
                self.assertGreater(len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()), w.FRAME_BYTES)
                with self.assertRaises(w.ModularError): w.immutable_value(value)
                with self.assertRaises(w.ModularError): w.check_immutable(value)
                raw = list(value) if type(value) is tuple else value
                with self.assertRaises(w.ModularError): w.encode(raw)
        for value in ("😀" * 16_383, "\x00" * 10_922 + "aa", -0.0, 5e-324, None, True, 7):
            projected = w.immutable_value(value)
            self.assertEqual(w.encode(projected), json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        for value in (float("nan"), float("inf"), -float("inf"), 9_007_199_254_740_992, "\ud800"):
            with self.assertRaises(w.ModularError): w.immutable_value(value)

    def test_selected_binary64_bits_and_independent_hash_construction(self):
        root = Path(__file__).resolve().parents[3]
        rows = json.loads((root / "ncp-core/tests/fixtures/modular-binary64.json").read_text())
        for row in rows:
            with self.subTest(number=row["json"]):
                value = w.parse(row["json"].encode())
                bits = bytes.fromhex(row["bits"])
                self.assertEqual(struct.pack(">d", value), bits)
                expected = hashlib.sha256(w.PROFILE_DOMAIN.encode() + b"\x00\x03" + bits).hexdigest()
                self.assertEqual(w.typed_digest(w.PROFILE_DOMAIN, value), expected)
        self.assertNotEqual(w.typed_digest(w.PROFILE_DOMAIN, w.parse(b"0")), w.typed_digest(w.PROFILE_DOMAIN, w.parse(b"-0")))

    def test_projection_exact_boundary_and_one_more_element(self):
        self.assertEqual(len(w.PROFILE_DOMAIN) + 1 + 9, 32)
        self.assertEqual(32 + 9 * 14_560, 131_072)
        self.assertLess(len(w.encode([0] * 14_561)), 65_536)
        self.assertTrue(w.typed_digest(w.PROFILE_DOMAIN, [0] * 14_560))
        with self.assertRaises(w.ModularError): w.typed_digest(w.PROFILE_DOMAIN, [0] * 14_561)

    def test_frame_and_lexical_limits(self):
        self.assertEqual(w.parse(b"0" + b" " * 65_535), 0)
        for payload in (b"0" + b" " * 65_536, br'{"a":1,"\u0061":2}', br'"\ud800"', b"0 trailing", b"NaN", b"1e301", b"9007199254740992", b"-9007199254740992"):
            with self.subTest(payload=payload[:40]):
                with self.assertRaises(ValueError): w.parse(payload)
        with self.assertRaises(w.ModularError): w.typed_digest(w.PROFILE_DOMAIN, 9_007_199_254_740_992)
        with self.assertRaises(w.ModularError): w.typed_digest("ncp.local.request.v1", {})

    def test_escaped_string_frame_bound_uses_bounded_encoder_fragments(self):
        accepted = "\x00" * 10_922 + "aa"
        expected = json.dumps(accepted, ensure_ascii=False).encode()
        self.assertEqual(len(expected), 65_536)
        observed = []
        original = json.dumps
        def measured(value, **kwargs):
            if type(value) is str: observed.append(len(value))
            return original(value, **kwargs)
        with patch.object(w.json, "dumps", side_effect=measured):
            self.assertEqual(w.encode(accepted), expected)
            with self.assertRaises(w.ModularError): w.encode(accepted + "a")
            with self.assertRaises(w.ModularError): w.encode("\x00" * 65_536)
        self.assertTrue(observed)
        self.assertLessEqual(max(observed), 256)
        for value in ('"\\\b\f\n\r\t\u007f\u00e9\U0001f680', {"x": [1, 1.25, -0.0, True, None]}):
            self.assertEqual(w.encode(value), json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


if __name__ == "__main__": unittest.main()
