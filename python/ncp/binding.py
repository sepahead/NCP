"""The byte-stream binding: pipes, Unix domain sockets, and TCP (specification section 9.1)."""

from __future__ import annotations

import collections
import ipaddress
import logging
import os
import select
import socket
import ssl
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from . import events as E
from . import frame as F
from .frame import FrameError
from .messages import bad_frame_response, nameless_binding, shutdown_response
from .owner import Owner, refuse
from .transcript import RECEIVED, SENT, Tap

# The kernel buffer size for Unix domain sockets and TCP connections. macOS gives Unix domain
# sockets 8 KiB buffers by default; a 1 MiB frame then crosses in 128 pieces and takes about 11
# times as long (benchmarks/comparison). The kernel uses the memory only while data waits.
SOCKET_BUFFER = 1 << 20
_LOG = logging.getLogger("ncp")


def _fd_reader(fd: int) -> Callable[[memoryview], int]:
    """read_into for a file descriptor: os.readv where the system has it, else a read and a copy."""
    if hasattr(os, "readv"):
        return lambda buffer: os.readv(fd, [buffer])

    def read_into(buffer: memoryview) -> int:  # pragma: no cover - Windows
        data = os.read(fd, len(buffer))
        buffer[: len(data)] = data
        return len(data)

    return read_into


class ChannelClosed(EOFError):
    """The peer closed the byte stream."""


class IdleTimeout(TimeoutError):
    """No byte of a frame arrived before the time limit."""


class StreamChannel:
    """Frames over one reliable, ordered byte stream (a pipe pair or a socket).

    `local` is true for a pipe pair and a Unix domain socket: the links on which an application
    may turn off the digest comparison (spec section 3, rule 5).
    """

    lossy = False

    def __init__(
        self,
        read_into: Callable[[memoryview], int],
        write: Callable[[bytes], None],
        fileno: int,
        *,
        tap: Tap | None = None,
        close: Callable[[], None] | None = None,
        local: bool = False,
        pending: Callable[[], int] | None = None,
    ) -> None:
        self._read_into, self._write, self._fileno, self._close = read_into, write, fileno, close
        self._pending = pending
        self._buffer = bytearray(1 << 16)
        self._start = self._end = 0  # unread bytes are _buffer[_start:_end]
        self.tap, self.local = tap, local

    @classmethod
    def from_fds(cls, read_fd: int, write_fd: int, *, tap: Tap | None = None) -> StreamChannel:
        def write(data: bytes) -> None:
            view = memoryview(data)
            while view:
                view = view[os.write(write_fd, view) :]

        def close() -> None:
            for fd in {read_fd, write_fd}:
                try:
                    os.close(fd)
                except OSError:
                    pass

        return cls(_fd_reader(read_fd), write, read_fd, tap=tap, close=close, local=True)

    @classmethod
    def from_socket(cls, sock: socket.socket, *, tap: Tap | None = None) -> StreamChannel:
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            # A MUST (specification 9.1, rule 6): without it, delayed acknowledgements can stall each
            # exchange. A connection on which it fails is not used; a server closes it and goes on.
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        for option in (socket.SO_SNDBUF, socket.SO_RCVBUF):
            try:
                sock.setsockopt(socket.SOL_SOCKET, option, SOCKET_BUFFER)
            except OSError:
                pass  # the kernel keeps its own limit
        local = getattr(socket, "AF_UNIX", None) is not None and sock.family == socket.AF_UNIX
        pending = sock.pending if isinstance(sock, ssl.SSLSocket) else None
        return cls(sock.recv_into, sock.sendall, sock.fileno(), tap=tap, close=sock.close, local=local, pending=pending)

    def send(self, frame: bytes) -> None:
        # The tap records the frame first (spec section 10.2), so that a transcript holds every
        # request that the peer may have executed, even if this program stops while sending.
        if self.tap is not None:
            self.tap.record(SENT, frame)
        self._write(frame)

    def receive(
        self, bound: int, timeout: float | None, frame_timeout: float | None = None, idle: float | None = None
    ) -> bytes:
        """Return one complete frame. Raise FrameError for a bad header, IdleTimeout when no byte
        of a frame arrived in time, TimeoutError when a frame did not complete in time, or
        ChannelClosed.

        `timeout` limits the whole wait. `idle` limits only the wait for the first byte.
        `frame_timeout` limits the time from the first byte of a frame to its last, which stops a
        slow sender from holding the receiver.
        """
        start = time.monotonic()
        deadline = None if timeout is None else start + timeout
        if frame_timeout is not None or idle is not None:
            first = deadline if idle is None else start + idle if deadline is None else min(deadline, start + idle)
            self._fill(1, first)
            if frame_timeout is not None:
                limit = time.monotonic() + frame_timeout
                deadline = limit if deadline is None else min(deadline, limit)
        self._fill(F.HEADER_BYTES, deadline)
        total = F.HEADER_BYTES + F.remaining_length(memoryview(self._buffer)[self._start : self._end], bound)
        self._fill(total, deadline)
        frame = bytes(memoryview(self._buffer)[self._start : self._start + total])
        self._start += total
        if self._start == self._end:
            self._start = self._end = 0
        if self.tap is not None:
            self.tap.record(RECEIVED, frame)
        return frame

    def _fill(self, size: int, deadline: float | None) -> None:
        """Read until `size` unread bytes are in the buffer, into a buffer that holds them."""
        while self._end - self._start < size:
            if self._start and self._end - self._start < size and len(self._buffer) - self._start < size:
                unread = self._end - self._start
                self._buffer[:unread] = self._buffer[self._start : self._end]
                self._start, self._end = 0, unread
            if len(self._buffer) < size:
                self._buffer.extend(bytes(size - len(self._buffer)))
            if deadline is not None and not (self._pending is not None and self._pending()):
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([self._fileno], [], [], remaining)[0]:
                    if self._end == self._start:
                        raise IdleTimeout("no frame before the time limit")
                    raise TimeoutError("no complete frame before the time limit")
            count = self._read_into(memoryview(self._buffer)[self._end :])
            if not count:
                raise ChannelClosed("the peer closed the stream")
            self._end += count

    def close(self) -> None:
        if self._close is not None:
            self._close()


class ChildChannel(StreamChannel):
    """A channel to an owner that runs as a child process, over its standard input and output.

    `close()` ends the child: it closes the child's standard input, which ends the session, waits
    `grace` seconds, then terminates and finally kills it, and reaps it. With `capture_stderr`,
    the channel keeps the last 50 lines of the child's standard error in `stderr_tail`.
    """

    def __init__(self, process: subprocess.Popen[bytes], *, tap: Tap | None, grace: float) -> None:
        stdin, stdout = process.stdin, process.stdout
        assert stdin is not None and stdout is not None
        read_fd, write_fd = stdout.fileno(), stdin.fileno()

        def write(data: bytes) -> None:
            view = memoryview(data)
            while view:
                view = view[os.write(write_fd, view) :]

        super().__init__(_fd_reader(read_fd), write, read_fd, tap=tap, local=True)
        self.process, self.grace = process, grace
        self.stderr_tail: collections.deque[str] = collections.deque(maxlen=50)
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for stream in (self.process.stdin, self.process.stdout):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        try:
            self.process.wait(self.grace)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(1.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()

    @property
    def returncode(self) -> int | None:
        return self.process.returncode


def spawn(
    argv: Sequence[str],
    *,
    tap: Tap | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    grace: float = 5.0,
    capture_stderr: bool = False,
) -> ChildChannel:
    """Start an owner process and return a channel to its standard input and output.

    Closing the channel ends the child (see `ChildChannel`). With `capture_stderr`, the child's
    standard error goes to `channel.stderr_tail` instead of this process's standard error.
    """
    process = subprocess.Popen(
        list(argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if capture_stderr else None,
        bufsize=0,
        env=env,
        cwd=cwd,
    )
    channel = ChildChannel(process, tap=tap, grace=grace)
    if capture_stderr:
        stream = process.stderr
        assert stream is not None

        def drain() -> None:
            for line in iter(stream.readline, b""):
                channel.stderr_tail.append(line.decode("utf-8", "replace").rstrip("\n"))

        threading.Thread(target=drain, daemon=True).start()
    return channel


@dataclass(frozen=True)
class TlsConfig:
    """TLS with certificates on both sides (spec section 13.3).

    `ca` is the file of the certificate authority that signs both sides. `cert` and `key` are
    this side's certificate chain and private key. A client checks that the server's certificate
    names `server_name`, which a client therefore needs (section 13.3); a server does not use it.
    """

    ca: str
    cert: str
    key: str
    server_name: str | None = None

    def server_context(self) -> ssl.SSLContext:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(self.cert, self.key)
        context.load_verify_locations(self.ca)
        context.verify_mode = ssl.CERT_REQUIRED
        return context

    def client_context(self) -> ssl.SSLContext:
        if not self.server_name:
            raise ValueError("a TLS client needs server_name: the client checks the server's name (section 13.3)")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.load_cert_chain(self.cert, self.key)
        context.load_verify_locations(self.ca)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        return context


def _chain(owner: Owner) -> dict[str, str]:
    """The members that bind a nameless response to the owner's chain (section 6.2)."""
    state = owner.state
    return nameless_binding(state.session, state.kept.identity if state.kept is not None else None)


def serve(
    owner: Owner,
    channel: StreamChannel,
    *,
    frame_timeout: float | None = None,
    idle_timeout: float | None = None,
    stop: threading.Event | None = None,
) -> str:
    """Serve one session on a byte stream until it ends. Return how it ended: "closed", "ended",
    "lost", "shutdown", or "bad_frame".

    A bad frame gets the bad-frame response, and the connection closes (rule 9.1.3). When `stop`
    is set, or no request arrives for `idle_timeout` seconds, the owner sends the shutdown
    response and closes (rule 9.1.9). It answers every request that it read first.
    """
    key = owner.config.key
    how = "lost"
    try:
        if not owner.check_digests and not channel.local:
            raise ValueError("the digest comparison can be turned off only on a pipe pair or a Unix domain socket")
        while True:
            if stop is not None and stop.is_set():
                how = "shutdown"
                _try_send(channel, shutdown_response(key=key, **_chain(owner)))
                return how
            try:
                frame = channel.receive(owner.bound, None, frame_timeout, idle_timeout)
            except IdleTimeout:
                how = "shutdown"
                _try_send(channel, shutdown_response(key=key, **_chain(owner)))
                return how
            except (FrameError, TimeoutError):
                how = "bad_frame"
                _try_send(channel, bad_frame_response(key=key, **_chain(owner)))
                return how
            except (ChannelClosed, OSError):
                if stop is not None and stop.is_set():
                    how = "shutdown"
                    _try_send(channel, shutdown_response(key=key, **_chain(owner)))
                return how
            try:
                response = owner.handle(frame)
            except FrameError:
                how = "bad_frame"
                _try_send(channel, bad_frame_response(key=key, **_chain(owner)))
                return how
            channel.send(response)
            if owner.closed:
                how = "closed"
    except (ChannelClosed, BrokenPipeError, ConnectionResetError):
        return how
    finally:
        channel.close()
        owner.finish(how)


def _try_send(channel: StreamChannel, frame: bytes) -> None:
    try:
        channel.send(frame)
    except OSError:
        pass


def serve_stdio(owner: Owner, *, tap: Tap | None = None) -> str:
    """Serve one session on standard input and output (rule 9.1.4).

    File descriptor 1 is kept for frames. Everything else written to standard output, including
    output from C libraries such as NEST, goes to standard error.
    """
    frames_out = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return serve(owner, StreamChannel.from_fds(0, frames_out, tap=tap))


def _resolve(host: str, port: int, allow_remote: bool) -> list[tuple[Any, ...]]:
    """Resolve once, and refuse addresses that are not loopback without the option (rule 9.1.6)."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"cannot resolve {host!r}") from error
    if not allow_remote and not all(
        ipaddress.ip_address(info[4][0].split("%")[0]).is_loopback for info in infos
    ):
        raise ValueError(
            f"{host!r} is not a loopback address; pass allow_remote=True for a trusted "
            "cluster network, and use TLS, a secure tunnel, or the Zenoh binding on other networks"
        )
    return infos


def connect_tcp(
    host: str,
    port: int,
    *,
    allow_remote: bool = False,
    tls: TlsConfig | None = None,
    tap: Tap | None = None,
    timeout: float = 10.0,
) -> StreamChannel:
    """Connect to a TCP owner. Remote addresses need `allow_remote` (rule 9.1.6); `tls` uses TLS
    with certificates on both sides (section 13.3)."""
    context = tls.client_context() if tls is not None else None  # before any connection
    name = tls.server_name if tls is not None else None
    last: OSError | None = None
    for family, kind, protocol, _, address in _resolve(host, port, allow_remote):
        sock = socket.socket(family, kind, protocol)
        try:
            sock.settimeout(timeout)
            sock.connect(address)
            if context is not None:
                sock = context.wrap_socket(sock, server_hostname=name)
            sock.settimeout(None)
            return StreamChannel.from_socket(sock, tap=tap)
        except OSError as error:
            sock.close()
            last = error
    assert last is not None
    raise last


def connect_unix(path: str, *, tap: Tap | None = None, timeout: float = 10.0) -> StreamChannel:
    """Connect to an owner that listens on a Unix domain socket.

    A refused connection is tried again until `timeout` seconds have passed. An owner refuses
    connections while its queue of connections that it has not yet accepted is full, for example
    when many agents start at once; macOS keeps at most 128 of them.
    """
    deadline = time.monotonic() + timeout
    pause = 0.001
    while True:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.settimeout(max(deadline - time.monotonic(), 0.001))
            sock.connect(path)
            sock.settimeout(None)
            break
        except (ConnectionRefusedError, BlockingIOError):
            sock.close()
            if time.monotonic() + pause >= deadline:
                raise
            time.sleep(pause)
            pause = min(2 * pause, 0.05)
        except OSError:
            sock.close()
            raise
    return StreamChannel.from_socket(sock, tap=tap)


@dataclass(frozen=True)
class Limits:
    """The limits of a server (specification, sections 9.1 and 12).

    `max_sessions` connections are served at once; a further connection gets `refused` for its
    `open`. `frame_timeout` limits the time from the first byte of a frame to its last.
    `idle_timeout`, if set, ends a session that sends no request for that long, with the shutdown
    response. `refuse_timeout` limits the wait for the first frame of a connection that the
    server refuses.
    """

    max_sessions: int = 256
    frame_timeout: float | None = 30.0
    idle_timeout: float | None = None
    refuse_timeout: float = 5.0

    def __post_init__(self) -> None:
        if self.max_sessions < 1:
            raise ValueError("max_sessions must be at least 1")


class _Server:
    def __init__(
        self,
        make_owner: Callable[[], Owner],
        listener: socket.socket,
        *,
        limits: Limits,
        tls: TlsConfig | None,
        observer: Any,
    ) -> None:
        self._make_owner, self._socket, self.limits = make_owner, listener, limits
        self._context = tls.server_context() if tls is not None else None
        self.observer = observer if observer is not None else E.DEFAULT
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active: dict[threading.Thread, socket.socket] = {}
        self._config: Any = None  # the configuration of the last owner, for refusals

    @property
    def sessions(self) -> int:
        """The number of sessions that the server serves now."""
        with self._lock:
            return len(self._active)

    def start(self) -> _Server:
        self._thread.start()
        return self

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._socket.accept()
            except OSError:
                if self._stop.is_set():
                    return
                time.sleep(0.01)  # transient: a peer that reset before accept, or no free descriptor
                continue
            if self._stop.is_set():
                connection.close()
                return
            threading.Thread(target=self._connection, args=(connection,), daemon=True).start()

    def _connection(self, connection: socket.socket) -> None:
        try:
            if self._context is not None:
                connection.settimeout(self.limits.refuse_timeout)
                connection = self._context.wrap_socket(connection, server_side=True)
                connection.settimeout(None)
            channel = StreamChannel.from_socket(connection)
        except OSError:  # the peer closed during setup, or TLS failed
            connection.close()
            return
        me = threading.current_thread()
        with self._lock:
            full = len(self._active) >= self.limits.max_sessions
            if not full:
                self._active[me] = connection
        if full:
            self.observer.event(E.Event("connection_refused", "server", detail="the server is full"))
            self._refuse(channel)
            return
        try:
            try:
                owner = self._make_owner()
            except Exception as error:  # noqa: BLE001 - a defect of the owner factory; report it and go on
                channel.close()
                self.observer.event(E.Event("server_error", "server", detail="the owner factory failed", error=error))
                return
            self._config = owner.config
            try:
                serve(
                    owner,
                    channel,
                    frame_timeout=self.limits.frame_timeout,
                    idle_timeout=self.limits.idle_timeout,
                    stop=self._stop,
                )
            except Exception as error:  # noqa: BLE001 - one session's failure must not go unseen
                self.observer.event(E.Event("server_error", "server", detail="a session failed", error=error))
        finally:
            with self._lock:
                self._active.pop(me, None)

    def _refuse(self, channel: StreamChannel) -> None:
        try:
            config = self._config
            frame = channel.receive(F.HANDSHAKE_BOUND, self.limits.refuse_timeout, self.limits.refuse_timeout)
            if config is not None:
                channel.send(refuse(config, F.decode(frame, F.HANDSHAKE_BOUND, key=config.key)))
        except (FrameError, OSError, EOFError):
            pass
        finally:
            channel.close()

    def stop(self, grace: float = 5.0) -> None:
        """Stop: accept no connection, end every session with the shutdown response after it
        answered the request that it reads (rule 9.1.9), and wait up to `grace` seconds."""
        self._stop.set()
        try:
            self._socket.shutdown(socket.SHUT_RDWR)  # wakes a blocked accept on Linux; close alone does not
        except OSError:
            pass  # macOS refuses it on a listening socket, and there close wakes accept
        self._socket.close()
        with self._lock:
            active = list(self._active.items())
        for _, connection in active:
            try:
                connection.shutdown(socket.SHUT_RD)  # wakes the session's read; it then answers shutdown
            except OSError:
                pass
        deadline = time.monotonic() + grace
        for thread, _ in active:
            thread.join(max(0.0, deadline - time.monotonic()))


class TcpServer(_Server):
    """Serve one owner session for each TCP connection, each in its own thread."""

    def __init__(
        self,
        make_owner: Callable[[], Owner],
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        allow_remote: bool = False,
        tls: TlsConfig | None = None,
        limits: Limits = Limits(),
        observer: Any = None,
    ) -> None:
        _resolve(host, port, allow_remote)
        super().__init__(
            make_owner,
            socket.create_server((host, port), backlog=socket.SOMAXCONN),
            limits=limits,
            tls=tls,
            observer=observer,
        )
        self.address: tuple[Any, ...] = self._socket.getsockname()


class UnixServer(_Server):
    """Serve one owner session for each connection to a Unix domain socket at `path`.

    The socket file gets the mode 0600. Put it in a directory that only the users of the sessions
    can access; the server logs a warning when other users can enter the directory (rule 9.1.5).
    """

    def __init__(
        self,
        make_owner: Callable[[], Owner],
        path: str,
        *,
        limits: Limits = Limits(),
        mode: int = 0o600,
        observer: Any = None,
    ) -> None:
        directory = os.path.dirname(os.path.abspath(path))
        if os.stat(directory).st_mode & (stat.S_IWOTH | stat.S_IXOTH):
            _LOG.warning("ncp: other users can enter %s, the directory of %s", directory, path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(path)
            os.chmod(path, mode)
            listener.listen(socket.SOMAXCONN)
        except OSError:
            listener.close()
            raise
        super().__init__(make_owner, listener, limits=limits, tls=None, observer=observer)
        self.address = path

    def stop(self, grace: float = 5.0) -> None:
        super().stop(grace)
        try:
            os.unlink(self.address)
        except FileNotFoundError:
            pass
