"""Tests of the Zenoh binding (specification, section 9.2), with two Zenoh sessions in one process.

Needs eclipse-zenoh and the NCP 2 core package `ncp` (the repository's python/ directory is put on
the path). The TLS tests also need the `openssl` command.
"""

from __future__ import annotations

import json
import os
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

    def execute(self, op, body):
        if isinstance(body, dict) and "k" in body:
            self.counts[body["k"]] = self.counts.get(body["k"], 0) + 1
        if op == "sleep":  # a slow step
            time.sleep(body["seconds"])
            return body
        return super().execute(op, body)


class Service:
    """An owner session that serves `ncp/x/<service>` in a thread, and a client session."""

    def __init__(self, owner_config: zenoh.Config, client_config: zenoh.Config, **serve_options) -> None:
        self.counts: dict = {}
        self.name = f"test/{uuid.uuid4().hex[:8]}"
        self.owner_session = zenoh.open(owner_config)
        self.client_session = zenoh.open(client_config)
        self.stop, ready = threading.Event(), threading.Event()

        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT.application, CONTRACT.identity, Counting(self.counts), CONTRACT.operations)

        self.thread = threading.Thread(
            target=ncp_zenoh.serve,
            args=(self.owner_session, self.name, make_owner),
            kwargs={"stop": self.stop, "ready": ready, **serve_options},
            daemon=True,
        )
        self.thread.start()
        ready.wait(5)
        self.linked = wait_for_peer(self.client_session)

    def client(self, channel: ncp_zenoh.ZenohChannel | None = None, timeout: float = TIMEOUT_S) -> ncp.Client:
        channel = channel or ncp_zenoh.ZenohChannel(self.client_session, self.name)
        return ncp.Client(channel, application=CONTRACT.application, contract=CONTRACT.identity, timeout=timeout)

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

    def close(self) -> None:
        self.stop.set()
        self.thread.join(5)
        self.client_session.close()
        self.owner_session.close()


def plain_service(**serve_options) -> Service:
    endpoint = f"tcp/127.0.0.1:{free_port()}"
    service = Service(plain_config(listen=[endpoint]), plain_config(connect=[endpoint]), **serve_options)
    if not (service.linked and service.answers()):
        service.close()
        raise AssertionError("the service never answered")
    return service


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
        (report,) = ncp.verify_transcript(directory / "client.ncpt").values()
        self.assertTrue(report.complete)
        self.assertEqual(report.problems, [])
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
        good = F.encode(
            {"ncp": 2, "session": client.session, "seq": 1, "op": "echo", "ack": client.ack, "body": {"k": 9}}
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

    def test_a_request_of_a_session_the_owner_does_not_hold(self) -> None:
        # seq > 0: the owner may have forgotten the session or restarted, so the request is
        # possibly executed (rule 9.2.7); seq 0 without open: not_open.
        for seq, op, expected in ((1, "echo", ("ended", "session_expired")), (0, "echo", ("rejected", "not_open"))):
            with self.subTest(seq=seq):
                ack = "0" * 64 if seq else None
                frame = F.encode({"ncp": 2, "session": str(uuid.uuid4()), "seq": seq, "op": op, "ack": ack, "body": {}})
                (reply,) = self.service.raw(frame)
                message = F.decode(reply, F.MAX_BOUND).message
                self.assertEqual((message["outcome"], message["code"]), expected)

    def test_a_failing_handler_ends_the_session_possibly_executed(self) -> None:
        client = self.service.client()
        client.open()
        with self.assertRaises(ncp.Ended) as caught:
            client.call("fail", {})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", "unknown"))


class Gate(Counting):
    """Counting, with a validation that rejects `{"bad": true}` and fails on `{"boom": true}`."""

    def validate(self, op, body):
        if isinstance(body, dict) and body.get("bad"):
            raise ncp.BodyInvalid("bad")
        if isinstance(body, dict) and body.get("boom"):
            raise KeyError("boom")
        return super().validate(op, body)


class Direct:
    """A lossy channel straight into a session table, without a network: it can lose the reply of
    one request and replace the table, as an owner restart does."""

    lossy = True

    def __init__(self, table) -> None:
        self.table, self.replies = table, []
        self.lose_reply_of: int | None = None
        self.then_restart = None

    def send(self, frame: bytes) -> None:
        reply = self.table.respond(frame)
        seq = F.decode(frame, F.MAX_BOUND).message["seq"]
        if seq == self.lose_reply_of:
            self.lose_reply_of = None
            if self.then_restart is not None:
                self.table, self.then_restart = self.then_restart(), None
            return
        if reply is not None:
            self.replies.append(reply)

    def receive(self, bound: int, timeout: float | None) -> bytes:
        if not self.replies:
            raise TimeoutError
        return self.replies.pop(0)


class SessionTableTests(unittest.TestCase):
    """The session table of the Python server, driven directly."""

    def setUp(self) -> None:
        self.counts: dict = {}

    def table(self, max_sessions: int = 4096):
        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT.application, CONTRACT.identity, Gate(self.counts), CONTRACT.operations)

        return ncp_zenoh._Sessions(make_owner, 600.0, max_sessions)

    def client(self, channel) -> ncp.Client:
        return ncp.Client(channel, application=CONTRACT.application, contract=CONTRACT.identity, timeout=0.01)

    def test_after_a_restart_an_executed_request_is_possibly_executed(self) -> None:
        channel = Direct(self.table())
        client = self.client(channel)
        client.open()
        channel.lose_reply_of, channel.then_restart = 1, self.table
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"k": 1})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("session_expired", "unknown"))
        self.assertEqual(self.counts, {1: 1})  # it did run, and the client was not told otherwise

    def test_a_repeated_request_rejected_as_invalid_is_possibly_executed(self) -> None:
        channel = Direct(self.table())
        client = self.client(channel)
        client.open()
        channel.lose_reply_of = 1  # the first copy's reply is lost, the client sends the frame again
        with self.assertRaises(ncp.Ended) as caught:
            client.call("echo", {"bad": True})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("body_invalid", "unknown"))

    def test_a_request_rejected_once_stays_rejected(self) -> None:
        client = self.client(Direct(self.table()))
        client.open()
        with self.assertRaises(ncp.Rejected) as caught:
            client.call("echo", {"bad": True})
        self.assertEqual(caught.exception.code, "body_invalid")
        self.assertEqual(client.call("echo", {"k": 2}).body, {"k": 2})  # the corrected request

    def test_a_failing_validation_ends_only_its_own_session(self) -> None:
        table = self.table()
        failing, healthy = self.client(Direct(table)), self.client(Direct(table))
        failing.open()
        healthy.open()
        with self.assertRaises(ncp.Ended) as caught:
            failing.call("echo", {"boom": True})
        self.assertEqual((caught.exception.code, caught.exception.executed), ("owner_failure", "unknown"))
        self.assertEqual(healthy.call("echo", {"k": 3}).body, {"k": 3})

    def test_a_deeply_nested_payload_is_dropped(self) -> None:
        table = self.table()
        region = b"[" * 1_000_000
        frame = F.HEADER.pack(F.MAGIC, len(region), 0) + region + bytes(32)
        self.assertIsNone(table.respond(frame))
        client = self.client(Direct(table))
        client.open()
        self.assertEqual(client.call("echo", {"k": 4}).body, {"k": 4})

    def test_above_the_limit_an_open_is_refused(self) -> None:
        table = self.table(max_sessions=1)
        self.client(Direct(table)).open()
        with self.assertRaises(ncp.Rejected) as caught:
            self.client(Direct(table)).open()
        self.assertEqual(caught.exception.code, "refused")


class ExpiryTests(unittest.TestCase):
    def test_a_forgotten_session_ends_with_session_expired(self) -> None:
        service = plain_service(expire_after_s=0.3)
        try:
            client = service.client()
            client.open()
            self.assertEqual(client.call("echo", {"k": 1}).body, {"k": 1})
            time.sleep(0.6)
            with self.assertRaises(ncp.Ended) as caught:
                client.call("echo", {"k": 2})
            self.assertEqual((caught.exception.code, caught.exception.executed), ("session_expired", "unknown"))
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
            client = ncp.Client(
                channel, application=CONTRACT.application, contract=CONTRACT.identity, timeout=TIMEOUT_S
            )
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

    def service(self, client: str, ca: str = "ca", allowed: str | None = None) -> Service:
        endpoint = f"tls/localhost:{free_port()}"
        name = f"test/{uuid.uuid4().hex[:8]}"
        owner_config = tls(self.directory, "ca", "owner", listen=[endpoint])
        if allowed is not None:
            owner_config = access_control(owner_config, name, allowed)
        service = Service.__new__(Service)
        service.counts, service.name = {}, name
        service.owner_session = zenoh.open(owner_config)
        service.client_session = zenoh.open(tls(self.directory, ca, client, connect=[endpoint]))
        service.stop, ready = threading.Event(), threading.Event()

        def make_owner() -> ncp.Owner:
            return ncp.Owner(CONTRACT.application, CONTRACT.identity, Counting(service.counts), CONTRACT.operations)

        service.thread = threading.Thread(
            target=ncp_zenoh.serve,
            args=(service.owner_session, name, make_owner),
            kwargs={"stop": service.stop, "ready": ready},
            daemon=True,
        )
        service.thread.start()
        ready.wait(5)
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
            self.assertEqual(caught.exception.code, "timeout")
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
                        self.assertEqual(caught.exception.code, "timeout")
                        self.assertEqual(service.counts, {})
                finally:
                    service.close()


if __name__ == "__main__":
    os.environ.setdefault("RUST_LOG", "error")
    unittest.main()
