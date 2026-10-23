"""Transcripts: records of the frames that one program sent and received (section 10).

A complete, verified transcript proves which frames the recorder sent and received, and in
which order. It does not prove who produced them.
"""

from __future__ import annotations

import os
import struct
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import BinaryIO

from . import frame as F
from .exchange import check_request, check_response
from .frame import FrameError

FILE_MAGIC = b"NCPT\x00\x00\x00\x01"
RECORD = struct.Struct(">BQI")
SENT, RECEIVED = 1, 2


class Tap:
    """Append every frame that a channel sends or receives to a transcript file.

    By default, each record goes to the operating system at once, so the transcript keeps every
    record up to a crash of this program. With `buffered=True`, records collect in a buffer of
    1 MiB: one system call fewer for each frame, but a crash loses the records in the buffer.
    A failure to write raises, so that a session never runs on without its record.
    """

    def __init__(self, path: str | os.PathLike[str], *, buffered: bool = False) -> None:
        self._file: BinaryIO = open(path, "xb", buffering=1 << 20)
        self._buffered = buffered
        self._lock = threading.Lock()
        self._file.write(FILE_MAGIC)
        if not buffered:
            self._file.flush()

    def record(self, kind: int, frame: bytes | bytearray | memoryview) -> None:
        with self._lock:
            self._file.write(RECORD.pack(kind, time.monotonic_ns(), len(frame)))
            self._file.write(frame)
            if not self._buffered:
                self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()

    def __enter__(self) -> Tap:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass
class Record:
    kind: int
    time_ns: int
    frame: bytes


def read(path: str | os.PathLike[str]) -> Iterator[Record]:
    """Yield the records of a transcript file."""
    with open(path, "rb") as handle:
        if handle.read(len(FILE_MAGIC)) != FILE_MAGIC:
            raise FrameError("transcript magic")
        while True:
            head = handle.read(RECORD.size)
            if not head:
                return
            if len(head) != RECORD.size:
                raise FrameError("truncated transcript record")
            kind, time_ns, length = RECORD.unpack(head)
            data = handle.read(length)
            if len(data) != length or kind not in (SENT, RECEIVED):
                raise FrameError("truncated or unknown transcript record")
            yield Record(kind, time_ns, data)


@dataclass
class SessionReport:
    session: str
    role: str  # "client" or "owner", from the direction of the open request
    requests: int = 0
    complete: bool = False
    ended: str | None = None
    problems: list[str] = field(default_factory=list)


def verify(path: str | os.PathLike[str]) -> dict[str, SessionReport]:
    """Verify every exchange session in a transcript (section 10).

    Checks the digest of every frame, sequence numbers, request identities, and the hash
    chain: each request names the identity of the response before it.
    """
    sessions: dict[str, SessionReport] = {}
    pending: dict[str, tuple[int, str, str]] = {}  # session -> (seq, request identity, op) awaiting a response
    last_response: dict[str, str] = {}  # session -> identity of the last ok response
    next_seq: dict[str, int] = {}
    for record in read(path):
        try:
            decoded = F.decode(record.frame, F.MAX_BOUND)
        except FrameError as error:
            sessions.setdefault("?", SessionReport("?", "?")).problems.append(f"bad frame: {error}")
            continue
        message = decoded.message
        if "op" in message:
            check_request(message)
            session = message["session"]
            role = "client" if record.kind == SENT else "owner"
            report = sessions.setdefault(session, SessionReport(session, role))
            seq = message["seq"]
            if session in pending and pending[session][0] == seq:
                if pending[session][1] != decoded.identity:
                    report.problems.append(f"seq {seq}: changed request")
                continue  # a repeat of the outstanding request
            expected = next_seq.get(session, 0)
            if seq != expected:
                report.problems.append(f"seq {seq}: expected {expected}")
            if seq == 0:
                if message["op"] != "open" or message["ack"] is not None:
                    report.problems.append("seq 0 is not an open without ack")
            elif message["ack"] != last_response.get(session):
                report.problems.append(f"seq {seq}: ack does not name the previous response")
            pending[session] = (seq, decoded.identity, message["op"])
            report.requests += 1
        elif "outcome" in message:
            check_response(message)
            session = message["session"]
            if session is None:
                for report in sessions.values():
                    if report.ended is None:
                        report.ended = message["code"]
                continue
            report = sessions.setdefault(session, SessionReport(session, "?"))
            if session not in pending:
                if last_response.get(session) == decoded.identity:
                    continue  # a repeat of the kept response
                report.problems.append(f"seq {message['seq']}: response without request")
                continue
            seq, request_id, op = pending[session]
            if message["seq"] != seq or message["request"] != request_id:
                report.problems.append(f"seq {message['seq']}: response names another request")
                continue
            del pending[session]
            if message["outcome"] == "rejected":
                continue  # the same seq may be sent again
            last_response[session] = decoded.identity
            next_seq[session] = seq + 1
            if message["outcome"] == "ended":
                report.ended = message["code"]
            elif op == "close":
                report.complete = True
        # stream messages are verified by stream.Subscriber
    for session, (seq, _, _) in pending.items():
        sessions[session].problems.append(f"seq {seq}: no response")
    return sessions
