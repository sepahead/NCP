#!/usr/bin/env python3
"""Exhaustive check of the reference client and owner over faulty networks (spec/NCP-2.md, 7.7).

The real state machines of the Python SDK exchange real frames: the client is `ncp.client`
(`request`, `receive`, `time_out`, `closed`) and the owner is `ncp.owner.step`. Nothing in this
file restates a protocol rule; it only moves frames and checks results. Two network models:

  message  the Zenoh binding: frames can be lost, repeated, delayed, and reordered, and the client
           sends a request again when its time limit expires;
  stream   a byte-stream binding: one FIFO stream in each direction; a fault breaks the
           connection, damages a frame (rule 9.1.3), or stops the owner (rule 9.1.9).

The search explores every interleaving of client steps, owner steps, time limits, and faults, up to
a fault budget. Faults: loss and repetition of any frame (message); a restart of the owner or the
expiry of its session, after which old copies can still arrive (message); a stop of the owner;
requests of a faulty client or of a second writer in the session: a sequence gap, a wrong
acknowledgement, another request with the next sequence number, a request after the end (message);
a broken connection and damaged frames (stream). The application declines bodies with
"bad", fails on "fail", and returns a result too large for the session on "big".

In every reachable state, the search checks the properties of section 7.7:

  P1 at most once      no request executes twice, and no request with seq > 0 is admitted twice,
                       also across openings;
  P2 in order          an opening admits seq 0, 1, 2, ... without gaps;
  P3 acknowledged      an admitted request names the identity of the response before it;
  P4 ok is true        an `ok` that the client accepts is the owner's response to the client's
                       own request, from one admission;
  P5 declined is final a request with a "not executed" verdict never executes or is admitted,
                       then or later; a stopped owner admits nothing until it restarts;
  P6 rejected          a `rejected` response changes no owner state and answers a request that
                       was not admitted (except seq_stale); the client gets `rejected` only for
                       `open`;
  P7 truthful          every verdict "executed" is true; "possibly executed" is the last verdict;
                       nothing is admitted after an exchange that ends the session;
  P8 one chain         every response names the identity of its request.

Runs without faults and without expired time limits must also make progress: the client gets the
verdicts that the application decides, for every call of its script.

`--self-test` injects each known defect of MUTANTS into the SDK machines in turn and requires the
search to find a violation. Usage: simulate.py [--faults 2] [--network both] [--self-test]
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
from ncp import messages as M  # noqa: E402
from ncp import owner as O  # noqa: E402

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}'
)
SESSION = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b"
RETRIES = 1

# name -> (the client's calls, the verdicts of a run without faults)
SCRIPTS: dict[str, tuple[tuple, tuple]] = {
    "calls": (
        (("open", None), ("step", {"n": 1}), ("step", {"bad": True}), ("close", {})),
        ("ok", "ok", "declined body_invalid", "ok"),
    ),
    "failure": ((("open", None), ("step", {"fail": True})), ("ok", "ended owner_failure")),
    "large": ((("open", None), ("step", {"big": True})), ("ok", "ended result_too_large")),
    "operations": (
        (("open", None), ("missing", {}), ("ncp.ping", {}), ("close", {})),
        ("ok", "declined unknown_op", "ok", "ok"),
    ),
}

# defect -> how it is injected (see Machines)
MUTANTS = (
    "owner_skips_ack_check",
    "owner_accepts_gaps",
    "owner_forgets_kept_request",
    "owner_executes_after_end",
    "owner_declined_not_kept",
    "owner_constant_nonce",
    "owner_ignores_stop",
    "client_skips_request_match",
    "client_timeout_not_executed",
    "client_trusts_session_expired",
    "client_trusts_rejected_call",
)


class Violation(Exception):
    def __init__(self, prop: str, text: str) -> None:
        super().__init__(f"{prop}: {text}")
        self.prop = prop


def require(condition: bool, prop: str, text: str) -> None:
    if not condition:
        raise Violation(prop, text)


class App:
    """The harness's application. It keeps no state: the world records what it executes."""

    def validate(self, request):
        if request.body.get("bad"):
            raise O.Declined("bad body")

    def execute(self, request):
        if request.body.get("fail"):
            raise RuntimeError("injected failure")
        if request.body.get("big"):
            return {"blob": F.Array("u8", [70_000], bytes(70_000))}
        return {"n": request.body.get("n")}


@dataclasses.dataclass(frozen=True)
class World:
    owner: O.OwnerState
    client: C.ClientState
    to_owner: tuple[bytes, ...]  # sorted (message) or in order (stream)
    to_client: tuple[bytes, ...]
    pos: int = 0  # calls of the script that the client has made
    openings: int = 0
    chain: tuple | None = None  # (seq, response identity, ends) of the last admission of this opening
    admitted: frozenset = frozenset()  # (request identity, seq, response identity, outcome, opening)
    executed: tuple[str, ...] = ()  # request identities, in the order the application executed them
    verdicts: tuple = ()  # (seq, op, request identity, kind, code, executed, response identity)
    faults: int = 0
    timed_out: bool = False
    stopped: bool = False  # the owner stopped once in this run
    halted: bool = False  # the owner stopped and has not restarted since
    conn: str = "open"  # stream: open, owner_closed, closed

    def key(self) -> tuple:
        o = self.owner
        kept = (o.kept.request, o.kept.identity) if o.kept else None
        return (o.session, o.high, kept, o.ended, o.stopping, o.nonce, self.client, self.to_owner, self.to_client,
                self.pos, self.openings, self.chain, self.admitted, self.executed, self.verdicts, self.faults,
                self.timed_out, self.stopped, self.halted, self.conn)


class Machines:
    """The SDK state machines, with at most one injected defect, and caches of their steps."""

    def __init__(self, mutant: str | None) -> None:
        self.mutant = mutant
        self.app = App()
        self.nonce = 0
        constant = mutant == "owner_constant_nonce"
        self.config = O.OwnerConfig(
            (CONTRACT,), max_bound=F.HANDSHAKE_BOUND, nonce=lambda: "0" * 32 if constant else f"{self.nonce:032x}"
        )
        self.owner_cache: dict = {}
        self.client_cache: dict = {}

    def owner_step(self, o: O.OwnerState, frame: bytes, openings: int):
        """(state before the step, state after, response, note, decoded request)."""
        cache_key = (o, frame, openings)
        hit = self.owner_cache.get(cache_key)
        if hit is not None:
            return hit
        decoded = F.decode(frame, o.bound)
        m, message = self.mutant, decoded.message
        before = o
        if o.session is not None and o.kept is not None:
            if m == "owner_skips_ack_check" and message["seq"] == o.high + 1 and message["ack"] is not None:
                before = dataclasses.replace(o, kept=dataclasses.replace(o.kept, identity=message["ack"]))
            elif m == "owner_accepts_gaps" and message["seq"] > o.high + 1:
                before = dataclasses.replace(o, high=message["seq"] - 1)
            elif m == "owner_forgets_kept_request":
                before = dataclasses.replace(o, kept=dataclasses.replace(o.kept, request="0" * 64))
            elif m == "owner_executes_after_end":
                before = dataclasses.replace(o, ended=False)
        if m == "owner_ignores_stop":
            before = dataclasses.replace(before, stopping=False)
        self.nonce = openings + 1
        after, response, note = O.step(self.config, before, decoded, self.app)
        if m == "owner_declined_not_kept" and F.decode(response, F.MAX_BOUND).message["outcome"] == "declined":
            after = before
        result = (before, after, response, note, decoded)
        self.owner_cache[cache_key] = result
        return result

    def client_receive(self, c: C.ClientState, frame: bytes, lossy: bool):
        cache_key = (c, frame, lossy)
        hit = self.client_cache.get(cache_key)
        if hit is not None:
            return hit
        state = c
        if self.mutant == "client_skips_request_match" and c.pending is not None:
            try:
                message = F.decode(frame, c.bound).message
                if message.get("session") == c.session and message.get("seq") == c.pending.seq:
                    state = dataclasses.replace(c, pending=dataclasses.replace(c.pending, identity=message["request"]))
            except F.FrameError:
                pass
        after, verdict = C.receive(state, frame, lossy=lossy)
        result = (after, verdict)
        self.client_cache[cache_key] = result
        return result

    def verdict_of(self, verdict) -> tuple[str, str | None, str | None, str | None]:
        """(kind, code, executed, response identity) of a client verdict."""
        if isinstance(verdict, C.Result):
            return "ok", None, "yes", verdict.identity
        if isinstance(verdict, O.Declined):
            return "declined", verdict.code, "no", None
        if isinstance(verdict, C.Rejected):
            return "rejected", verdict.code, None, None
        assert isinstance(verdict, C.Ended), verdict
        executed = verdict.executed.value
        if self.mutant == "client_timeout_not_executed" and verdict.code == "local.timeout":
            executed = "no"
        if self.mutant == "client_trusts_session_expired" and verdict.code == "session_expired":
            executed = "no"
        if self.mutant == "client_trusts_rejected_call" and verdict.detail == C.LOST_SESSION:
            executed = "no"  # the rule before revision 3: a rejected call ran nowhere
        return "ended", verdict.code, executed, None


def add(frames: tuple[bytes, ...], frame: bytes, ordered: bool) -> tuple[bytes, ...]:
    return frames + (frame,) if ordered else tuple(sorted(frames + (frame,)))


def without(frames: tuple[bytes, ...], index: int) -> tuple[bytes, ...]:
    return frames[:index] + frames[index + 1:]


def distinct(frames: tuple[bytes, ...]) -> list[int]:
    """The index of the first copy of each distinct frame."""
    first: dict[bytes, int] = {}
    for index, frame in enumerate(frames):
        first.setdefault(frame, index)
    return list(first.values())


class Search:
    def __init__(self, script: str, network: str, budget: int, mutant: str | None = None) -> None:
        self.calls, self.expected = SCRIPTS[script]
        self.network, self.budget = network, budget
        self.stream = network == "stream"
        self.m = Machines(mutant)

    def initial(self) -> World:
        client = C.new_state(CONTRACT, session=SESSION, bound=F.HANDSHAKE_BOUND)
        return World(O.OwnerState(), client, (), ())

    # The owner takes one frame.
    def owner_takes(self, w: World, index: int) -> World:
        frame = w.to_owner[index]
        before, after, response, note, decoded = self.m.owner_step(w.owner, frame, w.openings)
        request, request_id = decoded.message, decoded.identity
        message = F.decode(response, F.MAX_BOUND).message
        outcome, code = message["outcome"], message["code"]
        require(message["request"] == request_id, "P8", "a response that names another request")
        if outcome == "rejected":
            require(after == before, "P6", f"a {code} rejection changed the owner state")
            if w.chain is not None and code != "seq_stale":
                require(all(a[0] != request_id or a[4] != w.openings for a in w.admitted), "P6",
                        f"a {code} rejection of a request that this opening admitted")
        changes: dict = {"owner": after, "to_owner": without(w.to_owner, index),
                         "to_client": add(w.to_client, response, self.stream)}
        admitted = after.kept is not None and after.kept != before.kept
        if admitted:
            seq, response_id = request["seq"], F.identity(response)
            require(not w.halted, "P5", f"request {seq} admitted after the owner stopped")
            ends = outcome == "ended" or (request["op"] == "close" and outcome == "ok")
            if request["op"] == "open" and before.session is None:
                changes["openings"] = w.openings + 1
                changes["chain"] = (0, response_id, False)
            else:
                require(w.chain is not None, "P2", "an admission without an opening")
                last_seq, last_response, ended = w.chain
                require(not ended, "P7", f"request {seq} admitted after the session ended")
                require(seq == last_seq + 1, "P2", f"request {seq} admitted after request {last_seq}")
                require(request["ack"] == last_response, "P3", f"request {seq} admitted with a wrong acknowledgement")
                changes["chain"] = (seq, response_id, ends)
            if seq > 0:
                require(all(a[0] != request_id for a in w.admitted), "P1", f"request {seq} admitted twice")
            if outcome != "declined":
                for v in w.verdicts:
                    require(not (v[2] == request_id and v[5] == "no"), "P5",
                            f"request {seq} admitted after the verdict 'not executed'")
            opening = changes.get("openings", w.openings)
            changes["admitted"] = w.admitted | {(request_id, seq, response_id, outcome, opening)}
        if note.executed:
            require(request_id not in w.executed, "P1", f"request {request['seq']} executed twice")
            for v in w.verdicts:
                require(not (v[2] == request_id and v[5] == "no"), "P5",
                        f"request {request['seq']} executed after the verdict 'not executed'")
            changes["executed"] = w.executed + (request_id,)
        return dataclasses.replace(w, **changes)

    # The client reaches a verdict on its outstanding request.
    def verdict(self, w: World, before: C.ClientState, after: C.ClientState, verdict, changes: dict) -> World:
        pending = before.pending
        kind, code, executed, response_id = self.m.verdict_of(verdict)
        admissions = [a for a in w.admitted if a[0] == pending.identity]
        if kind == "rejected":  # the owner side of P6 is checked where the owner rejects
            require(pending.op == "open", "P6", f"the client got {code} for {pending.op}")
        if kind == "ok":
            require(any(a[2] == response_id and a[3] == "ok" for a in admissions), "P4",
                    f"the client accepted an ok that is not the owner's response to its {pending.op}")
        if executed == "yes":
            require(any(a[3] != "declined" for a in admissions), "P7", f"'executed' for {pending.op}, not admitted")
            if pending.op not in ("open", "close", "ncp.ping"):
                require(pending.identity in w.executed, "P7", f"'executed' for {pending.op}, not executed")
        if executed == "no":
            require(all(a[3] == "declined" for a in admissions) and pending.identity not in w.executed, "P5",
                    f"'not executed' ({code}) for {pending.op}, which the owner admitted or executed")
        if executed == "unknown":
            require(after.ended, "P7", "'possibly executed' that is not the last verdict")
        entry = (pending.seq, pending.op, pending.identity, kind, code, executed, response_id)
        return dataclasses.replace(w, client=after, verdicts=w.verdicts + (entry,), **changes)

    def client_takes(self, w: World, index: int) -> World:
        frame = w.to_client[index]
        after, verdict = self.m.client_receive(w.client, frame, not self.stream)
        changes = {"to_client": without(w.to_client, index)}
        if verdict is None:
            return dataclasses.replace(w, client=after, **changes)
        return self.verdict(w, w.client, after, verdict, changes)

    def successors(self, w: World) -> list[tuple[str, World]]:
        out: list[tuple[str, World]] = []
        c = w.client
        if self.can_call(w):
            op, body = self.calls[w.pos]
            after, frame = C.request(c, op, body)
            out.append((f"send {op}", dataclasses.replace(
                w, client=after, to_owner=add(w.to_owner, frame, self.stream), pos=w.pos + 1)))
        owner_choices = ([0] if w.to_owner else []) if self.stream else distinct(w.to_owner)
        for index in owner_choices:
            out.append(("owner", self.owner_takes(w, index)))
        client_choices = ([0] if w.to_client else []) if self.stream else distinct(w.to_client)
        for index in client_choices:
            out.append(("client", self.client_takes(w, index)))
        if c.pending is not None and w.conn == "open":
            after, result = C.time_out(c, lossy=not self.stream, retries=RETRIES)
            if isinstance(result, bytes):
                out.append(("time limit, send again", dataclasses.replace(
                    w, client=after, to_owner=add(w.to_owner, result, self.stream), timed_out=True)))
            elif result is not None:
                out.append(("time limit", self.verdict(w, c, after, result, {"timed_out": True})))
        if self.stream and w.conn == "owner_closed" and not w.to_client:
            after, result = C.closed(c, "end of stream")
            changes = {"conn": "closed"}
            if result is None:
                out.append(("end of stream", dataclasses.replace(w, client=after, **changes)))
            else:
                out.append(("end of stream", self.verdict(w, c, after, result, changes)))
        if w.faults < self.budget:
            out.extend(self.faults(w))
        return out

    def can_call(self, w: World) -> bool:
        """Whether the client makes its next call now: one at a time, and none after an `open`
        that failed or after the end."""
        c = w.client
        return (c.pending is None and not c.ended and w.pos < len(self.calls) and w.conn == "open"
                and (w.pos == 0 or c.opened))

    def faults(self, w: World) -> list[tuple[str, World]]:
        out: list[tuple[str, World]] = []
        fault = w.faults + 1
        c = w.client
        if self.stream:
            if w.conn != "open":
                return out
            after, result = C.closed(c, "connection broken")
            broken = {"to_owner": (), "to_client": (), "conn": "closed", "faults": fault}
            if result is None:
                out.append(("connection broken", dataclasses.replace(w, client=after, **broken)))
            else:
                out.append(("connection broken", self.verdict(w, c, after, result, broken)))
            if w.to_owner:  # rule 9.1.3: the owner answers a damaged frame with bad_frame and closes
                out.append(("request damaged", dataclasses.replace(
                    w, to_owner=(), to_client=w.to_client + (M.bad_frame_response(key=None),),
                    conn="owner_closed", faults=fault)))
            if w.to_client:
                after, result = self.m.client_receive(c, b"\x00" * 16, False)
                damaged = {"to_client": w.to_client[1:], "to_owner": (), "conn": "closed", "faults": fault}
                if result is None:
                    out.append(("response damaged", dataclasses.replace(w, client=after, **damaged)))
                else:
                    out.append(("response damaged", self.verdict(w, c, after, result, damaged)))
            if not w.stopped:  # rule 9.1.9: answer what was read, send shutdown, close
                out.append(("owner stops", dataclasses.replace(
                    w, to_owner=(), to_client=w.to_client + (M.shutdown_response(key=None),),
                    conn="owner_closed", stopped=True, faults=fault)))
            return out
        for index in distinct(w.to_owner):
            out.append(("request lost", dataclasses.replace(w, to_owner=without(w.to_owner, index), faults=fault)))
            out.append(("request repeated", dataclasses.replace(
                w, to_owner=add(w.to_owner, w.to_owner[index], False), faults=fault)))
        for index in distinct(w.to_client):
            out.append(("response lost", dataclasses.replace(w, to_client=without(w.to_client, index), faults=fault)))
            out.append(("response repeated", dataclasses.replace(
                w, to_client=add(w.to_client, w.to_client[index], False), faults=fault)))
        if w.owner.session is not None:
            out.append(("owner restarts or the session expires", dataclasses.replace(
                w, owner=O.OwnerState(), chain=None, halted=False, faults=fault)))
        if not w.stopped:
            out.append(("owner stops", dataclasses.replace(
                w, owner=dataclasses.replace(w.owner, stopping=True), stopped=True, halted=True, faults=fault)))
        if c.opened:
            rogue = []
            if c.ended:
                rogue.append(("request after the end", c.seq + 1, c.ack))
            else:
                rogue.append(("request with a sequence gap", c.seq + 2, c.ack))
                rogue.append(("request with a wrong acknowledgement", c.seq + 1, "0" * 64))
                rogue.append(("another request with the next sequence number", c.seq + 1, c.ack))
            for label, seq, ack in rogue:
                frame = F.encode({"ncp": 2, "session": c.session, "seq": seq, "op": "step", "ack": ack,
                                  "body": {"n": 99}})
                out.append((label, dataclasses.replace(w, to_owner=add(w.to_owner, frame, False), faults=fault)))
        return out

    def check_progress(self, w: World) -> None:
        if w.faults or w.timed_out:
            return
        c = w.client
        if c.pending is None and not self.can_call(w) and not w.to_owner and not w.to_client:
            got = tuple(v[3] if v[4] is None else f"{v[3]} {v[4]}" for v in w.verdicts)
            require(got == self.expected, "progress", f"verdicts {got}, expected {self.expected}")

    def run(self) -> tuple[int, int]:
        """Explore every reachable world. Return (worlds, transitions); raise Violation with a trace."""
        start = self.initial()
        seen = {start.key(): None}
        parents: dict = {start.key(): None}
        queue = deque([start])
        transitions = 0
        while queue:
            w = queue.popleft()
            try:
                self.check_progress(w)
                successors = self.successors(w)
            except Violation as violation:
                raise Violation(violation.prop, f"{violation}\n{self.trace(parents, w.key())}") from None
            for label, nxt in successors:
                transitions += 1
                k = nxt.key()
                if k not in seen:
                    seen[k] = None
                    parents[k] = (w.key(), label)
                    queue.append(nxt)
        return len(seen), transitions

    @staticmethod
    def trace(parents: dict, key: tuple) -> str:
        steps = []
        while parents.get(key) is not None:
            key, label = parents[key]
            steps.append(label)
        return "  trace: " + " -> ".join(reversed(steps) or ["start"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--faults", type=int, default=2, help="the fault budget of each run")
    parser.add_argument("--network", choices=("message", "stream", "both"), default="both")
    parser.add_argument("--script", choices=tuple(SCRIPTS) + ("all",), default="all")
    parser.add_argument("--self-test", action="store_true", help="require a violation for each known defect")
    args = parser.parse_args()
    networks = ("message", "stream") if args.network == "both" else (args.network,)
    scripts = tuple(SCRIPTS) if args.script == "all" else (args.script,)
    if args.self_test:
        missed = []
        for mutant in MUTANTS:
            found = None
            for network in networks:
                for script in scripts:
                    try:
                        Search(script, network, args.faults, mutant).run()
                    except Violation as violation:
                        found = (network, script, violation)
                        break
                if found:
                    break
            if found:
                network, script, violation = found
                print(f"mutant {mutant:32s} caught by {violation.prop} ({network}, {script})")
            else:
                print(f"mutant {mutant:32s} MISSED")
                missed.append(mutant)
        print(f"self-test: {len(MUTANTS) - len(missed)} of {len(MUTANTS)} known defects detected")
        return 1 if missed else 0
    total = 0
    for network in networks:
        for script in scripts:
            started = time.monotonic()
            try:
                worlds, transitions = Search(script, network, args.faults).run()
            except Violation as violation:
                print(f"VIOLATION ({network}, {script}) {violation}")
                return 1
            total += worlds
            print(f"{network:7s} {script:10s} {worlds:8d} worlds {transitions:9d} transitions "
                  f"{time.monotonic() - started:6.1f} s: P1 to P8 and progress hold")
    print(f"model check: {total} reachable worlds with up to {args.faults} faults; every property holds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
