//! A lockstep owner for tests across the SDKs: a world whose position each step moves, behind the
//! lockstep profile, with one clock for all its sessions.
//!
//! lockstep_owner unix PATH   one session per connection; prints "ready unix:PATH" and serves
//!                            until standard input closes
use ncp::{events, AppError, Contract, Handler, Invalid, Lockstep, Owner, Reply, Request, Stepper};
use serde_json::json;
use std::io::Write;
use std::sync::Arc;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"world","version":"1","operations":{"step":{},"look":{}},"streams":{}}"#;

/// The world: a position that each step moves by `dx`.
#[derive(Default)]
struct World {
    position: i64,
}

impl Handler for World {
    fn validate(&mut self, _: &Request<'_>) -> Result<(), Invalid> {
        Ok(())
    }

    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        if request.op == "step" {
            self.position += request.body["dx"].as_i64().unwrap_or(0);
        }
        Ok(json!({"position": self.position}).into())
    }
}

impl Stepper for World {
    fn state(&self) -> Option<String> {
        Some(format!("p{}", self.position))
    }
}

fn main() -> std::io::Result<()> {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).map_err(std::io::Error::other)?;
    let args: Vec<String> = std::env::args().collect();
    let (Some("unix"), Some(path)) = (args.get(1).map(String::as_str), args.get(2)) else {
        eprintln!("usage: lockstep_owner unix PATH");
        std::process::exit(2);
    };
    let lockstep = Lockstep::new(World::default(), &["step"]);
    let mut server = ncp::serve_unix(
        path,
        move || {
            Owner::new(contract.clone(), lockstep.share()).with_observer(Arc::new(events::Silent))
        },
        ncp::Limits::default(),
    )?;
    println!("ready unix:{path}");
    std::io::stdout().flush()?;
    // Serve until standard input closes.
    let mut sink = Vec::new();
    let _ = std::io::Read::read_to_end(&mut std::io::stdin(), &mut sink);
    server.stop(std::time::Duration::from_secs(1));
    Ok(())
}
