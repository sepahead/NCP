//! The client (specification section 7.6).
//!
//! The client rules live in one state machine of pure functions over a [`ClientState`]:
//! [`request`] makes the next request frame, [`receive`] applies a frame from the owner, and
//! [`time_out`], [`closed`], and [`bad_header`] apply local events. Each returns the new state
//! and, when the call is over, its verdict. [`Client`] drives the machine over a [`Channel`];
//! tests, the model check, and other drivers use the same functions.

use crate::contract::Contract;
use crate::events::{default_observer, Event, Observer};
use crate::frame::{
    self, Array, Decoded, FrameError, Key, Verify, DEFAULT_BOUND, HANDSHAKE_BOUND, MAX_BOUND,
};
use crate::messages::{
    check_response, executed, is_name, is_nonce, is_session, Executed, PROTOCOL,
};
use serde_json::{json, Map, Value};
use std::fmt;
use std::io;
use std::sync::Arc;

/// How a call ended without a result.
#[derive(Debug)]
pub enum Error {
    /// The owner admitted the request and did not execute it; it never will (outcome
    /// `declined`). The session goes on.
    Declined {
        /// The owner's code.
        code: String,
        /// The owner's detail, if any.
        detail: String,
        /// The response body.
        body: Value,
    },
    /// The owner did not admit the `open` request: no session is open (outcome `rejected`).
    ///
    /// A client gets it only in reply to `open`. A rejection of any other request ends the
    /// session with [`Error::Ended`] and the request possibly executed (rule 7.6.4): the owner
    /// lost the session, and a delayed copy of `open` opened it again, so an earlier copy of the
    /// request may have executed.
    Rejected {
        /// The owner's code.
        code: String,
        /// The response body.
        body: Value,
    },
    /// The session ended. `executed` says whether the last request executed (section 7.7,
    /// property 7). `code` is the owner's code, or a local code: `local.timeout`,
    /// `local.closed`, `local.protocol`, or `local.bad_frame`.
    Ended {
        /// The code.
        code: String,
        /// Whether the last request executed.
        executed: Executed,
        /// A detail, if any.
        detail: String,
        /// The response body, or an empty object for a local event.
        body: Value,
    },
    /// A call that the client refuses before it sends anything: the request was not sent.
    Usage(String),
}

impl Error {
    /// The code, if the call reached the point of having one.
    pub fn code(&self) -> Option<&str> {
        match self {
            Error::Declined { code, .. }
            | Error::Rejected { code, .. }
            | Error::Ended { code, .. } => Some(code),
            Error::Usage(_) => None,
        }
    }

    /// Whether the request executed: No for a declined or rejected request and for a request
    /// that was never sent; the ending's verdict for an ended session.
    pub fn executed(&self) -> Executed {
        match self {
            Error::Ended { executed, .. } => *executed,
            _ => Executed::No,
        }
    }

    fn ended(code: &str, executed: Executed, detail: impl Into<String>) -> Error {
        Error::Ended {
            code: code.to_owned(),
            executed,
            detail: detail.into(),
            body: json!({}),
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Declined { code, detail, .. } => write!(f, "declined: {code}: {detail}"),
            Error::Rejected { code, .. } => write!(f, "rejected: {code}"),
            Error::Ended {
                code,
                executed,
                detail,
                ..
            } => {
                write!(f, "session ended: {code} (executed: {executed})")?;
                if !detail.is_empty() {
                    write!(f, ": {detail}")?;
                }
                Ok(())
            }
            Error::Usage(reason) => write!(f, "not sent: {reason}"),
        }
    }
}

impl std::error::Error for Error {}

/// Why a channel returned no frame.
#[derive(Debug)]
pub enum ChannelError {
    /// A bad header: wrong magic, or a length above the bound.
    BadFrame(FrameError),
    /// No complete frame before the time limit.
    Timeout,
    /// The binding closed or failed.
    Closed(io::Error),
}

/// A binding as seen by a client: one frame out, one frame in.
pub trait Channel {
    /// Whether the binding can lose frames (section 9.2). A lossy channel allows copies.
    fn lossy(&self) -> bool;
    /// Whether the binding is a pipe pair or a Unix domain socket: the links on which the digest
    /// comparison may be turned off (section 3, rule 5).
    fn local(&self) -> bool {
        false
    }
    /// Send one frame.
    fn send(&mut self, frame: &[u8]) -> io::Result<()>;
    /// Receive one frame, checking its header against `bound`.
    fn receive(&mut self, bound: usize) -> Result<Vec<u8>, ChannelError>;
    /// Close the channel. One byte-stream connection carries one session.
    fn close(&mut self) {}
}

/// The request that waits for its response: its frame is kept for copies (rule 7.6.1).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Pending {
    /// The sequence number.
    pub seq: u64,
    /// The operation.
    pub op: String,
    /// The frame.
    pub frame: Arc<Vec<u8>>,
    /// The identity of the frame.
    pub identity: String,
    /// How many times the frame was sent.
    pub sends: u32,
}

/// The state of a client of one session.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientState {
    /// The session identifier.
    pub session: String,
    /// The application name of the contract.
    pub application: String,
    /// The contract identity.
    pub contract: String,
    /// The bound that the client asks for.
    pub requested_bound: usize,
    /// The bound in force.
    pub bound: usize,
    /// The sequence number of the last admitted request.
    pub seq: u64,
    /// The identity of the last `ok` or `declined` response.
    pub ack: Option<String>,
    /// The outstanding request, if any.
    pub pending: Option<Pending>,
    /// Whether the session is open.
    pub opened: bool,
    /// Whether the session ended.
    pub ended: bool,
}

/// The state of a new client of `contract`.
///
/// # Panics
///
/// If `session` is not a version 4 UUID in lowercase form, or `bound` is outside 65,536 to
/// 67,108,864.
pub fn new_state(contract: &Contract, session: Option<String>, bound: usize) -> ClientState {
    let session = session.unwrap_or_else(crate::random_session);
    assert!(
        is_session(&session),
        "session must be a lowercase version 4 UUID"
    );
    assert!((HANDSHAKE_BOUND..=MAX_BOUND).contains(&bound), "bound");
    ClientState {
        session,
        application: contract.application.clone(),
        contract: contract.identity.clone(),
        requested_bound: bound,
        bound: HANDSHAKE_BOUND,
        seq: 0,
        ack: None,
        pending: None,
        opened: false,
        ended: false,
    }
}

/// What the `open` request asks for, and the key of every request.
#[derive(Debug, Default, Clone, Copy)]
pub struct RequestOptions<'a> {
    /// The key of an authenticated session (section 13.2).
    pub key: Option<&'a Key>,
    /// The run name, for `open`.
    pub run: Option<&'a str>,
    /// The features to ask for, for `open`.
    pub features: Option<&'a Map<String, Value>>,
}

/// The frame of the next request and the state that waits for its response.
///
/// `op` "open" makes the `open` request (section 7.1); `body` is then ignored. Fails with
/// [`Error::Usage`], with nothing sent, for a request that the rules forbid now.
pub fn request(
    state: &ClientState,
    op: &str,
    body: Value,
    arrays: &[Array],
    options: &RequestOptions<'_>,
) -> Result<(ClientState, Arc<Vec<u8>>), Error> {
    if state.ended {
        return Err(Error::Usage("the session has ended".into()));
    }
    if state.pending.is_some() {
        return Err(Error::Usage(
            "a request is outstanding: one request at a time (rule 7.6.1)".into(),
        ));
    }
    let (seq, ack, body) = if op == "open" {
        if state.opened {
            return Err(Error::Usage("the session is open".into()));
        }
        let mut open = json!({"application": state.application, "contract": state.contract,
                              "bound": state.requested_bound});
        if let Some(run) = options.run {
            open["run"] = Value::from(run);
        }
        if let Some(features) = options.features.filter(|f| !f.is_empty()) {
            open["features"] = Value::Object(features.clone());
        }
        (0, Value::Null, open)
    } else {
        if !state.opened {
            return Err(Error::Usage("call before open".into()));
        }
        if !is_name(op) {
            return Err(Error::Usage(format!("{op:?} is not an operation name")));
        }
        (
            state.seq + 1,
            state.ack.clone().map_or(Value::Null, Value::from),
            body,
        )
    };
    let message = json!({"ncp": PROTOCOL, "session": state.session, "seq": seq, "op": op,
                         "ack": ack, "body": body});
    let frame = frame::encode_with(&message, arrays, options.key, None)
        .map_err(|e| Error::Usage(format!("the request cannot be sent: {e}")))?;
    if frame.len() > state.bound {
        return Err(Error::Usage(format!(
            "a request of {} bytes exceeds the session bound {}",
            frame.len(),
            state.bound
        )));
    }
    let frame = Arc::new(frame);
    let mut next = state.clone();
    next.pending = Some(Pending {
        seq,
        op: op.to_owned(),
        identity: frame::identity(&frame),
        frame: frame.clone(),
        sends: 1,
    });
    Ok((next, frame))
}

fn end(state: &ClientState, error: Error) -> (ClientState, Option<Result<Decoded, Error>>) {
    let mut next = state.clone();
    next.pending = None;
    next.ended = true;
    (next, Some(Err(error)))
}

fn text_detail(body: &Value) -> String {
    body.get("detail")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

/// The detail of a session that ends because the owner rejected a request other than `open`.
pub const LOST_SESSION: &str =
    "the owner rejected a request other than open: it holds another opening of the session (rule 7.6.4)";

/// Apply one frame from the owner (rules 7.6.2 to 7.6.5). Returns the new state and the verdict
/// of the outstanding request, or None if the frame does not end the call: it belongs to no
/// outstanding request, and the binding is lossy.
pub fn receive(
    state: &ClientState,
    frame_bytes: Vec<u8>,
    lossy: bool,
    verify: Verify<'_>,
) -> (ClientState, Option<Result<Decoded, Error>>) {
    let Some(pending) = &state.pending else {
        return (state.clone(), None);
    };
    let decoded = match frame::decode_verified(frame_bytes, state.bound, verify)
        .and_then(|d| check_response(&d.message).map(|()| d))
    {
        Ok(decoded) => decoded,
        Err(_) if lossy => return (state.clone(), None),
        Err(error) => {
            return end(
                state,
                Error::ended("local.bad_frame", Executed::Unknown, error.0),
            )
        }
    };
    let message = &decoded.message;
    if message["session"].is_null() {
        // A response that names no request (section 6.2).
        let code = message["code"].as_str().unwrap_or_default().to_owned();
        let verdict = executed(&code);
        return end(
            state,
            Error::Ended {
                code,
                executed: verdict,
                detail: text_detail(&message["body"]),
                body: message["body"].clone(),
            },
        );
    }
    let matches = message["ncp"] == PROTOCOL
        && message["session"] == state.session.as_str()
        && message["seq"] == pending.seq
        && message["request"] == pending.identity.as_str();
    if !matches {
        if lossy {
            return (state.clone(), None);
        }
        return end(
            state,
            Error::ended(
                "local.protocol",
                Executed::Unknown,
                "a frame that does not belong to the request",
            ),
        );
    }
    let code = message["code"].as_str().unwrap_or_default().to_owned();
    let body = message["body"].clone();
    let mut next = state.clone();
    next.pending = None;
    match message["outcome"].as_str().unwrap_or_default() {
        "ok" => {
            if pending.op == "open" {
                let bound = body["bound"].as_u64().map(|b| b as usize);
                let valid = bound
                    .is_some_and(|b| (HANDSHAKE_BOUND..=state.requested_bound).contains(&b))
                    && is_nonce(&body["nonce"])
                    && body.get("features").is_none_or(Value::is_object);
                if !valid {
                    return end(
                        state,
                        Error::ended(
                            "local.protocol",
                            Executed::Unknown,
                            "the open response breaks section 7.1",
                        ),
                    );
                }
                next.opened = true;
                next.bound = bound.unwrap_or(HANDSHAKE_BOUND);
                next.seq = 0;
            } else {
                next.seq = pending.seq;
                next.ended = pending.op == "close";
            }
            next.ack = Some(decoded.identity.clone());
            (next, Some(Ok(decoded)))
        }
        "declined" => {
            next.seq = pending.seq;
            next.ack = Some(decoded.identity.clone());
            let detail = text_detail(&body);
            (next, Some(Err(Error::Declined { code, detail, body })))
        }
        "rejected" if pending.op == "open" => (next, Some(Err(Error::Rejected { code, body }))),
        "rejected" => end(
            state,
            Error::Ended {
                code,
                executed: Executed::Unknown,
                detail: LOST_SESSION.to_owned(),
                body,
            },
        ),
        _ => {
            let verdict = executed(&code);
            let detail = text_detail(&body);
            end(
                state,
                Error::Ended {
                    code,
                    executed: verdict,
                    detail,
                    body,
                },
            )
        }
    }
}

/// What a client does when no response arrived in time.
#[derive(Debug)]
pub enum TimeoutAction {
    /// Send this frame again (rule 7.6.6).
    Resend(Arc<Vec<u8>>),
    /// The session ended; the request is possibly executed (rule 7.6.7).
    Done(Error),
}

/// No response arrived in time. On a lossy binding, the frame is sent again while copies remain
/// (rule 7.6.6); otherwise the session ends, possibly executed (rule 7.6.7).
pub fn time_out(
    state: &ClientState,
    lossy: bool,
    retries: u32,
) -> (ClientState, Option<TimeoutAction>) {
    let Some(pending) = &state.pending else {
        return (state.clone(), None);
    };
    if lossy && pending.sends <= retries {
        let mut next = state.clone();
        if let Some(p) = next.pending.as_mut() {
            p.sends += 1;
        }
        return (next, Some(TimeoutAction::Resend(pending.frame.clone())));
    }
    let (next, verdict) = end(state, Error::ended("local.timeout", Executed::Unknown, ""));
    (next, verdict.and_then(Result::err).map(TimeoutAction::Done))
}

/// The binding closed or failed: the session ends, and an outstanding request is possibly
/// executed (rule 7.6.7).
pub fn closed(state: &ClientState, detail: &str) -> (ClientState, Option<Error>) {
    if state.pending.is_none() {
        let mut next = state.clone();
        next.ended = true;
        return (next, None);
    }
    let (next, verdict) = end(
        state,
        Error::ended("local.closed", Executed::Unknown, detail),
    );
    (next, verdict.and_then(Result::err))
}

/// The channel reported a bad header. On a lossy binding the frame is dropped; on a byte stream
/// the session ends, possibly executed.
pub fn bad_header(
    state: &ClientState,
    lossy: bool,
    error: &FrameError,
) -> (ClientState, Option<Error>) {
    if lossy || state.pending.is_none() {
        return (state.clone(), None);
    }
    let (next, verdict) = end(
        state,
        Error::ended("local.bad_frame", Executed::Unknown, error.0.clone()),
    );
    (next, verdict.and_then(Result::err))
}

/// A client of one session over one channel (section 7.6).
pub struct Client<C: Channel> {
    channel: C,
    state: ClientState,
    run: Option<String>,
    features: Option<Map<String, Value>>,
    retries: u32,
    check_digests: bool,
    key: Option<Key>,
    owner: Option<Value>,
    observer: Arc<dyn Observer>,
}

impl<C: Channel> fmt::Debug for Client<C> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Client")
            .field("state", &self.state)
            .finish_non_exhaustive()
    }
}

impl<C: Channel> Client<C> {
    /// A client of `contract` over `channel`.
    pub fn new(channel: C, contract: &Contract) -> Client<C> {
        Client {
            channel,
            state: new_state(contract, None, DEFAULT_BOUND),
            run: None,
            features: None,
            retries: 3,
            check_digests: true,
            key: None,
            owner: None,
            observer: default_observer(),
        }
    }

    /// Request a session bound (default 1 MiB).
    ///
    /// # Panics
    ///
    /// If the bound is outside 65,536 to 67,108,864 or the session is open.
    pub fn with_bound(mut self, bound: usize) -> Client<C> {
        assert!((HANDSHAKE_BOUND..=MAX_BOUND).contains(&bound), "bound");
        assert!(!self.state.opened, "the session is open");
        self.state.requested_bound = bound;
        self
    }

    /// Name the run in the `open` request.
    pub fn with_run(mut self, run: &str) -> Client<C> {
        self.run = Some(run.to_owned());
        self
    }

    /// Ask for features in the `open` request (section 7.1), for example
    /// `{"ncp.lockstep": {}}`.
    pub fn with_features(mut self, features: Map<String, Value>) -> Client<C> {
        self.features = Some(features);
        self
    }

    /// Send a request at most `retries` more times on a lossy channel (default 3).
    pub fn with_retries(mut self, retries: u32) -> Client<C> {
        self.retries = retries;
        self
    }

    /// Stop comparing each response's digest with its bytes, under the conditions of spec
    /// section 3, rule 5.
    ///
    /// # Panics
    ///
    /// If the client has a key, or the channel is not a pipe pair or a Unix domain socket.
    pub fn without_digest_check(mut self) -> Client<C> {
        assert!(
            self.key.is_none(),
            "an authenticated session always compares digests"
        );
        assert!(
            self.channel.local(),
            "the digest comparison can be turned off only on a pipe pair or a Unix domain socket"
        );
        self.check_digests = false;
        self
    }

    /// Authenticate every frame with `key` (section 13.2).
    pub fn with_key(mut self, key: Key) -> Client<C> {
        self.check_digests = true;
        self.key = Some(key);
        self
    }

    /// Use this session identifier instead of a random one.
    ///
    /// # Panics
    ///
    /// If it is not a version 4 UUID in lowercase form.
    pub fn with_session(mut self, session: &str) -> Client<C> {
        assert!(
            is_session(session),
            "session must be a lowercase version 4 UUID"
        );
        self.state.session = session.to_owned();
        self
    }

    /// The observer of the client's events.
    pub fn with_observer(mut self, observer: Arc<dyn Observer>) -> Client<C> {
        self.observer = observer;
        self
    }

    /// The session identifier.
    pub fn session(&self) -> &str {
        &self.state.session
    }

    /// The state of the client machine.
    pub fn state(&self) -> &ClientState {
        &self.state
    }

    /// Whether the session ended.
    pub fn ended(&self) -> bool {
        self.state.ended
    }

    /// Whether the session is open.
    pub fn opened(&self) -> bool {
        self.state.opened
    }

    /// The session bound.
    pub fn bound(&self) -> usize {
        self.state.bound
    }

    /// The owner's `open` body, once the session is open.
    pub fn owner(&self) -> Option<&Value> {
        self.owner.as_ref()
    }

    /// The nonce of the opening.
    pub fn nonce(&self) -> Option<&str> {
        self.owner.as_ref()?.get("nonce")?.as_str()
    }

    /// The features that the owner enabled (section 7.1).
    pub fn enabled(&self) -> Map<String, Value> {
        self.owner
            .as_ref()
            .and_then(|o| o.get("features"))
            .and_then(Value::as_object)
            .cloned()
            .unwrap_or_default()
    }

    /// The channel, for binding-specific settings such as time limits.
    pub fn channel_mut(&mut self) -> &mut C {
        &mut self.channel
    }

    /// Open the session and return the owner's `open` body.
    pub fn open(&mut self) -> Result<Value, Error> {
        let pending = self.start_any("open", json!({}), &[])?;
        let result = self.finish(pending)?;
        let body = result.message["body"].clone();
        self.owner = Some(body.clone());
        Ok(body)
    }

    /// Send one request and return the decoded `ok` response.
    pub fn call(&mut self, op: &str, body: Value, arrays: &[Array]) -> Result<Decoded, Error> {
        if op == "open" || op == "close" {
            return Err(Error::Usage("use open() and close()".into()));
        }
        let pending = self.start_any(op, body, arrays)?;
        self.finish(pending)
    }

    /// Send `ncp.ping`: the owner answers without calling the application (rule 7.3.12).
    pub fn ping(&mut self) -> Result<Decoded, Error> {
        let pending = self.start_any("ncp.ping", json!({}), &[])?;
        self.finish(pending)
    }

    /// Close the session, then the channel.
    pub fn close(&mut self) -> Result<(), Error> {
        let result = if self.state.opened && !self.state.ended && self.state.pending.is_none() {
            self.start_any("close", json!({}), &[])
                .and_then(|pending| self.finish(pending))
                .map(|_| ())
        } else {
            Ok(())
        };
        self.state.ended = true;
        self.state.pending = None;
        if !self.channel.lossy() {
            self.channel.close();
        }
        result
    }

    /// Send a request without waiting for its response: the first half of `call`, for
    /// [`call_all`]. The session has one request outstanding until `finish` reads its response.
    pub fn start(&mut self, op: &str, body: Value, arrays: &[Array]) -> Result<Pending, Error> {
        if op == "open" || op == "close" {
            return Err(Error::Usage("use open() and close()".into()));
        }
        self.start_any(op, body, arrays)
    }

    fn start_any(&mut self, op: &str, body: Value, arrays: &[Array]) -> Result<Pending, Error> {
        let options = RequestOptions {
            key: self.key.as_ref(),
            run: self.run.as_deref(),
            features: self.features.as_ref(),
        };
        let (next, frame) = request(&self.state, op, body, arrays, &options)?;
        self.state = next;
        let pending = self.state.pending.clone().expect("a pending request");
        self.send(&frame)?;
        Ok(pending)
    }

    fn send(&mut self, frame: &[u8]) -> Result<(), Error> {
        if let Err(error) = self.channel.send(frame) {
            let (next, verdict) = closed(&self.state, &error.to_string());
            self.state = next;
            return Err(
                verdict.unwrap_or_else(|| Error::ended("local.closed", Executed::Unknown, ""))
            );
        }
        Ok(())
    }

    fn verify(&self) -> Verify<'_> {
        match (&self.key, self.check_digests) {
            (Some(key), _) => Verify::Key(key),
            (None, true) => Verify::Digest,
            (None, false) => Verify::Trust,
        }
    }

    /// Wait for the response to the request that `start` sent: the second half of `call`.
    pub fn finish(&mut self, pending: Pending) -> Result<Decoded, Error> {
        if self.state.pending.as_ref() != Some(&pending) {
            return Err(Error::Usage(
                "finish() takes the request that start() returned, once".into(),
            ));
        }
        let lossy = self.channel.lossy();
        let verdict = loop {
            match self.channel.receive(self.state.bound) {
                Ok(bytes) => {
                    let (next, verdict) = receive(&self.state, bytes, lossy, self.verify());
                    self.state = next;
                    match verdict {
                        Some(verdict) => break verdict,
                        None => self.event("ignored", &pending.op),
                    }
                }
                Err(ChannelError::Timeout) => {
                    let (next, action) = time_out(&self.state, lossy, self.retries);
                    self.state = next;
                    match action {
                        Some(TimeoutAction::Resend(frame)) => {
                            self.event("resent", &pending.op);
                            self.send(&frame)?;
                        }
                        Some(TimeoutAction::Done(error)) => break Err(error),
                        None => break Err(Error::Usage("no request outstanding".into())),
                    }
                }
                Err(ChannelError::BadFrame(error)) => {
                    let (next, verdict) = bad_header(&self.state, lossy, &error);
                    self.state = next;
                    if let Some(error) = verdict {
                        break Err(error);
                    }
                }
                Err(ChannelError::Closed(error)) => {
                    let (next, verdict) = closed(&self.state, &error.to_string());
                    self.state = next;
                    break Err(verdict
                        .unwrap_or_else(|| Error::ended("local.closed", Executed::Unknown, "")));
                }
            }
        };
        self.observer.event(&Event {
            kind: "verdict",
            role: "client",
            session: Some(self.state.session.clone()),
            seq: Some(pending.seq),
            op: Some(pending.op.clone()),
            outcome: Some(match &verdict {
                Ok(_) => "ok",
                Err(Error::Declined { .. }) => "declined",
                Err(Error::Rejected { .. }) => "rejected",
                Err(_) => "ended",
            }),
            code: verdict
                .as_ref()
                .err()
                .and_then(Error::code)
                .map(str::to_owned),
            ..Event::default()
        });
        verdict
    }

    fn event(&self, kind: &'static str, op: &str) {
        self.observer.event(&Event {
            kind,
            role: "client",
            session: Some(self.state.session.clone()),
            seq: self.state.pending.as_ref().map(|p| p.seq),
            op: Some(op.to_owned()),
            ..Event::default()
        });
    }
}

/// Send one request to each session and wait for all responses (spec section 16). Sessions are
/// independent: each result is returned in its place.
///
/// The requests go out first, one to each session, and the responses are read afterwards, in
/// order. The owners therefore work at the same time, without a thread for each session, and
/// each session still has one request outstanding at a time (rule 7.6.1).
///
/// # Panics
///
/// If `clients` and `bodies` differ in length.
pub fn call_all<C: Channel>(
    clients: &mut [Client<C>],
    op: &str,
    bodies: Vec<Value>,
) -> Vec<Result<Decoded, Error>> {
    assert_eq!(clients.len(), bodies.len(), "one body for each client");
    let started: Vec<_> = clients
        .iter_mut()
        .zip(bodies)
        .map(|(client, body)| client.start(op, body, &[]))
        .collect();
    clients
        .iter_mut()
        .zip(started)
        .map(|(client, started)| started.and_then(|pending| client.finish(pending)))
        .collect()
}
