//! Sequential and pipelined lockstep clients for the local Rust SDK (see ../../PROTOCOL.md).
//!
//! Modes:
//!   owner BINDING_JSON                              serve one echo owner on stdin and stdout
//!   sequential N CALLS WARMUP CMD [ARG...]          v1 client: request, response, ack, ack response
//!   pipelined N CALLS WARMUP CMD [ARG...]           ack n and request n+1 written back to back
//!   soak N CALLS WARMUP CMD [ARG...]                sequential, keeping a fixed 4096-call sample of times
//!
//! The owner is the unchanged v1 owner. A pipelined client breaks the v1 client rule that
//! only a verified acknowledgement advances the sequence; this harness measures what that
//! rule costs. It is not an SDK interface.
use std::io::{Read, Write};
use std::process::{Command, Stdio};
use std::time::Instant;

use ncp_local::local::{
    local_profile_digest, read_local_frame, serve_local, write_local_frame, LocalBackend,
    LocalBinding, LocalError, LocalOperation, LocalOutcome, LocalOwner, LocalRequest,
    LocalResponse, LocalRole,
};
use serde_json::{json, Value};

/// Builds the spike body once in prepare, as every arm of benchmarks/comparison does.
struct Echo {
    n: usize,
    body: Value,
}

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
                self.body = if self.n == 0 { json!({"count": 13}) } else { spikes(self.n) };
                json!({"prepared": true})
            }
            LocalOperation::Step => self.body.clone(),
            _ => json!({"finished": true}),
        })
    }
    fn retire(&mut self) {}
}

fn binding() -> LocalBinding {
    LocalBinding {
        profile_digest: local_profile_digest().expect("profile digest"),
        run_id: "0b0fd6c0-6a0e-4c1b-9d7e-3f2a1b0c9d8e".into(),
        generation: "5f4e3d2c-1b0a-4987-a6b5-c4d3e2f1a0b9".into(),
        role: LocalRole::Neural,
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

fn send(writer: &mut impl Write, request: &LocalRequest) {
    write_local_frame(writer, &serde_json::to_vec(request).expect("encode")).expect("write");
}

fn receive(binding: &LocalBinding, reader: &mut impl Read, request: &LocalRequest) -> LocalResponse {
    let bytes = read_local_frame(reader).expect("read").expect("frame");
    let response: LocalResponse = serde_json::from_slice(&bytes).expect("decode");
    response.verify(binding, request).expect("verify");
    response
}

fn ack_of(binding: &LocalBinding, response: &LocalResponse) -> LocalRequest {
    request(binding, response.sequence, LocalOperation::Ack, json!({"result_digest": response.result_digest}))
}

fn committed(response: &LocalResponse) {
    assert_eq!(response.outcome, LocalOutcome::Committed, "outcome");
}

fn acknowledged(response: &LocalResponse) {
    assert_eq!(response.outcome, LocalOutcome::Acknowledged, "acknowledgement");
}

fn count(n: usize, response: &LocalResponse) -> usize {
    if n == 0 {
        response.body["count"].as_u64().map_or(0, |count| count as usize)
    } else {
        response.body["senders"].as_array().map_or(0, Vec::len)
    }
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
    if args[1] == "owner" {
        let binding: LocalBinding = serde_json::from_str(&args[2]).expect("binding");
        let mut owner = LocalOwner::new(binding, Echo { n: 0, body: Value::Null }).expect("owner");
        let (mut input, mut output) = (std::io::stdin().lock(), std::io::stdout().lock());
        serve_local(&mut owner, &mut input, &mut output).expect("serve");
        return;
    }
    let mode = args[1].clone();
    let (n, calls, warmup): (usize, u64, u64) = (arg(&args, 2), arg(&args, 3), arg(&args, 4));
    let binding = binding();
    let mut child = Command::new(&args[5]).args(&args[6..])
        .arg(serde_json::to_string(&binding).expect("binding"))
        .stdin(Stdio::piped()).stdout(Stdio::piped()).spawn().expect("spawn owner");
    let (mut writer, mut reader) = (child.stdin.take().unwrap(), child.stdout.take().unwrap());
    // Prepare and acknowledge sequentially in both modes.
    let prepare = request(&binding, 1, LocalOperation::Prepare, json!({"n": n}));
    send(&mut writer, &prepare);
    let prepared = receive(&binding, &mut reader, &prepare);
    committed(&prepared);
    let ack = ack_of(&binding, &prepared);
    send(&mut writer, &ack);
    acknowledged(&receive(&binding, &mut reader, &ack));
    // The soak mode keeps a uniform reservoir of call times, so that its memory stays fixed.
    let reservoir = mode == "soak";
    let mut samples = Vec::with_capacity(if reservoir { 4096 } else { calls as usize });
    let mut state = 0x9e37_79b9_7f4a_7c15_u64;
    let mut timed = 0u64;
    let mut received = 0usize;
    let mut held: Option<LocalResponse> = None;
    for index in 0..warmup + calls {
        let sequence = index + 2;
        let step = request(&binding, sequence, LocalOperation::Step, json!({"stimulus": 0}));
        let started = Instant::now();
        let response = match mode.as_str() {
            "sequential" | "soak" => {
                send(&mut writer, &step);
                let response = receive(&binding, &mut reader, &step);
                committed(&response);
                let ack = ack_of(&binding, &response);
                send(&mut writer, &ack);
                acknowledged(&receive(&binding, &mut reader, &ack));
                response
            }
            "pipelined" => {
                // Acknowledge the previous step and send this one back to back.
                let previous = held.take().map(|response| ack_of(&binding, &response));
                if let Some(ack) = &previous {
                    send(&mut writer, ack);
                }
                send(&mut writer, &step);
                if let Some(ack) = &previous {
                    acknowledged(&receive(&binding, &mut reader, ack));
                }
                let response = receive(&binding, &mut reader, &step);
                committed(&response);
                held = Some(response.clone());
                response
            }
            other => panic!("unknown mode {other}"),
        };
        let elapsed = started.elapsed().as_secs_f64();
        received = count(n, &response);
        if index >= warmup {
            timed += 1;
            if !reservoir || samples.len() < 4096 {
                samples.push(elapsed);
            } else {
                state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
                let slot = (state >> 33) % timed;
                if slot < 4096 {
                    samples[slot as usize] = elapsed;
                }
            }
        }
    }
    if let Some(response) = held.take() {
        let ack = ack_of(&binding, &response);
        send(&mut writer, &ack);
        acknowledged(&receive(&binding, &mut reader, &ack));
    }
    let finish = request(&binding, warmup + calls + 2, LocalOperation::Finish, json!({}));
    send(&mut writer, &finish);
    let finished = receive(&binding, &mut reader, &finish);
    committed(&finished);
    let ack = ack_of(&binding, &finished);
    send(&mut writer, &ack);
    acknowledged(&receive(&binding, &mut reader, &ack));
    drop(writer);
    let status = child.wait().expect("wait");
    let expected = if n == 0 { 13 } else { n };
    println!("{}", json!({"mode": mode, "language": "rust", "n": n, "valid": received == expected,
                          "owner_exit": status.code(), "timing": summary(samples)}));
}
