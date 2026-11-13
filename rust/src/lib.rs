//! NCP 2: at-most-once exchanges with a known or possibly-executed outcome, and hash-chained
//! streams, between independent programs.
//!
//! See `spec/NCP-2.md`. Dependencies: `serde`, `serde_json`, `sha2`, and `socket2`.
//!
//! - [`owner`]: the owner state machine ([`owner::step`]) and its driver [`Owner`].
//! - [`client`]: the client state machine ([`client::request`], [`client::receive`]) and its
//!   driver [`Client`].
//! - [`frame`], [`messages`], [`contract`]: frames, message shapes, and contracts with schemas.
//! - [`binding`]: pipes, Unix domain sockets, TCP, child processes, and servers.
//! - [`stream`], [`transcript`]: streams and transcripts.
//! - [`lockstep`]: the lockstep profile.

pub mod binding;
pub mod client;
pub mod contract;
pub mod events;
pub mod frame;
pub mod lockstep;
pub mod messages;
pub mod owner;
pub mod stream;
pub mod transcript;

pub use binding::{
    connect_tcp, listen_tcp, serve, serve_stdio, serve_tcp, serve_with, spawn, tcp_channel,
    ChildChannel, Limits, ServeOptions, Server, StreamChannel,
};
#[cfg(unix)]
pub use binding::{connect_unix, serve_unix, spawn_unix, unix_channel};
pub use client::{call_all, Channel, ChannelError, Client, ClientState, Error};
pub use contract::{Contract, ContractError};
pub use events::{Event, Observer};
pub use frame::{
    decode, encode, identity, Array, Decoded, Dtype, FrameError, Key, DEFAULT_BOUND,
    HANDSHAKE_BOUND, MAX_BOUND, MAX_JSON,
};
pub use lockstep::{Lockstep, LockstepClient, Stepper};
pub use messages::{Executed, PROTOCOL};
pub use owner::{
    declined, AppError, Handler, Invalid, OpenInfo, Owner, OwnerState, Refused, Reply, Request,
    IMPLEMENTATION,
};
pub use stream::{Delivery, Publisher, Subscriber};
pub use transcript::Tap;

use std::collections::hash_map::RandomState;
use std::hash::{BuildHasher, Hasher};
use std::sync::atomic::{AtomicU64, Ordering};

/// Random bytes from the operating system, or, where it has no `/dev/urandom`, from the
/// process's random hash keys, a counter, and the time.
fn random_bytes<const N: usize>() -> [u8; N] {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    let mut bytes = [0u8; N];
    let from_os = std::fs::File::open("/dev/urandom")
        .and_then(|mut f| std::io::Read::read_exact(&mut f, &mut bytes));
    if from_os.is_err() {
        for (index, chunk) in bytes.chunks_mut(8).enumerate() {
            let mut hasher = RandomState::new().build_hasher();
            hasher.write_u64(COUNTER.fetch_add(1, Ordering::Relaxed));
            hasher.write_u128(
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_nanos())
                    .unwrap_or(0),
            );
            hasher.write_usize(index);
            let value = hasher.finish().to_le_bytes();
            chunk.copy_from_slice(&value[..chunk.len()]);
        }
    }
    bytes
}

/// A new random session identifier: a version 4 UUID in lowercase hyphenated form.
pub fn random_session() -> String {
    let mut bytes = random_bytes::<16>();
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let h = frame::hex(&bytes);
    format!(
        "{}-{}-{}-{}-{}",
        &h[0..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..32]
    )
}

/// A new random nonce: 32 lowercase hexadecimal characters from 128 random bits (section 7.1).
pub fn random_nonce() -> String {
    frame::hex(&random_bytes::<16>())
}
