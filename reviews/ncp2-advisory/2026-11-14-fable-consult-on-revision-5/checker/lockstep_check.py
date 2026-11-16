#!/usr/bin/env python3
"""Prototype of an exhaustive bounded check of the lockstep profile (advisory consult, revision 5).

It follows model/simulate.py: the real SDK machines exchange real frames, and this file only moves
frames and checks results. The owner side is `ncp.owner.step` with the real `ncp.Lockstep` handler;
the handler's clock is copied into the world before each step and read back after it. The client
side is the pure machine of `ncp.client`; the verdict of a recovery comes from the real
`LockstepClient.recover`, given the clock that the exchange returned.

  one stepping client L:  open, (take,) step, step; after a step that is possibly executed, or a
                          declined step or take, it opens a new session (at most SESSIONS).
  shapes   stream  one owner for each connection; a copy of a frame arrives on a new connection
           zenoh   one owner for each session identifier; copies go to the service
  free     delay and reordering of every frame, and the client's time limit
  faults   a copy of any frame that L sent; loss of a frame; expiry of a session (zenoh);
           a restart of the owner that keeps its clock

Properties:
  S1 truthful   a step with the verdict "not executed" never executes; "executed" is true
  S2 holder     a step executes only in the opening that took the ticks last
  S3 ticks      the executed steps produce the ticks 1, 2, 3, ... once each
  S4 verdict    a recovery that completes gives a verdict (one stepping client, clock kept)
  L1 stable     while L's current session holds the ticks, no other frame takes them
  progress      without faults and time limits, L finishes its script

Usage: lockstep_check.py SDK_DIR --profile 3|4 [--shape stream|zenoh|both] [--faults N]
                         [--mutant NAME] [--reuse-session] [--self-test]
"""
from __future__ import annotations
import argparse, dataclasses, sys, time, types
from collections import deque

parser = argparse.ArgumentParser()
parser.add_argument("sdk"); parser.add_argument("--profile", type=int, choices=(3, 4), required=True)
parser.add_argument("--shape", choices=("stream", "zenoh", "both"), default="both")
parser.add_argument("--faults", type=int, default=1); parser.add_argument("--mutant", default=None)
parser.add_argument("--steps", type=int, default=2); parser.add_argument("--sessions", type=int, default=3)
parser.add_argument("--reuse-session", action="store_true"); parser.add_argument("--self-test", action="store_true")
parser.add_argument("--no-l1", action="store_true", help="do not check L1 (profile 3 loses it by design)")
parser.add_argument("--max-worlds", type=int, default=2_000_000, help="stop with a message above this many worlds")
ARGS = parser.parse_args()
sys.path.insert(0, ARGS.sdk); sys.dont_write_bytecode = True
import ncp
from ncp import client as C, frame as F, owner as O, lockstep as LS

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}')
IDS = [f"6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a{n:02x}" for n in range(8)]
FEATURE, TAKE = "ncp.lockstep", "ncp.lockstep.take"
MUTANTS = {3: ("holder_by_session", "constant_nonce", "verdict_ignores_request"),
           4: ("holder_by_session", "constant_nonce", "takeover_in_open", "take_without_term",
               "verdict_from_open_report", "verdict_ignores_request")}

class Violation(Exception):
    def __init__(self, prop, text): super().__init__(f"{prop}: {text}"); self.prop = prop
def require(ok, prop, text):
    if not ok: raise Violation(prop, text)

class App:
    position = 0
    def validate(self, request): pass
    def execute(self, request):
        self.position += request.body["dx"]; return {"position": self.position}
    def state(self): return f"p{self.position}"

class BySession:
    """Mutant: the holder is a session identifier (the SDKs of revision 4)."""
    def __init__(self, inner): self.inner = inner
    def open(self, info): return self.inner.open(dataclasses.replace(info, nonce=info.session))
    def validate(self, r): self.inner.validate(dataclasses.replace(r, nonce=r.session))
    def execute(self, r): return self.inner.execute(dataclasses.replace(r, nonce=r.session))

@dataclasses.dataclass(frozen=True)
class Cl:  # the stepping client's program
    phase: str = "open"            # open, take, step, done, stuck
    si: int = 0                    # index of its current session
    cs: C.ClientState | None = None
    base: tuple | None = None      # (tick, state) that the next step answers
    li: int = 0                    # index of the next logical step
    uncertain: tuple | None = None # (tick, identity, li) of a step that is possibly executed
    term: int | None = None
    attempts: int = 0
    holds: bool = False            # it accepted the takeover of its current session
    opening: int | None = None     # ghost: the opening of its current session
    report: tuple | None = None    # profile 4: the clock of the open response

@dataclasses.dataclass(frozen=True)
class World:
    clock: tuple                   # tick, state, request, holder, term, position
    owners: tuple = ()             # sorted (key, OwnerState, opening)
    to_owner: tuple = ()           # sorted (key, frame)
    to_client: tuple = ()          # sorted frames for L's current session
    cl: Cl = Cl()
    sent: tuple = ()               # sorted (key, frame): every frame that L sent
    openings: int = 0
    opened: tuple = ()             # ghost: (identity of an open response, opening)
    holder: int | None = None      # ghost: the opening that took the ticks last
    executed: tuple = ()           # identities of executed steps, in order
    verdicts: tuple = ()           # (identity, "yes" | "no")
    faults: int = 0
    timed: bool = False
    replays: int = 0
    others: int = 0                # steps of another stepping client (a fault)

def put(items, item): return tuple(sorted(items + (item,)))
def drop(items, index): return items[:index] + items[index + 1:]
def distinct(items):
    first = {}
    for i, item in enumerate(items): first.setdefault(item, i)
    return list(first.values())

class Search:
    def __init__(self, profile, shape, budget, mutant=None, reuse=False):
        self.p, self.shape, self.budget, self.mutant, self.reuse = profile, shape, budget, mutant, reuse
        self.app = App(); self.core = ncp.Lockstep(self.app, ["step"])
        self.handler = BySession(self.core) if mutant == "holder_by_session" else self.core
        self.nonce = 0
        self.config = O.OwnerConfig((CONTRACT,), max_bound=F.HANDSHAKE_BOUND,
            nonce=lambda: "0" * 32 if mutant == "constant_nonce" else f"{self.nonce:032x}")
        self.cache = {}

    # ---- the owner side
    def owner_step(self, clock, state, frame, openings):
        key = (clock, state, frame, openings)
        hit = self.cache.get(key)
        if hit is None:
            core, app = self.core, self.app
            core.tick, core.state, core.request, core.holder = clock[0], clock[1], clock[2], clock[3]
            if self.p == 4: core.term = clock[4]
            app.position = clock[5]
            self.nonce = openings + 1
            decoded = F.decode(frame, state.bound)
            before_term = clock[4]
            if self.mutant == "take_without_term" and decoded.message.get("op") == TAKE:
                body = decoded.message["body"]
                if type(body) is dict and type(body.get("term")) is int: core.term = body["term"]
            after, response, note = O.step(self.config, state, decoded, self.handler)
            term = getattr(core, "term", 0)
            if self.mutant == "take_without_term" and decoded.message.get("op") == TAKE:
                term = before_term + (1 if F.decode(response, F.MAX_BOUND).message["outcome"] == "ok" else 0)
            holder = core.holder
            message = F.decode(response, F.MAX_BOUND).message
            took = False
            if decoded.message.get("op") == "open" and state.session is None and after.session is not None:
                if self.p == 3 or self.mutant == "takeover_in_open":
                    took, holder = True, after.nonce if self.mutant != "holder_by_session" else after.session
            # A copy of an admitted take gets the kept response (rule 7.3.5): it takes nothing.
            if decoded.message.get("op") == TAKE and message["outcome"] == "ok" and note.kind == "admitted":
                took = True
            hit = (after, response, note, decoded, message,
                   (core.tick, core.state, core.request, holder, term, app.position), took)
            self.cache[key] = hit
        return hit

    def owner_takes(self, w, index):
        key, frame = w.to_owner[index]
        entry = next((o for o in w.owners if o[0] == key), None)
        state, opening = (entry[1], entry[2]) if entry else (O.OwnerState(), None)
        after, response, note, decoded, message, clock, took = self.owner_step(w.clock, state, frame, w.openings)
        request = decoded.message
        ch = {"to_owner": drop(w.to_owner, index), "clock": clock}
        if state.session is None and after.session is not None:      # an opening
            opening = w.openings + 1
            ch["openings"] = opening
            ch["opened"] = w.opened + ((F.identity(response), opening),)
        owners = tuple(o for o in w.owners if o[0] != key)
        if after.session is not None:
            owners = tuple(sorted(owners + ((key, after, opening),), key=lambda o: o[0]))
        ch["owners"] = owners
        holder = opening if took else w.holder
        ch["holder"] = holder
        if note.executed and request["op"] == "step":
            ident = decoded.identity
            require(w.holder == opening, "S2", f"a step ran in opening {opening}; opening {w.holder} took the ticks last")
            require(all(not (v[0] == ident and v[1] == "no") for v in w.verdicts), "S1",
                    "a step ran after the verdict 'not executed'")
            require(ident not in w.executed, "S3", "a step ran twice")
            require(clock[0] == len(w.executed) + 1, "S3", "the tick does not count the executed steps")
            ch["executed"] = w.executed + (ident,)
        cl = w.cl
        if cl.cs is not None and key == self.key_of(cl.si) and cl.cs.pending is not None:
            ch["to_client"] = put(w.to_client, response)
        nw = dataclasses.replace(w, **ch)
        self.stable(nw)
        return nw

    def stable(self, w):
        if ARGS.no_l1 or w.others: return
        cl = w.cl
        # Only while the owner still holds L's opening: a restart or an expiry loses it by rule.
        if cl.holds and cl.phase in ("step", "done") and any(o[2] == cl.opening for o in w.owners):
            require(w.holder == cl.opening, "L1",
                    f"opening {w.holder} took the ticks from L's current opening {cl.opening}")

    # ---- the client side
    def key_of(self, si):
        return ("s", IDS[0 if self.reuse else si]) if self.shape == "zenoh" else ("c", si)

    def fresh(self, cl, **more):
        """L leaves its session and opens the next one, if it has one left."""
        si = cl.si + 1
        if si >= ARGS.sessions:
            return dataclasses.replace(cl, phase="stuck", cs=None, holds=False, **more)
        cs = C.new_state(CONTRACT, session=IDS[0 if self.reuse else si], bound=F.HANDSHAKE_BOUND)
        return dataclasses.replace(cl, phase="open", si=si, cs=cs, holds=False, opening=None, attempts=0, **more)

    def send(self, w):
        cl = w.cl
        if cl.phase == "open":
            cs, frame = C.request(cl.cs, "open", None, features={FEATURE: {}})
        elif cl.phase == "take":
            cs, frame = C.request(cl.cs, TAKE, {"term": cl.term})
        else:
            body = {"dx": cl.li + 1, "ncp.tick": {"tick": cl.base[0] + 1, "state": cl.base[1]}}
            cs, frame = C.request(cl.cs, "step", body)
        item = (self.key_of(cl.si), frame)
        return dataclasses.replace(w, cl=dataclasses.replace(cl, cs=cs), to_owner=put(w.to_owner, item),
                                   sent=tuple(sorted(set(w.sent) | {item})))

    def recovered(self, w, cl, clock):
        """The verdict of the real LockstepClient.recover for the clock that the takeover returned."""
        tick, state, request, term = clock
        if cl.uncertain is None:
            return w, dataclasses.replace(cl, base=(tick, state), phase="step", holds=True)
        u, ident, li = cl.uncertain
        shell = object.__new__(ncp.LockstepClient)
        shell.client, shell.tick, shell.state, shell.uncertain = None, cl.base[0], cl.base[1], (u, ident)
        if self.mutant == "verdict_ignores_request":
            request = ident if tick == u else request
        enabled = {"tick": tick, "state": state, "request": request}
        if self.p == 4: enabled["term"] = term - 1
        fake = types.SimpleNamespace(opened=True, enabled={FEATURE: enabled},
            call=lambda op, body: types.SimpleNamespace(body={"tick": tick, "state": state, "request": request, "term": term}))
        try:
            verdict = shell.recover(fake).value
        except ncp.ProtocolError as error:
            if w.others:  # another client stepped: no verdict is the truthful answer (profile, 6.3)
                return w, dataclasses.replace(cl, phase="stuck", cs=None, holds=False)
            raise Violation("S4", f"the recovery gave no verdict: {error}") from None
        if verdict == "yes":
            require(ident in w.executed, "S1", "'executed' for a step that did not run")
        else:
            require(ident not in w.executed, "S1", "'not executed' for a step that ran")
        w = dataclasses.replace(w, verdicts=w.verdicts + ((ident, verdict),))
        return w, dataclasses.replace(cl, base=(tick, state), li=li + (verdict == "yes"), uncertain=None,
                                      phase="step", holds=True)

    def react(self, w, before, after, verdict):
        """L's program after the verdict of its outstanding request."""
        cl = dataclasses.replace(w.cl, cs=after)
        op, ident = before.pending.op, before.pending.identity
        if op == "open":
            if not isinstance(verdict, C.Result):
                return dataclasses.replace(w, cl=self.fresh(cl), to_client=())
            opening = max((o for r, o in w.opened if r == verdict.identity), default=None)
            report = verdict.body.get("features", {}).get(FEATURE)
            clock = (report["tick"], report["state"], report["request"], report.get("term"))
            cl = dataclasses.replace(cl, opening=opening)
            if self.p == 3:
                w, cl = self.recovered(w, cl, clock)
            elif self.mutant == "verdict_from_open_report" and cl.uncertain is not None:
                w, cl = self.recovered(w, cl, clock[:3] + (clock[3] + 1,))
                cl = dataclasses.replace(cl, phase="take", term=clock[3], holds=False)
            else:
                cl = dataclasses.replace(cl, phase="take", term=clock[3])
            return dataclasses.replace(w, cl=cl)
        if op == TAKE:
            if isinstance(verdict, C.Result):
                b = verdict.body
                w, cl = self.recovered(w, cl, (b["tick"], b["state"], b["request"], b["term"]))
                return dataclasses.replace(w, cl=cl)
            if isinstance(verdict, O.Declined):
                moved = verdict.body.get(FEATURE, {}).get("term") if type(verdict.body) is dict else None
                if type(moved) is int and cl.attempts + 1 < 3:
                    return dataclasses.replace(w, cl=dataclasses.replace(cl, term=moved, attempts=cl.attempts + 1))
            return dataclasses.replace(w, cl=self.fresh(cl), to_client=())
        # a step
        if isinstance(verdict, C.Result):
            member = verdict.body[LS.TICK]
            require(ident in w.executed, "S1", "an ok for a step that did not run")
            cl = dataclasses.replace(cl, base=(member["tick"], member["state"]), li=cl.li + 1)
            if cl.li >= ARGS.steps: cl = dataclasses.replace(cl, phase="done")
            return dataclasses.replace(w, cl=cl, verdicts=w.verdicts + ((ident, "yes"),))
        if isinstance(verdict, O.Declined) or (isinstance(verdict, C.Ended) and verdict.executed.value == "no"):
            require(ident not in w.executed, "S1", "'not executed' for a step that ran")
            return dataclasses.replace(w, cl=self.fresh(cl), to_client=(), verdicts=w.verdicts + ((ident, "no"),))
        assert isinstance(verdict, C.Ended) and verdict.executed.value == "unknown", verdict
        return dataclasses.replace(w, cl=self.fresh(cl, uncertain=(cl.base[0] + 1, ident, cl.li)), to_client=())

    def successors(self, w):
        out = []
        cl = w.cl
        lossy = self.shape == "zenoh"
        if cl.cs is not None and cl.cs.pending is None and cl.phase in ("open", "take", "step"):
            out.append((f"L sends {cl.phase}", self.send(w)))
        for index in distinct(w.to_owner):
            out.append(("owner", self.owner_takes(w, index)))
        if cl.cs is not None and cl.cs.pending is not None:
            for index in distinct(w.to_client):
                after, verdict = C.receive(cl.cs, w.to_client[index], lossy=lossy)
                nw = dataclasses.replace(w, to_client=drop(w.to_client, index))
                if verdict is None:
                    out.append(("L ignores a frame", dataclasses.replace(nw, cl=dataclasses.replace(cl, cs=after))))
                else:
                    nw = self.react(nw, cl.cs, after, verdict); self.stable(nw)
                    out.append(("L takes a response", nw))
            after, result = C.time_out(cl.cs, lossy=False, retries=0)
            nw = self.react(dataclasses.replace(w, timed=True), cl.cs, after, result); self.stable(nw)
            out.append(("time limit", nw))
        if w.faults < self.budget:
            f = {"faults": w.faults + 1}
            for key, frame in w.sent:
                targets = [key] if self.shape == "zenoh" else [("r", n) for n in range(w.replays + 1)]
                for target in targets:
                    more = {"replays": max(w.replays, target[1] + 1)} if self.shape == "stream" else {}
                    out.append(("a copy of a frame", dataclasses.replace(w, to_owner=put(w.to_owner, (target, frame)), **f, **more)))
            for index in distinct(w.to_owner):
                out.append(("a request is lost", dataclasses.replace(w, to_owner=drop(w.to_owner, index), **f)))
            for index in distinct(w.to_client):
                out.append(("a response is lost", dataclasses.replace(w, to_client=drop(w.to_client, index), **f)))
            if self.shape == "zenoh":
                for index in range(len(w.owners)):
                    out.append(("a session expires", dataclasses.replace(w, owners=drop(w.owners, index), **f)))
            if not w.others:
                out.append(("another client takes the ticks and steps once", self.other(dataclasses.replace(w, **f))))
            if w.owners:
                c = w.clock
                out.append(("the owner restarts with its clock", dataclasses.replace(
                    w, owners=(), clock=(c[0], c[1], c[2], None, c[4], c[5]), holder=None,
                    cl=dataclasses.replace(cl, holds=False), **f)))
        return out

    def other(self, w):
        """Another client B: its own session; it opens, takes the ticks, and steps once."""
        key = ("s", IDS[7]) if self.shape == "zenoh" else ("b", 0)
        cs = C.new_state(CONTRACT, session=IDS[7], bound=F.HANDSHAKE_BOUND)
        def exchange(w, cs, op, body):
            cs, frame = C.request(cs, op, body, features={FEATURE: {}})
            entry = next((o for o in w.owners if o[0] == key), None)
            state = entry[1] if entry else O.OwnerState()
            response = self.owner_step(w.clock, state, frame, w.openings)[1]
            w = dataclasses.replace(w, to_owner=put(w.to_owner, (key, frame)))
            w = self.owner_takes(dataclasses.replace(w, others=1), w.to_owner.index((key, frame)))
            cs, verdict = C.receive(cs, response, lossy=False)
            return w, cs, verdict
        w, cs, opened = exchange(w, cs, "open", None)
        clock = opened.body["features"][FEATURE]
        if self.p == 4:
            w, cs, took = exchange(w, cs, TAKE, {"term": clock["term"]})
            clock = took.body
        w, cs, _ = exchange(w, cs, "step", {"dx": 100, "ncp.tick": {"tick": clock["tick"] + 1, "state": clock["state"]}})
        return w

    def run(self):
        cs = C.new_state(CONTRACT, session=IDS[0], bound=F.HANDSHAKE_BOUND)
        start = World(clock=(0, None, None, None, 0, 0), cl=Cl(cs=cs))
        seen, parents, queue, transitions = {start}, {start: None}, deque([start]), 0
        while queue:
            w = queue.popleft()
            try:
                successors = self.successors(w)
                if not w.faults and not w.timed and not successors:
                    require(w.cl.phase == "done" and len(w.executed) == ARGS.steps, "progress",
                            f"L stopped in phase {w.cl.phase} after {len(w.executed)} steps")
            except Violation as v:
                steps, key = [], w
                while parents.get(key) is not None:
                    key, label = parents[key]; steps.append(label)
                raise Violation(v.prop, f"{v}\n  trace: " + " -> ".join(reversed(steps))) from None
            for label, nxt in successors:
                transitions += 1
                if nxt not in seen:
                    seen.add(nxt); parents[nxt] = (w, label); queue.append(nxt)
                    if len(seen) > ARGS.max_worlds:
                        raise Violation("bound", f"more than {ARGS.max_worlds} worlds; {len(queue)} still to explore")
        return len(seen), transitions

def main():
    shapes = ("stream", "zenoh") if ARGS.shape == "both" else (ARGS.shape,)
    if ARGS.self_test:
        missed = 0
        for mutant in MUTANTS[ARGS.profile]:
            found = None
            for shape, reuse in [(sh, r) for r in (False, True) for sh in shapes]:
                if reuse and shape == "zenoh" and ARGS.profile == 3:
                    continue  # finding R1: revision 3 of the profile is not safe there without a mutant
                try: Search(ARGS.profile, shape, ARGS.faults, mutant, reuse).run()
                except Violation as v: found = (shape + (", same session identifier" if reuse else ""), v); break
            if found: print(f"mutant {mutant:26s} caught by {found[1].prop} ({found[0]}): {str(found[1]).splitlines()[0][:90]}")
            else: print(f"mutant {mutant:26s} MISSED"); missed += 1
        print(f"self-test: {len(MUTANTS[ARGS.profile]) - missed} of {len(MUTANTS[ARGS.profile])} detected"); return 1 if missed else 0
    total = 0
    for shape in shapes:
        started = time.monotonic()
        try: worlds, transitions = Search(ARGS.profile, shape, ARGS.faults, ARGS.mutant, ARGS.reuse_session).run()
        except Violation as v:
            print(f"VIOLATION ({shape}) {v}"); return 1
        total += worlds
        print(f"{shape:6s} {worlds:9d} worlds {transitions:10d} transitions {time.monotonic() - started:6.1f} s: every property holds")
    print(f"lockstep check, profile revision {ARGS.profile}: {total} worlds with up to {ARGS.faults} faults"); return 0

if __name__ == "__main__":
    sys.exit(main())
