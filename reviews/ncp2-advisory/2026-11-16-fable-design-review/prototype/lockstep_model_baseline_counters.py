#!/usr/bin/env python3
"""Exhaustive check of the lockstep profile (spec/NCP-2-LOCKSTEP.md, revision 4).

As in simulate.py, the real machines of the Python SDK exchange real frames: the owner is
`ncp.owner.step` with the real `ncp.Lockstep` handler, and the client is the pure machine of
`ncp.client`, which a small stepping program drives. The verdict of a recovery comes from
`ncp.lockstep.judge`, the function that `LockstepClient.recover` uses. The handler's clock is copied
into it before each owner step and read back after it, so that each world is a value.

  stepping client L   open, take, step, step. After a step that is possibly executed, or a declined
                      step, or a take that fails, it opens a new session (at most SESSIONS in all)
                      and takes the ticks again; a recovery reads its verdict from the take. After
                      a recovery without a verdict, L goes on from the clock of the take, as
                      LockstepClient.recover does.
  shapes   stream     one owner for each connection; a copy of a frame arrives on a new connection
           zenoh      one owner for each session identifier, as the Zenoh servers keep them
  free                delay and reordering of every frame, and the client's time limit
  faults              a copy of any frame that L sent; the loss of a frame; the expiry of a
                      session (zenoh); a restart of the owner that keeps its tick, state, and
                      request, that restores the same tick with another state, or that restores
                      an earlier saved clock with its state (profile, rule 5.7), the initial one
                      included; another client that takes the ticks and steps once

In every reachable world, the search checks:

  S1 truthful   a step with the verdict "did not run" never runs, before or after; "ran" is true.
                After a restart to an earlier saved clock, the verdict of a recovery describes the
                owner's state (profile, section 7): "did not run" then means that the step was not
                in that state when the take ran
  S2 holder     a step runs only in the opening whose take succeeded last
  S3 ticks      the steps that run produce the ticks 1, 2, 3, ..., each once
  S4 verdict    a recovery gives a verdict, unless another client stepped or the owner restored
                another state or an earlier clock (profile, rule 6.5)
  S5 open reads accepting an open changes neither the clock nor the holder (rule 3.3, and rule
                7.1.8 of the specification)
  S6 resend     after the verdict "did not run", the owner's state when L's take ran was the state
                that the step answered, produced by the request that L knew, so the step can be
                sent again
  L1 stable     while the owner holds L's opening and that opening took the ticks, no frame takes
                them from it, unless another client takes them
  progress      without faults and time limits, L finishes its script: checked in each world
                where only faults could still happen

`--same-session` makes L use one session identifier for all its sessions. `--self-test` injects
each defect of MUTANTS in turn and requires the search to find a violation; it tries both shapes,
with new and with reused session identifiers.
Each owner step is atomic in the search, so the wait of a take for a running step is outside it;
the SDK tests cover that wait. Usage:
lockstep.py [--faults 1] [--shape both] [--same-session] [--self-test] [--max-worlds N]
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
import time
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))

import ncp  # noqa: E402
from ncp import client as C  # noqa: E402
from ncp import frame as F  # noqa: E402
from ncp import lockstep as LS  # noqa: E402
from ncp import owner as O  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}'
)
IDS = [f"6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a{n:02x}" for n in range(8)]
OTHER = IDS[7]  # the session identifier of the other client
STEPS = 2  # the steps of L's script
SESSIONS = 3  # L's sessions, its first one included
LIMIT = 3_000_000  # by default, stop with a message above this many worlds

MUTANTS = (
    "holder_by_session",  # the holder is a session identifier, as in revision 4 of the SDKs
    "constant_nonce",  # every opening has the same nonce: assumption A4 is broken
    "takeover_in_open",  # an open with the feature takes the ticks, as revision 3 of the profile did
    "take_without_term",  # a take does not compare its term (rule 5.2)
    "verdict_from_open_report",  # the client judges from the report of the open (rule 6.5)
    "verdict_ignores_request",  # "ran" from the tick alone, without the request identity
    "step_skips_holder_check",  # a step of any opening can run (rule 5.4)
    "take_keeps_term",  # a take does not raise the term (rule 5.3)
    "verdict_ignores_state",  # "did not run" from the tick alone, without the state and request
    "step_moves_two_ticks",  # a step advances the tick by 2 (rule 5.5)
    "judge_never_decides",  # a recovery never gives a verdict (rule 6.5)
    "take_always_declined",  # the owner declines every take, so no client can step (rule 5.3)
)


class Violation(Exception):
    def __init__(self, prop: str, text: str) -> None:
        super().__init__(f"{prop}: {text}")
        self.prop = prop


def require(condition: bool, prop: str, text: str) -> None:
    if not condition:
        raise Violation(prop, text)


class App:
    """The application: a position that each step moves; its state digest names the position."""

    def __init__(self) -> None:
        self.position = 0

    def validate(self, request: O.Request) -> None:
        pass

    def execute(self, request: O.Request) -> dict:
        self.position += request.body["dx"]
        return {"position": self.position}

    def state(self) -> str:
        return f"p{self.position}"


class TakeoverInOpen(LS.Lockstep):
    """Mutant: an open with the feature takes the ticks."""

    def open(self, info: O.OpenInfo) -> dict:
        granted = super().open(info)
        if LS.FEATURE in info.features:
            self.holder, self.term = info.nonce, self.term + 1
            granted[LS.FEATURE] = self.clock()
        return granted


class TakeWithoutTerm(LS.Lockstep):
    """Mutant: a take with any term succeeds."""

    def validate(self, request: O.Request) -> None:
        if request.op == LS.TAKE and type(request.body) is dict and type(request.body.get("term")) is int:
            request = dataclasses.replace(request, body={"term": self.term})
        super().validate(request)


class StepWithoutHolder(LS.Lockstep):
    """Mutant: a step passes the holder check whatever its opening."""

    def validate(self, request: O.Request) -> None:
        if request.op in self.ops and self.holder is not None:
            request = dataclasses.replace(request, nonce=self.holder)
        super().validate(request)


class TakeKeepsTerm(LS.Lockstep):
    """Mutant: a take that runs does not raise the term."""

    def execute(self, request: O.Request) -> object:
        result = super().execute(request)
        if request.op == LS.TAKE:
            self.term -= 1
            result = self.clock()
        return result


class StepMovesTwoTicks(LS.Lockstep):
    """Mutant: a step advances the tick by 2."""

    def execute(self, request: O.Request) -> object:
        result = super().execute(request)
        if request.op in self.ops:
            self.tick += 1
        return result


class TakeAlwaysDeclined(LS.Lockstep):
    """Mutant: the owner declines every take with its term."""

    def validate(self, request: O.Request) -> None:
        if request.op == LS.TAKE:
            raise O.Declined(f"term: the term is {self.term}", body={LS.FEATURE: {"term": self.term}})
        super().validate(request)


class BySession:
    """Mutant: the handler sees the session identifier in place of the nonce of the opening."""

    def __init__(self, inner: LS.Lockstep) -> None:
        self.inner = inner

    def open(self, info: O.OpenInfo) -> dict:
        return self.inner.open(dataclasses.replace(info, nonce=info.session))

    def validate(self, request: O.Request) -> None:
        self.inner.validate(dataclasses.replace(request, nonce=request.session))

    def execute(self, request: O.Request) -> object:
        return self.inner.execute(dataclasses.replace(request, nonce=request.session))


def judge_ignoring_request(known: tuple, uncertain: tuple, taken: tuple) -> ncp.Executed:
    """Mutant of LS.judge: a take at the tick of the step says that the step ran."""
    if taken[0] == uncertain[0]:
        return ncp.Executed.YES
    return LS.judge(known, uncertain, taken)


def judge_ignoring_state(known: tuple, uncertain: tuple, taken: tuple) -> ncp.Executed:
    """Mutant of LS.judge: a take at the tick before the step says that the step did not run."""
    if taken[0] == uncertain[0] - 1:
        return ncp.Executed.NO
    return LS.judge(known, uncertain, taken)


@dataclasses.dataclass(frozen=True)
class Stepper:
    """The program of the stepping client L."""

    phase: str = "open"  # open, take, step, done, stuck
    index: int = 0  # the index of its current session
    cs: C.ClientState | None = None
    known: tuple = (0, "p0", None)  # the tick, state digest, and request that L knows
    done: int = 0  # the steps of its script that it knows to have run
    uncertain: tuple | None = None  # (tick, request identity) of a step that is possibly executed
    term: int = 0  # the term that its next take names
    takes: int = 0  # the takes that it sent in this session
    report: tuple | None = None  # the clock in the report of its last open
    holds: bool = False  # its current opening took the ticks
    opening: int | None = None  # ghost: the opening of its current session


@dataclasses.dataclass(frozen=True)
class World:
    clock: tuple  # tick, state digest, request, term, holder nonce, and the application's position
    owners: tuple = ()  # sorted (key, OwnerState, opening)
    to_owner: tuple = ()  # sorted (key, frame) on their way to an owner
    to_client: tuple = ()  # sorted (frame, ghost: the opening that sent it, or -1) on their way to L
    stepper: Stepper = Stepper()
    sent: tuple = ()  # sorted (key, frame): every frame that L sent
    openings: int = 0
    holder: int | None = None  # ghost: the opening whose take succeeded last
    ran: tuple = ()  # the identities of the steps that ran, in order
    verdicts: tuple = ()  # (identity, "yes" or "no")
    faults: int = 0
    timed: bool = False  # a time limit expired
    connections: int = 0  # stream: the new connections that copies opened
    other: bool = False  # another client took the ticks and stepped
    rewound: bool = False  # the owner restored the same tick with another state
    older: bool = False  # the owner restored an earlier saved clock
    current: tuple = ()  # the identities of the steps in the owner's state, in order
    history: tuple = ((0, "p0", None, 0),)  # tick, state, request, position: after each of current
    taken: tuple = ()  # ghost: sorted (opening, (the clock, current) when the take of that opening ran)


def put(items: tuple, item: object) -> tuple:
    return tuple(sorted(items + (item,)))


def drop(items: tuple, index: int) -> tuple:
    return items[:index] + items[index + 1 :]


def distinct(items: tuple) -> list[int]:
    first: dict = {}
    for index, item in enumerate(items):
        first.setdefault(item, index)
    return list(first.values())


class Search:
    def __init__(self, shape: str, budget: int, mutant: str | None = None, same_session: bool = False,
                 limit: int = LIMIT) -> None:
        self.shape, self.budget, self.mutant, self.same, self.limit = shape, budget, mutant, same_session, limit
        self.app = App()
        kinds = {
            "takeover_in_open": TakeoverInOpen,
            "take_without_term": TakeWithoutTerm,
            "step_skips_holder_check": StepWithoutHolder,
            "take_keeps_term": TakeKeepsTerm,
            "step_moves_two_ticks": StepMovesTwoTicks,
            "take_always_declined": TakeAlwaysDeclined,
        }
        self.lockstep = kinds.get(mutant or "", LS.Lockstep)(self.app, ["step"])
        self.handler = BySession(self.lockstep) if mutant == "holder_by_session" else self.lockstep
        judges = {
            "verdict_ignores_request": judge_ignoring_request,
            "verdict_ignores_state": judge_ignoring_state,
            "judge_never_decides": lambda known, uncertain, taken: ncp.Executed.UNKNOWN,
        }
        self.judge = judges.get(mutant or "", LS.judge)
        self.next_nonce = 1
        self.config = O.OwnerConfig((CONTRACT,), max_bound=F.HANDSHAKE_BOUND, nonce=self.nonce)
        self.cache: dict = {}
        self.stats: dict = {}

    def nonce(self) -> str:
        return "0" * 32 if self.mutant == "constant_nonce" else f"{self.next_nonce:032x}"

    # ---- the owner side

    def owner_step(self, clock: tuple, state: O.OwnerState, frame: bytes, openings: int) -> tuple:
        key = (clock, state, frame, openings)
        hit = self.cache.get(key)
        if hit is None:
            ls = self.lockstep
            ls.tick, ls.state, ls.request, ls.term, ls.holder = clock[:5]
            self.app.position = clock[5]
            self.next_nonce = openings + 1
            decoded = F.decode(frame, state.bound)
            after, response, note = O.step(self.config, state, decoded, self.handler)
            clock = (ls.tick, ls.state, ls.request, ls.term, ls.holder, self.app.position)
            hit = (after, response, note, decoded, F.decode(response, F.MAX_BOUND).message, clock)
            self.cache[key] = hit
        return hit

    def owner_takes(self, w: World, index: int) -> World:
        key, frame = w.to_owner[index]
        entry = next((o for o in w.owners if o[0] == key), None)
        state, opening = (entry[1], entry[2]) if entry else (O.OwnerState(), None)
        after, response, note, decoded, answer, clock = self.owner_step(w.clock, state, frame, w.openings)
        request = decoded.message
        changes: dict = {"to_owner": drop(w.to_owner, index), "clock": clock}
        if state.session is None and after.session is not None:  # a new opening
            opening = w.openings + 1
            changes["openings"] = opening
        owners = tuple(o for o in w.owners if o[0] != key)
        if after.session is not None:
            owners = tuple(sorted(owners + ((key, after, opening),), key=lambda o: o[0]))
        changes["owners"] = owners
        if request["op"] == "open":
            require(clock[:5] == w.clock[:5], "S5", "accepting an open changed the clock or the holder")
        holder = w.holder
        took = request["op"] == LS.TAKE and answer["outcome"] == "ok" and note.kind == "admitted"
        took = took or (self.mutant == "takeover_in_open" and request["op"] == "open" and state.session is None
                        and after.session is not None and LS.FEATURE in after.features)
        if took:
            holder = opening
            changes["taken"] = tuple(sorted({**dict(w.taken), opening: (clock, w.current)}.items()))
        changes["holder"] = holder
        if note.executed and request["op"] == "step":
            identity = decoded.identity
            require(w.holder == opening, "S2", f"a step ran in opening {opening}; opening {w.holder} took the ticks last")
            require((identity, "no") not in w.verdicts, "S1", "a step ran after the verdict 'did not run'")
            require(identity not in w.ran, "S3", "a step ran twice")
            require(w.rewound or clock[0] == len(w.current) + 1, "S3", "the tick does not count the steps that ran")
            changes["ran"] = w.ran + (identity,)
            changes["current"] = w.current + (identity,)
            changes["history"] = w.history + ((clock[0], clock[1], clock[2], clock[5]),)
        cs = w.stepper.cs
        if cs is not None and cs.pending is not None and key == self.key_of(w.stepper.index):
            changes["to_client"] = put(w.to_client, (response, -1 if opening is None else opening))
        return self.stable(dataclasses.replace(w, **changes))

    def stable(self, w: World) -> World:
        """L1: only while the owner still holds L's opening, because a restart or an expiry loses
        it by rule, and only while no other client takes the ticks."""
        s = w.stepper
        if not w.other and s.holds and s.phase in ("step", "done") and any(o[2] == s.opening for o in w.owners):
            require(w.holder == s.opening, "L1", f"opening {w.holder} took the ticks from L's opening {s.opening}")
        return w

    # ---- the client side

    def key_of(self, index: int) -> tuple:
        session = IDS[0 if self.same else index]
        return ("s", session) if self.shape == "zenoh" else ("c", index)

    def fresh(self, s: Stepper, **more: object) -> Stepper:
        """L leaves its session and opens its next one, if it has one left."""
        index = s.index + 1
        if index >= SESSIONS:
            return dataclasses.replace(s, phase="stuck", cs=None, holds=False, **more)
        cs = C.new_state(CONTRACT, session=IDS[0 if self.same else index], bound=F.HANDSHAKE_BOUND)
        return dataclasses.replace(s, phase="open", index=index, cs=cs, holds=False, opening=None, takes=0, **more)

    def send(self, w: World) -> World:
        s = w.stepper
        if s.phase == "open":
            cs, frame = C.request(s.cs, "open", None, features={LS.FEATURE: {}})
        elif s.phase == "take":
            cs, frame = C.request(s.cs, LS.TAKE, {"term": s.term})
            s = dataclasses.replace(s, takes=s.takes + 1)
        else:
            body = {"dx": s.done + 1, LS.TICK: {"tick": s.known[0] + 1, "state": s.known[1]}}
            cs, frame = C.request(s.cs, "step", body)
        item = (self.key_of(s.index), frame)
        return dataclasses.replace(
            w,
            stepper=dataclasses.replace(s, cs=cs),
            to_owner=put(w.to_owner, item),
            sent=tuple(sorted(set(w.sent) | {item})),
        )

    def verdict(self, w: World, s: Stepper, taken: tuple) -> tuple[World, Stepper]:
        """L's verdict on its uncertain step, from the response of a take (profile, rule 6.5)."""
        if s.uncertain is None:
            return w, s
        tick, identity = s.uncertain
        verdict = self.judge(s.known, s.uncertain, taken)
        if verdict is ncp.Executed.UNKNOWN:
            label = ('unknown', 'older' if w.older else 'rewound' if w.rewound else 'other' if w.other else 'plain', 'ran' if identity in w.ran else 'never ran')
            self.stats[label] = self.stats.get(label, 0) + 1
            if w.other or w.rewound or w.older or getattr(w, 'restarted', False):
                # The clock changed in another way: no verdict is truthful. The step stays possibly
                # executed, and L goes on from the clock of the take.
                return w, dataclasses.replace(s, uncertain=None)
            raise Violation("S4", f"the recovery gave no verdict: the take returned {taken}, L knew {s.known}")
        at_take = dict(w.taken).get(s.opening)
        label = (verdict.value, 'older' if w.older else 'rewound' if w.rewound else 'plain', 'ran' if identity in w.ran else 'never ran')
        self.stats[label] = self.stats.get(label, 0) + 1
        if verdict is ncp.Executed.YES:
            require(identity in w.ran, "S1", "'ran' for a step that did not run")
        elif w.older:
            # After a restart to an earlier saved clock, "did not run" describes the owner's state
            # when the take ran (profile, section 7).
            require(at_take is not None and identity not in at_take[1], "S1",
                    "'did not run' for a step in the owner's state when the take ran")
        else:
            require(identity not in w.ran, "S1", "'did not run' for a step that ran")
        if verdict is ncp.Executed.NO:
            require(w.other or (at_take is not None and at_take[0][1:3] == s.known[1:3]), "S6",
                    "'did not run', but when the take ran, the owner's state was not the state that the step answered")
        w = dataclasses.replace(w, verdicts=w.verdicts + ((identity, verdict.value),))
        return w, dataclasses.replace(s, done=s.done + (verdict is ncp.Executed.YES), uncertain=None)

    def react(self, w: World, before: C.ClientState, after: C.ClientState, verdict: object, sender: int) -> World:
        """L's program, after the verdict on its outstanding request. `sender` is the opening that
        sent the response, or -1."""
        s = dataclasses.replace(w.stepper, cs=after)
        op, identity = before.pending.op, before.pending.identity
        if op == "open":
            if not isinstance(verdict, C.Result):
                return dataclasses.replace(w, stepper=self.fresh(s), to_client=())
            opening = None if sender < 0 else sender
            report = verdict.body["features"][LS.FEATURE]
            clock = (report["tick"], report["state"], report["request"])
            s = dataclasses.replace(s, phase="take", term=report["term"], opening=opening, report=clock)
            if self.mutant == "verdict_from_open_report":
                w, s = self.verdict(w, s, clock)
            return dataclasses.replace(w, stepper=s)
        if op == LS.TAKE:
            if isinstance(verdict, C.Result):
                body = verdict.body
                taken = (body["tick"], body["state"], body["request"])
                w, s = self.verdict(w, s, taken)
                if s.phase == "stuck":
                    return dataclasses.replace(w, stepper=s, to_client=())
                phase = "done" if s.done >= STEPS else "step"
                return dataclasses.replace(w, stepper=dataclasses.replace(s, known=taken, phase=phase, holds=True))
            if isinstance(verdict, O.Declined) and type(verdict.body) is dict:
                moved = verdict.body.get(LS.FEATURE, {}).get("term")
                if type(moved) is int and moved != s.term and s.takes < LS.TAKE_ATTEMPTS:
                    return dataclasses.replace(w, stepper=dataclasses.replace(s, term=moved))
            return dataclasses.replace(w, stepper=self.fresh(s), to_client=())
        if isinstance(verdict, C.Result):
            member = verdict.body[LS.TICK]
            require(identity in w.ran, "S1", "an ok for a step that did not run")
            done = s.done + 1
            s = dataclasses.replace(s, known=(member["tick"], member["state"], member["request"]), done=done,
                                    phase="done" if done >= STEPS else "step")
            return dataclasses.replace(w, stepper=s, verdicts=w.verdicts + ((identity, "yes"),))
        if isinstance(verdict, O.Declined) or (isinstance(verdict, C.Ended) and verdict.executed is ncp.Executed.NO):
            require(identity not in w.ran, "S1", "'did not run' for a step that ran")
            return dataclasses.replace(w, stepper=self.fresh(s), to_client=(), verdicts=w.verdicts + ((identity, "no"),))
        assert isinstance(verdict, C.Ended) and verdict.executed is ncp.Executed.UNKNOWN, verdict
        uncertain = (s.known[0] + 1, identity)
        return dataclasses.replace(w, stepper=self.fresh(s, uncertain=uncertain), to_client=())

    def other_client(self, w: World) -> World:
        """Another client: in its own session, it opens, takes the ticks, and steps once."""
        key = ("s", OTHER) if self.shape == "zenoh" else ("b", 0)
        cs = C.new_state(CONTRACT, session=OTHER, bound=F.HANDSHAKE_BOUND)

        def exchange(w: World, cs: C.ClientState, op: str, body: object) -> tuple[World, C.ClientState, object]:
            cs, frame = C.request(cs, op, body, features={LS.FEATURE: {}})
            w = dataclasses.replace(w, to_owner=put(w.to_owner, (key, frame)), other=True)
            entry = next((o for o in w.owners if o[0] == key), None)
            response = self.owner_step(w.clock, entry[1] if entry else O.OwnerState(), frame, w.openings)[1]
            w = self.owner_takes(w, w.to_owner.index((key, frame)))
            cs, verdict = C.receive(cs, response, lossy=False)
            return w, cs, verdict

        w, cs, opened = exchange(w, cs, "open", None)
        clock = opened.body["features"][LS.FEATURE]
        w, cs, took = exchange(w, cs, LS.TAKE, {"term": clock["term"]})
        if isinstance(took, C.Result):
            clock = took.body
            w, cs, _ = exchange(w, cs, "step", {"dx": 100, LS.TICK: {"tick": clock["tick"] + 1, "state": clock["state"]}})
        return w

    # ---- the search

    def successors(self, w: World) -> tuple[list[tuple[str, World]], int]:
        """The transitions from w, and how many of them, at the start of the list, are free: not
        faults."""
        out: list[tuple[str, World]] = []
        s = w.stepper
        if s.cs is not None and s.cs.pending is None and s.phase in ("open", "take", "step"):
            out.append((f"L sends {s.phase}", self.send(w)))
        for index in distinct(w.to_owner):
            out.append(("an owner takes a frame", self.owner_takes(w, index)))
        if s.cs is not None and s.cs.pending is not None:
            for index in distinct(w.to_client):
                frame, sender = w.to_client[index]
                after, verdict = C.receive(s.cs, frame, lossy=self.shape == "zenoh")
                nw = dataclasses.replace(w, to_client=drop(w.to_client, index))
                if verdict is None:
                    out.append(("L ignores a frame", dataclasses.replace(nw, stepper=dataclasses.replace(s, cs=after))))
                else:
                    out.append(("L takes a response", self.stable(self.react(nw, s.cs, after, verdict, sender))))
            after, result = C.time_out(s.cs, lossy=False, retries=0)
            nw = dataclasses.replace(w, timed=True)
            out.append(("a time limit", self.stable(self.react(nw, s.cs, after, result, -1))))
        free = len(out)
        if w.faults < self.budget:
            f = {"faults": w.faults + 1}
            for key, frame in w.sent:
                if self.shape == "zenoh":
                    out.append(("a copy of a frame", dataclasses.replace(w, to_owner=put(w.to_owner, (key, frame)), **f)))
                else:
                    for n in range(w.connections + 1):
                        moved = dataclasses.replace(w, to_owner=put(w.to_owner, (("r", n), frame)),
                                                    connections=max(w.connections, n + 1), **f)
                        out.append(("a copy of a frame on another connection", moved))
            for index in distinct(w.to_owner):
                out.append(("a request is lost", dataclasses.replace(w, to_owner=drop(w.to_owner, index), **f)))
            for index in distinct(w.to_client):
                out.append(("a response is lost", dataclasses.replace(w, to_client=drop(w.to_client, index), **f)))
            if self.shape == "zenoh":
                for index in range(len(w.owners)):
                    out.append(("a session expires", dataclasses.replace(w, owners=drop(w.owners, index), **f)))
            if not w.other:
                out.append(("another client takes the ticks and steps", self.other_client(dataclasses.replace(w, **f))))
            if w.owners:
                c = w.clock  # the restarted owner restores its tick, state, and request
                restarted = dataclasses.replace(w, owners=(), clock=(c[0], c[1], c[2], 0, None, c[5]), holder=None,
                                                stepper=dataclasses.replace(s, holds=False), **f)
                out.append(("the owner restarts", restarted))
                other_state = c[5] + 1000  # the same tick, but the application restored another state
                rewound = dataclasses.replace(restarted, rewound=True, current=(),
                                              history=((c[0], f"p{other_state}", "restored", other_state),),
                                              clock=(c[0], f"p{other_state}", "restored", 0, None, other_state))
                out.append(("the owner restarts with another state", rewound))
            if not w.rewound:
                # The application restores the state that it saved with an earlier clock, the
                # initial state included (profile, rule 5.7): the later steps are not in its state.
                for k in range(len(w.history) - 1):
                    tick, state, request, position = w.history[k]
                    older = dataclasses.replace(
                        w, owners=(), clock=(tick, state, request, 0, None, position), holder=None,
                        stepper=dataclasses.replace(s, holds=False), older=True,
                        current=w.current[:k], history=w.history[: k + 1], **f,
                    )
                    out.append(("the owner restarts to an earlier saved clock", older))
        return out, free

    def run(self) -> tuple[int, int]:
        cs = C.new_state(CONTRACT, session=IDS[0], bound=F.HANDSHAKE_BOUND)
        start = World(clock=(0, "p0", None, 0, None, 0), stepper=Stepper(cs=cs))
        seen = {start}
        parents: dict = {start: None}
        queue = deque([start])
        transitions = 0
        while queue:
            w = queue.popleft()
            try:
                successors, free = self.successors(w)
                if not w.faults and not w.timed and not free:
                    require(w.stepper.phase == "done" and len(w.ran) == STEPS, "progress",
                            f"L stopped in phase {w.stepper.phase} after {len(w.ran)} steps")
            except Violation as violation:
                trace, key = [], w
                while parents.get(key) is not None:
                    key, label = parents[key]
                    trace.append(label)
                raise Violation(violation.prop, f"{violation}\n  trace: " + " -> ".join(reversed(trace))) from None
            for label, nxt in successors:
                transitions += 1
                if nxt not in seen:
                    seen.add(nxt)
                    parents[nxt] = (w, label)
                    queue.append(nxt)
                    if len(seen) > self.limit:
                        raise Violation("bound", f"more than {self.limit} worlds; raise --max-worlds")
        return len(seen), transitions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--faults", type=int, default=1)
    parser.add_argument("--shape", choices=("stream", "zenoh", "both"), default="both")
    parser.add_argument("--same-session", action="store_true", help="one session identifier for all of L's sessions")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--max-worlds", type=int, default=LIMIT, help="stop with a message above this many worlds")
    args = parser.parse_args()
    shapes = ("stream", "zenoh") if args.shape == "both" else (args.shape,)
    if args.self_test:
        missed = 0
        for mutant in MUTANTS:
            found = None
            for same in (False, True):
                for shape in shapes:
                    try:
                        Search(shape, args.faults, mutant, same, args.max_worlds).run()
                    except Violation as violation:
                        found = (shape + (", one session identifier" if same else ""), violation)
                        break
                if found:
                    break
            if found:
                print(f"mutant {mutant:26s} caught by {found[1].prop} ({found[0]})")
            else:
                print(f"mutant {mutant:26s} MISSED")
                missed += 1
        print(f"self-test: {len(MUTANTS) - missed} of {len(MUTANTS)} known defects detected")
        return 1 if missed else 0
    total = 0
    for same in ((False, True) if not args.same_session else (True,)):
        for shape in shapes:
            started = time.monotonic()
            try:
                search = Search(shape, args.faults, None, same, args.max_worlds)
                worlds, transitions = search.run()
                print('   verdict events:', sorted(search.stats.items()))
            except Violation as violation:
                print(f"VIOLATION ({shape}{', one session identifier' if same else ''}) {violation}")
                return 1
            total += worlds
            label = f"{shape}, {'one session identifier' if same else 'new session identifiers'}"
            print(f"{label:38s} {worlds:9d} worlds {transitions:10d} transitions "
                  f"{time.monotonic() - started:6.1f} s: S1 to S6, L1, and progress hold")
    print(f"lockstep check: {total} reachable worlds with up to {args.faults} faults; every property holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
