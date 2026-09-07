//! Closed generic modular envelopes. Application types are installed by the host.
//! This SDK surface supplies no installed body, capture, neural, or monitor schema.

use std::fmt;
use std::io::Write;

use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use crate::bounded_json::{preflight, MAX_FINITE_NUMBER_MAGNITUDE, MAX_NESTING_DEPTH};
use crate::modular_buffer::{
    BufferBinding, BufferChunk, BufferManifest, BufferRef, DIGEST_STAGING_BYTES, FRAME_BYTES,
    MAX_ID,
};

pub const REQUEST_SCHEMA: &str = "ncp.modular.request.v1";
pub const RESPONSE_SCHEMA: &str = "ncp.modular.response.v1";
pub const PROFILE_DOMAIN: &str = "ncp.modular.profile.v1";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModularError {
    Wire,
    Binding,
    Capacity,
    Retired,
    Execution(Diagnostic),
}
impl fmt::Display for ModularError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "modular owner error: {self:?}")
    }
}
impl std::error::Error for ModularError {}

pub fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub(crate) struct FrameWriter<'a> {
    pub bytes: &'a mut Vec<u8>,
}
impl Write for FrameWriter<'_> {
    fn write(&mut self, input: &[u8]) -> std::io::Result<usize> {
        if input.len() > FRAME_BYTES.saturating_sub(self.bytes.len()) {
            return Err(std::io::Error::other("modular frame capacity"));
        }
        self.bytes.extend_from_slice(input);
        Ok(input.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// Allocate the complete logical frame slot before its producer can execute.
pub(crate) fn frame_slot() -> Result<Vec<u8>, ModularError> {
    #[cfg(test)]
    if FRAME_ALLOCATION_FAILURE.with(|remaining| match remaining.get() {
        Some(0) => {
            remaining.set(None);
            true
        }
        Some(count) => {
            remaining.set(Some(count - 1));
            false
        }
        None => false,
    }) {
        return Err(ModularError::Capacity);
    }
    let mut bytes = Vec::new();
    bytes
        .try_reserve_exact(FRAME_BYTES)
        .map_err(|_| ModularError::Capacity)?;
    Ok(bytes)
}

#[cfg(test)]
thread_local! { static FRAME_ALLOCATION_FAILURE: std::cell::Cell<Option<usize>> = const { std::cell::Cell::new(None) }; }
#[cfg(test)]
pub(crate) struct FrameAllocationFault;
#[cfg(test)]
impl Drop for FrameAllocationFault {
    fn drop(&mut self) {
        FRAME_ALLOCATION_FAILURE.with(|remaining| remaining.set(None));
    }
}
#[cfg(test)]
pub(crate) fn fail_frame_allocation_after(successes: usize) -> FrameAllocationFault {
    FRAME_ALLOCATION_FAILURE.with(|remaining| remaining.set(Some(successes)));
    FrameAllocationFault
}

/// Preflight is applied before allocating the generic parsed representation.
pub fn parse_value(bytes: &[u8]) -> Result<Value, ModularError> {
    if bytes.is_empty() || bytes.len() > FRAME_BYTES {
        return Err(ModularError::Capacity);
    }
    preflight(bytes).map_err(|_| ModularError::Wire)?;
    serde_json::from_slice(bytes).map_err(|_| ModularError::Wire)
}

fn check_fixed_binding(value: &Value, expected: &BufferBinding) -> Result<(), ModularError> {
    expected.validate().map_err(|_| ModularError::Binding)?;
    let binding = value
        .get("binding")
        .and_then(Value::as_object)
        .ok_or(ModularError::Binding)?;
    let fields = [
        ("profile_digest", &expected.profile_digest),
        ("application_digest", &expected.application_digest),
        ("run_id", &expected.run_id),
        ("endpoint_id", &expected.endpoint_id),
        ("generation", &expected.generation),
    ];
    if binding.len() != fields.len()
        || fields.iter().any(|(key, expected)| {
            binding.get(*key).and_then(Value::as_str) != Some(expected.as_str())
        })
    {
        return Err(ModularError::Binding);
    }
    Ok(())
}

struct TypedHash {
    hash: Sha256,
    length: usize,
    sort_scratch: usize,
}
impl TypedHash {
    fn push(&mut self, bytes: &[u8]) -> Result<(), ModularError> {
        if bytes.len() > DIGEST_STAGING_BYTES - self.length {
            return Err(ModularError::Capacity);
        }
        self.hash.update(bytes);
        self.length += bytes.len();
        Ok(())
    }
    fn length(&mut self, length: usize) -> Result<(), ModularError> {
        self.push(&(length as u64).to_be_bytes())
    }
    fn string(&mut self, value: &str) -> Result<(), ModularError> {
        self.push(&[4])?;
        self.length(value.len())?;
        self.push(value.as_bytes())
    }
    fn value(
        &mut self,
        value: &Value,
        depth: usize,
        omit: Option<&str>,
    ) -> Result<(), ModularError> {
        if depth > MAX_NESTING_DEPTH {
            return Err(ModularError::Capacity);
        }
        match value {
            Value::Null => self.push(&[0]),
            Value::Bool(b) => self.push(&[if *b { 2 } else { 1 }]),
            Value::Number(n) => {
                if n.as_i64().is_some_and(|v| v.unsigned_abs() > MAX_ID)
                    || n.as_u64().is_some_and(|v| v > MAX_ID)
                {
                    return Err(ModularError::Wire);
                }
                let number = n
                    .as_f64()
                    .filter(|n| n.is_finite() && n.abs() <= MAX_FINITE_NUMBER_MAGNITUDE)
                    .ok_or(ModularError::Wire)?;
                self.push(&[3])?;
                self.push(&number.to_bits().to_be_bytes())
            }
            Value::String(s) => {
                if s.len() > 65_536 {
                    return Err(ModularError::Capacity);
                }
                self.string(s)
            }
            Value::Array(a) => {
                if a.len() > 65_536 {
                    return Err(ModularError::Capacity);
                }
                self.push(&[5])?;
                self.length(a.len())?;
                for item in a {
                    self.value(item, depth + 1, None)?;
                }
                Ok(())
            }
            Value::Object(o) => {
                // The preflight's 4,096-member ceiling bounds these borrowed keys.
                if o.len() > 4_096 || o.keys().any(|key| key.len() > 128) {
                    return Err(ModularError::Capacity);
                }
                let scratch = o.len() * std::mem::size_of::<(&String, &Value)>();
                if scratch > (DIGEST_STAGING_BYTES - 1_024).saturating_sub(self.sort_scratch) {
                    return Err(ModularError::Capacity);
                }
                self.sort_scratch += scratch;
                let mut entries = Vec::new();
                entries
                    .try_reserve_exact(o.len())
                    .map_err(|_| ModularError::Capacity)?;
                entries.extend(o.iter().filter(|(k, _)| Some(k.as_str()) != omit));
                entries.sort_unstable_by(|(a, _), (b, _)| a.as_bytes().cmp(b.as_bytes()));
                self.push(&[6])?;
                self.length(entries.len())?;
                for (key, item) in entries {
                    self.string(key)?;
                    self.value(item, depth + 1, None)?;
                }
                self.sort_scratch -= scratch;
                Ok(())
            }
        }
    }
}

/// Stream the bounded typed projection into SHA-256; never construct an oversized projection first.
pub fn typed_digest(
    domain: &str,
    value: &Value,
    omit: Option<&str>,
) -> Result<String, ModularError> {
    if !matches!(domain, REQUEST_SCHEMA | RESPONSE_SCHEMA | PROFILE_DOMAIN) {
        return Err(ModularError::Wire);
    }
    let mut output = TypedHash {
        hash: Sha256::new(),
        length: 0,
        sort_scratch: 0,
    };
    output.push(domain.as_bytes())?;
    output.push(&[0])?;
    output.value(value, 0, omit)?;
    Ok(output
        .hash
        .finalize()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect())
}

/// Seal a bounded typed projection. A borrowing caller must account for its live
/// original while this function constructs the single parsed representation.
pub(crate) fn seal_into<T: Serialize>(
    value: T,
    field: &str,
    domain: &str,
    bytes: &mut Vec<u8>,
) -> Result<(), ModularError> {
    bytes.clear();
    serde_json::to_writer(FrameWriter { bytes }, &value).map_err(|_| ModularError::Capacity)?;
    drop(value);
    let mut parsed = parse_value(bytes)?;
    let digest = typed_digest(domain, &parsed, Some(field))?;
    let object = parsed.as_object_mut().ok_or(ModularError::Wire)?;
    if !object.contains_key(field) {
        return Err(ModularError::Wire);
    }
    object.insert(field.into(), Value::String(digest));
    bytes.clear();
    serde_json::to_writer(FrameWriter { bytes }, &parsed).map_err(|_| ModularError::Capacity)?;
    preflight(bytes).map_err(|_| ModularError::Wire)?;
    Ok(())
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OperationName {
    Prepare,
    Application,
    BufferImportBegin,
    BufferAppend,
    BufferSeal,
    BufferAbort,
    BufferRead,
    BufferRelease,
    Finish,
    Abort,
    Result,
    Ack,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(
    tag = "kind",
    content = "data",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum Operation<P, C, I, F> {
    Prepare(P),
    Application(C),
    BufferImportBegin(I),
    BufferAppend(AppendInput),
    BufferSeal(SealInput),
    BufferAbort(ReferenceInput),
    BufferRead(ReadInput),
    BufferRelease(ReferenceInput),
    Finish(F),
    Abort(Empty),
}
impl<P, C, I, F> Operation<P, C, I, F> {
    pub fn name(&self) -> OperationName {
        match self {
            Self::Prepare(_) => OperationName::Prepare,
            Self::Application(_) => OperationName::Application,
            Self::BufferImportBegin(_) => OperationName::BufferImportBegin,
            Self::BufferAppend(_) => OperationName::BufferAppend,
            Self::BufferSeal(_) => OperationName::BufferSeal,
            Self::BufferAbort(_) => OperationName::BufferAbort,
            Self::BufferRead(_) => OperationName::BufferRead,
            Self::BufferRelease(_) => OperationName::BufferRelease,
            Self::Finish(_) => OperationName::Finish,
            Self::Abort(_) => OperationName::Abort,
        }
    }
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AppendInput {
    pub reference: BufferRef,
    pub chunk: BufferChunk,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReferenceInput {
    pub reference: BufferRef,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SealInput {
    pub reference: BufferRef,
    pub expected_import_request_digest: String,
    pub expected_source_manifest_digest: String,
}
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ReadInput {
    pub reference: BufferRef,
    pub expected_manifest_digest: String,
    pub index: usize,
}
#[derive(Debug, Default, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Empty {}

#[derive(Debug, Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command<O> {
    Execute {
        expected_predecessor_result_digest: Option<String>,
        operation: O,
    },
    Result {
        original_request_digest: String,
    },
    Ack {
        original_request_digest: String,
        result_digest: String,
    },
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Request<O> {
    pub schema: String,
    pub binding: BufferBinding,
    pub sequence: u64,
    pub command: Command<O>,
    pub request_digest: String,
}
impl<O: Serialize> Request<O> {
    /// Rejoin even a caller-mutated typed request to its complete digest.
    pub fn verify(&self, expected: &BufferBinding) -> Result<(), ModularError> {
        let mut bytes = frame_slot()?;
        self.verify_into(expected, &mut bytes)
    }

    fn verify_into(
        &self,
        expected: &BufferBinding,
        bytes: &mut Vec<u8>,
    ) -> Result<(), ModularError> {
        bytes.clear();
        serde_json::to_writer(FrameWriter { bytes }, self).map_err(|_| ModularError::Capacity)?;
        let value = parse_value(bytes)?;
        if self.schema != REQUEST_SCHEMA
            || self.sequence == 0
            || self.sequence > MAX_ID
            || !valid_digest(&self.request_digest)
            || typed_digest(REQUEST_SCHEMA, &value, Some("request_digest"))? != self.request_digest
        {
            return Err(ModularError::Wire);
        }
        self.binding.validate().map_err(|_| ModularError::Binding)?;
        if &self.binding != expected {
            return Err(ModularError::Binding);
        }
        match &self.command {
            Command::Execute {
                expected_predecessor_result_digest: Some(p),
                ..
            } if !valid_digest(p) => Err(ModularError::Wire),
            Command::Result {
                original_request_digest,
            } if !valid_digest(original_request_digest) => Err(ModularError::Wire),
            Command::Ack {
                original_request_digest,
                result_digest,
            } if !valid_digest(original_request_digest) || !valid_digest(result_digest) => {
                Err(ModularError::Wire)
            }
            _ => Ok(()),
        }
    }

    pub fn encode(
        binding: BufferBinding,
        sequence: u64,
        command: Command<O>,
    ) -> Result<Vec<u8>, ModularError> {
        binding.validate().map_err(|_| ModularError::Binding)?;
        if sequence == 0 || sequence > MAX_ID {
            return Err(ModularError::Wire);
        }
        let request = Self {
            schema: REQUEST_SCHEMA.into(),
            binding,
            sequence,
            command,
            request_digest: String::new(),
        };
        let mut bytes = frame_slot()?;
        seal_into(request, "request_digest", REQUEST_SCHEMA, &mut bytes)?;
        Ok(bytes)
    }
}
impl<O: Serialize + DeserializeOwned> Request<O> {
    pub fn decode(bytes: &[u8], expected: &BufferBinding) -> Result<Self, ModularError> {
        let mut scratch = frame_slot()?;
        Self::decode_with_import_identity(bytes, expected, &mut scratch).map(|(request, _)| request)
    }

    pub(crate) fn decode_with_import_identity(
        bytes: &[u8],
        expected: &BufferBinding,
        scratch: &mut Vec<u8>,
    ) -> Result<(Self, Option<String>), ModularError> {
        let value = parse_value(bytes)?;
        let claimed = value
            .get("request_digest")
            .and_then(Value::as_str)
            .ok_or(ModularError::Wire)?;
        if !valid_digest(claimed)
            || typed_digest(REQUEST_SCHEMA, &value, Some("request_digest"))? != claimed
        {
            return Err(ModularError::Wire);
        }
        // Fixed host identity and exact sequence precede every application decoder.
        check_fixed_binding(&value, expected)?;
        if value.get("schema").and_then(Value::as_str) != Some(REQUEST_SCHEMA)
            || !value
                .get("sequence")
                .and_then(Value::as_u64)
                .is_some_and(|v| (1..=MAX_ID).contains(&v))
        {
            return Err(ModularError::Wire);
        }
        let descriptor_digest = if value["command"]["kind"] == "execute"
            && value["command"]["operation"]["kind"] == "buffer_import_begin"
        {
            Some(typed_digest(
                PROFILE_DOMAIN,
                &value["command"]["operation"]["data"],
                None,
            )?)
        } else {
            None
        };
        let request: Self = serde_json::from_value(value).map_err(|_| ModularError::Wire)?;
        if request.schema != REQUEST_SCHEMA || request.sequence == 0 || request.sequence > MAX_ID {
            return Err(ModularError::Wire);
        }
        request
            .binding
            .validate()
            .map_err(|_| ModularError::Binding)?;
        if &request.binding != expected {
            return Err(ModularError::Binding);
        }
        match &request.command {
            Command::Execute {
                expected_predecessor_result_digest: Some(p),
                ..
            } if !valid_digest(p) => return Err(ModularError::Wire),
            Command::Result {
                original_request_digest,
            } if !valid_digest(original_request_digest) => return Err(ModularError::Wire),
            Command::Ack {
                original_request_digest,
                result_digest,
            } if !valid_digest(original_request_digest) || !valid_digest(result_digest) => {
                return Err(ModularError::Wire)
            }
            _ => {}
        }
        request.verify_into(expected, scratch)?;
        Ok((request, descriptor_digest))
    }
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Committed,
    RejectedBeforeExecution,
    NotAdmitted,
    Indeterminate,
    Unavailable,
    Acknowledged,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Code {
    Ok,
    Role,
    State,
    InvalidInput,
    Capacity,
    BufferUnavailable,
    Conflict,
    ResultPending,
    ExecutionUnknown,
    NoMatchingRetainedResult,
    ResultReleased,
}
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Diagnostic {
    Backend,
    InvalidOutput,
    Internal,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AckStamp {
    pub sequence: u64,
    pub original_request_digest: String,
    pub result_digest: String,
}

#[derive(Debug, Deserialize, Serialize, PartialEq)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Body<R, I, T> {
    Prepared { data: R },
    Application { data: R },
    ImportReserved { reference: BufferRef },
    ImportSealed { manifest: BufferManifest, data: I },
    Chunk { data: BufferChunk },
    BufferChanged { reference: BufferRef },
    Finished { data: T },
    Aborted {},
    Rejected {},
    NotAdmitted {},
    Indeterminate { reason: Diagnostic },
    Unavailable {},
    Acknowledged { stamp: AckStamp },
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Response<R, I, T> {
    pub schema: String,
    pub binding: BufferBinding,
    pub sequence: u64,
    pub operation: OperationName,
    pub request_digest: String,
    pub outcome: Outcome,
    pub code: Code,
    pub body: Body<R, I, T>,
    pub result_digest: String,
}

impl<
        R: Serialize + DeserializeOwned,
        I: Serialize + DeserializeOwned,
        T: Serialize + DeserializeOwned,
    > Response<R, I, T>
{
    pub(crate) fn decode_initial(
        bytes: &[u8],
        expected: &BufferBinding,
    ) -> Result<Self, ModularError> {
        let value = parse_value(bytes)?;
        let claimed = value
            .get("result_digest")
            .and_then(Value::as_str)
            .ok_or(ModularError::Wire)?;
        if !valid_digest(claimed)
            || typed_digest(RESPONSE_SCHEMA, &value, Some("result_digest"))? != claimed
        {
            return Err(ModularError::Wire);
        }
        check_fixed_binding(&value, expected)?;
        if value.get("schema").and_then(Value::as_str) != Some(RESPONSE_SCHEMA)
            || !value
                .get("sequence")
                .and_then(Value::as_u64)
                .is_some_and(|v| (1..=MAX_ID).contains(&v))
        {
            return Err(ModularError::Wire);
        }
        let response: Self = serde_json::from_value(value).map_err(|_| ModularError::Wire)?;
        if response.schema != RESPONSE_SCHEMA
            || response.sequence == 0
            || response.sequence > MAX_ID
            || !valid_digest(&response.request_digest)
        {
            return Err(ModularError::Wire);
        }
        if &response.binding != expected {
            return Err(ModularError::Binding);
        }
        response
            .binding
            .validate()
            .map_err(|_| ModularError::Binding)?;
        response.check_shape()?;
        Ok(response)
    }

    /// Reproject only after the previous typed object has been released.
    pub(crate) fn verify_rejoin_into(
        &self,
        representation: &mut Vec<u8>,
    ) -> Result<(), ModularError> {
        representation.clear();
        serde_json::to_writer(
            FrameWriter {
                bytes: representation,
            },
            self,
        )
        .map_err(|_| ModularError::Capacity)?;
        let decoded = parse_value(representation)?;
        if typed_digest(RESPONSE_SCHEMA, &decoded, Some("result_digest"))? != self.result_digest {
            return Err(ModularError::Wire);
        }
        Ok(())
    }

    pub fn decode(bytes: &[u8], expected: &BufferBinding) -> Result<Self, ModularError> {
        let response = Self::decode_initial(bytes, expected)?;
        response.verify_rejoin_into(&mut frame_slot()?)?;
        Ok(response)
    }
}

impl<R, I, T> Response<R, I, T> {
    pub fn check_shape(&self) -> Result<(), ModularError> {
        let valid = match (&self.outcome, &self.code, &self.body) {
            (Outcome::Committed, Code::Ok, body) => matches!(
                (self.operation, body),
                (OperationName::Prepare, Body::Prepared { .. })
                    | (OperationName::Application, Body::Application { .. })
                    | (
                        OperationName::BufferImportBegin,
                        Body::ImportReserved { .. }
                    )
                    | (OperationName::BufferSeal, Body::ImportSealed { .. })
                    | (OperationName::BufferRead, Body::Chunk { .. })
                    | (
                        OperationName::BufferAppend
                            | OperationName::BufferAbort
                            | OperationName::BufferRelease,
                        Body::BufferChanged { .. }
                    )
                    | (OperationName::Finish, Body::Finished { .. })
                    | (OperationName::Abort, Body::Aborted {})
            ),
            (
                Outcome::RejectedBeforeExecution,
                Code::Role
                | Code::State
                | Code::InvalidInput
                | Code::Capacity
                | Code::BufferUnavailable,
                Body::Rejected {},
            ) => !matches!(self.operation, OperationName::Result | OperationName::Ack),
            (Outcome::NotAdmitted, Code::Conflict | Code::ResultPending, Body::NotAdmitted {}) => {
                self.operation != OperationName::Result
            }
            (Outcome::Indeterminate, Code::ExecutionUnknown, Body::Indeterminate { .. }) => {
                !matches!(self.operation, OperationName::Result | OperationName::Ack)
            }
            (Outcome::Unavailable, Code::NoMatchingRetainedResult, Body::Unavailable {}) => true,
            (Outcome::Acknowledged, Code::ResultReleased, Body::Acknowledged { stamp }) => {
                self.operation == OperationName::Ack
                    && stamp.sequence == self.sequence
                    && valid_digest(&stamp.original_request_digest)
                    && valid_digest(&stamp.result_digest)
            }
            _ => false,
        };
        if valid {
            Ok(())
        } else {
            Err(ModularError::Wire)
        }
    }
}
