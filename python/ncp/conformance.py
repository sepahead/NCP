"""Run the conformance vectors of spec/NCP-2.md (section 14).

The SDK's tests run every part against this SDK. `python -m ncp conformance` runs the frames
against another implementation's decoder and the owner scenarios against its owner program.

A decoder program is called as `DECODER CORPUS`. The corpus holds entries of a 4-byte big-endian
bound, a 4-byte big-endian length, and that many frame bytes. The program prints one line of JSON
for each entry: {"ok": false} for a bad frame, or {"ok": true, "identity": ..., "message": ...,
"arrays": [hex, ...]} with arrays as {"ncp.array": {...}} in the message.

An owner program serves one session on standard input and output (rule 9.1.4) for the contract
and handler of the vectors' "contract" and "handler" members.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from typing import Any

from . import client as C
from . import contract as K
from . import frame as F
from . import transcript as T
from .binding import ChannelClosed, spawn
from .contract import Contract, ContractError
from .frame import FrameError
from .messages import check_request, check_response, check_stream_message, foreign
from .owner import Declined, Owner, Request
from .stream import Subscriber

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vectors.json")
_KEPT_ENDED = frozenset({"owner_failure", "result_too_large"})


def load(path: str | None = None) -> dict[str, Any]:
    with open(path or _PATH, encoding="utf-8") as handle:
        return json.load(handle)


def plain(value: Any, decoded: F.Decoded) -> Any:
    """A decoded message with each array as its reference object."""
    if isinstance(value, F.Array):
        index = next(i for i, item in enumerate(decoded.arrays) if item is value)  # not by equal content
        return {"ncp.array": {"dtype": value.dtype, "shape": list(value.shape), "att": index}}
    if isinstance(value, dict):
        return {k: plain(v, decoded) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v, decoded) for v in value]
    return value


def same(a: Any, b: Any) -> bool:
    """JSON equality that keeps integers and other numbers apart, and -0.0 apart from 0.0."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, float):
        return a == b and (a != 0 or str(a) == str(b))
    return a == b


class VectorHandler:
    """The handler that the vectors' "handler" member describes."""

    def __init__(self) -> None:
        self.flaky_seen = False

    def validate(self, request: Request) -> None:
        body = request.body
        if request.op == "step" and isinstance(body, dict) and body.get("invalid") is True:
            raise Declined("invalid")
        if request.op == "flaky" and not self.flaky_seen:
            self.flaky_seen = True
            raise Declined("the first validation declines")

    def execute(self, request: Request) -> Any:
        if request.op == "fail":
            raise RuntimeError("fail")
        if request.op == "big":
            return {"blob": "z" * request.body["size"]}
        return {"echo": request.body}


def _body(value: Any) -> Any:
    if isinstance(value, dict):
        if value.keys() == {"array", "values"}:
            code, size, _ = F.DTYPES[value["array"]]
            data = b"".join(struct.pack(code, v) for v in value["values"])
            return F.Array(value["array"], [len(value["values"])], data)
        return {k: _body(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_body(v) for v in value]
    return value


def _kept(message: dict[str, Any]) -> bool:
    return message["outcome"] in ("ok", "declined") or (
        message["outcome"] == "ended" and message["code"] in _KEPT_ENDED
    )


def frame_bytes(value: Any) -> bytes:
    """A frame of the vectors: hexadecimal, or {"parts": [[HEX, COUNT], ...]}, the bytes of each
    HEX repeated COUNT times, in order (conformance/generate.py stores large frames so)."""
    if type(value) is str:
        return bytes.fromhex(value)
    return b"".join(bytes.fromhex(part) * count for part, count in value["parts"])


# ---------------------------------------------------------------- parts of the vectors


def run_frames(vectors: dict[str, Any], decode: Callable[[bytes, int], Any]) -> list[str]:
    """`decode(frame, bound)` returns a dict like a decoder program's line."""
    failures = []
    for case in vectors["frames"]:
        result = decode(frame_bytes(case["frame"]), case["bound"])
        if not case["valid"]:
            if result.get("ok"):
                failures.append(f"frame {case['name']!r}: accepted, must be a bad frame")
            continue
        if not result.get("ok"):
            failures.append(f"frame {case['name']!r}: rejected ({result.get('error', '')})")
        elif not (
            ("message" not in case or same(result["message"], case["message"]))
            and result["identity"] == case["identity"]
            and result["arrays"] == case["arrays"]
        ):
            failures.append(f"frame {case['name']!r}: decoded to another message, identity, or arrays")
    return failures


def python_decode(frame: bytes, bound: int) -> dict[str, Any]:
    try:
        decoded = F.decode(frame, bound)
    except FrameError as error:
        return {"ok": False, "error": str(error)}
    return {
        "ok": True,
        "identity": decoded.identity,
        "message": plain(decoded.message, decoded),
        "arrays": [bytes(item.data).hex() for item in decoded.arrays],
    }


def program_decoder(argv: list[str]) -> Callable[[bytes, int], dict[str, Any]]:
    """A `decode` function that batches nothing: it runs the program once for each call. Use
    `run_frames_with_program` to run all frames in one call."""

    def decode(frame: bytes, bound: int) -> dict[str, Any]:
        return decode_with_program(argv, [(frame, bound)])[0]

    return decode


def decode_with_program(argv: list[str], cases: list[tuple[bytes, int]]) -> list[dict[str, Any]]:
    with tempfile.NamedTemporaryFile(suffix=".corpus", delete=False) as handle:
        for frame, bound in cases:
            handle.write(struct.pack(">II", bound, len(frame)) + frame)
        corpus = handle.name
    try:
        output = subprocess.run([*argv, corpus], capture_output=True, check=True).stdout
    finally:
        os.unlink(corpus)
    lines = output.decode("utf-8").split("\n")[:-1]  # not splitlines: U+2028 may appear in strings
    if len(lines) != len(cases):
        raise RuntimeError(f"the decoder printed {len(lines)} lines for {len(cases)} frames")
    return [json.loads(line) for line in lines]


def run_frames_with_program(vectors: dict[str, Any], argv: list[str]) -> list[str]:
    cases = [(frame_bytes(case["frame"]), case["bound"]) for case in vectors["frames"]]
    results = iter(decode_with_program(argv, cases))
    return run_frames(vectors, lambda frame, bound: next(results))


def run_messages(vectors: dict[str, Any]) -> list[str]:
    def check_foreign(message: dict[str, Any]) -> None:
        if not foreign(message):
            raise FrameError("not a request of another protocol version")

    checks = {
        "request": check_request,
        "response": check_response,
        "stream": check_stream_message,
        "foreign": check_foreign,
    }
    failures = []
    for case in vectors["messages"]:
        message = F.decode(frame_bytes(case["frame"]), F.MAX_BOUND).message
        try:
            checks[case["kind"]](message)
            accepted = True
        except FrameError:
            accepted = False
        if accepted != case["valid"]:
            failures.append(f"message {case['name']!r}: {'accepted' if accepted else 'refused'}")
    return failures


def run_auth(vectors: dict[str, Any]) -> list[str]:
    key = bytes.fromhex(vectors["key"])
    failures = []
    for case in vectors["auth"]:
        frame = frame_bytes(case["frame"])
        for with_key, expected in ((True, case["valid_with_key"]), (False, case["valid_without_key"])):
            try:
                decoded = F.decode(frame, F.MAX_BOUND, key=key if with_key else None)
                ok = True
            except FrameError:
                ok = False
            if ok != expected:
                failures.append(f"auth {case['name']!r} {'with' if with_key else 'without'} the key: {ok}")
            elif ok and decoded.identity != case["identity"]:
                failures.append(f"auth {case['name']!r}: another identity")
    return failures


OwnerFactory = Callable[[bool], tuple[Callable[[bytes], bytes], Callable[[], None] | None, Callable[[], None]]]


class _Silent:
    """The scenarios make the application fail on purpose; those failures are not news."""

    def event(self, event: Any) -> None:
        pass


def python_owner(vectors: dict[str, Any]) -> OwnerFactory:
    """Owners of this SDK for the scenarios: (handle, stop, close) for a new owner."""
    contract = Contract.from_bytes(vectors["contract"].encode("utf-8"))

    def make(stopping: bool) -> tuple[Callable[[bytes], bytes], Callable[[], None] | None, Callable[[], None]]:
        owner = Owner(contract, VectorHandler(), max_bound=F.HANDSHAKE_BOUND, observer=_Silent())
        if stopping:
            owner.stop()
        return owner.handle, owner.stop, lambda: None

    return make


def program_owner(argv: list[str]) -> OwnerFactory:
    """Owner programs for the scenarios: a new process for each new owner. A program offers no
    stop through the binding's frames, so scenarios that need one are skipped."""

    def make(stopping: bool) -> tuple[Callable[[bytes], bytes], Callable[[], None] | None, Callable[[], None]]:
        channel = spawn(argv, grace=2.0)

        def handle(frame: bytes) -> bytes:
            channel.send(frame)
            try:
                return channel.receive(F.MAX_BOUND, 10.0)
            except (ChannelClosed, OSError) as error:
                raise RuntimeError(f"the owner program closed or did not answer: {error}") from error

        return handle, None, channel.close

    return make


def run_scenarios(vectors: dict[str, Any], make_owner: OwnerFactory) -> tuple[list[str], int]:
    """Return the failures and the number of scenarios skipped for lack of an interface."""
    contract_id = vectors["contract_identity"]
    failures: list[str] = []
    skipped = 0
    for scenario in vectors["scenarios"]:
        handle, stop, close = make_owner(False)
        if scenario.get("api") and stop is None:
            close()
            skipped += 1
            continue
        try:
            failures += _scenario(vectors, scenario, contract_id, handle, stop, make_owner)
        finally:
            close()
    return failures, skipped


def _scenario(
    vectors: dict[str, Any],
    scenario: dict[str, Any],
    contract_id: str,
    handle: Callable[[bytes], bytes],
    stop: Callable[[], None] | None,
    make_owner: OwnerFactory,
) -> list[str]:
    failures = []
    history: list[str] = []
    frames: list[bytes | None] = []
    responses: list[bytes | None] = []
    for index, step in enumerate(scenario["steps"]):
        name = f"scenario {scenario['name']!r} step {index}"
        if "stop" in step:
            assert stop is not None
            stop()
            frames.append(None)
            responses.append(None)
            continue
        if "owner" in step:
            handle, stop, _ = make_owner(step["owner"] == "stopping")
            history = []
            frames.append(None)
            responses.append(None)
            continue
        if "repeat" in step:
            frame = frames[step["repeat"]]
            assert frame is not None
        else:
            if "open" in step:
                spec = step["open"]
                body = {
                    "application": spec.get("application", "conformance"),
                    "contract": spec.get("contract", contract_id),
                    "bound": spec.get("bound"),
                }
                body.pop(spec.get("omit", ""), None)
                for member in ("run", "features", "extra"):
                    if member in spec:
                        body[member] = spec[member]
            else:
                body = _body(step.get("body", {}))
            ack = {
                "last": history[-1] if history else None,
                "stale": history[-2] if len(history) > 1 else None,
                "none": None,
                "other": "0" * 64,
            }[step["ack"]]
            session = vectors["session"] if step.get("session") != "other" else str(uuid.uuid4())
            request = {"ncp": step.get("ncp", 2), "session": session, "seq": step["seq"], "op": step["op"], "ack": ack, "body": body}
            for member in step.get("drop", ()):
                del request[member]
            request.update(step.get("extra", {}))
            frame = F.encode(request)
        response = handle(frame)
        message = F.decode(response, F.MAX_BOUND).message
        observed = [message["outcome"], message["code"]]
        if observed != step["expect"]:
            failures.append(f"{name}: expected {step['expect']}, observed {observed}")
        if "repeat" in step:
            original = responses[step["repeat"]]
            assert original is not None
            first = F.decode(original, F.MAX_BOUND).message
            if _kept(first) and [first["outcome"], first["code"]] == step["expect"] and response != original:
                failures.append(f"{name}: a copy of an admitted request got other bytes")
        if "open_bound" in step and message["body"].get("bound") != step["open_bound"]:
            failures.append(f"{name}: open bound {message['body'].get('bound')}")
        if "open_features" in step and message["body"].get("features") != step["open_features"]:
            failures.append(f"{name}: open features {message['body'].get('features')}")
        for member in step.get("body_has", ()):
            if member not in message["body"]:
                failures.append(f"{name}: the body has no member {member!r}")
        if message["outcome"] == "ok" and step.get("op") == "open":
            nonce = message["body"].get("nonce")
            if not (isinstance(nonce, str) and len(nonce) == 32):
                failures.append(f"{name}: the open response has no nonce")
        if _kept(message) and "repeat" not in step:
            history.append(F.identity(response))
        frames.append(frame)
        responses.append(response)
    return failures


def run_clients(vectors: dict[str, Any]) -> list[str]:
    contract = Contract.from_bytes(vectors["contract"].encode("utf-8"))
    failures = []
    for case in vectors["clients"]:
        for variant in case.get("cases") or [[]]:
            failures += _client_case(vectors, contract, case, variant)
    return failures


def _substitute(value: Any, variant: list[str], bodies: dict[str, Any]) -> Any:
    if value == "$code":
        return bodies.get(variant[0], variant[0])
    if value == "$executed":
        return variant[1]
    if isinstance(value, dict):
        return {k: _substitute(v, variant, bodies) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, variant, bodies) for v in value]
    return value


def _verdict(outcome: Any) -> dict[str, Any]:
    if outcome is None:
        return {"kind": "ignored"}
    if isinstance(outcome, bytes):
        return {"kind": "resend"}
    if isinstance(outcome, C.Result):
        return {"kind": "ok"}
    if isinstance(outcome, Declined):
        return {"kind": "declined", "code": outcome.code, "executed": "no"}
    if isinstance(outcome, C.Rejected):
        return {"kind": "rejected", "code": outcome.code}
    assert isinstance(outcome, C.Ended)
    return {"kind": "ended", "code": outcome.code, "executed": outcome.executed.value}


def _client_case(vectors: dict[str, Any], contract: Contract, case: dict[str, Any], variant: list[str]) -> list[str]:
    name = f"client {case['name']!r} {variant}"
    lossy, retries = case["lossy"], case.get("retries", 3)
    steps = _substitute(case["steps"], variant, case.get("bodies", {}))
    state = C.new_state(contract, session=vectors["session"], bound=F.HANDSHAKE_BOUND)
    last: str | None = None
    first_open: bytes | None = None
    failures = []
    for index, step in enumerate(steps):
        where = f"{name} step {index}"
        if "do" in step:
            op = {"open": "open", "close": "close", "ping": "ncp.ping"}.get(step["do"], step.get("op"))
            try:
                state, frame = C.request(state, op, step.get("body"))
            except C.UsageError:
                if step["expect"] != "usage":
                    failures.append(f"{where}: refused, expected a frame")
                continue
            if step["expect"] != "sent":
                failures.append(f"{where}: sent, expected a refusal")
                continue
            if op == "open":
                if step.get("same_as_first") and frame != first_open:
                    failures.append(f"{where}: the open again is another frame")
                first_open = first_open or frame
            sent = F.decode(frame, F.MAX_BOUND).message
            want = step.get("request")
            if want and (sent["seq"] != want["seq"] or (want["ack"] == "last" and sent["ack"] != last)):
                failures.append(f"{where}: request seq {sent['seq']} ack {sent['ack']}")
            continue
        if "reply" in step:
            frame = _reply(state, step["reply"], step["to"])
            state, outcome = C.receive(state, frame, lossy=lossy)
            if isinstance(outcome, (C.Result, Declined)):
                last = F.identity(frame)
        elif "timeout" in step:
            state, outcome = C.time_out(state, lossy=lossy, retries=retries)
        else:
            state, outcome = C.closed(state)
        observed = _verdict(outcome)
        if observed != step["expect"]:
            failures.append(f"{where}: expected {step['expect']}, observed {observed}")
        want_state = step.get("state")
        if want_state is not None:
            got = {"seq": state.seq, "opened": state.opened, "ended": state.ended}
            if got != want_state:
                failures.append(f"{where}: state {got}, expected {want_state}")
    return failures


def _reply(state: C.ClientState, reply: dict[str, Any], to: str) -> bytes:
    pending = state.pending
    assert pending is not None
    if to == "garbage":
        return b"junk that is not a frame"
    message = {
        "ncp": 2,
        "session": state.session,
        "seq": pending.seq,
        "request": pending.identity,
        "outcome": reply["outcome"],
        "code": reply["code"],
        "body": reply["body"],
    }
    if to == "other_seq":
        message["seq"] = pending.seq + 1
    elif to == "other_request":
        message["request"] = "0" * 64
    elif to == "other_session":
        message["session"] = str(uuid.uuid4())
    elif to == "nameless":
        message.update(session=None, seq=None, request=None)
    elif to == "nameless_bound":
        message.update(session=None, seq=None, request=None, body={"session": state.session, "kept": state.ack})
    return F.encode(message)


def run_streams(vectors: dict[str, Any]) -> list[str]:
    subscriber = Subscriber({vectors["contract_identity"]})
    failures = []
    for index, case in enumerate(vectors["streams"]):
        delivery = subscriber.receive(frame_bytes(case["frame"]))
        observed = (delivery.status, delivery.lost, delivery.end)
        if observed != (case["status"], case["lost"], case["end"]):
            failures.append(f"stream case {index}: {observed}, expected {(case['status'], case['lost'], case['end'])}")
    return failures


def transcript_summary(report: T.Report) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "version": report.version,
        "closed": report.closed,
        "truncated": report.truncated_at is not None,
        "chain_ok": report.chain_ok,
        "sessions": [
            {
                "role": s.role,
                "requests": s.requests,
                "declined": s.declined,
                "complete": s.complete,
                "problems": bool(s.problems),
            }
            for s in report.sessions.values()
        ],
    }


def run_transcripts(vectors: dict[str, Any]) -> list[str]:
    failures = []
    with tempfile.TemporaryDirectory(prefix="ncp-conformance-") as directory:
        for case in vectors["transcripts"]:
            path = os.path.join(directory, "case.ncpt")
            with open(path, "wb") as handle:
                handle.write(bytes.fromhex(case["file"]))
            key = bytes.fromhex(case["key"]) if case["key"] else None
            observed = transcript_summary(T.verify(path, key=key))
            if observed != case["expect"]:
                failures.append(f"transcript {case['name']!r}: {observed}, expected {case['expect']}")
    return failures


def run_contracts(vectors: dict[str, Any]) -> list[str]:
    failures = []
    for case in vectors["contracts"]:
        try:
            Contract.from_bytes(case["document"].encode("utf-8"))
            accepted = True
        except ContractError:
            accepted = False
        if accepted != case["valid"]:
            failures.append(f"contract {case['name']!r}: {'accepted' if accepted else 'refused'}")
    return failures


def run_schemas(vectors: dict[str, Any]) -> list[str]:
    failures = []
    for index, case in enumerate(vectors["schemas"]):
        K.compile_schema(case["schema"])
        value = F.decode(frame_bytes(case["frame"]), F.MAX_BOUND).message["value"]
        if (K.check(case["schema"], value) is None) != case["valid"]:
            failures.append(f"schema case {index} {case['schema']}: {not case['valid']}")
    return failures


def run_all(vectors: dict[str, Any] | None = None) -> dict[str, list[str]]:
    """Every part against this SDK."""
    vectors = vectors or load()
    scenario_failures, _ = run_scenarios(vectors, python_owner(vectors))
    contract = hashlib.sha256(vectors["contract"].encode("utf-8")).hexdigest()
    assert contract == vectors["contract_identity"]
    return {
        "frames": run_frames(vectors, python_decode),
        "messages": run_messages(vectors),
        "auth": run_auth(vectors),
        "scenarios": scenario_failures,
        "clients": run_clients(vectors),
        "streams": run_streams(vectors),
        "transcripts": run_transcripts(vectors),
        "contracts": run_contracts(vectors),
        "schemas": run_schemas(vectors),
    }
