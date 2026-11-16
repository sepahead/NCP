//! Probes of the advisory consult on revision 5 (scratch copy only; not part of the repository).
//! R1: one owner for each session identifier, as the Zenoh servers keep it (rule 9.2.7). A
//!     recovery with the same session identifier sends the same `open` frame and gets the kept
//!     `open` response: the same opening, no takeover.
//! R2: `recover` with a client that was opened before the uncertain step was sent.
//! R4: an owner that restarts at the same tick with another state.

use ncp::{
    AppError, Channel, ChannelError, Client, Contract, Executed, Handler, Invalid, Lockstep,
    LockstepClient, Owner, Reply, Request, Stepper,
};
use serde_json::{json, Map};
use std::cell::RefCell;
use std::collections::VecDeque;
use std::rc::Rc;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{}},"streams":{}}"#;
const SESSION: &str = "6f1c2e4a-9b3d-4c8e-a1f0-2d4b6c8e0a1b";

fn contract() -> Contract {
    Contract::from_bytes(CONTRACT.to_vec()).expect("contract")
}

struct World {
    position: i64,
}
impl Handler for World {
    fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        self.position += request.body["dx"].as_i64().unwrap_or(0);
        Ok(json!({"position": self.position}).into())
    }
}
impl Stepper for World {
    fn state(&self) -> Option<String> {
        Some(format!("p{}", self.position))
    }
}

type Shared = Rc<RefCell<Owner<Lockstep<World>>>>;

/// A lossy channel to an owner that several channels can share, as the worker of a Zenoh server.
struct Wire {
    owner: Shared,
    inbox: VecDeque<Vec<u8>>,
    frames: Vec<Vec<u8>>,
    hold: bool,
}
impl Channel for Wire {
    fn lossy(&self) -> bool {
        true
    }
    fn local(&self) -> bool {
        false
    }
    fn send(&mut self, frame: &[u8]) -> std::io::Result<()> {
        self.frames.push(frame.to_vec());
        if !self.hold {
            let response = self
                .owner
                .borrow_mut()
                .handle(frame.to_vec())
                .map_err(std::io::Error::other)?;
            self.inbox.push_back(response.to_vec());
        }
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

fn client(owner: &Shared, session: Option<&str>) -> Client<Wire> {
    let mut features = Map::new();
    features.insert(ncp::lockstep::FEATURE.into(), json!({}));
    let wire = Wire {
        owner: owner.clone(),
        inbox: VecDeque::new(),
        frames: Vec::new(),
        hold: false,
    };
    let client = Client::new(wire, &contract())
        .with_features(features)
        .with_retries(1);
    match session {
        Some(session) => client.with_session(session),
        None => client,
    }
}

#[test]
fn r1_one_owner_for_a_session_identifier_answers_the_recovery_open_with_its_kept_response() {
    let lockstep = Lockstep::new(World { position: 0 }, &["step"]);
    let worker: Shared = Rc::new(RefCell::new(Owner::new(contract(), lockstep.share())));
    let mut stepper = LockstepClient::new(client(&worker, Some(SESSION))).expect("lockstep");
    let first_nonce = stepper.client().nonce().map(str::to_owned);
    stepper.client().channel_mut().hold = true;
    let error = stepper
        .step("step", json!({"dx": 10}), &[])
        .expect_err("the first step is delayed");
    assert_eq!(error.executed(), Executed::Unknown);
    let delayed = stepper.client().channel_mut().frames.last().cloned().expect("s");

    // The recovery uses the same session identifier: the server routes it to the same owner.
    let mut fresh = client(&worker, Some(SESSION));
    fresh.open().expect("open");
    let same_opening = fresh.nonce().map(str::to_owned) == first_nonce;
    let verdict = stepper.recover(fresh).expect("recover");
    println!("R1 rust: verdict {verdict:?}; same nonce as the first opening: {same_opening}");

    let response = worker.borrow_mut().handle(delayed).expect("a response");
    let message = ncp::frame::decode(response.to_vec(), ncp::frame::MAX_BOUND)
        .expect("response")
        .message;
    println!(
        "R1 rust: delayed s -> {} | owner tick {}",
        message["outcome"],
        lockstep.clock().tick
    );
    // What the probe shows: the verdict was No, and the step then ran.
    assert!(same_opening);
    assert_eq!(verdict, Executed::No);
    assert_eq!(message["outcome"], "ok");
    assert_eq!(lockstep.clock().tick, 1);
}

#[test]
fn r2_recover_with_a_client_that_was_opened_before_the_step() {
    let lockstep = Lockstep::new(World { position: 0 }, &["step"]);
    let own = |l: &Lockstep<World>| -> Shared { Rc::new(RefCell::new(Owner::new(contract(), l.share()))) };
    let mut standby = client(&own(&lockstep), None);
    standby.open().expect("the standby opens first");
    let first = own(&lockstep);
    let mut stepper = LockstepClient::new(client(&first, None)).expect("lockstep");
    stepper.client().channel_mut().hold = true;
    stepper
        .step("step", json!({"dx": 10}), &[])
        .expect_err("delayed");
    let delayed = stepper.client().channel_mut().frames.last().cloned().expect("s");
    let verdict = stepper.recover(standby).expect("recover");
    let response = first.borrow_mut().handle(delayed).expect("a response");
    let message = ncp::frame::decode(response.to_vec(), ncp::frame::MAX_BOUND)
        .expect("response")
        .message;
    println!(
        "R2 rust: verdict {verdict:?}; delayed s -> {} | owner tick {}",
        message["outcome"],
        lockstep.clock().tick
    );
    assert_eq!(verdict, Executed::No);
    assert_eq!(message["outcome"], "ok");
}
