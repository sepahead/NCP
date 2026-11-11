//! The Zenoh binding of NCP 2 (specification, section 9.2), for Rust.
//!
//! Exchanges travel as Zenoh queries and replies, streams as Zenoh publications. This crate is
//! optional: the NCP 2 core crate (`sepahead-ncp-core`, library `ncp`) does not depend on Zenoh.
//!
//! - An owner serves on the key `ncp/x/<service>` ([`Server`]). A client sends each request
//!   frame as the payload of a query to that key ([`ZenohChannel`]), and the owner replies with the
//!   response frame (rule 9.2.1).
//! - A publisher puts stream frames on `ncp/s/<stream-key>` ([`StreamSender`]), and subscribers
//!   subscribe to that key ([`subscribe`]) (rule 9.2.2).
//! - A receiver drops a bad frame (rule 9.2.3).
//! - The client accepts only the reply that matches its request; when no reply arrives in time,
//!   it sends the same request frame again (rule 9.2.4). [`ncp::Client`] does this for a channel
//!   whose `lossy` is true, and the owner answers a repeated request with its kept response
//!   (rule 7.3.5), so the request still runs at most once.
//! - Each owner uses its own service key (rule 9.2.5).
//! - A server forgets a session after a time without requests and answers its later requests
//!   with `ended` and the code `session_expired`, possibly executed (rule 9.2.7).
//! - On networks that are not trusted, the Zenoh sessions MUST use TLS with client certificates
//!   and Zenoh access control (rule 9.2.6). [`secure_config`] writes the TLS part of such a
//!   configuration; the README shows the access control.
#![forbid(unsafe_code)]

use ncp::exchange::check_request;
use ncp::frame::{self, HANDSHAKE_BOUND, HEADER_BYTES, MAGIC, MAX_BOUND};
use ncp::transcript::{RECEIVED, SENT};
use ncp::{Channel, Error, Handler, Owner, Tap, PROTOCOL};
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet, VecDeque};
use std::fmt;
use std::io;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::time::{Duration, Instant};
use zenoh::handlers::FifoChannelHandler;
use zenoh::pubsub::{Publisher, Subscriber};
use zenoh::query::{Query, Queryable};
use zenoh::{Config, Session, Wait};

/// The prefix of the key of an owner's service.
pub const EXCHANGE_PREFIX: &str = "ncp/x/";
/// The prefix of the key of a stream.
pub const STREAM_PREFIX: &str = "ncp/s/";
/// How long a client waits for a reply before it sends the request again.
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(1);
/// How long Zenoh keeps a query open for a late reply. [`ncp::Client`] drops a reply that does
/// not match its current request.
const QUERY_TIMEOUT: Duration = Duration::from_secs(10);
/// The frame overhead: header and digest.
const OVERHEAD: usize = HEADER_BYTES + frame::DIGEST_BYTES;

/// A failure of the binding: a name that is not a plain Zenoh key, or an error of Zenoh.
#[derive(Debug)]
pub enum BindingError {
    /// The service or stream name is not a Zenoh key without wildcards.
    Name(String),
    /// Zenoh reported an error.
    Zenoh(String),
}

impl fmt::Display for BindingError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BindingError::Name(name) => write!(f, "not a service or stream name: {name:?}"),
            BindingError::Zenoh(error) => write!(f, "zenoh: {error}"),
        }
    }
}

impl std::error::Error for BindingError {}

fn zenoh_error(error: impl fmt::Display) -> BindingError {
    BindingError::Zenoh(error.to_string())
}

/// Chunks of letters, digits, `_`, `.`, and `-`, separated by `/`: a Zenoh key without wildcards.
fn valid_name(name: &str) -> bool {
    !name.is_empty()
        && name.len() <= 256
        && name.split('/').all(|chunk| {
            !chunk.is_empty()
                && chunk
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'-'))
        })
}

fn key(prefix: &str, name: &str) -> Result<String, BindingError> {
    if valid_name(name) {
        Ok(format!("{prefix}{name}"))
    } else {
        Err(BindingError::Name(name.to_owned()))
    }
}

/// The Zenoh key of an owner's service: `ncp/x/<service>`.
pub fn exchange_key(service: &str) -> Result<String, BindingError> {
    key(EXCHANGE_PREFIX, service)
}

/// The Zenoh key of a stream: `ncp/s/<name>`.
pub fn stream_key(name: &str) -> Result<String, BindingError> {
    key(STREAM_PREFIX, name)
}

/// A client channel to one service, for [`ncp::Client`].
///
/// Zenoh can lose a query or a reply, so the channel is lossy: after its time limit, the client
/// sends the same request frame again. Every sent frame and every received reply go to the tap,
/// if one is set.
pub struct ZenohChannel {
    session: Session,
    key: String,
    timeout: Duration,
    sender: Sender<Vec<u8>>,
    replies: Receiver<Vec<u8>>,
    tap: Option<Tap>,
}

impl fmt::Debug for ZenohChannel {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("ZenohChannel")
            .field("key", &self.key)
            .field("timeout", &self.timeout)
            .finish_non_exhaustive()
    }
}

impl ZenohChannel {
    /// A channel to the service `ncp/x/<service>` on `session`.
    pub fn new(session: &Session, service: &str) -> Result<ZenohChannel, BindingError> {
        let (sender, replies) = mpsc::channel();
        Ok(ZenohChannel {
            session: session.clone(),
            key: exchange_key(service)?,
            timeout: DEFAULT_TIMEOUT,
            sender,
            replies,
            tap: None,
        })
    }

    /// Wait at most `timeout` for a reply before the client sends the request again.
    pub fn with_timeout(mut self, timeout: Duration) -> ZenohChannel {
        self.timeout = timeout;
        self
    }

    /// Record every sent frame and every received reply in a transcript.
    pub fn with_tap(mut self, tap: Tap) -> ZenohChannel {
        self.tap = Some(tap);
        self
    }
}

impl Channel for ZenohChannel {
    fn lossy(&self) -> bool {
        true
    }

    fn send(&mut self, frame: &[u8]) -> io::Result<()> {
        if let Some(tap) = &self.tap {
            tap.record(SENT, frame)?;
        }
        let sender = self.sender.clone();
        self.session
            .get(&self.key)
            .payload(frame.to_vec())
            .timeout(QUERY_TIMEOUT)
            .callback(move |reply| {
                if let Ok(sample) = reply.result() {
                    // The client may have stopped listening; then the reply has no reader.
                    let _ = sender.send(sample.payload().to_bytes().into_owned());
                }
            })
            .wait()
            .map_err(|error| io::Error::other(error.to_string()))
    }

    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, Error> {
        match self.replies.recv_timeout(self.timeout) {
            Ok(frame) => {
                if let Some(tap) = &self.tap {
                    tap.record(RECEIVED, &frame)?;
                }
                Ok(frame)
            }
            Err(RecvTimeoutError::Timeout) => Err(Error::Io(io::Error::new(
                io::ErrorKind::TimedOut,
                "no reply from the owner",
            ))),
            Err(RecvTimeoutError::Disconnected) => Err(Error::Io(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "the reply channel closed",
            ))),
        }
    }
}

/// Options of a [`Server`].
#[derive(Debug, Clone, Copy)]
pub struct ServeOptions {
    /// A session without a request for this long is forgotten (rule 9.2.7).
    pub expire_after: Duration,
    /// The identifiers of up to this many forgotten sessions are kept, so that their later
    /// requests get `session_expired`.
    pub remember: usize,
}

impl Default for ServeOptions {
    fn default() -> ServeOptions {
        ServeOptions {
            expire_after: Duration::from_secs(600),
            remember: 100_000,
        }
    }
}

/// The session, op, and seq of a request frame, read from its JSON region only. None for a
/// frame that cannot be a request. The owner checks the whole frame.
fn peek(frame: &[u8]) -> Option<(String, Value, Value)> {
    if frame.len() < OVERHEAD || frame.len() > MAX_BOUND || frame[..4] != MAGIC {
        return None;
    }
    let length = |at: usize| u32::from_be_bytes(frame[at..at + 4].try_into().unwrap_or([0; 4]));
    let (json_length, attachments) = (length(4) as usize, length(8) as usize);
    if OVERHEAD
        .checked_add(json_length)?
        .checked_add(attachments)?
        != frame.len()
    {
        return None;
    }
    let message: Value =
        serde_json::from_slice(&frame[HEADER_BYTES..HEADER_BYTES + json_length]).ok()?;
    let session = message.get("session")?.as_str()?.to_owned();
    Some((session, message["op"].clone(), message["seq"].clone()))
}

/// A response that the server makes itself: `rejected` with `wrong_protocol` or `not_open` for
/// an unknown session, or `ended` with `session_expired` for a forgotten one. None for a bad frame.
fn answer(frame: Vec<u8>, expired: bool) -> Option<Vec<u8>> {
    let decoded = frame::decode(frame, MAX_BOUND).ok()?;
    check_request(&decoded.message).ok()?;
    let request = &decoded.message;
    let (outcome, code) = if request["ncp"] != PROTOCOL {
        ("rejected", "wrong_protocol")
    } else if expired {
        ("ended", "session_expired")
    } else {
        ("rejected", "not_open")
    };
    let response = json!({"ncp": PROTOCOL, "session": request["session"], "seq": request["seq"],
                          "request": decoded.identity, "outcome": outcome, "code": code, "body": {}});
    frame::encode(&response, &[]).ok()
}

/// Whether a response frame has the outcome `ok`.
fn accepted(response: &[u8]) -> bool {
    frame::decode(response.to_vec(), MAX_BOUND).is_ok_and(|d| d.message["outcome"] == "ok")
}

/// The owners of one service, one for each session, and the sessions that it forgot.
struct Sessions<H: Handler> {
    owners: HashMap<String, (Owner<H>, Instant)>,
    forgotten: HashSet<String>,
    order: VecDeque<String>,
    options: ServeOptions,
}

impl<H: Handler> Sessions<H> {
    /// Idle time counts from each response, so a long step does not expire its own session.
    fn respond(
        &mut self,
        frame: Vec<u8>,
        make_owner: &mut dyn FnMut() -> Owner<H>,
    ) -> Option<Vec<u8>> {
        let (session, op, seq) = peek(&frame)?;
        if let Some((owner, last)) = self.owners.get_mut(&session) {
            let response = owner.handle(frame).ok()?;
            *last = Instant::now();
            return Some(response.to_vec());
        }
        if self.forgotten.contains(&session) {
            return answer(frame, true);
        }
        if op == "open" && seq == 0 {
            // Check the whole frame before the application makes an owner for it.
            let decoded = frame::decode(frame.clone(), HANDSHAKE_BOUND).ok()?;
            check_request(&decoded.message).ok()?;
            let mut owner = make_owner();
            let response = owner.handle(frame).ok()?;
            if accepted(&response) {
                self.owners.insert(session, (owner, Instant::now()));
            }
            return Some(response.to_vec());
        }
        answer(frame, false)
    }

    fn expire(&mut self, now: Instant) {
        let expire_after = self.options.expire_after;
        let stale: Vec<String> = self
            .owners
            .iter()
            .filter(|(_, (_, last))| now.duration_since(*last) >= expire_after)
            .map(|(session, _)| session.clone())
            .collect();
        for session in stale {
            self.owners.remove(&session);
            if self.forgotten.insert(session.clone()) {
                self.order.push_back(session);
            }
        }
        while self.order.len() > self.options.remember {
            if let Some(oldest) = self.order.pop_front() {
                self.forgotten.remove(&oldest);
            }
        }
    }
}

/// An owner service on `ncp/x/<service>`: one [`Owner`] for each session.
///
/// [`Server::declare`] declares the service, so clients can reach it once it returns.
/// [`Server::run`] then handles the queries in their order of arrival, one at a time, on the
/// caller's thread: a long step of one session delays the others.
pub struct Server<H: Handler, F: FnMut() -> Owner<H>> {
    key: String,
    queryable: Queryable<FifoChannelHandler<Query>>,
    sessions: Sessions<H>,
    make_owner: F,
}

impl<H: Handler, F: FnMut() -> Owner<H>> fmt::Debug for Server<H, F> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Server")
            .field("key", &self.key)
            .field("sessions", &self.sessions.owners.len())
            .finish_non_exhaustive()
    }
}

impl<H: Handler, F: FnMut() -> Owner<H>> Server<H, F> {
    /// Declare the service `ncp/x/<service>` on `session`. `make_owner` returns a new owner for
    /// each new session.
    pub fn declare(
        session: &Session,
        service: &str,
        make_owner: F,
        options: ServeOptions,
    ) -> Result<Server<H, F>, BindingError> {
        let key = exchange_key(service)?;
        let queryable = session
            .declare_queryable(key.clone())
            .complete(true)
            .wait()
            .map_err(zenoh_error)?;
        Ok(Server {
            key,
            queryable,
            sessions: Sessions {
                owners: HashMap::new(),
                forgotten: HashSet::new(),
                order: VecDeque::new(),
                options,
            },
            make_owner,
        })
    }

    /// Handle at most one query, waiting at most `timeout` for it. Returns whether one came.
    pub fn serve_one(&mut self, timeout: Duration) -> Result<bool, BindingError> {
        self.sessions.expire(Instant::now());
        let Some(query) = self.queryable.recv_timeout(timeout).map_err(zenoh_error)? else {
            return Ok(false);
        };
        let response = query.payload().and_then(|payload| {
            self.sessions
                .respond(payload.to_bytes().into_owned(), &mut self.make_owner)
        });
        if let Some(response) = response {
            query
                .reply(&self.key, response)
                .wait()
                .map_err(zenoh_error)?;
        }
        Ok(true) // dropping the query tells the client that no more replies come
    }

    /// Handle queries until `stop` is set.
    pub fn run(&mut self, stop: &AtomicBool) -> Result<(), BindingError> {
        while !stop.load(Ordering::Acquire) {
            self.serve_one(Duration::from_millis(50))?;
        }
        Ok(())
    }

    /// The number of sessions whose state the server keeps.
    pub fn sessions(&self) -> usize {
        self.sessions.owners.len()
    }
}

/// A sender of stream frames on `ncp/s/<name>`, for the frames of an [`ncp::Publisher`].
#[derive(Debug)]
pub struct StreamSender {
    publisher: Publisher<'static>,
}

impl StreamSender {
    /// Declare a publisher on `ncp/s/<name>`.
    pub fn declare(session: &Session, name: &str) -> Result<StreamSender, BindingError> {
        let publisher = session
            .declare_publisher(stream_key(name)?)
            .wait()
            .map_err(zenoh_error)?;
        Ok(StreamSender { publisher })
    }

    /// Put one stream frame.
    pub fn send(&self, frame: &[u8]) -> Result<(), BindingError> {
        self.publisher
            .put(frame.to_vec())
            .wait()
            .map_err(zenoh_error)
    }
}

/// Call `on_frame` with every frame put on `ncp/s/<name>`. Check the frames with an
/// [`ncp::Subscriber`]: it drops bad frames and reports lost, repeated, and changed messages.
pub fn subscribe(
    session: &Session,
    name: &str,
    on_frame: impl Fn(Vec<u8>) + Send + Sync + 'static,
) -> Result<Subscriber<()>, BindingError> {
    session
        .declare_subscriber(stream_key(name)?)
        .callback(move |sample| on_frame(sample.payload().to_bytes().into_owned()))
        .wait()
        .map_err(zenoh_error)
}

/// The TLS files of one side of a mutual-TLS link: the root certificate that signs both sides,
/// and this side's certificate and private key.
#[derive(Debug, Clone)]
pub struct TlsFiles {
    /// The root certificate, PEM.
    pub root_ca_certificate: String,
    /// This side's certificate, PEM.
    pub certificate: String,
    /// This side's private key, PEM.
    pub private_key: String,
}

/// A Zenoh configuration for networks that are not trusted (rule 9.2.6): peer mode, TLS links
/// only, with a certificate on both sides (mutual TLS), and no multicast scouting. Endpoints have
/// the form `tls/HOST:PORT`. Add access control before you open the session.
pub fn secure_config(
    tls: &TlsFiles,
    listen: &[&str],
    connect: &[&str],
) -> Result<Config, BindingError> {
    let endpoints = listen.iter().chain(connect);
    if listen.is_empty() && connect.is_empty() || endpoints.clone().any(|e| !e.starts_with("tls/"))
    {
        return Err(BindingError::Zenoh(
            "secure_config needs tls/ endpoints only".into(),
        ));
    }
    let mut config = Config::default();
    let mut set = |key: &str, value: Value| {
        config
            .insert_json5(key, &value.to_string())
            .map_err(zenoh_error)
    };
    set("mode", json!("peer"))?;
    set("scouting/multicast/enabled", json!(false))?;
    set("listen/endpoints", json!(listen))?;
    set("connect/endpoints", json!(connect))?;
    let link = "transport/link/tls";
    set(
        &format!("{link}/root_ca_certificate"),
        json!(tls.root_ca_certificate),
    )?;
    for side in ["listen", "connect"] {
        set(
            &format!("{link}/{side}_certificate"),
            json!(tls.certificate),
        )?;
        set(
            &format!("{link}/{side}_private_key"),
            json!(tls.private_key),
        )?;
    }
    set(&format!("{link}/enable_mtls"), json!(true))?;
    set(&format!("{link}/verify_name_on_connect"), json!(true))?;
    Ok(config)
}
