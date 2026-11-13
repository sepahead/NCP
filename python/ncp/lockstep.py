"""The lockstep profile (spec/NCP-2-LOCKSTEP.md).

Each step of a lockstep operation names the tick that it advances to and the state that it
answers. The owner keeps its tick and state across sessions. A client that lost a session, with
its last step possibly executed, opens a new session and learns from the `open` response whether
that step ran.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any

from .client import Client, Ended, Result
from .messages import Executed, ProtocolError
from .owner import Declined, OpenInfo, Request

FEATURE = "ncp.lockstep"
TICK = "ncp.tick"
MAX_STATE = 128


def _state_ok(value: Any) -> bool:
    return value is None or (type(value) is str and 1 <= len(value) <= MAX_STATE)


class Lockstep:
    """A handler that applies the lockstep profile around an application handler.

    `handler` is the application: `validate(request)` and `execute(request)` as for any owner, and
    `state()`, which returns a digest of the application's state after each step (a string of 1
    to 128 characters), or None. `ops` are the lockstep operations; other operations pass through
    unchanged. One `Lockstep` keeps one tick for all its sessions: pass the same object to every
    owner of the application, for example `UnixServer(lambda: ncp.Owner(contract, lockstep), path)`.

    `tick`, `state`, and `request` restore a clock that the application saved: the tick, the
    state digest, and the identity of the request whose step produced the tick.

    Only the last session that asked for the feature can step (profile, rule 3.3): `holder`.
    """

    def __init__(
        self,
        handler: Any,
        ops: Iterable[str],
        *,
        tick: int = 0,
        state: str | None = None,
        request: str | None = None,
    ) -> None:
        if type(tick) is not int or tick < 0 or not _state_ok(state) or not (request is None or type(request) is str):
            raise ValueError(
                "tick must be an integer from 0, state a string of 1 to 128 characters or None, and request a string or None"
            )
        self.handler, self.ops = handler, frozenset(ops)
        self.tick, self.state, self.request = tick, state, request
        self.holder: str | None = None
        self._lock = threading.Lock()
        self._local = threading.local()

    def open(self, info: OpenInfo) -> dict[str, Any]:
        opener = getattr(self.handler, "open", None)
        granted = dict(opener(info) or {}) if opener is not None else {}
        if FEATURE in info.features:
            # The session takes over the ticks (profile, rule 3.3). A checked step holds the lock
            # until it has run, so the tick read here is final for every earlier session: validate
            # declines their later steps.
            with self._lock:
                self.holder = info.session
                granted[FEATURE] = {"tick": self.tick, "state": self.state, "request": self.request}
        return granted

    def validate(self, request: Request) -> None:
        if request.op not in self.ops:
            self.handler.validate(request)
            return
        body = request.body
        member = body.get(TICK) if type(body) is dict else None
        if type(member) is not dict or member.keys() != {"tick", "state"}:
            raise Declined('a lockstep step needs the member "ncp.tick": {"tick": T, "state": S}')
        self._lock.acquire()
        try:
            if request.session != self.holder:
                raise Declined(
                    "the session does not hold the ticks: it did not ask for ncp.lockstep, or a later session took them over"
                )
            if type(member["tick"]) is not int or member["tick"] != self.tick + 1:
                raise Declined(f"tick: the next tick is {self.tick + 1}")
            if member["state"] != self.state:
                raise Declined("state: the step answers another state")
            self.handler.validate(request)
        except BaseException:
            self._lock.release()
            raise
        self._local.held = True  # execute follows in this thread and releases the lock

    def execute(self, request: Request) -> Any:
        if request.op not in self.ops:
            return self.handler.execute(request)
        try:
            # The step counts as executed from here, also if the application fails (profile, rule
            # 5.3): the tick advances, so that a recovery says that the step ran.
            failure: BaseException | None = None
            result: Any = None
            try:
                result = self.handler.execute(request)
            except BaseException as error:  # noqa: BLE001 - raised again below, after the tick
                failure = error
            try:
                state = getattr(self.handler, "state", lambda: None)()
            except Exception as error:  # noqa: BLE001 - the digest is then unknown
                state, failure = None, failure or error
            valid = _state_ok(state)
            self.tick += 1
            self.state = state if valid else None
            self.request = request.identity
            if failure is not None:
                raise failure
            if not valid:
                raise TypeError("state() must return a string of 1 to 128 characters or None")
            if type(result) is not dict or TICK in result:
                raise TypeError(f"a lockstep result must be an object without {TICK}")
            return {**result, TICK: {"tick": self.tick, "state": state, "request": request.identity}}
        finally:
            if getattr(self._local, "held", False):
                self._local.held = False
                self._lock.release()

    def close(self, reason: str) -> None:
        closer = getattr(self.handler, "close", None)
        if closer is not None:
            closer(reason)


class LockstepClient:
    """A client of a lockstep owner: it adds the tick and the state to each step, and it learns
    after a lost session whether its last step ran.

    Open `client` with the feature: `ncp.Client(channel, contract, features={"ncp.lockstep": {}})`.
    """

    def __init__(self, client: Client) -> None:
        if not client.opened:
            client.open()
        tick, state, _ = _granted(client)
        self.client = client
        self.tick: int = tick
        self.state: str | None = state
        # The tick and the request identity of a step that is possibly executed.
        self.uncertain: tuple[int, str | None] | None = None

    def step(self, op: str, body: dict[str, Any]) -> Result:
        """Send one lockstep step. If the call ends with the step possibly executed, `uncertain`
        holds its tick and request identity; call `recover` with a new client."""
        if TICK in body:
            raise ValueError(f"the client sets {TICK}")
        try:
            result = self.client.call(op, {**body, TICK: {"tick": self.tick + 1, "state": self.state}})
        except Ended as ended:
            if ended.executed is Executed.UNKNOWN:
                self.uncertain = (self.tick + 1, ended.request)
            elif ended.executed is Executed.YES:
                self.tick += 1  # result_too_large: the step ran; its new state is unknown here
                self.state = None
            raise
        member = result.body.get(TICK) if type(result.body) is dict else None
        if (
            type(member) is not dict
            or member.get("tick") != self.tick + 1
            or not _state_ok(member.get("state"))
            or type(member.get("request")) is not str
            or member["request"] != result.request
        ):
            raise ProtocolError("the result does not carry the next tick")
        self.tick, self.state = member["tick"], member["state"]
        return result

    def recover(self, client: Client) -> Executed:
        """Continue with `client`, a new session to the same owner, after a step that is possibly
        executed. Return YES if that step ran, NO if it did not and never will. Raise ProtocolError
        if the owner's tick is neither, for example because another client stepped it.

        The new session takes over the ticks (profile, rule 3.3), so a copy of the step that is
        still on its way can no longer run."""
        if self.uncertain is None:
            raise ValueError("no step is possibly executed")
        uncertain, identity = self.uncertain
        if not client.opened:
            client.open()
        tick, state, last = _granted(client)
        if tick == uncertain and identity is not None and last == identity:
            verdict = Executed.YES
        elif tick == uncertain - 1:
            verdict = Executed.NO
        else:
            raise ProtocolError(f"the owner is at tick {tick}; the uncertain step was tick {uncertain}")
        self.client, self.tick, self.state, self.uncertain = client, tick, state, None
        return verdict


def _granted(client: Client) -> tuple[int, str | None, str | None]:
    """The owner's tick, state digest, and the identity of the request that produced the tick."""
    granted = client.enabled.get(FEATURE)
    if (
        type(granted) is not dict
        or type(granted.get("tick")) is not int
        or granted["tick"] < 0
        or not _state_ok(granted.get("state"))
        or not (granted.get("request") is None or type(granted.get("request")) is str)
    ):
        raise ProtocolError("the owner did not enable ncp.lockstep")
    return granted["tick"], granted.get("state"), granted.get("request")
