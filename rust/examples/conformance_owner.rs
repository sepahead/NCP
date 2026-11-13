//! The owner of the conformance vectors (conformance/vectors.json, member "handler"), serving
//! one session on standard input and output: `python -m ncp conformance --owner PATH`.
use ncp::{declined, events, AppError, Contract, Handler, Invalid, Owner, Reply, Request};
use serde_json::json;
use std::sync::Arc;

/// The contract of the vectors; the Rust conformance test checks that it is the same text.
const CONTRACT: &str = r#"{"ncp_contract":1,"application":"conformance","version":"2","operations":{"step":{},"fail":{},"big":{},"flaky":{},"typed":{"ncp.schema":{"request":{"type":"object","required":["n"],"properties":{"n":{"type":"integer","minimum":0,"maximum":9},"v":{"ncp.array":{"dtype":"f64","shape":[null]}}},"additionalProperties":false}}}},"streams":{"sensor":{}}}"#;

#[derive(Default)]
struct Vectors {
    flaky_seen: bool,
}

impl Handler for Vectors {
    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        if request.op == "step" && request.body["invalid"] == true {
            return Err(declined("invalid"));
        }
        if request.op == "flaky" && !self.flaky_seen {
            self.flaky_seen = true;
            return Err(declined("the first validation declines"));
        }
        Ok(())
    }
    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        match request.op {
            "fail" => Err("fail".into()),
            "big" => Ok(
                json!({"blob": "z".repeat(request.body["size"].as_u64().unwrap_or(0) as usize)})
                    .into(),
            ),
            _ => Ok(Reply {
                body: json!({"echo": request.body}),
                arrays: request.owned_arrays(),
            }),
        }
    }
}

fn main() {
    let contract =
        Contract::from_bytes(CONTRACT.as_bytes().to_vec()).expect("the vectors' contract");
    let mut owner = Owner::new(contract, Vectors::default())
        .with_max_bound(ncp::HANDSHAKE_BOUND)
        .with_observer(Arc::new(events::Silent));
    if let Err(error) = ncp::serve_stdio(&mut owner) {
        eprintln!("conformance owner: {error}");
        std::process::exit(1);
    }
}
