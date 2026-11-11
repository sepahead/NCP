"""The Zenoh binding of NCP 2 (specification, section 9.2), for Python.

Exchanges travel as Zenoh queries and replies, streams as Zenoh publications. This package is
optional: it needs `eclipse-zenoh`, and the NCP 2 core package `ncp` never imports it.

- An owner serves on the key `ncp/x/<service>` (`serve`). A client sends each request frame as
  the payload of a query to that key (`ZenohChannel`), and the owner replies with the response
  frame (rule 9.2.1).
- A publisher puts stream frames on `ncp/s/<stream-key>` (`stream_sender`), and subscribers
  subscribe to that key (`subscribe`) (rule 9.2.2).
- A receiver drops a bad frame (rule 9.2.3).
- The client accepts only the reply that matches its request; when no reply arrives in time, it
  sends the same request frame again (rule 9.2.4). `ncp.Client` does this for a channel whose
  `lossy` is true, and the owner answers a repeated request with its kept response (rule 7.3.5),
  so the request still runs at most once.
- Each owner uses its own service key (rule 9.2.5).
- On networks that are not trusted, the Zenoh sessions MUST use TLS with client certificates and
  Zenoh access control (rule 9.2.6). `secure_config` writes the TLS part of such a configuration;
  the README shows the access control.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable
from typing import Any

import ncp
import zenoh
from ncp import frame as F
from ncp.exchange import check_request
from ncp.transcript import RECEIVED, SENT, Tap

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "EXCHANGE_PREFIX",
    "STREAM_PREFIX",
    "ZenohChannel",
    "exchange_key",
    "secure_config",
    "serve",
    "stream_key",
    "stream_sender",
    "subscribe",
]

EXCHANGE_PREFIX = "ncp/x/"
STREAM_PREFIX = "ncp/s/"
# How long a client waits for a reply before it sends the request again, if its ncp.Client has no
# time limit of its own.
DEFAULT_TIMEOUT_S = 1.0
# How long Zenoh keeps a query open for a late reply. A reply after the client's time limit still
# reaches the channel; ncp.Client drops a reply that does not match its current request.
QUERY_TIMEOUT_S = 10.0
# Chunks of letters, digits, '_', '.', and '-', separated by '/': a Zenoh key without wildcards.
_NAME = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\Z")


def _key(prefix: str, name: str) -> str:
    if type(name) is not str or _NAME.match(name) is None or len(name) > 256:
        raise ValueError(f"not a service or stream name: {name!r}")
    return prefix + name


def exchange_key(service: str) -> str:
    """The Zenoh key of an owner's service: `ncp/x/<service>`."""
    return _key(EXCHANGE_PREFIX, service)


def stream_key(name: str) -> str:
    """The Zenoh key of a stream: `ncp/s/<name>`."""
    return _key(STREAM_PREFIX, name)


class ZenohChannel:
    """A client channel to one service, for `ncp.Client`.

    Zenoh can lose a query or a reply, so the channel is lossy: after the time limit, the client
    sends the same request frame again. `timeout` is that limit when the client sets none. Every
    sent frame and every received reply go to `tap`, if given.
    """

    lossy = True

    def __init__(
        self,
        session: zenoh.Session,
        service: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        tap: Tap | None = None,
    ) -> None:
        self.session, self.key = session, exchange_key(service)
        self.timeout, self.tap = timeout, tap
        self._replies: queue.SimpleQueue[bytes] = queue.SimpleQueue()

    def _on_reply(self, reply: zenoh.Reply) -> None:
        sample = reply.ok
        if sample is not None:  # an error reply carries no frame
            self._replies.put(sample.payload.to_bytes())

    def send(self, frame: bytes) -> None:
        if self.tap is not None:
            self.tap.record(SENT, frame)
        self.session.get(self.key, self._on_reply, payload=frame, timeout=QUERY_TIMEOUT_S)

    def receive(self, bound: int, timeout: float | None) -> bytes:
        """The next reply. Raises TimeoutError after `timeout`, or the channel's own limit."""
        try:
            frame = self._replies.get(timeout=self.timeout if timeout is None else timeout)
        except queue.Empty:
            raise TimeoutError("no reply from the owner") from None
        if self.tap is not None:
            self.tap.record(RECEIVED, frame)
        return frame


class _Refuser:
    """The handler of an owner that never opens: it answers `not_open` for an unknown session."""

    def validate(self, op: str, body: Any) -> None:
        raise ncp.BodyInvalid("no session")

    def execute(self, op: str, body: Any) -> Any:
        raise RuntimeError("no session")


def _peek(frame: bytes) -> tuple[Any, Any, Any]:
    """The session, op, and seq of a request frame, read from its JSON region only. Raises
    ValueError for a frame that cannot be a request. The owner checks the whole frame."""
    if len(frame) < F.OVERHEAD or len(frame) > F.MAX_BOUND or frame[:4] != F.MAGIC:
        raise ValueError("not a frame")
    _, json_length, attachment_length = F.HEADER.unpack_from(frame)
    if F.OVERHEAD + json_length + attachment_length != len(frame):
        raise ValueError("frame length")
    message = json.loads(frame[F.HEADER_BYTES : F.HEADER_BYTES + json_length])
    if type(message) is not dict:
        raise ValueError("not an object")
    return message.get("session"), message.get("op"), message.get("seq")


def _expired(frame: bytes) -> bytes | None:
    """The `ended` response with the code `session_expired` to a request of a forgotten session,
    or None for a bad frame."""
    try:
        decoded = F.decode(frame, F.MAX_BOUND)
        check_request(decoded.message)
    except F.FrameError:
        return None
    request = decoded.message
    return F.encode(
        {
            "ncp": ncp.PROTOCOL,
            "session": request["session"],
            "seq": request["seq"],
            "request": decoded.identity,
            "outcome": "ended",
            "code": "session_expired",
            "body": {},
        }
    )


class _Sessions:
    """The owners of one service, one for each session, and the sessions that it forgot."""

    def __init__(self, make_owner: Callable[[], ncp.Owner], expire_after_s: float, remember: int) -> None:
        self.make_owner, self.expire_after_s, self.remember = make_owner, expire_after_s, remember
        self.owners: dict[str, tuple[ncp.Owner, float]] = {}
        self.forgotten: OrderedDict[str, None] = OrderedDict()

    def respond(self, frame: bytes, now: float) -> bytes | None:
        """The response frame to one request frame, or None for a bad frame (rule 9.2.3)."""
        try:
            session, op, seq = _peek(frame)
        except (ValueError, UnicodeDecodeError):
            return None
        if type(session) is not str:
            return None
        if session in self.owners:
            owner = self.owners[session][0]
        elif session in self.forgotten:
            return _expired(frame)
        elif op == "open" and seq == 0:
            try:  # check the whole frame before the application makes an owner for it
                check_request(F.decode(frame, F.HANDSHAKE_BOUND).message)
            except F.FrameError:
                return None
            owner = self.make_owner()
        else:
            owner = ncp.Owner("ncp", "0" * 64, _Refuser(), ())
            owner.bound = F.MAX_BOUND  # read a request of any size, to answer not_open
            try:
                return owner.handle(frame)
            except F.FrameError:
                return None
        try:
            response = owner.handle(frame)
        except F.FrameError:
            return None
        if owner.session == session:  # the open was accepted, or the session already existed
            self.owners[session] = (owner, now)
        return response

    def expire(self, now: float) -> None:
        """Forget the sessions without a request for `expire_after_s`."""
        for session, (_, last) in list(self.owners.items()):
            if now - last >= self.expire_after_s:
                del self.owners[session]
                self.forgotten[session] = None
        while len(self.forgotten) > self.remember:
            self.forgotten.popitem(last=False)


def serve(
    session: zenoh.Session,
    service: str,
    make_owner: Callable[[], ncp.Owner],
    *,
    stop: threading.Event | None = None,
    ready: threading.Event | None = None,
    expire_after_s: float = 600.0,
    remember: int = 100_000,
) -> None:
    """Serve exchange sessions on `ncp/x/<service>` until `stop` is set.

    `make_owner` returns a new `ncp.Owner` for each new session. The caller's thread handles the
    queries in their order of arrival, one at a time, so a long step of one session delays the
    others. A session without a request for `expire_after_s` seconds is forgotten (rule 9.2.7):
    its later requests are answered with `ended` and the code `session_expired`, possibly
    executed. The identifiers of up to `remember` forgotten sessions are kept for this. `ready` is
    set once the service is declared.
    """
    key = exchange_key(service)
    incoming: queue.SimpleQueue[zenoh.Query] = queue.SimpleQueue()
    queryable = session.declare_queryable(key, incoming.put, complete=True)
    sessions = _Sessions(make_owner, expire_after_s, remember)
    if ready is not None:
        ready.set()
    try:
        while stop is None or not stop.is_set():
            sessions.expire(time.monotonic())
            try:
                query = incoming.get(timeout=0.05)
            except queue.Empty:
                continue
            payload = query.payload
            response = None if payload is None else sessions.respond(payload.to_bytes(), time.monotonic())
            if response is not None:
                query.reply(key, response)
            query.drop()  # the query is complete: the client stops waiting for more replies
    finally:
        queryable.undeclare()


def stream_sender(session: zenoh.Session, name: str, **options: Any) -> Callable[[bytes], None]:
    """A `send` function for `ncp.Publisher` that puts each frame on `ncp/s/<name>`. `options`
    go to `declare_publisher`, for example `congestion_control`."""
    publisher = session.declare_publisher(stream_key(name), **options)

    def send(frame: bytes) -> None:
        publisher.put(frame)

    return send


def subscribe(session: zenoh.Session, name: str, on_frame: Callable[[bytes], None]) -> zenoh.Subscriber:
    """Call `on_frame` with every frame put on `ncp/s/<name>`. Check the frames with an
    `ncp.Subscriber`: it drops bad frames and reports lost, repeated, and changed messages."""
    return session.declare_subscriber(stream_key(name), lambda sample: on_frame(sample.payload.to_bytes()))


def secure_config(
    *,
    root_ca_certificate: str,
    certificate: str,
    private_key: str,
    listen: Iterable[str] = (),
    connect: Iterable[str] = (),
    mode: str = "peer",
    verify_name_on_connect: bool = True,
) -> zenoh.Config:
    """A Zenoh configuration for networks that are not trusted (rule 9.2.6): TLS links only,
    with a certificate on both sides (mutual TLS), signed by `root_ca_certificate`, and no
    multicast scouting. Endpoints have the form `tls/HOST:PORT`. Add access control to the
    configuration before you open the session; the README shows an example."""
    endpoints = [*listen, *connect]
    if not endpoints or any(not e.startswith("tls/") for e in endpoints):
        raise ValueError("secure_config needs tls/ endpoints only")
    config = zenoh.Config()
    config.insert_json5("mode", json.dumps(mode))
    config.insert_json5("scouting/multicast/enabled", "false")
    config.insert_json5("listen/endpoints", json.dumps(list(listen)))
    config.insert_json5("connect/endpoints", json.dumps(list(connect)))
    tls = {
        "root_ca_certificate": root_ca_certificate,
        "listen_certificate": certificate,
        "listen_private_key": private_key,
        "connect_certificate": certificate,
        "connect_private_key": private_key,
        "enable_mtls": True,
        "verify_name_on_connect": verify_name_on_connect,
    }
    for name, value in tls.items():
        config.insert_json5(f"transport/link/tls/{name}", json.dumps(value))
    return config
