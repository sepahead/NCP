//! Rust host of content protocol 3 of the NEST campaign (see ../../../PROTOCOL-CONTENT-3.md), on
//! revision 7 of the NCP 2 SDK.
//!
//! Usage: ncp2-nest-host7 NETWORK N THREADS DELTA_MS SEED OUT CONTRACT OWNER [ARG...]
//! Starts the NEST owner, prepares the network, advances 2 s of simulated time in steps of
//! DELTA_MS, and finishes. Writes every received event to OUT as JSON, each float64 in a form that
//! reads back to the same bits, and prints one JSON line.
use ncp::{Client, Contract, Decoded};
use serde_json::{json, Map, Value};
use std::process::Command;

const T_BIO_MS: f64 = 2000.0;
/// The arrays of a step response, with their dtypes (harness/networks7.py, ARRAYS).
const ARRAYS: [(&str, &str); 6] = [
    ("senders", "u32"),
    ("steps", "i64"),
    ("offsets", "f64"),
    ("vm_senders", "u32"),
    ("vm_steps", "i64"),
    ("vm_values", "f64"),
];

/// The little-endian bytes of the one-dimensional array that a body member refers to.
fn array<'a>(reply: &'a Decoded, member: &str, dtype: &str) -> &'a [u8] {
    let spec = &reply.message["body"][member]["ncp.array"];
    assert_eq!(
        spec["dtype"].as_str(),
        Some(dtype),
        "{member} is not a {dtype} array"
    );
    assert_eq!(
        spec["shape"].as_array().map(Vec::len),
        Some(1),
        "{member} is not one-dimensional"
    );
    let index = spec["att"].as_u64().expect("array reference") as usize;
    reply.array_bytes(index).expect("attachment")
}

fn values(bytes: &[u8], dtype: &str) -> Vec<Value> {
    match dtype {
        "u32" => bytes
            .as_chunks::<4>()
            .0
            .iter()
            .map(|c| Value::from(u32::from_le_bytes(*c)))
            .collect(),
        "i64" => bytes
            .as_chunks::<8>()
            .0
            .iter()
            .map(|c| Value::from(i64::from_le_bytes(*c)))
            .collect(),
        // A NaN has no JSON form and becomes null, which the comparison counts as a difference.
        _ => bytes
            .as_chunks::<8>()
            .0
            .iter()
            .map(|c| Value::from(f64::from_le_bytes(*c)))
            .collect(),
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let network = args[1].clone();
    let n: u64 = args[2].parse().expect("n");
    let threads: u64 = args[3].parse().expect("threads");
    let delta: f64 = args[4].parse().expect("delta");
    let seed: u64 = args[5].parse().expect("seed");
    let out = args[6].clone();
    let contract =
        Contract::from_bytes(std::fs::read(&args[7]).expect("contract file")).expect("contract");
    let mut command = Command::new(&args[8]);
    command.args(&args[9..]);
    let channel = ncp::spawn(command).expect("spawn owner");
    let mut client = Client::new(channel, &contract);
    client.open().expect("open");
    let spec =
        json!({"network": network, "n": n, "threads": threads, "delta_ms": delta, "seed": seed});
    let prepared = client.call("prepare", spec, &[]).expect("prepare");
    let first = prepared.message["body"]["first"].clone();
    let steps = (T_BIO_MS / delta).round() as u64;
    let mut collected: Vec<Vec<Value>> = vec![Vec::new(); ARRAYS.len()];
    for _ in 0..steps {
        let reply = client.call("step", json!({}), &[]).expect("step");
        for ((name, dtype), into) in ARRAYS.iter().zip(collected.iter_mut()) {
            into.extend(values(array(&reply, name, dtype), dtype));
        }
    }
    let finished = client.call("finish", json!({}), &[]).expect("finish");
    client.close().expect("close");
    let status = match client.channel_mut().exit_status() {
        Some(status) => status,
        None => client.channel_mut().child().wait().expect("wait"),
    };
    let (spikes, vm) = (collected[0].len(), collected[5].len());
    let mut record = Map::new();
    record.insert("first".into(), first);
    for ((name, _), list) in ARRAYS.iter().zip(collected) {
        record.insert((*name).into(), Value::Array(list));
    }
    std::fs::write(
        &out,
        serde_json::to_vec(&Value::Object(record)).expect("events"),
    )
    .expect("write events");
    println!(
        "{}",
        json!({"arm": "ncp2-rs", "network": network, "n": n, "threads": threads, "delta_ms": delta,
               "seed": seed, "exchanges": steps, "spikes": spikes, "vm": vm,
               "owner_sent": finished.message["body"], "child_exit": status.code()})
    );
}
