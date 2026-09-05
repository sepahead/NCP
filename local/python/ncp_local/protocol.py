"""Independent serial ownership and exact-result client for local NCP.

Launch bindings come from a trusted supervisor before the private channel opens.
Payloads cannot change that binding or install a backend. There is no listener.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib.resources import files
import re
import threading
import time
from typing import Any, BinaryIO, Protocol
from uuid import uuid4

from .wire import (
    LocalError,
    LocalPreflightError,
    MAX_FRAME_BYTES,
    MAX_SEQUENCE,
    decode,
    digest_without,
    encode,
    local_digest,
    read_local_frame,
    write_local_frame,
)

LOCAL_PROFILE = "ncp.local-lockstep.v1"
REQUEST_SCHEMA = "ncp.local.request.v1"
RESPONSE_SCHEMA = "ncp.local.response.v1"
ROLES = {
    "neural": frozenset({"prepare", "step", "finish", "abort", "result", "ack"}),
    "body": frozenset({"prepare", "step", "finish", "abort", "result", "ack"}),
    "capture": frozenset(
        {"prepare", "reserve", "capture", "finish", "abort", "result", "ack"}
    ),
    "monitor": frozenset({"prepare", "assess", "finish", "abort", "result", "ack"}),
}
OPERATIONS = frozenset().union(*ROLES.values())
OUTCOMES = frozenset(
    {
        "committed",
        "rejected_before_execution",
        "indeterminate",
        "unavailable",
        "acknowledged",
    }
)
CODES = frozenset(
    {
        "ok",
        "wire",
        "binding",
        "role",
        "state",
        "conflict",
        "result_pending",
        "result_released",
        "invalid_input",
        "capacity",
        "execution_unknown",
        "retired",
    }
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\Z"
)
_REQUEST_KEYS = frozenset(
    {
        "schema",
        "profile_digest",
        "run_id",
        "generation",
        "sequence",
        "operation",
        "body",
        "request_digest",
    }
)
_RESPONSE_KEYS = frozenset(
    {
        "schema",
        "binding",
        "sequence",
        "operation",
        "request_digest",
        "outcome",
        "code",
        "body",
        "result_digest",
    }
)


def valid_digest(value: Any) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _valid_uuid(value: Any) -> bool:
    return type(value) is str and _UUID.fullmatch(value) is not None


def _sequence(value: Any) -> bool:
    return type(value) is int and 1 <= value <= MAX_SEQUENCE


def profile_descriptor_bytes() -> bytes:
    """Read the exact descriptor bundled in the installed SDK artifact."""
    return files("ncp_local").joinpath("local-profile.v1.json").read_bytes()


def profile_digest() -> str:
    descriptor = decode(profile_descriptor_bytes())
    if type(descriptor) is not dict or descriptor.get("profile") != LOCAL_PROFILE:
        raise LocalError("binding")
    if descriptor.get("roles") != {
        role: list(values) for role, values in _DESCRIPTOR_ROLES.items()
    }:
        raise LocalError("binding")
    if descriptor.get("max_frame_bytes") != MAX_FRAME_BYTES:
        raise LocalError("binding")
    return local_digest("ncp.local.profile.v1", descriptor)


_DESCRIPTOR_ROLES = {
    "neural": ("prepare", "step", "finish", "abort", "result", "ack"),
    "body": ("prepare", "step", "finish", "abort", "result", "ack"),
    "capture": ("prepare", "reserve", "capture", "finish", "abort", "result", "ack"),
    "monitor": ("prepare", "assess", "finish", "abort", "result", "ack"),
}


@dataclass(frozen=True)
class LocalBinding:
    """Immutable endpoint identity supplied by the private-channel supervisor."""

    profile_digest: str
    run_id: str
    generation: str
    role: str

    def __post_init__(self) -> None:
        if (
            not _valid_uuid(self.run_id)
            or not _valid_uuid(self.generation)
            or self.profile_digest != profile_digest()
            or type(self.role) is not str
            or self.role not in ROLES
        ):
            raise LocalError("binding")

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> LocalBinding:
        if type(value) is not dict or set(value) != {
            "profile_digest",
            "run_id",
            "generation",
            "role",
        }:
            raise LocalError("binding")
        if any(type(member) is not str for member in value.values()):
            raise LocalError("binding")
        return cls(**value)

    @classmethod
    def fresh(cls, role: str, *, run_id: str | None = None) -> LocalBinding:
        """Create a launch binding. Never use this to reconnect an old generation."""
        return cls(
            profile_digest(),
            str(uuid4()) if run_id is None else run_id,
            str(uuid4()),
            role,
        )


def make_request(
    binding: LocalBinding, sequence: int, operation: str, body: Any
) -> dict[str, Any]:
    if not _sequence(sequence) or operation not in OPERATIONS:
        raise LocalError("wire")
    request = {
        "schema": REQUEST_SCHEMA,
        "profile_digest": binding.profile_digest,
        "run_id": binding.run_id,
        "generation": binding.generation,
        "sequence": sequence,
        "operation": operation,
        "body": body,
    }
    request["request_digest"] = local_digest(REQUEST_SCHEMA, request)
    # Snapshot caller-owned data so later mutations cannot change a retry identity.
    return decode(encode(request))


def validate_request(request: Any) -> None:
    if type(request) is not dict or set(request) != _REQUEST_KEYS:
        raise LocalError("wire")
    if (
        request["schema"] != REQUEST_SCHEMA
        or not _sequence(request["sequence"])
        or type(request["operation"]) is not str
        or request["operation"] not in OPERATIONS
        or any(
            type(request[name]) is not str
            for name in ("run_id", "generation", "profile_digest", "request_digest")
        )
        or not valid_digest(request["request_digest"])
        or request["request_digest"]
        != digest_without(REQUEST_SCHEMA, request, "request_digest")
    ):
        raise LocalError("wire")


def verify_integrity(response: Any, binding: LocalBinding) -> None:
    """Verify sealed response bytes and fixed origin; this is not attestation."""
    if type(response) is not dict or set(response) != _RESPONSE_KEYS:
        raise LocalError("wire")
    if (
        response["schema"] != RESPONSE_SCHEMA
        or response["binding"] != binding.as_dict()
        or not _sequence(response["sequence"])
        or type(response["operation"]) is not str
        or response["operation"] not in OPERATIONS
        or not valid_digest(response["request_digest"])
        or not valid_digest(response["result_digest"])
        or response["result_digest"]
        != digest_without(RESPONSE_SCHEMA, response, "result_digest")
    ):
        raise LocalError("binding")
    outcome, code = response["outcome"], response["code"]
    if (
        type(outcome) is not str
        or type(code) is not str
        or outcome not in OUTCOMES
        or code not in CODES
    ):
        raise LocalError("wire")
    coherent = (
        (
            outcome == "committed"
            and code == "ok"
            and response["operation"] not in {"result", "ack"}
        )
        or (
            outcome == "acknowledged"
            and code == "ok"
            and response["operation"] == "ack"
        )
        or (
            outcome == "indeterminate"
            and code == "execution_unknown"
            and response["operation"] not in {"result", "ack"}
        )
        or (
            outcome == "unavailable"
            and code == "result_released"
            and response["operation"] != "ack"
        )
        or (
            outcome == "rejected_before_execution"
            and code not in {"ok", "execution_unknown", "result_released"}
        )
    )
    if not coherent:
        raise LocalError("wire")
    if response["operation"] not in ROLES[binding.role] and (outcome, code) != (
        "rejected_before_execution",
        "role",
    ):
        raise LocalError("binding")


def verify_response(
    response: Any, binding: LocalBinding, request: dict[str, Any]
) -> None:
    """Check closed schema, every correlation field, and the complete body digest."""
    validate_request(request)
    verify_integrity(response, binding)
    if (
        response["sequence"] != request["sequence"]
        or response["operation"] != request["operation"]
        or response["request_digest"] != request["request_digest"]
        or any(
            request[name] != getattr(binding, name)
            for name in ("run_id", "generation", "profile_digest")
        )
    ):
        raise LocalError("binding")


def verify_retrieved(
    response: Any,
    binding: LocalBinding,
    original: dict[str, Any],
    query: dict[str, Any],
) -> None:
    validate_request(query)
    if (
        query["operation"] != "result"
        or query["sequence"] != original["sequence"]
        or any(
            query[key] != original[key]
            for key in ("profile_digest", "run_id", "generation")
        )
        or query["body"] != {"request_digest": original["request_digest"]}
    ):
        raise LocalError("binding")
    verify_response(response, binding, original)
    if response["outcome"] not in {"committed", "indeterminate"}:
        raise LocalError("wire")


class LocalBackend(Protocol):
    """Owner-local application. Validation must not mutate or acquire resources."""

    def validate(self, operation: str, body: Any) -> None: ...
    def execute(self, operation: str, body: Any) -> Any: ...
    def retire(self) -> None: ...


@dataclass(frozen=True)
class _Retained:
    sequence: int
    request_digest: str
    result_digest: str
    payload: bytes


def _check_result_shape(body: Any) -> None:
    budget = 16_384

    def visit(value: Any, depth: int) -> None:
        nonlocal budget
        if depth > 32 or budget == 0:
            raise LocalError("capacity")
        budget -= 1
        if type(value) in (dict, list):
            if len(value) > budget or (type(value) is dict and len(value) > 4096):
                raise LocalError("capacity")
            for item in value.values() if type(value) is dict else value:
                visit(item, depth + 1)

    visit(body, 0)


class LocalOwner:
    """One generation, one execution owner, and one exact retained response."""

    def __init__(self, binding: LocalBinding, backend: LocalBackend) -> None:
        if type(binding) is not LocalBinding:
            raise LocalError("binding")
        self._binding = binding
        self._backend = backend
        self._high_water = 0
        self._retained: _Retained | None = None
        self._acknowledged: tuple[int, str, str] | None = None
        self._prepared = False
        self._finished = False
        self._retired = False
        self._lock = threading.RLock()

    @property
    def binding(self) -> LocalBinding:
        return self._binding

    @property
    def retained_bytes(self) -> int:
        with self._lock:
            return 0 if self._retained is None else len(self._retained.payload)

    def retire_generation(self) -> None:
        """Stop future mutation. Cleanup does not claim rollback."""
        with self._lock:
            if not self._retired:
                self._retired = True
                try:
                    self._backend.retire()
                except BaseException:
                    pass

    def _response(
        self, request: dict[str, Any], outcome: str, code: str, body: Any
    ) -> bytes:
        _check_result_shape(body)
        response = {
            "schema": RESPONSE_SCHEMA,
            "binding": self._binding.as_dict(),
            "sequence": request["sequence"],
            "operation": request["operation"],
            "request_digest": request["request_digest"],
            "outcome": outcome,
            "code": code,
            "body": body,
            "result_digest": "0" * 64,
        }
        # Prove the wire budget before creating a bounded typed projection.
        encode(response)
        response["result_digest"] = digest_without(
            RESPONSE_SCHEMA, response, "result_digest"
        )
        return encode(response)

    def _reject(self, request: dict[str, Any], code: str) -> bytes:
        return self._response(request, "rejected_before_execution", code, {})

    @staticmethod
    def _query_digest(request: dict[str, Any], name: str) -> str:
        body = request["body"]
        if (
            type(body) is not dict
            or set(body) != {name}
            or not valid_digest(body[name])
        ):
            raise LocalError("invalid_input")
        return body[name]

    def _lookup(self, request: dict[str, Any]) -> bytes:
        expected = self._query_digest(request, "request_digest")
        row = self._retained
        if row is not None and row.sequence == request["sequence"]:
            return (
                row.payload
                if row.request_digest == expected
                else self._reject(request, "conflict")
            )
        if request["sequence"] <= self._high_water:
            return self._response(request, "unavailable", "result_released", {})
        return self._reject(request, "state")

    def _acknowledge(self, request: dict[str, Any]) -> bytes:
        expected = self._query_digest(request, "result_digest")
        row = self._retained
        if row is not None:
            if row.sequence != request["sequence"] or row.result_digest != expected:
                return self._reject(request, "conflict")
            self._acknowledged = (row.sequence, row.request_digest, row.result_digest)
            self._retained = None
        elif (
            self._acknowledged is None
            or self._acknowledged[0] != request["sequence"]
            or self._acknowledged[2] != expected
        ):
            return self._reject(request, "conflict")
        return self._response(request, "acknowledged", "ok", {})

    def handle(self, payload: bytes) -> bytes:
        """Admit before mutation; retain exact outcomes until a digest-bound ACK."""
        with self._lock:
            request = decode(payload)
            validate_request(request)
            if any(
                request[name] != getattr(self._binding, name)
                for name in ("run_id", "generation", "profile_digest")
            ):
                return self._reject(request, "binding")
            operation, sequence = request["operation"], request["sequence"]
            if operation not in ROLES[self._binding.role]:
                return self._reject(request, "role")
            if operation == "result":
                return self._lookup(request)
            if operation == "ack":
                return self._acknowledge(request)
            row = self._retained
            if row is not None:
                if row.sequence != sequence:
                    return self._reject(request, "result_pending")
                return (
                    row.payload
                    if row.request_digest == request["request_digest"]
                    else self._reject(request, "conflict")
                )
            if sequence <= self._high_water:
                return self._response(request, "unavailable", "result_released", {})
            if self._retired:
                return self._reject(request, "retired")
            if (
                self._finished
                or sequence != self._high_water + 1
                or (not self._prepared and operation != "prepare")
                or (self._prepared and operation == "prepare")
            ):
                return self._reject(request, "state")
            try:
                self._backend.validate(operation, request["body"])
            except LocalError as error:
                code = (
                    error.code
                    if error.code
                    in CODES - {"ok", "execution_unknown", "result_released"}
                    else "invalid_input"
                )
                return self._reject(request, code)
            # Reserve bounded retained-wire capacity before entering the backend.
            # Python objects and digest staging have separate bounded allocations.
            reservation = bytearray(MAX_FRAME_BYTES)
            self._high_water = sequence
            try:
                body = self._backend.execute(operation, request["body"])
                output = self._response(request, "committed", "ok", body)
                self._prepared = True
                self._finished = operation in {"finish", "abort"}
            except BaseException:
                self.retire_generation()
                output = self._response(
                    request, "indeterminate", "execution_unknown", {}
                )
            reservation[: len(output)] = output
            result = decode(output)
            self._retained = _Retained(
                sequence,
                request["request_digest"],
                result["result_digest"],
                bytes(reservation[: len(output)]),
            )
            return self._retained.payload


def serve_local(owner: LocalOwner, reader: BinaryIO, writer: BinaryIO) -> None:
    """Serve an inherited channel. Every exit retires the installed generation."""
    try:
        while (payload := read_local_frame(reader)) is not None:
            write_local_frame(writer, owner.handle(payload))
    finally:
        owner.retire_generation()


class LocalClient:
    """Single-channel client with bounded deadlines and no retry after channel loss.

    ``request`` retains the verified result locally. Call ``acknowledge`` before
    another mutation. ``call`` performs both steps and returns the full response.
    Use unbuffered private subprocess pipes; a supervisor owns process termination.
    """

    def __init__(
        self,
        binding: LocalBinding,
        reader: BinaryIO,
        writer: BinaryIO,
        *,
        timeout_s: float = 10.0,
    ) -> None:
        if (
            type(binding) is not LocalBinding
            or type(timeout_s) not in (int, float)
            or not 0 < timeout_s <= 300
        ):
            raise LocalError("binding")
        self._binding = binding
        self._reader, self._writer = reader, writer
        self._timeout_s = timeout_s
        self._next_sequence = 1
        self._pending: tuple[dict[str, Any], dict[str, Any]] | None = None
        self._retired = False
        self._lock = threading.RLock()

    @property
    def binding(self) -> LocalBinding:
        return self._binding

    @property
    def retired(self) -> bool:
        return self._retired

    @property
    def next_sequence(self) -> int:
        """Preview the owned sequence; only a verified ACK advances it.

        The run owner must serialize preview and dispatch. A pending result
        retains its sequence until acknowledgement and blocks a new mutation.
        """
        with self._lock:
            return self._next_sequence

    def retire_generation(self) -> None:
        """Prevent reuse after cancellation. The supervisor must terminate peers."""
        with self._lock:
            self._retired = True

    def _exchange(
        self, request: dict[str, Any], original: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._retired:
            raise LocalPreflightError("retired")
        try:
            payload = encode(request)
        except LocalError as error:
            raise LocalPreflightError(error.code) from error
        deadline = time.monotonic() + self._timeout_s
        try:
            write_local_frame(self._writer, payload, deadline=deadline)
            received = read_local_frame(self._reader, deadline=deadline)
            if received is None:
                raise LocalError("wire")
            response = decode(received)
            if (
                original is not None
                and type(response) is dict
                and response.get("outcome") in {"committed", "indeterminate"}
            ):
                verify_retrieved(response, self._binding, original, request)
            else:
                verify_response(response, self._binding, request)
            return response
        except (Exception, KeyboardInterrupt) as error:
            self._retired = True
            raise LocalError("execution_unknown") from error

    def request(self, operation: str, body: Any) -> dict[str, Any]:
        with self._lock:
            if (
                type(operation) is not str
                or operation in {"result", "ack"}
                or operation not in ROLES[self._binding.role]
            ):
                raise LocalPreflightError("role")
            if self._pending is not None:
                raise LocalPreflightError("result_pending")
            try:
                request = make_request(
                    self._binding, self._next_sequence, operation, body
                )
            except LocalError as error:
                raise LocalPreflightError(error.code) from error
            response = self._exchange(request)
            if response["outcome"] in {"committed", "indeterminate"}:
                self._pending = (request, decode(encode(response)))
            elif response["outcome"] != "rejected_before_execution":
                self._retired = True
                raise LocalError("state")
            return response

    def result(self) -> dict[str, Any]:
        """Reopen the exact owed result on the still-healthy original channel."""
        with self._lock:
            if self._pending is None:
                raise LocalPreflightError("state")
            original, expected = self._pending
            query = make_request(
                self._binding,
                original["sequence"],
                "result",
                {"request_digest": original["request_digest"]},
            )
            response = self._exchange(query, original)
            if response["result_digest"] != expected["result_digest"]:
                self._retired = True
                raise LocalError("execution_unknown")
            return response

    def acknowledge(self) -> dict[str, Any]:
        with self._lock:
            if self._pending is None:
                raise LocalPreflightError("state")
            original, response = self._pending
            request = make_request(
                self._binding,
                original["sequence"],
                "ack",
                {"result_digest": response["result_digest"]},
            )
            acknowledgement = self._exchange(request)
            if (
                acknowledgement["outcome"] != "acknowledged"
                or acknowledgement["body"] != {}
            ):
                self._retired = True
                raise LocalError("execution_unknown")
            self._next_sequence += 1
            self._pending = None
            if response["outcome"] == "indeterminate" or original["operation"] in {
                "finish",
                "abort",
            }:
                self._retired = True
            return acknowledgement

    def call(self, operation: str, body: Any) -> dict[str, Any]:
        """Execute and acknowledge one verified outcome; return its full envelope."""
        with self._lock:
            response = self.request(operation, body)
            if self._pending is not None:
                self.acknowledge()
            return response
