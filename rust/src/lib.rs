//! NCP 2: at-most-once exchanges with a known or possibly-executed outcome, and hash-chained
//! streams, between independent programs.
//!
//! See `spec/NCP-2.md`. Dependencies: `serde`, `serde_json`, `sha2`, `socket2`, and `getrandom`.
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

/// Random bytes from the cryptographically secure generator of the operating system, which
/// rule 7.1.5 requires for nonces.
///
/// # Panics
///
/// If the operating system gives no random bytes. NCP then opens no session and makes no
/// stream: it never falls back to a weaker source.
fn random_bytes<const N: usize>() -> [u8; N] {
    let mut bytes = [0u8; N];
    if let Err(error) = getrandom::fill(&mut bytes) {
        panic!(
            "the operating system gave no random bytes ({error}); NCP needs them for nonces and \
             session identifiers (rule 7.1.5)"
        );
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
