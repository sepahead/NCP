"""Tests of the Python reference SDK against the rules of spec/NCP-2.md."""
from __future__ import annotations

import array
import hashlib
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

import ncp  # noqa: E402
from ncp import frame as F  # noqa: E402
from ncp.exchange import bad_frame_response, check_response  # noqa: E402
from echo_owner import CONTRACT, Echo, make_owner  # noqa: E402

OTHER = "0" * 64


def raw_frame(text: bytes, attachments: bytes = b"") -> bytes:
    """Build a frame around arbitrary JSON bytes, for malformed-input tests."""
    payload = text + b" " * ((8 - (12 + len(text)) % 8) % 8)
    body = F.HEADER.pack(F.MAGIC, len(payload), len(attachments)) + payload + attachments
    return body + hashlib.sha256(body).digest()


def request(session: str, seq: int, op: str, ack: str | None, body=None, ncp_version: int = 2) -> bytes:
    return F.encode({"ncp": ncp_version, "session": session, "seq": seq, "op": op, "ack": ack, "body": body})


def open_request(session: str, contract: str = CONTRACT.identity, bound: int = F.DEFAULT_BOUND,
                 application: str = "echo") -> bytes:
    return request(session, 0, "open", None, {"application": application, "contract": contract, "bound": bound})


def response_of(frame: bytes) -> dict:
    message = F.decode(frame, F.MAX_BOUND).message
    check_response(message)
    return message


class FrameTests(unittest.TestCase):
    def test_round_trip_and_alignment(self) -> None:
        values = array.array("d", [0.5, -2.25, 1e300])
        frame = F.encode({"body": {"a": 1, "b": [1.5, None, True, "é"],
                                   "v": F.Array("f64", [3], values.tobytes()),
                                   "w": F.Array("u8", [1], b"\x07"), "x": F.Array("i16", [2, 1], b"\x01\x00\xff\xff")}})
        _, json_length, attachment_length = F.HEADER.unpack_from(frame)
        self.assertEqual((12 + json_length) % 8, 0)
        decoded = F.decode(frame, F.HANDSHAKE_BOUND)
        body = decoded.message["body"]
        self.assertEqual(body["v"].tolist(), [0.5, -2.25, 1e300])
        self.assertEqual(body["w"].tolist(), [7])
        self.assertEqual(body["x"].tolist(), [1, -1])
        self.assertEqual(body["x"].shape, (2, 1))
        self.assertEqual(decoded.message["att"], [24, 1, 4])
        self.assertEqual(attachment_length, 24 + 1 + 7 + 4)  # padding after the second attachment
        self.assertEqual(decoded.identity, F.identity(frame))
        self.assertEqual(decoded.identity, hashlib.sha256(frame[:-32]).hexdigest())

    def test_encoder_refuses_frames_that_receivers_must_reject(self) -> None:
        F.encode({"n": 2**53 - 1, "m": -(2**53 - 1), "t": True})
        for message in ({"n": 2**53}, {"n": -(2**53)}, {"n": [1, {"m": 2**64}]}, {1: "a"},
                        {"a": {None: 1}}, {"a": "\ud83d"}, {"x": float("nan")}, {"x": b"bytes"}):
            with self.subTest(message=repr(message)), self.assertRaises(F.FrameError):
                F.encode(message)
        deep: object = 1
        for _ in range(63):
            deep = [deep]
        F.encode({"d": deep})  # 64 levels
        with self.assertRaises(F.FrameError):
            F.encode({"d": [deep]})
        with self.assertRaises(F.FrameError):
            F.encode([1])  # type: ignore[arg-type]
        # An array's reference object nests three levels below its container.
        nested: object = F.Array("u8", [1], b"x")
        for _ in range(60):
            nested = [nested]
        F.encode({"a": nested})  # shape list at level 64
        with self.assertRaises(F.FrameError):
            F.encode({"a": [nested]})

    def test_numpy_values(self) -> None:
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        decoded = F.decode(F.encode({"s": numpy.int64(7), "f": numpy.float32(0.5), "b": numpy.bool_(True),
                                     "v": numpy.arange(6, dtype=numpy.int16).reshape(2, 3)}), F.HANDSHAKE_BOUND)
        message = decoded.message
        self.assertEqual((message["s"], message["f"], message["b"]), (7, 0.5, True))
        self.assertIs(type(message["s"]), int)
        self.assertEqual(message["v"].to_numpy().tolist(), [[0, 1, 2], [3, 4, 5]])
        with self.assertRaises(F.FrameError):
            F.encode({"s": numpy.uint64(2**64 - 1)})

    def test_the_digest_check_can_be_turned_off(self) -> None:
        good = F.encode({"a": 1})
        wrong = good[:-1] + bytes([good[-1] ^ 1])
        with self.assertRaises(F.FrameError):
            F.decode(wrong, F.HANDSHAKE_BOUND)
        decoded = F.decode(wrong, F.HANDSHAKE_BOUND, check_digest=False)
        self.assertEqual(decoded.identity, F.identity(wrong))
        self.assertEqual(decoded.message, {"a": 1})
        owner = ncp.Owner("echo", CONTRACT.identity, Echo(), CONTRACT.operations, check_digests=False)
        channel, process = ncp.spawn([sys.executable, "-I", os.path.join(HERE, "echo_owner.py"), "--no-digest-check"])
        client = ncp.Client(channel, application="echo", contract=CONTRACT.identity, check_digests=False)
        client.open()
        self.assertEqual(client.call("echo", {"v": F.Array("u8", [2], b"ab")}).body["v"].tolist(), [97, 98])
        client.close()
        self.assertEqual(process.wait(timeout=10), 0)
        self.assertFalse(owner.check_digests)

    def test_attachments_are_eight_byte_aligned_in_the_frame(self) -> None:
        frame = F.encode({"a": F.Array("u8", [3], b"abc"), "b": F.Array("f64", [1], struct.pack("<d", 2.0))})
        decoded = F.decode(frame, F.HANDSHAKE_BOUND)
        self.assertEqual([bytes(item.data) for item in decoded.arrays], [b"abc", struct.pack("<d", 2.0)])
        _, json_length, _ = F.HEADER.unpack_from(frame)
        start = 12 + json_length
        self.assertEqual(start % 8, 0)
        self.assertEqual(frame[start:start + 3], b"abc")
        self.assertEqual(frame[start + 3:start + 8], bytes(5))
        self.assertEqual(frame[start + 8:start + 16], struct.pack("<d", 2.0))

    def test_every_dtype(self) -> None:
        for dtype, (code, size, _) in F.DTYPES.items():
            data = bytes(range(size * 2))
            array_value = F.Array(dtype, [2], data)
            decoded = F.decode(F.encode({"v": array_value}), F.HANDSHAKE_BOUND)
            self.assertEqual(decoded.message["v"], array_value, dtype)

    def test_numpy_round_trip(self) -> None:
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        value = numpy.arange(12, dtype=">i4").reshape(3, 4)[:, ::2]
        decoded = F.decode(F.encode({"v": value}), F.HANDSHAKE_BOUND)
        numpy.testing.assert_array_equal(decoded.message["v"].to_numpy(), value)

    def test_bad_frames(self) -> None:
        good = F.encode({"a": 1})
        cases = {
            "digest": good[:-1] + bytes([good[-1] ^ 1]),
            "magic": b"NCP\x01" + good[4:],
            "json alignment": F.HEADER.pack(F.MAGIC, 3, 0) + b'{} ' + bytes(32),
            "length": good + b"x",
            "duplicate": raw_frame(b'{"a":1,"a":1}'),
            "integer": raw_frame(b'{"a":-9007199254740992}'),
            "infinite": raw_frame(b'{"a":-1e309}'),
            "nan": raw_frame(b'{"a":NaN}'),
            "unpaired high": raw_frame(b'{"a":"x\\ud83dy"}'),
            "unpaired low": raw_frame(b'{"a":"\\ude00"}'),
            "bom": raw_frame(b'\xef\xbb\xbf{"a":1}'),
            "utf16": raw_frame('{"a":1}'.encode("utf-16-le")),
            "not object": raw_frame(b'[1,2]'),
            "depth": raw_frame(b'{"a":' + b'[' * 64 + b']' * 64 + b'}'),
            "att without attachments": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}'),
            "attachments without att": raw_frame(b'{"a":1}', b"abcd"),
            "attachment without array": raw_frame(b'{"att":[4]}', b"abcd"),
            "array without attachment": raw_frame(b'{"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}'),
            "shape mismatch": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"u16","shape":[4],"att":0}}}', b"abcd"),
            "unknown dtype": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"c64","shape":[1],"att":0}}}', b"abcd"),
            "reused attachment": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}},'
                                           b'"w":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}', b"abcd"),
            "array extra member": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0},"x":1}}', b"abcd"),
            "nonzero padding": raw_frame(b'{"att":[1,1],"v":{"ncp.array":{"dtype":"u8","shape":[1],"att":0}},'
                                         b'"w":{"ncp.array":{"dtype":"u8","shape":[1],"att":1}}}', b"a\x01\x00\x00\x00\x00\x00\x00b"),
        }
        for name, frame in cases.items():
            with self.subTest(name):
                with self.assertRaises(F.FrameError):
                    F.decode(frame, F.HANDSHAKE_BOUND)
        self.assertEqual(F.decode(raw_frame(b'{"a":"\\ud83d\\ude00"}'), F.HANDSHAKE_BOUND).message["a"], "\U0001F600")
        deepest = F.decode(raw_frame(b'{"a":' + b'[' * 63 + b']' * 63 + b'}'), F.HANDSHAKE_BOUND).message["a"]
        for _ in range(62):
            deepest = deepest[0]
        self.assertEqual(deepest, [])  # 64 levels including the top object are accepted
        self.assertEqual(F.decode(raw_frame(b'{"a":9007199254740991}'), F.HANDSHAKE_BOUND).message["a"], 2**53 - 1)

    def test_bound(self) -> None:
        frame = F.encode({"a": "x" * 70_000})
        with self.assertRaises(F.FrameError):
            F.decode(frame, F.HANDSHAKE_BOUND)
        self.assertEqual(len(F.decode(frame, F.DEFAULT_BOUND).message["a"]), 70_000)

    def test_encoder_rejects(self) -> None:
        for message in ({"a": float("nan")}, {"a": object()}, {"a": "\ud800"}, {"att": []}):
            with self.subTest(message=repr(message)):
                with self.assertRaises(F.FrameError):
                    F.encode(message)


class OwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.owner = make_owner(max_bound=F.DEFAULT_BOUND)
        self.session = str(uuid.uuid4())

    def opened(self) -> str:
        return F.identity(self.owner.handle(open_request(self.session)))

    def call(self, seq: int, op: str, ack: str | None, body=None, session: str | None = None) -> dict:
        return response_of(self.owner.handle(request(session or self.session, seq, op, ack, body)))

    def test_not_open_and_wrong_protocol(self) -> None:
        self.assertEqual(self.call(1, "echo", OTHER)["code"], "not_open")
        self.assertEqual(response_of(self.owner.handle(request(self.session, 0, "open", None, {}, ncp_version=3)))["code"],
                         "wrong_protocol")

    def test_open_checks(self) -> None:
        self.assertEqual(response_of(self.owner.handle(open_request(self.session, contract=OTHER)))["code"], "contract_mismatch")
        self.assertEqual(response_of(self.owner.handle(open_request(self.session, application="other")))["code"], "contract_mismatch")
        self.assertEqual(response_of(self.owner.handle(open_request(self.session, bound=1000)))["code"], "bound_unacceptable")
        self.assertEqual(response_of(self.owner.handle(request(self.session, 0, "open", None, {"application": "echo"})))["code"],
                         "body_invalid")
        self.assertIsNone(self.owner.session)
        reply = response_of(self.owner.handle(open_request(self.session, bound=F.MAX_BOUND)))
        self.assertEqual(reply["outcome"], "ok")
        self.assertEqual(reply["body"]["bound"], F.DEFAULT_BOUND)  # lowered to the owner's largest bound

    def test_open_retry_returns_identical_bytes(self) -> None:
        first = self.owner.handle(open_request(self.session))
        self.assertEqual(self.owner.handle(open_request(self.session)), first)

    def test_sequence_and_ack_rules(self) -> None:
        ack = self.opened()
        self.assertEqual(self.call(1, "echo", OTHER, session=str(uuid.uuid4()))["code"], "wrong_session")
        self.assertEqual(self.call(2, "echo", ack)["code"], "seq_gap")
        self.assertEqual(self.call(1, "echo", None)["code"], "ack_missing")
        self.assertEqual(self.call(1, "echo", OTHER)["code"], "ack_mismatch")
        self.assertEqual(self.call(1, "open", ack)["code"], "already_open")
        self.assertEqual(self.call(1, "missing", ack)["code"], "unknown_op")
        self.assertEqual(self.call(1, "echo", ack, {"invalid": True})["code"], "body_invalid")
        # None of the rejections changed state: request 1 still executes with the open ack.
        first = self.owner.handle(request(self.session, 1, "echo", ack, {"n": 1}))
        self.assertEqual(response_of(first)["body"], {"n": 1})
        self.assertEqual(self.owner.handle(request(self.session, 1, "echo", ack, {"n": 1})), first)
        self.assertEqual(self.call(1, "echo", ack, {"n": 2})["code"], "seq_conflict")
        self.assertEqual(self.call(0, "open", None, {})["code"], "seq_stale")
        self.assertEqual(self.call(2, "echo", ack)["code"], "ack_mismatch")  # ack must name response 1
        second = response_of(self.owner.handle(request(self.session, 2, "echo", F.identity(first), {"n": 3})))
        self.assertEqual(second["body"], {"n": 3})

    def test_owner_failure_ends_the_session(self) -> None:
        ack = self.opened()
        failed = self.owner.handle(request(self.session, 1, "fail", ack, {}))
        self.assertEqual((response_of(failed)["outcome"], response_of(failed)["code"]), ("ended", "owner_failure"))
        self.assertEqual(self.owner.handle(request(self.session, 1, "fail", ack, {})), failed)
        self.assertEqual(self.call(2, "echo", F.identity(failed))["code"], "session_ended")

    def test_result_too_large(self) -> None:
        # The result, not the request, exceeds the bound: the handler inflates a small body.
        owner = ncp.Owner("echo", CONTRACT.identity, _Inflater(), CONTRACT.operations, max_bound=F.HANDSHAKE_BOUND)
        session = str(uuid.uuid4())
        ack = F.identity(owner.handle(open_request(session, bound=F.HANDSHAKE_BOUND)))
        reply = response_of(owner.handle(request(session, 1, "echo", ack, {"size": F.HANDSHAKE_BOUND})))
        self.assertEqual((reply["outcome"], reply["code"]), ("ended", "result_too_large"))
        self.assertEqual(reply["body"]["bound"], F.HANDSHAKE_BOUND)
        self.assertGreater(reply["body"]["size"], F.HANDSHAKE_BOUND)

    def test_close(self) -> None:
        ack = self.opened()
        closed = self.owner.handle(request(self.session, 1, "close", ack, {}))
        self.assertEqual(response_of(closed)["outcome"], "ok")
        self.assertEqual(self.owner.handle(request(self.session, 1, "close", ack, {})), closed)
        self.assertEqual(self.call(2, "echo", F.identity(closed))["code"], "session_ended")

    def test_bad_frame_raises(self) -> None:
        with self.assertRaises(F.FrameError):
            self.owner.handle(raw_frame(b'{"ncp":2}'))
        with self.assertRaises(F.FrameError):
            self.owner.handle(F.encode({"ncp": 2, "session": "x", "seq": 0, "op": "open", "ack": None, "body": {}}))


class _Inflater:
    def validate(self, op, body):
        pass

    def execute(self, op, body):
        return {"blob": "z" * body["size"]}


class _MemoryChannel:
    """An in-memory channel to an owner that can drop frames in both directions."""

    lossy = True

    def __init__(self, owner, drop_requests=(), drop_responses=()) -> None:
        self.owner, self.queue = owner, []
        self.drop_requests, self.drop_responses = set(drop_requests), set(drop_responses)
        self.sent = 0

    def send(self, frame: bytes) -> None:
        self.sent += 1
        if self.sent in self.drop_requests:
            return
        response = self.owner.handle(frame)
        if self.sent not in self.drop_responses:
            self.queue.append(response)

    def receive(self, bound: int, timeout):
        if not self.queue:
            raise TimeoutError
        return self.queue.pop(0)


class ClientTests(unittest.TestCase):
    def test_lossy_channel_retries_without_reexecution(self) -> None:
        executed = []

        class Counting(Echo):
            def execute(self, op, body):
                executed.append(body)
                return body

        owner = ncp.Owner("echo", CONTRACT.identity, Counting(), CONTRACT.operations)
        channel = _MemoryChannel(owner, drop_requests={2}, drop_responses={4, 5})
        client = ncp.Client(channel, application="echo", contract=CONTRACT.identity, retries=3)
        client.open()
        self.assertEqual(client.call("echo", {"n": 1}).body, {"n": 1})  # sends 2 (dropped) and 3
        self.assertEqual(client.call("echo", {"n": 2}).body, {"n": 2})  # sends 4, 5 (responses lost) and 6
        self.assertEqual(executed, [{"n": 1}, {"n": 2}])  # each request executed exactly once

    def test_rejected_then_corrected(self) -> None:
        owner = make_owner()
        client = ncp.Client(_MemoryChannel(owner), application="echo", contract=CONTRACT.identity)
        client.open()
        with self.assertRaises(ncp.Rejected) as caught:
            client.call("echo", {"invalid": True})
        self.assertEqual(caught.exception.code, "body_invalid")
        self.assertEqual(client.call("echo", {"ok": 1}).body, {"ok": 1})

    def test_owner_failure(self) -> None:
        client = ncp.Client(_MemoryChannel(make_owner()), application="echo", contract=CONTRACT.identity)
        client.open()
        with self.assertRaises(ncp.Ended) as caught:
            client.call("fail", {})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", "unknown"))
        with self.assertRaises(ncp.ProtocolError):
            client.call("echo", {})


class StreamTests(unittest.TestCase):
    def test_subscriber_rules(self) -> None:
        sent = []
        publisher = ncp.Publisher("sensors/camera-0", CONTRACT.identity, sent.append)
        for index in range(5):
            publisher.publish({"i": index})
        subscriber = ncp.Subscriber({CONTRACT.identity})
        self.assertEqual(subscriber.receive(sent[0]).status, "accepted")
        self.assertEqual(subscriber.receive(sent[0]).status, "repeat")
        delivery = subscriber.receive(sent[3])
        self.assertEqual((delivery.status, delivery.lost), ("accepted", 2))
        changed = F.encode({**F.decode(sent[4], F.MAX_BOUND).message, "body": {"i": 99}})
        self.assertEqual(subscriber.receive(changed).status, "accepted")  # a re-encoded frame with the right prev
        forged = F.encode({"ncp": 2, "stream": "sensors/camera-0", "seq": 6, "prev": OTHER,
                           "contract": CONTRACT.identity, "body": {}})
        self.assertEqual(subscriber.receive(forged).status, "broken_chain")
        other = ncp.Publisher("x", OTHER, sent.append)
        self.assertEqual(subscriber.receive(other.publish({})).status, "unknown_contract")
        self.assertEqual(subscriber.receive(b"garbage").status, "bad_frame")


class TranscriptTests(unittest.TestCase):
    def run_session(self, path: str) -> None:
        tap = ncp.Tap(path)
        channel, process = ncp.spawn([sys.executable, "-I", os.path.join(HERE, "echo_owner.py")], tap=tap)
        client = ncp.Client(channel, application="echo", contract=CONTRACT.identity)
        client.open()
        for index in range(3):
            client.call("echo", {"i": index})
        client.close()
        tap.close()
        process.wait(timeout=10)

    def test_complete_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "t.ncpt")
            self.run_session(path)
            (report,) = ncp.verify_transcript(path).values()
            self.assertEqual((report.role, report.requests, report.complete, report.problems), ("client", 5, True, []))

    def test_changed_and_truncated_transcripts(self) -> None:
        from ncp import transcript as T
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "t.ncpt")
            self.run_session(path)
            records = list(T.read(path))
            # Drop the close exchange: the session is no longer complete.
            truncated = os.path.join(directory, "truncated.ncpt")
            with open(truncated, "wb") as handle:
                handle.write(T.FILE_MAGIC)
                for record in records[:-2]:
                    handle.write(T.RECORD.pack(record.kind, record.time_ns, len(record.frame)) + record.frame)
            (report,) = ncp.verify_transcript(truncated).values()
            self.assertFalse(report.complete)
            # Replace a response by another valid frame: the chain breaks.
            message = F.decode(records[3].frame, F.MAX_BOUND).message
            records[3].frame = F.encode({**message, "body": {"i": 42}})
            changed = os.path.join(directory, "changed.ncpt")
            with open(changed, "wb") as handle:
                handle.write(T.FILE_MAGIC)
                for record in records:
                    handle.write(T.RECORD.pack(record.kind, record.time_ns, len(record.frame)) + record.frame)
            (report,) = ncp.verify_transcript(changed).values()
            self.assertTrue(any("ack does not name the previous response" in p for p in report.problems), report.problems)


class BindingTests(unittest.TestCase):
    def test_tcp_loopback_session(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        try:
            host, port = server.address[:2]
            client = ncp.Client(ncp.connect_tcp(host, port), application="echo", contract=CONTRACT.identity)
            client.open()
            self.assertEqual(client.call("echo", {"tcp": True}).body, {"tcp": True})
            client.close()
        finally:
            server.stop()

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "no Unix domain sockets")
    def test_unix_socket_session(self) -> None:
        directory = tempfile.mkdtemp(prefix="ncp-")
        os.chmod(directory, 0o700)
        path = os.path.join(directory, "owner.sock")
        server = ncp.UnixServer(make_owner, path).start()
        try:
            clients = [ncp.Client(ncp.connect_unix(path), application="echo", contract=CONTRACT.identity)
                       for _ in range(3)]
            for client in clients:
                client.open()
            for index, client in enumerate(clients):
                self.assertEqual(client.call("echo", {"unix": index}).body, {"unix": index})
            for client in clients:
                client.close()
        finally:
            server.stop()
            os.rmdir(directory)
        self.assertFalse(os.path.exists(path))

    @unittest.skipUnless(os.environ.get("NCP_RUST_EXAMPLES"), "set NCP_RUST_EXAMPLES to the Rust examples directory")
    def test_python_client_with_the_rust_owner(self) -> None:
        owner = os.path.join(os.environ["NCP_RUST_EXAMPLES"], "echo_owner")
        channel, process = ncp.spawn([owner])
        rust_contract = ncp.Contract.from_bytes(
            b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}')
        client = ncp.Client(channel, application="echo", contract=rust_contract.identity)
        self.assertTrue(client.open()["implementation"].startswith("ncp-rust/"))
        values = {d: F.Array(d, [3], bytes(range(3 * F.DTYPES[d][1]))) for d in F.DTYPES}
        result = client.call("echo", {"v": values, "n": -(2**53 - 1), "s": "é😀"})
        self.assertEqual(result.body["n"], -(2**53 - 1))
        self.assertEqual(result.body["s"], "é😀")
        for dtype, value in values.items():
            self.assertEqual(result.body["v"][dtype], value)
        with self.assertRaises(ncp.Rejected):
            client.call("echo", {"invalid": True})
        with self.assertRaises(ncp.Ended) as ended:
            client.call("fail", {})
        self.assertEqual((ended.exception.code, ended.exception.executed), ("owner_failure", "unknown"))
        client.close()
        self.assertEqual(process.wait(timeout=10), 0)

    def test_a_damaged_body_is_a_bad_frame(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        try:
            host, port = server.address[:2]
            damaged = bytearray(F.encode({"a": "x" * 70_000}))
            damaged[40_000] ^= 1
            with socket.create_connection((host, port)) as sock:
                sock.sendall(damaged)
                channel = ncp.StreamChannel.from_socket(sock)
                response = F.decode(channel.receive(F.MAX_BOUND, 10), F.MAX_BOUND).message
            self.assertEqual(response["code"], "bad_frame")
        finally:
            server.stop()

    def test_remote_addresses_need_an_option(self) -> None:
        with self.assertRaises(ValueError):
            ncp.connect_tcp("192.0.2.1", 1)

    def test_bad_frame_rule_and_slow_sender(self) -> None:
        left, right = socket.socketpair()
        owner_channel = ncp.StreamChannel.from_socket(right)
        thread = threading.Thread(target=ncp.serve, args=(make_owner(), owner_channel), kwargs={"frame_timeout": 0.2})
        thread.start()
        left.sendall(b"NCP\x02" + struct.pack(">II", 4, 0) + b"{}  " + bytes(32))  # wrong digest
        reply = ncp.StreamChannel.from_socket(left).receive(F.MAX_BOUND, 2.0)
        self.assertEqual(response_of(reply)["code"], "bad_frame")
        thread.join(2.0)
        self.assertFalse(thread.is_alive())
        left.close()
        left2, right2 = socket.socketpair()
        thread = threading.Thread(target=ncp.serve, args=(make_owner(), ncp.StreamChannel.from_socket(right2)),
                                  kwargs={"frame_timeout": 0.2})
        thread.start()
        left2.sendall(b"NCP\x02")  # a header that never completes
        reply = ncp.StreamChannel.from_socket(left2).receive(F.MAX_BOUND, 2.0)
        self.assertEqual(response_of(reply)["code"], "bad_frame")
        thread.join(2.0)
        self.assertFalse(thread.is_alive())
        left2.close()

    def test_bad_frame_response_form(self) -> None:
        message = response_of(bad_frame_response())
        self.assertEqual((message["session"], message["seq"], message["request"]), (None, None, None))

    def test_call_all(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        try:
            host, port = server.address[:2]
            clients = [ncp.Client(ncp.connect_tcp(host, port), application="echo", contract=CONTRACT.identity)
                       for _ in range(8)]
            for client in clients:
                client.open()
            results = ncp.call_all(clients, "echo", [{"agent": index} for index in range(8)])
            self.assertEqual([result.body for result in results], [{"agent": index} for index in range(8)])
            failures = ncp.call_all(clients, "fail", [{}] * 8)
            self.assertTrue(all(isinstance(item, ncp.Ended) for item in failures))
            for client in clients:
                client.close()
        finally:
            server.stop()


class ContractTests(unittest.TestCase):
    def test_identity_is_the_digest_of_exact_bytes(self) -> None:
        self.assertEqual(CONTRACT.identity, hashlib.sha256(CONTRACT.data).hexdigest())
        spaced = ncp.Contract.from_bytes(CONTRACT.data.replace(b",", b", "))
        self.assertNotEqual(spaced.identity, CONTRACT.identity)
        with self.assertRaises(ValueError):
            ncp.Contract.from_bytes(b'{"ncp_contract":2}')


if __name__ == "__main__":
    unittest.main()
