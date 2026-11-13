"""NCP 2: at-most-once exchanges with a known or possibly-executed outcome, and hash-chained
streams, between independent programs.

See spec/NCP-2.md. Standard library only.
"""

from .binding import (
    ChannelClosed,
    ChildChannel,
    IdleTimeout,
    Limits,
    StreamChannel,
    TcpServer,
    TlsConfig,
    UnixServer,
    connect_tcp,
    connect_unix,
    serve,
    serve_stdio,
    spawn,
)
from .client import Client, ClientState, Ended, Pending, Rejected, Result, UsageError, call_all
from .contract import Contract, ContractError
from .events import Event, LogObserver, Observer
from .frame import DEFAULT_BOUND, HANDSHAKE_BOUND, MAX_BOUND, Array, FrameError, decode, encode, identity
from .lockstep import Lockstep, LockstepClient
from .messages import PROTOCOL, CallError, Executed, ProtocolError
from .owner import IMPLEMENTATION, Declined, Handler, OpenInfo, Owner, OwnerState, Refused, Request
from .rounds import RoundRecord, Rounds
from .stream import Delivery, Publisher, Subscriber
from .transcript import Tap
from .transcript import verify as verify_transcript

__all__ = [
    "Array",
    "CallError",
    "ChannelClosed",
    "ChildChannel",
    "Client",
    "ClientState",
    "Contract",
    "ContractError",
    "DEFAULT_BOUND",
    "Declined",
    "Delivery",
    "Ended",
    "Event",
    "Executed",
    "FrameError",
    "HANDSHAKE_BOUND",
    "Handler",
    "IMPLEMENTATION",
    "IdleTimeout",
    "Limits",
    "Lockstep",
    "LockstepClient",
    "LogObserver",
    "MAX_BOUND",
    "Observer",
    "OpenInfo",
    "Owner",
    "OwnerState",
    "PROTOCOL",
    "Pending",
    "ProtocolError",
    "Publisher",
    "Refused",
    "Rejected",
    "Request",
    "Result",
    "RoundRecord",
    "Rounds",
    "StreamChannel",
    "Subscriber",
    "Tap",
    "TcpServer",
    "TlsConfig",
    "UnixServer",
    "UsageError",
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
