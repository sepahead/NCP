//! Test-only installed counter and byte producer. No scientific application claim.
use ncp_core::modular_buffer::{BufferBinding, BufferManifest, OutputSpec};
use ncp_core::modular_owner::*;
use ncp_core::modular_wire::*;
use serde::{Deserialize, Serialize};
use std::cell::Cell;
use std::rc::Rc;

pub const SEMANTIC: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const DESCRIPTOR: &[u8] = br#"{"schema":"ncp.test.counter.v1","status":"test-only","role":"counter","data_shapes":"closed test types in support/modular_fixture.rs"}"#;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Prepare {
    pub initial: u64,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum Change {
    Add { amount: u64, output_bytes: usize },
    Panic,
    BackendError,
    AdmissionRole,
    InvalidOutput,
    OmitOutput,
    IgnoreWriteError,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Import {
    pub manifest: BufferManifest,
    pub source: BufferBinding,
    pub label: String,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Metadata {
    pub byte_length: usize,
    pub label: String,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Finish {
    pub allocate: bool,
    pub demand: bool,
}
#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Output {
    pub value: u64,
    pub manifest: Option<BufferManifest>,
}
#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Imported {
    pub byte_length: usize,
    pub label: String,
}
#[derive(Debug, Serialize, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct Terminal {
    pub value: u64,
}

pub struct Counter {
    pub calls: Rc<Cell<usize>>,
    value: u64,
}
impl Counter {
    pub fn new(calls: Rc<Cell<usize>>) -> Self {
        Self { calls, value: 0 }
    }
}
impl Contract for Counter {
    type Prepare = Prepare;
    type Command = Change;
    type ImportDescriptor = Import;
    type ImportMetadata = Metadata;
    type Finish = Finish;
    type Result = Output;
    type Imported = Imported;
    type Terminal = Terminal;
    fn descriptor() -> &'static [u8] {
        DESCRIPTOR
    }
    fn allows(operation: OperationName) -> bool {
        operation != OperationName::Abort
    }
    fn check_input(operation: &AppOperation<Self>) -> Result<(), ModularError> {
        let invalid = match operation {
            Operation::Prepare(input) => input.initial > 100,
            Operation::Application(Change::Add {
                amount,
                output_bytes,
            }) => *amount > 100 || *output_bytes > 8_388_608,
            Operation::BufferImportBegin(input) => input.label.len() > 2_000,
            _ => false,
        };
        if invalid {
            Err(ModularError::Wire)
        } else {
            Ok(())
        }
    }
    fn check_response(
        operation: &AppOperation<Self>,
        body: &AppBody<Self>,
        context: &ExecutionContext,
    ) -> Result<(), ModularError> {
        if let Body::Prepared { data } | Body::Application { data } = body {
            if let Operation::Application(Change::Add { output_bytes, .. }) = operation {
                if data
                    .manifest
                    .as_ref()
                    .map_or(0, |manifest| manifest.byte_length)
                    != *output_bytes
                {
                    return Err(ModularError::Wire);
                }
            }
            if data.value > 10_000 {
                return Err(ModularError::Wire);
            }
            if let Some(manifest) = &data.manifest {
                manifest
                    .verify(context.binding())
                    .map_err(|_| ModularError::Wire)?;
                if manifest.creating_request_digest != context.request_digest()
                    || manifest.causal_predecessor.as_deref() != context.predecessor()
                {
                    return Err(ModularError::Binding);
                }
            }
        }
        Ok(())
    }
    fn check_import_metadata(descriptor: &Import, metadata: &Metadata) -> Result<(), ModularError> {
        if metadata.byte_length != descriptor.manifest.byte_length
            || metadata.label != descriptor.label
        {
            return Err(ModularError::Binding);
        }
        Ok(())
    }
}
impl Application for Counter {
    fn admit(
        &self,
        op: &AppOperation<Self>,
        _: &AdmissionView<'_>,
    ) -> Result<AdmissionDemand, Code> {
        let length = match op {
            Operation::Application(Change::AdmissionRole) => return Err(Code::Role),
            Operation::Application(Change::Add { amount: 0, .. }) => {
                return Err(Code::InvalidInput)
            }
            Operation::Application(Change::Add { output_bytes, .. }) => *output_bytes,
            Operation::Application(Change::OmitOutput | Change::IgnoreWriteError) => 4,
            Operation::Finish(Finish { demand: true, .. }) => 4,
            _ => 0,
        };
        Ok(AdmissionDemand {
            inputs: vec![],
            outputs: if length == 0 {
                vec![]
            } else {
                vec![OutputSpec {
                    semantic_digest: SEMANTIC.into(),
                    byte_length: length,
                }]
            },
        })
    }
    fn execute(
        &mut self,
        op: &AppOperation<Self>,
        permit: &mut ExecutionPermit<'_, '_>,
    ) -> Result<ApplicationOutput<Output, Terminal>, Diagnostic> {
        self.calls.set(self.calls.get() + 1);
        let mut manifest = None;
        match op {
            Operation::Prepare(input) => self.value = input.initial,
            Operation::Application(Change::Add {
                amount,
                output_bytes,
            }) => {
                self.value += amount;
                let mut offset = 0;
                while offset < *output_bytes {
                    let count = (*output_bytes - offset).min(32_768);
                    let bytes: Vec<u8> =
                        (offset..offset + count).map(|i| (i % 251) as u8).collect();
                    permit
                        .write_output(0, offset, &bytes)
                        .map_err(|_| Diagnostic::Backend)?;
                    offset += count;
                }
                if *output_bytes > 0 {
                    manifest = Some(permit.seal_output(0).map_err(|_| Diagnostic::Backend)?);
                }
            }
            Operation::Application(Change::Panic) => panic!("test-only backend failure"),
            Operation::Application(Change::BackendError) => return Err(Diagnostic::Backend),
            Operation::Application(Change::AdmissionRole) => return Err(Diagnostic::Internal),
            Operation::Application(Change::InvalidOutput) => self.value = 10_001,
            Operation::Application(Change::OmitOutput) => {}
            Operation::Application(Change::IgnoreWriteError) => {
                let _ = permit.write_output(0, 1, b"bad");
            }
            Operation::Finish(input) => {
                if input.allocate {
                    let _ = permit.seal_output(0);
                }
                return Ok(ApplicationOutput::Terminal(Terminal { value: self.value }));
            }
            Operation::Abort(_) => return Ok(ApplicationOutput::Aborted),
            _ => return Err(Diagnostic::Backend),
        }
        Ok(ApplicationOutput::Result(Output {
            value: self.value,
            manifest,
        }))
    }
    fn split_import<'a>(
        &'a self,
        descriptor: &'a Import,
    ) -> Result<ImportSource<'a, Metadata>, Code> {
        Ok(ImportSource {
            manifest: &descriptor.manifest,
            expected_binding: &descriptor.source,
            metadata: Metadata {
                byte_length: descriptor.manifest.byte_length,
                label: descriptor.label.clone(),
            },
        })
    }
    fn validate_import(
        &self,
        metadata: &Metadata,
        _: &BufferManifest,
        bytes: &[u8],
    ) -> Result<Imported, Code> {
        if bytes.len() != metadata.byte_length {
            return Err(Code::InvalidInput);
        }
        Ok(Imported {
            byte_length: bytes.len(),
            label: metadata.label.clone(),
        })
    }
}

pub fn binding() -> BufferBinding {
    BufferBinding {
        profile_digest: profile_digest().unwrap(),
        application_digest: typed_digest(PROFILE_DOMAIN, &parse_value(DESCRIPTOR).unwrap(), None)
            .unwrap(),
        run_id: "11111111-1111-4111-8111-111111111111".into(),
        endpoint_id: "22222222-2222-4222-8222-222222222222".into(),
        generation: "33333333-3333-4333-8333-333333333333".into(),
    }
}
