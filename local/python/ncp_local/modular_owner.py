"""Independent synchronous modular owner with local reservation tickets.

Application types are installed by the host. This SDK supplies no application
schema, arbitrary-method dispatch, runtime launcher, or scientific acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import io
import math
import os
import select
import struct
import time
from typing import BinaryIO, Protocol

from . import wire as framing

from .modular_buffer import (BufferBinding, BufferError, BufferManifest, BufferPool, BufferUsage,
                             InputSpec, InputView, OutputReservation, OutputSpec, TrustedHostCreationContext, LIVE_SLOTS, MAX_ID, admit_composition)
from .modular_profile import CORE_DESCRIPTOR
from .modular_wire import (Ack, AckStamp, Append, Application, Body, BodyKind, BufferAbort, Code, Contract,
                           Execute, Finish, ImportBegin, ModularError, Name, Operation, Outcome, Prepare,
                           Query, Read, Release, Request, Response, Seal, SealedImport, Abort,
                           FRAME_BYTES, PROFILE_DOMAIN, closed, encode_into, immutable_value, check_immutable,
                           operation_name, parse, typed_digest)

IMPORT_METADATA_BYTES = 1_024
IMPORT_METADATA_LOGICAL_BYTES = 32_768
ENDPOINT_LOGICAL_OVERHEAD = 1_261_568


def profile_digest() -> str:
    return typed_digest(PROFILE_DOMAIN, parse(CORE_DESCRIPTOR))


def composition_budget(reservations: tuple[int, ...]) -> tuple[int, int]:
    """Return payload and owner extents; clients and caller storage are additional."""
    return admit_composition(reservations), len(reservations) * ENDPOINT_LOGICAL_OVERHEAD


class Lifecycle(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    FINISHED = "finished"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class AdmissionView:
    lifecycle: Lifecycle
    high_water: int
    predecessor: str | None
    buffers: BufferUsage


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    """Owner-produced immutable identity; constructing one externally grants no authority."""
    binding: BufferBinding
    sequence: int
    request_digest: str
    predecessor: str | None

    def _trusted(self) -> TrustedHostCreationContext:
        return TrustedHostCreationContext(self.binding, self.request_digest, self.predecessor)


@dataclass(frozen=True, slots=True)
class ImportSource:
    manifest: BufferManifest
    expected_binding: BufferBinding
    metadata: object


@dataclass(frozen=True, slots=True)
class ApplicationResult: data: object
@dataclass(frozen=True, slots=True)
class TerminalResult: data: object
@dataclass(frozen=True, slots=True)
class AbortedResult: pass


@dataclass(frozen=True, slots=True)
class AdmissionDemand:
    inputs: tuple[InputSpec, ...] = ()
    outputs: tuple[OutputSpec, ...] = ()


class InstalledApplication(Contract, Protocol):
    def admit(self, operation: Operation, view: AdmissionView) -> AdmissionDemand: ...
    def execute(self, operation: Operation, permit: ExecutionPermit) -> ApplicationResult | TerminalResult | AbortedResult: ...
    def split_import(self, descriptor: object) -> ImportSource: ...
    def validate_import(self, metadata: object, manifest: BufferManifest, payload: memoryview) -> object: ...


class AdmissionError(ValueError):
    """A pure installed validator rejects before the execution boundary."""
    def __init__(self, code: Code) -> None:
        self.code = code
        super().__init__(code.value)


class ExecutionError(ValueError):
    """A closed application diagnostic after its operation entered execution."""
    def __init__(self, reason: str) -> None:
        if reason not in ("backend", "invalid_output", "internal"): raise ModularError("wire")
        self.reason = reason
        super().__init__(reason)


class ExecutionPermit:
    def __init__(self, context: ExecutionContext, outputs: OutputReservation | None) -> None:
        self._context = context
        self._outputs = outputs
        self._violated = False

    @property
    def context(self) -> ExecutionContext: return self._context

    def input(self, slot: int) -> InputView:
        try:
            if self._outputs is None: raise BufferError("state")
            return self._outputs.input(slot)
        except BaseException:
            self._violated = True
            raise

    def write_output(self, slot: int, offset: int, payload: bytes) -> None:
        try:
            if self._outputs is None: raise BufferError("state")
            self._outputs.write(slot, offset, payload)
        except BaseException:
            self._violated = True
            raise

    def seal_output(self, slot: int) -> BufferManifest:
        try:
            if self._outputs is None: raise BufferError("state")
            return self._outputs.seal(slot)
        except BaseException:
            self._violated = True
            raise


@dataclass(frozen=True, slots=True)
class _Stamp: sequence: int; request_digest: str; operation: Name
@dataclass(frozen=True, slots=True)
class _Owed: stamp: _Stamp; result_digest: str
@dataclass(frozen=True, slots=True)
class _StoredImport: buffer_id: int; wire: bytes; integrity: str


def _buffer_code(error: BufferError) -> Code:
    return {"capacity": Code.CAPACITY, "unavailable": Code.BUFFER_UNAVAILABLE}.get(error.code, Code.INVALID)


def _rejection_code(code: Code) -> Code:
    return code if code in (Code.ROLE, Code.STATE, Code.INVALID, Code.CAPACITY, Code.BUFFER_UNAVAILABLE) else Code.INVALID


def _check_core(operation: Operation, body: Body, context: ExecutionContext) -> None:
    if type(operation) is Seal and body.kind == BodyKind.IMPORT_SEALED:
        manifest = body.data.manifest
        manifest.verify(context.binding)
        if manifest.reference() != operation.reference or manifest.creating_request_digest != operation.expected_import_request_digest or manifest.imported_manifest_digest != operation.expected_source_manifest_digest:
            raise ModularError("binding")
    if type(operation) is ImportBegin and body.kind == BodyKind.IMPORT_RESERVED:
        reference = body.data
        if reference.generation != context.binding.generation or type(reference.buffer_id) is not int or not 1 <= reference.buffer_id <= MAX_ID:
            raise ModularError("binding")
    if type(operation) in (Append, Release, BufferAbort) and body.kind == BodyKind.BUFFER_CHANGED and operation.reference != body.data:
        raise ModularError("binding")
    if type(operation) is Read and body.kind == BodyKind.CHUNK:
        chunk = body.data
        if chunk.index != operation.index or chunk.manifest_digest != operation.expected_manifest_digest:
            raise ModularError("binding")
        try: chunk.decoded()
        except BufferError as error: raise ModularError("wire") from error


class Owner:
    """One endpoint and retained wire. Returned read-only views expire on the next call.

    A caller that retains evidence must copy that view into its own bounded storage.
    A Python protocol cannot attest a malicious host implementation or plugin.
    """
    def __init__(self, binding: BufferBinding, application: InstalledApplication, semantics: tuple[str, ...]) -> None:
        binding.validate()
        self._contract = type(application)
        if binding.profile_digest != profile_digest() or binding.application_digest != typed_digest(PROFILE_DOMAIN, parse(self._contract.descriptor())):
            raise ModularError("binding")
        self._binding = binding
        self._application = application
        self._pool = BufferPool(binding, semantics)
        self._lifecycle = Lifecycle.NEW
        self._channel_retired = False
        self._high_water = 0
        self._predecessor = None
        # Both complete slots exist before this owner can execute.
        self._retained = bytearray(FRAME_BYTES)
        self._staging = bytearray(FRAME_BYTES)
        self._retained_length = 0
        self._staging_length = 0
        self._owed = None
        self._last_ack = None
        self._entered = None
        self._imports: list[_StoredImport | None] = [None] * LIVE_SLOTS

    @property
    def binding(self) -> BufferBinding: return self._binding
    @property
    def lifecycle(self) -> Lifecycle: return self._lifecycle
    @property
    def high_water(self) -> int: return self._high_water
    @property
    def predecessor(self) -> str | None: return self._predecessor
    @property
    def usage(self) -> BufferUsage: return self._pool.usage()
    @property
    def retained(self) -> memoryview | None:
        return memoryview(self._retained)[:self._retained_length].toreadonly() if self._owed else None

    def retire_channel(self) -> None:
        self._channel_retired = True
        self._lifecycle = Lifecycle.RETIRED

    def _emit(self, stamp: _Stamp, outcome: Outcome, code: Code, body: Body, *, retained: bool = False) -> bool:
        response = Response(self.binding, stamp.sequence, stamp.operation, stamp.request_digest, outcome, code, body)
        length, digest = response.write(self._staging)
        if retained:
            # The admitted request is gone. Decode the exact candidate, then release
            # the original body before reprojection into the currently unowed slot.
            decoded = Response._decode_raw(parse(memoryview(self._staging)[:length]), self.binding, self._contract)
            del response, body
            _, reopened_digest = decoded.write(self._retained)
            if reopened_digest != digest:
                raise ModularError("wire")
            del decoded
            self._predecessor = digest
            self._owed = _Owed(stamp, digest)
            self._retained, self._staging = self._staging, self._retained
            self._retained_length, self._staging_length = length, 0
        else: self._staging_length = length
        return retained

    def _reject(self, stamp: _Stamp, code: Code) -> bool:
        return self._emit(stamp, Outcome.REJECTED, _rejection_code(code), Body(BodyKind.REJECTED))

    def _unavailable(self, stamp: _Stamp) -> bool:
        return self._emit(stamp, Outcome.UNAVAILABLE, Code.NO_RESULT, Body(BodyKind.UNAVAILABLE))

    def _conflict(self, stamp: _Stamp, pending: bool = False) -> bool:
        return self._emit(stamp, Outcome.NOT_ADMITTED, Code.PENDING if pending else Code.CONFLICT, Body(BodyKind.NOT_ADMITTED))

    def process(self, payload: bytes) -> memoryview:
        if self._channel_retired: raise ModularError("retired")
        self._entered = None
        failure = None
        try:
            retained = self._process(payload)
        except BaseException as error:
            self._lifecycle = Lifecycle.RETIRED
            stamp = self._entered
            if stamp is None:
                self.retire_channel()
                raise ModularError("retired") from error
            reason = error.reason if isinstance(error, ExecutionError) else "invalid_output" if isinstance(error, (ModularError, BufferError)) else "backend"
            # Clear the failed stack, then leave the exception suite. Its handled
            # exception and args must also die before allocating the diagnostic.
            error.__traceback__ = None
            error.__cause__ = None
            error.__context__ = None
            failure = (stamp, reason)
        finally:
            self._entered = None
        if failure is not None:
            stamp, reason = failure
            try:
                retained = self._emit(stamp, Outcome.INDETERMINATE, Code.UNKNOWN, Body(BodyKind.INDETERMINATE, reason), retained=True)
            except BaseException as terminal:
                self.retire_channel()
                raise ModularError("retired") from terminal
        return (memoryview(self._retained)[:self._retained_length] if retained else memoryview(self._staging)[:self._staging_length]).toreadonly()

    def _process(self, payload: bytes) -> bool:
        request = Request.decode(payload, self.binding, self._contract, scratch=self._staging)
        command = request.command
        if type(command) is Execute:
            self._contract.check_input(command.operation)
            name = operation_name(command.operation)
        else: name = Name.RESULT if type(command) is Query else Name.ACK
        stamp = _Stamp(request.sequence, request.request_digest, name)
        if type(command) is Query:
            if self._owed and self._owed.stamp.sequence == request.sequence and self._owed.stamp.request_digest == command.original_request_digest: return True
            return self._unavailable(stamp)
        if type(command) is Ack:
            target = AckStamp(request.sequence, command.original_request_digest, command.result_digest)
            current = self._owed and self._owed.stamp.sequence == target.sequence and self._owed.stamp.request_digest == target.original_request_digest and self._owed.result_digest == target.result_digest
            if current or self._last_ack == target:
                result = self._emit(stamp, Outcome.ACKNOWLEDGED, Code.RELEASED, Body(BodyKind.ACKNOWLEDGED, target))
                if current:
                    self._owed = None
                    self._retained_length = 0
                    self._last_ack = target
                return result
            if self._owed and self._owed.stamp.sequence == request.sequence or self._last_ack and self._last_ack.sequence == request.sequence: return self._conflict(stamp)
            return self._unavailable(stamp)
        if self._owed:
            if self._owed.stamp.sequence == stamp.sequence and self._owed.stamp.request_digest == stamp.request_digest: return True
            return self._conflict(stamp, stamp.sequence > self._owed.stamp.sequence)
        if stamp.sequence <= self._high_water: return self._unavailable(stamp)
        if self._high_water == MAX_ID or stamp.sequence != self._high_water + 1: return self._conflict(stamp)
        if not self._contract.allows(name): return self._reject(stamp, Code.ROLE)
        if command.expected_predecessor_result_digest != self._predecessor: return self._reject(stamp, Code.STATE)
        if name == Name.PREPARE and self._lifecycle != Lifecycle.NEW or name != Name.PREPARE and self._lifecycle != Lifecycle.ACTIVE: return self._reject(stamp, Code.STATE)
        try:
            demand = self._application.admit(command.operation, AdmissionView(self._lifecycle, self._high_water, self._predecessor, self.usage))
        except AdmissionError as error: return self._reject(stamp, Code.INVALID if error.code == Code.ROLE else error.code)
        if type(demand) is not AdmissionDemand or type(demand.inputs) is not tuple or type(demand.outputs) is not tuple or len(demand.inputs) > LIVE_SLOTS or len(demand.outputs) > LIVE_SLOTS: return self._reject(stamp, Code.CAPACITY)
        if name not in (Name.PREPARE, Name.APPLICATION) and (demand.inputs or demand.outputs): return self._reject(stamp, Code.CAPACITY)
        if name == Name.FINISH and (self.usage.live_slots or any(self._imports)): return self._reject(stamp, Code.STATE)
        context = ExecutionContext(self.binding, stamp.sequence, stamp.request_digest, self._predecessor)
        try:
            body = self._execute(stamp, command.operation, demand, context)
        except AdmissionError as error:
            if self._entered is not None: raise ModularError("retired") from error
            return self._reject(stamp, Code.INVALID if error.code == Code.ROLE else error.code)
        _check_core(command.operation, body, context)
        self._contract.check_response(command.operation, body, context)
        if name == Name.FINISH and (self.usage.live_slots or any(self._imports)): raise ModularError("retired")
        # Release the complete admitted input before staging the typed output.
        del request, command
        pending_body = [body]
        del body
        reply = self._emit(stamp, Outcome.COMMITTED, Code.OK, pending_body.pop(), retained=True)
        if name == Name.PREPARE: self._lifecycle = Lifecycle.ACTIVE
        elif name == Name.FINISH: self._lifecycle = Lifecycle.FINISHED
        elif name == Name.ABORT: self._lifecycle = Lifecycle.RETIRED
        return reply

    def _enter(self, stamp: _Stamp) -> None:
        self._high_water = stamp.sequence
        self._entered = stamp

    def _execute(self, stamp: _Stamp, operation: Operation, demand: AdmissionDemand, context: ExecutionContext) -> Body:
        try:
            if type(operation) is Append: self._pool.check_append(operation.reference, operation.chunk)
            elif type(operation) is BufferAbort: self._pool.check_release(operation.reference, True)
            elif type(operation) is Release: self._pool.check_release(operation.reference, False)
            elif type(operation) is Read:
                self._pool.check_read(operation.reference, operation.index)
                self._pool.check_manifest(operation.reference, operation.expected_manifest_digest)
        except BufferError as error: raise AdmissionError(_buffer_code(error)) from error
        if type(operation) in (Prepare, Application, Finish, Abort):
            try: ticket = self._pool.reserve_execution(demand.inputs, demand.outputs)
            except BufferError as error: raise AdmissionError(_buffer_code(error)) from error
            with ticket:
                self._enter(stamp)
                ticket.enter(context._trusted())
                permit = ExecutionPermit(context, ticket if type(operation) in (Prepare, Application) else None)
                try:
                    output = self._application.execute(operation, permit)
                finally:
                    ticket.expire_inputs()
                if permit._violated or not ticket.complete(): raise ModularError("retired")
                if type(operation) in (Prepare, Application) and type(output) is ApplicationResult:
                    return Body(BodyKind.PREPARED if type(operation) is Prepare else BodyKind.APPLICATION, output.data)
                if type(operation) is Finish and type(output) is TerminalResult: return Body(BodyKind.FINISHED, output.data)
                if type(operation) is Abort and type(output) is AbortedResult: return Body(BodyKind.ABORTED)
                raise ModularError("wire")
        if type(operation) is ImportBegin:
            slot = next((index for index, item in enumerate(self._imports) if item is None), None)
            if slot is None: raise AdmissionError(Code.CAPACITY)
            source = self._application.split_import(operation.data)
            if type(source) is not ImportSource: raise AdmissionError(Code.INVALID)
            descriptor_digest = typed_digest(PROFILE_DOMAIN, immutable_value(operation.data))
            record = {"source_manifest_digest": source.manifest.manifest_digest, "source_descriptor_digest": descriptor_digest,
                      "data": immutable_value(source.metadata)}
            # The complete metadata allocation and owned copy precede promotion.
            try:
                metadata_slot = bytearray(IMPORT_METADATA_BYTES)
                length = encode_into(record, metadata_slot)
                integrity = typed_digest(PROFILE_DOMAIN, record)
                wire = bytes(memoryview(metadata_slot)[:length])
            except (ModularError, MemoryError) as error: raise AdmissionError(Code.CAPACITY) from error
            del record, metadata_slot
            owned = closed(parse(wire), {"source_manifest_digest", "source_descriptor_digest", "data"})
            metadata = self._contract.decode_metadata(owned["data"])
            check_immutable(metadata)
            try: self._contract.check_import_metadata(operation.data, metadata)
            except (ModularError, ValueError) as error: raise AdmissionError(Code.INVALID) from error
            del owned, metadata
            prepared = _StoredImport(0, wire, integrity)
            try: ticket = self._pool.reserve_import(context._trusted(), source.manifest, source.expected_binding)
            except BufferError as error: raise AdmissionError(_buffer_code(error)) from error
            with ticket:
                self._enter(stamp)
                reference = ticket.commit()
                self._imports[slot] = _StoredImport(reference.buffer_id, prepared.wire, prepared.integrity)
            return Body(BodyKind.IMPORT_RESERVED, reference)
        if type(operation) is Seal:
            try: manifest, payload = self._pool.inspect_import(operation.reference)
            except BufferError as error: raise AdmissionError(_buffer_code(error)) from error
            if manifest.creating_request_digest != operation.expected_import_request_digest or manifest.imported_manifest_digest != operation.expected_source_manifest_digest: raise AdmissionError(Code.INVALID)
            stored = next((entry for entry in self._imports if entry and entry.buffer_id == operation.reference.buffer_id), None)
            if stored is None: raise AdmissionError(Code.BUFFER_UNAVAILABLE)
            record = closed(parse(stored.wire), {"source_manifest_digest", "source_descriptor_digest", "data"})
            if typed_digest(PROFILE_DOMAIN, record) != stored.integrity or manifest.imported_manifest_digest != record["source_manifest_digest"]: raise ModularError("wire")
            metadata = self._contract.decode_metadata(record["data"])
            check_immutable(metadata)
            output = self._application.validate_import(metadata, manifest, payload)
            del payload, record, metadata
            self._enter(stamp)
            manifest = self._pool.seal(operation.reference)
            return Body(BodyKind.IMPORT_SEALED, SealedImport(manifest, output))
        self._enter(stamp)
        if type(operation) is Append:
            self._pool.append(operation.reference, operation.chunk)
            return Body(BodyKind.BUFFER_CHANGED, operation.reference)
        if type(operation) is Read: return Body(BodyKind.CHUNK, self._pool.read(operation.reference, operation.index))
        if type(operation) in (Release, BufferAbort):
            if type(operation) is Release: self._pool.release(operation.reference)
            else: self._pool.abort_import(operation.reference)
            for index, entry in enumerate(self._imports):
                if entry and entry.buffer_id == operation.reference.buffer_id: self._imports[index] = None
            return Body(BodyKind.BUFFER_CHANGED, operation.reference)
        raise ModularError("wire")


def verify_response(binding: BufferBinding, request: Request, payload: bytes | memoryview, contract: type[Contract]) -> Response:
    request.verify(binding)
    response = Response.decode(payload, binding, contract)
    if response.sequence != request.sequence or response.request_digest != request.request_digest: raise ModularError("binding")
    command = request.command
    if type(command) is Execute:
        contract.check_input(command.operation)
        name = operation_name(command.operation)
        if response.operation != name: raise ModularError("wire")
        allowed = contract.allows(name)
        if not allowed and (response.outcome != Outcome.REJECTED or response.code != Code.ROLE) or allowed and response.code == Code.ROLE: raise ModularError("wire")
        if response.outcome == Outcome.COMMITTED:
            context = ExecutionContext(binding, request.sequence, request.request_digest, command.expected_predecessor_result_digest)
            _check_core(command.operation, response.body, context)
            contract.check_response(command.operation, response.body, context)
    elif type(command) is Query:
        if response.operation != Name.RESULT or response.outcome != Outcome.UNAVAILABLE: raise ModularError("wire")
    elif type(command) is Ack:
        if response.operation != Name.ACK: raise ModularError("wire")
        if response.body.kind == BodyKind.ACKNOWLEDGED and response.body.data != AckStamp(request.sequence, command.original_request_digest, command.result_digest): raise ModularError("binding")
    else: raise ModularError("wire")
    return response


def verify_retrieved(binding: BufferBinding, original: Request, query: Request, payload: bytes | memoryview, contract: type[Contract]) -> Response:
    query.verify(binding)
    if type(query.command) is not Query or query.binding != binding or original.binding != binding or query.sequence != original.sequence or query.command.original_request_digest != original.request_digest:
        raise ModularError("binding")
    response = verify_response(binding, original, payload, contract)
    if response.outcome not in (Outcome.COMMITTED, Outcome.INDETERMINATE): raise ModularError("wire")
    return response


def _write_view(writer: BinaryIO, payload: memoryview, deadline: float) -> None:
    """Write the borrowed owner slot; never allocate another complete response copy."""
    if not math.isfinite(deadline) or not payload.readonly or not 1 <= payload.nbytes <= FRAME_BYTES: raise ModularError("wire")
    try: fd = writer.fileno()
    except (AttributeError, OSError):
        if not isinstance(writer, io.BytesIO): raise ModularError("wire")
        fd = None
    for part in (memoryview(struct.pack(">I", payload.nbytes)), payload):
        offset = 0
        while offset < part.nbytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ModularError("retired")
            if fd is not None:
                if not select.select([], [fd], [], remaining)[1]: raise ModularError("retired")
                count = os.write(fd, part[offset:offset + 512])
            else: count = writer.write(part[offset:])
            if type(count) is not int or not 1 <= count <= part.nbytes - offset: raise ModularError("wire")
            offset += count
    writer.flush()


def serve(owner: Owner, reader: BinaryIO, writer: BinaryIO, *, deadline: float) -> None:
    """Host-owned lifetime with an absolute deadline. Every exit retires the channel."""
    try:
        if not math.isfinite(deadline): raise ModularError("wire")
        while True:
            payload = framing.read_local_frame(reader, deadline=deadline)
            if payload is None: return
            result = owner.process(payload)
            _write_view(writer, result, deadline)
    finally:
        owner.retire_channel()
