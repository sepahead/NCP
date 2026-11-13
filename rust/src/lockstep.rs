//! The lockstep profile (spec/NCP-2-LOCKSTEP.md).
//!
//! Each step of a lockstep operation names the tick that it advances to and the state that it
//! answers. The owner keeps its tick and state across sessions. A client that lost a session,
//! with its last step possibly executed, opens a new session and learns from the `open` response
//! whether that step ran.

use crate::client::{Channel, Client, Error};
use crate::frame::{Array, Decoded};
use crate::messages::Executed;
use crate::owner::{declined, AppError, Handler, Invalid, OpenInfo, Refused, Reply, Request};
use serde_json::{json, Map, Value};
use std::sync::{Arc, Condvar, Mutex};

/// The feature name.
pub const FEATURE: &str = "ncp.lockstep";
/// The body member that carries the tick and the state.
pub const TICK: &str = "ncp.tick";
/// The longest state digest.
pub const MAX_STATE: usize = 128;

fn state_ok(value: &Value) -> bool {
    value.is_null()
        || value
            .as_str()
            .is_some_and(|s| (1..=MAX_STATE).contains(&s.chars().count()))
}

/// The application of a lockstep owner: an ordinary handler, and the digest of its state.
pub trait Stepper: Handler {
    /// A digest of the application's state after the last step: 1 to 128 characters, or None.
    fn state(&self) -> Option<String>;
}

/// The tick and the state of a lockstep owner, shared by all its sessions.
#[derive(Debug, Clone, Default)]
pub struct Clock {
    /// The last tick.
    pub tick: u64,
    /// The digest of the state after the last tick.
    pub state: Option<String>,
    /// The identity of the request whose step produced the last tick, if any.
    pub request: Option<String>,
    /// The session that holds the ticks: the last session that enabled the feature.
    pub holder: Option<String>,
    /// The identity of the step between its validation and its execution, if any.
    running: Option<String>,
}

/// A handler that applies the lockstep profile around an application.
///
/// One `Lockstep` serves one session; its application and clock are shared, so make each owner
/// of the application with [`Lockstep::share`] from the same [`Arc`].
#[derive(Debug)]
pub struct Lockstep<S: Stepper> {
    shared: Arc<(Mutex<(S, Clock)>, Condvar)>,
    ops: Vec<String>,
}

impl<S: Stepper> Lockstep<S> {
    /// A lockstep handler for the operations `ops` of `stepper`, from tick 0.
    pub fn new(stepper: S, ops: &[&str]) -> Lockstep<S> {
        Lockstep {
            shared: Arc::new((Mutex::new((stepper, Clock::default())), Condvar::new())),
            ops: ops.iter().map(|op| (*op).to_owned()).collect(),
        }
    }

    /// Another handler of the same application and clock, for another session.
    pub fn share(&self) -> Lockstep<S> {
        Lockstep {
            shared: self.shared.clone(),
            ops: self.ops.clone(),
        }
    }

    /// The tick and the state now.
    pub fn clock(&self) -> Clock {
        self.shared
            .0
            .lock()
            .map(|g| g.1.clone())
            .unwrap_or_default()
    }
}

impl<S: Stepper> Handler for Lockstep<S> {
    fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        let (mutex, idle) = &*self.shared;
        let mut guard = mutex.lock().map_err(|_| Refused("lock".into()))?;
        let mut granted = guard.0.open(info)?;
        if info.features.contains_key(FEATURE) {
            // The session takes over the ticks (profile, rule 5.2): wait until no checked step
            // is about to run, so that the tick read here is final for every earlier session,
            // whose later steps validate then declines.
            while guard.1.running.is_some() {
                guard = idle.wait(guard).map_err(|_| Refused("lock".into()))?;
            }
            guard.1.holder = Some(info.session.to_owned());
            granted.insert(
                FEATURE.to_owned(),
                json!({"tick": guard.1.tick, "state": guard.1.state, "request": guard.1.request}),
            );
        }
        Ok(granted)
    }

    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        let mut guard = self
            .shared
            .0
            .lock()
            .map_err(|_| Invalid::Failed("lock".into()))?;
        if !self.ops.iter().any(|op| op == request.op) {
            return guard.0.validate(request);
        }
        let member = &request.body[TICK];
        let valid_shape = member
            .as_object()
            .is_some_and(|m| m.len() == 2 && m.contains_key("tick") && m.contains_key("state"));
        if !valid_shape {
            return Err(declined(
                "a lockstep step needs the member \"ncp.tick\": {\"tick\": T, \"state\": S}",
            ));
        }
        if guard.1.holder.as_deref() != Some(request.session) {
            return Err(declined(
                "the session does not hold the ticks: it did not ask for ncp.lockstep, or a later session took them over",
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
        if guard.1.running.is_some() {
            return Err(declined("another step of this owner is running"));
        }
        guard.0.validate(request)?;
        // The owner executes a validated request at once; reserve the tick until then.
        guard.1.running = Some(request.identity.to_owned());
        Ok(())
    }

    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        let (mutex, idle) = &*self.shared;
        let mut guard = mutex.lock().map_err(|_| -> AppError { "lock".into() })?;
        if !self.ops.iter().any(|op| op == request.op) {
            return guard.0.execute(request);
        }
        // The lock stays held to the end of the step, so a waiting open sees the new tick.
        guard.1.running = None;
        idle.notify_all();
        // The step counts as executed from here, also if the application fails (profile, rule
        // 5.3): the tick advances, so that a recovery says that the step ran.
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

/// A client of a lockstep owner: it adds the tick and the state to each step, and it learns after
/// a lost session whether its last step ran.
#[derive(Debug)]
pub struct LockstepClient<C: Channel> {
    client: Client<C>,
    /// The last tick that the client knows.
    pub tick: u64,
    /// The state after it.
    pub state: Option<String>,
    /// The tick and the request identity of a step that is possibly executed.
    pub uncertain: Option<(u64, Option<String>)>,
}

/// The owner's tick, state, and the identity of the request that produced the tick.
type Granted = (u64, Option<String>, Option<String>);

fn granted<C: Channel>(client: &Client<C>) -> Result<Granted, Error> {
    let enabled = client.enabled();
    let granted = enabled.get(FEATURE).filter(|g| {
        g["tick"].is_u64()
            && state_ok(&g["state"])
            && (g["request"].is_null() || g["request"].is_string())
    });
    match granted {
        Some(g) => Ok((
            g["tick"].as_u64().unwrap_or_default(),
            g["state"].as_str().map(str::to_owned),
            g["request"].as_str().map(str::to_owned),
        )),
        None => Err(Error::Usage("the owner did not enable ncp.lockstep".into())),
    }
}

impl<C: Channel> LockstepClient<C> {
    /// Open `client`, which asks for the feature ([`Client::with_features`] with
    /// `{"ncp.lockstep": {}}`), and read the owner's tick and state.
    pub fn new(mut client: Client<C>) -> Result<LockstepClient<C>, Error> {
        if !client.opened() {
            client.open()?;
        }
        let (tick, state, _) = granted(&client)?;
        Ok(LockstepClient {
            client,
            tick,
            state,
            uncertain: None,
        })
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
                    return Err(Error::Usage(
                        "the result does not carry the next tick".into(),
                    ));
                }
                self.tick += 1;
                self.state = member["state"].as_str().map(str::to_owned);
                Ok(result)
            }
            Err(error) => {
                match &error {
                    Error::Ended {
                        executed: Executed::Unknown,
                        request,
                        ..
                    } => {
                        self.uncertain = Some((self.tick + 1, request.clone()));
                    }
                    Error::Ended {
                        executed: Executed::Yes,
                        ..
                    } => {
                        // result_too_large: the step ran; its new state is unknown here.
                        self.tick += 1;
                        self.state = None;
                    }
                    _ => {}
                }
                Err(error)
            }
        }
    }

    /// Continue with `client`, a new session to the same owner, after a step that is possibly
    /// executed. Returns Yes if that step ran and No if it did not and never will. Fails if the
    /// owner's tick is neither, for example because another client stepped it.
    pub fn recover(&mut self, mut client: Client<C>) -> Result<Executed, Error> {
        let Some((uncertain, request)) = self.uncertain.clone() else {
            return Err(Error::Usage("no step is possibly executed".into()));
        };
        if !client.opened() {
            client.open()?;
        }
        // The new session took over the ticks (profile, rule 5.2), so the step of the old
        // session that is possibly executed has run, with this identity, or never will.
        let (tick, state, last) = granted(&client)?;
        let verdict = if tick == uncertain && request.is_some() && last == request {
            Executed::Yes
        } else if tick + 1 == uncertain {
            Executed::No
        } else {
            return Err(Error::Usage(format!(
                "the owner is at tick {tick}; the uncertain step was tick {uncertain}"
            )));
        };
        self.client = client;
        self.tick = tick;
        self.state = state;
        self.uncertain = None;
        Ok(verdict)
    }
}
