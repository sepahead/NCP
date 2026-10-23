"""Streams: sequenced, hash-chained messages without retries (sections 6.3 and 8)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from . import frame as F
from .exchange import PROTOCOL, is_identity
from .frame import FrameError

_STREAM = re.compile(r"[A-Za-z0-9_./-]{1,256}\Z")
_MEMBERS = frozenset({"ncp", "stream", "seq", "prev", "contract", "body"})


def check_stream_message(message: dict[str, Any]) -> None:
    """Raise FrameError unless the message has the stream form of section 6.3."""
    if message.keys() - {"att"} != _MEMBERS:
        raise FrameError("stream message members")
    seq, prev = message["seq"], message["prev"]
    if (message["ncp"] != PROTOCOL or type(message["stream"]) is not str
            or _STREAM.match(message["stream"]) is None or type(seq) is not int or seq < 1
            or not is_identity(message["contract"])
            or not ((seq == 1 and prev is None) or (seq > 1 and is_identity(prev)))):
        raise FrameError("stream message member types")


class Publisher:
    """Number, chain, and send the messages of one stream."""

    def __init__(self, stream: str, contract: str, send: Callable[[bytes], None]) -> None:
        if _STREAM.match(stream) is None or not is_identity(contract):
            raise ValueError("stream identifier or contract")
        self.stream, self.contract, self._send = stream, contract, send
        self.seq = 0
        self.prev: str | None = None

    def publish(self, body: Any) -> bytes:
        self.seq += 1
        frame = F.encode({"ncp": PROTOCOL, "stream": self.stream, "seq": self.seq, "prev": self.prev,
                          "contract": self.contract, "body": body})
        self.prev = F.identity(frame)
        self._send(frame)
        return frame


@dataclass
class Delivery:
    """The outcome of one received stream frame."""

    status: str  # "accepted", "repeat", "broken_chain", "unknown_contract", "bad_frame"
    message: dict[str, Any] | None = None
    lost: int = 0


class Subscriber:
    """Check the frames of any number of streams (section 8).

    `check_digests=False` stops the comparison of each frame's digest with its bytes, under the
    conditions of spec section 3, rule 4.
    """

    def __init__(self, contracts: set[str] | frozenset[str], bound: int = F.MAX_BOUND, *,
                 check_digests: bool = True) -> None:
        self.contracts, self.bound, self.check_digests = frozenset(contracts), bound, check_digests
        self._next: dict[str, int] = {}
        self._last: dict[str, str] = {}

    def receive(self, frame: bytes | bytearray | memoryview) -> Delivery:
        try:
            decoded = F.decode(frame, self.bound, check_digest=self.check_digests)
            check_stream_message(decoded.message)
        except FrameError:
            return Delivery("bad_frame")
        message = decoded.message
        if message["contract"] not in self.contracts:
            return Delivery("unknown_contract", message)
        stream, seq = message["stream"], message["seq"]
        expected = self._next.get(stream, 1)
        if seq < expected:
            return Delivery("repeat", message)
        if seq == expected and message["prev"] != self._last.get(stream):
            return Delivery("broken_chain", message)
        self._next[stream], self._last[stream] = seq + 1, decoded.identity
        return Delivery("accepted", message, seq - expected)
