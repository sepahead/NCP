"""The Zenoh binding of NCP 2 (specification, section 9.2), for Python.

Exchanges travel as Zenoh queries and replies, streams as Zenoh publications. This package is
optional: it needs `eclipse-zenoh`, and the NCP 2 core package `ncp` never imports it.

- An owner serves on the key `ncp/x/<service>` (`Server`, `serve`). A client sends each request
  frame as the payload of a query to that key (`ZenohChannel`), and the owner replies with the
  response frame (rule 9.2.1).
- A publisher puts stream frames on `ncp/s/<stream-key>` (`stream_sender`), and subscribers
  subscribe to that key (`subscribe`) (rule 9.2.2).
- A receiver drops a bad frame (rule 9.2.3).
- The client accepts only the reply that matches its request; when no reply arrives in time, it
  sends the same request frame again (rule 9.2.4). `ncp.Client` does this for a channel whose
  `lossy` is true, and the owner answers a repeated request with its kept response (rule 7.3.5),
  so the request still runs at most once.
- Each owner uses its own service key (rule 9.2.5).
- On networks that are not trusted, the Zenoh sessions MUST use TLS with client certificates and
  Zenoh access control on both sides (rule 9.2.6). `secure_config` writes the TLS part of such a
  configuration; the README shows the access control.
- The server keeps one owner for each session and runs each session in its own thread, so a long
  step of one session does not delay the others (rules 9.2.7 and 9.2.8). It forgets a session
  after a time without requests, and it stops as rule 9.2.9 says.
- The server checks the digest of each frame, or its authentication code with the server's key
  (section 13.2), before it reads the message (section 3, rule 5). A frame of a session that the
  server does not hold has the handshake bound.
"""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

import ncp
import zenoh
from ncp import events as E
from ncp import frame as F
from ncp.messages import check_request, foreign
from ncp.transcript import RECEIVED, SENT, Tap

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "EXCHANGE_PREFIX",
    "STREAM_PREFIX",
    "Server",
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
    local = False

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

    def close(self) -> None:
        pass




class _Worker:
    """One session: its owner, the queries that wait for it, and its thread."""

    def __init__(self, server: Server, session: str, owner: ncp.Owner) -> None:
        self.server, self.session, self.owner = server, session, owner
        self.queries: queue.SimpleQueue[tuple[zenoh.Query, F.Decoded] | None] = queue.SimpleQueue()
        self.lock = threading.Lock()  # one step of the owner at a time; stop() waits for it
        self.waiting = 0  # queries queued or in progress; guarded by the server's lock
        self.last = time.monotonic()  # the time of the last response; guarded by the server's lock
        self.thread = threading.Thread(target=self._run, name=f"ncp-zenoh {session[:8]}", daemon=True)

    def _run(self) -> None:
        server = self.server
        while True:
            item = self.queries.get()
            if item is None:
                break
            query, decoded = item
            response = None
            try:
                with self.lock:
                    # The server checked the frame with the largest bound of its sessions; a frame
                    # above this session's bound is a bad frame (rule 9.2.3).
                    if len(decoded.frame) <= self.owner.bound:
                        response = self.owner.handle_decoded(decoded)
                    bound = self.owner.bound
            except F.FrameError:
                response, bound = None, F.HANDSHAKE_BOUND  # rule 9.2.3: a bad frame gets no reply
            except Exception as error:  # noqa: BLE001 - one query must not stop the session
                bound = F.HANDSHAKE_BOUND
                server.observer.event(E.Event("server_error", "server", self.session, detail="query dropped", error=error))
            with server.lock:
                # Before the reply: a client can send a frame of the new session bound as soon as
                # it has the `open` response.
                server.largest = max(server.largest, bound)
            server._reply(query, response)
            with server.lock:
                self.waiting -= 1
                self.last = time.monotonic()
                if self.owner.session is None and self.waiting == 0:
                    server._forget(self)  # the open was not accepted: there is no session to keep


class Server:
    """An owner service on `ncp/x/<service>`: one `ncp.Owner` for each session.

    `make_owner` returns a new owner for each new session. Each session runs in its own thread, so
    a long step of one session does not delay the others (rule 9.2.8). A session without a request
    for `expire_after_s` seconds, counted from the last response, is forgotten; a session with a
    request in progress is never forgotten. A request with `seq` greater than 0 of a session that
    the server does not hold, because it forgot the session or restarted, gets `ended` with
    `session_expired`: possibly executed (rule 9.2.7). Above `max_sessions` sessions, an `open`
    gets `rejected` with `refused`.

    `key` authenticates every frame (section 13.2): the server checks the authentication code of
    each request before it reads the message, and authenticates the responses that it makes
    itself. Each owner that `make_owner` returns must have the same key, or none if the server has
    none; the server drops an `open` for an owner with another key.

    `start()` declares the service; `stop(grace)` stops it as rule 9.2.9 says. Use it as a
    context manager to do both.
    """

    def __init__(
        self,
        session: zenoh.Session,
        service: str,
        make_owner: Callable[[], ncp.Owner],
        *,
        expire_after_s: float = 600.0,
        max_sessions: int = 4096,
        observer: Any = None,
        key: bytes | None = None,
    ) -> None:
        if expire_after_s <= 0 or max_sessions < 1:
            raise ValueError("expire_after_s must be positive and max_sessions at least 1")
        self.zenoh_session, self.key, self.make_owner = session, exchange_key(service), make_owner
        self.frame_key = F.check_key(key)
        # The largest bound of a session that the server holds or held: the bound for the first
        # check of a frame, before the server knows its session.
        self.largest = F.HANDSHAKE_BOUND
        self.expire_after_s, self.max_sessions = expire_after_s, max_sessions
        self.observer = observer if observer is not None else E.DEFAULT
        self.lock = threading.Lock()
        self.workers: dict[str, _Worker] = {}
        self.stopping = False
        self._queryable: Any = None
        self._done = threading.Event()
        self._janitor = threading.Thread(target=self._expire, name="ncp-zenoh expiry", daemon=True)

    @property
    def sessions(self) -> int:
        """The number of sessions whose state the server keeps."""
        with self.lock:
            return len(self.workers)

    def start(self) -> Server:
        self._queryable = self.zenoh_session.declare_queryable(self.key, self._on_query, complete=True)
        self._janitor.start()
        return self

    def __enter__(self) -> Server:
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()

    def _reply(self, query: zenoh.Query, response: bytes | None) -> None:
        try:
            if response is not None:
                query.reply(self.key, response)
            query.drop()  # the query is complete: the client stops waiting for more replies
        except Exception:  # noqa: BLE001 - the client may have gone; the query then has no reader
            pass

    def _forget(self, worker: _Worker) -> bool:
        """Remove a session and end its thread. Needs the lock. The caller then calls `_finish`
        without the lock: it runs application code."""
        if self.workers.get(worker.session) is not worker:
            return False
        del self.workers[worker.session]
        worker.queries.put(None)
        return True

    def _finish(self, worker: _Worker, reason: str) -> None:
        """Tell the application, once, that the session ended."""
        try:
            with worker.lock:
                worker.owner.finish(reason)
        except Exception as error:  # noqa: BLE001 - the session is over anyway
            self.observer.event(E.Event("server_error", "server", worker.session, detail="close failed", error=error))

    def _answer(self, decoded: F.Decoded, outcome: str, code: str) -> bytes:
        """A response that the server makes itself, without an owner of the session, with the
        server's key. A request of another protocol version gets `wrong_protocol` (rule 7.3.2)."""
        request = decoded.message
        if request["ncp"] != ncp.PROTOCOL:
            outcome, code = "rejected", "wrong_protocol"
        message = {
            "ncp": ncp.PROTOCOL,
            "session": request["session"],
            "seq": request["seq"],
            "request": decoded.identity,
            "outcome": outcome,
            "code": code,
            "body": {},
        }
        return F.encode(message, key=self.frame_key)

    def _on_query(self, query: zenoh.Query) -> None:
        """Route one query to its session's thread, or answer it here (rules 7.3.2, 7.3.3, and
        9.2.7). Runs in a thread of Zenoh, so it never waits for an owner.

        The server checks the digest, or the authentication code with its key, before it reads
        the message (section 3, rule 5), with the largest bound of its sessions; a frame of a
        session that it does not hold has the handshake bound."""
        payload = query.payload
        frame = b"" if payload is None else payload.to_bytes()
        with self.lock:
            limit = self.largest
        try:
            decoded = F.decode(frame, limit, key=self.frame_key)
            message = decoded.message
            other = foreign(message)
            if not other:
                check_request(message)
        except F.FrameError:
            self._reply(query, None)  # rule 9.2.3
            return
        session, op, seq = message["session"], message.get("op"), message["seq"]
        small = len(frame) <= F.HANDSHAKE_BOUND
        with self.lock:
            worker = self.workers.get(session)
            opens = op == "open" and seq == 0 and not other and small
            if worker is None and opens and not self.stopping and len(self.workers) < self.max_sessions:
                try:
                    owner = self.make_owner()
                    if owner.config.key != self.frame_key:
                        raise ValueError("the owner's key is not the server's key")
                    worker = _Worker(self, session, owner)
                except Exception as error:  # noqa: BLE001 - a defect of the factory drops the query
                    self.observer.event(E.Event("server_error", "server", session, detail="the owner factory failed", error=error))
                    self._reply(query, None)
                    return
                self.workers[session] = worker
                worker.thread.start()
            if worker is not None:
                worker.waiting += 1
                worker.queries.put((query, decoded))
                return
            stopping, full = self.stopping, len(self.workers) >= self.max_sessions
        if not small:
            response = None  # above the handshake bound of a session that the server does not hold
        elif other or seq > 0:
            # seq > 0: a session that this server does not hold: it forgot it, it restarted, or it
            # never served it. An earlier copy of the request may have executed (rule 9.2.7).
            response = self._answer(decoded, "ended", "session_expired")
        elif op != "open":
            response = self._answer(decoded, "rejected", "not_open")
        elif stopping or full:
            response = self._answer(decoded, "rejected", "refused")
        else:
            response = None
        self._reply(query, response)

    def _expire(self) -> None:
        period = min(1.0, self.expire_after_s / 4)
        while not self._done.wait(period):
            now = time.monotonic()
            with self.lock:
                expired = [
                    worker
                    for worker in list(self.workers.values())
                    if worker.waiting == 0 and now - worker.last >= self.expire_after_s and self._forget(worker)
                ]
            for worker in expired:
                self._finish(worker, "expired")

    def stop(self, grace: float = 1.0) -> None:
        """Stop as rule 9.2.9 says: every owner stops. Rules 7.3.1 to 7.3.9 still apply, so a copy
        of a kept request gets the kept response and the other checks reject as usual; an `open`
        gets `rejected` with `refused`; a request that the owner would otherwise admit gets
        `ended` with `shutdown`, and is never admitted. After `grace` seconds, the server
        undeclares the queryable and ends the threads of the sessions, once they have answered
        their queries."""
        with self.lock:
            if self.stopping:
                return
            self.stopping = True
            workers = list(self.workers.values())
        for worker in workers:
            with worker.lock:  # waits for a step in progress, so the stop is never lost
                worker.owner.stop()
        time.sleep(grace)
        if self._queryable is not None:
            self._queryable.undeclare()
        self._done.set()
        with self.lock:
            workers = [worker for worker in list(self.workers.values()) if self._forget(worker)]
        for worker in workers:
            worker.thread.join(10)
            self._finish(worker, "shutdown")


def serve(
    session: zenoh.Session,
    service: str,
    make_owner: Callable[[], ncp.Owner],
    *,
    stop: threading.Event,
    ready: threading.Event | None = None,
    grace: float = 1.0,
    **options: Any,
) -> None:
    """Serve `ncp/x/<service>` with a `Server` until `stop` is set, then stop as rule 9.2.9 says.
    `ready` is set once the service is declared. `options` go to `Server`."""
    server = Server(session, service, make_owner, **options).start()
    if ready is not None:
        ready.set()
    try:
        stop.wait()
    finally:
        server.stop(grace)


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
    multicast scouting. Endpoints have the form `tls/HOST:PORT`. Add access control on both sides
    before you open the session; the README shows an example."""
    listen, connect = list(listen), list(connect)
    endpoints = [*listen, *connect]
    if not endpoints or any(not e.startswith("tls/") for e in endpoints):
        raise ValueError("secure_config needs tls/ endpoints only")
    config = zenoh.Config()
    config.insert_json5("mode", json.dumps(mode))
    config.insert_json5("scouting/multicast/enabled", "false")
    config.insert_json5("listen/endpoints", json.dumps(listen))
    config.insert_json5("connect/endpoints", json.dumps(connect))
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
