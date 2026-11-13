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
//! - A server keeps one [`Owner`] for each session and runs each session in its own thread, so a
//!   long step of one session does not delay the others (rules 9.2.7 and 9.2.8). It forgets a
//!   session after a time without requests, and answers a request with `seq` greater than 0 of a
//!   session that it does not hold, because it forgot the session or restarted, with `ended` and
//!   the code `session_expired`, possibly executed. It refuses an `open` above
//!   [`ServeOptions::max_sessions`] sessions with the code `refused`, and stops as rule 9.2.9
//!   says ([`Server::stop`]).
//! - On networks that are not trusted, the Zenoh sessions MUST use TLS with client certificates
//!   and Zenoh access control on both sides (rule 9.2.6). [`secure_config`] writes the TLS part
//!   of such a configuration; the README shows the access control.
//! - A server checks the digest of each frame, or its authentication code with the key of
//!   [`ServeOptions::key`] (section 13.2), before it reads the message (section 3, rule 5). A
//!   frame of a session that the server does not hold has the handshake bound.
#![forbid(unsafe_code)]

use ncp::frame::{self, Decoded, Key, Verify, HANDSHAKE_BOUND};
use ncp::messages::{check_request, foreign};
use ncp::transcript::{RECEIVED, SENT};
use ncp::{Channel, ChannelError, Handler, Owner, Tap, PROTOCOL};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::fmt;
use std::io;
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Arc, Condvar, Mutex, MutexGuard};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};
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

    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        match self.replies.recv_timeout(self.timeout) {
            Ok(frame) => {
                if let Some(tap) = &self.tap {
                    tap.record(RECEIVED, &frame).map_err(ChannelError::Closed)?;
                }
                Ok(frame)
            }
            Err(RecvTimeoutError::Timeout) => Err(ChannelError::Timeout),
            Err(RecvTimeoutError::Disconnected) => Err(ChannelError::Closed(io::Error::new(
                io::ErrorKind::BrokenPipe,
                "the reply channel closed",
            ))),
        }
    }
}

/// Options of a [`Server`].
#[derive(Debug, Clone)]
pub struct ServeOptions {
    /// A session without a request for this long, counted from its last response, is forgotten
    /// (rule 9.2.7). A session with a request in progress is never forgotten.
    pub expire_after: Duration,
    /// Above this many sessions, an `open` is answered with `rejected` and the code `refused`
    /// (rule 7.1.4).
    pub max_sessions: usize,
    /// The key that authenticates every frame (section 13.2), if any. The server checks the
    /// authentication code of each request before it reads the message, and authenticates the
    /// responses that it makes itself. Each owner that the factory returns must have the same key,
    /// or none if the server has none; the server drops an `open` for an owner with another key.
    pub key: Option<Key>,
}

impl Default for ServeOptions {
    fn default() -> ServeOptions {
        ServeOptions {
            expire_after: Duration::from_secs(600),
            max_sessions: 4096,
            key: None,
        }
    }
}

/// Reply to a query, if there is a response, and complete it. The client may have gone; the
/// reply then has no reader.
fn reply(key: &str, query: Query, response: Option<Vec<u8>>) {
    if let Some(response) = response {
        let _ = query.reply(key, response).wait();
    }
    drop(query); // dropping the query tells the client that no more replies come
}

fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// One session: its owner, the channel to its thread, and what the expiry needs.
struct Worker<H: Handler> {
    sender: Sender<(Query, Decoded)>,
    owner: Arc<Mutex<Owner<H>>>,
    waiting: usize,
    last: Instant,
    thread: Option<JoinHandle<()>>,
}

struct Table<H: Handler> {
    workers: HashMap<String, Worker<H>>,
    stopping: bool,
    /// The largest bound of a session that the server holds or held: the bound for the first
    /// check of a frame, before the server knows its session.
    largest: usize,
}

type Factory<H> = dyn Fn() -> Owner<H> + Send + Sync;

struct Shared<H: Handler> {
    key: String,
    make_owner: Box<Factory<H>>,
    options: ServeOptions,
    table: Mutex<Table<H>>,
    done: (Mutex<bool>, Condvar),
}

impl<H: Handler + Send + 'static> Shared<H> {
    /// A response that the server makes itself, without an owner of the session, with the
    /// server's key. A request of another protocol version gets `wrong_protocol` (rule 7.3.2).
    fn answer(&self, decoded: &Decoded, outcome: &str, code: &str) -> Option<Vec<u8>> {
        let request = &decoded.message;
        let (outcome, code) = if request["ncp"] != PROTOCOL {
            ("rejected", "wrong_protocol")
        } else {
            (outcome, code)
        };
        let response = json!({"ncp": PROTOCOL, "session": request["session"], "seq": request["seq"],
                              "request": decoded.identity, "outcome": outcome, "code": code, "body": {}});
        frame::encode_with(&response, &[], self.options.key.as_ref(), None).ok()
    }

    /// Route one query to its session's thread, or answer it here (rules 7.3.2, 7.3.3, and
    /// 9.2.7). Runs in a thread of Zenoh, so it never waits for an owner.
    ///
    /// The server checks the digest, or the authentication code with its key, before it reads the
    /// message (section 3, rule 5), with the largest bound of its sessions; a frame of a session
    /// that it does not hold has the handshake bound.
    fn route(self: &Arc<Self>, query: Query) {
        let Some(frame_bytes) = query.payload().map(|p| p.to_bytes().into_owned()) else {
            return reply(&self.key, query, None);
        };
        let size = frame_bytes.len();
        let limit = lock(&self.table).largest;
        let verify = self
            .options
            .key
            .as_ref()
            .map_or(Verify::Digest, Verify::Key);
        let Ok(decoded) = frame::decode_verified(frame_bytes, limit, verify) else {
            return reply(&self.key, query, None); // rule 9.2.3
        };
        let other = foreign(&decoded.message);
        if !other && check_request(&decoded.message).is_err() {
            return reply(&self.key, query, None); // rule 9.2.3
        }
        let session = decoded.message["session"]
            .as_str()
            .unwrap_or_default()
            .to_owned();
        let (op, seq) = (
            decoded.message["op"].clone(),
            decoded.message["seq"].clone(),
        );
        let small = size <= HANDSHAKE_BOUND;
        let mut table = lock(&self.table);
        if !table.workers.contains_key(&session)
            && op == "open"
            && seq == 0
            && !other
            && small
            && !table.stopping
            && table.workers.len() < self.options.max_sessions
        {
            let owner = (self.make_owner)();
            if owner.key() == self.options.key.as_ref() {
                let owner = Arc::new(Mutex::new(owner));
                let (sender, receiver) = mpsc::channel();
                let thread = {
                    let (shared, session, owner) = (self.clone(), session.clone(), owner.clone());
                    std::thread::Builder::new()
                        .name(format!("ncp-zenoh {}", &session[..session.len().min(8)]))
                        .spawn(move || shared.serve(&session, &owner, &receiver))
                };
                if let Ok(thread) = thread {
                    table.workers.insert(
                        session.clone(),
                        Worker {
                            sender,
                            owner,
                            waiting: 0,
                            last: Instant::now(),
                            thread: Some(thread),
                        },
                    );
                }
            }
            // Otherwise the owner's key is not the server's key: the open gets no reply.
        }
        if let Some(worker) = table.workers.get_mut(&session) {
            worker.waiting += 1;
            let _ = worker.sender.send((query, decoded));
            return;
        }
        let (stopping, full) = (
            table.stopping,
            table.workers.len() >= self.options.max_sessions,
        );
        drop(table);
        let response = if !small {
            None // above the handshake bound of a session that the server does not hold
        } else if other || seq.as_u64().is_some_and(|seq| seq > 0) {
            // seq > 0: a session that this server does not hold: it forgot it, it restarted, or
            // it never served it. An earlier copy of the request may have executed (rule 9.2.7).
            self.answer(&decoded, "ended", "session_expired")
        } else if op != "open" {
            self.answer(&decoded, "rejected", "not_open")
        } else if stopping || full {
            self.answer(&decoded, "rejected", "refused")
        } else {
            None
        };
        reply(&self.key, query, response);
    }

    /// The thread of one session: handle its queries in order, one at a time.
    fn serve(&self, session: &str, owner: &Mutex<Owner<H>>, queries: &Receiver<(Query, Decoded)>) {
        while let Ok((query, decoded)) = queries.recv() {
            let (response, bound) = {
                let mut owner = lock(owner);
                // The server checked the frame with the largest bound of its sessions; a frame
                // above this session's bound is a bad frame (rule 9.2.3).
                let response = if decoded.frame.len() <= owner.bound() {
                    owner
                        .handle_decoded(&decoded)
                        .ok()
                        .map(|response| response.to_vec())
                } else {
                    None
                };
                (response, owner.bound())
            };
            reply(&self.key, query, response);
            let mut table = lock(&self.table);
            table.largest = table.largest.max(bound);
            let forget = match table.workers.get_mut(session) {
                Some(worker) => {
                    worker.waiting -= 1;
                    worker.last = Instant::now();
                    worker.waiting == 0 && lock(owner).session().is_none()
                }
                None => false,
            };
            if forget {
                // The open was not accepted: there is no session to keep. Removing the worker
                // drops its sender, so this loop ends.
                table.workers.remove(session);
            }
        }
    }

    /// Forget the sessions without a request for `expire_after`, until the server stops.
    fn expire(&self) {
        let period = (self.options.expire_after / 4).min(Duration::from_secs(1));
        loop {
            {
                let (done, signal) = &self.done;
                let done = lock(done);
                let (done, _) = signal
                    .wait_timeout(done, period)
                    .unwrap_or_else(|poisoned| poisoned.into_inner());
                if *done {
                    return;
                }
            }
            let now = Instant::now();
            let expired: Vec<Worker<H>> = {
                let mut table = lock(&self.table);
                let stale: Vec<String> = table
                    .workers
                    .iter()
                    .filter(|(_, w)| {
                        w.waiting == 0 && now.duration_since(w.last) >= self.options.expire_after
                    })
                    .map(|(session, _)| session.clone())
                    .collect();
                stale
                    .iter()
                    .filter_map(|session| table.workers.remove(session))
                    .collect()
            };
            for worker in expired {
                finish(worker, "expired");
            }
        }
    }
}

/// End a session's thread and tell the application, once, that the session ended.
fn finish<H: Handler>(worker: Worker<H>, reason: &str) {
    let Worker {
        sender,
        owner,
        thread,
        ..
    } = worker;
    drop(sender);
    if let Some(thread) = thread {
        let _ = thread.join();
    }
    lock(&owner).finish(reason);
}

/// An owner service on `ncp/x/<service>`: one [`Owner`] for each session, each in its own thread.
///
/// [`Server::declare`] declares the service, so clients can reach it once it returns. A long
/// step of one session does not delay the others (rule 9.2.8). [`Server::stop`] stops the
/// service as rule 9.2.9 says; dropping the server stops it without a grace time.
pub struct Server<H: Handler + Send + 'static> {
    shared: Arc<Shared<H>>,
    queryable: Option<Queryable<()>>,
    janitor: Option<JoinHandle<()>>,
}

impl<H: Handler + Send + 'static> fmt::Debug for Server<H> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Server")
            .field("key", &self.shared.key)
            .field("sessions", &self.sessions())
            .finish_non_exhaustive()
    }
}

impl<H: Handler + Send + 'static> Server<H> {
    /// Declare the service `ncp/x/<service>` on `session`. `make_owner` returns a new owner for
    /// each new session.
    pub fn declare<F>(
        session: &Session,
        service: &str,
        make_owner: F,
        options: ServeOptions,
    ) -> Result<Server<H>, BindingError>
    where
        F: Fn() -> Owner<H> + Send + Sync + 'static,
    {
        if options.max_sessions == 0 || options.expire_after.is_zero() {
            return Err(BindingError::Zenoh(
                "max_sessions and expire_after must be positive".into(),
            ));
        }
        let key = exchange_key(service)?;
        let shared = Arc::new(Shared {
            key: key.clone(),
            make_owner: Box::new(make_owner),
            options,
            table: Mutex::new(Table {
                workers: HashMap::new(),
                stopping: false,
                largest: HANDSHAKE_BOUND,
            }),
            done: (Mutex::new(false), Condvar::new()),
        });
        let router = shared.clone();
        let queryable = session
            .declare_queryable(key)
            .complete(true)
            .callback(move |query| router.route(query))
            .wait()
            .map_err(zenoh_error)?;
        let janitor = {
            let shared = shared.clone();
            std::thread::Builder::new()
                .name("ncp-zenoh expiry".into())
                .spawn(move || shared.expire())
                .map_err(zenoh_error)?
        };
        Ok(Server {
            shared,
            queryable: Some(queryable),
            janitor: Some(janitor),
        })
    }

    /// The number of sessions whose state the server keeps.
    pub fn sessions(&self) -> usize {
        lock(&self.shared.table).workers.len()
    }

    /// Stop as rule 9.2.9 says: every owner stops. Rules 7.3.1 to 7.3.9 still apply, so a copy of
    /// a kept request gets the kept response and the other checks reject as usual; an `open`
    /// gets `rejected` with `refused`; a request that the owner would otherwise admit gets
    /// `ended` with `shutdown`, and is never admitted. After `grace`, the server undeclares the
    /// queryable and ends the threads of the sessions, once they have answered their queries.
    pub fn stop(mut self, grace: Duration) {
        self.shutdown(grace);
    }

    fn shutdown(&mut self, grace: Duration) {
        let owners: Vec<Arc<Mutex<Owner<H>>>> = {
            let mut table = lock(&self.shared.table);
            if table.stopping {
                return;
            }
            table.stopping = true;
            table.workers.values().map(|w| w.owner.clone()).collect()
        };
        for owner in owners {
            lock(&owner).stop(); // waits for a step in progress, so the stop is never lost
        }
        std::thread::sleep(grace);
        if let Some(queryable) = self.queryable.take() {
            let _ = queryable.undeclare().wait();
        }
        {
            let (done, signal) = &self.shared.done;
            *lock(done) = true;
            signal.notify_all();
        }
        if let Some(janitor) = self.janitor.take() {
            let _ = janitor.join();
        }
        let workers: Vec<Worker<H>> = lock(&self.shared.table)
            .workers
            .drain()
            .map(|(_, worker)| worker)
            .collect();
        for worker in workers {
            finish(worker, "shutdown");
        }
    }
}

impl<H: Handler + Send + 'static> Drop for Server<H> {
    fn drop(&mut self) {
        self.shutdown(Duration::ZERO);
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
