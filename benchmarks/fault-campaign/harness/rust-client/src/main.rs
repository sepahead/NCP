//! The Rust client of fault-campaign protocol 4 (../../PROTOCOL-4.md).
//!
//! fault-client CONNECT TIMEOUT_MS PLAN REPORT   one session, as harness/fault_client2.py runs it
//! fault-client victim CONNECT                   open a session, then call `echo` until killed
//!
//! CONNECT is `unix:PATH` or `tcp:HOST:PORT`. TIMEOUT_MS is the receive time limit. PLAN is a
//! JSON object with the optional members
//! `oversize_request_k` and `fail_k`. The session is open, six steps k = 1 to 6, and close.
//! REPORT receives one JSON object: the view of each step, the wrong results, the last step
//! sent, and the error that ended the session early, if any. The program prints "connected"
//! once it is connected; in victim mode, it prints "open" once the session is open.
use ncp::{Channel, Client, Contract, Decoded, Error, HANDSHAKE_BOUND};
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::time::{Duration, Instant};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}"#;
const STEPS: u64 = 6;

/// N spikes from the benchmark generator: senders 1 to 1000 (u32), times 0.1 to 10.0 ms (f64).
fn spikes(n: usize) -> (Vec<u32>, Vec<f64>) {
    let mut state = 0x2545_f491_4f6c_dd1d_u64;
    let (mut senders, mut times) = (Vec::with_capacity(n), Vec::with_capacity(n));
    for _ in 0..n {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        senders.push(((state >> 33) % 1000 + 1) as u32);
        times.push(((state >> 20) % 100) as f64 / 10.0 + 0.1);
    }
    (senders, times)
}

/// The operation and body of step k, as in harness/fault_client2.py.
fn step(k: u64) -> (&'static str, Value) {
    match k {
        2 | 6 => ("spikes", json!({"k": k, "n": 127})),
        4 => ("spikes", json!({"k": k, "n": 1788})),
        _ => (
            "echo",
            json!({"k": k, "v": [k, k * k], "s": format!("step {k}")}),
        ),
    }
}

/// Whether an accepted result is the right one for its request.
fn correct(op: &str, body: &Value, reply: &Decoded) -> bool {
    let result = &reply.message["body"];
    if op == "echo" {
        return result == body;
    }
    let n = body["n"].as_u64().unwrap_or(0) as usize;
    let (senders, times) = spikes(n);
    let index = |name: &str| {
        result[name]["ncp.array"]["att"]
            .as_u64()
            .map(|i| i as usize)
    };
    let (Some(s), Some(t)) = (index("senders"), index("times")) else {
        return false;
    };
    let got_times = reply.array_f64(t);
    reply.array_u32(s).as_deref() == Some(&senders[..])
        && got_times.is_some_and(|got| {
            got.len() == n
                && got
                    .iter()
                    .zip(&times)
                    .all(|(a, b)| a.to_bits() == b.to_bits())
        })
}

/// The name of the error that ended a session, as harness/fault_client2.py names the Python
/// SDK's exceptions; an error that the SDK does not document for a call is reported as such.
fn error_name(error: &Error) -> String {
    match error {
        Error::Rejected { .. } => "Rejected".into(),
        Error::Ended { .. } => "Ended".into(),
        Error::Protocol(_) => "ProtocolError".into(),
        other => format!("undocumented:{other:?}"),
    }
}

/// The view of a failed call.
fn view_of(error: &Error) -> String {
    match error {
        Error::Rejected { code, .. } => format!("rejected:{code}"),
        Error::Ended { code, executed } => format!("ended:{code}:{executed}"),
        Error::Protocol(_) => "protocol_error".into(),
        other => format!("undocumented:{other:?}"),
    }
}

struct Outcome {
    views: BTreeMap<i64, String>,
    wrong: u64,
    last_sent: Option<u64>,
    error: Option<String>,
}

fn run_session<C: Channel>(client: &mut Client<C>, plan: &Value) -> Outcome {
    let mut outcome = Outcome {
        views: BTreeMap::new(),
        wrong: 0,
        last_sent: None,
        error: None,
    };
    if let Err(error) = client.open() {
        outcome.error = Some(error_name(&error));
        return outcome;
    }
    for k in 1..=STEPS {
        if plan["oversize_request_k"].as_u64() == Some(k) {
            let blob = "y".repeat(70_000);
            let view = match client.call("echo", json!({"k": k, "blob": blob}), &[]) {
                Err(Error::Protocol(text)) if text.contains("exceeds the bound") => {
                    "refused_before_sending"
                }
                _ => "oversize_sent",
            };
            outcome.views.insert(-(k as i64), view.into());
        }
        let (mut op, mut body) = step(k);
        if plan["fail_k"].as_u64() == Some(k) {
            (op, body) = ("fail", json!({"k": k}));
        }
        outcome.last_sent = Some(k);
        match client.call(op, body.clone(), &[]) {
            Ok(reply) => {
                if correct(op, &body, &reply) {
                    outcome.views.insert(k as i64, "ok".into());
                } else {
                    outcome.views.insert(k as i64, "wrong".into());
                    outcome.wrong += 1;
                }
            }
            Err(error) => {
                outcome.views.insert(k as i64, view_of(&error));
                outcome.error = Some(error_name(&error));
                return outcome;
            }
        }
    }
    outcome.last_sent = None;
    match client.close() {
        Ok(()) => {
            outcome.views.insert(STEPS as i64 + 1, "closed".into());
        }
        Err(error) => outcome.error = Some(error_name(&error)),
    }
    outcome
}

/// Tell the driver that the connection stands, so that it can time a fault from then on.
fn announce(word: &str) {
    use std::io::Write;
    let mut stdout = std::io::stdout().lock();
    writeln!(stdout, "{word}").expect("stdout");
    stdout.flush().expect("stdout");
}

fn client_for<C: Channel>(channel: C, contract: &Contract) -> Client<C> {
    Client::new(channel, &contract.application, &contract.identity).with_bound(HANDSHAKE_BOUND)
}

fn session(connect: &str, timeout_ms: u64, plan: &Value) -> Outcome {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
    let limit = Some(Duration::from_millis(timeout_ms));
    if let Some(path) = connect.strip_prefix("unix:") {
        let channel = ncp::connect_unix(path).expect("connect");
        ncp::set_unix_timeout(&channel, limit).expect("time limit");
        announce("connected");
        return run_session(&mut client_for(channel, &contract), plan);
    }
    let address = connect
        .strip_prefix("tcp:")
        .expect("CONNECT is unix:PATH or tcp:HOST:PORT");
    let channel = ncp::connect_tcp(address, false).expect("connect");
    ncp::set_tcp_timeout(&channel, limit).expect("time limit");
    announce("connected");
    run_session(&mut client_for(channel, &contract), plan)
}

fn victim<C: Channel>(mut client: Client<C>) {
    client.open().expect("open");
    announce("open");
    for k in 1..u64::MAX {
        if client.call("echo", json!({"k": k}), &[]).is_err() {
            return;
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args[1] == "victim" {
        let connect = args[2].as_str();
        let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
        if let Some(path) = connect.strip_prefix("unix:") {
            victim(client_for(
                ncp::connect_unix(path).expect("connect"),
                &contract,
            ));
        } else {
            let address = connect.strip_prefix("tcp:").expect("tcp:HOST:PORT");
            victim(client_for(
                ncp::connect_tcp(address, false).expect("connect"),
                &contract,
            ));
        }
        return;
    }
    let (connect, timeout_ms, report) = (
        args[1].as_str(),
        args[2].parse::<u64>().expect("TIMEOUT_MS"),
        args[4].as_str(),
    );
    let plan: Value = serde_json::from_str(&args[3]).expect("PLAN");
    let started = Instant::now();
    let outcome = session(connect, timeout_ms, &plan);
    let views: Map<String, Value> = outcome
        .views
        .iter()
        .map(|(k, v)| (k.to_string(), Value::String(v.clone())))
        .collect();
    let text = json!({"views": views, "wrong_accepted": outcome.wrong, "last_sent": outcome.last_sent,
                      "error": outcome.error, "seconds": started.elapsed().as_secs_f64()});
    std::fs::write(report, format!("{text}\n")).expect("report");
}
