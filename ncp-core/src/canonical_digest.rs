//! Shared typed canonical encoding for content-addressed NCP configuration.
//!
//! JSON text is not a portable digest input: object order, whitespace, numeric
//! spelling, and language-specific float formatting vary. Security-state and
//! plant-profile digests therefore hash a domain-separated typed projection.

use crate::bounded_json::{MAX_FINITE_NUMBER_MAGNITUDE, MAX_NESTING_DEPTH};
use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::fmt;

pub(crate) const MAX_PROFILE_PROJECTION_BYTES: usize = 2_097_152;

const TAG_NULL: u8 = 0x00;
const TAG_FALSE: u8 = 0x01;
const TAG_TRUE: u8 = 0x02;
const TAG_NUMBER: u8 = 0x03;
const TAG_STRING: u8 = 0x04;
const TAG_ARRAY: u8 = 0x05;
const TAG_OBJECT: u8 = 0x06;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct CanonicalDigestError(String);

impl CanonicalDigestError {
    fn new(detail: impl Into<String>) -> Self {
        Self(detail.into())
    }
}

impl fmt::Display for CanonicalDigestError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.0)
    }
}

fn push(output: &mut Vec<u8>, bytes: &[u8]) -> Result<(), CanonicalDigestError> {
    let next_len = output
        .len()
        .checked_add(bytes.len())
        .ok_or_else(|| CanonicalDigestError::new("canonical projection length overflow"))?;
    if next_len > MAX_PROFILE_PROJECTION_BYTES {
        return Err(CanonicalDigestError::new(
            "canonical projection exceeds its byte budget",
        ));
    }
    output.extend_from_slice(bytes);
    Ok(())
}

fn push_len(output: &mut Vec<u8>, length: usize) -> Result<(), CanonicalDigestError> {
    let length = u64::try_from(length)
        .map_err(|_| CanonicalDigestError::new("canonical length is not representable as u64"))?;
    push(output, &length.to_be_bytes())
}

fn encode_string(output: &mut Vec<u8>, value: &str) -> Result<(), CanonicalDigestError> {
    push(output, &[TAG_STRING])?;
    push_len(output, value.len())?;
    push(output, value.as_bytes())
}

fn encode_object(
    output: &mut Vec<u8>,
    object: &Map<String, Value>,
    depth: usize,
) -> Result<(), CanonicalDigestError> {
    let mut entries = object.iter().collect::<Vec<_>>();
    entries.sort_by(|(left, _), (right, _)| left.as_bytes().cmp(right.as_bytes()));
    push(output, &[TAG_OBJECT])?;
    push_len(output, entries.len())?;
    for (key, value) in entries {
        encode_string(output, key)?;
        encode_value(output, value, depth + 1)?;
    }
    Ok(())
}

fn encode_value(
    output: &mut Vec<u8>,
    value: &Value,
    depth: usize,
) -> Result<(), CanonicalDigestError> {
    if depth > MAX_NESTING_DEPTH {
        return Err(CanonicalDigestError::new(
            "canonical projection exceeds its nesting-depth budget",
        ));
    }
    match value {
        Value::Null => push(output, &[TAG_NULL]),
        Value::Bool(false) => push(output, &[TAG_FALSE]),
        Value::Bool(true) => push(output, &[TAG_TRUE]),
        Value::Number(number) => {
            let number = number
                .as_f64()
                .filter(|number| number.is_finite() && number.abs() <= MAX_FINITE_NUMBER_MAGNITUDE)
                .ok_or_else(|| {
                    CanonicalDigestError::new(
                        "canonical projection contains an out-of-budget number",
                    )
                })?;
            push(output, &[TAG_NUMBER])?;
            push(output, &number.to_bits().to_be_bytes())
        }
        Value::String(value) => encode_string(output, value),
        Value::Array(values) => {
            push(output, &[TAG_ARRAY])?;
            push_len(output, values.len())?;
            for value in values {
                encode_value(output, value, depth + 1)?;
            }
            Ok(())
        }
        Value::Object(object) => encode_object(output, object, depth),
    }
}

pub(crate) fn canonical_projection(
    domain: &[u8],
    value: &Value,
) -> Result<Vec<u8>, CanonicalDigestError> {
    let body = domain.strip_suffix(&[0]).unwrap_or_default();
    if body.is_empty()
        || body.len() > 128
        || !body.first().is_some_and(u8::is_ascii_alphanumeric)
        || !body.last().is_some_and(u8::is_ascii_alphanumeric)
        || !body.iter().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'-')
        })
    {
        return Err(CanonicalDigestError::new(
            "canonical digest domain must be a bounded lowercase ASCII identifier followed by exactly one NUL",
        ));
    }
    let mut output = Vec::with_capacity(
        domain
            .len()
            .saturating_add(512)
            .min(MAX_PROFILE_PROJECTION_BYTES),
    );
    push(&mut output, domain)?;
    encode_value(&mut output, value, 0)?;
    Ok(output)
}

pub(crate) fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn object_order_is_irrelevant_and_negative_zero_is_distinct() {
        let first = json!({"b": 2, "a": -0.0});
        let second: Value = serde_json::from_str(r#"{"a":-0.0,"b":2.0}"#).unwrap();
        let lexical_integer: Value = serde_json::from_str(r#"{"a":-0,"b":2}"#).unwrap();
        let positive = json!({"a": 0.0, "b": 2});
        let domain = b"ncp.test.v1\0";
        assert_eq!(
            canonical_projection(domain, &first).unwrap(),
            canonical_projection(domain, &second).unwrap()
        );
        assert_eq!(
            canonical_projection(domain, &first).unwrap(),
            canonical_projection(domain, &lexical_integer).unwrap()
        );
        assert_ne!(
            canonical_projection(domain, &first).unwrap(),
            canonical_projection(domain, &positive).unwrap()
        );
    }

    #[test]
    fn domain_size_and_depth_fail_closed() {
        assert!(canonical_projection(b"missing-terminal-nul", &Value::Null).is_err());
        assert!(canonical_projection(b"\0", &Value::Null).is_err());
        assert!(canonical_projection(b"ncp\0embedded\0", &Value::Null).is_err());
        assert!(canonical_projection(b"NCP.upper.v1\0", &Value::Null).is_err());

        let oversized = Value::String("x".repeat(MAX_PROFILE_PROJECTION_BYTES));
        assert!(canonical_projection(b"ncp.test.v1\0", &oversized).is_err());

        let mut nested = Value::Null;
        for _ in 0..=MAX_NESTING_DEPTH {
            nested = Value::Array(vec![nested]);
        }
        assert!(canonical_projection(b"ncp.test.v1\0", &nested).is_err());
    }
}
