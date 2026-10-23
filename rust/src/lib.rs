//! NCP 2: exactly-once exchanges and hash-chained streams between independent programs.
//!
//! See `spec/NCP-2.md`. Dependencies: `serde`, `serde_json`, and `sha2`.

pub mod binding;
pub mod exchange;
pub mod frame;
pub mod stream;
pub mod transcript;

pub use binding::{connect_tcp, listen_tcp, serve, serve_stdio, spawn, tcp_channel, StreamChannel};
#[cfg(unix)]
pub use binding::{connect_unix, unix_channel};
pub use exchange::{Channel, Client, Error, Handler, Owner, Reply, IMPLEMENTATION, PROTOCOL};
pub use frame::{decode, encode, identity, Array, Decoded, Dtype, FrameError, DEFAULT_BOUND, HANDSHAKE_BOUND, MAX_BOUND};
pub use stream::{Delivery, Publisher, Subscriber};
pub use transcript::Tap;

use sha2::{Digest, Sha256};
use std::collections::hash_map::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};

/// A contract document and its identity: the SHA-256 digest of its exact bytes (section 11).
#[derive(Debug, Clone)]
pub struct Contract {
    /// The exact bytes.
    pub data: Vec<u8>,
    /// The identity.
    pub identity: String,
    /// The application name.
    pub application: String,
    /// The operation names.
    pub operations: Vec<String>,
    /// The stream type names.
    pub streams: Vec<String>,
}

impl Contract {
    /// Parse a contract document.
    pub fn from_bytes(data: Vec<u8>) -> Result<Contract, FrameError> {
        let document: serde_json::Value = serde_json::from_slice(&data).map_err(|e| FrameError(e.to_string()))?;
        let application = document["application"].as_str().unwrap_or_default().to_owned();
        let operations = document["operations"].as_object().map(|o| o.keys().cloned().collect());
        let streams = document["streams"].as_object().map(|o| o.keys().cloned().collect());
        match (document["ncp_contract"].as_u64(), operations, streams, document["version"].is_string()) {
            (Some(1), Some(operations), Some(streams), true) if (1..=128).contains(&application.chars().count()) => Ok(Contract {
                identity: frame::hex(&Sha256::digest(&data)),
                data,
                application,
                operations,
                streams,
            }),
            _ => Err(FrameError("not an NCP contract".into())),
        }
    }
}

/// A new random session identifier: a version 4 UUID in lowercase hyphenated form.
///
/// Uniqueness is what matters, not secrecy; the bits come from the operating system's random
/// source when available and otherwise from the process's random hash keys.
pub fn random_session() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let mut bytes = [0u8; 16];
    let from_os = std::fs::File::open("/dev/urandom").and_then(|mut f| std::io::Read::read_exact(&mut f, &mut bytes));
    if from_os.is_err() {
        for (index, chunk) in bytes.chunks_mut(8).enumerate() {
            let mut hasher = RandomState::new().build_hasher();
            hasher.write_u64(COUNTER.fetch_add(1, Ordering::Relaxed));
            hasher.write_u128(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0));
            hasher.write_usize(index);
            chunk.copy_from_slice(&hasher.finish().to_le_bytes());
        }
    }
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let h = frame::hex(&bytes);
    format!("{}-{}-{}-{}-{}", &h[0..8], &h[8..12], &h[12..16], &h[16..20], &h[20..32])
}

/// Send one request to each session and wait for all responses (spec section 16). Sessions are
/// independent: each result is returned in its place.
pub fn call_all<C: Channel + Send>(
    clients: &mut [Client<C>],
    op: &str,
    bodies: Vec<serde_json::Value>,
) -> Vec<Result<Decoded, Error>> {
    assert_eq!(clients.len(), bodies.len(), "one body for each client");
    std::thread::scope(|scope| {
        let handles: Vec<_> = clients
            .iter_mut()
            .zip(bodies)
            .map(|(client, body)| scope.spawn(move || client.call(op, body, &[])))
            .collect();
        handles
            .into_iter()
            .map(|h| h.join().unwrap_or_else(|_| Err(Error::Protocol("session thread panicked".into()))))
            .collect()
    })
}
