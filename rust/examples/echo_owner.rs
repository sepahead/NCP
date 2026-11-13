//! An echo owner for tests and benchmarks: returns the request body and arrays.
//!
//! echo_owner [--no-digest-check]             one session on standard input and output
//! echo_owner [--no-digest-check] unix PATH   one session per connection; prints "ready unix:PATH"
//! echo_owner tcp                             one session per connection; prints "ready tcp:127.0.0.1:PORT"
//!
//! --no-digest-check turns off the comparison of request digests (spec section 3, rule 5).
//! With NCP_EXECUTION_LOG set, each execution first appends its request body as one JSON line to
//! that file; benchmarks/fault-campaign compares these lines with what the client learned.
use ncp::{declined, events, AppError, Array, Contract, Handler, Invalid, Owner, Reply, Request};
use serde_json::json;
use std::collections::HashMap;
use std::io::Write;
use std::sync::Arc;

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
struct Echo {
    cache: HashMap<usize, (Array, Array)>,
    log: Option<std::fs::File>,
}

impl Default for Echo {
    fn default() -> Self {
        let log = std::env::var_os("NCP_EXECUTION_LOG").map(|path| {
            std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .expect("execution log")
        });
        Echo {
            cache: HashMap::new(),
            log,
        }
    }
}

impl Handler for Echo {
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        if request.op == "echo" && request.body["invalid"] == true {
            return Err(declined("invalid requested"));
        }
        if request.op == "spikes" && request.body["n"].as_u64().is_none_or(|n| n > 1 << 22) {
            return Err(declined("n must be an integer from 0 to 2^22"));
        }
        Ok(())
    }

    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        if let Some(log) = self.log.as_mut() {
            // One write for the whole line, so that a killed owner leaves whole lines.
            log.write_all(format!("{}\n", request.body).as_bytes())?;
        }
        match request.op {
            "fail" => Err("requested failure".into()),
            "spikes" => {
                let n = request.body["n"].as_u64().unwrap_or(0) as usize;
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
                body: request.body.clone(),
                arrays: request.owned_arrays(),
            }),
        }
    }
}

fn owner(contract: &Contract, check_digests: bool) -> Owner<Echo> {
    let owner = Owner::new(contract.clone(), Echo::default())
        .with_max_bound(ncp::MAX_BOUND)
        .with_observer(Arc::new(events::Silent)); // the requested failures are expected
    if check_digests {
        owner
    } else {
        owner.without_digest_check()
    }
}

fn main() -> std::io::Result<()> {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).map_err(std::io::Error::other)?;
    let mut args: Vec<String> = std::env::args().collect();
    let check = !args.iter().any(|a| a == "--no-digest-check");
    args.retain(|a| a != "--no-digest-check");
    let mut server = match args.get(1).map(String::as_str) {
        None => {
            if let Err(error) = ncp::serve_stdio(&mut owner(&contract, check)) {
                eprintln!("echo owner: {error}");
                std::process::exit(1);
            }
            return Ok(());
        }
        Some("unix") => {
            let server = ncp::serve_unix(
                &args[2],
                move || owner(&contract, check),
                ncp::Limits::default(),
            )?;
            println!("ready unix:{}", args[2]);
            server
        }
        Some(_) => {
            let server = ncp::serve_tcp(
                "127.0.0.1:0",
                false,
                move || owner(&contract, true),
                ncp::Limits::default(),
            )?;
            println!("ready tcp:{}", server.address());
            server
        }
    };
    std::io::stdout().flush()?;
    // Serve until standard input closes.
    let mut sink = Vec::new();
    let _ = std::io::Read::read_to_end(&mut std::io::stdin(), &mut sink);
    server.stop(std::time::Duration::from_secs(1));
    Ok(())
}
