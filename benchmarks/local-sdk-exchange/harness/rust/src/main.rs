//! Lockstep exchange harness for the local Rust SDK (see ../../PROTOCOL.md).
//!
//! Modes:
//!   owner BINDING_JSON                    serve one echo owner on stdin and stdout
//!   client N CALLS WARMUP CMD [ARG...]    drive an owner command; the binding is its last argument
//!   raw SIZE CALLS WARMUP                 time a framed echo between two processes, without NCP
//!   rawchild                              the echo peer of `raw`
//!   phases N CALLS WARMUP                 time each step of one call in one process
//!   transcript                            print every owner output for a fixed request script
//!
//! Every timed call is one request with its verified response, then one acknowledgement
//! with its verified response. A failed check ends the run with a nonzero status.
use std::io::{Read, Write};
use std::process::{Command, Stdio};
use std::time::Instant;

use ncp_local::local::{
    local_profile_digest, read_local_frame, serve_local, write_local_frame, LocalBackend,
    LocalBinding, LocalError, LocalOperation, LocalOutcome, LocalOwner, LocalRequest,
    LocalResponse, LocalRole,
};
use serde_json::{json, Value};

/// Echo backend. `n == 0` returns a spike count; `n > 0` returns `n` spikes.
struct Echo {
    n: usize,
}

/// Deterministic spike body with `n` senders and `n` times.
fn spikes(n: usize) -> Value {
    let mut state = 0x2545_f491_4f6c_dd1d_u64;
    let mut senders = Vec::with_capacity(n);
    let mut times = Vec::with_capacity(n);
    for _ in 0..n {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        senders.push(json!((state >> 33) % 1000 + 1));
        times.push(json!(((state >> 20) % 100) as f64 / 10.0 + 0.1));
    }
    json!({"senders": senders, "times": times})
}

impl LocalBackend for Echo {
    fn validate(&self, _: LocalOperation, _: &Value) -> Result<(), LocalError> {
        Ok(())
    }
    fn execute(&mut self, operation: LocalOperation, body: &Value) -> Result<Value, LocalError> {
        Ok(match operation {
            LocalOperation::Prepare => {
                self.n = body["n"].as_u64().unwrap_or(0) as usize;
                json!({"prepared": true})
            }
            LocalOperation::Step if self.n == 0 => json!({"count": 13}),
            LocalOperation::Step => spikes(self.n),
            _ => json!({"finished": true}),
        })
    }
    fn retire(&mut self) {}
}

fn binding(role: LocalRole) -> LocalBinding {
    LocalBinding {
        profile_digest: local_profile_digest().expect("profile digest"),
        run_id: "0b0fd6c0-6a0e-4c1b-9d7e-3f2a1b0c9d8e".into(),
        generation: "5f4e3d2c-1b0a-4987-a6b5-c4d3e2f1a0b9".into(),
        role,
    }
}

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

fn exchange(
    binding: &LocalBinding,
    writer: &mut impl Write,
    reader: &mut impl Read,
    request: &LocalRequest,
) -> LocalResponse {
    write_local_frame(writer, &serde_json::to_vec(request).expect("encode")).expect("write");
    let bytes = read_local_frame(reader).expect("read").expect("frame");
    let response: LocalResponse = serde_json::from_slice(&bytes).expect("decode");
    response.verify(binding, request).expect("verify");
    response
}

/// One lockstep call: request, verified response, acknowledgement, verified acknowledgement.
fn call(
    binding: &LocalBinding,
    writer: &mut impl Write,
    reader: &mut impl Read,
    sequence: u64,
    operation: LocalOperation,
    body: Value,
) -> LocalResponse {
    let sent = request(binding, sequence, operation, body);
    let response = exchange(binding, writer, reader, &sent);
    assert_eq!(response.outcome, LocalOutcome::Committed, "outcome");
    let ack = request(binding, sequence, LocalOperation::Ack, json!({"result_digest": response.result_digest}));
    let acknowledgement = exchange(binding, writer, reader, &ack);
    assert_eq!(acknowledgement.outcome, LocalOutcome::Acknowledged, "acknowledgement");
    response
}

fn summary(mut samples: Vec<f64>) -> Value {
    samples.sort_by(f64::total_cmp);
    let at = |q: f64| samples[((samples.len() - 1) as f64 * q).round() as usize] * 1e6;
    json!({"calls": samples.len(), "median_us": at(0.5), "p05_us": at(0.05), "p95_us": at(0.95),
           "p99_us": at(0.99), "min_us": at(0.0), "max_us": at(1.0)})
}

fn arg<T: std::str::FromStr>(args: &[String], index: usize) -> T {
    args[index].parse().unwrap_or_else(|_| panic!("argument {index}"))
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args[1].as_str() {
        "owner" => {
            let binding: LocalBinding = serde_json::from_str(&args[2]).expect("binding");
            let mut owner = LocalOwner::new(binding, Echo { n: 0 }).expect("owner");
            let (mut input, mut output) = (std::io::stdin().lock(), std::io::stdout().lock());
            serve_local(&mut owner, &mut input, &mut output).expect("serve");
        }
        "rawchild" => {
            let (mut input, mut output) = (std::io::stdin().lock(), std::io::stdout().lock());
            while let Some(frame) = read_local_frame(&mut input).expect("read") {
                write_local_frame(&mut output, &frame).expect("write");
            }
        }
        "raw" => {
            let (size, calls, warmup): (usize, usize, usize) = (arg(&args, 2), arg(&args, 3), arg(&args, 4));
            let mut child = Command::new(&args[0]).arg("rawchild").stdin(Stdio::piped()).stdout(Stdio::piped())
                .spawn().expect("spawn");
            let (mut writer, mut reader) = (child.stdin.take().unwrap(), child.stdout.take().unwrap());
            let message = vec![b'x'; size];
            let mut samples = Vec::with_capacity(calls);
            for index in 0..warmup + calls {
                let started = Instant::now();
                write_local_frame(&mut writer, &message).expect("write");
                let echoed = read_local_frame(&mut reader).expect("read").expect("frame");
                assert_eq!(echoed.len(), size);
                if index >= warmup {
                    samples.push(started.elapsed().as_secs_f64());
                }
            }
            drop(writer);
            child.wait().expect("wait");
            println!("{}", json!({"mode": "raw", "language": "rust", "size": size, "timing": summary(samples)}));
        }
        "client" => {
            let (n, calls, warmup): (usize, u64, u64) = (arg(&args, 2), arg(&args, 3), arg(&args, 4));
            let binding = binding(LocalRole::Neural);
            let mut child = Command::new(&args[5]).args(&args[6..])
                .arg(serde_json::to_string(&binding).expect("binding"))
                .stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().expect("spawn owner");
            let (mut writer, mut reader) = (child.stdin.take().unwrap(), child.stdout.take().unwrap());
            call(&binding, &mut writer, &mut reader, 1, LocalOperation::Prepare, json!({"n": n}));
            let mut samples = Vec::with_capacity(calls as usize);
            let mut received = 0usize;
            for index in 0..warmup + calls {
                let started = Instant::now();
                let response = call(&binding, &mut writer, &mut reader, index + 2, LocalOperation::Step,
                                    json!({"stimulus": 0}));
                let elapsed = started.elapsed().as_secs_f64();
                received = if n == 0 {
                    response.body["count"].as_u64().map_or(0, |count| count as usize)
                } else {
                    response.body["senders"].as_array().map_or(0, Vec::len)
                };
                if index >= warmup {
                    samples.push(elapsed);
                }
            }
            call(&binding, &mut writer, &mut reader, warmup + calls + 2, LocalOperation::Finish, json!({}));
            drop(writer);
            let status = child.wait().expect("wait");
            let expected = if n == 0 { 13 } else { n };
            println!("{}", json!({"mode": "client", "language": "rust", "n": n, "valid": received == expected,
                                  "owner_exit": status.code(), "timing": summary(samples)}));
        }
        "phases" => {
            let (n, calls, warmup): (usize, u64, u64) = (arg(&args, 2), arg(&args, 3), arg(&args, 4));
            let binding = binding(LocalRole::Neural);
            let mut owner = LocalOwner::new(binding.clone(), Echo { n: 0 }).expect("owner");
            let handle = |owner: &mut LocalOwner<Echo>, request: &LocalRequest| -> LocalResponse {
                let bytes = owner.handle(&serde_json::to_vec(request).expect("encode")).expect("handle");
                let response: LocalResponse = serde_json::from_slice(&bytes).expect("decode");
                response.verify(&binding, request).expect("verify");
                response
            };
            let prepared = handle(&mut owner, &request(&binding, 1, LocalOperation::Prepare, json!({"n": n})));
            handle(&mut owner, &request(&binding, 1, LocalOperation::Ack,
                                        json!({"result_digest": prepared.result_digest})));
            let names = ["seal_request", "encode_request", "owner_step", "decode_verify_response",
                         "seal_encode_ack", "owner_ack", "decode_verify_ack"];
            let mut totals = [0f64; 7];
            for index in 0..warmup + calls {
                let sequence = index + 2;
                let t0 = Instant::now();
                let sent = request(&binding, sequence, LocalOperation::Step, json!({"stimulus": 0}));
                let t1 = Instant::now();
                let bytes = serde_json::to_vec(&sent).expect("encode");
                let t2 = Instant::now();
                let output = owner.handle(&bytes).expect("handle");
                let t3 = Instant::now();
                let response: LocalResponse = serde_json::from_slice(&output).expect("decode");
                response.verify(&binding, &sent).expect("verify");
                let t4 = Instant::now();
                let ack = request(&binding, sequence, LocalOperation::Ack,
                                  json!({"result_digest": response.result_digest}));
                let ack_bytes = serde_json::to_vec(&ack).expect("encode");
                let t5 = Instant::now();
                let ack_output = owner.handle(&ack_bytes).expect("handle");
                let t6 = Instant::now();
                let acknowledgement: LocalResponse = serde_json::from_slice(&ack_output).expect("decode");
                acknowledgement.verify(&binding, &ack).expect("verify");
                let t7 = Instant::now();
                if index >= warmup {
                    for (slot, (from, to)) in [(t0, t1), (t1, t2), (t2, t3), (t3, t4), (t4, t5), (t5, t6), (t6, t7)]
                        .into_iter().enumerate() {
                        totals[slot] += (to - from).as_secs_f64();
                    }
                }
            }
            let phases: serde_json::Map<String, Value> = names.iter().zip(totals)
                .map(|(name, total)| (name.to_string(), json!(total / calls as f64 * 1e6))).collect();
            println!("{}", json!({"mode": "phases", "n": n, "calls": calls, "mean_us": phases,
                                  "total_mean_us": totals.iter().sum::<f64>() / calls as f64 * 1e6}));
        }
        "transcript" => transcript(),
        other => panic!("unknown mode {other}"),
    }
}

/// Owner outputs for a fixed script of valid, rejected, retried, and queried requests.
/// The released and current SDKs must print the same lines.
fn transcript() {
    let binding = binding(LocalRole::Neural);
    let mut owner = LocalOwner::new(binding.clone(), Echo { n: 0 }).expect("owner");
    let mut out = std::io::stdout().lock();
    let mut emit = |label: &str, request: &LocalRequest, owner: &mut LocalOwner<Echo>| -> Option<LocalResponse> {
        let bytes = serde_json::to_vec(request).expect("encode");
        match owner.handle(&bytes) {
            Ok(output) => {
                writeln!(out, "{label}\t{}\t{}", request.request_digest, String::from_utf8_lossy(&output)).unwrap();
                let response: LocalResponse = serde_json::from_slice(&output).expect("decode");
                let verdict = response.verify(&binding, request).map_err(|error| format!("{error}"));
                writeln!(out, "{label}\tverify\t{verdict:?}").unwrap();
                Some(response)
            }
            Err(error) => {
                writeln!(out, "{label}\t{}\terror {error}", request.request_digest).unwrap();
                None
            }
        }
    };
    let prepare = request(&binding, 1, LocalOperation::Prepare, json!({"n": 127}));
    let early_step = request(&binding, 1, LocalOperation::Step, json!({"stimulus": 0}));
    emit("step-before-prepare", &early_step, &mut owner);
    let prepared = emit("prepare", &prepare, &mut owner).expect("prepared");
    emit("prepare-retry", &prepare, &mut owner);
    let pending = request(&binding, 2, LocalOperation::Step, json!({"stimulus": 0}));
    emit("step-while-pending", &pending, &mut owner);
    let wrong_ack = request(&binding, 1, LocalOperation::Ack, json!({"result_digest": "0".repeat(64)}));
    emit("wrong-ack", &wrong_ack, &mut owner);
    let lookup = request(&binding, 1, LocalOperation::Result, json!({"request_digest": prepare.request_digest}));
    emit("result-lookup", &lookup, &mut owner);
    let ack = request(&binding, 1, LocalOperation::Ack, json!({"result_digest": prepared.result_digest}));
    emit("ack", &ack, &mut owner);
    emit("ack-repeat", &ack, &mut owner);
    emit("released-lookup", &lookup, &mut owner);
    emit("released-retry", &prepare, &mut owner);
    let forbidden = request(&binding, 2, LocalOperation::Capture, json!({}));
    emit("role-forbidden", &forbidden, &mut owner);
    let mut foreign = binding.clone();
    foreign.run_id = "11111111-2222-4333-8444-555555555555".into();
    emit("foreign-run", &request(&foreign, 2, LocalOperation::Step, json!({"stimulus": 0})), &mut owner);
    let mut sequence = 2;
    for body in [json!({"stimulus": 0}), json!({"a": -0.0, "b": [1, 2.5, "é", null, true], "c": {"z": 1, "a": 2}}),
                 json!({"big": 9_007_199_254_740_991_u64, "small": -1e-300, "large": 1e300})] {
        let step = request(&binding, sequence, LocalOperation::Step, body);
        let response = emit("step", &step, &mut owner).expect("step");
        let skipped = request(&binding, sequence + 5, LocalOperation::Step, json!({"stimulus": 0}));
        emit("step-gap", &skipped, &mut owner);
        let ack = request(&binding, sequence, LocalOperation::Ack, json!({"result_digest": response.result_digest}));
        emit("step-ack", &ack, &mut owner);
        sequence += 1;
    }
    let finish = request(&binding, sequence, LocalOperation::Finish, json!({}));
    let finished = emit("finish", &finish, &mut owner).expect("finish");
    let ack = request(&binding, sequence, LocalOperation::Ack, json!({"result_digest": finished.result_digest}));
    emit("finish-ack", &ack, &mut owner);
    emit("after-finish", &request(&binding, sequence + 1, LocalOperation::Step, json!({"stimulus": 0})), &mut owner);
}
