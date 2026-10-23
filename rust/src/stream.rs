//! Streams: sequenced, hash-chained messages without retries (sections 6.3 and 8).

use crate::exchange::{is_identity, PROTOCOL};
use crate::frame::{self, Array, FrameError, MAX_BOUND};
use serde_json::{json, Value};
use std::collections::{BTreeSet, HashMap};

fn is_stream(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 256
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'.' | b'-' | b'/'))
}

/// Fail unless the message has the stream form of section 6.3.
pub fn check_stream_message(message: &Value) -> Result<(), FrameError> {
    let object = message
        .as_object()
        .ok_or_else(|| FrameError("stream message".into()))?;
    let required = ["ncp", "stream", "seq", "prev", "contract", "body"];
    let ok = object.len() == required.len() + usize::from(object.contains_key("att"))
        && required.iter().all(|k| object.contains_key(*k))
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

/// Number, chain, and encode the messages of one stream.
#[derive(Debug)]
pub struct Publisher {
    stream: String,
    contract: String,
    seq: u64,
    prev: Option<String>,
}

impl Publisher {
    /// A publisher of `stream` with contract identity `contract`.
    pub fn new(stream: &str, contract: &str) -> Result<Publisher, FrameError> {
        if !is_stream(stream) || !is_identity(&Value::from(contract)) {
            return Err(FrameError("stream identifier or contract".into()));
        }
        Ok(Publisher {
            stream: stream.to_owned(),
            contract: contract.to_owned(),
            seq: 0,
            prev: None,
        })
    }

    /// Encode the next message. The caller sends the returned frame.
    pub fn publish(&mut self, body: Value, arrays: &[Array]) -> Result<Vec<u8>, FrameError> {
        let seq = self.seq + 1;
        let message = json!({"ncp": PROTOCOL, "stream": self.stream, "seq": seq, "prev": self.prev,
                              "contract": self.contract, "body": body});
        let frame_bytes = frame::encode(&message, arrays)?;
        self.seq = seq;
        self.prev = Some(frame::identity(&frame_bytes));
        Ok(frame_bytes)
    }
}

/// The outcome of one received stream frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Delivery {
    /// Accepted; `lost` messages were missing before it.
    Accepted {
        /// Messages lost before this one.
        lost: u64,
    },
    /// A repeat of an earlier message.
    Repeat,
    /// The sequence number fits, but `prev` names another message.
    BrokenChain,
    /// The contract is not one that the subscriber knows.
    UnknownContract,
    /// A bad frame.
    BadFrame,
}

/// Check the frames of any number of streams (section 8).
#[derive(Debug)]
pub struct Subscriber {
    contracts: BTreeSet<String>,
    next: HashMap<String, u64>,
    last: HashMap<String, String>,
    check_digests: bool,
}

impl Subscriber {
    /// A subscriber that accepts the given contract identities.
    pub fn new(contracts: impl IntoIterator<Item = String>) -> Subscriber {
        Subscriber {
            contracts: contracts.into_iter().collect(),
            next: HashMap::new(),
            last: HashMap::new(),
            check_digests: true,
        }
    }

    /// Stop comparing each frame's digest with its bytes, under the conditions of spec
    /// section 3, rule 4.
    pub fn without_digest_check(mut self) -> Subscriber {
        self.check_digests = false;
        self
    }

    /// Check one frame; on acceptance, also return the decoded message.
    pub fn receive(&mut self, frame_bytes: Vec<u8>) -> (Delivery, Option<frame::Decoded>) {
        let decoded = match frame::decode_with(frame_bytes, MAX_BOUND, self.check_digests)
            .and_then(|d| check_stream_message(&d.message).map(|_| d))
        {
            Ok(decoded) => decoded,
            Err(_) => return (Delivery::BadFrame, None),
        };
        let message = &decoded.message;
        if !self
            .contracts
            .contains(message["contract"].as_str().unwrap_or_default())
        {
            return (Delivery::UnknownContract, Some(decoded));
        }
        let stream = message["stream"].as_str().unwrap_or_default().to_owned();
        let seq = message["seq"].as_u64().unwrap_or_default();
        let expected = self.next.get(&stream).copied().unwrap_or(1);
        if seq < expected {
            return (Delivery::Repeat, Some(decoded));
        }
        if seq == expected && message["prev"].as_str() != self.last.get(&stream).map(String::as_str)
        {
            return (Delivery::BrokenChain, Some(decoded));
        }
        self.next.insert(stream.clone(), seq + 1);
        self.last.insert(stream, decoded.identity.clone());
        (
            Delivery::Accepted {
                lost: seq - expected,
            },
            Some(decoded),
        )
    }
}
