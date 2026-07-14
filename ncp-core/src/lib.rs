#![doc = include_str!("../README.md")]
#![cfg_attr(docsrs, feature(doc_cfg))]

pub mod audit;
pub mod authority;
pub mod bounded_json;
pub mod bulk;
pub mod bus;
mod canonical_digest;
pub mod codec;
pub mod contract_identity;
pub mod idempotency;
pub mod keys;
pub mod messages;
pub mod migration;
pub mod plant;
pub mod request_digest;
pub mod resilience;
pub mod safety;
pub mod security;
pub mod stream_fence;
pub mod transport;

pub use audit::{AuditChain, AuditEvent, AuditEventDraft, AuditEventType};
pub use authority::{AuthorityLease, AuthorityMachine, AuthoritySnapshot, LifecycleState};
pub use bulk::{observation_from_bulk, BulkBlock, BulkError, Column, BULK_MAGIC, BULK_VERSION};
pub use bus::{Bus, BusError, LocalBus, NcpBusClient, NcpBusServer, QueryHandler, SubCallback};
pub use codec::{
    default_uav_velocity_codec, CodecError, CodecSpec, DecoderChannelMap, EncoderChannelMap,
    MAX_CODEC_COMPONENTS,
};
pub use contract_identity::{BUILD_IDENTITY, NORMATIVE_CONTRACT_DIGEST, PACKAGE_VERSION};
pub use idempotency::{
    IdempotencyCache, OperationContext, OperationDecision, OperationOutcome, ResponderBinding,
    ResponderReceipt,
};
pub use keys::{valid_id_segment, InvalidKeySegment, InvalidRealm, Keys, DEFAULT_REALM};
pub use messages::*;
pub use migration::{
    translate_capabilities_0_8_to_1_0, translate_capabilities_0_8_to_1_0_with_context,
    GatewayContext, MigrationError, MigrationReceipt,
};
pub use plant::{PlantCommand, PlantProfile, PlantProfileError, SafeActionKind};
pub use request_digest::{
    canonical_request_projection, request_digest, verify_request_digest, RequestDigestError,
    MAX_REQUEST_PROJECTION_BYTES, REQUEST_DIGEST_DOMAIN_V1,
};
pub use resilience::{max_horizon_len, ActionBuffer, LinkMonitor};
pub use safety::{CommandWatchdog, SafetyGovernor};
pub use stream_fence::{
    StreamFenceError, StreamMonotonicityFence, MAX_STREAM_FENCE_ENTRIES,
    MAX_STREAM_FENCE_KIND_BYTES, MAX_STREAM_FENCE_ROUTE_BYTES,
};
pub use transport::{
    ControlTransport, Controller, InProcessTransport, NeuroControlLoop, ReflexController,
};

#[cfg(test)]
mod wire_tests {
    use super::*;
    use crate::messages::test_ids::{session, stream, EPOCH, GEN, SID};

    fn operation() -> serde_json::Value {
        serde_json::json!({
            "operation_id": "10000000-0000-4000-8000-000000000001",
            "request_digest": "661cc70e48a4fbbe0217623e657c5a00457b2f1114a22f67ccc97ff27b05e212",
            "session_epoch": GEN,
            "expected_state_version": 1,
            "deadline_utc_ms": 1_700_000_030_000_i64,
            "retry": false
        })
    }

    fn authority() -> serde_json::Value {
        serde_json::json!({
            "session_epoch": GEN,
            "term": 1,
            "lease_id": "20000000-0000-4000-8000-000000000001",
            "issuer_principal_id": "controller-1",
            "holder_principal_id": "controller-1",
            "holder_entity_id": "body-1",
            "issued_at_utc_ms": 1_700_000_000_000_i64,
            "expires_at_utc_ms": 1_700_000_030_000_i64
        })
    }

    fn seal_mutation(mut request: serde_json::Value) -> serde_json::Value {
        let digest = request_digest(&request).expect("test mutation is digestible");
        request["operation"]["request_digest"] = serde_json::Value::String(digest);
        request
    }

    fn body_identity() -> serde_json::Value {
        serde_json::json!({
            "principal_id": "body-1",
            "entity_id": "simulator-1",
            "role": "body",
            "plane": "control"
        })
    }

    /// The `kind` discriminator and enum string values must match the Python
    /// reference exactly so peers interoperate.
    #[test]
    fn enum_wire_values() {
        assert_eq!(serde_json::to_string(&Observable::Vm).unwrap(), "\"V_m\"");
        assert_eq!(
            serde_json::to_string(&Observable::Spikes).unwrap(),
            "\"spikes\""
        );
        assert_eq!(
            serde_json::to_string(&StimulusKind::CurrentPa).unwrap(),
            "\"current_pA\""
        );
        assert_eq!(
            serde_json::to_string(&StimulusKind::SpikeTimes).unwrap(),
            "\"spike_times\""
        );
        assert_eq!(
            serde_json::to_string(&NetworkRefKind::ModelId).unwrap(),
            "\"model_id\""
        );
        assert_eq!(serde_json::to_string(&Mode::Estop).unwrap(), "\"estop\"");
    }

    /// A step request from a TS/Python client must round-trip through the Rust
    /// types (forward-compatible: unknown fields ignored).
    #[test]
    fn step_request_roundtrip_from_python_json() {
        let json = r#"{
            "ncp_version": "0.7",
            "kind": "step_request",
            "session_id": "s1",
            "advance_ms": 50.0,
            "stimulus": {"kind":"stimulus_frame","session_id":"s1","values":{
                "drive": {"data":[500.0],"unit":"pA"}
            }},
            "future_field_we_do_not_know": 7
        }"#;
        let req: StepRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.session_id, "s1");
        assert_eq!(req.advance_ms, Some(50.0));
        let stim = req.stimulus.unwrap();
        assert_eq!(stim.values["drive"].data, vec![500.0]);
        assert_eq!(stim.values["drive"].unit.as_deref(), Some("pA"));
    }

    #[test]
    fn observation_frame_carries_scientific_boundary() {
        let obs = ObservationFrame::default();
        let v: serde_json::Value = serde_json::to_value(&obs).unwrap();
        assert_eq!(v["calibrated_posterior"], serde_json::json!(false));
        assert_eq!(v["is_simulation_output"], serde_json::json!(true));
        assert_eq!(v["kind"], serde_json::json!("observation_frame"));
    }

    #[test]
    fn network_ref_field_is_ref_on_the_wire() {
        let n = NetworkRef {
            ref_: "iaf_psc_alpha".into(),
            ..Default::default()
        };
        let v: serde_json::Value = serde_json::to_value(&n).unwrap();
        assert_eq!(v["ref"], serde_json::json!("iaf_psc_alpha"));
        assert_eq!(v["kind"], serde_json::json!("builtin"));
    }

    #[test]
    fn version_guard() {
        // Stable wire 1.x is major-compatible. Every 0.x wire is a deliberate
        // incompatible boundary and requires the labelled fail-closed gateway.
        assert!(check_version("1.0", true).unwrap());
        assert!(check_version("1.9", true).unwrap());
        assert!(check_version("0.8", true).is_err());
        assert!(check_version("0.5", true).is_err());
        assert!(check_version("0.4", true).is_err());
        assert!(check_version("0.1", true).is_err());
        assert!(!check_version("0.1", false).unwrap()); // ...and Ok(false) when lenient
        assert!(check_version("0.9", true).is_err());
        assert!(!check_version("0.9", false).unwrap()); // ...and Ok(false) when lenient
        assert!(check_version("2.0", true).is_err());
        assert!(check_version("bogus", false).is_err());
    }

    #[test]
    fn codec_encode_decode_roundtrip() {
        let codec = default_uav_velocity_codec();
        let mut channels = Map::new();
        channels.insert(
            "pose_error".into(),
            ChannelValue::vec3(2.0, 0.0, -2.0, Some("m")),
        );
        let sensor = SensorFrame {
            channels,
            ..Default::default()
        };
        let rates = codec.encode(Some(&sensor));
        // +2.0 error -> top of rate range; -2.0 -> bottom.
        assert!((rates["err_x"] - 200.0).abs() < 1e-6);
        assert!((rates["err_z"] - 0.0).abs() < 1e-6);
        let cmd = codec.decode(
            &rates,
            0.0,
            stream(1),
            "world",
            Mode::Active,
            session(),
            SID,
        );
        assert_eq!(cmd.channels["velocity_setpoint"].data.len(), 3);
        assert_eq!(cmd.stream.seq, 1, "decode stamps its own stream seq");
    }

    /// codec-bus-1: the decoder's readout populations (`vel_*`) are absent from
    /// `pop_rates` here, so each component must fall to the NEUTRAL midpoint (0.0
    /// for the symmetric ±1.5 range) — NOT the value-range low bound (-1.5 m/s,
    /// full-reverse actuation that the governor's magnitude clamp would pass).
    #[test]
    fn codec_absent_population_maps_to_neutral_not_full_reverse() {
        let codec = default_uav_velocity_codec();
        let cmd = codec.decode(
            &Map::new(),
            0.0,
            stream(1),
            "world",
            Mode::Active,
            session(),
            SID,
        );
        for c in &cmd.channels["velocity_setpoint"].data {
            assert!(
                c.abs() < 1e-9,
                "absent population must decode to neutral 0.0, got {c}"
            );
        }
    }

    /// A non-finite sensor sample must not poison the rate pipeline: a NaN error
    /// component encodes to the low bound of the rate range (fail-safe), never
    /// to a NaN rate.
    #[test]
    fn codec_nan_sensor_fails_safe_to_low_bound() {
        let codec = default_uav_velocity_codec();
        let mut channels = Map::new();
        channels.insert(
            "pose_error".into(),
            ChannelValue::vec3(f64::NAN, f64::INFINITY, f64::NEG_INFINITY, Some("m")),
        );
        let sensor = SensorFrame {
            channels,
            ..Default::default()
        };
        let rates = codec.encode(Some(&sensor));
        for axis in ["err_x", "err_y", "err_z"] {
            let r = rates[axis];
            assert!(r.is_finite(), "{axis} rate must be finite, got {r}");
            // rate_range_hz low bound is 0.0 for the default codec.
            assert!(
                (r - 0.0).abs() < 1e-9,
                "{axis} should fail safe to low bound, got {r}"
            );
        }
    }

    /// `validate()` must be honest: a `step_request` missing its required
    /// `session_id` is rejected even though the typed `serde` round-trip would
    /// silently default it to an empty string.
    #[test]
    fn validate_rejects_missing_required() {
        // Missing required `session_id` (version present so THIS is what trips).
        let bad = serde_json::json!({"kind": "step_request", "ncp_version": NCP_VERSION, "advance_ms": 1.0});
        assert!(
            validate(&bad).is_err(),
            "missing session_id must be rejected"
        );
        // ...yet the typed round-trip happily defaults it (the bug validate closes).
        let typed: StepRequest = serde_json::from_value(bad).unwrap();
        assert_eq!(typed.session_id, "");

        // A complete step_request passes.
        let good = seal_mutation(serde_json::json!({
            "kind": "step_request", "ncp_version": NCP_VERSION, "session_id": "s1",
            "session": {"generation": GEN}, "operation": operation(), "authority": authority()
        }));
        assert!(validate(&good).is_ok());

        // Wire 0.6: a version-less control message is rejected too — every kind
        // now requires `ncp_version` (the spec's line, finally enforced).
        assert!(
            validate(&serde_json::json!({"kind": "step_request", "session_id": "s1"})).is_err(),
            "missing ncp_version must be rejected"
        );

        // Unknown kinds and non-objects are rejected.
        assert!(validate(&serde_json::json!({"kind": "not_a_real_kind"})).is_err());
        assert!(validate(&serde_json::json!([1, 2, 3])).is_err());
        assert!(
            validate(&serde_json::json!({"session_id": "s1"})).is_err(),
            "no kind -> err"
        );

        // Forward-compatible: unknown extra fields are still accepted.
        let fwd = seal_mutation(serde_json::json!({
            "kind": "step_request", "ncp_version": NCP_VERSION, "session_id": "s1",
            "session": {"generation": GEN}, "operation": operation(), "authority": authority(),
            "future": 7
        }));
        assert!(validate(&fwd).is_ok());
    }

    /// `validate()` pins the scientific-boundary discriminators: a frame asserting
    /// it is a calibrated posterior (or NOT sim output) is rejected, not trusted.
    #[test]
    fn validate_pins_scientific_boundary() {
        // observation_frame: a tampered calibrated_posterior=true is rejected.
        // (Fixtures carry the wire-0.6 required ncp_version + seq.)
        let lie = serde_json::json!({
            "kind": "observation_frame", "ncp_version": NCP_VERSION, "session_id": "s1",
            "stream": {"epoch": EPOCH, "seq": 1}, "session": {"generation": GEN}, "records": {}, "calibrated_posterior": true,
            "is_simulation_output": true
        });
        assert!(
            validate(&lie).is_err(),
            "calibrated_posterior=true must be rejected"
        );
        let lie2 = serde_json::json!({
            "kind": "observation_frame", "ncp_version": NCP_VERSION, "session_id": "s1",
            "stream": {"epoch": EPOCH, "seq": 1}, "session": {"generation": GEN}, "records": {}, "calibrated_posterior": false,
            "is_simulation_output": false
        });
        assert!(
            validate(&lie2).is_err(),
            "is_simulation_output=false must be rejected"
        );
        // The honest default values pass; absent boundary fields also pass.
        let ok = serde_json::json!({
            "kind": "observation_frame", "ncp_version": NCP_VERSION, "session_id": "s1",
            "stream": {"epoch": EPOCH, "seq": 1}, "session": {"generation": GEN}, "records": {}, "calibrated_posterior": false,
            "is_simulation_output": true
        });
        assert!(validate(&ok).is_ok());
        // The honesty fields are mandatory in wire 0.7; omission must not be
        // silently repaired with serde defaults.
        let absent = serde_json::json!({
            "kind": "observation_frame", "ncp_version": NCP_VERSION, "session_id": "s1", "seq": 0
        });
        assert!(validate(&absent).is_err());

        // session_opened: the pin reaches into the nested provenance object...
        let bad_prov = serde_json::json!({
            "kind": "session_opened", "ncp_version": NCP_VERSION, "session_id": "s1",
            "ok": true, "state_version": 1, "backend": "b", "session": {"generation": GEN}, "error": null,
            "provenance": {"network_ref": "n", "backend": "b", "calibrated_posterior": false,
                           "is_simulation_output": false, "advisory_only": true},
            "identity": body_identity(), "security_profile": "dev-loopback-insecure",
            "security_state_digest": "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab",
            "gateway_permitted": false
        });
        assert!(
            validate(&bad_prov).is_err(),
            "tampered provenance.is_simulation_output must be rejected"
        );
        // ...and a null provenance (the nullable wire form) is simply skipped.
        let null_prov = serde_json::json!({
            "kind": "session_opened", "ncp_version": NCP_VERSION, "session_id": "s1",
            "ok": false, "state_version": 0, "backend": "unknown", "error": "backend unavailable", "provenance": null,
            "identity": body_identity(), "security_profile": "dev-loopback-insecure",
            "security_state_digest": "8b65c88deecefc922a191ea646b1a2b9602f733c61d7649e778d0d7087bc15ab",
            "gateway_permitted": false
        });
        assert!(validate(&null_prov).is_ok());
    }
}
