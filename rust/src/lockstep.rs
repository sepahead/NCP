//! The lockstep profile, revision 4 (spec/NCP-2-LOCKSTEP.md).
//!
//! Each step of a lockstep operation names the tick that it advances to and the state that it
//! answers. The owner keeps its tick, state, and term across sessions. One opening at a time
//! holds the ticks: the last one whose take (`ncp.lockstep.take`) succeeded. An `open` only
//! reports the tick. A client that lost a session, with its last step possibly executed, opens a
//! new session, takes the ticks, and learns from the response of the take whether that step ran.

use crate::client::{Channel, Client, Error};
use crate::frame::{Array, Decoded, MAX_INTEGER};
use crate::messages::{is_identity, Executed};
use crate::owner::{
    declined, declined_with, AppError, Handler, Invalid, OpenInfo, Refused, Reply, Request,
};
use serde_json::{json, Map, Value};
use std::sync::{Arc, Condvar, Mutex, PoisonError};

/// The feature name.
pub const FEATURE: &str = "ncp.lockstep";
/// The body member that carries the tick and the state.
pub const TICK: &str = "ncp.tick";
/// The feature operation that takes the ticks (profile, rules 5.2 and 5.3).
pub const TAKE: &str = "ncp.lockstep.take";
/// The longest state digest.
pub const MAX_STATE: usize = 128;
/// How many takes a client sends in one session before it gives up on a term that keeps moving.
pub const TAKE_ATTEMPTS: usize = 3;
/// The largest term: the largest integer that a JSON number carries exactly (profile, rule 5.2).
pub const MAX_TERM: u64 = MAX_INTEGER;
/// The largest tick, for the same reason (profile, rule 5.4).
pub const MAX_TICK: u64 = MAX_INTEGER;

fn state_ok(value: &Value) -> bool {
    value.is_null()
        || value
            .as_str()
            .is_some_and(|s| (1..=MAX_STATE).contains(&s.chars().count()))
}

fn term_of(value: &Value) -> Option<u64> {
    value.as_u64().filter(|term| *term <= MAX_TERM)
}

/// The application of a lockstep owner: an ordinary handler, and the digest of its state.
pub trait Stepper: Handler {
    /// A digest of the application's state after the last step: 1 to 128 characters, or None.
    fn state(&self) -> Option<String>;
}

/// The tick, the state, and the term of a lockstep owner, shared by all its sessions.
#[derive(Debug, Clone, Default)]
pub struct Clock {
    /// The last tick.
    pub tick: u64,
    /// The digest of the state after the last tick.
    pub state: Option<String>,
    /// The identity of the request whose step produced the last tick, if any.
    pub request: Option<String>,
    /// The number of takes since the owner started (profile, rule 5.3).
    pub term: u64,
    /// The nonce of the opening that holds the ticks: the opening whose take succeeded last. A
    /// session identifier does not name one opening: a copy of an old `open` opens the session
    /// again with another nonce (specification, rule 7.1.8).
    pub holder: Option<String>,
    /// The identity of the step or take between its validation and its execution, if any.
    running: Option<String>,
}

impl Clock {
    /// The report of rule 3.2, which is also the body of the response to a take (rule 5.3).
    fn report(&self) -> Value {
        json!({"tick": self.tick, "state": self.state, "request": self.request, "term": self.term})
    }
}

/// A handler that applies the lockstep profile around an application.
///
/// One `Lockstep` serves one session; its application and clock are shared, so make each owner
/// of the application with [`Lockstep::share`] from the same [`Arc`].
///
/// The application and the clock share one lock. While a step of the application runs, every
/// request of every session that reaches the application waits, and so do `open` and a report;
/// a step that was checked but does not run yet holds up only takes and other steps
/// (profile, rule 5.1).
///
/// Use `Lockstep` as the outermost handler of the owner. A successful `validate` of a take or a
/// step reserves the clock until `execute` runs; a handler around `Lockstep` that declines after
/// it leaves the reservation, and every later take and step waits.
#[derive(Debug)]
pub struct Lockstep<S: Stepper> {
    shared: Arc<(Mutex<(S, Clock)>, Condvar)>,
    ops: Vec<String>,
}

impl<S: Stepper> Lockstep<S> {
    /// A lockstep handler for the operations `ops` of `stepper`, from tick 0, with the
    /// application's digest of its state now (profile, rule 5.7).
    pub fn new(stepper: S, ops: &[&str]) -> Lockstep<S> {
        let state = stepper
            .state()
            .filter(|s| state_ok(&Value::from(s.as_str())));
        let clock = Clock {
            state,
            ..Clock::default()
        };
        Lockstep {
            shared: Arc::new((Mutex::new((stepper, clock)), Condvar::new())),
            ops: ops.iter().map(|op| (*op).to_owned()).collect(),
        }
    }

    /// A lockstep handler whose application restored a saved clock (profile, rule 5.7): the
    /// tick, the state digest, the identity of the request whose step produced the tick, and the
    /// term, 0 if the application saved none. No opening holds the ticks. Fails if the state
    /// digest does not have 1 to 128 characters, the request is not the identity of a request,
    /// or the tick or the term is larger than [`MAX_INTEGER`].
    pub fn restored(
        stepper: S,
        ops: &[&str],
        tick: u64,
        state: Option<String>,
        request: Option<String>,
        term: u64,
    ) -> Result<Lockstep<S>, Error> {
        if !state_ok(&state.clone().map_or(Value::Null, Value::from))
            || request
                .as_deref()
                .is_some_and(|r| !is_identity(&Value::from(r)))
            || tick > MAX_TICK
            || term > MAX_TERM
        {
            return Err(Error::Usage(
                "a state digest has 1 to 128 characters, a request is the identity of a request, \
                 and a tick and a term are at most 2^53 - 1"
                    .into(),
            ));
        }
        let clock = Clock {
            tick,
            state,
            request,
            term,
            ..Clock::default()
        };
        Ok(Lockstep {
            shared: Arc::new((Mutex::new((stepper, clock)), Condvar::new())),
            ops: ops.iter().map(|op| (*op).to_owned()).collect(),
        })
    }

    /// Another handler of the same application and clock, for another session.
    pub fn share(&self) -> Lockstep<S> {
        Lockstep {
            shared: self.shared.clone(),
            ops: self.ops.clone(),
        }
    }

    /// The tick, the state, the term, and the holder now.
    /// A copy of the clock. After a panic of the application, the clock is the one that the
    /// panic left, and every later request fails.
    pub fn clock(&self) -> Clock {
        let guard = self.shared.0.lock().unwrap_or_else(PoisonError::into_inner);
        guard.1.clone()
    }
}

impl<S: Stepper> Handler for Lockstep<S> {
    fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        // The application and the clock share one lock, and the application's own `open` runs
        // under it: an open waits while a step of the application runs, but not for a step that
        // was checked and has not started. Either way it reports the clock between two steps.
        let mut guard = self.shared.0.lock().map_err(|_| Refused("lock".into()))?;
        let mut granted = guard.0.open(info)?;
        if info.features.contains_key(FEATURE) {
            // A report from one instant (profile, rule 3.2). It changes nothing outside the
            // session, so that a copy of this `open` takes nothing (rule 3.3).
            granted.insert(FEATURE.to_owned(), guard.1.report());
        }
        Ok(granted)
    }

    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        let (mutex, idle) = &*self.shared;
        let mut guard = mutex.lock().map_err(|_| Invalid::Failed("lock".into()))?;
        if request.op == TAKE {
            let term = request
                .body
                .as_object()
                .filter(|body| body.len() == 1)
                .and_then(|body| body.get("term"))
                .and_then(term_of);
            let Some(term) = term else {
                return Err(declined("member: a take needs the body {\"term\": E}"));
            };
            // Wait until no checked step is still to run (rule 5.1), so that the clock is final.
            while guard.1.running.is_some() {
                guard = idle
                    .wait(guard)
                    .map_err(|_| Invalid::Failed("lock".into()))?;
            }
            // A term that moved: another take ran after the owner told the client the term
            // (rule 5.2). The response names the owner's term.
            if term != guard.1.term {
                let mut members = Map::new();
                members.insert(FEATURE.to_owned(), json!({"term": guard.1.term}));
                return Err(declined_with(
                    format!("term: the term is {}", guard.1.term),
                    members,
                ));
            }
            // The largest term, which no take can raise (rule 5.2).
            if guard.1.term >= MAX_TERM {
                return Err(declined(
                    "term: the term is the largest; no take can follow it",
                ));
            }
            // The owner executes a validated request at once; reserve the clock until then.
            guard.1.running = Some(request.identity.to_owned());
            return Ok(());
        }
        if request
            .op
            .strip_prefix(FEATURE)
            .is_some_and(|rest| rest.starts_with('.'))
        {
            return Err(declined(format!(
                "operation: the lockstep profile defines no operation {}; it defines {TAKE}",
                request.op
            )));
        }
        if !self.ops.iter().any(|op| op == request.op) {
            return guard.0.validate(request);
        }
        let member = &request.body[TICK];
        let valid_shape = member
            .as_object()
            .is_some_and(|m| m.len() == 2 && m.contains_key("tick") && m.contains_key("state"));
        if !valid_shape {
            return Err(declined(
                "member: a lockstep step needs \"ncp.tick\": {\"tick\": T, \"state\": S}",
            ));
        }
        // Wait until no checked step or take is still to run (rule 5.1), so that the checks below
        // see the clock and the holder that it leaves.
        while guard.1.running.is_some() {
            guard = idle
                .wait(guard)
                .map_err(|_| Invalid::Failed("lock".into()))?;
        }
        if guard.1.holder.as_deref() != Some(request.nonce) {
            // The term lets the client take the ticks again in this session (rule 6.4).
            let mut members = Map::new();
            members.insert(FEATURE.to_owned(), json!({"term": guard.1.term}));
            return Err(declined_with(
                "holder: this opening does not hold the ticks; send ncp.lockstep.take",
                members,
            ));
        }
        if guard.1.tick >= MAX_TICK {
            return Err(declined(
                "tick: the tick is the largest; no step can follow it",
            ));
        }
        if !member["tick"].is_u64() || member["tick"].as_u64() != Some(guard.1.tick + 1) {
            return Err(declined(format!(
                "tick: the next tick is {}",
                guard.1.tick + 1
            )));
        }
        let expected = guard.1.state.clone().map_or(Value::Null, Value::from);
        if member["state"] != expected {
            return Err(declined("state: the step answers another state"));
        }
        guard.0.validate(request)?;
        // The owner executes a validated request at once; reserve the tick until then.
        guard.1.running = Some(request.identity.to_owned());
        Ok(())
    }

    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        let (mutex, idle) = &*self.shared;
        let mut guard = mutex.lock().map_err(|_| -> AppError { "lock".into() })?;
        if request.op == TAKE {
            guard.1.running = None;
            idle.notify_all();
            // The take counts as executed: its opening holds the ticks, and the term moves on
            // (rule 5.3). The clock is final: no step of another opening can run any more.
            guard.1.holder = Some(request.nonce.to_owned());
            guard.1.term += 1;
            return Ok(guard.1.report().into());
        }
        if !self.ops.iter().any(|op| op == request.op) {
            return guard.0.execute(request);
        }
        // The lock stays held to the end of the step, so a waiting take sees the new tick.
        guard.1.running = None;
        idle.notify_all();
        // The step counts as executed from here, also if the application fails (profile, rule
        // 5.5): the tick advances, so that a recovery says that the step ran.
        let outcome = guard.0.execute(request);
        let state = guard.0.state();
        let valid = state_ok(&state.clone().map_or(Value::Null, Value::from));
        guard.1.tick += 1;
        guard.1.state = if valid { state.clone() } else { None };
        guard.1.request = Some(request.identity.to_owned());
        let mut reply = outcome?;
        if !valid {
            return Err("state() must return 1 to 128 characters or None".into());
        }
        let Value::Object(body) = &mut reply.body else {
            return Err("a lockstep result must be an object".into());
        };
        if body.contains_key(TICK) {
            return Err(format!("a lockstep result must not have {TICK}").into());
        }
        body.insert(
            TICK.to_owned(),
            json!({"tick": guard.1.tick, "state": state, "request": request.identity}),
        );
        Ok(reply)
    }

    fn close(&mut self, reason: &str) {
        if let Ok(mut guard) = self.shared.0.lock() {
            guard.0.close(reason);
        }
    }
}

/// What a client knows of the owner's clock: the tick, the state digest, and the identity of the
/// request whose step produced the tick.
pub type Known = (u64, Option<String>, Option<String>);

/// A client of a lockstep owner: it takes the ticks, adds the tick and the state to each step,
/// and learns after a lost session whether its last step ran.
#[derive(Debug)]
pub struct LockstepClient<C: Channel> {
    client: Client<C>,
    /// The last tick that the client knows.
    pub tick: u64,
    /// The state after it.
    pub state: Option<String>,
    /// The identity of the request whose step produced the tick, if the client knows one.
    pub request: Option<String>,
    /// The term that the owner told last in this session (profile, rule 4.1).
    pub term: u64,
    /// The tick and the request identity of a step that is possibly executed.
    pub uncertain: Option<(u64, Option<String>)>,
}

/// End the session of a client whose owner broke the profile, and describe the request that
/// executed.
fn broken<C: Channel>(
    client: &mut Client<C>,
    detail: &str,
    body: &Value,
    request: Option<String>,
) -> Error {
    let _ = client.close(); // the session ends either way
    Error::Ended {
        code: "local.protocol".into(),
        executed: Executed::Yes,
        detail: detail.into(),
        body: body.clone(),
        request,
    }
}

/// The term in the report of the `open` response (profile, rule 3.2). The report can be older
/// than the owner's clock by the time it arrives; only a take gives final values.
fn reported_term<C: Channel>(client: &Client<C>) -> Result<u64, Error> {
    let enabled = client.enabled();
    let term = enabled
        .get(FEATURE)
        .filter(|g| {
            g["tick"].is_u64()
                && state_ok(&g["state"])
                && (g["request"].is_null() || g["request"].is_string())
        })
        .and_then(|g| term_of(&g["term"]));
    term.ok_or_else(|| {
        Error::Usage("the owner did not enable ncp.lockstep (revision 4 of the profile)".into())
    })
}

/// Take the ticks for the opening of `client` (profile, rules 5.2 and 5.3). Returns the final
/// tick, state digest, and request identity, and the owner's new term.
///
/// `term` is the term that the owner told last in this session (rule 4.1), by default the term
/// of the `open` response. A take that is declined because the term moved is sent again with
/// the owner's term, at most [`TAKE_ATTEMPTS`] times in all; then, or if the term did not move,
/// take returns the last [`Error::Declined`]. If the `open` response does not enable the feature
/// with a term, take ends the session and fails (rule 3.4). If a take ran and its response does
/// not carry the clock, take ends the session and returns [`Error::Ended`] with the code
/// `local.protocol`: the take executed (rule 6.1).
pub fn take<C: Channel>(client: &mut Client<C>, term: Option<u64>) -> Result<(Known, u64), Error> {
    let told = match reported_term(client) {
        Ok(term) => term,
        Err(error) => {
            let _ = client.close(); // the session ends either way
            return Err(error);
        }
    };
    let mut term = match term {
        None => told,
        Some(term) if term <= MAX_TERM => term,
        Some(_) => {
            return Err(Error::Usage(format!(
                "a term is an integer from 0 to {MAX_TERM}"
            )))
        }
    };
    let mut attempt = 1;
    loop {
        match client.call(TAKE, json!({"term": term}), &[]) {
            Ok(result) => {
                let body = &result.message["body"];
                let valid = body["tick"].is_u64()
                    && state_ok(&body["state"])
                    && (body["request"].is_null() || body["request"].is_string())
                    && term_of(&body["term"]) == Some(term + 1);
                if !valid {
                    let request = result.message["request"].as_str().map(str::to_owned);
                    let detail = "the response of the take does not carry the clock";
                    return Err(broken(client, detail, body, request));
                }
                let known = (
                    body["tick"].as_u64().unwrap_or_default(),
                    body["state"].as_str().map(str::to_owned),
                    body["request"].as_str().map(str::to_owned),
                );
                return Ok((known, term + 1));
            }
            Err(Error::Declined { ref body, .. })
                if attempt < TAKE_ATTEMPTS
                    && term_of(&body[FEATURE]["term"]).is_some_and(|moved| moved != term) =>
            {
                term = term_of(&body[FEATURE]["term"]).unwrap_or_default();
                attempt += 1;
            }
            Err(error) => return Err(error),
        }
    }
}

/// The verdict of a recovery (profile, rule 6.5), from what the client knew before its uncertain
/// step (`known`: tick, state digest, request), the tick and request identity of that step
/// (`uncertain`), and the response of the take in the new opening (`taken`).
///
/// Yes if the take names the tick of the step and the identity of its request; No if it names
/// exactly what the client knew, so that the step did not run and never will; otherwise Unknown:
/// the owner's clock changed in another way, and the step stays possibly executed.
pub fn judge(known: &Known, uncertain: &(u64, Option<String>), taken: &Known) -> Executed {
    let (tick, identity) = uncertain;
    if taken.0 == *tick && identity.is_some() && taken.2 == *identity {
        return Executed::Yes;
    }
    if taken == known && known.0 + 1 == *tick {
        return Executed::No;
    }
    Executed::Unknown
}

impl<C: Channel> LockstepClient<C> {
    /// Open `client`, which asks for the feature ([`Client::with_features`] with
    /// `{"ncp.lockstep": {}}`), if it is not open yet, and take the ticks.
    pub fn new(mut client: Client<C>) -> Result<LockstepClient<C>, Error> {
        if !client.opened() {
            client.open()?;
        }
        let ((tick, state, request), term) = take(&mut client, None)?;
        Ok(LockstepClient {
            client,
            tick,
            state,
            request,
            term,
            uncertain: None,
        })
    }

    /// Take the ticks again in this session, with the term that the owner told last: for example
    /// after a step that was declined because another opening took them (profile, rule 6.4).
    pub fn take(&mut self) -> Result<(), Error> {
        if self.uncertain.is_some() {
            return Err(Error::Usage(
                "a step is possibly executed: recover with a new client".into(),
            ));
        }
        let ((tick, state, request), term) = take(&mut self.client, Some(self.term))?;
        (self.tick, self.state, self.request, self.term) = (tick, state, request, term);
        Ok(())
    }

    /// The client of the session.
    pub fn client(&mut self) -> &mut Client<C> {
        &mut self.client
    }

    /// Send one lockstep step. If the call ends with the step possibly executed, `uncertain`
    /// holds its tick and request identity; call `recover` with a new client.
    pub fn step(&mut self, op: &str, body: Value, arrays: &[Array]) -> Result<Decoded, Error> {
        let Value::Object(mut body) = body else {
            return Err(Error::Usage("a lockstep step's body is an object".into()));
        };
        if body.contains_key(TICK) {
            return Err(Error::Usage(format!("the client sets {TICK}")));
        }
        if self.tick >= MAX_TICK {
            return Err(Error::Usage(
                "the tick is the largest; no step can follow it".into(),
            ));
        }
        body.insert(
            TICK.to_owned(),
            json!({"tick": self.tick + 1, "state": self.state}),
        );
        match self.client.call(op, Value::Object(body), arrays) {
            Ok(result) => {
                let member = &result.message["body"][TICK];
                if member["tick"].as_u64() != Some(self.tick + 1)
                    || !state_ok(&member["state"])
                    || !member["request"].is_string()
                    || member["request"] != result.message["request"]
                {
                    // The step ran, but the owner broke the profile (rule 6.3): the clock is
                    // unknown, and the session ends.
                    self.tick += 1;
                    self.state = None;
                    self.request = result.message["request"].as_str().map(str::to_owned);
                    let detail = "the result does not carry the next tick";
                    let body = &result.message["body"];
                    return Err(broken(&mut self.client, detail, body, self.request.clone()));
                }
                self.tick += 1;
                self.state = member["state"].as_str().map(str::to_owned);
                self.request = member["request"].as_str().map(str::to_owned);
                Ok(result)
            }
            Err(error) => {
                match &error {
                    // The holder check names the owner's term: another opening took the ticks
                    // (rule 6.4).
                    Error::Declined { body, .. } => {
                        if let Some(term) = term_of(&body[FEATURE]["term"]) {
                            self.term = term;
                        }
                    }
                    Error::Ended {
                        executed: Executed::Unknown,
                        request,
                        ..
                    } => {
                        self.uncertain = Some((self.tick + 1, request.clone()));
                    }
                    Error::Ended {
                        executed: Executed::Yes,
                        request,
                        ..
                    } => {
                        // result_too_large: the step ran; its new state digest is unknown here.
                        self.tick += 1;
                        self.state = None;
                        self.request = request.clone();
                    }
                    _ => {}
                }
                Err(error)
            }
        }
    }

    /// Continue with `client`, a new session to the same owner, after a step that is possibly
    /// executed. Returns Yes if that step ran, and No if it did not and never will. Returns
    /// Unknown if the owner's clock changed in another way, for example because another client
    /// stepped it or the owner restarted with another state: the step stays possibly executed
    /// (rule 6.5).
    ///
    /// The opening of `client` takes the ticks (profile, rule 5.3), so a copy of the step that is
    /// still on its way can no longer run. The verdict comes from the response of the take,
    /// never from the `open` response, whose report can be older. With every verdict, the client
    /// goes on in the new session from the owner's clock.
    pub fn recover(&mut self, mut client: Client<C>) -> Result<Executed, Error> {
        let Some(uncertain) = self.uncertain.clone() else {
            return Err(Error::Usage("no step is possibly executed".into()));
        };
        if !client.opened() {
            client.open()?;
        }
        let (taken, term) = take(&mut client, None)?;
        let known = (self.tick, self.state.clone(), self.request.clone());
        let verdict = judge(&known, &uncertain, &taken);
        self.client = client;
        (self.tick, self.state, self.request) = taken;
        self.term = term;
        self.uncertain = None;
        Ok(verdict)
    }
}
