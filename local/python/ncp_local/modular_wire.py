"""Independent closed modular wire codecs for statically installed application types.

Decoded dictionaries stay inside codecs. The execution seam receives frozen types.
This module installs no body, capture, neural, monitor, or launcher application.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
import struct
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from . import wire as bounded
from .modular_buffer import BufferBinding, BufferChunk, BufferManifest, BufferRef, MAX_ID

REQUEST_SCHEMA = "ncp.modular.request.v1"
RESPONSE_SCHEMA = "ncp.modular.response.v1"
PROFILE_DOMAIN = "ncp.modular.profile.v1"
FRAME_BYTES = 65_536
PROJECTION_BYTES = 131_072

# Each matched character is one UTF-8 byte without JSON escape semantics.
_ASCII_STRING_RUN = re.compile(r'[\x20-\x21\x23-\x5b\x5d-\x7f]+')


class _ModularScanner(bounded._Scanner):
    """Scan complete ASCII strings in C; retain the scalar grammar as a reference."""

    def _parse_string(self, *, capture: bool) -> str | None:
        opening = self.position
        self._expect('"')
        start = self.position
        limit = bounded.MAX_KEY_BYTES if capture else bounded.MAX_STRING_BYTES
        span = _ASCII_STRING_RUN.match(self.text, start, start + limit + 1)
        if span is not None:
            end = span.end()
            size = end - start
            if size > limit:
                self.position = end
                self._fail("NCP-LIMIT-005", "JSON string exceeds its byte limit")
            if end < len(self.text) and self.text[end] == '"':
                self.position = end + 1
                self.string_bytes += size
                if self.string_bytes > bounded.MAX_TOTAL_STRING_BYTES:
                    self._fail("NCP-LIMIT-005", "aggregate JSON string budget exceeded")
                return self.text[start:end] if capture else None
        self.position = opening
        return super()._parse_string(capture=capture)


def _preflight(payload: bytes) -> None:
    if type(payload) is not bytes or not payload or len(payload) > FRAME_BYTES:
        raise bounded.LocalError("capacity")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise bounded.BoundedJsonError("NCP-LIMIT-008", "invalid UTF-8") from error
    _ModularScanner(text).scan()


class ModularError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"modular owner error: {code}")


def digest_valid(value: Any) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def integer(value: Any, low: int = 1, high: int = MAX_ID) -> bool:
    return type(value) is int and low <= value <= high


def closed(value: Any, keys: set[str]) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ModularError("wire")
    return value


def parse(payload: bytes | memoryview) -> Any:
    if type(payload) is memoryview:
        if payload.nbytes > FRAME_BYTES: raise ModularError("capacity")
        payload = payload.tobytes()
    try:
        _preflight(payload)
        return json.loads(
            payload, parse_int=lambda token: -0.0 if token == "-0" else int(token)
        )
    except bounded.LocalError as error:
        raise ModularError(error.code) from error


def encode(value: Any) -> bytes:
    slot = bytearray(FRAME_BYTES)
    length = encode_into(value, slot)
    return bytes(memoryview(slot)[:length])


def _validate_json(value: Any) -> None:
    """Check exact encoded extent and universal limits without emitting bytes."""
    try:
        _check_json_extent(value)
        bounded.check_value(value)
    except bounded.LocalError as error:
        raise ModularError(error.code) from error


def encode_into(value: Any, slot: bytearray) -> int:
    """Write inside a fixed slot; escaped string fragments have at most1,538 bytes.

    A whole escaped token could grow sixfold before a size check. Fragmented
    escaping bounds that temporary even for an oversized application result.
    """
    try:
        _validate_json(value)
        end = 0

        def write(payload: bytes) -> None:
            nonlocal end
            if len(payload) > len(slot) - end: raise ModularError("capacity")
            slot[end:end + len(payload)] = payload
            end += len(payload)

        def string(text: str) -> None:
            write(b'"')
            for start in range(0, len(text), 256):
                fragment = json.dumps(text[start:start + 256], ensure_ascii=False)[1:-1]
                write(fragment.encode("utf-8"))
            write(b'"')

        def visit(item: Any) -> None:
            if item is None: write(b"null")
            elif type(item) is bool: write(b"true" if item else b"false")
            elif type(item) in (int, float): write(json.dumps(item, allow_nan=False).encode("ascii"))
            elif type(item) is str: string(item)
            elif type(item) is list:
                write(b"[")
                for index, child in enumerate(item):
                    if index: write(b",")
                    visit(child)
                write(b"]")
            elif type(item) is dict:
                write(b"{")
                for index, (key, child) in enumerate(item.items()):
                    if index: write(b",")
                    string(key)
                    write(b":")
                    visit(child)
                write(b"}")
            else: raise ModularError("wire")

        visit(value)
        return end
    except bounded.LocalError as error:
        raise ModularError(error.code) from error


def _string_extent(text: str, limit: int, *, quoted: bool = False) -> int:
    """Count UTF8 or compact JSON bytes before allocating a complete token."""
    size = 2 if quoted else 0
    if size > limit: raise ModularError("capacity")
    # ASCII has no surrogate, so its byte lower bound preserves rejection order.
    if type(text) is str and text.isascii() and type(limit) is int and type(quoted) is bool:
        if len(text) > limit - size:
            raise ModularError("capacity")
        if not quoted or (text.isprintable() and '"' not in text and '\\' not in text):
            return size + len(text)
    for character in text:
        point = ord(character)
        if 0xD800 <= point <= 0xDFFF: raise ModularError("wire")
        if quoted and character in '\"\\\b\f\n\r\t': width = 2
        elif quoted and point < 0x20: width = 6
        else: width = 1 if point < 0x80 else 2 if point < 0x800 else 3 if point < 0x10000 else 4
        if width > limit - size: raise ModularError("capacity")
        size += width
    return size


def _check_json_extent(value: Any) -> None:
    """Bound compact JSON before scalar encoding, key sorting, or projection use."""
    remaining = FRAME_BYTES

    def charge(size: int) -> None:
        nonlocal remaining
        if size > remaining: raise ModularError("capacity")
        remaining -= size

    def visit(item: Any, depth: int) -> None:
        if depth > 32: raise ModularError("capacity")
        if item is None: charge(4)
        elif type(item) is bool: charge(4 if item else 5)
        elif type(item) in (int, float):
            if type(item) is int and abs(item) > MAX_ID or not math.isfinite(item) or abs(item) > 1e300:
                raise ModularError("wire")
            charge(len(json.dumps(item, allow_nan=False)))
        elif type(item) is str: charge(_string_extent(item, remaining, quoted=True))
        elif type(item) is list:
            if len(item) > 65_536: raise ModularError("capacity")
            charge(2 + max(0, len(item) - 1))
            for child in item: visit(child, depth + 1)
        elif type(item) is dict:
            if len(item) > 4_096: raise ModularError("capacity")
            charge(2 + max(0, len(item) - 1))
            for key, child in item.items():
                if type(key) is not str: raise ModularError("wire")
                _string_extent(key, 128)
                charge(_string_extent(key, remaining, quoted=True))
                charge(1)
                visit(child, depth + 1)
        else: raise ModularError("wire")

    visit(value, 0)


def _check_hash_text_extent(value: Any) -> None:
    """Bound hash/sort UTF8 copies without changing numeric token semantics."""
    remaining = FRAME_BYTES

    def text(item: str, key: bool = False) -> None:
        nonlocal remaining
        size = _string_extent(item, min(remaining, 128) if key else remaining)
        remaining -= size

    def visit(item: Any, depth: int) -> None:
        if depth > 32: raise ModularError("capacity")
        if type(item) is str: text(item)
        elif type(item) is list:
            if len(item) > 65_536: raise ModularError("capacity")
            for child in item: visit(child, depth + 1)
        elif type(item) is dict:
            if len(item) > 4_096: raise ModularError("capacity")
            for key, child in item.items():
                if type(key) is not str: raise ModularError("wire")
                text(key, True)
                visit(child, depth + 1)

    visit(value, 0)


def typed_digest(domain: str, value: Any, omit: str | None = None) -> str:
    if domain not in (REQUEST_SCHEMA, RESPONSE_SCHEMA, PROFILE_DOMAIN):
        raise ModularError("wire")
    _check_hash_text_extent(value)
    result = hashlib.sha256()
    length = 0
    scratch = 0

    def push(payload: bytes) -> None:
        nonlocal length
        if len(payload) > PROJECTION_BYTES - length:
            raise ModularError("capacity")
        result.update(payload)
        length += len(payload)

    def string(text: str) -> None:
        try:
            payload = text.encode("utf-8")
        except UnicodeError as error:
            raise ModularError("wire") from error
        push(b"\x04" + struct.pack(">Q", len(payload)))
        push(payload)

    def visit(item: Any, depth: int, skip: str | None = None) -> None:
        nonlocal scratch
        if depth > 32:
            raise ModularError("capacity")
        if item is None:
            push(b"\x00")
        elif type(item) is bool:
            push(b"\x02" if item else b"\x01")
        elif type(item) in (int, float):
            if type(item) is int and abs(item) > MAX_ID:
                raise ModularError("wire")
            if not math.isfinite(item) or abs(item) > 1e300:
                raise ModularError("wire")
            push(b"\x03" + struct.pack(">d", item))
        elif type(item) is str:
            _string_extent(item, FRAME_BYTES)
            string(item)
        elif type(item) is list:
            if len(item) > 65_536:
                raise ModularError("capacity")
            push(b"\x05" + struct.pack(">Q", len(item)))
            for child in item:
                visit(child, depth + 1)
        elif type(item) is dict:
            if len(item) > 4_096 or any(type(key) is not str for key in item):
                raise ModularError("capacity")
            for key in item: _string_extent(key, 128)
            extent = len(item) * 16
            if extent > PROJECTION_BYTES - 1_024 - scratch:
                raise ModularError("capacity")
            scratch += extent
            keys = sorted((key for key in item if key != skip), key=lambda key: key.encode("utf-8"))
            push(b"\x06" + struct.pack(">Q", len(keys)))
            for key in keys:
                string(key)
                visit(item[key], depth + 1)
            scratch -= extent
        else:
            raise ModularError("wire")

    push(domain.encode("ascii") + b"\x00")
    visit(value, 0, omit)
    return result.hexdigest()


def immutable_value(value: object, depth: int = 0, _budget: list[int] | None = None, *, _build: bool = True) -> Any:
    """Project frozen records with exact compact JSON charges before each copy.

    The budget charges escaped UTF8, scalar spellings, keys, and separators.
    Application allocations and custom accessor execution remain host-owned.
    """
    if depth > 32: raise ModularError("capacity")
    budget = [FRAME_BYTES] if _budget is None else _budget

    def charge(size: int) -> None:
        if size > budget[0]: raise ModularError("capacity")
        budget[0] -= size

    if value is None: charge(4)
    elif type(value) is bool: charge(4 if value else 5)
    elif type(value) in (int, float):
        if type(value) is int and abs(value) > MAX_ID or not math.isfinite(value) or abs(value) > 1e300:
            raise ModularError("wire")
        charge(len(json.dumps(value, allow_nan=False)))
    elif type(value) is str: charge(_string_extent(value, budget[0], quoted=True))
    elif isinstance(value, Enum):
        return immutable_value(value.value, depth + 1, budget, _build=_build)
    elif type(value) is tuple:
        if len(value) > 65_536: raise ModularError("capacity")
        charge(2 + max(0, len(value) - 1))
        if _build: return [immutable_value(item, depth + 1, budget) for item in value]
        for item in value: immutable_value(item, depth + 1, budget, _build=False)
        return None
    elif dataclasses.is_dataclass(value) and not isinstance(value, type) and value.__dataclass_params__.frozen:
        fields = dataclasses.fields(value)
        if len(fields) > 4_096: raise ModularError("capacity")
        charge(2 + max(0, len(fields) - 1))
        output = {} if _build else None
        for field in fields:
            charge(_string_extent(field.name, budget[0], quoted=True))
            charge(1)
            item = immutable_value(getattr(value, field.name), depth + 1, budget, _build=_build)
            if _build: output[field.name] = item
        return output
    else: raise ModularError("wire")
    return value if _build else None


def check_immutable(value: object) -> None:
    """Check frozen shape and extent without constructing another parsed value."""
    immutable_value(value, _build=False)


class Name(str, Enum):
    PREPARE = "prepare"
    APPLICATION = "application"
    IMPORT = "buffer_import_begin"
    APPEND = "buffer_append"
    SEAL = "buffer_seal"
    BUFFER_ABORT = "buffer_abort"
    READ = "buffer_read"
    RELEASE = "buffer_release"
    FINISH = "finish"
    ABORT = "abort"
    RESULT = "result"
    ACK = "ack"


@dataclass(frozen=True, slots=True)
class Prepare: data: object
@dataclass(frozen=True, slots=True)
class Application: data: object
@dataclass(frozen=True, slots=True)
class ImportBegin: data: object
@dataclass(frozen=True, slots=True)
class Append: reference: BufferRef; chunk: BufferChunk
@dataclass(frozen=True, slots=True)
class Seal: reference: BufferRef; expected_import_request_digest: str; expected_source_manifest_digest: str
@dataclass(frozen=True, slots=True)
class BufferAbort: reference: BufferRef
@dataclass(frozen=True, slots=True)
class Read: reference: BufferRef; expected_manifest_digest: str; index: int
@dataclass(frozen=True, slots=True)
class Release: reference: BufferRef
@dataclass(frozen=True, slots=True)
class Finish: data: object
@dataclass(frozen=True, slots=True)
class Abort: pass

Operation = Prepare | Application | ImportBegin | Append | Seal | BufferAbort | Read | Release | Finish | Abort
_NAMES = {Prepare: Name.PREPARE, Application: Name.APPLICATION, ImportBegin: Name.IMPORT, Append: Name.APPEND,
          Seal: Name.SEAL, BufferAbort: Name.BUFFER_ABORT, Read: Name.READ, Release: Name.RELEASE, Finish: Name.FINISH, Abort: Name.ABORT}


def operation_name(operation: Operation) -> Name:
    try:
        return _NAMES[type(operation)]
    except KeyError as error:
        raise ModularError("wire") from error


class Contract(Protocol):
    """An installed implementation closes each of its eight application slots."""
    @staticmethod
    def descriptor() -> bytes: ...
    @staticmethod
    def allows(operation: Name) -> bool: ...
    @staticmethod
    def decode_prepare(value: Any) -> object: ...
    @staticmethod
    def decode_command(value: Any) -> object: ...
    @staticmethod
    def decode_import(value: Any) -> object: ...
    @staticmethod
    def decode_metadata(value: Any) -> object: ...
    @staticmethod
    def decode_finish(value: Any) -> object: ...
    @staticmethod
    def decode_result(value: Any) -> object: ...
    @staticmethod
    def decode_imported(value: Any) -> object: ...
    @staticmethod
    def decode_terminal(value: Any) -> object: ...
    @staticmethod
    def check_input(operation: Operation) -> None: ...
    @staticmethod
    def check_response(operation: Operation, body: Body, context: object) -> None: ...
    @staticmethod
    def check_import_metadata(descriptor: object, metadata: object) -> None: ...


def _binding(value: Any) -> BufferBinding:
    obj = closed(value, {"profile_digest", "application_digest", "run_id", "endpoint_id", "generation"})
    result = BufferBinding(**obj)
    try:
        result.validate()
    except ValueError as error:
        raise ModularError("binding") from error
    return result


def _reference(value: Any) -> BufferRef:
    obj = closed(value, {"generation", "buffer_id"})
    if type(obj["generation"]) is not str or len(obj["generation"]) != 36 or not integer(obj["buffer_id"]):
        raise ModularError("wire")
    return BufferRef(**obj)


def _chunk(value: Any) -> BufferChunk:
    obj = closed(value, {"schema", "manifest_digest", "index", "offset", "decoded_length", "chunk_sha256", "data_base64"})
    # Structural decode preserves semantic failures for pre-execution admission.
    if any(not integer(obj[k], 0) for k in ("index", "offset", "decoded_length")) or any(type(obj[k]) is not str for k in ("schema", "manifest_digest", "chunk_sha256", "data_base64")):
        raise ModularError("wire")
    return BufferChunk(**obj)


def _typed(decoder: Any, value: Any) -> object:
    result = decoder(value)
    check_immutable(result)
    return result


def decode_operation(value: Any, contract: type[Contract]) -> Operation:
    obj = closed(value, {"kind", "data"})
    name = Name(obj["kind"])
    data = obj["data"]
    if name == Name.PREPARE: return Prepare(_typed(contract.decode_prepare, data))
    if name == Name.APPLICATION: return Application(_typed(contract.decode_command, data))
    if name == Name.IMPORT: return ImportBegin(_typed(contract.decode_import, data))
    if name == Name.FINISH: return Finish(_typed(contract.decode_finish, data))
    if name == Name.APPEND:
        row = closed(data, {"reference", "chunk"})
        return Append(_reference(row["reference"]), _chunk(row["chunk"]))
    if name == Name.READ:
        row = closed(data, {"reference", "expected_manifest_digest", "index"})
        if not integer(row["index"], 0) or type(row["expected_manifest_digest"]) is not str: raise ModularError("wire")
        return Read(_reference(row["reference"]), row["expected_manifest_digest"], row["index"])
    if name == Name.SEAL:
        row = closed(data, {"reference", "expected_import_request_digest", "expected_source_manifest_digest"})
        if type(row["expected_import_request_digest"]) is not str or type(row["expected_source_manifest_digest"]) is not str: raise ModularError("wire")
        return Seal(_reference(row["reference"]), row["expected_import_request_digest"], row["expected_source_manifest_digest"])
    if name in (Name.BUFFER_ABORT, Name.RELEASE):
        row = closed(data, {"reference"})
        cls = {Name.BUFFER_ABORT: BufferAbort, Name.RELEASE: Release}[name]
        return cls(_reference(row["reference"]))
    if name == Name.ABORT:
        closed(data, set())
        return Abort()
    raise ModularError("wire")


def operation_value(operation: Operation) -> dict[str, Any]:
    name = operation_name(operation)
    data = immutable_value(operation.data) if type(operation) in (Prepare, Application, ImportBegin, Finish) else immutable_value(operation)
    return {"kind": name.value, "data": data}


@dataclass(frozen=True, slots=True)
class Execute: expected_predecessor_result_digest: str | None; operation: Operation
@dataclass(frozen=True, slots=True)
class Query: original_request_digest: str
@dataclass(frozen=True, slots=True)
class Ack: original_request_digest: str; result_digest: str
Command = Execute | Query | Ack


@dataclass(frozen=True, slots=True)
class Request:
    binding: BufferBinding
    sequence: int
    command: Command
    request_digest: str

    def value(self) -> dict[str, Any]:
        command = self.command
        if type(command) is Execute:
            row = {"kind": "execute", "expected_predecessor_result_digest": command.expected_predecessor_result_digest, "operation": operation_value(command.operation)}
        elif type(command) is Query:
            row = {"kind": "result", "original_request_digest": command.original_request_digest}
        elif type(command) is Ack:
            row = {"kind": "ack", "original_request_digest": command.original_request_digest, "result_digest": command.result_digest}
        else: raise ModularError("wire")
        return {"schema": REQUEST_SCHEMA, "binding": immutable_value(self.binding), "sequence": self.sequence, "command": row, "request_digest": self.request_digest}

    @staticmethod
    def create(binding: BufferBinding, sequence: int, command: Command) -> bytes:
        binding.validate()
        if not integer(sequence): raise ModularError("wire")
        value = Request(binding, sequence, command, "").value()
        # Keep exact extent and universal scalar checks before hashing.
        _validate_json(value)
        value["request_digest"] = typed_digest(REQUEST_SCHEMA, value, "request_digest")
        return encode(value)

    @staticmethod
    def decode(payload: bytes, binding: BufferBinding, contract: type[Contract], *, scratch: bytearray | None = None) -> Request:
        result = Request._decode_raw(parse(payload), binding, contract)
        # The helper's entire raw object tree has died before this second phase.
        result.verify(binding, scratch=scratch)
        return result

    @staticmethod
    def _decode_raw(value: Any, binding: BufferBinding, contract: type[Contract]) -> Request:
        value = closed(value, {"schema", "binding", "sequence", "command", "request_digest"})
        if value["schema"] != REQUEST_SCHEMA or not integer(value["sequence"]) or not digest_valid(value["request_digest"]) or typed_digest(REQUEST_SCHEMA, value, "request_digest") != value["request_digest"]:
            raise ModularError("wire")
        actual = _binding(value["binding"])
        if actual != binding: raise ModularError("binding")
        command = value["command"]
        if type(command) is not dict: raise ModularError("wire")
        kind = command.get("kind")
        if kind == "execute":
            row = closed(command, {"kind", "expected_predecessor_result_digest", "operation"})
            previous = row["expected_predecessor_result_digest"]
            if previous is not None and not digest_valid(previous): raise ModularError("wire")
            parsed = Execute(previous, decode_operation(row["operation"], contract))
        elif kind == "result":
            row = closed(command, {"kind", "original_request_digest"})
            if not digest_valid(row["original_request_digest"]): raise ModularError("wire")
            parsed = Query(row["original_request_digest"])
        elif kind == "ack":
            row = closed(command, {"kind", "original_request_digest", "result_digest"})
            if not digest_valid(row["original_request_digest"]) or not digest_valid(row["result_digest"]): raise ModularError("wire")
            parsed = Ack(row["original_request_digest"], row["result_digest"])
        else: raise ModularError("wire")
        return Request(actual, value["sequence"], parsed, value["request_digest"])

    def verify(self, binding: BufferBinding, *, scratch: bytearray | None = None) -> None:
        value = self.value()
        if scratch is None:
            _validate_json(value)
        else:
            encode_into(value, scratch)
        if self.binding != binding or not integer(self.sequence) or not digest_valid(self.request_digest) or typed_digest(REQUEST_SCHEMA, value, "request_digest") != self.request_digest:
            raise ModularError("binding")


class Outcome(str, Enum):
    COMMITTED = "committed"
    REJECTED = "rejected_before_execution"
    NOT_ADMITTED = "not_admitted"
    INDETERMINATE = "indeterminate"
    UNAVAILABLE = "unavailable"
    ACKNOWLEDGED = "acknowledged"


class Code(str, Enum):
    OK = "ok"
    ROLE = "role"
    STATE = "state"
    INVALID = "invalid_input"
    CAPACITY = "capacity"
    BUFFER_UNAVAILABLE = "buffer_unavailable"
    CONFLICT = "conflict"
    PENDING = "result_pending"
    UNKNOWN = "execution_unknown"
    NO_RESULT = "no_matching_retained_result"
    RELEASED = "result_released"


class BodyKind(str, Enum):
    PREPARED = "prepared"
    APPLICATION = "application"
    IMPORT_RESERVED = "import_reserved"
    IMPORT_SEALED = "import_sealed"
    CHUNK = "chunk"
    BUFFER_CHANGED = "buffer_changed"
    FINISHED = "finished"
    ABORTED = "aborted"
    REJECTED = "rejected"
    NOT_ADMITTED = "not_admitted"
    INDETERMINATE = "indeterminate"
    UNAVAILABLE = "unavailable"
    ACKNOWLEDGED = "acknowledged"


@dataclass(frozen=True, slots=True)
class AckStamp: sequence: int; original_request_digest: str; result_digest: str
@dataclass(frozen=True, slots=True)
class SealedImport: manifest: BufferManifest; data: object
@dataclass(frozen=True, slots=True)
class Body:
    kind: BodyKind
    data: object = None

    def value(self) -> dict[str, Any]:
        result: dict[str, Any] = {"kind": self.kind.value}
        if self.kind == BodyKind.IMPORT_SEALED:
            if type(self.data) is not SealedImport: raise ModularError("wire")
            result.update(immutable_value(self.data))
            return result
        if self.kind in (BodyKind.PREPARED, BodyKind.APPLICATION, BodyKind.CHUNK, BodyKind.FINISHED): key = "data"
        elif self.kind in (BodyKind.IMPORT_RESERVED, BodyKind.BUFFER_CHANGED): key = "reference"
        elif self.kind == BodyKind.INDETERMINATE: key = "reason"
        elif self.kind == BodyKind.ACKNOWLEDGED: key = "stamp"
        else:
            if self.data is not None: raise ModularError("wire")
            return result
        result[key] = immutable_value(self.data)
        return result


def _body(value: Any, contract: type[Contract]) -> Body:
    if type(value) is not dict: raise ModularError("wire")
    kind = BodyKind(value.get("kind"))
    if kind == BodyKind.IMPORT_SEALED:
        row = closed(value, {"kind", "manifest", "data"})
        manifest_row = closed(row["manifest"], set(BufferManifest.__dataclass_fields__))
        manifest = BufferManifest(**{**manifest_row, "binding": _binding(manifest_row["binding"])})
        return Body(kind, SealedImport(manifest, _typed(contract.decode_imported, row["data"])))
    if kind in (BodyKind.PREPARED, BodyKind.APPLICATION, BodyKind.FINISHED, BodyKind.CHUNK):
        row = closed(value, {"kind", "data"})
        decoder = {BodyKind.PREPARED: contract.decode_result, BodyKind.APPLICATION: contract.decode_result,
                   BodyKind.FINISHED: contract.decode_terminal, BodyKind.CHUNK: _chunk}[kind]
        return Body(kind, _typed(decoder, row["data"]))
    if kind in (BodyKind.IMPORT_RESERVED, BodyKind.BUFFER_CHANGED): return Body(kind, _reference(closed(value, {"kind", "reference"})["reference"]))
    if kind == BodyKind.INDETERMINATE:
        reason = closed(value, {"kind", "reason"})["reason"]
        if reason not in ("backend", "invalid_output", "internal"): raise ModularError("wire")
        return Body(kind, reason)
    if kind == BodyKind.ACKNOWLEDGED:
        row = closed(closed(value, {"kind", "stamp"})["stamp"], {"sequence", "original_request_digest", "result_digest"})
        if not integer(row["sequence"]) or not digest_valid(row["original_request_digest"]) or not digest_valid(row["result_digest"]): raise ModularError("wire")
        return Body(kind, AckStamp(**row))
    closed(value, {"kind"})
    return Body(kind)


@dataclass(frozen=True, slots=True)
class Response:
    binding: BufferBinding
    sequence: int
    operation: Name
    request_digest: str
    outcome: Outcome
    code: Code
    body: Body
    result_digest: str = ""

    def check_shape(self) -> None:
        kind, op, code, outcome = self.body.kind, self.operation, self.code, self.outcome
        expected = {Name.PREPARE: BodyKind.PREPARED, Name.APPLICATION: BodyKind.APPLICATION, Name.IMPORT: BodyKind.IMPORT_RESERVED,
                    Name.SEAL: BodyKind.IMPORT_SEALED, Name.READ: BodyKind.CHUNK, Name.APPEND: BodyKind.BUFFER_CHANGED,
                    Name.BUFFER_ABORT: BodyKind.BUFFER_CHANGED, Name.RELEASE: BodyKind.BUFFER_CHANGED, Name.FINISH: BodyKind.FINISHED, Name.ABORT: BodyKind.ABORTED}
        valid = (outcome == Outcome.COMMITTED and code == Code.OK and expected.get(op) == kind
                 or outcome == Outcome.REJECTED and code in (Code.ROLE, Code.STATE, Code.INVALID, Code.CAPACITY, Code.BUFFER_UNAVAILABLE) and kind == BodyKind.REJECTED and op not in (Name.RESULT, Name.ACK)
                 or outcome == Outcome.NOT_ADMITTED and code in (Code.CONFLICT, Code.PENDING) and kind == BodyKind.NOT_ADMITTED and op != Name.RESULT
                 or outcome == Outcome.INDETERMINATE and code == Code.UNKNOWN and kind == BodyKind.INDETERMINATE and op not in (Name.RESULT, Name.ACK)
                 or outcome == Outcome.UNAVAILABLE and code == Code.NO_RESULT and kind == BodyKind.UNAVAILABLE
                 or outcome == Outcome.ACKNOWLEDGED and code == Code.RELEASED and kind == BodyKind.ACKNOWLEDGED and op == Name.ACK
                 and type(self.body.data) is AckStamp and self.body.data.sequence == self.sequence)
        if not valid: raise ModularError("wire")

    def encode(self) -> bytes:
        slot = bytearray(FRAME_BYTES)
        length, _ = self.write(slot)
        return bytes(memoryview(slot)[:length])

    def write(self, slot: bytearray) -> tuple[int, str]:
        self.check_shape()
        value = {"schema": RESPONSE_SCHEMA, "binding": immutable_value(self.binding), "sequence": self.sequence,
                 "operation": self.operation.value, "request_digest": self.request_digest, "outcome": self.outcome.value,
                 "code": self.code.value, "body": self.body.value(), "result_digest": ""}
        encode_into(value, slot)
        value["result_digest"] = typed_digest(RESPONSE_SCHEMA, value, "result_digest")
        length = encode_into(value, slot)
        return length, value["result_digest"]

    @staticmethod
    def decode(payload: bytes, binding: BufferBinding, contract: type[Contract]) -> Response:
        result = Response._decode_raw(parse(payload), binding, contract)
        # The raw response tree is gone before constructing its checked projection.
        slot = bytearray(FRAME_BYTES)
        _, digest = result.write(slot)
        if digest != result.result_digest: raise ModularError("wire")
        return result

    @staticmethod
    def _decode_raw(value: Any, binding: BufferBinding, contract: type[Contract]) -> Response:
        row = closed(value, {"schema", "binding", "sequence", "operation", "request_digest", "outcome", "code", "body", "result_digest"})
        if row["schema"] != RESPONSE_SCHEMA or not integer(row["sequence"]) or not digest_valid(row["request_digest"]) or not digest_valid(row["result_digest"]) or typed_digest(RESPONSE_SCHEMA, row, "result_digest") != row["result_digest"]:
            raise ModularError("wire")
        actual = _binding(row["binding"])
        if actual != binding: raise ModularError("binding")
        result = Response(actual, row["sequence"], Name(row["operation"]), row["request_digest"], Outcome(row["outcome"]), Code(row["code"]), _body(row["body"], contract), row["result_digest"])
        result.check_shape()
        return result
