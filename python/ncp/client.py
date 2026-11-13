"""The client (specification section 7.6).

The client rules live in one state machine of pure functions over an immutable `ClientState`:
`request` makes the next request frame, `receive` applies a frame from the owner, `time_out` and
`closed` apply the two local events. Each returns the new state and, when the call is over, its
verdict: a `Result`, or a `Declined`, `Rejected`, or `Ended` error. `Client` drives the machine
over a channel; tests, the model check, and other drivers use the same functions.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from . import events as E
from . import frame as F
from .contract import Contract
from .frame import FrameError
from .messages import (
    LOCAL_CODES,
    PROTOCOL,
    CallError,
    Executed,
    check_response,
    executed,
    is_name,
    is_nonce,
    is_session,
)
from .owner import Declined

__all__ = [
    "ClientState",
    "Client",
    "Ended",
    "Pending",
    "Rejected",
    "Result",
    "UsageError",
    "closed",
    "new_state",
    "receive",
    "request",
    "time_out",
]


class Rejected(CallError):
    """The owner did not admit the `open` request: no session is open (outcome `rejected`).

    A client gets it only in reply to `open`. A rejection of any other request ends the session
    with `Ended` and the request possibly executed (rule 7.6.4): the owner lost the session, and a
    delayed copy of `open` opened it again, so an earlier copy of the request may have executed."""

    def __init__(self, code: str, body: Any) -> None:
        super().__init__(code)
        self.code, self.body = code, body

    @property
    def detail(self) -> str:
        return self.body.get("detail", "") if type(self.body) is dict else ""


class Ended(CallError):
    """The session ended. `executed` says whether the last request executed: YES, NO, or UNKNOWN
    (spec section 7.7, property 7). `code` is the owner's code, or a local code: `local.timeout`,
    `local.closed`, `local.protocol`, or `local.bad_frame`. `request` is the identity of the
    request that `executed` is about, or None if no request was outstanding."""

    def __init__(
        self, code: str, executed: Executed, body: Any = None, detail: str = "", request: str | None = None
    ) -> None:
        super().__init__(f"{code} (executed: {executed.value})" + (f": {detail}" if detail else ""))
        self.code, self.executed, self.body, self.detail = code, executed, body if body is not None else {}, detail
        self.request = request


class UsageError(ValueError):
    """A call that the client refuses before it sends anything: the request was not sent."""


class Result:
    """The `ok` response to a request: its body with arrays in place, its arrays, its identity,
    the identity of the request that it answers, and the sequence number."""

    __slots__ = ("body", "arrays", "identity", "request", "seq")

    def __init__(self, body: Any, identity: str, arrays: list[F.Array], request: str, seq: int = 0) -> None:
        self.body, self.identity, self.arrays, self.request, self.seq = body, identity, arrays, request, seq

    def __repr__(self) -> str:
        return f"Result(seq={self.seq}, body={self.body!r})"


@dataclass(frozen=True, slots=True)
class Pending:
    """The request that waits for its response: its frame is kept for copies (rule 7.6.1)."""

    seq: int
    op: str
    frame: bytes = field(repr=False)
    identity: str
    sends: int = 1


@dataclass(frozen=True, slots=True)
class ClientState:
    """The state of a client of one session."""

    session: str
    application: str
    contract: str
    requested_bound: int = F.DEFAULT_BOUND
    bound: int = F.HANDSHAKE_BOUND
    seq: int = 0
    ack: str | None = None
    pending: Pending | None = None
    opened: bool = False
    ended: bool = False


def new_state(contract: Contract, *, session: str | None = None, bound: int = F.DEFAULT_BOUND) -> ClientState:
    """The state of a new client of `contract`."""
    if not F.HANDSHAKE_BOUND <= bound <= F.MAX_BOUND:
        raise ValueError(f"bound must be from {F.HANDSHAKE_BOUND} to {F.MAX_BOUND}")
    return ClientState(session or str(uuid.uuid4()), contract.application, contract.identity, bound)


def request(
    state: ClientState,
    op: str,
    body: Any = None,
    *,
    key: bytes | None = None,
    run: str | None = None,
    features: dict[str, Any] | None = None,
) -> tuple[ClientState, bytes]:
    """The frame of the next request and the state that waits for its response.

    `op` "open" makes the `open` request (section 7.1); `body` is then ignored. Raise UsageError,
    with nothing sent, for a request that the rules forbid now.
    """
    if state.ended:
        raise UsageError("the session has ended")
    if state.pending is not None:
        raise UsageError("a request is outstanding: one request at a time (rule 7.6.1)")
    if op == "open":
        if state.opened:
            raise UsageError("the session is open")
        open_body: dict[str, Any] = {
            "application": state.application,
            "contract": state.contract,
            "bound": state.requested_bound,
        }
        if run is not None:
            open_body["run"] = run
        if features:
            open_body["features"] = features
        seq, ack, body = 0, None, open_body
    else:
        if not state.opened:
            raise UsageError("call before open")
        if not is_name(op):
            raise UsageError(f"{op!r} is not an operation name")
        seq, ack = state.seq + 1, state.ack
    try:
        frame = F.encode(
            {"ncp": PROTOCOL, "session": state.session, "seq": seq, "op": op, "ack": ack, "body": body}, key=key
        )
    except FrameError as error:
        raise UsageError(f"the request cannot be sent: {error}") from error
    if len(frame) > state.bound:
        raise UsageError(f"a request of {len(frame)} bytes exceeds the session bound {state.bound}")
    return replace(state, pending=Pending(seq, op, frame, F.identity(frame))), frame


LOST_SESSION = "the owner rejected a request other than open: it holds another opening of the session (rule 7.6.4)"


def _bound(state: ClientState, body: Any) -> bool:
    """Whether a nameless response is bound to the chain of the outstanding request (rule 7.6.2):
    it names the client's session and the kept response that the request acknowledges. Only then
    did the request not execute; a nameless frame can be replayed from another connection, also
    when frames are authenticated."""
    return (
        state.ack is not None
        and type(body) is dict
        and body.get("session") == state.session
        and body.get("kept") == state.ack
    )


def _end(state: ClientState, code: str, verdict: Executed, body: Any = None, text: str = "") -> tuple[
    ClientState, Ended
]:
    request = state.pending.identity if state.pending is not None else None
    return replace(state, pending=None, ended=True), Ended(code, verdict, body, text, request)


def receive(
    state: ClientState,
    frame: bytes | bytearray | memoryview,
    *,
    lossy: bool,
    key: bytes | None = None,
    check_digest: bool = True,
) -> tuple[ClientState, Result | CallError | None]:
    """Apply one frame from the owner (rules 7.6.2 to 7.6.5).

    Return the new state and the verdict of the outstanding request, or None if the frame does
    not end the call: it belongs to no outstanding request, and the binding is lossy.
    """
    pending = state.pending
    if pending is None:
        return state, None
    try:
        decoded = F.decode(frame, state.bound, check_digest=check_digest, key=key)
        message = decoded.message
        check_response(message)
    except FrameError as error:
        if lossy:
            return state, None
        return _end(state, "local.bad_frame", Executed.UNKNOWN, text=str(error))
    if message["session"] is None:  # a response that names no request (section 6.2)
        if lossy:
            return state, None  # rule 7.6.2: only the byte-stream binding sends it
        code, body = message["code"], message["body"]
        verdict = Executed.NO if code in ("bad_frame", "shutdown") and _bound(state, body) else Executed.UNKNOWN
        return _end(state, code, verdict, body)
    if not (
        message["ncp"] == PROTOCOL
        and message["session"] == state.session
        and message["seq"] == pending.seq
        and message["request"] == pending.identity
    ):
        if lossy:
            return state, None
        return _end(state, "local.protocol", Executed.UNKNOWN, text="a frame that does not belong to the request")
    outcome, code, body = message["outcome"], message["code"], message["body"]
    if outcome == "ok":
        if pending.op == "open":
            if (
                type(body) is not dict
                or type(body.get("bound")) is not int
                or not F.HANDSHAKE_BOUND <= body["bound"] <= state.requested_bound
                or not is_nonce(body.get("nonce"))
                or type(body.get("features", {})) is not dict
            ):
                return _end(state, "local.protocol", Executed.UNKNOWN, body, "the open response breaks section 7.1")
            new = replace(state, pending=None, opened=True, bound=body["bound"], seq=0, ack=decoded.identity)
        else:
            new = replace(state, pending=None, seq=pending.seq, ack=decoded.identity, ended=pending.op == "close")
        return new, Result(body, decoded.identity, decoded.arrays, message["request"], pending.seq)
    if outcome == "declined":
        new = replace(state, pending=None, seq=pending.seq, ack=decoded.identity)
        text = body.get("detail", "") if type(body.get("detail")) is str else ""
        return new, Declined(text, code=code, body=body)
    if outcome == "rejected":
        if pending.op == "open":
            return replace(state, pending=None), Rejected(code, body)
        return _end(state, code, Executed.UNKNOWN, body, LOST_SESSION)
    return _end(state, code, executed(code), body, body.get("detail", "") if type(body.get("detail")) is str else "")


def time_out(state: ClientState, *, lossy: bool, retries: int) -> tuple[ClientState, bytes | Ended | None]:
    """No response arrived in time. On a lossy binding, return the frame to send again while
    copies remain (rule 7.6.6); otherwise end the session, possibly executed (rule 7.6.7)."""
    pending = state.pending
    if pending is None:
        return state, None
    if lossy and pending.sends <= retries:
        return replace(state, pending=replace(pending, sends=pending.sends + 1)), pending.frame
    return _end(state, "local.timeout", Executed.UNKNOWN)


def closed(state: ClientState, text: str = "") -> tuple[ClientState, Ended | None]:
    """The binding closed or failed: the session ends, and an outstanding request is possibly
    executed (rule 7.6.7)."""
    if state.pending is None:
        return replace(state, ended=True), None
    return _end(state, "local.closed", Executed.UNKNOWN, text=text)


assert LOCAL_CODES == {"local.timeout", "local.closed", "local.protocol", "local.bad_frame"}


class Client:
    """A client of one session over one channel (section 7.6).

    `contract` is the application's `Contract`. `timeout` is the time limit for each response, in
    seconds; on a lossy channel, the client then sends the same frame again, at most `retries`
    times. `key` authenticates every frame (section 13.2). `features` asks for features at `open`
    (section 7.1), for example {"ncp.lockstep": {}}.

    Use it as a context manager to open and close the session:

        with ncp.Client(ncp.spawn(["./world"]), contract) as world:
            result = world.call("step", {"dt_ms": 1})
    """

    def __init__(
        self,
        channel: Any,
        contract: Contract,
        *,
        bound: int = F.DEFAULT_BOUND,
        run: str | None = None,
        features: dict[str, Any] | None = None,
        timeout: float | None = None,
        retries: int = 3,
        check_digests: bool = True,
        key: bytes | None = None,
        session: str | None = None,
        observer: Any = None,
    ) -> None:
        if not isinstance(contract, Contract):
            raise TypeError("contract must be an ncp.Contract")
        if key is not None and not check_digests:
            raise ValueError("an authenticated session always compares digests (section 13.2)")
        if session is not None and not is_session(session):
            raise ValueError("session must be a lowercase version 4 UUID")
        self.channel, self.contract = channel, contract
        self.state = new_state(contract, session=session, bound=bound)
        self.run, self.features, self.timeout, self.retries = run, features, timeout, retries
        self.check_digests, self.key = check_digests, F.check_key(key)
        self.observer = observer if observer is not None else E.DEFAULT
        self.owner: dict[str, Any] | None = None

    # ------------------------------------------------------------------ properties
    @property
    def session(self) -> str:
        return self.state.session

    @property
    def ended(self) -> bool:
        return self.state.ended

    @property
    def opened(self) -> bool:
        return self.state.opened

    @property
    def bound(self) -> int:
        return self.state.bound

    @property
    def nonce(self) -> str | None:
        return None if self.owner is None else self.owner.get("nonce")

    @property
    def enabled(self) -> dict[str, Any]:
        """The features that the owner enabled (section 7.1)."""
        return {} if self.owner is None else dict(self.owner.get("features", {}))

    # ------------------------------------------------------------------ calls
    def open(self) -> dict[str, Any]:
        """Open the session and return the owner's `open` body."""
        result = self._finish(self._start("open", None))
        self.owner = result.body
        return result.body

    def call(self, op: str, body: Any = None) -> Result:
        """Send one request and return its result. Raise Declined, Rejected, Ended, or UsageError."""
        if op in ("open", "close"):
            raise UsageError("use open() and close()")
        return self._finish(self._start(op, body))

    def ping(self) -> Result:
        """Send `ncp.ping`: the owner answers without calling the application (rule 7.3.12)."""
        return self._finish(self._start("ncp.ping", {}))

    def close(self) -> None:
        """Close the session, then the channel. On a byte stream, one connection carries one
        session (section 9.1)."""
        try:
            if self.state.opened and not self.state.ended and self.state.pending is None:
                self._finish(self._start("close", {}))
        finally:
            self.state = replace(self.state, ended=True, pending=None)
            if not getattr(self.channel, "lossy", False) and hasattr(self.channel, "close"):
                self.channel.close()

    def start(self, op: str, body: Any = None) -> Pending:
        """Send a request without waiting for its response: the first half of `call`, for
        `call_all`. The session has one request outstanding until `finish` reads its response."""
        if op in ("open", "close"):
            raise UsageError("use open() and close()")
        return self._start(op, body)

    def finish(self, pending: Pending) -> Result:
        """Wait for the response to the request that `start` sent: the second half of `call`."""
        if self.state.pending is not pending:
            raise UsageError("finish() takes the request that start() returned, once")
        return self._finish(pending)

    def __enter__(self) -> Client:
        if not self.state.opened:
            self.open()
        return self

    def __exit__(self, kind: Any, error: Any, traceback: Any) -> None:
        if kind is None:
            self.close()
        else:  # leave the session; an outstanding request stays possibly executed
            self.state = replace(self.state, ended=True, pending=None)
            if hasattr(self.channel, "close"):
                self.channel.close()

    # ------------------------------------------------------------------ the driver
    def _event(self, kind: str, op: str | None, outcome: Any = None) -> None:
        code = getattr(outcome, "code", None)
        name = "ok" if isinstance(outcome, Result) else type(outcome).__name__.lower() if outcome else None
        self.observer.event(E.Event(kind, "client", self.state.session, self.state.seq, op, name, code))

    def _start(self, op: str, body: Any) -> Pending:
        self.state, frame = request(self.state, op, body, key=self.key, run=self.run, features=self.features)
        pending = self.state.pending
        assert pending is not None
        self._send(frame)
        return pending

    def _send(self, frame: bytes) -> None:
        try:
            self.channel.send(frame)
        except OSError as error:
            # The binding failed: no response can arrive, and the request is possibly executed.
            self.state, verdict = closed(self.state, str(error))
            if verdict is not None:
                raise verdict from error
            raise

    def _finish(self, pending: Pending) -> Result:
        lossy = bool(getattr(self.channel, "lossy", False))
        while True:
            try:
                frame = self.channel.receive(self.state.bound, self.timeout)
            except TimeoutError:
                self.state, action = time_out(self.state, lossy=lossy, retries=self.retries)
                if isinstance(action, bytes):
                    self._event("resent", pending.op)
                    self._send(action)
                    continue
                verdict: Result | CallError | None = action
            except FrameError as error:  # a bad header on a byte stream
                if lossy:
                    continue
                self.state, verdict = _end(self.state, "local.bad_frame", Executed.UNKNOWN, text=str(error))
            except (EOFError, OSError) as error:
                self.state, verdict = closed(self.state, str(error))
            else:
                self.state, verdict = receive(
                    self.state, frame, lossy=lossy, key=self.key, check_digest=self.check_digests
                )
                if verdict is None:
                    self._event("ignored", pending.op)
                    continue
            self._event("verdict", pending.op, verdict)
            if isinstance(verdict, Result):
                return verdict
            assert verdict is not None
            raise verdict


def call_all(clients: list[Client], op: str, bodies: list[Any]) -> list[Result | Exception]:
    """Send one request to each session and wait for all responses (spec section 16).

    The requests go out first, one to each session, and the responses are read afterwards, in
    order. The owners therefore work at the same time, without a thread for each session, and
    each session still has one request outstanding at a time (rule 7.6.1). Sessions are
    independent: an exception of one session is returned in its place and does not stop the
    others.
    """
    if len(clients) != len(bodies):
        raise ValueError("one body for each client")
    if len({id(client) for client in clients}) != len(clients):
        raise ValueError("each client at most once")
    started: list[Pending | Exception] = []
    for client, body in zip(clients, bodies, strict=True):
        try:
            started.append(client.start(op, body))
        except Exception as error:  # noqa: BLE001 - returned in its place
            started.append(error)
    results: list[Result | Exception] = []
    for client, pending in zip(clients, started, strict=True):
        if isinstance(pending, Exception):
            results.append(pending)
            continue
        try:
            results.append(client.finish(pending))
        except Exception as error:  # noqa: BLE001 - returned in its place
            results.append(error)
    return results
