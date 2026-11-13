//! Messages, outcomes, and codes (specification sections 6 and 7.4 to 7.5).
//!
//! `spec/ncp2-rules.json` states the same codes as data; `scripts/check_ncp2_rules.py` keeps this
//! module equal to it.

use crate::frame::{self, FrameError, Key};
use serde_json::{json, Map, Value};
use std::fmt;

/// The protocol version in every message.
pub const PROTOCOL: u64 = 2;
/// The outcomes of a response (section 7.4).
pub const OUTCOMES: [&str; 4] = ["ok", "declined", "rejected", "ended"];
/// The longest operation name, feature name, and code.
pub const MAX_NAME: usize = 64;
/// The longest `run` member of an `open` request.
pub const MAX_RUN: usize = 256;
/// The longest detail member of a response body.
pub const MAX_DETAIL: usize = 256;
/// The most features in an `open` request.
pub const MAX_FEATURES: usize = 32;

/// Codes of a rejected frame: the owner did not admit it (section 7.5).
pub const REJECTION_CODES: [&str; 14] = [
    "wrong_protocol",
    "not_open",
    "wrong_session",
    "seq_conflict",
    "seq_stale",
    "seq_gap",
    "session_ended",
    "ack_missing",
    "ack_mismatch",
    "already_open",
    // in reply to open
    "body_invalid",
    "contract_mismatch",
    "bound_unacceptable",
    "refused",
];
/// Codes of a declined request: admitted, not executed, never executed (section 7.5).
pub const DECLINE_CODES: [&str; 2] = ["unknown_op", "body_invalid"];
/// Codes of an ending response, with whether the request executed (section 7.5).
pub const ENDING_CODES: [(&str, Executed); 5] = [
    ("result_too_large", Executed::Yes),
    ("owner_failure", Executed::Unknown),
    ("session_expired", Executed::Unknown),
    ("shutdown", Executed::No),
    ("bad_frame", Executed::No),
];
/// Codes that a client reports for local events (spec/ncp2-rules.json, local_codes).
pub const LOCAL_CODES: [&str; 4] = [
    "local.timeout",
    "local.closed",
    "local.protocol",
    "local.bad_frame",
];

/// Whether a request executed, as far as the client can know (section 7.7, property 7).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Executed {
    /// The request executed once.
    Yes,
    /// The request did not execute, and never will.
    No,
    /// The request is possibly executed.
    Unknown,
}

impl Executed {
    /// "yes", "no", or "unknown".
    pub fn as_str(self) -> &'static str {
        match self {
            Executed::Yes => "yes",
            Executed::No => "no",
            Executed::Unknown => "unknown",
        }
    }
}

impl fmt::Display for Executed {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Whether the request named by an `ended` response executed. A code that this version does not
/// know gives Unknown (section 7.5).
pub fn executed(code: &str) -> Executed {
    ENDING_CODES
        .iter()
        .find(|(known, _)| *known == code)
        .map_or(Executed::Unknown, |(_, executed)| *executed)
}

fn is_hex(s: &str, length: usize) -> bool {
    s.len() == length
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Whether a value is an identity: 64 lowercase hexadecimal characters.
pub fn is_identity(value: &Value) -> bool {
    value.as_str().is_some_and(|s| is_hex(s, 64))
}

/// Whether a value is a nonce: 32 lowercase hexadecimal characters (section 7.1).
pub fn is_nonce(value: &Value) -> bool {
    value.as_str().is_some_and(|s| is_hex(s, 32))
}

/// Whether a string is a session identifier: a version 4 UUID in lowercase hyphenated form.
pub fn is_session(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 36
        && b.iter().enumerate().all(|(i, &c)| match i {
            8 | 13 | 18 | 23 => c == b'-',
            14 => c == b'4',
            19 => matches!(c, b'8' | b'9' | b'a' | b'b'),
            _ => c.is_ascii_digit() || (b'a'..=b'f').contains(&c),
        })
}

/// Whether a string is an operation name, feature name, or stream type name (section 6).
pub fn is_name(s: &str) -> bool {
    let b = s.as_bytes();
    !b.is_empty()
        && b.len() <= MAX_NAME
        && b[0].is_ascii_lowercase()
        && b.iter().all(|&c| {
            c.is_ascii_lowercase() || c.is_ascii_digit() || matches!(c, b'_' | b'.' | b'-')
        })
}

/// Whether a value is a code: 1 to 64 characters from `a`–`z` and `_` (section 6).
pub fn is_code(value: &Value) -> bool {
    value.as_str().is_some_and(|c| {
        (1..=MAX_NAME).contains(&c.len()) && c.bytes().all(|b| b.is_ascii_lowercase() || b == b'_')
    })
}

/// Whether a string is a stream identifier (section 6.3).
pub fn is_stream(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 256
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'-' | b'/'))
}

/// A non-negative integer: an integer that JSON wrote without fraction or exponent.
fn is_counter(value: &Value) -> bool {
    value.is_u64()
}

const REQUEST_MEMBERS: [&str; 6] = ["ncp", "session", "seq", "op", "ack", "body"];
const RESPONSE_MEMBERS: [&str; 7] = [
    "ncp", "session", "seq", "request", "outcome", "code", "body",
];
const STREAM_MEMBERS: [&str; 6] = ["ncp", "stream", "seq", "prev", "contract", "body"];

fn has_members(object: &Map<String, Value>, required: &[&str]) -> bool {
    object.len() == required.len() + usize::from(object.contains_key("att"))
        && required.iter().all(|key| object.contains_key(*key))
}

/// "request", "response", "stream", or "other", from the members of a decoded message.
pub fn kind(message: &Value) -> &'static str {
    match message.as_object() {
        Some(o) if has_members(o, &REQUEST_MEMBERS) => "request",
        Some(o) if has_members(o, &RESPONSE_MEMBERS) => "response",
        Some(o) if has_members(o, &STREAM_MEMBERS) => "stream",
        _ => "other",
    }
}

/// Whether a message is a request of another protocol version (section 6.1): `ncp` is a
/// non-negative integer other than 2, `session` is a session identifier, and `seq` is a sequence
/// number. It is not a bad frame, whatever its other members: the owner rejects it with
/// `wrong_protocol` (rule 7.3.2).
pub fn foreign(message: &Value) -> bool {
    is_counter(&message["ncp"])
        && message["ncp"] != PROTOCOL
        && message["session"].as_str().is_some_and(is_session)
        && is_counter(&message["seq"])
}

/// Fail unless the message has the request form of section 6.1.
pub fn check_request(message: &Value) -> Result<(), FrameError> {
    let object = message
        .as_object()
        .ok_or_else(|| FrameError("request".into()))?;
    let ok = has_members(object, &REQUEST_MEMBERS)
        && is_counter(&object["ncp"])
        && object["session"].as_str().is_some_and(is_session)
        && is_counter(&object["seq"])
        && object["op"].as_str().is_some_and(is_name)
        && (object["ack"].is_null() || is_identity(&object["ack"]));
    if ok {
        Ok(())
    } else {
        Err(FrameError("request members".into()))
    }
}

/// Fail unless the message has the response form of section 6.2.
pub fn check_response(message: &Value) -> Result<(), FrameError> {
    let object = message
        .as_object()
        .ok_or_else(|| FrameError("response".into()))?;
    if !has_members(object, &RESPONSE_MEMBERS) || !is_counter(&object["ncp"]) {
        return Err(FrameError("response members".into()));
    }
    let names = object["session"].as_str().is_some_and(is_session)
        && is_counter(&object["seq"])
        && is_identity(&object["request"]);
    let ok = match object["outcome"].as_str() {
        Some("ok") => object["code"].is_null() && names,
        Some("ended") => {
            let nameless = object["session"].is_null()
                && object["seq"].is_null()
                && object["request"].is_null();
            is_code(&object["code"]) && object["body"].is_object() && (names || nameless)
        }
        Some("declined" | "rejected") => {
            is_code(&object["code"]) && object["body"].is_object() && names
        }
        _ => false,
    };
    if ok {
        Ok(())
    } else {
        Err(FrameError("response member types".into()))
    }
}

/// Fail unless the message has the stream form of section 6.3.
pub fn check_stream_message(message: &Value) -> Result<(), FrameError> {
    let object = message
        .as_object()
        .ok_or_else(|| FrameError("stream message".into()))?;
    let ok = has_members(object, &STREAM_MEMBERS)
        && object["ncp"].is_u64()
        && object["ncp"] == PROTOCOL
        && object["stream"].as_str().is_some_and(is_stream)
        && is_identity(&object["contract"])
        && match object["seq"].as_u64() {
            Some(1) => object["prev"].is_null(),
            Some(seq) if seq > 1 => is_identity(&object["prev"]),
            _ => false,
        };
    if ok {
        Ok(())
    } else {
        Err(FrameError("stream message members".into()))
    }
}

/// A detail member for a response body: at most 256 characters.
pub fn detail(text: &str) -> String {
    text.chars().take(MAX_DETAIL).collect()
}

/// The response of the byte-stream binding that names no request (section 6.2): the bad-frame
/// response (rule 9.1.3) and the shutdown response (rule 9.1.9).
///
/// Its body binds it to the owner's chain: `chain` is the session that the owner holds and the
/// identity of its kept response; without a session, the body is an empty object.
pub fn nameless_response(code: &str, key: Option<&Key>, chain: Option<(&str, &str)>) -> Vec<u8> {
    let body = match chain {
        Some((session, kept)) => json!({"session": session, "kept": kept}),
        None => json!({}),
    };
    let message = json!({"ncp": PROTOCOL, "session": null, "seq": null, "request": null,
                         "outcome": "ended", "code": code, "body": body});
    frame::encode_with(&message, &[], key, None).unwrap_or_default()
}

/// The response a byte-stream owner sends for a bad frame before it closes (rule 9.1.3).
pub fn bad_frame_response(key: Option<&Key>, chain: Option<(&str, &str)>) -> Vec<u8> {
    nameless_response("bad_frame", key, chain)
}

/// The response a byte-stream owner sends when it stops a session (rule 9.1.9).
pub fn shutdown_response(key: Option<&Key>, chain: Option<(&str, &str)>) -> Vec<u8> {
    nameless_response("shutdown", key, chain)
}
