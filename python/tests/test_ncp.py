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


class NegativeZeroCheckTests(unittest.TestCase):
    """The decoder parses a frame a second time only when -0 can be a JSON number."""

    def test_the_check_finds_every_integer_negative_zero(self) -> None:
        for text in ("-0", " -0", "[-0]", "[1,-0]", "[1, \t-0]", '{"a":-0}', '{"a": -0}', '{"a":[{"b":\n-0}]}'):
            self.assertIsNotNone(F._NEGATIVE_ZERO.search(text), text)
            with self.assertRaises(F.FrameError):
                F.loads(text)

    def test_identifiers_do_not_trigger_the_second_parse(self) -> None:
        for text in ('{"session":"6c5a1fad-0cf3-4953-87d8-0ab303100000"}', '{"s":"a-0b"}', '{"n":-0.5}', '{"n":-0e1}'):
            self.assertIsNone(F._NEGATIVE_ZERO.search(text), text)
        self.assertEqual(F.loads('{"session":"6c5a1fad-0cf3"}'), {"session": "6c5a1fad-0cf3"})


class _Recorder:
    def __init__(self) -> None:
        self.kinds: list[tuple[str, str]] = []

    def event(self, event: ncp.Event) -> None:
        self.kinds.append((event.role, event.kind))


class ObserverTests(unittest.TestCase):
    """The SDK skips events that the default observer drops; another observer gets every one."""

    def test_an_observer_gets_every_event_of_a_call(self) -> None:
        owner_events, client_events = _Recorder(), _Recorder()
        owner = ncp.Owner(CONTRACT, Echo(), observer=owner_events)
        client = ncp.Client(_Lossless(owner), CONTRACT, observer=client_events)
        client.open()
        client.call("echo", {"n": 1})
        client.close()
        self.assertEqual([kind for _, kind in owner_events.kinds], ["opened", "admitted", "admitted"])
        self.assertEqual([kind for _, kind in client_events.kinds], ["verdict", "verdict", "verdict"])


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

    def test_a_conflict_names_its_reason_and_the_facts_of_a_profile(self) -> None:
        # Rule 7.3.12 and section 7.5: the application chooses the code and the reason; the facts
        # of a profile ride along, and the owner leaves them out, never the reason, when they do
        # not fit the session bound.
        facts = {"ncp.app": {"next": 4}}

        class Busy(Echo):
            def validate(self, req):
                if req.body.get("big"):
                    raise ncp.Declined("busy", code="conflict", reason="app.busy", body={"ncp.app": "x" * 70_000})
                raise ncp.Declined("busy", code="conflict", reason="app.busy", body=facts)

        self.owner = ncp.Owner(CONTRACT, Busy(), max_bound=F.HANDSHAKE_BOUND)
        ack = self.opened()
        first = self.owner.handle(request(self.session, 1, "echo", ack, {}))
        self.assertEqual((response_of(first)["outcome"], response_of(first)["code"]), ("declined", "conflict"))
        self.assertEqual(response_of(first)["body"], {"detail": "busy", "ncp.app": {"next": 4}, "ncp.reason": "app.busy"})
        self.assertEqual(self.owner.handle(request(self.session, 1, "echo", ack, {})), first)
        second = response_of(self.owner.handle(request(self.session, 2, "echo", F.identity(first), {"big": True})))
        self.assertEqual((second["code"], second["body"]), ("conflict", {"detail": "busy", "ncp.reason": "app.busy"}))

    def test_a_decline_that_ncp_cannot_send_ends_the_session(self) -> None:
        # Rule 7.3.12: an application can decline only with body_invalid or conflict, a reason is a
        # name, and an operation that lists its reasons (section 11, rule 6) gives no other reason
        # of the application. Anything else is a defect while checking: owner_failure.
        listed = ncp.Contract.from_bytes(
            b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{"ncp.reasons":'
            b'["echo.busy"]}},"streams":{}}'
        )
        cases = [
            ({"code": "unknown_op"}, "owner_failure"),
            ({"code": "conflict", "reason": "Not A Name"}, "owner_failure"),
            ({"code": "conflict", "reason": "echo.other"}, "owner_failure"),
            ({"code": "conflict", "reason": "echo.busy"}, "conflict"),
            ({"code": "conflict", "reason": "ncp.profile.reason"}, "conflict"),
            ({"code": "body_invalid"}, "body_invalid"),
        ]
        for decline, code in cases:
            with self.subTest(decline=decline):

                class Declining(Echo):
                    def validate(self, req, decline=decline):
                        raise ncp.Declined("no", **decline)

                self.owner = ncp.Owner(listed, Declining())
                self.session = str(uuid.uuid4())
                ack = F.identity(self.owner.handle(open_request(self.session, contract=listed.identity)))
                reply = self.call(1, "echo", ack, {})
                self.assertEqual(reply["code"], code)
                self.assertEqual(reply["outcome"], "ended" if code == "owner_failure" else "declined")

    def test_a_refused_open_names_its_reason(self) -> None:
        # Section 7.5: a rejected open with refused can name a reason; a reason that is not a name
        # is a defect of the application, and the owner refuses without it.
        for reason, body in [("echo.full", {"detail": "full", "ncp.reason": "echo.full"}),
                             ("Full!", {"detail": "the application failed to open the session"})]:
            with self.subTest(reason=reason):

                class Full(Echo):
                    def open(self, info, reason=reason):
                        raise ncp.Refused("full", reason=reason)

                self.owner = ncp.Owner(CONTRACT, Full())
                reply = response_of(self.owner.handle(open_request(self.session)))
                self.assertEqual((reply["outcome"], reply["code"], reply["body"]), ("rejected", "refused", body))

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

    @unittest.skipUnless(os.environ.get("NCP_RUST_EXAMPLES"), "set NCP_RUST_EXAMPLES to the Rust examples directory")
    def test_python_lockstep_client_with_the_rust_lockstep_owner(self) -> None:
        # The lockstep profile across the two SDKs: the Python client takes the ticks of the Rust
        # owner, reads a report, recovers after a connection that breaks, and meets a moved term.
        world = ncp.Contract.from_bytes(
            b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{},"look":{}},"streams":{}}'
        )
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "lockstep.sock")
        owner = subprocess.Popen(
            [os.path.join(os.environ["NCP_RUST_EXAMPLES"], "lockstep_owner"), "unix", path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )

        class Cut:
            """A channel that breaks after it sent a request, before the response arrives."""

            def __init__(self, inner) -> None:
                self.inner, self.cut = inner, False
                self.lossy, self.local = inner.lossy, inner.local

            def send(self, frame: bytes) -> None:
                self.inner.send(frame)

            def receive(self, bound: int, timeout: float | None) -> bytes:
                if self.cut:
                    self.inner.close()
                    raise ConnectionResetError("the connection broke")
                return self.inner.receive(bound, timeout)

            def close(self) -> None:
                self.inner.close()

        def session(channel=None) -> ncp.Client:
            return ncp.Client(channel or ncp.connect_unix(path), world, features={"ncp.lockstep": {"rev": [5]}})

        try:
            self.assertEqual(owner.stdout.readline().strip(), f"ready unix:{path}")
            channel = Cut(ncp.connect_unix(path))
            stepper = ncp.LockstepClient(session(channel))
            self.assertTrue(stepper.client.owner["implementation"].startswith("ncp-rust/"))
            first = stepper.step("step", {"dx": 2})
            self.assertEqual((stepper.tick, stepper.state, first.body["position"]), (1, "p2", 2))
            monitor = session()
            monitor.open()
            report = {"rev": 5, "tick": 1, "state": "p2", "request": first.request, "term": 1,
                      "history": stepper.history, "take": True}
            self.assertEqual(monitor.enabled["ncp.lockstep"], report)
            with self.assertRaises(ncp.Declined) as declined:
                monitor.call("step", {"dx": 5, "ncp.tick": {"tick": 2, "state": "p2"}})
            self.assertTrue(declined.exception.detail.startswith("holder:"), declined.exception.detail)
            self.assertEqual((declined.exception.code, declined.exception.reason), ("conflict", "ncp.lockstep.holder"))
            self.assertEqual(declined.exception.body["ncp.lockstep"], {"term": 1})
            # The connection breaks after the step was sent: it possibly ran.
            channel.cut = True
            with self.assertRaises(ncp.Ended) as ended:
                stepper.step("step", {"dx": 1})
            self.assertEqual(ended.exception.executed, ncp.Executed.UNKNOWN)
            # The owner ran it, as a report shows without taking anything; the recovery says so.
            deadline = time.monotonic() + 5
            while True:
                reader = session()
                reader.open()
                if reader.enabled["ncp.lockstep"]["tick"] == 2 or time.monotonic() > deadline:
                    break
                time.sleep(0.01)
            self.assertEqual(stepper.recover(session()), ncp.Executed.YES)
            self.assertEqual((stepper.tick, stepper.state), (2, "p3"))
            # A take whose term moved is declined with the owner's term, and taken again.
            late = session()
            late.open()  # its report names term 2
            other = ncp.LockstepClient(session())  # term 3
            again = ncp.LockstepClient(late)  # declined once, then term 4
            self.assertEqual(again.step("step", {"dx": 10}).body["position"], 13)
            with self.assertRaises(ncp.Declined):
                other.step("step", {"dx": 1})
        finally:
            owner.stdin.close()
            owner.wait(timeout=10)
            shutil.rmtree(directory, ignore_errors=True)

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
    SESSION = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b"

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
        can, and records every frame that the client sent."""

        def __init__(self, owner) -> None:
            super().__init__(owner)
            self.broken, self.held, self.frames = False, [], []

        def send(self, frame: bytes) -> None:
            self.frames.append(bytes(frame))
            if self.broken:
                self.held.append(bytes(frame))
                raise ConnectionResetError("the connection broke")
            super().send(frame)

    def session(self, lockstep, feature: bool = True, session: str | None = None, owner=None) -> ncp.Client:
        return ncp.Client(
            self.Held(owner or ncp.Owner(self.CONTRACT, lockstep)),
            self.CONTRACT,
            features={"ncp.lockstep": {"rev": [5]}} if feature else None,
            session=session,
        )

    def lose_a_step(self, lockstep, session: str | None = None, owner=None):
        """A stepper whose second step is on its way when its connection breaks."""
        stepper = ncp.LockstepClient(self.session(lockstep, session=session, owner=owner))
        stepper.step("step", {"dx": 2})
        old = stepper.client.channel
        old.broken = True
        with self.assertRaises(ncp.Ended) as caught:
            stepper.step("step", {"dx": 1})
        self.assertEqual(caught.exception.executed, ncp.Executed.UNKNOWN)
        return stepper, old

    def answer(self, owner, frame: bytes) -> dict:
        return F.decode(owner.handle(frame), F.MAX_BOUND).message

    def test_steps_carry_the_tick_and_the_state(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        owner = ncp.Owner(self.CONTRACT, lockstep)
        client = ncp.Client(_Lossless(owner), self.CONTRACT, features={"ncp.lockstep": {"rev": [5]}})
        stepper = ncp.LockstepClient(client)  # opens and takes the ticks
        self.assertEqual((stepper.tick, stepper.state, stepper.request), (0, "p0", None))  # the world's digest
        self.assertEqual((lockstep.holder, lockstep.term), (client.nonce, 1))
        result = stepper.step("step", {"dx": 2})
        self.assertEqual(result.body["position"], 2)
        self.assertEqual((stepper.tick, stepper.state, stepper.request), (1, "p2", result.request))
        self.assertEqual(client.call("look", {}).body, {"position": 2})  # not a lockstep operation
        self.assertEqual(result.body["ncp.tick"]["request"], result.request)
        with self.assertRaises(ncp.Declined) as caught:
            client.call("step", {"dx": 1, "ncp.tick": {"tick": 5, "state": "p2"}})
        self.assertIn("tick", caught.exception.detail)
        with self.assertRaises(ncp.Declined):
            client.call("step", {"dx": 1, "ncp.tick": {"tick": 2, "state": "p9"}})
        self.assertEqual(lockstep.tick, 1)

    def test_an_open_only_reports_the_clock(self) -> None:
        # Profile rule 3.3: an open with the feature changes nothing outside its session. A
        # monitor reads the clock without fencing the stepping client, and cannot step itself.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        result = stepper.step("step", {"dx": 2})
        monitor = self.session(lockstep)
        monitor.open()
        self.assertEqual(monitor.enabled["ncp.lockstep"], {"rev": 5, "tick": 1, "state": "p2", "request": result.request,
                                                           "term": 1, "history": lockstep.history, "take": True})
        self.assertEqual(lockstep.holder, stepper.client.nonce)
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 3)
        with self.assertRaises(ncp.Declined) as caught:
            monitor.call("step", {"dx": 1, "ncp.tick": {"tick": 3, "state": "p3"}})
        self.assertIn("does not hold the ticks", caught.exception.detail)
        self.assertEqual((caught.exception.code, caught.exception.reason), ("conflict", "ncp.lockstep.holder"))
        self.assertEqual(caught.exception.body["ncp.lockstep"], {"term": 1})  # to take them (rule 6.4)

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
                stepper = ncp.LockstepClient(ncp.Client(channel, self.CONTRACT, features={"ncp.lockstep": {"rev": [5]}}))
                stepper.step("step", {"dx": 1})
                channel.broken = True
                with self.assertRaises(ncp.Ended) as caught:
                    stepper.step("step", {"dx": 1})
                self.assertEqual(caught.exception.executed, ncp.Executed.UNKNOWN)
                self.assertEqual(stepper.uncertain[0], 2)
                self.assertEqual(stepper.uncertain[1], caught.exception.request)
                self.assertIsNotNone(caught.exception.request)
                fresh = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, lockstep)), self.CONTRACT,
                                   features={"ncp.lockstep": {"rev": [5]}})
                self.assertEqual(stepper.recover(fresh), expected)
                self.assertEqual(stepper.tick, 2 if expected is ncp.Executed.YES else 1)
                stepper.step("step", {"dx": 10})

    def test_a_take_fences_the_steps_of_earlier_openings(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper, old = self.lose_a_step(lockstep)
        self.assertEqual(stepper.recover(self.session(lockstep)), ncp.Executed.NO)
        self.assertEqual(stepper.tick, 1)
        # The delayed request reaches the old opening after the recovery: it never runs.
        response = self.answer(old.owner, old.held[0])
        self.assertEqual((response["outcome"], response["code"]), ("declined", "conflict"))
        self.assertEqual(response["body"]["ncp.reason"], "ncp.lockstep.holder")
        self.assertIn("does not hold the ticks", response["body"]["detail"])
        self.assertEqual(lockstep.tick, 1)
        self.assertEqual(stepper.step("step", {"dx": 10}).body["position"], 12)
        self.assertEqual((lockstep.holder, lockstep.term), (stepper.client.nonce, 2))
        # A session that did not ask for the feature can neither step nor take.
        plain = self.session(lockstep, feature=False)
        plain.open()
        with self.assertRaises(ncp.Declined) as declined:
            plain.call("step", {"dx": 1, "ncp.tick": {"tick": 3, "state": "p12"}})
        self.assertIn("does not hold the ticks", declined.exception.detail)
        for op in ("ncp.lockstep.take", "ncp.other.thing"):
            with self.assertRaises(ncp.Declined) as declined:
                plain.call(op, {"term": 2})
            self.assertEqual(declined.exception.code, "unknown_op")
        self.assertEqual(lockstep.holder, stepper.client.nonce)

    def test_a_copy_of_an_old_open_takes_nothing(self) -> None:
        # Profile rule 3.3 and specification rule 7.1.8. A copy of the first open, replayed on
        # another connection, opens that session again with another nonce and takes nothing. A
        # copy of the old take acknowledges the old open response, so the copy's opening rejects it.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper, old = self.lose_a_step(lockstep)
        self.assertEqual(stepper.recover(self.session(lockstep)), ncp.Executed.NO)
        holder = lockstep.holder
        replayed = ncp.Owner(self.CONTRACT, lockstep)  # a fresh owner, as a server makes one
        opened = self.answer(replayed, old.frames[0])
        self.assertEqual(opened["outcome"], "ok")
        self.assertNotEqual(opened["body"]["nonce"], old.owner.state.nonce)
        took = self.answer(replayed, old.frames[1])
        self.assertEqual((took["outcome"], took["code"]), ("rejected", "ack_mismatch"))
        self.assertEqual(lockstep.holder, holder)
        response = self.answer(old.owner, old.held[0])
        self.assertEqual((response["outcome"], response["code"]), ("declined", "conflict"))
        self.assertEqual(response["body"]["ncp.reason"], "ncp.lockstep.holder")
        self.assertEqual((lockstep.tick, lockstep.handler.position), (1, 2))  # "did not run" stays true
        self.assertEqual(stepper.step("step", {"dx": 10}).body["position"], 12)  # and the stepper keeps going

    def test_a_recovery_with_the_same_session_identifier_fences_the_old_opening(self) -> None:
        # On a byte stream, each connection has its own owner: a new opening, which takes the ticks.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper, old = self.lose_a_step(lockstep, session=self.SESSION)
        self.assertEqual(stepper.recover(self.session(lockstep, session=self.SESSION)), ncp.Executed.NO)
        response = self.answer(old.owner, old.held[0])
        self.assertEqual((response["outcome"], response["code"]), ("declined", "conflict"))
        self.assertEqual(response["body"]["ncp.reason"], "ncp.lockstep.holder")
        self.assertEqual((lockstep.tick, lockstep.handler.position), (1, 2))
        self.assertEqual(stepper.step("step", {"dx": 10}).body["position"], 12)

    def test_a_recovery_that_reaches_the_old_opening_gives_no_verdict(self) -> None:
        # Where one owner holds a session identifier, as a Zenoh server does, the same open
        # reaches the old opening again: it is stale there, so the recovery gives no verdict, and
        # the delayed step can still run. A new session identifier then finds that it ran.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        owner = ncp.Owner(self.CONTRACT, lockstep)
        stepper, old = self.lose_a_step(lockstep, session=self.SESSION, owner=owner)
        with self.assertRaises(ncp.Rejected) as caught:
            stepper.recover(self.session(lockstep, session=self.SESSION, owner=owner))
        self.assertEqual(caught.exception.code, "seq_stale")
        self.assertIsNotNone(stepper.uncertain)
        self.assertEqual(self.answer(owner, old.held[0])["outcome"], "ok")
        self.assertEqual(stepper.recover(self.session(lockstep)), ncp.Executed.YES)
        self.assertEqual((stepper.tick, stepper.state), (2, "p3"))

    def test_a_recovery_reads_its_verdict_from_the_take(self) -> None:
        # The report of an open can be older than the clock: here the standby client opened before
        # the steps. Its take decides, and its opening then holds the ticks.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        standby = self.session(lockstep)
        standby.open()
        self.assertEqual(standby.enabled["ncp.lockstep"]["tick"], 0)
        stepper, old = self.lose_a_step(lockstep)
        self.assertEqual(stepper.recover(standby), ncp.Executed.NO)
        self.assertEqual(lockstep.holder, standby.nonce)
        self.assertEqual(self.answer(old.owner, old.held[0])["outcome"], "declined")
        self.assertEqual((lockstep.tick, lockstep.handler.position), (1, 2))

    def test_a_delayed_take_of_an_abandoned_opening_is_declined(self) -> None:
        # Profile rule 5.2: the term moved, so a late take cannot take the ticks from a newer holder.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        abandoned = self.session(lockstep)
        abandoned.open()
        abandoned.channel.broken = True
        with self.assertRaises(ncp.Ended):
            abandoned.call("ncp.lockstep.take", {"term": 0})
        stepper = ncp.LockstepClient(self.session(lockstep))
        late = self.answer(abandoned.channel.owner, abandoned.channel.held[0])
        self.assertEqual((late["outcome"], late["code"]), ("declined", "conflict"))
        self.assertEqual(late["body"]["ncp.reason"], "ncp.lockstep.term")
        self.assertEqual(late["body"]["ncp.lockstep"], {"term": 1})
        self.assertIn("term", late["body"]["detail"])
        self.assertEqual(lockstep.holder, stepper.client.nonce)
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 1)

    def test_a_take_whose_term_moved_is_sent_again(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        late = self.session(lockstep)
        late.open()  # its report names term 0
        other = ncp.LockstepClient(self.session(lockstep))  # takes first: term 1
        stepper = ncp.LockstepClient(late)  # declined once with term 1, then takes: term 2
        self.assertEqual((lockstep.term, lockstep.holder), (2, late.nonce))
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 1)
        with self.assertRaises(ncp.Declined):
            other.step("step", {"dx": 1})

    def test_no_take_raises_the_largest_term(self) -> None:
        # Profile rule 5.2: the term stays an integer that a JSON number carries exactly.
        lockstep = ncp.Lockstep(self.World(), ["step"], term=ncp.lockstep.MAX_TERM)
        client = self.session(lockstep)
        client.open()
        with self.assertRaises(ncp.Declined) as caught:
            ncp.lockstep.take(client)
        # No other take ran, so the response names no term (rule 6.2).
        self.assertEqual(caught.exception.body, {"detail": "term: the term is the largest; no take can follow it",
                                                 "ncp.reason": "ncp.lockstep.limit"})
        self.assertEqual(caught.exception.code, "conflict")
        self.assertEqual((lockstep.term, lockstep.holder), (ncp.lockstep.MAX_TERM, None))

    def test_a_take_needs_its_body_and_the_profile_defines_no_other_operation(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        client = self.session(lockstep)
        client.open()
        for op, body, code in (("ncp.lockstep.take", {}, "body_invalid"), ("ncp.lockstep.take", {"term": "0"}, "body_invalid"),
                               ("ncp.lockstep.other", {}, "unknown_op")):
            with self.assertRaises(ncp.Declined) as caught:
                client.call(op, body)
            self.assertEqual((caught.exception.code, caught.exception.reason), (code, None))
        self.assertEqual((lockstep.holder, lockstep.term, lockstep.handler.position), (None, 0, 0))

    def test_a_restart_to_the_same_tick_with_another_state_gives_no_verdict(self) -> None:
        # Profile rule 6.5: "did not run" needs exactly the clock that the client knew. Without a
        # verdict, the client goes on from the owner's clock in the new session.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper, _ = self.lose_a_step(lockstep)  # it knows tick 1 and state p2; tick 2 is uncertain
        restarted = ncp.Lockstep(self.World(), ["step"], tick=1, state="p500", request="e" * 64)
        self.assertIs(stepper.recover(self.session(restarted)), ncp.Executed.UNKNOWN)
        self.assertEqual((stepper.tick, stepper.state, stepper.uncertain), (1, "p500", None))
        restarted.handler.position = 500  # the world that the restored digest names
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 501)

    def test_a_restore_to_an_earlier_saved_clock_gives_no_verdict(self) -> None:
        # Profile rules 5.7 and 6.5 (revision 5). The step of tick 2 runs, with an effect outside
        # the state, and its response is lost. The owner restarts and restores the clock that it
        # saved at tick 1: a step started after that clock, so the owner draws a new history
        # identity. The client gets no verdict, never "did not run", and cannot run the step twice
        # on a false verdict.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper, old = self.lose_a_step(lockstep)
        saved = (stepper.tick, stepper.state, stepper.request, lockstep.term)
        ran = self.answer(old.owner, old.held[0])  # the step arrives late and runs
        self.assertEqual((ran["outcome"], lockstep.tick), ("ok", 2))
        world = self.World()
        world.position = 2  # the state saved with the clock of tick 1
        restored = ncp.Lockstep(world, ["step"], tick=saved[0], state=saved[1], request=saved[2], term=saved[3])
        self.assertNotEqual(restored.history, lockstep.history)
        self.assertIs(stepper.recover(self.session(restored)), ncp.Executed.UNKNOWN)
        self.assertEqual((stepper.tick, stepper.state, stepper.history), (1, "p2", restored.history))

    def test_a_restart_that_keeps_the_latest_clock_and_its_history_gives_a_verdict(self) -> None:
        # Profile rule 5.7: no step started after the latest clock was saved, so the owner may
        # restore its history identity, and "did not run" stays a verdict. Without the history
        # identity, the same restart gives no verdict.
        for keep, verdict in ((True, ncp.Executed.NO), (False, ncp.Executed.UNKNOWN)):
            with self.subTest(keep=keep):
                lockstep = ncp.Lockstep(self.World(), ["step"])
                stepper, _ = self.lose_a_step(lockstep)  # the step of tick 2 never reached the owner
                world = self.World()
                world.position = 2
                restarted = ncp.Lockstep(
                    world, ["step"], tick=lockstep.tick, state=lockstep.state, request=lockstep.request,
                    term=lockstep.term, history=lockstep.history if keep else None,
                )
                self.assertIs(stepper.recover(self.session(restarted)), verdict)
                self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 3)
        with self.assertRaises(ValueError):
            ncp.Lockstep(self.World(), ["step"], history="A" * 32)

    def test_a_reader_opening_reads_the_clock_and_cannot_take_or_step(self) -> None:
        # Profile rule 3.5: the owner lets the openings of a service only read the clock.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        stepper.step("step", {"dx": 2})
        monitor = self.session(None, owner=ncp.Owner(self.CONTRACT, lockstep.reader()))
        monitor.open()
        reported = ncp.lockstep.report(monitor)
        self.assertEqual((reported["tick"], reported["take"], reported["history"]), (1, False, lockstep.history))
        with self.assertRaises(ncp.UsageError):
            ncp.lockstep.take(monitor)
        for op, body in (("ncp.lockstep.take", {"term": reported["term"]}),
                         ("step", {"dx": 1, "ncp.tick": {"tick": 2, "state": "p2"}})):
            with self.assertRaises(ncp.Declined) as caught:
                monitor.call(op, body)
            self.assertEqual((caught.exception.code, caught.exception.reason), ("body_invalid", "ncp.lockstep.reader"))
        self.assertEqual(monitor.call("look", {}).body, {"position": 2})  # other operations pass through
        self.assertEqual(lockstep.holder, stepper.client.nonce)
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 3)

    def test_each_refusal_of_a_step_names_its_reason_and_its_facts(self) -> None:
        # Profile rule 5.8: conflict with a reason for a state that does not permit the step, and
        # body_invalid without a reason for a body that no state accepts.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        client = stepper.client
        for member, reason, facts in (({"tick": 5, "state": "p0"}, "ncp.lockstep.tick", {"next": 1}),
                                      ({"tick": 1, "state": "other"}, "ncp.lockstep.state", None)):
            with self.assertRaises(ncp.Declined) as caught:
                client.call("step", {"dx": 1, "ncp.tick": member})
            self.assertEqual((caught.exception.code, caught.exception.reason), ("conflict", reason))
            self.assertEqual(caught.exception.body.get("ncp.lockstep"), facts)
        for member in ({"tick": "1", "state": "p0"}, {"tick": 1}, {"tick": -1, "state": "p0"}, {"tick": 1, "state": ""}):
            with self.assertRaises(ncp.Declined) as caught:
                client.call("step", {"dx": 1, "ncp.tick": member})
            self.assertEqual((caught.exception.code, caught.exception.reason), ("body_invalid", None))
        self.assertEqual((lockstep.tick, lockstep.handler.position), (0, 0))

    def test_profile_members_that_cannot_be_encoded_leave_the_detail(self) -> None:
        # The owner keeps the decline and drops members that it cannot encode.
        class Refusing:
            def __init__(self, members):
                self.members = members

            def validate(self, request):
                raise ncp.Declined("no", body=self.members)

            def execute(self, request):
                return {}

        cases = [
            # Too large for any frame, and a number that JSON cannot carry.
            ({"ncp.big": "x" * 2_000_000, "ncp.odd": float("nan")}, F.DEFAULT_BOUND, {"detail": "no"}),
            # Larger than the session's bound, which the client set to the smallest bound.
            ({"ncp.big": "x" * 100_000}, F.HANDSHAKE_BOUND, {"detail": "no"}),
            # A member name that is not a string is dropped; the other members stay.
            ({1: "x", "ncp.small": 1, "other": 2}, F.DEFAULT_BOUND, {"detail": "no", "ncp.small": 1}),
            # A member that is not plain JSON, such as an array attachment, is dropped, as in Rust.
            ({"ncp.array": F.Array("u8", [2], b"ab"), "ncp.small": 1}, F.DEFAULT_BOUND, {"detail": "no", "ncp.small": 1}),
        ]
        for members, bound, expected in cases:
            owner = ncp.Owner(self.CONTRACT, Refusing(members))
            client = ncp.Client(_Lossless(owner), self.CONTRACT, bound=bound)
            client.open()
            with self.assertRaises(ncp.Declined) as caught:
                client.call("step", {})
            self.assertEqual((caught.exception.code, caught.exception.body), ("body_invalid", expected))
            self.assertEqual(client.ping().body, {})  # the session goes on

    def test_features_that_cannot_be_sent_refuse_the_open(self) -> None:
        # Rule 7.1.3: the client reads the open response with the handshake bound.
        class Generous:
            def __init__(self) -> None:
                self.closed: list[str] = []

            def open(self, info):
                return {"big": {"blob": "x" * 70_000}}

            def validate(self, request):
                pass

            def execute(self, request):
                return {}

            def close(self, reason):
                self.closed.append(reason)

        generous = Generous()
        client = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, generous)), self.CONTRACT, features={"big": {}})
        with self.assertRaises(ncp.Rejected) as caught:
            client.open()
        self.assertEqual(caught.exception.code, "refused")
        self.assertEqual(generous.closed, ["refused"])

        # Parameters that are not plain JSON, such as an array attachment, cannot be sent either.
        class Arrayed(Generous):
            def open(self, info):
                return {"big": {"blob": F.Array("u8", [1], b"x")}}

        arrayed = Arrayed()
        client = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, arrayed)), self.CONTRACT, features={"big": {}})
        with self.assertRaises(ncp.Rejected) as caught:
            client.open()
        self.assertEqual((caught.exception.code, arrayed.closed), ("refused", ["refused"]))

    def test_no_step_follows_the_largest_tick(self) -> None:
        # Profile rule 5.4: the tick stays an integer that a JSON number carries exactly.
        lockstep = ncp.Lockstep(self.World(), ["step"], tick=ncp.lockstep.MAX_TICK)
        stepper = ncp.LockstepClient(self.session(lockstep))
        with self.assertRaises(ValueError):
            stepper.step("step", {"dx": 1})
        # The owner declines a step with any tick.
        with self.assertRaises(ncp.Declined) as caught:
            stepper.client.call("step", {"dx": 1, "ncp.tick": {"tick": ncp.lockstep.MAX_TICK, "state": "p0"}})
        self.assertTrue(caught.exception.detail.startswith("tick:"), caught.exception.detail)
        self.assertIn("largest", caught.exception.detail)
        self.assertEqual((lockstep.tick, lockstep.handler.position), (ncp.lockstep.MAX_TICK, 0))
        with self.assertRaises(ValueError):
            ncp.Lockstep(self.World(), ["step"], tick=ncp.lockstep.MAX_TICK + 1)

    def test_an_application_digest_of_the_wrong_length_is_refused(self) -> None:
        # Terms: a state digest has 1 to 128 characters; a wrong one is refused at the start.
        class Wordy(self.World):
            def state(self):
                return "x" * 200

        with self.assertRaises(ValueError):
            ncp.Lockstep(Wordy(), ["step"])

    def test_an_owner_without_a_term_ends_the_session(self) -> None:
        # Profile rule 3.4: parameters without a term come from an earlier revision of the profile.
        class Earlier:
            def open(self, info):
                return {"ncp.lockstep": {"tick": 0, "state": None, "request": None}}

            def validate(self, request):
                pass

            def execute(self, request):
                return {}

        client = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, Earlier())), self.CONTRACT,
                            features={"ncp.lockstep": {"rev": [5]}})
        with self.assertRaises(ncp.ProtocolError):
            ncp.LockstepClient(client)
        self.assertTrue(client.ended)

    def test_a_rejected_open_takes_nothing(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))

        class Full:
            def open(self, info):
                lockstep.open(info)
                raise ncp.Refused("the owner serves its largest number of sessions")

        refused = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, Full())), self.CONTRACT, features={"ncp.lockstep": {"rev": [5]}})
        with self.assertRaises(ncp.Rejected):
            refused.open()
        self.assertEqual(lockstep.holder, stepper.client.nonce)
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 1)

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

    def test_a_closed_request_schema_admits_the_tick(self) -> None:
        # Section 11.1: additionalProperties does not apply to members whose names start with
        # "ncp.", and the take is a feature operation, to which the contract does not apply.
        closed = ncp.Contract.from_bytes(
            b'{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{"ncp.schema":'
            b'{"request":{"type":"object","required":["dx"],"properties":{"dx":{"type":"integer"}},'
            b'"additionalProperties":false},"result":{"type":"object","properties":{"position":'
            b'{"type":"integer"}},"additionalProperties":false}}}},"streams":{}}'
        )
        lockstep = ncp.Lockstep(self.World(), ["step"])
        client = ncp.Client(_Lossless(ncp.Owner(closed, lockstep)), closed, features={"ncp.lockstep": {"rev": [5]}})
        stepper = ncp.LockstepClient(client)
        result = stepper.step("step", {"dx": 2})
        self.assertEqual(result.body["position"], 2)
        self.assertIsNone(closed.check_result("step", result.body))
        self.assertEqual(stepper.tick, 1)
        with self.assertRaises(ncp.Declined) as caught:  # other members stay closed out
            stepper.step("step", {"dx": 1, "dy": 1})
        self.assertEqual(caught.exception.code, "body_invalid")
        self.assertIn("'dy' is not allowed", caught.exception.detail)
        self.assertEqual(lockstep.tick, 1)

    def test_a_recovery_that_finds_the_step_of_another_session_gives_no_verdict(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])
        first = ncp.LockstepClient(self.session(lockstep))
        first.client.channel.broken = True
        with self.assertRaises(ncp.Ended):
            first.step("step", {"dx": 1})
        second = ncp.LockstepClient(self.session(lockstep))  # takes the ticks
        second.step("step", {"dx": 5})  # the step with the same tick, from another request
        self.assertIs(first.recover(self.session(lockstep)), ncp.Executed.UNKNOWN)
        self.assertEqual((first.tick, first.state, first.uncertain), (1, "p5", None))
        self.assertEqual(first.step("step", {"dx": 1}).body["position"], 6)  # it holds the ticks now

    def test_a_take_waits_for_a_checked_step_and_an_open_does_not(self) -> None:
        lockstep = ncp.Lockstep(self.World(), ["step"])

        def request(op, body, nonce, identity):
            return ncp.Request(op, body, [], 1, "s", identity, self.CONTRACT, None, {"ncp.lockstep": {"rev": [5]}}, nonce)

        def take(nonce, term, identity):
            took = request("ncp.lockstep.take", {"term": term}, nonce, identity)
            lockstep.validate(took)
            return lockstep.execute(took)

        take("n1", 0, "t1")
        step = request("step", {"dx": 3, "ncp.tick": {"tick": 1, "state": "p0"}}, "n1", "r1")
        lockstep.validate(step)
        # An open only reports: it does not wait, and it sees the clock before the step.
        info = ncp.OpenInfo("s", self.CONTRACT, None, {"ncp.lockstep": {"rev": [5]}}, "n3")
        self.assertEqual(lockstep.open(info)["ncp.lockstep"], {"rev": 5, "tick": 0, "state": "p0", "request": None,
                                                               "term": 1, "history": lockstep.history, "take": True})
        granted = []
        waiting = threading.Thread(target=lambda: granted.append(take("n2", 1, "t2")))
        waiting.start()
        waiting.join(0.1)
        self.assertTrue(waiting.is_alive(), "the take did not wait")
        lockstep.execute(step)
        waiting.join(5)
        self.assertEqual(granted, [{"tick": 1, "state": "p3", "request": "r1", "term": 2, "history": lockstep.history}])
        self.assertEqual(lockstep.holder, "n2")

    def test_a_step_waits_for_a_checked_take(self) -> None:
        # Profile rule 5.1: the step of the holder waits while another opening's take is checked;
        # after the take, the holder check declines it, with the term.
        lockstep = ncp.Lockstep(self.World(), ["step"])

        def request(op, body, nonce, identity):
            return ncp.Request(op, body, [], 1, "s", identity, self.CONTRACT, None, {"ncp.lockstep": {"rev": [5]}}, nonce)

        first = request("ncp.lockstep.take", {"term": 0}, "n1", "t1")
        lockstep.validate(first)
        lockstep.execute(first)
        other = request("ncp.lockstep.take", {"term": 1}, "n2", "t2")
        lockstep.validate(other)  # checked; its execution follows
        declined = []

        def step() -> None:
            try:
                lockstep.validate(request("step", {"dx": 1, "ncp.tick": {"tick": 1, "state": "p0"}}, "n1", "r1"))
            except ncp.Declined as error:
                declined.append(error)

        waiting = threading.Thread(target=step)
        waiting.start()
        waiting.join(0.1)
        self.assertTrue(waiting.is_alive(), "the step did not wait")
        lockstep.execute(other)
        waiting.join(5)
        self.assertEqual(len(declined), 1)
        self.assertTrue(declined[0].detail.startswith("holder:"), declined[0].detail)
        self.assertEqual(declined[0].body, {"ncp.lockstep": {"term": 2}})
        self.assertEqual((lockstep.tick, lockstep.holder), (0, "n2"))

    def test_a_take_names_the_last_term_that_the_owner_told(self) -> None:
        # Profile rule 4.1: after a declined step names the term, a take in the same session names it.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))  # term 1
        other = ncp.LockstepClient(self.session(lockstep))  # term 2
        with self.assertRaises(ncp.Declined) as caught:
            stepper.step("step", {"dx": 1})
        self.assertEqual(caught.exception.body["ncp.lockstep"], {"term": 2})
        self.assertEqual(stepper.term, 2)
        sent = len(stepper.client.channel.frames)
        stepper.take()
        self.assertEqual(len(stepper.client.channel.frames), sent + 1)  # one take, which ran
        self.assertEqual((stepper.term, lockstep.term, lockstep.holder), (3, 3, stepper.client.nonce))
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 1)
        with self.assertRaises(ncp.Declined):
            other.step("step", {"dx": 1})

    def test_the_client_checks_the_term_of_the_take(self) -> None:
        # Profile rule 6.1: the body of the take names the term of the request plus 1.
        class Skipping(ncp.Lockstep):
            def execute(self, request):
                result = super().execute(request)
                if request.op == ncp.lockstep.TAKE:
                    result = {**result, "term": result["term"] + 1}
                return result

        client = self.session(Skipping(self.World(), ["step"]))
        with self.assertRaises(ncp.Ended) as caught:
            ncp.LockstepClient(client)
        self.assertEqual((caught.exception.code, caught.exception.executed), ("local.protocol", ncp.Executed.YES))
        self.assertTrue(client.ended)

    def test_the_client_checks_the_tick_and_the_request_of_a_step(self) -> None:
        # Profile rule 6.3: ncp.tick in the result names the tick and the identity of the request.
        class Misnaming(ncp.Lockstep):
            def execute(self, request):
                result = super().execute(request)
                if request.op == "step":
                    result = {**result, "ncp.tick": {**result["ncp.tick"], "request": "0" * 64}}
                return result

        lockstep = Misnaming(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        with self.assertRaises(ncp.Ended) as caught:
            stepper.step("step", {"dx": 2})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("local.protocol", ncp.Executed.YES))
        self.assertEqual((stepper.tick, stepper.state, lockstep.tick), (1, None, 1))
        self.assertTrue(stepper.client.ended)

    def test_a_client_stops_after_three_takes_whose_term_moved(self) -> None:
        # Profile rule 6.2: a client stops after TAKE_ATTEMPTS takes without an ok response.
        class Moving:
            def __init__(self) -> None:
                self.term, self.takes = 0, 0

            def open(self, info):
                return {"ncp.lockstep": {"rev": 5, "tick": 0, "state": None, "request": None, "term": self.term,
                                         "history": "c" * 32, "take": True}}

            def validate(self, request):
                self.takes += 1
                self.term += 1  # another client takes the ticks each time
                raise ncp.Declined(f"term: the term is {self.term}", code="conflict", reason="ncp.lockstep.term",
                                   body={"ncp.lockstep": {"term": self.term}})

            def execute(self, request):
                return {}

        moving = Moving()
        client = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, moving)), self.CONTRACT, features={"ncp.lockstep": {"rev": [5]}})
        client.open()
        with self.assertRaises(ncp.Declined) as caught:
            ncp.lockstep.take(client)
        self.assertEqual(moving.takes, ncp.lockstep.TAKE_ATTEMPTS)
        self.assertEqual(caught.exception.body["ncp.lockstep"], {"term": 3})
        self.assertEqual(client.ping().body, {})  # the session goes on

    class Contested(ncp.Lockstep):
        """A lockstep owner where another opening takes the ticks just before each take, while
        `contest` is set."""

        contest = False

        def validate(self, request):
            if self.contest and request.op == ncp.lockstep.TAKE:
                other = ncp.Request(ncp.lockstep.TAKE, {"term": self.term}, [], 1, "s", "0" * 64, request.contract,
                                    None, request.features, "f" * 32)
                super().validate(other)
                super().execute(other)
            super().validate(request)

    def test_a_take_that_fails_keeps_the_term_that_the_owner_told(self) -> None:
        # Rule 4.1: the next take names the term of the last decline.
        lockstep = self.Contested(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))  # term 1
        lockstep.contest = True
        with self.assertRaises(ncp.Declined) as caught:
            stepper.take()  # three takes, each named an old term
        told = caught.exception.body["ncp.lockstep"]["term"]
        self.assertEqual((told, stepper.term), (4, 4))
        lockstep.contest = False
        sent = len(stepper.client.channel.frames)
        stepper.take()
        self.assertEqual(len(stepper.client.channel.frames), sent + 1)  # one take, with term 4
        self.assertEqual((stepper.term, lockstep.holder), (5, stepper.client.nonce))

    def test_a_recovery_whose_take_is_declined_ends_its_session(self) -> None:
        lockstep = self.Contested(self.World(), ["step"])
        stepper, _ = self.lose_a_step(lockstep)
        lockstep.contest = True
        fresh = self.session(lockstep)
        with self.assertRaises(ncp.Declined):
            stepper.recover(fresh)
        self.assertTrue(fresh.ended)
        self.assertIsNotNone(stepper.uncertain)  # still possibly executed
        lockstep.contest = False
        # The other opening's takes moved only the term, and the lost step never arrived: the clock is
        # the one that the client knew, so the step did not run.
        self.assertEqual(stepper.recover(self.session(lockstep)), ncp.Executed.NO)

    def test_a_response_without_a_member_of_the_clock_ends_the_session(self) -> None:
        # Rules 5.3 and 6.1: the take's body has all four members; rule 6.3: ncp.tick has all three.
        class Lacking(ncp.Lockstep):
            drop: tuple = ()

            def execute(self, request):
                result = super().execute(request)
                if request.op == ncp.lockstep.TAKE and "take" in self.drop:
                    result = {k: v for k, v in result.items() if k != "state"}
                if request.op == "step" and "step" in self.drop:
                    result = {**result, "ncp.tick": {k: v for k, v in result["ncp.tick"].items() if k != "state"}}
                return result

        lockstep = Lacking(self.World(), ["step"])
        lockstep.drop = ("take",)
        client = self.session(lockstep)
        with self.assertRaises(ncp.Ended) as caught:
            ncp.LockstepClient(client)
        self.assertEqual((caught.exception.code, caught.exception.executed), ("local.protocol", ncp.Executed.YES))
        self.assertTrue(client.ended)
        lockstep.drop = ("step",)
        stepper = ncp.LockstepClient(self.session(lockstep))
        with self.assertRaises(ncp.Ended) as caught:
            stepper.step("step", {"dx": 2})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("local.protocol", ncp.Executed.YES))
        self.assertEqual((stepper.tick, lockstep.tick), (1, 1))
        self.assertTrue(stepper.client.ended)

    def test_other_operations_change_neither_the_clock_nor_the_holder(self) -> None:
        # Rule 5.6.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        stepper = ncp.LockstepClient(self.session(lockstep))
        stepper.step("step", {"dx": 2})
        before = (lockstep.clock(), lockstep.holder)
        self.assertEqual(stepper.client.call("look", {}).body, {"position": 2})
        self.assertEqual((lockstep.clock(), lockstep.holder), before)

    def test_a_client_acts_on_the_member_and_not_on_the_detail(self) -> None:
        # Rule 5.8: the detail says 99, the member says 5; the client names 5.
        class Misleading:
            def __init__(self) -> None:
                self.named: list[int] = []

            def open(self, info):
                return {"ncp.lockstep": {"rev": 5, "tick": 0, "state": None, "request": None, "term": 0,
                                         "history": "a" * 32, "take": True}}

            def validate(self, request):
                self.named.append(request.body["term"])
                if request.body["term"] != 5:
                    raise ncp.Declined("term: the term is 99", code="conflict", reason="ncp.lockstep.term",
                                       body={"ncp.lockstep": {"term": 5}})

            def execute(self, request):
                return {"tick": 0, "state": None, "request": None, "term": 6, "history": "a" * 32}

        misleading = Misleading()
        client = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, misleading)), self.CONTRACT,
                            features={"ncp.lockstep": {"rev": [5]}})
        client.open()
        self.assertEqual(ncp.lockstep.take(client), ((0, None, None, "a" * 32), 6))
        self.assertEqual(misleading.named, [0, 5])

    def test_an_owner_reads_only_the_revisions_of_the_feature_parameters(self) -> None:
        # Rule 3.1, and specification section 17, rule 1: the owner enables the profile only for a
        # client that lists revision 5, names that revision, and ignores the other members.
        lockstep = ncp.Lockstep(self.World(), ["step"])
        client = ncp.Client(self.Held(ncp.Owner(self.CONTRACT, lockstep)), self.CONTRACT,
                            features={"ncp.lockstep": {"rev": [4, 5, 6], "tick": 99, "other": True}})
        stepper = ncp.LockstepClient(client)
        self.assertEqual(client.enabled["ncp.lockstep"], {"rev": 5, "tick": 0, "state": "p0", "request": None,
                                                          "term": 0, "history": lockstep.history, "take": True})
        self.assertEqual(stepper.step("step", {"dx": 1}).body["position"], 1)
        for parameters in ({}, {"rev": [4]}, {"rev": 5}, {"rev": [True, "5"]}):
            with self.subTest(parameters=parameters):
                client = ncp.Client(self.Held(ncp.Owner(self.CONTRACT, lockstep)), self.CONTRACT,
                                    features={"ncp.lockstep": parameters})
                client.open()
                self.assertNotIn("ncp.lockstep", client.enabled)
                with self.assertRaises(ncp.ProtocolError):
                    ncp.LockstepClient(client)

    def test_a_client_uses_no_report_of_another_revision(self) -> None:
        # Specification section 17, rule 1: a report that names another revision, or that misses a
        # member of revision 5, enables nothing that the client can use; it ends the session.
        clock = {"rev": 5, "tick": 0, "state": None, "request": None, "term": 0, "history": "b" * 32, "take": True}
        for report in ({**clock, "rev": 4}, {**clock, "rev": [5]}, {k: v for k, v in clock.items() if k != "history"},
                       {**clock, "history": "B" * 32}, {k: v for k, v in clock.items() if k != "take"}):
            with self.subTest(report=report):

                class Other:
                    def open(self, info, report=report):
                        return {"ncp.lockstep": report}

                    def validate(self, request):
                        raise AssertionError("no take may follow")

                    def execute(self, request):
                        raise AssertionError("no take may follow")

                client = ncp.Client(_Lossless(ncp.Owner(self.CONTRACT, Other())), self.CONTRACT,
                                    features={"ncp.lockstep": {"rev": [5]}})
                client.open()
                with self.assertRaises(ncp.ProtocolError):
                    ncp.lockstep.take(client)
                self.assertTrue(client.ended)

    def test_the_verdict_of_a_recovery(self) -> None:
        judge, known = ncp.lockstep.judge, (4, "s4", "r4", "h1")
        self.assertIs(judge(known, (5, "r5"), (5, "s5", "r5", "h1")), ncp.Executed.YES)
        self.assertIs(judge(known, (5, "r5"), (5, "s5", "r5", "h2")), ncp.Executed.YES)  # a restored state holds it
        self.assertIs(judge(known, (5, "r5"), known), ncp.Executed.NO)
        for taken in ((5, "s5", "other", "h1"), (4, "s4", "other", "h1"), (4, "other", "r4", "h1"), (3, "s3", "r3", "h1"),
                      (6, "s6", "r6", "h1"), (4, "s4", "r4", "h2")):
            with self.subTest(taken=taken):
                self.assertIs(judge(known, (5, "r5"), taken), ncp.Executed.UNKNOWN)
        self.assertIs(judge(known, (5, None), (5, "s5", None, "h1")), ncp.Executed.UNKNOWN)  # "ran" cannot be shown


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
