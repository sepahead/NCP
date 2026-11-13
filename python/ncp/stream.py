"""Streams: sequenced, hash-chained messages without retries (specification sections 6.3 and 8)."""

from __future__ import annotations

import secrets
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from . import frame as F
from .frame import FrameError
from .messages import PROTOCOL, check_stream_message, is_identity, is_stream

END = "ncp.end"
STATUSES = ("accepted", "joined", "repeat", "conflict", "broken_chain", "unknown_contract", "bad_frame")


class Publisher:
    """Number, chain, and send the messages of one stream (section 8).

    The stream identifier is `name` and `/` and 16 random hexadecimal characters, so that a
    publisher that restarts never shares an identifier with its earlier instance (rule 8.2).
    With `exact=True`, the identifier is `name` itself, and the caller guarantees that no other
    instance uses it.
    """

    def __init__(
        self,
        name: str,
        contract: str,
        send: Callable[[bytes], None],
        *,
        exact: bool = False,
        key: bytes | None = None,
    ) -> None:
        identifier = name if exact else f"{name}/{secrets.token_hex(8)}"
        if not is_stream(identifier) or not is_identity(contract):
            raise ValueError("stream identifier or contract")
        self.stream, self.contract, self._send, self.key = identifier, contract, send, F.check_key(key)
        self.seq = 0
        self.prev: str | None = None
        self.ended = False

    def publish(self, body: Any) -> bytes:
        """Send the next message. Return its frame."""
        if self.ended:
            raise ValueError("the stream has ended")
        frame = F.encode(
            {
                "ncp": PROTOCOL,
                "stream": self.stream,
                "seq": self.seq + 1,
                "prev": self.prev,
                "contract": self.contract,
                "body": body,
            },
            key=self.key,
        )
        self.seq += 1
        self.prev = F.identity(frame)
        self._send(frame)
        return frame

    def end(self, body: dict[str, Any] | None = None) -> bytes:
        """Send the end message of the stream (rule 8.12): a body with the member `ncp.end`."""
        frame = self.publish({**(body or {}), END: {}})
        self.ended = True
        return frame


@dataclass
class Delivery:
    """The outcome of one received stream frame.

    `status` is one of STATUSES. `lost` counts the messages missing before an accepted one.
    `end` is true for the end message of a stream.
    """

    status: str
    message: dict[str, Any] | None = None
    lost: int = 0
    end: bool = False

    @property
    def accepted(self) -> bool:
        return self.status in ("accepted", "joined")


@dataclass
class _State:
    seq: int
    identity: str
    ended: bool = False


class Subscriber:
    """Check the frames of any number of streams (section 8).

    `contracts` are the contract identities that the subscriber accepts. `bound` limits each
    frame (rule 8.4). The subscriber keeps the state of at most `max_streams` streams and forgets
    the least recently used one beyond that. `check_digests=False` stops the comparison of each
    frame's digest with its bytes, under the conditions of spec section 3, rule 5.
    """

    def __init__(
        self,
        contracts: Iterable[str],
        bound: int = F.DEFAULT_BOUND,
        *,
        check_digests: bool = True,
        key: bytes | None = None,
        max_streams: int = 1024,
    ) -> None:
        if key is not None and not check_digests:
            raise ValueError("an authenticated session always compares digests (section 13.2)")
        if max_streams < 1:
            raise ValueError("max_streams must be at least 1")
        self.contracts = frozenset(contracts)
        self.bound, self.check_digests, self.key, self.max_streams = bound, check_digests, F.check_key(key), max_streams
        self._streams: OrderedDict[str, _State] = OrderedDict()

    def receive(self, frame: bytes | bytearray | memoryview) -> Delivery:
        try:
            decoded = F.decode(frame, self.bound, check_digest=self.check_digests, key=self.key)
            check_stream_message(decoded.message)
        except FrameError:
            return Delivery("bad_frame")
        message = decoded.message
        if message["contract"] not in self.contracts:
            return Delivery("unknown_contract", message)
        stream, seq = message["stream"], message["seq"]
        end = type(message["body"]) is dict and END in message["body"]
        state = self._streams.get(stream)
        if state is None:
            self._remember(stream, _State(seq, decoded.identity, end))
            return Delivery("accepted" if seq == 1 else "joined", message, 0, end)
        self._streams.move_to_end(stream)
        if seq == state.seq:
            return Delivery("repeat" if decoded.identity == state.identity else "conflict", message)
        if seq < state.seq:
            return Delivery("repeat", message)
        if state.ended:
            return Delivery("conflict", message)
        if seq == state.seq + 1 and message["prev"] != state.identity:
            return Delivery("broken_chain", message)
        lost = seq - state.seq - 1
        state.seq, state.identity, state.ended = seq, decoded.identity, end
        return Delivery("accepted", message, lost, end)

    def _remember(self, stream: str, state: _State) -> None:
        self._streams[stream] = state
        while len(self._streams) > self.max_streams:
            self._streams.popitem(last=False)
