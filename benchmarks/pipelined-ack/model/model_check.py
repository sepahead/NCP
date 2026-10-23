#!/usr/bin/env python3
"""Exhaustive explicit-state check of NCP local lockstep clients against the v1 owner.

The model has one client, one owner, and one FIFO channel in each direction, as with
the private process pipes of the local profile. It explores every interleaving of
client steps, owner steps, and faults up to a fault budget, and checks safety
properties in every reachable state.

Clients:
  sequential  v1: request, verified response, acknowledgement, verified acknowledgement.
  deferred    v1-compliant: sends the acknowledgement without waiting, and verifies
              its response before it sends the next request.
  pipelined   not v1: sends acknowledgement n and request n+1 back to back.

Faults (each costs one unit of the budget):
  corrupt     replace one in-flight frame by bytes that fail parsing or digests;
  wrong_ack   change the result identity of one in-flight acknowledgement to a valid
              but wrong value (a guard test: digests make this unreachable in practice);
  owner_crash the owner process dies; unread requests are lost, written responses stay
              readable until the client reads end of file;
  client_crash the client process dies;
  timeout     the client stops waiting and retires.

Properties:
  P1 at-most-once: the owner executes each sequence at most once.
  P2 order: the owner executes sequences 1, 2, ... without gaps.
  P3 acknowledged predecessor: the owner executes n+1 only after it accepted the
     acknowledgement of n with the result identity of n.
  P4 committed is true: a sequence that the client records as committed was executed
     exactly once, with the recorded result identity.
  P5 not-executed is true: a sequence that the client records as not executed was not
     executed.
  P6 v1 client rule: the client sends request n+1 only after it verified the response
     to acknowledgement n. The pipelined client breaks this rule by design.

Standard library only. Usage: model_check.py [--steps 3] [--faults 2] [--json OUT]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque

# Frames. Requests carry (sequence, request identity); acknowledgements carry
# (sequence, result identity). Responses carry (kind, sequence, outcome, code, result).
CORRUPT = ("corrupt",)


def result_id(sequence):
    return ("R", sequence)


WRONG = ("wrong",)

# Deliberate defects for the self-test. Each must produce its expected violation.
MUTANTS = {
    "owner_ignores_pending": "the owner executes a new sequence while a result is retained",
    "owner_accepts_wrong_ack": "the owner releases a result for any acknowledgement of its sequence",
    "client_unknown_as_not_executed": "a retiring client records dispatched requests as not executed",
}
ACTIVE = set()


# ---- owner: the v1 owner's admission rules for steps and acknowledgements ------------
# owner = (alive, high_water, retained, acknowledged)
#   retained / acknowledged = None or (sequence, result identity)
def owner_handle(owner, frame, ghost):
    alive, high, retained, acked = owner
    executed, accepted, order = ghost
    kind = frame[0]
    if kind == "req":
        _, seq = frame
        if retained is not None and "owner_ignores_pending" not in ACTIVE:
            if retained[0] == seq:
                return owner, ("resp", seq, "committed", "ok", retained[1]), ghost
            return owner, ("resp", seq, "rejected", "result_pending", None), ghost
        if seq <= high:
            return owner, ("resp", seq, "unavailable", "result_released", None), ghost
        if seq != high + 1:
            return owner, ("resp", seq, "rejected", "state", None), ghost
        # P3 ghost: the predecessor must be acknowledged with its own result identity.
        predecessor_ok = seq == 1 or (acked is not None and acked == (seq - 1, result_id(seq - 1)))
        executed = executed[:seq - 1] + (executed[seq - 1] + 1,) + executed[seq:]
        order = order + (seq,)
        ghost = (executed, accepted + ((seq, predecessor_ok),), order)
        owner = (alive, seq, (seq, result_id(seq)), acked)
        return owner, ("resp", seq, "committed", "ok", result_id(seq)), ghost
    if kind == "ack":
        _, seq, res = frame
        if retained is not None:
            if retained[0] != seq or (retained[1] != res and "owner_accepts_wrong_ack" not in ACTIVE):
                return owner, ("ackresp", seq, "rejected", "conflict", None), ghost
            # Record the identity that the acknowledgement carried; P3 compares it.
            return (alive, high, None, (seq, res)), ("ackresp", seq, "acknowledged", "ok", None), ghost
        if acked is not None and acked == (seq, res):
            return owner, ("ackresp", seq, "acknowledged", "ok", None), ghost
        return owner, ("ackresp", seq, "rejected", "conflict", None), ghost
    raise AssertionError(frame)


# ---- clients ---------------------------------------------------------------------------
# client = (variant, pc, seq, held, view, verified_acks)
#   pc: "send", "await_resp", "await_ack", "await_both", "await_ack_then_send", "done", "retired", "crashed"
#   held: result identity of the last committed step, to acknowledge
#   view: tuple per sequence: "none", "unknown", "committed:<res>", "not_executed"
#   verified_acks: frozenset of sequences whose acknowledgement response was verified

def set_view(view, seq, value):
    return view[:seq - 1] + (value,) + view[seq:]


def retire(client):
    variant, pc, seq, held, view, verified = client
    # Every dispatched sequence without a verified outcome is unknown.
    unknown = "not_executed" if "client_unknown_as_not_executed" in ACTIVE else "unknown"
    view = tuple(unknown if v == "sent" else v for v in view)
    return (variant, "retired", seq, held, view, verified)


def client_moves(client, c2o, o2c, owner, steps):
    """Yield (label, client, c2o, o2c, sent_requests) for each enabled client action."""
    variant, pc, seq, held, view, verified = client
    alive = owner[0]
    if pc == "send":
        # P6 ghost: record whether the predecessor's acknowledgement was verified.
        frames = (("req", seq),)
        if variant == "pipelined" and seq > 1 and held is not None:
            frames = (("ack", seq - 1, held), ("req", seq))
        new_view = set_view(view, seq, "sent")
        new_pc = "await_both" if len(frames) == 2 else "await_resp"
        yield ("send", (variant, new_pc, seq, held, new_view, verified), c2o + frames, o2c, frames)
        return
    if pc in ("await_resp", "await_ack", "await_both", "await_ack_then_send"):
        if o2c:
            frame, rest = o2c[0], o2c[1:]
            if frame == CORRUPT:
                yield ("read_corrupt", retire(client), c2o, rest, ())
                return
            yield from client_receive(client, frame, c2o, rest, steps)
        elif not alive:
            yield ("eof", retire(client), c2o, o2c, ())
        return


def client_receive(client, frame, c2o, rest, steps):
    variant, pc, seq, held, view, verified = client
    kind = frame[0]
    if pc == "await_resp":
        if kind != "resp" or frame[1] != seq:
            yield ("mismatch", retire(client), c2o, rest, ())
            return
        _, s, outcome, code, res = frame
        if outcome == "committed":
            view = set_view(view, s, "committed:" + repr(res))
            if variant == "sequential":
                yield ("resp", (variant, "await_ack", s, res, view, verified), c2o + (("ack", s, res),), rest, ())
            elif variant == "deferred":
                # Send the acknowledgement and return the result; verify the ack before the next request.
                nxt = "await_ack_then_send" if s < steps else "await_ack"
                yield ("resp", (variant, nxt, s, res, view, verified), c2o + (("ack", s, res),), rest, ())
            else:  # pipelined
                if s < steps:
                    yield ("resp", (variant, "send", s + 1, res, view, verified), c2o, rest, ())
                else:
                    yield ("resp", (variant, "await_ack", s, res, view, verified), c2o + (("ack", s, res),), rest, ())
        elif outcome in ("rejected",):
            view = set_view(view, s, "not_executed")
            yield ("reject", retire((variant, pc, s, held, view, verified)), c2o, rest, ())
        else:
            yield ("unavailable", retire(client), c2o, rest, ())
        return
    if pc in ("await_ack", "await_ack_then_send"):
        if kind != "ackresp" or frame[1] != seq:
            yield ("mismatch", retire(client), c2o, rest, ())
            return
        if frame[2] != "acknowledged":
            yield ("ack_rejected", retire(client), c2o, rest, ())
            return
        verified = verified | {seq}
        if pc == "await_ack_then_send" or (variant == "sequential" and seq < steps):
            yield ("ack", (variant, "send", seq + 1, None, view, verified), c2o, rest, ())
        else:
            yield ("ack", (variant, "done", seq, None, view, verified), c2o, rest, ())
        return
    if pc == "await_both":
        # The acknowledgement of seq-1 answers first, then the response to seq.
        if kind == "ackresp" and frame[1] == seq - 1:
            if frame[2] != "acknowledged":
                # The owner rejected the acknowledgement; the request behind it is pending.
                yield ("ack_rejected", (variant, "await_resp_after_rejected_ack", seq, held, view, verified),
                       c2o, rest, ())
                return
            yield ("ack", (variant, "await_resp", seq, None, view, verified | {seq - 1}), c2o, rest, ())
            return
        yield ("mismatch", retire(client), c2o, rest, ())


def client_moves_full(client, c2o, o2c, owner, steps):
    variant, pc, seq, held, view, verified = client
    if pc == "await_resp_after_rejected_ack":
        if o2c:
            frame, rest = o2c[0], o2c[1:]
            if frame == CORRUPT:
                yield ("read_corrupt", retire(client), c2o, rest, ())
                return
            if frame[0] == "resp" and frame[1] == seq and frame[2] == "rejected":
                view = set_view(view, seq, "not_executed")
                yield ("reject", retire((variant, pc, seq, held, view, verified)), c2o, rest, ())
            else:
                yield ("mismatch", retire(client), c2o, rest, ())
        elif not owner[0]:
            yield ("eof", retire(client), c2o, o2c, ())
        return
    yield from client_moves(client, c2o, o2c, owner, steps)


# ---- exploration -----------------------------------------------------------------------

def check(state, steps):
    client, owner, c2o, o2c, ghost, faults, p6 = state
    executed, accepted, order = ghost
    variant, pc, seq, held, view, verified = client
    failures = []
    if any(count > 1 for count in executed):
        failures.append("P1")
    if order != tuple(range(1, len(order) + 1)):
        failures.append("P2")
    if not all(ok for _, ok in accepted):
        failures.append("P3")
    for s in range(1, steps + 1):
        v = view[s - 1]
        if v.startswith("committed:") and (executed[s - 1] != 1 or v != "committed:" + repr(result_id(s))):
            failures.append("P4")
        if v == "not_executed" and executed[s - 1] != 0:
            failures.append("P5")
    if not p6:
        failures.append("P6")
    return failures


def successors(state, steps):
    client, owner, c2o, o2c, ghost, faults, p6 = state
    variant, pc, seq, held, view, verified = client
    out = []
    if pc not in ("done", "retired", "crashed"):
        for label, new_client, n_c2o, n_o2c, sent in client_moves_full(client, c2o, o2c, owner, steps):
            n_p6 = p6
            for frame in sent:
                if frame[0] == "req" and frame[1] > 1 and (frame[1] - 1) not in verified:
                    n_p6 = False
            out.append((label, (new_client, owner, n_c2o, n_o2c, ghost, faults, n_p6)))
    if owner[0] and c2o:
        frame, rest = c2o[0], c2o[1:]
        if frame == CORRUPT:
            # A frame that fails parsing or its digest ends the owner's serve loop.
            dead = (False,) + owner[1:]
            out.append(("owner_rejects_corrupt", (client, dead, (), o2c, ghost, faults, p6)))
        else:
            new_owner, reply, new_ghost = owner_handle(owner, frame, ghost)
            out.append(("owner", (client, new_owner, rest, o2c + (reply,), new_ghost, faults, p6)))
    if faults > 0:
        for i in range(len(c2o)):
            if c2o[i] != CORRUPT:
                out.append(("corrupt_c2o", (client, owner, c2o[:i] + (CORRUPT,) + c2o[i + 1:], o2c, ghost, faults - 1, p6)))
                if c2o[i][0] == "ack":
                    wrong = ("ack", c2o[i][1], WRONG)
                    out.append(("wrong_ack", (client, owner, c2o[:i] + (wrong,) + c2o[i + 1:], o2c, ghost, faults - 1, p6)))
        for i in range(len(o2c)):
            if o2c[i] != CORRUPT:
                out.append(("corrupt_o2c", (client, owner, c2o, o2c[:i] + (CORRUPT,) + o2c[i + 1:], ghost, faults - 1, p6)))
        if owner[0]:
            out.append(("owner_crash", (client, (False,) + owner[1:], (), o2c, ghost, faults - 1, p6)))
        if pc not in ("done", "retired", "crashed"):
            crashed = (variant, "crashed", seq, held, view, verified)
            out.append(("client_crash", (crashed, owner, c2o, o2c, ghost, faults - 1, p6)))
            if pc.startswith("await"):
                out.append(("timeout", (retire(client), owner, c2o, o2c, ghost, faults - 1, p6)))
    return out


def explore(variant, steps, faults):
    view = ("none",) * steps
    client = (variant, "send", 1, None, view, frozenset())
    owner = (True, 0, None, None)
    ghost = ((0,) * steps, (), ())
    start = (client, owner, (), (), ghost, faults, True)
    seen = {start}
    queue = deque([(start, ())])
    violations = {}
    terminal = 0
    completed = 0
    while queue:
        state, trace = queue.popleft()
        for prop in check(state, steps):
            violations.setdefault(prop, trace)
        moves = successors(state, steps)
        if not moves:
            terminal += 1
            if state[0][1] == "done":
                completed += 1
        for label, nxt in moves:
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, trace + (label,)))
    return {"variant": variant, "steps": steps, "faults": faults, "states": len(seen),
            "terminal_states": terminal, "completed_runs": completed,
            "violations": {k: list(v) for k, v in sorted(violations.items())}}


def self_test(steps, faults):
    """Each deliberate defect must be found; the unmodified model must stay clean for v1."""
    expected = {
        "owner_ignores_pending": "P3",
        "owner_accepts_wrong_ack": "P3",
        "client_unknown_as_not_executed": "P5",
    }
    report = {}
    for mutant, prop in expected.items():
        ACTIVE.clear()
        ACTIVE.add(mutant)
        found = {variant: sorted(explore(variant, steps, faults)["violations"])
                 for variant in ("sequential", "deferred", "pipelined")}
        ACTIVE.clear()
        caught = any(prop in props for props in found.values())
        report[mutant] = {"expected": prop, "found": found, "caught": caught}
        print(f"mutant {mutant:32} expected {prop}: {'caught' if caught else 'MISSED'} {found}")
        if not caught:
            sys.exit(f"self-test failed: {mutant} not detected")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--faults", type=int, default=2)
    parser.add_argument("--json", type=str)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        report = self_test(args.steps, args.faults)
        if args.json:
            open(args.json, "w").write(json.dumps(report, indent=1) + "\n")
        return
    results = []
    for variant in ("sequential", "deferred", "pipelined"):
        started = time.time()
        result = explore(variant, args.steps, args.faults)
        result["seconds"] = round(time.time() - started, 2)
        results.append(result)
        print(f"{variant:10} steps={args.steps} faults={args.faults} states={result['states']:>9} "
              f"completed={result['completed_runs']:>6} violations={sorted(result['violations'])} ({result['seconds']} s)")
    if args.json:
        open(args.json, "w").write(json.dumps(results, indent=1) + "\n")


if __name__ == "__main__":
    main()
