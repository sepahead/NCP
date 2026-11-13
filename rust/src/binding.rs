//! The byte-stream binding: pipes, Unix domain sockets, and TCP (section 9.1).

use crate::client::{Channel, ChannelError};
use crate::events::{default_observer, Event, Observer};
use crate::frame::{self, FrameError, HANDSHAKE_BOUND, HEADER_BYTES};
use crate::messages::{bad_frame_response, shutdown_response};
use crate::owner::{refuse, Handler, Owner, OwnerConfig};
use crate::transcript::{Tap, RECEIVED, SENT};
use std::collections::HashMap;
use std::io::{self, Read, Write};
use std::net::{Shutdown, SocketAddr, TcpListener, TcpStream, ToSocketAddrs};
use std::process::{Child, ChildStdin, ChildStdout, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

/// The kernel buffer size that the binding sets for Unix domain sockets and TCP connections.
///
/// macOS gives Unix domain sockets 8 KiB buffers by default; a 1 MiB frame then crosses in 128
/// pieces and takes about 11 times as long (benchmarks/comparison). The kernel uses the memory
/// only while data waits. A smaller system limit applies without an error.
pub const SOCKET_BUFFER: usize = 1 << 20;

fn enlarge_buffers(socket: socket2::SockRef<'_>) {
    // Ignored on failure: the kernel then keeps its own limit.
    let _ = socket.set_send_buffer_size(SOCKET_BUFFER);
    let _ = socket.set_recv_buffer_size(SOCKET_BUFFER);
}

/// Why a receive with time limits returned no frame.
#[derive(Debug)]
pub enum ReceiveError {
    /// No byte of a frame arrived before the time limit.
    Idle,
    /// A frame started but did not complete before the time limit.
    Timeout,
    /// A bad header: wrong magic, or a length above the bound or the JSON limit.
    BadFrame(FrameError),
    /// The stream closed or failed.
    Closed(io::Error),
}

type TimeoutSetter = Box<dyn Fn(Option<Duration>) -> io::Result<()> + Send>;

/// Frames over one reliable, ordered byte stream.
pub struct StreamChannel<R: Read, W: Write> {
    reader: R,
    writer: Option<W>,
    buffer: Vec<u8>,
    start: usize,
    end: usize,
    tap: Option<Arc<Tap>>,
    closer: Option<Box<dyn FnMut() + Send>>,
    timeouts: Option<TimeoutSetter>,
    timeout: Option<Duration>,
    local: bool,
}

impl<R: Read, W: Write> std::fmt::Debug for StreamChannel<R, W> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("StreamChannel")
            .field("open", &self.writer.is_some())
            .field("local", &self.local)
            .field("tap", &self.tap.is_some())
            .finish_non_exhaustive()
    }
}

impl<R: Read, W: Write> StreamChannel<R, W> {
    /// A channel over a reader and a writer. `local` is true for a pipe pair and a Unix domain
    /// socket: the links on which the digest comparison may be turned off (section 3, rule 5).
    pub fn new(reader: R, writer: W) -> StreamChannel<R, W> {
        StreamChannel {
            reader,
            writer: Some(writer),
            buffer: vec![0; 1 << 16],
            start: 0,
            end: 0,
            tap: None,
            closer: None,
            timeouts: None,
            timeout: None,
            local: false,
        }
    }

    /// Mark the channel as a pipe pair or a Unix domain socket.
    pub fn local(mut self) -> StreamChannel<R, W> {
        self.local = true;
        self
    }

    /// Record every frame in a transcript (section 10).
    pub fn with_tap(mut self, tap: Arc<Tap>) -> StreamChannel<R, W> {
        self.tap = Some(tap);
        self
    }

    /// The time limit for each response that a client waits for. It works on sockets; a pipe
    /// takes no time limit (start a child with [`spawn_unix`] to give it one).
    pub fn set_timeout(&mut self, timeout: Option<Duration>) {
        self.timeout = timeout;
    }

    /// Send one frame. The tap records it first (section 10.2), so that a transcript holds
    /// every request that the peer may have executed, even if this program stops while sending.
    pub fn send_frame(&mut self, frame: &[u8]) -> io::Result<()> {
        let writer = self
            .writer
            .as_mut()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "channel closed"))?;
        if let Some(tap) = &self.tap {
            tap.record(SENT, frame)?;
        }
        writer.write_all(frame)?;
        writer.flush()
    }

    /// Read until `size` unread bytes are in the buffer, before `deadline`.
    fn fill(&mut self, size: usize, deadline: Option<Instant>) -> Result<(), ReceiveError> {
        while self.end - self.start < size {
            if self.buffer.len() - self.start < size {
                self.buffer.copy_within(self.start..self.end, 0);
                self.end -= self.start;
                self.start = 0;
                if self.buffer.len() < size {
                    self.buffer.resize(size, 0);
                }
            }
            if let (Some(deadline), Some(set)) = (deadline, &self.timeouts) {
                let remaining = deadline.saturating_duration_since(Instant::now());
                if remaining.is_zero() {
                    return Err(if self.end == self.start {
                        ReceiveError::Idle
                    } else {
                        ReceiveError::Timeout
                    });
                }
                set(Some(remaining)).map_err(ReceiveError::Closed)?;
            }
            match self.reader.read(&mut self.buffer[self.end..]) {
                Ok(0) => {
                    return Err(ReceiveError::Closed(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "the peer closed the stream",
                    )))
                }
                Ok(count) => self.end += count,
                Err(error)
                    if matches!(
                        error.kind(),
                        io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut
                    ) =>
                {
                    return Err(if self.end == self.start {
                        ReceiveError::Idle
                    } else {
                        ReceiveError::Timeout
                    });
                }
                Err(error) if error.kind() == io::ErrorKind::Interrupted => {}
                Err(error) => return Err(ReceiveError::Closed(error)),
            }
        }
        Ok(())
    }

    /// Receive one complete frame, checking its header against `bound`. `timeout` limits the
    /// whole wait; `idle` limits only the wait for the first byte; `frame_limit` limits the time
    /// from the first byte to the last, which stops a slow sender from holding the receiver.
    pub fn receive_with(
        &mut self,
        bound: usize,
        timeout: Option<Duration>,
        idle: Option<Duration>,
        frame_limit: Option<Duration>,
    ) -> Result<Vec<u8>, ReceiveError> {
        let start = Instant::now();
        let whole = timeout.map(|d| start + d);
        let earliest = |a: Option<Instant>, b: Option<Instant>| match (a, b) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        };
        self.fill(1, earliest(whole, idle.map(|d| start + d)))?;
        let deadline = earliest(whole, frame_limit.map(|d| Instant::now() + d));
        self.fill(HEADER_BYTES, deadline)?;
        let rest = frame::remaining_length(&self.buffer[self.start..self.end], bound)
            .map_err(ReceiveError::BadFrame)?;
        let total = HEADER_BYTES + rest;
        self.fill(total, deadline)?;
        let frame = self.buffer[self.start..self.start + total].to_vec();
        self.start += total;
        if self.start == self.end {
            self.start = 0;
            self.end = 0;
        }
        if let Some(set) = &self.timeouts {
            let _ = set(None);
        }
        if let Some(tap) = &self.tap {
            tap.record(RECEIVED, &frame).map_err(ReceiveError::Closed)?;
        }
        Ok(frame)
    }

    /// Receive one complete frame with the channel's time limit, checking its header against
    /// `bound`.
    pub fn receive_frame(&mut self, bound: usize) -> Result<Vec<u8>, ChannelError> {
        match self.receive_with(bound, self.timeout, None, None) {
            Ok(frame) => Ok(frame),
            Err(ReceiveError::Idle | ReceiveError::Timeout) => Err(ChannelError::Timeout),
            Err(ReceiveError::BadFrame(error)) => Err(ChannelError::BadFrame(error)),
            Err(ReceiveError::Closed(error)) => Err(ChannelError::Closed(error)),
        }
    }

    fn close_now(&mut self) {
        // Dropping the writer closes a pipe, so a child owner sees end of file and exits.
        if let Some(mut writer) = self.writer.take() {
            let _ = writer.flush();
        }
        if let Some(mut closer) = self.closer.take() {
            closer();
        }
    }
}

impl<R: Read, W: Write> Channel for StreamChannel<R, W> {
    fn lossy(&self) -> bool {
        false
    }
    fn local(&self) -> bool {
        self.local
    }
    fn send(&mut self, frame: &[u8]) -> io::Result<()> {
        self.send_frame(frame)
    }
    fn receive(&mut self, bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.receive_frame(bound)
    }
    fn close(&mut self) {
        self.close_now();
    }
}

/// Options of [`serve_with`].
#[derive(Debug, Clone, Default)]
pub struct ServeOptions {
    /// The time from the first byte of a frame to its last.
    pub frame_timeout: Option<Duration>,
    /// End the session with the shutdown response when no request arrives for this long.
    pub idle_timeout: Option<Duration>,
    /// When set, end the session with the shutdown response (rule 9.1.9).
    pub stop: Option<Arc<AtomicBool>>,
}

/// Serve one session on a byte stream until it ends. Returns how it ended: "closed", "ended",
/// "lost", "shutdown", or "bad_frame".
pub fn serve<H: Handler, R: Read, W: Write>(
    owner: &mut Owner<H>,
    channel: &mut StreamChannel<R, W>,
) -> io::Result<&'static str> {
    serve_with(owner, channel, &ServeOptions::default())
}

/// As [`serve`], with time limits and a stop flag.
///
/// A bad frame gets the bad-frame response, and the connection closes (rule 9.1.3). When the
/// stop flag is set, or no request arrives for `idle_timeout`, the owner sends the shutdown
/// response and closes (rule 9.1.9). It answers every request that it read first.
pub fn serve_with<H: Handler, R: Read, W: Write>(
    owner: &mut Owner<H>,
    channel: &mut StreamChannel<R, W>,
    options: &ServeOptions,
) -> io::Result<&'static str> {
    let key = owner.key().cloned();
    let stopped = || {
        options
            .stop
            .as_ref()
            .is_some_and(|s| s.load(Ordering::Acquire))
    };
    let result = (|| {
        if !owner.check_digests() && !channel.local {
            return Err(io::Error::other(
                "the digest comparison can be turned off only on a pipe pair or a Unix domain socket",
            ));
        }
        let mut how = "lost";
        loop {
            if stopped() {
                let _ = channel.send_frame(&shutdown_response(key.as_ref()));
                return Ok("shutdown");
            }
            let frame_bytes = match channel.receive_with(
                owner.bound(),
                None,
                options.idle_timeout,
                options.frame_timeout,
            ) {
                Ok(bytes) => bytes,
                Err(ReceiveError::Idle) => {
                    let _ = channel.send_frame(&shutdown_response(key.as_ref()));
                    return Ok("shutdown");
                }
                Err(ReceiveError::BadFrame(_) | ReceiveError::Timeout) => {
                    let _ = channel.send_frame(&bad_frame_response(key.as_ref()));
                    return Ok("bad_frame");
                }
                Err(ReceiveError::Closed(error)) => {
                    if stopped() {
                        let _ = channel.send_frame(&shutdown_response(key.as_ref()));
                        return Ok("shutdown");
                    }
                    return match error.kind() {
                        io::ErrorKind::UnexpectedEof
                        | io::ErrorKind::BrokenPipe
                        | io::ErrorKind::ConnectionReset => Ok(how),
                        _ => Err(error),
                    };
                }
            };
            match owner.handle(frame_bytes) {
                Ok(response) => {
                    if let Err(error) = channel.send_frame(&response) {
                        return if error.kind() == io::ErrorKind::BrokenPipe {
                            Ok(how)
                        } else {
                            Err(error)
                        };
                    }
                    if owner.closed() {
                        how = "closed";
                    }
                }
                Err(FrameError(_)) => {
                    let _ = channel.send_frame(&bad_frame_response(key.as_ref()));
                    return Ok("bad_frame");
                }
            }
        }
    })();
    channel.close_now();
    owner.finish(match &result {
        Ok(how) => how,
        Err(_) => "lost",
    });
    result
}

/// Serve one session on standard input and output (rule 9.1.4). The owner must not write
/// anything else to standard output.
pub fn serve_stdio<H: Handler>(owner: &mut Owner<H>) -> io::Result<&'static str> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut channel = StreamChannel::new(stdin.lock(), stdout.lock()).local();
    serve(owner, &mut channel)
}

/// A channel to an owner that runs as a child process.
///
/// `close()`, and dropping the channel, end the child: the channel closes the child's standard
/// input, which ends the session, waits the grace time (5 s by default), then kills the child
/// and reaps it.
pub struct ChildChannel<R: Read, W: Write> {
    channel: StreamChannel<R, W>,
    child: Child,
    grace: Duration,
    closed: bool,
    status: Option<ExitStatus>,
}

impl<R: Read, W: Write> std::fmt::Debug for ChildChannel<R, W> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ChildChannel")
            .field("pid", &self.child.id())
            .field("closed", &self.closed)
            .finish_non_exhaustive()
    }
}

impl<R: Read, W: Write> ChildChannel<R, W> {
    /// Wait this long for the child to exit after its input closed (default 5 s).
    pub fn with_grace(mut self, grace: Duration) -> ChildChannel<R, W> {
        self.grace = grace;
        self
    }

    /// Record every frame in a transcript (section 10).
    pub fn with_tap(mut self, tap: Arc<Tap>) -> ChildChannel<R, W> {
        self.channel.tap = Some(tap);
        self
    }

    /// The child process.
    pub fn child(&mut self) -> &mut Child {
        &mut self.child
    }

    /// The time limit for each response; it works when the channel is a socket ([`spawn_unix`]).
    pub fn set_timeout(&mut self, timeout: Option<Duration>) {
        self.channel.set_timeout(timeout);
    }

    /// The child's exit status, once the channel is closed.
    pub fn exit_status(&self) -> Option<ExitStatus> {
        self.status
    }

    fn end(&mut self) {
        if self.closed {
            return;
        }
        self.closed = true;
        self.channel.close_now();
        let deadline = Instant::now() + self.grace;
        loop {
            match self.child.try_wait() {
                Ok(Some(status)) => {
                    self.status = Some(status);
                    return;
                }
                Ok(None) if Instant::now() < deadline => {
                    std::thread::sleep(Duration::from_millis(5))
                }
                _ => break,
            }
        }
        let _ = self.child.kill();
        self.status = self.child.wait().ok();
    }
}

impl<R: Read, W: Write> Channel for ChildChannel<R, W> {
    fn lossy(&self) -> bool {
        false
    }
    fn local(&self) -> bool {
        true
    }
    fn send(&mut self, frame: &[u8]) -> io::Result<()> {
        self.channel.send_frame(frame)
    }
    fn receive(&mut self, bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.channel.receive_frame(bound)
    }
    fn close(&mut self) {
        self.end();
    }
}

impl<R: Read, W: Write> Drop for ChildChannel<R, W> {
    fn drop(&mut self) {
        self.end();
    }
}

/// A channel to a child owner over its standard input and output.
pub type PipeChild = ChildChannel<ChildStdout, ChildStdin>;

/// Start an owner process and return a channel to its standard input and output. A pipe takes
/// no time limit; start the child with [`spawn_unix`] to give it one.
pub fn spawn(mut command: Command) -> io::Result<PipeChild> {
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()?;
    let stdin = child
        .stdin
        .take()
        .ok_or_else(|| io::Error::other("no stdin"))?;
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| io::Error::other("no stdout"))?;
    Ok(ChildChannel {
        channel: StreamChannel::new(stdout, stdin).local(),
        child,
        grace: Duration::from_secs(5),
        closed: false,
        status: None,
    })
}

/// A channel to a child owner whose standard input and output are one end of a Unix domain
/// socket pair: it takes a time limit ([`ChildChannel::set_timeout`]).
#[cfg(unix)]
pub type UnixChild = ChildChannel<std::os::unix::net::UnixStream, std::os::unix::net::UnixStream>;

/// Start an owner process whose standard input and output are one end of a Unix domain socket
/// pair, and return a channel to the other end. The owner serves its standard input and output
/// as it would serve pipes.
#[cfg(unix)]
pub fn spawn_unix(mut command: Command) -> io::Result<UnixChild> {
    let (parent, child_end) = std::os::unix::net::UnixStream::pair()?;
    let input = std::os::fd::OwnedFd::from(child_end.try_clone()?);
    let output = std::os::fd::OwnedFd::from(child_end);
    let child = command
        .stdin(Stdio::from(input))
        .stdout(Stdio::from(output))
        .spawn()?;
    // Dropping the command closes this process's copies of the child's end, so that the channel
    // sees the end of the stream when the child exits.
    drop(command);
    Ok(ChildChannel {
        channel: unix_channel(parent)?,
        child,
        grace: Duration::from_secs(5),
        closed: false,
        status: None,
    })
}

fn resolve(address: impl ToSocketAddrs, allow_remote: bool) -> io::Result<Vec<SocketAddr>> {
    let addresses: Vec<SocketAddr> = address.to_socket_addrs()?.collect();
    if allow_remote || addresses.iter().all(|a| a.ip().is_loopback()) {
        Ok(addresses)
    } else {
        Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "not a loopback address; allow remote addresses only on a trusted cluster network, \
             and use TLS, a secure tunnel, or the Zenoh binding on other networks",
        ))
    }
}

/// A channel over a TCP connection.
pub type TcpChannel = StreamChannel<TcpStream, TcpStream>;

/// Connect to a TCP owner. The name is resolved once, and remote addresses need `allow_remote`
/// (rule 9.1.6).
pub fn connect_tcp(address: impl ToSocketAddrs, allow_remote: bool) -> io::Result<TcpChannel> {
    let addresses = resolve(address, allow_remote)?;
    let stream = TcpStream::connect(&addresses[..])?;
    tcp_channel(stream)
}

/// Wrap an accepted or connected TCP stream: sets TCP_NODELAY, which rule 9.1.6 requires (an
/// error if it fails, for example on macOS after the peer has closed), and tries to set
/// [`SOCKET_BUFFER`].
pub fn tcp_channel(stream: TcpStream) -> io::Result<TcpChannel> {
    stream.set_nodelay(true)?;
    enlarge_buffers(socket2::SockRef::from(&stream));
    let writer = stream.try_clone()?;
    let closer = stream.try_clone()?;
    let timeouts = stream.try_clone()?;
    let mut channel = StreamChannel::new(stream, writer);
    channel.closer = Some(Box::new(move || {
        let _ = closer.shutdown(Shutdown::Both);
    }));
    channel.timeouts = Some(Box::new(move |t| timeouts.set_read_timeout(t)));
    Ok(channel)
}

/// Bind a TCP listener. Remote addresses need `allow_remote`.
pub fn listen_tcp(address: impl ToSocketAddrs, allow_remote: bool) -> io::Result<TcpListener> {
    TcpListener::bind(&resolve(address, allow_remote)?[..])
}

/// A channel over a Unix domain socket connection.
#[cfg(unix)]
pub type UnixChannel =
    StreamChannel<std::os::unix::net::UnixStream, std::os::unix::net::UnixStream>;

/// How long [`connect_unix`] tries a refused connection again.
pub const CONNECT_PATIENCE: Duration = Duration::from_secs(10);

/// Connect to an owner that listens on a Unix domain socket (rule 9.1.5).
///
/// A refused connection is tried again for up to [`CONNECT_PATIENCE`]. An owner refuses
/// connections while its queue of connections that it has not yet accepted is full, for example
/// when many agents start at once; macOS keeps at most 128 of them.
#[cfg(unix)]
pub fn connect_unix(path: impl AsRef<std::path::Path>) -> io::Result<UnixChannel> {
    let deadline = Instant::now() + CONNECT_PATIENCE;
    let mut pause = Duration::from_millis(1);
    loop {
        match std::os::unix::net::UnixStream::connect(path.as_ref()) {
            Ok(stream) => return unix_channel(stream),
            Err(error)
                if matches!(
                    error.kind(),
                    io::ErrorKind::ConnectionRefused | io::ErrorKind::WouldBlock
                ) && Instant::now() + pause < deadline =>
            {
                std::thread::sleep(pause);
                pause = (pause * 2).min(Duration::from_millis(50));
            }
            Err(error) => return Err(error),
        }
    }
}

/// Wrap an accepted or connected Unix domain socket stream: sets [`SOCKET_BUFFER`].
#[cfg(unix)]
pub fn unix_channel(stream: std::os::unix::net::UnixStream) -> io::Result<UnixChannel> {
    enlarge_buffers(socket2::SockRef::from(&stream));
    let writer = stream.try_clone()?;
    let closer = stream.try_clone()?;
    let timeouts = stream.try_clone()?;
    let mut channel = StreamChannel::new(stream, writer).local();
    channel.closer = Some(Box::new(move || {
        let _ = closer.shutdown(Shutdown::Both);
    }));
    channel.timeouts = Some(Box::new(move |t| timeouts.set_read_timeout(t)));
    Ok(channel)
}

/// The sessions that a server serves now, each with the function that ends its reads.
type Sessions = Arc<Mutex<HashMap<u64, Box<dyn Fn() + Send>>>>;

/// The limits of a server (specification, sections 9.1 and 12).
#[derive(Debug, Clone)]
pub struct Limits {
    /// Connections served at once; a further connection gets `refused` for its `open`.
    pub max_sessions: usize,
    /// The time from the first byte of a frame to its last.
    pub frame_timeout: Option<Duration>,
    /// End a session that sends no request for this long, with the shutdown response.
    pub idle_timeout: Option<Duration>,
    /// The wait for the first frame of a connection that the server refuses.
    pub refuse_timeout: Duration,
}

impl Default for Limits {
    fn default() -> Limits {
        Limits {
            max_sessions: 256,
            frame_timeout: Some(Duration::from_secs(30)),
            idle_timeout: None,
            refuse_timeout: Duration::from_secs(5),
        }
    }
}

/// A server: one owner session for each connection, each in its own thread.
pub struct Server {
    stop: Arc<AtomicBool>,
    active: Sessions,
    accept: Option<JoinHandle<()>>,
    wake: Box<dyn Fn() + Send>,
    address: String,
    path: Option<std::path::PathBuf>,
}

impl std::fmt::Debug for Server {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Server")
            .field("address", &self.address)
            .finish_non_exhaustive()
    }
}

impl Server {
    /// The address: `PATH` for a Unix domain socket, `HOST:PORT` for TCP.
    pub fn address(&self) -> &str {
        &self.address
    }

    /// The number of sessions that the server serves now.
    pub fn sessions(&self) -> usize {
        self.active.lock().map_or(0, |a| a.len())
    }

    /// Stop: accept no connection, end every session with the shutdown response after it
    /// answered the request that it reads (rule 9.1.9), and wait up to `grace`.
    pub fn stop(&mut self, grace: Duration) {
        if self.stop.swap(true, Ordering::AcqRel) {
            return;
        }
        (self.wake)();
        if let Some(accept) = self.accept.take() {
            let _ = accept.join();
        }
        if let Ok(active) = self.active.lock() {
            for shut in active.values() {
                shut();
            }
        }
        let deadline = Instant::now() + grace;
        while self.sessions() > 0 && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(5));
        }
        if let Some(path) = self.path.take() {
            let _ = std::fs::remove_file(path);
        }
    }
}

impl Drop for Server {
    fn drop(&mut self) {
        self.stop(Duration::from_secs(1));
    }
}

struct Shared<F> {
    make_owner: F,
    limits: Limits,
    stop: Arc<AtomicBool>,
    active: Sessions,
    config: Mutex<Option<OwnerConfig>>,
    observer: Arc<dyn Observer>,
    next: AtomicU64,
}

impl<F> Shared<F> {
    fn report(&self, kind: &'static str, detail: &str, error: Option<String>) {
        self.observer.event(&Event {
            kind,
            role: "server",
            detail: Some(detail.to_owned()),
            error,
            ..Event::default()
        });
    }
}

fn session<F, H, R, W>(
    shared: &Shared<F>,
    mut channel: StreamChannel<R, W>,
    shut: Box<dyn Fn() + Send>,
) where
    F: Fn() -> Owner<H>,
    H: Handler,
    R: Read,
    W: Write,
{
    let id = shared.next.fetch_add(1, Ordering::Relaxed);
    let full = {
        let mut active = match shared.active.lock() {
            Ok(active) => active,
            Err(_) => return,
        };
        if active.len() >= shared.limits.max_sessions {
            true
        } else {
            active.insert(id, shut);
            false
        }
    };
    if full {
        shared.report("connection_refused", "the server is full", None);
        let config = shared.config.lock().ok().and_then(|c| c.clone());
        let limit = Some(shared.limits.refuse_timeout);
        if let (Ok(bytes), Some(config)) = (
            channel.receive_with(HANDSHAKE_BOUND, limit, None, limit),
            config,
        ) {
            let verify = match &config.key {
                Some(key) => frame::Verify::Key(key),
                None => frame::Verify::Digest,
            };
            if let Ok(decoded) = frame::decode_verified(bytes, HANDSHAKE_BOUND, verify) {
                if let Ok(response) = refuse(&config, &decoded, "") {
                    let _ = channel.send_frame(&response);
                }
            }
        }
        channel.close_now();
        return;
    }
    if !shared.stop.load(Ordering::Acquire) {
        let mut owner = (shared.make_owner)();
        if let Ok(mut config) = shared.config.lock() {
            *config = Some(owner.config().clone());
        }
        let options = ServeOptions {
            frame_timeout: shared.limits.frame_timeout,
            idle_timeout: shared.limits.idle_timeout,
            stop: Some(shared.stop.clone()),
        };
        if let Err(error) = serve_with(&mut owner, &mut channel, &options) {
            shared.report("server_error", "a session failed", Some(error.to_string()));
        }
    }
    if let Ok(mut active) = shared.active.lock() {
        active.remove(&id);
    }
}

/// Serve one owner session for each connection to a Unix domain socket at `path`, each in its
/// own thread. The socket file gets the mode 0600; put it in a directory that only the users of
/// the sessions can access (rule 9.1.5).
#[cfg(unix)]
pub fn serve_unix<F, H>(
    path: impl AsRef<std::path::Path>,
    make_owner: F,
    limits: Limits,
) -> io::Result<Server>
where
    F: Fn() -> Owner<H> + Send + Sync + 'static,
    H: Handler + 'static,
{
    use std::os::unix::fs::PermissionsExt;
    let path = path.as_ref().to_path_buf();
    let listener = std::os::unix::net::UnixListener::bind(&path)?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    let stop = Arc::new(AtomicBool::new(false));
    let active: Sessions = Arc::default();
    let shared = Arc::new(Shared {
        make_owner,
        limits,
        stop: stop.clone(),
        active: active.clone(),
        config: Mutex::new(None),
        observer: default_observer(),
        next: AtomicU64::new(0),
    });
    let accept_stop = stop.clone();
    let accept = std::thread::spawn(move || {
        for stream in listener.incoming() {
            if accept_stop.load(Ordering::Acquire) {
                return;
            }
            let Ok(stream) = stream else { continue };
            let shared = shared.clone();
            std::thread::spawn(move || {
                let Ok(shutter) = stream.try_clone() else {
                    return;
                };
                let Ok(channel) = unix_channel(stream) else {
                    return;
                };
                let shut: Box<dyn Fn() + Send> = Box::new(move || {
                    let _ = shutter.shutdown(Shutdown::Read);
                });
                session(&shared, channel, shut);
            });
        }
    });
    let wake_path = path.clone();
    Ok(Server {
        stop,
        active,
        accept: Some(accept),
        wake: Box::new(move || {
            let _ = std::os::unix::net::UnixStream::connect(&wake_path);
        }),
        address: path.display().to_string(),
        path: Some(path),
    })
}

/// Serve one owner session for each TCP connection, each in its own thread. Remote addresses
/// need `allow_remote` (rule 9.1.6).
pub fn serve_tcp<F, H>(
    address: impl ToSocketAddrs,
    allow_remote: bool,
    make_owner: F,
    limits: Limits,
) -> io::Result<Server>
where
    F: Fn() -> Owner<H> + Send + Sync + 'static,
    H: Handler + 'static,
{
    let listener = listen_tcp(address, allow_remote)?;
    let local = listener.local_addr()?;
    let stop = Arc::new(AtomicBool::new(false));
    let active: Sessions = Arc::default();
    let shared = Arc::new(Shared {
        make_owner,
        limits,
        stop: stop.clone(),
        active: active.clone(),
        config: Mutex::new(None),
        observer: default_observer(),
        next: AtomicU64::new(0),
    });
    let accept_stop = stop.clone();
    let accept = std::thread::spawn(move || {
        for stream in listener.incoming() {
            if accept_stop.load(Ordering::Acquire) {
                return;
            }
            let Ok(stream) = stream else { continue };
            let shared = shared.clone();
            std::thread::spawn(move || {
                let Ok(shutter) = stream.try_clone() else {
                    return;
                };
                let Ok(channel) = tcp_channel(stream) else {
                    return;
                };
                let shut: Box<dyn Fn() + Send> = Box::new(move || {
                    let _ = shutter.shutdown(Shutdown::Read);
                });
                session(&shared, channel, shut);
            });
        }
    });
    Ok(Server {
        stop,
        active,
        accept: Some(accept),
        wake: Box::new(move || {
            let _ = TcpStream::connect_timeout(&local, Duration::from_secs(1));
        }),
        address: local.to_string(),
        path: None,
    })
}
