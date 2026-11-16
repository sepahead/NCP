"""The lockstep profile, revision 4 (spec/NCP-2-LOCKSTEP.md).

Each step of a lockstep operation names the tick that it advances to and the state that it
answers. The owner keeps its tick, state, and term across sessions. One opening at a time holds the
ticks: the last one whose take (`ncp.lockstep.take`) succeeded. An `open` only reports the tick. A
client that lost a session, with its last step possibly executed, opens a new session, takes the
ticks, and learns from the response of the take whether that step ran.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable
from typing import Any

from . import frame as F
from .client import Client, Ended, Result, UsageError
from .messages import CallError, Executed, ProtocolError, is_identity
from .owner import Declined, OpenInfo, Request

FEATURE = "ncp.lockstep"
TICK = "ncp.tick"
TAKE = "ncp.lockstep.take"
MAX_STATE = 128
# How many takes a client sends in one session before it gives up on a term that keeps moving.
TAKE_ATTEMPTS = 3
# The largest term and the largest tick: the largest integer that a JSON number carries exactly
# (profile, rules 5.2 and 5.4).
MAX_TERM = MAX_TICK = F.MAX_INTEGER
# The default state digest of a new Lockstep: the application's digest of its state now.
_INITIAL: Any = object()

# What a client knows of the owner's clock: the tick, the state digest, and the identity of the
# request whose step produced the tick.
Known = tuple[int, "str | None", "str | None"]


def _state_ok(value: Any) -> bool:
    return value is None or (type(value) is str and 1 <= len(value) <= MAX_STATE)


def _term_ok(value: Any) -> bool:
    return type(value) is int and 0 <= value <= MAX_TERM


def _told_term(declined: Declined) -> int | None:
    """The owner's term that a `declined` response names in its member `ncp.lockstep`, if any."""
    moved = declined.body.get(FEATURE) if type(declined.body) is dict else None
    return moved["term"] if type(moved) is dict and _term_ok(moved.get("term")) else None


class Lockstep:
    """A handler that applies the lockstep profile around an application handler.

    `handler` is the application: `validate(request)` and `execute(request)` as for any owner, and
    `state()`, which returns a digest of the application's state after each step (a string of 1
    to 128 characters), or None. `ops` are the lockstep operations; other operations pass through
    unchanged. One `Lockstep` keeps one tick for all its sessions: pass the same object to every
    owner of the application, for example `UnixServer(lambda: ncp.Owner(contract, lockstep), path)`.

    `tick`, `state`, `request`, and `term` restore a clock that the application saved: the tick,
    the state digest, the identity of the request whose step produced the tick, and the term
    (profile, rule 5.7). Without `state`, the clock starts with the application's digest of its
    state now, from `state()`, or None if the application has no `state`.

    Only the opening whose take succeeded last can step (profile, rule 5.3): `holder` is the
    nonce of that opening, and `term` counts the takes. A session identifier does not name one
    opening: a copy of an old `open` opens the session again with another nonce (specification,
    rule 7.1.8). Accepting an `open` changes neither.

    Use `Lockstep` as the outermost handler of the owner. A successful `validate` of a take or a
    step holds the lock of the clock until `execute` runs; a handler around `Lockstep` that
    declines after it leaves the lock held, and every later take and step waits. Other operations,
    and the application's `open`, pass through without the lock: an application that serves them
    while a step runs keeps its own state safe across threads.
    """

    def __init__(
        self,
        handler: Any,
        ops: Iterable[str],
        *,
        tick: int = 0,
        state: str | None = _INITIAL,
        request: str | None = None,
        term: int = 0,
    ) -> None:
        if state is _INITIAL:
            digest = getattr(handler, "state", None)
            state = digest() if digest is not None else None
        if (
            type(tick) is not int
            or not 0 <= tick <= MAX_TICK
            or not _state_ok(state)
            or not (request is None or is_identity(request))
            or not _term_ok(term)
        ):
            raise ValueError(
                "tick and term must be integers from 0 to 2**53 - 1, state a string of 1 to 128 characters or "
                "None, and request the identity of a request or None"
            )
        self.handler, self.ops = handler, frozenset(ops)
        self.tick, self.state, self.request = tick, state, request
        self.term = term
        self.holder: str | None = None
        # _lock orders the steps and takes: a step holds it from its check to the end of its
        # execution. _clock guards the clock for a report, which never waits for a step.
        self._lock = threading.Lock()
        self._clock = threading.Lock()
        self._local = threading.local()

    def clock(self) -> dict[str, Any]:
        """The tick, the state digest, the request that produced the tick, and the term."""
        with self._clock:
            return {"tick": self.tick, "state": self.state, "request": self.request, "term": self.term}

    def open(self, info: OpenInfo) -> dict[str, Any]:
        opener = getattr(self.handler, "open", None)
        granted = dict(opener(info) or {}) if opener is not None else {}
        if FEATURE in info.features:
            # A report from one instant (profile, rule 3.2). It changes nothing outside the
            # session, so that a copy of this `open` takes nothing (rule 3.3), and it does not
            # wait for a running step.
            granted[FEATURE] = self.clock()
        return granted

    def validate(self, request: Request) -> None:
        if request.op == TAKE:
            body = request.body
            if type(body) is not dict or body.keys() != {"term"} or not _term_ok(body["term"]):
                raise Declined('member: a take needs the body {"term": E}')
            # Wait until no checked step is still to run (rule 5.1): a step holds the lock from
            # its check to the end of its execution, so the clock read after this is final.
            self._lock.acquire()
            # A term that moved: another take ran after the owner told the client the term
            # (rule 5.2). The response names the owner's term.
            if body["term"] != self.term:
                term = self.term
                self._lock.release()
                raise Declined(f"term: the term is {term}", body={FEATURE: {"term": term}})
            # The largest term, which no take can raise (rule 5.2).
            if self.term >= MAX_TERM:
                self._lock.release()
                raise Declined("term: the term is the largest; no take can follow it")
            self._local.held = True  # execute follows in this thread and releases the lock
            return
        if request.op.startswith(FEATURE + "."):
            raise Declined(f"operation: the lockstep profile defines no operation {request.op}; it defines {TAKE}")
        if request.op not in self.ops:
            self.handler.validate(request)
            return
        body = request.body
        member = body.get(TICK) if type(body) is dict else None
        if type(member) is not dict or member.keys() != {"tick", "state"}:
            raise Declined('member: a lockstep step needs "ncp.tick": {"tick": T, "state": S}')
        self._lock.acquire()
        try:
            if request.nonce != self.holder:
                # The term lets the client take the ticks again in this session (rule 6.4).
                raise Declined(
                    "holder: this opening does not hold the ticks; send ncp.lockstep.take",
                    body={FEATURE: {"term": self.term}},
                )
            if self.tick >= MAX_TICK:
                raise Declined("tick: the tick is the largest; no step can follow it")
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
        if request.op == TAKE:
            try:
                # The take counts as executed: its opening holds the ticks, and the term moves on
                # (rule 5.3). The clock is final: no step of another opening can run any more.
                with self._clock:
                    self.holder, self.term = request.nonce, self.term + 1
                return self.clock()
            finally:
                self._release()
        if request.op not in self.ops:
            return self.handler.execute(request)
        try:
            # The step counts as executed from here, also if the application fails (profile, rule
            # 5.5): the tick advances, so that a recovery says that the step ran.
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
            with self._clock:
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
            self._release()

    def _release(self) -> None:
        if getattr(self._local, "held", False):
            self._local.held = False
            self._lock.release()

    def close(self, reason: str) -> None:
        closer = getattr(self.handler, "close", None)
        if closer is not None:
            closer(reason)


class LockstepClient:
    """A client of a lockstep owner: it takes the ticks, adds the tick and the state to each step,
    and learns after a lost session whether its last step ran.

    Open `client` with the feature: `ncp.Client(channel, contract, features={"ncp.lockstep": {}})`.
    The constructor opens the session if it is not open yet, and takes the ticks.
    """

    def __init__(self, client: Client) -> None:
        if not client.opened:
            client.open()
        self.client = client
        # The tick, the state digest, and the request that produced the tick, as the client knows
        # them, and the term that the owner told last in this session (rule 4.1).
        (self.tick, self.state, self.request), self.term = take(client)
        # The tick and the request identity of a step that is possibly executed.
        self.uncertain: tuple[int, str | None] | None = None

    def take(self) -> None:
        """Take the ticks again in this session, with the term that the owner told last: for
        example after a step that was declined because another opening took them (rule 6.4)."""
        if self.uncertain is not None:
            raise UsageError("a step is possibly executed: call recover with a new client")
        try:
            (self.tick, self.state, self.request), self.term = take(self.client, self.term)
        except Declined as declined:
            told = _told_term(declined)  # the owner told a newer term: the next take names it (rule 4.1)
            if told is not None:
                self.term = told
            raise

    def step(self, op: str, body: dict[str, Any]) -> Result:
        """Send one lockstep step. If the call ends with the step possibly executed, `uncertain`
        holds its tick and request identity; call `recover` with a new client."""
        if TICK in body:
            raise UsageError(f"the client sets {TICK}")
        if self.tick >= MAX_TICK:
            raise UsageError("the tick is the largest; no step can follow it")
        try:
            result = self.client.call(op, {**body, TICK: {"tick": self.tick + 1, "state": self.state}})
        except Declined as declined:
            # The holder check names the owner's term: another opening took the ticks (rule 6.4).
            told = _told_term(declined)
            if told is not None:
                self.term = told
            raise
        except Ended as ended:
            if ended.executed is Executed.UNKNOWN:
                self.uncertain = (self.tick + 1, ended.request)
            elif ended.executed is Executed.YES:
                # result_too_large: the step ran; its new state digest is unknown here.
                self.tick, self.state, self.request = self.tick + 1, None, ended.request
            raise
        member = result.body.get(TICK) if type(result.body) is dict else None
        if (
            type(member) is not dict
            or not {"tick", "state", "request"} <= member.keys()
            or type(member["tick"]) is not int
            or member["tick"] != self.tick + 1
            or not _state_ok(member["state"])
            or type(member["request"]) is not str
            or member["request"] != result.request
        ):
            # The step ran, but the owner broke the profile (rule 6.3): the clock is unknown, and
            # the session ends.
            self.tick, self.state, self.request = self.tick + 1, None, result.request
            _end(self.client)
            raise Ended("local.protocol", Executed.YES, result.body, "the result does not carry the next tick", result.request)
        self.tick, self.state, self.request = member["tick"], member["state"], member["request"]
        return result

    def recover(self, client: Client) -> Executed:
        """Continue with `client`, a new session to the same owner, after a step that is possibly
        executed. Return YES if that step ran, and NO if it did not and never will. Return UNKNOWN
        if the owner's clock changed in another way, for example because another client stepped it
        or the owner restarted with another state: the step stays possibly executed (rule 6.5).

        The opening of `client` takes the ticks (profile, rule 5.3), so a copy of the step that is
        still on its way can no longer run. The verdict comes from the response of the take, never
        from the `open` response, whose report can be older. With every verdict, the client goes on
        in the new session from the owner's clock. If the take is declined, recover ends the session
        of `client` and raises: the step stays possibly executed; recover again with a new client."""
        if self.uncertain is None:
            raise UsageError("no step is possibly executed")
        if not client.opened:
            client.open()
        try:
            taken, term = take(client)
        except Declined:
            # The client does not go on in this session, whose term moved: try again with a new client.
            _end(client)
            raise
        verdict = judge((self.tick, self.state, self.request), self.uncertain, taken)
        self.client, self.uncertain, self.term = client, None, term
        self.tick, self.state, self.request = taken
        return verdict


def judge(known: Known, uncertain: tuple[int, str | None], taken: Known) -> Executed:
    """The verdict of a recovery (profile, rule 6.5), from what the client knew before its
    uncertain step (`known`: tick, state digest, request), the tick and request identity of that
    step (`uncertain`), and the response of the take in the new opening (`taken`).

    YES if the take names the tick of the step and the identity of its request; NO if it names
    exactly what the client knew, so that the step did not run and never will; otherwise UNKNOWN:
    the owner's clock changed in another way, and the step stays possibly executed."""
    tick, identity = uncertain
    if taken[0] == tick and identity is not None and taken[2] == identity:
        return Executed.YES
    if taken == known and known[0] == tick - 1:
        return Executed.NO
    return Executed.UNKNOWN


def report(client: Client) -> dict[str, Any]:
    """The report of the `open` response (profile, rule 3.2): tick, state, request, and term. It can
    be older than the owner's clock by the time it arrives; only a take gives final values."""
    granted = client.enabled.get(FEATURE)
    if (
        type(granted) is not dict
        or not {"tick", "state", "request", "term"} <= granted.keys()
        or type(granted.get("tick")) is not int
        or granted["tick"] < 0
        or not _state_ok(granted.get("state"))
        or not (granted.get("request") is None or type(granted.get("request")) is str)
        or not _term_ok(granted.get("term"))
    ):
        raise ProtocolError("the owner did not enable ncp.lockstep (revision 4 of the profile)")
    return granted


def _end(client: Client) -> None:
    """End the session of a client whose owner broke the profile."""
    try:
        client.close()
    except (CallError, OSError, ValueError):
        pass  # the session ends anyway


def take(client: Client, term: int | None = None) -> tuple[Known, int]:
    """Take the ticks for the opening of `client` (profile, rules 5.2 and 5.3). Return the final
    tick, state digest, and request identity, and the owner's new term.

    `term` is the term that the owner told last in this session (rule 4.1), by default the term of
    the `open` response. A take that is declined because the term moved is sent again with the
    owner's term, at most TAKE_ATTEMPTS times in all; then, or if the term did not move, the last
    `Declined` is raised. If the `open` response does not enable the feature with a term, take
    ends the session and raises ProtocolError (rule 3.4). If a take ran and its response does not
    carry the clock, take ends the session and raises `Ended` with the code `local.protocol`: the
    take executed (rule 6.1)."""
    try:
        told = report(client)["term"]
    except ProtocolError:
        _end(client)
        raise
    if term is None:
        term = told
    elif not _term_ok(term):
        raise UsageError(f"a term is an integer from 0 to {MAX_TERM}")
    for attempt in range(1, TAKE_ATTEMPTS + 1):
        try:
            result = client.call(TAKE, {"term": term})
        except Declined as declined:
            told = _told_term(declined)
            if attempt == TAKE_ATTEMPTS or told is None or told == term:
                raise
            term = told
            continue
        body = result.body
        if (
            type(body) is not dict
            or not {"tick", "state", "request", "term"} <= body.keys()
            or type(body["tick"]) is not int
            or body["tick"] < 0
            or not _state_ok(body["state"])
            or not (body["request"] is None or type(body["request"]) is str)
            or not _term_ok(body["term"])
            or body["term"] != term + 1
        ):
            _end(client)
            raise Ended("local.protocol", Executed.YES, body, "the response of the take does not carry the clock", result.request)
        return (body["tick"], body["state"], body["request"]), body["term"]
    raise AssertionError("unreachable: the last attempt returns or raises")
