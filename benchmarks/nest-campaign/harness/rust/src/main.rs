//! Rust NCP host for the NEST campaign (see ../../../PROTOCOL.md).
//!
//! Usage: host PAYLOAD NETWORK N THREADS DELTA_MS SEED CMD [ARG...]
//! Starts the NEST owner command with the binding as its last argument, prepares the
//! network, advances 2 s of biological time in steps of DELTA_MS, and finishes. Each
//! call is a request, its verified response, an acknowledgement, and its verified
//! response. Prints one JSON line.
use std::io::{Read, Write};
use std::process::{Command, Stdio};
use std::time::Instant;

use ncp_local::local::{
    local_profile_digest, read_local_frame, write_local_frame, LocalBinding, LocalOperation, LocalOutcome,
    LocalRequest, LocalResponse, LocalRole,
};
use serde_json::{json, Value};

const T_BIO_MS: f64 = 2000.0;

fn request(binding: &LocalBinding, sequence: u64, operation: LocalOperation, body: Value) -> LocalRequest {
    let mut request = LocalRequest {
        schema: "ncp.local.request.v1".into(),
        profile_digest: binding.profile_digest.clone(),
        run_id: binding.run_id.clone(),
        generation: binding.generation.clone(),
        sequence,
        operation,
        body,
        request_digest: String::new(),
    };
    request.seal().expect("seal");
    request
}

fn exchange(binding: &LocalBinding, writer: &mut impl Write, reader: &mut impl Read, request: &LocalRequest)
    -> LocalResponse {
    write_local_frame(writer, &serde_json::to_vec(request).expect("encode")).expect("write");
    let bytes = read_local_frame(reader).expect("read").expect("frame");
    let response: LocalResponse = serde_json::from_slice(&bytes).expect("decode");
    response.verify(binding, request).expect("verify");
    response
}

fn call(binding: &LocalBinding, writer: &mut impl Write, reader: &mut impl Read, sequence: u64,
        operation: LocalOperation, body: Value) -> LocalResponse {
    let sent = request(binding, sequence, operation, body);
    let response = exchange(binding, writer, reader, &sent);
    assert_eq!(response.outcome, LocalOutcome::Committed, "outcome");
    let ack = request(binding, sequence, LocalOperation::Ack, json!({"result_digest": response.result_digest}));
    assert_eq!(exchange(binding, writer, reader, &ack).outcome, LocalOutcome::Acknowledged, "ack");
    response
}

// A UUID version 4 string from the process clock and identity, for one fresh generation.
fn fresh_uuid(salt: u64) -> String {
    let mut state = (std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64)
        ^ (u64::from(std::process::id()) << 32) ^ salt;
    let mut hex = String::new();
    for _ in 0..32 {
        state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
        hex.push(char::from_digit(((state >> 59) & 15) as u32, 16).unwrap());
    }
    format!("{}-{}-4{}-a{}-{}", &hex[0..8], &hex[8..12], &hex[13..16], &hex[17..20], &hex[20..32])
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let payload = args[1].clone();
    let (network, n, threads, delta, seed) = (args[2].clone(), args[3].parse::<u64>().unwrap(),
        args[4].parse::<u64>().unwrap(), args[5].parse::<f64>().unwrap(), args[6].parse::<u64>().unwrap());
    let binding = LocalBinding {
        profile_digest: local_profile_digest().expect("profile digest"),
        run_id: fresh_uuid(1),
        generation: fresh_uuid(2),
        role: LocalRole::Neural,
    };
    let mut child = Command::new(&args[7]).args(&args[8..])
        .arg(serde_json::to_string(&binding).expect("binding"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().expect("spawn owner");
    let (mut writer, mut reader) = (child.stdin.take().unwrap(), child.stdout.take().unwrap());
    call(&binding, &mut writer, &mut reader, 1, LocalOperation::Prepare,
         json!({"network": network, "n": n, "threads": threads, "delta_ms": delta, "seed": seed, "payload": payload}));
    let steps = (T_BIO_MS / delta).round() as u64;
    let mut spikes = 0u64;
    let mut calls: Vec<u64> = Vec::with_capacity(steps as usize);
    let started = Instant::now();
    for index in 0..steps {
        let call_started = Instant::now();
        let response = call(&binding, &mut writer, &mut reader, index + 2, LocalOperation::Step,
                            json!({"stimulus": 0}));
        calls.push(call_started.elapsed().as_nanos() as u64);
        spikes += if payload == "count" {
            response.body["count"].as_u64().expect("count")
        } else {
            response.body["senders"].as_array().map_or(0, Vec::len) as u64
        };
    }
    let wall = started.elapsed().as_secs_f64();
    // Protocol 4: each call (request and acknowledgement) as the host sees it, in nanoseconds.
    if let Ok(path) = std::env::var("NCP_CALL_TIMES") {
        std::fs::write(path, serde_json::to_vec(&calls).expect("times")).expect("write times");
    }
    let finished = call(&binding, &mut writer, &mut reader, steps + 2, LocalOperation::Finish, json!({}));
    drop(writer);
    let status = child.wait().expect("wait");
    println!("{}", json!({"arm": format!("ncp-rs-{payload}"), "network": network, "n": n, "threads": threads,
                          "delta_ms": delta, "seed": seed, "wall_s": wall, "spikes": spikes,
                          "recorded": finished.body["recorded"], "exchanges": steps, "child_exit": status.code()}));
}
