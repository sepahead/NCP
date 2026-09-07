"""Independent test-only counter contract; never an installed scientific profile."""
from dataclasses import dataclass, fields
from typing import Any
from ncp_local.modular_buffer import BufferBinding, BufferManifest, OutputSpec
from ncp_local import modular_wire as w
from ncp_local import modular_owner as o

SEMANTIC = "a" * 64
DESCRIPTOR = b'{"schema":"ncp.test.counter.v1","status":"test-only","role":"counter","data_shapes":"closed test types in support/modular_fixture.rs"}'

@dataclass(frozen=True, slots=True)
class Initial: initial: int
@dataclass(frozen=True, slots=True)
class Add:
    amount: int
    output_bytes: int
    kind: str = "add"
@dataclass(frozen=True, slots=True)
class Special: kind: str
@dataclass(frozen=True, slots=True)
class Import: manifest: BufferManifest; source: BufferBinding; label: str
@dataclass(frozen=True, slots=True)
class Metadata: byte_length: int; label: str
@dataclass(frozen=True, slots=True)
class Finish: allocate: bool; demand: bool
@dataclass(frozen=True, slots=True)
class Output: value: int; manifest: BufferManifest | None
@dataclass(frozen=True, slots=True)
class Imported: byte_length: int; label: str
@dataclass(frozen=True, slots=True)
class Terminal: value: int


def binding() -> BufferBinding:
    return BufferBinding(o.profile_digest(), w.typed_digest(w.PROFILE_DOMAIN, w.parse(DESCRIPTOR)),
                         "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222", "33333333-3333-4333-8333-333333333333")


def row(value: Any, cls: type) -> dict[str, Any]:
    return w.closed(value, {field.name for field in fields(cls)})


def manifest(value: Any) -> BufferManifest:
    source = row(value, BufferManifest)
    return BufferManifest(**{**source, "binding": BufferBinding(**row(source["binding"], BufferBinding))})


class Counter:
    def __init__(self) -> None: self.calls = 0; self.value = 0
    @staticmethod
    def descriptor() -> bytes: return DESCRIPTOR
    @staticmethod
    def allows(operation: w.Name) -> bool: return operation != w.Name.ABORT
    @staticmethod
    def decode_prepare(value: Any) -> Initial:
        item = row(value, Initial)
        if not w.integer(item["initial"], 0): raise w.ModularError("wire")
        return Initial(**item)
    @staticmethod
    def decode_command(value: Any) -> Add | Special:
        if type(value) is not dict: raise w.ModularError("wire")
        if value.get("kind") == "add":
            item = row(value, Add)
            if not w.integer(item["amount"], 0) or not w.integer(item["output_bytes"], 0): raise w.ModularError("wire")
            return Add(**item)
        item = row(value, Special)
        if item["kind"] not in ("panic", "backend_error", "admission_role", "invalid_output", "omit_output", "ignore_write_error"): raise w.ModularError("wire")
        return Special(**item)
    @staticmethod
    def decode_import(value: Any) -> Import:
        item = row(value, Import)
        if type(item["label"]) is not str: raise w.ModularError("wire")
        return Import(manifest(item["manifest"]), BufferBinding(**row(item["source"], BufferBinding)), item["label"])
    @staticmethod
    def decode_metadata(value: Any) -> Metadata:
        item = row(value, Metadata)
        if not w.integer(item["byte_length"], 0) or type(item["label"]) is not str: raise w.ModularError("wire")
        return Metadata(**item)
    @staticmethod
    def decode_finish(value: Any) -> Finish:
        item = row(value, Finish)
        if type(item["allocate"]) is not bool or type(item["demand"]) is not bool: raise w.ModularError("wire")
        return Finish(**item)
    @staticmethod
    def decode_result(value: Any) -> Output:
        item = row(value, Output)
        if not w.integer(item["value"], 0): raise w.ModularError("wire")
        return Output(item["value"], manifest(item["manifest"]) if item["manifest"] is not None else None)
    @staticmethod
    def decode_imported(value: Any) -> Imported:
        item = row(value, Imported)
        if not w.integer(item["byte_length"], 0) or type(item["label"]) is not str: raise w.ModularError("wire")
        return Imported(**item)
    @staticmethod
    def decode_terminal(value: Any) -> Terminal:
        item = row(value, Terminal)
        if not w.integer(item["value"], 0): raise w.ModularError("wire")
        return Terminal(**item)
    @staticmethod
    def check_input(operation: w.Operation) -> None:
        if type(operation) is w.Prepare and operation.data.initial > 100: raise w.ModularError("wire")
        if type(operation) is w.Application and type(operation.data) is Add and (operation.data.amount > 100 or operation.data.output_bytes > 8_388_608): raise w.ModularError("wire")
        if type(operation) is w.ImportBegin and len(operation.data.label.encode()) > 2_000: raise w.ModularError("wire")
    @staticmethod
    def check_response(operation: w.Operation, body: w.Body, context: o.ExecutionContext) -> None:
        if body.kind in (w.BodyKind.PREPARED, w.BodyKind.APPLICATION):
            if type(operation) is w.Application and type(operation.data) is Add:
                if (body.data.manifest.byte_length if body.data.manifest else 0) != operation.data.output_bytes: raise w.ModularError("wire")
            if body.data.value > 10_000: raise w.ModularError("wire")
            item = body.data.manifest
            if item:
                item.verify(context.binding)
                if item.creating_request_digest != context.request_digest or item.causal_predecessor != context.predecessor: raise w.ModularError("binding")
    @staticmethod
    def check_import_metadata(descriptor: Import, metadata: Metadata) -> None:
        if metadata.byte_length != descriptor.manifest.byte_length or metadata.label != descriptor.label: raise w.ModularError("binding")
    def admit(self, operation: w.Operation, view: o.AdmissionView) -> o.AdmissionDemand:
        length = 0
        if type(operation) is w.Application:
            if type(operation.data) is Special and operation.data.kind == "admission_role": raise o.AdmissionError(w.Code.ROLE)
            if type(operation.data) is Add:
                if operation.data.amount == 0: raise o.AdmissionError(w.Code.INVALID)
                length = operation.data.output_bytes
            elif operation.data.kind in ("omit_output", "ignore_write_error"): length = 4
        elif type(operation) is w.Finish and operation.data.demand: length = 4
        return o.AdmissionDemand(outputs=(OutputSpec(SEMANTIC, length),) if length else ())
    def execute(self, operation: w.Operation, permit: o.ExecutionPermit) -> o.ApplicationResult | o.TerminalResult | o.AbortedResult:
        self.calls += 1
        item = None
        if type(operation) is w.Prepare: self.value = operation.data.initial
        elif type(operation) is w.Application:
            data = operation.data
            if type(data) is Add:
                self.value += data.amount
                for offset in range(0, data.output_bytes, 32_768):
                    payload = bytes(i % 251 for i in range(offset, min(offset + 32_768, data.output_bytes)))
                    permit.write_output(0, offset, payload)
                if data.output_bytes: item = permit.seal_output(0)
            elif data.kind == "panic": raise RuntimeError("test-only backend failure")
            elif data.kind == "backend_error": raise o.ExecutionError("backend")
            elif data.kind == "invalid_output": self.value = 10_001
            elif data.kind == "ignore_write_error":
                try: permit.write_output(0, 1, b"bad")
                except ValueError: pass
        elif type(operation) is w.Finish:
            if operation.data.allocate:
                try: permit.seal_output(0)
                except ValueError: pass
            return o.TerminalResult(Terminal(self.value))
        elif type(operation) is w.Abort: return o.AbortedResult()
        else: raise RuntimeError("wrong core dispatch")
        return o.ApplicationResult(Output(self.value, item))
    def split_import(self, descriptor: Import) -> o.ImportSource:
        return o.ImportSource(descriptor.manifest, descriptor.source, Metadata(descriptor.manifest.byte_length, descriptor.label))
    def validate_import(self, metadata: Metadata, source: BufferManifest, payload: memoryview) -> Imported:
        if len(payload) != metadata.byte_length: raise o.AdmissionError(w.Code.INVALID)
        return Imported(len(payload), metadata.label)
