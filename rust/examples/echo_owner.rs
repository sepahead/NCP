//! An echo owner over standard input and output, for tests and benchmarks.
use ncp::{Contract, Decoded, Handler, Owner, Reply};

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"echo","version":"1","operations":{"echo":{},"fail":{}},"streams":{}}"#;

struct Echo;

impl Handler for Echo {
    fn validate(&mut self, op: &str, request: &Decoded) -> Result<(), String> {
        if op == "echo" && request.message["body"]["invalid"] == true {
            return Err("invalid requested".into());
        }
        Ok(())
    }
    fn execute(&mut self, op: &str, request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        if op == "fail" {
            return Err("requested failure".into());
        }
        Ok(Reply { body: request.message["body"].clone(), arrays: request.owned_arrays() })
    }
}

fn main() {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).expect("contract");
    let mut owner = Owner::new(&contract.application, &contract.identity, Echo, contract.operations.clone(), ncp::MAX_BOUND);
    if let Err(error) = ncp::serve_stdio(&mut owner) {
        eprintln!("echo owner: {error}");
        std::process::exit(1);
    }
}
