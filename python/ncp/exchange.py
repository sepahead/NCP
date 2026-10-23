"""Exchange sessions: messages, the owner state machine, and the client (sections 6 and 7)."""
from __future__ import annotations

import re
import uuid
from typing import Any, Callable, Iterable, Protocol

from . import frame as F
from .frame import FrameError

PROTOCOL = 2
IMPLEMENTATION = "ncp-python/2.0.0a1"
_SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_OPERATION = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_IDENTITY = re.compile(r"[0-9a-f]{64}\Z")
_REQUEST_MEMBERS = frozenset({"ncp", "session", "seq", "op", "ack", "body"})
_RESPONSE_MEMBERS = frozenset({"ncp", "session", "seq", "request", "outcome", "code", "body"})
OUTCOMES = ("ok", "rejected", "ended")
REJECTION_CODES = frozenset({
    "wrong_protocol", "not_open", "already_open", "wrong_session", "seq_stale", "seq_gap",
    "seq_conflict", "ack_missing", "ack_mismatch", "unknown_op", "body_invalid",
    "contract_mismatch", "bound_unacceptable", "session_ended",
})
ENDING_CODES = frozenset({"result_too_large", "owner_failure", "bad_frame", "shutdown"})
EXECUTED = {"result_too_large": "yes", "owner_failure": "unknown", "bad_frame": "no", "shutdown": "no"}


class BodyInvalid(Exception):
    """Raised by a handler's validate step: reject the request without any state change."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail[:256]


class Handler(Protocol):
    """The application side of an owner."""

    def validate(self, op: str, body: Any) -> None:
        """Raise BodyInvalid if the body is invalid. Must not change any state."""

    def execute(self, op: str, body: Any) -> Any:
        """Execute one request and return its result. An exception ends the session."""


def is_identity(value: Any) -> bool:
    return type(value) is str and _IDENTITY.match(value) is not None


def check_request(message: dict[str, Any]) -> None:
    """Raise FrameError unless the message has the request form of section 6.1."""
    keys = message.keys() - {"att"}
    if keys != _REQUEST_MEMBERS:
        raise FrameError("request members")
    session, seq, op, ack = message["session"], message["seq"], message["op"], message["ack"]
    if (type(message["ncp"]) is not int or type(session) is not str or _SESSION.match(session) is None
            or type(seq) is not int or seq < 0 or type(op) is not str or _OPERATION.match(op) is None
            or not (ack is None or is_identity(ack))):
        raise FrameError("request member types")


def check_response(message: dict[str, Any]) -> None:
    """Raise FrameError unless the message has the response form of section 6.2."""
    if message.keys() - {"att"} != _RESPONSE_MEMBERS:
        raise FrameError("response members")
    outcome, code = message["outcome"], message["code"]
    if type(message["ncp"]) is not int or outcome not in OUTCOMES:
        raise FrameError("response member types")
    if outcome == "ok":
        valid = (code is None and type(message["session"]) is str and type(message["seq"]) is int
                 and is_identity(message["request"]))
    elif outcome == "rejected":
        valid = code in REJECTION_CODES and type(message["seq"]) is int and is_identity(message["request"])
    else:
        valid = code in ENDING_CODES and (
            (message["session"] is None and message["seq"] is None and message["request"] is None)
            or (type(message["seq"]) is int and is_identity(message["request"])))
    if not valid:
        raise FrameError("response member types")


class Owner:
    """The owner state machine of section 7.3. One instance serves one session.

    `handle` takes one frame and returns the response frame. It never raises for a bad
    request; it raises FrameError only for a bad frame, which the binding handles.

    `check_digests=False` stops the comparison of each request's digest with its bytes. Use it
    only on a pipe pair or a Unix domain socket with no other program between the endpoints
    (spec section 3, rule 4). The response digests are always computed.
    """

    def __init__(self, application: str, contract: str, handler: Handler, operations: Iterable[str], *,
                 max_bound: int = F.DEFAULT_BOUND, implementation: str = IMPLEMENTATION,
                 check_digests: bool = True) -> None:
        if not is_identity(contract):
            raise ValueError("contract must be an identity")
        if not F.HANDSHAKE_BOUND <= max_bound <= F.MAX_BOUND:
            raise ValueError("max_bound")
        self.application, self.contract, self.handler = application, contract, handler
        self.operations = frozenset(operations) - {"open", "close"}
        self.max_bound, self.implementation = max_bound, implementation
        self.check_digests = check_digests
        self.session: str | None = None
        self.bound = F.HANDSHAKE_BOUND
        self.high = 0
        self.kept: tuple[str, bytes, str] | None = None  # (request identity, response frame, response identity)
        self.ended = False
        self.closed = False

    def handle(self, frame_bytes: bytes | bytearray | memoryview) -> bytes:
        """Handle one request frame and return the response frame."""
        decoded = F.decode(frame_bytes, self.bound, check_digest=self.check_digests)
        request = decoded.message
        check_request(request)
        request_id = decoded.identity
        session, seq, op = request["session"], request["seq"], request["op"]

        def reply(outcome: str, code: str | None, body: Any) -> bytes:
            return F.encode({"ncp": PROTOCOL, "session": session, "seq": seq, "request": request_id,
                             "outcome": outcome, "code": code, "body": body})

        def reject(code: str, detail: str | None = None) -> bytes:
            return reply("rejected", code, {"detail": detail} if detail else {})

        if request["ncp"] != PROTOCOL:
            return reject("wrong_protocol")
        if self.session is None:
            if op != "open" or seq != 0:
                return reject("not_open")
            return self._open(request, request_id, reply, reject)
        if session != self.session:
            return reject("wrong_session")
        if self.kept is not None and seq == self.high:
            if request_id == self.kept[0]:
                return self.kept[1]
            return reject("seq_conflict")
        if seq <= self.high:
            return reject("seq_stale")
        if seq > self.high + 1:
            return reject("seq_gap")
        if self.ended:
            return reject("session_ended")
        ack = request["ack"]
        if ack is None:
            return reject("ack_missing")
        if self.kept is None or ack != self.kept[2]:
            return reject("ack_mismatch")
        if op == "open":
            return reject("already_open")
        if op != "close":
            if op not in self.operations:
                return reject("unknown_op")
            try:
                self.handler.validate(op, request["body"])
            except BodyInvalid as error:
                return reject("body_invalid", error.detail or None)
        self.kept = None
        self.high = seq
        if op == "close":
            response = reply("ok", None, {})
            self.ended = self.closed = True
        else:
            try:
                result = self.handler.execute(op, request["body"])
            except Exception:  # noqa: BLE001 - any application failure ends the session
                response = reply("ended", "owner_failure", {})
                self.ended = True
            else:
                try:
                    response = reply("ok", None, result)
                except FrameError as error:
                    response = reply("ended", "owner_failure", {"detail": str(error)[:256]})
                    self.ended = True
                else:
                    if len(response) > self.bound:
                        size = len(response)
                        response = reply("ended", "result_too_large", {"size": size, "bound": self.bound})
                        self.ended = True
        self.kept = (request_id, response, F.identity(response))
        return response

    def _open(self, request: dict[str, Any], request_id: str, reply: Callable[..., bytes],
              reject: Callable[..., bytes]) -> bytes:
        body = request["body"]
        if request["ack"] is not None or type(body) is not dict:
            return reject("body_invalid", "open body")
        if not body.keys() >= {"application", "contract", "bound"} or not body.keys() <= {
                "application", "contract", "bound", "run"}:
            return reject("body_invalid", "open members")
        bound, run = body["bound"], body.get("run")
        if (type(body["application"]) is not str or not is_identity(body["contract"]) or type(bound) is not int
                or not (run is None or (type(run) is str and len(run) <= 256))):
            return reject("body_invalid", "open member types")
        if body["application"] != self.application or body["contract"] != self.contract:
            return reject("contract_mismatch")
        if not F.HANDSHAKE_BOUND <= bound <= F.MAX_BOUND:
            return reject("bound_unacceptable")
        effective = min(bound, self.max_bound)
        response = reply("ok", None, {"bound": effective, "application": self.application,
                                      "contract": self.contract, "implementation": self.implementation})
        self.session, self.bound, self.high = request["session"], effective, 0
        self.kept = (request_id, response, F.identity(response))
        return response


def bad_frame_response() -> bytes:
    """The response a byte-stream owner sends for a bad frame before it closes (section 9.1)."""
    return F.encode({"ncp": PROTOCOL, "session": None, "seq": None, "request": None, "outcome": "ended",
                     "code": "bad_frame", "body": {}})


class Rejected(Exception):
    """The owner did not execute the request and changed no state."""

    def __init__(self, code: str, body: Any) -> None:
        super().__init__(code)
        self.code, self.body = code, body


class Ended(Exception):
    """The session ended. `executed` is "yes", "no", or "unknown" for the last request."""

    def __init__(self, code: str, executed: str, body: Any = None) -> None:
        super().__init__(f"{code} (executed: {executed})")
        self.code, self.executed, self.body = code, executed, body


class ProtocolError(Exception):
    """The peer broke the protocol. The session cannot continue."""


class Channel(Protocol):
    """A binding as seen by a client: one frame out, one frame in."""

    lossy: bool

    def send(self, frame: bytes) -> None: ...

    def receive(self, bound: int, timeout: float | None) -> bytes: ...


class Result:
    """The body of an ok response, with its arrays in place, and the response identity."""

    __slots__ = ("body", "identity", "arrays")

    def __init__(self, body: Any, identity: str, arrays: list[F.Array]) -> None:
        self.body, self.identity, self.arrays = body, identity, arrays


class Client:
    """The client rules of section 7.6, over one channel.

    `check_digests=False` stops the comparison of each response's digest with its bytes, under
    the same conditions as for the owner (spec section 3, rule 4).
    """

    def __init__(self, channel: Channel, *, application: str, contract: str, bound: int = F.DEFAULT_BOUND,
                 run: str | None = None, timeout: float | None = None, retries: int = 3,
                 check_digests: bool = True) -> None:
        if not is_identity(contract):
            raise ValueError("contract must be an identity")
        self.channel, self.application, self.contract = channel, application, contract
        self.requested_bound, self.run, self.timeout, self.retries = bound, run, timeout, retries
        self.check_digests = check_digests
        self.session = str(uuid.uuid4())
        self.bound = F.HANDSHAKE_BOUND
        self.seq = 0
        self.ack: str | None = None
        self.ended = False
        self.owner: dict[str, Any] | None = None

    def open(self) -> dict[str, Any]:
        body: dict[str, Any] = {"application": self.application, "contract": self.contract,
                                "bound": self.requested_bound}
        if self.run is not None:
            body["run"] = self.run
        result = self._exchange(0, "open", body)
        info = result.body
        if (type(info) is not dict or type(info.get("bound")) is not int
                or not F.HANDSHAKE_BOUND <= info["bound"] <= self.requested_bound):
            raise ProtocolError("open response")
        self.bound = info["bound"]
        self.owner = info
        return info

    def call(self, op: str, body: Any = None) -> Result:
        """Send one request and return its result. Raise Rejected, Ended, or ProtocolError."""
        if self.owner is None:
            raise ProtocolError("call before open")
        if op in ("open", "close"):
            raise ValueError("use open() and close()")
        return self._exchange(self.seq + 1, op, body)

    def close(self) -> None:
        """Close the session. On a byte-stream binding, also close the channel: one connection
        carries one session (section 9.1)."""
        try:
            if not self.ended and self.owner is not None:
                self._exchange(self.seq + 1, "close", {})
        finally:
            self.ended = True
            if not self.channel.lossy and hasattr(self.channel, "close"):
                self.channel.close()

    def _exchange(self, seq: int, op: str, body: Any) -> Result:
        if self.ended:
            raise ProtocolError("session ended")
        request = F.encode({"ncp": PROTOCOL, "session": self.session, "seq": seq, "op": op,
                            "ack": self.ack, "body": body})
        if len(request) > self.bound:
            raise ValueError(f"request of {len(request)} bytes exceeds the bound {self.bound}")
        request_id = F.identity(request)
        attempts = self.retries + 1 if self.channel.lossy else 1
        for attempt in range(attempts):
            self.channel.send(request)
            try:
                decoded = self._receive_match(seq, request_id)
            except TimeoutError:
                if attempt + 1 < attempts:
                    continue
                self.ended = True
                raise Ended("timeout", "unknown") from None
            message = decoded.message
            outcome = message["outcome"]
            if outcome == "ok":
                self.seq, self.ack = seq, decoded.identity
                if op == "close":
                    self.ended = True
                return Result(message["body"], decoded.identity, decoded.arrays)
            if outcome == "rejected":
                raise Rejected(message["code"], message["body"])
            self.ended = True
            raise Ended(message["code"], EXECUTED[message["code"]], message["body"])
        raise AssertionError("unreachable")

    def _receive_match(self, seq: int, request_id: str) -> F.Decoded:
        while True:
            frame = self.channel.receive(self.bound, self.timeout)
            try:
                decoded = F.decode(frame, self.bound, check_digest=self.check_digests)
                check_response(decoded.message)
            except FrameError as error:
                if self.channel.lossy:
                    continue
                self.ended = True
                raise ProtocolError(f"bad frame from the owner: {error}") from error
            message = decoded.message
            if message["session"] is None and message["code"] in ("bad_frame", "shutdown"):
                self.ended = True
                raise Ended(message["code"], EXECUTED[message["code"]])
            if (message["session"] == self.session and message["seq"] == seq
                    and message["request"] == request_id and message["ncp"] == PROTOCOL):
                return decoded
            if not self.channel.lossy:
                self.ended = True
                raise ProtocolError("response does not match the request")
