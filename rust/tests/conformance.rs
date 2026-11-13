//! The shared conformance vectors (conformance/vectors.json) against the Rust SDK: every part
//! that the Python SDK runs, with the same expectations.

use ncp::client::{self, ClientState, RequestOptions, TimeoutAction};
use ncp::contract::{check, compile_schema};
use ncp::frame::{self, Array, Dtype, Key, Verify, HANDSHAKE_BOUND, MAX_BOUND};
use ncp::messages::{check_request, check_response, check_stream_message, foreign};
use ncp::{
    declined, AppError, Contract, Delivery, Error, Handler, Invalid, Owner, Reply, Request,
    Subscriber,
};
use serde_json::{json, Map, Value};
use std::path::PathBuf;

fn vectors() -> Value {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../conformance/vectors.json");
    serde_json::from_slice(&std::fs::read(path).expect("vectors")).expect("vectors JSON")
}

fn bytes(hex: &str) -> Vec<u8> {
    (0..hex.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).expect("hex"))
        .collect()
}

/// A frame of the vectors: hexadecimal, or {"parts": [[HEX, COUNT], ...]}, the bytes of each HEX
/// repeated COUNT times, in order (conformance/generate.py stores large frames so).
fn frame_of(value: &Value) -> Vec<u8> {
    if let Some(hex) = value.as_str() {
        return bytes(hex);
    }
    let mut frame = Vec::new();
    for part in value["parts"].as_array().expect("parts") {
        let piece = bytes(part[0].as_str().expect("part"));
        for _ in 0..part[1].as_u64().expect("count") {
            frame.extend_from_slice(&piece);
        }
    }
    frame
}

/// JSON equality that keeps integers and other numbers apart, and -0.0 apart from 0.0.
fn same(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Number(x), Value::Number(y)) => {
            let integer = |n: &serde_json::Number| n.is_u64() || n.is_i64();
            if integer(x) != integer(y) {
                return false;
            }
            if integer(x) {
                return x == y;
            }
            let (p, q) = (
                x.as_f64().unwrap_or(f64::NAN),
                y.as_f64().unwrap_or(f64::NAN),
            );
            p == q && p.is_sign_negative() == q.is_sign_negative()
        }
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(p, q)| same(p, q))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len() && x.iter().all(|(k, v)| y.get(k).is_some_and(|w| same(v, w)))
        }
        _ => a == b,
    }
}

#[test]
fn frames() {
    let mut failures = Vec::new();
    for case in vectors()["frames"].as_array().expect("frames") {
        let name = case["name"].as_str().unwrap_or_default();
        let bound = case["bound"].as_u64().expect("bound") as usize;
        let result = frame::decode(frame_of(&case["frame"]), bound);
        match (case["valid"].as_bool().expect("valid"), result) {
            (false, Ok(_)) => failures.push(format!("{name}: accepted, must be a bad frame")),
            (true, Err(error)) => failures.push(format!("{name}: rejected ({})", error.0)),
            (true, Ok(decoded)) => {
                let arrays: Vec<Value> = (0..decoded.arrays.len())
                    .map(|i| Value::from(frame::hex(decoded.array_bytes(i).unwrap_or_default())))
                    .collect();
                // A large frame's vector omits its message; the identity checks it.
                let message_ok =
                    case.get("message").is_none() || same(&decoded.message, &case["message"]);
                if !message_ok
                    || decoded.identity != case["identity"].as_str().unwrap_or_default()
                    || Value::from(arrays) != case["arrays"]
                {
                    failures.push(format!("{name}: another message, identity, or arrays"));
                }
            }
            (false, Err(_)) => {}
        }
    }
    assert!(failures.is_empty(), "{failures:#?}");
}

#[test]
fn messages() {
    let mut failures = Vec::new();
    for case in vectors()["messages"].as_array().expect("messages") {
        let message = frame::decode(frame_of(&case["frame"]), MAX_BOUND)
            .expect("decodes")
            .message;
        let accepted = match case["kind"].as_str() {
            Some("request") => check_request(&message).is_ok(),
            Some("response") => check_response(&message).is_ok(),
            Some("foreign") => foreign(&message),
            _ => check_stream_message(&message).is_ok(),
        };
        if accepted != case["valid"].as_bool().expect("valid") {
            failures.push(format!("{}: {accepted}", case["name"]));
        }
    }
    assert!(failures.is_empty(), "{failures:#?}");
}

#[test]
fn authenticated_frames() {
    let all = vectors();
    let key = Key::new(bytes(all["key"].as_str().expect("key"))).expect("key");
    for case in all["auth"].as_array().expect("auth") {
        let frame_bytes = frame_of(&case["frame"]);
        let with = frame::decode_verified(frame_bytes.clone(), MAX_BOUND, Verify::Key(&key));
        let without = frame::decode(frame_bytes, MAX_BOUND);
        assert_eq!(
            with.is_ok(),
            case["valid_with_key"] == true,
            "{}",
            case["name"]
        );
        assert_eq!(
            without.is_ok(),
            case["valid_without_key"] == true,
            "{}",
            case["name"]
        );
        if let Some(decoded) = with.ok().or(without.ok()) {
            assert_eq!(
                decoded.identity,
                case["identity"].as_str().unwrap_or_default()
            );
        }
    }
}

/// The handler of the vectors' "handler" member.
#[derive(Default)]
struct VectorHandler {
    flaky_seen: bool,
}

impl Handler for VectorHandler {
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
            "big" => {
                let size = request.body["size"].as_u64().unwrap_or(0) as usize;
                Ok(json!({"blob": "z".repeat(size)}).into())
            }
            _ => Ok(Reply {
                body: json!({"echo": request.body}),
                arrays: request.owned_arrays(),
            }),
        }
    }
}

/// A body with each {"array": DTYPE, "values": [...]} replaced by an array reference.
fn body_of(value: &Value, arrays: &mut Vec<Array>) -> Value {
    match value {
        Value::Object(object)
            if object.len() == 2
                && object.contains_key("array")
                && object.contains_key("values") =>
        {
            let dtype = Dtype::parse(object["array"].as_str().unwrap_or_default()).expect("dtype");
            let values = object["values"].as_array().expect("values");
            let array = match dtype {
                Dtype::F64 => Array::from_f64(
                    &values
                        .iter()
                        .map(|v| v.as_f64().unwrap_or(0.0))
                        .collect::<Vec<_>>(),
                ),
                Dtype::F32 => Array::from_f32(
                    &values
                        .iter()
                        .map(|v| v.as_f64().unwrap_or(0.0) as f32)
                        .collect::<Vec<_>>(),
                ),
                other => panic!("the vectors use no arrays of {other:?}"),
            };
            let reference = array.reference(arrays.len());
            arrays.push(array);
            reference
        }
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(k, v)| (k.clone(), body_of(v, arrays)))
                .collect(),
        ),
        Value::Array(items) => Value::Array(items.iter().map(|v| body_of(v, arrays)).collect()),
        other => other.clone(),
    }
}

fn kept(message: &Value) -> bool {
    matches!(message["outcome"].as_str(), Some("ok" | "declined"))
        || (message["outcome"] == "ended"
            && matches!(
                message["code"].as_str(),
                Some("owner_failure" | "result_too_large")
            ))
}

fn new_owner(contract: &Contract, stopping: bool) -> Owner<VectorHandler> {
    let mut owner = Owner::new(contract.clone(), VectorHandler::default())
        .with_max_bound(HANDSHAKE_BOUND)
        .with_observer(std::sync::Arc::new(ncp::events::Silent));
    if stopping {
        owner.stop();
    }
    owner
}

#[test]
fn owner_scenarios() {
    let all = vectors();
    let contract = Contract::from_bytes(
        all["contract"]
            .as_str()
            .expect("contract")
            .as_bytes()
            .to_vec(),
    )
    .expect("contract");
    assert_eq!(
        contract.identity,
        all["contract_identity"].as_str().unwrap_or_default()
    );
    let mut failures = Vec::new();
    for scenario in all["scenarios"].as_array().expect("scenarios") {
        let name = scenario["name"].as_str().unwrap_or_default();
        let mut owner = new_owner(&contract, false);
        let mut history: Vec<String> = Vec::new();
        let mut frames: Vec<Option<Vec<u8>>> = Vec::new();
        let mut responses: Vec<Option<Vec<u8>>> = Vec::new();
        for (index, step) in scenario["steps"]
            .as_array()
            .expect("steps")
            .iter()
            .enumerate()
        {
            if step.get("stop").is_some() {
                owner.stop();
                frames.push(None);
                responses.push(None);
                continue;
            }
            if let Some(kind) = step.get("owner") {
                owner = new_owner(&contract, kind == "stopping");
                history.clear();
                frames.push(None);
                responses.push(None);
                continue;
            }
            let frame_bytes = if let Some(repeat) = step.get("repeat") {
                frames[repeat.as_u64().expect("repeat") as usize]
                    .clone()
                    .expect("a frame")
            } else {
                let mut arrays = Vec::new();
                let body = if let Some(spec) = step.get("open") {
                    let mut body = json!({
                        "application": spec.get("application").cloned().unwrap_or(json!("conformance")),
                        "contract": spec.get("contract").cloned().unwrap_or(json!(contract.identity)),
                        "bound": spec.get("bound").cloned().unwrap_or(Value::Null),
                    });
                    if let Some(omit) = spec.get("omit").and_then(Value::as_str) {
                        body.as_object_mut().expect("object").remove(omit);
                    }
                    for member in ["run", "features", "extra"] {
                        if let Some(value) = spec.get(member) {
                            body[member] = value.clone();
                        }
                    }
                    body
                } else {
                    body_of(step.get("body").unwrap_or(&json!({})), &mut arrays)
                };
                let ack = match step["ack"].as_str() {
                    Some("last") => history.last().cloned().map_or(Value::Null, Value::from),
                    Some("stale") => history
                        .len()
                        .checked_sub(2)
                        .map_or(Value::Null, |i| Value::from(history[i].clone())),
                    Some("other") => Value::from("0".repeat(64)),
                    _ => Value::Null,
                };
                let session = if step.get("session").is_some_and(|s| s == "other") {
                    ncp::random_session()
                } else {
                    all["session"].as_str().unwrap_or_default().to_owned()
                };
                let mut message = json!({"ncp": step.get("ncp").cloned().unwrap_or(json!(2)), "session": session,
                                         "seq": step["seq"], "op": step["op"], "ack": ack, "body": body});
                if let Value::Object(members) = &mut message {
                    for member in step
                        .get("drop")
                        .and_then(Value::as_array)
                        .into_iter()
                        .flatten()
                    {
                        members.remove(member.as_str().unwrap_or_default());
                    }
                    for (name, value) in step
                        .get("extra")
                        .and_then(Value::as_object)
                        .into_iter()
                        .flatten()
                    {
                        members.insert(name.clone(), value.clone());
                    }
                }
                frame::encode(&message, &arrays).expect("encode")
            };
            let response = owner
                .handle(frame_bytes.clone())
                .expect("a request")
                .to_vec();
            let message = frame::decode(response.clone(), MAX_BOUND)
                .expect("response")
                .message;
            let observed = json!([message["outcome"], message["code"]]);
            if observed != step["expect"] {
                failures.push(format!(
                    "{name} step {index}: expected {}, observed {observed}",
                    step["expect"]
                ));
            }
            if let Some(repeat) = step.get("repeat") {
                let original = responses[repeat.as_u64().expect("repeat") as usize]
                    .clone()
                    .expect("a response");
                let first = frame::decode(original.clone(), MAX_BOUND)
                    .expect("response")
                    .message;
                if kept(&first)
                    && json!([first["outcome"], first["code"]]) == step["expect"]
                    && response != original
                {
                    failures.push(format!(
                        "{name} step {index}: a copy of an admitted request got other bytes"
                    ));
                }
            }
            if let Some(bound) = step.get("open_bound") {
                if &message["body"]["bound"] != bound {
                    failures.push(format!("{name} step {index}: open bound"));
                }
            }
            if let Some(features) = step.get("open_features") {
                if &message["body"]["features"] != features {
                    failures.push(format!("{name} step {index}: open features"));
                }
            }
            for member in step
                .get("body_has")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
            {
                if message["body"]
                    .get(member.as_str().unwrap_or_default())
                    .is_none()
                {
                    failures.push(format!("{name} step {index}: no member {member}"));
                }
            }
            if message["outcome"] == "ok" && step.get("op").is_some_and(|op| op == "open") {
                let nonce = message["body"]["nonce"].as_str().unwrap_or_default();
                if nonce.len() != 32 {
                    failures.push(format!("{name} step {index}: no nonce"));
                }
            }
            if kept(&message) && step.get("repeat").is_none() {
                history.push(frame::identity(&response));
            }
            frames.push(Some(frame_bytes));
            responses.push(Some(response));
        }
    }
    assert!(failures.is_empty(), "{failures:#?}");
}

fn substitute(value: &Value, variant: &[Value], bodies: &Value) -> Value {
    match value {
        Value::String(s) if s == "$code" => {
            let key = variant[0].as_str().unwrap_or_default();
            bodies
                .get(key)
                .cloned()
                .unwrap_or_else(|| variant[0].clone())
        }
        Value::String(s) if s == "$executed" => variant[1].clone(),
        Value::Object(object) => Value::Object(
            object
                .iter()
                .map(|(k, v)| (k.clone(), substitute(v, variant, bodies)))
                .collect(),
        ),
        Value::Array(items) => Value::Array(
            items
                .iter()
                .map(|v| substitute(v, variant, bodies))
                .collect(),
        ),
        other => other.clone(),
    }
}

fn verdict_of(outcome: &Option<Result<ncp::Decoded, Error>>) -> Value {
    match outcome {
        None => json!({"kind": "ignored"}),
        Some(Ok(_)) => json!({"kind": "ok"}),
        Some(Err(Error::Declined { code, .. })) => {
            json!({"kind": "declined", "code": code, "executed": "no"})
        }
        Some(Err(Error::Rejected { code, .. })) => json!({"kind": "rejected", "code": code}),
        Some(Err(Error::Ended { code, executed, .. })) => {
            json!({"kind": "ended", "code": code, "executed": executed.as_str()})
        }
        Some(Err(Error::Usage(reason))) => json!({"kind": "usage", "reason": reason}),
    }
}

fn reply(state: &ClientState, spec: &Value, to: &str) -> Vec<u8> {
    let pending = state.pending.as_ref().expect("a pending request");
    if to == "garbage" {
        return b"junk that is not a frame".to_vec();
    }
    let mut message = json!({"ncp": 2, "session": state.session, "seq": pending.seq,
                             "request": pending.identity, "outcome": spec["outcome"],
                             "code": spec["code"], "body": spec["body"]});
    match to {
        "other_seq" => message["seq"] = json!(pending.seq + 1),
        "other_request" => message["request"] = json!("0".repeat(64)),
        "other_session" => message["session"] = json!(ncp::random_session()),
        "nameless" => {
            message["session"] = Value::Null;
            message["seq"] = Value::Null;
            message["request"] = Value::Null;
        }
        "nameless_bound" => {
            message["session"] = Value::Null;
            message["seq"] = Value::Null;
            message["request"] = Value::Null;
            message["body"] = json!({"session": state.session, "kept": state.ack});
        }
        _ => {}
    }
    frame::encode(&message, &[]).expect("encode")
}

#[test]
fn client_rules() {
    let all = vectors();
    let contract = Contract::from_bytes(
        all["contract"]
            .as_str()
            .expect("contract")
            .as_bytes()
            .to_vec(),
    )
    .expect("contract");
    let mut failures = Vec::new();
    for case in all["clients"].as_array().expect("clients") {
        let variants: Vec<Vec<Value>> = case
            .get("cases")
            .and_then(Value::as_array)
            .map(|v| {
                v.iter()
                    .map(|c| c.as_array().cloned().unwrap_or_default())
                    .collect()
            })
            .unwrap_or_else(|| vec![vec![]]);
        for variant in variants {
            let name = format!("{} {:?}", case["name"], variant);
            let lossy = case["lossy"] == true;
            let retries = case.get("retries").and_then(Value::as_u64).unwrap_or(3) as u32;
            let steps = substitute(
                &case["steps"],
                &variant,
                case.get("bodies").unwrap_or(&json!({})),
            );
            let mut state = client::new_state(
                &contract,
                Some(all["session"].as_str().unwrap_or_default().to_owned()),
                HANDSHAKE_BOUND,
            );
            let mut last: Option<String> = None;
            let mut first_open: Option<Vec<u8>> = None;
            for (index, step) in steps.as_array().expect("steps").iter().enumerate() {
                let at = format!("{name} step {index}");
                if let Some(action) = step.get("do").and_then(Value::as_str) {
                    let op = match action {
                        "open" => "open",
                        "close" => "close",
                        "ping" => "ncp.ping",
                        _ => step["op"].as_str().unwrap_or_default(),
                    };
                    let body = step.get("body").cloned().unwrap_or(Value::Null);
                    match client::request(&state, op, body, &[], &RequestOptions::default()) {
                        Err(_) => {
                            if step["expect"] != "usage" {
                                failures.push(format!("{at}: refused, expected a frame"));
                            }
                        }
                        Ok((next, frame_bytes)) => {
                            state = next;
                            if step["expect"] != "sent" {
                                failures.push(format!("{at}: sent, expected a refusal"));
                                continue;
                            }
                            if op == "open" {
                                if step.get("same_as_first") == Some(&json!(true))
                                    && first_open.as_deref() != Some(frame_bytes.as_slice())
                                {
                                    failures.push(format!("{at}: the open again is another frame"));
                                }
                                if first_open.is_none() {
                                    first_open = Some(frame_bytes.to_vec());
                                }
                            }
                            if let Some(want) = step.get("request") {
                                let sent = frame::decode(frame_bytes.to_vec(), MAX_BOUND)
                                    .expect("request")
                                    .message;
                                if sent["seq"] != want["seq"]
                                    || (want["ack"] == "last"
                                        && sent["ack"].as_str() != last.as_deref())
                                {
                                    failures.push(format!(
                                        "{at}: request seq {} ack {}",
                                        sent["seq"], sent["ack"]
                                    ));
                                }
                            }
                        }
                    }
                    continue;
                }
                let observed = if let Some(spec) = step.get("reply") {
                    let frame_bytes = reply(&state, spec, step["to"].as_str().unwrap_or("own"));
                    let identity = frame::identity(&frame_bytes);
                    let (next, outcome) =
                        client::receive(&state, frame_bytes, lossy, Verify::Digest);
                    state = next;
                    if matches!(outcome, Some(Ok(_)) | Some(Err(Error::Declined { .. }))) {
                        last = Some(identity);
                    }
                    verdict_of(&outcome)
                } else if step.get("timeout").is_some() {
                    let (next, action) = client::time_out(&state, lossy, retries);
                    state = next;
                    match action {
                        Some(TimeoutAction::Resend(_)) => json!({"kind": "resend"}),
                        Some(TimeoutAction::Done(error)) => verdict_of(&Some(Err(error))),
                        None => json!({"kind": "ignored"}),
                    }
                } else {
                    let (next, error) = client::closed(&state, "");
                    state = next;
                    verdict_of(&error.map(Err))
                };
                if observed != step["expect"] {
                    failures.push(format!(
                        "{at}: expected {}, observed {observed}",
                        step["expect"]
                    ));
                }
                if let Some(want) = step.get("state") {
                    let got =
                        json!({"seq": state.seq, "opened": state.opened, "ended": state.ended});
                    if &got != want {
                        failures.push(format!("{at}: state {got}, expected {want}"));
                    }
                }
            }
        }
    }
    assert!(failures.is_empty(), "{failures:#?}");
}

#[test]
fn streams() {
    let all = vectors();
    let mut subscriber = Subscriber::new([all["contract_identity"]
        .as_str()
        .unwrap_or_default()
        .to_owned()]);
    for (index, case) in all["streams"]
        .as_array()
        .expect("streams")
        .iter()
        .enumerate()
    {
        let (delivery, _) = subscriber.receive(frame_of(&case["frame"]));
        let (lost, end) = match delivery {
            Delivery::Accepted { lost, end } => (lost, end),
            Delivery::Joined { end } => (0, end),
            _ => (0, false),
        };
        assert_eq!(
            json!([delivery.status(), lost, end]),
            json!([case["status"], case["lost"], case["end"]]),
            "stream case {index}"
        );
    }
}

#[test]
fn transcripts() {
    let directory = std::env::temp_dir().join(format!("ncp-conformance-{}", std::process::id()));
    std::fs::create_dir_all(&directory).expect("directory");
    let mut failures = Vec::new();
    for (index, case) in vectors()["transcripts"]
        .as_array()
        .expect("transcripts")
        .iter()
        .enumerate()
    {
        let path = directory.join(format!("case-{index}.ncpt"));
        std::fs::write(&path, bytes(case["file"].as_str().expect("file"))).expect("write");
        let key = case["key"]
            .as_str()
            .map(|k| Key::new(bytes(k)).expect("key"));
        let report = ncp::transcript::verify(&path, key.as_ref()).expect("readable");
        let summary = json!({
            "ok": report.ok(),
            "version": report.version,
            "closed": report.closed,
            "truncated": report.truncated_at.is_some(),
            "chain_ok": report.chain_ok,
            "sessions": report.sessions.iter().map(|s| json!({
                "role": s.role, "requests": s.requests, "declined": s.declined,
                "complete": s.complete, "problems": !s.problems.is_empty(),
            })).collect::<Vec<_>>(),
        });
        if summary != case["expect"] {
            failures.push(format!(
                "{}: {summary}, expected {}",
                case["name"], case["expect"]
            ));
        }
    }
    let _ = std::fs::remove_dir_all(&directory);
    assert!(failures.is_empty(), "{failures:#?}");
}

#[test]
fn contracts() {
    for case in vectors()["contracts"].as_array().expect("contracts") {
        let accepted = Contract::from_bytes(
            case["document"]
                .as_str()
                .expect("document")
                .as_bytes()
                .to_vec(),
        )
        .is_ok();
        assert_eq!(accepted, case["valid"] == true, "{}", case["name"]);
    }
}

#[test]
fn schemas() {
    for (index, case) in vectors()["schemas"]
        .as_array()
        .expect("schemas")
        .iter()
        .enumerate()
    {
        compile_schema(&case["schema"], "$").expect("a valid schema");
        let message = frame::decode(frame_of(&case["frame"]), MAX_BOUND)
            .expect("frame")
            .message;
        let matches = check(&case["schema"], &message["value"], "$").is_none();
        assert_eq!(
            matches,
            case["valid"] == true,
            "schema case {index}: {}",
            case["schema"]
        );
    }
}

#[test]
fn the_conformance_owner_example_uses_the_vectors_contract() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let source =
        std::fs::read_to_string(root.join("examples/conformance_owner.rs")).expect("example");
    let contract = vectors()["contract"].as_str().expect("contract").to_owned();
    assert!(source.contains(&format!("r#\"{contract}\"#")));
}

#[test]
fn the_package_copy_of_the_vectors_is_the_same() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
    let a = std::fs::read(root.join("conformance/vectors.json")).expect("vectors");
    let b = std::fs::read(root.join("python/ncp/vectors.json")).expect("packaged vectors");
    assert_eq!(a, b);
    let _ = Map::<String, Value>::new();
}
