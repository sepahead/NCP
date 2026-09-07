"""Independent development payload primitives, without a protocol/application owner.

TrustedHostCreationContext is a trusted local API, not request attestation.
The host must supply its already verified request identity, never peer body fields.
The caller must serialize access to each pool. No remote outcome or retry is implied.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
import struct
from dataclasses import asdict, dataclass
from typing import Any

from .wire import LocalError, decode, encode

FRAME_BYTES = 65_536
CHUNK_BYTES = 32_768
BUFFER_BYTES = 8_388_608
ENDPOINT_BYTES = 67_108_864
COMPOSITION_BYTES = 268_435_456
LIVE_SLOTS = 24
INCOMPLETE_SLOTS = 12
ENDPOINTS = 16
MANIFEST_BYTES = 4_096
SEMANTIC_SLOTS = 64
METADATA_BYTES = 131_072
INPUT_SPEC_BYTES = 256
INPUT_METADATA_BYTES = 16_384
DIGEST_STAGING_BYTES = 131_072
MAX_ID = 9_007_199_254_740_991
_DIGEST = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z", re.ASCII)


class BufferError(ValueError):
    """One local primitive code, without a remote execution disposition."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"modular buffer error: {code}")


def _digest(value: Any) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _integer(value: Any, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _sha(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def encode_chunk(payload: bytes) -> str:
    if type(payload) is not bytes or not 1 <= len(payload) <= CHUNK_BYTES:
        raise BufferError("capacity")
    return base64.b64encode(payload).decode("ascii")


def decode_chunk(text: str) -> bytes:
    if type(text) is not str or not text or len(text) > ((CHUNK_BYTES + 2) // 3) * 4 or len(text) % 4:
        raise BufferError("wire")
    padding = len(text) - len(text.rstrip("="))
    if padding > 2 or len(text) // 4 * 3 - padding > CHUNK_BYTES:
        raise BufferError("wire")
    try:
        result = base64.b64decode(text, validate=True)
    except (ValueError, binascii.Error) as error:
        raise BufferError("wire") from error
    if not result or len(result) > CHUNK_BYTES or encode_chunk(result) != text:
        raise BufferError("wire")
    return result


@dataclass(frozen=True, slots=True)
class BufferBinding:
    profile_digest: str
    application_digest: str
    run_id: str
    endpoint_id: str
    generation: str

    def validate(self) -> None:
        if not _digest(self.profile_digest) or not _digest(self.application_digest):
            raise BufferError("binding")
        if any(type(v) is not str or _UUID.fullmatch(v) is None for v in (self.run_id, self.endpoint_id, self.generation)):
            raise BufferError("binding")


@dataclass(frozen=True, slots=True)
class TrustedHostCreationContext:
    """Shape-checked trusted host input; not proof of prior request verification."""

    binding: BufferBinding
    request_digest: str
    predecessor: str | None

    def __post_init__(self) -> None:
        if type(self.binding) is not BufferBinding:
            raise BufferError("binding")
        self.binding.validate()
        if not _digest(self.request_digest) or (self.predecessor is not None and not _digest(self.predecessor)):
            raise BufferError("binding")


@dataclass(frozen=True, slots=True)
class BufferRef:
    generation: str
    buffer_id: int


def _manifest_digest(value: dict[str, Any]) -> str:
    """Typed canonical projection for a previously validated closed manifest only."""
    output = bytearray(b"ncp.modular.buffer-manifest.v1\0")

    def append(data: bytes) -> None:
        if len(data) > DIGEST_STAGING_BYTES - len(output):
            raise BufferError("capacity")
        output.extend(data)

    def visit(item: Any) -> None:
        if item is None:
            append(b"\x00")
        elif type(item) is int:
            append(b"\x03" + struct.pack(">d", item))
        elif type(item) is str:
            text = item.encode("utf-8")
            append(b"\x04" + struct.pack(">Q", len(text)))
            append(text)
        elif type(item) is dict:
            append(b"\x06" + struct.pack(">Q", len(item)))
            for key in sorted(item, key=lambda k: k.encode("utf-8")):
                visit(key)
                visit(item[key])
        else:
            raise BufferError("wire")

    visit({key: item for key, item in value.items() if key != "manifest_digest"})
    return _sha(output)


@dataclass(frozen=True, slots=True)
class BufferManifest:
    schema: str
    binding: BufferBinding
    buffer_id: int
    creating_request_digest: str
    causal_predecessor: str | None
    semantic_digest: str
    byte_length: int
    payload_sha256: str
    chunk_bytes: int
    chunk_count: int
    imported_manifest_digest: str | None
    manifest_digest: str

    def reference(self) -> BufferRef:
        return BufferRef(self.binding.generation, self.buffer_id)

    def _shape(self, expected: BufferBinding) -> None:
        if type(self.binding) is not BufferBinding:
            raise BufferError("binding")
        self.binding.validate()
        if self.binding != expected:
            raise BufferError("binding")
        if self.schema != "ncp.modular.buffer-manifest.v1" or not _integer(self.buffer_id, 1, MAX_ID):
            raise BufferError("wire")
        if any(not _digest(v) for v in (self.creating_request_digest, self.semantic_digest, self.payload_sha256, self.manifest_digest)):
            raise BufferError("wire")
        if any(v is not None and not _digest(v) for v in (self.causal_predecessor, self.imported_manifest_digest)):
            raise BufferError("wire")
        if not _integer(self.byte_length, 1, BUFFER_BYTES) or not _integer(self.chunk_bytes, CHUNK_BYTES, CHUNK_BYTES):
            raise BufferError("wire")
        if not _integer(self.chunk_count, 1, BUFFER_BYTES // CHUNK_BYTES) or self.chunk_count != (self.byte_length + CHUNK_BYTES - 1) // CHUNK_BYTES:
            raise BufferError("wire")

    def verify(self, expected: BufferBinding) -> None:
        self._shape(expected)
        if len(encode(asdict(self))) > MANIFEST_BYTES:
            raise BufferError("capacity")
        if _manifest_digest(asdict(self)) != self.manifest_digest:
            raise BufferError("conflict")

    @classmethod
    def from_json(cls, payload: bytes, expected: BufferBinding) -> BufferManifest:
        if type(payload) is not bytes or not 1 <= len(payload) <= MANIFEST_BYTES:
            raise BufferError("capacity")
        try:
            obj = decode(payload)
            if type(obj) is not dict or set(obj) != set(cls.__dataclass_fields__):
                raise BufferError("wire")
            binding = obj["binding"]
            if type(binding) is not dict or set(binding) != set(BufferBinding.__dataclass_fields__):
                raise BufferError("wire")
            result = cls(**{**obj, "binding": BufferBinding(**binding)})
            result.verify(expected)
            return result
        except (TypeError, ValueError, LocalError) as error:
            if isinstance(error, BufferError):
                raise
            raise BufferError("wire") from error


@dataclass(frozen=True, slots=True)
class BufferChunk:
    schema: str
    manifest_digest: str
    index: int
    offset: int
    decoded_length: int
    chunk_sha256: str
    data_base64: str

    def decoded(self) -> bytes:
        if self.schema != "ncp.modular.buffer-chunk.v1" or not _digest(self.manifest_digest) or not _digest(self.chunk_sha256):
            raise BufferError("wire")
        if not _integer(self.index, 0, BUFFER_BYTES // CHUNK_BYTES - 1) or not _integer(self.offset, 0, BUFFER_BYTES - 1) or self.offset != self.index * CHUNK_BYTES:
            raise BufferError("wire")
        if not _integer(self.decoded_length, 1, CHUNK_BYTES):
            raise BufferError("wire")
        payload = decode_chunk(self.data_base64)
        if len(payload) != self.decoded_length or _sha(payload) != self.chunk_sha256:
            raise BufferError("conflict")
        return payload

    def to_json(self) -> bytes:
        self.decoded()
        return encode(asdict(self))

    @classmethod
    def from_json(cls, payload: bytes) -> BufferChunk:
        if type(payload) is not bytes or not 1 <= len(payload) <= FRAME_BYTES:
            raise BufferError("capacity")
        try:
            obj = decode(payload)
            if type(obj) is not dict or set(obj) != set(cls.__dataclass_fields__):
                raise BufferError("wire")
            result = cls(**obj)
            result.decoded()
            return result
        except (TypeError, ValueError, LocalError) as error:
            if isinstance(error, BufferError):
                raise
            raise BufferError("wire") from error


@dataclass(frozen=True, slots=True)
class BufferUsage:
    reserved_bytes: int
    live_slots: int
    incomplete_slots: int
    next_id: int


@dataclass(slots=True)
class _Entry:
    manifest: BufferManifest
    payload: bytes | bytearray
    prefix: int | None


class BufferPool:
    """One synchronous host-owned pool. Serialize calls; do not expose peer handles."""

    def __init__(self, binding: BufferBinding, semantics: tuple[str, ...]) -> None:
        if type(binding) is not BufferBinding:
            raise BufferError("binding")
        binding.validate()
        if type(semantics) is not tuple or not 1 <= len(semantics) <= SEMANTIC_SLOTS or any(not _digest(s) for s in semantics):
            raise BufferError("binding")
        if any(a >= b for a, b in zip(semantics, semantics[1:])):
            raise BufferError("binding")
        self._binding = binding
        self._semantics = semantics
        self._entries: dict[int, _Entry] = {}
        self._reserved = 0
        self._next_id = 1
        self._ticket = None

    def usage(self) -> BufferUsage:
        extra_bytes, extra_slots, extra_imports = (0, 0, 0) if self._ticket is None else self._ticket._pending()
        return BufferUsage(self._reserved + extra_bytes, len(self._entries) + extra_slots, sum(e.prefix is not None for e in self._entries.values()) + extra_imports, self._next_id)

    def _admit(self, context: TrustedHostCreationContext, semantic: str, length: int, incomplete: bool) -> None:
        if self._ticket is not None:
            raise BufferError("state")
        if type(context) is not TrustedHostCreationContext or context.binding != self._binding or semantic not in self._semantics:
            raise BufferError("binding")
        if not _integer(length, 1, BUFFER_BYTES) or self._next_id > MAX_ID or len(self._entries) >= LIVE_SLOTS or length > ENDPOINT_BYTES - self._reserved:
            raise BufferError("capacity")
        if incomplete and self.usage().incomplete_slots >= INCOMPLETE_SLOTS:
            raise BufferError("capacity")

    def _manifest(self, context: TrustedHostCreationContext, semantic: str, length: int, payload_hash: str, imported: str | None, *, buffer_id: int | None = None) -> BufferManifest:
        obj = dict(schema="ncp.modular.buffer-manifest.v1", binding=self._binding, buffer_id=self._next_id if buffer_id is None else buffer_id,
                   creating_request_digest=context.request_digest, causal_predecessor=context.predecessor,
                   semantic_digest=semantic, byte_length=length, payload_sha256=payload_hash, chunk_bytes=CHUNK_BYTES,
                   chunk_count=(length + CHUNK_BYTES - 1) // CHUNK_BYTES, imported_manifest_digest=imported, manifest_digest="0" * 64)
        provisional = BufferManifest(**obj)
        provisional._shape(self._binding)
        result = BufferManifest(**{**obj, "manifest_digest": _manifest_digest(asdict(provisional))})
        result.verify(self._binding)
        return result

    def publish(self, context: TrustedHostCreationContext, semantic: str, payload: bytes) -> BufferManifest:
        if type(payload) is not bytes:
            raise BufferError("wire")
        self._admit(context, semantic, len(payload), False)
        # Explicit owned immutable snapshot precedes its hash and publication.
        owned = memoryview(payload).tobytes()
        manifest = self._manifest(context, semantic, len(owned), _sha(owned), None)
        entry = _Entry(manifest, owned, None)
        self._entries[self._next_id] = entry
        self._reserved += len(owned)
        self._next_id += 1
        return manifest

    def begin_import(self, context: TrustedHostCreationContext, source: BufferManifest, expected_source: BufferBinding) -> BufferRef:
        if type(source) is not BufferManifest:
            raise BufferError("wire")
        source.verify(expected_source)
        self._admit(context, source.semantic_digest, source.byte_length, True)
        owned = bytearray(source.byte_length)
        manifest = self._manifest(context, source.semantic_digest, source.byte_length, source.payload_sha256, source.manifest_digest)
        reference = manifest.reference()
        entry = _Entry(manifest, owned, 0)
        self._entries[self._next_id] = entry
        self._reserved += len(owned)
        self._next_id += 1
        return reference

    def _entry(self, reference: BufferRef) -> _Entry:
        if self._ticket is not None:
            raise BufferError("state")
        if type(reference) is not BufferRef or reference.generation != self._binding.generation:
            raise BufferError("binding")
        if not _integer(reference.buffer_id, 1, MAX_ID):
            raise BufferError("wire")
        entry = self._entries.get(reference.buffer_id)
        if entry is None:
            raise BufferError("unavailable")
        return entry

    def append(self, reference: BufferRef, chunk: BufferChunk) -> None:
        entry = self._entry(reference)
        if type(chunk) is not BufferChunk:
            raise BufferError("wire")
        payload = chunk.decoded()
        if entry.prefix is None:
            raise BufferError("state")
        if chunk.manifest_digest != entry.manifest.imported_manifest_digest or chunk.offset != entry.prefix or len(payload) != min(CHUNK_BYTES, len(entry.payload) - entry.prefix):
            raise BufferError("conflict")
        end = entry.prefix + len(payload)
        entry.payload[entry.prefix:end] = payload
        entry.prefix = end

    def seal(self, reference: BufferRef) -> BufferManifest:
        entry = self._entry(reference)
        if entry.prefix != len(entry.payload):
            raise BufferError("state")
        if _sha(entry.payload) != entry.manifest.payload_sha256:
            raise BufferError("conflict")
        # The bytearray remains private; no mutation API accepts sealed entries.
        entry.prefix = None
        return entry.manifest

    def read(self, reference: BufferRef, index: int) -> BufferChunk:
        self.check_read(reference, index)
        entry = self._entry(reference)
        if entry.prefix is not None or not _integer(index, 0, entry.manifest.chunk_count - 1):
            raise BufferError("state")
        offset = index * CHUNK_BYTES
        payload = bytes(memoryview(entry.payload)[offset:offset + CHUNK_BYTES])
        return BufferChunk("ncp.modular.buffer-chunk.v1", entry.manifest.manifest_digest, index, offset, len(payload), _sha(payload), encode_chunk(payload))

    def check_read(self, reference: BufferRef, index: int) -> None:
        entry = self._entry(reference)
        if entry.prefix is not None or not _integer(index, 0, entry.manifest.chunk_count - 1):
            raise BufferError("state")

    def check_manifest(self, reference: BufferRef, expected: str) -> None:
        if self._entry(reference).manifest.manifest_digest != expected:
            raise BufferError("conflict")

    def _remove(self, reference: BufferRef, incomplete: bool) -> None:
        entry = self._entry(reference)
        if (entry.prefix is not None) != incomplete:
            raise BufferError("state")
        length = len(entry.payload)
        del self._entries[reference.buffer_id]
        self._reserved -= length

    def abort_import(self, reference: BufferRef) -> None:
        self._remove(reference, True)

    def release(self, reference: BufferRef) -> None:
        self._remove(reference, False)

    def inspect_import(self, reference: BufferRef) -> tuple[BufferManifest, memoryview]:
        entry = self._entry(reference)
        if entry.prefix != len(entry.payload):
            raise BufferError("state")
        if _sha(entry.payload) != entry.manifest.payload_sha256:
            raise BufferError("conflict")
        return entry.manifest, memoryview(entry.payload).toreadonly()

    def check_append(self, reference: BufferRef, chunk: BufferChunk) -> None:
        entry = self._entry(reference)
        if type(chunk) is not BufferChunk:
            raise BufferError("wire")
        payload = chunk.decoded()
        if entry.prefix is None:
            raise BufferError("state")
        if chunk.manifest_digest != entry.manifest.imported_manifest_digest or chunk.offset != entry.prefix or len(payload) != min(CHUNK_BYTES, len(entry.payload) - entry.prefix):
            raise BufferError("conflict")

    def check_release(self, reference: BufferRef, incomplete: bool) -> None:
        if (self._entry(reference).prefix is not None) != incomplete:
            raise BufferError("state")

    def reserve_outputs(self, specs: tuple[OutputSpec, ...]) -> OutputReservation:
        return self.reserve_execution((), specs)

    def reserve_execution(self, inputs: tuple[InputSpec, ...], specs: tuple[OutputSpec, ...]) -> OutputReservation:
        try:
            return self._reserve_execution(inputs, specs)
        except MemoryError as error:
            raise BufferError("capacity") from error

    def _reserve_execution(self, inputs: tuple[InputSpec, ...], specs: tuple[OutputSpec, ...]) -> OutputReservation:
        if self._ticket is not None:
            raise BufferError("state")
        if type(inputs) is not tuple or len(inputs) > LIVE_SLOTS:
            raise BufferError("capacity")
        selected = []
        for index, spec in enumerate(inputs):
            if type(spec) is not InputSpec or not _digest(spec.expected_manifest_digest):
                raise BufferError("wire")
            entry = self._entry(spec.reference)
            if entry.prefix is not None:
                raise BufferError("state")
            if entry.manifest.manifest_digest != spec.expected_manifest_digest:
                raise BufferError("conflict")
            if any(prior.reference == spec.reference for prior in inputs[:index]):
                raise BufferError("conflict")
            if len(encode(asdict(spec))) > INPUT_SPEC_BYTES:
                raise BufferError("capacity")
            selected.append(spec)
        if self._ticket is not None:
            raise BufferError("state")
        if type(specs) is not tuple or len(specs) > LIVE_SLOTS - len(self._entries):
            raise BufferError("capacity")
        total = 0
        for spec in specs:
            if type(spec) is not OutputSpec or not _integer(spec.byte_length, 1, BUFFER_BYTES) or spec.semantic_digest not in self._semantics:
                raise BufferError("capacity")
            total += spec.byte_length
        if total > ENDPOINT_BYTES - self._reserved or (specs and self._next_id + len(specs) - 1 > MAX_ID):
            raise BufferError("capacity")
        # All allocations stage before publishing a ticket or changing counters.
        try:
            slots = [_ReservedOutput(spec, bytearray(spec.byte_length), 0, 0) for spec in specs]
            ticket = OutputReservation(self, slots, tuple(selected))
        except MemoryError as error:
            raise BufferError("capacity") from error
        self._ticket = ticket
        return ticket

    def reserve_import(self, context: TrustedHostCreationContext, source: BufferManifest, expected: BufferBinding) -> ImportReservation:
        if type(source) is not BufferManifest:
            raise BufferError("wire")
        source.verify(expected)
        self._admit(context, source.semantic_digest, source.byte_length, True)
        manifest = self._manifest(context, source.semantic_digest, source.byte_length, source.payload_sha256, source.manifest_digest)
        try:
            ticket = ImportReservation(self, manifest, bytearray(source.byte_length))
        except MemoryError as error:
            raise BufferError("capacity") from error
        self._ticket = ticket
        return ticket


@dataclass(frozen=True, slots=True)
class OutputSpec:
    semantic_digest: str
    byte_length: int


@dataclass(frozen=True, slots=True)
class InputSpec:
    reference: BufferRef
    expected_manifest_digest: str


@dataclass(slots=True)
class _InputLifetime:
    active: bool = False


@dataclass(frozen=True, slots=True)
class InputView:
    """Trusted synchronous borrow. Do not retain extracted views after execution.

    A previously extracted Python memoryview cannot be revoked. This is not
    malicious-host isolation; caller copies need separate application bounds.
    """
    _manifest: BufferManifest
    _payload: memoryview
    _lifetime: _InputLifetime

    @property
    def manifest(self) -> BufferManifest:
        if not self._lifetime.active: raise BufferError("state")
        return self._manifest

    @property
    def payload(self) -> memoryview:
        if not self._lifetime.active: raise BufferError("state")
        return self._payload


@dataclass(slots=True)
class _ReservedOutput:
    spec: OutputSpec
    payload: bytearray | None
    prefix: int
    buffer_id: int


class OutputReservation:
    """Exclusive local ticket. Always close explicitly in the owner's finally block.

    Closing releases only known core-owned staging. It cannot attest external cleanup.
    Ignored write/seal errors latch and prevent a complete execution result.
    """

    def __init__(self, pool: BufferPool, slots: list[_ReservedOutput], inputs: tuple[InputSpec, ...] = ()) -> None:
        self._pool, self._slots = pool, slots
        self._inputs = inputs
        self._input_lifetime = _InputLifetime()
        self._context = None
        self._failed = False
        self._closed = False

    def _pending(self) -> tuple[int, int, int]:
        return sum(len(s.payload) for s in self._slots if s.payload is not None), sum(s.payload is not None for s in self._slots), 0

    def enter(self, context: TrustedHostCreationContext) -> None:
        if self._failed or self._closed or self._context is not None or type(context) is not TrustedHostCreationContext or context.binding != self._pool._binding:
            self._failed = True
            raise BufferError("binding")
        for slot in self._slots:
            slot.buffer_id = self._pool._next_id
            self._pool._next_id += 1
        self._context = context
        self._input_lifetime.active = True

    def expire_inputs(self) -> None:
        self._input_lifetime.active = False

    def input(self, index: int) -> InputView:
        if self._failed or self._closed or not self._input_lifetime.active:
            raise BufferError("state")
        if not _integer(index, 0, len(self._inputs) - 1):
            raise BufferError("unavailable")
        spec = self._inputs[index]
        entry = self._pool._entries.get(spec.reference.buffer_id)
        if entry is None: raise BufferError("unavailable")
        if entry.prefix is not None or entry.manifest.manifest_digest != spec.expected_manifest_digest:
            raise BufferError("state")
        return InputView(entry.manifest, memoryview(entry.payload).toreadonly(), self._input_lifetime)

    def write(self, index: int, offset: int, payload: bytes) -> None:
        try:
            if self._failed or self._closed or self._context is None or type(payload) is not bytes or not 1 <= len(payload) <= CHUNK_BYTES:
                raise BufferError("state")
            if not _integer(index, 0, len(self._slots) - 1):
                raise BufferError("unavailable")
            slot = self._slots[index]
            if slot.payload is None:
                raise BufferError("state")
            if not _integer(offset, 0, BUFFER_BYTES) or offset != slot.prefix or len(payload) > len(slot.payload) - slot.prefix:
                raise BufferError("conflict")
            slot.payload[offset:offset + len(payload)] = payload
            slot.prefix += len(payload)
        except BufferError:
            self._failed = True
            raise

    def seal(self, index: int) -> BufferManifest:
        try:
            if self._failed or self._closed or self._context is None:
                raise BufferError("state")
            if not _integer(index, 0, len(self._slots) - 1):
                raise BufferError("unavailable")
            slot = self._slots[index]
            if slot.payload is None or slot.prefix != len(slot.payload):
                raise BufferError("state")
            manifest = self._pool._manifest(self._context, slot.spec.semantic_digest, len(slot.payload), _sha(slot.payload), None, buffer_id=slot.buffer_id)
            self._pool._entries[slot.buffer_id] = _Entry(manifest, slot.payload, None)
            self._pool._reserved += len(slot.payload)
            slot.payload = None
            return manifest
        except BufferError:
            self._failed = True
            raise

    def complete(self) -> bool:
        return not self._closed and self._context is not None and not self._failed and all(s.payload is None for s in self._slots)

    def close(self) -> None:
        self._input_lifetime.active = False
        if not self._closed:
            if self._pool._ticket is not self:
                raise BufferError("state")
            self._slots.clear()
            self._inputs = ()
            self._pool._ticket = None
            self._closed = True

    def __enter__(self) -> OutputReservation:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class ImportReservation:
    def __init__(self, pool: BufferPool, manifest: BufferManifest, payload: bytearray) -> None:
        self._pool, self._manifest, self._payload = pool, manifest, payload
        self._closed = False

    def _pending(self) -> tuple[int, int, int]:
        return (0, 0, 0) if self._payload is None else (len(self._payload), 1, 1)

    def commit(self) -> BufferRef:
        if self._closed or self._payload is None or self._pool._ticket is not self:
            raise BufferError("state")
        ref = self._manifest.reference()
        self._pool._entries[ref.buffer_id] = _Entry(self._manifest, self._payload, 0)
        self._pool._reserved += len(self._payload)
        self._pool._next_id += 1
        self._payload = None
        return ref

    def close(self) -> None:
        if not self._closed:
            if self._pool._ticket is not self:
                raise BufferError("state")
            self._payload = None
            self._pool._ticket = None
            self._closed = True

    def __enter__(self) -> ImportReservation:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def admit_composition(reservations: tuple[int, ...]) -> int:
    if type(reservations) is not tuple or not 1 <= len(reservations) <= ENDPOINTS:
        raise BufferError("capacity")
    total = 0
    for value in reservations:
        if not _integer(value, 0, ENDPOINT_BYTES) or value > COMPOSITION_BYTES - total:
            raise BufferError("capacity")
        total += value
    return total
