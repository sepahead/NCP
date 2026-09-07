import dataclasses
import hashlib
import io
import math
import struct
import sys
import weakref
import time
import unittest
from unittest.mock import patch

from ncp_local import modular_wire as w
from ncp_local import modular_owner as o
from ncp_local.modular_client import Client
from ncp_local.modular_buffer import BufferPool, TrustedHostCreationContext, OutputReservation, BufferError
from ncp_local.modular_buffer import MAX_ID, InputSpec, OutputSpec
from ncp_local import wire as framing
from modular_fixture import Counter, Initial, Add, Special, Finish, Import, Output, Imported, Terminal, SEMANTIC, binding


class OwnerTests(unittest.TestCase):
    def setup(self):
        application = Counter()
        return o.Owner(binding(), application, (SEMANTIC,)), Client(binding(), Counter), application

    def run_call(self, owner, client, operation):
        request = client.begin(operation)
        response = client.observe(owner.process(request))
        if response.outcome == w.Outcome.COMMITTED:
            client.observe_acknowledgement(owner.process(client.acknowledgement()))
        return response

    def prepare(self, owner, client): self.run_call(owner, client, w.Prepare(Initial(7)))

    def test_failed_exception_is_released_before_diagnostic_projection(self):
        owner, client, application = self.setup(); self.prepare(owner, client)
        class FailedOutput: pass
        weak = []
        def fail(operation, permit):
            application.calls += 1
            output = FailedOutput()
            weak.append(weakref.ref(output))
            raise RuntimeError(output)
        original_emit = owner._emit
        observed = []
        def inspect(*args, **kwargs):
            if args[1] == w.Outcome.INDETERMINATE:
                observed.append((sys.exception() is None, weak[0]() is None))
            return original_emit(*args, **kwargs)
        with patch.object(application, "execute", fail), patch.object(owner, "_emit", inspect):
            response = self.run_call(owner, client, w.Application(Add(1, 0)))
        self.assertEqual(response.outcome, w.Outcome.INDETERMINATE)
        self.assertEqual(observed, [(True, True)])
        self.assertEqual((owner.high_water, application.calls), (2, 2))
        owner, client, _ = self.setup(); self.prepare(owner, client)
        self.assertEqual(self.run_call(owner, client, w.Application(Add(1, 0))).outcome, w.Outcome.COMMITTED)

    def test_prepare_replay_and_exact_ack_sequence(self):
        owner, client, application = self.setup()
        request = client.begin(w.Prepare(Initial(7)))
        first = bytes(owner.process(request))
        self.assertEqual(bytes(owner.process(request)), first)
        self.assertEqual(application.calls, 1)
        client.observe(first)
        self.assertEqual(client.next_sequence, 1)
        ack = client.acknowledgement()
        client.observe_acknowledgement(owner.process(ack))
        self.assertEqual(client.next_sequence, 2)
        self.assertEqual(w.Response.decode(owner.process(request), binding(), Counter).outcome, w.Outcome.UNAVAILABLE)

    def test_clean_rejection_preserves_head_and_allows_corrected_same_sequence(self):
        owner, client, application = self.setup(); self.prepare(owner, client)
        head = client.predecessor
        response = self.run_call(owner, client, w.Application(Add(0, 0)))
        self.assertEqual(response.outcome, w.Outcome.REJECTED)
        self.assertIsNone(client.pending_request)
        self.assertEqual((client.next_sequence, client.predecessor, application.calls, owner.high_water), (2, head, 1, 1))
        self.assertEqual(self.run_call(owner, client, w.Application(Add(1, 0))).outcome, w.Outcome.COMMITTED)

    def test_post_execution_faults_do_not_become_clean_rejection(self):
        for action in ("panic", "backend_error", "invalid_output", "omit_output", "ignore_write_error"):
            with self.subTest(action=action):
                owner, client, application = self.setup(); self.prepare(owner, client)
                response = self.run_call(owner, client, w.Application(Special(action)))
                self.assertEqual(response.outcome, w.Outcome.INDETERMINATE)
                self.assertEqual((owner.high_water, owner.lifecycle, application.calls), (2, o.Lifecycle.RETIRED, 2))
                self.assertTrue(client.is_retired)
                self.assertIsNotNone(client.pending_request)
        owner, client, application = self.setup(); self.prepare(owner, client)
        with patch.object(application, "execute", side_effect=o.AdmissionError(w.Code.INVALID)):
            response = self.run_call(owner, client, w.Application(Add(1, 0)))
        self.assertEqual(response.outcome, w.Outcome.INDETERMINATE)

    def test_application_admission_cannot_redefine_installed_role(self):
        owner, client, application = self.setup(); self.prepare(owner, client)
        result = self.run_call(owner, client, w.Application(Special("admission_role")))
        self.assertEqual((result.outcome, result.code), (w.Outcome.REJECTED, w.Code.INVALID))
        self.assertEqual((application.calls, owner.high_water), (1, 1))
        self.assertEqual(self.run_call(owner, client, w.Application(Add(1, 0))).outcome, w.Outcome.COMMITTED)

    def test_unknown_ticket_cleanup_retires_without_claiming_released_capacity(self):
        owner, client, application = self.setup(); self.prepare(owner, client)
        with patch.object(OutputReservation, "close", side_effect=BufferError("state")):
            result = self.run_call(owner, client, w.Application(Add(1, 4)))
        self.assertEqual(result.outcome, w.Outcome.INDETERMINATE)
        self.assertEqual((owner.high_water, application.calls, owner.lifecycle), (2, 2, o.Lifecycle.RETIRED))
        self.assertEqual((owner.usage.live_slots, owner.usage.reserved_bytes), (1, 4))
        self.assertIsNotNone(owner._pool._ticket)
        self.assertTrue(client.is_retired)
        self.assertIsNotNone(client.pending_request)
        healthy, healthy_client, _ = self.setup(); self.prepare(healthy, healthy_client)
        result = self.run_call(healthy, healthy_client, w.Application(Add(1, 4)))
        self.assertEqual(result.outcome, w.Outcome.COMMITTED)
        self.assertIsNone(healthy._pool._ticket)

    def test_finish_cannot_allocate_output_and_normal_terminal_is_bounded(self):
        owner, client, application = self.setup(); self.prepare(owner, client)
        self.assertEqual(self.run_call(owner, client, w.Finish(Finish(False, True))).code, w.Code.CAPACITY)
        self.assertEqual(application.calls, 1)
        self.assertEqual(self.run_call(owner, client, w.Finish(Finish(True, False))).outcome, w.Outcome.INDETERMINATE)
        owner, client, _ = self.setup(); self.prepare(owner, client)
        self.assertEqual(self.run_call(owner, client, w.Finish(Finish(False, False))).outcome, w.Outcome.COMMITTED)
        self.assertEqual((owner.lifecycle, owner.usage.live_slots), (o.Lifecycle.FINISHED, 0))

    def test_buffer_lifetime_read_join_and_release_replay(self):
        owner, client, _ = self.setup(); self.prepare(owner, client)
        result = self.run_call(owner, client, w.Application(Add(1, 4)))
        source = result.body.data.manifest
        self.assertEqual(owner.usage.live_slots, 1)
        self.assertEqual(self.run_call(owner, client, w.Finish(Finish(False, False))).code, w.Code.STATE)
        self.assertEqual(self.run_call(owner, client, w.Read(source.reference(), "0" * 64, 0)).outcome, w.Outcome.REJECTED)
        good = self.run_call(owner, client, w.Read(source.reference(), source.manifest_digest, 0))
        self.assertEqual(good.body.data.decoded(), bytes(range(4)))
        request = client.begin(w.Release(source.reference()))
        result = bytes(owner.process(request))
        self.assertEqual(owner.usage.live_slots, 0)
        self.assertEqual(bytes(owner.process(request)), result)
        client.observe(result); client.observe_acknowledgement(owner.process(client.acknowledgement()))
        self.assertEqual(self.run_call(owner, client, w.Read(source.reference(), source.manifest_digest, 0)).code, w.Code.BUFFER_UNAVAILABLE)

    def test_metadata_capacity_and_atomic_failure_before_import_promotion(self):
        owner, client, _ = self.setup(); self.prepare(owner, client)
        source_binding = dataclasses.replace(binding(), generation="44444444-4444-4444-8444-444444444444")
        pool = BufferPool(source_binding, (SEMANTIC,))
        source = pool.publish(TrustedHostCreationContext(source_binding, "b" * 64, None), SEMANTIC, b"abc")
        before = owner.usage
        response = self.run_call(owner, client, w.ImportBegin(Import(source, source_binding, "x" * 1_000)))
        self.assertEqual(response.code, w.Code.CAPACITY)
        self.assertEqual(owner.usage, before)
        with patch("ncp_local.modular_owner.bytearray", side_effect=MemoryError):
            response = self.run_call(owner, client, w.ImportBegin(Import(source, source_binding, "")))
        self.assertEqual(response.code, w.Code.CAPACITY)
        self.assertEqual(owner.usage, before)
        response = self.run_call(owner, client, w.ImportBegin(Import(source, source_binding, "owned")))
        reference = response.body.data
        self.assertEqual(owner.usage.incomplete_slots, 1)
        self.run_call(owner, client, w.Append(reference, pool.read(source.reference(), 0)))
        sealed = self.run_call(owner, client, w.Seal(reference, response.request_digest, source.manifest_digest))
        self.assertEqual(sealed.body.data.data.label, "owned")
        read = self.run_call(owner, client, w.Read(reference, sealed.body.data.manifest.manifest_digest, 0))
        self.assertEqual(read.body.data.decoded(), b"abc")
        self.assertEqual(owner.usage.incomplete_slots, 0)
        self.run_call(owner, client, w.Release(reference))
        self.assertEqual(owner.usage.live_slots, 0)
        self.assertFalse(any(owner._imports))

    def test_omitted_predecessor_and_mutated_typed_request_rejected(self):
        owner, client, _ = self.setup()
        request = client.begin(w.Prepare(Initial(7)))
        parsed = w.Request.decode(request, binding(), Counter)
        altered = dataclasses.replace(parsed, command=w.Execute(None, w.Prepare(Initial(8))))
        response = bytes(owner.process(request))
        with self.assertRaises(w.ModularError): o.verify_response(binding(), altered, response, Counter)
        row = w.parse(request)
        del row["command"]["expected_predecessor_result_digest"]
        row["request_digest"] = w.typed_digest(w.REQUEST_SCHEMA, row, "request_digest")
        owner, _, _ = self.setup()
        with self.assertRaises(w.ModularError): owner.process(w.encode(row))
        self.assertEqual(owner.high_water, 0)

    def test_lost_response_preserves_pending_and_forbids_retry(self):
        _, client, _ = self.setup()
        request = client.begin(w.Prepare(Initial(7)))
        with self.assertRaises(w.ModularError): client.dispatch(io.BytesIO(), io.BytesIO(), deadline=time.monotonic() + 1)
        self.assertTrue(client.is_retired)
        self.assertEqual(client.pending_request, request)
        with self.assertRaises(w.ModularError): client.result_query()

    def test_outgoing_closed_codecs_precede_commit_in_every_application_slot(self):
        for phase in ("prepare", "application", "import", "finish"):
            for value, expected in ((7, w.Outcome.COMMITTED), (True, w.Outcome.INDETERMINATE),
                                    (float("nan"), w.Outcome.INDETERMINATE),
                                    (float("inf"), w.Outcome.INDETERMINATE),
                                    (-float("inf"), w.Outcome.INDETERMINATE)):
                with self.subTest(phase=phase, value=value):
                    owner, client, application = self.setup()
                    if phase != "prepare": self.prepare(owner, client)
                    if phase == "import":
                        source_binding = dataclasses.replace(binding(), generation="44444444-4444-4444-8444-444444444444")
                        pool = BufferPool(source_binding, (SEMANTIC,))
                        source = pool.publish(TrustedHostCreationContext(source_binding, "b" * 64, None), SEMANTIC, b"abc")
                        reserved = self.run_call(owner, client, w.ImportBegin(Import(source, source_binding, "input")))
                        self.run_call(owner, client, w.Append(reserved.body.data, pool.read(source.reference(), 0)))
                        operation = w.Seal(reserved.body.data, reserved.request_digest, source.manifest_digest)
                        replacement = Imported(value, "input")
                        target = "validate_import"
                    else:
                        operation = {"prepare": w.Prepare(Initial(7)), "application": w.Application(Add(1, 0)),
                                     "finish": w.Finish(Finish(False, False))}[phase]
                        replacement = o.TerminalResult(Terminal(value)) if phase == "finish" else o.ApplicationResult(Output(value, None))
                        target = "execute"
                    entered = owner.high_water + 1
                    request = client.begin(operation)
                    observed_calls = []
                    def backend_result(*args):
                        observed_calls.append(True)
                        return replacement
                    with patch.object(application, target, side_effect=backend_result):
                        wire = bytes(owner.process(request))
                    response = client.observe(wire)
                    self.assertEqual(response.outcome, expected)
                    self.assertEqual(owner.high_water, entered)
                    self.assertEqual(len(observed_calls), 1)
                    self.assertEqual(bytes(owner.process(request)), wire)
                    if expected == w.Outcome.INDETERMINATE:
                        self.assertEqual(owner.lifecycle, o.Lifecycle.RETIRED)
                        self.assertTrue(client.is_retired)
                        self.assertIsNotNone(client.pending_request)
                    else:
                        client.observe_acknowledgement(owner.process(client.acknowledgement()))
                        self.assertEqual(owner.lifecycle, o.Lifecycle.FINISHED if phase == "finish" else o.Lifecycle.ACTIVE)

    def test_outgoing_finite_optional_values_preserve_binary64_bits(self):
        @dataclasses.dataclass(frozen=True, slots=True)
        class Number:
            value: float | None
        class Numeric(Counter):
            @staticmethod
            def decode_result(value):
                row = w.closed(value, {"value"})
                if row["value"] is not None and type(row["value"]) is not float: raise w.ModularError("wire")
                return Number(row["value"])
            decode_imported = decode_result
            decode_terminal = decode_result
            @staticmethod
            def check_response(*args): pass
        import struct
        for value in (1.25, -0.0, 0.0, float.fromhex("0x0.0000000000001p-1022"), None):
            with self.subTest(value=value):
                application = Numeric()
                owner = o.Owner(binding(), application, (SEMANTIC,))
                client = Client(binding(), Numeric)
                request = client.begin(w.Prepare(Initial(7)))
                with patch.object(application, "execute", return_value=o.ApplicationResult(Number(value))):
                    response = client.observe(owner.process(request))
                self.assertEqual(response.outcome, w.Outcome.COMMITTED)
                observed = response.body.data.value
                self.assertEqual(None if observed is None else struct.pack(">d", observed), None if value is None else struct.pack(">d", value))
                client.observe_acknowledgement(owner.process(client.acknowledgement()))

    def test_outgoing_normalizing_decoder_has_no_commit_authority(self):
        owner, client, application = self.setup()
        original_decoder = Counter.decode_result
        def normalize(value):
            decoded = original_decoder(value)
            return dataclasses.replace(decoded, value=decoded.value + 1)
        with patch.object(Counter, "decode_result", side_effect=normalize):
            request = client.begin(w.Prepare(Initial(7)))
            response = client.observe(owner.process(request))
        self.assertEqual(response.outcome, w.Outcome.INDETERMINATE)
        self.assertEqual((owner.high_water, application.calls, owner.lifecycle), (1, 1, o.Lifecycle.RETIRED))
        healthy, healthy_client, _ = self.setup()
        self.assertEqual(self.run_call(healthy, healthy_client, w.Prepare(Initial(7))).outcome, w.Outcome.COMMITTED)

    def test_maximum_sequence_ack_exhausts_without_wrapping(self):
        owner, client, application = self.setup()
        owner._high_water = MAX_ID - 1
        client._next_sequence = MAX_ID
        self.prepare(owner, client)
        self.assertEqual((owner.high_water, application.calls), (MAX_ID, 1))
        self.assertIsNone(client.next_sequence)
        with self.assertRaises(w.ModularError): client.begin(w.Application(Add(1, 0)))
        self.assertIsNone(client.pending_request)

    def test_each_owner_frame_allocation_failure_precedes_execution(self):
        for position in range(2):
            application = Counter()
            count = 0
            def allocate(length):
                nonlocal count
                if count == position: raise MemoryError
                count += 1
                return bytearray(length)
            with patch("ncp_local.modular_owner.bytearray", side_effect=allocate):
                with self.assertRaises(MemoryError): o.Owner(binding(), application, (SEMANTIC,))
            self.assertEqual(application.calls, 0)
            owner = o.Owner(binding(), application, (SEMANTIC,))
            self.prepare(owner, Client(binding(), Counter))
            self.assertEqual(application.calls, 1)

    def test_eof_and_failed_response_write_retire_with_precise_known_prefix(self):
        owner, client, application = self.setup()
        o.serve(owner, io.BytesIO(), io.BytesIO(), deadline=time.monotonic() + 1)
        self.assertEqual((owner.lifecycle, application.calls), (o.Lifecycle.RETIRED, 0))
        self.assertIsNone(owner.retained)
        owner, client, application = self.setup()
        request = client.begin(w.Prepare(Initial(7)))
        input_frame = io.BytesIO()
        framing.write_local_frame(input_frame, request)
        class BrokenWriter(io.BytesIO):
            def write(self, data):
                if self.tell() >= 4: raise OSError("selected output fault")
                return super().write(data)
        with self.assertRaises(OSError): o.serve(owner, io.BytesIO(input_frame.getvalue()), BrokenWriter(), deadline=time.monotonic() + 1)
        self.assertEqual((owner.lifecycle, owner.high_water, application.calls), (o.Lifecycle.RETIRED, 1, 1))
        self.assertEqual(w.Response.decode(owner.retained, binding(), Counter).outcome, w.Outcome.COMMITTED)
        with self.assertRaises(w.ModularError): owner.process(request)

    def test_lost_ack_preserves_pending_and_forbids_operational_retry(self):
        owner, client, _ = self.setup()
        request = client.begin(w.Prepare(Initial(7)))
        client.observe(owner.process(request))
        with self.assertRaises(w.ModularError): client.dispatch_acknowledgement(io.BytesIO(), io.BytesIO(), deadline=time.monotonic() + 1)
        self.assertEqual(client.pending_request, request)
        self.assertTrue(client.is_retired)
        with self.assertRaises(w.ModularError): client.acknowledgement()


@dataclasses.dataclass(frozen=True, slots=True)
class TensorImport:
    manifest: object
    source: object
    shape: tuple[int, int]
    dtype: str

@dataclasses.dataclass(frozen=True, slots=True)
class TensorMetadata:
    shape: tuple[int, int]
    dtype: str

@dataclasses.dataclass(frozen=True, slots=True)
class TensorCommand:
    inputs: tuple[InputSpec, ...]
    output_bytes: int
    action: str

@dataclasses.dataclass(frozen=True, slots=True)
class TensorResult:
    accumulated_sum: float
    source_manifests: tuple[str, ...]
    output_manifest: object


class TensorConsumer(Counter):
    """Closed test consumer computes from imported f32 bytes during execution."""
    def __init__(self):
        super().__init__()
        self.total = 0.0
        self.view = None
        self.raw_view = None
    @staticmethod
    def descriptor(): return b'{"schema":"ncp.test.tensor-consumer.python.v1","status":"test-only","dtype":"f32le","operation":"sum_then_accumulate"}'
    @staticmethod
    def decode_import(value):
        from modular_fixture import manifest
        from ncp_local.modular_buffer import BufferBinding
        row = w.closed(value, {"manifest", "source", "shape", "dtype"})
        shape = TensorConsumer._shape(row["shape"], row["dtype"])
        source = BufferBinding(**w.closed(row["source"], set(BufferBinding.__dataclass_fields__)))
        return TensorImport(manifest(row["manifest"]), source, shape, row["dtype"])
    @staticmethod
    def _shape(value, dtype):
        if type(value) is not list or len(value) != 2 or any(not w.integer(item, 1, 64) for item in value) or dtype != "f32le": raise w.ModularError("wire")
        return tuple(value)
    @staticmethod
    def decode_metadata(value):
        row = w.closed(value, {"shape", "dtype"})
        return TensorMetadata(TensorConsumer._shape(row["shape"], row["dtype"]), row["dtype"])
    @staticmethod
    def decode_command(value):
        row = w.closed(value, {"inputs", "output_bytes", "action"})
        if type(row["inputs"]) is not list or len(row["inputs"]) > 25 or type(row["output_bytes"]) is not int or row["output_bytes"] not in (0, 4): raise w.ModularError("wire")
        if row["action"] not in ("sum", "read_unnamed", "ignore_read_error"): raise w.ModularError("wire")
        selected = []
        for value in row["inputs"]:
            item = w.closed(value, {"reference", "expected_manifest_digest"})
            selected.append(InputSpec(w._reference(item["reference"]), item["expected_manifest_digest"]))
        return TensorCommand(tuple(selected), row["output_bytes"], row["action"])
    @staticmethod
    def decode_result(value):
        from modular_fixture import manifest
        row = w.closed(value, {"accumulated_sum", "source_manifests", "output_manifest"})
        if type(row["accumulated_sum"]) is not float or not math.isfinite(row["accumulated_sum"]) or type(row["source_manifests"]) is not list or len(row["source_manifests"]) > 24 or any(not w.digest_valid(x) for x in row["source_manifests"]): raise w.ModularError("wire")
        return TensorResult(row["accumulated_sum"], tuple(row["source_manifests"]), manifest(row["output_manifest"]) if row["output_manifest"] is not None else None)
    decode_imported = decode_result
    decode_terminal = decode_result
    @staticmethod
    def check_input(operation):
        if type(operation) is w.ImportBegin:
            item = operation.data
            if item.manifest.byte_length != math.prod(item.shape) * 4: raise w.ModularError("wire")
    @staticmethod
    def check_response(operation, body, context):
        if body.kind == w.BodyKind.APPLICATION and type(operation) is w.Application and operation.data.action == "sum":
            if body.data.source_manifests != tuple(x.expected_manifest_digest for x in operation.data.inputs): raise w.ModularError("binding")
            output = body.data.output_manifest
            if (output.byte_length if output else 0) != operation.data.output_bytes: raise w.ModularError("binding")
            if output:
                output.verify(context.binding)
                if output.creating_request_digest != context.request_digest or output.causal_predecessor != context.predecessor: raise w.ModularError("binding")
    @staticmethod
    def check_import_metadata(descriptor, metadata):
        if metadata.shape != descriptor.shape or metadata.dtype != descriptor.dtype: raise w.ModularError("binding")
    def split_import(self, descriptor):
        return o.ImportSource(descriptor.manifest, descriptor.source, TensorMetadata(descriptor.shape, descriptor.dtype))
    def validate_import(self, metadata, manifest, payload):
        if len(payload) != math.prod(metadata.shape) * 4 or any(not math.isfinite(x[0]) for x in struct.iter_unpack("<f", payload)): raise o.AdmissionError(w.Code.INVALID)
        return TensorResult(self.total, (), None)
    def admit(self, operation, view):
        if type(operation) is w.Application:
            data = operation.data
            return o.AdmissionDemand(data.inputs, (OutputSpec(SEMANTIC, data.output_bytes),) if data.output_bytes else ())
        return o.AdmissionDemand()
    def execute(self, operation, permit):
        self.calls += 1
        manifests = []
        if type(operation) is w.Application:
            data = operation.data
            if data.action in ("read_unnamed", "ignore_read_error"):
                try: permit.input(len(data.inputs))
                except BufferError:
                    if data.action == "read_unnamed": raise
            views = tuple(permit.input(index) for index in range(len(data.inputs)))
            for self.view in views:
                self.raw_view = self.view.payload
                self.total += sum(x[0] for x in struct.iter_unpack("<f", self.view.payload))
                manifests.append(self.view.manifest.manifest_digest)
        output = None
        if type(operation) is w.Application and operation.data.output_bytes:
            try: payload = struct.pack("<f", self.total)
            except (OverflowError, struct.error) as error: raise o.ExecutionError("invalid_output") from error
            if not math.isfinite(struct.unpack("<f", payload)[0]): raise o.ExecutionError("invalid_output")
            permit.write_output(0, 0, payload)
            output = permit.seal_output(0)
        result = TensorResult(self.total, tuple(manifests), output)
        return o.TerminalResult(result) if type(operation) is w.Finish else o.ApplicationResult(result)


class InputLeaseTests(unittest.TestCase):
    def setup(self):
        selected = dataclasses.replace(binding(), application_digest=w.typed_digest(w.PROFILE_DOMAIN, w.parse(TensorConsumer.descriptor())))
        application = TensorConsumer()
        owner = o.Owner(selected, application, (SEMANTIC,))
        client = Client(selected, TensorConsumer)
        self.call(owner, client, w.Prepare(Initial(0)))
        return owner, client, application
    def call(self, owner, client, operation):
        request = client.begin(operation)
        response = client.observe(owner.process(request))
        if response.outcome == w.Outcome.COMMITTED:
            client.observe_acknowledgement(owner.process(client.acknowledgement()))
        return response
    def import_tensor(self, owner, client, payload, *, seal=True):
        source_binding = dataclasses.replace(owner.binding, generation="44444444-4444-4444-8444-444444444444")
        pool = BufferPool(source_binding, (SEMANTIC,))
        source = pool.publish(TrustedHostCreationContext(source_binding, "b" * 64, None), SEMANTIC, payload)
        reserved = self.call(owner, client, w.ImportBegin(TensorImport(source, source_binding, (2, 3), "f32le")))
        reference = reserved.body.data
        self.call(owner, client, w.Append(reference, pool.read(source.reference(), 0)))
        if not seal: return reference, reserved, source, pool
        result = self.call(owner, client, w.Seal(reference, reserved.request_digest, source.manifest_digest))
        self.assertEqual(result.outcome, w.Outcome.COMMITTED)
        return result.body.data.manifest
    def test_actual_tensor_consumption_coherent_change_and_expiring_view(self):
        owner, client, application = self.setup()
        original = struct.pack("<6f", 1, 2, 3, 4, 5, 6)
        changed = bytearray(original); changed[2] ^= 0x10
        delta = struct.unpack("<f", changed[:4])[0] - 1.0
        totals = []
        for payload in (original, bytes(changed)):
            manifest = self.import_tensor(owner, client, payload)
            before = application.total
            response = self.call(owner, client, w.Application(TensorCommand((InputSpec(manifest.reference(), manifest.manifest_digest),), 0, "sum")))
            self.assertEqual(response.outcome, w.Outcome.COMMITTED)
            self.assertEqual(response.body.data.source_manifests, (manifest.manifest_digest,))
            totals.append(response.body.data.accumulated_sum - before)
            self.assertTrue(application.raw_view.readonly)
            with self.assertRaises(BufferError): _ = application.view.payload
            with self.assertRaises(BufferError): _ = application.view.manifest
            # Raw borrowed views cannot be revoked by Python. Application retention
            # here is a diagnostic outside the SDK lifetime contract.
            self.assertEqual(application.raw_view.tobytes(), payload)
            application.view = None; application.raw_view = None
            self.call(owner, client, w.Release(manifest.reference()))
        self.assertEqual(totals, [21.0, 21.0 + delta])
        self.assertNotEqual(totals[0], totals[1])
        first = self.import_tensor(owner, client, original)
        second = self.import_tensor(owner, client, bytes(changed))
        selected = tuple(InputSpec(m.reference(), m.manifest_digest) for m in (first, second))
        response = self.call(owner, client, w.Application(TensorCommand(selected, 0, "sum")))
        self.assertEqual(response.body.data.accumulated_sum, 84.0 + 2.0 * delta)
        self.assertEqual(response.body.data.source_manifests, (first.manifest_digest, second.manifest_digest))
        application.view = None; application.raw_view = None
        for manifest in (first, second): self.call(owner, client, w.Release(manifest.reference()))
        self.assertEqual(self.call(owner, client, w.Finish(Finish(False, False))).outcome, w.Outcome.COMMITTED)
    def test_finite_input_sum_cannot_publish_nonfinite_f32_output(self):
        for overflowing in (False, True):
            owner, client, application = self.setup()
            payload = struct.pack("<6f", *([3e38] * 6 if overflowing else [1, 2, 3, 4, 5, 6]))
            manifest = self.import_tensor(owner, client, payload)
            selected = (InputSpec(manifest.reference(), manifest.manifest_digest),)
            sequence = owner.high_water + 1
            response = self.call(owner, client, w.Application(TensorCommand(selected, 4, "sum")))
            self.assertEqual(response.outcome, w.Outcome.INDETERMINATE if overflowing else w.Outcome.COMMITTED)
            self.assertEqual((owner.high_water, application.calls), (sequence, 2))
            self.assertTrue(math.isfinite(application.total))
            if overflowing:
                self.assertGreater(application.total, float.fromhex("0x1.fffffep127"))
                self.assertEqual(owner.lifecycle, o.Lifecycle.RETIRED)
                self.assertTrue(client.is_retired)
                self.assertEqual((owner.usage.live_slots, owner.usage.reserved_bytes), (1, 24))
    def test_input_admission_rejects_stale_released_incomplete_wrong_and_duplicate_before_effect(self):
        for fault in ("generation", "unknown", "released", "incomplete", "digest", "duplicate", "roster", "outputs", "metadata"):
            with self.subTest(fault=fault):
                owner, client, application = self.setup()
                payload = struct.pack("<6f", 1, 2, 3, 4, 5, 6)
                if fault == "incomplete":
                    reference, reserved, source, _ = self.import_tensor(owner, client, payload, seal=False)
                    digest = source.manifest_digest
                else:
                    manifest = self.import_tensor(owner, client, payload)
                    reference, digest = manifest.reference(), manifest.manifest_digest
                if fault == "generation": reference = dataclasses.replace(reference, generation="55555555-5555-4555-8555-555555555555")
                if fault == "unknown": reference = dataclasses.replace(reference, buffer_id=900)
                if fault == "released": self.call(owner, client, w.Release(reference))
                if fault == "digest": digest = "f" * 64
                selected = (InputSpec(reference, digest),)
                if fault == "duplicate": selected *= 2
                if fault == "roster": selected *= 25
                if fault == "outputs":
                    # Existing sealed imports fill every slot before output demand.
                    for _ in range(23): self.import_tensor(owner, client, payload)
                before = (owner.high_water, owner.usage, application.calls, application.total)
                operation = w.Application(TensorCommand(selected, 4 if fault == "outputs" else 0, "sum"))
                if fault == "metadata":
                    with patch("ncp_local.modular_buffer.asdict", side_effect=MemoryError):
                        response = self.call(owner, client, operation)
                else: response = self.call(owner, client, operation)
                self.assertEqual(response.outcome, w.Outcome.REJECTED)
                self.assertEqual((owner.high_water, owner.usage, application.calls, application.total), before)
                self.assertFalse(client.is_retired)
        healthy, healthy_client, _ = self.setup()
        manifest = self.import_tensor(healthy, healthy_client, struct.pack("<6f", 1, 2, 3, 4, 5, 6))
        self.assertEqual(self.call(healthy, healthy_client, w.Application(TensorCommand((InputSpec(manifest.reference(), manifest.manifest_digest),), 0, "sum"))).outcome, w.Outcome.COMMITTED)
    def test_changed_chunk_and_nonfinite_tensor_keep_incomplete_capacity_until_abort(self):
        from ncp_local.modular_buffer import encode_chunk
        for fault in ("changed_byte", "nonfinite"):
            owner, client, application = self.setup()
            payload = struct.pack("<6f", *(float("nan") if index == 0 and fault == "nonfinite" else index + 1 for index in range(6)))
            source_binding = dataclasses.replace(owner.binding, generation="44444444-4444-4444-8444-444444444444")
            pool = BufferPool(source_binding, (SEMANTIC,))
            source = pool.publish(TrustedHostCreationContext(source_binding, "b" * 64, None), SEMANTIC, payload)
            reserved = self.call(owner, client, w.ImportBegin(TensorImport(source, source_binding, (2, 3), "f32le")))
            chunk = pool.read(source.reference(), 0)
            if fault == "changed_byte":
                changed = bytearray(payload); changed[2] ^= 0x10
                chunk = dataclasses.replace(chunk, chunk_sha256=hashlib.sha256(changed).hexdigest(), data_base64=encode_chunk(bytes(changed)))
            self.call(owner, client, w.Append(reserved.body.data, chunk))
            before = (owner.high_water, owner.usage, application.calls, application.total)
            rejected = self.call(owner, client, w.Seal(reserved.body.data, reserved.request_digest, source.manifest_digest))
            self.assertEqual(rejected.outcome, w.Outcome.REJECTED)
            self.assertEqual((owner.high_water, owner.usage, application.calls, application.total), before)
            self.assertEqual((owner.usage.incomplete_slots, owner.usage.reserved_bytes), (1, 24))
            self.call(owner, client, w.BufferAbort(reserved.body.data))
            self.assertEqual(owner.usage.live_slots, 0)
            healthy = self.import_tensor(owner, client, struct.pack("<6f", 1, 2, 3, 4, 5, 6))
            result = self.call(owner, client, w.Application(TensorCommand((InputSpec(healthy.reference(), healthy.manifest_digest),), 4, "sum")))
            self.assertEqual(result.outcome, w.Outcome.COMMITTED)
            output = result.body.data.output_manifest
            read = self.call(owner, client, w.Read(output.reference(), output.manifest_digest, 0))
            self.assertEqual(struct.unpack("<f", read.body.data.decoded())[0], 21.0)
    def test_finish_cannot_demand_inputs_and_cleanup_failure_cannot_extend_borrow(self):
        owner, client, application = self.setup()
        manifest = self.import_tensor(owner, client, struct.pack("<6f", 1, 2, 3, 4, 5, 6))
        spec = InputSpec(manifest.reference(), manifest.manifest_digest)
        before = (owner.high_water, owner.usage, application.calls)
        with patch.object(application, "admit", return_value=o.AdmissionDemand(inputs=(spec,))):
            result = self.call(owner, client, w.Finish(Finish(False, False)))
        self.assertEqual(result.outcome, w.Outcome.REJECTED)
        self.assertEqual((owner.high_water, owner.usage, application.calls), before)
        with patch.object(OutputReservation, "close", side_effect=BufferError("state")):
            result = self.call(owner, client, w.Application(TensorCommand((spec,), 0, "sum")))
        self.assertEqual(result.outcome, w.Outcome.INDETERMINATE)
        with self.assertRaises(BufferError): _ = application.view.payload
        healthy, healthy_client, _ = self.setup()
        self.assertEqual(self.call(healthy, healthy_client, w.Finish(Finish(False, False))).outcome, w.Outcome.COMMITTED)

    def test_unnamed_input_and_ignored_failure_retire_after_entry(self):
        for action in ("read_unnamed", "ignore_read_error"):
            owner, client, application = self.setup()
            before = owner.high_water
            response = self.call(owner, client, w.Application(TensorCommand((), 0, action)))
            self.assertEqual(response.outcome, w.Outcome.INDETERMINATE)
            self.assertEqual(owner.high_water, before + 1)
            self.assertEqual(owner.lifecycle, o.Lifecycle.RETIRED)
            self.assertTrue(client.is_retired)

if __name__ == "__main__": unittest.main()
