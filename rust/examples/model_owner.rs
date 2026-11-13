//! The Rust owner of model/conformance.py. It drives the owner state machine directly, as the
//! harness drives the Python owner, so that the harness can compare both with the Lean model.
//!
//! Commands on standard input, each answered on standard output:
//!   `n`                     a new owner with no session; answer `k`
//!   `s`                     stop the owner (`Owner::stop`); answer `k`
//!   `r` LENGTH FRAME        a request frame (LENGTH: 4 bytes, big-endian); answer LENGTH FRAME
//!                           with the response, or LENGTH 0 if the frame is not a request
//!
//! The application is the harness's: a body with `"bad": true` is declined, one with
//! `"fail": true` fails, one with `"big": true` returns a result too large for the session, and
//! an `open` with the run `"refuse"` is refused.
use ncp::{
    declined, events, AppError, Array, Contract, Dtype, Handler, Invalid, OpenInfo, Owner, Refused,
    Reply, Request, HANDSHAKE_BOUND,
};
use serde_json::{json, Map, Value};
use std::io::{self, Read, Write};
use std::sync::Arc;

const CONTRACT: &[u8] = br#"{"ncp_contract":1,"application":"model","version":"1","operations":{"step":{}},"streams":{}}"#;

struct Model;

impl Handler for Model {
    fn open(&mut self, info: &OpenInfo<'_>) -> Result<Map<String, Value>, Refused> {
        if info.run == Some("refuse") {
            return Err(Refused("refused by the harness".into()));
        }
        Ok(Map::new())
    }

    fn validate(&mut self, request: &Request<'_>) -> Result<(), Invalid> {
        if request.body["bad"] == true {
            return Err(declined("bad body"));
        }
        Ok(())
    }

    fn execute(&mut self, request: &Request<'_>) -> Result<Reply, AppError> {
        if request.body["fail"] == true {
            return Err("injected failure".into());
        }
        if request.body["big"] == true {
            let blob = Array::new(Dtype::U8, vec![70_000], vec![0; 70_000])?;
            return Ok(Reply {
                body: json!({"blob": blob.reference(0)}),
                arrays: vec![blob],
            });
        }
        Ok(json!({"seq": request.body["seq"]}).into())
    }
}

fn main() -> io::Result<()> {
    let contract = Contract::from_bytes(CONTRACT.to_vec()).map_err(io::Error::other)?;
    let new_owner = || {
        Owner::new(contract.clone(), Model)
            .with_max_bound(HANDSHAKE_BOUND)
            .with_observer(Arc::new(events::Silent))
    };
    let mut owner = new_owner();
    let mut input = io::stdin().lock();
    let mut output = io::BufWriter::new(io::stdout().lock());
    let mut command = [0u8; 1];
    loop {
        match input.read_exact(&mut command) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::UnexpectedEof => return Ok(()),
            Err(e) => return Err(e),
        }
        match command[0] {
            b'n' => {
                owner = new_owner();
                output.write_all(b"k")?;
            }
            b's' => {
                owner.stop();
                output.write_all(b"k")?;
            }
            b'r' => {
                let mut length = [0u8; 4];
                input.read_exact(&mut length)?;
                let mut frame = vec![0u8; u32::from_be_bytes(length) as usize];
                input.read_exact(&mut frame)?;
                match owner.handle(frame) {
                    Ok(response) => {
                        output.write_all(&(response.len() as u32).to_be_bytes())?;
                        output.write_all(&response)?;
                    }
                    Err(_) => output.write_all(&0u32.to_be_bytes())?,
                }
            }
            other => {
                return Err(io::Error::other(format!("unknown command {other:#04x}")));
            }
        }
        output.flush()?;
    }
}
