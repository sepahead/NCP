//! An echo owner for tests and benchmarks: returns the request body and arrays.
//!
//! echo_owner [--no-digest-check]             one session on standard input and output
//! echo_owner [--no-digest-check] unix PATH   one session per connection; prints "ready unix:PATH"
//! echo_owner tcp                             one session per connection; prints "ready tcp:127.0.0.1:PORT"
//!
//! --no-digest-check turns off the comparison of request digests (spec section 3, rule 4).
use ncp::{binding, Array, Contract, Decoded, Handler, Owner, Reply};
use serde_json::json;
use std::collections::HashMap;
use std::io::Write;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"spikes":{}},"streams":{}}"#;

/// N spikes from the benchmark generator: senders 1 to 1000 (u32), times 0.1 to 10.0 ms (f64).
fn spikes(n: usize) -> (Array, Array) {
    let mut state = 0x2545_f491_4f6c_dd1d_u64;
    let (mut senders, mut times) = (Vec::with_capacity(n), Vec::with_capacity(n));
    for _ in 0..n {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        senders.push(((state >> 33) % 1000 + 1) as u32);
        times.push(((state >> 20) % 100) as f64 / 10.0 + 0.1);
    }
    (Array::from_u32(&senders), Array::from_f64(&times))
}

/// echo returns the request body; spikes returns N cached spikes; fail fails.
#[derive(Default)]
struct Echo {
    cache: HashMap<usize, (Array, Array)>,
}

impl Handler for Echo {
    fn validate(&mut self, op: &str, request: &Decoded) -> Result<(), String> {
        let body = &request.message["body"];
        if op == "echo" && body["invalid"] == true {
            return Err("invalid requested".into());
        }
        if op == "spikes" && body["n"].as_u64().is_none_or(|n| n > 1 << 22) {
            return Err("n must be an integer from 0 to 2^22".into());
        }
        Ok(())
    }
    fn execute(
        &mut self,
        op: &str,
        request: &Decoded,
    ) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        match op {
            "fail" => Err("requested failure".into()),
            "spikes" => {
                let n = request.message["body"]["n"].as_u64().unwrap_or(0) as usize;
                if n == 0 {
                    return Ok(json!({"count": 13}).into());
                }
                let (senders, times) = self.cache.entry(n).or_insert_with(|| spikes(n)).clone();
                let body = json!({"senders": senders.reference(0), "times": times.reference(1)});
                Ok(Reply {
                    body,
                    arrays: vec![senders, times],
                })
            }
            _ => Ok(Reply {
                body: request.message["body"].clone(),
                arrays: request.owned_arrays(),
            }),
        }
    }
}

fn owner(contract: &Contract, check_digests: bool) -> Owner<Echo> {
    let owner = Owner::new(
        &contract.application,
        &contract.identity,
        Echo::default(),
        contract.operations.clone(),
        ncp::MAX_BOUND,
    );
    if check_digests {
        owner
    } else {
        owner.without_digest_check()
    }
}

fn serve_one<R: std::io::Read, W: std::io::Write>(
    contract: &Contract,
    check: bool,
    channel: std::io::Result<ncp::StreamChannel<R, W>>,
) {
    if let Ok(mut channel) = channel {
        let _ = binding::serve(&mut owner(contract, check), &mut channel);
    }
}

fn main() -> std::io::Result<()> {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).map_err(std::io::Error::other)?;
    let mut args: Vec<String> = std::env::args().collect();
    let check = !args.iter().any(|a| a == "--no-digest-check");
    args.retain(|a| a != "--no-digest-check");
    match args.get(1).map(String::as_str) {
        None => {
            if let Err(error) = ncp::serve_stdio(&mut owner(&contract, check)) {
                eprintln!("echo owner: {error}");
                std::process::exit(1);
            }
        }
        Some("unix") => {
            let listener = std::os::unix::net::UnixListener::bind(&args[2])?;
            println!("ready unix:{}", args[2]);
            std::io::stdout().flush()?;
            for stream in listener.incoming() {
                let (stream, contract) = (stream?, contract.clone());
                std::thread::spawn(move || {
                    serve_one(&contract, check, binding::unix_channel(stream))
                });
            }
        }
        Some(_) => {
            let listener = binding::listen_tcp("127.0.0.1:0", false)?;
            println!("ready tcp:127.0.0.1:{}", listener.local_addr()?.port());
            std::io::stdout().flush()?;
            for stream in listener.incoming() {
                let (stream, contract) = (stream?, contract.clone());
                std::thread::spawn(move || {
                    serve_one(&contract, check, binding::tcp_channel(stream))
                });
            }
        }
    }
    Ok(())
}
