//! Bounded, non-executing data validation peer for independent SDK qualification.

use std::io;

use ncp_core::bounded_json::parse_value;
use ncp_core::local::{
    local_digest, local_profile_digest, read_local_frame, write_local_frame, LocalBinding,
    LocalCode, LocalError, LocalResponse,
};
use ncp_core::local_data::{BodyResult, NeuralProposal, RunPlan, Snapshot};
use serde::de::DeserializeOwned;
use serde_json::{json, Value};

fn typed<T: DeserializeOwned>(value: &Value) -> Result<T, LocalError> {
    serde_json::from_value(value.clone()).map_err(|_| LocalError(LocalCode::Wire))
}

fn evaluate(value: &Value) -> Result<Value, LocalError> {
    let kind = value
        .get("kind")
        .and_then(Value::as_str)
        .ok_or(LocalError(LocalCode::Wire))?;
    match kind {
        "profile" => Ok(json!({"digest": local_profile_digest()?})),
        "response" => {
            let binding: LocalBinding = typed(&value["binding"])?;
            let response: LocalResponse = typed(&value["body"])?;
            response.verify_integrity(&binding)?;
            Ok(json!({}))
        }
        "digest" => {
            let domain = value
                .get("domain")
                .and_then(Value::as_str)
                .ok_or(LocalError(LocalCode::Wire))?;
            Ok(json!({"digest": local_digest(domain, &value["body"])?}))
        }
        "plan" => {
            let plan: RunPlan = typed(&value["body"])?;
            Ok(json!({"digest": plan.digest()?}))
        }
        "snapshot" => {
            let plan: RunPlan = typed(&value["plan"])?;
            let snapshot: Snapshot = typed(&value["body"])?;
            snapshot.validate(&plan)?;
            Ok(json!({"digest": snapshot.snapshot_digest}))
        }
        "neural" => {
            let plan: RunPlan = typed(&value["plan"])?;
            let source: Snapshot = typed(&value["source"])?;
            let proposal: NeuralProposal = typed(&value["body"])?;
            proposal.validate(&plan, &source)?;
            Ok(json!({}))
        }
        "body" => {
            let plan: RunPlan = typed(&value["plan"])?;
            let result: BodyResult = typed(&value["body"])?;
            result.validate(&plan)?;
            Ok(json!({}))
        }
        _ => Err(LocalError(LocalCode::InvalidInput)),
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let (stdin, stdout) = (io::stdin(), io::stdout());
    let (mut reader, mut writer) = (stdin.lock(), stdout.lock());
    while let Some(bytes) = read_local_frame(&mut reader)? {
        let evaluated = parse_value(&bytes)
            .map_err(|_| LocalError(LocalCode::Wire))
            .and_then(|value| evaluate(&value));
        let response = match evaluated {
            Ok(value) => json!({"accepted": true, "result": value}),
            Err(error) => json!({"accepted": false, "code": error.0}),
        };
        write_local_frame(&mut writer, &serde_json::to_vec(&response)?)?;
    }
    Ok(())
}
