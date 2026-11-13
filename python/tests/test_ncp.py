"""Tests of the Python reference SDK against the rules of spec/NCP-2.md."""

from __future__ import annotations

import array
import hashlib
import json
import logging
import os
import shutil
import socket
import ssl
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from echo_owner import CONTRACT, Echo, make_owner  # noqa: E402

import ncp  # noqa: E402
from ncp import client as C  # noqa: E402
from ncp import frame as F  # noqa: E402
from ncp import transcript as T  # noqa: E402
from ncp.messages import bad_frame_response, check_response  # noqa: E402

OTHER = "0" * 64
KEY = bytes(range(32))
logging.getLogger("ncp").addHandler(logging.NullHandler())


def raw_frame(text: bytes, attachments: bytes = b"", pad: bytes | None = None) -> bytes:
    """Build a frame around arbitrary JSON bytes, for malformed-input tests."""
    payload = text + (b" " * ((8 - (12 + len(text)) % 8) % 8) if pad is None else pad)
    body = F.HEADER.pack(F.MAGIC, len(payload), len(attachments)) + payload + attachments
    return body + hashlib.sha256(body).digest()


def request(session: str, seq: int, op: str, ack: str | None, body=None, ncp_version: int = 2, key=None) -> bytes:
    return F.encode({"ncp": ncp_version, "session": session, "seq": seq, "op": op, "ack": ack, "body": body}, key=key)


def open_request(session: str, contract: str = CONTRACT.identity, bound: int = F.DEFAULT_BOUND, **extra) -> bytes:
    body = {"application": extra.pop("application", "echo"), "contract": contract, "bound": bound, **extra}
    return request(session, 0, "open", None, body)


def response_of(frame: bytes) -> dict:
    message = F.decode(frame, F.MAX_BOUND).message
    check_response(message)
    return message


def quiet() -> logging.Logger:
    """The SDK logs application errors; tests that cause them on purpose silence it."""
    return logging.getLogger("ncp")


class _Silence:
    def __enter__(self):
        logging.disable(logging.CRITICAL)

    def __exit__(self, *exc):
        logging.disable(logging.NOTSET)


class FrameTests(unittest.TestCase):
    def test_round_trip_and_alignment(self) -> None:
        values = array.array("d", [0.5, -2.25, 1e300])
        frame = F.encode(
            {
                "body": {
                    "a": 1,
                    "b": [1.5, None, True, "é"],
                    "v": F.Array("f64", [3], values.tobytes()),
                    "w": F.Array("u8", [1], b"\x07"),
                    "x": F.Array("i16", [2, 1], b"\x01\x00\xff\xff"),
                }
            }
        )
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
        for message in (
            {"n": 2**53},
            {"n": -(2**53)},
            {"n": [1, {"m": 2**64}]},
            {1: "a"},
            {"a": {None: 1}},
            {"a": "\ud83d"},
            {"x": float("nan")},
            {"x": b"bytes"},
        ):
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
        nested: object = F.Array("u8", [1], b"x")
        for _ in range(60):
            nested = [nested]
        F.encode({"a": nested})  # shape list at level 64
        with self.assertRaises(F.FrameError):
            F.encode({"a": [nested]})

    def test_json_padding_is_exact(self) -> None:
        # Section 3, rule 4: { first, } last, then only the padding that alignment needs.
        F.decode(raw_frame(b'{"a":1}'), F.HANDSHAKE_BOUND)
        for name, frame in {
            "eight spaces": raw_frame(b'{"a":1}', pad=b" " * 9),
            "tab and newline": raw_frame(b'{"a":1}', pad=b"\t\n\r\n "),
            "leading spaces": raw_frame(b"        " + b'{"a":1}'),
        }.items():
            with self.subTest(name), self.assertRaises(F.FrameError):
                F.decode(frame, F.HANDSHAKE_BOUND)

    def test_the_json_region_is_at_most_one_mebibyte(self) -> None:
        big = {"a": "x" * (F.MAX_JSON - 16)}
        frame = F.encode(big)
        # 12 + J is a multiple of 8, so the largest JSON region is 1 MiB minus 4 bytes.
        self.assertEqual(F.HEADER.unpack_from(frame)[1], F.MAX_JSON - 4)
        F.decode(frame, F.MAX_BOUND)
        with self.assertRaises(F.TooLarge) as caught:
            F.encode({"a": "x" * F.MAX_JSON})
        self.assertTrue(caught.exception.json)
        # Arrays are not part of the JSON region: 8 MiB of data travel in one frame.
        frame = F.encode({"a": F.Array("u8", [8 << 20], bytes(8 << 20))})
        self.assertEqual(len(F.decode(frame, F.MAX_BOUND).arrays[0].data), 8 << 20)
        with self.assertRaises(F.TooLarge):
            F.encode({"a": F.Array("u8", [1 << 20], bytes(1 << 20))}, limit=F.DEFAULT_BOUND)

    def test_authenticated_frames(self) -> None:
        frame = F.encode({"a": 1}, key=KEY)
        self.assertEqual(F.decode(frame, F.HANDSHAKE_BOUND, key=KEY).message, {"a": 1})
        with self.assertRaises(F.FrameError):
            F.decode(frame, F.HANDSHAKE_BOUND)  # a SHA-256 check fails on an authentication code
        with self.assertRaises(F.FrameError):
            F.decode(F.encode({"a": 1}), F.HANDSHAKE_BOUND, key=KEY)
        with self.assertRaises(ValueError):
            F.decode(frame, F.HANDSHAKE_BOUND, key=KEY, check_digest=False)
        with self.assertRaises(ValueError):
            F.encode({"a": 1}, key=b"short")

    def test_loads_applies_the_json_rules(self) -> None:
        self.assertEqual(F.loads(b'{"a":[1,2.5]}'), {"a": [1, 2.5]})
        for text in (b'{"a":1,"a":2}', b'{"a":-0}', b'{"a":1e400}', b'{"a":"\\ud800"}', b"\xef\xbb\xbf{}"):
            with self.subTest(text=text), self.assertRaises(F.FrameError):
                F.loads(text)

    def test_numpy_values(self) -> None:
        try:
            import numpy
        except ImportError:
            self.skipTest("numpy is not installed")
        decoded = F.decode(
            F.encode(
                {
                    "s": numpy.int64(7),
                    "f": numpy.float32(0.5),
                    "b": numpy.bool_(True),
                    "v": numpy.arange(6, dtype=numpy.int16).reshape(2, 3),
                }
            ),
            F.HANDSHAKE_BOUND,
        )
        message = decoded.message
        self.assertEqual((message["s"], message["f"], message["b"]), (7, 0.5, True))
        self.assertIs(type(message["s"]), int)
        self.assertEqual(message["v"].to_numpy().tolist(), [[0, 1, 2], [3, 4, 5]])
        with self.assertRaises(F.FrameError):
            F.encode({"s": numpy.uint64(2**64 - 1)})

    def test_the_digest_check_can_be_turned_off_on_local_links(self) -> None:
        good = F.encode({"a": 1})
        wrong = good[:-1] + bytes([good[-1] ^ 1])
        with self.assertRaises(F.FrameError):
            F.decode(wrong, F.HANDSHAKE_BOUND)
        decoded = F.decode(wrong, F.HANDSHAKE_BOUND, check_digest=False)
        self.assertEqual(decoded.identity, F.identity(wrong))
        self.assertEqual(decoded.message, {"a": 1})
        channel = ncp.spawn([sys.executable, "-I", os.path.join(HERE, "echo_owner.py"), "--no-digest-check"])
        with ncp.Client(channel, CONTRACT, check_digests=False) as client:
            self.assertEqual(client.call("echo", {"v": F.Array("u8", [2], b"ab")}).body["v"].tolist(), [97, 98])
        self.assertEqual(channel.process.wait(timeout=10), 0)
        # Never over TCP (section 3, rule 5).
        server = ncp.TcpServer(lambda: make_owner(check_digests=False)).start()
        try:
            host, port = server.address[:2]
            client = ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=5)
            with self.assertRaises(ncp.Ended):
                client.open()  # the server refuses to serve without the comparison and closes
        finally:
            server.stop()

    def test_attachments_are_eight_byte_aligned_in_the_frame(self) -> None:
        frame = F.encode({"a": F.Array("u8", [3], b"abc"), "b": F.Array("f64", [1], struct.pack("<d", 2.0))})
        decoded = F.decode(frame, F.HANDSHAKE_BOUND)
        self.assertEqual([bytes(item.data) for item in decoded.arrays], [b"abc", struct.pack("<d", 2.0)])
        _, json_length, _ = F.HEADER.unpack_from(frame)
        start = 12 + json_length
        self.assertEqual(start % 8, 0)
        self.assertEqual(frame[start : start + 3], b"abc")
        self.assertEqual(frame[start + 3 : start + 8], bytes(5))
        self.assertEqual(frame[start + 8 : start + 16], struct.pack("<d", 2.0))

    def test_every_dtype(self) -> None:
        for dtype, (_, size, _) in F.DTYPES.items():
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
            "json alignment": F.HEADER.pack(F.MAGIC, 3, 0) + b"{} " + bytes(32),
            "length": good + b"x",
            "duplicate": raw_frame(b'{"a":1,"a":1}'),
            "integer": raw_frame(b'{"a":-9007199254740992}'),
            "infinite": raw_frame(b'{"a":-1e309}'),
            "nan": raw_frame(b'{"a":NaN}'),
            "unpaired high": raw_frame(b'{"a":"x\\ud83dy"}'),
            "unpaired low": raw_frame(b'{"a":"\\ude00"}'),
            "bom": raw_frame(b'\xef\xbb\xbf{"a":1}'),
            "utf16": raw_frame('{"a":1}'.encode("utf-16-le")),
            "not object": raw_frame(b"[1,2]"),
            "depth": raw_frame(b'{"a":' + b"[" * 64 + b"]" * 64 + b"}"),
            "att without attachments": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}'),
            "attachments without att": raw_frame(b'{"a":1}', b"abcd"),
            "attachment without array": raw_frame(b'{"att":[4]}', b"abcd"),
            "array without attachment": raw_frame(b'{"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}'),
            "shape mismatch": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"u16","shape":[4],"att":0}}}', b"abcd"),
            "unknown dtype": raw_frame(b'{"att":[4],"v":{"ncp.array":{"dtype":"c64","shape":[1],"att":0}}}', b"abcd"),
            "reused attachment": raw_frame(
                b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}},'
                b'"w":{"ncp.array":{"dtype":"u8","shape":[4],"att":0}}}',
                b"abcd",
            ),
            "array extra member": raw_frame(
                b'{"att":[4],"v":{"ncp.array":{"dtype":"u8","shape":[4],"att":0},"x":1}}', b"abcd"
            ),
            "nonzero padding": raw_frame(
                b'{"att":[1,1],"v":{"ncp.array":{"dtype":"u8","shape":[1],"att":0}},'
                b'"w":{"ncp.array":{"dtype":"u8","shape":[1],"att":1}}}',
                b"a\x01\x00\x00\x00\x00\x00\x00b",
            ),
        }
        for name, frame in cases.items():
            with self.subTest(name):
                with self.assertRaises(F.FrameError):
                    F.decode(frame, F.HANDSHAKE_BOUND)
        self.assertEqual(F.decode(raw_frame(b'{"a":"\\ud83d\\ude00"}'), F.HANDSHAKE_BOUND).message["a"], "\U0001f600")
        deepest = F.decode(raw_frame(b'{"a":' + b"[" * 63 + b"]" * 63 + b"}"), F.HANDSHAKE_BOUND).message["a"]
        for _ in range(62):
            deepest = deepest[0]
        self.assertEqual(deepest, [])
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


class _Inflater(Echo):
    def execute(self, request):
        if "json" in request.body:
            return {"blob": "z" * request.body["json"]}
        return {"blob": F.Array("u8", [request.body["size"]], bytes(request.body["size"]))}


class OwnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.owner = make_owner(max_bound=F.DEFAULT_BOUND)
        self.session = str(uuid.uuid4())

    def opened(self) -> str:
        return F.identity(self.owner.handle(open_request(self.session)))

    def call(self, seq: int, op: str, ack: str | None, body=None, session: str | None = None) -> dict:
        return response_of(self.owner.handle(request(session or self.session, seq, op, ack, body)))

    def test_without_a_session(self) -> None:
        # Rule 7.3.3: seq 0 that is not open is rejected; seq > 0 is possibly executed elsewhere.
        self.assertEqual(self.call(0, "echo", None)["code"], "not_open")
        reply = self.call(1, "echo", OTHER)
        self.assertEqual((reply["outcome"], reply["code"]), ("ended", "session_expired"))
        self.assertEqual(
            response_of(self.owner.handle(request(self.session, 0, "open", None, {}, ncp_version=3)))["code"],
            "wrong_protocol",
        )
        self.assertIsNone(self.owner.session)

    def test_open_checks(self) -> None:
        def code(frame: bytes) -> str:
            return response_of(self.owner.handle(frame))["code"]

        self.assertEqual(code(open_request(self.session, contract=OTHER)), "contract_mismatch")
        self.assertEqual(code(open_request(self.session, application="other")), "contract_mismatch")
        self.assertEqual(code(open_request(self.session, bound=1000)), "bound_unacceptable")
        self.assertEqual(code(request(self.session, 0, "open", None, {"application": "echo"})), "body_invalid")
        self.assertEqual(code(open_request(self.session, extra={})), "body_invalid")
        self.assertEqual(code(open_request(self.session, run="r" * 257)), "body_invalid")
        self.assertEqual(code(open_request(self.session, features={"Bad": {}})), "body_invalid")
        self.assertEqual(code(open_request(self.session, features={"x": 1})), "body_invalid")
        self.assertIsNone(self.owner.session)
        reply = response_of(
            self.owner.handle(open_request(self.session, bound=F.MAX_BOUND, run="r" * 256, features={"later": {"a": 1}}))
        )
        self.assertEqual(reply["outcome"], "ok")
        body = reply["body"]
        self.assertEqual(body["bound"], F.DEFAULT_BOUND)  # lowered to the owner's largest bound
        self.assertEqual(body["features"], {})  # an unknown feature is not enabled
        self.assertRegex(body["nonce"], r"\A[0-9a-f]{32}\Z")
        self.assertEqual((body["application"], body["contract"]), ("echo", CONTRACT.identity))

    def test_each_opening_has_its_own_nonce(self) -> None:
        # Section 7.1, rule 5: different nonces make the chains of two openings disjoint, so a
        # copy of a step that an earlier owner admitted cannot be admitted again (property 7.7.1).
        first, second = make_owner(), make_owner()
        session = str(uuid.uuid4())
        open_a, open_b = first.handle(open_request(session)), second.handle(open_request(session))
        self.assertNotEqual(response_of(open_a)["body"]["nonce"], response_of(open_b)["body"]["nonce"])
        step = request(session, 1, "echo", F.identity(open_a), {"n": 1})
        self.assertEqual(response_of(first.handle(step))["outcome"], "ok")
        # The second owner, opened by a late copy of the same open, never admits that step.
        self.assertEqual(response_of(second.handle(step))["code"], "ack_mismatch")

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
        # None of the rejections changed state: request 1 still executes with the open ack.
        first = self.owner.handle(request(self.session, 1, "echo", ack, {"n": 1}))
        self.assertEqual(response_of(first)["body"], {"n": 1})
        self.assertEqual(self.owner.handle(request(self.session, 1, "echo", ack, {"n": 1})), first)
        self.assertEqual(self.call(1, "echo", ack, {"n": 2})["code"], "seq_conflict")
        self.assertEqual(self.call(0, "open", None, {})["code"], "seq_stale")
        self.assertEqual(self.call(2, "echo", ack)["code"], "ack_mismatch")  # ack must name response 1
        second = response_of(self.owner.handle(request(self.session, 2, "echo", F.identity(first), {"n": 3})))
        self.assertEqual(second["body"], {"n": 3})

    def test_a_declined_request_is_admitted_and_kept(self) -> None:
        # D1: unknown_op and body_invalid are answers to an admitted request. The answer is kept
        # and never changes; the next request acknowledges it.
        ack = self.opened()
        unknown = self.owner.handle(request(self.session, 1, "missing", ack, {}))
        self.assertEqual((response_of(unknown)["outcome"], response_of(unknown)["code"]), ("declined", "unknown_op"))
        self.assertEqual(self.owner.handle(request(self.session, 1, "missing", ack, {})), unknown)
        invalid = self.owner.handle(request(self.session, 2, "echo", F.identity(unknown), {"invalid": True}))
        self.assertEqual(response_of(invalid)["code"], "body_invalid")
        self.assertEqual(response_of(invalid)["body"], {"detail": "invalid requested"})
        third = self.call(3, "echo", F.identity(invalid), {"n": 3})
        self.assertEqual((third["outcome"], third["body"]), ("ok", {"n": 3}))
        self.assertEqual(self.call(1, "missing", ack, {})["code"], "seq_stale")

    def test_a_declined_answer_never_changes(self) -> None:
        # P-1: the application's verdict changes between two copies of one frame.
        class Flaky(Echo):
            def __init__(self) -> None:
                super().__init__()
                self.accept = False
                self.executed = 0

            def validate(self, req):
                if not self.accept:
                    raise ncp.Declined("not yet")

            def execute(self, req):
                self.executed += 1
                return {}

        handler = Flaky()
        owner = ncp.Owner(CONTRACT, handler)
        session = str(uuid.uuid4())
        ack = F.identity(owner.handle(open_request(session)))
        frame = request(session, 1, "echo", ack, {"n": 1})
        first = owner.handle(frame)
        handler.accept = True
        self.assertEqual(owner.handle(frame), first)
        self.assertEqual(handler.executed, 0)

    def test_owner_failure_ends_the_session(self) -> None:
        ack = self.opened()
        with _Silence():
            failed = self.owner.handle(request(self.session, 1, "fail", ack, {}))
        self.assertEqual((response_of(failed)["outcome"], response_of(failed)["code"]), ("ended", "owner_failure"))
        self.assertEqual(self.owner.handle(request(self.session, 1, "fail", ack, {})), failed)
        self.assertEqual(self.call(2, "echo", F.identity(failed))["code"], "session_ended")

    def test_an_application_error_reaches_the_log(self) -> None:
        ack = self.opened()
        with self.assertLogs("ncp", level="ERROR") as logs:
            self.owner.handle(request(self.session, 1, "fail", ack, {}))
        self.assertTrue(any("requested failure" in line for line in logs.output))

    def test_result_too_large(self) -> None:
        owner = ncp.Owner(CONTRACT, _Inflater(), max_bound=F.HANDSHAKE_BOUND)
        session = str(uuid.uuid4())
        ack = F.identity(owner.handle(open_request(session, bound=F.HANDSHAKE_BOUND)))
        reply = response_of(owner.handle(request(session, 1, "echo", ack, {"size": F.HANDSHAKE_BOUND})))
        self.assertEqual((reply["outcome"], reply["code"]), ("ended", "result_too_large"))
        self.assertEqual(reply["body"]["bound"], F.HANDSHAKE_BOUND)
        self.assertGreater(reply["body"]["size"], F.HANDSHAKE_BOUND)
        owner = ncp.Owner(CONTRACT, _Inflater(), max_bound=F.MAX_BOUND)
        ack = F.identity(owner.handle(open_request(session, bound=F.MAX_BOUND)))
        reply = response_of(owner.handle(request(session, 1, "echo", ack, {"json": F.MAX_JSON})))
        self.assertEqual((reply["code"], reply["body"]["limit"]), ("result_too_large", F.MAX_JSON))

    def test_close_and_ping(self) -> None:
        ack = self.opened()
        ping = self.owner.handle(request(self.session, 1, "ncp.ping", ack, {}))
        self.assertEqual((response_of(ping)["outcome"], response_of(ping)["body"]), ("ok", {}))
        closed = self.owner.handle(request(self.session, 2, "close", F.identity(ping), {}))
        self.assertEqual(response_of(closed)["outcome"], "ok")
        self.assertTrue(self.owner.closed)
        self.assertEqual(self.owner.handle(request(self.session, 2, "close", F.identity(ping), {})), closed)
        self.assertEqual(self.call(3, "echo", F.identity(closed))["code"], "session_ended")

    def test_a_stopping_owner_admits_nothing_new(self) -> None:
        ack = self.opened()
        first = self.owner.handle(request(self.session, 1, "echo", ack, {"n": 1}))
        self.owner.stop()
        self.assertEqual(self.owner.handle(request(self.session, 1, "echo", ack, {"n": 1})), first)
        reply = self.call(2, "echo", F.identity(first), {"n": 2})
        self.assertEqual((reply["outcome"], reply["code"]), ("ended", "shutdown"))
        fresh = make_owner()
        fresh.stop()
        self.assertEqual(response_of(fresh.handle(open_request(self.session)))["code"], "refused")

    def test_bad_frame_raises(self) -> None:
        with self.assertRaises(F.FrameError):
            self.owner.handle(raw_frame(b'{"ncp":2}'))
        with self.assertRaises(F.FrameError):
            self.owner.handle(F.encode({"ncp": 2, "session": "x", "seq": 0, "op": "open", "ack": None, "body": {}}))

    def test_a_detail_that_a_frame_cannot_carry_never_stops_the_response(self) -> None:
        class Odd(Echo):
            def validate(self, req):
                raise ncp.Declined("bad \ud800 value " + "x" * 400)

        owner = ncp.Owner(CONTRACT, Odd())
        session = str(uuid.uuid4())
        ack = F.identity(owner.handle(open_request(session)))
        reply = response_of(owner.handle(request(session, 1, "echo", ack, {})))
        self.assertEqual(reply["code"], "body_invalid")
        self.assertEqual(len(reply["body"]["detail"]), 256)

    def test_several_contracts_and_the_handler_hooks(self) -> None:
        v2 = ncp.Contract.from_bytes(CONTRACT.data.replace(b'"version":"1"', b'"version":"2"'))
        events: list[str] = []

        class Hooked(Echo):
            def open(self, info):
                events.append(f"open {info.contract.version} {sorted(info.features)}")
                if info.run == "refuse":
                    raise ncp.Refused("not today")
                return {"x.feature": {"granted": True}, "not.asked": {}}

            def execute(self, req):
                return {"version": req.contract.version, "features": dict(req.features), "run": req.run}

            def close(self, reason):
                events.append(f"close {reason}")

        owner = ncp.Owner([CONTRACT, v2], Hooked())
        session = str(uuid.uuid4())
        refused = response_of(owner.handle(open_request(session, contract=v2.identity, run="refuse")))
        self.assertEqual((refused["code"], refused["body"]["detail"]), ("refused", "not today"))
        opened = owner.handle(open_request(session, contract=v2.identity, run="r1", features={"x.feature": {}}))
        self.assertEqual(response_of(opened)["body"]["features"], {"x.feature": {"granted": True}})
        result = response_of(owner.handle(request(session, 1, "echo", F.identity(opened), {})))
        self.assertEqual(result["body"], {"version": "2", "features": {"x.feature": {"granted": True}}, "run": "r1"})
        owner.finish("lost")
        owner.finish("lost")
        self.assertEqual(events, ["open 2 []", "open 2 ['x.feature']", "close lost"])

    def test_the_request_schema_of_the_contract(self) -> None:
        typed = ncp.Contract.from_bytes(
            json.dumps(
                {
                    "ncp_contract": 1,
                    "application": "echo",
                    "version": "3",
                    "operations": {
                        "echo": {
                            "ncp.schema": {
                                "request": {
                                    "type": "object",
                                    "required": ["v"],
                                    "properties": {"v": {"ncp.array": {"dtype": "f64", "shape": [None, 3]}}},
                                }
                            }
                        }
                    },
                    "streams": {},
                }
            ).encode()
        )
        owner = ncp.Owner(typed, Echo())
        session = str(uuid.uuid4())
        ack = F.identity(owner.handle(open_request(session, contract=typed.identity)))
        ok = owner.handle(request(session, 1, "echo", ack, {"v": F.Array("f64", [2, 3], bytes(48))}))
        self.assertEqual(response_of(ok)["outcome"], "ok")
        bad = response_of(owner.handle(request(session, 2, "echo", F.identity(ok), {"v": F.Array("f64", [3], bytes(24))})))
        self.assertEqual((bad["outcome"], bad["code"]), ("declined", "body_invalid"))
        self.assertIn("shape", bad["body"]["detail"])


class _MemoryChannel:
    """An in-memory channel to an owner that can drop frames in both directions."""

    lossy = True
    local = True

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


class _Lossless(_MemoryChannel):
    lossy = False

    def close(self) -> None:
        pass


class ClientTests(unittest.TestCase):
    def test_lossy_channel_retries_without_reexecution(self) -> None:
        executed = []

        class Counting(Echo):
            def execute(self, req):
                executed.append(req.body)
                return req.body

        channel = _MemoryChannel(ncp.Owner(CONTRACT, Counting()), drop_requests={2}, drop_responses={4, 5})
        client = ncp.Client(channel, CONTRACT, retries=3)
        client.open()
        self.assertEqual(client.call("echo", {"n": 1}).body, {"n": 1})  # sends 2 (dropped) and 3
        self.assertEqual(client.call("echo", {"n": 2}).body, {"n": 2})  # sends 4, 5 (responses lost) and 6
        self.assertEqual(executed, [{"n": 1}, {"n": 2}])  # each request executed exactly once

    def test_a_declined_request_advances_the_session(self) -> None:
        client = ncp.Client(_Lossless(make_owner()), CONTRACT)
        client.open()
        with self.assertRaises(ncp.Declined) as caught:
            client.call("echo", {"invalid": True})
        self.assertEqual((caught.exception.code, caught.exception.detail), ("body_invalid", "invalid requested"))
        self.assertEqual(client.state.seq, 1)
        self.assertEqual(client.call("echo", {"ok": 1}).seq, 2)
        with self.assertRaises(ncp.Declined) as caught:
            client.call("missing", {})
        self.assertEqual(caught.exception.code, "unknown_op")

    def test_a_declined_request_sent_twice_is_still_declined(self) -> None:
        # The answer is kept, so a repeated copy cannot run (P-1, decision D1).
        channel = _MemoryChannel(make_owner(), drop_responses={2})
        client = ncp.Client(channel, CONTRACT, retries=3)
        client.open()
        with self.assertRaises(ncp.Declined):
            client.call("echo", {"invalid": True})
        self.assertFalse(client.ended)

    def test_session_expired_leaves_the_request_possibly_executed(self) -> None:
        client = ncp.Client(
            _ScriptedChannel([("ok", None, _OPEN), ("ended", "session_expired", {})]), CONTRACT, bound=F.HANDSHAKE_BOUND
        )
        client.open()
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"n": 1})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("session_expired", ncp.Executed.UNKNOWN))
        self.assertTrue(client.ended)

    def test_a_failing_validation_ends_the_session_as_a_failing_execution(self) -> None:
        class Failing(Echo):
            def validate(self, req):
                raise KeyError("a defect in the application")

        client = ncp.Client(_Lossless(ncp.Owner(CONTRACT, Failing())), CONTRACT)
        client.open()
        with _Silence(), self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"n": 1})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", ncp.Executed.UNKNOWN))

    def test_owner_failure(self) -> None:
        client = ncp.Client(_Lossless(make_owner()), CONTRACT)
        client.open()
        with _Silence(), self.assertRaises(ncp.Ended) as caught:
            client.call("fail", {})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", ncp.Executed.UNKNOWN))
        with self.assertRaises(ncp.UsageError):
            client.call("echo", {})

    def test_a_closed_stream_ends_the_session_with_the_request_possibly_executed(self) -> None:
        channel = ncp.spawn([sys.executable, "-I", os.path.join(HERE, "echo_owner.py")])
        client = ncp.Client(channel, CONTRACT, timeout=10)
        client.open()
        self.assertEqual(client.call("echo", {"n": 1}).body, {"n": 1})
        channel.process.kill()
        channel.process.wait(timeout=10)
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"n": 2})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("local.closed", ncp.Executed.UNKNOWN))
        self.assertTrue(client.ended)
        with self.assertRaises(ncp.UsageError):
            client.call("echo", {"n": 3})
        client.close()

    def test_a_bad_response_header_ends_the_session(self) -> None:
        class BadHeaderAfterOpen(_Lossless):
            def receive(self, bound: int, timeout):
                if self.sent > 1:  # a byte stream reports a bad header before it reads the rest
                    raise F.FrameError("frame magic")
                return super().receive(bound, timeout)

        client = ncp.Client(BadHeaderAfterOpen(make_owner()), CONTRACT)
        client.open()
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {})
        self.assertEqual(caught.exception.code, "local.bad_frame")
        self.assertTrue(client.ended)

    def test_the_client_as_a_context_manager(self) -> None:
        channel = _Lossless(make_owner())
        with ncp.Client(channel, CONTRACT) as client:
            self.assertTrue(client.opened)
            self.assertRegex(client.nonce, r"\A[0-9a-f]{32}\Z")
            self.assertEqual(client.ping().body, {})
        self.assertTrue(channel.owner.closed)

    def test_call_all_sends_every_request_before_it_reads_a_response(self) -> None:
        log: list[tuple[str, int]] = []

        class Logged(_Lossless):
            def __init__(self, name: int) -> None:
                super().__init__(make_owner())
                self.name = name

            def send(self, frame: bytes) -> None:
                log.append(("send", self.name))
                super().send(frame)

            def receive(self, bound: int, timeout):
                log.append(("receive", self.name))
                return super().receive(bound, timeout)

        clients = [ncp.Client(Logged(name), CONTRACT) for name in range(4)]
        for client in clients:
            client.open()
        log.clear()
        results = ncp.call_all(clients, "echo", [{"agent": name} for name in range(4)])
        self.assertEqual([result.body for result in results], [{"agent": name} for name in range(4)])
        self.assertEqual(log, [("send", name) for name in range(4)] + [("receive", name) for name in range(4)])

    def test_call_all_returns_the_error_of_one_session_in_its_place(self) -> None:
        clients = [ncp.Client(_Lossless(make_owner()), CONTRACT, bound=ncp.HANDSHAKE_BOUND) for _ in range(4)]
        for client in clients:
            client.open()
        with _Silence(), self.assertRaises(ncp.Ended):
            clients[1].call("fail", {})
        bodies = [{"n": 0}, {"n": 1}, {"blob": "x" * ncp.HANDSHAKE_BOUND}, {"n": 3}]
        results = ncp.call_all(clients, "echo", bodies)
        self.assertIsInstance(results[1], ncp.UsageError)  # the session had ended
        self.assertIsInstance(results[2], ncp.UsageError)  # above the bound: refused before sending
        self.assertEqual([results[0].body, results[3].body], [{"n": 0}, {"n": 3}])
        again = ncp.call_all([clients[0], clients[2], clients[3]], "echo", [{"m": 0}, {"m": 2}, {"m": 3}])
        self.assertEqual([result.body for result in again], [{"m": 0}, {"m": 2}, {"m": 3}])
        with self.assertRaises(ValueError):
            ncp.call_all([clients[0], clients[0]], "echo", [{}, {}])

    def test_the_machine_is_pure(self) -> None:
        # The client rules are functions of an immutable state: equal inputs give equal outputs.
        state = C.new_state(CONTRACT, session=str(uuid.uuid4()), bound=F.HANDSHAKE_BOUND)
        one, frame_one = C.request(state, "open")
        two, frame_two = C.request(state, "open")
        self.assertEqual((one, frame_one), (two, frame_two))
        self.assertIsNone(state.pending)


_OPEN = {"bound": F.HANDSHAKE_BOUND, "nonce": "0" * 32, "features": {}, "application": "echo"}


class _ScriptedChannel:
    """Answers each request with the next scripted (outcome, code, body)."""

    lossy = False
    local = True

    def __init__(self, script: list[tuple[str, str | None, object]]) -> None:
        self.script, self.inbox = list(script), []

    def send(self, frame: bytes) -> None:
        req = F.decode(frame, F.MAX_BOUND).message
        outcome, code, body = self.script.pop(0)
        self.inbox.append(
            F.encode(
                {
                    "ncp": 2,
                    "session": req["session"],
                    "seq": req["seq"],
                    "request": F.identity(frame),
                    "outcome": outcome,
                    "code": code,
                    "body": body,
                }
            )
        )

    def receive(self, bound: int, timeout: float | None) -> bytes:
        return self.inbox.pop(0)

    def close(self) -> None:
        pass


class ForwardCompatibilityTests(unittest.TestCase):
    OPEN = {**_OPEN, "contract": CONTRACT.identity, "implementation": "later", "later": ["x"]}

    def client(self, *script: tuple[str, str | None, object]) -> ncp.Client:
        client = ncp.Client(_ScriptedChannel([("ok", None, self.OPEN), *script]), CONTRACT, bound=F.HANDSHAKE_BOUND)
        self.assertEqual(client.open()["later"], ["x"])  # unknown open members are ignored
        return client

    def test_unknown_codes_are_handled_by_outcome(self) -> None:
        client = self.client(("declined", "later_decline", {}), ("ended", "later_end", {}))
        with self.assertRaises(ncp.Declined) as declined:
            client.call("echo", {})
        self.assertEqual((declined.exception.code, client.state.seq), ("later_decline", 1))
        with self.assertRaises(ncp.Ended) as ended:
            client.call("echo", {})
        self.assertEqual((ended.exception.code, ended.exception.executed), ("later_end", ncp.Executed.UNKNOWN))

    def test_a_rejected_call_ends_the_session_possibly_executed(self) -> None:
        # Rule 7.6.4: only a lost session, opened again by a delayed copy of open, rejects the
        # call of a client that follows section 7.6; an earlier copy may have executed.
        client = self.client(("rejected", "later_reason", {}))
        with self.assertRaises(ncp.Ended) as ended:
            client.call("echo", {})
        self.assertEqual((ended.exception.code, ended.exception.executed), ("later_reason", ncp.Executed.UNKNOWN))
        self.assertTrue(client.state.ended)
        with self.assertRaises(ncp.UsageError):
            client.call("echo", {})

    def test_a_code_outside_the_format_is_a_bad_frame(self) -> None:
        client = self.client(("rejected", "Later-Reason", {}))
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {})
        self.assertEqual(caught.exception.code, "local.bad_frame")


class TapTests(unittest.TestCase):
    def test_a_tap_records_a_frame_before_sending_it(self) -> None:
        path = os.path.join(tempfile.mkdtemp(prefix="ncp-tap-"), "sent.ncpt")

        def broken(_: bytes) -> None:
            raise BrokenPipeError("the peer is gone")

        frame = F.encode({"a": 1})
        with T.Tap(path) as tap:
            channel = ncp.StreamChannel(lambda buffer: 0, broken, -1, tap=tap)
            with self.assertRaises(BrokenPipeError):
                channel.send(frame)
        transcript = T.read(path)
        self.assertEqual([(r.kind, r.frame) for r in transcript.records], [(T.SENT, frame)])
        self.assertTrue(transcript.closed)
        self.assertTrue(transcript.chain_ok)

    def test_a_tap_keeps_its_records_when_the_program_dies(self) -> None:
        directory = tempfile.mkdtemp(prefix="ncp-tap-")
        frame = F.encode({"a": 1})
        program = (
            "import os, sys; sys.path.insert(0, sys.argv[1]); from ncp import transcript as T; "
            "tap = T.Tap(sys.argv[2], buffered=sys.argv[3] == '1'); "
            "[tap.record(T.SENT, bytes.fromhex(sys.argv[4])) for _ in range(3)]; os._exit(1)"
        )
        for name, buffered, expected in (("direct.ncpt", "0", 3), ("buffered.ncpt", "1", 0)):
            path = os.path.join(directory, name)
            root = os.path.join(HERE, "..")
            subprocess.run([sys.executable, "-I", "-c", program, root, path, buffered, frame.hex()], check=False)
            try:
                transcript = T.read(path)
                records = len(transcript.records)
                self.assertFalse(transcript.closed)  # no end record: the program died
            except F.FrameError:
                records = 0  # the buffered tap had not even written the file magic
            self.assertEqual(records, expected, name)


class StreamTests(unittest.TestCase):
    def test_subscriber_rules(self) -> None:
        sent: list[bytes] = []
        publisher = ncp.Publisher("sensors/camera-0", CONTRACT.identity, sent.append)
        self.assertRegex(publisher.stream, r"\Asensors/camera-0/[0-9a-f]{16}\Z")
        for index in range(5):
            publisher.publish({"i": index})
        subscriber = ncp.Subscriber({CONTRACT.identity})
        self.assertEqual(subscriber.receive(sent[0]).status, "accepted")
        self.assertEqual(subscriber.receive(sent[0]).status, "repeat")
        delivery = subscriber.receive(sent[3])
        self.assertEqual((delivery.status, delivery.lost), ("accepted", 2))
        changed = F.encode({**F.decode(sent[3], F.MAX_BOUND).message, "body": {"i": 99}})
        self.assertEqual(subscriber.receive(changed).status, "conflict")
        forged = F.encode(
            {"ncp": 2, "stream": publisher.stream, "seq": 5, "prev": OTHER, "contract": CONTRACT.identity, "body": {}}
        )
        self.assertEqual(subscriber.receive(forged).status, "broken_chain")
        self.assertEqual(subscriber.receive(sent[4]).status, "accepted")
        other = ncp.Publisher("x", OTHER, sent.append)
        self.assertEqual(subscriber.receive(other.publish({})).status, "unknown_contract")
        self.assertEqual(subscriber.receive(b"garbage").status, "bad_frame")

    def test_a_restarted_publisher_is_a_new_stream(self) -> None:
        sent: list[bytes] = []
        first = ncp.Publisher("cam", CONTRACT.identity, sent.append)
        for index in range(4):
            first.publish({"i": index})
        second = ncp.Publisher("cam", CONTRACT.identity, sent.append)
        second.publish({"i": 100})
        subscriber = ncp.Subscriber({CONTRACT.identity})
        statuses = [subscriber.receive(frame).status for frame in sent]
        self.assertEqual(statuses, ["accepted"] * 5)

    def test_a_late_subscriber_joins_and_an_end_message_ends(self) -> None:
        sent: list[bytes] = []
        publisher = ncp.Publisher("telemetry", CONTRACT.identity, sent.append, exact=True)
        for index in range(3):
            publisher.publish({"i": index})
        publisher.end({"reason": "done"})
        with self.assertRaises(ValueError):
            publisher.publish({})
        subscriber = ncp.Subscriber({CONTRACT.identity})
        joined = subscriber.receive(sent[1])
        self.assertEqual((joined.status, joined.lost), ("joined", 0))
        end = subscriber.receive(sent[3])
        self.assertEqual((end.status, end.lost, end.end), ("accepted", 1, True))
        late = F.encode(
            {"ncp": 2, "stream": "telemetry", "seq": 5, "prev": F.identity(sent[3]), "contract": CONTRACT.identity,
             "body": {}}
        )
        self.assertEqual(subscriber.receive(late).status, "conflict")

    def test_the_subscriber_keeps_a_bounded_number_of_streams(self) -> None:
        subscriber = ncp.Subscriber({CONTRACT.identity}, max_streams=2)
        frames = {}
        for name in "abc":
            frames[name] = ncp.Publisher(name, CONTRACT.identity, lambda f: None, exact=True).publish({})
            subscriber.receive(frames[name])
        self.assertEqual(subscriber.receive(frames["c"]).status, "repeat")
        self.assertEqual(subscriber.receive(frames["a"]).status, "accepted")  # forgotten, so new

    def test_the_subscriber_applies_its_bound_to_each_frame(self) -> None:
        # Rule 8.4: a frame over the subscriber's bound is a bad frame, and changes no stream state.
        subscriber = ncp.Subscriber({CONTRACT.identity}, bound=F.HANDSHAKE_BOUND)
        publisher = ncp.Publisher("big", CONTRACT.identity, lambda f: None, exact=True)
        large = publisher.publish({"blob": F.Array("u8", [F.HANDSHAKE_BOUND], bytes(F.HANDSHAKE_BOUND))})
        self.assertGreater(len(large), F.HANDSHAKE_BOUND)
        self.assertEqual(subscriber.receive(large).status, "bad_frame")
        self.assertEqual(subscriber.receive(publisher.publish({})).status, "joined")


class TranscriptTests(unittest.TestCase):
    def run_session(self, path: str, key=None) -> None:
        tap = ncp.Tap(path, recorder="test", key=key)
        channel = ncp.spawn([sys.executable, "-I", os.path.join(HERE, "echo_owner.py")], tap=tap)
        with ncp.Client(channel, CONTRACT) as client:
            for index in range(3):
                client.call("echo", {"i": index})
            with self.assertRaises(ncp.Declined):
                client.call("echo", {"invalid": True})
        tap.close()

    def test_complete_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "t.ncpt")
            self.run_session(path)
            report = ncp.verify_transcript(path)
            self.assertTrue(report.ok, report)
            self.assertEqual((report.version, report.closed, report.chain_ok), (2, True, True))
            (session,) = report.sessions.values()
            self.assertEqual(
                (session.role, session.requests, session.declined, session.complete, session.problems),
                ("client", 6, 1, True, []),
            )
            self.assertEqual(report.header["recorder"], "test")

    def test_changed_truncated_and_torn_transcripts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "t.ncpt")
            self.run_session(path)
            with open(path, "rb") as handle:
                data = handle.read()
            transcript = T.read(path)
            # A changed byte in a frame: the frame's digest and the record chain both catch it.
            changed = bytearray(data)
            changed[len(data) // 2] ^= 1
            with open(path, "wb") as handle:
                handle.write(bytes(changed))
            self.assertFalse(ncp.verify_transcript(path).ok)
            # A torn last record: the prefix verifies, and the report says where the file ends.
            with open(path, "wb") as handle:
                handle.write(data[: len(data) - 50])
            report = ncp.verify_transcript(path)
            self.assertIsNotNone(report.truncated_at)
            self.assertFalse(report.closed)
            self.assertEqual(report.chain_ok, True)
            (session,) = report.sessions.values()
            self.assertGreaterEqual(session.requests, 5)
            # A response replaced by another valid frame, without the record chain: the chain breaks.
            records = transcript.records
            message = F.decode(records[3].frame, F.MAX_BOUND).message
            records[3] = T.Record(records[3].kind, records[3].time_ns, F.encode({**message, "body": {"i": 42}}),
                                  records[3].chain)
            header_end = 12 + struct.unpack(">I", data[8:12])[0]
            out = bytearray(data[:header_end])
            for record in records:
                out += T.RECORD.pack(record.kind, record.time_ns, len(record.frame)) + record.frame + record.chain
            with open(path, "wb") as handle:
                handle.write(bytes(out))
            report = ncp.verify_transcript(path)
            self.assertEqual(report.chain_ok, False)

    def test_a_keyed_transcript_verifies_only_with_the_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "k.ncpt")
            tap = ncp.Tap(path, key=KEY)
            owner = ncp.Owner(CONTRACT, Echo(), key=KEY)

            class Direct(_Lossless):
                def send(self, frame: bytes) -> None:
                    tap.record(T.SENT, frame)
                    response = owner.handle(frame)
                    tap.record(T.RECEIVED, response)
                    self.queue.append(response)

            with ncp.Client(Direct(owner), CONTRACT, key=KEY) as client:
                client.call("echo", {"a": 1})
            tap.close()
            self.assertTrue(ncp.verify_transcript(path, key=KEY).ok)
            self.assertFalse(ncp.verify_transcript(path).ok)
            self.assertFalse(ncp.verify_transcript(path, key=bytes(reversed(KEY))).ok)

    def test_version_1_transcripts_are_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "v1.ncpt")
            frame = request(str(uuid.uuid4()), 0, "open", None, {})
            with open(path, "wb") as handle:
                handle.write(T.MAGIC_V1 + T.RECORD.pack(T.SENT, 5, len(frame)) + frame)
            report = ncp.verify_transcript(path)
            self.assertEqual((report.version, report.records, report.chain_ok), (1, 1, None))


def _certificates(directory: str) -> dict[str, str] | None:
    """A certificate authority, a server, and a client, made by openssl for the test."""
    if shutil.which("openssl") is None:
        return None
    paths = {name: os.path.join(directory, name) for name in ("ca.pem", "ca.key", "other.pem", "other.key")}

    def run(*arguments: str) -> None:
        subprocess.run(["openssl", *arguments], check=True, capture_output=True)

    for authority in ("ca", "other"):
        run("req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-days", "2",
            "-subj", f"/CN={authority}", "-keyout", paths[f"{authority}.key"], "-out", paths[f"{authority}.pem"])
    for name, signer in (("server", "ca"), ("client", "ca"), ("stranger", "other")):
        key, csr, pem = (os.path.join(directory, f"{name}.{suffix}") for suffix in ("key", "csr", "pem"))
        extension = os.path.join(directory, f"{name}.ext")
        with open(extension, "w") as handle:
            handle.write("subjectAltName=DNS:localhost,IP:127.0.0.1\n")
        run("req", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes", "-subj", f"/CN={name}",
            "-keyout", key, "-out", csr)
        run("x509", "-req", "-in", csr, "-CA", paths[f"{signer}.pem"], "-CAkey", paths[f"{signer}.key"],
            "-CAcreateserial", "-days", "2", "-extfile", extension, "-out", pem)
        paths[f"{name}.pem"], paths[f"{name}.key"] = pem, key
    return paths


class BindingTests(unittest.TestCase):
    def test_tcp_loopback_session(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        try:
            host, port = server.address[:2]
            with ncp.Client(ncp.connect_tcp(host, port), CONTRACT) as client:
                self.assertEqual(client.call("echo", {"tcp": True}).body, {"tcp": True})
        finally:
            server.stop()

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "no Unix domain sockets")
    def test_unix_socket_session(self) -> None:
        directory = tempfile.mkdtemp(prefix="ncp-")
        os.chmod(directory, 0o700)
        path = os.path.join(directory, "owner.sock")
        server = ncp.UnixServer(make_owner, path).start()
        try:
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            clients = [ncp.Client(ncp.connect_unix(path), CONTRACT) for _ in range(3)]
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

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "no Unix domain sockets")
    def test_connect_unix_tries_a_refused_connection_again(self) -> None:
        directory = tempfile.mkdtemp(prefix="ncp-")
        os.chmod(directory, 0o700)
        path = os.path.join(directory, "owner.sock")
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        listener.listen(1)
        clients = 8
        results: list[object] = []

        def owner() -> None:
            time.sleep(0.2)
            for _ in range(clients):
                connection, _ = listener.accept()
                channel = ncp.StreamChannel.from_socket(connection)
                threading.Thread(target=ncp.serve, args=(make_owner(), channel), daemon=True).start()

        def client(index: int) -> None:
            try:
                with ncp.Client(ncp.connect_unix(path), CONTRACT) as session:
                    results.append(session.call("echo", {"i": index}).body == {"i": index})
            except Exception as error:  # noqa: BLE001 - reported by the assertion below
                results.append(error)

        threads = [threading.Thread(target=owner)] + [threading.Thread(target=client, args=(i,)) for i in range(clients)]
        try:
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(30)
        finally:
            listener.close()
            os.unlink(path)
            os.rmdir(directory)
        self.assertEqual(results, [True] * clients)

    @unittest.skipUnless(os.environ.get("NCP_RUST_EXAMPLES"), "set NCP_RUST_EXAMPLES to the Rust examples directory")
    def test_python_client_with_the_rust_owner(self) -> None:
        channel = ncp.spawn([os.path.join(os.environ["NCP_RUST_EXAMPLES"], "echo_owner")])
        with ncp.Client(channel, CONTRACT) as client:
            self.assertTrue(client.owner["implementation"].startswith("ncp-rust/"))
            values = {d: F.Array(d, [3], bytes(range(3 * F.DTYPES[d][1]))) for d in F.DTYPES}
            result = client.call("echo", {"v": values, "n": -(2**53 - 1), "s": "é😀"})
            self.assertEqual(result.body["n"], -(2**53 - 1))
            self.assertEqual(result.body["s"], "é😀")
            for dtype, value in values.items():
                self.assertEqual(result.body["v"][dtype], value)
            with self.assertRaises(ncp.Declined):
                client.call("echo", {"invalid": True})
            self.assertEqual(client.ping().body, {})
            with self.assertRaises(ncp.Ended) as ended:
                client.call("fail", {})
            self.assertEqual((ended.exception.code, ended.exception.executed), ("owner_failure", ncp.Executed.UNKNOWN))
        self.assertEqual(channel.process.wait(timeout=10), 0)

    def test_a_damaged_body_is_a_bad_frame(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        try:
            host, port = server.address[:2]
            damaged = bytearray(F.encode({"a": "x" * 70_000}))
            damaged[40_000] ^= 1
            with socket.create_connection((host, port)) as sock:
                channel = ncp.StreamChannel.from_socket(sock)
                sock.sendall(damaged)
                reply = F.decode(channel.receive(F.MAX_BOUND, 10), F.MAX_BOUND).message
            self.assertEqual(reply["code"], "bad_frame")
        finally:
            server.stop()

    def test_stop_ends_each_session_with_the_shutdown_response(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        host, port = server.address[:2]
        client = ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=10)
        client.open()
        self.assertEqual(client.call("echo", {"n": 1}).body, {"n": 1})
        server.stop()
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"n": 2})
        # The owner stopped before it read the request: it was not executed (rule 9.1.9).
        self.assertIn((caught.exception.code, caught.exception.executed),
                      {("shutdown", ncp.Executed.NO), ("local.closed", ncp.Executed.UNKNOWN)})
        client.close()

    def test_an_idle_session_ends_with_the_shutdown_response(self) -> None:
        server = ncp.TcpServer(make_owner, limits=ncp.Limits(idle_timeout=0.2)).start()
        try:
            host, port = server.address[:2]
            client = ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=10)
            client.open()
            time.sleep(0.5)
            with self.assertRaises(ncp.Ended) as caught:
                client.call("echo", {})
            self.assertIn(caught.exception.code, {"shutdown", "local.closed"})
        finally:
            server.stop()

    def test_a_full_server_refuses_an_open(self) -> None:
        server = ncp.TcpServer(make_owner, limits=ncp.Limits(max_sessions=1)).start()
        try:
            host, port = server.address[:2]
            first = ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=10)
            first.open()
            second = ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=10)
            with self.assertRaises(ncp.Rejected) as caught:
                second.open()
            self.assertEqual(caught.exception.code, "refused")
            first.close()
        finally:
            server.stop()

    def test_tls_with_certificates_on_both_sides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = _certificates(directory)
            if paths is None:
                self.skipTest("no openssl command")
            server_tls = ncp.TlsConfig(paths["ca.pem"], paths["server.pem"], paths["server.key"])
            server = ncp.TcpServer(make_owner, tls=server_tls).start()
            try:
                host, port = server.address[:2]
                tls = ncp.TlsConfig(paths["ca.pem"], paths["client.pem"], paths["client.key"], server_name="localhost")
                with ncp.Client(ncp.connect_tcp(host, port, tls=tls), CONTRACT) as client:
                    self.assertEqual(client.call("echo", {"tls": True}).body, {"tls": True})
                stranger = ncp.TlsConfig(paths["ca.pem"], paths["stranger.pem"], paths["stranger.key"],
                                         server_name="localhost")
                without_name = ncp.TlsConfig(paths["ca.pem"], paths["client.pem"], paths["client.key"])
                with self.assertRaises(ValueError):  # section 13.3: the client checks the server's name
                    ncp.connect_tcp(host, port, tls=without_name)
                with self.assertRaises((ssl.SSLError, OSError, ncp.Ended)):
                    with ncp.Client(ncp.connect_tcp(host, port, tls=stranger), CONTRACT, timeout=5) as client:
                        client.call("echo", {})
            finally:
                server.stop()

    def test_authenticated_session(self) -> None:
        server = ncp.TcpServer(lambda: make_owner(key=KEY)).start()
        try:
            host, port = server.address[:2]
            with ncp.Client(ncp.connect_tcp(host, port), CONTRACT, key=KEY) as client:
                self.assertEqual(client.call("echo", {"a": 1}).body, {"a": 1})
            client = ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=5)
            with self.assertRaises(ncp.Ended) as caught:
                client.open()  # the owner finds the unauthenticated frame bad
            self.assertIn(caught.exception.code, {"local.bad_frame", "local.closed"})
        finally:
            server.stop()

    def test_a_failed_connection_does_not_stop_the_server(self) -> None:
        original = ncp.StreamChannel.from_socket
        lock = threading.Lock()
        failed = threading.Event()

        def fail_once(sock, **options):
            with lock:
                first = not failed.is_set()
                failed.set()
            if first:
                raise OSError(22, "Invalid argument")
            return original(sock, **options)

        ncp.StreamChannel.from_socket = staticmethod(fail_once)
        server = ncp.TcpServer(make_owner).start()
        try:
            host, port = server.address[:2]
            socket.create_connection((host, port)).close()
            self.assertTrue(failed.wait(10))
            with ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=10) as client:
                self.assertEqual(client.call("echo", {"x": 1}).body, {"x": 1})
        finally:
            ncp.StreamChannel.from_socket = original
            server.stop()

    def test_stop_closes_the_listening_socket(self) -> None:
        server = ncp.TcpServer(make_owner).start()
        host, port = server.address[:2]
        server.stop()
        server._thread.join(timeout=5)
        self.assertFalse(server._thread.is_alive())
        with self.assertRaises(OSError):
            socket.create_connection((host, port), timeout=2).close()

    def test_a_defect_of_the_owner_factory_is_reported(self) -> None:
        calls = []

        def factory():
            calls.append(None)
            if len(calls) == 1:
                raise ValueError("defective factory")
            return make_owner()

        server = ncp.TcpServer(factory).start()
        try:
            host, port = server.address[:2]
            with self.assertLogs("ncp", level="ERROR") as logs:
                socket.create_connection((host, port)).close()
                with ncp.Client(ncp.connect_tcp(host, port), CONTRACT, timeout=10) as client:
                    self.assertEqual(client.call("echo", {"x": 3}).body, {"x": 3})
        finally:
            server.stop()
        self.assertTrue(any("defective factory" in line for line in logs.output))

    def test_a_tcp_connection_without_nodelay_is_not_used(self) -> None:
        class Refusing:
            family = socket.AF_INET

            def setsockopt(self, level, option, value):
                if option == socket.TCP_NODELAY:
                    raise OSError(22, "Invalid argument")

            recv_into = sendall = close = staticmethod(lambda *arguments: None)
            fileno = staticmethod(lambda: -1)

        with self.assertRaises(OSError):
            ncp.StreamChannel.from_socket(Refusing())

    def test_remote_addresses_need_an_option(self) -> None:
        with self.assertRaises(ValueError):
            ncp.connect_tcp("192.0.2.1", 1)

    def test_bad_frame_rule_and_slow_sender(self) -> None:
        left, right = socket.socketpair()
        thread = threading.Thread(
            target=ncp.serve, args=(make_owner(), ncp.StreamChannel.from_socket(right)), kwargs={"frame_timeout": 0.2}
        )
        thread.start()
        left.sendall(b"NCP\x02" + struct.pack(">II", 4, 0) + b"{}  " + bytes(32))  # wrong digest
        reply = ncp.StreamChannel.from_socket(left).receive(F.MAX_BOUND, 2.0)
        self.assertEqual(response_of(reply)["code"], "bad_frame")
        thread.join(2.0)
        self.assertFalse(thread.is_alive())
        left.close()
        left2, right2 = socket.socketpair()
        thread = threading.Thread(
            target=ncp.serve, args=(make_owner(), ncp.StreamChannel.from_socket(right2)), kwargs={"frame_timeout": 0.2}
        )
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
            clients = [ncp.Client(ncp.connect_tcp(host, port), CONTRACT) for _ in range(8)]
            for client in clients:
                client.open()
            results = ncp.call_all(clients, "echo", [{"agent": index} for index in range(8)])
            self.assertEqual([result.body for result in results], [{"agent": index} for index in range(8)])
            with _Silence():
                failures = ncp.call_all(clients, "fail", [{}] * 8)
            self.assertTrue(all(isinstance(item, ncp.Ended) for item in failures))
            for client in clients:
                client.close()
        finally:
            server.stop()

    def test_spawn_ends_the_child_and_keeps_its_standard_error(self) -> None:
        program = "import sys, time; print('hello from the child', file=sys.stderr, flush=True); time.sleep(60)"
        channel = ncp.spawn([sys.executable, "-I", "-c", program], grace=0.2, capture_stderr=True)
        time.sleep(0.5)
        started = time.monotonic()
        channel.close()
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNotNone(channel.returncode)
        self.assertIn("hello from the child", list(channel.stderr_tail))


class ContractTests(unittest.TestCase):
    def test_identity_is_the_digest_of_exact_bytes(self) -> None:
        self.assertEqual(CONTRACT.identity, hashlib.sha256(CONTRACT.data).hexdigest())
        spaced = ncp.Contract.from_bytes(CONTRACT.data.replace(b",", b", "))
        self.assertNotEqual(spaced.identity, CONTRACT.identity)
        for document in (
            b'{"ncp_contract":2}',
            b'{"ncp_contract":true,"application":"a","version":"1","operations":{},"streams":{}}',
            b'{"ncp_contract":1,"application":"a","version":"1","operations":{"close":{}},"streams":{}}',
            b'{"ncp_contract":1,"application":"a","version":"1","operations":{"ncp.x":{}},"streams":{}}',
        ):
            with self.subTest(document=document), self.assertRaises(ncp.ContractError):
                ncp.Contract.from_bytes(document)


class LockstepTests(unittest.TestCase):
    CONTRACT = ncp.Contract.from_bytes(
        b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{},"look":{}},"streams":{}}'
    )

    class World:
        def __init__(self) -> None:
            self.position = 0

        def validate(self, request):
            pass

        def execute(self, request):
            self.position += request.body.get("dx", 0)
            if request.body.get("fail"):
                raise RuntimeError("the world failed half way")  # after it changed its state
            return {"position": self.position}

        def state(self):
            return f"p{self.position}"

    class Held(_Lossless):
        """A channel that holds back the requests once the connection breaks, as a slow network
        can."""

        def __init__(self, owner) -> None:
            super().__init__(owner)
            self.broken, self.held = False, []

        def send(self, frame: bytes) -> None:
            if self.broken:
                self.held.append(bytes(frame))
                raise ConnectionResetError("the connection broke")
            super().send(frame)

    def session(self, lockstep, feature: bool = True) -> ncp.Client:
        return ncp.Client(
            self.Held(ncp.Owner(self.CONTRACT, lockstep)),
            self.CONTRACT,
            features={"ncp.lockstep": {}} if feature else None,
        )

    def test_steps_carry_the_tick_and_the_state(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        owner = ncp.Owner(self.CONTRACT, lockstep)
        client = ncp.Client(_Lossless(owner), self.CONTRACT, features={"ncp.lockstep": {}})
        stepper = ncp.LockstepClient(client)
        self.assertEqual((stepper.tick, stepper.state), (0, None))
        result = stepper.step("step", {"dx": 2})
        self.assertEqual(result.body["position"], 2)
        self.assertEqual((stepper.tick, stepper.state), (1, "p2"))
        self.assertEqual(client.call("look", {}).body, {"position": 2})  # not a lockstep operation
        self.assertEqual(result.body["ncp.tick"]["request"], result.request)
        with self.assertRaises(ncp.Declined) as caught:
            client.call("step", {"dx": 1, "ncp.tick": {"tick": 5, "state": "p2"}})
        self.assertIn("tick", caught.exception.detail)
        with self.assertRaises(ncp.Declined):
            client.call("step", {"dx": 1, "ncp.tick": {"tick": 2, "state": "p9"}})
        self.assertEqual(lockstep.tick, 1)

    def test_a_new_session_tells_whether_the_last_step_ran(self) -> None:
        for lose, expected in (("response", ncp.Executed.YES), ("request", ncp.Executed.NO)):
            with self.subTest(lose=lose):
                lockstep = ncp.Lockstep(self.World(), ["step"])

                class Breaking(_Lossless):
                    def __init__(self, owner) -> None:
                        super().__init__(owner)
                        self.broken = False

                    def send(self, frame: bytes) -> None:
                        if self.broken:
                            if lose == "response":
                                self.owner.handle(frame)  # the owner executes; the answer is lost
                            raise ConnectionResetError("the connection broke")
                        super().send(frame)

                channel = Breaking(ncp.Owner(self.CONTRACT, lockstep))
                stepper = ncp.LockstepClient(ncp.Client(channel, self.CONTRACT, features={"ncp.lockstep": {}}))
                stepper.step("step", {"dx": 1})
                channel.broken = True
                with self.assertRaises(ncp.Ended) as caught:
                    stepper.step("step", {"dx": 1})
                self.assertEqual(caught.exception.executed, ncp.Executed.UNKNOWN)
                self.assertEqual(stepper.uncertain[0], 2)
                self.assertEqual(stepper.uncertain[1], caught.exception.request)
                self.assertIsNotNone(caught.exception.request)
                fresh = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, lockstep)), self.CONTRACT,
                                   features={"ncp.lockstep": {}})
                self.assertEqual(stepper.recover(fresh), expected)
                self.assertEqual(stepper.tick, 2 if expected is ncp.Executed.YES else 1)
                stepper.step("step", {"dx": 10})

    def test_a_session_that_takes_over_the_ticks_fences_earlier_sessions(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        stepper.step("step", {"dx": 2})
        old = stepper.client.channel
        old.broken = True  # the connection breaks while the second step is on its way
        with self.assertRaises(ncp.Ended) as caught:
            stepper.step("step", {"dx": 1})
        self.assertEqual(caught.exception.executed, ncp.Executed.UNKNOWN)
        self.assertEqual(stepper.recover(self.session(lockstep)), ncp.Executed.NO)
        self.assertEqual(stepper.tick, 1)
        # The delayed request reaches the old session after the recovery: it never runs.
        response = F.decode(old.owner.handle(old.held[0]), F.MAX_BOUND)
        self.assertEqual((response.message["outcome"], response.message["code"]), ("declined", "body_invalid"))
        self.assertIn("does not hold the ticks", response.message["body"]["detail"])
        self.assertEqual(lockstep.tick, 1)
        self.assertEqual(stepper.step("step", {"dx": 10}).body["position"], 12)
        # A session that did not ask for the feature cannot step.
        plain = self.session(lockstep, feature=False)
        plain.open()
        with self.assertRaises(ncp.Declined) as declined:
            plain.call("step", {"dx": 1, "ncp.tick": {"tick": 3, "state": "p12"}})
        self.assertIn("does not hold the ticks", declined.exception.detail)

    def test_a_step_whose_application_fails_counts_as_executed(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        with self.assertRaises(ncp.Ended) as caught:
            stepper.step("step", {"dx": 4, "fail": True})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", ncp.Executed.UNKNOWN))
        self.assertEqual(lockstep.tick, 1)
        # The world moved before it failed, so the recovery must say that the step ran.
        self.assertEqual(stepper.recover(self.session(lockstep)), ncp.Executed.YES)
        self.assertEqual((stepper.tick, stepper.state), (1, "p4"))

    def test_a_recovery_that_finds_the_step_of_another_session_gives_no_verdict(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        first = ncp.LockstepClient(self.session(lockstep))
        first.client.channel.broken = True
        with self.assertRaises(ncp.Ended):
            first.step("step", {"dx": 1})
        second = ncp.LockstepClient(self.session(lockstep))  # takes over the ticks
        second.step("step", {"dx": 5})  # the step with the same tick, from another request
        with self.assertRaises(ncp.ProtocolError):
            first.recover(self.session(lockstep))
        self.assertIsNotNone(first.uncertain)

    def test_a_takeover_waits_for_a_checked_step_and_reads_its_tick(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        lockstep.open(ncp.OpenInfo("first", self.CONTRACT, None, {"ncp.lockstep": {}}))
        request = ncp.Request(
            "step", {"dx": 3, "ncp.tick": {"tick": 1, "state": None}}, [], 1, "first", "r1", self.CONTRACT, None, {}
        )
        lockstep.validate(request)
        granted = []
        waiting = threading.Thread(
            target=lambda: granted.append(
                lockstep.open(ncp.OpenInfo("second", self.CONTRACT, None, {"ncp.lockstep": {}}))["ncp.lockstep"]
            )
        )
        waiting.start()
        waiting.join(0.1)
        self.assertTrue(waiting.is_alive(), "the takeover did not wait")
        lockstep.execute(request)
        waiting.join(5)
        self.assertEqual(granted, [{"tick": 1, "state": "p3", "request": "r1"}])
        self.assertEqual(lockstep.holder, "second")


class PackageTests(unittest.TestCase):
    def test_implementation_names_the_package_version(self) -> None:
        import tomllib

        with open(os.path.join(HERE, "..", "pyproject.toml"), "rb") as f:
            version = tomllib.load(f)["project"]["version"]
        self.assertEqual(ncp.IMPLEMENTATION, f"ncp-python/{version}")

    def test_the_package_ships_the_conformance_vectors(self) -> None:
        packaged = os.path.join(HERE, "..", "ncp", "vectors.json")
        repository = os.path.join(HERE, "..", "..", "conformance", "vectors.json")
        with open(packaged, "rb") as a, open(repository, "rb") as b:
            self.assertEqual(a.read(), b.read())


if __name__ == "__main__":
    unittest.main()
