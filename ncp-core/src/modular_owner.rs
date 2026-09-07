//! Synchronous closed SDK owner for statically installed application contracts.
//! No application schema, executable, scientific model, or launcher is installed here.

use std::cell::Cell;
use std::io::{Read, Write};
use std::panic::{catch_unwind, AssertUnwindSafe};

use serde::{de::DeserializeOwned, Deserialize, Serialize};

use crate::modular_buffer::{
    self, BufferBinding, BufferError, BufferManifest, BufferPool, BufferUsage, InputSpec,
    InputView, OutputReservation, OutputSpec, TrustedHostCreationContext, LIVE_SLOTS, MAX_ID,
};
use crate::modular_wire::{
    self as wire, AckStamp, Body, Code, Command, Diagnostic, ModularError, Operation,
    OperationName, Outcome, Request, Response,
};

pub const CORE_DESCRIPTOR: &[u8] = include_bytes!("modular_profile.v1.json");
pub const IMPORT_METADATA_BYTES: usize = 1_024;
pub const IMPORT_METADATA_LOGICAL_BYTES: usize = 32_768;
pub const ENDPOINT_LOGICAL_OVERHEAD: usize = 1_261_568;

pub fn profile_digest() -> Result<String, ModularError> {
    wire::typed_digest(
        wire::PROFILE_DOMAIN,
        &wire::parse_value(CORE_DESCRIPTOR)?,
        None,
    )
}

/// Return payload and owner extents. Add clients and caller-owned storage separately.
pub fn composition_budget(payload_reservations: &[usize]) -> Result<(usize, usize), BufferError> {
    let payload = modular_buffer::admit_composition(payload_reservations)?;
    Ok((
        payload,
        payload_reservations.len() * ENDPOINT_LOGICAL_OVERHEAD,
    ))
}

pub type AppOperation<A> = Operation<
    <A as Contract>::Prepare,
    <A as Contract>::Command,
    <A as Contract>::ImportDescriptor,
    <A as Contract>::Finish,
>;
pub type AppBody<A> =
    Body<<A as Contract>::Result, <A as Contract>::Imported, <A as Contract>::Terminal>;
pub type AppResponse<A> =
    Response<<A as Contract>::Result, <A as Contract>::Imported, <A as Contract>::Terminal>;

/// Installed closed codecs and pure client-verifiable semantics.
/// A trait cannot attest that arbitrary user implementations obey this contract.
pub trait Contract: Sized {
    type Prepare: Serialize + DeserializeOwned;
    type Command: Serialize + DeserializeOwned;
    type ImportDescriptor: Serialize + DeserializeOwned;
    type ImportMetadata: Serialize + DeserializeOwned;
    type Finish: Serialize + DeserializeOwned;
    type Result: Serialize + DeserializeOwned + PartialEq;
    type Imported: Serialize + DeserializeOwned + PartialEq;
    type Terminal: Serialize + DeserializeOwned + PartialEq;

    fn descriptor() -> &'static [u8];
    fn allows(operation: OperationName) -> bool;
    /// Static shape/quantity checks only: replay cannot depend on current state.
    fn check_input(operation: &AppOperation<Self>) -> Result<(), ModularError>;
    fn check_response(
        operation: &AppOperation<Self>,
        body: &AppBody<Self>,
        context: &ExecutionContext,
    ) -> Result<(), ModularError>;
    fn check_import_metadata(
        descriptor: &Self::ImportDescriptor,
        metadata: &Self::ImportMetadata,
    ) -> Result<(), ModularError>;
}

/// Pure split result borrows the admitted source, avoiding a full manifest shadow.
pub struct ImportSource<'a, M> {
    pub manifest: &'a BufferManifest,
    pub expected_binding: &'a BufferBinding,
    pub metadata: M,
}

/// Closed local admission demand. Input payloads remain owned by the core pool.
#[derive(Default)]
pub struct AdmissionDemand {
    pub inputs: Vec<InputSpec>,
    pub outputs: Vec<OutputSpec>,
}

pub enum ApplicationOutput<R, T> {
    Result(R),
    Terminal(T),
    Aborted,
}

/// The application owns execution and its scientific state. Core bytes and indexing
/// are inaccessible through this interface. There is no string/Value dispatch.
pub trait Application: Contract {
    /// Pure state validation and closed local output demand. No I/O or reservation.
    fn admit(
        &self,
        operation: &AppOperation<Self>,
        view: &AdmissionView<'_>,
    ) -> Result<AdmissionDemand, Code>;
    fn execute(
        &mut self,
        operation: &AppOperation<Self>,
        permit: &mut ExecutionPermit<'_, '_>,
    ) -> Result<ApplicationOutput<Self::Result, Self::Terminal>, Diagnostic>;
    fn split_import<'a>(
        &'a self,
        descriptor: &'a Self::ImportDescriptor,
    ) -> Result<ImportSource<'a, Self::ImportMetadata>, Code>;
    /// Pure validation of the complete owned payload and its frozen typed metadata.
    fn validate_import(
        &self,
        metadata: &Self::ImportMetadata,
        manifest: &BufferManifest,
        bytes: &[u8],
    ) -> Result<Self::Imported, Code>;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Lifecycle {
    New,
    Active,
    Finished,
    Retired,
}

pub struct AdmissionView<'a> {
    pub lifecycle: Lifecycle,
    pub high_water: u64,
    pub predecessor: Option<&'a str>,
    pub buffers: BufferUsage,
}

/// Private construction joins the exact fixed binding and complete verified request.
pub struct ExecutionContext {
    binding: BufferBinding,
    sequence: u64,
    request_digest: String,
    predecessor: Option<String>,
}
impl ExecutionContext {
    pub fn binding(&self) -> &BufferBinding {
        &self.binding
    }
    pub fn sequence(&self) -> u64 {
        self.sequence
    }
    pub fn request_digest(&self) -> &str {
        &self.request_digest
    }
    pub fn predecessor(&self) -> Option<&str> {
        self.predecessor.as_deref()
    }
    fn trusted(&self) -> Result<TrustedHostCreationContext, ModularError> {
        TrustedHostCreationContext::new(
            self.binding.clone(),
            self.request_digest.clone(),
            self.predecessor.clone(),
        )
        .map_err(|_| ModularError::Binding)
    }
}

pub struct ExecutionPermit<'a, 'pool> {
    context: &'a ExecutionContext,
    outputs: Option<&'a mut OutputReservation<'pool>>,
    violated: Cell<bool>,
}
impl ExecutionPermit<'_, '_> {
    pub fn context(&self) -> &ExecutionContext {
        self.context
    }
    /// Read only a selected sealed input during this synchronous call.
    /// The returned view borrows this permit; it cannot become a static capability.
    pub fn input(&self, slot: usize) -> Result<InputView<'_>, BufferError> {
        let result = self
            .outputs
            .as_ref()
            .ok_or(BufferError::State)
            .and_then(|ticket| ticket.input(slot));
        if result.is_err() {
            self.violated.set(true);
        }
        result
    }

    pub fn write_output(
        &mut self,
        slot: usize,
        offset: usize,
        bytes: &[u8],
    ) -> Result<(), BufferError> {
        let result = self
            .outputs
            .as_mut()
            .ok_or(BufferError::State)
            .and_then(|outputs| outputs.write(slot, offset, bytes));
        if result.is_err() {
            self.violated.set(true);
        }
        result
    }
    pub fn seal_output(&mut self, slot: usize) -> Result<BufferManifest, BufferError> {
        let result = self
            .outputs
            .as_mut()
            .ok_or(BufferError::State)
            .and_then(|outputs| outputs.seal(slot));
        if result.is_err() {
            self.violated.set(true);
        }
        result
    }
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ImportRecord<M> {
    source_manifest_digest: String,
    source_descriptor_digest: String,
    data: M,
}
struct StoredImport {
    id: u64,
    wire: Vec<u8>,
    integrity: String,
}
struct MetadataWriter<'a>(&'a mut Vec<u8>);
impl Write for MetadataWriter<'_> {
    fn write(&mut self, input: &[u8]) -> std::io::Result<usize> {
        if input.len() > IMPORT_METADATA_BYTES.saturating_sub(self.0.len()) {
            return Err(std::io::Error::other("import metadata capacity"));
        }
        self.0.extend_from_slice(input);
        Ok(input.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

#[derive(Clone)]
struct Stamp {
    sequence: u64,
    request_digest: String,
    operation: OperationName,
}
struct Owed {
    stamp: Stamp,
    result_digest: String,
}
enum Reply {
    Retained,
    Staging,
}

/// One synchronous endpoint, one retained outcome, and one fixed ACK stamp.
pub struct Owner<A: Application> {
    binding: BufferBinding,
    application: A,
    pool: BufferPool,
    lifecycle: Lifecycle,
    channel_retired: bool,
    high_water: u64,
    predecessor: Option<String>,
    retained: Vec<u8>,
    staging: Vec<u8>,
    owed: Option<Owed>,
    last_ack: Option<AckStamp>,
    entered: Option<Stamp>,
    imports: Vec<Option<StoredImport>>,
}

fn buffer_code(error: BufferError) -> Code {
    match error {
        BufferError::Capacity => Code::Capacity,
        BufferError::Unavailable => Code::BufferUnavailable,
        _ => Code::InvalidInput,
    }
}
fn rejection_code(code: Code) -> Code {
    match code {
        Code::Role
        | Code::State
        | Code::InvalidInput
        | Code::Capacity
        | Code::BufferUnavailable => code,
        _ => Code::InvalidInput,
    }
}

fn application_rejection(code: Code) -> Code {
    if code == Code::Role {
        Code::InvalidInput
    } else {
        rejection_code(code)
    }
}

impl<A: Application> Owner<A> {
    pub fn new(
        binding: BufferBinding,
        application: A,
        semantics: Vec<String>,
    ) -> Result<Self, ModularError> {
        binding.validate().map_err(|_| ModularError::Binding)?;
        let application_digest = wire::typed_digest(
            wire::PROFILE_DOMAIN,
            &wire::parse_value(A::descriptor())?,
            None,
        )?;
        if binding.profile_digest != profile_digest()?
            || binding.application_digest != application_digest
        {
            return Err(ModularError::Binding);
        }
        let pool =
            BufferPool::new(binding.clone(), semantics).map_err(|_| ModularError::Binding)?;
        let mut imports = Vec::new();
        imports
            .try_reserve_exact(LIVE_SLOTS)
            .map_err(|_| ModularError::Capacity)?;
        imports.resize_with(LIVE_SLOTS, || None);
        Ok(Self {
            binding,
            application,
            pool,
            lifecycle: Lifecycle::New,
            channel_retired: false,
            high_water: 0,
            predecessor: None,
            retained: wire::frame_slot()?,
            staging: wire::frame_slot()?,
            owed: None,
            last_ack: None,
            entered: None,
            imports,
        })
    }

    pub fn binding(&self) -> &BufferBinding {
        &self.binding
    }
    pub fn lifecycle(&self) -> Lifecycle {
        self.lifecycle
    }
    pub fn high_water(&self) -> u64 {
        self.high_water
    }
    pub fn predecessor(&self) -> Option<&str> {
        self.predecessor.as_deref()
    }
    pub fn usage(&self) -> BufferUsage {
        self.pool.usage()
    }
    pub fn retained(&self) -> Option<&[u8]> {
        self.owed.as_ref().map(|_| self.retained.as_slice())
    }
    pub fn retire_channel(&mut self) {
        self.channel_retired = true;
        self.lifecycle = Lifecycle::Retired;
    }

    fn emit(
        &mut self,
        stamp: &Stamp,
        outcome: Outcome,
        code: Code,
        body: AppBody<A>,
        retained: bool,
    ) -> Result<Reply, ModularError> {
        let response = Response {
            schema: wire::RESPONSE_SCHEMA.into(),
            binding: self.binding.clone(),
            sequence: stamp.sequence,
            operation: stamp.operation,
            request_digest: stamp.request_digest.clone(),
            outcome,
            code,
            body,
            result_digest: String::new(),
        };
        response.check_shape()?;
        wire::seal_into(
            &response,
            "result_digest",
            wire::RESPONSE_SCHEMA,
            &mut self.staging,
        )?;
        if retained {
            // No result is owed when execution enters. Its existing slot can be scratch.
            // Keep at most original+decoded typed bodies, then decoded+projection.
            let decoded = AppResponse::<A>::decode_initial(&self.staging, &self.binding)?;
            if decoded.body != response.body {
                return Err(ModularError::Wire);
            }
            drop(response);
            decoded.verify_rejoin_into(&mut self.retained)?;
            let result_digest = decoded.result_digest;
            self.predecessor = Some(result_digest.clone());
            self.owed = Some(Owed {
                stamp: stamp.clone(),
                result_digest,
            });
            std::mem::swap(&mut self.retained, &mut self.staging);
            self.staging.clear();
            Ok(Reply::Retained)
        } else {
            Ok(Reply::Staging)
        }
    }

    fn reject(&mut self, stamp: &Stamp, code: Code) -> Result<Reply, ModularError> {
        self.emit(
            stamp,
            Outcome::RejectedBeforeExecution,
            rejection_code(code),
            Body::Rejected {},
            false,
        )
    }
    fn unavailable(&mut self, stamp: &Stamp) -> Result<Reply, ModularError> {
        self.emit(
            stamp,
            Outcome::Unavailable,
            Code::NoMatchingRetainedResult,
            Body::Unavailable {},
            false,
        )
    }
    fn conflict(&mut self, stamp: &Stamp, pending: bool) -> Result<Reply, ModularError> {
        self.emit(
            stamp,
            Outcome::NotAdmitted,
            if pending {
                Code::ResultPending
            } else {
                Code::Conflict
            },
            Body::NotAdmitted {},
            false,
        )
    }

    /// Handle a complete frame. The returned bytes borrow one bounded owner slot.
    /// Unbound input closes this generation without a fabricated correlated response.
    pub fn process(&mut self, bytes: &[u8]) -> Result<&[u8], ModularError> {
        if self.channel_retired {
            return Err(ModularError::Retired);
        }
        self.entered = None;
        let result = catch_unwind(AssertUnwindSafe(|| self.process_inner(bytes)));
        let reply = match result {
            Ok(Ok(reply)) => reply,
            failed => {
                self.lifecycle = Lifecycle::Retired;
                if let Some(stamp) = self.entered.take() {
                    let reason = match &failed {
                        Err(_) => Diagnostic::Backend,
                        Ok(Err(ModularError::Execution(reason))) => *reason,
                        _ => Diagnostic::InvalidOutput,
                    };
                    // A caught panic can own failed application output. Release it
                    // before constructing the separately bounded diagnostic.
                    drop(failed);
                    match self.emit(
                        &stamp,
                        Outcome::Indeterminate,
                        Code::ExecutionUnknown,
                        Body::Indeterminate { reason },
                        true,
                    ) {
                        Ok(reply) => reply,
                        Err(error) => {
                            self.retire_channel();
                            return Err(error);
                        }
                    }
                } else {
                    self.retire_channel();
                    return Err(match failed {
                        Ok(Err(error)) => error,
                        _ => ModularError::Retired,
                    });
                }
            }
        };
        self.entered = None;
        Ok(match reply {
            Reply::Retained => &self.retained,
            Reply::Staging => &self.staging,
        })
    }

    fn process_inner(&mut self, bytes: &[u8]) -> Result<Reply, ModularError> {
        let (request, import_descriptor_digest) =
            Request::<AppOperation<A>>::decode_with_import_identity(
                bytes,
                &self.binding,
                &mut self.staging,
            )?;
        let name = match &request.command {
            Command::Execute { operation, .. } => {
                A::check_input(operation)?;
                operation.name()
            }
            Command::Result { .. } => OperationName::Result,
            Command::Ack { .. } => OperationName::Ack,
        };
        let stamp = Stamp {
            sequence: request.sequence,
            request_digest: request.request_digest.clone(),
            operation: name,
        };
        match &request.command {
            Command::Result {
                original_request_digest,
            } => {
                if self.owed.as_ref().is_some_and(|owed| {
                    owed.stamp.sequence == request.sequence
                        && &owed.stamp.request_digest == original_request_digest
                }) {
                    return Ok(Reply::Retained);
                }
                return self.unavailable(&stamp);
            }
            Command::Ack {
                original_request_digest,
                result_digest,
            } => {
                let target = AckStamp {
                    sequence: request.sequence,
                    original_request_digest: original_request_digest.clone(),
                    result_digest: result_digest.clone(),
                };
                let current = self.owed.as_ref().is_some_and(|owed| {
                    owed.stamp.sequence == target.sequence
                        && owed.stamp.request_digest == target.original_request_digest
                        && owed.result_digest == target.result_digest
                });
                if current || self.last_ack.as_ref() == Some(&target) {
                    let reply = self.emit(
                        &stamp,
                        Outcome::Acknowledged,
                        Code::ResultReleased,
                        Body::Acknowledged {
                            stamp: target.clone(),
                        },
                        false,
                    )?;
                    if current {
                        self.owed = None;
                        self.retained.clear();
                        self.last_ack = Some(target);
                    }
                    return Ok(reply);
                }
                if self
                    .owed
                    .as_ref()
                    .is_some_and(|owed| owed.stamp.sequence == request.sequence)
                    || self
                        .last_ack
                        .as_ref()
                        .is_some_and(|ack| ack.sequence == request.sequence)
                {
                    return self.conflict(&stamp, false);
                }
                return self.unavailable(&stamp);
            }
            Command::Execute { .. } => {}
        }
        if let Some(owed) = &self.owed {
            if owed.stamp.sequence == stamp.sequence
                && owed.stamp.request_digest == stamp.request_digest
            {
                return Ok(Reply::Retained);
            }
            return self.conflict(&stamp, stamp.sequence > owed.stamp.sequence);
        }
        if stamp.sequence <= self.high_water {
            return self.unavailable(&stamp);
        }
        if self.high_water == MAX_ID || stamp.sequence != self.high_water + 1 {
            return self.conflict(&stamp, false);
        }
        let Command::Execute {
            expected_predecessor_result_digest,
            operation,
        } = &request.command
        else {
            return Err(ModularError::Wire);
        };
        if !A::allows(name) {
            return self.reject(&stamp, Code::Role);
        }
        if expected_predecessor_result_digest != &self.predecessor {
            return self.reject(&stamp, Code::State);
        }
        if (name == OperationName::Prepare && self.lifecycle != Lifecycle::New)
            || (name != OperationName::Prepare && self.lifecycle != Lifecycle::Active)
        {
            return self.reject(&stamp, Code::State);
        }
        let demand = match self.application.admit(
            operation,
            &AdmissionView {
                lifecycle: self.lifecycle,
                high_water: self.high_water,
                predecessor: self.predecessor.as_deref(),
                buffers: self.pool.usage(),
            },
        ) {
            Ok(demand) => demand,
            Err(code) => return self.reject(&stamp, application_rejection(code)),
        };
        if !matches!(name, OperationName::Prepare | OperationName::Application)
            && (!demand.inputs.is_empty() || !demand.outputs.is_empty())
        {
            return self.reject(&stamp, Code::Capacity);
        }
        if name == OperationName::Finish
            && (self.pool.usage().live_slots != 0 || self.imports.iter().any(Option::is_some))
        {
            return self.reject(&stamp, Code::State);
        }
        let context = ExecutionContext {
            binding: self.binding.clone(),
            sequence: stamp.sequence,
            request_digest: stamp.request_digest.clone(),
            predecessor: self.predecessor.clone(),
        };
        let body = match self.execute_admitted(
            &stamp,
            operation,
            demand,
            &context,
            import_descriptor_digest,
        )? {
            Ok(body) => body,
            Err(code) => return self.reject(&stamp, code),
        };
        check_core_response(operation, &body, &context)?;
        A::check_response(operation, &body, &context)?;
        if name == OperationName::Finish
            && (self.pool.usage().live_slots != 0 || self.imports.iter().any(Option::is_some))
        {
            return Err(ModularError::Retired);
        }
        // Output codec checking uses the former request's parsed extent.
        drop(request);
        let reply = self.emit(&stamp, Outcome::Committed, Code::Ok, body, true)?;
        match name {
            OperationName::Prepare => self.lifecycle = Lifecycle::Active,
            OperationName::Finish => self.lifecycle = Lifecycle::Finished,
            OperationName::Abort => self.lifecycle = Lifecycle::Retired,
            _ => {}
        }
        Ok(reply)
    }

    fn execute_admitted(
        &mut self,
        stamp: &Stamp,
        operation: &AppOperation<A>,
        demand: AdmissionDemand,
        context: &ExecutionContext,
        import_descriptor_digest: Option<String>,
    ) -> Result<Result<AppBody<A>, Code>, ModularError> {
        let core_check = match operation {
            Operation::BufferAppend(input) => {
                self.pool.check_append(&input.reference, &input.chunk)
            }
            Operation::BufferAbort(input) => self.pool.check_release(&input.reference, true),
            Operation::BufferRelease(input) => self.pool.check_release(&input.reference, false),
            Operation::BufferRead(input) => self
                .pool
                .check_read(&input.reference, input.index)
                .and_then(|()| {
                    self.pool
                        .check_manifest(&input.reference, &input.expected_manifest_digest)
                }),
            _ => Ok(()),
        };
        if let Err(error) = core_check {
            return Ok(Err(buffer_code(error)));
        }
        match operation {
            Operation::Prepare(_)
            | Operation::Application(_)
            | Operation::Finish(_)
            | Operation::Abort(_) => {
                let mut ticket = match self.pool.reserve_execution(&demand.inputs, &demand.outputs)
                {
                    Ok(ticket) => ticket,
                    Err(error) => return Ok(Err(buffer_code(error))),
                };
                self.high_water = stamp.sequence;
                self.entered = Some(stamp.clone());
                ticket
                    .enter(context.trusted()?)
                    .map_err(|_| ModularError::Retired)?;
                let result = {
                    let mut permit = ExecutionPermit {
                        context,
                        outputs: if matches!(
                            operation,
                            Operation::Prepare(_) | Operation::Application(_)
                        ) {
                            Some(&mut ticket)
                        } else {
                            None
                        },
                        violated: Cell::new(false),
                    };
                    let result = self
                        .application
                        .execute(operation, &mut permit)
                        .map_err(ModularError::Execution)?;
                    if permit.violated.get() {
                        return Err(ModularError::Retired);
                    }
                    result
                };
                if !ticket.complete() {
                    return Err(ModularError::Retired);
                }
                let body = match (operation, result) {
                    (Operation::Prepare(_), ApplicationOutput::Result(data)) => {
                        Body::Prepared { data }
                    }
                    (Operation::Application(_), ApplicationOutput::Result(data)) => {
                        Body::Application { data }
                    }
                    (Operation::Finish(_), ApplicationOutput::Terminal(data)) => {
                        Body::Finished { data }
                    }
                    (Operation::Abort(_), ApplicationOutput::Aborted) => Body::Aborted {},
                    _ => return Err(ModularError::Wire),
                };
                Ok(Ok(body))
            }
            Operation::BufferImportBegin(descriptor) => {
                let Some(slot) = self.imports.iter().position(Option::is_none) else {
                    return Ok(Err(Code::Capacity));
                };
                let source = match self.application.split_import(descriptor) {
                    Ok(source) => source,
                    Err(code) => return Ok(Err(application_rejection(code))),
                };
                let source_descriptor_digest =
                    import_descriptor_digest.ok_or(ModularError::Wire)?;
                let record = ImportRecord {
                    source_manifest_digest: source.manifest.manifest_digest.clone(),
                    source_descriptor_digest,
                    data: source.metadata,
                };
                self.staging.clear();
                if serde_json::to_writer(MetadataWriter(&mut self.staging), &record).is_err() {
                    return Ok(Err(Code::Capacity));
                }
                drop(record);
                let value = wire::parse_value(&self.staging)?;
                let integrity = wire::typed_digest(wire::PROFILE_DOMAIN, &value, None)?;
                let record: ImportRecord<A::ImportMetadata> =
                    serde_json::from_value(value).map_err(|_| ModularError::Wire)?;
                if A::check_import_metadata(descriptor, &record.data).is_err() {
                    return Ok(Err(Code::InvalidInput));
                }
                drop(record);
                let mut metadata_wire = Vec::new();
                if metadata_wire
                    .try_reserve_exact(IMPORT_METADATA_BYTES)
                    .is_err()
                {
                    return Ok(Err(Code::Capacity));
                }
                metadata_wire.extend_from_slice(&self.staging);
                self.staging.clear();
                let ticket = match self.pool.reserve_import(
                    &context.trusted()?,
                    source.manifest,
                    source.expected_binding,
                ) {
                    Ok(ticket) => ticket,
                    Err(error) => return Ok(Err(buffer_code(error))),
                };
                self.high_water = stamp.sequence;
                self.entered = Some(stamp.clone());
                let reference = ticket.commit();
                self.imports[slot] = Some(StoredImport {
                    id: reference.buffer_id,
                    wire: metadata_wire,
                    integrity,
                });
                Ok(Ok(Body::ImportReserved { reference }))
            }
            Operation::BufferSeal(input) => {
                let (manifest, payload) = match self.pool.inspect_import(&input.reference) {
                    Ok(pair) => pair,
                    Err(error) => return Ok(Err(buffer_code(error))),
                };
                if manifest.creating_request_digest != input.expected_import_request_digest
                    || manifest.imported_manifest_digest.as_ref()
                        != Some(&input.expected_source_manifest_digest)
                {
                    return Ok(Err(Code::InvalidInput));
                }
                let Some(stored) = self
                    .imports
                    .iter()
                    .flatten()
                    .find(|entry| entry.id == input.reference.buffer_id)
                else {
                    return Ok(Err(Code::BufferUnavailable));
                };
                let value = wire::parse_value(&stored.wire)?;
                if wire::typed_digest(wire::PROFILE_DOMAIN, &value, None)? != stored.integrity {
                    return Err(ModularError::Wire);
                }
                let metadata: ImportRecord<A::ImportMetadata> =
                    serde_json::from_value(value).map_err(|_| ModularError::Wire)?;
                if manifest.imported_manifest_digest.as_ref()
                    != Some(&metadata.source_manifest_digest)
                {
                    return Err(ModularError::Wire);
                }
                let data = match self
                    .application
                    .validate_import(&metadata.data, manifest, payload)
                {
                    Ok(data) => data,
                    Err(code) => return Ok(Err(application_rejection(code))),
                };
                self.high_water = stamp.sequence;
                self.entered = Some(stamp.clone());
                let manifest = self
                    .pool
                    .seal(&input.reference)
                    .map_err(|_| ModularError::Retired)?;
                Ok(Ok(Body::ImportSealed { manifest, data }))
            }
            Operation::BufferAppend(input) => {
                self.high_water = stamp.sequence;
                self.entered = Some(stamp.clone());
                self.pool
                    .append(&input.reference, &input.chunk)
                    .map_err(|_| ModularError::Retired)?;
                Ok(Ok(Body::BufferChanged {
                    reference: input.reference.clone(),
                }))
            }
            Operation::BufferRead(input) => {
                self.high_water = stamp.sequence;
                self.entered = Some(stamp.clone());
                let data = self
                    .pool
                    .read(&input.reference, input.index)
                    .map_err(|_| ModularError::Retired)?;
                Ok(Ok(Body::Chunk { data }))
            }
            Operation::BufferAbort(input) | Operation::BufferRelease(input) => {
                self.high_water = stamp.sequence;
                self.entered = Some(stamp.clone());
                let result = if matches!(operation, Operation::BufferAbort(_)) {
                    self.pool.abort_import(&input.reference)
                } else {
                    self.pool.release(&input.reference)
                };
                result.map_err(|_| ModularError::Retired)?;
                if let Some(slot) = self.imports.iter_mut().find(|slot| {
                    slot.as_ref()
                        .is_some_and(|entry| entry.id == input.reference.buffer_id)
                }) {
                    *slot = None;
                }
                Ok(Ok(Body::BufferChanged {
                    reference: input.reference.clone(),
                }))
            }
        }
    }
}

/// Verify a direct response without changing caller or owner state.
pub fn verify_response<A: Contract>(
    binding: &BufferBinding,
    request: &Request<AppOperation<A>>,
    bytes: &[u8],
) -> Result<AppResponse<A>, ModularError> {
    request.verify(binding)?;
    let response = AppResponse::<A>::decode(bytes, binding)?;
    if response.sequence != request.sequence || response.request_digest != request.request_digest {
        return Err(ModularError::Binding);
    }
    match &request.command {
        Command::Execute {
            operation,
            expected_predecessor_result_digest,
        } => {
            A::check_input(operation)?;
            if response.operation != operation.name() {
                return Err(ModularError::Wire);
            }
            match (A::allows(operation.name()), response.outcome, response.code) {
                (false, Outcome::RejectedBeforeExecution, Code::Role) => {}
                (false, _, _) | (true, _, Code::Role) => return Err(ModularError::Wire),
                _ => {}
            }
            if response.outcome == Outcome::Committed {
                let context = ExecutionContext {
                    binding: binding.clone(),
                    sequence: request.sequence,
                    request_digest: request.request_digest.clone(),
                    predecessor: expected_predecessor_result_digest.clone(),
                };
                check_core_response(operation, &response.body, &context)?;
                A::check_response(operation, &response.body, &context)?;
            }
        }
        Command::Result { .. } => {
            if response.operation != OperationName::Result
                || response.outcome != Outcome::Unavailable
            {
                return Err(ModularError::Wire);
            }
        }
        Command::Ack {
            original_request_digest,
            result_digest,
        } => {
            if response.operation != OperationName::Ack {
                return Err(ModularError::Wire);
            }
            if let Body::Acknowledged { stamp } = &response.body {
                if &stamp.original_request_digest != original_request_digest
                    || &stamp.result_digest != result_digest
                {
                    return Err(ModularError::Binding);
                }
            }
        }
    }
    Ok(response)
}

pub fn verify_retrieved<A: Contract>(
    binding: &BufferBinding,
    original: &Request<AppOperation<A>>,
    query: &Request<AppOperation<A>>,
    bytes: &[u8],
) -> Result<AppResponse<A>, ModularError> {
    query.verify(binding)?;
    let Command::Result {
        original_request_digest,
    } = &query.command
    else {
        return Err(ModularError::Wire);
    };
    if query.binding != *binding
        || original.binding != *binding
        || query.sequence != original.sequence
        || original_request_digest != &original.request_digest
    {
        return Err(ModularError::Binding);
    }
    let response = verify_response::<A>(binding, original, bytes)?;
    if !matches!(
        response.outcome,
        Outcome::Committed | Outcome::Indeterminate
    ) {
        return Err(ModularError::Wire);
    }
    Ok(response)
}

/// u32BE framing over host-owned I/O. The host must supply a bounded supervisor or
/// deadline-aware I/O; this helper does not install a process/lifetime policy.
pub fn serve<A: Application, R: Read, W: Write>(
    owner: &mut Owner<A>,
    reader: &mut R,
    writer: &mut W,
) -> Result<(), ModularError> {
    let result = catch_unwind(AssertUnwindSafe(|| loop {
        let Some(frame) = crate::local::read_local_frame(reader).map_err(|_| ModularError::Wire)?
        else {
            return Ok(());
        };
        let response = owner.process(&frame)?;
        crate::local::write_local_frame(writer, response).map_err(|_| ModularError::Wire)?;
        writer.flush().map_err(|_| ModularError::Wire)?;
    }));
    owner.retire_channel();
    result.unwrap_or(Err(ModularError::Retired))
}

fn check_core_response<P, C, I, F, R, V, T>(
    operation: &Operation<P, C, I, F>,
    body: &Body<R, V, T>,
    context: &ExecutionContext,
) -> Result<(), ModularError> {
    match (operation, body) {
        (Operation::BufferSeal(input), Body::ImportSealed { manifest, .. }) => {
            manifest
                .verify(&context.binding)
                .map_err(|_| ModularError::Wire)?;
            if manifest.reference() != input.reference
                || manifest.creating_request_digest != input.expected_import_request_digest
                || manifest.imported_manifest_digest.as_ref()
                    != Some(&input.expected_source_manifest_digest)
            {
                return Err(ModularError::Binding);
            }
        }
        (Operation::BufferImportBegin(_), Body::ImportReserved { reference }) => {
            if reference.generation != context.binding.generation
                || reference.buffer_id == 0
                || reference.buffer_id > MAX_ID
            {
                return Err(ModularError::Binding);
            }
        }
        (Operation::BufferAppend(input), Body::BufferChanged { reference })
            if &input.reference != reference =>
        {
            return Err(ModularError::Binding)
        }
        (
            Operation::BufferRelease(input) | Operation::BufferAbort(input),
            Body::BufferChanged { reference },
        ) if &input.reference != reference => return Err(ModularError::Binding),
        (Operation::BufferRead(input), Body::Chunk { data }) => {
            if data.index != input.index || data.manifest_digest != input.expected_manifest_digest {
                return Err(ModularError::Binding);
            }
            data.decoded().map_err(|_| ModularError::Wire)?;
        }
        _ => {}
    }
    Ok(())
}

#[cfg(test)]
pub(crate) mod test_contract {
    use super::*;
    use crate::modular_wire::Empty;
    use std::cell::Cell;
    use std::rc::Rc;

    pub struct TextApplication(pub Rc<Cell<usize>>);
    impl Contract for TextApplication {
        type Prepare = usize;
        type Command = Empty;
        type ImportDescriptor = Empty;
        type ImportMetadata = Empty;
        type Finish = Empty;
        type Result = String;
        type Imported = Empty;
        type Terminal = Empty;
        fn descriptor() -> &'static [u8] {
            br#"{"schema":"ncp.test.text-bound.v1","status":"test-only"}"#
        }
        fn allows(operation: OperationName) -> bool {
            matches!(operation, OperationName::Prepare | OperationName::Finish)
        }
        fn check_input(operation: &AppOperation<Self>) -> Result<(), ModularError> {
            if matches!(operation, Operation::Prepare(length) if *length > 65_536) {
                return Err(ModularError::Capacity);
            }
            Ok(())
        }
        fn check_response(
            operation: &AppOperation<Self>,
            body: &AppBody<Self>,
            _: &ExecutionContext,
        ) -> Result<(), ModularError> {
            if let (Operation::Prepare(length), Body::Prepared { data }) = (operation, body) {
                if data.len() != *length {
                    return Err(ModularError::Wire);
                }
            }
            Ok(())
        }
        fn check_import_metadata(_: &Empty, _: &Empty) -> Result<(), ModularError> {
            Err(ModularError::Wire)
        }
    }
    impl Application for TextApplication {
        fn admit(
            &self,
            _: &AppOperation<Self>,
            _: &AdmissionView<'_>,
        ) -> Result<AdmissionDemand, Code> {
            Ok(AdmissionDemand::default())
        }
        fn execute(
            &mut self,
            operation: &AppOperation<Self>,
            _: &mut ExecutionPermit<'_, '_>,
        ) -> Result<ApplicationOutput<String, Empty>, Diagnostic> {
            self.0.set(self.0.get() + 1);
            match operation {
                Operation::Prepare(length) => Ok(ApplicationOutput::Result("x".repeat(*length))),
                Operation::Finish(_) => Ok(ApplicationOutput::Terminal(Empty {})),
                _ => Err(Diagnostic::Backend),
            }
        }
        fn split_import<'a>(&'a self, _: &'a Empty) -> Result<ImportSource<'a, Empty>, Code> {
            Err(Code::Role)
        }
        fn validate_import(&self, _: &Empty, _: &BufferManifest, _: &[u8]) -> Result<Empty, Code> {
            Err(Code::Role)
        }
    }
    pub fn binding() -> BufferBinding {
        BufferBinding {
            profile_digest: profile_digest().unwrap(),
            application_digest: wire::typed_digest(
                wire::PROFILE_DOMAIN,
                &wire::parse_value(TextApplication::descriptor()).unwrap(),
                None,
            )
            .unwrap(),
            run_id: "11111111-1111-4111-8111-111111111111".into(),
            endpoint_id: "22222222-2222-4222-8222-222222222222".into(),
            generation: "33333333-3333-4333-8333-333333333333".into(),
        }
    }

    #[test]
    fn exact_frame_result_and_one_byte_overflow_have_distinct_execution_outcomes() {
        let blank = AppResponse::<TextApplication> {
            schema: wire::RESPONSE_SCHEMA.into(),
            binding: binding(),
            sequence: 1,
            operation: OperationName::Prepare,
            request_digest: "0".repeat(64),
            outcome: Outcome::Committed,
            code: Code::Ok,
            body: Body::Prepared {
                data: String::new(),
            },
            result_digest: "0".repeat(64),
        };
        let length = modular_buffer::FRAME_BYTES - serde_json::to_vec(&blank).unwrap().len();
        for (amount, outcome) in [
            (length, Outcome::Committed),
            (length + 1, Outcome::Indeterminate),
        ] {
            let calls = Rc::new(Cell::new(0));
            let mut owner = Owner::new(
                binding(),
                TextApplication(calls.clone()),
                vec!["a".repeat(64)],
            )
            .unwrap();
            let request = Request::encode(
                binding(),
                1,
                Command::Execute {
                    expected_predecessor_result_digest: None,
                    operation: AppOperation::<TextApplication>::Prepare(amount),
                },
            )
            .unwrap();
            let result = owner.process(&request).unwrap().to_vec();
            assert_eq!(
                AppResponse::<TextApplication>::decode(&result, &binding())
                    .unwrap()
                    .outcome,
                outcome
            );
            assert_eq!(calls.get(), 1);
            assert_eq!(owner.high_water(), 1);
            if outcome == Outcome::Committed {
                assert_eq!(result.len(), modular_buffer::FRAME_BYTES);
            } else {
                assert_eq!(owner.lifecycle(), Lifecycle::Retired);
                assert!(result.len() < modular_buffer::FRAME_BYTES);
            }
        }
    }

    #[test]
    fn maximum_sequence_is_consumed_once_without_wrapping() {
        let calls = Rc::new(Cell::new(0));
        let mut owner = Owner::new(
            binding(),
            TextApplication(calls.clone()),
            vec!["a".repeat(64)],
        )
        .unwrap();
        owner.high_water = MAX_ID - 1;
        let request = Request::encode(
            binding(),
            MAX_ID,
            Command::Execute {
                expected_predecessor_result_digest: None,
                operation: AppOperation::<TextApplication>::Prepare(0),
            },
        )
        .unwrap();
        let response =
            AppResponse::<TextApplication>::decode(owner.process(&request).unwrap(), &binding())
                .unwrap();
        let ack = Request::<AppOperation<TextApplication>>::encode(
            binding(),
            MAX_ID,
            Command::Ack {
                original_request_digest: response.request_digest,
                result_digest: response.result_digest,
            },
        )
        .unwrap();
        owner.process(&ack).unwrap();
        let another = Request::encode(
            binding(),
            MAX_ID,
            Command::Execute {
                expected_predecessor_result_digest: owner.predecessor.clone(),
                operation: AppOperation::<TextApplication>::Finish(Empty {}),
            },
        )
        .unwrap();
        assert_eq!(
            AppResponse::<TextApplication>::decode(owner.process(&another).unwrap(), &binding())
                .unwrap()
                .outcome,
            Outcome::Unavailable
        );
        assert_eq!(owner.high_water(), MAX_ID);
        assert_eq!(calls.get(), 1);
    }

    #[test]
    fn each_initial_frame_reservation_failure_precedes_backend_execution() {
        for position in 0..2 {
            let calls = Rc::new(Cell::new(0));
            {
                let _fault = wire::fail_frame_allocation_after(position);
                assert!(matches!(
                    Owner::new(
                        binding(),
                        TextApplication(calls.clone()),
                        vec!["a".repeat(64)]
                    ),
                    Err(ModularError::Capacity)
                ));
                assert_eq!(calls.get(), 0);
            }
            let mut owner = Owner::new(
                binding(),
                TextApplication(calls.clone()),
                vec!["a".repeat(64)],
            )
            .unwrap();
            let request = Request::encode(
                binding(),
                1,
                Command::Execute {
                    expected_predecessor_result_digest: None,
                    operation: AppOperation::<TextApplication>::Prepare(0),
                },
            )
            .unwrap();
            owner.process(&request).unwrap();
            assert_eq!(calls.get(), 1);
        }
    }
}
