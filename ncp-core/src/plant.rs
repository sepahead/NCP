//! Plant-local action validation for NCP 1.0.
//!
//! NCP `HOLD` and `ESTOP` are protocol states. They are not a certified physical
//! emergency stop. A body validates this profile and remains the final authority
//! over actuators; an unknown or mismatched profile forbids active action.

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

pub const MAX_PLANT_CHANNELS: usize = 256;
pub const MAX_PLANT_CHANNEL_ARITY: usize = 4_096;
pub const MAX_SAFE_HOLD_MS: u64 = 1_000;
pub const PLANT_PROFILE_DIGEST_DOMAIN_V1: &[u8] = b"ncp.plant-profile-digest.v1\0";

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum PlantClass {
    Simulation,
    Uav,
    MobileBase,
    Arm,
    Other,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlantChannel {
    pub name: String,
    pub unit: String,
    pub arity: usize,
    pub min: f64,
    pub max: f64,
    pub actuator_semantics: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SafeActionKind {
    Neutral,
    HoldLast,
    Shutdown,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SafeAction {
    pub kind: SafeActionKind,
    pub channel_values: BTreeMap<String, Vec<f64>>,
    pub hold_max_ms: Option<u64>,
    pub body_local_executor: String,
}

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlantProfile {
    pub schema: String,
    pub status: String,
    pub profile_id: String,
    pub revision: u64,
    pub plant_class: PlantClass,
    pub body_entity_id: String,
    pub command_channels: Vec<PlantChannel>,
    pub hold_action: SafeAction,
    pub estop_action: SafeAction,
    pub body_is_final_authority: bool,
    pub protocol_estop_is_physical_certification: bool,
    pub consumer_safety_case_required: bool,
    pub profile_digest_sha256: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct PlantCommand {
    pub profile_digest_sha256: String,
    pub channels: BTreeMap<String, Vec<f64>>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct PlantProfileError {
    pub code: &'static str,
    pub detail: String,
}

impl PlantProfileError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for PlantProfileError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for PlantProfileError {}

fn valid_id(value: &str, max: usize) -> bool {
    value.len() <= max && crate::keys::valid_id_segment(value)
}

fn valid_text(value: &str, max: usize) -> bool {
    !value.is_empty() && value.len() <= max && !value.chars().any(char::is_control)
}

fn is_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .as_bytes()
            .iter()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
}

impl PlantProfile {
    fn value_without_digest(&self) -> Result<serde_json::Value, PlantProfileError> {
        let mut value = serde_json::to_value(self).map_err(|error| {
            PlantProfileError::new(
                "NCP-PLANT-001",
                format!("profile is not JSON-safe: {error}"),
            )
        })?;
        value
            .as_object_mut()
            .ok_or_else(|| {
                PlantProfileError::new(
                    "NCP-PLANT-001",
                    "profile serialization did not produce a JSON object",
                )
            })?
            .remove("profile_digest_sha256");
        Ok(value)
    }

    pub fn computed_digest(&self) -> Result<String, PlantProfileError> {
        let value = self.value_without_digest()?;
        let canonical =
            crate::canonical_digest::canonical_projection(PLANT_PROFILE_DIGEST_DOMAIN_V1, &value)
                .map_err(|error| {
                PlantProfileError::new(
                    "NCP-PLANT-001",
                    format!("profile canonicalization failed: {error}"),
                )
            })?;
        Ok(crate::canonical_digest::sha256_hex(&canonical))
    }

    fn validate_safe_action(
        &self,
        label: &str,
        action: &SafeAction,
        channels: &BTreeMap<&str, &PlantChannel>,
    ) -> Result<(), PlantProfileError> {
        if !valid_id(&action.body_local_executor, 128) {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                format!("{label}.body_local_executor is invalid"),
            ));
        }
        match action.kind {
            SafeActionKind::HoldLast => {
                let hold = action.hold_max_ms.ok_or_else(|| {
                    PlantProfileError::new(
                        "NCP-PLANT-001",
                        format!("{label} hold_last requires hold_max_ms"),
                    )
                })?;
                if hold == 0 || hold > MAX_SAFE_HOLD_MS || !action.channel_values.is_empty() {
                    return Err(PlantProfileError::new(
                        "NCP-PLANT-001",
                        format!("{label} hold_last duration/values are invalid"),
                    ));
                }
            }
            SafeActionKind::Neutral | SafeActionKind::Shutdown => {
                if action.hold_max_ms.is_some() || action.channel_values.len() != channels.len() {
                    return Err(PlantProfileError::new(
                        "NCP-PLANT-001",
                        format!("{label} must define exactly every command channel"),
                    ));
                }
                for (name, channel) in channels {
                    let values = action.channel_values.get(*name).ok_or_else(|| {
                        PlantProfileError::new(
                            "NCP-PLANT-001",
                            format!("{label} omits command channel {name:?}"),
                        )
                    })?;
                    validate_values(label, channel, values)?;
                }
            }
        }
        Ok(())
    }

    pub fn validate(&self) -> Result<(), PlantProfileError> {
        if self.schema != "ncp.plant-profile.v1" {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "plant profile schema is not ncp.plant-profile.v1",
            ));
        }
        if self.status != "reference-non-certifying" && self.status != "deployment-specific" {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "plant profile status is not recognized",
            ));
        }
        if !valid_id(&self.profile_id, 128)
            || !valid_id(&self.body_entity_id, 128)
            || self.revision == 0
            || self.revision > crate::messages::JSON_SAFE_INTEGER_MAX as u64
            || self.command_channels.is_empty()
            || self.command_channels.len() > MAX_PLANT_CHANNELS
        {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "plant profile identity, revision, or channel count is invalid",
            ));
        }
        if !self.body_is_final_authority
            || self.protocol_estop_is_physical_certification
            || !self.consumer_safety_case_required
        {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "plant profile weakens the body-authority/non-certification boundary",
            ));
        }
        let mut channels = BTreeMap::new();
        let mut prior_name: Option<&str> = None;
        for channel in &self.command_channels {
            if !valid_id(&channel.name, 128)
                || !valid_text(&channel.unit, 64)
                || !valid_text(&channel.actuator_semantics, 512)
                || channel.arity == 0
                || channel.arity > MAX_PLANT_CHANNEL_ARITY
                || !channel.min.is_finite()
                || !channel.max.is_finite()
                || channel.min > channel.max
            {
                return Err(PlantProfileError::new(
                    "NCP-PLANT-001",
                    format!("command channel {:?} is invalid", channel.name),
                ));
            }
            if prior_name.is_some_and(|prior| prior >= channel.name.as_str()) {
                return Err(PlantProfileError::new(
                    "NCP-PLANT-001",
                    "command channels must be unique and lexically sorted",
                ));
            }
            prior_name = Some(&channel.name);
            channels.insert(channel.name.as_str(), channel);
        }
        self.validate_safe_action("hold_action", &self.hold_action, &channels)?;
        if self.estop_action.kind == SafeActionKind::HoldLast {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "ESTOP action cannot retain the last active command",
            ));
        }
        self.validate_safe_action("estop_action", &self.estop_action, &channels)?;
        if !is_digest(&self.profile_digest_sha256)
            || self.profile_digest_sha256 != self.computed_digest()?
        {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "plant profile digest is absent or mismatched",
            ));
        }
        Ok(())
    }

    pub fn validate_active_command(&self, command: &PlantCommand) -> Result<(), PlantProfileError> {
        self.validate()?;
        if command.profile_digest_sha256 != self.profile_digest_sha256 {
            return Err(PlantProfileError::new(
                "NCP-PLANT-001",
                "command references an unknown or stale plant profile",
            ));
        }
        if command.channels.len() != self.command_channels.len() {
            return Err(PlantProfileError::new(
                "NCP-PLANT-002",
                "active command must contain exactly every plant command channel",
            ));
        }
        for channel in &self.command_channels {
            let values = command.channels.get(&channel.name).ok_or_else(|| {
                PlantProfileError::new(
                    "NCP-PLANT-002",
                    format!("active command omits channel {:?}", channel.name),
                )
            })?;
            validate_values("active command", channel, values)?;
        }
        let known: BTreeSet<_> = self
            .command_channels
            .iter()
            .map(|channel| channel.name.as_str())
            .collect();
        if command
            .channels
            .keys()
            .any(|name| !known.contains(name.as_str()))
        {
            return Err(PlantProfileError::new(
                "NCP-PLANT-002",
                "active command contains an unknown plant channel",
            ));
        }
        Ok(())
    }
}

fn validate_values(
    label: &str,
    channel: &PlantChannel,
    values: &[f64],
) -> Result<(), PlantProfileError> {
    if values.len() != channel.arity
        || values
            .iter()
            .any(|value| !value.is_finite() || *value < channel.min || *value > channel.max)
    {
        return Err(PlantProfileError::new(
            "NCP-PLANT-002",
            format!(
                "{label} channel {:?} violates arity/range/finite constraints",
                channel.name
            ),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture() -> PlantProfile {
        let mut profile = PlantProfile {
            schema: "ncp.plant-profile.v1".into(),
            status: "reference-non-certifying".into(),
            profile_id: "simulation-scalar".into(),
            revision: 1,
            plant_class: PlantClass::Simulation,
            body_entity_id: "body".into(),
            command_channels: vec![PlantChannel {
                name: "drive".into(),
                unit: "dimensionless".into(),
                arity: 1,
                min: -1.0,
                max: 1.0,
                actuator_semantics: "bounded simulated input".into(),
            }],
            hold_action: SafeAction {
                kind: SafeActionKind::Neutral,
                channel_values: BTreeMap::from([("drive".into(), vec![0.0])]),
                hold_max_ms: None,
                body_local_executor: "body".into(),
            },
            estop_action: SafeAction {
                kind: SafeActionKind::Shutdown,
                channel_values: BTreeMap::from([("drive".into(), vec![0.0])]),
                hold_max_ms: None,
                body_local_executor: "body".into(),
            },
            body_is_final_authority: true,
            protocol_estop_is_physical_certification: false,
            consumer_safety_case_required: true,
            profile_digest_sha256: String::new(),
        };
        profile.profile_digest_sha256 = profile.computed_digest().unwrap();
        profile
    }

    #[test]
    fn validates_profile_and_exact_active_command() {
        let profile = fixture();
        profile.validate().unwrap();
        profile
            .validate_active_command(&PlantCommand {
                profile_digest_sha256: profile.profile_digest_sha256.clone(),
                channels: BTreeMap::from([("drive".into(), vec![0.5])]),
            })
            .unwrap();
    }

    #[test]
    fn unknown_profile_missing_or_out_of_range_channel_forbids_action() {
        let profile = fixture();
        for command in [
            PlantCommand {
                profile_digest_sha256: "0".repeat(64),
                channels: BTreeMap::from([("drive".into(), vec![0.5])]),
            },
            PlantCommand {
                profile_digest_sha256: profile.profile_digest_sha256.clone(),
                channels: BTreeMap::new(),
            },
            PlantCommand {
                profile_digest_sha256: profile.profile_digest_sha256.clone(),
                channels: BTreeMap::from([("drive".into(), vec![1.01])]),
            },
        ] {
            assert!(profile.validate_active_command(&command).is_err());
        }
    }

    #[test]
    fn protocol_estop_cannot_claim_physical_certification_or_hold_last() {
        let mut profile = fixture();
        profile.protocol_estop_is_physical_certification = true;
        profile.profile_digest_sha256 = profile.computed_digest().unwrap();
        assert!(profile.validate().is_err());

        let mut profile = fixture();
        profile.estop_action = SafeAction {
            kind: SafeActionKind::HoldLast,
            channel_values: BTreeMap::new(),
            hold_max_ms: Some(10),
            body_local_executor: "body".into(),
        };
        profile.profile_digest_sha256 = profile.computed_digest().unwrap();
        assert!(profile.validate().is_err());
    }

    #[test]
    fn safe_action_must_cover_every_channel_and_digest_detects_mutation() {
        let mut profile = fixture();
        profile.hold_action.channel_values.clear();
        assert!(profile.validate().is_err());

        let mut profile = fixture();
        profile.command_channels[0].max = 2.0;
        assert!(profile.validate().is_err());
    }
}
