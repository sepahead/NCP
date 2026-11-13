"""Tests of the Zenoh binding (specification, section 9.2), with two Zenoh sessions in one process.

Needs eclipse-zenoh and the NCP 2 core package `ncp` (the repository's python/ directory is put on
the path). The TLS tests also need the `openssl` command.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(HERE.parent), str(ROOT / "python"), str(ROOT / "python" / "tests")]

import ncp  # noqa: E402
import zenoh  # noqa: E402
from echo_owner import Echo  # noqa: E402
from ncp import frame as F  # noqa: E402

import ncp_zenoh  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"sleep":{},"spikes":{}},"streams":{}}'
)

TIMEOUT_S = 0.5


class Quiet:
    """An observer that drops events: the tests inject failures on purpose."""

    def event(self, event) -> None:
        pass


QUIET = Quiet()


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def plain_config(**endpoints: list[str]) -> zenoh.Config:
    config = zenoh.Config()
    config.insert_json5("mode", '"peer"')
    config.insert_json5("scouting/multicast/enabled", "false")
    for name, values in endpoints.items():
        config.insert_json5(f"{name}/endpoints", json.dumps(values))
    return config


def wait_for_peer(session: zenoh.Session, seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if list(session.info.peers_zid()):
            return True
        time.sleep(0.01)
    return False


class Counting(Echo):
    """The echo handler of the SDK tests, counting the executions of each body member `k`."""

    def __init__(self, counts: dict) -> None:
        super().__init__()
        self.counts = counts

    def execute(self, request):
        body = request.body
        if isinstance(body, dict) and "k" in body:
            self.counts[body["k"]] = self.counts.get(body["k"], 0) + 1
        if request.op == "sleep":  # a slow step
            time.sleep(body["seconds"])
            return body
        return super().execute(request)


class Service:
    """An owner session that serves `ncp/x/<service>`, and a client session."""

    def __init__(self, owner_config: zenoh.Config, client_config: zenoh.Config, **serve_options) -> None:
        self.counts: dict = {}
        self.name = f"test/{uuid.uuid4().hex[:8]}"
        self.owner_session = zenoh.open(owner_config)
        self.client_session = zenoh.open(client_config)

        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT, Counting(self.counts), observer=QUIET)

        self.server = ncp_zenoh.Server(self.owner_session, self.name, make_owner, observer=QUIET, **serve_options)
        self.server.start()
        self.linked = wait_for_peer(self.client_session)

    def client(self, channel: ncp_zenoh.ZenohChannel | None = None, timeout: float = TIMEOUT_S) -> ncp.Client:
        channel = channel or ncp_zenoh.ZenohChannel(self.client_session, self.name)
        return ncp.Client(channel, CONTRACT, timeout=timeout, observer=QUIET)

    def answers(self) -> bool:
        """Wait until the service answers a request of an unknown session. A linked peer does not
        yet mean that the declaration of the service has reached the client; without this wait,
        a test that expects no reply could pass without reaching the owner."""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            probe = {"ncp": 2, "session": str(uuid.uuid4()), "seq": 1, "op": "echo", "ack": "0" * 64, "body": {}}
            if self.raw(F.encode(probe), 0.3):
                return True
        return False

    def raw(self, frame: bytes, seconds: float = 1.0) -> list[bytes]:
        """Send one frame as a query and return every reply frame."""
        replies = self.client_session.get(ncp_zenoh.exchange_key(self.name), payload=frame, timeout=seconds)
        return [reply.ok.payload.to_bytes() for reply in replies if reply.ok is not None]

    def close(self, grace: float = 0.0) -> None:
        self.server.stop(grace)
        self.client_session.close()
        self.owner_session.close()


def plain_service(**serve_options) -> Service:
    endpoint = f"tcp/127.0.0.1:{free_port()}"
    service = Service(plain_config(listen=[endpoint]), plain_config(connect=[endpoint]), **serve_options)
    if not (service.linked and service.answers()):
        service.close()
        raise AssertionError("the service never answered")
    return service


def outcome(frame: bytes) -> tuple[str, str | None]:
    message = F.decode(frame, F.MAX_BOUND).message
    return message["outcome"], message["code"]


class Dropping(ncp_zenoh.ZenohChannel):
    """A channel that loses the first query or the first reply of one request, as a network can."""

    def __init__(self, session, service, *, lose: str, seq: int) -> None:
        super().__init__(session, service)
        self.lose, self.seq, self.lost = lose, seq, False

    def _seq(self, frame: bytes) -> int:
        return F.decode(frame, F.MAX_BOUND).message["seq"]

    def send(self, frame: bytes) -> None:
        if self.lose == "query" and not self.lost and self._seq(frame) == self.seq:
            self.lost = True
            return
        super().send(frame)

    def receive(self, bound: int, timeout: float | None) -> bytes:
        frame = super().receive(bound, timeout)
        if self.lose == "reply" and not self.lost and self._seq(frame) == self.seq:
            self.lost = True
            raise TimeoutError("the reply was lost")
        return frame


class ExchangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = plain_service()
        self.assertTrue(self.service.linked)

    def tearDown(self) -> None:
        self.service.close()

    def test_a_session_runs_and_its_transcript_verifies(self) -> None:
        directory = Path(tempfile.mkdtemp())
        tap = ncp.Tap(directory / "client.ncpt")
        client = self.service.client(ncp_zenoh.ZenohChannel(self.service.client_session, self.service.name, tap=tap))
        info = client.open()
        self.assertEqual(info["contract"], CONTRACT.identity)
        self.assertEqual(client.call("echo", {"k": 1, "x": "y"}).body, {"k": 1, "x": "y"})
        spikes = client.call("spikes", {"n": 127})
        self.assertEqual(spikes.body["senders"].shape, (127,))
        self.assertEqual(client.call("echo", {"k": 3}).body, {"k": 3})
        client.close()
        tap.close()
        report = ncp.verify_transcript(directory / "client.ncpt")
        self.assertTrue(report.ok, report)
        (session,) = report.sessions.values()
        self.assertTrue(session.complete)
        self.assertEqual(session.problems, [])
        self.assertEqual(self.service.counts, {1: 1, 3: 1})
        shutil.rmtree(directory)

    def test_a_lost_reply_or_query_still_runs_each_step_once(self) -> None:
        for lose in ("reply", "query"):
            with self.subTest(lose=lose):
                self.service.counts.clear()
                channel = Dropping(self.service.client_session, self.service.name, lose=lose, seq=2)
                client = self.service.client(channel)
                client.open()
                for k in (1, 2, 3):
                    self.assertEqual(client.call("echo", {"k": k}).body, {"k": k})
                client.close()
                self.assertTrue(channel.lost)
                self.assertEqual(self.service.counts, {1: 1, 2: 1, 3: 1})

    def test_a_bad_frame_gets_no_reply(self) -> None:
        client = self.service.client()
        client.open()
        state = client.state
        good = F.encode(
            {"ncp": 2, "session": state.session, "seq": 1, "op": "echo", "ack": state.ack, "body": {"k": 9}}
        )
        bad = bytearray(good)
        bad[20] ^= 0x01
        self.assertEqual(self.service.raw(bytes(bad)), [])
        self.assertNotIn(9, self.service.counts)
        self.assertEqual(client.call("echo", {"k": 1}).body, {"k": 1})  # the session goes on
        client.close()

    def test_sessions_are_independent(self) -> None:
        first, second = self.service.client(), self.service.client()
        first.open()
        second.open()
        self.assertEqual(first.call("echo", {"k": 1}).body, {"k": 1})
        self.assertEqual(second.call("echo", {"k": 2}).body, {"k": 2})
        first.close()
        self.assertEqual(second.call("echo", {"k": 3}).body, {"k": 3})
        second.close()
        self.assertEqual(self.service.counts, {1: 1, 2: 1, 3: 1})

    def test_a_long_step_does_not_delay_another_session(self) -> None:
        # Rule 9.2.8: each session runs in its own thread.
        slow, fast = self.service.client(timeout=5.0), self.service.client(timeout=5.0)
        slow.open()
        fast.open()
        done = threading.Event()
        thread = threading.Thread(target=lambda: (slow.call("sleep", {"k": 1, "seconds": 1.5}), done.set()))
        thread.start()
        time.sleep(0.2)  # the slow step is running
        started = time.monotonic()
        self.assertEqual(fast.call("echo", {"k": 2}).body, {"k": 2})
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertFalse(done.is_set())
        thread.join(5)
        self.assertTrue(done.is_set())

    def test_a_request_of_a_session_the_owner_does_not_hold(self) -> None:
        # seq > 0: the owner may have forgotten the session or restarted, so the request is
        # possibly executed (rule 9.2.7); seq 0 without open: not_open.
        for seq, op, expected in ((1, "echo", ("ended", "session_expired")), (0, "echo", ("rejected", "not_open"))):
            with self.subTest(seq=seq):
                ack = "0" * 64 if seq else None
                frame = F.encode({"ncp": 2, "session": str(uuid.uuid4()), "seq": seq, "op": op, "ack": ack, "body": {}})
                (reply,) = self.service.raw(frame)
                self.assertEqual(outcome(reply), expected)

    def test_a_failing_handler_ends_the_session_possibly_executed(self) -> None:
        client = self.service.client()
        client.open()
        with self.assertRaises(ncp.Ended) as caught:
            client.call("fail", {})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", ncp.Executed.UNKNOWN))


class StopTests(unittest.TestCase):
    def test_a_stopping_server_answers_as_rule_9_2_9_says(self) -> None:
        service = plain_service()
        try:
            session = str(uuid.uuid4())
            open_frame = F.encode({"ncp": 2, "session": session, "seq": 0, "op": "open", "ack": None,
                                   "body": {"application": "echo", "contract": CONTRACT.identity,
                                            "bound": F.HANDSHAKE_BOUND}})
            (opened,) = service.raw(open_frame)
            step = F.encode({"ncp": 2, "session": session, "seq": 1, "op": "echo", "ack": F.identity(opened),
                             "body": {"k": 1}})
            (kept,) = service.raw(step)
            self.assertEqual(outcome(kept), ("ok", None))
            stopper = threading.Thread(target=service.server.stop, args=(1.5,))
            stopper.start()
            time.sleep(0.3)  # the owners have stopped; the queryable is still declared
            self.assertEqual(service.raw(step), [kept])  # a copy of the kept request: the kept response
            later = F.encode({"ncp": 2, "session": session, "seq": 2, "op": "echo", "ack": F.identity(kept),
                              "body": {"k": 2}})
            (ended,) = service.raw(later)
            self.assertEqual(outcome(ended), ("ended", "shutdown"))
            with self.assertRaises(ncp.Rejected) as refused:
                service.client().open()
            self.assertEqual(refused.exception.code, "refused")
            stopper.join(5)
            self.assertEqual(service.raw(step, 0.5), [])  # the service is undeclared
            self.assertEqual(service.counts, {1: 1})
            self.assertEqual(service.server.sessions, 0)
        finally:
            service.close()


class FakeQuery:
    """A query without a network, for the server's routing."""

    def __init__(self, frame: bytes, replies: queue.SimpleQueue) -> None:
        self.payload = zenoh.ZBytes(frame)
        self.replies = replies

    def reply(self, key: str, payload: bytes) -> None:
        self.replies.put(bytes(payload))

    def drop(self) -> None:
        pass


class Gate(Counting):
    """Counting, with a validation that declines `{"bad": true}` and fails on `{"boom": true}`."""

    def validate(self, request):
        body = request.body
        if isinstance(body, dict) and body.get("bad"):
            raise ncp.Declined("bad")
        if isinstance(body, dict) and body.get("boom"):
            raise KeyError("boom")
        return super().validate(request)


class Direct:
    """A lossy channel straight into a server's routing, without a network: it can lose the reply
    of one request and replace the server, as an owner restart does."""

    lossy = True
    local = False

    def __init__(self, server) -> None:
        self.server = server
        self.replies: queue.SimpleQueue = queue.SimpleQueue()
        self.lose_reply_of: int | None = None
        self.then_restart = None

    def send(self, frame: bytes) -> None:
        seq = F.decode(frame, F.MAX_BOUND, check_digest=False).message["seq"]  # also a keyed frame
        if seq == self.lose_reply_of:
            self.lose_reply_of = None
            lost: queue.SimpleQueue = queue.SimpleQueue()
            self.server._on_query(FakeQuery(frame, lost))
            lost.get(timeout=5)  # the owner answered; the reply is lost
            if self.then_restart is not None:
                self.server, self.then_restart = self.then_restart(), None
            return
        self.server._on_query(FakeQuery(frame, self.replies))

    def receive(self, bound: int, timeout: float | None) -> bytes:
        try:
            return self.replies.get(timeout=0.5)
        except queue.Empty:
            raise TimeoutError from None

    def close(self) -> None:
        pass


class RoutingTests(unittest.TestCase):
    """The routing of the Python server, driven directly."""

    def setUp(self) -> None:
        self.counts: dict = {}
        self.servers: list = []

    def tearDown(self) -> None:
        for server in self.servers:
            server.stop(0.0)

    def server(self, max_sessions: int = 4096):
        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT, Gate(self.counts), observer=QUIET)

        server = ncp_zenoh.Server(None, "test/direct", make_owner, max_sessions=max_sessions, observer=QUIET)
        self.servers.append(server)
        return server

    def client(self, channel) -> ncp.Client:
        return ncp.Client(channel, CONTRACT, timeout=0.2, retries=1, observer=QUIET)

    def test_after_a_restart_an_executed_request_is_possibly_executed(self) -> None:
        channel = Direct(self.server())
        client = self.client(channel)
        client.open()
        channel.lose_reply_of, channel.then_restart = 1, self.server
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"k": 1})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("session_expired", ncp.Executed.UNKNOWN))
        self.assertEqual(self.counts, {1: 1})  # it did run, and the client was not told otherwise

    def test_a_repeated_declined_request_gets_the_same_answer(self) -> None:
        channel = Direct(self.server())
        client = self.client(channel)
        client.open()
        channel.lose_reply_of = 1  # the first copy's reply is lost, the client sends the frame again
        with self.assertRaises(ncp.Declined) as caught:
            client.call("echo", {"bad": True})
        self.assertEqual(caught.exception.code, "body_invalid")
        self.assertEqual(client.call("echo", {"k": 2}).body, {"k": 2})  # the session goes on

    def test_a_failing_validation_ends_only_its_own_session(self) -> None:
        server = self.server()
        failing, healthy = self.client(Direct(server)), self.client(Direct(server))
        failing.open()
        healthy.open()
        with self.assertRaises(ncp.Ended) as caught:
            failing.call("echo", {"boom": True})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", ncp.Executed.UNKNOWN))
        self.assertEqual(healthy.call("echo", {"k": 3}).body, {"k": 3})

    def test_a_deeply_nested_payload_is_dropped(self) -> None:
        server = self.server()
        region = b"[" * 1_000_000
        frame = F.HEADER.pack(F.MAGIC, len(region), 0) + region + bytes(32)
        replies: queue.SimpleQueue = queue.SimpleQueue()
        server._on_query(FakeQuery(frame, replies))
        self.assertTrue(replies.empty())
        client = self.client(Direct(server))
        client.open()
        self.assertEqual(client.call("echo", {"k": 4}).body, {"k": 4})

    def test_above_the_limit_an_open_is_refused(self) -> None:
        server = self.server(max_sessions=1)
        self.client(Direct(server)).open()
        with self.assertRaises(ncp.Rejected) as caught:
            self.client(Direct(server)).open()
        self.assertEqual(caught.exception.code, "refused")

    def test_a_rejected_open_keeps_no_session(self) -> None:
        server = self.server()
        frame = F.encode({"ncp": 2, "session": str(uuid.uuid4()), "seq": 0, "op": "open", "ack": None,
                          "body": {"application": "echo", "contract": "0" * 64, "bound": F.HANDSHAKE_BOUND}})
        replies: queue.SimpleQueue = queue.SimpleQueue()
        server._on_query(FakeQuery(frame, replies))
        self.assertEqual(outcome(replies.get(timeout=5)), ("rejected", "contract_mismatch"))
        deadline = time.monotonic() + 5
        while server.sessions and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(server.sessions, 0)


class KeyedRoutingTests(unittest.TestCase):
    """A server with a key (section 13.2), driven directly: it checks each frame's authentication
    code before it reads the message, and authenticates the responses that it makes itself."""

    KEY = bytes(range(32))

    def setUp(self) -> None:
        self.counts: dict = {}
        self.servers: list = []

    def tearDown(self) -> None:
        for server in self.servers:
            server.stop(0.0)

    def server(self, *, owner_key: bytes | None = KEY, server_key: bytes | None = KEY):
        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT, Gate(self.counts), observer=QUIET, key=owner_key)

        server = ncp_zenoh.Server(None, "test/keyed", make_owner, observer=QUIET, key=server_key)
        self.servers.append(server)
        return server

    def client(self, server, **options) -> ncp.Client:
        options = {"key": self.KEY, "timeout": 0.2, "retries": 1, **options}
        return ncp.Client(Direct(server), CONTRACT, observer=QUIET, **options)

    def route(self, server, frame: bytes) -> list[bytes]:
        replies: queue.SimpleQueue = queue.SimpleQueue()
        server._on_query(FakeQuery(frame, replies))
        try:
            return [replies.get(timeout=1)]
        except queue.Empty:
            return []

    def test_a_keyed_session_runs_and_frames_without_the_key_get_no_reply(self) -> None:
        server = self.server()
        client = self.client(server)
        client.open()
        self.assertEqual(client.call("echo", {"k": 1}).body, {"k": 1})
        state = client.state
        request = {"ncp": 2, "session": state.session, "seq": 2, "op": "echo", "ack": state.ack, "body": {"k": 2}}
        self.assertEqual(self.route(server, F.encode(request)), [])  # a digest, not the key's code
        self.assertEqual(self.route(server, F.encode(request, key=bytes(32))), [])  # another key
        self.assertNotIn(2, self.counts)
        self.assertEqual(client.call("echo", {"k": 3}).body, {"k": 3})  # the session goes on
        client.close()

    def test_the_responses_of_the_server_itself_carry_the_key(self) -> None:
        server = self.server()
        unknown = {"ncp": 2, "session": str(uuid.uuid4()), "seq": 1, "op": "echo", "ack": "0" * 64, "body": {}}
        (reply,) = self.route(server, F.encode(unknown, key=self.KEY))
        message = F.decode(reply, F.MAX_BOUND, key=self.KEY).message
        self.assertEqual((message["outcome"], message["code"]), ("ended", "session_expired"))
        with self.assertRaises(F.FrameError):
            F.decode(reply, F.MAX_BOUND)  # not a plain digest

    def test_an_owner_without_the_servers_key_gets_no_session(self) -> None:
        server = self.server(owner_key=None)
        with self.assertRaises(ncp.CallError):
            self.client(server).open()
        self.assertEqual(server.sessions, 0)

    def test_a_large_frame_of_a_session_the_server_does_not_hold_is_dropped(self) -> None:
        server = self.server()
        client = self.client(server, bound=F.DEFAULT_BOUND)
        client.open()  # the server now holds a session with a bound above the handshake bound
        large = {"ncp": 2, "session": str(uuid.uuid4()), "seq": 1, "op": "echo", "ack": "0" * 64,
                 "body": {"x": "y" * F.HANDSHAKE_BOUND}}
        self.assertEqual(self.route(server, F.encode(large, key=self.KEY)), [])
        self.assertEqual(client.call("echo", {"x": "y" * F.HANDSHAKE_BOUND}).body["x"], "y" * F.HANDSHAKE_BOUND)

    def test_the_server_raises_its_bound_before_it_answers_open(self) -> None:
        # A client can send a frame of the session bound as soon as it has the `open` response,
        # so the server must check frames against that bound before it sends the response.
        server = self.server()
        at_reply: list[int] = []

        class Recording(FakeQuery):
            def reply(self, key: str, payload: bytes) -> None:
                at_reply.append(server.largest)
                super().reply(key, payload)

        session = str(uuid.uuid4())
        opening = F.encode({"ncp": 2, "session": session, "seq": 0, "op": "open", "ack": None,
                            "body": {"application": "echo", "contract": CONTRACT.identity, "bound": F.DEFAULT_BOUND}},
                           key=self.KEY)
        replies: queue.SimpleQueue = queue.SimpleQueue()
        server._on_query(Recording(opening, replies))
        opened = F.decode(replies.get(timeout=5), F.MAX_BOUND, key=self.KEY)
        self.assertEqual((opened.message["outcome"], opened.message["body"]["bound"]), ("ok", F.DEFAULT_BOUND))
        self.assertEqual(at_reply, [F.DEFAULT_BOUND])
        large = {"x": "y" * (2 * F.HANDSHAKE_BOUND)}
        step = F.encode({"ncp": 2, "session": session, "seq": 1, "op": "echo", "ack": opened.identity, "body": large},
                        key=self.KEY)
        (reply,) = self.route(server, step)
        self.assertEqual(F.decode(reply, F.MAX_BOUND, key=self.KEY).message["body"], large)

    def test_a_request_of_another_protocol_version_gets_wrong_protocol(self) -> None:
        server = self.server()
        later = {"ncp": 3, "session": str(uuid.uuid4()), "seq": 0, "later": [1]}
        (reply,) = self.route(server, F.encode(later, key=self.KEY))
        message = F.decode(reply, F.MAX_BOUND, key=self.KEY).message
        self.assertEqual((message["outcome"], message["code"]), ("rejected", "wrong_protocol"))
        self.assertEqual(server.sessions, 0)


class ExpiryTests(unittest.TestCase):
    def test_a_forgotten_session_ends_with_session_expired(self) -> None:
        service = plain_service(expire_after_s=0.3)
        try:
            client = service.client()
            client.open()
            self.assertEqual(client.call("echo", {"k": 1}).body, {"k": 1})
            time.sleep(0.8)
            with self.assertRaises(ncp.Ended) as caught:
                client.call("echo", {"k": 2})
            self.assertEqual((caught.exception.code, caught.exception.executed), ("session_expired", ncp.Executed.UNKNOWN))
            self.assertNotIn(2, service.counts)
        finally:
            service.close()


class SlowStepTests(unittest.TestCase):
    def test_a_step_longer_than_the_expiry_time_keeps_its_session(self) -> None:
        service = plain_service(expire_after_s=0.4)
        try:
            client = service.client(timeout=2.0)
            client.open()
            self.assertEqual(client.call("sleep", {"k": 1, "seconds": 0.8}).body, {"k": 1, "seconds": 0.8})
            self.assertEqual(client.call("echo", {"k": 2}).body, {"k": 2})  # the session is still known
            client.close()
            self.assertEqual(service.counts, {1: 1, 2: 1})
        finally:
            service.close()


class StreamTests(unittest.TestCase):
    def test_a_subscriber_accepts_every_message_in_order(self) -> None:
        endpoint = f"tcp/127.0.0.1:{free_port()}"
        publishing, subscribing = (
            zenoh.open(plain_config(listen=[endpoint])),
            zenoh.open(plain_config(connect=[endpoint])),
        )
        try:
            self.assertTrue(wait_for_peer(subscribing))
            contract = "a" * 64
            checker, deliveries, done = ncp.Subscriber({contract}), [], threading.Event()

            def on_frame(frame: bytes) -> None:
                deliveries.append(checker.receive(frame))
                if len(deliveries) == 20:
                    done.set()

            subscriber = ncp_zenoh.subscribe(subscribing, "test/sensors", on_frame)
            time.sleep(0.3)  # let the subscription reach the publisher
            publisher = ncp.Publisher("sensors", contract, ncp_zenoh.stream_sender(publishing, "test/sensors"))
            for t in range(20):
                publisher.publish({"t": t})
            self.assertTrue(done.wait(5))
            self.assertEqual([d.status for d in deliveries], ["accepted"] * 20)
            self.assertEqual([d.message["body"]["t"] for d in deliveries], list(range(20)))
            subscriber.undeclare()
        finally:
            subscribing.close()
            publishing.close()

    def test_names_must_be_plain_keys(self) -> None:
        for name in ("", "a/*", "a//b", "a/$b", "a b", "x" * 300):
            with self.subTest(name=name), self.assertRaises(ValueError):
                ncp_zenoh.exchange_key(name)


@unittest.skipUnless(os.environ.get("NCP_ZENOH_RUST_EXAMPLES"), "needs the Rust examples of the binding")
class CrossLanguageTests(unittest.TestCase):
    """The Python client against the Rust owner (bindings/zenoh/rust/examples/zenoh_echo_owner.rs)."""

    def test_python_client_with_the_rust_owner(self) -> None:
        endpoint = f"tcp/127.0.0.1:{free_port()}"
        name = f"test/{uuid.uuid4().hex[:8]}"
        log = Path(tempfile.mkdtemp()) / "executions.jsonl"
        owner = subprocess.Popen(
            [str(Path(os.environ["NCP_ZENOH_RUST_EXAMPLES"]) / "zenoh_echo_owner"), name, endpoint],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            env=dict(os.environ, NCP_EXECUTION_LOG=str(log)),
        )
        session = zenoh.open(plain_config(connect=[endpoint]))
        try:
            self.assertEqual(owner.stdout.readline().strip(), "ready")
            self.assertTrue(wait_for_peer(session))
            channel = Dropping(session, name, lose="reply", seq=2)
            client = ncp.Client(channel, CONTRACT, timeout=TIMEOUT_S, observer=QUIET)
            client.open()
            values = ncp.Array("u32", (3,), b"\x01\x00\x00\x00\x02\x00\x00\x00\x03\x00\x00\x00")
            for k in (1, 2, 3):
                result = client.call("echo", {"k": k, "a": values})
                self.assertEqual(result.body["k"], k)
                self.assertEqual(result.body["a"].tolist(), [1, 2, 3])
            client.close()
            self.assertTrue(channel.lost)
            executed = [json.loads(line)["k"] for line in log.read_text().splitlines()]
            self.assertEqual(executed, [1, 2, 3])  # the lost reply did not run step 2 again
        finally:
            session.close()
            owner.stdin.close()
            owner.wait(10)
            owner.stdout.close()
            shutil.rmtree(log.parent)


def openssl(*args: str, cwd: Path) -> None:
    subprocess.run(["openssl", *args], cwd=cwd, check=True, capture_output=True)


def make_ca(directory: Path, name: str) -> None:
    openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", f"{name}.key", cwd=directory)
    (directory / f"{name}.ext").write_text(
        "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n"
    )
    openssl("req", "-new", "-key", f"{name}.key", "-subj", f"/CN={name}", "-out", f"{name}.csr", cwd=directory)
    openssl(
        "x509", "-req", "-in", f"{name}.csr", "-signkey", f"{name}.key", "-days", "30",
        "-extfile", f"{name}.ext", "-out", f"{name}.pem", cwd=directory,
    )  # fmt: skip


def make_certificate(directory: Path, ca: str, name: str) -> None:
    openssl("genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", "-out", f"{name}.key", cwd=directory)
    (directory / f"{name}.ext").write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\n"
        "extendedKeyUsage=serverAuth,clientAuth\nsubjectAltName=DNS:localhost\n"
    )
    openssl("req", "-new", "-key", f"{name}.key", "-subj", f"/CN={name}", "-out", f"{name}.csr", cwd=directory)
    openssl(
        "x509", "-req", "-in", f"{name}.csr", "-CA", f"{ca}.pem", "-CAkey", f"{ca}.key", "-CAcreateserial",
        "-days", "30", "-extfile", f"{name}.ext", "-out", f"{name}.pem", cwd=directory,
    )  # fmt: skip


def tls(directory: Path, ca: str, name: str, **endpoints: list[str]) -> zenoh.Config:
    return ncp_zenoh.secure_config(
        root_ca_certificate=str(directory / f"{ca}.pem"),
        certificate=str(directory / f"{name}.pem"),
        private_key=str(directory / f"{name}.key"),
        **endpoints,
    )


def access_control(config: zenoh.Config, service: str, allowed: str) -> zenoh.Config:
    """Allow only the peer whose certificate names `allowed` to query the service."""
    key = ncp_zenoh.exchange_key(service)
    rules = {
        "enabled": True,
        "default_permission": "deny",
        "rules": [
            {
                "id": "ncp-exchange",
                "messages": ["query", "reply", "declare_queryable"],
                "flows": ["ingress", "egress"],
                "permission": "allow",
                "key_exprs": [key],
            }
        ],
        "subjects": [{"id": "allowed-client", "cert_common_names": [allowed]}],
        "policies": [{"rules": ["ncp-exchange"], "subjects": ["allowed-client"]}],
    }
    config.insert_json5("access_control", json.dumps(rules))
    return config


def client_access_control(config: zenoh.Config, service: str, owner: str) -> zenoh.Config:
    """Rule 9.2.6, the client's side: admit only the peer whose certificate names `owner` as the one
    that may declare the queryable of the service and reply on its key."""
    key = ncp_zenoh.exchange_key(service)
    rules = {
        "enabled": True,
        "default_permission": "deny",
        "rules": [
            {"id": "send-queries", "messages": ["query"], "flows": ["egress"], "permission": "allow",
             "key_exprs": [key]},
            {"id": "owner-replies", "messages": ["reply", "declare_queryable"], "flows": ["ingress"],
             "permission": "allow", "key_exprs": [key]},
        ],
        "subjects": [{"id": "owner", "cert_common_names": [owner]}],
        "policies": [{"rules": ["send-queries", "owner-replies"], "subjects": ["owner"]}],
    }
    config.insert_json5("access_control", json.dumps(rules))
    return config


@unittest.skipUnless(shutil.which("openssl"), "needs the openssl command")
class TlsTests(unittest.TestCase):
    """Rule 9.2.6: mutual TLS, and access control by the client's certificate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = Path(tempfile.mkdtemp())
        make_ca(cls.directory, "ca")
        make_ca(cls.directory, "other-ca")
        for name in ("owner", "client-a", "client-b"):
            make_certificate(cls.directory, "ca", name)
        make_certificate(cls.directory, "other-ca", "intruder")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.directory)

    def service(
        self, client: str, ca: str = "ca", allowed: str | None = None, owner: str = "owner",
        trusted_owner: str | None = None,
    ) -> Service:
        endpoint = f"tls/localhost:{free_port()}"
        name = f"test/{uuid.uuid4().hex[:8]}"
        owner_config = tls(self.directory, "ca", owner, listen=[endpoint])
        if allowed is not None:
            owner_config = access_control(owner_config, name, allowed)
        client_config = tls(self.directory, ca, client, connect=[endpoint])
        if trusted_owner is not None:
            client_config = client_access_control(client_config, name, trusted_owner)
        service = Service.__new__(Service)
        service.counts, service.name = {}, name
        service.owner_session = zenoh.open(owner_config)
        service.client_session = zenoh.open(client_config)

        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT, Counting(service.counts), observer=QUIET)

        service.server = ncp_zenoh.Server(service.owner_session, name, make_owner, observer=QUIET).start()
        service.linked = wait_for_peer(service.client_session, 3.0)
        return service

    def test_mutual_tls_admits_a_client_with_a_certificate_of_the_ca(self) -> None:
        service = self.service("client-a")
        try:
            self.assertTrue(service.linked)
            client = service.client()
            client.open()
            self.assertEqual(client.call("echo", {"k": 1}).body, {"k": 1})
            client.close()
        finally:
            service.close()

    def test_mutual_tls_refuses_a_client_of_another_ca(self) -> None:
        service = self.service("intruder", ca="other-ca")
        try:
            self.assertFalse(service.linked)
            with self.assertRaises(ncp.Ended) as caught:
                service.client().open()
            self.assertEqual(caught.exception.code, "local.timeout")
            self.assertEqual(service.counts, {})
        finally:
            service.close()

    def test_access_control_admits_only_the_named_certificate(self) -> None:
        # The last case is the control: without access control, client-b is admitted, so its refusal
        # in the second case comes from the access control, not from its certificate.
        for client, allowed, admitted in (
            ("client-a", "client-a", True),
            ("client-b", "client-a", False),
            ("client-b", None, True),
        ):
            with self.subTest(client=client, allowed=allowed):
                service = self.service(client, allowed=allowed)
                try:
                    self.assertTrue(service.linked)  # both certificates come from the CA
                    session = service.client()
                    if admitted:
                        session.open()
                        self.assertEqual(session.call("echo", {"k": 1}).body, {"k": 1})
                        session.close()
                    else:
                        with self.assertRaises(ncp.Ended) as caught:
                            session.open()
                        self.assertEqual(caught.exception.code, "local.timeout")
                        self.assertEqual(service.counts, {})
                finally:
                    service.close()


    def test_the_client_admits_only_the_owner_it_trusts(self) -> None:
        # The client's side of rule 9.2.6. An impostor with a certificate of the same CA declares
        # the service. The last case is the control: without the client's access control, the
        # impostor answers, so the refusal in the second case comes from the access control.
        for owner, trusted, answered in (
            ("owner", "owner", True),
            ("client-b", "owner", False),
            ("client-b", None, True),
        ):
            with self.subTest(owner=owner, trusted=trusted):
                service = self.service("client-a", owner=owner, trusted_owner=trusted)
                try:
                    self.assertTrue(service.linked)
                    session = service.client()
                    if answered:
                        session.open()
                        self.assertEqual(session.call("echo", {"k": 1}).body, {"k": 1})
                        session.close()
                    else:
                        with self.assertRaises(ncp.Ended) as caught:
                            session.open()
                        self.assertEqual(caught.exception.code, "local.timeout")
                        self.assertEqual(service.counts, {})
                finally:
                    service.close()

if __name__ == "__main__":
    os.environ.setdefault("RUST_LOG", "error")
    unittest.main()
