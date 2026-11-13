//! The owner (specification sections 7.1 to 7.3).
//!
//! [`step`] is the owner state machine: a function from an [`OwnerState`] and one decoded request
//! to the new state and the response frame. It calls the application only through the handler
//! that it is given. The Lean model in `formal/` states the same rules, and the gate compares the
//! two. [`Owner`] drives [`step`] for one session and keeps its state.

use crate::contract::Contract;
use crate::events::{default_observer, Event, Observer};
use crate::frame::{
    self, Array, Decoded, EncodeError, FrameError, Key, Verify, DEFAULT_BOUND, HANDSHAKE_BOUND,
    MAX_BOUND,
};
use crate::messages::{
    check_request, detail, foreign, is_identity, is_name, MAX_FEATURES, MAX_RUN, PROTOCOL,
};
use serde_json::{json, Map, Value};
use std::fmt;
use std::sync::Arc;

/// The name and version of this implementation, sent in the `open` response.
pub const IMPLEMENTATION: &str = concat!("ncp-rust/", env!("CARGO_PKG_VERSION"));

/// An error of the application.
pub type AppError = Box<dyn std::error::Error + Send + Sync>;

/// Why a handler does not let a request run (rule 7.3.12).
#[derive(Debug)]
pub enum Invalid {
    /// Decline the request: the owner responds `declined` with `body_invalid` and the detail, and
    /// the request never runs. Make it with [`declined`].
    Declined(String),
    /// The application failed while it checked the body: the session ends with `owner_failure`.
    Failed(AppError),
}

/// Decline a request with a detail, from a handler's `validate`.
pub fn declined(detail: impl Into<String>) -> Invalid {
    Invalid::Declined(detail.into())
}

/// Returned by a handler's `open` to refuse a session: the owner rejects the `open` with the code
/// `refused` (section 7.1, rule 4.4).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Refused(pub String);

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
        Reply {
            body,
            arrays: Vec::new(),
        }
    }
}

/// What the client asked for in its `open` request.
#[derive(Debug)]
pub struct OpenInfo<'a> {
    /// The session identifier.
    pub session: &'a str,
    /// The contract that the session uses.
    pub contract: &'a Contract,
    /// The run name, if any.
    pub run: Option<&'a str>,
    /// The features that the client asked for, with its parameters.
    pub features: &'a Map<String, Value>,
}

/// One admitted request, as the handler sees it.
#[derive(Debug)]
pub struct Request<'a> {
    /// The operation.
    pub op: &'a str,
    /// The body. Array references stay in place as `{"ncp.array": ...}` objects.
    pub body: &'a Value,
    /// The sequence number.
    pub seq: u64,
    /// The session identifier.
    pub session: &'a str,
    /// The identity of the request frame.
    pub identity: &'a str,
    /// The contract that the session uses.
    pub contract: &'a Contract,
    /// The run name of the session, if any.
    pub run: Option<&'a str>,
    /// The features that the owner enabled for the session.
    pub features: &'a Map<String, Value>,
    /// The decoded frame, for its arrays.
    pub decoded: &'a Decoded,
}

impl Request<'_> {
    /// The little-endian bytes of array `index`, without a copy.
    pub fn array_bytes(&self, index: usize) -> Option<&[u8]> {
        self.decoded.array_bytes(index)
    }

    /// The arrays as owned values, for example to send them on.
    pub fn owned_arrays(&self) -> Vec<Array> {
        self.decoded.owned_arrays()
    }
}

/// The application side of an owner.
pub trait Handler {
    /// Check a request. Return [`declined`] to decline it. Must not change any state.
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid>;
    /// Execute one request. An `Err` ends the session with `owner_failure`.
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError>;
    /// Called when the owner accepts an `open`. Return the features that the handler enables,
    /// as {name: parameters}, or [`Refused`]. The default enables none.
    fn open(&mut self, _info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        Ok(Map::new())
    }
    /// Called once when the session ends: reason "closed", "ended", "lost", "shutdown", or
    /// "expired".
    fn close(&mut self, _reason: &str) {}
}

/// The response to the last admitted request (section 7.2).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Kept {
    /// The identity of the request.
    pub request: String,
    /// The response frame.
    pub response: Arc<Vec<u8>>,
    /// The identity of the response.
    pub identity: String,
}

/// The state of an owner for one session (section 7.2), and what it agreed at `open`.
#[derive(Debug, Clone, PartialEq)]
pub struct OwnerState {
    /// The session that the owner holds, if any.
    pub session: Option<String>,
    /// The session bound.
    pub bound: usize,
    /// The sequence number of the last admitted request.
    pub high: u64,
    /// The response to the last admitted request.
    pub kept: Option<Kept>,
    /// Whether the session ended.
    pub ended: bool,
    /// Whether the session ended with an `ok` response to `close`.
    pub closed: bool,
    /// Whether the owner stops: it admits no new request (rule 7.3.10).
    pub stopping: bool,
    /// The index, in the configuration, of the contract that the session uses.
    pub contract: Option<usize>,
    /// The run name of the session, if any.
    pub run: Option<String>,
    /// The nonce of the opening.
    pub nonce: Option<String>,
    /// The features that the owner enabled.
    pub features: Map<String, Value>,
}

impl Default for OwnerState {
    fn default() -> OwnerState {
        OwnerState {
            session: None,
            bound: HANDSHAKE_BOUND,
            high: 0,
            kept: None,
            ended: false,
            closed: false,
            stopping: false,
            contract: None,
            run: None,
            nonce: None,
            features: Map::new(),
        }
    }
}

/// What an owner knows before any session: its contracts, its limits, and its key.
#[derive(Clone)]
pub struct OwnerConfig {
    /// The contracts that the owner accepts, all of one application.
    pub contracts: Vec<Contract>,
    /// The largest session bound.
    pub max_bound: usize,
    /// The name and version of the implementation.
    pub implementation: String,
    /// The key of an authenticated session (section 13.2).
    pub key: Option<Key>,
    /// Whether the owner checks requests against the contract's schemas (section 11).
    pub check_schemas: bool,
    /// A fresh nonce for each opening (section 7.1, rule 5).
    pub nonce: Arc<dyn Fn() -> String + Send + Sync>,
}

impl fmt::Debug for OwnerConfig {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("OwnerConfig")
            .field(
                "application",
                &self.contracts.first().map(|c| &c.application),
            )
            .field("max_bound", &self.max_bound)
            .field("check_schemas", &self.check_schemas)
            .finish_non_exhaustive()
    }
}

impl OwnerConfig {
    /// A configuration for `contracts`, which must name one application.
    pub fn new(contracts: Vec<Contract>) -> Result<OwnerConfig, FrameError> {
        let Some(first) = contracts.first() else {
            return Err(FrameError("an owner needs at least one contract".into()));
        };
        if contracts.iter().any(|c| c.application != first.application) {
            return Err(FrameError(
                "the contracts of one owner name one application".into(),
            ));
        }
        Ok(OwnerConfig {
            contracts,
            max_bound: DEFAULT_BOUND,
            implementation: IMPLEMENTATION.to_owned(),
            key: None,
            check_schemas: true,
            nonce: Arc::new(crate::random_nonce),
        })
    }
}

/// What one step did, for observers and for the model check.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Note {
    /// "opened", "open_rejected", "admitted", "repeated", "rejected", "expired", "shutdown", or
    /// "application_error".
    pub kind: &'static str,
    /// The outcome of the response.
    pub outcome: Option<&'static str>,
    /// The code of the response.
    pub code: Option<&'static str>,
    /// A detail.
    pub detail: Option<String>,
    /// Whether the application's `execute` was called.
    pub executed: bool,
    /// The error of the application, as text.
    pub error: Option<String>,
}

fn note(kind: &'static str, outcome: &'static str, code: Option<&'static str>) -> Note {
    Note {
        kind,
        outcome: Some(outcome),
        code,
        ..Note::default()
    }
}

fn valid_features(value: &Value) -> bool {
    value.as_object().is_some_and(|features| {
        features.len() <= MAX_FEATURES
            && features
                .iter()
                .all(|(name, params)| is_name(name) && params.is_object())
    })
}

/// Apply rules 7.3.2 to 7.3.13 to one decoded frame.
///
/// Fails with FrameError if the frame is not a request (rule 7.3.1: the binding's bad-frame
/// rule). Otherwise returns the new state, the response frame, and a note of what happened.
pub fn step<H: Handler + ?Sized>(
    config: &OwnerConfig,
    state: &OwnerState,
    decoded: &Decoded,
    handler: &mut H,
) -> Result<(OwnerState, Arc<Vec<u8>>, Note), FrameError> {
    let request = &decoded.message;
    if !foreign(request) {
        // A request of another protocol version gets wrong_protocol below.
        check_request(request)?;
    }
    let request_id = decoded.identity.as_str();
    let session = request["session"].as_str().unwrap_or_default();
    let seq = request["seq"].as_u64().unwrap_or_default();
    let op = request["op"].as_str().unwrap_or_default();
    let key = config.key.as_ref();
    let reply = |outcome: &str,
                 code: Option<&str>,
                 body: Value,
                 arrays: &[Array],
                 limit: Option<usize>|
     -> Result<Arc<Vec<u8>>, EncodeError> {
        let message = json!({"ncp": PROTOCOL, "session": session, "seq": seq,
                             "request": request_id, "outcome": outcome, "code": code, "body": body});
        frame::encode_with(&message, arrays, key, limit).map(Arc::new)
    };
    let small = |outcome: &str, code: &str, body: Value| -> Result<Arc<Vec<u8>>, FrameError> {
        reply(outcome, Some(code), body, &[], None).map_err(FrameError::from)
    };
    let reject =
        |code: &'static str, text: &str| -> Result<(OwnerState, Arc<Vec<u8>>, Note), FrameError> {
            let body = if text.is_empty() {
                json!({})
            } else {
                json!({"detail": detail(text)})
            };
            let mut n = note("rejected", "rejected", Some(code));
            if !text.is_empty() {
                n.detail = Some(text.to_owned());
            }
            Ok((state.clone(), small("rejected", code, body)?, n))
        };
    if request["ncp"] != PROTOCOL {
        return reject("wrong_protocol", "");
    }
    let Some(held) = state.session.as_deref() else {
        if seq == 0 && op == "open" {
            return open(config, state, decoded, handler, &small);
        }
        if seq == 0 {
            return reject("not_open", "");
        }
        let response = small("ended", "session_expired", json!({}))?;
        return Ok((
            state.clone(),
            response,
            note("expired", "ended", Some("session_expired")),
        ));
    };
    if session != held {
        return reject("wrong_session", "");
    }
    if let Some(kept) = &state.kept {
        if seq == state.high {
            if kept.request == request_id {
                return Ok((
                    state.clone(),
                    kept.response.clone(),
                    Note {
                        kind: "repeated",
                        ..Note::default()
                    },
                ));
            }
            return reject("seq_conflict", "");
        }
    }
    if seq <= state.high {
        return reject("seq_stale", "");
    }
    if seq > state.high + 1 {
        return reject("seq_gap", "");
    }
    if state.ended {
        return reject("session_ended", "");
    }
    match request["ack"].as_str() {
        None => return reject("ack_missing", ""),
        Some(ack) => {
            if state.kept.as_ref().map(|k| k.identity.as_str()) != Some(ack) {
                return reject("ack_mismatch", "");
            }
        }
    }
    if op == "open" {
        return reject("already_open", "");
    }
    if state.stopping {
        let response = small("ended", "shutdown", json!({}))?;
        return Ok((
            state.clone(),
            response,
            note("shutdown", "ended", Some("shutdown")),
        ));
    }
    // Rule 11: the request is admitted. Every response from here on is kept.
    let ok_empty = || reply("ok", None, json!({}), &[], None).map_err(FrameError::from);
    let (response, n, ends) = match op {
        "close" => (ok_empty()?, note("admitted", "ok", None), true),
        "ncp.ping" => (ok_empty()?, note("admitted", "ok", None), false),
        _ => {
            let (response, n) = call(config, state, decoded, op, handler, &reply)?;
            let ends = n.outcome == Some("ended");
            (response, n, ends)
        }
    };
    let mut next = state.clone();
    next.high = seq;
    next.kept = Some(Kept {
        request: request_id.to_owned(),
        identity: frame::identity(&response),
        response: response.clone(),
    });
    next.ended = ends;
    next.closed = op == "close";
    Ok((next, response, n))
}

type Small<'r> = dyn Fn(&str, &str, Value) -> Result<Arc<Vec<u8>>, FrameError> + 'r;

type Replier<'r> = dyn Fn(&str, Option<&str>, Value, &[Array], Option<usize>) -> Result<Arc<Vec<u8>>, EncodeError>
    + 'r;

/// Rule 12 for an operation of the application.
fn call<H: Handler + ?Sized>(
    config: &OwnerConfig,
    state: &OwnerState,
    decoded: &Decoded,
    op: &str,
    handler: &mut H,
    reply: &Replier<'_>,
) -> Result<(Arc<Vec<u8>>, Note), FrameError> {
    let contract = &config.contracts[state.contract.unwrap_or_default()];
    let small = |outcome: &str, code: &str, body: Value| -> Result<Arc<Vec<u8>>, FrameError> {
        reply(outcome, Some(code), body, &[], None).map_err(FrameError::from)
    };
    if !contract.has_operation(op) {
        let response = small("declined", "unknown_op", json!({}))?;
        return Ok((response, note("admitted", "declined", Some("unknown_op"))));
    }
    let message = &decoded.message;
    let body = &message["body"];
    if config.check_schemas {
        if let Some(mismatch) = contract.check_request(op, body) {
            let text = detail(&format!("request schema: {mismatch}"));
            let response = small("declined", "body_invalid", json!({"detail": text}))?;
            let mut n = note("admitted", "declined", Some("body_invalid"));
            n.detail = Some(text);
            return Ok((response, n));
        }
    }
    let request = Request {
        op,
        body,
        seq: message["seq"].as_u64().unwrap_or_default(),
        session: message["session"].as_str().unwrap_or_default(),
        identity: &decoded.identity,
        contract,
        run: state.run.as_deref(),
        features: &state.features,
        decoded,
    };
    match handler.validate(&request) {
        Ok(()) => {}
        Err(Invalid::Declined(text)) => {
            let text = detail(&text);
            let body = if text.is_empty() {
                json!({})
            } else {
                json!({"detail": text})
            };
            let response = small("declined", "body_invalid", body)?;
            let mut n = note("admitted", "declined", Some("body_invalid"));
            n.detail = (!text.is_empty()).then_some(text);
            return Ok((response, n));
        }
        Err(Invalid::Failed(error)) => {
            let response = small("ended", "owner_failure", json!({}))?;
            let mut n = note("application_error", "ended", Some("owner_failure"));
            n.detail = Some("the application failed while it checked the body".into());
            n.error = Some(error.to_string());
            return Ok((response, n));
        }
    }
    let result = match handler.execute(&request) {
        Ok(result) => result,
        Err(error) => {
            let response = small("ended", "owner_failure", json!({}))?;
            let mut n = note("application_error", "ended", Some("owner_failure"));
            n.detail = Some("the application failed".into());
            n.error = Some(error.to_string());
            n.executed = true;
            return Ok((response, n));
        }
    };
    let mut done = note("admitted", "ok", None);
    done.executed = true;
    match reply("ok", None, result.body, &result.arrays, Some(state.bound)) {
        Ok(response) => Ok((response, done)),
        Err(EncodeError::TooLarge(t)) => {
            let body = if t.json {
                json!({"json": t.size, "limit": t.limit})
            } else {
                json!({"size": t.size, "bound": state.bound})
            };
            let response = small("ended", "result_too_large", body)?;
            let mut n = note("admitted", "ended", Some("result_too_large"));
            n.executed = true;
            Ok((response, n))
        }
        Err(EncodeError::Invalid(error)) => {
            let text = detail(&format!("the result cannot be sent: {}", error.0));
            let response = small("ended", "owner_failure", json!({"detail": text}))?;
            let mut n = note("application_error", "ended", Some("owner_failure"));
            n.detail = Some(text);
            n.error = Some(error.0);
            n.executed = true;
            Ok((response, n))
        }
    }
}

/// Section 7.1 for an `open` request while no session is held.
fn open<H: Handler + ?Sized>(
    config: &OwnerConfig,
    state: &OwnerState,
    decoded: &Decoded,
    handler: &mut H,
    small: &Small<'_>,
) -> Result<(OwnerState, Arc<Vec<u8>>, Note), FrameError> {
    let request = &decoded.message;
    let reject =
        |code: &'static str, text: &str| -> Result<(OwnerState, Arc<Vec<u8>>, Note), FrameError> {
            let body = if text.is_empty() {
                json!({})
            } else {
                json!({"detail": detail(text)})
            };
            let mut n = note("open_rejected", "rejected", Some(code));
            n.detail = (!text.is_empty()).then(|| text.to_owned());
            Ok((state.clone(), small("rejected", code, body)?, n))
        };
    let body = match (&request["ack"], request["body"].as_object()) {
        (Value::Null, Some(body)) => body,
        _ => return reject("body_invalid", "open body"),
    };
    let keys_ok = ["application", "contract", "bound"]
        .iter()
        .all(|k| body.contains_key(*k))
        && body.keys().all(|k| {
            matches!(
                k.as_str(),
                "application" | "contract" | "bound" | "run" | "features"
            )
        });
    if !keys_ok {
        return reject("body_invalid", "open members");
    }
    let run_ok = match body.get("run") {
        None => true,
        Some(run) => run.as_str().is_some_and(|r| r.chars().count() <= MAX_RUN),
    };
    let empty = Value::Object(Map::new());
    let features = body.get("features").unwrap_or(&empty);
    let bound = body["bound"].as_u64();
    if !body["application"].is_string()
        || !is_identity(&body["contract"])
        || bound.is_none()
        || !run_ok
        || !valid_features(features)
    {
        return reject("body_invalid", "open member types");
    }
    let Some(index) = config.contracts.iter().position(|c| {
        body["application"] == c.application.as_str() && body["contract"] == c.identity.as_str()
    }) else {
        return reject("contract_mismatch", "");
    };
    let bound = bound.unwrap_or_default() as usize;
    if !(HANDSHAKE_BOUND..=MAX_BOUND).contains(&bound) {
        return reject("bound_unacceptable", "");
    }
    if state.stopping {
        return reject("refused", "the owner stops");
    }
    let contract = &config.contracts[index];
    let requested = features.as_object().cloned().unwrap_or_default();
    let run = body.get("run").and_then(Value::as_str);
    let info = OpenInfo {
        session: request["session"].as_str().unwrap_or_default(),
        contract,
        run,
        features: &requested,
    };
    let granted = match handler.open(&info) {
        Ok(granted) => granted,
        Err(Refused(text)) => return reject("refused", &text),
    };
    // Only features that the client asked for, each with parameters that are an object.
    let enabled: Map<String, Value> = granted
        .into_iter()
        .filter(|(name, params)| requested.contains_key(name) && params.is_object())
        .collect();
    let nonce = (config.nonce)();
    let effective = bound.min(config.max_bound);
    let message = json!({"ncp": PROTOCOL, "session": info.session, "seq": 0, "request": decoded.identity,
                         "outcome": "ok", "code": null,
                         "body": {"bound": effective, "application": contract.application,
                                  "contract": contract.identity, "implementation": config.implementation,
                                  "nonce": nonce, "features": enabled}});
    let response = Arc::new(
        frame::encode_with(&message, &[], config.key.as_ref(), None).map_err(FrameError::from)?,
    );
    let next = OwnerState {
        session: Some(info.session.to_owned()),
        bound: effective,
        high: 0,
        kept: Some(Kept {
            request: decoded.identity.clone(),
            identity: frame::identity(&response),
            response: response.clone(),
        }),
        ended: false,
        closed: false,
        stopping: false,
        contract: Some(index),
        run: run.map(str::to_owned),
        nonce: Some(nonce),
        features: enabled,
    };
    Ok((next, response, note("opened", "ok", None)))
}

/// The response of a server that cannot serve one more session: an `open` gets `rejected` with
/// `refused`, and any other request of a session that the server does not hold gets the
/// response of rule 7.3.3. Fails for a frame that is not a request.
pub fn refuse(
    config: &OwnerConfig,
    decoded: &Decoded,
    text: &str,
) -> Result<Arc<Vec<u8>>, FrameError> {
    struct Refusing(String);
    impl Handler for Refusing {
        fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
            Ok(())
        }
        fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
            Err("refused".into())
        }
        fn open(&mut self, _: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
            Err(Refused(self.0.clone()))
        }
    }
    let text = if text.is_empty() {
        "the owner serves its largest number of sessions"
    } else {
        text
    };
    let (_, response, _) = step(
        config,
        &OwnerState::default(),
        decoded,
        &mut Refusing(text.to_owned()),
    )?;
    Ok(response)
}

/// The owner of one session: the state machine of [`step`], its state, and an observer.
pub struct Owner<H: Handler> {
    config: OwnerConfig,
    state: OwnerState,
    handler: H,
    check_digests: bool,
    observer: Arc<dyn Observer>,
    finished: bool,
}

impl<H: Handler> fmt::Debug for Owner<H> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Owner")
            .field("config", &self.config)
            .field("state", &self.state)
            .finish_non_exhaustive()
    }
}

impl<H: Handler> Owner<H> {
    /// An owner of one session of `contract`.
    pub fn new(contract: Contract, handler: H) -> Owner<H> {
        Owner::with_contracts(vec![contract], handler).expect("one contract names one application")
    }

    /// An owner that accepts several contracts of one application, for example two versions
    /// during an upgrade (section 7.1, rule 4.2).
    pub fn with_contracts(contracts: Vec<Contract>, handler: H) -> Result<Owner<H>, FrameError> {
        Ok(Owner {
            config: OwnerConfig::new(contracts)?,
            state: OwnerState::default(),
            handler,
            check_digests: true,
            observer: default_observer(),
            finished: false,
        })
    }

    /// The largest session bound, from 65,536 to 67,108,864 (default 1 MiB).
    ///
    /// # Panics
    ///
    /// If the bound is outside that range.
    pub fn with_max_bound(mut self, max_bound: usize) -> Owner<H> {
        assert!(
            (HANDSHAKE_BOUND..=MAX_BOUND).contains(&max_bound),
            "max_bound"
        );
        self.config.max_bound = max_bound;
        self
    }

    /// Stop comparing each request's digest with its bytes. Use it only on a pipe pair or a Unix
    /// domain socket with no other program between the endpoints (spec section 3, rule 5), and
    /// never with a key. Response digests are always computed.
    ///
    /// # Panics
    ///
    /// If the owner has a key.
    pub fn without_digest_check(mut self) -> Owner<H> {
        assert!(
            self.config.key.is_none(),
            "an authenticated session always compares digests"
        );
        self.check_digests = false;
        self
    }

    /// Authenticate every frame with `key` (section 13.2).
    pub fn with_key(mut self, key: Key) -> Owner<H> {
        self.check_digests = true;
        self.config.key = Some(key);
        self
    }

    /// The source of each opening's nonce. Tests pass a fixed source.
    pub fn with_nonce(mut self, nonce: impl Fn() -> String + Send + Sync + 'static) -> Owner<H> {
        self.config.nonce = Arc::new(nonce);
        self
    }

    /// The observer of the owner's events.
    pub fn with_observer(mut self, observer: Arc<dyn Observer>) -> Owner<H> {
        self.observer = observer;
        self
    }

    /// Do not check requests against the contract's schemas.
    pub fn without_schema_check(mut self) -> Owner<H> {
        self.config.check_schemas = false;
        self
    }

    /// The configuration.
    pub fn config(&self) -> &OwnerConfig {
        &self.config
    }

    /// The state.
    pub fn state(&self) -> &OwnerState {
        &self.state
    }

    /// The bound that the binding must apply to the next request.
    pub fn bound(&self) -> usize {
        self.state.bound
    }

    /// The session that the owner holds, if any.
    pub fn session(&self) -> Option<&str> {
        self.state.session.as_deref()
    }

    /// Whether the session ended.
    pub fn ended(&self) -> bool {
        self.state.ended
    }

    /// Whether the session ended with an `ok` response to `close`.
    pub fn closed(&self) -> bool {
        self.state.closed
    }

    /// Whether the owner compares request digests.
    pub fn check_digests(&self) -> bool {
        self.check_digests
    }

    /// The key of an authenticated session, if any.
    pub fn key(&self) -> Option<&Key> {
        self.config.key.as_ref()
    }

    /// The application handler.
    pub fn handler(&mut self) -> &mut H {
        &mut self.handler
    }

    /// Decode one request frame with the session's bound, digest rule, and key.
    pub fn decode(&self, frame_bytes: Vec<u8>) -> Result<Decoded, FrameError> {
        let verify = match (&self.config.key, self.check_digests) {
            (Some(key), _) => Verify::Key(key),
            (None, true) => Verify::Digest,
            (None, false) => Verify::Trust,
        };
        frame::decode_verified(frame_bytes, self.state.bound, verify)
    }

    /// Handle one request frame and return the response frame. Fails only for a bad frame, which
    /// the binding handles (section 9).
    pub fn handle(&mut self, frame_bytes: Vec<u8>) -> Result<Arc<Vec<u8>>, FrameError> {
        let decoded = self.decode(frame_bytes)?;
        self.handle_decoded(&decoded)
    }

    /// Handle one decoded request frame and return the response frame.
    pub fn handle_decoded(&mut self, decoded: &Decoded) -> Result<Arc<Vec<u8>>, FrameError> {
        let (next, response, n) = step(&self.config, &self.state, decoded, &mut self.handler)?;
        self.state = next;
        let message = &decoded.message;
        self.observer.event(&Event {
            kind: n.kind,
            role: "owner",
            session: message["session"].as_str().map(str::to_owned),
            seq: message["seq"].as_u64(),
            op: message["op"].as_str().map(str::to_owned),
            outcome: n.outcome,
            code: n.code.map(str::to_owned),
            detail: n.detail,
            error: n.error,
        });
        Ok(response)
    }

    /// Stop admitting requests: every later request that the owner would admit gets `ended` with
    /// `shutdown`, and an `open` gets `rejected` with `refused` (rules 7.3.10 and 9.2.9).
    pub fn stop(&mut self) {
        self.state.stopping = true;
    }

    /// Tell the handler, once, that the session ended. A binding calls it when the connection
    /// ends; the reason is "closed" or "ended" when the session ended by the protocol.
    pub fn finish(&mut self, reason: &str) {
        if self.finished || self.state.session.is_none() {
            return;
        }
        self.finished = true;
        let reason = if self.state.closed {
            "closed"
        } else if self.state.ended {
            "ended"
        } else {
            reason
        };
        self.handler.close(reason);
    }
}
