"""The owner (specification sections 7.1 to 7.3).

`step` is the owner state machine: a function from an immutable `OwnerState` and one decoded
request to the new state and the response frame. It calls the application only through the
handler that it is given. The Lean model in formal/ states the same rules, and the gate compares
the two. `Owner` drives `step` for one session and keeps its state.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from . import events as E
from . import frame as F
from .contract import Contract
from .frame import FrameError
from .messages import (
    MAX_FEATURES,
    CallError,
    MAX_RUN,
    PROTOCOL,
    check_request,
    detail,
    is_identity,
    is_name,
)

IMPLEMENTATION = "ncp-python/2.0.0"


class Declined(CallError):
    """A request that the owner admitted and did not execute (outcome `declined`).

    A handler raises it in `validate` to decline a request: `raise ncp.Declined("why")`. The owner
    then responds `declined` with the code `body_invalid` and the detail, and the request never
    executes. A client raises it when its request was declined; `code` and `body` are the owner's.
    """

    def __init__(self, detail: str = "", *, code: str = "body_invalid", body: Any = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.detail, self.code = detail, code
        self.body = body if body is not None else ({"detail": detail} if detail else {})


class Refused(Exception):
    """Raised by a handler's `open` to refuse a session: the owner rejects the `open` with
    the code `refused` (section 7.1, rule 4.4)."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Kept:
    """The response to the last admitted request (section 7.2)."""

    request: str
    response: bytes = field(repr=False)
    identity: str


@dataclass(frozen=True, slots=True)
class OwnerState:
    """The state of an owner for one session (section 7.2), and what it agreed at `open`."""

    session: str | None = None
    bound: int = F.HANDSHAKE_BOUND
    high: int = 0
    kept: Kept | None = None
    ended: bool = False
    closed: bool = False
    stopping: bool = False
    contract: Contract | None = None
    run: str | None = None
    nonce: str | None = None
    features: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass(frozen=True, slots=True)
class OpenInfo:
    """What the client asked for in its `open` request."""

    session: str
    contract: Contract
    run: str | None
    features: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Request:
    """One admitted request, as the handler sees it."""

    op: str
    body: Any
    arrays: list[F.Array]
    seq: int
    session: str
    identity: str
    contract: Contract
    run: str | None
    features: Mapping[str, Any]


class Handler(Protocol):
    """The application side of an owner.

    `validate(request)` raises `Declined` to decline the request. It must not change any state.
    `execute(request)` executes the request and returns its result: a JSON value, with `Array`
    or numpy arrays anywhere in it. Any exception of either method ends the session with
    `owner_failure`.

    Two methods are optional. `open(info)` is called when the owner accepts an `open`; it returns
    the features that it enables, as {name: parameters}, or raises `Refused`. `close(reason)` is
    called once when the session ends: reason "closed", "ended", "lost", "shutdown", or "expired".
    """

    def validate(self, request: Request) -> None: ...

    def execute(self, request: Request) -> Any: ...


@dataclass(frozen=True)
class OwnerConfig:
    """What an owner knows before any session: its contracts, its limits, and its key."""

    contracts: tuple[Contract, ...]
    max_bound: int = F.DEFAULT_BOUND
    implementation: str = IMPLEMENTATION
    key: bytes | None = field(default=None, repr=False)
    check_schemas: bool = True
    nonce: Callable[[], str] = field(default=lambda: secrets.token_hex(16), compare=False)

    def __post_init__(self) -> None:
        if not self.contracts:
            raise ValueError("an owner needs at least one contract")
        if len({c.application for c in self.contracts}) != 1:
            raise ValueError("the contracts of one owner name one application")
        if not F.HANDSHAKE_BOUND <= self.max_bound <= F.MAX_BOUND:
            raise ValueError(f"max_bound must be from {F.HANDSHAKE_BOUND} to {F.MAX_BOUND}")
        F.check_key(self.key)


@dataclass(frozen=True, slots=True)
class Note:
    """What one step did, for observers and for the model check."""

    kind: str
    outcome: str | None = None
    code: str | None = None
    detail: str | None = None
    executed: bool = False  # the application's execute was called
    error: BaseException | None = None


def _features(value: Any) -> bool:
    return (
        type(value) is dict
        and len(value) <= MAX_FEATURES
        and all(is_name(name) and type(params) is dict for name, params in value.items())
    )


def step(
    config: OwnerConfig, state: OwnerState, decoded: F.Decoded, handler: Any
) -> tuple[OwnerState, bytes, Note]:
    """Apply rules 7.3.2 to 7.3.13 to one decoded frame.

    Raise FrameError if the frame is not a request (rule 7.3.1: the binding's bad-frame rule).
    Otherwise return the new state, the response frame, and a note of what happened.
    """
    request = decoded.message
    check_request(request)
    request_id = decoded.identity
    session, seq, op = request["session"], request["seq"], request["op"]
    key = config.key

    def reply(outcome: str, code: str | None, body: Any, limit: int | None = None) -> bytes:
        message = {
            "ncp": PROTOCOL,
            "session": session,
            "seq": seq,
            "request": request_id,
            "outcome": outcome,
            "code": code,
            "body": body,
        }
        return F.encode(message, key=key, limit=limit)

    def reject(code: str, text: str = "") -> tuple[OwnerState, bytes, Note]:
        body = {"detail": detail(text)} if text else {}
        return state, reply("rejected", code, body), Note("rejected", "rejected", code, text or None)

    if request["ncp"] != PROTOCOL:
        return reject("wrong_protocol")
    if state.session is None:
        if seq == 0 and op == "open":
            return _open(config, state, request, request_id, reply, reject, handler)
        if seq == 0:
            return reject("not_open")
        return state, reply("ended", "session_expired", {}), Note("expired", "ended", "session_expired")
    if session != state.session:
        return reject("wrong_session")
    kept = state.kept
    if kept is not None and seq == state.high:
        if request_id == kept.request:
            return state, kept.response, Note("repeated")
        return reject("seq_conflict")
    if seq <= state.high:
        return reject("seq_stale")
    if seq > state.high + 1:
        return reject("seq_gap")
    if state.ended:
        return reject("session_ended")
    ack = request["ack"]
    if ack is None:
        return reject("ack_missing")
    if kept is None or ack != kept.identity:
        return reject("ack_mismatch")
    if op == "open":
        return reject("already_open")
    if state.stopping:
        return state, reply("ended", "shutdown", {}), Note("shutdown", "ended", "shutdown")
    # Rule 11: the request is admitted. Every response from here on is kept.
    note: Note
    ends = False
    if op == "close":
        response, note, ends = reply("ok", None, {}), Note("admitted", "ok"), True
    elif op == "ncp.ping":
        response, note = reply("ok", None, {}), Note("admitted", "ok")
    else:
        response, note = _call(config, state, decoded, op, reply, handler)
        ends = note.outcome == "ended"
    new_state = replace(
        state,
        high=seq,
        kept=Kept(request_id, response, F.identity(response)),
        ended=ends,
        closed=op == "close",
    )
    return new_state, response, note


def _call(
    config: OwnerConfig, state: OwnerState, decoded: F.Decoded, op: str, reply: Any, handler: Any
) -> tuple[bytes, Note]:
    """Rule 12 for an operation of the application."""
    message = decoded.message
    contract = state.contract
    assert contract is not None
    if op not in contract.operations:
        return reply("declined", "unknown_op", {}), Note("admitted", "declined", "unknown_op")
    body = message["body"]
    if config.check_schemas:
        mismatch = contract.check_request(op, body)
        if mismatch is not None:
            text = detail(f"request schema: {mismatch}")
            return reply("declined", "body_invalid", {"detail": text}), Note("admitted", "declined", "body_invalid", text)
    request = Request(
        op,
        body,
        decoded.arrays,
        message["seq"],
        message["session"],
        decoded.identity,
        contract,
        state.run,
        state.features,
    )
    try:
        handler.validate(request)
    except Declined as declined:
        text = detail(declined.detail)
        body_out = {"detail": text} if text else {}
        return reply("declined", "body_invalid", body_out), Note("admitted", "declined", "body_invalid", text or None)
    except Exception as error:  # noqa: BLE001 - a failure while checking ends the session (rule 12)
        return reply("ended", "owner_failure", {}), Note(
            "application_error", "ended", "owner_failure", "the application failed while it checked the body", error=error
        )
    try:
        result = handler.execute(request)
    except Exception as error:  # noqa: BLE001 - any application failure ends the session
        return reply("ended", "owner_failure", {}), Note(
            "application_error", "ended", "owner_failure", "the application failed", True, error
        )
    try:
        return reply("ok", None, result, limit=state.bound), Note("admitted", "ok", executed=True)
    except F.TooLarge as error:
        body_out = {"json": error.size, "limit": error.limit} if error.json else {"size": error.size, "bound": state.bound}
        return reply("ended", "result_too_large", body_out), Note("admitted", "ended", "result_too_large", executed=True)
    except FrameError as error:
        text = detail(f"the result cannot be sent: {error}")
        return reply("ended", "owner_failure", {"detail": text}), Note(
            "application_error", "ended", "owner_failure", text, True, error
        )


def _open(
    config: OwnerConfig,
    state: OwnerState,
    request: dict[str, Any],
    request_id: str,
    reply: Any,
    reject: Any,
    handler: Any,
) -> tuple[OwnerState, bytes, Note]:
    """Section 7.1 for an `open` request while no session is held."""
    plain_reject = reject

    def reject(code: str, text: str = "") -> tuple[OwnerState, bytes, Note]:  # noqa: F811 - a rejected open
        state_, response, note = plain_reject(code, text)
        return state_, response, replace(note, kind="open_rejected")

    body = request["body"]
    if request["ack"] is not None or type(body) is not dict:
        return reject("body_invalid", "open body")
    if not {"application", "contract", "bound"} <= body.keys() <= {"application", "contract", "bound", "run", "features"}:
        return reject("body_invalid", "open members")
    bound, run, features = body["bound"], body.get("run"), body.get("features", {})
    if (
        type(body["application"]) is not str
        or not is_identity(body["contract"])
        or type(bound) is not int
        or not (run is None or (type(run) is str and len(run) <= MAX_RUN))
        or not _features(features)
    ):
        return reject("body_invalid", "open member types")
    contract = next(
        (c for c in config.contracts if c.application == body["application"] and c.identity == body["contract"]),
        None,
    )
    if contract is None:
        return reject("contract_mismatch")
    if not F.HANDSHAKE_BOUND <= bound <= F.MAX_BOUND:
        return reject("bound_unacceptable")
    if state.stopping:
        return reject("refused", "the owner stops")
    enabled: Mapping[str, Any] = {}
    opener = getattr(handler, "open", None)
    if opener is not None:
        try:
            granted = opener(OpenInfo(request["session"], contract, run, features)) or {}
        except Refused as refusal:
            return reject("refused", refusal.detail)
        except Exception as error:  # noqa: BLE001 - the owner cannot open; it says so
            state_, response, _ = reject("refused", "the application failed to open the session")
            return state_, response, Note(
                "application_error", "rejected", "refused", "the application failed to open the session", error=error
            )
        if not isinstance(granted, Mapping):
            return reject("refused", "the application returned features that are not an object")
        # Only features that the client asked for, each with parameters that are an object.
        enabled = {name: dict(params) for name, params in granted.items() if name in features and type(params) is dict}
    nonce = config.nonce()
    effective = min(bound, config.max_bound)
    response = reply(
        "ok",
        None,
        {
            "bound": effective,
            "application": contract.application,
            "contract": contract.identity,
            "implementation": config.implementation,
            "nonce": nonce,
            "features": enabled,
        },
    )
    new_state = OwnerState(
        session=request["session"],
        bound=effective,
        high=0,
        kept=Kept(request_id, response, F.identity(response)),
        contract=contract,
        run=run,
        nonce=nonce,
        features=json.loads(json.dumps(enabled)),
    )
    return new_state, response, Note("opened", "ok")


def refuse(config: OwnerConfig, decoded: F.Decoded, text: str = "") -> bytes:
    """The response of a server that cannot serve one more session: an `open` gets `rejected`
    with `refused`, and any other request of a session that the server does not hold gets the
    response of rule 7.3.3. Raise FrameError for a frame that is not a request."""

    class _Refusing:
        def open(self, info: OpenInfo) -> None:
            raise Refused(text or "the owner serves its largest number of sessions")

    _, response, _ = step(config, OwnerState(), decoded, _Refusing())
    return response


def _contracts(contract: Contract | Iterable[Contract]) -> tuple[Contract, ...]:
    if isinstance(contract, Contract):
        return (contract,)
    contracts = tuple(contract)
    if not all(isinstance(c, Contract) for c in contracts):
        raise TypeError("an owner takes a Contract or a sequence of Contracts")
    return contracts


class Owner:
    """The owner of one session: the state machine of `step`, its state, and an observer.

    `handle(frame)` takes one request frame and returns the response frame. It raises FrameError
    only for a bad frame, which the binding handles (section 9).

    `contract` is a `Contract`, or several contracts of one application, for example two versions
    during an upgrade (section 7.1, rule 4.2). `check_digests=False` stops the comparison of each
    request's digest with its bytes; use it only on a pipe pair or a Unix domain socket with no
    other program between the endpoints (spec section 3, rule 5). `key` authenticates every frame
    (section 13.2). `nonce` returns a fresh nonce for each opening; tests pass a fixed source.
    """

    def __init__(
        self,
        contract: Contract | Iterable[Contract],
        handler: Any,
        *,
        max_bound: int = F.DEFAULT_BOUND,
        check_digests: bool = True,
        key: bytes | None = None,
        implementation: str = IMPLEMENTATION,
        nonce: Callable[[], str] | None = None,
        observer: Any = None,
        check_schemas: bool = True,
    ) -> None:
        if key is not None and not check_digests:
            raise ValueError("an authenticated session always compares digests (section 13.2)")
        options: dict[str, Any] = {}
        if nonce is not None:
            options["nonce"] = nonce
        self.config = OwnerConfig(
            _contracts(contract),
            max_bound=max_bound,
            implementation=implementation,
            key=key,
            check_schemas=check_schemas,
            **options,
        )
        self.handler = handler
        self.check_digests = check_digests
        self.observer = observer if observer is not None else E.DEFAULT
        self.state = OwnerState()
        self._finished = False

    @property
    def contract(self) -> Contract:
        return self.config.contracts[0]

    @property
    def session(self) -> str | None:
        return self.state.session

    @property
    def bound(self) -> int:
        """The bound that the binding must apply to the next request."""
        return self.state.bound

    @property
    def ended(self) -> bool:
        return self.state.ended

    @property
    def closed(self) -> bool:
        """Whether the session ended with an `ok` response to `close`."""
        return self.state.closed

    def decode(self, frame: bytes | bytearray | memoryview) -> F.Decoded:
        """Decode one request frame with the session's bound, digest rule, and key."""
        return F.decode(frame, self.state.bound, check_digest=self.check_digests, key=self.config.key)

    def handle(self, frame: bytes | bytearray | memoryview) -> bytes:
        """Handle one request frame and return the response frame."""
        return self.handle_decoded(self.decode(frame))

    def handle_decoded(self, decoded: F.Decoded) -> bytes:
        """Handle one decoded request frame and return the response frame."""
        before = self.state
        self.state, response, note = step(self.config, before, decoded, self.handler)
        message = decoded.message
        self.observer.event(
            E.Event(
                note.kind,
                "owner",
                message.get("session"),
                message.get("seq"),
                message.get("op"),
                note.outcome,
                note.code,
                note.detail,
                note.error,
            )
        )
        return response

    def stop(self) -> None:
        """Stop admitting requests: every later request that the owner would admit gets `ended`
        with `shutdown`, and an `open` gets `rejected` with `refused` (rules 7.3.10 and 9.2.9)."""
        self.state = replace(self.state, stopping=True)

    def finish(self, reason: str = "lost") -> None:
        """Tell the handler, once, that the session ended. A binding calls it when the connection
        ends; the reason is "closed" or "ended" when the session ended by the protocol."""
        if self._finished or self.state.session is None:
            return
        self._finished = True
        if self.state.closed:
            reason = "closed"
        elif self.state.ended:
            reason = "ended"
        closer = getattr(self.handler, "close", None)
        if closer is None:
            return
        try:
            closer(reason)
        except Exception as error:  # noqa: BLE001 - reported, and the session is over anyway
            self.observer.event(
                E.Event("application_error", "owner", self.state.session, detail="close failed", error=error)
            )
