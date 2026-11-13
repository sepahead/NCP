//! Application contracts and their schemas (specification section 11).

use crate::frame::{self, Dtype, FrameError};
use crate::messages::is_name;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fmt;

const TYPES: [&str; 7] = [
    "null", "boolean", "integer", "number", "string", "array", "object",
];
const NUMBER_KEYWORDS: [&str; 4] = ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"];
const COUNT_KEYWORDS: [&str; 4] = ["minLength", "maxLength", "minItems", "maxItems"];
const OTHER_KEYWORDS: [&str; 9] = [
    "type",
    "enum",
    "const",
    "items",
    "properties",
    "required",
    "additionalProperties",
    "ncp.array",
    "description",
];

/// A document that is not a valid NCP contract (section 11).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ContractError(pub String);

impl fmt::Display for ContractError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "not a valid NCP contract: {}", self.0)
    }
}

impl std::error::Error for ContractError {}

impl From<ContractError> for FrameError {
    fn from(error: ContractError) -> FrameError {
        FrameError(error.to_string())
    }
}

fn fail<T>(text: String) -> Result<T, ContractError> {
    Err(ContractError(text))
}

fn is_number(value: &Value) -> bool {
    value.is_number()
}

/// Check that `schema` uses only the keywords of section 11.1 with values of their kind.
pub fn compile_schema(schema: &Value, path: &str) -> Result<(), ContractError> {
    let Some(object) = schema.as_object() else {
        return fail(format!("{path}: a schema is an object"));
    };
    for name in object.keys() {
        let known = NUMBER_KEYWORDS.contains(&name.as_str())
            || COUNT_KEYWORDS.contains(&name.as_str())
            || OTHER_KEYWORDS.contains(&name.as_str())
            || name == "title";
        if !known {
            return fail(format!("{path}: unknown schema keyword {name:?}"));
        }
    }
    if let Some(kind) = object.get("type") {
        let kinds: Vec<&Value> = match kind {
            Value::Array(items) => items.iter().collect(),
            other => vec![other],
        };
        let names: Vec<&str> = kinds.iter().filter_map(|k| k.as_str()).collect();
        let mut distinct = names.clone();
        distinct.sort_unstable();
        distinct.dedup();
        if kinds.is_empty()
            || names.len() != kinds.len()
            || names.iter().any(|n| !TYPES.contains(n))
            || distinct.len() != names.len()
        {
            return fail(format!("{path}.type: one of {TYPES:?} or a list of them"));
        }
    }
    if object.get("enum").is_some_and(|v| !v.is_array()) {
        return fail(format!("{path}.enum: an array"));
    }
    for keyword in NUMBER_KEYWORDS {
        if object.get(keyword).is_some_and(|v| !is_number(v)) {
            return fail(format!("{path}.{keyword}: a number"));
        }
    }
    for keyword in COUNT_KEYWORDS {
        if object.get(keyword).is_some_and(|v| !v.is_u64()) {
            return fail(format!("{path}.{keyword}: an integer, 0 or larger"));
        }
    }
    if let Some(items) = object.get("items") {
        compile_schema(items, &format!("{path}.items"))?;
    }
    if let Some(properties) = object.get("properties") {
        let Some(properties) = properties.as_object() else {
            return fail(format!("{path}.properties: an object of schemas"));
        };
        for (name, member) in properties {
            compile_schema(member, &format!("{path}.properties.{name}"))?;
        }
    }
    if let Some(required) = object.get("required") {
        let names: Option<Vec<&str>> = required
            .as_array()
            .and_then(|items| items.iter().map(Value::as_str).collect());
        let distinct = names.as_ref().is_some_and(|names| {
            let mut sorted = names.clone();
            sorted.sort_unstable();
            sorted.dedup();
            sorted.len() == names.len()
        });
        if !distinct {
            return fail(format!(
                "{path}.required: an array of distinct member names"
            ));
        }
    }
    if let Some(extra) = object.get("additionalProperties") {
        if extra != &Value::Bool(false) {
            compile_schema(extra, &format!("{path}.additionalProperties"))?;
        }
    }
    if let Some(spec) = object.get("ncp.array") {
        let ok = spec.as_object().is_some_and(|spec| {
            spec.len() == 2
                && match spec.get("dtype") {
                    Some(Value::String(d)) => Dtype::parse(d).is_some(),
                    Some(Value::Array(items)) => {
                        !items.is_empty()
                            && items
                                .iter()
                                .all(|d| d.as_str().and_then(Dtype::parse).is_some())
                    }
                    _ => false,
                }
                && spec
                    .get("shape")
                    .and_then(Value::as_array)
                    .is_some_and(|shape| shape.iter().all(|n| n.is_null() || n.is_u64()))
        });
        if !ok {
            return fail(format!(
                "{path}.ncp.array: an object with the members dtype and shape"
            ));
        }
    }
    for keyword in ["description", "title"] {
        if object.get(keyword).is_some_and(|v| !v.is_string()) {
            return fail(format!("{path}.{keyword}: a string"));
        }
    }
    Ok(())
}

/// The array reference of a decoded value, if it is one (section 5).
fn array_spec(value: &Value) -> Option<&serde_json::Map<String, Value>> {
    let object = value.as_object()?;
    if object.len() != 1 {
        return None;
    }
    object.get(frame::ARRAY_KEY)?.as_object()
}

/// The JSON type of a decoded value (section 11.1). An array reference is an object.
pub fn json_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(n) if n.is_u64() || n.is_i64() => "integer",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

/// Equality of section 11.1: the same JSON type and the same value. An array of section 5 never
/// equals a value written in a contract.
pub fn json_equal(a: &Value, b: &Value) -> bool {
    if json_type(a) != json_type(b) || array_spec(a).is_some() || array_spec(b).is_some() {
        return false;
    }
    match (a, b) {
        (Value::Array(x), Value::Array(y)) => {
            x.len() == y.len() && x.iter().zip(y).all(|(p, q)| json_equal(p, q))
        }
        (Value::Object(x), Value::Object(y)) => {
            x.len() == y.len()
                && x.iter()
                    .all(|(k, v)| y.get(k).is_some_and(|w| json_equal(v, w)))
        }
        (Value::Number(x), Value::Number(y)) => {
            match (x.as_i64(), y.as_i64(), x.as_u64(), y.as_u64()) {
                (Some(p), Some(q), _, _) => p == q,
                (_, _, Some(p), Some(q)) => p == q,
                _ => x.as_f64() == y.as_f64(),
            }
        }
        _ => a == b,
    }
}

fn number(value: &Value) -> f64 {
    value.as_f64().unwrap_or(f64::NAN)
}

/// None if `value` matches `schema` (section 11.1), otherwise the first mismatch.
pub fn check(schema: &Value, value: &Value, path: &str) -> Option<String> {
    let kind = json_type(value);
    if let Some(allowed) = schema.get("type") {
        let allowed: Vec<&str> = match allowed {
            Value::Array(items) => items.iter().filter_map(Value::as_str).collect(),
            other => other.as_str().into_iter().collect(),
        };
        if !allowed.contains(&kind) && !(kind == "integer" && allowed.contains(&"number")) {
            return Some(format!(
                "{path}: expected {}, found {kind}",
                allowed.join(" or ")
            ));
        }
    }
    if let Some(options) = schema.get("enum").and_then(Value::as_array) {
        if !options.iter().any(|option| json_equal(value, option)) {
            return Some(format!("{path}: not one of the allowed values"));
        }
    }
    if let Some(constant) = schema.get("const") {
        if !json_equal(value, constant) {
            return Some(format!("{path}: not the required value"));
        }
    }
    let spec = array_spec(value);
    if schema.get("ncp.array").is_some() && spec.is_none() {
        return Some(format!("{path}: expected an array of section 5"));
    }
    match kind {
        "integer" | "number" => {
            let v = number(value);
            let bound = |key: &str| schema.get(key).map(number);
            if bound("minimum").is_some_and(|m| v < m) {
                return Some(format!("{path}: below the minimum {}", schema["minimum"]));
            }
            if bound("maximum").is_some_and(|m| v > m) {
                return Some(format!("{path}: above the maximum {}", schema["maximum"]));
            }
            if bound("exclusiveMinimum").is_some_and(|m| v <= m) {
                return Some(format!("{path}: not above {}", schema["exclusiveMinimum"]));
            }
            if bound("exclusiveMaximum").is_some_and(|m| v >= m) {
                return Some(format!("{path}: not below {}", schema["exclusiveMaximum"]));
            }
        }
        "string" => {
            let count = value.as_str().map_or(0, |s| s.chars().count()) as u64;
            if schema["minLength"].as_u64().is_some_and(|m| count < m) {
                return Some(format!(
                    "{path}: shorter than {} characters",
                    schema["minLength"]
                ));
            }
            if schema["maxLength"].as_u64().is_some_and(|m| count > m) {
                return Some(format!(
                    "{path}: longer than {} characters",
                    schema["maxLength"]
                ));
            }
        }
        "array" => {
            let items = value.as_array().map_or(&[][..], Vec::as_slice);
            let count = items.len() as u64;
            if schema["minItems"].as_u64().is_some_and(|m| count < m) {
                return Some(format!("{path}: fewer than {} items", schema["minItems"]));
            }
            if schema["maxItems"].as_u64().is_some_and(|m| count > m) {
                return Some(format!("{path}: more than {} items", schema["maxItems"]));
            }
            if let Some(item_schema) = schema.get("items") {
                for (index, item) in items.iter().enumerate() {
                    if let Some(error) = check(item_schema, item, &format!("{path}[{index}]")) {
                        return Some(error);
                    }
                }
            }
        }
        "object" => {
            if let Some(spec) = spec {
                return check_array(schema, spec, path);
            }
            let object = value.as_object()?;
            if let Some(required) = schema.get("required").and_then(Value::as_array) {
                for name in required.iter().filter_map(Value::as_str) {
                    if !object.contains_key(name) {
                        return Some(format!("{path}: the member {name:?} is missing"));
                    }
                }
            }
            let properties = schema.get("properties").and_then(Value::as_object);
            let extra = schema.get("additionalProperties");
            for (name, member) in object {
                let error = if let Some(member_schema) = properties.and_then(|p| p.get(name)) {
                    check(member_schema, member, &format!("{path}.{name}"))
                } else if extra == Some(&Value::Bool(false)) {
                    return Some(format!("{path}: the member {name:?} is not allowed"));
                } else if let Some(extra_schema) = extra {
                    check(extra_schema, member, &format!("{path}.{name}"))
                } else {
                    None
                };
                if error.is_some() {
                    return error;
                }
            }
        }
        _ => {}
    }
    None
}

/// Object keywords do not constrain an array of section 5; only `ncp.array` does.
fn check_array(
    schema: &Value,
    spec: &serde_json::Map<String, Value>,
    path: &str,
) -> Option<String> {
    let wanted = schema.get("ncp.array")?;
    let dtype = spec
        .get("dtype")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let dtypes: Vec<&str> = match &wanted["dtype"] {
        Value::Array(items) => items.iter().filter_map(Value::as_str).collect(),
        other => other.as_str().into_iter().collect(),
    };
    if !dtypes.contains(&dtype) {
        return Some(format!(
            "{path}: dtype {dtype} is not {}",
            dtypes.join(" or ")
        ));
    }
    let shape: Vec<u64> = spec
        .get("shape")
        .and_then(Value::as_array)
        .map(|items| items.iter().filter_map(Value::as_u64).collect())
        .unwrap_or_default();
    let pattern = wanted["shape"].as_array().map_or(&[][..], Vec::as_slice);
    let matches = pattern.len() == shape.len()
        && pattern
            .iter()
            .zip(&shape)
            .all(|(p, n)| p.is_null() || p.as_u64() == Some(*n));
    if !matches {
        return Some(format!(
            "{path}: shape {shape:?} does not match {}",
            wanted["shape"]
        ));
    }
    None
}

fn check_schemas(value: &Value, path: &str, parts: &[&str]) -> Result<(), ContractError> {
    let Some(object) = value.as_object() else {
        return fail(format!(
            "{path}: the description must be an object (section 11, rule 2)"
        ));
    };
    if let Some(schemas) = object.get("ncp.schema") {
        let Some(schemas) = schemas.as_object() else {
            return fail(format!("{path}.ncp.schema: an object"));
        };
        for (part, schema) in schemas {
            if !parts.contains(&part.as_str()) {
                return fail(format!(
                    "{path}.ncp.schema: an object with the members {parts:?}"
                ));
            }
            compile_schema(schema, &format!("{path}.ncp.schema.{part}"))?;
        }
    }
    Ok(())
}

/// A contract document and its identity: the SHA-256 digest of its exact bytes (section 11).
#[derive(Debug, Clone, PartialEq)]
pub struct Contract {
    /// The exact bytes.
    pub data: Vec<u8>,
    /// The identity.
    pub identity: String,
    /// The application name.
    pub application: String,
    /// The contract version.
    pub version: String,
    /// The operation names.
    pub operations: Vec<String>,
    /// The stream type names.
    pub streams: Vec<String>,
    /// The parsed document.
    pub document: Value,
}

impl Contract {
    /// Parse and check a contract document (section 11).
    pub fn from_bytes(data: Vec<u8>) -> Result<Contract, ContractError> {
        let document = frame::loads(&data).map_err(|e| ContractError(e.0))?;
        let Some(object) = document.as_object() else {
            return fail("the document is not an object".into());
        };
        if !(object.get("ncp_contract").is_some_and(Value::is_u64) && object["ncp_contract"] == 1) {
            return fail("ncp_contract must be the integer 1".into());
        }
        for member in ["application", "version"] {
            let ok = object
                .get(member)
                .and_then(Value::as_str)
                .is_some_and(|s| (1..=128).contains(&s.chars().count()));
            if !ok {
                return fail(format!("{member} must be a string of 1 to 128 characters"));
            }
        }
        let (Some(operations), Some(streams)) = (
            object.get("operations").and_then(Value::as_object),
            object.get("streams").and_then(Value::as_object),
        ) else {
            return fail("operations and streams must be objects".into());
        };
        for (name, value) in operations {
            if !is_name(name) || name == "open" || name == "close" || name.starts_with("ncp.") {
                return fail(format!(
                    "operation name {name:?} is not allowed (section 11, rule 1)"
                ));
            }
            check_schemas(value, &format!("operations.{name}"), &["request", "result"])?;
        }
        for (name, value) in streams {
            if !is_name(name) {
                return fail(format!(
                    "stream type name {name:?} is not allowed (section 11, rule 1)"
                ));
            }
            check_schemas(value, &format!("streams.{name}"), &["body"])?;
        }
        Ok(Contract {
            identity: frame::hex(&Sha256::digest(&data)),
            application: object["application"]
                .as_str()
                .unwrap_or_default()
                .to_owned(),
            version: object["version"].as_str().unwrap_or_default().to_owned(),
            operations: operations.keys().cloned().collect(),
            streams: streams.keys().cloned().collect(),
            document,
            data,
        })
    }

    /// Read and check a contract file.
    pub fn load(path: impl AsRef<std::path::Path>) -> Result<Contract, ContractError> {
        let data = std::fs::read(path).map_err(|e| ContractError(e.to_string()))?;
        Contract::from_bytes(data)
    }

    /// Whether the contract has the operation `op`.
    pub fn has_operation(&self, op: &str) -> bool {
        self.operations.iter().any(|name| name == op)
    }

    /// The schema of an operation's `request` or `result`, if any.
    pub fn schema(&self, op: &str, part: &str) -> Option<&Value> {
        self.document["operations"]
            .get(op)?
            .get("ncp.schema")?
            .get(part)
    }

    /// None if the body matches the operation's request schema, otherwise the mismatch.
    pub fn check_request(&self, op: &str, body: &Value) -> Option<String> {
        check(self.schema(op, "request")?, body, "$")
    }

    /// None if the result matches the operation's result schema, otherwise the mismatch.
    pub fn check_result(&self, op: &str, body: &Value) -> Option<String> {
        check(self.schema(op, "result")?, body, "$")
    }

    /// None if the body matches the stream type's body schema, otherwise the mismatch.
    pub fn check_stream(&self, name: &str, body: &Value) -> Option<String> {
        let schema = self.document["streams"]
            .get(name)?
            .get("ncp.schema")?
            .get("body")?;
        check(schema, body, "$")
    }
}
