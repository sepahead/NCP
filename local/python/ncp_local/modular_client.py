"""Independent one-pending client. Unknown channel outcomes never grant retry."""
from __future__ import annotations

from typing import BinaryIO

from . import wire as framing
from .modular_buffer import BufferBinding, MAX_ID
from .modular_owner import profile_digest, verify_response, verify_retrieved
from .modular_wire import (Ack, Command, Contract, Execute, ModularError, Name, Operation,
                           Outcome, Query, Request, Response, PROFILE_DOMAIN, operation_name, parse, typed_digest)

CLIENT_LOGICAL_OVERHEAD = 1_085_440


class Client:
    """Six frame extents, three parsed extents, explicit UTF8 scratch, and fixed state.

    The logical allowance includes one caller-held typed original during verification.
    Extra caller-retained copies and installed application objects need separate bounds.
    This is not an allocator or process RSS guarantee.
    """
    def __init__(self, binding: BufferBinding, contract: type[Contract]) -> None:
        binding.validate()
        if binding.profile_digest != profile_digest() or binding.application_digest != typed_digest(PROFILE_DOMAIN, parse(contract.descriptor())):
            raise ModularError("binding")
        self._binding = binding
        self._contract = contract
        self._next_sequence = 1
        self._predecessor = None
        self._pending = None
        self._result_digest = None
        self._retired = False

    @property
    def binding(self) -> BufferBinding: return self._binding
    @property
    def next_sequence(self) -> int | None: return self._next_sequence
    @property
    def predecessor(self) -> str | None: return self._predecessor
    @property
    def pending_request(self) -> bytes | None: return self._pending
    @property
    def is_retired(self) -> bool: return self._retired

    def retire_channel(self) -> None: self._retired = True

    def begin(self, operation: Operation) -> bytes:
        """Complete local preflight and immutable journal bytes before any write."""
        if self._retired: raise ModularError("retired")
        if self._pending is not None: raise ModularError("binding")
        if self._next_sequence is None: raise ModularError("capacity")
        self._contract.check_input(operation)
        if not self._contract.allows(operation_name(operation)): raise ModularError("binding")
        payload = Request.create(self.binding, self._next_sequence, Execute(self._predecessor, operation))
        parsed = Request.decode(payload, self.binding, self._contract)
        self._contract.check_input(parsed.command.operation)
        self._pending = payload
        return payload

    def _original(self) -> Request:
        if self._retired: raise ModularError("retired")
        if self._pending is None: raise ModularError("binding")
        return Request.decode(self._pending, self.binding, self._contract)

    def result_query(self) -> bytes:
        original = self._original()
        return Request.create(self.binding, original.sequence, Query(original.request_digest))

    def acknowledgement(self) -> bytes:
        original = self._original()
        if self._result_digest is None: raise ModularError("binding")
        return Request.create(self.binding, original.sequence, Ack(original.request_digest, self._result_digest))

    def _apply(self, response: Response) -> None:
        if self._result_digest is not None and (response.outcome != Outcome.COMMITTED or response.result_digest != self._result_digest):
            raise ModularError("binding")
        if response.outcome == Outcome.COMMITTED: self._result_digest = response.result_digest
        elif response.outcome == Outcome.REJECTED:
            self._pending = None
            self._result_digest = None
        elif response.outcome == Outcome.INDETERMINATE:
            self._result_digest = response.result_digest
            self.retire_channel()
        elif response.outcome not in (Outcome.NOT_ADMITTED, Outcome.UNAVAILABLE): raise ModularError("wire")

    def observe(self, payload: bytes | memoryview) -> Response:
        try:
            original = self._original()
            response = verify_response(self.binding, original, payload, self._contract)
            self._apply(response)
            return response
        except BaseException:
            self.retire_channel()
            raise

    def observe_query(self, payload: bytes | memoryview) -> Response:
        try:
            original = self._original()
            query = Request.decode(self.result_query(), self.binding, self._contract)
            shape = parse(payload)
            unavailable = shape.get("operation") == Name.RESULT.value
            del shape
            if unavailable: return verify_response(self.binding, query, payload, self._contract)
            response = verify_retrieved(self.binding, original, query, payload, self._contract)
            self._apply(response)
            return response
        except BaseException:
            self.retire_channel()
            raise

    def observe_acknowledgement(self, payload: bytes | memoryview) -> Response:
        try:
            ack = Request.decode(self.acknowledgement(), self.binding, self._contract)
            response = verify_response(self.binding, ack, payload, self._contract)
            if response.outcome == Outcome.ACKNOWLEDGED:
                self._predecessor = self._result_digest
                self._result_digest = None
                self._next_sequence = ack.sequence + 1 if ack.sequence < MAX_ID else None
                self._pending = None
            return response
        except BaseException:
            self.retire_channel()
            raise

    def dispatch(self, reader: BinaryIO, writer: BinaryIO, *, deadline: float) -> Response:
        """One explicit dispatch, with an absolute monotonic deadline and no retry."""
        if self._retired or self._pending is None or self._result_digest is not None: raise ModularError("binding")
        try:
            framing.write_local_frame(writer, self._pending, deadline=deadline)
            payload = framing.read_local_frame(reader, deadline=deadline)
            if payload is None: raise ModularError("retired")
            return self.observe(payload)
        except BaseException as error:
            self.retire_channel()
            raise ModularError("retired") from error

    def dispatch_acknowledgement(self, reader: BinaryIO, writer: BinaryIO, *, deadline: float) -> Response:
        payload = self.acknowledgement()
        try:
            framing.write_local_frame(writer, payload, deadline=deadline)
            response = framing.read_local_frame(reader, deadline=deadline)
            if response is None: raise ModularError("retired")
            return self.observe_acknowledgement(response)
        except BaseException as error:
            self.retire_channel()
            raise ModularError("retired") from error

    def dispatch_query(self, reader: BinaryIO, writer: BinaryIO, *, deadline: float) -> Response:
        payload = self.result_query()
        try:
            framing.write_local_frame(writer, payload, deadline=deadline)
            response = framing.read_local_frame(reader, deadline=deadline)
            if response is None: raise ModularError("retired")
            return self.observe_query(response)
        except BaseException as error:
            self.retire_channel()
            raise ModularError("retired") from error
