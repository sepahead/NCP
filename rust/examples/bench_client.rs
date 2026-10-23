//! Time lockstep calls to an owner process: bench_client CALLS WARMUP SPIKES -- OWNER COMMAND...
//! Prints one JSON line with the median and percentiles of the call time in microseconds.
use ncp::{Array, Client, Contract};
use serde_json::json;
use std::process::Command;
use std::time::Instant;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{}},"streams":{}}"#;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let separator = args.iter().position(|a| a == "--").expect("usage: bench_client CALLS WARMUP SPIKES -- OWNER...");
    let calls: usize = args[1].parse().expect("calls");
    let warmup: usize = args[2].parse().expect("warmup");
    let spikes: usize = args[3].parse().expect("spikes");
    let mut command = Command::new(&args[separator + 1]);
    command.args(&args[separator + 2..]);
    let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
    let (channel, mut child) = ncp::spawn(command).expect("spawn owner");
    let mut client = Client::new(channel, &contract.application, &contract.identity);
    client.open().expect("open");
    let senders: Vec<u32> = (0..spikes as u32).collect();
    let steps: Vec<u32> = (0..spikes as u32).map(|i| i * 7).collect();
    let mut times = Vec::with_capacity(calls);
    for index in 0..warmup + calls {
        let started = Instant::now();
        let (body, arrays) = if spikes > 0 {
            let arrays = vec![Array::from_u32(&senders), Array::from_u32(&steps)];
            (json!({"step": index, "senders": arrays[0].reference(0), "steps": arrays[1].reference(1)}), arrays)
        } else {
            (json!({"stimulus": index}), Vec::new())
        };
        let reply = client.call("echo", body, &arrays).expect("call");
        assert!(reply.message["outcome"] == "ok");
        if index >= warmup {
            times.push(started.elapsed().as_secs_f64() * 1e6);
        }
    }
    client.close().expect("close");
    let _ = child.wait();
    times.sort_by(|a, b| a.total_cmp(b));
    let pick = |q: f64| times[((times.len() - 1) as f64 * q).round() as usize];
    println!("{}", json!({"calls": calls, "spikes": spikes, "median_us": pick(0.5), "p05_us": pick(0.05),
                           "p95_us": pick(0.95), "p99_us": pick(0.99), "min_us": times[0], "max_us": times[times.len()-1]}));
}
