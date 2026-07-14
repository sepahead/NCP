//! NCP wire messages — the normative payload contract.
//!
//! Every type here implements the JSON projection of the normative protobuf IDL
//! (`proto/ncp.proto`). The generated JSON Schemas and TypeScript types derive
//! from these Rust reference types and independent parity/conformance guards keep
//! every shipped surface wire-compatible (map key order may differ). In particular:
//!
//! - enums serialize as their string *values* (`"V_m"`, `"spike_times"`, …),
//! - every message carries a `kind` discriminator and an `ncp_version`,
//! - `Option::None` serializes as JSON `null`,
//! - unknown fields are **ignored** on deserialize. This is forward compatible
//!   only within a compatible version: while the wire is pre-1.0 (`0.x`) the
//!   minor is breaking, so [`check_version`] requires an exact `(major, minor)`
//!   match; once `>=1.0` the major alone gates compatibility.
//!
//! Construct messages with `..Default::default()` (or the `new` helpers) so the
//! `kind`/`ncp_version` defaults are filled in.

use serde::{de::Error as _, Deserialize, Serialize};
use std::collections::BTreeMap;

/// Protocol version (semver). While pre-1.0 (`0.x`) receivers check the full
/// `(major, minor)`; once `>=1.0` they check the **major** only. See
/// [`check_version`].
///
/// Wire `1.0` is the unreleased candidate line. It retains the frozen 0.8 stream
/// identity and honesty boundaries while making safety-relevant channel
/// requirement state explicit. Release status is independent of this identifier;
/// the candidate remains blocked until every external gate is evidenced.
pub const NCP_VERSION: &str = "1.0";

/// Largest integer that every NCP JSON peer can represent exactly. The JSON wire
/// deliberately uses numbers for proto `int64` fields, but JavaScript parses those
/// numbers as binary64. Wire values outside this range therefore cannot round-trip
/// identically across Rust/Python/C++/TypeScript and are rejected at ingress.
pub const JSON_SAFE_INTEGER_MAX: i64 = 9_007_199_254_740_991;
pub const JSON_SAFE_INTEGER_MIN: i64 = -JSON_SAFE_INTEGER_MAX;

/// Absolute resource ceiling for packetized predictive-control setpoints. The
/// TTL/cadence bound is usually much smaller; this prevents an attacker from
/// turning a tiny cadence into an effectively unbounded decoded horizon.
pub const MAX_HORIZON_STEPS: usize = 65_536;
pub const MAX_CHANNELS: usize = 4_096;

fn ncp_version() -> String {
    NCP_VERSION.to_string()
}

/// Deserialize-side default for every `ncp_version` field (wire 0.6): a frame that
/// OMITS `ncp_version` deserializes to `""` — detectably invalid under
/// [`validate`]/[`check_version`] — instead of being silently fabricated as the
/// receiver's own version (the pre-0.6 behaviour, where the container-level
/// `#[serde(default)]` filled it from `Default::default()`). Programmatic
/// construction (`..Default::default()` / the `new` helpers) still stamps
/// [`NCP_VERSION`].
fn missing_version() -> String {
    String::new()
}

/// Deserialize-side default for every message-envelope `kind` field, mirroring
/// [`missing_version`]: a frame that omits `kind` deserializes to `""` instead of
/// the container default (which would fabricate the *correct* discriminator for a
/// frame that never declared one), so [`decode_validated`] and the RPC reply gate
/// can reject it. Programmatic construction still stamps the right `kind`.
fn missing_kind() -> String {
    String::new()
}

/// A JSON object map (`{string: T}`); `BTreeMap` for deterministic ordering.
pub type Map<T> = BTreeMap<String, T>;

/// Proto `int64` is projected as a JSON number. JSON Schema defines `integer`
/// semantically, so `1`, `1.0`, and `1e0` are the same integer value; JavaScript
/// also erases that lexical distinction during `JSON.parse`. Serde's stock `i64`
/// decoder rejects the latter two spellings, which made Rust disagree with the
/// TypeScript/schema peers. These field decoders accept every mathematically
/// integral spelling while still enforcing the exact cross-language safe range.
mod json_integer {
    use super::{Map, JSON_SAFE_INTEGER_MAX, JSON_SAFE_INTEGER_MIN};
    use serde::de::{Error, Visitor};
    use serde::{Deserialize, Deserializer, Serialize, Serializer};
    use std::fmt;

    #[derive(Clone, Copy)]
    struct ExactI64(i64);

    struct ExactI64Visitor;

    impl Visitor<'_> for ExactI64Visitor {
        type Value = ExactI64;

        fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            write!(
                formatter,
                "an exact JSON integer in [{JSON_SAFE_INTEGER_MIN}, {JSON_SAFE_INTEGER_MAX}]"
            )
        }

        fn visit_i64<E: Error>(self, value: i64) -> Result<Self::Value, E> {
            if (JSON_SAFE_INTEGER_MIN..=JSON_SAFE_INTEGER_MAX).contains(&value) {
                Ok(ExactI64(value))
            } else {
                Err(E::custom("integer is outside the exact NCP JSON range"))
            }
        }

        fn visit_u64<E: Error>(self, value: u64) -> Result<Self::Value, E> {
            if value <= JSON_SAFE_INTEGER_MAX as u64 {
                Ok(ExactI64(value as i64))
            } else {
                Err(E::custom("integer is outside the exact NCP JSON range"))
            }
        }

        fn visit_f64<E: Error>(self, value: f64) -> Result<Self::Value, E> {
            if value.is_finite()
                && value.fract() == 0.0
                && value >= JSON_SAFE_INTEGER_MIN as f64
                && value <= JSON_SAFE_INTEGER_MAX as f64
            {
                Ok(ExactI64(value as i64))
            } else {
                Err(E::custom(
                    "number is fractional or outside the exact NCP JSON integer range",
                ))
            }
        }
    }

    impl<'de> Deserialize<'de> for ExactI64 {
        fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
            deserializer.deserialize_any(ExactI64Visitor)
        }
    }

    pub mod one {
        use super::*;

        pub fn serialize<S: Serializer>(value: &i64, serializer: S) -> Result<S::Ok, S::Error> {
            value.serialize(serializer)
        }

        pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<i64, D::Error> {
            ExactI64::deserialize(deserializer).map(|value| value.0)
        }
    }

    pub mod option {
        use super::*;

        pub fn serialize<S: Serializer>(
            value: &Option<i64>,
            serializer: S,
        ) -> Result<S::Ok, S::Error> {
            value.serialize(serializer)
        }

        pub fn deserialize<'de, D: Deserializer<'de>>(
            deserializer: D,
        ) -> Result<Option<i64>, D::Error> {
            Option::<ExactI64>::deserialize(deserializer).map(|value| value.map(|value| value.0))
        }
    }

    pub mod unsigned {
        use super::*;
        use serde::ser::Error as _;

        pub fn serialize<S: Serializer>(value: &u64, serializer: S) -> Result<S::Ok, S::Error> {
            if *value > JSON_SAFE_INTEGER_MAX as u64 {
                return Err(S::Error::custom(
                    "integer is outside the exact NCP JSON range",
                ));
            }
            value.serialize(serializer)
        }

        pub fn deserialize<'de, D: Deserializer<'de>>(deserializer: D) -> Result<u64, D::Error> {
            let value = ExactI64::deserialize(deserializer)?.0;
            u64::try_from(value).map_err(|_| D::Error::custom("integer must be non-negative"))
        }
    }

    pub mod vec {
        use super::*;

        pub fn serialize<S: Serializer>(value: &[i64], serializer: S) -> Result<S::Ok, S::Error> {
            value.serialize(serializer)
        }

        pub fn deserialize<'de, D: Deserializer<'de>>(
            deserializer: D,
        ) -> Result<Vec<i64>, D::Error> {
            Vec::<ExactI64>::deserialize(deserializer)
                .map(|values| values.into_iter().map(|value| value.0).collect())
        }
    }

    pub mod map {
        use super::*;

        pub fn serialize<S: Serializer>(
            value: &Map<i64>,
            serializer: S,
        ) -> Result<S::Ok, S::Error> {
            value.serialize(serializer)
        }

        pub fn deserialize<'de, D: Deserializer<'de>>(
            deserializer: D,
        ) -> Result<Map<i64>, D::Error> {
            Map::<ExactI64>::deserialize(deserializer).map(|values| {
                values
                    .into_iter()
                    .map(|(key, value)| (key, value.0))
                    .collect()
            })
        }
    }
}

// ───────────────────────── stream identity (wire 0.8) ─────────────────────────

/// One exact position in ONE logical stream incarnation (`proto/ncp.proto`
/// `StreamPosition`). Wire 0.8 splits the old overloaded top-level `seq` into a
/// frame's OWN [`stream`](SensorFrame) — the only sequence loss/`LinkMonitor`/
/// `ActionBuffer` accounting reads — and a `source` referencing the frame that drove
/// it (correlation only, never loss accounting).
///
/// `epoch` is an opaque per-incarnation id (canonical lowercase UUIDv4), compared for
/// EQUALITY ONLY — never ordered, never a timestamp. `seq` starts at 1 per epoch,
/// strictly increasing, within `1 ..= JSON_SAFE_INTEGER_MAX`. The `""`/`0` default is
/// "unset" and is not wire-legal until stamped (mirrors the retired `seq` discipline).
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Hash, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct StreamPosition {
    pub epoch: String,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub seq: i64,
}

/// One live session incarnation (`proto/ncp.proto` `SessionRef`). The routing
/// `session_id` (carried alongside on every session-scoped frame) remains the logical
/// name; this server-issued `generation` distinguishes one opening of that id from a
/// later reuse, so a stale-session frame is rejectable. The pair
/// `(session_id, generation)` identifies the live instance; `""` = unset.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Hash, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SessionRef {
    pub generation: String,
}

/// Shared identity fixtures for wire-0.8 tests across the crate: canonical UUIDv4
/// `stream.epoch` / `session.generation` and a valid `session_id`, so a constructed
/// test frame passes [`WireFrame::validate_wire`].
#[cfg(test)]
pub(crate) mod test_ids {
    use super::{SessionRef, StreamPosition};
    pub const EPOCH: &str = "00000000-0000-4000-8000-000000000001";
    pub const GEN: &str = "00000000-0000-4000-8000-0000000000a2";
    pub const SID: &str = "sess";
    pub fn stream(seq: i64) -> StreamPosition {
        StreamPosition {
            epoch: EPOCH.into(),
            seq,
        }
    }
    pub fn session() -> SessionRef {
        SessionRef {
            generation: GEN.into(),
        }
    }
}

// ───────────────────────── enums ─────────────────────────

/// Implement a string-valued enum whose unknown values are retained exactly.
///
/// A catch-all unit variant is not sufficient: serde's `other` accepts the value
/// but destroys it, so decode -> encode silently rewrites an unrecognized value to
/// `"unknown"`. The original string is therefore stored in `Unknown`, both for
/// the explicitly open `Mode` and for closed enums that need
/// faithful diagnostics or relay. Path-level validation decides whether the value
/// is safe there. Empty strings are never enum values (proto's `*_UNSPECIFIED`
/// constants are not part of the JSON wire), so they fail closed instead of
/// becoming an ambiguous sentinel.
macro_rules! forward_string_enum {
    ($ty:ident { $($wire:literal => $variant:ident),+ $(,)? }) => {
        impl $ty {
            pub fn as_str(&self) -> &str {
                match self {
                    $(Self::$variant => $wire,)+
                    Self::Unknown(value) => value,
                }
            }

            /// Whether this in-memory representation has one unambiguous wire
            /// spelling. Deserialization always canonicalizes known spellings to
            /// their known variants; public callers must not construct
            /// `Unknown("known")` and serialize it into a different authority.
            pub fn is_canonical_wire_value(&self) -> bool {
                match self {
                    $(Self::$variant => true,)+
                    Self::Unknown(value) => {
                        !value.is_empty() && !matches!(value.as_str(), $($wire)|+)
                    }
                }
            }
        }

        impl Serialize for $ty {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: serde::Serializer,
            {
                if !self.is_canonical_wire_value() {
                    return Err(serde::ser::Error::custom(concat!(
                        stringify!($ty),
                        " has a non-canonical Unknown value"
                    )));
                }
                serializer.serialize_str(self.as_str())
            }
        }

        impl<'de> Deserialize<'de> for $ty {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: serde::Deserializer<'de>,
            {
                let value = String::deserialize(deserializer)?;
                if value.is_empty() {
                    return Err(D::Error::custom("NCP enum strings must not be empty"));
                }
                Ok(match value.as_str() {
                    $($wire => Self::$variant,)+
                    _ => Self::Unknown(value),
                })
            }
        }
    };
}

/// What to record off a population/neuron/synapse.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(
        export,
        type = "\"spikes\" | \"V_m\" | \"rate\" | \"weight\" | \"binary_state\""
    )
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum Observable {
    #[cfg_attr(feature = "schema", schemars(rename = "spikes"))]
    Spikes,
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "V_m"))]
    Vm,
    #[cfg_attr(feature = "schema", schemars(rename = "rate"))]
    Rate,
    #[cfg_attr(feature = "schema", schemars(rename = "weight"))]
    Weight,
    /// Binary / multi-state neurons: discrete state via spin_detector, not V_m. (#10)
    #[cfg_attr(feature = "schema", schemars(rename = "binary_state"))]
    BinaryState,
    /// An unrecognized value retained for diagnostics or lossless relay. This is
    /// closed because recording and observation paths require interpretation.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(Observable {
    "spikes" => Spikes,
    "V_m" => Vm,
    "rate" => Rate,
    "weight" => Weight,
    "binary_state" => BinaryState,
});

/// How a stimulus drives a target.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(
        export,
        type = "\"current_pA\" | \"rate_hz\" | \"spike_times\" | \"weight_set\" | \"rate_inject\""
    )
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum StimulusKind {
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "current_pA"))]
    CurrentPa,
    #[cfg_attr(feature = "schema", schemars(rename = "rate_hz"))]
    RateHz,
    #[cfg_attr(feature = "schema", schemars(rename = "spike_times"))]
    SpikeTimes,
    #[cfg_attr(feature = "schema", schemars(rename = "weight_set"))]
    WeightSet,
    /// Continuous-rate injection for rate-based neurons (rate connections /
    /// step_rate_generator); rate models cannot receive spikes. (#10)
    #[cfg_attr(feature = "schema", schemars(rename = "rate_inject"))]
    RateInject,
    /// An unrecognized value retained for diagnostics or lossless relay. Because
    /// this enum selects an input action, request validation rejects it.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(StimulusKind {
    "current_pA" => CurrentPa,
    "rate_hz" => RateHz,
    "spike_times" => SpikeTimes,
    "weight_set" => WeightSet,
    "rate_inject" => RateInject,
});

/// What kind of network reference `NetworkRef.ref` is.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(export, type = "\"handle\" | \"builtin\" | \"model_id\" | \"spec\"")
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum NetworkRefKind {
    #[cfg_attr(feature = "schema", schemars(rename = "handle"))]
    Handle,
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "builtin"))]
    Builtin,
    #[cfg_attr(feature = "schema", schemars(rename = "model_id"))]
    ModelId,
    #[cfg_attr(feature = "schema", schemars(rename = "spec"))]
    Spec,
    /// An unrecognized value retained for diagnostics or lossless relay. Because
    /// this enum selects model-loading behavior, request validation rejects it.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(NetworkRefKind {
    "handle" => Handle,
    "builtin" => Builtin,
    "model_id" => ModelId,
    "spec" => Spec,
});

/// Stream vs batch simulation.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(export, type = "\"stream\" | \"batch\"")
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum SimMode {
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "stream"))]
    Stream,
    #[cfg_attr(feature = "schema", schemars(rename = "batch"))]
    Batch,
    /// An unrecognized value retained for diagnostics or lossless relay. Because
    /// this enum selects execution behavior, request validation rejects it.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(SimMode {
    "stream" => Stream,
    "batch" => Batch,
});

/// Controller mode (the safety-critical action authority lives here). Unknown
/// additive strings are preserved, but every safety decision treats them exactly
/// like a non-Active mode and emits HOLD.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(
        export,
        type = "\"init\" | \"active\" | \"hold\" | \"estop\" | (string & {})"
    )
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum Mode {
    #[cfg_attr(feature = "schema", schemars(rename = "init"))]
    Init,
    #[cfg_attr(feature = "schema", schemars(rename = "active"))]
    Active,
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "hold"))]
    Hold,
    #[cfg_attr(feature = "schema", schemars(rename = "estop"))]
    Estop,
    /// A newer additive wire value. It never authorizes actuation.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(Mode {
    "init" => Init,
    "active" => Active,
    "hold" => Hold,
    "estop" => Estop,
});

/// Hierarchical entity role for addressing sensors/actuators.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(export, type = "\"system\" | \"actor\" | \"sensor\" | \"actuator\"")
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum EntityRole {
    #[cfg_attr(feature = "schema", schemars(rename = "system"))]
    System,
    #[cfg_attr(feature = "schema", schemars(rename = "actor"))]
    Actor,
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "sensor"))]
    Sensor,
    #[cfg_attr(feature = "schema", schemars(rename = "actuator"))]
    Actuator,
    /// An unrecognized value retained for diagnostics or lossless relay. This is
    /// closed because bindings may use the role for routing or authorization.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(EntityRole {
    "system" => System,
    "actor" => Actor,
    "sensor" => Sensor,
    "actuator" => Actuator,
});

/// Channel arity (carries the vec semantics so the envelope stays generic).
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(export, type = "\"scalar\" | \"vec3\" | \"quat\" | \"array\"")
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum ChannelKind {
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "scalar"))]
    Scalar,
    #[cfg_attr(feature = "schema", schemars(rename = "vec3"))]
    Vec3,
    #[cfg_attr(feature = "schema", schemars(rename = "quat"))]
    Quat,
    #[cfg_attr(feature = "schema", schemars(rename = "array"))]
    Array,
    /// An unrecognized value retained for diagnostics or lossless relay. This is
    /// closed because required capability paths must interpret the shape.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(ChannelKind {
    "scalar" => Scalar,
    "vec3" => Vec3,
    "quat" => Quat,
    "array" => Array,
});

/// Whether a negotiated channel is mandatory. Wire 1.0 deliberately makes
/// absence/`"unknown"` non-authorizing; wire 0.8's missing `optional` boolean
/// optimistically defaulted to `true` and is accepted only by the labelled gateway.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(export, type = "\"unknown\" | \"required\" | \"optional\"")
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum ChannelRequirement {
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "unknown"))]
    Indeterminate,
    #[cfg_attr(feature = "schema", schemars(rename = "required"))]
    Required,
    #[cfg_attr(feature = "schema", schemars(rename = "optional"))]
    Optional,
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    /// An unrecognized value retained for diagnostics or lossless relay. This is
    /// a closed negotiation enum, so semantic validation rejects it.
    Unknown(String),
}

forward_string_enum!(ChannelRequirement {
    "unknown" => Indeterminate,
    "required" => Required,
    "optional" => Optional,
});

/// Who a peer is in the closed-loop handshake.
#[derive(Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(
    feature = "ts",
    derive(ts_rs::TS),
    ts(
        export,
        type = "\"controller\" | \"plant\" | \"observer\" | \"operator\""
    )
)]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub enum Role {
    #[default]
    #[cfg_attr(feature = "schema", schemars(rename = "controller"))]
    Controller,
    #[cfg_attr(feature = "schema", schemars(rename = "plant"))]
    Plant,
    #[cfg_attr(feature = "schema", schemars(rename = "observer"))]
    Observer,
    #[cfg_attr(feature = "schema", schemars(rename = "operator"))]
    Operator,
    /// An unrecognized value retained for diagnostics or lossless relay. This is
    /// a closed authority-negotiation enum, so semantic validation rejects it.
    #[cfg_attr(feature = "schema", schemars(skip))]
    #[cfg_attr(feature = "ts", ts(skip))]
    Unknown(String),
}

forward_string_enum!(Role {
    "controller" => Controller,
    "plant" => Plant,
    "observer" => Observer,
    "operator" => Operator,
});

/// Transport plane named by an authenticated principal claim. Security enums are
/// closed: an unknown plane never inherits authority from a known one.
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum Plane {
    #[default]
    Unknown,
    Control,
    Perception,
    Action,
    Observation,
}

/// Principal role enrolled by a deployment authority manifest. This is distinct
/// from the older controller/plant handshake role because observers and operators
/// have security authority without pretending to be a controller or body.
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum PrincipalRole {
    #[default]
    Unknown,
    Commander,
    Body,
    Observer,
    Operator,
}

/// Payload claim that an authenticated transport adapter binds to its verified
/// peer identity. The claim never authenticates itself.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct IdentityClaim {
    pub principal_id: String,
    pub entity_id: String,
    pub role: PrincipalRole,
    pub plane: Plane,
}

/// Visible attribution for a deliberately translated legacy payload. Native
/// peers omit it; its presence never upgrades the legacy source's security or
/// scientific/safety evidence.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct GatewayAttribution {
    pub gateway_id: String,
    pub source_wire: String,
}

/// Normative lifecycle state carried by authority/audit projections.
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum LifecycleState {
    #[default]
    Unknown,
    Closed,
    Opening,
    Init,
    Active,
    Hold,
    Estop,
    Closing,
    Reconnecting,
    Failed,
}

/// One bounded authority term for a single session incarnation. UTC timestamps
/// are receipt/audit bounds; receivers derive a local monotonic expiry deadline.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct AuthorityLease {
    pub session_epoch: String,
    #[serde(with = "json_integer::unsigned")]
    #[cfg_attr(feature = "schema", schemars(with = "u64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub term: u64,
    pub lease_id: String,
    pub issuer_principal_id: String,
    pub holder_principal_id: String,
    pub holder_entity_id: String,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub issued_at_utc_ms: i64,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub expires_at_utc_ms: i64,
}

/// Caller-provided exactly-once context for a state-mutating lifecycle RPC.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct OperationContext {
    pub operation_id: String,
    pub request_digest: String,
    pub session_epoch: String,
    #[serde(with = "json_integer::unsigned")]
    #[cfg_attr(feature = "schema", schemars(with = "u64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub expected_state_version: u64,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub deadline_utc_ms: i64,
    pub retry: bool,
}

/// Terminal state of one idempotent lifecycle operation.
#[derive(Serialize, Deserialize, Clone, Copy, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(rename_all = "snake_case")]
pub enum OperationOutcome {
    #[default]
    Unknown,
    Succeeded,
    Rejected,
    Cancelled,
    OutcomeUnknown,
}

/// Authenticated responder receipt returned by a state-mutating lifecycle RPC.
#[derive(Serialize, Deserialize, Clone, PartialEq, Eq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct ResponderReceipt {
    pub operation_id: String,
    pub request_digest: String,
    pub result_digest: String,
    pub outcome: OperationOutcome,
    #[serde(with = "json_integer::unsigned")]
    #[cfg_attr(feature = "schema", schemars(with = "u64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub state_version: u64,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub committed_at_utc_ms: i64,
    pub responder_principal_id: String,
    pub responder_entity_id: String,
}

// ───────────────────────── primitives ─────────────────────────

/// A channel sample: a flat list of floats plus an optional unit string. Width
/// carries the semantics (1=scalar, 3=vec3, 4=quat, N=array).
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub struct ChannelValue {
    #[serde(default)]
    pub data: Vec<f64>,
    #[serde(default)]
    pub unit: Option<String>,
}

impl ChannelValue {
    pub fn scalar(value: f64, unit: Option<&str>) -> Self {
        Self {
            data: vec![value],
            unit: unit.map(str::to_string),
        }
    }
    pub fn vec3(x: f64, y: f64, z: f64, unit: Option<&str>) -> Self {
        Self {
            data: vec![x, y, z],
            unit: unit.map(str::to_string),
        }
    }
}

// ───────────────────────── entity addressing ─────────────────────────

/// A hierarchical client-side entity address, e.g. `uav1/sensor/cam0`.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct EntityRef {
    pub path: String,
    pub role: EntityRole,
    pub meta: Map<String>,
}

/// Binds a client entity to a stimulus or record port.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct EntityBinding {
    pub entity: EntityRef,
    pub port: String,
    /// `"stimulus"` | `"record"`.
    pub direction: String,
}

impl Default for EntityBinding {
    fn default() -> Self {
        Self {
            entity: EntityRef::default(),
            port: String::new(),
            direction: "stimulus".into(),
        }
    }
}

// ───────────────────────── network / sim config ─────────────────────────

/// What to simulate.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct NetworkRef {
    pub kind: NetworkRefKind,
    /// builtin model name, or a `compiled_module_id` (kind=handle). `ref` is a
    /// Rust keyword, so the field is `ref_` and renamed on the wire.
    #[serde(rename = "ref")]
    pub ref_: String,
    /// kind=handle: which registered model to create if the handle has >1.
    pub model_name: Option<String>,
    #[serde(with = "json_integer::map")]
    #[cfg_attr(
        feature = "schema",
        schemars(with = "std::collections::BTreeMap<String, i64>")
    )]
    #[cfg_attr(feature = "ts", ts(type = "{ [key in string]: bigint }"))]
    pub population_sizes: Map<i64>,
    pub params: Map<f64>,
}

/// Integration / streaming configuration.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SimConfig {
    pub dt_ms: f64,
    pub chunk_ms: f64,
    #[serde(with = "json_integer::option")]
    #[cfg_attr(feature = "schema", schemars(with = "Option<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint | null"))]
    pub seed: Option<i64>,
    pub mode: SimMode,
    pub duration_ms: Option<f64>,
}

impl Default for SimConfig {
    fn default() -> Self {
        Self {
            dt_ms: 0.1,
            chunk_ms: 10.0,
            seed: None,
            mode: SimMode::Stream,
            duration_ms: None,
        }
    }
}

// ───────────────────────── record / stimulus specs ─────────────────────────

/// One recording: client `port` name ← `observable` of `target` population.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct RecordTarget {
    pub port: String,
    pub target: String,
    pub observable: Observable,
    #[serde(with = "json_integer::vec")]
    #[cfg_attr(feature = "schema", schemars(with = "Vec<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "Array<bigint>"))]
    pub ids: Vec<i64>,
    pub cadence_ms: f64,
    /// Generic named multimeter recordables (model-specific: e.g. `g_ex`/`g_in`
    /// for conductance models, `w` for aeif, `rate` for rate models). Empty =
    /// just `observable`. Resolved via NEST multimeter `record_from`. (#10)
    pub recordables: Vec<String>,
}

impl Default for RecordTarget {
    fn default() -> Self {
        Self {
            port: String::new(),
            target: String::new(),
            observable: Observable::Vm,
            ids: Vec::new(),
            cadence_ms: 1.0,
            recordables: Vec::new(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct RecordSpec {
    pub targets: Vec<RecordTarget>,
}

/// One stimulus input port.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct StimulusTarget {
    pub port: String,
    pub target: String,
    pub kind: StimulusKind,
    #[serde(with = "json_integer::vec")]
    #[cfg_attr(feature = "schema", schemars(with = "Vec<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "Array<bigint>"))]
    pub ids: Vec<i64>,
    /// Named stimulus parameters beyond the scalar value, e.g. siegert_neuron's
    /// diffusion_connection `drift_factor` / `diffusion_factor`. (#10)
    pub params: Map<f64>,
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct StimulusSpec {
    pub targets: Vec<StimulusTarget>,
}

// ───────────────────────── provenance ─────────────────────────

/// Scientific-boundary discriminators carried on every opened session. Returned
/// data is a **raw simulation output of a specified model**, never a validated
/// reproduction: `calibrated_posterior=false`, `is_simulation_output=true`.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SimProvenance {
    pub network_ref: String,
    pub backend: String,
    #[serde(with = "json_integer::option")]
    #[cfg_attr(feature = "schema", schemars(with = "Option<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint | null"))]
    pub seed: Option<i64>,
    pub calibrated_posterior: bool,
    pub is_simulation_output: bool,
    pub advisory_only: bool,
    pub note: Option<String>,
}

impl Default for SimProvenance {
    fn default() -> Self {
        Self {
            network_ref: String::new(),
            backend: String::new(),
            seed: None,
            calibrated_posterior: false,
            is_simulation_output: true,
            advisory_only: true,
            note: None,
        }
    }
}

// ───────────────────────── simulation-service messages ─────────────────────────

/// Request a simulation: declare what to record and what to stimulate.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct OpenSession {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub network: NetworkRef,
    pub record: RecordSpec,
    pub stimulus: StimulusSpec,
    pub sim: SimConfig,
    pub bindings: Vec<EntityBinding>,
    /// Caller's [`CONTRACT_HASH`], carried in the handshake as an **advisory**
    /// identity signal (see [`ContractStatus`]): a mismatch is logged, not rejected —
    /// `ncp_version` is the hard compatibility gate. Defaults to our own hash so
    /// every session advertises it; `None` (serialized `null`) = not advertised.
    pub contract_hash: Option<String>,
    /// Authenticated caller claim; the transport adapter binds it to the peer
    /// certificate before opening any session state.
    pub identity: IdentityClaim,
    pub security_profile: String,
    pub security_state_digest: String,
    /// Explicit opt-in to a labelled 0.8→1.0 gateway. `false` is native-only.
    pub gateway_permitted: bool,
    /// Present only when this payload was emitted by a terminating gateway.
    pub gateway: Option<GatewayAttribution>,
}

impl Default for OpenSession {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "open_session".into(),
            session_id: String::new(),
            network: NetworkRef::default(),
            record: RecordSpec::default(),
            stimulus: StimulusSpec::default(),
            sim: SimConfig::default(),
            bindings: Vec::new(),
            contract_hash: Some(CONTRACT_HASH.to_string()),
            identity: IdentityClaim::default(),
            security_profile: String::new(),
            security_state_digest: String::new(),
            gateway_permitted: false,
            gateway: None,
        }
    }
}

/// Ack of `open_session` with resolved sizes and provenance.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SessionOpened {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub ok: bool,
    pub backend: String,
    #[serde(with = "json_integer::map")]
    #[cfg_attr(
        feature = "schema",
        schemars(with = "std::collections::BTreeMap<String, i64>")
    )]
    #[cfg_attr(feature = "ts", ts(type = "{ [key in string]: bigint }"))]
    pub resolved: Map<i64>,
    pub provenance: Option<SimProvenance>,
    pub error: Option<String>,
    /// Server's [`CONTRACT_HASH`] — the reply half of the handshake (see
    /// [`OpenSession::contract_hash`]). A client treats a hash difference as an
    /// **advisory** ([`ContractStatus::Mismatch`], logged not rejected); the version
    /// is the hard gate. `None` (serialized `null`) = not advertised.
    pub contract_hash: Option<String>,
    /// (0.8) Server-ISSUED session incarnation, present iff `ok`; clients echo
    /// `session.generation` on every subsequent session-scoped frame.
    pub session: Option<SessionRef>,
    /// Authoritative state version after processing the open request. A successful
    /// client uses this as the first mutation's `expected_state_version`.
    #[serde(with = "json_integer::unsigned")]
    #[cfg_attr(feature = "schema", schemars(with = "u64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub state_version: u64,
    /// Authenticated responder claim bound by the transport adapter.
    pub identity: IdentityClaim,
    pub security_profile: String,
    pub security_state_digest: String,
    pub gateway_permitted: bool,
    pub gateway: Option<GatewayAttribution>,
}

impl Default for SessionOpened {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "session_opened".into(),
            session_id: String::new(),
            // A default-constructed acknowledgement must never claim a session
            // opened successfully without the mandatory provenance identity.
            ok: false,
            backend: "unknown".into(),
            resolved: Map::new(),
            provenance: None,
            error: Some("session not opened".into()),
            contract_hash: Some(CONTRACT_HASH.to_string()),
            session: None,
            state_version: 0,
            identity: IdentityClaim::default(),
            security_profile: String::new(),
            security_state_digest: String::new(),
            gateway_permitted: false,
            gateway: None,
        }
    }
}

/// The values to inject this step (keyed by stimulus port). `t` is
/// producer-local monotonic seconds and is never compared across peers.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct StimulusFrame {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub t: f64,
    pub values: Map<ChannelValue>,
    /// (0.8) The session incarnation; nested in Step/Run it MUST equal the outer.
    pub session: SessionRef,
}

impl Default for StimulusFrame {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "stimulus_frame".into(),
            session_id: String::new(),
            t: 0.0,
            values: Map::new(),
            session: SessionRef::default(),
        }
    }
}

/// Advance one chunk; optional stimulus; returns an `ObservationFrame`.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct StepRequest {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub advance_ms: Option<f64>,
    pub stimulus: Option<StimulusFrame>,
    /// (0.8) REQUIRED: targets an open incarnation; `(session_id, generation)` live pair.
    pub session: SessionRef,
    pub operation: OperationContext,
    pub authority: AuthorityLease,
}

impl Default for StepRequest {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "step_request".into(),
            session_id: String::new(),
            advance_ms: None,
            stimulus: None,
            session: SessionRef::default(),
            operation: OperationContext::default(),
            authority: AuthorityLease::default(),
        }
    }
}

/// Batch: advance `duration_ms` holding a stimulus; returns an `ObservationFrame`.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct RunRequest {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub duration_ms: f64,
    pub stimulus: Option<StimulusFrame>,
    /// (0.8) REQUIRED: targets an open incarnation; `(session_id, generation)` live pair.
    pub session: SessionRef,
    pub operation: OperationContext,
    pub authority: AuthorityLease,
}

impl Default for RunRequest {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "run_request".into(),
            session_id: String::new(),
            duration_ms: 0.0,
            stimulus: None,
            session: SessionRef::default(),
            operation: OperationContext::default(),
            authority: AuthorityLease::default(),
        }
    }
}

/// Recorded data for one record port. `times`+`values` are parallel for analog;
/// `times`+`senders` are parallel for spikes.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug, Default)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct Observation {
    pub port: String,
    pub target: String,
    pub observable: Observable,
    pub times: Vec<f64>,
    pub values: Vec<f64>,
    #[serde(with = "json_integer::vec")]
    #[cfg_attr(feature = "schema", schemars(with = "Vec<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "Array<bigint>"))]
    pub senders: Vec<i64>,
    pub unit: Option<String>,
    /// Which named recordable this series carries (e.g. `g_ex`, `w`) when a port
    /// records more than the primary `observable`; `None` = the `observable`. (#10)
    pub recordable: Option<String>,
}

/// The returned neural data, keyed by a unique record-series name. The nested
/// `Observation.port` identifies the negotiated record port; distinct
/// `recordable` series from one port therefore remain representable. `t` is
/// this observation publisher's local monotonic creation time; a driving
/// sensor's position/time travels separately in `source`/`source_t`.
/// `sim_time_ms` is authoritative simulation time.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct ObservationFrame {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub t: f64,
    pub sim_time_ms: f64,
    pub records: Map<Observation>,
    #[serde(default = "missing_calibrated_posterior")]
    pub calibrated_posterior: bool,
    #[serde(default = "missing_is_simulation_output")]
    pub is_simulation_output: bool,
    /// Wire 0.8: this observation stream's own incarnation + position.
    pub stream: StreamPosition,
    /// The driving `SensorFrame.stream` on the observation PLANE (the cross-plane
    /// join key); omitted for the pull/RPC reply form (absence, not `seq == 0`).
    pub source: Option<StreamPosition>,
    /// The driving `SensorFrame.t`; `0.0` = unset.
    pub source_t: f64,
    /// The live session incarnation this stream belongs to.
    pub session: SessionRef,
    /// Present on step/run RPC replies; absent on ordinary observation-plane
    /// publication. Clients require it before claiming a mutating RPC completed.
    pub receipt: Option<ResponderReceipt>,
}

// Deserialize-only sentinels: omitted honesty-boundary fields must be detectable
// as INVALID, never fabricated into the safe values from `Default::default()`.
fn missing_calibrated_posterior() -> bool {
    true
}

fn missing_is_simulation_output() -> bool {
    false
}

impl Default for ObservationFrame {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "observation_frame".into(),
            session_id: String::new(),
            t: 0.0,
            sim_time_ms: 0.0,
            records: Map::new(),
            calibrated_posterior: false,
            is_simulation_output: true,
            stream: StreamPosition::default(),
            source: None,
            source_t: 0.0,
            session: SessionRef::default(),
            receipt: None,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct CloseSession {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    /// (0.8) REQUIRED: a delayed close for an old incarnation must not close a reopen.
    pub session: SessionRef,
    pub operation: OperationContext,
    pub authority: AuthorityLease,
}

impl Default for CloseSession {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "close_session".into(),
            session_id: String::new(),
            session: SessionRef::default(),
            operation: OperationContext::default(),
            authority: AuthorityLease::default(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SessionClosed {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub ok: bool,
    /// (0.8) the incarnation this close concerns; a delayed reply must attribute to it.
    pub session: SessionRef,
    pub receipt: ResponderReceipt,
}

/// Closed error-code vocabulary from the normative `contract/errors.v1.json`
/// registry. A package-snapshot test keeps this implementation list identical to
/// the registry used by every binding.
pub const REGISTERED_ERROR_CODES: &[&str] = &[
    "NCP-AUTH-001",
    "NCP-AUTH-002",
    "NCP-AUTH-003",
    "NCP-AUTH-004",
    "NCP-AUTH-005",
    "NCP-AUTH-006",
    "NCP-LEASE-001",
    "NCP-LEASE-002",
    "NCP-LEASE-003",
    "NCP-LEASE-004",
    "NCP-OP-001",
    "NCP-OP-002",
    "NCP-OP-003",
    "NCP-OP-004",
    "NCP-OP-005",
    "NCP-OP-006",
    "NCP-LIMIT-001",
    "NCP-LIMIT-002",
    "NCP-LIMIT-003",
    "NCP-LIMIT-004",
    "NCP-LIMIT-005",
    "NCP-LIMIT-006",
    "NCP-LIMIT-007",
    "NCP-LIMIT-008",
    "NCP-LIMIT-009",
    "NCP-PROFILE-001",
    "NCP-PROFILE-002",
    "NCP-PLANT-001",
    "NCP-PLANT-002",
    "NCP-PLANT-003",
    "NCP-STATE-001",
    "NCP-STATE-002",
    "NCP-STATE-003",
    "NCP-VERSION-001",
    "NCP-FEATURE-001",
    "NCP-AUDIT-001",
    "NCP-AUDIT-002",
    "NCP-GATEWAY-001",
    "NCP-GATEWAY-002",
    "NCP-WIRE-001",
    "NCP-INTERNAL-001",
];

/// Return whether `code` is a stable wire-1.0 error code.
pub fn is_registered_error_code(code: &str) -> bool {
    REGISTERED_ERROR_CODES.contains(&code)
}

/// Transport-level classification used by the infallible RPC containment path.
/// Domain handlers may return their own validated `ErrorFrame`; this enum keeps
/// generic transport wrappers from emitting an unclassified free-form failure.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum RpcErrorCode {
    /// The received selector or message failed semantic wire validation.
    InvalidMessage,
    /// Universal bounded-JSON ingress rejected the request. The exact stable
    /// limit code is retained rather than collapsed into a generic wire error.
    JsonLimit(crate::bounded_json::JsonLimitCode),
    /// The server contained a panic, invalid handler reply, unavailable backend,
    /// or another failure for which it cannot claim a narrower outcome.
    ContainedInternalFailure,
}

impl RpcErrorCode {
    /// Exact stable registry code placed on the wire.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidMessage => "NCP-WIRE-001",
            Self::JsonLimit(code) => code.stable_code(),
            Self::ContainedInternalFailure => "NCP-INTERNAL-001",
        }
    }

    const fn default_message(self) -> &'static str {
        match self {
            Self::InvalidMessage => "invalid NCP message",
            Self::JsonLimit(_) => "bounded JSON ingress rejected",
            Self::ContainedInternalFailure => "contained internal failure",
        }
    }
}

/// A typed, versioned failure reply. Error payloads are wire messages too: leaving
/// them unversioned lets a stale or misrouted peer bypass the same identity checks
/// applied to successful replies.
///
/// `code` is a closed contract value from `contract/errors.v1.json`; the
/// human-readable `error` string is diagnostic and never substitutes for it.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
pub struct ErrorFrame {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub code: String,
    pub error: String,
    pub session_id: Option<String>,
    pub request_kind: Option<String>,
    /// (0.8) Optional correlation copied from the rejected request; presence does NOT
    /// assert the generation is active. Present iff `session_id` is (copy both or neither).
    pub session: Option<SessionRef>,
    /// Optional terminal receipt. Pre-authentication/shape failures have no
    /// responder receipt; a committed rejection or cancellation does.
    pub receipt: Option<ResponderReceipt>,
}

impl ErrorFrame {
    /// Construct an error frame only when both its registry code and diagnostic
    /// message are explicit and valid.
    pub fn new(code: impl Into<String>, error: impl Into<String>) -> Result<Self, ValidationError> {
        let code = code.into();
        if !is_registered_error_code(&code) {
            return Err(ValidationError(format!(
                "unregistered NCP error code {code:?}"
            )));
        }
        let error = error.into();
        if error.is_empty() {
            return Err(ValidationError(
                "ErrorFrame diagnostic must be non-empty".into(),
            ));
        }
        Ok(Self {
            code,
            error,
            ..Self::default()
        })
    }
}

impl Default for ErrorFrame {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "error".into(),
            code: String::new(),
            error: String::new(),
            session_id: None,
            request_kind: None,
            session: None,
            receipt: None,
        }
    }
}

impl Default for SessionClosed {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "session_closed".into(),
            session_id: String::new(),
            ok: true,
            session: SessionRef::default(),
            receipt: ResponderReceipt::default(),
        }
    }
}

// ───────────────────────── closed-loop control messages ─────────────────────────

/// Declares a named channel a controller produces or consumes.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct ChannelSpec {
    pub name: String,
    pub kind: ChannelKind,
    pub unit: Option<String>,
    #[serde(with = "json_integer::option")]
    #[cfg_attr(feature = "schema", schemars(with = "Option<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint | null"))]
    pub size: Option<i64>,
    pub requirement: ChannelRequirement,
    pub description: Option<String>,
}

impl Default for ChannelSpec {
    fn default() -> Self {
        Self {
            name: String::new(),
            kind: ChannelKind::Scalar,
            unit: None,
            size: None,
            requirement: ChannelRequirement::Indeterminate,
            description: None,
        }
    }
}

/// Bounds the action plane. `max_speed_mps`, `geofence_radius_m` and
/// `command_timeout_ms` are enforced by the action-plane safety governor;
/// `max_tilt_rad` is advisory metadata and is **not** enforced in this layer
/// (no command-path clamp consumes it yet).
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SafetyLimits {
    pub max_speed_mps: Option<f64>,
    pub max_tilt_rad: Option<f64>,
    pub geofence_radius_m: Option<f64>,
    pub command_timeout_ms: f64,
}

impl Default for SafetyLimits {
    fn default() -> Self {
        Self {
            max_speed_mps: None,
            max_tilt_rad: None,
            geofence_radius_m: None,
            command_timeout_ms: 500.0,
        }
    }
}

/// Handshake: who the controller is and what it speaks.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct Capabilities {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub controller_id: String,
    pub role: Role,
    pub control_rate_hz: f64,
    pub sensor_channels: Vec<ChannelSpec>,
    pub command_channels: Vec<ChannelSpec>,
    pub codec_id: Option<String>,
    pub safety: SafetyLimits,
    pub identity: IdentityClaim,
    pub security_profile: String,
    pub security_state_digest: String,
    pub stable_capabilities: Vec<String>,
    /// `false` means native 1.0 only. A gateway is never inferred from absence.
    pub gateway_permitted: bool,
    pub plant_profile_digest: Option<String>,
    pub gateway: Option<GatewayAttribution>,
}

impl Default for Capabilities {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "capabilities".into(),
            controller_id: String::new(),
            role: Role::Controller,
            control_rate_hz: 20.0,
            sensor_channels: Vec::new(),
            command_channels: Vec::new(),
            codec_id: None,
            safety: SafetyLimits::default(),
            identity: IdentityClaim::default(),
            security_profile: String::new(),
            security_state_digest: String::new(),
            stable_capabilities: Vec::new(),
            gateway_permitted: false,
            plant_profile_digest: None,
            gateway: None,
        }
    }
}

/// Plant → controller: the latest sensed state. Its own `stream`/`t` identify the
/// sensor publication; a derived command correlates it through `source`/`source_t`
/// without copying those values into the command publisher's own identity.
/// Publishers stamp `stream.seq` starting at `1`, strictly increasing within a
/// canonical `stream.epoch`. `stream.seq = 0` is unstamped and rejected.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct SensorFrame {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub t: f64,
    pub frame_id: String,
    pub channels: Map<ChannelValue>,
    /// Wire 0.8: this sensor stream's own incarnation + position — the ONLY sequence
    /// loss/`LinkMonitor`/`ActionBuffer` accounting reads. The origin: no `source`;
    /// downstream `command`/`observation` `source` copies THIS `stream` position.
    pub stream: StreamPosition,
    /// The live session incarnation this stream belongs to (server-issued generation).
    pub session: SessionRef,
    /// Logical session id (transport-neutral); MUST equal the routing key's session
    /// segment. Carried in-payload so a non-keyed transport can interpret the frame.
    pub session_id: String,
}

impl Default for SensorFrame {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "sensor_frame".into(),
            t: 0.0,
            frame_id: "world".into(),
            channels: Map::new(),
            stream: StreamPosition::default(),
            session: SessionRef::default(),
            session_id: String::new(),
        }
    }
}

/// Controller → plant: the proposed actuation, with `mode`/`ttl_ms` safety
/// metadata.
///
/// `stream`/`t` belong to the command publisher and advance independently of the
/// sensor stream. A closed-loop command carries the driving sensor position/time
/// in `source`/`source_t`; consumers correlate on `source`, never by equating the
/// two publishers' `stream.seq` or clocks. `ActionBuffer` and
/// `CommandWatchdog` apply replay/freshness discipline to the command's own stream.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct CommandFrame {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub t: f64,
    pub frame_id: String,
    // Fail-safe: a wire frame that OMITS `mode` deserializes to HOLD, never to an
    // actuating mode — an untrusted/partial CommandFrame must not silently drive.
    // Programmatic construction follows the same invariant: `Default` is HOLD and
    // a controller must opt in to ACTIVE explicitly.
    #[serde(default = "default_command_mode")]
    pub mode: Mode,
    #[serde(default = "missing_command_ttl")]
    pub ttl_ms: f64,
    pub channels: Map<ChannelValue>,
    /// Packetized predictive control: future setpoints. `channels` is tick 0;
    /// `horizon[i]` applies at tick i+1, spaced `horizon_dt_ms` apart. The
    /// actuator replays these through dropouts (see `ActionBuffer`), bounded by
    /// `ttl_ms`. Empty = legacy single-step command. Backward compatible: a
    /// consumer that ignores `horizon` still reads `channels` (tick 0).
    pub horizon: Vec<Map<ChannelValue>>,
    pub horizon_dt_ms: Option<f64>,
    /// Wire 0.8: this command stream's own incarnation + position — the sequence
    /// `LinkMonitor`/`ActionBuffer` read for loss/dedup/supersession.
    pub stream: StreamPosition,
    /// The driving `SensorFrame.stream` (correlation only; never loss accounting).
    /// Present for a closed-loop Active command; omitted for negotiated open-loop.
    pub source: Option<StreamPosition>,
    /// The driving `SensorFrame.t`, for source-age checks; `0.0` = unset.
    pub source_t: f64,
    /// The live session incarnation this command stream belongs to.
    pub session: SessionRef,
    /// Logical session id (transport-neutral); MUST equal the routing key's session.
    pub session_id: String,
    /// Required for Active/HOLD authority-bearing commands. Authenticated ESTOP
    /// may omit it so a stale lease cannot suppress the fail-safe latch.
    pub authority: Option<AuthorityLease>,
}

/// Wire default for `CommandFrame.mode`: a frame that omits `mode` is HOLD, never
/// an actuating mode (fail-safe deserialization of an untrusted/partial frame).
fn default_command_mode() -> Mode {
    Mode::Hold
}

fn missing_command_ttl() -> f64 {
    f64::NAN
}

impl Default for CommandFrame {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "command_frame".into(),
            t: 0.0,
            frame_id: "world".into(),
            mode: Mode::Hold,
            ttl_ms: 200.0,
            channels: Map::new(),
            horizon: Vec::new(),
            horizon_dt_ms: None,
            stream: StreamPosition::default(),
            source: None,
            source_t: 0.0,
            session: SessionRef::default(),
            session_id: String::new(),
            authority: None,
        }
    }
}

/// Controller → plant / telemetry: loop health and mode. `t` is producer-local
/// monotonic seconds and is never compared across peers.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct ControlStatus {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub t: f64,
    pub mode: Mode,
    pub sim_time_ms: f64,
    pub loop_latency_ms: f64,
    pub safety_ok: bool,
    pub note: Option<String>,
    /// This status stream's own incarnation + strictly positive position. A
    /// publisher never repeats the JSON-safe maximum; it becomes silent until a
    /// fresh declaration mints another epoch.
    pub stream: StreamPosition,
    /// The live session incarnation.
    pub session: SessionRef,
    /// Logical session id (transport-neutral).
    pub session_id: String,
}

impl Default for ControlStatus {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "control_status".into(),
            t: 0.0,
            mode: Mode::Init,
            sim_time_ms: 0.0,
            loop_latency_ms: 0.0,
            safety_ok: true,
            note: None,
            stream: StreamPosition::default(),
            session: SessionRef::default(),
            session_id: String::new(),
        }
    }
}

/// Link-health telemetry from the seq-gap / CUSUM monitor (published on the
/// control plane). `burst=true` flags sustained loss — a possible jam — at which
/// point the only sound response is to fail safe, not add redundancy. `t` is
/// producer-local monotonic seconds and is never compared across peers.
#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[cfg_attr(feature = "ts", derive(ts_rs::TS), ts(export))]
#[cfg_attr(feature = "schema", derive(schemars::JsonSchema))]
#[serde(default)]
pub struct LinkStatus {
    #[serde(default = "missing_version")]
    pub ncp_version: String,
    #[serde(default = "missing_kind")]
    pub kind: String,
    pub session_id: String,
    pub t: f64,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub received: i64,
    #[serde(with = "json_integer::one")]
    #[cfg_attr(feature = "schema", schemars(with = "i64"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint"))]
    pub lost: i64,
    pub loss_rate: f64,
    pub burst: bool,
    /// The LinkStatus stream's own incarnation + strictly positive position —
    /// validate this before trusting any reported burst/loss/high-water state.
    pub stream: StreamPosition,
    /// The MONITORED stream's epoch + forward high-water seq; absent before the first
    /// valid observed frame (presence tracks `last_arrival_seq`). Its seq starts at
    /// 1 and is the forward high-water.
    pub observed_stream: Option<StreamPosition>,
    /// F-16: seq of the last valid in-epoch ARRIVAL (`< observed_stream.seq` under
    /// reordering; `==` it on forward arrival). Range starts at 1, cannot exceed the
    /// observed high-water, and presence tracks `observed_stream`.
    #[serde(with = "json_integer::option")]
    #[cfg_attr(feature = "schema", schemars(with = "Option<i64>"))]
    #[cfg_attr(feature = "ts", ts(type = "bigint | null"))]
    pub last_arrival_seq: Option<i64>,
    /// The live session incarnation.
    pub session: SessionRef,
}

impl Default for LinkStatus {
    fn default() -> Self {
        Self {
            ncp_version: ncp_version(),
            kind: "link_status".into(),
            session_id: String::new(),
            t: 0.0,
            received: 0,
            lost: 0,
            loss_rate: 0.0,
            burst: false,
            stream: StreamPosition::default(),
            observed_stream: None,
            last_arrival_seq: None,
            session: SessionRef::default(),
        }
    }
}

// ───────────────────────── version guard ─────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NcpVersionError(pub String);

impl std::fmt::Display for NcpVersionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}
impl std::error::Error for NcpVersionError {}

/// Compatible? For a pre-1.0 wire (major == 0) the protocol has no stability
/// guarantee yet, so *both* major and minor must match exactly (0.1 ≠ 0.9). For
/// a stable wire (major >= 1) the major alone decides compatibility (consumers
/// ignore unknown fields within a major). On a mismatch, `Err` when `strict`
/// else `Ok(false)`.
pub fn check_version(version: &str, strict: bool) -> Result<bool, NcpVersionError> {
    let parse_ver = |s: &str| -> Result<(u64, u64), NcpVersionError> {
        let err = || NcpVersionError(format!("unparseable ncp_version {s:?}"));
        let parse_part = |part: &str| -> Result<u64, NcpVersionError> {
            // `u64::from_str` accepts a leading `+`, while JavaScript's exact
            // grammar does not. Pin the language-neutral wire grammar first:
            // canonical ASCII decimal (no leading zeroes), bounded by u64::MAX.
            if part.is_empty()
                || !part.bytes().all(|byte| byte.is_ascii_digit())
                || (part.len() > 1 && part.starts_with('0'))
            {
                return Err(err());
            }
            part.parse::<u64>().map_err(|_| err())
        };
        // Strict: 1 or 2 dot-separated components, each a canonical ASCII
        // base-10 u64 with no leading zeroes, sign, whitespace, or trailing
        // junk. A malformed minor
        // ("2.GARBAGE") or extra component
        // ("0.2.x") must REJECT, never silently coerce to 0 — otherwise the
        // fail-closed guard becomes fail-open the moment our own minor is 0.
        let mut parts = s.split('.');
        let major = parts.next().ok_or_else(err)?;
        let major = parse_part(major)?;
        let minor: u64 = match parts.next() {
            // Missing minor (e.g. "1") is treated as minor 0...
            None => 0,
            // ...but a PRESENT minor must parse strictly.
            Some(m) => parse_part(m)?,
        };
        // No third component allowed (semver patch is not part of the wire id).
        if parts.next().is_some() {
            return Err(err());
        }
        Ok((major, minor))
    };
    let (got_major, got_minor) = parse_ver(version)?;
    let (want_major, want_minor) = parse_ver(NCP_VERSION)?;
    // Pre-1.0: minor is breaking, so require an exact (major, minor) match.
    // Stable (>=1.0): major-only compatibility.
    let compatible = if want_major == 0 {
        (got_major, got_minor) == (want_major, want_minor)
    } else {
        got_major == want_major
    };
    if !compatible {
        if strict {
            return Err(NcpVersionError(format!(
                "NCP version mismatch: got {version}, want {NCP_VERSION}"
            )));
        }
        return Ok(false);
    }
    Ok(true)
}

/// FNV-1a (64-bit) hex digest of the **canonicalized** normative wire contract
/// ([`canonical_proto`] of `proto/ncp.proto` — cosmetic comments/formatting
/// stripped, structured `wire string` / `wire key` annotations retained).
/// Peers exchange this alongside `ncp_version` in the control-plane handshake (the
/// `contract_hash` field of [`OpenSession`] / [`SessionOpened`]). A mismatch is an
/// advisory identity signal that is surfaced for logging; [`NCP_VERSION`] remains
/// the hard compatibility gate, unless a deployment explicitly opts into strict
/// [`verify_contract`]. A post-agreement schema mutation is therefore *detectable*
/// rather than silently coerced. The value is recomputed from the actual proto
/// by the `contract_hash_matches_proto` test, so a proto edit that forgets to bump
/// this constant fails CI — but a comment- or whitespace-only edit no longer flips it
/// (the churn the `v0.2.5`/`v0.2.6` releases documented).
///
/// # Why a hardcoded constant (and not computed at runtime)?
///
/// The value is **baked in, not derived at runtime**, and that is deliberate.
///
/// 1. **The proto is not on disk at runtime.** The conformance tests read a
///    crate-local snapshot of `proto/ncp.proto` at build/test time. A shipped
///    `ncp-core` binary, PyO3 wheel, or C ABI has no source fixture to hash, so
///    the value a running peer advertises must be embedded.
/// 2. **It is a contract *identity*, not a derived quantity.** Hardcoding makes
///    "which wire do I claim to speak" an explicit, greppable, reviewable fact, and
///    makes bumping it a deliberate, visible diff rather than an invisible
///    recompute.
/// 3. **It is the shared cross-language anchor.** Rust recomputes the hash from the
///    normative proto; Python and C expose the Rust-core constant, TypeScript mirrors
///    it, and the shared behavior corpus pins every peer to the same value. A skew is
///    caught in CI instead of silently producing different contract identities.
/// 4. **Drift is impossible to ship, not merely unlikely.** The
///    `contract_hash_matches_proto` test asserts `contract_hash_of_proto(proto) ==
///    CONTRACT_HASH`, so the constant cannot diverge from the proto it claims to
///    represent without failing CI. It is "hardcoded, but *provably equal* to the
///    computed value."
///
/// The considered alternative is to drop the constant entirely and compute it once at
/// startup from a compile-time-embedded proto:
/// `LazyLock::new(|| contract_hash_of_proto(include_str!(".../ncp.proto").as_bytes()))`.
/// That removes the forgot-to-bump class of errors, but loses the `const`-usability,
/// the greppable/reviewable value, and the "bumping it is a deliberate event"
/// property — and still needs a per-language anchor for cross-language parity. The
/// constant-plus-CI-guard form is kept on purpose. See `VERSIONING.md` (§"Contract
/// hash") for the full rationale and the handshake design.
pub const CONTRACT_HASH: &str = "163acc57d8a62b66";

/// FNV-1a (64-bit) hex digest of `bytes`. Dependency-free (no sha/digest crate),
/// adequate for the contract-pinning integrity-vs-accidental-drift use. It is
/// **not** a cryptographic MAC — adversarial integrity is the transport's job
/// (mTLS); this detects unintended/forgotten contract drift between peers.
pub fn fnv1a_hex(bytes: &[u8]) -> String {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for &b in bytes {
        h ^= b as u64;
        h = h.wrapping_mul(0x0000_0100_0000_01b3);
    }
    format!("{h:016x}")
}

/// Canonicalize a `.proto` source so the contract hash depends only on the
/// *wire-semantic* definition — the message/field/enum structure — not on
/// cosmetic comments, formatting, or naming-only declarations (`package`,
/// top-level `option`). The protobuf `syntax`, imports, and NCP's JSON enum
/// `wire string` and transport `wire key` annotations are semantic and remain in
/// the digest.
///
/// Protobuf's wire encoding is determined by field numbers, types, and modifiers
/// — **never** by comments, by the `package` namespace, or by file options. So a
/// purely *naming* change (e.g. renaming the package `engram.ncp.v0 → ncp.v0` to
/// decouple the protocol's identity from a consumer) leaves the wire identical and
/// MUST leave [`CONTRACT_HASH`] identical too. This pass therefore:
/// 1. removes cosmetic `//` line and `/* … */` block comments — respecting string
///    literals — while converting `// wire string "..."` and `// wire key "..."`
///    annotations into hashed canonical tokens (those comments define NCP's JSON
///    enum projection and transport addressing),
/// 2. drops naming/codegen-only declaration lines (`package`/top-level `option`),
/// 3. trims each line and drops blank lines.
///
/// The result is that cosmetic and naming changes are hash-neutral, while any real
/// wire change (add/remove/retype a field, change an enum value or its JSON wire
/// string, switch proto syntax) still flips the hash. Dependency-free (no
/// protoc/buf): adequate for the accidental-drift
/// detection this hash targets (adversarial integrity is the transport's job).
pub fn canonical_proto(bytes: &[u8]) -> Vec<u8> {
    let text = String::from_utf8_lossy(bytes);
    let mut out = String::with_capacity(text.len());
    let mut chars = text.chars().peekable();
    let mut in_string: Option<char> = None;
    while let Some(c) = chars.next() {
        if let Some(quote) = in_string {
            out.push(c);
            if c == '\\' {
                // Preserve the escaped char verbatim (e.g. \" or \\).
                if let Some(next) = chars.next() {
                    out.push(next);
                }
            } else if c == quote {
                in_string = None;
            }
            continue;
        }
        match c {
            '"' | '\'' => {
                in_string = Some(c);
                out.push(c);
            }
            '/' if chars.peek() == Some(&'/') => {
                chars.next(); // consume the second '/'
                let mut comment = String::new();
                for n in chars.by_ref() {
                    if n == '\n' {
                        break;
                    }
                    comment.push(n);
                }
                // Most comments are cosmetic. These annotations are different:
                // they are the normative proto-enum -> NCP-JSON mapping and must
                // affect contract identity even though protobuf itself ignores them.
                let annotation = comment.trim();
                for (prefix, token) in [
                    ("wire string \"", "@ncp_json_wire"),
                    ("wire key \"", "@ncp_transport_key"),
                ] {
                    if let Some(rest) = annotation.strip_prefix(prefix) {
                        if let Some(end) = rest.find('"') {
                            out.push(' ');
                            out.push_str(token);
                            out.push_str("(\"");
                            out.push_str(&rest[..end]);
                            out.push_str("\")");
                        }
                    }
                }
                out.push('\n');
            }
            '/' if chars.peek() == Some(&'*') => {
                // Block comment: skip until the closing `*/`.
                chars.next(); // consume '*'
                let mut prev = '\0';
                for n in chars.by_ref() {
                    if prev == '*' && n == '/' {
                        break;
                    }
                    prev = n;
                }
            }
            _ => out.push(c),
        }
    }
    // Normalize whitespace and drop naming/codegen-only declarations. `syntax`
    // and `import` remain: proto2/proto3 presence/default semantics and imported
    // type definitions can change the contract.
    let normalized = out
        .lines()
        .map(str::trim_start)
        .map(str::trim_end)
        .filter(|line| !line.is_empty())
        .filter(|line| !(line.starts_with("package ") || line.starts_with("option ")))
        .collect::<Vec<_>>()
        .join("\n");
    normalized.into_bytes()
}

/// The contract hash of a `.proto` source: [`fnv1a_hex`] of its
/// [`canonical_proto`] form. This is the value pinned in [`CONTRACT_HASH`] and
/// the function a peer uses to recompute the contract identity from its own copy
/// of the proto, so two peers agree iff their *semantic* contracts agree —
/// independent of comments or formatting.
pub fn contract_hash_of_proto(bytes: &[u8]) -> String {
    fnv1a_hex(&canonical_proto(bytes))
}

/// Outcome of comparing a peer's advertised [`CONTRACT_HASH`] to ours.
///
/// This is **advisory**: a [`ContractStatus::Mismatch`] does *not* fail the
/// handshake. [`NCP_VERSION`] (via [`check_version`]) is the *compatibility* gate —
/// "can we speak the same wire at all"; the contract hash is a finer *identity*
/// signal — "are we on the exact same contract revision". Conflating the two
/// (fail-closed on hash) would break a version-compatible flow the moment one peer
/// added an optional field or renamed a non-wire declaration. So a mismatch is
/// surfaced for logging/telemetry, and the session proceeds. (The hash is not a
/// cryptographic MAC; adversarial integrity is the transport's job — mTLS.)
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContractStatus {
    /// Peer advertised a hash equal to ours — same contract revision.
    Match,
    /// Peer advertised no hash (older/minimal peer). Accepted within a compatible version.
    NotAdvertised,
    /// Peer advertised a *different* hash. Advisory only — log it; the session still opens.
    Mismatch { peer: String },
}

impl ContractStatus {
    /// `true` unless the peer advertised a different hash.
    pub fn is_match(&self) -> bool {
        !matches!(self, ContractStatus::Mismatch { .. })
    }
    /// A human-readable advisory string for a mismatch (for logging), else `None`.
    pub fn advisory(&self) -> Option<String> {
        match self {
            ContractStatus::Mismatch { peer } => Some(format!(
                "NCP contract-hash differs: peer {peer:?}, ours {CONTRACT_HASH:?} — \
                 versions are compatible so the session proceeds, but the peers are on \
                 different contract revisions (advisory)"
            )),
            _ => None,
        }
    }
}

/// Classify a peer-advertised contract hash against ours (advisory; see
/// [`ContractStatus`]). Never fails — `None` = not advertised, `Some(==ours)` =
/// match, `Some(!=ours)` = mismatch.
pub fn contract_status(peer_hash: Option<&str>) -> ContractStatus {
    match peer_hash {
        None => ContractStatus::NotAdvertised,
        Some(h) if h == CONTRACT_HASH => ContractStatus::Match,
        Some(h) => ContractStatus::Mismatch {
            peer: h.to_string(),
        },
    }
}

/// **Strict** contract verification (opt-in): a typed error on hash mismatch.
/// Most callers want [`negotiate`] (advisory). Use this only where a deployment
/// has decided that an exact contract-revision match is mandatory and a mismatch
/// must fail closed (e.g. a safety-certified configuration).
pub fn verify_contract(peer_hash: Option<&str>) -> Result<(), NcpVersionError> {
    match contract_status(peer_hash) {
        ContractStatus::Mismatch { peer } => Err(NcpVersionError(format!(
            "NCP contract-hash mismatch: peer {peer:?}, want {CONTRACT_HASH:?}"
        ))),
        _ => Ok(()),
    }
}

/// Handshake gate a control-plane `open_session` calls. The `(major, minor)`
/// version MUST be compatible (fail-closed [`NcpVersionError`] otherwise) — this is
/// the wire-compatibility gate. The contract hash is returned as an **advisory**
/// [`ContractStatus`] (a mismatch does NOT fail the handshake; the caller logs it).
/// This separation lets additive optional fields and non-wire renames evolve the
/// contract without breaking version-compatible peers.
pub fn negotiate(
    peer_version: &str,
    peer_contract_hash: Option<&str>,
) -> Result<ContractStatus, NcpVersionError> {
    check_version(peer_version, true)?;
    Ok(contract_status(peer_contract_hash))
}

/// Best-effort version diagnostic for a raw inbound frame, so a receiver can log
/// WHY a frame was dropped — the data plane otherwise drops silently. Returns
/// `Some(err)` when the frame carries an incompatible `ncp_version`, a non-string
/// one, or (since wire 0.6, where the version is mandatory) none at all; `None`
/// when the frame is compatible or fails bounded JSON ingress (nothing safe to
/// diagnose). This best-effort fallback never reparses rejected bytes without
/// the universal frame, structure, and duplicate-key limits.
pub fn diagnose_version(bytes: &[u8]) -> Option<NcpVersionError> {
    let v = crate::bounded_json::parse_value(bytes).ok()?;
    let Some(field) = v.get("ncp_version") else {
        return Some(NcpVersionError(
            "frame carries no ncp_version (mandatory since wire 0.6)".into(),
        ));
    };
    let Some(ver) = field.as_str() else {
        return Some(NcpVersionError(format!(
            "ncp_version must be a string, got {field}"
        )));
    };
    check_version(ver, true).err()
}

/// Typed hot-path wire acceptance for the closed-loop data-plane frames
/// (`SensorFrame` / `CommandFrame` / `ObservationFrame`).
///
/// The data planes run at 20–1000 Hz, so ingress acceptance works on the
/// already-deserialized typed frame — one parse, no `serde_json::Value` detour:
/// an absent `ncp_version`/`kind` deserializes to `""` (see [`missing_version`])
/// and is rejected here, never fabricated. Prefer [`decode_validated`], which
/// combines parse + `kind` check + [`validate_wire`](WireFrame::validate_wire).
///
/// A receiver DROPS a rejected frame (log the error; never actuate on it). The
/// safety layers ([`crate::resilience::ActionBuffer`] /
/// [`crate::safety::CommandWatchdog`]) independently reject `seq < 1`, so a
/// bypassed ingress still cannot refresh liveness — defense in depth, not a
/// substitute for this gate.
pub trait WireFrame: serde::de::DeserializeOwned {
    /// The `kind` discriminator this type carries on the wire.
    const KIND: &'static str;
    /// Minimum wire-legal `seq` for this kind (see [`validate`]'s seq bounds).
    const MIN_SEQ: i64;
    fn wire_kind(&self) -> &str;
    fn wire_version(&self) -> &str;
    fn wire_seq(&self) -> i64;

    /// Accept/reject this frame at a data-plane ingress: the carried version must
    /// be compatible ([`check_version`], fail-closed — `""` from an absent field
    /// is rejected as unparseable) and `seq` must meet the wire bound.
    fn validate_wire(&self) -> Result<(), ValidationError> {
        if self.wire_kind() != Self::KIND {
            return Err(ValidationError(format!(
                "{}: kind mismatch (got {:?})",
                Self::KIND,
                self.wire_kind()
            )));
        }
        check_version(self.wire_version(), true).map_err(|e| {
            ValidationError(format!("{}: incompatible ncp_version: {e}", Self::KIND))
        })?;
        if !(JSON_SAFE_INTEGER_MIN..=JSON_SAFE_INTEGER_MAX).contains(&self.wire_seq()) {
            return Err(ValidationError(format!(
                "{}: seq {} is outside the exact NCP JSON integer range [{}, {}]",
                Self::KIND,
                self.wire_seq(),
                JSON_SAFE_INTEGER_MIN,
                JSON_SAFE_INTEGER_MAX
            )));
        }
        if self.wire_seq() < Self::MIN_SEQ {
            return Err(ValidationError(format!(
                "{}: seq {} < {} (wire 0.6 requires a stamped, strictly-increasing seq)",
                Self::KIND,
                self.wire_seq(),
                Self::MIN_SEQ
            )));
        }
        self.validate_payload()
    }

    /// Kind-specific typed checks beyond the common envelope.
    fn validate_payload(&self) -> Result<(), ValidationError> {
        Ok(())
    }
}

impl WireFrame for SensorFrame {
    const KIND: &'static str = "sensor_frame";
    const MIN_SEQ: i64 = 1;
    fn wire_kind(&self) -> &str {
        &self.kind
    }
    fn wire_version(&self) -> &str {
        &self.ncp_version
    }
    fn wire_seq(&self) -> i64 {
        self.stream.seq
    }
    fn validate_payload(&self) -> Result<(), ValidationError> {
        validate_stream_identity(
            &self.stream,
            &self.session,
            &self.session_id,
            "sensor_frame",
        )?;
        if !self.t.is_finite() {
            return Err(ValidationError("sensor_frame.t must be finite".into()));
        }
        if self.frame_id.is_empty() || self.frame_id.chars().any(char::is_control) {
            return Err(ValidationError(
                "sensor_frame.frame_id must be non-empty and contain no control characters".into(),
            ));
        }
        validate_channel_map_finite(&self.channels, "sensor_frame.channels", false)
    }
}

fn validate_channel_map_finite(
    channels: &Map<ChannelValue>,
    path: &str,
    require_data: bool,
) -> Result<(), ValidationError> {
    for (name, channel) in channels {
        if name.is_empty() || name.chars().any(char::is_control) {
            return Err(ValidationError(format!(
                "{path} channel name {name:?} must be non-empty and contain no control characters"
            )));
        }
        if require_data && channel.data.is_empty() {
            return Err(ValidationError(format!(
                "{path}[{name:?}].data must not be empty"
            )));
        }
        if channel.data.iter().any(|value| !value.is_finite()) {
            return Err(ValidationError(format!(
                "{path}[{name:?}].data must contain only finite numbers"
            )));
        }
    }
    Ok(())
}

/// A canonical lowercase UUIDv4: `8-4-4-4-12` lowercase-hex with version nibble `4`
/// and variant nibble in `[89ab]`. Compared for EQUALITY ONLY (never ordered).
/// True iff `s` is a canonical lowercase UUIDv4 (`8-4-4-4-12` hex with the version
/// nibble `4` and a `8/9/a/b` variant nibble) — the wire-0.8 form for a
/// `stream.epoch` / `session.generation`. Equality-only: never ordered or parsed.
pub fn is_canonical_uuid_v4(s: &str) -> bool {
    let b = s.as_bytes();
    if b.len() != 36 {
        return false;
    }
    for (i, &c) in b.iter().enumerate() {
        let ok = match i {
            8 | 13 | 18 | 23 => c == b'-',
            14 => c == b'4',
            19 => matches!(c, b'8' | b'9' | b'a' | b'b'),
            _ => matches!(c, b'0'..=b'9' | b'a'..=b'f'),
        };
        if !ok {
            return false;
        }
    }
    true
}

/// Validate a transport-neutral `session_id` string: 1..=64 bytes and a safe single
/// key segment (reuses [`crate::keys::valid_id_segment`] — no `/ * $ # ?`, no
/// whitespace/control), case-sensitive exact equality.
fn validate_session_id_str(id: &str, who: &str) -> Result<(), ValidationError> {
    if id.is_empty() || id.len() > 64 {
        return Err(ValidationError(format!("{who} must be 1..=64 bytes")));
    }
    if !crate::keys::valid_id_segment(id) {
        return Err(ValidationError(format!(
            "{who} {id:?} is not a safe single key segment"
        )));
    }
    Ok(())
}

/// Validate the wire-0.8 stream identity carried on every session-scoped frame:
/// `stream.epoch` and `session.generation` are canonical UUIDv4s and `session_id` is
/// well-formed. `stream.seq`'s range/`MIN_SEQ` bound is checked by the common
/// [`WireFrame::validate_wire`] path via [`WireFrame::wire_seq`].
fn validate_stream_identity(
    stream: &StreamPosition,
    session: &SessionRef,
    session_id: &str,
    who: &str,
) -> Result<(), ValidationError> {
    if !is_canonical_uuid_v4(&stream.epoch) {
        return Err(ValidationError(format!(
            "{who}.stream.epoch must be a canonical lowercase UUIDv4"
        )));
    }
    if !is_canonical_uuid_v4(&session.generation) {
        return Err(ValidationError(format!(
            "{who}.session.generation must be a canonical lowercase UUIDv4"
        )));
    }
    validate_session_id_str(session_id, &format!("{who}.session_id"))
}

/// Validate an optional `source` correlation reference (absent = no source; never a
/// `seq == 0` sentinel): when present, `epoch` is a canonical UUIDv4 and `seq >= 1`.
fn validate_source(source: &Option<StreamPosition>, who: &str) -> Result<(), ValidationError> {
    if let Some(src) = source {
        if !is_canonical_uuid_v4(&src.epoch) {
            return Err(ValidationError(format!(
                "{who}.source.epoch must be a canonical lowercase UUIDv4"
            )));
        }
        if !(1..=JSON_SAFE_INTEGER_MAX).contains(&src.seq) {
            return Err(ValidationError(format!(
                "{who}.source.seq must be within 1..=2^53-1"
            )));
        }
    }
    Ok(())
}

impl WireFrame for CommandFrame {
    const KIND: &'static str = "command_frame";
    const MIN_SEQ: i64 = 1;
    fn wire_kind(&self) -> &str {
        &self.kind
    }
    fn wire_version(&self) -> &str {
        &self.ncp_version
    }
    fn wire_seq(&self) -> i64 {
        self.stream.seq
    }
    fn validate_payload(&self) -> Result<(), ValidationError> {
        validate_stream_identity(
            &self.stream,
            &self.session,
            &self.session_id,
            "command_frame",
        )?;
        validate_source(&self.source, "command_frame")?;
        if !self.mode.is_canonical_wire_value() {
            return Err(ValidationError(
                "command_frame.mode has a non-canonical in-memory representation".into(),
            ));
        }
        if !self.t.is_finite() {
            return Err(ValidationError("command_frame.t must be finite".into()));
        }
        if self.frame_id.is_empty() || self.frame_id.chars().any(char::is_control) {
            return Err(ValidationError(
                "command_frame.frame_id must be non-empty and contain no control characters".into(),
            ));
        }
        // `missing_command_ttl()` uses NaN as a deserialize-only sentinel so an
        // Active frame that omitted ttl_ms cannot inherit authority. Non-Active
        // frames may omit the field; their sentinel is harmless because those
        // modes never actuate and the watchdog treats it as immediately stale.
        if self.ttl_ms.is_infinite() || (self.ttl_ms.is_nan() && matches!(self.mode, Mode::Active))
        {
            return Err(ValidationError(
                "command_frame.ttl_ms must be finite".into(),
            ));
        }
        if self.horizon_dt_ms.is_some_and(|value| !value.is_finite()) {
            return Err(ValidationError(
                "command_frame.horizon_dt_ms must be finite or null".into(),
            ));
        }
        if self.horizon.len() > MAX_HORIZON_STEPS {
            return Err(ValidationError(format!(
                "command_frame.horizon exceeds the {MAX_HORIZON_STEPS}-step resource ceiling"
            )));
        }
        validate_channel_map_finite(&self.channels, "command_frame.channels", false)?;
        for (index, step) in self.horizon.iter().enumerate() {
            validate_channel_map_finite(step, &format!("command_frame.horizon[{index}]"), false)?;
        }
        if self.mode == Mode::Active {
            if !self.ttl_ms.is_finite() || self.ttl_ms <= 0.0 {
                return Err(ValidationError(
                    "command_frame: Active mode requires an explicit finite ttl_ms > 0".into(),
                ));
            }
            if self.channels.is_empty() {
                return Err(ValidationError(
                    "command_frame: Active mode requires at least one command channel".into(),
                ));
            }
            validate_channel_map_finite(&self.channels, "command_frame.channels", true)?;
            for (index, step) in self.horizon.iter().enumerate() {
                if step.is_empty() {
                    return Err(ValidationError(format!(
                        "command_frame.horizon[{index}] must not be empty"
                    )));
                }
                validate_channel_map_finite(
                    step,
                    &format!("command_frame.horizon[{index}]"),
                    true,
                )?;
            }
            if !self.horizon.is_empty()
                && self
                    .horizon_dt_ms
                    .is_none_or(|dt| !dt.is_finite() || dt <= 0.0)
            {
                return Err(ValidationError(
                    "command_frame: a predictive horizon requires finite horizon_dt_ms > 0".into(),
                ));
            }
            if let Some(dt) = self.horizon_dt_ms.filter(|_| !self.horizon.is_empty()) {
                let by_ttl = crate::resilience::max_horizon_len(self.ttl_ms, dt);
                if !self.ttl_ms.is_finite()
                    || self.horizon.len() > MAX_HORIZON_STEPS
                    || self.horizon.len() > by_ttl
                {
                    return Err(ValidationError(format!(
                        "command_frame.horizon has {} steps but the strict watchdog deadline permits at most {by_ttl} (future step time < ttl_ms) and at most {MAX_HORIZON_STEPS}", self.horizon.len()
                    )));
                }
            }
        }
        Ok(())
    }
}

impl WireFrame for ObservationFrame {
    /// Wire 0.8: every observation frame carries its OWN `stream` position
    /// (`stream.seq >= 1`); the pull/RPC reply form is distinguished by `source`
    /// ABSENCE (not a `seq == 0` sentinel), and a plane frame's `source` echoes the
    /// driving `SensorFrame.stream` (the cross-plane join key).
    const KIND: &'static str = "observation_frame";
    const MIN_SEQ: i64 = 1;
    fn wire_kind(&self) -> &str {
        &self.kind
    }
    fn wire_version(&self) -> &str {
        &self.ncp_version
    }
    fn wire_seq(&self) -> i64 {
        self.stream.seq
    }

    fn validate_payload(&self) -> Result<(), ValidationError> {
        validate_stream_identity(
            &self.stream,
            &self.session,
            &self.session_id,
            "observation_frame",
        )?;
        validate_source(&self.source, "observation_frame")?;
        if !self.t.is_finite() || !self.sim_time_ms.is_finite() {
            return Err(ValidationError(
                "observation_frame.t and sim_time_ms must be finite".into(),
            ));
        }
        if self.calibrated_posterior || !self.is_simulation_output {
            return Err(ValidationError(
                "observation_frame: missing or dishonest scientific-boundary discriminators".into(),
            ));
        }
        for (series, observation) in &self.records {
            if series.is_empty() || series.chars().any(char::is_control) {
                return Err(ValidationError(format!(
                    "observation_frame record-series key {series:?} must be non-empty and contain no control characters"
                )));
            }
            if observation.port.is_empty() {
                return Err(ValidationError(format!(
                    "observation_frame.records[{series:?}].port must be non-empty"
                )));
            }
            if observation.target.is_empty() {
                return Err(ValidationError(format!(
                    "observation_frame.records[{series:?}].target must be non-empty"
                )));
            }
            if matches!(observation.observable, Observable::Unknown(_)) {
                return Err(ValidationError(format!(
                    "observation_frame.records[{series:?}].observable is unknown"
                )));
            }
            if !observation.values.is_empty() && !observation.senders.is_empty() {
                return Err(ValidationError(format!(
                    "observation_frame.records[{series:?}] cannot carry values and senders in one series"
                )));
            }
            let payload_len = observation.values.len().max(observation.senders.len());
            if observation.times.len() != payload_len
                && (!observation.times.is_empty() || payload_len > 0)
            {
                return Err(ValidationError(format!(
                    "observation_frame.records[{series:?}] parallel arrays disagree: times={}, values={}, senders={}",
                    observation.times.len(),
                    observation.values.len(),
                    observation.senders.len()
                )));
            }
            if observation
                .times
                .iter()
                .chain(observation.values.iter())
                .any(|value| !value.is_finite())
            {
                return Err(ValidationError(format!(
                    "observation_frame.records[{series:?}] times/values must be finite"
                )));
            }
            for (index, sender) in observation.senders.iter().enumerate() {
                if !(JSON_SAFE_INTEGER_MIN..=JSON_SAFE_INTEGER_MAX).contains(sender) {
                    return Err(ValidationError(format!(
                        "observation_frame.records[{series:?}].senders[{index}]={sender} is outside the exact NCP JSON integer range"
                    )));
                }
            }
        }
        Ok(())
    }
}

/// Parse + accept a data-plane frame in one call: typed `serde_json` decode, then
/// a `kind` check (a misrouted or kind-less frame is rejected, not silently
/// decoded into an all-default value), then [`WireFrame::validate_wire`]. This is
/// the ingress every data-plane subscriber should run before acting on a frame.
pub fn decode_validated<T: WireFrame>(bytes: &[u8]) -> Result<T, ValidationError> {
    // Serde's derived named-struct visitor also accepts positional JSON arrays.
    // Parse once to Value and run the strict map-only raw contract before the
    // typed conversion, otherwise e.g. `channels: {"x": []}` can become a
    // default ChannelValue even though every schema/peer requires an object.
    let value = crate::bounded_json::parse_value(bytes).map_err(|e| {
        ValidationError(format!(
            "{}: unparseable or over-budget frame: {e}",
            T::KIND
        ))
    })?;
    decode_validated_value(value)
}

fn decode_validated_value<T: WireFrame>(value: serde_json::Value) -> Result<T, ValidationError> {
    if message_kind(&value) != Some(T::KIND) {
        return Err(ValidationError(format!(
            "kind mismatch: expected {:?}, got {:?}",
            T::KIND,
            message_kind(&value)
        )));
    }
    validate(&value)?;
    let frame: T = serde_json::from_value(value)
        .map_err(|e| ValidationError(format!("{}: invalid wire shape: {e}", T::KIND)))?;
    Ok(frame)
}

/// Perception-plane publisher gate shared by every transport binding.
pub fn validate_sensor_plane_payload(bytes: &[u8]) -> Result<(), ValidationError> {
    decode_validated::<SensorFrame>(bytes).map(drop)
}

/// Perception-plane gate bound to both the session encoded in the concrete
/// transport key and the live generation returned by `SessionOpened`.
pub fn decode_sensor_plane_payload_for(
    session_id: &str,
    expected_session: &SessionRef,
    bytes: &[u8],
) -> Result<SensorFrame, ValidationError> {
    if !crate::keys::valid_id_segment(session_id) {
        return Err(ValidationError(format!(
            "invalid perception-plane session id {session_id:?}"
        )));
    }
    let sensor = decode_validated::<SensorFrame>(bytes)?;
    validate_data_plane_session_binding(
        "sensor_frame",
        session_id,
        expected_session,
        &sensor.session_id,
        &sensor.session,
    )?;
    Ok(sensor)
}

/// Validate a perception-plane payload against its concrete route and live
/// session generation without retaining the decoded frame.
pub fn validate_sensor_plane_payload_for(
    session_id: &str,
    expected_session: &SessionRef,
    bytes: &[u8],
) -> Result<(), ValidationError> {
    decode_sensor_plane_payload_for(session_id, expected_session, bytes).map(drop)
}

// Decode once so the public generic and live-session-bound gates make their
// decisions from the same bounded, duplicate-free document. ESTOP is safety
// privileged only after this complete wire envelope has been authenticated and
// fenced; it never bypasses kind/version/stream/session validation.
fn decode_command_plane_payload(bytes: &[u8]) -> Result<CommandFrame, ValidationError> {
    let value = crate::bounded_json::parse_value(bytes).map_err(|e| {
        ValidationError(format!(
            "command_frame: unparseable or over-budget frame: {e}"
        ))
    })?;
    decode_validated_value(value)
}

/// Action-plane publisher gate. Every command, including ESTOP, must carry a
/// complete compatible wire envelope. ESTOP may omit an authority lease only;
/// it does not bypass envelope or session validation.
pub fn validate_command_plane_payload(bytes: &[u8]) -> Result<(), ValidationError> {
    decode_command_plane_payload(bytes).map(drop)
}

/// Action-plane gate bound to the concrete transport-key session and current live
/// generation. This applies to ESTOP before callback or latch mutation; ESTOP may
/// omit authority, not the complete envelope or live binding.
pub fn decode_command_plane_payload_for(
    session_id: &str,
    expected_session: &SessionRef,
    bytes: &[u8],
) -> Result<CommandFrame, ValidationError> {
    if !crate::keys::valid_id_segment(session_id) {
        return Err(ValidationError(format!(
            "invalid action-plane session id {session_id:?}"
        )));
    }
    let command = decode_command_plane_payload(bytes)?;
    validate_data_plane_session_binding(
        "command_frame",
        session_id,
        expected_session,
        &command.session_id,
        &command.session,
    )?;
    Ok(command)
}

/// Validate an action-plane payload against its concrete route and live session
/// generation without retaining the decoded frame.
pub fn validate_command_plane_payload_for(
    session_id: &str,
    expected_session: &SessionRef,
    bytes: &[u8],
) -> Result<(), ValidationError> {
    decode_command_plane_payload_for(session_id, expected_session, bytes).map(drop)
}

/// Observation-plane publisher gate. A plane-published frame MUST carry a `source`
/// (echoing the driving `SensorFrame.stream`); a `source`-less frame is the pull/RPC
/// reply form and is not valid on the plane.
pub fn validate_observation_plane_payload(bytes: &[u8]) -> Result<(), ValidationError> {
    let observation = decode_validated::<ObservationFrame>(bytes)?;
    if observation.source.is_none() {
        return Err(ValidationError(
            "observation_frame: a plane-published frame requires a `source` (the driving sensor \
             position); its absence is the pull/RPC reply form"
                .into(),
        ));
    }
    if observation.receipt.is_some() {
        return Err(ValidationError(
            "observation_frame: a plane-published frame must not carry an RPC responder receipt"
                .into(),
        ));
    }
    Ok(())
}

/// Observation-plane publisher/subscriber gate bound to the concrete transport-key
/// session and current live generation.
pub fn decode_observation_plane_payload_for(
    session_id: &str,
    expected_session: &SessionRef,
    bytes: &[u8],
) -> Result<ObservationFrame, ValidationError> {
    if !crate::keys::valid_id_segment(session_id) {
        return Err(ValidationError(format!(
            "invalid observation-plane session id {session_id:?}"
        )));
    }
    let observation = decode_validated::<ObservationFrame>(bytes)?;
    if observation.source.is_none() {
        return Err(ValidationError(
            "observation_frame: a plane-published frame requires a `source` (the driving sensor \
             position); its absence is the pull/RPC reply form"
                .into(),
        ));
    }
    if observation.receipt.is_some() {
        return Err(ValidationError(
            "observation_frame: a plane-published frame must not carry an RPC responder receipt"
                .into(),
        ));
    }
    validate_data_plane_session_binding(
        "observation_frame",
        session_id,
        expected_session,
        &observation.session_id,
        &observation.session,
    )?;
    Ok(observation)
}

/// Validate an observation-plane payload against its concrete route and live
/// session generation without retaining the decoded frame.
pub fn validate_observation_plane_payload_for(
    session_id: &str,
    expected_session: &SessionRef,
    bytes: &[u8],
) -> Result<(), ValidationError> {
    decode_observation_plane_payload_for(session_id, expected_session, bytes).map(drop)
}

/// Require a frame to target the exact live session incarnation selected by the
/// typed transport boundary. The expected generation comes from a successful
/// `SessionOpened`; accepting an arbitrary canonical generation here would permit
/// a delayed frame from an earlier reuse of the same logical session id.
fn validate_data_plane_session_binding(
    who: &str,
    expected_session_id: &str,
    expected_session: &SessionRef,
    payload_session_id: &str,
    payload_session: &SessionRef,
) -> Result<(), ValidationError> {
    if !is_canonical_uuid_v4(&expected_session.generation) {
        return Err(ValidationError(format!(
            "{who}: expected live session generation must be a canonical lowercase UUIDv4"
        )));
    }
    if payload_session_id != expected_session_id {
        return Err(ValidationError(format!(
            "{who} session mismatch: key session {expected_session_id:?}, payload session {payload_session_id:?}"
        )));
    }
    if payload_session.generation != expected_session.generation {
        return Err(ValidationError(format!(
            "{who} stale-session mismatch: live generation {:?}, payload generation {:?}",
            expected_session.generation, payload_session.generation
        )));
    }
    Ok(())
}

/// Successful reply kind required for one lifecycle RPC request kind.
pub fn expected_rpc_reply_kind(request_kind: &str) -> Option<&'static str> {
    match request_kind {
        "open_session" => Some("session_opened"),
        "step_request" | "run_request" => Some("observation_frame"),
        "close_session" => Some("session_closed"),
        _ => None,
    }
}

/// Parse and validate a lifecycle RPC request received on an exact selector.
/// The caller supplies the request kind authorized by that selector; a different
/// payload kind is rejected so transport ACLs cannot be bypassed by smuggling.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RpcRequestValidationError {
    /// The universal bounded-JSON ingress rejected the request before semantic
    /// decoding. Its exact contract code must be preserved in the reply.
    JsonLimit(crate::bounded_json::BoundedJsonError),
    /// The JSON passed structural budgets but failed selector or message
    /// semantics. These failures use the generic stable wire code.
    Semantic(ValidationError),
}

impl RpcRequestValidationError {
    /// Stable error classification transports must place in their `ErrorFrame`.
    pub const fn rpc_error_code(&self) -> RpcErrorCode {
        match self {
            Self::JsonLimit(error) => RpcErrorCode::JsonLimit(error.code),
            Self::Semantic(_) => RpcErrorCode::InvalidMessage,
        }
    }
}

impl std::fmt::Display for RpcRequestValidationError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::JsonLimit(error) => {
                write!(formatter, "invalid or over-budget NCP RPC JSON: {error}")
            }
            Self::Semantic(error) => write!(formatter, "{error}"),
        }
    }
}

impl std::error::Error for RpcRequestValidationError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::JsonLimit(error) => Some(error),
            Self::Semantic(error) => Some(error),
        }
    }
}

/// Parse and validate a lifecycle RPC request, retaining bounded-JSON failures
/// separately from semantic wire failures for exact transport classification.
pub fn validate_rpc_request_for(
    expected_kind: &str,
    payload: &[u8],
) -> Result<(serde_json::Value, String), RpcRequestValidationError> {
    if !crate::keys::RPC_REQUEST_KINDS.contains(&expected_kind) {
        return Err(RpcRequestValidationError::Semantic(ValidationError(
            format!("unsupported RPC selector kind {expected_kind:?}"),
        )));
    }
    let value =
        crate::bounded_json::parse_value(payload).map_err(RpcRequestValidationError::JsonLimit)?;
    validate(&value).map_err(|error| {
        RpcRequestValidationError::Semantic(ValidationError(format!(
            "invalid NCP RPC request: {error}"
        )))
    })?;
    let kind = message_kind(&value).expect("validated request carries kind");
    if kind != expected_kind {
        return Err(RpcRequestValidationError::Semantic(ValidationError(
            format!("RPC selector/payload mismatch: expected {expected_kind:?}, got {kind:?}"),
        )));
    }
    let session_id = value
        .get("session_id")
        .and_then(serde_json::Value::as_str)
        .expect("validated lifecycle request carries session_id")
        .to_owned();
    Ok((value, session_id))
}

/// Parse and validate a lifecycle RPC reply against both its originating
/// request and session. A typed `ErrorFrame` is accepted only when its optional
/// `request_kind` agrees; successful replies must carry the exact session.
pub fn validate_rpc_reply_for(
    request_kind: &str,
    session_id: &str,
    payload: &[u8],
) -> Result<serde_json::Value, ValidationError> {
    let value = crate::bounded_json::parse_value(payload).map_err(|error| {
        ValidationError(format!(
            "invalid or over-budget NCP RPC reply JSON: {error}"
        ))
    })?;
    validate(&value).map_err(|error| ValidationError(format!("invalid NCP RPC reply: {error}")))?;
    let kind = message_kind(&value).expect("validated reply carries kind");
    let expected = expected_rpc_reply_kind(request_kind)
        .ok_or_else(|| ValidationError(format!("unsupported request kind {request_kind:?}")))?;
    if kind != expected && kind != "error" {
        return Err(ValidationError(format!(
            "RPC reply kind mismatch: {request_kind:?} requires {expected:?} or \"error\", got {kind:?}"
        )));
    }
    if kind == "observation_frame" && matches!(request_kind, "step_request" | "run_request") {
        if value.get("source").is_some_and(|source| !source.is_null()) {
            return Err(ValidationError(
                "step/run RPC observation replies must omit source; sourced observations belong on the observation plane"
                    .into(),
            ));
        }
        if value.get("receipt").is_none_or(serde_json::Value::is_null) {
            return Err(ValidationError(
                "step/run RPC observation replies require a responder receipt".into(),
            ));
        }
    }
    if kind == "error" {
        if let Some(reply_kind) = value
            .get("request_kind")
            .and_then(serde_json::Value::as_str)
        {
            if reply_kind != request_kind {
                return Err(ValidationError(format!(
                    "RPC error request_kind mismatch: expected {request_kind:?}, got {reply_kind:?}"
                )));
            }
        }
    }
    match value.get("session_id") {
        Some(serde_json::Value::String(reply_session)) if reply_session == session_id => {}
        None | Some(serde_json::Value::Null) if kind == "error" => {}
        Some(serde_json::Value::String(reply_session)) => {
            return Err(ValidationError(format!(
                "RPC reply session mismatch: expected {session_id:?}, got {reply_session:?}"
            )))
        }
        _ => {
            return Err(ValidationError(format!(
                "RPC {kind} reply carries no string session_id"
            )))
        }
    }
    Ok(value)
}

/// Build the typed, versioned failure reply used by transport servers. The
/// classification is required at the call site; a diagnostic string alone can
/// never become an unregistered wire outcome. This function is intentionally
/// infallible so a malformed request or panicking handler still receives a
/// closed, protocol-shaped outcome.
pub fn rpc_error_payload(
    code: RpcErrorCode,
    error: impl Into<String>,
    session_id: Option<String>,
    request_kind: Option<String>,
) -> Vec<u8> {
    rpc_error_payload_with_session(code, error, session_id, None, request_kind)
}

/// Build an error reply correlated to a structurally valid session incarnation.
/// The ID and generation are copied as one unit; callers that cannot prove both
/// must use [`rpc_error_payload`], which intentionally omits both.
pub fn rpc_error_payload_with_session(
    code: RpcErrorCode,
    error: impl Into<String>,
    session_id: Option<String>,
    session: Option<SessionRef>,
    request_kind: Option<String>,
) -> Vec<u8> {
    let error = error.into();
    let session_pair = session_id
        .filter(|value| crate::keys::valid_id_segment(value))
        .zip(session.filter(|value| is_canonical_uuid_v4(&value.generation)));
    let (session_id, session) = session_pair.unzip();
    let frame = ErrorFrame {
        code: code.as_str().into(),
        error: if error.is_empty() {
            code.default_message().into()
        } else {
            error
        },
        session_id,
        request_kind: request_kind.filter(|value| !value.is_empty()),
        session,
        ..Default::default()
    };
    serde_json::to_vec(&frame).unwrap_or_else(|_| {
        format!(
            r#"{{"ncp_version":"{NCP_VERSION}","kind":"error","code":"NCP-INTERNAL-001","error":"contained internal failure"}}"#
        )
        .into_bytes()
    })
}

/// Read the `kind` discriminator off any NCP JSON (for client reply dispatch).
pub fn message_kind(json: &serde_json::Value) -> Option<&str> {
    json.get("kind").and_then(|v| v.as_str())
}

/// The schema-`required` field names for a given message `kind` — the validation
/// contract (`validate()` enforces these). Most serde types retain compatibility
/// defaults, while security-sensitive required fields may also fail directly at
/// deserialization; this list remains the schema generator's source of truth for
/// what a peer MUST send. Kinds with no further required fields return just the
/// universal ones; an unknown `kind` returns `None`.
///
/// Wire 1.0: **every** kind requires `ncp_version` (the spec's "every message
/// carries `ncp_version`" is now enforced, closing the data-plane gap), and the
/// closed-loop frames require `seq` (`sensor_frame`/`command_frame` must stamp a
/// strictly-positive, strictly-increasing `seq`; `observation_frame` must carry
/// the key — `0` is reserved for the pull/RPC reply path). Value-level checks
/// (version compatibility, `seq` bounds) live in [`validate`] and
/// [`WireFrame::validate_wire`].
pub fn required_fields(kind: &str) -> Option<&'static [&'static str]> {
    Some(match kind {
        "capabilities" => &[
            "command_channels",
            "control_rate_hz",
            "controller_id",
            "gateway_permitted",
            "identity",
            "kind",
            "ncp_version",
            "role",
            "safety",
            "security_profile",
            "security_state_digest",
            "sensor_channels",
            "stable_capabilities",
        ],
        "close_session" => &[
            "authority",
            "kind",
            "ncp_version",
            "operation",
            "session",
            "session_id",
        ],
        "command_frame" => &["kind", "ncp_version", "session", "session_id", "stream"],
        "control_status" => &[
            "kind",
            "loop_latency_ms",
            "mode",
            "ncp_version",
            "safety_ok",
            "session",
            "session_id",
            "stream",
            "t",
        ],
        "error" => &["code", "error", "kind", "ncp_version"],
        "link_status" => &[
            "burst",
            "kind",
            "loss_rate",
            "lost",
            "ncp_version",
            "received",
            "session",
            "session_id",
            "stream",
            "t",
        ],
        "observation_frame" => &[
            "calibrated_posterior",
            "is_simulation_output",
            "kind",
            "ncp_version",
            "records",
            "session",
            "session_id",
            "stream",
        ],
        "open_session" => &[
            "gateway_permitted",
            "identity",
            "kind",
            "ncp_version",
            "network",
            "security_profile",
            "security_state_digest",
            "session_id",
        ],
        "run_request" => &[
            "authority",
            "duration_ms",
            "kind",
            "ncp_version",
            "operation",
            "session",
            "session_id",
        ],
        "sensor_frame" => &["kind", "ncp_version", "session", "session_id", "stream"],
        "session_closed" => &[
            "kind",
            "ncp_version",
            "ok",
            "receipt",
            "session",
            "session_id",
        ],
        "session_opened" => &[
            "backend",
            "gateway_permitted",
            "identity",
            "kind",
            "ncp_version",
            "ok",
            "security_profile",
            "security_state_digest",
            "session_id",
            "state_version",
        ],
        "step_request" => &[
            "authority",
            "kind",
            "ncp_version",
            "operation",
            "session",
            "session_id",
        ],
        "stimulus_frame" => &["kind", "ncp_version", "session", "session_id"],
        _ => return None,
    })
}

/// Minimum wire-legal `stream.seq` for a kind that carries a stream position.
/// Every periodically published data or status stream starts at `1`; `0` and
/// negative positions are unstamped/invalid. The pull/RPC observation form is
/// distinguished by `source` ABSENCE, not by a `seq == 0` sentinel.
fn min_seq(kind: &str) -> Option<i64> {
    match kind {
        "sensor_frame" | "command_frame" | "observation_frame" | "control_status"
        | "link_status" => Some(1),
        _ => None,
    }
}

/// Validation failure: either the JSON is structurally unusable, the `kind` is
/// unknown, or a schema-required field is absent.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValidationError(pub String);

impl std::fmt::Display for ValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}
impl std::error::Error for ValidationError {}

/// Deserialize the raw document as the type selected by its `kind`. The public
/// validator must check both the presence/value invariants above and the actual
/// nested field types; checking field names alone lets malformed channel maps and
/// other structurally invalid payloads pass as "valid".
fn validate_typed_shape(kind: &str, json: &serde_json::Value) -> Result<(), ValidationError> {
    macro_rules! parse {
        ($ty:ty) => {
            serde_json::from_value::<$ty>(json.clone())
                .map(|_| ())
                .map_err(|e| ValidationError(format!("{kind}: invalid wire shape: {e}")))
        };
    }
    macro_rules! parse_wire {
        ($ty:ty) => {{
            let frame = serde_json::from_value::<$ty>(json.clone())
                .map_err(|e| ValidationError(format!("{kind}: invalid wire shape: {e}")))?;
            frame.validate_wire()
        }};
    }
    match kind {
        "open_session" => parse!(OpenSession),
        "session_opened" => parse!(SessionOpened),
        "step_request" => parse!(StepRequest),
        "run_request" => parse!(RunRequest),
        "stimulus_frame" => parse!(StimulusFrame),
        "observation_frame" => parse_wire!(ObservationFrame),
        "close_session" => parse!(CloseSession),
        "session_closed" => parse!(SessionClosed),
        "error" => parse!(ErrorFrame),
        "sensor_frame" => parse_wire!(SensorFrame),
        "command_frame" => parse_wire!(CommandFrame),
        "control_status" => parse!(ControlStatus),
        "link_status" => parse!(LinkStatus),
        "capabilities" => parse!(Capabilities),
        _ => Err(ValidationError(format!(
            "unknown NCP message kind {kind:?}"
        ))),
    }
}

/// Validate raw NCP JSON against the wire contract for its `kind`.
///
/// Every message struct is `#[serde(default)]` with no `deny_unknown_fields`, so
/// a typed `serde_json::from_*` round-trip alone is *not* honest: it silently
/// fills in defaults for required-but-missing fields (e.g. a `step_request`
/// with no `session_id` deserializes to an empty session id rather than
/// failing). This function closes that gap by checking the `kind`'s
/// schema-`required` array (the same arrays `tests/conformance.rs` reads from
/// `ncp/schemas/`) **before** trusting the typed value:
///
///   - the payload must be a JSON object,
///   - it must carry a known `kind`,
///   - every schema-required field for that `kind` must be present,
///   - `ncp_version` must be **compatible** ([`check_version`], exact
///     `(major, minor)` pre-1.0) — an absent or incompatible version is rejected,
///     never coerced to the receiver's own,
///   - every data/status `stream.seq` must be an integer in
///     `1..=2^53-1`; `0` is never a pull or telemetry sentinel.
///
/// Unknown extra fields are still accepted (forward compatibility within a
/// compatible version), so this stays wire-safe.
pub fn validate(json: &serde_json::Value) -> Result<(), ValidationError> {
    let obj = json
        .as_object()
        .ok_or_else(|| ValidationError("NCP message is not a JSON object".into()))?;
    let kind = message_kind(json)
        .ok_or_else(|| ValidationError("NCP message has no string `kind`".into()))?;
    let required = required_fields(kind)
        .ok_or_else(|| ValidationError(format!("unknown NCP message kind {kind:?}")))?;
    for field in required {
        if !obj.contains_key(*field) {
            return Err(ValidationError(format!(
                "{kind}: required field {field:?} is missing"
            )));
        }
    }
    // Version-value gate: presence alone is not enough — the carried
    // version must be compatible, or an incompatible-but-parseable frame would
    // still be accepted (the audited data-plane gap). Fail closed, never coerce.
    let ver = obj
        .get("ncp_version")
        .and_then(|v| v.as_str())
        .ok_or_else(|| ValidationError(format!("{kind}: `ncp_version` must be a string")))?;
    check_version(ver, true)
        .map_err(|e| ValidationError(format!("{kind}: incompatible ncp_version: {e}")))?;
    // Stream-position bounds: all closed-loop data and status frames must stamp
    // a positive seq. A non-integer
    // or out-of-range seq is rejected here so the anti-replay/anti-stale layers
    // (`ActionBuffer`/`CommandWatchdog`) never see an unstamped frame.
    if let Some(min) = min_seq(kind) {
        let seq = obj
            .get("stream")
            .and_then(|v| v.as_object())
            .and_then(|s| s.get("seq"))
            .and_then(json_exact_i64)
            .ok_or_else(|| ValidationError(format!("{kind}: `stream.seq` must be an integer")))?;
        if seq < min {
            return Err(ValidationError(format!(
                "{kind}: stream.seq {seq} < {min} (wire 1.0 requires a stamped, \
                 strictly-increasing per-stream stream.seq)"
            )));
        }
    }
    validate_nested_object_shapes(kind, obj)?;
    // Step/run embed a complete StimulusFrame envelope. Validate it recursively
    // rather than letting struct-level serde defaults fabricate its mandatory
    // kind/version/session, and prevent a cross-session stimulus from being
    // smuggled inside an otherwise valid outer request.
    if matches!(kind, "step_request" | "run_request") {
        if let Some(stimulus) = obj.get("stimulus").filter(|v| !v.is_null()) {
            validate(stimulus).map_err(|e| {
                ValidationError(format!("{kind}.stimulus: invalid nested frame: {e}"))
            })?;
            if message_kind(stimulus) != Some("stimulus_frame") {
                return Err(ValidationError(format!(
                    "{kind}.stimulus: kind must be \"stimulus_frame\""
                )));
            }
            let outer_session = obj.get("session_id").and_then(|v| v.as_str());
            let inner_session = stimulus.get("session_id").and_then(|v| v.as_str());
            if inner_session != outer_session {
                return Err(ValidationError(format!(
                    "{kind}.stimulus: session_id {inner_session:?} does not match outer {outer_session:?}"
                )));
            }
        }
    }
    validate_typed_shape(kind, json)?;
    validate_semantics(kind, obj)?;
    validate_safe_integers(kind, obj)?;
    // Scientific-boundary value pins: these discriminators are NOT free booleans.
    // An NCP frame is a control/simulation artifact, never a calibrated posterior
    // — so where they appear they MUST read calibrated_posterior=false and
    // is_simulation_output=true. A peer asserting otherwise is rejected, not
    // silently trusted. (Mirrors the proto "always false"/"always true" contract
    // and the ObservationFrame::default() invariant.)
    match kind {
        "observation_frame" => check_scientific_boundary(obj, kind)?,
        "session_opened" => {
            if let Some(p) = obj.get("provenance").and_then(|v| v.as_object()) {
                check_scientific_boundary(p, "session_opened.provenance")?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn required_nonempty_string<'a>(
    obj: &'a serde_json::Map<String, serde_json::Value>,
    field: &str,
    path: &str,
) -> Result<&'a str, ValidationError> {
    obj.get(field)
        .and_then(|value| value.as_str())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| ValidationError(format!("{path} must be a non-empty string")))
}

fn validate_session_id(
    obj: &serde_json::Map<String, serde_json::Value>,
    kind: &str,
) -> Result<(), ValidationError> {
    let session_id = required_nonempty_string(obj, "session_id", &format!("{kind}.session_id"))?;
    if !crate::keys::valid_id_segment(session_id) {
        return Err(ValidationError(format!(
            "{kind}.session_id {session_id:?} is not a safe single key segment"
        )));
    }
    Ok(())
}

fn required_session_epoch<'a>(
    obj: &'a serde_json::Map<String, serde_json::Value>,
    path: &str,
) -> Result<&'a str, ValidationError> {
    let session = required_json_object(obj.get("session"), &format!("{path}.session"))?;
    let generation =
        required_nonempty_string(session, "generation", &format!("{path}.session.generation"))?;
    if !is_canonical_uuid_v4(generation) {
        return Err(ValidationError(format!(
            "{path}.session.generation must be a canonical lowercase UUIDv4"
        )));
    }
    Ok(generation)
}

fn finite_number(value: &serde_json::Value, path: &str) -> Result<f64, ValidationError> {
    value
        .as_f64()
        .filter(|number| number.is_finite())
        .ok_or_else(|| ValidationError(format!("{path} must be a finite number")))
}

fn required_json_object<'a>(
    value: Option<&'a serde_json::Value>,
    path: &str,
) -> Result<&'a serde_json::Map<String, serde_json::Value>, ValidationError> {
    value
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| ValidationError(format!("{path} must be an object")))
}

fn optional_json_object<'a>(
    obj: &'a serde_json::Map<String, serde_json::Value>,
    field: &str,
    path: &str,
) -> Result<Option<&'a serde_json::Map<String, serde_json::Value>>, ValidationError> {
    obj.get(field)
        .map(|value| required_json_object(Some(value), path))
        .transpose()
}

fn nullable_json_object<'a>(
    obj: &'a serde_json::Map<String, serde_json::Value>,
    field: &str,
    path: &str,
) -> Result<Option<&'a serde_json::Map<String, serde_json::Value>>, ValidationError> {
    match obj.get(field) {
        None | Some(serde_json::Value::Null) => Ok(None),
        Some(value) => required_json_object(Some(value), path).map(Some),
    }
}

fn required_json_array<'a>(
    value: Option<&'a serde_json::Value>,
    path: &str,
) -> Result<&'a Vec<serde_json::Value>, ValidationError> {
    value
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| ValidationError(format!("{path} must be an array")))
}

fn optional_json_array<'a>(
    obj: &'a serde_json::Map<String, serde_json::Value>,
    field: &str,
    path: &str,
) -> Result<Option<&'a Vec<serde_json::Value>>, ValidationError> {
    obj.get(field)
        .map(|value| required_json_array(Some(value), path))
        .transpose()
}

fn validate_object_map(value: &serde_json::Value, path: &str) -> Result<(), ValidationError> {
    let map = required_json_object(Some(value), path)?;
    for (name, value) in map {
        required_json_object(Some(value), &format!("{path}[{name:?}]"))?;
    }
    Ok(())
}

/// Enforce the JSON projection's map-only shape for every nested named message.
/// Serde intentionally supports positional sequences for Rust structs; that is a
/// useful data-format feature but is not part of NCP's object-based JSON wire.
fn validate_nested_object_shapes(
    kind: &str,
    obj: &serde_json::Map<String, serde_json::Value>,
) -> Result<(), ValidationError> {
    match kind {
        "open_session" => {
            let network = required_json_object(obj.get("network"), "open_session.network")?;
            required_json_object(obj.get("identity"), "open_session.identity")?;
            nullable_json_object(obj, "gateway", "open_session.gateway")?;
            for field in ["population_sizes", "params"] {
                if let Some(value) = network.get(field) {
                    required_json_object(Some(value), &format!("open_session.network.{field}"))?;
                }
            }
            if let Some(record) = optional_json_object(obj, "record", "open_session.record")? {
                if let Some(targets) =
                    optional_json_array(record, "targets", "open_session.record.targets")?
                {
                    for (index, target) in targets.iter().enumerate() {
                        required_json_object(
                            Some(target),
                            &format!("open_session.record.targets[{index}]"),
                        )?;
                    }
                }
            }
            if let Some(stimulus) = optional_json_object(obj, "stimulus", "open_session.stimulus")?
            {
                if let Some(targets) =
                    optional_json_array(stimulus, "targets", "open_session.stimulus.targets")?
                {
                    for (index, target) in targets.iter().enumerate() {
                        let target = required_json_object(
                            Some(target),
                            &format!("open_session.stimulus.targets[{index}]"),
                        )?;
                        if let Some(params) = target.get("params") {
                            required_json_object(
                                Some(params),
                                &format!("open_session.stimulus.targets[{index}].params"),
                            )?;
                        }
                    }
                }
            }
            optional_json_object(obj, "sim", "open_session.sim")?;
            if let Some(bindings) = optional_json_array(obj, "bindings", "open_session.bindings")? {
                for (index, binding) in bindings.iter().enumerate() {
                    let binding = required_json_object(
                        Some(binding),
                        &format!("open_session.bindings[{index}]"),
                    )?;
                    if let Some(entity) = binding.get("entity") {
                        let entity = required_json_object(
                            Some(entity),
                            &format!("open_session.bindings[{index}].entity"),
                        )?;
                        if let Some(meta) = entity.get("meta") {
                            required_json_object(
                                Some(meta),
                                &format!("open_session.bindings[{index}].entity.meta"),
                            )?;
                        }
                    }
                }
            }
        }
        "session_opened" => {
            required_json_object(obj.get("identity"), "session_opened.identity")?;
            nullable_json_object(obj, "gateway", "session_opened.gateway")?;
            nullable_json_object(obj, "provenance", "session_opened.provenance")?;
            if let Some(resolved) = obj.get("resolved") {
                required_json_object(Some(resolved), "session_opened.resolved")?;
            }
        }
        "step_request" | "run_request" => {
            nullable_json_object(obj, "stimulus", &format!("{kind}.stimulus"))?;
            required_json_object(obj.get("operation"), &format!("{kind}.operation"))?;
            required_json_object(obj.get("authority"), &format!("{kind}.authority"))?;
        }
        "close_session" => {
            required_json_object(obj.get("operation"), "close_session.operation")?;
            required_json_object(obj.get("authority"), "close_session.authority")?;
        }
        "session_closed" => {
            required_json_object(obj.get("receipt"), "session_closed.receipt")?;
        }
        "error" => {
            nullable_json_object(obj, "receipt", "error.receipt")?;
        }
        "stimulus_frame" => {
            if let Some(values) = obj.get("values") {
                validate_object_map(values, "stimulus_frame.values")?;
            }
        }
        "sensor_frame" => {
            if let Some(channels) = obj.get("channels") {
                validate_object_map(channels, "sensor_frame.channels")?;
            }
        }
        "command_frame" => {
            nullable_json_object(obj, "authority", "command_frame.authority")?;
            if let Some(channels) = obj.get("channels") {
                validate_object_map(channels, "command_frame.channels")?;
            }
            if let Some(horizon) = optional_json_array(obj, "horizon", "command_frame.horizon")? {
                for (index, step) in horizon.iter().enumerate() {
                    let path = format!("command_frame.horizon[{index}]");
                    let step = required_json_object(Some(step), &path)?;
                    for (name, channel) in step {
                        required_json_object(Some(channel), &format!("{path}[{name:?}]"))?;
                    }
                }
            }
        }
        "observation_frame" => {
            nullable_json_object(obj, "receipt", "observation_frame.receipt")?;
            let records = required_json_object(obj.get("records"), "observation_frame.records")?;
            for (name, record) in records {
                required_json_object(
                    Some(record),
                    &format!("observation_frame.records[{name:?}]"),
                )?;
            }
        }
        "capabilities" => {
            required_json_object(obj.get("identity"), "capabilities.identity")?;
            nullable_json_object(obj, "gateway", "capabilities.gateway")?;
            for field in ["sensor_channels", "command_channels"] {
                let channels =
                    required_json_array(obj.get(field), &format!("capabilities.{field}"))?;
                for (index, channel) in channels.iter().enumerate() {
                    required_json_object(Some(channel), &format!("capabilities.{field}[{index}]"))?;
                }
            }
            required_json_object(obj.get("safety"), "capabilities.safety")?;
        }
        _ => {}
    }
    Ok(())
}

/// Read the semantic JSON-Schema `integer` value of a number. JSON has a single
/// number grammar, so integral spellings such as `1.0` and `1e0` are integers too;
/// keep them aligned with JS/Python while rejecting fractions and unsafe values.
fn json_exact_i64(value: &serde_json::Value) -> Option<i64> {
    if let Some(value) = value.as_i64() {
        return (JSON_SAFE_INTEGER_MIN..=JSON_SAFE_INTEGER_MAX)
            .contains(&value)
            .then_some(value);
    }
    if let Some(value) = value.as_u64() {
        return (value <= JSON_SAFE_INTEGER_MAX as u64).then_some(value as i64);
    }
    let value = value.as_f64()?;
    (value.is_finite()
        && value.fract() == 0.0
        && value >= JSON_SAFE_INTEGER_MIN as f64
        && value <= JSON_SAFE_INTEGER_MAX as f64)
        .then_some(value as i64)
}

const CORE_STABLE_CAPABILITIES: &[&str] = &[
    "ncp.core.canonical-json.v1",
    "ncp.core.lifecycle.v1",
    "ncp.core.authority-lease.v1",
    "ncp.core.idempotent-mutation.v1",
    "ncp.core.plant-profile.v1",
];

const KNOWN_STABLE_CAPABILITIES: &[&str] = &[
    "ncp.core.canonical-json.v1",
    "ncp.core.lifecycle.v1",
    "ncp.core.authority-lease.v1",
    "ncp.core.idempotent-mutation.v1",
    "ncp.core.plant-profile.v1",
    "ncp.transport.zenoh.v1",
];

fn valid_bounded_id(value: &str) -> bool {
    value.len() <= 128 && crate::keys::valid_id_segment(value)
}

fn valid_sha256_hex(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f'))
}

fn validate_identity_claim(
    value: Option<&serde_json::Value>,
    path: &str,
    expected_plane: Option<&str>,
    expected_role: Option<&str>,
) -> Result<(), ValidationError> {
    let claim = required_json_object(value, path)?;
    for field in ["principal_id", "entity_id"] {
        let identity = required_nonempty_string(claim, field, &format!("{path}.{field}"))?;
        if !valid_bounded_id(identity) {
            return Err(ValidationError(format!(
                "{path}.{field} must be a bounded canonical identity segment"
            )));
        }
    }
    let role = required_nonempty_string(claim, "role", &format!("{path}.role"))?;
    if !matches!(role, "commander" | "body" | "observer" | "operator") {
        return Err(ValidationError(format!(
            "{path}.role is unknown and cannot authorize this message"
        )));
    }
    if expected_role.is_some_and(|expected| role != expected) {
        return Err(ValidationError(format!(
            "{path}.role {role:?} does not match the envelope role"
        )));
    }
    let plane = required_nonempty_string(claim, "plane", &format!("{path}.plane"))?;
    if !matches!(plane, "control" | "perception" | "action" | "observation") {
        return Err(ValidationError(format!(
            "{path}.plane is unknown and cannot authorize this message"
        )));
    }
    if expected_plane.is_some_and(|expected| plane != expected) {
        return Err(ValidationError(format!(
            "{path}.plane {plane:?} does not match the transport message plane"
        )));
    }
    Ok(())
}

fn validate_security_negotiation(
    obj: &serde_json::Map<String, serde_json::Value>,
    path: &str,
) -> Result<(), ValidationError> {
    let profile =
        required_nonempty_string(obj, "security_profile", &format!("{path}.security_profile"))?;
    if !matches!(profile, "dev-loopback-insecure" | "production-secure") {
        return Err(ValidationError(format!(
            "{path}.security_profile is not a registered NCP 1.0 profile"
        )));
    }
    let digest = required_nonempty_string(
        obj,
        "security_state_digest",
        &format!("{path}.security_state_digest"),
    )?;
    if !valid_sha256_hex(digest) {
        return Err(ValidationError(format!(
            "{path}.security_state_digest must be 64 lowercase hexadecimal characters"
        )));
    }
    Ok(())
}

fn validate_gateway_attribution(
    obj: &serde_json::Map<String, serde_json::Value>,
    path: &str,
) -> Result<(), ValidationError> {
    let gateway_permitted = obj
        .get("gateway_permitted")
        .and_then(serde_json::Value::as_bool)
        .ok_or_else(|| ValidationError(format!("{path}.gateway_permitted must be a boolean")))?;
    let Some(value) = obj.get("gateway").filter(|value| !value.is_null()) else {
        return Ok(());
    };
    if !gateway_permitted {
        return Err(ValidationError(format!(
            "{path}.gateway attribution is forbidden when gateway_permitted=false"
        )));
    }
    let gateway = required_json_object(Some(value), &format!("{path}.gateway"))?;
    let gateway_id =
        required_nonempty_string(gateway, "gateway_id", &format!("{path}.gateway.gateway_id"))?;
    if !valid_bounded_id(gateway_id) {
        return Err(ValidationError(format!(
            "{path}.gateway.gateway_id must be a bounded canonical identity segment"
        )));
    }
    if required_nonempty_string(
        gateway,
        "source_wire",
        &format!("{path}.gateway.source_wire"),
    )? != "0.8"
    {
        return Err(ValidationError(format!(
            "{path}.gateway.source_wire must identify the only supported legacy wire, 0.8"
        )));
    }
    Ok(())
}

fn validate_authority_lease(
    value: Option<&serde_json::Value>,
    path: &str,
    expected_epoch: Option<&str>,
) -> Result<(), ValidationError> {
    let lease = required_json_object(value, path)?;
    let session_epoch =
        required_nonempty_string(lease, "session_epoch", &format!("{path}.session_epoch"))?;
    let lease_id = required_nonempty_string(lease, "lease_id", &format!("{path}.lease_id"))?;
    if !is_canonical_uuid_v4(session_epoch) || !is_canonical_uuid_v4(lease_id) {
        return Err(ValidationError(format!(
            "{path}.session_epoch and lease_id must be canonical lowercase UUIDv4 values"
        )));
    }
    if expected_epoch.is_some_and(|expected| session_epoch != expected) {
        return Err(ValidationError(format!(
            "{path}.session_epoch does not match the message session generation"
        )));
    }
    let term = lease
        .get("term")
        .and_then(json_exact_i64)
        .ok_or_else(|| ValidationError(format!("{path}.term must be a JSON-safe integer")))?;
    if term <= 0 {
        return Err(ValidationError(format!("{path}.term must be > 0")));
    }
    for field in [
        "issuer_principal_id",
        "holder_principal_id",
        "holder_entity_id",
    ] {
        let identity = required_nonempty_string(lease, field, &format!("{path}.{field}"))?;
        if !valid_bounded_id(identity) {
            return Err(ValidationError(format!(
                "{path}.{field} must be a bounded canonical identity segment"
            )));
        }
    }
    let issued = lease
        .get("issued_at_utc_ms")
        .and_then(json_exact_i64)
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.issued_at_utc_ms must be a JSON-safe integer"
            ))
        })?;
    let expires = lease
        .get("expires_at_utc_ms")
        .and_then(json_exact_i64)
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.expires_at_utc_ms must be a JSON-safe integer"
            ))
        })?;
    if issued < 0
        || expires <= issued
        || expires - issued > crate::authority::MAX_AUTHORITY_LEASE_MS
    {
        return Err(ValidationError(format!(
            "{path} must have a positive bounded UTC lease interval"
        )));
    }
    Ok(())
}

fn validate_operation_context(
    value: Option<&serde_json::Value>,
    path: &str,
    expected_epoch: Option<&str>,
) -> Result<(), ValidationError> {
    let operation = required_json_object(value, path)?;
    let operation_id =
        required_nonempty_string(operation, "operation_id", &format!("{path}.operation_id"))?;
    let session_epoch =
        required_nonempty_string(operation, "session_epoch", &format!("{path}.session_epoch"))?;
    if !is_canonical_uuid_v4(operation_id) || !is_canonical_uuid_v4(session_epoch) {
        return Err(ValidationError(format!(
            "{path}.operation_id and session_epoch must be canonical lowercase UUIDv4 values"
        )));
    }
    if expected_epoch.is_some_and(|expected| session_epoch != expected) {
        return Err(ValidationError(format!(
            "{path}.session_epoch does not match the message session generation"
        )));
    }
    let digest = required_nonempty_string(
        operation,
        "request_digest",
        &format!("{path}.request_digest"),
    )?;
    if !valid_sha256_hex(digest) {
        return Err(ValidationError(format!(
            "{path}.request_digest must be 64 lowercase hexadecimal characters"
        )));
    }
    operation
        .get("expected_state_version")
        .and_then(json_exact_i64)
        .filter(|value| *value >= 0)
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.expected_state_version must be a non-negative JSON-safe integer"
            ))
        })?;
    operation
        .get("deadline_utc_ms")
        .and_then(json_exact_i64)
        .filter(|value| *value > 0)
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.deadline_utc_ms must be a positive JSON-safe integer"
            ))
        })?;
    if operation
        .get("retry")
        .and_then(serde_json::Value::as_bool)
        .is_none()
    {
        return Err(ValidationError(format!("{path}.retry must be a boolean")));
    }
    Ok(())
}

fn validate_responder_receipt(
    value: Option<&serde_json::Value>,
    path: &str,
) -> Result<(), ValidationError> {
    let receipt = required_json_object(value, path)?;
    let operation_id =
        required_nonempty_string(receipt, "operation_id", &format!("{path}.operation_id"))?;
    if !is_canonical_uuid_v4(operation_id) {
        return Err(ValidationError(format!(
            "{path}.operation_id must be a canonical lowercase UUIDv4"
        )));
    }
    for field in ["request_digest", "result_digest"] {
        let digest = required_nonempty_string(receipt, field, &format!("{path}.{field}"))?;
        if !valid_sha256_hex(digest) {
            return Err(ValidationError(format!(
                "{path}.{field} must be 64 lowercase hexadecimal characters"
            )));
        }
    }
    let outcome = required_nonempty_string(receipt, "outcome", &format!("{path}.outcome"))?;
    if !matches!(outcome, "succeeded" | "rejected" | "cancelled") {
        return Err(ValidationError(format!(
            "{path}.outcome must be a known terminal outcome"
        )));
    }
    receipt
        .get("state_version")
        .and_then(json_exact_i64)
        .filter(|value| *value >= 0)
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.state_version must be a non-negative JSON-safe integer"
            ))
        })?;
    receipt
        .get("committed_at_utc_ms")
        .and_then(json_exact_i64)
        .filter(|value| *value > 0)
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.committed_at_utc_ms must be a positive JSON-safe integer"
            ))
        })?;
    for field in ["responder_principal_id", "responder_entity_id"] {
        let identity = required_nonempty_string(receipt, field, &format!("{path}.{field}"))?;
        if !valid_bounded_id(identity) {
            return Err(ValidationError(format!(
                "{path}.{field} must be a bounded canonical identity segment"
            )));
        }
    }
    Ok(())
}

/// Validate a JSON-projected stream position without relying on serde's support
/// for positional struct sequences. Status frames do not implement `WireFrame`,
/// so their envelope positions use this equivalent ingress gate.
fn validate_json_stream_position(
    value: Option<&serde_json::Value>,
    path: &str,
) -> Result<i64, ValidationError> {
    let position = required_json_object(value, path)?;
    let epoch = required_nonempty_string(position, "epoch", &format!("{path}.epoch"))?;
    if !is_canonical_uuid_v4(epoch) {
        return Err(ValidationError(format!(
            "{path}.epoch must be a canonical lowercase UUIDv4"
        )));
    }
    position
        .get("seq")
        .and_then(json_exact_i64)
        .filter(|seq| (1..=JSON_SAFE_INTEGER_MAX).contains(seq))
        .ok_or_else(|| {
            ValidationError(format!(
                "{path}.seq must be a JSON-safe integer within 1..=2^53-1"
            ))
        })
}

fn validate_semantics(
    kind: &str,
    obj: &serde_json::Map<String, serde_json::Value>,
) -> Result<(), ValidationError> {
    if matches!(
        kind,
        "open_session"
            | "session_opened"
            | "step_request"
            | "run_request"
            | "stimulus_frame"
            | "observation_frame"
            | "close_session"
            | "session_closed"
            | "sensor_frame"
            | "command_frame"
            | "control_status"
            | "link_status"
    ) {
        validate_session_id(obj, kind)?;
    }

    let session_epoch = if matches!(
        kind,
        "step_request"
            | "run_request"
            | "stimulus_frame"
            | "observation_frame"
            | "close_session"
            | "session_closed"
            | "sensor_frame"
            | "command_frame"
            | "control_status"
            | "link_status"
    ) {
        Some(required_session_epoch(obj, kind)?)
    } else {
        None
    };

    match kind {
        "open_session" => {
            validate_identity_claim(
                obj.get("identity"),
                "open_session.identity",
                Some("control"),
                Some("commander"),
            )?;
            validate_security_negotiation(obj, "open_session")?;
            validate_gateway_attribution(obj, "open_session")?;
            let network = obj
                .get("network")
                .and_then(|value| value.as_object())
                .ok_or_else(|| ValidationError("open_session.network must be an object".into()))?;
            let network_kind =
                required_nonempty_string(network, "kind", "open_session.network.kind")?;
            if !matches!(network_kind, "handle" | "builtin" | "model_id" | "spec") {
                return Err(ValidationError(
                    "open_session.network.kind is unknown and cannot select model-loading behavior"
                        .into(),
                ));
            }
            required_nonempty_string(network, "ref", "open_session.network.ref")?;
            if let Some(sim) = obj.get("sim").and_then(|value| value.as_object()) {
                for (field, allow_zero) in
                    [("dt_ms", false), ("chunk_ms", false), ("duration_ms", true)]
                {
                    if let Some(value) = sim.get(field).filter(|value| !value.is_null()) {
                        let number = finite_number(value, &format!("open_session.sim.{field}"))?;
                        if number < 0.0 || (!allow_zero && number == 0.0) {
                            return Err(ValidationError(format!(
                                "open_session.sim.{field} must be {} 0",
                                if allow_zero { ">=" } else { ">" }
                            )));
                        }
                    }
                }
                if let Some(mode) = sim.get("mode") {
                    if !matches!(mode.as_str(), Some("stream" | "batch")) {
                        return Err(ValidationError(
                            "open_session.sim.mode must be stream or batch".into(),
                        ));
                    }
                }
            }
            if let Some(record) = obj.get("record").and_then(|value| value.as_object()) {
                for (index, value) in record
                    .get("targets")
                    .and_then(|value| value.as_array())
                    .into_iter()
                    .flatten()
                    .enumerate()
                {
                    let path = format!("open_session.record.targets[{index}]");
                    let target = required_json_object(Some(value), &path)?;
                    required_nonempty_string(target, "port", &format!("{path}.port"))?;
                    required_nonempty_string(target, "target", &format!("{path}.target"))?;
                    let observable = required_nonempty_string(
                        target,
                        "observable",
                        &format!("{path}.observable"),
                    )?;
                    if !matches!(
                        observable,
                        "spikes" | "V_m" | "rate" | "weight" | "binary_state"
                    ) {
                        return Err(ValidationError(format!(
                            "{path}.observable is unknown and cannot configure recording"
                        )));
                    }
                    if let Some(cadence) = target.get("cadence_ms") {
                        if finite_number(cadence, &format!("{path}.cadence_ms"))? <= 0.0 {
                            return Err(ValidationError(format!("{path}.cadence_ms must be > 0")));
                        }
                    }
                }
            }
            if let Some(stimulus) = obj.get("stimulus").and_then(|value| value.as_object()) {
                for (index, value) in stimulus
                    .get("targets")
                    .and_then(|value| value.as_array())
                    .into_iter()
                    .flatten()
                    .enumerate()
                {
                    let path = format!("open_session.stimulus.targets[{index}]");
                    let target = required_json_object(Some(value), &path)?;
                    required_nonempty_string(target, "port", &format!("{path}.port"))?;
                    required_nonempty_string(target, "target", &format!("{path}.target"))?;
                    let stimulus_kind =
                        required_nonempty_string(target, "kind", &format!("{path}.kind"))?;
                    if !matches!(
                        stimulus_kind,
                        "current_pA" | "rate_hz" | "spike_times" | "weight_set" | "rate_inject"
                    ) {
                        return Err(ValidationError(format!(
                            "{path}.kind is unknown and cannot select stimulus behavior"
                        )));
                    }
                    if let Some(params) = target.get("params").and_then(|value| value.as_object()) {
                        for (name, value) in params {
                            finite_number(value, &format!("{path}.params[{name:?}]"))?;
                        }
                    }
                }
            }
            for (index, value) in obj
                .get("bindings")
                .and_then(|value| value.as_array())
                .into_iter()
                .flatten()
                .enumerate()
            {
                let path = format!("open_session.bindings[{index}]");
                let binding = required_json_object(Some(value), &path)?;
                required_nonempty_string(binding, "port", &format!("{path}.port"))?;
                let direction =
                    required_nonempty_string(binding, "direction", &format!("{path}.direction"))?;
                if !matches!(direction, "stimulus" | "record") {
                    return Err(ValidationError(format!(
                        "{path}.direction must be \"stimulus\" or \"record\""
                    )));
                }
                let entity = binding
                    .get("entity")
                    .and_then(|value| value.as_object())
                    .ok_or_else(|| ValidationError(format!("{path}.entity must be an object")))?;
                required_nonempty_string(entity, "path", &format!("{path}.entity.path"))?;
                let entity_role =
                    required_nonempty_string(entity, "role", &format!("{path}.entity.role"))?;
                if !matches!(entity_role, "system" | "actor" | "sensor" | "actuator") {
                    return Err(ValidationError(format!(
                        "{path}.entity.role is unknown and cannot select binding semantics"
                    )));
                }
            }
        }
        "session_opened" => {
            validate_identity_claim(
                obj.get("identity"),
                "session_opened.identity",
                Some("control"),
                Some("body"),
            )?;
            validate_security_negotiation(obj, "session_opened")?;
            validate_gateway_attribution(obj, "session_opened")?;
            let backend = required_nonempty_string(obj, "backend", "session_opened.backend")?;
            let ok = obj
                .get("ok")
                .and_then(|value| value.as_bool())
                .ok_or_else(|| ValidationError("session_opened.ok must be a boolean".into()))?;
            obj.get("state_version")
                .and_then(json_exact_i64)
                .filter(|value| *value >= 0)
                .ok_or_else(|| {
                    ValidationError(
                        "session_opened.state_version must be a non-negative JSON-safe integer"
                            .into(),
                    )
                })?;
            if ok {
                required_session_epoch(obj, "session_opened")?;
                let provenance = obj
                    .get("provenance")
                    .and_then(|value| value.as_object())
                    .ok_or_else(|| {
                        ValidationError(
                            "session_opened.provenance is mandatory when ok=true".into(),
                        )
                    })?;
                required_nonempty_string(
                    provenance,
                    "network_ref",
                    "session_opened.provenance.network_ref",
                )?;
                required_nonempty_string(
                    provenance,
                    "backend",
                    "session_opened.provenance.backend",
                )?;
                if provenance.get("backend").and_then(|value| value.as_str()) != Some(backend) {
                    return Err(ValidationError(
                        "session_opened.provenance.backend must equal session_opened.backend"
                            .into(),
                    ));
                }
                check_scientific_boundary(provenance, "session_opened.provenance")?;
                if provenance
                    .get("advisory_only")
                    .and_then(|value| value.as_bool())
                    != Some(true)
                {
                    return Err(ValidationError(
                        "session_opened.provenance.advisory_only must be explicitly true".into(),
                    ));
                }
                if obj.get("error").is_some_and(|value| !value.is_null()) {
                    return Err(ValidationError(
                        "session_opened.error must be null when ok=true".into(),
                    ));
                }
            } else if obj
                .get("error")
                .and_then(|value| value.as_str())
                .is_none_or(str::is_empty)
            {
                return Err(ValidationError(
                    "session_opened.error must explain an ok=false reply".into(),
                ));
            } else if obj.get("provenance").is_some_and(|value| !value.is_null()) {
                return Err(ValidationError(
                    "session_opened.provenance must be null when ok=false".into(),
                ));
            } else if obj.get("session").is_some_and(|value| !value.is_null()) {
                return Err(ValidationError(
                    "session_opened.session must be null when ok=false".into(),
                ));
            }
        }
        "session_closed" => {
            if obj.get("ok").and_then(|value| value.as_bool()) != Some(true) {
                return Err(ValidationError(
                    "session_closed.ok must be true; failures use a typed ErrorFrame".into(),
                ));
            }
            validate_responder_receipt(obj.get("receipt"), "session_closed.receipt")?;
        }
        "error" => {
            let code = required_nonempty_string(obj, "code", "error.code")?;
            if !is_registered_error_code(code) {
                return Err(ValidationError(format!(
                    "error.code {code:?} is not registered in contract/errors.v1.json"
                )));
            }
            required_nonempty_string(obj, "error", "error.error")?;
            if let Some(request_kind) = obj.get("request_kind").filter(|value| !value.is_null()) {
                if request_kind.as_str().is_none_or(str::is_empty) {
                    return Err(ValidationError(
                        "error.request_kind must be a non-empty string or null".into(),
                    ));
                }
            }
            if let Some(session_id) = obj.get("session_id").filter(|value| !value.is_null()) {
                let session_id = session_id.as_str().ok_or_else(|| {
                    ValidationError("error.session_id must be a string or null".into())
                })?;
                if !crate::keys::valid_id_segment(session_id) {
                    return Err(ValidationError(format!(
                        "error.session_id {session_id:?} is not a safe single key segment"
                    )));
                }
            }
            let has_session_id = obj.get("session_id").is_some_and(|value| !value.is_null());
            let has_session = obj.get("session").is_some_and(|value| !value.is_null());
            if has_session_id != has_session {
                return Err(ValidationError(
                    "error.session_id and error.session must be present or null together".into(),
                ));
            }
            if has_session {
                required_session_epoch(obj, "error")?;
            }
            if let Some(receipt) = obj.get("receipt").filter(|value| !value.is_null()) {
                validate_responder_receipt(Some(receipt), "error.receipt")?;
            }
        }
        "run_request" => {
            validate_operation_context(
                obj.get("operation"),
                "run_request.operation",
                session_epoch,
            )?;
            validate_authority_lease(obj.get("authority"), "run_request.authority", session_epoch)?;
            let duration = finite_number(
                obj.get("duration_ms")
                    .ok_or_else(|| ValidationError("run_request.duration_ms is required".into()))?,
                "run_request.duration_ms",
            )?;
            if duration <= 0.0 {
                return Err(ValidationError(
                    "run_request.duration_ms must be > 0".into(),
                ));
            }
        }
        "step_request" => {
            validate_operation_context(
                obj.get("operation"),
                "step_request.operation",
                session_epoch,
            )?;
            validate_authority_lease(
                obj.get("authority"),
                "step_request.authority",
                session_epoch,
            )?;
            if let Some(value) = obj.get("advance_ms").filter(|value| !value.is_null()) {
                if finite_number(value, "step_request.advance_ms")? < 0.0 {
                    return Err(ValidationError(
                        "step_request.advance_ms must be >= 0".into(),
                    ));
                }
            }
        }
        "close_session" => {
            validate_operation_context(
                obj.get("operation"),
                "close_session.operation",
                session_epoch,
            )?;
            validate_authority_lease(
                obj.get("authority"),
                "close_session.authority",
                session_epoch,
            )?;
        }
        "command_frame" => {
            if obj.contains_key("mode") {
                required_nonempty_string(obj, "mode", "command_frame.mode")?;
            }
            if obj.get("mode").and_then(|value| value.as_str()) == Some("active") {
                validate_authority_lease(
                    obj.get("authority"),
                    "command_frame.authority",
                    session_epoch,
                )?;
                let ttl = obj.get("ttl_ms").ok_or_else(|| {
                    ValidationError("command_frame Active mode requires ttl_ms".into())
                })?;
                if finite_number(ttl, "command_frame.ttl_ms")? <= 0.0 {
                    return Err(ValidationError(
                        "command_frame Active ttl_ms must be > 0".into(),
                    ));
                }
                if !obj
                    .get("channels")
                    .is_some_and(serde_json::Value::is_object)
                {
                    return Err(ValidationError(
                        "command_frame Active mode requires a channels object".into(),
                    ));
                }
            } else if let Some(authority) = obj.get("authority").filter(|value| !value.is_null()) {
                validate_authority_lease(
                    Some(authority),
                    "command_frame.authority",
                    session_epoch,
                )?;
            }
        }
        "observation_frame" => {
            if let Some(receipt) = obj.get("receipt").filter(|value| !value.is_null()) {
                validate_responder_receipt(Some(receipt), "observation_frame.receipt")?;
            }
            let records = obj
                .get("records")
                .and_then(|value| value.as_object())
                .ok_or_else(|| {
                    ValidationError("observation_frame.records must be an object".into())
                })?;
            for (record_key, value) in records {
                if record_key.is_empty() || record_key.chars().any(char::is_control) {
                    return Err(ValidationError(format!(
                        "observation_frame record-series key {record_key:?} must be non-empty and contain no control characters"
                    )));
                }
                let record = value.as_object().ok_or_else(|| {
                    ValidationError(format!(
                        "observation_frame.records[{record_key:?}] must be an object"
                    ))
                })?;
                required_nonempty_string(
                    record,
                    "port",
                    &format!("observation_frame.records[{record_key:?}].port"),
                )?;
                required_nonempty_string(
                    record,
                    "target",
                    &format!("observation_frame.records[{record_key:?}].target"),
                )?;
                let observable = required_nonempty_string(
                    record,
                    "observable",
                    &format!("observation_frame.records[{record_key:?}].observable"),
                )?;
                if !matches!(
                    observable,
                    "spikes" | "V_m" | "rate" | "weight" | "binary_state"
                ) {
                    return Err(ValidationError(format!(
                        "observation_frame.records[{record_key:?}].observable is unknown"
                    )));
                }
                let times = record
                    .get("times")
                    .and_then(|value| value.as_array())
                    .map_or(0, Vec::len);
                let values = record
                    .get("values")
                    .and_then(|value| value.as_array())
                    .map_or(0, Vec::len);
                let senders = record
                    .get("senders")
                    .and_then(|value| value.as_array())
                    .map_or(0, Vec::len);
                if values > 0 && senders > 0 {
                    return Err(ValidationError(format!(
                        "observation_frame.records[{record_key:?}] cannot carry values and senders in one series"
                    )));
                }
                let payload_len = values.max(senders);
                if times != payload_len && (times > 0 || payload_len > 0) {
                    return Err(ValidationError(format!(
                        "observation_frame.records[{record_key:?}] parallel arrays disagree: times={times}, values={values}, senders={senders}"
                    )));
                }
            }
        }
        "capabilities" => {
            let controller_id =
                required_nonempty_string(obj, "controller_id", "capabilities.controller_id")?;
            if !valid_bounded_id(controller_id) {
                return Err(ValidationError(
                    "capabilities.controller_id must be a bounded canonical identity segment"
                        .into(),
                ));
            }
            let role = required_nonempty_string(obj, "role", "capabilities.role")?;
            let principal_role = match role {
                "controller" => "commander",
                "plant" => "body",
                "observer" => "observer",
                "operator" => "operator",
                _ => {
                    return Err(ValidationError(
                        "capabilities.role is unknown and cannot negotiate authority".into(),
                    ));
                }
            };
            validate_identity_claim(
                obj.get("identity"),
                "capabilities.identity",
                Some("control"),
                Some(principal_role),
            )?;
            if obj
                .get("identity")
                .and_then(|value| value.get("entity_id"))
                .and_then(serde_json::Value::as_str)
                != Some(controller_id)
            {
                return Err(ValidationError(
                    "capabilities.controller_id must equal capabilities.identity.entity_id".into(),
                ));
            }
            validate_security_negotiation(obj, "capabilities")?;
            validate_gateway_attribution(obj, "capabilities")?;
            let stable = required_json_array(
                obj.get("stable_capabilities"),
                "capabilities.stable_capabilities",
            )?;
            let mut advertised = std::collections::BTreeSet::new();
            if stable.len() > 64 {
                return Err(ValidationError(
                    "capabilities.stable_capabilities exceeds the 64-entry limit".into(),
                ));
            }
            for (index, capability) in stable.iter().enumerate() {
                let capability = capability
                    .as_str()
                    .filter(|value| !value.is_empty())
                    .ok_or_else(|| {
                        ValidationError(format!(
                            "capabilities.stable_capabilities[{index}] must be a non-empty string"
                        ))
                    })?;
                if !KNOWN_STABLE_CAPABILITIES.contains(&capability) {
                    return Err(ValidationError(format!(
                        "capabilities.stable_capabilities contains unknown or non-stable capability {capability:?}"
                    )));
                }
                if !advertised.insert(capability) {
                    return Err(ValidationError(format!(
                        "capabilities.stable_capabilities contains duplicate {capability:?}"
                    )));
                }
            }
            for required in CORE_STABLE_CAPABILITIES {
                if !advertised.contains(required) {
                    return Err(ValidationError(format!(
                        "capabilities.stable_capabilities omits required core capability {required:?}"
                    )));
                }
            }
            if let Some(digest) = obj
                .get("plant_profile_digest")
                .filter(|value| !value.is_null())
            {
                let digest = digest.as_str().ok_or_else(|| {
                    ValidationError(
                        "capabilities.plant_profile_digest must be a string or null".into(),
                    )
                })?;
                if !valid_sha256_hex(digest) {
                    return Err(ValidationError(
                        "capabilities.plant_profile_digest must be 64 lowercase hexadecimal characters"
                            .into(),
                    ));
                }
            }
            if role == "plant"
                && obj
                    .get("plant_profile_digest")
                    .is_none_or(serde_json::Value::is_null)
            {
                return Err(ValidationError(
                    "plant capabilities require a content-addressed plant_profile_digest".into(),
                ));
            }
            let rate = finite_number(
                obj.get("control_rate_hz").ok_or_else(|| {
                    ValidationError("capabilities.control_rate_hz is required".into())
                })?,
                "capabilities.control_rate_hz",
            )?;
            if rate <= 0.0 {
                return Err(ValidationError(
                    "capabilities.control_rate_hz must be > 0".into(),
                ));
            }
            for field in ["sensor_channels", "command_channels"] {
                let channels =
                    required_json_array(obj.get(field), &format!("capabilities.{field}"))?;
                if channels.len() > MAX_CHANNELS {
                    return Err(ValidationError(format!(
                        "capabilities.{field} exceeds the {MAX_CHANNELS}-channel limit"
                    )));
                }
                let mut names = std::collections::BTreeSet::new();
                for (index, value) in channels.iter().enumerate() {
                    let path = format!("capabilities.{field}[{index}]");
                    let channel = required_json_object(Some(value), &path)?;
                    let name = required_nonempty_string(channel, "name", &format!("{path}.name"))?;
                    let channel_kind =
                        required_nonempty_string(channel, "kind", &format!("{path}.kind"))?;
                    let requirement = required_nonempty_string(
                        channel,
                        "requirement",
                        &format!("{path}.requirement"),
                    )?;
                    if !matches!(requirement, "required" | "optional") {
                        return Err(ValidationError(format!(
                            "{path}.requirement must explicitly be required or optional"
                        )));
                    }
                    if !matches!(channel_kind, "scalar" | "vec3" | "quat" | "array") {
                        return Err(ValidationError(format!(
                            "{path}.kind is unknown and cannot negotiate channel semantics"
                        )));
                    }
                    if !names.insert(name) {
                        return Err(ValidationError(format!(
                            "capabilities.{field} contains duplicate channel {name:?}"
                        )));
                    }
                    if let Some(size) = channel.get("size").filter(|value| !value.is_null()) {
                        if json_exact_i64(size).is_none_or(|size| size <= 0) {
                            return Err(ValidationError(format!(
                                "{path}.size must be a positive integer or null"
                            )));
                        }
                    }
                }
            }
            let safety = required_json_object(obj.get("safety"), "capabilities.safety")?;
            let timeout = finite_number(
                safety.get("command_timeout_ms").ok_or_else(|| {
                    ValidationError("capabilities.safety.command_timeout_ms is required".into())
                })?,
                "capabilities.safety.command_timeout_ms",
            )?;
            if timeout <= 0.0 {
                return Err(ValidationError(
                    "capabilities.safety.command_timeout_ms must be > 0".into(),
                ));
            }
            for field in ["max_speed_mps", "max_tilt_rad", "geofence_radius_m"] {
                if let Some(value) = safety.get(field).filter(|value| !value.is_null()) {
                    if finite_number(value, &format!("capabilities.safety.{field}"))? < 0.0 {
                        return Err(ValidationError(format!(
                            "capabilities.safety.{field} must be >= 0"
                        )));
                    }
                }
            }
        }
        "control_status" => {
            validate_json_stream_position(obj.get("stream"), "control_status.stream")?;
            finite_number(
                obj.get("t")
                    .ok_or_else(|| ValidationError("control_status.t is required".into()))?,
                "control_status.t",
            )?;
            if let Some(sim_time) = obj.get("sim_time_ms") {
                finite_number(sim_time, "control_status.sim_time_ms")?;
            }
            let latency = finite_number(
                obj.get("loop_latency_ms").ok_or_else(|| {
                    ValidationError("control_status.loop_latency_ms is required".into())
                })?,
                "control_status.loop_latency_ms",
            )?;
            if latency < 0.0 {
                return Err(ValidationError(
                    "control_status.loop_latency_ms must be >= 0".into(),
                ));
            }
            required_nonempty_string(obj, "mode", "control_status.mode")?;
        }
        "link_status" => {
            validate_json_stream_position(obj.get("stream"), "link_status.stream")?;
            finite_number(
                obj.get("t")
                    .ok_or_else(|| ValidationError("link_status.t is required".into()))?,
                "link_status.t",
            )?;
            for field in ["received", "lost"] {
                let value = obj.get(field).and_then(json_exact_i64).ok_or_else(|| {
                    ValidationError(format!("link_status.{field} must be an integer"))
                })?;
                if value < 0 {
                    return Err(ValidationError(format!("link_status.{field} must be >= 0")));
                }
            }
            let observed = obj.get("observed_stream").filter(|value| !value.is_null());
            let last_arrival = obj.get("last_arrival_seq").filter(|value| !value.is_null());
            if observed.is_some() != last_arrival.is_some() {
                return Err(ValidationError(
                    "link_status.observed_stream and last_arrival_seq must be present together"
                        .into(),
                ));
            }
            if let (Some(observed), Some(last_arrival)) = (observed, last_arrival) {
                let high_water =
                    validate_json_stream_position(Some(observed), "link_status.observed_stream")?;
                let last_arrival = json_exact_i64(last_arrival)
                    .filter(|seq| (1..=JSON_SAFE_INTEGER_MAX).contains(seq))
                    .ok_or_else(|| {
                        ValidationError(
                            "link_status.last_arrival_seq must be a JSON-safe integer within 1..=2^53-1"
                                .into(),
                        )
                    })?;
                if last_arrival > high_water {
                    return Err(ValidationError(
                        "link_status.last_arrival_seq cannot exceed observed_stream.seq".into(),
                    ));
                }
            }
            let loss = finite_number(
                obj.get("loss_rate")
                    .ok_or_else(|| ValidationError("link_status.loss_rate is required".into()))?,
                "link_status.loss_rate",
            )?;
            if !(0.0..=1.0).contains(&loss) {
                return Err(ValidationError(
                    "link_status.loss_rate must be in [0, 1]".into(),
                ));
            }
        }
        _ => {}
    }
    if matches!(kind, "step_request" | "run_request" | "close_session") {
        crate::request_digest::verify_request_digest(&serde_json::Value::Object(obj.clone()))
            .map_err(|error| ValidationError(error.to_string()))?;
    }
    Ok(())
}

fn check_safe_integer(value: &serde_json::Value, path: &str) -> Result<(), ValidationError> {
    if value.is_null() {
        return Ok(());
    }
    if json_exact_i64(value).is_none() {
        return Err(ValidationError(format!("{path} must be an integer")));
    }
    Ok(())
}

fn check_safe_integer_array(
    value: Option<&serde_json::Value>,
    path: &str,
) -> Result<(), ValidationError> {
    let Some(value) = value else { return Ok(()) };
    let Some(values) = value.as_array() else {
        return Err(ValidationError(format!("{path} must be an array")));
    };
    for (index, value) in values.iter().enumerate() {
        check_safe_integer(value, &format!("{path}[{index}]"))?;
    }
    Ok(())
}

fn check_safe_integer_map(
    value: Option<&serde_json::Value>,
    path: &str,
) -> Result<(), ValidationError> {
    let Some(value) = value else { return Ok(()) };
    let Some(values) = value.as_object() else {
        return Err(ValidationError(format!("{path} must be an object")));
    };
    for (key, value) in values {
        check_safe_integer(value, &format!("{path}[{key:?}]"))?;
    }
    Ok(())
}

/// Enforce the exact cross-language range only at schema-known `int64` paths.
/// Unknown additive fields remain ignored even if they happen to reuse a name
/// like `seq`; forward compatibility must not depend on extension internals.
fn validate_safe_integers(
    kind: &str,
    obj: &serde_json::Map<String, serde_json::Value>,
) -> Result<(), ValidationError> {
    match kind {
        "open_session" => {
            if let Some(network) = obj.get("network").and_then(|v| v.as_object()) {
                check_safe_integer_map(
                    network.get("population_sizes"),
                    "open_session.network.population_sizes",
                )?;
            }
            for (index, target) in obj
                .get("record")
                .and_then(|v| v.get("targets"))
                .and_then(|v| v.as_array())
                .into_iter()
                .flatten()
                .enumerate()
            {
                check_safe_integer_array(
                    target.get("ids"),
                    &format!("open_session.record.targets[{index}].ids"),
                )?;
            }
            for (index, target) in obj
                .get("stimulus")
                .and_then(|v| v.get("targets"))
                .and_then(|v| v.as_array())
                .into_iter()
                .flatten()
                .enumerate()
            {
                check_safe_integer_array(
                    target.get("ids"),
                    &format!("open_session.stimulus.targets[{index}].ids"),
                )?;
            }
            if let Some(seed) = obj.get("sim").and_then(|v| v.get("seed")) {
                check_safe_integer(seed, "open_session.sim.seed")?;
            }
        }
        "session_opened" => {
            check_safe_integer_map(obj.get("resolved"), "session_opened.resolved")?;
            if let Some(seed) = obj.get("provenance").and_then(|v| v.get("seed")) {
                check_safe_integer(seed, "session_opened.provenance.seed")?;
            }
        }
        "capabilities" => {
            for field in ["sensor_channels", "command_channels"] {
                for (index, channel) in obj
                    .get(field)
                    .and_then(|v| v.as_array())
                    .into_iter()
                    .flatten()
                    .enumerate()
                {
                    if let Some(size) = channel.get("size") {
                        check_safe_integer(size, &format!("capabilities.{field}[{index}].size"))?;
                    }
                }
            }
        }
        "sensor_frame" | "command_frame" | "control_status" | "observation_frame" => {
            if let Some(stream) = obj.get("stream").and_then(|v| v.as_object()) {
                if let Some(seq) = stream.get("seq") {
                    check_safe_integer(seq, &format!("{kind}.stream.seq"))?;
                }
            }
            if let Some(source) = obj.get("source").and_then(|v| v.as_object()) {
                if let Some(seq) = source.get("seq") {
                    check_safe_integer(seq, &format!("{kind}.source.seq"))?;
                }
            }
            if kind == "observation_frame" {
                if let Some(records) = obj.get("records").and_then(|v| v.as_object()) {
                    for (port, record) in records {
                        check_safe_integer_array(
                            record.get("senders"),
                            &format!("observation_frame.records[{port:?}].senders"),
                        )?;
                    }
                }
            }
        }
        "link_status" => {
            for field in ["received", "lost", "last_arrival_seq"] {
                if let Some(value) = obj.get(field).filter(|v| !v.is_null()) {
                    check_safe_integer(value, &format!("link_status.{field}"))?;
                }
            }
            for pos in ["stream", "observed_stream"] {
                if let Some(seq) = obj
                    .get(pos)
                    .and_then(|v| v.as_object())
                    .and_then(|s| s.get("seq"))
                {
                    check_safe_integer(seq, &format!("link_status.{pos}.seq"))?;
                }
            }
        }
        _ => {}
    }
    Ok(())
}

/// Enforce the scientific-boundary discriminators as explicit wire assertions.
/// Absence is invalid: fabricating safe values locally would claim provenance the
/// producer never supplied.
fn check_scientific_boundary(
    obj: &serde_json::Map<String, serde_json::Value>,
    ctx: &str,
) -> Result<(), ValidationError> {
    let calibrated = obj.get("calibrated_posterior").ok_or_else(|| {
        ValidationError(format!(
            "{ctx}: calibrated_posterior is an explicit mandatory honesty-boundary field"
        ))
    })?;
    if calibrated.as_bool() != Some(false) {
        return Err(ValidationError(format!(
            "{ctx}: calibrated_posterior must be false (an NCP frame is sim \
             output, never a calibrated posterior), got {calibrated}"
        )));
    }
    let simulation = obj.get("is_simulation_output").ok_or_else(|| {
        ValidationError(format!(
            "{ctx}: is_simulation_output is an explicit mandatory honesty-boundary field"
        ))
    })?;
    if simulation.as_bool() != Some(true) {
        return Err(ValidationError(format!(
            "{ctx}: is_simulation_output must be true (NCP frames are \
             simulation output), got {simulation}"
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::test_ids::{session, stream, EPOCH, GEN, SID};
    use super::*;

    #[test]
    fn unknown_enum_values_are_preserved_before_path_semantics() {
        // Deserialization retains every unrecognized string so diagnostics and
        // relays do not rewrite it. The operational validators below still reject
        // unknown values at paths where interpretation would be required.
        assert_eq!(
            serde_json::from_str::<Observable>("\"lfp_v5\"").unwrap(),
            Observable::Unknown("lfp_v5".into())
        );
        assert_eq!(
            serde_json::from_str::<StimulusKind>("\"optogenetic\"").unwrap(),
            StimulusKind::Unknown("optogenetic".into())
        );
        assert_eq!(
            serde_json::from_str::<NetworkRefKind>("\"future_kind\"").unwrap(),
            NetworkRefKind::Unknown("future_kind".into())
        );
        assert_eq!(
            serde_json::from_str::<ChannelKind>("\"tensor\"").unwrap(),
            ChannelKind::Unknown("tensor".into())
        );
        assert_eq!(
            serde_json::from_str::<Role>("\"coordinator\"").unwrap(),
            Role::Unknown("coordinator".into())
        );
        assert_eq!(
            serde_json::from_str::<ChannelRequirement>("\"recommended\"").unwrap(),
            ChannelRequirement::Unknown("recommended".into())
        );
        assert_eq!(
            serde_json::from_str::<EntityRole>("\"swarm\"").unwrap(),
            EntityRole::Unknown("swarm".into())
        );
        assert_eq!(
            serde_json::from_str::<SimMode>("\"realtime\"").unwrap(),
            SimMode::Unknown("realtime".into())
        );
        assert_eq!(
            serde_json::from_str::<Mode>("\"land\"").unwrap(),
            Mode::Unknown("land".into())
        );
        // Known values still parse exactly; the sentinel only catches the unrecognized.
        assert_eq!(
            serde_json::from_str::<Observable>("\"spikes\"").unwrap(),
            Observable::Spikes
        );
        // A nested carrier also preserves the value before path semantics run.
        let rt: RecordTarget =
            serde_json::from_str(r#"{"port":"p","target":"t","observable":"lfp_v5"}"#).unwrap();
        assert_eq!(rt.observable, Observable::Unknown("lfp_v5".into()));
        assert_eq!(
            serde_json::to_string(&rt.observable).unwrap(),
            "\"lfp_v5\"",
            "an unknown enum value must survive decode -> encode unchanged"
        );
        assert!(serde_json::from_str::<Observable>("\"\"").is_err());
    }

    #[test]
    fn closed_enum_paths_reject_unknown_values_while_mode_remains_fail_safe() {
        let load = |name: &str| {
            let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("testdata/conformance/vectors")
                .join(name);
            serde_json::from_slice::<serde_json::Value>(
                &std::fs::read(&path)
                    .unwrap_or_else(|error| panic!("failed to read {}: {error}", path.display())),
            )
            .unwrap_or_else(|error| panic!("failed to parse {}: {error}", path.display()))
        };

        let mut open = load("open_session.json");
        open["bindings"] = serde_json::json!([{
            "port": "sensor",
            "direction": "record",
            "entity": {"path": "body/sensor", "role": "sensor"}
        }]);
        assert!(
            validate(&open).is_ok(),
            "canonical open_session must validate"
        );
        for (path, value) in [
            (&["network", "kind"][..], "future_loader"),
            (&["sim", "mode"][..], "realtime"),
            (&["record", "targets", "0", "observable"][..], "lfp_v5"),
            (&["stimulus", "targets", "0", "kind"][..], "optogenetic"),
            (&["bindings", "0", "entity", "role"][..], "swarm"),
        ] {
            let mut candidate = open.clone();
            let mut node = &mut candidate;
            for segment in &path[..path.len() - 1] {
                node = if let Ok(index) = segment.parse::<usize>() {
                    &mut node.as_array_mut().expect("test path array")[index]
                } else {
                    node.get_mut(*segment).expect("test path object member")
                };
            }
            node[path[path.len() - 1]] = value.into();
            assert!(
                validate(&candidate).is_err(),
                "unknown operational enum at {path:?} must fail closed"
            );
        }

        let capabilities = load("capabilities.json");
        assert!(
            validate(&capabilities).is_ok(),
            "canonical capabilities must validate"
        );
        let mut unknown_channel = capabilities.clone();
        unknown_channel["sensor_channels"][0]["kind"] = "tensor".into();
        assert!(
            validate(&unknown_channel).is_err(),
            "an unknown required channel kind must fail negotiation"
        );

        let mut optional_unknown = unknown_channel;
        optional_unknown["sensor_channels"][0]["requirement"] = "optional".into();
        assert!(
            validate(&optional_unknown).is_err(),
            "a globally closed channel kind must fail even when optional"
        );
    }

    #[test]
    fn unknown_field_in_a_nested_message_is_ignored_not_rejected() {
        // Forward-compat must hold for an unknown field NESTED inside a message, not
        // only at the top level: every struct is `#[serde(default)]` with no
        // `deny_unknown_fields`, so a newer peer can add a field at any depth and an
        // older peer still decodes the frame (it ignores what it does not know).
        // (1) an unknown field inside the nested `NetworkRef` of an `OpenSession`.
        let open: OpenSession = serde_json::from_str(
            r#"{"session_id":"s","network":{"kind":"builtin","ref":"iaf_psc_alpha","future_nested":[1,2]}}"#,
        )
        .unwrap();
        assert_eq!(open.network.ref_, "iaf_psc_alpha");
        // (2) an unknown field TWO levels deep: a recorded series inside an
        // `ObservationFrame` (`records[port]` -> `Observation`).
        let obs: ObservationFrame = serde_json::from_str(
            r#"{"session_id":"s","records":{"vm":{"port":"vm","target":"n0","observable":"V_m","future_series_field":"tbd"}}}"#,
        )
        .unwrap();
        assert_eq!(obs.records["vm"].observable, Observable::Vm);
    }

    #[test]
    fn check_version_rejects_malformed_minor_no_coercion() {
        // core-wire-1: a present-but-garbage minor or a trailing component must
        // REJECT (Err in strict mode), never silently coerce to minor 0. Tested
        // here against the live "1.0": none may parse as a valid two-component wire.
        for bad in [
            "1.GARBAGE",
            "1.0.1",
            "1.0x",
            "1.",
            "1.0.0",
            "x.6",
            "0.0.0.0",
            "", // an ABSENT ncp_version deserializes to "" — must reject, never coerce
        ] {
            assert!(
                check_version(bad, true).is_err(),
                "malformed version {bad:?} must be rejected, not coerced"
            );
        }
        // Stable wire 1.x is major-compatible; the released 0.8 line remains a
        // deliberately incompatible gateway boundary.
        assert_eq!(check_version("1.0", true), Ok(true));
        assert_eq!(check_version("1", true), Ok(true));
        assert_eq!(check_version("1.9", true), Ok(true));
        assert!(check_version("0", true).is_err(), "0.x != 1.x");
        assert!(
            check_version("0.8", true).is_err(),
            "released wire 0.8 is incompatible without the labelled gateway"
        );
        // Non-strict mode surfaces the same rejection as Ok(false), not a coerced pass.
        assert_eq!(check_version("0.1", false), Ok(false));
    }

    #[test]
    fn check_version_accepts_canonical_stable_minor_through_u64_max() {
        for version in ["1", "1.0", "1.9", "1.18446744073709551615"] {
            assert_eq!(
                check_version(version, true),
                Ok(true),
                "canonical stable-line version {version:?} must be compatible"
            );
        }
    }

    #[test]
    fn check_version_rejects_noncanonical_or_overflow_components() {
        for version in [
            "01",
            "01.0",
            "1.00",
            "1.01",
            "1.١",
            "1.0\n",
            "1.18446744073709551616",
        ] {
            assert!(
                check_version(version, false).is_err(),
                "noncanonical or out-of-range version {version:?} must be malformed"
            );
        }
    }

    #[test]
    fn contract_hash_matches_proto() {
        // Drift guard: recompute the canonical contract hash of the real proto and
        // assert it equals the pinned CONTRACT_HASH, so any *semantic* proto edit
        // must bump the constant (a comment-only edit must NOT — see below).
        let proto = std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/testdata/proto/ncp.proto"
        ))
        .expect("packaged proto snapshot is readable");
        assert_eq!(
            contract_hash_of_proto(&proto),
            CONTRACT_HASH,
            "proto's semantic contract changed without bumping CONTRACT_HASH (or vice versa)"
        );
    }

    #[test]
    fn contract_hash_ignores_comments_and_formatting() {
        let proto = std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/testdata/proto/ncp.proto"
        ))
        .expect("packaged proto snapshot is readable");
        let base = contract_hash_of_proto(&proto);

        // Inserting comments and blank lines must NOT change the contract hash.
        let mut commented = String::from_utf8_lossy(&proto).into_owned();
        commented
            .push_str("\n// a brand-new trailing comment\n/* and a block\n   comment */\n\n\n");
        commented = commented.replace(
            "message OpenSession {",
            "message OpenSession { // inline note",
        );
        assert_eq!(
            contract_hash_of_proto(commented.as_bytes()),
            base,
            "comment/whitespace-only edits must not change the contract hash"
        );

        // A NAMING-ONLY change (the proto `package`) must NOT change the hash — the
        // wire is identical, only the codegen namespace differs (the v0.4 decoupling
        // of `engram.ncp.v0 -> ncp.v0` is hash-neutral by construction).
        let renamed =
            String::from_utf8_lossy(&proto).replace("package ncp.v0;", "package engram.ncp.v0;");
        assert_eq!(
            contract_hash_of_proto(renamed.as_bytes()),
            base,
            "a package/naming-only change must NOT change the contract hash"
        );
        // A top-level option line must also be hash-neutral (non-wire metadata).
        let optioned = format!(
            "{}\noption go_package = \"x\";\n",
            String::from_utf8_lossy(&proto)
        );
        assert_eq!(
            contract_hash_of_proto(optioned.as_bytes()),
            base,
            "a top-level option must not change the contract hash"
        );

        // A real wire change (a new field) MUST change the hash.
        let semantic = String::from_utf8_lossy(&proto).replace(
            "string ncp_version = 1;",
            "string ncp_version = 1;\n  string injected = 99;",
        );
        assert_ne!(
            contract_hash_of_proto(semantic.as_bytes()),
            base,
            "a semantic wire change must change the contract hash"
        );

        // NCP's enum JSON mapping lives in a deliberately structured proto comment.
        // Changing it is wire-semantic even though protobuf binary ignores comments.
        let remapped = String::from_utf8_lossy(&proto).replacen(
            "wire string \"V_m\"",
            "wire string \"membrane_voltage\"",
            1,
        );
        assert_ne!(
            contract_hash_of_proto(remapped.as_bytes()),
            base,
            "changing an enum JSON wire-string annotation must change the contract hash"
        );

        let rerouted = String::from_utf8_lossy(&proto).replacen(
            "wire key \"{realm}/rpc/open_session\"",
            "wire key \"{realm}/rpc/open\"",
            1,
        );
        assert_ne!(
            contract_hash_of_proto(rerouted.as_bytes()),
            base,
            "changing a normative transport-key annotation must change the contract hash"
        );

        let proto2 =
            String::from_utf8_lossy(&proto).replace("syntax = \"proto3\";", "syntax = \"proto2\";");
        assert_ne!(
            contract_hash_of_proto(proto2.as_bytes()),
            base,
            "changing protobuf syntax changes presence/default semantics and must change the hash"
        );

        // A `//` inside a string literal must be preserved (not treated as a comment).
        assert!(
            String::from_utf8(canonical_proto(b"string k = 1; // c\nstring s = \"a//b\";"))
                .unwrap()
                .contains("\"a//b\""),
            "string-literal contents must survive canonicalization"
        );
    }

    #[test]
    fn required_fields_match_the_schemas() {
        // Drift guard: required_fields() (the validator's source of truth) MUST
        // equal each JSON Schema's `required` array, so the Rust validator and the
        // schema corpus cannot silently disagree about what a wire message must
        // carry. Also asserts every schema `kind` has a required_fields() entry.
        use std::collections::BTreeSet;
        let dir = concat!(env!("CARGO_MANIFEST_DIR"), "/testdata/schemas");
        let mut checked = 0;
        for entry in std::fs::read_dir(dir).expect("packaged schema snapshots are readable") {
            let path = entry.unwrap().path();
            if !path.to_string_lossy().ends_with(".schema.json") {
                continue;
            }
            let schema: serde_json::Value =
                serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            let Some(kind) = schema["properties"]["kind"]["const"].as_str() else {
                continue;
            };
            let schema_required: BTreeSet<String> = schema
                .get("required")
                .and_then(|r| r.as_array())
                .map(|a| {
                    a.iter()
                        .filter_map(|v| v.as_str().map(String::from))
                        .collect()
                })
                .unwrap_or_default();
            let rf = required_fields(kind)
                .unwrap_or_else(|| panic!("schema kind {kind:?} has no required_fields() entry"));
            let rf_set: BTreeSet<String> = rf.iter().map(|s| (*s).to_string()).collect();
            assert_eq!(
                rf_set,
                schema_required,
                "required_fields({kind:?}) disagrees with {}'s `required`",
                path.file_name().unwrap().to_string_lossy()
            );
            checked += 1;
        }
        assert_eq!(
            checked, 14,
            "expected all 14 schema kinds, checked {checked}"
        );
    }

    #[test]
    fn negotiate_gates_version_advisory_contract() {
        // Version is the HARD gate; contract hash is ADVISORY.
        assert_eq!(
            negotiate(NCP_VERSION, Some(CONTRACT_HASH)),
            Ok(ContractStatus::Match)
        );
        assert_eq!(
            negotiate(NCP_VERSION, None),
            Ok(ContractStatus::NotAdvertised)
        );
        // Hash mismatch does NOT fail the handshake — it is surfaced as advisory so a
        // version-compatible flow (e.g. one peer added an optional field) keeps working.
        let status = negotiate(NCP_VERSION, Some("deadbeefdeadbeef")).expect("version ok");
        assert!(matches!(status, ContractStatus::Mismatch { .. }));
        assert!(!status.is_match());
        assert!(status.advisory().is_some());
        // Version mismatch still rejects (hard gate), regardless of the hash.
        assert!(negotiate("0.1", Some(CONTRACT_HASH)).is_err());
    }

    #[test]
    fn verify_contract_strict_still_fails_closed_opt_in() {
        // The opt-in strict path still rejects a mismatch, for safety-certified configs.
        assert!(verify_contract(Some(CONTRACT_HASH)).is_ok());
        assert!(verify_contract(None).is_ok());
        assert!(verify_contract(Some("deadbeefdeadbeef")).is_err());
    }

    #[test]
    fn rpc_error_builder_always_emits_a_valid_frame() {
        let bytes = rpc_error_payload(
            RpcErrorCode::ContainedInternalFailure,
            "",
            Some("bad/*".into()),
            Some(String::new()),
        );
        let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        validate(&value).unwrap();
        assert_eq!(value["code"], "NCP-INTERNAL-001");
        assert_eq!(value["error"], "contained internal failure");
        assert_eq!(value["session_id"], serde_json::Value::Null);
        assert_eq!(value["request_kind"], serde_json::Value::Null);
    }

    #[test]
    fn rpc_request_validation_preserves_limit_codes_into_error_frames() {
        fn assert_code(payload: &[u8], expected: &str) {
            let error = validate_rpc_request_for("open_session", payload).unwrap_err();
            assert_eq!(error.rpc_error_code().as_str(), expected);
            let reply = rpc_error_payload(
                error.rpc_error_code(),
                error.to_string(),
                None,
                Some("open_session".into()),
            );
            let frame: serde_json::Value = serde_json::from_slice(&reply).unwrap();
            validate(&frame).unwrap();
            assert_eq!(frame["code"], expected);
        }

        assert_code(
            br#"{"kind":"open_session","kind":"open_session"}"#,
            "NCP-LIMIT-007",
        );

        let too_deep = format!(
            "{}0{}",
            "[".repeat(crate::bounded_json::MAX_NESTING_DEPTH + 1),
            "]".repeat(crate::bounded_json::MAX_NESTING_DEPTH + 1)
        );
        assert_code(too_deep.as_bytes(), "NCP-LIMIT-002");

        let too_large = vec![b' '; crate::bounded_json::MAX_FRAME_BYTES + 1];
        assert_code(&too_large, "NCP-LIMIT-001");
        assert_code(br#"{"#, "NCP-LIMIT-009");

        let semantic = validate_rpc_request_for("open_session", br#"{}"#).unwrap_err();
        assert_eq!(semantic.rpc_error_code(), RpcErrorCode::InvalidMessage);
        assert_eq!(semantic.rpc_error_code().as_str(), "NCP-WIRE-001");
    }

    #[test]
    fn registered_error_codes_match_the_packaged_normative_registry() {
        let registry: serde_json::Value =
            serde_json::from_str(include_str!("../testdata/contract/errors.v1.json")).unwrap();
        let codes: Vec<&str> = registry["codes"]
            .as_array()
            .unwrap()
            .iter()
            .map(|entry| entry["code"].as_str().unwrap())
            .collect();
        assert_eq!(codes, REGISTERED_ERROR_CODES);
    }

    #[test]
    fn error_frame_constructor_rejects_unregistered_code() {
        let error = ErrorFrame::new("NCP-NOT-REGISTERED", "bad request").unwrap_err();
        assert!(error.to_string().contains("unregistered NCP error code"));
    }

    #[test]
    fn diagnose_version_flags_mismatch_and_absence() {
        // Compatible frame -> None; an incompatible version -> Some(err).
        let ok = format!(r#"{{"kind":"sensor_frame","ncp_version":"{NCP_VERSION}"}}"#);
        assert!(diagnose_version(ok.as_bytes()).is_none());
        assert!(diagnose_version(br#"{"kind":"sensor_frame","ncp_version":"0.1"}"#).is_some());
        // Wire 0.6: an ABSENT or non-string version is itself diagnosable (the
        // version is mandatory) — no longer a silent None.
        assert!(diagnose_version(br#"{"kind":"sensor_frame"}"#).is_some());
        assert!(diagnose_version(br#"{"kind":"sensor_frame","ncp_version":6}"#).is_some());
        // Unparseable/ambiguous/over-budget JSON -> None. The diagnostic path
        // must not bypass bounded ingress after the primary decoder rejects it.
        assert!(diagnose_version(b"not json").is_none());
        assert!(diagnose_version(br#"{"ncp_version":"1.0","ncp_version":"0.1"}"#).is_none());
        let mut oversized = br#"{"ncp_version":"0.1"}"#.to_vec();
        oversized.resize(crate::bounded_json::MAX_FRAME_BYTES + 1, b' ');
        assert!(diagnose_version(&oversized).is_none());
    }

    #[test]
    fn absent_version_and_kind_deserialize_detectably_empty() {
        // Wire 0.6: the deserialize-side defaults for `ncp_version`/`kind` are ""
        // (field-level `missing_version`/`missing_kind`), NOT the receiver's own
        // constants — an unversioned/kind-less frame must be detectable, never
        // fabricated into a compliant-looking one.
        let sf: SensorFrame = serde_json::from_str(r#"{"seq":1}"#).unwrap();
        assert_eq!(
            sf.ncp_version, "",
            "absent ncp_version must NOT default to ours"
        );
        assert_eq!(
            sf.kind, "",
            "absent kind must NOT default to the correct discriminator"
        );
        // Programmatic construction still stamps both.
        let d = SensorFrame::default();
        assert_eq!(d.ncp_version, NCP_VERSION);
        assert_eq!(d.kind, "sensor_frame");
    }

    #[test]
    fn validate_enforces_version_value_and_seq_bounds() {
        let v = |s: &str| serde_json::from_str::<serde_json::Value>(s).unwrap();
        // A fully-stamped 0.8 command frame passes.
        let cmd = |seq: &str| {
            format!(
                r#"{{"kind":"command_frame","ncp_version":"{NCP_VERSION}","stream":{{"epoch":"{EPOCH}","seq":{seq}}},"session":{{"generation":"{GEN}"}},"session_id":"s"}}"#
            )
        };
        assert!(validate(&v(&cmd("1"))).is_ok());
        // Missing version -> rejected (required key).
        assert!(validate(&v(
            r#"{"kind":"command_frame","stream":{"epoch":"e","seq":1},"session":{"generation":"g"},"session_id":"s"}"#
        ))
        .is_err());
        // Present-but-incompatible version -> rejected (value gate, the audited
        // "incompatible-but-parseable frames are accepted" hole).
        assert!(
            validate(&v(&format!(
                r#"{{"kind":"command_frame","ncp_version":"0.6","stream":{{"epoch":"{EPOCH}","seq":1}},"session":{{"generation":"{GEN}"}},"session_id":"s"}}"#
            )))
            .is_err(),
            "wire 0.6 frames must be rejected by a 0.8 validator"
        );
        // Unstamped / negative / non-integer stream.seq -> rejected on the action plane.
        for bad_seq in [r#"0"#, r#"-3"#, r#"1.5"#, r#""1""#] {
            assert!(
                validate(&v(&cmd(bad_seq))).is_err(),
                "stream.seq {bad_seq} must be rejected"
            );
        }
        // sensor_frame mirrors command_frame: stream.seq 0 is unstamped -> reject.
        let sf = format!(
            r#"{{"kind":"sensor_frame","ncp_version":"{NCP_VERSION}","stream":{{"epoch":"{EPOCH}","seq":0}},"session":{{"generation":"{GEN}"}},"session_id":"s"}}"#
        );
        assert!(
            validate(&v(&sf)).is_err(),
            "sensor stream.seq 0 is unstamped -> reject"
        );
        // observation_frame: wire 0.8 requires stream.seq >= 1 (the pull form is
        // `source` ABSENCE, not seq 0), so stream.seq 0 is rejected and 1 is legal.
        let obs = |seq: &str| {
            format!(
                r#"{{"kind":"observation_frame","ncp_version":"{NCP_VERSION}","session_id":"s","stream":{{"epoch":"{EPOCH}","seq":{seq}}},"session":{{"generation":"{GEN}"}},"records":{{}},"calibrated_posterior":false,"is_simulation_output":true}}"#
            )
        };
        assert!(
            validate(&v(&obs("0"))).is_err(),
            "observation stream.seq 0 -> reject"
        );
        assert!(
            validate(&v(&obs("1"))).is_ok(),
            "observation stream.seq 1 (pull) legal"
        );
    }

    #[test]
    fn status_positions_are_stamped_and_link_observation_is_coherent() {
        let mut control = serde_json::json!({
            "kind": "control_status",
            "ncp_version": NCP_VERSION,
            "t": 0.0,
            "mode": "hold",
            "loop_latency_ms": 0.0,
            "safety_ok": true,
            "stream": {"epoch": EPOCH, "seq": 0},
            "session": {"generation": GEN},
            "session_id": SID,
        });
        assert!(validate(&control).is_err(), "status seq 0 is unstamped");
        control["stream"]["seq"] = 1.into();
        assert!(validate(&control).is_ok());
        control["stream"]["epoch"] = "not-an-epoch".into();
        assert!(validate(&control).is_err());

        let mut link = serde_json::json!({
            "kind": "link_status",
            "ncp_version": NCP_VERSION,
            "session_id": SID,
            "t": 0.0,
            "received": 1,
            "lost": 0,
            "loss_rate": 0.0,
            "burst": false,
            "stream": {"epoch": EPOCH, "seq": 1},
            "session": {"generation": GEN},
        });
        assert!(validate(&link).is_ok());

        link["observed_stream"] = serde_json::json!({"epoch": EPOCH, "seq": 2});
        assert!(
            validate(&link).is_err(),
            "observed_stream and last_arrival_seq are a presence pair"
        );
        link["last_arrival_seq"] = 0.into();
        assert!(validate(&link).is_err(), "an observed arrival starts at 1");
        link["last_arrival_seq"] = 3.into();
        assert!(
            validate(&link).is_err(),
            "last arrival cannot exceed the observed forward high-water"
        );
        link["last_arrival_seq"] = 2.into();
        assert!(validate(&link).is_ok());
    }

    #[test]
    fn validator_rejects_positional_nested_structs_without_panicking() {
        let cases = [
            serde_json::json!({
                "kind": "open_session", "ncp_version": NCP_VERSION,
                "session_id": "s", "network": {"kind": "builtin", "ref": "m"},
                "record": {"targets": [[]]}
            }),
            serde_json::json!({
                "kind": "open_session", "ncp_version": NCP_VERSION,
                "session_id": "s", "network": {"kind": "builtin", "ref": "m"},
                "stimulus": {"targets": [[]]}
            }),
            serde_json::json!({
                "kind": "open_session", "ncp_version": NCP_VERSION,
                "session_id": "s", "network": {"kind": "builtin", "ref": "m"},
                "bindings": [[]]
            }),
            serde_json::json!({
                "kind": "capabilities", "ncp_version": NCP_VERSION,
                "controller_id": "c", "role": "controller", "control_rate_hz": 20,
                "sensor_channels": [[]], "command_channels": [],
                "safety": {"command_timeout_ms": 500}
            }),
            serde_json::json!({
                "kind": "capabilities", "ncp_version": NCP_VERSION,
                "controller_id": "c", "role": "controller", "control_rate_hz": 20,
                "sensor_channels": [], "command_channels": [[]],
                "safety": {"command_timeout_ms": 500}
            }),
            serde_json::json!({
                "kind": "capabilities", "ncp_version": NCP_VERSION,
                "controller_id": "c", "role": "controller", "control_rate_hz": 20,
                "sensor_channels": [], "command_channels": [], "safety": []
            }),
        ];

        for value in cases {
            let result = std::panic::catch_unwind(|| validate(&value));
            assert!(
                result.is_ok(),
                "raw validation must never panic for {value}"
            );
            assert!(
                result.expect("catch checked").is_err(),
                "positional nested struct must be rejected: {value}"
            );
        }
    }

    #[test]
    fn decode_validated_gates_kind_version_and_seq() {
        let ok = format!(
            r#"{{"kind":"command_frame","ncp_version":"{NCP_VERSION}","stream":{{"epoch":"{EPOCH}","seq":3}},"session":{{"generation":"{GEN}"}},"session_id":"s","mode":"active","ttl_ms":200,"channels":{{"velocity_setpoint":{{"data":[0]}}}},"authority":{{"session_epoch":"{GEN}","term":1,"lease_id":"20000000-0000-4000-8000-000000000001","issuer_principal_id":"controller-1","holder_principal_id":"controller-1","holder_entity_id":"body-1","issued_at_utc_ms":1000,"expires_at_utc_ms":2000}}}}"#
        );
        let cmd: CommandFrame = decode_validated(ok.as_bytes()).expect("valid frame decodes");
        assert_eq!(cmd.stream.seq, 3);
        // Kind-less frames no longer decode into a compliant-looking default.
        let kindless = format!(r#"{{"ncp_version":"{NCP_VERSION}","seq":3}}"#);
        assert!(decode_validated::<CommandFrame>(kindless.as_bytes()).is_err());
        // A misrouted frame (observation JSON on the command plane) is rejected.
        let misrouted = format!(
            r#"{{"kind":"observation_frame","ncp_version":"{NCP_VERSION}","session_id":"s","seq":3}}"#
        );
        assert!(decode_validated::<CommandFrame>(misrouted.as_bytes()).is_err());
        // Version-less / stale-wire / unstamped frames are rejected.
        assert!(decode_validated::<CommandFrame>(br#"{"kind":"command_frame","seq":3}"#).is_err());
        assert!(decode_validated::<CommandFrame>(
            br#"{"kind":"command_frame","ncp_version":"0.5","seq":3}"#
        )
        .is_err());
        let unstamped =
            format!(r#"{{"kind":"command_frame","ncp_version":"{NCP_VERSION}","seq":0}}"#);
        assert!(decode_validated::<CommandFrame>(unstamped.as_bytes()).is_err());
        // ObservationFrame pull form: stream.seq >= 1 with `source` ABSENT decodes;
        // stream.seq 0 does not.
        let obs = format!(
            r#"{{"kind":"observation_frame","ncp_version":"{NCP_VERSION}","session_id":"s","stream":{{"epoch":"{EPOCH}","seq":1}},"session":{{"generation":"{GEN}"}},"records":{{}},"calibrated_posterior":false,"is_simulation_output":true}}"#
        );
        assert!(decode_validated::<ObservationFrame>(obs.as_bytes()).is_ok());
        let neg = format!(
            r#"{{"kind":"observation_frame","ncp_version":"{NCP_VERSION}","session_id":"s","stream":{{"epoch":"{EPOCH}","seq":0}},"session":{{"generation":"{GEN}"}},"records":{{}},"calibrated_posterior":false,"is_simulation_output":true}}"#
        );
        assert!(decode_validated::<ObservationFrame>(neg.as_bytes()).is_err());
        assert!(decode_validated::<SensorFrame>(
            br#"{"kind":"sensor_frame","ncp_version":"0.7","seq":1,"channels":{"pose":[]}}"#
        )
        .is_err());
        assert!(decode_validated::<CommandFrame>(
            br#"{"kind":"command_frame","ncp_version":"0.7","seq":1,"channels":{"velocity":[]}}"#
        )
        .is_err());
    }

    #[test]
    fn data_plane_key_session_gates_reject_cross_session_payloads() {
        let sensor = SensorFrame {
            stream: stream(1),
            session: session(),
            session_id: SID.into(),
            ..Default::default()
        };
        let sensor = serde_json::to_vec(&sensor).unwrap();
        let live = session();
        assert!(validate_sensor_plane_payload_for(SID, &live, &sensor).is_ok());
        assert!(validate_sensor_plane_payload_for("other", &live, &sensor).is_err());
        let stale = SessionRef {
            generation: "10000000-0000-4000-8000-000000000003".into(),
        };
        assert!(validate_sensor_plane_payload_for(SID, &stale, &sensor).is_err());

        let command = CommandFrame {
            stream: stream(1),
            session: session(),
            session_id: SID.into(),
            mode: Mode::Hold,
            ttl_ms: 200.0,
            ..Default::default()
        };
        let command = serde_json::to_vec(&command).unwrap();
        assert!(validate_command_plane_payload_for(SID, &live, &command).is_ok());
        assert!(validate_command_plane_payload_for("other", &live, &command).is_err());
        assert!(validate_command_plane_payload_for(SID, &stale, &command).is_err());

        let mut estop: CommandFrame = serde_json::from_slice(&command).unwrap();
        estop.mode = Mode::Estop;
        estop.authority = None;
        let estop = serde_json::to_vec(&estop).unwrap();
        assert!(validate_command_plane_payload_for(SID, &live, &estop).is_ok());
        assert!(validate_command_plane_payload_for("other", &live, &estop).is_err());
        assert!(validate_command_plane_payload_for(SID, &stale, &estop).is_err());
        assert!(validate_command_plane_payload_for(
            SID,
            &live,
            format!(r#"{{"mode":"estop","session_id":"{SID}"}}"#).as_bytes()
        )
        .is_err());

        let observation = ObservationFrame {
            stream: stream(2),
            source: Some(stream(1)),
            session: live.clone(),
            session_id: SID.into(),
            ..Default::default()
        };
        let observation = serde_json::to_vec(&observation).unwrap();
        assert!(validate_observation_plane_payload_for(SID, &live, &observation).is_ok());
        assert!(validate_observation_plane_payload_for("other", &live, &observation).is_err());
        assert!(validate_observation_plane_payload_for(SID, &stale, &observation).is_err());
    }

    #[test]
    fn nonactive_command_payloads_still_obey_resource_and_numeric_bounds() {
        let mut command = CommandFrame {
            stream: stream(1),
            session: session(),
            session_id: SID.into(),
            mode: Mode::Hold,
            ttl_ms: f64::INFINITY,
            ..Default::default()
        };
        assert!(command.validate_wire().is_err());

        command.ttl_ms = 200.0;
        command.channels.insert(
            String::new(),
            ChannelValue {
                data: vec![0.0],
                unit: None,
            },
        );
        assert!(command.validate_wire().is_err());

        command.channels.clear();
        command.horizon = vec![Map::new(); MAX_HORIZON_STEPS + 1];
        assert!(command.validate_wire().is_err());
    }

    #[test]
    fn command_frame_absent_mode_deserializes_to_hold() {
        // Fail-safe: a wire CommandFrame that OMITS `mode` must NOT actuate. An
        // untrusted/partial frame (no mode field) deserializes to HOLD, not Active.
        let cmd: CommandFrame =
            serde_json::from_str(r#"{"kind":"command_frame","seq":1}"#).expect("parses");
        assert_eq!(
            cmd.mode,
            Mode::Hold,
            "a CommandFrame with no `mode` must default to HOLD on the wire"
        );
    }

    #[test]
    fn command_frame_unknown_mode_is_preserved_without_actuation_authority() {
        // Forward compatibility: preserve an unrecognized string so a decode /
        // encode relay does not destroy it. Safety code grants authority only to
        // the exact `Active` variant, so the unknown value still degrades to HOLD.
        let cmd: CommandFrame =
            serde_json::from_str(r#"{"kind":"command_frame","seq":1,"mode":"creep"}"#)
                .expect("unknown mode must parse, not error the frame");
        assert_eq!(cmd.mode, Mode::Unknown("creep".into()));
        assert_ne!(cmd.mode, Mode::Active, "unknown mode cannot actuate");
        assert!(serde_json::to_string(&cmd).unwrap().contains("\"creep\""));
        // Known modes still map and serialize back to their lowercase wire string.
        let active: CommandFrame =
            serde_json::from_str(r#"{"kind":"command_frame","mode":"active"}"#).unwrap();
        assert_eq!(active.mode, Mode::Active);
        assert!(serde_json::to_string(&active)
            .unwrap()
            .contains("\"active\""));
    }

    #[test]
    fn programmatic_unknown_mode_cannot_alias_a_known_wire_authority() {
        let command = CommandFrame {
            stream: stream(1),
            session: session(),
            session_id: SID.into(),
            mode: Mode::Unknown("active".into()),
            ttl_ms: 200.0,
            channels: [("velocity_setpoint".into(), ChannelValue::scalar(1.0, None))]
                .into_iter()
                .collect(),
            ..Default::default()
        };

        assert!(command.validate_wire().is_err());
        assert!(
            serde_json::to_string(&command).is_err(),
            "Unknown(\"active\") must not serialize into canonical Active authority"
        );
        assert!(serde_json::to_string(&Mode::Unknown("hold".into())).is_err());
        assert!(serde_json::to_string(&Mode::Unknown("land".into())).is_ok());
    }
}
