"""Messages, outcomes, and codes (specification sections 6 and 7.4 to 7.5).

spec/ncp2-rules.json states the same codes as data; scripts/check_ncp2_rules.py keeps this module
equal to it.
"""

from __future__ import annotations

import enum
import re
from typing import Any

from . import frame as F
from .frame import FrameError

PROTOCOL = 2
OUTCOMES = ("ok", "declined", "rejected", "ended")
MAX_NAME = 64
MAX_RUN = 256
MAX_DETAIL = 256
MAX_FEATURES = 32

# Codes of a rejected frame: the owner did not admit it.
REJECTION_CODES = frozenset(
    {
        "wrong_protocol",
        "not_open",
        "wrong_session",
        "seq_conflict",
        "seq_stale",
        "seq_gap",
        "session_ended",
        "ack_missing",
        "ack_mismatch",
        "already_open",
        # in reply to open
        "body_invalid",
        "contract_mismatch",
        "bound_unacceptable",
        "refused",
    }
)
# Codes of a declined request: admitted, not executed, never executed.
DECLINE_CODES = frozenset({"unknown_op", "body_invalid"})
# Codes of an ending response, with whether the request executed.
ENDING_CODES = {
    "result_too_large": "yes",
    "owner_failure": "unknown",
    "session_expired": "unknown",
    "shutdown": "no",
    "bad_frame": "no",
}
# Codes that a client reports for local events (spec/ncp2-rules.json, local_codes).
LOCAL_CODES = frozenset({"local.timeout", "local.closed", "local.protocol", "local.bad_frame"})

_SESSION = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_IDENTITY = re.compile(r"[0-9a-f]{64}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_CODE = re.compile(r"[a-z_]{1,64}\Z")
_STREAM = re.compile(r"[A-Za-z0-9_./-]{1,256}\Z")
_REQUEST_MEMBERS = frozenset({"ncp", "session", "seq", "op", "ack", "body"})
_RESPONSE_MEMBERS = frozenset({"ncp", "session", "seq", "request", "outcome", "code", "body"})
_STREAM_MEMBERS = frozenset({"ncp", "stream", "seq", "prev", "contract", "body"})


class CallError(Exception):
    """A call that returned no result: `Declined`, `Rejected`, or `Ended`. `code` is the owner's
    code, or a local code of spec/ncp2-rules.json; `body` is the response body, if any."""

    code: str
    body: Any


class ProtocolError(Exception):
    """A peer broke a rule of a profile or of a contract, outside the exchange rules of section 7:
    for example a round record that does not list the agent's request."""


class Executed(str, enum.Enum):
    """Whether a request executed, as far as the client can know (spec section 7.7, property 7)."""

    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return self.value


def executed(code: str) -> Executed:
    """Whether the request named by an `ended` response executed. A code that this version does
    not know gives UNKNOWN (spec section 7.5)."""
    return Executed(ENDING_CODES.get(code, "unknown"))


def is_identity(value: Any) -> bool:
    return type(value) is str and _IDENTITY.match(value) is not None


def is_session(value: Any) -> bool:
    return type(value) is str and _SESSION.match(value) is not None


def is_name(value: Any) -> bool:
    """An operation name, feature name, or stream type name (spec section 6)."""
    return type(value) is str and _NAME.match(value) is not None


def is_nonce(value: Any) -> bool:
    return type(value) is str and _NONCE.match(value) is not None


def is_code(value: Any) -> bool:
    return type(value) is str and _CODE.match(value) is not None


def is_stream(value: Any) -> bool:
    return type(value) is str and _STREAM.match(value) is not None


def _counter(value: Any) -> bool:
    """A non-negative integer: JSON's integers decode to int, and bool is not one."""
    return type(value) is int and value >= 0


def check_request(message: dict[str, Any]) -> None:
    """Raise FrameError unless the message has the request form of section 6.1."""
    if message.keys() - {"att"} != _REQUEST_MEMBERS:
        raise FrameError("request members")
    ack = message["ack"]
    if not (
        _counter(message["ncp"])
        and is_session(message["session"])
        and _counter(message["seq"])
        and is_name(message["op"])
        and (ack is None or is_identity(ack))
    ):
        raise FrameError("request member types")


def check_response(message: dict[str, Any]) -> None:
    """Raise FrameError unless the message has the response form of section 6.2."""
    if message.keys() - {"att"} != _RESPONSE_MEMBERS:
        raise FrameError("response members")
    outcome, code = message["outcome"], message["code"]
    if not _counter(message["ncp"]) or outcome not in OUTCOMES:
        raise FrameError("response member types")
    names = is_session(message["session"]) and _counter(message["seq"]) and is_identity(message["request"])
    if outcome == "ok":
        valid = code is None and names
    elif outcome == "ended":
        nameless = message["session"] is None and message["seq"] is None and message["request"] is None
        valid = is_code(code) and type(message["body"]) is dict and (names or nameless)
    else:
        valid = is_code(code) and type(message["body"]) is dict and names
    if not valid:
        raise FrameError("response member types")


def check_stream_message(message: dict[str, Any]) -> None:
    """Raise FrameError unless the message has the stream form of section 6.3."""
    if message.keys() - {"att"} != _STREAM_MEMBERS:
        raise FrameError("stream message members")
    seq, prev = message["seq"], message["prev"]
    if not (
        type(message["ncp"]) is int
        and message["ncp"] == PROTOCOL
        and is_stream(message["stream"])
        and type(seq) is int
        and seq >= 1
        and is_identity(message["contract"])
        and ((seq == 1 and prev is None) or (seq > 1 and is_identity(prev)))
    ):
        raise FrameError("stream message member types")


def kind(message: dict[str, Any]) -> str:
    """"request", "response", "stream", or "other", from the members of a decoded message."""
    keys = message.keys() - {"att"}
    if keys == _REQUEST_MEMBERS:
        return "request"
    if keys == _RESPONSE_MEMBERS:
        return "response"
    if keys == _STREAM_MEMBERS:
        return "stream"
    return "other"


def detail(text: Any) -> str:
    """A detail member for a response body: at most 256 characters, always encodable as UTF-8.
    A text that a frame cannot carry, such as one with an unpaired surrogate, never stops the
    response."""
    text = str(text)
    return text.encode("utf-8", "replace").decode("utf-8")[:MAX_DETAIL]


def nameless_response(code: str, *, key: bytes | None = None) -> bytes:
    """The response of the byte-stream binding that names no request (section 6.2): the bad-frame
    response (rule 9.1.3) and the shutdown response (rule 9.1.9)."""
    return F.encode(
        {
            "ncp": PROTOCOL,
            "session": None,
            "seq": None,
            "request": None,
            "outcome": "ended",
            "code": code,
            "body": {},
        },
        key=key,
    )


def bad_frame_response(*, key: bytes | None = None) -> bytes:
    """The response a byte-stream owner sends for a bad frame before it closes (rule 9.1.3)."""
    return nameless_response("bad_frame", key=key)


def shutdown_response(*, key: bytes | None = None) -> bytes:
    """The response a byte-stream owner sends when it stops a session (rule 9.1.9)."""
    return nameless_response("shutdown", key=key)
