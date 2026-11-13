"""Transcripts: records of the frames that one program sent and received (specification section 10).

A verified transcript is internally consistent: it shows which frames the recorder sent and
received, and in which order, as far as the file can be trusted. Without a key, anyone can write
a transcript that verifies. With a key (section 13.2), only a holder of the key can.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import os
import struct
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from . import frame as F
from .frame import FrameError
from .messages import check_request, check_response, check_stream_message, kind as message_kind

MAGIC_V1 = b"NCPT\x00\x00\x00\x01"
MAGIC = b"NCPT\x00\x00\x00\x02"
FILE_MAGIC = MAGIC
RECORD = struct.Struct(">BQI")
LENGTH = struct.Struct(">I")
COUNT = struct.Struct(">Q")
SENT, RECEIVED, END = 1, 2, 3
MAX_HEADER = 4096
CHAIN_BYTES = 32


def _now_rfc3339() -> str:
    nanoseconds = time.time_ns()
    seconds, fraction = divmod(nanoseconds, 1_000_000_000)
    moment = datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc)
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{fraction:09d}Z"


def _mac(key: bytes | None, *parts: bytes) -> bytes:
    digest = hashlib.sha256() if key is None else hmac.new(key, digestmod=hashlib.sha256)
    for part in parts:
        digest.update(part)
    return digest.digest()


class Tap:
    """Append every frame that a channel sends or receives to a transcript file (section 10).

    By default, each record goes to the operating system at once, so the transcript keeps every
    record up to a crash of this program. With `buffered=True`, records collect in a buffer of
    1 MiB: one system call fewer for each frame, but a crash loses the records in the buffer.
    A failure to write raises, so that a session never runs on without its record. `close()`
    writes the end record. With `key`, the chain uses HMAC-SHA-256 (section 13.2).
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        recorder: str = "",
        buffered: bool = False,
        key: bytes | None = None,
        clock: Callable[[], int] = time.monotonic_ns,
        started: str | None = None,
    ) -> None:
        from .owner import IMPLEMENTATION

        self._key = F.check_key(key)
        header = json.dumps(
            {
                "recorder": recorder[:256],
                "implementation": IMPLEMENTATION,
                "started": started or _now_rfc3339(),
                "chain": "sha256" if key is None else "hmac-sha256",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(header) > MAX_HEADER:
            raise ValueError("the transcript header exceeds 4096 bytes")
        self._file: BinaryIO = open(path, "xb", buffering=1 << 20)
        self._buffered, self._clock = buffered, clock
        self._lock = threading.Lock()
        start = MAGIC + LENGTH.pack(len(header)) + header
        self._file.write(start)
        if not buffered:
            self._file.flush()
        self._chain = _mac(self._key, start)
        self._origin = clock()
        self._count = 0
        self._closed = False

    def record(self, kind: int, frame: bytes | bytearray | memoryview) -> None:
        if kind not in (SENT, RECEIVED):
            raise ValueError("kind must be SENT or RECEIVED")
        with self._lock:
            if self._closed:
                raise ValueError("the transcript is closed")
            elapsed = max(0, self._clock() - self._origin)
            head = RECORD.pack(kind, elapsed, len(frame))
            self._chain = _mac(self._key, self._chain, head, bytes(frame[-F.DIGEST_BYTES :]))
            self._file.write(head)
            self._file.write(frame)
            self._file.write(self._chain)
            self._count += 1
            if not self._buffered:
                self._file.flush()

    def flush(self) -> None:
        with self._lock:
            self._file.flush()

    def close(self) -> None:
        """Write the end record and close the file."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            elapsed = max(0, self._clock() - self._origin)
            head = RECORD.pack(END, elapsed, 0)
            self._chain = _mac(self._key, self._chain, head, COUNT.pack(self._count))
            self._file.write(head + self._chain)
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
    chain: bytes | None = None


@dataclass
class Transcript:
    """A transcript file as read: its version, header, records, and how it ends."""

    version: int
    header: dict[str, Any] | None
    records: list[Record]
    closed: bool = False  # it ends with an end record (version 2)
    truncated_at: int | None = None  # the offset of a record that ends before its length
    chain_ok: bool | None = None  # None: version 1, or a keyed chain read without the key
    problems: list[str] = field(default_factory=list)


def _records(
    handle: BinaryIO, version: int, key: bytes | None, start: bytes, out: Transcript, check: bool
) -> Iterator[Record]:
    """The records of a transcript. With `check`, compare each chain value (version 2)."""
    chain = _mac(key, start) if version == 2 else b""
    count = 0
    while True:
        offset = handle.tell()
        head = handle.read(RECORD.size)
        if not head:
            return
        if len(head) != RECORD.size:
            out.truncated_at = offset
            return
        kind, time_ns, length = RECORD.unpack(head)
        if kind == END and version == 2:
            value = handle.read(CHAIN_BYTES)
            if length != 0 or len(value) != CHAIN_BYTES:
                out.truncated_at = offset
                return
            if check:
                chain = _mac(key, chain, head, COUNT.pack(count))
                if not hmac.compare_digest(chain, value):
                    out.chain_ok = False
                    out.problems.append(f"record {count}: the end record's chain value differs")
            out.closed = True
            if handle.read(1):
                out.problems.append("data after the end record")
            return
        if kind not in (SENT, RECEIVED):
            out.problems.append(f"record {count} at offset {offset}: unknown kind {kind}")
            out.truncated_at = offset
            return
        frame = handle.read(length)
        if len(frame) != length:
            out.truncated_at = offset
            return
        value: bytes | None = None
        if version == 2:
            value = handle.read(CHAIN_BYTES)
            if len(value) != CHAIN_BYTES:
                out.truncated_at = offset
                return
            if check:
                chain = _mac(key, chain, head, frame[-F.DIGEST_BYTES :])
                if not hmac.compare_digest(chain, value):
                    out.chain_ok = False
                    out.problems.append(f"record {count}: the chain value differs; the file changed at or before it")
                    chain = value  # report each break once, and go on from the recorded value
        count += 1
        yield Record(kind, time_ns, frame, value)


def iterate(path: str | os.PathLike[str], *, key: bytes | None = None) -> tuple[Transcript, Iterator[Record]]:
    """Open a transcript and return its description and an iterator of its records. The
    description's `closed`, `truncated_at`, `chain_ok`, and `problems` are final once the
    iterator is exhausted."""
    key = F.check_key(key)
    handle = open(path, "rb")
    try:
        magic = handle.read(8)
        if magic == MAGIC_V1:
            out = Transcript(1, None, [])
            records = _records(handle, 1, None, b"", out, False)
        elif magic == MAGIC:
            length = handle.read(LENGTH.size)
            if len(length) != LENGTH.size or LENGTH.unpack(length)[0] > MAX_HEADER:
                raise FrameError("transcript header length")
            text = handle.read(LENGTH.unpack(length)[0])
            try:
                header = F.loads(text)
            except FrameError as error:
                raise FrameError(f"transcript header: {error}") from error
            if type(header) is not dict or header.get("chain") not in ("sha256", "hmac-sha256"):
                raise FrameError("transcript header members")
            out = Transcript(2, header, [])
            keyed = header["chain"] == "hmac-sha256"
            if keyed and key is None:
                out.problems.append("the chain and the frames are authenticated: verify them with the key")
                records = _records(handle, 2, None, magic + length + text, out, False)
            else:
                out.chain_ok = True
                records = _records(handle, 2, key if keyed else None, magic + length + text, out, True)
        else:
            raise FrameError("transcript magic")
    except BaseException:
        handle.close()
        raise

    def closing() -> Iterator[Record]:
        try:
            yield from records
        finally:
            handle.close()

    return out, closing()


def read(path: str | os.PathLike[str], *, key: bytes | None = None) -> Transcript:
    """Read a whole transcript into memory. For large files, use `iterate`."""
    out, records = iterate(path, key=key)
    out.records = list(records)
    return out


@dataclass
class SessionReport:
    session: str
    role: str  # "client" or "owner", from the direction of the open request
    requests: int = 0  # admitted requests: ok, declined, or ended with a request named
    declined: int = 0
    rejected: int = 0
    repeats: int = 0  # copies of a request, and copies of a response
    complete: bool = False
    ended: str | None = None
    problems: list[str] = field(default_factory=list)


@dataclass
class StreamReport:
    stream: str
    accepted: int = 0
    lost: int = 0
    ended: bool = False
    problems: list[str] = field(default_factory=list)


@dataclass
class Report:
    """The verification of one transcript (section 10.3)."""

    version: int
    header: dict[str, Any] | None
    records: int = 0
    closed: bool = False
    truncated_at: int | None = None
    chain_ok: bool | None = None
    sessions: dict[str, SessionReport] = field(default_factory=dict)
    streams: dict[str, StreamReport] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """No problem in the file, in any session, or in any stream, and the chain checked."""
        return (
            not self.problems
            and self.truncated_at is None
            and self.chain_ok is not False
            and all(not s.problems for s in self.sessions.values())
            and all(not s.problems for s in self.streams.values())
        )


def verify(path: str | os.PathLike[str], *, key: bytes | None = None) -> Report:
    """Verify every exchange session and stream of a transcript (section 10.3)."""
    out, records = iterate(path, key=key)
    report = Report(out.version, out.header)
    pending: dict[str, tuple[int, str, str]] = {}  # session -> (seq, request identity, op)
    last: dict[str, str] = {}  # session -> identity of the last kept response
    next_seq: dict[str, int] = {}
    seen: dict[str, set[str]] = {}  # session -> identities of its requests
    streams: dict[str, tuple[int, str, bool]] = {}  # stream -> (seq, identity, ended)
    previous_time = -1
    for index, record in enumerate(records):
        report.records += 1
        if record.time_ns < previous_time:
            report.problems.append(f"record {index}: its time is earlier than the record before it")
        previous_time = record.time_ns
        try:
            if _keyed(out):
                decoded = F.decode(record.frame, F.MAX_BOUND, key=key, check_digest=key is not None)
            else:
                decoded = F.decode(record.frame, F.MAX_BOUND)
        except FrameError as error:
            report.problems.append(f"record {index}: bad frame: {error}")
            continue
        message = decoded.message
        what = message_kind(message)
        try:
            if what == "request":
                check_request(message)
            elif what == "response":
                check_response(message)
            elif what == "stream":
                check_stream_message(message)
        except FrameError as error:
            report.problems.append(f"record {index}: {error}")
            continue
        if what == "request":
            _request(report, index, record, decoded, pending, last, next_seq, seen)
        elif what == "response":
            _response(report, index, record, decoded, pending, last, next_seq, seen)
        elif what == "stream":
            _stream(report, decoded, streams)
        else:
            report.problems.append(f"record {index}: not an NCP message")
    report.closed, report.truncated_at, report.chain_ok = out.closed, out.truncated_at, out.chain_ok
    report.problems.extend(out.problems)
    if out.version == 2 and not out.closed and out.truncated_at is None:
        report.problems.append("no end record: the recorder did not close the transcript")
    if out.truncated_at is not None:
        report.problems.append(f"the transcript is truncated at offset {out.truncated_at}")
    for session, (seq, _, _) in pending.items():
        report.sessions[session].problems.append(f"seq {seq}: no response")
    return report


def _keyed(out: Transcript) -> bool:
    return out.header is not None and out.header.get("chain") == "hmac-sha256"


def _request(
    report: Report,
    index: int,
    record: Record,
    decoded: F.Decoded,
    pending: dict[str, tuple[int, str, str]],
    last: dict[str, str],
    next_seq: dict[str, int],
    seen: dict[str, set[str]],
) -> None:
    message = decoded.message
    session, seq = message["session"], message["seq"]
    role = "client" if record.kind == SENT else "owner"
    entry = report.sessions.get(session)
    if entry is None:
        entry = report.sessions[session] = SessionReport(session, role)
    if role != entry.role:
        entry.problems.append(f"record {index}: a request in the direction of the other role")
    requests = seen.setdefault(session, set())
    if session in pending and pending[session][0] == seq:
        if pending[session][1] != decoded.identity:
            entry.problems.append(f"seq {seq}: two different requests outstanding")
        else:
            entry.repeats += 1
        return
    if decoded.identity in requests:
        entry.repeats += 1  # a delayed copy of an earlier request
        return
    expected = next_seq.get(session, 0)
    if seq != expected:
        entry.problems.append(f"seq {seq}: expected {expected}")
    if seq == 0:
        if message["op"] != "open" or message["ack"] is not None:
            entry.problems.append("seq 0 is not an open without ack")
    elif message["ack"] != last.get(session):
        entry.problems.append(f"seq {seq}: ack does not name the previous response")
    requests.add(decoded.identity)
    pending[session] = (seq, decoded.identity, message["op"])


def _response(
    report: Report,
    index: int,
    record: Record,
    decoded: F.Decoded,
    pending: dict[str, tuple[int, str, str]],
    last: dict[str, str],
    next_seq: dict[str, int],
    seen: dict[str, set[str]],
) -> None:
    message = decoded.message
    session = message["session"]
    if session is None:  # names no request: the bad-frame or shutdown response (section 6.2)
        outstanding = list(pending)
        if len(outstanding) != 1:
            report.problems.append(f"record {index}: a {message['code']} response that no single session awaits")
            return
        owner = outstanding[0]
        entry = report.sessions[owner]
        del pending[owner]
        entry.ended = message["code"]
        return
    entry = report.sessions.get(session)
    if entry is None:
        entry = report.sessions[session] = SessionReport(session, "client" if record.kind == RECEIVED else "owner")
        entry.problems.append(f"record {index}: a response before any request of the session")
        return
    expected_kind = RECEIVED if entry.role == "client" else SENT
    if record.kind != expected_kind:
        entry.problems.append(f"record {index}: a response in the direction of the other role")
    if session not in pending:
        if last.get(session) == decoded.identity or message["request"] in seen.get(session, ()):
            entry.repeats += 1  # a copy of a kept response, or a response to a copy of a request
        else:
            entry.problems.append(f"seq {message['seq']}: response without request")
        return
    seq, request_id, op = pending[session]
    if message["seq"] != seq or message["request"] != request_id:
        if message["request"] in seen.get(session, ()):
            entry.repeats += 1  # the response to an earlier copy
            return
        entry.problems.append(f"seq {message['seq']}: response names another request")
        return
    del pending[session]
    outcome = message["outcome"]
    if outcome == "rejected":
        entry.rejected += 1
        seen[session].discard(request_id)  # a corrected request may follow with the same seq
        return
    entry.requests += 1
    last[session] = decoded.identity
    next_seq[session] = seq + 1
    if outcome == "declined":
        entry.declined += 1
    elif outcome == "ended":
        entry.ended = message["code"]
    elif op == "close":
        entry.complete = True


def _stream(report: Report, decoded: F.Decoded, streams: dict[str, tuple[int, str, bool]]) -> None:
    message = decoded.message
    name, seq = message["stream"], message["seq"]
    entry = report.streams.setdefault(name, StreamReport(name))
    end = type(message["body"]) is dict and "ncp.end" in message["body"]
    state = streams.get(name)
    if state is None:
        streams[name] = (seq, decoded.identity, end)
        entry.accepted += 1
        entry.ended = end
        return
    last_seq, last_identity, ended = state
    if seq <= last_seq:
        if seq == last_seq and decoded.identity != last_identity:
            entry.problems.append(f"seq {seq}: two different messages")
        return
    if ended:
        entry.problems.append(f"seq {seq}: a message after the end of the stream")
        return
    if seq == last_seq + 1 and message["prev"] != last_identity:
        entry.problems.append(f"seq {seq}: broken chain")
        return
    entry.lost += seq - last_seq - 1
    entry.accepted += 1
    entry.ended = end
    streams[name] = (seq, decoded.identity, end)
