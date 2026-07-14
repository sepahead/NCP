//! Bounded monotonicity admission for typed data-plane streams.
//!
//! A fence is local runtime state, not a wire field. It binds the first accepted
//! stream epoch to one concrete route, message kind, and live session generation,
//! then accepts only strictly increasing sequence numbers for that epoch. A
//! publisher restart therefore requires a fresh fence (for example, a newly
//! declared typed publisher or subscriber); silently adopting a foreign epoch
//! would reopen replay acceptance.

use std::collections::BTreeMap;

use sha2::{Digest, Sha256};

use crate::{is_canonical_uuid_v4, SessionRef, StreamPosition, JSON_SAFE_INTEGER_MAX};

const STREAM_FENCE_KEY_DOMAIN: &[u8] = b"ncp.stream-monotonicity-fence.key.v1\0";

/// Maximum number of distinct route/kind/session-generation bindings retained by
/// one fence. The fence never evicts an entry: eviction would let a retired stream
/// epoch become "first" again and admit replay.
pub const MAX_STREAM_FENCE_ENTRIES: usize = 4_096;

/// Maximum concrete route length accepted by the reusable fence.
pub const MAX_STREAM_FENCE_ROUTE_BYTES: usize = 512;

/// Maximum message-kind length accepted by the reusable fence.
pub const MAX_STREAM_FENCE_KIND_BYTES: usize = 128;

#[derive(Clone, Debug, PartialEq, Eq)]
struct StreamState {
    epoch: String,
    high_water_seq: i64,
}

/// A bounded, non-evicting high-water fence for typed stream positions.
///
/// State is keyed by a fixed-size SHA-256 digest of the concrete route, message
/// kind, and immutable live session generation. The digest prevents caller-sized
/// strings from being retained while preserving the same domain-separated identity
/// convention used by the rest of the NCP contract.
#[derive(Debug)]
pub struct StreamMonotonicityFence {
    capacity: usize,
    streams: BTreeMap<[u8; 32], StreamState>,
}

impl Default for StreamMonotonicityFence {
    fn default() -> Self {
        Self {
            capacity: MAX_STREAM_FENCE_ENTRIES,
            streams: BTreeMap::new(),
        }
    }
}

impl StreamMonotonicityFence {
    /// Construct a non-evicting fence with an explicit bounded capacity.
    ///
    /// # Errors
    ///
    /// Returns [`StreamFenceError::InvalidCapacity`] when `capacity` is zero or
    /// exceeds [`MAX_STREAM_FENCE_ENTRIES`].
    pub fn with_capacity(capacity: usize) -> Result<Self, StreamFenceError> {
        if !(1..=MAX_STREAM_FENCE_ENTRIES).contains(&capacity) {
            return Err(StreamFenceError::InvalidCapacity {
                requested: capacity,
                maximum: MAX_STREAM_FENCE_ENTRIES,
            });
        }
        Ok(Self {
            capacity,
            streams: BTreeMap::new(),
        })
    }

    /// Admit one typed stream position at a concrete route boundary.
    ///
    /// The first valid epoch for a route/kind/live-generation key is retained.
    /// Later positions must use exactly that epoch and a sequence number strictly
    /// greater than the retained high-water mark. Rejected positions never mutate
    /// the fence.
    ///
    /// # Errors
    ///
    /// Returns a validation error for a non-concrete or overlong route/kind,
    /// malformed live generation or stream position, capacity exhaustion, a
    /// foreign epoch, or a duplicate/reordered sequence number.
    pub fn accept(
        &mut self,
        route: &str,
        kind: &str,
        live_session: &SessionRef,
        stream: &StreamPosition,
    ) -> Result<(), StreamFenceError> {
        validate_key_parts(route, kind, live_session)?;
        validate_stream(stream)?;

        let key = stream_fence_key(route, kind, &live_session.generation);
        if let Some(state) = self.streams.get_mut(&key) {
            if stream.epoch != state.epoch {
                return Err(StreamFenceError::ForeignEpoch {
                    expected: state.epoch.clone(),
                    actual: stream.epoch.clone(),
                });
            }
            if stream.seq <= state.high_water_seq {
                return Err(StreamFenceError::NonMonotonicSequence {
                    high_water: state.high_water_seq,
                    actual: stream.seq,
                });
            }
            state.high_water_seq = stream.seq;
            return Ok(());
        }

        if self.streams.len() >= self.capacity {
            return Err(StreamFenceError::CapacityExceeded {
                capacity: self.capacity,
            });
        }
        self.streams.insert(
            key,
            StreamState {
                epoch: stream.epoch.clone(),
                high_water_seq: stream.seq,
            },
        );
        Ok(())
    }

    /// Number of route/kind/session-generation bindings currently retained.
    pub fn tracked_streams(&self) -> usize {
        self.streams.len()
    }

    /// Configured non-evicting entry capacity.
    pub fn capacity(&self) -> usize {
        self.capacity
    }
}

fn validate_key_parts(
    route: &str,
    kind: &str,
    live_session: &SessionRef,
) -> Result<(), StreamFenceError> {
    if route.len() > MAX_STREAM_FENCE_ROUTE_BYTES || !crate::keys::valid_realm(route) {
        return Err(StreamFenceError::InvalidRoute);
    }
    if kind.len() > MAX_STREAM_FENCE_KIND_BYTES || !crate::keys::valid_id_segment(kind) {
        return Err(StreamFenceError::InvalidKind);
    }
    if !is_canonical_uuid_v4(&live_session.generation) {
        return Err(StreamFenceError::InvalidSessionGeneration);
    }
    Ok(())
}

fn validate_stream(stream: &StreamPosition) -> Result<(), StreamFenceError> {
    if !is_canonical_uuid_v4(&stream.epoch) {
        return Err(StreamFenceError::InvalidStreamEpoch);
    }
    if !(1..=JSON_SAFE_INTEGER_MAX).contains(&stream.seq) {
        return Err(StreamFenceError::InvalidSequence(stream.seq));
    }
    Ok(())
}

fn stream_fence_key(route: &str, kind: &str, generation: &str) -> [u8; 32] {
    let mut digest = Sha256::new();
    digest.update(STREAM_FENCE_KEY_DOMAIN);
    for component in [route, kind, generation] {
        digest.update((component.len() as u64).to_be_bytes());
        digest.update(component.as_bytes());
    }
    digest.finalize().into()
}

/// Fail-closed reason returned by [`StreamMonotonicityFence`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StreamFenceError {
    /// Configured capacity was zero or exceeded the implementation ceiling.
    InvalidCapacity { requested: usize, maximum: usize },
    /// The route was empty, wildcard-bearing, malformed, or overlong.
    InvalidRoute,
    /// The message kind was empty, malformed, or overlong.
    InvalidKind,
    /// The live session generation was not a canonical lowercase UUIDv4.
    InvalidSessionGeneration,
    /// The stream epoch was not a canonical lowercase UUIDv4.
    InvalidStreamEpoch,
    /// The sequence was outside the wire-legal positive JSON-safe range.
    InvalidSequence(i64),
    /// A new key could not be retained without exceeding the configured bound.
    CapacityExceeded { capacity: usize },
    /// The key was already bound to another stream incarnation.
    ForeignEpoch { expected: String, actual: String },
    /// The sequence duplicated or preceded the accepted high-water mark.
    NonMonotonicSequence { high_water: i64, actual: i64 },
}

impl std::fmt::Display for StreamFenceError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidCapacity { requested, maximum } => write!(
                formatter,
                "stream fence capacity {requested} is outside 1..={maximum}"
            ),
            Self::InvalidRoute => write!(formatter, "stream fence requires a bounded concrete route"),
            Self::InvalidKind => write!(formatter, "stream fence requires a bounded message kind"),
            Self::InvalidSessionGeneration => write!(
                formatter,
                "stream fence requires a canonical live session generation"
            ),
            Self::InvalidStreamEpoch => {
                write!(formatter, "stream fence requires a canonical stream epoch")
            }
            Self::InvalidSequence(sequence) => write!(
                formatter,
                "stream fence sequence {sequence} is outside 1..={JSON_SAFE_INTEGER_MAX}"
            ),
            Self::CapacityExceeded { capacity } => write!(
                formatter,
                "stream fence capacity {capacity} exhausted; entries are never evicted"
            ),
            Self::ForeignEpoch { expected, actual } => write!(
                formatter,
                "stream fence rejected foreign epoch {actual:?}; bound epoch is {expected:?}"
            ),
            Self::NonMonotonicSequence { high_water, actual } => write!(
                formatter,
                "stream fence rejected sequence {actual}; it is not strictly greater than high-water {high_water}"
            ),
        }
    }
}

impl std::error::Error for StreamFenceError {}

#[cfg(test)]
mod tests {
    use super::*;

    const ROUTE: &str = "ncp/session/s1/sensor";
    const GENERATION: &str = "10000000-0000-4000-8000-000000000001";
    const EPOCH_A: &str = "20000000-0000-4000-8000-000000000001";
    const EPOCH_B: &str = "30000000-0000-4000-8000-000000000001";

    fn live_session() -> SessionRef {
        SessionRef {
            generation: GENERATION.into(),
        }
    }

    fn position(epoch: &str, seq: i64) -> StreamPosition {
        StreamPosition {
            epoch: epoch.into(),
            seq,
        }
    }

    #[test]
    fn accepts_first_canonical_epoch_and_advancing_sequence() {
        let mut fence = StreamMonotonicityFence::with_capacity(1).unwrap();
        fence
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 2),
            )
            .unwrap();

        assert!(fence
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 3)
            )
            .is_ok());
    }

    #[test]
    fn rejects_reordered_sequence_after_higher_position() {
        let mut fence = StreamMonotonicityFence::with_capacity(1).unwrap();
        fence
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 2),
            )
            .unwrap();

        assert_eq!(
            fence
                .accept(
                    ROUTE,
                    "sensor_frame",
                    &live_session(),
                    &position(EPOCH_A, 1)
                )
                .unwrap_err(),
            StreamFenceError::NonMonotonicSequence {
                high_water: 2,
                actual: 1,
            }
        );
    }

    #[test]
    fn rejects_duplicate_sequence() {
        let mut fence = StreamMonotonicityFence::with_capacity(1).unwrap();
        fence
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 2),
            )
            .unwrap();

        assert!(matches!(
            fence.accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 2)
            ),
            Err(StreamFenceError::NonMonotonicSequence {
                high_water: 2,
                actual: 2
            })
        ));
    }

    #[test]
    fn rejects_foreign_epoch_for_existing_binding() {
        let mut fence = StreamMonotonicityFence::with_capacity(1).unwrap();
        fence
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 2),
            )
            .unwrap();

        assert!(matches!(
            fence.accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_B, 3)
            ),
            Err(StreamFenceError::ForeignEpoch { .. })
        ));
    }

    #[test]
    fn fresh_fence_accepts_restarted_epoch() {
        let mut retired = StreamMonotonicityFence::with_capacity(1).unwrap();
        retired
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 2),
            )
            .unwrap();
        let mut fresh = StreamMonotonicityFence::with_capacity(1).unwrap();

        assert!(fresh
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_B, 1)
            )
            .is_ok());
    }

    #[test]
    fn refuses_eviction_when_capacity_is_exhausted() {
        let mut fence = StreamMonotonicityFence::with_capacity(1).unwrap();
        fence
            .accept(
                ROUTE,
                "sensor_frame",
                &live_session(),
                &position(EPOCH_A, 1),
            )
            .unwrap();

        assert_eq!(
            fence
                .accept(
                    "ncp/session/s2/sensor",
                    "sensor_frame",
                    &live_session(),
                    &position(EPOCH_B, 1),
                )
                .unwrap_err(),
            StreamFenceError::CapacityExceeded { capacity: 1 }
        );
    }
}
