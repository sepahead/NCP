"""Selected structural controls for development payload primitives only."""

from dataclasses import asdict, replace
import json
import unittest

from ncp_local.modular_buffer import (
    BUFFER_BYTES, CHUNK_BYTES, COMPOSITION_BYTES, ENDPOINT_BYTES, ENDPOINTS,
    FRAME_BYTES, INCOMPLETE_SLOTS, LIVE_SLOTS, MANIFEST_BYTES, MAX_ID, SEMANTIC_SLOTS,
    BufferBinding, BufferChunk, BufferError, BufferManifest, BufferPool,
    BufferRef, TrustedHostCreationContext, admit_composition, decode_chunk, encode_chunk,
)

SOURCE = "10000000-0000-4000-8000-000000000003"
TARGET = "10000000-0000-4000-8000-000000000004"
SEMANTIC = "5" * 64


def binding(generation=SOURCE):
    return BufferBinding("1" * 64, "2" * 64,
                         "10000000-0000-4000-8000-000000000001",
                         "10000000-0000-4000-8000-000000000002", generation)


def context(value):
    return TrustedHostCreationContext(value, "3" * 64, "4" * 64)


def pool(value):
    return BufferPool(value, (SEMANTIC,))


class ModularBufferTests(unittest.TestCase):
    def assert_code(self, code, function, *args):
        with self.assertRaises(BufferError) as caught:
            function(*args)
        self.assertEqual(caught.exception.code, code)

    def test_independent_base64_grammar_and_boundaries(self):
        for raw, encoded in [(b"f", "Zg=="), (b"fo", "Zm8="), (b"foo", "Zm9v")]:
            self.assertEqual(encode_chunk(raw), encoded)
            self.assertEqual(decode_chunk(encoded), raw)
        for length in [1, 2, 3, CHUNK_BYTES - 1, CHUNK_BYTES]:
            raw = bytes(i % 251 for i in range(length))
            self.assertEqual(decode_chunk(encode_chunk(raw)), raw)
        for bad in ["", "Zg", "Zh==", "Zm9=", "Zg===", "Zg==\n", "Zg==AAAA", "-w==", "_w==", "é===", "AA=A", "===="]:
            with self.subTest(bad=bad):
                self.assert_code("wire", decode_chunk, bad)
        self.assert_code("capacity", encode_chunk, bytes(CHUNK_BYTES + 1))
        self.assert_code("wire", decode_chunk, "A" * (((CHUNK_BYTES + 2) // 3) * 4))

    def test_installed_semantic_roster_and_host_field_bounds(self):
        owner = binding()
        full = tuple(f"{i:064x}" for i in range(SEMANTIC_SLOTS))
        self.assertEqual(BufferPool(owner, full).usage().live_slots, 0)
        for bad in [(), full + (f"{SEMANTIC_SLOTS:064x}",), (SEMANTIC, SEMANTIC), ("6" * 64, SEMANTIC), ("A" * 64,)]:
            self.assert_code("binding", BufferPool, owner, bad)
        self.assert_code("binding", TrustedHostCreationContext, owner, "3" * 63, None)
        self.assert_code("binding", TrustedHostCreationContext, owner, "3" * 64, "4" * 63)

    def test_owned_snapshot_and_complete_context_join(self):
        owner = binding()
        producer = pool(owner)
        source = bytes([1, 2, 3])
        manifest = producer.publish(context(owner), SEMANTIC, source)
        manifest.verify(owner)
        self.assertIsNot(producer._entries[1].payload, source)
        self.assertEqual(producer.read(manifest.reference(), 0).decoded(), source)
        self.assertEqual(manifest.creating_request_digest, "3" * 64)
        self.assertEqual(manifest.causal_predecessor, "4" * 64)
        self.assertNotIn("result_digest", asdict(manifest))
        self.assertLessEqual(len(json.dumps(asdict(manifest)).encode()), MANIFEST_BYTES)
        self.assert_code("wire", producer.publish, context(owner), SEMANTIC, bytearray(b"mutable"))

    def test_context_and_semantic_rejections_preserve_counter_and_bytes(self):
        owner = binding()
        producer = pool(owner)
        manifest = producer.publish(context(owner), SEMANTIC, b"preserve")
        for field in ["profile_digest", "application_digest", "generation", "endpoint_id", "run_id"]:
            with self.subTest(field=field):
                wrong = replace(owner, **{field: "6" * 64 if field.endswith("digest") else TARGET})
                before = producer.usage()
                self.assert_code("binding", producer.publish, context(wrong), SEMANTIC, b"x")
                self.assertEqual(producer.usage(), before)
                self.assertEqual(producer.read(manifest.reference(), 0).decoded(), b"preserve")
        before = producer.usage()
        self.assert_code("binding", producer.publish, context(owner), "6" * 64, b"x")
        self.assert_code("capacity", producer.publish, context(owner), SEMANTIC, b"")
        self.assertEqual(producer.usage(), before)

    def test_manifest_and_closed_chunk_wire_admission(self):
        owner = binding()
        producer = pool(owner)
        manifest = producer.publish(context(owner), SEMANTIC, b"x")
        self.assertEqual(BufferManifest.from_json(json.dumps(asdict(manifest)).encode(), owner), manifest)
        self.assert_code("conflict", replace(manifest, creating_request_digest="6" * 64).verify, owner)
        self.assert_code("binding", manifest.verify, binding(TARGET))
        extra = {**asdict(manifest), "result_digest": "6" * 64}
        self.assert_code("wire", BufferManifest.from_json, json.dumps(extra).encode(), owner)
        chunk = producer.read(manifest.reference(), 0)
        wire = chunk.to_json().decode()
        self.assertEqual(BufferChunk.from_json(wire.encode()), chunk)
        malformed = [wire.replace("{", '{"index":0,', 1),
                     wire.replace('"index":0', '"index":-0'),
                     wire.replace('"index":0', '"index":0.0'),
                     wire.replace('"index":0', '"index":true'),
                     wire.replace('"index":0', '"index":9007199254740992'),
                     wire.replace('"index":0', '"index":"\\ud800"'),
                     wire.replace("{", '{"path":"/tmp/not-a-handle",', 1)]
        for case in malformed:
            self.assert_code("wire", BufferChunk.from_json, case.encode())
        padded = wire.encode() + b" " * (FRAME_BYTES - len(wire))
        self.assertEqual(BufferChunk.from_json(padded), chunk)
        self.assert_code("capacity", BufferChunk.from_json, padded + b" ")

    def test_import_prefix_and_sealing_account_for_both_owners(self):
        source, target = binding(), binding(TARGET)
        producer, receiver = pool(source), pool(target)
        payload = bytes(i % 251 for i in range(CHUNK_BYTES + 7))
        manifest = producer.publish(context(source), SEMANTIC, payload)
        handle = receiver.begin_import(context(target), manifest, source)
        self.assertEqual(producer.usage().reserved_bytes + receiver.usage().reserved_bytes, len(payload) * 2)
        before = receiver.usage()
        self.assert_code("state", receiver.seal, handle)
        self.assert_code("state", receiver.read, handle, 0)
        self.assert_code("conflict", receiver.append, handle, producer.read(manifest.reference(), 1))
        first = producer.read(manifest.reference(), 0)
        receiver.append(handle, first)
        self.assert_code("conflict", receiver.append, handle, first)
        corrupt = replace(producer.read(manifest.reference(), 1), chunk_sha256="0" * 64)
        self.assert_code("conflict", receiver.append, handle, corrupt)
        self.assertEqual(receiver.usage(), before)
        receiver.append(handle, producer.read(manifest.reference(), 1))
        imported = receiver.seal(handle)
        self.assertEqual(imported.imported_manifest_digest, manifest.manifest_digest)
        self.assertEqual(receiver.usage().reserved_bytes, before.reserved_bytes)
        self.assertEqual(receiver.usage().live_slots, before.live_slots)
        self.assertEqual(receiver.usage().incomplete_slots, 0)
        self.assertEqual(b"".join(receiver.read(handle, i).decoded() for i in range(imported.chunk_count)), payload)
        self.assert_code("state", receiver.abort_import, handle)
        receiver.release(handle)
        self.assert_code("unavailable", receiver.release, handle)
        self.assertEqual(receiver.usage().next_id, 2)
        self.assertEqual(producer.usage().reserved_bytes, len(payload))

    def test_valid_chunk_hash_cannot_hide_wrong_complete_payload(self):
        source, target = binding(), binding(TARGET)
        producer, receiver = pool(source), pool(target)
        manifest = producer.publish(context(source), SEMANTIC, b"x")
        other = producer.publish(context(source), SEMANTIC, b"y")
        handle = receiver.begin_import(context(target), manifest, source)
        forged = replace(producer.read(other.reference(), 0), manifest_digest=manifest.manifest_digest)
        receiver.append(handle, forged)
        before = receiver.usage()
        self.assert_code("conflict", receiver.seal, handle)
        self.assertEqual(receiver.usage(), before)
        self.assert_code("state", receiver.read, handle, 0)
        receiver.abort_import(handle)
        fresh = receiver.begin_import(context(target), manifest, source)
        receiver.append(fresh, producer.read(manifest.reference(), 0))
        receiver.seal(fresh)

    def test_named_abort_never_reuses_id_or_discards_another_import(self):
        source, target = binding(), binding(TARGET)
        producer, receiver = pool(source), pool(target)
        manifest = producer.publish(context(source), SEMANTIC, b"x")
        first = receiver.begin_import(context(target), manifest, source)
        second = receiver.begin_import(context(target), manifest, source)
        before = receiver.usage()
        self.assert_code("state", receiver.release, first)
        self.assert_code("binding", receiver.abort_import, manifest.reference())
        self.assertEqual(receiver.usage(), before)
        receiver.abort_import(first)
        self.assert_code("unavailable", receiver.abort_import, first)
        receiver.append(second, producer.read(manifest.reference(), 0))
        receiver.seal(second)
        self.assertEqual(receiver.begin_import(context(target), manifest, source).buffer_id, 3)

    def test_exact_payload_and_slot_budgets(self):
        owner = binding()
        producer = pool(owner)
        maximum = b"\x07" * BUFFER_BYTES
        before = producer.usage()
        self.assert_code("capacity", producer.publish, context(owner), SEMANTIC, maximum + b"x")
        self.assertEqual(producer.usage(), before)
        for _ in range(ENDPOINT_BYTES // BUFFER_BYTES):
            producer.publish(context(owner), SEMANTIC, maximum)
        before = producer.usage()
        self.assert_code("capacity", producer.publish, context(owner), SEMANTIC, b"x")
        self.assertEqual(producer.usage(), before)
        self.assertEqual(producer.read(BufferRef(SOURCE, 1), 255).decoded(), b"\x07" * CHUNK_BYTES)
        small = pool(owner)
        for _ in range(LIVE_SLOTS):
            small.publish(context(owner), SEMANTIC, b"x")
        before = small.usage()
        self.assert_code("capacity", small.publish, context(owner), SEMANTIC, b"x")
        self.assertEqual(small.usage(), before)

    def test_incomplete_and_total_slots_use_same_budget(self):
        source, target = binding(), binding(TARGET)
        producer, receiver = pool(source), pool(target)
        manifest = producer.publish(context(source), SEMANTIC, b"x")
        for _ in range(INCOMPLETE_SLOTS):
            receiver.begin_import(context(target), manifest, source)
        before = receiver.usage()
        self.assert_code("capacity", receiver.begin_import, context(target), manifest, source)
        self.assertEqual(receiver.usage(), before)
        for _ in range(LIVE_SLOTS - INCOMPLETE_SLOTS):
            receiver.publish(context(target), SEMANTIC, b"x")
        self.assertEqual(receiver.usage().live_slots, LIVE_SLOTS)
        self.assert_code("capacity", receiver.publish, context(target), SEMANTIC, b"x")

    def test_counter_exhaustion_fails_before_admission(self):
        owner = binding()
        producer = pool(owner)
        producer._next_id = MAX_ID
        last = producer.publish(context(owner), SEMANTIC, b"x")
        self.assertEqual(last.buffer_id, MAX_ID)
        producer.release(last.reference())
        before = producer.usage()
        self.assert_code("capacity", producer.publish, context(owner), SEMANTIC, b"x")
        self.assertEqual(producer.usage(), before)

    def test_composition_reservations_count_source_and_receiver_separately(self):
        self.assertEqual(admit_composition((ENDPOINT_BYTES,) * 4), COMPOSITION_BYTES)
        self.assertEqual(admit_composition((1,) * ENDPOINTS), ENDPOINTS)
        self.assertEqual(admit_composition((0,) * ENDPOINTS), 0)
        for bad in [(1,) * (ENDPOINTS + 1), (0,) * (ENDPOINTS + 1), (ENDPOINT_BYTES,) * 4 + (1,), (ENDPOINT_BYTES + 1,), (-1,), (True,)]:
            self.assert_code("capacity", admit_composition, bad)


if __name__ == "__main__":
    unittest.main()
