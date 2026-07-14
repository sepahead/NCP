//! Cross-language canonical digest for state-mutating NCP requests.
//!
//! JSON text is not a stable digest input: object order, whitespace, numeric
//! spelling, and authority-lease renewal can differ without changing a mutation.
//! NCP therefore hashes a typed, length-prefixed semantic projection.  The
//! projection excludes the top-level `authority` authentication envelope and the
//! attempt-local `operation.request_digest` / `operation.retry` members.  Every
//! other member, including unknown extension members, is covered.

use crate::bounded_json::{MAX_FINITE_NUMBER_MAGNITUDE, MAX_NESTING_DEPTH};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::fmt;

/// Exact domain prefix for the NCP request-digest-v1 byte stream.
pub const REQUEST_DIGEST_DOMAIN_V1: &[u8] = b"ncp.request-digest.v1\0";

/// Projection output is bounded independently of caller allocation.  A legal
/// 1 MiB NCP JSON frame plus typed tags and length prefixes remains below 2 MiB.
pub const MAX_REQUEST_PROJECTION_BYTES: usize = 2_097_152;

const TAG_NULL: u8 = 0x00;
const TAG_FALSE: u8 = 0x01;
const TAG_TRUE: u8 = 0x02;
const TAG_NUMBER: u8 = 0x03;
const TAG_STRING: u8 = 0x04;
const TAG_ARRAY: u8 = 0x05;
const TAG_OBJECT: u8 = 0x06;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RequestDigestError {
    detail: String,
}

impl RequestDigestError {
    fn new(detail: impl Into<String>) -> Self {
        Self {
            detail: detail.into(),
        }
    }
}

impl fmt::Display for RequestDigestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "NCP-OP-001: {}", self.detail)
    }
}

impl std::error::Error for RequestDigestError {}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Location {
    Root,
    Operation,
    Nested,
}

fn push(output: &mut Vec<u8>, bytes: &[u8]) -> Result<(), RequestDigestError> {
    let next_len = output
        .len()
        .checked_add(bytes.len())
        .ok_or_else(|| RequestDigestError::new("canonical projection length overflow"))?;
    if next_len > MAX_REQUEST_PROJECTION_BYTES {
        return Err(RequestDigestError::new(
            "canonical request projection exceeds its byte budget",
        ));
    }
    output.extend_from_slice(bytes);
    Ok(())
}

fn push_byte(output: &mut Vec<u8>, byte: u8) -> Result<(), RequestDigestError> {
    push(output, &[byte])
}

fn push_len(output: &mut Vec<u8>, len: usize) -> Result<(), RequestDigestError> {
    let len = u64::try_from(len)
        .map_err(|_| RequestDigestError::new("canonical projection length is not u64"))?;
    push(output, &len.to_be_bytes())
}

fn encode_string(output: &mut Vec<u8>, value: &str) -> Result<(), RequestDigestError> {
    push_byte(output, TAG_STRING)?;
    push_len(output, value.len())?;
    push(output, value.as_bytes())
}

fn excluded(location: Location, key: &str) -> bool {
    matches!((location, key), (Location::Root, "authority"))
        || matches!(
            (location, key),
            (Location::Operation, "request_digest" | "retry")
        )
}

fn encode_object(
    output: &mut Vec<u8>,
    object: &Map<String, Value>,
    depth: usize,
    location: Location,
) -> Result<(), RequestDigestError> {
    let mut entries = object
        .iter()
        .filter(|(key, _)| !excluded(location, key))
        .collect::<Vec<_>>();
    entries.sort_by(|(left, _), (right, _)| left.as_bytes().cmp(right.as_bytes()));

    push_byte(output, TAG_OBJECT)?;
    push_len(output, entries.len())?;
    for (key, value) in entries {
        encode_string(output, key)?;
        let child_location = if location == Location::Root && key == "operation" {
            Location::Operation
        } else {
            Location::Nested
        };
        encode_value(output, value, depth + 1, child_location)?;
    }
    Ok(())
}

fn encode_value(
    output: &mut Vec<u8>,
    value: &Value,
    depth: usize,
    location: Location,
) -> Result<(), RequestDigestError> {
    if depth > MAX_NESTING_DEPTH {
        return Err(RequestDigestError::new(
            "canonical request projection exceeds the nesting-depth budget",
        ));
    }
    match value {
        Value::Null => push_byte(output, TAG_NULL),
        Value::Bool(false) => push_byte(output, TAG_FALSE),
        Value::Bool(true) => push_byte(output, TAG_TRUE),
        Value::Number(number) => {
            let number = number
                .as_f64()
                .filter(|number| number.is_finite() && number.abs() <= MAX_FINITE_NUMBER_MAGNITUDE);
            let number = number.ok_or_else(|| {
                RequestDigestError::new("canonical request contains an out-of-budget number")
            })?;
            push_byte(output, TAG_NUMBER)?;
            push(output, &number.to_bits().to_be_bytes())
        }
        Value::String(value) => encode_string(output, value),
        Value::Array(values) => {
            push_byte(output, TAG_ARRAY)?;
            push_len(output, values.len())?;
            for value in values {
                encode_value(output, value, depth + 1, Location::Nested)?;
            }
            Ok(())
        }
        Value::Object(object) => encode_object(output, object, depth, location),
    }
}

fn mutation_object(request: &Value) -> Result<&Map<String, Value>, RequestDigestError> {
    let object = request
        .as_object()
        .ok_or_else(|| RequestDigestError::new("mutation request must be a JSON object"))?;
    let kind = object
        .get("kind")
        .and_then(Value::as_str)
        .ok_or_else(|| RequestDigestError::new("mutation request kind is required"))?;
    if !matches!(kind, "step_request" | "run_request" | "close_session") {
        return Err(RequestDigestError::new(format!(
            "request kind {kind:?} is not a state-mutating lifecycle request"
        )));
    }
    if !object.get("operation").is_some_and(Value::is_object) {
        return Err(RequestDigestError::new(
            "mutation request operation must be an object",
        ));
    }
    Ok(object)
}

/// Return the exact request-digest-v1 projection bytes.
pub fn canonical_request_projection(request: &Value) -> Result<Vec<u8>, RequestDigestError> {
    let object = mutation_object(request)?;
    let mut output = Vec::with_capacity(REQUEST_DIGEST_DOMAIN_V1.len() + 512);
    push(&mut output, REQUEST_DIGEST_DOMAIN_V1)?;
    encode_object(&mut output, object, 0, Location::Root)?;
    Ok(output)
}

/// Compute the lowercase SHA-256 digest of a mutation's canonical projection.
pub fn request_digest(request: &Value) -> Result<String, RequestDigestError> {
    let projection = canonical_request_projection(request)?;
    let digest = Sha256::digest(projection);
    Ok(digest.iter().map(|byte| format!("{byte:02x}")).collect())
}

/// Verify the embedded `operation.request_digest` against the canonical request.
pub fn verify_request_digest(request: &Value) -> Result<(), RequestDigestError> {
    let object = mutation_object(request)?;
    let embedded = object
        .get("operation")
        .and_then(Value::as_object)
        .and_then(|operation| operation.get("request_digest"))
        .and_then(Value::as_str)
        .ok_or_else(|| RequestDigestError::new("operation.request_digest is required"))?;
    let expected = request_digest(request)?;
    if embedded != expected {
        return Err(RequestDigestError::new(
            "operation.request_digest does not cover the canonical request",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn request() -> Value {
        json!({
            "kind": "step_request",
            "ncp_version": "1.0",
            "session_id": "s",
            "session": {"generation": "00000000-0000-4000-8000-0000000000a2"},
            "operation": {
                "operation_id": "00000000-0000-4000-8000-0000000000c1",
                "request_digest": "placeholder",
                "session_epoch": "00000000-0000-4000-8000-0000000000a2",
                "expected_state_version": 7,
                "deadline_utc_ms": 62000,
                "retry": false
            },
            "authority": {"lease_id": "first"},
            "advance_ms": 10.0,
            "stimulus": {"values": {"drive": {"data": [1.0, -0.0], "unit": "µA"}}}
        })
    }

    #[test]
    fn object_order_does_not_change_the_projection() {
        let first = request();
        let second: Value = serde_json::from_str(&serde_json::to_string(&first).unwrap()).unwrap();
        assert_eq!(
            request_digest(&first).unwrap(),
            request_digest(&second).unwrap()
        );
    }

    #[test]
    fn retry_and_renewed_authority_do_not_change_mutation_identity() {
        let first = request();
        let mut retry = first.clone();
        retry["operation"]["retry"] = json!(true);
        retry["operation"]["request_digest"] = json!("different-placeholder");
        retry["authority"] = json!({"lease_id": "renewed", "term": 9});
        assert_eq!(
            request_digest(&first).unwrap(),
            request_digest(&retry).unwrap()
        );
    }

    #[test]
    fn payload_or_deadline_change_changes_mutation_identity() {
        let first = request();
        let mut payload = first.clone();
        payload["advance_ms"] = json!(11.0);
        let mut deadline = first.clone();
        deadline["operation"]["deadline_utc_ms"] = json!(62001);
        assert_ne!(
            request_digest(&first).unwrap(),
            request_digest(&payload).unwrap()
        );
        assert_ne!(
            request_digest(&first).unwrap(),
            request_digest(&deadline).unwrap()
        );
    }

    #[test]
    fn embedded_digest_is_verified() {
        let mut value = request();
        value["operation"]["request_digest"] = json!(request_digest(&value).unwrap());
        verify_request_digest(&value).unwrap();
        value["advance_ms"] = json!(12.0);
        assert!(verify_request_digest(&value).is_err());
    }
}
