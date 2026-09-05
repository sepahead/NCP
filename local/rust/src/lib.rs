//! Local NCP lockstep contract for bounded, explicitly owned simulation.
//!
//! The profile descriptor defines the selected wire and lifecycle contract.
//! This crate does not implement remote authentication or physical actuation.
//! Generated modules preserve exact bytes from the repository's canonical source.

#![forbid(unsafe_code)]

pub mod bounded_json;
mod canonical_digest;
pub mod local;
pub mod local_data;
