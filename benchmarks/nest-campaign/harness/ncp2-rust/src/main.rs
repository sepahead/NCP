//! Rust host for the NCP 2 arms of the NEST campaign (see ../../../PROTOCOL-3.md).
//!
//! Usage: ncp2-nest-host PAYLOAD NETWORK N THREADS DELTA_MS SEED CONTRACT OWNER [ARG...]
//! Starts the NEST owner, prepares the network, advances 2 s of simulated time in steps of
//! DELTA_MS, and finishes. Prints one JSON line.
use ncp::{Client, Contract, Decoded};
use serde_json::json;
use std::process::Command;
use std::time::Instant;

const T_BIO_MS: f64 = 2000.0;

/// The number of elements of the array that a body member refers to.
fn array_length(reply: &Decoded, member: &str) -> u64 {
    let index = reply.message["body"][member]["ncp.array"]["att"]
        .as_u64()
        .expect("array reference") as usize;
    reply.arrays[index].shape.iter().product()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let payload = args[1].clone();
    let network = args[2].clone();
    let n: u64 = args[3].parse().expect("n");
    let threads: u64 = args[4].parse().expect("threads");
    let delta: f64 = args[5].parse().expect("delta");
    let seed: u64 = args[6].parse().expect("seed");
    let contract =
        Contract::from_bytes(std::fs::read(&args[7]).expect("contract file")).expect("contract");
    let mut command = Command::new(&args[8]);
    command.args(&args[9..]);
    let (channel, mut child) = ncp::spawn(command).expect("spawn owner");
    let mut client = Client::new(channel, &contract.application, &contract.identity);
    client.open().expect("open");
    let spec = json!({"network": network, "n": n, "threads": threads, "delta_ms": delta, "seed": seed, "payload": payload});
    client.call("prepare", spec, &[]).expect("prepare");
    let steps = (T_BIO_MS / delta).round() as u64;
    let mut spikes = 0u64;
    let mut calls: Vec<u64> = Vec::with_capacity(steps as usize);
    let started = Instant::now();
    for _ in 0..steps {
        let call_started = Instant::now();
        let reply = client
            .call("step", json!({"stimulus": 0}), &[])
            .expect("step");
        calls.push(call_started.elapsed().as_nanos() as u64);
        spikes += if payload == "count" {
            reply.message["body"]["count"].as_u64().expect("count")
        } else {
            array_length(&reply, "senders")
        };
    }
    let wall = started.elapsed().as_secs_f64();
    // Protocol 4: each call as the host sees it, in nanoseconds.
    if let Ok(path) = std::env::var("NCP_CALL_TIMES") {
        std::fs::write(path, serde_json::to_vec(&calls).expect("times")).expect("write times");
    }
    let finished = client.call("finish", json!({}), &[]).expect("finish");
    client.close().expect("close");
    let status = child.wait().expect("wait");
    println!(
        "{}",
        json!({"arm": format!("ncp2-rs-{payload}"), "network": network, "n": n, "threads": threads,
               "delta_ms": delta, "seed": seed, "wall_s": wall, "spikes": spikes,
               "recorded": finished.message["body"]["recorded"], "exchanges": steps, "child_exit": status.code()})
    );
}
