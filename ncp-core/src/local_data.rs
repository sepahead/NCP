//! Closed data plane for the candidate local simulation application profile.
//!
//! Times are integer microseconds. Positions, velocities, and accelerations use
//! east/north/up axes in metres, metres per second, and metres per second squared.
//! These application types do not grant remote, physical, or safety authority.

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::local::{local_digest, LocalCode, LocalError, LocalResponse};

/// Largest declared run admitted by this initial simulation application profile.
pub const MAX_STEPS: u64 = 1024;
/// Maximum body entity count in the installed CREBAIN application profile.
pub const MAX_ENTITIES: usize = 3;

/// One axis and its immutable physical meaning.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Component {
    /// Physical quantity, such as position or acceleration.
    pub quantity: String,
    /// Exact SI unit spelling.
    pub unit: String,
    /// Ordered coordinate axis.
    pub axis: String,
    /// Coordinate frame.
    pub frame: String,
}

fn components(quantity: &str, unit: &str) -> Vec<Component> {
    ["east", "north", "up"]
        .into_iter()
        .map(|axis| Component {
            quantity: quantity.into(),
            unit: unit.into(),
            axis: axis.into(),
            frame: "enu".into(),
        })
        .collect()
}

/// Per-entity fused observation layout: position followed by velocity.
pub fn observation_layout() -> Vec<Component> {
    let mut layout = components("position", "m");
    layout.extend(components("velocity", "m/s"));
    layout
}

/// Per-entity acceleration layout accepted by the initial simulated body.
pub fn action_layout() -> Vec<Component> {
    components("acceleration", "m/s^2")
}

/// Immutable joint run plan, supplied identically to all four endpoint roles.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunPlan {
    /// Exact schema `ncp.local.plan.v1`.
    pub schema: String,
    /// Sorted, unique identifiers; no positional roster changes are permitted.
    pub entity_ids: Vec<String>,
    /// Exact number of coupled steps, excluding prepare and finish.
    pub planned_steps: u64,
    /// Positive integral duration of one body and neural advance, in microseconds.
    pub step_us: u64,
    /// Positive NEST integration resolution, in microseconds.
    pub resolution_us: u64,
    /// Explicit NEST minimum connection delay and readout lag, in microseconds.
    pub readout_delay_us: u64,
    /// Explicit deterministic simulator seed. It is not evidence of a fitted model.
    pub seed: u64,
    /// Only `direct_simulation` is admitted by this application profile.
    pub execution_mode: String,
    /// Only `lossless_bounded` is admitted.
    pub capture_mode: String,
    /// Only `record_only` is admitted. A monitor cannot change a command.
    pub monitor_mode: String,
    /// Must be false; calibrated posterior inference is not implemented.
    pub calibrated_posterior: bool,
    /// Ordered components for each entity's observation slice.
    pub observation_layout: Vec<Component>,
    /// Ordered components for each entity's action slice.
    pub action_layout: Vec<Component>,
}

impl RunPlan {
    /// Validate the complete declared initial application envelope.
    pub fn validate(&self) -> Result<(), LocalError> {
        let valid_id = |id: &str| {
            !id.is_empty()
                && id.len() <= 64
                && id
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        };
        if self.schema != "ncp.local.plan.v1"
            || self.entity_ids.is_empty()
            || self.entity_ids.len() > MAX_ENTITIES
            || !self.entity_ids.iter().all(|id| valid_id(id))
            || !self.entity_ids.windows(2).all(|pair| pair[0] < pair[1])
            || !(1..=MAX_STEPS).contains(&self.planned_steps)
            || !(1000..=1_000_000).contains(&self.step_us)
            || !self.step_us.is_multiple_of(1000)
            || !(1..=1000).contains(&self.resolution_us)
            || !self.step_us.is_multiple_of(self.resolution_us)
            || self.readout_delay_us < self.resolution_us
            || self.readout_delay_us >= self.step_us
            || !self.readout_delay_us.is_multiple_of(self.resolution_us)
            || !(1..=2_147_483_647).contains(&self.seed)
            || self.execution_mode != "direct_simulation"
            || self.capture_mode != "lossless_bounded"
            || self.monitor_mode != "record_only"
            || self.calibrated_posterior
            || self.observation_layout != observation_layout()
            || self.action_layout != action_layout()
        {
            return Err(LocalError(LocalCode::InvalidInput));
        }
        Ok(())
    }

    /// Hash every plan member under its declared domain after validation.
    pub fn digest(&self) -> Result<String, LocalError> {
        self.validate()?;
        local_digest(
            "ncp.local.plan.v1",
            &serde_json::to_value(self).map_err(|_| LocalError(LocalCode::Wire))?,
        )
    }

    /// Exact logical boundary for a declared step, in microseconds.
    pub fn time_us(&self, step: u64) -> Result<u64, LocalError> {
        self.validate()?;
        if step > self.planned_steps {
            return Err(LocalError(LocalCode::InvalidInput));
        }
        step.checked_mul(self.step_us)
            .ok_or(LocalError(LocalCode::InvalidInput))
    }
}

/// Shared prepare envelope; the selected owner validates its closed configuration.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrepareData {
    /// Exact immutable joint plan.
    pub plan: RunPlan,
    /// Exact installed application profile; unsupported names fail before mutation.
    pub application_profile: String,
    /// Data only, interpreted by the selected installed profile's closed schema.
    pub configuration: Value,
}

/// Actual availability of one producer diagnostic.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InnovationStatus {
    /// An actual Kalman update produced NIS.
    Observed,
    /// Track initialization has no prior innovation.
    Birth,
    /// No admissible measurement update exists at this step.
    Unavailable,
}

/// Actual source association and raw Kalman diagnostic accompanying scalar NIS.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InnovationSource {
    /// Configured producer sensor label; it is not authenticated device identity.
    pub sensor_id: String,
    /// Actual lane-local track identifier.
    pub fusion_track_id: u64,
    /// Actual fusion position, distinct from the body step index.
    pub fusion_sequence: u64,
    /// Original measurement time, converted exactly to integer microseconds.
    pub measurement_time_us: u64,
    /// Actual residual in east/north/up metres.
    pub residual_m: [f64; 3],
    /// Actual row-major innovation covariance in square metres.
    pub covariance_m2: [[f64; 3]; 3],
}

/// Scalar NIS produced by the body kernel, with its declared innovation dimension.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScalarInnovation {
    /// Entity to which this diagnostic belongs.
    pub entity_id: String,
    /// Actual producer modality; the initial body emits `visual` only.
    pub modality: String,
    /// Positive innovation dimension. It is not an estimated degrees-of-freedom fit.
    pub dof: u8,
    /// Why a numeric NIS is present or absent.
    pub status: InnovationStatus,
    /// Dimensionless NIS, present exactly when status is observed.
    pub nis: Option<f64>,
    /// Present exactly for an observed update; never reconstructed from position.
    pub source: Option<InnovationSource>,
}

/// One immutable source sample. Unavailable fixed-width slices contain inert zeros.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    /// Exact schema `ncp.local.snapshot.v1`.
    pub schema: String,
    /// Digest of the complete immutable plan.
    pub plan_digest: String,
    /// Completed body step; initial sample is step zero.
    pub step: u64,
    /// Exact logical sample boundary in microseconds.
    pub time_us: u64,
    /// Exact prepared roster.
    pub entity_ids: Vec<String>,
    /// Whether each entity has an admissible observation at this sample.
    pub available: Vec<bool>,
    /// Flattened entity-major observations under the plan's component layout.
    pub values: Vec<f64>,
    /// One explicit innovation status per entity, in roster order.
    pub innovations: Vec<ScalarInnovation>,
    /// Hash of this complete snapshot excluding only this field.
    pub snapshot_digest: String,
}

impl Snapshot {
    fn content_digest(&self) -> Result<String, LocalError> {
        let mut value = serde_json::to_value(self).map_err(|_| LocalError(LocalCode::Wire))?;
        value
            .as_object_mut()
            .ok_or(LocalError(LocalCode::Wire))?
            .remove("snapshot_digest");
        local_digest("ncp.local.snapshot.v1", &value)
    }

    /// Validate numeric meaning, missingness, roster, time, and the complete digest.
    pub fn validate(&self, plan: &RunPlan) -> Result<(), LocalError> {
        self.validate_content(plan)?;
        if self.snapshot_digest != self.content_digest()? {
            return Err(LocalError(LocalCode::Binding));
        }
        Ok(())
    }

    fn validate_content(&self, plan: &RunPlan) -> Result<(), LocalError> {
        let n = plan.entity_ids.len();
        if self.schema != "ncp.local.snapshot.v1"
            || self.plan_digest != plan.digest()?
            || self.entity_ids != plan.entity_ids
            || self.time_us != plan.time_us(self.step)?
            || self.available.len() != n
            || self.values.len() != n * 6
            || self.innovations.len() != n
        {
            return Err(LocalError(LocalCode::InvalidInput));
        }
        for (index, innovation) in self.innovations.iter().enumerate() {
            let values = &self.values[index * 6..(index + 1) * 6];
            if values.iter().enumerate().any(|(component, v)| {
                !v.is_finite()
                    || v.abs() > if component < 3 { 100_000.0 } else { 100.0 }
                    || (!self.available[index] && *v != 0.0)
            }) || innovation.entity_id != self.entity_ids[index]
                || innovation.modality != "visual"
                || innovation.dof != 3
                || match innovation.status {
                    InnovationStatus::Observed => {
                        !self.available[index]
                            || !innovation
                                .nis
                                .is_some_and(|v| v.is_finite() && (0.0..=1e12).contains(&v))
                            || !innovation.source.as_ref().is_some_and(|source| {
                                !source.sensor_id.is_empty()
                                    && source.sensor_id.len() <= 128
                                    && source.fusion_track_id <= crate::local::MAX_SEQUENCE
                                    && source.fusion_sequence <= crate::local::MAX_SEQUENCE
                                    && source.measurement_time_us == self.time_us
                                    && source
                                        .residual_m
                                        .iter()
                                        .all(|v| v.is_finite() && v.abs() <= 200_000.0)
                                    && source
                                        .covariance_m2
                                        .iter()
                                        .flatten()
                                        .all(|v| v.is_finite() && v.abs() <= 1e12)
                            })
                    }
                    InnovationStatus::Birth => {
                        !self.available[index]
                            || innovation.nis.is_some()
                            || innovation.source.is_some()
                    }
                    InnovationStatus::Unavailable => {
                        innovation.nis.is_some() || innovation.source.is_some()
                    }
                }
            {
                return Err(LocalError(LocalCode::InvalidInput));
            }
        }
        Ok(())
    }

    /// Validate and seal an owner-produced snapshot before returning it.
    pub fn seal(&mut self, plan: &RunPlan) -> Result<(), LocalError> {
        self.validate_content(plan)?;
        self.snapshot_digest = self.content_digest()?;
        Ok(())
    }
}

/// Simulation command semantics. Neither value claims physical safe stopping.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionMode {
    /// Apply the proposed bounded acceleration.
    Active,
    /// Apply zero acceleration; existing velocity can continue.
    ZeroAcceleration,
}

/// Neural readout and proposal for exactly one source sample.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NeuralProposal {
    /// Exact schema `ncp.local.neural-result.v1`.
    pub schema: String,
    /// Complete joint plan identity.
    pub plan_digest: String,
    /// Next body step to which the proposal applies.
    pub step: u64,
    /// Exact source snapshot used by the encoder.
    pub source_snapshot_digest: String,
    /// Per-entity simulator action meanings, in the immutable roster order.
    pub selected_modes: Vec<ActionMode>,
    /// Entity-major acceleration components, in metres per second squared.
    pub values: Vec<f64>,
    /// Exact cumulative neural time after this advance, in microseconds.
    pub neural_time_us: u64,
    /// Inclusive readout completion watermark, in microseconds.
    pub completed_end_us: u64,
    /// Exclusive start of the newly completed readout interval, in microseconds.
    pub window_start_us: u64,
    /// Per-entity, per-axis positive/negative population counts, six per entity.
    pub spike_counts: Vec<u64>,
    /// Exact installed NEST model token used for every controller population.
    pub neural_model: String,
}

impl NeuralProposal {
    /// Validate source causality, bounded output, exact time, and inert missingness.
    pub fn validate(&self, plan: &RunPlan, source: &Snapshot) -> Result<(), LocalError> {
        source.validate(plan)?;
        let n = plan.entity_ids.len();
        if self.schema != "ncp.local.neural-result.v1"
            || self.plan_digest != plan.digest()?
            || self.step != source.step + 1
            || self.source_snapshot_digest != source.snapshot_digest
            || self.neural_time_us != plan.time_us(self.step)?
            || self.completed_end_us != self.neural_time_us - plan.readout_delay_us
            || self.window_start_us != source.time_us.saturating_sub(plan.readout_delay_us)
            || self.values.len() != n * 3
            || self.spike_counts.len() != n * 6
            || self.selected_modes.len() != n
            || self.spike_counts.iter().any(|count| *count > 1_000_000)
            || self.neural_model.is_empty()
            || self.neural_model.len() > 64
            || self.values.iter().any(|v| !v.is_finite() || v.abs() > 50.0)
            || self.selected_modes.iter().enumerate().any(|(i, mode)| {
                (*mode == ActionMode::ZeroAcceleration
                    && self.values[i * 3..(i + 1) * 3].iter().any(|v| *v != 0.0))
                    || (!source.available[i] && *mode != ActionMode::ZeroAcceleration)
            })
        {
            return Err(LocalError(LocalCode::InvalidInput));
        }
        Ok(())
    }
}

/// Neural owner input for one advance.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct NeuralStep {
    /// Complete immutable source snapshot.
    pub source_snapshot: Snapshot,
}

/// Body input containing the exact retained neural outcome routed by the supervisor.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BodyStep {
    /// Exact committed neural outcome. Its binding is checked against preparation.
    pub neural_response: LocalResponse,
}

/// Final application and subsequent observation, distinct from the neural proposal.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct BodyResult {
    /// Exact schema `ncp.local.body-result.v1`.
    pub schema: String,
    /// Complete immutable plan identity.
    pub plan_digest: String,
    /// Body step that was actually completed.
    pub step: u64,
    /// Source sample that caused this action.
    pub source_snapshot_digest: String,
    /// Exact retained neural response digest.
    pub neural_result_digest: String,
    /// Final per-entity action meanings, in roster order.
    pub selected_modes: Vec<ActionMode>,
    /// Neural proposal in the plan's acceleration layout.
    pub proposed_values: Vec<f64>,
    /// Actual bounded body acceleration in the same layout.
    pub applied_values: Vec<f64>,
    /// Per-entity actuator bounding indication.
    pub saturated: Vec<bool>,
    /// Next immutable sample from the actual body kernel.
    pub snapshot: Snapshot,
}

impl BodyResult {
    /// Validate complete body-result shape without claiming source authentication.
    pub fn validate(&self, plan: &RunPlan) -> Result<(), LocalError> {
        self.snapshot.validate(plan)?;
        let hash = |v: &str| {
            v.len() == 64
                && v.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        };
        let n = plan.entity_ids.len();
        if self.schema != "ncp.local.body-result.v1"
            || self.plan_digest != plan.digest()?
            || self.step == 0
            || self.step != self.snapshot.step
            || !hash(&self.source_snapshot_digest)
            || !hash(&self.neural_result_digest)
            || self.proposed_values.len() != n * 3
            || self.applied_values.len() != n * 3
            || self.saturated.len() != n
            || self.selected_modes.len() != n
            || self
                .proposed_values
                .iter()
                .chain(&self.applied_values)
                .any(|v| !v.is_finite() || v.abs() > 50.0)
            || self.selected_modes.iter().enumerate().any(|(i, mode)| {
                *mode == ActionMode::ZeroAcceleration
                    && self.proposed_values[i * 3..(i + 1) * 3]
                        .iter()
                        .chain(&self.applied_values[i * 3..(i + 1) * 3])
                        .any(|v| *v != 0.0)
            })
        {
            return Err(LocalError(LocalCode::InvalidInput));
        }
        Ok(())
    }
}
