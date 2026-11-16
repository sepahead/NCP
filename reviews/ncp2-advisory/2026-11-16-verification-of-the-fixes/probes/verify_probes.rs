//! Probes of the revision 6 fixes, Rust SDK (advisory; certifies nothing).
//! Copy to SNAP/rust/examples/ and run with
//! `CARGO_TARGET_DIR=... cargo run --offline --locked --example verify_probes`.

use ncp::frame::MAX_BOUND;
use ncp::{
    AppError, Channel, ChannelError, Client, Contract, Error, Handler, Invalid, Lockstep,
    LockstepClient, OpenInfo, Owner, Refused, Reply, Request, Stepper,
};
use serde_json::{json, Map, Value};
use std::collections::VecDeque;
use std::sync::{Arc, Mutex};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"big":{}},"streams":{"sensor":{}}}"#;

fn contract() -> Contract {
    Contract::from_bytes(CONTRACT.to_vec()).expect("contract")
}

struct World {
    position: i64,
    digest: Option<String>,
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
        self.digest
            .clone()
            .or_else(|| Some(format!("p{}", self.position)))
    }
}

struct Memory<H: Handler> {
    owner: Owner<H>,
    inbox: VecDeque<Vec<u8>>,
    frames: Arc<Mutex<Vec<Vec<u8>>>>,
}

impl<H: Handler> Channel for Memory<H> {
    fn lossy(&self) -> bool {
        false
    }
    fn local(&self) -> bool {
        true
    }
    fn send(&mut self, frame_bytes: &[u8]) -> std::io::Result<()> {
        self.frames.lock().unwrap().push(frame_bytes.to_vec());
        let response = self
            .owner
            .handle(frame_bytes.to_vec())
            .map_err(std::io::Error::other)?;
        self.inbox.push_back(response.to_vec());
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

fn features() -> Map<String, Value> {
    let mut f = Map::new();
    f.insert(ncp::lockstep::FEATURE.into(), json!({}));
    f
}

fn client_of<H: Handler>(handler: H, frames: Arc<Mutex<Vec<Vec<u8>>>>) -> Client<Memory<H>> {
    Client::new(
        Memory {
            owner: Owner::new(contract(), handler),
            inbox: VecDeque::new(),
            frames,
        },
        &contract(),
    )
    .with_features(features())
}

/// A lockstep owner whose results the probe alters.
struct Altered {
    inner: Lockstep<World>,
    alter: fn(&str, &mut Value),
    bump: Arc<Mutex<usize>>,
    bumper: Option<Lockstep<World>>,
}

impl Handler for Altered {
    fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        self.inner.open(info)
    }
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        // Another client takes the ticks before this take, `bump` times.
        if request.op == ncp::lockstep::TAKE {
            let mut bump = self.bump.lock().unwrap();
            if *bump > 0 {
                *bump -= 1;
                if let Some(other) = &mut self.bumper {
                    let term = other.clock().term;
                    let mut c = Client::new(
                        Memory {
                            owner: Owner::new(contract(), other.share()),
                            inbox: VecDeque::new(),
                            frames: Arc::new(Mutex::new(Vec::new())),
                        },
                        &contract(),
                    )
                    .with_features(features());
                    c.open().expect("open");
                    let _ = ncp::lockstep::take(&mut c, Some(term));
                }
            }
        }
        self.inner.validate(request)
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        let mut reply = self.inner.execute(request)?;
        (self.alter)(request.op, &mut reply.body);
        Ok(reply)
    }
}

fn terms_named(frames: &Arc<Mutex<Vec<Vec<u8>>>>) -> Vec<Value> {
    frames
        .lock()
        .unwrap()
        .iter()
        .filter_map(|f| ncp::frame::decode(f.clone(), MAX_BOUND).ok())
        .filter(|d| d.message["op"] == ncp::lockstep::TAKE)
        .map(|d| d.message["body"]["term"].clone())
        .collect()
}

fn main() {
    println!("== R1: the ok response of a take lacks 'state' and 'request'");
    let lockstep = Lockstep::new(World { position: 0, digest: None }, &["echo"]);
    let altered = Altered {
        inner: lockstep.share(),
        alter: |op, body| {
            if op == ncp::lockstep::TAKE {
                let o = body.as_object_mut().unwrap();
                o.remove("state");
                o.remove("request");
            }
        },
        bump: Arc::new(Mutex::new(0)),
        bumper: None,
    };
    match LockstepClient::new(client_of(altered, Arc::new(Mutex::new(Vec::new())))) {
        Ok(s) => println!(
            "  accepted: tick {} state {:?} request {:?} term {} (owner state {:?})",
            s.tick,
            s.state,
            s.request,
            s.term,
            lockstep.clock().state
        ),
        Err(e) => println!("  error {e:?} executed {:?}", e.executed()),
    }

    println!("== R2: the ok response of a step has ncp.tick without 'state'");
    let lockstep = Lockstep::new(World { position: 0, digest: None }, &["echo"]);
    let altered = Altered {
        inner: lockstep.share(),
        alter: |op, body| {
            if op == "echo" {
                body[ncp::lockstep::TICK].as_object_mut().unwrap().remove("state");
            }
        },
        bump: Arc::new(Mutex::new(0)),
        bumper: None,
    };
    let mut s = LockstepClient::new(client_of(altered, Arc::new(Mutex::new(Vec::new())))).unwrap();
    match s.step("echo", json!({"dx": 2}), &[]) {
        Ok(_) => println!(
            "  accepted: client tick {} state {:?}; owner tick {} state {:?}",
            s.tick,
            s.state,
            lockstep.clock().tick,
            lockstep.clock().state
        ),
        Err(e) => println!("  error {e:?}"),
    }
    match s.step("echo", json!({"dx": 1}), &[]) {
        Ok(_) => println!("  next step ok"),
        Err(e) => println!("  next step: {e:?} executed {:?}", e.executed()),
    }

    println!("== R3: LockstepClient::take() after three declined takes names a stale term");
    let lockstep = Lockstep::new(World { position: 0, digest: None }, &["echo"]);
    let bump = Arc::new(Mutex::new(0));
    let altered = Altered {
        inner: lockstep.share(),
        alter: |_, _| {},
        bump: bump.clone(),
        bumper: Some(lockstep.share()),
    };
    let frames = Arc::new(Mutex::new(Vec::new()));
    let mut s = LockstepClient::new(client_of(altered, frames.clone())).unwrap(); // term 1
    *bump.lock().unwrap() = 3;
    match s.take() {
        Ok(()) => println!("  take ok"),
        Err(e) => println!("  take(): {e:?}"),
    }
    println!(
        "  owner term {}; stepper.term {}; terms named {:?}",
        lockstep.clock().term,
        s.term,
        terms_named(&frames)
    );
    frames.lock().unwrap().clear();
    match s.take() {
        Ok(()) => println!("  second take() ok"),
        Err(e) => println!("  second take(): {e:?}"),
    }
    println!(
        "  terms named by the second take(): {:?}; owner term now {}",
        terms_named(&frames),
        lockstep.clock().term
    );

    println!("== R4: Lockstep::new with an application digest of 200 characters");
    let lockstep = Lockstep::new(
        World {
            position: 0,
            digest: Some("x".repeat(200)),
        },
        &["echo"],
    );
    println!("  accepted; the initial S is {:?}", lockstep.clock().state);
}
