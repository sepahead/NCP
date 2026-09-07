//! One-pending-request client. A channel failure preserves evidence and forbids retry.
//! Pure response verification is available separately in `modular_owner`.

use std::io::{Read, Write};
use std::marker::PhantomData;
use std::panic::{catch_unwind, AssertUnwindSafe};

use crate::modular_buffer::{BufferBinding, MAX_ID};
use crate::modular_owner::{self, AppOperation, AppResponse, Contract};
use crate::modular_wire::{self as wire, Command, ModularError, Outcome, Request};

pub const CLIENT_LOGICAL_OVERHEAD: usize = 1_085_440;

/// Logical storage includes six bounded frame extents, three parsed extents,
/// digest/sort, decoded-chunk and explicit UTF8 scratch, and fixed identity state.
/// These are logical extents, not an allocator, application-object, or RSS bound.
/// A caller-held typed original occupies one parsed extent during verification.
/// Independently retained originals, responses, and artifacts need caller accounting.
pub struct Client<A: Contract> {
    binding: BufferBinding,
    next_sequence: Option<u64>,
    predecessor: Option<String>,
    pending: Vec<u8>,
    result_digest: Option<String>,
    retired: bool,
    contract: PhantomData<A>,
}

impl<A: Contract> Client<A> {
    pub fn new(binding: BufferBinding) -> Result<Self, ModularError> {
        binding.validate().map_err(|_| ModularError::Binding)?;
        let application = wire::typed_digest(
            wire::PROFILE_DOMAIN,
            &wire::parse_value(A::descriptor())?,
            None,
        )?;
        if binding.profile_digest != modular_owner::profile_digest()?
            || binding.application_digest != application
        {
            return Err(ModularError::Binding);
        }
        Ok(Self {
            binding,
            next_sequence: Some(1),
            predecessor: None,
            pending: wire::frame_slot()?,
            result_digest: None,
            retired: false,
            contract: PhantomData,
        })
    }

    pub fn binding(&self) -> &BufferBinding {
        &self.binding
    }
    pub fn next_sequence(&self) -> Option<u64> {
        self.next_sequence
    }
    pub fn predecessor(&self) -> Option<&str> {
        self.predecessor.as_deref()
    }
    pub fn pending_request(&self) -> Option<&[u8]> {
        (!self.pending.is_empty()).then_some(self.pending.as_slice())
    }
    pub fn is_retired(&self) -> bool {
        self.retired
    }
    pub fn retire_channel(&mut self) {
        self.retired = true;
    }

    /// Local preflight only. No channel write occurs, and failure leaves state intact.
    /// The returned immutable bytes can be durably journaled before dispatch.
    pub fn begin(&mut self, operation: AppOperation<A>) -> Result<&[u8], ModularError> {
        if self.retired {
            return Err(ModularError::Retired);
        }
        if !self.pending.is_empty() {
            return Err(ModularError::Binding);
        }
        let sequence = self.next_sequence.ok_or(ModularError::Capacity)?;
        A::check_input(&operation)?;
        if !A::allows(operation.name()) {
            return Err(ModularError::Binding);
        }
        let bytes = Request::encode(
            self.binding.clone(),
            sequence,
            Command::Execute {
                expected_predecessor_result_digest: self.predecessor.clone(),
                operation,
            },
        )?;
        // Reopen the exact representation before publishing pending state.
        let parsed = Request::<AppOperation<A>>::decode(&bytes, &self.binding)?;
        let Command::Execute { operation, .. } = &parsed.command else {
            return Err(ModularError::Wire);
        };
        A::check_input(operation)?;
        drop(parsed);
        self.pending.extend_from_slice(&bytes);
        Ok(&self.pending)
    }

    fn original(&self) -> Result<Request<AppOperation<A>>, ModularError> {
        if self.retired {
            return Err(ModularError::Retired);
        }
        Request::decode(&self.pending, &self.binding)
    }

    pub fn result_query(&self) -> Result<Vec<u8>, ModularError> {
        let original = self.original()?;
        Request::<AppOperation<A>>::encode(
            self.binding.clone(),
            original.sequence,
            Command::Result {
                original_request_digest: original.request_digest,
            },
        )
    }

    pub fn acknowledgement(&self) -> Result<Vec<u8>, ModularError> {
        let original = self.original()?;
        let result_digest = self.result_digest.clone().ok_or(ModularError::Binding)?;
        Request::<AppOperation<A>>::encode(
            self.binding.clone(),
            original.sequence,
            Command::Ack {
                original_request_digest: original.request_digest,
                result_digest,
            },
        )
    }

    /// Accept only the exact original outcome. Invalid peer bytes retire the client.
    pub fn observe(&mut self, bytes: &[u8]) -> Result<AppResponse<A>, ModularError> {
        let result = (|| {
            let original = self.original()?;
            let response = modular_owner::verify_response::<A>(&self.binding, &original, bytes)?;
            self.apply_outcome(&response)?;
            Ok(response)
        })();
        if result.is_err() {
            self.retire_channel();
        }
        result
    }

    pub fn observe_query(&mut self, bytes: &[u8]) -> Result<AppResponse<A>, ModularError> {
        let result = (|| {
            let original = self.original()?;
            let query = Request::<AppOperation<A>>::decode(&self.result_query()?, &self.binding)?;
            // Unavailable is correlated to the query. Retained bytes belong to the original.
            let shape = wire::parse_value(bytes)?;
            let unavailable =
                shape.get("operation").and_then(serde_json::Value::as_str) == Some("result");
            drop(shape);
            if unavailable {
                return modular_owner::verify_response::<A>(&self.binding, &query, bytes);
            }
            let response =
                modular_owner::verify_retrieved::<A>(&self.binding, &original, &query, bytes)?;
            self.apply_outcome(&response)?;
            Ok(response)
        })();
        if result.is_err() {
            self.retire_channel();
        }
        result
    }

    fn apply_outcome(&mut self, response: &AppResponse<A>) -> Result<(), ModularError> {
        if let Some(known) = &self.result_digest {
            if response.outcome != Outcome::Committed || known != &response.result_digest {
                return Err(ModularError::Binding);
            }
        }
        match response.outcome {
            Outcome::Committed => self.result_digest = Some(response.result_digest.clone()),
            Outcome::RejectedBeforeExecution => {
                self.pending.clear();
                self.result_digest = None;
            }
            Outcome::Indeterminate => {
                self.result_digest = Some(response.result_digest.clone());
                self.retire_channel();
            }
            Outcome::NotAdmitted | Outcome::Unavailable => {}
            Outcome::Acknowledged => return Err(ModularError::Wire),
        }
        Ok(())
    }

    /// Only a verified ACK advances sequence/head and clears a committed request.
    pub fn observe_acknowledgement(
        &mut self,
        bytes: &[u8],
    ) -> Result<AppResponse<A>, ModularError> {
        let result = (|| {
            let ack = Request::<AppOperation<A>>::decode(&self.acknowledgement()?, &self.binding)?;
            let response = modular_owner::verify_response::<A>(&self.binding, &ack, bytes)?;
            if response.outcome == Outcome::Acknowledged {
                self.predecessor = self.result_digest.take();
                self.next_sequence = (ack.sequence < MAX_ID).then(|| ack.sequence + 1);
                self.pending.clear();
            }
            Ok(response)
        })();
        if result.is_err() {
            self.retire_channel();
        }
        result
    }

    /// Dispatch a prepared request exactly once. The host supplies deadlines.
    pub fn dispatch<R: Read, W: Write>(
        &mut self,
        reader: &mut R,
        writer: &mut W,
    ) -> Result<AppResponse<A>, ModularError> {
        if self.retired || self.pending.is_empty() || self.result_digest.is_some() {
            return Err(ModularError::Binding);
        }
        let result = catch_unwind(AssertUnwindSafe(|| {
            crate::local::write_local_frame(writer, &self.pending)
                .map_err(|_| ModularError::Retired)?;
            writer.flush().map_err(|_| ModularError::Retired)?;
            let bytes = crate::local::read_local_frame(reader)
                .map_err(|_| ModularError::Retired)?
                .ok_or(ModularError::Retired)?;
            self.observe(&bytes)
        }))
        .unwrap_or(Err(ModularError::Retired));
        if result.is_err() {
            self.retire_channel();
        }
        result
    }

    /// A failed ACK exchange retires the channel and retains unresolved pending bytes.
    pub fn dispatch_acknowledgement<R: Read, W: Write>(
        &mut self,
        reader: &mut R,
        writer: &mut W,
    ) -> Result<AppResponse<A>, ModularError> {
        let ack = self.acknowledgement()?;
        let result = catch_unwind(AssertUnwindSafe(|| {
            crate::local::write_local_frame(writer, &ack).map_err(|_| ModularError::Retired)?;
            writer.flush().map_err(|_| ModularError::Retired)?;
            let bytes = crate::local::read_local_frame(reader)
                .map_err(|_| ModularError::Retired)?
                .ok_or(ModularError::Retired)?;
            self.observe_acknowledgement(&bytes)
        }))
        .unwrap_or(Err(ModularError::Retired));
        if result.is_err() {
            self.retire_channel();
        }
        result
    }

    pub fn dispatch_query<R: Read, W: Write>(
        &mut self,
        reader: &mut R,
        writer: &mut W,
    ) -> Result<AppResponse<A>, ModularError> {
        let query = self.result_query()?;
        let result = catch_unwind(AssertUnwindSafe(|| {
            crate::local::write_local_frame(writer, &query).map_err(|_| ModularError::Retired)?;
            writer.flush().map_err(|_| ModularError::Retired)?;
            let bytes = crate::local::read_local_frame(reader)
                .map_err(|_| ModularError::Retired)?
                .ok_or(ModularError::Retired)?;
            self.observe_query(&bytes)
        }))
        .unwrap_or(Err(ModularError::Retired));
        if result.is_err() {
            self.retire_channel();
        }
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::modular_owner::{
        test_contract::{binding, TextApplication},
        Owner,
    };
    use std::cell::Cell;
    use std::rc::Rc;

    #[test]
    fn maximum_ack_enters_exhaustion_without_advancing_past_the_safe_integer() {
        let mut client = Client::<TextApplication>::new(binding()).unwrap();
        client.next_sequence = Some(MAX_ID);
        let pending = client
            .begin(AppOperation::<TextApplication>::Prepare(0))
            .unwrap()
            .to_vec();
        // A closed synthetic response models a caller that has already reached this boundary.
        let original =
            Request::<AppOperation<TextApplication>>::decode(&pending, &binding()).unwrap();
        let response = wire::Response::<String, wire::Empty, wire::Empty> {
            schema: wire::RESPONSE_SCHEMA.into(),
            binding: binding(),
            sequence: MAX_ID,
            operation: wire::OperationName::Prepare,
            request_digest: original.request_digest,
            outcome: Outcome::Committed,
            code: wire::Code::Ok,
            body: wire::Body::Prepared {
                data: String::new(),
            },
            result_digest: String::new(),
        };
        let mut bytes = wire::frame_slot().unwrap();
        wire::seal_into(response, "result_digest", wire::RESPONSE_SCHEMA, &mut bytes).unwrap();
        client.observe(&bytes).unwrap();
        let ack = Request::<AppOperation<TextApplication>>::decode(
            &client.acknowledgement().unwrap(),
            &binding(),
        )
        .unwrap();
        let Command::Ack {
            original_request_digest,
            result_digest,
        } = ack.command
        else {
            panic!("ack")
        };
        let response = wire::Response::<String, wire::Empty, wire::Empty> {
            schema: wire::RESPONSE_SCHEMA.into(),
            binding: binding(),
            sequence: MAX_ID,
            operation: wire::OperationName::Ack,
            request_digest: ack.request_digest,
            outcome: Outcome::Acknowledged,
            code: wire::Code::ResultReleased,
            body: wire::Body::Acknowledged {
                stamp: wire::AckStamp {
                    sequence: MAX_ID,
                    original_request_digest,
                    result_digest,
                },
            },
            result_digest: String::new(),
        };
        wire::seal_into(response, "result_digest", wire::RESPONSE_SCHEMA, &mut bytes).unwrap();
        client.observe_acknowledgement(&bytes).unwrap();
        assert_eq!(client.next_sequence(), None);
        assert!(client.pending_request().is_none());
        assert!(client
            .begin(AppOperation::<TextApplication>::Prepare(0))
            .is_err());
        // The ordinary initial state still performs a real owner/client exchange.
        let mut owner = Owner::new(
            binding(),
            TextApplication(Rc::new(Cell::new(0))),
            vec!["a".repeat(64)],
        )
        .unwrap();
        let mut client = Client::<TextApplication>::new(binding()).unwrap();
        let request = client
            .begin(AppOperation::<TextApplication>::Prepare(0))
            .unwrap()
            .to_vec();
        client.observe(owner.process(&request).unwrap()).unwrap();
        client
            .observe_acknowledgement(owner.process(&client.acknowledgement().unwrap()).unwrap())
            .unwrap();
        assert_eq!(client.next_sequence(), Some(2));
    }
}
