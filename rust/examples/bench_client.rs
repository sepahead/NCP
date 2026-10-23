//! Time lockstep calls to an owner:
//! bench_client CALLS WARMUP SPIKES [--no-digest-check] -- OWNER COMMAND...    (pipes to a child owner)
//! bench_client CALLS WARMUP SPIKES [--no-digest-check] --connect unix:PATH|tcp:ADDR
//!
//! Each call sends a small `spikes` request and gets SPIKES spikes back as a u32 and an f64
//! array (or the body {"count": 13} when SPIKES is 0). Prints one JSON line: call-time
//! statistics in microseconds and 101 quantiles.
use ncp::{Channel, Client, Contract};
use serde_json::json;
use std::process::Command;
use std::time::Instant;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}"#;

fn main() {
    let mut args: Vec<String> = std::env::args().collect();
    let check = !args.iter().any(|a| a == "--no-digest-check");
    args.retain(|a| a != "--no-digest-check");
    let calls: usize = args[1].parse().expect("calls");
    let warmup: usize = args[2].parse().expect("warmup");
    let spikes: usize = args[3].parse().expect("spikes");
    let times = match args[4].as_str() {
        "--connect" => match args[5].split_once(':') {
            Some(("unix", path)) => run(ncp::connect_unix(path).expect("connect"), calls, warmup, spikes, check),
            Some(("tcp", address)) => run(ncp::connect_tcp(address, false).expect("connect"), calls, warmup, spikes, check),
            _ => panic!("--connect unix:PATH or tcp:ADDRESS"),
        },
        "--" => {
            let mut command = Command::new(&args[5]);
            command.args(&args[6..]);
            let (channel, mut child) = ncp::spawn(command).expect("spawn owner");
            let times = run(channel, calls, warmup, spikes, check);
            let status = child.wait().expect("owner exit");
            assert!(status.success(), "owner exit status {status}");
            times
        }
        _ => panic!("usage: bench_client CALLS WARMUP SPIKES (-- OWNER... | --connect ADDRESS)"),
    };
    print_summary(times, calls, warmup, spikes);
}

fn run<C: Channel>(channel: C, calls: usize, warmup: usize, spikes: usize, check: bool) -> Vec<f64> {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
    // A bound with room for the arrays (12 bytes per spike) and the envelope.
    let bound = (spikes * 12 + 65_536).next_power_of_two().clamp(ncp::DEFAULT_BOUND, ncp::MAX_BOUND);
    let client = Client::new(channel, &contract.application, &contract.identity).with_bound(bound);
    let mut client = if check { client } else { client.without_digest_check() };
    client.open().expect("open");
    let mut times = Vec::with_capacity(calls);
    for index in 0..warmup + calls {
        let started = Instant::now();
        let reply = client.call("spikes", json!({"step": index, "n": spikes}), &[]).expect("call");
        let valid = if spikes == 0 {
            reply.message["body"]["count"] == 13
        } else {
            reply.array_bytes(0).map(<[u8]>::len) == Some(spikes * 4) && reply.array_bytes(1).map(<[u8]>::len) == Some(spikes * 8)
        };
        if index >= warmup {
            times.push(started.elapsed().as_secs_f64() * 1e6);
        }
        assert!(valid, "wrong response");
    }
    client.close().expect("close");
    times
}

fn print_summary(mut times: Vec<f64>, calls: usize, warmup: usize, spikes: usize) {
    times.sort_by(|a, b| a.total_cmp(b));
    let pick = |q: f64| times[((times.len() - 1) as f64 * q).round() as usize];
    let quantiles: Vec<f64> = (0..=100).map(|i| pick(f64::from(i) / 100.0)).collect();
    let mean = times.iter().sum::<f64>() / times.len() as f64;
    println!("{}", json!({"calls": calls, "warmup": warmup, "spikes": spikes, "median_us": pick(0.5), "p05_us": pick(0.05),
                           "p95_us": pick(0.95), "p99_us": pick(0.99), "mean_us": mean, "min_us": times[0],
                           "max_us": times[times.len() - 1], "quantiles_us": quantiles}));
}
