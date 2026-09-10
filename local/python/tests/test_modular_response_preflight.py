"""Response bounds and scratch controls, independent of the codec optimization."""
from dataclasses import dataclass
import json
import unittest

from ncp_local import modular_wire as w
from modular_fixture import binding


@dataclass(frozen=True, slots=True)
class Record:
    value: object
    padding: str = ''


class ScalarContract:
    @staticmethod
    def decode_result(value):
        return Record(**w.closed(value, {'value', 'padding'}))

    decode_terminal = decode_result


class AbsoluteContract(ScalarContract):
    @staticmethod
    def decode_result(value):
        row = w.closed(value, {'value', 'padding'})
        return Record(abs(row['value']), row['padding'])


def response(value, padding=''):
    return w.Response(binding(), 1, w.Name.PREPARE, 'a' * 64, w.Outcome.COMMITTED,
        w.Code.OK, w.Body(w.BodyKind.PREPARED, Record(value, padding)))


def unsigned(item):
    return {'schema': w.RESPONSE_SCHEMA, 'binding': w.immutable_value(item.binding),
        'sequence': item.sequence, 'operation': item.operation.value,
        'request_digest': item.request_digest, 'outcome': item.outcome.value,
        'code': item.code.value, 'body': item.body.value(), 'result_digest': ''}


class ResponsePreflightTests(unittest.TestCase):
    def test_received_frame_and_typed_projection_have_separate_extent_checks(self):
        base = response(1e300).encode()
        padding = 'a' * (w.FRAME_BYTES - len(base))
        full = response(1e300, padding).encode()
        self.assertEqual(len(full), w.FRAME_BYTES)
        self.assertEqual(w.Response.decode(full, binding(), ScalarContract).encode(), full)

        # Removing the optional exponent plus sign saves one received byte.
        # Its numeric value and typed digest stay unchanged by that spelling.
        row = unsigned(response(1e300, padding + 'a'))
        row['result_digest'] = w.typed_digest(w.RESPONSE_SCHEMA, row, 'result_digest')
        canonical = json.dumps(row, ensure_ascii=False, separators=(',', ':')).encode()
        self.assertEqual(canonical.count(b'1e+300'), 1)
        received = canonical.replace(b'1e+300', b'1e300')
        self.assertEqual(len(received), w.FRAME_BYTES)
        self.assertEqual(len(canonical), w.FRAME_BYTES + 1)
        parsed = w.parse(received)
        self.assertEqual(w.typed_digest(w.RESPONSE_SCHEMA, parsed, 'result_digest'), parsed['result_digest'])
        with self.assertRaises(w.ModularError) as caught:
            w.Response.decode(received, binding(), ScalarContract)
        self.assertEqual(caught.exception.code, 'capacity')
        self.assertEqual(w.Response.decode(full, binding(), ScalarContract).encode(), full)

    def test_raw_and_reconstructed_digests_both_bind_the_result(self):
        for value, accepted in ((-0.0, False), (-1.0, False), (0.0, True), (1.0, True)):
            encoded = response(value).encode()
            w.Response.decode(encoded, binding(), ScalarContract)
            if accepted:
                w.Response.decode(encoded, binding(), AbsoluteContract)
            else:
                with self.assertRaises(w.ModularError) as caught:
                    w.Response.decode(encoded, binding(), AbsoluteContract)
                self.assertEqual(caught.exception.code, 'wire')
            row = json.loads(encoded)
            row['result_digest'] = '0' * 64
            bad = json.dumps(row, separators=(',', ':')).encode()
            with self.assertRaises(w.ModularError) as caught:
                w.Response.decode(bad, binding(), ScalarContract)
            self.assertEqual(caught.exception.code, 'wire')
            w.Response.decode(encoded, binding(), ScalarContract)

    def test_public_scratch_retains_placeholder_when_hash_capacity_fails(self):
        accepted = response((0,) * 14_000)
        accepted.encode()
        rejected = response((0,) * 14_561)
        placeholder = w.encode(unsigned(rejected))
        self.assertLess(len(placeholder), w.FRAME_BYTES)
        slot = bytearray(b'\xa5') * w.FRAME_BYTES
        with self.assertRaises(w.ModularError) as caught:
            rejected.write(slot)
        self.assertEqual(caught.exception.code, 'capacity')
        self.assertEqual(slot[:len(placeholder)], placeholder)
        self.assertEqual(slot[len(placeholder):], b'\xa5' * (w.FRAME_BYTES - len(placeholder)))
        accepted.encode()


if __name__ == '__main__':
    unittest.main()
