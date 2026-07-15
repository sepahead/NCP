//! Explicit, one-way wire-0.8 to wire-1.0 migration helpers.
//!
//! This is not a transparent compatibility mode. The only currently supported
//! mapping is `Capabilities.optional` -> `ChannelSpec.requirement`, and it is
//! allowed only when every legacy boolean is explicitly present. The gateway
//! never asserts transport security, authority, plant safety, or scientific
//! evidence that the 0.8 payload did not carry. The capture validator is likewise
//! validation-only: it checks explicit legacy fields in a bounded capture limited
//! to capabilities, the lifecycle open exchange, sensor data, and observations,
//! but never emits a native-1.0 capture or upgrades its security, authority,
//! safety, or scientific status.

mod capture;

pub use capture::{
    validate_wire_0_8_capture, CaptureMigrationError, CaptureMigrationGap, CaptureMigrationReport,
    CaptureReconstructability, CAPTURE_MIGRATION_REPORT_SCHEMA, LEGACY_CAPTURE_SCHEMA,
    LEGACY_WIRE_0_8_CONTRACT_HASH, MAX_CAPTURE_RECORDS,
};

use crate::bounded_json;
use crate::idempotency::sha256_hex;
use crate::{GatewayAttribution, IdentityClaim, CONTRACT_HASH, NCP_VERSION};
use serde::{Deserialize, Serialize};
use std::fmt;

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct MigrationReceipt {
    pub schema: String,
    pub gateway_id: String,
    pub direction: String,
    pub source_wire: String,
    pub target_wire: String,
    pub target_contract_hash: String,
    pub source_sha256: String,
    pub target_sha256: String,
    pub security_upgraded: bool,
    pub authority_upgraded: bool,
    pub plant_safety_certified: bool,
    pub scientific_evidence_upgraded: bool,
}

/// Explicit authority supplied by a terminating 1.0 gateway. None of these
/// values may be inferred from the legacy payload. `terminates_native_1_0=true`
/// means the gateway itself implements and enforces the advertised 1.0 core
/// semantics rather than pretending the 0.8 peer did.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct GatewayContext {
    pub gateway_id: String,
    pub identity: IdentityClaim,
    pub security_profile: String,
    pub security_state_digest: String,
    pub stable_capabilities: Vec<String>,
    pub plant_profile_digest: Option<String>,
    pub terminates_native_1_0: bool,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct MigrationError {
    pub code: &'static str,
    pub detail: String,
}

impl MigrationError {
    fn new(code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            code,
            detail: detail.into(),
        }
    }
}

impl fmt::Display for MigrationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for MigrationError {}

fn valid_gateway_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && !value.chars().any(|character| {
            character.is_control()
                || character.is_whitespace()
                || matches!(character, '/' | '*' | '$' | '#' | '?')
        })
}

pub fn translate_capabilities_0_8_to_1_0(
    _source: &[u8],
    gateway_id: &str,
) -> Result<(Vec<u8>, MigrationReceipt), MigrationError> {
    if !valid_gateway_id(gateway_id) {
        return Err(MigrationError::new(
            "NCP-GATEWAY-001",
            "gateway identity is invalid",
        ));
    }
    Err(MigrationError::new(
        "NCP-GATEWAY-002",
        "legacy translation requires explicit authenticated GatewayContext; identity, security, authority, and capabilities are never invented",
    ))
}

pub fn translate_capabilities_0_8_to_1_0_with_context(
    source: &[u8],
    context: &GatewayContext,
) -> Result<(Vec<u8>, MigrationReceipt), MigrationError> {
    if !valid_gateway_id(&context.gateway_id) {
        return Err(MigrationError::new(
            "NCP-GATEWAY-001",
            "gateway identity is invalid",
        ));
    }
    if !context.terminates_native_1_0 {
        return Err(MigrationError::new(
            "NCP-GATEWAY-002",
            "a transparent gateway cannot advertise native 1.0 semantics",
        ));
    }
    let mut value = bounded_json::parse_value(source).map_err(|error| {
        MigrationError::new(error.code.stable_code(), format!("legacy payload: {error}"))
    })?;
    let object = value
        .as_object_mut()
        .ok_or_else(|| MigrationError::new("NCP-GATEWAY-001", "legacy payload is not an object"))?;
    if object
        .get("ncp_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.8")
        || object.get("kind").and_then(serde_json::Value::as_str) != Some("capabilities")
    {
        return Err(MigrationError::new(
            "NCP-GATEWAY-001",
            "only wire-0.8 capabilities -> wire-1.0 translation is supported",
        ));
    }
    for field in [
        "identity",
        "security_profile",
        "security_state_digest",
        "stable_capabilities",
        "gateway_permitted",
        "plant_profile_digest",
        "gateway",
    ] {
        if object.contains_key(field) {
            return Err(MigrationError::new(
                "NCP-GATEWAY-002",
                format!("legacy payload mixes 0.8 with 1.0 field {field:?}"),
            ));
        }
    }
    for field in ["sensor_channels", "command_channels"] {
        let channels = object
            .get_mut(field)
            .and_then(serde_json::Value::as_array_mut)
            .ok_or_else(|| {
                MigrationError::new(
                    "NCP-GATEWAY-002",
                    format!("legacy capabilities.{field} is missing or not an array"),
                )
            })?;
        if channels.len() > crate::MAX_CHANNELS {
            return Err(MigrationError::new(
                "NCP-LIMIT-003",
                format!("legacy capabilities.{field} exceeds the channel limit"),
            ));
        }
        for (index, channel) in channels.iter_mut().enumerate() {
            let channel = channel.as_object_mut().ok_or_else(|| {
                MigrationError::new(
                    "NCP-GATEWAY-002",
                    format!("legacy capabilities.{field}[{index}] is not an object"),
                )
            })?;
            if channel.contains_key("requirement") {
                return Err(MigrationError::new(
                    "NCP-GATEWAY-002",
                    format!("legacy capabilities.{field}[{index}] mixes 0.8 and 1.0 fields"),
                ));
            }
            let optional = channel
                .remove("optional")
                .and_then(|value| value.as_bool())
                .ok_or_else(|| {
                    MigrationError::new(
                        "NCP-GATEWAY-002",
                        format!(
                            "legacy capabilities.{field}[{index}].optional must be an explicit boolean"
                        ),
                    )
                })?;
            channel.insert(
                "requirement".into(),
                serde_json::Value::String(if optional { "optional" } else { "required" }.into()),
            );
        }
    }
    object.insert(
        "ncp_version".into(),
        serde_json::Value::String(NCP_VERSION.into()),
    );
    object.insert(
        "identity".into(),
        serde_json::to_value(&context.identity).map_err(|error| {
            MigrationError::new(
                "NCP-GATEWAY-001",
                format!("gateway identity cannot be encoded: {error}"),
            )
        })?,
    );
    object.insert(
        "security_profile".into(),
        serde_json::Value::String(context.security_profile.clone()),
    );
    object.insert(
        "security_state_digest".into(),
        serde_json::Value::String(context.security_state_digest.clone()),
    );
    object.insert(
        "stable_capabilities".into(),
        serde_json::to_value(&context.stable_capabilities).expect("string list serializes"),
    );
    object.insert("gateway_permitted".into(), serde_json::Value::Bool(true));
    object.insert(
        "plant_profile_digest".into(),
        context
            .plant_profile_digest
            .clone()
            .map_or(serde_json::Value::Null, serde_json::Value::String),
    );
    object.insert(
        "gateway".into(),
        serde_json::to_value(GatewayAttribution {
            gateway_id: context.gateway_id.clone(),
            source_wire: "0.8".into(),
        })
        .expect("gateway attribution serializes"),
    );
    let target = serde_json::to_vec(&value).map_err(|error| {
        MigrationError::new(
            "NCP-GATEWAY-001",
            format!("translated payload cannot be encoded: {error}"),
        )
    })?;
    let target_value = bounded_json::parse_value(&target).map_err(|error| {
        MigrationError::new(
            error.code.stable_code(),
            format!("translated payload: {error}"),
        )
    })?;
    crate::validate(&target_value).map_err(|error| {
        MigrationError::new(
            "NCP-GATEWAY-002",
            format!("translated capabilities is not valid wire 1.0: {error}"),
        )
    })?;
    let receipt = MigrationReceipt {
        schema: "ncp.migration-receipt.v1".into(),
        gateway_id: context.gateway_id.clone(),
        direction: "0.8-to-1.0".into(),
        source_wire: "0.8".into(),
        target_wire: NCP_VERSION.into(),
        target_contract_hash: CONTRACT_HASH.into(),
        source_sha256: sha256_hex(source),
        target_sha256: sha256_hex(&target),
        security_upgraded: false,
        authority_upgraded: false,
        plant_safety_certified: false,
        scientific_evidence_upgraded: false,
    };
    Ok((target, receipt))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Plane, PrincipalRole};

    fn context() -> GatewayContext {
        GatewayContext {
            gateway_id: "gateway-1".into(),
            identity: IdentityClaim {
                principal_id: "controller-principal-1".into(),
                entity_id: "c".into(),
                role: PrincipalRole::Commander,
                plane: Plane::Control,
            },
            security_profile: "dev-loopback-insecure".into(),
            security_state_digest:
                "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab".into(),
            stable_capabilities: vec![
                "ncp.core.canonical-json.v1".into(),
                "ncp.core.lifecycle.v1".into(),
                "ncp.core.authority-lease.v1".into(),
                "ncp.core.idempotent-mutation.v1".into(),
                "ncp.core.plant-profile.v1".into(),
            ],
            plant_profile_digest: None,
            terminates_native_1_0: true,
        }
    }

    fn capabilities(channel: &str) -> Vec<u8> {
        format!(
            r#"{{"ncp_version":"0.8","kind":"capabilities","controller_id":"c","role":"controller","control_rate_hz":50,"sensor_channels":[{channel}],"command_channels":[],"safety":{{"command_timeout_ms":200}}}}"#
        )
        .into_bytes()
    }

    #[test]
    fn explicit_legacy_booleans_translate_without_upgrading_claims() {
        for (legacy, expected) in [("false", "required"), ("true", "optional")] {
            let source = capabilities(&format!(
                r#"{{"name":"pose","kind":"vec3","optional":{legacy}}}"#
            ));
            let (target, receipt) =
                translate_capabilities_0_8_to_1_0_with_context(&source, &context()).unwrap();
            let value: serde_json::Value = serde_json::from_slice(&target).unwrap();
            assert_eq!(value["sensor_channels"][0]["requirement"], expected);
            assert!(value["sensor_channels"][0].get("optional").is_none());
            assert_eq!(value["ncp_version"], "1.0");
            assert_eq!(value["gateway"]["gateway_id"], "gateway-1");
            assert_eq!(value["gateway"]["source_wire"], "0.8");
            assert!(!receipt.security_upgraded);
            assert!(!receipt.authority_upgraded);
            assert!(!receipt.plant_safety_certified);
            assert!(!receipt.scientific_evidence_upgraded);
        }
    }

    #[test]
    fn absent_malformed_or_mixed_legacy_default_fails_closed() {
        for channel in [
            r#"{"name":"pose","kind":"vec3"}"#,
            r#"{"name":"pose","kind":"vec3","optional":"yes"}"#,
            r#"{"name":"pose","kind":"vec3","optional":false,"requirement":"required"}"#,
        ] {
            assert_eq!(
                translate_capabilities_0_8_to_1_0_with_context(&capabilities(channel), &context())
                    .unwrap_err()
                    .code,
                "NCP-GATEWAY-002"
            );
        }
    }

    #[test]
    fn legacy_convenience_path_and_transparent_gateway_fail_closed() {
        let source = capabilities(r#"{"name":"pose","kind":"vec3","optional":false}"#);
        assert_eq!(
            translate_capabilities_0_8_to_1_0(&source, "gateway-1")
                .unwrap_err()
                .code,
            "NCP-GATEWAY-002"
        );
        let mut transparent = context();
        transparent.terminates_native_1_0 = false;
        assert_eq!(
            translate_capabilities_0_8_to_1_0_with_context(&source, &transparent)
                .unwrap_err()
                .code,
            "NCP-GATEWAY-002"
        );
    }

    #[test]
    fn reverse_native_or_other_message_translation_is_excluded() {
        for source in [
            br#"{"ncp_version":"1.0","kind":"capabilities"}"#.as_slice(),
            br#"{"ncp_version":"0.8","kind":"command_frame"}"#.as_slice(),
        ] {
            assert_eq!(
                translate_capabilities_0_8_to_1_0_with_context(source, &context())
                    .unwrap_err()
                    .code,
                "NCP-GATEWAY-001"
            );
        }
    }

    #[test]
    fn committed_migration_vectors_are_exhaustive_and_fail_closed() {
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("testdata/conformance/migration/channel-requirement.json");
        let corpus: serde_json::Value = serde_json::from_slice(
            &std::fs::read(&path)
                .unwrap_or_else(|error| panic!("failed to read {}: {error}", path.display())),
        )
        .unwrap_or_else(|error| panic!("invalid migration corpus {}: {error}", path.display()));
        let cases = corpus["cases"]
            .as_array()
            .expect("migration corpus cases is an array");
        assert!(!cases.is_empty(), "migration corpus must not be empty");

        for case in cases {
            let id = case["id"].as_str().expect("migration case id");
            let channel = if let Some(channel) = case.get("legacy_channel") {
                channel.clone()
            } else {
                serde_json::json!({
                    "name": "pose",
                    "kind": "vec3",
                    "optional": case.get("legacy_optional").cloned().unwrap_or_default()
                })
            };
            let source = serde_json::to_vec(&serde_json::json!({
                "ncp_version": "0.8",
                "kind": "capabilities",
                "controller_id": "c",
                "role": "controller",
                "control_rate_hz": 50,
                "sensor_channels": [channel],
                "command_channels": [],
                "safety": {"command_timeout_ms": 200}
            }))
            .expect("legacy fixture serializes");
            let mut gateway = context();
            if case
                .pointer("/gateway_context/terminates_native_1_0")
                .and_then(serde_json::Value::as_bool)
                == Some(false)
            {
                gateway.terminates_native_1_0 = false;
            }

            let result = translate_capabilities_0_8_to_1_0_with_context(&source, &gateway);
            match case["expected"].as_str().expect("migration expectation") {
                "translated" => {
                    let (target, receipt) = result.unwrap_or_else(|error| {
                        panic!("migration vector {id} unexpectedly rejected: {error}")
                    });
                    let target: serde_json::Value =
                        serde_json::from_slice(&target).expect("translated JSON");
                    assert_eq!(
                        target["sensor_channels"][0]["requirement"], case["expected_requirement"],
                        "migration vector {id}"
                    );
                    assert_eq!(receipt.source_wire, "0.8", "migration vector {id}");
                    assert_eq!(receipt.target_wire, "1.0", "migration vector {id}");
                    assert!(!receipt.security_upgraded, "migration vector {id}");
                    assert!(!receipt.authority_upgraded, "migration vector {id}");
                }
                "rejected" => match result {
                    Ok(_) => panic!("migration vector {id} unexpectedly passed"),
                    Err(error) => assert_eq!(
                        error.code,
                        case["expected_error"]
                            .as_str()
                            .expect("expected error code"),
                        "migration vector {id}"
                    ),
                },
                expected => panic!("migration vector {id} has unknown expectation {expected:?}"),
            }
        }
    }
}
