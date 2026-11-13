//! Streams: sequenced, hash-chained messages without retries (sections 6.3 and 8).

use crate::frame::{self, Array, Decoded, FrameError, Key, Verify, DEFAULT_BOUND};
use crate::messages::{check_stream_message, is_identity, is_stream, PROTOCOL};
use serde_json::{json, Value};
use std::collections::{BTreeSet, HashMap};

/// The body member that ends a stream (rule 8.12).
pub const END: &str = "ncp.end";

/// Number, chain, and encode the messages of one stream (section 8).
///
/// The stream identifier is the name, `/`, and 16 random hexadecimal characters, so that a
/// publisher that restarts never shares an identifier with its earlier instance (rule 8.2).
/// [`Publisher::exact`] uses the name itself; the caller then guarantees that no other instance
/// uses it.
#[derive(Debug)]
pub struct Publisher {
    stream: String,
    contract: String,
    seq: u64,
    prev: Option<String>,
    key: Option<Key>,
    ended: bool,
}

impl Publisher {
    /// A publisher of a stream named `name`, with a random instance part, and contract identity
    /// `contract`.
    pub fn new(name: &str, contract: &str) -> Result<Publisher, FrameError> {
        let instance = &crate::random_nonce()[..16];
        Publisher::exact(&format!("{name}/{instance}"), contract)
    }

    /// A publisher whose stream identifier is exactly `identifier`.
    pub fn exact(identifier: &str, contract: &str) -> Result<Publisher, FrameError> {
        if !is_stream(identifier) || !is_identity(&Value::from(contract)) {
            return Err(FrameError("stream identifier or contract".into()));
        }
        Ok(Publisher {
            stream: identifier.to_owned(),
            contract: contract.to_owned(),
            seq: 0,
            prev: None,
            key: None,
            ended: false,
        })
    }

    /// Authenticate every frame with `key` (section 13.2).
    pub fn with_key(mut self, key: Key) -> Publisher {
        self.key = Some(key);
        self
    }

    /// The stream identifier.
    pub fn stream(&self) -> &str {
        &self.stream
    }

    /// Encode the next message. The caller sends the returned frame.
    pub fn publish(&mut self, body: Value, arrays: &[Array]) -> Result<Vec<u8>, FrameError> {
        if self.ended {
            return Err(FrameError("the stream has ended".into()));
        }
        let seq = self.seq + 1;
        let message = json!({"ncp": PROTOCOL, "stream": self.stream, "seq": seq, "prev": self.prev,
                             "contract": self.contract, "body": body});
        let frame_bytes = frame::encode_with(&message, arrays, self.key.as_ref(), None)?;
        self.seq = seq;
        self.prev = Some(frame::identity(&frame_bytes));
        Ok(frame_bytes)
    }

    /// Encode the end message of the stream (rule 8.12): `body` with the member `ncp.end`.
    pub fn end(&mut self, body: Value) -> Result<Vec<u8>, FrameError> {
        let mut body = match body {
            Value::Object(object) => object,
            Value::Null => serde_json::Map::new(),
            _ => return Err(FrameError("the end message's body is an object".into())),
        };
        body.insert(END.to_owned(), json!({}));
        let frame_bytes = self.publish(Value::Object(body), &[])?;
        self.ended = true;
        Ok(frame_bytes)
    }
}

/// The outcome of one received stream frame.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Delivery {
    /// Accepted; `lost` messages were missing before it. `end` for the end message.
    Accepted {
        /// Messages lost before this one.
        lost: u64,
        /// Whether the message ends the stream.
        end: bool,
    },
    /// The first message of a stream that the subscriber sees, with `seq` greater than 1.
    Joined {
        /// Whether the message ends the stream.
        end: bool,
    },
    /// A repeat of an earlier message.
    Repeat,
    /// The `seq` of the last accepted message with another identity, or a message after the
    /// end: two publishers share the identifier, or the message changed.
    Conflict,
    /// The sequence number fits, but `prev` names another message.
    BrokenChain,
    /// The contract is not one that the subscriber knows.
    UnknownContract,
    /// A bad frame.
    BadFrame,
}

impl Delivery {
    /// The status name of the specification and the vectors.
    pub fn status(&self) -> &'static str {
        match self {
            Delivery::Accepted { .. } => "accepted",
            Delivery::Joined { .. } => "joined",
            Delivery::Repeat => "repeat",
            Delivery::Conflict => "conflict",
            Delivery::BrokenChain => "broken_chain",
            Delivery::UnknownContract => "unknown_contract",
            Delivery::BadFrame => "bad_frame",
        }
    }
}

#[derive(Debug, Clone)]
struct StreamState {
    seq: u64,
    identity: String,
    ended: bool,
    used: u64,
}

/// Check the frames of any number of streams (section 8).
#[derive(Debug)]
pub struct Subscriber {
    contracts: BTreeSet<String>,
    streams: HashMap<String, StreamState>,
    bound: usize,
    check_digests: bool,
    key: Option<Key>,
    max_streams: usize,
    clock: u64,
}

impl Subscriber {
    /// A subscriber that accepts the given contract identities, with a bound of 1 MiB for each
    /// frame and the state of at most 1024 streams.
    pub fn new(contracts: impl IntoIterator<Item = String>) -> Subscriber {
        Subscriber {
            contracts: contracts.into_iter().collect(),
            streams: HashMap::new(),
            bound: DEFAULT_BOUND,
            check_digests: true,
            key: None,
            max_streams: 1024,
            clock: 0,
        }
    }

    /// The largest stream frame (rule 8.4).
    pub fn with_bound(mut self, bound: usize) -> Subscriber {
        self.bound = bound;
        self
    }

    /// Keep the state of at most `max_streams` streams; forget the least recently used one
    /// beyond that.
    ///
    /// # Panics
    ///
    /// If `max_streams` is 0.
    pub fn with_max_streams(mut self, max_streams: usize) -> Subscriber {
        assert!(max_streams >= 1, "max_streams");
        self.max_streams = max_streams;
        self
    }

    /// Stop comparing each frame's digest with its bytes, under the conditions of spec
    /// section 3, rule 5.
    pub fn without_digest_check(mut self) -> Subscriber {
        self.check_digests = false;
        self
    }

    /// Verify every frame with `key` (section 13.2).
    pub fn with_key(mut self, key: Key) -> Subscriber {
        self.key = Some(key);
        self.check_digests = true;
        self
    }

    /// Check one frame; also return the decoded message when the frame decodes.
    pub fn receive(&mut self, frame_bytes: Vec<u8>) -> (Delivery, Option<Decoded>) {
        let verify = match (&self.key, self.check_digests) {
            (Some(key), _) => Verify::Key(key),
            (None, true) => Verify::Digest,
            (None, false) => Verify::Trust,
        };
        let decoded = match frame::decode_verified(frame_bytes, self.bound, verify)
            .and_then(|d| check_stream_message(&d.message).map(|()| d))
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
        let end = message["body"].get(END).is_some();
        self.clock += 1;
        let clock = self.clock;
        let Some(state) = self.streams.get_mut(&stream) else {
            self.remember(
                stream,
                StreamState {
                    seq,
                    identity: decoded.identity.clone(),
                    ended: end,
                    used: clock,
                },
            );
            let delivery = if seq == 1 {
                Delivery::Accepted { lost: 0, end }
            } else {
                Delivery::Joined { end }
            };
            return (delivery, Some(decoded));
        };
        state.used = clock;
        if seq == state.seq {
            let delivery = if decoded.identity == state.identity {
                Delivery::Repeat
            } else {
                Delivery::Conflict
            };
            return (delivery, Some(decoded));
        }
        if seq < state.seq {
            return (Delivery::Repeat, Some(decoded));
        }
        if state.ended {
            return (Delivery::Conflict, Some(decoded));
        }
        if seq == state.seq + 1 && message["prev"].as_str() != Some(state.identity.as_str()) {
            return (Delivery::BrokenChain, Some(decoded));
        }
        let lost = seq - state.seq - 1;
        state.seq = seq;
        state.identity = decoded.identity.clone();
        state.ended = end;
        (Delivery::Accepted { lost, end }, Some(decoded))
    }

    fn remember(&mut self, stream: String, state: StreamState) {
        self.streams.insert(stream, state);
        while self.streams.len() > self.max_streams {
            let oldest = self
                .streams
                .iter()
                .min_by_key(|(_, s)| s.used)
                .map(|(name, _)| name.clone());
            match oldest {
                Some(name) => {
                    self.streams.remove(&name);
                }
                None => break,
            }
        }
    }
}
