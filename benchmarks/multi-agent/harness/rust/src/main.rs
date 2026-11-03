//! The Rust programs of the multi-agent benchmark (see ../../PROTOCOL.md). One binary:
//!
//! multi owner WAIT_US                  NCP 2 echo owner on standard input and output; each echo
//!                                      first waits WAIT_US microseconds (a sleep)
//! multi raw-owner WAIT_US              the same without a protocol: a 4-byte little-endian length,
//!                                      then that many bytes, sent back after the wait
//! multi fanout N ROUNDS WARMUP MODE WAIT_US
//!                                      part F: one host, N owners (this binary), one round = one
//!                                      request to each owner; MODE is all (ncp::call_all), pool (one
//!                                      persistent thread per session), split (8 persistent threads,
//!                                      each with call_all on its share), sequential, or raw
//! multi agents N ROUNDS WARMUP PATH MODE
//!                                      part R: N agent threads, one session each, on the world
//!                                      owner at PATH; MODE is rounds or arrival
//! multi spikes PATH SPIKES CALLS WARMUP
//!                                      part M: one session on the rank-0 owner at PATH; checks
//!                                      every spike of every call
//!
//! Each run prints one JSON line. Times are in microseconds; a run fails on any wrong response.
use ncp::{Client, Contract, Decoded, Handler, Owner, Reply};
use serde_json::{json, Value};
use std::io::{BufReader, Read, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Barrier, Mutex};
use std::time::{Duration, Instant};

const ECHO: &[u8] =
    br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{}},"streams":{}}"#;
const WORLD: &[u8] =
    br#"{"ncp_contract":1,"application":"world","version":"1","operations":{"act":{}},"streams":{}}"#;
const SPIKES: &[u8] = br#"{"ncp_contract":1,"application":"spikes","version":"1","operations":{"spikes":{}},"streams":{}}"#;
const SPIKE_BOUND: usize = 4 << 20;
/// The threads of the `split` mode of part F: half of the 16 cores of the benchmark computer,
/// leaving the other half to the owners.
const SPLIT_THREADS: usize = 8;

fn contract(bytes: &[u8]) -> Contract {
    Contract::from_bytes(bytes.to_vec()).expect("contract")
}

/// Order statistics of a sample, as the other benchmarks of this repository compute them.
fn summary(mut times: Vec<f64>) -> Value {
    times.sort_by(f64::total_cmp);
    let pick = |q: f64| times[((times.len() - 1) as f64 * q).round() as usize];
    let mean = times.iter().sum::<f64>() / times.len() as f64;
    json!({"n": times.len(), "median_us": pick(0.5), "p05_us": pick(0.05), "p95_us": pick(0.95),
           "p99_us": pick(0.99), "mean_us": mean, "max_us": times[times.len() - 1]})
}

fn micros(since: Instant) -> f64 {
    since.elapsed().as_secs_f64() * 1e6
}

fn wait(wait_us: u64) {
    if wait_us > 0 {
        std::thread::sleep(Duration::from_micros(wait_us));
    }
}

struct WaitingEcho {
    wait_us: u64,
}

impl Handler for WaitingEcho {
    fn validate(&mut self, _op: &str, _request: &Decoded) -> Result<(), String> {
        Ok(())
    }
    fn execute(
        &mut self,
        _op: &str,
        request: &Decoded,
    ) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        wait(self.wait_us);
        Ok(request.message["body"].clone().into())
    }
}

fn owner(wait_us: u64) {
    let echo = contract(ECHO);
    let mut owner = Owner::new(
        &echo.application,
        &echo.identity,
        WaitingEcho { wait_us },
        echo.operations.clone(),
        ncp::DEFAULT_BOUND,
    );
    ncp::serve_stdio(&mut owner).expect("serve");
}

fn raw_owner(wait_us: u64) {
    let mut input = BufReader::with_capacity(1 << 16, std::io::stdin().lock());
    let mut output = std::io::stdout().lock();
    let mut message = Vec::new();
    loop {
        let mut header = [0u8; 4];
        if input.read_exact(&mut header).is_err() {
            return; // the host closed the pipe
        }
        let length = u32::from_le_bytes(header) as usize;
        message.clear();
        message.extend_from_slice(&header);
        message.resize(4 + length, 0);
        input.read_exact(&mut message[4..]).expect("message");
        wait(wait_us);
        output.write_all(&message).expect("write");
        output.flush().expect("flush");
    }
}

fn body(round: usize, agent: usize) -> Value {
    json!({"round": round, "agent": agent})
}

fn spawn_self(role: &str, wait_us: u64) -> Command {
    let mut command = Command::new(std::env::current_exe().expect("own path"));
    command.args([role, &wait_us.to_string()]);
    command
}

/// One host and N owners. Returns the time of each round, warm-up included.
fn fanout(args: &[String]) {
    let n: usize = args[2].parse().expect("N");
    let rounds: usize = args[3].parse().expect("ROUNDS");
    let warmup: usize = args[4].parse().expect("WARMUP");
    let mode = args[5].as_str();
    let wait_us: u64 = args[6].parse().expect("WAIT_US");
    let total = warmup + rounds;
    let times = match mode {
        "raw" => fanout_raw(n, total, wait_us),
        "pool" => fanout_threads(n, total, wait_us, n),
        "split" => fanout_threads(n, total, wait_us, n.min(SPLIT_THREADS)),
        "all" | "sequential" => fanout_ncp(n, total, wait_us, mode == "all"),
        other => panic!("unknown mode {other}"),
    };
    println!(
        "{}",
        json!({"part": "F", "host": "rust", "mode": mode, "n": n, "wait_us": wait_us,
               "rounds": rounds, "warmup": warmup, "round": summary(times[warmup..].to_vec())})
    );
}

fn open_owners(n: usize, wait_us: u64) -> (Vec<Client<ncp::binding::ChildChannel>>, Vec<Child>) {
    let echo = contract(ECHO);
    let mut clients = Vec::with_capacity(n);
    let mut children = Vec::with_capacity(n);
    for _ in 0..n {
        let (channel, child) = ncp::spawn(spawn_self("owner", wait_us)).expect("spawn owner");
        let mut client = Client::new(channel, &echo.application, &echo.identity);
        client.open().expect("open");
        clients.push(client);
        children.push(child);
    }
    (clients, children)
}

fn close_owners(clients: &mut [Client<ncp::binding::ChildChannel>], children: Vec<Child>) {
    for client in clients.iter_mut() {
        client.close().expect("close");
    }
    for mut child in children {
        assert!(child.wait().expect("owner exit").success(), "owner failed");
    }
}

fn fanout_ncp(n: usize, total: usize, wait_us: u64, all: bool) -> Vec<f64> {
    let (mut clients, children) = open_owners(n, wait_us);
    let mut times = Vec::with_capacity(total);
    for round in 0..total {
        let bodies: Vec<Value> = (0..n).map(|agent| body(round, agent)).collect();
        let started = Instant::now();
        let replies: Vec<_> = if all {
            ncp::call_all(&mut clients, "echo", bodies.clone())
        } else {
            clients
                .iter_mut()
                .zip(bodies.iter().cloned())
                .map(|(client, body)| client.call("echo", body, &[]))
                .collect()
        };
        times.push(micros(started));
        for (reply, expected) in replies.into_iter().zip(&bodies) {
            assert_eq!(
                &reply.expect("call").message["body"],
                expected,
                "wrong response"
            );
        }
    }
    close_owners(&mut clients, children);
    times
}

/// Threads that last the whole run: `threads` of them, each with a contiguous share of the
/// sessions. A thread with one session calls it; a thread with more uses `call_all` on its share.
fn fanout_threads(n: usize, total: usize, wait_us: u64, threads: usize) -> Vec<f64> {
    let (mut clients, children) = open_owners(n, wait_us);
    let start = Arc::new(Barrier::new(threads + 1));
    let end = Arc::new(Barrier::new(threads + 1));
    let round = Arc::new(AtomicUsize::new(0));
    let stop = Arc::new(AtomicBool::new(false));
    let mut shares = Vec::with_capacity(threads);
    for j in (0..threads).rev() {
        let first = j * n / threads;
        shares.push((
            (first..clients.len()).collect::<Vec<usize>>(),
            clients.split_off(first),
        ));
    }
    let workers: Vec<_> = shares
        .into_iter()
        .map(|(agents, mut share)| {
            let (start, end, round, stop) =
                (start.clone(), end.clone(), round.clone(), stop.clone());
            std::thread::spawn(move || {
                loop {
                    start.wait();
                    if stop.load(Ordering::SeqCst) {
                        break;
                    }
                    let r = round.load(Ordering::SeqCst);
                    let expected: Vec<Value> = agents.iter().map(|agent| body(r, *agent)).collect();
                    let replies = if share.len() == 1 {
                        vec![share[0].call("echo", expected[0].clone(), &[])]
                    } else {
                        ncp::call_all(&mut share, "echo", expected.clone())
                    };
                    end.wait();
                    // Checked after the round, as in the other modes.
                    for (reply, expected) in replies.into_iter().zip(&expected) {
                        assert_eq!(
                            &reply.expect("call").message["body"],
                            expected,
                            "wrong response"
                        );
                    }
                }
                for client in share.iter_mut() {
                    client.close().expect("close");
                }
            })
        })
        .collect();
    let mut times = Vec::with_capacity(total);
    for r in 0..total {
        round.store(r, Ordering::SeqCst);
        let started = Instant::now();
        start.wait();
        end.wait();
        times.push(micros(started));
    }
    stop.store(true, Ordering::SeqCst);
    start.wait();
    for worker in workers {
        worker.join().expect("worker");
    }
    for mut child in children {
        assert!(child.wait().expect("owner exit").success(), "owner failed");
    }
    times
}

fn fanout_raw(n: usize, total: usize, wait_us: u64) -> Vec<f64> {
    let mut children: Vec<Child> = Vec::with_capacity(n);
    let mut pipes: Vec<(ChildStdin, BufReader<ChildStdout>)> = Vec::with_capacity(n);
    for _ in 0..n {
        let mut child = spawn_self("raw-owner", wait_us)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()
            .expect("spawn raw owner");
        let input = child.stdin.take().expect("stdin");
        let output = BufReader::with_capacity(1 << 16, child.stdout.take().expect("stdout"));
        pipes.push((input, output));
        children.push(child);
    }
    let mut times = Vec::with_capacity(total);
    let mut received: Vec<Vec<u8>> = vec![Vec::new(); n];
    for round in 0..total {
        let messages: Vec<Vec<u8>> = (0..n)
            .map(|agent| {
                let payload = serde_json::to_vec(&body(round, agent)).expect("json");
                let mut message = (payload.len() as u32).to_le_bytes().to_vec();
                message.extend_from_slice(&payload);
                message
            })
            .collect();
        let started = Instant::now();
        for ((input, _), message) in pipes.iter_mut().zip(&messages) {
            input.write_all(message).expect("write");
        }
        for ((_, output), (message, buffer)) in
            pipes.iter_mut().zip(messages.iter().zip(&mut received))
        {
            buffer.resize(message.len(), 0);
            output.read_exact(buffer).expect("read");
        }
        times.push(micros(started));
        assert!(received == messages, "wrong response"); // checked after the round, as in the other modes
    }
    drop(pipes);
    for mut child in children {
        assert!(
            child.wait().expect("raw owner exit").success(),
            "raw owner failed"
        );
    }
    times
}

fn hex_bytes(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).expect("hex"))
        .collect()
}

/// Check the record of a rounds response (spec/NCP-2-ROUNDS.md, client rule 1).
fn check_record(reply: &Decoded, name: &str, round: usize) -> bool {
    let record = &reply.message["body"]["ncp.round_record"];
    let Some(agents) = record["agents"].as_array() else {
        return false;
    };
    let Some(row) = agents.iter().position(|agent| agent == name) else {
        return false;
    };
    let array = &record["requests"]["ncp.array"];
    let index = array["att"].as_u64().unwrap_or(u64::MAX) as usize;
    let Some(bytes) = reply.array_bytes(index) else {
        return false;
    };
    let request = reply.message["request"].as_str().unwrap_or("");
    record["round"] == round
        && array["dtype"] == "u8"
        && array["shape"] == json!([agents.len(), 32])
        && bytes.len() == 32 * agents.len()
        && bytes[32 * row..32 * row + 32] == hex_bytes(request)[..]
}

/// N agents in lockstep on the world owner. Agent 0 measures the time of each round, from the
/// barrier that starts it to the barrier that starts the next one.
fn agents(args: &[String]) {
    let n: usize = args[2].parse().expect("N");
    let rounds: usize = args[3].parse().expect("ROUNDS");
    let warmup: usize = args[4].parse().expect("WARMUP");
    let path = args[5].clone();
    let mode = args[6].clone();
    assert!(mode == "rounds" || mode == "arrival", "unknown mode {mode}");
    let total = warmup + rounds;
    let world = contract(WORLD);
    let barrier = Arc::new(Barrier::new(n));
    let states: Arc<Mutex<Vec<Vec<String>>>> = Arc::new(Mutex::new(vec![Vec::new(); n]));
    // The sessions open one after another, before the timed rounds.
    let clients: Vec<_> = (0..n)
        .map(|_| {
            let channel = ncp::connect_unix(&path).expect("connect");
            let mut client = Client::new(channel, &world.application, &world.identity);
            client.open().expect("open");
            client
        })
        .collect();
    let handles: Vec<_> = clients
        .into_iter()
        .enumerate()
        .map(|(agent, mut client)| {
            let (barrier, states, mode) = (barrier.clone(), states.clone(), mode.clone());
            std::thread::spawn(move || {
                let name = format!("agent-{agent:03}");
                let mut marks = Vec::with_capacity(total + 1);
                let mut seen = Vec::with_capacity(total);
                let mut checked = 0usize;
                for round in 1..=total {
                    barrier.wait();
                    marks.push(Instant::now());
                    let action = json!([agent, round]);
                    let request = if mode == "rounds" {
                        json!({"ncp.round": {"agent": name, "round": round}, "action": action})
                    } else {
                        json!({"agent": name, "round": round, "action": action})
                    };
                    let reply = client.call("act", request, &[]).expect("call");
                    if mode == "rounds" {
                        assert!(check_record(&reply, &name, round), "bad round record");
                        checked += 1;
                    }
                    seen.push(
                        reply.message["body"]["state"]
                            .as_str()
                            .expect("state")
                            .to_owned(),
                    );
                }
                barrier.wait();
                marks.push(Instant::now());
                client.close().expect("close");
                states.lock().expect("states")[agent] = seen;
                (marks, checked)
            })
        })
        .collect();
    let results: Vec<_> = handles
        .into_iter()
        .map(|h| h.join().expect("agent"))
        .collect();
    let marks = &results[0].0;
    let times: Vec<f64> = marks
        .windows(2)
        .map(|w| (w[1] - w[0]).as_secs_f64() * 1e6)
        .collect();
    let states = states.lock().expect("states");
    let agree = (0..total).all(|round| states.iter().all(|s| s[round] == states[0][round]));
    let checked: usize = results.iter().map(|r| r.1).sum();
    println!(
        "{}",
        json!({"part": "R", "mode": mode, "n": n, "rounds": rounds, "warmup": warmup,
               "round": summary(times[warmup..].to_vec()), "records_checked": checked,
               "states_agree": agree, "last_state_agent_0": states[0][total - 1]})
    );
}

/// The spikes that the rank-0 owner returns: spike i of a call came from sender i mod 1000 + 1,
/// at time (i mod 100) / 10 + 0.1 ms, whichever rank made it.
fn expected_spikes(n: usize) -> (Vec<u32>, Vec<f64>) {
    (
        (0..n).map(|i| (i % 1000) as u32 + 1).collect(),
        (0..n).map(|i| (i % 100) as f64 / 10.0 + 0.1).collect(),
    )
}

fn spikes(args: &[String]) {
    let path = &args[2];
    let n: usize = args[3].parse().expect("SPIKES");
    let calls: usize = args[4].parse().expect("CALLS");
    let warmup: usize = args[5].parse().expect("WARMUP");
    let spikes = contract(SPIKES);
    let channel = ncp::connect_unix(path).expect("connect");
    let mut client =
        Client::new(channel, &spikes.application, &spikes.identity).with_bound(SPIKE_BOUND);
    client.open().expect("open");
    let (senders, times_ms) = expected_spikes(n);
    let mut times = Vec::with_capacity(calls);
    for call in 0..warmup + calls {
        let started = Instant::now();
        let reply = client.call("spikes", json!({"n": n}), &[]).expect("call");
        let elapsed = micros(started);
        let body = &reply.message["body"];
        let index = |name: &str| body[name]["ncp.array"]["att"].as_u64().expect("array") as usize;
        assert_eq!(
            reply.array_u32(index("senders")).as_ref(),
            Some(&senders),
            "wrong senders"
        );
        let got = reply.array_f64(index("times")).expect("times");
        assert!(
            got.len() == n
                && got
                    .iter()
                    .zip(&times_ms)
                    .all(|(a, b)| a.to_bits() == b.to_bits()),
            "wrong times"
        );
        if call >= warmup {
            times.push(elapsed);
        }
    }
    client.close().expect("close");
    println!(
        "{}",
        json!({"part": "M", "spikes": n, "calls": calls, "warmup": warmup, "call": summary(times),
               "spikes_checked": n * (warmup + calls)})
    );
}

fn main() {
    // A failed thread ends the program: the other threads would otherwise wait at a barrier.
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        default_hook(info);
        std::process::exit(101);
    }));
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("owner") => owner(args[2].parse().expect("WAIT_US")),
        Some("raw-owner") => raw_owner(args[2].parse().expect("WAIT_US")),
        Some("fanout") => fanout(&args),
        Some("agents") => agents(&args),
        Some("spikes") => spikes(&args),
        _ => {
            eprintln!("usage: see the comment at the top of main.rs");
            std::process::exit(2);
        }
    }
}
