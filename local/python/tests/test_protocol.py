"""Native controls for the independent local SDK, including real private pipes."""

import copy
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from ncp_local import (
    BoundedJsonError,
    LocalBinding,
    LocalClient,
    LocalError,
    LocalPreflightError,
    LocalOwner,
    MAX_FRAME_BYTES,
    MAX_SEQUENCE,
    decode,
    digest_without,
    encode,
    local_digest,
    make_request,
    profile_descriptor_bytes,
    profile_digest,
    read_local_frame,
    serve_local,
    verify_integrity,
    verify_response,
    verify_retrieved,
    write_local_frame,
)


class CounterBackend:
    def __init__(self):
        self.executions = 0
        self.retires = 0

    def validate(self, operation, body):
        if type(body) is not dict:
            raise LocalError("invalid_input")
        if "reject" in body:
            raise LocalError(body["reject"])

    def execute(self, operation, body):
        self.executions += 1
        fault = body.get("fault")
        if fault == "exception":
            raise RuntimeError("controlled backend failure after mutation")
        if fault == "interrupt":
            raise KeyboardInterrupt()
        if fault == "oversize":
            return {"data": "x" * MAX_FRAME_BYTES}
        if fault == "unsupported_value":
            return {"data": object()}
        if fault == "many_nodes":
            return [0] * 16_384
        if fault == "deep":
            value = None
            for _ in range(34):
                value = [value]
            return value
        return {"count": self.executions, "value": body}

    def retire(self):
        self.retires += 1


def fixed_binding(role="body"):
    return LocalBinding(
        profile_digest(),
        "10c99b86-c8e0-4b94-80ae-8cec74456e2a",
        "748d5ab4-51c1-408f-b144-a27602edc823",
        role,
    )


class WireTests(unittest.TestCase):
    def test_rejects_before_generic_object_materialization(self):
        cases = [
            b'{"a":1,"\\u0061":2}',
            b'{"x":"\\ud800"}',
            b'{"x":"\\udfff"}',
            b'{"x":"\xff"}',
            b'{"x":NaN}',
            b'{"x":1e301}',
            b'{"x":9007199254740992}',
            b'{"x":-9007199254740992}',
            b"[" * 33 + b"0" + b"]" * 33,
            b" " * (MAX_FRAME_BYTES + 1),
            b'{"' + b"x" * 129 + b'":1}',
            b'{"x":01}',
            b'{"x":1}{}',
        ]
        for payload in cases:
            with self.subTest(payload=payload[:60]):
                with patch(
                    "ncp_local.wire.json.loads",
                    side_effect=AssertionError("tree decoder ran"),
                ):
                    with self.assertRaises(LocalError):
                        decode(payload)
        self.assertEqual(
            decode(b'{"a":9007199254740991,"b":-9007199254740991}'),
            {"a": MAX_SEQUENCE, "b": -MAX_SEQUENCE},
        )
        self.assertEqual(decode(b'"\\ud83d\\ude80"'), "🚀")
        self.assertEqual(decode(b'{"' + b"x" * 128 + b'":0}'), {"x" * 128: 0})
        self.assertIsNone(
            decode(b"[" * 32 + b"null" + b"]" * 32)[0][0][0][0][0][0][0][0][0][0][0][0][
                0
            ][0][0][0][0][0][0][0][0][0][0][0][0][0][0][0][0][0][0][0]
        )

    def test_decoded_unicode_identity_and_member_budget(self):
        with self.assertRaises(BoundedJsonError):
            decode('{"🚀":1,"\\ud83d\\ude80":2}'.encode())
        valid = {f"k{i}": 0 for i in range(4096)}
        self.assertEqual(len(decode(encode(valid))), 4096)
        oversized = b"{" + b",".join(f'"k{i}":0'.encode() for i in range(4097)) + b"}"
        with patch(
            "ncp_local.wire.json.loads", side_effect=AssertionError("tree decoder ran")
        ):
            with self.assertRaises(LocalError):
                decode(oversized)

    def test_negative_zero_and_exact_typed_digest_domains(self):
        negative = decode(b'{"v":-0}')
        self.assertEqual(math.copysign(1, negative["v"]), -1)
        domain = "ncp.local.snapshot.v1"
        self.assertEqual(
            local_digest(domain, negative), local_digest(domain, {"v": -0.0})
        )
        self.assertNotEqual(
            local_digest(domain, negative), local_digest(domain, {"v": 0.0})
        )
        self.assertEqual(
            local_digest(domain, {"a": 1, "β": [True, None]}),
            local_digest(domain, {"β": [True, None], "a": 1.0}),
        )
        self.assertNotEqual(
            local_digest(domain, [1]), local_digest("ncp.local.plan.v1", [1])
        )
        with self.assertRaises(LocalError):
            local_digest("ncp.unregistered.v1", {})

    def test_frame_length_is_checked_before_payload_read(self):
        class HeaderOnly(io.BytesIO):
            def read(self, count=-1):
                if self.tell() >= 4:
                    raise AssertionError("unbounded payload was read")
                return super().read(count)

        for length in (0, MAX_FRAME_BYTES + 1, 2**32 - 1):
            with self.assertRaises(LocalError):
                read_local_frame(HeaderOnly(struct.pack(">I", length)))
        self.assertIsNone(read_local_frame(io.BytesIO()))
        for payload in (b"x", b"y" * MAX_FRAME_BYTES):
            stream = io.BytesIO()
            write_local_frame(stream, payload)
            stream.seek(0)
            self.assertEqual(read_local_frame(stream), payload)
        for truncated in (b"\0", b"\0\0\0\x02x"):
            with self.assertRaises(LocalError):
                read_local_frame(io.BytesIO(truncated))

    def test_programmatic_non_json_or_unbounded_values_fail(self):
        for value in (
            float("nan"),
            float("inf"),
            MAX_SEQUENCE + 1,
            {1: "key"},
            {"x": object()},
            "\ud800",
            "x" * (MAX_FRAME_BYTES + 1),
        ):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(LocalError):
                    encode(value)
        self.assertEqual(
            decode(encode({"x": [True, -0.0, 1e300]})), {"x": [True, -0.0, 1e300]}
        )

    def test_bundled_descriptor_matches_rust_source_when_available(self):
        source = Path(__file__).resolve().parents[3] / "ncp-core/local-profile.v1.json"
        if source.exists():
            self.assertEqual(profile_descriptor_bytes(), source.read_bytes())
        self.assertEqual(len(profile_digest()), 64)


class OwnerTests(unittest.TestCase):
    def setUp(self):
        self.binding = fixed_binding()
        self.backend = CounterBackend()
        self.owner = LocalOwner(self.binding, self.backend)

    def send(self, sequence, operation, body):
        request = make_request(self.binding, sequence, operation, body)
        return request, decode(self.owner.handle(encode(request)))

    def ack(self, response):
        request, ack = self.send(
            response["sequence"], "ack", {"result_digest": response["result_digest"]}
        )
        verify_response(ack, self.binding, request)
        self.assertEqual(ack["outcome"], "acknowledged")
        return request, ack

    def test_exact_retry_lookup_ack_and_no_reexecution(self):
        request = make_request(self.binding, 1, "prepare", {"v": -0.0})
        first = self.owner.handle(encode(request))
        self.assertEqual(first, self.owner.handle(encode(request)))
        query = make_request(
            self.binding, 1, "result", {"request_digest": request["request_digest"]}
        )
        self.assertEqual(first, self.owner.handle(encode(query)))
        response = decode(first)
        verify_response(response, self.binding, request)
        verify_retrieved(response, self.binding, request, query)
        with self.assertRaises(LocalError):
            verify_response(response, self.binding, query)
        ack_request, ack = self.ack(response)
        self.assertEqual(self.owner.retained_bytes, 0)
        self.assertEqual(decode(self.owner.handle(encode(ack_request))), ack)
        released = decode(self.owner.handle(encode(query)))
        verify_response(released, self.binding, query)
        self.assertEqual(released["outcome"], "unavailable")
        self.assertEqual(
            decode(self.owner.handle(encode(request)))["outcome"], "unavailable"
        )
        self.assertEqual(self.backend.executions, 1)

    def test_pending_changed_retry_and_wrong_ack_do_not_mutate(self):
        _, first = self.send(1, "prepare", {})
        self.assertEqual(
            self.send(1, "prepare", {"changed": True})[1]["code"], "conflict"
        )
        self.assertEqual(self.send(2, "step", {})[1]["code"], "result_pending")
        self.assertEqual(
            self.send(1, "ack", {"result_digest": "0" * 64})[1]["code"], "conflict"
        )
        self.assertEqual(self.backend.executions, 1)
        self.ack(first)
        self.assertEqual(self.send(2, "step", {})[1]["outcome"], "committed")

    def test_invalid_before_execution_keeps_next_position(self):
        for code in (
            "invalid_input",
            "ok",
            "execution_unknown",
            "result_released",
            "made_up",
        ):
            request, response = self.send(1, "prepare", {"reject": code})
            verify_response(response, self.binding, request)
            self.assertEqual(response["code"], "invalid_input")
        self.assertEqual(self.backend.executions, 0)
        self.assertEqual(self.send(1, "prepare", {})[1]["outcome"], "committed")

    def test_post_mutation_failures_retire_and_remain_exactly_queryable(self):
        for fault in (
            "exception",
            "interrupt",
            "oversize",
            "unsupported_value",
            "deep",
            "many_nodes",
        ):
            with self.subTest(fault=fault):
                backend = CounterBackend()
                owner = LocalOwner(self.binding, backend)
                request = make_request(self.binding, 1, "prepare", {"fault": fault})
                payload = owner.handle(encode(request))
                response = decode(payload)
                verify_response(response, self.binding, request)
                self.assertEqual(response["outcome"], "indeterminate")
                self.assertEqual(owner.handle(encode(request)), payload)
                self.assertLess(owner.retained_bytes, 1024)
                ack = make_request(
                    self.binding, 1, "ack", {"result_digest": response["result_digest"]}
                )
                owner.handle(encode(ack))
                next_request = make_request(self.binding, 2, "prepare", {})
                self.assertEqual(
                    decode(owner.handle(encode(next_request)))["code"], "retired"
                )
                owner.retire_generation()
                self.assertEqual((backend.executions, backend.retires), (1, 1))

    def test_role_and_launch_identity_cannot_be_selected_by_payload(self):
        binding = fixed_binding("monitor")
        backend = CounterBackend()
        owner = LocalOwner(binding, backend)
        request = make_request(binding, 1, "step", {})
        response = decode(owner.handle(encode(request)))
        verify_response(response, binding, request)
        self.assertEqual(response["code"], "role")
        valid = make_request(binding, 1, "prepare", {})
        for field in ("run_id", "generation", "profile_digest"):
            changed = copy.deepcopy(valid)
            changed[field] = (
                "0" * 64
                if field == "profile_digest"
                else "64789f06-e732-4db0-9b05-9563c5699813"
            )
            changed["request_digest"] = digest_without(
                "ncp.local.request.v1", changed, "request_digest"
            )
            self.assertEqual(decode(owner.handle(encode(changed)))["code"], "binding")
        self.assertEqual(backend.executions, 0)
        self.assertEqual(decode(owner.handle(encode(valid)))["outcome"], "committed")
        for field, value in (
            ("profile_digest", "0" * 64),
            ("role", "gate"),
            ("generation", binding.generation.upper()),
        ):
            row = binding.as_dict()
            row[field] = value
            with self.assertRaises(LocalError):
                LocalBinding.from_dict(row)

    def test_sequence_spelling_and_closed_envelopes_fail_before_mutation(self):
        request = make_request(self.binding, 1, "prepare", {})
        for value in (0, -0.0, 1.0, True, MAX_SEQUENCE + 1):
            altered = copy.deepcopy(request)
            altered["sequence"] = value
            with self.assertRaises(LocalError):
                self.owner.handle(encode(altered))
        for payload in (b"[]", b'{"x":1,"x":2}', b'{"x":"\\ud800"}'):
            with self.assertRaises(LocalError):
                self.owner.handle(payload)
        altered = copy.deepcopy(request)
        altered["extra"] = 0
        altered["request_digest"] = digest_without(
            "ncp.local.request.v1", altered, "request_digest"
        )
        with self.assertRaises(LocalError):
            self.owner.handle(encode(altered))
        self.assertEqual(self.backend.executions, 0)
        self.assertEqual(
            decode(self.owner.handle(encode(request)))["outcome"], "committed"
        )

    def test_parallel_identical_retries_have_one_owner_execution(self):
        request = encode(make_request(self.binding, 1, "prepare", {}))
        output = []
        threads = [
            threading.Thread(target=lambda: output.append(self.owner.handle(request)))
            for _ in range(12)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(output), 12)
        self.assertEqual(len(set(output)), 1)
        self.assertEqual(self.backend.executions, 1)

    def test_all_server_exits_retire_including_clean_eof(self):
        for input_bytes in (b"", b"\0", b"\0\0\0\0", b"\0\1\0\1"):
            backend = CounterBackend()
            owner = LocalOwner(self.binding, backend)
            try:
                serve_local(owner, io.BytesIO(input_bytes), io.BytesIO())
            except LocalError:
                pass
            request = make_request(self.binding, 1, "prepare", {})
            self.assertEqual(decode(owner.handle(encode(request)))["code"], "retired")
            self.assertEqual((backend.executions, backend.retires), (0, 1))

    def test_tampered_body_and_forged_success_kind_fail(self):
        request, response = self.send(1, "prepare", {})
        changed = copy.deepcopy(response)
        changed["body"] = {"faked": True}
        with self.assertRaises(LocalError):
            verify_response(changed, self.binding, request)
        changed = copy.deepcopy(response)
        changed["outcome"] = "acknowledged"
        changed["result_digest"] = digest_without(
            "ncp.local.response.v1", changed, "result_digest"
        )
        with self.assertRaises(LocalError):
            verify_integrity(changed, self.binding)
        verify_response(response, self.binding, request)


_PEER = r"""
import json, sys
from ncp_local import LocalBinding, LocalError, LocalOwner, serve_local
class Backend:
    count = 0
    def validate(self, operation, body):
        if body.get("reject"): raise LocalError("invalid_input")
    def execute(self, operation, body):
        self.count += 1
        return {"count":self.count,"body":body}
    def retire(self): pass
serve_local(LocalOwner(LocalBinding.from_dict(json.loads(sys.argv[1])),Backend()),sys.stdin.buffer,sys.stdout.buffer)
"""


class ClientTests(unittest.TestCase):
    def test_preflight_disposition_never_attempts_a_channel_write(self):
        for case in ("role", "body", "retired", "empty_ack", "empty_result"):
            with self.subTest(case=case):
                client = LocalClient(fixed_binding(), io.BytesIO(), io.BytesIO())
                if case == "retired":
                    client.retire_generation()
                with patch("ncp_local.protocol.write_local_frame") as write:
                    with self.assertRaises(LocalPreflightError):
                        if case == "empty_ack":
                            client.acknowledge()
                        elif case == "empty_result":
                            client.result()
                        else:
                            client.request(
                                "assess" if case == "role" else "prepare",
                                {"v": object()} if case == "body" else {},
                            )
                    write.assert_not_called()

    def test_attempted_write_failure_is_unknown_not_preflight(self):
        client = LocalClient(fixed_binding(), io.BytesIO(), io.BytesIO())
        with patch(
            "ncp_local.protocol.write_local_frame",
            side_effect=OSError("selected write failure"),
        ) as write:
            with self.assertRaises(LocalError) as caught:
                client.request("prepare", {})
            self.assertNotIsInstance(caught.exception, LocalPreflightError)
            self.assertEqual(caught.exception.code, "execution_unknown")
            self.assertEqual(write.call_count, 1)
            self.assertTrue(client.retired)

    def test_real_subprocess_exchange_exact_lookup_and_ack(self):
        binding = fixed_binding("neural")
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", _PEER, json.dumps(binding.as_dict())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        try:
            client = LocalClient(binding, process.stdout, process.stdin, timeout_s=5)
            self.assertEqual(client.next_sequence, 1)
            with self.assertRaises(AttributeError):
                client.next_sequence = 9
            rejected = client.call("prepare", {"reject": True})
            self.assertEqual(rejected["outcome"], "rejected_before_execution")
            self.assertEqual(client.next_sequence, 1)
            prepared = client.request("prepare", {"v": -0.0})
            self.assertEqual(prepared["body"]["count"], 1)
            self.assertEqual(client.next_sequence, 1)
            with patch("ncp_local.protocol.write_local_frame") as write:
                with self.assertRaises(LocalPreflightError):
                    client.request("step", {})
                write.assert_not_called()
            self.assertEqual(client.result(), prepared)
            # Caller mutation cannot alter the SDK's saved acknowledgement target.
            prepared["result_digest"] = "0" * 64
            client.acknowledge()
            self.assertEqual(client.next_sequence, 2)
            stepped = client.call("step", {"value": 3})
            self.assertEqual(stepped["body"]["count"], 2)
            self.assertEqual(stepped["sequence"], 2)
            self.assertEqual(client.call("finish", {})["outcome"], "committed")
            self.assertTrue(client.retired)
            process.stdin.close()
            process.wait(timeout=5)
            self.assertEqual(process.returncode, 0, process.stderr.read().decode())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()

    def test_timeout_retires_client_without_blind_retry(self):
        binding = fixed_binding()
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", "import time;time.sleep(5)"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        try:
            client = LocalClient(binding, process.stdout, process.stdin, timeout_s=0.05)
            start = time.monotonic()
            with self.assertRaisesRegex(LocalError, "execution_unknown"):
                client.call("prepare", {})
            self.assertLess(time.monotonic() - start, 1)
            self.assertTrue(client.retired)
            with self.assertRaisesRegex(LocalError, "retired"):
                client.call("prepare", {})
        finally:
            process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()


if __name__ == "__main__":
    unittest.main()
