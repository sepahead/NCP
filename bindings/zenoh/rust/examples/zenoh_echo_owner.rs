//! An echo owner on the Zenoh binding, for the cross-language tests of the Python binding.
//!
//! zenoh_echo_owner SERVICE LISTEN_ENDPOINT
//! Serves `ncp/x/SERVICE` in peer mode on LISTEN_ENDPOINT (for example tcp/127.0.0.1:7447),
//! prints "ready", and serves until its standard input closes. It has the test contract of the
//! binding (echo, fail, sleep, spikes): each operation but `fail` returns the request body and
//! arrays, and `sleep` first waits `seconds`. Each execution appends the body as one line to
//! NCP_EXECUTION_LOG, if set.
use ncp::{Contract, Decoded, Handler, Owner, Reply};
use std::io::{Read, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use zenoh::Wait;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{},"sleep":{},"spikes":{}},"streams":{}}"#;

struct Echo {
    log: Option<std::fs::File>,
}

impl Handler for Echo {
    fn validate(&mut self, _op: &str, _request: &Decoded) -> Result<(), String> {
        Ok(())
    }
    fn execute(
        &mut self,
        op: &str,
        request: &Decoded,
    ) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        if let Some(log) = self.log.as_mut() {
            writeln!(log, "{}", request.message["body"])?;
        }
        if op == "fail" {
            return Err("requested failure".into());
        }
        if op == "sleep" {
            let seconds = request.message["body"]["seconds"].as_f64().unwrap_or(0.0);
            std::thread::sleep(std::time::Duration::from_secs_f64(seconds));
        }
        Ok(Reply {
            body: request.message["body"].clone(),
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
    let make_owner = || {
        let log = log_path.as_ref().map(|path| {
            std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(path)
                .expect("execution log")
        });
        Owner::new(
            &contract.application,
            &contract.identity,
            Echo { log },
            contract.operations.clone(),
            ncp::MAX_BOUND,
        )
    };
    let mut server = ncp_zenoh::Server::declare(&session, service, make_owner, Default::default())?;
    println!("ready");
    std::io::stdout().flush()?;
    let stop = Arc::new(AtomicBool::new(false));
    let watcher = Arc::clone(&stop);
    std::thread::spawn(move || {
        let _ = std::io::stdin().read_to_end(&mut Vec::new());
        watcher.store(true, Ordering::Release);
    });
    server.run(&stop)?;
    drop(server);
    session.close().wait()?;
    Ok(())
}
