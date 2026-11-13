//! An echo owner on the Zenoh binding, for the cross-language tests of the Python binding.
//!
//! zenoh_echo_owner SERVICE LISTEN_ENDPOINT
//! Serves `ncp/x/SERVICE` in peer mode on LISTEN_ENDPOINT (for example tcp/127.0.0.1:7447),
//! prints "ready", and serves until its standard input closes. It has the test contract of the
//! binding (echo, fail, sleep, spikes): each operation but `fail` returns the request body and
//! arrays, and `sleep` first waits `seconds`. Each execution appends the body as one line to
//! NCP_EXECUTION_LOG, if set.
use ncp::{AppError, Contract, Handler, Invalid, Owner, Reply, Request};
use std::io::{Read, Write};
use std::sync::Mutex;
use std::time::Duration;
use zenoh::Wait;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"sleep":{},"spikes":{}},"streams":{}}"#;

struct Echo {
    log: Option<std::fs::File>,
}

impl Handler for Echo {
    fn validate(&mut self, _request: &Request<'_>) -> Result<(), Invalid> {
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        if let Some(log) = self.log.as_mut() {
            writeln!(log, "{}", request.body)?;
        }
        if request.op == "fail" {
            return Err("requested failure".into());
        }
        if request.op == "sleep" {
            let seconds = request.body["seconds"].as_f64().unwrap_or(0.0);
            std::thread::sleep(Duration::from_secs_f64(seconds));
        }
        Ok(Reply {
            body: request.body.clone(),
            arrays: request.owned_arrays(),
        })
    }
}

fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let args: Vec<String> = std::env::args().collect();
    let (service, endpoint) = (&args[1], &args[2]);
    let contract = Contract::from_bytes(CONTRACT.to_vec())?;
    let mut config = zenoh::Config::default();
    config.insert_json5("mode", r#""peer""#)?;
    config.insert_json5("scouting/multicast/enabled", "false")?;
    config.insert_json5("listen/endpoints", &format!(r#"["{endpoint}"]"#))?;
    let session = zenoh::open(config).wait()?;
    let log_path = std::env::var_os("NCP_EXECUTION_LOG");
    let make_owner = {
        let log_path = Mutex::new(log_path);
        move || {
            let log = log_path.lock().unwrap().as_ref().map(|path| {
                std::fs::OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(path)
                    .expect("execution log")
            });
            Owner::new(contract.clone(), Echo { log })
        }
    };
    let server = ncp_zenoh::Server::declare(&session, service, make_owner, Default::default())?;
    println!("ready");
    std::io::stdout().flush()?;
    let _ = std::io::stdin().read_to_end(&mut Vec::new());
    server.stop(Duration::ZERO);
    session.close().wait()?;
    Ok(())
}
