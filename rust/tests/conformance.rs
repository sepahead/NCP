//! Run the shared conformance vectors (conformance/vectors.json) against the Rust SDK.

use ncp::frame::{self, HANDSHAKE_BOUND, MAX_BOUND};
use ncp::{Contract, Decoded, Delivery, Handler, Owner, Reply, Subscriber};
use serde_json::{json, Value};

fn vectors() -> Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../conformance/vectors.json");
    serde_json::from_slice(&std::fs::read(path).expect("read vectors")).expect("parse vectors")
}

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len()).step_by(2).map(|i| u8::from_str_radix(&text[i..i + 2], 16).expect("hex")).collect()
}

struct Conformance;

impl Handler for Conformance {
    fn validate(&mut self, op: &str, request: &Decoded) -> Result<(), String> {
        if op == "step" && request.message["body"]["invalid"] == true {
            return Err("invalid".into());
        }
        Ok(())
    }
    fn execute(&mut self, op: &str, request: &Decoded) -> Result<Reply, Box<dyn std::error::Error + Send + Sync>> {
        let body = &request.message["body"];
        match op {
            "fail" => Err("fail".into()),
            "big" => Ok(json!({"blob": "z".repeat(body["size"].as_u64().unwrap_or(0) as usize)}).into()),
            _ => Ok(json!({"echo": body}).into()),
        }
    }
}

#[test]
fn frames() {
    let vectors = vectors();
    for case in vectors["frames"].as_array().expect("frames") {
        let name = case["name"].as_str().unwrap_or_default();
        let bound = case["bound"].as_u64().expect("bound") as usize;
        let result = frame::decode(unhex(case["frame"].as_str().expect("frame")), bound);
        if case["valid"] == true {
            let decoded = result.unwrap_or_else(|e| panic!("{name}: rejected a valid frame: {e}"));
            assert_eq!(decoded.message, case["message"], "{name}: message");
            assert_eq!(decoded.identity, case["identity"].as_str().unwrap_or_default(), "{name}: identity");
            let arrays: Vec<String> = (0..decoded.arrays.len()).map(|i| frame::hex(decoded.array_bytes(i).unwrap_or_default())).collect();
            let expected: Vec<String> = case["arrays"].as_array().expect("arrays").iter().map(|v| v.as_str().unwrap_or_default().to_owned()).collect();
            assert_eq!(arrays, expected, "{name}: arrays");
        } else {
            assert!(result.is_err(), "{name}: accepted an invalid frame");
        }
    }
}

#[test]
fn scenarios() {
    let vectors = vectors();
    let contract = Contract::from_bytes(vectors["contract"].as_str().expect("contract").as_bytes().to_vec()).expect("contract");
    assert_eq!(contract.identity, vectors["contract_identity"].as_str().unwrap_or_default());
    let session = vectors["session"].as_str().expect("session");
    for scenario in vectors["scenarios"].as_array().expect("scenarios") {
        let name = scenario["name"].as_str().unwrap_or_default();
        let mut owner = Owner::new("conformance", &contract.identity, Conformance, contract.operations.clone(), HANDSHAKE_BOUND);
        let mut history: Vec<String> = Vec::new();
        let mut frames: Vec<Vec<u8>> = Vec::new();
        let mut responses: Vec<Vec<u8>> = Vec::new();
        for (index, step) in scenario["steps"].as_array().expect("steps").iter().enumerate() {
            let request = if let Some(repeat) = step["repeat"].as_u64() {
                frames[repeat as usize].clone()
            } else {
                let body = if let Some(spec) = step.get("open") {
                    let mut body = json!({"application": spec.get("application").cloned().unwrap_or(json!("conformance")),
                                          "contract": spec.get("contract").cloned().unwrap_or(json!(contract.identity)),
                                          "bound": spec.get("bound").cloned().unwrap_or(Value::Null)});
                    if let Some(omit) = spec.get("omit").and_then(Value::as_str) {
                        body.as_object_mut().map(|o| o.remove(omit));
                    }
                    body
                } else {
                    step.get("body").cloned().unwrap_or(json!({}))
                };
                let ack = match step["ack"].as_str() {
                    Some("last") => history.last().cloned().map(Value::from).unwrap_or(Value::Null),
                    Some("stale") => history.len().checked_sub(2).map(|i| Value::from(history[i].clone())).unwrap_or(Value::Null),
                    Some("other") => Value::from("0".repeat(64)),
                    _ => Value::Null,
                };
                let session = if step["session"] == "other" { ncp::random_session() } else { session.to_owned() };
                frame::encode(&json!({"ncp": step.get("ncp").cloned().unwrap_or(json!(2)), "session": session,
                                       "seq": step["seq"], "op": step["op"], "ack": ack, "body": body}), &[]).expect("encode")
            };
            let response = owner.handle(request.clone()).expect("not a bad frame").to_vec();
            let message = frame::decode(response.clone(), MAX_BOUND).expect("response").message;
            let observed = json!([message["outcome"], message["code"]]);
            assert_eq!(observed, step["expect"], "{name}, step {index}");
            if let Some(repeat) = step["repeat"].as_u64() {
                if step["expect"][0] != "rejected" {
                    assert_eq!(response, responses[repeat as usize], "{name}, step {index}: repeat returned different bytes");
                }
            }
            if let Some(bound) = step.get("open_bound") {
                assert_eq!(&message["body"]["bound"], bound, "{name}, step {index}: open bound");
            }
            if message["outcome"] != "rejected" && step.get("repeat").is_none() {
                history.push(frame::identity(&response));
            }
            frames.push(request);
            responses.push(response);
        }
    }
}

#[test]
fn streams() {
    let vectors = vectors();
    let mut subscriber = Subscriber::new([vectors["contract_identity"].as_str().unwrap_or_default().to_owned()]);
    for (index, case) in vectors["streams"].as_array().expect("streams").iter().enumerate() {
        let (delivery, _) = subscriber.receive(unhex(case["frame"].as_str().unwrap_or_default()));
        let (status, lost) = match delivery {
            Delivery::Accepted { lost } => ("accepted", lost),
            Delivery::Repeat => ("repeat", 0),
            Delivery::BrokenChain => ("broken_chain", 0),
            Delivery::UnknownContract => ("unknown_contract", 0),
            Delivery::BadFrame => ("bad_frame", 0),
        };
        assert_eq!((status, lost), (case["status"].as_str().unwrap_or_default(), case["lost"].as_u64().unwrap_or(0)), "stream case {index}");
    }
}
