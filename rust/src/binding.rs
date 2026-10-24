//! The byte-stream binding: pipes, Unix domain sockets, and TCP (section 9.1).

use crate::exchange::{bad_frame_response, Channel, Error, Handler, Owner};
use crate::frame::{self, FrameError, HEADER_BYTES};
use crate::transcript::{Tap, RECEIVED, SENT};
use std::io::{self, BufReader, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream, ToSocketAddrs};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::Arc;
use std::time::Duration;

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

/// Frames over one reliable, ordered byte stream.
pub struct StreamChannel<R: Read, W: Write> {
    reader: BufReader<R>,
    writer: Option<W>,
    tap: Option<Arc<Tap>>,
    closer: Option<Box<dyn FnMut() + Send>>,
}

impl<R: Read, W: Write> std::fmt::Debug for StreamChannel<R, W> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("StreamChannel")
            .field("open", &self.writer.is_some())
            .field("tap", &self.tap.is_some())
            .finish_non_exhaustive()
    }
}

impl<R: Read, W: Write> StreamChannel<R, W> {
    /// A channel over a reader and a writer.
    pub fn new(reader: R, writer: W) -> StreamChannel<R, W> {
        StreamChannel {
            reader: BufReader::with_capacity(1 << 16, reader),
            writer: Some(writer),
            tap: None,
            closer: None,
        }
    }

    /// Record every frame in a transcript (section 10).
    pub fn with_tap(mut self, tap: Arc<Tap>) -> StreamChannel<R, W> {
        self.tap = Some(tap);
        self
    }

    fn set_closer(&mut self, closer: Box<dyn FnMut() + Send>) {
        self.closer = Some(closer);
    }

    /// Send one frame.
    pub fn send_frame(&mut self, frame: &[u8]) -> io::Result<()> {
        let writer = self
            .writer
            .as_mut()
            .ok_or_else(|| io::Error::new(io::ErrorKind::BrokenPipe, "channel closed"))?;
        writer.write_all(frame)?;
        writer.flush()?;
        if let Some(tap) = &self.tap {
            tap.record(SENT, frame)?;
        }
        Ok(())
    }

    fn read_header(&mut self, header: &mut [u8; HEADER_BYTES]) -> Result<(), Error> {
        match self.reader.read_exact(header) {
            Ok(()) => Ok(()),
            Err(error) if error.kind() == io::ErrorKind::UnexpectedEof => Err(Error::Io(
                io::Error::new(io::ErrorKind::UnexpectedEof, "the peer closed the stream"),
            )),
            Err(error) => Err(Error::Io(error)),
        }
    }

    /// Receive one complete frame, checking its header against `bound`.
    pub fn receive_frame(&mut self, bound: usize) -> Result<Vec<u8>, Error> {
        let mut header = [0u8; HEADER_BYTES];
        self.read_header(&mut header)?;
        let rest = frame::remaining_length(&header, bound)?;
        let mut frame = Vec::with_capacity(HEADER_BYTES + rest);
        frame.extend_from_slice(&header);
        frame.resize(HEADER_BYTES + rest, 0);
        self.reader.read_exact(&mut frame[HEADER_BYTES..])?;
        if let Some(tap) = &self.tap {
            tap.record(RECEIVED, &frame)?;
        }
        Ok(frame)
    }
}

impl<R: Read, W: Write> Channel for StreamChannel<R, W> {
    fn lossy(&self) -> bool {
        false
    }
    fn send(&mut self, frame: &[u8]) -> io::Result<()> {
        self.send_frame(frame)
    }
    fn receive(&mut self, bound: usize) -> Result<Vec<u8>, Error> {
        self.receive_frame(bound)
    }
    fn close(&mut self) {
        // Dropping the writer closes a pipe, so a child owner sees end of file and exits.
        if let Some(mut writer) = self.writer.take() {
            let _ = writer.flush();
        }
        if let Some(mut closer) = self.closer.take() {
            closer();
        }
    }
}

/// Serve one session on a byte stream until the peer closes it. A bad frame gets the bad-frame
/// response, and the connection closes (section 9.1).
pub fn serve<H: Handler, R: Read, W: Write>(
    owner: &mut Owner<H>,
    channel: &mut StreamChannel<R, W>,
) -> Result<(), Error> {
    loop {
        let frame_bytes = match channel.receive_frame(owner.bound()) {
            Ok(bytes) => bytes,
            Err(Error::Frame(_)) => {
                let _ = channel.send_frame(&bad_frame_response());
                return Ok(());
            }
            Err(Error::Io(error))
                if matches!(
                    error.kind(),
                    io::ErrorKind::UnexpectedEof
                        | io::ErrorKind::BrokenPipe
                        | io::ErrorKind::ConnectionReset
                ) =>
            {
                return Ok(())
            }
            Err(other) => return Err(other),
        };
        match owner.handle(frame_bytes) {
            Ok(response) => {
                if let Err(error) = channel.send_frame(&response) {
                    return if error.kind() == io::ErrorKind::BrokenPipe {
                        Ok(())
                    } else {
                        Err(Error::Io(error))
                    };
                }
            }
            Err(FrameError(_)) => {
                let _ = channel.send_frame(&bad_frame_response());
                return Ok(());
            }
        }
    }
}

/// Serve one session on standard input and output (section 9.1, rule 4). The owner must not
/// write anything else to standard output.
pub fn serve_stdio<H: Handler>(owner: &mut Owner<H>) -> Result<(), Error> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut channel = StreamChannel::new(stdin.lock(), stdout.lock());
    serve(owner, &mut channel)
}

/// A channel to a child owner process over its standard input and output.
pub type ChildChannel = StreamChannel<ChildStdout, ChildStdin>;

/// Start an owner process and return a channel to it.
pub fn spawn(mut command: Command) -> io::Result<(ChildChannel, Child)> {
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
    Ok((StreamChannel::new(stdout, stdin), child))
}

fn check_loopback(addresses: &[SocketAddr], allow_remote: bool) -> io::Result<()> {
    if allow_remote || addresses.iter().all(|a| a.ip().is_loopback()) {
        Ok(())
    } else {
        Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "not a loopback address; allow remote addresses only on a trusted cluster network, or use a secure tunnel or the Zenoh binding",
        ))
    }
}

/// A channel over a TCP connection.
pub type TcpChannel = StreamChannel<TcpStream, TcpStream>;

/// Connect to a TCP owner. Remote addresses need `allow_remote` (section 9.1, rule 5).
pub fn connect_tcp(address: impl ToSocketAddrs, allow_remote: bool) -> io::Result<TcpChannel> {
    let addresses: Vec<SocketAddr> = address.to_socket_addrs()?.collect();
    check_loopback(&addresses, allow_remote)?;
    let stream = TcpStream::connect(&addresses[..])?;
    tcp_channel(stream)
}

/// Wrap an accepted or connected TCP stream: sets TCP_NODELAY, which specification 9.1 requires
/// (an error if it fails, for example on macOS after the peer has closed), and tries to set
/// [`SOCKET_BUFFER`].
pub fn tcp_channel(stream: TcpStream) -> io::Result<TcpChannel> {
    stream.set_nodelay(true)?;
    enlarge_buffers(socket2::SockRef::from(&stream));
    let writer = stream.try_clone()?;
    let closer = stream.try_clone()?;
    let mut channel = StreamChannel::new(stream, writer);
    channel.set_closer(Box::new(move || {
        let _ = closer.shutdown(std::net::Shutdown::Both);
    }));
    Ok(channel)
}

/// Bind a TCP listener. Remote addresses need `allow_remote`.
pub fn listen_tcp(address: impl ToSocketAddrs, allow_remote: bool) -> io::Result<TcpListener> {
    let addresses: Vec<SocketAddr> = address.to_socket_addrs()?.collect();
    check_loopback(&addresses, allow_remote)?;
    TcpListener::bind(&addresses[..])
}

/// A channel over a Unix domain socket connection.
#[cfg(unix)]
pub type UnixChannel =
    StreamChannel<std::os::unix::net::UnixStream, std::os::unix::net::UnixStream>;

/// Connect to an owner that listens on a Unix domain socket (section 9.1, rule 5).
#[cfg(unix)]
pub fn connect_unix(path: impl AsRef<std::path::Path>) -> io::Result<UnixChannel> {
    unix_channel(std::os::unix::net::UnixStream::connect(path)?)
}

/// Wrap an accepted or connected Unix domain socket stream: sets [`SOCKET_BUFFER`].
#[cfg(unix)]
pub fn unix_channel(stream: std::os::unix::net::UnixStream) -> io::Result<UnixChannel> {
    enlarge_buffers(socket2::SockRef::from(&stream));
    let writer = stream.try_clone()?;
    let closer = stream.try_clone()?;
    let mut channel = StreamChannel::new(stream, writer);
    channel.set_closer(Box::new(move || {
        let _ = closer.shutdown(std::net::Shutdown::Both);
    }));
    Ok(channel)
}

/// Set a time limit for each receive on a TCP channel; a missed limit reads as a timeout.
pub fn set_tcp_timeout(channel: &TcpChannel, timeout: Option<Duration>) -> io::Result<()> {
    channel.reader.get_ref().set_read_timeout(timeout)
}
