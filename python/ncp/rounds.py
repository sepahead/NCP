"""The rounds profile (spec/NCP-2-ROUNDS.md): one owner applies the requests of many agents in
rounds, in a fixed order, and tells each agent which requests each round applied."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from . import frame as F
from .exchange import BodyInvalid, Owner, ProtocolError, Result

ROUND = "ncp.round"
RECORD = "ncp.round_record"
MAX_NAME = 128

Step = Callable[[int, list[tuple[str, Any]]], dict[str, dict[str, Any]]]


class _Slot:
    """One agent's request in the open round."""

    __slots__ = ("request", "body", "result", "failed", "done")

    def __init__(self, request: str) -> None:
        self.request = request  # the identity of the request
        self.body: Any = None
        self.result: dict[str, Any] | None = None
        self.failed = False
        self.done = threading.Event()  # set when the round has closed


class Rounds:
    """Serve many agents in rounds (spec/NCP-2-ROUNDS.md).

    Each agent has its own session. Each request of operation `op` names its agent and its round
    in the body member "ncp.round": {"agent": NAME, "round": K}. Round K opens when the owner
    accepts the first request for it. It closes when every member that is not excluded has a
    request in it, or `deadline` seconds after it opened. Then `step(K, inputs)` runs once:
    `inputs` lists (agent, body) for the requests of the round, in the order of `members`, and
    `step` returns a dict that maps each of these agents to its result, a JSON object. Each agent
    receives its result with the member "ncp.round_record": the round, the agents whose requests
    the round applied, the identities of those requests, and the members that missed the round.

    A member without a request in a round when it closes is excluded from every later round, so
    an agent that stops delays the others once, by at most one deadline. If `step` raises or
    returns a wrong result, every session of the round ends with `owner_failure`, the exception
    is kept in `error`, and every later request is rejected.

    Serve the sessions with a server that runs each session in its own thread, for example
    `UnixServer(rounds.owner, path)`: a request waits in its session's thread until its round
    closes.
    """

    def __init__(
        self,
        application: str,
        contract: str,
        op: str,
        members: Iterable[str],
        step: Step,
        *,
        deadline: float,
        max_bound: int = F.DEFAULT_BOUND,
        check_digests: bool = True,
    ) -> None:
        names = tuple(members)
        if (
            not names
            or len(set(names)) != len(names)
            or not all(type(name) is str and 1 <= len(name) <= MAX_NAME for name in names)
        ):
            raise ValueError(f"members: one or more distinct names of 1 to {MAX_NAME} characters")
        if not deadline > 0:
            raise ValueError("deadline must be positive")
        self.application, self.contract, self.op = application, contract, op
        self.members, self.step, self.deadline = names, step, deadline
        self.max_bound, self.check_digests = max_bound, check_digests
        self.closed = 0  # the last round that closed
        self.excluded: dict[str, int] = {}  # member -> the round that it missed
        self.error: BaseException | None = None  # set when a step failed; no later round runs
        self._members = frozenset(names)
        self._lock = threading.Lock()
        self._sessions: dict[str, _AgentHandler] = {}
        self._slots: dict[str, _Slot] = {}  # the open round's requests, reserved or added
        self._pending = 0  # requests of the open round that are reserved but not yet added
        self._opened = 0.0  # time.monotonic() when round closed + 1 opened, if it has slots

    def owner(self) -> Owner:
        """A new owner for one agent's session."""
        handler = _AgentHandler(self)
        owner = Owner(
            self.application,
            self.contract,
            handler,
            [self.op],
            max_bound=self.max_bound,
            check_digests=self.check_digests,
        )
        handler.owner = owner
        return owner

    def _accept(self, handler: _AgentHandler, body: Any) -> None:
        """Validate a request and reserve its place in the open round. The owner executes every
        request that it validated, so a reserved place is filled at once by `_wait`."""
        member = body.get(ROUND) if type(body) is dict else None
        if type(member) is not dict or member.keys() != {"agent", "round"}:
            raise BodyInvalid('the body needs the member "ncp.round": {"agent": NAME, "round": K}')
        agent, number = member["agent"], member["round"]
        if type(agent) is not str or type(number) is not int:
            raise BodyInvalid("ncp.round: agent must be a string and round an integer")
        with self._lock:
            if self.error is not None:
                raise BodyInvalid(f"a step failed in round {self.closed}; the rounds have stopped")
            if agent not in self._members:
                raise BodyInvalid("unknown agent")
            if handler.agent is not None and handler.agent != agent:
                raise BodyInvalid("this session belongs to another agent")
            if agent in self.excluded:
                raise BodyInvalid(f"the agent is excluded: it missed round {self.excluded[agent]}")
            if self._sessions.get(agent, handler) is not handler:
                raise BodyInvalid("the agent has another session")
            if number != self.closed + 1:
                raise BodyInvalid(f"round {number} is not open; the next round is {self.closed + 1}")
            if agent in self._slots:  # unreachable: one session, one request at a time
                raise BodyInvalid("the agent already has a request in this round")
            assert handler.owner is not None and handler.owner.request_identity is not None
            self._sessions[agent] = handler
            handler.agent = agent
            if not self._slots:
                self._opened = time.monotonic()
            self._slots[agent] = _Slot(handler.owner.request_identity)
            self._pending += 1

    def _wait(self, handler: _AgentHandler, body: Any) -> dict[str, Any]:
        """Add a validated request to its round, wait until the round closes, and return the
        agent's result with the record."""
        with self._lock:
            number = self.closed + 1
            slot = self._slots[handler.agent]  # type: ignore[index]
            slot.body = body
            self._pending -= 1
            self._close_if_ready(number)
            deadline = self._opened + self.deadline
        # Each request waits on its own event, so that a closed round wakes its requests without
        # making them queue for the lock.
        while not slot.done.is_set():
            remaining = deadline - time.monotonic()
            if remaining > 0:
                slot.done.wait(remaining)
                continue
            with self._lock:
                if not slot.done.is_set():
                    self._close_if_ready(number)
            # After the deadline, a round stays open only while a reserved request is being
            # added, and the thread that adds it closes the round.
            slot.done.wait()
        if slot.failed:
            raise RuntimeError(f"the step of round {number} failed") from self.error
        assert slot.result is not None
        return slot.result

    def _close_if_ready(self, number: int) -> None:
        """Close round `number` if every member that is not excluded has a request in it, or if
        its deadline has passed; never while a reserved request is not yet added. Needs the lock."""
        if self._pending == 0 and (
            len(self._slots) + len(self.excluded) == len(self.members)
            or time.monotonic() >= self._opened + self.deadline
        ):
            self._close(number)

    def _close(self, number: int) -> None:
        applied = [(agent, self._slots[agent]) for agent in self.members if agent in self._slots]
        missing = [agent for agent in self.members if agent not in self._slots and agent not in self.excluded]
        for agent in missing:
            self.excluded[agent] = number
        try:
            results = self.step(number, [(agent, slot.body) for agent, slot in applied])
            if type(results) is not dict or results.keys() != {agent for agent, _ in applied}:
                raise TypeError("step must return one result for each agent of the round")
            record = {
                "round": number,
                "agents": [agent for agent, _ in applied],
                "requests": F.Array("u8", (len(applied), 32), b"".join(bytes.fromhex(s.request) for _, s in applied)),
                "missing": missing,
            }
            for agent, slot in applied:
                result = results[agent]
                if type(result) is not dict or RECORD in result:
                    raise TypeError(f"the result for {agent} must be an object without {RECORD}")
                slot.result = {**result, RECORD: record}  # the record is shared and never changed
        except Exception as error:  # noqa: BLE001 - any failure of the step stops the rounds
            self.error = error
            for _, slot in applied:
                slot.failed = True
        self.closed = number
        self._slots = {}
        for _, slot in applied:
            slot.done.set()


class _AgentHandler:
    """The handler of one agent's session."""

    def __init__(self, rounds: Rounds) -> None:
        self.rounds = rounds
        self.owner: Owner | None = None
        self.agent: str | None = None

    def validate(self, op: str, body: Any) -> None:
        self.rounds._accept(self, body)

    def execute(self, op: str, body: Any) -> Any:
        return self.rounds._wait(self, body)


@dataclass(frozen=True)
class RoundRecord:
    """The record of one round, as an agent received it (spec/NCP-2-ROUNDS.md)."""

    round: int
    agents: tuple[str, ...]
    requests: tuple[str, ...]  # the identities of the applied requests, in the order of agents
    missing: tuple[str, ...]

    @classmethod
    def of(cls, result: Result, agent: str) -> RoundRecord:
        """Read the record of a round response, and check that it lists the request that
        `result` answers as the request of `agent`. Raise ProtocolError otherwise."""
        record = result.body.get(RECORD) if type(result.body) is dict else None
        if type(record) is not dict or record.keys() != {"round", "agents", "requests", "missing"}:
            raise ProtocolError("the response has no round record")
        number, agents, requests, missing = record["round"], record["agents"], record["requests"], record["missing"]
        if (
            type(number) is not int
            or type(agents) is not list
            or not all(type(name) is str for name in agents)
            or type(missing) is not list
            or not all(type(name) is str for name in missing)
            or not isinstance(requests, F.Array)
            or requests.dtype != "u8"
            or tuple(requests.shape) != (len(agents), 32)
        ):
            raise ProtocolError("bad round record")
        data = bytes(requests.data)
        identities = tuple(data[i : i + 32].hex() for i in range(0, len(data), 32))
        if agent not in agents or identities[agents.index(agent)] != result.request:
            raise ProtocolError("the round record does not list this request as the agent's")
        return cls(number, tuple(agents), identities, tuple(missing))
