"""Mandatory separate-process Rust/Python primitive comparisons.

Build local/rust's modular_buffer_probe before running. Missing probes fail.
The fixture probe is not an application owner or an NCP envelope endpoint.
"""

from dataclasses import asdict, replace
import json
import hashlib
import os
from pathlib import Path
import random
import subprocess
import time
import unittest

from ncp_local import modular_buffer as sdk
from ncp_local.wire import read_local_frame, write_local_frame

ROOT = Path(__file__).resolve().parents[2]
PLAN = json.loads((Path(__file__).parent / "primitive-bounds.v1.json").read_bytes())
PROBE = Path(os.environ.get("NCP_MODULAR_PROBE", ROOT / "local/rust/target/debug/examples/modular_buffer_probe"))
SOURCE = sdk.BufferBinding("1" * 64, "2" * 64,
                          "10000000-0000-4000-8000-000000000001",
                          "10000000-0000-4000-8000-000000000002",
                          "10000000-0000-4000-8000-000000000003")
TARGET = replace(SOURCE, generation="10000000-0000-4000-8000-000000000004")
SEMANTIC = "5" * 64


def probe(value):
    result = subprocess.run([str(PROBE)], input=json.dumps(value, separators=(",", ":")).encode(),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=True)
    if len(result.stdout) > 262_144:
        raise AssertionError("probe output exceeded its test-only bound")
    return json.loads(result.stdout)


def context(binding):
    return sdk.TrustedHostCreationContext(binding, "3" * 64, "4" * 64)


class ModularParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not PROBE.is_file():
            raise AssertionError("build the mandatory modular_buffer_probe before running parity")
        # Freeze every selected byte vector before examining any native result.
        random_source = random.Random(PLAN["parity_selection"]["seed"])
        cls.payloads = tuple(bytes(random_source.randrange(256) for _ in range(length))
                             for length in PLAN["parity_selection"]["payload_lengths"])

    def test_declared_bounds_match_python(self):
        for key, value in PLAN["limits"].items():
            self.assertEqual(getattr(sdk, key), value)
        self.assertFalse(PLAN["request_owner_implemented"])
        self.assertFalse(PLAN["application_qualification"])
        self.assertEqual(probe({"operation": "bounds"}), {"ok": PLAN["limits"]})

    def test_exact_manifests_and_two_owner_payloads(self):
        for payload in self.payloads:
            with self.subTest(length=len(payload)):
                producer = sdk.BufferPool(SOURCE, (SEMANTIC,))
                receiver = sdk.BufferPool(TARGET, (SEMANTIC,))
                source = producer.publish(context(SOURCE), SEMANTIC, payload)
                handle = receiver.begin_import(context(TARGET), source, SOURCE)
                for index in range(source.chunk_count):
                    chunk = producer.read(source.reference(), index)
                    native = probe({"operation": "chunk", "wire": chunk.to_json().decode()})
                    self.assertEqual(native, {"ok": {"chunk": asdict(chunk)}})
                    receiver.append(handle, sdk.BufferChunk.from_json(chunk.to_json()))
                destination = receiver.seal(handle)
                self.assertEqual(b"".join(receiver.read(handle, i).decoded() for i in range(destination.chunk_count)), payload)
                native = probe({"operation": "transfer", "data_hex": payload.hex(),
                                "binding": asdict(SOURCE), "target": asdict(TARGET),
                                "request_digest": "3" * 64, "predecessor": "4" * 64,
                                "semantic_digest": SEMANTIC})
                expected = {"source": asdict(source), "destination": asdict(destination),
                            "source_reserved_bytes": len(payload), "destination_reserved_bytes": len(payload)}
                self.assertEqual(native, {"ok": expected})
                for manifest, owner in [(source, SOURCE), (destination, TARGET)]:
                    wire = json.dumps(asdict(manifest))
                    self.assertEqual(probe({"operation": "manifest", "wire": wire, "binding": asdict(owner)}),
                                     {"ok": {"manifest": asdict(manifest)}})
                    self.assertEqual(sdk.BufferManifest.from_json(wire.encode(), owner), manifest)

    def test_independent_base64_negative_controls(self):
        cases = ["", "Zg", "Zh==", "Zm9=", "Zg===", "Zg==\n", "Zg==AAAA", "-w==", "_w==", "é===", "AA=A", "====",
                 "A" * (((sdk.CHUNK_BYTES + 2) // 3) * 4)]
        for value in cases:
            with self.subTest(value=value[:24]):
                self.assertEqual(probe({"operation": "decode", "data_base64": value}), {"error": "wire"})
                with self.assertRaises(sdk.BufferError) as caught:
                    sdk.decode_chunk(value)
                self.assertEqual(caught.exception.code, "wire")
        for payload in self.payloads[:-1]:
            encoded = sdk.encode_chunk(payload)
            self.assertEqual(probe({"operation": "decode", "data_base64": encoded}), {"ok": {"hex": payload.hex()}})

    def test_closed_fields_integer_grammar_and_manifest_tampering(self):
        producer = sdk.BufferPool(SOURCE, (SEMANTIC,))
        manifest = producer.publish(context(SOURCE), SEMANTIC, b"x")
        chunk = producer.read(manifest.reference(), 0)
        wire = chunk.to_json().decode()
        malformed = [wire.replace("{", '{"index":0,', 1),
                     wire.replace('"index":0', '"index":-0'),
                     wire.replace('"index":0', '"index":0.0'),
                     wire.replace('"index":0', '"index":true'),
                     wire.replace('"index":0', '"index":9007199254740992'),
                     wire.replace('"index":0', '"index":"\\ud800"'),
                     wire.replace("{", '{"path":"/tmp/not-a-handle",', 1)]
        for text in malformed:
            self.assertEqual(probe({"operation": "chunk", "wire": text}), {"error": "wire"})
            with self.assertRaises(sdk.BufferError) as caught:
                sdk.BufferChunk.from_json(text.encode())
            self.assertEqual(caught.exception.code, "wire")
        for field in ["creating_request_digest", "semantic_digest", "payload_sha256", "causal_predecessor"]:
            tampered = replace(manifest, **{field: "6" * 64})
            wire = json.dumps(asdict(tampered))
            self.assertEqual(probe({"operation": "manifest", "wire": wire, "binding": asdict(SOURCE)}), {"error": "conflict"})
            with self.assertRaises(sdk.BufferError) as caught:
                sdk.BufferManifest.from_json(wire.encode(), SOURCE)
            self.assertEqual(caught.exception.code, "conflict")
        for field in SOURCE.__dataclass_fields__:
            wrong = replace(SOURCE, **{field: "6" * 64 if field.endswith("digest") else TARGET.generation})
            wire = json.dumps(asdict(manifest))
            self.assertEqual(probe({"operation": "manifest", "wire": wire, "binding": asdict(wrong)}), {"error": "binding"})

    def test_separately_selected_maximum_transfer_and_changed_final_chunk(self):
        # Additional structural boundary, separate from the frozen small-vector roster.
        # This deterministic fixture is neither scientific evidence nor a benchmark.
        payload = bytes(range(251)) * (sdk.BUFFER_BYTES // 251) + bytes(range(sdk.BUFFER_BYTES % 251))
        expected_hash = hashlib.sha256(payload).hexdigest()
        for changed_final_chunk in [False, True]:
            with self.subTest(changed_final_chunk=changed_final_chunk):
                producer = sdk.BufferPool(SOURCE, (SEMANTIC,))
                manifest = producer.publish(context(SOURCE), SEMANTIC, payload)
                self.assertEqual(manifest.chunk_count, 256)
                process = subprocess.Popen([str(PROBE), "--maximum-import-control"], stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                deadline = time.monotonic() + 45

                def send(frame):
                    write_local_frame(process.stdin, frame, deadline=deadline)

                def receive():
                    raw = read_local_frame(process.stdout, deadline=deadline)
                    self.assertIsNotNone(raw)
                    return raw

                try:
                    send(json.dumps(asdict(manifest), separators=(",", ":")).encode())
                    reserved = json.loads(receive())["reservation"]
                    self.assertEqual(reserved, {"reserved_bytes": sdk.BUFFER_BYTES, "live_slots": 1, "incomplete_slots": 1, "next_id": 2})
                    for index in range(256):
                        chunk = producer.read(manifest.reference(), index)
                        if changed_final_chunk and index == 255:
                            changed = bytearray(chunk.decoded())
                            changed[-1] ^= 1
                            changed = bytes(changed)
                            # Preserve a valid per-chunk digest; only the full payload join is false.
                            chunk = replace(chunk, data_base64=sdk.encode_chunk(changed), chunk_sha256=hashlib.sha256(changed).hexdigest())
                        send(chunk.to_json())
                        self.assertEqual(json.loads(receive()), {"accepted_index": index, "accepted_bytes": (index + 1) * sdk.CHUNK_BYTES})
                    sealed = json.loads(receive())
                    if changed_final_chunk:
                        self.assertEqual(sealed, {"seal_error": "conflict", "usage": reserved})
                        self.assertEqual(json.loads(receive()), {"aborted": {"reserved_bytes": 0, "live_slots": 0, "incomplete_slots": 0, "next_id": 2}})
                    else:
                        target = sdk.BufferManifest.from_json(json.dumps(sealed["sealed"]).encode(), TARGET)
                        self.assertEqual(target.payload_sha256, expected_hash)
                        self.assertEqual(target.imported_manifest_digest, manifest.manifest_digest)
                        self.assertEqual(target.creating_request_digest, "3" * 64)
                        self.assertEqual(sealed["usage"], {**reserved, "incomplete_slots": 0})
                        received_hash = hashlib.sha256()
                        for index in range(256):
                            chunk = sdk.BufferChunk.from_json(receive())
                            self.assertEqual(chunk.manifest_digest, target.manifest_digest)
                            self.assertEqual(chunk.index, index)
                            raw = chunk.decoded()
                            self.assertEqual(raw, payload[index * sdk.CHUNK_BYTES:(index + 1) * sdk.CHUNK_BYTES])
                            received_hash.update(raw)
                        self.assertEqual(received_hash.hexdigest(), expected_hash)
                        self.assertEqual(json.loads(receive()), {"released": {"reserved_bytes": 0, "live_slots": 0, "incomplete_slots": 0, "next_id": 2}, "duplicate_release_unavailable": True})
                    self.assertEqual(producer.usage().reserved_bytes, sdk.BUFFER_BYTES)
                    producer.release(manifest.reference())
                    self.assertEqual(producer.usage().reserved_bytes, 0)
                    self.assertEqual(producer.usage().next_id, 2)
                    process.stdin.close()
                    self.assertIsNone(read_local_frame(process.stdout, deadline=deadline))
                    self.assertEqual(process.wait(timeout=5), 0)
                    self.assertEqual(process.stderr.read(), b"")
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=5)
                    for stream in (process.stdin, process.stdout, process.stderr):
                        stream.close()


if __name__ == "__main__":
    unittest.main()
