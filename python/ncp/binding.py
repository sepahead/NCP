"""The byte-stream binding: pipes, Unix domain sockets, and TCP (section 9.1)."""
from __future__ import annotations

import ipaddress
import os
import select
import socket
import subprocess
import sys
import threading
import time
from typing import Any, Callable, Sequence

from . import frame as F
from .exchange import Owner, bad_frame_response
from .frame import FrameError
from .transcript import RECEIVED, SENT, Tap

_READ_CHUNK = 1 << 16


class ChannelClosed(EOFError):
    """The peer closed the byte stream."""


class StreamChannel:
    """Frames over one reliable, ordered byte stream (a pipe pair or a socket)."""

    lossy = False

    def __init__(self, read: Callable[[int], bytes], write: Callable[[bytes], None], fileno: int, *,
                 tap: Tap | None = None, close: Callable[[], None] | None = None) -> None:
        self._read, self._write, self._fileno, self._close = read, write, fileno, close
        self._buffer = bytearray()
        self.tap = tap

    @classmethod
    def from_fds(cls, read_fd: int, write_fd: int, *, tap: Tap | None = None) -> "StreamChannel":
        def write(data: bytes) -> None:
            view = memoryview(data)
            while view:
                view = view[os.write(write_fd, view):]

        def close() -> None:
            for fd in {read_fd, write_fd}:
                try:
                    os.close(fd)
                except OSError:
                    pass

        return cls(lambda n: os.read(read_fd, n), write, read_fd, tap=tap, close=close)

    @classmethod
    def from_socket(cls, sock: socket.socket, *, tap: Tap | None = None) -> "StreamChannel":
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        return cls(sock.recv, sock.sendall, sock.fileno(), tap=tap, close=sock.close)

    def send(self, frame: bytes) -> None:
        self._write(frame)
        if self.tap is not None:
            self.tap.record(SENT, frame)

    def receive(self, bound: int, timeout: float | None, frame_timeout: float | None = None) -> bytes:
        """Return one complete frame. Raise FrameError for a bad header, TimeoutError, or
        ChannelClosed.

        `timeout` limits the whole wait. `frame_timeout` limits the time from the first byte of
        a frame to its last, which stops a slow sender from holding the receiver.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        if frame_timeout is not None:
            self._fill(1, deadline)
            limit = time.monotonic() + frame_timeout
            deadline = limit if deadline is None else min(deadline, limit)
        self._fill(F.HEADER_BYTES, deadline)
        total = F.HEADER_BYTES + F.remaining_length(self._buffer, bound)
        self._fill(total, deadline)
        frame = bytes(self._buffer[:total])
        del self._buffer[:total]
        if self.tap is not None:
            self.tap.record(RECEIVED, frame)
        return frame

    def _fill(self, size: int, deadline: float | None) -> None:
        while len(self._buffer) < size:
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self._fileno], [], [], remaining)[0]:
                    raise TimeoutError("no complete frame before the time limit")
            chunk = self._read(max(_READ_CHUNK, size - len(self._buffer)))
            if not chunk:
                raise ChannelClosed("the peer closed the stream")
            self._buffer += chunk

    def close(self) -> None:
        if self._close is not None:
            self._close()


def serve(owner: Owner, channel: StreamChannel, *, frame_timeout: float | None = None) -> None:
    """Serve one session on a byte stream until the peer closes it.

    A bad frame gets the bad-frame response, and the connection closes (section 9.1).
    """
    try:
        while True:
            try:
                frame = channel.receive(owner.bound, None, frame_timeout)
                response = owner.handle(frame)
            except (FrameError, TimeoutError):
                try:
                    channel.send(bad_frame_response())
                except OSError:
                    pass
                return
            channel.send(response)
    except (ChannelClosed, BrokenPipeError, ConnectionResetError):
        return
    finally:
        channel.close()


def serve_stdio(owner: Owner, *, tap: Tap | None = None) -> None:
    """Serve one session on standard input and output (section 9.1, rule 4).

    File descriptor 1 is kept for frames. Everything else written to standard output, including
    output from C libraries such as NEST, goes to standard error.
    """
    frames_out = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    serve(owner, StreamChannel.from_fds(0, frames_out, tap=tap))


def spawn(argv: Sequence[str], *, tap: Tap | None = None, env: dict[str, str] | None = None,
          cwd: str | None = None) -> tuple[StreamChannel, subprocess.Popen[bytes]]:
    """Start an owner process and return a channel to its standard input and output."""
    process = subprocess.Popen(list(argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0,
                               env=env, cwd=cwd)
    stdin, stdout = process.stdin, process.stdout
    assert stdin is not None and stdout is not None
    read_fd, write_fd = stdout.fileno(), stdin.fileno()

    def write(data: bytes) -> None:
        view = memoryview(data)
        while view:
            view = view[os.write(write_fd, view):]

    def close() -> None:
        # The Popen file objects own the descriptors; close them through those objects.
        for stream in (stdin, stdout):
            try:
                stream.close()
            except OSError:
                pass

    channel = StreamChannel(lambda n: os.read(read_fd, n), write, read_fd, tap=tap, close=close)
    return channel, process


def _check_address(host: str, allow_remote: bool) -> None:
    if allow_remote:
        return
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as error:
        raise ValueError(f"cannot resolve {host!r}") from error
    if not all(ipaddress.ip_address(address.split("%")[0]).is_loopback for address in addresses):
        raise ValueError(f"{host!r} is not a loopback address; pass allow_remote=True for a trusted "
                         "cluster network, or use a secure tunnel or the Zenoh binding")


def connect_tcp(host: str, port: int, *, allow_remote: bool = False, tap: Tap | None = None,
                timeout: float = 10.0) -> StreamChannel:
    _check_address(host, allow_remote)
    sock = socket.create_connection((host, port), timeout=timeout)
    sock.settimeout(None)
    return StreamChannel.from_socket(sock, tap=tap)


def connect_unix(path: str, *, tap: Tap | None = None, timeout: float = 10.0) -> StreamChannel:
    """Connect to an owner that listens on a Unix domain socket."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(timeout)
        sock.connect(path)
        sock.settimeout(None)
    except OSError:
        sock.close()
        raise
    return StreamChannel.from_socket(sock, tap=tap)


class _Server:
    def __init__(self, make_owner: Callable[[], Owner], listener: socket.socket) -> None:
        self._make_owner = make_owner
        self._socket = listener
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._stopped = False

    def start(self) -> "_Server":
        self._thread.start()
        return self

    def _accept(self) -> None:
        while not self._stopped:
            try:
                connection, _ = self._socket.accept()
            except OSError:
                return
            channel = StreamChannel.from_socket(connection)
            threading.Thread(target=serve, args=(self._make_owner(), channel), daemon=True).start()

    def stop(self) -> None:
        self._stopped = True
        self._socket.close()


class TcpServer(_Server):
    """Serve one owner session for each TCP connection, each in its own thread."""

    def __init__(self, make_owner: Callable[[], Owner], host: str = "127.0.0.1", port: int = 0, *,
                 allow_remote: bool = False) -> None:
        _check_address(host, allow_remote)
        super().__init__(make_owner, socket.create_server((host, port)))
        self.address: tuple[Any, ...] = self._socket.getsockname()


class UnixServer(_Server):
    """Serve one owner session for each connection to a Unix domain socket at `path`.

    Put the socket in a directory that only the users of the sessions can access.
    """

    def __init__(self, make_owner: Callable[[], Owner], path: str) -> None:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(path)
            listener.listen()
        except OSError:
            listener.close()
            raise
        super().__init__(make_owner, listener)
        self.address = path

    def stop(self) -> None:
        super().stop()
        try:
            os.unlink(self.address)
        except FileNotFoundError:
            pass
