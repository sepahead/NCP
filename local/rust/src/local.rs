//! Supervised local lockstep operations with exact retained outcomes.
//!
//! This candidate binding has no listener or remote authentication claim. The
//! supervisor installs the binding before exposing a private pipe to one peer.
//! Backend implementations must validate before mutation and own their state.

use std::fmt;
use std::io::{Read, Write};
use std::panic::{catch_unwind, AssertUnwindSafe};

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::bounded_json::preflight;
use crate::canonical_digest::{canonical_projection, sha256_hex};

/// Maximum bytes in one local frame, excluding its four-byte length prefix.
pub const MAX_LOCAL_FRAME_BYTES: usize = 65_536;
/// Exact candidate profile identity. The contract descriptor also has a digest.
pub const LOCAL_PROFILE: &str = "ncp.local-lockstep.v1";
/// Exact embedded candidate profile descriptor.
pub const LOCAL_PROFILE_DESCRIPTOR: &str = include_str!("../local-profile.v1.json");
/// Maximum positive operation sequence, within the interoperable integer range.
pub const MAX_SEQUENCE: u64 = 9_007_199_254_740_991;

/// Installed endpoint role. A request cannot change this role.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LocalRole {
    /// Private neural simulation owner.
    Neural,
    /// Simulated body owner and final executor.
    Body,
    /// Evidence capture owner with no command capability.
    Capture,
    /// Advisory monitor with no command capability.
    Monitor,
}

/// Closed local operation vocabulary.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LocalOperation {
    /// Bind one immutable run plan and application configuration.
    Prepare,
    /// Advance one neural or body step.
    Step,
    /// Reserve capture capacity before a coupled mutation.
    Reserve,
    /// Record one causally complete pair.
    Capture,
    /// Process advisory evidence without granting control authority.
    Assess,
    /// Close the plan with exact counts and terminal evidence.
    Finish,
    /// Retire the run and release backend resources.
    Abort,
    /// Retrieve an exact retained outcome without execution.
    Result,
    /// Release one retained result with its exact digest.
    Ack,
}

impl LocalRole {
    fn permits(self, operation: LocalOperation) -> bool {
        match operation {
            LocalOperation::Prepare
            | LocalOperation::Finish
            | LocalOperation::Abort
            | LocalOperation::Result
            | LocalOperation::Ack => true,
            LocalOperation::Step => matches!(self, Self::Neural | Self::Body),
            LocalOperation::Reserve | LocalOperation::Capture => self == Self::Capture,
            LocalOperation::Assess => self == Self::Monitor,
        }
    }
}

/// Receiver-owned launch context, established outside the request payload.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct LocalBinding {
    /// Exact selected protocol descriptor digest.
    pub profile_digest: String,
    /// Supervisor-issued run identifier.
    pub run_id: String,
    /// Fresh endpoint generation, never reused after retirement.
    pub generation: String,
    /// Fixed role of this endpoint executable.
    pub role: LocalRole,
}

impl LocalBinding {
    /// Validate a launch binding against the installed profile and UUID grammar.
    pub fn validate(&self) -> Result<(), LocalError> {
        if !valid_uuid(&self.run_id)
            || !valid_uuid(&self.generation)
            || self.profile_digest != local_profile_digest()?
        {
            return Err(LocalError(LocalCode::Binding));
        }
        Ok(())
    }
}

/// One fully correlated local operation request.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LocalRequest {
    /// Must equal `ncp.local.request.v1`.
    pub schema: String,
    /// Must equal the installed descriptor digest.
    pub profile_digest: String,
    /// Must equal the installed run identifier.
    pub run_id: String,
    /// Must equal the installed endpoint generation.
    pub generation: String,
    /// Contiguous operation sequence. Queries reuse the target sequence.
    pub sequence: u64,
    /// Receiver-authorized operation.
    pub operation: LocalOperation,
    /// Closed, application-profile-validated data. Never executable code.
    pub body: Value,
    /// Digest of the complete request except this member.
    pub request_digest: String,
}

/// Outcome at the endpoint's locally observed execution boundary.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LocalOutcome {
    /// The exact backend result is known and retained.
    Committed,
    /// Validation rejected the request before backend execution.
    RejectedBeforeExecution,
    /// Execution started but its complete result cannot be established.
    Indeterminate,
    /// The acknowledged payload is no longer retained. No execution occurs.
    Unavailable,
    /// The exact retained payload was released without backend execution.
    Acknowledged,
}

/// Result body and locally observed outcome, bound by a nonrecursive digest.
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct LocalResponse {
    /// Must equal `ncp.local.response.v1`.
    pub schema: String,
    /// Exact installed context, including the actual endpoint role.
    pub binding: LocalBinding,
    /// Correlated operation sequence.
    pub sequence: u64,
    /// Correlated operation name.
    pub operation: LocalOperation,
    /// Digest of the exact semantic request.
    pub request_digest: String,
    /// Local execution classification.
    pub outcome: LocalOutcome,
    /// Closed local disposition code. Free text does not authorize success.
    pub code: LocalCode,
    /// Complete application result or bounded empty diagnostic object.
    pub body: Value,
    /// Digest of this response excluding only this member.
    pub result_digest: String,
}

/// Closed failure and success codes for the local binding.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum LocalCode {
    /// Normal completion.
    Ok,
    /// Invalid bounded wire representation.
    Wire,
    /// Installed identity or contract mismatch.
    Binding,
    /// Operation is outside the installed role.
    Role,
    /// Invalid sequence or lifecycle transition.
    State,
    /// Same operation identity has different semantic input.
    Conflict,
    /// The previously committed result is still owed.
    ResultPending,
    /// Explicit response acknowledgement released the payload.
    ResultReleased,
    /// Application data or selected configuration is unsupported.
    InvalidInput,
    /// No response reservation is available before execution.
    Capacity,
    /// Backend or response production failed after execution began.
    ExecutionUnknown,
    /// The generation is retired and cannot execute another operation.
    Retired,
}

/// A bounded protocol error. It contains no user payload or credentials.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LocalError(pub LocalCode);

impl fmt::Display for LocalError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "local NCP error: {:?}", self.0)
    }
}
impl std::error::Error for LocalError {}

fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn valid_uuid(value: &str) -> bool {
    value.len() == 36
        && value.as_bytes()[14] == b'4'
        && matches!(value.as_bytes()[19], b'8' | b'9' | b'a' | b'b')
        && value.bytes().enumerate().all(|(i, b)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

/// Hash the complete typed value under one of the declared local digest domains.
pub fn local_digest(domain: &str, value: &Value) -> Result<String, LocalError> {
    if !matches!(
        domain,
        "ncp.local.request.v1"
            | "ncp.local.response.v1"
            | "ncp.local.profile.v1"
            | "ncp.local.snapshot.v1"
            | "ncp.local.plan.v1"
            | "ncp.local.capture.v1"
    ) {
        return Err(LocalError(LocalCode::Wire));
    }
    let mut bytes = domain.as_bytes().to_vec();
    bytes.push(0);
    canonical_projection(&bytes, value)
        .map(|value| sha256_hex(&value))
        .map_err(|_| LocalError(LocalCode::Wire))
}

/// Derive the exact installed descriptor identity, independently of caller data.
pub fn local_profile_digest() -> Result<String, LocalError> {
    let descriptor: Value =
        serde_json::from_str(LOCAL_PROFILE_DESCRIPTOR).map_err(|_| LocalError(LocalCode::Wire))?;
    local_digest("ncp.local.profile.v1", &descriptor)
}

fn digest_without<T: Serialize>(
    domain: &str,
    value: &T,
    member: &str,
) -> Result<String, LocalError> {
    let mut value = serde_json::to_value(value).map_err(|_| LocalError(LocalCode::Wire))?;
    value
        .as_object_mut()
        .ok_or(LocalError(LocalCode::Wire))?
        .remove(member);
    local_digest(domain, &value)
}

impl LocalRequest {
    /// Seal a constructed request after its complete payload is available.
    pub fn seal(&mut self) -> Result<(), LocalError> {
        self.request_digest = digest_without("ncp.local.request.v1", self, "request_digest")?;
        Ok(())
    }
}

impl LocalResponse {
    /// Verify an exact sealed response from the supervisor-bound endpoint.
    ///
    /// This verifies bytes and installed context, not a signature or loaded code.
    /// A client with the original request must also call [`Self::verify`].
    pub fn verify_integrity(&self, binding: &LocalBinding) -> Result<(), LocalError> {
        if self.schema != "ncp.local.response.v1"
            || &self.binding != binding
            || binding.profile_digest != local_profile_digest()?
            || !valid_uuid(&binding.run_id)
            || !valid_uuid(&binding.generation)
            || !(binding.role.permits(self.operation)
                || (self.outcome == LocalOutcome::RejectedBeforeExecution
                    && self.code == LocalCode::Role))
            || self.sequence == 0
            || self.sequence > MAX_SEQUENCE
            || !valid_digest(&self.request_digest)
            || !valid_digest(&self.result_digest)
            || self.result_digest != digest_without("ncp.local.response.v1", self, "result_digest")?
        {
            return Err(LocalError(LocalCode::Binding));
        }
        let coherent = match self.outcome {
            LocalOutcome::Committed => {
                self.code == LocalCode::Ok
                    && !matches!(self.operation, LocalOperation::Result | LocalOperation::Ack)
            }
            LocalOutcome::Acknowledged => {
                self.code == LocalCode::Ok && self.operation == LocalOperation::Ack
            }
            LocalOutcome::Indeterminate => {
                self.code == LocalCode::ExecutionUnknown
                    && !matches!(self.operation, LocalOperation::Result | LocalOperation::Ack)
            }
            LocalOutcome::Unavailable => {
                self.code == LocalCode::ResultReleased && self.operation != LocalOperation::Ack
            }
            LocalOutcome::RejectedBeforeExecution => !matches!(
                self.code,
                LocalCode::Ok | LocalCode::ExecutionUnknown | LocalCode::ResultReleased
            ),
        };
        if !coherent {
            return Err(LocalError(LocalCode::Wire));
        }
        Ok(())
    }

    /// Independently verify the complete response body and its request join.
    pub fn verify(&self, binding: &LocalBinding, request: &LocalRequest) -> Result<(), LocalError> {
        self.verify_integrity(binding)?;
        if self.schema != "ncp.local.response.v1"
            || &self.binding != binding
            || self.sequence != request.sequence
            || self.operation != request.operation
            || self.request_digest != request.request_digest
            || request.profile_digest != binding.profile_digest
            || request.run_id != binding.run_id
            || request.generation != binding.generation
            || request.request_digest
                != digest_without("ncp.local.request.v1", request, "request_digest")?
            || !valid_digest(&self.result_digest)
            || self.result_digest != digest_without("ncp.local.response.v1", self, "result_digest")?
        {
            return Err(LocalError(LocalCode::Binding));
        }
        Ok(())
    }

    /// Verify a successful exact-result lookup against its original operation.
    ///
    /// The lookup is a query; the returned bytes retain the original correlation.
    /// Rejections and unavailable answers instead use ordinary query verification.
    pub fn verify_retrieved(
        &self,
        binding: &LocalBinding,
        original: &LocalRequest,
        query: &LocalRequest,
    ) -> Result<(), LocalError> {
        if query.operation != LocalOperation::Result
            || query.sequence != original.sequence
            || query.profile_digest != original.profile_digest
            || query.run_id != original.run_id
            || query.generation != original.generation
            || query.body != json!({"request_digest": original.request_digest})
            || query.request_digest
                != digest_without("ncp.local.request.v1", query, "request_digest")?
        {
            return Err(LocalError(LocalCode::Binding));
        }
        self.verify(binding, original)?;
        if !matches!(
            self.outcome,
            LocalOutcome::Committed | LocalOutcome::Indeterminate
        ) {
            return Err(LocalError(LocalCode::Wire));
        }
        Ok(())
    }
}

// Bound traversal before serializing or cloning programmatic backend results.
// Backend-owned scientific values still require their closed application schema.
fn check_result_value(value: &Value, depth: usize, budget: &mut usize) -> Result<(), LocalError> {
    if depth > 32 || *budget == 0 {
        return Err(LocalError(LocalCode::Capacity));
    }
    *budget -= 1;
    match value {
        Value::String(text) if text.len() > MAX_LOCAL_FRAME_BYTES => {
            return Err(LocalError(LocalCode::Capacity))
        }
        Value::Array(items) => {
            if items.len() > *budget {
                return Err(LocalError(LocalCode::Capacity));
            }
            for item in items {
                check_result_value(item, depth + 1, budget)?;
            }
        }
        Value::Object(items) => {
            if items.len() > 4096 || items.len() > *budget {
                return Err(LocalError(LocalCode::Capacity));
            }
            for (key, item) in items {
                if key.len() > 128 {
                    return Err(LocalError(LocalCode::Capacity));
                }
                check_result_value(item, depth + 1, budget)?;
            }
        }
        _ => (),
    }
    Ok(())
}

struct LocalWriter {
    bytes: Vec<u8>,
}
impl Write for LocalWriter {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        if bytes.len() > MAX_LOCAL_FRAME_BYTES.saturating_sub(self.bytes.len()) {
            return Err(std::io::Error::other("local frame capacity"));
        }
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

/// Owner-local application seam. Validation must not mutate the backend.
pub trait LocalBackend {
    /// Validate all data, logical predecessors, and application resource limits.
    fn validate(&self, operation: LocalOperation, body: &Value) -> Result<(), LocalError>;
    /// Execute one already validated operation. Every error retires the generation.
    fn execute(&mut self, operation: LocalOperation, body: &Value) -> Result<Value, LocalError>;
    /// Stop further mutation and release resources. This does not imply rollback.
    fn retire(&mut self);
}

struct Retained {
    sequence: u64,
    request_digest: String,
    result_digest: String,
    bytes: Vec<u8>,
}

/// Serial owner of one endpoint generation and one exact retained response.
pub struct LocalOwner<B: LocalBackend> {
    binding: LocalBinding,
    backend: B,
    high_water: u64,
    retained: Option<Retained>,
    acknowledged: Option<(u64, String, String)>,
    prepared: bool,
    finished: bool,
    retired: bool,
}

impl<B: LocalBackend> LocalOwner<B> {
    /// Install a trusted launch binding. No request can replace this binding.
    pub fn new(binding: LocalBinding, backend: B) -> Result<Self, LocalError> {
        binding.validate()?;
        Ok(Self {
            binding,
            backend,
            high_water: 0,
            retained: None,
            acknowledged: None,
            prepared: false,
            finished: false,
            retired: false,
        })
    }

    /// Read the immutable installed context.
    pub fn binding(&self) -> &LocalBinding {
        &self.binding
    }

    /// Report retained payload bytes for resource tests and observability.
    pub fn retained_bytes(&self) -> usize {
        self.retained.as_ref().map_or(0, |row| row.bytes.len())
    }

    /// Permanently retire this generation after channel loss or cancellation.
    ///
    /// An owed outcome remains readable. No later operation can mutate the backend.
    /// The supervisor must kill a child whose cleanup does not terminate in time.
    pub fn retire_generation(&mut self) {
        if !self.retired {
            self.retired = true;
            let _ = catch_unwind(AssertUnwindSafe(|| self.backend.retire()));
        }
    }

    fn response(
        &self,
        request: &LocalRequest,
        outcome: LocalOutcome,
        code: LocalCode,
        body: Value,
    ) -> Result<Vec<u8>, LocalError> {
        let mut reservation = Vec::new();
        reservation
            .try_reserve_exact(MAX_LOCAL_FRAME_BYTES)
            .map_err(|_| LocalError(LocalCode::Capacity))?;
        self.response_into(request, outcome, code, body, reservation)
    }

    fn response_into(
        &self,
        request: &LocalRequest,
        outcome: LocalOutcome,
        code: LocalCode,
        body: Value,
        reservation: Vec<u8>,
    ) -> Result<Vec<u8>, LocalError> {
        check_result_value(&body, 0, &mut 16_384)?;
        let mut response = LocalResponse {
            schema: "ncp.local.response.v1".into(),
            binding: self.binding.clone(),
            sequence: request.sequence,
            operation: request.operation,
            request_digest: request.request_digest.clone(),
            outcome,
            code,
            body,
            result_digest: "0".repeat(64),
        };
        // Prove the complete wire ceiling before the bounded digest projection.
        let mut writer = LocalWriter { bytes: reservation };
        serde_json::to_writer(&mut writer, &response)
            .map_err(|_| LocalError(LocalCode::Capacity))?;
        preflight(&writer.bytes).map_err(|_| LocalError(LocalCode::Wire))?;
        response.result_digest =
            digest_without("ncp.local.response.v1", &response, "result_digest")?;
        writer.bytes.clear();
        serde_json::to_writer(&mut writer, &response)
            .map_err(|_| LocalError(LocalCode::Capacity))?;
        Ok(writer.bytes)
    }

    fn reject(&self, request: &LocalRequest, code: LocalCode) -> Result<Vec<u8>, LocalError> {
        self.response(
            request,
            LocalOutcome::RejectedBeforeExecution,
            code,
            json!({}),
        )
    }

    fn lookup(&self, request: &LocalRequest) -> Result<Vec<u8>, LocalError> {
        let expected = request
            .body
            .as_object()
            .filter(|body| body.len() == 1)
            .and_then(|body| body.get("request_digest"))
            .and_then(Value::as_str)
            .filter(|digest| valid_digest(digest))
            .ok_or(LocalError(LocalCode::InvalidInput))?;
        if let Some(row) = &self.retained {
            if row.sequence == request.sequence {
                return if row.request_digest == expected {
                    Ok(row.bytes.clone())
                } else {
                    self.reject(request, LocalCode::Conflict)
                };
            }
        }
        if request.sequence <= self.high_water {
            return self.response(
                request,
                LocalOutcome::Unavailable,
                LocalCode::ResultReleased,
                json!({}),
            );
        }
        self.reject(request, LocalCode::State)
    }

    fn acknowledge(&mut self, request: &LocalRequest) -> Result<Vec<u8>, LocalError> {
        let expected = request
            .body
            .as_object()
            .filter(|body| body.len() == 1)
            .and_then(|body| body.get("result_digest"))
            .and_then(Value::as_str)
            .filter(|digest| valid_digest(digest))
            .ok_or(LocalError(LocalCode::InvalidInput))?;
        if let Some(row) = &self.retained {
            if row.sequence != request.sequence || row.result_digest != expected {
                return self.reject(request, LocalCode::Conflict);
            }
            self.acknowledged = Some((
                row.sequence,
                row.request_digest.clone(),
                row.result_digest.clone(),
            ));
            self.retained = None;
        } else if !self
            .acknowledged
            .as_ref()
            .is_some_and(|row| row.0 == request.sequence && row.2 == expected)
        {
            return self.reject(request, LocalCode::Conflict);
        }
        self.response(
            request,
            LocalOutcome::Acknowledged,
            LocalCode::Ok,
            json!({}),
        )
    }

    /// Decode, validate, and handle a bounded frame under serialized ownership.
    ///
    /// Exact retries return identical bytes. Acknowledged operations cannot rerun.
    /// Backend failures and unrepresentable post-mutation results retire the owner.
    pub fn handle(&mut self, bytes: &[u8]) -> Result<Vec<u8>, LocalError> {
        if bytes.len() > MAX_LOCAL_FRAME_BYTES {
            return Err(LocalError(LocalCode::Capacity));
        }
        preflight(bytes).map_err(|_| LocalError(LocalCode::Wire))?;
        let request: LocalRequest =
            serde_json::from_slice(bytes).map_err(|_| LocalError(LocalCode::Wire))?;
        if request.schema != "ncp.local.request.v1"
            || request.sequence == 0
            || request.sequence > MAX_SEQUENCE
            || request.request_digest
                != digest_without("ncp.local.request.v1", &request, "request_digest")?
        {
            return Err(LocalError(LocalCode::Wire));
        }
        if request.run_id != self.binding.run_id
            || request.generation != self.binding.generation
            || request.profile_digest != self.binding.profile_digest
        {
            return self.reject(&request, LocalCode::Binding);
        }
        if !self.binding.role.permits(request.operation) {
            return self.reject(&request, LocalCode::Role);
        }
        if request.operation == LocalOperation::Result {
            return self.lookup(&request);
        }
        if request.operation == LocalOperation::Ack {
            return self.acknowledge(&request);
        }
        if let Some(row) = &self.retained {
            return if row.sequence == request.sequence {
                if row.request_digest == request.request_digest {
                    Ok(row.bytes.clone())
                } else {
                    self.reject(&request, LocalCode::Conflict)
                }
            } else {
                self.reject(&request, LocalCode::ResultPending)
            };
        }
        if request.sequence <= self.high_water {
            return self.response(
                &request,
                LocalOutcome::Unavailable,
                LocalCode::ResultReleased,
                json!({}),
            );
        }
        if self.retired {
            return self.reject(&request, LocalCode::Retired);
        }
        if self.finished
            || request.sequence != self.high_water + 1
            || (!self.prepared && request.operation != LocalOperation::Prepare)
            || (self.prepared && request.operation == LocalOperation::Prepare)
        {
            return self.reject(&request, LocalCode::State);
        }
        if let Err(error) = self.backend.validate(request.operation, &request.body) {
            let code = match error.0 {
                LocalCode::Ok | LocalCode::ExecutionUnknown | LocalCode::ResultReleased => {
                    LocalCode::InvalidInput
                }
                code => code,
            };
            return self.reject(&request, code);
        }
        // Reserve retained wire storage. Bounded digest staging allocates separately.
        let mut reservation = Vec::<u8>::new();
        reservation
            .try_reserve_exact(MAX_LOCAL_FRAME_BYTES)
            .map_err(|_| LocalError(LocalCode::Capacity))?;
        self.high_water = request.sequence;
        let result = catch_unwind(AssertUnwindSafe(|| {
            self.backend.execute(request.operation, &request.body)
        }));
        let output = match result {
            Ok(Ok(body)) => self.response_into(
                &request,
                LocalOutcome::Committed,
                LocalCode::Ok,
                body,
                reservation,
            ),
            _ => Err(LocalError(LocalCode::ExecutionUnknown)),
        };
        let output = match output {
            Ok(bytes) => {
                self.prepared = true;
                if matches!(
                    request.operation,
                    LocalOperation::Finish | LocalOperation::Abort
                ) {
                    self.finished = true;
                }
                bytes
            }
            Err(_) => {
                self.retire_generation();
                self.response(
                    &request,
                    LocalOutcome::Indeterminate,
                    LocalCode::ExecutionUnknown,
                    json!({}),
                )?
            }
        };
        let response: LocalResponse =
            serde_json::from_slice(&output).map_err(|_| LocalError(LocalCode::Wire))?;
        self.retained = Some(Retained {
            sequence: request.sequence,
            request_digest: request.request_digest,
            result_digest: response.result_digest,
            bytes: output.clone(),
        });
        Ok(output)
    }
}

impl<B: LocalBackend> Drop for LocalOwner<B> {
    fn drop(&mut self) {
        self.retire_generation();
    }
}

/// Read one length-prefixed bounded local frame. Clean EOF returns `None`.
pub fn read_local_frame(reader: &mut impl Read) -> Result<Option<Vec<u8>>, LocalError> {
    let mut header = [0u8; 4];
    match reader.read(&mut header[..1]) {
        Ok(0) => return Ok(None),
        Ok(_) => (),
        Err(_) => return Err(LocalError(LocalCode::Wire)),
    }
    reader
        .read_exact(&mut header[1..])
        .map_err(|_| LocalError(LocalCode::Wire))?;
    let length = u32::from_be_bytes(header) as usize;
    if length == 0 || length > MAX_LOCAL_FRAME_BYTES {
        return Err(LocalError(LocalCode::Capacity));
    }
    let mut bytes = vec![0u8; length];
    reader
        .read_exact(&mut bytes)
        .map_err(|_| LocalError(LocalCode::Wire))?;
    Ok(Some(bytes))
}

/// Write exactly one bounded frame and flush its complete length-prefixed bytes.
pub fn write_local_frame(writer: &mut impl Write, bytes: &[u8]) -> Result<(), LocalError> {
    if bytes.is_empty() || bytes.len() > MAX_LOCAL_FRAME_BYTES {
        return Err(LocalError(LocalCode::Capacity));
    }
    writer
        .write_all(&(bytes.len() as u32).to_be_bytes())
        .map_err(|_| LocalError(LocalCode::Wire))?;
    writer
        .write_all(bytes)
        .map_err(|_| LocalError(LocalCode::Wire))?;
    writer.flush().map_err(|_| LocalError(LocalCode::Wire))
}

/// Serve one inherited private channel and retire on every exit, including EOF.
pub fn serve_local<B: LocalBackend>(
    owner: &mut LocalOwner<B>,
    reader: &mut impl Read,
    writer: &mut impl Write,
) -> Result<(), LocalError> {
    let result = (|| {
        while let Some(bytes) = read_local_frame(reader)? {
            let output = owner.handle(&bytes)?;
            write_local_frame(writer, &output)?;
        }
        Ok(())
    })();
    owner.retire_generation();
    result
}
