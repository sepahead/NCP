#!/usr/bin/env python3
"""Check that the real owners answer like the verified Lean model (spec/NCP-2.md, section 7.3).

Random traces of inputs drive several owners side by side. The inputs are requests before and after
`open` with every `open` verdict; correct, stale, missing, and foreign acknowledgements; stale,
repeated, and skipped sequence numbers; other sessions and protocol versions; invalid bodies,
failing and too large results, unknown operations, `ncp.ping`, and `close`; exact copies of earlier
requests, as a network repeats them; stops of the owner; and restarts of the owner, after which
copies of the requests of the earlier opening can still arrive.

For every input, all owners must give the same outcome and code. A response that the reference
gives again (the same identity) must come back as the identical bytes from each real owner. The
application of the Python owner records what it executes: no request may execute twice, across
restarts too (spec section 7.7, properties 1 and 2).

The owners:
  --oracle PATH      the compiled Lean model of ../formal (`ncp2-oracle`): the reference, whose
                     step function the Lean proofs cover
  the Python owner   `ncp.Owner`, always
  --owner PROGRAM    an external owner program with the command protocol of
                     rust/examples/model_owner.rs, which drives the Rust owner state machine

Without --oracle, the Python owner is the reference. The run fails if the traces do not reach every
code of section 7.5 that an owner sends.

With --self-test, the Python owner runs with each known defect of MUTANTS in turn, and the traces
must detect every defect.

Usage: conformance.py [--traces 20000] [--seed 20261023] [--oracle PATH] [--self-test]
                      [--owner PROGRAM ...]
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import logging
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "python"))

import ncp  # noqa: E402
from ncp import frame as F  # noqa: E402

logging.getLogger("ncp").addHandler(logging.NullHandler())
logging.getLogger("ncp").propagate = False

CONTRACT = ncp.Contract.from_bytes(
    b'{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}'
)
OTHER_CONTRACT = "0" * 64
SESSIONS = {1: "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b", 2: "1b2c3d4e-5f60-4718-9a2b-3c4d5e6f7a8b"}
OPEN_VERDICTS = ("accept", "body_invalid", "contract_mismatch", "bound_unacceptable", "refused")
OWNER_CODES = frozenset(
    {
        "wrong_protocol", "not_open", "already_open", "wrong_session", "seq_stale", "seq_gap", "seq_conflict",
        "ack_missing", "ack_mismatch", "unknown_op", "body_invalid", "contract_mismatch", "bound_unacceptable",
        "refused", "session_ended", "result_too_large", "owner_failure", "session_expired", "shutdown",
    }
)
ADMITTED_ENDINGS = frozenset({"owner_failure", "result_too_large"})


@dataclasses.dataclass(frozen=True)
class Req:
    """An abstract request. `ack` names which response it acknowledges: None, "last" (the last
    kept response), "stale" (the one before it), "first" (the first one of the trace), or "other"
    (an identity that no owner sent)."""

    seq: int
    op: str  # open | close | ping | step | unknown
    ack: str | None
    bad: bool = False
    fail: bool = False
    big: bool = False
    session: int = 1
    protocol: int = 2
    verdict: str = "accept"


class Handler:
    """The harness's application. Bad bodies are declined, failing ones raise, big ones return a
    result too large for the session, and a run named "refuse" is refused at open. It records the
    identity of each request that it executes, across restarts of the owner."""

    def __init__(self, decline: bool = True) -> None:
        self.decline = decline
        self.executed: set[str] = set()
        self.twice: list[str] = []

    def open(self, info):
        if info.run == "refuse":
            raise ncp.Refused("refused by the harness")
        return {}

    def validate(self, request):
        if self.decline and request.body.get("bad"):
            raise ncp.Declined("bad body")

    def execute(self, request):
        if request.identity in self.executed:
            self.twice.append(request.identity)
        self.executed.add(request.identity)
        if request.body.get("fail"):
            raise RuntimeError("injected failure")
        if request.body.get("big"):
            return {"blob": F.Array("u8", [70_000], bytes(70_000))}
        return {"seq": request.body["seq"]}


def frame_of(event: Req, ack: str | None) -> bytes:
    """The real request frame of an abstract request."""
    if event.op == "open":
        body: dict = {"application": "model", "contract": CONTRACT.identity, "bound": F.HANDSHAKE_BOUND}
        if event.verdict == "body_invalid":
            del body["bound"]
        elif event.verdict == "contract_mismatch":
            body["contract"] = OTHER_CONTRACT
        elif event.verdict == "bound_unacceptable":
            body["bound"] = 1000
        elif event.verdict == "refused":
            body["run"] = "refuse"
    else:
        body = {"seq": event.seq, "bad": event.bad, "fail": event.fail, "big": event.big}
    op = {"open": "open", "close": "close", "ping": "ncp.ping", "step": "step", "unknown": "missing"}[event.op]
    message = {"ncp": event.protocol, "session": SESSIONS[event.session], "seq": event.seq, "op": op, "ack": ack,
               "body": body}
    return F.encode(message)


class _Silent:
    def event(self, event) -> None:
        pass


class PythonOwner:
    """`ncp.Owner`, possibly with a known defect (see MUTANTS)."""

    def __init__(self, mutant: str | None = None) -> None:
        self.mutant = mutant
        self.reset()

    def reset(self) -> None:
        self.handler = Handler(decline=self.mutant != "ignores_invalid")
        self.restart()

    def restart(self) -> None:
        self.nonce = 0
        constant = self.mutant == "constant_nonce"
        self.owner = ncp.Owner(
            CONTRACT, self.handler, max_bound=F.HANDSHAKE_BOUND, observer=_Silent(),
            nonce=lambda: "0" * 32 if constant else f"{self.nonce:032x}",
        )

    def handle(self, event: Req, ack: str | None, nonce: int) -> bytes:
        self.nonce = nonce
        frame = frame_of(event, ack)
        state = self.owner.state
        m = self.mutant
        if m and state.session is not None and state.kept is not None:
            if m == "skips_ack_check" and event.seq == state.high + 1 and ack is not None:
                state = dataclasses.replace(state, kept=dataclasses.replace(state.kept, identity=ack))
            if m == "accepts_gaps" and event.seq > state.high + 1:
                state = dataclasses.replace(state, high=event.seq - 1)
            if m == "forgets_kept_request":
                state = dataclasses.replace(state, kept=dataclasses.replace(state.kept, request="0" * 64))
            if m == "executes_after_end":
                state = dataclasses.replace(state, ended=False)
        before = self.owner.state = state
        response = self.owner.handle(frame)
        message = F.decode(response, F.MAX_BOUND).message
        plain = {k: v for k, v in message.items() if k != "att"}
        if m == "reports_stale_as_gap" and message["code"] == "seq_stale":
            response = F.encode({**plain, "code": "seq_gap"})
        if m == "declined_not_kept" and message["outcome"] == "declined":
            self.owner.state = before
        if m == "expired_as_not_open" and message["code"] == "session_expired":
            response = F.encode({**plain, "outcome": "rejected", "code": "not_open"})
        return response

    def stop(self) -> None:
        if self.mutant != "ignores_stop":
            self.owner.stop()

    def check(self) -> None:
        if self.handler.twice:
            raise AssertionError(f"the Python owner executed request {self.handler.twice[0][:16]} twice")

    def close(self) -> None:
        pass


class ExternalOwner:
    """An owner program with the command protocol of rust/examples/model_owner.rs."""

    def __init__(self, argv: list[str]) -> None:
        self.name = os.path.basename(argv[0])
        self.process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _command(self, data: bytes) -> None:
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def _read(self, size: int) -> bytes:
        data = self.process.stdout.read(size)
        if len(data) != size:
            raise RuntimeError(f"{self.name} stopped")
        return data

    def reset(self) -> None:
        self._command(b"n")
        if self._read(1) != b"k":
            raise RuntimeError(f"{self.name} did not take a new owner")

    restart = reset

    def stop(self) -> None:
        self._command(b"s")
        if self._read(1) != b"k":
            raise RuntimeError(f"{self.name} did not take the stop")

    def handle(self, event: Req, ack: str | None, nonce: int) -> bytes:
        frame = frame_of(event, ack)
        self._command(b"r" + len(frame).to_bytes(4, "big") + frame)
        size = int.from_bytes(self._read(4), "big")
        if size == 0:
            raise RuntimeError(f"{self.name} did not take a request frame")
        return self._read(size)

    def check(self) -> None:
        pass

    def close(self) -> None:
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()


class LeanOracle:
    """The compiled Lean model."""

    def __init__(self, path: str) -> None:
        self.process = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def line(self, text: str) -> str:
        self.process.stdin.write(text + "\n")
        self.process.stdin.flush()
        reply = self.process.stdout.readline()
        if not reply:
            raise RuntimeError("the oracle stopped")
        return reply.strip()

    def _expect_dash(self, text: str) -> None:
        if self.line(text) != "-":
            raise RuntimeError(f"the oracle did not take {text!r}")

    def reset(self) -> None:
        self._expect_dash("reset")

    def restart(self) -> None:
        self._expect_dash("restart")

    def stop(self) -> None:
        self._expect_dash("stop")

    def handle(self, event: Req, ack: str | None, nonce: int) -> tuple[str, str | None, str | None]:
        reply = self.line(
            f"req {event.seq} {event.op} {'-' if ack is None else ack} {int(event.bad)} {int(event.fail)} "
            f"{int(event.big)} {event.session} {event.protocol} {nonce} {event.verdict}"
        ).split()
        if len(reply) != 3:
            raise RuntimeError(f"the oracle answered {reply!r}")
        outcome, code, identity = reply
        return outcome, None if code == "-" else code, None if identity == "-" else identity

    def check(self) -> None:
        pass

    def close(self) -> None:
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()


def answer(subject, event: Req, ack: str | None, nonce: int):
    """(outcome, code, identity, frame) of a subject's response; identity is None for a rejection."""
    if isinstance(subject, LeanOracle):
        outcome, code, identity = subject.handle(event, ack, nonce)
        return outcome, code, identity, None
    response = subject.handle(event, ack, nonce)
    message = F.decode(response, F.MAX_BOUND).message
    identity = None if message["outcome"] == "rejected" else F.identity(response)
    return message["outcome"], message["code"], identity, response


def resolve(choice: str | None, kept: list[str], lean: bool) -> str | None:
    """A subject's acknowledgement for an abstract choice, from its own kept identities."""
    if choice is None:
        return None
    if choice == "other":
        return "1" if lean else "1" * 64
    index = {"last": -1, "stale": -2, "first": 0}[choice]
    if (index < 0 and len(kept) >= -index) or (index >= 0 and len(kept) > index):
        return kept[index]
    return "0" if lean else "0" * 64


def generate(rng: random.Random, length: int, stops: bool) -> list[tuple]:
    """A random trace of ("req", Req, nonce), ("copy", k, nonce), ("stop",), and ("restart",)
    items. A copy repeats the k-th new request of the trace with the same bytes."""
    trace: list[tuple] = []
    new = 0
    seq, opened = 0, False  # what a correct client would send next, as the generator believes
    for _ in range(length):
        roll = rng.random()
        nonce = rng.getrandbits(64)
        if stops and roll < 0.03:
            trace.append(("stop",))
            continue
        if roll < 0.06:
            trace.append(("restart",))
            seq, opened = 0, False
            continue
        if new and roll < 0.22:
            k = new - 1 if rng.random() < 0.5 else rng.randrange(new)
            trace.append(("copy", k, nonce))
            continue
        if not opened:
            pick = rng.random()
            if pick < 0.08:
                event = Req(0, "step", None)  # not_open
            elif pick < 0.16:
                event = Req(rng.randint(1, 3), "step", "last")  # session_expired
            else:
                verdict = "accept" if rng.random() < 0.75 else rng.choice(OPEN_VERDICTS[1:])
                event = Req(0, "open", None, verdict=verdict)
                opened = verdict == "accept"
                seq = 1 if opened else 0
        else:
            ack: str | None = "last"
            current = seq
            op, bad, fail, big = "step", False, False, False
            session, protocol = 1, 2
            pick = rng.random()
            if pick < 0.06:
                bad = True
            elif pick < 0.10:
                fail = True
            elif pick < 0.13:
                big = True
            elif pick < 0.17:
                op = "unknown"
            elif pick < 0.21:
                op = "ping"
            elif pick < 0.24:
                op = "close"
            elif pick < 0.27:
                op = "open"
            elif pick < 0.31:
                current = seq + 1  # seq_gap
            elif pick < 0.35:
                ack = "stale"
            elif pick < 0.37:
                ack = "first"
            elif pick < 0.40:
                ack = None
            elif pick < 0.43:
                ack = "other"
            elif pick < 0.46:
                current = max(seq - 1, 0)  # seq_stale or seq_conflict
            elif pick < 0.49:
                session = 2
            elif pick < 0.51:
                protocol = 3
            event = Req(current, op, ack, bad, fail, big, session, protocol)
            if current == seq and ack == "last" and session == 1 and protocol == 2 and op != "open":
                seq += 1  # admitted, unless the owner ended or stopped; the reference decides
        trace.append(("req", event, nonce))
        new += 1
    return trace


def run_trace(trace: list[tuple], subjects: list) -> tuple[int, collections.Counter]:
    """Drive the subjects with one trace; the first is the reference. Return the number of inputs
    compared and the codes that the reference gave. Raise AssertionError on a difference."""
    for subject in subjects:
        subject.reset()
    codes: collections.Counter = collections.Counter()
    kept: list[list[str]] = [[] for _ in subjects]  # each subject's kept identities, in order
    seen: list[dict[str, bytes]] = [{} for _ in subjects]  # reference identity -> subject frame
    sent: list[tuple[Req, list[str | None]]] = []  # each new request, with each subject's ack
    compared = 0
    for index, item in enumerate(trace):
        if item[0] in ("stop", "restart"):
            for subject in subjects:
                getattr(subject, item[0])()
            continue
        if item[0] == "req":
            event = item[1]
            acks = [resolve(event.ack, kept[p], isinstance(s, LeanOracle)) for p, s in enumerate(subjects)]
            sent.append((event, acks))
        else:
            event, acks = sent[item[1]]
        nonce = item[2]
        results = [answer(s, event, acks[p], nonce) for p, s in enumerate(subjects)]
        for subject in subjects:
            subject.check()
        reference = results[0]
        for position, result in enumerate(results[1:], start=1):
            if result[:2] != reference[:2]:
                raise AssertionError(
                    f"input {index} {event}: reference {reference[:2]}, owner {position} {result[:2]}"
                )
        outcome, code, identity = reference[0], reference[1], reference[2]
        codes[code or outcome] += 1
        if identity is not None:
            for position, result in enumerate(results):
                frame = result[3]
                if frame is not None:
                    earlier = seen[position].setdefault(identity, frame)
                    if earlier != frame:
                        raise AssertionError(f"input {index} {event}: the same response came back as other bytes")
            if outcome in ("ok", "declined") or code in ADMITTED_ENDINGS:
                for position, result in enumerate(results):
                    if result[2] not in kept[position]:
                        kept[position].append(result[2])
        compared += 1
    return compared, codes


MUTANTS = (
    "skips_ack_check",
    "accepts_gaps",
    "forgets_kept_request",
    "executes_after_end",
    "reports_stale_as_gap",
    "declined_not_kept",
    "ignores_stop",
    "expired_as_not_open",
    "constant_nonce",
    "ignores_invalid",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--traces", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--oracle", default=None, help="the compiled Lean model (formal/.lake/build/bin/ncp2-oracle)")
    parser.add_argument("--self-test", action="store_true", help="require the traces to detect each known defect")
    parser.add_argument("--owner", nargs=argparse.REMAINDER, help="an external owner program and its arguments")
    args = parser.parse_args()

    def subjects_for(mutant: str | None = None) -> list:
        subjects: list = []
        if args.oracle:
            subjects.append(LeanOracle(args.oracle))
        elif mutant is not None:
            subjects.append(PythonOwner())
        subjects.append(PythonOwner(mutant))
        if args.owner:
            subjects.append(ExternalOwner(args.owner))
        return subjects

    def run(subjects: list, traces: int) -> tuple[int, collections.Counter, AssertionError | None]:
        rng = random.Random(args.seed)
        total, codes = 0, collections.Counter()
        try:
            for _ in range(traces):
                compared, reached = run_trace(generate(rng, rng.randint(1, 16), True), subjects)
                total += compared
                codes.update(reached)
        except AssertionError as error:
            return total, codes, error
        finally:
            for subject in subjects:
                subject.close()
        return total, codes, None

    if args.self_test:
        missed = []
        for mutant in MUTANTS:
            _, _, caught = run(subjects_for(mutant), args.traces)
            print(f"mutant {mutant:22s} {'caught: ' + str(caught)[:110] if caught else 'MISSED'}")
            if caught is None:
                missed.append(mutant)
        print(f"self-test: {len(MUTANTS) - len(missed)} of {len(MUTANTS)} known defects detected")
        return 1 if missed else 0
    total, codes, error = run(subjects_for(), args.traces)
    if error is not None:
        print(f"conformance: FAILED: {error}")
        return 1
    names = ["the Python owner"] + ([os.path.basename(args.owner[0])] if args.owner else [])
    reference = "the verified Lean model" if args.oracle else "the Python owner"
    print(f"conformance: {args.traces} traces, {total} requests; {' and '.join(names)} answer like {reference}; "
          f"no request executed twice; {len(codes)} outcomes and codes reached")
    missing = sorted(OWNER_CODES - codes.keys())
    if missing:
        print(f"the traces never reached: {', '.join(missing)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
