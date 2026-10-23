#!/usr/bin/env python3
"""Exhaustive explicit-state check of the NCP 2 exchange (spec/NCP-2.md, section 7).

One client and one owner exchange frames over one of two network models:

  stream   the byte-stream binding: one FIFO channel in each direction, no loss;
  message  the Zenoh binding: frames can be lost, repeated, and delivered in any order.

The search explores every interleaving of client steps, owner steps, and faults up to a fault
budget. In every reachable state it checks the properties of section 7.7:

  P1 at most once      the owner executes each sequence number at most once;
  P2 order             the owner executes 1, 2, ... without gaps;
  P3 acknowledged      the owner executes n only if the request names the identity of the
                       owner's response n - 1 (the open response for n = 1);
  P4 ok is true        a result that the client accepts is the owner's response to the client's
                       own request, from one execution;
  P5 rejected is true  a request that the client learns was rejected did not execute;
  P6 chain             each request whose result the client accepts names the identity of the
                       response that the client accepted before it;
  P7 end is final      the owner executes nothing after a response that ends the session.

P1, P2, P3, and P7 protect the owner and must hold for any client. P4 to P6 describe what a
correct client learns; they are checked in runs without client faults.

Faults (each costs one unit of the budget):
  network  drop or repeat one frame (message model); damage one frame, which the receiver
           drops (message model) or answers with bad_frame and a closed stream (stream model);
  process  owner crash; client crash; an application failure during one execution;
  client   a faulty client: sends a request with a stale acknowledgement, skips a sequence
           number, or continues after an ended response. These exercise the owner's checks.
The client may also send one invalid body, which the owner must reject without executing.

`--self-test` injects each known defect in turn and requires its property to fail.
Standard library only. Usage: ncp2_model.py [--steps 3] [--faults 2] [--network both]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque

# defect -> the property that must catch it
MUTANTS = {
    "owner_forgets_kept_response": "P5",
    "owner_skips_ack_check": "P3",
    "owner_accepts_gaps": "P2",
    "owner_executes_after_end": "P7",
    "client_skips_response_match": "P4",
}
ACTIVE: set[str] = set()
OPEN = ("r", 0)  # identity of the open response; the model starts after open


# Frames.
#   request:  ("q", seq, version, ack)   version 0 = valid body, "bad" = invalid body
#   response: ("p", seq, request, outcome, code, identity)
#   "x" = a damaged frame
# Owner: (alive, high, kept, ended, counter)   kept = (request, response)
# Client: (phase, seq, ack, outstanding, accepted, rejected, retries, sent_bad)
#   phase: ready | waiting | done | crashed | retired
# Ghost: (executed, ended_at, client_faulty)
#   executed: tuple of (seq, request, response identity, ack)
def owner_step(owner, request, ghost, may_fail):
    """Apply the rules of section 7.3. Return a list of (owner, response, ghost, used_fault)."""
    alive, high, kept, ended, counter = owner
    executed, ended_at, faulty = ghost
    _, seq, version, ack = request

    def reply(outcome, code, identity=None):
        return ("p", seq, request, outcome, code, identity)

    if kept is not None and seq == high:
        if kept[0] == request:
            if "owner_forgets_kept_response" not in ACTIVE:
                return [(owner, kept[1], ghost, False)]
        else:
            return [(owner, reply("rejected", "seq_conflict"), ghost, False)]
    if seq <= high and not ("owner_forgets_kept_response" in ACTIVE and kept and kept[0] == request):
        return [(owner, reply("rejected", "seq_stale"), ghost, False)]
    if seq > high + 1 and "owner_accepts_gaps" not in ACTIVE:
        return [(owner, reply("rejected", "seq_gap"), ghost, False)]
    if ended and "owner_executes_after_end" not in ACTIVE:
        return [(owner, reply("rejected", "session_ended"), ghost, False)]
    if "owner_skips_ack_check" not in ACTIVE:
        if ack is None:
            return [(owner, reply("rejected", "ack_missing"), ghost, False)]
        if kept is None or ack != kept[1][5]:
            return [(owner, reply("rejected", "ack_mismatch"), ghost, False)]
    if version == "bad":
        return [(owner, reply("rejected", "body_invalid"), ghost, False)]
    counter += 1
    identity = ("r", seq, counter)
    out = []
    for fails in (False, True) if may_fail else (False,):
        response = reply("ended", "owner_failure", identity) if fails else reply("ok", None, identity)
        now_ended = ended or fails
        new_ghost = (
            executed + ((seq, request, identity, ack),),
            ended_at if ended_at is not None else (len(executed) if now_ended else None),
            faulty,
        )
        out.append(((alive, seq, (request, response), now_ended, counter), response, new_ghost, fails))
    return out


def client_receive(client, response, ghost):
    """Apply the client rules of section 7.6 to one response."""
    phase, seq, ack, outstanding, accepted, rejected, retries, sent_bad = client
    if phase != "waiting":
        return client, ghost
    _, rseq, request, outcome, code, identity = response
    if "client_skips_response_match" in ACTIVE:
        matches = True
    else:
        matches = rseq == seq and request == outstanding
    if not matches:
        return client, ghost
    if outcome == "ok":
        return (
            "ready",
            seq,
            identity,
            None,
            accepted + ((seq, outstanding, identity),),
            rejected,
            retries,
            sent_bad,
        ), ghost
    if outcome == "rejected":
        # Rule 7.6.4: nothing changed at the owner. Return to the last accepted sequence number.
        base = accepted[-1][0] if accepted else 0
        known = tuple(sorted(set(rejected) | {outstanding}, key=repr))
        return ("ready", base, ack, None, accepted, known, retries, sent_bad), ghost
    return ("retired", seq, ack, None, accepted, rejected, retries, sent_bad), ghost


def check(state):
    owner, client, to_owner, to_client, ghost, budget = state
    executed, ended_at, faulty = ghost
    accepted, rejected = client[4], client[5]
    found = []
    seqs = [item[0] for item in executed]
    if len(set(seqs)) != len(seqs):
        found.append("P1")
    if seqs != list(range(1, len(seqs) + 1)):
        found.append("P2")
    response_of = {0: OPEN}
    for item in executed:
        response_of.setdefault(item[0], item[2])
    if any(ack != response_of.get(seq - 1) for seq, _, _, ack in executed):
        found.append("P3")
    if ended_at is not None and len(executed) > ended_at + 1:
        found.append("P7")
    if not faulty:
        executions = {(item[0], item[1]): item[2] for item in executed}
        if any(executions.get((seq, request)) != identity for seq, request, identity in accepted):
            found.append("P4")
        executed_requests = {item[1] for item in executed}
        if any(request in executed_requests for request in rejected):
            found.append("P5")
        chain = OPEN
        for _, request, identity in accepted:
            if request[3] != chain:
                found.append("P6")
                break
            chain = identity
    return found


def successors(state, steps, lossy):
    owner, client, to_owner, to_client, ghost, budget = state
    phase, seq, ack, outstanding, accepted, rejected, retries, sent_bad = client
    alive = owner[0]
    executed, ended_at, faulty = ghost
    out = []

    def put(queue, frame):
        return tuple(sorted(queue + (frame,), key=repr)) if lossy else queue + (frame,)

    def takes(queue):
        if lossy:
            return [
                (queue[i], queue[:i] + queue[i + 1 :]) for i in range(len(queue)) if i == 0 or queue[i] != queue[i - 1]
            ]
        return [(queue[0], queue[1:])] if queue else []

    def send(request, faulty_now=False, bad=sent_bad):
        new_client = ("waiting", request[1], ack, request, accepted, rejected, retries, bad)
        return (
            owner,
            new_client,
            put(to_owner, request),
            to_client,
            (executed, ended_at, faulty or faulty_now),
            budget - (1 if faulty_now else 0),
        )

    if phase == "ready":
        if seq < steps:
            out.append(send(("q", seq + 1, 0, ack)))
            if not sent_bad:
                out.append(send(("q", seq + 1, "bad", ack), bad=True))
            if budget > 0:
                out.append(send(("q", seq + 1, 0, accepted[-2][2] if len(accepted) >= 2 else None), True))
                out.append(send(("q", seq + 2, 0, ack), True))
        else:
            out.append((owner, ("done",) + client[1:], to_owner, to_client, ghost, budget))
    if phase == "waiting":
        if lossy and retries > 0:
            out.append(
                (owner, client[:6] + (retries - 1, sent_bad), put(to_owner, outstanding), to_client, ghost, budget)
            )
        out.append((owner, ("retired",) + client[1:], to_owner, to_client, ghost, budget))
    if alive:
        for frame, rest in takes(to_owner):
            if frame == "x":
                if lossy:
                    out.append((owner, client, rest, to_client, ghost, budget))
                else:
                    bad = ("p", None, None, "ended", "bad_frame", None)
                    out.append(((False,) + owner[1:], client, (), put(to_client, bad), ghost, budget))
                continue
            for new_owner, response, new_ghost, used in owner_step(owner, frame, ghost, budget > 0):
                out.append((new_owner, client, rest, put(to_client, response), new_ghost, budget - (1 if used else 0)))
    for frame, rest in takes(to_client):
        if frame == "x":
            out.append(
                (
                    owner,
                    client if lossy or phase != "waiting" else ("retired",) + client[1:],
                    to_owner,
                    rest,
                    ghost,
                    budget,
                )
            )
            continue
        if frame[4] == "bad_frame":
            out.append(
                (owner, ("retired",) + client[1:] if phase == "waiting" else client, to_owner, rest, ghost, budget)
            )
            continue
        if frame[3] == "ended" and phase == "waiting" and budget > 0 and frame[2] == outstanding:
            # Faulty client: treats an ended response as ok and continues.
            ignoring = ("ready", seq, frame[5], None, accepted, rejected, retries, sent_bad)
            out.append((owner, ignoring, to_owner, rest, (executed, ended_at, True), budget - 1))
        new_client, new_ghost = client_receive(client, frame, ghost)
        out.append((owner, new_client, to_owner, rest, new_ghost, budget))
    if budget > 0:
        for name, queue in (("o", to_owner), ("c", to_client)):
            for index, frame in enumerate(queue):
                if frame == "x":
                    continue
                variants = [queue[:index] + ("x",) + queue[index + 1 :]]
                if lossy:
                    variants = [
                        tuple(sorted(variants[0], key=repr)),
                        queue[:index] + queue[index + 1 :],
                        put(queue, frame),
                    ]
                for changed in variants:
                    out.append(
                        (
                            owner,
                            client,
                            changed if name == "o" else to_owner,
                            changed if name == "c" else to_client,
                            ghost,
                            budget - 1,
                        )
                    )
        if alive:
            out.append(((False,) + owner[1:], client, (), to_client, ghost, budget - 1))
        if phase in ("ready", "waiting"):
            out.append((owner, ("crashed",) + client[1:], to_owner, to_client, ghost, budget - 1))
    return out


def explore(steps, faults, network, limit=20_000_000, stop_on=None):
    lossy = network == "message"
    open_request = ("q", 0, 0, None)
    kept = (open_request, ("p", 0, open_request, "ok", None, OPEN))
    start = ((True, 0, kept, False, 0), ("ready", 0, OPEN, None, (), (), 2, False), (), (), ((), None, False), faults)
    seen = {start}
    queue = deque([start])
    violations: dict[str, int] = {}
    completed = 0
    while queue:
        state = queue.popleft()
        for violation in check(state):
            violations[violation] = violations.get(violation, 0) + 1
        if stop_on is not None and stop_on in violations:
            break  # a mutant run only has to show its expected violation
        client = state[1]
        if client[0] == "done" and not state[4][2] and len(client[4]) == steps:
            completed += 1
        for nxt in successors(state, steps, lossy):
            if nxt not in seen:
                if len(seen) >= limit:
                    raise RuntimeError("state limit reached")
                seen.add(nxt)
                queue.append(nxt)
    return {
        "network": network,
        "steps": steps,
        "faults": faults,
        "states": len(seen),
        "completed": completed,
        "violations": sorted(violations),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steps", type=int, default=3)
    parser.add_argument("--faults", type=int, default=2)
    parser.add_argument("--network", choices=("stream", "message", "both"), default="both")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json")
    args = parser.parse_args()
    networks = ("stream", "message") if args.network == "both" else (args.network,)
    report: dict = {"runs": [], "self_test": []}
    status = 0
    for network in networks:
        started = time.monotonic()
        result = explore(args.steps, args.faults, network)
        result["seconds"] = round(time.monotonic() - started, 2)
        report["runs"].append(result)
        print(
            f"{network:8s} steps={args.steps} faults={args.faults} states={result['states']:>9} "
            f"completed={result['completed']:>7} violations={result['violations']} ({result['seconds']} s)"
        )
        if result["violations"] or not result["completed"]:
            status = 1
    if args.self_test:
        for mutant, expected in MUTANTS.items():
            ACTIVE.clear()
            ACTIVE.add(mutant)
            found: set[str] = set()
            for network in networks:
                found.update(explore(args.steps, args.faults, network, stop_on=expected)["violations"])
                if expected in found:
                    break
            caught = expected in found
            status |= 0 if caught else 1
            print(f"mutant {mutant:30s} must fail {expected}: {'caught' if caught else 'MISSED'} {sorted(found)}")
            report["self_test"].append(
                {"mutant": mutant, "expected": expected, "found": sorted(found), "caught": caught}
            )
        ACTIVE.clear()
    if args.json:
        with open(args.json, "w") as handle:
            json.dump(report, handle, indent=1)
    return status


if __name__ == "__main__":
    sys.exit(main())
