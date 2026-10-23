//! Exchange sessions: messages, the owner state machine, and the client (sections 6 and 7).

use crate::frame::{self, Array, Decoded, FrameError, DEFAULT_BOUND, HANDSHAKE_BOUND, MAX_BOUND};
use serde_json::{json, Map, Value};
use std::collections::BTreeSet;
use std::fmt;
use std::sync::Arc;

/// The protocol version in every message.
pub const PROTOCOL: u64 = 2;
/// The name and version of this implementation, sent in the `open` response.
pub const IMPLEMENTATION: &str = concat!("ncp-rust/", env!("CARGO_PKG_VERSION"));

/// The rejection codes of this version (spec section 7.5). Later versions can add codes; a
/// receiver handles an unknown code by its outcome.
pub const REJECTION_CODES: [&str; 14] = [
    "wrong_protocol",
    "not_open",
    "already_open",
    "wrong_session",
    "seq_stale",
    "seq_gap",
    "seq_conflict",
    "ack_missing",
    "ack_mismatch",
    "unknown_op",
    "body_invalid",
    "contract_mismatch",
    "bound_unacceptable",
    "session_ended",
];
/// The ending codes of this version (spec section 7.5).
pub const ENDING_CODES: [&str; 4] = ["result_too_large", "owner_failure", "bad_frame", "shutdown"];

/// Whether the request named by an `ended` response executed: "yes", "no", or "unknown". A code
/// that this version does not know gives "unknown" (spec section 7.5).
pub fn executed_for(code: &str) -> &'static str {
    match code {
        "result_too_large" => "yes",
        "bad_frame" | "shutdown" => "no",
        _ => "unknown",
    }
}

fn is_code(value: &Value) -> bool {
    value.as_str().is_some_and(|c| (1..=64).contains(&c.len()) && c.bytes().all(|b| b.is_ascii_lowercase() || b == b'_'))
}

/// Whether a value is an identity: 64 lowercase hexadecimal characters.
pub fn is_identity(value: &Value) -> bool {
    value.as_str().is_some_and(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
}

fn is_session(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 36
        && b.iter().enumerate().all(|(i, &c)| match i {
            8 | 13 | 18 | 23 => c == b'-',
            14 => c == b'4',
            19 => matches!(c, b'8' | b'9' | b'a' | b'b'),
            _ => c.is_ascii_digit() || (b'a'..=b'f').contains(&c),
        })
}

fn is_operation(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.len() <= 64
        && b[0].is_ascii_lowercase()
        && b.iter().all(|&c| c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, b'_' | b'.' | b'-'))
}

fn members(object: &Map<String, Value>, required: &[&str]) -> bool {
    object.len() == required.len() + usize::from(object.contains_key("att"))
        && required.iter().all(|key| object.contains_key(*key))
}

/// Fail unless the message has the request form of section 6.1.
pub fn check_request(message: &Value) -> Result<(), FrameError> {
    let object = message.as_object().ok_or_else(|| FrameError("request".into()))?;
    let ok = members(object, &["ncp", "session", "seq", "op", "ack", "body"])
        && object["ncp"].is_u64()
        && object["session"].as_str().is_some_and(is_session)
        && object["seq"].is_u64()
        && object["op"].as_str().is_some_and(is_operation)
        && (object["ack"].is_null() || is_identity(&object["ack"]));
    if ok { Ok(()) } else { Err(FrameError("request members".into())) }
}

/// Fail unless the message has the response form of section 6.2.
pub fn check_response(message: &Value) -> Result<(), FrameError> {
    let object = message.as_object().ok_or_else(|| FrameError("response".into()))?;
    if !members(object, &["ncp", "session", "seq", "request", "outcome", "code", "body"]) || !object["ncp"].is_u64() {
        return Err(FrameError("response members".into()));
    }
    let ok = match object["outcome"].as_str() {
        Some("ok") => {
            object["code"].is_null() && object["session"].is_string() && object["seq"].is_u64() && is_identity(&object["request"])
        }
        Some("rejected") => is_code(&object["code"]) && object["seq"].is_u64() && is_identity(&object["request"]),
        Some("ended") => {
            is_code(&object["code"])
                && ((object["session"].is_null() && object["seq"].is_null() && object["request"].is_null())
                    || (object["seq"].is_u64() && is_identity(&object["request"])))
        }
        _ => false,
    };
    if ok { Ok(()) } else { Err(FrameError("response member types".into())) }
}

/// A result of an application operation: a body and the arrays that it refers to.
#[derive(Debug, Clone, Default)]
pub struct Reply {
    /// The result body.
    pub body: Value,
    /// Arrays referred to from the body with [`Array::reference`].
    pub arrays: Vec<Array>,
}

impl From<Value> for Reply {
    fn from(body: Value) -> Reply {
        Reply { body, arrays: Vec::new() }
    }
}

/// The application side of an owner.
pub trait Handler {
    /// Check a request body. Return `Err(detail)` to reject it. Must not change any state.
    fn validate(&mut self, op: &str, request: &Decoded) -> Result<(), String>;
    /// Execute one request. An `Err` ends the session with `owner_failure`.
    fn execute(&mut self, op: &str, request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>>;
}

/// The owner state machine of section 7.3. One instance serves one session.
pub struct Owner<H: Handler> {
    application: String,
    contract: String,
    handler: H,
    operations: BTreeSet<String>,
    max_bound: usize,
    session: Option<String>,
    bound: usize,
    high: u64,
    kept: Option<(String, Arc<Vec<u8>>, String)>, // request identity, response frame, response identity
    ended: bool,
    closed: bool,
    check_digests: bool,
}

impl<H: Handler> fmt::Debug for Owner<H> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Owner")
            .field("application", &self.application)
            .field("session", &self.session)
            .field("bound", &self.bound)
            .field("high", &self.high)
            .field("ended", &self.ended)
            .finish_non_exhaustive()
    }
}

impl<H: Handler> Owner<H> {
    /// A new owner for one session of `application` with contract identity `contract`.
    pub fn new(application: &str, contract: &str, handler: H, operations: impl IntoIterator<Item = String>, max_bound: usize) -> Owner<H> {
        assert!(is_identity(&Value::from(contract)), "contract must be an identity");
        assert!((HANDSHAKE_BOUND..=MAX_BOUND).contains(&max_bound), "max_bound");
        let operations = operations.into_iter().filter(|op| op != "open" && op != "close").collect();
        Owner {
            application: application.to_owned(),
            contract: contract.to_owned(),
            handler,
            operations,
            max_bound,
            session: None,
            bound: HANDSHAKE_BOUND,
            high: 0,
            kept: None,
            ended: false,
            closed: false,
            check_digests: true,
        }
    }

    /// Stop comparing each request's digest with its bytes. Use it only on a pipe pair or a Unix
    /// domain socket with no other program between the endpoints (spec section 3, rule 4).
    /// Response digests are always computed.
    pub fn without_digest_check(mut self) -> Owner<H> {
        self.check_digests = false;
        self
    }

    /// The bound that the binding must apply to the next request.
    pub fn bound(&self) -> usize {
        self.bound
    }

    /// Whether the session ended with an `ok` response to `close`.
    pub fn closed(&self) -> bool {
        self.closed
    }

    /// The application handler.
    pub fn handler(&mut self) -> &mut H {
        &mut self.handler
    }

    /// Handle one request frame and return the response frame. Fails only for a bad frame,
    /// which the binding handles (section 9).
    pub fn handle(&mut self, frame_bytes: Vec<u8>) -> Result<Arc<Vec<u8>>, FrameError> {
        let decoded = frame::decode_with(frame_bytes, self.bound, self.check_digests)?;
        check_request(&decoded.message)?;
        let request = &decoded.message;
        let session = request["session"].as_str().unwrap_or_default().to_owned();
        let seq = request["seq"].as_u64().unwrap_or_default();
        let op = request["op"].as_str().unwrap_or_default().to_owned();
        let request_id = decoded.identity.clone();
        let reply = |outcome: &str, code: Option<&str>, body: Value, arrays: &[Array]| -> Result<Arc<Vec<u8>>, FrameError> {
            let message = json!({"ncp": PROTOCOL, "session": session, "seq": seq, "request": request_id,
                                  "outcome": outcome, "code": code, "body": body});
            frame::encode(&message, arrays).map(Arc::new)
        };
        let reject = |code: &str, detail: Option<String>| {
            let body = match detail {
                Some(detail) => json!({"detail": detail}),
                None => json!({}),
            };
            reply("rejected", Some(code), body, &[])
        };
        if request["ncp"].as_u64() != Some(PROTOCOL) {
            return reject("wrong_protocol", None);
        }
        let Some(open_session) = self.session.clone() else {
            if op != "open" || seq != 0 {
                return reject("not_open", None);
            }
            return self.open(&decoded, reply, reject);
        };
        if session != open_session {
            return reject("wrong_session", None);
        }
        if let Some((kept_request, kept_response, _)) = &self.kept {
            if seq == self.high {
                if *kept_request == decoded.identity {
                    return Ok(kept_response.clone());
                }
                return reject("seq_conflict", None);
            }
        }
        if seq <= self.high {
            return reject("seq_stale", None);
        }
        if seq > self.high + 1 {
            return reject("seq_gap", None);
        }
        if self.ended {
            return reject("session_ended", None);
        }
        match request["ack"].as_str() {
            None => return reject("ack_missing", None),
            Some(ack) => {
                if self.kept.as_ref().map(|k| k.2.as_str()) != Some(ack) {
                    return reject("ack_mismatch", None);
                }
            }
        }
        if op == "open" {
            return reject("already_open", None);
        }
        if op != "close" {
            if !self.operations.contains(&op) {
                return reject("unknown_op", None);
            }
            if let Err(detail) = self.handler.validate(&op, &decoded) {
                let detail: String = detail.chars().take(256).collect();
                return reject("body_invalid", if detail.is_empty() { None } else { Some(detail) });
            }
        }
        self.kept = None;
        self.high = seq;
        let response = if op == "close" {
            self.ended = true;
            self.closed = true;
            reply("ok", None, json!({}), &[])?
        } else {
            match self.handler.execute(&op, &decoded) {
                Err(_) => {
                    self.ended = true;
                    reply("ended", Some("owner_failure"), json!({}), &[])?
                }
                Ok(result) => match reply("ok", None, result.body, &result.arrays) {
                    Err(error) => {
                        self.ended = true;
                        reply("ended", Some("owner_failure"), json!({"detail": error.0.chars().take(256).collect::<String>()}), &[])?
                    }
                    Ok(response) if response.len() > self.bound => {
                        self.ended = true;
                        reply("ended", Some("result_too_large"), json!({"size": response.len(), "bound": self.bound}), &[])?
                    }
                    Ok(response) => response,
                },
            }
        };
        self.kept = Some((decoded.identity.clone(), response.clone(), frame::identity(&response)));
        Ok(response)
    }

    fn open(
        &mut self,
        decoded: &Decoded,
        reply: impl Fn(&str, Option<&str>, Value, &[Array]) -> Result<Arc<Vec<u8>>, FrameError>,
        reject: impl Fn(&str, Option<String>) -> Result<Arc<Vec<u8>>, FrameError>,
    ) -> Result<Arc<Vec<u8>>, FrameError> {
        let request = &decoded.message;
        let body = match (&request["ack"], request["body"].as_object()) {
            (Value::Null, Some(body)) => body,
            _ => return reject("body_invalid", Some("open body".into())),
        };
        let keys_ok = ["application", "contract", "bound"].iter().all(|k| body.contains_key(*k))
            && body.keys().all(|k| matches!(k.as_str(), "application" | "contract" | "bound" | "run"));
        if !keys_ok {
            return reject("body_invalid", Some("open members".into()));
        }
        let run_ok = match body.get("run") {
            None => true,
            Some(run) => run.as_str().is_some_and(|r| r.chars().count() <= 256),
        };
        let bound = body["bound"].as_u64();
        if !body["application"].is_string() || !is_identity(&body["contract"]) || bound.is_none() || !run_ok {
            return reject("body_invalid", Some("open member types".into()));
        }
        if body["application"] != self.application.as_str() || body["contract"] != self.contract.as_str() {
            return reject("contract_mismatch", None);
        }
        let bound = bound.unwrap_or_default() as usize;
        if !(HANDSHAKE_BOUND..=MAX_BOUND).contains(&bound) {
            return reject("bound_unacceptable", None);
        }
        let effective = bound.min(self.max_bound);
        let response = reply(
            "ok",
            None,
            json!({"bound": effective, "application": self.application, "contract": self.contract,
                   "implementation": IMPLEMENTATION}),
            &[],
        )?;
        self.session = request["session"].as_str().map(str::to_owned);
        self.bound = effective;
        self.high = 0;
        self.kept = Some((decoded.identity.clone(), response.clone(), frame::identity(&response)));
        Ok(response)
    }
}

/// The response a byte-stream owner sends for a bad frame before it closes (section 9.1).
pub fn bad_frame_response() -> Vec<u8> {
    let message = json!({"ncp": PROTOCOL, "session": null, "seq": null, "request": null,
                          "outcome": "ended", "code": "bad_frame", "body": {}});
    frame::encode(&message, &[]).unwrap_or_default()
}

/// A client-side failure.
#[derive(Debug)]
pub enum Error {
    /// The owner did not execute the request and changed no state.
    Rejected {
        /// The rejection code.
        code: String,
        /// The response body.
        body: Value,
    },
    /// The session ended. `executed` is "yes", "no", or "unknown" for the last request.
    Ended {
        /// The ending code, or "timeout" or "closed" for a local end.
        code: String,
        /// Whether the last request executed.
        executed: &'static str,
    },
    /// The peer broke the protocol, or the session is not usable.
    Protocol(String),
    /// A bad frame from the peer.
    Frame(FrameError),
    /// An input or output error of the binding.
    Io(std::io::Error),
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Error::Rejected { code, .. } => write!(f, "rejected: {code}"),
            Error::Ended { code, executed } => write!(f, "session ended: {code} (executed: {executed})"),
            Error::Protocol(reason) => write!(f, "protocol error: {reason}"),
            Error::Frame(error) => write!(f, "{error}"),
            Error::Io(error) => write!(f, "io: {error}"),
        }
    }
}

impl std::error::Error for Error {}

impl From<FrameError> for Error {
    fn from(error: FrameError) -> Error {
        Error::Frame(error)
    }
}

impl From<std::io::Error> for Error {
    fn from(error: std::io::Error) -> Error {
        Error::Io(error)
    }
}

/// A binding as seen by a client: one frame out, one frame in.
pub trait Channel {
    /// Whether the binding can lose frames (section 9.2). A lossy channel allows retries.
    fn lossy(&self) -> bool;
    /// Send one frame.
    fn send(&mut self, frame: &[u8]) -> std::io::Result<()>;
    /// Receive one frame, checking its header against `bound`.
    fn receive(&mut self, bound: usize) -> Result<Vec<u8>, Error>;
    /// Close the channel. One byte-stream connection carries one session.
    fn close(&mut self) {}
}

/// The client rules of section 7.6, over one channel.
pub struct Client<C: Channel> {
    channel: C,
    application: String,
    contract: String,
    requested_bound: usize,
    run: Option<String>,
    retries: u32,
    session: String,
    bound: usize,
    seq: u64,
    ack: Option<String>,
    ended: bool,
    opened: bool,
    check_digests: bool,
}

impl<C: Channel> fmt::Debug for Client<C> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Client")
            .field("application", &self.application)
            .field("session", &self.session)
            .field("seq", &self.seq)
            .field("bound", &self.bound)
            .field("ended", &self.ended)
            .finish_non_exhaustive()
    }
}

impl<C: Channel> Client<C> {
    /// A client for `application` with contract identity `contract`.
    pub fn new(channel: C, application: &str, contract: &str) -> Client<C> {
        Client {
            channel,
            application: application.to_owned(),
            contract: contract.to_owned(),
            requested_bound: DEFAULT_BOUND,
            run: None,
            retries: 3,
            session: crate::random_session(),
            bound: HANDSHAKE_BOUND,
            seq: 0,
            ack: None,
            ended: false,
            opened: false,
            check_digests: true,
        }
    }

    /// Stop comparing each response's digest with its bytes, under the conditions of spec
    /// section 3, rule 4.
    pub fn without_digest_check(mut self) -> Client<C> {
        self.check_digests = false;
        self
    }

    /// Request a session bound (default 1 MiB).
    pub fn with_bound(mut self, bound: usize) -> Client<C> {
        self.requested_bound = bound;
        self
    }

    /// Name the run in the `open` request.
    pub fn with_run(mut self, run: &str) -> Client<C> {
        self.run = Some(run.to_owned());
        self
    }

    /// The session identifier.
    pub fn session(&self) -> &str {
        &self.session
    }

    /// The channel, for binding-specific settings such as time limits.
    pub fn channel_mut(&mut self) -> &mut C {
        &mut self.channel
    }

    /// Open the session and return the owner's `open` body.
    pub fn open(&mut self) -> Result<Value, Error> {
        let mut body = json!({"application": self.application, "contract": self.contract, "bound": self.requested_bound});
        if let Some(run) = &self.run {
            body["run"] = Value::from(run.clone());
        }
        let result = self.exchange(0, "open", body, &[])?;
        let bound = result.message["body"]["bound"].as_u64().map(|b| b as usize);
        match bound {
            Some(bound) if (HANDSHAKE_BOUND..=self.requested_bound).contains(&bound) => {
                self.bound = bound;
                self.opened = true;
                Ok(result.message["body"].clone())
            }
            _ => Err(Error::Protocol("open response".into())),
        }
    }

    /// Send one request and return the decoded `ok` response.
    pub fn call(&mut self, op: &str, body: Value, arrays: &[Array]) -> Result<Decoded, Error> {
        if !self.opened {
            return Err(Error::Protocol("call before open".into()));
        }
        if op == "open" || op == "close" {
            return Err(Error::Protocol("use open() and close()".into()));
        }
        self.exchange(self.seq + 1, op, body, arrays)
    }

    /// Close the session and the channel.
    pub fn close(&mut self) -> Result<(), Error> {
        let result = if !self.ended && self.opened { self.exchange(self.seq + 1, "close", json!({}), &[]).map(|_| ()) } else { Ok(()) };
        self.ended = true;
        if !self.channel.lossy() {
            self.channel.close();
        }
        result
    }

    fn exchange(&mut self, seq: u64, op: &str, body: Value, arrays: &[Array]) -> Result<Decoded, Error> {
        if self.ended {
            return Err(Error::Protocol("session ended".into()));
        }
        let message = json!({"ncp": PROTOCOL, "session": self.session, "seq": seq, "op": op, "ack": self.ack, "body": body});
        let request = frame::encode(&message, arrays)?;
        if request.len() > self.bound {
            return Err(Error::Protocol(format!("request of {} bytes exceeds the bound {}", request.len(), self.bound)));
        }
        let request_id = frame::identity(&request);
        let attempts = if self.channel.lossy() { self.retries + 1 } else { 1 };
        for attempt in 0..attempts {
            self.channel.send(&request)?;
            let decoded = match self.receive_match(seq, &request_id) {
                Err(Error::Io(error)) if error.kind() == std::io::ErrorKind::TimedOut || error.kind() == std::io::ErrorKind::WouldBlock => {
                    if attempt + 1 < attempts {
                        continue;
                    }
                    self.ended = true;
                    return Err(Error::Ended { code: "timeout".into(), executed: "unknown" });
                }
                other => other?,
            };
            let outcome = decoded.message["outcome"].as_str().unwrap_or_default().to_owned();
            let code = decoded.message["code"].as_str().unwrap_or_default().to_owned();
            return match outcome.as_str() {
                "ok" => {
                    self.seq = seq;
                    self.ack = Some(decoded.identity.clone());
                    if op == "close" {
                        self.ended = true;
                    }
                    Ok(decoded)
                }
                "rejected" => Err(Error::Rejected { code, body: decoded.message["body"].clone() }),
                _ => {
                    self.ended = true;
                    let executed = executed_for(&code);
                    Err(Error::Ended { code, executed })
                }
            };
        }
        Err(Error::Protocol("unreachable".into()))
    }

    fn receive_match(&mut self, seq: u64, request_id: &str) -> Result<Decoded, Error> {
        loop {
            let frame_bytes = match self.channel.receive(self.bound) {
                Ok(bytes) => bytes,
                Err(Error::Frame(error)) if !self.channel.lossy() => {
                    self.ended = true;
                    return Err(Error::Protocol(format!("bad frame from the owner: {error}")));
                }
                Err(Error::Frame(_)) => continue,
                Err(other) => return Err(other),
            };
            let decoded = match frame::decode_with(frame_bytes, self.bound, self.check_digests).and_then(|d| check_response(&d.message).map(|_| d)) {
                Ok(decoded) => decoded,
                Err(_) if self.channel.lossy() => continue,
                Err(error) => {
                    self.ended = true;
                    return Err(Error::Protocol(format!("bad frame from the owner: {error}")));
                }
            };
            let message = &decoded.message;
            if message["session"].is_null() {
                let code = message["code"].as_str().unwrap_or_default().to_owned();
                self.ended = true;
                let executed = executed_for(&code);
                return Err(Error::Ended { code, executed });
            }
            if message["session"] == self.session.as_str() && message["seq"] == seq && message["request"] == request_id && message["ncp"] == PROTOCOL {
                return Ok(decoded);
            }
            if !self.channel.lossy() {
                self.ended = true;
                return Err(Error::Protocol("response does not match the request".into()));
            }
        }
    }
}
