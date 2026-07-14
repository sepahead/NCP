//! Generate the JSON-Schema projection of the NCP wire **from the serde reference
//! types** — NCP owns its schemas. The normative contract remains proto-first;
//! the `ncp-core` serde types are the
//! conformance-locked reference implementation of `proto/ncp.proto`, and their
//! `#[serde(rename)]` carry the enum wire strings (`"V_m"`, not the proto constant
//! `V_M`), so deriving the schema from them is faithful and machine-driven (no
//! comment-parsing, no downstream-consumer dependency).
//!
//! Usage:
//!   cargo run -p ncp-core --features schema --bin gen-schemas -- [out_dir]
//! Writes `<out_dir>/<kind>.schema.json` + `index.json`. `out_dir` defaults to the
//! repository's sibling `../schemas` when present, otherwise to the packaged
//! `testdata/schemas` snapshot.

use schemars::schema_for;
use serde_json::{Map, Value};
use std::collections::HashSet;
use std::fs;
use std::path::PathBuf;

// The only path-semantically safe same-major additive enum. Every unknown Mode
// is non-authorizing and governed as HOLD. Other forward-string enums retain
// unknown values in Rust for diagnostics/relays, but their JSON-Schema projection
// remains closed because at least one path requires interpretation.
const OPEN_ENUMS: &[&str] = &["Mode"];

const NESTED_REQUIRED: &[(&str, &[&str])] = &[
    (
        "AuthorityLease",
        &[
            "expires_at_utc_ms",
            "holder_entity_id",
            "holder_principal_id",
            "issued_at_utc_ms",
            "issuer_principal_id",
            "lease_id",
            "session_epoch",
            "term",
        ],
    ),
    ("ChannelSpec", &["kind", "name", "requirement"]),
    ("EntityBinding", &["direction", "entity", "port"]),
    ("EntityRef", &["path", "role"]),
    ("GatewayAttribution", &["gateway_id", "source_wire"]),
    ("NetworkRef", &["kind", "ref"]),
    ("Observation", &["observable", "port", "target"]),
    (
        "IdentityClaim",
        &["entity_id", "plane", "principal_id", "role"],
    ),
    (
        "OperationContext",
        &[
            "deadline_utc_ms",
            "expected_state_version",
            "operation_id",
            "request_digest",
            "retry",
            "session_epoch",
        ],
    ),
    ("RecordTarget", &["observable", "port", "target"]),
    (
        "ResponderReceipt",
        &[
            "committed_at_utc_ms",
            "operation_id",
            "outcome",
            "request_digest",
            "responder_entity_id",
            "responder_principal_id",
            "result_digest",
            "state_version",
        ],
    ),
    ("SafetyLimits", &["command_timeout_ms"]),
    ("SessionRef", &["generation"]),
    (
        "SimProvenance",
        &[
            "advisory_only",
            "backend",
            "calibrated_posterior",
            "is_simulation_output",
            "network_ref",
        ],
    ),
    ("StimulusTarget", &["kind", "port", "target"]),
    ("StreamPosition", &["epoch", "seq"]),
];

fn kind_for_title(title: &str) -> Option<&'static str> {
    Some(match title {
        "Capabilities" => "capabilities",
        "OpenSession" => "open_session",
        "SessionOpened" => "session_opened",
        "CloseSession" => "close_session",
        "SessionClosed" => "session_closed",
        "ErrorFrame" => "error",
        "RunRequest" => "run_request",
        "StepRequest" => "step_request",
        "SensorFrame" => "sensor_frame",
        "StimulusFrame" => "stimulus_frame",
        "ObservationFrame" => "observation_frame",
        "CommandFrame" => "command_frame",
        "ControlStatus" => "control_status",
        "LinkStatus" => "link_status",
        _ => return None,
    })
}

/// JSON-Schema regular expression for one canonical unsigned decimal `u64`.
///
/// The shorter branches cover zero and every 1--19 digit value. The generated
/// 20-digit branches compare lexicographically with `u64::MAX`, which is valid
/// because both operands have equal width. This keeps the published string
/// schema exactly aligned with the Rust/TypeScript parser instead of accepting
/// an arbitrary-length digit string and relying on a later semantic check.
fn canonical_u64_pattern() -> String {
    let maximum = u64::MAX.to_string();
    let mut branches = vec![
        "0".to_owned(),
        format!("[1-9][0-9]{{0,{}}}", maximum.len() - 2),
    ];

    for (index, byte) in maximum.bytes().enumerate().skip(1) {
        let digit = byte - b'0';
        if digit == 0 {
            continue;
        }
        let prefix = &maximum[..index];
        let lower_digit = if digit == 1 {
            "0".to_owned()
        } else {
            format!("[0-{}]", digit - 1)
        };
        let suffix_len = maximum.len() - index - 1;
        let suffix = if suffix_len == 0 {
            String::new()
        } else {
            format!("[0-9]{{{suffix_len}}}")
        };
        branches.push(format!("{prefix}{lower_digit}{suffix}"));
    }
    branches.push(maximum);
    format!("(?:{})", branches.join("|"))
}

/// Exact compatible stable-line grammar for every message `ncp_version`.
///
/// Wire versions are canonical unsigned decimal `u64` components with no
/// leading zeroes. The candidate is stable major 1, so the schema accepts the
/// shorthand `1` and every additive-compatible `1.<minor>` while rejecting a
/// different major even when that version is otherwise well formed.
fn compatible_ncp_version_pattern() -> String {
    let major = ncp_core::NCP_VERSION
        .split_once('.')
        .map_or(ncp_core::NCP_VERSION, |(major, _)| major);
    assert!(
        major != "0" && major.bytes().all(|byte| byte.is_ascii_digit()) && !major.starts_with('0'),
        "NCP_VERSION major is not a canonical stable unsigned decimal"
    );
    // JSON Schema uses ECMA-262 regex semantics, while the dependency-free
    // conformance gate evaluates this portable subset with Python `re` (whose
    // `$` also matches before a final newline). `(?![\s\S])` is an absolute-end
    // assertion in both engines, so their decisions cannot diverge there.
    format!(r"^{major}(?:\.{})?(?![\s\S])", canonical_u64_pattern())
}

fn pin_message_contract(schema: &mut Value, kind: &str) {
    let Some(obj) = schema.as_object_mut() else {
        return;
    };
    if let Some(properties) = obj.get_mut("properties").and_then(Value::as_object_mut) {
        if let Some(field) = properties.get_mut("kind").and_then(Value::as_object_mut) {
            field.insert("const".into(), Value::String(kind.into()));
        }
        if let Some(field) = properties
            .get_mut("ncp_version")
            .and_then(Value::as_object_mut)
        {
            field.remove("const");
            field.insert(
                "pattern".into(),
                Value::String(compatible_ncp_version_pattern()),
            );
        }
        if kind == "error" {
            if let Some(field) = properties.get_mut("code").and_then(Value::as_object_mut) {
                field.insert(
                    "enum".into(),
                    Value::Array(
                        ncp_core::REGISTERED_ERROR_CODES
                            .iter()
                            .map(|code| Value::String((*code).into()))
                            .collect(),
                    ),
                );
            }
        }
    }
    if let Some(required) = ncp_core::required_fields(kind) {
        obj.insert(
            "required".into(),
            Value::Array(
                required
                    .iter()
                    .map(|field| Value::String((*field).into()))
                    .collect(),
            ),
        );
    }
}

fn enum_values(schema: &Value) -> Vec<Value> {
    if let Some(values) = schema.get("enum").and_then(Value::as_array) {
        return values.clone();
    }
    let mut values = Vec::new();
    for branch in schema
        .get("oneOf")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(branch_values) = branch.get("enum").and_then(Value::as_array) {
            values.extend(branch_values.iter().cloned());
        } else if let Some(value) = branch.get("const") {
            values.push(value.clone());
        }
    }
    values
}

fn make_forward_enums_open(schema: &mut Value) {
    let Some(defs) = schema.get_mut("$defs").and_then(Value::as_object_mut) else {
        return;
    };
    for name in OPEN_ENUMS {
        let Some(node) = defs.get_mut(*name) else {
            continue;
        };
        let known = enum_values(node);
        assert!(!known.is_empty(), "{name} schema has no known wire values");
        let description = node.get("description").cloned();
        let mut open = Map::new();
        if let Some(description) = description {
            open.insert("description".into(), description);
        }
        open.insert("type".into(), Value::String("string".into()));
        open.insert("minLength".into(), Value::from(1));
        open.insert("x-ncp-known-values".into(), Value::Array(known));
        *node = Value::Object(open);
    }
}

fn enforce_projection_invariants(schema: &mut Value) {
    match schema {
        Value::Array(values) => {
            for value in values {
                enforce_projection_invariants(value);
            }
        }
        Value::Object(obj) => {
            if matches!(
                obj.get("format").and_then(Value::as_str),
                Some("int64" | "uint64")
            ) {
                let minimum = if obj.get("format").and_then(Value::as_str) == Some("uint64") {
                    0
                } else {
                    ncp_core::JSON_SAFE_INTEGER_MIN
                };
                obj.insert("minimum".into(), Value::from(minimum));
                obj.insert(
                    "maximum".into(),
                    Value::from(ncp_core::JSON_SAFE_INTEGER_MAX),
                );
            }
            if let Some(properties) = obj.get_mut("properties").and_then(Value::as_object_mut) {
                if let Some(field) = properties.get_mut("horizon").and_then(Value::as_object_mut) {
                    field.insert("maxItems".into(), Value::from(ncp_core::MAX_HORIZON_STEPS));
                }
                if let Some(field) = properties
                    .get_mut("calibrated_posterior")
                    .and_then(Value::as_object_mut)
                {
                    field.insert("const".into(), Value::Bool(false));
                }
                if let Some(field) = properties
                    .get_mut("is_simulation_output")
                    .and_then(Value::as_object_mut)
                {
                    field.insert("const".into(), Value::Bool(true));
                }
            }
            for value in obj.values_mut() {
                enforce_projection_invariants(value);
            }
        }
        _ => {}
    }
}

fn declared_type_allows_null(node: &Map<String, Value>) -> bool {
    match node.get("type") {
        Some(Value::String(kind)) => kind == "null",
        Some(Value::Array(kinds)) => kinds.iter().any(|kind| kind.as_str() == Some("null")),
        // `$ref` / `anyOf` nodes need resolution to answer this question. Leave
        // their valid optional defaults alone; the focused default guard checks
        // every directly declared primitive type.
        _ => true,
    }
}

/// Schemars derives annotations from the deserialize-side sentinel functions
/// used to *detect* missing required fields. Those sentinels are deliberately
/// invalid wire values (`kind=""`, reversed honesty booleans, NaN TTL), so they
/// must never be advertised as JSON-Schema defaults that a code generator might
/// apply. Required fields have no wire default; const fields are discriminators,
/// not fill-ins. Keep only genuine optional, type-compatible defaults such as
/// `CommandFrame.mode = "hold"`.
fn sanitize_default_annotations(schema: &mut Value) {
    match schema {
        Value::Array(values) => {
            for value in values {
                sanitize_default_annotations(value);
            }
        }
        Value::Object(obj) => {
            let remove_local_default = obj.contains_key("const")
                || (obj.get("default") == Some(&Value::Null) && !declared_type_allows_null(obj));
            if remove_local_default {
                obj.remove("default");
            }

            let required: HashSet<String> = obj
                .get("required")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect();
            if let Some(properties) = obj.get_mut("properties").and_then(Value::as_object_mut) {
                for field in &required {
                    if let Some(node) = properties.get_mut(field).and_then(Value::as_object_mut) {
                        node.remove("default");
                    }
                }
            }

            for value in obj.values_mut() {
                sanitize_default_annotations(value);
            }
        }
        _ => {}
    }
}

fn pin_nested_messages(schema: &mut Value) {
    let Some(defs) = schema.get_mut("$defs").and_then(Value::as_object_mut) else {
        return;
    };
    for (title, node) in defs {
        if let Some(kind) = kind_for_title(title) {
            pin_message_contract(node, kind);
        }
        if let Some((_, required)) = NESTED_REQUIRED.iter().find(|(name, _)| *name == title) {
            node.as_object_mut()
                .expect("nested schema is an object")
                .insert(
                    "required".into(),
                    Value::Array(
                        required
                            .iter()
                            .map(|field| Value::String((*field).into()))
                            .collect(),
                    ),
                );
        }
    }
}

macro_rules! kinds {
    ($($name:literal => $ty:ty),+ $(,)?) => {
        vec![ $( ($name, serde_json::to_value(schema_for!($ty)).expect("schema serializes")) ),+ ]
    };
}

fn main() {
    let out = std::env::args()
        .nth(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
            let workspace_schemas = manifest_dir.join("../schemas");
            if workspace_schemas.is_dir() {
                workspace_schemas
            } else {
                manifest_dir.join("testdata/schemas")
            }
        });
    fs::create_dir_all(&out).expect("create out_dir");

    // One schema per top-level wire message `kind`. Keep this list in lockstep with
    // the proto messages / the conformance corpus coverage gate.
    let mut schemas = kinds! {
        "capabilities"      => ncp_core::Capabilities,
        "open_session"      => ncp_core::OpenSession,
        "session_opened"    => ncp_core::SessionOpened,
        "close_session"     => ncp_core::CloseSession,
        "session_closed"    => ncp_core::SessionClosed,
        "error"             => ncp_core::ErrorFrame,
        "run_request"       => ncp_core::RunRequest,
        "step_request"      => ncp_core::StepRequest,
        "sensor_frame"      => ncp_core::SensorFrame,
        "stimulus_frame"    => ncp_core::StimulusFrame,
        "observation_frame" => ncp_core::ObservationFrame,
        "command_frame"     => ncp_core::CommandFrame,
        "control_status"    => ncp_core::ControlStatus,
        "link_status"       => ncp_core::LinkStatus,
    };

    let mut names: Vec<&str> = Vec::new();
    for (name, val) in &mut schemas {
        pin_message_contract(val, name);
        pin_nested_messages(val);
        make_forward_enums_open(val);
        enforce_projection_invariants(val);
        sanitize_default_annotations(val);
        let pretty = serde_json::to_string_pretty(val).expect("pretty json");
        fs::write(out.join(format!("{name}.schema.json")), pretty + "\n").expect("write schema");
        names.push(name);
    }
    names.sort_unstable();

    let index = serde_json::json!({
        "ncp_version": ncp_core::NCP_VERSION,
        "messages": names,
        "note": "Generated from the ncp-core serde reference types \
                 (cargo run --features schema --bin gen-schemas); do not edit by hand.",
    });
    fs::write(
        out.join("index.json"),
        serde_json::to_string_pretty(&index).expect("pretty index") + "\n",
    )
    .expect("write index");

    eprintln!(
        "wrote {} schemas + index.json to {}",
        schemas.len(),
        out.display()
    );
}
