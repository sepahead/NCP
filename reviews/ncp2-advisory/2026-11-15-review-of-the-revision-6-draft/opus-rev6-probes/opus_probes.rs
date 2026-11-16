//! Review probes (scratch only): candidate findings (a), (b), (e), (g), and lead L-A.
use ncp::client::{Channel, ChannelError, Client, Error};
use ncp::lockstep::{self, Lockstep, LockstepClient, Stepper};
use ncp::owner::{declined_with, AppError, Handler, Invalid, OpenInfo, Owner, Reply, Request};
use ncp::{frame, Contract};
use serde_json::{json, Map, Value};
use std::collections::VecDeque;
use std::sync::Arc;
use std::time::{Duration, Instant};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{},"move":{},"op":{}},"streams":{}}"#;

fn contract() -> Contract {
    Contract::from_bytes(CONTRACT.to_vec()).expect("contract")
}

#[derive(Debug)]
struct World {
    position: i64,
    sleep_ms: u64,
}

impl Handler for World {
    fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        std::thread::sleep(Duration::from_millis(self.sleep_ms));
        self.position += request.body["dx"].as_i64().unwrap_or(0);
        Ok(json!({"position": self.position}).into())
    }
}

impl Stepper for World {
    fn state(&self) -> Option<String> {
        Some(format!("p{}", self.position))
    }
}

/// An in-memory byte-stream-like channel. `run_then_cut`: the owner executes the next request,
/// but the response is lost and the connection breaks.
struct Mem<H: Handler> {
    owner: Owner<H>,
    inbox: VecDeque<Vec<u8>>,
    run_then_cut: bool,
    cut: bool,
}

impl<H: Handler> Channel for Mem<H> {
    fn lossy(&self) -> bool {
        false
    }
    fn send(&mut self, bytes: &[u8]) -> std::io::Result<()> {
        if self.cut {
            return Err(std::io::Error::other("broken"));
        }
        let response = self
            .owner
            .handle(bytes.to_vec())
            .map_err(std::io::Error::other)?;
        if self.run_then_cut {
            self.cut = true;
            return Ok(()); // the response is lost
        }
        self.inbox.push_back(response.to_vec());
        Ok(())
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        if self.cut {
            return Err(ChannelError::Closed(std::io::Error::other("closed")));
        }
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

fn session<H: Handler>(owner: Owner<H>) -> Client<Mem<H>> {
    let mut features = Map::new();
    features.insert(lockstep::FEATURE.into(), json!({}));
    Client::new(
        Mem {
            owner,
            inbox: VecDeque::new(),
            run_then_cut: false,
            cut: false,
        },
        &contract(),
    )
    .with_features(features)
    .with_observer(Arc::new(ncp::events::Silent))
}

fn world(ls: &Lockstep<World>) -> Owner<Lockstep<World>> {
    Owner::new(contract(), ls.share()).with_observer(Arc::new(ncp::events::Silent))
}

fn probe_la_recover_no_verdict_reads_as_not_executed() {
    println!("== L-A: a recovery without a verdict, after a step that RAN");
    let ls = Lockstep::new(World { position: 0, sleep_ms: 0 }, &["step"]);
    let mut stepper = LockstepClient::new(session(world(&ls))).expect("lockstep");
    stepper.step("step", json!({"dx": 2}), &[]).expect("step 1");
    stepper.client().channel_mut().run_then_cut = true; // step 2 runs; its response is lost
    let error = stepper.step("step", json!({"dx": 1}), &[]).expect_err("cut");
    println!("   step 2: {:?}, owner tick now {}", error.executed(), ls.clock().tick);
    // Another client takes the ticks and steps once.
    let mut other = LockstepClient::new(session(world(&ls))).expect("other");
    other.step("step", json!({"dx": 100}), &[]).expect("other step");
    let result = stepper.recover(session(world(&ls)));
    match &result {
        Err(e) => println!(
            "   recover -> Err({}), e.executed() = {:?}; step 2 actually ran: {}",
            match e {
                Error::Usage(t) => format!("Usage({t:.50})"),
                other => format!("{other:?}"),
            },
            e.executed(),
            ls.clock().tick >= 2
        ),
        Ok(v) => println!("   recover -> Ok({v:?})"),
    }
    println!(
        "   after Err: stepper.uncertain = {:?}; holder is the dropped recovery opening: {}",
        stepper.uncertain.as_ref().map(|u| u.0),
        ls.clock().holder.is_some() && ls.clock().holder != other.client().nonce().map(str::to_owned)
    );
    let again = stepper.step("step", json!({"dx": 1}), &[]);
    println!("   stepper.step after Err: {:?}", again.map(|_| ()).map_err(|e| format!("{e:?}")));
}

fn probe_la_step_ok_without_tick_reads_as_not_executed() {
    println!("== L-A: an ok step response without the tick (owner serves 'move' as a plain op)");
    let ls = Lockstep::new(World { position: 0, sleep_ms: 0 }, &["step"]);
    let mut stepper = LockstepClient::new(session(world(&ls))).expect("lockstep");
    let error = stepper
        .step("move", json!({"dx": 7}), &[])
        .expect_err("no tick");
    println!(
        "   step('move') -> {}; error.executed() = {:?}; application position now {}",
        match &error {
            Error::Usage(t) => format!("Usage({t})"),
            other => format!("{other:?}"),
        },
        error.executed(),
        ls.clock().tick // the tick did not move: 'move' is not a lockstep op
    );
}

fn probe_b_open_waits_for_running_step() {
    println!("== (b): does a Rust open wait for an executing step?");
    let ls = Lockstep::new(World { position: 0, sleep_ms: 600 }, &["step"]);
    let mut stepper = LockstepClient::new(session(world(&ls))).expect("lockstep");
    let handle = std::thread::spawn(move || {
        stepper.step("step", json!({"dx": 1}), &[]).expect("step");
    });
    std::thread::sleep(Duration::from_millis(100)); // the step is executing now
    let mut reader = ls.share();
    let contract = contract();
    let mut features = Map::new();
    features.insert(lockstep::FEATURE.into(), json!({}));
    let started = Instant::now();
    let report = reader
        .open(&OpenInfo {
            session: "s",
            contract: &contract,
            run: None,
            features: &features,
            nonce: "n9",
        })
        .expect("open")[lockstep::FEATURE]
        .clone();
    println!(
        "   open returned after {} ms with tick {}",
        started.elapsed().as_millis(),
        report["tick"]
    );
    handle.join().expect("join");
}

struct Decliner(Map<String, Value>);
impl Handler for Decliner {
    fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
        Err(declined_with("no", self.0.clone()))
    }
    fn execute(&mut self, _: &Request<'_>) -> Result<Reply, AppError> {
        Ok(json!({}).into())
    }
}

/// A channel that records what the owner's `handle` returned.
struct Rec<H: Handler> {
    owner: Owner<H>,
    inbox: VecDeque<Vec<u8>>,
    log: Vec<String>,
}

impl<H: Handler> Channel for Rec<H> {
    fn lossy(&self) -> bool {
        false
    }
    fn send(&mut self, bytes: &[u8]) -> std::io::Result<()> {
        match self.owner.handle(bytes.to_vec()) {
            Ok(response) => {
                self.log.push(format!(
                    "response of {} bytes (session bound {}), high={}",
                    response.len(),
                    self.owner.bound(),
                    self.owner.state().high
                ));
                self.inbox.push_back(response.to_vec());
                Ok(())
            }
            Err(e) => {
                self.log.push(format!(
                    "owner.handle -> Err(FrameError({})): the binding applies its bad-frame rule; high={}",
                    e.0,
                    self.owner.state().high
                ));
                Err(std::io::Error::other("bad frame"))
            }
        }
    }
    fn receive(&mut self, _bound: usize) -> Result<Vec<u8>, ChannelError> {
        self.inbox.pop_front().ok_or(ChannelError::Timeout)
    }
}

fn probe_a_declined_members() {
    println!("== (a): declined bodies with large or invalid ncp. members, Rust owner");
    for (label, value, bound) in [
        ("small (control)", json!(1), 1_048_576usize),
        ("2 MB string", json!("a".repeat(2_000_000)), 1_048_576),
        ("u64::MAX integer", json!(u64::MAX), 1_048_576),
        ("100 kB string, bound 65536", json!("a".repeat(100_000)), 65_536),
    ] {
        let mut members = Map::new();
        members.insert("ncp.x".into(), value);
        let owner = Owner::new(contract(), Decliner(members))
            .with_observer(Arc::new(ncp::events::Silent))
            .with_max_bound(bound);
        let mut client = Client::new(
            Rec {
                owner,
                inbox: VecDeque::new(),
                log: Vec::new(),
            },
            &contract(),
        )
        .with_observer(Arc::new(ncp::events::Silent));
        client.open().expect("open");
        let outcome = client.call("op", json!({}), &[]);
        let log = client.channel_mut().log.last().cloned().unwrap_or_default();
        println!(
            "   {label}: {log}\n      client: {}",
            match outcome {
                Ok(_) => "ok?!".to_owned(),
                Err(Error::Declined { code, .. }) => format!("Declined({code})"),
                Err(e) => format!("{e:?}").chars().take(110).collect(),
            }
        );
    }
}

fn probe_g_large_ticks() {
    println!("== (g): Lockstep::restored with ticks at the JSON limit and above");
    for tick in [(1u64 << 53) - 2, 1u64 << 60, u64::MAX] {
        let ls = Lockstep::restored(
            World { position: 0, sleep_ms: 0 },
            &["step"],
            tick,
            Some("s".into()),
            None,
            0,
        )
        .expect("restored accepts the tick");
        let mut client = session(world(&ls));
        match client.open() {
            Ok(_) => match LockstepClient::new(client) {
                Ok(mut stepper) => {
                    let first = stepper.step("step", json!({"dx": 1}), &[]);
                    let second = stepper.step("step", json!({"dx": 1}), &[]);
                    println!(
                        "   tick {tick}: step 1 {:?}; step 2 {:?}",
                        first.map(|_| ()).map_err(|e| format!("{e:?}")),
                        second.map(|_| ()).map_err(|e| format!("{e:?}"))
                    );
                }
                Err(e) => println!("   tick {tick}: take -> {e:?}"),
            },
            Err(e) => println!("   tick {tick}: open -> {e:?}"),
        }
    }
    // The overflow at `tick + 1` in validate, through the public Handler methods.
    let result = std::panic::catch_unwind(|| {
        let ls = Lockstep::restored(
            World { position: 0, sleep_ms: 0 },
            &["step"],
            u64::MAX,
            None,
            None,
            0,
        )
        .expect("restored");
        let mut h = ls.share();
        let c = contract();
        let mut features = Map::new();
        features.insert(lockstep::FEATURE.into(), json!({}));
        let decoded = frame::Decoded {
            message: json!({}),
            arrays: Vec::new(),
            identity: "t".into(),
            frame: Arc::new(Vec::new()),
        };
        let take_body = json!({"term": 0});
        let take = Request {
            op: lockstep::TAKE,
            body: &take_body,
            seq: 1,
            session: "s",
            identity: "t",
            contract: &c,
            run: None,
            features: &features,
            nonce: "n1",
            decoded: &decoded,
        };
        h.validate(&take).expect("take checked");
        h.execute(&take).expect("take runs");
        let step_body = json!({"dx": 1, "ncp.tick": {"tick": 0, "state": null}});
        let step = Request {
            op: "step",
            body: &step_body,
            identity: "r",
            ..take
        };
        let _ = h.validate(&step);
        let after = ls.share().clock(); // a poisoned mutex gives the default clock
        println!(
            "   after validate: clock tick {} term {}",
            after.tick, after.term
        );
    });
    println!(
        "   validate of a step at tick u64::MAX: {}",
        if result.is_err() { "PANICKED" } else { "no panic" }
    );
}

fn main() {
    probe_la_recover_no_verdict_reads_as_not_executed();
    probe_la_step_ok_without_tick_reads_as_not_executed();
    probe_b_open_waits_for_running_step();
    probe_a_declined_members();
    probe_g_large_ticks();
}
