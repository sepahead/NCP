"""Selected structural owner controls, independently executed in Rust and Python.

The fixed order below is test selection, not a random scientific sample.
The native process uses a test-only counter contract and owns no external engine.
"""
from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "local/python/tests"))

from ncp_local import modular_wire as w
from ncp_local import modular_owner as o
from ncp_local import wire as framing
from ncp_local.modular_client import Client
from ncp_local.modular_buffer import BufferPool, TrustedHostCreationContext
from ncp_local.modular_buffer import _manifest_digest
from modular_fixture import Counter, Initial, Add, Finish, Import, SEMANTIC, binding


class OwnerParity(unittest.TestCase):
    def setUp(self):
        binary = Path(os.environ.get("NCP_MODULAR_OWNER_PROBE", ROOT / "target/debug/examples/modular_owner_probe"))
        self.peer = subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env={"PATH": "/usr/bin:/bin", "LANG": "C"})
        self.owner = o.Owner(binding(), Counter(), (SEMANTIC,))
        self.client = Client(binding(), Counter)
        self.exchanges = 0

    def tearDown(self):
        self.peer.stdin.close()
        try: self.peer.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.peer.kill(); self.peer.wait(timeout=3)
        diagnostics = self.peer.stderr.read().decode("utf-8", "replace")
        self.peer.stdout.close(); self.peer.stderr.close()
        self.assertEqual(self.peer.returncode, 0, diagnostics)

    def exchange(self, request):
        expected = bytes(self.owner.process(request))
        deadline = time.monotonic() + 5
        framing.write_local_frame(self.peer.stdin, request, deadline=deadline)
        actual = framing.read_local_frame(self.peer.stdout, deadline=deadline)
        self.assertIsNotNone(actual)
        # Field order is not wire identity. Both independent typed digests must agree.
        self.assertEqual(w.parse(actual), w.parse(expected))
        self.assertEqual(w.Response.decode(actual, binding(), Counter).result_digest,
                         w.Response.decode(expected, binding(), Counter).result_digest)
        self.exchanges += 1
        return actual

    def call(self, operation):
        request = self.client.begin(operation)
        response = self.client.observe(self.exchange(request))
        if response.outcome == w.Outcome.COMMITTED:
            self.client.observe_acknowledgement(self.exchange(self.client.acknowledgement()))
        return response

    def test_selected_execution_replay_queries_ack_and_buffer_lifetimes(self):
        request = self.client.begin(w.Prepare(Initial(7)))
        response = self.exchange(request)
        self.assertEqual(self.exchange(request), response)
        query = self.client.result_query()
        self.client.observe_query(self.exchange(query))
        old_ack = self.client.acknowledgement()
        self.client.observe_acknowledgement(self.exchange(old_ack))
        self.assertEqual(self.call(w.Application(Add(0, 0))).outcome, w.Outcome.REJECTED)
        output = self.call(w.Application(Add(1, 32_775))).body.data.manifest
        for index in (0, 1):
            response = self.call(w.Read(output.reference(), output.manifest_digest, index))
            self.assertEqual(response.body.data.decoded(), bytes(i % 251 for i in range(index * 32_768, min(output.byte_length, (index + 1) * 32_768))))
        self.assertEqual(self.call(w.Read(output.reference(), "f" * 64, 0)).outcome, w.Outcome.REJECTED)
        self.assertEqual(self.call(w.Finish(Finish(False, False))).code, w.Code.STATE)
        self.call(w.Release(output.reference()))
        self.assertEqual(self.call(w.Read(output.reference(), output.manifest_digest, 0)).code, w.Code.BUFFER_UNAVAILABLE)
        self.call(w.Finish(Finish(False, False)))
        self.assertEqual(self.owner.usage.live_slots, 0)
        self.assertEqual(self.owner.lifecycle, o.Lifecycle.FINISHED)

    def test_import_metadata_exact_bound_24_slots_and_25th_rejection(self):
        self.call(w.Prepare(Initial(7)))
        source_binding = dataclasses.replace(binding(), generation="44444444-4444-4444-8444-444444444444")
        pool = BufferPool(source_binding, (SEMANTIC,))
        source = pool.publish(TrustedHostCreationContext(source_binding, "b" * 64, None), SEMANTIC, b"abc")
        record = {"source_manifest_digest": source.manifest_digest, "source_descriptor_digest": "0" * 64,
                  "data": {"byte_length": 3, "label": ""}}
        maximum_label = "x" * (1_024 - len(w.encode(record)))
        self.assertEqual(len(w.encode({**record, "data": {"byte_length": 3, "label": maximum_label}})), 1_024)
        before = self.owner.usage
        rejected = self.call(w.ImportBegin(Import(source, source_binding, maximum_label + "x")))
        self.assertEqual(rejected.code, w.Code.CAPACITY)
        self.assertEqual(self.owner.usage, before)
        references = []
        for index in range(24):
            label = maximum_label if index == 0 else str(index)
            result = self.call(w.ImportBegin(Import(source, source_binding, label)))
            reference = result.body.data
            references.append(reference)
            request = self.client.begin(w.Append(reference, pool.read(source.reference(), 0)))
            response = self.exchange(request)
            # Prefix changed; duplicate must still return exact retained bytes.
            self.assertEqual(self.exchange(request), response)
            self.client.observe(response)
            self.client.observe_acknowledgement(self.exchange(self.client.acknowledgement()))
            sealed = self.call(w.Seal(reference, result.request_digest, source.manifest_digest))
            self.assertEqual(sealed.body.data.data.label, label)
            received = self.call(w.Read(reference, sealed.body.data.manifest.manifest_digest, 0))
            self.assertEqual(received.body.data.decoded(), b"abc")
        before = self.owner.usage
        self.assertEqual((before.live_slots, before.incomplete_slots), (24, 0))
        self.assertEqual(self.call(w.ImportBegin(Import(source, source_binding, "25"))).code, w.Code.CAPACITY)
        self.assertEqual(self.owner.usage, before)
        for reference in references: self.call(w.Release(reference))
        self.assertEqual(self.owner.usage.live_slots, 0)
        self.assertFalse(any(self.owner._imports))
        self.call(w.Finish(Finish(False, False)))

    def test_seal_provenance_joins_reject_coherently_rehashed_substitutions(self):
        self.call(w.Prepare(Initial(7)))
        source_binding = dataclasses.replace(binding(), generation="44444444-4444-4444-8444-444444444444")
        pool = BufferPool(source_binding, (SEMANTIC,))
        source = pool.publish(TrustedHostCreationContext(source_binding, "b" * 64, None), SEMANTIC, b"abc")
        imported = self.call(w.ImportBegin(Import(source, source_binding, "source-bound")))
        reference = imported.body.data
        self.call(w.Append(reference, pool.read(source.reference(), 0)))
        before = self.owner.usage
        for creating, origin in (("0" * 64, source.manifest_digest), (imported.request_digest, "0" * 64)):
            rejection = self.call(w.Seal(reference, creating, origin))
            self.assertEqual(rejection.outcome, w.Outcome.REJECTED)
            self.assertEqual(self.owner.usage, before)
        request = self.client.begin(w.Seal(reference, imported.request_digest, source.manifest_digest))
        parsed = w.Request.decode(request, binding(), Counter)
        actual = self.exchange(request)
        # Recompute both manifest and outer response hashes: integrity alone must not pass.
        alterations = (("creating_request_digest", "0" * 64), ("imported_manifest_digest", "0" * 64), ("buffer_id", reference.buffer_id + 1))
        for field, changed in alterations:
            with self.subTest(field=field):
                row = w.parse(actual)
                manifest = row["body"]["manifest"]
                manifest[field] = changed
                manifest["manifest_digest"] = _manifest_digest(manifest)
                row["result_digest"] = w.typed_digest(w.RESPONSE_SCHEMA, row, "result_digest")
                with self.assertRaises(ValueError): o.verify_response(binding(), parsed, w.encode(row), Counter)
        row = w.parse(actual)
        manifest = row["body"]["manifest"]
        manifest["binding"]["generation"] = source_binding.generation
        manifest["manifest_digest"] = _manifest_digest(manifest)
        row["result_digest"] = w.typed_digest(w.RESPONSE_SCHEMA, row, "result_digest")
        with self.assertRaises(ValueError): o.verify_response(binding(), parsed, w.encode(row), Counter)
        self.client.observe(actual)
        self.client.observe_acknowledgement(self.exchange(self.client.acknowledgement()))
        self.call(w.Release(reference))
        self.call(w.Finish(Finish(False, False)))


if __name__ == "__main__": unittest.main()
