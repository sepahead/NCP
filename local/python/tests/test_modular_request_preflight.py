"""Boundary controls for request validation without discarded wire output."""
from dataclasses import replace
import json
import unittest

from ncp_local import modular_wire as w
from modular_fixture import Counter, Initial, binding


class RequestPreflightTests(unittest.TestCase):
    def test_validation_retains_aggregate_limits_below_the_frame_ceiling(self):
        for accepted, rejected in (
            ([{} for _ in range(4096)], [{} for _ in range(4097)]),
            ([[] for _ in range(4095)], [[] for _ in range(4096)]),
        ):
            self.assertLess(len(json.dumps(rejected, separators=(",", ":"))), w.FRAME_BYTES)
            w._validate_json(accepted)
            with self.assertRaises(w.ModularError) as caught:
                w._validate_json(rejected)
            self.assertEqual(caught.exception.code, "capacity")
            w._validate_json(accepted)

    def test_complete_request_capacity_includes_the_final_digest(self):
        context = binding()
        empty = w.Request.create(context, 1, w.Execute(None, w.Prepare("")))
        available = w.FRAME_BYTES - len(empty)
        command = w.Execute(None, w.Prepare("a" * available))
        encoded = w.Request.create(context, 1, command)
        self.assertEqual(len(encoded), w.FRAME_BYTES)
        value = json.loads(encoded)
        self.assertEqual(encoded, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
        request = w.Request(context, 1, command, value["request_digest"])
        request.verify(context)
        scratch = bytearray(w.FRAME_BYTES)
        request.verify(context, scratch=scratch)
        self.assertEqual(scratch, encoded)
        with self.assertRaises(w.ModularError) as caught:
            w.Request.create(context, 1, w.Execute(None, w.Prepare("a" * (available + 1))))
        self.assertEqual(caught.exception.code, "capacity")
        self.assertEqual(w.Request.create(context, 1, command), encoded)

    def test_scratch_bytes_and_rejection_order_remain_observable(self):
        context = binding()
        encoded = w.Request.create(context, 1, w.Execute(None, w.Prepare(Initial(1))))
        request = w.Request.decode(encoded, context, Counter)
        for size in (0, len(encoded) - 1, len(encoded), len(encoded) + 7):
            scratch = bytearray(b"\xa5") * size
            if size < len(encoded):
                with self.assertRaises(w.ModularError) as caught:
                    request.verify(context, scratch=scratch)
                self.assertEqual(caught.exception.code, "capacity")
            else:
                request.verify(context, scratch=scratch)
                self.assertEqual(scratch[:len(encoded)], encoded)
                self.assertEqual(scratch[len(encoded):], b"\xa5" * (size - len(encoded)))
            self.assertEqual(len(scratch), size)
            request.verify(context)

        for rejected, code, emits in (
            (replace(request, request_digest="\ud800"), "wire", False),
            (replace(request, sequence=w.MAX_ID + 1), "wire", False),
            (replace(request, request_digest="0" * 64), "binding", True),
            (replace(request, sequence=True), "binding", True),
        ):
            for scratch in (None, bytearray(b"\xa5") * w.FRAME_BYTES):
                with self.assertRaises(w.ModularError) as caught:
                    rejected.verify(context, scratch=scratch)
                self.assertEqual(caught.exception.code, code)
                if scratch is not None:
                    expected = w.encode(rejected.value()) if emits else b""
                    self.assertEqual(scratch[:len(expected)], expected)
                    self.assertEqual(scratch[len(expected):], b"\xa5" * (w.FRAME_BYTES - len(expected)))
                request.verify(context)


if __name__ == "__main__":
    unittest.main()
