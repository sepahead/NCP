"""NCP 2: exactly-once exchanges and hash-chained streams between independent programs.

See spec/NCP-2.md. Standard library only.
"""

from .binding import (
    ChannelClosed,
    StreamChannel,
    TcpServer,
    UnixServer,
    connect_tcp,
    connect_unix,
    serve,
    serve_stdio,
    spawn,
)
from .contract import Contract, call_all
from .exchange import (
    IMPLEMENTATION,
    PROTOCOL,
    BodyInvalid,
    Client,
    Ended,
    Handler,
    Owner,
    ProtocolError,
    Rejected,
    Result,
)
from .frame import DEFAULT_BOUND, HANDSHAKE_BOUND, MAX_BOUND, Array, FrameError, decode, encode, identity
from .stream import Delivery, Publisher, Subscriber
from .transcript import Tap
from .transcript import verify as verify_transcript

__all__ = [
    "Array",
    "BodyInvalid",
    "ChannelClosed",
    "Client",
    "Contract",
    "DEFAULT_BOUND",
    "Delivery",
    "Ended",
    "FrameError",
    "HANDSHAKE_BOUND",
    "Handler",
    "IMPLEMENTATION",
    "MAX_BOUND",
    "Owner",
    "PROTOCOL",
    "ProtocolError",
    "Publisher",
    "Rejected",
    "Result",
    "StreamChannel",
    "Subscriber",
    "Tap",
    "TcpServer",
    "UnixServer",
    "call_all",
    "connect_tcp",
    "connect_unix",
    "decode",
    "encode",
    "identity",
    "serve",
    "serve_stdio",
    "spawn",
    "verify_transcript",
]
