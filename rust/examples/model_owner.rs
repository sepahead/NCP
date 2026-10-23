//! The owner of model/conformance.py: model_owner [PORT | UNIX-SOCKET-PATH]. Prints "port N" or
//! "unix PATH", then serves one session per connection until it is stopped.
use ncp::{binding, Contract, Decoded, Handler, Owner, Reply, HANDSHAKE_BOUND};
use serde_json::json;
use std::io::Write;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}"#;

struct Model;

impl Handler for Model {
    fn validate(&mut self, _op: &str, request: &Decoded) -> Result<(), String> {
        if request.message["body"]["version"] == "bad" {
            return Err("bad version".into());
        }
        Ok(())
    }
    fn execute(&mut self, _op: &str, request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        let body = &request.message["body"];
        if body["fail"] == true {
            return Err("injected failure".into());
        }
        Ok(json!({"seq": body["seq"]}).into())
    }
}

fn serve_one<R: std::io::Read, W: std::io::Write>(contract: &Contract, channel: std::io::Result<ncp::StreamChannel<R, W>>) {
    let mut owner = Owner::new(&contract.application, &contract.identity, Model, contract.operations.clone(), HANDSHAKE_BOUND);
    if let Ok(mut channel) = channel {
        let _ = binding::serve(&mut owner, &mut channel);
    }
}

fn main() -> std::io::Result<()> {
    let argument = std::env::args().nth(1).unwrap_or_else(|| "0".into());
    let contract = Contract::from_bytes(CONTRACT.to_vec()).map_err(std::io::Error::other)?;
    if argument.contains('/') {
        let listener = std::os::unix::net::UnixListener::bind(&argument)?;
        println!("unix {argument}");
        std::io::stdout().flush()?;
        for stream in listener.incoming() {
            let stream = stream?;
            let contract = contract.clone();
            std::thread::spawn(move || serve_one(&contract, binding::unix_channel(stream)));
        }
        return Ok(());
    }
    let port: u16 = argument.parse().map_err(std::io::Error::other)?;
    let listener = binding::listen_tcp(("127.0.0.1", port), false)?;
    println!("port {}", listener.local_addr()?.port());
    std::io::stdout().flush()?;
    for stream in listener.incoming() {
        let stream = stream?;
        let contract = contract.clone();
        std::thread::spawn(move || serve_one(&contract, binding::tcp_channel(stream)));
    }
    Ok(())
}
