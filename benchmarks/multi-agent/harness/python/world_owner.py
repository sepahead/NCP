"""The world owner of part R of the multi-agent benchmark (../../PROTOCOL.md).

Usage: world_owner.py MODE PATH N
Serves N agents, agent-000 to agent-(N-1), one session each, on a Unix domain socket at PATH, and
prints "ready PATH". The world's state is a SHA-256 chain over the actions that it applied:

- rounds: ncp.Rounds (spec/NCP-2-ROUNDS.md). Each round applies the actions of all agents in
  member order: state = SHA-256(state + JSON of [[agent, action], ...]). Every agent receives
  the state after the round. The deadline is 60 s, so that no agent is excluded.
- arrival: each request is applied when it arrives, in the order in which the sessions' threads
  take the world's lock: state = SHA-256(state + JSON of [agent, action]). The agent receives
  the state after its own action.

On SIGTERM, prints one JSON line with the final state and, for rounds, how many rounds the
requests reached the owner in an order other than the member order, and exits.
"""

from __future__ import annotations

import hashlib
import json
import signal
import sys
import threading
from typing import Any

import ncp

WORLD = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"world","version":"1","operations":{"act":{}},"streams":{}}'
)
DEADLINE_S = 60.0


def compact(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def main() -> None:
    mode, path, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
    members = [f"agent-{i:03}" for i in range(n)]
    lock = threading.Lock()
    state = bytes(32)
    arrivals: dict[int, list[str]] = {}  # rounds: the order in which requests passed validation
    rounds_object: ncp.Rounds | None = None

    if mode == "rounds":

        def step(number: int, inputs: list[tuple[str, Any]]) -> dict[str, dict[str, Any]]:
            nonlocal state
            state = hashlib.sha256(state + compact([[agent, body["action"]] for agent, body in inputs])).digest()
            text = state.hex()
            return {agent: {"state": text} for agent, _ in inputs}

        rounds_object = ncp.Rounds("world", WORLD.identity, "act", members, step, deadline=DEADLINE_S)

        def make_owner() -> ncp.Owner:
            owner = rounds_object.owner()
            inner = owner.handler

            class Recording:
                def validate(self, op: str, body: Any) -> None:
                    inner.validate(op, body)
                    member = body["ncp.round"]
                    with lock:
                        arrivals.setdefault(member["round"], []).append(member["agent"])

                def execute(self, op: str, body: Any) -> Any:
                    return inner.execute(op, body)

            owner.handler = Recording()
            return owner

    elif mode == "arrival":

        class Shared:
            def validate(self, op: str, body: Any) -> None:
                if type(body) is not dict or body.keys() != {"agent", "round", "action"}:
                    raise ncp.BodyInvalid("agent, round, and action")

            def execute(self, op: str, body: Any) -> Any:
                nonlocal state
                with lock:
                    state = hashlib.sha256(state + compact([body["agent"], body["action"]])).digest()
                    return {"state": state.hex()}

        def make_owner() -> ncp.Owner:
            return ncp.Owner("world", WORLD.identity, Shared(), ["act"])

    else:
        raise SystemExit(f"unknown mode {mode}")

    server = ncp.UnixServer(make_owner, path).start()
    finished = threading.Event()
    signal.signal(signal.SIGTERM, lambda signum, frame: finished.set())
    print(f"ready {path}", flush=True)
    finished.wait()
    server.stop()
    with lock:
        report: dict[str, Any] = {"mode": mode, "n": n, "final_state": state.hex()}
        if rounds_object is not None:
            orders = [arrivals[k] for k in sorted(arrivals)]
            report.update(
                {
                    "rounds_closed": rounds_object.closed,
                    "excluded": sorted(rounds_object.excluded),
                    "rounds_out_of_member_order": sum(order != members for order in orders),
                    "rounds_recorded": len(orders),
                }
            )
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
