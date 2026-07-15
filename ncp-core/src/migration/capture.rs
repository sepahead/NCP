//! Bounded validation of persisted wire-0.8 captures before migration work.
//!
//! This module does not translate records. It accepts only a complete, ordered
//! capture limited to capabilities, the lifecycle open exchange, sensor data, and
//! observations whose units, coordinate frames, session lineage, restart
//! boundaries, and simulation epistemic flags are explicit. Legacy records that
//! would need 1.0 authority or operation evidence are rejected because that
//! evidence cannot be recovered from the 0.8 payload.

use crate::bounded_json;
use crate::idempotency::sha256_hex;
use crate::{
    is_canonical_uuid_v4, valid_id_segment, BUILD_IDENTITY, CONTRACT_HASH, NCP_VERSION,
    NORMATIVE_CONTRACT_DIGEST, PACKAGE_VERSION,
};
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt;

/// Compact proto hash frozen by the immutable wire-0.8 release.
pub const LEGACY_WIRE_0_8_CONTRACT_HASH: &str = "d1b50a2d8a265276";

/// Exact input envelope understood by [`validate_wire_0_8_capture`].
pub const LEGACY_CAPTURE_SCHEMA: &str = "ncp.wire-0.8-capture.v1";

/// Exact validation-only report emitted for an accepted capture.
pub const CAPTURE_MIGRATION_REPORT_SCHEMA: &str = "ncp.capture-migration-validation.v1";

/// A capture is deliberately smaller than the universal JSON array ceiling.
/// Validation retains session and stream state for the complete capture and does
/// not evict it, because eviction would make replay look new.
pub const MAX_CAPTURE_RECORDS: usize = 4_096;

const MAX_CAPTURE_ROUTE_BYTES: usize = 512;
const MAX_CAPTURE_ID_BYTES: usize = 128;
const MAX_UNIT_BYTES: usize = 64;
const MAX_FRAME_ID_BYTES: usize = 128;

/// Stable reconstruction category for a rejected legacy capture.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureMigrationGap {
    Envelope,
    ContractIdentity,
    Unit,
    Frame,
    SessionLineage,
    Authority,
    EpistemicStatus,
    StreamContinuity,
}

impl CaptureMigrationGap {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Envelope => "envelope",
            Self::ContractIdentity => "contract_identity",
            Self::Unit => "unit",
            Self::Frame => "frame",
            Self::SessionLineage => "session_lineage",
            Self::Authority => "authority",
            Self::EpistemicStatus => "epistemic_status",
            Self::StreamContinuity => "stream_continuity",
        }
    }
}

impl fmt::Display for CaptureMigrationGap {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.as_str())
    }
}

/// Fail-closed validation error. Bounded-JSON failures retain their exact
/// `NCP-LIMIT-*` code; semantic ambiguity uses `NCP-GATEWAY-002`.
#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct CaptureMigrationError {
    pub code: &'static str,
    pub gap: CaptureMigrationGap,
    pub record_index: Option<u64>,
    pub detail: String,
}

impl CaptureMigrationError {
    fn semantic(
        gap: CaptureMigrationGap,
        record_index: Option<u64>,
        detail: impl Into<String>,
    ) -> Self {
        Self {
            code: "NCP-GATEWAY-002",
            gap,
            record_index,
            detail: detail.into(),
        }
    }

    fn bounded(error: bounded_json::BoundedJsonError) -> Self {
        Self {
            code: error.code.stable_code(),
            gap: CaptureMigrationGap::Envelope,
            record_index: None,
            detail: format!("legacy capture failed bounded JSON preflight: {error}"),
        }
    }
}

impl fmt::Display for CaptureMigrationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        if let Some(index) = self.record_index {
            write!(
                formatter,
                "{} [{}] at capture record {}: {}",
                self.code, self.gap, index, self.detail
            )
        } else {
            write!(formatter, "{} [{}]: {}", self.code, self.gap, self.detail)
        }
    }
}

impl std::error::Error for CaptureMigrationError {}

/// Five reconstruction axes covered by an accepted validation-only report.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CaptureReconstructability {
    pub units: bool,
    pub frames: bool,
    pub session_lineage: bool,
    /// True only when the capture has no post-open operation or action record that
    /// requires authority. The accepted lifecycle open exchange is state-mutating;
    /// this field is not reconstructed authority evidence and never authorizes a
    /// target action.
    pub authority_applicability: bool,
    pub epistemic_status: bool,
}

/// Deterministic report for an accepted capture. The negative claim fields are
/// explicit so this receipt cannot be mistaken for a translated or certified
/// native-1.0 artifact.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct CaptureMigrationReport {
    pub schema: String,
    pub validator: String,
    pub validator_package_version: String,
    pub validator_build_identity: String,
    pub validation_only: bool,
    pub source_wire: String,
    pub source_contract_hash: String,
    pub target_wire: String,
    pub target_contract_hash: String,
    pub target_normative_contract_digest: String,
    pub capture_sha256: String,
    pub records_validated: usize,
    pub sessions_validated: usize,
    pub streams_validated: usize,
    pub publisher_restarts_validated: usize,
    pub channel_values_validated: usize,
    pub frame_ids_validated: usize,
    pub epistemic_records_validated: usize,
    pub authority_requiring_records: usize,
    pub reconstructable: CaptureReconstructability,
    pub target_artifact_emitted: bool,
    pub security_upgraded: bool,
    pub authority_upgraded: bool,
    pub plant_safety_certified: bool,
    pub scientific_evidence_upgraded: bool,
    pub release_certified: bool,
}

#[derive(Clone, Debug)]
struct CaptureRecord<'a> {
    index: u64,
    route: &'a str,
    route_session_id: Option<&'a str>,
    publisher_id: &'a str,
    publisher_incarnation: &'a str,
    session_opened_index: Option<u64>,
    payload: &'a Map<String, Value>,
}

#[derive(Clone, Debug)]
struct ChannelDeclaration {
    unit: Option<String>,
    size: usize,
    required: bool,
}

#[derive(Clone, Debug, Default)]
struct CapabilityProjection {
    sensor: BTreeMap<String, ChannelDeclaration>,
}

#[derive(Clone, Debug)]
struct LiveSession {
    generation: String,
    opened_index: u64,
}

#[derive(Clone, Debug)]
struct PublisherState {
    active_incarnation: String,
    retired_incarnations: BTreeSet<String>,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct StreamKey {
    route: String,
    kind: String,
    generation: String,
    publisher_id: String,
}

#[derive(Clone, Debug)]
struct StreamState {
    publisher_incarnation: String,
    active_epoch: String,
    high_water: i64,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct CapturedPosition {
    session_id: String,
    generation: String,
    epoch: String,
    seq: i64,
}

#[derive(Clone, Debug)]
struct PendingOpen {
    capture_index: u64,
    network_ref: String,
    requested_seed: Option<i64>,
}

#[derive(Default)]
struct CaptureValidator {
    realm: Option<String>,
    capabilities: Option<CapabilityProjection>,
    pending_opens: BTreeMap<String, PendingOpen>,
    live_sessions: BTreeMap<String, LiveSession>,
    seen_generations: BTreeSet<(String, String)>,
    publishers: BTreeMap<String, PublisherState>,
    streams: BTreeMap<StreamKey, StreamState>,
    seen_stream_epochs: BTreeSet<String>,
    sensor_positions: BTreeMap<CapturedPosition, f64>,
    sessions_validated: usize,
    publisher_restarts_validated: usize,
    channel_values_validated: usize,
    frame_ids_validated: usize,
    epistemic_records_validated: usize,
}

/// Validate one complete persisted wire-0.8 capture without translating it.
///
/// The capture must be a bounded JSON object with exact top-level fields:
/// `schema`, `source_wire`, `source_contract_hash`, and `records`. Each record
/// must explicitly carry `capture_index`, `route`, `route_session_id`,
/// `publisher_id`, `publisher_incarnation`, `session_opened_index`, and
/// `payload`. Nullable metadata fields must be present as JSON `null`; omission is
/// rejected rather than defaulted.
pub fn validate_wire_0_8_capture(
    source: &[u8],
) -> Result<CaptureMigrationReport, CaptureMigrationError> {
    let value = bounded_json::parse_value(source).map_err(CaptureMigrationError::bounded)?;
    let root = object_at(&value, None, CaptureMigrationGap::Envelope, "capture")?;
    exact_fields(
        root,
        &["schema", "source_wire", "source_contract_hash", "records"],
        &["schema", "source_wire", "source_contract_hash", "records"],
        None,
        CaptureMigrationGap::Envelope,
        "capture",
    )?;
    require_string(
        root,
        "schema",
        None,
        CaptureMigrationGap::Envelope,
        "capture",
    )
    .and_then(|schema| {
        if schema == LEGACY_CAPTURE_SCHEMA {
            Ok(schema)
        } else {
            Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                None,
                format!("capture.schema must be {LEGACY_CAPTURE_SCHEMA:?}"),
            ))
        }
    })?;
    require_string(
        root,
        "source_wire",
        None,
        CaptureMigrationGap::ContractIdentity,
        "capture",
    )
    .and_then(|wire| {
        if wire == "0.8" {
            Ok(wire)
        } else {
            Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::ContractIdentity,
                None,
                "capture.source_wire must be exactly wire 0.8",
            ))
        }
    })?;
    require_string(
        root,
        "source_contract_hash",
        None,
        CaptureMigrationGap::ContractIdentity,
        "capture",
    )
    .and_then(|hash| {
        if hash == LEGACY_WIRE_0_8_CONTRACT_HASH {
            Ok(hash)
        } else {
            Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::ContractIdentity,
                None,
                format!("wire-0.8 capture contract hash must be {LEGACY_WIRE_0_8_CONTRACT_HASH:?}"),
            ))
        }
    })?;

    let records = root
        .get("records")
        .and_then(Value::as_array)
        .ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                None,
                "capture.records must be an array",
            )
        })?;
    if records.is_empty() || records.len() > MAX_CAPTURE_RECORDS {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Envelope,
            None,
            format!("capture.records length must be within 1..={MAX_CAPTURE_RECORDS}"),
        ));
    }

    let mut validator = CaptureValidator::default();
    for (offset, value) in records.iter().enumerate() {
        let expected_index = u64::try_from(offset + 1).map_err(|_| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                None,
                "capture index exceeds the validator integer domain",
            )
        })?;
        let record = parse_record(value, expected_index)?;
        validator.validate_record(&record)?;
    }
    validator.finish(source, records.len())
}

impl CaptureValidator {
    fn validate_record(&mut self, record: &CaptureRecord<'_>) -> Result<(), CaptureMigrationError> {
        self.validate_publisher_incarnation(record)?;
        let version = require_string(
            record.payload,
            "ncp_version",
            Some(record.index),
            CaptureMigrationGap::ContractIdentity,
            "payload",
        )?;
        if version != "0.8" {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::ContractIdentity,
                Some(record.index),
                "every captured payload must declare ncp_version exactly \"0.8\"",
            ));
        }
        let kind = require_string(
            record.payload,
            "kind",
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "payload",
        )?;
        match kind {
            "capabilities" => self.validate_capabilities(record),
            "open_session" => self.validate_open_session(record),
            "session_opened" => self.validate_session_opened(record),
            "sensor_frame" => self.validate_sensor_frame(record),
            "observation_frame" => self.validate_observation_frame(record),
            "control_status" => Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                Some(record.index),
                "wire-0.8 defines no transport key for control_status; its capture route cannot be reconstructed",
            )),
            "command_frame" | "step_request" | "run_request" | "close_session"
            | "session_closed" | "stimulus_frame" => Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Authority,
                Some(record.index),
                format!(
                    "wire-0.8 {kind:?} lacks the live authority/operation evidence needed for unambiguous 1.0 reconstruction"
                ),
            )),
            _ => Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                Some(record.index),
                format!("unsupported wire-0.8 capture kind {kind:?}"),
            )),
        }
    }

    fn validate_publisher_incarnation(
        &mut self,
        record: &CaptureRecord<'_>,
    ) -> Result<(), CaptureMigrationError> {
        if let Some(state) = self.publishers.get_mut(record.publisher_id) {
            if state.active_incarnation == record.publisher_incarnation {
                return Ok(());
            }
            if state
                .retired_incarnations
                .contains(record.publisher_incarnation)
            {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::StreamContinuity,
                    Some(record.index),
                    "a retired publisher process incarnation was replayed after restart",
                ));
            }
            state
                .retired_incarnations
                .insert(state.active_incarnation.clone());
            state.active_incarnation = record.publisher_incarnation.to_owned();
            self.publisher_restarts_validated += 1;
        } else {
            self.publishers.insert(
                record.publisher_id.to_owned(),
                PublisherState {
                    active_incarnation: record.publisher_incarnation.to_owned(),
                    retired_incarnations: BTreeSet::new(),
                },
            );
        }
        Ok(())
    }

    fn validate_capabilities(
        &mut self,
        record: &CaptureRecord<'_>,
    ) -> Result<(), CaptureMigrationError> {
        if self.capabilities.is_some()
            || !self.pending_opens.is_empty()
            || !self.live_sessions.is_empty()
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                "capabilities must appear exactly once before every session record",
            ));
        }
        require_unscoped_metadata(record)?;
        let realm = require_unscoped_route(record, "capabilities")?;
        self.bind_capture_realm(record, &realm)?;
        exact_fields(
            record.payload,
            &[
                "ncp_version",
                "kind",
                "controller_id",
                "role",
                "control_rate_hz",
                "sensor_channels",
                "command_channels",
                "codec_id",
                "safety",
            ],
            &[
                "ncp_version",
                "kind",
                "controller_id",
                "role",
                "control_rate_hz",
                "sensor_channels",
                "command_channels",
                "codec_id",
                "safety",
            ],
            Some(record.index),
            CaptureMigrationGap::Unit,
            "capabilities",
        )?;
        let controller_id = require_string(
            record.payload,
            "controller_id",
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "capabilities",
        )?;
        if controller_id.len() > MAX_CAPTURE_ID_BYTES || !valid_id_segment(controller_id) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                Some(record.index),
                "capabilities.controller_id must be a bounded concrete identifier",
            ));
        }
        let role = require_string(
            record.payload,
            "role",
            Some(record.index),
            CaptureMigrationGap::Authority,
            "capabilities",
        )?;
        if !matches!(role, "controller" | "plant") {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Authority,
                Some(record.index),
                format!("capabilities.role {role:?} has no closed wire-0.8 meaning"),
            ));
        }
        let control_rate_hz = finite_number(
            record.payload.get("control_rate_hz"),
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "capabilities.control_rate_hz",
        )?;
        if control_rate_hz <= 0.0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Envelope,
                Some(record.index),
                "capabilities.control_rate_hz must be positive",
            ));
        }
        if let Some(codec_id) = nullable_string(
            record.payload.get("codec_id"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            "capabilities.codec_id",
        )? {
            if codec_id.len() > MAX_CAPTURE_ID_BYTES || !valid_id_segment(codec_id) {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::Unit,
                    Some(record.index),
                    "capabilities.codec_id must be null or a bounded concrete identifier",
                ));
            }
        }
        let safety = object_at(
            required_value(
                record.payload,
                "safety",
                Some(record.index),
                CaptureMigrationGap::Envelope,
                "capabilities",
            )?,
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "capabilities.safety",
        )?;
        exact_fields(
            safety,
            &[
                "command_timeout_ms",
                "max_speed_mps",
                "max_tilt_rad",
                "geofence_radius_m",
            ],
            &[
                "command_timeout_ms",
                "max_speed_mps",
                "max_tilt_rad",
                "geofence_radius_m",
            ],
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "capabilities.safety",
        )?;
        let timeout = finite_number(
            safety.get("command_timeout_ms"),
            Some(record.index),
            CaptureMigrationGap::Authority,
            "capabilities.safety.command_timeout_ms",
        )?;
        if timeout <= 0.0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Authority,
                Some(record.index),
                "capabilities.safety.command_timeout_ms must be positive",
            ));
        }
        for field in ["max_speed_mps", "max_tilt_rad", "geofence_radius_m"] {
            if let Some(value) = safety.get(field) {
                if !value.is_null()
                    && finite_number(
                        Some(value),
                        Some(record.index),
                        CaptureMigrationGap::Authority,
                        &format!("capabilities.safety.{field}"),
                    )? < 0.0
                {
                    return Err(CaptureMigrationError::semantic(
                        CaptureMigrationGap::Authority,
                        Some(record.index),
                        format!("capabilities.safety.{field} must be non-negative or null"),
                    ));
                }
            }
        }
        let sensor = parse_channel_declarations(record, "sensor_channels")?;
        parse_channel_declarations(record, "command_channels")?;
        self.capabilities = Some(CapabilityProjection { sensor });
        Ok(())
    }

    fn validate_open_session(
        &mut self,
        record: &CaptureRecord<'_>,
    ) -> Result<(), CaptureMigrationError> {
        self.require_capabilities(record.index)?;
        exact_fields(
            record.payload,
            &[
                "ncp_version",
                "kind",
                "session_id",
                "network",
                "record",
                "stimulus",
                "sim",
                "bindings",
                "contract_hash",
            ],
            &[
                "ncp_version",
                "kind",
                "session_id",
                "network",
                "record",
                "stimulus",
                "sim",
                "bindings",
                "contract_hash",
            ],
            Some(record.index),
            CaptureMigrationGap::SessionLineage,
            "open_session",
        )?;
        let session_id = payload_session_id(record)?;
        require_route_session_metadata(record, session_id, false)?;
        let realm = require_rpc_route(record, "open_session")?;
        self.require_capture_realm(record, &realm)?;
        require_legacy_contract_hash(record, "open_session")?;
        let (network_ref, requested_seed) = validate_open_payload(record)?;
        if self.pending_opens.contains_key(session_id) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                format!("session {session_id:?} already has an unresolved open request"),
            ));
        }
        self.pending_opens.insert(
            session_id.to_owned(),
            PendingOpen {
                capture_index: record.index,
                network_ref,
                requested_seed,
            },
        );
        Ok(())
    }

    fn validate_session_opened(
        &mut self,
        record: &CaptureRecord<'_>,
    ) -> Result<(), CaptureMigrationError> {
        self.require_capabilities(record.index)?;
        exact_fields(
            record.payload,
            &[
                "ncp_version",
                "kind",
                "session_id",
                "ok",
                "backend",
                "resolved",
                "provenance",
                "error",
                "contract_hash",
                "session",
            ],
            &[
                "ncp_version",
                "kind",
                "session_id",
                "ok",
                "backend",
                "resolved",
                "provenance",
                "error",
                "contract_hash",
                "session",
            ],
            Some(record.index),
            CaptureMigrationGap::SessionLineage,
            "session_opened",
        )?;
        let session_id = payload_session_id(record)?;
        require_route_session_metadata(record, session_id, false)?;
        let realm = require_rpc_route(record, "open_session")?;
        self.require_capture_realm(record, &realm)?;
        require_legacy_contract_hash(record, "session_opened")?;
        if record.payload.get("ok").and_then(Value::as_bool) != Some(true) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                "only an explicit successful session_opened establishes reconstructable lineage",
            ));
        }
        validate_safe_integer_map(
            record.payload.get("resolved"),
            Some(record.index),
            CaptureMigrationGap::SessionLineage,
            "session_opened.resolved",
            true,
        )?;
        let pending_open = self.pending_opens.remove(session_id).ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                format!(
                    "session_opened for {session_id:?} has no preceding unresolved open_session"
                ),
            )
        })?;
        let generation = require_generation(record.payload, record.index)?;
        if !self
            .seen_generations
            .insert((session_id.to_owned(), generation.to_owned()))
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                "a retired session generation was reopened or replayed",
            ));
        }
        validate_session_provenance(
            record,
            &pending_open.network_ref,
            pending_open.requested_seed,
        )?;
        self.epistemic_records_validated += 1;
        self.sessions_validated += 1;
        self.live_sessions.insert(
            session_id.to_owned(),
            LiveSession {
                generation: generation.to_owned(),
                opened_index: record.index,
            },
        );
        Ok(())
    }

    fn validate_sensor_frame(
        &mut self,
        record: &CaptureRecord<'_>,
    ) -> Result<(), CaptureMigrationError> {
        exact_fields(
            record.payload,
            &[
                "ncp_version",
                "kind",
                "session_id",
                "session",
                "stream",
                "t",
                "channels",
            ],
            &[
                "ncp_version",
                "kind",
                "session_id",
                "session",
                "stream",
                "t",
                "frame_id",
                "channels",
            ],
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "sensor_frame",
        )?;
        let (session_id, generation) = self.validate_live_session(record, "sensor")?;
        let sensor_t = finite_number(
            record.payload.get("t"),
            Some(record.index),
            CaptureMigrationGap::StreamContinuity,
            "sensor_frame.t",
        )?;
        validate_frame_id(record)?;
        self.frame_ids_validated += 1;
        let validated_values = validate_channel_values(
            record,
            "channels",
            &self.require_capabilities(record.index)?.sensor,
            "sensor_frame.channels",
        )?;
        self.channel_values_validated += validated_values;
        let (epoch, seq) =
            self.validate_stream(record, &session_id, &generation, "sensor_frame")?;
        if self
            .sensor_positions
            .insert(
                CapturedPosition {
                    session_id,
                    generation,
                    epoch,
                    seq,
                },
                sensor_t,
            )
            .is_some()
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                "captured sensor position is ambiguous or duplicated",
            ));
        }
        Ok(())
    }

    fn validate_observation_frame(
        &mut self,
        record: &CaptureRecord<'_>,
    ) -> Result<(), CaptureMigrationError> {
        exact_fields(
            record.payload,
            &[
                "ncp_version",
                "kind",
                "session_id",
                "session",
                "stream",
                "t",
                "sim_time_ms",
                "records",
                "calibrated_posterior",
                "is_simulation_output",
            ],
            &[
                "ncp_version",
                "kind",
                "session_id",
                "session",
                "stream",
                "source",
                "source_t",
                "t",
                "sim_time_ms",
                "records",
                "calibrated_posterior",
                "is_simulation_output",
            ],
            Some(record.index),
            CaptureMigrationGap::Envelope,
            "observation_frame",
        )?;
        let (session_id, generation) = self.validate_live_session(record, "observation")?;
        finite_number(
            record.payload.get("t"),
            Some(record.index),
            CaptureMigrationGap::StreamContinuity,
            "observation_frame.t",
        )?;
        finite_number(
            record.payload.get("sim_time_ms"),
            Some(record.index),
            CaptureMigrationGap::EpistemicStatus,
            "observation_frame.sim_time_ms",
        )?;
        let source_t = finite_number(
            record.payload.get("source_t"),
            Some(record.index),
            CaptureMigrationGap::SessionLineage,
            "observation_frame.source_t",
        )?;
        validate_epistemic_flags(record.payload, record.index, "observation_frame")?;
        self.epistemic_records_validated += 1;
        self.channel_values_validated += validate_observation_units(record)?;
        validate_observation_source(
            record,
            &session_id,
            &generation,
            source_t,
            &self.sensor_positions,
        )?;
        self.validate_stream(record, &session_id, &generation, "observation_frame")?;
        Ok(())
    }

    fn validate_live_session(
        &self,
        record: &CaptureRecord<'_>,
        route_plane: &str,
    ) -> Result<(String, String), CaptureMigrationError> {
        self.require_capabilities(record.index)?;
        let session_id = payload_session_id(record)?;
        let generation = require_generation(record.payload, record.index)?;
        require_route_session_metadata(record, session_id, true)?;
        let realm = require_route_plane(record, session_id, route_plane)?;
        self.require_capture_realm(record, &realm)?;
        let live = self.live_sessions.get(session_id).ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                format!("record names unopened session {session_id:?}"),
            )
        })?;
        if live.generation != generation || record.session_opened_index != Some(live.opened_index) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                format!(
                    "record does not bind the exact live ({session_id:?}, {generation:?}) opening at capture index {}",
                    live.opened_index
                ),
            ));
        }
        Ok((session_id.to_owned(), generation.to_owned()))
    }

    fn validate_stream(
        &mut self,
        record: &CaptureRecord<'_>,
        _session_id: &str,
        generation: &str,
        kind: &str,
    ) -> Result<(String, i64), CaptureMigrationError> {
        let stream = record.payload.get("stream").ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::StreamContinuity,
                Some(record.index),
                format!("{kind}.stream is missing"),
            )
        })?;
        let stream = object_at(
            stream,
            Some(record.index),
            CaptureMigrationGap::StreamContinuity,
            &format!("{kind}.stream"),
        )?;
        exact_fields(
            stream,
            &["epoch", "seq"],
            &["epoch", "seq"],
            Some(record.index),
            CaptureMigrationGap::StreamContinuity,
            &format!("{kind}.stream"),
        )?;
        let epoch = require_string(
            stream,
            "epoch",
            Some(record.index),
            CaptureMigrationGap::StreamContinuity,
            &format!("{kind}.stream"),
        )?;
        if !is_canonical_uuid_v4(epoch) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::StreamContinuity,
                Some(record.index),
                format!("{kind}.stream.epoch must be a canonical lowercase UUIDv4"),
            ));
        }
        let seq = positive_safe_integer(
            stream.get("seq"),
            Some(record.index),
            CaptureMigrationGap::StreamContinuity,
            &format!("{kind}.stream.seq"),
        )?;
        let key = StreamKey {
            route: record.route.to_owned(),
            kind: kind.to_owned(),
            generation: generation.to_owned(),
            publisher_id: record.publisher_id.to_owned(),
        };

        if let Some(state) = self.streams.get_mut(&key) {
            if state.publisher_incarnation == record.publisher_incarnation {
                if state.active_epoch != epoch {
                    return Err(CaptureMigrationError::semantic(
                        CaptureMigrationGap::StreamContinuity,
                        Some(record.index),
                        "a publisher changed stream epoch without a process-incarnation restart",
                    ));
                }
                let expected = state.high_water.checked_add(1).ok_or_else(|| {
                    CaptureMigrationError::semantic(
                        CaptureMigrationGap::StreamContinuity,
                        Some(record.index),
                        "stream high-water exhausted the exact JSON integer range",
                    )
                })?;
                if seq != expected {
                    return Err(CaptureMigrationError::semantic(
                        CaptureMigrationGap::StreamContinuity,
                        Some(record.index),
                        format!(
                            "stream sequence must advance contiguously from high-water {} to {}; got {seq}",
                            state.high_water, expected
                        ),
                    ));
                }
                state.high_water = seq;
            } else {
                if state.active_epoch == epoch {
                    return Err(CaptureMigrationError::semantic(
                        CaptureMigrationGap::StreamContinuity,
                        Some(record.index),
                        "publisher restart reused the stream's prior epoch",
                    ));
                }
                if !self.seen_stream_epochs.insert(epoch.to_owned()) {
                    return Err(CaptureMigrationError::semantic(
                        CaptureMigrationGap::StreamContinuity,
                        Some(record.index),
                        "publisher restart reused an epoch already seen in another stream or session",
                    ));
                }
                if seq != 1 {
                    return Err(CaptureMigrationError::semantic(
                        CaptureMigrationGap::StreamContinuity,
                        Some(record.index),
                        "the first captured frame after publisher restart must use seq 1",
                    ));
                }
                state.publisher_incarnation = record.publisher_incarnation.to_owned();
                state.active_epoch = epoch.to_owned();
                state.high_water = 1;
            }
        } else {
            if seq != 1 {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::StreamContinuity,
                    Some(record.index),
                    "the first captured position for a stream must be seq 1; a partial prefix cannot reconstruct high-water state",
                ));
            }
            if self.streams.len() >= crate::MAX_STREAM_FENCE_ENTRIES {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::StreamContinuity,
                    Some(record.index),
                    "capture exceeds the non-evicting stream-state capacity",
                ));
            }
            if !self.seen_stream_epochs.insert(epoch.to_owned()) {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::StreamContinuity,
                    Some(record.index),
                    "publisher reused an epoch already seen in another stream or session",
                ));
            }
            self.streams.insert(
                key,
                StreamState {
                    publisher_incarnation: record.publisher_incarnation.to_owned(),
                    active_epoch: epoch.to_owned(),
                    high_water: seq,
                },
            );
        }
        Ok((epoch.to_owned(), seq))
    }

    fn require_capabilities(
        &self,
        record_index: u64,
    ) -> Result<&CapabilityProjection, CaptureMigrationError> {
        self.capabilities.as_ref().ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record_index),
                "capture has no preceding explicit capabilities declaration",
            )
        })
    }

    fn bind_capture_realm(
        &mut self,
        record: &CaptureRecord<'_>,
        realm: &str,
    ) -> Result<(), CaptureMigrationError> {
        if let Some(expected) = &self.realm {
            if expected != realm {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::SessionLineage,
                    Some(record.index),
                    format!("capture route realm {realm:?} does not match {expected:?}"),
                ));
            }
        } else {
            self.realm = Some(realm.to_owned());
        }
        Ok(())
    }

    fn require_capture_realm(
        &self,
        record: &CaptureRecord<'_>,
        realm: &str,
    ) -> Result<(), CaptureMigrationError> {
        if self.realm.as_deref() == Some(realm) {
            Ok(())
        } else {
            Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                format!(
                    "capture route realm {realm:?} does not match the capabilities/open lineage"
                ),
            ))
        }
    }

    fn finish(
        self,
        source: &[u8],
        record_count: usize,
    ) -> Result<CaptureMigrationReport, CaptureMigrationError> {
        if self.capabilities.is_none() {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                None,
                "capture contains no capabilities declaration",
            ));
        }
        if let Some((session_id, pending)) = self.pending_opens.first_key_value() {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(pending.capture_index),
                format!("session {session_id:?} open outcome is missing from the capture"),
            ));
        }
        if self.sessions_validated == 0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                None,
                "capture contains no complete successful session lineage",
            ));
        }
        if self.streams.is_empty() {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::StreamContinuity,
                None,
                "capture contains no complete stream from seq 1",
            ));
        }
        if self.channel_values_validated == 0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                None,
                "capture contains no channel value with explicit unit evidence",
            ));
        }
        if self.frame_ids_validated == 0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Frame,
                None,
                "capture contains no spatial frame with explicit frame_id evidence",
            ));
        }
        if self.epistemic_records_validated == 0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::EpistemicStatus,
                None,
                "capture contains no explicit simulation epistemic discriminator",
            ));
        }

        Ok(CaptureMigrationReport {
            schema: CAPTURE_MIGRATION_REPORT_SCHEMA.into(),
            validator: "ncp-core::validate_wire_0_8_capture".into(),
            validator_package_version: PACKAGE_VERSION.into(),
            validator_build_identity: BUILD_IDENTITY.into(),
            validation_only: true,
            source_wire: "0.8".into(),
            source_contract_hash: LEGACY_WIRE_0_8_CONTRACT_HASH.into(),
            target_wire: NCP_VERSION.into(),
            target_contract_hash: CONTRACT_HASH.into(),
            target_normative_contract_digest: NORMATIVE_CONTRACT_DIGEST.into(),
            capture_sha256: sha256_hex(source),
            records_validated: record_count,
            sessions_validated: self.sessions_validated,
            streams_validated: self.streams.len(),
            publisher_restarts_validated: self.publisher_restarts_validated,
            channel_values_validated: self.channel_values_validated,
            frame_ids_validated: self.frame_ids_validated,
            epistemic_records_validated: self.epistemic_records_validated,
            authority_requiring_records: 0,
            reconstructable: CaptureReconstructability {
                units: true,
                frames: true,
                session_lineage: true,
                authority_applicability: true,
                epistemic_status: true,
            },
            target_artifact_emitted: false,
            security_upgraded: false,
            authority_upgraded: false,
            plant_safety_certified: false,
            scientific_evidence_upgraded: false,
            release_certified: false,
        })
    }
}

fn parse_record(
    value: &Value,
    expected_index: u64,
) -> Result<CaptureRecord<'_>, CaptureMigrationError> {
    let object = object_at(
        value,
        Some(expected_index),
        CaptureMigrationGap::Envelope,
        "capture record",
    )?;
    exact_fields(
        object,
        &[
            "capture_index",
            "route",
            "route_session_id",
            "publisher_id",
            "publisher_incarnation",
            "session_opened_index",
            "payload",
        ],
        &[
            "capture_index",
            "route",
            "route_session_id",
            "publisher_id",
            "publisher_incarnation",
            "session_opened_index",
            "payload",
        ],
        Some(expected_index),
        CaptureMigrationGap::Envelope,
        "capture record",
    )?;
    let index = positive_safe_u64(
        object.get("capture_index"),
        Some(expected_index),
        CaptureMigrationGap::Envelope,
        "capture_index",
    )?;
    if index != expected_index {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Envelope,
            Some(index),
            format!("capture_index must be contiguous array order {expected_index}; got {index}"),
        ));
    }
    let route = require_string(
        object,
        "route",
        Some(index),
        CaptureMigrationGap::Envelope,
        "capture record",
    )?;
    if route.len() > MAX_CAPTURE_ROUTE_BYTES || !crate::keys::valid_realm(route) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Envelope,
            Some(index),
            "capture route must be a bounded concrete key without wildcards",
        ));
    }
    let route_session_id = nullable_string(
        object.get("route_session_id"),
        Some(index),
        CaptureMigrationGap::SessionLineage,
        "route_session_id",
    )?;
    let publisher_id = require_string(
        object,
        "publisher_id",
        Some(index),
        CaptureMigrationGap::Envelope,
        "capture record",
    )?;
    if publisher_id.len() > MAX_CAPTURE_ID_BYTES || !valid_id_segment(publisher_id) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Envelope,
            Some(index),
            "publisher_id must be a bounded concrete identifier",
        ));
    }
    let publisher_incarnation = require_string(
        object,
        "publisher_incarnation",
        Some(index),
        CaptureMigrationGap::StreamContinuity,
        "capture record",
    )?;
    if !is_canonical_uuid_v4(publisher_incarnation) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::StreamContinuity,
            Some(index),
            "publisher_incarnation must be a canonical lowercase UUIDv4",
        ));
    }
    let session_opened_index = nullable_positive_u64(
        object.get("session_opened_index"),
        Some(index),
        CaptureMigrationGap::SessionLineage,
        "session_opened_index",
    )?;
    let payload = object_at(
        required_value(
            object,
            "payload",
            Some(index),
            CaptureMigrationGap::Envelope,
            "capture record",
        )?,
        Some(index),
        CaptureMigrationGap::Envelope,
        "capture record payload",
    )?;
    Ok(CaptureRecord {
        index,
        route,
        route_session_id,
        publisher_id,
        publisher_incarnation,
        session_opened_index,
        payload,
    })
}

fn parse_channel_declarations(
    record: &CaptureRecord<'_>,
    field: &str,
) -> Result<BTreeMap<String, ChannelDeclaration>, CaptureMigrationError> {
    let channels = record
        .payload
        .get(field)
        .and_then(Value::as_array)
        .ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("capabilities.{field} must be an array"),
            )
        })?;
    if channels.len() > crate::MAX_CHANNELS {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Unit,
            Some(record.index),
            format!("capabilities.{field} exceeds the channel limit"),
        ));
    }
    let mut result = BTreeMap::new();
    for (offset, value) in channels.iter().enumerate() {
        let path = format!("capabilities.{field}[{offset}]");
        let channel = object_at(value, Some(record.index), CaptureMigrationGap::Unit, &path)?;
        exact_fields(
            channel,
            &["name", "kind", "unit", "size", "optional", "description"],
            &["name", "kind", "unit", "size", "optional", "description"],
            Some(record.index),
            CaptureMigrationGap::Unit,
            &path,
        )?;
        let name = require_string(
            channel,
            "name",
            Some(record.index),
            CaptureMigrationGap::Unit,
            &path,
        )?;
        if name.len() > MAX_CAPTURE_ID_BYTES || !valid_id_segment(name) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path}.name is not a bounded concrete identifier"),
            ));
        }
        let kind = require_string(
            channel,
            "kind",
            Some(record.index),
            CaptureMigrationGap::Unit,
            &path,
        )?;
        let unit = parse_unit(
            channel.get("unit"),
            Some(record.index),
            &format!("{path}.unit"),
        )?;
        let size = usize::try_from(positive_safe_u64(
            channel.get("size"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            &format!("{path}.size"),
        )?)
        .map_err(|_| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path}.size exceeds this implementation's address space"),
            )
        })?;
        let expected_size = match kind {
            "scalar" => Some(1),
            "vec3" => Some(3),
            "quat" => Some(4),
            "array" => None,
            _ => {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::Unit,
                    Some(record.index),
                    format!("{path}.kind {kind:?} cannot be reconstructed"),
                ))
            }
        };
        if expected_size.is_some_and(|expected| expected != size) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path}.size {size} contradicts channel kind {kind:?}"),
            ));
        }
        let optional = channel
            .get("optional")
            .and_then(Value::as_bool)
            .ok_or_else(|| {
                CaptureMigrationError::semantic(
                    CaptureMigrationGap::Unit,
                    Some(record.index),
                    format!("{path}.optional must be an explicit boolean"),
                )
            })?;
        validate_nullable_clean_string(
            channel.get("description"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            &format!("{path}.description"),
        )?;
        if result
            .insert(
                name.to_owned(),
                ChannelDeclaration {
                    unit,
                    size,
                    required: !optional,
                },
            )
            .is_some()
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("capabilities.{field} contains duplicate channel {name:?}"),
            ));
        }
    }
    Ok(result)
}

fn validate_channel_values(
    record: &CaptureRecord<'_>,
    field: &str,
    declarations: &BTreeMap<String, ChannelDeclaration>,
    path: &str,
) -> Result<usize, CaptureMigrationError> {
    let channels = record
        .payload
        .get(field)
        .and_then(Value::as_object)
        .ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path} must be an object"),
            )
        })?;
    if channels.len() > crate::MAX_CHANNELS {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Unit,
            Some(record.index),
            format!("{path} exceeds the channel limit"),
        ));
    }
    for (name, declaration) in declarations {
        if declaration.required && !channels.contains_key(name) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path} omits required declared channel {name:?}"),
            ));
        }
    }
    let mut scalar_count = 0usize;
    for (name, value) in channels {
        let declaration = declarations.get(name).ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path} contains undeclared channel {name:?}"),
            )
        })?;
        let channel_path = format!("{path}.{name}");
        let channel = object_at(
            value,
            Some(record.index),
            CaptureMigrationGap::Unit,
            &channel_path,
        )?;
        exact_fields(
            channel,
            &["data", "unit"],
            &["data", "unit"],
            Some(record.index),
            CaptureMigrationGap::Unit,
            &channel_path,
        )?;
        let data = channel
            .get("data")
            .and_then(Value::as_array)
            .ok_or_else(|| {
                CaptureMigrationError::semantic(
                    CaptureMigrationGap::Unit,
                    Some(record.index),
                    format!("{channel_path}.data must be an array"),
                )
            })?;
        if data.len() != declaration.size || data.iter().any(|sample| sample.as_f64().is_none()) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!(
                    "{channel_path}.data must contain exactly {} finite numeric values",
                    declaration.size
                ),
            ));
        }
        scalar_count = scalar_count.checked_add(data.len()).ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path} scalar count exceeds this implementation's address space"),
            )
        })?;
        let unit = parse_unit(
            channel.get("unit"),
            Some(record.index),
            &format!("{channel_path}.unit"),
        )?;
        if unit != declaration.unit {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!(
                    "{channel_path}.unit {unit:?} contradicts declared unit {:?}",
                    declaration.unit
                ),
            ));
        }
    }
    Ok(scalar_count)
}

fn validate_observation_units(record: &CaptureRecord<'_>) -> Result<usize, CaptureMigrationError> {
    let records = record
        .payload
        .get("records")
        .and_then(Value::as_object)
        .ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                "observation_frame.records must be an object",
            )
        })?;
    let mut count = 0;
    for (name, value) in records {
        if name.is_empty()
            || name.len() > MAX_CAPTURE_ID_BYTES
            || name.chars().any(char::is_control)
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                "observation record-series names must be bounded, non-empty, and control-free",
            ));
        }
        let path = format!("observation_frame.records.{name}");
        let observation = object_at(value, Some(record.index), CaptureMigrationGap::Unit, &path)?;
        exact_fields(
            observation,
            &[
                "port",
                "target",
                "observable",
                "recordable",
                "times",
                "values",
                "senders",
                "unit",
            ],
            &[
                "port",
                "target",
                "observable",
                "recordable",
                "times",
                "values",
                "senders",
                "unit",
            ],
            Some(record.index),
            CaptureMigrationGap::Unit,
            &path,
        )?;
        for field in ["port", "target", "observable"] {
            let value = require_string(
                observation,
                field,
                Some(record.index),
                CaptureMigrationGap::Unit,
                &path,
            )?;
            if value.is_empty()
                || value.len() > MAX_CAPTURE_ID_BYTES
                || value.chars().any(char::is_control)
            {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::Unit,
                    Some(record.index),
                    format!("{path}.{field} must be bounded, non-empty, and control-free"),
                ));
            }
        }
        let observable = require_string(
            observation,
            "observable",
            Some(record.index),
            CaptureMigrationGap::Unit,
            &path,
        )?;
        if !matches!(
            observable,
            "spikes" | "V_m" | "rate" | "weight" | "binary_state"
        ) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path}.observable {observable:?} has no closed wire-0.8 meaning"),
            ));
        }
        if let Some(recordable) = nullable_string(
            observation.get("recordable"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            &format!("{path}.recordable"),
        )? {
            if recordable.is_empty()
                || recordable.len() > MAX_CAPTURE_ID_BYTES
                || recordable.chars().any(char::is_control)
            {
                return Err(CaptureMigrationError::semantic(
                    CaptureMigrationGap::Unit,
                    Some(record.index),
                    format!("{path}.recordable must be null or a bounded non-empty string"),
                ));
            }
        }
        let times = finite_number_array(
            observation.get("times"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            &format!("{path}.times"),
        )?;
        let values = finite_number_array(
            observation.get("values"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            &format!("{path}.values"),
        )?;
        let senders = safe_integer_array(
            observation.get("senders"),
            Some(record.index),
            CaptureMigrationGap::Unit,
            &format!("{path}.senders"),
        )?;
        if !values.is_empty() && !senders.is_empty() {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path} cannot mix analog values and spike senders"),
            ));
        }
        let payload_len = values.len().max(senders.len());
        if times.len() != payload_len {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                Some(record.index),
                format!("{path} parallel times/value/sender arrays disagree"),
            ));
        }
        parse_unit(
            observation.get("unit"),
            Some(record.index),
            &format!("{path}.unit"),
        )?;
        count += payload_len;
    }
    Ok(count)
}

fn validate_observation_source(
    record: &CaptureRecord<'_>,
    session_id: &str,
    generation: &str,
    source_t: f64,
    sensor_positions: &BTreeMap<CapturedPosition, f64>,
) -> Result<(), CaptureMigrationError> {
    let source = record.payload.get("source");
    let route_is_plane = route_binds_plane(record.route, session_id, "observation");
    if source.is_none_or(Value::is_null) {
        if route_is_plane {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                "observation-plane capture requires an explicit driving sensor source",
            ));
        }
        return Ok(());
    }
    let source = object_at(
        source.ok_or_else(|| {
            CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                Some(record.index),
                "observation source is missing",
            )
        })?,
        Some(record.index),
        CaptureMigrationGap::SessionLineage,
        "observation_frame.source",
    )?;
    exact_fields(
        source,
        &["epoch", "seq"],
        &["epoch", "seq"],
        Some(record.index),
        CaptureMigrationGap::SessionLineage,
        "observation_frame.source",
    )?;
    let epoch = require_string(
        source,
        "epoch",
        Some(record.index),
        CaptureMigrationGap::SessionLineage,
        "observation_frame.source",
    )?;
    let seq = positive_safe_integer(
        source.get("seq"),
        Some(record.index),
        CaptureMigrationGap::SessionLineage,
        "observation_frame.source.seq",
    )?;
    let captured_t = sensor_positions.get(&CapturedPosition {
        session_id: session_id.to_owned(),
        generation: generation.to_owned(),
        epoch: epoch.to_owned(),
        seq,
    });
    let Some(captured_t) = captured_t else {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "observation source does not identify a preceding captured sensor position in the same session generation",
        ));
    };
    if source_t != *captured_t {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            format!(
                "observation_frame.source_t {source_t} does not equal the cited sensor timestamp {captured_t}"
            ),
        ));
    }
    Ok(())
}

fn validate_frame_id(record: &CaptureRecord<'_>) -> Result<(), CaptureMigrationError> {
    let frame = require_string(
        record.payload,
        "frame_id",
        Some(record.index),
        CaptureMigrationGap::Frame,
        "sensor_frame",
    )?;
    if frame.is_empty() || frame.len() > MAX_FRAME_ID_BYTES || frame.chars().any(char::is_control) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Frame,
            Some(record.index),
            "sensor_frame.frame_id must be explicit, non-empty, bounded, and control-free",
        ));
    }
    Ok(())
}

fn validate_open_payload(
    record: &CaptureRecord<'_>,
) -> Result<(String, Option<i64>), CaptureMigrationError> {
    let index = Some(record.index);
    let network = object_at(
        required_value(
            record.payload,
            "network",
            index,
            CaptureMigrationGap::SessionLineage,
            "open_session",
        )?,
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network",
    )?;
    exact_fields(
        network,
        &["kind", "ref", "model_name", "population_sizes", "params"],
        &["kind", "ref", "model_name", "population_sizes", "params"],
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network",
    )?;
    let network_kind = clean_string(
        network,
        "kind",
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network",
    )?;
    if !matches!(network_kind, "handle" | "builtin" | "model_id" | "spec") {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            index,
            format!("open_session.network.kind {network_kind:?} has no closed wire-0.8 meaning"),
        ));
    }
    let network_ref = clean_string(
        network,
        "ref",
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network",
    )?;
    validate_nullable_clean_string(
        network.get("model_name"),
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network.model_name",
    )?;
    validate_safe_integer_map(
        network.get("population_sizes"),
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network.population_sizes",
        true,
    )?;
    validate_finite_number_map(
        network.get("params"),
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.network.params",
    )?;

    let record_spec = object_at(
        required_value(
            record.payload,
            "record",
            index,
            CaptureMigrationGap::Unit,
            "open_session",
        )?,
        index,
        CaptureMigrationGap::Unit,
        "open_session.record",
    )?;
    exact_fields(
        record_spec,
        &["targets"],
        &["targets"],
        index,
        CaptureMigrationGap::Unit,
        "open_session.record",
    )?;
    let record_targets = bounded_array(
        record_spec.get("targets"),
        index,
        CaptureMigrationGap::Unit,
        "open_session.record.targets",
    )?;
    for (offset, value) in record_targets.iter().enumerate() {
        let path = format!("open_session.record.targets[{offset}]");
        let target = object_at(value, index, CaptureMigrationGap::Unit, &path)?;
        exact_fields(
            target,
            &[
                "port",
                "target",
                "observable",
                "ids",
                "cadence_ms",
                "recordables",
            ],
            &[
                "port",
                "target",
                "observable",
                "ids",
                "cadence_ms",
                "recordables",
            ],
            index,
            CaptureMigrationGap::Unit,
            &path,
        )?;
        clean_string(target, "port", index, CaptureMigrationGap::Unit, &path)?;
        clean_string(target, "target", index, CaptureMigrationGap::Unit, &path)?;
        let observable = clean_string(
            target,
            "observable",
            index,
            CaptureMigrationGap::Unit,
            &path,
        )?;
        if !matches!(
            observable,
            "spikes" | "V_m" | "rate" | "weight" | "binary_state"
        ) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                index,
                format!("{path}.observable {observable:?} has no closed wire-0.8 meaning"),
            ));
        }
        safe_integer_array(
            target.get("ids"),
            index,
            CaptureMigrationGap::Unit,
            &format!("{path}.ids"),
        )?;
        if finite_number(
            target.get("cadence_ms"),
            index,
            CaptureMigrationGap::Unit,
            &format!("{path}.cadence_ms"),
        )? <= 0.0
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                index,
                format!("{path}.cadence_ms must be positive"),
            ));
        }
        validate_clean_string_array(
            target.get("recordables"),
            index,
            CaptureMigrationGap::Unit,
            &format!("{path}.recordables"),
        )?;
    }

    let stimulus_spec = object_at(
        required_value(
            record.payload,
            "stimulus",
            index,
            CaptureMigrationGap::Unit,
            "open_session",
        )?,
        index,
        CaptureMigrationGap::Unit,
        "open_session.stimulus",
    )?;
    exact_fields(
        stimulus_spec,
        &["targets"],
        &["targets"],
        index,
        CaptureMigrationGap::Unit,
        "open_session.stimulus",
    )?;
    let stimulus_targets = bounded_array(
        stimulus_spec.get("targets"),
        index,
        CaptureMigrationGap::Unit,
        "open_session.stimulus.targets",
    )?;
    for (offset, value) in stimulus_targets.iter().enumerate() {
        let path = format!("open_session.stimulus.targets[{offset}]");
        let target = object_at(value, index, CaptureMigrationGap::Unit, &path)?;
        exact_fields(
            target,
            &["port", "target", "kind", "ids", "params"],
            &["port", "target", "kind", "ids", "params"],
            index,
            CaptureMigrationGap::Unit,
            &path,
        )?;
        clean_string(target, "port", index, CaptureMigrationGap::Unit, &path)?;
        clean_string(target, "target", index, CaptureMigrationGap::Unit, &path)?;
        let kind = clean_string(target, "kind", index, CaptureMigrationGap::Unit, &path)?;
        if !matches!(
            kind,
            "current_pA" | "rate_hz" | "spike_times" | "weight_set" | "rate_inject"
        ) {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::Unit,
                index,
                format!("{path}.kind {kind:?} has no closed wire-0.8 meaning"),
            ));
        }
        safe_integer_array(
            target.get("ids"),
            index,
            CaptureMigrationGap::Unit,
            &format!("{path}.ids"),
        )?;
        validate_finite_number_map(
            target.get("params"),
            index,
            CaptureMigrationGap::Unit,
            &format!("{path}.params"),
        )?;
    }

    let sim = object_at(
        required_value(
            record.payload,
            "sim",
            index,
            CaptureMigrationGap::EpistemicStatus,
            "open_session",
        )?,
        index,
        CaptureMigrationGap::EpistemicStatus,
        "open_session.sim",
    )?;
    exact_fields(
        sim,
        &["dt_ms", "chunk_ms", "seed", "mode", "duration_ms"],
        &["dt_ms", "chunk_ms", "seed", "mode", "duration_ms"],
        index,
        CaptureMigrationGap::EpistemicStatus,
        "open_session.sim",
    )?;
    for field in ["dt_ms", "chunk_ms"] {
        if finite_number(
            sim.get(field),
            index,
            CaptureMigrationGap::EpistemicStatus,
            &format!("open_session.sim.{field}"),
        )? <= 0.0
        {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::EpistemicStatus,
                index,
                format!("open_session.sim.{field} must be positive"),
            ));
        }
    }
    let requested_seed = nullable_safe_integer(
        sim.get("seed"),
        index,
        CaptureMigrationGap::EpistemicStatus,
        "open_session.sim.seed",
    )?;
    let mode = clean_string(
        sim,
        "mode",
        index,
        CaptureMigrationGap::EpistemicStatus,
        "open_session.sim",
    )?;
    if !matches!(mode, "stream" | "batch") {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            index,
            format!("open_session.sim.mode {mode:?} has no closed wire-0.8 meaning"),
        ));
    }
    if let Some(duration) = nullable_finite_number(
        sim.get("duration_ms"),
        index,
        CaptureMigrationGap::EpistemicStatus,
        "open_session.sim.duration_ms",
    )? {
        if duration <= 0.0 {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::EpistemicStatus,
                index,
                "open_session.sim.duration_ms must be positive or null",
            ));
        }
    }

    let bindings = bounded_array(
        record.payload.get("bindings"),
        index,
        CaptureMigrationGap::SessionLineage,
        "open_session.bindings",
    )?;
    for (offset, value) in bindings.iter().enumerate() {
        let path = format!("open_session.bindings[{offset}]");
        let binding = object_at(value, index, CaptureMigrationGap::SessionLineage, &path)?;
        exact_fields(
            binding,
            &["port", "direction", "entity"],
            &["port", "direction", "entity"],
            index,
            CaptureMigrationGap::SessionLineage,
            &path,
        )?;
        clean_string(
            binding,
            "port",
            index,
            CaptureMigrationGap::SessionLineage,
            &path,
        )?;
        let direction = clean_string(
            binding,
            "direction",
            index,
            CaptureMigrationGap::SessionLineage,
            &path,
        )?;
        if !matches!(direction, "stimulus" | "record") {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                index,
                format!("{path}.direction must be stimulus or record"),
            ));
        }
        let entity = object_at(
            required_value(
                binding,
                "entity",
                index,
                CaptureMigrationGap::SessionLineage,
                &path,
            )?,
            index,
            CaptureMigrationGap::SessionLineage,
            &format!("{path}.entity"),
        )?;
        exact_fields(
            entity,
            &["path", "role", "meta"],
            &["path", "role", "meta"],
            index,
            CaptureMigrationGap::SessionLineage,
            &format!("{path}.entity"),
        )?;
        clean_string(
            entity,
            "path",
            index,
            CaptureMigrationGap::SessionLineage,
            &format!("{path}.entity"),
        )?;
        let role = clean_string(
            entity,
            "role",
            index,
            CaptureMigrationGap::SessionLineage,
            &format!("{path}.entity"),
        )?;
        if !matches!(role, "system" | "actor" | "sensor" | "actuator") {
            return Err(CaptureMigrationError::semantic(
                CaptureMigrationGap::SessionLineage,
                index,
                format!("{path}.entity.role {role:?} has no closed wire-0.8 meaning"),
            ));
        }
        validate_string_map(
            entity.get("meta"),
            index,
            CaptureMigrationGap::SessionLineage,
            &format!("{path}.entity.meta"),
        )?;
    }

    Ok((network_ref.to_owned(), requested_seed))
}

fn validate_session_provenance(
    record: &CaptureRecord<'_>,
    requested_network_ref: &str,
    requested_seed: Option<i64>,
) -> Result<(), CaptureMigrationError> {
    let backend = require_string(
        record.payload,
        "backend",
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened",
    )?;
    if backend.is_empty() || backend.len() > MAX_CAPTURE_ID_BYTES {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            Some(record.index),
            "session_opened.backend must be explicit and bounded",
        ));
    }
    if !record.payload.get("error").is_some_and(Value::is_null) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "successful session_opened.error must be explicitly null",
        ));
    }
    let provenance = record.payload.get("provenance").ok_or_else(|| {
        CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            Some(record.index),
            "session_opened.provenance is missing",
        )
    })?;
    let provenance = object_at(
        provenance,
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened.provenance",
    )?;
    let provenance_backend = require_string(
        provenance,
        "backend",
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened.provenance",
    )?;
    let network_ref = require_string(
        provenance,
        "network_ref",
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened.provenance",
    )?;
    if provenance_backend != backend || network_ref != requested_network_ref {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            Some(record.index),
            "session provenance backend/network reference contradicts the open request or opened session",
        ));
    }
    exact_fields(
        provenance,
        &[
            "network_ref",
            "backend",
            "seed",
            "calibrated_posterior",
            "is_simulation_output",
            "advisory_only",
            "note",
        ],
        &[
            "network_ref",
            "backend",
            "seed",
            "calibrated_posterior",
            "is_simulation_output",
            "advisory_only",
            "note",
        ],
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened.provenance",
    )?;
    let provenance_seed = nullable_safe_integer(
        provenance.get("seed"),
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened.provenance.seed",
    )?;
    if requested_seed.is_some() && provenance_seed != requested_seed {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            Some(record.index),
            "session provenance seed contradicts the explicit open-session seed",
        ));
    }
    validate_nullable_clean_string(
        provenance.get("note"),
        Some(record.index),
        CaptureMigrationGap::EpistemicStatus,
        "session_opened.provenance.note",
    )?;
    validate_epistemic_flags(provenance, record.index, "session_opened.provenance")?;
    if provenance.get("advisory_only").and_then(Value::as_bool) != Some(true) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            Some(record.index),
            "session_opened.provenance.advisory_only must be explicitly true",
        ));
    }
    Ok(())
}

fn validate_epistemic_flags(
    object: &Map<String, Value>,
    record_index: u64,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    if object.get("calibrated_posterior").and_then(Value::as_bool) != Some(false)
        || object.get("is_simulation_output").and_then(Value::as_bool) != Some(true)
    {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::EpistemicStatus,
            Some(record_index),
            format!(
                "{path} must explicitly carry calibrated_posterior=false and is_simulation_output=true"
            ),
        ));
    }
    Ok(())
}

fn require_generation(
    payload: &Map<String, Value>,
    record_index: u64,
) -> Result<&str, CaptureMigrationError> {
    let session = payload.get("session").ok_or_else(|| {
        CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record_index),
            "session generation is missing",
        )
    })?;
    let session = object_at(
        session,
        Some(record_index),
        CaptureMigrationGap::SessionLineage,
        "session",
    )?;
    exact_fields(
        session,
        &["generation"],
        &["generation"],
        Some(record_index),
        CaptureMigrationGap::SessionLineage,
        "session",
    )?;
    let generation = require_string(
        session,
        "generation",
        Some(record_index),
        CaptureMigrationGap::SessionLineage,
        "session",
    )?;
    if !is_canonical_uuid_v4(generation) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record_index),
            "session.generation must be a canonical lowercase UUIDv4",
        ));
    }
    Ok(generation)
}

fn require_legacy_contract_hash(
    record: &CaptureRecord<'_>,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    let hash = require_string(
        record.payload,
        "contract_hash",
        Some(record.index),
        CaptureMigrationGap::ContractIdentity,
        path,
    )?;
    if hash != LEGACY_WIRE_0_8_CONTRACT_HASH {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::ContractIdentity,
            Some(record.index),
            format!("{path}.contract_hash does not match the frozen wire-0.8 contract"),
        ));
    }
    Ok(())
}

fn payload_session_id<'a>(record: &'a CaptureRecord<'_>) -> Result<&'a str, CaptureMigrationError> {
    let session_id = require_string(
        record.payload,
        "session_id",
        Some(record.index),
        CaptureMigrationGap::SessionLineage,
        "payload",
    )?;
    if session_id.len() > 64 || !valid_id_segment(session_id) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "payload.session_id must be a bounded concrete identifier",
        ));
    }
    Ok(session_id)
}

fn require_unscoped_metadata(record: &CaptureRecord<'_>) -> Result<(), CaptureMigrationError> {
    if record.route_session_id.is_some() || record.session_opened_index.is_some() {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "unscoped capabilities metadata must explicitly use null session fields",
        ));
    }
    Ok(())
}

fn require_route_session_metadata(
    record: &CaptureRecord<'_>,
    session_id: &str,
    require_open_index: bool,
) -> Result<(), CaptureMigrationError> {
    if record.route_session_id != Some(session_id) {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "route_session_id must explicitly equal payload.session_id",
        ));
    }
    if require_open_index && record.session_opened_index.is_none() {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "post-open records require an explicit session_opened_index",
        ));
    }
    if !require_open_index && record.session_opened_index.is_some() {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            "session creation records must explicitly use null session_opened_index",
        ));
    }
    Ok(())
}

fn require_route_plane(
    record: &CaptureRecord<'_>,
    session_id: &str,
    plane: &str,
) -> Result<String, CaptureMigrationError> {
    session_route_realm(record.route, session_id, plane).ok_or_else(|| {
        CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            format!(
                "capture route must explicitly bind session {session_id:?} and {plane:?} plane"
            ),
        )
    })
}

fn require_unscoped_route(
    record: &CaptureRecord<'_>,
    terminal: &str,
) -> Result<String, CaptureMigrationError> {
    let segments: Vec<&str> = record.route.split('/').collect();
    if segments.len() < 2
        || segments.last() != Some(&terminal)
        || !segments[..segments.len() - 1]
            .iter()
            .all(|segment| valid_id_segment(segment))
    {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            format!("capture route must be an exact {{realm}}/{terminal} key"),
        ));
    }
    Ok(segments[..segments.len() - 1].join("/"))
}

fn require_rpc_route(
    record: &CaptureRecord<'_>,
    request_kind: &str,
) -> Result<String, CaptureMigrationError> {
    let segments: Vec<&str> = record.route.split('/').collect();
    if segments.len() < 3
        || segments[segments.len() - 2..] != ["rpc", request_kind]
        || !segments[..segments.len() - 2]
            .iter()
            .all(|segment| valid_id_segment(segment))
    {
        return Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::SessionLineage,
            Some(record.index),
            format!("capture route must be an exact {{realm}}/rpc/{request_kind} key"),
        ));
    }
    Ok(segments[..segments.len() - 2].join("/"))
}

fn route_binds_plane(route: &str, session_id: &str, plane: &str) -> bool {
    session_route_realm(route, session_id, plane).is_some()
}

fn session_route_realm(route: &str, session_id: &str, plane: &str) -> Option<String> {
    let segments: Vec<&str> = route.split('/').collect();
    let plain_suffix = ["session", session_id, plane];
    if segments.len() >= 4
        && segments[segments.len() - plain_suffix.len()..] == plain_suffix
        && segments[..segments.len() - plain_suffix.len()]
            .iter()
            .all(|segment| valid_id_segment(segment))
    {
        return Some(segments[..segments.len() - plain_suffix.len()].join("/"));
    }
    if plane == "sensor"
        && segments.len() >= 5
        && segments[segments.len() - 4..segments.len() - 1] == plain_suffix
        && valid_id_segment(segments[segments.len() - 1])
        && segments[..segments.len() - 4]
            .iter()
            .all(|segment| valid_id_segment(segment))
    {
        return Some(segments[..segments.len() - 4].join("/"));
    }
    None
}

fn parse_unit(
    value: Option<&Value>,
    record_index: Option<u64>,
    path: &str,
) -> Result<Option<String>, CaptureMigrationError> {
    match value {
        Some(Value::Null) => Ok(None),
        Some(Value::String(unit))
            if !unit.is_empty()
                && unit.len() <= MAX_UNIT_BYTES
                && !unit.chars().any(char::is_control) =>
        {
            Ok(Some(unit.clone()))
        }
        _ => Err(CaptureMigrationError::semantic(
            CaptureMigrationGap::Unit,
            record_index,
            format!("{path} must be explicitly null or a bounded non-empty string"),
        )),
    }
}

fn clean_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a str, CaptureMigrationError> {
    let value = require_string(object, field, record_index, gap, path)?;
    if value.is_empty() || value.len() > MAX_CAPTURE_ID_BYTES || value.chars().any(char::is_control)
    {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path}.{field} must be bounded, non-empty, and control-free"),
        ));
    }
    Ok(value)
}

fn validate_nullable_clean_string(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    if let Some(value) = nullable_string(value, record_index, gap, path)? {
        if value.is_empty()
            || value.len() > MAX_CAPTURE_ID_BYTES
            || value.chars().any(char::is_control)
        {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path} must be null or a bounded non-empty control-free string"),
            ));
        }
    }
    Ok(())
}

fn bounded_array<'a>(
    value: Option<&'a Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a [Value], CaptureMigrationError> {
    let values = value.and_then(Value::as_array).ok_or_else(|| {
        CaptureMigrationError::semantic(gap, record_index, format!("{path} must be an array"))
    })?;
    if values.len() > crate::MAX_CHANNELS {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} exceeds the bounded entry limit"),
        ));
    }
    Ok(values)
}

fn validate_clean_string_array(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    for (offset, value) in bounded_array(value, record_index, gap, path)?
        .iter()
        .enumerate()
    {
        let value = value.as_str().ok_or_else(|| {
            CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path}[{offset}] must be a string"),
            )
        })?;
        if value.is_empty()
            || value.len() > MAX_CAPTURE_ID_BYTES
            || value.chars().any(char::is_control)
        {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path}[{offset}] must be bounded, non-empty, and control-free"),
            ));
        }
    }
    Ok(())
}

fn map_at<'a>(
    value: Option<&'a Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a Map<String, Value>, CaptureMigrationError> {
    let object = value.and_then(Value::as_object).ok_or_else(|| {
        CaptureMigrationError::semantic(gap, record_index, format!("{path} must be an object"))
    })?;
    if object.len() > crate::MAX_CHANNELS {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} exceeds the bounded entry limit"),
        ));
    }
    Ok(object)
}

fn validate_finite_number_map(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    for (name, value) in map_at(value, record_index, gap, path)? {
        if name.is_empty()
            || name.len() > MAX_CAPTURE_ID_BYTES
            || name.chars().any(char::is_control)
        {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path} contains an invalid member name"),
            ));
        }
        finite_number(Some(value), record_index, gap, &format!("{path}.{name}"))?;
    }
    Ok(())
}

fn validate_safe_integer_map(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
    require_positive: bool,
) -> Result<(), CaptureMigrationError> {
    for (name, value) in map_at(value, record_index, gap, path)? {
        if name.is_empty()
            || name.len() > MAX_CAPTURE_ID_BYTES
            || name.chars().any(char::is_control)
        {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path} contains an invalid member name"),
            ));
        }
        let integer = safe_integer(Some(value), record_index, gap, &format!("{path}.{name}"))?;
        if require_positive && integer <= 0 {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path}.{name} must be positive"),
            ));
        }
    }
    Ok(())
}

fn validate_string_map(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    for (name, value) in map_at(value, record_index, gap, path)? {
        if name.is_empty()
            || name.len() > MAX_CAPTURE_ID_BYTES
            || name.chars().any(char::is_control)
            || value.as_str().is_none_or(|value| {
                value.len() > MAX_CAPTURE_ID_BYTES || value.chars().any(char::is_control)
            })
        {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path} must contain only bounded control-free string pairs"),
            ));
        }
    }
    Ok(())
}

fn exact_fields(
    object: &Map<String, Value>,
    required: &[&str],
    allowed: &[&str],
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<(), CaptureMigrationError> {
    for field in required {
        if !object.contains_key(*field) {
            return Err(CaptureMigrationError::semantic(
                gap,
                record_index,
                format!("{path}.{field} is missing; migration never fills defaults"),
            ));
        }
    }
    if let Some(field) = object
        .keys()
        .find(|field| !allowed.contains(&field.as_str()))
    {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} contains unsupported or mixed-wire field {field:?}"),
        ));
    }
    Ok(())
}

fn object_at<'a>(
    value: &'a Value,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a Map<String, Value>, CaptureMigrationError> {
    value.as_object().ok_or_else(|| {
        CaptureMigrationError::semantic(gap, record_index, format!("{path} must be an object"))
    })
}

fn required_value<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a Value, CaptureMigrationError> {
    object.get(field).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path}.{field} is missing; migration never fills defaults"),
        )
    })
}

fn require_string<'a>(
    object: &'a Map<String, Value>,
    field: &str,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a str, CaptureMigrationError> {
    object.get(field).and_then(Value::as_str).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path}.{field} must be a string"),
        )
    })
}

fn nullable_string<'a>(
    value: Option<&'a Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<Option<&'a str>, CaptureMigrationError> {
    match value {
        Some(Value::Null) => Ok(None),
        Some(Value::String(value)) => Ok(Some(value)),
        _ => Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be an explicit string or null"),
        )),
    }
}

fn positive_safe_integer(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<i64, CaptureMigrationError> {
    let integer = value.and_then(Value::as_i64).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be an exact JSON integer"),
        )
    })?;
    if !(1..=crate::JSON_SAFE_INTEGER_MAX).contains(&integer) {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be within 1..=2^53-1"),
        ));
    }
    Ok(integer)
}

fn finite_number(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<f64, CaptureMigrationError> {
    value.and_then(Value::as_f64).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be a finite JSON number"),
        )
    })
}

fn nullable_finite_number(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<Option<f64>, CaptureMigrationError> {
    match value {
        Some(Value::Null) => Ok(None),
        Some(value) => finite_number(Some(value), record_index, gap, path).map(Some),
        None => Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be explicitly a finite number or null"),
        )),
    }
}

fn safe_integer(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<i64, CaptureMigrationError> {
    let integer = value.and_then(Value::as_i64).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be an exact JSON integer"),
        )
    })?;
    if !(crate::JSON_SAFE_INTEGER_MIN..=crate::JSON_SAFE_INTEGER_MAX).contains(&integer) {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} exceeds the exact JSON integer range"),
        ));
    }
    Ok(integer)
}

fn nullable_safe_integer(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<Option<i64>, CaptureMigrationError> {
    match value {
        Some(Value::Null) => Ok(None),
        Some(value) => safe_integer(Some(value), record_index, gap, path).map(Some),
        None => Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be explicitly an exact JSON integer or null"),
        )),
    }
}

fn finite_number_array<'a>(
    value: Option<&'a Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a [Value], CaptureMigrationError> {
    let values = value.and_then(Value::as_array).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be an array of finite JSON numbers"),
        )
    })?;
    for (index, value) in values.iter().enumerate() {
        finite_number(Some(value), record_index, gap, &format!("{path}[{index}]"))?;
    }
    Ok(values)
}

fn safe_integer_array<'a>(
    value: Option<&'a Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<&'a [Value], CaptureMigrationError> {
    let values = value.and_then(Value::as_array).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be an array of exact JSON integers"),
        )
    })?;
    for (index, value) in values.iter().enumerate() {
        safe_integer(Some(value), record_index, gap, &format!("{path}[{index}]"))?;
    }
    Ok(values)
}

fn positive_safe_u64(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<u64, CaptureMigrationError> {
    let integer = value.and_then(Value::as_u64).ok_or_else(|| {
        CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be an exact positive JSON integer"),
        )
    })?;
    if integer == 0 || integer > crate::JSON_SAFE_INTEGER_MAX as u64 {
        return Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be within 1..=2^53-1"),
        ));
    }
    Ok(integer)
}

fn nullable_positive_u64(
    value: Option<&Value>,
    record_index: Option<u64>,
    gap: CaptureMigrationGap,
    path: &str,
) -> Result<Option<u64>, CaptureMigrationError> {
    match value {
        Some(Value::Null) => Ok(None),
        Some(value) => positive_safe_u64(Some(value), record_index, gap, path).map(Some),
        None => Err(CaptureMigrationError::semantic(
            gap,
            record_index,
            format!("{path} must be explicitly an integer or null"),
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    type FixtureMutation = (CaptureMigrationGap, fn(&mut Value));

    fn fixture() -> Value {
        serde_json::from_slice(include_bytes!(
            "../../testdata/migration/wire-0.8-reconstructable-capture.json"
        ))
        .expect("capture fixture is JSON")
    }

    fn validate_value(value: &Value) -> Result<CaptureMigrationReport, CaptureMigrationError> {
        validate_wire_0_8_capture(&serde_json::to_vec(value).expect("fixture serializes"))
    }

    fn record_mut(value: &mut Value, one_based_index: usize) -> &mut Value {
        &mut value["records"][one_based_index - 1]
    }

    #[test]
    fn complete_capture_validates_without_upgrading_any_claim() {
        let source =
            include_bytes!("../../testdata/migration/wire-0.8-reconstructable-capture.json");
        let report = validate_wire_0_8_capture(source).unwrap();
        assert_eq!(report.records_validated, 11);
        assert_eq!(report.sessions_validated, 2);
        assert_eq!(report.streams_validated, 4);
        assert_eq!(report.publisher_restarts_validated, 3);
        assert_eq!(report.channel_values_validated, 12);
        assert_eq!(report.frame_ids_validated, 3);
        assert_eq!(report.epistemic_records_validated, 5);
        assert_eq!(report.authority_requiring_records, 0);
        assert!(report.validation_only);
        assert!(report.reconstructable.units);
        assert!(report.reconstructable.frames);
        assert!(report.reconstructable.session_lineage);
        assert!(report.reconstructable.authority_applicability);
        assert!(report.reconstructable.epistemic_status);
        assert!(!report.target_artifact_emitted);
        assert!(!report.security_upgraded);
        assert!(!report.authority_upgraded);
        assert!(!report.plant_safety_certified);
        assert!(!report.scientific_evidence_upgraded);
        assert!(!report.release_certified);
        assert_eq!(report.validator, "ncp-core::validate_wire_0_8_capture");
        assert_eq!(report.validator_package_version, PACKAGE_VERSION);
        assert_eq!(report.validator_build_identity, BUILD_IDENTITY);
        assert_eq!(
            report.target_normative_contract_digest,
            NORMATIVE_CONTRACT_DIGEST
        );
        assert_eq!(report.capture_sha256, sha256_hex(source));
    }

    #[test]
    fn each_required_reconstruction_axis_fails_with_a_distinct_category() {
        let mutations: &[FixtureMutation] = &[
            (CaptureMigrationGap::Unit, |value| {
                record_mut(value, 4)["payload"]["channels"]["pose_error"]
                    .as_object_mut()
                    .unwrap()
                    .remove("unit");
            }),
            (CaptureMigrationGap::Frame, |value| {
                record_mut(value, 4)["payload"]
                    .as_object_mut()
                    .unwrap()
                    .remove("frame_id");
            }),
            (CaptureMigrationGap::SessionLineage, |value| {
                record_mut(value, 4)["session_opened_index"] = Value::from(9);
            }),
            (CaptureMigrationGap::Authority, |value| {
                record_mut(value, 4)["payload"]["kind"] = Value::from("command_frame");
            }),
            (CaptureMigrationGap::EpistemicStatus, |value| {
                record_mut(value, 5)["payload"]["calibrated_posterior"] = Value::Bool(true);
            }),
        ];
        for (expected, mutate) in mutations {
            let mut value = fixture();
            mutate(&mut value);
            assert_eq!(validate_value(&value).unwrap_err().gap, *expected);
        }
    }

    #[test]
    fn restart_requires_fresh_publisher_incarnation_epoch_and_seq_one() {
        let mut same_process_new_epoch = fixture();
        let old_incarnation = same_process_new_epoch["records"][3]["publisher_incarnation"].clone();
        record_mut(&mut same_process_new_epoch, 6)["publisher_incarnation"] = old_incarnation;
        assert_eq!(
            validate_value(&same_process_new_epoch).unwrap_err().gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut restarted_with_old_epoch = fixture();
        let old_epoch =
            restarted_with_old_epoch["records"][3]["payload"]["stream"]["epoch"].clone();
        record_mut(&mut restarted_with_old_epoch, 6)["payload"]["stream"]["epoch"] = old_epoch;
        assert_eq!(
            validate_value(&restarted_with_old_epoch).unwrap_err().gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut restarted_above_one = fixture();
        record_mut(&mut restarted_above_one, 6)["payload"]["stream"]["seq"] = Value::from(2);
        assert_eq!(
            validate_value(&restarted_above_one).unwrap_err().gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut next_session_reused_epoch = fixture();
        let prior_epoch =
            next_session_reused_epoch["records"][3]["payload"]["stream"]["epoch"].clone();
        record_mut(&mut next_session_reused_epoch, 10)["payload"]["stream"]["epoch"] = prior_epoch;
        assert_eq!(
            validate_value(&next_session_reused_epoch).unwrap_err().gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut retired_process_on_another_route = fixture();
        let retired_incarnation =
            retired_process_on_another_route["records"][3]["publisher_incarnation"].clone();
        record_mut(&mut retired_process_on_another_route, 10)["route"] =
            Value::from("ncp/session/capture-session/sensor/velocity");
        record_mut(&mut retired_process_on_another_route, 10)["publisher_incarnation"] =
            retired_incarnation;
        assert_eq!(
            validate_value(&retired_process_on_another_route)
                .unwrap_err()
                .gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut cross_publisher_epoch_collision = fixture();
        let first_epoch =
            cross_publisher_epoch_collision["records"][3]["payload"]["stream"]["epoch"].clone();
        record_mut(&mut cross_publisher_epoch_collision, 6)["route"] =
            Value::from("ncp/session/capture-session/sensor/velocity");
        record_mut(&mut cross_publisher_epoch_collision, 6)["publisher_id"] =
            Value::from("sensor2");
        record_mut(&mut cross_publisher_epoch_collision, 6)["payload"]["stream"]["epoch"] =
            first_epoch;
        assert_eq!(
            validate_value(&cross_publisher_epoch_collision)
                .unwrap_err()
                .gap,
            CaptureMigrationGap::StreamContinuity
        );
    }

    #[test]
    fn timestamps_routes_and_source_correlation_are_exact() {
        let mut malformed_sensor_time = fixture();
        record_mut(&mut malformed_sensor_time, 4)["payload"]["t"] = Value::from("not-a-number");
        assert_eq!(
            validate_value(&malformed_sensor_time).unwrap_err().gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut cross_plane_route = fixture();
        record_mut(&mut cross_plane_route, 4)["route"] =
            Value::from("ncp/session/capture-session/command/sensor/pose");
        assert_eq!(
            validate_value(&cross_plane_route).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );

        let mut cross_realm_route = fixture();
        record_mut(&mut cross_realm_route, 4)["route"] =
            Value::from("other/session/capture-session/sensor/pose");
        assert_eq!(
            validate_value(&cross_realm_route).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );

        let mut mismatched_source_time = fixture();
        record_mut(&mut mismatched_source_time, 5)["payload"]["source_t"] = Value::from(999_999.0);
        assert_eq!(
            validate_value(&mismatched_source_time).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );

        let mut malformed_observation = fixture();
        let series = &mut record_mut(&mut malformed_observation, 5)["payload"]["records"]["vm"];
        series["port"] = Value::from(123);
        series["target"] = serde_json::json!({});
        series["observable"] = serde_json::json!([]);
        series["recordable"] = Value::from(42);
        series["times"] = Value::from("not-an-array");
        series["values"] = Value::from("not-an-array");
        series["senders"] = Value::from("not-an-array");
        assert_eq!(
            validate_value(&malformed_observation).unwrap_err().gap,
            CaptureMigrationGap::Unit
        );
    }

    #[test]
    fn duplicate_reorder_stale_generation_and_missing_open_result_reject() {
        let mut duplicate = fixture();
        record_mut(&mut duplicate, 7)["payload"]["stream"]["seq"] = Value::from(1);
        assert_eq!(
            validate_value(&duplicate).unwrap_err().gap,
            CaptureMigrationGap::StreamContinuity
        );

        let mut reordered = fixture();
        reordered["records"].as_array_mut().unwrap().swap(5, 6);
        reordered["records"][5]["capture_index"] = Value::from(6);
        reordered["records"][6]["capture_index"] = Value::from(7);
        assert_eq!(
            validate_value(&reordered).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );

        let mut stale = fixture();
        record_mut(&mut stale, 10)["payload"]["session"]["generation"] =
            Value::from("293279f3-d459-4bfd-aeeb-604799e96925");
        record_mut(&mut stale, 10)["session_opened_index"] = Value::from(3);
        assert_eq!(
            validate_value(&stale).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );

        let mut missing_result = fixture();
        missing_result["records"]
            .as_array_mut()
            .unwrap()
            .truncate(8);
        assert_eq!(
            validate_value(&missing_result).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );
    }

    #[test]
    fn partial_defaults_wrong_contract_future_wire_and_mutation_records_reject() {
        let mut missing_metadata = fixture();
        record_mut(&mut missing_metadata, 4)
            .as_object_mut()
            .unwrap()
            .remove("session_opened_index");
        assert_eq!(
            validate_value(&missing_metadata).unwrap_err().gap,
            CaptureMigrationGap::Envelope
        );

        let mut wrong_contract = fixture();
        wrong_contract["source_contract_hash"] = Value::from("163acc57d8a62b66");
        assert_eq!(
            validate_value(&wrong_contract).unwrap_err().gap,
            CaptureMigrationGap::ContractIdentity
        );

        let mut future_wire = fixture();
        record_mut(&mut future_wire, 4)["payload"]["ncp_version"] = Value::from("1.0");
        assert_eq!(
            validate_value(&future_wire).unwrap_err().gap,
            CaptureMigrationGap::ContractIdentity
        );

        let mut missing_codec_disposition = fixture();
        record_mut(&mut missing_codec_disposition, 1)["payload"]
            .as_object_mut()
            .unwrap()
            .remove("codec_id");
        assert_eq!(
            validate_value(&missing_codec_disposition).unwrap_err().gap,
            CaptureMigrationGap::Unit
        );

        let mut missing_channel_description = fixture();
        record_mut(&mut missing_channel_description, 1)["payload"]["sensor_channels"][0]
            .as_object_mut()
            .unwrap()
            .remove("description");
        assert_eq!(
            validate_value(&missing_channel_description)
                .unwrap_err()
                .gap,
            CaptureMigrationGap::Unit
        );

        let mut malformed_channel_description = fixture();
        record_mut(&mut malformed_channel_description, 1)["payload"]["sensor_channels"][0]
            ["description"] = serde_json::json!({});
        assert_eq!(
            validate_value(&malformed_channel_description)
                .unwrap_err()
                .gap,
            CaptureMigrationGap::Unit
        );

        let mut contradictory_role = fixture();
        record_mut(&mut contradictory_role, 1)["payload"]["role"] = Value::from("commander");
        assert_eq!(
            validate_value(&contradictory_role).unwrap_err().gap,
            CaptureMigrationGap::Authority
        );

        let mut contradictory_provenance = fixture();
        record_mut(&mut contradictory_provenance, 3)["payload"]["provenance"]["backend"] =
            Value::from("other-backend");
        assert_eq!(
            validate_value(&contradictory_provenance).unwrap_err().gap,
            CaptureMigrationGap::EpistemicStatus
        );

        let mut contradictory_seed = fixture();
        record_mut(&mut contradictory_seed, 2)["payload"]["sim"]["seed"] = Value::from(999);
        assert_eq!(
            validate_value(&contradictory_seed).unwrap_err().gap,
            CaptureMigrationGap::EpistemicStatus
        );

        let mut malformed_record_spec = fixture();
        record_mut(&mut malformed_record_spec, 2)["payload"]["record"] =
            Value::from("not-an-object");
        assert_eq!(
            validate_value(&malformed_record_spec).unwrap_err().gap,
            CaptureMigrationGap::Unit
        );

        let mut malformed_stimulus_spec = fixture();
        record_mut(&mut malformed_stimulus_spec, 2)["payload"]["stimulus"] = serde_json::json!([]);
        assert_eq!(
            validate_value(&malformed_stimulus_spec).unwrap_err().gap,
            CaptureMigrationGap::Unit
        );

        let mut malformed_bindings = fixture();
        record_mut(&mut malformed_bindings, 2)["payload"]["bindings"] = serde_json::json!({});
        assert_eq!(
            validate_value(&malformed_bindings).unwrap_err().gap,
            CaptureMigrationGap::SessionLineage
        );

        let mut unroutable_status = fixture();
        record_mut(&mut unroutable_status, 4)["payload"]["kind"] = Value::from("control_status");
        assert_eq!(
            validate_value(&unroutable_status).unwrap_err().gap,
            CaptureMigrationGap::Envelope
        );

        for kind in [
            "command_frame",
            "step_request",
            "run_request",
            "close_session",
            "session_closed",
        ] {
            let mut authority_gap = fixture();
            record_mut(&mut authority_gap, 4)["payload"]["kind"] = Value::from(kind);
            let error = validate_value(&authority_gap).unwrap_err();
            assert_eq!(error.gap, CaptureMigrationGap::Authority, "{kind}");
        }
    }

    #[test]
    fn empty_malformed_duplicate_and_oversized_captures_fail_before_semantics() {
        let empty = serde_json::json!({
            "schema": LEGACY_CAPTURE_SCHEMA,
            "source_wire": "0.8",
            "source_contract_hash": LEGACY_WIRE_0_8_CONTRACT_HASH,
            "records": []
        });
        assert_eq!(
            validate_value(&empty).unwrap_err().gap,
            CaptureMigrationGap::Envelope
        );
        assert_eq!(
            validate_wire_0_8_capture(br#"{"schema": }"#)
                .unwrap_err()
                .code,
            "NCP-LIMIT-009"
        );
        assert_eq!(
            validate_wire_0_8_capture(br#"{"schema":"a","schema":"b"}"#)
                .unwrap_err()
                .code,
            "NCP-LIMIT-007"
        );
        let oversized = vec![b' '; bounded_json::MAX_FRAME_BYTES + 1];
        assert_eq!(
            validate_wire_0_8_capture(&oversized).unwrap_err().code,
            "NCP-LIMIT-001"
        );
    }

    #[test]
    fn formatting_changes_only_capture_identity_not_semantic_counts() {
        let compact = serde_json::to_vec(&fixture()).unwrap();
        let pretty = serde_json::to_vec_pretty(&fixture()).unwrap();
        let compact_report = validate_wire_0_8_capture(&compact).unwrap();
        let pretty_report = validate_wire_0_8_capture(&pretty).unwrap();
        assert_ne!(compact_report.capture_sha256, pretty_report.capture_sha256);
        assert_eq!(
            compact_report.records_validated,
            pretty_report.records_validated
        );
        assert_eq!(
            compact_report.reconstructable,
            pretty_report.reconstructable
        );
    }
}
