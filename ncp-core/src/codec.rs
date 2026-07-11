//! Reference sensor→rate encoder and rate→command decoder.
//!
//! The codec is a *declarative* contract (`CodecSpec`) so a trained SNN policy
//! trains against a frozen interface. The reference implementation is linear
//! **rate coding** (deterministic, dependency-light): the encoder maps a
//! sensor-channel component onto a population firing rate; the decoder maps a
//! population's readout rate back onto a command-channel component. Mirrors
//! `backend/neurocontrol/codec.py`.

use crate::messages::{
    ChannelValue, CommandFrame, Map, Mode, SensorFrame, SessionRef, StreamPosition, WireFrame,
    JSON_SAFE_INTEGER_MAX,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

/// Maximum zero-based component index accepted from an untrusted codec spec.
/// This bounds per-channel allocation during decode while remaining far above
/// practical actuator dimensionality.
pub const MAX_CODEC_COMPONENTS: usize = 4096;

/// Invalid codec configuration or input. Codec JSON is deployment data rather
/// than part of the NCP wire, but it still sits on the actuation path and must
/// reject ambiguous/non-finite values instead of manufacturing a command.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CodecError(pub String);

impl std::fmt::Display for CodecError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

impl std::error::Error for CodecError {}

fn valid_codec_name(value: &str) -> bool {
    !value.is_empty() && !value.chars().any(|ch| ch.is_control())
}

fn validate_range(range: (f64, f64), path: &str, nonnegative: bool) -> Result<(), CodecError> {
    let (lo, hi) = range;
    let span = hi - lo;
    if !lo.is_finite()
        || !hi.is_finite()
        || !span.is_finite()
        || span <= 0.0
        || (nonnegative && lo < 0.0)
    {
        return Err(CodecError(format!(
            "{path} must be a finite, strictly increasing{} range with a finite span",
            if nonnegative { ", non-negative" } else { "" }
        )));
    }
    Ok(())
}

fn clamp(x: f64, lo: f64, hi: f64) -> f64 {
    // A non-finite input (NaN/±inf) has no defensible clamped value and would
    // otherwise poison the whole pipeline (NaN sensor -> NaN rate -> NaN
    // command). Fail safe to the low bound rather than propagate it.
    if !x.is_finite() {
        return lo;
    }
    if x < lo {
        lo
    } else if x > hi {
        hi
    } else {
        x
    }
}

fn lerp(x: f64, in_lo: f64, in_hi: f64, out_lo: f64, out_hi: f64) -> f64 {
    if (in_hi - in_lo).abs() < f64::EPSILON {
        return out_lo;
    }
    let frac = clamp((x - in_lo) / (in_hi - in_lo), 0.0, 1.0);
    out_lo + frac * (out_hi - out_lo)
}

fn default_value_range() -> (f64, f64) {
    (-1.0, 1.0)
}
fn default_rate_range() -> (f64, f64) {
    (0.0, 200.0)
}
fn default_codec_id() -> String {
    "ncp.codec.rate.v0".to_string()
}
fn one() -> i64 {
    1
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
pub struct EncoderChannelMap {
    pub channel: String,
    #[serde(default)]
    pub component: usize,
    pub population: String,
    #[serde(default = "default_coding")]
    pub coding: String,
    #[serde(default = "default_value_range")]
    pub value_range: (f64, f64),
    #[serde(default = "default_rate_range")]
    pub rate_range_hz: (f64, f64),
    #[serde(default = "one")]
    pub n_neurons: i64,
}

fn default_coding() -> String {
    "rate".to_string()
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
pub struct DecoderChannelMap {
    pub population: String,
    #[serde(default = "default_readout")]
    pub readout: String,
    pub command_channel: String,
    #[serde(default)]
    pub component: usize,
    #[serde(default)]
    pub unit: Option<String>,
    #[serde(default = "default_rate_range")]
    pub rate_range_hz: (f64, f64),
    #[serde(default = "default_value_range")]
    pub value_range: (f64, f64),
}

fn default_readout() -> String {
    "rate".to_string()
}

#[derive(Serialize, Deserialize, Clone, PartialEq, Debug)]
#[serde(default)]
pub struct CodecSpec {
    pub codec_id: String,
    pub encoder: Vec<EncoderChannelMap>,
    pub decoder: Vec<DecoderChannelMap>,
}

impl Default for CodecSpec {
    fn default() -> Self {
        Self {
            codec_id: default_codec_id(),
            encoder: Vec::new(),
            decoder: Vec::new(),
        }
    }
}

impl CodecSpec {
    /// Validate deployment-supplied codec configuration before it can allocate,
    /// overwrite an ambiguous mapping, or produce non-finite rates/setpoints.
    pub fn validate(&self) -> Result<(), CodecError> {
        if !valid_codec_name(&self.codec_id) {
            return Err(CodecError(
                "codec_id must be non-empty and contain no control characters".into(),
            ));
        }

        let mut encoder_populations = BTreeSet::new();
        for (index, mapping) in self.encoder.iter().enumerate() {
            let path = format!("encoder[{index}]");
            if !valid_codec_name(&mapping.channel) || !valid_codec_name(&mapping.population) {
                return Err(CodecError(format!(
                    "{path}.channel and population must be non-empty and contain no control characters"
                )));
            }
            if mapping.coding != "rate" {
                return Err(CodecError(format!(
                    "{path}.coding {:?} is unsupported (expected \"rate\")",
                    mapping.coding
                )));
            }
            if mapping.component >= MAX_CODEC_COMPONENTS {
                return Err(CodecError(format!(
                    "{path}.component {} exceeds the allocation ceiling {}",
                    mapping.component,
                    MAX_CODEC_COMPONENTS - 1
                )));
            }
            if !(1..=JSON_SAFE_INTEGER_MAX).contains(&mapping.n_neurons) {
                return Err(CodecError(format!(
                    "{path}.n_neurons must be within 1..={JSON_SAFE_INTEGER_MAX}"
                )));
            }
            validate_range(mapping.value_range, &format!("{path}.value_range"), false)?;
            validate_range(
                mapping.rate_range_hz,
                &format!("{path}.rate_range_hz"),
                true,
            )?;
            if !encoder_populations.insert(mapping.population.as_str()) {
                return Err(CodecError(format!(
                    "{path}.population {:?} duplicates an earlier encoder output",
                    mapping.population
                )));
            }
        }

        let mut decoder_components = BTreeSet::new();
        for (index, mapping) in self.decoder.iter().enumerate() {
            let path = format!("decoder[{index}]");
            if !valid_codec_name(&mapping.population) || !valid_codec_name(&mapping.command_channel)
            {
                return Err(CodecError(format!(
                    "{path}.population and command_channel must be non-empty and contain no control characters"
                )));
            }
            if mapping.readout != "rate" {
                return Err(CodecError(format!(
                    "{path}.readout {:?} is unsupported (expected \"rate\")",
                    mapping.readout
                )));
            }
            if mapping.component >= MAX_CODEC_COMPONENTS {
                return Err(CodecError(format!(
                    "{path}.component {} exceeds the allocation ceiling {}",
                    mapping.component,
                    MAX_CODEC_COMPONENTS - 1
                )));
            }
            validate_range(
                mapping.rate_range_hz,
                &format!("{path}.rate_range_hz"),
                true,
            )?;
            validate_range(mapping.value_range, &format!("{path}.value_range"), false)?;
            if !decoder_components.insert((mapping.command_channel.as_str(), mapping.component)) {
                return Err(CodecError(format!(
                    "{path} duplicates command component {:?}[{}]",
                    mapping.command_channel, mapping.component
                )));
            }
        }
        Ok(())
    }

    /// Checked wire-ingress form used by language bindings. `None` is an
    /// intentional missing sensor and maps every population to its neutral rate;
    /// a supplied frame must be a complete compatible SensorFrame.
    pub fn encode_checked(&self, sensor: Option<&SensorFrame>) -> Result<Map<f64>, CodecError> {
        self.validate()?;
        if let Some(sensor) = sensor {
            sensor
                .validate_wire()
                .map_err(|error| CodecError(format!("invalid sensor frame: {error}")))?;
        }
        let rates = self.encode(sensor);
        if rates.values().any(|rate| !rate.is_finite()) {
            return Err(CodecError(
                "codec produced a non-finite population rate".into(),
            ));
        }
        Ok(rates)
    }

    /// Checked wire-egress form used by language bindings. The caller owns the
    /// monotonically increasing sequence; the returned command has passed the
    /// complete CommandFrame wire gate (including Active payload requirements).
    #[allow(clippy::too_many_arguments)]
    pub fn decode_checked(
        &self,
        pop_rates: &Map<f64>,
        t: f64,
        stream: StreamPosition,
        frame_id: &str,
        mode: Mode,
        session: SessionRef,
        session_id: &str,
    ) -> Result<CommandFrame, CodecError> {
        self.validate()?;
        if pop_rates
            .iter()
            .any(|(name, rate)| !valid_codec_name(name) || !rate.is_finite())
        {
            return Err(CodecError(
                "population rates must have non-empty names and finite values".into(),
            ));
        }
        if !t.is_finite() {
            return Err(CodecError("command timestamp must be finite".into()));
        }
        if !valid_codec_name(frame_id) {
            return Err(CodecError(
                "frame_id must be non-empty and contain no control characters".into(),
            ));
        }
        let command = self.decode(pop_rates, t, stream, frame_id, mode, session, session_id);
        command
            .validate_wire()
            .map_err(|error| CodecError(format!("decoded command is not wire-valid: {error}")))?;
        Ok(command)
    }

    /// Map a `SensorFrame` to `{population: firing_rate_hz}`.
    pub fn encode(&self, sensor: Option<&SensorFrame>) -> Map<f64> {
        let mut rates: Map<f64> = Map::new();
        for m in &self.encoder {
            let cv = sensor.and_then(|s| s.channels.get(&m.channel));
            match cv {
                Some(cv) if m.component < cv.data.len() => {
                    rates.insert(
                        m.population.clone(),
                        lerp(
                            cv.data[m.component],
                            m.value_range.0,
                            m.value_range.1,
                            m.rate_range_hz.0,
                            m.rate_range_hz.1,
                        ),
                    );
                }
                _ => {
                    // Missing/short sensor data must not masquerade as the
                    // value-range minimum. For a position/error codec that low
                    // rate represents a real extreme and can provoke a full-scale
                    // response downstream. Preserve shape but encode the neutral
                    // midpoint instead.
                    rates.insert(
                        m.population.clone(),
                        0.5 * (m.rate_range_hz.0 + m.rate_range_hz.1),
                    );
                }
            }
        }
        rates
    }

    /// Map `{population: readout_rate_hz}` to a `CommandFrame`.
    #[allow(clippy::too_many_arguments)]
    pub fn decode(
        &self,
        pop_rates: &Map<f64>,
        t: f64,
        stream: StreamPosition,
        frame_id: &str,
        mode: Mode,
        session: SessionRef,
        session_id: &str,
    ) -> CommandFrame {
        let mut buffers: Map<Vec<f64>> = Map::new();
        let mut units: Map<Option<String>> = Map::new();
        for m in &self.decoder {
            // `component` is deserialized from an untrusted CodecSpec; bound the
            // per-channel buffer growth so a hostile/garbage value cannot drive an
            // unbounded Vec<f64> allocation (OOM/DoS). 4096 >> any real dimensionality.
            if m.component >= MAX_CODEC_COMPONENTS {
                continue;
            }
            // A dropped/renamed readout population must NOT be treated as "rate =
            // low end of the range": for a symmetric range that lerps to the most
            // negative command (e.g. -1.5 m/s — full-reverse actuation), which the
            // governor only magnitude-clamps, so it passes as commanded motion.
            // Map an absent population to the documented NEUTRAL value (the
            // midpoint of value_range — 0.0 for a symmetric range), keeping the
            // command channel shape intact but never emitting max-magnitude
            // actuation for missing data.
            let value = match pop_rates.get(&m.population) {
                Some(rate) => lerp(
                    *rate,
                    m.rate_range_hz.0,
                    m.rate_range_hz.1,
                    m.value_range.0,
                    m.value_range.1,
                ),
                None => 0.5 * (m.value_range.0 + m.value_range.1),
            };
            let buf = buffers.entry(m.command_channel.clone()).or_default();
            while buf.len() <= m.component {
                buf.push(0.0);
            }
            buf[m.component] = value;
            units.insert(m.command_channel.clone(), m.unit.clone());
        }
        let channels: Map<ChannelValue> = buffers
            .into_iter()
            .map(|(name, data)| {
                let unit = units.get(&name).cloned().flatten();
                (name, ChannelValue { data, unit })
            })
            .collect();
        CommandFrame {
            t,
            stream,
            frame_id: frame_id.to_string(),
            mode,
            channels,
            session,
            session_id: session_id.to_string(),
            ..Default::default()
        }
    }
}

/// Illustrative 3-axis position-error → velocity-setpoint codec (untuned; it
/// documents the interface a trained SNN controller would train against).
pub fn default_uav_velocity_codec() -> CodecSpec {
    let mut enc = Vec::new();
    let mut dec = Vec::new();
    for (i, axis) in ["x", "y", "z"].iter().enumerate() {
        enc.push(EncoderChannelMap {
            channel: "pose_error".into(),
            component: i,
            population: format!("err_{axis}"),
            coding: "rate".into(),
            value_range: (-2.0, 2.0),
            rate_range_hz: (0.0, 200.0),
            n_neurons: 1,
        });
        dec.push(DecoderChannelMap {
            population: format!("vel_{axis}"),
            readout: "rate".into(),
            command_channel: "velocity_setpoint".into(),
            component: i,
            unit: Some("m/s".into()),
            rate_range_hz: (0.0, 200.0),
            value_range: (-1.5, 1.5),
        });
    }
    CodecSpec {
        codec_id: default_codec_id(),
        encoder: enc,
        decoder: dec,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::messages::test_ids::{session, stream, SID};

    fn stamped_sensor() -> SensorFrame {
        SensorFrame {
            stream: stream(1),
            session: session(),
            session_id: SID.into(),
            ..Default::default()
        }
    }

    #[test]
    fn default_codec_is_valid_and_checked_paths_emit_finite_wire_data() {
        let codec = default_uav_velocity_codec();
        codec.validate().unwrap();
        let rates = codec.encode_checked(Some(&stamped_sensor())).unwrap();
        assert!(rates.values().all(|rate| rate.is_finite()));

        let command = codec
            .decode_checked(
                &rates,
                0.0,
                stream(1),
                "world",
                Mode::Active,
                session(),
                SID,
            )
            .unwrap();
        assert_eq!(command.mode, Mode::Active);
        command.validate_wire().unwrap();
    }

    #[test]
    fn checked_codec_rejects_invalid_wire_envelopes_and_outputs() {
        let codec = default_uav_velocity_codec();
        let unstamped = SensorFrame::default();
        assert!(codec.encode_checked(Some(&unstamped)).is_err());
        assert!(codec
            .decode_checked(
                &Map::new(),
                0.0,
                stream(0),
                "world",
                Mode::Active,
                session(),
                SID
            )
            .is_err());
        assert!(codec
            .decode_checked(
                &Map::new(),
                f64::NAN,
                stream(1),
                "world",
                Mode::Active,
                session(),
                SID
            )
            .is_err());

        let mut nonfinite_rates = Map::new();
        nonfinite_rates.insert("vel_x".into(), f64::INFINITY);
        assert!(codec
            .decode_checked(
                &nonfinite_rates,
                0.0,
                stream(1),
                "world",
                Mode::Active,
                session(),
                SID
            )
            .is_err());

        assert!(CodecSpec::default()
            .decode_checked(
                &Map::new(),
                0.0,
                stream(1),
                "world",
                Mode::Active,
                session(),
                SID
            )
            .is_err());
    }

    #[test]
    fn missing_or_short_sensor_channel_encodes_neutral_not_extreme() {
        let codec = default_uav_velocity_codec();
        let sensor = stamped_sensor();
        let rates = codec.encode_checked(Some(&sensor)).unwrap();
        assert_eq!(rates["err_x"], 100.0);
        assert_eq!(rates["err_y"], 100.0);
        assert_eq!(rates["err_z"], 100.0);

        let mut short = stamped_sensor();
        short.channels.insert(
            "pose_error".into(),
            ChannelValue {
                data: vec![2.0],
                unit: Some("m".into()),
            },
        );
        let rates = codec.encode_checked(Some(&short)).unwrap();
        assert_eq!(rates["err_x"], 200.0);
        assert_eq!(rates["err_y"], 100.0);
        assert_eq!(rates["err_z"], 100.0);
    }

    #[test]
    fn codec_validation_rejects_ambiguous_or_unbounded_config() {
        let mut codec = default_uav_velocity_codec();
        codec.encoder[0].rate_range_hz = (0.0, f64::INFINITY);
        assert!(codec.validate().is_err());

        let mut codec = default_uav_velocity_codec();
        codec.decoder[0].component = MAX_CODEC_COMPONENTS;
        assert!(codec.validate().is_err());

        let mut codec = default_uav_velocity_codec();
        codec.encoder[1].population = codec.encoder[0].population.clone();
        assert!(codec.validate().is_err());

        let mut codec = default_uav_velocity_codec();
        codec.decoder[1].command_channel = codec.decoder[0].command_channel.clone();
        codec.decoder[1].component = codec.decoder[0].component;
        assert!(codec.validate().is_err());

        let mut codec = default_uav_velocity_codec();
        codec.encoder[0].coding = "future-coding".into();
        assert!(codec.validate().is_err());
    }
}
